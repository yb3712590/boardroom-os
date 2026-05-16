from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from boardroom_os.agents.profiles import ModelExecutionProfileId
from boardroom_os.agents.seat import (
    AgentSeat,
    AgentSeatRef,
    RoleCategory,
    SeatDemand,
    SeatLifecycleProjection,
    SeatLifecycleStatus,
)
from boardroom_os.agents.skills import CapabilityTag, RoleProfileId, SkillRef
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
)
from boardroom_os.graph.ticket import TicketCreatedPayload, TicketId


BASE_TIMESTAMP = datetime(2026, 5, 16, 12, 0, tzinfo=UTC)
PROJECT_REF = ProjectRef(value="project-tiny-fullstack")


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



def _agent_seat(**overrides: object) -> AgentSeat:
    values = {
        "seat_ref": AgentSeatRef(value="seat-worker-backend"),
        "actor_ref": ActorRef(value="actor.worker.backend"),
        "project_ref": PROJECT_REF,
        "role_profile_ref": RoleProfileId(value="role.implementation.backend"),
        "role_category": RoleCategory.IMPLEMENTATION,
        "capability_tags": (
            CapabilityTag(value="task.implementation"),
            CapabilityTag(value="surface.backend"),
        ),
        "model_execution_profile_ref": ModelExecutionProfileId(
            value="model.implementation.backend"
        ),
        "skill_refs": (SkillRef(value="skill.implementation.backend"),),
        "context_budget_tokens": 8192,
        "lifecycle_status": SeatLifecycleStatus.ACTIVE,
    }
    values.update(overrides)
    return AgentSeat(**values)



def _seat_projection(
    *,
    active_seats: tuple[AgentSeat, ...] | None = None,
    seats: tuple[AgentSeat, ...] | None = None,
    replacement_refs: dict[AgentSeatRef, AgentSeatRef] | None = None,
) -> SeatLifecycleProjection:
    active = active_seats if active_seats is not None else (_agent_seat(),)
    all_seats = seats if seats is not None else active
    return SeatLifecycleProjection(
        graph_version=1,
        seats={seat.seat_ref: seat for seat in all_seats},
        active_seats={seat.seat_ref: seat for seat in active},
        replacement_refs=replacement_refs or {},
    )



def _ticket_payload(**overrides: object) -> TicketCreatedPayload:
    values = {
        "ticket_id": TicketId(value="ticket-backend-api"),
        "purpose": "Implement backend API surface",
        "seat_demand": SeatDemand(
            required_role_category=RoleCategory.IMPLEMENTATION,
            required_capability_tags=(
                CapabilityTag(value="task.implementation"),
                CapabilityTag(value="surface.backend"),
            ),
        ),
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
        "seat_ref": AgentSeatRef(value="seat-worker-backend"),
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
        project_ref=PROJECT_REF,
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
    seat_projection: SeatLifecycleProjection | None = None,
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
        seat_projection=seat_projection or _seat_projection(),
    )



def test_ticket_without_seat_demand_is_not_assignable() -> None:
    with pytest.raises(ValidationError):
        _ticket_payload(seat_demand=None)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        (
            "required_capability_tags",
            (CapabilityTag(value="surface.backend"),),
        ),
        ("required_role_category", RoleCategory.IMPLEMENTATION),
    ],
)
def test_assignment_payload_rejects_demand_override(field: str, value: object) -> None:
    payload = _seat_assignment_payload().model_dump()
    payload[field] = value

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        SeatAssignmentPayload(**payload)



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
    projector = _projector(seat_projection=_seat_projection(active_seats=(), seats=()))

    graph = projector.project((_ticket_created_event(), _seat_assigned_event()))

    ticket_id = TicketId(value="ticket-backend-api")
    assert graph.ready_queue == ()
    assert graph.nodes[ticket_id].status.value == "blocked"
    assert graph.seat_assignments == {}
    assert graph.seat_blockers[ticket_id] == (
        "team composition gap: inactive or unknown seat: seat-worker-backend",
    )



