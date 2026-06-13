from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from boardroom_os.checker.verdict import (
    CheckerBlockerCode,
    CheckerVerdict,
    CheckerVerdictBlocker,
    CheckerVerdictStatus,
)
from boardroom_os.closeout.gate import (
    CloseoutGateBlocker,
    CloseoutGateBlockerCode,
    CloseoutGateResult,
    CloseoutGateVerdict,
)
from boardroom_os.contracts.evidence_obligation import RequiredArtifactType
from boardroom_os.contracts.types import (
    AcceptanceRef,
    ContractId,
    EvidenceObligationRef,
    SourceSurfaceRef,
)
from boardroom_os.evidence.table import (
    FinalEvidenceBlocker,
    FinalEvidenceStatus,
    FinalEvidenceTable,
)
from boardroom_os.rework.model import (
    BlockerRef,
    BlockerReport,
    BlockerReportId,
    BlockerSourceKind,
    ExpectedFactRef,
    ObservedFactRef,
    ReworkActorKind,
    ReworkCycleId,
    ReworkIssue,
    ReworkIssueCode,
    ReworkIssueId,
    ReworkIssueSeverity,
    ReworkRequest,
    ReworkRequestId,
    ReworkSuspectedDomain,
    RunId,
    validate_issue_contract_scope,
    validate_request_verified_sources,
)

_REQUESTER_ACTORS = frozenset(
    {
        ReworkActorKind.CHECKER,
        ReworkActorKind.CLOSEOUT_GATE,
        ReworkActorKind.GRAPH_PATCH_REVIEW_GATE,
        ReworkActorKind.GOVERNANCE_ADAPTER,
        ReworkActorKind.EVIDENCE_VERIFIER,
        ReworkActorKind.CLOSEOUT,
    }
)


def _reject_empty_tuple(values: tuple[Any, ...], field_name: str) -> tuple[Any, ...]:
    if not values:
        raise ValueError(f"{field_name} must not be empty")
    return values


def _reject_duplicate_value_refs(values: tuple[Any, ...], field_name: str) -> tuple[Any, ...]:
    seen: set[str] = set()
    for value in values:
        ref_value = value.value if hasattr(value, "value") else str(value)
        if ref_value in seen:
            raise ValueError(f"{field_name} must be unique")
        seen.add(ref_value)
    return values


