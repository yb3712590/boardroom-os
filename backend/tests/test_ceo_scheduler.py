from __future__ import annotations

import json
from datetime import datetime

from app.contracts.ceo_actions import CEOActionBatch
from app.core.ceo_snapshot import build_ceo_shadow_snapshot
from app.core.ceo_execution_presets import (
    PROJECT_INIT_SCOPE_NODE_ID,
    build_project_init_scope_ticket_id,
)
from app.core.ceo_prompts import build_ceo_shadow_system_prompt
from app.core.ceo_validator import validate_ceo_action_batch
from app.core.ceo_scheduler import (
    SCHEDULER_IDLE_MAINTENANCE_TRIGGER,
    list_due_ceo_maintenance_workflows,
    run_ceo_shadow_for_trigger,
    run_due_ceo_maintenance,
)
from app.core.constants import (
    EVENT_BOARD_REVIEW_REJECTED,
    EVENT_BOARD_DIRECTIVE_RECEIVED,
    EVENT_CIRCUIT_BREAKER_OPENED,
    EVENT_EMPLOYEE_HIRED,
    EVENT_INCIDENT_OPENED,
    EVENT_WORKFLOW_CREATED,
)
from app.core.persona_profiles import clone_persona_template, get_hire_persona_template_id
from app.core.provider_openai_compat import OpenAICompatProviderResult
from app.core.runtime_provider_config import RuntimeProviderMode, RuntimeProviderStoredConfig


def _project_init(client, goal: str = "CEO shadow test") -> str:
    response = client.post(
        "/api/v1/commands/project-init",
        json={
            "north_star_goal": goal,
            "hard_constraints": [
                "Keep governance explicit.",
                "Do not move workflow truth into the browser.",
            ],
            "budget_cap": 500000,
            "deadline_at": None,
        },
    )
    assert response.status_code == 200
    assert response.json()["status"] == "ACCEPTED"
    return response.json()["causation_hint"].split(":", 1)[1]


def _seed_workflow(client, workflow_id: str, goal: str = "Seeded CEO workflow") -> str:
    repository = client.app.state.repository
    with repository.transaction() as connection:
        repository.insert_event(
            connection,
            event_type=EVENT_WORKFLOW_CREATED,
            actor_type="system",
            actor_id="test-seed",
            workflow_id=workflow_id,
            idempotency_key=f"workflow-created:{workflow_id}",
            causation_id=None,
            correlation_id=workflow_id,
            payload={
                "north_star_goal": goal,
                "hard_constraints": ["Keep governance explicit."],
                "budget_cap": 500000,
                "deadline_at": None,
                "title": goal,
                "tenant_id": "tenant_default",
                "workspace_id": "ws_default",
            },
            occurred_at=datetime.fromisoformat("2026-04-05T10:00:00+08:00"),
        )
        repository.refresh_projections(connection)
    return workflow_id


def _set_deterministic_mode(client) -> None:
    client.app.state.runtime_provider_store.save_config(
        RuntimeProviderStoredConfig(
            mode=RuntimeProviderMode.DETERMINISTIC,
            base_url=None,
            api_key=None,
            model=None,
            timeout_sec=30.0,
            reasoning_effort=None,
        )
    )


def _set_live_provider(client) -> None:
    client.app.state.runtime_provider_store.save_config(
        RuntimeProviderStoredConfig(
            mode=RuntimeProviderMode.OPENAI_COMPAT,
            base_url="https://api.example.test/v1",
            api_key="sk-test-secret",
            model="gpt-5.3-codex",
            timeout_sec=30.0,
            reasoning_effort="medium",
        )
    )


def _approve_scope_review(client, workflow_id: str) -> None:
    approval = next(
        item for item in client.app.state.repository.list_open_approvals() if item["workflow_id"] == workflow_id
    )
    option_id = approval["payload"]["review_pack"]["options"][0]["option_id"]
    response = client.post(
        "/api/v1/commands/board-approve",
        json={
            "review_pack_id": approval["review_pack_id"],
            "review_pack_version": approval["review_pack_version"],
            "command_target_version": approval["command_target_version"],
            "approval_id": approval["approval_id"],
            "selected_option_id": option_id,
            "board_comment": "Approve scope and continue.",
            "idempotency_key": f"board-approve:{approval['approval_id']}:ceo-shadow",
        },
    )
    assert response.status_code == 200
    assert response.json()["status"] == "ACCEPTED"


def _ticket_create_payload(
    *,
    workflow_id: str,
    ticket_id: str,
    node_id: str,
    retry_budget: int = 0,
) -> dict:
    return {
        "ticket_id": ticket_id,
        "workflow_id": workflow_id,
        "node_id": node_id,
        "parent_ticket_id": None,
        "attempt_no": 1,
        "role_profile_ref": "frontend_engineer_primary",
        "constraints_ref": "global_constraints_v3",
        "input_artifact_refs": ["art://inputs/brief.md"],
        "context_query_plan": {
            "keywords": ["shadow", "test"],
            "semantic_queries": ["ceo shadow test"],
            "max_context_tokens": 3000,
        },
        "acceptance_criteria": ["Must produce a structured result."],
        "output_schema_ref": "ui_milestone_review",
        "output_schema_version": 1,
        "allowed_tools": ["read_artifact", "write_artifact"],
        "allowed_write_set": ["artifacts/ui/homepage/*"],
        "retry_budget": retry_budget,
        "priority": "high",
        "timeout_sla_sec": 1800,
        "deadline_at": None,
        "excluded_employee_ids": [],
        "escalation_policy": {
            "on_timeout": "retry",
            "on_schema_error": "retry",
            "on_repeat_failure": "escalate_ceo",
        },
        "idempotency_key": f"ticket-create:{workflow_id}:{ticket_id}",
    }


