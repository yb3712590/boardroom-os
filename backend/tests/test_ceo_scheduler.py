from __future__ import annotations

import json
from datetime import datetime
from unittest.mock import patch

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
from app.core.ceo_prompts import CEO_SHADOW_PROMPT_VERSION, build_ceo_shadow_system_prompt
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
    EVENT_INCIDENT_CLOSED,
    EVENT_INCIDENT_OPENED,
    EVENT_TICKET_FAILED,
    EVENT_TICKET_TIMED_OUT,
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


def _seed_closed_persistent_failure_zone_incidents(
    repository,
    workflow_id: str,
    node_id: str,
    *,
    ticket_id_prefix: str = "tkt_persistent_failure",
) -> None:
    with repository.transaction() as connection:
        for index in range(3):
            incident_id = f"inc_{workflow_id}_{index}"
            opened_at = datetime.fromisoformat(f"2026-04-15T20:4{index}:00+08:00")
            repository.insert_event(
                connection,
                event_type=EVENT_INCIDENT_OPENED,
                actor_type="system",
                actor_id="test-seed",
                workflow_id=workflow_id,
                idempotency_key=f"incident-opened:{workflow_id}:{incident_id}",
                causation_id=None,
                correlation_id=workflow_id,
                payload={
                    "incident_id": incident_id,
                    "node_id": node_id,
                    "ticket_id": f"{ticket_id_prefix}_{index}",
                    "incident_type": "REPEATED_FAILURE_ESCALATION",
                    "status": "OPEN",
                    "severity": "high",
                    "fingerprint": f"{workflow_id}:{node_id}:repeat-failure:{index}",
                    "latest_failure_fingerprint": f"repeat-failure:{index}",
                },
                occurred_at=opened_at,
            )
            repository.insert_event(
                connection,
                event_type=EVENT_INCIDENT_CLOSED,
                actor_type="system",
                actor_id="test-seed",
                workflow_id=workflow_id,
                idempotency_key=f"incident-closed:{workflow_id}:{incident_id}",
                causation_id=None,
                correlation_id=workflow_id,
                payload={
                    "incident_id": incident_id,
                    "node_id": node_id,
                    "ticket_id": f"{ticket_id_prefix}_{index}",
                    "incident_type": "REPEATED_FAILURE_ESCALATION",
                    "status": "CLOSED",
                    "severity": "high",
                    "fingerprint": f"{workflow_id}:{node_id}:repeat-failure:{index}",
                    "close_reason": "Seed closed historical failure for graph health gate coverage.",
                },
                occurred_at=opened_at.replace(minute=opened_at.minute + 1),
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
    parent_ticket_id: str | None = None,
    retry_budget: int = 0,
    role_profile_ref: str = "frontend_engineer_primary",
    output_schema_ref: str = "ui_milestone_review",
) -> dict:
    return {
        "ticket_id": ticket_id,
        "workflow_id": workflow_id,
        "node_id": node_id,
        "parent_ticket_id": parent_ticket_id,
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
        "execution_contract": infer_execution_contract_payload(
            role_profile_ref=role_profile_ref,
            output_schema_ref=output_schema_ref,
        ),
        "allowed_tools": ["read_artifact", "write_artifact"],
        "allowed_write_set": ["artifacts/ui/homepage/*"],
        "retry_budget": retry_budget,
        "priority": "high",
        "timeout_sla_sec": 1800,
        "deadline_at": None,
        "graph_contract": {
            "lane_kind": "execution",
        },
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


def _seed_failed_ticket_projection_for_existing_node(
    client,
    *,
    workflow_id: str,
    ticket_id: str,
    node_id: str,
    parent_ticket_id: str | None = None,
    failure_kind: str = "WORKSPACE_HOOK_VALIDATION_ERROR",
    updated_at: str = "2026-04-25T10:45:00+08:00",
) -> None:
    repository = client.app.state.repository
    ticket_payload = _ticket_create_payload(
        workflow_id=workflow_id,
        ticket_id=ticket_id,
        node_id=node_id,
        parent_ticket_id=parent_ticket_id,
        retry_budget=0,
        role_profile_ref="frontend_engineer_primary",
        output_schema_ref="source_code_delivery",
    )
    with repository.transaction() as connection:
        repository.insert_event(
            connection,
            event_type="TICKET_CREATED",
            actor_type="system",
            actor_id="test-seed",
            workflow_id=workflow_id,
            idempotency_key=f"test-seed-ticket-created:{workflow_id}:{ticket_id}",
            causation_id=None,
            correlation_id=workflow_id,
            payload=ticket_payload,
            occurred_at=datetime.fromisoformat(updated_at),
        )
        repository.refresh_projections(connection)
        connection.execute(
            """
            UPDATE ticket_projection
            SET status = ?,
                last_failure_kind = ?,
                last_failure_message = ?,
                updated_at = ?
            WHERE ticket_id = ?
            """,
            (
                "FAILED",
                failure_kind,
                "Synthetic failed retry after a completed attempt.",
                updated_at,
                ticket_id,
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
    extra_written_artifacts: list[dict] | None = None,
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
    normalized_tickets = []
    for raw_ticket in (
        tickets
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
    ):
        ticket_shape = dict(raw_ticket)
        ticket_id_value = str(ticket_shape.get("ticket_id") or "").strip()
        ticket_name = str(ticket_shape.get("name") or ticket_id_value).strip() or ticket_id_value
        ticket_shape["ticket_id"] = ticket_id_value
        ticket_shape["name"] = ticket_name
        ticket_shape["summary"] = (
            str(ticket_shape.get("summary") or f"交付{ticket_name}。").strip() or ticket_name
        )
        ticket_shape["scope"] = [
            str(item).strip()
            for item in list(ticket_shape.get("scope") or [])
            if str(item).strip()
        ]
        ticket_shape["target_role"] = (
            str(ticket_shape.get("target_role") or "frontend_engineer").strip()
            or "frontend_engineer"
        )
        normalized_tickets.append(ticket_shape)

    normalized_dependency_graph = [
        {
            **dict(raw_dependency),
            "ticket_id": str(raw_dependency.get("ticket_id") or "").strip(),
            "depends_on": [
                str(item).strip()
                for item in list(raw_dependency.get("depends_on") or [])
                if str(item).strip()
            ],
        }
        for raw_dependency in (
            dependency_graph
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
            ]
        )
    ]
    normalized_recommended_sequence = [
        str(item).strip().split(" ", 1)[0]
        for item in (
            recommended_sequence
            or [
                "BR-T02 主布局与通用组件底座",
                "BR-T01 登录能力交付",
                "BR-T03 首页仪表盘交付",
            ]
        )
        if str(item).strip()
    ]
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
            },
            {
                "section_id": "dependency_and_sequence_plan",
                "label": "依赖关系与实施顺序",
                "summary": "先底座，再登录，再仪表盘。",
                "content_markdown": "BR-T02 和 BR-T01 先行，BR-T03 依赖 BR-T02。",
            },
        ],
        "implementation_handoff": {
            "tickets": normalized_tickets,
            "dependency_graph": normalized_dependency_graph,
            "recommended_sequence": normalized_recommended_sequence,
        },
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
                    *(
                        extra_written_artifacts
                        or []
                    ),
                    {
                        "path": f"reports/governance/{ticket_id}/{BACKLOG_RECOMMENDATION_SCHEMA_REF}.json",
                        "artifact_ref": artifact_ref,
                        "kind": "JSON",
                        "content_json": backlog_payload,
                    },
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
    source_graph_node_id: str,
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
            source_graph_node_id=source_graph_node_id,
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
        if source_node_id != source_graph_node_id:
            repository.update_meeting_projection(
                connection,
                meeting_id,
                source_node_id=source_node_id,
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
    _set_live_provider(client)
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

    from app.core import ceo_proposer

    def _fake_invoke(_config, rendered_payload):
        snapshot = rendered_payload.messages[2].content_payload
        required_plan = snapshot["capability_plan"]["required_governance_ticket_plan"]
        assert required_plan is not None
        ticket_payload = required_plan["ticket_payload"]
        return OpenAICompatProviderResult(
            output_text=json.dumps(
                {
                    "summary": "Create the next governance document before any delivery closeout work starts.",
                    "actions": [
                        {
                            "action_type": "CREATE_TICKET",
                            "payload": ticket_payload,
                        }
                    ],
                }
            ),
            response_id="resp_ceo_gov_only_1",
        )

    monkeypatch.setattr(ceo_proposer, "invoke_openai_compat_response", _fake_invoke)

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


def test_autopilot_closeout_batch_ignores_stale_closeout_node_projection_without_closeout_ticket(
    client,
    monkeypatch,
):
    _set_deterministic_mode(client)
    workflow_id = _seed_workflow(
        client,
        "wf_closeout_batch_stale_node_projection",
        goal="Closeout fallback should ignore stale legacy node projection",
    )
    repository = client.app.state.repository
    with repository.transaction() as connection:
        connection.execute(
            """
            INSERT INTO node_projection (
                workflow_id,
                node_id,
                latest_ticket_id,
                status,
                blocking_reason_code,
                updated_at,
                version
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                workflow_id,
                "node_ceo_delivery_closeout",
                "tkt_stale_closeout_shadow",
                "PENDING",
                None,
                "2026-04-17T18:00:00+08:00",
                1,
            ),
        )

    from app.core import ceo_proposer

    monkeypatch.setattr(ceo_proposer, "_workflow_has_existing_closeout_ticket", lambda *args, **kwargs: False)
    monkeypatch.setattr(
        ceo_proposer,
        "_resolve_autopilot_closeout_parent_ticket_id",
        lambda *args, **kwargs: "tkt_delivery_parent",
    )
    monkeypatch.setattr(ceo_proposer, "_select_default_assignee", lambda *args, **kwargs: "emp_frontend_2")

    batch = ceo_proposer._build_autopilot_closeout_batch(
        repository,
        {
            "workflow": {
                "workflow_id": workflow_id,
                "workflow_profile": "CEO_AUTOPILOT_FINE_GRAINED",
                "north_star_goal": "Close out the workflow cleanly.",
            },
            "approvals": [],
            "incidents": [],
            "ticket_summary": {"active_count": 0},
            "nodes": [{"status": "COMPLETED"}],
        },
        "Closeout fallback should still create the final package.",
    )

    assert batch is not None
    payload = batch.model_dump(mode="json")["actions"][0]["payload"]
    assert payload["node_id"] == "node_ceo_delivery_closeout"
    assert payload["parent_ticket_id"] == "tkt_delivery_parent"
    assert payload["dispatch_intent"]["assignee_employee_id"] == "emp_frontend_2"


def test_project_init_records_board_directive_shadow_and_hires_architect_when_missing(client):
    _set_deterministic_mode(client)
    workflow_id = _project_init(client, "CEO kickoff deterministic fallback blocked")
    repository = client.app.state.repository

    runs = repository.list_ceo_shadow_runs(workflow_id)
    scope_ticket_id = build_project_init_scope_ticket_id(workflow_id)
    scope_ticket = repository.get_current_ticket_projection(scope_ticket_id)
    with repository.connection() as connection:
        created_spec = repository.get_latest_ticket_created_payload(connection, scope_ticket_id)

    assert any(run["trigger_type"] == EVENT_BOARD_DIRECTIVE_RECEIVED for run in runs)
    open_incidents = [
        incident
        for incident in repository.list_open_incidents()
        if incident["workflow_id"] == workflow_id
    ]

    assert any(run["trigger_type"] == EVENT_BOARD_DIRECTIVE_RECEIVED for run in runs)
    assert runs[0]["accepted_actions"][0]["action_type"] == "HIRE_EMPLOYEE"
    assert runs[0]["executed_actions"][0]["action_type"] == "HIRE_EMPLOYEE"
    assert scope_ticket is None
    assert created_spec is None
    assert open_incidents == []
    hired_employee = repository.get_employee_projection("emp_architect_governance")
    assert hired_employee is not None
    assert hired_employee["state"] == "ACTIVE"
    assert hired_employee["board_approved"] is True


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
    incidents = [
        incident
        for incident in client.app.state.repository.list_open_incidents()
        if incident["workflow_id"] == workflow_id
    ]
    runs = client.app.state.repository.list_ceo_shadow_runs(workflow_id)

    assert response.status_code == 200
    assert response.json()["status"] == "ACCEPTED"
    assert created_events == []
    assert incidents == []
    assert runs[0]["accepted_actions"][0]["action_type"] == "HIRE_EMPLOYEE"
    assert runs[0]["executed_actions"][0]["action_type"] == "HIRE_EMPLOYEE"
    hired_employee = client.app.state.repository.get_employee_projection("emp_architect_governance")
    assert hired_employee is not None
    assert hired_employee["state"] == "ACTIVE"


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
        "runtime_liveness_report",
        "recent_asset_digests",
    ]
    assert projection_snapshot["project_map_slices"][0]["workflow_id"] == workflow_id
    assert projection_snapshot["graph_health_report"]["workflow_id"] == workflow_id
    assert projection_snapshot["graph_health_report"]["overall_health"] == "HEALTHY"
    assert projection_snapshot["runtime_liveness_report"]["workflow_id"] == workflow_id
    assert projection_snapshot["runtime_liveness_report"]["overall_health"] == "HEALTHY"
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
    assert candidate["source_graph_node_id"] == "node_ceo_meeting_candidate"
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
        source_graph_node_id="node_ceo_reuse_completed",
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
    assert closed_meeting["source_graph_node_id"] == "node_ceo_reuse_completed"
    assert closed_meeting["source_node_id"] == "node_ceo_reuse_completed"
    assert closed_meeting["topic"] == "Reuse the existing governance decision"
    assert closed_meeting["consensus_summary"] == "Meeting already resolved the technical trade-off."
    assert closed_meeting["review_status"] == "APPROVED"
    assert closed_meeting["closed_at"] is not None


def test_ceo_shadow_snapshot_derives_closed_meeting_source_node_id_from_graph_subject(client):
    _set_deterministic_mode(client)
    workflow_id = _seed_workflow(client, "wf_ceo_reuse_closed_meeting_graph_mirror")
    _create_and_complete_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_ceo_reuse_graph_mirror",
        node_id="node_ceo_reuse_graph_mirror",
        summary="Completed implementation slice ready for graph-first meeting reuse.",
    )
    _seed_closed_meeting(
        client,
        workflow_id=workflow_id,
        meeting_id="mtg_ceo_reuse_graph_mirror",
        source_ticket_id="tkt_ceo_reuse_graph_mirror",
        source_graph_node_id="node_ceo_reuse_graph_mirror",
        source_node_id="node_stale_legacy_reuse_mirror",
    )
    repository = client.app.state.repository
    with repository.transaction() as connection:
        repository.update_meeting_projection(
            connection,
            "mtg_ceo_reuse_graph_mirror",
            source_node_id="node_stale_legacy_reuse_mirror",
        )

    snapshot = build_ceo_shadow_snapshot(
        repository,
        workflow_id=workflow_id,
        trigger_type="MANUAL_TEST",
        trigger_ref="manual:reuse-graph-mirror",
    )

    closed_meeting = next(
        item
        for item in snapshot["reuse_candidates"]["recent_closed_meetings"]
        if item["meeting_id"] == "mtg_ceo_reuse_graph_mirror"
    )

    assert closed_meeting["source_graph_node_id"] == "node_ceo_reuse_graph_mirror"
    assert closed_meeting["source_node_id"] == "node_ceo_reuse_graph_mirror"


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


def test_ceo_shadow_snapshot_reuse_candidates_ignore_stale_node_projection_for_approved_consensus(client):
    _set_deterministic_mode(client)
    workflow_id = _seed_workflow(client, "wf_ceo_approved_consensus_stale_node_projection")
    _create_and_board_approve_consensus_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_ceo_board_approved_consensus_stale",
        node_id="node_ceo_board_approved_consensus_stale",
    )
    repository = client.app.state.repository
    with repository.transaction() as connection:
        connection.execute(
            """
            DELETE FROM node_projection
            WHERE workflow_id = ? AND node_id = ?
            """,
            (workflow_id, "node_ceo_board_approved_consensus_stale"),
        )

    snapshot = build_ceo_shadow_snapshot(
        repository,
        workflow_id=workflow_id,
        trigger_type="MANUAL_TEST",
        trigger_ref="manual:approved-consensus-stale-node",
    )

    consensus_candidates = [
        item
        for item in snapshot["reuse_candidates"]["recent_completed_tickets"]
        if item["ticket_id"] == "tkt_ceo_board_approved_consensus_stale"
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
        source_graph_node_id="node_ceo_live_reuse_completed",
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
            output_text='{"bad":"shape"}'
            + json.dumps(
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
            selected_payload={
                "summary": "Reuse candidates already cover this workflow state, so no new action is needed.",
                "actions": [
                    {
                        "action_type": "NO_ACTION",
                        "payload": {
                            "reason": "Recent completed tickets and closed meetings already provide reusable guidance.",
                        },
                    }
                ],
            },
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
    assert result["rejected_actions"][0]["details"] == {
        "reason_code": "ROLE_ALREADY_COVERED",
        "reuse_candidate_employee_id": "emp_frontend_polish",
        "role_type": "frontend_engineer",
        "role_profile_refs": ["frontend_engineer_primary"],
    }


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


def test_ceo_validator_rejects_hire_overlap_when_employee_hint_differs_from_reuse_candidate(client):
    _set_deterministic_mode(client)
    workflow_id = _project_init(client, "CEO validator CTO reuse")
    _seed_board_approved_employee(
        client,
        employee_id="emp_custom_cto_governance",
        role_type="governance_cto",
        role_profile_refs=["cto_primary"],
    )

    result = validate_ceo_action_batch(
        client.app.state.repository,
        action_batch=CEOActionBatch.model_validate(
            {
                "summary": "Hire a second CTO governance role.",
                "actions": [
                    {
                        "action_type": "HIRE_EMPLOYEE",
                        "payload": {
                            "workflow_id": workflow_id,
                            "role_type": "governance_cto",
                            "role_profile_refs": ["cto_primary"],
                            "request_summary": "Hire another CTO governance worker.",
                            "employee_id_hint": "emp_cto_shadow",
                            "provider_id": "prov_openai_compat",
                        },
                    }
                ],
            }
        ),
    )

    assert result["accepted_actions"] == []
    assert result["rejected_actions"][0]["action_type"] == "HIRE_EMPLOYEE"
    assert result["rejected_actions"][0]["details"] == {
        "reason_code": "ROLE_ALREADY_COVERED",
        "reuse_candidate_employee_id": "emp_custom_cto_governance",
        "role_type": "governance_cto",
        "role_profile_refs": ["cto_primary"],
    }


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


def test_ceo_hire_execution_prefers_runtime_default_provider_over_template(client):
    custom_provider_id = "prov_openai_compat_truerealbill"
    client.app.state.runtime_provider_store.save_config(
        RuntimeProviderStoredConfig(
            default_provider_id=custom_provider_id,
            providers=[
                RuntimeProviderConfigEntry(
                    provider_id=custom_provider_id,
                    adapter_kind="openai_compat",
                    label="Truerealbill Compat",
                    enabled=True,
                    base_url="http://codex.truerealbill.com:11234/v1",
                    api_key="sk-test-secret",
                    model="gpt-5.4",
                    timeout_sec=30.0,
                    reasoning_effort="high",
                )
            ],
            role_bindings=[],
        )
    )
    workflow_id = _project_init(client, "CEO custom provider hire")
    repository = client.app.state.repository
    action_batch = CEOActionBatch.model_validate(
        {
            "summary": "Hire one architect with runtime default provider.",
            "actions": [
                {
                    "action_type": "HIRE_EMPLOYEE",
                    "payload": {
                        "workflow_id": workflow_id,
                        "role_type": "governance_architect",
                        "role_profile_refs": ["architect_primary"],
                        "request_summary": "Hire one architect before governance kickoff starts.",
                        "employee_id_hint": "emp_architect_governance",
                    },
                }
            ],
        }
    )
    validation = validate_ceo_action_batch(repository, action_batch=action_batch)

    from app.core.ceo_executor import execute_ceo_action_batch

    execute_ceo_action_batch(
        repository,
        action_batch=action_batch,
        accepted_actions=validation["accepted_actions"],
    )

    hired_employee = repository.get_employee_projection("emp_architect_governance")
    assert hired_employee is not None
    assert hired_employee["provider_id"] == custom_provider_id


def test_project_init_can_use_live_provider_to_hire_architect_before_kickoff(client, monkeypatch):
    _set_live_provider(client)
    monkeypatch.setattr("app.core.command_handlers._auto_advance_project_init_to_first_review", lambda *args, **kwargs: None)

    from app.core import ceo_proposer

    def _fake_invoke(_config, rendered_payload):
        snapshot = rendered_payload.messages[2].content_payload
        workflow_id = snapshot["workflow"]["workflow_id"]
        return OpenAICompatProviderResult(
            output_text=json.dumps(
                {
                    "summary": "Hire one architect before governance kickoff starts.",
                    "actions": [
                        {
                            "action_type": "HIRE_EMPLOYEE",
                            "payload": {
                                "workflow_id": workflow_id,
                                "role_type": "governance_architect",
                                "role_profile_refs": ["architect_primary"],
                                "request_summary": "Hire one architect before governance kickoff starts.",
                                "employee_id_hint": "emp_architect_governance",
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

    assert created_spec is None
    hired_employee = repository.get_employee_projection("emp_architect_governance")
    assert hired_employee is not None
    assert hired_employee["state"] == "ACTIVE"
    assert hired_employee["board_approved"] is True
    assert hired_employee["provider_id"] == OPENAI_COMPAT_PROVIDER_ID
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
    assert run["executed_actions"][0]["causation_hint"] == "employee:emp_checker_shadow"
    assert run["execution_summary"]["executed_action_count"] == 1
    assert run["deterministic_fallback_used"] is False
    assert not any(
        approval["approval_type"] == "CORE_HIRE_APPROVAL"
        for approval in client.app.state.repository.list_open_approvals()
        if approval["workflow_id"] == workflow_id
    )
    hired_employee = client.app.state.repository.get_employee_projection("emp_checker_shadow")
    assert hired_employee is not None
    assert hired_employee["state"] == "ACTIVE"
    assert hired_employee["board_approved"] is True


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


def test_ceo_shadow_run_rejects_invalid_create_ticket_preset_without_pipeline_failure(client, monkeypatch):
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

    run = run_ceo_shadow_for_trigger(
        client.app.state.repository,
        workflow_id=workflow_id,
        trigger_type="MANUAL_TEST",
        trigger_ref="manual:create-invalid",
        runtime_provider_store=client.app.state.runtime_provider_store,
    )

    assert run["provider_response_id"] == "resp_ceo_create_invalid_1"
    assert run["fallback_reason"] is None
    assert run["accepted_actions"] == []
    assert run["executed_actions"] == []
    assert run["rejected_actions"][0]["action_type"] == "CREATE_TICKET"
    assert "current limited CEO execution path" in run["rejected_actions"][0]["reason"]


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


def test_ceo_shadow_run_rejects_flat_create_ticket_action_shape_from_live_provider(client, monkeypatch):
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
    with pytest.raises(CeoShadowPipelineError) as exc_info:
        run_ceo_shadow_for_trigger(
            repository,
            workflow_id=workflow_id,
            trigger_type="TICKET_COMPLETED",
            trigger_ref="tkt_parent_milestone_plan",
            runtime_provider_store=client.app.state.runtime_provider_store,
        )

    runs = repository.list_ceo_shadow_runs(workflow_id)

    assert exc_info.value.source_stage == "proposal"
    assert runs[0]["provider_response_id"] == "resp_ceo_flat_action_1"
    assert runs[0]["deterministic_fallback_used"] is False
    assert runs[0]["accepted_actions"] == []
    assert runs[0]["executed_actions"] == []


def test_ceo_shadow_run_rejects_live_action_type_alias_field(client, monkeypatch):
    workflow_id = _seed_workflow(client, "wf_live_type_alias", "CEO live action type alias rejection")
    _set_live_provider(client)

    from app.core import ceo_proposer

    def _fake_invoke(_config, _rendered_payload):
        return OpenAICompatProviderResult(
            output_text=json.dumps(
                {
                    "summary": "Legacy action_type alias should be rejected.",
                    "actions": [
                        {
                            "type": "CREATE_TICKET",
                            "payload": {
                                "workflow_id": workflow_id,
                                "node_id": "node_ceo_architecture_brief",
                                "role_profile_ref": "frontend_engineer_primary",
                                "output_schema_ref": ARCHITECTURE_BRIEF_SCHEMA_REF,
                                "execution_contract": infer_execution_contract_payload(
                                    role_profile_ref="frontend_engineer_primary",
                                    output_schema_ref=ARCHITECTURE_BRIEF_SCHEMA_REF,
                                ),
                                "dispatch_intent": {
                                    "assignee_employee_id": "emp_frontend_2",
                                    "selection_reason": "Keep the first governance document on the current live frontend owner.",
                                    "dependency_gate_refs": [],
                                },
                                "summary": "Write the architecture brief with the legacy action type alias.",
                                "parent_ticket_id": None,
                            },
                        }
                    ],
                }
            ),
            response_id="resp_ceo_type_alias_1",
        )

    monkeypatch.setattr(ceo_proposer, "invoke_openai_compat_response", _fake_invoke)

    repository = client.app.state.repository
    with pytest.raises(CeoShadowPipelineError) as exc_info:
        run_ceo_shadow_for_trigger(
            repository,
            workflow_id=workflow_id,
            trigger_type="MANUAL_TEST",
            trigger_ref="manual:type-alias",
            runtime_provider_store=client.app.state.runtime_provider_store,
        )

    runs = repository.list_ceo_shadow_runs(workflow_id)
    assert exc_info.value.source_stage == "proposal"
    assert runs[0]["provider_response_id"] == "resp_ceo_type_alias_1"
    assert runs[0]["accepted_actions"] == []
    assert runs[0]["executed_actions"] == []


def test_ceo_shadow_run_rejects_governance_dependency_chain_when_action_type_uses_alias_field(
    client,
    monkeypatch,
):
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
                    "summary": "Legacy action_type alias should be rejected even when the payload is otherwise valid.",
                    "actions": [
                        {
                            "type": "CREATE_TICKET",
                            "payload": {
                                "workflow_id": workflow_id,
                                "node_id": "node_ceo_backlog_recommendation",
                                "role_profile_ref": "frontend_engineer_primary",
                                "output_schema_ref": BACKLOG_RECOMMENDATION_SCHEMA_REF,
                                "execution_contract": infer_execution_contract_payload(
                                    role_profile_ref="frontend_engineer_primary",
                                    output_schema_ref=BACKLOG_RECOMMENDATION_SCHEMA_REF,
                                ),
                                "dispatch_intent": {
                                    "assignee_employee_id": "emp_frontend_2",
                                    "selection_reason": "Advance to the next governance document with the explicit dependency chain.",
                                    "dependency_gate_refs": [
                                        "tkt_parent_architecture_doc",
                                        "tkt_parent_technology_decision",
                                        "tkt_parent_milestone_plan",
                                        "tkt_parent_detailed_design",
                                    ],
                                },
                                "summary": "Create backlog recommendation from the completed governance chain.",
                                "parent_ticket_id": "tkt_parent_detailed_design",
                            },
                        }
                    ],
                }
            ),
            response_id="resp_ceo_idle_gov_chain_1",
        )

    monkeypatch.setattr(ceo_proposer, "invoke_openai_compat_response", _fake_invoke)

    repository = client.app.state.repository
    with pytest.raises(CeoShadowPipelineError) as exc_info:
        run_ceo_shadow_for_trigger(
            repository,
            workflow_id=workflow_id,
            trigger_type=SCHEDULER_IDLE_MAINTENANCE_TRIGGER,
            trigger_ref="scheduler-runner:test-idle-gov-chain",
            runtime_provider_store=client.app.state.runtime_provider_store,
        )

    runs = repository.list_ceo_shadow_runs(workflow_id)
    assert exc_info.value.source_stage == "proposal"
    assert runs[0]["provider_response_id"] == "resp_ceo_idle_gov_chain_1"
    assert runs[0]["accepted_actions"] == []
    assert runs[0]["executed_actions"] == []


def test_ceo_shadow_run_rejects_legacy_no_action_reason_shape(client, monkeypatch):
    workflow_id = _seed_workflow(client, "wf_live_legacy_no_action", "Reject legacy NO_ACTION shape")
    _set_live_provider(client)

    from app.core import ceo_proposer

    def _fake_invoke(_config, _rendered_payload):
        return OpenAICompatProviderResult(
            output_text=json.dumps(
                {
                    "summary": "Legacy NO_ACTION should be rejected.",
                    "actions": [
                        {
                            "action_type": "NO_ACTION",
                            "reason": "Recent work already covers the need.",
                        }
                    ],
                }
            ),
            response_id="resp_ceo_legacy_no_action_1",
        )

    monkeypatch.setattr(ceo_proposer, "invoke_openai_compat_response", _fake_invoke)

    repository = client.app.state.repository
    with pytest.raises(CeoShadowPipelineError) as exc_info:
        run_ceo_shadow_for_trigger(
            repository,
            workflow_id=workflow_id,
            trigger_type="MANUAL_TEST",
            trigger_ref="manual:legacy-no-action",
            runtime_provider_store=client.app.state.runtime_provider_store,
        )

    runs = repository.list_ceo_shadow_runs(workflow_id)

    assert exc_info.value.source_stage == "proposal"
    assert runs[0]["deterministic_fallback_used"] is False
    assert runs[0]["accepted_actions"] == []
    assert runs[0]["executed_actions"] == []


def test_ceo_shadow_run_records_current_prompt_version(client, monkeypatch):
    workflow_id = _seed_workflow(client, "wf_live_prompt_version", "Record current CEO prompt version")
    _set_live_provider(client)

    from app.core import ceo_proposer

    def _fake_invoke(_config, _rendered_payload):
        return OpenAICompatProviderResult(
            output_text=json.dumps(
                {
                    "summary": "Recent work already covers the need.",
                    "actions": [
                        {
                            "action_type": "NO_ACTION",
                            "payload": {
                                "reason": "Recent completed work already covers the next step.",
                            },
                        }
                    ],
                }
            ),
            response_id="resp_ceo_prompt_version_1",
        )

    monkeypatch.setattr(ceo_proposer, "invoke_openai_compat_response", _fake_invoke)

    run = run_ceo_shadow_for_trigger(
        client.app.state.repository,
        workflow_id=workflow_id,
        trigger_type="MANUAL_TEST",
        trigger_ref="manual:prompt-version",
        runtime_provider_store=client.app.state.runtime_provider_store,
    )

    assert run["prompt_version"] == CEO_SHADOW_PROMPT_VERSION
    assert run["prompt_version"] == "ceo_shadow_v3"


@pytest.mark.parametrize(
    ("legacy_payload", "response_id"),
    [
        (
            {
                "workflow_id": "wf_live_legacy_hire",
                "role_type": "checker",
                "role_profile_ref": "checker_primary",
                "request_summary": "Hire a checker from legacy role_profile_ref.",
            },
            "resp_ceo_legacy_hire_role_profile_ref",
        ),
        (
            {
                "workflow_id": "wf_live_legacy_hire",
                "role_type": "checker",
                "role_profile_refs": ["checker_primary"],
                "request_summary": "Hire a checker from legacy justification.",
                "justification": "Old provider wording should not be accepted.",
            },
            "resp_ceo_legacy_hire_justification",
        ),
        (
            {
                "workflow_id": "wf_live_legacy_hire",
                "role_type": "checker",
                "role_profile_refs": ["checker_primary"],
                "request_summary": "Hire a checker from legacy selection guidance.",
                "selection_guidance": "Use the most experienced checker.",
            },
            "resp_ceo_legacy_hire_selection_guidance",
        ),
        (
            {
                "workflow_id": "wf_live_legacy_hire",
                "role_type": "checker",
                "role_profile_refs": ["checker_primary"],
                "request_summary": "Hire a checker from legacy reason.",
                "reason": "Old provider wording should not be accepted.",
            },
            "resp_ceo_legacy_hire_reason",
        ),
    ],
    ids=[
        "role_profile_ref_only",
        "legacy_justification",
        "legacy_selection_guidance",
        "legacy_reason",
    ],
)
def test_ceo_shadow_run_rejects_legacy_hire_employee_payload_shapes(
    client,
    monkeypatch,
    legacy_payload,
    response_id,
):
    workflow_id = _seed_workflow(client, "wf_live_legacy_hire", "Reject legacy HIRE_EMPLOYEE shapes")
    _set_live_provider(client)

    from app.core import ceo_proposer

    def _fake_invoke(_config, _rendered_payload):
        payload = dict(legacy_payload)
        payload["workflow_id"] = workflow_id
        return OpenAICompatProviderResult(
            output_text=json.dumps(
                {
                    "summary": "Legacy HIRE_EMPLOYEE should be rejected.",
                    "actions": [
                        {
                            "action_type": "HIRE_EMPLOYEE",
                            "payload": payload,
                        }
                    ],
                }
            ),
            response_id=response_id,
        )

    monkeypatch.setattr(ceo_proposer, "invoke_openai_compat_response", _fake_invoke)

    repository = client.app.state.repository
    with pytest.raises(CeoShadowPipelineError) as exc_info:
        run_ceo_shadow_for_trigger(
            repository,
            workflow_id=workflow_id,
            trigger_type="MANUAL_TEST",
            trigger_ref=response_id,
            runtime_provider_store=client.app.state.runtime_provider_store,
        )

    runs = repository.list_ceo_shadow_runs(workflow_id)

    assert exc_info.value.source_stage == "proposal"
    assert runs[0]["deterministic_fallback_used"] is False
    assert runs[0]["accepted_actions"] == []
    assert runs[0]["executed_actions"] == []


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


def test_ceo_shadow_run_raises_when_deterministic_project_init_kickoff_has_no_resolved_assignee(
    client,
    monkeypatch,
):
    _set_deterministic_mode(client)
    workflow_id = _seed_workflow(client, "wf_det_project_init_assignee_gap", "Kickoff assignee gap")

    from app.core import ceo_proposer

    monkeypatch.setattr(ceo_proposer, "_select_default_assignee", lambda *args, **kwargs: None)

    def _fake_snapshot(*_args, **_kwargs):
        return {
            "workflow": {"workflow_id": workflow_id, "workflow_profile": "CEO_AUTOPILOT_FINE_GRAINED"},
            "trigger": {"trigger_type": EVENT_BOARD_DIRECTIVE_RECEIVED, "trigger_ref": f"project-init:{workflow_id}"},
            "approvals": [],
            "incidents": [],
            "ticket_summary": {"active_count": 0, "total": 0},
            "nodes": [],
            "employees": [],
            "replan_focus": {
                "controller_state": {
                    "state": "GOVERNANCE_REQUIRED",
                    "recommended_action": "CREATE_TICKET",
                    "blocking_reason": "Kickoff governance ticket must be created first.",
                },
                "capability_plan": {},
                "meeting_candidates": [],
            },
        }

    monkeypatch.setattr("app.core.ceo_scheduler.build_ceo_shadow_snapshot", _fake_snapshot)

    repository = client.app.state.repository
    with pytest.raises(CeoShadowPipelineError) as exc_info:
        run_ceo_shadow_for_trigger(
            repository,
            workflow_id=workflow_id,
            trigger_type=EVENT_BOARD_DIRECTIVE_RECEIVED,
            trigger_ref=f"project-init:{workflow_id}",
        )

    runs = repository.list_ceo_shadow_runs(workflow_id)

    assert exc_info.value.source_stage == "proposal"
    assert runs[0]["deterministic_fallback_used"] is False
    assert runs[0]["accepted_actions"] == []
    assert runs[0]["executed_actions"] == []


def test_ceo_shadow_run_hires_architect_before_project_init_governance_kickoff(client):
    _set_deterministic_mode(client)
    workflow_id = _seed_workflow(client, "wf_project_init_architect_hire", "Project init architect hire")
    _persist_workflow_directive_details(
        client.app.state.repository,
        workflow_id,
        workflow_profile="CEO_AUTOPILOT_FINE_GRAINED",
        hard_constraints=["Keep governance explicit."],
    )

    run = run_ceo_shadow_for_trigger(
        client.app.state.repository,
        workflow_id=workflow_id,
        trigger_type=EVENT_BOARD_DIRECTIVE_RECEIVED,
        trigger_ref=f"project-init:{workflow_id}",
    )

    assert run["snapshot"]["controller_state"]["recommended_action"] == "HIRE_EMPLOYEE"
    assert run["accepted_actions"][0]["action_type"] == "HIRE_EMPLOYEE"
    assert run["executed_actions"][0]["action_type"] == "HIRE_EMPLOYEE"
    assert run["executed_actions"][0]["execution_status"] == "EXECUTED"
    assert run["executed_actions"][0]["payload"]["role_profile_refs"] == ["architect_primary"]

    hired_employee = client.app.state.repository.get_employee_projection("emp_architect_governance")
    assert hired_employee is not None
    assert hired_employee["state"] == "ACTIVE"
    assert hired_employee["board_approved"] is True

    followup_run = run_ceo_shadow_for_trigger(
        client.app.state.repository,
        workflow_id=workflow_id,
        trigger_type="MANUAL_TEST",
        trigger_ref="manual:post-project-init-hire",
    )

    assert followup_run["snapshot"]["controller_state"]["recommended_action"] == "CREATE_TICKET"
    assert followup_run["accepted_actions"][0]["action_type"] == "CREATE_TICKET"
    assert followup_run["executed_actions"][0]["action_type"] == "CREATE_TICKET"
    assert followup_run["executed_actions"][0]["execution_status"] == "EXECUTED"

    created_ticket_id = followup_run["executed_actions"][0]["payload"]["ticket_id"]
    with client.app.state.repository.connection() as connection:
        created_spec = client.app.state.repository.get_latest_ticket_created_payload(connection, created_ticket_id)

    assert created_spec["node_id"] == "node_ceo_architecture_brief"
    assert created_spec["role_profile_ref"] == "architect_primary"
    assert created_spec["output_schema_ref"] == ARCHITECTURE_BRIEF_SCHEMA_REF
    assert created_spec["dispatch_intent"]["assignee_employee_id"] == "emp_architect_governance"


def test_ceo_shadow_run_raises_when_deterministic_required_governance_plan_is_incomplete(
    client,
    monkeypatch,
):
    _set_deterministic_mode(client)
    workflow_id = _seed_workflow(client, "wf_det_required_governance_gap", "Governance plan gap")

    def _fake_snapshot(*_args, **_kwargs):
        return {
            "workflow": {"workflow_id": workflow_id, "workflow_profile": "CEO_AUTOPILOT_FINE_GRAINED"},
            "trigger": {"trigger_type": "MANUAL_TEST", "trigger_ref": "manual:required-governance-gap"},
            "approvals": [],
            "incidents": [],
            "ticket_summary": {"active_count": 0, "total": 1},
            "nodes": [],
            "employees": [],
            "replan_focus": {
                "controller_state": {
                    "state": "GOVERNANCE_REQUIRED",
                    "recommended_action": "CREATE_TICKET",
                    "blocking_reason": "Governance ticket must be created first.",
                },
                "capability_plan": {
                    "required_governance_ticket_plan": {
                        "node_id": "node_ceo_architecture_brief",
                        "role_profile_ref": "frontend_engineer_primary",
                        "output_schema_ref": ARCHITECTURE_BRIEF_SCHEMA_REF,
                        "assignee_employee_id": "",
                        "summary": "Create the architecture brief first.",
                        "selection_reason": "Follow governance progression.",
                    }
                },
                "meeting_candidates": [],
            },
        }

    monkeypatch.setattr("app.core.ceo_scheduler.build_ceo_shadow_snapshot", _fake_snapshot)

    repository = client.app.state.repository
    with pytest.raises(CeoShadowPipelineError) as exc_info:
        run_ceo_shadow_for_trigger(
            repository,
            workflow_id=workflow_id,
            trigger_type="MANUAL_TEST",
            trigger_ref="manual:required-governance-gap",
        )

    runs = repository.list_ceo_shadow_runs(workflow_id)

    assert exc_info.value.source_stage == "proposal"
    assert runs[0]["deterministic_fallback_used"] is False
    assert runs[0]["accepted_actions"] == []
    assert runs[0]["executed_actions"] == []


def test_ceo_shadow_run_raises_when_deterministic_hire_plan_is_incomplete(client, monkeypatch):
    _set_deterministic_mode(client)
    workflow_id = _seed_workflow(client, "wf_det_hire_gap", "Hire plan gap")

    def _fake_snapshot(*_args, **_kwargs):
        return {
            "workflow": {"workflow_id": workflow_id, "workflow_profile": "CEO_AUTOPILOT_FINE_GRAINED"},
            "trigger": {"trigger_type": "MANUAL_TEST", "trigger_ref": "manual:hire-gap"},
            "approvals": [],
            "incidents": [],
            "ticket_summary": {"active_count": 0, "total": 1},
            "nodes": [],
            "employees": [],
            "replan_focus": {
                "controller_state": {
                    "state": "STAFFING_REQUIRED",
                    "recommended_action": "HIRE_EMPLOYEE",
                    "blocking_reason": "Capability gap requires a new hire.",
                },
                "capability_plan": {
                    "recommended_hire": {
                        "role_type": "backend_engineer",
                        "role_profile_refs": [],
                        "request_summary": "Hire a backend engineer before fanout continues.",
                    }
                },
                "meeting_candidates": [],
            },
        }

    monkeypatch.setattr("app.core.ceo_scheduler.build_ceo_shadow_snapshot", _fake_snapshot)

    repository = client.app.state.repository
    with pytest.raises(CeoShadowPipelineError) as exc_info:
        run_ceo_shadow_for_trigger(
            repository,
            workflow_id=workflow_id,
            trigger_type="MANUAL_TEST",
            trigger_ref="manual:hire-gap",
        )

    runs = repository.list_ceo_shadow_runs(workflow_id)

    assert exc_info.value.source_stage == "proposal"
    assert runs[0]["deterministic_fallback_used"] is False
    assert runs[0]["accepted_actions"] == []
    assert runs[0]["executed_actions"] == []


def test_ceo_shadow_run_raises_when_deterministic_backlog_followup_plan_is_incomplete(
    client,
    monkeypatch,
):
    _set_deterministic_mode(client)
    workflow_id = _seed_workflow(client, "wf_det_followup_gap", "Backlog followup gap")

    def _fake_snapshot(*_args, **_kwargs):
        return {
            "workflow": {"workflow_id": workflow_id, "workflow_profile": "CEO_AUTOPILOT_FINE_GRAINED"},
            "trigger": {"trigger_type": "TICKET_COMPLETED", "trigger_ref": "tkt_backlog_gap"},
            "approvals": [],
            "incidents": [],
            "ticket_summary": {"active_count": 0, "total": 3},
            "nodes": [],
            "employees": [],
            "replan_focus": {
                "controller_state": {
                    "state": "READY_FOR_FANOUT",
                    "recommended_action": "CREATE_TICKET",
                    "blocking_reason": None,
                },
                "capability_plan": {
                    "followup_ticket_plans": [
                        {
                            "ticket_key": "BR-BE-01",
                            "existing_ticket_id": None,
                            "blocked_by_plan_keys": [],
                            "ticket_payload": {
                                "workflow_id": workflow_id,
                                "node_id": "node_backlog_followup_br_be_01",
                                "role_profile_ref": "backend_engineer_primary",
                                "output_schema_ref": "source_code_delivery",
                                "execution_contract": infer_execution_contract_payload(
                                    role_profile_ref="backend_engineer_primary",
                                    output_schema_ref="source_code_delivery",
                                ),
                                "dispatch_intent": {
                                    "assignee_employee_id": "",
                                    "selection_reason": "Translate the approved backlog item into implementation work.",
                                    "dependency_gate_refs": [],
                                },
                                "summary": "BR-BE-01 借阅后端 API 交付；范围：借阅服务、REST API",
                                "parent_ticket_id": "tkt_backlog_gap",
                            },
                        }
                    ]
                },
                "meeting_candidates": [],
            },
        }

    monkeypatch.setattr("app.core.ceo_scheduler.build_ceo_shadow_snapshot", _fake_snapshot)

    repository = client.app.state.repository
    with pytest.raises(CeoShadowPipelineError) as exc_info:
        run_ceo_shadow_for_trigger(
            repository,
            workflow_id=workflow_id,
            trigger_type="TICKET_COMPLETED",
            trigger_ref="tkt_backlog_gap",
        )

    runs = repository.list_ceo_shadow_runs(workflow_id)

    assert exc_info.value.source_stage == "proposal"
    assert runs[0]["deterministic_fallback_used"] is False
    assert runs[0]["accepted_actions"] == []
    assert runs[0]["executed_actions"] == []


def test_ceo_shadow_run_raises_when_deterministic_meeting_request_has_no_eligible_candidate(
    client,
    monkeypatch,
):
    _set_deterministic_mode(client)
    workflow_id = _seed_workflow(client, "wf_det_meeting_gap", "Meeting candidate gap")

    def _fake_snapshot(*_args, **_kwargs):
        return {
            "workflow": {"workflow_id": workflow_id, "workflow_profile": "CEO_AUTOPILOT_FINE_GRAINED"},
            "trigger": {"trigger_type": "MANUAL_TEST", "trigger_ref": "manual:meeting-gap"},
            "approvals": [],
            "incidents": [],
            "ticket_summary": {"active_count": 0, "total": 1},
            "nodes": [],
            "employees": [],
            "replan_focus": {
                "controller_state": {
                    "state": "MEETING_REQUIRED",
                    "recommended_action": "REQUEST_MEETING",
                    "blocking_reason": "Meeting gate must be satisfied first.",
                },
                "capability_plan": {},
                "meeting_candidates": [],
            },
        }

    monkeypatch.setattr("app.core.ceo_scheduler.build_ceo_shadow_snapshot", _fake_snapshot)

    repository = client.app.state.repository
    with pytest.raises(CeoShadowPipelineError) as exc_info:
        run_ceo_shadow_for_trigger(
            repository,
            workflow_id=workflow_id,
            trigger_type="MANUAL_TEST",
            trigger_ref="manual:meeting-gap",
        )

    runs = repository.list_ceo_shadow_runs(workflow_id)

    assert exc_info.value.source_stage == "proposal"
    assert runs[0]["deterministic_fallback_used"] is False
    assert runs[0]["accepted_actions"] == []
    assert runs[0]["executed_actions"] == []


def test_mainline_deterministic_fallback_blocks_create_ticket_on_board_directive(client, monkeypatch):
    _set_deterministic_mode(client)
    workflow_id = _seed_workflow(client, "wf_det_mainline_create_blocked", "Block mainline create fallback")
    monkeypatch.setattr("app.core.ceo_proposer._select_default_assignee", lambda *args, **kwargs: "emp_frontend_2")

    def _fake_snapshot(*_args, **_kwargs):
        return {
            "workflow": {
                "workflow_id": workflow_id,
                "workflow_profile": "CEO_AUTOPILOT_FINE_GRAINED",
                "north_star_goal": "Block implicit kickoff fallback",
                "title": "Block implicit kickoff fallback",
            },
            "trigger": {
                "trigger_type": EVENT_BOARD_DIRECTIVE_RECEIVED,
                "trigger_ref": f"project-init:{workflow_id}",
            },
            "approvals": [],
            "incidents": [],
            "ticket_summary": {"active_count": 0, "total": 0},
            "nodes": [],
            "employees": [],
            "replan_focus": {
                "controller_state": {
                    "state": "GOVERNANCE_REQUIRED",
                    "recommended_action": "CREATE_TICKET",
                    "blocking_reason": "Kickoff governance ticket must be created first.",
                },
                "capability_plan": {},
                "meeting_candidates": [],
            },
        }

    monkeypatch.setattr("app.core.ceo_scheduler.build_ceo_shadow_snapshot", _fake_snapshot)

    repository = client.app.state.repository
    with pytest.raises(CeoShadowPipelineError) as exc_info:
        run_ceo_shadow_for_trigger(
            repository,
            workflow_id=workflow_id,
            trigger_type=EVENT_BOARD_DIRECTIVE_RECEIVED,
            trigger_ref=f"project-init:{workflow_id}",
        )

    runs = repository.list_ceo_shadow_runs(workflow_id)

    assert exc_info.value.source_stage == "proposal"
    assert runs[0]["deterministic_fallback_used"] is False
    assert runs[0]["accepted_actions"] == []
    assert runs[0]["executed_actions"] == []
    assert "deterministic fallback" in str(runs[0]["fallback_reason"] or "").lower()
    assert "create_ticket" in str(runs[0]["fallback_reason"] or "").lower()


def test_mainline_deterministic_fallback_blocks_hire_employee_on_ticket_completed(client, monkeypatch):
    _set_deterministic_mode(client)
    workflow_id = _seed_workflow(client, "wf_det_mainline_hire_blocked", "Block mainline hire fallback")

    def _fake_snapshot(*_args, **_kwargs):
        return {
            "workflow": {"workflow_id": workflow_id, "workflow_profile": "CEO_AUTOPILOT_FINE_GRAINED"},
            "trigger": {"trigger_type": "TICKET_COMPLETED", "trigger_ref": "tkt_backlog_hire_gap"},
            "approvals": [],
            "incidents": [],
            "ticket_summary": {"active_count": 0, "total": 1},
            "nodes": [],
            "employees": [],
            "replan_focus": {
                "controller_state": {
                    "state": "STAFFING_REQUIRED",
                    "recommended_action": "HIRE_EMPLOYEE",
                    "blocking_reason": "Capability gap requires a new hire.",
                },
                "capability_plan": {
                    "recommended_hire": {
                        "role_type": "governance_architect",
                        "role_profile_refs": ["architect_primary"],
                        "request_summary": "Hire one architect before implementation fanout continues.",
                    }
                },
                "meeting_candidates": [],
            },
        }

    monkeypatch.setattr("app.core.ceo_scheduler.build_ceo_shadow_snapshot", _fake_snapshot)

    repository = client.app.state.repository
    with pytest.raises(CeoShadowPipelineError) as exc_info:
        run_ceo_shadow_for_trigger(
            repository,
            workflow_id=workflow_id,
            trigger_type="TICKET_COMPLETED",
            trigger_ref="tkt_backlog_hire_gap",
        )

    runs = repository.list_ceo_shadow_runs(workflow_id)

    assert exc_info.value.source_stage == "proposal"
    assert runs[0]["deterministic_fallback_used"] is False
    assert runs[0]["accepted_actions"] == []
    assert runs[0]["executed_actions"] == []
    assert "deterministic fallback" in str(runs[0]["fallback_reason"] or "").lower()
    assert "hire_employee" in str(runs[0]["fallback_reason"] or "").lower()


def test_mainline_deterministic_fallback_blocks_request_meeting_on_ticket_completed(client, monkeypatch):
    _set_deterministic_mode(client)
    workflow_id = _seed_workflow(client, "wf_det_mainline_meeting_blocked", "Block mainline meeting fallback")

    def _fake_snapshot(*_args, **_kwargs):
        return {
            "workflow": {"workflow_id": workflow_id, "workflow_profile": "CEO_AUTOPILOT_FINE_GRAINED"},
            "trigger": {"trigger_type": "TICKET_COMPLETED", "trigger_ref": "tkt_backlog_meeting_gap"},
            "approvals": [],
            "incidents": [],
            "ticket_summary": {"active_count": 0, "total": 1},
            "nodes": [],
            "employees": [],
            "replan_focus": {
                "controller_state": {
                    "state": "MEETING_REQUIRED",
                    "recommended_action": "REQUEST_MEETING",
                    "blocking_reason": "One technical decision meeting must happen before fanout resumes.",
                },
                "capability_plan": {},
                "meeting_candidates": [
                    {
                        "workflow_id": workflow_id,
                        "source_graph_node_id": "node_backlog_meeting_gap",
                        "source_ticket_id": "tkt_backlog_meeting_gap",
                        "topic": "Lock the implementation boundary before delivery fanout.",
                        "participant_employee_ids": ["emp_architect_1", "emp_checker_1"],
                        "recorder_employee_id": "emp_architect_1",
                        "input_artifact_refs": ["art://runtime/tkt_backlog_meeting_gap/backlog_recommendation.json"],
                        "reason": "The controller requires one bounded technical decision meeting.",
                        "eligible": True,
                    }
                ],
            },
        }

    monkeypatch.setattr("app.core.ceo_scheduler.build_ceo_shadow_snapshot", _fake_snapshot)

    repository = client.app.state.repository
    with pytest.raises(CeoShadowPipelineError) as exc_info:
        run_ceo_shadow_for_trigger(
            repository,
            workflow_id=workflow_id,
            trigger_type="TICKET_COMPLETED",
            trigger_ref="tkt_backlog_meeting_gap",
        )

    runs = repository.list_ceo_shadow_runs(workflow_id)

    assert exc_info.value.source_stage == "proposal"
    assert runs[0]["deterministic_fallback_used"] is False
    assert runs[0]["accepted_actions"] == []
    assert runs[0]["executed_actions"] == []
    assert "deterministic fallback" in str(runs[0]["fallback_reason"] or "").lower()
    assert "request_meeting" in str(runs[0]["fallback_reason"] or "").lower()


def test_controller_ready_ticket_staffing_recommends_hire_when_no_active_role_worker(client):
    workflow_id = _seed_workflow(
        client,
        "wf_ready_ticket_staffing_required",
        "Ready ticket should surface staffing gap.",
    )
    _persist_workflow_directive_details(
        client.app.state.repository,
        workflow_id,
        workflow_profile="CEO_AUTOPILOT_FINE_GRAINED",
    )
    _create_ticket_for_test(
        client,
        _ticket_create_payload(
            workflow_id=workflow_id,
            ticket_id="tkt_ready_backend_staffing_required",
            node_id="node_ready_backend_staffing_required",
            role_profile_ref="backend_engineer_primary",
            output_schema_ref="source_code_delivery",
        ),
    )

    snapshot = build_ceo_shadow_snapshot(
        client.app.state.repository,
        workflow_id=workflow_id,
        trigger_type=SCHEDULER_IDLE_MAINTENANCE_TRIGGER,
        trigger_ref="scheduler-runner:test-ready-staffing-required",
    )

    assert snapshot["controller_state"]["state"] == "STAFFING_REQUIRED"
    assert snapshot["controller_state"]["recommended_action"] == "HIRE_EMPLOYEE"
    assert snapshot["capability_plan"]["recommended_hire"]["role_profile_refs"] == [
        "backend_engineer_primary"
    ]
    assert snapshot["capability_plan"]["recommended_hire"]["role_type"] == "backend_engineer"
    assert snapshot["capability_plan"]["ready_ticket_staffing_gaps"][0]["ticket_id"] == (
        "tkt_ready_backend_staffing_required"
    )
    assert snapshot["capability_plan"]["ready_ticket_staffing_gaps"][0]["reason_code"] == "NO_ACTIVE_ROLE_WORKER"
    assert snapshot["capability_plan"]["contract_issues"] == []


def test_controller_classifies_ready_ticket_role_schema_mismatch_without_hire(client):
    workflow_id = _seed_workflow(
        client,
        "wf_ready_ticket_contract_mismatch",
        "Ready ticket contract mismatch should not trigger hiring.",
    )
    _persist_workflow_directive_details(
        client.app.state.repository,
        workflow_id,
        workflow_profile="CEO_AUTOPILOT_FINE_GRAINED",
    )
    repository = client.app.state.repository
    payload = _ticket_create_payload(
        workflow_id=workflow_id,
        ticket_id="tkt_ready_cto_source_mismatch",
        node_id="node_ready_cto_source_mismatch",
        role_profile_ref="cto_primary",
        output_schema_ref="source_code_delivery",
    )
    with repository.transaction() as connection:
        repository.insert_event(
            connection,
            event_type="TICKET_CREATED",
            actor_type="system",
            actor_id="test-seed",
            workflow_id=workflow_id,
            idempotency_key="test-seed-ticket-created:wf_ready_ticket_contract_mismatch:mismatch",
            causation_id=None,
            correlation_id=workflow_id,
            payload=payload,
            occurred_at=datetime.fromisoformat("2026-04-05T10:10:00+08:00"),
        )
        repository.refresh_projections(connection)

    snapshot = build_ceo_shadow_snapshot(
        repository,
        workflow_id=workflow_id,
        trigger_type=SCHEDULER_IDLE_MAINTENANCE_TRIGGER,
        trigger_ref="scheduler-runner:test-ready-contract-mismatch",
    )

    assert snapshot["controller_state"]["state"] == "CONTRACT_REPLAN_REQUIRED"
    assert snapshot["controller_state"]["recommended_action"] == "NO_ACTION"
    assert "recommended_hire" not in snapshot["capability_plan"]
    assert snapshot["capability_plan"]["ready_ticket_staffing_gaps"] == []
    assert snapshot["capability_plan"]["contract_issues"][0]["reason_code"] == "ROLE_SCHEMA_UNSUPPORTED"
    assert snapshot["capability_plan"]["contract_issues"][0]["ticket_id"] == "tkt_ready_cto_source_mismatch"


def test_controller_worker_busy_recommends_capacity_hire_for_ready_ticket(client):
    busy_workflow_id = _seed_workflow(client, "wf_busy_backend_worker", "Busy backend worker")
    _seed_board_approved_employee(
        client,
        employee_id="emp_backend_busy",
        role_type="backend_engineer",
        role_profile_refs=["backend_engineer_primary"],
    )
    _create_ticket_for_test(
        client,
        _ticket_create_payload(
            workflow_id=busy_workflow_id,
            ticket_id="tkt_backend_busy_existing",
            node_id="node_backend_busy_existing",
            role_profile_ref="backend_engineer_primary",
            output_schema_ref="source_code_delivery",
        ),
    )
    with _temporary_live_provider(client):
        _lease_ticket_for_test(
            client,
            workflow_id=busy_workflow_id,
            ticket_id="tkt_backend_busy_existing",
            node_id="node_backend_busy_existing",
            leased_by="emp_backend_busy",
            idempotency_key="ticket-lease:wf_busy_backend_worker:tkt_backend_busy_existing",
        )

    workflow_id = _seed_workflow(
        client,
        "wf_ready_ticket_worker_busy",
        "Ready ticket should hire more capacity when matching worker is busy.",
    )
    _persist_workflow_directive_details(
        client.app.state.repository,
        workflow_id,
        workflow_profile="CEO_AUTOPILOT_FINE_GRAINED",
    )
    _create_ticket_for_test(
        client,
        _ticket_create_payload(
            workflow_id=workflow_id,
            ticket_id="tkt_ready_backend_worker_busy",
            node_id="node_ready_backend_worker_busy",
            role_profile_ref="backend_engineer_primary",
            output_schema_ref="source_code_delivery",
        ),
    )

    snapshot = build_ceo_shadow_snapshot(
        client.app.state.repository,
        workflow_id=workflow_id,
        trigger_type=SCHEDULER_IDLE_MAINTENANCE_TRIGGER,
        trigger_ref="scheduler-runner:test-ready-worker-busy",
    )

    assert snapshot["controller_state"]["state"] == "STAFFING_REQUIRED"
    assert snapshot["controller_state"]["recommended_action"] == "HIRE_EMPLOYEE"
    assert snapshot["capability_plan"]["ready_ticket_staffing_gaps"][0]["reason_code"] == "WORKER_BUSY"
    assert snapshot["capability_plan"]["recommended_hire"]["role_profile_refs"] == ["backend_engineer_primary"]
    assert "capacity" in snapshot["capability_plan"]["recommended_hire"]["request_summary"].lower()


def test_controller_worker_excluded_waits_for_ready_ticket_recovery(client):
    workflow_id = _seed_workflow(
        client,
        "wf_ready_ticket_worker_excluded",
        "Ready ticket excluded worker should wait for recovery.",
    )
    _persist_workflow_directive_details(
        client.app.state.repository,
        workflow_id,
        workflow_profile="CEO_AUTOPILOT_FINE_GRAINED",
    )
    _seed_board_approved_employee(
        client,
        employee_id="emp_backend_excluded",
        role_type="backend_engineer",
        role_profile_refs=["backend_engineer_primary"],
    )
    payload = _ticket_create_payload(
        workflow_id=workflow_id,
        ticket_id="tkt_ready_backend_worker_excluded",
        node_id="node_ready_backend_worker_excluded",
        role_profile_ref="backend_engineer_primary",
        output_schema_ref="source_code_delivery",
    )
    payload["excluded_employee_ids"] = ["emp_backend_excluded"]
    _create_ticket_for_test(client, payload)

    snapshot = build_ceo_shadow_snapshot(
        client.app.state.repository,
        workflow_id=workflow_id,
        trigger_type=SCHEDULER_IDLE_MAINTENANCE_TRIGGER,
        trigger_ref="scheduler-runner:test-ready-worker-excluded",
    )

    assert snapshot["controller_state"]["state"] == "STAFFING_WAIT"
    assert snapshot["controller_state"]["recommended_action"] == "NO_ACTION"
    assert "recommended_hire" not in snapshot["capability_plan"]
    assert snapshot["capability_plan"]["ready_ticket_staffing_gaps"] == []
    assert snapshot["capability_plan"]["staffing_wait_reasons"][0]["reason_code"] == "WORKER_EXCLUDED"


def test_controller_provider_paused_waits_for_ready_ticket_recovery(client):
    paused_workflow_id = _seed_workflow(client, "wf_paused_backend_provider", "Paused backend provider")
    repository = client.app.state.repository
    with repository.transaction() as connection:
        repository.insert_event(
            connection,
            event_type=EVENT_INCIDENT_OPENED,
            actor_type="system",
            actor_id="test-seed",
            workflow_id=paused_workflow_id,
            idempotency_key="incident-opened:wf_paused_backend_provider:provider",
            causation_id=None,
            correlation_id=paused_workflow_id,
            payload={
                "incident_id": "inc_paused_backend_provider",
                "incident_type": "RUNTIME_PROVIDER_FAILURE",
                "status": "OPEN",
                "severity": "high",
                "fingerprint": "provider:prov_openai_compat:paused",
                "provider_id": OPENAI_COMPAT_PROVIDER_ID,
            },
            occurred_at=datetime.fromisoformat("2026-04-05T10:10:00+08:00"),
        )
        repository.insert_event(
            connection,
            event_type=EVENT_CIRCUIT_BREAKER_OPENED,
            actor_type="system",
            actor_id="test-seed",
            workflow_id=paused_workflow_id,
            idempotency_key="breaker-opened:wf_paused_backend_provider:provider",
            causation_id=None,
            correlation_id=paused_workflow_id,
            payload={
                "incident_id": "inc_paused_backend_provider",
                "incident_type": "RUNTIME_PROVIDER_FAILURE",
                "circuit_breaker_state": "OPEN",
                "fingerprint": "provider:prov_openai_compat:paused",
                "provider_id": OPENAI_COMPAT_PROVIDER_ID,
            },
            occurred_at=datetime.fromisoformat("2026-04-05T10:10:01+08:00"),
        )
        repository.refresh_projections(connection)
    _seed_board_approved_employee(
        client,
        employee_id="emp_backend_provider_paused",
        role_type="backend_engineer",
        role_profile_refs=["backend_engineer_primary"],
        provider_id=OPENAI_COMPAT_PROVIDER_ID,
    )

    workflow_id = _seed_workflow(
        client,
        "wf_ready_ticket_provider_paused",
        "Ready ticket provider pause should wait for recovery.",
    )
    _persist_workflow_directive_details(
        repository,
        workflow_id,
        workflow_profile="CEO_AUTOPILOT_FINE_GRAINED",
    )
    _create_ticket_for_test(
        client,
        _ticket_create_payload(
            workflow_id=workflow_id,
            ticket_id="tkt_ready_backend_provider_paused",
            node_id="node_ready_backend_provider_paused",
            role_profile_ref="backend_engineer_primary",
            output_schema_ref="source_code_delivery",
        ),
    )

    snapshot = build_ceo_shadow_snapshot(
        repository,
        workflow_id=workflow_id,
        trigger_type=SCHEDULER_IDLE_MAINTENANCE_TRIGGER,
        trigger_ref="scheduler-runner:test-ready-provider-paused",
    )

    assert snapshot["controller_state"]["state"] == "STAFFING_WAIT"
    assert snapshot["controller_state"]["recommended_action"] == "NO_ACTION"
    assert "recommended_hire" not in snapshot["capability_plan"]
    assert snapshot["capability_plan"]["ready_ticket_staffing_gaps"] == []
    assert snapshot["capability_plan"]["staffing_wait_reasons"][0]["reason_code"] == "PROVIDER_PAUSED"


def test_ceo_hire_fallback_uses_missing_ready_ticket_role_profile(client):
    workflow_id = _seed_workflow(
        client,
        "wf_ready_ticket_hire_fallback",
        "CEO fallback should hire missing ready-ticket role.",
    )
    _persist_workflow_directive_details(
        client.app.state.repository,
        workflow_id,
        workflow_profile="CEO_AUTOPILOT_FINE_GRAINED",
    )
    _create_ticket_for_test(
        client,
        _ticket_create_payload(
            workflow_id=workflow_id,
            ticket_id="tkt_ready_database_hire_fallback",
            node_id="node_ready_database_hire_fallback",
            role_profile_ref="database_engineer_primary",
            output_schema_ref="source_code_delivery",
        ),
    )
    snapshot = build_ceo_shadow_snapshot(
        client.app.state.repository,
        workflow_id=workflow_id,
        trigger_type=SCHEDULER_IDLE_MAINTENANCE_TRIGGER,
        trigger_ref="scheduler-runner:test-ready-hire-fallback",
    )

    from app.core.ceo_proposer import build_deterministic_fallback_batch

    batch = build_deterministic_fallback_batch(
        client.app.state.repository,
        snapshot,
        "Hire the missing ready-ticket role.",
    )
    action = batch.model_dump(mode="json")["actions"][0]

    assert action["action_type"] == "HIRE_EMPLOYEE"
    assert action["payload"]["workflow_id"] == workflow_id
    assert action["payload"]["role_type"] == "database_engineer"
    assert action["payload"]["role_profile_refs"] == ["database_engineer_primary"]
    assert "request_summary" in action["payload"]
    assert "role_profile_ref" not in action["payload"]


def test_ceo_hire_fallback_rejects_when_role_profile_is_already_covered(client):
    workflow_id = _seed_workflow(
        client,
        "wf_ready_ticket_cto_hire_reuse_guard",
        "CEO fallback should reuse an existing CTO instead of hiring another.",
    )
    _seed_board_approved_employee(
        client,
        employee_id="emp_existing_cto_any_id",
        role_type="governance_cto",
        role_profile_refs=["cto_primary"],
    )
    snapshot = {
        "workflow": {"workflow_id": workflow_id},
        "replan_focus": {
            "controller_state": {
                "state": "STAFFING_REQUIRED",
                "recommended_action": "HIRE_EMPLOYEE",
            },
            "capability_plan": {
                "recommended_hire": {
                    "role_type": "governance_cto",
                    "role_profile_refs": ["cto_primary"],
                    "request_summary": "Hire a CTO governance worker.",
                }
            },
        },
    }

    from app.core.ceo_proposer import CEOProposalContractError, build_deterministic_fallback_batch

    with pytest.raises(CEOProposalContractError) as exc_info:
        build_deterministic_fallback_batch(
            client.app.state.repository,
            snapshot,
            "Hire the missing CTO role.",
        )

    assert exc_info.value.reason_code == "ROLE_ALREADY_COVERED"
    assert exc_info.value.details == {
        "reason_code": "ROLE_ALREADY_COVERED",
        "reuse_candidate_employee_id": "emp_existing_cto_any_id",
        "role_type": "governance_cto",
        "role_profile_refs": ["cto_primary"],
    }


def test_ceo_shadow_snapshot_suppresses_repeated_hire_after_role_already_covered_rejection(client):
    busy_workflow_id = _seed_workflow(client, "wf_reuse_guard_busy_backend", "Busy backend worker")
    _seed_board_approved_employee(
        client,
        employee_id="emp_backend_reuse_guard_busy",
        role_type="backend_engineer",
        role_profile_refs=["backend_engineer_primary"],
    )
    _create_ticket_for_test(
        client,
        _ticket_create_payload(
            workflow_id=busy_workflow_id,
            ticket_id="tkt_backend_reuse_guard_busy_existing",
            node_id="node_backend_reuse_guard_busy_existing",
            role_profile_ref="backend_engineer_primary",
            output_schema_ref="source_code_delivery",
        ),
    )
    with _temporary_live_provider(client):
        _lease_ticket_for_test(
            client,
            workflow_id=busy_workflow_id,
            ticket_id="tkt_backend_reuse_guard_busy_existing",
            node_id="node_backend_reuse_guard_busy_existing",
            leased_by="emp_backend_reuse_guard_busy",
            idempotency_key="ticket-lease:wf_reuse_guard_busy_backend:tkt_backend_reuse_guard_busy_existing",
        )

    workflow_id = _seed_workflow(
        client,
        "wf_reuse_guard_repeated_backend_hire",
        "Repeated backend hire should be suppressed after covered-role rejection.",
    )
    _persist_workflow_directive_details(
        client.app.state.repository,
        workflow_id,
        workflow_profile="CEO_AUTOPILOT_FINE_GRAINED",
    )
    _create_ticket_for_test(
        client,
        _ticket_create_payload(
            workflow_id=workflow_id,
            ticket_id="tkt_reuse_guard_backend_ready",
            node_id="node_reuse_guard_backend_ready",
            role_profile_ref="backend_engineer_primary",
            output_schema_ref="source_code_delivery",
        ),
    )
    repository = client.app.state.repository
    rejection_details = {
        "reason_code": "ROLE_ALREADY_COVERED",
        "reuse_candidate_employee_id": "emp_backend_reuse_guard_busy",
        "role_type": "backend_engineer",
        "role_profile_refs": ["backend_engineer_primary"],
    }
    with repository.transaction() as connection:
        repository.append_ceo_shadow_run(
            connection,
            workflow_id=workflow_id,
            trigger_type=SCHEDULER_IDLE_MAINTENANCE_TRIGGER,
            trigger_ref="scheduler-runner:test-reuse-guard-previous",
            occurred_at=datetime.fromisoformat("2026-04-08T09:00:00+08:00"),
            effective_mode="DETERMINISTIC",
            provider_health_summary="OK",
            model=None,
            preferred_provider_id=None,
            preferred_model=None,
            actual_provider_id=None,
            actual_model=None,
            selection_reason=None,
            policy_reason=None,
            prompt_version=CEO_SHADOW_PROMPT_VERSION,
            provider_response_id=None,
            fallback_reason=None,
            snapshot={},
            proposed_action_batch={},
            accepted_actions=[],
            rejected_actions=[
                {
                    "action_type": "HIRE_EMPLOYEE",
                    "payload": {
                        "workflow_id": workflow_id,
                        "role_type": "backend_engineer",
                        "role_profile_refs": ["backend_engineer_primary"],
                    },
                    "reason": "Role already covered.",
                    "details": rejection_details,
                }
            ],
            executed_actions=[],
            execution_summary={},
            deterministic_fallback_used=False,
            deterministic_fallback_reason=None,
            comparison={},
        )

    snapshot = build_ceo_shadow_snapshot(
        repository,
        workflow_id=workflow_id,
        trigger_type=SCHEDULER_IDLE_MAINTENANCE_TRIGGER,
        trigger_ref="scheduler-runner:test-reuse-guard-current",
    )

    assert snapshot["controller_state"]["state"] == "STAFFING_WAIT"
    assert snapshot["controller_state"]["recommended_action"] == "NO_ACTION"
    assert "recommended_hire" not in snapshot["capability_plan"]
    assert "emp_backend_reuse_guard_busy" in snapshot["capability_plan"]["reuse_candidate_employee_ids"]


def test_duplicate_hire_loop_opens_incident_after_second_rejection(client, monkeypatch):
    _set_live_provider(client)
    busy_workflow_id = _seed_workflow(client, "wf_duplicate_loop_busy_backend", "Busy backend worker")
    _seed_board_approved_employee(
        client,
        employee_id="emp_backend_duplicate_loop_busy",
        role_type="backend_engineer",
        role_profile_refs=["backend_engineer_primary"],
    )
    _create_ticket_for_test(
        client,
        _ticket_create_payload(
            workflow_id=busy_workflow_id,
            ticket_id="tkt_duplicate_loop_backend_busy_existing",
            node_id="node_duplicate_loop_backend_busy_existing",
            role_profile_ref="backend_engineer_primary",
            output_schema_ref="source_code_delivery",
        ),
    )
    with _temporary_live_provider(client):
        _lease_ticket_for_test(
            client,
            workflow_id=busy_workflow_id,
            ticket_id="tkt_duplicate_loop_backend_busy_existing",
            node_id="node_duplicate_loop_backend_busy_existing",
            leased_by="emp_backend_duplicate_loop_busy",
            idempotency_key=(
                "ticket-lease:wf_duplicate_loop_busy_backend:"
                "tkt_duplicate_loop_backend_busy_existing"
            ),
        )
    _set_live_provider(client)

    workflow_id = _seed_workflow(
        client,
        "wf_duplicate_loop_repeated_backend_hire",
        "Repeated backend hire opens a loop incident.",
    )
    _persist_workflow_directive_details(
        client.app.state.repository,
        workflow_id,
        workflow_profile="CEO_AUTOPILOT_FINE_GRAINED",
    )
    _create_ticket_for_test(
        client,
        _ticket_create_payload(
            workflow_id=workflow_id,
            ticket_id="tkt_duplicate_loop_backend_ready",
            node_id="node_duplicate_loop_backend_ready",
            role_profile_ref="backend_engineer_primary",
            output_schema_ref="source_code_delivery",
        ),
    )
    repository = client.app.state.repository
    stale_snapshot = build_ceo_shadow_snapshot(
        repository,
        workflow_id=workflow_id,
        trigger_type=SCHEDULER_IDLE_MAINTENANCE_TRIGGER,
        trigger_ref="scheduler-runner:test-duplicate-loop-stale",
    )

    import app.core.ceo_proposer as ceo_proposer
    import app.core.ceo_scheduler as ceo_scheduler

    def _fake_snapshot(*args, **kwargs):
        return json.loads(json.dumps(stale_snapshot))

    def _fake_invoke(_config, rendered_payload):
        snapshot = rendered_payload.messages[2].content_payload
        recommended_hire = snapshot["capability_plan"]["recommended_hire"]
        return OpenAICompatProviderResult(
            output_text=json.dumps(
                {
                    "summary": "Hire backend capacity again.",
                    "actions": [
                        {
                            "action_type": "HIRE_EMPLOYEE",
                            "payload": {
                                "workflow_id": workflow_id,
                                "role_type": recommended_hire["role_type"],
                                "role_profile_refs": recommended_hire["role_profile_refs"],
                                "request_summary": recommended_hire["request_summary"],
                                "employee_id_hint": "emp_backend_duplicate_loop_new",
                            },
                        }
                    ],
                }
            ),
            response_id="resp_ceo_duplicate_hire_loop",
        )

    monkeypatch.setattr(ceo_scheduler, "build_ceo_shadow_snapshot", _fake_snapshot)
    monkeypatch.setattr(ceo_proposer, "invoke_openai_compat_response", _fake_invoke)

    first_run = run_ceo_shadow_for_trigger(
        repository,
        workflow_id=workflow_id,
        trigger_type=SCHEDULER_IDLE_MAINTENANCE_TRIGGER,
        trigger_ref="scheduler-runner:test-duplicate-loop-first",
        runtime_provider_store=client.app.state.runtime_provider_store,
    )
    assert first_run["rejected_actions"][0]["details"]["reason_code"] == "ROLE_ALREADY_COVERED"
    assert [
        incident
        for incident in repository.list_open_incidents()
        if incident["workflow_id"] == workflow_id
    ] == []

    second_run = run_ceo_shadow_for_trigger(
        repository,
        workflow_id=workflow_id,
        trigger_type=SCHEDULER_IDLE_MAINTENANCE_TRIGGER,
        trigger_ref="scheduler-runner:test-duplicate-loop-second",
        runtime_provider_store=client.app.state.runtime_provider_store,
    )
    incidents = [
        incident
        for incident in repository.list_open_incidents()
        if incident["workflow_id"] == workflow_id
    ]

    assert second_run["rejected_actions"][0]["details"]["reason_code"] == "ROLE_ALREADY_COVERED"
    assert len(incidents) == 1
    assert incidents[0]["incident_type"] == "CEO_HIRE_LOOP_DETECTED"
    assert incidents[0]["payload"]["reuse_candidate_employee_id"] == "emp_backend_duplicate_loop_busy"
    assert incidents[0]["payload"]["rejected_action"]["details"]["reason_code"] == "ROLE_ALREADY_COVERED"
    assert incidents[0]["payload"]["recommended_hire"]["role_profile_refs"] == [
        "backend_engineer_primary"
    ]


def test_duplicate_hire_loop_summary_suppresses_same_recommended_hire(client):
    workflow_id = _seed_workflow(
        client,
        "wf_duplicate_loop_open_incident",
        "Open duplicate hire loop incident should block more hiring.",
    )
    _persist_workflow_directive_details(
        client.app.state.repository,
        workflow_id,
        workflow_profile="CEO_AUTOPILOT_FINE_GRAINED",
    )
    _create_ticket_for_test(
        client,
        _ticket_create_payload(
            workflow_id=workflow_id,
            ticket_id="tkt_duplicate_loop_open_backend_ready",
            node_id="node_duplicate_loop_open_backend_ready",
            role_profile_ref="backend_engineer_primary",
            output_schema_ref="source_code_delivery",
        ),
    )
    repository = client.app.state.repository
    with repository.transaction() as connection:
        repository.insert_event(
            connection,
            event_type=EVENT_INCIDENT_OPENED,
            actor_type="system",
            actor_id="ceo-hire-loop-detector",
            workflow_id=workflow_id,
            idempotency_key="incident-opened:wf_duplicate_loop_open_incident:hire-loop",
            causation_id=None,
            correlation_id=workflow_id,
            payload={
                "incident_id": "inc_duplicate_loop_open",
                "incident_type": "CEO_HIRE_LOOP_DETECTED",
                "status": "OPEN",
                "severity": "high",
                "fingerprint": (
                    "ceo-hire-loop:"
                    "wf_duplicate_loop_open_incident:STAFFING_REQUIRED:HIRE_EMPLOYEE:"
                    "backend_engineer:backend_engineer_primary:ROLE_ALREADY_COVERED"
                ),
                "loop_fingerprint": (
                    "ceo-hire-loop:"
                    "wf_duplicate_loop_open_incident:STAFFING_REQUIRED:HIRE_EMPLOYEE:"
                    "backend_engineer:backend_engineer_primary:ROLE_ALREADY_COVERED"
                ),
                "reuse_candidate_employee_id": "emp_backend_loop_reuse",
                "role_type": "backend_engineer",
                "role_profile_refs": ["backend_engineer_primary"],
                "suggested_recovery_action": "REUSE_EXISTING_EMPLOYEE_OR_REPLAN_CONTRACT",
            },
            occurred_at=datetime.fromisoformat("2026-04-08T10:00:00+08:00"),
        )
        repository.insert_event(
            connection,
            event_type=EVENT_CIRCUIT_BREAKER_OPENED,
            actor_type="system",
            actor_id="ceo-hire-loop-detector",
            workflow_id=workflow_id,
            idempotency_key="breaker-opened:wf_duplicate_loop_open_incident:hire-loop",
            causation_id=None,
            correlation_id=workflow_id,
            payload={
                "incident_id": "inc_duplicate_loop_open",
                "circuit_breaker_state": "OPEN",
                "fingerprint": (
                    "ceo-hire-loop:"
                    "wf_duplicate_loop_open_incident:STAFFING_REQUIRED:HIRE_EMPLOYEE:"
                    "backend_engineer:backend_engineer_primary:ROLE_ALREADY_COVERED"
                ),
            },
            occurred_at=datetime.fromisoformat("2026-04-08T10:00:01+08:00"),
        )
        repository.refresh_projections(connection)

    snapshot = build_ceo_shadow_snapshot(
        repository,
        workflow_id=workflow_id,
        trigger_type=SCHEDULER_IDLE_MAINTENANCE_TRIGGER,
        trigger_ref="scheduler-runner:test-open-duplicate-loop",
    )

    assert snapshot["controller_state"]["state"] == "WAIT_FOR_INCIDENT"
    assert snapshot["controller_state"]["recommended_action"] == "NO_ACTION"
    assert "recommended_hire" not in snapshot["capability_plan"]
    assert snapshot["capability_plan"]["ceo_hire_loop_summary"] == {
        "has_open_loop_incident": True,
        "incident_id": "inc_duplicate_loop_open",
        "fingerprint": (
            "ceo-hire-loop:"
            "wf_duplicate_loop_open_incident:STAFFING_REQUIRED:HIRE_EMPLOYEE:"
            "backend_engineer:backend_engineer_primary:ROLE_ALREADY_COVERED"
        ),
        "reuse_candidate_employee_id": "emp_backend_loop_reuse",
        "role_type": "backend_engineer",
        "role_profile_refs": ["backend_engineer_primary"],
        "suggested_recovery_action": "REUSE_EXISTING_EMPLOYEE_OR_REPLAN_CONTRACT",
    }


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
    assert [
        item["ticket_payload"]["role_profile_ref"]
        for item in snapshot["capability_plan"]["followup_ticket_plans"]
    ] == [
        "backend_engineer_primary",
        "database_engineer_primary",
    ]
    assert [
        item["ticket_payload"]["workflow_id"]
        for item in snapshot["capability_plan"]["followup_ticket_plans"]
    ] == [
        workflow_id,
        workflow_id,
    ]
    assert snapshot["capability_plan"]["followup_ticket_plans"][0]["blocked_by_plan_keys"] == []
    assert snapshot["capability_plan"]["followup_ticket_plans"][1]["blocked_by_plan_keys"] == ["BR-BE-01"]


def test_controller_waits_when_graph_health_critical_recommends_pause(client, monkeypatch):
    _set_deterministic_mode(client)
    workflow_id = _seed_workflow(
        client,
        "wf_controller_graph_health_wait",
        "Controller should pause fanout while graph health is critical.",
    )
    _persist_workflow_directive_details(
        client.app.state.repository,
        workflow_id,
        workflow_profile="CEO_AUTOPILOT_FINE_GRAINED",
    )
    _seed_board_approved_employee(
        client,
        employee_id="emp_backend_graph_health_wait",
        role_type="backend_engineer",
        role_profile_refs=["backend_engineer_primary"],
    )
    monkeypatch.setattr("app.core.ticket_handlers._trigger_ceo_shadow_safely", lambda *args, **kwargs: None)
    _create_and_complete_minimum_governance_chain(
        client,
        workflow_id=workflow_id,
        ticket_prefix="graph_health_wait",
    )
    _create_and_complete_backlog_recommendation_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_backlog_graph_health_wait",
        node_id="node_ceo_backlog_graph_health_wait",
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
    _seed_closed_persistent_failure_zone_incidents(
        client.app.state.repository,
        workflow_id,
        "node_graph_health_wait_failure_zone",
    )

    snapshot = build_ceo_shadow_snapshot(
        client.app.state.repository,
        workflow_id=workflow_id,
        trigger_type="TICKET_COMPLETED",
        trigger_ref="tkt_backlog_graph_health_wait",
    )

    assert snapshot["projection_snapshot"]["graph_health_report"]["overall_health"] == "CRITICAL"
    assert snapshot["controller_state"]["state"] == "GRAPH_HEALTH_WAIT"
    assert snapshot["controller_state"]["recommended_action"] == "NO_ACTION"
    assert "graph health" in snapshot["controller_state"]["blocking_reason"].lower()


def test_ceo_shadow_snapshot_ignores_noncanonical_backlog_json_artifact(client, monkeypatch):
    _set_deterministic_mode(client)
    workflow_id = _seed_workflow(client, "wf_backlog_canonical_artifact", "Canonical backlog artifact only")
    _persist_workflow_directive_details(
        client.app.state.repository,
        workflow_id,
        workflow_profile="CEO_AUTOPILOT_FINE_GRAINED",
    )
    _seed_board_approved_employee(
        client,
        employee_id="emp_backend_canonical",
        role_type="backend_engineer",
        role_profile_refs=["backend_engineer_primary"],
    )
    monkeypatch.setattr("app.core.ticket_handlers._trigger_ceo_shadow_safely", lambda *args, **kwargs: None)
    _create_and_complete_minimum_governance_chain(
        client,
        workflow_id=workflow_id,
        ticket_prefix="canonical_artifact",
    )
    _create_and_complete_backlog_recommendation_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_backlog_canonical_parent",
        node_id="node_ceo_backlog_canonical",
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
        extra_written_artifacts=[
            {
                "path": "reports/governance/tkt_backlog_canonical_parent/000-decoy.json",
                "artifact_ref": "art://runtime/tkt_backlog_canonical_parent/000-decoy.json",
                "kind": "JSON",
                "content_json": {"note": "decoy json should not become backlog truth"},
            }
        ],
    )

    snapshot = build_ceo_shadow_snapshot(
        client.app.state.repository,
        workflow_id=workflow_id,
        trigger_type="TICKET_COMPLETED",
        trigger_ref="tkt_backlog_canonical_parent",
    )

    assert snapshot["controller_state"]["state"] == "READY_FOR_FANOUT"
    assert snapshot["controller_state"]["recommended_action"] == "CREATE_TICKET"
    assert [item["ticket_key"] for item in snapshot["capability_plan"]["followup_ticket_plans"]] == [
        "BR-BE-01"
    ]
    assert snapshot["capability_plan"]["followup_ticket_plans"][0]["ticket_payload"]["node_id"] == (
        "node_backlog_followup_br_be_01"
    )


def test_trigger_ceo_shadow_with_recovery_opens_incident_when_canonical_backlog_json_is_invalid(
    client,
    monkeypatch,
):
    _set_deterministic_mode(client)
    workflow_id = _seed_workflow(client, "wf_backlog_invalid_json", "Invalid backlog artifact should fail closed")
    _persist_workflow_directive_details(
        client.app.state.repository,
        workflow_id,
        workflow_profile="CEO_AUTOPILOT_FINE_GRAINED",
    )
    _seed_board_approved_employee(
        client,
        employee_id="emp_backend_invalid_json",
        role_type="backend_engineer",
        role_profile_refs=["backend_engineer_primary"],
    )
    monkeypatch.setattr("app.core.ticket_handlers._trigger_ceo_shadow_safely", lambda *args, **kwargs: None)
    _create_and_complete_minimum_governance_chain(
        client,
        workflow_id=workflow_id,
        ticket_prefix="invalid_backlog_json",
    )
    _create_and_complete_backlog_recommendation_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_backlog_invalid_json",
        node_id="node_ceo_backlog_invalid_json",
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

    repository = client.app.state.repository
    backlog_artifact = next(
        item
        for item in repository.list_ticket_artifacts("tkt_backlog_invalid_json")
        if item["artifact_ref"] == "art://runtime/tkt_backlog_invalid_json/backlog_recommendation.json"
    )
    artifact_path = client.app.state.artifact_store.root / backlog_artifact["storage_relpath"]
    artifact_path.write_text("{not-json}", encoding="utf-8")

    run = trigger_ceo_shadow_with_recovery(
        repository,
        workflow_id=workflow_id,
        trigger_type="TICKET_COMPLETED",
        trigger_ref="tkt_backlog_invalid_json",
        idempotency_key_base="test-ceo-shadow-invalid-backlog-json",
    )

    incidents = [
        item
        for item in repository.list_open_incidents()
        if item["workflow_id"] == workflow_id
    ]

    assert run is None
    assert len(incidents) == 1
    assert incidents[0]["incident_type"] == INCIDENT_TYPE_CEO_SHADOW_PIPELINE_FAILED
    assert incidents[0]["payload"]["source_stage"] == "snapshot"
    assert "backlog" in str(incidents[0]["payload"]["error_message"] or "").lower()


def test_ceo_shadow_run_rejects_live_no_action_when_controller_requires_backlog_fanout(client, monkeypatch):
    workflow_id = _seed_workflow(client, "wf_live_backlog_no_action_rejected", "Reject live NO_ACTION during fanout")
    _persist_workflow_directive_details(
        client.app.state.repository,
        workflow_id,
        workflow_profile="CEO_AUTOPILOT_FINE_GRAINED",
    )
    _seed_board_approved_employee(
        client,
        employee_id="emp_backend_no_action",
        role_type="backend_engineer",
        role_profile_refs=["backend_engineer_primary"],
    )
    _set_live_provider(client)
    monkeypatch.setattr("app.core.ticket_handlers._trigger_ceo_shadow_safely", lambda *args, **kwargs: None)
    _create_and_complete_minimum_governance_chain(
        client,
        workflow_id=workflow_id,
        ticket_prefix="live_no_action_rejected",
    )
    _create_and_complete_backlog_recommendation_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_backlog_live_no_action",
        node_id="node_ceo_backlog_live_no_action",
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

    from app.core import ceo_proposer

    def _fake_invoke(_config, _rendered_payload):
        return OpenAICompatProviderResult(
            output_text=json.dumps(
                {
                    "summary": "Do nothing even though implementation fanout is ready.",
                    "actions": [
                        {
                            "action_type": "NO_ACTION",
                            "payload": {
                                "reason": "The workflow can wait.",
                            },
                        }
                    ],
                }
            ),
            response_id="resp_ceo_backlog_no_action_1",
        )

    monkeypatch.setattr(ceo_proposer, "invoke_openai_compat_response", _fake_invoke)

    repository = client.app.state.repository
    run = run_ceo_shadow_for_trigger(
        repository,
        workflow_id=workflow_id,
        trigger_type="TICKET_COMPLETED",
        trigger_ref="tkt_backlog_live_no_action",
        runtime_provider_store=client.app.state.runtime_provider_store,
    )

    assert run["snapshot"]["controller_state"]["state"] == "READY_FOR_FANOUT"
    assert run["snapshot"]["controller_state"]["recommended_action"] == "CREATE_TICKET"
    assert run["deterministic_fallback_used"] is True
    assert "no accepted actions" in run["deterministic_fallback_reason"]
    assert run["accepted_actions"][0]["action_type"] == "CREATE_TICKET"
    assert run["executed_actions"][0]["action_type"] == "CREATE_TICKET"
    assert run["executed_actions"][0]["execution_status"] == "EXECUTED"
    assert run["rejected_actions"][0]["action_type"] == "NO_ACTION"
    assert "controller_state.recommended_action is CREATE_TICKET" in run["rejected_actions"][0]["reason"]


def test_scheduler_does_not_fallback_over_health_gate_no_action(client, monkeypatch):
    workflow_id = _seed_workflow(
        client,
        "wf_scheduler_graph_health_no_action",
        "Scheduler should not override graph health pause.",
    )
    _persist_workflow_directive_details(
        client.app.state.repository,
        workflow_id,
        workflow_profile="CEO_AUTOPILOT_FINE_GRAINED",
    )
    _seed_board_approved_employee(
        client,
        employee_id="emp_backend_graph_health_no_action",
        role_type="backend_engineer",
        role_profile_refs=["backend_engineer_primary"],
    )
    _set_live_provider(client)
    monkeypatch.setattr("app.core.ticket_handlers._trigger_ceo_shadow_safely", lambda *args, **kwargs: None)

    def _fake_snapshot(*_args, **_kwargs):
        return {
            "workflow": {
                "workflow_id": workflow_id,
                "workflow_profile": "CEO_AUTOPILOT_FINE_GRAINED",
                "north_star_goal": "Pause while graph health is critical.",
            },
            "trigger": {"trigger_type": "TICKET_COMPLETED", "trigger_ref": "tkt_backlog_graph_health_no_action"},
            "approvals": [],
            "incidents": [],
            "ticket_summary": {"active_count": 0, "total": 1},
            "nodes": [],
            "employees": [
                {
                    "employee_id": "emp_backend_graph_health_no_action",
                    "state": "ACTIVE",
                    "role_profile_refs": ["backend_engineer_primary"],
                }
            ],
            "projection_snapshot": {
                "graph_health_report": {
                    "overall_health": "CRITICAL",
                    "findings": [
                        {
                            "finding_type": "PERSISTENT_FAILURE_ZONE",
                            "severity": "CRITICAL",
                            "affected_nodes": ["node_scheduler_graph_health_no_action"],
                            "affected_graph_node_ids": [],
                            "metric_value": 3,
                            "threshold": 3,
                            "description": "The graph health gate recommends pausing new fanout.",
                            "suggested_action": (
                                "Pause new fanout and rerun the CEO against the latest graph health snapshot."
                            ),
                        }
                    ],
                    "recommended_actions": [
                        "Pause new fanout and rerun the CEO against the latest graph health snapshot."
                    ],
                },
                "runtime_liveness_report": {"overall_health": "HEALTHY", "findings": [], "recommended_actions": []},
            },
            "replan_focus": {
                "task_sensemaking": {
                    "task_type": "implementation_fanout",
                    "deliverable_kind": "source_code_delivery",
                    "coordination_mode": "fanout",
                    "source_ticket_id": "tkt_backlog_graph_health_no_action",
                },
                "controller_state": {
                    "state": "READY_FOR_FANOUT",
                    "recommended_action": "CREATE_TICKET",
                    "blocking_reason": None,
                },
                "capability_plan": {
                    "followup_ticket_plans": [
                        {
                            "ticket_key": "BR-BE-01",
                            "existing_ticket_id": None,
                            "blocked_by_plan_keys": [],
                            "ticket_payload": {
                                "workflow_id": workflow_id,
                                "node_id": "node_backlog_followup_graph_health_no_action",
                                "role_profile_ref": "backend_engineer_primary",
                                "output_schema_ref": "source_code_delivery",
                                "execution_contract": infer_execution_contract_payload(
                                    role_profile_ref="backend_engineer_primary",
                                    output_schema_ref="source_code_delivery",
                                ),
                                "dispatch_intent": {
                                    "assignee_employee_id": "emp_backend_graph_health_no_action",
                                    "selection_reason": "Translate the approved backlog item into implementation work.",
                                    "dependency_gate_refs": [],
                                },
                                "summary": "BR-BE-01 借阅后端 API 交付。",
                                "parent_ticket_id": "tkt_backlog_graph_health_no_action",
                            },
                        }
                    ]
                },
                "meeting_candidates": [],
            },
        }

    from app.core import ceo_proposer

    def _fake_invoke(_config, _rendered_payload):
        return OpenAICompatProviderResult(
            output_text=json.dumps(
                {
                    "summary": "Graph health is critical, so the CEO waits.",
                    "actions": [
                        {
                            "action_type": "NO_ACTION",
                            "payload": {
                                "reason": "Pause new fanout until graph health recovers.",
                            },
                        }
                    ],
                }
            ),
            response_id="resp_ceo_graph_health_no_action_1",
        )

    monkeypatch.setattr("app.core.ceo_scheduler.build_ceo_shadow_snapshot", _fake_snapshot)
    monkeypatch.setattr(ceo_proposer, "invoke_openai_compat_response", _fake_invoke)

    repository = client.app.state.repository
    run = run_ceo_shadow_for_trigger(
        repository,
        workflow_id=workflow_id,
        trigger_type="TICKET_COMPLETED",
        trigger_ref="tkt_backlog_graph_health_no_action",
        runtime_provider_store=client.app.state.runtime_provider_store,
    )

    assert run["deterministic_fallback_used"] is False
    assert run["accepted_actions"] == []
    assert run["executed_actions"] == []
    assert run["rejected_actions"][0]["action_type"] == "NO_ACTION"
    assert "controller_state.recommended_action is CREATE_TICKET" in run["rejected_actions"][0]["reason"]


def test_backlog_followup_batch_uses_existing_ticket_ids_from_capability_plan_when_node_projection_is_stale(
    client,
):
    _set_deterministic_mode(client)
    workflow_id = _seed_workflow(
        client,
        "wf_backlog_followup_stale_node_projection",
        "Backlog follow-up should keep dependency truth without legacy node projection",
    )
    repository = client.app.state.repository
    _create_ticket_for_test(
        client,
            {
                **_ticket_create_payload(
                    workflow_id=workflow_id,
                    ticket_id="tkt_existing_followup_be",
                    node_id="node_backlog_followup_br_be_01",
                    retry_budget=0,
                ),
                "role_profile_ref": "backend_engineer_primary",
                "output_schema_ref": "source_code_delivery",
            },
        )
    with repository.transaction() as connection:
        connection.execute(
            """
            DELETE FROM node_projection
            WHERE workflow_id = ? AND node_id = ?
            """,
            (workflow_id, "node_backlog_followup_br_be_01"),
        )

    from app.core import ceo_proposer

    batch = ceo_proposer._build_backlog_followup_batch(
        repository,
        {
            "workflow": {"workflow_id": workflow_id},
            "replan_focus": {
                "capability_plan": {
                    "followup_ticket_plans": [
                        {
                            "ticket_key": "BR-BE-01",
                            "existing_ticket_id": "tkt_existing_followup_be",
                            "blocked_by_plan_keys": [],
                            "ticket_payload": {
                                "workflow_id": workflow_id,
                                "node_id": "node_backlog_followup_br_be_01",
                                "role_profile_ref": "backend_engineer_primary",
                                "output_schema_ref": "source_code_delivery",
                                "execution_contract": infer_execution_contract_payload(
                                    role_profile_ref="backend_engineer_primary",
                                    output_schema_ref="source_code_delivery",
                                ),
                                "dispatch_intent": {
                                    "assignee_employee_id": "emp_backend_plan",
                                    "selection_reason": "Translate the approved backlog item into implementation work.",
                                    "dependency_gate_refs": [],
                                },
                                "summary": "BR-BE-01 借阅后端 API 交付；范围：借阅服务、REST API",
                                "parent_ticket_id": "tkt_backlog_parent",
                            },
                        },
                        {
                            "ticket_key": "BR-DB-01",
                            "existing_ticket_id": None,
                            "blocked_by_plan_keys": ["BR-BE-01"],
                            "ticket_payload": {
                                "workflow_id": workflow_id,
                                "node_id": "node_backlog_followup_br_db_01",
                                "role_profile_ref": "database_engineer_primary",
                                "output_schema_ref": "source_code_delivery",
                                "execution_contract": infer_execution_contract_payload(
                                    role_profile_ref="database_engineer_primary",
                                    output_schema_ref="source_code_delivery",
                                ),
                                "dispatch_intent": {
                                    "assignee_employee_id": "emp_database_plan",
                                    "selection_reason": "Translate the approved backlog item into implementation work.",
                                    "dependency_gate_refs": [],
                                },
                                "summary": "BR-DB-01 库存数据库建模；范围：数据库 schema、索引优化",
                                "parent_ticket_id": "tkt_backlog_parent",
                            },
                        },
                    ]
                }
            },
        },
        "Continue the approved backlog fanout.",
    )

    assert batch is not None
    payload = batch.model_dump(mode="json")["actions"][0]["payload"]
    assert payload["node_id"] == "node_backlog_followup_br_db_01"
    assert payload["dispatch_intent"]["dependency_gate_refs"] == ["tkt_existing_followup_be"]
    assert payload["parent_ticket_id"] == "tkt_backlog_parent"


def test_deterministic_fallback_prefers_missing_backlog_followup_over_closeout(client, monkeypatch):
    _set_deterministic_mode(client)
    workflow_id = _seed_workflow(
        client,
        "wf_fallback_prefers_backlog_followup",
        "Fallback should fan out backlog before closeout",
    )
    repository = client.app.state.repository
    _persist_autopilot_workflow_profile(repository, workflow_id)
    _seed_board_approved_employee(
        client,
        employee_id="emp_closeout_frontend",
        role_type="frontend_engineer",
        role_profile_refs=["frontend_engineer_primary"],
    )
    monkeypatch.setattr("app.core.ticket_handlers._trigger_ceo_shadow_safely", lambda *args, **kwargs: None)
    _create_and_complete_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_existing_delivery_parent",
        node_id="node_existing_delivery_parent",
    )

    from app.core import ceo_proposer

    followup_ticket_plans = [
        {
            "ticket_key": f"BR00{index}",
            "existing_ticket_id": f"tkt_completed_br00{index}",
            "blocked_by_plan_keys": [f"BR00{index - 1}"] if index > 1 else [],
            "ticket_payload": {
                "workflow_id": workflow_id,
                "node_id": f"node_backlog_followup_br00{index}",
                "role_profile_ref": "frontend_engineer_primary",
                "output_schema_ref": "source_code_delivery",
                "execution_contract": infer_execution_contract_payload(
                    role_profile_ref="frontend_engineer_primary",
                    output_schema_ref="source_code_delivery",
                ),
                "dispatch_intent": {
                    "assignee_employee_id": "emp_closeout_frontend",
                    "selection_reason": "Translate the approved backlog item into implementation work.",
                    "dependency_gate_refs": [],
                },
                "summary": f"BR00{index} completed backlog follow-up.",
                "parent_ticket_id": "tkt_backlog_parent",
            },
        }
        for index in range(1, 4)
    ]
    followup_ticket_plans.extend(
        {
            "ticket_key": f"BR00{index}",
            "existing_ticket_id": None,
            "blocked_by_plan_keys": [f"BR00{index - 1}"],
            "ticket_payload": {
                "workflow_id": workflow_id,
                "node_id": f"node_backlog_followup_br00{index}",
                "role_profile_ref": "frontend_engineer_primary",
                "output_schema_ref": "source_code_delivery",
                "execution_contract": infer_execution_contract_payload(
                    role_profile_ref="frontend_engineer_primary",
                    output_schema_ref="source_code_delivery",
                ),
                "dispatch_intent": {
                    "assignee_employee_id": "emp_closeout_frontend",
                    "selection_reason": "Translate the approved backlog item into implementation work.",
                    "dependency_gate_refs": [],
                },
                "summary": f"BR00{index} pending backlog follow-up.",
                "parent_ticket_id": "tkt_backlog_parent",
            },
        }
        for index in range(4, 8)
    )
    batch = ceo_proposer.build_deterministic_fallback_batch(
        repository,
        {
            "workflow": {
                "workflow_id": workflow_id,
                "workflow_profile": "CEO_AUTOPILOT_FINE_GRAINED",
                "north_star_goal": "Ship the library workflow.",
            },
            "approvals": [],
            "incidents": [],
            "ticket_summary": {"active_count": 0, "total": 7},
            "nodes": [{"node_id": "node_existing_delivery_parent", "status": "COMPLETED"}],
            "employees": [
                {
                    "employee_id": "emp_closeout_frontend",
                    "state": "ACTIVE",
                    "role_profile_refs": ["frontend_engineer_primary"],
                }
            ],
            "replan_focus": {
                "controller_state": {
                    "state": "READY_FOR_FANOUT",
                    "recommended_action": "CREATE_TICKET",
                    "blocking_reason": None,
                },
                "capability_plan": {
                    "followup_ticket_plans": followup_ticket_plans,
                },
            },
        },
        "Continue the approved backlog fanout.",
    )

    action = batch.model_dump(mode="json")["actions"][0]
    assert action["action_type"] == "CREATE_TICKET"
    assert action["payload"]["node_id"] == "node_backlog_followup_br004"
    assert action["payload"]["node_id"] != "node_ceo_delivery_closeout"
    assert action["payload"]["dispatch_intent"]["dependency_gate_refs"] == ["tkt_completed_br003"]


def test_autopilot_closeout_blocked_by_unmaterialized_followup_plans(client, monkeypatch):
    _set_deterministic_mode(client)
    workflow_id = _seed_workflow(
        client,
        "wf_closeout_blocked_unmaterialized_followups",
        "Closeout should wait for planned follow-up materialization",
    )
    repository = client.app.state.repository
    _persist_autopilot_workflow_profile(repository, workflow_id)
    _seed_board_approved_employee(
        client,
        employee_id="emp_closeout_blocked_frontend",
        role_type="frontend_engineer",
        role_profile_refs=["frontend_engineer_primary"],
    )
    monkeypatch.setattr("app.core.ticket_handlers._trigger_ceo_shadow_safely", lambda *args, **kwargs: None)
    _create_and_complete_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_closeout_blocked_parent",
        node_id="node_closeout_blocked_parent",
    )

    from app.core import ceo_proposer

    batch = ceo_proposer._build_autopilot_closeout_batch(
        repository,
        {
            "workflow": {
                "workflow_id": workflow_id,
                "workflow_profile": "CEO_AUTOPILOT_FINE_GRAINED",
                "north_star_goal": "Do not close out early.",
            },
            "approvals": [],
            "incidents": [],
            "ticket_summary": {"active_count": 0},
            "nodes": [{"node_id": "node_closeout_blocked_parent", "status": "COMPLETED"}],
            "employees": [
                {
                    "employee_id": "emp_closeout_blocked_frontend",
                    "state": "ACTIVE",
                    "role_profile_refs": ["frontend_engineer_primary"],
                }
            ],
            "replan_focus": {
                "capability_plan": {
                    "followup_ticket_plans": [
                        {
                            "ticket_key": "BR004",
                            "existing_ticket_id": None,
                            "blocked_by_plan_keys": ["BR003"],
                            "ticket_payload": {
                                "workflow_id": workflow_id,
                                "node_id": "node_backlog_followup_br004",
                                "role_profile_ref": "frontend_engineer_primary",
                                "output_schema_ref": "source_code_delivery",
                                "execution_contract": infer_execution_contract_payload(
                                    role_profile_ref="frontend_engineer_primary",
                                    output_schema_ref="source_code_delivery",
                                ),
                                "dispatch_intent": {
                                    "assignee_employee_id": "emp_closeout_blocked_frontend",
                                    "selection_reason": "Translate backlog follow-up before closeout.",
                                    "dependency_gate_refs": [],
                                },
                                "summary": "BR004 pending backlog follow-up.",
                                "parent_ticket_id": "tkt_backlog_parent",
                            },
                        }
                    ]
                }
            },
        },
        "Closeout should be blocked.",
    )

    assert batch is None


def test_autopilot_closeout_parent_prefers_checker_handoff_maker_ticket(client, monkeypatch):
    _set_deterministic_mode(client)
    workflow_id = _seed_workflow(
        client,
        "wf_closeout_parent_prefers_checker_handoff",
        "Closeout parent should use the final checked maker ticket",
    )
    repository = client.app.state.repository
    maker_ticket_payload = {
        **_ticket_create_payload(
            workflow_id=workflow_id,
            ticket_id="tkt_checked_maker_delivery",
            node_id="node_checked_delivery",
            retry_budget=0,
        ),
        "output_schema_ref": "source_code_delivery",
    }
    api_test_helpers._seed_created_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_checked_maker_delivery",
        node_id="node_checked_delivery",
        role_profile_ref="frontend_engineer_primary",
        output_schema_ref="source_code_delivery",
    )
    api_test_helpers._seed_created_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_later_unchecked_delivery",
        node_id="node_later_unchecked_delivery",
        role_profile_ref="frontend_engineer_primary",
        output_schema_ref="source_code_delivery",
    )
    checker_ticket_payload = {
        **_ticket_create_payload(
            workflow_id=workflow_id,
            ticket_id="tkt_checked_delivery_checker",
            node_id="node_checked_delivery",
            retry_budget=0,
            role_profile_ref="checker_primary",
            output_schema_ref="maker_checker_verdict",
        )
        ,
        "maker_checker_context": {
            "maker_ticket_id": "tkt_checked_maker_delivery",
            "maker_completed_by": "emp_frontend_2",
            "maker_artifact_refs": [],
            "maker_process_asset_refs": [],
            "maker_ticket_spec": maker_ticket_payload,
            "original_review_request": {
                "review_type": "INTERNAL_DELIVERY_REVIEW",
                "title": "Review checked delivery",
            },
        },
    }
    with repository.transaction() as connection:
        repository.insert_event(
            connection,
            event_type="TICKET_CREATED",
            actor_type="system",
            actor_id="test-seed",
            workflow_id=workflow_id,
            idempotency_key=f"test-seed-ticket-created:{workflow_id}:tkt_checked_delivery_checker",
            causation_id=None,
            correlation_id=workflow_id,
            payload=checker_ticket_payload,
            occurred_at=datetime.fromisoformat("2026-04-25T10:00:00+08:00"),
        )
        repository.refresh_projections(connection)
        connection.execute(
            """
            UPDATE ticket_projection
            SET status = ?,
                updated_at = ?
            WHERE ticket_id IN (?, ?)
            """,
            (
                "COMPLETED",
                "2026-04-25T10:30:00+08:00",
                "tkt_checked_maker_delivery",
                "tkt_checked_delivery_checker",
            ),
        )
        connection.execute(
            """
            UPDATE ticket_projection
            SET status = ?,
                updated_at = ?
            WHERE ticket_id = ?
            """,
            ("COMPLETED", "2026-04-25T23:59:00+08:00", "tkt_later_unchecked_delivery"),
        )

    from app.core import ceo_proposer

    with repository.connection() as connection:
        parent_ticket_id = ceo_proposer._resolve_autopilot_closeout_parent_ticket_id(
            repository,
            workflow_id=workflow_id,
            connection=connection,
        )

    assert parent_ticket_id == "tkt_checked_maker_delivery"


def test_backlog_followup_batch_builds_retry_ticket_for_retryable_existing_ticket(client):
    _set_deterministic_mode(client)
    workflow_id = _seed_workflow(
        client,
        "wf_backlog_followup_retry_existing",
        "Backlog follow-up should retry an existing ticket when recovery is direct.",
    )
    _create_and_fail_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_existing_followup_retryable",
        node_id="node_backlog_followup_br_be_retryable",
        retry_budget=2,
        failure_kind="UPSTREAM_UNAVAILABLE",
        role_profile_ref="backend_engineer_primary",
        output_schema_ref="source_code_delivery",
        leased_by="emp_frontend_2",
    )

    from app.core import ceo_proposer

    batch = ceo_proposer._build_backlog_followup_batch(
        client.app.state.repository,
        {
            "workflow": {"workflow_id": workflow_id},
            "replan_focus": {
                "capability_plan": {
                    "followup_ticket_plans": [
                        {
                            "ticket_key": "BR-BE-RETRY",
                            "existing_ticket_id": "tkt_existing_followup_retryable",
                            "blocked_by_plan_keys": [],
                            "ticket_payload": {
                                "workflow_id": workflow_id,
                                "node_id": "node_backlog_followup_br_be_retryable",
                                "role_profile_ref": "backend_engineer_primary",
                                "output_schema_ref": "source_code_delivery",
                                "execution_contract": infer_execution_contract_payload(
                                    role_profile_ref="backend_engineer_primary",
                                    output_schema_ref="source_code_delivery",
                                ),
                                "dispatch_intent": {
                                    "assignee_employee_id": "emp_backend_plan",
                                    "selection_reason": "Translate the approved backlog item into implementation work.",
                                    "dependency_gate_refs": [],
                                },
                                "summary": "BR-BE-RETRY 借阅后端 API 交付；范围：借阅服务、REST API",
                                "parent_ticket_id": "tkt_backlog_parent_retryable",
                            },
                        }
                    ]
                }
            },
        },
        "Continue the approved backlog fanout.",
    )

    assert batch is not None
    payload = batch.model_dump(mode="json")["actions"][0]["payload"]
    assert batch.model_dump(mode="json")["actions"][0]["action_type"] == "RETRY_TICKET"
    assert payload == {
        "workflow_id": workflow_id,
        "ticket_id": "tkt_existing_followup_retryable",
        "node_id": "node_backlog_followup_br_be_retryable",
        "reason": "Continue approved backlog follow-up by retrying the existing ticket instead of creating a parallel ticket.",
    }


def test_backlog_followup_batch_returns_none_when_all_planned_tickets_already_exist(client):
    _set_deterministic_mode(client)
    workflow_id = _seed_workflow(
        client,
        "wf_backlog_followup_all_existing",
        "Backlog follow-up should not incident when all planned tickets already exist.",
    )
    _create_and_complete_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_existing_followup_done",
        node_id="node_backlog_followup_br_done",
    )

    from app.core import ceo_proposer

    batch = ceo_proposer._build_backlog_followup_batch(
        client.app.state.repository,
        {
            "workflow": {"workflow_id": workflow_id},
            "replan_focus": {
                "capability_plan": {
                    "followup_ticket_plans": [
                        {
                            "ticket_key": "BR-DONE",
                            "existing_ticket_id": "tkt_existing_followup_done",
                            "blocked_by_plan_keys": [],
                            "ticket_payload": {
                                "workflow_id": workflow_id,
                                "node_id": "node_backlog_followup_br_done",
                                "role_profile_ref": "frontend_engineer_primary",
                                "output_schema_ref": "source_code_delivery",
                                "execution_contract": infer_execution_contract_payload(
                                    role_profile_ref="frontend_engineer_primary",
                                    output_schema_ref="source_code_delivery",
                                ),
                                "dispatch_intent": {
                                    "assignee_employee_id": "emp_frontend_2",
                                    "selection_reason": "Translate the approved backlog item into implementation work.",
                                    "dependency_gate_refs": [],
                                },
                                "summary": "BR-DONE completed backlog follow-up.",
                                "parent_ticket_id": "tkt_backlog_parent_done",
                            },
                        }
                    ]
                }
            },
        },
        "Continue the approved backlog fanout.",
    )

    assert batch is None


def test_backlog_followup_batch_uses_completed_attempt_when_latest_existing_ticket_failed(client):
    _set_deterministic_mode(client)
    workflow_id = _seed_workflow(
        client,
        "wf_backlog_followup_completed_before_failed_retry",
        "Backlog follow-up should continue from completed attempt when latest retry failed.",
    )
    node_id = "node_backlog_followup_br_done_then_failed"
    _create_and_complete_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_followup_completed_attempt",
        node_id=node_id,
    )
    _seed_failed_ticket_projection_for_existing_node(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_followup_failed_retry",
        node_id=node_id,
    )

    from app.core import ceo_proposer

    batch = ceo_proposer._build_backlog_followup_batch(
        client.app.state.repository,
        {
            "workflow": {"workflow_id": workflow_id},
            "replan_focus": {
                "capability_plan": {
                    "followup_ticket_plans": [
                        {
                            "ticket_key": "BR-DONE-THEN-FAILED",
                            "existing_ticket_id": "tkt_followup_failed_retry",
                            "blocked_by_plan_keys": [],
                            "ticket_payload": {
                                "workflow_id": workflow_id,
                                "node_id": node_id,
                                "role_profile_ref": "frontend_engineer_primary",
                                "output_schema_ref": "source_code_delivery",
                                "execution_contract": infer_execution_contract_payload(
                                    role_profile_ref="frontend_engineer_primary",
                                    output_schema_ref="source_code_delivery",
                                ),
                                "dispatch_intent": {
                                    "assignee_employee_id": "emp_frontend_2",
                                    "selection_reason": "Translate the approved backlog item into implementation work.",
                                    "dependency_gate_refs": [],
                                },
                                "summary": "BR-DONE-THEN-FAILED completed backlog follow-up.",
                                "parent_ticket_id": "tkt_backlog_parent_done_then_failed",
                            },
                        },
                        {
                            "ticket_key": "BR-NEXT",
                            "existing_ticket_id": None,
                            "blocked_by_plan_keys": ["BR-DONE-THEN-FAILED"],
                            "ticket_payload": {
                                "workflow_id": workflow_id,
                                "node_id": "node_backlog_followup_br_next",
                                "role_profile_ref": "frontend_engineer_primary",
                                "output_schema_ref": "source_code_delivery",
                                "execution_contract": infer_execution_contract_payload(
                                    role_profile_ref="frontend_engineer_primary",
                                    output_schema_ref="source_code_delivery",
                                ),
                                "dispatch_intent": {
                                    "assignee_employee_id": "emp_frontend_2",
                                    "selection_reason": "Translate the approved backlog item into implementation work.",
                                    "dependency_gate_refs": [],
                                },
                                "summary": "BR-NEXT dependent backlog follow-up.",
                                "parent_ticket_id": "tkt_backlog_parent_done_then_failed",
                            },
                        },
                    ]
                }
            },
        },
        "Continue the approved backlog fanout.",
    )

    assert batch is not None
    action = batch.model_dump(mode="json")["actions"][0]
    assert action["action_type"] == "CREATE_TICKET"
    assert action["payload"]["node_id"] == "node_backlog_followup_br_next"
    assert action["payload"]["dispatch_intent"]["dependency_gate_refs"] == ["tkt_followup_completed_attempt"]


def test_backlog_followup_completed_attempt_superseded_by_failed_replacement_does_not_open_downstream(
    client,
):
    _set_deterministic_mode(client)
    workflow_id = _seed_workflow(
        client,
        "wf_backlog_followup_completed_superseded_by_failed_replacement",
        "Backlog follow-up should not reuse a completed attempt superseded by a failed replacement.",
    )
    node_id = "node_backlog_followup_br_superseded"
    _create_and_complete_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_followup_completed_attempt",
        node_id=node_id,
    )
    _seed_failed_ticket_projection_for_existing_node(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_followup_failed_replacement",
        node_id=node_id,
        parent_ticket_id="tkt_followup_completed_attempt",
        failure_kind="WORKSPACE_HOOK_VALIDATION_ERROR",
    )

    from app.core import ceo_proposer

    with pytest.raises(ceo_proposer.CEOProposalContractError) as exc_info:
        ceo_proposer._build_backlog_followup_batch(
            client.app.state.repository,
            {
                "workflow": {"workflow_id": workflow_id},
                "replan_focus": {
                    "capability_plan": {
                        "followup_ticket_plans": [
                            {
                                "ticket_key": "BR-SUPERSEDED",
                                "existing_ticket_id": "tkt_followup_failed_replacement",
                                "blocked_by_plan_keys": [],
                                "ticket_payload": {
                                    "workflow_id": workflow_id,
                                    "node_id": node_id,
                                    "role_profile_ref": "frontend_engineer_primary",
                                    "output_schema_ref": "source_code_delivery",
                                    "execution_contract": infer_execution_contract_payload(
                                        role_profile_ref="frontend_engineer_primary",
                                        output_schema_ref="source_code_delivery",
                                    ),
                                    "dispatch_intent": {
                                        "assignee_employee_id": "emp_frontend_2",
                                        "selection_reason": "Translate the approved backlog item into implementation work.",
                                        "dependency_gate_refs": [],
                                    },
                                    "summary": "BR-SUPERSEDED completed backlog follow-up.",
                                    "parent_ticket_id": "tkt_backlog_parent_superseded",
                                },
                            },
                            {
                                "ticket_key": "BR-NEXT",
                                "existing_ticket_id": None,
                                "blocked_by_plan_keys": ["BR-SUPERSEDED"],
                                "ticket_payload": {
                                    "workflow_id": workflow_id,
                                    "node_id": "node_backlog_followup_br_next_after_superseded",
                                    "role_profile_ref": "frontend_engineer_primary",
                                    "output_schema_ref": "source_code_delivery",
                                    "execution_contract": infer_execution_contract_payload(
                                        role_profile_ref="frontend_engineer_primary",
                                        output_schema_ref="source_code_delivery",
                                    ),
                                    "dispatch_intent": {
                                        "assignee_employee_id": "emp_frontend_2",
                                        "selection_reason": "Translate the approved backlog item into implementation work.",
                                        "dependency_gate_refs": [],
                                    },
                                    "summary": "BR-NEXT dependent backlog follow-up.",
                                    "parent_ticket_id": "tkt_backlog_parent_superseded",
                                },
                            },
                        ]
                    }
                },
            },
            "Continue the approved backlog fanout.",
        )

    error = exc_info.value
    assert error.source_component == "deterministic_fallback.backlog_followup"
    assert error.reason_code == "restore_needed"
    assert error.details["source_ticket_id"] == "tkt_followup_failed_replacement"
    rejection = error.details["completed_ticket_gate_rejection"]
    assert rejection["completed_ticket_id"] == "tkt_followup_completed_attempt"
    assert rejection["terminal_failed_ticket_id"] == "tkt_followup_failed_replacement"
    assert rejection["node_id"] == node_id
    assert rejection["reason_code"] in {
        "completed_ticket_lineage_invalidated",
        "completed_ticket_superseded",
    }


def test_backlog_followup_completed_attempt_still_satisfies_gate_when_failed_retry_is_unrelated(
    client,
):
    _set_deterministic_mode(client)
    workflow_id = _seed_workflow(
        client,
        "wf_backlog_followup_completed_unrelated_failed_retry",
        "Backlog follow-up should reuse completed attempt when failed retry is unrelated noise.",
    )
    node_id = "node_backlog_followup_br_unrelated_failed_retry"
    _create_and_complete_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_followup_completed_attempt",
        node_id=node_id,
    )
    _seed_failed_ticket_projection_for_existing_node(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_followup_failed_retry",
        node_id=node_id,
        failure_kind="PROVIDER_MALFORMED_JSON",
    )

    from app.core import ceo_proposer

    batch = ceo_proposer._build_backlog_followup_batch(
        client.app.state.repository,
        {
            "workflow": {"workflow_id": workflow_id},
            "replan_focus": {
                "capability_plan": {
                    "followup_ticket_plans": [
                        {
                            "ticket_key": "BR-UNRELATED-FAILED-RETRY",
                            "existing_ticket_id": "tkt_followup_failed_retry",
                            "blocked_by_plan_keys": [],
                            "ticket_payload": {
                                "workflow_id": workflow_id,
                                "node_id": node_id,
                                "role_profile_ref": "frontend_engineer_primary",
                                "output_schema_ref": "source_code_delivery",
                                "execution_contract": infer_execution_contract_payload(
                                    role_profile_ref="frontend_engineer_primary",
                                    output_schema_ref="source_code_delivery",
                                ),
                                "dispatch_intent": {
                                    "assignee_employee_id": "emp_frontend_2",
                                    "selection_reason": "Translate the approved backlog item into implementation work.",
                                    "dependency_gate_refs": [],
                                },
                                "summary": "BR-DONE-THEN-NOISY-FAILED completed backlog follow-up.",
                                "parent_ticket_id": "tkt_backlog_parent_unrelated_failed_retry",
                            },
                        },
                        {
                            "ticket_key": "BR-NEXT",
                            "existing_ticket_id": None,
                            "blocked_by_plan_keys": ["BR-UNRELATED-FAILED-RETRY"],
                            "ticket_payload": {
                                "workflow_id": workflow_id,
                                "node_id": "node_backlog_followup_br_next_after_unrelated_failed_retry",
                                "role_profile_ref": "frontend_engineer_primary",
                                "output_schema_ref": "source_code_delivery",
                                "execution_contract": infer_execution_contract_payload(
                                    role_profile_ref="frontend_engineer_primary",
                                    output_schema_ref="source_code_delivery",
                                ),
                                "dispatch_intent": {
                                    "assignee_employee_id": "emp_frontend_2",
                                    "selection_reason": "Translate the approved backlog item into implementation work.",
                                    "dependency_gate_refs": [],
                                },
                                "summary": "BR-NEXT dependent backlog follow-up.",
                                "parent_ticket_id": "tkt_backlog_parent_unrelated_failed_retry",
                            },
                        },
                    ]
                }
            },
        },
        "Continue the approved backlog fanout.",
    )

    assert batch is not None
    action = batch.model_dump(mode="json")["actions"][0]
    assert action["action_type"] == "CREATE_TICKET"
    assert action["payload"]["node_id"] == "node_backlog_followup_br_next_after_unrelated_failed_retry"
    assert action["payload"]["dispatch_intent"]["dependency_gate_refs"] == ["tkt_followup_completed_attempt"]


def test_backlog_followup_batch_raises_structured_restore_needed_for_existing_ticket_without_direct_retry(
    client,
):
    _set_deterministic_mode(client)
    workflow_id = _seed_workflow(
        client,
        "wf_backlog_followup_restore_needed",
        "Backlog follow-up should surface restore-needed details when direct retry is blocked.",
    )
    _create_and_fail_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_existing_followup_restore_needed",
        node_id="node_backlog_followup_br_be_restore_needed",
        retry_budget=0,
        failure_kind="TEST_FAILURE",
        role_profile_ref="backend_engineer_primary",
        output_schema_ref="source_code_delivery",
        leased_by="emp_frontend_2",
    )

    from app.core import ceo_proposer

    with pytest.raises(ceo_proposer.CEOProposalContractError) as exc_info:
        ceo_proposer._build_backlog_followup_batch(
            client.app.state.repository,
            {
                "workflow": {"workflow_id": workflow_id},
                "replan_focus": {
                    "capability_plan": {
                        "followup_ticket_plans": [
                            {
                                "ticket_key": "BR-BE-RESTORE",
                                "existing_ticket_id": "tkt_existing_followup_restore_needed",
                                "blocked_by_plan_keys": [],
                                "ticket_payload": {
                                    "workflow_id": workflow_id,
                                    "node_id": "node_backlog_followup_br_be_restore_needed",
                                    "role_profile_ref": "backend_engineer_primary",
                                    "output_schema_ref": "source_code_delivery",
                                    "execution_contract": infer_execution_contract_payload(
                                        role_profile_ref="backend_engineer_primary",
                                        output_schema_ref="source_code_delivery",
                                    ),
                                    "dispatch_intent": {
                                        "assignee_employee_id": "emp_backend_plan",
                                        "selection_reason": "Translate the approved backlog item into implementation work.",
                                        "dependency_gate_refs": [],
                                    },
                                    "summary": "BR-BE-RESTORE 借阅后端 API 交付；范围：借阅服务、REST API",
                                    "parent_ticket_id": "tkt_backlog_parent_restore_needed",
                                },
                            }
                        ]
                    }
                },
            },
            "Continue the approved backlog fanout.",
        )

    error = exc_info.value
    assert error.source_component == "deterministic_fallback.backlog_followup"
    assert error.reason_code == "restore_needed"
    assert error.details == {
        "source_ticket_id": "tkt_existing_followup_restore_needed",
        "node_id": "node_backlog_followup_br_be_restore_needed",
        "ticket_key": "BR-BE-RESTORE",
        "source_ticket_status": "FAILED",
        "failure_kind": "TEST_FAILURE",
        "recommended_followup_action": "RESTORE_AND_RETRY_LATEST_FAILURE",
    }


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
    assert required_plan["existing_ticket_id"] is None
    assert required_plan["ticket_payload"] == {
        "workflow_id": workflow_id,
        "node_id": "node_architect_governance_gate_node_ceo_backlog_architect_doc_gap",
        "role_profile_ref": "architect_primary",
        "output_schema_ref": ARCHITECTURE_BRIEF_SCHEMA_REF,
        "execution_contract": infer_execution_contract_payload(
            role_profile_ref="architect_primary",
            output_schema_ref=ARCHITECTURE_BRIEF_SCHEMA_REF,
        ),
        "dispatch_intent": {
            "assignee_employee_id": "emp_architect_doc_gap",
            "selection_reason": "Satisfy the current architect governance gate before implementation fanout continues.",
            "dependency_gate_refs": [],
            "selected_by": "ceo",
            "wakeup_policy": "default",
        },
        "summary": "Prepare the architect governance brief before implementation fanout continues.",
        "parent_ticket_id": "tkt_backlog_architect_doc_gap",
    }


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
    assert required_plan["ticket_payload"]["output_schema_ref"] == TECHNOLOGY_DECISION_SCHEMA_REF
    assert required_plan["ticket_payload"]["parent_ticket_id"] == "tkt_parent_architecture_doc"
    assert required_plan["ticket_payload"]["dispatch_intent"]["dependency_gate_refs"] == ["tkt_parent_architecture_doc"]


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
    assert required_plan["ticket_payload"]["output_schema_ref"] == DETAILED_DESIGN_SCHEMA_REF
    assert required_plan["ticket_payload"]["parent_ticket_id"] == "tkt_parent_milestone_plan"
    assert required_plan["ticket_payload"]["dispatch_intent"]["dependency_gate_refs"] == [
        "tkt_parent_architecture_doc",
        "tkt_parent_technology_decision",
        "tkt_parent_milestone_plan",
    ]


def test_ceo_shadow_snapshot_keeps_existing_governance_ticket_plan_when_node_projection_is_stale(
    client,
    monkeypatch,
):
    _set_deterministic_mode(client)
    workflow_id = _seed_workflow(
        client,
        "wf_governance_existing_ticket_stale_node_projection",
        "Governance existing ticket should stay visible through graph truth",
    )
    repository = client.app.state.repository
    _persist_workflow_directive_details(
        repository,
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
    _create_ticket_for_test(
        client,
            {
                **_ticket_create_payload(
                    workflow_id=workflow_id,
                    ticket_id="tkt_pending_technology_decision",
                    node_id="node_ceo_technology_decision",
                    role_profile_ref="frontend_engineer_primary",
                    output_schema_ref=TECHNOLOGY_DECISION_SCHEMA_REF,
                    retry_budget=0,
                ),
                "allowed_write_set": ["reports/governance/tkt_pending_technology_decision/*"],
            },
    )
    with repository.transaction() as connection:
        connection.execute(
            """
            DELETE FROM node_projection
            WHERE workflow_id = ? AND node_id = ?
            """,
            (workflow_id, "node_ceo_technology_decision"),
        )

    snapshot = build_ceo_shadow_snapshot(
        repository,
        workflow_id=workflow_id,
        trigger_type="TICKET_COMPLETED",
        trigger_ref="tkt_parent_architecture_doc",
    )
    required_plan = snapshot["capability_plan"]["required_governance_ticket_plan"]

    assert snapshot["task_sensemaking"]["task_type"] == "governance_followup"
    assert snapshot["controller_state"]["state"] == "READY_TICKET"
    assert required_plan["ticket_payload"]["output_schema_ref"] == TECHNOLOGY_DECISION_SCHEMA_REF
    assert required_plan["existing_ticket_id"] == "tkt_pending_technology_decision"


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
    _set_live_provider(client)
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

    from app.core import ceo_proposer

    def _fake_invoke(_config, rendered_payload):
        snapshot = rendered_payload.messages[2].content_payload
        recommended_action = snapshot["controller_state"]["recommended_action"]
        if recommended_action == "HIRE_EMPLOYEE":
            recommended_hire = snapshot["capability_plan"]["recommended_hire"]
            return OpenAICompatProviderResult(
                output_text=json.dumps(
                    {
                        "summary": "Hire one architect before delivery fanout resumes.",
                        "actions": [
                            {
                                "action_type": "HIRE_EMPLOYEE",
                                "payload": {
                                    "workflow_id": workflow_id,
                                    "role_type": recommended_hire["role_type"],
                                    "role_profile_refs": recommended_hire["role_profile_refs"],
                                    "request_summary": recommended_hire["request_summary"],
                                    "employee_id_hint": "emp_architect_governance",
                                },
                            }
                        ],
                    }
                ),
                response_id="resp_ceo_architect_hire_1",
            )
        required_plan = snapshot["capability_plan"]["required_governance_ticket_plan"]
        assert required_plan is not None
        ticket_payload = required_plan["ticket_payload"]
        return OpenAICompatProviderResult(
            output_text=json.dumps(
                {
                    "summary": "Create the architect governance brief before implementation fanout resumes.",
                    "actions": [
                        {
                            "action_type": "CREATE_TICKET",
                            "payload": ticket_payload,
                        }
                    ],
                }
            ),
            response_id="resp_ceo_architect_hire_followup_1",
        )

    monkeypatch.setattr(ceo_proposer, "invoke_openai_compat_response", _fake_invoke)

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
    assert run["executed_actions"][0]["causation_hint"] == "employee:emp_architect_governance"
    assert run["executed_actions"][0]["payload"]["role_profile_refs"] == ["architect_primary"]
    assert not any(
        approval["approval_type"] == "CORE_HIRE_APPROVAL"
        for approval in client.app.state.repository.list_open_approvals()
        if approval["workflow_id"] == workflow_id
    )
    hired_employee = client.app.state.repository.get_employee_projection("emp_architect_governance")
    assert hired_employee is not None
    assert hired_employee["state"] == "ACTIVE"
    assert hired_employee["board_approved"] is True

    followup_run = run_ceo_shadow_for_trigger(
        client.app.state.repository,
        workflow_id=workflow_id,
        trigger_type="MANUAL_TEST",
        trigger_ref="manual:post-hire",
    )

    assert followup_run["snapshot"]["controller_state"]["state"] == "ARCHITECT_REQUIRED"
    assert followup_run["snapshot"]["controller_state"]["recommended_action"] == "CREATE_TICKET"
    assert followup_run["accepted_actions"][0]["action_type"] == "CREATE_TICKET"
    assert followup_run["executed_actions"][0]["action_type"] == "CREATE_TICKET"
    assert followup_run["executed_actions"][0]["execution_status"] == "EXECUTED"


@pytest.mark.parametrize("target_role", ["cto", "governance_cto", "cto_primary"])
def test_ceo_shadow_snapshot_uses_existing_cto_for_backlog_governance_followup(
    client,
    monkeypatch,
    target_role,
):
    workflow_id = _seed_workflow(client, "wf_backlog_cto_existing_staff", "Reuse existing CTO")
    _persist_workflow_directive_details(
        client.app.state.repository,
        workflow_id,
        workflow_profile="CEO_AUTOPILOT_FINE_GRAINED",
        hard_constraints=["现有 CTO 治理角色可承接 backlog fanout traceability。"],
    )
    _seed_board_approved_employee(
        client,
        employee_id="emp_cto_governance",
        role_type="governance_cto",
        role_profile_refs=["cto_primary"],
    )
    monkeypatch.setattr("app.core.ticket_handlers._trigger_ceo_shadow_safely", lambda *args, **kwargs: None)
    _create_and_complete_minimum_governance_chain(
        client,
        workflow_id=workflow_id,
        ticket_prefix="cto_existing_staff",
    )
    _create_and_complete_backlog_recommendation_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_backlog_cto_existing_staff",
        node_id="node_ceo_backlog_cto_existing_staff",
        tickets=[
            {
                "ticket_id": "BR-GOV-001",
                "name": "Governance fanout and traceability setup",
                "priority": "P0",
                "target_role": target_role,
                "scope": ["Record PRD traceability and handoff IDs without implementation code."],
            }
        ],
        dependency_graph=[
            {"ticket_id": "BR-GOV-001", "depends_on": [], "reason": "Governance traceability starts fanout."},
        ],
        recommended_sequence=[
            "BR-GOV-001 Governance fanout and traceability setup",
        ],
    )

    snapshot = build_ceo_shadow_snapshot(
        client.app.state.repository,
        workflow_id=workflow_id,
        trigger_type="TICKET_COMPLETED",
        trigger_ref="tkt_backlog_cto_existing_staff",
    )

    assert snapshot["controller_state"]["state"] == "READY_FOR_FANOUT"
    assert snapshot["controller_state"]["recommended_action"] == "CREATE_TICKET"
    assert snapshot["capability_plan"]["staffing_gaps"] == []
    followup_plan = snapshot["capability_plan"]["followup_ticket_plans"][0]
    ticket_payload = followup_plan["ticket_payload"]
    assert ticket_payload["role_profile_ref"] == "cto_primary"
    assert ticket_payload["output_schema_ref"] == BACKLOG_RECOMMENDATION_SCHEMA_REF
    assert ticket_payload["execution_contract"]["execution_target_ref"] == "execution_target:cto_governance_document"
    assert ticket_payload["dispatch_intent"]["assignee_employee_id"] == "emp_cto_governance"


@pytest.mark.parametrize("target_role", ["cto", "governance_cto", "cto_primary"])
def test_backlog_followup_execution_plan_resolves_cto_governance_contract(target_role):
    from app.core import workflow_controller

    result = workflow_controller._resolve_backlog_followup_execution_plan(
        {"ticket_id": "BR-GOV-001", "target_role": target_role}
    )

    assert result["ok"] is True
    assert result["role_profile_ref"] == "cto_primary"
    assert result["output_schema_ref"] == BACKLOG_RECOMMENDATION_SCHEMA_REF
    assert result["execution_contract"]["execution_target_ref"] == "execution_target:cto_governance_document"
    assert result["execution_target_ref"] == "execution_target:cto_governance_document"
    assert result["deliverable_kind"] == BACKLOG_RECOMMENDATION_SCHEMA_REF


def test_backlog_followup_execution_plan_rejects_unsupported_target_role():
    from app.core import workflow_controller

    result = workflow_controller._resolve_backlog_followup_execution_plan(
        {"ticket_id": "BR-PM-001", "target_role": "product_manager"}
    )

    assert result == {
        "ok": False,
        "reason_code": "unsupported_target_role",
        "target_role": "product_manager",
        "role_profile_ref": "",
        "output_schema_ref": "",
    }


def test_backlog_followup_execution_plan_rejects_role_schema_mismatch():
    from app.core import workflow_controller

    result = workflow_controller._resolve_backlog_followup_execution_plan(
        {
            "ticket_id": "BR-GOV-001",
            "target_role": "cto",
            "output_schema_ref": "source_code_delivery",
        }
    )

    assert result["ok"] is False
    assert result["reason_code"] == "unsupported_role_schema_combo"
    assert result["role_profile_ref"] == "cto_primary"
    assert result["output_schema_ref"] == "source_code_delivery"


def test_backlog_followup_execution_plan_rejects_missing_execution_contract(monkeypatch):
    from app.core import workflow_controller

    monkeypatch.setattr(workflow_controller, "infer_execution_contract_payload", lambda **_kwargs: None)

    result = workflow_controller._resolve_backlog_followup_execution_plan(
        {"ticket_id": "BR-BE-001", "target_role": "backend_engineer"}
    )

    assert result["ok"] is False
    assert result["reason_code"] == "execution_contract_missing"
    assert result["role_profile_ref"] == "backend_engineer_primary"
    assert result["output_schema_ref"] == "source_code_delivery"


def test_ceo_shadow_run_creates_architect_governance_ticket_before_backlog_followup_when_doc_is_missing(
    client,
    monkeypatch,
):
    _set_live_provider(client)
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

    from app.core import ceo_proposer

    def _fake_invoke(_config, rendered_payload):
        snapshot = rendered_payload.messages[2].content_payload
        required_plan = snapshot["capability_plan"]["required_governance_ticket_plan"]
        assert required_plan is not None
        ticket_payload = required_plan["ticket_payload"]
        return OpenAICompatProviderResult(
            output_text=json.dumps(
                {
                    "summary": "Create the architect governance brief before implementation fanout resumes.",
                    "actions": [
                        {
                            "action_type": "CREATE_TICKET",
                            "payload": ticket_payload,
                        }
                    ],
                }
            ),
            response_id="resp_ceo_architect_doc_ticket_1",
        )

    monkeypatch.setattr(ceo_proposer, "invoke_openai_compat_response", _fake_invoke)

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
    _set_live_provider(client)
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

    from app.core import ceo_proposer

    def _fake_invoke(_config, rendered_payload):
        snapshot = rendered_payload.messages[2].content_payload
        candidate = next(
            item
            for item in snapshot["meeting_candidates"]
            if item["source_ticket_id"] == "tkt_backlog_meeting_parent" and item["eligible"] is True
        )
        return OpenAICompatProviderResult(
            output_text=json.dumps(
                {
                    "summary": "Open the required technical decision meeting before implementation fanout.",
                    "actions": [
                        {
                            "action_type": "REQUEST_MEETING",
                            "payload": {
                                "workflow_id": workflow_id,
                                "meeting_type": "TECHNICAL_DECISION",
                                "source_graph_node_id": candidate["source_graph_node_id"],
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
            response_id="resp_ceo_meeting_gate_1",
        )

    monkeypatch.setattr(ceo_proposer, "invoke_openai_compat_response", _fake_invoke)

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
                            **required_plan["ticket_payload"],
                            "dispatch_intent": {
                                **required_plan["ticket_payload"]["dispatch_intent"],
                                "selection_reason": "Follow the required architect governance ticket plan exactly.",
                            },
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


@pytest.mark.parametrize(
    ("payload", "reason_code"),
    [
        (
            {
                "summary": "Create the next governance ticket.",
                "actions": [
                    {
                        "action_type": "CREATE_TICKET",
                        "payload": {
                            "workflow_id": "wf_demo",
                            "node_id": "node_ceo_architecture_brief",
                            "role_profile_ref": "architect_primary",
                            "output_schema_ref": "architecture_brief",
                            "execution_contract": {
                                "execution_target_ref": "execution_target:architect_governance_document",
                                "required_capability_tags": ["structured_output", "planning"],
                                "runtime_contract_version": "execution_contract_v1",
                            },
                            "dispatch_intent": {
                                "assignee_employee_id": "emp_architect_governance",
                                "dependency_gate_refs": ["tkt_seed_parent"],
                            },
                            "summary": "Create architecture brief ticket.",
                            "parent_ticket_id": None,
                        },
                    }
                ],
            },
            "payload_validation_failed",
        ),
        (
            {
                "summary": "Create the next governance ticket.",
                "actions": [
                    {
                        "action_type": "CREATE_TICKET",
                        "payload": {
                            "workflow_id": "wf_demo",
                            "node_id": "node_ceo_architecture_brief",
                            "role_profile_ref": "architect_primary",
                            "output_schema_ref": "architecture_brief",
                            "execution_contract": {
                                "contract_kind": "GOVERNANCE_DOCUMENT",
                                "role_profile_ref": "architect_primary",
                                "output_schema_ref": "architecture_brief",
                            },
                            "dispatch_intent": {
                                "assignee_employee_id": "emp_architect_governance",
                                "selection_reason": "Use the architect governance owner.",
                                "dependency_gate_refs": ["tkt_seed_parent"],
                            },
                            "summary": "Create architecture brief ticket.",
                            "parent_ticket_id": None,
                        },
                    }
                ],
            },
            "payload_validation_failed",
        ),
    ],
)
def test_provider_action_batch_rejects_legacy_or_incomplete_create_ticket_payload(payload, reason_code):
    from app.core import ceo_proposer

    with pytest.raises(ceo_proposer.CEOProposalContractError) as exc_info:
        ceo_proposer._normalize_provider_action_batch_payload(payload)

    assert exc_info.value.source_component == "provider_action_batch"
    assert exc_info.value.reason_code == reason_code


def test_ceo_shadow_live_provider_requests_non_strict_ceo_action_batch_schema(client, monkeypatch):
    _set_live_provider(client)
    workflow_id = _project_init(client, "CEO strict schema request")

    from app.core import ceo_proposer

    def _fake_invoke(config, _rendered_payload):
        assert config.schema_name == "ceo_action_batch"
        assert config.strict is False
        assert isinstance(config.schema_body, dict)
        assert config.schema_body["type"] == "object"
        return OpenAICompatProviderResult(
            output_text=json.dumps(
                {
                    "summary": "Stay idle for this schema verification round.",
                    "actions": [
                        {
                            "action_type": "NO_ACTION",
                            "payload": {"reason": "Schema wiring verified."},
                        }
                    ],
                }
            ),
            response_id="resp_ceo_strict_schema_1",
        )

    monkeypatch.setattr(ceo_proposer, "invoke_openai_compat_response", _fake_invoke)

    run = run_ceo_shadow_for_trigger(
        client.app.state.repository,
        workflow_id=workflow_id,
        trigger_type="MANUAL_TEST",
        trigger_ref="manual:strict-schema",
        runtime_provider_store=client.app.state.runtime_provider_store,
    )

    assert run["accepted_actions"][0]["action_type"] == "NO_ACTION"
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
                                "source_graph_node_id": candidate["source_graph_node_id"],
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


def test_ceo_validator_rejects_request_meeting_when_source_graph_node_id_mismatches_snapshot_candidate(client):
    _set_deterministic_mode(client)
    workflow_id = _seed_workflow(client, "wf_ceo_meeting_validator_graph_guard")
    _create_and_fail_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_ceo_validator_meeting_source",
        node_id="node_ceo_validator_meeting_source",
        retry_budget=0,
    )

    snapshot = next(
        run["snapshot"]
        for run in client.app.state.repository.list_ceo_shadow_runs(workflow_id)
        if run["trigger_type"] == "TICKET_FAILED"
    )
    candidate = next(
        item
        for item in snapshot["meeting_candidates"]
        if item["source_ticket_id"] == "tkt_ceo_validator_meeting_source"
    )

    result = validate_ceo_action_batch(
        client.app.state.repository,
        snapshot=snapshot,
        action_batch=CEOActionBatch.model_validate(
            {
                "summary": "Request a bounded technical decision meeting.",
                "actions": [
                    {
                        "action_type": "REQUEST_MEETING",
                        "payload": {
                            "workflow_id": workflow_id,
                            "meeting_type": "TECHNICAL_DECISION",
                            "source_graph_node_id": "node_ceo_validator_meeting_source::wrong",
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
    )

    assert result["accepted_actions"] == []
    assert "does not match any snapshot meeting candidate" in result["rejected_actions"][0]["reason"]


def test_ceo_validator_accepts_request_meeting_without_source_node_id_when_graph_truth_matches(client):
    _set_deterministic_mode(client)
    workflow_id = _seed_workflow(client, "wf_ceo_meeting_validator_optional_source_node")
    _create_and_fail_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_ceo_validator_optional_source_node",
        node_id="node_ceo_validator_optional_source_node",
        retry_budget=0,
    )

    snapshot = next(
        run["snapshot"]
        for run in client.app.state.repository.list_ceo_shadow_runs(workflow_id)
        if run["trigger_type"] == "TICKET_FAILED"
    )
    candidate = next(
        item
        for item in snapshot["meeting_candidates"]
        if item["source_ticket_id"] == "tkt_ceo_validator_optional_source_node"
    )

    result = validate_ceo_action_batch(
        client.app.state.repository,
        snapshot=snapshot,
        action_batch=CEOActionBatch.model_validate(
            {
                "summary": "Request a bounded technical decision meeting.",
                "actions": [
                    {
                        "action_type": "REQUEST_MEETING",
                        "payload": {
                            "workflow_id": workflow_id,
                            "meeting_type": "TECHNICAL_DECISION",
                            "source_graph_node_id": candidate["source_graph_node_id"],
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
    )

    assert len(result["accepted_actions"]) == 1
    assert result["rejected_actions"] == []


def test_ceo_request_meeting_batch_omits_source_node_id_payload(client):
    _set_deterministic_mode(client)
    workflow_id = _seed_workflow(client, "wf_ceo_meeting_payload_graph_only")
    _create_and_fail_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_ceo_meeting_payload_graph_only",
        node_id="node_ceo_meeting_payload_graph_only",
        retry_budget=0,
    )

    snapshot = next(
        run["snapshot"]
        for run in client.app.state.repository.list_ceo_shadow_runs(workflow_id)
        if run["trigger_type"] == "TICKET_FAILED"
    )
    candidate = next(
        item
        for item in snapshot["meeting_candidates"]
        if item["source_ticket_id"] == "tkt_ceo_meeting_payload_graph_only"
    )

    from app.core.ceo_proposer import _build_request_meeting_batch

    batch = _build_request_meeting_batch(
        {
            **candidate,
            "workflow_id": workflow_id,
        },
        reason="Open one bounded technical decision meeting because the snapshot exposes a single eligible candidate.",
    )

    payload = batch.actions[0].payload.model_dump(mode="json")

    assert payload["source_graph_node_id"] == candidate["source_graph_node_id"]
    assert payload["source_ticket_id"] == candidate["source_ticket_id"]
    assert "source_node_id" not in payload


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


def test_ceo_shadow_snapshot_exposes_latest_board_advisory_decision(client, monkeypatch):
    workflow_id = "wf_ceo_advisory_snapshot"
    _seed_workflow(client, workflow_id, "CEO advisory snapshot")
    approval = api_test_helpers._seed_review_request(client, workflow_id=workflow_id)
    api_test_helpers._seed_worker(
        client,
        employee_id="emp_cto_advisory_snapshot",
        role_type="cto",
        provider_id="",
        role_profile_refs=["cto_primary"],
    )
    _set_live_provider(client)

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

    proposal_payload = {
        "proposal_ref": f"pa://graph-patch-proposal/{advisory_session['session_id']}@1",
        "workflow_id": workflow_id,
        "session_id": advisory_session["session_id"],
        "base_graph_version": advisory_session["source_version"],
        "proposal_summary": "Freeze the current execution node until the advisory decision lands.",
        "impact_summary": "Keep the graph aligned with the latest board decision.",
        "freeze_node_ids": ["node_homepage_visual"],
        "source_decision_pack_ref": advisory_session["decision_pack_refs"][0],
        "proposal_hash": "hash-ceo-advisory-snapshot",
    }
    with patch(
        "app.core.board_advisory_analysis.invoke_openai_compat_response",
        return_value=OpenAICompatProviderResult(
            output_text=json.dumps(proposal_payload),
            response_id="resp_ceo_advisory_snapshot",
        ),
    ):
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


def test_ceo_shadow_prompt_mentions_latest_board_advisory_decision(client, monkeypatch):
    workflow_id = "wf_ceo_advisory_prompt"
    _seed_workflow(client, workflow_id, "CEO advisory prompt")
    approval = api_test_helpers._seed_review_request(client, workflow_id=workflow_id)
    api_test_helpers._seed_worker(
        client,
        employee_id="emp_cto_advisory_prompt",
        role_type="cto",
        provider_id="",
        role_profile_refs=["cto_primary"],
    )
    _set_live_provider(client)

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

    proposal_payload = {
        "proposal_ref": f"pa://graph-patch-proposal/{advisory_session['session_id']}@1",
        "workflow_id": workflow_id,
        "session_id": advisory_session["session_id"],
        "base_graph_version": advisory_session["source_version"],
        "proposal_summary": "Escalate the next step through the advisory decision baseline.",
        "impact_summary": "Keep the prompt aligned with the latest board decision.",
        "freeze_node_ids": ["node_homepage_visual"],
        "source_decision_pack_ref": advisory_session["decision_pack_refs"][0],
        "proposal_hash": "hash-ceo-advisory-prompt",
    }
    with patch(
        "app.core.board_advisory_analysis.invoke_openai_compat_response",
        return_value=OpenAICompatProviderResult(
            output_text=json.dumps(proposal_payload),
            response_id="resp_ceo_advisory_prompt",
        ),
    ):
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


def test_ceo_shadow_snapshot_exposes_full_timeline_archive_refs_for_applied_advisory_session(client, monkeypatch):
    workflow_id = "wf_ceo_advisory_timeline_refs"
    _seed_workflow(client, workflow_id, "CEO advisory timeline refs")
    approval = api_test_helpers._seed_review_request(client, workflow_id=workflow_id)
    api_test_helpers._seed_worker(
        client,
        employee_id="emp_cto_advisory_timeline_refs",
        role_type="cto",
        provider_id="",
        role_profile_refs=["cto_primary"],
    )
    _set_live_provider(client)

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

    proposal_payload = {
        "proposal_ref": f"pa://graph-patch-proposal/{advisory_session['session_id']}@1",
        "workflow_id": workflow_id,
        "session_id": advisory_session["session_id"],
        "base_graph_version": advisory_session["source_version"],
        "proposal_summary": "Persist the advisory decision with full timeline refs.",
        "impact_summary": "Freeze the current execution node while the archived advisory path is applied.",
        "freeze_node_ids": ["node_homepage_visual"],
        "source_decision_pack_ref": advisory_session["decision_pack_refs"][0],
        "proposal_hash": "hash-ceo-advisory-timeline-refs",
    }
    with patch(
        "app.core.board_advisory_analysis.invoke_openai_compat_response",
        return_value=OpenAICompatProviderResult(
            output_text=json.dumps(proposal_payload),
            response_id="resp_ceo_advisory_timeline_refs",
        ),
    ):
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
    assert "runtime_liveness_report" in prompt


def test_recent_failures_are_exposed_in_snapshot(client):
    _set_deterministic_mode(client)
    workflow_id = _seed_workflow(client, "wf_ceo_recent_failures", "CEO recent failures")
    import app.core.ticket_handlers as ticket_handlers

    monkeypatch = patch.object(ticket_handlers, "run_ceo_shadow_for_trigger", lambda *args, **kwargs: None)
    monkeypatch.start()
    try:
        _create_and_fail_ticket(
            client,
            workflow_id=workflow_id,
            ticket_id="tkt_ceo_recent_failure",
            node_id="node_ceo_recent_failure",
            retry_budget=2,
            failure_kind="UPSTREAM_UNAVAILABLE",
            failure_message="The upstream provider stalled before the response completed.",
        )
    finally:
        monkeypatch.stop()

    snapshot = build_ceo_shadow_snapshot(
        client.app.state.repository,
        workflow_id=workflow_id,
        trigger_type="MANUAL_TEST",
        trigger_ref="manual:recent-failures",
    )

    recent_failure = snapshot["replan_focus"]["recent_failures"][0]

    assert recent_failure["ticket_id"] == "tkt_ceo_recent_failure"
    assert recent_failure["node_id"] == "node_ceo_recent_failure"
    assert recent_failure["status"] == "FAILED"
    assert recent_failure["failure_kind"] == "UPSTREAM_UNAVAILABLE"
    assert recent_failure["failure_message"] == "The upstream provider stalled before the response completed."
    assert recent_failure["retry_count"] == 0
    assert recent_failure["retry_budget"] == 2
    assert recent_failure["updated_at"] is not None


def test_recent_failures_are_mentioned_in_prompt(client):
    _set_deterministic_mode(client)
    workflow_id = _seed_workflow(client, "wf_ceo_recent_failures_prompt", "CEO recent failures prompt")
    import app.core.ticket_handlers as ticket_handlers

    monkeypatch = patch.object(ticket_handlers, "run_ceo_shadow_for_trigger", lambda *args, **kwargs: None)
    monkeypatch.start()
    try:
        _create_and_fail_ticket(
            client,
            workflow_id=workflow_id,
            ticket_id="tkt_ceo_recent_failure_prompt",
            node_id="node_ceo_recent_failure_prompt",
            retry_budget=0,
            failure_kind="TEST_FAILURE",
            failure_message="The checker rejected the current implementation twice.",
        )
    finally:
        monkeypatch.stop()

    snapshot = build_ceo_shadow_snapshot(
        client.app.state.repository,
        workflow_id=workflow_id,
        trigger_type="MANUAL_TEST",
        trigger_ref="manual:recent-failures-prompt",
    )
    prompt = build_ceo_shadow_system_prompt(snapshot)

    assert "recent_failures" in prompt
    assert "TEST_FAILURE" in prompt
    assert "The checker rejected the current implementation twice." in prompt


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


def test_ceo_shadow_snapshot_exposes_queue_starvation_finding(client, monkeypatch):
    workflow_id = "wf_ceo_graph_health_queue_starvation"
    _seed_workflow(client, workflow_id, "CEO graph health queue starvation prompt")
    api_test_helpers._seed_created_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_ceo_graph_health_queue_starvation",
        node_id="node_ceo_graph_health_queue_starvation",
        role_profile_ref="frontend_engineer_primary",
        output_schema_ref="source_code_delivery",
        delivery_stage="BUILD",
    )
    monkeypatch.setattr(
        graph_health_module,
        "now_local",
        lambda: datetime.fromisoformat("2026-04-16T13:00:00+08:00"),
    )
    repository = client.app.state.repository
    with repository.transaction() as connection:
        connection.execute(
            """
            UPDATE ticket_projection
            SET updated_at = ?
            WHERE ticket_id = ?
            """,
            ("2026-04-16T09:00:00+08:00", "tkt_ceo_graph_health_queue_starvation"),
        )

    snapshot = build_ceo_shadow_snapshot(
        repository,
        workflow_id=workflow_id,
        trigger_type="MANUAL_TEST",
        trigger_ref="manual:ceo-graph-health-queue-starvation",
    )
    prompt = build_ceo_shadow_system_prompt(snapshot)
    graph_health_findings = snapshot["projection_snapshot"]["graph_health_report"]["findings"]
    runtime_liveness_findings = snapshot["projection_snapshot"]["runtime_liveness_report"]["findings"]
    finding_types = [item["finding_type"] for item in runtime_liveness_findings]
    queue_starvation_finding = next(
        item for item in runtime_liveness_findings if item["finding_type"] == "QUEUE_STARVATION"
    )

    assert "QUEUE_STARVATION" in finding_types
    assert "QUEUE_STARVATION" not in [
        item["finding_type"] for item in graph_health_findings
    ]
    assert queue_starvation_finding["affected_graph_node_ids"] == [
        "node_ceo_graph_health_queue_starvation"
    ]
    assert "QUEUE_STARVATION" in prompt


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


def test_idle_ceo_maintenance_targets_controller_action_even_without_idle_signal(monkeypatch):
    workflow_id = "wf_idle_controller_action"

    class _Repository:
        def list_workflow_projections(self):
            return [
                {
                    "workflow_id": workflow_id,
                    "status": "EXECUTING",
                    "updated_at": datetime.fromisoformat("2026-04-04T10:00:00+08:00"),
                }
            ]

        def get_latest_ceo_shadow_run_for_trigger(self, *_args, **_kwargs):
            return None

    def _fake_snapshot(*_args, **_kwargs):
        return {
            "approvals": [],
            "incidents": [],
            "ticket_summary": {"working_count": 0},
            "idle_maintenance": {
                "signal_types": [],
                "latest_state_change_at": "2026-04-04T10:00:00+08:00",
            },
            "replan_focus": {
                "controller_state": {
                    "state": "READY_FOR_FANOUT",
                    "recommended_action": "CREATE_TICKET",
                    "blocking_reason": None,
                }
            },
        }

    monkeypatch.setattr("app.core.ceo_scheduler.build_ceo_shadow_snapshot", _fake_snapshot)

    due_workflow_ids = {
        item["workflow_id"]
        for item in list_due_ceo_maintenance_workflows(
            _Repository(),
            current_time=datetime.fromisoformat("2026-04-04T10:01:05+08:00"),
            interval_sec=60,
        )
    }

    assert workflow_id in due_workflow_ids
