from __future__ import annotations

import json
from datetime import datetime

import pytest
import app.core.graph_health as graph_health_module
import tests.test_api as api_test_helpers

from app.contracts.ceo_actions import CEOActionBatch
from app.core.ceo_snapshot import build_ceo_shadow_snapshot
from app.core.ceo_execution_presets import (
    PROJECT_INIT_SCOPE_NODE_ID,
    build_project_init_scope_ticket_id,
)
from app.core.governance_profiles import build_default_governance_profile
from app.core.ceo_prompts import build_ceo_shadow_system_prompt
from app.core.ceo_validator import validate_ceo_action_batch
from app.core.execution_targets import infer_execution_contract_payload
from app.core.output_schemas import (
    ARCHITECTURE_BRIEF_SCHEMA_REF,
    BACKLOG_RECOMMENDATION_SCHEMA_REF,
    DETAILED_DESIGN_SCHEMA_REF,
    MILESTONE_PLAN_SCHEMA_REF,
    TECHNOLOGY_DECISION_SCHEMA_REF,
)
from app.core.ceo_scheduler import (
    CeoShadowPipelineError,
    SCHEDULER_IDLE_MAINTENANCE_TRIGGER,
    is_ticket_graph_unavailable_error,
    list_due_ceo_maintenance_workflows,
    run_ceo_shadow_for_trigger,
    run_due_ceo_maintenance,
    trigger_ceo_shadow_with_recovery,
)
from app.core.constants import (
    EVENT_BOARD_REVIEW_REJECTED,
    EVENT_BOARD_DIRECTIVE_RECEIVED,
    EVENT_CIRCUIT_BREAKER_OPENED,
    EVENT_EMPLOYEE_HIRED,
    EVENT_INCIDENT_OPENED,
    INCIDENT_TYPE_CEO_SHADOW_PIPELINE_FAILED,
    EVENT_WORKFLOW_CREATED,
)
from app.core.persona_profiles import clone_persona_template, get_hire_persona_template_id
from app.core.provider_openai_compat import OpenAICompatProviderResult, OpenAICompatProviderUnavailableError
from app.core.runtime_provider_config import (
    CLAUDE_CODE_PROVIDER_ID,
    OPENAI_COMPAT_PROVIDER_ID,
    ROLE_BINDING_CEO_SHADOW,
    RuntimeProviderConfigEntry,
    RuntimeProviderRoleBinding,
    RuntimeProviderStoredConfig,
)


def _assert_command_status(
    response,
    *,
    expected_status: str = "ACCEPTED",
    expected_reason_contains: str | None = None,
) -> dict:
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == expected_status
    if expected_reason_contains is not None:
        assert expected_reason_contains in str(payload.get("reason") or "")
    return payload


class _temporary_live_provider:
    def __init__(self, client):
        self.client = client
        self.store = client.app.state.runtime_provider_store
        self.previous_config = None

    def __enter__(self):
        self.previous_config = self.store.load_saved_config()
        _set_live_provider(self.client)
        return self

    def __exit__(self, exc_type, exc, tb):
        if self.previous_config is None:
            _set_deterministic_mode(self.client)
        else:
            self.store.save_config(self.previous_config)
        return False


def _create_ticket_for_test(client, payload: dict) -> dict:
    return _assert_command_status(client.post("/api/v1/commands/ticket-create", json=payload))


def _lease_ticket_for_test(
    client,
    *,
    workflow_id: str,
    ticket_id: str,
    node_id: str,
    leased_by: str,
    idempotency_key: str,
    expected_status: str = "ACCEPTED",
    expected_reason_contains: str | None = None,
) -> dict:
    return _assert_command_status(
        client.post(
            "/api/v1/commands/ticket-lease",
            json={
                "workflow_id": workflow_id,
                "ticket_id": ticket_id,
                "node_id": node_id,
                "leased_by": leased_by,
                "lease_timeout_sec": 600,
                "idempotency_key": idempotency_key,
            },
        ),
        expected_status=expected_status,
        expected_reason_contains=expected_reason_contains,
    )


def _start_ticket_for_test(
    client,
    *,
    workflow_id: str,
    ticket_id: str,
    node_id: str,
    started_by: str,
    idempotency_key: str,
    expected_status: str = "ACCEPTED",
    expected_reason_contains: str | None = None,
) -> dict:
    return _assert_command_status(
        client.post(
            "/api/v1/commands/ticket-start",
            json={
                "workflow_id": workflow_id,
                "ticket_id": ticket_id,
                "node_id": node_id,
                "started_by": started_by,
                "idempotency_key": idempotency_key,
            },
        ),
        expected_status=expected_status,
        expected_reason_contains=expected_reason_contains,
    )


def _submit_ticket_result_for_test(client, payload: dict) -> dict:
    return _assert_command_status(client.post("/api/v1/commands/ticket-result-submit", json=payload))


def _complete_checker_verdict_for_test(
    client,
    *,
    workflow_id: str,
    ticket_id: str,
    node_id: str,
    submitted_by: str = "emp_checker_1",
    review_status: str = "APPROVED_WITH_NOTES",
    findings: list[dict] | None = None,
    idempotency_key: str,
) -> None:
    _lease_ticket_for_test(
        client,
        workflow_id=workflow_id,
        ticket_id=ticket_id,
        node_id=node_id,
        leased_by=submitted_by,
        idempotency_key=f"ticket-lease:{workflow_id}:{ticket_id}:{submitted_by}",
    )
    _start_ticket_for_test(
        client,
        workflow_id=workflow_id,
        ticket_id=ticket_id,
        node_id=node_id,
        started_by=submitted_by,
        idempotency_key=f"ticket-start:{workflow_id}:{ticket_id}:{submitted_by}",
    )
    _submit_ticket_result_for_test(
        client,
        api_test_helpers._maker_checker_result_submit_payload(
            workflow_id=workflow_id,
            ticket_id=ticket_id,
            node_id=node_id,
            submitted_by=submitted_by,
            review_status=review_status,
            findings=findings,
            idempotency_key=idempotency_key,
        ),
    )


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
        repository.save_governance_profile(
            connection,
            build_default_governance_profile(
                workflow_id=workflow_id,
                source_ref=f"test://workflow/{workflow_id}/charter",
                effective_from_event=f"workflow-created:{workflow_id}",
            ),
        )
        repository.refresh_projections(connection)
    return workflow_id


def _set_deterministic_mode(client) -> None:
    client.app.state.runtime_provider_store.save_config(
        RuntimeProviderStoredConfig(
            default_provider_id=None,
            providers=[],
            role_bindings=[],
        )
    )


def _set_live_provider(client) -> None:
    client.app.state.runtime_provider_store.save_config(
        RuntimeProviderStoredConfig(
            default_provider_id=OPENAI_COMPAT_PROVIDER_ID,
            providers=[
                RuntimeProviderConfigEntry(
                    provider_id=OPENAI_COMPAT_PROVIDER_ID,
                    adapter_kind="openai_compat",
                    label="OpenAI Compat",
                    enabled=True,
                    base_url="https://api.example.test/v1",
                    api_key="sk-test-secret",
                    model="gpt-5.3-codex",
                    timeout_sec=30.0,
                    reasoning_effort="medium",
                ),
                RuntimeProviderConfigEntry(
                    provider_id=CLAUDE_CODE_PROVIDER_ID,
                    adapter_kind="claude_code_cli",
                    label="Claude Code CLI",
                    enabled=False,
                    command_path="/Users/bill/.local/bin/claude",
                    model="claude-sonnet-4-6",
                    timeout_sec=30.0,
                ),
            ],
            role_bindings=[],
        )
    )


def _persist_autopilot_workflow_profile(repository, workflow_id: str) -> None:
    with repository.transaction() as connection:
        row = connection.execute(
            """
            SELECT event_id, payload_json
            FROM events
            WHERE workflow_id = ? AND event_type = ?
            ORDER BY sequence_no ASC
            LIMIT 1
            """,
            (workflow_id, EVENT_WORKFLOW_CREATED),
        ).fetchone()
        payload = json.loads(row["payload_json"])
        payload["workflow_profile"] = "CEO_AUTOPILOT_FINE_GRAINED"
        connection.execute(
            "UPDATE events SET payload_json = ? WHERE event_id = ?",
            (json.dumps(payload, sort_keys=True), row["event_id"]),
        )
        repository.refresh_projections(connection)


def _persist_workflow_directive_details(
    repository,
    workflow_id: str,
    *,
    workflow_profile: str | None = None,
    hard_constraints: list[str] | None = None,
) -> None:
    with repository.transaction() as connection:
        rows = connection.execute(
            """
            SELECT event_id, payload_json
            FROM events
            WHERE workflow_id = ? AND event_type IN (?, ?)
            ORDER BY sequence_no ASC
            """,
            (workflow_id, EVENT_WORKFLOW_CREATED, EVENT_BOARD_DIRECTIVE_RECEIVED),
        ).fetchall()
        for row in rows:
            payload = json.loads(row["payload_json"])
            if workflow_profile is not None:
                payload["workflow_profile"] = workflow_profile
            if hard_constraints is not None:
                payload["hard_constraints"] = list(hard_constraints)
            connection.execute(
                "UPDATE events SET payload_json = ? WHERE event_id = ?",
                (json.dumps(payload, sort_keys=True), row["event_id"]),
            )
        if workflow_profile is not None:
            connection.execute(
                "UPDATE workflow_projection SET workflow_profile = ? WHERE workflow_id = ?",
                (workflow_profile, workflow_id),
            )
        repository.refresh_projections(connection)


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
    role_profile_ref: str = "frontend_engineer_primary",
    output_schema_ref: str = "ui_milestone_review",
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
            "keywords": ["shadow", "test"],
            "semantic_queries": ["ceo shadow test"],
            "max_context_tokens": 3000,
        },
        "acceptance_criteria": ["Must produce a structured result."],
        "output_schema_ref": output_schema_ref,
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
    failure_kind: str = "TEST_FAILURE",
    failure_message: str = "Synthetic failure for CEO limited execution coverage.",
    failure_detail: dict | None = None,
    role_profile_ref: str = "frontend_engineer_primary",
    output_schema_ref: str = "ui_milestone_review",
    leased_by: str = "emp_frontend_2",
) -> None:
    _create_ticket_for_test(
        client,
        _ticket_create_payload(
            workflow_id=workflow_id,
            ticket_id=ticket_id,
            node_id=node_id,
            retry_budget=retry_budget,
            role_profile_ref=role_profile_ref,
            output_schema_ref=output_schema_ref,
        ),
    )

    with _temporary_live_provider(client):
        _lease_ticket_for_test(
            client,
            workflow_id=workflow_id,
            ticket_id=ticket_id,
            node_id=node_id,
            leased_by=leased_by,
            idempotency_key=f"ticket-lease:{workflow_id}:{ticket_id}",
        )
        _start_ticket_for_test(
            client,
            workflow_id=workflow_id,
            ticket_id=ticket_id,
            node_id=node_id,
            started_by=leased_by,
            idempotency_key=f"ticket-start:{workflow_id}:{ticket_id}",
        )
        _assert_command_status(
            client.post(
                "/api/v1/commands/ticket-fail",
                json={
                    "workflow_id": workflow_id,
                    "ticket_id": ticket_id,
                    "node_id": node_id,
                    "failed_by": leased_by,
                    "failure_kind": failure_kind,
                    "failure_message": failure_message,
                    "failure_detail": failure_detail or {},
                    "idempotency_key": f"ticket-fail:{workflow_id}:{ticket_id}",
                },
            ),
        )


def _seed_board_approved_employee(
    client,
    *,
    employee_id: str,
    role_type: str,
    role_profile_refs: list[str],
    provider_id: str = OPENAI_COMPAT_PROVIDER_ID,
) -> None:
    repository = client.app.state.repository
    persona = clone_persona_template(get_hire_persona_template_id(role_type))
    with repository.transaction() as connection:
        repository.insert_event(
            connection,
            event_type=EVENT_EMPLOYEE_HIRED,
            actor_type="system",
            actor_id="test-seed",
            workflow_id=None,
            idempotency_key=f"test-seed-employee:{employee_id}",
            causation_id=None,
            correlation_id=None,
            payload={
                "employee_id": employee_id,
                "role_type": role_type,
                "skill_profile": persona["skill_profile"],
                "personality_profile": persona["personality_profile"],
                "aesthetic_profile": persona["aesthetic_profile"],
                "state": "ACTIVE",
                "board_approved": True,
                "provider_id": provider_id,
                "role_profile_refs": role_profile_refs,
            },
            occurred_at=datetime.fromisoformat("2026-04-04T18:00:00+08:00"),
        )
        repository.refresh_projections(connection)


def _create_and_complete_ticket(
    client,
    *,
    workflow_id: str,
    ticket_id: str,
    node_id: str,
    summary: str = "Completed implementation slice ready for reuse.",
) -> None:
    _create_ticket_for_test(
        client,
        {
            **_ticket_create_payload(
                workflow_id=workflow_id,
                ticket_id=ticket_id,
                node_id=node_id,
                retry_budget=0,
            ),
            "output_schema_ref": "source_code_delivery",
        },
    )

    with _temporary_live_provider(client):
        _lease_ticket_for_test(
            client,
            workflow_id=workflow_id,
            ticket_id=ticket_id,
            node_id=node_id,
            leased_by="emp_frontend_2",
            idempotency_key=f"ticket-lease:{workflow_id}:{ticket_id}:complete",
        )
        _start_ticket_for_test(
            client,
            workflow_id=workflow_id,
            ticket_id=ticket_id,
            node_id=node_id,
            started_by="emp_frontend_2",
            idempotency_key=f"ticket-start:{workflow_id}:{ticket_id}:complete",
        )
        submit_payload = api_test_helpers._source_code_delivery_result_submit_payload(
            workflow_id=workflow_id,
            ticket_id=ticket_id,
            node_id=node_id,
            written_artifact_path="artifacts/ui/homepage/source-code.tsx",
            idempotency_key=f"ticket-result-submit:{workflow_id}:{ticket_id}:complete",
        )
        submit_payload["payload"]["summary"] = summary
        submit_payload["summary"] = summary
        _submit_ticket_result_for_test(client, submit_payload)


def _create_and_complete_governance_ticket(
    client,
    *,
    workflow_id: str,
    ticket_id: str,
    node_id: str,
    output_schema_ref: str = ARCHITECTURE_BRIEF_SCHEMA_REF,
    summary: str = "Structured governance document is ready for downstream delivery.",
    approve_internal_gate: bool = True,
    role_profile_ref: str = "frontend_engineer_primary",
    leased_by: str = "emp_frontend_2",
) -> None:
    _create_ticket_for_test(
        client,
        {
            **_ticket_create_payload(
                workflow_id=workflow_id,
                ticket_id=ticket_id,
                node_id=node_id,
                retry_budget=0,
            ),
            "role_profile_ref": role_profile_ref,
            "output_schema_ref": output_schema_ref,
            "allowed_write_set": [f"reports/governance/{ticket_id}/*"],
        },
    )

    with _temporary_live_provider(client):
        _lease_ticket_for_test(
            client,
            workflow_id=workflow_id,
            ticket_id=ticket_id,
            node_id=node_id,
            leased_by=leased_by,
            idempotency_key=f"ticket-lease:{workflow_id}:{ticket_id}:governance",
        )
        _start_ticket_for_test(
            client,
            workflow_id=workflow_id,
            ticket_id=ticket_id,
            node_id=node_id,
            started_by=leased_by,
            idempotency_key=f"ticket-start:{workflow_id}:{ticket_id}:governance",
        )
        submit_payload = api_test_helpers._governance_document_result_submit_payload(
            workflow_id=workflow_id,
            ticket_id=ticket_id,
            node_id=node_id,
            output_schema_ref=output_schema_ref,
            summary=summary,
        )
        submit_payload["submitted_by"] = leased_by
        _submit_ticket_result_for_test(client, submit_payload)

    if not approve_internal_gate:
        return

    repository = client.app.state.repository
    current_node = repository.get_current_node_projection(workflow_id, node_id)
    if current_node is None or current_node["latest_ticket_id"] == ticket_id:
        return

    checker_ticket_id = current_node["latest_ticket_id"]
    with _temporary_live_provider(client):
        _complete_checker_verdict_for_test(
            client,
            workflow_id=workflow_id,
            ticket_id=checker_ticket_id,
            node_id=node_id,
            idempotency_key=f"ticket-result-submit:{workflow_id}:{checker_ticket_id}:governance-approved",
        )


