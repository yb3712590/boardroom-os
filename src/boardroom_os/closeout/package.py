from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from enum import StrEnum
from typing import Any, Literal, Mapping, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    SkipValidation,
    ValidationError,
    field_serializer,
    field_validator,
    model_validator,
)

from boardroom_os.agents.skills import _normalize_ref_fields
from boardroom_os.audit.git_version_audit import (
    GitVersionAuditBundle,
    GitVersionAuditBundleRef,
    git_version_audit_readiness,
)
from boardroom_os.audit.process_audit import (
    ProcessAuditBundle,
    ProcessAuditBundleRef,
    process_audit_readiness,
)
from boardroom_os.audit.replay_bundle import ReplayBundle, ReplayBundleRef, replay_bundle_readiness
from boardroom_os.closeout.gate import (
    CloseoutGateResult,
    CloseoutGateResultRef,
    CloseoutGateVerdict,
    GitAuditReadiness,
    ProcessAuditReadiness,
    ReplayBundleReadiness,
)
from boardroom_os.closeout.closure import assert_checked_refs_cover
from boardroom_os.contracts.types import NonEmptyTextValue
from boardroom_os.evidence.table import FinalEvidenceTable, FinalEvidenceTableRef
from boardroom_os.events.types import ProjectRef
from boardroom_os.workspace.source_inventory import (
    PackageCommitRef,
    SourceInventory,
    SourceInventoryRef,
)


class CloseoutPackageError(ValueError):
    pass


class CloseoutPackageRef(NonEmptyTextValue):
    pass


class CloseoutPackageCheckedRef(NonEmptyTextValue):
    pass


class CloseoutPackageVerdict(StrEnum):
    PASSED = "passed"
    FAILED = "failed"


_UNSAFE_REF_PATTERNS = (
    ".pytest",
    "backend/app/core",
    "doc/refactor",
    "doc/live-report",
    "doc/tests",
)


def _canonical_jsonable(value: Any) -> Any:
    if isinstance(value, BaseModel):
        field_names = tuple(type(value).model_fields)
        if field_names == ("value",):
            return value.value
        return value.model_dump(mode="json")
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, tuple | list):
        return [_canonical_jsonable(item) for item in value]
    if isinstance(value, Mapping):
        return {str(key): _canonical_jsonable(item) for key, item in value.items()}
    return value