def _create_and_fail_ticket(
    client,
    *,
    workflow_id: str,
    ticket_id: str,
    node_id: str,
    retry_budget: int,
) -> None:
    create_response = client.post(
        "/api/v1/commands/ticket-create",
        json=_ticket_create_payload(
            workflow_id=workflow_id,
            ticket_id=ticket_id,
            node_id=node_id,
            retry_budget=retry_budget,
        ),
    )
    assert create_response.status_code == 200
    assert create_response.json()["status"] == "ACCEPTED"

    lease_response = client.post(
        "/api/v1/commands/ticket-lease",
        json={
            "workflow_id": workflow_id,
            "ticket_id": ticket_id,
            "node_id": node_id,
            "leased_by": "emp_frontend_2",
            "lease_timeout_sec": 600,
            "idempotency_key": f"ticket-lease:{workflow_id}:{ticket_id}",
        },
    )
    assert lease_response.status_code == 200

    start_response = client.post(
        "/api/v1/commands/ticket-start",
        json={
            "workflow_id": workflow_id,
            "ticket_id": ticket_id,
            "node_id": node_id,
            "started_by": "emp_frontend_2",
            "idempotency_key": f"ticket-start:{workflow_id}:{ticket_id}",
        },
    )
    assert start_response.status_code == 200

    fail_response = client.post(
        "/api/v1/commands/ticket-fail",
        json={
            "workflow_id": workflow_id,
            "ticket_id": ticket_id,
            "node_id": node_id,
            "failed_by": "emp_frontend_2",
            "failure_kind": "TEST_FAILURE",
            "failure_message": "Synthetic failure for CEO limited execution coverage.",
            "failure_detail": {},
            "idempotency_key": f"ticket-fail:{workflow_id}:{ticket_id}",
        },
    )
    assert fail_response.status_code == 200
    assert fail_response.json()["status"] == "ACCEPTED"


def _create_and_complete_ticket(
    client,
    *,
    workflow_id: str,
    ticket_id: str,
    node_id: str,
    summary: str = "Completed implementation slice ready for reuse.",
) -> None:
    create_response = client.post(
        "/api/v1/commands/ticket-create",
        json={
            **_ticket_create_payload(
                workflow_id=workflow_id,
                ticket_id=ticket_id,
                node_id=node_id,
                retry_budget=0,
            ),
            "output_schema_ref": "implementation_bundle",
        },
    )
    assert create_response.status_code == 200
    assert create_response.json()["status"] == "ACCEPTED"

    lease_response = client.post(
        "/api/v1/commands/ticket-lease",
        json={
            "workflow_id": workflow_id,
            "ticket_id": ticket_id,
            "node_id": node_id,
            "leased_by": "emp_frontend_2",
            "lease_timeout_sec": 600,
            "idempotency_key": f"ticket-lease:{workflow_id}:{ticket_id}:complete",
        },
    )
    assert lease_response.status_code == 200

    start_response = client.post(
        "/api/v1/commands/ticket-start",
        json={
            "workflow_id": workflow_id,
            "ticket_id": ticket_id,
            "node_id": node_id,
            "started_by": "emp_frontend_2",
            "idempotency_key": f"ticket-start:{workflow_id}:{ticket_id}:complete",
        },
    )
    assert start_response.status_code == 200

    artifact_ref = f"art://runtime/{ticket_id}/implementation-bundle.json"
    submit_response = client.post(
        "/api/v1/commands/ticket-result-submit",
        json={
            "workflow_id": workflow_id,
            "ticket_id": ticket_id,
            "node_id": node_id,
            "submitted_by": "emp_frontend_2",
            "result_status": "completed",
            "schema_version": "implementation_bundle_v1",
            "payload": {
                "summary": summary,
                "deliverable_artifact_refs": [artifact_ref],
                "implementation_notes": ["Keep delivery inside the already approved scope."],
            },
            "artifact_refs": [artifact_ref],
            "written_artifacts": [
                {
                    "path": "artifacts/ui/homepage/implementation-bundle.json",
                    "artifact_ref": artifact_ref,
                    "kind": "JSON",
                    "content_json": {
                        "summary": summary,
                        "deliverable_artifact_refs": [artifact_ref],
                        "implementation_notes": ["Keep delivery inside the already approved scope."],
                    },
                }
            ],
            "assumptions": ["Completed bundle is still reusable for the current workflow."],
            "issues": [],
            "confidence": 0.87,
            "needs_escalation": False,
            "summary": summary,
            "idempotency_key": f"ticket-result-submit:{workflow_id}:{ticket_id}:complete",
        },
    )
    assert submit_response.status_code == 200
    assert submit_response.json()["status"] == "ACCEPTED"


def _seed_closed_meeting(
    client,
    *,
    workflow_id: str,
    meeting_id: str,
    source_ticket_id: str,
    source_node_id: str,
    topic: str = "Reuse the existing governance decision",
    consensus_summary: str = "Meeting already resolved the technical trade-off.",
) -> None:
    repository = client.app.state.repository
    closed_at = datetime.fromisoformat("2026-04-06T11:30:00+08:00")
    with repository.transaction() as connection:
        repository.create_meeting_projection(
            connection,
            meeting_id=meeting_id,
            workflow_id=workflow_id,
            meeting_type="TECHNICAL_DECISION",
            topic=topic,
            normalized_topic="reuse existing governance decision",
            status="CLOSED",
            review_status="APPROVED",
            source_ticket_id=source_ticket_id,
            source_node_id=source_node_id,
            review_pack_id="rp_meeting_reuse_1",
            opened_at=datetime.fromisoformat("2026-04-06T10:00:00+08:00"),
            updated_at=closed_at,
            closed_at=closed_at,
            current_round="CLOSE",
            recorder_employee_id="emp_frontend_2",
            participants=[
                {
                    "employee_id": "emp_frontend_2",
                    "role_type": "frontend_engineer",
                    "meeting_responsibility": "recorder",
                    "is_recorder": True,
                },
                {
                    "employee_id": "emp_checker_1",
                    "role_type": "checker",
                    "meeting_responsibility": "reviewer",
                    "is_recorder": False,
                },
            ],
            rounds=[],
            consensus_summary=consensus_summary,
            no_consensus_reason=None,
        )


def test_ceo_shadow_run_records_fallback_without_touching_mainline_state(client):
    _set_deterministic_mode(client)
    workflow_id = _project_init(client, "CEO shadow fallback")
    repository = client.app.state.repository
    _, projection_version_before = repository.get_cursor_and_version()

    run = run_ceo_shadow_for_trigger(
        repository,
        workflow_id=workflow_id,
        trigger_type="MANUAL_TEST",
        trigger_ref="manual:fallback",
    )

    _, projection_version_after = repository.get_cursor_and_version()
    assert projection_version_after == projection_version_before
    assert run["workflow_id"] == workflow_id
    assert run["trigger_type"] == "MANUAL_TEST"
    assert run["fallback_reason"] is not None
    assert run["accepted_actions"][0]["action_type"] == "NO_ACTION"
    assert run["deterministic_fallback_used"] is True
    assert run["deterministic_fallback_reason"] is not None