def test_assignment_blocks_when_active_seat_does_not_match_ticket_demand() -> None:
    projector = _projector(
        seat_projection=_seat_projection(
            active_seats=(
                _agent_seat(
                    role_category=RoleCategory.VERIFICATION,
                    capability_tags=(
                        CapabilityTag(value="task.implementation"),
                        CapabilityTag(value="surface.backend"),
                    ),
                ),
            )
        )
    )

    graph = projector.project((_ticket_created_event(), _seat_assigned_event()))

    ticket_id = TicketId(value="ticket-backend-api")
    assert graph.ready_queue == ()
    assert graph.nodes[ticket_id].status.value == "blocked"
    assert graph.seat_assignments == {}
    assert graph.seat_blockers[ticket_id] == (
        "team composition gap: role category mismatch: verification != implementation",
    )



def test_seat_assignment_blocks_missing_capability_tags() -> None:
    projector = _projector(
        seat_projection=_seat_projection(
            active_seats=(
                _agent_seat(
                    capability_tags=(CapabilityTag(value="task.implementation"),),
                ),
            )
        )
    )

    graph = projector.project((_ticket_created_event(), _seat_assigned_event()))

    ticket_id = TicketId(value="ticket-backend-api")
    assert graph.ready_queue == ()
    assert graph.nodes[ticket_id].status.value == "blocked"
    assert graph.seat_assignments == {}
    assert graph.seat_blockers[ticket_id] == (
        "team composition gap: missing capability tags: surface.backend",
    )



def test_seat_assignment_blocks_inactive_seat() -> None:
    inactive_seat = _agent_seat(
        lifecycle_status=SeatLifecycleStatus.DEACTIVATED,
    )
    projector = _projector(
        seat_projection=_seat_projection(active_seats=(), seats=(inactive_seat,))
    )

    graph = projector.project((_ticket_created_event(), _seat_assigned_event()))

    ticket_id = TicketId(value="ticket-backend-api")
    assert graph.ready_queue == ()
    assert graph.nodes[ticket_id].status.value == "blocked"
    assert graph.seat_assignments == {}
    assert graph.seat_blockers[ticket_id] == (
        "team composition gap: inactive or unknown seat: seat-worker-backend",
    )



def test_assignment_does_not_follow_replacement_chain() -> None:
    replaced_seat_ref = AgentSeatRef(value="seat-worker-backend")
    replacement_seat_ref = AgentSeatRef(value="seat-worker-backend-v2")
    replaced_seat = _agent_seat(
        seat_ref=replaced_seat_ref,
        lifecycle_status=SeatLifecycleStatus.REPLACED,
    )
    replacement_seat = _agent_seat(
        seat_ref=replacement_seat_ref,
        actor_ref=ActorRef(value="actor.worker.backend.v2"),
        role_profile_ref=RoleProfileId(value="role.implementation.backend.v2"),
        model_execution_profile_ref=ModelExecutionProfileId(
            value="model.implementation.backend.v2"
        ),
        skill_refs=(SkillRef(value="skill.implementation.backend.v2"),),
    )
    projector = _projector(
        seat_projection=_seat_projection(
            active_seats=(replacement_seat,),
            seats=(replaced_seat, replacement_seat),
            replacement_refs={replaced_seat_ref: replacement_seat_ref},
        )
    )

    graph = projector.project((_ticket_created_event(), _seat_assigned_event()))

    ticket_id = TicketId(value="ticket-backend-api")
    assert graph.ready_queue == ()
    assert graph.nodes[ticket_id].status.value == "blocked"
    assert graph.seat_assignments == {}
    assert graph.seat_blockers[ticket_id] == (
        "team composition gap: inactive or unknown seat: seat-worker-backend",
    )



