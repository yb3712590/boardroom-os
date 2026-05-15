from datetime import UTC, datetime, timedelta

import pytest

from boardroom_os.events.log import EventLogAppendError, InMemoryEventLog
from boardroom_os.events.record import EventRecord
from boardroom_os.events.types import (
    ActorRef,
    EventId,
    EventPayloadRef,
    EventType,
    ProjectRef,
)


BASE_TIMESTAMP = datetime(2026, 5, 15, 11, 0, tzinfo=UTC)


def _event_record(
    *,
    event_id: str = "evt-project-a-001",
    event_type: EventType = EventType.TICKET_CREATED,
    project_ref: str = "project-a",
    graph_version: int = 1,
    minute_offset: int = 0,
) -> EventRecord:
    return EventRecord(
        event_id=EventId(value=event_id),
        event_type=event_type,
        project_ref=ProjectRef(value=project_ref),
        actor_ref=ActorRef(value="seat-architect"),
        timestamp=BASE_TIMESTAMP + timedelta(minutes=minute_offset),
        graph_version=graph_version,
        payload_refs=(EventPayloadRef(value=f"payload:{event_id}"),),
    )


def test_event_log_rejects_graph_version_rollback_within_project() -> None:
    log = InMemoryEventLog()
    log.append(_event_record(event_id="evt-project-a-002", graph_version=2))

    with pytest.raises(EventLogAppendError, match="graph_version"):
        log.append(_event_record(event_id="evt-project-a-001", graph_version=1))


def test_event_log_rejects_duplicate_event_id() -> None:
    log = InMemoryEventLog()
    log.append(_event_record(event_id="evt-duplicate", graph_version=1))

    with pytest.raises(EventLogAppendError, match="event_id"):
        log.append(_event_record(event_id="evt-duplicate", graph_version=2))


def test_event_log_rejects_unknown_event_type_even_if_record_was_constructed_unsafely() -> None:
    invalid_event = EventRecord.model_construct(
        event_id=EventId(value="evt-invalid-type"),
        event_type="made_up_event",
        project_ref=ProjectRef(value="project-a"),
        actor_ref=ActorRef(value="seat-architect"),
        timestamp=BASE_TIMESTAMP,
        graph_version=1,
        payload_refs=(EventPayloadRef(value="payload:invalid"),),
        causation_refs=(),
        correlation_refs=(),
    )

    with pytest.raises(EventLogAppendError, match="event_type"):
        InMemoryEventLog().append(invalid_event)


def test_event_log_allows_independent_project_version_sequences() -> None:
    log = InMemoryEventLog()
    project_a_event = _event_record(
        event_id="evt-project-a-001",
        project_ref="project-a",
        graph_version=1,
    )
    project_b_event = _event_record(
        event_id="evt-project-b-001",
        project_ref="project-b",
        graph_version=1,
    )

    log.append(project_a_event)
    log.append(project_b_event)

    assert log.read(ProjectRef(value="project-a")) == (project_a_event,)
    assert log.read(ProjectRef(value="project-b")) == (project_b_event,)


def test_event_log_reads_project_events_by_graph_version_range() -> None:
    log = InMemoryEventLog()
    project_a_v1 = _event_record(event_id="evt-project-a-001", graph_version=1)
    project_a_v2 = _event_record(event_id="evt-project-a-002", graph_version=2, minute_offset=1)
    project_a_v3 = _event_record(event_id="evt-project-a-003", graph_version=3, minute_offset=2)
    project_b_v1 = _event_record(
        event_id="evt-project-b-001",
        project_ref="project-b",
        graph_version=1,
    )
    for event in (project_a_v1, project_b_v1, project_a_v2, project_a_v3):
        log.append(event)

    assert log.read(
        ProjectRef(value="project-a"),
        from_graph_version=2,
        to_graph_version=3,
    ) == (project_a_v2, project_a_v3)
