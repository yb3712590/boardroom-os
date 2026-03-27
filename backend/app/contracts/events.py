from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from app.contracts.common import StrictModel


class EventCategory(StrEnum):
    WORKFLOW = "workflow"
    SYSTEM = "system"


class EventSeverity(StrEnum):
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class UIHint(StrictModel):
    invalidate: list[str]
    refresh_policy: str
    refresh_after_ms: int
    toast: str | None = None


class EventStreamItem(StrictModel):
    event_id: str
    occurred_at: datetime
    category: EventCategory
    severity: EventSeverity
    event_type: str
    workflow_id: str | None = None
    node_id: str | None = None
    ticket_id: str | None = None
    causation_id: str | None = None
    related_command_id: str | None = None
    ui_hint: UIHint


class EventStreamEnvelope(StrictModel):
    stream_type: str
    cursor: str | None
    projection_version_hint: int
    events: list[EventStreamItem]
