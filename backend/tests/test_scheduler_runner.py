from __future__ import annotations

import json
import importlib
from datetime import datetime

import app.core.runtime as runtime_module
from app.core.runtime import RuntimeExecutionResult, run_leased_ticket_runtime
from app.core.provider_openai_compat import (
    OpenAICompatProviderRateLimitedError,
    OpenAICompatProviderResult,
)
from app.scheduler_runner import run_scheduler_loop, run_scheduler_once


def _ticket_create_payload(
    *,
    workflow_id: str,
    ticket_id: str,
    node_id: str,
    role_profile_ref: str,
    output_schema_ref: str = "ui_milestone_review",
    input_artifact_refs: list[str] | None = None,
    excluded_employee_ids: list[str] | None = None,
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
        "excluded_employee_ids": excluded_employee_ids or [],
        "escalation_policy": {
            "on_timeout": "retry",
            "on_schema_error": "retry",
            "on_repeat_failure": "escalate_ceo",
        },
        "idempotency_key": f"ticket-create:{workflow_id}:{ticket_id}",
    }


def _project_init(client, goal: str = "Scheduler staffing") -> str:
    response = client.post(
        "/api/v1/commands/project-init",
        json={
            "north_star_goal": goal,
            "hard_constraints": ["Keep governance explicit."],
            "budget_cap": 500000,
            "deadline_at": None,
        },
    )
    assert response.status_code == 200
    assert response.json()["status"] == "ACCEPTED"
    return response.json()["causation_hint"].split(":", 1)[1]


def _approve_hire_worker(
    client,
    *,
    workflow_id: str,
    employee_id: str,
    provider_id: str = "prov_openai_compat",
) -> None:
    hire_response = client.post(
        "/api/v1/commands/employee-hire-request",
        json={
            "workflow_id": workflow_id,
            "employee_id": employee_id,
            "role_type": "frontend_engineer",
            "role_profile_refs": ["ui_designer_primary"],
            "skill_profile": {"primary_domain": "frontend"},
            "personality_profile": {"style": "maker"},
            "aesthetic_profile": {"preference": "minimal"},
            "provider_id": provider_id,
            "request_summary": "Hire backup worker for scheduler coverage.",
            "idempotency_key": f"employee-hire-request:{workflow_id}:{employee_id}",
        },
    )
    assert hire_response.status_code == 200
    assert hire_response.json()["status"] == "ACCEPTED"

    approval = client.app.state.repository.list_open_approvals()[0]
    option_id = approval["payload"]["review_pack"]["options"][0]["option_id"]
    approve_response = client.post(
        "/api/v1/commands/board-approve",
        json={
            "review_pack_id": approval["review_pack_id"],
            "review_pack_version": approval["review_pack_version"],
            "command_target_version": approval["command_target_version"],
            "approval_id": approval["approval_id"],
            "selected_option_id": option_id,
            "board_comment": "Approve backup staffing.",
            "idempotency_key": f"board-approve:{approval['approval_id']}:staffing",
        },
    )
    assert approve_response.status_code == 200
    assert approve_response.json()["status"] == "ACCEPTED"


def _seed_worker(repository, *, employee_id: str, provider_id: str) -> None:
    with repository.transaction() as connection:
        repository.insert_event(
            connection,
            event_type="EMPLOYEE_HIRED",
            actor_type="system",
            actor_id="test-seed",
            workflow_id=None,
            idempotency_key=f"test-seed-employee:{employee_id}",
            causation_id=None,
            correlation_id=None,
            payload={
                "employee_id": employee_id,
                "role_type": "frontend_engineer",
                "skill_profile": {},
                "personality_profile": {},
                "aesthetic_profile": {},
                "state": "ACTIVE",
                "board_approved": True,
                "provider_id": provider_id,
                "role_profile_refs": ["ui_designer_primary"],
            },
            occurred_at=datetime.fromisoformat("2026-03-28T10:00:00+08:00"),
        )
        repository.refresh_projections(connection)


def _seed_ephemeral_artifact_for_cleanup(
    client,
    *,
    artifact_ref: str,
    created_at: datetime,
    expires_at: datetime,
) -> None:
    repository = client.app.state.repository
    artifact_store = client.app.state.artifact_store
    materialized = artifact_store.materialize_text(
        "artifacts/runtime/cleanup/ephemeral.txt",
        "ephemeral cleanup payload\n",
    )
    with repository.transaction() as connection:
        repository.save_artifact_record(
            connection,
            artifact_ref=artifact_ref,
            workflow_id="wf_runner_cleanup",
            ticket_id="tkt_runner_cleanup",
            node_id="node_runner_cleanup",
            logical_path="artifacts/runtime/cleanup/ephemeral.txt",
            kind="TEXT",
            media_type="text/plain",
            materialization_status="MATERIALIZED",
            lifecycle_status="ACTIVE",
            storage_relpath=materialized.storage_relpath,
            content_hash=materialized.content_hash,
            size_bytes=materialized.size_bytes,
            retention_class="EPHEMERAL",
            expires_at=expires_at,
            deleted_at=None,
            deleted_by=None,
            delete_reason=None,
            created_at=created_at,
        )


