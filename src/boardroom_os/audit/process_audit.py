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
    computed_field,
    field_serializer,
    field_validator,
    model_validator,
)

from boardroom_os.agents.skills import _normalize_ref_fields
from boardroom_os.checker.verdict import CheckerVerdict
from boardroom_os.closeout.gate import (
    GitAuditReadiness,
    ProcessAuditArtifactPath,
    ProcessAuditReadiness,
    ReplayBundleReadiness,
)
from boardroom_os.contracts.acceptance import AcceptanceContract
from boardroom_os.contracts.package import PackageContract
from boardroom_os.contracts.types import NonEmptyTextValue
from boardroom_os.evidence.table import FinalEvidenceTable
from boardroom_os.evidence.verifier import VerifiedEvidence
from boardroom_os.events.record import EventRecord
from boardroom_os.events.types import EventType, ProjectRef
from boardroom_os.execution.context_index import ProviderAttemptRef
from boardroom_os.execution.verification_run import VerificationRun
from boardroom_os.workspace.evidence_export import WorkspaceEvidenceBundle
from boardroom_os.workspace.source_inventory import SourceInventory
from boardroom_os.audit.replay_bundle import ReplayBundle

_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")

REQUIRED_PROCESS_AUDIT_ARTIFACT_PATHS = (
    "30-audit/process-audit.md",
    "30-audit/timeline.json",
    "30-audit/decision-log.md",
    "30-audit/agent-context-index.json",
    "30-audit/ticket-graph.md",
    "30-audit/artifact-lineage.json",
    "30-audit/evidence-map.json",
    "30-audit/git-version-audit.md",
    "30-audit/closeout-summary.md",
    "30-audit/replay-bundle-report.json",
)

_REQUIRED_PATH_SET = set(REQUIRED_PROCESS_AUDIT_ARTIFACT_PATHS)
_REQUIRED_TIMELINE_EVENT_KINDS = {
    "directive_received",
    "charter_created",
    "acceptance_contract_created",
    "package_contract_created",
    "seat_assigned",
    "ticket_created",
    "ticket_started",
    "provider_attempt_recorded",
    "work_product_submitted",
    "command_run_recorded",
    "evidence_verified",
    "checker_verdict_recorded",
    "closeout_prepared",
    "replay_bundle_materialized",
}
_EVENT_TYPE_TO_TIMELINE_KIND: dict[EventType, str] = {
    EventType.TICKET_CREATED: "ticket_created",
    EventType.TICKET_LEASED: "ticket_started",
    EventType.SEAT_ASSIGNED: "seat_assigned",
    EventType.PROVIDER_ATTEMPT_RECORDED: "provider_attempt_recorded",
    EventType.WORK_PRODUCT_SUBMITTED: "work_product_submitted",
    EventType.COMMAND_RUN_RECORDED: "command_run_recorded",
}
_LINEAGE_REQUIRED_FIELDS = {
    "producer_attempt_ref",
    "artifact_ref",
    "consumer_ticket_ref",
    "evidence_claim_ref",
    "verified_evidence_ref",
    "verifier_ref",
    "closeout_related_ref",
}
_FALLBACK_LINEAGE_REQUIRED_FIELDS = {
    "fallback_decision_record_ref",
    "verifier_ref",
    "evidence_map_ref",
    "closeout_related_ref",
}


class ProcessAuditError(ValueError):
    pass


class ProcessAuditBundleRef(NonEmptyTextValue):
    pass


class ProcessAuditReportRef(NonEmptyTextValue):
    pass


class ProcessAuditArtifactRef(NonEmptyTextValue):
    pass


class ProcessAuditManifestRef(NonEmptyTextValue):
    pass


class ProcessAuditContentRef(NonEmptyTextValue):
    pass


class ProcessAuditContentHash(NonEmptyTextValue):
    @field_validator("value")
    @classmethod
    def _require_lowercase_sha256(cls, value: str) -> str:
        if not _SHA256_PATTERN.fullmatch(value):
            raise ValueError("sha256 must be a 64-character lowercase hex digest")
        if len(set(value)) == 1:
            raise ValueError("sha256 must not be a placeholder or synthetic digest")
        return value


class ProcessAuditCheckedRef(NonEmptyTextValue):
    pass


class ProcessAuditArtifactKind(StrEnum):
    PROCESS_AUDIT = "process_audit"
    TIMELINE = "timeline"
    DECISION_LOG = "decision_log"
    AGENT_CONTEXT_INDEX = "agent_context_index"
    TICKET_GRAPH = "ticket_graph"
    ARTIFACT_LINEAGE = "artifact_lineage"
    EVIDENCE_MAP = "evidence_map"
    GIT_VERSION_AUDIT = "git_version_audit"
    CLOSEOUT_SUMMARY = "closeout_summary"
    REPLAY_BUNDLE_REPORT = "replay_bundle_report"


class ProcessAuditArtifactFormat(StrEnum):
    MARKDOWN = "markdown"
    JSON = "json"


_PATH_KIND_FORMAT: dict[str, tuple[ProcessAuditArtifactKind, ProcessAuditArtifactFormat]] = {
    "30-audit/process-audit.md": (
        ProcessAuditArtifactKind.PROCESS_AUDIT,
        ProcessAuditArtifactFormat.MARKDOWN,
    ),
    "30-audit/timeline.json": (
        ProcessAuditArtifactKind.TIMELINE,
        ProcessAuditArtifactFormat.JSON,
    ),
    "30-audit/decision-log.md": (
        ProcessAuditArtifactKind.DECISION_LOG,
        ProcessAuditArtifactFormat.MARKDOWN,
    ),
    "30-audit/agent-context-index.json": (
        ProcessAuditArtifactKind.AGENT_CONTEXT_INDEX,
        ProcessAuditArtifactFormat.JSON,
    ),
    "30-audit/ticket-graph.md": (
        ProcessAuditArtifactKind.TICKET_GRAPH,
        ProcessAuditArtifactFormat.MARKDOWN,
    ),
    "30-audit/artifact-lineage.json": (
        ProcessAuditArtifactKind.ARTIFACT_LINEAGE,
        ProcessAuditArtifactFormat.JSON,
    ),
    "30-audit/evidence-map.json": (
        ProcessAuditArtifactKind.EVIDENCE_MAP,
        ProcessAuditArtifactFormat.JSON,
    ),
    "30-audit/git-version-audit.md": (
        ProcessAuditArtifactKind.GIT_VERSION_AUDIT,
        ProcessAuditArtifactFormat.MARKDOWN,
    ),
    "30-audit/closeout-summary.md": (
        ProcessAuditArtifactKind.CLOSEOUT_SUMMARY,
        ProcessAuditArtifactFormat.MARKDOWN,
    ),
    "30-audit/replay-bundle-report.json": (
        ProcessAuditArtifactKind.REPLAY_BUNDLE_REPORT,
        ProcessAuditArtifactFormat.JSON,
    ),
}

_KIND_PATH = {kind: path for path, (kind, _format) in _PATH_KIND_FORMAT.items()}


def _canonical_jsonable(value: Any) -> Any:
    if isinstance(value, BaseModel):
        field_names = tuple(type(value).model_fields)
        if field_names == ("value",):
            return value.value
        return value.model_dump(mode="json")
    if isinstance(value, StrEnum):
        return value.value
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


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _hash_content(content: Any, artifact_format: ProcessAuditArtifactFormat) -> str:
    if artifact_format is ProcessAuditArtifactFormat.MARKDOWN:
        return _sha256_text(str(content))
    return _hash_jsonable(content)


def _hash_model(model: BaseModel) -> str:
    return _hash_jsonable(model.model_dump(mode="json"))


def _reject_unsafe_ref(value: str, *, field_name: str) -> str:
    if (
        value.startswith("/")
        or "\\" in value
        or re.match(r"^[A-Za-z]:", value)
        or value in {".", ".."}
        or value.endswith("/")
        or value.endswith("/.")
        or value.endswith("/..")
        or value.startswith("./")
        or value.startswith("../")
        or "/./" in value
        or "/../" in value
    ):
        raise ProcessAuditError(f"{field_name} must be audit-friendly relative path/ref")
    return value