def _require_timezone(value: datetime, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value


class BlockerProjectionContext(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    cycle_id: ReworkCycleId
    run_id: RunId
    package_contract_ref: ContractId
    run_manifest_ref: str
    active_acceptance_refs: tuple[AcceptanceRef, ...]
    active_source_surface_refs: tuple[SourceSurfaceRef, ...]
    active_evidence_obligation_refs: tuple[EvidenceObligationRef, ...]
    active_graph_version: int = Field(gt=0)
    requested_by_actor: ReworkActorKind
    requested_at: datetime

    @field_validator(
        "active_acceptance_refs",
        "active_source_surface_refs",
        "active_evidence_obligation_refs",
    )
    @classmethod
    def _reject_empty_or_duplicate_refs(cls, values: tuple[Any, ...], info: Any) -> tuple[Any, ...]:
        _reject_empty_tuple(values, info.field_name)
        return _reject_duplicate_value_refs(values, info.field_name)

    @field_validator("run_manifest_ref")
    @classmethod
    def _reject_empty_run_manifest_ref(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("run_manifest_ref must not be empty")
        return normalized

    @field_validator("requested_at")
    @classmethod
    def _require_requested_at_timezone(cls, value: datetime) -> datetime:
        return _require_timezone(value, "requested_at")

    @model_validator(mode="after")
    def _validate_requested_by_actor(self) -> "BlockerProjectionContext":
        if self.requested_by_actor not in _REQUESTER_ACTORS:
            raise ValueError("requested_by_actor is not allowed to create rework requests")
        return self


def project_final_evidence_table_blockers(
    table: FinalEvidenceTable,
    context: BlockerProjectionContext,
) -> ReworkRequest:
    issues: list[ReworkIssue] = []
    source_ref = table.final_evidence_table_id.value if table.final_evidence_table_id else "final-evidence-table"
    for row in table.rows:
        if row.status is FinalEvidenceStatus.MISSING:
            blocker_ref = BlockerRef(value=f"final-evidence-missing.{row.acceptance_ref.value}")
            issue = _issue(
                issue_id=f"rework-issue.final-evidence-missing.{row.acceptance_ref.value}",
                blocker_refs=(blocker_ref,),
                issue_code=ReworkIssueCode.FINAL_EVIDENCE_MISSING,
                acceptance_refs=(row.acceptance_ref,),
                context=context,
                source_surface_refs=context.active_source_surface_refs,
                evidence_obligation_refs=context.active_evidence_obligation_refs,
                required_artifact_types=row.missing_required_artifact_types,
                suspected_domains=(ReworkSuspectedDomain.EVIDENCE_PROJECTION,),
                description=f"Final evidence row is missing for {row.acceptance_ref.value}.",
                expected_fact_refs=(ExpectedFactRef(value=f"fact.required-evidence.{row.acceptance_ref.value}"),),
            )
            issues.append(issue)
        if row.status is FinalEvidenceStatus.FAILED:
            for blocker in row.blockers:
                issues.append(_issue_from_final_blocker(blocker, context))
    if not issues:
        raise ValueError("final evidence table has no missing or failed blockers")
    blocker_report = _blocker_report(
        blocker_report_id=f"blocker-report.final-evidence.{source_ref}",
        source_kind=BlockerSourceKind.FINAL_EVIDENCE_TABLE,
        source_ref=source_ref,
        issues=tuple(issues),
        context=context,
    )
    request = _request(
        request_id=f"rework-request.final-evidence.{source_ref}",
        source_refs=(blocker_report.blocker_report_id.value,),
        issues=tuple(issues),
        context=context,
    )
    validate_request_verified_sources(request, (blocker_report,))
    return request


def project_checker_verdict_blockers(
    verdict: CheckerVerdict,
    context: BlockerProjectionContext,
) -> ReworkRequest:
    if verdict.status not in {CheckerVerdictStatus.REWORK_REQUIRED, CheckerVerdictStatus.ESCALATE}:
        raise ValueError("checker verdict has no verified blockers")
    if not verdict.blockers:
        raise ValueError("checker verdict has no verified blockers")

    issues = tuple(_issue_from_checker_blocker(blocker, context) for blocker in verdict.blockers)
    source_ref = verdict.checker_verdict_id.value
    blocker_report = _blocker_report(
        blocker_report_id=f"blocker-report.checker.{source_ref}",
        source_kind=BlockerSourceKind.CHECKER_VERDICT,
        source_ref=source_ref,
        issues=issues,
        context=context,
    )
    request = _request(
        request_id=f"rework-request.checker.{verdict.checker_verdict_id.value}",
        source_refs=(blocker_report.blocker_report_id.value,),
        issues=issues,
        context=context,
    )
    validate_request_verified_sources(request, (blocker_report,))
    return request


def project_closeout_gate_blockers(
    closeout_gate_result: CloseoutGateResult,
    context: BlockerProjectionContext,
) -> ReworkRequest:
    if closeout_gate_result.verdict is CloseoutGateVerdict.PASSED:
        raise ValueError("closeout gate passed, no blockers to project")
    issues = tuple(
        _issue_from_closeout_blocker(blocker, closeout_gate_result, context)
        for blocker in closeout_gate_result.blockers
    )
    source_ref = closeout_gate_result.closeout_gate_result_id.value
    blocker_report = _blocker_report(
        blocker_report_id=f"blocker-report.closeout.{source_ref}",
        source_kind=BlockerSourceKind.CLOSEOUT_GATE,
        source_ref=source_ref,
        issues=issues,
        context=context,
    )
    request = _request(
        request_id=f"rework-request.closeout.{closeout_gate_result.closeout_gate_result_id.value}",
        source_refs=(blocker_report.blocker_report_id.value,),
        issues=issues,
        context=context,
    )
    validate_request_verified_sources(request, (blocker_report,))
    return request


def project_v2_090k_failure_summary(
    summary_path: str | Path,
    context: BlockerProjectionContext,
) -> ReworkRequest:
    data = json.loads(Path(summary_path).read_text(encoding="utf-8"))
    if data.get("snapshot_kind") != "curated_real_provider_failure":
        raise ValueError("unsupported V2-090K failure snapshot kind")
    failures = data.get("primary_failures")
    if not isinstance(failures, list):
        raise ValueError("primary_failures must be a list")
    failure_ids = tuple(item.get("failure_id") for item in failures)
    expected_ids = tuple(_V2_090K_FAILURE_MAPPINGS)
    if failure_ids != expected_ids:
        raise ValueError("unexpected V2-090K primary failure ids")

    issues = tuple(_issue_from_v2_090k_failure(item, context) for item in failures)
    snapshot_id = data["snapshot_id"]
    source_ref = f"v2-090k-failure-summary.{snapshot_id}"
    blocker_report = _blocker_report(
        blocker_report_id=f"blocker-report.v2-090k.{snapshot_id}",
        source_kind=BlockerSourceKind.PROCESS_AUDIT,
        source_ref=source_ref,
        issues=issues,
        context=context,
    )
    request = _request(
        request_id=f"rework-request.v2-090k.{snapshot_id}",
        source_refs=(blocker_report.blocker_report_id.value,),
        issues=issues,
        context=context,
    )
    validate_request_verified_sources(request, (blocker_report,))
    return request


def _issue_from_final_blocker(
    blocker: FinalEvidenceBlocker,
    context: BlockerProjectionContext,
) -> ReworkIssue:
    blocker_id = blocker.blocker_id.value if blocker.blocker_id else blocker.related_ref
    issue_code = _issue_code_from_text(blocker.message, blocker.source, ReworkIssueCode.FINAL_EVIDENCE_FAILED)
    return _issue(
        issue_id=f"rework-issue.final-evidence-failed.{blocker.acceptance_ref.value}.{blocker.related_ref}",
        blocker_refs=(BlockerRef(value=blocker_id),),
        issue_code=issue_code,
        acceptance_refs=(blocker.acceptance_ref,),
        context=context,
        source_surface_refs=context.active_source_surface_refs,
        evidence_obligation_refs=context.active_evidence_obligation_refs,
        required_artifact_types=(RequiredArtifactType(value="verified_evidence"),),
        suspected_domains=_domains_for_issue_code(issue_code),
        description=blocker.message,
        observed_fact_refs=(ObservedFactRef(value=f"fact.final-evidence.blocker.{blocker.related_ref}"),),
    )


def _issue_from_checker_blocker(
    blocker: CheckerVerdictBlocker,
    context: BlockerProjectionContext,
) -> ReworkIssue:
    issue_code = {
        CheckerBlockerCode.FINAL_EVIDENCE_MISSING: ReworkIssueCode.FINAL_EVIDENCE_MISSING,
        CheckerBlockerCode.FINAL_EVIDENCE_FAILED: ReworkIssueCode.FINAL_EVIDENCE_FAILED,
        CheckerBlockerCode.CHECKER_BLOCKER: ReworkIssueCode.CHECKER_BLOCKER,
        CheckerBlockerCode.CONTRACT_MISMATCH: ReworkIssueCode.CONTRACT_MISMATCH,
        CheckerBlockerCode.WORK_PRODUCT_MISMATCH: ReworkIssueCode.WORK_PRODUCT_MISMATCH,
        CheckerBlockerCode.INVALID_CHECKER_INPUT: ReworkIssueCode.INVALID_CHECKER_INPUT,
    }[blocker.code]
    domains = (
        (
            ReworkSuspectedDomain.CONTRACT,
            ReworkSuspectedDomain.PROBE,
            ReworkSuspectedDomain.IMPLEMENTATION,
        )
        if blocker.code is CheckerBlockerCode.CONTRACT_MISMATCH
        else _domains_for_issue_code(issue_code)
    )
    acceptance_refs = (blocker.acceptance_ref,) if blocker.acceptance_ref else context.active_acceptance_refs
    blocker_ref = blocker.blocker_id.value if blocker.blocker_id else blocker.related_ref
    return _issue(
        issue_id=f"rework-issue.checker.{blocker_ref}",
        blocker_refs=(BlockerRef(value=blocker_ref),),
        issue_code=issue_code,
        acceptance_refs=acceptance_refs,
        context=context,
        source_surface_refs=context.active_source_surface_refs,
        evidence_obligation_refs=context.active_evidence_obligation_refs,
        required_artifact_types=(RequiredArtifactType(value="checker_blocker"),),
        suspected_domains=domains,
        description=blocker.message,
        observed_fact_refs=(ObservedFactRef(value=f"fact.checker.blocker.{blocker.related_ref}"),),
    )


def _issue_from_closeout_blocker(
    blocker: CloseoutGateBlocker,
    result: CloseoutGateResult,
    context: BlockerProjectionContext,
) -> ReworkIssue:
    related_ref = blocker.related_ref or result.closeout_gate_result_id.value
    domains = (
        (ReworkSuspectedDomain.CLOSEOUT_AUDIT,)
        if _is_closeout_audit_blocker(blocker)
        else (ReworkSuspectedDomain.EVIDENCE_PROJECTION,)
    )
    blocker_ref = blocker.blocker_id.value if blocker.blocker_id else related_ref
    return _issue(
        issue_id=f"rework-issue.closeout.{blocker_ref}",
        blocker_refs=(BlockerRef(value=blocker_ref),),
        issue_code=ReworkIssueCode.CLOSEOUT_GATE_FAILURE,
        acceptance_refs=context.active_acceptance_refs,
        context=context,
        source_surface_refs=context.active_source_surface_refs,
        evidence_obligation_refs=context.active_evidence_obligation_refs,
        required_artifact_types=(RequiredArtifactType(value="closeout_gate"),),
        suspected_domains=domains,
        description=blocker.message,
        observed_fact_refs=(ObservedFactRef(value=f"fact.closeout.blocker.{related_ref}"),),
    )


def _issue_from_v2_090k_failure(
    failure: dict[str, Any],
    context: BlockerProjectionContext,
) -> ReworkIssue:
    failure_id = failure["failure_id"]
    mapping = _V2_090K_FAILURE_MAPPINGS[failure_id]
    acceptance_refs = _select_refs(
        context.active_acceptance_refs,
        mapping.acceptance_refs,
        "acceptance_ref",
    )
    source_surface_refs = _select_refs(
        context.active_source_surface_refs,
        mapping.source_surface_refs,
        "source_surface_ref",
    )
    evidence_obligation_refs = _select_refs(
        context.active_evidence_obligation_refs,
        mapping.evidence_obligation_refs,
        "evidence_obligation_ref",
    )
    observed_fact_refs = tuple(ObservedFactRef(value=value) for value in mapping.observed_fact_refs(failure))
    return _issue(
        issue_id=f"rework-issue.v2-090k.{failure_id}",
        blocker_refs=(BlockerRef(value=f"v2-090k-failure.{failure_id}"),),
        issue_code=mapping.issue_code,
        acceptance_refs=acceptance_refs,
        context=context,
        source_surface_refs=source_surface_refs,
        evidence_obligation_refs=evidence_obligation_refs,
        required_artifact_types=(RequiredArtifactType(value=mapping.required_artifact_type),),
        suspected_domains=mapping.domains,
        description=_failure_description(failure),
        observed_fact_refs=observed_fact_refs,
        expected_fact_refs=(ExpectedFactRef(value=f"fact.v2-090k.expected.{failure_id}"),),
    )


def _issue(
    *,
    issue_id: str,
    blocker_refs: tuple[BlockerRef, ...],
    issue_code: ReworkIssueCode,
    acceptance_refs: tuple[AcceptanceRef, ...],
    context: BlockerProjectionContext,
    source_surface_refs: tuple[SourceSurfaceRef, ...],
    evidence_obligation_refs: tuple[EvidenceObligationRef, ...],
    required_artifact_types: tuple[RequiredArtifactType, ...],
    suspected_domains: tuple[ReworkSuspectedDomain, ...],
    description: str,
    observed_fact_refs: tuple[ObservedFactRef, ...] = (),
    expected_fact_refs: tuple[ExpectedFactRef, ...] = (),
) -> ReworkIssue:
    issue = ReworkIssue(
        issue_id=ReworkIssueId(value=issue_id),
        blocker_refs=blocker_refs,
        issue_code=issue_code,
        severity=ReworkIssueSeverity.BLOCKING,
        acceptance_refs=acceptance_refs,
        source_surface_refs=source_surface_refs,
        run_manifest_refs=(context.run_manifest_ref,),
        evidence_obligation_refs=evidence_obligation_refs,
        observed_fact_refs=observed_fact_refs,
        expected_fact_refs=expected_fact_refs,
        suspected_domains=suspected_domains,
        required_artifact_types=required_artifact_types,
        description=description,
    )
    validate_issue_contract_scope(
        issue,
        active_acceptance_refs=context.active_acceptance_refs,
        active_source_surface_refs=context.active_source_surface_refs,
        active_evidence_obligation_refs=context.active_evidence_obligation_refs,
    )
    return issue


def _request(
    *,
    request_id: str,
    source_refs: tuple[str, ...],
    issues: tuple[ReworkIssue, ...],
    context: BlockerProjectionContext,
) -> ReworkRequest:
    return ReworkRequest(
        rework_request_id=ReworkRequestId(value=request_id),
        cycle_id=context.cycle_id,
        run_id=context.run_id,
        request_source_refs=source_refs,
        issues=issues,
        requested_by_actor=context.requested_by_actor,
        requested_at=context.requested_at,
        active_contract_refs=(context.package_contract_ref,),
        active_graph_version=context.active_graph_version,
    )


def _blocker_report(
    *,
    blocker_report_id: str,
    source_kind: BlockerSourceKind,
    source_ref: str,
    issues: tuple[ReworkIssue, ...],
    context: BlockerProjectionContext,
) -> BlockerReport:
    acceptance_refs = tuple(
        {ref.value: ref for issue in issues for ref in issue.acceptance_refs}.values()
    )
    blocker_refs = tuple(
        {ref.value: ref for issue in issues for ref in issue.blocker_refs}.values()
    )
    return BlockerReport(
        blocker_report_id=BlockerReportId(value=blocker_report_id),
        run_id=context.run_id,
        source_kind=source_kind,
        source_ref=source_ref,
        contract_refs=(context.package_contract_ref,),
        acceptance_refs=acceptance_refs,
        package_contract_ref=context.package_contract_ref,
        run_manifest_ref=context.run_manifest_ref,
        blockers=blocker_refs,
        created_at=context.requested_at,
    )


def _issue_code_from_text(
    message: str,
    source: str,
    default: ReworkIssueCode,
) -> ReworkIssueCode:
    text = f"{message} {source}".lower()
    if "shape" in text or "book.title" in text or "$.title" in text:
        return ReworkIssueCode.PROBE_RESPONSE_SHAPE_MISMATCH
    if "env" in text or "environment" in text:
        return ReworkIssueCode.ENV_BINDING_NOT_CONVERGED
    if "old acceptance" in text or "ac-tiny" in text:
        return ReworkIssueCode.FINAL_EVIDENCE_OLD_ACCEPTANCE_REFS
    if "old run" in text:
        return ReworkIssueCode.CLOSEOUT_AUDIT_OLD_RUN_REFS
    return default


def _domains_for_issue_code(issue_code: ReworkIssueCode) -> tuple[ReworkSuspectedDomain, ...]:
    if issue_code is ReworkIssueCode.PROBE_RESPONSE_SHAPE_MISMATCH:
        return (ReworkSuspectedDomain.IMPLEMENTATION, ReworkSuspectedDomain.PROBE)
    if issue_code is ReworkIssueCode.ENV_BINDING_NOT_CONVERGED:
        return (ReworkSuspectedDomain.RUN_ENV, ReworkSuspectedDomain.IMPLEMENTATION)
    if issue_code is ReworkIssueCode.FINAL_EVIDENCE_OLD_ACCEPTANCE_REFS:
        return (ReworkSuspectedDomain.EVIDENCE_PROJECTION,)
    if issue_code is ReworkIssueCode.CLOSEOUT_AUDIT_OLD_RUN_REFS:
        return (ReworkSuspectedDomain.CLOSEOUT_AUDIT,)
    if issue_code is ReworkIssueCode.CONTRACT_MISMATCH:
        return (
            ReworkSuspectedDomain.CONTRACT,
            ReworkSuspectedDomain.PROBE,
            ReworkSuspectedDomain.IMPLEMENTATION,
        )
    return (ReworkSuspectedDomain.EVIDENCE_PROJECTION,)


def _is_closeout_audit_blocker(blocker: CloseoutGateBlocker) -> bool:
    if blocker.code in {
        CloseoutGateBlockerCode.PROCESS_AUDIT_NOT_READY,
        CloseoutGateBlockerCode.REPLAY_NOT_READY,
        CloseoutGateBlockerCode.GIT_AUDIT_NOT_READY,
    }:
        return True
    related_ref = (blocker.related_ref or "").lower()
    return any(token in related_ref for token in ("audit", "replay", "git", "closeout"))


def _select_refs(
    active_refs: tuple[Any, ...],
    requested_values: tuple[str, ...] | None,
    ref_kind: str,
) -> tuple[Any, ...]:
    if requested_values is None:
        return active_refs
    by_value = {ref.value: ref for ref in active_refs}
    selected: list[Any] = []
    for value in requested_values:
        if value not in by_value:
            raise ValueError(f"missing active {ref_kind} for V2-090K projection: {value}")
        selected.append(by_value[value])
    return tuple(selected)


def _failure_description(failure: dict[str, Any]) -> str:
    expected_use = failure.get("v2_100_expected_use")
    if isinstance(expected_use, str) and expected_use.strip():
        return expected_use
    return f"Project V2-090K failure {failure['failure_id']} requires typed rework."


class _SnapshotFailureMapping(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    issue_code: ReworkIssueCode
    acceptance_refs: tuple[str, ...] | None
    source_surface_refs: tuple[str, ...]
    evidence_obligation_refs: tuple[str, ...] | None
    domains: tuple[ReworkSuspectedDomain, ...]
    required_artifact_type: str
    observed_fact_refs: Callable[[dict[str, Any]], tuple[str, ...]]


def _observed_probe_failure(failure: dict[str, Any]) -> tuple[str, ...]:
    actual = failure.get("actual", {})
    return (
        "fact.v2-090k.observed.probe-response-shape-mismatch",
        *(f"fact.v2-090k.actual.{key}.{value}" for key, value in actual.items() if isinstance(value, str)),
    )


def _observed_env_failure(failure: dict[str, Any]) -> tuple[str, ...]:
    implementation_names = failure.get("implementation_env_names", ())
    declared_names = failure.get("declared_env_names", ())
    return (
        "fact.v2-090k.observed.env-binding-not-converged",
        *(f"fact.v2-090k.declared-env.{name}" for name in declared_names),
        *(f"fact.v2-090k.implementation-env.{name}" for name in implementation_names),
    )


def _observed_old_acceptance_refs(failure: dict[str, Any]) -> tuple[str, ...]:
    refs = failure.get("final_evidence_refs", ())
    observed = [f"fact.v2-090k.stale-acceptance-ref.{ref}" for ref in refs if "AC-TINY-" in ref]
    if not observed:
        observed.append("fact.v2-090k.observed.AC-TINY-stale-acceptance-refs")
    return tuple(observed)


def _observed_old_run_refs(failure: dict[str, Any]) -> tuple[str, ...]:
    old_run_ref = failure.get("observed_old_run_ref")
    observed = [f"fact.v2-090k.stale-run-ref.{old_run_ref}"] if old_run_ref == "run-v2-080f" else []
    if not observed:
        observed.append("fact.v2-090k.observed.run-v2-080f")
    return tuple(observed)


_V2_090K_FAILURE_MAPPINGS = {
    "probe-response-shape-mismatch": _SnapshotFailureMapping(
        issue_code=ReworkIssueCode.PROBE_RESPONSE_SHAPE_MISMATCH,
        acceptance_refs=("acceptance.book.add", "acceptance.book.list"),
        source_surface_refs=("surface.backend.api", "surface.behavioral_probe"),
        evidence_obligation_refs=("evidence.add.api", "evidence.list.api"),
        domains=(ReworkSuspectedDomain.IMPLEMENTATION, ReworkSuspectedDomain.PROBE),
        required_artifact_type="live_blackbox_integration",
        observed_fact_refs=_observed_probe_failure,
    ),
    "env-binding-not-converged": _SnapshotFailureMapping(
        issue_code=ReworkIssueCode.ENV_BINDING_NOT_CONVERGED,
        acceptance_refs=("acceptance.persistence.sqlite", "acceptance.instructions.tests"),
        source_surface_refs=("surface.run_manifest", "surface.backend.api"),
        evidence_obligation_refs=("evidence.tests.instructions", "evidence.sqlite.persistence"),
        domains=(ReworkSuspectedDomain.RUN_ENV, ReworkSuspectedDomain.IMPLEMENTATION),
        required_artifact_type="run_manifest",
        observed_fact_refs=_observed_env_failure,
    ),
    "final-evidence-uses-old-acceptance-refs": _SnapshotFailureMapping(
        issue_code=ReworkIssueCode.FINAL_EVIDENCE_OLD_ACCEPTANCE_REFS,
        acceptance_refs=None,
        source_surface_refs=("surface.closeout_audit",),
        evidence_obligation_refs=None,
        domains=(ReworkSuspectedDomain.EVIDENCE_PROJECTION,),
        required_artifact_type="final_evidence_table",
        observed_fact_refs=_observed_old_acceptance_refs,
    ),
    "closeout-audit-references-old-run": _SnapshotFailureMapping(
        issue_code=ReworkIssueCode.CLOSEOUT_AUDIT_OLD_RUN_REFS,
        acceptance_refs=None,
        source_surface_refs=("surface.closeout_audit",),
        evidence_obligation_refs=None,
        domains=(ReworkSuspectedDomain.CLOSEOUT_AUDIT,),
        required_artifact_type="process_audit",
        observed_fact_refs=_observed_old_run_refs,
    ),
}


__all__ = [
    "BlockerProjectionContext",
    "project_checker_verdict_blockers",
    "project_closeout_gate_blockers",
    "project_final_evidence_table_blockers",
    "project_v2_090k_failure_summary",
]
