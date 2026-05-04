from __future__ import annotations

import json
from datetime import datetime

from app.core.constants import EVENT_TICKET_CREATED, EVENT_WORKFLOW_CREATED, SCHEMA_VERSION
from app.core.replay_resume import (
    REPLAY_RESUME_CONTRACT_VERSION,
    build_replay_resume_request,
    resume_replay_from_event_id,
)


def _event(
    sequence_no: int,
    event_id: str,
    event_type: str,
    payload: dict,
) -> dict:
    return {
        "sequence_no": sequence_no,
        "event_id": event_id,
        "event_type": event_type,
        "workflow_id": "wf_replay",
        "occurred_at": datetime.fromisoformat(f"2026-05-04T10:0{sequence_no}:00+08:00"),
        "payload_json": json.dumps(payload, sort_keys=True),
    }


def _events() -> list[dict]:
    return [
        _event(
            1,
            "evt_replay_001",
            EVENT_WORKFLOW_CREATED,
            {
                "north_star_goal": "Replay contract",
                "budget_cap": 500000,
                "deadline_at": None,
                "title": "Replay contract",
            },
        ),
        _event(
            2,
            "evt_replay_002",
            EVENT_TICKET_CREATED,
            {
                "ticket_id": "tkt_replay",
                "node_id": "node_replay",
                "retry_budget": 1,
                "timeout_sla_sec": 1800,
                "priority": "high",
            },
        ),
        _event(
            3,
            "evt_replay_003",
            EVENT_TICKET_CREATED,
            {
                "ticket_id": "tkt_replay_check",
                "node_id": "node_replay_check",
                "retry_budget": 1,
                "timeout_sla_sec": 1800,
                "priority": "normal",
            },
        ),
    ]


def test_resume_from_event_id_returns_explicit_watermark_boundary():
    request = build_replay_resume_request(
        resume_kind="event_id",
        event_cursor="evt_replay_002",
        projection_version=2,
    )

    result = resume_replay_from_event_id(_events(), request)

    assert result.status == "READY"
    assert result.event_cursor == "evt_replay_002"
    assert result.projection_version == 2
    assert result.event_range == {
        "start_sequence_no": 1,
        "end_sequence_no": 2,
    }
    assert result.schema_version == SCHEMA_VERSION
    assert result.contract_version == REPLAY_RESUME_CONTRACT_VERSION
    assert result.replay_watermark is not None
    assert result.replay_watermark.event_cursor == "evt_replay_002"
    assert result.replay_watermark.projection_version == 2
    assert result.replay_watermark.event_range == result.event_range
    assert result.replay_watermark.watermark_hash
    assert result.diagnostic == {
        "reason_code": "resume_ready",
        "message": "Replay resume point is ready.",
    }


def test_replay_watermark_is_stable_for_same_event_log_and_request():
    request = build_replay_resume_request(
        resume_kind="event_id",
        event_cursor="evt_replay_003",
        projection_version=3,
    )

    first = resume_replay_from_event_id(_events(), request)
    second = resume_replay_from_event_id(_events(), request)

    assert first.status == "READY"
    assert second.status == "READY"
    assert first.replay_watermark == second.replay_watermark
    assert first.replay_watermark is not None
    assert first.replay_watermark.watermark_hash == second.replay_watermark.watermark_hash


def test_resume_fails_closed_when_event_cursor_is_missing():
    request = build_replay_resume_request(
        resume_kind="event_id",
        event_cursor=None,
        projection_version=2,
    )

    result = resume_replay_from_event_id(_events(), request)

    assert result.status == "FAILED"
    assert result.replay_watermark is None
    assert result.diagnostic["reason_code"] == "missing_event_cursor"


def test_resume_fails_closed_when_event_cursor_is_out_of_range():
    request = build_replay_resume_request(
        resume_kind="event_id",
        event_cursor="evt_missing",
        projection_version=2,
    )

    result = resume_replay_from_event_id(_events(), request)

    assert result.status == "FAILED"
    assert result.replay_watermark is None
    assert result.diagnostic["reason_code"] == "event_cursor_out_of_range"


def test_resume_fails_closed_when_projection_version_mismatches_event_cursor():
    request = build_replay_resume_request(
        resume_kind="event_id",
        event_cursor="evt_replay_002",
        projection_version=3,
    )

    result = resume_replay_from_event_id(_events(), request)

    assert result.status == "FAILED"
    assert result.replay_watermark is None
    assert result.diagnostic["reason_code"] == "projection_version_mismatch"
    assert result.diagnostic["expected_projection_version"] == 2
    assert result.diagnostic["actual_projection_version"] == 3


def test_resume_fails_closed_when_event_range_is_not_contiguous():
    request = build_replay_resume_request(
        resume_kind="event_id",
        event_cursor="evt_replay_003",
        projection_version=3,
    )
    events = [
        _events()[0],
        _event(
            3,
            "evt_replay_003",
            EVENT_TICKET_CREATED,
            {
                "ticket_id": "tkt_replay_check",
                "node_id": "node_replay_check",
                "retry_budget": 1,
                "timeout_sla_sec": 1800,
                "priority": "normal",
            },
        ),
    ]

    result = resume_replay_from_event_id(events, request)

    assert result.status == "FAILED"
    assert result.replay_watermark is None
    assert result.diagnostic["reason_code"] == "event_range_not_contiguous"
    assert result.diagnostic["missing_sequence_no"] == 2


def test_resume_fails_closed_when_event_range_does_not_start_at_first_event():
    request = build_replay_resume_request(
        resume_kind="event_id",
        event_cursor="evt_replay_003",
        projection_version=3,
    )
    events = [
        _event(
            2,
            "evt_replay_002",
            EVENT_TICKET_CREATED,
            {
                "ticket_id": "tkt_replay",
                "node_id": "node_replay",
                "retry_budget": 1,
                "timeout_sla_sec": 1800,
                "priority": "high",
            },
        ),
        _events()[2],
    ]

    result = resume_replay_from_event_id(events, request)

    assert result.status == "FAILED"
    assert result.replay_watermark is None
    assert result.diagnostic["reason_code"] == "event_range_not_contiguous"
    assert result.diagnostic["missing_sequence_no"] == 1


def test_resume_rejects_non_event_id_kind_until_later_rounds():
    request = build_replay_resume_request(
        resume_kind="graph_version",
        event_cursor="evt_replay_002",
        projection_version=2,
    )

    result = resume_replay_from_event_id(_events(), request)

    assert result.status == "FAILED"
    assert result.replay_watermark is None
    assert result.diagnostic["reason_code"] == "unsupported_resume_kind"


def test_resume_normal_path_does_not_touch_projection_repair(monkeypatch, client):
    repository = client.app.state.repository
    called = {"refresh_projections": False}

    def _forbid_refresh_projections(*args, **kwargs):
        called["refresh_projections"] = True
        raise AssertionError("resume must not repair projection rows")

    monkeypatch.setattr(repository, "refresh_projections", _forbid_refresh_projections)
    request = build_replay_resume_request(
        resume_kind="event_id",
        event_cursor="evt_replay_002",
        projection_version=2,
    )

    result = resume_replay_from_event_id(_events(), request)

    assert result.status == "READY"
    assert called["refresh_projections"] is False
