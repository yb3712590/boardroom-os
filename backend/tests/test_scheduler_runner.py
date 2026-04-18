from __future__ import annotations

import json
import importlib
from datetime import datetime
from pathlib import Path
from typing import Callable
from uuid import uuid4

import app.core.ceo_proposer as ceo_proposer_module
import app.core.runtime as runtime_module
import app.core.workflow_auto_advance as workflow_auto_advance_module
import pytest
import tests.test_api as api_test_helpers
from app.core.ceo_execution_presets import build_project_init_scope_ticket_id
from app.core.ceo_scheduler import SCHEDULER_IDLE_MAINTENANCE_TRIGGER
from app.core.constants import EVENT_SCHEDULER_ORCHESTRATION_RECORDED, EVENT_TICKET_CREATED
from app.core.execution_targets import infer_execution_contract_payload
from app.core.output_schemas import (
    ARCHITECTURE_BRIEF_SCHEMA_REF,
    BACKLOG_RECOMMENDATION_SCHEMA_REF,
    DETAILED_DESIGN_SCHEMA_REF,
    MILESTONE_PLAN_SCHEMA_REF,
    TECHNOLOGY_DECISION_SCHEMA_REF,
)
from app.core.runtime import RuntimeExecutionResult, run_leased_ticket_runtime
from app.core.provider_openai_compat import (
    OpenAICompatProviderAuthError,
    OpenAICompatProviderBadResponseError,
    OpenAICompatProviderRateLimitedError,
    OpenAICompatProviderResult,
    OpenAICompatProviderUnavailableError,
)
from app.core.runtime_provider_config import (
    CLAUDE_CODE_PROVIDER_ID,
    OPENAI_COMPAT_PROVIDER_ID,
    ROLE_BINDING_FRONTEND_ENGINEER,
    RuntimeProviderConfigEntry,
    RuntimeProviderRoleBinding,
    RuntimeProviderStoredConfig,
)
from app.core.ticket_graph import build_ticket_graph_snapshot
from app.core.ticket_handlers import run_scheduler_tick
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
    acceptance_criteria: list[str] | None = None,
    allowed_write_set: list[str] | None = None,
    allowed_tools: list[str] | None = None,
    context_query_plan: dict | None = None,
) -> dict:
    resolved_role_profile_ref = (
        "frontend_engineer_primary"
        if role_profile_ref == "ui_designer_primary"
        else role_profile_ref
    )
    return {
        "ticket_id": ticket_id,
        "workflow_id": workflow_id,
        "node_id": node_id,
        "parent_ticket_id": None,
        "attempt_no": 1,
        "role_profile_ref": resolved_role_profile_ref,
        "constraints_ref": "global_constraints_v3",
        "input_artifact_refs": input_artifact_refs or ["art://inputs/brief.md"],
        "context_query_plan": context_query_plan or {
            "keywords": ["homepage"],
            "semantic_queries": ["approved direction"],
            "max_context_tokens": 3000,
        },
        "acceptance_criteria": acceptance_criteria or ["Must produce a structured result"],
        "output_schema_ref": output_schema_ref,
        "output_schema_version": 1,
        "allowed_tools": allowed_tools or ["read_artifact"],
        "allowed_write_set": allowed_write_set or ["artifacts/ui/homepage/*"],
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


def _seed_runtime_workflow(client, workflow_id: str, goal: str) -> str:
    from tests.test_ceo_scheduler import _seed_workflow

    return _seed_workflow(client, workflow_id, goal=goal)


def _ensure_runtime_provider_ready_for_ticket(
    client,
    *,
    role_profile_ref: str,
    output_schema_ref: str,
) -> None:
    resolved_role_profile_ref = (
        "frontend_engineer_primary"
        if role_profile_ref == "ui_designer_primary"
        else role_profile_ref
    )
    execution_contract = infer_execution_contract_payload(
        role_profile_ref=resolved_role_profile_ref,
        output_schema_ref=output_schema_ref,
    )
    if execution_contract is None:
        return

    target_ref = str(execution_contract["execution_target_ref"])
    provider_projection = client.get("/api/v1/projections/runtime-provider")
    assert provider_projection.status_code == 200
    projection_data = provider_projection.json()["data"]
    has_enabled_provider = any(
        provider["provider_id"] == OPENAI_COMPAT_PROVIDER_ID and provider["enabled"]
        for provider in projection_data["providers"]
    )
    has_target_binding = any(
        binding["target_ref"] == target_ref and binding["provider_model_entry_refs"]
        for binding in projection_data["role_bindings"]
    )
    if has_enabled_provider and has_target_binding:
        return

    upsert_response = client.post(
        "/api/v1/commands/runtime-provider-upsert",
        json={
            "providers": [
                {
                    "provider_id": OPENAI_COMPAT_PROVIDER_ID,
                    "type": "openai_responses_stream",
                    "enabled": True,
                    "base_url": "https://api.example.test/v1",
                    "api_key": "sk-test-secret",
                    "alias": "",
                    "preferred_model": "gpt-5.3-codex",
                    "max_context_window": None,
                    "reasoning_effort": "high",
                },
            ],
            "provider_model_entries": [
                {
                    "provider_id": OPENAI_COMPAT_PROVIDER_ID,
                    "model_name": "gpt-5.3-codex",
                }
            ],
            "role_bindings": [
                {
                    "target_ref": "ceo_shadow",
                    "provider_model_entry_refs": [f"{OPENAI_COMPAT_PROVIDER_ID}::gpt-5.3-codex"],
                    "max_context_window_override": None,
                    "reasoning_effort_override": None,
                },
                {
                    "target_ref": target_ref,
                    "provider_model_entry_refs": [f"{OPENAI_COMPAT_PROVIDER_ID}::gpt-5.3-codex"],
                    "max_context_window_override": None,
                    "reasoning_effort_override": None,
                },
            ],
            "idempotency_key": f"runtime-provider-upsert:test-scheduler-helper:{target_ref}",
        },
    )
    assert upsert_response.status_code == 200
    assert upsert_response.json()["status"] == "ACCEPTED"


def _seed_runtime_leased_ticket(
    client,
    *,
    workflow_id: str,
    ticket_id: str,
    node_id: str,
    leased_by: str,
    role_profile_ref: str = "ui_designer_primary",
    output_schema_ref: str = "ui_milestone_review",
    configure_provider: bool = True,
) -> None:
    api_test_helpers._ensure_scoped_workflow(
        client,
        workflow_id=workflow_id,
        tenant_id="tenant_default",
        workspace_id="ws_default",
        goal=f"Seed runtime provider ticket {ticket_id}.",
    )
    if configure_provider:
        _ensure_runtime_provider_ready_for_ticket(
            client,
            role_profile_ref=role_profile_ref,
            output_schema_ref=output_schema_ref,
        )
    api_test_helpers._seed_created_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id=ticket_id,
        node_id=node_id,
        role_profile_ref=role_profile_ref,
        output_schema_ref=output_schema_ref,
    )
    lease_response = client.post(
        "/api/v1/commands/ticket-lease",
        json={
            "workflow_id": workflow_id,
            "ticket_id": ticket_id,
            "node_id": node_id,
            "leased_by": leased_by,
            "lease_timeout_sec": 600,
            "idempotency_key": f"ticket-lease:{workflow_id}:{ticket_id}",
        },
    )
    assert lease_response.status_code == 200
    assert lease_response.json()["status"] == "ACCEPTED"


def test_run_scheduler_tick_does_not_materialize_graph_only_placeholder_node(client):
    workflow_id = "wf_scheduler_placeholder_gate"
    api_test_helpers._ensure_scoped_workflow(
        client,
        workflow_id=workflow_id,
        tenant_id="tenant_default",
        workspace_id="ws_default",
        goal="Scheduler should ignore graph-only placeholders.",
    )
    api_test_helpers._seed_created_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_scheduler_placeholder_parent",
        node_id="node_scheduler_placeholder_parent",
        role_profile_ref="frontend_engineer_primary",
        output_schema_ref="source_code_delivery",
        delivery_stage="BUILD",
    )
    api_test_helpers._seed_graph_patch_applied_event(
        client,
        workflow_id=workflow_id,
        patch_index=1,
        freeze_node_ids=[],
        focus_node_ids=["node_scheduler_placeholder_target"],
        add_nodes=[
            {
                "node_id": "node_scheduler_placeholder_target",
                "node_kind": "IMPLEMENTATION",
                "deliverable_kind": "source_code_delivery",
                "role_hint": "frontend_engineer_primary",
                "parent_node_id": "node_scheduler_placeholder_parent",
                "dependency_node_ids": [],
            }
        ],
    )

    repository = client.app.state.repository
    created_before = repository.count_events_by_type(EVENT_TICKET_CREATED)
    ack = run_scheduler_tick(
        repository,
        idempotency_key="scheduler-tick:placeholder-gate",
        max_dispatches=1,
    )
    created_after = repository.count_events_by_type(EVENT_TICKET_CREATED)
    graph_snapshot = build_ticket_graph_snapshot(repository, workflow_id)
    placeholder = next(
        node for node in graph_snapshot.nodes if node.graph_node_id == "node_scheduler_placeholder_target"
    )

    assert ack.status.value == "ACCEPTED"
    assert created_after == created_before
    assert repository.get_current_node_projection(workflow_id, "node_scheduler_placeholder_target") is None
    assert placeholder.is_placeholder is True


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
            "role_profile_refs": ["frontend_engineer_primary"],
            "skill_profile": {
                "primary_domain": "frontend",
                "system_scope": "surface_polish",
                "validation_bias": "finish_first",
            },
            "personality_profile": {
                "risk_posture": "cautious",
                "challenge_style": "probing",
                "execution_pace": "measured",
                "detail_rigor": "rigorous",
                "communication_style": "concise",
            },
            "aesthetic_profile": {
                "surface_preference": "polished",
                "information_density": "layered",
                "motion_tolerance": "restrained",
            },
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
                "role_profile_refs": ["frontend_engineer_primary"],
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


def _approval_by_type(repository, workflow_id: str, approval_type: str) -> dict:
    return next(
        approval
        for approval in repository.list_open_approvals()
        if approval["workflow_id"] == workflow_id and approval["approval_type"] == approval_type
    )


def _approve_review(client, approval: dict, *, idempotency_suffix: str) -> None:
    option_id = approval["payload"]["review_pack"]["options"][0]["option_id"]
    response = client.post(
        "/api/v1/commands/board-approve",
        json={
            "review_pack_id": approval["review_pack_id"],
            "review_pack_version": approval["review_pack_version"],
            "command_target_version": approval["command_target_version"],
            "approval_id": approval["approval_id"],
            "selected_option_id": option_id,
            "board_comment": "Approve and continue the mainline chain.",
            "idempotency_key": f"board-approve:{approval['approval_id']}:{idempotency_suffix}",
        },
    )
    assert response.status_code == 200
    assert response.json()["status"] == "ACCEPTED"


def _assert_workflow_reaches_closeout_completion(client, *, workflow_id: str, final_review_approval: dict) -> None:
    dashboard_response = client.get("/api/v1/projections/dashboard")
    assert dashboard_response.status_code == 200
    completion_summary = dashboard_response.json()["data"]["completion_summary"]

    assert completion_summary is not None
    assert completion_summary["workflow_id"] == workflow_id
    assert completion_summary["final_review_pack_id"] == final_review_approval["review_pack_id"]
    assert completion_summary["closeout_completed_at"] is not None
    assert completion_summary["closeout_ticket_id"] is not None
    assert completion_summary["closeout_artifact_refs"] == [
        f"art://runtime/{completion_summary['closeout_ticket_id']}/delivery-closeout-package.json"
    ]


def test_build_runtime_closeout_review_request_adds_documentation_sync_evidence() -> None:
    created_spec = {
        "auto_review_request": {
            "review_type": "INTERNAL_CLOSEOUT_REVIEW",
            "priority": "high",
            "title": "Check delivery closeout package",
            "subtitle": "Internal checker should validate the final handoff package before the workflow closes.",
            "blocking_scope": "NODE_ONLY",
            "trigger_reason": "Final delivery package reached the closeout checker gate.",
            "why_now": "Workflow completion should only happen after the final handoff package is internally checked.",
            "recommended_action": "APPROVE",
            "recommended_option_id": "internal_closeout_ok",
            "recommendation_summary": "Delivery closeout package is ready for final internal review.",
            "options": [
                {
                    "option_id": "internal_closeout_ok",
                    "label": "Pass closeout package",
                    "summary": "Delivery closeout package is ready for final internal review.",
                    "artifact_refs": [],
                }
            ],
            "evidence_summary": [
                {
                    "evidence_id": "ev_delivery_closeout_package",
                    "source_type": "DELIVERY_CLOSEOUT_PACKAGE",
                    "headline": "Delivery closeout package is ready for internal review",
                    "summary": "Delivery closeout package is ready for final internal review.",
                    "source_ref": None,
                }
            ],
            "available_actions": ["APPROVE", "REJECT", "MODIFY_CONSTRAINTS"],
            "draft_selected_option_id": "internal_closeout_ok",
            "comment_template": "",
            "badges": ["internal_closeout", "closeout_gate"],
        },
        "output_schema_ref": "delivery_closeout_package",
    }
    execution_result = RuntimeExecutionResult(
        result_status="completed",
        completion_summary="Closeout package completed with documentation sync notes.",
        artifact_refs=["art://runtime/tkt_closeout_001/delivery-closeout-package.json"],
        result_payload={
            "summary": "Closeout package completed with documentation sync notes.",
            "final_artifact_refs": ["art://runtime/tkt_closeout_001/delivery-closeout-package.json"],
            "handoff_notes": [
                "Board-approved final option is captured in the closeout package.",
                "Final evidence remains linked back to the board review pack.",
            ],
            "documentation_updates": [
                {
                    "doc_ref": "doc/TODO.md",
                    "status": "UPDATED",
                    "summary": "Marked P2-GOV-007 as completed.",
                },
                {
                    "doc_ref": "README.md",
                    "status": "FOLLOW_UP_REQUIRED",
                    "summary": "Public quick-start wording still needs one closeout follow-up pass.",
                },
            ],
        },
    )

    review_request = runtime_module._build_runtime_review_request(
        ticket={"ticket_id": "tkt_closeout_001"},
        execution_result=execution_result,
        created_spec=created_spec,
    )

    assert review_request is not None
    assert "documentation sync" in review_request.recommendation_summary.lower()
    documentation_evidence = next(
        evidence
        for evidence in review_request.evidence_summary
        if evidence.evidence_id == "ev_closeout_documentation_sync"
    )
    assert documentation_evidence.source_type == "DOCUMENTATION_SYNC"
    assert "FOLLOW_UP_REQUIRED" in documentation_evidence.summary
    assert "doc/TODO.md" in documentation_evidence.summary


