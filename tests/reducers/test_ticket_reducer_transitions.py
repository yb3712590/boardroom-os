from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

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
from boardroom_os.graph.ticket import TicketCreatedPayload, TicketId, TicketStatus
from boardroom_os.reducers.errors import TicketReducerError
from boardroom_os.reducers.ticket_reducer import (
    TicketCheckSnapshot,
    TicketCompletionSnapshot,
    TicketReducer,
    TicketReducerPayloadResolver,
    TicketRefPayload,
)

BASE_TIMESTAMP = datetime(2026, 5, 16, 9, 0, tzinfo=UTC)


class InMemoryTicketReducerPayloadResolver(TicketReducerPayloadResolver):
    def __init__(
        self,
        *,
        created_payloads: dict[str, TicketCreatedPayload] | None = None,
        completion_snapshots: dict[str, TicketCompletionSnapshot] | None = None,
        ticket_refs: dict[str, TicketRefPayload] | None = None,
        check_snapshots: dict[str, TicketCheckSnapshot] | None = None,
    ) -> None:
        self._created_payloads = created_payloads or {}
        self._completion_snapshots = completion_snapshots or {}
        self._ticket_refs = ticket_refs or {}
        self._check_snapshots = check_snapshots or {}

    def resolve_ticket_created(self, payload_ref: EventPayloadRef) -> TicketCreatedPayload:
        return self._created_payloads[payload_ref.value]

    def resolve_ticket_ref(self, payload_ref: EventPayloadRef) -> TicketRefPayload:
        return self._ticket_refs[payload_ref.value]

    def resolve_work_product_ticket_ref(
        self,
        payload_ref: EventPayloadRef,
    ) -> TicketRefPayload:
        return self._ticket_refs[payload_ref.value]

    def resolve_ticket_check(self, payload_ref: EventPayloadRef) -> TicketCheckSnapshot:
        return self._check_snapshots[payload_ref.value]

    def resolve_ticket_completion(
        self, payload_ref: EventPayloadRef
    ) -> TicketCompletionSnapshot:
        return self._completion_snapshots[payload_ref.value]


def _valid_ticket_payload(**overrides: object) -> TicketCreatedPayload:
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


def _ticket_ref(**overrides: object) -> TicketRefPayload:
    values = {"ticket_id": TicketId(value="ticket-backend-api")}
    values.update(overrides)
    return TicketRefPayload(**values)


def _check_snapshot(**overrides: object) -> TicketCheckSnapshot:
    values = {
        "ticket_id": TicketId(value="ticket-backend-api"),
        "checker_approved": True,
        "blocking_issue_refs": (),
    }
    values.update(overrides)
    return TicketCheckSnapshot(**values)


def _completion_snapshot(**overrides: object) -> TicketCompletionSnapshot:
    values = {
        "ticket_id": TicketId(value="ticket-backend-api"),
        "provider_attempt_count": 1,
        "evidence_complete": True,
        "checker_approved": True,
        "blocking_issue_refs": (),
    }
    values.update(overrides)
    return TicketCompletionSnapshot(**values)


def _event(
    *,
    event_id: str,
    event_type: EventType,
    actor_ref: str,
    payload_ref: str,
    graph_version: int,
) -> EventRecord:
    return EventRecord(
        event_id=EventId(value=event_id),
        event_type=event_type,
        project_ref=ProjectRef(value="project-tiny-fullstack"),
        actor_ref=ActorRef(value=actor_ref),
        timestamp=BASE_TIMESTAMP,
        graph_version=graph_version,
        payload_refs=(EventPayloadRef(value=payload_ref),),
    )


def _created_event() -> EventRecord:
    return _event(
        event_id="evt-ticket-backend-api-created",
        event_type=EventType.TICKET_CREATED,
        actor_ref="seat-architect",
        payload_ref="payload:ticket-backend-api-created",
        graph_version=1,
    )


def _lifecycle_event(
    event_type: EventType,
    *,
    event_id: str | None = None,
    graph_version: int = 2,
    actor_ref: str = "seat-worker-backend",
) -> EventRecord:
    event_name = event_type.value.replace("_", "-")
    return _event(
        event_id=event_id or f"evt-ticket-backend-api-{event_name}",
        event_type=event_type,
        actor_ref=actor_ref,
        payload_ref=f"payload:ticket-backend-api-{event_name}",
        graph_version=graph_version,
    )


def _completed_event(
    actor_ref: str = "seat-checker",
    *,
    graph_version: int = 2,
) -> EventRecord:
    return _event(
        event_id="evt-ticket-backend-api-completed",
        event_type=EventType.TICKET_COMPLETED,
        actor_ref=actor_ref,
        payload_ref="payload:ticket-backend-api-completed",
        graph_version=graph_version,
    )


