from __future__ import annotations

import time

from fastapi.testclient import TestClient

from app.core.constants import TICKET_STATUS_PENDING


def _ticket_create_payload(
    *,
    workflow_id: str = "wf_inprocess",
    ticket_id: str = "tkt_inprocess_001",
    node_id: str = "node_inprocess_001",
    role_profile_ref: str = "frontend_engineer_primary",
) -> dict:
    return {
        "ticket_id": ticket_id,
        "workflow_id": workflow_id,
        "node_id": node_id,
        "parent_ticket_id": None,
        "attempt_no": 1,
        "role_profile_ref": role_profile_ref,
        "constraints_ref": "global_constraints_v3",
        "input_artifact_refs": ["art://inputs/brief.md"],
        "context_query_plan": {
            "keywords": ["homepage"],
            "semantic_queries": ["approved direction"],
            "max_context_tokens": 3000,
        },
        "acceptance_criteria": ["Must produce a structured result"],
        "output_schema_ref": "ui_milestone_review",
        "output_schema_version": 1,
        "allowed_tools": ["read_artifact"],
        "allowed_write_set": ["artifacts/ui/homepage/*"],
        "retry_budget": 1,
        "priority": "high",
        "timeout_sla_sec": 1800,
        "deadline_at": "2026-03-28T18:00:00+08:00",
        "escalation_policy": {
            "on_timeout": "retry",
            "on_schema_error": "retry",
            "on_repeat_failure": "escalate_ceo",
        },
        "idempotency_key": f"ticket-create:{workflow_id}:{ticket_id}",
    }


def _wait_until(predicate, timeout_sec: float = 0.5, sleep_sec: float = 0.01) -> None:
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(sleep_sec)
    raise AssertionError("Condition was not satisfied before timeout.")


def test_inprocess_scheduler_loop_runs_immediately_and_stops_cleanly():
    from app.core.inprocess_scheduler import InProcessSchedulerLoop

    tick_times: list[float] = []
    loop = InProcessSchedulerLoop(
        run_once=lambda: tick_times.append(time.monotonic()),
        poll_interval_sec=0.01,
        thread_name="test-inprocess-loop",
    )

    loop.start()
    _wait_until(lambda: len(tick_times) >= 2)

    loop.stop()
    stopped_count = len(tick_times)
    time.sleep(0.03)

    assert stopped_count >= 2
    assert len(tick_times) == stopped_count
    assert loop.is_running is False


def test_inprocess_scheduler_loop_start_and_stop_are_idempotent():
    from app.core.inprocess_scheduler import InProcessSchedulerLoop

    run_count = 0

    def _run_once() -> None:
        nonlocal run_count
        run_count += 1

    loop = InProcessSchedulerLoop(
        run_once=_run_once,
        poll_interval_sec=0.01,
        thread_name="test-inprocess-loop-idempotent",
    )

    loop.start()
    loop.start()
    _wait_until(lambda: run_count >= 1)
    loop.stop()
    loop.stop()

    assert run_count >= 1
    assert loop.is_running is False


def test_fastapi_inprocess_scheduler_is_disabled_by_default(monkeypatch, db_path, set_ticket_time):
    monkeypatch.delenv("BOARDROOM_OS_ENABLE_INPROCESS_SCHEDULER", raising=False)

    from app.main import create_app

    set_ticket_time("2026-03-28T10:00:00+08:00")
    with TestClient(create_app()) as client:
        response = client.post("/api/v1/commands/ticket-create", json=_ticket_create_payload())

        assert response.status_code == 200
        time.sleep(0.05)

        ticket_projection = client.app.state.repository.get_current_ticket_projection("tkt_inprocess_001")

        assert getattr(client.app.state, "inprocess_scheduler", None) is None
        assert ticket_projection["status"] == TICKET_STATUS_PENDING


def test_fastapi_inprocess_scheduler_completes_pending_ticket_when_enabled(
    monkeypatch,
    db_path,
    set_ticket_time,
):
    monkeypatch.setenv("BOARDROOM_OS_ENABLE_INPROCESS_SCHEDULER", "true")
    monkeypatch.setenv("BOARDROOM_OS_SCHEDULER_POLL_INTERVAL_SEC", "0.01")

    from app.main import create_app

    set_ticket_time("2026-03-28T10:00:00+08:00")
    with TestClient(create_app()) as client:
        response = client.post("/api/v1/commands/ticket-create", json=_ticket_create_payload())
        assert response.status_code == 200

        repository = client.app.state.repository
        _wait_until(
            lambda: repository.get_current_ticket_projection("tkt_inprocess_001")["status"] == "COMPLETED",
            timeout_sec=1.0,
        )

        ticket_projection = repository.get_current_ticket_projection("tkt_inprocess_001")
        bundle = repository.get_latest_compiled_context_bundle_by_ticket("tkt_inprocess_001")
        manifest = repository.get_latest_compile_manifest_by_ticket("tkt_inprocess_001")

        assert client.app.state.inprocess_scheduler is not None
        assert client.app.state.inprocess_scheduler.is_running is True
        assert ticket_projection["status"] == "COMPLETED"
        assert bundle is not None
        assert manifest is not None
