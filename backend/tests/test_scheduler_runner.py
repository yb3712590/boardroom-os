from __future__ import annotations

from app.scheduler_runner import run_scheduler_loop, run_scheduler_once


def _ticket_create_payload(
    *,
    workflow_id: str,
    ticket_id: str,
    node_id: str,
    role_profile_ref: str,
    output_schema_ref: str = "ui_milestone_review",
    input_artifact_refs: list[str] | None = None,
) -> dict:
    return {
        "ticket_id": ticket_id,
        "workflow_id": workflow_id,
        "node_id": node_id,
        "parent_ticket_id": None,
        "attempt_no": 1,
        "role_profile_ref": role_profile_ref,
        "constraints_ref": "global_constraints_v3",
        "input_artifact_refs": input_artifact_refs or ["art://inputs/brief.md"],
        "context_query_plan": {
            "keywords": ["homepage"],
            "semantic_queries": ["approved direction"],
            "max_context_tokens": 3000,
        },
        "acceptance_criteria": ["Must produce a structured result"],
        "output_schema_ref": output_schema_ref,
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


def test_scheduler_runner_once_dispatches_using_persisted_roster(client, set_ticket_time):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    client.post(
        "/api/v1/commands/ticket-create",
        json=_ticket_create_payload(
            workflow_id="wf_runner",
            ticket_id="tkt_runner_ui",
            node_id="node_runner_ui",
            role_profile_ref="ui_designer_primary",
        ),
    )

    set_ticket_time("2026-03-28T10:01:00+08:00")
    ack = run_scheduler_once(
        client.app.state.repository,
        idempotency_key="scheduler-runner:test-once",
        max_dispatches=10,
    )
    ticket_projection = client.app.state.repository.get_current_ticket_projection("tkt_runner_ui")
    node_projection = client.app.state.repository.get_current_node_projection("wf_runner", "node_runner_ui")

    assert ack.status.value == "ACCEPTED"
    assert ack.causation_hint == "scheduler:tick"
    assert ticket_projection["status"] == "COMPLETED"
    assert ticket_projection["lease_owner"] is None
    assert node_projection["status"] == "COMPLETED"


def test_scheduler_runner_loop_respects_tick_limit_and_dispatch_budget(client, set_ticket_time):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    client.post(
        "/api/v1/commands/ticket-create",
        json=_ticket_create_payload(
            workflow_id="wf_runner",
            ticket_id="tkt_runner_checker",
            node_id="node_runner_checker",
            role_profile_ref="checker_primary",
        ),
    )
    client.post(
        "/api/v1/commands/ticket-create",
        json=_ticket_create_payload(
            workflow_id="wf_runner",
            ticket_id="tkt_runner_ui",
            node_id="node_runner_ui",
            role_profile_ref="ui_designer_primary",
        ),
    )

    sleep_calls: list[float] = []
    acknowledgements = run_scheduler_loop(
        client.app.state.repository,
        poll_interval_sec=12.5,
        max_dispatches=1,
        max_ticks=2,
        sleep_fn=sleep_calls.append,
    )

    checker_ticket = client.app.state.repository.get_current_ticket_projection("tkt_runner_checker")
    ui_ticket = client.app.state.repository.get_current_ticket_projection("tkt_runner_ui")
    completed_count = sum(
        1 for ticket in (checker_ticket, ui_ticket) if ticket is not None and ticket["status"] == "COMPLETED"
    )

    assert len(acknowledgements) == 2
    assert sleep_calls == [12.5]
    assert completed_count == 2


def test_scheduler_runner_marks_started_then_failed_for_unsupported_bridge_execution(client, set_ticket_time):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    client.post(
        "/api/v1/commands/ticket-create",
        json=_ticket_create_payload(
            workflow_id="wf_runner_fail",
            ticket_id="tkt_runner_fail",
            node_id="node_runner_fail",
            role_profile_ref="ui_designer_primary",
            output_schema_ref="unsupported_schema_v1",
        ),
    )

    run_scheduler_once(
        client.app.state.repository,
        idempotency_key="scheduler-runner:test-fail",
        max_dispatches=10,
    )

    repository = client.app.state.repository
    ticket_projection = repository.get_current_ticket_projection("tkt_runner_fail")
    events = repository.list_events_for_testing()
    started_events = [event for event in events if event["event_type"] == "TICKET_STARTED"]
    failed_events = [event for event in events if event["event_type"] == "TICKET_FAILED"]

    assert ticket_projection["status"] == "FAILED"
    assert started_events
    assert failed_events
    assert failed_events[-1]["payload"]["failure_kind"] == "UNSUPPORTED_RUNTIME_EXECUTION"
    assert "unsupported_schema_v1" in failed_events[-1]["payload"]["failure_message"]


def test_scheduler_runner_execution_events_are_visible_in_stream(client, set_ticket_time):
    initial_cursor = client.get("/api/v1/projections/dashboard").json()["cursor"]
    set_ticket_time("2026-03-28T10:00:00+08:00")
    client.post(
        "/api/v1/commands/ticket-create",
        json=_ticket_create_payload(
            workflow_id="wf_runner_stream",
            ticket_id="tkt_runner_stream",
            node_id="node_runner_stream",
            role_profile_ref="ui_designer_primary",
        ),
    )

    set_ticket_time("2026-03-28T10:01:00+08:00")
    run_scheduler_once(
        client.app.state.repository,
        idempotency_key="scheduler-runner:test-stream",
        max_dispatches=10,
    )

    with client.stream("GET", f"/api/v1/events/stream?after={initial_cursor}") as response:
        body = "".join(response.iter_text())

    assert response.status_code == 200
    assert "TICKET_LEASED" in body
    assert "TICKET_STARTED" in body
    assert "TICKET_COMPLETED" in body