def _followup_ticket_from_scope_approval(client, repository, approval: dict, *, delivery_stage: str) -> dict:
    consensus_artifact_ref = approval["payload"]["review_pack"]["evidence_summary"][0]["source_ref"]
    artifact = repository.get_artifact_by_ref(consensus_artifact_ref)
    assert artifact is not None
    assert artifact["storage_relpath"] is not None

    artifact_path = client.app.state.artifact_store.root / artifact["storage_relpath"]
    consensus_payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    return next(
        item for item in consensus_payload["followup_tickets"] if item["delivery_stage"] == delivery_stage
    )


def _create_scope_consensus_approval(
    client,
    *,
    workflow_id: str,
    ticket_id: str,
    node_id: str,
    summary: str,
) -> dict:
    create_response = client.post(
        "/api/v1/commands/ticket-create",
        json={
            **_ticket_create_payload(
                workflow_id=workflow_id,
                ticket_id=ticket_id,
                node_id=node_id,
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
            "retry_budget": 0,
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
            "idempotency_key": f"ticket-lease:{workflow_id}:{ticket_id}:scope-consensus",
        },
    )
    assert lease_response.status_code == 200
    assert lease_response.json()["status"] == "ACCEPTED"

    start_response = client.post(
        "/api/v1/commands/ticket-start",
        json={
            "workflow_id": workflow_id,
            "ticket_id": ticket_id,
            "node_id": node_id,
            "started_by": "emp_frontend_2",
            "idempotency_key": f"ticket-start:{workflow_id}:{ticket_id}:scope-consensus",
        },
    )
    assert start_response.status_code == 200
    assert start_response.json()["status"] == "ACCEPTED"

    artifact_ref = f"art://meeting/{ticket_id}/scope-consensus.json"
    result_payload = {
        "topic": f"Consensus for {ticket_id}",
        "participants": ["emp_frontend_2", "emp_checker_1"],
        "input_artifact_refs": ["art://inputs/brief.md", "art://inputs/scope-notes.md"],
        "consensus_summary": summary,
        "rejected_options": ["Do not widen the MVP scope in this round."],
        "open_questions": ["Whether non-blocking polish should move after board approval."],
        "followup_tickets": [
            {
                "ticket_id": "tkt_scope_provider_build",
                "task_title": "Build the provider-backed homepage foundation",
                "owner_role": "frontend_engineer",
                "summary": "Build the approved homepage foundation without widening scope.",
                "delivery_stage": "BUILD",
            },
            {
                "ticket_id": "tkt_scope_provider_check",
                "task_title": "Check the provider-backed homepage foundation",
                "owner_role": "checker",
                "summary": "Check the source code delivery against the locked scope.",
                "delivery_stage": "CHECK",
            },
            {
                "ticket_id": "tkt_scope_provider_review",
                "task_title": "Prepare the provider-backed review package",
                "owner_role": "frontend_engineer",
                "summary": "Prepare the final board-facing review package.",
                "delivery_stage": "REVIEW",
            },
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
                    "evidence_id": "ev_scope_consensus",
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
    submit_response = client.post(
        "/api/v1/commands/ticket-result-submit",
        json={
            "workflow_id": workflow_id,
            "ticket_id": ticket_id,
            "node_id": node_id,
            "submitted_by": "emp_frontend_2",
            "result_status": "completed",
            "schema_version": "consensus_document_v1",
            "payload": result_payload,
            "artifact_refs": [artifact_ref],
            "written_artifacts": [
                {
                    "path": f"reports/meeting/{ticket_id}/scope-consensus.json",
                    "artifact_ref": artifact_ref,
                    "kind": "JSON",
                    "content_json": result_payload,
                }
            ],
            "assumptions": ["The governance-first chain has converged on a single delivery scope."],
            "issues": [],
            "confidence": 0.86,
            "needs_escalation": False,
            "summary": summary,
            "review_request": review_request,
            "idempotency_key": f"ticket-result-submit:{workflow_id}:{ticket_id}:scope-consensus",
        },
    )
    assert submit_response.status_code == 200
    assert submit_response.json()["status"] == "ACCEPTED"

    repository = client.app.state.repository
    checker_ticket_id = repository.get_current_node_projection(workflow_id, node_id)["latest_ticket_id"]

    checker_lease_response = client.post(
        "/api/v1/commands/ticket-lease",
        json={
            "workflow_id": workflow_id,
            "ticket_id": checker_ticket_id,
            "node_id": node_id,
            "leased_by": "emp_checker_1",
            "lease_timeout_sec": 600,
            "idempotency_key": f"ticket-lease:{workflow_id}:{checker_ticket_id}:scope-consensus-checker",
        },
    )
    assert checker_lease_response.status_code == 200
    assert checker_lease_response.json()["status"] == "ACCEPTED"

    checker_start_response = client.post(
        "/api/v1/commands/ticket-start",
        json={
            "workflow_id": workflow_id,
            "ticket_id": checker_ticket_id,
            "node_id": node_id,
            "started_by": "emp_checker_1",
            "idempotency_key": f"ticket-start:{workflow_id}:{checker_ticket_id}:scope-consensus-checker",
        },
    )
    assert checker_start_response.status_code == 200
    assert checker_start_response.json()["status"] == "ACCEPTED"

    checker_submit_response = client.post(
        "/api/v1/commands/ticket-result-submit",
        json={
            "workflow_id": workflow_id,
            "ticket_id": checker_ticket_id,
            "node_id": node_id,
            "submitted_by": "emp_checker_1",
            "result_status": "completed",
            "schema_version": "maker_checker_verdict_v1",
            "payload": {
                "summary": "Checker approved the consensus output.",
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
            "idempotency_key": f"ticket-result-submit:{workflow_id}:{checker_ticket_id}:scope-consensus-approved",
        },
    )
    assert checker_submit_response.status_code == 200
    assert checker_submit_response.json()["status"] == "ACCEPTED"

    return next(
        approval
        for approval in repository.list_open_approvals()
        if approval["workflow_id"] == workflow_id and approval["approval_type"] == "MEETING_ESCALATION"
    )


def _run_scheduler_until_workflow_stop(
    repository,
    *,
    workflow_id: str,
    idempotency_key_prefix: str,
    max_runs: int = 10,
    before_each_run: Callable[[int], None] | None = None,
) -> None:
    for run_index in range(max_runs):
        if before_each_run is not None:
            before_each_run(run_index)
        _, version_before = repository.get_cursor_and_version()
        run_scheduler_once(
            repository,
            idempotency_key=f"{idempotency_key_prefix}:{run_index}",
            max_dispatches=10,
        )
        if any(approval["workflow_id"] == workflow_id for approval in repository.list_open_approvals()):
            return
        if any(incident["workflow_id"] == workflow_id for incident in repository.list_open_incidents()):
            return
        _, version_after = repository.get_cursor_and_version()
        if version_after == version_before:
            return


def _mock_provider_payload_for_schema(schema_ref: str) -> dict:
    if schema_ref in {
        ARCHITECTURE_BRIEF_SCHEMA_REF,
        TECHNOLOGY_DECISION_SCHEMA_REF,
        MILESTONE_PLAN_SCHEMA_REF,
        DETAILED_DESIGN_SCHEMA_REF,
    }:
        return {
            "document_kind_ref": schema_ref,
            "title": f"{schema_ref} title",
            "summary": f"{schema_ref} is complete and ready for the next governance step.",
            "linked_document_refs": ["doc://governance/upstream/current"],
            "linked_artifact_refs": [f"art://runtime/provider/{schema_ref}.json"],
            "source_process_asset_refs": [],
            "decisions": ["Keep the delivery sequence explicit and governance-first."],
            "constraints": ["Do not widen the current MVP boundary."],
            "sections": [
                {
                    "section_id": "section_overview",
                    "label": "Overview",
                    "summary": f"{schema_ref} summary",
                    "content_markdown": "Document-first guidance for the next delivery slice.",
                }
            ],
            "followup_recommendations": [
                {
                    "recommendation_id": "rec_next_governance_step",
                    "summary": "Continue the governance chain.",
                    "target_role": "frontend_engineer",
                }
            ],
        }
    if schema_ref == BACKLOG_RECOMMENDATION_SCHEMA_REF:
        return {
            "document_kind_ref": schema_ref,
            "title": "Provider-backed backlog recommendation",
            "summary": "Turn the approved governance chain into executable tickets.",
            "linked_document_refs": ["doc://governance/upstream/current"],
            "linked_artifact_refs": ["art://runtime/provider/backlog-recommendation.json"],
            "source_process_asset_refs": [],
            "decisions": ["Continue with the approved narrow MVP sequence."],
            "constraints": ["Keep governance explicit before execution fanout."],
            "sections": [
                {
                    "section_id": "recommended_ticket_split",
                    "label": "Recommended ticket split",
                    "summary": "Split the next delivery steps into executable tickets.",
                    "content_markdown": "Create build, check, and review follow-ups.",
                    "content_json": {
                        "tickets": [
                            {
                                "ticket_id": "BR-FE-01",
                                "name": "Provider-backed homepage build",
                                "priority": "P0",
                                "target_role": "frontend_engineer",
                                "scope": ["homepage foundation"],
                            }
                        ],
                        "dependency_graph": [
                            {
                                "ticket_id": "BR-FE-01",
                                "depends_on": [],
                                "reason": "The approved scope can move into implementation.",
                            }
                        ],
                        "recommended_sequence": ["BR-FE-01 Provider-backed homepage build"],
                    },
                }
            ],
            "followup_recommendations": [
                {
                    "recommendation_id": "rec_build_followup",
                    "summary": "Create the implementation follow-up ticket.",
                    "target_role": "frontend_engineer",
                }
            ],
        }
    if schema_ref == "consensus_document":
        return {
            "topic": "Homepage scope consensus",
            "participants": ["frontend_engineer_primary", "checker_primary"],
            "input_artifact_refs": ["art://inputs/brief.md"],
            "consensus_summary": "Lock scope to the narrow homepage MVP path and continue delivery.",
            "rejected_options": ["Expand beyond the current MVP boundary in this round."],
            "open_questions": ["Whether non-blocking polish should move after board approval."],
            "followup_tickets": [
                {
                    "ticket_id": "tkt_scope_provider_build",
                    "task_title": "Build the provider-backed homepage foundation",
                    "owner_role": "frontend_engineer",
                    "summary": "Build the approved homepage foundation without widening scope.",
                    "delivery_stage": "BUILD",
                },
                {
                    "ticket_id": "tkt_scope_provider_check",
                    "task_title": "Check the provider-backed homepage foundation",
                    "owner_role": "checker",
                    "summary": "Check the source code delivery against the locked scope.",
                    "delivery_stage": "CHECK",
                },
                {
                    "ticket_id": "tkt_scope_provider_review",
                    "task_title": "Prepare the provider-backed review package",
                    "owner_role": "frontend_engineer",
                    "summary": "Prepare the final board-facing review package.",
                    "delivery_stage": "REVIEW",
                },
            ],
        }
    if schema_ref == "source_code_delivery":
        return {
            "summary": "Provider-backed source code delivery is ready for internal checking.",
            "source_file_refs": ["art://runtime/provider/source-code.tsx"],
            "implementation_notes": [
                "Implementation stays inside the approved homepage MVP scope."
            ],
        }
    if schema_ref == "delivery_check_report":
        return {
            "summary": "Provider-backed internal delivery check passed with one non-blocking note.",
            "status": "PASS_WITH_NOTES",
            "findings": [
                {
                    "finding_id": "finding_copy_trim",
                    "summary": "Keep copy trimmed to the approved homepage scope.",
                    "blocking": False,
                }
            ],
        }
    if schema_ref == "delivery_closeout_package":
        return {
            "summary": "Provider-backed closeout package captured the approved board choice.",
            "final_artifact_refs": ["art://runtime/tkt_scope_provider_review/option-a.json"],
            "handoff_notes": [
                "Approved board choice is captured in the closeout package.",
                "Final evidence stays linked to the board review pack for audit.",
            ],
        }
    if schema_ref == "maker_checker_verdict":
        return {
            "summary": "Provider-backed checker approved the submitted deliverable.",
            "review_status": "APPROVED",
            "findings": [],
        }
    if schema_ref == "ui_milestone_review":
        return {
            "summary": "Provider-backed final review package is ready for board approval.",
            "recommended_option_id": "option_a",
            "options": [
                {
                    "option_id": "option_a",
                    "label": "Option A",
                    "summary": "Approved homepage direction with clear hierarchy.",
                    "artifact_refs": ["art://runtime/provider/final-review-option-a.json"],
                },
                {
                    "option_id": "option_b",
                    "label": "Option B",
                    "summary": "Fallback direction with lower emphasis.",
                    "artifact_refs": ["art://runtime/provider/final-review-option-b.json"],
                },
            ],
        }
    raise AssertionError(f"Unexpected schema_ref for mock provider: {schema_ref}")


def _build_mock_provider_responder(*, bad_response_schemas: set[str] | None = None):
    observed_schema_refs: list[str] = []

    def _respond(config, rendered_payload):
        schema_ref = str(rendered_payload.messages[-1].content_payload["output_schema_ref"])
        observed_schema_refs.append(schema_ref)
        if schema_ref in (bad_response_schemas or set()):
            return OpenAICompatProviderResult(
                output_text='{"summary":"Broken provider payload.","recommended_option_id":"option_a","options":[]}',
                response_id=f"resp_bad_{schema_ref}_{len(observed_schema_refs)}",
            )
        return OpenAICompatProviderResult(
            output_text=json.dumps(_mock_provider_payload_for_schema(schema_ref)),
            response_id=f"resp_{schema_ref}_{len(observed_schema_refs)}",
        )

    return _respond, observed_schema_refs


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
    assert [event["event_type"] for event in events][-3:] == [
        "TICKET_CREATED",
        "TICKET_LEASED",
        EVENT_SCHEDULER_ORCHESTRATION_RECORDED,
    ]


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
    assert latest_bundle["payload"]["context_blocks"][0]["source_kind"] == "PROCESS_ASSET"
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


def test_runtime_uses_openai_compat_provider_when_configured(client, set_ticket_time, monkeypatch):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    workflow_id = _seed_runtime_workflow(client, "wf_runner_provider_live", "OpenAI provider runtime")
    monkeypatch.setenv("BOARDROOM_OS_PROVIDER_OPENAI_COMPAT_BASE_URL", "https://api-vip.codex-for.me/v1")
    monkeypatch.setenv("BOARDROOM_OS_PROVIDER_OPENAI_COMPAT_API_KEY", "provider-key")
    monkeypatch.setenv("BOARDROOM_OS_PROVIDER_OPENAI_COMPAT_MODEL", "gpt-5.3-codex")
    repository = client.app.state.repository
    _seed_worker(repository, employee_id="emp_frontend_live", provider_id="prov_openai_compat")

    client.post(
        "/api/v1/commands/ticket-create",
        json=_ticket_create_payload(
            workflow_id=workflow_id,
            ticket_id="tkt_runner_provider_live",
            node_id="node_runner_provider_live",
            role_profile_ref="ui_designer_primary",
        ),
    )
    client.post(
        "/api/v1/commands/ticket-lease",
        json={
            "workflow_id": workflow_id,
            "ticket_id": "tkt_runner_provider_live",
            "node_id": "node_runner_provider_live",
            "leased_by": "emp_frontend_live",
            "lease_timeout_sec": 600,
            "idempotency_key": "ticket-lease:wf_runner_provider_live:tkt_runner_provider_live",
        },
    )

    called_ticket_ids: list[str] = []

    def _fake_provider_execute(execution_package, *args, **kwargs):
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


def test_runtime_completes_governance_document_ticket_on_live_role(client, set_ticket_time):
    set_ticket_time("2026-04-07T19:00:00+08:00")
    repository = client.app.state.repository

    client.post(
        "/api/v1/commands/ticket-create",
        json=_ticket_create_payload(
            workflow_id="wf_runtime_governance_doc",
            ticket_id="tkt_runtime_governance_doc",
            node_id="node_runtime_governance_doc",
            role_profile_ref="frontend_engineer_primary",
            output_schema_ref=ARCHITECTURE_BRIEF_SCHEMA_REF,
            allowed_tools=["read_artifact", "write_artifact"],
            allowed_write_set=["reports/governance/tkt_runtime_governance_doc/*"],
            acceptance_criteria=["Must produce a structured architecture_brief governance document."],
        ),
    )
    client.post(
        "/api/v1/commands/ticket-lease",
        json={
            "workflow_id": "wf_runtime_governance_doc",
            "ticket_id": "tkt_runtime_governance_doc",
            "node_id": "node_runtime_governance_doc",
            "leased_by": "emp_frontend_2",
            "lease_timeout_sec": 600,
            "idempotency_key": "ticket-lease:wf_runtime_governance_doc:tkt_runtime_governance_doc",
        },
    )

    outcomes = run_leased_ticket_runtime(repository)
    ticket_projection = repository.get_current_ticket_projection("tkt_runtime_governance_doc")
    with repository.connection() as connection:
        terminal_event = repository.get_latest_ticket_terminal_event(connection, "tkt_runtime_governance_doc")

    assert [outcome.ticket_id for outcome in outcomes] == ["tkt_runtime_governance_doc"]
    assert ticket_projection["status"] == "COMPLETED"
    assert terminal_event is not None
    assert terminal_event["payload"]["artifact_refs"] == [
        "art://runtime/tkt_runtime_governance_doc/architecture_brief.json"
    ]
    assert "pa://governance-document/tkt_runtime_governance_doc" in [
        item["process_asset_ref"] for item in terminal_event["payload"]["produced_process_assets"]
    ]


def test_runtime_governance_document_completion_routes_to_internal_governance_checker(client, set_ticket_time):
    set_ticket_time("2026-04-07T19:05:00+08:00")
    repository = client.app.state.repository

    client.post(
        "/api/v1/commands/ticket-create",
        json=_ticket_create_payload(
            workflow_id="wf_runtime_governance_gate",
            ticket_id="tkt_runtime_governance_gate",
            node_id="node_runtime_governance_gate",
            role_profile_ref="frontend_engineer_primary",
            output_schema_ref=ARCHITECTURE_BRIEF_SCHEMA_REF,
            allowed_tools=["read_artifact", "write_artifact"],
            allowed_write_set=["reports/governance/tkt_runtime_governance_gate/*"],
            acceptance_criteria=["Must produce a structured architecture_brief governance document."],
        ),
    )
    client.post(
        "/api/v1/commands/ticket-lease",
        json={
            "workflow_id": "wf_runtime_governance_gate",
            "ticket_id": "tkt_runtime_governance_gate",
            "node_id": "node_runtime_governance_gate",
            "leased_by": "emp_frontend_2",
            "lease_timeout_sec": 600,
            "idempotency_key": "ticket-lease:wf_runtime_governance_gate:tkt_runtime_governance_gate",
        },
    )

    outcomes = run_leased_ticket_runtime(repository)

    assert [outcome.ticket_id for outcome in outcomes] == ["tkt_runtime_governance_gate"]
    current_node = repository.get_current_node_projection("wf_runtime_governance_gate", "node_runtime_governance_gate")
    assert current_node is not None
    assert current_node["latest_ticket_id"] != "tkt_runtime_governance_gate"
    with repository.connection() as connection:
        checker_created_spec = repository.get_latest_ticket_created_payload(
            connection,
            current_node["latest_ticket_id"],
        )

    assert checker_created_spec is not None
    assert checker_created_spec["output_schema_ref"] == "maker_checker_verdict"
    assert checker_created_spec["maker_checker_context"]["maker_ticket_id"] == "tkt_runtime_governance_gate"
    assert checker_created_spec["maker_checker_context"]["original_review_request"]["review_type"] == (
        "INTERNAL_GOVERNANCE_REVIEW"
    )


def test_runtime_runner_executes_leased_review_lane_ticket(client, set_ticket_time, monkeypatch):
    set_ticket_time("2026-04-07T19:05:00+08:00")
    workflow_id = "wf_runtime_review_lane_runner"
    api_test_helpers._ensure_scoped_workflow(
        client,
        workflow_id=workflow_id,
        tenant_id="tenant_default",
        workspace_id="ws_default",
        goal="Runtime runner should execute leased review-lane tickets through runtime_node_projection truth.",
    )
    api_test_helpers._create_lease_and_start_ticket(client, workflow_id=workflow_id)

    maker_response = client.post(
        "/api/v1/commands/ticket-complete",
        json=api_test_helpers._ticket_complete_payload(workflow_id=workflow_id),
    )
    assert maker_response.status_code == 200
    assert maker_response.json()["status"] == "ACCEPTED"

    repository = client.app.state.repository
    current_node = repository.get_current_node_projection(workflow_id, "node_homepage_visual")
    assert current_node is not None
    checker_ticket_id = current_node["latest_ticket_id"]

    checker_lease_response = client.post(
        "/api/v1/commands/ticket-lease",
        json=api_test_helpers._ticket_lease_payload(
            workflow_id=workflow_id,
            ticket_id=checker_ticket_id,
            leased_by="emp_checker_1",
        ),
    )
    assert checker_lease_response.status_code == 200
    assert checker_lease_response.json()["status"] == "ACCEPTED"

    provider_responder, _ = _build_mock_provider_responder()
    monkeypatch.setattr(runtime_module, "invoke_openai_compat_response", provider_responder)

    outcomes = run_leased_ticket_runtime(repository)
    latest_checker = repository.get_current_ticket_projection(checker_ticket_id)

    assert [outcome.ticket_id for outcome in outcomes] == [checker_ticket_id]
    assert latest_checker is not None
    assert outcomes[0].start_ack.status.value == "ACCEPTED"
    assert latest_checker["status"] == "EXECUTING"


def test_runtime_uses_saved_runtime_provider_config_when_env_is_missing(
    client,
    set_ticket_time,
    monkeypatch,
):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    workflow_id = _seed_runtime_workflow(client, "wf_runner_provider_saved", "Saved provider runtime")
    config_path = Path.cwd() / ".tmp" / f"runtime-provider-config-{uuid4().hex}.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        json.dumps(
            {
                "default_provider_id": "prov_openai_compat",
                "providers": [
                    {
                        "provider_id": "prov_openai_compat",
                        "type": "openai_responses_stream",
                        "base_url": "https://api-vip.codex-for.me/v1",
                        "api_key": "provider-key",
                        "alias": "vip",
                        "preferred_model": "gpt-5.3-codex",
                        "max_context_window": 1000000,
                        "enabled": True,
                        "timeout_sec": 30.0,
                        "reasoning_effort": "medium",
                    }
                ],
                "provider_model_entries": [
                    {
                        "provider_id": "prov_openai_compat",
                        "model_name": "gpt-5.3-codex",
                    }
                ],
                "role_bindings": [],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("BOARDROOM_OS_RUNTIME_PROVIDER_CONFIG_PATH", str(config_path))
    monkeypatch.delenv("BOARDROOM_OS_PROVIDER_OPENAI_COMPAT_BASE_URL", raising=False)
    monkeypatch.delenv("BOARDROOM_OS_PROVIDER_OPENAI_COMPAT_API_KEY", raising=False)
    monkeypatch.delenv("BOARDROOM_OS_PROVIDER_OPENAI_COMPAT_MODEL", raising=False)
    repository = client.app.state.repository
    _seed_worker(repository, employee_id="emp_frontend_saved_config", provider_id="prov_openai_compat")

    client.post(
        "/api/v1/commands/ticket-create",
        json=_ticket_create_payload(
            workflow_id=workflow_id,
            ticket_id="tkt_runner_provider_saved",
            node_id="node_runner_provider_saved",
            role_profile_ref="ui_designer_primary",
        ),
    )
    client.post(
        "/api/v1/commands/ticket-lease",
        json={
            "workflow_id": workflow_id,
            "ticket_id": "tkt_runner_provider_saved",
            "node_id": "node_runner_provider_saved",
            "leased_by": "emp_frontend_saved_config",
            "lease_timeout_sec": 600,
            "idempotency_key": "ticket-lease:wf_runner_provider_saved:tkt_runner_provider_saved",
        },
    )

    called_ticket_ids: list[str] = []

    def _fake_provider_execute(execution_package, *args, **kwargs):
        called_ticket_ids.append(execution_package.meta.ticket_id)
        return RuntimeExecutionResult(
            result_status="completed",
            completion_summary="Provider completed the runtime ticket from saved config.",
            artifact_refs=["art://runtime/provider-saved/option-a.json"],
            result_payload={
                "summary": "Provider completed the runtime ticket from saved config.",
                "recommended_option_id": "option_a",
                "options": [
                    {
                        "option_id": "option_a",
                        "label": "Option A",
                        "summary": "Provider-backed option from saved config.",
                        "artifact_refs": ["art://runtime/provider-saved/option-a.json"],
                    }
                ],
            },
            confidence=0.84,
        )

    monkeypatch.setattr(
        runtime_module,
        "_execute_openai_compat_provider",
        _fake_provider_execute,
        raising=False,
    )

    outcomes = run_leased_ticket_runtime(repository)
    ticket_projection = repository.get_current_ticket_projection("tkt_runner_provider_saved")

    assert [outcome.ticket_id for outcome in outcomes] == ["tkt_runner_provider_saved"]
    assert called_ticket_ids == ["tkt_runner_provider_saved"]
    assert ticket_projection["status"] == "COMPLETED"


def test_runtime_prefers_role_binding_over_employee_provider(client, set_ticket_time, monkeypatch):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    workflow_id = _seed_runtime_workflow(client, "wf_runner_provider_binding", "Role binding provider runtime")
    repository = client.app.state.repository
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
                    target_ref=ROLE_BINDING_FRONTEND_ENGINEER,
                    provider_id=CLAUDE_CODE_PROVIDER_ID,
                    model="claude-opus-4-1",
                )
            ],
        )
    )
    _seed_worker(repository, employee_id="emp_frontend_bound", provider_id=OPENAI_COMPAT_PROVIDER_ID)

    client.post(
        "/api/v1/commands/ticket-create",
        json=_ticket_create_payload(
            workflow_id=workflow_id,
            ticket_id="tkt_runner_provider_binding",
            node_id="node_runner_provider_binding",
            role_profile_ref="frontend_engineer_primary",
        ),
    )
    client.post(
        "/api/v1/commands/ticket-lease",
        json={
            "workflow_id": workflow_id,
            "ticket_id": "tkt_runner_provider_binding",
            "node_id": "node_runner_provider_binding",
            "leased_by": "emp_frontend_bound",
            "lease_timeout_sec": 600,
            "idempotency_key": "ticket-lease:wf_runner_provider_binding:tkt_runner_provider_binding",
        },
    )

    monkeypatch.setattr(
        runtime_module,
        "invoke_openai_compat_response",
        lambda *args, **kwargs: pytest.fail("runtime should not pick OpenAI when a role binding points to Claude"),
    )

    def _fake_claude(*args, **kwargs):
        return type(
            "ClaudeResult",
            (),
            {
                "output_text": '{"summary":"Claude handled the runtime ticket.","recommended_option_id":"option_a","options":[{"option_id":"option_a","label":"Option A","summary":"Claude-backed option.","artifact_refs":["art://runtime/provider-claude/option-a.json"]}]}',
                "response_id": None,
            },
        )()

    monkeypatch.setattr(runtime_module, "invoke_claude_code_response", _fake_claude)

    outcomes = run_leased_ticket_runtime(repository)
    ticket_projection = repository.get_current_ticket_projection("tkt_runner_provider_binding")

    assert [outcome.ticket_id for outcome in outcomes] == ["tkt_runner_provider_binding"]
    assert ticket_projection["status"] == "COMPLETED"


def test_scheduler_runner_completes_consensus_document_ticket_with_local_runtime(client, set_ticket_time):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    client.post(
        "/api/v1/commands/ticket-create",
        json=_ticket_create_payload(
            workflow_id="wf_runner_consensus",
            ticket_id="tkt_runner_consensus",
            node_id="node_runner_consensus",
            role_profile_ref="ui_designer_primary",
            output_schema_ref="consensus_document",
            input_artifact_refs=["art://inputs/brief.md", "art://inputs/meeting-notes.md"],
            acceptance_criteria=[
                "Must produce a consensus document",
                "Must include follow-up tickets",
            ],
            allowed_write_set=["reports/meeting/*"],
            allowed_tools=["read_artifact", "write_artifact"],
            context_query_plan={
                "keywords": ["scope", "meeting", "decision"],
                "semantic_queries": ["current scope tradeoffs"],
                "max_context_tokens": 3000,
            },
        ),
    )

    run_scheduler_once(
        client.app.state.repository,
        idempotency_key="scheduler-runner:test-consensus-runtime",
        max_dispatches=10,
    )

    repository = client.app.state.repository
    ticket_projection = repository.get_current_ticket_projection("tkt_runner_consensus")
    artifact_response = client.get("/api/v1/projections/tickets/tkt_runner_consensus/artifacts")
    failed_events = [
        event for event in repository.list_events_for_testing() if event["event_type"] == "TICKET_FAILED"
    ]

    assert ticket_projection["status"] == "COMPLETED"
    assert failed_events == []
    assert artifact_response.status_code == 200
    assert len(artifact_response.json()["data"]["artifacts"]) == 1
    assert artifact_response.json()["data"]["artifacts"][0]["path"] == "reports/meeting/consensus-document.json"


def test_scheduler_runner_auto_advances_default_scope_delivery_chain_to_final_review_stop(
    client,
    set_ticket_time,
):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    workflow_id = _project_init(client, goal="Scope follow-up fanout")
    repository = client.app.state.repository
    approval = repository.list_open_approvals()[0]
    consensus_artifact_ref = approval["payload"]["review_pack"]["evidence_summary"][0]["source_ref"]
    artifact = repository.get_artifact_by_ref(consensus_artifact_ref)

    assert artifact is not None
    assert artifact["storage_relpath"] is not None

    artifact_path = client.app.state.artifact_store.root / artifact["storage_relpath"]
    consensus_payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    followup_ticket_ids = [item["ticket_id"] for item in consensus_payload["followup_tickets"]]

    approve_response = client.post(
        "/api/v1/commands/board-approve",
        json={
            "review_pack_id": approval["review_pack_id"],
            "review_pack_version": approval["review_pack_version"],
            "command_target_version": approval["command_target_version"],
            "approval_id": approval["approval_id"],
            "selected_option_id": approval["payload"]["review_pack"]["options"][0]["option_id"],
            "board_comment": "Approve the locked scope and continue.",
            "idempotency_key": f"board-approve:{approval['approval_id']}:multi-followup",
        },
    )

    followup_tickets = [
        repository.get_current_ticket_projection(ticket_id) for ticket_id in followup_ticket_ids
    ]
    open_approvals = repository.list_open_approvals()
    build_checker_creates = [
        event
        for event in repository.list_events_for_testing()
        if event["event_type"] == "TICKET_CREATED"
        and (event["payload"].get("ticket_kind") == "MAKER_CHECKER_REVIEW")
        and (event["payload"].get("delivery_stage") == "BUILD")
    ]

    assert [item["delivery_stage"] for item in consensus_payload["followup_tickets"]] == [
        "BUILD",
        "CHECK",
        "REVIEW",
    ]
    assert len(consensus_payload["followup_tickets"]) == 3
    assert len(set(followup_ticket_ids)) == 3
    assert approve_response.status_code == 200
    assert approve_response.json()["status"] == "ACCEPTED"
    assert all(ticket is not None for ticket in followup_tickets)
    assert all(ticket["status"] == "COMPLETED" for ticket in followup_tickets if ticket is not None)
    assert len(build_checker_creates) == 1
    assert any(item["approval_type"] == "VISUAL_MILESTONE" for item in open_approvals)


def test_deterministic_scope_delivery_chain_reaches_closeout_completion(client, set_ticket_time):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    workflow_id = _project_init(client, goal="Deterministic mainline completion")
    repository = client.app.state.repository

    scope_approval = _approval_by_type(repository, workflow_id, "MEETING_ESCALATION")
    _approve_review(client, scope_approval, idempotency_suffix="deterministic-scope")

    final_review_approval = _approval_by_type(repository, workflow_id, "VISUAL_MILESTONE")
    _approve_review(client, final_review_approval, idempotency_suffix="deterministic-final-review")

    dashboard_response = client.get("/api/v1/projections/dashboard")
    assert dashboard_response.status_code == 200
    completion_summary = dashboard_response.json()["data"]["completion_summary"]

    assert completion_summary is not None
    assert completion_summary["workflow_id"] == workflow_id
    assert completion_summary["final_review_pack_id"] == final_review_approval["review_pack_id"]
    assert completion_summary["closeout_completed_at"] is not None
    assert completion_summary["closeout_ticket_id"] is not None
    assert completion_summary["closeout_artifact_refs"] == [
        f"art://runtime/{completion_summary['closeout_ticket_id']}/delivery-closeout-package.json"
    ]
    assert repository.list_open_approvals() == []
    assert repository.list_open_incidents() == []


def test_scheduler_runner_triggers_idle_ceo_maintenance_for_pending_workflow(
    client,
    monkeypatch,
    set_ticket_time,
):
    set_ticket_time("2026-04-04T10:00:00+08:00")
    monkeypatch.setattr(
        client.app.state.repository,
        "list_scheduler_worker_candidates",
        lambda connection=None: [],
    )
    workflow_id = _project_init(client, goal="Scheduler idle CEO maintenance")

    set_ticket_time("2026-04-04T10:01:05+08:00")
    run_scheduler_once(
        client.app.state.repository,
        idempotency_key="scheduler-runner:test-idle-ceo-maintenance",
        max_dispatches=10,
    )

    runs = client.app.state.repository.list_ceo_shadow_runs(workflow_id)

    assert any(run["trigger_type"] == SCHEDULER_IDLE_MAINTENANCE_TRIGGER for run in runs)


def test_scheduler_runner_idle_ceo_maintenance_hires_architect_for_controller_gate(
    client,
    monkeypatch,
    set_ticket_time,
):
    from tests.test_ceo_scheduler import (
        _create_and_complete_backlog_recommendation_ticket,
        _create_and_complete_minimum_governance_chain,
        _persist_workflow_directive_details,
        _seed_workflow,
        _set_deterministic_mode,
    )

    set_ticket_time("2026-04-04T10:00:00+08:00")
    _set_deterministic_mode(client)
    workflow_id = _seed_workflow(client, "wf_scheduler_architect_gate", "Scheduler architect gate")
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
        ticket_prefix="scheduler_architect_gate",
    )
    _create_and_complete_backlog_recommendation_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_scheduler_backlog_parent",
        node_id="node_scheduler_backlog_parent",
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

    set_ticket_time("2026-04-04T10:01:05+08:00")
    run_scheduler_once(
        client.app.state.repository,
        idempotency_key="scheduler-runner:architect-gate",
        max_dispatches=10,
    )

    runs = client.app.state.repository.list_ceo_shadow_runs(workflow_id)
    idle_run = next(run for run in runs if run["trigger_type"] == SCHEDULER_IDLE_MAINTENANCE_TRIGGER)

    assert idle_run["snapshot"]["controller_state"]["state"] == "ARCHITECT_REQUIRED"
    assert idle_run["executed_actions"][0]["action_type"] == "HIRE_EMPLOYEE"


