from __future__ import annotations

from datetime import datetime
from typing import Any, Iterable

from pydantic import BaseModel, ConfigDict, field_validator

from boardroom_os.contracts.types import AcceptanceRef, ContractId, EvidenceObligationRef, SourceSurfaceRef
from boardroom_os.rework.model import (
    GraphPatchApprovalSet,
    GraphPatchApprovalSetId,
    GraphPatchApprovalStatus,
    GraphPatchReview,
    GraphPatchReviewDomain,
    GraphPatchReviewStatus,
    ReworkIssue,
    ReworkIssueCode,
    ReworkSuspectedDomain,
    TicketGraphPatch,
    TicketGraphPatchOperation,
    canonical_rework_hash,
)


class TicketGraphPatchBoundaryError(ValueError):
    pass


class RequiredReviewDomainInput(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    issues: tuple[ReworkIssue, ...]
    operations: tuple[TicketGraphPatchOperation, ...]

    @field_validator("issues", "operations")
    @classmethod
    def _reject_empty(cls, values: tuple[Any, ...], info: Any) -> tuple[Any, ...]:
        if not values:
            raise ValueError(f"{info.field_name} must not be empty")
        return values


def infer_required_review_domains(input: RequiredReviewDomainInput) -> tuple[GraphPatchReviewDomain, ...]:
    domains: list[GraphPatchReviewDomain] = [
        GraphPatchReviewDomain.PLANNING,
        GraphPatchReviewDomain.STRUCTURAL,
        GraphPatchReviewDomain.BLOCKER_COVERAGE,
    ]
    issue_codes = {issue.issue_code for issue in input.issues}
    suspected_domains = {
        suspected_domain
        for issue in input.issues
        for suspected_domain in issue.suspected_domains
    }

    if issue_codes & {
        ReworkIssueCode.PROBE_RESPONSE_SHAPE_MISMATCH,
        ReworkIssueCode.CONTRACT_MISMATCH,
    } or ReworkSuspectedDomain.PROBE in suspected_domains:
        domains.append(GraphPatchReviewDomain.BEHAVIORAL_PROBE)
    if issue_codes & {
        ReworkIssueCode.ENV_BINDING_NOT_CONVERGED,
        ReworkIssueCode.RUN_MANIFEST_ERROR,
        ReworkIssueCode.RUN_MANIFEST_MISMATCH,
    } or ReworkSuspectedDomain.RUN_ENV in suspected_domains:
        domains.append(GraphPatchReviewDomain.RUN_ENV_READINESS)
    if issue_codes & {
        ReworkIssueCode.CLOSEOUT_AUDIT_OLD_RUN_REFS,
        ReworkIssueCode.CLOSEOUT_GATE_FAILURE,
    } or ReworkSuspectedDomain.CLOSEOUT_AUDIT in suspected_domains:
        domains.append(GraphPatchReviewDomain.CLOSEOUT_FACT_CHAIN)
    return tuple(domains)


def _values(values: Iterable[Any]) -> set[str]:
    return {getattr(value, "value", str(value)) for value in values}


def _require_subset(kind: str, refs: Iterable[Any], active_refs: Iterable[Any]) -> None:
    active = _values(active_refs)
    for ref in refs:
        value = getattr(ref, "value", str(ref))
        if value not in active:
            raise TicketGraphPatchBoundaryError(f"unknown {kind}: {value}")


def validate_ticket_graph_patch_scope(
    patch: TicketGraphPatch,
    *,
    active_acceptance_refs: tuple[AcceptanceRef, ...],
    active_source_surface_refs: tuple[SourceSurfaceRef, ...],
    active_evidence_obligation_refs: tuple[EvidenceObligationRef, ...],
    active_contract_refs: tuple[ContractId, ...],
) -> TicketGraphPatch:
    _require_subset("affected_contract_ref", patch.affected_contract_refs, active_contract_refs)
    _require_subset("affected_source_surface_ref", patch.affected_source_surface_refs, active_source_surface_refs)

    affected_tickets = set(patch.affected_ticket_refs)
    for operation in patch.operations:
        _require_subset("acceptance_ref", operation.acceptance_refs, active_acceptance_refs)
        _require_subset("source_surface_ref", operation.source_surface_refs, active_source_surface_refs)
        _require_subset("evidence_obligation_ref", operation.evidence_obligation_refs, active_evidence_obligation_refs)
        for ticket_ref in operation.target_ticket_refs:
            if ticket_ref not in affected_tickets:
                raise TicketGraphPatchBoundaryError(f"operation target ticket is not affected by patch: {ticket_ref.value}")

    required = {
        GraphPatchReviewDomain.PLANNING,
        GraphPatchReviewDomain.STRUCTURAL,
        GraphPatchReviewDomain.BLOCKER_COVERAGE,
    }
    declared = set(patch.required_review_domains)
    missing = required - declared
    if missing:
        names = ", ".join(sorted(domain.value for domain in missing))
        raise TicketGraphPatchBoundaryError(f"missing required review domain: {names}")
    return patch


def derive_ticket_graph_patch_hash(patch_without_hash: TicketGraphPatch) -> str:
    normalized_patch = patch_without_hash.model_copy(update={"patch_hash": "sha256:pending"})
    return f"sha256:{canonical_rework_hash(normalized_patch)}"


def build_graph_patch_approval_set(
    patch: TicketGraphPatch,
    reviews: tuple[GraphPatchReview, ...],
    *,
    computed_at: datetime,
) -> GraphPatchApprovalSet:
    if computed_at.tzinfo is None or computed_at.utcoffset() is None:
        raise TicketGraphPatchBoundaryError("computed_at must be timezone-aware")
    required = set(patch.required_review_domains)
    approved = {
        review.review_domain
        for review in reviews
        if review.ticket_graph_patch_ref == patch.ticket_graph_patch_id
        and review.status is GraphPatchReviewStatus.APPROVED
    }
    status = (
        GraphPatchApprovalStatus.READY_TO_COMMIT
        if required.issubset(approved)
        else GraphPatchApprovalStatus.INCOMPLETE
    )
    patch_hash = derive_ticket_graph_patch_hash(patch)
    return GraphPatchApprovalSet(
        approval_set_id=GraphPatchApprovalSetId(value=f"graph-patch-approval.{patch_hash.removeprefix('sha256:')[:16]}"),
        ticket_graph_patch_ref=patch.ticket_graph_patch_id,
        required_domains=patch.required_review_domains,
        reviews=reviews,
        status=status,
        computed_at=computed_at,
    )


__all__ = [
    "RequiredReviewDomainInput",
    "TicketGraphPatchBoundaryError",
    "build_graph_patch_approval_set",
    "derive_ticket_graph_patch_hash",
    "infer_required_review_domains",
    "validate_ticket_graph_patch_scope",
]