def _hash_jsonable(value: Any) -> str:
    encoded = json.dumps(
        _canonical_jsonable(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _require_timezone(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise CloseoutPackageError("generated_at must include timezone")
    return value


def _reject_unsafe_ref(value: str, *, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise CloseoutPackageError(f"{field_name} must not contain empty values")
    if (
        normalized.startswith("/")
        or "\\" in normalized
        or re.match(r"^[A-Za-z]:", normalized)
        or normalized in {".", ".."}
        or normalized.startswith("./")
        or normalized.startswith("../")
        or normalized.endswith("/")
        or normalized.endswith("/.")
        or normalized.endswith("/..")
        or "/./" in normalized
        or "/../" in normalized
        or any(pattern in normalized for pattern in _UNSAFE_REF_PATTERNS)
    ):
        raise CloseoutPackageError(f"{field_name} must be audit-friendly")
    return normalized


def _require_instance(value: Any, expected_type: type[Any], field_name: str) -> Any:
    if not isinstance(value, expected_type):
        raise CloseoutPackageError(f"{field_name} must be {expected_type.__name__}")
    return value


def _dedupe_checked_refs(refs: list[str]) -> tuple[CloseoutPackageCheckedRef, ...]:
    normalized: list[str] = []
    for ref in refs:
        normalized.append(_reject_unsafe_ref(str(ref), field_name="checked_refs"))
    deduped = tuple(dict.fromkeys(normalized))
    if not deduped:
        raise CloseoutPackageError("checked_refs must not be empty")
    return tuple(CloseoutPackageCheckedRef(value=ref) for ref in deduped)


def _checked_ref_values(values: tuple[CloseoutPackageCheckedRef, ...]) -> tuple[str, ...]:
    return tuple(value.value for value in values)


class CloseoutPackage(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    version: Literal[1] = 1
    closeout_package_id: CloseoutPackageRef
    project_ref: ProjectRef
    graph_version: int
    generated_at: datetime
    package_commit_ref: PackageCommitRef
    verdict: CloseoutPackageVerdict
    closeout_gate_result_ref: CloseoutGateResultRef
    acceptance_summary_ref: FinalEvidenceTableRef
    source_inventory_ref: SourceInventoryRef
    final_evidence_table_ref: FinalEvidenceTableRef
    replay_bundle_ref: ReplayBundleRef
    process_audit_bundle_ref: ProcessAuditBundleRef
    git_version_audit_bundle_ref: GitVersionAuditBundleRef
    checked_refs: tuple[CloseoutPackageCheckedRef, ...]

    @model_validator(mode="before")
    @classmethod
    def _normalize_refs(cls, data: Any) -> Any:
        if isinstance(data, dict) and "checked_refs" in data and not isinstance(
            data["checked_refs"], list | tuple
        ):
            raise CloseoutPackageError("checked_refs must be a tuple or list")
        return _normalize_ref_fields(
            data,
            {
                "closeout_package_id": CloseoutPackageRef,
                "project_ref": ProjectRef,
                "package_commit_ref": PackageCommitRef,
                "closeout_gate_result_ref": CloseoutGateResultRef,
                "acceptance_summary_ref": FinalEvidenceTableRef,
                "source_inventory_ref": SourceInventoryRef,
                "final_evidence_table_ref": FinalEvidenceTableRef,
                "replay_bundle_ref": ReplayBundleRef,
                "process_audit_bundle_ref": ProcessAuditBundleRef,
                "git_version_audit_bundle_ref": GitVersionAuditBundleRef,
            },
            {"checked_refs": CloseoutPackageCheckedRef},
        )

    @field_validator("generated_at")
    @classmethod
    def _require_generated_at_timezone(cls, value: datetime) -> datetime:
        return _require_timezone(value)

    @field_validator("graph_version")
    @classmethod
    def _require_positive_graph_version(cls, value: int) -> int:
        if value <= 0:
            raise CloseoutPackageError("graph_version must be positive")
        return value

    @field_validator("checked_refs")
    @classmethod
    def _validate_checked_refs(
        cls,
        values: tuple[CloseoutPackageCheckedRef, ...],
    ) -> tuple[CloseoutPackageCheckedRef, ...]:
        normalized = tuple(
            CloseoutPackageCheckedRef(
                value=_reject_unsafe_ref(value.value, field_name="checked_refs")
            )
            for value in values
        )
        if not normalized:
            raise CloseoutPackageError("checked_refs must not be empty")
        ref_values = _checked_ref_values(normalized)
        if len(set(ref_values)) != len(ref_values):
            raise CloseoutPackageError("checked_refs must be unique")
        return normalized

    @model_validator(mode="after")
    def _validate_package_shape(self) -> Self:
        if self.verdict is not CloseoutPackageVerdict.PASSED:
            raise CloseoutPackageError("verdict must be passed for v1 closeout package")
        if self.acceptance_summary_ref != self.final_evidence_table_ref:
            raise CloseoutPackageError("acceptance_summary_ref must match final_evidence_table_ref")
        required_refs = {
            self.closeout_gate_result_ref.value,
            self.source_inventory_ref.value,
            self.final_evidence_table_ref.value,
            self.replay_bundle_ref.value,
            self.process_audit_bundle_ref.value,
            self.git_version_audit_bundle_ref.value,
            self.package_commit_ref.value,
        }
        missing = required_refs - set(_checked_ref_values(self.checked_refs))
        if missing:
            raise CloseoutPackageError("checked_refs must include required closeout refs")
        return self

    @field_serializer("verdict")
    def _serialize_verdict(self, value: CloseoutPackageVerdict) -> str:
        return value.value


class CloseoutPackageBuilderInput(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    closeout_gate_result: SkipValidation[CloseoutGateResult]
    source_inventory: SkipValidation[SourceInventory]
    final_evidence_table: SkipValidation[FinalEvidenceTable]
    replay_bundle: SkipValidation[ReplayBundle]
    replay_readiness: SkipValidation[ReplayBundleReadiness]
    process_audit_bundle: SkipValidation[ProcessAuditBundle]
    process_audit_readiness: SkipValidation[ProcessAuditReadiness]
    git_version_audit_bundle: SkipValidation[GitVersionAuditBundle]
    git_audit_readiness: SkipValidation[GitAuditReadiness]
    graph_version: int
    generated_at: datetime

    @field_validator("generated_at")
    @classmethod
    def _require_generated_at_timezone(cls, value: datetime) -> datetime:
        return _require_timezone(value)

    @field_validator("graph_version")
    @classmethod
    def _require_positive_graph_version(cls, value: int) -> int:
        if value <= 0:
            raise CloseoutPackageError("graph_version must be positive")
        return value

    @field_validator(
        "closeout_gate_result",
        "source_inventory",
        "final_evidence_table",
        "replay_bundle",
        "replay_readiness",
        "process_audit_bundle",
        "process_audit_readiness",
        "git_version_audit_bundle",
        "git_audit_readiness",
        mode="before",
    )
    @classmethod
    def _require_typed_instances(cls, value: Any, info: Any) -> Any:
        expected_types = {
            "closeout_gate_result": CloseoutGateResult,
            "source_inventory": SourceInventory,
            "final_evidence_table": FinalEvidenceTable,
            "replay_bundle": ReplayBundle,
            "replay_readiness": ReplayBundleReadiness,
            "process_audit_bundle": ProcessAuditBundle,
            "process_audit_readiness": ProcessAuditReadiness,
            "git_version_audit_bundle": GitVersionAuditBundle,
            "git_audit_readiness": GitAuditReadiness,
        }
        expected_type = expected_types[info.field_name]
        return _require_instance(value, expected_type, info.field_name)

    @model_validator(mode="after")
    def _validate_input(self) -> Self:
        _validate_builder_input(self)
        return self


def build_closeout_package(builder_input: CloseoutPackageBuilderInput) -> CloseoutPackage:
    if not isinstance(builder_input, CloseoutPackageBuilderInput):
        raise CloseoutPackageError("builder_input must be CloseoutPackageBuilderInput")
    try:
        builder_input = CloseoutPackageBuilderInput.model_validate(builder_input)
    except ValidationError as error:
        raise CloseoutPackageError(str(error)) from error

    checked_refs = _build_checked_refs(builder_input)
    package_id = CloseoutPackageRef(
        value=(
            f"closeout-package.{builder_input.replay_bundle.project_ref.value}."
            f"{_closeout_package_hash(builder_input, checked_refs)[:16]}"
        )
    )
    return CloseoutPackage(
        closeout_package_id=package_id,
        project_ref=builder_input.replay_bundle.project_ref,
        graph_version=builder_input.graph_version,
        generated_at=builder_input.generated_at,
        package_commit_ref=builder_input.source_inventory.package_commit_ref,
        verdict=CloseoutPackageVerdict.PASSED,
        closeout_gate_result_ref=builder_input.closeout_gate_result.closeout_gate_result_id,
        acceptance_summary_ref=builder_input.final_evidence_table.final_evidence_table_id,
        source_inventory_ref=builder_input.source_inventory.source_inventory_id,
        final_evidence_table_ref=builder_input.final_evidence_table.final_evidence_table_id,
        replay_bundle_ref=builder_input.replay_bundle.replay_bundle_id,
        process_audit_bundle_ref=builder_input.process_audit_bundle.process_audit_bundle_id,
        git_version_audit_bundle_ref=builder_input.git_version_audit_bundle.git_version_audit_bundle_id,
        checked_refs=checked_refs,
    )


def _validate_builder_input(builder_input: CloseoutPackageBuilderInput) -> None:
    if builder_input.closeout_gate_result.verdict is not CloseoutGateVerdict.PASSED:
        raise CloseoutPackageError("closeout gate result must be passed")
    if builder_input.closeout_gate_result.blockers:
        raise CloseoutPackageError("passed closeout gate result must not include blockers")

    expected_gate_result_ref = CloseoutGateResultRef(
        value=(
            "closeout-gate-result."
            f"{builder_input.source_inventory.source_inventory_id.value}."
            f"{builder_input.final_evidence_table.final_evidence_table_id.value}"
        )
    )
    if builder_input.closeout_gate_result.closeout_gate_result_id != expected_gate_result_ref:
        raise CloseoutPackageError("closeout gate result id mismatch")

    replay_last_graph_version = max(
        attestation.event_window.last_graph_version
        for attestation in builder_input.replay_bundle.attestations
    )
    if builder_input.graph_version < replay_last_graph_version:
        raise CloseoutPackageError("graph_version must cover replay bundle event window")

    if builder_input.source_inventory.source_inventory_id != builder_input.git_version_audit_bundle.report.source_inventory_ref:
        raise CloseoutPackageError("source inventory ref mismatch")
    if builder_input.source_inventory.package_commit_ref != builder_input.git_version_audit_bundle.report.package_commit_ref:
        raise CloseoutPackageError("package_commit_ref mismatch")
    if builder_input.final_evidence_table.final_evidence_table_id is None:
        raise CloseoutPackageError("final_evidence_table_ref must not be empty")

    project_ref = builder_input.replay_bundle.project_ref
    if builder_input.process_audit_bundle.project_ref != project_ref:
        raise CloseoutPackageError("process audit bundle project_ref mismatch")
    if builder_input.git_version_audit_bundle.project_ref != project_ref:
        raise CloseoutPackageError("git version audit bundle project_ref mismatch")

    if replay_bundle_readiness(builder_input.replay_bundle) != builder_input.replay_readiness:
        raise CloseoutPackageError("replay readiness bundle mismatch")
    if process_audit_readiness(builder_input.process_audit_bundle) != builder_input.process_audit_readiness:
        raise CloseoutPackageError("process audit readiness bundle mismatch")
    if git_version_audit_readiness(builder_input.git_version_audit_bundle) != builder_input.git_audit_readiness:
        raise CloseoutPackageError("git audit readiness bundle mismatch")

    _validate_gate_checked_refs(builder_input)
    _validate_process_audit_checked_refs(builder_input)


def _validate_process_audit_checked_refs(builder_input: CloseoutPackageBuilderInput) -> None:
    required = _process_audit_required_checked_refs(builder_input)
    try:
        assert_checked_refs_cover(
            builder_input.process_audit_bundle.process_audit_bundle_id.value,
            required,
            builder_input.process_audit_bundle.checked_refs,
        )
        assert_checked_refs_cover(
            builder_input.process_audit_bundle.process_audit_report.process_audit_report_id.value,
            required,
            builder_input.process_audit_bundle.process_audit_report.checked_refs,
        )
    except ValueError as error:
        raise CloseoutPackageError("process audit checked_refs missing required closeout refs") from error


def _process_audit_required_checked_refs(builder_input: CloseoutPackageBuilderInput) -> set[str]:
    git_bundle = builder_input.git_version_audit_bundle
    return {
        *builder_input.closeout_gate_result.checked_refs,
        builder_input.source_inventory.source_inventory_id.value,
        builder_input.final_evidence_table.final_evidence_table_id.value,
        builder_input.replay_bundle.replay_bundle_id.value,
        builder_input.replay_bundle.replay_report.replay_report_id.value,
        builder_input.replay_readiness.summary_hash.value,
        builder_input.replay_readiness.event_range.value,
        builder_input.git_audit_readiness.final_commit_sha.value,
        builder_input.git_audit_readiness.source_inventory_hash.value,
        git_bundle.git_version_audit_bundle_id.value,
        git_bundle.report.git_version_audit_report_id.value,
        git_bundle.hash_manifest.hash_manifest_id.value,
        git_bundle.fact_set.fact_set_id.value,
        *(version.value for version in builder_input.replay_readiness.projection_versions),
        *(path.value for path in builder_input.process_audit_readiness.artifact_paths),
        *(binding.binding_id.value for binding in git_bundle.command_evidence_bindings),
    }


def _validate_gate_checked_refs(builder_input: CloseoutPackageBuilderInput) -> None:
    checked_refs = set(builder_input.closeout_gate_result.checked_refs)
    required = {
        builder_input.source_inventory.source_inventory_id.value,
        builder_input.final_evidence_table.final_evidence_table_id.value,
        builder_input.replay_readiness.summary_hash.value,
        builder_input.replay_readiness.event_range.value,
        builder_input.git_audit_readiness.final_commit_sha.value,
        builder_input.git_audit_readiness.source_inventory_hash.value,
        *(version.value for version in builder_input.replay_readiness.projection_versions),
        *(path.value for path in builder_input.process_audit_readiness.artifact_paths),
    }
    missing = required - checked_refs
    if missing:
        raise CloseoutPackageError("closeout gate checked_refs missing required refs")


def _build_checked_refs(
    builder_input: CloseoutPackageBuilderInput,
) -> tuple[CloseoutPackageCheckedRef, ...]:
    refs = [
        builder_input.closeout_gate_result.closeout_gate_result_id.value,
        builder_input.source_inventory.source_inventory_id.value,
        builder_input.final_evidence_table.final_evidence_table_id.value,
        builder_input.replay_bundle.replay_bundle_id.value,
        builder_input.process_audit_bundle.process_audit_bundle_id.value,
        builder_input.git_version_audit_bundle.git_version_audit_bundle_id.value,
        builder_input.source_inventory.package_commit_ref.value,
        builder_input.git_audit_readiness.final_commit_sha.value,
        builder_input.git_audit_readiness.source_inventory_hash.value,
        builder_input.replay_readiness.summary_hash.value,
        builder_input.replay_readiness.event_range.value,
        *(version.value for version in builder_input.replay_readiness.projection_versions),
        *(path.value for path in builder_input.process_audit_readiness.artifact_paths),
        builder_input.git_version_audit_bundle.report.git_version_audit_report_id.value,
        builder_input.git_version_audit_bundle.hash_manifest.hash_manifest_id.value,
        builder_input.git_version_audit_bundle.fact_set.fact_set_id.value,
        *(binding.binding_id.value for binding in builder_input.git_version_audit_bundle.command_evidence_bindings),
        builder_input.process_audit_bundle.process_audit_report.process_audit_report_id.value,
        builder_input.process_audit_bundle.hash_manifest.hash_manifest_id.value,
        *(builder_input.closeout_gate_result.checked_refs),
    ]
    return _dedupe_checked_refs(refs)


def _closeout_package_hash(
    builder_input: CloseoutPackageBuilderInput,
    checked_refs: tuple[CloseoutPackageCheckedRef, ...],
) -> str:
    return _hash_jsonable(
        {
            "version": 1,
            "project_ref": builder_input.replay_bundle.project_ref.value,
            "graph_version": builder_input.graph_version,
            "closeout_gate_result_ref": builder_input.closeout_gate_result.closeout_gate_result_id.value,
            "source_inventory_ref": builder_input.source_inventory.source_inventory_id.value,
            "final_evidence_table_ref": builder_input.final_evidence_table.final_evidence_table_id.value,
            "replay_bundle_ref": builder_input.replay_bundle.replay_bundle_id.value,
            "process_audit_bundle_ref": builder_input.process_audit_bundle.process_audit_bundle_id.value,
            "git_version_audit_bundle_ref": builder_input.git_version_audit_bundle.git_version_audit_bundle_id.value,
            "package_commit_ref": builder_input.source_inventory.package_commit_ref.value,
            "checked_refs": [ref.value for ref in checked_refs],
        }
    )
