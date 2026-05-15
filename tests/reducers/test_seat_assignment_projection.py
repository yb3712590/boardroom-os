from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from boardroom_os.events.log import InMemoryEventLog
from boardroom_os.events.record import EventRecord
from boardroom_os.events.types import (
    ActorRef,
    EventId,
    EventPayloadRef,
    EventType,
    ProjectRef,
)
from boardroom_os.graph.projection import TicketGraphProjector
from boardroom_os.graph.seat_assignment import (
    SeatAssignmentPayload,
    SeatAssignmentProjectionError,
    SeatAssignmentProjector,
    SeatDefinition,
    SeatRef,
    SeatStatus,
)
from boardroom_os.graph.ticket import TicketCreatedPayload, TicketId


BASE_TIMESTAMP = datetime(2026, 5, 16, 12, 0, tzinfo=UTC)


class InMemorySeatAssignmentPayloadResolver:
    def __init__(
        self,
        *,
        created_payloads: dict[str, TicketCreatedPayload] | None = None,
        assignment_payloads: dict[str, SeatAssignmentPayload] | None = None,
    ) -> None:
        self._created_payloads = created_payloads or {}
        self._assignment_payloads = assignment_payloads or {}
        self.created_calls: list[str] = []
        self.assignment_calls: list[str] = []

    def resolve_ticket_created(self, payload_ref: EventPayloadRef) -> TicketCreatedPayload:
        self.created_calls.append(payload_ref.value)
        return self._created_payloads[payload_ref.value]

    def resolve_seat_assignment(
        self, payload_ref: EventPayloadRef
    ) -> SeatAssignmentPayload:
        self.assignment_calls.append(payload_ref.value)
        return self._assignment_payloads[payload_ref.value]


def _seat_definition(**overrides: object) -> SeatDefinition:
    values = {
        "seat_ref": SeatRef(value="seat-worker-backend"),
        "role_ref": "role-worker",
        "capability_tags": ("implementation", "backend"),
        "model_execution_profile_ref": "model-profile-worker-opus",
        "status": SeatStatus.ACTIVE,
    }
    values.update(overrides)
    return SeatDefinition(**values)


def _ticket_payload(**overrides: object) -> TicketCreatedPayload:
    values = {
        "ticket_id": TicketId(value="ticket-backend-api"),
        "purpose": "Implement backend API surface",
        "owner_seat_ref": "seat-worker-backend",
        "depends_on": (),
        "acceptance_refs": ("AC-BOOK-API-STATE-001",),
        "source_surface_refs": ("surface-backend-api",),
        "evidence_obligations": ("obligation-api-test-run",),
        "allowed_read_refs": ("contract:tiny-fullstack",),
        "allowed_write_set": ("10-project/backend/**",),
        "attempt_count": 0,
    }
    values.update(overrides)
    return TicketCreatedPayload(**values)


def _seat_assignment_payload(**overrides: object) -> SeatAssignmentPayload:
    values = {
        "ticket_id": TicketId(value="ticket-backend-api"),
        "seat_ref": SeatRef(value="seat-worker-backend"),
        "required_capability_tags": ("implementation", "backend"),
    }
    values.update(overrides)
    return SeatAssignmentPayload(**values)


def _event(
    *,
    event_id: str,
    event_type: EventType,
    payload_ref: str,
    graph_version: int,
    actor_ref: str = "seat-architect",
    payload_refs: tuple[str, ...] | None = None,
) -> EventRecord:
    refs = payload_refs or (payload_ref,)
    return EventRecord(
        event_id=EventId(value=event_id),
        event_type=event_type,
        project_ref=ProjectRef(value="project-tiny-fullstack"),
        actor_ref=ActorRef(value=actor_ref),
        timestamp=BASE_TIMESTAMP,
        graph_version=graph_version,
        payload_refs=tuple(EventPayloadRef(value=ref) for ref in refs),
    )


def _ticket_created_event(
    *,
    graph_version: int = 1,
    payload_ref: str = "payload:ticket-backend-api-created",
) -> EventRecord:
    return _event(
        event_id=f"evt-ticket-created-{graph_version}-{payload_ref.rsplit(':', 1)[-1]}",
        event_type=EventType.TICKET_CREATED,
        payload_ref=payload_ref,
        graph_version=graph_version,
    )


def _seat_assigned_event(
    *,
    graph_version: int = 2,
    payload_ref: str = "payload:ticket-backend-api-seat-assigned",
    payload_refs: tuple[str, ...] | None = None,
) -> EventRecord:
    return _event(
        event_id=f"evt-seat-assigned-{graph_version}-{payload_ref.rsplit(':', 1)[-1]}",
        event_type=EventType.SEAT_ASSIGNED,
        payload_ref=payload_ref,
        graph_version=graph_version,
        actor_ref="seat-ceo",
        payload_refs=payload_refs,
    )


