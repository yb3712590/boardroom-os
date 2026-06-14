from __future__ import annotations

from datetime import datetime
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from boardroom_os.checker.checker import CheckerService, CheckerServiceInput
from boardroom_os.checker.verdict import CheckerVerdict, CheckerVerdictStatus, SourceDiffRef
from boardroom_os.closeout.gate import CloseoutGate, CloseoutGateInput, CloseoutGateResult
from boardroom_os.contracts.acceptance import AcceptanceContract
from boardroom_os.contracts.package import PackageContract
from boardroom_os.contracts.types import AcceptanceRef
from boardroom_os.evidence.claim import EvidenceClaimSourceKind
from boardroom_os.evidence.table import (
    EvidenceNamespaceRef,
    FinalEvidenceBlocker,
    FinalEvidenceTable,
    FinalEvidenceTableBuilder,
    FinalEvidenceTableInput,
)
from boardroom_os.evidence.verifier import EvidenceVerificationResult, VerifiedEvidence
from boardroom_os.execution.work_product import WorkProduct
from boardroom_os.rework.model import (
    BlockerRef,
    ReworkAttempt,
    ReworkAttemptId,
    ReworkCycleId,
    ReworkOutcome,
    ReworkOutcomeId,
    ReworkOutcomeStatus,
    RunId,
)
from boardroom_os.workspace.assembler import PackageAssembly
from boardroom_os.workspace.run_manifest import RunManifest, RunManifestCommandKind
from boardroom_os.workspace.source_inventory import (
    PackageCommitRef,
    SourceFileRecord,
    SourceInventory,
    SourceLineageRecord,
    build_source_inventory,
)


class ReworkEvidenceError(ValueError):
    pass