def test_project_init_records_board_directive_shadow_and_stable_scope_ticket(client):
    _set_deterministic_mode(client)
    workflow_id = _project_init(client, "CEO kickoff deterministic fallback")
    repository = client.app.state.repository

    runs = repository.list_ceo_shadow_runs(workflow_id)
    scope_ticket_id = build_project_init_scope_ticket_id(workflow_id)
    scope_ticket = repository.get_current_ticket_projection(scope_ticket_id)
    with repository.connection() as connection:
        created_spec = repository.get_latest_ticket_created_payload(connection, scope_ticket_id)

    assert any(run["trigger_type"] == EVENT_BOARD_DIRECTIVE_RECEIVED for run in runs)
    assert scope_ticket is not None
    assert created_spec is not None
    assert created_spec["node_id"] == PROJECT_INIT_SCOPE_NODE_ID
    assert created_spec["role_profile_ref"] == "ui_designer_primary"
    assert created_spec["tenant_id"] == "tenant_default"
    assert created_spec["workspace_id"] == "ws_default"
    assert any(ref.endswith("/board-brief.md") for ref in created_spec["input_artifact_refs"])


def test_ceo_shadow_snapshot_includes_normalized_profiles_and_summary(client):
    _set_deterministic_mode(client)
    workflow_id = _project_init(client, "CEO snapshot persona")

    snapshot = build_ceo_shadow_snapshot(
        client.app.state.repository,
        workflow_id=workflow_id,
        trigger_type="MANUAL_TEST",
        trigger_ref="manual:persona",
    )

    frontend_employee = next(
        employee for employee in snapshot["employees"] if employee["employee_id"] == "emp_frontend_2"
    )
    assert frontend_employee["skill_profile"]["system_scope"] == "delivery_slice"
    assert frontend_employee["personality_profile"]["risk_posture"] == "assertive"
    assert frontend_employee["profile_summary"].startswith("Skill frontend")


def test_ceo_shadow_snapshot_includes_failed_ticket_meeting_candidate(client):
    _set_deterministic_mode(client)
    workflow_id = _seed_workflow(client, "wf_ceo_meeting_candidate")
    _create_and_fail_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_ceo_meeting_candidate",
        node_id="node_ceo_meeting_candidate",
        retry_budget=0,
    )

    snapshot = next(
        run["snapshot"]
        for run in client.app.state.repository.list_ceo_shadow_runs(workflow_id)
        if run["trigger_type"] == "TICKET_FAILED"
    )

    assert "meeting_candidates" in snapshot
    assert snapshot["meeting_candidates"]
    candidate = next(
        item
        for item in snapshot["meeting_candidates"]
        if item["source_ticket_id"] == "tkt_ceo_meeting_candidate"
    )
    assert candidate["eligible"] is True
    assert candidate["participant_employee_ids"] == ["emp_frontend_2", "emp_checker_1"]
    assert candidate["recorder_employee_id"] == "emp_frontend_2"
    assert "failed" in candidate["reason"].lower()


def test_ceo_shadow_snapshot_includes_reuse_candidates(client):
    _set_deterministic_mode(client)
    workflow_id = _seed_workflow(client, "wf_ceo_reuse_candidates")
    _create_and_complete_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_ceo_reuse_completed",
        node_id="node_ceo_reuse_completed",
        summary="Completed implementation slice ready for reuse.",
    )
    _seed_closed_meeting(
        client,
        workflow_id=workflow_id,
        meeting_id="mtg_ceo_reuse_closed",
        source_ticket_id="tkt_ceo_reuse_completed",
        source_node_id="node_ceo_reuse_completed",
    )

    snapshot = build_ceo_shadow_snapshot(
        client.app.state.repository,
        workflow_id=workflow_id,
        trigger_type="MANUAL_TEST",
        trigger_ref="manual:reuse-candidates",
    )

    reuse_candidates = snapshot["reuse_candidates"]
    assert reuse_candidates["recent_completed_tickets"]
    completed_ticket = reuse_candidates["recent_completed_tickets"][0]
    assert completed_ticket["ticket_id"] == "tkt_ceo_reuse_completed"
    assert completed_ticket["node_id"] == "node_ceo_reuse_completed"
    assert completed_ticket["output_schema_ref"] == "implementation_bundle"
    assert completed_ticket["summary"] == "Completed implementation slice ready for reuse."
    assert completed_ticket["artifact_refs"] == ["art://runtime/tkt_ceo_reuse_completed/implementation-bundle.json"]
    assert completed_ticket["completed_at"] is not None

    assert reuse_candidates["recent_closed_meetings"]
    closed_meeting = reuse_candidates["recent_closed_meetings"][0]
    assert closed_meeting["meeting_id"] == "mtg_ceo_reuse_closed"
    assert closed_meeting["source_ticket_id"] == "tkt_ceo_reuse_completed"
    assert closed_meeting["source_node_id"] == "node_ceo_reuse_completed"
    assert closed_meeting["topic"] == "Reuse the existing governance decision"
    assert closed_meeting["consensus_summary"] == "Meeting already resolved the technical trade-off."
    assert closed_meeting["review_status"] == "APPROVED"
    assert closed_meeting["closed_at"] is not None


