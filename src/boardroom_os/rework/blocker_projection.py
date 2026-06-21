from __future__ import annotations

import json
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Callable, Mapping

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


class ManifestReworkRoutingStatus(StrEnum):
    REWORK_REQUIRED = "rework_required"
    BLOCKED_OR_ESCALATED = "blocked_or_escalated"
    PASSED = "passed"


class ManifestReworkRoutingResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: ManifestReworkRoutingStatus
    rework_request: ReworkRequest | None = None
    blocked_reason_code: str | None = None
    blocked_message: str | None = None

    @field_validator("blocked_reason_code", "blocked_message")
    @classmethod
    def _normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("blocked fields must not be empty")
        return normalized

    @model_validator(mode="after")
    def _validate_status_shape(self) -> "ManifestReworkRoutingResult":
        if self.status is ManifestReworkRoutingStatus.REWORK_REQUIRED:
            if self.rework_request is None:
                raise ValueError("rework_required routing requires rework_request")
            if self.blocked_reason_code is not None or self.blocked_message is not None:
                raise ValueError("rework_required routing must not include blocked reason")
        if self.status is ManifestReworkRoutingStatus.BLOCKED_OR_ESCALATED:
            if self.rework_request is not None:
                raise ValueError("blocked_or_escalated routing must not include rework_request")
            if self.blocked_reason_code is None or self.blocked_message is None:
                raise ValueError("blocked_or_escalated routing requires blocked reason")
        if self.status is ManifestReworkRoutingStatus.PASSED:
            if self.rework_request is not None:
                raise ValueError("passed routing must not include rework_request")
            if self.blocked_reason_code is not None or self.blocked_message is not None:
                raise ValueError("passed routing must not include blocked reason")
        return self


def route_manifest_blackbox_facts(
    *,
    facts: tuple[Any, ...],
    context: BlockerProjectionContext,
    advisory_context: Mapping[str, Any] | None = None,
    raw_exception: Exception | None = None,
) -> ManifestReworkRoutingResult:
    context_blocker = _manifest_context_blocker(context)
    if context_blocker is not None:
        return context_blocker
    if not facts:
        if raw_exception is not None:
            return _blocked_manifest_routing(
                "raw_exception_without_facts",
                "raw exception alone cannot produce a rework request",
            )
        return _blocked_manifest_routing(
            "missing_blackbox_facts",
            "manifest routing requires blackbox action execution facts",
        )

    for fact in facts:
        fact_blocker = _manifest_fact_blocker(fact)
        if fact_blocker is not None:
            return fact_blocker

    failed_facts = tuple(fact for fact in facts if _blackbox_fact_failed(fact))
    if not failed_facts:
        return ManifestReworkRoutingResult(status=ManifestReworkRoutingStatus.PASSED)

    first_fact = failed_facts[0]
    first_fact_ref = _required_ref_value(getattr(first_fact, "fact_id", None))
    ref_fragment = _safe_ref_fragment(first_fact_ref)
    blocker_ref = BlockerRef(value=f"run-manifest-error.{ref_fragment}")
    observed_context = _manifest_observed_context(first_fact)
    merged_advisory_context = dict(advisory_context or {})
    merged_advisory_context["observed"] = observed_context
    issue = _issue(
        issue_id=f"rework-issue.run-manifest-error.{ref_fragment}",
        blocker_refs=(blocker_ref,),
        issue_code=ReworkIssueCode.RUN_MANIFEST_ERROR,
        acceptance_refs=context.active_acceptance_refs,
        context=context,
        source_surface_refs=context.active_source_surface_refs,
        evidence_obligation_refs=context.active_evidence_obligation_refs,
        required_artifact_types=(RequiredArtifactType(value="live_blackbox_integration"),),
        suspected_domains=(
            ReworkSuspectedDomain.RUN_ENV,
            ReworkSuspectedDomain.PROBE,
            ReworkSuspectedDomain.IMPLEMENTATION,
        ),
        description="Blackbox action execution facts show run manifest, API, readiness or response-shape drift.",
        observed_fact_refs=tuple(
            ObservedFactRef(value=_required_ref_value(getattr(fact, "fact_id", None)))
            for fact in failed_facts
        ),
        expected_fact_refs=tuple(
            ExpectedFactRef(value=f"fact.blackbox.expected.{_required_text(getattr(fact, 'action_id', None))}")
            for fact in failed_facts
        ),
        advisory_context=merged_advisory_context,
    )
    source_ref = f"blackbox-facts.{_required_ref_value(getattr(first_fact, 'plan_ref', None))}"
    blocker_report = _blocker_report(
        blocker_report_id=f"blocker-report.run-manifest-error.{ref_fragment}",
        source_kind=BlockerSourceKind.RUN_MANIFEST,
        source_ref=source_ref,
        issues=(issue,),
        context=context,
    )
    request = _request(
        request_id=f"rework-request.run-manifest-error.{ref_fragment}",
        source_refs=(blocker_report.blocker_report_id.value,),
        issues=(issue,),
        context=context,
    )
    validate_request_verified_sources(request, (blocker_report,))
    return ManifestReworkRoutingResult(
        status=ManifestReworkRoutingStatus.REWORK_REQUIRED,
        rework_request=request,
    )


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


