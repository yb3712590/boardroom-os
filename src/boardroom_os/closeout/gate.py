from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    StrictBool,
    ValidationInfo,
    field_serializer,
    field_validator,
    model_validator,
)

from boardroom_os.agents.skills import _normalize_ref_fields
from boardroom_os.checker.verdict import CheckerVerdict, CheckerVerdictStatus
from boardroom_os.contracts.hashes import Sha1Hex, Sha256Hex
from boardroom_os.contracts.package import PackageContract
from boardroom_os.contracts.types import ContractId, NonEmptyTextValue
from boardroom_os.evidence.table import FinalEvidenceStatus, FinalEvidenceTable, FinalEvidenceTableRef
from boardroom_os.evidence.verifier import VerifiedEvidence
from boardroom_os.execution.context_index import ProviderAttemptRef
from boardroom_os.execution.verification_run import VerificationRun, VerificationRunRef, VerificationRunStatus
from boardroom_os.workspace.evidence_export import EvidenceBundleArtifactKind, WorkspaceEvidenceBundle
from boardroom_os.workspace.run_manifest import RunManifest, RunManifestCommandKind, RunManifestRef
from boardroom_os.workspace.source_inventory import SourceInventory


class CloseoutGateError(ValueError):
    pass


class CloseoutGateResultRef(NonEmptyTextValue):
    pass


class ReplaySummaryHash(Sha256Hex):
    pass


class EventRangeRef(NonEmptyTextValue):
    pass


class ProjectionVersionRef(NonEmptyTextValue):
    pass


class GitCommitSha(Sha1Hex):
    pass


class SourceInventoryHash(Sha256Hex):
    pass


class ProcessAuditArtifactPath(NonEmptyTextValue):
    pass


class CloseoutGateBlockerRef(NonEmptyTextValue):
    pass


class CloseoutGateVerdict(StrEnum):
    PASSED = "passed"
    BLOCKED = "blocked"


class CloseoutGateBlockerCode(StrEnum):
    FINAL_EVIDENCE_INCOMPLETE = "final_evidence_incomplete"
    SOURCE_INVENTORY_INCOMPLETE = "source_inventory_incomplete"
    WORKSPACE_EVIDENCE_BUNDLE_NOT_READY = "workspace_evidence_bundle_not_ready"
    CHECKER_NOT_APPROVED = "checker_not_approved"
    PROVIDER_ATTEMPTS_MISSING = "provider_attempts_missing"
    COMMAND_EVIDENCE_NOT_FINAL = "command_evidence_not_final"
    REPLAY_NOT_READY = "replay_not_ready"
    GIT_AUDIT_NOT_READY = "git_audit_not_ready"
    PACKAGE_COMMIT_MISMATCH = "package_commit_mismatch"
    PROCESS_AUDIT_NOT_READY = "process_audit_not_ready"
    REF_MISMATCH = "ref_mismatch"


