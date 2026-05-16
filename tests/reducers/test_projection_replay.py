from datetime import UTC, datetime

import pytest

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
from boardroom_os.graph.replay import ProjectionReplay, ProjectionReplayError
from boardroom_os.graph.seat_assignment import (
    SeatAssignmentPayload,
    SeatAssignmentProjector,
)
from boardroom_os.graph.ticket import TicketCreatedPayload, TicketId

BASE_TIMESTAMP = datetime(2026, 5, 16, 14, 0, tzinfo=UTC)
PROJECT_REF = ProjectRef(value="project-tiny-fullstack")


class InMemoryReplayPayloadResolver:
    def __init__(
        self,
        *,
        created_payloads: dict[str, TicketCreatedPayload] | None = None,
        assignment_payloads: dict[str, SeatAssignmentPayload] | None = None,
    ) -> None:
        self._created_payloads = created_payloads or {}
        self._assignment_payloads = assignment_payloads or {}

    def resolve_ticket_created(self, payload_ref: EventPayloadRef) -> TicketCreatedPayload:
        return self._created_payloads[payload_ref.value]

    def resolve_ticket_blocked(self, payload_ref: EventPayloadRef):
        raise KeyError(payload_ref.value)

    def resolve_seat_assignment(
        self, payload_ref: EventPayloadRef
    ) -> SeatAssignmentPayload:
        return self._assignment_payloads[payload_ref.value]



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
    *, active_seats: tuple[AgentSeat, ...] | None = None
) -> SeatLifecycleProjection:
    active = active_seats if active_seats is not None else (_agent_seat(),)
    return SeatLifecycleProjection(
        graph_version=1,
        seats={seat.seat_ref: seat for seat in active},
        active_seats={seat.seat_ref: seat for seat in active},
        replacement_refs={},
    )



def _event(
    *,
    event_id: str,
    event_type: EventType,
    payload_ref: str,
    graph_version: int,
    actor_ref: str = "seat-architect",
) -> EventRecord:
    return EventRecord(
        event_id=EventId(value=event_id),
        event_type=event_type,
        project_ref=PROJECT_REF,
        actor_ref=ActorRef(value=actor_ref),
        timestamp=BASE_TIMESTAMP,
        graph_version=graph_version,
        payload_refs=(EventPayloadRef(value=payload_ref),),
    )



def _ticket_created_event(
    *,
    graph_version: int = 1,
    payload_ref: str = "payload:ticket-backend-api-created",
) -> EventRecord:
    return _event(
        event_id=f"evt-ticket-created-{graph_version}",
        event_type=EventType.TICKET_CREATED,
        payload_ref=payload_ref,
        graph_version=graph_version,
    )



def _seat_assigned_event(*, graph_version: int = 2) -> EventRecord:
    return _event(
        event_id=f"evt-seat-assigned-{graph_version}",
        event_type=EventType.SEAT_ASSIGNED,
        payload_ref="payload:ticket-backend-api-seat-assigned",
        graph_version=graph_version,
        actor_ref="seat-ceo",
    )



def _projector(
    *,
    created_payloads: dict[str, TicketCreatedPayload] | None = None,
    assignment_payloads: dict[str, SeatAssignmentPayload] | None = None,
    seat_projection: SeatLifecycleProjection | None = None,
) -> SeatAssignmentProjector:
    if created_payloads is None:
        created_payloads = {"payload:ticket-backend-api-created": _ticket_payload()}
    if assignment_payloads is None:
        assignment_payloads = {
            "payload:ticket-backend-api-seat-assigned": _seat_assignment_payload()
        }
    resolver = InMemoryReplayPayloadResolver(
        created_payloads=created_payloads,
        assignment_payloads=assignment_payloads,
    )
    return SeatAssignmentProjector(
        ticket_projector=TicketGraphProjector(resolver),
        payload_resolver=resolver,
        seat_projection=seat_projection or _seat_projection(),
    )



def _replay() -> ProjectionReplay:
    return ProjectionReplay(projection_kind="seat_assignment_graph")



def _event_log(events: tuple[EventRecord, ...]) -> InMemoryEventLog:
    log = InMemoryEventLog()
    for event in events:
        log.append(event)
    return log



@pytest.mark.parametrize("value", [0, -1])
def test_replay_rejects_non_positive_expected_graph_version(value: int) -> None:
    with pytest.raises(
        ProjectionReplayError,
        match="expected_graph_version must be positive",
    ):
        _replay().replay(
            event_log=InMemoryEventLog(),
            project_ref=PROJECT_REF,
            expected_graph_version=value,
            projector=_projector(),
        )



def test_replay_rejects_empty_event_history() -> None:
    with pytest.raises(ProjectionReplayError, match="event range must not be empty"):
        _replay().replay(
            event_log=InMemoryEventLog(),
            project_ref=PROJECT_REF,
            expected_graph_version=1,
            projector=_projector(),
        )



def test_replay_rejects_project_ref_mismatch() -> None:
    events = (_ticket_created_event(), _seat_assigned_event())

    with pytest.raises(ProjectionReplayError, match="event project_ref mismatch"):
        _replay().replay_events(
            events=events,
            project_ref=ProjectRef(value="project-other"),
            expected_graph_version=2,
            projector=_projector(),
        )