def _create_and_board_approve_consensus_ticket(
    client,
    *,
    workflow_id: str,
    ticket_id: str,
    node_id: str,
    summary: str = "Board-approved consensus is ready for reuse.",
) -> None:
    _create_ticket_for_test(
        client,
        {
            **_ticket_create_payload(
                workflow_id=workflow_id,
                ticket_id=ticket_id,
                node_id=node_id,
                retry_budget=0,
                role_profile_ref="ui_designer_primary",
                output_schema_ref="consensus_document",
            ),
            "allowed_write_set": [f"reports/meeting/{ticket_id}/*"],
            "input_artifact_refs": ["art://inputs/brief.md", "art://inputs/scope-notes.md"],
            "acceptance_criteria": [
                "Must produce a consensus document.",
                "Must include follow-up tickets.",
            ],
            "allowed_tools": ["read_artifact", "write_artifact"],
            "context_query_plan": {
                "keywords": ["scope", "decision", "meeting"],
                "semantic_queries": ["current scope tradeoffs"],
                "max_context_tokens": 3000,
            },
        },
    )

    artifact_ref = f"art://meeting/{ticket_id}/consensus-document.json"
    result_payload = {
        "topic": f"Consensus for {ticket_id}",
        "participants": ["emp_frontend_2", "emp_checker_1"],
        "input_artifact_refs": ["art://inputs/brief.md", "art://inputs/scope-notes.md"],
        "consensus_summary": summary,
        "rejected_options": ["Do not widen the MVP scope in this round."],
        "open_questions": ["Whether polish should move after board approval."],
        "followup_tickets": [
            {
                "ticket_id": f"{ticket_id}_followup_review",
                "task_title": "Prepare the board review package",
                "owner_role": "frontend_engineer",
                "summary": "Prepare the board-facing review package without widening scope.",
                "delivery_stage": "REVIEW",
            }
        ],
    }
    review_request = {
        "review_type": "MEETING_ESCALATION",
        "priority": "high",
        "title": "Review scope decision consensus",
        "subtitle": "Meeting output is ready for board lock-in.",
        "blocking_scope": "WORKFLOW",
        "trigger_reason": "Cross-role scope decision needs explicit board confirmation.",
        "why_now": "Implementation should not continue before this decision is locked.",
        "recommended_action": "APPROVE",
        "recommended_option_id": "consensus_scope_lock",
        "recommendation_summary": summary,
        "options": [
            {
                "option_id": "consensus_scope_lock",
                "label": "Lock consensus scope",
                "summary": summary,
                "artifact_refs": [artifact_ref],
                "pros": ["Keeps the next step aligned."],
                "cons": ["Defers non-critical stretch ideas."],
                "risks": ["A later change needs a fresh governance pass."],
            }
        ],
        "evidence_summary": [
            {
                "evidence_id": "ev_meeting_consensus",
                "source_type": "CONSENSUS_DOCUMENT",
                "headline": "Meeting converged on one scope",
                "summary": summary,
                "source_ref": artifact_ref,
            }
        ],
        "available_actions": ["APPROVE", "REJECT", "MODIFY_CONSTRAINTS"],
        "draft_selected_option_id": "consensus_scope_lock",
        "comment_template": "",
        "inbox_title": "Review scope decision consensus",
        "inbox_summary": "A consensus document is ready for board review.",
        "badges": ["meeting", "board_gate", "scope"],
    }
    with _temporary_live_provider(client):
        _lease_ticket_for_test(
            client,
            workflow_id=workflow_id,
            ticket_id=ticket_id,
            node_id=node_id,
            leased_by="emp_frontend_2",
            idempotency_key=f"ticket-lease:{workflow_id}:{ticket_id}:consensus",
        )
        _start_ticket_for_test(
            client,
            workflow_id=workflow_id,
            ticket_id=ticket_id,
            node_id=node_id,
            started_by="emp_frontend_2",
            idempotency_key=f"ticket-start:{workflow_id}:{ticket_id}:consensus",
        )
        _submit_ticket_result_for_test(
            client,
            {
                **api_test_helpers._consensus_document_result_submit_payload(
                    workflow_id=workflow_id,
                    ticket_id=ticket_id,
                    node_id=node_id,
                    payload=result_payload,
                    review_request=review_request,
                    include_review_request=True,
                    artifact_refs=[artifact_ref],
                    idempotency_key=f"ticket-result-submit:{workflow_id}:{ticket_id}:consensus",
                ),
                "written_artifacts": [
                    {
                        "path": f"reports/meeting/{ticket_id}/consensus-document.json",
                        "artifact_ref": artifact_ref,
                        "kind": "JSON",
                        "content_json": result_payload,
                    }
                ],
            },
        )

    repository = client.app.state.repository
    checker_ticket_id = repository.get_current_node_projection(workflow_id, node_id)["latest_ticket_id"]
    with _temporary_live_provider(client):
        _complete_checker_verdict_for_test(
            client,
            workflow_id=workflow_id,
            ticket_id=checker_ticket_id,
            node_id=node_id,
            idempotency_key=f"ticket-result-submit:{workflow_id}:{checker_ticket_id}:approved",
        )

    approval = next(
        item
        for item in repository.list_open_approvals()
        if item["workflow_id"] == workflow_id and item["approval_type"] == "MEETING_ESCALATION"
    )
    option_id = approval["payload"]["review_pack"]["options"][0]["option_id"]
    _assert_command_status(
        client.post(
            "/api/v1/commands/board-approve",
            json={
                "review_pack_id": approval["review_pack_id"],
                "review_pack_version": approval["review_pack_version"],
                "command_target_version": approval["command_target_version"],
                "approval_id": approval["approval_id"],
                "selected_option_id": option_id,
                "board_comment": "Approve consensus and keep it reusable.",
                "idempotency_key": f"board-approve:{approval['approval_id']}:consensus",
            },
        ),
    )


def _create_and_complete_backlog_recommendation_ticket(
    client,
    *,
    workflow_id: str,
    ticket_id: str,
    node_id: str,
    approve_internal_gate: bool = True,
    tickets: list[dict] | None = None,
    dependency_graph: list[dict] | None = None,
    recommended_sequence: list[str] | None = None,
) -> None:
    _create_ticket_for_test(
        client,
        {
            **_ticket_create_payload(
                workflow_id=workflow_id,
                ticket_id=ticket_id,
                node_id=node_id,
                retry_budget=0,
            ),
            "role_profile_ref": "frontend_engineer_primary",
            "output_schema_ref": BACKLOG_RECOMMENDATION_SCHEMA_REF,
            "allowed_write_set": [f"reports/governance/{ticket_id}/*"],
        },
    )

    artifact_ref = f"art://runtime/{ticket_id}/{BACKLOG_RECOMMENDATION_SCHEMA_REF}.json"
    backlog_payload = {
        "document_kind_ref": BACKLOG_RECOMMENDATION_SCHEMA_REF,
        "title": "图书馆管理系统 backlog recommendation",
        "summary": "把治理文档转成可执行 backlog。",
        "linked_document_refs": ["doc://governance/upstream/current"],
        "linked_artifact_refs": [artifact_ref],
        "source_process_asset_refs": [],
        "decisions": ["继续保持单一 MVP 范围，并把实现任务拆细。"],
        "constraints": ["必须继续显式拆票，不能直接跳过任务分解。"],
        "sections": [
            {
                "section_id": "recommended_ticket_split",
                "label": "推荐工单拆分",
                "summary": "把 backlog recommendation 变成实现工单。",
                "content_markdown": "先做底座，再做登录，再做仪表盘。",
                "content_json": {
                    "tickets": tickets
                    or [
                        {
                            "ticket_id": "BR-T01",
                            "name": "登录能力交付",
                            "priority": "P0",
                            "scope": ["P-01 登录页", "M1 认证模块"],
                        },
                        {
                            "ticket_id": "BR-T02",
                            "name": "主布局与通用组件底座",
                            "priority": "P0",
                            "scope": ["后台主布局", "M2 布局模块", "M7 通用组件"],
                        },
                        {
                            "ticket_id": "BR-T03",
                            "name": "首页仪表盘交付",
                            "priority": "P1",
                            "scope": ["P-02 首页仪表盘", "M6 仪表盘模块"],
                        },
                    ]
                },
            },
            {
                "section_id": "dependency_and_sequence_plan",
                "label": "依赖关系与实施顺序",
                "summary": "先底座，再登录，再仪表盘。",
                "content_markdown": "BR-T02 和 BR-T01 先行，BR-T03 依赖 BR-T02。",
                "content_json": {
                    "dependency_graph": dependency_graph
                    or [
                        {
                            "ticket_id": "BR-T01",
                            "depends_on": [],
                            "reason": "登录能力可以独立先行。",
                        },
                        {
                            "ticket_id": "BR-T02",
                            "depends_on": [],
                            "reason": "布局底座建议最早交付。",
                        },
                        {
                            "ticket_id": "BR-T03",
                            "depends_on": ["BR-T02"],
                            "reason": "仪表盘需要布局承载。",
                        },
                    ],
                    "recommended_sequence": recommended_sequence
                    or [
                        "BR-T02 主布局与通用组件底座",
                        "BR-T01 登录能力交付",
                        "BR-T03 首页仪表盘交付",
                    ],
                },
            },
        ],
        "followup_recommendations": [
            {
                "recommendation_id": "rec_impl_followup",
                "summary": "创建实现工单并保留审计链路。",
                "target_role": "frontend_engineer",
            }
        ],
    }
    with _temporary_live_provider(client):
        _lease_ticket_for_test(
            client,
            workflow_id=workflow_id,
            ticket_id=ticket_id,
            node_id=node_id,
            leased_by="emp_frontend_2",
            idempotency_key=f"ticket-lease:{workflow_id}:{ticket_id}:backlog",
        )
        _start_ticket_for_test(
            client,
            workflow_id=workflow_id,
            ticket_id=ticket_id,
            node_id=node_id,
            started_by="emp_frontend_2",
            idempotency_key=f"ticket-start:{workflow_id}:{ticket_id}:backlog",
        )
        _submit_ticket_result_for_test(
            client,
            {
                "workflow_id": workflow_id,
                "ticket_id": ticket_id,
                "node_id": node_id,
                "submitted_by": "emp_frontend_2",
                "result_status": "completed",
                "schema_version": f"{BACKLOG_RECOMMENDATION_SCHEMA_REF}_v1",
                "payload": backlog_payload,
                "artifact_refs": [artifact_ref],
                "written_artifacts": [
                    {
                        "path": f"reports/governance/{ticket_id}/{BACKLOG_RECOMMENDATION_SCHEMA_REF}.json",
                        "artifact_ref": artifact_ref,
                        "kind": "JSON",
                        "content_json": backlog_payload,
                    }
                ],
                "assumptions": ["backlog recommendation 可以直接转成实现工单。"],
                "issues": [],
                "confidence": 0.88,
                "needs_escalation": False,
                "summary": "backlog recommendation 已完成。",
                "idempotency_key": f"ticket-result-submit:{workflow_id}:{ticket_id}:backlog",
            },
        )

    if not approve_internal_gate:
        return

    repository = client.app.state.repository
    current_node = repository.get_current_node_projection(workflow_id, node_id)
    if current_node is None or current_node["latest_ticket_id"] == ticket_id:
        return

    checker_ticket_id = current_node["latest_ticket_id"]
    with _temporary_live_provider(client):
        _complete_checker_verdict_for_test(
            client,
            workflow_id=workflow_id,
            ticket_id=checker_ticket_id,
            node_id=node_id,
            idempotency_key=f"ticket-result-submit:{workflow_id}:{checker_ticket_id}:backlog-approved",
        )


def _create_and_complete_minimum_governance_chain(
    client,
    *,
    workflow_id: str,
    ticket_prefix: str,
    existing_schema_refs: set[str] | None = None,
) -> None:
    existing = set(existing_schema_refs or set())
    chain = [
        (ARCHITECTURE_BRIEF_SCHEMA_REF, "architecture_brief"),
        (TECHNOLOGY_DECISION_SCHEMA_REF, "technology_decision"),
        (MILESTONE_PLAN_SCHEMA_REF, "milestone_plan"),
        (DETAILED_DESIGN_SCHEMA_REF, "detailed_design"),
    ]
    for schema_ref, suffix in chain:
        if schema_ref in existing:
            continue
        _create_and_complete_governance_ticket(
            client,
            workflow_id=workflow_id,
            ticket_id=f"tkt_{ticket_prefix}_{suffix}",
            node_id=f"node_{ticket_prefix}_{suffix}",
            output_schema_ref=schema_ref,
            summary=f"{schema_ref} is complete.",
        )


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


def test_ceo_shadow_pipeline_failed_raises_without_hidden_fallback(client, monkeypatch):
    _set_deterministic_mode(client)
    workflow_id = _seed_workflow(client, "wf_ceo_shadow_pipeline_error", goal="CEO shadow pipeline failure")
    _set_live_provider(client)

    from app.core import ceo_proposer

    def _fake_invoke(_config, _rendered_payload):
        return OpenAICompatProviderResult(
            output_text="{not-json}",
            response_id="resp_ceo_pipeline_error_1",
        )

    monkeypatch.setattr(ceo_proposer, "invoke_openai_compat_response", _fake_invoke)

    with pytest.raises(CeoShadowPipelineError) as exc_info:
        run_ceo_shadow_for_trigger(
            client.app.state.repository,
            workflow_id=workflow_id,
            trigger_type="MANUAL_TEST",
            trigger_ref="manual:proposal-error",
            runtime_provider_store=client.app.state.runtime_provider_store,
        )

    runs = client.app.state.repository.list_ceo_shadow_runs(workflow_id)

    assert exc_info.value.source_stage == "proposal"
    assert exc_info.value.workflow_id == workflow_id
    assert exc_info.value.trigger_type == "MANUAL_TEST"
    assert exc_info.value.trigger_ref == "manual:proposal-error"
    assert runs[0]["trigger_type"] == "MANUAL_TEST"
    assert runs[0]["fallback_reason"] is not None
    assert runs[0]["deterministic_fallback_used"] is False


def test_trigger_ceo_shadow_with_recovery_opens_ceo_shadow_pipeline_failed_incident(client, monkeypatch):
    _set_deterministic_mode(client)
    workflow_id = _seed_workflow(
        client,
        "wf_ceo_shadow_pipeline_incident",
        goal="CEO shadow helper should open explicit incident.",
    )
    _set_live_provider(client)

    from app.core import ceo_proposer

    def _fake_invoke(_config, _rendered_payload):
        return OpenAICompatProviderResult(
            output_text="{not-json}",
            response_id="resp_ceo_pipeline_incident_1",
        )

    monkeypatch.setattr(ceo_proposer, "invoke_openai_compat_response", _fake_invoke)

    run = trigger_ceo_shadow_with_recovery(
        client.app.state.repository,
        workflow_id=workflow_id,
        trigger_type="MANUAL_TEST",
        trigger_ref="manual:helper-incident",
        runtime_provider_store=client.app.state.runtime_provider_store,
        idempotency_key_base="test-ceo-shadow-helper-incident",
    )

    incidents = [
        item
        for item in client.app.state.repository.list_open_incidents()
        if item["workflow_id"] == workflow_id
    ]

    assert run is None
    assert len(incidents) == 1
    assert incidents[0]["incident_type"] == INCIDENT_TYPE_CEO_SHADOW_PIPELINE_FAILED
    assert incidents[0]["payload"]["trigger_type"] == "MANUAL_TEST"
    assert incidents[0]["payload"]["trigger_ref"] == "manual:helper-incident"
    assert incidents[0]["payload"]["source_stage"] == "proposal"


def test_autopilot_completed_atomic_task_does_not_auto_create_closeout_ticket_before_full_delivery_chain(client):
    _set_deterministic_mode(client)
    workflow_id = _seed_workflow(client, "wf_ceo_autopilot_closeout", goal="Autopilot closeout fallback")
    repository = client.app.state.repository

    _persist_autopilot_workflow_profile(repository, workflow_id)
    _create_and_complete_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_autopilot_impl_done",
        node_id="node_backlog_followup_demo",
        summary="Atomic implementation slice is complete and ready for final closeout.",
    )
    with repository.connection() as connection:
        pending_ticket = next(
            (
                ticket
                for ticket in repository.list_ticket_projections_by_statuses(connection, ["PENDING"])
                if ticket["workflow_id"] == workflow_id
            ),
            None,
        )
        pending_created_spec = (
            repository.get_latest_ticket_created_payload(connection, str(pending_ticket["ticket_id"]))
            if pending_ticket is not None
            else None
        )
    assert pending_created_spec is None or pending_created_spec["output_schema_ref"] != "delivery_closeout_package"


