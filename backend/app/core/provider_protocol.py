from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class ProviderEventType(StrEnum):
    REQUEST_STARTED = "request_started"
    CONNECTED = "connected"
    FIRST_TOKEN = "first_token"
    CONTENT_DELTA = "content_delta"
    HEARTBEAT = "heartbeat"
    SCHEMA_CANDIDATE = "schema_candidate"
    COMPLETED = "completed"
    FAILED_RETRYABLE = "failed_retryable"
    FAILED_TERMINAL = "failed_terminal"


@dataclass(frozen=True)
class ProviderEvent:
    type: ProviderEventType
    provider_name: str
    model: str
    request_id: str
    attempt_id: str
    monotonic_ts: float
    raw_byte_count: int = 0
    text_char_count: int = 0
    error_category: str | None = None
    response_id: str | None = None
    metadata: dict[str, object] = field(default_factory=dict)
