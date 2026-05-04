from __future__ import annotations

from typing import Literal

from app.contracts.common import JsonValue, StrictModel


ReplayStatus = Literal["READY", "FAILED"]


class ReplayResumeRequest(StrictModel):
    resume_kind: str
    event_cursor: str | None
    projection_version: int | None
    event_range: dict[str, int] | None
    schema_version: str
    contract_version: str
    request_hash: str
    diagnostic: dict[str, JsonValue]


class ReplayWatermark(StrictModel):
    resume_kind: str
    event_cursor: str
    projection_version: int
    event_range: dict[str, int]
    schema_version: str
    contract_version: str
    event_log_hash: str
    request_hash: str
    watermark_hash: str


class ReplayResumeResult(StrictModel):
    status: ReplayStatus
    resume_request: ReplayResumeRequest
    replay_watermark: ReplayWatermark | None
    event_cursor: str | None
    projection_version: int | None
    event_range: dict[str, int] | None
    schema_version: str
    contract_version: str
    diagnostic: dict[str, JsonValue]