class ReworkEvidenceNamespace(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: RunId
    cycle_id: ReworkCycleId | str
    rework_attempt_id: ReworkAttemptId
    graph_version: int = Field(gt=0)
    config_hash_refs: tuple[str, ...]

    @field_validator("config_hash_refs")
    @classmethod
    def _reject_empty_or_duplicate_config_hash_refs(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(value.strip() for value in values)
        if not normalized or any(not value for value in normalized):
            raise ReworkEvidenceError("config_hash_refs must not be empty")
        if len(set(normalized)) != len(normalized):
            raise ReworkEvidenceError("config_hash_refs must be unique")
        return normalized


def rework_evidence_namespace_ref(namespace: ReworkEvidenceNamespace) -> EvidenceNamespaceRef:
    cycle_id = namespace.cycle_id.value if hasattr(namespace.cycle_id, "value") else str(namespace.cycle_id)
    return EvidenceNamespaceRef(
        value=(
            "rework-evidence."
            f"{namespace.run_id.value}."
            f"{cycle_id}."
            f"{namespace.rework_attempt_id.value}."
            f"g{namespace.graph_version}"
        )
    )


class ReworkEnvironmentUsage(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    source_ref: str
    env_names: tuple[str, ...]

    @field_validator("source_ref")
    @classmethod
    def _reject_empty_source_ref(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ReworkEvidenceError("source_ref must not be empty")
        return normalized

    @field_validator("env_names")
    @classmethod
    def _reject_empty_or_duplicate_env_names(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(value.strip() for value in values)
        if not normalized or any(not value for value in normalized):
            raise ReworkEvidenceError("env_names must not be empty")
        if len(set(normalized)) != len(normalized):
            raise ReworkEvidenceError("env_names must be unique")
        return normalized


class ReworkCloseoutRecheckContext(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    closeout_input: CloseoutGateInput


class ReworkEvidenceRecheckInput(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    attempt: ReworkAttempt
    namespace: ReworkEvidenceNamespace
    active_acceptance_contract: AcceptanceContract
    active_package_contract: PackageContract
    package_assembly: PackageAssembly
    package_commit_ref: PackageCommitRef
    source_files: tuple[SourceFileRecord, ...]
    source_lineage_records: tuple[SourceLineageRecord, ...]
    evidence_verification_results: tuple[EvidenceVerificationResult, ...]
    failed_final_evidence_blockers: tuple[FinalEvidenceBlocker, ...] = ()
    target_blocker_refs: tuple[BlockerRef, ...]
    work_product: WorkProduct
    source_diff_ref: SourceDiffRef
    run_manifest: RunManifest
    environment_usage: tuple[ReworkEnvironmentUsage, ...] = ()
    checked_at: datetime
    closeout_context: ReworkCloseoutRecheckContext | None = None

    @field_validator("active_acceptance_contract", mode="wrap")
    @classmethod
    def _require_acceptance_contract_instance(cls, value, handler) -> AcceptanceContract:
        if not isinstance(value, AcceptanceContract):
            raise ReworkEvidenceError("active_acceptance_contract must be an AcceptanceContract")
        return value

    @field_validator("active_package_contract", mode="wrap")
    @classmethod
    def _require_package_contract_instance(cls, value, handler) -> PackageContract:
        if not isinstance(value, PackageContract):
            raise ReworkEvidenceError("active_package_contract must be a PackageContract")
        return value

    @model_validator(mode="after")
    def _validate_attempt_namespace(self) -> Self:
        if self.namespace.rework_attempt_id != self.attempt.rework_attempt_id:
            raise ReworkEvidenceError("namespace rework_attempt_id must match attempt")
        if not self.target_blocker_refs:
            raise ReworkEvidenceError("target_blocker_refs must not be empty")
        if self.run_manifest.run_manifest_id.value != self.attempt.run_manifest_ref:
            raise ReworkEvidenceError("run_manifest must match attempt run_manifest_ref")
        return self


class ReworkEvidenceRecheckResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    namespace: ReworkEvidenceNamespace
    attempt_ref: ReworkAttemptId
    source_inventory: SourceInventory
    final_evidence_table: FinalEvidenceTable
    checker_verdict: CheckerVerdict
    closeout_gate_result: CloseoutGateResult | None = None
    status: ReworkOutcomeStatus
    remaining_blocker_refs: tuple[BlockerRef, ...] = ()
    accepted_blocker_refs: tuple[BlockerRef, ...] = ()
    checked_refs: tuple[str, ...]
    rejected_stale_refs: tuple[str, ...] = ()
    created_at: datetime

    def to_rework_outcome(self) -> ReworkOutcome:
        return ReworkOutcome(
            rework_outcome_id=ReworkOutcomeId(value=f"rework-outcome.{self.attempt_ref.value}"),
            rework_attempt_ref=self.attempt_ref,
            final_evidence_table_ref=self.final_evidence_table.final_evidence_table_id.value,
            source_inventory_ref=self.source_inventory.source_inventory_id.value,
            checker_verdict_ref=self.checker_verdict.checker_verdict_id.value,
            closeout_gate_ref=(
                self.closeout_gate_result.closeout_gate_result_id.value
                if self.closeout_gate_result is not None
                else None
            ),
            status=self.status,
            remaining_blocker_refs=self.remaining_blocker_refs,
            accepted_blocker_refs=self.accepted_blocker_refs,
            created_at=self.created_at,
        )


def validate_rework_attempt_fact_refs(attempt: ReworkAttempt) -> ReworkAttempt:
    if not attempt.provider_attempt_refs:
        raise ReworkEvidenceError("rework attempt requires provider_attempt_refs")
    if not attempt.command_evidence_refs:
        raise ReworkEvidenceError("rework attempt requires command_evidence_refs")
    if not attempt.source_lineage_refs:
        raise ReworkEvidenceError("rework attempt requires source_lineage_refs")
    if not attempt.workspace_mutation_refs:
        raise ReworkEvidenceError("rework attempt requires workspace_mutation_refs")
    return attempt


def _verified_evidence(results: tuple[EvidenceVerificationResult, ...]) -> tuple[VerifiedEvidence, ...]:
    return tuple(result.verified_evidence for result in results if result.verified_evidence is not None)


def validate_rework_evidence_freshness(recheck_input: ReworkEvidenceRecheckInput) -> None:
    validate_rework_attempt_fact_refs(recheck_input.attempt)
    namespace_ref = rework_evidence_namespace_ref(recheck_input.namespace).value
    provider_attempt_refs = {ref.value for ref in recheck_input.attempt.provider_attempt_refs}
    current_evidence = _verified_evidence(recheck_input.evidence_verification_results)
    if not current_evidence:
        raise ReworkEvidenceError("rework evidence verification requires current verified evidence")
    if not recheck_input.source_lineage_records:
        raise ReworkEvidenceError("source lineage records are required")

    for evidence in current_evidence:
        if evidence.producer_attempt_ref.value not in provider_attempt_refs:
            raise ReworkEvidenceError("verified evidence producer_attempt_ref is not from current attempt")
        if namespace_ref not in evidence.verified_evidence_id.value:
            raise ReworkEvidenceError("verified evidence ref must include rework namespace")
        if evidence.verified_at > recheck_input.checked_at:
            raise ReworkEvidenceError("checker verdict must be after current verified evidence")

    current_evidence_refs = {evidence.verified_evidence_id.value for evidence in current_evidence}
    for lineage in recheck_input.source_lineage_records:
        if lineage.producer_attempt_ref.value not in provider_attempt_refs:
            raise ReworkEvidenceError("source lineage producer_attempt_ref is not from current attempt")
        lineage_evidence_refs = {ref.value for ref in lineage.evidence_refs}
        if not lineage_evidence_refs.issubset(current_evidence_refs):
            raise ReworkEvidenceError("source lineage evidence_refs are not from current attempt")


def validate_rework_final_evidence_table_freshness(
    table: FinalEvidenceTable,
    *,
    namespace: ReworkEvidenceNamespace,
    verified_evidence: tuple[VerifiedEvidence, ...],
) -> FinalEvidenceTable:
    namespace_ref = rework_evidence_namespace_ref(namespace)
    if table.evidence_namespace_ref != namespace_ref:
        raise ReworkEvidenceError("final evidence table namespace mismatch")
    current_evidence_refs = {evidence.verified_evidence_id.value for evidence in verified_evidence}
    table_evidence_refs = {
        ref.value
        for row in table.rows
        for ref in row.verified_evidence_refs
    }
    if not table_evidence_refs.issubset(current_evidence_refs):
        raise ReworkEvidenceError("final evidence table contains stale verified evidence refs")
    return table


def validate_rework_run_manifest_readiness(
    run_manifest: RunManifest,
    *,
    active_acceptance_refs: tuple[AcceptanceRef, ...],
    environment_usage: tuple[ReworkEnvironmentUsage, ...],
) -> None:
    run_commands = tuple(
        command for command in run_manifest.commands if command.kind is RunManifestCommandKind.RUN
    )
    if run_commands and not run_manifest.service_contracts:
        raise ReworkEvidenceError("run commands require explicit service contracts")

    active_acceptance_ref_values = {ref.value for ref in active_acceptance_refs}
    for probe in run_manifest.behavioral_probes or ():
        for acceptance_ref in probe.acceptance_refs:
            if acceptance_ref.value not in active_acceptance_ref_values:
                raise ReworkEvidenceError("behavioral probe acceptance_ref is not active")

    declared_env_names = {
        binding.name
        for service in run_manifest.service_contracts or ()
        for binding in service.env_bindings
    }
    observed_env_names = {env_name for usage in environment_usage for env_name in usage.env_names}
    undeclared = observed_env_names - declared_env_names
    if undeclared:
        names = ", ".join(sorted(undeclared))
        raise ReworkEvidenceError(f"undeclared environment usage: {names}")


def build_rework_source_inventory(recheck_input: ReworkEvidenceRecheckInput) -> SourceInventory:
    validate_rework_evidence_freshness(recheck_input)
    return build_source_inventory(
        package_assembly=recheck_input.package_assembly,
        package_contract=recheck_input.active_package_contract,
        package_commit_ref=recheck_input.package_commit_ref,
        source_files=recheck_input.source_files,
        lineage_records=recheck_input.source_lineage_records,
    )


def _behavioral_probe_acceptance_refs(run_manifest: RunManifest) -> set[str]:
    return {
        acceptance_ref.value
        for probe in run_manifest.behavioral_probes or ()
        for acceptance_ref in probe.acceptance_refs
    }


def _verified_live_acceptance_refs(verified_evidence: tuple[VerifiedEvidence, ...]) -> set[str]:
    return {
        acceptance_ref.value
        for evidence in verified_evidence
        if evidence.source_kind is EvidenceClaimSourceKind.LIVE_BLACKBOX
        for acceptance_ref in evidence.acceptance_refs
    }


def _failed_blocker_acceptance_refs(blockers: tuple[FinalEvidenceBlocker, ...]) -> set[str]:
    return {blocker.acceptance_ref.value for blocker in blockers}


def _validate_behavioral_probe_coverage(recheck_input: ReworkEvidenceRecheckInput) -> None:
    verified = _verified_evidence(recheck_input.evidence_verification_results)
    probe_refs = _behavioral_probe_acceptance_refs(recheck_input.run_manifest)
    covered = _verified_live_acceptance_refs(verified) | _failed_blocker_acceptance_refs(
        recheck_input.failed_final_evidence_blockers
    )
    missing = probe_refs - covered
    if missing:
        raise ReworkEvidenceError("behavioral probe failure must be represented in final evidence")


def build_rework_final_evidence_table(recheck_input: ReworkEvidenceRecheckInput) -> FinalEvidenceTable:
    validate_rework_evidence_freshness(recheck_input)
    validate_rework_run_manifest_readiness(
        recheck_input.run_manifest,
        active_acceptance_refs=tuple(
            criterion.acceptance_ref for criterion in recheck_input.active_acceptance_contract.criteria
        ),
        environment_usage=recheck_input.environment_usage,
    )
    _validate_behavioral_probe_coverage(recheck_input)
    verified = _verified_evidence(recheck_input.evidence_verification_results)
    table = FinalEvidenceTableBuilder().build(
        FinalEvidenceTableInput(
            active_acceptance_contract=recheck_input.active_acceptance_contract,
            verified_evidence=verified,
            failed_blockers=recheck_input.failed_final_evidence_blockers,
            generated_at=recheck_input.checked_at,
            evidence_namespace_ref=rework_evidence_namespace_ref(recheck_input.namespace),
        )
    )
    return validate_rework_final_evidence_table_freshness(
        table,
        namespace=recheck_input.namespace,
        verified_evidence=verified,
    )


def build_rework_checker_verdict(
    recheck_input: ReworkEvidenceRecheckInput,
    final_evidence_table: FinalEvidenceTable,
) -> CheckerVerdict:
    validate_rework_evidence_freshness(recheck_input)
    final_evidence_table = validate_rework_final_evidence_table_freshness(
        final_evidence_table,
        namespace=recheck_input.namespace,
        verified_evidence=_verified_evidence(recheck_input.evidence_verification_results),
    )
    return CheckerService().review(
        CheckerServiceInput(
            ticket_ref=recheck_input.attempt.ticket_ref,
            work_product=recheck_input.work_product,
            source_diff_ref=recheck_input.source_diff_ref,
            active_acceptance_contract=recheck_input.active_acceptance_contract,
            final_evidence_table=final_evidence_table,
            notes=(),
            checker_blockers=(),
            checked_at=recheck_input.checked_at,
        )
    )


def _blocker_refs_from_checker(verdict: CheckerVerdict) -> tuple[BlockerRef, ...]:
    return tuple(BlockerRef(value=blocker.blocker_id.value) for blocker in verdict.blockers if blocker.blocker_id)


def evaluate_rework_closeout(
    recheck_input: ReworkEvidenceRecheckInput,
    source_inventory: SourceInventory,
    final_evidence_table: FinalEvidenceTable,
    checker_verdict: CheckerVerdict,
) -> CloseoutGateResult | None:
    if recheck_input.closeout_context is None:
        return None
    gate_input = _validate_closeout_context_freshness(
        recheck_input,
        source_inventory,
        final_evidence_table,
        checker_verdict,
    )
    return CloseoutGate().evaluate(gate_input)


def _namespace_value(recheck_input: ReworkEvidenceRecheckInput) -> str:
    return rework_evidence_namespace_ref(recheck_input.namespace).value


def _require_ref_contains_namespace(ref_value: str, namespace_value: str, label: str) -> None:
    if namespace_value not in ref_value:
        raise ReworkEvidenceError(f"{label} namespace mismatch")


def _validate_closeout_context_freshness(
    recheck_input: ReworkEvidenceRecheckInput,
    source_inventory: SourceInventory,
    final_evidence_table: FinalEvidenceTable,
    checker_verdict: CheckerVerdict,
) -> CloseoutGateInput:
    if recheck_input.closeout_context is None:
        raise ReworkEvidenceError("closeout_context is required for closeout recheck")
    gate_input = recheck_input.closeout_context.closeout_input
    namespace_value = _namespace_value(recheck_input)
    _require_ref_contains_namespace(final_evidence_table.final_evidence_table_id.value, namespace_value, "final evidence table")
    _require_ref_contains_namespace(checker_verdict.checker_verdict_id.value, namespace_value, "checker verdict")
    if gate_input.run_manifest.run_manifest_id != recheck_input.run_manifest.run_manifest_id:
        raise ReworkEvidenceError("run manifest namespace mismatch")
    if gate_input.source_inventory != source_inventory:
        raise ReworkEvidenceError("source inventory namespace mismatch")
    if gate_input.final_evidence_table != final_evidence_table:
        raise ReworkEvidenceError("final evidence table namespace mismatch")
    if gate_input.checker_verdict != checker_verdict:
        raise ReworkEvidenceError("checker verdict namespace mismatch")

    current_evidence_refs = {
        evidence.verified_evidence_id.value
        for evidence in _verified_evidence(recheck_input.evidence_verification_results)
    }
    inventory_evidence_refs = {
        ref.value
        for entry in source_inventory.entries
        for ref in entry.evidence_refs
    }
    if not inventory_evidence_refs.issubset(current_evidence_refs):
        raise ReworkEvidenceError("source inventory namespace mismatch")
    return gate_input


def recheck_rework_attempt(recheck_input: ReworkEvidenceRecheckInput) -> ReworkEvidenceRecheckResult:
    source_inventory = build_rework_source_inventory(recheck_input)
    final_evidence_table = build_rework_final_evidence_table(recheck_input)
    checker_verdict = build_rework_checker_verdict(recheck_input, final_evidence_table)
    closeout_gate_result = evaluate_rework_closeout(
        recheck_input,
        source_inventory,
        final_evidence_table,
        checker_verdict,
    )

    remaining = _blocker_refs_from_checker(checker_verdict)
    if closeout_gate_result is not None:
        remaining = remaining + tuple(
            BlockerRef(value=blocker.blocker_id.value)
            for blocker in closeout_gate_result.blockers
            if blocker.blocker_id is not None
        )

    if remaining:
        status = ReworkOutcomeStatus.REWORK_REQUIRED
        accepted = ()
    else:
        status = ReworkOutcomeStatus.ACCEPTED
        accepted = recheck_input.target_blocker_refs

    return ReworkEvidenceRecheckResult(
        namespace=recheck_input.namespace,
        attempt_ref=recheck_input.attempt.rework_attempt_id,
        source_inventory=source_inventory,
        final_evidence_table=final_evidence_table,
        checker_verdict=checker_verdict,
        closeout_gate_result=closeout_gate_result,
        status=status,
        remaining_blocker_refs=remaining,
        accepted_blocker_refs=accepted,
        checked_refs=tuple(
            dict.fromkeys(
                (
                    source_inventory.source_inventory_id.value,
                    final_evidence_table.final_evidence_table_id.value,
                    checker_verdict.checker_verdict_id.value,
                    *(closeout_gate_result.checked_refs if closeout_gate_result else ()),
                )
            )
        ),
        created_at=recheck_input.checked_at,
    )


__all__ = [
    "ReworkCloseoutRecheckContext",
    "ReworkEnvironmentUsage",
    "ReworkEvidenceError",
    "ReworkEvidenceNamespace",
    "ReworkEvidenceRecheckInput",
    "ReworkEvidenceRecheckResult",
    "build_rework_checker_verdict",
    "build_rework_final_evidence_table",
    "build_rework_source_inventory",
    "evaluate_rework_closeout",
    "recheck_rework_attempt",
    "rework_evidence_namespace_ref",
    "validate_rework_attempt_fact_refs",
    "validate_rework_evidence_freshness",
    "validate_rework_final_evidence_table_freshness",
    "validate_rework_run_manifest_readiness",
]