def _validate_artifact_path_value(value: str) -> str:
    _reject_unsafe_ref(value, field_name="artifact path")
    if not value.startswith("30-audit/"):
        raise ProcessAuditError("artifact path must be under 30-audit")
    if value not in _REQUIRED_PATH_SET:
        raise ProcessAuditError("artifact path must be a required process audit path")
    return value


def _ref_value(value: Any) -> str:
    if isinstance(value, BaseModel) and tuple(type(value).model_fields) == ("value",):
        return str(value.value)
    if hasattr(value, "value"):
        return str(value.value)
    return str(value)


def _unique_strings(values: tuple[str, ...], *, field_name: str) -> tuple[str, ...]:
    normalized = tuple(value.strip() for value in values)
    if not normalized:
        raise ProcessAuditError(f"{field_name} must not be empty")
    if any(not value for value in normalized):
        raise ProcessAuditError(f"{field_name} must not contain empty values")
    if len(set(normalized)) != len(normalized):
        raise ProcessAuditError(f"{field_name} must be unique")
    return normalized


class ProcessAuditArtifact(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    artifact_id: ProcessAuditArtifactRef
    path: ProcessAuditArtifactPath
    kind: ProcessAuditArtifactKind
    format: ProcessAuditArtifactFormat
    content_ref: ProcessAuditContentRef
    content: Any
    sha256: ProcessAuditContentHash
    source_refs: tuple[str, ...]

    @model_validator(mode="before")
    @classmethod
    def _normalize_refs(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        if "source_refs" in data and not isinstance(data["source_refs"], list | tuple):
            raise ProcessAuditError("source_refs must be a tuple or list")
        return _normalize_ref_fields(
            data,
            {
                "artifact_id": ProcessAuditArtifactRef,
                "path": ProcessAuditArtifactPath,
                "content_ref": ProcessAuditContentRef,
                "sha256": ProcessAuditContentHash,
            },
        )

    @field_validator("content_ref")
    @classmethod
    def _reject_unsafe_content_ref(
        cls, value: ProcessAuditContentRef
    ) -> ProcessAuditContentRef:
        _reject_unsafe_ref(value.value, field_name="content_ref")
        return value

    @field_validator("source_refs")
    @classmethod
    def _validate_source_refs(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        return _unique_strings(values, field_name="source_refs")

    @model_validator(mode="after")
    def _validate_artifact(self) -> Self:
        _validate_artifact_path_value(self.path.value)
        expected = _PATH_KIND_FORMAT[self.path.value]
        if self.kind is not expected[0]:
            raise ProcessAuditError("artifact kind must match artifact path")
        if self.format is not expected[1]:
            raise ProcessAuditError("artifact format must match artifact path suffix")
        if self.content is None:
            raise ProcessAuditError("artifact content must not be empty")
        if isinstance(self.content, str) and not self.content.strip():
            raise ProcessAuditError("artifact content must not be empty")
        expected_hash = _hash_content(self.content, self.format)
        if self.sha256.value != expected_hash:
            raise ProcessAuditError("artifact sha256 must match canonical content")
        return self

    @field_serializer("kind")
    def _serialize_kind(self, value: ProcessAuditArtifactKind) -> str:
        return value.value

    @field_serializer("format")
    def _serialize_format(self, value: ProcessAuditArtifactFormat) -> str:
        return value.value


class ProcessAuditArtifactManifestEntry(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    artifact_ref: ProcessAuditArtifactRef
    path: ProcessAuditArtifactPath
    kind: ProcessAuditArtifactKind
    format: ProcessAuditArtifactFormat
    content_ref: ProcessAuditContentRef
    sha256: ProcessAuditContentHash

    @model_validator(mode="before")
    @classmethod
    def _normalize_refs(cls, data: Any) -> Any:
        return _normalize_ref_fields(
            data,
            {
                "artifact_ref": ProcessAuditArtifactRef,
                "path": ProcessAuditArtifactPath,
                "content_ref": ProcessAuditContentRef,
                "sha256": ProcessAuditContentHash,
            },
        )

    @model_validator(mode="after")
    def _validate_entry(self) -> Self:
        _validate_artifact_path_value(self.path.value)
        expected = _PATH_KIND_FORMAT[self.path.value]
        if self.kind is not expected[0]:
            raise ProcessAuditError("artifact manifest kind must match path")
        if self.format is not expected[1]:
            raise ProcessAuditError("artifact manifest format must match path")
        _reject_unsafe_ref(self.content_ref.value, field_name="content_ref")
        return self

    @field_serializer("kind")
    def _serialize_kind(self, value: ProcessAuditArtifactKind) -> str:
        return value.value

    @field_serializer("format")
    def _serialize_format(self, value: ProcessAuditArtifactFormat) -> str:
        return value.value


class ProcessAuditArtifactManifest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    artifact_manifest_id: ProcessAuditManifestRef
    project_ref: ProjectRef
    entries: tuple[ProcessAuditArtifactManifestEntry, ...]

    @model_validator(mode="before")
    @classmethod
    def _normalize_refs(cls, data: Any) -> Any:
        if isinstance(data, dict) and "entries" in data and not isinstance(
            data["entries"], list | tuple
        ):
            raise ProcessAuditError("artifact manifest entries must be a tuple or list")
        return _normalize_ref_fields(
            data,
            {
                "artifact_manifest_id": ProcessAuditManifestRef,
                "project_ref": ProjectRef,
            },
        )

    @field_validator("entries")
    @classmethod
    def _validate_entries(
        cls, values: tuple[ProcessAuditArtifactManifestEntry, ...]
    ) -> tuple[ProcessAuditArtifactManifestEntry, ...]:
        if len(values) != len(REQUIRED_PROCESS_AUDIT_ARTIFACT_PATHS):
            raise ProcessAuditError("artifact manifest must cover required process audit artifacts")
        paths = [entry.path.value for entry in values]
        if set(paths) != _REQUIRED_PATH_SET:
            raise ProcessAuditError("artifact manifest paths must match required process audit artifacts")
        if len(set(paths)) != len(paths):
            raise ProcessAuditError("artifact manifest paths must be unique")
        artifact_refs = [entry.artifact_ref.value for entry in values]
        content_refs = [entry.content_ref.value for entry in values]
        if len(set(artifact_refs)) != len(artifact_refs):
            raise ProcessAuditError("artifact manifest artifact refs must be unique")
        if len(set(content_refs)) != len(content_refs):
            raise ProcessAuditError("artifact manifest content refs must be unique")
        return values

    @property
    def entries_by_path(self) -> dict[str, ProcessAuditArtifactManifestEntry]:
        return {entry.path.value: entry for entry in self.entries}


class ProcessAuditHashManifest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    hash_manifest_id: ProcessAuditManifestRef
    project_ref: ProjectRef
    artifact_hashes: dict[str, ProcessAuditContentHash]
    artifact_manifest_hash: ProcessAuditContentHash
    process_audit_report_hash: ProcessAuditContentHash
    bundle_payload_hash: ProcessAuditContentHash

    @model_validator(mode="before")
    @classmethod
    def _normalize_refs(cls, data: Any) -> Any:
        normalized = _normalize_ref_fields(
            data,
            {
                "hash_manifest_id": ProcessAuditManifestRef,
                "project_ref": ProjectRef,
                "artifact_manifest_hash": ProcessAuditContentHash,
                "process_audit_report_hash": ProcessAuditContentHash,
                "bundle_payload_hash": ProcessAuditContentHash,
            },
        )
        if isinstance(normalized, dict) and "artifact_hashes" in normalized:
            try:
                normalized = dict(normalized)
                normalized["artifact_hashes"] = {
                    path: _process_audit_content_hash(value)
                    for path, value in normalized["artifact_hashes"].items()
                }
            except (TypeError, ValueError, ValidationError) as error:
                raise ProcessAuditError("hash manifest artifact hash invalid") from error
        return normalized

    @field_validator("artifact_hashes")
    @classmethod
    def _validate_artifact_hashes(
        cls, values: dict[str, ProcessAuditContentHash]
    ) -> dict[str, ProcessAuditContentHash]:
        if set(values) != _REQUIRED_PATH_SET:
            raise ProcessAuditError("hash manifest artifact hashes must cover required paths")
        for path in values:
            _validate_artifact_path_value(path)
        return dict(values)


def _process_audit_content_hash(value: Any) -> ProcessAuditContentHash:
    if isinstance(value, ProcessAuditContentHash):
        return value
    if isinstance(value, dict):
        return ProcessAuditContentHash.model_validate(value)
    return ProcessAuditContentHash(value=value)


class ProcessAuditReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    process_audit_report_id: ProcessAuditReportRef
    project_ref: ProjectRef
    generated_at: datetime
    process_audit_ref: ProcessAuditArtifactRef
    timeline_ref: ProcessAuditArtifactRef
    decision_log_ref: ProcessAuditArtifactRef
    agent_context_index_ref: ProcessAuditArtifactRef
    ticket_graph_ref: ProcessAuditArtifactRef
    artifact_lineage_ref: ProcessAuditArtifactRef
    evidence_map_ref: ProcessAuditArtifactRef
    git_audit_ref: ProcessAuditArtifactRef
    closeout_summary_ref: ProcessAuditArtifactRef
    replay_bundle_report_ref: ProcessAuditArtifactRef
    checked_refs: tuple[str, ...]
    expected_evidence_map_rows: tuple[dict[str, Any], ...]
    expected_fallback_decision_refs: tuple[str, ...] = ()
    replay_summary_hash: str
    replay_projection_versions: tuple[str, ...]

    @model_validator(mode="before")
    @classmethod
    def _normalize_refs(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        for field_name in (
            "checked_refs",
            "expected_evidence_map_rows",
            "expected_fallback_decision_refs",
            "replay_projection_versions",
        ):
            if field_name in data and not isinstance(data[field_name], list | tuple):
                raise ProcessAuditError(f"{field_name} must be a tuple or list")
        return _normalize_ref_fields(
            data,
            {
                "process_audit_report_id": ProcessAuditReportRef,
                "project_ref": ProjectRef,
                "process_audit_ref": ProcessAuditArtifactRef,
                "timeline_ref": ProcessAuditArtifactRef,
                "decision_log_ref": ProcessAuditArtifactRef,
                "agent_context_index_ref": ProcessAuditArtifactRef,
                "ticket_graph_ref": ProcessAuditArtifactRef,
                "artifact_lineage_ref": ProcessAuditArtifactRef,
                "evidence_map_ref": ProcessAuditArtifactRef,
                "git_audit_ref": ProcessAuditArtifactRef,
                "closeout_summary_ref": ProcessAuditArtifactRef,
                "replay_bundle_report_ref": ProcessAuditArtifactRef,
            },
        )

    @field_validator("generated_at")
    @classmethod
    def _require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ProcessAuditError("generated_at must include timezone")
        return value

    @field_validator("checked_refs", "replay_projection_versions")
    @classmethod
    def _validate_required_unique_strings(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        return _unique_strings(values, field_name="report refs")

    @field_validator("expected_fallback_decision_refs")
    @classmethod
    def _validate_optional_unique_strings(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(value.strip() for value in values)
        if any(not value for value in normalized):
            raise ProcessAuditError("fallback decision refs must not contain empty values")
        if len(set(normalized)) != len(normalized):
            raise ProcessAuditError("fallback decision refs must be unique")
        return normalized

    @field_validator("expected_evidence_map_rows")
    @classmethod
    def _validate_expected_rows(
        cls, values: tuple[dict[str, Any], ...]
    ) -> tuple[dict[str, Any], ...]:
        if not values:
            raise ProcessAuditError("expected evidence map rows must not be empty")
        return values

    @field_validator("replay_summary_hash")
    @classmethod
    def _validate_replay_summary_hash(cls, value: str) -> str:
        if not _SHA256_PATTERN.fullmatch(value):
            raise ProcessAuditError("replay summary_hash must be a sha256 digest")
        return value


class ProcessAuditBundle(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    version: Literal[1] = 1
    process_audit_bundle_id: ProcessAuditBundleRef
    project_ref: ProjectRef
    generated_at: datetime
    artifacts: tuple[ProcessAuditArtifact, ...]
    artifact_manifest: ProcessAuditArtifactManifest
    hash_manifest: ProcessAuditHashManifest
    process_audit_report: ProcessAuditReport
    checked_refs: tuple[str, ...]

    @model_validator(mode="before")
    @classmethod
    def _normalize_refs(cls, data: Any) -> Any:
        if isinstance(data, dict):
            for field_name in ("artifacts", "checked_refs"):
                if field_name in data and not isinstance(data[field_name], list | tuple):
                    raise ProcessAuditError(f"{field_name} must be a tuple or list")
        return _normalize_ref_fields(
            data,
            {
                "process_audit_bundle_id": ProcessAuditBundleRef,
                "project_ref": ProjectRef,
            },
        )

    @field_validator("generated_at")
    @classmethod
    def _require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ProcessAuditError("generated_at must include timezone")
        return value

    @field_validator("checked_refs")
    @classmethod
    def _validate_checked_refs(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        return _unique_strings(values, field_name="checked_refs")

    @model_validator(mode="after")
    def _validate_bundle(self) -> Self:
        _validate_bundle_shape(self)
        _revalidate_artifact_manifest(self)
        _revalidate_hash_manifest(self)
        _validate_report_alignment(self)
        return self

    @computed_field
    @property
    def bundle_hash(self) -> str:
        return self.hash_manifest.bundle_payload_hash.value


def _require_instance(value: Any, expected_type: type[Any], field_name: str) -> Any:
    if not isinstance(value, expected_type):
        raise ProcessAuditError(f"{field_name} must be {expected_type.__name__}")
    return value


class ProcessAuditBuilderInput(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    project_ref: ProjectRef
    generated_at: datetime
    events: tuple[EventRecord, ...]
    package_contract: SkipValidation[PackageContract]
    acceptance_contract: SkipValidation[AcceptanceContract]
    agent_context_index: BaseModel
    ticket_graph_summary: BaseModel
    source_inventory: SkipValidation[SourceInventory]
    workspace_evidence_bundle: SkipValidation[WorkspaceEvidenceBundle]
    final_evidence_table: SkipValidation[FinalEvidenceTable]
    checker_verdict: SkipValidation[CheckerVerdict]
    verification_runs: tuple[SkipValidation[VerificationRun], ...]
    verified_evidence: tuple[SkipValidation[VerifiedEvidence], ...]
    provider_attempt_refs: tuple[ProviderAttemptRef, ...]
    replay_bundle: SkipValidation[ReplayBundle]
    replay_readiness: SkipValidation[ReplayBundleReadiness]
    git_audit_readiness: SkipValidation[GitAuditReadiness]

    @model_validator(mode="before")
    @classmethod
    def _normalize_refs(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        for field_name in (
            "events",
            "verification_runs",
            "verified_evidence",
            "provider_attempt_refs",
        ):
            if field_name in data and not isinstance(data[field_name], list | tuple):
                raise ProcessAuditError(f"{field_name} must be a tuple or list")
        return _normalize_ref_fields(
            data,
            {"project_ref": ProjectRef},
            {"provider_attempt_refs": ProviderAttemptRef},
        )

    @field_validator("generated_at")
    @classmethod
    def _require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ProcessAuditError("generated_at must include timezone")
        return value

    @field_validator("package_contract", mode="before")
    @classmethod
    def _require_package_contract(cls, value: Any) -> Any:
        return _require_instance(value, PackageContract, "package_contract")

    @field_validator("acceptance_contract", mode="before")
    @classmethod
    def _require_acceptance_contract(cls, value: Any) -> Any:
        return _require_instance(value, AcceptanceContract, "acceptance_contract")

    @field_validator("source_inventory", mode="before")
    @classmethod
    def _require_source_inventory(cls, value: Any) -> Any:
        return _require_instance(value, SourceInventory, "source_inventory")

    @field_validator("workspace_evidence_bundle", mode="before")
    @classmethod
    def _require_workspace_evidence_bundle(cls, value: Any) -> Any:
        return _require_instance(
            value,
            WorkspaceEvidenceBundle,
            "workspace_evidence_bundle",
        )

    @field_validator("final_evidence_table", mode="before")
    @classmethod
    def _require_final_evidence_table(cls, value: Any) -> Any:
        return _require_instance(value, FinalEvidenceTable, "final_evidence_table")

    @field_validator("checker_verdict", mode="before")
    @classmethod
    def _require_checker_verdict(cls, value: Any) -> Any:
        return _require_instance(value, CheckerVerdict, "checker_verdict")

    @field_validator("replay_bundle", mode="before")
    @classmethod
    def _require_replay_bundle(cls, value: Any) -> Any:
        return _require_instance(value, ReplayBundle, "replay_bundle")

    @field_validator("replay_readiness", mode="before")
    @classmethod
    def _require_replay_readiness(cls, value: Any) -> Any:
        return _require_instance(value, ReplayBundleReadiness, "replay_readiness")

    @field_validator("git_audit_readiness", mode="before")
    @classmethod
    def _require_git_audit_readiness(cls, value: Any) -> Any:
        return _require_instance(value, GitAuditReadiness, "git_audit_readiness")

    @field_validator("agent_context_index", "ticket_graph_summary", mode="before")
    @classmethod
    def _require_projection_model(cls, value: Any) -> Any:
        if not isinstance(value, BaseModel):
            raise ProcessAuditError("builder input fields must be typed model instances")
        return value

    @field_validator("events")
    @classmethod
    def _validate_events(cls, values: tuple[EventRecord, ...]) -> tuple[EventRecord, ...]:
        if not values:
            raise ProcessAuditError("events must not be empty")
        return values

    @field_validator("verification_runs")
    @classmethod
    def _validate_verification_runs(
        cls, values: tuple[VerificationRun, ...]
    ) -> tuple[VerificationRun, ...]:
        if not values:
            raise ProcessAuditError("verification_runs must not be empty")
        return values

    @field_validator("verified_evidence")
    @classmethod
    def _validate_verified_evidence(
        cls, values: tuple[VerifiedEvidence, ...]
    ) -> tuple[VerifiedEvidence, ...]:
        if not values:
            raise ProcessAuditError("verified_evidence must not be empty")
        return values

    @field_validator("provider_attempt_refs")
    @classmethod
    def _validate_provider_attempt_refs(
        cls, values: tuple[ProviderAttemptRef, ...]
    ) -> tuple[ProviderAttemptRef, ...]:
        if not values:
            raise ProcessAuditError("provider_attempt_refs must not be empty")
        if len({value.value for value in values}) != len(values):
            raise ProcessAuditError("provider_attempt_refs must be unique")
        return values

    @model_validator(mode="after")
    def _validate_input(self) -> Self:
        if self.replay_bundle.project_ref != self.project_ref:
            raise ProcessAuditError("replay bundle project_ref mismatch")
        for event in self.events:
            if event.project_ref != self.project_ref:
                raise ProcessAuditError("event project_ref mismatch")
        if self.source_inventory.package_contract_ref != self.package_contract.package_contract_id:
            raise ProcessAuditError("source inventory package contract mismatch")
        if self.workspace_evidence_bundle.final_evidence_table_ref != self.final_evidence_table.final_evidence_table_id:
            raise ProcessAuditError("workspace evidence bundle final table mismatch")
        if self.checker_verdict.final_evidence_table_ref != self.final_evidence_table.final_evidence_table_id:
            raise ProcessAuditError("checker verdict final table mismatch")
        if self.replay_readiness.summary_hash != self.replay_bundle.attestations[0].summary_hash:
            raise ProcessAuditError("replay readiness summary_hash mismatch")
        return self


def build_process_audit_bundle(builder_input: ProcessAuditBuilderInput) -> ProcessAuditBundle:
    if not isinstance(builder_input, ProcessAuditBuilderInput):
        raise ProcessAuditError("builder_input must be ProcessAuditBuilderInput")
    builder_input = _validate_builder_input_instance(builder_input)

    _validate_agent_context_index_payload(_agent_context_index_payload(builder_input))
    checked_refs = _checked_refs(builder_input)
    artifacts = _build_artifacts(builder_input, checked_refs)
    artifact_manifest = _build_artifact_manifest(builder_input, artifacts)
    report = _build_report(builder_input, artifacts, checked_refs)
    artifact_hashes = {
        artifact.path.value: artifact.sha256 for artifact in artifacts
    }
    partial_hash_manifest = {
        "hash_manifest_id": ProcessAuditManifestRef(
            value=f"process-audit-hash-manifest.{builder_input.project_ref.value}"
        ),
        "project_ref": builder_input.project_ref,
        "artifact_hashes": artifact_hashes,
        "artifact_manifest_hash": ProcessAuditContentHash(
            value=_hash_model(artifact_manifest)
        ),
        "process_audit_report_hash": ProcessAuditContentHash(value=_hash_model(report)),
    }
    bundle_payload_hash = ProcessAuditContentHash(
        value=_hash_bundle_payload(
            process_audit_bundle_id=ProcessAuditBundleRef(
                value=f"process-audit-bundle.{builder_input.project_ref.value}"
            ),
            project_ref=builder_input.project_ref,
            generated_at=builder_input.generated_at,
            artifacts=artifacts,
            artifact_manifest=artifact_manifest,
            hash_manifest_without_bundle_hash=partial_hash_manifest,
            process_audit_report=report,
            checked_refs=checked_refs,
        )
    )
    hash_manifest = ProcessAuditHashManifest(
        **partial_hash_manifest,
        bundle_payload_hash=bundle_payload_hash,
    )
    return ProcessAuditBundle(
        process_audit_bundle_id=ProcessAuditBundleRef(
            value=f"process-audit-bundle.{builder_input.project_ref.value}"
        ),
        project_ref=builder_input.project_ref,
        generated_at=builder_input.generated_at,
        artifacts=artifacts,
        artifact_manifest=artifact_manifest,
        hash_manifest=hash_manifest,
        process_audit_report=report,
        checked_refs=checked_refs,
    )


def _validate_builder_input_instance(
    builder_input: ProcessAuditBuilderInput,
) -> ProcessAuditBuilderInput:
    try:
        return ProcessAuditBuilderInput.model_validate(builder_input)
    except ValidationError as error:
        raise ProcessAuditError(str(error)) from error


def process_audit_readiness(bundle: ProcessAuditBundle) -> ProcessAuditReadiness:
    try:
        validated_bundle = _validate_bundle_instance(bundle)
    except ValidationError as error:
        raise ProcessAuditError(str(error)) from error
    _revalidate_artifact_manifest(validated_bundle)
    _revalidate_hash_manifest(validated_bundle)
    _validate_report_alignment(validated_bundle)
    _validate_timeline(validated_bundle)
    _validate_decision_log(validated_bundle)
    _validate_agent_context_index(validated_bundle)
    _validate_artifact_lineage(validated_bundle)
    _validate_evidence_map(validated_bundle)
    _validate_git_version_audit(validated_bundle)
    _validate_replay_bundle_report(validated_bundle)
    return ProcessAuditReadiness(
        artifact_paths=tuple(
            artifact.path for artifact in sorted(
                validated_bundle.artifacts,
                key=lambda item: REQUIRED_PROCESS_AUDIT_ARTIFACT_PATHS.index(item.path.value),
            )
        ),
        all_artifacts_present=True,
        timeline_key_events_present=True,
        agent_context_index_complete=True,
        artifact_lineage_complete=True,
        evidence_map_consistent_with_final_table=True,
    )


def _build_artifacts(
    builder_input: ProcessAuditBuilderInput,
    checked_refs: tuple[str, ...],
) -> tuple[ProcessAuditArtifact, ...]:
    content_by_kind = {
        ProcessAuditArtifactKind.PROCESS_AUDIT: _process_audit_markdown(builder_input),
        ProcessAuditArtifactKind.TIMELINE: _timeline_payload(builder_input),
        ProcessAuditArtifactKind.DECISION_LOG: _decision_log_markdown(builder_input),
        ProcessAuditArtifactKind.AGENT_CONTEXT_INDEX: _agent_context_index_payload(builder_input),
        ProcessAuditArtifactKind.TICKET_GRAPH: _ticket_graph_markdown(builder_input),
        ProcessAuditArtifactKind.ARTIFACT_LINEAGE: _artifact_lineage_payload(builder_input),
        ProcessAuditArtifactKind.EVIDENCE_MAP: _evidence_map_payload(builder_input),
        ProcessAuditArtifactKind.GIT_VERSION_AUDIT: _git_version_audit_markdown(builder_input),
        ProcessAuditArtifactKind.CLOSEOUT_SUMMARY: _closeout_summary_markdown(builder_input),
        ProcessAuditArtifactKind.REPLAY_BUNDLE_REPORT: _replay_bundle_report_payload(builder_input),
    }
    artifacts: list[ProcessAuditArtifact] = []
    for path in REQUIRED_PROCESS_AUDIT_ARTIFACT_PATHS:
        kind, artifact_format = _PATH_KIND_FORMAT[path]
        content = content_by_kind[kind]
        artifacts.append(
            ProcessAuditArtifact(
                artifact_id=ProcessAuditArtifactRef(value=f"process-audit-artifact.{kind.value}"),
                path=ProcessAuditArtifactPath(value=path),
                kind=kind,
                format=artifact_format,
                content_ref=ProcessAuditContentRef(value=f"process-audit-content.{kind.value}"),
                content=content,
                sha256=ProcessAuditContentHash(value=_hash_content(content, artifact_format)),
                source_refs=checked_refs,
            )
        )
    return tuple(artifacts)


def _build_artifact_manifest(
    builder_input: ProcessAuditBuilderInput,
    artifacts: tuple[ProcessAuditArtifact, ...],
) -> ProcessAuditArtifactManifest:
    return ProcessAuditArtifactManifest(
        artifact_manifest_id=ProcessAuditManifestRef(
            value=f"process-audit-artifact-manifest.{builder_input.project_ref.value}"
        ),
        project_ref=builder_input.project_ref,
        entries=tuple(
            ProcessAuditArtifactManifestEntry(
                artifact_ref=artifact.artifact_id,
                path=artifact.path,
                kind=artifact.kind,
                format=artifact.format,
                content_ref=artifact.content_ref,
                sha256=artifact.sha256,
            )
            for artifact in artifacts
        ),
    )


def _build_report(
    builder_input: ProcessAuditBuilderInput,
    artifacts: tuple[ProcessAuditArtifact, ...],
    checked_refs: tuple[str, ...],
) -> ProcessAuditReport:
    by_kind = {artifact.kind: artifact for artifact in artifacts}
    return ProcessAuditReport(
        process_audit_report_id=ProcessAuditReportRef(
            value=f"process-audit-report.{builder_input.project_ref.value}"
        ),
        project_ref=builder_input.project_ref,
        generated_at=builder_input.generated_at,
        process_audit_ref=by_kind[ProcessAuditArtifactKind.PROCESS_AUDIT].artifact_id,
        timeline_ref=by_kind[ProcessAuditArtifactKind.TIMELINE].artifact_id,
        decision_log_ref=by_kind[ProcessAuditArtifactKind.DECISION_LOG].artifact_id,
        agent_context_index_ref=by_kind[ProcessAuditArtifactKind.AGENT_CONTEXT_INDEX].artifact_id,
        ticket_graph_ref=by_kind[ProcessAuditArtifactKind.TICKET_GRAPH].artifact_id,
        artifact_lineage_ref=by_kind[ProcessAuditArtifactKind.ARTIFACT_LINEAGE].artifact_id,
        evidence_map_ref=by_kind[ProcessAuditArtifactKind.EVIDENCE_MAP].artifact_id,
        git_audit_ref=by_kind[ProcessAuditArtifactKind.GIT_VERSION_AUDIT].artifact_id,
        closeout_summary_ref=by_kind[ProcessAuditArtifactKind.CLOSEOUT_SUMMARY].artifact_id,
        replay_bundle_report_ref=by_kind[ProcessAuditArtifactKind.REPLAY_BUNDLE_REPORT].artifact_id,
        checked_refs=checked_refs,
        expected_evidence_map_rows=tuple(_evidence_map_payload(builder_input)["rows"]),
        expected_fallback_decision_refs=_fallback_decision_refs(builder_input),
        replay_summary_hash=builder_input.replay_readiness.summary_hash.value,
        replay_projection_versions=tuple(
            version.value for version in builder_input.replay_readiness.projection_versions
        ),
    )


def _markdown_lines(*lines: str) -> str:
    return "\n\n".join(lines)


def _process_audit_markdown(builder_input: ProcessAuditBuilderInput) -> str:
    return _markdown_lines(
        "# Process Audit",
        "## Requirement interpretation",
        f"Package contract: {builder_input.package_contract.package_contract_id.value}",
        f"Acceptance contract: {builder_input.acceptance_contract.acceptance_contract_id.value}",
        "## Contract formation",
        "AcceptanceContract and PackageContract constrain implementation evidence.",
        "## Team execution",
        "Agent seats received ExecutionPackage context and recorded ProviderAttempt facts.",
        "## Evidence verification",
        f"Final evidence table: {builder_input.final_evidence_table.final_evidence_table_id.value}",
        "## Checker review",
        f"Checker verdict: {builder_input.checker_verdict.checker_verdict_id.value}",
        "## Replay and closeout readiness",
        f"Replay bundle: {builder_input.replay_bundle.replay_bundle_id.value}",
    )


def _timeline_payload(builder_input: ProcessAuditBuilderInput) -> dict[str, Any]:
    event_log_items = [_timeline_item_from_event(event) for event in builder_input.events]
    covered_kinds = {item["kind"] for item in event_log_items}
    milestone_items = _timeline_milestone_items(builder_input, covered_kinds)
    ordered_events = sorted(
        (*event_log_items, *milestone_items),
        key=lambda item: (item["timestamp"], item["graph_version"], item["event_ref"]),
    )
    return {
        "project_ref": builder_input.project_ref.value,
        "archived_event_refs": [event.event_id.value for event in builder_input.events],
        "events": ordered_events,
    }


def _timeline_item_from_event(event: EventRecord) -> dict[str, Any]:
    return {
        "event_ref": event.event_id.value,
        "kind": _EVENT_TYPE_TO_TIMELINE_KIND.get(event.event_type, event.event_type.value),
        "timestamp": event.timestamp.isoformat(),
        "actor_ref": event.actor_ref.value,
        "graph_version": event.graph_version,
        "payload_refs": [payload_ref.value for payload_ref in event.payload_refs],
        "causation_refs": [event_ref.value for event_ref in event.causation_refs],
        "correlation_refs": [event_ref.value for event_ref in event.correlation_refs],
        "source": "event_log",
    }


def _timeline_milestone_items(
    builder_input: ProcessAuditBuilderInput,
    covered_kinds: set[str],
) -> list[dict[str, Any]]:
    milestone_specs = {
        "directive_received": (builder_input.acceptance_contract.project_charter_ref.value,),
        "charter_created": (builder_input.acceptance_contract.project_charter_ref.value,),
        "acceptance_contract_created": (builder_input.acceptance_contract.acceptance_contract_id.value,),
        "package_contract_created": (builder_input.package_contract.package_contract_id.value,),
        "seat_assigned": tuple(attempt.value for attempt in builder_input.provider_attempt_refs),
        "ticket_created": tuple(_ticket_refs(builder_input)),
        "ticket_started": tuple(_ticket_refs(builder_input)),
        "provider_attempt_recorded": tuple(attempt.value for attempt in builder_input.provider_attempt_refs),
        "work_product_submitted": tuple(entry.path.value for entry in builder_input.source_inventory.entries),
        "command_run_recorded": tuple(run.verification_run_id.value for run in builder_input.verification_runs),
        "evidence_verified": tuple(evidence.verified_evidence_id.value for evidence in builder_input.verified_evidence),
        "checker_verdict_recorded": (builder_input.checker_verdict.checker_verdict_id.value,),
        "closeout_prepared": (builder_input.final_evidence_table.final_evidence_table_id.value,),
        "replay_bundle_materialized": (builder_input.replay_bundle.replay_bundle_id.value,),
    }
    base_graph_version = max(event.graph_version for event in builder_input.events)
    items = []
    for index, kind in enumerate(sorted(_REQUIRED_TIMELINE_EVENT_KINDS - covered_kinds), start=1):
        items.append(
            {
                "event_ref": f"process-audit-timeline.{kind}",
                "kind": kind,
                "timestamp": builder_input.generated_at.isoformat(),
                "actor_ref": "boardroom-os",
                "graph_version": base_graph_version + index,
                "related_refs": list(milestone_specs[kind]),
                "source": "process_audit_projection",
            }
        )
    return items


def _ticket_refs(builder_input: ProcessAuditBuilderInput) -> tuple[str, ...]:
    return tuple(
        _ref_value(getattr(ticket, "ticket_ref", "ticket"))
        for ticket in getattr(builder_input.ticket_graph_summary, "tickets", ())
    )


def _decision_log_markdown(builder_input: ProcessAuditBuilderInput) -> str:
    return _markdown_lines(
        "# Decision Log",
        "## CEO / Human Board Decision",
        "CEO / human board accepted the directive and required evidence-backed closeout.",
        "## Architect / Contract Decision",
        f"Package contract {builder_input.package_contract.package_contract_id.value} governs delivery.",
        "## Checker Decision",
        f"Checker verdict {builder_input.checker_verdict.checker_verdict_id.value} is recorded.",
        "## Closeout Readiness Decision",
        "Closeout can only proceed after replay, git, evidence, and process audit readiness.",
    )


def _agent_context_index_payload(builder_input: ProcessAuditBuilderInput) -> dict[str, Any]:
    entries = []
    for entry in getattr(builder_input.agent_context_index, "entries", ()):
        provider_attempt_refs = tuple(getattr(entry, "provider_attempt_refs", ()))
        entries.append(
            {
                "entry_id": _ref_value(getattr(entry, "entry_id", "agent-context-entry")),
                "execution_package_ref": _optional_ref_value(
                    getattr(entry, "execution_package_ref", None)
                ),
                "model_execution_profile": _model_execution_profile_payload(
                    getattr(entry, "model_execution_profile", None)
                ),
                "provider_attempt_refs": [
                    _ref_value(ref) for ref in provider_attempt_refs
                ],
            }
        )
    return {"entries": entries}


def _model_execution_profile_payload(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    return _canonical_jsonable(value)


def _optional_ref_value(value: Any) -> str | None:
    if value is None:
        return None
    return _ref_value(value)


def _ticket_graph_markdown(builder_input: ProcessAuditBuilderInput) -> str:
    lines = ["# Ticket Graph"]
    for ticket in getattr(builder_input.ticket_graph_summary, "tickets", ()):
        acceptance_refs = ", ".join(
            _ref_value(ref) for ref in getattr(ticket, "acceptance_refs", ())
        )
        lines.extend(
            (
                f"## {_ref_value(getattr(ticket, 'ticket_ref', 'ticket'))}",
                f"Status: {getattr(ticket, 'status', 'unknown')}",
                f"Acceptance refs: {acceptance_refs}",
                f"Owner seat: {getattr(ticket, 'owner_seat_ref', 'unknown')}",
            )
        )
    return _markdown_lines(*lines)


def _artifact_lineage_payload(builder_input: ProcessAuditBuilderInput) -> dict[str, Any]:
    verified_by_ref = {
        evidence.verified_evidence_id.value: evidence for evidence in builder_input.verified_evidence
    }
    lineages = []
    for entry in builder_input.source_inventory.entries:
        for evidence_ref in entry.evidence_refs:
            evidence = verified_by_ref.get(evidence_ref.value)
            lineages.append(
                {
                    "producer_attempt_ref": entry.producer_attempt_ref.value,
                    "artifact_ref": entry.path.value,
                    "consumer_ticket_ref": entry.producer_ticket_ref.value,
                    "evidence_claim_ref": evidence.evidence_claim_ref.value if evidence else evidence_ref.value,
                    "verified_evidence_ref": evidence_ref.value,
                    "verifier_ref": _verification_ref_for_evidence(evidence),
                    "closeout_related_ref": builder_input.final_evidence_table.final_evidence_table_id.value,
                }
            )
    fallback_lineages = []
    for evidence in builder_input.verified_evidence:
        if evidence.fallback_decision_record_ref is not None:
            fallback_lineages.append(
                {
                    "fallback_decision_record_ref": evidence.fallback_decision_record_ref.value,
                    "fallback_decision_recorded_ref": (
                        evidence.fallback_decision_recorded_ref.value
                        if evidence.fallback_decision_recorded_ref is not None
                        else None
                    ),
                    "verifier_ref": _verification_ref_for_evidence(evidence),
                    "evidence_map_ref": builder_input.final_evidence_table.final_evidence_table_id.value,
                    "closeout_related_ref": builder_input.checker_verdict.checker_verdict_id.value,
                }
            )
    return {"lineages": lineages, "fallback_lineages": fallback_lineages}


def _verification_ref_for_evidence(evidence: VerifiedEvidence | None) -> str:
    if evidence is None or not evidence.verification_run_refs:
        return "verifier.unresolved"
    return evidence.verification_run_refs[0].value


def _evidence_map_payload(builder_input: ProcessAuditBuilderInput) -> dict[str, Any]:
    source_entries_by_evidence: dict[str, list[str]] = {}
    for entry in builder_input.source_inventory.entries:
        for evidence_ref in entry.evidence_refs:
            source_entries_by_evidence.setdefault(evidence_ref.value, []).append(entry.path.value)
    verified_by_ref = {
        evidence.verified_evidence_id.value: evidence for evidence in builder_input.verified_evidence
    }
    rows = []
    for row in builder_input.final_evidence_table.rows:
        evidence_refs = [ref.value for ref in row.verified_evidence_refs]
        verification_refs: list[str] = []
        source_inventory_refs: list[str] = []
        for evidence_ref in evidence_refs:
            evidence = verified_by_ref.get(evidence_ref)
            if evidence is not None:
                verification_refs.extend(ref.value for ref in evidence.verification_run_refs)
            source_inventory_refs.extend(source_entries_by_evidence.get(evidence_ref, ()))
        rows.append(
            {
                "acceptance_ref": row.acceptance_ref.value,
                "criterion_ref": row.acceptance_ref.value,
                "status": row.status.value,
                "verified_evidence_refs": evidence_refs,
                "source_inventory_refs": sorted(set(source_inventory_refs)),
                "verification_run_refs": sorted(set(verification_refs)),
                "checker_verdict_ref": builder_input.checker_verdict.checker_verdict_id.value,
            }
        )
    return {
        "final_evidence_table_ref": builder_input.final_evidence_table.final_evidence_table_id.value,
        "rows": rows,
    }


def _git_version_audit_markdown(builder_input: ProcessAuditBuilderInput) -> str:
    readiness = builder_input.git_audit_readiness
    return _markdown_lines(
        "# Git Version Audit",
        f"Final commit SHA: {readiness.final_commit_sha.value}",
        f"Git clean status: {readiness.git_clean}",
        f"Source inventory hash: {readiness.source_inventory_hash.value}",
        f"Source inventory hash matches: {readiness.source_inventory_hash_matches}",
        f"Final command evidence at final commit: {readiness.final_command_evidence_at_final_commit}",
    )


def _closeout_summary_markdown(builder_input: ProcessAuditBuilderInput) -> str:
    return _markdown_lines(
        "# Closeout Summary",
        f"Package contract: {builder_input.package_contract.package_contract_id.value}",
        f"Source inventory: {builder_input.source_inventory.source_inventory_id.value}",
        f"Final evidence table: {builder_input.final_evidence_table.final_evidence_table_id.value}",
        f"Checker verdict: {builder_input.checker_verdict.checker_verdict_id.value}",
        f"Replay summary hash: {builder_input.replay_readiness.summary_hash.value}",
        "Remaining blockers: none",
    )


def _replay_bundle_report_payload(builder_input: ProcessAuditBuilderInput) -> dict[str, Any]:
    readiness = builder_input.replay_readiness
    return {
        "replay_bundle_ref": builder_input.replay_bundle.replay_bundle_id.value,
        "replay_report_ref": builder_input.replay_bundle.replay_report.replay_report_id.value,
        "projection_kind": builder_input.replay_bundle.replay_report.projection_kind,
        "projection_versions": [version.value for version in readiness.projection_versions],
        "event_range": readiness.event_range.value,
        "summary_hash": readiness.summary_hash.value,
        "hash_chain_verified": readiness.hash_chain_verified,
        "replay_passed": readiness.replay_passed,
    }


def _checked_refs(builder_input: ProcessAuditBuilderInput) -> tuple[str, ...]:
    refs = [
        builder_input.project_ref.value,
        builder_input.package_contract.package_contract_id.value,
        builder_input.acceptance_contract.acceptance_contract_id.value,
        builder_input.source_inventory.source_inventory_id.value,
        builder_input.workspace_evidence_bundle.workspace_evidence_bundle_id.value,
        builder_input.final_evidence_table.final_evidence_table_id.value,
        builder_input.checker_verdict.checker_verdict_id.value,
        builder_input.checker_verdict.source_diff_ref.value,
        builder_input.replay_bundle.replay_bundle_id.value,
        builder_input.replay_bundle.replay_report.replay_report_id.value,
        builder_input.git_audit_readiness.final_commit_sha.value,
        builder_input.git_audit_readiness.source_inventory_hash.value,
        *(event.event_id.value for event in builder_input.events),
        *(attempt.value for attempt in builder_input.provider_attempt_refs),
        *(run.verification_run_id.value for run in builder_input.verification_runs),
        *(evidence.verified_evidence_id.value for evidence in builder_input.verified_evidence),
        *(entry.path.value for entry in builder_input.source_inventory.entries),
        *(
            evidence.fallback_decision_record_ref.value
            for evidence in builder_input.verified_evidence
            if evidence.fallback_decision_record_ref is not None
        ),
    ]
    return tuple(dict.fromkeys(refs))


def _fallback_decision_refs(builder_input: ProcessAuditBuilderInput) -> tuple[str, ...]:
    return tuple(
        evidence.fallback_decision_record_ref.value
        for evidence in builder_input.verified_evidence
        if evidence.fallback_decision_record_ref is not None
    )


def _validate_bundle_instance(bundle: ProcessAuditBundle) -> ProcessAuditBundle:
    if not isinstance(bundle, ProcessAuditBundle):
        raise ProcessAuditError("bundle must be ProcessAuditBundle")
    return ProcessAuditBundle.model_validate(
        bundle.model_dump(mode="python", exclude={"bundle_hash"})
    )


def _validate_bundle_shape(bundle: ProcessAuditBundle) -> None:
    if len(bundle.artifacts) != len(REQUIRED_PROCESS_AUDIT_ARTIFACT_PATHS):
        raise ProcessAuditError("process audit artifacts must cover every required artifact")
    paths = [artifact.path.value for artifact in bundle.artifacts]
    if set(paths) != _REQUIRED_PATH_SET:
        raise ProcessAuditError("process audit artifact paths must match required artifact paths")
    if len(set(paths)) != len(paths):
        raise ProcessAuditError("process audit artifact paths must be unique")
    kinds = [artifact.kind for artifact in bundle.artifacts]
    if len(set(kinds)) != len(kinds):
        raise ProcessAuditError("process audit artifact kinds must be unique")
    if bundle.project_ref != bundle.artifact_manifest.project_ref:
        raise ProcessAuditError("bundle project_ref must match artifact manifest")
    if bundle.project_ref != bundle.hash_manifest.project_ref:
        raise ProcessAuditError("bundle project_ref must match hash manifest")
    if bundle.project_ref != bundle.process_audit_report.project_ref:
        raise ProcessAuditError("bundle project_ref must match process audit report")


def _revalidate_artifact_manifest(bundle: ProcessAuditBundle) -> None:
    artifacts_by_path = {artifact.path.value: artifact for artifact in bundle.artifacts}
    entries_by_path = bundle.artifact_manifest.entries_by_path
    if set(artifacts_by_path) != _REQUIRED_PATH_SET:
        raise ProcessAuditError("artifact manifest requires all process audit artifacts")
    if set(entries_by_path) != set(artifacts_by_path):
        raise ProcessAuditError("artifact manifest paths must match artifacts")
    for path, artifact in artifacts_by_path.items():
        entry = entries_by_path[path]
        if entry.artifact_ref != artifact.artifact_id:
            raise ProcessAuditError("artifact manifest artifact ref mismatch")
        if entry.kind is not artifact.kind:
            raise ProcessAuditError("artifact manifest kind mismatch")
        if entry.format is not artifact.format:
            raise ProcessAuditError("artifact manifest format mismatch")
        if entry.content_ref != artifact.content_ref:
            raise ProcessAuditError("artifact manifest content ref mismatch")
        if entry.sha256 != artifact.sha256:
            raise ProcessAuditError("artifact manifest hash mismatch; hash manifest stale")


def _revalidate_hash_manifest(bundle: ProcessAuditBundle) -> None:
    expected_artifact_hashes = {
        artifact.path.value: artifact.sha256.value for artifact in bundle.artifacts
    }
    actual_artifact_hashes = {
        path: value.value for path, value in bundle.hash_manifest.artifact_hashes.items()
    }
    if actual_artifact_hashes != expected_artifact_hashes:
        raise ProcessAuditError("hash manifest artifact hash mismatch")
    if bundle.hash_manifest.artifact_manifest_hash.value != _hash_model(bundle.artifact_manifest):
        raise ProcessAuditError("hash manifest artifact_manifest_hash mismatch")
    if bundle.hash_manifest.process_audit_report_hash.value != _hash_model(bundle.process_audit_report):
        raise ProcessAuditError("hash manifest process_audit_report_hash mismatch")
    expected_bundle_payload_hash = _hash_bundle_payload(
        process_audit_bundle_id=bundle.process_audit_bundle_id,
        project_ref=bundle.project_ref,
        generated_at=bundle.generated_at,
        artifacts=bundle.artifacts,
        artifact_manifest=bundle.artifact_manifest,
        hash_manifest_without_bundle_hash={
            "hash_manifest_id": bundle.hash_manifest.hash_manifest_id,
            "project_ref": bundle.hash_manifest.project_ref,
            "artifact_hashes": bundle.hash_manifest.artifact_hashes,
            "artifact_manifest_hash": bundle.hash_manifest.artifact_manifest_hash,
            "process_audit_report_hash": bundle.hash_manifest.process_audit_report_hash,
        },
        process_audit_report=bundle.process_audit_report,
        checked_refs=bundle.checked_refs,
    )
    if bundle.hash_manifest.bundle_payload_hash.value != expected_bundle_payload_hash:
        raise ProcessAuditError("hash manifest bundle payload hash mismatch")


def _hash_bundle_payload(
    *,
    process_audit_bundle_id: ProcessAuditBundleRef,
    project_ref: ProjectRef,
    generated_at: datetime,
    artifacts: tuple[ProcessAuditArtifact, ...],
    artifact_manifest: ProcessAuditArtifactManifest,
    hash_manifest_without_bundle_hash: Mapping[str, Any],
    process_audit_report: ProcessAuditReport,
    checked_refs: tuple[str, ...],
) -> str:
    return _hash_jsonable(
        {
            "version": 1,
            "process_audit_bundle_id": process_audit_bundle_id,
            "project_ref": project_ref,
            "generated_at": generated_at.isoformat(),
            "artifacts": [artifact.model_dump(mode="json") for artifact in artifacts],
            "artifact_manifest": artifact_manifest.model_dump(mode="json"),
            "hash_manifest": _canonical_jsonable(hash_manifest_without_bundle_hash),
            "process_audit_report": process_audit_report.model_dump(mode="json"),
            "checked_refs": checked_refs,
        }
    )


def _validate_report_alignment(bundle: ProcessAuditBundle) -> None:
    report = bundle.process_audit_report
    artifact_refs = {artifact.artifact_id.value for artifact in bundle.artifacts}
    report_refs = {
        report.process_audit_ref.value,
        report.timeline_ref.value,
        report.decision_log_ref.value,
        report.agent_context_index_ref.value,
        report.ticket_graph_ref.value,
        report.artifact_lineage_ref.value,
        report.evidence_map_ref.value,
        report.git_audit_ref.value,
        report.closeout_summary_ref.value,
        report.replay_bundle_report_ref.value,
    }
    if artifact_refs != report_refs:
        raise ProcessAuditError("process audit report must index all artifacts")
    if tuple(report.checked_refs) != tuple(bundle.checked_refs):
        raise ProcessAuditError("process audit report checked_refs mismatch")


def _artifact_by_kind(
    bundle: ProcessAuditBundle, kind: ProcessAuditArtifactKind
) -> ProcessAuditArtifact:
    for artifact in bundle.artifacts:
        if artifact.kind is kind:
            return artifact
    raise ProcessAuditError(f"missing process audit artifact: {kind.value}")


def _validate_timeline(bundle: ProcessAuditBundle) -> None:
    artifact = _artifact_by_kind(bundle, ProcessAuditArtifactKind.TIMELINE)
    content = artifact.content
    if not isinstance(content, dict) or not isinstance(content.get("events"), list | tuple):
        raise ProcessAuditError("timeline key events must be present")
    kinds = {str(event.get("kind")) for event in content["events"] if isinstance(event, dict)}
    missing = _REQUIRED_TIMELINE_EVENT_KINDS - kinds
    if missing:
        raise ProcessAuditError(f"timeline missing key event: {sorted(missing)[0]}")


def _validate_decision_log(bundle: ProcessAuditBundle) -> None:
    artifact = _artifact_by_kind(bundle, ProcessAuditArtifactKind.DECISION_LOG)
    content = str(artifact.content)
    if "## CEO / Human Board Decision" not in content or "CEO / human board" not in content:
        raise ProcessAuditError("decision log must include CEO / human board decision")


def _validate_agent_context_index(bundle: ProcessAuditBundle) -> None:
    artifact = _artifact_by_kind(bundle, ProcessAuditArtifactKind.AGENT_CONTEXT_INDEX)
    content = artifact.content
    if not isinstance(content, dict) or not content.get("entries"):
        raise ProcessAuditError("agent context index entries must not be empty")
    for entry in content["entries"]:
        if not isinstance(entry, dict):
            raise ProcessAuditError("agent context index entries must be objects")
        if not entry.get("execution_package_ref"):
            raise ProcessAuditError("agent context index missing execution_package_ref")
        if not entry.get("model_execution_profile"):
            raise ProcessAuditError("agent context index missing model_execution_profile")
        if not entry.get("provider_attempt_refs"):
            raise ProcessAuditError("agent context index missing provider_attempt_refs")


def _validate_artifact_lineage(bundle: ProcessAuditBundle) -> None:
    artifact = _artifact_by_kind(bundle, ProcessAuditArtifactKind.ARTIFACT_LINEAGE)
    content = artifact.content
    if not isinstance(content, dict):
        raise ProcessAuditError("artifact lineage content must be an object")
    lineages = content.get("lineages")
    if not lineages:
        raise ProcessAuditError("artifact lineage must include producer attempt lineage")
    for lineage in lineages:
        if not isinstance(lineage, dict) or not _LINEAGE_REQUIRED_FIELDS <= set(lineage):
            raise ProcessAuditError("artifact lineage missing producer attempt or closeout link")
        if any(not lineage[field] for field in _LINEAGE_REQUIRED_FIELDS):
            raise ProcessAuditError("artifact lineage missing producer attempt or closeout link")
    expected_fallback_refs = set(bundle.process_audit_report.expected_fallback_decision_refs)
    fallback_lineages = content.get("fallback_lineages") or ()
    actual_fallback_refs = {
        lineage.get("fallback_decision_record_ref")
        for lineage in fallback_lineages
        if isinstance(lineage, dict)
    }
    if expected_fallback_refs and actual_fallback_refs != expected_fallback_refs:
        raise ProcessAuditError("fallback lineage missing decision record")
    for lineage in fallback_lineages:
        if not isinstance(lineage, dict) or not _FALLBACK_LINEAGE_REQUIRED_FIELDS <= set(lineage):
            raise ProcessAuditError("fallback lineage missing decision record")
        if any(not lineage[field] for field in _FALLBACK_LINEAGE_REQUIRED_FIELDS):
            raise ProcessAuditError("fallback lineage missing decision record")


def _validate_evidence_map(bundle: ProcessAuditBundle) -> None:
    artifact = _artifact_by_kind(bundle, ProcessAuditArtifactKind.EVIDENCE_MAP)
    content = artifact.content
    if not isinstance(content, dict) or not isinstance(content.get("rows"), list | tuple):
        raise ProcessAuditError("evidence map rows must match final evidence table")
    actual_rows = tuple(content["rows"])
    expected_rows = bundle.process_audit_report.expected_evidence_map_rows
    if _canonical_jsonable(actual_rows) != _canonical_jsonable(expected_rows):
        raise ProcessAuditError("evidence map inconsistent with final evidence table verified_evidence_refs")


def _validate_git_version_audit(bundle: ProcessAuditBundle) -> None:
    artifact = _artifact_by_kind(bundle, ProcessAuditArtifactKind.GIT_VERSION_AUDIT)
    content = str(artifact.content)
    required_labels = (
        "Final commit SHA",
        "Git clean status",
        "Source inventory hash",
    )
    for label in required_labels:
        if label not in content:
            raise ProcessAuditError(f"git audit missing {label.lower()}")


def _validate_replay_bundle_report(bundle: ProcessAuditBundle) -> None:
    artifact = _artifact_by_kind(bundle, ProcessAuditArtifactKind.REPLAY_BUNDLE_REPORT)
    content = artifact.content
    if not isinstance(content, dict):
        raise ProcessAuditError("replay bundle report must be an object")
    report = bundle.process_audit_report
    if content.get("summary_hash") != report.replay_summary_hash:
        raise ProcessAuditError("replay bundle report summary_hash mismatch")
    if tuple(content.get("projection_versions", ())) != report.replay_projection_versions:
        raise ProcessAuditError("replay bundle report projection version mismatch")
    if content.get("replay_passed") is not True or content.get("hash_chain_verified") is not True:
        raise ProcessAuditError("replay bundle report must prove replay readiness")


def _validate_agent_context_index_payload(payload: dict[str, Any]) -> None:
    if not payload.get("entries"):
        raise ProcessAuditError("agent context index entries must not be empty")
    for entry in payload["entries"]:
        if not entry.get("execution_package_ref"):
            raise ProcessAuditError("agent context index missing execution_package_ref")
        if not entry.get("model_execution_profile"):
            raise ProcessAuditError("agent context index missing model_execution_profile")
        if not entry.get("provider_attempt_refs"):
            raise ProcessAuditError("agent context index missing provider_attempt_refs")


__all__ = [
    "REQUIRED_PROCESS_AUDIT_ARTIFACT_PATHS",
    "ProcessAuditArtifact",
    "ProcessAuditArtifactFormat",
    "ProcessAuditArtifactKind",
    "ProcessAuditArtifactManifest",
    "ProcessAuditArtifactManifestEntry",
    "ProcessAuditArtifactRef",
    "ProcessAuditBundle",
    "ProcessAuditBundleRef",
    "ProcessAuditBuilderInput",
    "ProcessAuditCheckedRef",
    "ProcessAuditContentHash",
    "ProcessAuditContentRef",
    "ProcessAuditError",
    "ProcessAuditHashManifest",
    "ProcessAuditManifestRef",
    "ProcessAuditReport",
    "ProcessAuditReportRef",
    "build_process_audit_bundle",
    "process_audit_readiness",
]