def _projector(
    *,
    seats: tuple[SeatDefinition, ...] = (_seat_definition(),),
    created_payloads: dict[str, TicketCreatedPayload] | None = None,
    assignment_payloads: dict[str, SeatAssignmentPayload] | None = None,
) -> SeatAssignmentProjector:
    resolver = InMemorySeatAssignmentPayloadResolver(
        created_payloads=created_payloads
        or {"payload:ticket-backend-api-created": _ticket_payload()},
        assignment_payloads=assignment_payloads
        or {"payload:ticket-backend-api-seat-assigned": _seat_assignment_payload()},
    )
    return SeatAssignmentProjector(
        ticket_projector=TicketGraphProjector(resolver),
        payload_resolver=resolver,
        seats=seats,
    )


def test_ticket_without_owner_seat_is_not_assignable() -> None:
    with pytest.raises(ValidationError):
        _ticket_payload(owner_seat_ref=" ")


def test_seat_definition_requires_model_execution_profile_ref() -> None:
    with pytest.raises(ValidationError):
        _seat_definition(model_execution_profile_ref=" ")


def test_ticket_without_seat_assignment_is_blocked_from_assignment_ready_queue() -> None:
    projector = _projector()

    graph = projector.project((_ticket_created_event(),))

    ticket_id = TicketId(value="ticket-backend-api")
    assert graph.ready_queue == ()
    assert graph.nodes[ticket_id].status.value == "blocked"
    assert graph.seat_assignments == {}
    assert graph.seat_blockers[ticket_id] == ("missing seat assignment",)



def test_seat_assignment_rejects_event_before_ticket_created() -> None:
    projector = _projector()

    with pytest.raises(SeatAssignmentProjectionError, match="before ticket created"):
        projector.project(
            (
                _seat_assigned_event(graph_version=1),
                _ticket_created_event(graph_version=2),
            )
        )



def test_seat_assignment_rejects_unknown_ticket_without_key_error() -> None:
    projector = _projector(
        assignment_payloads={
            "payload:ticket-backend-api-seat-assigned": _seat_assignment_payload(
                ticket_id=TicketId(value="ticket-missing")
            )
        }
    )

    with pytest.raises(SeatAssignmentProjectionError, match="ticket does not exist"):
        projector.project((_ticket_created_event(), _seat_assigned_event()))



def test_seat_assignment_rejects_multiple_payload_refs() -> None:
    projector = _projector()

    with pytest.raises(SeatAssignmentProjectionError, match="exactly one payload_ref"):
        projector.project(
            (
                _ticket_created_event(),
                _seat_assigned_event(
                    payload_refs=(
                        "payload:ticket-backend-api-seat-assigned",
                        "payload:unexpected-extra-seat-assigned",
                    )
                ),
            )
        )



def test_seat_assignment_blocks_unknown_seat() -> None:
    projector = _projector(seats=())

    graph = projector.project((_ticket_created_event(), _seat_assigned_event()))

    ticket_id = TicketId(value="ticket-backend-api")
    assert graph.ready_queue == ()
    assert graph.nodes[ticket_id].status.value == "blocked"
    assert graph.seat_assignments == {}
    assert graph.seat_blockers[ticket_id] == ("unknown seat: seat-worker-backend",)


def test_seat_assignment_blocks_capability_mismatch() -> None:
    projector = _projector(
        seats=(
            _seat_definition(
                capability_tags=("implementation", "frontend"),
            ),
        )
    )

    graph = projector.project((_ticket_created_event(), _seat_assigned_event()))

    ticket_id = TicketId(value="ticket-backend-api")
    assert graph.ready_queue == ()
    assert graph.nodes[ticket_id].status.value == "blocked"
    assert graph.seat_assignments == {}
    assert graph.seat_blockers[ticket_id] == ("seat missing capability tags: backend",)


def test_seat_assignment_blocks_inactive_seat() -> None:
    projector = _projector(seats=(_seat_definition(status=SeatStatus.INACTIVE),))

    graph = projector.project((_ticket_created_event(), _seat_assigned_event()))

    ticket_id = TicketId(value="ticket-backend-api")
    assert graph.ready_queue == ()
    assert graph.nodes[ticket_id].status.value == "blocked"
    assert graph.seat_assignments == {}
    assert graph.seat_blockers[ticket_id] == ("seat is not active: seat-worker-backend",)


def test_seat_assignment_requires_ticket_owner_to_match_assignment() -> None:
    projector = _projector(
        created_payloads={
            "payload:ticket-backend-api-created": _ticket_payload(
                owner_seat_ref="seat-worker-other"
            )
        }
    )

    graph = projector.project((_ticket_created_event(), _seat_assigned_event()))

    ticket_id = TicketId(value="ticket-backend-api")
    assert graph.ready_queue == ()
    assert graph.nodes[ticket_id].status.value == "blocked"
    assert graph.seat_assignments == {}
    assert graph.seat_blockers[ticket_id] == (
        "ticket owner seat mismatch: seat-worker-other != seat-worker-backend",
    )