def test_scheduler_runner_idle_ceo_maintenance_creates_architect_governance_ticket_for_controller_gate(
    client,
    monkeypatch,
    set_ticket_time,
):
    from tests.test_ceo_scheduler import (
        _create_and_complete_backlog_recommendation_ticket,
        _create_and_complete_minimum_governance_chain,
        _persist_workflow_directive_details,
        _seed_board_approved_employee,
        _seed_workflow,
        _set_deterministic_mode,
    )

    set_ticket_time("2026-04-04T10:00:00+08:00")
    _set_deterministic_mode(client)
    workflow_id = _seed_workflow(client, "wf_scheduler_architect_doc_gate", "Scheduler architect doc gate")
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
        employee_id="emp_architect_scheduler_gate",
        role_type="governance_architect",
        role_profile_refs=["architect_primary"],
    )
    _seed_board_approved_employee(
        client,
        employee_id="emp_backend_scheduler_gate",
        role_type="backend_engineer",
        role_profile_refs=["backend_engineer_primary"],
    )
    monkeypatch.setattr("app.core.ticket_handlers._trigger_ceo_shadow_safely", lambda *args, **kwargs: None)
    _create_and_complete_minimum_governance_chain(
        client,
        workflow_id=workflow_id,
        ticket_prefix="scheduler_architect_doc_gate",
    )
    _create_and_complete_backlog_recommendation_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_scheduler_architect_doc_parent",
        node_id="node_scheduler_architect_doc_parent",
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

    set_ticket_time("2026-04-04T10:01:05+08:00")
    run_scheduler_once(
        client.app.state.repository,
        idempotency_key="scheduler-runner:architect-doc-gate",
        max_dispatches=10,
    )

    runs = client.app.state.repository.list_ceo_shadow_runs(workflow_id)
    idle_run = next(run for run in runs if run["trigger_type"] == SCHEDULER_IDLE_MAINTENANCE_TRIGGER)

    assert idle_run["snapshot"]["controller_state"]["state"] == "ARCHITECT_REQUIRED"
    assert idle_run["snapshot"]["controller_state"]["recommended_action"] == "CREATE_TICKET"
    assert idle_run["executed_actions"][0]["action_type"] == "CREATE_TICKET"

    created_ticket_id = idle_run["executed_actions"][0]["payload"]["ticket_id"]
    with client.app.state.repository.connection() as connection:
        created_spec = client.app.state.repository.get_latest_ticket_created_payload(connection, created_ticket_id)

    assert created_spec["role_profile_ref"] == "architect_primary"
    assert created_spec["output_schema_ref"] == ARCHITECTURE_BRIEF_SCHEMA_REF
    assert created_spec["dispatch_intent"]["assignee_employee_id"] == "emp_architect_scheduler_gate"


