from __future__ import annotations

import json

import app.core.runtime as runtime_module
from app.core.runtime import RuntimeExecutionResult, run_leased_ticket_runtime
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


def _seed_worker(repository, *, employee_id: str, provider_id: str) -> None:
    with repository.transaction() as connection:
        connection.execute(
            """
            INSERT OR REPLACE INTO employee_projection (
                employee_id,
                role_type,
                skill_profile_json,
                personality_profile_json,
                aesthetic_profile_json,
                state,
                board_approved,
                provider_id,
                role_profile_refs_json,
                updated_at,
                version
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                employee_id,
                "frontend_engineer",
                "{}",
                "{}",
                "{}",
                "ACTIVE",
                1,
                provider_id,
                json.dumps(["ui_designer_primary"], sort_keys=True),
                "2026-03-28T10:00:00+08:00",
                1,
            ),
    )


def _runtime_success_result(
    *,
    summary: str = "Runtime produced a structured UI milestone review.",
    payload: dict | None = None,
    written_artifacts: list[dict] | None = None,
) -> RuntimeExecutionResult:
    return RuntimeExecutionResult(
        result_status="completed",
        completion_summary=summary,
        artifact_refs=["art://runtime/homepage/option-a.png", "art://runtime/homepage/option-b.png"],
        result_payload=payload
        or {
            "summary": "Runtime produced a structured UI milestone review.",
            "recommended_option_id": "option_a",
            "options": [
                {
                    "option_id": "option_a",
                    "label": "Option A",
                    "summary": "Primary runtime-generated option.",
                    "artifact_refs": ["art://runtime/homepage/option-a.png"],
                },
                {
                    "option_id": "option_b",
                    "label": "Option B",
                    "summary": "Fallback runtime-generated option.",
                    "artifact_refs": ["art://runtime/homepage/option-b.png"],
                },
            ],
        },
        written_artifacts=written_artifacts
        or [
            {
                "path": "artifacts/ui/homepage/option-a.png",
                "artifact_ref": "art://runtime/homepage/option-a.png",
                "kind": "IMAGE",
            },
            {
                "path": "artifacts/ui/homepage/option-b.png",
                "artifact_ref": "art://runtime/homepage/option-b.png",
                "kind": "IMAGE",
            },
        ],
        assumptions=["Runtime used the minimal compiled context bundle."],
        issues=[],
        confidence=0.75,
    )


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
    latest_bundle = client.app.state.repository.get_latest_compiled_context_bundle_by_ticket(
        "tkt_runner_ui"
    )
    latest_manifest = client.app.state.repository.get_latest_compile_manifest_by_ticket(
        "tkt_runner_ui"
    )
    ticket_projection = client.app.state.repository.get_current_ticket_projection("tkt_runner_ui")
    node_projection = client.app.state.repository.get_current_node_projection("wf_runner", "node_runner_ui")

    assert ack.status.value == "ACCEPTED"
    assert ack.causation_hint == "scheduler:tick"
    assert latest_bundle is not None
    assert latest_manifest is not None
    assert latest_bundle["payload"]["meta"]["ticket_id"] == "tkt_runner_ui"
    assert latest_manifest["payload"]["compile_meta"]["ticket_id"] == "tkt_runner_ui"
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


def test_scheduler_runner_marks_started_then_failed_for_unsupported_compiled_execution(client, set_ticket_time):
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
    latest_bundle = repository.get_latest_compiled_context_bundle_by_ticket("tkt_runner_fail")
    latest_manifest = repository.get_latest_compile_manifest_by_ticket("tkt_runner_fail")
    ticket_projection = repository.get_current_ticket_projection("tkt_runner_fail")
    events = repository.list_events_for_testing()
    started_events = [event for event in events if event["event_type"] == "TICKET_STARTED"]
    failed_events = [event for event in events if event["event_type"] == "TICKET_FAILED"]

    assert latest_bundle is not None
    assert latest_manifest is not None
    assert latest_bundle["payload"]["context_blocks"][0]["source_kind"] == "ARTIFACT_REFERENCE"
    assert latest_manifest["payload"]["degradation"]["is_degraded"] is True
    assert ticket_projection["status"] == "FAILED"
    assert started_events
    assert failed_events
    assert failed_events[-1]["payload"]["failure_kind"] == "UNSUPPORTED_RUNTIME_EXECUTION"
    assert "unsupported_schema_v1" in failed_events[-1]["payload"]["failure_message"]
    assert failed_events[-1]["payload"]["failure_detail"]["compiler_version"] == "context-compiler.min.v1"


def test_scheduler_runner_fails_closed_when_ticket_create_spec_disappears(client, set_ticket_time):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    client.post(
        "/api/v1/commands/ticket-create",
        json=_ticket_create_payload(
            workflow_id="wf_runner_missing_spec",
            ticket_id="tkt_runner_missing_spec",
            node_id="node_runner_missing_spec",
            role_profile_ref="ui_designer_primary",
        ),
    )
    client.post(
        "/api/v1/commands/ticket-lease",
        json={
            "workflow_id": "wf_runner_missing_spec",
            "ticket_id": "tkt_runner_missing_spec",
            "node_id": "node_runner_missing_spec",
            "leased_by": "emp_frontend_2",
            "lease_timeout_sec": 600,
            "idempotency_key": "ticket-lease:wf_runner_missing_spec:tkt_runner_missing_spec",
        },
    )

    repository = client.app.state.repository
    with repository.transaction() as connection:
        connection.execute(
            """
            DELETE FROM events
            WHERE event_type = 'TICKET_CREATED' AND json_extract(payload_json, '$.ticket_id') = ?
            """,
            ("tkt_runner_missing_spec",),
        )

    run_scheduler_once(
        repository,
        idempotency_key="scheduler-runner:test-missing-spec",
        max_dispatches=10,
    )

    ticket_projection = repository.get_current_ticket_projection("tkt_runner_missing_spec")
    failed_events = [
        event for event in repository.list_events_for_testing() if event["event_type"] == "TICKET_FAILED"
    ]

    assert ticket_projection["status"] == "FAILED"
    assert failed_events[-1]["payload"]["failure_kind"] == "RUNTIME_INPUT_ERROR"
    assert "runtime compilation" in failed_events[-1]["payload"]["failure_message"]
    assert failed_events[-1]["payload"]["failure_detail"]["compiler_version"] == "context-compiler.min.v1"


def test_scheduler_runner_fails_closed_when_worker_projection_disappears(client, set_ticket_time):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    client.post(
        "/api/v1/commands/ticket-create",
        json=_ticket_create_payload(
            workflow_id="wf_runner_missing_worker",
            ticket_id="tkt_runner_missing_worker",
            node_id="node_runner_missing_worker",
            role_profile_ref="ui_designer_primary",
        ),
    )
    client.post(
        "/api/v1/commands/ticket-lease",
        json={
            "workflow_id": "wf_runner_missing_worker",
            "ticket_id": "tkt_runner_missing_worker",
            "node_id": "node_runner_missing_worker",
            "leased_by": "emp_frontend_2",
            "lease_timeout_sec": 600,
            "idempotency_key": "ticket-lease:wf_runner_missing_worker:tkt_runner_missing_worker",
        },
    )

    repository = client.app.state.repository
    with repository.transaction() as connection:
        connection.execute(
            "DELETE FROM employee_projection WHERE employee_id = ?",
            ("emp_frontend_2",),
        )

    run_scheduler_once(
        repository,
        idempotency_key="scheduler-runner:test-missing-worker",
        max_dispatches=10,
    )

    ticket_projection = repository.get_current_ticket_projection("tkt_runner_missing_worker")
    failed_events = [
        event for event in repository.list_events_for_testing() if event["event_type"] == "TICKET_FAILED"
    ]

    assert ticket_projection["status"] == "FAILED"
    assert failed_events[-1]["payload"]["failure_kind"] == "RUNTIME_INPUT_ERROR"
    assert "missing from employee_projection" in failed_events[-1]["payload"]["failure_message"]
    assert failed_events[-1]["payload"]["failure_detail"]["compiler_version"] == "context-compiler.min.v1"


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


def test_runtime_skips_later_leased_tickets_after_provider_pause_opens(client, set_ticket_time, monkeypatch):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    repository = client.app.state.repository
    _seed_worker(repository, employee_id="emp_frontend_backup", provider_id="prov_openai_compat")

    client.post(
        "/api/v1/commands/ticket-create",
        json=_ticket_create_payload(
            workflow_id="wf_runner_provider_pause",
            ticket_id="tkt_runner_provider_pause_1",
            node_id="node_runner_provider_pause_1",
            role_profile_ref="ui_designer_primary",
        ),
    )
    client.post(
        "/api/v1/commands/ticket-create",
        json=_ticket_create_payload(
            workflow_id="wf_runner_provider_pause",
            ticket_id="tkt_runner_provider_pause_2",
            node_id="node_runner_provider_pause_2",
            role_profile_ref="ui_designer_primary",
        ),
    )
    client.post(
        "/api/v1/commands/ticket-lease",
        json={
            "workflow_id": "wf_runner_provider_pause",
            "ticket_id": "tkt_runner_provider_pause_1",
            "node_id": "node_runner_provider_pause_1",
            "leased_by": "emp_frontend_2",
            "lease_timeout_sec": 600,
            "idempotency_key": "ticket-lease:wf_runner_provider_pause:tkt_runner_provider_pause_1",
        },
    )
    client.post(
        "/api/v1/commands/ticket-lease",
        json={
            "workflow_id": "wf_runner_provider_pause",
            "ticket_id": "tkt_runner_provider_pause_2",
            "node_id": "node_runner_provider_pause_2",
            "leased_by": "emp_frontend_backup",
            "lease_timeout_sec": 600,
            "idempotency_key": "ticket-lease:wf_runner_provider_pause:tkt_runner_provider_pause_2",
        },
    )

    executed_ticket_ids: list[str] = []

    def _fake_execute(execution_package):
        executed_ticket_ids.append(execution_package.meta.ticket_id)
        if execution_package.meta.ticket_id == "tkt_runner_provider_pause_1":
            return RuntimeExecutionResult(
                result_status="failed",
                failure_kind="PROVIDER_RATE_LIMITED",
                failure_message="Provider quota exhausted.",
                failure_detail={"provider_id": "prov_openai_compat"},
            )
        return RuntimeExecutionResult(
            result_status="completed",
            completion_summary="Completed after pause should not happen.",
        )

    monkeypatch.setattr(runtime_module, "_execute_compiled_execution_package", _fake_execute)

    outcomes = run_leased_ticket_runtime(repository)
    first_ticket = repository.get_current_ticket_projection("tkt_runner_provider_pause_1")
    second_ticket = repository.get_current_ticket_projection("tkt_runner_provider_pause_2")

    assert [outcome.ticket_id for outcome in outcomes] == ["tkt_runner_provider_pause_1"]
    assert executed_ticket_ids == ["tkt_runner_provider_pause_1"]
    assert first_ticket["status"] == "FAILED"
    assert second_ticket["status"] == "LEASED"


def test_scheduler_runner_auto_closes_recovering_incident_after_followup_success(client, set_ticket_time):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    client.post(
        "/api/v1/commands/ticket-create",
        json={
            **_ticket_create_payload(
                workflow_id="wf_runner_recovery",
                ticket_id="tkt_runner_recovery",
                node_id="node_runner_recovery",
                role_profile_ref="ui_designer_primary",
            ),
            "retry_budget": 2,
        },
    )

    client.post(
        "/api/v1/commands/ticket-lease",
        json={
            "workflow_id": "wf_runner_recovery",
            "ticket_id": "tkt_runner_recovery",
            "node_id": "node_runner_recovery",
            "leased_by": "emp_frontend_2",
            "lease_timeout_sec": 600,
            "idempotency_key": "ticket-lease:wf_runner_recovery:tkt_runner_recovery",
        },
    )
    client.post(
        "/api/v1/commands/ticket-start",
        json={
            "workflow_id": "wf_runner_recovery",
            "ticket_id": "tkt_runner_recovery",
            "node_id": "node_runner_recovery",
            "started_by": "emp_frontend_2",
            "idempotency_key": "ticket-start:wf_runner_recovery:tkt_runner_recovery",
        },
    )

    set_ticket_time("2026-03-28T10:31:00+08:00")
    client.post(
        "/api/v1/commands/scheduler-tick",
        json={"max_dispatches": 10, "idempotency_key": "scheduler-tick:runner-recovery-first"},
    )

    repository = client.app.state.repository
    second_ticket_id = repository.get_current_node_projection(
        "wf_runner_recovery",
        "node_runner_recovery",
    )["latest_ticket_id"]

    set_ticket_time("2026-03-28T10:32:00+08:00")
    client.post(
        "/api/v1/commands/ticket-start",
        json={
            "workflow_id": "wf_runner_recovery",
            "ticket_id": second_ticket_id,
            "node_id": "node_runner_recovery",
            "started_by": "emp_frontend_2",
                "idempotency_key": f"ticket-start:wf_runner_recovery:{second_ticket_id}",
            },
        )

    set_ticket_time("2026-03-28T11:18:00+08:00")
    client.post(
        "/api/v1/commands/scheduler-tick",
        json={"max_dispatches": 10, "idempotency_key": "scheduler-tick:runner-recovery-second"},
    )

    incident_id = [
        event["payload"]["incident_id"]
        for event in repository.list_events_for_testing()
        if event["event_type"] == "INCIDENT_OPENED"
    ][0]

    set_ticket_time("2026-03-28T11:20:00+08:00")
    client.post(
        "/api/v1/commands/incident-resolve",
        json={
            "incident_id": incident_id,
            "resolved_by": "emp_ops_1",
            "resolution_summary": "Retry after mitigation.",
            "followup_action": "RESTORE_AND_RETRY_LATEST_TIMEOUT",
            "idempotency_key": "incident-resolve:runner-recovery",
        },
    )

    followup_ticket_id = repository.get_current_node_projection(
        "wf_runner_recovery",
        "node_runner_recovery",
    )["latest_ticket_id"]

    set_ticket_time("2026-03-28T11:21:00+08:00")
    run_scheduler_once(
        repository,
        idempotency_key="scheduler-runner:recovery-close",
        max_dispatches=10,
    )

    incident_projection = repository.get_incident_projection(incident_id)
    followup_ticket = repository.get_current_ticket_projection(followup_ticket_id)

    assert followup_ticket["status"] == "COMPLETED"
    assert incident_projection["status"] == "CLOSED"
    assert incident_projection["closed_at"] is not None


def test_scheduler_runner_routes_success_results_through_schema_validation(client, set_ticket_time, monkeypatch):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    client.post(
        "/api/v1/commands/ticket-create",
        json=_ticket_create_payload(
            workflow_id="wf_runner_schema_guard",
            ticket_id="tkt_runner_schema_guard",
            node_id="node_runner_schema_guard",
            role_profile_ref="ui_designer_primary",
            input_artifact_refs=["art://inputs/runtime-brief.md"],
        ),
    )

    def _fake_execute(_execution_package):
        return _runtime_success_result(
            payload={
                "summary": "Missing options should trip structured-result validation.",
                "recommended_option_id": "option_a",
            }
        )

    monkeypatch.setattr(runtime_module, "_execute_compiled_execution_package", _fake_execute)

    run_scheduler_once(
        client.app.state.repository,
        idempotency_key="scheduler-runner:test-schema-guard",
        max_dispatches=10,
    )

    repository = client.app.state.repository
    ticket_projection = repository.get_current_ticket_projection("tkt_runner_schema_guard")
    failed_events = [
        event for event in repository.list_events_for_testing() if event["event_type"] == "TICKET_FAILED"
    ]

    assert ticket_projection["status"] == "FAILED"
    assert failed_events[-1]["payload"]["failure_kind"] == "SCHEMA_ERROR"
    assert "Result payload.options must be a non-empty array." in failed_events[-1]["payload"]["failure_message"]


def test_scheduler_runner_routes_success_results_through_write_set_validation(
    client,
    set_ticket_time,
    monkeypatch,
):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    client.post(
        "/api/v1/commands/ticket-create",
        json=_ticket_create_payload(
            workflow_id="wf_runner_write_set_guard",
            ticket_id="tkt_runner_write_set_guard",
            node_id="node_runner_write_set_guard",
            role_profile_ref="ui_designer_primary",
        ),
    )

    def _fake_execute(_execution_package):
        return _runtime_success_result(
            written_artifacts=[
                {
                    "path": "artifacts/forbidden/option-a.png",
                    "artifact_ref": "art://runtime/homepage/option-a.png",
                    "kind": "IMAGE",
                }
            ]
        )

    monkeypatch.setattr(runtime_module, "_execute_compiled_execution_package", _fake_execute)

    run_scheduler_once(
        client.app.state.repository,
        idempotency_key="scheduler-runner:test-write-set-guard",
        max_dispatches=10,
    )

    repository = client.app.state.repository
    ticket_projection = repository.get_current_ticket_projection("tkt_runner_write_set_guard")
    failed_events = [
        event for event in repository.list_events_for_testing() if event["event_type"] == "TICKET_FAILED"
    ]

    assert ticket_projection["status"] == "FAILED"
    assert failed_events[-1]["payload"]["failure_kind"] == "WRITE_SET_VIOLATION"
    assert failed_events[-1]["payload"]["failure_detail"]["violating_paths"] == [
        "artifacts/forbidden/option-a.png"
    ]