def test_seat_assignment_allows_role_specific_seats_for_different_tickets() -> None:
    seats = (
        _seat_definition(
            seat_ref=SeatRef(value="seat-ceo"),
            role_ref="role-ceo",
            capability_tags=("governance",),
            model_execution_profile_ref="model-profile-ceo-opus",
        ),
        _seat_definition(
            seat_ref=SeatRef(value="seat-architect"),
            role_ref="role-architect",
            capability_tags=("architecture",),
            model_execution_profile_ref="model-profile-architect-opus",
        ),
        _seat_definition(
            seat_ref=SeatRef(value="seat-worker-backend"),
            role_ref="role-worker",
            capability_tags=("implementation", "backend"),
            model_execution_profile_ref="model-profile-worker-opus",
        ),
        _seat_definition(
            seat_ref=SeatRef(value="seat-checker"),
            role_ref="role-checker",
            capability_tags=("verification",),
            model_execution_profile_ref="model-profile-checker-opus",
        ),
    )
    created_payloads = {
        "payload:ticket-scope-created": _ticket_payload(
            ticket_id=TicketId(value="ticket-scope"),
            purpose="Clarify scope",
            owner_seat_ref="seat-ceo",
        ),
        "payload:ticket-architecture-created": _ticket_payload(
            ticket_id=TicketId(value="ticket-architecture"),
            purpose="Design architecture",
            owner_seat_ref="seat-architect",
        ),
        "payload:ticket-backend-api-created": _ticket_payload(),
        "payload:ticket-check-created": _ticket_payload(
            ticket_id=TicketId(value="ticket-check"),
            purpose="Check implementation evidence",
            owner_seat_ref="seat-checker",
        ),
    }
    assignment_payloads = {
        "payload:ticket-scope-seat-assigned": _seat_assignment_payload(
            ticket_id=TicketId(value="ticket-scope"),
            seat_ref=SeatRef(value="seat-ceo"),
            required_capability_tags=("governance",),
        ),
        "payload:ticket-architecture-seat-assigned": _seat_assignment_payload(
            ticket_id=TicketId(value="ticket-architecture"),
            seat_ref=SeatRef(value="seat-architect"),
            required_capability_tags=("architecture",),
        ),
        "payload:ticket-backend-api-seat-assigned": _seat_assignment_payload(),
        "payload:ticket-check-seat-assigned": _seat_assignment_payload(
            ticket_id=TicketId(value="ticket-check"),
            seat_ref=SeatRef(value="seat-checker"),
            required_capability_tags=("verification",),
        ),
    }
    resolver = InMemorySeatAssignmentPayloadResolver(
        created_payloads=created_payloads,
        assignment_payloads=assignment_payloads,
    )
    projector = SeatAssignmentProjector(
        ticket_projector=TicketGraphProjector(resolver),
        payload_resolver=resolver,
        seats=seats,
    )

    graph = projector.project(
        (
            _ticket_created_event(
                graph_version=1,
                payload_ref="payload:ticket-scope-created",
            ),
            _ticket_created_event(
                graph_version=2,
                payload_ref="payload:ticket-architecture-created",
            ),
            _ticket_created_event(graph_version=3),
            _ticket_created_event(
                graph_version=4,
                payload_ref="payload:ticket-check-created",
            ),
            _seat_assigned_event(
                graph_version=5,
                payload_ref="payload:ticket-scope-seat-assigned",
            ),
            _seat_assigned_event(
                graph_version=6,
                payload_ref="payload:ticket-architecture-seat-assigned",
            ),
            _seat_assigned_event(graph_version=7),
            _seat_assigned_event(
                graph_version=8,
                payload_ref="payload:ticket-check-seat-assigned",
            ),
        )
    )

    assert graph.ready_queue == (
        TicketId(value="ticket-scope"),
        TicketId(value="ticket-architecture"),
        TicketId(value="ticket-backend-api"),
        TicketId(value="ticket-check"),
    )
    assert graph.seat_assignments == {
        TicketId(value="ticket-scope"): SeatRef(value="seat-ceo"),
        TicketId(value="ticket-architecture"): SeatRef(value="seat-architect"),
        TicketId(value="ticket-backend-api"): SeatRef(value="seat-worker-backend"),
        TicketId(value="ticket-check"): SeatRef(value="seat-checker"),
    }
    assert graph.seat_blockers == {}

    event_log = InMemoryEventLog()
    for event in (
        _ticket_created_event(
            graph_version=1,
            payload_ref="payload:ticket-scope-created",
        ),
        _ticket_created_event(
            graph_version=2,
            payload_ref="payload:ticket-architecture-created",
        ),
        _ticket_created_event(graph_version=3),
        _ticket_created_event(
            graph_version=4,
            payload_ref="payload:ticket-check-created",
        ),
        _seat_assigned_event(
            graph_version=5,
            payload_ref="payload:ticket-scope-seat-assigned",
        ),
        _seat_assigned_event(
            graph_version=6,
            payload_ref="payload:ticket-architecture-seat-assigned",
        ),
        _seat_assigned_event(graph_version=7),
        _seat_assigned_event(
            graph_version=8,
            payload_ref="payload:ticket-check-seat-assigned",
        ),
    ):
        event_log.append(event)

    assert len(event_log.read(ProjectRef(value="project-tiny-fullstack"))) == 8
