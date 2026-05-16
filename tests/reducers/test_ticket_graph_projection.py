from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from boardroom_os.events.record import EventRecord
from boardroom_os.events.types import (
    ActorRef,
    EventId,
    EventPayloadRef,
    EventType,
    ProjectRef,
)
from boardroom_os.graph.projection import (
    TicketGraphProjectionError,
    TicketGraphProjector,
)
from boardroom_os.graph.ticket import (
    TicketBlockedPayload,
    TicketCreatedPayload,
    TicketGraph,
    TicketId,
    TicketNode,
    TicketStatus,
)


BASE_TIMESTAMP = datetime(2026, 5, 15, 12, 0, tzinfo=UTC)


class InMemoryTicketPayloadResolver:
    def __init__(
        self,
        created_payloads: dict[str, TicketCreatedPayload],
        blocked_payloads: dict[str, TicketBlockedPayload] | None = None,
    ) -> None:
        self._created_payloads = created_payloads
        self._blocked_payloads = blocked_payloads or {}
        self.created_calls: list[str] = []
        self.blocked_calls: list[str] = []

    def resolve_ticket_created(self, payload_ref: EventPayloadRef) -> TicketCreatedPayload:
        self.created_calls.append(payload_ref.value)
        return self._created_payloads[payload_ref.value]

    def resolve_ticket_blocked(self, payload_ref: EventPayloadRef) -> TicketBlockedPayload:
        self.blocked_calls.append(payload_ref.value)
        return self._blocked_payloads[payload_ref.value]



def _valid_ticket_blocked_payload(**overrides: object) -> TicketBlockedPayload:
    values = {
        "ticket_id": TicketId(value="ticket-backend-api"),
    }
    values.update(overrides)
    return TicketBlockedPayload(**values)


def _valid_ticket_payload(**overrides: object) -> TicketCreatedPayload:
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


def _valid_ticket_node(**overrides: object) -> TicketNode:
    values = _valid_ticket_payload().model_dump()
    values["status"] = TicketStatus.READY
    values.update(overrides)
    return TicketNode(**values)



def _completed_ticket_node(**overrides: object) -> TicketNode:
    values = _valid_ticket_payload().model_dump()
    values["status"] = TicketStatus.COMPLETED
    values.update(overrides)
    return TicketNode(**values)


def _ticket_event(
    *,
    event_id: str = "evt-ticket-backend-api-created",
    payload_ref: str = "payload:ticket-backend-api",
    graph_version: int = 1,
    event_type: EventType = EventType.TICKET_CREATED,
) -> EventRecord:
    return EventRecord(
        event_id=EventId(value=event_id),
        event_type=event_type,
        project_ref=ProjectRef(value="project-tiny-fullstack"),
        actor_ref=ActorRef(value="seat-architect"),
        timestamp=BASE_TIMESTAMP,
        graph_version=graph_version,
        payload_refs=(EventPayloadRef(value=payload_ref),),
    )


@pytest.mark.parametrize(
    "missing_field",
    ["acceptance_refs", "source_surface_refs", "evidence_obligations", "allowed_write_set"],
)
def test_ticket_payload_requires_execution_contract_fields(missing_field: str) -> None:
    values = _valid_ticket_payload().model_dump()
    values.pop(missing_field)

    with pytest.raises(ValidationError):
        TicketCreatedPayload(**values)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("ticket_id", {"value": " "}),
        ("purpose", " "),
        ("owner_seat_ref", " "),
        ("acceptance_refs", ()),
        ("source_surface_refs", ()),
        ("evidence_obligations", ()),
        ("allowed_write_set", ()),
        ("attempt_count", -1),
        ("status", "made_up_status"),
    ],
)
def test_ticket_payload_rejects_invalid_core_fields(field: str, value: object) -> None:
    with pytest.raises(ValidationError):
        _valid_ticket_payload(**{field: value})


@pytest.mark.parametrize(
    "field",
    ["acceptance_refs", "source_surface_refs", "evidence_obligations", "allowed_write_set"],
)
def test_ticket_payload_rejects_required_tuple_blank_values(field: str) -> None:
    with pytest.raises(ValidationError):
        _valid_ticket_payload(**{field: (" ",)})


@pytest.mark.parametrize(
    "field",
    ["acceptance_refs", "source_surface_refs", "evidence_obligations", "allowed_write_set"],
)
def test_ticket_payload_normalizes_required_tuple_values(field: str) -> None:
    payload = _valid_ticket_payload(**{field: (" value ",)})

    assert getattr(payload, field) == ("value",)