def test_replay_rejects_missing_graph_version() -> None:
    log = _event_log((_ticket_created_event(graph_version=1), _seat_assigned_event(graph_version=3)))

    with pytest.raises(ProjectionReplayError, match="graph_version must be contiguous"):
        _replay().replay(
            event_log=log,
            project_ref=PROJECT_REF,
            expected_graph_version=3,
            projector=_projector(),
        )



def test_replay_rejects_unordered_event_input() -> None:
    events = (_seat_assigned_event(graph_version=2), _ticket_created_event(graph_version=1))

    with pytest.raises(ProjectionReplayError, match="graph_version must be strictly ordered"):
        _replay().replay_events(
            events=events,
            project_ref=PROJECT_REF,
            expected_graph_version=2,
            projector=_projector(),
        )



def test_replay_rejects_projection_version_mismatch() -> None:
    log = _event_log((_ticket_created_event(), _seat_assigned_event()))

    with pytest.raises(ProjectionReplayError, match="projection version mismatch"):
        _replay().replay(
            event_log=log,
            project_ref=PROJECT_REF,
            expected_graph_version=3,
            projector=_projector(),
        )



def test_replay_rejects_unresolved_payload_ref() -> None:
    log = _event_log((_ticket_created_event(), _seat_assigned_event()))

    with pytest.raises(ProjectionReplayError, match="projection failed"):
        _replay().replay(
            event_log=log,
            project_ref=PROJECT_REF,
            expected_graph_version=2,
            projector=_projector(created_payloads={}),
        )



def test_replay_rejects_mid_range_without_snapshot_contract() -> None:
    log = _event_log(
        (
            _ticket_created_event(graph_version=1),
            _ticket_created_event(
                graph_version=2,
                payload_ref="payload:ticket-frontend-created",
            ),
        )
    )
    projector = _projector(
        created_payloads={
            "payload:ticket-backend-api-created": _ticket_payload(),
            "payload:ticket-frontend-created": _ticket_payload(
                ticket_id=TicketId(value="ticket-frontend-ui"),
                purpose="Implement frontend UI surface",
                seat_demand=SeatDemand(
                    required_role_category=RoleCategory.IMPLEMENTATION,
                    required_capability_tags=(
                        CapabilityTag(value="task.implementation"),
                        CapabilityTag(value="surface.frontend"),
                    ),
                ),
                source_surface_refs=("surface-frontend-ui",),
                allowed_write_set=("10-project/frontend/**",),
            ),
        }
    )

    with pytest.raises(
        ProjectionReplayError,
        match="from_graph_version requires snapshot or base projection contract",
    ):
        _replay().replay(
            event_log=log,
            project_ref=PROJECT_REF,
            expected_graph_version=2,
            projector=projector,
            from_graph_version=2,
        )



def test_replay_returns_stable_seat_assignment_summary() -> None:
    log = _event_log((_ticket_created_event(), _seat_assigned_event()))

    summary = _replay().replay(
        event_log=log,
        project_ref=PROJECT_REF,
        expected_graph_version=2,
        projector=_projector(),
    )

    assert summary.projection_kind == "seat_assignment_graph"
    assert summary.project_ref == PROJECT_REF
    assert summary.event_range.first_graph_version == 1
    assert summary.event_range.last_graph_version == 2
    assert summary.event_range.first_event_id == EventId(value="evt-ticket-created-1")
    assert summary.event_range.last_event_id == EventId(value="evt-seat-assigned-2")
    assert summary.event_count == 2
    assert summary.graph_version == 2
    assert tuple(summary.nodes) == ("ticket-backend-api",)
    assert summary.nodes["ticket-backend-api"] == {
        "ticket_id": {"value": "ticket-backend-api"},
        "purpose": "Implement backend API surface",
        "seat_demand": {
            "required_role_category": "implementation",
            "required_capability_tags": [
                {"value": "task.implementation"},
                {"value": "surface.backend"},
            ],
        },
        "depends_on": [],
        "acceptance_refs": ["AC-BOOK-API-STATE-001"],
        "source_surface_refs": ["surface-backend-api"],
        "evidence_obligations": ["obligation-api-test-run"],
        "allowed_read_refs": ["contract:tiny-fullstack"],
        "allowed_write_set": ["10-project/backend/**"],
        "attempt_count": 0,
        "status": "ready",
    }
    assert summary.ready_queue == ("ticket-backend-api",)
    assert summary.blocked_by == {}
    assert summary.completed_nodes == ()
    assert summary.seat_assignments == {
        "ticket-backend-api": "seat-worker-backend",
    }
    assert summary.seat_blockers == {}
    assert len(summary.summary_hash) == 64



def test_replay_hash_is_identical_for_equivalent_summary_payloads() -> None:
    log = _event_log((_ticket_created_event(), _seat_assigned_event()))

    first_summary = _replay().replay(
        event_log=log,
        project_ref=PROJECT_REF,
        expected_graph_version=2,
        projector=_projector(),
    )

    payload = first_summary.model_dump(mode="python", exclude={"summary_hash"})
    payload["nodes"] = {
        ticket_id: dict(reversed(tuple(node.items())))
        for ticket_id, node in payload["nodes"].items()
    }
    second_summary = type(first_summary)(**payload)

    assert second_summary.model_dump(mode="json", exclude={"summary_hash"}) == (
        first_summary.model_dump(mode="json", exclude={"summary_hash"})
    )
    assert second_summary.summary_hash == first_summary.summary_hash
