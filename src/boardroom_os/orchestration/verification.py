from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator

from boardroom_os.agents.categories import RoleCategory
from boardroom_os.agents.seat import SeatDemand
from boardroom_os.contracts.types import AcceptanceRef, EvidenceObligationRef, SourceSurfaceRef
from boardroom_os.execution.package import ContextRef
from boardroom_os.graph.ticket import (
    VERIFY_BLACKBOX_CAPABILITY,
    VERIFY_BLACKBOX_PURPOSE,
    TicketCreatedPayload,
    TicketId,
)


class VerificationMilestoneRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    ticket_id: TicketId
    raw_manifest_context_ref: ContextRef
    skeleton_summary_ref: ContextRef
    acceptance_refs: tuple[AcceptanceRef, ...]
    acceptance_contract_ref: ContextRef
    package_contract_ref: ContextRef
    source_surface_refs: tuple[SourceSurfaceRef, ...]
    evidence_obligation_refs: tuple[EvidenceObligationRef, ...]
    workspace_context_refs: tuple[ContextRef, ...] = ()
    project_doc_refs: tuple[ContextRef, ...] = ()
    observed_failure_refs: tuple[ContextRef, ...] = ()

    @field_validator("acceptance_refs", "source_surface_refs", "evidence_obligation_refs")
    @classmethod
    def _reject_empty_required_refs(cls, values: tuple[object, ...]) -> tuple[object, ...]:
        if not values:
            raise ValueError("verify-blackbox request refs must not be empty")
        return values


class VerifyBlackboxTicketIntent(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    ticket_id: TicketId
    raw_manifest_context_ref: ContextRef
    skeleton_summary_ref: ContextRef
    acceptance_refs: tuple[AcceptanceRef, ...]
    acceptance_contract_ref: ContextRef
    package_contract_ref: ContextRef
    source_surface_refs: tuple[SourceSurfaceRef, ...]
    evidence_obligation_refs: tuple[EvidenceObligationRef, ...]
    allowed_read_refs: tuple[ContextRef, ...]

    @classmethod
    def from_request(
        cls,
        request: VerificationMilestoneRequest,
    ) -> "VerifyBlackboxTicketIntent":
        allowed_read_refs = _dedupe_context_refs(
            (
                request.raw_manifest_context_ref,
                request.skeleton_summary_ref,
                request.acceptance_contract_ref,
                request.package_contract_ref,
                *request.workspace_context_refs,
                *request.project_doc_refs,
                *(
                    ContextRef(value=acceptance_ref.value)
                    for acceptance_ref in request.acceptance_refs
                ),
                *(
                    ContextRef(value=source_surface_ref.value)
                    for source_surface_ref in request.source_surface_refs
                ),
                *request.observed_failure_refs,
            )
        )
        return cls(
            ticket_id=request.ticket_id,
            raw_manifest_context_ref=request.raw_manifest_context_ref,
            skeleton_summary_ref=request.skeleton_summary_ref,
            acceptance_refs=request.acceptance_refs,
            acceptance_contract_ref=request.acceptance_contract_ref,
            package_contract_ref=request.package_contract_ref,
            source_surface_refs=request.source_surface_refs,
            evidence_obligation_refs=request.evidence_obligation_refs,
            allowed_read_refs=allowed_read_refs,
        )

    def to_ticket_created_payload(self) -> TicketCreatedPayload:
        return TicketCreatedPayload(
            ticket_id=self.ticket_id,
            purpose=VERIFY_BLACKBOX_PURPOSE,
            seat_demand=SeatDemand(
                required_role_category=RoleCategory.VERIFICATION,
                required_capability_tags=(VERIFY_BLACKBOX_CAPABILITY,),
            ),
            depends_on=(),
            acceptance_refs=tuple(ref.value for ref in self.acceptance_refs),
            source_surface_refs=tuple(ref.value for ref in self.source_surface_refs),
            evidence_obligations=tuple(ref.value for ref in self.evidence_obligation_refs),
            allowed_read_refs=tuple(ref.value for ref in self.allowed_read_refs),
            allowed_write_set=(),
            attempt_count=0,
        )


class VerificationOutcomeProjection(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: Literal["pending", "passed", "rework_required", "blocked_or_escalated"]
    ticket_ref: TicketId
    context_refs: tuple[ContextRef, ...]


def _dedupe_context_refs(refs: tuple[ContextRef, ...]) -> tuple[ContextRef, ...]:
    deduped: list[ContextRef] = []
    seen_values: set[str] = set()
    for ref in refs:
        if ref.value in seen_values:
            continue
        deduped.append(ref)
        seen_values.add(ref.value)
    return tuple(deduped)


__all__ = [
    "VERIFY_BLACKBOX_CAPABILITY",
    "VERIFY_BLACKBOX_PURPOSE",
    "VerificationMilestoneRequest",
    "VerificationOutcomeProjection",
    "VerifyBlackboxTicketIntent",
]
