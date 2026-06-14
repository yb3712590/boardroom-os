from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from boardroom_os.events.record import EventRecord
from boardroom_os.events.types import (
    ActorRef,
    EventId,
    EventPayloadRef,
    EventRef,
    EventType,
    ProjectRef,
)


def _valid_event_record(**overrides: object) -> EventRecord:
    values = {
        "event_id": EventId(value="evt-ticket-created-001"),
        "event_type": EventType.TICKET_CREATED,
        "project_ref": ProjectRef(value="project-tiny-fullstack"),
        "actor_ref": ActorRef(value="seat-architect"),
        "timestamp": datetime(2026, 5, 15, 10, 30, tzinfo=UTC),
        "graph_version": 1,
        "payload_refs": (EventPayloadRef(value="ticket:ticket-backend-api"),),
        "causation_refs": (EventRef(value="evt-contract-gate-passed"),),
        "correlation_refs": (EventRef(value="corr-board-directive-001"),),
    }
    values.update(overrides)
    return EventRecord(**values)


@pytest.mark.parametrize(
    "missing_field",
    ["actor_ref", "timestamp", "graph_version", "payload_refs"],
)
def test_event_record_requires_actor_timestamp_graph_version_and_payload_refs(
    missing_field: str,
) -> None:
    values = _valid_event_record().model_dump()
    values.pop(missing_field)

    with pytest.raises(ValidationError):
        EventRecord(**values)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("actor_ref", {"value": " "}),
        ("graph_version", 0),
        ("payload_refs", ()),
        ("timestamp", datetime(2026, 5, 15, 10, 30)),
        ("event_type", "made_up_event"),
    ],
)
def test_event_record_rejects_invalid_core_fields(field: str, value: object) -> None:
    with pytest.raises(ValidationError):
        _valid_event_record(**{field: value})


def test_event_record_preserves_event_type_enum_for_reducer_branching() -> None:
    event = _valid_event_record()

    assert event.event_type is EventType.TICKET_CREATED


def test_event_record_accepts_rework_event_types() -> None:
    rework_event_types = (
        EventType.REWORK_REQUESTED,
        EventType.REWORK_PLANNED,
        EventType.REWORK_GRAPH_PATCH_REVIEWED,
        EventType.REWORK_GRAPH_PATCH_APPROVED,
        EventType.REWORK_TICKET_CREATED,
        EventType.REWORK_ATTEMPT_STARTED,
        EventType.REWORK_ATTEMPT_SUBMITTED,
        EventType.REWORK_REVIEWED,
        EventType.REWORK_ACCEPTED,
        EventType.REWORK_ESCALATED,
        EventType.REWORK_EXHAUSTED,
    )

    for index, event_type in enumerate(rework_event_types, start=10):
        event = _valid_event_record(
            event_id=EventId(value=f"evt-rework-{event_type.value}"),
            event_type=event_type,
            payload_refs=(EventPayloadRef(value=f"payload:{event_type.value}"),),
            graph_version=index,
        )

        assert event.event_type is event_type
        assert event.stable_dump()["event_type"] == event_type.value


def test_event_record_stably_serializes_and_preserves_causation_and_correlation_refs() -> None:
    event = _valid_event_record()

    assert event.stable_dump() == {
        "actor_ref": {"value": "seat-architect"},
        "causation_refs": [{"value": "evt-contract-gate-passed"}],
        "correlation_refs": [{"value": "corr-board-directive-001"}],
        "event_id": {"value": "evt-ticket-created-001"},
        "event_type": "ticket_created",
        "graph_version": 1,
        "payload_refs": [{"value": "ticket:ticket-backend-api"}],
        "project_ref": {"value": "project-tiny-fullstack"},
        "timestamp": "2026-05-15T10:30:00+00:00",
    }


def test_event_record_stable_dump_can_be_replayed_into_event_record() -> None:
    event = _valid_event_record()

    replayed = EventRecord(**event.stable_dump())

    assert replayed == event