def test_live_ceo_prompt_mentions_reuse_candidates_and_provider_receives_them(client, monkeypatch):
    _set_deterministic_mode(client)
    workflow_id = _seed_workflow(client, "wf_ceo_live_reuse")
    _create_and_complete_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_ceo_live_reuse_completed",
        node_id="node_ceo_live_reuse_completed",
    )
    _seed_closed_meeting(
        client,
        workflow_id=workflow_id,
        meeting_id="mtg_ceo_live_reuse_closed",
        source_ticket_id="tkt_ceo_live_reuse_completed",
        source_node_id="node_ceo_live_reuse_completed",
    )
    _set_live_provider(client)

    from app.core import ceo_proposer

    def _fake_invoke(_config, rendered_payload):
        system_prompt = rendered_payload.messages[0].content_payload["text"]
        snapshot = rendered_payload.messages[2].content_payload
        assert "reuse_candidates" in system_prompt
        assert "NO_ACTION" in system_prompt
        assert "REQUEST_MEETING" in system_prompt
        assert snapshot["reuse_candidates"]["recent_completed_tickets"]
        assert snapshot["reuse_candidates"]["recent_closed_meetings"]
        return OpenAICompatProviderResult(
            output_text=json.dumps(
                {
                    "summary": "Reuse candidates already cover this workflow state, so no new action is needed.",
                    "actions": [
                        {
                            "action_type": "NO_ACTION",
                            "payload": {
                                "reason": "Recent completed tickets and closed meetings already provide reusable guidance.",
                            },
                        }
                    ],
                }
            ),
            response_id="resp_ceo_reuse_1",
        )

    monkeypatch.setattr(ceo_proposer, "invoke_openai_compat_response", _fake_invoke)

    snapshot = build_ceo_shadow_snapshot(
        client.app.state.repository,
        workflow_id=workflow_id,
        trigger_type="MANUAL_TEST",
        trigger_ref="manual:live-reuse",
    )
    system_prompt = build_ceo_shadow_system_prompt(snapshot)
    assert "reuse_candidates" in system_prompt

    run = run_ceo_shadow_for_trigger(
        client.app.state.repository,
        workflow_id=workflow_id,
        trigger_type="MANUAL_TEST",
        trigger_ref="manual:live-reuse",
        runtime_provider_store=client.app.state.runtime_provider_store,
    )

    assert run["provider_response_id"] == "resp_ceo_reuse_1"
    assert run["accepted_actions"][0]["action_type"] == "NO_ACTION"
    assert run["executed_actions"][0]["execution_status"] == "PASSTHROUGH"
    assert run["deterministic_fallback_used"] is False


def test_ceo_validator_rejects_high_overlap_hire_when_same_role_template_is_already_active(client):
    _set_deterministic_mode(client)
    workflow_id = _project_init(client, "CEO validator overlap")
    repository = client.app.state.repository
    hire_template = clone_persona_template(get_hire_persona_template_id("frontend_engineer"))

    with repository.transaction() as connection:
        repository.insert_event(
            connection,
            event_type=EVENT_EMPLOYEE_HIRED,
            actor_type="system",
            actor_id="test-seed",
            workflow_id=None,
            idempotency_key="test-seed-employee:emp_frontend_polish",
            causation_id=None,
            correlation_id=None,
            payload={
                "employee_id": "emp_frontend_polish",
                "role_type": "frontend_engineer",
                "skill_profile": hire_template["skill_profile"],
                "personality_profile": hire_template["personality_profile"],
                "aesthetic_profile": hire_template["aesthetic_profile"],
                "state": "ACTIVE",
                "board_approved": True,
                "provider_id": "prov_openai_compat",
                "role_profile_refs": ["frontend_engineer_primary"],
            },
            occurred_at=datetime.fromisoformat("2026-04-04T18:00:00+08:00"),
        )
        repository.refresh_projections(connection)

    result = validate_ceo_action_batch(
        repository,
        action_batch=CEOActionBatch.model_validate(
            {
                "summary": "Hire a frontend backup.",
                "actions": [
                    {
                        "action_type": "HIRE_EMPLOYEE",
                        "payload": {
                            "workflow_id": workflow_id,
                            "role_type": "frontend_engineer",
                            "role_profile_refs": ["frontend_engineer_primary"],
                            "request_summary": "Hire another frontend backup.",
                            "employee_id_hint": "emp_frontend_duplicate",
                            "provider_id": "prov_openai_compat",
                        },
                    }
                ],
            }
        ),
    )

    assert result["accepted_actions"] == []
    assert result["rejected_actions"][0]["action_type"] == "HIRE_EMPLOYEE"
    assert "too similar" in result["rejected_actions"][0]["reason"].lower()


def test_project_init_can_use_live_provider_for_first_scope_ticket(client, monkeypatch):
    _set_live_provider(client)

    from app.core import ceo_proposer

    def _fake_invoke(_config, rendered_payload):
        snapshot = rendered_payload.messages[2].content_payload
        workflow_id = snapshot["workflow"]["workflow_id"]
        return OpenAICompatProviderResult(
            output_text=json.dumps(
                {
                    "summary": "Create the kickoff scope consensus ticket first.",
                    "actions": [
                        {
                            "action_type": "CREATE_TICKET",
                            "payload": {
                                "workflow_id": workflow_id,
                                "node_id": PROJECT_INIT_SCOPE_NODE_ID,
                                "role_profile_ref": "ui_designer_primary",
                                "output_schema_ref": "consensus_document",
                                "summary": "Prepare the kickoff consensus report and the first batch of follow-up ticket outlines.",
                                "parent_ticket_id": None,
                            },
                        }
                    ],
                }
            ),
            response_id="resp_ceo_project_init_1",
        )

    monkeypatch.setattr(ceo_proposer, "invoke_openai_compat_response", _fake_invoke)

    workflow_id = _project_init(client, "CEO kickoff live provider")
    repository = client.app.state.repository
    scope_ticket_id = build_project_init_scope_ticket_id(workflow_id)
    board_directive_run = next(
        run for run in repository.list_ceo_shadow_runs(workflow_id) if run["trigger_type"] == EVENT_BOARD_DIRECTIVE_RECEIVED
    )
    with repository.connection() as connection:
        created_spec = repository.get_latest_ticket_created_payload(connection, scope_ticket_id)

    assert created_spec is not None
    assert created_spec["ticket_id"] == scope_ticket_id
    assert created_spec["node_id"] == PROJECT_INIT_SCOPE_NODE_ID
    assert board_directive_run["provider_response_id"] == "resp_ceo_project_init_1"