def test_ticket_payload_rejects_blank_allowed_read_refs() -> None:
    with pytest.raises(ValidationError):
        _valid_ticket_payload(allowed_read_refs=(" ",))


def test_ticket_payload_normalizes_allowed_read_refs() -> None:
    payload = _valid_ticket_payload(allowed_read_refs=(" contract:tiny-fullstack ",))

    assert payload.allowed_read_refs == ("contract:tiny-fullstack",)


def test_ticket_created_payload_rejects_completed_status() -> None:
    values = _valid_ticket_payload().model_dump()
    values["status"] = TicketStatus.COMPLETED

    with pytest.raises(ValidationError):
        TicketCreatedPayload(**values)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("purpose", " "),
        ("owner_seat_ref", " "),
        ("acceptance_refs", ()),
        ("source_surface_refs", ()),
        ("evidence_obligations", ()),
        ("allowed_write_set", ()),
        ("attempt_count", -1),
    ],
)
def test_ticket_node_direct_construction_rejects_invalid_core_fields(
    field: str, value: object
) -> None:
    with pytest.raises(ValidationError):
        _valid_ticket_node(**{field: value})


@pytest.mark.parametrize(
    "field",
    ["acceptance_refs", "source_surface_refs", "evidence_obligations", "allowed_write_set"],
)
def test_ticket_node_direct_construction_rejects_required_tuple_blank_values(
    field: str,
) -> None:
    with pytest.raises(ValidationError):
        _valid_ticket_node(**{field: (" ",)})


def test_ticket_node_direct_construction_rejects_blank_allowed_read_refs() -> None:
    with pytest.raises(ValidationError):
        _valid_ticket_node(allowed_read_refs=(" ",))


@pytest.mark.parametrize(
    "field",
    ["acceptance_refs", "source_surface_refs", "evidence_obligations", "allowed_write_set"],
)
def test_ticket_node_direct_construction_normalizes_required_tuple_values(field: str) -> None:
    node = _valid_ticket_node(**{field: (" value ",)})

    assert getattr(node, field) == ("value",)


def test_ticket_node_direct_construction_normalizes_allowed_read_refs() -> None:
    node = _valid_ticket_node(allowed_read_refs=(" contract:tiny-fullstack ",))

    assert node.allowed_read_refs == ("contract:tiny-fullstack",)


def test_ticket_graph_puts_ready_ticket_in_ready_queue() -> None:
    ticket = TicketNode.from_created_payload(_valid_ticket_payload())

    graph = TicketGraph.from_nodes(graph_version=1, nodes=(ticket,))

    assert graph.ready_queue == (TicketId(value="ticket-backend-api"),)
    assert graph.nodes[TicketId(value="ticket-backend-api")] == ticket


def test_ticket_node_from_created_payload_always_sets_ready_status() -> None:
    ticket = TicketNode.from_created_payload(_valid_ticket_payload())

    assert ticket.status is TicketStatus.READY



def test_ticket_graph_excludes_blocked_ticket_from_ready_queue() -> None:
    blocked = _valid_ticket_node(status=TicketStatus.BLOCKED)

    graph = TicketGraph.from_nodes(graph_version=1, nodes=(blocked,))

    assert graph.ready_queue == ()
    assert graph.blocked_by == {}


def test_ticket_graph_waits_for_dependencies_before_ready_queue() -> None:
    dependency = TicketNode.from_created_payload(
        _valid_ticket_payload(ticket_id=TicketId(value="ticket-contracts"))
    )
    dependent = TicketNode.from_created_payload(
        _valid_ticket_payload(
            ticket_id=TicketId(value="ticket-backend-api"),
            depends_on=(TicketId(value="ticket-contracts"),),
        )
    )

    graph = TicketGraph.from_nodes(graph_version=1, nodes=(dependency, dependent))

    assert graph.ready_queue == (TicketId(value="ticket-contracts"),)
    assert graph.blocked_by == {
        TicketId(value="ticket-backend-api"): (TicketId(value="ticket-contracts"),)
    }


def test_ticket_graph_puts_dependent_ticket_in_ready_queue_after_dependency_completed() -> None:
    dependency = _completed_ticket_node(ticket_id=TicketId(value="ticket-contracts"))
    dependent = TicketNode.from_created_payload(
        _valid_ticket_payload(
            ticket_id=TicketId(value="ticket-backend-api"),
            depends_on=(TicketId(value="ticket-contracts"),),
        )
    )

    graph = TicketGraph.from_nodes(graph_version=1, nodes=(dependency, dependent))

    assert graph.completed_nodes == (TicketId(value="ticket-contracts"),)
    assert graph.blocked_by == {}
    assert graph.ready_queue == (TicketId(value="ticket-backend-api"),)


