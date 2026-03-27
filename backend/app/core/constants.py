from __future__ import annotations

from datetime import timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

SCHEMA_VERSION = "2026-03-28.boardroom.v1"
try:
    BOARDROOM_TIMEZONE = ZoneInfo("Asia/Shanghai")
except ZoneInfoNotFoundError:
    BOARDROOM_TIMEZONE = timezone(timedelta(hours=8), name="Asia/Shanghai")

EVENT_SYSTEM_INITIALIZED = "SYSTEM_INITIALIZED"
EVENT_BOARD_DIRECTIVE_RECEIVED = "BOARD_DIRECTIVE_RECEIVED"
EVENT_WORKFLOW_CREATED = "WORKFLOW_CREATED"

SYSTEM_INITIALIZED_KEY = "system:initialized"

DEFAULT_WORKFLOW_STAGE = "project_init"
DEFAULT_WORKFLOW_STATUS = "EXECUTING"
DEFAULT_BOARD_GATE_STATE = "UNREQUESTED"

STREAM_TYPE = "boardroom_events"