def test_ceo_shadow_run_uses_live_provider_and_executes_hire_request(client, monkeypatch):
    workflow_id = _project_init(client, "CEO shadow live provider")
    _set_live_provider(client)

    from app.core import ceo_proposer

    def _fake_invoke(_config, _rendered_payload):
        return OpenAICompatProviderResult(
            output_text=json.dumps(
                {
                    "summary": "Hire a backup checker and reject an invalid retry.",
                    "actions": [
                        {
                            "action_type": "HIRE_EMPLOYEE",
                            "payload": {
                                "workflow_id": workflow_id,
                                "role_type": "checker",
                                "role_profile_refs": ["checker_primary"],
                                "request_summary": "Hire a backup checker for internal review continuity.",
                                "employee_id_hint": "emp_checker_shadow",
                                "provider_id": "prov_openai_compat",
                            },
                        },
                        {
                            "action_type": "RETRY_TICKET",
                            "payload": {
                                "workflow_id": workflow_id,
                                "ticket_id": "tkt_missing_shadow",
                                "node_id": "node_missing_shadow",
                                "reason": "Retry a missing ticket.",
                            },
                        },
                    ],
                }
            ),
            response_id="resp_ceo_shadow_1",
        )

    monkeypatch.setattr(ceo_proposer, "invoke_openai_compat_response", _fake_invoke)

    run = run_ceo_shadow_for_trigger(
        client.app.state.repository,
        workflow_id=workflow_id,
        trigger_type="MANUAL_TEST",
        trigger_ref="manual:live-provider",
        runtime_provider_store=client.app.state.runtime_provider_store,
    )

    assert run["provider_response_id"] == "resp_ceo_shadow_1"
    assert run["fallback_reason"] is None
    assert run["accepted_actions"][0]["action_type"] == "HIRE_EMPLOYEE"
    assert run["rejected_actions"][0]["action_type"] == "RETRY_TICKET"
    assert run["executed_actions"][0]["action_type"] == "HIRE_EMPLOYEE"
    assert run["executed_actions"][0]["execution_status"] == "EXECUTED"
    assert run["execution_summary"]["executed_action_count"] == 1
    assert run["deterministic_fallback_used"] is False
    assert any(
        approval["approval_type"] == "CORE_HIRE_APPROVAL"
        for approval in client.app.state.repository.list_open_approvals()
        if approval["workflow_id"] == workflow_id
    )


def test_ceo_shadow_run_executes_retry_ticket(client, monkeypatch):
    _set_deterministic_mode(client)
    workflow_id = _project_init(client, "CEO limited retry execution")
    _create_and_fail_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_ceo_retry_source",
        node_id="node_ceo_retry_source",
        retry_budget=1,
    )
    _set_live_provider(client)

    from app.core import ceo_proposer

    def _fake_invoke(_config, _rendered_payload):
        return OpenAICompatProviderResult(
            output_text=json.dumps(
                {
                    "summary": "Retry the failed ticket once.",
                    "actions": [
                        {
                            "action_type": "RETRY_TICKET",
                            "payload": {
                                "workflow_id": workflow_id,
                                "ticket_id": "tkt_ceo_retry_source",
                                "node_id": "node_ceo_retry_source",
                                "reason": "The ticket failed once and still has retry budget.",
                            },
                        }
                    ],
                }
            ),
            response_id="resp_ceo_retry_1",
        )

    monkeypatch.setattr(ceo_proposer, "invoke_openai_compat_response", _fake_invoke)

    run = run_ceo_shadow_for_trigger(
        client.app.state.repository,
        workflow_id=workflow_id,
        trigger_type="MANUAL_TEST",
        trigger_ref="manual:retry",
        runtime_provider_store=client.app.state.runtime_provider_store,
    )

    assert run["executed_actions"][0]["action_type"] == "RETRY_TICKET"
    assert run["executed_actions"][0]["execution_status"] == "EXECUTED"
    retry_ticket_id = run["executed_actions"][0]["causation_hint"].split(":", 1)[1]
    retry_ticket = client.app.state.repository.get_current_ticket_projection(retry_ticket_id)
    assert retry_ticket is not None
    with client.app.state.repository.connection() as connection:
        created_spec = client.app.state.repository.get_latest_ticket_created_payload(connection, retry_ticket_id)
    assert created_spec["parent_ticket_id"] == "tkt_ceo_retry_source"
    assert created_spec["attempt_no"] == 2
    assert created_spec["retry_count"] == 1
    assert run["deterministic_fallback_used"] is False


def test_ceo_shadow_run_executes_whitelisted_create_ticket(client, monkeypatch):
    workflow_id = _project_init(client, "CEO limited create execution")
    _set_live_provider(client)

    from app.core import ceo_proposer

    def _fake_invoke(_config, _rendered_payload):
        return OpenAICompatProviderResult(
            output_text=json.dumps(
                {
                    "summary": "Create a mainline implementation ticket.",
                    "actions": [
                        {
                            "action_type": "CREATE_TICKET",
                            "payload": {
                                "workflow_id": workflow_id,
                                "node_id": "node_ceo_create_bundle",
                                "role_profile_ref": "frontend_engineer_primary",
                                "output_schema_ref": "implementation_bundle",
                                "summary": "Create the implementation bundle for the approved scope slice.",
                                "parent_ticket_id": None,
                            },
                        }
                    ],
                }
            ),
            response_id="resp_ceo_create_1",
        )

    monkeypatch.setattr(ceo_proposer, "invoke_openai_compat_response", _fake_invoke)

    run = run_ceo_shadow_for_trigger(
        client.app.state.repository,
        workflow_id=workflow_id,
        trigger_type="MANUAL_TEST",
        trigger_ref="manual:create",
        runtime_provider_store=client.app.state.runtime_provider_store,
    )

    assert run["executed_actions"][0]["action_type"] == "CREATE_TICKET"
    assert run["executed_actions"][0]["execution_status"] == "EXECUTED"
    created_ticket_id = run["executed_actions"][0]["payload"]["ticket_id"]
    with client.app.state.repository.connection() as connection:
        created_spec = client.app.state.repository.get_latest_ticket_created_payload(connection, created_ticket_id)
    assert created_spec["output_schema_ref"] == "implementation_bundle"
    assert created_spec["role_profile_ref"] == "frontend_engineer_primary"
    assert created_spec["delivery_stage"] == "BUILD"