def test_ticket_graph_rejects_graph_version_zero_or_negative() -> None:
    ticket = TicketNode.from_created_payload(_valid_ticket_payload())

    with pytest.raises(ValidationError):
        TicketGraph.from_nodes(graph_version=0, nodes=(ticket,))

    with pytest.raises(ValidationError):
        TicketGraph.from_nodes(graph_version=-1, nodes=(ticket,))


def test_ticket_graph_rejects_duplicate_ticket_ids() -> None:
    first = TicketNode.from_created_payload(
        _valid_ticket_payload(ticket_id=TicketId(value="ticket-duplicate"))
    )
    second = TicketNode.from_created_payload(
        _valid_ticket_payload(ticket_id=TicketId(value="ticket-duplicate"))
    )

    with pytest.raises(ValueError, match="duplicate ticket_id"):
        TicketGraph.from_nodes(graph_version=1, nodes=(first, second))


def test_ticket_graph_rejects_unknown_dependency() -> None:
    dependent = TicketNode.from_created_payload(
        _valid_ticket_payload(depends_on=(TicketId(value="ticket-missing"),))
    )

    with pytest.raises(ValueError, match="unknown dependency"):
        TicketGraph.from_nodes(graph_version=1, nodes=(dependent,))



def test_ticket_graph_rejects_dependency_cycle() -> None:
    backend = TicketNode.from_created_payload(
        _valid_ticket_payload(
            ticket_id=TicketId(value="ticket-backend-api"),
            depends_on=(TicketId(value="ticket-frontend-ui"),),
        )
    )
    frontend = TicketNode.from_created_payload(
        _valid_ticket_payload(
            ticket_id=TicketId(value="ticket-frontend-ui"),
            depends_on=(TicketId(value="ticket-backend-api"),),
        )
    )

    with pytest.raises(ValueError, match="dependency cycle"):
        TicketGraph.from_nodes(graph_version=1, nodes=(backend, frontend))



def test_projector_builds_ticket_graph_from_created_event_payload_ref() -> None:
    resolver = InMemoryTicketPayloadResolver(
        {"payload:ticket-backend-api": _valid_ticket_payload()}
    )

    graph = TicketGraphProjector(resolver).project((_ticket_event(),))

    assert graph.graph_version == 1
    assert graph.ready_queue == (TicketId(value="ticket-backend-api"),)
    assert tuple(graph.nodes) == (TicketId(value="ticket-backend-api"),)
    assert resolver.created_calls == ["payload:ticket-backend-api"]
    assert resolver.blocked_calls == []



def test_projector_fails_closed_when_payload_ref_cannot_be_resolved() -> None:
    resolver = InMemoryTicketPayloadResolver({})

    with pytest.raises(TicketGraphProjectionError, match="payload_ref"):
        TicketGraphProjector(resolver).project((_ticket_event(),))



def test_projector_marks_ticket_blocked_from_blocked_event() -> None:
    resolver = InMemoryTicketPayloadResolver(
        {"payload:ticket-backend-api": _valid_ticket_payload()},
        {"payload:ticket-backend-api": _valid_ticket_blocked_payload()},
    )
    created = _ticket_event(graph_version=1)
    blocked = _ticket_event(
        event_id="evt-ticket-backend-api-blocked",
        payload_ref="payload:ticket-backend-api",
        graph_version=2,
        event_type=EventType.TICKET_BLOCKED,
    )

    graph = TicketGraphProjector(resolver).project((created, blocked))

    assert graph.ready_queue == ()
    assert graph.blocked_by == {}
    assert graph.nodes[TicketId(value="ticket-backend-api")].status is TicketStatus.BLOCKED
    assert resolver.created_calls == ["payload:ticket-backend-api"]
    assert resolver.blocked_calls == ["payload:ticket-backend-api"]



def test_projector_rejects_empty_events() -> None:
    resolver = InMemoryTicketPayloadResolver({})

    with pytest.raises(TicketGraphProjectionError, match="events must not be empty"):
        TicketGraphProjector(resolver).project(())



