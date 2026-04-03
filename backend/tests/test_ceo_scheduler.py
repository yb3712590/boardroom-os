from __future__ import annotations

import json

from app.core.ceo_scheduler import run_ceo_shadow_for_trigger
from app.core.constants import EVENT_CIRCUIT_BREAKER_OPENED, EVENT_INCIDENT_OPENED
from app.core.provider_openai_compat import OpenAICompatProviderResult
from app.core.runtime_provider_config import RuntimeProviderMode, RuntimeProviderStoredConfig


def _project_init(client, goal: str = "CEO shadow test") -> str:
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
        "retry_budget": 0,
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


def test_ceo_shadow_run_uses_live_provider_and_validates_actions(client, monkeypatch):
    workflow_id = _project_init(client, "CEO shadow live provider")
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


def test_ticket_fail_triggers_ceo_shadow_audit(client):
    _set_deterministic_mode(client)
    workflow_id = _project_init(client, "CEO shadow ticket fail trigger")
    create_response = client.post(
        "/api/v1/commands/ticket-create",
        json=_ticket_create_payload(
            workflow_id=workflow_id,
            ticket_id="tkt_ceo_shadow_fail",
            node_id="node_ceo_shadow_fail",
        ),
    )
    assert create_response.status_code == 200
    assert create_response.json()["status"] == "ACCEPTED"

    lease_response = client.post(
        "/api/v1/commands/ticket-lease",
        json={
            "workflow_id": workflow_id,
            "ticket_id": "tkt_ceo_shadow_fail",
            "node_id": "node_ceo_shadow_fail",
            "leased_by": "emp_frontend_2",
            "lease_timeout_sec": 600,
            "idempotency_key": f"ticket-lease:{workflow_id}:tkt_ceo_shadow_fail",
        },
    )
    assert lease_response.status_code == 200
    start_response = client.post(
        "/api/v1/commands/ticket-start",
        json={
            "workflow_id": workflow_id,
            "ticket_id": "tkt_ceo_shadow_fail",
            "node_id": "node_ceo_shadow_fail",
            "started_by": "emp_frontend_2",
            "idempotency_key": f"ticket-start:{workflow_id}:tkt_ceo_shadow_fail",
        },
    )
    assert start_response.status_code == 200

    fail_response = client.post(
        "/api/v1/commands/ticket-fail",
        json={
            "workflow_id": workflow_id,
            "ticket_id": "tkt_ceo_shadow_fail",
            "node_id": "node_ceo_shadow_fail",
            "failed_by": "emp_frontend_2",
            "failure_kind": "TEST_FAILURE",
            "failure_message": "Synthetic failure for CEO shadow trigger coverage.",
            "failure_detail": {},
            "idempotency_key": f"ticket-fail:{workflow_id}:tkt_ceo_shadow_fail",
        },
    )
    assert fail_response.status_code == 200
    assert fail_response.json()["status"] == "ACCEPTED"

    runs = client.app.state.repository.list_ceo_shadow_runs(workflow_id)
    assert runs
    assert any(run["trigger_type"] == "TICKET_FAILED" for run in runs)
    assert client.app.state.repository.get_current_ticket_projection("tkt_ceo_shadow_fail")["status"] == "FAILED"


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