def _manifest_context_blocker(context: BlockerProjectionContext) -> ManifestReworkRoutingResult | None:
    if not getattr(context, "active_acceptance_refs", ()):
        return _blocked_manifest_routing(
            "missing_active_acceptance_refs",
            "manifest routing requires active acceptance refs",
        )
    if not getattr(context, "active_source_surface_refs", ()):
        return _blocked_manifest_routing(
            "missing_active_source_surface_refs",
            "manifest routing requires active source surface refs",
        )
    if not getattr(context, "active_evidence_obligation_refs", ()):
        return _blocked_manifest_routing(
            "missing_active_evidence_obligation_refs",
            "manifest routing requires active evidence obligation refs",
        )
    if _optional_ref_value(getattr(context, "package_contract_ref", None)) is None:
        return _blocked_manifest_routing(
            "missing_package_contract_ref",
            "manifest routing requires an active package contract ref",
        )
    graph_version = getattr(context, "active_graph_version", None)
    if not isinstance(graph_version, int) or graph_version <= 0:
        return _blocked_manifest_routing(
            "missing_graph_linkage",
            "manifest routing requires active graph linkage",
        )
    return None


def _manifest_fact_blocker(fact: Any) -> ManifestReworkRoutingResult | None:
    if _optional_ref_value(getattr(fact, "plan_ref", None)) is None:
        return _blocked_manifest_routing(
            "missing_plan_ref",
            "blackbox action execution fact is missing plan_ref",
        )
    if _optional_ref_value(getattr(fact, "fact_id", None)) is None:
        return _blocked_manifest_routing(
            "missing_fact_ref",
            "blackbox action execution fact is missing fact_id",
        )
    if not _required_text(getattr(fact, "action_id", None)):
        return _blocked_manifest_routing(
            "missing_action_id",
            "blackbox action execution fact is missing action_id",
        )
    if not getattr(fact, "acceptance_refs", ()):
        return _blocked_manifest_routing(
            "missing_fact_acceptance_refs",
            "blackbox action execution fact is missing acceptance refs",
        )
    return None


def _blocked_manifest_routing(reason_code: str, message: str) -> ManifestReworkRoutingResult:
    return ManifestReworkRoutingResult(
        status=ManifestReworkRoutingStatus.BLOCKED_OR_ESCALATED,
        blocked_reason_code=reason_code,
        blocked_message=message,
    )


def _blackbox_fact_failed(fact: Any) -> bool:
    http_status = getattr(fact, "http_status", None)
    if http_status is not None:
        return not (200 <= http_status < 300)
    exit_code = getattr(fact, "exit_code", None)
    if exit_code is not None:
        return exit_code != 0
    return True


