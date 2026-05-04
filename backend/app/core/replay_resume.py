from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any

from app.contracts.replay import ReplayResumeRequest, ReplayResumeResult, ReplayWatermark
from app.core.constants import SCHEMA_VERSION

REPLAY_RESUME_CONTRACT_VERSION = "replay-resume.v1"
RESUME_KIND_EVENT_ID = "event_id"


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _event_payload(event: dict[str, Any]) -> dict[str, Any]:
    payload = event.get("payload")
    if isinstance(payload, dict):
        return payload
    payload_json = event.get("payload_json")
    if isinstance(payload_json, str):
        return json.loads(payload_json)
    return {}


def _normalize_occurred_at(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _normalize_event_for_hash(event: dict[str, Any]) -> dict[str, Any]:
    return {
        "sequence_no": int(event["sequence_no"]),
        "event_id": str(event["event_id"]),
        "event_type": str(event["event_type"]),
        "workflow_id": event.get("workflow_id"),
        "occurred_at": _normalize_occurred_at(event.get("occurred_at")),
        "payload": _event_payload(event),
    }


def _failed_result(
    request: ReplayResumeRequest,
    *,
    reason_code: str,
    message: str,
    details: dict[str, Any] | None = None,
) -> ReplayResumeResult:
    diagnostic = {
        "reason_code": reason_code,
        "message": message,
        **(details or {}),
    }
    return ReplayResumeResult(
        status="FAILED",
        resume_request=request,
        replay_watermark=None,
        event_cursor=request.event_cursor,
        projection_version=request.projection_version,
        event_range=None,
        schema_version=request.schema_version,
        contract_version=request.contract_version,
        diagnostic=diagnostic,
    )


def build_replay_resume_request(
    *,
    resume_kind: str,
    event_cursor: str | None,
    projection_version: int | None,
    event_range: dict[str, int] | None = None,
    schema_version: str = SCHEMA_VERSION,
    contract_version: str = REPLAY_RESUME_CONTRACT_VERSION,
    diagnostic: dict[str, Any] | None = None,
) -> ReplayResumeRequest:
    request_payload = {
        "resume_kind": resume_kind,
        "event_cursor": event_cursor,
        "projection_version": projection_version,
        "event_range": event_range,
        "schema_version": schema_version,
        "contract_version": contract_version,
        "diagnostic": diagnostic or {},
    }
    return ReplayResumeRequest(
        **request_payload,
        request_hash=_sha256(request_payload),
    )


def _event_log_hash(events: list[dict[str, Any]]) -> str:
    return _sha256([_normalize_event_for_hash(event) for event in events])


def build_replay_watermark(
    events: list[dict[str, Any]],
    request: ReplayResumeRequest,
    event_range: dict[str, int],
) -> ReplayWatermark:
    if request.event_cursor is None or request.projection_version is None:
        raise ValueError("event cursor and projection version are required")
    event_log_hash = _event_log_hash(events)
    watermark_payload = {
        "resume_kind": request.resume_kind,
        "event_cursor": request.event_cursor,
        "projection_version": request.projection_version,
        "event_range": event_range,
        "schema_version": request.schema_version,
        "contract_version": request.contract_version,
        "event_log_hash": event_log_hash,
        "request_hash": request.request_hash,
    }
    return ReplayWatermark(
        **watermark_payload,
        watermark_hash=_sha256(watermark_payload),
    )


def _events_through_cursor(
    events: list[dict[str, Any]],
    cursor_event: dict[str, Any],
) -> list[dict[str, Any]]:
    cursor_sequence_no = int(cursor_event["sequence_no"])
    return [
        event
        for event in sorted(events, key=lambda item: int(item["sequence_no"]))
        if int(event["sequence_no"]) <= cursor_sequence_no
    ]


def _first_missing_sequence_no(events: list[dict[str, Any]], *, start_sequence_no: int = 1) -> int | None:
    if not events:
        return start_sequence_no
    sorted_sequence_numbers = sorted(int(event["sequence_no"]) for event in events)
    expected = start_sequence_no
    for sequence_no in sorted_sequence_numbers:
        if sequence_no != expected:
            return expected
        expected += 1
    return None


def resume_replay_from_event_id(
    events: list[dict[str, Any]],
    request: ReplayResumeRequest,
) -> ReplayResumeResult:
    if request.resume_kind != RESUME_KIND_EVENT_ID:
        return _failed_result(
            request,
            reason_code="unsupported_resume_kind",
            message="Only event_id replay resume is supported in Round 10A.",
            details={"resume_kind": request.resume_kind},
        )
    if not request.event_cursor:
        return _failed_result(
            request,
            reason_code="missing_event_cursor",
            message="Replay resume requires an event cursor.",
        )

    cursor_event = next(
        (event for event in events if str(event.get("event_id")) == request.event_cursor),
        None,
    )
    if cursor_event is None:
        return _failed_result(
            request,
            reason_code="event_cursor_out_of_range",
            message="Replay resume event cursor was not found in the event log.",
            details={"event_cursor": request.event_cursor},
        )

    expected_projection_version = int(cursor_event["sequence_no"])
    if request.projection_version != expected_projection_version:
        return _failed_result(
            request,
            reason_code="projection_version_mismatch",
            message="Replay resume projection version must match the cursor event sequence.",
            details={
                "expected_projection_version": expected_projection_version,
                "actual_projection_version": request.projection_version,
            },
        )

    replay_events = _events_through_cursor(events, cursor_event)
    missing_sequence_no = _first_missing_sequence_no(replay_events)
    if missing_sequence_no is not None:
        return _failed_result(
            request,
            reason_code="event_range_not_contiguous",
            message="Replay resume event range is not contiguous.",
            details={"missing_sequence_no": missing_sequence_no},
        )

    start_sequence_no = min(int(event["sequence_no"]) for event in replay_events)
    event_range = {
        "start_sequence_no": start_sequence_no,
        "end_sequence_no": expected_projection_version,
    }
    watermark = build_replay_watermark(replay_events, request, event_range)
    return ReplayResumeResult(
        status="READY",
        resume_request=request,
        replay_watermark=watermark,
        event_cursor=request.event_cursor,
        projection_version=request.projection_version,
        event_range=event_range,
        schema_version=request.schema_version,
        contract_version=request.contract_version,
        diagnostic={
            "reason_code": "resume_ready",
            "message": "Replay resume point is ready.",
        },
    )