def test_ceo_shadow_run_rejects_invalid_create_ticket_preset(client, monkeypatch):
    workflow_id = _project_init(client, "CEO invalid create preset")
    _set_live_provider(client)

    from app.core import ceo_proposer

    def _fake_invoke(_config, _rendered_payload):
        return OpenAICompatProviderResult(
            output_text=json.dumps(
                {
                    "summary": "Try an invalid create-ticket combo.",
                    "actions": [
                        {
                            "action_type": "CREATE_TICKET",
                            "payload": {
                                "workflow_id": workflow_id,
                                "node_id": "node_ceo_invalid_create",
                                "role_profile_ref": "frontend_engineer_primary",
                                "output_schema_ref": "delivery_check_report",
                                "summary": "This combo should be rejected.",
                                "parent_ticket_id": None,
                            },
                        }
                    ],
                }
            ),
            response_id="resp_ceo_create_invalid_1",
        )

    monkeypatch.setattr(ceo_proposer, "invoke_openai_compat_response", _fake_invoke)

    run = run_ceo_shadow_for_trigger(
        client.app.state.repository,
        workflow_id=workflow_id,
        trigger_type="MANUAL_TEST",
        trigger_ref="manual:create-invalid",
        runtime_provider_store=client.app.state.runtime_provider_store,
    )

    assert run["rejected_actions"][0]["action_type"] == "CREATE_TICKET"
    assert run["executed_actions"] == []


def test_ceo_shadow_run_marks_deferred_board_escalation(client, monkeypatch):
    workflow_id = _project_init(client, "CEO deferred board escalation")
    _set_live_provider(client)

    from app.core import ceo_proposer

    def _fake_invoke(_config, _rendered_payload):
        return OpenAICompatProviderResult(
            output_text=json.dumps(
                {
                    "summary": "Escalate to board later, but stay shadow-only now.",
                    "actions": [
                        {
                            "action_type": "ESCALATE_TO_BOARD",
                            "payload": {
                                "workflow_id": workflow_id,
                                "reason": "Potential board escalation should remain shadow-only in this round.",
                                "target_ref": "workflow",
                                "review_type": "VISUAL_MILESTONE",
                            },
                        }
                    ],
                }
            ),
            response_id="resp_ceo_escalate_1",
        )

    monkeypatch.setattr(ceo_proposer, "invoke_openai_compat_response", _fake_invoke)

    run = run_ceo_shadow_for_trigger(
        client.app.state.repository,
        workflow_id=workflow_id,
        trigger_type="MANUAL_TEST",
        trigger_ref="manual:escalate",
        runtime_provider_store=client.app.state.runtime_provider_store,
    )

    assert run["accepted_actions"][0]["action_type"] == "ESCALATE_TO_BOARD"
    assert run["executed_actions"][0]["execution_status"] == "DEFERRED_SHADOW_ONLY"
    assert run["deterministic_fallback_used"] is False


def test_ceo_shadow_run_records_execution_failure_without_breaking_mainline(client, monkeypatch):
    _set_deterministic_mode(client)
    workflow_id = _project_init(client, "CEO failed retry execution")
    _create_and_fail_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_ceo_retry_exhausted",
        node_id="node_ceo_retry_exhausted",
        retry_budget=0,
    )
    _set_live_provider(client)

    from app.core import ceo_proposer

    def _fake_invoke(_config, _rendered_payload):
        return OpenAICompatProviderResult(
            output_text=json.dumps(
                {
                    "summary": "Try a retry that should fail execution because budget is exhausted.",
                    "actions": [
                        {
                            "action_type": "RETRY_TICKET",
                            "payload": {
                                "workflow_id": workflow_id,
                                "ticket_id": "tkt_ceo_retry_exhausted",
                                "node_id": "node_ceo_retry_exhausted",
                                "reason": "Budget is already exhausted, so execution should fail safely.",
                            },
                        }
                    ],
                }
            ),
            response_id="resp_ceo_retry_fail_1",
        )

    monkeypatch.setattr(ceo_proposer, "invoke_openai_compat_response", _fake_invoke)

    run = run_ceo_shadow_for_trigger(
        client.app.state.repository,
        workflow_id=workflow_id,
        trigger_type="MANUAL_TEST",
        trigger_ref="manual:retry-fail",
        runtime_provider_store=client.app.state.runtime_provider_store,
    )

    assert run["executed_actions"][0]["execution_status"] == "FAILED"
    assert run["deterministic_fallback_used"] is True
    assert run["deterministic_fallback_reason"] is not None
    assert client.app.state.repository.get_current_ticket_projection("tkt_ceo_retry_exhausted")["status"] == "FAILED"


def test_ticket_fail_triggers_ceo_shadow_audit(client):
    _set_deterministic_mode(client)
    workflow_id = _project_init(client, "CEO shadow ticket fail trigger")
    _create_and_fail_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_ceo_shadow_fail",
        node_id="node_ceo_shadow_fail",
        retry_budget=1,
    )

    runs = client.app.state.repository.list_ceo_shadow_runs(workflow_id)
    assert runs
    assert any(run["trigger_type"] == "TICKET_FAILED" for run in runs)
    assert client.app.state.repository.get_current_ticket_projection("tkt_ceo_shadow_fail")["status"] == "FAILED"


def test_ticket_fail_can_trigger_ceo_meeting_request_in_deterministic_mode(client):
    _set_deterministic_mode(client)
    workflow_id = _seed_workflow(client, "wf_ceo_meeting_auto")
    _create_and_fail_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_ceo_meeting_auto",
        node_id="node_ceo_meeting_auto",
        retry_budget=0,
    )

    runs = client.app.state.repository.list_ceo_shadow_runs(workflow_id)
    ticket_fail_run = next(run for run in runs if run["trigger_type"] == "TICKET_FAILED")
    executed_meeting = next(
        item for item in ticket_fail_run["executed_actions"] if item["action_type"] == "REQUEST_MEETING"
    )
    meeting_id = executed_meeting["causation_hint"].split(":", 1)[1]
    meeting = client.app.state.repository.get_meeting_projection(meeting_id)

    assert ticket_fail_run["accepted_actions"][0]["action_type"] == "REQUEST_MEETING"
    assert executed_meeting["execution_status"] == "EXECUTED"
    assert meeting is not None
    assert meeting["meeting_type"] == "TECHNICAL_DECISION"
    assert meeting["source_ticket_id"].startswith("tkt_meeting_")