def test_scheduler_runner_idle_ceo_maintenance_creates_next_governance_document_ticket(
    client,
    monkeypatch,
    set_ticket_time,
):
    from tests.test_ceo_scheduler import (
        _create_and_complete_governance_ticket,
        _persist_workflow_directive_details,
        _seed_workflow,
        _set_deterministic_mode,
    )

    set_ticket_time("2026-04-04T10:00:00+08:00")
    _set_deterministic_mode(client)
    workflow_id = _seed_workflow(client, "wf_scheduler_governance_followup", "Scheduler governance followup")
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
        ticket_id="tkt_scheduler_architecture_doc",
        node_id="node_scheduler_architecture_doc",
        output_schema_ref=ARCHITECTURE_BRIEF_SCHEMA_REF,
        summary="Architecture brief is complete.",
    )

    set_ticket_time("2026-04-04T10:01:05+08:00")
    run_scheduler_once(
        client.app.state.repository,
        idempotency_key="scheduler-runner:governance-followup",
        max_dispatches=10,
    )

    runs = client.app.state.repository.list_ceo_shadow_runs(workflow_id)
    idle_run = next(run for run in runs if run["trigger_type"] == SCHEDULER_IDLE_MAINTENANCE_TRIGGER)

    assert idle_run["snapshot"]["controller_state"]["state"] == "GOVERNANCE_REQUIRED"
    assert idle_run["snapshot"]["controller_state"]["recommended_action"] == "CREATE_TICKET"
    assert idle_run["executed_actions"][0]["action_type"] == "CREATE_TICKET"

    created_ticket_id = idle_run["executed_actions"][0]["payload"]["ticket_id"]
    with client.app.state.repository.connection() as connection:
        created_spec = client.app.state.repository.get_latest_ticket_created_payload(connection, created_ticket_id)

    assert created_spec["output_schema_ref"] == TECHNOLOGY_DECISION_SCHEMA_REF


