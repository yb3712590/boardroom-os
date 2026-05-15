from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from boardroom_os.events.record import EventRecord
from boardroom_os.events.types import EventPayloadRef, EventType
from boardroom_os.graph.ticket import TicketCreatedPayload, TicketGraph, TicketId, TicketNode, TicketStatus
from boardroom_os.reducers.errors import TicketReducerError


class TicketRefPayload(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    ticket_id: TicketId


class _BlockingIssueFields(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    blocking_issue_refs: tuple[str, ...] = ()

    @field_validator("blocking_issue_refs")
    @classmethod
    def _reject_blank_blocking_issue_refs(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized_values = tuple(value.strip() for value in values)
        if any(not value for value in normalized_values):
            raise ValueError("blocking issue refs must not be empty")
        return normalized_values


class TicketCheckSnapshot(_BlockingIssueFields):
    ticket_id: TicketId
    checker_approved: bool


class TicketCompletionSnapshot(_BlockingIssueFields):
    ticket_id: TicketId
    provider_attempt_count: int = Field(ge=0)
    evidence_complete: bool
    checker_approved: bool

    @model_validator(mode="after")
    def _require_completion_gate_passed(self) -> "TicketCompletionSnapshot":
        if not self.evidence_complete:
            raise ValueError("evidence must be complete")
        if not self.checker_approved:
            raise ValueError("checker must be approved")
        return self


class TicketReducerPayloadResolver(Protocol):
    def resolve_ticket_created(
        self,
        payload_ref: EventPayloadRef,
    ) -> TicketCreatedPayload: ...

    def resolve_ticket_ref(
        self,
        payload_ref: EventPayloadRef,
    ) -> TicketRefPayload: ...

    def resolve_ticket_check(
        self,
        payload_ref: EventPayloadRef,
    ) -> TicketCheckSnapshot: ...

    def resolve_ticket_completion(
        self,
        payload_ref: EventPayloadRef,
    ) -> TicketCompletionSnapshot: ...


class TicketReducer:
    def __init__(self, payload_resolver: TicketReducerPayloadResolver) -> None:
        self._payload_resolver = payload_resolver

    def reduce(self, events: tuple[EventRecord, ...]) -> TicketGraph:
        if not events:
            raise TicketReducerError("events must not be empty")

        nodes_by_id: dict[TicketId, TicketNode] = {}
        tickets_with_checker_blockers: set[TicketId] = set()
        latest_graph_version = 0
        for event in sorted(events, key=lambda item: item.graph_version):
            latest_graph_version = event.graph_version
            payload_ref = event.payload_refs[0]

            if event.event_type is EventType.TICKET_CREATED:
                payload = self._resolve_created_payload(payload_ref)
                if payload.ticket_id in nodes_by_id:
                    raise TicketReducerError(f"ticket already exists: {payload.ticket_id.value}")
                nodes_by_id[payload.ticket_id] = TicketNode.from_created_payload(payload)
                continue

            if event.event_type in {
                EventType.TICKET_LEASED,
                EventType.WORK_PRODUCT_SUBMITTED,
            }:
                payload = self._resolve_ticket_ref(payload_ref)
                self._require_existing_ticket(nodes_by_id, payload.ticket_id, event.event_type)
                continue

            if event.event_type is EventType.TICKET_CHECKED:
                check = self._resolve_check_snapshot(payload_ref)
                existing = self._require_existing_ticket(nodes_by_id, check.ticket_id, event.event_type)
                if not check.checker_approved or check.blocking_issue_refs:
                    tickets_with_checker_blockers.add(check.ticket_id)
                else:
                    tickets_with_checker_blockers.discard(check.ticket_id)
                    if existing.status is TicketStatus.BLOCKED:
                        nodes_by_id[check.ticket_id] = existing.model_copy(
                            update={"status": TicketStatus.READY}
                        )
                continue

            if event.event_type is EventType.TICKET_REWORKED:
                payload = self._resolve_ticket_ref(payload_ref)
                existing = self._require_existing_ticket(nodes_by_id, payload.ticket_id, event.event_type)
                if payload.ticket_id not in tickets_with_checker_blockers:
                    raise TicketReducerError("rework requires checker blocker")
                nodes_by_id[payload.ticket_id] = existing.model_copy(
                    update={"status": TicketStatus.BLOCKED}
                )
                continue

            if event.event_type is EventType.TICKET_COMPLETED:
                completion = self._resolve_completion_snapshot(payload_ref)
                self._reject_executor_completion(event)
                existing = self._require_existing_ticket(
                    nodes_by_id,
                    completion.ticket_id,
                    event.event_type,
                )
                if completion.ticket_id in tickets_with_checker_blockers:
                    raise TicketReducerError("open checker blockers must be cleared before completion")
                if existing.status is TicketStatus.BLOCKED:
                    raise TicketReducerError(
                        f"blocked ticket cannot be completed: {completion.ticket_id.value}"
                    )
                if completion.provider_attempt_count == 0:
                    raise TicketReducerError("provider attempt count must be greater than zero")
                if completion.blocking_issue_refs:
                    raise TicketReducerError("blocking issues must be cleared before completion")
                nodes_by_id[completion.ticket_id] = existing.model_copy(
                    update={
                        "status": TicketStatus.COMPLETED,
                        "attempt_count": completion.provider_attempt_count,
                    }
                )
                continue

            if event.event_type is EventType.TICKET_BLOCKED:
                raise TicketReducerError(
                    f"unsupported ticket transition: {event.event_type.value}"
                )

        try:
            return TicketGraph.from_nodes(
                graph_version=latest_graph_version,
                nodes=tuple(nodes_by_id.values()),
            )
        except ValueError as error:
            raise TicketReducerError(str(error)) from error

    def _resolve_created_payload(self, payload_ref: EventPayloadRef) -> TicketCreatedPayload:
        try:
            return self._payload_resolver.resolve_ticket_created(payload_ref)
        except Exception as error:
            raise TicketReducerError(
                f"payload_ref could not be resolved: {payload_ref.value}"
            ) from error

    def _resolve_ticket_ref(self, payload_ref: EventPayloadRef) -> TicketRefPayload:
        try:
            return self._payload_resolver.resolve_ticket_ref(payload_ref)
        except Exception as error:
            raise TicketReducerError(
                f"ticket payload_ref could not be resolved: {payload_ref.value}"
            ) from error

    def _resolve_check_snapshot(self, payload_ref: EventPayloadRef) -> TicketCheckSnapshot:
        try:
            return self._payload_resolver.resolve_ticket_check(payload_ref)
        except Exception as error:
            raise TicketReducerError(
                f"check payload_ref could not be resolved: {payload_ref.value}"
            ) from error

    def _resolve_completion_snapshot(
        self,
        payload_ref: EventPayloadRef,
    ) -> TicketCompletionSnapshot:
        try:
            return self._payload_resolver.resolve_ticket_completion(payload_ref)
        except TicketReducerError:
            raise
        except Exception as error:
            raise TicketReducerError(
                f"completion payload_ref could not be resolved: {payload_ref.value}"
            ) from error

    def _require_existing_ticket(
        self,
        nodes_by_id: dict[TicketId, TicketNode],
        ticket_id: TicketId,
        event_type: EventType,
    ) -> TicketNode:
        existing = nodes_by_id.get(ticket_id)
        if existing is None:
            raise TicketReducerError(
                f"ticket must exist before {event_type.value}: {ticket_id.value}"
            )
        return existing

    def _reject_executor_completion(self, event: EventRecord) -> None:
        actor = event.actor_ref.value
        if actor.startswith("executor:") or actor.startswith("runtime:"):
            raise TicketReducerError("executor/runtime cannot complete ticket")