def test_autopilot_governance_only_workflow_does_not_auto_create_closeout_ticket(client, monkeypatch):
    _set_deterministic_mode(client)
    workflow_id = _seed_workflow(client, "wf_ceo_autopilot_governance_only", goal="Autopilot governance only")
    repository = client.app.state.repository

    _persist_autopilot_workflow_profile(repository, workflow_id)
    monkeypatch.setattr("app.core.ticket_handlers._trigger_ceo_shadow_safely", lambda *args, **kwargs: None)
    _create_and_complete_governance_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_autopilot_gov_only",
        node_id="node_ceo_architecture_brief",
        output_schema_ref=ARCHITECTURE_BRIEF_SCHEMA_REF,
        summary="Architecture brief is complete, but delivery has not started.",
    )

    run = run_ceo_shadow_for_trigger(
        repository,
        workflow_id=workflow_id,
        trigger_type="TICKET_COMPLETED",
        trigger_ref="tkt_autopilot_gov_only",
    )

    with repository.connection() as connection:
        closeout_ticket = next(
            (
                ticket
                for ticket in repository.list_ticket_projections_by_statuses(
                    connection,
                    ["PENDING", "LEASED", "EXECUTING", "COMPLETED", "FAILED", "REWORK_REQUIRED"],
                )
                if ticket["workflow_id"] == workflow_id
                and (
                    repository.get_latest_ticket_created_payload(connection, ticket["ticket_id"]) or {}
                ).get("output_schema_ref")
                == "delivery_closeout_package"
            ),
            None,
        )

    assert run["accepted_actions"][0]["action_type"] == "CREATE_TICKET"
    assert run["executed_actions"][0]["action_type"] == "CREATE_TICKET"
    assert closeout_ticket is None
    created_ticket_id = run["executed_actions"][0]["payload"]["ticket_id"]
    with repository.connection() as connection:
        created_spec = repository.get_latest_ticket_created_payload(connection, created_ticket_id)
    assert created_spec["output_schema_ref"] == TECHNOLOGY_DECISION_SCHEMA_REF


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
    assert created_spec["node_id"] == "node_ceo_architecture_brief"
    assert created_spec["role_profile_ref"] == "frontend_engineer_primary"
    assert created_spec["execution_contract"] == {
        "execution_target_ref": "execution_target:frontend_governance_document",
        "required_capability_tags": ["structured_output", "planning"],
        "runtime_contract_version": "execution_contract_v1",
    }
    assert created_spec["dispatch_intent"] == {
        "assignee_employee_id": "emp_frontend_2",
        "selection_reason": "Keep the first governance document on the current live frontend owner.",
        "dependency_gate_refs": [],
        "selected_by": "ceo",
        "wakeup_policy": "default",
    }
    assert created_spec["tenant_id"] == "tenant_default"
    assert created_spec["workspace_id"] == "ws_default"
    assert any(ref.endswith("/board-brief.md") for ref in created_spec["input_artifact_refs"])


def test_ceo_autopilot_project_init_kicks_off_architecture_brief_before_scope_consensus(client):
    _set_deterministic_mode(client)
    response = client.post(
        "/api/v1/commands/project-init",
        json={
            "north_star_goal": "做一个图书馆管理系统毕业设计",
            "hard_constraints": [
                "允许 CEO 代审当前项目。",
                "必须拆成大量原子任务。",
            ],
            "budget_cap": 500000,
            "workflow_profile": "CEO_AUTOPILOT_FINE_GRAINED",
        },
    )

    workflow_id = response.json()["causation_hint"].split(":", 1)[1]
    created_events = [
        event
        for event in client.app.state.repository.list_events_for_testing()
        if event["workflow_id"] == workflow_id and event["event_type"] == "TICKET_CREATED"
    ]

    assert response.status_code == 200
    assert response.json()["status"] == "ACCEPTED"
    assert created_events
    assert created_events[0]["payload"]["output_schema_ref"] == ARCHITECTURE_BRIEF_SCHEMA_REF
    assert created_events[0]["payload"]["node_id"] == "node_ceo_architecture_brief"
    assert any(ref.endswith("/board-brief.md") for ref in created_events[0]["payload"]["input_artifact_refs"])


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


def test_ceo_shadow_snapshot_exposes_projection_snapshot_and_replan_focus(client):
    _set_deterministic_mode(client)
    workflow_id = _seed_workflow(client, "wf_ceo_projection_snapshot")

    snapshot = build_ceo_shadow_snapshot(
        client.app.state.repository,
        workflow_id=workflow_id,
        trigger_type="MANUAL_TEST",
        trigger_ref="manual:projection-snapshot",
    )

    projection_snapshot = snapshot["projection_snapshot"]
    replan_focus = snapshot["replan_focus"]

    assert projection_snapshot["workflow_status"] == "EXECUTING"
    assert projection_snapshot["governance_profile_ref"].startswith("gp_")
    assert projection_snapshot["approval_mode"] == "AUTO_CEO"
    assert projection_snapshot["audit_mode"] == "MINIMAL"
    assert projection_snapshot["reuse_candidates"] == snapshot["reuse_candidates"]
    assert projection_snapshot["memory_budget_ratios"] == {
        "m0_constitution": 10,
        "m1_control_snapshot": 40,
        "m2_replan_focus": 20,
        "m3_process_assets": 20,
        "reserve": 10,
    }
    assert projection_snapshot["default_read_order"] == [
        "projection_snapshot",
        "ticket_graph",
        "open_incidents",
        "open_board_items",
        "board_advisory_sessions",
        "project_map_slices",
        "failure_fingerprints",
        "graph_health_report",
        "recent_asset_digests",
    ]
    assert projection_snapshot["project_map_slices"][0]["workflow_id"] == workflow_id
    assert projection_snapshot["graph_health_report"]["workflow_id"] == workflow_id
    assert projection_snapshot["graph_health_report"]["overall_health"] == "HEALTHY"
    assert replan_focus["failure_fingerprints"] == []
    assert replan_focus["task_sensemaking"] == snapshot["task_sensemaking"]
    assert replan_focus["capability_plan"] == snapshot["capability_plan"]
    assert replan_focus["controller_state"] == snapshot["controller_state"]


def test_ceo_shadow_snapshot_rejects_missing_governance_profile(client):
    repository = client.app.state.repository
    workflow_id = "wf_ceo_missing_governance"
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
                "north_star_goal": "Missing governance snapshot",
                "hard_constraints": ["Keep governance explicit."],
                "budget_cap": 500000,
                "deadline_at": None,
                "title": "Missing governance snapshot",
                "tenant_id": "tenant_default",
                "workspace_id": "ws_default",
            },
            occurred_at=datetime.fromisoformat("2026-04-05T10:00:00+08:00"),
        )
        repository.refresh_projections(connection)

    with pytest.raises(ValueError, match="GovernanceProfile"):
        build_ceo_shadow_snapshot(
            repository,
            workflow_id=workflow_id,
            trigger_type="MANUAL_TEST",
            trigger_ref="manual:missing-governance",
        )


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
    assert completed_ticket["output_schema_ref"] == "source_code_delivery"
    assert completed_ticket["summary"] == "Completed implementation slice ready for reuse."
    assert completed_ticket["artifact_refs"] == ["art://runtime/tkt_ceo_reuse_completed/source-code.tsx"]
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


def test_ceo_shadow_snapshot_excludes_unreviewed_governance_ticket_from_reuse_candidates(client):
    _set_deterministic_mode(client)
    workflow_id = _seed_workflow(client, "wf_ceo_unreviewed_governance")

    _create_and_complete_governance_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_unreviewed_architecture_doc",
        node_id="node_unreviewed_architecture_doc",
        output_schema_ref=ARCHITECTURE_BRIEF_SCHEMA_REF,
        summary="Architecture brief is still waiting for governance checker approval.",
        approve_internal_gate=False,
    )

    snapshot = build_ceo_shadow_snapshot(
        client.app.state.repository,
        workflow_id=workflow_id,
        trigger_type="MANUAL_TEST",
        trigger_ref="manual:unreviewed-governance",
    )

    governance_candidates = [
        item
        for item in snapshot["reuse_candidates"]["recent_completed_tickets"]
        if item["output_schema_ref"] == ARCHITECTURE_BRIEF_SCHEMA_REF
    ]
    assert governance_candidates == []


def test_ceo_shadow_snapshot_excludes_unapproved_consensus_ticket_from_reuse_candidates(client):
    _set_deterministic_mode(client)
    workflow_id = _project_init(client, "Consensus reuse should wait for board approval")

    snapshot = build_ceo_shadow_snapshot(
        client.app.state.repository,
        workflow_id=workflow_id,
        trigger_type="MANUAL_TEST",
        trigger_ref="manual:unapproved-consensus",
    )

    consensus_candidates = [
        item
        for item in snapshot["reuse_candidates"]["recent_completed_tickets"]
        if item["output_schema_ref"] == "consensus_document"
    ]
    assert consensus_candidates == []


def test_ceo_shadow_snapshot_includes_board_approved_consensus_ticket_in_reuse_candidates(client):
    _set_deterministic_mode(client)
    workflow_id = _seed_workflow(client, "wf_ceo_approved_consensus")
    _create_and_board_approve_consensus_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_ceo_board_approved_consensus",
        node_id="node_ceo_board_approved_consensus",
    )

    snapshot = build_ceo_shadow_snapshot(
        client.app.state.repository,
        workflow_id=workflow_id,
        trigger_type="MANUAL_TEST",
        trigger_ref="manual:approved-consensus",
    )

    consensus_candidates = [
        item
        for item in snapshot["reuse_candidates"]["recent_completed_tickets"]
        if item["ticket_id"] == "tkt_ceo_board_approved_consensus"
    ]
    assert len(consensus_candidates) == 1
    assert consensus_candidates[0]["output_schema_ref"] == "consensus_document"


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
    assert "snapshot.projection_snapshot" in system_prompt
    assert "snapshot.replan_focus" in system_prompt

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


def test_ceo_shadow_prefers_role_binding_over_default_provider(client, monkeypatch):
    workflow_id = _project_init(client, "CEO shadow provider binding")
    client.app.state.runtime_provider_store.save_config(
        RuntimeProviderStoredConfig(
            default_provider_id=OPENAI_COMPAT_PROVIDER_ID,
            providers=[
                RuntimeProviderConfigEntry(
                    provider_id=OPENAI_COMPAT_PROVIDER_ID,
                    adapter_kind="openai_compat",
                    label="OpenAI Compat",
                    enabled=True,
                    base_url="https://api.example.test/v1",
                    api_key="sk-test-secret",
                    model="gpt-5.3-codex",
                    timeout_sec=30.0,
                    reasoning_effort="medium",
                ),
                    RuntimeProviderConfigEntry(
                        provider_id=CLAUDE_CODE_PROVIDER_ID,
                        adapter_kind="claude_code_cli",
                        label="Claude Code CLI",
                        enabled=True,
                        command_path="python",
                        model="claude-sonnet-4-6",
                        timeout_sec=30.0,
                    ),
            ],
            role_bindings=[
                RuntimeProviderRoleBinding(
                    target_ref=ROLE_BINDING_CEO_SHADOW,
                    provider_id=CLAUDE_CODE_PROVIDER_ID,
                    model="claude-opus-4-1",
                )
            ],
        )
    )

    from app.core import ceo_proposer

    monkeypatch.setattr(
        ceo_proposer,
        "invoke_openai_compat_response",
        lambda *args, **kwargs: pytest.fail("CEO shadow should not pick OpenAI when ceo_shadow is bound to Claude"),
    )

    def _fake_claude(_config, _rendered_payload):
        return type(
            "ClaudeResult",
            (),
            {
                "output_text": json.dumps(
                    {
                        "summary": "Use Claude for the CEO proposal.",
                        "actions": [
                            {
                                "action_type": "NO_ACTION",
                                "payload": {"reason": "Claude decided the current workflow should wait."},
                            }
                        ],
                    }
                ),
                "response_id": None,
            },
        )()

    monkeypatch.setattr(ceo_proposer, "invoke_claude_code_response", _fake_claude)

    run = run_ceo_shadow_for_trigger(
        client.app.state.repository,
        workflow_id=workflow_id,
        trigger_type="MANUAL_TEST",
        trigger_ref="manual:ceo-binding",
        runtime_provider_store=client.app.state.runtime_provider_store,
    )

    assert run["effective_mode"] == "CLAUDE_CODE_CLI_LIVE"
    assert run["model"] == "claude-opus-4-1"
    assert run["preferred_provider_id"] == CLAUDE_CODE_PROVIDER_ID
    assert run["preferred_model"] == "claude-opus-4-1"
    assert run["actual_provider_id"] == CLAUDE_CODE_PROVIDER_ID
    assert run["actual_model"] == "claude-opus-4-1"
    assert run["selection_reason"] == "role_binding"
    assert run["policy_reason"] is None
    assert run["proposed_action_batch"]["summary"] == "Use Claude for the CEO proposal."


def test_ceo_shadow_system_prompt_prefers_document_chain_before_implementation(client):
    _set_deterministic_mode(client)
    workflow_id = _project_init(client, "CEO governance prompt guidance")

    snapshot = build_ceo_shadow_snapshot(
        client.app.state.repository,
        workflow_id=workflow_id,
        trigger_type="MANUAL_TEST",
        trigger_ref="manual:governance-prompt",
    )
    system_prompt = build_ceo_shadow_system_prompt(snapshot)

    assert "governance document" in system_prompt.lower()
    assert "before directly creating implementation tickets" in system_prompt.lower()
    assert "architect_primary / cto_primary" in system_prompt.lower()
    assert "do not use backend_engineer_primary" in system_prompt.lower()


def test_ceo_shadow_system_prompt_uses_architecture_brief_kickoff_for_autopilot_workflow(client):
    _set_deterministic_mode(client)
    workflow_id = _seed_workflow(client, "wf_autopilot_prompt", "做一个图书馆管理系统毕业设计")
    repository = client.app.state.repository
    with repository.transaction() as connection:
        connection.execute(
            "UPDATE workflow_projection SET workflow_profile = ? WHERE workflow_id = ?",
            ("CEO_AUTOPILOT_FINE_GRAINED", workflow_id),
        )

    snapshot = build_ceo_shadow_snapshot(
        repository,
        workflow_id=workflow_id,
        trigger_type=EVENT_BOARD_DIRECTIVE_RECEIVED,
        trigger_ref=f"project-init:{workflow_id}",
    )
    system_prompt = build_ceo_shadow_system_prompt(snapshot)

    assert snapshot["workflow"]["workflow_profile"] == "CEO_AUTOPILOT_FINE_GRAINED"
    assert "architecture_brief" in system_prompt.lower()
    assert "atomic" in system_prompt.lower()


def test_ceo_shadow_failover_uses_fallback_provider_when_primary_is_unavailable(client, monkeypatch):
    workflow_id = _project_init(client, "CEO shadow provider failover")
    client.app.state.runtime_provider_store.save_config(
        RuntimeProviderStoredConfig(
            default_provider_id=OPENAI_COMPAT_PROVIDER_ID,
            providers=[
                RuntimeProviderConfigEntry(
                    provider_id=OPENAI_COMPAT_PROVIDER_ID,
                    adapter_kind="openai_compat",
                    label="OpenAI Compat",
                    enabled=True,
                    base_url="https://api.example.test/v1",
                    api_key="sk-test-secret",
                    model="gpt-5.3-codex",
                    timeout_sec=30.0,
                    reasoning_effort="medium",
                    capability_tags=["structured_output", "planning"],
                    fallback_provider_ids=[CLAUDE_CODE_PROVIDER_ID],
                ),
                    RuntimeProviderConfigEntry(
                        provider_id=CLAUDE_CODE_PROVIDER_ID,
                        adapter_kind="claude_code_cli",
                        label="Claude Code CLI",
                        enabled=True,
                        command_path="python",
                        model="claude-sonnet-4-6",
                        timeout_sec=30.0,
                        capability_tags=["structured_output", "planning", "implementation", "review"],
                    ),
            ],
            role_bindings=[],
        )
    )

    from app.core import ceo_proposer

    openai_attempts = {"value": 0}

    def _raise_unavailable(*_args, **_kwargs):
        openai_attempts["value"] += 1
        raise OpenAICompatProviderUnavailableError(
            failure_kind="UPSTREAM_UNAVAILABLE",
            message="Provider returned 503.",
            failure_detail={
                "provider_status_code": 503,
                "provider_id": OPENAI_COMPAT_PROVIDER_ID,
            },
        )

    def _fake_claude(_config, _rendered_payload):
        return type(
            "ClaudeResult",
            (),
            {
                "output_text": json.dumps(
                    {
                        "summary": "Claude handled the CEO failover proposal.",
                        "actions": [
                            {
                                "action_type": "NO_ACTION",
                                "payload": {"reason": "Claude fallback says to wait."},
                            }
                        ],
                    }
                ),
                "response_id": None,
            },
        )()

    monkeypatch.setattr(ceo_proposer, "invoke_openai_compat_response", _raise_unavailable)
    monkeypatch.setattr(ceo_proposer, "invoke_claude_code_response", _fake_claude)

    run = run_ceo_shadow_for_trigger(
        client.app.state.repository,
        workflow_id=workflow_id,
        trigger_type="MANUAL_TEST",
        trigger_ref="manual:ceo-failover",
        runtime_provider_store=client.app.state.runtime_provider_store,
    )

    assert openai_attempts["value"] == 1
    assert run["effective_mode"] == "CLAUDE_CODE_CLI_LIVE"
    assert run["deterministic_fallback_used"] is False
    assert run["preferred_provider_id"] == OPENAI_COMPAT_PROVIDER_ID
    assert run["preferred_model"] == "gpt-5.3-codex"
    assert run["actual_provider_id"] == CLAUDE_CODE_PROVIDER_ID
    assert run["actual_model"] == "claude-sonnet-4-6"
    assert run["selection_reason"] == "provider_failover"
    assert run["policy_reason"] is None
    assert run["proposed_action_batch"]["summary"] == "Claude handled the CEO failover proposal."


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