def test_scheduler_runner_skips_idle_ceo_maintenance_when_ticket_is_executing(
    client,
    monkeypatch,
    set_ticket_time,
):
    set_ticket_time("2026-04-04T10:00:00+08:00")
    monkeypatch.setattr(
        workflow_auto_advance_module,
        "run_leased_ticket_runtime",
        lambda _repository: [],
    )
    monkeypatch.setattr(
        client.app.state.repository,
        "list_scheduler_worker_candidates",
        lambda connection=None: [],
    )
    workflow_id = _project_init(client, goal="Scheduler executing workflow")
    scope_ticket_id = build_project_init_scope_ticket_id(workflow_id)
    scope_ticket = client.app.state.repository.get_current_ticket_projection(scope_ticket_id)
    assert scope_ticket is not None
    lease_response = None
    if scope_ticket["status"] == "PENDING":
        lease_response = client.post(
            "/api/v1/commands/ticket-lease",
            json={
                "workflow_id": workflow_id,
                "ticket_id": scope_ticket_id,
                "node_id": "node_scope_decision",
                "leased_by": "emp_frontend_2",
                "lease_timeout_sec": 600,
                "idempotency_key": f"ticket-lease:{workflow_id}:{scope_ticket_id}",
            },
        )
        assert lease_response.status_code == 200
        assert lease_response.json()["status"] == "ACCEPTED"
        scope_ticket = client.app.state.repository.get_current_ticket_projection(scope_ticket_id)
    start_response = None
    if scope_ticket["status"] == "LEASED":
        start_response = client.post(
            "/api/v1/commands/ticket-start",
            json={
                "workflow_id": workflow_id,
                "ticket_id": scope_ticket_id,
                "node_id": "node_scope_decision",
                "started_by": scope_ticket["lease_owner"] or "emp_frontend_2",
                "idempotency_key": f"ticket-start:{workflow_id}:{scope_ticket_id}",
            },
        )
        assert start_response.status_code == 200
        assert start_response.json()["status"] == "ACCEPTED"

    set_ticket_time("2026-04-04T10:01:05+08:00")
    run_scheduler_once(
        client.app.state.repository,
        idempotency_key="scheduler-runner:test-executing-no-maintenance",
        max_dispatches=10,
    )

    runs = client.app.state.repository.list_ceo_shadow_runs(workflow_id)
    assert not any(run["trigger_type"] == SCHEDULER_IDLE_MAINTENANCE_TRIGGER for run in runs)


def test_scheduler_runner_records_orchestration_trace_in_execution_order(client, monkeypatch, set_ticket_time):
    repository = client.app.state.repository
    set_ticket_time("2026-04-07T10:00:00+08:00")

    call_order: list[str] = []

    def _fake_run_due_ceo_maintenance(*args, **kwargs):
        call_order.append("ceo_maintenance")
        return [
            {
                "run_id": "ceo_trace_001",
                "workflow_id": "wf_trace_001",
                "trigger_type": SCHEDULER_IDLE_MAINTENANCE_TRIGGER,
            }
        ]

    def _fake_run_scheduler_tick(*args, **kwargs):
        call_order.append("scheduler_tick")
        return type(
            "Ack",
            (),
            {
                "status": "accepted",
                "idempotency_key": kwargs["idempotency_key"],
                "causation_hint": "scheduler:tick",
                "received_at": datetime.fromisoformat("2026-04-07T10:00:00+08:00"),
            },
        )()

    def _fake_run_leased_ticket_runtime(*args, **kwargs):
        call_order.append("runtime_execution")
        return [
            {
                "ticket_id": "tkt_trace_001",
                "lease_owner": "emp_frontend_2",
                "final_ack_status": "accepted",
            }
        ]

    monkeypatch.setattr("app.scheduler_runner.run_due_ceo_maintenance", _fake_run_due_ceo_maintenance)
    monkeypatch.setattr("app.scheduler_runner.run_scheduler_tick", _fake_run_scheduler_tick)
    monkeypatch.setattr("app.scheduler_runner.run_leased_ticket_runtime", _fake_run_leased_ticket_runtime)
    monkeypatch.setattr("app.scheduler_runner.maybe_run_artifact_cleanup", lambda *args, **kwargs: None)

    run_scheduler_once(
        repository,
        idempotency_key="scheduler-runner:test-orchestration-trace",
        max_dispatches=10,
    )

    trace_events = [
        event
        for event in repository.list_events_for_testing()
        if event["event_type"] == EVENT_SCHEDULER_ORCHESTRATION_RECORDED
    ]

    assert call_order == ["ceo_maintenance", "scheduler_tick", "runtime_execution"]
    assert len(trace_events) == 1
    assert trace_events[0]["payload"]["stage_order"] == [
        "collect_due_ceo_maintenance",
        "scheduler_tick",
        "runtime_execution",
        "record_orchestration_trace",
    ]
    assert trace_events[0]["payload"]["ceo_maintenance"]["run_ids"] == ["ceo_trace_001"]
    assert trace_events[0]["payload"]["runtime_execution"]["ticket_ids"] == ["tkt_trace_001"]


def test_provider_backed_scope_delivery_chain_completes_closeout_after_canonical_scope_seed(
    client,
    set_ticket_time,
    monkeypatch,
):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    monkeypatch.setenv("BOARDROOM_OS_PROVIDER_OPENAI_COMPAT_BASE_URL", "https://api-vip.codex-for.me/v1")
    monkeypatch.setenv("BOARDROOM_OS_PROVIDER_OPENAI_COMPAT_API_KEY", "provider-key")
    monkeypatch.setenv("BOARDROOM_OS_PROVIDER_OPENAI_COMPAT_MODEL", "gpt-5.3-codex")
    provider_responder, observed_schema_refs = _build_mock_provider_responder()
    monkeypatch.setattr(runtime_module, "invoke_openai_compat_response", provider_responder)
    monkeypatch.setattr(ceo_proposer_module, "invoke_openai_compat_response", provider_responder)

    workflow_id, scope_approval = api_test_helpers._project_init_to_scope_approval(client)
    workflow_id, final_review_approval, _ = api_test_helpers._complete_scope_followup_chain_to_visual_milestone(
        client,
        scope_approval,
        idempotency_suffix="provider-scope",
    )
    repository = client.app.state.repository
    _approve_review(client, final_review_approval, idempotency_suffix="provider-final-review")
    _, closeout_ticket_id, _ = api_test_helpers._complete_closeout_chain_after_final_review_approval(
        client,
        final_review_approval,
    )

    dashboard_response = client.get("/api/v1/projections/dashboard")
    assert dashboard_response.status_code == 200
    completion_summary = dashboard_response.json()["data"]["completion_summary"]

    closeout_ticket = repository.get_current_ticket_projection(closeout_ticket_id)
    assert closeout_ticket is not None
    assert closeout_ticket["status"] == "COMPLETED"
    assert completion_summary is None
    assert repository.list_open_approvals() == []
    assert repository.list_open_provider_incidents() == []
    assert observed_schema_refs
    assert set(observed_schema_refs) == {"ceo_action_batch"}


def test_timeout_incident_recovery_on_build_chain_still_reaches_closeout_completion(
    client,
    set_ticket_time,
    monkeypatch,
):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    workflow_id = _project_init(client, goal="Timeout recovery reaches completion")
    repository = client.app.state.repository
    scope_approval = _approval_by_type(repository, workflow_id, "MEETING_ESCALATION")
    build_followup = _followup_ticket_from_scope_approval(
        client,
        repository,
        scope_approval,
        delivery_stage="BUILD",
    )
    build_ticket_id = build_followup["ticket_id"]

    monkeypatch.setattr(
        workflow_auto_advance_module,
        "run_leased_ticket_runtime",
        lambda _repository: [],
    )
    _approve_review(client, scope_approval, idempotency_suffix="timeout-build-scope")

    build_ticket = repository.get_current_ticket_projection(build_ticket_id)
    assert build_ticket is not None
    assert build_ticket["status"] == "LEASED"

    client.post(
        "/api/v1/commands/ticket-start",
        json={
            "workflow_id": workflow_id,
            "ticket_id": build_ticket_id,
            "node_id": build_ticket["node_id"],
            "started_by": build_ticket["lease_owner"],
            "idempotency_key": f"ticket-start:{workflow_id}:{build_ticket_id}",
        },
    )

    set_ticket_time("2026-03-28T10:31:00+08:00")
    client.post(
        "/api/v1/commands/scheduler-tick",
        json={"max_dispatches": 10, "idempotency_key": "scheduler-tick:mainline-timeout-first"},
    )

    second_ticket_id = repository.get_current_node_projection(workflow_id, build_ticket["node_id"])["latest_ticket_id"]
    second_ticket = repository.get_current_ticket_projection(second_ticket_id)
    client.post(
        "/api/v1/commands/ticket-lease",
        json={
            "workflow_id": workflow_id,
            "ticket_id": second_ticket_id,
            "node_id": second_ticket["node_id"],
            "leased_by": "emp_frontend_2",
            "lease_timeout_sec": 600,
            "idempotency_key": f"ticket-lease:{workflow_id}:{second_ticket_id}",
        },
    )
    client.post(
        "/api/v1/commands/ticket-start",
        json={
            "workflow_id": workflow_id,
            "ticket_id": second_ticket_id,
            "node_id": second_ticket["node_id"],
            "started_by": "emp_frontend_2",
            "idempotency_key": f"ticket-start:{workflow_id}:{second_ticket_id}",
        },
    )

    set_ticket_time("2026-03-28T11:18:00+08:00")
    client.post(
        "/api/v1/commands/scheduler-tick",
        json={"max_dispatches": 10, "idempotency_key": "scheduler-tick:mainline-timeout-second"},
    )

    incident_id = [
        event["payload"]["incident_id"]
        for event in repository.list_events_for_testing()
        if event["event_type"] == "INCIDENT_OPENED"
    ][0]
    incident_response = client.get(f"/api/v1/projections/incidents/{incident_id}")

    monkeypatch.setattr(
        workflow_auto_advance_module,
        "run_leased_ticket_runtime",
        run_leased_ticket_runtime,
    )
    set_ticket_time("2026-03-28T11:20:00+08:00")
    resolve_response = client.post(
        "/api/v1/commands/incident-resolve",
        json={
            "incident_id": incident_id,
            "resolved_by": "emp_ops_1",
            "resolution_summary": "Retry after timeout mitigation.",
            "followup_action": "RESTORE_AND_RETRY_LATEST_TIMEOUT",
            "idempotency_key": "incident-resolve:mainline-timeout",
        },
    )
    recovered_incident_response = client.get(f"/api/v1/projections/incidents/{incident_id}")
    followup_ticket_id = repository.get_current_node_projection(workflow_id, build_ticket["node_id"])["latest_ticket_id"]
    followup_ticket = repository.get_current_ticket_projection(followup_ticket_id)

    set_ticket_time("2026-03-28T11:21:00+08:00")
    _run_scheduler_until_workflow_stop(
        repository,
        workflow_id=workflow_id,
        idempotency_key_prefix="scheduler-runner:mainline-timeout-recovery",
        before_each_run=lambda index: set_ticket_time(
            f"2026-03-28T11:{21 + index:02d}:00+08:00"
        ),
    )

    final_review_approval = _approval_by_type(repository, workflow_id, "VISUAL_MILESTONE")
    _approve_review(client, final_review_approval, idempotency_suffix="timeout-build-final-review")

    assert resolve_response.status_code == 200
    assert resolve_response.json()["status"] == "ACCEPTED"
    assert incident_response.status_code == 200
    assert recovered_incident_response.status_code == 200
    assert recovered_incident_response.json()["data"]["incident"]["payload"]["followup_action"] == (
        "RESTORE_AND_RETRY_LATEST_TIMEOUT"
    )
    assert followup_ticket["ticket_id"] not in {build_ticket_id, second_ticket_id}
    assert followup_ticket["retry_count"] == 2
    _assert_workflow_reaches_closeout_completion(
        client,
        workflow_id=workflow_id,
        final_review_approval=final_review_approval,
    )
    assert repository.list_open_incidents() == []
    assert repository.list_open_approvals() == []


