from __future__ import annotations

from enum import StrEnum
from typing import Protocol, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from boardroom_os.events.record import EventRecord
from boardroom_os.events.types import EventId, EventPayloadRef, EventType, ProjectRef
from boardroom_os.graph.ticket import TicketCreatedPayload, TicketId
from boardroom_os.rework.model import (
    BlockerRef,
    GraphPatchApprovalSet,
    GraphPatchApprovalStatus,
    GraphPatchReview,
    GraphPatchReviewDomain,
    GraphPatchReviewStatus,
    ReworkAttempt,
    ReworkAttemptId,
    ReworkCycleId,
    ReworkCycleStatus,
    ReworkOutcome,
    ReworkOutcomeId,
    ReworkOutcomeStatus,
    ReworkPlan,
    ReworkPlanId,
    ReworkRequest,
    ReworkRequestId,
    ReworkTerminationDecision,
    ReworkTerminationDecisionId,
    TicketGraphPatch,
    TicketGraphPatchId,
)


class ReworkReducerError(ValueError):
    pass


class ReworkTerminalStatus(StrEnum):
    OPEN = "open"
    ACCEPTED = "accepted"
    ESCALATED = "escalated"
    EXHAUSTED = "exhausted"


class ReworkRequestPayload(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    request: ReworkRequest


class ReworkPlanPayload(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    request_ref: ReworkRequestId
    plan: ReworkPlan
    patch: TicketGraphPatch

    @model_validator(mode="after")
    def _validate_plan_patch_binding(self) -> Self:
        if self.plan.rework_request_id != self.request_ref:
            raise ReworkReducerError("plan request_ref mismatch")
        if self.plan.rework_plan_id != self.patch.proposed_by_plan_ref:
            raise ReworkReducerError("patch proposed_by_plan_ref mismatch")
        if self.plan.ticket_graph_patch_ref != self.patch.ticket_graph_patch_id:
            raise ReworkReducerError("plan ticket_graph_patch_ref mismatch")
        return self


class GraphPatchReviewPayload(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    patch_ref: TicketGraphPatchId
    review: GraphPatchReview

    @model_validator(mode="after")
    def _validate_review_patch_binding(self) -> Self:
        if self.review.ticket_graph_patch_ref != self.patch_ref:
            raise ReworkReducerError("graph patch review ref mismatch")
        return self


class GraphPatchApprovalPayload(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    patch_ref: TicketGraphPatchId
    approval_set: GraphPatchApprovalSet

    @model_validator(mode="after")
    def _validate_approval_patch_binding(self) -> Self:
        if self.approval_set.ticket_graph_patch_ref != self.patch_ref:
            raise ReworkReducerError("graph patch approval ref mismatch")
        return self


class ReworkAttemptPayload(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    attempt: ReworkAttempt


class ReworkReviewPayload(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    outcome: ReworkOutcome


class ReworkTerminalPayload(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    cycle_id: ReworkCycleId | str
    outcome_ref: ReworkOutcomeId | None = None
    termination_decision_ref: ReworkTerminationDecisionId | None = None
    accepted_blocker_refs: tuple[BlockerRef, ...] = ()
    remaining_blocker_refs: tuple[BlockerRef, ...] = ()
    termination_decision: ReworkTerminationDecision | None = None


class ReworkReducerPayloadResolver(Protocol):
    def resolve_rework_request(self, payload_ref: EventPayloadRef) -> ReworkRequestPayload: ...

    def resolve_rework_plan(self, payload_ref: EventPayloadRef) -> ReworkPlanPayload: ...

    def resolve_graph_patch_review(self, payload_ref: EventPayloadRef) -> GraphPatchReviewPayload: ...

    def resolve_graph_patch_approval(self, payload_ref: EventPayloadRef) -> GraphPatchApprovalPayload: ...

    def resolve_rework_ticket_created(self, payload_ref: EventPayloadRef) -> TicketCreatedPayload: ...

    def resolve_rework_attempt(self, payload_ref: EventPayloadRef) -> ReworkAttemptPayload: ...

    def resolve_rework_review(self, payload_ref: EventPayloadRef) -> ReworkReviewPayload: ...

    def resolve_rework_terminal(self, payload_ref: EventPayloadRef) -> ReworkTerminalPayload: ...


class GraphPatchReviewGate:
    @staticmethod
    def evaluate(
        patch: TicketGraphPatch,
        approval_set: GraphPatchApprovalSet,
    ) -> GraphPatchApprovalSet:
        if approval_set.ticket_graph_patch_ref != patch.ticket_graph_patch_id:
            raise ReworkReducerError("approval set patch ref mismatch")

        required = set(patch.required_review_domains)
        declared = set(approval_set.required_domains)
        if required != declared:
            raise ReworkReducerError("approval set required domains must match patch")

        approved_domains: set[GraphPatchReviewDomain] = set()
        for review in approval_set.reviews:
            if review.ticket_graph_patch_ref != patch.ticket_graph_patch_id:
                raise ReworkReducerError("review patch ref mismatch")
            if review.review_domain not in required:
                raise ReworkReducerError("review domain is not required by patch")
            if review.status is not GraphPatchReviewStatus.APPROVED:
                raise ReworkReducerError("graph patch approval is not ready")
            approved_domains.add(review.review_domain)

        missing = required - approved_domains
        if missing:
            names = ", ".join(sorted(domain.value for domain in missing))
            raise ReworkReducerError(f"missing required review domain: {names}")

        if approval_set.status is not GraphPatchApprovalStatus.READY_TO_COMMIT:
            raise ReworkReducerError("graph patch approval is not ready")

        return approval_set


class ReworkProjection(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    project_ref: ProjectRef
    graph_version: int = Field(gt=0)
    cycle_id: ReworkCycleId | str
    status: ReworkCycleStatus
    terminal_status: ReworkTerminalStatus = ReworkTerminalStatus.OPEN
    request_ref: ReworkRequestId | None = None
    plan_ref: ReworkPlanId | None = None
    patch_ref: TicketGraphPatchId | None = None
    approval_set_ref: str | None = None
    rework_ticket_refs: tuple[TicketId, ...] = ()
    attempt_refs: tuple[ReworkAttemptId, ...] = ()
    outcome_refs: tuple[ReworkOutcomeId, ...] = ()
    accepted_blocker_refs: tuple[BlockerRef, ...] = ()
    remaining_blocker_refs: tuple[BlockerRef, ...] = ()
    committed_event_refs: tuple[EventId, ...] = ()
    checked_refs: tuple[str, ...] = ()

    @field_validator(
        "rework_ticket_refs",
        "attempt_refs",
        "outcome_refs",
        "accepted_blocker_refs",
        "remaining_blocker_refs",
        "committed_event_refs",
    )
    @classmethod
    def _reject_duplicate_refs(cls, values: tuple[object, ...]) -> tuple[object, ...]:
        raw = [getattr(value, "value", str(value)) for value in values]
        if len(raw) != len(set(raw)):
            raise ReworkReducerError("projection refs must be unique")
        return values


_GOVERNANCE_TERMINAL_EVENTS = {
    EventType.REWORK_ACCEPTED,
    EventType.REWORK_ESCALATED,
    EventType.REWORK_EXHAUSTED,
}


class ReworkReducer:
    def __init__(self, payload_resolver: ReworkReducerPayloadResolver) -> None:
        self._payload_resolver = payload_resolver

    def reduce(self, events: tuple[EventRecord, ...]) -> ReworkProjection:
        if not events:
            raise ReworkReducerError("events must not be empty")
        self._pre_scan_events(events)

        project_ref = events[0].project_ref
        graph_version = 0
        request: ReworkRequest | None = None
        plan: ReworkPlan | None = None
        patch: TicketGraphPatch | None = None
        approved = False
        approval_set_ref: str | None = None
        rework_ticket_refs: list[TicketId] = []
        attempt_refs: list[ReworkAttemptId] = []
        outcome_refs: list[ReworkOutcomeId] = []
        reviewed_outcome: ReworkOutcome | None = None
        accepted_blockers: tuple[BlockerRef, ...] = ()
        remaining_blockers: tuple[BlockerRef, ...] = ()
        committed_event_refs: list[EventId] = []
        checked_refs: list[str] = []
        status = ReworkCycleStatus.REQUESTED
        terminal_status = ReworkTerminalStatus.OPEN

        for event in events:
            self._require_single_payload_ref(event)
            graph_version = event.graph_version
            payload_ref = event.payload_refs[0]
            committed_event_refs.append(event.event_id)

            if event.event_type is EventType.REWORK_REQUESTED:
                if request is not None:
                    raise ReworkReducerError("duplicate rework request")
                payload = self._resolve_request(payload_ref)
                request = payload.request
                if request.active_graph_version >= event.graph_version:
                    raise ReworkReducerError("rework request active_graph_version must precede event graph_version")
                checked_refs.append(request.rework_request_id.value)
                status = ReworkCycleStatus.REQUESTED
                continue

            if event.event_type is EventType.REWORK_PLANNED:
                if request is None:
                    raise ReworkReducerError("request must exist before rework_planned")
                payload = self._resolve_plan(payload_ref)
                if payload.request_ref != request.rework_request_id:
                    raise ReworkReducerError("rework plan does not match request")
                if payload.plan.cycle_id != request.cycle_id:
                    raise ReworkReducerError("rework plan cycle_id does not match request")
                plan = payload.plan
                patch = payload.patch
                checked_refs.extend((plan.rework_plan_id.value, patch.ticket_graph_patch_id.value))
                status = ReworkCycleStatus.PLANNED
                continue

            if event.event_type is EventType.REWORK_GRAPH_PATCH_REVIEWED:
                if patch is None:
                    raise ReworkReducerError("patch must exist before graph patch review")
                payload = self._resolve_graph_patch_review(payload_ref)
                if payload.patch_ref != patch.ticket_graph_patch_id:
                    raise ReworkReducerError("graph patch review does not match planned patch")
                checked_refs.append(payload.review.graph_patch_review_id.value)
                continue

            if event.event_type is EventType.REWORK_GRAPH_PATCH_APPROVED:
                if patch is None:
                    raise ReworkReducerError("patch must exist before graph patch approval")
                payload = self._resolve_approval(payload_ref)
                if payload.patch_ref != patch.ticket_graph_patch_id:
                    raise ReworkReducerError("graph patch approval does not match planned patch")
                GraphPatchReviewGate.evaluate(patch, payload.approval_set)
                approved = True
                approval_set_ref = payload.approval_set.approval_set_id.value
                checked_refs.append(payload.approval_set.approval_set_id.value)
                continue

            if event.event_type is EventType.REWORK_TICKET_CREATED:
                if patch is None or not approved:
                    raise ReworkReducerError("approved patch required before rework ticket creation")
                ticket_payload = self._resolve_ticket(payload_ref)
                self._validate_rework_ticket_payload(ticket_payload, patch)
                rework_ticket_refs.append(ticket_payload.ticket_id)
                checked_refs.append(ticket_payload.ticket_id.value)
                status = ReworkCycleStatus.EXECUTING
                continue

            if event.event_type in {EventType.REWORK_ATTEMPT_STARTED, EventType.REWORK_ATTEMPT_SUBMITTED}:
                if not rework_ticket_refs:
                    raise ReworkReducerError("rework ticket must exist before attempt")
                payload = self._resolve_attempt(payload_ref)
                if payload.attempt.ticket_ref not in rework_ticket_refs:
                    raise ReworkReducerError("rework attempt ticket is not approved")
                if plan is not None and payload.attempt.rework_plan_ref != plan.rework_plan_id:
                    raise ReworkReducerError("rework attempt plan does not match approved plan")
                if event.event_type is EventType.REWORK_ATTEMPT_SUBMITTED:
                    attempt_refs.append(payload.attempt.rework_attempt_id)
                    status = ReworkCycleStatus.REVIEWING
                checked_refs.append(payload.attempt.rework_attempt_id.value)
                continue

            if event.event_type is EventType.REWORK_REVIEWED:
                if not attempt_refs:
                    raise ReworkReducerError("submitted attempt required before rework review")
                payload = self._resolve_review(payload_ref)
                if payload.outcome.rework_attempt_ref not in attempt_refs:
                    raise ReworkReducerError("rework outcome attempt is not submitted")
                reviewed_outcome = payload.outcome
                outcome_refs.append(payload.outcome.rework_outcome_id)
                remaining_blockers = payload.outcome.remaining_blocker_refs
                accepted_blockers = payload.outcome.accepted_blocker_refs
                checked_refs.append(payload.outcome.rework_outcome_id.value)
                continue

            if event.event_type in _GOVERNANCE_TERMINAL_EVENTS:
                self._reject_runtime_governance(event)
                if event.event_type is EventType.REWORK_ACCEPTED and not outcome_refs:
                    raise ReworkReducerError("reviewed outcome required before accepted")
                payload = self._resolve_terminal(payload_ref)
                if request is not None and payload.cycle_id != request.cycle_id:
                    raise ReworkReducerError("terminal payload cycle_id does not match request")
                if event.event_type is EventType.REWORK_ACCEPTED:
                    if reviewed_outcome is None:
                        raise ReworkReducerError("reviewed outcome required before accepted")
                    if reviewed_outcome.status is not ReworkOutcomeStatus.ACCEPTED:
                        raise ReworkReducerError("accepted rework requires accepted outcome")
                    if payload.outcome_ref != reviewed_outcome.rework_outcome_id:
                        raise ReworkReducerError("terminal outcome_ref does not match reviewed outcome")
                    if remaining_blockers:
                        raise ReworkReducerError("remaining blockers must be empty before accepted")
                    terminal_status = ReworkTerminalStatus.ACCEPTED
                    status = ReworkCycleStatus.ACCEPTED
                    accepted_blockers = payload.accepted_blocker_refs
                elif event.event_type is EventType.REWORK_ESCALATED:
                    if payload.termination_decision_ref is None and payload.termination_decision is None:
                        raise ReworkReducerError("escalated rework requires termination decision")
                    terminal_status = ReworkTerminalStatus.ESCALATED
                    status = ReworkCycleStatus.ESCALATED
                    remaining_blockers = payload.remaining_blocker_refs
                else:
                    if payload.termination_decision_ref is None and payload.termination_decision is None:
                        raise ReworkReducerError("exhausted rework requires termination decision")
                    terminal_status = ReworkTerminalStatus.EXHAUSTED
                    status = ReworkCycleStatus.EXHAUSTED
                    remaining_blockers = payload.remaining_blocker_refs
                continue

            raise ReworkReducerError(f"unsupported rework event type: {event.event_type.value}")

        if request is None:
            raise ReworkReducerError("rework request event is required")

        return ReworkProjection(
            project_ref=project_ref,
            graph_version=graph_version,
            cycle_id=request.cycle_id,
            status=status,
            terminal_status=terminal_status,
            request_ref=request.rework_request_id,
            plan_ref=plan.rework_plan_id if plan else None,
            patch_ref=patch.ticket_graph_patch_id if patch else None,
            approval_set_ref=approval_set_ref,
            rework_ticket_refs=tuple(dict.fromkeys(rework_ticket_refs)),
            attempt_refs=tuple(dict.fromkeys(attempt_refs)),
            outcome_refs=tuple(dict.fromkeys(outcome_refs)),
            accepted_blocker_refs=accepted_blockers,
            remaining_blocker_refs=remaining_blockers,
            committed_event_refs=tuple(committed_event_refs),
            checked_refs=tuple(dict.fromkeys(checked_refs)),
        )

    @staticmethod
    def _pre_scan_events(events: tuple[EventRecord, ...]) -> None:
        project_ref = events[0].project_ref
        previous_graph_version = 0
        terminal_seen = False
        for event in events:
            if event.project_ref != project_ref:
                raise ReworkReducerError("events must belong to one project_ref")
            if event.graph_version <= previous_graph_version:
                raise ReworkReducerError("events must be strictly increasing by graph_version")
            previous_graph_version = event.graph_version
            if terminal_seen:
                raise ReworkReducerError("events after rework terminal event are not allowed")
            if event.event_type in _GOVERNANCE_TERMINAL_EVENTS:
                terminal_seen = True

    @staticmethod
    def _require_single_payload_ref(event: EventRecord) -> None:
        if len(event.payload_refs) != 1:
            raise ReworkReducerError("event must have exactly one payload_ref")

    @staticmethod
    def _reject_runtime_governance(event: EventRecord) -> None:
        actor = event.actor_ref.value
        if actor.startswith(("runtime:", "executor:", "atomic-agent:")):
            raise ReworkReducerError("runtime/executor/atomic-agent cannot emit governance event")

    def _resolve_request(self, payload_ref: EventPayloadRef) -> ReworkRequestPayload:
        try:
            return self._payload_resolver.resolve_rework_request(payload_ref)
        except Exception as error:
            raise ReworkReducerError(f"rework request payload could not be resolved: {payload_ref.value}") from error

    def _resolve_plan(self, payload_ref: EventPayloadRef) -> ReworkPlanPayload:
        try:
            return self._payload_resolver.resolve_rework_plan(payload_ref)
        except Exception as error:
            raise ReworkReducerError(f"rework plan payload could not be resolved: {payload_ref.value}") from error

    def _resolve_graph_patch_review(self, payload_ref: EventPayloadRef) -> GraphPatchReviewPayload:
        try:
            return self._payload_resolver.resolve_graph_patch_review(payload_ref)
        except Exception as error:
            raise ReworkReducerError(f"graph patch review payload could not be resolved: {payload_ref.value}") from error

    def _resolve_approval(self, payload_ref: EventPayloadRef) -> GraphPatchApprovalPayload:
        try:
            return self._payload_resolver.resolve_graph_patch_approval(payload_ref)
        except Exception as error:
            raise ReworkReducerError(f"graph patch approval payload could not be resolved: {payload_ref.value}") from error

    def _resolve_ticket(self, payload_ref: EventPayloadRef) -> TicketCreatedPayload:
        try:
            return self._payload_resolver.resolve_rework_ticket_created(payload_ref)
        except Exception as error:
            raise ReworkReducerError(f"rework ticket payload could not be resolved: {payload_ref.value}") from error

    def _resolve_attempt(self, payload_ref: EventPayloadRef) -> ReworkAttemptPayload:
        try:
            return self._payload_resolver.resolve_rework_attempt(payload_ref)
        except Exception as error:
            raise ReworkReducerError(f"rework attempt payload could not be resolved: {payload_ref.value}") from error

    def _resolve_review(self, payload_ref: EventPayloadRef) -> ReworkReviewPayload:
        try:
            return self._payload_resolver.resolve_rework_review(payload_ref)
        except Exception as error:
            raise ReworkReducerError(f"rework review payload could not be resolved: {payload_ref.value}") from error

    def _resolve_terminal(self, payload_ref: EventPayloadRef) -> ReworkTerminalPayload:
        try:
            return self._payload_resolver.resolve_rework_terminal(payload_ref)
        except Exception as error:
            raise ReworkReducerError(f"rework terminal payload could not be resolved: {payload_ref.value}") from error

    @staticmethod
    def _validate_rework_ticket_payload(
        ticket_payload: TicketCreatedPayload,
        patch: TicketGraphPatch,
    ) -> None:
        affected_tickets = {ticket.value for ticket in patch.affected_ticket_refs}
        if ticket_payload.ticket_id.value not in affected_tickets:
            raise ReworkReducerError("rework ticket is not listed in graph patch")

        patch_acceptance = {ref.value for operation in patch.operations for ref in operation.acceptance_refs}
        patch_surfaces = {ref.value for operation in patch.operations for ref in operation.source_surface_refs}
        patch_obligations = {ref.value for operation in patch.operations for ref in operation.evidence_obligation_refs}

        if not set(ticket_payload.acceptance_refs).issubset(patch_acceptance):
            raise ReworkReducerError("rework ticket acceptance refs must be patch-bound")
        if not set(ticket_payload.source_surface_refs).issubset(patch_surfaces):
            raise ReworkReducerError("rework ticket source surfaces must be patch-bound")
        if not set(ticket_payload.evidence_obligations).issubset(patch_obligations):
            raise ReworkReducerError("rework ticket evidence obligations must be patch-bound")

        for path in ticket_payload.allowed_write_set:
            if path in {"**", "10-project/**", "20-evidence/**", "30-audit/**"}:
                raise ReworkReducerError("allowed_write_set expansion is not allowed")


def rework_ticket_payload_to_ticket_created_payload(
    payload: TicketCreatedPayload,
    *,
    patch: TicketGraphPatch,
) -> TicketCreatedPayload:
    ReworkReducer._validate_rework_ticket_payload(payload, patch)
    return payload