class ReplayBundleReadiness(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    replay_passed: StrictBool
    summary_hash: ReplaySummaryHash
    event_range: EventRangeRef
    projection_versions: tuple[ProjectionVersionRef, ...]
    hash_chain_verified: StrictBool

    @model_validator(mode="before")
    @classmethod
    def _normalize_refs(cls, data: Any) -> Any:
        if isinstance(data, dict) and "projection_versions" in data and not isinstance(
            data["projection_versions"], list | tuple
        ):
            raise CloseoutGateError("projection_versions must be a tuple or list")
        return _normalize_ref_fields(
            data,
            {
                "summary_hash": ReplaySummaryHash,
                "event_range": EventRangeRef,
            },
            {"projection_versions": ProjectionVersionRef},
        )

    @field_validator("projection_versions")
    @classmethod
    def _reject_empty_projection_versions(
        cls,
        values: tuple[ProjectionVersionRef, ...],
    ) -> tuple[ProjectionVersionRef, ...]:
        if not values:
            raise CloseoutGateError("projection_versions must not be empty")
        if len({value.value for value in values}) != len(values):
            raise CloseoutGateError("projection_versions must be unique")
        return values


class GitAuditReadiness(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    git_clean: StrictBool
    final_commit_sha: GitCommitSha
    source_inventory_hash: SourceInventoryHash
    source_inventory_hash_matches: StrictBool
    final_command_evidence_at_final_commit: StrictBool

    @model_validator(mode="before")
    @classmethod
    def _normalize_refs(cls, data: Any) -> Any:
        return _normalize_ref_fields(
            data,
            {
                "final_commit_sha": GitCommitSha,
                "source_inventory_hash": SourceInventoryHash,
            },
        )


class ProcessAuditReadiness(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    artifact_paths: tuple[ProcessAuditArtifactPath, ...]
    all_artifacts_present: StrictBool
    timeline_key_events_present: StrictBool
    agent_context_index_complete: StrictBool
    artifact_lineage_complete: StrictBool
    evidence_map_consistent_with_final_table: StrictBool

    @model_validator(mode="before")
    @classmethod
    def _normalize_refs(cls, data: Any) -> Any:
        if isinstance(data, dict) and "artifact_paths" in data and not isinstance(
            data["artifact_paths"], list | tuple
        ):
            raise CloseoutGateError("artifact_paths must be a tuple or list")
        return _normalize_ref_fields(
            data,
            {},
            {"artifact_paths": ProcessAuditArtifactPath},
        )

    @field_validator("artifact_paths")
    @classmethod
    def _reject_duplicate_artifact_paths(
        cls,
        values: tuple[ProcessAuditArtifactPath, ...],
    ) -> tuple[ProcessAuditArtifactPath, ...]:
        if len({value.value for value in values}) != len(values):
            raise CloseoutGateError("artifact_paths must be unique")
        return values

    @field_serializer("artifact_paths")
    def _serialize_artifact_paths(
        self,
        values: tuple[ProcessAuditArtifactPath, ...],
    ) -> list[dict[str, str]]:
        return [value.model_dump() for value in values]


class CloseoutCommandEvidenceBinding(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    verification_run_ref: VerificationRunRef
    run_manifest_ref: RunManifestRef
    package_contract_ref: ContractId
    command_id: ContractId
    binding_kind: RunManifestCommandKind

    @model_validator(mode="before")
    @classmethod
    def _normalize_refs(cls, data: Any) -> Any:
        return _normalize_ref_fields(
            data,
            {
                "verification_run_ref": VerificationRunRef,
                "run_manifest_ref": RunManifestRef,
                "package_contract_ref": ContractId,
                "command_id": ContractId,
            },
        )

    @field_serializer("binding_kind")
    def _serialize_binding_kind(self, value: RunManifestCommandKind) -> str:
        return value.value


class CloseoutGateBlocker(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    blocker_id: CloseoutGateBlockerRef | None = None
    code: CloseoutGateBlockerCode
    message: str
    related_ref: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _normalize_refs(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        normalized = _normalize_ref_fields(data, {"blocker_id": CloseoutGateBlockerRef})
        if "blocker_id" not in normalized:
            code = normalized.get("code")
            code_value = getattr(code, "value", str(code))
            related_ref = normalized.get("related_ref") or "unscoped"
            normalized["blocker_id"] = CloseoutGateBlockerRef(
                value=f"closeout-gate-blocker.{code_value}.{related_ref}"
            )
        return normalized

    @field_validator("message")
    @classmethod
    def _reject_empty_message(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise CloseoutGateError("message must not be empty")
        return normalized

    @field_validator("related_ref")
    @classmethod
    def _reject_empty_related_ref(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise CloseoutGateError("related_ref must not be empty")
        return normalized

    @field_serializer("code")
    def _serialize_code(self, value: CloseoutGateBlockerCode) -> str:
        return value.value


class CloseoutGateInput(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    package_contract: PackageContract
    source_inventory: SourceInventory
    run_manifest: RunManifest
    workspace_evidence_bundle: WorkspaceEvidenceBundle
    final_evidence_table: FinalEvidenceTable
    checker_verdict: CheckerVerdict
    verification_runs: tuple[VerificationRun, ...]
    verified_evidence: tuple[VerifiedEvidence, ...]
    provider_attempt_refs: tuple[ProviderAttemptRef, ...]
    final_command_bindings: tuple[CloseoutCommandEvidenceBinding, ...]
    replay_readiness: ReplayBundleReadiness | None
    git_audit_readiness: GitAuditReadiness | None
    process_audit_readiness: ProcessAuditReadiness | None

    @field_validator(
        "package_contract",
        "source_inventory",
        "run_manifest",
        "workspace_evidence_bundle",
        "final_evidence_table",
        "checker_verdict",
        mode="wrap",
    )
    @classmethod
    def _require_typed_model_instances(cls, value: Any, handler: Any, info: ValidationInfo) -> Any:
        expected_types = {
            "package_contract": PackageContract,
            "source_inventory": SourceInventory,
            "run_manifest": RunManifest,
            "workspace_evidence_bundle": WorkspaceEvidenceBundle,
            "final_evidence_table": FinalEvidenceTable,
            "checker_verdict": CheckerVerdict,
        }
        expected_type = expected_types[info.field_name]
        if not isinstance(value, expected_type):
            raise CloseoutGateError(
                f"{info.field_name} must be a {expected_type.__name__} instance"
            )
        return value

    @field_validator("verification_runs", mode="before")
    @classmethod
    def _require_verification_runs_tuple(cls, value: Any) -> Any:
        return _require_instance_tuple(value, VerificationRun, "verification_runs")

    @field_validator("verified_evidence", mode="before")
    @classmethod
    def _require_verified_evidence_tuple(cls, value: Any) -> Any:
        return _require_instance_tuple(value, VerifiedEvidence, "verified_evidence")

    @field_validator("provider_attempt_refs", mode="before")
    @classmethod
    def _normalize_provider_attempt_refs(cls, value: Any) -> Any:
        if not isinstance(value, list | tuple):
            raise CloseoutGateError("provider_attempt_refs must be a tuple or list")
        return tuple(
            item if isinstance(item, ProviderAttemptRef) else ProviderAttemptRef(value=item)
            for item in value
        )

    @field_validator("final_command_bindings", mode="before")
    @classmethod
    def _require_command_bindings_tuple(cls, value: Any) -> Any:
        return _require_instance_tuple(
            value,
            CloseoutCommandEvidenceBinding,
            "final_command_bindings",
        )


class CloseoutGateResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    version: Literal[1] = 1
    closeout_gate_result_id: CloseoutGateResultRef
    verdict: CloseoutGateVerdict
    blockers: tuple[CloseoutGateBlocker, ...]
    checked_refs: tuple[str, ...]

    @field_validator("blockers")
    @classmethod
    def _validate_blockers(
        cls,
        values: tuple[CloseoutGateBlocker, ...],
    ) -> tuple[CloseoutGateBlocker, ...]:
        ids = [value.blocker_id.value for value in values if value.blocker_id is not None]
        if len(set(ids)) != len(ids):
            raise CloseoutGateError("blocker ids must be unique")
        return values

    @field_validator("checked_refs")
    @classmethod
    def _validate_checked_refs(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(value.strip() for value in values)
        if any(not value for value in normalized):
            raise CloseoutGateError("checked_refs must not contain empty values")
        if len(set(normalized)) != len(normalized):
            raise CloseoutGateError("checked_refs must be unique")
        return normalized

    @model_validator(mode="after")
    def _validate_verdict_shape(self) -> Self:
        if self.verdict is CloseoutGateVerdict.PASSED and self.blockers:
            raise CloseoutGateError("passed closeout gate result must not include blockers")
        if self.verdict is CloseoutGateVerdict.BLOCKED and not self.blockers:
            raise CloseoutGateError("blocked closeout gate result requires blockers")
        return self

    @field_serializer("verdict")
    def _serialize_verdict(self, value: CloseoutGateVerdict) -> str:
        return value.value


_REQUIRED_PROCESS_AUDIT_ARTIFACT_PATHS = {
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
}


class CloseoutGate:
    def evaluate(self, gate_input: CloseoutGateInput) -> CloseoutGateResult:
        if not isinstance(gate_input, CloseoutGateInput):
            raise CloseoutGateError("gate_input must be CloseoutGateInput")

        blockers: list[CloseoutGateBlocker] = []
        blockers.extend(_reference_blockers(gate_input))
        blockers.extend(_final_evidence_blockers(gate_input))
        blockers.extend(_source_inventory_blockers(gate_input))
        blockers.extend(_workspace_evidence_bundle_blockers(gate_input))
        blockers.extend(_checker_blockers(gate_input))
        blockers.extend(_provider_attempt_blockers(gate_input))
        blockers.extend(_command_evidence_blockers(gate_input))
        blockers.extend(_replay_readiness_blockers(gate_input))
        blockers.extend(_git_audit_blockers(gate_input))
        blockers.extend(_process_audit_blockers(gate_input))

        checked_refs = _checked_refs(gate_input)
        verdict = CloseoutGateVerdict.BLOCKED if blockers else CloseoutGateVerdict.PASSED
        return CloseoutGateResult(
            closeout_gate_result_id=CloseoutGateResultRef(
                value=(
                    "closeout-gate-result."
                    f"{gate_input.source_inventory.source_inventory_id.value}."
                    f"{gate_input.final_evidence_table.final_evidence_table_id.value}"
                )
            ),
            verdict=verdict,
            blockers=tuple(_dedupe_blockers(blockers)),
            checked_refs=checked_refs,
        )


def _require_instance_tuple(value: Any, expected_type: type[Any], field_name: str) -> tuple[Any, ...]:
    if not isinstance(value, list | tuple):
        raise CloseoutGateError(f"{field_name} must be a tuple or list")
    for item in value:
        if not isinstance(item, expected_type):
            raise CloseoutGateError(f"{field_name} must contain {expected_type.__name__} values")
    return tuple(value)


def _blocker(
    code: CloseoutGateBlockerCode,
    message: str,
    related_ref: str | None = None,
) -> CloseoutGateBlocker:
    return CloseoutGateBlocker(code=code, message=message, related_ref=related_ref)


def _dedupe_blockers(blockers: list[CloseoutGateBlocker]) -> list[CloseoutGateBlocker]:
    seen: set[tuple[str, str | None]] = set()
    deduped: list[CloseoutGateBlocker] = []
    for blocker in blockers:
        key = (blocker.code.value, blocker.related_ref)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(blocker)
    return deduped


def _reference_blockers(gate_input: CloseoutGateInput) -> list[CloseoutGateBlocker]:
    blockers: list[CloseoutGateBlocker] = []
    package_contract_ref = gate_input.package_contract.package_contract_id
    _append_ref_mismatch(
        blockers,
        gate_input.source_inventory.package_contract_ref,
        package_contract_ref,
        "source_inventory.package_contract_ref",
    )
    _append_ref_mismatch(
        blockers,
        gate_input.run_manifest.package_contract_ref,
        package_contract_ref,
        "run_manifest.package_contract_ref",
    )
    _append_ref_mismatch(
        blockers,
        gate_input.workspace_evidence_bundle.package_contract_ref,
        package_contract_ref,
        "workspace_evidence_bundle.package_contract_ref",
    )
    _append_ref_mismatch(
        blockers,
        gate_input.workspace_evidence_bundle.source_inventory_ref,
        gate_input.source_inventory.source_inventory_id,
        "workspace_evidence_bundle.source_inventory_ref",
    )
    _append_ref_mismatch(
        blockers,
        gate_input.workspace_evidence_bundle.run_manifest_ref,
        gate_input.run_manifest.run_manifest_id,
        "workspace_evidence_bundle.run_manifest_ref",
    )
    _append_ref_mismatch(
        blockers,
        gate_input.workspace_evidence_bundle.final_evidence_table_ref,
        gate_input.final_evidence_table.final_evidence_table_id,
        "workspace_evidence_bundle.final_evidence_table_ref",
    )
    _append_ref_mismatch(
        blockers,
        gate_input.checker_verdict.acceptance_contract_ref,
        gate_input.final_evidence_table.acceptance_contract_ref,
        "checker_verdict.acceptance_contract_ref",
    )
    _append_ref_mismatch(
        blockers,
        gate_input.checker_verdict.final_evidence_table_ref,
        gate_input.final_evidence_table.final_evidence_table_id,
        "checker_verdict.final_evidence_table_ref",
    )
    return blockers


def _append_ref_mismatch(
    blockers: list[CloseoutGateBlocker],
    actual: Any,
    expected: Any,
    related_ref: str,
) -> None:
    if actual != expected:
        blockers.append(
            _blocker(
                CloseoutGateBlockerCode.REF_MISMATCH,
                f"{related_ref} does not match expected closeout input ref",
                related_ref,
            )
        )


def _final_evidence_blockers(gate_input: CloseoutGateInput) -> list[CloseoutGateBlocker]:
    table = gate_input.final_evidence_table
    rows = getattr(table, "rows", ())
    if not rows or table.complete is not True:
        return [
            _blocker(
                CloseoutGateBlockerCode.FINAL_EVIDENCE_INCOMPLETE,
                "final evidence table must be complete and include acceptance rows",
                table.final_evidence_table_id.value,
            )
        ]
    for row in rows:
        if row.status is not FinalEvidenceStatus.SATISFIED or row.blockers or not row.verified_evidence_refs:
            return [
                _blocker(
                    CloseoutGateBlockerCode.FINAL_EVIDENCE_INCOMPLETE,
                    "final evidence table rows must all be satisfied by verified evidence",
                    row.acceptance_ref.value,
                )
            ]

    table_refs = _final_table_verified_evidence_ref_values(table)
    evidence_refs = {evidence.verified_evidence_id.value for evidence in gate_input.verified_evidence}
    if not table_refs or table_refs != evidence_refs:
        return [
            _blocker(
                CloseoutGateBlockerCode.FINAL_EVIDENCE_INCOMPLETE,
                "verified_evidence must exactly match final evidence table refs",
                table.final_evidence_table_id.value,
            )
        ]
    return []


def _final_table_verified_evidence_ref_values(table: FinalEvidenceTable) -> set[str]:
    return {
        evidence_ref.value
        for row in table.rows
        for evidence_ref in row.verified_evidence_refs
    }


def _source_inventory_blockers(gate_input: CloseoutGateInput) -> list[CloseoutGateBlocker]:
    inventory = gate_input.source_inventory
    if not inventory.entries:
        return [
            _blocker(
                CloseoutGateBlockerCode.SOURCE_INVENTORY_INCOMPLETE,
                "source inventory must include implementation lineage entries",
                inventory.source_inventory_id.value,
            )
        ]

    provider_attempt_refs = {ref.value for ref in gate_input.provider_attempt_refs}
    verified_evidence_refs = {evidence.verified_evidence_id.value for evidence in gate_input.verified_evidence}
    final_table_refs = _final_table_verified_evidence_ref_values(gate_input.final_evidence_table)
    inventory_evidence_refs: set[str] = set()
    for entry in inventory.entries:
        inventory_evidence_refs.update(ref.value for ref in entry.evidence_refs)
        if (
            not entry.acceptance_refs
            or not entry.evidence_refs
            or entry.producer_attempt_ref.value not in provider_attempt_refs
            or any(ref.value not in verified_evidence_refs for ref in entry.evidence_refs)
        ):
            return [
                _blocker(
                    CloseoutGateBlockerCode.SOURCE_INVENTORY_INCOMPLETE,
                    "source inventory entries must bind lineage to provider attempts and verified evidence",
                    entry.path.value,
                )
            ]

    if not final_table_refs.issubset(inventory_evidence_refs):
        return [
            _blocker(
                CloseoutGateBlockerCode.SOURCE_INVENTORY_INCOMPLETE,
                "source inventory must cover final evidence refs",
                inventory.source_inventory_id.value,
            )
        ]
    return []


def _workspace_evidence_bundle_blockers(gate_input: CloseoutGateInput) -> list[CloseoutGateBlocker]:
    bundle = gate_input.workspace_evidence_bundle
    if bundle.closeout_ready is not True:
        return [
            _blocker(
                CloseoutGateBlockerCode.WORKSPACE_EVIDENCE_BUNDLE_NOT_READY,
                "workspace evidence bundle must be closeout ready",
                bundle.workspace_evidence_bundle_id.value,
            )
        ]
    artifact_kinds = {artifact.artifact_kind for artifact in bundle.artifacts}
    if artifact_kinds != set(EvidenceBundleArtifactKind):
        return [
            _blocker(
                CloseoutGateBlockerCode.WORKSPACE_EVIDENCE_BUNDLE_NOT_READY,
                "workspace evidence bundle must include all required artifact kinds",
                bundle.workspace_evidence_bundle_id.value,
            )
        ]
    if {ref.value for ref in bundle.verified_evidence_refs} != {
        evidence.verified_evidence_id.value for evidence in gate_input.verified_evidence
    }:
        return [
            _blocker(
                CloseoutGateBlockerCode.WORKSPACE_EVIDENCE_BUNDLE_NOT_READY,
                "workspace evidence bundle verified evidence refs must match gate input",
                bundle.workspace_evidence_bundle_id.value,
            )
        ]
    if {ref.value for ref in bundle.verification_run_refs} != {
        run.verification_run_id.value for run in gate_input.verification_runs
    }:
        return [
            _blocker(
                CloseoutGateBlockerCode.WORKSPACE_EVIDENCE_BUNDLE_NOT_READY,
                "workspace evidence bundle verification run refs must match gate input",
                bundle.workspace_evidence_bundle_id.value,
            )
        ]
    return []


def _checker_blockers(gate_input: CloseoutGateInput) -> list[CloseoutGateBlocker]:
    verdict = gate_input.checker_verdict
    if verdict.status not in {
        CheckerVerdictStatus.APPROVED,
        CheckerVerdictStatus.APPROVED_WITH_NON_BLOCKING_NOTES,
    } or verdict.blockers:
        return [
            _blocker(
                CloseoutGateBlockerCode.CHECKER_NOT_APPROVED,
                "checker verdict must be approved without blocking issues",
                verdict.checker_verdict_id.value,
            )
        ]
    return []


def _provider_attempt_blockers(gate_input: CloseoutGateInput) -> list[CloseoutGateBlocker]:
    provider_attempt_refs = [ref.value for ref in gate_input.provider_attempt_refs]
    provider_attempt_ref_set = set(provider_attempt_refs)
    if not provider_attempt_refs or len(provider_attempt_ref_set) != len(provider_attempt_refs):
        return [
            _blocker(
                CloseoutGateBlockerCode.PROVIDER_ATTEMPTS_MISSING,
                "provider attempt refs must be present and unique",
                gate_input.package_contract.package_contract_id.value,
            )
        ]
    for evidence in gate_input.verified_evidence:
        if evidence.producer_attempt_ref.value not in provider_attempt_ref_set:
            return [
                _blocker(
                    CloseoutGateBlockerCode.PROVIDER_ATTEMPTS_MISSING,
                    "verified evidence producer attempts must be present in provider_attempt_refs",
                    evidence.verified_evidence_id.value,
                )
            ]
        for artifact in evidence.verified_artifacts:
            if artifact.producer_attempt_ref.value not in provider_attempt_ref_set:
                return [
                    _blocker(
                        CloseoutGateBlockerCode.PROVIDER_ATTEMPTS_MISSING,
                        "verified artifact producer attempts must be present in provider_attempt_refs",
                        artifact.artifact_ref.value,
                    )
                ]
    return []


def _command_evidence_blockers(gate_input: CloseoutGateInput) -> list[CloseoutGateBlocker]:
    runs = gate_input.verification_runs
    run_refs = [run.verification_run_id.value for run in runs]
    if not runs or len(set(run_refs)) != len(run_refs):
        return [
            _blocker(
                CloseoutGateBlockerCode.COMMAND_EVIDENCE_NOT_FINAL,
                "verification runs must be present and unique",
                gate_input.run_manifest.run_manifest_id.value,
            )
        ]
    for run in runs:
        if run.status is not VerificationRunStatus.PASSED or run.exit_code != 0:
            return [
                _blocker(
                    CloseoutGateBlockerCode.COMMAND_EVIDENCE_NOT_FINAL,
                    "final verification runs must pass",
                    run.verification_run_id.value,
                )
            ]

    bindings = gate_input.final_command_bindings
    binding_refs = [binding.verification_run_ref.value for binding in bindings]
    if not bindings or len(set(binding_refs)) != len(binding_refs) or set(binding_refs) != set(run_refs):
        return [
            _blocker(
                CloseoutGateBlockerCode.COMMAND_EVIDENCE_NOT_FINAL,
                "every final verification run must have exactly one run manifest binding",
                gate_input.run_manifest.run_manifest_id.value,
            )
        ]

    run_by_ref = {run.verification_run_id.value: run for run in runs}
    commands_by_id = {command.command_id.value: command for command in gate_input.run_manifest.commands}
    for binding in bindings:
        if (
            binding.run_manifest_ref != gate_input.run_manifest.run_manifest_id
            or binding.package_contract_ref != gate_input.package_contract.package_contract_id
        ):
            return [
                _blocker(
                    CloseoutGateBlockerCode.COMMAND_EVIDENCE_NOT_FINAL,
                    "run manifest binding refs must match closeout input",
                    binding.verification_run_ref.value,
                )
            ]
        command = commands_by_id.get(binding.command_id.value)
        run = run_by_ref[binding.verification_run_ref.value]
        if command is None or command.kind is not binding.binding_kind:
            return [
                _blocker(
                    CloseoutGateBlockerCode.COMMAND_EVIDENCE_NOT_FINAL,
                    "run manifest binding must reference a declared command",
                    binding.command_id.value,
                )
            ]
        if run.command_id != command.command_id or run.command != command.command or run.cwd != command.cwd:
            return [
                _blocker(
                    CloseoutGateBlockerCode.COMMAND_EVIDENCE_NOT_FINAL,
                    "verification run command must match run manifest binding",
                    run.verification_run_id.value,
                )
            ]
    return []


def _replay_readiness_blockers(gate_input: CloseoutGateInput) -> list[CloseoutGateBlocker]:
    readiness = gate_input.replay_readiness
    if (
        readiness is None
        or readiness.replay_passed is not True
        or readiness.hash_chain_verified is not True
        or not readiness.summary_hash.value
        or not readiness.event_range.value
        or not readiness.projection_versions
    ):
        return [
            _blocker(
                CloseoutGateBlockerCode.REPLAY_NOT_READY,
                "replay bundle readiness must prove replay success and hash chain verification",
                gate_input.package_contract.package_contract_id.value,
            )
        ]
    return []


def _git_audit_blockers(gate_input: CloseoutGateInput) -> list[CloseoutGateBlocker]:
    readiness = gate_input.git_audit_readiness
    if readiness is None:
        return [
            _blocker(
                CloseoutGateBlockerCode.GIT_AUDIT_NOT_READY,
                "git audit readiness is required",
                gate_input.source_inventory.source_inventory_id.value,
            )
        ]
    if readiness.final_command_evidence_at_final_commit is not True:
        return [
            _blocker(
                CloseoutGateBlockerCode.COMMAND_EVIDENCE_NOT_FINAL,
                "final command evidence must be captured at final commit",
                readiness.final_commit_sha.value,
            )
        ]
    if (
        readiness.git_clean is not True
        or readiness.source_inventory_hash_matches is not True
        or not readiness.final_commit_sha.value
        or not readiness.source_inventory_hash.value
    ):
        return [
            _blocker(
                CloseoutGateBlockerCode.GIT_AUDIT_NOT_READY,
                "git audit readiness must prove clean final version and source inventory hash",
                gate_input.source_inventory.source_inventory_id.value,
            )
        ]
    final_commit_sha = readiness.final_commit_sha.value
    package_commit_ref = gate_input.source_inventory.package_commit_ref.value
    if package_commit_ref not in {final_commit_sha, f"package-commit.{final_commit_sha}"}:
        return [
            _blocker(
                CloseoutGateBlockerCode.PACKAGE_COMMIT_MISMATCH,
                "source inventory package_commit_ref must match git audit final commit sha",
                gate_input.source_inventory.package_commit_ref.value,
            )
        ]
    return []


def _process_audit_blockers(gate_input: CloseoutGateInput) -> list[CloseoutGateBlocker]:
    readiness = gate_input.process_audit_readiness
    if readiness is None:
        return [
            _blocker(
                CloseoutGateBlockerCode.PROCESS_AUDIT_NOT_READY,
                "process audit readiness is required",
                gate_input.package_contract.package_contract_id.value,
            )
        ]
    artifact_paths = {path.value for path in readiness.artifact_paths}
    if (
        artifact_paths != _REQUIRED_PROCESS_AUDIT_ARTIFACT_PATHS
        or readiness.all_artifacts_present is not True
        or readiness.timeline_key_events_present is not True
        or readiness.agent_context_index_complete is not True
        or readiness.artifact_lineage_complete is not True
        or readiness.evidence_map_consistent_with_final_table is not True
    ):
        return [
            _blocker(
                CloseoutGateBlockerCode.PROCESS_AUDIT_NOT_READY,
                "process audit readiness must prove all closeout audit artifacts",
                gate_input.package_contract.package_contract_id.value,
            )
        ]
    return []


def _checked_refs(gate_input: CloseoutGateInput) -> tuple[str, ...]:
    refs = [
        gate_input.package_contract.package_contract_id.value,
        gate_input.source_inventory.source_inventory_id.value,
        gate_input.run_manifest.run_manifest_id.value,
        gate_input.workspace_evidence_bundle.workspace_evidence_bundle_id.value,
        gate_input.final_evidence_table.final_evidence_table_id.value,
        gate_input.checker_verdict.checker_verdict_id.value,
    ]
    refs.extend(ref.value for ref in gate_input.provider_attempt_refs)
    refs.extend(run.verification_run_id.value for run in gate_input.verification_runs)
    refs.extend(evidence.verified_evidence_id.value for evidence in gate_input.verified_evidence)
    refs.extend(
        evidence.fallback_decision_record_ref.value
        for evidence in gate_input.verified_evidence
        if evidence.fallback_decision_record_ref is not None
    )
    if gate_input.replay_readiness is not None:
        refs.append(gate_input.replay_readiness.summary_hash.value)
        refs.append(gate_input.replay_readiness.event_range.value)
        refs.extend(ref.value for ref in gate_input.replay_readiness.projection_versions)
    if gate_input.git_audit_readiness is not None:
        refs.append(gate_input.git_audit_readiness.final_commit_sha.value)
        refs.append(gate_input.git_audit_readiness.source_inventory_hash.value)
    if gate_input.process_audit_readiness is not None:
        refs.extend(path.value for path in gate_input.process_audit_readiness.artifact_paths)
    return tuple(dict.fromkeys(refs))


__all__ = [
    "CloseoutCommandEvidenceBinding",
    "CloseoutGate",
    "CloseoutGateBlocker",
    "CloseoutGateBlockerCode",
    "CloseoutGateBlockerRef",
    "CloseoutGateError",
    "CloseoutGateInput",
    "CloseoutGateResult",
    "CloseoutGateResultRef",
    "CloseoutGateVerdict",
    "EventRangeRef",
    "GitAuditReadiness",
    "GitCommitSha",
    "ProcessAuditArtifactPath",
    "ProcessAuditReadiness",
    "ProjectionVersionRef",
    "ReplayBundleReadiness",
    "ReplaySummaryHash",
    "SourceInventoryHash",
]