def _runtime_success_result(
    *,
    summary: str = "Runtime produced a structured UI milestone review.",
    payload: dict | None = None,
    artifact_refs: list[str] | None = None,
    written_artifacts: list[dict] | None = None,
) -> RuntimeExecutionResult:
    resolved_artifact_refs = artifact_refs or [
        "art://runtime/homepage/option-a.json",
        "art://runtime/homepage/option-b.json",
    ]
    return RuntimeExecutionResult(
        result_status="completed",
        completion_summary=summary,
        artifact_refs=resolved_artifact_refs,
        result_payload=payload
        or {
            "summary": "Runtime produced a structured UI milestone review.",
            "recommended_option_id": "option_a",
            "options": [
                {
                    "option_id": "option_a",
                    "label": "Option A",
                    "summary": "Primary runtime-generated option.",
                    "artifact_refs": [resolved_artifact_refs[0]],
                },
                {
                    "option_id": "option_b",
                    "label": "Option B",
                    "summary": "Fallback runtime-generated option.",
                    "artifact_refs": [resolved_artifact_refs[1]],
                },
            ],
        },
        written_artifacts=written_artifacts
        or [
            {
                "path": "artifacts/ui/homepage/option-a.json",
                "artifact_ref": resolved_artifact_refs[0],
                "kind": "JSON",
                "content_json": {
                    "option_id": "option_a",
                    "headline": "Primary runtime-generated structured review artifact.",
                },
            },
            {
                "path": "artifacts/ui/homepage/option-b.json",
                "artifact_ref": resolved_artifact_refs[1],
                "kind": "JSON",
                "content_json": {
                    "option_id": "option_b",
                    "headline": "Fallback runtime-generated structured review artifact.",
                },
            },
        ],
        assumptions=["Runtime used the minimal compiled context bundle."],
        issues=[],
        confidence=0.75,
    )