def test_repeated_failure_incident_recovery_on_build_chain_still_reaches_closeout_completion(
    client,
    set_ticket_time,
    monkeypatch,
):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    workflow_id = _project_init(client, goal="Repeated failure recovery reaches completion")
    repository = client.app.state.repository
    scope_approval = _approval_by_type(repository, workflow_id, "MEETING_ESCALATION")
    build_followup = _followup_ticket_from_scope_approval(
        client,
        repository,
        scope_approval,
        delivery_stage="BUILD",
    )
    build_ticket_id = build_followup["ticket_id"]
    repeated_failure = {"step": "render", "exit_code": 1, "component": "hero"}

    monkeypatch.setattr(
        workflow_auto_advance_module,
        "run_leased_ticket_runtime",
        lambda _repository: [],
    )
    _approve_review(client, scope_approval, idempotency_suffix="repeat-failure-build-scope")

    first_ticket = repository.get_current_ticket_projection(build_ticket_id)
    client.post(
        "/api/v1/commands/ticket-start",
        json={
            "workflow_id": workflow_id,
            "ticket_id": build_ticket_id,
            "node_id": first_ticket["node_id"],
            "started_by": first_ticket["lease_owner"],
            "idempotency_key": f"ticket-start:{workflow_id}:{build_ticket_id}",
        },
    )
    client.post(
        "/api/v1/commands/ticket-fail",
        json={
            "workflow_id": workflow_id,
            "ticket_id": build_ticket_id,
            "node_id": first_ticket["node_id"],
            "failed_by": first_ticket["lease_owner"],
            "failure_kind": "RUNTIME_ERROR",
            "failure_message": "Primary hero render crashed.",
            "failure_detail": repeated_failure,
            "idempotency_key": f"ticket-fail:{workflow_id}:{build_ticket_id}:first",
        },
    )

    second_ticket_id = repository.get_current_node_projection(workflow_id, first_ticket["node_id"])["latest_ticket_id"]
    second_ticket = repository.get_current_ticket_projection(second_ticket_id)
    client.post(
        "/api/v1/commands/ticket-lease",
        json={
            "workflow_id": workflow_id,
            "ticket_id": second_ticket_id,
            "node_id": second_ticket["node_id"],
            "leased_by": "emp_frontend_2",
            "lease_timeout_sec": 600,
            "idempotency_key": f"ticket-lease:{workflow_id}:{second_ticket_id}",
        },
    )
    client.post(
        "/api/v1/commands/ticket-start",
        json={
            "workflow_id": workflow_id,
            "ticket_id": second_ticket_id,
            "node_id": second_ticket["node_id"],
            "started_by": "emp_frontend_2",
            "idempotency_key": f"ticket-start:{workflow_id}:{second_ticket_id}",
        },
    )
    client.post(
        "/api/v1/commands/ticket-fail",
        json={
            "workflow_id": workflow_id,
            "ticket_id": second_ticket_id,
            "node_id": second_ticket["node_id"],
            "failed_by": "emp_frontend_2",
            "failure_kind": "RUNTIME_ERROR",
            "failure_message": "Primary hero render crashed.",
            "failure_detail": repeated_failure,
            "idempotency_key": f"ticket-fail:{workflow_id}:{second_ticket_id}:second",
        },
    )

    incident_id = [
        event["payload"]["incident_id"]
        for event in repository.list_events_for_testing()
        if event["event_type"] == "INCIDENT_OPENED"
    ][0]
    incident_response = client.get(f"/api/v1/projections/incidents/{incident_id}")

    monkeypatch.setattr(
        workflow_auto_advance_module,
        "run_leased_ticket_runtime",
        run_leased_ticket_runtime,
    )
    resolve_response = client.post(
        "/api/v1/commands/incident-resolve",
        json={
            "incident_id": incident_id,
            "resolved_by": "emp_ops_1",
            "resolution_summary": "Retry after repeated failure mitigation.",
            "followup_action": "RESTORE_AND_RETRY_LATEST_FAILURE",
            "idempotency_key": "incident-resolve:mainline-repeated-failure",
        },
    )
    recovered_incident_response = client.get(f"/api/v1/projections/incidents/{incident_id}")
    followup_ticket_id = repository.get_current_node_projection(workflow_id, first_ticket["node_id"])["latest_ticket_id"]
    followup_ticket = repository.get_current_ticket_projection(followup_ticket_id)

    _run_scheduler_until_workflow_stop(
        repository,
        workflow_id=workflow_id,
        idempotency_key_prefix="scheduler-runner:mainline-repeated-failure-recovery",
        before_each_run=lambda index: set_ticket_time(
            f"2026-03-28T11:{21 + index:02d}:00+08:00"
        ),
    )

    final_review_approval = _approval_by_type(repository, workflow_id, "VISUAL_MILESTONE")
    _approve_review(client, final_review_approval, idempotency_suffix="repeat-failure-build-final-review")

    assert resolve_response.status_code == 200
    assert resolve_response.json()["status"] == "ACCEPTED"
    assert incident_response.status_code == 200
    assert recovered_incident_response.status_code == 200
    assert recovered_incident_response.json()["data"]["incident"]["payload"]["followup_action"] == (
        "RESTORE_AND_RETRY_LATEST_FAILURE"
    )
    assert followup_ticket["ticket_id"] not in {build_ticket_id, second_ticket_id}
    assert followup_ticket["retry_count"] == 2
    _assert_workflow_reaches_closeout_completion(
        client,
        workflow_id=workflow_id,
        final_review_approval=final_review_approval,
    )
    assert repository.list_open_incidents() == []
    assert repository.list_open_approvals() == []


def test_runtime_provider_auth_failure_does_not_open_provider_incident(client, set_ticket_time, monkeypatch):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    workflow_id = "wf_runner_provider_auth"
    repository = client.app.state.repository
    _seed_worker(repository, employee_id="emp_frontend_auth", provider_id="prov_openai_compat")
    _seed_runtime_leased_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_runner_provider_auth",
        node_id="node_runner_provider_auth",
        leased_by="emp_frontend_auth",
    )

    def _fake_provider_execute(execution_package, *args, **kwargs):
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
    with repository.connection() as connection:
        terminal_event = repository.get_latest_ticket_terminal_event(connection, "tkt_runner_provider_auth")

    assert [outcome.ticket_id for outcome in outcomes] == ["tkt_runner_provider_auth"]
    assert ticket_projection["status"] == "FAILED"
    assert terminal_event is not None
    assert terminal_event["payload"]["failure_kind"] == "PROVIDER_AUTH_FAILED"
    assert repository.list_open_provider_incidents() == []


def test_runtime_provider_bad_response_does_not_open_provider_incident(client, set_ticket_time, monkeypatch):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    workflow_id = "wf_runner_provider_bad_response"
    repository = client.app.state.repository
    _seed_worker(repository, employee_id="emp_frontend_bad_response", provider_id="prov_openai_compat")
    _seed_runtime_leased_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_runner_provider_bad_response",
        node_id="node_runner_provider_bad_response",
        leased_by="emp_frontend_bad_response",
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
    with repository.connection() as connection:
        terminal_event = repository.get_latest_ticket_terminal_event(connection, "tkt_runner_provider_bad_response")

    assert [outcome.ticket_id for outcome in outcomes] == ["tkt_runner_provider_bad_response"]
    assert ticket_projection["status"] == "FAILED"
    assert terminal_event is not None
    assert terminal_event["payload"]["failure_kind"] == "PROVIDER_BAD_RESPONSE"
    assert repository.list_open_provider_incidents() == []


def test_runtime_load_provider_payload_repairs_common_json_noise():
    payload = runtime_module._load_provider_payload(
        """```json
        {
          // provider side comment
          'summary': 'Recovered payload',
          'recommended_option_id': 'option_a',
          'options': [
            {
              'option_id': 'option_a',
              'label': 'Primary option',
              'summary': 'Recovered after cleanup',
            },
          ],
        }
        ```"""
    )

    assert payload["summary"] == "Recovered payload"
    assert payload["recommended_option_id"] == "option_a"
    assert payload["options"][0]["option_id"] == "option_a"


def test_runtime_load_provider_payload_reports_parse_stage_and_repairs_for_irreparable_json():
    with pytest.raises(OpenAICompatProviderBadResponseError) as exc_info:
        runtime_module._load_provider_payload(
            """```json
            {
              "summary": "Broken payload",
              "recommended_option_id": option_a,
            }
            ```"""
        )

    assert exc_info.value.failure_kind == "PROVIDER_BAD_RESPONSE"
    assert exc_info.value.failure_detail["parse_stage"] == "repair_parse"
    assert exc_info.value.failure_detail["repair_steps"] == [
        "strip_markdown_code_fence",
        "strip_bom",
        "strip_json_comments",
        "strip_trailing_commas",
    ]
    assert "parse_error" in exc_info.value.failure_detail


def test_runtime_provider_rate_limited_response_fails_ticket_without_opening_provider_incident(
    client,
    set_ticket_time,
    monkeypatch,
):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    workflow_id = _project_init(client, "Provider rate limit ticket failure")
    repository = client.app.state.repository
    _seed_worker(repository, employee_id="emp_frontend_rate_limited", provider_id="prov_openai_compat")
    _ensure_runtime_provider_ready_for_ticket(
        client,
        role_profile_ref="ui_designer_primary",
        output_schema_ref="ui_milestone_review",
    )

    client.post(
        "/api/v1/commands/ticket-create",
        json=_ticket_create_payload(
            workflow_id=workflow_id,
            ticket_id="tkt_runner_provider_live_rate_limit",
            node_id="node_runner_provider_live_rate_limit",
            role_profile_ref="ui_designer_primary",
        ),
    )
    client.post(
        "/api/v1/commands/ticket-lease",
        json={
            "workflow_id": workflow_id,
            "ticket_id": "tkt_runner_provider_live_rate_limit",
            "node_id": "node_runner_provider_live_rate_limit",
            "leased_by": "emp_frontend_rate_limited",
            "lease_timeout_sec": 600,
            "idempotency_key": "ticket-lease:wf_runner_provider_live_rate_limit:tkt_runner_provider_live_rate_limit",
        },
    )
    sleep_calls: list[float] = []

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
    monkeypatch.setattr(runtime_module, "_sleep", sleep_calls.append)

    outcomes = run_leased_ticket_runtime(repository)
    ticket_projection = repository.get_current_ticket_projection("tkt_runner_provider_live_rate_limit")
    open_provider_incidents = repository.list_open_provider_incidents()
    with repository.connection() as connection:
        terminal_event = repository.get_latest_ticket_terminal_event(connection, "tkt_runner_provider_live_rate_limit")

    assert [outcome.ticket_id for outcome in outcomes] == ["tkt_runner_provider_live_rate_limit"]
    assert ticket_projection["status"] == "FAILED"
    assert terminal_event is not None
    assert terminal_event["payload"]["failure_kind"] == "PROVIDER_RATE_LIMITED"
    assert sleep_calls == [1.0, 2.0, 4.0, 8.0, 16.0, 32.0, 60.0, 60.0, 60.0]
    assert open_provider_incidents == []


def test_runtime_provider_unavailable_failure_exhausts_ten_attempts_without_opening_provider_incident(
    client,
    set_ticket_time,
    monkeypatch,
):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    workflow_id = _project_init(client, "Provider unavailable exhaustion")
    repository = client.app.state.repository
    _seed_worker(repository, employee_id="emp_frontend_retry_exhausted", provider_id="prov_openai_compat")
    _ensure_runtime_provider_ready_for_ticket(
        client,
        role_profile_ref="ui_designer_primary",
        output_schema_ref="ui_milestone_review",
    )

    client.post(
        "/api/v1/commands/ticket-create",
        json=_ticket_create_payload(
            workflow_id=workflow_id,
            ticket_id="tkt_runner_provider_retry_exhausted",
            node_id="node_runner_provider_retry_exhausted",
            role_profile_ref="ui_designer_primary",
        ),
    )
    client.post(
        "/api/v1/commands/ticket-lease",
        json={
            "workflow_id": workflow_id,
            "ticket_id": "tkt_runner_provider_retry_exhausted",
            "node_id": "node_runner_provider_retry_exhausted",
            "leased_by": "emp_frontend_retry_exhausted",
            "lease_timeout_sec": 600,
            "idempotency_key": (
                "ticket-lease:wf_runner_provider_retry_exhausted:"
                "tkt_runner_provider_retry_exhausted"
            ),
        },
    )

    attempt_count = {"value": 0}
    sleep_calls: list[float] = []

    def _raise_unavailable(config, rendered_payload):
        attempt_count["value"] += 1
        raise OpenAICompatProviderUnavailableError(
            failure_kind="UPSTREAM_UNAVAILABLE",
            message="Provider transport failed.",
            failure_detail={
                "provider_id": "prov_openai_compat",
                "provider_transport_error": "ReadTimeout",
            },
        )

    monkeypatch.setattr(runtime_module, "invoke_openai_compat_response", _raise_unavailable)
    monkeypatch.setattr(runtime_module, "_sleep", sleep_calls.append)

    outcomes = run_leased_ticket_runtime(repository)
    ticket_projection = repository.get_current_ticket_projection("tkt_runner_provider_retry_exhausted")
    open_provider_incidents = repository.list_open_provider_incidents()
    with repository.connection() as connection:
        terminal_event = repository.get_latest_ticket_terminal_event(connection, "tkt_runner_provider_retry_exhausted")

    assert [outcome.ticket_id for outcome in outcomes] == ["tkt_runner_provider_retry_exhausted"]
    assert ticket_projection["status"] == "FAILED"
    assert terminal_event is not None
    assert terminal_event["payload"]["failure_kind"] == "UPSTREAM_UNAVAILABLE"
    assert attempt_count["value"] == 10
    assert sleep_calls == [1.0, 2.0, 4.0, 8.0, 16.0, 32.0, 60.0, 60.0, 60.0]
    assert open_provider_incidents == []