def test_ceo_validator_accepts_seeded_variant_hire_when_live_staffing_seed_is_enabled(
    client,
    monkeypatch,
):
    _set_deterministic_mode(client)
    monkeypatch.setenv("BOARDROOM_OS_CEO_STAFFING_VARIANT_SEED", "17")
    workflow_id = _project_init(client, "CEO validator seeded variant")
    repository = client.app.state.repository
    hire_template = clone_persona_template(get_hire_persona_template_id("frontend_engineer"))

    with repository.transaction() as connection:
        repository.insert_event(
            connection,
            event_type=EVENT_EMPLOYEE_HIRED,
            actor_type="system",
            actor_id="test-seed",
            workflow_id=None,
            idempotency_key="test-seed-employee:emp_frontend_polish_seeded",
            causation_id=None,
            correlation_id=None,
            payload={
                "employee_id": "emp_frontend_polish_seeded",
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
                "summary": "Hire a seeded frontend backup.",
                "actions": [
                    {
                        "action_type": "HIRE_EMPLOYEE",
                        "payload": {
                            "workflow_id": workflow_id,
                            "role_type": "frontend_engineer",
                            "role_profile_refs": ["frontend_engineer_primary"],
                            "request_summary": "Hire another frontend backup with a seeded variant.",
                            "employee_id_hint": "emp_frontend_seeded_variant",
                            "provider_id": "prov_openai_compat",
                        },
                    }
                ],
            }
        ),
    )

    assert result["rejected_actions"] == []
    assert result["accepted_actions"][0]["action_type"] == "HIRE_EMPLOYEE"


@pytest.mark.parametrize(
    ("role_type", "role_profile_refs", "employee_id_hint"),
    [
        ("backend_engineer", ["backend_engineer_primary"], "emp_backend_shadow"),
        ("database_engineer", ["database_engineer_primary"], "emp_database_shadow"),
        ("platform_sre", ["platform_sre_primary"], "emp_platform_shadow"),
        ("governance_architect", ["architect_primary"], "emp_architect_shadow"),
        ("governance_cto", ["cto_primary"], "emp_cto_shadow"),
    ],
)
def test_ceo_validator_accepts_new_role_hires_on_current_ceo_path(
    client,
    role_type,
    role_profile_refs,
    employee_id_hint,
):
    _set_deterministic_mode(client)
    workflow_id = _project_init(client, "CEO limited staffing boundary")
    repository = client.app.state.repository

    result = validate_ceo_action_batch(
        repository,
        action_batch=CEOActionBatch.model_validate(
            {
                "summary": "Hire a backend engineer from the CEO path.",
                "actions": [
                    {
                        "action_type": "HIRE_EMPLOYEE",
                        "payload": {
                            "workflow_id": workflow_id,
                            "role_type": role_type,
                            "role_profile_refs": role_profile_refs,
                            "request_summary": f"Hire {role_type} on the CEO path.",
                            "employee_id_hint": employee_id_hint,
                            "provider_id": "prov_openai_compat",
                        },
                    }
                ],
            }
        ),
    )

    assert result["rejected_actions"] == []
    assert result["accepted_actions"][0]["action_type"] == "HIRE_EMPLOYEE"


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
                                "execution_contract": {
                                    "execution_target_ref": "execution_target:scope_consensus",
                                    "required_capability_tags": ["structured_output", "planning"],
                                    "runtime_contract_version": "execution_contract_v1",
                                },
                                "dispatch_intent": {
                                    "assignee_employee_id": "emp_frontend_2",
                                    "selection_reason": "Use the active frontend delivery owner for the kickoff scope consensus ticket.",
                                },
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
    assert created_spec["execution_contract"]["execution_target_ref"] == "execution_target:scope_consensus"
    assert created_spec["dispatch_intent"]["assignee_employee_id"] == "emp_frontend_2"
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
    workflow_id = _seed_workflow(client, "wf_ceo_create_execution", "CEO limited create execution")
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
                                "output_schema_ref": "source_code_delivery",
                                "execution_contract": {
                                    "execution_target_ref": "execution_target:frontend_build",
                                    "required_capability_tags": ["structured_output", "implementation"],
                                    "runtime_contract_version": "execution_contract_v1",
                                },
                                "dispatch_intent": {
                                    "assignee_employee_id": "emp_frontend_2",
                                    "selection_reason": "Use the active frontend delivery owner for the approved scope build ticket.",
                                },
                                "summary": "Create the source code delivery for the approved scope slice.",
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
    assert created_spec["output_schema_ref"] == "source_code_delivery"
    assert created_spec["role_profile_ref"] == "frontend_engineer_primary"
    assert created_spec["execution_contract"]["execution_target_ref"] == "execution_target:frontend_build"
    assert created_spec["dispatch_intent"]["assignee_employee_id"] == "emp_frontend_2"
    assert created_spec["delivery_stage"] == "BUILD"


def test_ceo_shadow_run_executes_governance_document_create_ticket_for_live_role(client, monkeypatch):
    workflow_id = _seed_workflow(client, "wf_ceo_gov_create_execution", "CEO governance create execution")
    _set_live_provider(client)

    from app.core import ceo_proposer

    def _fake_invoke(_config, _rendered_payload):
        return OpenAICompatProviderResult(
            output_text=json.dumps(
                {
                    "summary": "Create an architecture brief before implementation starts.",
                    "actions": [
                        {
                            "action_type": "CREATE_TICKET",
                            "payload": {
                                "workflow_id": workflow_id,
                                "node_id": "node_ceo_architecture_brief",
                                "role_profile_ref": "frontend_engineer_primary",
                                "output_schema_ref": ARCHITECTURE_BRIEF_SCHEMA_REF,
                                "execution_contract": {
                                    "execution_target_ref": "execution_target:frontend_governance_document",
                                    "required_capability_tags": ["structured_output", "planning"],
                                    "runtime_contract_version": "execution_contract_v1",
                                },
                                "dispatch_intent": {
                                    "assignee_employee_id": "emp_frontend_2",
                                    "selection_reason": "Keep the first governance document on the current live frontend owner.",
                                },
                                "summary": "Write the architecture brief before opening the implementation ticket.",
                                "parent_ticket_id": None,
                            },
                        }
                    ],
                }
            ),
            response_id="resp_ceo_gov_doc_1",
        )

    monkeypatch.setattr(ceo_proposer, "invoke_openai_compat_response", _fake_invoke)

    run = run_ceo_shadow_for_trigger(
        client.app.state.repository,
        workflow_id=workflow_id,
        trigger_type="MANUAL_TEST",
        trigger_ref="manual:gov-doc-create",
        runtime_provider_store=client.app.state.runtime_provider_store,
    )

    assert run["executed_actions"][0]["action_type"] == "CREATE_TICKET"
    assert run["executed_actions"][0]["execution_status"] == "EXECUTED"
    created_ticket_id = run["executed_actions"][0]["payload"]["ticket_id"]
    with client.app.state.repository.connection() as connection:
        created_spec = client.app.state.repository.get_latest_ticket_created_payload(connection, created_ticket_id)
    assert created_spec["output_schema_ref"] == ARCHITECTURE_BRIEF_SCHEMA_REF
    assert created_spec["role_profile_ref"] == "frontend_engineer_primary"
    assert created_spec["execution_contract"]["required_capability_tags"] == [
        "structured_output",
        "planning",
    ]
    assert created_spec["dispatch_intent"]["assignee_employee_id"] == "emp_frontend_2"
    assert created_spec["delivery_stage"] is None


def test_ceo_shadow_run_raises_for_invalid_create_ticket_preset(client, monkeypatch):
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
                                "execution_contract": {
                                    "execution_target_ref": "execution_target:frontend_build",
                                    "required_capability_tags": ["structured_output", "implementation"],
                                    "runtime_contract_version": "execution_contract_v1",
                                },
                                "dispatch_intent": {
                                    "assignee_employee_id": "emp_frontend_2",
                                    "selection_reason": "This invalid preset still carries a concrete assignee.",
                                },
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

    with pytest.raises(CeoShadowPipelineError) as exc_info:
        run_ceo_shadow_for_trigger(
            client.app.state.repository,
            workflow_id=workflow_id,
            trigger_type="MANUAL_TEST",
            trigger_ref="manual:create-invalid",
            runtime_provider_store=client.app.state.runtime_provider_store,
        )

    runs = client.app.state.repository.list_ceo_shadow_runs(workflow_id)

    assert exc_info.value.source_stage == "proposal"
    assert runs[0]["deterministic_fallback_used"] is False
    assert runs[0]["fallback_reason"] is not None


def test_ceo_validator_accepts_governance_document_create_ticket_for_architect_role(client):
    _set_deterministic_mode(client)
    workflow_id = _project_init(client, "CEO invalid governance role")
    _seed_board_approved_employee(
        client,
        employee_id="emp_architect_1",
        role_type="governance_architect",
        role_profile_refs=["architect_primary"],
    )

    result = validate_ceo_action_batch(
        client.app.state.repository,
        action_batch=CEOActionBatch.model_validate(
            {
                "summary": "Allow governance-document tickets on architect role.",
                "actions": [
                    {
                        "action_type": "CREATE_TICKET",
                        "payload": {
                            "workflow_id": workflow_id,
                            "node_id": "node_architect_governance_attempt",
                            "role_profile_ref": "architect_primary",
                            "output_schema_ref": DETAILED_DESIGN_SCHEMA_REF,
                            "execution_contract": {
                                "execution_target_ref": "execution_target:architect_governance_document",
                                "required_capability_tags": ["structured_output", "planning"],
                                "runtime_contract_version": "execution_contract_v1",
                            },
                            "dispatch_intent": {
                                "assignee_employee_id": "emp_architect_1",
                                "selection_reason": "Use the active architect governance role for design detail.",
                            },
                            "summary": "This should succeed because architect_primary can now produce governance documents.",
                            "parent_ticket_id": None,
                        },
                    }
                ],
            }
        ),
    )

    assert result["rejected_actions"] == []
    assert result["accepted_actions"][0]["action_type"] == "CREATE_TICKET"


def test_ceo_shadow_run_executes_governance_document_create_ticket_for_cto_role(client, monkeypatch):
    workflow_id = _seed_workflow(client, "wf_ceo_cto_gov_create_execution", "CEO governance create execution for cto")
    _seed_board_approved_employee(
        client,
        employee_id="emp_cto_1",
        role_type="governance_cto",
        role_profile_refs=["cto_primary"],
    )
    _set_live_provider(client)

    from app.core import ceo_proposer

    def _fake_invoke(_config, _rendered_payload):
        return OpenAICompatProviderResult(
            output_text=json.dumps(
                {
                    "summary": "Create a backlog recommendation with the CTO governance role.",
                    "actions": [
                        {
                            "action_type": "CREATE_TICKET",
                            "payload": {
                                "workflow_id": workflow_id,
                                "node_id": "node_ceo_cto_backlog_recommendation",
                                "role_profile_ref": "cto_primary",
                                "output_schema_ref": BACKLOG_RECOMMENDATION_SCHEMA_REF,
                                "execution_contract": {
                                    "execution_target_ref": "execution_target:cto_governance_document",
                                    "required_capability_tags": ["structured_output", "planning"],
                                    "runtime_contract_version": "execution_contract_v1",
                                },
                                "dispatch_intent": {
                                    "assignee_employee_id": "emp_cto_1",
                                    "selection_reason": "Route the backlog recommendation through the active CTO governance role.",
                                },
                                "summary": "Write the backlog recommendation before implementation fans out.",
                                "parent_ticket_id": None,
                            },
                        }
                    ],
                }
            ),
            response_id="resp_ceo_cto_gov_doc_1",
        )

    monkeypatch.setattr(ceo_proposer, "invoke_openai_compat_response", _fake_invoke)

    run = run_ceo_shadow_for_trigger(
        client.app.state.repository,
        workflow_id=workflow_id,
        trigger_type="MANUAL_TEST",
        trigger_ref="manual:cto-gov-doc-create",
        runtime_provider_store=client.app.state.runtime_provider_store,
    )

    assert run["executed_actions"][0]["action_type"] == "CREATE_TICKET"
    assert run["executed_actions"][0]["execution_status"] == "EXECUTED"
    created_ticket_id = run["executed_actions"][0]["payload"]["ticket_id"]
    with client.app.state.repository.connection() as connection:
        created_spec = client.app.state.repository.get_latest_ticket_created_payload(connection, created_ticket_id)
    assert created_spec["output_schema_ref"] == BACKLOG_RECOMMENDATION_SCHEMA_REF
    assert created_spec["role_profile_ref"] == "cto_primary"
    assert created_spec["execution_contract"]["execution_target_ref"] == "execution_target:cto_governance_document"
    assert created_spec["dispatch_intent"]["assignee_employee_id"] == "emp_cto_1"


def test_ceo_shadow_run_normalizes_loose_governance_followup_create_ticket_from_live_provider(client, monkeypatch):
    workflow_id = _seed_workflow(client, "wf_live_gov_followup", "CEO live governance follow-up normalization")
    _set_live_provider(client)

    from app.core import ceo_proposer

    def _fake_invoke(_config, _rendered_payload):
        return OpenAICompatProviderResult(
            output_text=json.dumps(
                {
                    "summary": "Continue the governance chain after the architecture brief.",
                    "actions": [
                        {
                            "action_type": "CREATE_TICKET",
                            "payload": {
                                "node_id": "node_ceo_technology_decision",
                                "output_schema_ref": TECHNOLOGY_DECISION_SCHEMA_REF,
                                "execution_contract": {
                                    "deliverable": "Produce the technology decision document for the current library system graduation project.",
                                    "acceptance_criteria": [
                                        "明确推荐的系统技术方案与取舍。",
                                        "为后续实现级任务拆分提供依据。",
                                    ],
                                    "constraints": [
                                        "保持细粒度，只推进下一张治理票。",
                                        "避免重复架构定义。",
                                    ],
                                },
                                "dispatch_intent": {
                                    "document_family": "governance",
                                    "document_kind": "technology_decision",
                                    "reason": "已存在可复用的 architecture brief，需要继续补齐技术决策，为后续设计提供依据。",
                                    "preferred_path": "current_live_planning_role",
                                    "fallback_policy": "if no live planning assignee exists, wait instead of creating implementation tickets",
                                },
                                "title": "Create technology decision for the library system graduation project",
                                "priority": "high",
                                "depends_on_ticket_ids": ["tkt_parent_architecture_doc"],
                                "inputs": {
                                    "workflow_goal": "做一个图书馆管理系统毕业设计",
                                    "next_document_kind": "technology_decision",
                                },
                            },
                        }
                    ],
                }
            ),
            response_id="resp_ceo_loose_gov_followup_1",
        )

    monkeypatch.setattr(ceo_proposer, "invoke_openai_compat_response", _fake_invoke)

    _create_and_complete_governance_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_parent_architecture_doc",
        node_id="node_parent_architecture_doc",
        output_schema_ref=ARCHITECTURE_BRIEF_SCHEMA_REF,
        summary="Architecture brief is complete and ready for the next governance document.",
    )

    repository = client.app.state.repository
    runs = repository.list_ceo_shadow_runs(workflow_id)
    run = next(run for run in reversed(runs) if run["executed_actions"])
    assert run["trigger_type"] == "TICKET_COMPLETED"
    assert run["provider_response_id"] == "resp_ceo_loose_gov_followup_1"
    assert run["executed_actions"][0]["action_type"] == "CREATE_TICKET"
    assert run["executed_actions"][0]["execution_status"] == "EXECUTED"

    created_ticket_id = run["executed_actions"][0]["payload"]["ticket_id"]
    with repository.connection() as connection:
        created_spec = repository.get_latest_ticket_created_payload(connection, created_ticket_id)

    assert created_spec["output_schema_ref"] == TECHNOLOGY_DECISION_SCHEMA_REF
    assert created_spec["role_profile_ref"] == "frontend_engineer_primary"
    assert created_spec["execution_contract"]["execution_target_ref"] == "execution_target:frontend_governance_document"
    assert created_spec["dispatch_intent"]["assignee_employee_id"] == "emp_frontend_2"
    assert created_spec["dispatch_intent"]["dependency_gate_refs"] == ["tkt_parent_architecture_doc"]
    assert created_spec["parent_ticket_id"] == "tkt_parent_architecture_doc"


