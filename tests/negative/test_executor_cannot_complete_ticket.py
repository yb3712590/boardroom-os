from datetime import UTC, datetime

import pytest

from boardroom_os.agents.seat import RoleCategory, SeatDemand
from boardroom_os.agents.skills import CapabilityTag
from boardroom_os.events.record import EventRecord
from boardroom_os.events.types import (
    ActorRef,
    EventId,
    EventPayloadRef,
    EventType,
    ProjectRef,
)
from boardroom_os.graph.ticket import TicketCreatedPayload, TicketId
from boardroom_os.reducers.errors import TicketReducerError
from boardroom_os.reducers.ticket_reducer import (
    TicketCompletionSnapshot,
    TicketReducer,
    TicketReducerPayloadResolver,
)

BASE_TIMESTAMP = datetime(2026, 5, 16, 9, 30, tzinfo=UTC)


class InMemoryTicketReducerPayloadResolver(TicketReducerPayloadResolver):
    def resolve_ticket_created(self, payload_ref: EventPayloadRef) -> TicketCreatedPayload:
        return TicketCreatedPayload(
            ticket_id=TicketId(value="ticket-backend-api"),
            purpose="Implement backend API surface",
            seat_demand=SeatDemand(
                required_role_category=RoleCategory.IMPLEMENTATION,
                required_capability_tags=(
                    CapabilityTag(value="task.implementation"),
                    CapabilityTag(value="surface.backend"),
                ),
            ),
            acceptance_refs=("AC-BOOK-API-STATE-001",),
            source_surface_refs=("surface-backend-api",),
            evidence_obligations=("obligation-api-test-run",),
            allowed_write_set=("10-project/backend/**",),
            attempt_count=0,
        )

    def resolve_ticket_completion(
        self, payload_ref: EventPayloadRef
    ) -> TicketCompletionSnapshot:
        return TicketCompletionSnapshot(
            ticket_id=TicketId(value="ticket-backend-api"),
            provider_attempt_count=1,
            evidence_complete=True,
            checker_approved=True,
            blocking_issue_refs=(),
        )


def _event(
    *,
    event_id: str,
    event_type: EventType,
    actor_ref: str,
    graph_version: int,
) -> EventRecord:
    return EventRecord(
        event_id=EventId(value=event_id),
        event_type=event_type,
        project_ref=ProjectRef(value="project-tiny-fullstack"),
        actor_ref=ActorRef(value=actor_ref),
        timestamp=BASE_TIMESTAMP,
        graph_version=graph_version,
        payload_refs=(EventPayloadRef(value=f"payload:{event_id}"),),
    )


def test_executor_cannot_emit_ticket_completed_event() -> None:
    created = _event(
        event_id="ticket-backend-api-created",
        event_type=EventType.TICKET_CREATED,
        actor_ref="seat-architect",
        graph_version=1,
    )
    completed = _event(
        event_id="ticket-backend-api-completed",
        event_type=EventType.TICKET_COMPLETED,
        actor_ref="executor:local",
        graph_version=2,
    )

    with pytest.raises(TicketReducerError, match="executor/runtime cannot complete ticket"):
        TicketReducer(InMemoryTicketReducerPayloadResolver()).reduce((created, completed))