def test_runtime_provider_rate_limit_failover_uses_fallback_provider_before_deterministic(
    client,
    set_ticket_time,
    monkeypatch,
):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    workflow_id = _seed_runtime_workflow(client, "wf_runner_provider_failover", "Provider failover")
    repository = client.app.state.repository
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
                    capability_tags=["structured_output", "planning", "implementation"],
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
    _seed_worker(repository, employee_id="emp_frontend_failover", provider_id=OPENAI_COMPAT_PROVIDER_ID)

    client.post(
        "/api/v1/commands/ticket-create",
        json=_ticket_create_payload(
            workflow_id=workflow_id,
            ticket_id="tkt_runner_provider_failover",
            node_id="node_runner_provider_failover",
            role_profile_ref="ui_designer_primary",
        ),
    )
    client.post(
        "/api/v1/commands/ticket-lease",
        json={
            "workflow_id": workflow_id,
            "ticket_id": "tkt_runner_provider_failover",
            "node_id": "node_runner_provider_failover",
            "leased_by": "emp_frontend_failover",
            "lease_timeout_sec": 600,
            "idempotency_key": "ticket-lease:wf_runner_provider_failover:tkt_runner_provider_failover",
        },
    )

    openai_attempts = {"value": 0}
    monkeypatch.setattr(runtime_module, "_sleep", lambda _delay: None)

    def _raise_rate_limited(config, rendered_payload):
        openai_attempts["value"] += 1
        raise OpenAICompatProviderRateLimitedError(
            failure_kind="PROVIDER_RATE_LIMITED",
            message="Provider quota exhausted.",
            failure_detail={
                "provider_status_code": 429,
                "provider_id": "prov_openai_compat",
            },
        )

    def _fake_claude(config, rendered_payload):
        return type(
            "ClaudeResult",
            (),
            {
                "output_text": json.dumps(
                    {
                        "summary": "Claude failover completed the ticket.",
                        "recommended_option_id": "option_a",
                        "options": [
                            {
                                "option_id": "option_a",
                                "label": "Option A",
                                "summary": "Failover option from Claude.",
                                "artifact_refs": [],
                            }
                        ],
                    }
                ),
                "response_id": None,
            },
        )()

    monkeypatch.setattr(runtime_module, "invoke_openai_compat_response", _raise_rate_limited)
    monkeypatch.setattr(runtime_module, "invoke_claude_code_response", _fake_claude)
    recorded_submit: dict[str, object] = {}
    original_submit = runtime_module.handle_ticket_result_submit

    def _record_submit(repository_arg, payload, developer_inspector_store=None, artifact_store=None):
        recorded_submit["assumptions"] = list(payload.assumptions)
        recorded_submit["issues"] = list(payload.issues)
        return original_submit(
            repository_arg,
            payload,
            developer_inspector_store=developer_inspector_store,
            artifact_store=artifact_store,
        )

    monkeypatch.setattr(runtime_module, "handle_ticket_result_submit", _record_submit)

    outcomes = run_leased_ticket_runtime(repository)
    ticket_projection = repository.get_current_ticket_projection("tkt_runner_provider_failover")
    open_provider_incidents = repository.list_open_provider_incidents()

    assert [outcome.ticket_id for outcome in outcomes] == ["tkt_runner_provider_failover"]
    assert ticket_projection["status"] == "COMPLETED"
    assert openai_attempts["value"] == 10
    assert open_provider_incidents == []
    assert "preferred_provider_id=prov_openai_compat" in recorded_submit["assumptions"]
    assert "preferred_model=gpt-5.3-codex" in recorded_submit["assumptions"]
    assert "actual_provider_id=prov_claude_code" in recorded_submit["assumptions"]
    assert "actual_model=claude-sonnet-4-6" in recorded_submit["assumptions"]
    assert "effective_reasoning_effort=high" in recorded_submit["assumptions"]
    assert "selection_reason=provider_failover" in recorded_submit["assumptions"]
    assert any("failover" in issue.lower() for issue in recorded_submit["issues"])


def test_runtime_provider_retries_then_succeeds(client, set_ticket_time, monkeypatch):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    workflow_id = _project_init(client, "Provider retry recovery")
    monkeypatch.setenv("BOARDROOM_OS_PROVIDER_OPENAI_COMPAT_BASE_URL", "https://api-vip.codex-for.me/v1")
    monkeypatch.setenv("BOARDROOM_OS_PROVIDER_OPENAI_COMPAT_API_KEY", "provider-key")
    monkeypatch.setenv("BOARDROOM_OS_PROVIDER_OPENAI_COMPAT_MODEL", "gpt-5.3-codex")
    repository = client.app.state.repository
    _seed_worker(repository, employee_id="emp_frontend_retry", provider_id="prov_openai_compat")

    client.post(
        "/api/v1/commands/ticket-create",
        json=_ticket_create_payload(
            workflow_id=workflow_id,
            ticket_id="tkt_runner_provider_retry",
            node_id="node_runner_provider_retry",
            role_profile_ref="ui_designer_primary",
        ),
    )
    client.post(
        "/api/v1/commands/ticket-lease",
        json={
            "workflow_id": workflow_id,
            "ticket_id": "tkt_runner_provider_retry",
            "node_id": "node_runner_provider_retry",
            "leased_by": "emp_frontend_retry",
            "lease_timeout_sec": 600,
            "idempotency_key": "ticket-lease:wf_runner_provider_retry:tkt_runner_provider_retry",
        },
    )

    attempt_count = {"value": 0}
    sleep_calls: list[float] = []

    def _invoke_retry_then_success(config, rendered_payload):
        attempt_count["value"] += 1
        if attempt_count["value"] < 10:
            raise OpenAICompatProviderUnavailableError(
                failure_kind="UPSTREAM_UNAVAILABLE",
                message="Provider returned 503.",
                failure_detail={
                    "provider_id": "prov_openai_compat",
                    "provider_status_code": 503,
                },
            )
        return OpenAICompatProviderResult(
            output_text=json.dumps(
                {
                    "summary": "Provider succeeded after retries.",
                    "recommended_option_id": "option_a",
                    "options": [
                        {
                            "option_id": "option_a",
                            "label": "Option A",
                            "summary": "Recovered provider option.",
                            "artifact_refs": [],
                        }
                    ],
                }
            ),
            response_id="resp_retry_success",
        )

    monkeypatch.setattr(runtime_module, "invoke_openai_compat_response", _invoke_retry_then_success)
    monkeypatch.setattr(runtime_module, "_sleep", sleep_calls.append)

    outcomes = run_leased_ticket_runtime(repository)
    ticket_projection = repository.get_current_ticket_projection("tkt_runner_provider_retry")

    assert [outcome.ticket_id for outcome in outcomes] == ["tkt_runner_provider_retry"]
    assert ticket_projection["status"] == "COMPLETED"
    assert attempt_count["value"] == 10
    assert sleep_calls == [1.0, 2.0, 4.0, 8.0, 16.0, 32.0, 60.0, 60.0, 60.0]
    assert repository.list_open_provider_incidents() == []


def test_runtime_without_configured_provider_blocks_lease_instead_of_using_deterministic_path(
    client,
    set_ticket_time,
):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    workflow_id = "wf_runner_provider_required"
    repository = client.app.state.repository
    _seed_worker(repository, employee_id="emp_frontend_missing_provider", provider_id=OPENAI_COMPAT_PROVIDER_ID)
    api_test_helpers._ensure_scoped_workflow(
        client,
        workflow_id=workflow_id,
        tenant_id="tenant_default",
        workspace_id="ws_default",
        goal="Provider required failure",
    )
    api_test_helpers._seed_created_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_runner_provider_required",
        node_id="node_runner_provider_required",
        role_profile_ref="ui_designer_primary",
        output_schema_ref="ui_milestone_review",
    )
    lease_response = client.post(
        "/api/v1/commands/ticket-lease",
        json={
            "workflow_id": workflow_id,
            "ticket_id": "tkt_runner_provider_required",
            "node_id": "node_runner_provider_required",
            "leased_by": "emp_frontend_missing_provider",
            "lease_timeout_sec": 600,
            "idempotency_key": "ticket-lease:wf_runner_provider_required:tkt_runner_provider_required",
        },
    )

    ticket_projection = repository.get_current_ticket_projection("tkt_runner_provider_required")

    assert lease_response.status_code == 200
    assert lease_response.json()["status"] == "REJECTED"
    assert "no live provider was available" in str(lease_response.json()["reason"] or "").lower()
    assert ticket_projection["status"] == "PENDING"
    assert repository.list_open_provider_incidents() == []


def test_runtime_provider_auth_failure_fails_closed_without_provider_failover(
    client,
    set_ticket_time,
    monkeypatch,
):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    workflow_id = "wf_runner_provider_auth_no_failover"
    repository = client.app.state.repository
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
                    capability_tags=["structured_output", "planning", "implementation"],
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
    _seed_worker(repository, employee_id="emp_frontend_auth_no_failover", provider_id=OPENAI_COMPAT_PROVIDER_ID)
    _seed_runtime_leased_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_runner_provider_auth_no_failover",
        node_id="node_runner_provider_auth_no_failover",
        leased_by="emp_frontend_auth_no_failover",
        configure_provider=False,
    )

    monkeypatch.setattr(
        runtime_module,
        "invoke_openai_compat_response",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            OpenAICompatProviderAuthError(
                failure_kind="PROVIDER_AUTH_FAILED",
                message="Provider rejected the configured API key.",
                failure_detail={
                    "provider_status_code": 401,
                    "provider_id": OPENAI_COMPAT_PROVIDER_ID,
                },
            )
        ),
    )
    monkeypatch.setattr(
        runtime_module,
        "invoke_claude_code_response",
        lambda *args, **kwargs: pytest.fail("Claude fallback should not run for provider auth failures"),
    )
    recorded_submit: dict[str, object] = {}
    original_submit = runtime_module.handle_ticket_result_submit

    def _record_submit(repository_arg, payload, developer_inspector_store=None, artifact_store=None):
        recorded_submit["assumptions"] = list(payload.assumptions)
        recorded_submit["failure_detail"] = dict(payload.failure_detail or {})
        return original_submit(
            repository_arg,
            payload,
            developer_inspector_store=developer_inspector_store,
            artifact_store=artifact_store,
        )

    monkeypatch.setattr(runtime_module, "handle_ticket_result_submit", _record_submit)

    outcomes = run_leased_ticket_runtime(repository)
    ticket_projection = repository.get_current_ticket_projection("tkt_runner_provider_auth_no_failover")
    with repository.connection() as connection:
        terminal_event = repository.get_latest_ticket_terminal_event(connection, "tkt_runner_provider_auth_no_failover")

    assert [outcome.ticket_id for outcome in outcomes] == ["tkt_runner_provider_auth_no_failover"]
    assert ticket_projection["status"] == "FAILED"
    assert terminal_event is not None
    assert terminal_event["payload"]["failure_kind"] == "PROVIDER_AUTH_FAILED"
    assert repository.list_open_provider_incidents() == []
    assert recorded_submit["failure_detail"]["fallback_blocked"] is True
    assert recorded_submit["failure_detail"]["provider_candidate_chain"] == [
        OPENAI_COMPAT_PROVIDER_ID,
        CLAUDE_CODE_PROVIDER_ID,
    ]
    assert [item["provider_id"] for item in recorded_submit["failure_detail"]["provider_attempt_log"]] == [
        OPENAI_COMPAT_PROVIDER_ID
    ]
    assert [item["failure_kind"] for item in recorded_submit["failure_detail"]["provider_attempt_log"]] == [
        "PROVIDER_AUTH_FAILED"
    ]
    assert not any("prov_claude_code" in assumption for assumption in recorded_submit["assumptions"])


def test_runtime_provider_paused_ticket_blocks_runtime_start_without_deterministic_completion(
    client,
    set_ticket_time,
    monkeypatch,
):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    workflow_id = "wf_runner_provider_paused_fallback"
    pause_seed_workflow_id = "wf_runner_provider_pause_seed"
    monkeypatch.setenv("BOARDROOM_OS_PROVIDER_OPENAI_COMPAT_BASE_URL", "https://api-vip.codex-for.me/v1")
    monkeypatch.setenv("BOARDROOM_OS_PROVIDER_OPENAI_COMPAT_API_KEY", "provider-key")
    monkeypatch.setenv("BOARDROOM_OS_PROVIDER_OPENAI_COMPAT_MODEL", "gpt-5.3-codex")
    repository = client.app.state.repository
    _seed_worker(repository, employee_id="emp_frontend_paused", provider_id="prov_openai_compat")
    _seed_runtime_leased_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_runner_provider_paused_fallback",
        node_id="node_runner_provider_paused_fallback",
        leased_by="emp_frontend_paused",
    )
    _seed_runtime_leased_ticket(
        client,
        workflow_id=pause_seed_workflow_id,
        ticket_id="tkt_runner_provider_pause_seed",
        node_id="node_runner_provider_pause_seed",
        leased_by="emp_frontend_paused",
    )
    client.post(
        "/api/v1/commands/ticket-start",
        json={
            "workflow_id": pause_seed_workflow_id,
            "ticket_id": "tkt_runner_provider_pause_seed",
            "node_id": "node_runner_provider_pause_seed",
            "started_by": "emp_frontend_paused",
            "idempotency_key": "ticket-start:wf_runner_provider_pause_seed:tkt_runner_provider_pause_seed",
        },
    )
    client.post(
        "/api/v1/commands/ticket-fail",
        json={
            "workflow_id": pause_seed_workflow_id,
            "ticket_id": "tkt_runner_provider_pause_seed",
            "node_id": "node_runner_provider_pause_seed",
            "failed_by": "emp_frontend_paused",
            "failure_kind": "PROVIDER_RATE_LIMITED",
            "failure_message": "Provider quota exhausted.",
            "failure_detail": {
                "provider_id": "prov_openai_compat",
                "provider_status_code": 429,
            },
            "idempotency_key": "ticket-fail:wf_runner_provider_pause_seed:tkt_runner_provider_pause_seed",
        },
    )
    with repository.transaction() as connection:
        repository.insert_event(
            connection,
            event_type="INCIDENT_OPENED",
            actor_type="system",
            actor_id="runtime",
            workflow_id=pause_seed_workflow_id,
            idempotency_key="test-incident-opened:wf_runner_provider_pause_seed:provider-open",
            causation_id=None,
            correlation_id=pause_seed_workflow_id,
            payload={
                "incident_id": "inc_runner_provider_pause_seed",
                "ticket_id": "tkt_runner_provider_pause_seed",
                "node_id": "node_runner_provider_pause_seed",
                "provider_id": "prov_openai_compat",
                "incident_type": "PROVIDER_EXECUTION_PAUSED",
                "status": "OPEN",
                "severity": "high",
                "fingerprint": "provider:prov_openai_compat",
                "pause_reason": "PROVIDER_RATE_LIMITED",
                "latest_failure_kind": "PROVIDER_RATE_LIMITED",
                "latest_failure_message": "Provider quota exhausted.",
                "latest_failure_fingerprint": "PROVIDER_RATE_LIMITED",
            },
            occurred_at=datetime.fromisoformat("2026-03-28T10:02:00+08:00"),
        )
        repository.insert_event(
            connection,
            event_type="CIRCUIT_BREAKER_OPENED",
            actor_type="system",
            actor_id="runtime",
            workflow_id=pause_seed_workflow_id,
            idempotency_key="test-breaker-opened:wf_runner_provider_pause_seed:provider-open",
            causation_id=None,
            correlation_id=pause_seed_workflow_id,
            payload={
                "incident_id": "inc_runner_provider_pause_seed",
                "ticket_id": "tkt_runner_provider_pause_seed",
                "node_id": "node_runner_provider_pause_seed",
                "provider_id": "prov_openai_compat",
                "circuit_breaker_state": "OPEN",
                "fingerprint": "provider:prov_openai_compat",
            },
            occurred_at=datetime.fromisoformat("2026-03-28T10:02:00+08:00"),
        )
        repository.refresh_projections(connection)

    called_live_path = {"value": 0}
    monkeypatch.setattr(
        runtime_module,
        "invoke_openai_compat_response",
        lambda config, rendered_payload: called_live_path.__setitem__("value", called_live_path["value"] + 1),
    )

    outcomes = run_leased_ticket_runtime(repository)
    ticket_projection = repository.get_current_ticket_projection("tkt_runner_provider_paused_fallback")
    open_provider_incidents = repository.list_open_provider_incidents()
    with repository.connection() as connection:
        terminal_event = repository.get_latest_ticket_terminal_event(connection, "tkt_runner_provider_paused_fallback")

    assert [outcome.ticket_id for outcome in outcomes] == ["tkt_runner_provider_paused_fallback"]
    assert outcomes[0].start_ack.status.value == "REJECTED"
    assert outcomes[0].final_ack is None
    assert ticket_projection["status"] == "PENDING"
    assert ticket_projection["blocking_reason_code"] == "PROVIDER_REQUIRED"
    assert called_live_path["value"] == 0
    assert terminal_event is None
    assert len(open_provider_incidents) == 1
    assert open_provider_incidents[0]["provider_id"] == "prov_openai_compat"


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