def test_ceo_shadow_run_normalizes_live_governance_followup_with_kind_field_and_invalid_role(client, monkeypatch):
    workflow_id = _seed_workflow(client, "wf_live_gov_kind", "CEO live governance kind normalization")
    _set_live_provider(client)

    from app.core import ceo_proposer

    def _fake_invoke(_config, _rendered_payload):
        return OpenAICompatProviderResult(
            output_text=json.dumps(
                {
                    "summary": "Architecture brief is already completed and reusable. Advance by one minimal governance step in the approved document-first sequence.",
                    "actions": [
                        {
                            "action_type": "CREATE_TICKET",
                            "payload": {
                                "title": "Produce technology decision for the library management system graduation project",
                                "kind": TECHNOLOGY_DECISION_SCHEMA_REF,
                                "priority": "high",
                                "role_profile_ref": "checker_primary",
                                "depends_on_ticket_ids": ["tkt_parent_architecture_doc"],
                                "source_artifact_refs": [
                                    "art://runtime/tkt_parent_architecture_doc/architecture_brief.json"
                                ],
                                "execution_contract": {
                                    "objective": "Create the technology_decision document that selects a practical, low-risk stack for the library management system based on the completed architecture brief.",
                                    "deliverable_schema_ref": TECHNOLOGY_DECISION_SCHEMA_REF,
                                    "must_include": [
                                        "recommended frontend technology",
                                        "recommended backend technology",
                                    ],
                                    "constraints": [
                                        "Use the existing architecture_brief as the primary input",
                                        "Do not start implementation in this ticket",
                                    ],
                                    "definition_of_done": [
                                        "A complete technology_decision artifact is produced"
                                    ],
                                },
                                "dispatch_intent": {
                                    "mode": "governance_document",
                                    "reason": "The workflow has completed architecture_brief and still needs the next governance document in sequence.",
                                    "sequence_position": "architecture_brief -> technology_decision -> milestone_plan -> detailed_design -> backlog_recommendation -> source_code_delivery",
                                },
                            },
                        }
                    ],
                }
            ),
            response_id="resp_ceo_live_kind_1",
        )

    monkeypatch.setattr(ceo_proposer, "invoke_openai_compat_response", _fake_invoke)

    _create_and_complete_governance_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_parent_architecture_doc",
        node_id="node_parent_architecture_doc",
        output_schema_ref=ARCHITECTURE_BRIEF_SCHEMA_REF,
        summary="Architecture brief is complete and ready for the next governance document.",
    )

    repository = client.app.state.repository
    runs = repository.list_ceo_shadow_runs(workflow_id)
    run = next(run for run in reversed(runs) if run["executed_actions"])
    assert run["provider_response_id"] == "resp_ceo_live_kind_1"
    assert run["executed_actions"][0]["action_type"] == "CREATE_TICKET"
    assert run["executed_actions"][0]["execution_status"] == "EXECUTED"

    created_ticket_id = run["executed_actions"][0]["payload"]["ticket_id"]
    with repository.connection() as connection:
        created_spec = repository.get_latest_ticket_created_payload(connection, created_ticket_id)

    assert created_spec["output_schema_ref"] == TECHNOLOGY_DECISION_SCHEMA_REF
    assert created_spec["role_profile_ref"] == "frontend_engineer_primary"
    assert created_spec["execution_contract"]["execution_target_ref"] == "execution_target:frontend_governance_document"
    assert created_spec["dispatch_intent"]["assignee_employee_id"] == "emp_frontend_2"
    assert created_spec["dispatch_intent"]["dependency_gate_refs"] == ["tkt_parent_architecture_doc"]


def test_ceo_shadow_run_normalizes_flat_create_ticket_action_shape_from_live_provider(client, monkeypatch):
    workflow_id = _seed_workflow(client, "wf_live_flat_action", "CEO live flat action normalization")
    _set_live_provider(client)
    monkeypatch.setattr("app.core.ticket_handlers._trigger_ceo_shadow_safely", lambda *args, **kwargs: None)

    from app.core import ceo_proposer
    from app.core.ceo_scheduler import run_ceo_shadow_for_trigger

    def _fake_invoke(_config, _rendered_payload):
        return OpenAICompatProviderResult(
            output_text=json.dumps(
                {
                    "summary": "Continue the governance sequence with a detailed design document.",
                    "actions": [
                        {
                            "action_type": "CREATE_TICKET",
                            "title": "Produce detailed design for the library management system graduation project",
                            "priority": "medium",
                            "node_id": "node_ceo_detailed_design",
                            "role_type": "frontend_engineer_primary",
                            "output_schema_ref": DETAILED_DESIGN_SCHEMA_REF,
                            "depends_on": [
                                "tkt_parent_architecture_doc",
                                "tkt_parent_technology_decision",
                                "tkt_parent_milestone_plan",
                            ],
                            "parent_ticket_id": "tkt_parent_milestone_plan",
                            "execution_contract": {
                                "goal": "Generate a detailed design document for the next implementation stage.",
                                "deliverable_schema_ref": DETAILED_DESIGN_SCHEMA_REF,
                                "constraints": [
                                    "Use completed governance documents as source of truth."
                                ],
                            },
                            "dispatch_intent": {
                                "reason": "Next required document in the explicit governance order is detailed_design.",
                                "prefer_parallel_implementation": True,
                            },
                        }
                    ],
                }
            ),
            response_id="resp_ceo_flat_action_1",
        )

    monkeypatch.setattr(ceo_proposer, "invoke_openai_compat_response", _fake_invoke)

    _create_and_complete_governance_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_parent_architecture_doc",
        node_id="node_parent_architecture_doc",
        output_schema_ref=ARCHITECTURE_BRIEF_SCHEMA_REF,
        summary="Architecture brief is complete.",
    )
    _create_and_complete_governance_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_parent_technology_decision",
        node_id="node_parent_technology_decision",
        output_schema_ref=TECHNOLOGY_DECISION_SCHEMA_REF,
        summary="Technology decision is complete.",
    )
    _create_and_complete_governance_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_parent_milestone_plan",
        node_id="node_parent_milestone_plan",
        output_schema_ref="milestone_plan",
        summary="Milestone plan is complete.",
    )

    repository = client.app.state.repository
    run = run_ceo_shadow_for_trigger(
        repository,
        workflow_id=workflow_id,
        trigger_type="TICKET_COMPLETED",
        trigger_ref="tkt_parent_milestone_plan",
        runtime_provider_store=client.app.state.runtime_provider_store,
    )

    assert run["provider_response_id"] == "resp_ceo_flat_action_1"
    assert run["executed_actions"][0]["action_type"] == "CREATE_TICKET"
    assert run["executed_actions"][0]["execution_status"] == "EXECUTED"

    created_ticket_id = run["executed_actions"][0]["payload"]["ticket_id"]
    with repository.connection() as connection:
        created_spec = repository.get_latest_ticket_created_payload(connection, created_ticket_id)

    assert created_spec["output_schema_ref"] == DETAILED_DESIGN_SCHEMA_REF
    assert created_spec["node_id"] == "node_ceo_detailed_design"
    assert created_spec["role_profile_ref"] == "frontend_engineer_primary"
    assert created_spec["dispatch_intent"]["assignee_employee_id"] == "emp_frontend_2"
    assert created_spec["dispatch_intent"]["dependency_gate_refs"] == [
        "tkt_parent_architecture_doc",
        "tkt_parent_technology_decision",
        "tkt_parent_milestone_plan",
    ]


def test_ceo_shadow_run_normalizes_live_action_type_alias_field(client, monkeypatch):
    workflow_id = _seed_workflow(client, "wf_live_type_alias", "CEO live action type alias normalization")
    _set_live_provider(client)

    from app.core import ceo_proposer

    def _fake_invoke(_config, _rendered_payload):
        return OpenAICompatProviderResult(
            output_text=json.dumps(
                {
                    "summary": "Create the next governance ticket using a loose type field.",
                    "actions": [
                        {
                            "type": "CREATE_TICKET",
                            "payload": {
                                "workflow_id": workflow_id,
                                "node_id": "node_ceo_architecture_brief",
                                "role_profile_ref": "frontend_engineer_primary",
                                "output_schema_ref": ARCHITECTURE_BRIEF_SCHEMA_REF,
                                "summary": "Write the architecture brief with the normalized action type alias.",
                            },
                        }
                    ],
                }
            ),
            response_id="resp_ceo_type_alias_1",
        )

    monkeypatch.setattr(ceo_proposer, "invoke_openai_compat_response", _fake_invoke)

    run = run_ceo_shadow_for_trigger(
        client.app.state.repository,
        workflow_id=workflow_id,
        trigger_type="MANUAL_TEST",
        trigger_ref="manual:type-alias",
        runtime_provider_store=client.app.state.runtime_provider_store,
    )

    assert run["provider_response_id"] == "resp_ceo_type_alias_1"
    assert run["executed_actions"][0]["action_type"] == "CREATE_TICKET"
    assert run["executed_actions"][0]["execution_status"] == "EXECUTED"


def test_ceo_shadow_run_idle_governance_followup_infers_dependency_chain_and_process_assets(client, monkeypatch):
    workflow_id = _seed_workflow(client, "wf_idle_gov_chain", "CEO idle governance chain inference")
    _set_deterministic_mode(client)
    monkeypatch.setattr("app.core.ticket_handlers._trigger_ceo_shadow_safely", lambda *args, **kwargs: None)

    _create_and_complete_governance_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_parent_architecture_doc",
        node_id="node_parent_architecture_doc",
        output_schema_ref=ARCHITECTURE_BRIEF_SCHEMA_REF,
        summary="Architecture brief is complete.",
    )
    _create_and_complete_governance_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_parent_technology_decision",
        node_id="node_parent_technology_decision",
        output_schema_ref=TECHNOLOGY_DECISION_SCHEMA_REF,
        summary="Technology decision is complete.",
    )
    _create_and_complete_governance_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_parent_milestone_plan",
        node_id="node_parent_milestone_plan",
        output_schema_ref="milestone_plan",
        summary="Milestone plan is complete.",
    )
    _create_and_complete_governance_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_parent_detailed_design",
        node_id="node_parent_detailed_design",
        output_schema_ref=DETAILED_DESIGN_SCHEMA_REF,
        summary="Detailed design is complete.",
    )

    _set_live_provider(client)
    from app.core import ceo_proposer

    def _fake_invoke(_config, _rendered_payload):
        return OpenAICompatProviderResult(
            output_text=json.dumps(
                {
                    "summary": "Advance to backlog recommendation using the existing governance chain.",
                    "actions": [
                        {
                            "type": "CREATE_TICKET",
                            "payload": {
                                "workflow_id": workflow_id,
                                "node_id": "node_ceo_backlog_recommendation",
                                "role_profile_ref": "frontend_engineer_primary",
                                "output_schema_ref": BACKLOG_RECOMMENDATION_SCHEMA_REF,
                                "summary": "Create backlog recommendation from the completed governance chain.",
                            },
                        }
                    ],
                }
            ),
            response_id="resp_ceo_idle_gov_chain_1",
        )

    monkeypatch.setattr(ceo_proposer, "invoke_openai_compat_response", _fake_invoke)

    run = run_ceo_shadow_for_trigger(
        client.app.state.repository,
        workflow_id=workflow_id,
        trigger_type=SCHEDULER_IDLE_MAINTENANCE_TRIGGER,
        trigger_ref="scheduler-runner:test-idle-gov-chain",
        runtime_provider_store=client.app.state.runtime_provider_store,
    )

    assert run["provider_response_id"] == "resp_ceo_idle_gov_chain_1"
    assert run["executed_actions"][0]["action_type"] == "CREATE_TICKET"
    created_ticket_id = run["executed_actions"][0]["payload"]["ticket_id"]

    with client.app.state.repository.connection() as connection:
        created_spec = client.app.state.repository.get_latest_ticket_created_payload(connection, created_ticket_id)

    assert created_spec["output_schema_ref"] == BACKLOG_RECOMMENDATION_SCHEMA_REF
    assert created_spec["dispatch_intent"]["dependency_gate_refs"] == [
        "tkt_parent_architecture_doc",
        "tkt_parent_technology_decision",
        "tkt_parent_milestone_plan",
        "tkt_parent_detailed_design",
    ]
    assert created_spec["parent_ticket_id"] == "tkt_parent_detailed_design"
    assert "pa://governance-document/tkt_parent_architecture_doc@1" in created_spec["input_process_asset_refs"]
    assert "pa://governance-document/tkt_parent_technology_decision@1" in created_spec["input_process_asset_refs"]
    assert "pa://governance-document/tkt_parent_milestone_plan@1" in created_spec["input_process_asset_refs"]
    assert "pa://governance-document/tkt_parent_detailed_design@1" in created_spec["input_process_asset_refs"]


def test_ceo_shadow_run_raises_when_live_provider_leaves_backlog_followup_fields_blank(
    client,
    monkeypatch,
):
    workflow_id = _seed_workflow(client, "wf_live_backlog_followup_fallback", "CEO backlog follow-up fallback")
    _persist_workflow_directive_details(
        client.app.state.repository,
        workflow_id,
        workflow_profile="CEO_AUTOPILOT_FINE_GRAINED",
    )
    _seed_board_approved_employee(
        client,
        employee_id="emp_backend_gate",
        role_type="backend_engineer",
        role_profile_refs=["backend_engineer_primary"],
    )
    _seed_board_approved_employee(
        client,
        employee_id="emp_platform_gate",
        role_type="platform_sre",
        role_profile_refs=["platform_sre_primary"],
    )
    _set_live_provider(client)
    monkeypatch.setattr("app.core.ticket_handlers._trigger_ceo_shadow_safely", lambda *args, **kwargs: None)
    _create_and_complete_minimum_governance_chain(
        client,
        workflow_id=workflow_id,
        ticket_prefix="live_backlog_blank",
    )
    _create_and_complete_backlog_recommendation_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_backlog_followup_parent",
        node_id="node_ceo_backlog_recommendation",
        tickets=[
            {
                "ticket_id": "BR-BE-01",
                "name": "借阅后端 API 交付",
                "priority": "P0",
                "target_role": "backend_engineer",
                "scope": ["借阅服务", "REST API"],
            },
            {
                "ticket_id": "BR-OPS-01",
                "name": "发布与监控底座",
                "priority": "P0",
                "target_role": "platform_sre",
                "scope": ["部署流水线", "监控告警"],
            },
        ],
        dependency_graph=[
            {"ticket_id": "BR-BE-01", "depends_on": [], "reason": "后端服务可先行。"},
            {"ticket_id": "BR-OPS-01", "depends_on": [], "reason": "平台底座可并行先行。"},
        ],
        recommended_sequence=[
            "BR-BE-01 借阅后端 API 交付",
            "BR-OPS-01 发布与监控底座",
        ],
    )

    from app.core import ceo_proposer

    def _fake_invoke(_config, _rendered_payload):
        return OpenAICompatProviderResult(
            output_text=json.dumps(
                {
                    "summary": "Fan out implementation work from the completed backlog recommendation.",
                    "actions": [
                        {
                            "action_type": "CREATE_TICKET",
                            "payload": {
                                "workflow_id": workflow_id,
                                "node_id": "",
                                "role_profile_ref": "",
                                "output_schema_ref": "",
                                "summary": "Create the next implementation tickets from backlog.",
                            },
                        }
                    ],
                }
            ),
            response_id="resp_ceo_backlog_blank_1",
        )

    monkeypatch.setattr(ceo_proposer, "invoke_openai_compat_response", _fake_invoke)

    repository = client.app.state.repository
    with pytest.raises(CeoShadowPipelineError) as exc_info:
        run_ceo_shadow_for_trigger(
            repository,
            workflow_id=workflow_id,
            trigger_type="TICKET_COMPLETED",
            trigger_ref="tkt_backlog_followup_parent",
            runtime_provider_store=client.app.state.runtime_provider_store,
        )

    runs = repository.list_ceo_shadow_runs(workflow_id)

    assert exc_info.value.source_stage == "proposal"
    assert runs[0]["deterministic_fallback_used"] is False
    assert runs[0]["fallback_reason"] is not None
    assert runs[0]["accepted_actions"] == []
    assert runs[0]["executed_actions"] == []


def test_ceo_shadow_snapshot_exposes_capability_plan_for_backlog_followups(client, monkeypatch):
    _set_deterministic_mode(client)
    workflow_id = _seed_workflow(client, "wf_backlog_capability_plan", "Capability-driven backlog fanout")
    _persist_workflow_directive_details(
        client.app.state.repository,
        workflow_id,
        workflow_profile="CEO_AUTOPILOT_FINE_GRAINED",
    )
    _seed_board_approved_employee(
        client,
        employee_id="emp_backend_plan",
        role_type="backend_engineer",
        role_profile_refs=["backend_engineer_primary"],
    )
    _seed_board_approved_employee(
        client,
        employee_id="emp_database_plan",
        role_type="database_engineer",
        role_profile_refs=["database_engineer_primary"],
    )
    monkeypatch.setattr("app.core.ticket_handlers._trigger_ceo_shadow_safely", lambda *args, **kwargs: None)
    _create_and_complete_minimum_governance_chain(
        client,
        workflow_id=workflow_id,
        ticket_prefix="capability_plan",
    )
    _create_and_complete_backlog_recommendation_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_backlog_capability_parent",
        node_id="node_ceo_backlog_capability",
        tickets=[
            {
                "ticket_id": "BR-BE-01",
                "name": "借阅后端 API 交付",
                "priority": "P0",
                "target_role": "backend_engineer",
                "scope": ["借阅服务", "REST API"],
            },
            {
                "ticket_id": "BR-DB-01",
                "name": "库存数据库建模",
                "priority": "P0",
                "target_role": "database_engineer",
                "scope": ["数据库 schema", "索引优化"],
            },
        ],
        dependency_graph=[
            {"ticket_id": "BR-BE-01", "depends_on": [], "reason": "后端服务可先行。"},
            {"ticket_id": "BR-DB-01", "depends_on": ["BR-BE-01"], "reason": "数据库结构依赖服务边界。"},
        ],
        recommended_sequence=[
            "BR-BE-01 借阅后端 API 交付",
            "BR-DB-01 库存数据库建模",
        ],
    )

    snapshot = build_ceo_shadow_snapshot(
        client.app.state.repository,
        workflow_id=workflow_id,
        trigger_type="TICKET_COMPLETED",
        trigger_ref="tkt_backlog_capability_parent",
    )

    assert snapshot["task_sensemaking"]["task_type"] == "implementation_fanout"
    assert snapshot["task_sensemaking"]["deliverable_kind"] == "source_code_delivery"
    assert snapshot["controller_state"]["state"] == "READY_FOR_FANOUT"
    assert snapshot["controller_state"]["recommended_action"] == "CREATE_TICKET"
    assert [item["ticket_key"] for item in snapshot["capability_plan"]["followup_ticket_plans"]] == [
        "BR-BE-01",
        "BR-DB-01",
    ]
    assert [item["role_profile_ref"] for item in snapshot["capability_plan"]["followup_ticket_plans"]] == [
        "backend_engineer_primary",
        "database_engineer_primary",
    ]