def _maker_checker_verdict_result(
    *,
    review_status: str = "APPROVED_WITH_NOTES",
) -> RuntimeExecutionResult:
    if review_status == "CHANGES_REQUIRED":
        findings = [
            {
                "finding_id": "finding_hero_hierarchy",
                "severity": "high",
                "category": "VISUAL_HIERARCHY",
                "headline": "Hero hierarchy is not strong enough yet.",
                "summary": "The first screen still lacks a clear attention anchor.",
                "required_action": "Strengthen hero hierarchy before board review.",
                "blocking": True,
            }
        ]
    elif review_status == "APPROVED":
        findings = []
    else:
        findings = [
            {
                "finding_id": "finding_cta_spacing",
                "severity": "low",
                "category": "VISUAL_POLISH",
                "headline": "CTA spacing can be tightened slightly.",
                "summary": "Spacing is acceptable but should be polished downstream.",
                "required_action": "Tighten CTA spacing during implementation.",
                "blocking": False,
            }
        ]

    return RuntimeExecutionResult(
        result_status="completed",
        completion_summary=f"Checker returned {review_status}.",
        artifact_refs=[],
        result_payload={
            "summary": f"Checker returned {review_status} for the visual milestone.",
            "review_status": review_status,
            "findings": findings,
        },
        written_artifacts=[],
        assumptions=["Runtime used the minimal checker verdict template."],
        issues=[],
        confidence=0.7,
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
    indexed_artifacts = client.app.state.repository.list_ticket_artifacts("tkt_runner_ui")
    ticket_projection = client.app.state.repository.get_current_ticket_projection("tkt_runner_ui")
    node_projection = client.app.state.repository.get_current_node_projection("wf_runner", "node_runner_ui")
    indexed_by_ref = {item["artifact_ref"]: item for item in indexed_artifacts}
    stored_artifact = indexed_by_ref["art://runtime/tkt_runner_ui/option-a.json"]
    artifact_store = client.app.state.artifact_store

    assert ack.status.value == "ACCEPTED"
    assert ack.causation_hint == "scheduler:tick"
    assert latest_bundle is not None
    assert latest_manifest is not None
    assert latest_bundle["payload"]["meta"]["ticket_id"] == "tkt_runner_ui"
    assert latest_manifest["payload"]["compile_meta"]["ticket_id"] == "tkt_runner_ui"
    assert len(indexed_artifacts) == 2
    assert stored_artifact["materialization_status"] == "MATERIALIZED"
    assert stored_artifact["storage_relpath"] is not None
    assert (artifact_store.root / stored_artifact["storage_relpath"]).exists()
    assert ticket_projection["status"] == "COMPLETED"
    assert ticket_projection["lease_owner"] is None
    assert node_projection["status"] == "COMPLETED"


def test_scheduler_runner_once_external_mode_leaves_ticket_leased(client, set_ticket_time, monkeypatch):
    monkeypatch.setenv("BOARDROOM_OS_RUNTIME_EXECUTION_MODE", "EXTERNAL")
    scheduler_runner = importlib.import_module("app.scheduler_runner")
    scheduler_runner = importlib.reload(scheduler_runner)

    set_ticket_time("2026-03-28T10:00:00+08:00")
    client.post(
        "/api/v1/commands/ticket-create",
        json=_ticket_create_payload(
            workflow_id="wf_runner_external",
            ticket_id="tkt_runner_external",
            node_id="node_runner_external",
            role_profile_ref="ui_designer_primary",
        ),
    )

    set_ticket_time("2026-03-28T10:01:00+08:00")
    ack = scheduler_runner.run_scheduler_once(
        client.app.state.repository,
        idempotency_key="scheduler-runner:test-external-mode",
        max_dispatches=10,
    )

    repository = client.app.state.repository
    ticket_projection = repository.get_current_ticket_projection("tkt_runner_external")
    node_projection = repository.get_current_node_projection("wf_runner_external", "node_runner_external")
    latest_bundle = repository.get_latest_compiled_context_bundle_by_ticket("tkt_runner_external")
    latest_manifest = repository.get_latest_compile_manifest_by_ticket("tkt_runner_external")
    latest_execution_package = repository.get_latest_compiled_execution_package_by_ticket(
        "tkt_runner_external"
    )
    events = repository.list_events_for_testing()

    assert ack.status.value == "ACCEPTED"
    assert ticket_projection["status"] == "LEASED"
    assert ticket_projection["lease_owner"] == "emp_frontend_2"
    assert node_projection["status"] == "PENDING"
    assert latest_bundle is None
    assert latest_manifest is None
    assert latest_execution_package is None
    assert [event["event_type"] for event in events][-2:] == ["TICKET_CREATED", "TICKET_LEASED"]


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


def test_scheduler_runner_executes_checker_ticket_and_opens_board_review_after_maker_completion(
    client,
    set_ticket_time,
):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    client.post(
        "/api/v1/commands/ticket-create",
        json=_ticket_create_payload(
            workflow_id="wf_runner_checker_chain",
            ticket_id="tkt_runner_maker",
            node_id="node_runner_maker",
            role_profile_ref="ui_designer_primary",
        ),
    )
    client.post(
        "/api/v1/commands/ticket-lease",
        json={
            "workflow_id": "wf_runner_checker_chain",
            "ticket_id": "tkt_runner_maker",
            "node_id": "node_runner_maker",
            "leased_by": "emp_frontend_2",
            "lease_timeout_sec": 600,
            "idempotency_key": "ticket-lease:wf_runner_checker_chain:tkt_runner_maker:emp_frontend_2",
        },
    )
    client.post(
        "/api/v1/commands/ticket-start",
        json={
            "workflow_id": "wf_runner_checker_chain",
            "ticket_id": "tkt_runner_maker",
            "node_id": "node_runner_maker",
            "started_by": "emp_frontend_2",
            "idempotency_key": "ticket-start:wf_runner_checker_chain:tkt_runner_maker",
        },
    )
    maker_submit = client.post(
        "/api/v1/commands/ticket-result-submit",
        json={
            "workflow_id": "wf_runner_checker_chain",
            "ticket_id": "tkt_runner_maker",
            "node_id": "node_runner_maker",
            "submitted_by": "emp_frontend_2",
            "result_status": "completed",
            "schema_version": "ui_milestone_review_v1",
            "payload": {
                "summary": "Homepage visual milestone is ready for downstream review.",
                "recommended_option_id": "option_a",
                "options": [
                    {
                        "option_id": "option_a",
                        "label": "Option A",
                        "summary": "Primary runtime-generated option.",
                        "artifact_refs": ["art://runtime/maker/option-a.json"],
                    }
                ],
            },
            "artifact_refs": ["art://runtime/maker/option-a.json"],
            "written_artifacts": [
                {
                    "path": "artifacts/ui/homepage/option-a.json",
                    "artifact_ref": "art://runtime/maker/option-a.json",
                    "kind": "JSON",
                    "content_json": {"option_id": "option_a"},
                }
            ],
            "assumptions": ["Runtime used the minimal compiled context bundle."],
            "issues": [],
            "confidence": 0.75,
            "needs_escalation": False,
            "summary": "Structured runtime result submitted.",
            "review_request": {
                "review_type": "VISUAL_MILESTONE",
                "priority": "high",
                "title": "Review homepage visual milestone",
                "subtitle": "Two candidate hero directions are ready for board selection.",
                "blocking_scope": "NODE_ONLY",
                "trigger_reason": "Visual milestone hit a board-gated release checkpoint.",
                "why_now": "Downstream homepage implementation should not proceed before direction lock.",
                "recommended_action": "APPROVE",
                "recommended_option_id": "option_a",
                "recommendation_summary": "Option A has the clearest hierarchy and strongest first impression.",
                "options": [
                    {
                        "option_id": "option_a",
                        "label": "Option A",
                        "summary": "High-contrast review candidate.",
                        "artifact_refs": ["art://runtime/maker/option-a.json"],
                    }
                ],
                "evidence_summary": [],
                "maker_checker_summary": {
                    "maker_employee_id": "emp_frontend_2",
                    "checker_employee_id": "emp_checker_1",
                    "review_status": "APPROVED_WITH_NOTES",
                    "top_findings": [
                        {
                            "finding_id": "finding_legacy",
                            "severity": "medium",
                            "headline": "Legacy summary should be replaced by checker verdict.",
                        }
                    ],
                },
                "available_actions": ["APPROVE", "REJECT", "MODIFY_CONSTRAINTS"],
                "draft_selected_option_id": "option_a",
                "comment_template": "",
                "inbox_title": "Review homepage visual milestone",
                "inbox_summary": "Visual milestone is blocked for board review.",
                "badges": ["visual", "board_gate"],
            },
            "failure_kind": None,
            "failure_message": None,
            "failure_detail": None,
            "idempotency_key": "ticket-result-submit:wf_runner_checker_chain:tkt_runner_maker:completed",
        },
    )
    repository = client.app.state.repository
    node_before_runner = repository.get_current_node_projection(
        "wf_runner_checker_chain",
        "node_runner_maker",
    )
    assert node_before_runner is not None
    checker_ticket_id = node_before_runner["latest_ticket_id"]
    approvals_before_runner = repository.list_open_approvals()

    set_ticket_time("2026-03-28T10:01:00+08:00")
    ack = run_scheduler_once(
        client.app.state.repository,
        idempotency_key="scheduler-runner:test-checker-chain",
        max_dispatches=10,
    )

    approvals = repository.list_open_approvals()
    inbox_items = client.get("/api/v1/projections/inbox").json()["data"]["items"]

    assert maker_submit.status_code == 200
    assert maker_submit.json()["status"] == "ACCEPTED"
    assert checker_ticket_id != "tkt_runner_maker"
    assert approvals_before_runner == []
    assert ack.status.value == "ACCEPTED"
    assert len(approvals) == 1
    assert inbox_items[0]["route_target"]["view"] == "review_room"


def test_scheduler_runner_auto_runs_artifact_cleanup_once_per_interval_bucket(
    client,
    set_ticket_time,
    monkeypatch,
):
    monkeypatch.setenv("BOARDROOM_OS_ARTIFACT_CLEANUP_INTERVAL_SEC", "300")
    monkeypatch.setenv("BOARDROOM_OS_ARTIFACT_CLEANUP_OPERATOR_ID", "system:artifact-cleanup")
    artifact_ref = "art://runtime/cleanup/auto-ephemeral.txt"

    _seed_ephemeral_artifact_for_cleanup(
        client,
        artifact_ref=artifact_ref,
        created_at=datetime.fromisoformat("2026-03-28T10:00:00+08:00"),
        expires_at=datetime.fromisoformat("2026-03-28T10:01:00+08:00"),
    )

    set_ticket_time("2026-03-28T10:02:00+08:00")
    first_ack = run_scheduler_once(
        client.app.state.repository,
        idempotency_key="scheduler-runner:artifact-cleanup-first",
        max_dispatches=10,
    )
    first_record = client.app.state.repository.get_artifact_by_ref(artifact_ref)
    first_cleanup_events = [
        event
        for event in client.app.state.repository.list_events_for_testing()
        if event["event_type"] == "ARTIFACT_CLEANUP_COMPLETED"
    ]

    second_ack = run_scheduler_once(
        client.app.state.repository,
        idempotency_key="scheduler-runner:artifact-cleanup-second",
        max_dispatches=10,
    )
    second_cleanup_events = [
        event
        for event in client.app.state.repository.list_events_for_testing()
        if event["event_type"] == "ARTIFACT_CLEANUP_COMPLETED"
    ]

    assert first_ack.status.value == "ACCEPTED"
    assert second_ack.status.value == "ACCEPTED"
    assert first_record is not None
    assert first_record["lifecycle_status"] == "EXPIRED"
    assert first_record["deleted_by"] == "system:artifact-cleanup"
    assert first_record["storage_deleted_at"] is not None
    assert len(first_cleanup_events) == 1
    assert first_cleanup_events[0]["payload"]["cleaned_by"] == "system:artifact-cleanup"
    assert len(second_cleanup_events) == 1


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


def test_scheduler_runner_rebuilds_employee_projection_when_projection_row_disappears(client, set_ticket_time):
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
    rebuilt_employee = repository.get_employee_projection("emp_frontend_2")
    failed_events = [
        event for event in repository.list_events_for_testing() if event["event_type"] == "TICKET_FAILED"
    ]

    assert ticket_projection["status"] == "COMPLETED"
    assert rebuilt_employee is not None
    assert rebuilt_employee["state"] == "ACTIVE"
    assert failed_events == []


def test_scheduler_runner_fails_closed_when_mandatory_source_descriptor_exceeds_budget(
    client,
    set_ticket_time,
):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    create_payload = _ticket_create_payload(
        workflow_id="wf_runner_tiny_budget",
        ticket_id="tkt_runner_tiny_budget",
        node_id="node_runner_tiny_budget",
        role_profile_ref="ui_designer_primary",
        input_artifact_refs=["art://inputs/too-tight.md"],
    )
    create_payload["context_query_plan"]["max_context_tokens"] = 1
    client.post("/api/v1/commands/ticket-create", json=create_payload)

    repository = client.app.state.repository
    artifact_store = client.app.state.artifact_store
    materialized = artifact_store.materialize_text(
        "artifacts/inputs/too-tight.md",
        "# Tiny Budget\n\nThis mandatory source cannot fit even as a descriptor.\n",
    )
    with repository.transaction() as connection:
        repository.save_artifact_record(
            connection,
            artifact_ref="art://inputs/too-tight.md",
            workflow_id="wf_runner_tiny_budget",
            ticket_id="tkt_runner_tiny_budget",
            node_id="node_runner_tiny_budget",
            logical_path="artifacts/inputs/too-tight.md",
            kind="MARKDOWN",
            media_type="text/markdown",
            materialization_status="MATERIALIZED",
            lifecycle_status="ACTIVE",
            storage_relpath=materialized.storage_relpath,
            content_hash=materialized.content_hash,
            size_bytes=materialized.size_bytes,
            retention_class="PERSISTENT",
            expires_at=None,
            deleted_at=None,
            deleted_by=None,
            delete_reason=None,
            created_at=datetime.fromisoformat("2026-03-28T10:00:00+08:00"),
        )

    run_scheduler_once(
        repository,
        idempotency_key="scheduler-runner:test-tiny-budget",
        max_dispatches=10,
    )

    ticket_projection = repository.get_current_ticket_projection("tkt_runner_tiny_budget")
    failed_events = [
        event for event in repository.list_events_for_testing() if event["event_type"] == "TICKET_FAILED"
    ]

    assert ticket_projection["status"] == "FAILED"
    assert failed_events[-1]["payload"]["failure_kind"] == "RUNTIME_INPUT_ERROR"
    assert "art://inputs/too-tight.md" in failed_events[-1]["payload"]["failure_message"]
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


def test_runtime_uses_openai_compat_provider_when_configured(client, set_ticket_time, monkeypatch):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    monkeypatch.setenv("BOARDROOM_OS_PROVIDER_OPENAI_COMPAT_BASE_URL", "https://api-vip.codex-for.me/v1")
    monkeypatch.setenv("BOARDROOM_OS_PROVIDER_OPENAI_COMPAT_API_KEY", "provider-key")
    monkeypatch.setenv("BOARDROOM_OS_PROVIDER_OPENAI_COMPAT_MODEL", "gpt-5.3-codex")
    repository = client.app.state.repository
    _seed_worker(repository, employee_id="emp_frontend_live", provider_id="prov_openai_compat")

    client.post(
        "/api/v1/commands/ticket-create",
        json=_ticket_create_payload(
            workflow_id="wf_runner_provider_live",
            ticket_id="tkt_runner_provider_live",
            node_id="node_runner_provider_live",
            role_profile_ref="ui_designer_primary",
        ),
    )
    client.post(
        "/api/v1/commands/ticket-lease",
        json={
            "workflow_id": "wf_runner_provider_live",
            "ticket_id": "tkt_runner_provider_live",
            "node_id": "node_runner_provider_live",
            "leased_by": "emp_frontend_live",
            "lease_timeout_sec": 600,
            "idempotency_key": "ticket-lease:wf_runner_provider_live:tkt_runner_provider_live",
        },
    )

    called_ticket_ids: list[str] = []

    def _fake_provider_execute(execution_package):
        called_ticket_ids.append(execution_package.meta.ticket_id)
        return RuntimeExecutionResult(
            result_status="completed",
            completion_summary="Provider completed the runtime ticket.",
            artifact_refs=["art://runtime/provider/option-a.json"],
            result_payload={
                "summary": "Provider completed the runtime ticket.",
                "recommended_option_id": "option_a",
                "options": [
                    {
                        "option_id": "option_a",
                        "label": "Option A",
                        "summary": "Provider-backed option.",
                        "artifact_refs": ["art://runtime/provider/option-a.json"],
                    }
                ],
            },
            confidence=0.81,
        )

    monkeypatch.setattr(
        runtime_module,
        "_execute_openai_compat_provider",
        _fake_provider_execute,
        raising=False,
    )

    outcomes = run_leased_ticket_runtime(repository)
    ticket_projection = repository.get_current_ticket_projection("tkt_runner_provider_live")

    assert [outcome.ticket_id for outcome in outcomes] == ["tkt_runner_provider_live"]
    assert called_ticket_ids == ["tkt_runner_provider_live"]
    assert ticket_projection["status"] == "COMPLETED"


def test_runtime_provider_auth_failure_does_not_open_provider_incident(client, set_ticket_time, monkeypatch):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    monkeypatch.setenv("BOARDROOM_OS_PROVIDER_OPENAI_COMPAT_BASE_URL", "https://api-vip.codex-for.me/v1")
    monkeypatch.setenv("BOARDROOM_OS_PROVIDER_OPENAI_COMPAT_API_KEY", "provider-key")
    monkeypatch.setenv("BOARDROOM_OS_PROVIDER_OPENAI_COMPAT_MODEL", "gpt-5.3-codex")
    repository = client.app.state.repository
    _seed_worker(repository, employee_id="emp_frontend_auth", provider_id="prov_openai_compat")

    client.post(
        "/api/v1/commands/ticket-create",
        json=_ticket_create_payload(
            workflow_id="wf_runner_provider_auth",
            ticket_id="tkt_runner_provider_auth",
            node_id="node_runner_provider_auth",
            role_profile_ref="ui_designer_primary",
        ),
    )
    client.post(
        "/api/v1/commands/ticket-lease",
        json={
            "workflow_id": "wf_runner_provider_auth",
            "ticket_id": "tkt_runner_provider_auth",
            "node_id": "node_runner_provider_auth",
            "leased_by": "emp_frontend_auth",
            "lease_timeout_sec": 600,
            "idempotency_key": "ticket-lease:wf_runner_provider_auth:tkt_runner_provider_auth",
        },
    )

    def _fake_provider_execute(execution_package):
        return RuntimeExecutionResult(
            result_status="failed",
            failure_kind="PROVIDER_AUTH_FAILED",
            failure_message="Provider rejected the configured API key.",
            failure_detail={
                "provider_id": "prov_openai_compat",
                "provider_status_code": 401,
            },
        )

    monkeypatch.setattr(
        runtime_module,
        "_execute_openai_compat_provider",
        _fake_provider_execute,
        raising=False,
    )

    outcomes = run_leased_ticket_runtime(repository)
    ticket_projection = repository.get_current_ticket_projection("tkt_runner_provider_auth")

    assert [outcome.ticket_id for outcome in outcomes] == ["tkt_runner_provider_auth"]
    assert ticket_projection["status"] == "FAILED"
    assert repository.list_open_incidents() == []


def test_runtime_provider_bad_response_does_not_open_provider_incident(client, set_ticket_time, monkeypatch):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    monkeypatch.setenv("BOARDROOM_OS_PROVIDER_OPENAI_COMPAT_BASE_URL", "https://api-vip.codex-for.me/v1")
    monkeypatch.setenv("BOARDROOM_OS_PROVIDER_OPENAI_COMPAT_API_KEY", "provider-key")
    monkeypatch.setenv("BOARDROOM_OS_PROVIDER_OPENAI_COMPAT_MODEL", "gpt-5.3-codex")
    repository = client.app.state.repository
    _seed_worker(repository, employee_id="emp_frontend_bad_response", provider_id="prov_openai_compat")

    client.post(
        "/api/v1/commands/ticket-create",
        json=_ticket_create_payload(
            workflow_id="wf_runner_provider_bad_response",
            ticket_id="tkt_runner_provider_bad_response",
            node_id="node_runner_provider_bad_response",
            role_profile_ref="ui_designer_primary",
        ),
    )
    client.post(
        "/api/v1/commands/ticket-lease",
        json={
            "workflow_id": "wf_runner_provider_bad_response",
            "ticket_id": "tkt_runner_provider_bad_response",
            "node_id": "node_runner_provider_bad_response",
            "leased_by": "emp_frontend_bad_response",
            "lease_timeout_sec": 600,
            "idempotency_key": "ticket-lease:wf_runner_provider_bad_response:tkt_runner_provider_bad_response",
        },
    )

    monkeypatch.setattr(
        runtime_module,
        "invoke_openai_compat_response",
        lambda config, rendered_payload: OpenAICompatProviderResult(
            output_text='{"summary":"Broken provider payload.","recommended_option_id":"option_a","options":[]}',
            response_id="resp_bad_schema",
        ),
    )

    outcomes = run_leased_ticket_runtime(repository)
    ticket_projection = repository.get_current_ticket_projection("tkt_runner_provider_bad_response")

    assert [outcome.ticket_id for outcome in outcomes] == ["tkt_runner_provider_bad_response"]
    assert ticket_projection["status"] == "FAILED"
    assert repository.list_open_incidents() == []


def test_runtime_provider_rate_limited_response_opens_provider_incident(client, set_ticket_time, monkeypatch):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    monkeypatch.setenv("BOARDROOM_OS_PROVIDER_OPENAI_COMPAT_BASE_URL", "https://api-vip.codex-for.me/v1")
    monkeypatch.setenv("BOARDROOM_OS_PROVIDER_OPENAI_COMPAT_API_KEY", "provider-key")
    monkeypatch.setenv("BOARDROOM_OS_PROVIDER_OPENAI_COMPAT_MODEL", "gpt-5.3-codex")
    repository = client.app.state.repository
    _seed_worker(repository, employee_id="emp_frontend_rate_limited", provider_id="prov_openai_compat")

    client.post(
        "/api/v1/commands/ticket-create",
        json=_ticket_create_payload(
            workflow_id="wf_runner_provider_live_rate_limit",
            ticket_id="tkt_runner_provider_live_rate_limit",
            node_id="node_runner_provider_live_rate_limit",
            role_profile_ref="ui_designer_primary",
        ),
    )
    client.post(
        "/api/v1/commands/ticket-lease",
        json={
            "workflow_id": "wf_runner_provider_live_rate_limit",
            "ticket_id": "tkt_runner_provider_live_rate_limit",
            "node_id": "node_runner_provider_live_rate_limit",
            "leased_by": "emp_frontend_rate_limited",
            "lease_timeout_sec": 600,
            "idempotency_key": "ticket-lease:wf_runner_provider_live_rate_limit:tkt_runner_provider_live_rate_limit",
        },
    )

    def _raise_rate_limited(config, rendered_payload):
        raise OpenAICompatProviderRateLimitedError(
            failure_kind="PROVIDER_RATE_LIMITED",
            message="Provider quota exhausted.",
            failure_detail={
                "provider_status_code": 429,
                "provider_id": "prov_openai_compat",
            },
        )

    monkeypatch.setattr(runtime_module, "invoke_openai_compat_response", _raise_rate_limited)

    outcomes = run_leased_ticket_runtime(repository)
    ticket_projection = repository.get_current_ticket_projection("tkt_runner_provider_live_rate_limit")
    open_incidents = repository.list_open_incidents()

    assert [outcome.ticket_id for outcome in outcomes] == ["tkt_runner_provider_live_rate_limit"]
    assert ticket_projection["status"] == "FAILED"
    assert len(open_incidents) == 1
    assert open_incidents[0]["provider_id"] == "prov_openai_compat"


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


def test_scheduler_skips_excluded_employee_ids_and_leases_backup_worker(client):
    workflow_id = _project_init(client, "Excluded worker routing")
    _approve_hire_worker(client, workflow_id=workflow_id, employee_id="emp_frontend_backup")

    create_response = client.post(
        "/api/v1/commands/ticket-create",
        json=_ticket_create_payload(
            workflow_id=workflow_id,
            ticket_id="tkt_runner_excluded",
            node_id="node_runner_excluded",
            role_profile_ref="ui_designer_primary",
            excluded_employee_ids=["emp_frontend_2"],
        ),
    )
    assert create_response.status_code == 200
    assert create_response.json()["status"] == "ACCEPTED"

    repository = client.app.state.repository
    run_scheduler_once(
        repository,
        idempotency_key="scheduler-runner:test-excluded-worker",
        max_dispatches=10,
    )

    ticket_projection = repository.get_current_ticket_projection("tkt_runner_excluded")
    leased_events = [
        event
        for event in repository.list_events_for_testing()
        if event["event_type"] == "TICKET_LEASED"
        and event["payload"].get("ticket_id") == "tkt_runner_excluded"
    ]

    assert ticket_projection is not None
    assert ticket_projection["status"] == "COMPLETED"
    assert leased_events[-1]["payload"]["leased_by"] == "emp_frontend_backup"


def test_scheduler_skips_frozen_employee_when_dispatching(client):
    workflow_id = _project_init(client, "Frozen worker routing")
    _approve_hire_worker(client, workflow_id=workflow_id, employee_id="emp_frontend_backup")

    freeze_response = client.post(
        "/api/v1/commands/employee-freeze",
        json={
            "workflow_id": workflow_id,
            "employee_id": "emp_frontend_2",
            "frozen_by": "ops@example.com",
            "reason": "Pause new dispatch while reviewing performance.",
            "idempotency_key": f"employee-freeze:{workflow_id}:emp_frontend_2",
        },
    )
    assert freeze_response.status_code == 200
    assert freeze_response.json()["status"] == "ACCEPTED"

    create_response = client.post(
        "/api/v1/commands/ticket-create",
        json=_ticket_create_payload(
            workflow_id=workflow_id,
            ticket_id="tkt_runner_frozen",
            node_id="node_runner_frozen",
            role_profile_ref="ui_designer_primary",
        ),
    )
    assert create_response.status_code == 200
    assert create_response.json()["status"] == "ACCEPTED"

    repository = client.app.state.repository
    run_scheduler_once(
        repository,
        idempotency_key="scheduler-runner:test-frozen-worker",
        max_dispatches=10,
    )

    ticket_projection = repository.get_current_ticket_projection("tkt_runner_frozen")
    leased_events = [
        event
        for event in repository.list_events_for_testing()
        if event["event_type"] == "TICKET_LEASED"
        and event["payload"].get("ticket_id") == "tkt_runner_frozen"
    ]

    assert ticket_projection is not None
    assert ticket_projection["status"] == "COMPLETED"
    assert leased_events[-1]["payload"]["leased_by"] == "emp_frontend_backup"


def test_scheduler_reassigns_requeued_ticket_after_freeze(client, set_ticket_time):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    workflow_id = _project_init(client, "Freeze leased reassignment")
    _approve_hire_worker(client, workflow_id=workflow_id, employee_id="emp_frontend_backup")

    client.post(
        "/api/v1/commands/ticket-create",
        json=_ticket_create_payload(
            workflow_id=workflow_id,
            ticket_id="tkt_runner_requeued_after_freeze",
            node_id="node_runner_requeued_after_freeze",
            role_profile_ref="ui_designer_primary",
        ),
    )
    client.post(
        "/api/v1/commands/ticket-lease",
        json={
            "workflow_id": workflow_id,
            "ticket_id": "tkt_runner_requeued_after_freeze",
            "node_id": "node_runner_requeued_after_freeze",
            "leased_by": "emp_frontend_2",
            "lease_timeout_sec": 600,
            "idempotency_key": "ticket-lease:freeze-requeued:emp_frontend_2",
        },
    )

    freeze_response = client.post(
        "/api/v1/commands/employee-freeze",
        json={
            "workflow_id": workflow_id,
            "employee_id": "emp_frontend_2",
            "frozen_by": "ops@example.com",
            "reason": "Reassign current leased ticket after freeze.",
            "idempotency_key": f"employee-freeze:{workflow_id}:emp_frontend_2:requeued",
        },
    )
    assert freeze_response.status_code == 200
    assert freeze_response.json()["status"] == "ACCEPTED"

    repository = client.app.state.repository
    run_scheduler_once(
        repository,
        idempotency_key="scheduler-runner:test-requeued-after-freeze",
        max_dispatches=10,
    )

    ticket_projection = repository.get_current_ticket_projection("tkt_runner_requeued_after_freeze")
    leased_events = [
        event
        for event in repository.list_events_for_testing()
        if event["event_type"] == "TICKET_LEASED"
        and event["payload"].get("ticket_id") == "tkt_runner_requeued_after_freeze"
    ]

    assert ticket_projection is not None
    assert ticket_projection["status"] == "COMPLETED"
    assert leased_events[-1]["payload"]["leased_by"] == "emp_frontend_backup"


def test_scheduler_dispatches_restored_employee_again(client):
    workflow_id = _project_init(client, "Restored worker routing")
    _approve_hire_worker(client, workflow_id=workflow_id, employee_id="emp_frontend_backup")

    freeze_response = client.post(
        "/api/v1/commands/employee-freeze",
        json={
            "workflow_id": workflow_id,
            "employee_id": "emp_frontend_2",
            "frozen_by": "ops@example.com",
            "reason": "Pause dispatch before restore test.",
            "idempotency_key": f"employee-freeze:{workflow_id}:emp_frontend_2:restore-cycle",
        },
    )
    assert freeze_response.status_code == 200
    assert freeze_response.json()["status"] == "ACCEPTED"

    client.post(
        "/api/v1/commands/ticket-create",
        json=_ticket_create_payload(
            workflow_id=workflow_id,
            ticket_id="tkt_runner_restore_before",
            node_id="node_runner_restore_before",
            role_profile_ref="ui_designer_primary",
        ),
    )
    repository = client.app.state.repository
    run_scheduler_once(
        repository,
        idempotency_key="scheduler-runner:test-restore-before",
        max_dispatches=10,
    )
    before_restore_lease = [
        event
        for event in repository.list_events_for_testing()
        if event["event_type"] == "TICKET_LEASED"
        and event["payload"].get("ticket_id") == "tkt_runner_restore_before"
    ][-1]

    restore_response = client.post(
        "/api/v1/commands/employee-restore",
        json={
            "workflow_id": workflow_id,
            "employee_id": "emp_frontend_2",
            "restored_by": "ops@example.com",
            "reason": "Return worker after review.",
            "idempotency_key": f"employee-restore:{workflow_id}:emp_frontend_2",
        },
    )
    assert restore_response.status_code == 200
    assert restore_response.json()["status"] == "ACCEPTED"

    client.post(
        "/api/v1/commands/ticket-create",
        json=_ticket_create_payload(
            workflow_id=workflow_id,
            ticket_id="tkt_runner_restore_after",
            node_id="node_runner_restore_after",
            role_profile_ref="ui_designer_primary",
        ),
    )
    run_scheduler_once(
        repository,
        idempotency_key="scheduler-runner:test-restore-after",
        max_dispatches=10,
    )
    after_restore_lease = [
        event
        for event in repository.list_events_for_testing()
        if event["event_type"] == "TICKET_LEASED"
        and event["payload"].get("ticket_id") == "tkt_runner_restore_after"
    ][-1]

    assert before_restore_lease["payload"]["leased_by"] == "emp_frontend_backup"
    assert after_restore_lease["payload"]["leased_by"] == "emp_frontend_2"