def test_live_provider_can_request_meeting_from_snapshot_candidate(client, monkeypatch):
    _set_deterministic_mode(client)
    workflow_id = _seed_workflow(client, "wf_ceo_live_meeting")
    import app.core.ticket_handlers as ticket_handlers

    monkeypatch.setattr(ticket_handlers, "run_ceo_shadow_for_trigger", lambda *args, **kwargs: None)
    _create_and_fail_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_ceo_live_meeting_source",
        node_id="node_ceo_live_meeting_source",
        retry_budget=0,
    )
    _set_live_provider(client)

    from app.core import ceo_proposer

    def _fake_invoke(_config, rendered_payload):
        snapshot = rendered_payload.messages[2].content_payload
        candidate = next(
            item
            for item in snapshot["meeting_candidates"]
            if item["source_ticket_id"] == "tkt_ceo_live_meeting_source"
        )
        return OpenAICompatProviderResult(
            output_text=json.dumps(
                {
                    "summary": "Open a bounded technical decision meeting before more serial retries.",
                    "actions": [
                        {
                            "action_type": "REQUEST_MEETING",
                            "payload": {
                                "workflow_id": workflow_id,
                                "meeting_type": "TECHNICAL_DECISION",
                                "source_node_id": candidate["source_node_id"],
                                "source_ticket_id": candidate["source_ticket_id"],
                                "topic": candidate["topic"],
                                "participant_employee_ids": candidate["participant_employee_ids"],
                                "recorder_employee_id": candidate["recorder_employee_id"],
                                "input_artifact_refs": candidate["input_artifact_refs"],
                                "reason": candidate["reason"],
                            },
                        }
                    ],
                }
            ),
            response_id="resp_ceo_request_meeting_1",
        )

    monkeypatch.setattr(ceo_proposer, "invoke_openai_compat_response", _fake_invoke)

    run = run_ceo_shadow_for_trigger(
        client.app.state.repository,
        workflow_id=workflow_id,
        trigger_type="TICKET_FAILED",
        trigger_ref="tkt_ceo_live_meeting_source",
        runtime_provider_store=client.app.state.runtime_provider_store,
    )

    assert run["provider_response_id"] == "resp_ceo_request_meeting_1"
    assert run["accepted_actions"][0]["action_type"] == "REQUEST_MEETING"
    assert run["executed_actions"][0]["action_type"] == "REQUEST_MEETING"
    assert run["executed_actions"][0]["execution_status"] == "EXECUTED"


def test_meeting_escalation_reject_does_not_trigger_recursive_ceo_meeting(client, set_ticket_time):
    set_ticket_time("2026-04-05T11:00:00+08:00")
    _set_deterministic_mode(client)
    workflow_id = _seed_workflow(client, "wf_ceo_no_recursion")

    request_response = client.post(
        "/api/v1/commands/meeting-request",
        json={
            "workflow_id": workflow_id,
            "meeting_type": "TECHNICAL_DECISION",
            "topic": "Lock the runtime contract once",
            "participant_employee_ids": ["emp_frontend_2", "emp_checker_1"],
            "recorder_employee_id": "emp_frontend_2",
            "input_artifact_refs": ["art://inputs/brief.md"],
            "max_rounds": 4,
            "idempotency_key": "meeting-request:ceo-no-recursion",
        },
    )
    meeting_id = request_response.json()["causation_hint"].split(":", 1)[1]

    from app.scheduler_runner import run_scheduler_once

    run_scheduler_once(
        client.app.state.repository,
        idempotency_key="scheduler-runner:ceo-no-recursion",
        max_dispatches=10,
    )
    meeting = client.app.state.repository.get_meeting_projection(meeting_id)
    checker_ticket_id = client.app.state.repository.get_current_node_projection(
        workflow_id,
        meeting["source_node_id"],
    )["latest_ticket_id"]

    lease_response = client.post(
        "/api/v1/commands/ticket-lease",
        json={
            "workflow_id": workflow_id,
            "ticket_id": checker_ticket_id,
            "node_id": meeting["source_node_id"],
            "leased_by": "emp_checker_1",
            "lease_timeout_sec": 600,
            "idempotency_key": f"ticket-lease:{workflow_id}:{checker_ticket_id}:checker",
        },
    )
    start_response = client.post(
        "/api/v1/commands/ticket-start",
        json={
            "workflow_id": workflow_id,
            "ticket_id": checker_ticket_id,
            "node_id": meeting["source_node_id"],
            "started_by": "emp_checker_1",
            "idempotency_key": f"ticket-start:{workflow_id}:{checker_ticket_id}:checker",
        },
    )
    submit_response = client.post(
        "/api/v1/commands/ticket-result-submit",
        json={
            "workflow_id": workflow_id,
            "ticket_id": checker_ticket_id,
            "node_id": meeting["source_node_id"],
            "submitted_by": "emp_checker_1",
            "result_status": "completed",
            "schema_version": "maker_checker_verdict_v1",
            "payload": {
                "summary": "Checker approved the meeting output.",
                "review_status": "APPROVED_WITH_NOTES",
                "findings": [],
            },
            "artifact_refs": [],
            "written_artifacts": [],
            "assumptions": [],
            "issues": [],
            "confidence": 0.9,
            "needs_escalation": False,
            "summary": "Checker verdict submitted.",
            "idempotency_key": f"ticket-result-submit:{workflow_id}:{checker_ticket_id}:approved",
        },
    )

    approval = next(
        item for item in client.app.state.repository.list_open_approvals() if item["workflow_id"] == workflow_id
    )
    reject_response = client.post(
        "/api/v1/commands/board-reject",
        json={
            "review_pack_id": approval["review_pack_id"],
            "review_pack_version": approval["review_pack_version"],
            "command_target_version": approval["command_target_version"],
            "approval_id": approval["approval_id"],
            "board_comment": "Reject the current meeting output.",
            "rejection_reasons": ["Need another governance decision."],
            "idempotency_key": f"board-reject:{approval['approval_id']}:ceo-no-recursion",
        },
    )

    runs = client.app.state.repository.list_ceo_shadow_runs(workflow_id)
    approval_run = next(run for run in runs if run["trigger_type"] == "APPROVAL_RESOLVED")

    assert lease_response.status_code == 200
    assert start_response.status_code == 200
    assert submit_response.status_code == 200
    assert reject_response.status_code == 200
    assert approval["approval_type"] == "MEETING_ESCALATION"
    assert approval_run["trigger_ref"] == approval["approval_id"]
    assert approval_run["accepted_actions"][0]["action_type"] == "NO_ACTION"
    assert all(item["action_type"] != "REQUEST_MEETING" for item in approval_run["accepted_actions"])
    assert any(
        event["event_type"] == EVENT_BOARD_REVIEW_REJECTED
        for event in client.app.state.repository.list_events_for_testing()
        if (event.get("payload") or {}).get("approval_id") == approval["approval_id"]
    )