def test_ceo_shadow_snapshot_exposes_required_governance_ticket_plan_when_architect_doc_missing(
    client,
    monkeypatch,
):
    _set_deterministic_mode(client)
    workflow_id = _seed_workflow(client, "wf_backlog_architect_doc_gap", "Architect governance gap")
    _persist_workflow_directive_details(
        client.app.state.repository,
        workflow_id,
        workflow_profile="CEO_AUTOPILOT_FINE_GRAINED",
        hard_constraints=[
            "CEO 必须真实招聘并真实使用 architect_primary，系统分析职责并入架构治理链。",
        ],
    )
    _seed_board_approved_employee(
        client,
        employee_id="emp_architect_doc_gap",
        role_type="governance_architect",
        role_profile_refs=["architect_primary"],
    )
    _seed_board_approved_employee(
        client,
        employee_id="emp_backend_doc_gap",
        role_type="backend_engineer",
        role_profile_refs=["backend_engineer_primary"],
    )
    monkeypatch.setattr("app.core.ticket_handlers._trigger_ceo_shadow_safely", lambda *args, **kwargs: None)
    _create_and_complete_minimum_governance_chain(
        client,
        workflow_id=workflow_id,
        ticket_prefix="architect_doc_gap",
    )
    _create_and_complete_backlog_recommendation_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_backlog_architect_doc_gap",
        node_id="node_ceo_backlog_architect_doc_gap",
        tickets=[
            {
                "ticket_id": "BR-BE-01",
                "name": "借阅后端 API 交付",
                "priority": "P0",
                "target_role": "backend_engineer",
                "scope": ["借阅服务", "REST API"],
            }
        ],
        dependency_graph=[
            {"ticket_id": "BR-BE-01", "depends_on": [], "reason": "后端服务可先行。"},
        ],
        recommended_sequence=[
            "BR-BE-01 借阅后端 API 交付",
        ],
    )

    snapshot = build_ceo_shadow_snapshot(
        client.app.state.repository,
        workflow_id=workflow_id,
        trigger_type="TICKET_COMPLETED",
        trigger_ref="tkt_backlog_architect_doc_gap",
    )

    required_plan = snapshot["capability_plan"]["required_governance_ticket_plan"]

    assert snapshot["controller_state"]["state"] == "ARCHITECT_REQUIRED"
    assert snapshot["controller_state"]["recommended_action"] == "CREATE_TICKET"
    assert required_plan["node_id"] == "node_architect_governance_gate_node_ceo_backlog_architect_doc_gap"
    assert required_plan["role_profile_ref"] == "architect_primary"
    assert required_plan["output_schema_ref"] == ARCHITECTURE_BRIEF_SCHEMA_REF
    assert required_plan["assignee_employee_id"] == "emp_architect_doc_gap"
    assert required_plan["parent_ticket_id"] == "tkt_backlog_architect_doc_gap"
    assert required_plan["existing_ticket_id"] is None
    assert "architect governance brief" in required_plan["summary"].lower()


@pytest.mark.parametrize("workflow_profile", ["CEO_AUTOPILOT_FINE_GRAINED", "STANDARD"])
def test_ceo_shadow_snapshot_requires_next_governance_document_before_backlog_fanout(
    client,
    monkeypatch,
    workflow_profile,
):
    _set_deterministic_mode(client)
    workflow_id = _seed_workflow(client, "wf_governance_chain_next_doc", "Governance chain next doc")
    _persist_workflow_directive_details(
        client.app.state.repository,
        workflow_id,
        workflow_profile=workflow_profile,
        hard_constraints=["Keep governance explicit."],
    )
    monkeypatch.setattr("app.core.ticket_handlers._trigger_ceo_shadow_safely", lambda *args, **kwargs: None)
    _create_and_complete_governance_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_parent_architecture_doc",
        node_id="node_parent_architecture_doc",
        output_schema_ref=ARCHITECTURE_BRIEF_SCHEMA_REF,
        summary="Architecture brief is complete.",
    )

    snapshot = build_ceo_shadow_snapshot(
        client.app.state.repository,
        workflow_id=workflow_id,
        trigger_type="TICKET_COMPLETED",
        trigger_ref="tkt_parent_architecture_doc",
    )
    required_plan = snapshot["capability_plan"]["required_governance_ticket_plan"]

    assert snapshot["task_sensemaking"]["task_type"] == "governance_followup"
    assert snapshot["task_sensemaking"]["deliverable_kind"] == "structured_document_delivery"
    assert snapshot["task_sensemaking"]["coordination_mode"] == "document_chain"
    assert snapshot["controller_state"]["state"] == "GOVERNANCE_REQUIRED"
    assert snapshot["controller_state"]["recommended_action"] == "CREATE_TICKET"
    assert required_plan["output_schema_ref"] == TECHNOLOGY_DECISION_SCHEMA_REF
    assert required_plan["parent_ticket_id"] == "tkt_parent_architecture_doc"
    assert required_plan["dependency_gate_refs"] == ["tkt_parent_architecture_doc"]


def test_ceo_shadow_snapshot_builds_full_dependency_chain_for_next_governance_document(
    client,
    monkeypatch,
):
    _set_deterministic_mode(client)
    workflow_id = _seed_workflow(client, "wf_governance_chain_detailed_design", "Governance chain detailed design")
    _persist_workflow_directive_details(
        client.app.state.repository,
        workflow_id,
        workflow_profile="CEO_AUTOPILOT_FINE_GRAINED",
        hard_constraints=["Keep governance explicit."],
    )
    monkeypatch.setattr("app.core.ticket_handlers._trigger_ceo_shadow_safely", lambda *args, **kwargs: None)
    _create_and_complete_governance_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_parent_architecture_doc",
        node_id="node_parent_architecture_doc",
        output_schema_ref=ARCHITECTURE_BRIEF_SCHEMA_REF,
        summary="Architecture brief is complete.",
    )
    _create_and_complete_governance_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_parent_technology_decision",
        node_id="node_parent_technology_decision",
        output_schema_ref=TECHNOLOGY_DECISION_SCHEMA_REF,
        summary="Technology decision is complete.",
    )
    _create_and_complete_governance_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_parent_milestone_plan",
        node_id="node_parent_milestone_plan",
        output_schema_ref=MILESTONE_PLAN_SCHEMA_REF,
        summary="Milestone plan is complete.",
    )

    snapshot = build_ceo_shadow_snapshot(
        client.app.state.repository,
        workflow_id=workflow_id,
        trigger_type="TICKET_COMPLETED",
        trigger_ref="tkt_parent_milestone_plan",
    )
    required_plan = snapshot["capability_plan"]["required_governance_ticket_plan"]

    assert snapshot["controller_state"]["state"] == "GOVERNANCE_REQUIRED"
    assert required_plan["output_schema_ref"] == DETAILED_DESIGN_SCHEMA_REF
    assert required_plan["parent_ticket_id"] == "tkt_parent_milestone_plan"
    assert required_plan["dependency_gate_refs"] == [
        "tkt_parent_architecture_doc",
        "tkt_parent_technology_decision",
        "tkt_parent_milestone_plan",
    ]


@pytest.mark.parametrize("workflow_profile", ["CEO_AUTOPILOT_FINE_GRAINED", "STANDARD"])
def test_ceo_validator_rejects_implementation_before_governance_chain_completes(
    client,
    monkeypatch,
    workflow_profile,
):
    _set_deterministic_mode(client)
    workflow_id = _seed_workflow(client, "wf_validate_governance_chain", "Validate governance chain")
    _persist_workflow_directive_details(
        client.app.state.repository,
        workflow_id,
        workflow_profile=workflow_profile,
        hard_constraints=["Keep governance explicit."],
    )
    monkeypatch.setattr("app.core.ticket_handlers._trigger_ceo_shadow_safely", lambda *args, **kwargs: None)
    _create_and_complete_governance_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_parent_architecture_doc",
        node_id="node_parent_architecture_doc",
        output_schema_ref=ARCHITECTURE_BRIEF_SCHEMA_REF,
        summary="Architecture brief is complete.",
    )

    snapshot = build_ceo_shadow_snapshot(
        client.app.state.repository,
        workflow_id=workflow_id,
        trigger_type="TICKET_COMPLETED",
        trigger_ref="tkt_parent_architecture_doc",
    )

    result = validate_ceo_action_batch(
        client.app.state.repository,
        snapshot=snapshot,
        action_batch=CEOActionBatch.model_validate(
            {
                "summary": "Try to skip governance and create implementation directly.",
                "actions": [
                    {
                        "action_type": "CREATE_TICKET",
                        "payload": {
                            "workflow_id": workflow_id,
                            "node_id": "node_impl_direct",
                            "role_profile_ref": "frontend_engineer_primary",
                            "output_schema_ref": "source_code_delivery",
                            "execution_contract": infer_execution_contract_payload(
                                role_profile_ref="frontend_engineer_primary",
                                output_schema_ref="source_code_delivery",
                            ),
                            "dispatch_intent": {
                                "assignee_employee_id": "emp_frontend_2",
                                "selection_reason": "Try to skip the remaining governance chain.",
                            },
                            "summary": "Skip governance and implement directly.",
                            "parent_ticket_id": "tkt_parent_architecture_doc",
                        },
                    }
                ],
            }
        ),
    )

    assert result["accepted_actions"] == []
    assert "required_governance_ticket_plan" in result["rejected_actions"][0]["reason"]


@pytest.mark.parametrize(
    ("approved_schema_ref", "ticket_id", "node_id"),
    [
        (ARCHITECTURE_BRIEF_SCHEMA_REF, "tkt_architect_ready_arch", "node_architect_ready_arch"),
        (TECHNOLOGY_DECISION_SCHEMA_REF, "tkt_architect_ready_td", "node_architect_ready_td"),
        (DETAILED_DESIGN_SCHEMA_REF, "tkt_architect_ready_dd", "node_architect_ready_dd"),
    ],
)
def test_ceo_shadow_snapshot_treats_any_approved_architect_governance_document_as_gate_satisfied(
    client,
    monkeypatch,
    approved_schema_ref,
    ticket_id,
    node_id,
):
    _set_deterministic_mode(client)
    workflow_id = _seed_workflow(client, f"wf_architect_ready_{ticket_id}", "Architect governance ready")
    _persist_workflow_directive_details(
        client.app.state.repository,
        workflow_id,
        workflow_profile="CEO_AUTOPILOT_FINE_GRAINED",
        hard_constraints=[
            "CEO 必须真实招聘并真实使用 architect_primary，系统分析职责并入架构治理链。",
        ],
    )
    _seed_board_approved_employee(
        client,
        employee_id="emp_architect_ready",
        role_type="governance_architect",
        role_profile_refs=["architect_primary"],
    )
    _seed_board_approved_employee(
        client,
        employee_id="emp_backend_ready",
        role_type="backend_engineer",
        role_profile_refs=["backend_engineer_primary"],
    )
    monkeypatch.setattr("app.core.ticket_handlers._trigger_ceo_shadow_safely", lambda *args, **kwargs: None)
    _create_and_complete_governance_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id=ticket_id,
        node_id=node_id,
        output_schema_ref=approved_schema_ref,
        role_profile_ref="architect_primary",
        leased_by="emp_architect_ready",
    )
    _create_and_complete_minimum_governance_chain(
        client,
        workflow_id=workflow_id,
        ticket_prefix=f"architect_ready_{ticket_id}",
        existing_schema_refs={approved_schema_ref},
    )
    _create_and_complete_backlog_recommendation_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_backlog_architect_ready",
        node_id="node_ceo_backlog_architect_ready",
        tickets=[
            {
                "ticket_id": "BR-BE-01",
                "name": "借阅后端 API 交付",
                "priority": "P0",
                "target_role": "backend_engineer",
                "scope": ["借阅服务", "REST API"],
            }
        ],
        dependency_graph=[
            {"ticket_id": "BR-BE-01", "depends_on": [], "reason": "后端服务可先行。"},
        ],
        recommended_sequence=[
            "BR-BE-01 借阅后端 API 交付",
        ],
    )

    snapshot = build_ceo_shadow_snapshot(
        client.app.state.repository,
        workflow_id=workflow_id,
        trigger_type="TICKET_COMPLETED",
        trigger_ref="tkt_backlog_architect_ready",
    )

    assert snapshot["controller_state"]["state"] == "READY_FOR_FANOUT"
    assert snapshot["controller_state"]["recommended_action"] == "CREATE_TICKET"
    assert snapshot["capability_plan"]["required_governance_ticket_plan"] is None


def test_ceo_shadow_run_hires_architect_before_backlog_followup_when_required(client, monkeypatch):
    _set_deterministic_mode(client)
    workflow_id = _seed_workflow(client, "wf_backlog_architect_gate", "Architect gate")
    _persist_workflow_directive_details(
        client.app.state.repository,
        workflow_id,
        workflow_profile="CEO_AUTOPILOT_FINE_GRAINED",
        hard_constraints=[
            "CEO 必须真实招聘并真实使用 architect_primary，系统分析职责并入架构治理链。",
        ],
    )
    monkeypatch.setattr("app.core.ticket_handlers._trigger_ceo_shadow_safely", lambda *args, **kwargs: None)
    _create_and_complete_minimum_governance_chain(
        client,
        workflow_id=workflow_id,
        ticket_prefix="architect_gate",
    )
    _create_and_complete_backlog_recommendation_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_backlog_architect_parent",
        node_id="node_ceo_backlog_architect",
        tickets=[
            {
                "ticket_id": "BR-BE-01",
                "name": "借阅后端 API 交付",
                "priority": "P0",
                "target_role": "backend_engineer",
                "scope": ["借阅服务", "REST API"],
            }
        ],
        dependency_graph=[
            {"ticket_id": "BR-BE-01", "depends_on": [], "reason": "后端服务可先行。"},
        ],
        recommended_sequence=[
            "BR-BE-01 借阅后端 API 交付",
        ],
    )

    run = run_ceo_shadow_for_trigger(
        client.app.state.repository,
        workflow_id=workflow_id,
        trigger_type="TICKET_COMPLETED",
        trigger_ref="tkt_backlog_architect_parent",
    )

    assert run["snapshot"]["controller_state"]["state"] == "ARCHITECT_REQUIRED"
    assert run["snapshot"]["controller_state"]["recommended_action"] == "HIRE_EMPLOYEE"
    assert run["accepted_actions"][0]["action_type"] == "HIRE_EMPLOYEE"
    assert run["executed_actions"][0]["action_type"] == "HIRE_EMPLOYEE"
    assert run["executed_actions"][0]["execution_status"] == "EXECUTED"
    assert run["executed_actions"][0]["payload"]["role_profile_refs"] == ["architect_primary"]