@pytest.mark.parametrize("actor_ref", ["executor:local", "runtime:default"])
def test_reducer_rejects_executor_or_runtime_ticket_completed(actor_ref: str) -> None:
    resolver = InMemoryTicketReducerPayloadResolver(
        created_payloads={"payload:ticket-backend-api-created": _valid_ticket_payload()},
        completion_snapshots={
            "payload:ticket-backend-api-completed": _completion_snapshot()
        },
    )

    with pytest.raises(TicketReducerError, match="executor/runtime cannot complete ticket"):
        TicketReducer(resolver).reduce((_created_event(), _completed_event(actor_ref)))


def test_reducer_records_lease_and_work_product_without_completing_ticket() -> None:
    resolver = InMemoryTicketReducerPayloadResolver(
        created_payloads={"payload:ticket-backend-api-created": _valid_ticket_payload()},
        ticket_refs={
            "payload:ticket-backend-api-ticket-leased": _ticket_ref(),
            "payload:ticket-backend-api-work-product-submitted": _ticket_ref(),
        },
    )

    graph = TicketReducer(resolver).reduce(
        (
            _created_event(),
            _lifecycle_event(EventType.TICKET_LEASED, graph_version=2),
            _lifecycle_event(EventType.WORK_PRODUCT_SUBMITTED, graph_version=3),
        )
    )

    assert graph.graph_version == 3
    assert graph.nodes[TicketId(value="ticket-backend-api")].status is TicketStatus.READY
    assert graph.completed_nodes == ()


def test_reducer_applies_checker_rework_as_blocked_ticket() -> None:
    resolver = InMemoryTicketReducerPayloadResolver(
        created_payloads={"payload:ticket-backend-api-created": _valid_ticket_payload()},
        check_snapshots={
            "payload:ticket-backend-api-ticket-checked": _check_snapshot(
                checker_approved=False,
                blocking_issue_refs=("blocker:missing-api-test",),
            )
        },
        ticket_refs={"payload:ticket-backend-api-ticket-reworked": _ticket_ref()},
    )

    graph = TicketReducer(resolver).reduce(
        (
            _created_event(),
            _lifecycle_event(EventType.TICKET_CHECKED, graph_version=2, actor_ref="seat-checker"),
            _lifecycle_event(EventType.TICKET_REWORKED, graph_version=3, actor_ref="seat-architect"),
        )
    )

    assert graph.graph_version == 3
    assert graph.nodes[TicketId(value="ticket-backend-api")].status is TicketStatus.BLOCKED
    assert graph.ready_queue == ()


def test_reducer_rejects_rework_without_checker_blocker() -> None:
    resolver = InMemoryTicketReducerPayloadResolver(
        created_payloads={"payload:ticket-backend-api-created": _valid_ticket_payload()},
        ticket_refs={"payload:ticket-backend-api-ticket-reworked": _ticket_ref()},
    )

    with pytest.raises(TicketReducerError, match="checker blocker"):
        TicketReducer(resolver).reduce(
            (
                _created_event(),
                _lifecycle_event(EventType.TICKET_REWORKED, graph_version=2, actor_ref="seat-architect"),
            )
        )


def test_reducer_rejects_completion_without_provider_attempt() -> None:
    resolver = InMemoryTicketReducerPayloadResolver(
        created_payloads={"payload:ticket-backend-api-created": _valid_ticket_payload()},
        ticket_refs={"payload:ticket-backend-api-work-product-submitted": _ticket_ref()},
        completion_snapshots={
            "payload:ticket-backend-api-completed": _completion_snapshot(
                provider_attempt_count=0
            )
        },
    )

    with pytest.raises(TicketReducerError, match="provider attempt"):
        TicketReducer(resolver).reduce(
            (
                _created_event(),
                _lifecycle_event(EventType.WORK_PRODUCT_SUBMITTED, graph_version=2),
                _completed_event(graph_version=3),
            )
        )


def test_reducer_rejects_completion_with_checker_blockers() -> None:
    resolver = InMemoryTicketReducerPayloadResolver(
        created_payloads={"payload:ticket-backend-api-created": _valid_ticket_payload()},
        ticket_refs={"payload:ticket-backend-api-work-product-submitted": _ticket_ref()},
        completion_snapshots={
            "payload:ticket-backend-api-completed": _completion_snapshot(
                blocking_issue_refs=("blocker:missing-api-test",)
            )
        },
    )

    with pytest.raises(TicketReducerError, match="blocking issues"):
        TicketReducer(resolver).reduce(
            (
                _created_event(),
                _lifecycle_event(EventType.WORK_PRODUCT_SUBMITTED, graph_version=2),
                _completed_event(graph_version=3),
            )
        )