def test_seat_assignment_allows_role_specific_seats_for_different_tickets() -> None:
    seats = (
        _agent_seat(
            seat_ref=AgentSeatRef(value="seat-ceo"),
            actor_ref=ActorRef(value="actor.ceo"),
            role_profile_ref=RoleProfileId(value="role.governance.ceo"),
            role_category=RoleCategory.GOVERNANCE,
            capability_tags=(CapabilityTag(value="team.composition"),),
            model_execution_profile_ref=ModelExecutionProfileId(
                value="model.governance.ceo"
            ),
            skill_refs=(SkillRef(value="skill.governance.ceo"),),
        ),
        _agent_seat(
            seat_ref=AgentSeatRef(value="seat-architect"),
            actor_ref=ActorRef(value="actor.architect"),
            role_profile_ref=RoleProfileId(value="role.architecture.lead"),
            role_category=RoleCategory.ARCHITECTURE,
            capability_tags=(CapabilityTag(value="surface.backend"),),
            model_execution_profile_ref=ModelExecutionProfileId(
                value="model.architecture.lead"
            ),
            skill_refs=(SkillRef(value="skill.architecture.lead"),),
        ),
        _agent_seat(),
        _agent_seat(
            seat_ref=AgentSeatRef(value="seat-checker"),
            actor_ref=ActorRef(value="actor.checker"),
            role_profile_ref=RoleProfileId(value="role.verification.qa"),
            role_category=RoleCategory.VERIFICATION,
            capability_tags=(CapabilityTag(value="quality.verification"),),
            model_execution_profile_ref=ModelExecutionProfileId(
                value="model.verification.qa"
            ),
            skill_refs=(SkillRef(value="skill.verification.qa"),),
        ),
    )
    created_payloads = {
        "payload:ticket-scope-created": _ticket_payload(
            ticket_id=TicketId(value="ticket-scope"),
            purpose="Clarify scope",
            seat_demand=SeatDemand(
                required_role_category=RoleCategory.GOVERNANCE,
                required_capability_tags=(CapabilityTag(value="team.composition"),),
            ),
        ),
        "payload:ticket-architecture-created": _ticket_payload(
            ticket_id=TicketId(value="ticket-architecture"),
            purpose="Design architecture",
            seat_demand=SeatDemand(
                required_role_category=RoleCategory.ARCHITECTURE,
                required_capability_tags=(CapabilityTag(value="surface.backend"),),
            ),
        ),
        "payload:ticket-backend-api-created": _ticket_payload(),
        "payload:ticket-check-created": _ticket_payload(
            ticket_id=TicketId(value="ticket-check"),
            purpose="Check implementation evidence",
            seat_demand=SeatDemand(
                required_role_category=RoleCategory.VERIFICATION,
                required_capability_tags=(CapabilityTag(value="quality.verification"),),
            ),
        ),
    }
    assignment_payloads = {
        "payload:ticket-scope-seat-assigned": _seat_assignment_payload(
            ticket_id=TicketId(value="ticket-scope"),
            seat_ref=AgentSeatRef(value="seat-ceo"),
        ),
        "payload:ticket-architecture-seat-assigned": _seat_assignment_payload(
            ticket_id=TicketId(value="ticket-architecture"),
            seat_ref=AgentSeatRef(value="seat-architect"),
        ),
        "payload:ticket-backend-api-seat-assigned": _seat_assignment_payload(),
        "payload:ticket-check-seat-assigned": _seat_assignment_payload(
            ticket_id=TicketId(value="ticket-check"),
            seat_ref=AgentSeatRef(value="seat-checker"),
        ),
    }
    resolver = InMemorySeatAssignmentPayloadResolver(
        created_payloads=created_payloads,
        assignment_payloads=assignment_payloads,
    )
    projector = SeatAssignmentProjector(
        ticket_projector=TicketGraphProjector(resolver),
        payload_resolver=resolver,
        seat_projection=_seat_projection(active_seats=seats, seats=seats),
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
        TicketId(value="ticket-scope"): AgentSeatRef(value="seat-ceo"),
        TicketId(value="ticket-architecture"): AgentSeatRef(value="seat-architect"),
        TicketId(value="ticket-backend-api"): AgentSeatRef(value="seat-worker-backend"),
        TicketId(value="ticket-check"): AgentSeatRef(value="seat-checker"),
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

    assert len(event_log.read(PROJECT_REF)) == 8