def test_ceo_shadow_run_creates_architect_governance_ticket_before_backlog_followup_when_doc_is_missing(
    client,
    monkeypatch,
):
    _set_deterministic_mode(client)
    workflow_id = _seed_workflow(client, "wf_backlog_architect_doc_ticket", "Architect document ticket")
    _persist_workflow_directive_details(
        client.app.state.repository,
        workflow_id,
        workflow_profile="CEO_AUTOPILOT_FINE_GRAINED",
        hard_constraints=[
            "CEO 必须真实招聘并真实使用 architect_primary，系统分析职责并入架构治理链。",
        ],
    )
    _seed_board_approved_employee(
        client,
        employee_id="emp_architect_doc_ticket",
        role_type="governance_architect",
        role_profile_refs=["architect_primary"],
    )
    _seed_board_approved_employee(
        client,
        employee_id="emp_backend_doc_ticket",
        role_type="backend_engineer",
        role_profile_refs=["backend_engineer_primary"],
    )
    monkeypatch.setattr("app.core.ticket_handlers._trigger_ceo_shadow_safely", lambda *args, **kwargs: None)
    _create_and_complete_minimum_governance_chain(
        client,
        workflow_id=workflow_id,
        ticket_prefix="architect_doc_ticket",
    )
    _create_and_complete_backlog_recommendation_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_backlog_architect_doc_ticket",
        node_id="node_ceo_backlog_architect_doc_ticket",
        tickets=[
            {
                "ticket_id": "BR-BE-01",
                "name": "借阅后端 API 交付",
                "priority": "P0",
                "target_role": "backend_engineer",
                "scope": ["借阅服务", "REST API"],
            }
        ],
        dependency_graph=[
            {"ticket_id": "BR-BE-01", "depends_on": [], "reason": "后端服务可先行。"},
        ],
        recommended_sequence=[
            "BR-BE-01 借阅后端 API 交付",
        ],
    )

    run = run_ceo_shadow_for_trigger(
        client.app.state.repository,
        workflow_id=workflow_id,
        trigger_type="TICKET_COMPLETED",
        trigger_ref="tkt_backlog_architect_doc_ticket",
    )

    assert run["snapshot"]["controller_state"]["state"] == "ARCHITECT_REQUIRED"
    assert run["snapshot"]["controller_state"]["recommended_action"] == "CREATE_TICKET"
    assert run["accepted_actions"][0]["action_type"] == "CREATE_TICKET"
    assert run["executed_actions"][0]["action_type"] == "CREATE_TICKET"
    assert run["executed_actions"][0]["execution_status"] == "EXECUTED"

    created_ticket_id = run["executed_actions"][0]["payload"]["ticket_id"]
    with client.app.state.repository.connection() as connection:
        created_spec = client.app.state.repository.get_latest_ticket_created_payload(connection, created_ticket_id)

    assert created_spec["node_id"] == "node_architect_governance_gate_node_ceo_backlog_architect_doc_ticket"
    assert created_spec["role_profile_ref"] == "architect_primary"
    assert created_spec["output_schema_ref"] == ARCHITECTURE_BRIEF_SCHEMA_REF
    assert created_spec["dispatch_intent"]["assignee_employee_id"] == "emp_architect_doc_ticket"
    assert created_spec["parent_ticket_id"] == "tkt_backlog_architect_doc_ticket"


def test_ceo_shadow_run_requests_meeting_before_backlog_followup_when_required(client, monkeypatch):
    _set_deterministic_mode(client)
    workflow_id = _seed_workflow(client, "wf_backlog_meeting_gate", "Meeting gate")
    _persist_workflow_directive_details(
        client.app.state.repository,
        workflow_id,
        workflow_profile="CEO_AUTOPILOT_FINE_GRAINED",
        hard_constraints=[
            "CEO 必须真实招聘并真实使用 architect_primary，系统分析职责并入架构治理链。",
            "关键实现前必须先通过技术决策会议锁定实现边界。",
        ],
    )
    monkeypatch.setattr("app.core.ticket_handlers._trigger_ceo_shadow_safely", lambda *args, **kwargs: None)
    _seed_board_approved_employee(
        client,
        employee_id="emp_architect_gate",
        role_type="governance_architect",
        role_profile_refs=["architect_primary"],
    )
    _seed_board_approved_employee(
        client,
        employee_id="emp_backend_meeting",
        role_type="backend_engineer",
        role_profile_refs=["backend_engineer_primary"],
    )
    _create_and_complete_governance_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_architect_gate_doc",
        node_id="node_architect_gate_doc",
        output_schema_ref=ARCHITECTURE_BRIEF_SCHEMA_REF,
        role_profile_ref="architect_primary",
        leased_by="emp_architect_gate",
    )
    _create_and_complete_minimum_governance_chain(
        client,
        workflow_id=workflow_id,
        ticket_prefix="meeting_gate",
        existing_schema_refs={ARCHITECTURE_BRIEF_SCHEMA_REF},
    )
    _create_and_complete_backlog_recommendation_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_backlog_meeting_parent",
        node_id="node_ceo_backlog_meeting",
        tickets=[
            {
                "ticket_id": "BR-BE-01",
                "name": "借阅后端 API 交付",
                "priority": "P0",
                "target_role": "backend_engineer",
                "scope": ["借阅服务", "REST API"],
            }
        ],
        dependency_graph=[
            {"ticket_id": "BR-BE-01", "depends_on": [], "reason": "后端服务可先行。"},
        ],
        recommended_sequence=[
            "BR-BE-01 借阅后端 API 交付",
        ],
    )

    run = run_ceo_shadow_for_trigger(
        client.app.state.repository,
        workflow_id=workflow_id,
        trigger_type="TICKET_COMPLETED",
        trigger_ref="tkt_backlog_meeting_parent",
    )

    assert run["snapshot"]["controller_state"]["state"] == "MEETING_REQUIRED"
    assert run["snapshot"]["controller_state"]["recommended_action"] == "REQUEST_MEETING"
    assert any(
        item["source_ticket_id"] == "tkt_backlog_meeting_parent" and item["eligible"] is True
        for item in run["snapshot"]["meeting_candidates"]
    )
    assert run["accepted_actions"][0]["action_type"] == "REQUEST_MEETING"
    assert run["executed_actions"][0]["action_type"] == "REQUEST_MEETING"
    assert run["executed_actions"][0]["execution_status"] == "EXECUTED"




def test_ceo_create_ticket_inherits_parent_governance_process_assets(client):
    _set_deterministic_mode(client)
    workflow_id = _project_init(client, "CEO governance process asset inheritance")
    _create_and_complete_governance_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_parent_governance_doc",
        node_id="node_parent_governance_doc",
    )

    repository = client.app.state.repository
    validation = validate_ceo_action_batch(
        repository,
        action_batch=CEOActionBatch.model_validate(
            {
                "summary": "Create the implementation ticket from the architecture brief.",
                "actions": [
                    {
                        "action_type": "CREATE_TICKET",
                        "payload": {
                            "workflow_id": workflow_id,
                            "node_id": "node_child_implementation_from_doc",
                            "role_profile_ref": "frontend_engineer_primary",
                            "output_schema_ref": "source_code_delivery",
                            "execution_contract": infer_execution_contract_payload(
                                role_profile_ref="frontend_engineer_primary",
                                output_schema_ref="source_code_delivery",
                            ),
                            "dispatch_intent": {
                                "assignee_employee_id": "emp_frontend_2",
                                "selection_reason": "Keep the downstream implementation on the same live owner.",
                            },
                            "summary": "Turn the architecture brief into the next source code delivery.",
                            "parent_ticket_id": "tkt_parent_governance_doc",
                        },
                    }
                ],
            }
        ),
    )

    assert validation["accepted_actions"][0]["action_type"] == "CREATE_TICKET"

    from app.core.ceo_executor import execute_ceo_action_batch

    action_batch = CEOActionBatch.model_validate(
        {
            "summary": "Create the implementation ticket from the architecture brief.",
            "actions": [
                {
                    "action_type": "CREATE_TICKET",
                    "payload": {
                        "workflow_id": workflow_id,
                        "node_id": "node_child_implementation_from_doc",
                        "role_profile_ref": "frontend_engineer_primary",
                        "output_schema_ref": "source_code_delivery",
                        "execution_contract": infer_execution_contract_payload(
                            role_profile_ref="frontend_engineer_primary",
                            output_schema_ref="source_code_delivery",
                        ),
                        "dispatch_intent": {
                            "assignee_employee_id": "emp_frontend_2",
                            "selection_reason": "Keep the downstream implementation on the same live owner.",
                        },
                        "summary": "Turn the architecture brief into the next source code delivery.",
                        "parent_ticket_id": "tkt_parent_governance_doc",
                    },
                }
            ],
        }
    )
    execution_result = execute_ceo_action_batch(
        repository,
        action_batch=action_batch,
        accepted_actions=validation["accepted_actions"],
    )

    assert execution_result["executed_actions"][0]["execution_status"] == "EXECUTED"
    created_ticket_id = execution_result["executed_actions"][0]["payload"]["ticket_id"]
    with repository.connection() as connection:
        created_spec = repository.get_latest_ticket_created_payload(connection, created_ticket_id)
    assert "pa://governance-document/tkt_parent_governance_doc@1" in created_spec["input_process_asset_refs"]


def test_ceo_validator_rejects_create_ticket_when_assignee_is_missing_or_incapable(client):
    _set_deterministic_mode(client)
    workflow_id = _project_init(client, "CEO invalid dispatch intent")

    result = validate_ceo_action_batch(
        client.app.state.repository,
        action_batch=CEOActionBatch.model_validate(
            {
                "summary": "Reject invalid create-ticket dispatch intents.",
                "actions": [
                    {
                        "action_type": "CREATE_TICKET",
                        "payload": {
                            "workflow_id": workflow_id,
                            "node_id": "node_missing_assignee",
                            "role_profile_ref": "frontend_engineer_primary",
                            "output_schema_ref": "source_code_delivery",
                            "execution_contract": {
                                "execution_target_ref": "execution_target:frontend_build",
                                "required_capability_tags": ["structured_output", "implementation"],
                                "runtime_contract_version": "execution_contract_v1",
                            },
                            "dispatch_intent": {
                                "assignee_employee_id": "emp_missing_dispatch",
                                "selection_reason": "Try to dispatch to a missing employee.",
                            },
                            "summary": "This should fail because the assignee does not exist.",
                            "parent_ticket_id": None,
                        },
                    },
                    {
                        "action_type": "CREATE_TICKET",
                        "payload": {
                            "workflow_id": workflow_id,
                            "node_id": "node_checker_assignee",
                            "role_profile_ref": "frontend_engineer_primary",
                            "output_schema_ref": "source_code_delivery",
                            "execution_contract": {
                                "execution_target_ref": "execution_target:frontend_build",
                                "required_capability_tags": ["structured_output", "implementation"],
                                "runtime_contract_version": "execution_contract_v1",
                            },
                            "dispatch_intent": {
                                "assignee_employee_id": "emp_checker_1",
                                "selection_reason": "Try to dispatch a frontend build to the checker.",
                            },
                            "summary": "This should fail because the checker lacks implementation capability.",
                            "parent_ticket_id": None,
                        },
                    },
                ],
            }
        ),
    )

    assert result["accepted_actions"] == []
    assert len(result["rejected_actions"]) == 2
    assert "does not exist" in result["rejected_actions"][0]["reason"].lower()
    assert "required capability tags" in result["rejected_actions"][1]["reason"].lower()


def test_ceo_validator_accepts_required_architect_governance_ticket_plan_and_rejects_other_create_ticket(
    client,
    monkeypatch,
):
    _set_deterministic_mode(client)
    workflow_id = _seed_workflow(client, "wf_validate_architect_gate_doc", "Validate architect governance gate")
    _persist_workflow_directive_details(
        client.app.state.repository,
        workflow_id,
        workflow_profile="CEO_AUTOPILOT_FINE_GRAINED",
        hard_constraints=[
            "CEO 必须真实招聘并真实使用 architect_primary，系统分析职责并入架构治理链。",
        ],
    )
    _seed_board_approved_employee(
        client,
        employee_id="emp_architect_validate",
        role_type="governance_architect",
        role_profile_refs=["architect_primary"],
    )
    _seed_board_approved_employee(
        client,
        employee_id="emp_backend_validate",
        role_type="backend_engineer",
        role_profile_refs=["backend_engineer_primary"],
    )
    monkeypatch.setattr("app.core.ticket_handlers._trigger_ceo_shadow_safely", lambda *args, **kwargs: None)
    _create_and_complete_backlog_recommendation_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_backlog_validate_architect_doc",
        node_id="node_ceo_backlog_validate_architect_doc",
        tickets=[
            {
                "ticket_id": "BR-BE-01",
                "name": "借阅后端 API 交付",
                "priority": "P0",
                "target_role": "backend_engineer",
                "scope": ["借阅服务", "REST API"],
            }
        ],
        dependency_graph=[
            {"ticket_id": "BR-BE-01", "depends_on": [], "reason": "后端服务可先行。"},
        ],
        recommended_sequence=[
            "BR-BE-01 借阅后端 API 交付",
        ],
    )
    snapshot = build_ceo_shadow_snapshot(
        client.app.state.repository,
        workflow_id=workflow_id,
        trigger_type="TICKET_COMPLETED",
        trigger_ref="tkt_backlog_validate_architect_doc",
    )
    required_plan = snapshot["capability_plan"]["required_governance_ticket_plan"]

    rejected_result = validate_ceo_action_batch(
        client.app.state.repository,
        snapshot=snapshot,
        action_batch=CEOActionBatch.model_validate(
            {
                "summary": "Try to bypass the architect governance gate.",
                "actions": [
                    {
                        "action_type": "CREATE_TICKET",
                        "payload": {
                            "workflow_id": workflow_id,
                            "node_id": "node_backlog_followup_br_be_01",
                            "role_profile_ref": "backend_engineer_primary",
                            "output_schema_ref": "source_code_delivery",
                            "execution_contract": infer_execution_contract_payload(
                                role_profile_ref="backend_engineer_primary",
                                output_schema_ref="source_code_delivery",
                            ),
                            "dispatch_intent": {
                                "assignee_employee_id": "emp_backend_validate",
                                "selection_reason": "Try to force implementation before the architect document exists.",
                            },
                            "summary": "Bypass the architect gate with an implementation ticket.",
                            "parent_ticket_id": "tkt_backlog_validate_architect_doc",
                        },
                    }
                ],
            }
        ),
    )
    assert rejected_result["accepted_actions"] == []
    assert "required_governance_ticket_plan" in rejected_result["rejected_actions"][0]["reason"]

    accepted_result = validate_ceo_action_batch(
        client.app.state.repository,
        snapshot=snapshot,
        action_batch=CEOActionBatch.model_validate(
            {
                "summary": "Create the required architect governance document.",
                "actions": [
                    {
                        "action_type": "CREATE_TICKET",
                        "payload": {
                            "workflow_id": workflow_id,
                            "node_id": required_plan["node_id"],
                            "role_profile_ref": required_plan["role_profile_ref"],
                            "output_schema_ref": required_plan["output_schema_ref"],
                            "execution_contract": infer_execution_contract_payload(
                                role_profile_ref=required_plan["role_profile_ref"],
                                output_schema_ref=required_plan["output_schema_ref"],
                            ),
                            "dispatch_intent": {
                                "assignee_employee_id": required_plan["assignee_employee_id"],
                                "selection_reason": "Follow the required architect governance ticket plan exactly.",
                            },
                            "summary": required_plan["summary"],
                            "parent_ticket_id": required_plan["parent_ticket_id"],
                        },
                    }
                ],
            }
        ),
    )
    assert len(accepted_result["accepted_actions"]) == 1
    assert accepted_result["accepted_actions"][0]["action_type"] == "CREATE_TICKET"
    assert accepted_result["rejected_actions"] == []


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


def test_ceo_shadow_run_raises_execution_failure_without_hidden_fallback(client, monkeypatch):
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

    with pytest.raises(CeoShadowPipelineError) as exc_info:
        run_ceo_shadow_for_trigger(
            client.app.state.repository,
            workflow_id=workflow_id,
            trigger_type="MANUAL_TEST",
            trigger_ref="manual:retry-fail",
            runtime_provider_store=client.app.state.runtime_provider_store,
        )

    runs = client.app.state.repository.list_ceo_shadow_runs(workflow_id)

    assert exc_info.value.source_stage == "execution"
    assert runs[0]["deterministic_fallback_used"] is False
    assert runs[0]["fallback_reason"] is not None
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


def test_ticket_fail_records_explicit_ceo_shadow_error_without_hidden_meeting_fallback(client):
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

    assert ticket_fail_run["effective_mode"] == "SHADOW_ERROR"
    assert ticket_fail_run["accepted_actions"] == []
    assert ticket_fail_run["executed_actions"] == []
    assert ticket_fail_run["fallback_reason"] is not None