def test_projector_rejects_blocked_event_before_ticket_created() -> None:
    resolver = InMemoryTicketPayloadResolver(
        {"payload:ticket-backend-api": _valid_ticket_payload()},
        {"payload:ticket-backend-api": _valid_ticket_blocked_payload()},
    )

    with pytest.raises(TicketGraphProjectionError, match="must exist before blocked event"):
        TicketGraphProjector(resolver).project(
            (
                _ticket_event(
                    event_id="evt-ticket-backend-api-blocked",
                    graph_version=1,
                    event_type=EventType.TICKET_BLOCKED,
                ),
            )
        )



def test_projector_rejects_blocked_event_for_unknown_ticket_payload() -> None:
    resolver = InMemoryTicketPayloadResolver(
        {"payload:ticket-backend-api": _valid_ticket_payload()},
        {"payload:ticket-backend-api": _valid_ticket_blocked_payload()},
    )

    with pytest.raises(TicketGraphProjectionError, match="payload_ref"):
        TicketGraphProjector(resolver).project(
            (
                _ticket_event(graph_version=1),
                _ticket_event(
                    event_id="evt-ticket-other-blocked",
                    payload_ref="payload:ticket-other",
                    graph_version=2,
                    event_type=EventType.TICKET_BLOCKED,
                ),
            )
        )



def test_projector_rejects_duplicate_ticket_created_events() -> None:
    resolver = InMemoryTicketPayloadResolver(
        {"payload:ticket-backend-api": _valid_ticket_payload()}
    )

    with pytest.raises(TicketGraphProjectionError, match="ticket already exists"):
        TicketGraphProjector(resolver).project(
            (
                _ticket_event(event_id="evt-ticket-created-1", graph_version=1),
                _ticket_event(event_id="evt-ticket-created-2", graph_version=2),
            )
        )



def test_projector_rejects_unsupported_ticket_event() -> None:
    resolver = InMemoryTicketPayloadResolver(
        {"payload:ticket-backend-api": _valid_ticket_payload()}
    )

    with pytest.raises(TicketGraphProjectionError, match="unsupported ticket event"):
        TicketGraphProjector(resolver).project(
            (
                _ticket_event(
                    event_id="evt-ticket-leased",
                    event_type=EventType.TICKET_LEASED,
                ),
            )
        )



def test_projector_ignores_non_ticket_event_without_mutating_graph() -> None:
    resolver = InMemoryTicketPayloadResolver(
        {"payload:ticket-backend-api": _valid_ticket_payload()}
    )

    graph = TicketGraphProjector(resolver).project(
        (
            _ticket_event(graph_version=1),
            _ticket_event(
                event_id="evt-execution-started",
                payload_ref="payload:execution-started",
                graph_version=2,
                event_type=EventType.EXECUTION_STARTED,
            ),
        )
    )

    assert graph.graph_version == 2
    assert graph.ready_queue == (TicketId(value="ticket-backend-api"),)
    assert graph.nodes[TicketId(value="ticket-backend-api")].status is TicketStatus.READY
    assert tuple(graph.nodes) == (TicketId(value="ticket-backend-api"),)
    assert resolver.created_calls == ["payload:ticket-backend-api"]
    assert resolver.blocked_calls == []



def test_projector_returns_empty_graph_for_non_ticket_events_only() -> None:
    resolver = InMemoryTicketPayloadResolver({})

    graph = TicketGraphProjector(resolver).project(
        (
            _ticket_event(
                event_id="evt-provider-attempt-recorded",
                payload_ref="payload:provider-attempt-recorded",
                graph_version=3,
                event_type=EventType.PROVIDER_ATTEMPT_RECORDED,
            ),
        )
    )

    assert graph.graph_version == 3
    assert graph.nodes == {}
    assert graph.ready_queue == ()
    assert graph.blocked_by == {}
    assert graph.completed_nodes == ()



def test_projector_sorts_events_by_graph_version_before_projection() -> None:
    resolver = InMemoryTicketPayloadResolver(
        {"payload:ticket-backend-api": _valid_ticket_payload()},
        {"payload:ticket-backend-api": _valid_ticket_blocked_payload()},
    )

    graph = TicketGraphProjector(resolver).project(
        (
            _ticket_event(
                event_id="evt-ticket-backend-api-blocked",
                payload_ref="payload:ticket-backend-api",
                graph_version=2,
                event_type=EventType.TICKET_BLOCKED,
            ),
            _ticket_event(graph_version=1),
        )
    )

    assert graph.graph_version == 2
    assert graph.nodes[TicketId(value="ticket-backend-api")].status is TicketStatus.BLOCKED
    assert resolver.created_calls == ["payload:ticket-backend-api"]
    assert resolver.blocked_calls == ["payload:ticket-backend-api"]