def _manifest_observed_context(fact: Any) -> dict[str, Any]:
    observed: dict[str, Any] = {
        "fact_id": _optional_ref_value(getattr(fact, "fact_id", None)),
        "plan_ref": _optional_ref_value(getattr(fact, "plan_ref", None)),
        "action_id": getattr(fact, "action_id", None),
        "action_kind": _optional_ref_value(getattr(fact, "action_kind", None)),
        "input_refs": tuple(
            _optional_ref_value(getattr(input_ref_hash, "input_ref", None))
            for input_ref_hash in getattr(fact, "input_ref_hashes", ())
        ),
        "exit_code": getattr(fact, "exit_code", None),
        "http_status": getattr(fact, "http_status", None),
        "status_text": getattr(fact, "status_text", None),
        "body_ref": getattr(fact, "body_ref", None),
        "artifact_refs": tuple(getattr(fact, "artifact_refs", ())),
        "verification_run_ref": _optional_ref_value(getattr(fact, "verification_run_ref", None)),
        "package_contract_ref": _optional_ref_value(getattr(fact, "package_contract_ref", None)),
    }
    return {key: value for key, value in observed.items() if value not in (None, (), "")}


def _optional_ref_value(value: Any) -> str | None:
    if value is None:
        return None
    ref_value = getattr(value, "value", value)
    text = str(ref_value).strip()
    return text or None


def _required_ref_value(value: Any) -> str:
    ref_value = _optional_ref_value(value)
    if ref_value is None:
        raise ValueError("required ref value is missing")
    return ref_value


def _required_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return text


def _safe_ref_fragment(value: str) -> str:
    return value.replace(":", ".").replace("/", ".").replace("\\", ".").replace(" ", "-")


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
    issue_code = _issue_code_from_text(
        blocker.message,
        related_ref,
        ReworkIssueCode.CLOSEOUT_GATE_FAILURE,
    )
    domains = _domains_for_issue_code(issue_code)
    if issue_code is ReworkIssueCode.CLOSEOUT_GATE_FAILURE and _is_closeout_audit_blocker(blocker):
        domains = (ReworkSuspectedDomain.CLOSEOUT_AUDIT,)
    blocker_ref = blocker.blocker_id.value if blocker.blocker_id else related_ref
    return _issue(
        issue_id=f"rework-issue.closeout.{blocker_ref}",
        blocker_refs=(BlockerRef(value=blocker_ref),),
        issue_code=issue_code,
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
    advisory_context: Mapping[str, Any] | None = None,
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
        advisory_context=dict(advisory_context or {}),
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
    if _describes_run_manifest_drift(text):
        return ReworkIssueCode.RUN_MANIFEST_ERROR
    if "shape" in text or "book.title" in text or "$.title" in text:
        return ReworkIssueCode.PROBE_RESPONSE_SHAPE_MISMATCH
    if "env" in text or "environment" in text:
        return ReworkIssueCode.ENV_BINDING_NOT_CONVERGED
    if "old acceptance" in text or "ac-tiny" in text:
        return ReworkIssueCode.FINAL_EVIDENCE_OLD_ACCEPTANCE_REFS
    if "old run" in text:
        return ReworkIssueCode.CLOSEOUT_AUDIT_OLD_RUN_REFS
    return default


def _describes_run_manifest_drift(text: str) -> bool:
    drift_tokens = (
        "run manifest",
        "run_manifest",
        "manifest",
        "readiness",
        "unsupported runmanifest",
    )
    api_or_shape_tokens = (
        "api",
        "response-shape",
        "response shape",
        "status code",
        "http",
        "json",
    )
    if any(token in text for token in drift_tokens):
        return True
    return "drift" in text and any(token in text for token in api_or_shape_tokens)


def _domains_for_issue_code(issue_code: ReworkIssueCode) -> tuple[ReworkSuspectedDomain, ...]:
    if issue_code is ReworkIssueCode.RUN_MANIFEST_ERROR:
        return (
            ReworkSuspectedDomain.RUN_ENV,
            ReworkSuspectedDomain.PROBE,
            ReworkSuspectedDomain.IMPLEMENTATION,
        )
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
    "ManifestReworkRoutingResult",
    "ManifestReworkRoutingStatus",
    "project_checker_verdict_blockers",
    "project_closeout_gate_blockers",
    "project_final_evidence_table_blockers",
    "project_v2_090k_failure_summary",
    "route_manifest_blackbox_facts",
]