def test_ceo_shadow_snapshot_includes_failed_governance_ticket_meeting_candidate(client):
    _set_deterministic_mode(client)
    workflow_id = _seed_workflow(client, "wf_ceo_governance_meeting_candidate")
    _seed_board_approved_employee(
        client,
        employee_id="emp_architect_1",
        role_type="governance_architect",
        role_profile_refs=["architect_primary"],
    )
    _create_and_fail_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_ceo_architect_meeting_candidate",
        node_id="node_ceo_architect_meeting_candidate",
        retry_budget=0,
        role_profile_ref="architect_primary",
        output_schema_ref=ARCHITECTURE_BRIEF_SCHEMA_REF,
        leased_by="emp_architect_1",
    )

    snapshot = next(
        run["snapshot"]
        for run in client.app.state.repository.list_ceo_shadow_runs(workflow_id)
        if run["trigger_type"] == "TICKET_FAILED"
    )

    candidate = next(
        item
        for item in snapshot["meeting_candidates"]
        if item["source_ticket_id"] == "tkt_ceo_architect_meeting_candidate"
    )

    assert candidate["eligible"] is True
    assert candidate["participant_employee_ids"] == ["emp_architect_1", "emp_checker_1"]
    assert candidate["recorder_employee_id"] == "emp_architect_1"


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
    _set_live_provider(client)

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

    lease_response = _assert_command_status(
        client.post(
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
    )
    start_response = _assert_command_status(
        client.post(
            "/api/v1/commands/ticket-start",
            json={
                "workflow_id": workflow_id,
                "ticket_id": checker_ticket_id,
                "node_id": meeting["source_node_id"],
                "started_by": "emp_checker_1",
                "idempotency_key": f"ticket-start:{workflow_id}:{checker_ticket_id}:checker",
            },
        )
    )
    submit_response = _assert_command_status(
        client.post(
            "/api/v1/commands/ticket-result-submit",
            json=api_test_helpers._maker_checker_result_submit_payload(
                workflow_id=workflow_id,
                ticket_id=checker_ticket_id,
                node_id=meeting["source_node_id"],
                idempotency_key=f"ticket-result-submit:{workflow_id}:{checker_ticket_id}:approved",
            ),
        )
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

    assert lease_response["status"] == "ACCEPTED"
    assert start_response["status"] == "ACCEPTED"
    assert submit_response["status"] == "ACCEPTED"
    assert reject_response.status_code == 200
    assert approval["approval_type"] == "MEETING_ESCALATION"
    assert approval_run["trigger_ref"] == approval["approval_id"]
    assert all(item["action_type"] != "REQUEST_MEETING" for item in approval_run["accepted_actions"])
    assert all(item["action_type"] != "REQUEST_MEETING" for item in approval_run["executed_actions"])
    assert any(
        event["event_type"] == EVENT_BOARD_REVIEW_REJECTED
        for event in client.app.state.repository.list_events_for_testing()
        if (event.get("payload") or {}).get("approval_id") == approval["approval_id"]
    )


def test_board_approve_triggers_ceo_shadow_projection_route(client):
    _set_deterministic_mode(client)
    workflow_id = _seed_workflow(client, "wf_ceo_projection_route", "CEO shadow approval trigger")
    _create_and_board_approve_consensus_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_ceo_projection_consensus",
        node_id="node_ceo_projection_consensus",
    )

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


def test_ceo_shadow_snapshot_exposes_latest_board_advisory_decision(client):
    workflow_id = "wf_ceo_advisory_snapshot"
    _seed_workflow(client, workflow_id, "CEO advisory snapshot")
    approval = api_test_helpers._seed_review_request(client, workflow_id=workflow_id)

    with api_test_helpers._suppress_ceo_shadow_side_effects():
        modify_response = client.post(
            "/api/v1/commands/modify-constraints",
            json={
                "review_pack_id": approval["review_pack_id"],
                "review_pack_version": approval["review_pack_version"],
                "command_target_version": approval["command_target_version"],
                "approval_id": approval["approval_id"],
                "constraint_patch": {
                    "add_rules": ["Hold execution until the advisory decision is reflected in the next run."],
                    "remove_rules": [],
                    "replace_rules": [],
                },
                "governance_patch": {
                    "approval_mode": "EXPERT_GATED",
                    "audit_mode": "TICKET_TRACE",
                },
                "board_comment": "Route the next pass through the tighter advisory decision.",
                "idempotency_key": f"modify-constraints:{approval['approval_id']}:snapshot",
            },
        )
    assert modify_response.status_code == 200
    assert modify_response.json()["status"] == "ACCEPTED"
    advisory_session = client.app.state.repository.get_board_advisory_session_for_approval(approval["approval_id"])
    assert advisory_session is not None

    analysis_response = client.post(
        "/api/v1/commands/board-advisory-request-analysis",
        json={
            "session_id": advisory_session["session_id"],
            "idempotency_key": f"board-advisory-analysis:{advisory_session['session_id']}:snapshot",
        },
    )
    assert analysis_response.status_code == 200
    assert analysis_response.json()["status"] == "ACCEPTED"

    advisory_session = client.app.state.repository.get_board_advisory_session_for_approval(approval["approval_id"])
    assert advisory_session is not None
    apply_response = client.post(
        "/api/v1/commands/board-advisory-apply-patch",
        json={
            "session_id": advisory_session["session_id"],
            "proposal_ref": advisory_session["latest_patch_proposal_ref"],
            "idempotency_key": f"board-advisory-apply:{advisory_session['session_id']}:snapshot",
        },
    )
    assert apply_response.status_code == 200
    assert apply_response.json()["status"] == "ACCEPTED"

    snapshot = build_ceo_shadow_snapshot(
        client.app.state.repository,
        workflow_id=workflow_id,
        trigger_type="APPROVAL_RESOLVED",
        trigger_ref=approval["approval_id"],
    )

    board_advisory_sessions = snapshot["projection_snapshot"]["board_advisory_sessions"]
    latest_advisory_decision = snapshot["replan_focus"]["latest_advisory_decision"]

    assert len(board_advisory_sessions) == 1
    assert board_advisory_sessions[0]["approval_id"] == approval["approval_id"]
    assert board_advisory_sessions[0]["status"] == "APPLIED"
    assert board_advisory_sessions[0]["change_flow_status"] == "APPLIED"
    assert board_advisory_sessions[0]["approved_patch_ref"] is not None
    assert board_advisory_sessions[0]["patched_graph_version"] == snapshot["projection_snapshot"]["graph_version"]
    assert latest_advisory_decision["approval_id"] == approval["approval_id"]
    assert latest_advisory_decision["governance_patch"] == {
        "approval_mode": "EXPERT_GATED",
        "audit_mode": "TICKET_TRACE",
    }
    assert latest_advisory_decision["constraint_patch"]["add_rules"] == [
        "Hold execution until the advisory decision is reflected in the next run."
    ]


def test_ceo_shadow_prompt_mentions_latest_board_advisory_decision(client):
    workflow_id = "wf_ceo_advisory_prompt"
    _seed_workflow(client, workflow_id, "CEO advisory prompt")
    approval = api_test_helpers._seed_review_request(client, workflow_id=workflow_id)

    with api_test_helpers._suppress_ceo_shadow_side_effects():
        modify_response = client.post(
            "/api/v1/commands/modify-constraints",
            json={
                "review_pack_id": approval["review_pack_id"],
                "review_pack_version": approval["review_pack_version"],
                "command_target_version": approval["command_target_version"],
                "approval_id": approval["approval_id"],
                "constraint_patch": {
                    "add_rules": ["Escalate the next step to expert approval."],
                    "remove_rules": [],
                    "replace_rules": [],
                },
                "governance_patch": {
                    "approval_mode": "EXPERT_GATED",
                },
                "board_comment": "Treat this advisory decision as the new execution baseline.",
                "idempotency_key": f"modify-constraints:{approval['approval_id']}:prompt",
            },
        )
    assert modify_response.status_code == 200
    assert modify_response.json()["status"] == "ACCEPTED"
    advisory_session = client.app.state.repository.get_board_advisory_session_for_approval(approval["approval_id"])
    assert advisory_session is not None

    analysis_response = client.post(
        "/api/v1/commands/board-advisory-request-analysis",
        json={
            "session_id": advisory_session["session_id"],
            "idempotency_key": f"board-advisory-analysis:{advisory_session['session_id']}:prompt",
        },
    )
    assert analysis_response.status_code == 200
    assert analysis_response.json()["status"] == "ACCEPTED"

    advisory_session = client.app.state.repository.get_board_advisory_session_for_approval(approval["approval_id"])
    assert advisory_session is not None
    apply_response = client.post(
        "/api/v1/commands/board-advisory-apply-patch",
        json={
            "session_id": advisory_session["session_id"],
            "proposal_ref": advisory_session["latest_patch_proposal_ref"],
            "idempotency_key": f"board-advisory-apply:{advisory_session['session_id']}:prompt",
        },
    )
    assert apply_response.status_code == 200
    assert apply_response.json()["status"] == "ACCEPTED"

    snapshot = build_ceo_shadow_snapshot(
        client.app.state.repository,
        workflow_id=workflow_id,
        trigger_type="APPROVAL_RESOLVED",
        trigger_ref=approval["approval_id"],
    )
    prompt = build_ceo_shadow_system_prompt(snapshot)

    assert "latest_advisory_decision" in prompt
    assert "board_advisory_sessions" in prompt
    assert "Treat this advisory decision as the new execution baseline." in prompt


def test_ceo_shadow_snapshot_exposes_full_timeline_archive_refs_for_applied_advisory_session(client):
    workflow_id = "wf_ceo_advisory_timeline_refs"
    _seed_workflow(client, workflow_id, "CEO advisory timeline refs")
    approval = api_test_helpers._seed_review_request(client, workflow_id=workflow_id)

    with api_test_helpers._suppress_ceo_shadow_side_effects():
        modify_response = client.post(
            "/api/v1/commands/modify-constraints",
            json={
                "review_pack_id": approval["review_pack_id"],
                "review_pack_version": approval["review_pack_version"],
                "command_target_version": approval["command_target_version"],
                "approval_id": approval["approval_id"],
                "constraint_patch": {
                    "add_rules": ["Persist a full advisory transcript before the next run."],
                    "remove_rules": [],
                    "replace_rules": [],
                },
                "governance_patch": {
                    "approval_mode": "EXPERT_GATED",
                    "audit_mode": "FULL_TIMELINE",
                },
                "board_comment": "Carry the archive refs into the CEO snapshot.",
                "idempotency_key": f"modify-constraints:{approval['approval_id']}:timeline-refs",
            },
        )
    assert modify_response.status_code == 200
    assert modify_response.json()["status"] == "ACCEPTED"
    advisory_session = client.app.state.repository.get_board_advisory_session_for_approval(approval["approval_id"])
    assert advisory_session is not None

    analysis_response = client.post(
        "/api/v1/commands/board-advisory-request-analysis",
        json={
            "session_id": advisory_session["session_id"],
            "idempotency_key": f"board-advisory-analysis:{advisory_session['session_id']}:timeline-refs",
        },
    )
    assert analysis_response.status_code == 200
    assert analysis_response.json()["status"] == "ACCEPTED"

    advisory_session = client.app.state.repository.get_board_advisory_session_for_approval(approval["approval_id"])
    assert advisory_session is not None
    apply_response = client.post(
        "/api/v1/commands/board-advisory-apply-patch",
        json={
            "session_id": advisory_session["session_id"],
            "proposal_ref": advisory_session["latest_patch_proposal_ref"],
            "idempotency_key": f"board-advisory-apply:{advisory_session['session_id']}:timeline-refs",
        },
    )
    assert apply_response.status_code == 200
    assert apply_response.json()["status"] == "ACCEPTED"

    snapshot = build_ceo_shadow_snapshot(
        client.app.state.repository,
        workflow_id=workflow_id,
        trigger_type="APPROVAL_RESOLVED",
        trigger_ref=approval["approval_id"],
    )

    board_advisory_sessions = snapshot["projection_snapshot"]["board_advisory_sessions"]
    latest_advisory_decision = snapshot["replan_focus"]["latest_advisory_decision"]

    assert len(board_advisory_sessions) == 1
    assert board_advisory_sessions[0]["timeline_archive_version_int"] == 4
    assert board_advisory_sessions[0]["latest_timeline_index_ref"] == (
        f"pa://timeline-index/{board_advisory_sessions[0]['session_id']}@4"
    )
    assert board_advisory_sessions[0]["latest_transcript_archive_artifact_ref"] == (
        f"art://board-advisory/{workflow_id}/{board_advisory_sessions[0]['session_id']}/transcript-v4.json"
    )
    assert latest_advisory_decision is not None
    assert latest_advisory_decision["timeline_archive_version_int"] == 4
    assert latest_advisory_decision["latest_timeline_index_ref"] == (
        f"pa://timeline-index/{board_advisory_sessions[0]['session_id']}@4"
    )


def test_ceo_shadow_prompt_mentions_project_map_and_graph_health(client):
    workflow_id = "wf_ceo_graph_health_prompt"
    _seed_workflow(client, workflow_id, "CEO project map prompt")

    snapshot = build_ceo_shadow_snapshot(
        client.app.state.repository,
        workflow_id=workflow_id,
        trigger_type="MANUAL_TEST",
        trigger_ref="manual:project-map-and-graph-health",
    )
    prompt = build_ceo_shadow_system_prompt(snapshot)

    assert "project_map_slices" in prompt
    assert "failure_fingerprints" in prompt
    assert "graph_health_report" in prompt


def test_ceo_shadow_snapshot_exposes_graph_thrashing_finding(client):
    workflow_id = "wf_ceo_graph_health_thrashing"
    _seed_workflow(client, workflow_id, "CEO graph thrashing prompt")
    api_test_helpers._seed_created_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_ceo_graph_health_thrashing",
        node_id="node_ceo_graph_health_thrashing",
        role_profile_ref="frontend_engineer_primary",
        output_schema_ref="source_code_delivery",
        delivery_stage="BUILD",
    )
    repository = client.app.state.repository
    with repository.transaction() as connection:
        for patch_index in range(1, 5):
            repository.insert_event(
                connection,
                event_type="GRAPH_PATCH_APPLIED",
                actor_type="board",
                actor_id="test-seed",
                workflow_id=workflow_id,
                idempotency_key=f"graph-patch-applied:{workflow_id}:{patch_index}",
                causation_id=None,
                correlation_id=workflow_id,
                payload={
                    "patch_ref": f"pa://graph-patch/{workflow_id}@{patch_index}",
                    "workflow_id": workflow_id,
                    "session_id": f"adv_ceo_graph_patch_{patch_index}",
                    "proposal_ref": f"pa://graph-patch-proposal/{workflow_id}@{patch_index}",
                    "base_graph_version": f"gv_{patch_index}",
                    "freeze_node_ids": ["node_ceo_graph_health_thrashing"],
                    "unfreeze_node_ids": [],
                    "focus_node_ids": ["node_ceo_graph_health_thrashing"],
                    "reason_summary": "Seed repeated graph patch churn for CEO snapshot coverage.",
                    "patch_hash": f"hash-ceo-graph-health-{patch_index}",
                },
                occurred_at=datetime.fromisoformat(f"2026-04-16T20:1{patch_index}:00+08:00"),
            )
        repository.refresh_projections(connection)

    snapshot = build_ceo_shadow_snapshot(
        repository,
        workflow_id=workflow_id,
        trigger_type="MANUAL_TEST",
        trigger_ref="manual:ceo-graph-health-thrashing",
    )
    prompt = build_ceo_shadow_system_prompt(snapshot)
    finding_types = [
        item["finding_type"] for item in snapshot["projection_snapshot"]["graph_health_report"]["findings"]
    ]

    assert "GRAPH_THRASHING" in finding_types
    assert "GRAPH_THRASHING" in prompt


def test_is_ticket_graph_unavailable_error_recognizes_graph_health_unavailable_error():
    assert hasattr(graph_health_module, "GraphHealthUnavailableError")
    error = graph_health_module.GraphHealthUnavailableError(
        "graph unavailable: malformed graph health timeline"
    )

    assert is_ticket_graph_unavailable_error(error) is True


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
    current_time = datetime.fromisoformat("2026-04-04T10:01:05+08:00")

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


def test_idle_ceo_maintenance_targets_workflow_with_only_completed_tickets(client, set_ticket_time):
    set_ticket_time("2026-04-04T10:00:00+08:00")
    _set_deterministic_mode(client)
    workflow_id = _seed_workflow(client, "wf_completed_only", goal="CEO idle maintenance completed tickets")

    _create_and_complete_governance_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_completed_architecture",
        node_id="node_completed_architecture",
        output_schema_ref=ARCHITECTURE_BRIEF_SCHEMA_REF,
    )
    _create_and_complete_governance_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_completed_technology",
        node_id="node_completed_technology",
        output_schema_ref=TECHNOLOGY_DECISION_SCHEMA_REF,
    )

    repository = client.app.state.repository
    snapshot = build_ceo_shadow_snapshot(
        repository,
        workflow_id=workflow_id,
        trigger_type=SCHEDULER_IDLE_MAINTENANCE_TRIGGER,
        trigger_ref="scheduler-runner:test-completed-only",
    )
    due_workflow_ids = {
        item["workflow_id"]
        for item in list_due_ceo_maintenance_workflows(
            repository,
            current_time=datetime.fromisoformat("2026-04-04T10:01:05+08:00"),
            interval_sec=60,
        )
    }

    assert snapshot["ticket_summary"]["completed_count"] == 4
    assert snapshot["ticket_summary"]["working_count"] == 0
    assert "NO_TICKET_STARTED" in snapshot["idle_maintenance"]["signal_types"]
    assert workflow_id not in due_workflow_ids


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


def test_idle_ceo_maintenance_waits_for_recent_state_change_cooldown(client, monkeypatch, set_ticket_time):
    set_ticket_time("2026-04-04T10:00:00+08:00")
    _set_deterministic_mode(client)
    monkeypatch.setattr(
        client.app.state.repository,
        "list_scheduler_worker_candidates",
        lambda connection=None: [],
    )
    workflow_id = _project_init(client, "CEO idle maintenance cooldown")
    repository = client.app.state.repository

    due_workflow_ids = {
        item["workflow_id"]
        for item in list_due_ceo_maintenance_workflows(
            repository,
            current_time=datetime.fromisoformat("2026-04-04T10:00:30+08:00"),
            interval_sec=60,
        )
    }

    assert workflow_id not in due_workflow_ids