def test_reducer_rejects_completion_while_prior_checker_blocker_is_open() -> None:
    resolver = InMemoryTicketReducerPayloadResolver(
        created_payloads={"payload:ticket-backend-api-created": _valid_ticket_payload()},
        check_snapshots={
            "payload:ticket-backend-api-ticket-checked": _check_snapshot(
                checker_approved=False,
                blocking_issue_refs=("blocker:missing-api-test",),
            )
        },
        completion_snapshots={
            "payload:ticket-backend-api-completed": _completion_snapshot(
                blocking_issue_refs=()
            )
        },
    )

    with pytest.raises(TicketReducerError, match="open checker blockers"):
        TicketReducer(resolver).reduce(
            (
                _created_event(),
                _lifecycle_event(EventType.TICKET_CHECKED, graph_version=2, actor_ref="seat-checker"),
                _completed_event(graph_version=3),
            )
        )


def test_reducer_rejects_completion_without_work_product() -> None:
    resolver = InMemoryTicketReducerPayloadResolver(
        created_payloads={"payload:ticket-backend-api-created": _valid_ticket_payload()},
        completion_snapshots={
            "payload:ticket-backend-api-completed": _completion_snapshot()
        },
    )

    with pytest.raises(TicketReducerError, match="work product"):
        TicketReducer(resolver).reduce((_created_event(), _completed_event()))



def test_reducer_allows_reworked_ticket_to_complete_after_checker_approval() -> None:
    resolver = InMemoryTicketReducerPayloadResolver(
        created_payloads={"payload:ticket-backend-api-created": _valid_ticket_payload()},
        check_snapshots={
            "payload:ticket-backend-api-ticket-checked": _check_snapshot(
                checker_approved=True,
                blocking_issue_refs=(),
            ),
            "payload:ticket-backend-api-check-failed": _check_snapshot(
                checker_approved=False,
                blocking_issue_refs=("blocker:missing-api-test",),
            ),
        },
        ticket_refs={
            "payload:ticket-backend-api-ticket-reworked": _ticket_ref(),
            "payload:ticket-backend-api-work-product-submitted": _ticket_ref(),
        },
        completion_snapshots={
            "payload:ticket-backend-api-completed": _completion_snapshot()
        },
    )

    graph = TicketReducer(resolver).reduce(
        (
            _created_event(),
            _event(
                event_id="evt-ticket-backend-api-check-failed",
                event_type=EventType.TICKET_CHECKED,
                actor_ref="seat-checker",
                payload_ref="payload:ticket-backend-api-check-failed",
                graph_version=2,
            ),
            _lifecycle_event(EventType.TICKET_REWORKED, graph_version=3, actor_ref="seat-architect"),
            _lifecycle_event(EventType.WORK_PRODUCT_SUBMITTED, graph_version=4),
            _lifecycle_event(EventType.TICKET_CHECKED, graph_version=5, actor_ref="seat-checker"),
            _completed_event(graph_version=6),
        )
    )

    assert graph.graph_version == 6
    assert graph.nodes[TicketId(value="ticket-backend-api")].status is TicketStatus.COMPLETED
    assert graph.completed_nodes == (TicketId(value="ticket-backend-api"),)


def test_completion_snapshot_rejects_missing_evidence_or_checker_approval() -> None:
    with pytest.raises(ValidationError):
        _completion_snapshot(evidence_complete=False)

    with pytest.raises(ValidationError):
        _completion_snapshot(checker_approved=False)


def test_reducer_completes_ticket_when_completion_boundary_is_satisfied() -> None:
    resolver = InMemoryTicketReducerPayloadResolver(
        created_payloads={"payload:ticket-backend-api-created": _valid_ticket_payload()},
        ticket_refs={"payload:ticket-backend-api-work-product-submitted": _ticket_ref()},
        completion_snapshots={
            "payload:ticket-backend-api-completed": _completion_snapshot()
        },
    )

    graph = TicketReducer(resolver).reduce(
        (
            _created_event(),
            _lifecycle_event(EventType.WORK_PRODUCT_SUBMITTED, graph_version=2),
            _completed_event(graph_version=3),
        )
    )

    assert graph.graph_version == 3
    assert graph.nodes[TicketId(value="ticket-backend-api")].status is TicketStatus.COMPLETED
    assert graph.completed_nodes == (TicketId(value="ticket-backend-api"),)
    assert graph.ready_queue == ()