def test_board_approve_triggers_ceo_shadow_projection_route(client):
    _set_deterministic_mode(client)
    workflow_id = _project_init(client, "CEO shadow approval trigger")
    _approve_scope_review(client, workflow_id)

    response = client.get(f"/api/v1/projections/workflows/{workflow_id}/ceo-shadow")

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["workflow_id"] == workflow_id
    assert payload["runs"]
    assert any(item["trigger_type"] == "APPROVAL_RESOLVED" for item in payload["runs"])


def test_ceo_shadow_projection_route_exposes_execution_fields(client, monkeypatch):
    workflow_id = _project_init(client, "CEO projection execution fields")
    _set_live_provider(client)

    from app.core import ceo_proposer

    def _fake_invoke(_config, _rendered_payload):
        return OpenAICompatProviderResult(
            output_text=json.dumps(
                {
                    "summary": "Hire a checker so projection includes executed actions.",
                    "actions": [
                        {
                            "action_type": "HIRE_EMPLOYEE",
                            "payload": {
                                "workflow_id": workflow_id,
                                "role_type": "checker",
                                "role_profile_refs": ["checker_primary"],
                                "request_summary": "Hire a checker from CEO limited execution.",
                                "employee_id_hint": "emp_checker_projection",
                                "provider_id": "prov_openai_compat",
                            },
                        }
                    ],
                }
            ),
            response_id="resp_ceo_projection_1",
        )

    monkeypatch.setattr(ceo_proposer, "invoke_openai_compat_response", _fake_invoke)

    run_ceo_shadow_for_trigger(
        client.app.state.repository,
        workflow_id=workflow_id,
        trigger_type="MANUAL_TEST",
        trigger_ref="manual:projection-fields",
        runtime_provider_store=client.app.state.runtime_provider_store,
    )

    response = client.get(f"/api/v1/projections/workflows/{workflow_id}/ceo-shadow")

    assert response.status_code == 200
    payload = response.json()["data"]["runs"][0]
    assert "executed_actions" in payload
    assert "execution_summary" in payload
    assert "deterministic_fallback_used" in payload
    assert payload["executed_actions"][0]["execution_status"] == "EXECUTED"


def test_incident_resolve_triggers_ceo_shadow_audit(client):
    _set_deterministic_mode(client)
    workflow_id = _project_init(client, "CEO shadow incident recovery trigger")
    repository = client.app.state.repository

    with repository.transaction() as connection:
        repository.insert_event(
            connection,
            event_type=EVENT_INCIDENT_OPENED,
            actor_type="system",
            actor_id="test-seed",
            workflow_id=workflow_id,
            idempotency_key=f"incident-opened:{workflow_id}:ceo-shadow",
            causation_id=None,
            correlation_id=workflow_id,
            payload={
                "incident_id": "inc_ceo_shadow_1",
                "incident_type": "REPEATED_FAILURE_ESCALATION",
                "status": "OPEN",
                "severity": "high",
                "fingerprint": "shadow:test:fingerprint",
            },
            occurred_at=repository.get_active_workflow()["started_at"],
        )
        repository.insert_event(
            connection,
            event_type=EVENT_CIRCUIT_BREAKER_OPENED,
            actor_type="system",
            actor_id="test-seed",
            workflow_id=workflow_id,
            idempotency_key=f"breaker-opened:{workflow_id}:ceo-shadow",
            causation_id=None,
            correlation_id=workflow_id,
            payload={
                "incident_id": "inc_ceo_shadow_1",
                "incident_type": "REPEATED_FAILURE_ESCALATION",
                "circuit_breaker_state": "OPEN",
                "fingerprint": "shadow:test:fingerprint",
            },
            occurred_at=repository.get_active_workflow()["started_at"],
        )
        repository.refresh_projections(connection)

    response = client.post(
        "/api/v1/commands/incident-resolve",
        json={
            "incident_id": "inc_ceo_shadow_1",
            "resolved_by": "ops@example.com",
            "resolution_summary": "Resume normal flow after manual check.",
            "followup_action": "RESTORE_ONLY",
            "idempotency_key": f"incident-resolve:{workflow_id}:ceo-shadow",
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "ACCEPTED"
    runs = repository.list_ceo_shadow_runs(workflow_id)
    assert runs[0]["trigger_type"] == "INCIDENT_RECOVERY_STARTED"


def test_idle_ceo_maintenance_targets_pending_workflow_once_per_interval(
    client,
    monkeypatch,
    set_ticket_time,
):
    set_ticket_time("2026-04-04T10:00:00+08:00")
    _set_deterministic_mode(client)
    monkeypatch.setattr(
        client.app.state.repository,
        "list_scheduler_worker_candidates",
        lambda connection=None: [],
    )
    workflow_id = _project_init(client, "CEO idle maintenance pending scope")
    repository = client.app.state.repository
    current_time = repository.get_active_workflow()["updated_at"]

    due_before = {
        item["workflow_id"]
        for item in list_due_ceo_maintenance_workflows(
            repository,
            current_time=current_time,
            interval_sec=60,
        )
    }
    runs = run_due_ceo_maintenance(
        repository,
        current_time=current_time,
        trigger_ref="scheduler-runner:test-idle-maintenance",
        interval_sec=60,
    )
    due_after = {
        item["workflow_id"]
        for item in list_due_ceo_maintenance_workflows(
            repository,
            current_time=current_time,
            interval_sec=60,
        )
    }

    assert workflow_id in due_before
    assert runs[0]["trigger_type"] == SCHEDULER_IDLE_MAINTENANCE_TRIGGER
    assert workflow_id not in due_after


def test_idle_ceo_maintenance_skips_workflow_waiting_for_board_review(client, set_ticket_time):
    set_ticket_time("2026-04-04T10:00:00+08:00")
    _set_deterministic_mode(client)
    workflow_id = _project_init(client, "CEO idle maintenance open approval")
    repository = client.app.state.repository
    current_time = repository.get_active_workflow()["updated_at"]

    due_workflow_ids = {
        item["workflow_id"]
        for item in list_due_ceo_maintenance_workflows(
            repository,
            current_time=current_time,
            interval_sec=60,
        )
    }

    assert workflow_id not in due_workflow_ids
