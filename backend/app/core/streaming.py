from __future__ import annotations

import json
from collections.abc import Iterator

from app.contracts.events import EventStreamEnvelope, EventStreamItem, UIHint
from app.core.constants import SCHEMA_VERSION, STREAM_TYPE
from app.core.time import now_local
from app.db.repository import ControlPlaneRepository


def _encode_sse(event_name: str, payload: dict) -> str:
    return f"event: {event_name}\ndata: {json.dumps(payload, default=str)}\n\n"


def stream_events(repository: ControlPlaneRepository, after: str | None = None) -> Iterator[str]:
    repository.initialize()

    for event in repository.list_stream_events(after=after):
        envelope = EventStreamEnvelope(
            stream_type=STREAM_TYPE,
            cursor=event["event_id"],
            projection_version_hint=event["projection_version_hint"],
            events=[
                EventStreamItem(
                    event_id=event["event_id"],
                    occurred_at=event["occurred_at"],
                    category=event["category"],
                    severity=event["severity"],
                    event_type=event["event_type"],
                    workflow_id=event["workflow_id"],
                    node_id=None,
                    ticket_id=None,
                    causation_id=event["causation_id"],
                    related_command_id=None,
                    ui_hint=UIHint(**event["ui_hint"]),
                )
            ],
        )
        yield _encode_sse("boardroom-event", envelope.model_dump(mode="json"))

    cursor, version = repository.get_cursor_and_version()
    heartbeat = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": now_local().isoformat(),
        "cursor": cursor,
        "projection_version_hint": version,
        "type": "heartbeat",
    }
    yield _encode_sse("heartbeat", heartbeat)