def test_scheduler_runner_auto_recovers_open_provider_incident_for_autopilot_workflow(
    client,
    set_ticket_time,
    monkeypatch,
):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    from tests.test_ceo_scheduler import (
        _persist_workflow_directive_details,
        _seed_workflow,
    )

    workflow_id = _seed_workflow(
        client,
        "wf_runner_provider_recovery",
        goal="Autopilot runner provider recovery",
    )
    _persist_workflow_directive_details(
        client.app.state.repository,
        workflow_id,
        workflow_profile="CEO_AUTOPILOT_FINE_GRAINED",
        hard_constraints=[
            "Keep governance explicit.",
            "Allow CEO delegate to keep the workflow moving.",
        ],
    )

    repository = client.app.state.repository
    _ensure_runtime_provider_ready_for_ticket(
        client,
        role_profile_ref="ui_designer_primary",
        output_schema_ref="ui_milestone_review",
    )
    create_source_response = client.post(
        "/api/v1/commands/ticket-create",
        json=_ticket_create_payload(
            workflow_id=workflow_id,
            ticket_id="tkt_runner_provider_source_completed",
            node_id="node_runner_provider_source_completed",
            role_profile_ref="ui_designer_primary",
        ),
    )
    lease_source_response = client.post(
        "/api/v1/commands/scheduler-tick",
        json={
            "max_dispatches": 10,
            "idempotency_key": "scheduler-tick:runner-provider-source",
        },
    )
    source_ticket = repository.get_current_ticket_projection("tkt_runner_provider_source_completed")
    assert source_ticket is not None
    start_source_response = client.post(
        "/api/v1/commands/ticket-start",
        json={
            "workflow_id": workflow_id,
            "ticket_id": source_ticket["ticket_id"],
            "node_id": source_ticket["node_id"],
            "started_by": source_ticket["lease_owner"],
            "idempotency_key": f"ticket-start:{workflow_id}:{source_ticket['ticket_id']}",
        },
    )

    with repository.transaction() as connection:
        repository.insert_event(
            connection,
            event_type="INCIDENT_OPENED",
            actor_type="system",
            actor_id="runtime",
            workflow_id=workflow_id,
            idempotency_key=f"test-incident-opened:{workflow_id}:provider-open",
            causation_id=None,
            correlation_id=workflow_id,
            payload={
                "incident_id": "inc_runner_provider_open",
                "ticket_id": source_ticket["ticket_id"],
                "node_id": source_ticket["node_id"],
                "provider_id": "prov_openai_compat",
                "incident_type": "PROVIDER_EXECUTION_PAUSED",
                "status": "OPEN",
                "severity": "high",
                "fingerprint": "provider:prov_openai_compat",
                "pause_reason": "UPSTREAM_UNAVAILABLE",
                "latest_failure_kind": "UPSTREAM_UNAVAILABLE",
                "latest_failure_message": "Provider transport failed after fallback completion.",
                "latest_failure_fingerprint": "UPSTREAM_UNAVAILABLE",
            },
            occurred_at=datetime.fromisoformat("2026-03-28T10:02:00+08:00"),
        )
        repository.insert_event(
            connection,
            event_type="CIRCUIT_BREAKER_OPENED",
            actor_type="system",
            actor_id="runtime",
            workflow_id=workflow_id,
            idempotency_key=f"test-breaker-opened:{workflow_id}:provider-open",
            causation_id=None,
            correlation_id=workflow_id,
            payload={
                "incident_id": "inc_runner_provider_open",
                "ticket_id": source_ticket["ticket_id"],
                "node_id": source_ticket["node_id"],
                "provider_id": "prov_openai_compat",
                "circuit_breaker_state": "OPEN",
                "fingerprint": "provider:prov_openai_compat",
            },
            occurred_at=datetime.fromisoformat("2026-03-28T10:02:00+08:00"),
        )
        repository.insert_event(
            connection,
            event_type="TICKET_COMPLETED",
            actor_type="worker",
            actor_id=str(source_ticket["lease_owner"]),
            workflow_id=workflow_id,
            idempotency_key=f"test-ticket-completed:{workflow_id}:{source_ticket['ticket_id']}",
            causation_id=None,
            correlation_id=workflow_id,
            payload={
                "ticket_id": source_ticket["ticket_id"],
                "node_id": source_ticket["node_id"],
                "completion_summary": "Source ticket completed through fallback execution.",
                "artifact_refs": [],
                "produced_process_assets": [],
                "documentation_updates": [],
                "board_review_requested": False,
            },
            occurred_at=datetime.fromisoformat("2026-03-28T10:02:01+08:00"),
        )
        repository.refresh_projections(connection)

    create_blocked_response = client.post(
        "/api/v1/commands/ticket-create",
        json=_ticket_create_payload(
            workflow_id=workflow_id,
            ticket_id="tkt_runner_provider_blocked",
            node_id="node_runner_provider_blocked",
            role_profile_ref="ui_designer_primary",
        ),
    )

    monkeypatch.setattr(
        runtime_module,
        "invoke_openai_compat_response",
        lambda *_args, **_kwargs: OpenAICompatProviderResult(
            output_text=json.dumps(_mock_provider_payload_for_schema("ui_milestone_review")),
            response_id="resp_ui_milestone_review_recovered",
        ),
    )

    run_scheduler_once(
        repository,
        idempotency_key="scheduler-runner:test-autopilot-provider-recovery",
        max_dispatches=10,
    )

    recovered_incident = repository.get_incident_projection("inc_runner_provider_open")
    blocked_ticket = repository.get_current_ticket_projection("tkt_runner_provider_blocked")

    assert create_source_response.status_code == 200
    assert create_source_response.json()["status"] == "ACCEPTED"
    assert lease_source_response.status_code == 200
    assert lease_source_response.json()["status"] == "ACCEPTED"
    assert start_source_response.status_code == 200
    assert start_source_response.json()["status"] == "ACCEPTED"
    assert create_blocked_response.status_code == 200
    assert create_blocked_response.json()["status"] == "ACCEPTED"
    assert recovered_incident is not None
    assert recovered_incident["status"] == "RECOVERING"
    assert recovered_incident["circuit_breaker_state"] == "CLOSED"
    assert recovered_incident["payload"]["followup_action"] == "RESTORE_ONLY"
    assert blocked_ticket is not None
    assert blocked_ticket["status"] == "COMPLETED"


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


def test_scheduler_relaxes_excluded_employee_ids_for_single_capable_rework_fix_worker(client):
    workflow_id = _project_init(client, "Singleton rework fix routing")
    repository = client.app.state.repository
    with repository.transaction() as connection:
        repository.insert_event(
            connection,
            event_type=EVENT_TICKET_CREATED,
            actor_type="system",
            actor_id="test-seed",
            workflow_id=workflow_id,
            idempotency_key="ticket-created:singleton-rework-fix",
            causation_id=None,
            correlation_id=workflow_id,
            payload={
                **_ticket_create_payload(
                    workflow_id=workflow_id,
                    ticket_id="tkt_runner_singleton_rework_fix",
                    node_id="node_runner_singleton_rework_fix",
                    role_profile_ref="frontend_engineer_primary",
                    output_schema_ref="source_code_delivery",
                    excluded_employee_ids=["emp_frontend_2"],
                    allowed_tools=["read_artifact", "write_artifact", "image_gen"],
                    allowed_write_set=["artifacts/ui/scope-followups/tkt_runner_singleton_rework_fix/*"],
                    acceptance_criteria=[
                        "Must implement the approved scope follow-up.",
                        "Must produce a structured source code delivery.",
                    ],
                ),
                "ticket_kind": "MAKER_REWORK_FIX",
            },
            occurred_at=datetime.fromisoformat("2026-03-28T10:00:00+08:00"),
        )
        repository.refresh_projections(connection)

    run_scheduler_once(
        repository,
        idempotency_key="scheduler-runner:test-singleton-rework-fix",
        max_dispatches=10,
    )

    ticket_projection = repository.get_current_ticket_projection("tkt_runner_singleton_rework_fix")
    leased_events = [
        event
        for event in repository.list_events_for_testing()
        if event["event_type"] == "TICKET_LEASED"
        and event["payload"].get("ticket_id") == "tkt_runner_singleton_rework_fix"
    ]

    assert ticket_projection is not None
    assert ticket_projection["status"] == "COMPLETED"
    assert leased_events[-1]["payload"]["leased_by"] == "emp_frontend_2"


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


def test_scheduler_redispatches_restored_requeued_ticket_to_original_employee(client, set_ticket_time):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    workflow_id = _project_init(client, "Restored requeued ticket dispatch")

    client.post(
        "/api/v1/commands/ticket-create",
        json=_ticket_create_payload(
            workflow_id=workflow_id,
            ticket_id="tkt_runner_restored_requeued",
            node_id="node_runner_restored_requeued",
            role_profile_ref="ui_designer_primary",
            excluded_employee_ids=["emp_frontend_backup"],
        ),
    )
    client.post(
        "/api/v1/commands/ticket-lease",
        json={
            "workflow_id": workflow_id,
            "ticket_id": "tkt_runner_restored_requeued",
            "node_id": "node_runner_restored_requeued",
            "leased_by": "emp_frontend_2",
            "lease_timeout_sec": 600,
            "idempotency_key": "ticket-lease:restored-requeued:emp_frontend_2",
        },
    )
    client.post(
        "/api/v1/commands/employee-freeze",
        json={
            "workflow_id": workflow_id,
            "employee_id": "emp_frontend_2",
            "frozen_by": "ops@example.com",
            "reason": "Pause worker before restore test.",
            "idempotency_key": f"employee-freeze:{workflow_id}:emp_frontend_2:restored-requeued",
        },
    )
    restore_response = client.post(
        "/api/v1/commands/employee-restore",
        json={
            "workflow_id": workflow_id,
            "employee_id": "emp_frontend_2",
            "restored_by": "ops@example.com",
            "reason": "Worker is back on duty.",
            "idempotency_key": f"employee-restore:{workflow_id}:emp_frontend_2:restored-requeued",
        },
    )

    assert restore_response.status_code == 200
    assert restore_response.json()["status"] == "ACCEPTED"

    run_scheduler_once(
        client.app.state.repository,
        idempotency_key="scheduler-runner:test-restored-requeued",
        max_dispatches=10,
    )

    repository = client.app.state.repository
    ticket_projection = repository.get_current_ticket_projection("tkt_runner_restored_requeued")
    with repository.connection() as connection:
        latest_created_spec = repository.get_latest_ticket_created_payload(
            connection,
            "tkt_runner_restored_requeued",
        )
    leased_events = [
        event
        for event in repository.list_events_for_testing()
        if event["event_type"] == "TICKET_LEASED"
        and event["payload"].get("ticket_id") == "tkt_runner_restored_requeued"
    ]

    assert ticket_projection["status"] == "COMPLETED"
    assert leased_events[-1]["payload"]["leased_by"] == "emp_frontend_2"
    assert latest_created_spec["excluded_employee_ids"] == ["emp_frontend_backup"]
