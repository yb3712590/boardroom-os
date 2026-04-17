from __future__ import annotations

import base64
import json
import sqlite3
import subprocess
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.contracts.advisory import GraphPatchProposal
from app.core.ceo_snapshot import build_ceo_shadow_snapshot
from app.core.ceo_execution_presets import build_project_init_scope_ticket_id
from app.core.context_compiler import compile_and_persist_execution_artifacts
from app.core.execution_targets import (
    EXECUTION_TARGET_ARCHITECT_GOVERNANCE_DOCUMENT,
    infer_execution_contract_payload,
)
from app.core.governance_profiles import build_default_governance_profile
from app.core.output_schemas import SOURCE_CODE_DELIVERY_SCHEMA_REF
from app.core.ticket_graph import build_ticket_graph_snapshot
from app.core.workflow_auto_advance import auto_advance_workflow_to_next_stop
from app.core.provider_openai_compat import OpenAICompatProviderResult
from app.core.runtime_provider_config import (
    OPENAI_COMPAT_PROVIDER_ID,
    RuntimeProviderConfigEntry,
    RuntimeProviderStoredConfig,
)
from app.core.process_assets import (
    build_closeout_summary_process_asset_ref,
    build_meeting_decision_process_asset_ref,
    build_source_code_delivery_process_asset_ref,
)
from app.core.constants import (
    APPROVAL_STATUS_APPROVED,
    APPROVAL_STATUS_MODIFIED_CONSTRAINTS,
    APPROVAL_STATUS_OPEN,
    APPROVAL_STATUS_REJECTED,
    BLOCKING_REASON_BOARD_REJECTED,
    BLOCKING_REASON_BOARD_REVIEW_REQUIRED,
    BLOCKING_REASON_MODIFY_CONSTRAINTS,
    BLOCKING_REASON_PROVIDER_REQUIRED,
    EVENT_BOARD_DIRECTIVE_RECEIVED,
    EVENT_BOARD_REVIEW_APPROVED,
    EVENT_BOARD_REVIEW_REJECTED,
    EVENT_BOARD_REVIEW_REQUIRED,
    EVENT_EMPLOYEE_HIRED,
    EVENT_ARTIFACT_CLEANUP_COMPLETED,
    EVENT_CIRCUIT_BREAKER_OPENED,
    EVENT_GRAPH_PATCH_APPLIED,
    EVENT_INCIDENT_OPENED,
    EVENT_INCIDENT_RECOVERY_STARTED,
    INCIDENT_TYPE_CEO_SHADOW_PIPELINE_FAILED,
    INCIDENT_TYPE_PLANNED_PLACEHOLDER_GATE_BLOCKED,
    EVENT_SYSTEM_INITIALIZED,
    EVENT_TICKET_CANCELLED,
    EVENT_TICKET_CANCEL_REQUESTED,
    EVENT_TICKET_COMPLETED,
    EVENT_TICKET_CREATED,
    EVENT_TICKET_EXECUTION_PRECONDITION_BLOCKED,
    EVENT_TICKET_EXECUTION_PRECONDITION_CLEARED,
    EVENT_TICKET_FAILED,
    EVENT_TICKET_HEARTBEAT_RECORDED,
    EVENT_TICKET_LEASED,
    EVENT_TICKET_RETRY_SCHEDULED,
    EVENT_TICKET_STARTED,
    EVENT_TICKET_TIMED_OUT,
    EVENT_WORKFLOW_CREATED,
    NODE_STATUS_BLOCKED_FOR_BOARD_REVIEW,
    NODE_STATUS_CANCELLED,
    NODE_STATUS_CANCEL_REQUESTED,
    NODE_STATUS_COMPLETED,
    NODE_STATUS_EXECUTING,
    NODE_STATUS_PENDING,
    NODE_STATUS_REWORK_REQUIRED,
    TICKET_STATUS_BLOCKED_FOR_BOARD_REVIEW,
    TICKET_STATUS_CANCELLED,
    TICKET_STATUS_CANCEL_REQUESTED,
    TICKET_STATUS_COMPLETED,
    TICKET_STATUS_EXECUTING,
    TICKET_STATUS_FAILED,
    TICKET_STATUS_LEASED,
    TICKET_STATUS_PENDING,
    TICKET_STATUS_REWORK_REQUIRED,
    TICKET_STATUS_TIMED_OUT,
)


class _FakeObjectStoreClient:
    def __init__(self, *, fail_delete: bool = False):
        self.fail_delete = fail_delete
        self.objects: dict[str, bytes] = {}
        self.media_types: dict[str, str | None] = {}

    def put_object(self, *, bucket: str, key: str, body: bytes, media_type: str | None = None) -> None:
        self.objects[f"{bucket}:{key}"] = body
        self.media_types[f"{bucket}:{key}"] = media_type

    def get_object(self, *, bucket: str, key: str) -> bytes:
        return self.objects[f"{bucket}:{key}"]

    def delete_object(self, *, bucket: str, key: str) -> None:
        if self.fail_delete:
            raise RuntimeError("simulated object delete failure")
        self.objects.pop(f"{bucket}:{key}", None)
        self.media_types.pop(f"{bucket}:{key}", None)


@contextmanager
def _create_client_with_fake_object_store(monkeypatch, *, fail_delete: bool = False):
    monkeypatch.setenv("BOARDROOM_OS_ARTIFACT_OBJECT_STORE_ENABLED", "1")
    monkeypatch.setenv("BOARDROOM_OS_ARTIFACT_OBJECT_STORE_BUCKET", "boardroom-artifacts")
    monkeypatch.setenv("BOARDROOM_OS_ARTIFACT_OBJECT_STORE_ENDPOINT", "https://object.local")
    monkeypatch.setenv("BOARDROOM_OS_ARTIFACT_OBJECT_STORE_ACCESS_KEY", "local-access")
    monkeypatch.setenv("BOARDROOM_OS_ARTIFACT_OBJECT_STORE_SECRET_KEY", "local-secret")
    fake_client = _FakeObjectStoreClient(fail_delete=fail_delete)

    import app._frozen.object_store as object_store_module

    monkeypatch.setattr(
        object_store_module,
        "build_s3_compatible_object_store_client",
        lambda settings: fake_client,
    )
    from app.main import create_app
    with TestClient(create_app()) as client:
        yield client, fake_client


def _project_init_payload(
    goal: str,
    budget_cap: int = 500000,
    *,
    hard_constraints: list[str] | None = None,
    deadline_at: str | None = None,
    force_requirement_elicitation: bool = False,
) -> dict:
    return {
        "north_star_goal": goal,
        "hard_constraints": hard_constraints
        or [
            "Keep governance explicit.",
            "Do not move workflow truth into the browser.",
        ],
        "budget_cap": budget_cap,
        "deadline_at": deadline_at,
        "force_requirement_elicitation": force_requirement_elicitation,
    }


def _git_output(cwd: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return completed.stdout.strip()


def _elicitation_answers() -> list[dict]:
    return [
        {
            "question_id": "delivery_scope",
            "selected_option_ids": ["scope_mvp_slice"],
            "text": "",
        },
        {
            "question_id": "core_roles",
            "selected_option_ids": [
                "role_frontend_engineer",
                "role_checker",
            ],
            "text": "",
        },
        {
            "question_id": "quality_bar",
            "selected_option_ids": ["quality_board_review_ready"],
            "text": "",
        },
        {
            "question_id": "hard_boundaries",
            "selected_option_ids": [],
            "text": "Stay local-first and avoid remote worker handoff.",
        },
    ]


def _ensure_scoped_workflow(
    client,
    *,
    workflow_id: str,
    tenant_id: str,
    workspace_id: str,
    goal: str | None = None,
) -> None:
    repository = client.app.state.repository
    workflow = repository.get_workflow_projection(workflow_id)
    if workflow is not None:
        assert workflow["tenant_id"] == tenant_id
        assert workflow["workspace_id"] == workspace_id
        return

    with repository.transaction() as connection:
        repository.insert_event(
            connection,
            event_type=EVENT_WORKFLOW_CREATED,
            actor_type="system",
            actor_id="test-seed",
            workflow_id=workflow_id,
            idempotency_key=f"test-workflow-created:{workflow_id}",
            causation_id=None,
            correlation_id=workflow_id,
            payload={
                "north_star_goal": goal or f"Seed scoped workflow {workflow_id}",
                "hard_constraints": ["Keep governance explicit."],
                "budget_cap": 500000,
                "deadline_at": None,
                "title": goal or f"Seed scoped workflow {workflow_id}",
                "tenant_id": tenant_id,
                "workspace_id": workspace_id,
            },
            occurred_at=datetime.fromisoformat("2026-03-28T10:00:00+08:00"),
        )
        repository.save_governance_profile(
            connection,
            build_default_governance_profile(
                workflow_id=workflow_id,
                source_ref=f"test://workflow/{workflow_id}/charter",
                effective_from_event=f"test-workflow-created:{workflow_id}",
            ),
        )
        repository.refresh_projections(connection)


def _ensure_default_governance_profile(client, *, workflow_id: str) -> None:
    repository = client.app.state.repository
    if repository.get_latest_governance_profile(workflow_id) is not None:
        return
    with repository.transaction() as connection:
        repository.save_governance_profile(
            connection,
            build_default_governance_profile(
                workflow_id=workflow_id,
                source_ref=f"test://workflow/{workflow_id}/charter",
                effective_from_event=f"test-governance:{workflow_id}",
            ),
        )
        repository.refresh_projections(connection)


def _persist_workflow_profile(repository, workflow_id: str, workflow_profile: str) -> None:
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
        payload["workflow_profile"] = workflow_profile
        connection.execute(
            "UPDATE events SET payload_json = ? WHERE event_id = ?",
            (json.dumps(payload, sort_keys=True), row["event_id"]),
        )
        repository.refresh_projections(connection)


def _seed_created_ticket(
    client,
    *,
    workflow_id: str,
    ticket_id: str,
    node_id: str,
    role_profile_ref: str,
    output_schema_ref: str,
    delivery_stage: str | None = None,
    allowed_write_set: list[str] | None = None,
    allowed_tools: list[str] | None = None,
    acceptance_criteria: list[str] | None = None,
    input_artifact_refs: list[str] | None = None,
    input_process_asset_refs: list[str] | None = None,
    parent_ticket_id: str | None = None,
    dependency_gate_refs: list[str] | None = None,
) -> None:
    repository = client.app.state.repository
    payload = _ticket_create_payload(
        workflow_id=workflow_id,
        ticket_id=ticket_id,
        node_id=node_id,
        role_profile_ref=role_profile_ref,
        output_schema_ref=output_schema_ref,
        delivery_stage=delivery_stage,
        allowed_write_set=allowed_write_set,
        allowed_tools=allowed_tools,
        acceptance_criteria=acceptance_criteria,
        input_artifact_refs=input_artifact_refs,
        parent_ticket_id=parent_ticket_id,
        dispatch_intent={
            "assignee_employee_id": "emp_frontend_2",
            "selection_reason": "Seed graph dependency gates",
            "dependency_gate_refs": dependency_gate_refs,
            "selected_by": "test",
            "wakeup_policy": "default",
        }
        if dependency_gate_refs is not None
        else None,
    )
    if input_process_asset_refs is not None:
        payload["input_process_asset_refs"] = input_process_asset_refs
    payload.setdefault(
        "graph_contract",
        {
            "lane_kind": "execution",
        },
    )
    with repository.transaction() as connection:
        repository.insert_event(
            connection,
            event_type=EVENT_TICKET_CREATED,
            actor_type="system",
            actor_id="test-seed",
            workflow_id=workflow_id,
            idempotency_key=f"test-seed-ticket-created:{workflow_id}:{ticket_id}",
            causation_id=None,
            correlation_id=workflow_id,
            payload=payload,
            occurred_at=datetime.fromisoformat("2026-03-28T10:30:00+08:00"),
        )
        repository.refresh_projections(connection)


def _seed_graph_patch_applied_event(
    client,
    *,
    workflow_id: str,
    patch_index: int,
    freeze_node_ids: list[str],
    unfreeze_node_ids: list[str] | None = None,
    focus_node_ids: list[str] | None = None,
    replacements: list[dict[str, str]] | None = None,
    remove_node_ids: list[str] | None = None,
    add_nodes: list[dict[str, object]] | None = None,
    edge_additions: list[dict[str, str]] | None = None,
    edge_removals: list[dict[str, str]] | None = None,
    payload_override=None,
    occurred_at: str | None = None,
) -> None:
    repository = client.app.state.repository
    with repository.transaction() as connection:
        repository.insert_event(
            connection,
            event_type=EVENT_GRAPH_PATCH_APPLIED,
            actor_type="board",
            actor_id="test-seed",
            workflow_id=workflow_id,
            idempotency_key=f"test-graph-patch-applied:{workflow_id}:{patch_index}",
            causation_id=None,
            correlation_id=workflow_id,
            payload=(
                payload_override
                if payload_override is not None
                else {
                    "patch_ref": f"pa://graph-patch/{workflow_id}@{patch_index}",
                    "workflow_id": workflow_id,
                    "session_id": f"adv_graph_patch_{patch_index}",
                    "proposal_ref": f"pa://graph-patch-proposal/{workflow_id}@{patch_index}",
                    "base_graph_version": f"gv_{patch_index}",
                    "freeze_node_ids": list(freeze_node_ids),
                    "unfreeze_node_ids": list(unfreeze_node_ids or []),
                    "focus_node_ids": list(focus_node_ids or freeze_node_ids),
                    "replacements": list(replacements or []),
                    "remove_node_ids": list(remove_node_ids or []),
                    "add_nodes": list(add_nodes or []),
                    "edge_additions": list(edge_additions or []),
                    "edge_removals": list(edge_removals or []),
                    "reason_summary": "Seed graph patch event for placeholder runtime materialization coverage.",
                    "patch_hash": f"hash-{workflow_id}-{patch_index}",
                }
            ),
            occurred_at=datetime.fromisoformat(
                occurred_at or f"2026-04-16T20:0{patch_index}:00+08:00"
            ),
        )
        if payload_override is None or isinstance(payload_override, dict):
            repository.refresh_projections(connection)


def _employee_hire_request_payload(
    workflow_id: str,
    *,
    employee_id: str = "emp_frontend_backup",
    role_type: str = "frontend_engineer",
    role_profile_refs: list[str] | None = None,
    skill_profile: dict | None = None,
    personality_profile: dict | None = None,
    aesthetic_profile: dict | None = None,
    request_summary: str = "Hire a backup frontend maker for rework rotation.",
) -> dict:
    return {
        "workflow_id": workflow_id,
        "employee_id": employee_id,
        "role_type": role_type,
        "role_profile_refs": role_profile_refs or ["frontend_engineer_primary"],
        "skill_profile": skill_profile
        or {
            "primary_domain": "frontend",
            "system_scope": "surface_polish",
            "validation_bias": "finish_first",
        },
        "personality_profile": personality_profile
        or {
            "risk_posture": "cautious",
            "challenge_style": "probing",
            "execution_pace": "measured",
            "detail_rigor": "rigorous",
            "communication_style": "concise",
        },
        "aesthetic_profile": aesthetic_profile
        or {
            "surface_preference": "polished",
            "information_density": "layered",
            "motion_tolerance": "restrained",
        },
        "provider_id": "prov_openai_compat",
        "request_summary": request_summary,
        "idempotency_key": f"employee-hire-request:{workflow_id}:{employee_id}",
    }


def _employee_replace_request_payload(
    workflow_id: str,
    *,
    replaced_employee_id: str = "emp_frontend_2",
    replacement_employee_id: str = "emp_frontend_backup",
    replacement_role_type: str = "frontend_engineer",
    replacement_role_profile_refs: list[str] | None = None,
    replacement_skill_profile: dict | None = None,
    replacement_personality_profile: dict | None = None,
    replacement_aesthetic_profile: dict | None = None,
) -> dict:
    return {
        "workflow_id": workflow_id,
        "replaced_employee_id": replaced_employee_id,
        "replacement_employee_id": replacement_employee_id,
        "replacement_role_type": replacement_role_type,
        "replacement_role_profile_refs": replacement_role_profile_refs or ["frontend_engineer_primary"],
        "replacement_skill_profile": replacement_skill_profile
        or {
            "primary_domain": "frontend",
            "system_scope": "surface_polish",
            "validation_bias": "finish_first",
        },
        "replacement_personality_profile": replacement_personality_profile
        or {
            "risk_posture": "cautious",
            "challenge_style": "probing",
            "execution_pace": "measured",
            "detail_rigor": "rigorous",
            "communication_style": "concise",
        },
        "replacement_aesthetic_profile": replacement_aesthetic_profile
        or {
            "surface_preference": "polished",
            "information_density": "layered",
            "motion_tolerance": "restrained",
        },
        "replacement_provider_id": "prov_openai_compat",
        "request_summary": "Replace the current maker with a backup frontend worker.",
        "idempotency_key": (
            f"employee-replace-request:{workflow_id}:{replaced_employee_id}:{replacement_employee_id}"
        ),
    }


def _employee_freeze_payload(
    workflow_id: str,
    *,
    employee_id: str = "emp_frontend_2",
    frozen_by: str = "ops@example.com",
) -> dict:
    return {
        "workflow_id": workflow_id,
        "employee_id": employee_id,
        "frozen_by": frozen_by,
        "reason": "Pause this worker from taking new tickets.",
        "idempotency_key": f"employee-freeze:{workflow_id}:{employee_id}",
    }


def _employee_restore_payload(
    workflow_id: str,
    *,
    employee_id: str = "emp_frontend_2",
    restored_by: str = "ops@example.com",
) -> dict:
    return {
        "workflow_id": workflow_id,
        "employee_id": employee_id,
        "restored_by": restored_by,
        "reason": "Return this worker to active duty.",
        "idempotency_key": f"employee-restore:{workflow_id}:{employee_id}",
    }


def _runtime_provider_upsert_payload(
    *,
    default_provider_id: str | None = None,
    openai_enabled: bool = True,
    openai_base_url: str | None = "https://api.example.test/v1",
    openai_api_key: str | None = "sk-test-secret",
    openai_model: str | None = "gpt-5.3-codex",
    openai_capability_tags: list[str] | None = None,
    openai_fallback_provider_ids: list[str] | None = None,
    role_bindings: list[dict] | None = None,
    idempotency_key: str = "runtime-provider-upsert:test",
) -> dict:
    payload = {
        "providers": [
            {
                "provider_id": "prov_openai_compat",
                "type": "openai_responses_stream",
                "enabled": openai_enabled,
                "base_url": openai_base_url,
                "api_key": openai_api_key,
                "alias": "",
                "preferred_model": openai_model,
                "max_context_window": None,
                "reasoning_effort": "high",
            },
        ],
        "provider_model_entries": (
            [{"provider_id": "prov_openai_compat", "model_name": openai_model}]
            if openai_model
            else []
        ),
        "role_bindings": list(
            role_bindings
            or [
                {
                    "target_ref": "ceo_shadow",
                    "provider_model_entry_refs": (
                        [f"prov_openai_compat::{openai_model}"] if openai_model else []
                    ),
                    "max_context_window_override": None,
                    "reasoning_effort_override": None,
                }
            ]
        ),
        "idempotency_key": idempotency_key,
    }
    if default_provider_id is not None:
        payload["default_provider_id"] = default_provider_id
    if openai_capability_tags is not None:
        payload["providers"][0]["capability_tags"] = list(openai_capability_tags)
    if openai_fallback_provider_ids is not None:
        payload["providers"][0]["fallback_provider_ids"] = list(openai_fallback_provider_ids)
    return payload


def _encode_base64(content: bytes) -> str:
    return base64.b64encode(content).decode("ascii")


def _seed_worker(
    client,
    *,
    employee_id: str,
    role_type: str = "frontend_engineer",
    provider_id: str = "prov_openai_compat",
    role_profile_refs: list[str] | None = None,
) -> None:
    repository = client.app.state.repository
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
                "skill_profile": {},
                "personality_profile": {},
                "aesthetic_profile": {},
                "state": "ACTIVE",
                "board_approved": True,
                "provider_id": provider_id,
                "role_profile_refs": list(role_profile_refs or ["frontend_engineer_primary"]),
            },
            occurred_at=datetime.fromisoformat("2026-03-28T10:00:00+08:00"),
        )
        repository.refresh_projections(connection)


def _worker_headers(
    shared_secret: str = "shared-secret",
    worker_id: str = "emp_frontend_2",
) -> dict[str, str]:
    return {
        "X-Boardroom-Worker-Key": shared_secret,
        "X-Boardroom-Worker-Id": worker_id,
    }


def _issue_worker_bootstrap_token(
    *,
    worker_id: str = "emp_frontend_2",
    credential_version: int = 1,
    signing_secret: str = "bootstrap-secret",
    tenant_id: str = "tenant_default",
    workspace_id: str = "ws_default",
    issued_at: str = "2026-03-28T10:00:00+08:00",
    ttl_sec: int = 3600,
) -> tuple[str, datetime]:
    from app.core.worker_bootstrap_tokens import issue_worker_bootstrap_token

    return issue_worker_bootstrap_token(
        signing_secret=signing_secret,
        worker_id=worker_id,
        credential_version=credential_version,
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        issue_id=None,
        issued_at=datetime.fromisoformat(issued_at),
        ttl_sec=ttl_sec,
    )


def _worker_bootstrap_headers(
    *,
    worker_id: str = "emp_frontend_2",
    credential_version: int = 1,
    signing_secret: str = "bootstrap-secret",
    tenant_id: str = "tenant_default",
    workspace_id: str = "ws_default",
    issued_at: str = "2026-03-28T10:00:00+08:00",
    ttl_sec: int = 3600,
) -> dict[str, str]:
    token, _ = _issue_worker_bootstrap_token(
        worker_id=worker_id,
        credential_version=credential_version,
        signing_secret=signing_secret,
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        issued_at=issued_at,
        ttl_sec=ttl_sec,
    )
    return {"X-Boardroom-Worker-Bootstrap": token}


def _worker_session_headers(session_token: str) -> dict[str, str]:
    return {"X-Boardroom-Worker-Session": session_token}


@pytest.fixture(autouse=True)
def _set_worker_admin_signing_secret(monkeypatch):
    monkeypatch.setenv("BOARDROOM_OS_WORKER_ADMIN_SIGNING_SECRET", "operator-secret")


def _legacy_worker_admin_headers(
    *,
    operator_id: str = "ops@example.com",
    role: str = "platform_admin",
    tenant_id: str | None = None,
    workspace_id: str | None = None,
) -> dict[str, str]:
    if (tenant_id is None) != (workspace_id is None):
        raise AssertionError("tenant_id and workspace_id must be provided together for worker-admin headers.")
    headers = {
        "X-Boardroom-Operator-Id": operator_id,
        "X-Boardroom-Operator-Role": role,
    }
    if tenant_id is not None and workspace_id is not None:
        headers["X-Boardroom-Operator-Tenant-Id"] = tenant_id
        headers["X-Boardroom-Operator-Workspace-Id"] = workspace_id
    return headers


def _worker_admin_headers(
    *,
    operator_id: str = "ops@example.com",
    role: str = "platform_admin",
    tenant_id: str | None = None,
    workspace_id: str | None = None,
    ttl_sec: int = 3600,
    issued_at: str | None = None,
    signing_secret: str = "operator-secret",
    include_assertion_headers: bool = True,
    asserted_operator_id: str | None = None,
    asserted_role: str | None = None,
    asserted_tenant_id: str | None = None,
    asserted_workspace_id: str | None = None,
    trusted_proxy_id: str | None = None,
) -> dict[str, str]:
    from app.core.worker_admin_tokens import issue_worker_admin_token

    token, _ = issue_worker_admin_token(
        signing_secret=signing_secret,
        operator_id=operator_id,
        role=role,
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        issued_at=datetime.fromisoformat(issued_at) if issued_at is not None else datetime.now().astimezone(),
        ttl_sec=ttl_sec,
    )
    headers = {"X-Boardroom-Operator-Token": token}
    if trusted_proxy_id is not None:
        headers["X-Boardroom-Trusted-Proxy-Id"] = trusted_proxy_id
    if include_assertion_headers:
        headers.update(
            _legacy_worker_admin_headers(
                operator_id=asserted_operator_id or operator_id,
                role=asserted_role or role,
                tenant_id=asserted_tenant_id if asserted_tenant_id is not None else tenant_id,
                workspace_id=asserted_workspace_id if asserted_workspace_id is not None else workspace_id,
            )
    )
    return headers


def _issue_persisted_worker_admin_token(
    client,
    *,
    operator_id: str = "ops@example.com",
    role: str = "platform_admin",
    tenant_id: str | None = None,
    workspace_id: str | None = None,
    ttl_sec: int = 3600,
    issued_at: str | None = None,
    signing_secret: str = "operator-secret",
    issued_by: str | None = None,
) -> tuple[str, dict]:
    from app.core.worker_admin_tokens import issue_worker_admin_token

    repository = client.app.state.repository
    issued_at_value = (
        datetime.fromisoformat(issued_at) if issued_at is not None else datetime.now().astimezone()
    )
    with repository.transaction() as connection:
        token_issue = repository.create_worker_admin_token_issue(
            connection,
            token_id=None,
            operator_id=operator_id,
            role=role,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            issued_at=issued_at_value,
            expires_at=issued_at_value,
            issued_via="test_helper",
            issued_by=issued_by or operator_id,
        )
        token, expires_at = issue_worker_admin_token(
            signing_secret=signing_secret,
            operator_id=operator_id,
            role=role,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            token_id=str(token_issue["token_id"]),
            issued_at=issued_at_value,
            ttl_sec=ttl_sec,
        )
        token_issue = repository.update_worker_admin_token_issue_expiry(
            connection,
            token_id=str(token_issue["token_id"]),
            expires_at=expires_at,
        )
    return token, token_issue


def _persisted_worker_admin_headers(
    client,
    *,
    operator_id: str = "ops@example.com",
    role: str = "platform_admin",
    tenant_id: str | None = None,
    workspace_id: str | None = None,
    ttl_sec: int = 3600,
    issued_at: str | None = None,
    signing_secret: str = "operator-secret",
    include_assertion_headers: bool = True,
    asserted_operator_id: str | None = None,
    asserted_role: str | None = None,
    asserted_tenant_id: str | None = None,
    asserted_workspace_id: str | None = None,
    trusted_proxy_id: str | None = None,
) -> tuple[dict[str, str], dict]:
    token, token_issue = _issue_persisted_worker_admin_token(
        client,
        operator_id=operator_id,
        role=role,
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        ttl_sec=ttl_sec,
        issued_at=issued_at,
        signing_secret=signing_secret,
    )
    headers = {"X-Boardroom-Operator-Token": token}
    if trusted_proxy_id is not None:
        headers["X-Boardroom-Trusted-Proxy-Id"] = trusted_proxy_id
    if include_assertion_headers:
        headers.update(
            _legacy_worker_admin_headers(
                operator_id=asserted_operator_id or operator_id,
                role=asserted_role or role,
                tenant_id=asserted_tenant_id if asserted_tenant_id is not None else tenant_id,
                workspace_id=asserted_workspace_id if asserted_workspace_id is not None else workspace_id,
            )
        )
    return headers, token_issue


def _worker_assignments_response(
    client,
    *,
    worker_id: str = "emp_frontend_2",
    credential_version: int = 1,
    signing_secret: str = "bootstrap-secret",
    tenant_id: str = "tenant_default",
    workspace_id: str = "ws_default",
    issued_at: str = "2026-03-28T10:00:00+08:00",
    ttl_sec: int = 3600,
):
    return client.get(
        "/api/v1/worker-runtime/assignments",
        headers=_worker_bootstrap_headers(
            worker_id=worker_id,
            credential_version=credential_version,
            signing_secret=signing_secret,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            issued_at=issued_at,
            ttl_sec=ttl_sec,
        ),
    )


def _worker_assignments_data(
    client,
    *,
    worker_id: str = "emp_frontend_2",
    credential_version: int = 1,
    signing_secret: str = "bootstrap-secret",
    tenant_id: str = "tenant_default",
    workspace_id: str = "ws_default",
    issued_at: str = "2026-03-28T10:00:00+08:00",
    ttl_sec: int = 3600,
) -> dict:
    repository = client.app.state.repository
    with repository.connection() as connection:
        workflow_ids = {
            str(row["workflow_id"])
            for row in connection.execute(
                """
                SELECT DISTINCT workflow_id
                FROM ticket_projection
                WHERE lease_owner = ?
                """,
                (worker_id,),
            ).fetchall()
            if str(row["workflow_id"] or "").strip()
        }
    for workflow_id in workflow_ids:
        _ensure_default_governance_profile(client, workflow_id=workflow_id)
    response = _worker_assignments_response(
        client,
        worker_id=worker_id,
        credential_version=credential_version,
        signing_secret=signing_secret,
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        issued_at=issued_at,
        ttl_sec=ttl_sec,
    )
    assert response.status_code == 200
    return response.json()["data"]


def _local_path_from_url(url: str) -> str:
    parsed = urlsplit(url)
    if parsed.query:
        return f"{parsed.path}?{parsed.query}"
    return parsed.path


def _query_value(url: str, name: str) -> str | None:
    values = parse_qs(urlsplit(url).query).get(name)
    if not values:
        return None
    return values[0]


def _decode_worker_delivery_token_payload(token: str) -> dict:
    payload_segment = token.split(".", 1)[0]
    padding = "=" * (-len(payload_segment) % 4)
    return json.loads(base64.urlsafe_b64decode(f"{payload_segment}{padding}").decode("utf-8"))


def _replace_query_value(url: str, name: str, value: str) -> str:
    parsed = urlsplit(url)
    query = parse_qs(parsed.query, keep_blank_values=True)
    query[name] = [value]
    return urlunsplit(
        (
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            urlencode(query, doseq=True),
            parsed.fragment,
        )
    )


def _worker_artifact_payloads(execution_package_data: dict) -> dict[str, dict]:
    payloads: dict[str, dict] = {}
    for block in execution_package_data["compiled_execution_package"]["atomic_context_bundle"]["context_blocks"]:
        content_payload = block.get("content_payload") or {}
        artifact_access = content_payload.get("artifact_access") or {}
        artifact_ref = (
            artifact_access.get("artifact_ref")
            or content_payload.get("artifact_ref")
            or content_payload.get("source_ref")
        )
        if isinstance(artifact_ref, str) and artifact_ref:
            payloads[artifact_ref] = content_payload
    return payloads


def _list_worker_delivery_grants(client) -> list[dict]:
    repository = client.app.state.repository
    with repository.connection() as connection:
        rows = connection.execute(
            """
            SELECT
                grant_id,
                scope,
                worker_id,
                session_id,
                credential_version,
                ticket_id,
                artifact_ref,
                artifact_action,
                command_name,
                issued_at,
                expires_at,
                revoked_at,
                revoke_reason
            FROM worker_delivery_grant
            ORDER BY issued_at, grant_id
            """
        ).fetchall()
        return [dict(row) for row in rows]


def _list_worker_auth_rejections(client) -> list[dict]:
    repository = client.app.state.repository
    with repository.connection() as connection:
        rows = connection.execute(
            """
            SELECT
                occurred_at,
                route_family,
                reason_code,
                worker_id,
                session_id,
                grant_id,
                ticket_id,
                tenant_id,
                workspace_id
            FROM worker_auth_rejection_log
            ORDER BY occurred_at ASC
            """
        ).fetchall()
        return [dict(row) for row in rows]


def _bootstrap_worker_execution_package(client, bootstrap_token: str) -> tuple[dict, dict]:
    assignments_response = client.get(
        "/api/v1/worker-runtime/assignments",
        headers={"X-Boardroom-Worker-Bootstrap": bootstrap_token},
    )
    assignments_data = assignments_response.json()["data"]
    execution_package_url = assignments_data["assignments"][0]["execution_package_url"]
    execution_package_response = client.get(_local_path_from_url(execution_package_url))
    return assignments_data, execution_package_response.json()["data"]


def _revoke_worker_delivery_grant(
    client,
    *,
    grant_id: str,
    revoked_at: str = "2026-03-28T10:06:00+08:00",
    revoke_reason: str = "Manual single-URL revoke for testing.",
) -> None:
    repository = client.app.state.repository
    with repository.transaction() as connection:
        connection.execute(
            """
            UPDATE worker_delivery_grant
            SET revoked_at = ?, revoke_reason = ?
            WHERE grant_id = ?
            """,
            (revoked_at, revoke_reason, grant_id),
        )


def _seed_input_artifact(
    client,
    *,
    artifact_ref: str = "art://inputs/brief.md",
    logical_path: str = "artifacts/inputs/brief.md",
    content: str = "# Brief\n\nMaterialized input.\n",
    content_bytes: bytes | None = None,
    kind: str = "MARKDOWN",
    media_type: str = "text/markdown",
    materialization_status: str = "MATERIALIZED",
    lifecycle_status: str = "ACTIVE",
    deleted_at: str | None = None,
    deleted_by: str | None = None,
    delete_reason: str | None = None,
) -> None:
    repository = client.app.state.repository
    artifact_store = client.app.state.artifact_store
    storage_relpath = None
    content_hash = None
    size_bytes = None

    if materialization_status == "MATERIALIZED":
        if content_bytes is not None:
            materialized = artifact_store.materialize_bytes(logical_path, content_bytes)
        else:
            materialized = artifact_store.materialize_text(logical_path, content)
        storage_relpath = materialized.storage_relpath
        content_hash = materialized.content_hash
        size_bytes = materialized.size_bytes

    with repository.transaction() as connection:
        repository.save_artifact_record(
            connection,
            artifact_ref=artifact_ref,
            workflow_id="wf_seed_inputs",
            ticket_id="tkt_seed_inputs",
            node_id="node_seed_inputs",
            logical_path=logical_path,
            kind=kind,
            media_type=media_type,
            materialization_status=materialization_status,
            lifecycle_status=lifecycle_status,
            storage_relpath=storage_relpath,
            content_hash=content_hash,
            size_bytes=size_bytes,
            retention_class="PERSISTENT",
            expires_at=None,
            deleted_at=datetime.fromisoformat(deleted_at) if deleted_at is not None else None,
            deleted_by=deleted_by,
            delete_reason=delete_reason,
            created_at=datetime.fromisoformat("2026-03-28T10:00:00+08:00"),
        )




def _ticket_complete_payload(
    workflow_id: str = "wf_seed",
    ticket_id: str = "tkt_visual_001",
    node_id: str = "node_homepage_visual",
    include_review_request: bool = True,
    compiled_context_bundle_ref: str = "ctx://homepage/visual-v1",
    compile_manifest_ref: str = "manifest://homepage/visual-v1",
    rendered_execution_payload_ref: str | None = None,
) -> dict:
    payload = {
        "workflow_id": workflow_id,
        "ticket_id": ticket_id,
        "node_id": node_id,
        "completed_by": "emp_frontend_2",
        "completion_summary": "Visual milestone is blocked for board review.",
        "artifact_refs": ["art://homepage/option-a.png", "art://homepage/option-b.png"],
        "idempotency_key": f"ticket-complete:{workflow_id}:{ticket_id}",
    }
    if include_review_request:
        payload["review_request"] = {
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
                    "artifact_refs": ["art://homepage/option-a.png"],
                    "pros": ["Strong first-screen hierarchy"],
                    "cons": ["Slightly more aggressive contrast"],
                    "risks": ["Needs careful brand calibration"],
                },
                {
                    "option_id": "option_b",
                    "label": "Option B",
                    "summary": "Lower contrast fallback.",
                    "artifact_refs": ["art://homepage/option-b.png"],
                    "pros": ["Safer visual tone"],
                    "cons": ["Weaker first impression"],
                    "risks": ["May undersignal product confidence"],
                },
            ],
            "evidence_summary": [
                {
                    "evidence_id": "ev_homepage_checker",
                    "source_type": "CHECKER_FINDING",
                    "headline": "Checker prefers Option A",
                    "summary": "Option A is more legible and directional under current constraints.",
                    "source_ref": "chk://homepage/visual-review",
                }
            ],
            "maker_checker_summary": {
                "maker_employee_id": "emp_frontend_2",
                "checker_employee_id": "emp_checker_1",
                "review_status": "APPROVED_WITH_NOTES",
                "top_findings": [
                    {
                        "finding_id": "finding_hero_contrast",
                        "severity": "medium",
                        "headline": "Option B lacks contrast in the hero section",
                    }
                ],
            },
            "risk_summary": {
                "user_risk": "LOW",
                "engineering_risk": "LOW",
                "schedule_risk": "MEDIUM",
                "budget_risk": "LOW",
            },
            "budget_impact": {
                "tokens_spent_so_far": 1200,
                "tokens_if_approved_estimate_range": {"min_tokens": 200, "max_tokens": 500},
                "tokens_if_rework_estimate_range": {"min_tokens": 600, "max_tokens": 1200},
                "estimate_confidence": "medium",
                "budget_risk": "LOW",
            },
            "developer_inspector_refs": {
                "compiled_context_bundle_ref": compiled_context_bundle_ref,
                "compile_manifest_ref": compile_manifest_ref,
                **(
                    {"rendered_execution_payload_ref": rendered_execution_payload_ref}
                    if rendered_execution_payload_ref is not None
                    else {}
                ),
            },
            "available_actions": ["APPROVE", "REJECT", "MODIFY_CONSTRAINTS"],
            "draft_selected_option_id": "option_a",
            "comment_template": "",
            "inbox_title": "Review homepage visual milestone",
            "inbox_summary": "Visual milestone is blocked for board review.",
            "badges": ["visual", "board_gate"],
        }
    return payload


def _ticket_result_submit_payload(
    workflow_id: str = "wf_seed",
    ticket_id: str = "tkt_visual_001",
    node_id: str = "node_homepage_visual",
    submitted_by: str = "emp_frontend_2",
    result_status: str = "completed",
    include_review_request: bool = False,
    schema_version: str = "ui_milestone_review_v1",
    payload: dict | None = None,
    artifact_refs: list[str] | None = None,
    written_artifacts: list[dict] | None = None,
    idempotency_key: str | None = None,
    review_request: dict | None = None,
    compile_request_id: str | None = None,
    compiled_execution_package_version_ref: str | None = None,
) -> dict:
    resolved_artifact_refs = artifact_refs or [
        "art://homepage/option-a.png",
        "art://homepage/option-b.png",
    ]
    option_a_ref = resolved_artifact_refs[0]
    option_b_ref = (
        resolved_artifact_refs[1] if len(resolved_artifact_refs) > 1 else resolved_artifact_refs[0]
    )
    result_payload = {
        "workflow_id": workflow_id,
        "ticket_id": ticket_id,
        "node_id": node_id,
        "submitted_by": submitted_by,
        "result_status": result_status,
        "schema_version": schema_version,
        "payload": payload
        or {
            "summary": "Homepage visual milestone is ready for downstream review.",
            "recommended_option_id": "option_a",
            "options": [
                {
                    "option_id": "option_a",
                    "label": "Option A",
                    "summary": "High-contrast review candidate.",
                    "artifact_refs": [option_a_ref],
                },
                {
                    "option_id": "option_b",
                    "label": "Option B",
                    "summary": "Lower contrast fallback.",
                    "artifact_refs": [option_b_ref],
                },
            ],
        },
        "artifact_refs": resolved_artifact_refs,
        "written_artifacts": written_artifacts
        or [
            {
                "path": "artifacts/ui/homepage/option-a.png",
                "artifact_ref": option_a_ref,
                "kind": "IMAGE",
            },
            {
                "path": "artifacts/ui/homepage/option-b.png",
                "artifact_ref": option_b_ref,
                "kind": "IMAGE",
            },
        ],
        "assumptions": ["Keep current homepage information hierarchy."],
        "issues": [],
        "confidence": 0.82,
        "needs_escalation": False,
        "summary": "Structured runtime result submitted.",
        "failure_kind": None,
        "failure_message": None,
        "failure_detail": None,
        "idempotency_key": idempotency_key
        or f"ticket-result-submit:{workflow_id}:{ticket_id}:{result_status}",
    }
    if compile_request_id is not None:
        result_payload["compile_request_id"] = compile_request_id
    if compiled_execution_package_version_ref is not None:
        result_payload["compiled_execution_package_version_ref"] = compiled_execution_package_version_ref
    if result_status == "failed":
        result_payload["failure_kind"] = "RUNTIME_ERROR"
        result_payload["failure_message"] = "Structured runtime result reported failure."
        result_payload["failure_detail"] = {"step": "render", "exit_code": 1}
    if include_review_request:
        result_payload["review_request"] = review_request or _ticket_complete_payload(
            workflow_id=workflow_id,
            ticket_id=ticket_id,
            node_id=node_id,
            include_review_request=True,
        )["review_request"]
    return result_payload


def _meeting_escalation_review_request(
    *,
    compiled_context_bundle_ref: str | None = None,
    compile_manifest_ref: str | None = None,
    rendered_execution_payload_ref: str | None = None,
) -> dict:
    developer_inspector_refs: dict[str, str] = {}
    if compiled_context_bundle_ref is not None:
        developer_inspector_refs["compiled_context_bundle_ref"] = compiled_context_bundle_ref
    if compile_manifest_ref is not None:
        developer_inspector_refs["compile_manifest_ref"] = compile_manifest_ref
    if rendered_execution_payload_ref is not None:
        developer_inspector_refs["rendered_execution_payload_ref"] = rendered_execution_payload_ref

    payload = {
        "review_type": "MEETING_ESCALATION",
        "priority": "high",
        "title": "Review scope decision consensus",
        "subtitle": "Meeting output is ready for board lock-in.",
        "blocking_scope": "WORKFLOW",
        "trigger_reason": "Cross-role scope decision needs explicit board confirmation.",
        "why_now": "Implementation and staffing should not continue before this decision is locked.",
        "recommended_action": "APPROVE",
        "recommended_option_id": "consensus_scope_lock",
        "recommendation_summary": "The meeting converged on the narrowest scope that still ships the workflow.",
        "options": [
            {
                "option_id": "consensus_scope_lock",
                "label": "Lock consensus scope",
                "summary": "Proceed with the converged scope and follow-up tickets.",
                "artifact_refs": ["art://meeting/consensus-document.json"],
                "pros": ["Keeps delivery scope stable"],
                "cons": ["Defers non-critical stretch ideas"],
                "risks": ["Some polish moves slip to later rounds"],
            }
        ],
        "evidence_summary": [
            {
                "evidence_id": "ev_meeting_consensus",
                "source_type": "CONSENSUS_DOCUMENT",
                "headline": "Meeting converged on one scope",
                "summary": "Participants aligned on one scope and attached concrete follow-up tickets.",
                "source_ref": "art://meeting/consensus-document.json",
            }
        ],
        "risk_summary": {
            "user_risk": "LOW",
            "engineering_risk": "MEDIUM",
            "schedule_risk": "LOW",
            "budget_risk": "LOW",
        },
        "budget_impact": {
            "tokens_spent_so_far": 900,
            "tokens_if_approved_estimate_range": {"min_tokens": 100, "max_tokens": 250},
            "tokens_if_rework_estimate_range": {"min_tokens": 350, "max_tokens": 700},
            "estimate_confidence": "medium",
            "budget_risk": "LOW",
        },
        "available_actions": ["APPROVE", "REJECT", "MODIFY_CONSTRAINTS"],
        "draft_selected_option_id": "consensus_scope_lock",
        "comment_template": "",
        "inbox_title": "Review scope decision consensus",
        "inbox_summary": "A consensus document is ready for board review.",
        "badges": ["meeting", "board_gate", "scope"],
    }
    if developer_inspector_refs:
        payload["developer_inspector_refs"] = developer_inspector_refs
    return payload


def _internal_delivery_review_request() -> dict:
    return {
        "review_type": "INTERNAL_DELIVERY_REVIEW",
        "priority": "high",
        "title": "Check approved source code delivery",
        "subtitle": "Internal delivery review should pass before downstream checking starts.",
        "blocking_scope": "NODE_ONLY",
        "trigger_reason": "Source code delivery reached the internal checker gate.",
        "why_now": "Build output should be checked by a separate checker before the next ticket consumes it.",
        "recommended_action": "APPROVE",
        "recommended_option_id": "internal_delivery_ok",
        "recommendation_summary": "Source code delivery stays inside the approved scope and is ready for the next stage.",
        "options": [
            {
                "option_id": "internal_delivery_ok",
                "label": "Accept source delivery",
                "summary": "Internal checker can pass this source code delivery downstream.",
                "artifact_refs": ["art://runtime/build/source-code.tsx"],
                "pros": ["Lets downstream delivery check start immediately"],
                "cons": ["Leaves only non-blocking polish for later"],
                "risks": ["Minor implementation notes may still need follow-up"],
            }
        ],
        "evidence_summary": [
            {
                "evidence_id": "ev_source_code_delivery",
                "source_type": "SOURCE_CODE_DELIVERY",
                "headline": "Source code delivery is ready for internal review",
                "summary": "Maker produced the structured source code delivery required by the approved scope.",
                "source_ref": "art://runtime/build/source-code.tsx",
            }
        ],
        "available_actions": ["APPROVE", "REJECT", "MODIFY_CONSTRAINTS"],
        "draft_selected_option_id": "internal_delivery_ok",
        "comment_template": "",
        "badges": ["internal_delivery", "build_gate"],
    }


def _internal_check_review_request() -> dict:
    return {
        "review_type": "INTERNAL_CHECK_REVIEW",
        "priority": "high",
        "title": "Check approved delivery check report",
        "subtitle": "Internal checker should verify the check report before final board review starts.",
        "blocking_scope": "NODE_ONLY",
        "trigger_reason": "Delivery check report reached the internal checker gate.",
        "why_now": "Board-facing review should only start after the delivery check report is internally verified.",
        "recommended_action": "APPROVE",
        "recommended_option_id": "internal_check_ok",
        "recommendation_summary": (
            "Delivery check report stays grounded in the approved scope and is ready for final review."
        ),
        "options": [
            {
                "option_id": "internal_check_ok",
                "label": "Accept check report",
                "summary": "Internal checker can pass this delivery check report into final review.",
                "artifact_refs": ["art://runtime/check/delivery-check-report.json"],
                "pros": ["Lets the final board-facing review start on verified evidence."],
                "cons": ["Leaves only non-blocking polish to the final review package."],
                "risks": ["Any remaining mismatch would need a real rework loop before board review."],
            }
        ],
        "evidence_summary": [
            {
                "evidence_id": "ev_delivery_check_report",
                "source_type": "DELIVERY_CHECK_REPORT",
                "headline": "Delivery check report is ready for internal review",
                "summary": "Maker produced the structured check report required before final board review.",
                "source_ref": "art://runtime/check/delivery-check-report.json",
            }
        ],
        "available_actions": ["APPROVE", "REJECT", "MODIFY_CONSTRAINTS"],
        "draft_selected_option_id": "internal_check_ok",
        "comment_template": "",
        "badges": ["internal_check", "check_gate"],
    }


def _internal_closeout_review_request() -> dict:
    return {
        "review_type": "INTERNAL_CLOSEOUT_REVIEW",
        "priority": "high",
        "title": "Check delivery closeout package",
        "subtitle": "Internal checker should validate the final delivery closeout package before the workflow closes.",
        "blocking_scope": "NODE_ONLY",
        "trigger_reason": "Delivery closeout package reached the final internal checker gate.",
        "why_now": "Workflow completion should only happen after the final handoff package is internally checked.",
        "recommended_action": "APPROVE",
        "recommended_option_id": "internal_closeout_ok",
        "recommendation_summary": (
            "Delivery closeout package captures the approved board choice and is ready to close the workflow."
        ),
        "options": [
            {
                "option_id": "internal_closeout_ok",
                "label": "Accept closeout package",
                "summary": "Internal checker can pass this final handoff package into workflow completion.",
                "artifact_refs": ["art://runtime/closeout/delivery-closeout-package.json"],
                "pros": ["Lets the workflow finish on a checked final delivery package."],
                "cons": ["Leaves only non-blocking polish outside the MVP closeout path."],
                "risks": ["Weak handoff notes would require one more rework loop before completion."],
            }
        ],
        "evidence_summary": [
            {
                "evidence_id": "ev_delivery_closeout_package",
                "source_type": "DELIVERY_CLOSEOUT_PACKAGE",
                "headline": "Delivery closeout package is ready for internal review",
                "summary": "Maker prepared the final handoff package after board approval.",
                "source_ref": "art://runtime/closeout/delivery-closeout-package.json",
            }
        ],
        "available_actions": ["APPROVE", "REJECT", "MODIFY_CONSTRAINTS"],
        "draft_selected_option_id": "internal_closeout_ok",
        "comment_template": "",
        "badges": ["internal_closeout", "closeout_gate"],
    }


def _consensus_document_payload(
    *,
    topic: str = "Boardroom OS scope convergence",
    followup_ticket_id: str = "tkt_followup_scope_lock",
    followup_tickets: list[dict] | None = None,
    decision_record: dict | None = None,
) -> dict:
    payload = {
        "topic": topic,
        "participants": ["emp_frontend_2", "emp_checker_1"],
        "input_artifact_refs": ["art://inputs/brief.md", "art://inputs/brand-guide.md"],
        "consensus_summary": "Team aligned on the smallest scope that still unblocks board review.",
        "rejected_options": ["Expand to remote handoff this round"],
        "open_questions": ["Whether analytics polish should move after MVP"],
        "followup_tickets": followup_tickets
        or _staged_scope_followup_tickets(followup_ticket_id.removesuffix("_review")),
    }
    if decision_record is not None:
        payload["decision_record"] = decision_record
    return payload


def _staged_scope_followup_tickets(ticket_id_prefix: str = "tkt_followup_scope_lock") -> list[dict]:
    return [
        {
            "ticket_id": f"{ticket_id_prefix}_build",
            "task_title": "实现已批准的首页基础版",
            "owner_role": "frontend_engineer",
            "summary": "Build the approved homepage foundation without widening the governance surface.",
            "delivery_stage": "BUILD",
            "dependency_ticket_ids": [],
        },
        {
            "ticket_id": f"{ticket_id_prefix}_check",
            "task_title": "检查首页基础版实现",
            "owner_role": "checker",
            "summary": "Check the source code delivery against the approved scope lock.",
            "delivery_stage": "CHECK",
            "dependency_ticket_ids": [f"{ticket_id_prefix}_build"],
        },
        {
            "ticket_id": f"{ticket_id_prefix}_review",
            "task_title": "整理董事会评审包",
            "owner_role": "frontend_engineer",
            "summary": "Prepare the final board-facing homepage review package from the approved implementation.",
            "delivery_stage": "REVIEW",
            "dependency_ticket_ids": [
                f"{ticket_id_prefix}_build",
                f"{ticket_id_prefix}_check",
            ],
        },
    ]


def _consensus_document_result_submit_payload(
    workflow_id: str = "wf_seed",
    ticket_id: str = "tkt_scope_001",
    node_id: str = "node_scope_decision",
    submitted_by: str = "emp_frontend_2",
    include_review_request: bool = False,
    review_request: dict | None = None,
    payload: dict | None = None,
    artifact_refs: list[str] | None = None,
    idempotency_key: str | None = None,
) -> dict:
    return {
        "workflow_id": workflow_id,
        "ticket_id": ticket_id,
        "node_id": node_id,
        "submitted_by": submitted_by,
        "result_status": "completed",
        "schema_version": "consensus_document_v1",
        "payload": payload or _consensus_document_payload(),
        "artifact_refs": artifact_refs or ["art://meeting/consensus-document.json"],
        "written_artifacts": [
            {
                "path": "reports/meeting/consensus-document.json",
                "artifact_ref": (artifact_refs or ["art://meeting/consensus-document.json"])[0],
                "kind": "JSON",
                "content_json": payload or _consensus_document_payload(),
            }
        ],
        "assumptions": ["Consensus already reflects the final facilitator summary."],
        "issues": [],
        "confidence": 0.84,
        "needs_escalation": False,
        "summary": "Structured consensus document submitted.",
        "failure_kind": None,
        "failure_message": None,
        "failure_detail": None,
        "idempotency_key": idempotency_key
        or f"ticket-result-submit:{workflow_id}:{ticket_id}:consensus",
        **(
            {"review_request": review_request or _meeting_escalation_review_request()}
            if include_review_request
            else {}
        ),
    }


def _maker_checker_result_submit_payload(
    workflow_id: str = "wf_seed",
    ticket_id: str = "tkt_checker_001",
    node_id: str = "node_homepage_visual",
    submitted_by: str = "emp_checker_1",
    review_status: str = "APPROVED_WITH_NOTES",
    findings: list[dict] | None = None,
    artifact_refs: list[str] | None = None,
    idempotency_key: str | None = None,
) -> dict:
    resolved_findings = findings
    if resolved_findings is None:
        if review_status == "APPROVED":
            resolved_findings = []
        elif review_status == "CHANGES_REQUIRED":
            resolved_findings = [
                {
                    "finding_id": "finding_hero_hierarchy",
                    "severity": "high",
                    "category": "VISUAL_HIERARCHY",
                    "headline": "Hero hierarchy is not strong enough yet.",
                    "summary": "The first screen still lacks a clear primary attention anchor.",
                    "required_action": "Strengthen hero hierarchy before board review.",
                    "blocking": True,
                }
            ]
        else:
            resolved_findings = [
                {
                    "finding_id": "finding_cta_spacing",
                    "severity": "low",
                    "category": "VISUAL_POLISH",
                    "headline": "CTA spacing can be tightened slightly.",
                    "summary": "Spacing is acceptable but should be cleaned up downstream.",
                    "required_action": "Tighten CTA spacing during implementation.",
                    "blocking": False,
                }
            ]

    return {
        "workflow_id": workflow_id,
        "ticket_id": ticket_id,
        "node_id": node_id,
        "submitted_by": submitted_by,
        "result_status": "completed",
        "schema_version": "maker_checker_verdict_v1",
        "payload": {
            "summary": f"Checker returned {review_status} for the visual milestone.",
            "review_status": review_status,
            "findings": resolved_findings,
        },
        "artifact_refs": artifact_refs or [],
        "written_artifacts": [],
        "assumptions": ["Checker reviewed the submitted visual milestone package."],
        "issues": [],
        "confidence": 0.8,
        "needs_escalation": False,
        "summary": "Structured checker verdict submitted.",
        "failure_kind": None,
        "failure_message": None,
        "failure_detail": None,
        "idempotency_key": idempotency_key
        or f"ticket-result-submit:{workflow_id}:{ticket_id}:maker-checker",
    }


def _governance_document_result_submit_payload(
    *,
    workflow_id: str,
    ticket_id: str,
    node_id: str,
    output_schema_ref: str = "architecture_brief",
    summary: str = "Structured governance document submitted.",
) -> dict:
    artifact_ref = f"art://runtime/{ticket_id}/{output_schema_ref}.json"
    payload = {
        "title": f"{output_schema_ref} for {ticket_id}",
        "summary": summary,
        "document_kind_ref": output_schema_ref,
        "linked_document_refs": ["doc://governance/upstream/current"],
        "linked_artifact_refs": [artifact_ref],
        "source_process_asset_refs": [],
        "decisions": ["Keep the governance chain explicit before implementation."],
        "constraints": ["Do not widen the local MVP boundary."],
        "sections": [
            {
                "section_id": "section_governance_context",
                "label": "Context",
                "summary": summary,
                "content_markdown": "Keep the next slice document-first and auditable.",
            }
        ],
        "followup_recommendations": [
            {
                "recommendation_id": "rec_governance_followup",
                "summary": "Turn this governance document into the next controlled delivery step.",
                "target_role": "frontend_engineer",
            }
        ],
    }
    return {
        "workflow_id": workflow_id,
        "ticket_id": ticket_id,
        "node_id": node_id,
        "submitted_by": "emp_frontend_2",
        "result_status": "completed",
        "schema_version": f"{output_schema_ref}_v1",
        "payload": payload,
        "artifact_refs": [artifact_ref],
        "written_artifacts": [
            {
                "path": f"reports/governance/{ticket_id}/{output_schema_ref}.json",
                "artifact_ref": artifact_ref,
                "kind": "JSON",
                "content_json": payload,
            }
        ],
        "assumptions": ["Governance output should stay reviewable before downstream tickets consume it."],
        "issues": [],
        "confidence": 0.84,
        "needs_escalation": False,
        "summary": summary,
        "failure_kind": None,
        "failure_message": None,
        "failure_detail": None,
        "idempotency_key": f"ticket-result-submit:{workflow_id}:{ticket_id}:governance",
    }


def _source_code_delivery_result_submit_payload(
    workflow_id: str = "wf_seed",
    ticket_id: str = "tkt_build_001",
    node_id: str = "node_build_001",
    submitted_by: str = "emp_frontend_2",
    include_review_request: bool = False,
    review_request: dict | None = None,
    artifact_refs: list[str] | None = None,
    written_artifact_path: str | None = None,
    idempotency_key: str | None = None,
) -> dict:
    source_file_ref = (artifact_refs or [f"art://runtime/{ticket_id}/source-code.tsx"])[0]
    source_path = written_artifact_path or f"artifacts/ui/scope-followups/{ticket_id}/source-code.tsx"
    payload = {
        "summary": f"Source code delivery prepared for {ticket_id}.",
        "source_file_refs": [source_file_ref],
        "source_files": [
            {
                "artifact_ref": source_file_ref,
                "path": source_path,
                "content": "export const sourceCodeDelivery = true;\n",
            }
        ],
        "verification_runs": [
            {
                "artifact_ref": f"art://runtime/{ticket_id}/test-report.json",
                "path": f"artifacts/ui/scope-followups/{ticket_id}/verification/test-report.json",
                "runner": "vitest",
                "command": "npm run test -- --runInBand",
                "status": "passed",
                "exit_code": 0,
                "duration_sec": 1.4,
                "stdout": " RUN  v1.0.0\n  ✓ source delivery smoke\n\n Test Files  1 passed\n",
                "stderr": "",
                "discovered_count": 1,
                "passed_count": 1,
                "failed_count": 0,
                "skipped_count": 0,
                "failures": [],
            }
        ],
        "implementation_notes": [
            "Homepage foundation stays inside the approved scope lock and is ready for internal checking."
        ],
    }
    result = {
        "workflow_id": workflow_id,
        "ticket_id": ticket_id,
        "node_id": node_id,
        "submitted_by": submitted_by,
        "result_status": "completed",
        "schema_version": "source_code_delivery_v1",
        "payload": payload,
        "artifact_refs": [source_file_ref],
        "written_artifacts": [
            {
                "path": source_path,
                "artifact_ref": source_file_ref,
                "kind": "TEXT",
                "content_text": "export const sourceCodeDelivery = true;\n",
            }
        ],
        "assumptions": ["Source delivery already includes the minimal approved homepage slice."],
        "issues": [],
        "confidence": 0.83,
        "needs_escalation": False,
        "summary": "Structured source code delivery submitted.",
        "failure_kind": None,
        "failure_message": None,
        "failure_detail": None,
        "idempotency_key": idempotency_key or f"ticket-result-submit:{workflow_id}:{ticket_id}:implementation",
    }
    if include_review_request:
        resolved_review_request = review_request or _internal_delivery_review_request()
        if review_request is None:
            resolved_review_request = {
                **resolved_review_request,
                "options": [
                    {
                        **resolved_review_request["options"][0],
                        "artifact_refs": [source_file_ref],
                    }
                ],
                "evidence_summary": [
                    {
                        **resolved_review_request["evidence_summary"][0],
                        "source_ref": source_file_ref,
                    }
                ],
            }
        result["review_request"] = resolved_review_request
    return result


def _delivery_check_report_result_submit_payload(
    workflow_id: str = "wf_seed",
    ticket_id: str = "tkt_check_001",
    node_id: str = "node_check_001",
    submitted_by: str = "emp_checker_1",
    include_review_request: bool = False,
    review_request: dict | None = None,
    artifact_refs: list[str] | None = None,
    written_artifact_path: str | None = None,
    status: str = "PASS_WITH_NOTES",
    findings: list[dict] | None = None,
    idempotency_key: str | None = None,
) -> dict:
    report_ref = (artifact_refs or [f"art://runtime/{ticket_id}/delivery-check-report.json"])[0]
    payload = {
        "summary": f"Delivery check report prepared for {ticket_id}.",
        "status": status,
        "findings": findings
        or [
            {
                "finding_id": "finding_scope_copy",
                "summary": "Keep launch copy trimmed to the approved scope lock.",
                "blocking": False,
            }
        ],
    }
    result = {
        "workflow_id": workflow_id,
        "ticket_id": ticket_id,
        "node_id": node_id,
        "submitted_by": submitted_by,
        "result_status": "completed",
        "schema_version": "delivery_check_report_v1",
        "payload": payload,
        "artifact_refs": [report_ref],
        "written_artifacts": [
            {
                "path": written_artifact_path or f"reports/check/{ticket_id}/delivery-check-report.json",
                "artifact_ref": report_ref,
                "kind": "JSON",
                "content_json": payload,
            }
        ],
        "assumptions": ["The approved scope lock remains the reference for this delivery check."],
        "issues": [],
        "confidence": 0.84,
        "needs_escalation": False,
        "summary": "Structured delivery check report submitted.",
        "failure_kind": None,
        "failure_message": None,
        "failure_detail": None,
        "idempotency_key": idempotency_key or f"ticket-result-submit:{workflow_id}:{ticket_id}:delivery-check",
    }
    if include_review_request:
        resolved_review_request = review_request or _internal_check_review_request()
        if review_request is None:
            resolved_review_request = {
                **resolved_review_request,
                "options": [
                    {
                        **resolved_review_request["options"][0],
                        "artifact_refs": [report_ref],
                    }
                ],
                "evidence_summary": [
                    {
                        **resolved_review_request["evidence_summary"][0],
                        "source_ref": report_ref,
                    }
                ],
            }
        result["review_request"] = resolved_review_request
    return result


def _delivery_closeout_package_result_submit_payload(
    workflow_id: str = "wf_seed",
    ticket_id: str = "tkt_closeout_001",
    node_id: str = "node_closeout_001",
    submitted_by: str = "emp_frontend_2",
    include_review_request: bool = False,
    review_request: dict | None = None,
    artifact_refs: list[str] | None = None,
    final_artifact_refs: list[str] | None = None,
    documentation_updates: list[dict] | None = None,
    written_artifact_path: str | None = None,
    idempotency_key: str | None = None,
) -> dict:
    closeout_ref = (artifact_refs or [f"art://runtime/{ticket_id}/delivery-closeout-package.json"])[0]
    payload = {
        "summary": f"Delivery closeout package prepared for {ticket_id}.",
        "final_artifact_refs": list(final_artifact_refs or ["art://runtime/tkt_review_final/option-a.json"]),
        "handoff_notes": [
            "Board-approved final option is captured in this closeout package.",
            "Final evidence remains linked back to the board review pack.",
        ],
        "documentation_updates": documentation_updates
        or [
            {
                "doc_ref": "doc/TODO.md",
                "status": "UPDATED",
                "summary": "Marked P2-GOV-007 as completed after closeout evidence sync landed.",
            },
            {
                "doc_ref": "README.md",
                "status": "NO_CHANGE_REQUIRED",
                "summary": "No public capability or runtime flow changed in this round.",
            },
        ],
    }
    result = {
        "workflow_id": workflow_id,
        "ticket_id": ticket_id,
        "node_id": node_id,
        "submitted_by": submitted_by,
        "result_status": "completed",
        "schema_version": "delivery_closeout_package_v1",
        "payload": payload,
        "artifact_refs": [closeout_ref],
        "written_artifacts": [
            {
                "path": written_artifact_path or f"20-evidence/closeout/{ticket_id}/delivery-closeout-package.json",
                "artifact_ref": closeout_ref,
                "kind": "JSON",
                "content_json": payload,
            }
        ],
        "assumptions": ["Closeout package stays within the already approved scope and final board choice."],
        "issues": [],
        "confidence": 0.82,
        "needs_escalation": False,
        "summary": "Structured delivery closeout package submitted.",
        "failure_kind": None,
        "failure_message": None,
        "failure_detail": None,
        "idempotency_key": idempotency_key or f"ticket-result-submit:{workflow_id}:{ticket_id}:closeout",
    }
    if include_review_request:
        resolved_review_request = review_request or _internal_closeout_review_request()
        if review_request is None:
            resolved_review_request = {
                **resolved_review_request,
                "options": [
                    {
                        **resolved_review_request["options"][0],
                        "artifact_refs": [closeout_ref],
                    }
                ],
                "evidence_summary": [
                    {
                        **resolved_review_request["evidence_summary"][0],
                        "source_ref": closeout_ref,
                    }
                ],
            }
        result["review_request"] = resolved_review_request
    return result


def _ticket_cancel_payload(
    workflow_id: str = "wf_seed",
    ticket_id: str = "tkt_visual_001",
    node_id: str = "node_homepage_visual",
    cancelled_by: str = "emp_ops_1",
    reason: str = "Operator requested controlled cancellation.",
    idempotency_key: str | None = None,
) -> dict:
    return {
        "workflow_id": workflow_id,
        "ticket_id": ticket_id,
        "node_id": node_id,
        "cancelled_by": cancelled_by,
        "reason": reason,
        "idempotency_key": idempotency_key or f"ticket-cancel:{workflow_id}:{ticket_id}",
    }


def _ticket_create_payload(
    workflow_id: str = "wf_seed",
    ticket_id: str = "tkt_visual_001",
    node_id: str = "node_homepage_visual",
    attempt_no: int = 1,
    role_profile_ref: str | None = None,
    lease_timeout_sec: int = 600,
    retry_budget: int = 2,
    on_timeout: str = "retry",
    on_schema_error: str = "retry",
    on_repeat_failure: str = "escalate_ceo",
    repeat_failure_threshold: int = 2,
    timeout_repeat_threshold: int = 2,
    timeout_backoff_multiplier: float = 1.5,
    timeout_backoff_cap_multiplier: float = 2.0,
    allowed_write_set: list[str] | None = None,
    input_artifact_refs: list[str] | None = None,
    acceptance_criteria: list[str] | None = None,
    output_schema_ref: str = "ui_milestone_review",
    output_schema_version: int = 1,
    allowed_tools: list[str] | None = None,
    context_query_plan: dict | None = None,
    tenant_id: str | None = None,
    workspace_id: str | None = None,
    delivery_stage: str | None = None,
    parent_ticket_id: str | None = None,
    dispatch_intent: dict | None = None,
) -> dict:
    resolved_role_profile_ref = role_profile_ref
    if resolved_role_profile_ref is None:
        resolved_role_profile_ref = (
            "ui_designer_primary" if output_schema_ref == "consensus_document" else "frontend_engineer_primary"
        )
    payload = {
        "ticket_id": ticket_id,
        "workflow_id": workflow_id,
        "node_id": node_id,
        "parent_ticket_id": parent_ticket_id,
        "attempt_no": attempt_no,
        "role_profile_ref": resolved_role_profile_ref,
        "constraints_ref": "global_constraints_v3",
        "input_artifact_refs": input_artifact_refs or ["art://inputs/brief.md", "art://inputs/brand-guide.md"],
        "context_query_plan": context_query_plan or {
            "keywords": ["homepage", "brand", "visual"],
            "semantic_queries": ["approved visual direction"],
            "max_context_tokens": 3000,
        },
        "acceptance_criteria": acceptance_criteria or [
            "Must satisfy approved visual direction",
            "Must produce 2 options",
            "Must include rationale and risks",
        ],
        "output_schema_ref": output_schema_ref,
        "output_schema_version": output_schema_version,
        "allowed_tools": allowed_tools or ["read_artifact", "write_artifact", "image_gen"],
        "allowed_write_set": allowed_write_set or ["artifacts/ui/homepage/*", "reports/review/*"],
        "lease_timeout_sec": lease_timeout_sec,
        "retry_budget": retry_budget,
        "priority": "high",
        "timeout_sla_sec": 1800,
        "deadline_at": "2026-03-28T18:00:00+08:00",
        "graph_contract": {
            "lane_kind": "execution",
        },
        "escalation_policy": {
            "on_timeout": on_timeout,
            "on_schema_error": on_schema_error,
            "on_repeat_failure": on_repeat_failure,
            "repeat_failure_threshold": repeat_failure_threshold,
            "timeout_repeat_threshold": timeout_repeat_threshold,
            "timeout_backoff_multiplier": timeout_backoff_multiplier,
            "timeout_backoff_cap_multiplier": timeout_backoff_cap_multiplier,
        },
        "idempotency_key": f"ticket-create:{workflow_id}:{ticket_id}",
    }
    if tenant_id is not None:
        payload["tenant_id"] = tenant_id
    if workspace_id is not None:
        payload["workspace_id"] = workspace_id
    if delivery_stage is not None:
        payload["delivery_stage"] = delivery_stage
    if dispatch_intent is not None:
        payload["dispatch_intent"] = dispatch_intent
    return payload


def _ticket_start_payload(
    workflow_id: str = "wf_seed",
    ticket_id: str = "tkt_visual_001",
    node_id: str = "node_homepage_visual",
    started_by: str = "emp_frontend_2",
    expected_ticket_version: int | None = None,
    expected_node_version: int | None = None,
    expected_runtime_node_version: int | None = None,
) -> dict:
    payload = {
        "workflow_id": workflow_id,
        "ticket_id": ticket_id,
        "node_id": node_id,
        "started_by": started_by,
        "idempotency_key": f"ticket-start:{workflow_id}:{ticket_id}",
    }
    if expected_ticket_version is not None:
        payload["expected_ticket_version"] = expected_ticket_version
    if expected_node_version is not None:
        payload["expected_node_version"] = expected_node_version
    if expected_runtime_node_version is not None:
        payload["expected_runtime_node_version"] = expected_runtime_node_version
    return payload


def _ticket_lease_payload(
    workflow_id: str = "wf_seed",
    ticket_id: str = "tkt_visual_001",
    node_id: str = "node_homepage_visual",
    leased_by: str = "emp_frontend_2",
    lease_timeout_sec: int = 600,
) -> dict:
    return {
        "workflow_id": workflow_id,
        "ticket_id": ticket_id,
        "node_id": node_id,
        "leased_by": leased_by,
        "lease_timeout_sec": lease_timeout_sec,
        "idempotency_key": f"ticket-lease:{workflow_id}:{ticket_id}:{leased_by}",
    }


def _ticket_fail_payload(
    workflow_id: str = "wf_seed",
    ticket_id: str = "tkt_visual_001",
    node_id: str = "node_homepage_visual",
    failure_kind: str = "RUNTIME_ERROR",
    failure_message: str = "Worker execution failed.",
    failure_detail: dict | None = None,
    idempotency_key: str | None = None,
) -> dict:
    return {
        "workflow_id": workflow_id,
        "ticket_id": ticket_id,
        "node_id": node_id,
        "failed_by": "emp_frontend_2",
        "failure_kind": failure_kind,
        "failure_message": failure_message,
        "failure_detail": failure_detail or {"step": "render", "exit_code": 1},
        "idempotency_key": idempotency_key or f"ticket-fail:{workflow_id}:{ticket_id}:{failure_kind}",
    }


def _ticket_heartbeat_payload(
    workflow_id: str = "wf_seed",
    ticket_id: str = "tkt_visual_001",
    node_id: str = "node_homepage_visual",
    reported_by: str = "emp_frontend_2",
) -> dict:
    return {
        "workflow_id": workflow_id,
        "ticket_id": ticket_id,
        "node_id": node_id,
        "reported_by": reported_by,
        "idempotency_key": f"ticket-heartbeat:{workflow_id}:{ticket_id}:{reported_by}",
    }


def _scheduler_tick_payload(workers: list[dict] | None = None, idempotency_key: str = "scheduler-tick:1") -> dict:
    payload = {
        "max_dispatches": 10,
        "idempotency_key": idempotency_key,
    }
    if workers is not None:
        payload["workers"] = workers
    return payload


def _incident_resolve_payload(
    incident_id: str,
    resolved_by: str = "emp_ops_1",
    resolution_summary: str = "Operator confirmed mitigation and reopened dispatch on the node.",
    idempotency_key: str | None = None,
    followup_action: str | None = None,
) -> dict:
    payload = {
        "incident_id": incident_id,
        "resolved_by": resolved_by,
        "resolution_summary": resolution_summary,
        "idempotency_key": idempotency_key or f"incident-resolve:{incident_id}",
    }
    if followup_action is not None:
        payload["followup_action"] = followup_action
    return payload


def _ensure_runtime_provider_ready_for_ticket(
    client,
    *,
    role_profile_ref: str | None,
    output_schema_ref: str,
) -> None:
    resolved_role_profile_ref = role_profile_ref
    if resolved_role_profile_ref is None:
        resolved_role_profile_ref = (
            "ui_designer_primary" if output_schema_ref == "consensus_document" else "frontend_engineer_primary"
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
        provider["provider_id"] == "prov_openai_compat" and provider["enabled"]
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
        json=_runtime_provider_upsert_payload(
            role_bindings=[
                {
                    "target_ref": "ceo_shadow",
                    "provider_model_entry_refs": ["prov_openai_compat::gpt-5.3-codex"],
                    "max_context_window_override": None,
                    "reasoning_effort_override": None,
                },
                {
                    "target_ref": target_ref,
                    "provider_model_entry_refs": ["prov_openai_compat::gpt-5.3-codex"],
                    "max_context_window_override": None,
                    "reasoning_effort_override": None,
                },
            ],
            idempotency_key=f"runtime-provider-upsert:test-helper:{target_ref}",
        ),
    )
    assert upsert_response.status_code == 200
    assert upsert_response.json()["status"] == "ACCEPTED"


def _create_and_lease_ticket(
    client,
    workflow_id: str = "wf_seed",
    ticket_id: str = "tkt_visual_001",
    node_id: str = "node_homepage_visual",
    attempt_no: int = 1,
    leased_by: str = "emp_frontend_2",
    lease_timeout_sec: int = 600,
    role_profile_ref: str | None = None,
    retry_budget: int = 2,
    on_timeout: str = "retry",
    on_schema_error: str = "retry",
    on_repeat_failure: str = "escalate_ceo",
    repeat_failure_threshold: int = 2,
    timeout_repeat_threshold: int = 2,
    timeout_backoff_multiplier: float = 1.5,
    timeout_backoff_cap_multiplier: float = 2.0,
    allowed_write_set: list[str] | None = None,
    input_artifact_refs: list[str] | None = None,
    acceptance_criteria: list[str] | None = None,
    output_schema_ref: str = "ui_milestone_review",
    output_schema_version: int = 1,
    allowed_tools: list[str] | None = None,
    context_query_plan: dict | None = None,
    tenant_id: str | None = None,
    workspace_id: str | None = None,
    delivery_stage: str | None = None,
) -> None:
    if tenant_id is not None and workspace_id is not None:
        _ensure_scoped_workflow(
            client,
            workflow_id=workflow_id,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
        )
    _ensure_runtime_provider_ready_for_ticket(
        client,
        role_profile_ref=role_profile_ref,
        output_schema_ref=output_schema_ref,
    )
    create_response = client.post(
        "/api/v1/commands/ticket-create",
        json=_ticket_create_payload(
            workflow_id=workflow_id,
            ticket_id=ticket_id,
            node_id=node_id,
            attempt_no=attempt_no,
            role_profile_ref=role_profile_ref,
            lease_timeout_sec=lease_timeout_sec,
            retry_budget=retry_budget,
            on_timeout=on_timeout,
            on_schema_error=on_schema_error,
            on_repeat_failure=on_repeat_failure,
            repeat_failure_threshold=repeat_failure_threshold,
            timeout_repeat_threshold=timeout_repeat_threshold,
            timeout_backoff_multiplier=timeout_backoff_multiplier,
            timeout_backoff_cap_multiplier=timeout_backoff_cap_multiplier,
            allowed_write_set=allowed_write_set,
            input_artifact_refs=input_artifact_refs,
            acceptance_criteria=acceptance_criteria,
            output_schema_ref=output_schema_ref,
            output_schema_version=output_schema_version,
            allowed_tools=allowed_tools,
            context_query_plan=context_query_plan,
            delivery_stage=delivery_stage,
        ),
    )
    assert create_response.status_code == 200
    assert create_response.json()["status"] == "ACCEPTED"
    _ensure_default_governance_profile(client, workflow_id=workflow_id)

    lease_response = client.post(
        "/api/v1/commands/ticket-lease",
        json=_ticket_lease_payload(
            workflow_id=workflow_id,
            ticket_id=ticket_id,
            node_id=node_id,
            leased_by=leased_by,
            lease_timeout_sec=lease_timeout_sec,
        ),
    )
    assert lease_response.status_code == 200
    assert lease_response.json()["status"] == "ACCEPTED"


def _create_lease_and_start_ticket(
    client,
    workflow_id: str = "wf_seed",
    ticket_id: str = "tkt_visual_001",
    node_id: str = "node_homepage_visual",
    attempt_no: int = 1,
    leased_by: str = "emp_frontend_2",
    lease_timeout_sec: int = 600,
    role_profile_ref: str | None = None,
    retry_budget: int = 2,
    on_timeout: str = "retry",
    on_schema_error: str = "retry",
    on_repeat_failure: str = "escalate_ceo",
    repeat_failure_threshold: int = 2,
    timeout_repeat_threshold: int = 2,
    timeout_backoff_multiplier: float = 1.5,
    timeout_backoff_cap_multiplier: float = 2.0,
    allowed_write_set: list[str] | None = None,
    input_artifact_refs: list[str] | None = None,
    acceptance_criteria: list[str] | None = None,
    output_schema_ref: str = "ui_milestone_review",
    output_schema_version: int = 1,
    allowed_tools: list[str] | None = None,
    context_query_plan: dict | None = None,
    tenant_id: str | None = None,
    workspace_id: str | None = None,
    delivery_stage: str | None = None,
) -> None:
    _create_and_lease_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id=ticket_id,
        node_id=node_id,
        attempt_no=attempt_no,
        leased_by=leased_by,
        lease_timeout_sec=lease_timeout_sec,
        role_profile_ref=role_profile_ref,
        retry_budget=retry_budget,
        on_timeout=on_timeout,
        on_schema_error=on_schema_error,
        on_repeat_failure=on_repeat_failure,
        repeat_failure_threshold=repeat_failure_threshold,
        timeout_repeat_threshold=timeout_repeat_threshold,
        timeout_backoff_multiplier=timeout_backoff_multiplier,
        timeout_backoff_cap_multiplier=timeout_backoff_cap_multiplier,
        allowed_write_set=allowed_write_set,
        input_artifact_refs=input_artifact_refs,
        acceptance_criteria=acceptance_criteria,
        output_schema_ref=output_schema_ref,
        output_schema_version=output_schema_version,
        allowed_tools=allowed_tools,
        context_query_plan=context_query_plan,
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        delivery_stage=delivery_stage,
    )
    start_response = client.post(
        "/api/v1/commands/ticket-start",
        json=_ticket_start_payload(
            workflow_id=workflow_id,
            ticket_id=ticket_id,
            node_id=node_id,
            started_by=leased_by,
        ),
    )
    assert start_response.status_code == 200
    assert start_response.json()["status"] == "ACCEPTED"


def _seed_review_request(
    client,
    workflow_id: str = "wf_seed",
    materialize_real_compile: bool = False,
    compiled_context_bundle_ref: str = "ctx://homepage/visual-v1",
    compile_manifest_ref: str = "manifest://homepage/visual-v1",
    rendered_execution_payload_ref: str | None = None,
) -> dict:
    _create_lease_and_start_ticket(client, workflow_id=workflow_id)
    if materialize_real_compile:
        repository = client.app.state.repository
        ticket = repository.get_current_ticket_projection("tkt_visual_001")
        assert ticket is not None
        compile_and_persist_execution_artifacts(repository, ticket)
    maker_response = client.post(
        "/api/v1/commands/ticket-complete",
        json=_ticket_complete_payload(
            workflow_id=workflow_id,
            compiled_context_bundle_ref=compiled_context_bundle_ref,
            compile_manifest_ref=compile_manifest_ref,
            rendered_execution_payload_ref=rendered_execution_payload_ref,
        ),
    )
    assert maker_response.status_code == 200
    assert maker_response.json()["status"] == "ACCEPTED"

    repository = client.app.state.repository
    node_projection = repository.get_current_node_projection(workflow_id, "node_homepage_visual")
    assert node_projection is not None
    checker_ticket_id = node_projection["latest_ticket_id"]
    assert checker_ticket_id != "tkt_visual_001"
    assert repository.list_open_approvals() == []

    checker_lease_response = client.post(
        "/api/v1/commands/ticket-lease",
        json=_ticket_lease_payload(
            workflow_id=workflow_id,
            ticket_id=checker_ticket_id,
            leased_by="emp_checker_1",
        ),
    )
    assert checker_lease_response.status_code == 200
    assert checker_lease_response.json()["status"] == "ACCEPTED"

    checker_start_response = client.post(
        "/api/v1/commands/ticket-start",
        json=_ticket_start_payload(
            workflow_id=workflow_id,
            ticket_id=checker_ticket_id,
            started_by="emp_checker_1",
        ),
    )
    assert checker_start_response.status_code == 200
    assert checker_start_response.json()["status"] == "ACCEPTED"

    checker_result_response = client.post(
        "/api/v1/commands/ticket-result-submit",
        json=_maker_checker_result_submit_payload(
            workflow_id=workflow_id,
            ticket_id=checker_ticket_id,
        ),
    )
    assert checker_result_response.status_code == 200
    assert checker_result_response.json()["status"] == "ACCEPTED"

    approvals = repository.list_open_approvals()
    assert len(approvals) == 1
    return approvals[0]


def _project_init_to_scope_approval(client) -> tuple[str, dict]:
    response = client.post("/api/v1/commands/project-init", json=_project_init_payload("Ship MVP A"))

    assert response.status_code == 200
    assert response.json()["status"] == "ACCEPTED"

    workflow_id = response.json()["causation_hint"].split(":", 1)[1]

    _create_lease_and_start_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_scope_review_001",
        node_id="node_scope_review",
        output_schema_ref="consensus_document",
        allowed_write_set=["reports/meeting/*"],
        input_artifact_refs=[
            f"art://project-init/{workflow_id}/board-brief.md",
            "art://inputs/scope-notes.md",
        ],
        acceptance_criteria=["Must produce a consensus document", "Must include follow-up tickets"],
        allowed_tools=["read_artifact", "write_artifact"],
        context_query_plan={
            "keywords": ["scope", "decision", "meeting"],
            "semantic_queries": ["current scope tradeoffs"],
            "max_context_tokens": 3000,
        },
    )
    maker_response = client.post(
        "/api/v1/commands/ticket-result-submit",
        json=_consensus_document_result_submit_payload(
            workflow_id=workflow_id,
            ticket_id="tkt_scope_review_001",
            node_id="node_scope_review",
            include_review_request=True,
            review_request=_meeting_escalation_review_request(),
        ),
    )
    assert maker_response.status_code == 200
    assert maker_response.json()["status"] == "ACCEPTED"

    repository = client.app.state.repository
    checker_ticket_id = repository.get_current_node_projection(workflow_id, "node_scope_review")["latest_ticket_id"]
    checker_lease_response = client.post(
        "/api/v1/commands/ticket-lease",
        json=_ticket_lease_payload(
            workflow_id=workflow_id,
            ticket_id=checker_ticket_id,
            node_id="node_scope_review",
            leased_by="emp_checker_1",
        ),
    )
    assert checker_lease_response.status_code == 200
    assert checker_lease_response.json()["status"] == "ACCEPTED"
    checker_start_response = client.post(
        "/api/v1/commands/ticket-start",
        json=_ticket_start_payload(
            workflow_id=workflow_id,
            ticket_id=checker_ticket_id,
            node_id="node_scope_review",
            started_by="emp_checker_1",
        ),
    )
    assert checker_start_response.status_code == 200
    assert checker_start_response.json()["status"] == "ACCEPTED"
    checker_result_response = client.post(
        "/api/v1/commands/ticket-result-submit",
        json=_maker_checker_result_submit_payload(
            workflow_id=workflow_id,
            ticket_id=checker_ticket_id,
            node_id="node_scope_review",
        ),
    )
    assert checker_result_response.status_code == 200
    assert checker_result_response.json()["status"] == "ACCEPTED"

    approvals = client.app.state.repository.list_open_approvals()
    assert len(approvals) == 1
    assert approvals[0]["workflow_id"] == workflow_id
    assert approvals[0]["approval_type"] == "MEETING_ESCALATION"
    return workflow_id, approvals[0]


def test_ticket_create_infers_internal_governance_review_request_for_governance_document(client):
    workflow_id = "wf_governance_auto_review"
    ticket_id = "tkt_governance_auto_review"
    node_id = "node_governance_auto_review"

    response = client.post(
        "/api/v1/commands/ticket-create",
        json=_ticket_create_payload(
            workflow_id=workflow_id,
            ticket_id=ticket_id,
            node_id=node_id,
            role_profile_ref="frontend_engineer_primary",
            output_schema_ref="architecture_brief",
            allowed_tools=["read_artifact", "write_artifact"],
            allowed_write_set=[f"reports/governance/{ticket_id}/*"],
            acceptance_criteria=["Must produce a structured architecture brief."],
        ),
    )

    repository = client.app.state.repository
    with repository.connection() as connection:
        created_spec = repository.get_latest_ticket_created_payload(connection, ticket_id)

    assert response.status_code == 200
    assert response.json()["status"] == "ACCEPTED"
    assert created_spec is not None
    assert created_spec["auto_review_request"]["review_type"] == "INTERNAL_GOVERNANCE_REVIEW"
    assert "governance" in created_spec["auto_review_request"]["title"].lower()


def test_governance_document_completion_routes_to_internal_checker_and_stays_off_board(client):
    workflow_id = "wf_governance_internal_gate"
    ticket_id = "tkt_governance_internal_gate"
    node_id = "node_governance_internal_gate"

    _create_lease_and_start_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id=ticket_id,
        node_id=node_id,
        role_profile_ref="frontend_engineer_primary",
        output_schema_ref="architecture_brief",
        allowed_tools=["read_artifact", "write_artifact"],
        allowed_write_set=[f"reports/governance/{ticket_id}/*"],
        acceptance_criteria=["Must produce a structured architecture brief."],
    )

    maker_response = client.post(
        "/api/v1/commands/ticket-result-submit",
        json=_governance_document_result_submit_payload(
            workflow_id=workflow_id,
            ticket_id=ticket_id,
            node_id=node_id,
        ),
    )

    repository = client.app.state.repository
    current_node = repository.get_current_node_projection(workflow_id, node_id)
    assert current_node is not None
    checker_ticket_id = current_node["latest_ticket_id"]
    with repository.connection() as connection:
        checker_created_spec = repository.get_latest_ticket_created_payload(connection, checker_ticket_id)

    client.post(
        "/api/v1/commands/ticket-lease",
        json=_ticket_lease_payload(
            workflow_id=workflow_id,
            ticket_id=checker_ticket_id,
            node_id=node_id,
            leased_by="emp_checker_1",
        ),
    )
    client.post(
        "/api/v1/commands/ticket-start",
        json=_ticket_start_payload(
            workflow_id=workflow_id,
            ticket_id=checker_ticket_id,
            node_id=node_id,
            started_by="emp_checker_1",
        ),
    )
    checker_response = client.post(
        "/api/v1/commands/ticket-result-submit",
        json=_maker_checker_result_submit_payload(
            workflow_id=workflow_id,
            ticket_id=checker_ticket_id,
            node_id=node_id,
            review_status="APPROVED_WITH_NOTES",
            idempotency_key=f"ticket-result-submit:{workflow_id}:{checker_ticket_id}:governance-approved",
        ),
    )

    current_node = repository.get_current_node_projection(workflow_id, node_id)
    approvals = [item for item in repository.list_open_approvals() if item["workflow_id"] == workflow_id]

    assert maker_response.status_code == 200
    assert maker_response.json()["status"] == "ACCEPTED"
    assert checker_created_spec is not None
    assert checker_created_spec["output_schema_ref"] == "maker_checker_verdict"
    assert checker_created_spec["maker_checker_context"]["maker_ticket_id"] == ticket_id
    assert checker_created_spec["maker_checker_context"]["original_review_request"]["review_type"] == (
        "INTERNAL_GOVERNANCE_REVIEW"
    )
    assert checker_response.status_code == 200
    assert checker_response.json()["status"] == "ACCEPTED"
    assert approvals == []
    assert current_node["status"] == NODE_STATUS_COMPLETED


def test_governance_checker_changes_required_creates_fix_ticket(client):
    workflow_id = "wf_governance_rework_gate"
    ticket_id = "tkt_governance_rework_gate"
    node_id = "node_governance_rework_gate"

    _create_lease_and_start_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id=ticket_id,
        node_id=node_id,
        role_profile_ref="frontend_engineer_primary",
        output_schema_ref="architecture_brief",
        allowed_tools=["read_artifact", "write_artifact"],
        allowed_write_set=[f"reports/governance/{ticket_id}/*"],
        acceptance_criteria=["Must produce a structured architecture brief."],
    )

    client.post(
        "/api/v1/commands/ticket-result-submit",
        json=_governance_document_result_submit_payload(
            workflow_id=workflow_id,
            ticket_id=ticket_id,
            node_id=node_id,
        ),
    )

    repository = client.app.state.repository
    checker_ticket_id = repository.get_current_node_projection(workflow_id, node_id)["latest_ticket_id"]
    client.post(
        "/api/v1/commands/ticket-lease",
        json=_ticket_lease_payload(
            workflow_id=workflow_id,
            ticket_id=checker_ticket_id,
            node_id=node_id,
            leased_by="emp_checker_1",
        ),
    )
    client.post(
        "/api/v1/commands/ticket-start",
        json=_ticket_start_payload(
            workflow_id=workflow_id,
            ticket_id=checker_ticket_id,
            node_id=node_id,
            started_by="emp_checker_1",
        ),
    )
    checker_response = client.post(
        "/api/v1/commands/ticket-result-submit",
        json=_maker_checker_result_submit_payload(
            workflow_id=workflow_id,
            ticket_id=checker_ticket_id,
            node_id=node_id,
            review_status="CHANGES_REQUIRED",
            findings=[
                {
                    "finding_id": "finding_governance_gap",
                    "severity": "high",
                    "category": "GOVERNANCE_TRACEABILITY",
                    "headline": "Governance document still leaves one blocking decision undocumented.",
                    "summary": "The document misses the explicit downstream boundary for the next delivery slice.",
                    "required_action": "Add the missing decision boundary before re-submitting the governance document.",
                    "blocking": True,
                }
            ],
            idempotency_key=f"ticket-result-submit:{workflow_id}:{checker_ticket_id}:governance-rework",
        ),
    )

    fix_ticket_id = repository.get_current_node_projection(workflow_id, node_id)["latest_ticket_id"]
    with repository.connection() as connection:
        fix_created_spec = repository.get_latest_ticket_created_payload(connection, fix_ticket_id)

    assert checker_response.status_code == 200
    assert checker_response.json()["status"] == "ACCEPTED"
    assert fix_created_spec is not None
    assert fix_created_spec["output_schema_ref"] == "architecture_brief"
    assert fix_created_spec["ticket_kind"] == "MAKER_REWORK_FIX"
    assert fix_created_spec["maker_checker_context"]["checker_ticket_id"] == checker_ticket_id
    assert fix_created_spec["maker_checker_context"]["original_review_request"]["review_type"] == (
        "INTERNAL_GOVERNANCE_REVIEW"
    )


def _approve_open_review(client, approval: dict, *, idempotency_suffix: str = "1"):
    option_id = approval["payload"]["review_pack"]["options"][0]["option_id"]
    response = client.post(
        "/api/v1/commands/board-approve",
        json={
            "review_pack_id": approval["review_pack_id"],
            "review_pack_version": approval["review_pack_version"],
            "command_target_version": approval["command_target_version"],
            "approval_id": approval["approval_id"],
            "selected_option_id": option_id,
            "board_comment": "Proceed with the approved scope.",
            "idempotency_key": f"board-approve:{approval['approval_id']}:{idempotency_suffix}",
        },
    )
    if response.status_code == 200 and response.json()["status"] == "ACCEPTED":
        approval_type = approval.get("approval_type")
        if approval_type == "MEETING_ESCALATION":
            auto_advance_workflow_to_next_stop(
                client.app.state.repository,
                workflow_id=approval["workflow_id"],
                idempotency_key_prefix=f"test-auto-advance:{approval['approval_id']}:{idempotency_suffix}",
                max_steps=8,
                max_dispatches=8,
            )
    return response


def _artifact_storage_path(client, artifact_ref: str):
    artifact = client.app.state.repository.get_artifact_by_ref(artifact_ref)
    assert artifact is not None
    assert artifact["storage_relpath"] is not None
    return client.app.state.artifact_store.root / artifact["storage_relpath"]


def _scope_followup_payload(client, approval: dict) -> dict:
    consensus_artifact_ref = approval["payload"]["review_pack"]["evidence_summary"][0]["source_ref"]
    artifact_path = _artifact_storage_path(client, consensus_artifact_ref)
    return json.loads(artifact_path.read_text(encoding="utf-8"))


@contextmanager
def _suppress_ceo_shadow_side_effects():
    with patch("app.core.ticket_handlers._trigger_ceo_shadow_safely", lambda *args, **kwargs: None), patch(
        "app.core.approval_handlers._trigger_ceo_shadow_safely", lambda *args, **kwargs: None
    ):
        yield


def _assert_command_accepted(response):
    assert response.status_code == 200
    assert response.json()["status"] == "ACCEPTED"
    return response


def _ui_milestone_review_result_submit_payload(
    *,
    workflow_id: str,
    ticket_id: str,
    node_id: str,
    idempotency_key: str | None = None,
) -> dict:
    option_a_ref = f"art://runtime/{ticket_id}/option-a.png"
    option_b_ref = f"art://runtime/{ticket_id}/option-b.png"
    return _ticket_result_submit_payload(
        workflow_id=workflow_id,
        ticket_id=ticket_id,
        node_id=node_id,
        include_review_request=True,
        artifact_refs=[option_a_ref, option_b_ref],
        written_artifacts=[
            {
                "path": f"artifacts/ui/scope-followups/{ticket_id}/option-a.png",
                "artifact_ref": option_a_ref,
                "kind": "IMAGE",
            },
            {
                "path": f"artifacts/ui/scope-followups/{ticket_id}/option-b.png",
                "artifact_ref": option_b_ref,
                "kind": "IMAGE",
            },
        ],
        idempotency_key=idempotency_key or f"ticket-result-submit:{workflow_id}:{ticket_id}:completed",
    )


def _workspace_scope_followup_source_code_delivery_result_submit_payload(
    *,
    workflow_id: str,
    ticket_id: str,
    node_id: str,
    idempotency_key: str | None = None,
) -> dict:
    source_file_ref = f"art://workspace/{ticket_id}/source.ts"
    verification_ref = f"art://workspace/{ticket_id}/test-report.json"
    git_ref = f"art://workspace/{ticket_id}/git-commit.json"
    verification_path = f"20-evidence/tests/{ticket_id}/attempt-1/test-report.json"
    payload = {
        "summary": f"Source code delivery prepared for {ticket_id}.",
        "source_file_refs": [source_file_ref],
        "source_files": [
            {
                "artifact_ref": source_file_ref,
                "path": f"10-project/src/{ticket_id}.ts",
                "content": "export const scopeFollowupBuild = true;\n",
            }
        ],
        "verification_runs": [
            {
                "artifact_ref": verification_ref,
                "path": verification_path,
                "runner": "pytest",
                "command": "pytest backend/tests/test_api.py -q",
                "status": "passed",
                "exit_code": 0,
                "duration_sec": 1.2,
                "stdout": "collected 1 item\n\n1 passed in 0.12s\n",
                "stderr": "",
                "discovered_count": 1,
                "passed_count": 1,
                "failed_count": 0,
                "skipped_count": 0,
                "failures": [],
            }
        ],
        "implementation_notes": ["Implementation stayed inside the approved scope lock."],
        "documentation_updates": [
            {
                "doc_ref": "10-project/docs/tracking/active-tasks.md",
                "status": "UPDATED",
                "summary": "Updated the active task index after implementation.",
            },
            {
                "doc_ref": "10-project/docs/history/memory-recent.md",
                "status": "NO_CHANGE_REQUIRED",
                "summary": "No new cross-ticket memory had to be recorded.",
            },
        ],
    }
    return {
        "workflow_id": workflow_id,
        "ticket_id": ticket_id,
        "node_id": node_id,
        "submitted_by": "emp_frontend_2",
        "result_status": "completed",
        "schema_version": "source_code_delivery_v1",
        "payload": payload,
        "artifact_refs": [],
        "written_artifacts": [
            {
                "path": f"10-project/src/{ticket_id}.ts",
                "artifact_ref": source_file_ref,
                "kind": "TEXT",
                "content_text": "export const scopeFollowupBuild = true;\n",
            },
            {
                "path": f"10-project/docs/tracking/{ticket_id}-active.md",
                "artifact_ref": f"art://workspace/{ticket_id}/active-task.md",
                "kind": "TEXT",
                "content_text": "Updated active task summary.\n",
            },
            {
                "path": f"10-project/docs/history/{ticket_id}-memory.md",
                "artifact_ref": f"art://workspace/{ticket_id}/memory.md",
                "kind": "TEXT",
                "content_text": "Updated recent memory.\n",
            },
            {
                "path": verification_path,
                "artifact_ref": verification_ref,
                "kind": "JSON",
                "content_json": payload["verification_runs"][0],
            },
            {
                "path": f"20-evidence/git/{ticket_id}/attempt-1/git-closeout.json",
                "artifact_ref": git_ref,
                "kind": "JSON",
                "content_json": {"commit_sha": "abc1234", "branch_ref": f"codex/{ticket_id}"},
            },
        ],
        "verification_evidence_refs": [verification_ref],
        "git_commit_record": {
            "commit_sha": "abc1234",
            "branch_ref": f"codex/{ticket_id}",
            "merge_status": "PENDING_REVIEW_GATE",
        },
        "assumptions": ["Project workspace receipts are enabled."],
        "issues": [],
        "confidence": 0.91,
        "needs_escalation": False,
        "summary": "Structured source code delivery submitted.",
        "failure_kind": None,
        "failure_message": None,
        "failure_detail": None,
        "review_request": _internal_delivery_review_request(),
        "idempotency_key": idempotency_key or f"ticket-result-submit:{workflow_id}:{ticket_id}:source-code-delivery",
    }


def _complete_scope_followup_chain_to_visual_milestone(
    client,
    scope_approval: dict,
    *,
    idempotency_suffix: str = "scope-chain",
) -> tuple[str, dict, dict]:
    workflow_id = scope_approval["workflow_id"]
    with _suppress_ceo_shadow_side_effects():
        _assert_command_accepted(
            client.post(
                "/api/v1/commands/runtime-provider-upsert",
                json=_runtime_provider_upsert_payload(
                    idempotency_key=f"runtime-provider-upsert:{workflow_id}:{idempotency_suffix}",
                ),
            )
        )
        scope_response = _approve_open_review(client, scope_approval, idempotency_suffix=idempotency_suffix)
        _assert_command_accepted(scope_response)

        followup_payload = _scope_followup_payload(client, scope_approval)
        build_ticket_id, check_ticket_id, review_ticket_id = [
            item["ticket_id"] for item in followup_payload["followup_tickets"]
        ]
        build_node_id = f"node_followup_{build_ticket_id.removeprefix('tkt_')}"
        check_node_id = f"node_followup_{check_ticket_id.removeprefix('tkt_')}"
        review_node_id = f"node_followup_{review_ticket_id.removeprefix('tkt_')}"
        repository = client.app.state.repository

        def _lease_and_start(ticket_id: str, node_id: str, worker_id: str) -> None:
            _assert_command_accepted(
                client.post(
                    "/api/v1/commands/ticket-lease",
                    json=_ticket_lease_payload(
                        workflow_id=workflow_id,
                        ticket_id=ticket_id,
                        node_id=node_id,
                        leased_by=worker_id,
                    ),
                )
            )
            _assert_command_accepted(
                client.post(
                    "/api/v1/commands/ticket-start",
                    json=_ticket_start_payload(
                        workflow_id=workflow_id,
                        ticket_id=ticket_id,
                        node_id=node_id,
                        started_by=worker_id,
                    ),
                )
            )

        _lease_and_start(build_ticket_id, build_node_id, "emp_frontend_2")
        _assert_command_accepted(
            client.post(
                "/api/v1/commands/ticket-result-submit",
                json=_workspace_scope_followup_source_code_delivery_result_submit_payload(
                    workflow_id=workflow_id,
                    ticket_id=build_ticket_id,
                    node_id=build_node_id,
                    idempotency_key=f"ticket-result-submit:{workflow_id}:{build_ticket_id}:source-code-delivery",
                ),
            )
        )
        build_checker_ticket_id = repository.get_current_node_projection(workflow_id, build_node_id)["latest_ticket_id"]
        _lease_and_start(build_checker_ticket_id, build_node_id, "emp_checker_1")
        _assert_command_accepted(
            client.post(
                "/api/v1/commands/ticket-result-submit",
                json=_maker_checker_result_submit_payload(
                    workflow_id=workflow_id,
                    ticket_id=build_checker_ticket_id,
                    node_id=build_node_id,
                    review_status="APPROVED_WITH_NOTES",
                    idempotency_key=f"ticket-result-submit:{workflow_id}:{build_checker_ticket_id}:approved",
                ),
            )
        )

        _lease_and_start(check_ticket_id, check_node_id, "emp_checker_1")
        _assert_command_accepted(
            client.post(
                "/api/v1/commands/ticket-result-submit",
                json=_delivery_check_report_result_submit_payload(
                    workflow_id=workflow_id,
                    ticket_id=check_ticket_id,
                    node_id=check_node_id,
                    include_review_request=True,
                    artifact_refs=[f"art://runtime/{check_ticket_id}/delivery-check-report.json"],
                    idempotency_key=f"ticket-result-submit:{workflow_id}:{check_ticket_id}:delivery-check",
                ),
            )
        )
        check_checker_ticket_id = repository.get_current_node_projection(workflow_id, check_node_id)["latest_ticket_id"]
        _lease_and_start(check_checker_ticket_id, check_node_id, "emp_checker_1")
        _assert_command_accepted(
            client.post(
                "/api/v1/commands/ticket-result-submit",
                json=_maker_checker_result_submit_payload(
                    workflow_id=workflow_id,
                    ticket_id=check_checker_ticket_id,
                    node_id=check_node_id,
                    review_status="APPROVED_WITH_NOTES",
                    idempotency_key=f"ticket-result-submit:{workflow_id}:{check_checker_ticket_id}:approved",
                ),
            )
        )

        _lease_and_start(review_ticket_id, review_node_id, "emp_frontend_2")
        _assert_command_accepted(
            client.post(
                "/api/v1/commands/ticket-result-submit",
                json=_ui_milestone_review_result_submit_payload(
                    workflow_id=workflow_id,
                    ticket_id=review_ticket_id,
                    node_id=review_node_id,
                    idempotency_key=f"ticket-result-submit:{workflow_id}:{review_ticket_id}:review",
                ),
            )
        )
        review_checker_ticket_id = repository.get_current_node_projection(workflow_id, review_node_id)["latest_ticket_id"]
        _lease_and_start(review_checker_ticket_id, review_node_id, "emp_checker_1")
        _assert_command_accepted(
            client.post(
                "/api/v1/commands/ticket-result-submit",
                json=_maker_checker_result_submit_payload(
                    workflow_id=workflow_id,
                    ticket_id=review_checker_ticket_id,
                    node_id=review_node_id,
                    review_status="APPROVED_WITH_NOTES",
                    idempotency_key=f"ticket-result-submit:{workflow_id}:{review_checker_ticket_id}:approved",
                ),
            )
        )

        final_review_approval = next(
            item
            for item in repository.list_open_approvals()
            if item["workflow_id"] == workflow_id and item["approval_type"] == "VISUAL_MILESTONE"
        )
        return workflow_id, final_review_approval, {
            "build_ticket_id": build_ticket_id,
            "check_ticket_id": check_ticket_id,
            "review_ticket_id": review_ticket_id,
        }


def _complete_closeout_chain_after_final_review_approval(
    client,
    approval: dict,
) -> tuple[str, str, str]:
    repository = client.app.state.repository
    workflow_id = approval["workflow_id"]
    logical_review_ticket_id, closeout_ticket_id, closeout_node_id = _expected_closeout_ids(repository, approval)

    with _suppress_ceo_shadow_side_effects():
        _assert_command_accepted(
            client.post(
                "/api/v1/commands/ticket-lease",
                json=_ticket_lease_payload(
                    workflow_id=workflow_id,
                    ticket_id=closeout_ticket_id,
                    node_id=closeout_node_id,
                    leased_by="emp_frontend_2",
                ),
            )
        )
        _assert_command_accepted(
            client.post(
                "/api/v1/commands/ticket-start",
                json=_ticket_start_payload(
                    workflow_id=workflow_id,
                    ticket_id=closeout_ticket_id,
                    node_id=closeout_node_id,
                    started_by="emp_frontend_2",
                ),
            )
        )
        _assert_command_accepted(
            client.post(
                "/api/v1/commands/ticket-result-submit",
                json=_delivery_closeout_package_result_submit_payload(
                    workflow_id=workflow_id,
                    ticket_id=closeout_ticket_id,
                    node_id=closeout_node_id,
                    include_review_request=True,
                    final_artifact_refs=[f"art://runtime/{logical_review_ticket_id}/option-a.png"],
                    idempotency_key=f"ticket-result-submit:{workflow_id}:{closeout_ticket_id}:closeout",
                ),
            )
        )

        checker_ticket_id = repository.get_current_node_projection(workflow_id, closeout_node_id)["latest_ticket_id"]
        _assert_command_accepted(
            client.post(
                "/api/v1/commands/ticket-lease",
                json=_ticket_lease_payload(
                    workflow_id=workflow_id,
                    ticket_id=checker_ticket_id,
                    node_id=closeout_node_id,
                    leased_by="emp_checker_1",
                ),
            )
        )
        _assert_command_accepted(
            client.post(
                "/api/v1/commands/ticket-start",
                json=_ticket_start_payload(
                    workflow_id=workflow_id,
                    ticket_id=checker_ticket_id,
                    node_id=closeout_node_id,
                    started_by="emp_checker_1",
                ),
            )
        )
        _assert_command_accepted(
            client.post(
                "/api/v1/commands/ticket-result-submit",
                json=_maker_checker_result_submit_payload(
                    workflow_id=workflow_id,
                    ticket_id=checker_ticket_id,
                    node_id=closeout_node_id,
                    review_status="APPROVED_WITH_NOTES",
                    idempotency_key=f"ticket-result-submit:{workflow_id}:{checker_ticket_id}:approved",
                ),
            )
        )
    return logical_review_ticket_id, closeout_ticket_id, closeout_node_id


def _seed_cross_workflow_compile_history(client) -> None:
    repository = client.app.state.repository
    artifact_store = client.app.state.artifact_store
    materialized = artifact_store.materialize_text(
        "reports/review/history-homepage.md",
        "# History\n\nApproved homepage brand direction with clearer hierarchy.\n",
    )
    review_payload = {
        "review_pack": {
            "meta": {
                "review_pack_id": "brp_history_compile",
                "workflow_id": "wf_history_compile_review",
                "review_type": "VISUAL_MILESTONE",
                "created_at": "2026-03-27T10:00:00+08:00",
                "priority": "high",
            },
            "subject": {
                "title": "Historical homepage approval",
                "source_node_id": "node_history_review",
                "source_ticket_id": "tkt_history_review",
                "blocking_scope": "NODE_ONLY",
            },
            "trigger": {
                "trigger_event_id": "evt_history_review",
                "trigger_reason": "Historical review result",
                "why_now": "Useful for local retrieval",
            },
            "recommendation": {
                "recommended_action": "APPROVE",
                "recommended_option_id": "A",
                "summary": "Approved homepage direction with strong brand hierarchy.",
            },
            "options": [
                {
                    "option_id": "A",
                    "label": "Approved",
                    "summary": "Approved homepage direction with strong brand hierarchy.",
                    "artifact_refs": [],
                    "preview_assets": [],
                    "pros": [],
                    "cons": [],
                    "risks": [],
                    "estimated_budget_impact_range": None,
                }
            ],
            "evidence_summary": [],
            "delta_summary": None,
            "maker_checker_summary": None,
            "risk_summary": None,
            "budget_impact": None,
            "decision_form": {
                "allowed_actions": ["APPROVE", "REJECT", "MODIFY_CONSTRAINTS"],
                "command_target_version": 1,
                "requires_comment_on_reject": True,
                "requires_constraint_patch_on_modify": True,
            },
            "developer_inspector_refs": None,
        },
        "available_actions": [],
        "draft_defaults": {},
        "inbox_title": "Historical homepage approval",
        "inbox_summary": "Approved homepage direction with strong brand hierarchy.",
        "badges": ["history", "review"],
        "priority": "high",
        "resolution": {
            "selected_option_id": "A",
            "board_comment": "Approved and archived.",
        },
    }
    incident_payload = {
        "incident_id": "inc_history_compile",
        "workflow_id": "wf_history_compile_incident",
        "node_id": "node_history_incident",
        "ticket_id": "tkt_history_incident",
        "incident_type": "REPEATED_FAILURE_ESCALATION",
        "status": "OPEN",
        "severity": "high",
        "fingerprint": "wf_history_compile_incident:history:fingerprint",
        "headline": "Repeated checker rejection",
        "summary": "Homepage run failed after checker rejected weak brand alignment.",
    }
    with repository.transaction() as connection:
        connection.execute(
            """
            INSERT INTO approval_projection (
                approval_id,
                review_pack_id,
                workflow_id,
                approval_type,
                status,
                requested_by,
                resolved_by,
                resolved_at,
                created_at,
                updated_at,
                review_pack_version,
                command_target_version,
                payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "apr_history_compile",
                "brp_history_compile",
                "wf_history_compile_review",
                "VISUAL_MILESTONE",
                "APPROVED",
                "board",
                "board",
                "2026-03-27T10:10:00+08:00",
                "2026-03-27T10:00:00+08:00",
                "2026-03-27T10:10:00+08:00",
                1,
                1,
                json.dumps(review_payload, sort_keys=True),
            ),
        )
        repository.insert_event(
            connection,
            event_type="INCIDENT_OPENED",
            actor_type="system",
            actor_id="system",
            workflow_id="wf_history_compile_incident",
            idempotency_key="incident-opened:wf_history_compile_incident:inc_history_compile",
            causation_id=None,
            correlation_id="wf_history_compile_incident",
            payload=incident_payload,
            occurred_at=datetime.fromisoformat("2026-03-27T10:20:00+08:00"),
        )
        repository.save_artifact_record(
            connection,
            artifact_ref="art://history/compile-homepage.md",
            workflow_id="wf_history_compile_artifact",
            ticket_id="tkt_history_compile_artifact",
            node_id="node_history_compile_artifact",
            logical_path="reports/review/history-homepage.md",
            kind="MARKDOWN",
            media_type="text/markdown",
            materialization_status="MATERIALIZED",
            lifecycle_status="ACTIVE",
            storage_relpath=materialized.storage_relpath,
            content_hash=materialized.content_hash,
            size_bytes=materialized.size_bytes,
            retention_class="REVIEW_EVIDENCE",
            expires_at=None,
            deleted_at=None,
            deleted_by=None,
            delete_reason=None,
            created_at=datetime.fromisoformat("2026-03-27T10:30:00+08:00"),
        )
        repository.refresh_projections(connection)


def test_startup_initializes_schema_and_wal_mode(client, db_path):
    assert db_path.exists()
    repository = client.app.state.repository
    assert repository.get_journal_mode() == "wal"


def test_startup_writes_single_system_initialized_event(client):
    repository = client.app.state.repository

    assert repository.count_events_by_type(EVENT_SYSTEM_INITIALIZED) == 1


def test_dashboard_empty_state_exposes_system_initialized_preview(client):
    response = client.get("/api/v1/projections/dashboard")

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["active_workflow"] is None
    assert body["data"]["pipeline_summary"]["blocked_node_source"] == "no_active_workflow"
    assert body["data"]["pipeline_summary"]["blocked_node_ids"] == []
    assert body["projection_version"] > 0
    assert body["cursor"] is not None
    assert any(
        item["message"] == "SYSTEM_INITIALIZED by system"
        for item in body["data"]["event_stream_preview"]
    )


def test_startup_seeds_minimal_employee_roster(client):
    employees = client.app.state.repository.list_employee_projections(
        states=["ACTIVE"],
        board_approved_only=True,
    )

    assert [employee["employee_id"] for employee in employees] == [
        "emp_checker_1",
        "emp_frontend_2",
    ]
    assert employees[0]["role_profile_refs"] == ["checker_primary"]
    assert employees[1]["role_profile_refs"] == ["frontend_engineer_primary"]


def test_project_init_returns_real_command_ack(client):
    response = client.post("/api/v1/commands/project-init", json=_project_init_payload("Ship MVP A"))

    assert response.status_code == 200
    body = response.json()
    assert body["command_id"].startswith("cmd_")
    assert body["idempotency_key"].startswith("project-init:")
    assert body["status"] == "ACCEPTED"
    assert body["received_at"]


def test_system_initialized_is_written_only_once(client):
    repository = client.app.state.repository

    assert repository.count_events_by_type(EVENT_SYSTEM_INITIALIZED) == 1

    client.post("/api/v1/commands/project-init", json=_project_init_payload("Ship MVP A"))
    duplicate = client.post("/api/v1/commands/project-init", json=_project_init_payload("Ship MVP A"))

    assert duplicate.status_code == 200
    assert duplicate.json()["status"] == "DUPLICATE"
    assert repository.count_events_by_type(EVENT_SYSTEM_INITIALIZED) == 1
    assert repository.count_events_by_type(EVENT_WORKFLOW_CREATED) == 1


def test_project_init_defaults_tenant_and_workspace_in_workflow_projection(client):
    response = client.post("/api/v1/commands/project-init", json=_project_init_payload("Ship MVP A"))

    workflow_id = response.json()["causation_hint"].split(":", 1)[1]
    workflow = client.app.state.repository.get_workflow_projection(workflow_id)

    assert response.status_code == 200
    assert workflow is not None
    assert workflow["tenant_id"] == "tenant_default"
    assert workflow["workspace_id"] == "ws_default"


def test_project_init_auto_advances_to_scope_review(client, set_ticket_time):
    set_ticket_time("2026-03-28T10:00:00+08:00")

    response = client.post("/api/v1/commands/project-init", json=_project_init_payload("Ship MVP A"))

    workflow_id = response.json()["causation_hint"].split(":", 1)[1]
    repository = client.app.state.repository
    approvals = repository.list_open_approvals()
    kickoff_ticket = repository.get_current_ticket_projection(build_project_init_scope_ticket_id(workflow_id))

    assert response.status_code == 200
    assert response.json()["status"] == "ACCEPTED"
    assert approvals == []
    assert kickoff_ticket is not None
    assert kickoff_ticket["workflow_id"] == workflow_id
    assert kickoff_ticket["status"] == TICKET_STATUS_COMPLETED


def test_project_init_force_requirement_elicitation_opens_init_review(client, set_ticket_time):
    set_ticket_time("2026-03-28T10:00:00+08:00")

    response = client.post(
        "/api/v1/commands/project-init",
        json=_project_init_payload(
            "Ship MVP A",
            force_requirement_elicitation=True,
        ),
    )

    workflow_id = response.json()["causation_hint"].split(":", 1)[1]
    repository = client.app.state.repository
    approvals = repository.list_open_approvals()
    legacy_scope_ticket = repository.get_current_ticket_projection(f"tkt_{workflow_id}_scope_decision")

    assert response.status_code == 200
    assert response.json()["status"] == "ACCEPTED"
    assert len(approvals) == 1
    assert approvals[0]["approval_type"] == "REQUIREMENT_ELICITATION"
    assert approvals[0]["payload"]["review_pack"]["meta"]["review_type"] == "REQUIREMENT_ELICITATION"
    assert approvals[0]["payload"]["review_pack"]["elicitation_questionnaire"] is not None
    assert approvals[0]["payload"]["available_actions"] == ["APPROVE", "MODIFY_CONSTRAINTS"]
    assert legacy_scope_ticket is None


def test_project_init_weak_signal_requirement_elicitation_stays_before_scope_kickoff(client, set_ticket_time):
    set_ticket_time("2026-03-28T10:00:00+08:00")

    response = client.post(
        "/api/v1/commands/project-init",
        json=_project_init_payload(
            "Ship MVP",
            budget_cap=0,
            hard_constraints=["Keep governance explicit."],
            deadline_at=None,
        ),
    )

    workflow_id = response.json()["causation_hint"].split(":", 1)[1]
    repository = client.app.state.repository
    approvals = repository.list_open_approvals()
    legacy_scope_ticket = repository.get_current_ticket_projection(f"tkt_{workflow_id}_scope_decision")

    assert response.status_code == 200
    assert response.json()["status"] == "ACCEPTED"
    assert len(approvals) == 1
    assert approvals[0]["approval_type"] == "REQUIREMENT_ELICITATION"
    assert legacy_scope_ticket is None


def test_board_approve_requirement_elicitation_generates_answers_artifact_and_starts_governance_kickoff(
    client,
    set_ticket_time,
):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    init_response = client.post(
        "/api/v1/commands/project-init",
        json=_project_init_payload("Ship MVP A", force_requirement_elicitation=True),
    )
    workflow_id = init_response.json()["causation_hint"].split(":", 1)[1]
    approval = client.app.state.repository.list_open_approvals()[0]
    option_id = approval["payload"]["review_pack"]["options"][0]["option_id"]

    response = client.post(
        "/api/v1/commands/board-approve",
        json={
            "review_pack_id": approval["review_pack_id"],
            "review_pack_version": approval["review_pack_version"],
            "command_target_version": approval["command_target_version"],
            "approval_id": approval["approval_id"],
            "selected_option_id": option_id,
            "board_comment": "Answers captured. Continue to scope kickoff.",
            "elicitation_answers": _elicitation_answers(),
            "idempotency_key": f"board-approve:{approval['approval_id']}:elicitation",
        },
    )

    repository = client.app.state.repository
    approvals = repository.list_open_approvals()
    legacy_scope_ticket = repository.get_current_ticket_projection(f"tkt_{workflow_id}_scope_decision")
    with repository.connection() as connection:
        created_rows = connection.execute(
            """
            SELECT payload_json
            FROM events
            WHERE workflow_id = ? AND event_type = ?
            ORDER BY sequence_no ASC
            """,
            (workflow_id, EVENT_TICKET_CREATED),
        ).fetchall()
    created_specs = [json.loads(row["payload_json"]) for row in created_rows]

    assert response.status_code == 200
    assert response.json()["status"] == "ACCEPTED"
    assert legacy_scope_ticket is None
    assert not any(item["approval_type"] == "MEETING_ESCALATION" for item in approvals)
    assert any(
        item["node_id"] == "node_ceo_architecture_brief" and item["output_schema_ref"] == "architecture_brief"
        for item in created_specs
    )
    with repository.connection() as connection:
        artifact_rows = connection.execute(
            "SELECT artifact_ref FROM artifact_index WHERE workflow_id = ? AND logical_path LIKE ?",
            (workflow_id, "%requirements-elicitation%"),
        ).fetchall()
    assert artifact_rows


def test_project_init_force_requirement_elicitation_autopilot_starts_governance_kickoff(
    client,
    set_ticket_time,
):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    init_response = client.post(
        "/api/v1/commands/project-init",
        json={
            **_project_init_payload("Ship MVP A", force_requirement_elicitation=True),
            "workflow_profile": "CEO_AUTOPILOT_FINE_GRAINED",
        },
    )
    workflow_id = init_response.json()["causation_hint"].split(":", 1)[1]

    repository = client.app.state.repository
    legacy_scope_ticket = repository.get_current_ticket_projection(f"tkt_{workflow_id}_scope_decision")
    with repository.connection() as connection:
        created_rows = connection.execute(
            """
            SELECT payload_json
            FROM events
            WHERE workflow_id = ? AND event_type = ?
            ORDER BY sequence_no ASC
            """,
            (workflow_id, EVENT_TICKET_CREATED),
        ).fetchall()
    created_specs = [json.loads(row["payload_json"]) for row in created_rows]

    assert init_response.status_code == 200
    assert init_response.json()["status"] == "ACCEPTED"
    assert legacy_scope_ticket is None
    assert any(
        item["node_id"] == "node_ceo_architecture_brief" and item["output_schema_ref"] == "architecture_brief"
        for item in created_specs
    )


def test_modify_constraints_requirement_elicitation_reopens_same_stage_with_saved_answers(
    client,
    set_ticket_time,
):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    init_response = client.post(
        "/api/v1/commands/project-init",
        json=_project_init_payload("Ship MVP A", force_requirement_elicitation=True),
    )
    workflow_id = init_response.json()["causation_hint"].split(":", 1)[1]
    approval = client.app.state.repository.list_open_approvals()[0]

    response = client.post(
        "/api/v1/commands/modify-constraints",
        json={
            "review_pack_id": approval["review_pack_id"],
            "review_pack_version": approval["review_pack_version"],
            "command_target_version": approval["command_target_version"],
            "approval_id": approval["approval_id"],
            "constraint_patch": {
                "add_rules": ["Need a clearer definition of what counts as MVP complete."],
                "remove_rules": [],
                "replace_rules": [],
            },
            "board_comment": "Clarify delivery boundaries before kickoff.",
            "elicitation_answers": _elicitation_answers(),
            "idempotency_key": f"modify-constraints:{approval['approval_id']}:elicitation",
        },
    )

    repository = client.app.state.repository
    approvals = repository.list_open_approvals()
    scope_ticket = repository.get_current_ticket_projection(f"tkt_{workflow_id}_scope_decision")

    assert response.status_code == 200
    assert response.json()["status"] == "ACCEPTED"
    assert len(approvals) == 1
    assert approvals[0]["approval_type"] == "REQUIREMENT_ELICITATION"
    assert approvals[0]["payload"]["draft_defaults"]["elicitation_answers"] == _elicitation_answers()
    assert scope_ticket is None


def test_board_approve_scope_review_creates_followup_ticket_and_advances_to_visual_review(
    client,
    set_ticket_time,
):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    workflow_id, approval = _project_init_to_scope_approval(client)
    followup_payload = _scope_followup_payload(client, approval)
    build_ticket_id, check_ticket_id, review_ticket_id = [
        item["ticket_id"] for item in followup_payload["followup_tickets"]
    ]
    workflow_id, final_review_approval, _ = _complete_scope_followup_chain_to_visual_milestone(
        client,
        approval,
        idempotency_suffix="scope-to-visual-review",
    )

    repository = client.app.state.repository
    open_approvals = repository.list_open_approvals()
    current_scope_approval = repository.get_approval_by_review_pack_id(approval["review_pack_id"])
    build_ticket = repository.get_current_ticket_projection(build_ticket_id)
    check_ticket = repository.get_current_ticket_projection(check_ticket_id)
    review_ticket = repository.get_current_ticket_projection(review_ticket_id)
    with repository.connection() as connection:
        build_created_spec = repository.get_latest_ticket_created_payload(
            connection,
            build_ticket_id,
        )
        check_created_spec = repository.get_latest_ticket_created_payload(
            connection,
            check_ticket_id,
        )
        review_created_spec = repository.get_latest_ticket_created_payload(
            connection,
            review_ticket_id,
        )

    assert current_scope_approval["status"] == APPROVAL_STATUS_APPROVED
    assert [item["delivery_stage"] for item in followup_payload["followup_tickets"]] == [
        "BUILD",
        "CHECK",
        "REVIEW",
    ]
    assert build_ticket is not None
    assert check_ticket is not None
    assert review_ticket is not None
    assert build_created_spec is not None
    assert check_created_spec is not None
    assert review_created_spec is not None
    assert build_created_spec["workflow_id"] == workflow_id
    assert build_created_spec["delivery_stage"] == "BUILD"
    assert build_created_spec["output_schema_ref"] == "source_code_delivery"
    assert build_created_spec["role_profile_ref"] == "frontend_engineer_primary"
    assert build_created_spec["auto_review_request"]["review_type"] == "INTERNAL_DELIVERY_REVIEW"
    assert any(ref.endswith("/board-brief.md") for ref in build_created_spec["input_artifact_refs"])
    assert any("consensus-document.json" in ref for ref in build_created_spec["input_artifact_refs"])
    assert check_created_spec["delivery_stage"] == "CHECK"
    assert check_created_spec["output_schema_ref"] == "delivery_check_report"
    assert check_created_spec["role_profile_ref"] == "checker_primary"
    assert check_created_spec["auto_review_request"]["review_type"] == "INTERNAL_CHECK_REVIEW"
    assert check_created_spec["parent_ticket_id"] == build_ticket_id
    assert review_created_spec["delivery_stage"] == "REVIEW"
    assert review_created_spec["output_schema_ref"] == "ui_milestone_review"
    assert review_created_spec["role_profile_ref"] == "frontend_engineer_primary"
    assert review_created_spec["parent_ticket_id"] == check_ticket_id
    assert f"art://runtime/{check_ticket_id}/delivery-check-report.json" in review_created_spec["input_artifact_refs"]
    assert build_ticket["status"] == TICKET_STATUS_COMPLETED
    assert check_ticket["status"] == TICKET_STATUS_COMPLETED
    assert review_ticket["status"] == TICKET_STATUS_COMPLETED
    assert final_review_approval["approval_type"] == "VISUAL_MILESTONE"
    assert any(item["approval_type"] == "VISUAL_MILESTONE" for item in open_approvals)


def test_board_approve_scope_review_creates_pending_followup_when_no_eligible_worker(
    client,
    set_ticket_time,
):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    workflow_id, approval = _project_init_to_scope_approval(client)
    followup_payload = _scope_followup_payload(client, approval)
    build_ticket_id, check_ticket_id, review_ticket_id = [
        item["ticket_id"] for item in followup_payload["followup_tickets"]
    ]

    freeze_response = client.post(
        "/api/v1/commands/employee-freeze",
        json=_employee_freeze_payload(workflow_id, employee_id="emp_frontend_2"),
    )
    response = _approve_open_review(client, approval, idempotency_suffix="pending")

    repository = client.app.state.repository
    build_ticket = repository.get_current_ticket_projection(build_ticket_id)
    check_ticket = repository.get_current_ticket_projection(check_ticket_id)
    review_ticket = repository.get_current_ticket_projection(review_ticket_id)
    open_approvals = repository.list_open_approvals()

    assert freeze_response.status_code == 200
    assert freeze_response.json()["status"] == "ACCEPTED"
    assert response.status_code == 200
    assert response.json()["status"] == "ACCEPTED"
    assert build_ticket is not None
    assert check_ticket is not None
    assert review_ticket is not None
    assert build_ticket["status"] == TICKET_STATUS_PENDING
    assert check_ticket["status"] == TICKET_STATUS_PENDING
    assert review_ticket["status"] == TICKET_STATUS_PENDING
    assert open_approvals == []


def test_board_approve_scope_review_creates_all_supported_followups_and_isolates_write_sets(
    client,
    set_ticket_time,
):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    workflow_id, approval = _project_init_to_scope_approval(client)

    consensus_artifact_ref = approval["payload"]["review_pack"]["evidence_summary"][0]["source_ref"]
    artifact_path = _artifact_storage_path(client, consensus_artifact_ref)
    payload = _scope_followup_payload(client, approval)
    payload["followup_tickets"] = _staged_scope_followup_tickets("tkt_followup_scope")
    artifact_path.write_text(json.dumps(payload), encoding="utf-8")

    response = _approve_open_review(client, approval, idempotency_suffix="all-followups")

    repository = client.app.state.repository
    build_ticket = repository.get_current_ticket_projection("tkt_followup_scope_build")
    check_ticket = repository.get_current_ticket_projection("tkt_followup_scope_check")
    review_ticket = repository.get_current_ticket_projection("tkt_followup_scope_review")
    current_scope_approval = repository.get_approval_by_review_pack_id(approval["review_pack_id"])
    open_approvals = repository.list_open_approvals()
    with repository.connection() as connection:
        build_created_spec = repository.get_latest_ticket_created_payload(
            connection,
            "tkt_followup_scope_build",
        )
        check_created_spec = repository.get_latest_ticket_created_payload(
            connection,
            "tkt_followup_scope_check",
        )
        review_created_spec = repository.get_latest_ticket_created_payload(
            connection,
            "tkt_followup_scope_review",
        )

    assert response.status_code == 200
    assert response.json()["status"] == "ACCEPTED"
    assert current_scope_approval["status"] == APPROVAL_STATUS_APPROVED
    assert build_ticket is not None
    assert check_ticket is not None
    assert review_ticket is not None
    assert build_created_spec is not None
    assert check_created_spec is not None
    assert review_created_spec is not None
    assert build_created_spec["workflow_id"] == workflow_id
    assert check_created_spec["workflow_id"] == workflow_id
    assert review_created_spec["workflow_id"] == workflow_id
    assert build_created_spec["allowed_write_set"] == [
        "10-project/src/*",
        "10-project/docs/*",
        "20-evidence/tests/*",
        "20-evidence/git/*",
    ]
    assert check_created_spec["allowed_write_set"] == [
        "reports/check/tkt_followup_scope_check/*",
    ]
    assert review_created_spec["allowed_write_set"] == [
        "artifacts/ui/scope-followups/tkt_followup_scope_review/*",
        "reports/review/tkt_followup_scope_review/*",
    ]
    assert any(
        item.endswith("Build the approved homepage foundation without widening the governance surface.")
        for item in build_created_spec["acceptance_criteria"]
    )
    assert any(
        item.endswith("Check the source code delivery against the approved scope lock.")
        for item in check_created_spec["acceptance_criteria"]
    )
    assert any(
        item.endswith("Prepare the final board-facing homepage review package from the approved implementation.")
        for item in review_created_spec["acceptance_criteria"]
    )
    assert build_created_spec["parent_ticket_id"] == "tkt_scope_review_001"
    assert check_created_spec["parent_ticket_id"] == "tkt_followup_scope_build"
    assert review_created_spec["parent_ticket_id"] == "tkt_followup_scope_check"
    assert build_created_spec["tenant_id"] == "tenant_default"
    assert build_created_spec["workspace_id"] == "ws_default"
    assert check_created_spec["tenant_id"] == "tenant_default"
    assert check_created_spec["workspace_id"] == "ws_default"
    assert review_created_spec["tenant_id"] == "tenant_default"
    assert review_created_spec["workspace_id"] == "ws_default"
    assert check_created_spec["parent_ticket_id"] == "tkt_followup_scope_build"
    assert f"art://runtime/tkt_followup_scope_check/delivery-check-report.json" in review_created_spec[
        "input_artifact_refs"
    ]
    assert any(item["approval_type"] == "VISUAL_MILESTONE" for item in open_approvals)
    assert build_ticket["status"] == TICKET_STATUS_COMPLETED
    assert check_ticket["status"] == TICKET_STATUS_COMPLETED
    assert review_ticket["status"] == TICKET_STATUS_COMPLETED


def test_scope_followups_translate_atomic_dependency_refs_into_dispatch_intent(client, set_ticket_time):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    workflow_id, approval = _project_init_to_scope_approval(client)

    consensus_artifact_ref = approval["payload"]["review_pack"]["evidence_summary"][0]["source_ref"]
    artifact_path = _artifact_storage_path(client, consensus_artifact_ref)
    payload = _scope_followup_payload(client, approval)
    payload["followup_tickets"] = [
        {
            "ticket_id": "tkt_library_books_ui",
            "task_title": "实现图书列表页骨架",
            "owner_role": "frontend_engineer",
            "summary": "只实现图书列表页骨架和静态表格布局。",
            "delivery_stage": "BUILD",
            "dependency_ticket_ids": [],
        },
        {
            "ticket_id": "tkt_library_search_ui",
            "task_title": "实现搜索框交互",
            "owner_role": "frontend_engineer",
            "summary": "只实现搜索框和筛选交互。",
            "delivery_stage": "BUILD",
            "dependency_ticket_ids": ["tkt_library_books_ui"],
        },
    ]
    artifact_path.write_text(json.dumps(payload), encoding="utf-8")

    response = _approve_open_review(client, approval, idempotency_suffix="atomic-deps")

    repository = client.app.state.repository
    with repository.connection() as connection:
        api_created_spec = repository.get_latest_ticket_created_payload(connection, "tkt_library_books_ui")
        ui_created_spec = repository.get_latest_ticket_created_payload(connection, "tkt_library_search_ui")

    assert response.status_code == 200
    assert response.json()["status"] == "ACCEPTED"
    assert api_created_spec is not None
    assert ui_created_spec is not None
    assert api_created_spec["workflow_id"] == workflow_id
    assert api_created_spec["dispatch_intent"]["assignee_employee_id"] == "emp_frontend_2"
    assert api_created_spec["dispatch_intent"]["dependency_gate_refs"] == []
    assert ui_created_spec["dispatch_intent"]["assignee_employee_id"] == "emp_frontend_2"
    assert ui_created_spec["dispatch_intent"]["dependency_gate_refs"] == ["tkt_library_books_ui"]
    assert ui_created_spec["dispatch_intent"]["selected_by"] == "scope_followup_router"
    assert ui_created_spec["dispatch_intent"]["wakeup_policy"] == "dependency_gated"


def test_internal_delivery_build_checker_approved_does_not_open_board_review(client, set_ticket_time):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    _create_lease_and_start_ticket(
        client,
        workflow_id="wf_build_internal_review",
        ticket_id="tkt_build_internal_review",
        node_id="node_build_internal_review",
        output_schema_ref="source_code_delivery",
        allowed_write_set=["artifacts/ui/scope-followups/tkt_build_internal_review/*"],
        allowed_tools=["read_artifact", "write_artifact"],
        acceptance_criteria=[
            "Must implement the approved scope follow-up.",
            "Must produce a structured source code delivery.",
        ],
        delivery_stage="BUILD",
    )

    maker_response = client.post(
        "/api/v1/commands/ticket-result-submit",
        json=_source_code_delivery_result_submit_payload(
            workflow_id="wf_build_internal_review",
            ticket_id="tkt_build_internal_review",
            node_id="node_build_internal_review",
            include_review_request=True,
        ),
    )

    repository = client.app.state.repository
    node_projection = repository.get_current_node_projection(
        "wf_build_internal_review",
        "node_build_internal_review",
    )
    assert node_projection is not None
    checker_ticket_id = node_projection["latest_ticket_id"]

    checker_lease = client.post(
        "/api/v1/commands/ticket-lease",
        json=_ticket_lease_payload(
            workflow_id="wf_build_internal_review",
            ticket_id=checker_ticket_id,
            node_id="node_build_internal_review",
            leased_by="emp_checker_1",
        ),
    )
    checker_start = client.post(
        "/api/v1/commands/ticket-start",
        json=_ticket_start_payload(
            workflow_id="wf_build_internal_review",
            ticket_id=checker_ticket_id,
            node_id="node_build_internal_review",
            started_by="emp_checker_1",
        ),
    )
    checker_result = client.post(
        "/api/v1/commands/ticket-result-submit",
        json=_maker_checker_result_submit_payload(
            workflow_id="wf_build_internal_review",
            ticket_id=checker_ticket_id,
            node_id="node_build_internal_review",
            review_status="APPROVED_WITH_NOTES",
            idempotency_key=f"ticket-result-submit:wf_build_internal_review:{checker_ticket_id}:approved",
        ),
    )

    maker_ticket = repository.get_current_ticket_projection("tkt_build_internal_review")
    current_node = repository.get_current_node_projection("wf_build_internal_review", "node_build_internal_review")

    assert maker_response.status_code == 200
    assert maker_response.json()["status"] == "ACCEPTED"
    assert checker_lease.status_code == 200
    assert checker_start.status_code == 200
    assert checker_result.status_code == 200
    assert checker_result.json()["status"] == "ACCEPTED"
    assert repository.list_open_approvals() == []
    assert repository.list_open_incidents() == []
    assert maker_ticket is not None
    assert maker_ticket["status"] == TICKET_STATUS_COMPLETED
    assert current_node is not None
    assert current_node["status"] == NODE_STATUS_COMPLETED


def test_internal_delivery_build_checker_changes_required_creates_fix_ticket_and_counts_rework_loop(
    client,
    set_ticket_time,
):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    _create_lease_and_start_ticket(
        client,
        workflow_id="wf_build_rework",
        ticket_id="tkt_build_rework",
        node_id="node_build_rework",
        output_schema_ref="source_code_delivery",
        allowed_write_set=["artifacts/ui/scope-followups/tkt_build_rework/*"],
        allowed_tools=["read_artifact", "write_artifact"],
        acceptance_criteria=[
            "Must implement the approved scope follow-up.",
            "Must produce a structured source code delivery.",
        ],
        delivery_stage="BUILD",
    )
    maker_response = client.post(
        "/api/v1/commands/ticket-result-submit",
        json=_source_code_delivery_result_submit_payload(
            workflow_id="wf_build_rework",
            ticket_id="tkt_build_rework",
            node_id="node_build_rework",
            include_review_request=True,
        ),
    )
    assert maker_response.status_code == 200
    assert maker_response.json()["status"] == "ACCEPTED"

    repository = client.app.state.repository
    checker_ticket_id = repository.get_current_node_projection("wf_build_rework", "node_build_rework")[
        "latest_ticket_id"
    ]
    client.post(
        "/api/v1/commands/ticket-lease",
        json=_ticket_lease_payload(
            workflow_id="wf_build_rework",
            ticket_id=checker_ticket_id,
            node_id="node_build_rework",
            leased_by="emp_checker_1",
        ),
    )
    client.post(
        "/api/v1/commands/ticket-start",
        json=_ticket_start_payload(
            workflow_id="wf_build_rework",
            ticket_id=checker_ticket_id,
            node_id="node_build_rework",
            started_by="emp_checker_1",
        ),
    )
    checker_result = client.post(
        "/api/v1/commands/ticket-result-submit",
        json=_maker_checker_result_submit_payload(
            workflow_id="wf_build_rework",
            ticket_id=checker_ticket_id,
            node_id="node_build_rework",
            review_status="CHANGES_REQUIRED",
            findings=[
                {
                    "finding_id": "finding_build_scope_drift",
                    "severity": "high",
                    "category": "SCOPE_DISCIPLINE",
                    "headline": "Source code delivery drifted outside the locked scope.",
                    "summary": "Build bundle still includes extra non-MVP sections.",
                    "required_action": "Trim the source code delivery back to the locked scope before downstream checks.",
                    "blocking": True,
                }
            ],
            idempotency_key=f"ticket-result-submit:wf_build_rework:{checker_ticket_id}:changes-required",
        ),
    )

    node_projection = repository.get_current_node_projection("wf_build_rework", "node_build_rework")
    assert node_projection is not None
    fix_ticket = repository.get_current_ticket_projection(node_projection["latest_ticket_id"])
    with repository.connection() as connection:
        fix_created_spec = repository.get_latest_ticket_created_payload(
            connection,
            node_projection["latest_ticket_id"],
        )
    dashboard_response = client.get("/api/v1/projections/dashboard")
    workforce_response = client.get("/api/v1/projections/workforce")

    assert checker_result.status_code == 200
    assert checker_result.json()["status"] == "ACCEPTED"
    assert fix_ticket is not None
    assert fix_ticket["status"] == TICKET_STATUS_PENDING
    assert fix_created_spec is not None
    assert fix_created_spec["output_schema_ref"] == "source_code_delivery"
    assert fix_created_spec["delivery_stage"] == "BUILD"
    assert fix_created_spec["excluded_employee_ids"] == ["emp_frontend_2"]
    assert fix_created_spec["maker_checker_context"]["original_review_request"]["review_type"] == (
        "INTERNAL_DELIVERY_REVIEW"
    )
    assert "Trim the source code delivery back to the locked scope before downstream checks." in (
        fix_created_spec["acceptance_criteria"][-1]
    )
    assert repository.list_open_approvals() == []
    assert dashboard_response.json()["data"]["workforce_summary"]["workers_in_rework_loop"] == 1
    assert workforce_response.json()["data"]["summary"]["workers_in_rework_loop"] == 1


def test_internal_delivery_build_rework_keeps_downstream_check_pending_until_fix_closes(
    client,
    set_ticket_time,
):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    _create_lease_and_start_ticket(
        client,
        workflow_id="wf_build_rework_gate",
        ticket_id="tkt_build_rework_gate",
        node_id="node_build_rework_gate",
        output_schema_ref="source_code_delivery",
        allowed_write_set=["artifacts/ui/scope-followups/tkt_build_rework_gate/*"],
        allowed_tools=["read_artifact", "write_artifact"],
        acceptance_criteria=[
            "Must implement the approved scope follow-up.",
            "Must produce a structured source code delivery.",
        ],
        delivery_stage="BUILD",
    )
    check_create = client.post(
        "/api/v1/commands/ticket-create",
        json=_ticket_create_payload(
            workflow_id="wf_build_rework_gate",
            ticket_id="tkt_build_rework_gate_check",
            node_id="node_build_rework_gate_check",
            role_profile_ref="checker_primary",
            output_schema_ref="delivery_check_report",
            allowed_tools=["read_artifact", "write_artifact"],
            allowed_write_set=["reports/check/tkt_build_rework_gate_check/*"],
            acceptance_criteria=[
                "Must check the source code delivery against the approved scope lock.",
                "Must produce a structured delivery check report.",
            ],
            input_artifact_refs=["art://runtime/tkt_build_rework_gate/source-code.tsx"],
            delivery_stage="CHECK",
            parent_ticket_id="tkt_build_rework_gate",
        ),
    )
    assert check_create.status_code == 200
    assert check_create.json()["status"] == "ACCEPTED"

    maker_response = client.post(
        "/api/v1/commands/ticket-result-submit",
        json=_source_code_delivery_result_submit_payload(
            workflow_id="wf_build_rework_gate",
            ticket_id="tkt_build_rework_gate",
            node_id="node_build_rework_gate",
            include_review_request=True,
        ),
    )
    assert maker_response.status_code == 200
    assert maker_response.json()["status"] == "ACCEPTED"

    repository = client.app.state.repository
    checker_ticket_id = repository.get_current_node_projection("wf_build_rework_gate", "node_build_rework_gate")[
        "latest_ticket_id"
    ]
    client.post(
        "/api/v1/commands/ticket-lease",
        json=_ticket_lease_payload(
            workflow_id="wf_build_rework_gate",
            ticket_id=checker_ticket_id,
            node_id="node_build_rework_gate",
            leased_by="emp_checker_1",
        ),
    )
    client.post(
        "/api/v1/commands/ticket-start",
        json=_ticket_start_payload(
            workflow_id="wf_build_rework_gate",
            ticket_id=checker_ticket_id,
            node_id="node_build_rework_gate",
            started_by="emp_checker_1",
        ),
    )
    checker_result = client.post(
        "/api/v1/commands/ticket-result-submit",
        json=_maker_checker_result_submit_payload(
            workflow_id="wf_build_rework_gate",
            ticket_id=checker_ticket_id,
            node_id="node_build_rework_gate",
            review_status="CHANGES_REQUIRED",
            findings=[
                {
                    "finding_id": "finding_build_scope_drift_gate",
                    "severity": "high",
                    "category": "SCOPE_DISCIPLINE",
                    "headline": "Source code delivery drifted outside the locked scope.",
                    "summary": "Build bundle still includes extra non-MVP sections.",
                    "required_action": "Trim the source code delivery back to the locked scope before downstream checks.",
                    "blocking": True,
                }
            ],
            idempotency_key=f"ticket-result-submit:wf_build_rework_gate:{checker_ticket_id}:changes-required",
        ),
    )
    assert checker_result.status_code == 200
    assert checker_result.json()["status"] == "ACCEPTED"

    scheduler_response = client.post(
        "/api/v1/commands/scheduler-tick",
        json=_scheduler_tick_payload(idempotency_key="scheduler-tick:build-rework-gate"),
    )

    check_ticket = repository.get_current_ticket_projection("tkt_build_rework_gate_check")

    assert scheduler_response.status_code == 200
    assert scheduler_response.json()["status"] == "ACCEPTED"
    assert check_ticket is not None
    assert check_ticket["status"] == TICKET_STATUS_PENDING
    assert check_ticket["lease_owner"] is None


def test_internal_delivery_build_fix_pass_releases_downstream_check(
    client,
    set_ticket_time,
):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    _seed_worker(client, employee_id="emp_frontend_3")
    _create_lease_and_start_ticket(
        client,
        workflow_id="wf_build_rework_resume",
        ticket_id="tkt_build_rework_resume",
        node_id="node_build_rework_resume",
        output_schema_ref="source_code_delivery",
        allowed_write_set=["artifacts/ui/scope-followups/tkt_build_rework_resume/*"],
        allowed_tools=["read_artifact", "write_artifact"],
        acceptance_criteria=[
            "Must implement the approved scope follow-up.",
            "Must produce a structured source code delivery.",
        ],
        delivery_stage="BUILD",
    )
    check_create = client.post(
        "/api/v1/commands/ticket-create",
        json=_ticket_create_payload(
            workflow_id="wf_build_rework_resume",
            ticket_id="tkt_build_rework_resume_check",
            node_id="node_build_rework_resume_check",
            role_profile_ref="checker_primary",
            output_schema_ref="delivery_check_report",
            allowed_tools=["read_artifact", "write_artifact"],
            allowed_write_set=["reports/check/tkt_build_rework_resume_check/*"],
            acceptance_criteria=[
                "Must check the source code delivery against the approved scope lock.",
                "Must produce a structured delivery check report.",
            ],
            input_artifact_refs=["art://runtime/tkt_build_rework_resume/source-code.tsx"],
            delivery_stage="CHECK",
            parent_ticket_id="tkt_build_rework_resume",
        ),
    )
    assert check_create.status_code == 200
    assert check_create.json()["status"] == "ACCEPTED"

    maker_response = client.post(
        "/api/v1/commands/ticket-result-submit",
        json=_source_code_delivery_result_submit_payload(
            workflow_id="wf_build_rework_resume",
            ticket_id="tkt_build_rework_resume",
            node_id="node_build_rework_resume",
            include_review_request=True,
        ),
    )
    assert maker_response.status_code == 200
    assert maker_response.json()["status"] == "ACCEPTED"

    repository = client.app.state.repository
    first_checker_ticket_id = repository.get_current_node_projection(
        "wf_build_rework_resume",
        "node_build_rework_resume",
    )["latest_ticket_id"]
    client.post(
        "/api/v1/commands/ticket-lease",
        json=_ticket_lease_payload(
            workflow_id="wf_build_rework_resume",
            ticket_id=first_checker_ticket_id,
            node_id="node_build_rework_resume",
            leased_by="emp_checker_1",
        ),
    )
    client.post(
        "/api/v1/commands/ticket-start",
        json=_ticket_start_payload(
            workflow_id="wf_build_rework_resume",
            ticket_id=first_checker_ticket_id,
            node_id="node_build_rework_resume",
            started_by="emp_checker_1",
        ),
    )
    first_checker_result = client.post(
        "/api/v1/commands/ticket-result-submit",
        json=_maker_checker_result_submit_payload(
            workflow_id="wf_build_rework_resume",
            ticket_id=first_checker_ticket_id,
            node_id="node_build_rework_resume",
            review_status="CHANGES_REQUIRED",
            findings=[
                {
                    "finding_id": "finding_build_scope_resume",
                    "severity": "high",
                    "category": "SCOPE_DISCIPLINE",
                    "headline": "Source code delivery drifted outside the locked scope.",
                    "summary": "Build bundle still includes extra non-MVP sections.",
                    "required_action": "Trim the source code delivery back to the locked scope before downstream checks.",
                    "blocking": True,
                }
            ],
            idempotency_key=f"ticket-result-submit:wf_build_rework_resume:{first_checker_ticket_id}:changes-required",
        ),
    )
    assert first_checker_result.status_code == 200
    assert first_checker_result.json()["status"] == "ACCEPTED"

    fix_ticket_id = repository.get_current_node_projection("wf_build_rework_resume", "node_build_rework_resume")[
        "latest_ticket_id"
    ]
    with repository.connection() as connection:
        fix_created_spec = repository.get_latest_ticket_created_payload(connection, fix_ticket_id)
    fix_lease = client.post(
        "/api/v1/commands/ticket-lease",
        json=_ticket_lease_payload(
            workflow_id="wf_build_rework_resume",
            ticket_id=fix_ticket_id,
            node_id="node_build_rework_resume",
            leased_by="emp_frontend_3",
        ),
    )
    fix_start = client.post(
        "/api/v1/commands/ticket-start",
        json=_ticket_start_payload(
            workflow_id="wf_build_rework_resume",
            ticket_id=fix_ticket_id,
            node_id="node_build_rework_resume",
            started_by="emp_frontend_3",
        ),
    )
    fix_result = client.post(
        "/api/v1/commands/ticket-result-submit",
        json=_source_code_delivery_result_submit_payload(
            workflow_id="wf_build_rework_resume",
            ticket_id=fix_ticket_id,
            node_id="node_build_rework_resume",
            submitted_by="emp_frontend_3",
            include_review_request=True,
            written_artifact_path="artifacts/ui/scope-followups/tkt_build_rework_resume/source-code.tsx",
            idempotency_key=f"ticket-result-submit:wf_build_rework_resume:{fix_ticket_id}:implementation",
        ),
    )
    assert fix_lease.status_code == 200
    assert fix_start.status_code == 200
    assert fix_result.status_code == 200
    assert fix_result.json()["status"] == "ACCEPTED"
    assert fix_created_spec["auto_review_request"]["review_type"] == "INTERNAL_DELIVERY_REVIEW"

    second_checker_ticket_id = repository.get_current_node_projection(
        "wf_build_rework_resume",
        "node_build_rework_resume",
    )["latest_ticket_id"]
    client.post(
        "/api/v1/commands/ticket-lease",
        json=_ticket_lease_payload(
            workflow_id="wf_build_rework_resume",
            ticket_id=second_checker_ticket_id,
            node_id="node_build_rework_resume",
            leased_by="emp_checker_1",
        ),
    )
    client.post(
        "/api/v1/commands/ticket-start",
        json=_ticket_start_payload(
            workflow_id="wf_build_rework_resume",
            ticket_id=second_checker_ticket_id,
            node_id="node_build_rework_resume",
            started_by="emp_checker_1",
        ),
    )
    second_checker_result = client.post(
        "/api/v1/commands/ticket-result-submit",
        json=_maker_checker_result_submit_payload(
            workflow_id="wf_build_rework_resume",
            ticket_id=second_checker_ticket_id,
            node_id="node_build_rework_resume",
            review_status="APPROVED_WITH_NOTES",
            idempotency_key=f"ticket-result-submit:wf_build_rework_resume:{second_checker_ticket_id}:approved",
        ),
    )
    assert second_checker_result.status_code == 200
    assert second_checker_result.json()["status"] == "ACCEPTED"

    scheduler_response = client.post(
        "/api/v1/commands/scheduler-tick",
        json=_scheduler_tick_payload(idempotency_key="scheduler-tick:build-rework-resume"),
    )

    check_ticket = repository.get_current_ticket_projection("tkt_build_rework_resume_check")

    assert scheduler_response.status_code == 200
    assert scheduler_response.json()["status"] == "ACCEPTED"
    assert check_ticket is not None
    assert check_ticket["status"] == TICKET_STATUS_LEASED
    assert check_ticket["lease_owner"] == "emp_checker_1"


def test_internal_delivery_build_checker_escalated_opens_incident_without_board_review(
    client,
    set_ticket_time,
):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    _create_lease_and_start_ticket(
        client,
        workflow_id="wf_build_escalation",
        ticket_id="tkt_build_escalation",
        node_id="node_build_escalation",
        output_schema_ref="source_code_delivery",
        allowed_write_set=["artifacts/ui/scope-followups/tkt_build_escalation/*"],
        allowed_tools=["read_artifact", "write_artifact"],
        acceptance_criteria=[
            "Must implement the approved scope follow-up.",
            "Must produce a structured source code delivery.",
        ],
        delivery_stage="BUILD",
    )
    maker_response = client.post(
        "/api/v1/commands/ticket-result-submit",
        json=_source_code_delivery_result_submit_payload(
            workflow_id="wf_build_escalation",
            ticket_id="tkt_build_escalation",
            node_id="node_build_escalation",
            include_review_request=True,
        ),
    )
    assert maker_response.status_code == 200
    assert maker_response.json()["status"] == "ACCEPTED"

    repository = client.app.state.repository
    checker_ticket_id = repository.get_current_node_projection("wf_build_escalation", "node_build_escalation")[
        "latest_ticket_id"
    ]
    client.post(
        "/api/v1/commands/ticket-lease",
        json=_ticket_lease_payload(
            workflow_id="wf_build_escalation",
            ticket_id=checker_ticket_id,
            node_id="node_build_escalation",
            leased_by="emp_checker_1",
        ),
    )
    client.post(
        "/api/v1/commands/ticket-start",
        json=_ticket_start_payload(
            workflow_id="wf_build_escalation",
            ticket_id=checker_ticket_id,
            node_id="node_build_escalation",
            started_by="emp_checker_1",
        ),
    )
    checker_result = client.post(
        "/api/v1/commands/ticket-result-submit",
        json=_maker_checker_result_submit_payload(
            workflow_id="wf_build_escalation",
            ticket_id=checker_ticket_id,
            node_id="node_build_escalation",
            review_status="ESCALATED",
            findings=[
                {
                    "finding_id": "finding_build_unverifiable",
                    "severity": "high",
                    "category": "DELIVERY_RISK",
                    "headline": "Checker cannot verify the bundle with current evidence.",
                    "summary": "Source code delivery needs CEO attention before downstream work continues.",
                    "required_action": "Escalate this source delivery for deeper intervention.",
                    "blocking": True,
                }
            ],
            idempotency_key=f"ticket-result-submit:wf_build_escalation:{checker_ticket_id}:escalated",
        ),
    )

    open_incidents = repository.list_open_incidents()

    assert checker_result.status_code == 200
    assert checker_result.json()["status"] == "ACCEPTED"
    assert repository.list_open_approvals() == []
    assert len(open_incidents) == 1
    assert open_incidents[0]["incident_type"] == "MAKER_CHECKER_REWORK_ESCALATION"
    assert open_incidents[0]["ticket_id"] == checker_ticket_id


def test_check_followup_result_creates_internal_checker_and_preserves_review_gate(client, set_ticket_time):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    _create_lease_and_start_ticket(
        client,
        workflow_id="wf_check_internal_review",
        ticket_id="tkt_check_internal_review",
        node_id="node_check_internal_review",
        role_profile_ref="checker_primary",
        output_schema_ref="delivery_check_report",
        allowed_write_set=["reports/check/tkt_check_internal_review/*"],
        allowed_tools=["read_artifact", "write_artifact"],
        acceptance_criteria=[
            "Must check the source code delivery against the approved scope lock.",
            "Must produce a structured delivery check report.",
        ],
        input_artifact_refs=[
            "art://runtime/tkt_check_internal_review_build/source-code.tsx",
            "art://meeting/consensus-document.json",
        ],
        delivery_stage="CHECK",
    )
    review_create = client.post(
        "/api/v1/commands/ticket-create",
        json=_ticket_create_payload(
            workflow_id="wf_check_internal_review",
            ticket_id="tkt_check_internal_review_review",
            node_id="node_check_internal_review_review",
            role_profile_ref="frontend_engineer_primary",
            output_schema_ref="ui_milestone_review",
            allowed_tools=["read_artifact", "write_artifact"],
            allowed_write_set=[
                "artifacts/ui/scope-followups/tkt_check_internal_review_review/*",
                "reports/review/tkt_check_internal_review_review/*",
            ],
            acceptance_criteria=[
                "Must prepare the final board-facing review package from the approved implementation.",
            ],
            input_artifact_refs=[
                "art://runtime/tkt_check_internal_review_build/source-code.tsx",
                "art://runtime/tkt_check_internal_review/delivery-check-report.json",
            ],
            delivery_stage="REVIEW",
            parent_ticket_id="tkt_check_internal_review",
        ),
    )
    assert review_create.status_code == 200
    assert review_create.json()["status"] == "ACCEPTED"

    maker_response = client.post(
        "/api/v1/commands/ticket-result-submit",
        json=_delivery_check_report_result_submit_payload(
            workflow_id="wf_check_internal_review",
            ticket_id="tkt_check_internal_review",
            node_id="node_check_internal_review",
            include_review_request=True,
        ),
    )

    repository = client.app.state.repository
    check_node = repository.get_current_node_projection("wf_check_internal_review", "node_check_internal_review")
    review_ticket = repository.get_current_ticket_projection("tkt_check_internal_review_review")
    with repository.connection() as connection:
        checker_created_spec = repository.get_latest_ticket_created_payload(
            connection,
            check_node["latest_ticket_id"],
        )

    assert maker_response.status_code == 200
    assert maker_response.json()["status"] == "ACCEPTED"
    assert repository.list_open_approvals() == []
    assert repository.list_open_incidents() == []
    assert check_node is not None
    assert check_node["latest_ticket_id"] != "tkt_check_internal_review"
    assert checker_created_spec["output_schema_ref"] == "maker_checker_verdict"
    assert checker_created_spec["maker_checker_context"]["original_review_request"]["review_type"] == (
        "INTERNAL_CHECK_REVIEW"
    )
    assert checker_created_spec["input_artifact_refs"] == [
        "art://runtime/tkt_check_internal_review/delivery-check-report.json",
        "art://runtime/tkt_check_internal_review_build/source-code.tsx",
        "art://meeting/consensus-document.json",
    ]
    assert review_ticket is not None
    assert review_ticket["status"] == TICKET_STATUS_PENDING
    assert review_ticket["lease_owner"] is None


def test_check_internal_checker_approved_releases_final_review_ticket(client, set_ticket_time):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    _create_lease_and_start_ticket(
        client,
        workflow_id="wf_check_release_review",
        ticket_id="tkt_check_release_review",
        node_id="node_check_release_review",
        role_profile_ref="checker_primary",
        output_schema_ref="delivery_check_report",
        allowed_write_set=["reports/check/tkt_check_release_review/*"],
        allowed_tools=["read_artifact", "write_artifact"],
        acceptance_criteria=[
            "Must check the source code delivery against the approved scope lock.",
            "Must produce a structured delivery check report.",
        ],
        input_artifact_refs=[
            "art://runtime/tkt_check_release_review_build/source-code.tsx",
            "art://meeting/consensus-document.json",
        ],
        delivery_stage="CHECK",
    )
    client.post(
        "/api/v1/commands/ticket-create",
        json=_ticket_create_payload(
            workflow_id="wf_check_release_review",
            ticket_id="tkt_check_release_review_final",
            node_id="node_check_release_review_final",
            role_profile_ref="frontend_engineer_primary",
            output_schema_ref="ui_milestone_review",
            allowed_tools=["read_artifact", "write_artifact"],
            allowed_write_set=[
                "artifacts/ui/scope-followups/tkt_check_release_review_final/*",
                "reports/review/tkt_check_release_review_final/*",
            ],
            acceptance_criteria=[
                "Must prepare the final board-facing review package from the approved implementation.",
            ],
            input_artifact_refs=[
                "art://runtime/tkt_check_release_review_build/source-code.tsx",
                "art://runtime/tkt_check_release_review/delivery-check-report.json",
            ],
            delivery_stage="REVIEW",
            parent_ticket_id="tkt_check_release_review",
        ),
    )
    maker_response = client.post(
        "/api/v1/commands/ticket-result-submit",
        json=_delivery_check_report_result_submit_payload(
            workflow_id="wf_check_release_review",
            ticket_id="tkt_check_release_review",
            node_id="node_check_release_review",
            include_review_request=True,
        ),
    )
    assert maker_response.status_code == 200

    repository = client.app.state.repository
    checker_ticket_id = repository.get_current_node_projection(
        "wf_check_release_review",
        "node_check_release_review",
    )["latest_ticket_id"]
    client.post(
        "/api/v1/commands/ticket-lease",
        json=_ticket_lease_payload(
            workflow_id="wf_check_release_review",
            ticket_id=checker_ticket_id,
            node_id="node_check_release_review",
            leased_by="emp_checker_1",
        ),
    )
    client.post(
        "/api/v1/commands/ticket-start",
        json=_ticket_start_payload(
            workflow_id="wf_check_release_review",
            ticket_id=checker_ticket_id,
            node_id="node_check_release_review",
            started_by="emp_checker_1",
        ),
    )
    checker_result = client.post(
        "/api/v1/commands/ticket-result-submit",
        json=_maker_checker_result_submit_payload(
            workflow_id="wf_check_release_review",
            ticket_id=checker_ticket_id,
            node_id="node_check_release_review",
            review_status="APPROVED_WITH_NOTES",
            idempotency_key=f"ticket-result-submit:wf_check_release_review:{checker_ticket_id}:approved",
        ),
    )
    scheduler_response = client.post(
        "/api/v1/commands/scheduler-tick",
        json=_scheduler_tick_payload(idempotency_key="scheduler-tick:check-release-review"),
    )

    review_ticket = repository.get_current_ticket_projection("tkt_check_release_review_final")

    assert checker_result.status_code == 200
    assert checker_result.json()["status"] == "ACCEPTED"
    assert scheduler_response.status_code == 200
    assert scheduler_response.json()["status"] == "ACCEPTED"
    assert review_ticket is not None
    assert review_ticket["status"] == TICKET_STATUS_LEASED
    assert review_ticket["lease_owner"] == "emp_frontend_2"


def test_review_evidence_missing_required_hook_keeps_dependency_gate_blocked(client, set_ticket_time):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    workflow_response = client.post(
        "/api/v1/commands/project-init",
        json=_project_init_payload("Review evidence hook gaps must block downstream follow-up tickets."),
    )
    workflow_id = workflow_response.json()["causation_hint"].split(":", 1)[1]
    _create_lease_and_start_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_check_gate_block",
        node_id="node_check_gate_block",
        role_profile_ref="checker_primary",
        output_schema_ref="delivery_check_report",
        allowed_write_set=["reports/check/tkt_check_gate_block/*"],
        allowed_tools=["read_artifact", "write_artifact"],
        acceptance_criteria=[
            "Must check the source code delivery against the approved scope lock.",
            "Must produce a structured delivery check report.",
        ],
        input_artifact_refs=[
            "art://runtime/tkt_check_gate_block_build/source-code.tsx",
            "art://meeting/consensus-document.json",
        ],
        delivery_stage="CHECK",
    )
    followup_create = client.post(
        "/api/v1/commands/ticket-create",
        json=_ticket_create_payload(
            workflow_id=workflow_id,
            ticket_id="tkt_review_waits_for_hook",
            node_id="node_review_waits_for_hook",
            role_profile_ref="frontend_engineer_primary",
            output_schema_ref="ui_milestone_review",
            allowed_tools=["read_artifact", "write_artifact"],
            allowed_write_set=[
                "artifacts/ui/scope-followups/tkt_review_waits_for_hook/*",
                "reports/review/tkt_review_waits_for_hook/*",
            ],
            acceptance_criteria=[
                "Must prepare the final board-facing review package from the approved implementation.",
            ],
            input_artifact_refs=[
                "art://runtime/tkt_check_gate_block_build/source-code.tsx",
                "art://runtime/tkt_check_gate_block/delivery-check-report.json",
            ],
            delivery_stage="REVIEW",
            dispatch_intent={
                "assignee_employee_id": "emp_frontend_2",
                "selection_reason": "Downstream review should wait for the upstream delivery check hook gate.",
                "dependency_gate_refs": ["tkt_check_gate_block"],
                "selected_by": "test",
                "wakeup_policy": "default",
            },
        ),
    )
    assert followup_create.status_code == 200
    assert followup_create.json()["status"] == "ACCEPTED"

    maker_response = client.post(
        "/api/v1/commands/ticket-result-submit",
        json=_delivery_check_report_result_submit_payload(
            workflow_id=workflow_id,
            ticket_id="tkt_check_gate_block",
            node_id="node_check_gate_block",
        ),
    )
    assert maker_response.status_code == 200

    artifact_capture_path = (
        get_settings().project_workspace_root
        / workflow_id
        / "00-boardroom"
        / "tickets"
        / "tkt_check_gate_block"
        / "hook-receipts"
        / "artifact-capture.json"
    )
    artifact_capture_path.unlink()

    scheduler_response = client.post(
        "/api/v1/commands/scheduler-tick",
        json=_scheduler_tick_payload(idempotency_key="scheduler-tick:review-evidence-hook-gate"),
    )
    repository = client.app.state.repository
    followup_ticket = repository.get_current_ticket_projection("tkt_review_waits_for_hook")

    assert scheduler_response.status_code == 200
    assert scheduler_response.json()["status"] == "ACCEPTED"
    assert followup_ticket is not None
    assert followup_ticket["status"] == TICKET_STATUS_PENDING
    assert followup_ticket["lease_owner"] is None


def test_check_internal_checker_changes_required_creates_fix_ticket_and_counts_rework_loop(
    client,
    set_ticket_time,
):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    _create_lease_and_start_ticket(
        client,
        workflow_id="wf_check_rework",
        ticket_id="tkt_check_rework",
        node_id="node_check_rework",
        role_profile_ref="checker_primary",
        output_schema_ref="delivery_check_report",
        allowed_write_set=["reports/check/tkt_check_rework/*"],
        allowed_tools=["read_artifact", "write_artifact"],
        acceptance_criteria=[
            "Must check the source code delivery against the approved scope lock.",
            "Must produce a structured delivery check report.",
        ],
        input_artifact_refs=[
            "art://runtime/tkt_check_rework_build/source-code.tsx",
            "art://meeting/consensus-document.json",
        ],
        delivery_stage="CHECK",
    )
    client.post(
        "/api/v1/commands/ticket-create",
        json=_ticket_create_payload(
            workflow_id="wf_check_rework",
            ticket_id="tkt_check_rework_final",
            node_id="node_check_rework_final",
            role_profile_ref="frontend_engineer_primary",
            output_schema_ref="ui_milestone_review",
            allowed_tools=["read_artifact", "write_artifact"],
            allowed_write_set=[
                "artifacts/ui/scope-followups/tkt_check_rework_final/*",
                "reports/review/tkt_check_rework_final/*",
            ],
            acceptance_criteria=[
                "Must prepare the final board-facing review package from the approved implementation.",
            ],
            input_artifact_refs=[
                "art://runtime/tkt_check_rework_build/source-code.tsx",
                "art://runtime/tkt_check_rework/delivery-check-report.json",
            ],
            delivery_stage="REVIEW",
            parent_ticket_id="tkt_check_rework",
        ),
    )
    client.post(
        "/api/v1/commands/ticket-result-submit",
        json=_delivery_check_report_result_submit_payload(
            workflow_id="wf_check_rework",
            ticket_id="tkt_check_rework",
            node_id="node_check_rework",
            include_review_request=True,
        ),
    )

    repository = client.app.state.repository
    checker_ticket_id = repository.get_current_node_projection("wf_check_rework", "node_check_rework")[
        "latest_ticket_id"
    ]
    client.post(
        "/api/v1/commands/ticket-lease",
        json=_ticket_lease_payload(
            workflow_id="wf_check_rework",
            ticket_id=checker_ticket_id,
            node_id="node_check_rework",
            leased_by="emp_checker_1",
        ),
    )
    client.post(
        "/api/v1/commands/ticket-start",
        json=_ticket_start_payload(
            workflow_id="wf_check_rework",
            ticket_id=checker_ticket_id,
            node_id="node_check_rework",
            started_by="emp_checker_1",
        ),
    )
    checker_result = client.post(
        "/api/v1/commands/ticket-result-submit",
        json=_maker_checker_result_submit_payload(
            workflow_id="wf_check_rework",
            ticket_id=checker_ticket_id,
            node_id="node_check_rework",
            review_status="CHANGES_REQUIRED",
            findings=[
                {
                    "finding_id": "finding_check_scope_drift",
                    "severity": "high",
                    "category": "SCOPE_DISCIPLINE",
                    "headline": "Delivery check report did not justify scope compliance.",
                    "summary": "Check report needs a clearer justification for the implementation staying in scope.",
                    "required_action": "Rewrite the delivery check report with grounded evidence from the source code delivery.",
                    "blocking": True,
                }
            ],
            idempotency_key=f"ticket-result-submit:wf_check_rework:{checker_ticket_id}:changes-required",
        ),
    )

    node_projection = repository.get_current_node_projection("wf_check_rework", "node_check_rework")
    fix_ticket = repository.get_current_ticket_projection(node_projection["latest_ticket_id"])
    with repository.connection() as connection:
        fix_created_spec = repository.get_latest_ticket_created_payload(
            connection,
            node_projection["latest_ticket_id"],
        )
    dashboard_response = client.get("/api/v1/projections/dashboard")
    workforce_response = client.get("/api/v1/projections/workforce")

    assert checker_result.status_code == 200
    assert checker_result.json()["status"] == "ACCEPTED"
    assert fix_ticket is not None
    assert fix_ticket["status"] == TICKET_STATUS_PENDING
    assert fix_created_spec is not None
    assert fix_created_spec["output_schema_ref"] == "delivery_check_report"
    assert fix_created_spec["delivery_stage"] == "CHECK"
    assert fix_created_spec["excluded_employee_ids"] == ["emp_checker_1"]
    assert fix_created_spec["maker_checker_context"]["original_review_request"]["review_type"] == (
        "INTERNAL_CHECK_REVIEW"
    )
    assert dashboard_response.json()["data"]["workforce_summary"]["workers_in_rework_loop"] == 1
    assert workforce_response.json()["data"]["summary"]["workers_in_rework_loop"] == 1


def test_check_internal_checker_escalated_opens_incident_and_marks_dependency_stop(client, set_ticket_time):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    workflow_response = client.post(
        "/api/v1/commands/project-init",
        json=_project_init_payload("Keep dependency inspector grounded in the real CHECK incident path."),
    )
    workflow_id = workflow_response.json()["causation_hint"].split(":", 1)[1]
    _create_lease_and_start_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_check_escalation",
        node_id="node_check_escalation",
        role_profile_ref="checker_primary",
        output_schema_ref="delivery_check_report",
        allowed_write_set=["reports/check/tkt_check_escalation/*"],
        allowed_tools=["read_artifact", "write_artifact"],
        acceptance_criteria=[
            "Must check the source code delivery against the approved scope lock.",
            "Must produce a structured delivery check report.",
        ],
        input_artifact_refs=[
            "art://runtime/tkt_check_escalation_build/source-code.tsx",
            "art://meeting/consensus-document.json",
        ],
        delivery_stage="CHECK",
    )
    client.post(
        "/api/v1/commands/ticket-create",
        json=_ticket_create_payload(
            workflow_id=workflow_id,
            ticket_id="tkt_check_escalation_final",
            node_id="node_check_escalation_final",
            role_profile_ref="frontend_engineer_primary",
            output_schema_ref="ui_milestone_review",
            allowed_tools=["read_artifact", "write_artifact"],
            allowed_write_set=[
                "artifacts/ui/scope-followups/tkt_check_escalation_final/*",
                "reports/review/tkt_check_escalation_final/*",
            ],
            acceptance_criteria=[
                "Must prepare the final board-facing review package from the approved implementation.",
            ],
            input_artifact_refs=[
                "art://runtime/tkt_check_escalation_build/source-code.tsx",
                "art://runtime/tkt_check_escalation/delivery-check-report.json",
            ],
            delivery_stage="REVIEW",
            parent_ticket_id="tkt_check_escalation",
        ),
    )
    client.post(
        "/api/v1/commands/ticket-result-submit",
        json=_delivery_check_report_result_submit_payload(
            workflow_id=workflow_id,
            ticket_id="tkt_check_escalation",
            node_id="node_check_escalation",
            include_review_request=True,
        ),
    )

    repository = client.app.state.repository
    checker_ticket_id = repository.get_current_node_projection(workflow_id, "node_check_escalation")[
        "latest_ticket_id"
    ]
    client.post(
        "/api/v1/commands/ticket-lease",
        json=_ticket_lease_payload(
            workflow_id=workflow_id,
            ticket_id=checker_ticket_id,
            node_id="node_check_escalation",
            leased_by="emp_checker_1",
        ),
    )
    client.post(
        "/api/v1/commands/ticket-start",
        json=_ticket_start_payload(
            workflow_id=workflow_id,
            ticket_id=checker_ticket_id,
            node_id="node_check_escalation",
            started_by="emp_checker_1",
        ),
    )
    checker_result = client.post(
        "/api/v1/commands/ticket-result-submit",
        json=_maker_checker_result_submit_payload(
            workflow_id=workflow_id,
            ticket_id=checker_ticket_id,
            node_id="node_check_escalation",
            review_status="ESCALATED",
            findings=[
                {
                    "finding_id": "finding_check_unverifiable",
                    "severity": "high",
                    "category": "DELIVERY_RISK",
                    "headline": "Checker cannot verify the report against the bundle.",
                    "summary": "Delivery check evidence is not strong enough to start final review.",
                    "required_action": "Escalate the delivery check report for deeper intervention.",
                    "blocking": True,
                }
            ],
            idempotency_key=f"ticket-result-submit:{workflow_id}:{checker_ticket_id}:escalated",
        ),
    )
    inspector_response = client.get(
        f"/api/v1/projections/workflows/{workflow_id}/dependency-inspector"
    )

    incidents = repository.list_open_incidents()
    check_open_approvals = [
        approval
        for approval in repository.list_open_approvals()
        if (((approval.get("payload") or {}).get("review_pack") or {}).get("subject") or {}).get("source_node_id")
        == "node_check_escalation"
    ]

    assert checker_result.status_code == 200
    assert checker_result.json()["status"] == "ACCEPTED"
    assert check_open_approvals == []
    assert len(incidents) == 1
    assert incidents[0]["incident_type"] == "MAKER_CHECKER_REWORK_ESCALATION"
    assert incidents[0]["ticket_id"] == checker_ticket_id
    assert inspector_response.status_code == 200
    assert inspector_response.json()["data"]["summary"]["current_stop"]["reason"] == "INCIDENT_OPEN"


def test_board_approve_scope_review_rejects_unsupported_followup_delivery_stage(client, set_ticket_time):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    _, approval = _project_init_to_scope_approval(client)

    consensus_artifact_ref = approval["payload"]["review_pack"]["evidence_summary"][0]["source_ref"]
    artifact_path = _artifact_storage_path(client, consensus_artifact_ref)
    payload = _scope_followup_payload(client, approval)
    payload["followup_tickets"][0]["delivery_stage"] = "LAUNCH"
    artifact_path.write_text(json.dumps(payload), encoding="utf-8")

    response = _approve_open_review(client, approval, idempotency_suffix="invalid-stage")

    repository = client.app.state.repository
    updated = repository.get_approval_by_review_pack_id(approval["review_pack_id"])

    assert response.status_code == 200
    assert response.json()["status"] == "REJECTED"
    assert "delivery_stage" in response.json()["reason"]
    assert updated["status"] == APPROVAL_STATUS_OPEN


def test_board_approve_visual_review_auto_advances_next_pending_followup_to_next_review(
    client,
    set_ticket_time,
):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    _, approval = _project_init_to_scope_approval(client)

    consensus_artifact_ref = approval["payload"]["review_pack"]["evidence_summary"][0]["source_ref"]
    artifact_path = _artifact_storage_path(client, consensus_artifact_ref)
    payload = _scope_followup_payload(client, approval)
    payload["followup_tickets"] = [
        {
            "ticket_id": "tkt_followup_scope_foundation",
            "task_title": "完成首页基础评审包",
            "owner_role": "frontend_engineer",
            "summary": "Build the approved homepage foundation under the locked scope.",
            "delivery_stage": "REVIEW",
            "dependency_ticket_ids": [],
        },
        {
            "ticket_id": "tkt_followup_scope_polish",
            "task_title": "完成首页细节润色评审包",
            "owner_role": "frontend_engineer",
            "summary": "Polish the approved homepage details without widening the scope.",
            "delivery_stage": "REVIEW",
            "dependency_ticket_ids": ["tkt_followup_scope_foundation"],
        },
    ]
    artifact_path.write_text(json.dumps(payload), encoding="utf-8")

    approve_scope_response = _approve_open_review(client, approval, idempotency_suffix="approve-visual-chain")

    repository = client.app.state.repository
    first_visual_approval = next(
        item for item in repository.list_open_approvals() if item["workflow_id"] == approval["workflow_id"]
    )

    approve_first_visual_response = _approve_open_review(
        client,
        first_visual_approval,
        idempotency_suffix="approve-foundation-visual",
    )

    open_approvals = [
        item for item in repository.list_open_approvals() if item["workflow_id"] == approval["workflow_id"]
    ]
    second_ticket = repository.get_current_ticket_projection("tkt_followup_scope_polish")

    assert approve_scope_response.status_code == 200
    assert approve_scope_response.json()["status"] == "ACCEPTED"
    assert approve_first_visual_response.status_code == 200
    assert approve_first_visual_response.json()["status"] == "ACCEPTED"
    assert second_ticket is not None
    assert second_ticket["status"] == TICKET_STATUS_COMPLETED
    assert len(open_approvals) == 1
    assert open_approvals[0]["approval_type"] == "VISUAL_MILESTONE"
    assert open_approvals[0]["approval_id"] != first_visual_approval["approval_id"]


def test_board_approve_visual_review_keeps_next_followup_pending_when_no_eligible_worker(
    client,
    set_ticket_time,
):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    workflow_id, approval = _project_init_to_scope_approval(client)

    consensus_artifact_ref = approval["payload"]["review_pack"]["evidence_summary"][0]["source_ref"]
    artifact_path = _artifact_storage_path(client, consensus_artifact_ref)
    payload = _scope_followup_payload(client, approval)
    payload["followup_tickets"] = [
        {
            "ticket_id": "tkt_followup_scope_foundation",
            "task_title": "完成首页基础评审包",
            "owner_role": "frontend_engineer",
            "summary": "Build the approved homepage foundation under the locked scope.",
            "delivery_stage": "REVIEW",
            "dependency_ticket_ids": [],
        },
        {
            "ticket_id": "tkt_followup_scope_polish",
            "task_title": "完成首页细节润色评审包",
            "owner_role": "frontend_engineer",
            "summary": "Polish the approved homepage details without widening the scope.",
            "delivery_stage": "REVIEW",
            "dependency_ticket_ids": ["tkt_followup_scope_foundation"],
        },
    ]
    artifact_path.write_text(json.dumps(payload), encoding="utf-8")

    approve_scope_response = _approve_open_review(client, approval, idempotency_suffix="approve-visual-pending")

    repository = client.app.state.repository
    first_visual_approval = next(
        item for item in repository.list_open_approvals() if item["workflow_id"] == workflow_id
    )

    freeze_response = client.post(
        "/api/v1/commands/employee-freeze",
        json=_employee_freeze_payload(workflow_id, employee_id="emp_frontend_2"),
    )
    approve_first_visual_response = _approve_open_review(
        client,
        first_visual_approval,
        idempotency_suffix="approve-foundation-visual-pending",
    )

    open_approvals = [item for item in repository.list_open_approvals() if item["workflow_id"] == workflow_id]
    second_ticket = repository.get_current_ticket_projection("tkt_followup_scope_polish")

    assert approve_scope_response.status_code == 200
    assert approve_scope_response.json()["status"] == "ACCEPTED"
    assert freeze_response.status_code == 200
    assert freeze_response.json()["status"] == "ACCEPTED"
    assert approve_first_visual_response.status_code == 200
    assert approve_first_visual_response.json()["status"] == "ACCEPTED"
    assert second_ticket is not None
    assert second_ticket["status"] == TICKET_STATUS_PENDING
    assert all(
        item["payload"]["review_pack"]["subject"]["source_ticket_id"] != "tkt_followup_scope_polish"
        for item in open_approvals
    )


def test_board_approve_scope_review_rejects_when_any_followup_owner_role_is_unsupported(
    client,
    set_ticket_time,
):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    _, approval = _project_init_to_scope_approval(client)

    consensus_artifact_ref = approval["payload"]["review_pack"]["evidence_summary"][0]["source_ref"]
    artifact_path = _artifact_storage_path(client, consensus_artifact_ref)
    payload = _scope_followup_payload(client, approval)
    payload["followup_tickets"] = [
        {
            "ticket_id": "tkt_followup_scope_valid",
            "task_title": "实现有效的已批准范围任务",
            "owner_role": "frontend_engineer",
            "summary": "Implement the approved scope without expanding governance.",
            "dependency_ticket_ids": [],
        },
        {
            "ticket_id": "tkt_followup_scope_invalid",
            "task_title": "触发非法角色校验",
            "owner_role": "governance_architect",
            "summary": "This follow-up should be rejected for the current MVP lane.",
            "dependency_ticket_ids": [],
        },
    ]
    artifact_path.write_text(json.dumps(payload), encoding="utf-8")

    response = _approve_open_review(client, approval, idempotency_suffix="mixed-role")

    repository = client.app.state.repository
    updated = repository.get_approval_by_review_pack_id(approval["review_pack_id"])

    assert response.status_code == 200
    assert response.json()["status"] == "REJECTED"
    assert "owner_role" in response.json()["reason"]
    assert updated["status"] == APPROVAL_STATUS_OPEN
    assert repository.get_current_ticket_projection("tkt_followup_scope_valid") is None
    assert repository.get_current_ticket_projection("tkt_followup_scope_invalid") is None


def test_board_approve_scope_review_rejects_when_followup_ticket_ids_repeat_within_payload(
    client,
    set_ticket_time,
):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    _, approval = _project_init_to_scope_approval(client)

    consensus_artifact_ref = approval["payload"]["review_pack"]["evidence_summary"][0]["source_ref"]
    artifact_path = _artifact_storage_path(client, consensus_artifact_ref)
    payload = _scope_followup_payload(client, approval)
    payload["followup_tickets"] = [
        {
            "ticket_id": "tkt_followup_scope_duplicate",
            "task_title": "第一次使用重复 ticket id",
            "owner_role": "frontend_engineer",
            "summary": "First follow-up uses the duplicate ticket id.",
            "dependency_ticket_ids": [],
        },
        {
            "ticket_id": "tkt_followup_scope_duplicate",
            "task_title": "第二次使用重复 ticket id",
            "owner_role": "frontend_engineer",
            "summary": "Second follow-up repeats the same ticket id.",
            "dependency_ticket_ids": [],
        },
    ]
    artifact_path.write_text(json.dumps(payload), encoding="utf-8")

    response = _approve_open_review(client, approval, idempotency_suffix="duplicate-inside-payload")

    repository = client.app.state.repository
    updated = repository.get_approval_by_review_pack_id(approval["review_pack_id"])

    assert response.status_code == 200
    assert response.json()["status"] == "REJECTED"
    assert "duplicate" in response.json()["reason"].lower()
    assert updated["status"] == APPROVAL_STATUS_OPEN
    assert repository.get_current_ticket_projection("tkt_followup_scope_duplicate") is None


def test_duplicate_project_init_does_not_duplicate_first_scope_review(client, set_ticket_time):
    set_ticket_time("2026-03-28T10:00:00+08:00")

    first = client.post("/api/v1/commands/project-init", json=_project_init_payload("Ship MVP A"))
    duplicate = client.post("/api/v1/commands/project-init", json=_project_init_payload("Ship MVP A"))

    workflow_id = first.json()["causation_hint"].split(":", 1)[1]
    repository = client.app.state.repository
    approvals = [approval for approval in repository.list_open_approvals() if approval["workflow_id"] == workflow_id]
    created_events = [
        event
        for event in repository.list_events_for_testing()
        if event["workflow_id"] == workflow_id and event["event_type"] == EVENT_TICKET_CREATED
    ]

    assert duplicate.status_code == 200
    assert duplicate.json()["status"] == "DUPLICATE"
    assert duplicate.json()["causation_hint"] == f"workflow:{workflow_id}"
    assert approvals == []
    assert len(created_events) == 1


def test_project_init_stops_auto_advance_when_no_worker_is_available(client, monkeypatch, set_ticket_time):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    monkeypatch.setattr(
        client.app.state.repository,
        "list_scheduler_worker_candidates",
        lambda connection=None: [],
    )

    response = client.post("/api/v1/commands/project-init", json=_project_init_payload("Ship MVP A"))

    workflow_id = response.json()["causation_hint"].split(":", 1)[1]
    repository = client.app.state.repository
    ticket_projection = repository.get_current_ticket_projection(build_project_init_scope_ticket_id(workflow_id))
    approvals = [approval for approval in repository.list_open_approvals() if approval["workflow_id"] == workflow_id]
    incidents = [incident for incident in repository.list_open_incidents() if incident["workflow_id"] == workflow_id]

    assert response.status_code == 200
    assert response.json()["status"] == "ACCEPTED"
    assert ticket_projection is None
    assert approvals == []
    assert incidents == []


def test_project_init_exposes_board_directive_ceo_shadow_run(client):
    response = client.post("/api/v1/commands/project-init", json=_project_init_payload("Ship MVP A"))
    workflow_id = response.json()["causation_hint"].split(":", 1)[1]

    projection_response = client.get(f"/api/v1/projections/workflows/{workflow_id}/ceo-shadow")

    assert projection_response.status_code == 200
    runs = projection_response.json()["data"]["runs"]
    assert any(run["trigger_type"] == EVENT_BOARD_DIRECTIVE_RECEIVED for run in runs)


def test_project_init_persists_default_governance_profile(client):
    response = client.post("/api/v1/commands/project-init", json=_project_init_payload("Ship governed MVP"))
    workflow_id = response.json()["causation_hint"].split(":", 1)[1]

    profile = client.app.state.repository.get_latest_governance_profile(workflow_id)

    assert profile is not None
    assert profile["approval_mode"] == "AUTO_CEO"
    assert profile["audit_mode"] == "MINIMAL"
    assert profile["auto_approval_scope"] == ["scope:mainline_internal"]
    assert profile["expert_review_targets"] == ["checker", "board"]
    assert profile["audit_materialization_policy"] == {
        "ticket_context_archive": False,
        "full_timeline": False,
        "closeout_evidence": True,
    }


def test_project_init_ignores_legacy_scope_fields_and_uses_default_scope(client):
    response = client.post(
        "/api/v1/commands/project-init",
        json={
            **_project_init_payload("Ship scoped MVP"),
            "tenant_id": "tenant_blue",
            "workspace_id": "ws_design",
        },
    )
    workflow_id = response.json()["causation_hint"].split(":", 1)[1]

    workflow = client.app.state.repository.get_workflow_projection(workflow_id)

    assert response.status_code == 200
    assert response.json()["status"] == "ACCEPTED"
    assert workflow is not None
    assert workflow["tenant_id"] == "tenant_default"
    assert workflow["workspace_id"] == "ws_default"


def test_ticket_create_ignores_legacy_scope_fields_and_uses_workflow_scope(client):
    workflow_response = client.post(
        "/api/v1/commands/project-init",
        json=_project_init_payload("Ship scoped MVP"),
    )
    workflow_id = workflow_response.json()["causation_hint"].split(":", 1)[1]

    create_response = client.post(
        "/api/v1/commands/ticket-create",
        json=_ticket_create_payload(
            workflow_id=workflow_id,
            ticket_id="tkt_scoped_ticket",
            node_id="node_scoped_ticket",
            tenant_id="tenant_blue",
            workspace_id="ws_design",
        ),
    )

    ticket_projection = client.app.state.repository.get_current_ticket_projection("tkt_scoped_ticket")

    assert create_response.status_code == 200
    assert create_response.json()["status"] == "ACCEPTED"
    assert ticket_projection["tenant_id"] == "tenant_default"
    assert ticket_projection["workspace_id"] == "ws_default"


def test_dashboard_returns_latest_active_workflow(client):
    client.post("/api/v1/commands/project-init", json=_project_init_payload("Ship MVP A", budget_cap=500000))
    client.post("/api/v1/commands/project-init", json=_project_init_payload("Ship MVP B", budget_cap=750000))

    response = client.get("/api/v1/projections/dashboard")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["active_workflow"]["north_star_goal"] == "Ship MVP B"
    assert data["ops_strip"]["budget_total"] == 750000
    assert isinstance(data["pipeline_summary"]["phases"], list)


def test_runtime_provider_projection_round_trips_masked_config_and_dashboard_runtime_status(
    db_path,
    monkeypatch,
):
    config_path = db_path.parent / "runtime-provider-config.json"
    monkeypatch.setenv("BOARDROOM_OS_RUNTIME_PROVIDER_CONFIG_PATH", str(config_path))

    from app.main import create_app

    with TestClient(create_app()) as client:
        _seed_worker(
            client,
            employee_id="emp_frontend_runtime_status",
            provider_id="prov_openai_compat",
        )
        command_response = client.post(
            "/api/v1/commands/runtime-provider-upsert",
            json=_runtime_provider_upsert_payload(),
        )
        projection_response = client.get("/api/v1/projections/runtime-provider")
        dashboard_response = client.get("/api/v1/projections/dashboard")

        assert command_response.status_code == 200
        assert command_response.json()["status"] == "ACCEPTED"
        assert projection_response.status_code == 200
        assert dashboard_response.status_code == 200

        projection_data = projection_response.json()["data"]
        dashboard_data = dashboard_response.json()["data"]

        assert projection_data["mode"] == "OPENAI_RESPONSES_STREAM"
        assert projection_data["effective_mode"] == "OPENAI_RESPONSES_STREAM_LIVE"
        assert projection_data["provider_health_summary"] == "HEALTHY"
        assert projection_data["fallback_blocked"] is True
        assert projection_data["provider_candidate_chain"] == ["prov_openai_compat"]
        assert projection_data["provider_id"] == "prov_openai_compat"
        assert projection_data["base_url"] == "https://api.example.test/v1"
        assert projection_data["alias"] == "example"
        assert projection_data["model"] == "gpt-5.3-codex"
        assert projection_data["max_context_window"] == 1000000
        assert projection_data["timeout_sec"] == 120.0
        assert projection_data["reasoning_effort"] == "high"
        assert projection_data["default_provider_id"] == "prov_openai_compat"
        assert projection_data["api_key_configured"] is True
        assert projection_data["api_key_masked"] != "sk-test-secret"
        assert "secret" not in projection_data["api_key_masked"]
        assert projection_data["configured_worker_count"] >= 1
        assert len(projection_data["providers"]) == 1
        assert projection_data["providers"][0]["provider_id"] == "prov_openai_compat"
        assert projection_data["providers"][0]["alias"] == "example"
        assert projection_data["providers"][0]["type"] == "openai_responses_stream"
        assert projection_data["providers"][0]["max_context_window"] == 1000000
        assert projection_data["providers"][0]["reasoning_effort"] == "high"
        assert projection_data["providers"][0]["cost_tier"] == "standard"
        assert projection_data["providers"][0]["participation_policy"] == "always_allowed"
        assert projection_data["providers"][0]["fallback_provider_ids"] == []
        assert projection_data["providers"][0]["health_status"] == "HEALTHY"
        assert "ready with streaming Responses" in projection_data["providers"][0]["health_reason"]
        assert projection_data["provider_model_entries"] == [
            {
                "entry_ref": "prov_openai_compat::gpt-5.3-codex",
                "provider_id": "prov_openai_compat",
                "provider_label": "example",
                "model_name": "gpt-5.3-codex",
                "max_context_window": 1000000,
            }
        ]
        assert projection_data["future_binding_slots"] == []
        assert dashboard_data["runtime_status"]["effective_mode"] == "OPENAI_RESPONSES_STREAM_LIVE"
        assert dashboard_data["runtime_status"]["provider_health_summary"] == "HEALTHY"
        assert dashboard_data["runtime_status"]["provider_label"] == "example"
        assert dashboard_data["runtime_status"]["model"] == "gpt-5.3-codex"
        assert dashboard_data["runtime_status"]["configured_worker_count"] >= 1

        switch_response = client.post(
            "/api/v1/commands/runtime-provider-upsert",
                json=_runtime_provider_upsert_payload(
                    openai_enabled=False,
                    openai_base_url="https://api.example.test/v1",
                    openai_api_key="sk-disabled",
                    openai_model=None,
                    role_bindings=[],
                idempotency_key="runtime-provider-upsert:deterministic",
            ),
        )
        switched_projection = client.get("/api/v1/projections/runtime-provider")
        switched_dashboard = client.get("/api/v1/projections/dashboard")

        assert switch_response.status_code == 200
        assert switch_response.json()["status"] == "ACCEPTED"
        assert switched_projection.json()["data"]["mode"] == "PROVIDER_REQUIRED"
        assert switched_projection.json()["data"]["effective_mode"] == "PROVIDER_REQUIRED_UNAVAILABLE"
        assert switched_projection.json()["data"]["provider_health_summary"] == "UNAVAILABLE"
        assert switched_projection.json()["data"]["fallback_blocked"] is True
        assert switched_projection.json()["data"]["provider_candidate_chain"] == []
        assert switched_projection.json()["data"]["default_provider_id"] is None
        assert switched_dashboard.json()["data"]["runtime_status"]["effective_mode"] == (
            "PROVIDER_REQUIRED_UNAVAILABLE"
        )
        assert switched_dashboard.json()["data"]["runtime_status"]["provider_health_summary"] == "UNAVAILABLE"


def test_runtime_provider_upsert_preserves_existing_openai_api_key_when_update_omits_key(
    db_path,
    monkeypatch,
):
    config_path = db_path.parent / "runtime-provider-config-preserve-key.json"
    monkeypatch.setenv("BOARDROOM_OS_RUNTIME_PROVIDER_CONFIG_PATH", str(config_path))

    from app.main import create_app

    with TestClient(create_app()) as client:
        first_response = client.post(
            "/api/v1/commands/runtime-provider-upsert",
            json=_runtime_provider_upsert_payload(
                idempotency_key="runtime-provider-upsert:preserve-key:first",
            ),
        )
        assert first_response.status_code == 200
        assert first_response.json()["status"] == "ACCEPTED"

        second_response = client.post(
            "/api/v1/commands/runtime-provider-upsert",
            json=_runtime_provider_upsert_payload(
                openai_api_key="sk-next-secret",
                idempotency_key="runtime-provider-upsert:preserve-key:second",
            ),
        )
        projection_response = client.get("/api/v1/projections/runtime-provider")

        assert second_response.status_code == 200
        assert second_response.json()["status"] == "ACCEPTED"
        assert projection_response.status_code == 200

        projection_data = projection_response.json()["data"]
        assert projection_data["effective_mode"] == "OPENAI_RESPONSES_STREAM_LIVE"
        assert projection_data["api_key_configured"] is True
        openai_provider = next(
            provider for provider in projection_data["providers"] if provider["provider_id"] == "prov_openai_compat"
        )
        assert openai_provider["health_status"] == "HEALTHY"


def test_board_approved_closeout_ticket_uses_configured_default_max_context_tokens(
    db_path,
    monkeypatch,
):
    config_path = db_path.parent / "runtime-provider-config-closeout-budget.json"
    monkeypatch.setenv("BOARDROOM_OS_RUNTIME_PROVIDER_CONFIG_PATH", str(config_path))
    monkeypatch.setenv("BOARDROOM_OS_DEFAULT_MAX_CONTEXT_TOKENS", "270000")

    from app.main import create_app

    with TestClient(create_app()) as client:
        workflow_id, scope_approval = _project_init_to_scope_approval(client)
        scope_response = _approve_open_review(client, scope_approval, idempotency_suffix="context-budget-scope")
        repository = client.app.state.repository
        approval = next(
            item
            for item in repository.list_open_approvals()
            if item["workflow_id"] == workflow_id and item["approval_type"] == "VISUAL_MILESTONE"
        )
        final_response = client.post(
            "/api/v1/commands/board-approve",
            json={
                "review_pack_id": approval["review_pack_id"],
                "review_pack_version": approval["review_pack_version"],
                "command_target_version": approval["command_target_version"],
                "approval_id": approval["approval_id"],
                "selected_option_id": "option_a",
                "board_comment": "Proceed with option A.",
                "idempotency_key": f"board-approve:{approval['approval_id']}:context-budget-final",
            },
        )
        _, closeout_ticket_id, _ = _expected_closeout_ids(repository, approval)
        with repository.connection() as connection:
            closeout_created_spec = repository.get_latest_ticket_created_payload(connection, closeout_ticket_id)

        assert scope_response.status_code == 200
        assert scope_response.json()["status"] == "ACCEPTED"
        assert final_response.status_code == 200
        assert final_response.json()["status"] == "ACCEPTED"
        assert closeout_created_spec is not None
        assert closeout_created_spec["context_query_plan"]["max_context_tokens"] == 270000


def test_dashboard_runtime_status_shows_provider_paused_when_provider_incident_is_open(
    db_path,
    monkeypatch,
):
    config_path = db_path.parent / "runtime-provider-config-paused.json"
    monkeypatch.setenv("BOARDROOM_OS_RUNTIME_PROVIDER_CONFIG_PATH", str(config_path))

    from app.main import create_app

    with TestClient(create_app()) as client:
        client.post(
            "/api/v1/commands/runtime-provider-upsert",
            json=_runtime_provider_upsert_payload(idempotency_key="runtime-provider-upsert:paused"),
        )
        _create_lease_and_start_ticket(
            client,
            workflow_id="wf_provider_paused",
            ticket_id="tkt_provider_paused",
            node_id="node_provider_paused",
        )
        fail_response = client.post(
            "/api/v1/commands/ticket-fail",
            json=_ticket_fail_payload(
                workflow_id="wf_provider_paused",
                ticket_id="tkt_provider_paused",
                node_id="node_provider_paused",
                failure_kind="PROVIDER_RATE_LIMITED",
                failure_message="Provider quota exhausted.",
                failure_detail={
                    "provider_id": "prov_openai_compat",
                    "provider_status_code": 429,
                },
                idempotency_key="ticket-fail:wf_provider_paused:tkt_provider_paused:rate-limit",
            ),
        )
        dashboard_response = client.get("/api/v1/projections/dashboard")
        provider_response = client.get("/api/v1/projections/runtime-provider")

        assert fail_response.status_code == 200
        assert fail_response.json()["status"] == "ACCEPTED"
        assert dashboard_response.status_code == 200
        assert provider_response.status_code == 200
        assert dashboard_response.json()["data"]["runtime_status"]["effective_mode"] == (
            "OPENAI_RESPONSES_STREAM_PAUSED"
        )
        assert dashboard_response.json()["data"]["runtime_status"]["provider_health_summary"] == "PAUSED"
        assert provider_response.json()["data"]["effective_mode"] == "OPENAI_RESPONSES_STREAM_PAUSED"
        assert provider_response.json()["data"]["provider_health_summary"] == "PAUSED"
        assert provider_response.json()["data"]["providers"][0]["health_status"] == "PAUSED"
        assert "paused by an open provider incident" in provider_response.json()["data"]["providers"][0]["health_reason"]


def test_runtime_provider_upsert_rejects_unknown_capability_and_invalid_fallback(db_path, monkeypatch):
    config_path = db_path.parent / "runtime-provider-config-invalid.json"
    monkeypatch.setenv("BOARDROOM_OS_RUNTIME_PROVIDER_CONFIG_PATH", str(config_path))

    from app.main import create_app

    with TestClient(create_app()) as client:
        response = client.post(
            "/api/v1/commands/runtime-provider-upsert",
            json=_runtime_provider_upsert_payload(
                openai_capability_tags=["structured_output", "unknown_capability"],
                openai_fallback_provider_ids=["prov_openai_compat", "prov_missing"],
                idempotency_key="runtime-provider-upsert:invalid",
            ),
        )

        assert response.status_code == 422


def test_dashboard_pipeline_summary_shows_review_stage_after_project_init_auto_advance(client):
    client.post("/api/v1/commands/project-init", json=_project_init_payload("Ship MVP A", budget_cap=500000))

    response = client.get("/api/v1/projections/dashboard")

    assert response.status_code == 200
    phases = response.json()["data"]["pipeline_summary"]["phases"]
    assert [phase["label"] for phase in phases] == ["Intake", "Plan", "Build", "Check", "Review"]
    intake_phase = phases[0]
    assert intake_phase["status"] == "COMPLETED"
    assert intake_phase["node_counts"]["completed"] == 1
    assert phases[1]["status"] == "PENDING"
    assert phases[2]["status"] == "PENDING"
    assert phases[3]["status"] == "PENDING"
    assert phases[4]["status"] == "PENDING"


def test_dashboard_pipeline_summary_shows_build_stage_for_executing_ticket(client):
    workflow_response = client.post("/api/v1/commands/project-init", json=_project_init_payload("Ship MVP A"))
    workflow_id = workflow_response.json()["causation_hint"].split(":", 1)[1]
    _create_lease_and_start_ticket(client, workflow_id=workflow_id)

    response = client.get("/api/v1/projections/dashboard")

    assert response.status_code == 200
    phases = response.json()["data"]["pipeline_summary"]["phases"]
    build_phase = next(phase for phase in phases if phase["label"] == "Build")
    assert build_phase["status"] == "EXECUTING"
    assert build_phase["node_counts"]["executing"] == 1


def test_dashboard_pipeline_summary_prefers_graph_truth_over_stale_node_projection(client):
    workflow_id = "wf_dashboard_graph_truth_over_stale_node_projection"
    ticket_id = "tkt_dashboard_graph_truth_runtime"
    node_id = "node_dashboard_graph_truth_runtime"
    _ensure_scoped_workflow(
        client,
        workflow_id=workflow_id,
        tenant_id="tenant_default",
        workspace_id="ws_default",
        goal="Dashboard phase summary should stay graph-first.",
    )
    _create_lease_and_start_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id=ticket_id,
        node_id=node_id,
        output_schema_ref="source_code_delivery",
        delivery_stage="BUILD",
    )
    repository = client.app.state.repository
    with repository.transaction() as connection:
        connection.execute(
            """
            UPDATE node_projection
            SET status = ?, updated_at = updated_at
            WHERE workflow_id = ? AND node_id = ?
            """,
            (NODE_STATUS_COMPLETED, workflow_id, node_id),
        )

    response = client.get("/api/v1/projections/dashboard")

    assert response.status_code == 200
    phases = response.json()["data"]["pipeline_summary"]["phases"]
    build_phase = next(phase for phase in phases if phase["label"] == "Build")
    assert build_phase["status"] == "EXECUTING"
    assert build_phase["node_counts"]["executing"] == 1
    assert build_phase["node_counts"]["completed"] == 0


def test_dashboard_pipeline_summary_stays_graph_first_after_scope_approval(client):
    _, approval = _project_init_to_scope_approval(client)
    approve_response = _approve_open_review(client, approval, idempotency_suffix="dashboard-final-review")

    response = client.get("/api/v1/projections/dashboard")

    assert approve_response.status_code == 200
    assert approve_response.json()["status"] == "ACCEPTED"
    assert response.status_code == 200
    phases = response.json()["data"]["pipeline_summary"]["phases"]
    plan_phase = next(phase for phase in phases if phase["label"] == "Plan")
    build_phase = next(phase for phase in phases if phase["label"] == "Build")
    check_phase = next(phase for phase in phases if phase["label"] == "Check")
    review_phase = next(phase for phase in phases if phase["label"] == "Review")
    assert plan_phase["status"] == "COMPLETED"
    assert build_phase["status"] == "PENDING"
    assert check_phase["status"] == "PENDING"
    assert review_phase["status"] == "PENDING"


def test_project_init_without_live_provider_writes_precondition_block_and_clears_after_provider_restore(
    client,
    set_ticket_time,
):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    workflow_response = client.post("/api/v1/commands/project-init", json=_project_init_payload("Ship MVP A"))
    workflow_id = workflow_response.json()["causation_hint"].split(":", 1)[1]
    kickoff_ticket_id = build_project_init_scope_ticket_id(workflow_id)
    repository = client.app.state.repository

    kickoff_ticket = repository.get_current_ticket_projection(kickoff_ticket_id)
    kickoff_node = repository.get_current_node_projection(workflow_id, "node_ceo_architecture_brief")
    dashboard_response = client.get("/api/v1/projections/dashboard")
    initial_block_events = [
        event
        for event in repository.list_events_for_testing()
        if event["event_type"] == EVENT_TICKET_EXECUTION_PRECONDITION_BLOCKED
    ]

    assert workflow_response.status_code == 200
    assert workflow_response.json()["status"] == "ACCEPTED"
    assert repository.count_events_by_type(EVENT_TICKET_EXECUTION_PRECONDITION_BLOCKED) == 1
    assert repository.count_events_by_type(EVENT_TICKET_EXECUTION_PRECONDITION_CLEARED) == 0
    assert repository.count_events_by_type(EVENT_TICKET_FAILED) == 0
    assert repository.count_events_by_type(EVENT_TICKET_RETRY_SCHEDULED) == 0
    assert repository.count_events_by_type(EVENT_INCIDENT_OPENED) == 0
    assert kickoff_ticket is not None
    assert kickoff_ticket["status"] == TICKET_STATUS_PENDING
    assert kickoff_ticket["lease_owner"] is None
    assert kickoff_ticket["blocking_reason_code"] == BLOCKING_REASON_PROVIDER_REQUIRED
    assert kickoff_node is not None
    assert kickoff_node["status"] == NODE_STATUS_PENDING
    assert kickoff_node["blocking_reason_code"] == BLOCKING_REASON_PROVIDER_REQUIRED
    assert len(initial_block_events) == 1
    assert initial_block_events[0]["payload"]["ticket_id"] == kickoff_ticket_id
    assert initial_block_events[0]["payload"]["node_id"] == "node_ceo_architecture_brief"
    assert initial_block_events[0]["payload"]["reason_code"] == BLOCKING_REASON_PROVIDER_REQUIRED
    assert initial_block_events[0]["payload"]["execution_target_ref"] == "execution_target:frontend_governance_document"
    assert initial_block_events[0]["payload"]["provider_effective_mode"] == "PROVIDER_REQUIRED_UNAVAILABLE"
    assert dashboard_response.json()["data"]["pipeline_summary"]["phases"][1]["status"] == "PENDING"

    set_ticket_time("2026-03-28T10:01:00+08:00")
    repeat_tick = client.post(
        "/api/v1/commands/scheduler-tick",
        json=_scheduler_tick_payload(idempotency_key="scheduler-tick:project-init-provider-blocked-repeat"),
    )
    repeated_ticket = repository.get_current_ticket_projection(kickoff_ticket_id)

    assert repeat_tick.status_code == 200
    assert repeat_tick.json()["status"] == "ACCEPTED"
    assert repository.count_events_by_type(EVENT_TICKET_EXECUTION_PRECONDITION_BLOCKED) == 1
    assert repeated_ticket is not None
    assert repeated_ticket["status"] == TICKET_STATUS_PENDING
    assert repeated_ticket["lease_owner"] is None

    provider_upsert = client.post(
        "/api/v1/commands/runtime-provider-upsert",
        json=_runtime_provider_upsert_payload(
            role_bindings=[
                {
                    "target_ref": "ceo_shadow",
                    "provider_model_entry_refs": ["prov_openai_compat::gpt-5.3-codex"],
                    "max_context_window_override": None,
                    "reasoning_effort_override": None,
                },
                {
                    "target_ref": "execution_target:frontend_governance_document",
                    "provider_model_entry_refs": ["prov_openai_compat::gpt-5.3-codex"],
                    "max_context_window_override": None,
                    "reasoning_effort_override": None,
                },
            ],
            idempotency_key="runtime-provider-upsert:project-init-provider-restore",
        ),
    )
    set_ticket_time("2026-03-28T10:02:00+08:00")
    resume_tick = client.post(
        "/api/v1/commands/scheduler-tick",
        json=_scheduler_tick_payload(idempotency_key="scheduler-tick:project-init-provider-restored"),
    )
    resumed_ticket = repository.get_current_ticket_projection(kickoff_ticket_id)
    resumed_node = repository.get_current_node_projection(workflow_id, "node_ceo_architecture_brief")
    clear_events = [
        event
        for event in repository.list_events_for_testing()
        if event["event_type"] == EVENT_TICKET_EXECUTION_PRECONDITION_CLEARED
    ]

    assert provider_upsert.status_code == 200
    assert provider_upsert.json()["status"] == "ACCEPTED"
    assert resume_tick.status_code == 200
    assert resume_tick.json()["status"] == "ACCEPTED"
    assert repository.count_events_by_type(EVENT_TICKET_EXECUTION_PRECONDITION_CLEARED) == 1
    assert len(clear_events) == 1
    assert clear_events[0]["payload"]["ticket_id"] == kickoff_ticket_id
    assert clear_events[0]["payload"]["node_id"] == "node_ceo_architecture_brief"
    assert clear_events[0]["payload"]["reason_code"] == BLOCKING_REASON_PROVIDER_REQUIRED
    assert resumed_ticket is not None
    assert resumed_ticket["status"] == TICKET_STATUS_LEASED
    assert resumed_ticket["lease_owner"] == "emp_frontend_2"
    assert resumed_ticket["blocking_reason_code"] is None
    assert resumed_node is not None
    assert resumed_node["status"] == NODE_STATUS_PENDING
    assert resumed_node["blocking_reason_code"] is None


def test_dashboard_pipeline_summary_shows_fused_build_stage_for_open_incident_breaker(client):
    workflow_response = client.post("/api/v1/commands/project-init", json=_project_init_payload("Ship MVP A"))
    workflow_id = workflow_response.json()["causation_hint"].split(":", 1)[1]
    _create_lease_and_start_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_incident_001",
        node_id="node_incident_build",
    )
    repository = client.app.state.repository
    with repository.transaction() as connection:
        repository.insert_event(
            connection,
            event_type=EVENT_INCIDENT_OPENED,
            actor_type="system",
            actor_id="test-seed",
            workflow_id=workflow_id,
            idempotency_key="test-incident-opened:node_incident_build",
            causation_id="cmd_test_incident",
            correlation_id=workflow_id,
                payload={
                    "incident_id": "inc_test_build_fused",
                    "node_id": "node_incident_build",
                    "ticket_id": "tkt_incident_001",
                    "incident_type": "REPEATED_FAILURE_ESCALATION",
                    "status": "OPEN",
                    "severity": "high",
                    "fingerprint": "runtime-timeout:node_incident_build",
                },
            occurred_at=datetime.fromisoformat("2026-03-28T10:03:00+08:00"),
        )
        repository.insert_event(
            connection,
            event_type=EVENT_CIRCUIT_BREAKER_OPENED,
            actor_type="system",
            actor_id="test-seed",
            workflow_id=workflow_id,
            idempotency_key="test-circuit-breaker-opened:node_incident_build",
            causation_id="cmd_test_incident",
            correlation_id=workflow_id,
            payload={
                "incident_id": "inc_test_build_fused",
                "node_id": "node_incident_build",
                "ticket_id": "tkt_incident_001",
                "circuit_breaker_state": "OPEN",
            },
            occurred_at=datetime.fromisoformat("2026-03-28T10:03:01+08:00"),
        )
        repository.refresh_projections(connection)

    response = client.get("/api/v1/projections/dashboard")

    assert response.status_code == 200
    phases = response.json()["data"]["pipeline_summary"]["phases"]
    build_phase = next(phase for phase in phases if phase["label"] == "Build")
    assert build_phase["status"] == "FUSED"
    assert build_phase["node_counts"]["fused"] == 1


def test_dependency_inspector_shows_scope_review_stop_after_project_init(client):
    workflow_id = "wf_dependency_inspector_review_stop"
    _ensure_scoped_workflow(
        client,
        workflow_id=workflow_id,
        tenant_id="tenant_default",
        workspace_id="ws_default",
        goal="Dependency inspector review stop",
    )
    approval = _seed_review_request(client, workflow_id=workflow_id)

    response = client.get(f"/api/v1/projections/workflows/{workflow_id}/dependency-inspector")

    assert response.status_code == 200
    body = response.json()["data"]
    assert body["workflow"]["workflow_id"] == workflow_id
    assert body["summary"]["total_nodes"] >= 1
    assert body["summary"]["blocked_nodes"] >= 1
    assert body["summary"]["open_approvals"] >= 1
    assert body["summary"]["open_incidents"] == 0
    assert body["summary"]["current_stop"]["reason"] == "BOARD_REVIEW_OPEN"
    assert body["summary"]["current_stop"]["review_pack_id"] == approval["review_pack_id"]
    assert body["graph_summary"]["graph_version"].startswith("gv_")
    assert body["graph_summary"]["source_adapter"] == "legacy_projection_adapter"
    assert body["graph_summary"]["reduction_issue_count"] == 0
    assert any(
        item["reason_code"] == "BOARD_REVIEW_OPEN"
        and body["summary"]["current_stop"]["node_id"] in item["node_ids"]
        for item in body["graph_summary"]["blocked_reasons"]
    )
    review_node = next(item for item in body["nodes"] if item["open_review_pack_id"] == approval["review_pack_id"])
    assert review_node["block_reason"] == "BOARD_REVIEW_OPEN"
    assert review_node["is_critical_path"] is True
    assert review_node["is_blocked"] is True
    assert review_node["open_incident_id"] is None
    assert "dependency_ticket_ids" in review_node


def test_dependency_inspector_prefers_source_graph_node_id_for_open_review_pack_match(client):
    workflow_id = "wf_dependency_inspector_graph_first_review_match"
    _ensure_scoped_workflow(
        client,
        workflow_id=workflow_id,
        tenant_id="tenant_default",
        workspace_id="ws_default",
        goal="Dependency inspector should use source_graph_node_id before legacy source_node_id",
    )
    approval = _seed_review_request(client, workflow_id=workflow_id)
    repository = client.app.state.repository
    payload = dict(approval["payload"] or {})
    review_pack = dict(payload.get("review_pack") or {})
    subject = dict(review_pack.get("subject") or {})
    assert str(subject.get("source_graph_node_id") or "").strip() == "node_homepage_visual::review"
    subject["source_node_id"] = "node_stale_legacy_review_lane"
    review_pack["subject"] = subject
    payload["review_pack"] = review_pack

    with repository.transaction() as connection:
        connection.execute(
            """
            UPDATE approval_projection
            SET payload_json = ?, updated_at = updated_at
            WHERE approval_id = ?
            """,
            (json.dumps(payload), approval["approval_id"]),
        )

    response = client.get(f"/api/v1/projections/workflows/{workflow_id}/dependency-inspector")

    assert response.status_code == 200
    body = response.json()["data"]
    review_node = next(item for item in body["nodes"] if item["graph_node_id"] == "node_homepage_visual::review")
    assert body["summary"]["current_stop"]["reason"] == "BOARD_REVIEW_OPEN"
    assert body["summary"]["current_stop"]["review_pack_id"] == approval["review_pack_id"]
    assert review_node["open_review_pack_id"] == approval["review_pack_id"]
    assert review_node["block_reason"] == "BOARD_REVIEW_OPEN"


def test_review_subject_identity_rejects_source_node_id_only_legacy_fallback(client):
    from app.core.review_subjects import ReviewSubjectResolutionError, resolve_review_subject_identity

    workflow_id = "wf_review_subject_source_node_only_reject"
    _ensure_scoped_workflow(
        client,
        workflow_id=workflow_id,
        tenant_id="tenant_default",
        workspace_id="ws_default",
        goal="Review subject resolution should not fall back to source_node_id only.",
    )

    with pytest.raises(
        ReviewSubjectResolutionError,
        match="missing source_graph_node_id",
    ):
        resolve_review_subject_identity(
            client.app.state.repository,
            workflow_id=workflow_id,
            subject={
                "source_node_id": "node_legacy_only_review_subject",
            },
        )


def test_dependency_inspector_shows_staged_followup_chain_after_scope_approval(client, set_ticket_time):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    workflow_id = "wf_dependency_inspector_linear_chain"
    _ensure_scoped_workflow(
        client,
        workflow_id=workflow_id,
        tenant_id="tenant_default",
        workspace_id="ws_default",
        goal="Dependency inspector linear chain",
    )
    _seed_created_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_plan_scope",
        node_id="node_plan_scope",
        role_profile_ref="ui_designer_primary",
        output_schema_ref="consensus_document",
    )
    _seed_created_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_build_app",
        node_id="node_build_app",
        role_profile_ref="frontend_engineer_primary",
        output_schema_ref="source_code_delivery",
        delivery_stage="BUILD",
        parent_ticket_id="tkt_plan_scope",
    )
    _seed_created_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_check_app",
        node_id="node_check_app",
        role_profile_ref="checker_primary",
        output_schema_ref="maker_checker_verdict",
        delivery_stage="CHECK",
        parent_ticket_id="tkt_build_app",
        dependency_gate_refs=["tkt_build_app"],
    )
    _seed_created_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_review_app",
        node_id="node_review_app",
        role_profile_ref="frontend_engineer_primary",
        output_schema_ref="ui_milestone_review",
        delivery_stage="REVIEW",
        parent_ticket_id="tkt_check_app",
        dependency_gate_refs=["tkt_check_app"],
    )
    response = client.get(f"/api/v1/projections/workflows/{workflow_id}/dependency-inspector")

    assert response.status_code == 200
    body = response.json()["data"]
    phases = [item["phase"] for item in body["nodes"]]
    assert phases == ["Plan", "Build", "Check", "Review"]
    assert body["summary"]["total_nodes"] == 4
    assert body["summary"]["critical_path_nodes"] == 0
    assert body["summary"]["blocked_nodes"] == 0
    assert body["summary"]["open_approvals"] == 0
    assert body["summary"]["current_stop"] is None

    build_node = next(item for item in body["nodes"] if item["phase"] == "Build")
    check_node = next(item for item in body["nodes"] if item["phase"] == "Check")
    review_node = next(item for item in body["nodes"] if item["phase"] == "Review")

    assert build_node["delivery_stage"] == "BUILD"
    assert check_node["delivery_stage"] == "CHECK"
    assert review_node["delivery_stage"] == "REVIEW"
    assert build_node["block_reason"] == "READY"
    assert check_node["depends_on_ticket_id"] == build_node["ticket_id"]
    assert build_node["dependency_ticket_ids"] == [body["nodes"][0]["ticket_id"]]
    assert check_node["dependency_ticket_ids"] == [build_node["ticket_id"]]
    assert review_node["dependency_ticket_ids"] == [check_node["ticket_id"]]
    assert review_node["depends_on_ticket_id"] == check_node["ticket_id"]
    assert build_node["dependent_ticket_ids"] == [check_node["ticket_id"]]
    assert check_node["dependent_ticket_ids"] == [review_node["ticket_id"]]
    assert review_node["block_reason"] == "READY"
    assert review_node["is_blocked"] is False
    assert review_node["open_review_pack_id"] is None
    assert review_node["open_incident_id"] is None
    assert "artifacts/ui/homepage/*" in build_node["expected_artifact_scope"]
    assert "reports/review/*" in build_node["expected_artifact_scope"]


def test_dependency_inspector_prefers_graph_runtime_truth_over_stale_node_projection(client):
    workflow_id = "wf_dependency_inspector_graph_truth_over_stale_node_projection"
    ticket_id = "tkt_dependency_graph_truth_runtime"
    node_id = "node_dependency_graph_truth_runtime"
    _ensure_scoped_workflow(
        client,
        workflow_id=workflow_id,
        tenant_id="tenant_default",
        workspace_id="ws_default",
        goal="Dependency inspector node status should stay graph-first.",
    )
    _create_lease_and_start_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id=ticket_id,
        node_id=node_id,
        output_schema_ref="source_code_delivery",
        delivery_stage="BUILD",
    )
    repository = client.app.state.repository
    with repository.transaction() as connection:
        connection.execute(
            """
            UPDATE node_projection
            SET status = ?, updated_at = updated_at
            WHERE workflow_id = ? AND node_id = ?
            """,
            (NODE_STATUS_COMPLETED, workflow_id, node_id),
        )

    response = client.get(f"/api/v1/projections/workflows/{workflow_id}/dependency-inspector")

    assert response.status_code == 200
    body = response.json()["data"]
    runtime_node = next(item for item in body["nodes"] if item["ticket_id"] == ticket_id)
    assert runtime_node["graph_node_id"] == node_id
    assert runtime_node["node_status"] == NODE_STATUS_EXECUTING
    assert runtime_node["ticket_status"] == TICKET_STATUS_EXECUTING
    assert runtime_node["block_reason"] == "IN_FLIGHT"


def test_dependency_inspector_marks_incident_stop_for_fused_node(client):
    workflow_id = "wf_dependency_inspector_incident_stop"
    _ensure_scoped_workflow(
        client,
        workflow_id=workflow_id,
        tenant_id="tenant_default",
        workspace_id="ws_default",
        goal="Dependency inspector incident stop",
    )
    _create_lease_and_start_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_incident_dependency_001",
        node_id="node_incident_dependency_build",
    )
    repository = client.app.state.repository
    with repository.transaction() as connection:
        repository.insert_event(
            connection,
            event_type=EVENT_INCIDENT_OPENED,
            actor_type="system",
            actor_id="test-seed",
            workflow_id=workflow_id,
            idempotency_key="test-dependency-incident-opened:node_incident_dependency_build",
            causation_id="cmd_test_dependency_incident",
            correlation_id=workflow_id,
            payload={
                "incident_id": "inc_dependency_build_fused",
                "node_id": "node_incident_dependency_build",
                "ticket_id": "tkt_incident_dependency_001",
                "incident_type": "REPEATED_FAILURE_ESCALATION",
                "status": "OPEN",
                "severity": "high",
                "fingerprint": "runtime-timeout:node_incident_dependency_build",
            },
            occurred_at=datetime.fromisoformat("2026-03-28T10:03:00+08:00"),
        )
        repository.insert_event(
            connection,
            event_type=EVENT_CIRCUIT_BREAKER_OPENED,
            actor_type="system",
            actor_id="test-seed",
            workflow_id=workflow_id,
            idempotency_key="test-dependency-circuit-breaker-opened:node_incident_dependency_build",
            causation_id="cmd_test_dependency_incident",
            correlation_id=workflow_id,
            payload={
                "incident_id": "inc_dependency_build_fused",
                "node_id": "node_incident_dependency_build",
                "ticket_id": "tkt_incident_dependency_001",
                "circuit_breaker_state": "OPEN",
            },
            occurred_at=datetime.fromisoformat("2026-03-28T10:03:01+08:00"),
        )
        repository.refresh_projections(connection)

    response = client.get(f"/api/v1/projections/workflows/{workflow_id}/dependency-inspector")

    assert response.status_code == 200
    body = response.json()["data"]
    assert body["summary"]["open_incidents"] == 1
    assert body["summary"]["current_stop"]["reason"] == "INCIDENT_OPEN"
    incident_node = next(item for item in body["nodes"] if item["node_id"] == "node_incident_dependency_build")
    assert incident_node["block_reason"] == "INCIDENT_OPEN"
    assert incident_node["is_blocked"] is True
    assert incident_node["open_incident_id"] == "inc_dependency_build_fused"
    assert incident_node["open_review_pack_id"] is None
    assert any(
        item["reason_code"] == "INCIDENT_OPEN" and "node_incident_dependency_build" in item["node_ids"]
        for item in body["graph_summary"]["blocked_reasons"]
    )


def test_dependency_inspector_exposes_multiple_dependency_gate_refs_from_ticket_graph(client):
    workflow_id = "wf_dependency_inspector_multi_dependency"
    _ensure_scoped_workflow(
        client,
        workflow_id=workflow_id,
        tenant_id="tenant_default",
        workspace_id="ws_default",
        goal="Dependency inspector shows multiple dependency gates",
    )
    _seed_created_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_build_api",
        node_id="node_build_api",
        role_profile_ref="frontend_engineer_primary",
        output_schema_ref="source_code_delivery",
        delivery_stage="BUILD",
    )
    _seed_created_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_build_ui",
        node_id="node_build_ui",
        role_profile_ref="frontend_engineer_primary",
        output_schema_ref="source_code_delivery",
        delivery_stage="BUILD",
    )
    _seed_created_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_check_bundle",
        node_id="node_check_bundle",
        role_profile_ref="checker_primary",
        output_schema_ref="maker_checker_verdict",
        delivery_stage="CHECK",
        dependency_gate_refs=["tkt_build_api", "tkt_build_ui"],
    )

    response = client.get(f"/api/v1/projections/workflows/{workflow_id}/dependency-inspector")

    assert response.status_code == 200
    body = response.json()["data"]
    check_node = next(item for item in body["nodes"] if item["node_id"] == "node_check_bundle")
    api_build_node = next(item for item in body["nodes"] if item["node_id"] == "node_build_api")
    ui_build_node = next(item for item in body["nodes"] if item["node_id"] == "node_build_ui")

    assert check_node["depends_on_ticket_id"] == "tkt_build_api"
    assert check_node["dependency_ticket_ids"] == ["tkt_build_api", "tkt_build_ui"]
    assert api_build_node["dependent_ticket_ids"] == ["tkt_check_bundle"]
    assert ui_build_node["dependent_ticket_ids"] == ["tkt_check_bundle"]


def test_dependency_inspector_surfaces_graph_reduction_issue_without_legacy_fallback(client):
    workflow_id = "wf_dependency_inspector_graph_issue"
    _ensure_scoped_workflow(
        client,
        workflow_id=workflow_id,
        tenant_id="tenant_default",
        workspace_id="ws_default",
        goal="Dependency inspector surfaces graph reduction issues",
    )
    _seed_created_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_invalid_dependency",
        node_id="node_invalid_dependency",
        role_profile_ref="frontend_engineer_primary",
        output_schema_ref="source_code_delivery",
        delivery_stage="BUILD",
        dependency_gate_refs=["tkt_missing_dependency"],
    )

    response = client.get(f"/api/v1/projections/workflows/{workflow_id}/dependency-inspector")

    assert response.status_code == 200
    body = response.json()["data"]
    invalid_node = body["nodes"][0]

    assert body["summary"]["current_stop"]["reason"] == "GRAPH_REDUCTION_ISSUE"
    assert body["graph_summary"]["reduction_issue_count"] == 1
    assert any(
        item["reason_code"] == "GRAPH_REDUCTION_ISSUE" and item["node_ids"] == ["node_invalid_dependency"]
        for item in body["graph_summary"]["blocked_reasons"]
    )
    assert invalid_node["block_reason"] == "GRAPH_REDUCTION_ISSUE"
    assert invalid_node["is_blocked"] is True


def test_dependency_inspector_shows_graph_only_placeholder_node_with_materialization_state(client):
    workflow_id = "wf_dependency_inspector_placeholder_node"
    _ensure_scoped_workflow(
        client,
        workflow_id=workflow_id,
        tenant_id="tenant_default",
        workspace_id="ws_default",
        goal="Dependency inspector should surface graph-only placeholder nodes.",
    )
    _seed_created_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_dependency_placeholder_parent",
        node_id="node_dependency_placeholder_parent",
        role_profile_ref="frontend_engineer_primary",
        output_schema_ref="source_code_delivery",
        delivery_stage="BUILD",
    )
    _seed_created_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_dependency_placeholder_dependency",
        node_id="node_dependency_placeholder_dependency",
        role_profile_ref="frontend_engineer_primary",
        output_schema_ref="source_code_delivery",
        delivery_stage="BUILD",
    )
    _seed_graph_patch_applied_event(
        client,
        workflow_id=workflow_id,
        patch_index=1,
        freeze_node_ids=[],
        focus_node_ids=["node_dependency_placeholder_build"],
        add_nodes=[
            {
                "node_id": "node_dependency_placeholder_build",
                "node_kind": "IMPLEMENTATION",
                "deliverable_kind": "source_code_delivery",
                "role_hint": "frontend_engineer_primary",
                "parent_node_id": "node_dependency_placeholder_parent",
                "dependency_node_ids": ["node_dependency_placeholder_dependency"],
            }
        ],
    )

    response = client.get(f"/api/v1/projections/workflows/{workflow_id}/dependency-inspector")

    assert response.status_code == 200
    body = response.json()["data"]
    placeholder_node = next(
        item for item in body["nodes"] if item["node_id"] == "node_dependency_placeholder_build"
    )

    assert placeholder_node["ticket_id"] is None
    assert placeholder_node["graph_node_id"] == "node_dependency_placeholder_build"
    assert placeholder_node["runtime_node_id"] is None
    assert placeholder_node["is_placeholder"] is True
    assert placeholder_node["materialization_state"] == "planned"
    assert placeholder_node["dependency_ticket_ids"] == [
        "tkt_dependency_placeholder_dependency",
        "tkt_dependency_placeholder_parent",
    ]
    assert placeholder_node["dependent_ticket_ids"] == []
    assert placeholder_node["block_reason"] == "PENDING"
    assert placeholder_node["is_blocked"] is False
    assert body["summary"]["total_nodes"] == 3
    placeholder_projection = client.app.state.repository.get_planned_placeholder_projection(
        workflow_id,
        "node_dependency_placeholder_build",
    )
    assert placeholder_projection is not None
    assert placeholder_projection["status"] == "PLANNED"


def test_ticket_start_rejects_stale_runtime_node_projection_version(client):
    workflow_id = "wf_ticket_start_runtime_node_version_guard"
    ticket_id = "tkt_ticket_start_runtime_node_version_guard"
    node_id = "node_ticket_start_runtime_node_version_guard"
    _ensure_scoped_workflow(
        client,
        workflow_id=workflow_id,
        tenant_id="tenant_default",
        workspace_id="ws_default",
        goal="Ticket-start should reject stale runtime node projection versions.",
    )
    _seed_created_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id=ticket_id,
        node_id=node_id,
        role_profile_ref="frontend_engineer_primary",
        output_schema_ref="source_code_delivery",
        delivery_stage="BUILD",
    )

    repository = client.app.state.repository
    ticket_projection = repository.get_current_ticket_projection(ticket_id)
    node_projection = repository.get_current_node_projection(workflow_id, node_id)
    runtime_node_projection = repository.get_runtime_node_projection(workflow_id, node_id)

    assert ticket_projection is not None
    assert node_projection is not None
    assert runtime_node_projection is not None

    response = client.post(
        "/api/v1/commands/ticket-start",
        json=_ticket_start_payload(
            workflow_id=workflow_id,
            ticket_id=ticket_id,
            node_id=node_id,
            expected_ticket_version=int(ticket_projection["version"]),
            expected_node_version=int(node_projection["version"]),
            expected_runtime_node_version=int(runtime_node_projection["version"]) - 1,
        ),
    )

    assert response.status_code == 200
    assert response.json()["status"] == "REJECTED"
    assert "runtime node version" in str(response.json()["reason"]).lower()


def test_ticket_start_rejects_stale_review_lane_runtime_node_projection_version(client):
    workflow_id = "wf_ticket_start_review_lane_runtime_node_version_guard"
    _ensure_scoped_workflow(
        client,
        workflow_id=workflow_id,
        tenant_id="tenant_default",
        workspace_id="ws_default",
        goal="Review-lane ticket-start should reject stale runtime node projection versions.",
    )
    _create_lease_and_start_ticket(client, workflow_id=workflow_id)

    maker_response = client.post(
        "/api/v1/commands/ticket-complete",
        json=_ticket_complete_payload(workflow_id=workflow_id),
    )
    assert maker_response.status_code == 200
    assert maker_response.json()["status"] == "ACCEPTED"

    repository = client.app.state.repository
    current_node = repository.get_current_node_projection(workflow_id, "node_homepage_visual")
    assert current_node is not None
    checker_ticket_id = current_node["latest_ticket_id"]

    checker_lease_response = client.post(
        "/api/v1/commands/ticket-lease",
        json=_ticket_lease_payload(
            workflow_id=workflow_id,
            ticket_id=checker_ticket_id,
            leased_by="emp_checker_1",
        ),
    )
    assert checker_lease_response.status_code == 200
    assert checker_lease_response.json()["status"] == "ACCEPTED"

    checker_ticket = repository.get_current_ticket_projection(checker_ticket_id)
    checker_node = repository.get_current_node_projection(workflow_id, "node_homepage_visual")
    review_runtime_node = repository.get_runtime_node_projection(
        workflow_id,
        "node_homepage_visual::review",
    )

    assert checker_ticket is not None
    assert checker_node is not None
    assert review_runtime_node is not None

    response = client.post(
        "/api/v1/commands/ticket-start",
        json=_ticket_start_payload(
            workflow_id=workflow_id,
            ticket_id=checker_ticket_id,
            node_id="node_homepage_visual",
            started_by="emp_checker_1",
            expected_ticket_version=int(checker_ticket["version"]),
            expected_node_version=int(checker_node["version"]),
            expected_runtime_node_version=int(review_runtime_node["version"]) - 1,
        ),
    )

    assert response.status_code == 200
    assert response.json()["status"] == "REJECTED"
    assert "runtime node version" in str(response.json()["reason"]).lower()


def test_ticket_create_accepts_placeholder_node_and_materializes_runtime_truth(client):
    workflow_id = "wf_ticket_create_placeholder_materialization"
    _ensure_scoped_workflow(
        client,
        workflow_id=workflow_id,
        tenant_id="tenant_default",
        workspace_id="ws_default",
        goal="Create-ticket should absorb a graph-only placeholder into runtime truth.",
    )
    _seed_created_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_placeholder_materialization_parent",
        node_id="node_placeholder_materialization_parent",
        role_profile_ref="frontend_engineer_primary",
        output_schema_ref="source_code_delivery",
        delivery_stage="BUILD",
    )
    _seed_graph_patch_applied_event(
        client,
        workflow_id=workflow_id,
        patch_index=1,
        freeze_node_ids=[],
        focus_node_ids=["node_placeholder_materialization_build"],
        add_nodes=[
            {
                "node_id": "node_placeholder_materialization_build",
                "node_kind": "IMPLEMENTATION",
                "deliverable_kind": "source_code_delivery",
                "role_hint": "frontend_engineer_primary",
                "parent_node_id": "node_placeholder_materialization_parent",
                "dependency_node_ids": [],
            }
        ],
    )

    create_response = client.post(
        "/api/v1/commands/ticket-create",
        json=_ticket_create_payload(
            workflow_id=workflow_id,
            ticket_id="tkt_placeholder_materialization_build",
            node_id="node_placeholder_materialization_build",
            role_profile_ref="frontend_engineer_primary",
            output_schema_ref="source_code_delivery",
            delivery_stage="BUILD",
            parent_ticket_id="tkt_placeholder_materialization_parent",
        ),
    )

    repository = client.app.state.repository
    node_projection = repository.get_current_node_projection(
        workflow_id,
        "node_placeholder_materialization_build",
    )
    graph_snapshot = build_ticket_graph_snapshot(repository, workflow_id)
    graph_node = next(
        node for node in graph_snapshot.nodes if node.graph_node_id == "node_placeholder_materialization_build"
    )

    assert create_response.status_code == 200
    assert create_response.json()["status"] == "ACCEPTED"
    assert node_projection is not None
    assert node_projection["latest_ticket_id"] == "tkt_placeholder_materialization_build"
    assert graph_node.is_placeholder is False
    assert graph_node.ticket_id == "tkt_placeholder_materialization_build"
    assert (
        repository.get_planned_placeholder_projection(
            workflow_id,
            "node_placeholder_materialization_build",
        )
        is None
    )

    duplicate_response = client.post(
        "/api/v1/commands/ticket-create",
        json=_ticket_create_payload(
            workflow_id=workflow_id,
            ticket_id="tkt_placeholder_materialization_build_retry",
            node_id="node_placeholder_materialization_build",
            role_profile_ref="frontend_engineer_primary",
            output_schema_ref="source_code_delivery",
            delivery_stage="BUILD",
            parent_ticket_id="tkt_placeholder_materialization_parent",
        ),
    )

    assert duplicate_response.status_code == 200
    assert duplicate_response.json()["status"] == "REJECTED"
    assert "cannot accept a new ticket while status is PENDING" in duplicate_response.json()["reason"]


def test_ticket_start_rejects_planned_placeholder_before_materialization(client):
    workflow_id = "wf_ticket_start_placeholder_gate"
    _ensure_scoped_workflow(
        client,
        workflow_id=workflow_id,
        tenant_id="tenant_default",
        workspace_id="ws_default",
        goal="Ticket-start should fail closed for graph-only placeholders.",
    )
    _seed_created_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_ticket_start_placeholder_parent",
        node_id="node_ticket_start_placeholder_parent",
        role_profile_ref="frontend_engineer_primary",
        output_schema_ref="source_code_delivery",
        delivery_stage="BUILD",
    )
    _seed_graph_patch_applied_event(
        client,
        workflow_id=workflow_id,
        patch_index=1,
        freeze_node_ids=[],
        focus_node_ids=["node_ticket_start_placeholder_target"],
        add_nodes=[
            {
                "node_id": "node_ticket_start_placeholder_target",
                "node_kind": "IMPLEMENTATION",
                "deliverable_kind": "source_code_delivery",
                "role_hint": "frontend_engineer_primary",
                "parent_node_id": "node_ticket_start_placeholder_parent",
                "dependency_node_ids": [],
            }
        ],
    )

    response = client.post(
        "/api/v1/commands/ticket-start",
        json=_ticket_start_payload(
            workflow_id=workflow_id,
            ticket_id="tkt_ticket_start_placeholder_target",
            node_id="node_ticket_start_placeholder_target",
        ),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "REJECTED"
    assert "PLANNED_PLACEHOLDER_NOT_MATERIALIZED" in str(body["reason"])


def test_ticket_result_submit_rejects_planned_placeholder_before_materialization(client):
    workflow_id = "wf_ticket_result_placeholder_gate"
    _ensure_scoped_workflow(
        client,
        workflow_id=workflow_id,
        tenant_id="tenant_default",
        workspace_id="ws_default",
        goal="Ticket result submit should fail closed for graph-only placeholders.",
    )
    _seed_created_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_ticket_result_placeholder_parent",
        node_id="node_ticket_result_placeholder_parent",
        role_profile_ref="frontend_engineer_primary",
        output_schema_ref="source_code_delivery",
        delivery_stage="BUILD",
    )
    _seed_graph_patch_applied_event(
        client,
        workflow_id=workflow_id,
        patch_index=1,
        freeze_node_ids=[],
        focus_node_ids=["node_ticket_result_placeholder_target"],
        add_nodes=[
            {
                "node_id": "node_ticket_result_placeholder_target",
                "node_kind": "IMPLEMENTATION",
                "deliverable_kind": "source_code_delivery",
                "role_hint": "frontend_engineer_primary",
                "parent_node_id": "node_ticket_result_placeholder_parent",
                "dependency_node_ids": [],
            }
        ],
    )

    response = client.post(
        "/api/v1/commands/ticket-result-submit",
        json=_ticket_result_submit_payload(
            workflow_id=workflow_id,
            ticket_id="tkt_ticket_result_placeholder_target",
            node_id="node_ticket_result_placeholder_target",
            idempotency_key="ticket-result-submit:wf_ticket_result_placeholder_gate:planned-placeholder",
        ),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "REJECTED"
    assert "PLANNED_PLACEHOLDER_NOT_MATERIALIZED" in str(body["reason"])


def test_dashboard_workforce_summary_reflects_seeded_roster_and_busy_worker(client, set_ticket_time):
    initial_response = client.get("/api/v1/projections/dashboard")

    assert initial_response.status_code == 200
    initial_summary = initial_response.json()["data"]["workforce_summary"]
    assert initial_summary["active_workers"] == 0
    assert initial_summary["idle_workers"] == 1
    assert initial_summary["active_checkers"] == 0

    set_ticket_time("2026-03-28T10:00:00+08:00")
    _create_and_lease_ticket(client)
    active_response = client.get("/api/v1/projections/dashboard")
    active_summary = active_response.json()["data"]["workforce_summary"]

    assert active_summary["active_workers"] == 1
    assert active_summary["idle_workers"] == 0
    assert active_summary["active_checkers"] == 0


def test_workforce_projection_returns_seeded_role_lanes(client):
    response = client.get("/api/v1/projections/workforce")

    assert response.status_code == 200
    role_lanes = {lane["role_type"]: lane for lane in response.json()["data"]["role_lanes"]}
    assert role_lanes["frontend_engineer"]["active_count"] == 0
    assert role_lanes["frontend_engineer"]["idle_count"] == 1
    assert role_lanes["frontend_engineer"]["workers"][0]["employee_id"] == "emp_frontend_2"
    assert role_lanes["frontend_engineer"]["workers"][0]["employment_state"] == "ACTIVE"
    assert role_lanes["frontend_engineer"]["workers"][0]["provider_id"] == "prov_openai_compat"
    assert role_lanes["checker"]["workers"][0]["employee_id"] == "emp_checker_1"
    assert role_lanes["checker"]["workers"][0]["employment_state"] == "ACTIVE"


def test_dashboard_exposes_artifact_cleanup_maintenance_summary(client, set_ticket_time):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    _create_lease_and_start_ticket(client)
    artifact_ref = "art://reports/homepage/dashboard-cleanup.md"

    submit_response = client.post(
        "/api/v1/commands/ticket-result-submit",
        json=_ticket_result_submit_payload(
            artifact_refs=[artifact_ref],
            payload={
                "summary": "Dashboard should expose artifact cleanup health.",
                "recommended_option_id": "option_a",
                "options": [
                    {
                        "option_id": "option_a",
                        "label": "Option A",
                        "summary": "Cleanup dashboard option.",
                        "artifact_refs": [artifact_ref],
                    }
                ],
            },
            written_artifacts=[
                {
                    "path": "reports/review/dashboard-cleanup.md",
                    "artifact_ref": artifact_ref,
                    "kind": "MARKDOWN",
                    "content_text": "# Cleanup\n\nPending cleanup should show up on dashboard.\n",
                    "retention_class": "EPHEMERAL",
                    "retention_ttl_sec": 60,
                }
            ],
            idempotency_key="ticket-result-submit:wf_seed:tkt_visual_001:dashboard-cleanup",
        ),
    )

    set_ticket_time("2026-03-28T10:02:00+08:00")
    cleanup_response = client.post(
        "/api/v1/commands/artifact-cleanup",
        json={
            "cleaned_by": "emp_ops_1",
            "idempotency_key": "artifact-cleanup:dashboard-maintenance",
        },
    )
    dashboard_response = client.get("/api/v1/projections/dashboard")

    assert submit_response.status_code == 200
    assert cleanup_response.status_code == 200
    assert dashboard_response.status_code == 200
    artifact_maintenance = dashboard_response.json()["data"]["artifact_maintenance"]
    assert artifact_maintenance["auto_cleanup_enabled"] is True
    assert artifact_maintenance["cleanup_interval_sec"] == 300
    assert artifact_maintenance["pending_expired_count"] == 0
    assert artifact_maintenance["pending_storage_cleanup_count"] == 0
    assert artifact_maintenance["last_cleaned_by"] == "emp_ops_1"
    assert artifact_maintenance["last_trigger"] == "manual_command"
    assert artifact_maintenance["last_expired_count"] == 1
    assert artifact_maintenance["last_storage_deleted_count"] == 1


def test_ticket_artifacts_projection_applies_default_ephemeral_ttl_and_exposes_retention_fields(
    db_path,
    monkeypatch,
    set_ticket_time,
):
    monkeypatch.setenv("BOARDROOM_OS_ARTIFACT_EPHEMERAL_DEFAULT_TTL_SEC", "120")

    from app.main import create_app

    app = create_app()
    with TestClient(app) as client:
        set_ticket_time("2026-03-28T10:00:00+08:00")
        _create_lease_and_start_ticket(client)
        artifact_ref = "art://reports/homepage/default-ttl.md"

        submit_response = client.post(
            "/api/v1/commands/ticket-result-submit",
            json=_ticket_result_submit_payload(
                artifact_refs=[artifact_ref],
                payload={
                    "summary": "Ephemeral artifact should pick up default retention TTL.",
                    "recommended_option_id": "option_a",
                    "options": [
                        {
                            "option_id": "option_a",
                            "label": "Option A",
                            "summary": "Default TTL option.",
                            "artifact_refs": [artifact_ref],
                        }
                    ],
                },
                written_artifacts=[
                    {
                        "path": "reports/review/default-ttl.md",
                        "artifact_ref": artifact_ref,
                        "kind": "MARKDOWN",
                        "content_text": "# Default TTL\n\nUse class default.\n",
                        "retention_class": "EPHEMERAL",
                    }
                ],
                idempotency_key="ticket-result-submit:wf_seed:tkt_visual_001:default-ttl",
            ),
        )
        projection_response = client.get("/api/v1/projections/tickets/tkt_visual_001/artifacts")
        projected_artifact = next(
            item
            for item in projection_response.json()["data"]["artifacts"]
            if item["artifact_ref"] == artifact_ref
        )
        stored_artifact = client.app.state.repository.get_artifact_by_ref(artifact_ref)

        assert submit_response.status_code == 200
        assert projection_response.status_code == 200
        assert stored_artifact is not None
        assert stored_artifact["retention_ttl_sec"] == 120
        assert stored_artifact["retention_policy_source"] == "CLASS_DEFAULT"
        assert stored_artifact["expires_at"] == datetime.fromisoformat("2026-03-28T10:02:00+08:00")
        assert projected_artifact["retention_ttl_sec"] == 120
        assert projected_artifact["retention_policy_source"] == "CLASS_DEFAULT"
        assert projected_artifact["expires_at"] == "2026-03-28T10:02:00+08:00"


def test_ticket_artifacts_projection_applies_default_review_evidence_ttl(
    db_path,
    monkeypatch,
    set_ticket_time,
):
    monkeypatch.setenv("BOARDROOM_OS_ARTIFACT_REVIEW_EVIDENCE_DEFAULT_TTL_SEC", "1800")

    from app.main import create_app

    app = create_app()
    with TestClient(app) as client:
        set_ticket_time("2026-03-28T10:00:00+08:00")
        _create_lease_and_start_ticket(client)
        artifact_ref = "art://reports/homepage/review-evidence.md"

        submit_response = client.post(
            "/api/v1/commands/ticket-result-submit",
            json=_ticket_result_submit_payload(
                artifact_refs=[artifact_ref],
                payload={
                    "summary": "Review evidence artifact should pick up review-evidence default TTL.",
                    "recommended_option_id": "option_a",
                    "options": [
                        {
                            "option_id": "option_a",
                            "label": "Option A",
                            "summary": "Review evidence option.",
                            "artifact_refs": [artifact_ref],
                        }
                    ],
                },
                written_artifacts=[
                    {
                        "path": "reports/review/review-evidence.md",
                        "artifact_ref": artifact_ref,
                        "kind": "MARKDOWN",
                        "content_text": "# Review Evidence\n\nKeep for board review window.\n",
                    }
                ],
                idempotency_key="ticket-result-submit:wf_seed:tkt_visual_001:review-evidence-default-ttl",
            ),
        )
        projection_response = client.get("/api/v1/projections/tickets/tkt_visual_001/artifacts")
        projected_artifact = next(
            item
            for item in projection_response.json()["data"]["artifacts"]
            if item["artifact_ref"] == artifact_ref
        )
        stored_artifact = client.app.state.repository.get_artifact_by_ref(artifact_ref)

        assert submit_response.status_code == 200
        assert projection_response.status_code == 200
        assert stored_artifact is not None
        assert stored_artifact["retention_class"] == "REVIEW_EVIDENCE"
        assert stored_artifact["retention_class_source"] == "PATH_DEFAULT"
        assert stored_artifact["retention_ttl_sec"] == 1800
        assert stored_artifact["retention_policy_source"] == "CLASS_DEFAULT"
        assert stored_artifact["expires_at"] == datetime.fromisoformat("2026-03-28T10:30:00+08:00")
        assert projected_artifact["retention_class"] == "REVIEW_EVIDENCE"
        assert projected_artifact["retention_class_source"] == "PATH_DEFAULT"
        assert projected_artifact["retention_ttl_sec"] == 1800
        assert projected_artifact["retention_policy_source"] == "CLASS_DEFAULT"
        assert projected_artifact["expires_at"] == "2026-03-28T10:30:00+08:00"


def test_ticket_artifacts_projection_applies_default_operational_evidence_ttl_for_ops_reports(
    db_path,
    monkeypatch,
    set_ticket_time,
):
    monkeypatch.setenv("BOARDROOM_OS_ARTIFACT_OPERATIONAL_EVIDENCE_DEFAULT_TTL_SEC", "600")

    from app.main import create_app

    app = create_app()
    with TestClient(app) as client:
        set_ticket_time("2026-03-28T10:00:00+08:00")
        _create_lease_and_start_ticket(
            client,
            allowed_write_set=["artifacts/ui/homepage/*", "reports/review/*", "reports/ops/*"],
        )
        artifact_ref = "art://reports/ops/runtime-diagnostic.md"

        submit_response = client.post(
            "/api/v1/commands/ticket-result-submit",
            json=_ticket_result_submit_payload(
                artifact_refs=[artifact_ref],
                payload={
                    "summary": "Operational evidence should pick up path default retention.",
                    "recommended_option_id": "option_a",
                    "options": [
                        {
                            "option_id": "option_a",
                            "label": "Option A",
                            "summary": "Operational evidence option.",
                            "artifact_refs": [artifact_ref],
                        }
                    ],
                },
                written_artifacts=[
                    {
                        "path": "reports/ops/runtime-diagnostic.md",
                        "artifact_ref": artifact_ref,
                        "kind": "MARKDOWN",
                        "content_text": "# Runtime Diagnostic\n\nKeep for incident follow-up.\n",
                    }
                ],
                idempotency_key="ticket-result-submit:wf_seed:tkt_visual_001:operational-evidence-default-ttl",
            ),
        )
        projection_response = client.get("/api/v1/projections/tickets/tkt_visual_001/artifacts")
        projected_artifact = next(
            item
            for item in projection_response.json()["data"]["artifacts"]
            if item["artifact_ref"] == artifact_ref
        )
        stored_artifact = client.app.state.repository.get_artifact_by_ref(artifact_ref)

        assert submit_response.status_code == 200
        assert projection_response.status_code == 200
        assert stored_artifact is not None
        assert stored_artifact["retention_class"] == "OPERATIONAL_EVIDENCE"
        assert stored_artifact["retention_class_source"] == "PATH_DEFAULT"
        assert stored_artifact["retention_ttl_sec"] == 600
        assert stored_artifact["retention_policy_source"] == "CLASS_DEFAULT"
        assert stored_artifact["expires_at"] == datetime.fromisoformat("2026-03-28T10:10:00+08:00")
        assert projected_artifact["retention_class"] == "OPERATIONAL_EVIDENCE"
        assert projected_artifact["retention_class_source"] == "PATH_DEFAULT"
        assert projected_artifact["retention_ttl_sec"] == 600
        assert projected_artifact["retention_policy_source"] == "CLASS_DEFAULT"
        assert projected_artifact["expires_at"] == "2026-03-28T10:10:00+08:00"


def test_explicit_retention_class_overrides_path_default(
    db_path,
    monkeypatch,
    set_ticket_time,
):
    monkeypatch.setenv("BOARDROOM_OS_ARTIFACT_OPERATIONAL_EVIDENCE_DEFAULT_TTL_SEC", "600")

    from app.main import create_app

    app = create_app()
    with TestClient(app) as client:
        set_ticket_time("2026-03-28T10:00:00+08:00")
        _create_lease_and_start_ticket(client)
        artifact_ref = "art://reports/review/persistent-runbook.md"

        submit_response = client.post(
            "/api/v1/commands/ticket-result-submit",
            json=_ticket_result_submit_payload(
                artifact_refs=[artifact_ref],
                payload={
                    "summary": "Explicit retention class should override path default.",
                    "recommended_option_id": "option_a",
                    "options": [
                        {
                            "option_id": "option_a",
                            "label": "Option A",
                            "summary": "Persistent runbook option.",
                            "artifact_refs": [artifact_ref],
                        }
                    ],
                },
                written_artifacts=[
                    {
                        "path": "reports/review/persistent-runbook.md",
                        "artifact_ref": artifact_ref,
                        "kind": "MARKDOWN",
                        "content_text": "# Persistent Runbook\n\nKeep long term.\n",
                        "retention_class": "PERSISTENT",
                    }
                ],
                idempotency_key="ticket-result-submit:wf_seed:tkt_visual_001:explicit-retention-class-override",
            ),
        )
        projection_response = client.get("/api/v1/projections/tickets/tkt_visual_001/artifacts")
        projected_artifact = next(
            item
            for item in projection_response.json()["data"]["artifacts"]
            if item["artifact_ref"] == artifact_ref
        )
        stored_artifact = client.app.state.repository.get_artifact_by_ref(artifact_ref)

        assert submit_response.status_code == 200
        assert projection_response.status_code == 200
        assert stored_artifact is not None
        assert stored_artifact["retention_class"] == "PERSISTENT"
        assert stored_artifact["retention_class_source"] == "EXPLICIT"
        assert stored_artifact["retention_ttl_sec"] is None
        assert stored_artifact["retention_policy_source"] == "NO_EXPIRY"
        assert projected_artifact["retention_class"] == "PERSISTENT"
        assert projected_artifact["retention_class_source"] == "EXPLICIT"
        assert projected_artifact["retention_ttl_sec"] is None
        assert projected_artifact["retention_policy_source"] == "NO_EXPIRY"


def test_dashboard_and_cleanup_candidates_expose_retention_policy_state(
    db_path,
    monkeypatch,
    set_ticket_time,
):
    monkeypatch.setenv("BOARDROOM_OS_ARTIFACT_EPHEMERAL_DEFAULT_TTL_SEC", "60")
    monkeypatch.setenv("BOARDROOM_OS_ARTIFACT_REVIEW_EVIDENCE_DEFAULT_TTL_SEC", "1800")
    monkeypatch.setenv("BOARDROOM_OS_ARTIFACT_OPERATIONAL_EVIDENCE_DEFAULT_TTL_SEC", "600")
    connection = sqlite3.connect(db_path)
    connection.execute(
        """
        CREATE TABLE artifact_index (
            artifact_ref TEXT PRIMARY KEY,
            workflow_id TEXT NOT NULL,
            ticket_id TEXT NOT NULL,
            node_id TEXT NOT NULL,
            logical_path TEXT NOT NULL,
            kind TEXT NOT NULL,
            media_type TEXT,
            materialization_status TEXT NOT NULL,
            lifecycle_status TEXT NOT NULL,
            storage_relpath TEXT,
            content_hash TEXT,
            size_bytes INTEGER,
            retention_class TEXT NOT NULL,
            expires_at TEXT,
            deleted_at TEXT,
            deleted_by TEXT,
            delete_reason TEXT,
            storage_deleted_at TEXT,
            created_at TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        INSERT INTO artifact_index (
            artifact_ref,
            workflow_id,
            ticket_id,
            node_id,
            logical_path,
            kind,
            media_type,
            materialization_status,
            lifecycle_status,
            storage_relpath,
            content_hash,
            size_bytes,
            retention_class,
            expires_at,
            deleted_at,
            deleted_by,
            delete_reason,
            storage_deleted_at,
            created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "art://legacy/explicit-expiry.md",
            "wf_legacy",
            "tkt_legacy",
            "node_legacy",
            "artifacts/legacy/explicit-expiry.md",
            "MARKDOWN",
            "text/markdown",
            "MATERIALIZED",
            "ACTIVE",
            "artifacts/legacy/explicit-expiry.md",
            "hash-legacy-explicit",
            32,
            "EPHEMERAL",
            "2026-03-28T09:30:00+08:00",
            None,
            None,
            None,
            None,
            "2026-03-28T09:00:00+08:00",
        ),
    )
    connection.commit()
    connection.close()

    from app.main import create_app

    app = create_app()
    with TestClient(app) as client:
        set_ticket_time("2026-03-28T10:00:00+08:00")
        _create_lease_and_start_ticket(client)
        artifact_ref = "art://reports/homepage/cleanup-candidate.md"

        submit_response = client.post(
            "/api/v1/commands/ticket-result-submit",
            json=_ticket_result_submit_payload(
                artifact_refs=[artifact_ref],
                payload={
                    "summary": "Cleanup candidate should expose retention policy state.",
                    "recommended_option_id": "option_a",
                    "options": [
                        {
                            "option_id": "option_a",
                            "label": "Option A",
                            "summary": "Cleanup candidate option.",
                            "artifact_refs": [artifact_ref],
                        }
                    ],
                },
                written_artifacts=[
                    {
                        "path": "reports/review/cleanup-candidate.md",
                        "artifact_ref": artifact_ref,
                        "kind": "MARKDOWN",
                        "content_text": "# Cleanup candidate\n\nWaiting for cleanup.\n",
                    }
                ],
                idempotency_key="ticket-result-submit:wf_seed:tkt_visual_001:cleanup-candidate",
            ),
        )
        repository = client.app.state.repository
        with repository.transaction() as txn:
            txn.execute(
                """
                INSERT INTO artifact_index (
                    artifact_ref,
                    workflow_id,
                    ticket_id,
                    node_id,
                    logical_path,
                    kind,
                    media_type,
                    materialization_status,
                    lifecycle_status,
                    storage_relpath,
                    content_hash,
                    size_bytes,
                    retention_class,
                    expires_at,
                    deleted_at,
                    deleted_by,
                    delete_reason,
                    storage_deleted_at,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "art://cleanup/pending-storage-delete.md",
                    "wf_cleanup",
                    "tkt_cleanup",
                    "node_cleanup",
                    "artifacts/cleanup/pending-storage-delete.md",
                    "MARKDOWN",
                    "text/markdown",
                    "MATERIALIZED",
                    "DELETED",
                    "artifacts/cleanup/pending-storage-delete.md",
                    "hash-pending-delete",
                    28,
                    "EPHEMERAL",
                    "2026-03-28T09:00:00+08:00",
                    "2026-03-28T09:10:00+08:00",
                    "emp_ops_1",
                    "Manual delete without storage cleanup.",
                    None,
                    "2026-03-28T09:00:00+08:00",
                ),
            )

        set_ticket_time("2026-03-28T10:31:00+08:00")
        dashboard_response = client.get("/api/v1/projections/dashboard")
        candidates_response = client.get("/api/v1/projections/artifact-cleanup-candidates?limit=10")

        assert submit_response.status_code == 200
        assert dashboard_response.status_code == 200
        assert candidates_response.status_code == 200
        artifact_maintenance = dashboard_response.json()["data"]["artifact_maintenance"]
        assert artifact_maintenance["ephemeral_default_ttl_sec"] == 60
        assert artifact_maintenance["retention_defaults"] == {
            "PERSISTENT": None,
            "REVIEW_EVIDENCE": 1800,
            "OPERATIONAL_EVIDENCE": 600,
            "EPHEMERAL": 60,
        }
        assert artifact_maintenance["legacy_unknown_retention_count"] == 1

        candidates = {
            item["artifact_ref"]: item for item in candidates_response.json()["data"]["artifacts"]
        }
        assert candidates["art://reports/homepage/cleanup-candidate.md"]["cleanup_reason"] == "EXPIRED_DUE"
        assert candidates["art://reports/homepage/cleanup-candidate.md"]["retention_class"] == (
            "REVIEW_EVIDENCE"
        )
        assert candidates["art://reports/homepage/cleanup-candidate.md"]["retention_class_source"] == (
            "PATH_DEFAULT"
        )
        assert candidates["art://reports/homepage/cleanup-candidate.md"]["retention_policy_source"] == (
            "CLASS_DEFAULT"
        )
        assert candidates["art://cleanup/pending-storage-delete.md"]["cleanup_reason"] == (
            "STORAGE_DELETE_PENDING"
        )


def test_ticket_create_moves_ticket_and_node_to_pending(client):
    response = client.post("/api/v1/commands/ticket-create", json=_ticket_create_payload())

    ticket_projection = client.app.state.repository.get_current_ticket_projection("tkt_visual_001")
    node_projection = client.app.state.repository.get_current_node_projection(
        "wf_seed",
        "node_homepage_visual",
    )

    assert response.status_code == 200
    assert response.json()["status"] == "ACCEPTED"
    assert response.json()["causation_hint"] == "ticket:tkt_visual_001"
    assert client.app.state.repository.count_events_by_type(EVENT_TICKET_CREATED) == 1
    assert ticket_projection["status"] == TICKET_STATUS_PENDING
    assert ticket_projection["priority"] == "high"
    assert ticket_projection["retry_budget"] == 2
    assert ticket_projection["timeout_sla_sec"] == 1800
    assert node_projection["status"] == NODE_STATUS_PENDING
    assert node_projection["latest_ticket_id"] == "tkt_visual_001"


def test_ticket_lease_moves_ticket_to_leased_and_keeps_node_pending(client, set_ticket_time):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    client.post("/api/v1/commands/ticket-create", json=_ticket_create_payload())

    response = client.post("/api/v1/commands/ticket-lease", json=_ticket_lease_payload())

    ticket_projection = client.app.state.repository.get_current_ticket_projection("tkt_visual_001")
    node_projection = client.app.state.repository.get_current_node_projection(
        "wf_seed",
        "node_homepage_visual",
    )

    assert response.status_code == 200
    assert response.json()["status"] == "ACCEPTED"
    assert client.app.state.repository.count_events_by_type(EVENT_TICKET_LEASED) == 1
    assert ticket_projection["status"] == TICKET_STATUS_LEASED
    assert ticket_projection["lease_owner"] == "emp_frontend_2"
    assert ticket_projection["lease_expires_at"].isoformat() == "2026-03-28T10:10:00+08:00"
    assert node_projection["status"] == NODE_STATUS_PENDING


def test_ticket_start_moves_ticket_and_node_to_executing(client, set_ticket_time):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    _create_and_lease_ticket(client)

    set_ticket_time("2026-03-28T10:05:00+08:00")
    response = client.post("/api/v1/commands/ticket-start", json=_ticket_start_payload())

    ticket_projection = client.app.state.repository.get_current_ticket_projection("tkt_visual_001")
    node_projection = client.app.state.repository.get_current_node_projection(
        "wf_seed",
        "node_homepage_visual",
    )

    assert response.status_code == 200
    assert response.json()["status"] == "ACCEPTED"
    assert client.app.state.repository.count_events_by_type(EVENT_TICKET_STARTED) == 1
    assert ticket_projection["status"] == TICKET_STATUS_EXECUTING
    assert ticket_projection["lease_owner"] == "emp_frontend_2"
    assert ticket_projection["started_at"].isoformat() == "2026-03-28T10:05:00+08:00"
    assert ticket_projection["last_heartbeat_at"].isoformat() == "2026-03-28T10:05:00+08:00"
    assert ticket_projection["heartbeat_timeout_sec"] == 600
    assert ticket_projection["heartbeat_expires_at"].isoformat() == "2026-03-28T10:15:00+08:00"
    assert ticket_projection["lease_expires_at"].isoformat() == "2026-03-28T10:10:00+08:00"
    assert node_projection["status"] == NODE_STATUS_EXECUTING


def test_worker_runtime_assignments_require_bootstrap_or_session_headers(client, set_ticket_time, monkeypatch):
    monkeypatch.setenv("BOARDROOM_OS_WORKER_BOOTSTRAP_SIGNING_SECRET", "bootstrap-secret")
    monkeypatch.setenv("BOARDROOM_OS_WORKER_SHARED_SECRET", "shared-secret")
    monkeypatch.setenv("BOARDROOM_OS_WORKER_SESSION_TTL_SEC", "600")
    set_ticket_time("2026-03-28T10:00:00+08:00")
    _create_and_lease_ticket(client)

    missing_headers = client.get("/api/v1/worker-runtime/assignments")
    legacy_shared_secret = client.get(
        "/api/v1/worker-runtime/assignments",
        headers=_worker_headers(),
    )
    bootstrap_response = client.get(
        "/api/v1/worker-runtime/assignments",
        headers=_worker_bootstrap_headers(),
    )
    session_response = client.get(
        "/api/v1/worker-runtime/assignments",
        headers=_worker_session_headers(bootstrap_response.json()["data"]["session_token"]),
    )

    assert missing_headers.status_code == 401
    assert legacy_shared_secret.status_code == 401
    assert bootstrap_response.status_code == 200
    assert session_response.status_code == 200


def test_worker_runtime_assignments_return_only_current_worker_tickets_and_signed_execution_urls(
    client,
    set_ticket_time,
    monkeypatch,
):
    monkeypatch.setenv("BOARDROOM_OS_WORKER_BOOTSTRAP_SIGNING_SECRET", "bootstrap-secret")
    monkeypatch.setenv("BOARDROOM_OS_WORKER_SESSION_TTL_SEC", "600")
    monkeypatch.setenv("BOARDROOM_OS_WORKER_DELIVERY_SIGNING_SECRET", "delivery-secret")
    monkeypatch.setenv("BOARDROOM_OS_PUBLIC_BASE_URL", "https://workers.boardroom.test")
    set_ticket_time("2026-03-28T10:00:00+08:00")
    _create_and_lease_ticket(
        client,
        workflow_id="wf_worker_runtime",
        ticket_id="tkt_worker_leased",
        node_id="node_worker_leased",
    )
    _create_lease_and_start_ticket(
        client,
        workflow_id="wf_worker_runtime",
        ticket_id="tkt_worker_executing",
        node_id="node_worker_executing",
    )
    _create_and_lease_ticket(
        client,
        workflow_id="wf_worker_runtime",
        ticket_id="tkt_other_worker",
        node_id="node_other_worker",
        leased_by="emp_checker_1",
        role_profile_ref="checker_primary",
    )
    client.post(
        "/api/v1/commands/ticket-create",
        json=_ticket_create_payload(
            workflow_id="wf_worker_runtime",
            ticket_id="tkt_pending_worker",
            node_id="node_pending_worker",
        ),
    )

    response = _worker_assignments_response(client)

    assert response.status_code == 200
    data = response.json()["data"]
    assignments = data["assignments"]
    assignment_ids = {item["ticket_id"] for item in assignments}
    assert assignment_ids == {"tkt_worker_leased", "tkt_worker_executing"}
    assert {item["status"] for item in assignments} == {"LEASED", "EXECUTING"}
    assert data["session_id"]
    assert data["session_token"]
    assert data["session_expires_at"] == "2026-03-28T10:10:00+08:00"
    assert all(
        item["execution_package_url"].startswith(
            "https://workers.boardroom.test/api/v1/worker-runtime/tickets/"
        )
        for item in assignments
    )
    assert all(item["delivery_expires_at"] == "2026-03-28T11:00:00+08:00" for item in assignments)
    assert all(_query_value(item["execution_package_url"], "access_token") for item in assignments)


def test_worker_runtime_assignments_accept_bootstrap_token_and_refresh_session(
    client,
    set_ticket_time,
    monkeypatch,
):
    monkeypatch.setenv("BOARDROOM_OS_WORKER_BOOTSTRAP_SIGNING_SECRET", "bootstrap-secret")
    monkeypatch.setenv("BOARDROOM_OS_WORKER_SESSION_TTL_SEC", "600")
    monkeypatch.setenv("BOARDROOM_OS_WORKER_DELIVERY_SIGNING_SECRET", "delivery-secret")
    set_ticket_time("2026-03-28T10:00:00+08:00")
    _create_and_lease_ticket(
        client,
        workflow_id="wf_worker_runtime",
        ticket_id="tkt_worker_bootstrap",
        node_id="node_worker_bootstrap",
    )

    bootstrap_response = client.get(
        "/api/v1/worker-runtime/assignments",
        headers=_worker_bootstrap_headers(),
    )

    assert bootstrap_response.status_code == 200
    bootstrap_data = bootstrap_response.json()["data"]
    assert bootstrap_data["worker_id"] == "emp_frontend_2"
    assert bootstrap_data["session_id"]
    assert bootstrap_data["session_token"]
    assert bootstrap_data["session_expires_at"] == "2026-03-28T10:10:00+08:00"

    set_ticket_time("2026-03-28T10:05:00+08:00")
    refreshed_response = client.get(
        "/api/v1/worker-runtime/assignments",
        headers=_worker_session_headers(bootstrap_data["session_token"]),
    )

    assert refreshed_response.status_code == 200
    refreshed_data = refreshed_response.json()["data"]
    assert refreshed_data["session_id"] == bootstrap_data["session_id"]
    assert refreshed_data["session_token"] != bootstrap_data["session_token"]
    assert refreshed_data["session_expires_at"] == "2026-03-28T10:15:00+08:00"


def test_worker_runtime_assignments_return_session_scope_fields(
    client,
    set_ticket_time,
    monkeypatch,
):
    monkeypatch.setenv("BOARDROOM_OS_WORKER_BOOTSTRAP_SIGNING_SECRET", "bootstrap-secret")
    monkeypatch.setenv("BOARDROOM_OS_WORKER_SESSION_TTL_SEC", "600")
    set_ticket_time("2026-03-28T10:00:00+08:00")
    _create_and_lease_ticket(
        client,
        workflow_id="wf_scope_runtime",
        ticket_id="tkt_scope_runtime",
        node_id="node_scope_runtime",
        tenant_id="tenant_scope",
        workspace_id="ws_scope",
    )

    response = _worker_assignments_response(
        client,
        tenant_id="tenant_scope",
        workspace_id="ws_scope",
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["tenant_id"] == "tenant_scope"
    assert data["workspace_id"] == "ws_scope"


def test_worker_runtime_assignments_isolate_scopes_for_same_worker(
    client,
    set_ticket_time,
    monkeypatch,
):
    monkeypatch.setenv("BOARDROOM_OS_WORKER_BOOTSTRAP_SIGNING_SECRET", "bootstrap-secret")
    monkeypatch.setenv("BOARDROOM_OS_WORKER_SESSION_TTL_SEC", "600")
    monkeypatch.setenv("BOARDROOM_OS_WORKER_DELIVERY_SIGNING_SECRET", "delivery-secret")
    set_ticket_time("2026-03-28T10:00:00+08:00")
    _create_and_lease_ticket(
        client,
        workflow_id="wf_scope_default",
        ticket_id="tkt_scope_default",
        node_id="node_scope_default",
        tenant_id="tenant_default",
        workspace_id="ws_default",
    )
    _create_and_lease_ticket(
        client,
        workflow_id="wf_scope_blue",
        ticket_id="tkt_scope_blue",
        node_id="node_scope_blue",
        tenant_id="tenant_blue",
        workspace_id="ws_design",
    )
    repository = client.app.state.repository
    with repository.transaction() as connection:
        repository.ensure_worker_bootstrap_state(
            connection,
            worker_id="emp_frontend_2",
            tenant_id="tenant_default",
            workspace_id="ws_default",
            at=datetime.fromisoformat("2026-03-28T10:00:00+08:00"),
        )
        repository.ensure_worker_bootstrap_state(
            connection,
            worker_id="emp_frontend_2",
            tenant_id="tenant_blue",
            workspace_id="ws_design",
            at=datetime.fromisoformat("2026-03-28T10:00:00+08:00"),
        )

    default_assignments = _worker_assignments_data(client)
    blue_assignments = _worker_assignments_data(
        client,
        tenant_id="tenant_blue",
        workspace_id="ws_design",
    )

    assert {item["ticket_id"] for item in default_assignments["assignments"]} == {
        "tkt_scope_default"
    }
    assert {item["ticket_id"] for item in blue_assignments["assignments"]} == {
        "tkt_scope_blue"
    }
    assert default_assignments["tenant_id"] == "tenant_default"
    assert default_assignments["workspace_id"] == "ws_default"
    assert blue_assignments["tenant_id"] == "tenant_blue"
    assert blue_assignments["workspace_id"] == "ws_design"


def test_worker_runtime_assignments_reject_ticket_scope_mismatch_and_log_it(
    client,
    set_ticket_time,
    monkeypatch,
):
    monkeypatch.setenv("BOARDROOM_OS_WORKER_BOOTSTRAP_SIGNING_SECRET", "bootstrap-secret")
    monkeypatch.setenv("BOARDROOM_OS_WORKER_SESSION_TTL_SEC", "600")
    set_ticket_time("2026-03-28T10:00:00+08:00")
    _create_and_lease_ticket(
        client,
        workflow_id="wf_scope_runtime",
        ticket_id="tkt_scope_mismatch",
        node_id="node_scope_mismatch",
        tenant_id="tenant_scope",
        workspace_id="ws_scope",
    )
    bootstrap_response = _worker_assignments_response(
        client,
        tenant_id="tenant_scope",
        workspace_id="ws_scope",
    )
    session_token = bootstrap_response.json()["data"]["session_token"]

    repository = client.app.state.repository
    with repository.transaction() as connection:
        connection.execute(
            """
            UPDATE ticket_projection
            SET workspace_id = ?
            WHERE ticket_id = ?
            """,
            ("ws_other", "tkt_scope_mismatch"),
        )

    response = client.get(
        "/api/v1/worker-runtime/assignments",
        headers=_worker_session_headers(session_token),
    )

    rejection_logs = _list_worker_auth_rejections(client)

    assert response.status_code == 403
    assert "workspace" in response.json()["detail"].lower()
    assert rejection_logs[-1]["route_family"] == "assignments"
    assert rejection_logs[-1]["reason_code"] == "workspace_mismatch"
    assert rejection_logs[-1]["ticket_id"] == "tkt_scope_mismatch"
    assert rejection_logs[-1]["tenant_id"] == "tenant_scope"
    assert rejection_logs[-1]["workspace_id"] == "ws_scope"


def test_worker_runtime_scope_specific_rotation_does_not_revoke_other_scope_session(
    client,
    set_ticket_time,
    monkeypatch,
):
    monkeypatch.setenv("BOARDROOM_OS_WORKER_BOOTSTRAP_SIGNING_SECRET", "bootstrap-secret")
    monkeypatch.setenv("BOARDROOM_OS_WORKER_SESSION_TTL_SEC", "600")
    set_ticket_time("2026-03-28T10:00:00+08:00")
    _create_and_lease_ticket(
        client,
        workflow_id="wf_scope_default",
        ticket_id="tkt_scope_default_rotation",
        node_id="node_scope_default_rotation",
        tenant_id="tenant_default",
        workspace_id="ws_default",
    )
    _create_and_lease_ticket(
        client,
        workflow_id="wf_scope_blue",
        ticket_id="tkt_scope_blue_rotation",
        node_id="node_scope_blue_rotation",
        tenant_id="tenant_blue",
        workspace_id="ws_design",
    )
    repository = client.app.state.repository
    with repository.transaction() as connection:
        repository.ensure_worker_bootstrap_state(
            connection,
            worker_id="emp_frontend_2",
            tenant_id="tenant_default",
            workspace_id="ws_default",
            at=datetime.fromisoformat("2026-03-28T10:00:00+08:00"),
        )
        repository.ensure_worker_bootstrap_state(
            connection,
            worker_id="emp_frontend_2",
            tenant_id="tenant_blue",
            workspace_id="ws_design",
            at=datetime.fromisoformat("2026-03-28T10:00:00+08:00"),
        )

    default_assignments = _worker_assignments_data(client)
    blue_assignments = _worker_assignments_data(
        client,
        tenant_id="tenant_blue",
        workspace_id="ws_design",
    )
    with repository.transaction() as connection:
        repository.rotate_worker_bootstrap_state(
            connection,
            worker_id="emp_frontend_2",
            tenant_id="tenant_default",
            workspace_id="ws_default",
            rotated_at=datetime.fromisoformat("2026-03-28T10:05:00+08:00"),
        )

    revoked_default_response = client.get(
        "/api/v1/worker-runtime/assignments",
        headers=_worker_session_headers(default_assignments["session_token"]),
    )
    surviving_blue_response = client.get(
        "/api/v1/worker-runtime/assignments",
        headers=_worker_session_headers(blue_assignments["session_token"]),
    )

    assert revoked_default_response.status_code == 401
    assert surviving_blue_response.status_code == 200
    assert {item["ticket_id"] for item in surviving_blue_response.json()["data"]["assignments"]} == {
        "tkt_scope_blue_rotation"
    }


def test_worker_runtime_revoked_session_rejects_assignments_and_signed_delivery(
    client,
    set_ticket_time,
    monkeypatch,
):
    monkeypatch.setenv("BOARDROOM_OS_WORKER_BOOTSTRAP_SIGNING_SECRET", "bootstrap-secret")
    monkeypatch.setenv("BOARDROOM_OS_WORKER_SESSION_TTL_SEC", "600")
    monkeypatch.setenv("BOARDROOM_OS_WORKER_DELIVERY_SIGNING_SECRET", "delivery-secret")
    monkeypatch.setenv("BOARDROOM_OS_PUBLIC_BASE_URL", "https://workers.boardroom.test")
    set_ticket_time("2026-03-28T10:00:00+08:00")
    _seed_input_artifact(client)
    _create_and_lease_ticket(
        client,
        workflow_id="wf_worker_runtime",
        ticket_id="tkt_worker_revoked_session",
        node_id="node_worker_revoked_session",
    )

    assignments_response = client.get(
        "/api/v1/worker-runtime/assignments",
        headers=_worker_bootstrap_headers(),
    )
    assignments_data = assignments_response.json()["data"]
    execution_package_url = assignments_data["assignments"][0]["execution_package_url"]
    execution_package_response = client.get(_local_path_from_url(execution_package_url))
    execution_package_data = execution_package_response.json()["data"]
    content_url = execution_package_data["compiled_execution_package"]["atomic_context_bundle"]["context_blocks"][0][
        "content_payload"
    ]["content_url"]
    ticket_start_url = execution_package_data["command_endpoints"]["ticket_start_url"]

    repository = client.app.state.repository
    with repository.transaction() as connection:
        connection.execute(
            """
            UPDATE worker_session
            SET revoked_at = ?
            WHERE session_id = ?
            """,
            ("2026-03-28T10:06:00+08:00", assignments_data["session_id"]),
        )

    assignments_after_revoke = client.get(
        "/api/v1/worker-runtime/assignments",
        headers=_worker_session_headers(assignments_data["session_token"]),
    )
    execution_after_revoke = client.get(_local_path_from_url(execution_package_url))
    artifact_after_revoke = client.get(_local_path_from_url(content_url))
    command_after_revoke = client.post(
        _local_path_from_url(ticket_start_url),
        json={
            "workflow_id": "wf_worker_runtime",
            "ticket_id": "tkt_worker_revoked_session",
            "node_id": "node_worker_revoked_session",
            "idempotency_key": "worker-runtime:start:tkt_worker_revoked_session",
        },
    )

    assert assignments_after_revoke.status_code == 401
    assert execution_after_revoke.status_code == 401
    assert artifact_after_revoke.status_code == 401
    assert command_after_revoke.status_code == 401


def test_worker_runtime_rotated_bootstrap_rejects_old_bootstrap_and_old_session(
    client,
    set_ticket_time,
    monkeypatch,
):
    monkeypatch.setenv("BOARDROOM_OS_WORKER_BOOTSTRAP_SIGNING_SECRET", "bootstrap-secret")
    monkeypatch.setenv("BOARDROOM_OS_WORKER_SESSION_TTL_SEC", "600")
    monkeypatch.setenv("BOARDROOM_OS_WORKER_DELIVERY_SIGNING_SECRET", "delivery-secret")
    set_ticket_time("2026-03-28T10:00:00+08:00")
    _create_and_lease_ticket(
        client,
        workflow_id="wf_worker_runtime",
        ticket_id="tkt_worker_rotated_bootstrap",
        node_id="node_worker_rotated_bootstrap",
    )

    initial_bootstrap_headers = _worker_bootstrap_headers()
    initial_response = client.get(
        "/api/v1/worker-runtime/assignments",
        headers=initial_bootstrap_headers,
    )
    initial_session_token = initial_response.json()["data"]["session_token"]

    repository = client.app.state.repository
    with repository.transaction() as connection:
        connection.execute(
            """
            UPDATE worker_bootstrap_state
            SET credential_version = 2,
                revoked_before = ?,
                rotated_at = ?,
                updated_at = ?
            WHERE worker_id = ?
            """,
            (
                "2026-03-28T10:05:00+08:00",
                "2026-03-28T10:05:00+08:00",
                "2026-03-28T10:05:00+08:00",
                "emp_frontend_2",
            ),
        )

    old_bootstrap_response = client.get(
        "/api/v1/worker-runtime/assignments",
        headers=initial_bootstrap_headers,
    )
    old_session_response = client.get(
        "/api/v1/worker-runtime/assignments",
        headers=_worker_session_headers(initial_session_token),
    )
    new_bootstrap_response = client.get(
        "/api/v1/worker-runtime/assignments",
        headers=_worker_bootstrap_headers(credential_version=2, issued_at="2026-03-28T10:05:00+08:00"),
    )

    assert old_bootstrap_response.status_code == 401
    assert old_session_response.status_code == 401
    assert new_bootstrap_response.status_code == 200


def test_worker_runtime_inactive_worker_cannot_bootstrap_or_use_session(
    client,
    set_ticket_time,
    monkeypatch,
):
    monkeypatch.setenv("BOARDROOM_OS_WORKER_BOOTSTRAP_SIGNING_SECRET", "bootstrap-secret")
    monkeypatch.setenv("BOARDROOM_OS_WORKER_SESSION_TTL_SEC", "600")
    monkeypatch.setenv("BOARDROOM_OS_WORKER_DELIVERY_SIGNING_SECRET", "delivery-secret")
    set_ticket_time("2026-03-28T10:00:00+08:00")
    _create_and_lease_ticket(
        client,
        workflow_id="wf_worker_runtime",
        ticket_id="tkt_worker_inactive",
        node_id="node_worker_inactive",
    )

    active_response = client.get(
        "/api/v1/worker-runtime/assignments",
        headers=_worker_bootstrap_headers(),
    )
    session_token = active_response.json()["data"]["session_token"]

    repository = client.app.state.repository
    with repository.transaction() as connection:
        connection.execute(
            """
            UPDATE employee_projection
            SET state = ?, updated_at = ?, version = version + 1
            WHERE employee_id = ?
            """,
            ("INACTIVE", "2026-03-28T10:06:00+08:00", "emp_frontend_2"),
        )

    bootstrap_after_deactivate = client.get(
        "/api/v1/worker-runtime/assignments",
        headers=_worker_bootstrap_headers(issued_at="2026-03-28T10:06:00+08:00"),
    )
    session_after_deactivate = client.get(
        "/api/v1/worker-runtime/assignments",
        headers=_worker_session_headers(session_token),
    )

    assert bootstrap_after_deactivate.status_code == 403
    assert session_after_deactivate.status_code == 403


def test_worker_runtime_execution_package_signed_url_allows_token_only_access_and_rewrites_signed_urls(
    client,
    set_ticket_time,
    monkeypatch,
):
    monkeypatch.setenv("BOARDROOM_OS_WORKER_BOOTSTRAP_SIGNING_SECRET", "bootstrap-secret")
    monkeypatch.setenv("BOARDROOM_OS_WORKER_SESSION_TTL_SEC", "600")
    monkeypatch.setenv("BOARDROOM_OS_WORKER_DELIVERY_SIGNING_SECRET", "delivery-secret")
    monkeypatch.setenv("BOARDROOM_OS_PUBLIC_BASE_URL", "https://workers.boardroom.test")
    set_ticket_time("2026-03-28T10:00:00+08:00")
    _seed_input_artifact(client)
    _create_and_lease_ticket(
        client,
        workflow_id="wf_worker_runtime",
        ticket_id="tkt_worker_package",
        node_id="node_worker_package",
    )

    assignments_data = _worker_assignments_data(client)
    execution_package_url = assignments_data["assignments"][0]["execution_package_url"]
    first_response = client.get(_local_path_from_url(execution_package_url))
    second_response = client.get(_local_path_from_url(execution_package_url))

    repository = client.app.state.repository
    latest_execution_package = repository.get_latest_compiled_execution_package_by_ticket(
        "tkt_worker_package"
    )

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert latest_execution_package is not None
    first_body = first_response.json()["data"]
    second_body = second_response.json()["data"]
    content_payload = first_body["compiled_execution_package"]["atomic_context_bundle"]["context_blocks"][0][
        "content_payload"
    ]
    assert first_body["ticket_id"] == "tkt_worker_package"
    assert first_body["compile_request_id"] == latest_execution_package["compile_request_id"]
    assert first_body["compile_request_id"] == second_body["compile_request_id"]
    assert first_body["delivery_expires_at"] == "2026-03-28T11:00:00+08:00"
    assert first_body["output_schema_body"]["required"] == [
        "summary",
        "recommended_option_id",
        "options",
    ]
    assert first_body["compiled_execution_package"]["org_context"]["upstream_provider"] is None
    assert (
        first_body["compiled_execution_package"]["org_context"]["downstream_reviewer"]["role_profile_ref"]
        == "checker_primary"
    )
    assert (
        first_body["compiled_execution_package"]["rendered_execution_payload"]["messages"][0]["content_payload"][
            "organization_context"
        ]
        == first_body["compiled_execution_package"]["org_context"]
    )
    assert (
        first_body["compiled_execution_package"]["execution"]["output_schema_ref"]
        == "ui_milestone_review"
    )
    assert first_body["compiled_execution_package"]["meta"]["governance_profile_ref"].startswith("gp_")
    assert first_body["compiled_execution_package"]["governance_mode_slice"]["approval_mode"] == "AUTO_CEO"
    assert first_body["compiled_execution_package"]["governance_mode_slice"]["audit_mode"] == "MINIMAL"
    assert first_body["compiled_execution_package"]["task_frame"]["task_category"] == "review"
    assert first_body["compiled_execution_package"]["required_doc_surfaces"] == []
    assert (
        first_body["compiled_execution_package"]["context_layer_summary"]["w0_constitution"]["governance_profile_ref"]
        == first_body["compiled_execution_package"]["meta"]["governance_profile_ref"]
    )
    assert content_payload["content_url"].startswith(
        "https://workers.boardroom.test/api/v1/worker-runtime/artifacts/content"
    )
    assert content_payload["preview_url"].startswith(
        "https://workers.boardroom.test/api/v1/worker-runtime/artifacts/preview"
    )
    assert content_payload["download_url"].startswith(
        "https://workers.boardroom.test/api/v1/worker-runtime/artifacts/content"
    )
    assert _query_value(content_payload["content_url"], "access_token")
    assert _query_value(content_payload["preview_url"], "access_token")
    assert _query_value(content_payload["download_url"], "access_token")
    assert _query_value(content_payload["content_url"], "access_token") != _query_value(
        content_payload["preview_url"], "access_token"
    )
    assert _query_value(content_payload["content_url"], "access_token") != _query_value(
        content_payload["download_url"], "access_token"
    )
    assert first_body["command_endpoints"]["ticket_start_url"].startswith(
        "https://workers.boardroom.test/api/v1/worker-runtime/commands/ticket-start"
    )
    assert _query_value(first_body["command_endpoints"]["ticket_start_url"], "access_token")
    grants = _list_worker_delivery_grants(client)
    assert len(grants) >= 8
    assert any(grant["scope"] == "execution_package" for grant in grants)
    assert {
        grant["artifact_action"]
        for grant in grants
        if grant["scope"] == "artifact_read"
    } == {"content_inline", "content_attachment", "preview"}
    artifact_content_response = client.get(_local_path_from_url(content_payload["content_url"]))
    assert artifact_content_response.status_code == 200
    assert "# Brief" in artifact_content_response.text


def test_worker_runtime_execution_package_inlines_materialized_text_input_and_keeps_signed_urls(
    client,
    set_ticket_time,
    monkeypatch,
):
    monkeypatch.setenv("BOARDROOM_OS_WORKER_BOOTSTRAP_SIGNING_SECRET", "bootstrap-secret")
    monkeypatch.setenv("BOARDROOM_OS_WORKER_SESSION_TTL_SEC", "600")
    monkeypatch.setenv("BOARDROOM_OS_WORKER_DELIVERY_SIGNING_SECRET", "delivery-secret")
    monkeypatch.setenv("BOARDROOM_OS_PUBLIC_BASE_URL", "https://workers.boardroom.test")
    set_ticket_time("2026-03-28T10:00:00+08:00")
    _ensure_runtime_provider_ready_for_ticket(
        client,
        role_profile_ref="frontend_engineer_primary",
        output_schema_ref="ui_milestone_review",
    )
    _seed_input_artifact(content="# Brief\n\nInline package body.\n", client=client)
    create_response = client.post(
        "/api/v1/commands/ticket-create",
        json={
            **_ticket_create_payload(
                workflow_id="wf_worker_runtime_inline",
                ticket_id="tkt_worker_inline",
                node_id="node_worker_inline",
            ),
            "input_artifact_refs": ["art://inputs/brief.md"],
            "idempotency_key": "ticket-create:wf_worker_runtime_inline:tkt_worker_inline",
        },
    )
    assert create_response.status_code == 200
    _ensure_default_governance_profile(client, workflow_id="wf_worker_runtime_inline")
    lease_response = client.post(
        "/api/v1/commands/ticket-lease",
        json=_ticket_lease_payload(
            workflow_id="wf_worker_runtime_inline",
            ticket_id="tkt_worker_inline",
            node_id="node_worker_inline",
        ),
    )
    assert lease_response.status_code == 200

    assignments_data = _worker_assignments_data(client)
    execution_package_url = assignments_data["assignments"][0]["execution_package_url"]
    execution_package = client.get(_local_path_from_url(execution_package_url)).json()["data"]
    context_payload = execution_package["compiled_execution_package"]["atomic_context_bundle"]["context_blocks"][0]

    assert context_payload["content_type"] == "TEXT"
    assert context_payload["content_payload"]["content_text"] == "# Brief\n\nInline package body.\n"
    assert context_payload["content_payload"]["artifact_access"]["artifact_ref"] == "art://inputs/brief.md"
    assert context_payload["content_payload"]["content_url"].startswith(
        "https://workers.boardroom.test/api/v1/worker-runtime/artifacts/content"
    )
    assert context_payload["content_payload"]["preview_url"].startswith(
        "https://workers.boardroom.test/api/v1/worker-runtime/artifacts/preview"
    )


def test_worker_runtime_execution_package_keeps_binary_artifact_kind_and_preview_kind(
    client,
    set_ticket_time,
    monkeypatch,
):
    monkeypatch.setenv("BOARDROOM_OS_WORKER_BOOTSTRAP_SIGNING_SECRET", "bootstrap-secret")
    monkeypatch.setenv("BOARDROOM_OS_WORKER_SESSION_TTL_SEC", "600")
    monkeypatch.setenv("BOARDROOM_OS_WORKER_DELIVERY_SIGNING_SECRET", "delivery-secret")
    monkeypatch.setenv("BOARDROOM_OS_PUBLIC_BASE_URL", "https://workers.boardroom.test")
    set_ticket_time("2026-03-28T10:00:00+08:00")
    _ensure_runtime_provider_ready_for_ticket(
        client,
        role_profile_ref="frontend_engineer_primary",
        output_schema_ref="ui_milestone_review",
    )
    _seed_input_artifact(
        client=client,
        artifact_ref="art://inputs/mock.png",
        logical_path="artifacts/inputs/mock.png",
        content_bytes=b"\x89PNG\r\n\x1a\nmock-image",
        kind="IMAGE",
        media_type="image/png",
    )
    create_response = client.post(
        "/api/v1/commands/ticket-create",
        json={
            **_ticket_create_payload(
                workflow_id="wf_worker_runtime_binary",
                ticket_id="tkt_worker_binary",
                node_id="node_worker_binary",
            ),
            "input_artifact_refs": ["art://inputs/mock.png"],
            "idempotency_key": "ticket-create:wf_worker_runtime_binary:tkt_worker_binary",
        },
    )
    assert create_response.status_code == 200
    _ensure_default_governance_profile(client, workflow_id="wf_worker_runtime_binary")
    lease_response = client.post(
        "/api/v1/commands/ticket-lease",
        json=_ticket_lease_payload(
            workflow_id="wf_worker_runtime_binary",
            ticket_id="tkt_worker_binary",
            node_id="node_worker_binary",
        ),
    )
    assert lease_response.status_code == 200

    assignments_data = _worker_assignments_data(client)
    execution_package_url = assignments_data["assignments"][0]["execution_package_url"]
    execution_package = client.get(_local_path_from_url(execution_package_url)).json()["data"]
    context_payload = execution_package["compiled_execution_package"]["atomic_context_bundle"]["context_blocks"][0]
    artifact_access = context_payload["content_payload"]["artifact_access"]

    assert context_payload["content_type"] == "SOURCE_DESCRIPTOR"
    assert context_payload["content_mode"] == "REFERENCE_ONLY"
    assert context_payload["degradation_reason_code"] == "MEDIA_REFERENCE_ONLY"
    assert context_payload["content_payload"]["display_hint"] == "OPEN_PREVIEW_URL"
    assert artifact_access["kind"] == "IMAGE"
    assert artifact_access["preview_kind"] == "INLINE_MEDIA"
    assert artifact_access["display_hint"] == "OPEN_PREVIEW_URL"
    assert context_payload["content_payload"]["content_url"].startswith(
        "https://workers.boardroom.test/api/v1/worker-runtime/artifacts/content"
    )
    assert context_payload["content_payload"]["preview_url"].startswith(
        "https://workers.boardroom.test/api/v1/worker-runtime/artifacts/preview"
    )


def test_worker_runtime_execution_package_exposes_fragment_selector_and_metadata(
    client,
    set_ticket_time,
    monkeypatch,
):
    monkeypatch.setenv("BOARDROOM_OS_WORKER_BOOTSTRAP_SIGNING_SECRET", "bootstrap-secret")
    monkeypatch.setenv("BOARDROOM_OS_WORKER_SESSION_TTL_SEC", "600")
    monkeypatch.setenv("BOARDROOM_OS_WORKER_DELIVERY_SIGNING_SECRET", "delivery-secret")
    monkeypatch.setenv("BOARDROOM_OS_PUBLIC_BASE_URL", "https://workers.boardroom.test")
    set_ticket_time("2026-03-28T10:00:00+08:00")
    _ensure_runtime_provider_ready_for_ticket(
        client,
        role_profile_ref="frontend_engineer_primary",
        output_schema_ref="ui_milestone_review",
    )
    _seed_input_artifact(
        client=client,
        artifact_ref="art://inputs/brief.md",
        logical_path="artifacts/inputs/brief.md",
        content=(
            "# Intro\n\n"
            + ("This introduction is intentionally verbose and non-actionable. " * 20)
            + "\n\n## Acceptance Contract\n\n"
            "This section defines the output contract, review path, and risk reminders.\n\n"
            "## Delivery Notes\n\nShip the homepage option with explicit review evidence.\n"
        ),
    )
    create_response = client.post(
        "/api/v1/commands/ticket-create",
        json={
            **_ticket_create_payload(
                workflow_id="wf_worker_runtime_fragment",
                ticket_id="tkt_worker_fragment",
                node_id="node_worker_fragment",
            ),
            "input_artifact_refs": ["art://inputs/brief.md"],
            "context_query_plan": {
                "keywords": ["acceptance", "output", "review"],
                "semantic_queries": ["contract risk"],
                "max_context_tokens": 500,
            },
            "idempotency_key": "ticket-create:wf_worker_runtime_fragment:tkt_worker_fragment",
        },
    )
    assert create_response.status_code == 200
    _ensure_default_governance_profile(client, workflow_id="wf_worker_runtime_fragment")
    lease_response = client.post(
        "/api/v1/commands/ticket-lease",
        json=_ticket_lease_payload(
            workflow_id="wf_worker_runtime_fragment",
            ticket_id="tkt_worker_fragment",
            node_id="node_worker_fragment",
        ),
    )
    assert lease_response.status_code == 200

    assignments_data = _worker_assignments_data(client)
    execution_package_url = assignments_data["assignments"][0]["execution_package_url"]
    execution_package = client.get(_local_path_from_url(execution_package_url)).json()["data"]
    context_payload = execution_package["compiled_execution_package"]["atomic_context_bundle"]["context_blocks"][0]

    assert context_payload["content_mode"] == "INLINE_FRAGMENT"
    assert context_payload["selector"]["selector_type"] == "MARKDOWN_SECTION"
    assert "Acceptance Contract" in context_payload["selector"]["selector_value"]
    assert context_payload["content_payload"]["content_fragment_strategy"] == "MARKDOWN_SECTION_MATCH"
    assert context_payload["content_payload"]["selected_sections"] == [
        "Acceptance Contract",
        "Delivery Notes",
    ]


def test_worker_runtime_execution_package_exposes_rendered_execution_payload(
    client,
    set_ticket_time,
    monkeypatch,
):
    monkeypatch.setenv("BOARDROOM_OS_WORKER_BOOTSTRAP_SIGNING_SECRET", "bootstrap-secret")
    monkeypatch.setenv("BOARDROOM_OS_WORKER_SESSION_TTL_SEC", "600")
    monkeypatch.setenv("BOARDROOM_OS_WORKER_DELIVERY_SIGNING_SECRET", "delivery-secret")
    monkeypatch.setenv("BOARDROOM_OS_PUBLIC_BASE_URL", "https://workers.boardroom.test")
    set_ticket_time("2026-03-28T10:00:00+08:00")
    _seed_input_artifact(content="# Brief\n\nRendered payload body.\n", client=client)
    _create_and_lease_ticket(
        client,
        workflow_id="wf_worker_runtime_rendered",
        ticket_id="tkt_worker_rendered",
        node_id="node_worker_rendered",
    )

    assignments_data = _worker_assignments_data(client)
    execution_package_url = assignments_data["assignments"][0]["execution_package_url"]
    execution_package = client.get(_local_path_from_url(execution_package_url)).json()["data"]
    rendered_payload = execution_package["rendered_execution_payload"]

    assert rendered_payload == execution_package["compiled_execution_package"]["rendered_execution_payload"]
    assert rendered_payload["meta"]["render_target"] == "json_messages_v1"
    assert rendered_payload["messages"][0]["channel"] == "SYSTEM_CONTROLS"
    assert rendered_payload["messages"][1]["channel"] == "TASK_DEFINITION"
    assert rendered_payload["messages"][-1]["channel"] == "OUTPUT_CONTRACT_REMINDER"
    assert rendered_payload["summary"]["control_message_count"] == 3
    assert rendered_payload["summary"]["data_message_count"] == len(
        execution_package["compiled_execution_package"]["atomic_context_bundle"]["context_blocks"]
    )


def test_worker_runtime_execution_package_rejects_legacy_header_fallback(
    client,
    set_ticket_time,
    monkeypatch,
):
    monkeypatch.setenv("BOARDROOM_OS_WORKER_BOOTSTRAP_SIGNING_SECRET", "bootstrap-secret")
    monkeypatch.setenv("BOARDROOM_OS_WORKER_SHARED_SECRET", "shared-secret")
    set_ticket_time("2026-03-28T10:00:00+08:00")
    _create_and_lease_ticket(
        client,
        workflow_id="wf_worker_runtime",
        ticket_id="tkt_worker_owned",
        node_id="node_worker_owned",
    )

    response = client.get(
        "/api/v1/worker-runtime/tickets/tkt_worker_owned/execution-package",
        headers=_worker_headers(),
    )

    assert response.status_code == 401


def test_worker_runtime_artifact_routes_return_worker_scoped_metadata_and_content(
    client,
    set_ticket_time,
    monkeypatch,
):
    monkeypatch.setenv("BOARDROOM_OS_WORKER_BOOTSTRAP_SIGNING_SECRET", "bootstrap-secret")
    monkeypatch.setenv("BOARDROOM_OS_WORKER_DELIVERY_SIGNING_SECRET", "delivery-secret")
    set_ticket_time("2026-03-28T10:00:00+08:00")
    _seed_input_artifact(client)
    _create_and_lease_ticket(
        client,
        workflow_id="wf_worker_runtime",
        ticket_id="tkt_worker_artifact",
        node_id="node_worker_artifact",
    )

    assignments_data = _worker_assignments_data(client)
    execution_package_url = assignments_data["assignments"][0]["execution_package_url"]
    execution_package_response = client.get(_local_path_from_url(execution_package_url))
    execution_package_data = execution_package_response.json()["data"]
    artifact_payload = _worker_artifact_payloads(execution_package_data)["art://inputs/brief.md"]
    artifact_token = _query_value(artifact_payload["content_url"], "access_token")

    metadata_response = client.get(
        "/api/v1/worker-runtime/artifacts/by-ref",
        params={
            "artifact_ref": "art://inputs/brief.md",
            "ticket_id": "tkt_worker_artifact",
            "access_token": artifact_token,
        },
    )
    preview_response = client.get(_local_path_from_url(artifact_payload["preview_url"]))
    content_response = client.get(_local_path_from_url(artifact_payload["content_url"]))

    assert metadata_response.status_code == 200
    assert preview_response.status_code == 200
    assert content_response.status_code == 200
    assert metadata_response.json()["data"]["content_url"].startswith(
        "http://testserver/api/v1/worker-runtime/artifacts/content"
    )
    assert metadata_response.json()["data"]["preview_url"].startswith(
        "http://testserver/api/v1/worker-runtime/artifacts/preview"
    )
    assert preview_response.json()["data"]["preview_kind"] == "TEXT"
    assert "# Brief" in preview_response.json()["data"]["text_content"]
    assert "# Brief" in content_response.text


def test_worker_runtime_artifact_routes_preserve_registered_only_and_deleted_behavior(
    client,
    set_ticket_time,
    monkeypatch,
):
    monkeypatch.setenv("BOARDROOM_OS_WORKER_BOOTSTRAP_SIGNING_SECRET", "bootstrap-secret")
    monkeypatch.setenv("BOARDROOM_OS_WORKER_DELIVERY_SIGNING_SECRET", "delivery-secret")
    set_ticket_time("2026-03-28T10:00:00+08:00")
    _ensure_runtime_provider_ready_for_ticket(
        client,
        role_profile_ref="frontend_engineer_primary",
        output_schema_ref="ui_milestone_review",
    )
    client.post(
        "/api/v1/commands/ticket-create",
        json={
            **_ticket_create_payload(
                workflow_id="wf_worker_runtime",
                ticket_id="tkt_worker_artifact_states",
                node_id="node_worker_artifact_states",
            ),
            "input_artifact_refs": ["art://inputs/registered.md", "art://inputs/deleted.md"],
        },
    )
    _ensure_default_governance_profile(client, workflow_id="wf_worker_runtime")
    client.post(
        "/api/v1/commands/ticket-lease",
        json=_ticket_lease_payload(
            workflow_id="wf_worker_runtime",
            ticket_id="tkt_worker_artifact_states",
            node_id="node_worker_artifact_states",
        ),
    )
    _seed_input_artifact(
        client,
        artifact_ref="art://inputs/registered.md",
        logical_path="artifacts/inputs/registered.md",
        materialization_status="REGISTERED_ONLY",
    )
    _seed_input_artifact(
        client,
        artifact_ref="art://inputs/deleted.md",
        logical_path="artifacts/inputs/deleted.md",
        lifecycle_status="DELETED",
        deleted_at="2026-03-28T10:05:00+08:00",
        deleted_by="emp_ops_1",
        delete_reason="Removed before worker pickup.",
    )

    assignments_data = _worker_assignments_data(client)
    execution_package_url = assignments_data["assignments"][0]["execution_package_url"]
    execution_package_response = client.get(_local_path_from_url(execution_package_url))
    artifact_payloads = _worker_artifact_payloads(execution_package_response.json()["data"])
    registered_token = _query_value(
        artifact_payloads["art://inputs/registered.md"]["content_url"],
        "access_token",
    )
    registered_metadata = client.get(
        "/api/v1/worker-runtime/artifacts/by-ref",
        params={
            "artifact_ref": "art://inputs/registered.md",
            "ticket_id": "tkt_worker_artifact_states",
            "access_token": registered_token,
        },
    )
    registered_content = client.get(
        _local_path_from_url(artifact_payloads["art://inputs/registered.md"]["content_url"])
    )
    deleted_content = client.get(
        _local_path_from_url(artifact_payloads["art://inputs/deleted.md"]["content_url"])
    )

    assert registered_metadata.status_code == 200
    assert registered_metadata.json()["data"]["materialization_status"] == "REGISTERED_ONLY"
    assert registered_content.status_code == 409
    assert deleted_content.status_code == 410


def test_worker_runtime_signed_command_urls_allow_token_only_writeback(
    client,
    set_ticket_time,
    monkeypatch,
):
    monkeypatch.setenv("BOARDROOM_OS_WORKER_BOOTSTRAP_SIGNING_SECRET", "bootstrap-secret")
    monkeypatch.setenv("BOARDROOM_OS_WORKER_DELIVERY_SIGNING_SECRET", "delivery-secret")
    monkeypatch.setenv("BOARDROOM_OS_PUBLIC_BASE_URL", "https://workers.boardroom.test")
    set_ticket_time("2026-03-28T10:00:00+08:00")
    _create_and_lease_ticket(
        client,
        workflow_id="wf_worker_runtime",
        ticket_id="tkt_worker_token_result",
        node_id="node_worker_token_result",
    )

    assignments_data = _worker_assignments_data(client)
    execution_package_url = assignments_data["assignments"][0]["execution_package_url"]
    execution_package_response = client.get(_local_path_from_url(execution_package_url))
    command_endpoints = execution_package_response.json()["data"]["command_endpoints"]

    start_response = client.post(
        _local_path_from_url(command_endpoints["ticket_start_url"]),
        json={
            "workflow_id": "wf_worker_runtime",
            "ticket_id": "tkt_worker_token_result",
            "node_id": "node_worker_token_result",
            "idempotency_key": "worker-runtime:start:tkt_worker_token_result",
        },
    )
    heartbeat_response = client.post(
        _local_path_from_url(command_endpoints["ticket_heartbeat_url"]),
        json={
            "workflow_id": "wf_worker_runtime",
            "ticket_id": "tkt_worker_token_result",
            "node_id": "node_worker_token_result",
            "idempotency_key": "worker-runtime:heartbeat:tkt_worker_token_result",
        },
    )
    create_upload_response = client.post(
        "/api/v1/artifact-uploads/sessions",
        json={
            "filename": "runtime-bundle.zip",
            "media_type": "application/zip",
        },
    )
    upload_session_id = create_upload_response.json()["data"]["session_id"]
    client.put(
        f"/api/v1/artifact-uploads/sessions/{upload_session_id}/parts/1",
        content=b"worker-runtime-bundle",
        headers={"content-type": "application/octet-stream"},
    )
    client.post(f"/api/v1/artifact-uploads/sessions/{upload_session_id}/complete")
    import_response = client.post(
        _local_path_from_url(command_endpoints["ticket_artifact_import_upload_url"]),
        json={
            "workflow_id": "wf_worker_runtime",
            "ticket_id": "tkt_worker_token_result",
            "node_id": "node_worker_token_result",
            "artifact_ref": "art://worker/runtime-bundle.zip",
            "path": "artifacts/ui/homepage/runtime-bundle.zip",
            "kind": "BINARY",
            "media_type": "application/zip",
            "upload_session_id": upload_session_id,
            "idempotency_key": "worker-runtime:import-upload:tkt_worker_token_result",
        },
    )
    result_payload = _ticket_result_submit_payload(
        workflow_id="wf_worker_runtime",
        ticket_id="tkt_worker_token_result",
        node_id="node_worker_token_result",
        artifact_refs=[
            "art://worker/runtime-token-option-a.json",
            "art://worker/runtime-bundle.zip",
        ],
        payload={
            "summary": "Worker runtime produced a structured result through signed command URLs.",
            "recommended_option_id": "option_a",
            "options": [
                {
                    "option_id": "option_a",
                    "label": "Option A",
                    "summary": "Single structured worker option.",
                    "artifact_refs": [
                        "art://worker/runtime-token-option-a.json",
                        "art://worker/runtime-bundle.zip",
                    ],
                }
            ],
        },
        written_artifacts=[
            {
                "path": "artifacts/ui/homepage/runtime-token-option-a.json",
                "artifact_ref": "art://worker/runtime-token-option-a.json",
                "kind": "JSON",
                "content_json": {
                    "option_id": "option_a",
                    "headline": "Worker generated artifact through signed URL.",
                },
            }
        ],
        idempotency_key="worker-runtime:result:tkt_worker_token_result",
    )
    result_payload.pop("submitted_by")
    result_response = client.post(
        _local_path_from_url(command_endpoints["ticket_result_submit_url"]),
        json=result_payload,
    )

    repository = client.app.state.repository
    ticket_projection = repository.get_current_ticket_projection("tkt_worker_token_result")
    artifact_record = repository.get_artifact_by_ref("art://worker/runtime-token-option-a.json")
    uploaded_artifact = repository.get_artifact_by_ref("art://worker/runtime-bundle.zip")

    assert start_response.status_code == 200
    assert heartbeat_response.status_code == 200
    assert create_upload_response.status_code == 200
    assert import_response.status_code == 200
    assert result_response.status_code == 200
    assert ticket_projection["status"] == TICKET_STATUS_COMPLETED
    assert artifact_record is not None
    assert artifact_record["materialization_status"] == "MATERIALIZED"
    assert uploaded_artifact is not None
    assert uploaded_artifact["materialization_status"] == "MATERIALIZED"


def test_worker_runtime_delivery_routes_reject_workspace_mismatch_and_log_it(
    client,
    set_ticket_time,
    monkeypatch,
):
    monkeypatch.setenv("BOARDROOM_OS_WORKER_BOOTSTRAP_SIGNING_SECRET", "bootstrap-secret")
    monkeypatch.setenv("BOARDROOM_OS_WORKER_DELIVERY_SIGNING_SECRET", "delivery-secret")
    set_ticket_time("2026-03-28T10:00:00+08:00")
    workflow_id = "wf_delivery_scope"
    _ensure_scoped_workflow(
        client,
        workflow_id=workflow_id,
        tenant_id="tenant_scope",
        workspace_id="ws_scope",
        goal="Delivery scope workflow",
    )
    _seed_input_artifact(client)
    _create_and_lease_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_delivery_scope",
        node_id="node_delivery_scope",
        tenant_id="tenant_scope",
        workspace_id="ws_scope",
    )

    assignments_data = _worker_assignments_data(
        client,
        tenant_id="tenant_scope",
        workspace_id="ws_scope",
    )
    execution_package_url = assignments_data["assignments"][0]["execution_package_url"]
    execution_package_response = client.get(_local_path_from_url(execution_package_url))
    execution_package_data = execution_package_response.json()["data"]
    artifact_payload = _worker_artifact_payloads(execution_package_data)["art://inputs/brief.md"]
    command_url = execution_package_data["command_endpoints"]["ticket_start_url"]

    repository = client.app.state.repository
    with repository.transaction() as connection:
        connection.execute(
            """
            UPDATE workflow_projection
            SET workspace_id = ?
            WHERE workflow_id = ?
            """,
            ("ws_other", workflow_id),
        )

    rejected_execution = client.get(_local_path_from_url(execution_package_url))
    rejected_artifact = client.get(_local_path_from_url(artifact_payload["content_url"]))
    rejected_command = client.post(
        _local_path_from_url(command_url),
        json={
            "workflow_id": workflow_id,
            "ticket_id": "tkt_delivery_scope",
            "node_id": "node_delivery_scope",
            "idempotency_key": "worker-runtime:start:tkt_delivery_scope",
        },
    )

    rejection_logs = _list_worker_auth_rejections(client)

    assert rejected_execution.status_code == 403
    assert rejected_artifact.status_code == 403
    assert rejected_command.status_code == 403
    assert {log["route_family"] for log in rejection_logs[-3:]} == {
        "execution_package",
        "artifact_read",
        "command",
    }
    assert all(log["reason_code"] == "workspace_mismatch" for log in rejection_logs[-3:])


def test_worker_runtime_signed_execution_package_url_rejects_expired_token(
    client,
    set_ticket_time,
    monkeypatch,
):
    monkeypatch.setenv("BOARDROOM_OS_WORKER_BOOTSTRAP_SIGNING_SECRET", "bootstrap-secret")
    monkeypatch.setenv("BOARDROOM_OS_WORKER_DELIVERY_SIGNING_SECRET", "delivery-secret")
    monkeypatch.setenv("BOARDROOM_OS_WORKER_DELIVERY_TOKEN_TTL_SEC", "60")
    set_ticket_time("2026-03-28T10:00:00+08:00")
    _create_and_lease_ticket(
        client,
        workflow_id="wf_worker_runtime",
        ticket_id="tkt_worker_expired_token",
        node_id="node_worker_expired_token",
    )

    assignments_data = _worker_assignments_data(client)
    execution_package_url = assignments_data["assignments"][0]["execution_package_url"]
    set_ticket_time("2026-03-28T10:02:00+08:00")

    response = client.get(_local_path_from_url(execution_package_url))

    assert response.status_code == 401
    assert "expired" in response.json()["detail"].lower()


def test_worker_runtime_signed_artifact_url_rejects_tampered_token(
    client,
    set_ticket_time,
    monkeypatch,
):
    monkeypatch.setenv("BOARDROOM_OS_WORKER_BOOTSTRAP_SIGNING_SECRET", "bootstrap-secret")
    monkeypatch.setenv("BOARDROOM_OS_WORKER_DELIVERY_SIGNING_SECRET", "delivery-secret")
    set_ticket_time("2026-03-28T10:00:00+08:00")
    _seed_input_artifact(client)
    _create_and_lease_ticket(
        client,
        workflow_id="wf_worker_runtime",
        ticket_id="tkt_worker_tampered_artifact",
        node_id="node_worker_tampered_artifact",
    )

    assignments_data = _worker_assignments_data(client)
    execution_package_url = assignments_data["assignments"][0]["execution_package_url"]
    execution_package_response = client.get(_local_path_from_url(execution_package_url))
    content_url = execution_package_response.json()["data"]["compiled_execution_package"]["atomic_context_bundle"][
        "context_blocks"
    ][0]["content_payload"]["content_url"]
    original_token = _query_value(content_url, "access_token")
    assert original_token is not None
    payload_segment, signature_segment = original_token.split(".", 1)
    replacement_char = "a" if signature_segment[0] != "a" else "b"
    tampered_url = _replace_query_value(
        content_url,
        "access_token",
        f"{payload_segment}.{replacement_char}{signature_segment[1:]}",
    )

    response = client.get(_local_path_from_url(tampered_url))

    assert response.status_code == 401
    assert "invalid" in response.json()["detail"].lower()


def test_worker_runtime_signed_artifact_url_rejects_artifact_scope_mismatch(
    client,
    set_ticket_time,
    monkeypatch,
):
    monkeypatch.setenv("BOARDROOM_OS_WORKER_BOOTSTRAP_SIGNING_SECRET", "bootstrap-secret")
    monkeypatch.setenv("BOARDROOM_OS_WORKER_DELIVERY_SIGNING_SECRET", "delivery-secret")
    set_ticket_time("2026-03-28T10:00:00+08:00")
    _ensure_runtime_provider_ready_for_ticket(
        client,
        role_profile_ref="frontend_engineer_primary",
        output_schema_ref="ui_milestone_review",
    )
    _seed_input_artifact(client, artifact_ref="art://inputs/brief.md", logical_path="artifacts/inputs/brief.md")
    _seed_input_artifact(
        client,
        artifact_ref="art://inputs/brand-guide.md",
        logical_path="artifacts/inputs/brand-guide.md",
        content="# Brand Guide\n\nMaterialized input.\n",
    )
    client.post(
        "/api/v1/commands/ticket-create",
        json={
            **_ticket_create_payload(
                workflow_id="wf_worker_runtime",
                ticket_id="tkt_worker_scope_mismatch",
                node_id="node_worker_scope_mismatch",
            ),
            "input_artifact_refs": ["art://inputs/brief.md", "art://inputs/brand-guide.md"],
        },
    )
    _ensure_default_governance_profile(client, workflow_id="wf_worker_runtime")
    client.post(
        "/api/v1/commands/ticket-lease",
        json=_ticket_lease_payload(
            workflow_id="wf_worker_runtime",
            ticket_id="tkt_worker_scope_mismatch",
            node_id="node_worker_scope_mismatch",
        ),
    )

    assignments_data = _worker_assignments_data(client)
    execution_package_url = assignments_data["assignments"][0]["execution_package_url"]
    execution_package_response = client.get(_local_path_from_url(execution_package_url))
    content_url = execution_package_response.json()["data"]["compiled_execution_package"]["atomic_context_bundle"][
        "context_blocks"
    ][0]["content_payload"]["content_url"]
    swapped_url = _replace_query_value(content_url, "artifact_ref", "art://inputs/brand-guide.md")

    response = client.get(_local_path_from_url(swapped_url))

    assert response.status_code == 403


def test_worker_runtime_signed_command_url_rejects_command_scope_mismatch(
    client,
    set_ticket_time,
    monkeypatch,
):
    monkeypatch.setenv("BOARDROOM_OS_WORKER_BOOTSTRAP_SIGNING_SECRET", "bootstrap-secret")
    monkeypatch.setenv("BOARDROOM_OS_WORKER_DELIVERY_SIGNING_SECRET", "delivery-secret")
    set_ticket_time("2026-03-28T10:00:00+08:00")
    _create_and_lease_ticket(
        client,
        workflow_id="wf_worker_runtime",
        ticket_id="tkt_worker_wrong_command",
        node_id="node_worker_wrong_command",
    )

    assignments_data = _worker_assignments_data(client)
    execution_package_url = assignments_data["assignments"][0]["execution_package_url"]
    execution_package_response = client.get(_local_path_from_url(execution_package_url))
    command_endpoints = execution_package_response.json()["data"]["command_endpoints"]
    wrong_route = _local_path_from_url(command_endpoints["ticket_start_url"]).replace(
        "/ticket-start?",
        "/ticket-heartbeat?",
    )

    response = client.post(
        wrong_route,
        json={
            "workflow_id": "wf_worker_runtime",
            "ticket_id": "tkt_worker_wrong_command",
            "node_id": "node_worker_wrong_command",
            "idempotency_key": "worker-runtime:heartbeat:tkt_worker_wrong_command",
        },
    )

    assert response.status_code == 403


def test_worker_runtime_signed_execution_package_url_rejects_previous_worker_after_reassignment(
    client,
    set_ticket_time,
    monkeypatch,
):
    monkeypatch.setenv("BOARDROOM_OS_WORKER_BOOTSTRAP_SIGNING_SECRET", "bootstrap-secret")
    monkeypatch.setenv("BOARDROOM_OS_WORKER_DELIVERY_SIGNING_SECRET", "delivery-secret")
    set_ticket_time("2026-03-28T10:00:00+08:00")
    _create_and_lease_ticket(
        client,
        workflow_id="wf_worker_runtime",
        ticket_id="tkt_worker_reassigned",
        node_id="node_worker_reassigned",
    )

    assignments_data = _worker_assignments_data(client)
    execution_package_url = assignments_data["assignments"][0]["execution_package_url"]

    set_ticket_time("2026-03-28T10:11:00+08:00")
    client.post(
        "/api/v1/commands/ticket-lease",
        json={
            **_ticket_lease_payload(
                workflow_id="wf_worker_runtime",
                ticket_id="tkt_worker_reassigned",
                node_id="node_worker_reassigned",
                leased_by="emp_checker_1",
            ),
            "idempotency_key": "ticket-lease:wf_worker_runtime:tkt_worker_reassigned:emp_checker_1",
        },
    )

    response = client.get(_local_path_from_url(execution_package_url))

    assert response.status_code == 403


def test_worker_runtime_command_routes_reject_legacy_header_fallback(
    client,
    set_ticket_time,
    monkeypatch,
):
    monkeypatch.setenv("BOARDROOM_OS_WORKER_BOOTSTRAP_SIGNING_SECRET", "bootstrap-secret")
    monkeypatch.setenv("BOARDROOM_OS_WORKER_SHARED_SECRET", "shared-secret")
    set_ticket_time("2026-03-28T10:00:00+08:00")
    _create_and_lease_ticket(
        client,
        workflow_id="wf_worker_runtime",
        ticket_id="tkt_worker_result",
        node_id="node_worker_result",
    )

    start_response = client.post(
        "/api/v1/worker-runtime/commands/ticket-start",
        json={
            "workflow_id": "wf_worker_runtime",
            "ticket_id": "tkt_worker_result",
            "node_id": "node_worker_result",
            "idempotency_key": "worker-runtime:start:tkt_worker_result",
        },
        headers=_worker_headers(),
    )
    heartbeat_response = client.post(
        "/api/v1/worker-runtime/commands/ticket-heartbeat",
        json={
            "workflow_id": "wf_worker_runtime",
            "ticket_id": "tkt_worker_result",
            "node_id": "node_worker_result",
            "idempotency_key": "worker-runtime:heartbeat:tkt_worker_result",
        },
        headers=_worker_headers(),
    )
    result_payload = _ticket_result_submit_payload(
        workflow_id="wf_worker_runtime",
        ticket_id="tkt_worker_result",
        node_id="node_worker_result",
        artifact_refs=["art://worker/runtime-option-a.json"],
        payload={
            "summary": "Worker runtime produced a structured result.",
            "recommended_option_id": "option_a",
            "options": [
                {
                    "option_id": "option_a",
                    "label": "Option A",
                    "summary": "Single structured worker option.",
                    "artifact_refs": ["art://worker/runtime-option-a.json"],
                }
            ],
        },
        written_artifacts=[
            {
                "path": "artifacts/ui/homepage/runtime-option-a.json",
                "artifact_ref": "art://worker/runtime-option-a.json",
                "kind": "JSON",
                "content_json": {
                    "option_id": "option_a",
                    "headline": "Worker generated artifact.",
                },
            }
        ],
        idempotency_key="worker-runtime:result:tkt_worker_result",
    )
    result_payload.pop("submitted_by")
    result_response = client.post(
        "/api/v1/worker-runtime/commands/ticket-result-submit",
        json=result_payload,
        headers=_worker_headers(),
    )

    assert start_response.status_code == 401
    assert heartbeat_response.status_code == 401
    assert result_response.status_code == 401


def test_worker_runtime_revoking_one_artifact_grant_only_invalidates_target_url(
    client,
    set_ticket_time,
    monkeypatch,
):
    monkeypatch.setenv("BOARDROOM_OS_WORKER_BOOTSTRAP_SIGNING_SECRET", "bootstrap-secret")
    monkeypatch.setenv("BOARDROOM_OS_WORKER_SESSION_TTL_SEC", "600")
    monkeypatch.setenv("BOARDROOM_OS_WORKER_DELIVERY_SIGNING_SECRET", "delivery-secret")
    set_ticket_time("2026-03-28T10:00:00+08:00")
    _seed_input_artifact(client)
    _create_and_lease_ticket(
        client,
        workflow_id="wf_worker_runtime",
        ticket_id="tkt_worker_single_revoke",
        node_id="node_worker_single_revoke",
    )

    assignments_data = _worker_assignments_data(client)
    execution_package_url = assignments_data["assignments"][0]["execution_package_url"]
    execution_package_response = client.get(_local_path_from_url(execution_package_url))
    execution_package_data = execution_package_response.json()["data"]
    artifact_payload = _worker_artifact_payloads(execution_package_data)["art://inputs/brief.md"]
    preview_url = artifact_payload["preview_url"]
    content_url = artifact_payload["content_url"]
    download_url = artifact_payload["download_url"]
    preview_grant_id = _decode_worker_delivery_token_payload(
        _query_value(preview_url, "access_token") or ""
    )["grant_id"]

    _revoke_worker_delivery_grant(client, grant_id=preview_grant_id)

    preview_response = client.get(_local_path_from_url(preview_url))
    content_response = client.get(_local_path_from_url(content_url))
    download_response = client.get(_local_path_from_url(download_url))
    refreshed_assignments = client.get(
        "/api/v1/worker-runtime/assignments",
        headers=_worker_session_headers(assignments_data["session_token"]),
    )

    assert preview_response.status_code == 401
    assert content_response.status_code == 200
    assert download_response.status_code == 200
    assert refreshed_assignments.status_code == 200


def test_worker_runtime_result_submit_preserves_schema_validation_path(
    client,
    set_ticket_time,
    monkeypatch,
):
    monkeypatch.setenv("BOARDROOM_OS_WORKER_BOOTSTRAP_SIGNING_SECRET", "bootstrap-secret")
    monkeypatch.setenv("BOARDROOM_OS_WORKER_DELIVERY_SIGNING_SECRET", "delivery-secret")
    set_ticket_time("2026-03-28T10:00:00+08:00")
    _create_lease_and_start_ticket(
        client,
        workflow_id="wf_worker_runtime",
        ticket_id="tkt_worker_schema_error",
        node_id="node_worker_schema_error",
        retry_budget=2,
    )

    assignments_data = _worker_assignments_data(client)
    execution_package_url = assignments_data["assignments"][0]["execution_package_url"]
    execution_package_response = client.get(_local_path_from_url(execution_package_url))
    result_submit_url = execution_package_response.json()["data"]["command_endpoints"][
        "ticket_result_submit_url"
    ]
    result_payload = _ticket_result_submit_payload(
        workflow_id="wf_worker_runtime",
        ticket_id="tkt_worker_schema_error",
        node_id="node_worker_schema_error",
        payload={
            "summary": "Worker runtime omitted options.",
            "recommended_option_id": "option_a",
        },
        idempotency_key="worker-runtime:result:schema-error",
    )
    result_payload.pop("submitted_by")
    response = client.post(
        _local_path_from_url(result_submit_url),
        json=result_payload,
    )

    repository = client.app.state.repository
    failed_events = [
        event for event in repository.list_events_for_testing() if event["event_type"] == EVENT_TICKET_FAILED
    ]

    assert response.status_code == 200
    assert response.json()["status"] == "ACCEPTED"
    assert failed_events[-1]["payload"]["failure_kind"] == "SCHEMA_ERROR"


def test_inbox_projection_returns_empty_items(client):
    response = client.get("/api/v1/projections/inbox")

    assert response.status_code == 200
    assert response.json()["data"]["items"] == []


def test_ticket_start_is_rejected_before_ticket_create(client):
    response = client.post("/api/v1/commands/ticket-start", json=_ticket_start_payload())

    assert response.status_code == 200
    assert response.json()["status"] == "REJECTED"
    assert "created" in response.json()["reason"].lower()


def test_ticket_start_is_rejected_before_ticket_lease(client):
    client.post("/api/v1/commands/ticket-create", json=_ticket_create_payload())

    response = client.post("/api/v1/commands/ticket-start", json=_ticket_start_payload())

    assert response.status_code == 200
    assert response.json()["status"] == "REJECTED"
    assert "LEASED" in response.json()["reason"]


def test_ticket_complete_is_rejected_before_ticket_start(client):
    client.post("/api/v1/commands/ticket-create", json=_ticket_create_payload())

    response = client.post(
        "/api/v1/commands/ticket-complete",
        json=_ticket_complete_payload(include_review_request=False),
    )

    assert response.status_code == 200
    assert response.json()["status"] == "REJECTED"
    assert "PENDING" in response.json()["reason"]


def test_ticket_create_lease_and_start_are_idempotent(client, set_ticket_time):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    first_create = client.post("/api/v1/commands/ticket-create", json=_ticket_create_payload())
    duplicate_create = client.post("/api/v1/commands/ticket-create", json=_ticket_create_payload())
    first_lease = client.post("/api/v1/commands/ticket-lease", json=_ticket_lease_payload())
    duplicate_lease = client.post("/api/v1/commands/ticket-lease", json=_ticket_lease_payload())
    set_ticket_time("2026-03-28T10:05:00+08:00")
    first_start = client.post("/api/v1/commands/ticket-start", json=_ticket_start_payload())
    duplicate_start = client.post("/api/v1/commands/ticket-start", json=_ticket_start_payload())

    assert first_create.json()["status"] == "ACCEPTED"
    assert duplicate_create.json()["status"] == "DUPLICATE"
    assert first_lease.json()["status"] == "ACCEPTED"
    assert duplicate_lease.json()["status"] == "DUPLICATE"
    assert first_start.json()["status"] == "ACCEPTED"
    assert duplicate_start.json()["status"] == "DUPLICATE"


def test_ticket_start_is_rejected_when_lease_owner_differs(client, set_ticket_time):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    _create_and_lease_ticket(client, leased_by="emp_checker_1")

    set_ticket_time("2026-03-28T10:05:00+08:00")
    response = client.post(
        "/api/v1/commands/ticket-start",
        json=_ticket_start_payload(started_by="emp_frontend_2"),
    )

    assert response.status_code == 200
    assert response.json()["status"] == "REJECTED"
    assert "leased by emp_checker_1" in response.json()["reason"]


def test_ticket_start_is_rejected_when_lease_has_expired(client, set_ticket_time):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    _create_and_lease_ticket(client, lease_timeout_sec=60)

    set_ticket_time("2026-03-28T10:02:00+08:00")
    response = client.post("/api/v1/commands/ticket-start", json=_ticket_start_payload())

    assert response.status_code == 200
    assert response.json()["status"] == "REJECTED"
    assert "expired" in response.json()["reason"].lower()


def test_ticket_start_rejects_stale_projection_version_guard(client, set_ticket_time):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    _create_and_lease_ticket(client)
    repository = client.app.state.repository
    ticket_projection = repository.get_current_ticket_projection("tkt_visual_001")
    node_projection = repository.get_current_node_projection("wf_seed", "node_homepage_visual")
    assert ticket_projection is not None
    assert node_projection is not None

    set_ticket_time("2026-03-28T10:05:00+08:00")
    response = client.post(
        "/api/v1/commands/ticket-start",
        json=_ticket_start_payload(
            expected_ticket_version=int(ticket_projection["version"]) - 1,
            expected_node_version=int(node_projection["version"]),
        ),
    )

    assert response.status_code == 200
    assert response.json()["status"] == "REJECTED"
    assert "outdated" in response.json()["reason"].lower()


def test_ticket_heartbeat_refreshes_executing_ticket(client, set_ticket_time):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    _create_lease_and_start_ticket(client)

    set_ticket_time("2026-03-28T10:09:00+08:00")
    response = client.post("/api/v1/commands/ticket-heartbeat", json=_ticket_heartbeat_payload())
    ticket_projection = client.app.state.repository.get_current_ticket_projection("tkt_visual_001")

    assert response.status_code == 200
    assert response.json()["status"] == "ACCEPTED"
    assert client.app.state.repository.count_events_by_type(EVENT_TICKET_HEARTBEAT_RECORDED) == 1
    assert ticket_projection["status"] == TICKET_STATUS_EXECUTING
    assert ticket_projection["started_at"].isoformat() == "2026-03-28T10:00:00+08:00"
    assert ticket_projection["last_heartbeat_at"].isoformat() == "2026-03-28T10:09:00+08:00"
    assert ticket_projection["heartbeat_expires_at"].isoformat() == "2026-03-28T10:19:00+08:00"


def test_ticket_heartbeat_is_rejected_before_ticket_start(client, set_ticket_time):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    _create_and_lease_ticket(client)

    response = client.post("/api/v1/commands/ticket-heartbeat", json=_ticket_heartbeat_payload())

    assert response.status_code == 200
    assert response.json()["status"] == "REJECTED"
    assert "EXECUTING" in response.json()["reason"]


def test_ticket_heartbeat_is_rejected_when_owner_differs(client, set_ticket_time):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    _create_lease_and_start_ticket(client, leased_by="emp_checker_1", role_profile_ref="checker_primary")

    set_ticket_time("2026-03-28T10:05:00+08:00")
    response = client.post(
        "/api/v1/commands/ticket-heartbeat",
        json=_ticket_heartbeat_payload(reported_by="emp_frontend_2"),
    )

    assert response.status_code == 200
    assert response.json()["status"] == "REJECTED"
    assert "leased by emp_checker_1" in response.json()["reason"]


def test_ticket_heartbeat_is_rejected_when_window_has_expired(client, set_ticket_time):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    _create_lease_and_start_ticket(client, lease_timeout_sec=60)

    set_ticket_time("2026-03-28T10:02:00+08:00")
    response = client.post("/api/v1/commands/ticket-heartbeat", json=_ticket_heartbeat_payload())

    assert response.status_code == 200
    assert response.json()["status"] == "REJECTED"
    assert "heartbeat" in response.json()["reason"].lower()
    assert "expired" in response.json()["reason"].lower()


def test_ticket_heartbeat_is_idempotent(client, set_ticket_time):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    _create_lease_and_start_ticket(client)

    set_ticket_time("2026-03-28T10:05:00+08:00")
    first = client.post("/api/v1/commands/ticket-heartbeat", json=_ticket_heartbeat_payload())
    duplicate = client.post("/api/v1/commands/ticket-heartbeat", json=_ticket_heartbeat_payload())

    assert first.status_code == 200
    assert first.json()["status"] == "ACCEPTED"
    assert duplicate.status_code == 200
    assert duplicate.json()["status"] == "DUPLICATE"


def test_ticket_lease_is_rejected_for_non_latest_ticket(client, set_ticket_time):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    client.post("/api/v1/commands/ticket-create", json=_ticket_create_payload(ticket_id="tkt_visual_001"))
    repository = client.app.state.repository
    with repository.transaction() as connection:
        connection.execute(
            """
            UPDATE node_projection
            SET latest_ticket_id = ?
            WHERE workflow_id = ? AND node_id = ?
            """,
            ("tkt_visual_002", "wf_seed", "node_homepage_visual"),
        )

    response = client.post(
        "/api/v1/commands/ticket-lease",
        json=_ticket_lease_payload(ticket_id="tkt_visual_001"),
    )

    assert response.status_code == 200
    assert response.json()["status"] == "REJECTED"
    assert "no longer points" in response.json()["reason"].lower()


def test_ticket_lease_is_rejected_when_active_lease_belongs_to_other_owner(client, set_ticket_time):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    _create_and_lease_ticket(client, leased_by="emp_checker_1", lease_timeout_sec=600)

    set_ticket_time("2026-03-28T10:05:00+08:00")
    response = client.post(
        "/api/v1/commands/ticket-lease",
        json=_ticket_lease_payload(leased_by="emp_frontend_2"),
    )

    assert response.status_code == 200
    assert response.json()["status"] == "REJECTED"
    assert "currently leased by emp_checker_1" in response.json()["reason"]


def test_ticket_lease_can_be_reclaimed_after_expiry(client, set_ticket_time):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    _create_and_lease_ticket(client, leased_by="emp_checker_1", lease_timeout_sec=60)

    set_ticket_time("2026-03-28T10:02:00+08:00")
    response = client.post(
        "/api/v1/commands/ticket-lease",
        json=_ticket_lease_payload(leased_by="emp_frontend_2"),
    )
    ticket_projection = client.app.state.repository.get_current_ticket_projection("tkt_visual_001")

    assert response.status_code == 200
    assert response.json()["status"] == "ACCEPTED"
    assert client.app.state.repository.count_events_by_type(EVENT_TICKET_LEASED) == 2
    assert ticket_projection["status"] == TICKET_STATUS_LEASED
    assert ticket_projection["lease_owner"] == "emp_frontend_2"
    assert ticket_projection["lease_expires_at"].isoformat() == "2026-03-28T10:12:00+08:00"


def test_ticket_complete_without_review_request_does_not_open_approval(client, set_ticket_time):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    _create_lease_and_start_ticket(client)
    response = client.post(
        "/api/v1/commands/ticket-complete",
        json=_ticket_complete_payload(include_review_request=False),
    )
    ticket_projection = client.app.state.repository.get_current_ticket_projection("tkt_visual_001")
    node_projection = client.app.state.repository.get_current_node_projection(
        "wf_seed",
        "node_homepage_visual",
    )

    assert response.status_code == 200
    assert response.json()["status"] == "ACCEPTED"
    assert response.json()["causation_hint"] == "ticket:tkt_visual_001"
    assert client.app.state.repository.count_events_by_type(EVENT_TICKET_COMPLETED) == 1
    assert client.app.state.repository.count_events_by_type(EVENT_BOARD_REVIEW_REQUIRED) == 0
    assert client.app.state.repository.list_open_approvals() == []
    assert ticket_projection["status"] == TICKET_STATUS_COMPLETED
    assert node_projection["status"] == NODE_STATUS_COMPLETED


def test_ticket_result_submit_completes_ticket_with_validated_structured_payload(client, set_ticket_time):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    _create_lease_and_start_ticket(client)

    response = client.post(
        "/api/v1/commands/ticket-result-submit",
        json=_ticket_result_submit_payload(),
    )

    repository = client.app.state.repository
    ticket_projection = repository.get_current_ticket_projection("tkt_visual_001")
    node_projection = repository.get_current_node_projection("wf_seed", "node_homepage_visual")

    assert response.status_code == 200
    assert response.json()["status"] == "ACCEPTED"
    assert ticket_projection["status"] == TICKET_STATUS_COMPLETED


def test_ticket_result_submit_rejects_stale_compiled_execution_package_version_ref(client, set_ticket_time):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    _create_lease_and_start_ticket(client)
    repository = client.app.state.repository
    ticket = repository.get_current_ticket_projection("tkt_visual_001")
    assert ticket is not None

    first = compile_and_persist_execution_artifacts(repository, ticket)
    set_ticket_time("2026-03-28T10:05:00+08:00")
    second = compile_and_persist_execution_artifacts(repository, ticket)

    stale_response = client.post(
        "/api/v1/commands/ticket-result-submit",
        json=_ticket_result_submit_payload(
            compile_request_id=first.compiled_execution_package.meta.compile_request_id,
            compiled_execution_package_version_ref=first.compiled_execution_package.meta.version_ref,
            idempotency_key="ticket-result-submit:wf_seed:tkt_visual_001:stale-execution-package",
        ),
    )

    assert stale_response.status_code == 200
    assert stale_response.json()["status"] == "REJECTED"
    assert "compiled execution package" in stale_response.json()["reason"].lower()

    fresh_response = client.post(
        "/api/v1/commands/ticket-result-submit",
        json=_ticket_result_submit_payload(
            compile_request_id=second.compiled_execution_package.meta.compile_request_id,
            compiled_execution_package_version_ref=second.compiled_execution_package.meta.version_ref,
            idempotency_key="ticket-result-submit:wf_seed:tkt_visual_001:fresh-execution-package",
        ),
    )

    assert fresh_response.status_code == 200
    assert fresh_response.json()["status"] == "ACCEPTED"
    node_projection = repository.get_current_node_projection("wf_seed", "node_homepage_visual")
    assert node_projection is not None
    assert node_projection["status"] == NODE_STATUS_COMPLETED


def test_ticket_result_submit_rejects_stale_runtime_node_projection_version(client, set_ticket_time):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    _ensure_scoped_workflow(
        client,
        workflow_id="wf_seed",
        tenant_id="tenant_default",
        workspace_id="ws_default",
        goal="Ticket result submit should reject stale runtime node projection versions.",
    )
    _create_lease_and_start_ticket(client)
    repository = client.app.state.repository
    ticket = repository.get_current_ticket_projection("tkt_visual_001")
    assert ticket is not None

    compiled = compile_and_persist_execution_artifacts(repository, ticket)

    with repository.transaction() as connection:
        connection.execute(
            """
            UPDATE runtime_node_projection
            SET version = version + 1
            WHERE workflow_id = ? AND graph_node_id = ?
            """,
            ("wf_seed", "node_homepage_visual"),
        )

    response = client.post(
        "/api/v1/commands/ticket-result-submit",
        json=_ticket_result_submit_payload(
            compile_request_id=compiled.compiled_execution_package.meta.compile_request_id,
            compiled_execution_package_version_ref=compiled.compiled_execution_package.meta.version_ref,
            idempotency_key="ticket-result-submit:wf_seed:tkt_visual_001:stale-runtime-node-version",
        ),
    )

    assert response.status_code == 200
    assert response.json()["status"] == "REJECTED"
    assert "runtime node version" in response.json()["reason"].lower()


def test_ticket_result_submit_materializes_json_artifacts_and_exposes_ticket_artifacts_projection(
    client,
    set_ticket_time,
):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    _create_lease_and_start_ticket(client)
    artifact_refs = ["art://homepage/option-a.json", "art://homepage/option-b.json"]

    response = client.post(
        "/api/v1/commands/ticket-result-submit",
        json=_ticket_result_submit_payload(
            artifact_refs=artifact_refs,
            payload={
                "summary": "Homepage visual milestone is ready for downstream review.",
                "recommended_option_id": "option_a",
                "options": [
                    {
                        "option_id": "option_a",
                        "label": "Option A",
                        "summary": "Structured review artifact for option A.",
                        "artifact_refs": ["art://homepage/option-a.json"],
                    },
                    {
                        "option_id": "option_b",
                        "label": "Option B",
                        "summary": "Structured review artifact for option B.",
                        "artifact_refs": ["art://homepage/option-b.json"],
                    },
                ],
            },
            written_artifacts=[
                {
                    "path": "artifacts/ui/homepage/option-a.json",
                    "artifact_ref": "art://homepage/option-a.json",
                    "kind": "JSON",
                    "content_json": {
                        "option_id": "option_a",
                        "headline": "Primary structured review artifact.",
                    },
                },
                {
                    "path": "artifacts/ui/homepage/option-b.json",
                    "artifact_ref": "art://homepage/option-b.json",
                    "kind": "JSON",
                    "content_json": {
                        "option_id": "option_b",
                        "headline": "Fallback structured review artifact.",
                    },
                },
            ],
            idempotency_key="ticket-result-submit:wf_seed:tkt_visual_001:json-artifacts",
        ),
    )

    repository = client.app.state.repository
    artifact_store = client.app.state.artifact_store
    indexed_artifacts = repository.list_ticket_artifacts("tkt_visual_001")
    indexed_by_ref = {item["artifact_ref"]: item for item in indexed_artifacts}
    stored_option_a = indexed_by_ref["art://homepage/option-a.json"]
    artifacts_response = client.get("/api/v1/projections/tickets/tkt_visual_001/artifacts")
    projected_by_ref = {
        item["artifact_ref"]: item for item in artifacts_response.json()["data"]["artifacts"]
    }

    assert response.status_code == 200
    assert response.json()["status"] == "ACCEPTED"
    assert len(indexed_artifacts) == 2
    assert stored_option_a["materialization_status"] == "MATERIALIZED"
    assert stored_option_a["storage_relpath"] is not None
    assert stored_option_a["content_hash"]
    assert stored_option_a["size_bytes"] > 0
    assert (artifact_store.root / stored_option_a["storage_relpath"]).exists()
    assert json.loads((artifact_store.root / stored_option_a["storage_relpath"]).read_text(encoding="utf-8")) == {
        "headline": "Primary structured review artifact.",
        "option_id": "option_a",
    }
    assert artifacts_response.status_code == 200
    assert projected_by_ref["art://homepage/option-a.json"]["status"] == "MATERIALIZED"
    assert projected_by_ref["art://homepage/option-a.json"]["materialization_status"] == "MATERIALIZED"
    assert projected_by_ref["art://homepage/option-a.json"]["lifecycle_status"] == "ACTIVE"
    assert projected_by_ref["art://homepage/option-a.json"]["path"] == "artifacts/ui/homepage/option-a.json"
    assert projected_by_ref["art://homepage/option-a.json"]["content_url"]
    assert projected_by_ref["art://homepage/option-a.json"]["download_url"]
    assert projected_by_ref["art://homepage/option-a.json"]["preview_url"]


def test_runtime_default_result_artifacts_use_review_evidence_retention(client, set_ticket_time):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    client.post("/api/v1/commands/ticket-create", json=_ticket_create_payload())

    from app.scheduler_runner import run_scheduler_once

    response = run_scheduler_once(
        client.app.state.repository,
        idempotency_key="scheduler-runner:runtime-default-retention",
        max_dispatches=1,
    )

    repository = client.app.state.repository
    indexed_artifacts = repository.list_ticket_artifacts("tkt_visual_001")
    indexed_by_ref = {item["artifact_ref"]: item for item in indexed_artifacts}

    assert response.status.value == "ACCEPTED"
    assert indexed_by_ref["art://runtime/tkt_visual_001/option-a.json"]["retention_class"] == (
        "REVIEW_EVIDENCE"
    )
    assert indexed_by_ref["art://runtime/tkt_visual_001/option-b.json"]["retention_class"] == (
        "REVIEW_EVIDENCE"
    )


def test_ticket_result_submit_materializes_markdown_artifacts(client, set_ticket_time):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    _create_lease_and_start_ticket(client)
    artifact_ref = "art://reports/homepage/review-summary.md"

    response = client.post(
        "/api/v1/commands/ticket-result-submit",
        json=_ticket_result_submit_payload(
            artifact_refs=[artifact_ref],
            payload={
                "summary": "Homepage review package includes a markdown summary artifact.",
                "recommended_option_id": "option_a",
                "options": [
                    {
                        "option_id": "option_a",
                        "label": "Option A",
                        "summary": "Review summary is attached as markdown.",
                        "artifact_refs": [artifact_ref],
                    }
                ],
            },
            written_artifacts=[
                {
                    "path": "reports/review/homepage-summary.md",
                    "artifact_ref": artifact_ref,
                    "kind": "MARKDOWN",
                    "content_text": "# Homepage Review\n\n- Keep stronger hero hierarchy.\n",
                }
            ],
            idempotency_key="ticket-result-submit:wf_seed:tkt_visual_001:markdown-artifact",
        ),
    )

    repository = client.app.state.repository
    artifact_store = client.app.state.artifact_store
    indexed_artifact = repository.get_artifact_by_ref(artifact_ref)

    assert response.status_code == 200
    assert response.json()["status"] == "ACCEPTED"
    assert indexed_artifact is not None
    assert indexed_artifact["materialization_status"] == "MATERIALIZED"
    assert indexed_artifact["media_type"] == "text/markdown"
    assert (artifact_store.root / indexed_artifact["storage_relpath"]).read_text(encoding="utf-8") == (
        "# Homepage Review\n\n- Keep stronger hero hierarchy.\n"
    )


def test_ticket_result_submit_registers_binary_artifacts_without_materializing_them(client, set_ticket_time):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    _create_lease_and_start_ticket(client)

    response = client.post(
        "/api/v1/commands/ticket-result-submit",
        json=_ticket_result_submit_payload(
            idempotency_key="ticket-result-submit:wf_seed:tkt_visual_001:registered-only-images",
        ),
    )

    repository = client.app.state.repository
    indexed_artifacts = repository.list_ticket_artifacts("tkt_visual_001")
    artifacts_response = client.get("/api/v1/projections/tickets/tkt_visual_001/artifacts")

    assert response.status_code == 200
    assert response.json()["status"] == "ACCEPTED"
    assert indexed_artifacts
    assert all(item["materialization_status"] == "REGISTERED_ONLY" for item in indexed_artifacts)
    assert all(item["storage_relpath"] is None for item in indexed_artifacts)
    assert all(item["status"] == "REGISTERED_ONLY" for item in artifacts_response.json()["data"]["artifacts"])

    metadata_response = client.get(
        "/api/v1/artifacts/by-ref",
        params={"artifact_ref": "art://homepage/option-a.png"},
    )
    content_response = client.get(
        "/api/v1/artifacts/content",
        params={"artifact_ref": "art://homepage/option-a.png", "disposition": "inline"},
    )

    assert metadata_response.status_code == 200
    assert metadata_response.json()["data"]["materialization_status"] == "REGISTERED_ONLY"
    assert metadata_response.json()["data"]["lifecycle_status"] == "ACTIVE"
    assert content_response.status_code == 409


def test_ticket_result_submit_materializes_binary_image_and_exposes_read_endpoints(client, set_ticket_time):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    _create_lease_and_start_ticket(client)
    image_bytes = b"\x89PNG\r\n\x1a\nbinary-homepage-image"
    artifact_ref = "art://homepage/mockup.png"

    response = client.post(
        "/api/v1/commands/ticket-result-submit",
        json=_ticket_result_submit_payload(
            artifact_refs=[artifact_ref],
            payload={
                "summary": "Homepage mockup image is attached as a materialized artifact.",
                "recommended_option_id": "option_a",
                "options": [
                    {
                        "option_id": "option_a",
                        "label": "Option A",
                        "summary": "Uses the uploaded mockup image.",
                        "artifact_refs": [artifact_ref],
                    }
                ],
            },
            written_artifacts=[
                {
                    "path": "artifacts/ui/homepage/mockup.png",
                    "artifact_ref": artifact_ref,
                    "kind": "IMAGE",
                    "media_type": "image/png",
                    "content_base64": _encode_base64(image_bytes),
                }
            ],
            idempotency_key="ticket-result-submit:wf_seed:tkt_visual_001:binary-image",
        ),
    )

    repository = client.app.state.repository
    artifact_store = client.app.state.artifact_store
    indexed_artifact = repository.get_artifact_by_ref(artifact_ref)
    metadata_response = client.get("/api/v1/artifacts/by-ref", params={"artifact_ref": artifact_ref})
    content_response = client.get(
        "/api/v1/artifacts/content",
        params={"artifact_ref": artifact_ref, "disposition": "inline"},
    )
    preview_response = client.get("/api/v1/artifacts/preview", params={"artifact_ref": artifact_ref})
    projection_response = client.get("/api/v1/projections/tickets/tkt_visual_001/artifacts")
    projected_artifact = projection_response.json()["data"]["artifacts"][0]

    assert response.status_code == 200
    assert response.json()["status"] == "ACCEPTED"
    assert indexed_artifact is not None
    assert indexed_artifact["materialization_status"] == "MATERIALIZED"
    assert indexed_artifact["lifecycle_status"] == "ACTIVE"
    assert indexed_artifact["media_type"] == "image/png"
    assert indexed_artifact["retention_class"] == "PERSISTENT"
    assert indexed_artifact["storage_relpath"] is not None
    assert (artifact_store.root / indexed_artifact["storage_relpath"]).read_bytes() == image_bytes
    assert metadata_response.status_code == 200
    assert metadata_response.json()["data"]["artifact_ref"] == artifact_ref
    assert metadata_response.json()["data"]["materialization_status"] == "MATERIALIZED"
    assert metadata_response.json()["data"]["lifecycle_status"] == "ACTIVE"
    assert metadata_response.json()["data"]["content_url"]
    assert metadata_response.json()["data"]["download_url"]
    assert metadata_response.json()["data"]["preview_url"]
    assert content_response.status_code == 200
    assert content_response.content == image_bytes
    assert content_response.headers["content-type"] == "image/png"
    assert "inline" in content_response.headers["content-disposition"]
    assert preview_response.status_code == 200
    assert preview_response.json()["data"]["preview_kind"] == "INLINE_MEDIA"
    assert preview_response.json()["data"]["media_type"] == "image/png"
    assert preview_response.json()["data"]["content_url"]
    assert projected_artifact["status"] == "MATERIALIZED"
    assert projected_artifact["materialization_status"] == "MATERIALIZED"
    assert projected_artifact["lifecycle_status"] == "ACTIVE"
    assert projected_artifact["content_url"]
    assert projected_artifact["download_url"]
    assert projected_artifact["preview_url"]


def test_ticket_result_submit_materializes_pdf_and_preview_reports_inline_media(client, set_ticket_time):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    _create_lease_and_start_ticket(client)
    pdf_bytes = b"%PDF-1.7\nbinary board review pack\n%%EOF"
    artifact_ref = "art://reports/homepage/board-pack.pdf"

    response = client.post(
        "/api/v1/commands/ticket-result-submit",
        json=_ticket_result_submit_payload(
            artifact_refs=[artifact_ref],
            payload={
                "summary": "Board review pack includes a materialized pdf artifact.",
                "recommended_option_id": "option_a",
                "options": [
                    {
                        "option_id": "option_a",
                        "label": "Option A",
                        "summary": "Board pack is attached as pdf.",
                        "artifact_refs": [artifact_ref],
                    }
                ],
            },
            written_artifacts=[
                {
                    "path": "reports/review/board-pack.pdf",
                    "artifact_ref": artifact_ref,
                    "kind": "PDF",
                    "media_type": "application/pdf",
                    "content_base64": _encode_base64(pdf_bytes),
                }
            ],
            idempotency_key="ticket-result-submit:wf_seed:tkt_visual_001:pdf-binary",
        ),
    )

    metadata_response = client.get("/api/v1/artifacts/by-ref", params={"artifact_ref": artifact_ref})
    content_response = client.get(
        "/api/v1/artifacts/content",
        params={"artifact_ref": artifact_ref, "disposition": "attachment"},
    )
    preview_response = client.get("/api/v1/artifacts/preview", params={"artifact_ref": artifact_ref})

    assert response.status_code == 200
    assert response.json()["status"] == "ACCEPTED"
    assert metadata_response.status_code == 200
    assert metadata_response.json()["data"]["materialization_status"] == "MATERIALIZED"
    assert metadata_response.json()["data"]["media_type"] == "application/pdf"
    assert content_response.status_code == 200
    assert content_response.content == pdf_bytes
    assert "attachment" in content_response.headers["content-disposition"]
    assert preview_response.status_code == 200
    assert preview_response.json()["data"]["preview_kind"] == "INLINE_MEDIA"
    assert preview_response.json()["data"]["media_type"] == "application/pdf"


def test_ticket_result_submit_invalid_binary_base64_converts_to_controlled_failure(client, set_ticket_time):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    _create_lease_and_start_ticket(client, retry_budget=2)

    response = client.post(
        "/api/v1/commands/ticket-result-submit",
        json=_ticket_result_submit_payload(
            artifact_refs=["art://homepage/mockup.png"],
            payload={
                "summary": "Invalid binary payload should be rejected.",
                "recommended_option_id": "option_a",
                "options": [
                    {
                        "option_id": "option_a",
                        "label": "Option A",
                        "summary": "Single option for invalid base64 validation.",
                        "artifact_refs": ["art://homepage/mockup.png"],
                    }
                ],
            },
            written_artifacts=[
                {
                    "path": "artifacts/ui/homepage/mockup.png",
                    "artifact_ref": "art://homepage/mockup.png",
                    "kind": "IMAGE",
                    "content_base64": "***not-base64***",
                }
            ],
            idempotency_key="ticket-result-submit:wf_seed:tkt_visual_001:invalid-binary-base64",
        ),
    )

    repository = client.app.state.repository
    failed_events = [
        event for event in repository.list_events_for_testing() if event["event_type"] == EVENT_TICKET_FAILED
    ]

    assert response.status_code == 200
    assert response.json()["status"] == "ACCEPTED"
    assert failed_events[-1]["payload"]["failure_kind"] == "ARTIFACT_VALIDATION_ERROR"
    assert "base64" in failed_events[-1]["payload"]["failure_message"].lower()


def test_artifact_delete_marks_tombstone_and_blocks_content_reads(client, set_ticket_time):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    _create_lease_and_start_ticket(client)
    artifact_ref = "art://homepage/option-a.json"

    submit_response = client.post(
        "/api/v1/commands/ticket-result-submit",
        json=_ticket_result_submit_payload(
            artifact_refs=[artifact_ref],
            payload={
                "summary": "Structured artifact is ready for deletion testing.",
                "recommended_option_id": "option_a",
                "options": [
                    {
                        "option_id": "option_a",
                        "label": "Option A",
                        "summary": "Single option for delete testing.",
                        "artifact_refs": [artifact_ref],
                    }
                ],
            },
            written_artifacts=[
                {
                    "path": "artifacts/ui/homepage/option-a.json",
                    "artifact_ref": artifact_ref,
                    "kind": "JSON",
                    "content_json": {"option_id": "option_a"},
                }
            ],
            idempotency_key="ticket-result-submit:wf_seed:tkt_visual_001:delete-target",
        ),
    )

    repository = client.app.state.repository
    artifact_store = client.app.state.artifact_store
    before_delete = repository.get_artifact_by_ref(artifact_ref)
    delete_response = client.post(
        "/api/v1/commands/artifact-delete",
        json={
            "artifact_ref": artifact_ref,
            "deleted_by": "emp_ops_1",
            "reason": "Outdated artifact should no longer be consumed.",
            "idempotency_key": "artifact-delete:art://homepage/option-a.json",
        },
    )
    after_delete = repository.get_artifact_by_ref(artifact_ref)
    metadata_response = client.get("/api/v1/artifacts/by-ref", params={"artifact_ref": artifact_ref})
    content_response = client.get(
        "/api/v1/artifacts/content",
        params={"artifact_ref": artifact_ref, "disposition": "inline"},
    )
    projection_response = client.get("/api/v1/projections/tickets/tkt_visual_001/artifacts")
    projected_artifact = projection_response.json()["data"]["artifacts"][0]
    event_types = [event["event_type"] for event in repository.list_events_for_testing()]

    assert submit_response.status_code == 200
    assert before_delete is not None
    assert before_delete["storage_relpath"] is not None
    assert delete_response.status_code == 200
    assert delete_response.json()["status"] == "ACCEPTED"
    assert after_delete is not None
    assert after_delete["lifecycle_status"] == "DELETED"
    assert after_delete["deleted_by"] == "emp_ops_1"
    assert after_delete["delete_reason"] == "Outdated artifact should no longer be consumed."
    assert after_delete["deleted_at"] is not None
    assert not (artifact_store.root / before_delete["storage_relpath"]).exists()
    assert metadata_response.status_code == 200
    assert metadata_response.json()["data"]["lifecycle_status"] == "DELETED"
    assert content_response.status_code == 410
    assert projected_artifact["lifecycle_status"] == "DELETED"
    assert "ARTIFACT_DELETED" in event_types


def test_artifact_cleanup_expires_elapsed_artifacts_and_deletes_files(client, set_ticket_time):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    _create_lease_and_start_ticket(client)
    artifact_ref = "art://reports/homepage/review-summary.md"

    submit_response = client.post(
        "/api/v1/commands/ticket-result-submit",
        json=_ticket_result_submit_payload(
            artifact_refs=[artifact_ref],
            payload={
                "summary": "Ephemeral markdown artifact should expire.",
                "recommended_option_id": "option_a",
                "options": [
                    {
                        "option_id": "option_a",
                        "label": "Option A",
                        "summary": "Single option for cleanup testing.",
                        "artifact_refs": [artifact_ref],
                    }
                ],
            },
            written_artifacts=[
                {
                    "path": "reports/review/homepage-summary.md",
                    "artifact_ref": artifact_ref,
                    "kind": "MARKDOWN",
                    "content_text": "# Summary\n\nEphemeral markdown artifact.\n",
                    "retention_class": "EPHEMERAL",
                    "retention_ttl_sec": 60,
                }
            ],
            idempotency_key="ticket-result-submit:wf_seed:tkt_visual_001:cleanup-target",
        ),
    )

    repository = client.app.state.repository
    artifact_store = client.app.state.artifact_store
    created_record = repository.get_artifact_by_ref(artifact_ref)
    assert created_record is not None
    assert created_record["storage_relpath"] is not None
    stored_path = artifact_store.root / created_record["storage_relpath"]
    assert stored_path.exists()

    set_ticket_time("2026-03-28T10:02:00+08:00")
    cleanup_response = client.post(
        "/api/v1/commands/artifact-cleanup",
        json={
            "cleaned_by": "emp_ops_1",
            "idempotency_key": "artifact-cleanup:expired-artifacts",
        },
    )
    expired_record = repository.get_artifact_by_ref(artifact_ref)
    metadata_response = client.get("/api/v1/artifacts/by-ref", params={"artifact_ref": artifact_ref})
    content_response = client.get(
        "/api/v1/artifacts/content",
        params={"artifact_ref": artifact_ref, "disposition": "inline"},
    )
    event_types = [event["event_type"] for event in repository.list_events_for_testing()]

    assert submit_response.status_code == 200
    assert cleanup_response.status_code == 200
    assert cleanup_response.json()["status"] == "ACCEPTED"
    assert expired_record is not None
    assert expired_record["lifecycle_status"] == "EXPIRED"
    assert expired_record["deleted_at"] is not None
    assert expired_record["storage_deleted_at"] is not None
    assert not stored_path.exists()
    assert metadata_response.status_code == 200
    assert metadata_response.json()["data"]["lifecycle_status"] == "EXPIRED"
    assert content_response.status_code == 410
    assert "ARTIFACT_EXPIRED" in event_types
    assert "ARTIFACT_CLEANUP_COMPLETED" in event_types


def test_artifact_cleanup_does_not_recount_storage_already_cleared(client, set_ticket_time):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    _create_lease_and_start_ticket(client)
    artifact_ref = "art://reports/homepage/repeat-cleanup.md"

    submit_response = client.post(
        "/api/v1/commands/ticket-result-submit",
        json=_ticket_result_submit_payload(
            artifact_refs=[artifact_ref],
            payload={
                "summary": "Repeated cleanup should not recount already deleted storage.",
                "recommended_option_id": "option_a",
                "options": [
                    {
                        "option_id": "option_a",
                        "label": "Option A",
                        "summary": "Repeat cleanup option.",
                        "artifact_refs": [artifact_ref],
                    }
                ],
            },
            written_artifacts=[
                {
                    "path": "reports/review/repeat-cleanup.md",
                    "artifact_ref": artifact_ref,
                    "kind": "MARKDOWN",
                    "content_text": "# Cleanup\n\nRepeat cleanup should stay zero.\n",
                    "retention_class": "EPHEMERAL",
                    "retention_ttl_sec": 60,
                }
            ],
            idempotency_key="ticket-result-submit:wf_seed:tkt_visual_001:repeat-cleanup",
        ),
    )

    set_ticket_time("2026-03-28T10:02:00+08:00")
    first_cleanup = client.post(
        "/api/v1/commands/artifact-cleanup",
        json={
            "cleaned_by": "emp_ops_1",
            "idempotency_key": "artifact-cleanup:repeat-first",
        },
    )
    second_cleanup = client.post(
        "/api/v1/commands/artifact-cleanup",
        json={
            "cleaned_by": "emp_ops_1",
            "idempotency_key": "artifact-cleanup:repeat-second",
        },
    )

    cleanup_events = [
        event
        for event in client.app.state.repository.list_events_for_testing()
        if event["event_type"] == EVENT_ARTIFACT_CLEANUP_COMPLETED
    ]

    assert submit_response.status_code == 200
    assert first_cleanup.status_code == 200
    assert second_cleanup.status_code == 200
    assert len(cleanup_events) == 2
    assert cleanup_events[0]["payload"]["expired_count"] == 1
    assert cleanup_events[0]["payload"]["storage_deleted_count"] == 1
    assert cleanup_events[1]["payload"]["expired_count"] == 0
    assert cleanup_events[1]["payload"]["storage_deleted_count"] == 0
    assert cleanup_events[1]["payload"]["already_cleared_count"] == 0


def test_artifact_upload_session_flow_materializes_local_binary_artifact_and_consumes_session(
    db_path,
    set_ticket_time,
):
    from app.main import create_app

    app = create_app()
    with TestClient(app) as client:
        set_ticket_time("2026-03-31T19:00:00+08:00")
        _create_lease_and_start_ticket(client, allowed_write_set=["reports/ops/*"])

        create_response = client.post(
            "/api/v1/artifact-uploads/sessions",
            json={
                "filename": "runtime-bundle.zip",
                "media_type": "application/zip",
            },
        )
        session_id = create_response.json()["data"]["session_id"]
        part_one = client.put(
            f"/api/v1/artifact-uploads/sessions/{session_id}/parts/1",
            content=b"abc",
            headers={"content-type": "application/octet-stream"},
        )
        part_two = client.put(
            f"/api/v1/artifact-uploads/sessions/{session_id}/parts/2",
            content=b"defg",
            headers={"content-type": "application/octet-stream"},
        )
        complete_response = client.post(f"/api/v1/artifact-uploads/sessions/{session_id}/complete")

        artifact_ref = "art://reports/ops/runtime-bundle.zip"
        import_response = client.post(
            "/api/v1/commands/ticket-artifact-import-upload",
            json={
                "workflow_id": "wf_seed",
                "ticket_id": "tkt_visual_001",
                "node_id": "node_homepage_visual",
                "artifact_ref": artifact_ref,
                "path": "reports/ops/runtime-bundle.zip",
                "kind": "BINARY",
                "media_type": "application/zip",
                "upload_session_id": session_id,
                "idempotency_key": "ticket-artifact-import-upload:wf_seed:tkt_visual_001:runtime-bundle",
            },
        )
        submit_response = client.post(
            "/api/v1/commands/ticket-result-submit",
            json=_ticket_result_submit_payload(
                artifact_refs=[artifact_ref],
                payload={
                    "summary": "Uploaded runtime bundle is ready.",
                    "recommended_option_id": "option_a",
                    "options": [
                        {
                            "option_id": "option_a",
                            "label": "Option A",
                            "summary": "Uploaded binary bundle.",
                            "artifact_refs": [artifact_ref],
                        }
                    ],
                },
                written_artifacts=[],
                idempotency_key="ticket-result-submit:wf_seed:tkt_visual_001:uploaded-bundle",
            ),
        )
        metadata_response = client.get("/api/v1/artifacts/by-ref", params={"artifact_ref": artifact_ref})
        content_response = client.get(
            "/api/v1/artifacts/content",
            params={"artifact_ref": artifact_ref, "disposition": "attachment"},
        )

        repository = client.app.state.repository
        stored_artifact = repository.get_artifact_by_ref(artifact_ref)
        upload_session = repository.get_artifact_upload_session(session_id)

        assert create_response.status_code == 200
        assert create_response.json()["data"]["status"] == "INITIATED"
        assert part_one.status_code == 200
        assert part_two.status_code == 200
        assert complete_response.status_code == 200
        assert complete_response.json()["data"]["status"] == "COMPLETED"
        assert import_response.status_code == 200
        assert submit_response.status_code == 200
        assert metadata_response.status_code == 200
        assert content_response.status_code == 200
        assert content_response.content == b"abcdefg"
        assert stored_artifact is not None
        assert stored_artifact["storage_backend"] == "LOCAL_FILE"
        assert stored_artifact["storage_delete_status"] == "PRESENT"
        assert stored_artifact["storage_relpath"] is not None
        assert stored_artifact["storage_object_key"] is None
        assert metadata_response.json()["data"]["storage_backend"] == "LOCAL_FILE"
        assert metadata_response.json()["data"]["storage_delete_status"] == "PRESENT"
        assert upload_session is not None
        assert upload_session["status"] == "CONSUMED"
        assert upload_session["consumed_by_artifact_ref"] == artifact_ref


def test_ticket_artifact_import_upload_rejects_path_outside_allowed_write_set(
    client,
    set_ticket_time,
):
    set_ticket_time("2026-03-31T19:05:00+08:00")
    _create_lease_and_start_ticket(client, allowed_write_set=["reports/ops/*"])

    create_response = client.post(
        "/api/v1/artifact-uploads/sessions",
        json={
            "filename": "runtime-bundle.zip",
            "media_type": "application/zip",
        },
    )
    session_id = create_response.json()["data"]["session_id"]
    client.put(
        f"/api/v1/artifact-uploads/sessions/{session_id}/parts/1",
        content=b"abcdefg",
        headers={"content-type": "application/octet-stream"},
    )
    client.post(f"/api/v1/artifact-uploads/sessions/{session_id}/complete")

    import_response = client.post(
        "/api/v1/commands/ticket-artifact-import-upload",
        json={
            "workflow_id": "wf_seed",
            "ticket_id": "tkt_visual_001",
            "node_id": "node_homepage_visual",
            "artifact_ref": "art://reports/ops/runtime-bundle.zip",
            "path": "artifacts/ui/homepage/runtime-bundle.zip",
            "kind": "BINARY",
            "media_type": "application/zip",
            "upload_session_id": session_id,
            "idempotency_key": "ticket-artifact-import-upload:wf_seed:tkt_visual_001:outside-write-set",
        },
    )

    repository = client.app.state.repository
    upload_session = repository.get_artifact_upload_session(session_id)
    stored_artifact = repository.get_artifact_by_ref("art://reports/ops/runtime-bundle.zip")

    assert create_response.status_code == 200
    assert import_response.status_code == 200
    assert import_response.json()["status"] == "REJECTED"
    assert stored_artifact is None
    assert upload_session is not None
    assert upload_session["status"] == "COMPLETED"


def test_object_store_artifact_content_route_reads_remote_body(
    monkeypatch,
    db_path,
    set_ticket_time,
):
    with _create_client_with_fake_object_store(monkeypatch) as (client, _fake_client):
        set_ticket_time("2026-03-31T19:10:00+08:00")
        _create_lease_and_start_ticket(client, allowed_write_set=["reports/ops/*"])
        artifact_ref = "art://reports/ops/object-store-bundle.zip"
        submit_response = client.post(
            "/api/v1/commands/ticket-result-submit",
            json=_ticket_result_submit_payload(
                artifact_refs=[artifact_ref],
                payload={
                    "summary": "Remote object store artifact is ready.",
                    "recommended_option_id": "option_a",
                    "options": [
                        {
                            "option_id": "option_a",
                            "label": "Option A",
                            "summary": "Remote binary bundle.",
                            "artifact_refs": [artifact_ref],
                        }
                    ],
                },
                written_artifacts=[
                    {
                        "path": "reports/ops/object-store-bundle.zip",
                        "artifact_ref": artifact_ref,
                        "kind": "BINARY",
                        "media_type": "application/zip",
                        "content_base64": _encode_base64(b"remote-binary"),
                    }
                ],
                idempotency_key="ticket-result-submit:wf_seed:tkt_visual_001:object-store-inline",
            ),
        )
        repository = client.app.state.repository
        stored_artifact = repository.get_artifact_by_ref(artifact_ref)
        metadata_response = client.get("/api/v1/artifacts/by-ref", params={"artifact_ref": artifact_ref})
        content_response = client.get(
            "/api/v1/artifacts/content",
            params={"artifact_ref": artifact_ref, "disposition": "inline"},
        )

        assert submit_response.status_code == 200
        assert stored_artifact is not None
        assert stored_artifact["storage_backend"] == "OBJECT_STORE"
        assert stored_artifact["storage_relpath"] is None
        assert stored_artifact["storage_object_key"] is not None
        assert stored_artifact["storage_delete_status"] == "PRESENT"
        assert metadata_response.status_code == 200
        assert metadata_response.json()["data"]["storage_backend"] == "OBJECT_STORE"
        assert metadata_response.json()["data"]["storage_delete_status"] == "PRESENT"
        assert content_response.status_code == 200
        assert content_response.content == b"remote-binary"


def test_object_store_cleanup_failure_surfaces_delete_failed_status_and_dashboard_counts(
    monkeypatch,
    db_path,
    set_ticket_time,
):
    with _create_client_with_fake_object_store(monkeypatch, fail_delete=True) as (client, _fake_client):
        set_ticket_time("2026-03-31T19:20:00+08:00")
        _create_lease_and_start_ticket(client, allowed_write_set=["reports/ops/*"])
        artifact_ref = "art://reports/ops/object-store-cleanup.zip"
        submit_response = client.post(
            "/api/v1/commands/ticket-result-submit",
            json=_ticket_result_submit_payload(
                artifact_refs=[artifact_ref],
                payload={
                    "summary": "Remote object cleanup failure should stay visible.",
                    "recommended_option_id": "option_a",
                    "options": [
                        {
                            "option_id": "option_a",
                            "label": "Option A",
                            "summary": "Cleanup failure option.",
                            "artifact_refs": [artifact_ref],
                        }
                    ],
                },
                written_artifacts=[
                    {
                        "path": "reports/ops/object-store-cleanup.zip",
                        "artifact_ref": artifact_ref,
                        "kind": "BINARY",
                        "media_type": "application/zip",
                        "content_base64": _encode_base64(b"cleanup-failure"),
                        "retention_class": "EPHEMERAL",
                        "retention_ttl_sec": 60,
                    }
                ],
                idempotency_key="ticket-result-submit:wf_seed:tkt_visual_001:object-store-cleanup",
            ),
        )

        set_ticket_time("2026-03-31T19:22:00+08:00")
        cleanup_response = client.post(
            "/api/v1/commands/artifact-cleanup",
            json={
                "cleaned_by": "emp_ops_1",
                "idempotency_key": "artifact-cleanup:object-store-delete-failure",
            },
        )
        repository = client.app.state.repository
        stored_artifact = repository.get_artifact_by_ref(artifact_ref)
        dashboard_response = client.get("/api/v1/projections/dashboard")
        candidates_response = client.get("/api/v1/projections/artifact-cleanup-candidates")

        assert submit_response.status_code == 200
        assert cleanup_response.status_code == 200
        assert stored_artifact is not None
        assert stored_artifact["lifecycle_status"] == "EXPIRED"
        assert stored_artifact["storage_backend"] == "OBJECT_STORE"
        assert stored_artifact["storage_delete_status"] == "DELETE_FAILED"
        assert stored_artifact["storage_deleted_at"] is None
        assert stored_artifact["storage_delete_error"] == "simulated object delete failure"
        assert dashboard_response.status_code == 200
        assert dashboard_response.json()["data"]["artifact_maintenance"]["delete_failed_count"] == 1
        projected_artifact = next(
            item
            for item in candidates_response.json()["data"]["artifacts"]
            if item["artifact_ref"] == artifact_ref
        )
        assert projected_artifact["storage_backend"] == "OBJECT_STORE"
        assert projected_artifact["storage_delete_status"] == "DELETE_FAILED"


def test_ticket_result_submit_schema_error_converts_to_controlled_failure(client, set_ticket_time):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    _create_lease_and_start_ticket(client, retry_budget=2, on_schema_error="retry")

    response = client.post(
        "/api/v1/commands/ticket-result-submit",
        json=_ticket_result_submit_payload(
            payload={
                "summary": "Homepage visual milestone is missing options.",
                "recommended_option_id": "option_a",
            },
            idempotency_key="ticket-result-submit:wf_seed:tkt_visual_001:schema-error",
        ),
    )

    repository = client.app.state.repository
    latest_ticket_id = repository.get_current_node_projection("wf_seed", "node_homepage_visual")[
        "latest_ticket_id"
    ]
    original_ticket = repository.get_current_ticket_projection("tkt_visual_001")
    latest_ticket = repository.get_current_ticket_projection(latest_ticket_id)
    failed_events = [
        event for event in repository.list_events_for_testing() if event["event_type"] == EVENT_TICKET_FAILED
    ]

    assert response.status_code == 200
    assert response.json()["status"] == "ACCEPTED"
    assert original_ticket["status"] == TICKET_STATUS_FAILED
    assert latest_ticket_id != "tkt_visual_001"
    assert latest_ticket["status"] == TICKET_STATUS_PENDING
    assert failed_events[-1]["payload"]["failure_kind"] == "SCHEMA_ERROR"
    assert failed_events[-1]["payload"]["failure_detail"]["field_path"] == "options"
    assert failed_events[-1]["payload"]["failure_detail"]["expected"] == "non-empty array"
    assert failed_events[-1]["payload"]["failure_detail"]["actual"] == "missing"


def test_ticket_result_submit_write_set_violation_converts_to_controlled_failure(client, set_ticket_time):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    _create_lease_and_start_ticket(client, retry_budget=2)

    response = client.post(
        "/api/v1/commands/ticket-result-submit",
        json=_ticket_result_submit_payload(
            written_artifacts=[
                {
                    "path": "artifacts/forbidden/option-a.png",
                    "artifact_ref": "art://homepage/option-a.png",
                    "kind": "IMAGE",
                }
            ],
            idempotency_key="ticket-result-submit:wf_seed:tkt_visual_001:write-set",
        ),
    )

    repository = client.app.state.repository
    failed_events = [
        event for event in repository.list_events_for_testing() if event["event_type"] == EVENT_TICKET_FAILED
    ]

    assert response.status_code == 200
    assert response.json()["status"] == "ACCEPTED"
    assert failed_events[-1]["payload"]["failure_kind"] == "WRITE_SET_VIOLATION"


def test_ticket_result_submit_duplicate_artifact_refs_convert_to_controlled_failure(client, set_ticket_time):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    _create_lease_and_start_ticket(client, retry_budget=2)

    response = client.post(
        "/api/v1/commands/ticket-result-submit",
        json=_ticket_result_submit_payload(
            artifact_refs=["art://homepage/duplicate.json"],
            payload={
                "summary": "Duplicate artifact refs should be rejected.",
                "recommended_option_id": "option_a",
                "options": [
                    {
                        "option_id": "option_a",
                        "label": "Option A",
                        "summary": "Single option for duplicate artifact ref validation.",
                        "artifact_refs": ["art://homepage/duplicate.json"],
                    }
                ],
            },
            written_artifacts=[
                {
                    "path": "artifacts/ui/homepage/option-a.json",
                    "artifact_ref": "art://homepage/duplicate.json",
                    "kind": "JSON",
                    "content_json": {"option_id": "option_a"},
                },
                {
                    "path": "artifacts/ui/homepage/option-b.json",
                    "artifact_ref": "art://homepage/duplicate.json",
                    "kind": "JSON",
                    "content_json": {"option_id": "option_b"},
                },
            ],
            idempotency_key="ticket-result-submit:wf_seed:tkt_visual_001:duplicate-artifact-ref",
        ),
    )

    repository = client.app.state.repository
    failed_events = [
        event for event in repository.list_events_for_testing() if event["event_type"] == EVENT_TICKET_FAILED
    ]

    assert response.status_code == 200
    assert response.json()["status"] == "ACCEPTED"
    assert failed_events[-1]["payload"]["failure_kind"] == "ARTIFACT_VALIDATION_ERROR"
    assert "artifact_ref" in failed_events[-1]["payload"]["failure_message"]


def test_ticket_result_submit_duplicate_paths_convert_to_controlled_failure(client, set_ticket_time):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    _create_lease_and_start_ticket(client, retry_budget=2)

    response = client.post(
        "/api/v1/commands/ticket-result-submit",
        json=_ticket_result_submit_payload(
            artifact_refs=["art://homepage/option-a.json", "art://homepage/option-b.json"],
            payload={
                "summary": "Duplicate artifact paths should be rejected.",
                "recommended_option_id": "option_a",
                "options": [
                    {
                        "option_id": "option_a",
                        "label": "Option A",
                        "summary": "Single option for duplicate path validation.",
                        "artifact_refs": ["art://homepage/option-a.json"],
                    }
                ],
            },
            written_artifacts=[
                {
                    "path": "artifacts/ui/homepage/duplicate.json",
                    "artifact_ref": "art://homepage/option-a.json",
                    "kind": "JSON",
                    "content_json": {"option_id": "option_a"},
                },
                {
                    "path": "artifacts/ui/homepage/duplicate.json",
                    "artifact_ref": "art://homepage/option-b.json",
                    "kind": "JSON",
                    "content_json": {"option_id": "option_b"},
                },
            ],
            idempotency_key="ticket-result-submit:wf_seed:tkt_visual_001:duplicate-path",
        ),
    )

    repository = client.app.state.repository
    failed_events = [
        event for event in repository.list_events_for_testing() if event["event_type"] == EVENT_TICKET_FAILED
    ]

    assert response.status_code == 200
    assert response.json()["status"] == "ACCEPTED"
    assert failed_events[-1]["payload"]["failure_kind"] == "ARTIFACT_VALIDATION_ERROR"
    assert "path" in failed_events[-1]["payload"]["failure_message"]


def test_ticket_result_submit_kind_content_mismatch_converts_to_controlled_failure(client, set_ticket_time):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    _create_lease_and_start_ticket(client, retry_budget=2)

    response = client.post(
        "/api/v1/commands/ticket-result-submit",
        json=_ticket_result_submit_payload(
            artifact_refs=["art://homepage/invalid.json"],
            payload={
                "summary": "Artifact content kind mismatch should be rejected.",
                "recommended_option_id": "option_a",
                "options": [
                    {
                        "option_id": "option_a",
                        "label": "Option A",
                        "summary": "Single option for kind/content validation.",
                        "artifact_refs": ["art://homepage/invalid.json"],
                    }
                ],
            },
            written_artifacts=[
                {
                    "path": "artifacts/ui/homepage/invalid.json",
                    "artifact_ref": "art://homepage/invalid.json",
                    "kind": "JSON",
                    "content_text": "{\"option_id\": \"option_a\"}",
                }
            ],
            idempotency_key="ticket-result-submit:wf_seed:tkt_visual_001:kind-content-mismatch",
        ),
    )

    repository = client.app.state.repository
    failed_events = [
        event for event in repository.list_events_for_testing() if event["event_type"] == EVENT_TICKET_FAILED
    ]

    assert response.status_code == 200
    assert response.json()["status"] == "ACCEPTED"
    assert failed_events[-1]["payload"]["failure_kind"] == "ARTIFACT_VALIDATION_ERROR"
    assert "content_json" in failed_events[-1]["payload"]["failure_message"]


def test_ticket_cancel_transitions_executing_ticket_to_cancel_requested_and_blocks_progress(
    client,
    set_ticket_time,
):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    _create_lease_and_start_ticket(client)

    cancel_response = client.post(
        "/api/v1/commands/ticket-cancel",
        json=_ticket_cancel_payload(),
    )
    ticket_projection = client.app.state.repository.get_current_ticket_projection("tkt_visual_001")
    node_projection = client.app.state.repository.get_current_node_projection("wf_seed", "node_homepage_visual")

    heartbeat_response = client.post(
        "/api/v1/commands/ticket-heartbeat",
        json=_ticket_heartbeat_payload(),
    )
    result_response = client.post(
        "/api/v1/commands/ticket-result-submit",
        json=_ticket_result_submit_payload(
            idempotency_key="ticket-result-submit:wf_seed:tkt_visual_001:after-cancel",
        ),
    )

    events = client.app.state.repository.list_events_for_testing()
    cancel_requested_events = [
        event for event in events if event["event_type"] == EVENT_TICKET_CANCEL_REQUESTED
    ]
    cancelled_events = [event for event in events if event["event_type"] == EVENT_TICKET_CANCELLED]

    assert cancel_response.status_code == 200
    assert cancel_response.json()["status"] == "ACCEPTED"
    assert ticket_projection["status"] == TICKET_STATUS_CANCEL_REQUESTED
    assert node_projection["status"] == NODE_STATUS_CANCEL_REQUESTED
    assert heartbeat_response.status_code == 200
    assert heartbeat_response.json()["status"] == "REJECTED"
    assert result_response.status_code == 200
    assert result_response.json()["status"] == "ACCEPTED"
    assert cancel_requested_events
    assert cancelled_events
    assert client.app.state.repository.get_current_ticket_projection("tkt_visual_001")["status"] == (
        TICKET_STATUS_CANCELLED
    )
    assert client.app.state.repository.get_current_node_projection("wf_seed", "node_homepage_visual")[
        "status"
    ] == NODE_STATUS_CANCELLED


def test_ticket_fail_moves_ticket_to_failed_and_node_to_rework_when_retry_exhausted(client, set_ticket_time):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    _create_lease_and_start_ticket(client, retry_budget=0)

    response = client.post("/api/v1/commands/ticket-fail", json=_ticket_fail_payload())
    ticket_projection = client.app.state.repository.get_current_ticket_projection("tkt_visual_001")
    node_projection = client.app.state.repository.get_current_node_projection(
        "wf_seed",
        "node_homepage_visual",
    )

    assert response.status_code == 200
    assert response.json()["status"] == "ACCEPTED"
    assert client.app.state.repository.count_events_by_type(EVENT_TICKET_FAILED) == 1
    assert client.app.state.repository.count_events_by_type(EVENT_TICKET_RETRY_SCHEDULED) == 0
    assert ticket_projection["status"] == TICKET_STATUS_FAILED
    assert ticket_projection["lease_owner"] is None
    assert ticket_projection["lease_expires_at"] is None
    assert ticket_projection["last_failure_kind"] == "RUNTIME_ERROR"
    assert ticket_projection["last_failure_message"] == "Worker execution failed."
    assert ticket_projection["last_failure_fingerprint"]
    assert node_projection["status"] == NODE_STATUS_REWORK_REQUIRED


def test_ticket_fail_is_rejected_before_ticket_start(client):
    client.post("/api/v1/commands/ticket-create", json=_ticket_create_payload())
    response = client.post("/api/v1/commands/ticket-fail", json=_ticket_fail_payload())

    assert response.status_code == 200
    assert response.json()["status"] == "REJECTED"
    assert "EXECUTING" in response.json()["reason"]


def test_ticket_fail_is_rejected_for_non_latest_ticket(client, set_ticket_time):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    _create_lease_and_start_ticket(client)
    repository = client.app.state.repository
    with repository.transaction() as connection:
        connection.execute(
            """
            UPDATE node_projection
            SET latest_ticket_id = ?
            WHERE workflow_id = ? AND node_id = ?
            """,
            ("tkt_other", "wf_seed", "node_homepage_visual"),
        )

    response = client.post("/api/v1/commands/ticket-fail", json=_ticket_fail_payload())

    assert response.status_code == 200
    assert response.json()["status"] == "REJECTED"
    assert "no longer points" in response.json()["reason"].lower()


def test_ticket_fail_auto_retry_creates_new_attempt(client, set_ticket_time):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    _create_lease_and_start_ticket(client)

    response = client.post(
        "/api/v1/commands/ticket-fail",
        json=_ticket_fail_payload(failure_kind="SCHEMA_ERROR"),
    )

    repository = client.app.state.repository
    events = repository.list_events_for_testing()
    latest_ticket = repository.get_current_node_projection("wf_seed", "node_homepage_visual")["latest_ticket_id"]
    new_ticket_projection = repository.get_current_ticket_projection(latest_ticket)
    failed_ticket_projection = repository.get_current_ticket_projection("tkt_visual_001")
    created_retry_events = [
        event
        for event in events
        if event["event_type"] == EVENT_TICKET_CREATED and event["payload"]["ticket_id"] != "tkt_visual_001"
    ]

    assert response.status_code == 200
    assert response.json()["status"] == "ACCEPTED"
    assert repository.count_events_by_type(EVENT_TICKET_FAILED) == 1
    assert repository.count_events_by_type(EVENT_TICKET_RETRY_SCHEDULED) == 1
    assert len(created_retry_events) == 1
    assert created_retry_events[0]["payload"]["parent_ticket_id"] == "tkt_visual_001"
    assert created_retry_events[0]["payload"]["attempt_no"] == 2
    assert created_retry_events[0]["payload"]["retry_count"] == 1
    assert failed_ticket_projection["status"] == TICKET_STATUS_FAILED
    assert new_ticket_projection["status"] == TICKET_STATUS_PENDING
    assert new_ticket_projection["retry_count"] == 1


def test_ticket_fail_is_idempotent(client, set_ticket_time):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    _create_lease_and_start_ticket(client, retry_budget=0)

    first = client.post("/api/v1/commands/ticket-fail", json=_ticket_fail_payload())
    duplicate = client.post("/api/v1/commands/ticket-fail", json=_ticket_fail_payload())

    assert first.status_code == 200
    assert first.json()["status"] == "ACCEPTED"
    assert duplicate.status_code == 200
    assert duplicate.json()["status"] == "DUPLICATE"


def test_scheduler_tick_times_out_executing_ticket_and_creates_retry(client, set_ticket_time):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    _create_lease_and_start_ticket(client, retry_budget=1)

    set_ticket_time("2026-03-28T10:31:00+08:00")
    response = client.post("/api/v1/commands/scheduler-tick", json=_scheduler_tick_payload())

    repository = client.app.state.repository
    node_projection = repository.get_current_node_projection("wf_seed", "node_homepage_visual")
    latest_ticket = node_projection["latest_ticket_id"]
    latest_projection = repository.get_current_ticket_projection(latest_ticket)
    original_projection = repository.get_current_ticket_projection("tkt_visual_001")
    retry_events = repository.count_events_by_type(EVENT_TICKET_RETRY_SCHEDULED)
    timeout_events = [
        event for event in repository.list_events_for_testing() if event["event_type"] == EVENT_TICKET_TIMED_OUT
    ]

    assert response.status_code == 200
    assert response.json()["status"] == "ACCEPTED"
    assert repository.count_events_by_type(EVENT_TICKET_TIMED_OUT) == 1
    assert retry_events == 1
    assert timeout_events[-1]["payload"]["failure_kind"] == "TIMEOUT_SLA_EXCEEDED"
    assert original_projection["status"] == TICKET_STATUS_TIMED_OUT
    assert latest_ticket != "tkt_visual_001"
    assert latest_projection["status"] == TICKET_STATUS_LEASED
    assert latest_projection["lease_owner"] == "emp_frontend_2"
    assert latest_projection["retry_count"] == 1
    assert latest_projection["timeout_sla_sec"] == 2700
    assert latest_projection["heartbeat_timeout_sec"] == 900
    assert repository.count_events_by_type(EVENT_INCIDENT_OPENED) == 0
    assert repository.count_events_by_type(EVENT_CIRCUIT_BREAKER_OPENED) == 0


def test_scheduler_tick_times_out_executing_ticket_on_missed_heartbeat(client, set_ticket_time):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    _create_lease_and_start_ticket(client, retry_budget=1, lease_timeout_sec=60)

    set_ticket_time("2026-03-28T10:02:00+08:00")
    response = client.post(
        "/api/v1/commands/scheduler-tick",
        json=_scheduler_tick_payload(idempotency_key="scheduler-tick:heartbeat-timeout"),
    )

    repository = client.app.state.repository
    node_projection = repository.get_current_node_projection("wf_seed", "node_homepage_visual")
    latest_ticket = node_projection["latest_ticket_id"]
    latest_projection = repository.get_current_ticket_projection(latest_ticket)
    original_projection = repository.get_current_ticket_projection("tkt_visual_001")
    timeout_events = [
        event for event in repository.list_events_for_testing() if event["event_type"] == EVENT_TICKET_TIMED_OUT
    ]

    assert response.status_code == 200
    assert response.json()["status"] == "ACCEPTED"
    assert repository.count_events_by_type(EVENT_TICKET_TIMED_OUT) == 1
    assert timeout_events[-1]["payload"]["failure_kind"] == "HEARTBEAT_TIMEOUT"
    assert original_projection["status"] == TICKET_STATUS_TIMED_OUT
    assert latest_ticket != "tkt_visual_001"
    assert latest_projection["status"] == TICKET_STATUS_LEASED
    assert latest_projection["retry_count"] == 1


def test_scheduler_tick_keeps_total_timeout_as_hard_cap_after_heartbeat_refresh(client, set_ticket_time):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    _create_lease_and_start_ticket(client, retry_budget=1, lease_timeout_sec=1800)

    set_ticket_time("2026-03-28T10:25:00+08:00")
    heartbeat_response = client.post("/api/v1/commands/ticket-heartbeat", json=_ticket_heartbeat_payload())
    assert heartbeat_response.status_code == 200
    assert heartbeat_response.json()["status"] == "ACCEPTED"

    set_ticket_time("2026-03-28T10:31:00+08:00")
    response = client.post(
        "/api/v1/commands/scheduler-tick",
        json=_scheduler_tick_payload(idempotency_key="scheduler-tick:total-timeout-after-heartbeat"),
    )

    repository = client.app.state.repository
    timeout_events = [
        event for event in repository.list_events_for_testing() if event["event_type"] == EVENT_TICKET_TIMED_OUT
    ]
    original_projection = repository.get_current_ticket_projection("tkt_visual_001")

    assert response.status_code == 200
    assert response.json()["status"] == "ACCEPTED"
    assert timeout_events[-1]["payload"]["failure_kind"] == "TIMEOUT_SLA_EXCEEDED"
    assert original_projection["status"] == TICKET_STATUS_TIMED_OUT


def test_repeated_timeout_opens_incident_and_blocks_same_node_dispatch(client, set_ticket_time):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    _create_lease_and_start_ticket(client, retry_budget=2)

    set_ticket_time("2026-03-28T10:31:00+08:00")
    first_timeout = client.post(
        "/api/v1/commands/scheduler-tick",
        json=_scheduler_tick_payload(idempotency_key="scheduler-tick:first-timeout"),
    )
    assert first_timeout.status_code == 200
    assert first_timeout.json()["status"] == "ACCEPTED"

    repository = client.app.state.repository
    retried_ticket_id = repository.get_current_node_projection("wf_seed", "node_homepage_visual")["latest_ticket_id"]

    set_ticket_time("2026-03-28T10:32:00+08:00")
    retry_start = client.post(
        "/api/v1/commands/ticket-start",
        json=_ticket_start_payload(ticket_id=retried_ticket_id),
    )
    assert retry_start.status_code == 200
    assert retry_start.json()["status"] == "ACCEPTED"

    set_ticket_time("2026-03-28T11:18:00+08:00")
    second_timeout = client.post(
        "/api/v1/commands/scheduler-tick",
        json=_scheduler_tick_payload(idempotency_key="scheduler-tick:second-timeout"),
    )
    assert second_timeout.status_code == 200
    assert second_timeout.json()["status"] == "ACCEPTED"

    same_node_create = client.post(
        "/api/v1/commands/ticket-create",
        json=_ticket_create_payload(ticket_id="tkt_visual_003", attempt_no=3),
    )
    assert same_node_create.status_code == 200
    assert same_node_create.json()["status"] == "ACCEPTED"

    other_node_create = client.post(
        "/api/v1/commands/ticket-create",
        json=_ticket_create_payload(ticket_id="tkt_other_node_001", node_id="node_docs_visual"),
    )
    assert other_node_create.status_code == 200
    assert other_node_create.json()["status"] == "ACCEPTED"

    set_ticket_time("2026-03-28T11:19:00+08:00")
    third_tick = client.post(
        "/api/v1/commands/scheduler-tick",
        json=_scheduler_tick_payload(idempotency_key="scheduler-tick:breaker-block"),
    )

    incident_events = [
        event for event in repository.list_events_for_testing() if event["event_type"] == EVENT_INCIDENT_OPENED
    ]
    breaker_events = [
        event
        for event in repository.list_events_for_testing()
        if event["event_type"] == EVENT_CIRCUIT_BREAKER_OPENED
    ]
    blocked_projection = repository.get_current_ticket_projection("tkt_visual_003")
    other_projection = repository.get_current_ticket_projection("tkt_other_node_001")

    assert third_tick.status_code == 200
    assert third_tick.json()["status"] == "ACCEPTED"
    assert len(incident_events) == 1
    assert len(breaker_events) == 1
    assert blocked_projection["status"] == TICKET_STATUS_PENDING
    assert blocked_projection["lease_owner"] is None
    assert other_projection["status"] == TICKET_STATUS_LEASED
    assert other_projection["lease_owner"] == "emp_frontend_2"
    assert repository.count_events_by_type(EVENT_TICKET_RETRY_SCHEDULED) == 1


def test_incident_projection_dashboard_inbox_and_endpoint_reflect_open_timeout_incident(client, set_ticket_time):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    _create_lease_and_start_ticket(client, retry_budget=2)

    set_ticket_time("2026-03-28T10:31:00+08:00")
    client.post(
        "/api/v1/commands/scheduler-tick",
        json=_scheduler_tick_payload(idempotency_key="scheduler-tick:incident-first"),
    )

    repository = client.app.state.repository
    retried_ticket_id = repository.get_current_node_projection("wf_seed", "node_homepage_visual")["latest_ticket_id"]

    set_ticket_time("2026-03-28T10:32:00+08:00")
    client.post(
        "/api/v1/commands/ticket-start",
        json=_ticket_start_payload(ticket_id=retried_ticket_id),
    )

    set_ticket_time("2026-03-28T11:18:00+08:00")
    client.post(
        "/api/v1/commands/scheduler-tick",
        json=_scheduler_tick_payload(idempotency_key="scheduler-tick:incident-second"),
    )

    incident_id = [
        event["payload"]["incident_id"]
        for event in repository.list_events_for_testing()
        if event["event_type"] == EVENT_INCIDENT_OPENED
    ][0]
    dashboard_response = client.get("/api/v1/projections/dashboard")
    inbox_response = client.get("/api/v1/projections/inbox")
    incident_response = client.get(f"/api/v1/projections/incidents/{incident_id}")

    assert dashboard_response.status_code == 200
    assert dashboard_response.json()["data"]["ops_strip"]["open_incidents"] == 1
    assert dashboard_response.json()["data"]["ops_strip"]["open_circuit_breakers"] == 1
    assert dashboard_response.json()["data"]["inbox_counts"]["incidents_pending"] == 1

    assert inbox_response.status_code == 200
    incident_items = [
        item for item in inbox_response.json()["data"]["items"] if item["item_type"] == "INCIDENT_ESCALATION"
    ]
    assert len(incident_items) == 1
    assert incident_items[0]["route_target"]["view"] == "incident_detail"
    assert incident_items[0]["route_target"]["incident_id"] == incident_id

    assert incident_response.status_code == 200
    assert incident_response.json()["data"]["incident"]["incident_id"] == incident_id
    assert incident_response.json()["data"]["incident"]["status"] == "OPEN"
    assert incident_response.json()["data"]["incident"]["circuit_breaker_state"] == "OPEN"
    assert incident_response.json()["data"]["available_followup_actions"] == [
        "RESTORE_ONLY",
        "RESTORE_AND_RETRY_LATEST_TIMEOUT",
    ]
    assert incident_response.json()["data"]["recommended_followup_action"] == (
        "RESTORE_AND_RETRY_LATEST_TIMEOUT"
    )


def test_incident_resolve_closes_breaker_and_removes_open_incident_from_dashboard_and_inbox(
    client,
    set_ticket_time,
):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    _create_lease_and_start_ticket(client, retry_budget=2)

    set_ticket_time("2026-03-28T10:31:00+08:00")
    client.post(
        "/api/v1/commands/scheduler-tick",
        json=_scheduler_tick_payload(idempotency_key="scheduler-tick:resolve-first"),
    )

    repository = client.app.state.repository
    retried_ticket_id = repository.get_current_node_projection("wf_seed", "node_homepage_visual")["latest_ticket_id"]

    set_ticket_time("2026-03-28T10:32:00+08:00")
    client.post(
        "/api/v1/commands/ticket-start",
        json=_ticket_start_payload(ticket_id=retried_ticket_id),
    )

    set_ticket_time("2026-03-28T11:18:00+08:00")
    client.post(
        "/api/v1/commands/scheduler-tick",
        json=_scheduler_tick_payload(idempotency_key="scheduler-tick:resolve-second"),
    )

    incident_id = [
        event["payload"]["incident_id"]
        for event in repository.list_events_for_testing()
        if event["event_type"] == EVENT_INCIDENT_OPENED
    ][0]

    set_ticket_time("2026-03-28T11:20:00+08:00")
    resolve_response = client.post(
        "/api/v1/commands/incident-resolve",
        json=_incident_resolve_payload(incident_id),
    )
    dashboard_response = client.get("/api/v1/projections/dashboard")
    inbox_response = client.get("/api/v1/projections/inbox")
    incident_response = client.get(f"/api/v1/projections/incidents/{incident_id}")
    duplicate_response = client.post(
        "/api/v1/commands/incident-resolve",
        json=_incident_resolve_payload(incident_id),
    )

    assert resolve_response.status_code == 200
    assert resolve_response.json()["status"] == "ACCEPTED"
    assert dashboard_response.json()["data"]["ops_strip"]["open_incidents"] == 0
    assert dashboard_response.json()["data"]["ops_strip"]["open_circuit_breakers"] == 0
    assert dashboard_response.json()["data"]["inbox_counts"]["incidents_pending"] == 0
    assert inbox_response.json()["data"]["items"] == []
    assert incident_response.json()["data"]["incident"]["status"] == "RECOVERING"
    assert incident_response.json()["data"]["incident"]["circuit_breaker_state"] == "CLOSED"
    assert incident_response.json()["data"]["incident"]["closed_at"] is None
    assert incident_response.json()["data"]["incident"]["payload"]["resolved_by"] == "emp_ops_1"
    assert incident_response.json()["data"]["incident"]["payload"]["followup_action"] == "RESTORE_ONLY"
    assert incident_response.json()["data"]["incident"]["payload"]["followup_ticket_id"] is None
    assert duplicate_response.status_code == 200
    assert duplicate_response.json()["status"] == "DUPLICATE"


def test_incident_resolve_can_restore_and_retry_latest_timeout_in_one_command(client, set_ticket_time):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    _create_lease_and_start_ticket(client, retry_budget=3)

    set_ticket_time("2026-03-28T10:31:00+08:00")
    client.post(
        "/api/v1/commands/scheduler-tick",
        json=_scheduler_tick_payload(idempotency_key="scheduler-tick:resolve-retry-first"),
    )

    repository = client.app.state.repository
    second_ticket_id = repository.get_current_node_projection("wf_seed", "node_homepage_visual")[
        "latest_ticket_id"
    ]

    set_ticket_time("2026-03-28T10:32:00+08:00")
    client.post(
        "/api/v1/commands/ticket-start",
        json=_ticket_start_payload(ticket_id=second_ticket_id),
    )

    set_ticket_time("2026-03-28T11:18:00+08:00")
    client.post(
        "/api/v1/commands/scheduler-tick",
        json=_scheduler_tick_payload(idempotency_key="scheduler-tick:resolve-retry-second"),
    )

    incident_id = [
        event["payload"]["incident_id"]
        for event in repository.list_events_for_testing()
        if event["event_type"] == EVENT_INCIDENT_OPENED
    ][0]
    retry_scheduled_before = repository.count_events_by_type(EVENT_TICKET_RETRY_SCHEDULED)

    set_ticket_time("2026-03-28T11:20:00+08:00")
    resolve_response = client.post(
        "/api/v1/commands/incident-resolve",
        json=_incident_resolve_payload(
            incident_id,
            idempotency_key="incident-resolve:restore-and-retry",
            followup_action="RESTORE_AND_RETRY_LATEST_TIMEOUT",
        ),
    )
    incident_response = client.get(f"/api/v1/projections/incidents/{incident_id}")

    latest_ticket_id = repository.get_current_node_projection("wf_seed", "node_homepage_visual")[
        "latest_ticket_id"
    ]
    latest_ticket = repository.get_current_ticket_projection(latest_ticket_id)

    set_ticket_time("2026-03-28T11:21:00+08:00")
    tick_response = client.post(
        "/api/v1/commands/scheduler-tick",
        json=_scheduler_tick_payload(idempotency_key="scheduler-tick:resolve-retry-third"),
    )
    leased_ticket = repository.get_current_ticket_projection(latest_ticket_id)

    assert resolve_response.status_code == 200
    assert resolve_response.json()["status"] == "ACCEPTED"
    assert latest_ticket_id not in {"tkt_visual_001", second_ticket_id}
    assert latest_ticket["status"] == TICKET_STATUS_PENDING
    assert latest_ticket["retry_count"] == 2
    assert repository.count_events_by_type(EVENT_TICKET_RETRY_SCHEDULED) == retry_scheduled_before + 1
    assert incident_response.json()["data"]["incident"]["payload"]["followup_action"] == (
        "RESTORE_AND_RETRY_LATEST_TIMEOUT"
    )
    assert incident_response.json()["data"]["incident"]["payload"]["followup_ticket_id"] == latest_ticket_id
    assert tick_response.status_code == 200
    assert tick_response.json()["status"] == "ACCEPTED"
    assert leased_ticket["status"] == TICKET_STATUS_LEASED


def test_incident_resolve_moves_incident_into_recovering_before_auto_close(client, set_ticket_time):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    _create_lease_and_start_ticket(client, retry_budget=3)

    set_ticket_time("2026-03-28T10:31:00+08:00")
    client.post(
        "/api/v1/commands/scheduler-tick",
        json=_scheduler_tick_payload(idempotency_key="scheduler-tick:recovering-first"),
    )

    repository = client.app.state.repository
    second_ticket_id = repository.get_current_node_projection("wf_seed", "node_homepage_visual")[
        "latest_ticket_id"
    ]

    set_ticket_time("2026-03-28T10:32:00+08:00")
    client.post(
        "/api/v1/commands/ticket-start",
        json=_ticket_start_payload(ticket_id=second_ticket_id),
    )

    set_ticket_time("2026-03-28T11:18:00+08:00")
    client.post(
        "/api/v1/commands/scheduler-tick",
        json=_scheduler_tick_payload(idempotency_key="scheduler-tick:recovering-second"),
    )

    incident_id = [
        event["payload"]["incident_id"]
        for event in repository.list_events_for_testing()
        if event["event_type"] == EVENT_INCIDENT_OPENED
    ][0]

    set_ticket_time("2026-03-28T11:20:00+08:00")
    resolve_response = client.post(
        "/api/v1/commands/incident-resolve",
        json=_incident_resolve_payload(
            incident_id,
            idempotency_key="incident-resolve:recovering-timeout",
            followup_action="RESTORE_AND_RETRY_LATEST_TIMEOUT",
        ),
    )
    incident_response = client.get(f"/api/v1/projections/incidents/{incident_id}")
    recovery_events = [
        event
        for event in repository.list_events_for_testing()
        if event["event_type"] == EVENT_INCIDENT_RECOVERY_STARTED
    ]

    assert resolve_response.status_code == 200
    assert resolve_response.json()["status"] == "ACCEPTED"
    assert incident_response.json()["data"]["incident"]["status"] == "RECOVERING"
    assert incident_response.json()["data"]["incident"]["circuit_breaker_state"] == "CLOSED"
    assert incident_response.json()["data"]["incident"]["closed_at"] is None
    assert recovery_events


def test_incident_resolve_reopens_scheduler_dispatch_for_same_node(client, set_ticket_time):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    _create_lease_and_start_ticket(client, retry_budget=2)

    set_ticket_time("2026-03-28T10:31:00+08:00")
    client.post(
        "/api/v1/commands/scheduler-tick",
        json=_scheduler_tick_payload(idempotency_key="scheduler-tick:breaker-reopen-first"),
    )

    repository = client.app.state.repository
    retried_ticket_id = repository.get_current_node_projection("wf_seed", "node_homepage_visual")["latest_ticket_id"]

    set_ticket_time("2026-03-28T10:32:00+08:00")
    client.post(
        "/api/v1/commands/ticket-start",
        json=_ticket_start_payload(ticket_id=retried_ticket_id),
    )

    set_ticket_time("2026-03-28T11:18:00+08:00")
    client.post(
        "/api/v1/commands/scheduler-tick",
        json=_scheduler_tick_payload(idempotency_key="scheduler-tick:breaker-reopen-second"),
    )

    incident_id = [
        event["payload"]["incident_id"]
        for event in repository.list_events_for_testing()
        if event["event_type"] == EVENT_INCIDENT_OPENED
    ][0]

    set_ticket_time("2026-03-28T11:20:00+08:00")
    client.post(
        "/api/v1/commands/incident-resolve",
        json=_incident_resolve_payload(incident_id, idempotency_key="incident-resolve:reopen"),
    )
    client.post(
        "/api/v1/commands/ticket-create",
        json=_ticket_create_payload(
            ticket_id="tkt_visual_003",
            attempt_no=3,
            retry_budget=2,
        ),
    )

    set_ticket_time("2026-03-28T11:21:00+08:00")
    tick_response = client.post(
        "/api/v1/commands/scheduler-tick",
        json=_scheduler_tick_payload(idempotency_key="scheduler-tick:breaker-reopen-third"),
    )
    ticket_projection = repository.get_current_ticket_projection("tkt_visual_003")

    assert tick_response.status_code == 200
    assert tick_response.json()["status"] == "ACCEPTED"
    assert ticket_projection is not None
    assert ticket_projection["status"] == TICKET_STATUS_LEASED
    assert ticket_projection["lease_owner"] == "emp_frontend_2"


def test_incident_resolve_rejects_missing_or_closed_incidents(client, set_ticket_time):
    missing_response = client.post(
        "/api/v1/commands/incident-resolve",
        json=_incident_resolve_payload("inc_missing", idempotency_key="incident-resolve:missing"),
    )

    assert missing_response.status_code == 200
    assert missing_response.json()["status"] == "REJECTED"

    set_ticket_time("2026-03-28T10:00:00+08:00")
    _create_lease_and_start_ticket(client, retry_budget=2)

    set_ticket_time("2026-03-28T10:31:00+08:00")
    client.post(
        "/api/v1/commands/scheduler-tick",
        json=_scheduler_tick_payload(idempotency_key="scheduler-tick:reject-first"),
    )

    repository = client.app.state.repository
    retried_ticket_id = repository.get_current_node_projection("wf_seed", "node_homepage_visual")["latest_ticket_id"]

    set_ticket_time("2026-03-28T10:32:00+08:00")
    client.post(
        "/api/v1/commands/ticket-start",
        json=_ticket_start_payload(ticket_id=retried_ticket_id),
    )

    set_ticket_time("2026-03-28T11:18:00+08:00")
    client.post(
        "/api/v1/commands/scheduler-tick",
        json=_scheduler_tick_payload(idempotency_key="scheduler-tick:reject-second"),
    )

    incident_id = [
        event["payload"]["incident_id"]
        for event in repository.list_events_for_testing()
        if event["event_type"] == EVENT_INCIDENT_OPENED
    ][0]

    set_ticket_time("2026-03-28T11:20:00+08:00")
    first_response = client.post(
        "/api/v1/commands/incident-resolve",
        json=_incident_resolve_payload(incident_id, idempotency_key="incident-resolve:first-close"),
    )
    second_response = client.post(
        "/api/v1/commands/incident-resolve",
        json=_incident_resolve_payload(incident_id, idempotency_key="incident-resolve:second-close"),
    )

    assert first_response.status_code == 200
    assert first_response.json()["status"] == "ACCEPTED"
    assert second_response.status_code == 200
    assert second_response.json()["status"] == "REJECTED"


def test_incident_resolve_restore_and_retry_can_override_exhausted_retry_budget(client, set_ticket_time):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    _create_lease_and_start_ticket(client, retry_budget=1)

    set_ticket_time("2026-03-28T10:31:00+08:00")
    client.post(
        "/api/v1/commands/scheduler-tick",
        json=_scheduler_tick_payload(idempotency_key="scheduler-tick:budget-first"),
    )

    repository = client.app.state.repository
    second_ticket_id = repository.get_current_node_projection("wf_seed", "node_homepage_visual")[
        "latest_ticket_id"
    ]

    set_ticket_time("2026-03-28T10:32:00+08:00")
    client.post(
        "/api/v1/commands/ticket-start",
        json=_ticket_start_payload(ticket_id=second_ticket_id),
    )

    set_ticket_time("2026-03-28T11:18:00+08:00")
    client.post(
        "/api/v1/commands/scheduler-tick",
        json=_scheduler_tick_payload(idempotency_key="scheduler-tick:budget-second"),
    )

    incident_id = [
        event["payload"]["incident_id"]
        for event in repository.list_events_for_testing()
        if event["event_type"] == EVENT_INCIDENT_OPENED
    ][0]

    set_ticket_time("2026-03-28T11:20:00+08:00")
    response = client.post(
        "/api/v1/commands/incident-resolve",
        json=_incident_resolve_payload(
            incident_id,
            idempotency_key="incident-resolve:budget-exhausted",
            followup_action="RESTORE_AND_RETRY_LATEST_TIMEOUT",
        ),
    )
    incident_response = client.get(f"/api/v1/projections/incidents/{incident_id}")
    followup_ticket_id = repository.get_current_node_projection("wf_seed", "node_homepage_visual")[
        "latest_ticket_id"
    ]
    followup_ticket = repository.get_current_ticket_projection(followup_ticket_id)

    assert response.status_code == 200
    assert response.json()["status"] == "ACCEPTED"
    assert followup_ticket_id not in {"tkt_visual_001", second_ticket_id}
    assert followup_ticket is not None
    assert followup_ticket["status"] == TICKET_STATUS_PENDING
    assert followup_ticket["retry_count"] == 2
    assert incident_response.json()["data"]["incident"]["status"] == "RECOVERING"
    assert incident_response.json()["data"]["incident"]["payload"]["followup_action"] == (
        "RESTORE_AND_RETRY_LATEST_TIMEOUT"
    )
    assert incident_response.json()["data"]["incident"]["payload"]["followup_ticket_id"] == followup_ticket_id
    assert repository.count_events_by_type(EVENT_TICKET_RETRY_SCHEDULED) == 2


def test_incident_resolve_restore_and_retry_rejects_when_source_ticket_spec_is_missing(
    client,
    set_ticket_time,
):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    _create_lease_and_start_ticket(client, retry_budget=2)

    set_ticket_time("2026-03-28T10:31:00+08:00")
    client.post(
        "/api/v1/commands/scheduler-tick",
        json=_scheduler_tick_payload(idempotency_key="scheduler-tick:missing-spec-first"),
    )

    repository = client.app.state.repository
    second_ticket_id = repository.get_current_node_projection("wf_seed", "node_homepage_visual")[
        "latest_ticket_id"
    ]

    set_ticket_time("2026-03-28T10:32:00+08:00")
    client.post(
        "/api/v1/commands/ticket-start",
        json=_ticket_start_payload(ticket_id=second_ticket_id),
    )

    set_ticket_time("2026-03-28T11:18:00+08:00")
    client.post(
        "/api/v1/commands/scheduler-tick",
        json=_scheduler_tick_payload(idempotency_key="scheduler-tick:missing-spec-second"),
    )

    incident_id = [
        event["payload"]["incident_id"]
        for event in repository.list_events_for_testing()
        if event["event_type"] == EVENT_INCIDENT_OPENED
    ][0]

    with repository.transaction() as connection:
        connection.execute(
            """
            DELETE FROM events
            WHERE event_type = 'TICKET_CREATED' AND json_extract(payload_json, '$.ticket_id') = ?
            """,
            (second_ticket_id,),
        )

    set_ticket_time("2026-03-28T11:20:00+08:00")
    response = client.post(
        "/api/v1/commands/incident-resolve",
        json=_incident_resolve_payload(
            incident_id,
            idempotency_key="incident-resolve:missing-spec",
            followup_action="RESTORE_AND_RETRY_LATEST_TIMEOUT",
        ),
    )

    assert response.status_code == 200
    assert response.json()["status"] == "REJECTED"
    assert "created spec" in response.json()["reason"].lower()


def test_incident_resolve_restore_and_retry_rejects_when_latest_terminal_event_is_not_timeout(
    client,
    set_ticket_time,
):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    _create_lease_and_start_ticket(client, retry_budget=2)

    set_ticket_time("2026-03-28T10:31:00+08:00")
    client.post(
        "/api/v1/commands/scheduler-tick",
        json=_scheduler_tick_payload(idempotency_key="scheduler-tick:not-timeout-first"),
    )

    repository = client.app.state.repository
    second_ticket_id = repository.get_current_node_projection("wf_seed", "node_homepage_visual")[
        "latest_ticket_id"
    ]

    set_ticket_time("2026-03-28T10:32:00+08:00")
    client.post(
        "/api/v1/commands/ticket-start",
        json=_ticket_start_payload(ticket_id=second_ticket_id),
    )

    set_ticket_time("2026-03-28T11:18:00+08:00")
    client.post(
        "/api/v1/commands/scheduler-tick",
        json=_scheduler_tick_payload(idempotency_key="scheduler-tick:not-timeout-second"),
    )

    incident_id = [
        event["payload"]["incident_id"]
        for event in repository.list_events_for_testing()
        if event["event_type"] == EVENT_INCIDENT_OPENED
    ][0]

    with repository.transaction() as connection:
        repository.insert_event(
            connection,
            event_type=EVENT_TICKET_FAILED,
            actor_type="system",
            actor_id="test",
            workflow_id="wf_seed",
            idempotency_key="test:not-timeout-terminal",
            causation_id="cmd_test_not_timeout",
            correlation_id="wf_seed",
            payload={
                "ticket_id": second_ticket_id,
                "node_id": "node_homepage_visual",
                "failure_kind": "RUNTIME_ERROR",
                "failure_message": "Injected non-timeout terminal event for guard coverage.",
                "failure_detail": {},
                "failure_fingerprint": "test-not-timeout",
            },
            occurred_at=set_ticket_time("2026-03-28T11:19:00+08:00"),
        )
        repository.refresh_projections(connection)

    response = client.post(
        "/api/v1/commands/incident-resolve",
        json=_incident_resolve_payload(
            incident_id,
            idempotency_key="incident-resolve:not-timeout",
            followup_action="RESTORE_AND_RETRY_LATEST_TIMEOUT",
        ),
    )

    assert response.status_code == 200
    assert response.json()["status"] == "REJECTED"
    assert "latest terminal" in response.json()["reason"].lower()


def test_provider_failure_opens_provider_incident_blocks_same_provider_and_updates_dashboard(
    client,
    set_ticket_time,
):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    _create_lease_and_start_ticket(client, retry_budget=2)
    _seed_worker(
        client,
        employee_id="emp_frontend_backup",
        provider_id="prov_backup",
    )

    set_ticket_time("2026-03-28T10:05:00+08:00")
    fail_response = client.post(
        "/api/v1/commands/ticket-fail",
        json=_ticket_fail_payload(
            failure_kind="PROVIDER_RATE_LIMITED",
            failure_message="Provider quota exhausted.",
            failure_detail={
                "provider_id": "prov_openai_compat",
                "provider_status_code": 429,
            },
        ),
    )

    repository = client.app.state.repository
    provider_incident_id = [
        event["payload"]["incident_id"]
        for event in repository.list_events_for_testing()
        if event["event_type"] == EVENT_INCIDENT_OPENED
    ][0]

    create_same_provider = client.post(
        "/api/v1/commands/ticket-create",
        json=_ticket_create_payload(
            ticket_id="tkt_provider_blocked",
            node_id="node_provider_blocked",
        ),
    )
    create_fallback = client.post(
        "/api/v1/commands/ticket-create",
        json=_ticket_create_payload(
            ticket_id="tkt_provider_fallback",
            node_id="node_provider_fallback",
        ),
    )
    blocked_lease = client.post(
        "/api/v1/commands/ticket-lease",
        json=_ticket_lease_payload(
            ticket_id="tkt_provider_blocked",
            node_id="node_provider_blocked",
        ),
    )

    set_ticket_time("2026-03-28T10:06:00+08:00")
    tick_response = client.post(
        "/api/v1/commands/scheduler-tick",
        json=_scheduler_tick_payload(idempotency_key="scheduler-tick:provider-block"),
    )
    dashboard_response = client.get("/api/v1/projections/dashboard")
    inbox_response = client.get("/api/v1/projections/inbox")
    incident_response = client.get(f"/api/v1/projections/incidents/{provider_incident_id}")

    blocked_ticket = repository.get_current_ticket_projection("tkt_provider_blocked")
    fallback_ticket = repository.get_current_ticket_projection("tkt_provider_fallback")

    assert fail_response.status_code == 200
    assert fail_response.json()["status"] == "ACCEPTED"
    assert repository.count_events_by_type(EVENT_TICKET_RETRY_SCHEDULED) == 0
    assert create_same_provider.status_code == 200
    assert create_same_provider.json()["status"] == "ACCEPTED"
    assert create_fallback.status_code == 200
    assert create_fallback.json()["status"] == "ACCEPTED"
    assert blocked_lease.status_code == 200
    assert blocked_lease.json()["status"] == "REJECTED"
    assert "currently paused" in blocked_lease.json()["reason"].lower()
    assert tick_response.status_code == 200
    assert tick_response.json()["status"] == "ACCEPTED"
    leased_tickets = [
        ticket
        for ticket in (blocked_ticket, fallback_ticket)
        if ticket is not None and ticket["status"] == TICKET_STATUS_LEASED
    ]
    pending_tickets = [
        ticket
        for ticket in (blocked_ticket, fallback_ticket)
        if ticket is not None and ticket["status"] == TICKET_STATUS_PENDING
    ]
    assert len(leased_tickets) == 1
    assert leased_tickets[0]["lease_owner"] == "emp_frontend_backup"
    assert len(pending_tickets) == 1
    assert pending_tickets[0]["lease_owner"] is None
    assert dashboard_response.json()["data"]["ops_strip"]["provider_health_summary"] == "PAUSED"
    assert dashboard_response.json()["data"]["inbox_counts"]["provider_alerts"] == 1
    incident_items = [
        item for item in inbox_response.json()["data"]["items"] if item["item_type"] == "PROVIDER_INCIDENT"
    ]
    assert len(incident_items) == 1
    assert incident_response.json()["data"]["incident"]["provider_id"] == "prov_openai_compat"
    assert incident_response.json()["data"]["incident"]["incident_type"] == "PROVIDER_EXECUTION_PAUSED"
    assert incident_response.json()["data"]["incident"]["payload"]["pause_reason"] == "PROVIDER_RATE_LIMITED"
    assert incident_response.json()["data"]["available_followup_actions"] == [
        "RESTORE_ONLY",
        "RESTORE_AND_RETRY_LATEST_PROVIDER_FAILURE",
    ]
    assert incident_response.json()["data"]["recommended_followup_action"] == (
        "RESTORE_AND_RETRY_LATEST_PROVIDER_FAILURE"
    )


def test_provider_incident_resolve_can_restore_and_retry_latest_provider_failure(client, set_ticket_time):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    _create_lease_and_start_ticket(client, retry_budget=2)

    set_ticket_time("2026-03-28T10:05:00+08:00")
    client.post(
        "/api/v1/commands/ticket-fail",
        json=_ticket_fail_payload(
            failure_kind="UPSTREAM_UNAVAILABLE",
            failure_message="Provider upstream returned 503.",
            failure_detail={
                "provider_id": "prov_openai_compat",
                "provider_status_code": 503,
            },
        ),
    )

    repository = client.app.state.repository
    incident_id = [
        event["payload"]["incident_id"]
        for event in repository.list_events_for_testing()
        if event["event_type"] == EVENT_INCIDENT_OPENED
    ][0]

    create_response = client.post(
        "/api/v1/commands/ticket-create",
        json=_ticket_create_payload(
            ticket_id="tkt_provider_resume",
            node_id="node_provider_resume",
        ),
    )
    set_ticket_time("2026-03-28T10:06:00+08:00")
    blocked_tick = client.post(
        "/api/v1/commands/scheduler-tick",
        json=_scheduler_tick_payload(idempotency_key="scheduler-tick:provider-before-resolve"),
    )
    blocked_ticket = repository.get_current_ticket_projection("tkt_provider_resume")

    set_ticket_time("2026-03-28T10:07:00+08:00")
    resolve_response = client.post(
        "/api/v1/commands/incident-resolve",
        json=_incident_resolve_payload(
            incident_id,
            idempotency_key="incident-resolve:provider-retry",
            followup_action="RESTORE_AND_RETRY_LATEST_PROVIDER_FAILURE",
        ),
    )
    incident_response = client.get(f"/api/v1/projections/incidents/{incident_id}")

    followup_ticket_id = repository.get_current_node_projection("wf_seed", "node_homepage_visual")[
        "latest_ticket_id"
    ]
    followup_ticket = repository.get_current_ticket_projection(followup_ticket_id)

    set_ticket_time("2026-03-28T10:08:00+08:00")
    resumed_tick = client.post(
        "/api/v1/commands/scheduler-tick",
        json=_scheduler_tick_payload(idempotency_key="scheduler-tick:provider-after-resolve"),
    )
    resumed_ticket = repository.get_current_ticket_projection("tkt_provider_resume")
    dashboard_response = client.get("/api/v1/projections/dashboard")

    assert create_response.status_code == 200
    assert create_response.json()["status"] == "ACCEPTED"
    assert blocked_tick.status_code == 200
    assert blocked_tick.json()["status"] == "ACCEPTED"
    assert blocked_ticket["status"] == TICKET_STATUS_PENDING


def test_repeated_failure_opens_incident_and_blocks_same_node_dispatch(client, set_ticket_time):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    _create_lease_and_start_ticket(client, retry_budget=3, repeat_failure_threshold=2)

    first_failure = {
        "step": "render",
        "exit_code": 1,
        "component": "hero",
    }
    set_ticket_time("2026-03-28T10:05:00+08:00")
    first_fail_response = client.post(
        "/api/v1/commands/ticket-fail",
        json=_ticket_fail_payload(
            failure_message="Primary hero render crashed.",
            failure_detail=first_failure,
        ),
    )

    repository = client.app.state.repository
    second_ticket_id = repository.get_current_node_projection("wf_seed", "node_homepage_visual")[
        "latest_ticket_id"
    ]

    set_ticket_time("2026-03-28T10:06:00+08:00")
    second_lease_response = client.post(
        "/api/v1/commands/ticket-lease",
        json=_ticket_lease_payload(ticket_id=second_ticket_id),
    )
    second_start_response = client.post(
        "/api/v1/commands/ticket-start",
        json=_ticket_start_payload(ticket_id=second_ticket_id),
    )

    set_ticket_time("2026-03-28T10:07:00+08:00")
    second_fail_response = client.post(
        "/api/v1/commands/ticket-fail",
        json=_ticket_fail_payload(
            ticket_id=second_ticket_id,
            failure_message="Primary hero render crashed.",
            failure_detail=first_failure,
        ),
    )

    incident_id = [
        event["payload"]["incident_id"]
        for event in repository.list_events_for_testing()
        if event["event_type"] == EVENT_INCIDENT_OPENED
    ][0]

    create_blocked_response = client.post(
        "/api/v1/commands/ticket-create",
        json=_ticket_create_payload(
            ticket_id="tkt_failure_blocked",
            node_id="node_homepage_visual",
        ),
    )
    set_ticket_time("2026-03-28T10:08:00+08:00")
    scheduler_response = client.post(
        "/api/v1/commands/scheduler-tick",
        json=_scheduler_tick_payload(idempotency_key="scheduler-tick:repeat-failure-breaker"),
    )
    blocked_ticket = repository.get_current_ticket_projection("tkt_failure_blocked")
    inbox_response = client.get("/api/v1/projections/inbox")
    incident_response = client.get(f"/api/v1/projections/incidents/{incident_id}")

    assert first_fail_response.status_code == 200
    assert first_fail_response.json()["status"] == "ACCEPTED"
    assert second_lease_response.status_code == 200
    assert second_lease_response.json()["status"] == "ACCEPTED"
    assert second_start_response.status_code == 200
    assert second_start_response.json()["status"] == "ACCEPTED"
    assert second_fail_response.status_code == 200
    assert second_fail_response.json()["status"] == "ACCEPTED"
    assert repository.count_events_by_type(EVENT_TICKET_RETRY_SCHEDULED) == 1
    assert repository.count_events_by_type(EVENT_INCIDENT_OPENED) == 1
    assert repository.count_events_by_type(EVENT_CIRCUIT_BREAKER_OPENED) == 1
    assert create_blocked_response.status_code == 200
    assert create_blocked_response.json()["status"] == "ACCEPTED"
    assert scheduler_response.status_code == 200
    assert scheduler_response.json()["status"] == "ACCEPTED"
    assert blocked_ticket["status"] == TICKET_STATUS_PENDING
    assert incident_response.json()["data"]["incident"]["incident_type"] == "REPEATED_FAILURE_ESCALATION"
    assert incident_response.json()["data"]["incident"]["payload"]["failure_streak_count"] == 2
    assert incident_response.json()["data"]["incident"]["payload"]["latest_failure_kind"] == "RUNTIME_ERROR"
    assert incident_response.json()["data"]["available_followup_actions"] == [
        "RESTORE_ONLY",
        "RESTORE_AND_RETRY_LATEST_FAILURE",
    ]
    assert incident_response.json()["data"]["recommended_followup_action"] == (
        "RESTORE_AND_RETRY_LATEST_FAILURE"
    )
    incident_items = [
        item for item in inbox_response.json()["data"]["items"] if item["item_type"] == "INCIDENT_ESCALATION"
    ]
    assert len(incident_items) == 1
    assert "Repeated failure escalation" in incident_items[0]["title"]


def test_repeated_failure_with_different_fingerprint_keeps_retrying_without_incident(
    client,
    set_ticket_time,
):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    _create_lease_and_start_ticket(client, retry_budget=3, repeat_failure_threshold=2)

    set_ticket_time("2026-03-28T10:05:00+08:00")
    client.post(
        "/api/v1/commands/ticket-fail",
        json=_ticket_fail_payload(
            failure_message="Primary hero render crashed.",
            failure_detail={"step": "render", "exit_code": 1},
        ),
    )

    repository = client.app.state.repository
    second_ticket_id = repository.get_current_node_projection("wf_seed", "node_homepage_visual")[
        "latest_ticket_id"
    ]

    set_ticket_time("2026-03-28T10:06:00+08:00")
    client.post(
        "/api/v1/commands/ticket-lease",
        json=_ticket_lease_payload(ticket_id=second_ticket_id),
    )
    client.post(
        "/api/v1/commands/ticket-start",
        json=_ticket_start_payload(ticket_id=second_ticket_id),
    )

    set_ticket_time("2026-03-28T10:07:00+08:00")
    second_fail_response = client.post(
        "/api/v1/commands/ticket-fail",
        json=_ticket_fail_payload(
            ticket_id=second_ticket_id,
            failure_message="Secondary export step crashed.",
            failure_detail={"step": "export", "exit_code": 9},
        ),
    )

    latest_ticket_id = repository.get_current_node_projection("wf_seed", "node_homepage_visual")[
        "latest_ticket_id"
    ]
    latest_ticket = repository.get_current_ticket_projection(latest_ticket_id)

    assert second_fail_response.status_code == 200
    assert second_fail_response.json()["status"] == "ACCEPTED"
    assert repository.count_events_by_type(EVENT_INCIDENT_OPENED) == 0
    assert repository.count_events_by_type(EVENT_CIRCUIT_BREAKER_OPENED) == 0
    assert repository.count_events_by_type(EVENT_TICKET_RETRY_SCHEDULED) == 2
    assert latest_ticket["status"] == TICKET_STATUS_PENDING


def test_incident_resolve_can_restore_and_retry_latest_failure_in_one_command(client, set_ticket_time):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    _create_lease_and_start_ticket(client, retry_budget=3, repeat_failure_threshold=2)

    repeated_failure = {
        "step": "render",
        "exit_code": 1,
        "component": "hero",
    }
    set_ticket_time("2026-03-28T10:05:00+08:00")
    client.post(
        "/api/v1/commands/ticket-fail",
        json=_ticket_fail_payload(
            failure_message="Primary hero render crashed.",
            failure_detail=repeated_failure,
        ),
    )

    repository = client.app.state.repository
    second_ticket_id = repository.get_current_node_projection("wf_seed", "node_homepage_visual")[
        "latest_ticket_id"
    ]

    set_ticket_time("2026-03-28T10:06:00+08:00")
    client.post(
        "/api/v1/commands/ticket-lease",
        json=_ticket_lease_payload(ticket_id=second_ticket_id),
    )
    client.post(
        "/api/v1/commands/ticket-start",
        json=_ticket_start_payload(ticket_id=second_ticket_id),
    )

    set_ticket_time("2026-03-28T10:07:00+08:00")
    client.post(
        "/api/v1/commands/ticket-fail",
        json=_ticket_fail_payload(
            ticket_id=second_ticket_id,
            failure_message="Primary hero render crashed.",
            failure_detail=repeated_failure,
        ),
    )

    incident_id = [
        event["payload"]["incident_id"]
        for event in repository.list_events_for_testing()
        if event["event_type"] == EVENT_INCIDENT_OPENED
    ][0]

    set_ticket_time("2026-03-28T10:08:00+08:00")
    resolve_response = client.post(
        "/api/v1/commands/incident-resolve",
        json=_incident_resolve_payload(
            incident_id,
            idempotency_key="incident-resolve:repeat-failure-retry",
            followup_action="RESTORE_AND_RETRY_LATEST_FAILURE",
        ),
    )
    incident_response = client.get(f"/api/v1/projections/incidents/{incident_id}")
    followup_ticket_id = repository.get_current_node_projection("wf_seed", "node_homepage_visual")[
        "latest_ticket_id"
    ]
    followup_ticket = repository.get_current_ticket_projection(followup_ticket_id)

    assert resolve_response.status_code == 200
    assert resolve_response.json()["status"] == "ACCEPTED"
    assert followup_ticket_id not in {"tkt_visual_001", second_ticket_id}
    assert followup_ticket["status"] == TICKET_STATUS_PENDING
    assert followup_ticket["retry_count"] == 2
    assert incident_response.json()["data"]["incident"]["payload"]["followup_action"] == (
        "RESTORE_AND_RETRY_LATEST_FAILURE"
    )
    assert incident_response.json()["data"]["incident"]["payload"]["followup_ticket_id"] == followup_ticket_id


def test_incident_resolve_restore_and_retry_latest_failure_can_override_exhausted_retry_budget(
    client,
    set_ticket_time,
):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    _create_lease_and_start_ticket(client, retry_budget=1, repeat_failure_threshold=2)

    repeated_failure = {
        "step": "render",
        "exit_code": 1,
        "component": "hero",
    }
    set_ticket_time("2026-03-28T10:05:00+08:00")
    client.post(
        "/api/v1/commands/ticket-fail",
        json=_ticket_fail_payload(
            failure_message="Primary hero render crashed.",
            failure_detail=repeated_failure,
        ),
    )

    repository = client.app.state.repository
    second_ticket_id = repository.get_current_node_projection("wf_seed", "node_homepage_visual")[
        "latest_ticket_id"
    ]

    set_ticket_time("2026-03-28T10:06:00+08:00")
    client.post(
        "/api/v1/commands/ticket-lease",
        json=_ticket_lease_payload(ticket_id=second_ticket_id),
    )
    client.post(
        "/api/v1/commands/ticket-start",
        json=_ticket_start_payload(ticket_id=second_ticket_id),
    )

    set_ticket_time("2026-03-28T10:07:00+08:00")
    client.post(
        "/api/v1/commands/ticket-fail",
        json=_ticket_fail_payload(
            ticket_id=second_ticket_id,
            failure_message="Primary hero render crashed.",
            failure_detail=repeated_failure,
        ),
    )

    incident_id = [
        event["payload"]["incident_id"]
        for event in repository.list_events_for_testing()
        if event["event_type"] == EVENT_INCIDENT_OPENED
    ][0]

    set_ticket_time("2026-03-28T10:08:00+08:00")
    resolve_response = client.post(
        "/api/v1/commands/incident-resolve",
        json=_incident_resolve_payload(
            incident_id,
            idempotency_key="incident-resolve:repeat-failure-budget",
            followup_action="RESTORE_AND_RETRY_LATEST_FAILURE",
        ),
    )
    incident_response = client.get(f"/api/v1/projections/incidents/{incident_id}")
    followup_ticket_id = repository.get_current_node_projection("wf_seed", "node_homepage_visual")[
        "latest_ticket_id"
    ]
    followup_ticket = repository.get_current_ticket_projection(followup_ticket_id)

    assert resolve_response.status_code == 200
    assert resolve_response.json()["status"] == "ACCEPTED"
    assert followup_ticket_id not in {"tkt_visual_001", second_ticket_id}
    assert followup_ticket is not None
    assert followup_ticket["status"] == TICKET_STATUS_PENDING
    assert followup_ticket["retry_count"] == 2
    assert incident_response.json()["data"]["incident"]["status"] == "RECOVERING"
    assert incident_response.json()["data"]["incident"]["payload"]["followup_action"] == (
        "RESTORE_AND_RETRY_LATEST_FAILURE"
    )
    assert incident_response.json()["data"]["incident"]["payload"]["followup_ticket_id"] == followup_ticket_id


def test_provider_failure_still_uses_provider_incident_path_not_repeated_failure_incident(
    client,
    set_ticket_time,
):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    _create_lease_and_start_ticket(client, retry_budget=3, repeat_failure_threshold=1)

    set_ticket_time("2026-03-28T10:05:00+08:00")
    fail_response = client.post(
        "/api/v1/commands/ticket-fail",
        json=_ticket_fail_payload(
            failure_kind="PROVIDER_RATE_LIMITED",
            failure_message="Provider quota exhausted.",
            failure_detail={
                "provider_id": "prov_openai_compat",
                "provider_status_code": 429,
            },
        ),
    )

    repository = client.app.state.repository
    incident_response = client.get(
        f"/api/v1/projections/incidents/{[event['payload']['incident_id'] for event in repository.list_events_for_testing() if event['event_type'] == EVENT_INCIDENT_OPENED][0]}"
    )

    assert fail_response.status_code == 200
    assert fail_response.json()["status"] == "ACCEPTED"
    assert repository.count_events_by_type(EVENT_INCIDENT_OPENED) == 1
    assert incident_response.json()["data"]["incident"]["incident_type"] == "PROVIDER_EXECUTION_PAUSED"


def test_scheduler_tick_reclaims_expired_lease_and_dispatches_matching_worker(client, set_ticket_time):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    _create_and_lease_ticket(client, lease_timeout_sec=60, leased_by="emp_checker_1")

    set_ticket_time("2026-03-28T10:02:00+08:00")
    response = client.post(
        "/api/v1/commands/scheduler-tick",
        json=_scheduler_tick_payload(
            workers=[
                {"employee_id": "emp_frontend_2", "role_profile_refs": ["frontend_engineer_primary"]},
                {"employee_id": "emp_checker_1", "role_profile_refs": ["checker_primary"]},
            ],
            idempotency_key="scheduler-tick:expired-lease",
        ),
    )
    ticket_projection = client.app.state.repository.get_current_ticket_projection("tkt_visual_001")

    assert response.status_code == 200
    assert response.json()["status"] == "ACCEPTED"
    assert client.app.state.repository.count_events_by_type(EVENT_TICKET_LEASED) == 2
    assert ticket_projection["status"] == TICKET_STATUS_LEASED
    assert ticket_projection["lease_owner"] == "emp_frontend_2"


def test_scheduler_tick_does_not_auto_start_ticket(client, set_ticket_time):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    client.post("/api/v1/commands/ticket-create", json=_ticket_create_payload())

    set_ticket_time("2026-03-28T10:01:00+08:00")
    response = client.post("/api/v1/commands/scheduler-tick", json=_scheduler_tick_payload())
    ticket_projection = client.app.state.repository.get_current_ticket_projection("tkt_visual_001")
    node_projection = client.app.state.repository.get_current_node_projection(
        "wf_seed",
        "node_homepage_visual",
    )

    assert response.status_code == 200
    assert response.json()["status"] == "ACCEPTED"
    assert ticket_projection["status"] == TICKET_STATUS_LEASED
    assert node_projection["status"] == NODE_STATUS_PENDING


def test_scheduler_tick_skips_busy_worker_and_role_mismatch(client, set_ticket_time):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    _create_lease_and_start_ticket(
        client,
        workflow_id="wf_busy",
        ticket_id="tkt_busy",
        node_id="node_busy",
        role_profile_ref="frontend_engineer_primary",
    )
    client.post(
        "/api/v1/commands/ticket-create",
        json=_ticket_create_payload(
            workflow_id="wf_busy",
            ticket_id="tkt_pending",
            node_id="node_pending",
            role_profile_ref="frontend_engineer_primary",
        ),
    )

    set_ticket_time("2026-03-28T10:05:00+08:00")
    response = client.post(
        "/api/v1/commands/scheduler-tick",
        json=_scheduler_tick_payload(
            workers=[
                {"employee_id": "emp_frontend_2", "role_profile_refs": ["frontend_engineer_primary"]},
                {"employee_id": "emp_checker_1", "role_profile_refs": ["checker_primary"]},
            ],
            idempotency_key="scheduler-tick:busy",
        ),
    )
    ticket_projection = client.app.state.repository.get_current_ticket_projection("tkt_pending")

    assert response.status_code == 200
    assert response.json()["status"] == "ACCEPTED"
    assert ticket_projection["status"] == TICKET_STATUS_PENDING
    assert ticket_projection["lease_owner"] is None


def test_scheduler_tick_dispatches_to_explicit_assignee_from_dispatch_intent(client, set_ticket_time):
    repository = client.app.state.repository
    with repository.transaction() as connection:
        repository.insert_event(
            connection,
            event_type="EMPLOYEE_HIRED",
            actor_type="system",
            actor_id="test-seed",
            workflow_id=None,
            idempotency_key="test-seed-employee:emp_frontend_backup",
            causation_id=None,
            correlation_id=None,
            payload={
                "employee_id": "emp_frontend_backup",
                "role_type": "frontend_engineer",
                "skill_profile": {},
                "personality_profile": {},
                "aesthetic_profile": {},
                "state": "ACTIVE",
                "board_approved": True,
                "provider_id": "prov_openai_compat",
                "role_profile_refs": ["frontend_engineer_primary"],
            },
            occurred_at=datetime.fromisoformat("2026-03-28T09:59:00+08:00"),
        )
        repository.refresh_projections(connection)

    set_ticket_time("2026-03-28T10:00:00+08:00")
    create_response = client.post(
        "/api/v1/commands/ticket-create",
        json=_ticket_create_payload(
            workflow_id="wf_seed",
            ticket_id="tkt_dispatch_intent_fixed",
            node_id="node_dispatch_intent_fixed",
            role_profile_ref="frontend_engineer_primary",
            dispatch_intent={
                "assignee_employee_id": "emp_frontend_backup",
                "selection_reason": "CEO already reserved the backup maker for this ticket.",
            },
        ),
    )
    assert create_response.status_code == 200
    assert create_response.json()["status"] == "ACCEPTED"

    set_ticket_time("2026-03-28T10:01:00+08:00")
    response = client.post(
        "/api/v1/commands/scheduler-tick",
        json=_scheduler_tick_payload(idempotency_key="scheduler-tick:dispatch-intent-fixed"),
    )
    ticket_projection = client.app.state.repository.get_current_ticket_projection("tkt_dispatch_intent_fixed")

    assert response.status_code == 200
    assert response.json()["status"] == "ACCEPTED"
    assert ticket_projection["status"] == TICKET_STATUS_LEASED
    assert ticket_projection["lease_owner"] == "emp_frontend_backup"


def test_ticket_create_is_rejected_when_dispatch_intent_dependency_gate_is_invalid(client):
    self_dependency_response = client.post(
        "/api/v1/commands/ticket-create",
        json=_ticket_create_payload(
            workflow_id="wf_seed",
            ticket_id="tkt_dependency_self",
            node_id="node_dependency_self",
            role_profile_ref="frontend_engineer_primary",
            dispatch_intent={
                "assignee_employee_id": "emp_frontend_2",
                "selection_reason": "CEO selected the primary frontend maker.",
                "dependency_gate_refs": ["tkt_dependency_self"],
            },
        ),
    )
    missing_dependency_response = client.post(
        "/api/v1/commands/ticket-create",
        json=_ticket_create_payload(
            workflow_id="wf_seed",
            ticket_id="tkt_dependency_missing",
            node_id="node_dependency_missing",
            role_profile_ref="frontend_engineer_primary",
            dispatch_intent={
                "assignee_employee_id": "emp_frontend_2",
                "selection_reason": "CEO selected the primary frontend maker.",
                "dependency_gate_refs": ["tkt_missing_gate_ref"],
            },
        ),
    )

    assert self_dependency_response.status_code == 200
    assert self_dependency_response.json()["status"] == "REJECTED"
    assert "self" in self_dependency_response.json()["reason"].lower()
    assert missing_dependency_response.status_code == 200
    assert missing_dependency_response.json()["status"] == "REJECTED"
    assert "does not exist" in missing_dependency_response.json()["reason"].lower()


def test_scheduler_tick_fails_ticket_when_dependency_gate_has_failed(client, set_ticket_time, monkeypatch):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    _create_lease_and_start_ticket(
        client,
        workflow_id="wf_seed",
        ticket_id="tkt_dependency_failed_upstream",
        node_id="node_dependency_failed_upstream",
        role_profile_ref="frontend_engineer_primary",
    )
    fail_response = client.post(
        "/api/v1/commands/ticket-fail",
        json=_ticket_fail_payload(
            workflow_id="wf_seed",
            ticket_id="tkt_dependency_failed_upstream",
            node_id="node_dependency_failed_upstream",
            failure_kind="RUNTIME_ERROR",
            failure_message="Upstream delivery failed before the dependent ticket could start.",
        ),
    )
    assert fail_response.status_code == 200
    assert fail_response.json()["status"] == "ACCEPTED"

    ceo_triggers: list[tuple[str, str | None]] = []
    import app.core.ticket_handlers as ticket_handlers

    monkeypatch.setattr(
        ticket_handlers,
        "run_ceo_shadow_for_trigger",
        lambda repository, *, workflow_id, trigger_type, trigger_ref, runtime_provider_store=None: ceo_triggers.append(
            (trigger_type, trigger_ref)
        ),
    )

    create_response = client.post(
        "/api/v1/commands/ticket-create",
        json=_ticket_create_payload(
            workflow_id="wf_seed",
            ticket_id="tkt_dependency_blocked",
            node_id="node_dependency_blocked",
            role_profile_ref="frontend_engineer_primary",
            dispatch_intent={
                "assignee_employee_id": "emp_frontend_2",
                "selection_reason": "CEO selected the primary frontend maker.",
                "dependency_gate_refs": ["tkt_dependency_failed_upstream"],
            },
        ),
    )
    assert create_response.status_code == 200
    assert create_response.json()["status"] == "ACCEPTED"

    set_ticket_time("2026-03-28T10:01:00+08:00")
    response = client.post(
        "/api/v1/commands/scheduler-tick",
        json=_scheduler_tick_payload(idempotency_key="scheduler-tick:dependency-gate-failed"),
    )
    repository = client.app.state.repository
    ticket_projection = repository.get_current_ticket_projection("tkt_dependency_blocked")

    assert response.status_code == 200
    assert response.json()["status"] == "ACCEPTED"
    assert ticket_projection["status"] == TICKET_STATUS_FAILED
    assert ticket_projection["last_failure_kind"] == "DEPENDENCY_GATE_UNHEALTHY"
    assert ("TICKET_FAILED", "tkt_dependency_blocked") in ceo_triggers


def test_scheduler_tick_fails_delivery_stage_child_when_parent_is_missing(client, set_ticket_time, monkeypatch):
    ceo_triggers: list[tuple[str, str | None]] = []
    import app.core.ticket_handlers as ticket_handlers

    monkeypatch.setattr(
        ticket_handlers,
        "run_ceo_shadow_for_trigger",
        lambda repository, *, workflow_id, trigger_type, trigger_ref, runtime_provider_store=None: ceo_triggers.append(
            (trigger_type, trigger_ref)
        ),
    )

    create_response = client.post(
        "/api/v1/commands/ticket-create",
        json=_ticket_create_payload(
            workflow_id="wf_seed",
            ticket_id="tkt_delivery_child_blocked",
            node_id="node_delivery_child_blocked",
            role_profile_ref="checker_primary",
            output_schema_ref="delivery_check_report",
            delivery_stage="CHECK",
            parent_ticket_id="tkt_delivery_parent_missing",
        ),
    )
    assert create_response.status_code == 200
    assert create_response.json()["status"] == "ACCEPTED"

    set_ticket_time("2026-03-28T10:01:00+08:00")
    response = client.post(
        "/api/v1/commands/scheduler-tick",
        json=_scheduler_tick_payload(idempotency_key="scheduler-tick:delivery-parent-failed"),
    )
    repository = client.app.state.repository
    ticket_projection = repository.get_current_ticket_projection("tkt_delivery_child_blocked")

    assert response.status_code == 200
    assert response.json()["status"] == "ACCEPTED"
    assert ticket_projection["status"] == TICKET_STATUS_FAILED
    assert ticket_projection["last_failure_kind"] == "DEPENDENCY_GATE_INVALID"
    assert ("TICKET_FAILED", "tkt_delivery_child_blocked") in ceo_triggers


def test_inbox_and_dashboard_reflect_open_approval(client):
    _seed_review_request(client)

    inbox_response = client.get("/api/v1/projections/inbox")
    dashboard_response = client.get("/api/v1/projections/dashboard")

    assert inbox_response.status_code == 200
    items = inbox_response.json()["data"]["items"]
    assert len(items) == 1
    assert items[0]["route_target"]["view"] == "review_room"
    assert dashboard_response.json()["data"]["inbox_counts"]["approvals_pending"] == 1
    assert dashboard_response.json()["data"]["ops_strip"]["active_tickets"] == 1
    assert dashboard_response.json()["data"]["ops_strip"]["blocked_nodes"] == 1
    assert dashboard_response.json()["data"]["pipeline_summary"]["blocked_node_source"] == "ticket_graph"
    assert dashboard_response.json()["data"]["pipeline_summary"]["blocked_node_ids"] == [
        "node_homepage_visual"
    ]


def test_dashboard_projection_reuses_ticket_graph_indexes_for_blocked_and_critical_path(client):
    workflow_id = "wf_dashboard_ticket_graph_indexes"
    ticket_id = "tkt_dashboard_graph_runtime"
    node_id = "node_dashboard_graph_runtime"
    _ensure_scoped_workflow(
        client,
        workflow_id=workflow_id,
        tenant_id="tenant_default",
        workspace_id="ws_default",
        goal="Dashboard uses ticket graph indexes",
    )
    _create_lease_and_start_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id=ticket_id,
        node_id=node_id,
        output_schema_ref="source_code_delivery",
        delivery_stage="BUILD",
    )
    freeze_response = client.post(
        "/api/v1/commands/employee-freeze",
        json=_employee_freeze_payload(workflow_id, employee_id="emp_frontend_2"),
    )
    assert freeze_response.status_code == 200
    assert freeze_response.json()["status"] == "ACCEPTED"

    graph_snapshot = build_ticket_graph_snapshot(client.app.state.repository, workflow_id)
    dashboard_response = client.get("/api/v1/projections/dashboard")
    dashboard_data = dashboard_response.json()["data"]

    assert dashboard_response.status_code == 200
    assert dashboard_data["active_workflow"]["workflow_id"] == workflow_id
    assert dashboard_data["pipeline_summary"]["blocked_node_source"] == "ticket_graph"
    assert dashboard_data["pipeline_summary"]["blocked_node_ids"] == graph_snapshot.index_summary.blocked_node_ids
    assert dashboard_data["pipeline_summary"]["critical_path_node_ids"] == (
        graph_snapshot.index_summary.critical_path_node_ids
    )
    assert dashboard_data["ops_strip"]["blocked_nodes"] == len(graph_snapshot.index_summary.blocked_node_ids)


def test_dashboard_projection_exposes_graph_unavailable_without_legacy_blocked_fallback(client, monkeypatch):
    workflow_id = "wf_dashboard_graph_unavailable"
    _ensure_scoped_workflow(
        client,
        workflow_id=workflow_id,
        tenant_id="tenant_default",
        workspace_id="ws_default",
        goal="Dashboard graph unavailable stays fail visible",
    )
    _seed_review_request(client, workflow_id=workflow_id)

    import app.core.projections as projections_module

    def _raise_graph_unavailable(*args, **kwargs):
        raise RuntimeError("ticket graph unavailable")

    monkeypatch.setattr(projections_module, "build_ticket_graph_snapshot", _raise_graph_unavailable)

    dashboard_response = client.get("/api/v1/projections/dashboard")

    assert dashboard_response.status_code == 200
    dashboard_data = dashboard_response.json()["data"]
    assert dashboard_data["active_workflow"]["workflow_id"] == workflow_id
    assert dashboard_data["pipeline_summary"]["blocked_node_source"] == "graph_unavailable"
    assert dashboard_data["pipeline_summary"]["blocked_node_ids"] == []
    assert dashboard_data["ops_strip"]["blocked_nodes"] == 0


def test_incident_detail_exposes_rebuild_ticket_graph_recovery_for_graph_unavailable_incident(client):
    workflow_id = "wf_incident_graph_unavailable_detail"
    incident_id = "inc_graph_unavailable_detail"
    _ensure_scoped_workflow(
        client,
        workflow_id=workflow_id,
        tenant_id="tenant_default",
        workspace_id="ws_default",
        goal="Incident detail should expose graph rebuild recovery.",
    )
    repository = client.app.state.repository

    with repository.transaction() as connection:
        repository.insert_event(
            connection,
            event_type=EVENT_INCIDENT_OPENED,
            actor_type="system",
            actor_id="scheduler",
            workflow_id=workflow_id,
            idempotency_key=f"test-incident-opened:{workflow_id}:{incident_id}",
            causation_id=None,
            correlation_id=workflow_id,
            payload={
                "incident_id": incident_id,
                "node_id": None,
                "ticket_id": None,
                "incident_type": "TICKET_GRAPH_UNAVAILABLE",
                "status": "OPEN",
                "severity": "high",
                "fingerprint": f"{workflow_id}:TICKET_GRAPH_UNAVAILABLE:ceo_shadow_snapshot",
                "source_component": "ceo_shadow_snapshot",
                "source_stage": "ticket_graph_snapshot",
                "error_class": "RuntimeError",
                "error_message": "ticket graph unavailable from ceo snapshot",
            },
            occurred_at=datetime.fromisoformat("2026-03-28T10:02:00+08:00"),
        )
        repository.insert_event(
            connection,
            event_type=EVENT_CIRCUIT_BREAKER_OPENED,
            actor_type="system",
            actor_id="scheduler",
            workflow_id=workflow_id,
            idempotency_key=f"test-breaker-opened:{workflow_id}:{incident_id}",
            causation_id=None,
            correlation_id=workflow_id,
            payload={
                "incident_id": incident_id,
                "ticket_id": None,
                "node_id": None,
                "circuit_breaker_state": "OPEN",
                "fingerprint": f"{workflow_id}:TICKET_GRAPH_UNAVAILABLE:ceo_shadow_snapshot",
            },
            occurred_at=datetime.fromisoformat("2026-03-28T10:02:00+08:00"),
        )
        repository.refresh_projections(connection)

    incident_response = client.get(f"/api/v1/projections/incidents/{incident_id}")

    assert incident_response.status_code == 200
    assert incident_response.json()["data"]["incident"]["incident_type"] == "TICKET_GRAPH_UNAVAILABLE"
    assert incident_response.json()["data"]["available_followup_actions"] == [
        "REBUILD_TICKET_GRAPH",
        "RESTORE_ONLY",
    ]
    assert incident_response.json()["data"]["recommended_followup_action"] == "REBUILD_TICKET_GRAPH"


def test_p2_ceo_shadow_incident_detail_exposes_rerun_action(client):
    workflow_id = "wf_ceo_shadow_incident_detail"
    incident_id = "inc_ceo_shadow_detail"
    _ensure_scoped_workflow(
        client,
        workflow_id=workflow_id,
        tenant_id="tenant_default",
        workspace_id="ws_default",
        goal="CEO shadow incident detail should expose rerun recovery.",
    )
    repository = client.app.state.repository

    with repository.transaction() as connection:
        repository.insert_event(
            connection,
            event_type=EVENT_INCIDENT_OPENED,
            actor_type="system",
            actor_id="scheduler",
            workflow_id=workflow_id,
            idempotency_key=f"test-incident-opened:{workflow_id}:{incident_id}",
            causation_id=None,
            correlation_id=workflow_id,
            payload={
                "incident_id": incident_id,
                "node_id": None,
                "ticket_id": None,
                "incident_type": INCIDENT_TYPE_CEO_SHADOW_PIPELINE_FAILED,
                "status": "OPEN",
                "severity": "high",
                "fingerprint": f"{workflow_id}:MANUAL_TEST:manual:rerun:proposal:JSONDecodeError",
                "trigger_type": "MANUAL_TEST",
                "trigger_ref": "manual:rerun",
                "source_stage": "proposal",
                "error_class": "JSONDecodeError",
                "error_message": "Invalid provider payload.",
                "failure_fingerprint": f"{workflow_id}:MANUAL_TEST:manual:rerun:proposal:JSONDecodeError",
            },
            occurred_at=datetime.fromisoformat("2026-03-28T10:02:00+08:00"),
        )
        repository.insert_event(
            connection,
            event_type=EVENT_CIRCUIT_BREAKER_OPENED,
            actor_type="system",
            actor_id="scheduler",
            workflow_id=workflow_id,
            idempotency_key=f"test-breaker-opened:{workflow_id}:{incident_id}",
            causation_id=None,
            correlation_id=workflow_id,
            payload={
                "incident_id": incident_id,
                "ticket_id": None,
                "node_id": None,
                "circuit_breaker_state": "OPEN",
                "fingerprint": f"{workflow_id}:MANUAL_TEST:manual:rerun:proposal:JSONDecodeError",
            },
            occurred_at=datetime.fromisoformat("2026-03-28T10:02:00+08:00"),
        )
        repository.refresh_projections(connection)

    incident_response = client.get(f"/api/v1/projections/incidents/{incident_id}")

    assert incident_response.status_code == 200
    assert incident_response.json()["data"]["incident"]["incident_type"] == INCIDENT_TYPE_CEO_SHADOW_PIPELINE_FAILED
    assert incident_response.json()["data"]["available_followup_actions"] == [
        "RERUN_CEO_SHADOW",
        "RESTORE_ONLY",
    ]
    assert incident_response.json()["data"]["recommended_followup_action"] == "RERUN_CEO_SHADOW"


def test_p4_placeholder_gate_incident_detail_exposes_rerun_action(client):
    workflow_id = "wf_placeholder_gate_incident_detail"
    incident_id = "inc_placeholder_gate_detail"
    _ensure_scoped_workflow(
        client,
        workflow_id=workflow_id,
        tenant_id="tenant_default",
        workspace_id="ws_default",
        goal="Placeholder gate incident detail should expose CEO rerun recovery.",
    )
    repository = client.app.state.repository

    with repository.transaction() as connection:
        repository.insert_event(
            connection,
            event_type=EVENT_INCIDENT_OPENED,
            actor_type="system",
            actor_id="autopilot-controller",
            workflow_id=workflow_id,
            idempotency_key=f"test-incident-opened:{workflow_id}:{incident_id}",
            causation_id=None,
            correlation_id=workflow_id,
            payload={
                "incident_id": incident_id,
                "node_id": "node_placeholder_gate_target",
                "ticket_id": None,
                "incident_type": INCIDENT_TYPE_PLANNED_PLACEHOLDER_GATE_BLOCKED,
                "status": "OPEN",
                "severity": "high",
                "fingerprint": (
                    f"{workflow_id}:node_placeholder_gate_target:gv_2:workflow_auto_advance:"
                    "PLANNED_PLACEHOLDER_NOT_MATERIALIZED"
                ),
                "reason_code": "PLANNED_PLACEHOLDER_NOT_MATERIALIZED",
                "graph_node_id": "node_placeholder_gate_target",
                "graph_version": "gv_2",
                "source_component": "workflow_auto_advance",
                "trigger_type": "SCHEDULER_IDLE_MAINTENANCE",
                "trigger_ref": "test-placeholder-controller-probe",
                "materialization_hint": "create_ticket",
            },
            occurred_at=datetime.fromisoformat("2026-04-17T10:02:00+08:00"),
        )
        repository.insert_event(
            connection,
            event_type=EVENT_CIRCUIT_BREAKER_OPENED,
            actor_type="system",
            actor_id="autopilot-controller",
            workflow_id=workflow_id,
            idempotency_key=f"test-breaker-opened:{workflow_id}:{incident_id}",
            causation_id=None,
            correlation_id=workflow_id,
            payload={
                "incident_id": incident_id,
                "ticket_id": None,
                "node_id": "node_placeholder_gate_target",
                "circuit_breaker_state": "OPEN",
                "fingerprint": (
                    f"{workflow_id}:node_placeholder_gate_target:gv_2:workflow_auto_advance:"
                    "PLANNED_PLACEHOLDER_NOT_MATERIALIZED"
                ),
            },
            occurred_at=datetime.fromisoformat("2026-04-17T10:02:00+08:00"),
        )
        repository.refresh_projections(connection)

    incident_response = client.get(f"/api/v1/projections/incidents/{incident_id}")

    assert incident_response.status_code == 200
    assert incident_response.json()["data"]["incident"]["incident_type"] == (
        INCIDENT_TYPE_PLANNED_PLACEHOLDER_GATE_BLOCKED
    )
    assert incident_response.json()["data"]["available_followup_actions"] == [
        "RERUN_CEO_SHADOW",
        "RESTORE_ONLY",
    ]
    assert incident_response.json()["data"]["recommended_followup_action"] == "RERUN_CEO_SHADOW"


def test_graph_health_critical_incident_detail_exposes_rerun_action(client):
    workflow_id = "wf_graph_health_critical_detail"
    incident_id = "inc_graph_health_critical_detail"
    _ensure_scoped_workflow(
        client,
        workflow_id=workflow_id,
        tenant_id="tenant_default",
        workspace_id="ws_default",
        goal="Graph health critical detail should expose rerun recovery.",
    )
    repository = client.app.state.repository

    with repository.transaction() as connection:
        repository.insert_event(
            connection,
            event_type=EVENT_INCIDENT_OPENED,
            actor_type="system",
            actor_id="scheduler",
            workflow_id=workflow_id,
            idempotency_key=f"test-incident-opened:{workflow_id}:{incident_id}",
            causation_id=None,
            correlation_id=workflow_id,
            payload={
                "incident_id": incident_id,
                "node_id": "node_graph_health_hotspot",
                "ticket_id": None,
                "incident_type": "GRAPH_HEALTH_CRITICAL",
                "status": "OPEN",
                "severity": "high",
                "fingerprint": (
                    f"{workflow_id}:gv_7:PERSISTENT_FAILURE_ZONE:node_graph_health_hotspot"
                ),
                "graph_version": "gv_7",
                "finding_type": "PERSISTENT_FAILURE_ZONE",
                "affected_nodes": ["node_graph_health_hotspot"],
            },
            occurred_at=datetime.fromisoformat("2026-04-15T20:42:00+08:00"),
        )
        repository.insert_event(
            connection,
            event_type=EVENT_CIRCUIT_BREAKER_OPENED,
            actor_type="system",
            actor_id="scheduler",
            workflow_id=workflow_id,
            idempotency_key=f"test-breaker-opened:{workflow_id}:{incident_id}",
            causation_id=None,
            correlation_id=workflow_id,
            payload={
                "incident_id": incident_id,
                "ticket_id": None,
                "node_id": "node_graph_health_hotspot",
                "circuit_breaker_state": "OPEN",
                "fingerprint": (
                    f"{workflow_id}:gv_7:PERSISTENT_FAILURE_ZONE:node_graph_health_hotspot"
                ),
            },
            occurred_at=datetime.fromisoformat("2026-04-15T20:42:00+08:00"),
        )
        repository.refresh_projections(connection)

    incident_response = client.get(f"/api/v1/projections/incidents/{incident_id}")

    assert incident_response.status_code == 200
    assert incident_response.json()["data"]["incident"]["incident_type"] == "GRAPH_HEALTH_CRITICAL"
    assert incident_response.json()["data"]["available_followup_actions"] == [
        "RERUN_CEO_SHADOW",
        "RESTORE_ONLY",
    ]
    assert incident_response.json()["data"]["recommended_followup_action"] == "RERUN_CEO_SHADOW"


def test_graph_health_thrashing_incident_detail_exposes_rerun_action(client):
    workflow_id = "wf_graph_health_thrashing_detail"
    incident_id = "inc_graph_health_thrashing_detail"
    _ensure_scoped_workflow(
        client,
        workflow_id=workflow_id,
        tenant_id="tenant_default",
        workspace_id="ws_default",
        goal="Graph thrashing detail should still expose rerun recovery.",
    )
    repository = client.app.state.repository

    with repository.transaction() as connection:
        repository.insert_event(
            connection,
            event_type=EVENT_INCIDENT_OPENED,
            actor_type="system",
            actor_id="scheduler",
            workflow_id=workflow_id,
            idempotency_key=f"test-incident-opened:{workflow_id}:{incident_id}",
            causation_id=None,
            correlation_id=workflow_id,
            payload={
                "incident_id": incident_id,
                "node_id": "node_graph_health_thrashing_hotspot",
                "ticket_id": None,
                "incident_type": "GRAPH_HEALTH_CRITICAL",
                "status": "OPEN",
                "severity": "high",
                "fingerprint": (
                    f"{workflow_id}:gv_9:GRAPH_THRASHING:node_graph_health_thrashing_hotspot"
                ),
                "graph_version": "gv_9",
                "finding_type": "GRAPH_THRASHING",
                "affected_nodes": ["node_graph_health_thrashing_hotspot"],
            },
            occurred_at=datetime.fromisoformat("2026-04-16T20:52:00+08:00"),
        )
        repository.insert_event(
            connection,
            event_type=EVENT_CIRCUIT_BREAKER_OPENED,
            actor_type="system",
            actor_id="scheduler",
            workflow_id=workflow_id,
            idempotency_key=f"test-breaker-opened:{workflow_id}:{incident_id}",
            causation_id=None,
            correlation_id=workflow_id,
            payload={
                "incident_id": incident_id,
                "ticket_id": None,
                "node_id": "node_graph_health_thrashing_hotspot",
                "circuit_breaker_state": "OPEN",
                "fingerprint": (
                    f"{workflow_id}:gv_9:GRAPH_THRASHING:node_graph_health_thrashing_hotspot"
                ),
            },
            occurred_at=datetime.fromisoformat("2026-04-16T20:52:00+08:00"),
        )
        repository.refresh_projections(connection)

    incident_response = client.get(f"/api/v1/projections/incidents/{incident_id}")

    assert incident_response.status_code == 200
    assert incident_response.json()["data"]["incident"]["payload"]["finding_type"] == "GRAPH_THRASHING"
    assert incident_response.json()["data"]["available_followup_actions"] == [
        "RERUN_CEO_SHADOW",
        "RESTORE_ONLY",
    ]
    assert incident_response.json()["data"]["recommended_followup_action"] == "RERUN_CEO_SHADOW"


def test_graph_health_ready_node_stale_stays_in_snapshot_without_opening_incident(client, monkeypatch):
    workflow_id = "wf_graph_health_ready_node_stale_snapshot"
    _ensure_scoped_workflow(
        client,
        workflow_id=workflow_id,
        tenant_id="tenant_default",
        workspace_id="ws_default",
        goal="Ready node stale should stay in graph health snapshot without opening incident.",
    )
    _seed_created_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_graph_health_ready_node_stale_snapshot",
        node_id="node_graph_health_ready_node_stale_snapshot",
        role_profile_ref="frontend_engineer_primary",
        output_schema_ref="source_code_delivery",
        delivery_stage="BUILD",
    )
    import app.core.runtime_liveness as runtime_liveness_module

    monkeypatch.setattr(
        runtime_liveness_module,
        "now_local",
        lambda: datetime.fromisoformat("2026-04-16T12:00:00+08:00"),
    )
    repository = client.app.state.repository
    with repository.transaction() as connection:
        connection.execute(
            """
            UPDATE ticket_projection
            SET updated_at = ?
            WHERE ticket_id = ?
            """,
            ("2026-04-16T09:00:00+08:00", "tkt_graph_health_ready_node_stale_snapshot"),
        )

    snapshot = build_ceo_shadow_snapshot(
        repository,
        workflow_id=workflow_id,
        trigger_type="MANUAL_TEST",
        trigger_ref="manual:graph-health-ready-node-stale-snapshot",
    )

    finding_types = [
        item["finding_type"]
        for item in snapshot["projection_snapshot"]["runtime_liveness_report"]["findings"]
    ]

    assert "READY_NODE_STALE" in finding_types
    assert repository.list_open_incidents() == []


def test_graph_health_queue_starvation_opens_critical_incident_via_auto_advance(client, monkeypatch):
    workflow_id = "wf_graph_health_queue_starvation_incident"
    ticket_id = "tkt_graph_health_queue_starvation_incident"
    node_id = "node_graph_health_queue_starvation_incident"
    _ensure_scoped_workflow(
        client,
        workflow_id=workflow_id,
        tenant_id="tenant_default",
        workspace_id="ws_default",
        goal="Queue starvation should open a graph health critical incident.",
    )
    _seed_created_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id=ticket_id,
        node_id=node_id,
        role_profile_ref="frontend_engineer_primary",
        output_schema_ref="source_code_delivery",
        delivery_stage="BUILD",
    )
    import app.core.graph_health as graph_health_module

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
            ("2026-04-16T09:00:00+08:00", ticket_id),
        )

    auto_advance_workflow_to_next_stop(
        repository,
        workflow_id=workflow_id,
        idempotency_key_prefix=f"test-graph-health-queue-starvation:{workflow_id}",
        max_steps=1,
        max_dispatches=1,
    )

    open_incidents = [
        item for item in repository.list_open_incidents() if item["workflow_id"] == workflow_id
    ]

    assert len(open_incidents) == 1
    assert open_incidents[0]["incident_type"] == "RUNTIME_LIVENESS_CRITICAL"
    assert open_incidents[0]["payload"]["finding_type"] == "QUEUE_STARVATION"
    assert open_incidents[0]["payload"]["affected_nodes"] == [node_id]
    assert open_incidents[0]["payload"]["affected_graph_node_ids"] == [node_id]


def test_runtime_liveness_unavailable_opens_runtime_liveness_unavailable_incident(client, monkeypatch):
    workflow_id = "wf_runtime_liveness_unavailable_incident"
    _ensure_scoped_workflow(
        client,
        workflow_id=workflow_id,
        tenant_id="tenant_default",
        workspace_id="ws_default",
        goal="Runtime liveness failure should open its own explicit incident path.",
    )
    _seed_created_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_runtime_liveness_unavailable_incident",
        node_id="node_runtime_liveness_unavailable_incident",
        role_profile_ref="frontend_engineer_primary",
        output_schema_ref="source_code_delivery",
        delivery_stage="BUILD",
    )
    import app.core.ceo_snapshot as ceo_snapshot_module
    import app.core.runtime_liveness as runtime_liveness_module

    def _raise_runtime_liveness_unavailable(*args, **kwargs):
        raise runtime_liveness_module.RuntimeLivenessUnavailableError(
            "runtime liveness unavailable: malformed runtime timeline"
        )

    monkeypatch.setattr(
        ceo_snapshot_module,
        "build_runtime_liveness_report",
        _raise_runtime_liveness_unavailable,
        raising=False,
    )

    auto_advance_workflow_to_next_stop(
        client.app.state.repository,
        workflow_id=workflow_id,
        idempotency_key_prefix=f"test-runtime-liveness-unavailable:{workflow_id}",
        max_steps=1,
        max_dispatches=1,
    )

    open_incidents = [
        item
        for item in client.app.state.repository.list_open_incidents()
        if item["workflow_id"] == workflow_id
    ]

    assert len(open_incidents) == 1
    assert open_incidents[0]["incident_type"] == "RUNTIME_LIVENESS_UNAVAILABLE"
    assert open_incidents[0]["payload"]["error_class"] == "RuntimeLivenessUnavailableError"


def test_graph_health_unavailable_error_opens_ticket_graph_unavailable_incident(client, monkeypatch):
    workflow_id = "wf_graph_health_unavailable_incident"
    _ensure_scoped_workflow(
        client,
        workflow_id=workflow_id,
        tenant_id="tenant_default",
        workspace_id="ws_default",
        goal="Graph health failure should reuse the ticket graph unavailable recovery path.",
    )
    _seed_created_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_graph_health_unavailable_incident",
        node_id="node_graph_health_unavailable_incident",
        role_profile_ref="frontend_engineer_primary",
        output_schema_ref="source_code_delivery",
        delivery_stage="BUILD",
    )
    import app.core.ceo_snapshot as ceo_snapshot_module
    import app.core.graph_health as graph_health_module

    assert hasattr(graph_health_module, "GraphHealthUnavailableError")

    def _raise_graph_health_unavailable(*args, **kwargs):
        raise graph_health_module.GraphHealthUnavailableError(
            "graph unavailable: malformed graph health timeline"
        )

    monkeypatch.setattr(
        ceo_snapshot_module,
        "build_graph_health_report",
        _raise_graph_health_unavailable,
    )

    auto_advance_workflow_to_next_stop(
        client.app.state.repository,
        workflow_id=workflow_id,
        idempotency_key_prefix=f"test-graph-health-unavailable:{workflow_id}",
        max_steps=1,
        max_dispatches=1,
    )

    open_incidents = [
        item
        for item in client.app.state.repository.list_open_incidents()
        if item["workflow_id"] == workflow_id
    ]

    assert len(open_incidents) == 1
    assert open_incidents[0]["incident_type"] == "TICKET_GRAPH_UNAVAILABLE"
    assert open_incidents[0]["payload"]["error_class"] == "GraphHealthUnavailableError"


def test_incident_resolve_can_rebuild_ticket_graph_when_graph_unavailable_incident_is_open(client, monkeypatch):
    workflow_id = "wf_incident_graph_rebuild"
    incident_id = "inc_graph_rebuild"
    _ensure_scoped_workflow(
        client,
        workflow_id=workflow_id,
        tenant_id="tenant_default",
        workspace_id="ws_default",
        goal="Incident resolve should support graph rebuild.",
    )
    repository = client.app.state.repository

    with repository.transaction() as connection:
        repository.insert_event(
            connection,
            event_type=EVENT_INCIDENT_OPENED,
            actor_type="system",
            actor_id="scheduler",
            workflow_id=workflow_id,
            idempotency_key=f"test-incident-opened:{workflow_id}:{incident_id}",
            causation_id=None,
            correlation_id=workflow_id,
            payload={
                "incident_id": incident_id,
                "node_id": None,
                "ticket_id": None,
                "incident_type": "TICKET_GRAPH_UNAVAILABLE",
                "status": "OPEN",
                "severity": "high",
                "fingerprint": f"{workflow_id}:TICKET_GRAPH_UNAVAILABLE:ceo_shadow_snapshot",
                "source_component": "ceo_shadow_snapshot",
                "source_stage": "ticket_graph_snapshot",
                "error_class": "RuntimeError",
                "error_message": "ticket graph unavailable from ceo snapshot",
            },
            occurred_at=datetime.fromisoformat("2026-03-28T10:02:00+08:00"),
        )
        repository.insert_event(
            connection,
            event_type=EVENT_CIRCUIT_BREAKER_OPENED,
            actor_type="system",
            actor_id="scheduler",
            workflow_id=workflow_id,
            idempotency_key=f"test-breaker-opened:{workflow_id}:{incident_id}",
            causation_id=None,
            correlation_id=workflow_id,
            payload={
                "incident_id": incident_id,
                "ticket_id": None,
                "node_id": None,
                "circuit_breaker_state": "OPEN",
                "fingerprint": f"{workflow_id}:TICKET_GRAPH_UNAVAILABLE:ceo_shadow_snapshot",
            },
            occurred_at=datetime.fromisoformat("2026-03-28T10:02:00+08:00"),
        )
        repository.refresh_projections(connection)

    import app.core.ticket_handlers as ticket_handlers_module

    rebuild_calls: list[str] = []

    def _rebuild_ticket_graph(*args, **kwargs):
        rebuild_calls.append("called")
        return {"graph_snapshot": "ok"}

    monkeypatch.setattr(ticket_handlers_module, "build_ticket_graph_snapshot", _rebuild_ticket_graph)

    resolve_response = client.post(
        "/api/v1/commands/incident-resolve",
        json=_incident_resolve_payload(
            incident_id,
            followup_action="REBUILD_TICKET_GRAPH",
        ),
    )
    incident_response = client.get(f"/api/v1/projections/incidents/{incident_id}")

    assert resolve_response.status_code == 200
    assert resolve_response.json()["status"] == "ACCEPTED"
    assert rebuild_calls == ["called"]
    assert incident_response.json()["data"]["incident"]["status"] == "RECOVERING"
    assert incident_response.json()["data"]["incident"]["circuit_breaker_state"] == "CLOSED"
    assert incident_response.json()["data"]["incident"]["payload"]["followup_action"] == "REBUILD_TICKET_GRAPH"


def test_p2_ceo_shadow_incident_resolve_reruns_shadow_and_closes_incident(client, monkeypatch):
    workflow_id = "wf_ceo_shadow_incident_resolve"
    incident_id = "inc_ceo_shadow_resolve"
    _ensure_scoped_workflow(
        client,
        workflow_id=workflow_id,
        tenant_id="tenant_default",
        workspace_id="ws_default",
        goal="CEO shadow incident resolve should rerun and close.",
    )
    repository = client.app.state.repository

    with repository.transaction() as connection:
        repository.insert_event(
            connection,
            event_type=EVENT_INCIDENT_OPENED,
            actor_type="system",
            actor_id="scheduler",
            workflow_id=workflow_id,
            idempotency_key=f"test-incident-opened:{workflow_id}:{incident_id}",
            causation_id=None,
            correlation_id=workflow_id,
            payload={
                "incident_id": incident_id,
                "node_id": None,
                "ticket_id": None,
                "incident_type": INCIDENT_TYPE_CEO_SHADOW_PIPELINE_FAILED,
                "status": "OPEN",
                "severity": "high",
                "fingerprint": f"{workflow_id}:APPROVAL_RESOLVED:apr_001:proposal:JSONDecodeError",
                "trigger_type": "APPROVAL_RESOLVED",
                "trigger_ref": "apr_001",
                "source_stage": "proposal",
                "error_class": "JSONDecodeError",
                "error_message": "Invalid provider payload.",
                "failure_fingerprint": f"{workflow_id}:APPROVAL_RESOLVED:apr_001:proposal:JSONDecodeError",
            },
            occurred_at=datetime.fromisoformat("2026-03-28T10:02:00+08:00"),
        )
        repository.insert_event(
            connection,
            event_type=EVENT_CIRCUIT_BREAKER_OPENED,
            actor_type="system",
            actor_id="scheduler",
            workflow_id=workflow_id,
            idempotency_key=f"test-breaker-opened:{workflow_id}:{incident_id}",
            causation_id=None,
            correlation_id=workflow_id,
            payload={
                "incident_id": incident_id,
                "ticket_id": None,
                "node_id": None,
                "circuit_breaker_state": "OPEN",
                "fingerprint": f"{workflow_id}:APPROVAL_RESOLVED:apr_001:proposal:JSONDecodeError",
            },
            occurred_at=datetime.fromisoformat("2026-03-28T10:02:00+08:00"),
        )
        repository.refresh_projections(connection)

    import app.core.ticket_handlers as ticket_handlers_module

    rerun_calls: list[tuple[str, str, str | None]] = []

    def _fake_rerun(repository, *, workflow_id, trigger_type, trigger_ref, runtime_provider_store=None):
        rerun_calls.append((workflow_id, trigger_type, trigger_ref))
        return {
            "workflow_id": workflow_id,
            "trigger_type": trigger_type,
            "trigger_ref": trigger_ref,
            "effective_mode": "LOCAL_DETERMINISTIC",
            "provider_health_summary": "UNAVAILABLE",
            "fallback_reason": "deterministic mode",
            "accepted_actions": [],
            "rejected_actions": [],
            "executed_actions": [],
            "execution_summary": {
                "attempted_action_count": 0,
                "executed_action_count": 0,
                "duplicate_action_count": 0,
                "passthrough_action_count": 0,
                "deferred_action_count": 0,
                "failed_action_count": 0,
            },
            "deterministic_fallback_used": False,
            "deterministic_fallback_reason": None,
        }

    monkeypatch.setattr(ticket_handlers_module, "run_ceo_shadow_for_trigger", _fake_rerun)

    resolve_response = client.post(
        "/api/v1/commands/incident-resolve",
        json=_incident_resolve_payload(
            incident_id,
            followup_action="RERUN_CEO_SHADOW",
        ),
    )
    incident_response = client.get(f"/api/v1/projections/incidents/{incident_id}")

    assert resolve_response.status_code == 200
    assert resolve_response.json()["status"] == "ACCEPTED"
    assert rerun_calls == [(workflow_id, "APPROVAL_RESOLVED", "apr_001")]
    assert incident_response.json()["data"]["incident"]["status"] == "CLOSED"
    assert incident_response.json()["data"]["incident"]["circuit_breaker_state"] == "CLOSED"
    assert incident_response.json()["data"]["incident"]["payload"]["followup_action"] == "RERUN_CEO_SHADOW"


def test_p4_placeholder_gate_incident_resolve_reruns_shadow_and_closes_incident(client, monkeypatch):
    workflow_id = "wf_placeholder_gate_incident_resolve"
    incident_id = "inc_placeholder_gate_resolve"
    _ensure_scoped_workflow(
        client,
        workflow_id=workflow_id,
        tenant_id="tenant_default",
        workspace_id="ws_default",
        goal="Placeholder gate incident resolve should rerun CEO shadow and close.",
    )
    repository = client.app.state.repository

    with repository.transaction() as connection:
        repository.insert_event(
            connection,
            event_type=EVENT_INCIDENT_OPENED,
            actor_type="system",
            actor_id="autopilot-controller",
            workflow_id=workflow_id,
            idempotency_key=f"test-incident-opened:{workflow_id}:{incident_id}",
            causation_id=None,
            correlation_id=workflow_id,
            payload={
                "incident_id": incident_id,
                "node_id": "node_placeholder_gate_resolve_target",
                "ticket_id": None,
                "incident_type": INCIDENT_TYPE_PLANNED_PLACEHOLDER_GATE_BLOCKED,
                "status": "OPEN",
                "severity": "high",
                "fingerprint": (
                    f"{workflow_id}:node_placeholder_gate_resolve_target:gv_9:workflow_auto_advance:"
                    "PLANNED_PLACEHOLDER_NOT_MATERIALIZED"
                ),
                "reason_code": "PLANNED_PLACEHOLDER_NOT_MATERIALIZED",
                "graph_node_id": "node_placeholder_gate_resolve_target",
                "graph_version": "gv_9",
                "source_component": "workflow_auto_advance",
                "trigger_type": "SCHEDULER_IDLE_MAINTENANCE",
                "trigger_ref": "test-placeholder-resolve",
                "materialization_hint": "create_ticket",
            },
            occurred_at=datetime.fromisoformat("2026-04-17T10:12:00+08:00"),
        )
        repository.insert_event(
            connection,
            event_type=EVENT_CIRCUIT_BREAKER_OPENED,
            actor_type="system",
            actor_id="autopilot-controller",
            workflow_id=workflow_id,
            idempotency_key=f"test-breaker-opened:{workflow_id}:{incident_id}",
            causation_id=None,
            correlation_id=workflow_id,
            payload={
                "incident_id": incident_id,
                "ticket_id": None,
                "node_id": "node_placeholder_gate_resolve_target",
                "circuit_breaker_state": "OPEN",
                "fingerprint": (
                    f"{workflow_id}:node_placeholder_gate_resolve_target:gv_9:workflow_auto_advance:"
                    "PLANNED_PLACEHOLDER_NOT_MATERIALIZED"
                ),
            },
            occurred_at=datetime.fromisoformat("2026-04-17T10:12:00+08:00"),
        )
        repository.refresh_projections(connection)

    import app.core.ticket_handlers as ticket_handlers_module

    rerun_calls: list[tuple[str, str, str | None]] = []

    def _fake_rerun(repository, *, workflow_id, trigger_type, trigger_ref, runtime_provider_store=None):
        rerun_calls.append((workflow_id, trigger_type, trigger_ref))
        return {
            "workflow_id": workflow_id,
            "trigger_type": trigger_type,
            "trigger_ref": trigger_ref,
            "effective_mode": "LOCAL_DETERMINISTIC",
            "provider_health_summary": "UNAVAILABLE",
            "fallback_reason": "deterministic mode",
            "accepted_actions": [],
            "rejected_actions": [],
            "executed_actions": [],
            "execution_summary": {
                "attempted_action_count": 0,
                "executed_action_count": 0,
                "duplicate_action_count": 0,
                "passthrough_action_count": 0,
                "deferred_action_count": 0,
                "failed_action_count": 0,
            },
            "deterministic_fallback_used": False,
            "deterministic_fallback_reason": None,
        }

    monkeypatch.setattr(ticket_handlers_module, "run_ceo_shadow_for_trigger", _fake_rerun)

    resolve_response = client.post(
        "/api/v1/commands/incident-resolve",
        json=_incident_resolve_payload(
            incident_id,
            followup_action="RERUN_CEO_SHADOW",
        ),
    )
    incident_response = client.get(f"/api/v1/projections/incidents/{incident_id}")

    assert resolve_response.status_code == 200
    assert resolve_response.json()["status"] == "ACCEPTED"
    assert rerun_calls == [(workflow_id, "SCHEDULER_IDLE_MAINTENANCE", "test-placeholder-resolve")]
    assert incident_response.json()["data"]["incident"]["status"] == "CLOSED"
    assert incident_response.json()["data"]["incident"]["circuit_breaker_state"] == "CLOSED"
    assert incident_response.json()["data"]["incident"]["payload"]["followup_action"] == "RERUN_CEO_SHADOW"
    assert repository.get_current_node_projection(workflow_id, "node_placeholder_gate_resolve_target") is None
    assert repository.get_current_ticket_projection("tkt_placeholder_gate_resolve_target") is None


def test_p4_placeholder_gate_incident_resolve_rejects_missing_trigger_type(client):
    workflow_id = "wf_placeholder_gate_missing_trigger"
    incident_id = "inc_placeholder_gate_missing_trigger"
    _ensure_scoped_workflow(
        client,
        workflow_id=workflow_id,
        tenant_id="tenant_default",
        workspace_id="ws_default",
        goal="Placeholder gate incident resolve should fail closed when trigger_type is missing.",
    )
    repository = client.app.state.repository

    with repository.transaction() as connection:
        repository.insert_event(
            connection,
            event_type=EVENT_INCIDENT_OPENED,
            actor_type="system",
            actor_id="autopilot-controller",
            workflow_id=workflow_id,
            idempotency_key=f"test-incident-opened:{workflow_id}:{incident_id}",
            causation_id=None,
            correlation_id=workflow_id,
            payload={
                "incident_id": incident_id,
                "node_id": "node_placeholder_gate_missing_trigger",
                "ticket_id": None,
                "incident_type": INCIDENT_TYPE_PLANNED_PLACEHOLDER_GATE_BLOCKED,
                "status": "OPEN",
                "severity": "high",
                "fingerprint": (
                    f"{workflow_id}:node_placeholder_gate_missing_trigger:gv_3:workflow_auto_advance:"
                    "PLANNED_PLACEHOLDER_NOT_MATERIALIZED"
                ),
                "reason_code": "PLANNED_PLACEHOLDER_NOT_MATERIALIZED",
                "graph_node_id": "node_placeholder_gate_missing_trigger",
                "graph_version": "gv_3",
                "source_component": "workflow_auto_advance",
                "trigger_ref": "missing-trigger-type",
                "materialization_hint": "create_ticket",
            },
            occurred_at=datetime.fromisoformat("2026-04-17T10:22:00+08:00"),
        )
        repository.insert_event(
            connection,
            event_type=EVENT_CIRCUIT_BREAKER_OPENED,
            actor_type="system",
            actor_id="autopilot-controller",
            workflow_id=workflow_id,
            idempotency_key=f"test-breaker-opened:{workflow_id}:{incident_id}",
            causation_id=None,
            correlation_id=workflow_id,
            payload={
                "incident_id": incident_id,
                "ticket_id": None,
                "node_id": "node_placeholder_gate_missing_trigger",
                "circuit_breaker_state": "OPEN",
                "fingerprint": (
                    f"{workflow_id}:node_placeholder_gate_missing_trigger:gv_3:workflow_auto_advance:"
                    "PLANNED_PLACEHOLDER_NOT_MATERIALIZED"
                ),
            },
            occurred_at=datetime.fromisoformat("2026-04-17T10:22:00+08:00"),
        )
        repository.refresh_projections(connection)

    resolve_response = client.post(
        "/api/v1/commands/incident-resolve",
        json=_incident_resolve_payload(
            incident_id,
            followup_action="RERUN_CEO_SHADOW",
        ),
    )

    assert resolve_response.status_code == 200
    assert resolve_response.json()["status"] == "REJECTED"
    assert "missing its original trigger_type" in resolve_response.json()["reason"]


def test_p2_ceo_shadow_incident_command_trigger_opens_incident(client, monkeypatch):
    provider_upsert = client.post(
        "/api/v1/commands/runtime-provider-upsert",
        json=_runtime_provider_upsert_payload(idempotency_key="runtime-provider-upsert:ceo-shadow-command"),
    )
    assert provider_upsert.status_code == 200

    from app.core import ceo_proposer

    def _fake_invoke(_config, _rendered_payload):
        return OpenAICompatProviderResult(
            output_text="{not-json}",
            response_id="resp_api_ceo_shadow_command_1",
        )

    monkeypatch.setattr(ceo_proposer, "invoke_openai_compat_response", _fake_invoke)

    response = client.post(
        "/api/v1/commands/project-init",
        json=_project_init_payload("Open an explicit CEO shadow incident on command trigger."),
    )
    workflow_id = response.json()["causation_hint"].split(":", 1)[1]
    incidents = [
        item
        for item in client.app.state.repository.list_open_incidents()
        if item["workflow_id"] == workflow_id
    ]

    assert response.status_code == 200
    assert response.json()["status"] == "ACCEPTED"
    assert len(incidents) == 1
    assert incidents[0]["incident_type"] == INCIDENT_TYPE_CEO_SHADOW_PIPELINE_FAILED
    assert incidents[0]["payload"]["trigger_type"] == EVENT_BOARD_DIRECTIVE_RECEIVED


def test_p2_ceo_shadow_incident_approval_trigger_opens_incident(client, monkeypatch):
    approval = _seed_review_request(client, workflow_id="wf_p2_ceo_shadow_approval")
    provider_upsert = client.post(
        "/api/v1/commands/runtime-provider-upsert",
        json=_runtime_provider_upsert_payload(idempotency_key="runtime-provider-upsert:ceo-shadow-approval"),
    )
    assert provider_upsert.status_code == 200

    from app.core import ceo_proposer

    def _fake_invoke(_config, _rendered_payload):
        return OpenAICompatProviderResult(
            output_text="{not-json}",
            response_id="resp_api_ceo_shadow_approval_1",
        )

    monkeypatch.setattr(ceo_proposer, "invoke_openai_compat_response", _fake_invoke)

    response = client.post(
        "/api/v1/commands/board-approve",
        json={
            "review_pack_id": approval["review_pack_id"],
            "review_pack_version": approval["review_pack_version"],
            "command_target_version": approval["command_target_version"],
            "approval_id": approval["approval_id"],
            "selected_option_id": "option_a",
            "board_comment": "Approve and let CEO shadow continue.",
            "idempotency_key": f"board-approve:{approval['approval_id']}:p2-ceo-shadow-incident",
        },
    )
    incidents = [
        item
        for item in client.app.state.repository.list_open_incidents()
        if item["workflow_id"] == approval["workflow_id"]
        and item["incident_type"] == INCIDENT_TYPE_CEO_SHADOW_PIPELINE_FAILED
        and str((item.get("payload") or {}).get("trigger_type") or "") == "APPROVAL_RESOLVED"
        and str((item.get("payload") or {}).get("trigger_ref") or "") == approval["approval_id"]
    ]

    assert response.status_code == 200
    assert response.json()["status"] == "ACCEPTED"
    assert len(incidents) == 1
    assert incidents[0]["incident_type"] == INCIDENT_TYPE_CEO_SHADOW_PIPELINE_FAILED
    assert incidents[0]["payload"]["trigger_type"] == "APPROVAL_RESOLVED"
    assert incidents[0]["payload"]["trigger_ref"] == approval["approval_id"]


def test_p2_ceo_shadow_incident_ticket_trigger_opens_incident(client, monkeypatch):
    workflow_id = "wf_p2_ceo_shadow_ticket"
    _ensure_scoped_workflow(
        client,
        workflow_id=workflow_id,
        tenant_id="tenant_default",
        workspace_id="ws_default",
        goal="Open an explicit CEO shadow incident on ticket trigger.",
    )
    _create_lease_and_start_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_p2_ceo_shadow_ticket",
        node_id="node_p2_ceo_shadow_ticket",
    )
    provider_upsert = client.post(
        "/api/v1/commands/runtime-provider-upsert",
        json=_runtime_provider_upsert_payload(idempotency_key="runtime-provider-upsert:ceo-shadow-ticket"),
    )
    assert provider_upsert.status_code == 200

    from app.core import ceo_proposer

    def _fake_invoke(_config, _rendered_payload):
        return OpenAICompatProviderResult(
            output_text="{not-json}",
            response_id="resp_api_ceo_shadow_ticket_1",
        )

    monkeypatch.setattr(ceo_proposer, "invoke_openai_compat_response", _fake_invoke)

    response = client.post(
        "/api/v1/commands/ticket-fail",
        json=_ticket_fail_payload(
            workflow_id=workflow_id,
            ticket_id="tkt_p2_ceo_shadow_ticket",
            node_id="node_p2_ceo_shadow_ticket",
            failure_kind="RUNTIME_ERROR",
            failure_message="Seed the CEO shadow trigger from a ticket failure.",
        ),
    )
    incidents = [
        item
        for item in client.app.state.repository.list_open_incidents()
        if item["workflow_id"] == workflow_id
    ]

    assert response.status_code == 200
    assert response.json()["status"] == "ACCEPTED"
    assert len(incidents) == 1
    assert incidents[0]["incident_type"] == INCIDENT_TYPE_CEO_SHADOW_PIPELINE_FAILED
    assert incidents[0]["payload"]["trigger_type"] == EVENT_TICKET_FAILED
    assert incidents[0]["payload"]["trigger_ref"] == "tkt_p2_ceo_shadow_ticket"


def test_incident_resolve_rejects_rebuild_ticket_graph_when_snapshot_still_unavailable(client, monkeypatch):
    workflow_id = "wf_incident_graph_rebuild_reject"
    incident_id = "inc_graph_rebuild_reject"
    _ensure_scoped_workflow(
        client,
        workflow_id=workflow_id,
        tenant_id="tenant_default",
        workspace_id="ws_default",
        goal="Incident resolve should fail closed when graph rebuild still fails.",
    )
    repository = client.app.state.repository

    with repository.transaction() as connection:
        repository.insert_event(
            connection,
            event_type=EVENT_INCIDENT_OPENED,
            actor_type="system",
            actor_id="scheduler",
            workflow_id=workflow_id,
            idempotency_key=f"test-incident-opened:{workflow_id}:{incident_id}",
            causation_id=None,
            correlation_id=workflow_id,
            payload={
                "incident_id": incident_id,
                "node_id": None,
                "ticket_id": None,
                "incident_type": "TICKET_GRAPH_UNAVAILABLE",
                "status": "OPEN",
                "severity": "high",
                "fingerprint": f"{workflow_id}:TICKET_GRAPH_UNAVAILABLE:ceo_shadow_snapshot",
                "source_component": "ceo_shadow_snapshot",
                "source_stage": "ticket_graph_snapshot",
                "error_class": "RuntimeError",
                "error_message": "ticket graph unavailable from ceo snapshot",
            },
            occurred_at=datetime.fromisoformat("2026-03-28T10:02:00+08:00"),
        )
        repository.insert_event(
            connection,
            event_type=EVENT_CIRCUIT_BREAKER_OPENED,
            actor_type="system",
            actor_id="scheduler",
            workflow_id=workflow_id,
            idempotency_key=f"test-breaker-opened:{workflow_id}:{incident_id}",
            causation_id=None,
            correlation_id=workflow_id,
            payload={
                "incident_id": incident_id,
                "ticket_id": None,
                "node_id": None,
                "circuit_breaker_state": "OPEN",
                "fingerprint": f"{workflow_id}:TICKET_GRAPH_UNAVAILABLE:ceo_shadow_snapshot",
            },
            occurred_at=datetime.fromisoformat("2026-03-28T10:02:00+08:00"),
        )
        repository.refresh_projections(connection)

    import app.core.ticket_handlers as ticket_handlers_module

    def _raise_graph_unavailable(*args, **kwargs):
        raise RuntimeError("ticket graph unavailable during rebuild")

    monkeypatch.setattr(ticket_handlers_module, "build_ticket_graph_snapshot", _raise_graph_unavailable)

    resolve_response = client.post(
        "/api/v1/commands/incident-resolve",
        json=_incident_resolve_payload(
            incident_id,
            followup_action="REBUILD_TICKET_GRAPH",
        ),
    )
    incident_response = client.get(f"/api/v1/projections/incidents/{incident_id}")

    assert resolve_response.status_code == 200
    assert resolve_response.json()["status"] == "REJECTED"
    assert "ticket graph unavailable during rebuild" in resolve_response.json()["reason"]
    assert incident_response.json()["data"]["incident"]["status"] == "OPEN"
    assert incident_response.json()["data"]["incident"]["circuit_breaker_state"] == "OPEN"


def test_visual_milestone_result_submit_routes_to_checker_ticket_before_board_review(client, set_ticket_time):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    _create_lease_and_start_ticket(client)

    response = client.post(
        "/api/v1/commands/ticket-result-submit",
        json=_ticket_result_submit_payload(include_review_request=True),
    )

    repository = client.app.state.repository
    maker_ticket = repository.get_current_ticket_projection("tkt_visual_001")
    node_projection = repository.get_current_node_projection("wf_seed", "node_homepage_visual")
    assert node_projection is not None
    checker_ticket = repository.get_current_ticket_projection(node_projection["latest_ticket_id"])
    with repository.connection() as connection:
        checker_created_spec = repository.get_latest_ticket_created_payload(
            connection,
            node_projection["latest_ticket_id"],
        )
    inbox_response = client.get("/api/v1/projections/inbox")
    dashboard_response = client.get("/api/v1/projections/dashboard")

    assert response.status_code == 200
    assert response.json()["status"] == "ACCEPTED"
    assert maker_ticket is not None
    assert maker_ticket["status"] == TICKET_STATUS_COMPLETED
    assert checker_ticket is not None
    assert checker_ticket["ticket_id"] != "tkt_visual_001"
    assert checker_ticket["status"] == TICKET_STATUS_PENDING
    assert checker_created_spec is not None
    assert checker_created_spec["parent_ticket_id"] == "tkt_visual_001"
    assert checker_created_spec["role_profile_ref"] == "checker_primary"
    assert checker_created_spec["output_schema_ref"] == "maker_checker_verdict"
    assert repository.list_open_approvals() == []
    assert inbox_response.json()["data"]["items"] == []
    assert dashboard_response.json()["data"]["inbox_counts"]["approvals_pending"] == 0


def test_meeting_escalation_consensus_result_submit_routes_to_checker_ticket_before_board_review(
    client,
    set_ticket_time,
):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    _create_lease_and_start_ticket(
        client,
        workflow_id="wf_scope_meeting",
        ticket_id="tkt_scope_meeting_001",
        node_id="node_scope_meeting",
        output_schema_ref="consensus_document",
        allowed_write_set=["reports/meeting/*"],
        input_artifact_refs=["art://inputs/brief.md", "art://inputs/scope-notes.md"],
        acceptance_criteria=[
            "Must produce a consensus document",
            "Must include follow-up tickets",
            "Must summarize rejected options",
        ],
        allowed_tools=["read_artifact", "write_artifact"],
        context_query_plan={
            "keywords": ["scope", "decision", "meeting"],
            "semantic_queries": ["current scope tradeoffs"],
            "max_context_tokens": 3000,
        },
    )

    response = client.post(
        "/api/v1/commands/ticket-result-submit",
        json=_consensus_document_result_submit_payload(
            workflow_id="wf_scope_meeting",
            ticket_id="tkt_scope_meeting_001",
            node_id="node_scope_meeting",
            include_review_request=True,
            review_request=_meeting_escalation_review_request(),
        ),
    )

    repository = client.app.state.repository
    maker_ticket = repository.get_current_ticket_projection("tkt_scope_meeting_001")
    node_projection = repository.get_current_node_projection("wf_scope_meeting", "node_scope_meeting")
    assert node_projection is not None
    checker_ticket = repository.get_current_ticket_projection(node_projection["latest_ticket_id"])
    with repository.connection() as connection:
        checker_created_spec = repository.get_latest_ticket_created_payload(
            connection,
            node_projection["latest_ticket_id"],
        )
    inbox_response = client.get("/api/v1/projections/inbox")

    assert response.status_code == 200
    assert response.json()["status"] == "ACCEPTED"
    assert maker_ticket is not None
    assert maker_ticket["status"] == TICKET_STATUS_COMPLETED
    assert checker_ticket is not None
    assert checker_ticket["ticket_id"] != "tkt_scope_meeting_001"
    assert checker_ticket["status"] == TICKET_STATUS_PENDING
    assert checker_created_spec is not None
    assert checker_created_spec["parent_ticket_id"] == "tkt_scope_meeting_001"
    assert checker_created_spec["role_profile_ref"] == "checker_primary"
    assert checker_created_spec["output_schema_ref"] == "maker_checker_verdict"
    assert repository.list_open_approvals() == []
    assert all(
        item["item_type"] != "BOARD_REVIEW"
        for item in inbox_response.json()["data"]["items"]
    )


def test_meeting_escalation_consensus_result_submit_requires_declared_artifact_ref(
    client,
    set_ticket_time,
):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    _create_lease_and_start_ticket(
        client,
        workflow_id="wf_scope_meeting_missing_declared_artifact",
        ticket_id="tkt_scope_meeting_missing_declared_artifact",
        node_id="node_scope_meeting_missing_declared_artifact",
        output_schema_ref="consensus_document",
        allowed_write_set=["reports/meeting/*"],
        input_artifact_refs=["art://inputs/brief.md", "art://inputs/scope-notes.md"],
        acceptance_criteria=[
            "Must produce a consensus document",
            "Must include follow-up tickets",
        ],
        allowed_tools=["read_artifact", "write_artifact"],
        context_query_plan={
            "keywords": ["scope", "decision", "meeting"],
            "semantic_queries": ["current scope tradeoffs"],
            "max_context_tokens": 3000,
        },
    )

    payload = _consensus_document_result_submit_payload(
        workflow_id="wf_scope_meeting_missing_declared_artifact",
        ticket_id="tkt_scope_meeting_missing_declared_artifact",
        node_id="node_scope_meeting_missing_declared_artifact",
        include_review_request=True,
        review_request=_meeting_escalation_review_request(),
    )
    payload["artifact_refs"] = []

    response = client.post("/api/v1/commands/ticket-result-submit", json=payload)

    repository = client.app.state.repository
    ticket = repository.get_current_ticket_projection("tkt_scope_meeting_missing_declared_artifact")

    assert response.status_code == 200
    assert ticket is not None
    assert ticket["status"] == TICKET_STATUS_FAILED
    assert ticket["last_failure_kind"] == "WORKSPACE_HOOK_VALIDATION_ERROR"
    assert repository.list_open_approvals() == []


def test_meeting_escalation_consensus_result_submit_requires_written_artifact(
    client,
    set_ticket_time,
):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    _create_lease_and_start_ticket(
        client,
        workflow_id="wf_scope_meeting_missing_written_artifact",
        ticket_id="tkt_scope_meeting_missing_written_artifact",
        node_id="node_scope_meeting_missing_written_artifact",
        output_schema_ref="consensus_document",
        allowed_write_set=["reports/meeting/*"],
        input_artifact_refs=["art://inputs/brief.md", "art://inputs/scope-notes.md"],
        acceptance_criteria=[
            "Must produce a consensus document",
            "Must include follow-up tickets",
        ],
        allowed_tools=["read_artifact", "write_artifact"],
        context_query_plan={
            "keywords": ["scope", "decision", "meeting"],
            "semantic_queries": ["current scope tradeoffs"],
            "max_context_tokens": 3000,
        },
    )

    payload = _consensus_document_result_submit_payload(
        workflow_id="wf_scope_meeting_missing_written_artifact",
        ticket_id="tkt_scope_meeting_missing_written_artifact",
        node_id="node_scope_meeting_missing_written_artifact",
        include_review_request=True,
        review_request=_meeting_escalation_review_request(),
    )
    payload["written_artifacts"] = []

    response = client.post("/api/v1/commands/ticket-result-submit", json=payload)

    repository = client.app.state.repository
    ticket = repository.get_current_ticket_projection("tkt_scope_meeting_missing_written_artifact")
    assert response.status_code == 200
    assert ticket is not None
    assert ticket["status"] == TICKET_STATUS_FAILED
    assert ticket["last_failure_kind"] == "WORKSPACE_HOOK_VALIDATION_ERROR"
    assert repository.list_open_approvals() == []


def test_meeting_escalation_consensus_result_submit_requires_declared_artifact_to_be_persisted(
    client,
    set_ticket_time,
):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    _create_lease_and_start_ticket(
        client,
        workflow_id="wf_scope_meeting_declared_artifact_not_persisted",
        ticket_id="tkt_scope_meeting_declared_artifact_not_persisted",
        node_id="node_scope_meeting_declared_artifact_not_persisted",
        output_schema_ref="consensus_document",
        allowed_write_set=["reports/meeting/*"],
        input_artifact_refs=["art://inputs/brief.md", "art://inputs/scope-notes.md"],
        acceptance_criteria=[
            "Must produce a consensus document",
            "Must include follow-up tickets",
        ],
        allowed_tools=["read_artifact", "write_artifact"],
        context_query_plan={
            "keywords": ["scope", "decision", "meeting"],
            "semantic_queries": ["current scope tradeoffs"],
            "max_context_tokens": 3000,
        },
    )

    payload = _consensus_document_result_submit_payload(
        workflow_id="wf_scope_meeting_declared_artifact_not_persisted",
        ticket_id="tkt_scope_meeting_declared_artifact_not_persisted",
        node_id="node_scope_meeting_declared_artifact_not_persisted",
        include_review_request=True,
        review_request=_meeting_escalation_review_request(),
    )
    payload["artifact_refs"] = ["art://meeting/missing-consensus-document.json"]

    response = client.post("/api/v1/commands/ticket-result-submit", json=payload)

    repository = client.app.state.repository
    ticket = repository.get_current_ticket_projection("tkt_scope_meeting_declared_artifact_not_persisted")

    assert response.status_code == 200
    assert ticket is not None
    assert ticket["status"] == TICKET_STATUS_FAILED
    assert ticket["last_failure_kind"] == "WORKSPACE_HOOK_VALIDATION_ERROR"
    assert repository.list_open_approvals() == []


def test_meeting_escalation_checker_approved_opens_review_pack_with_maker_checker_summary(
    client,
    set_ticket_time,
):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    _create_lease_and_start_ticket(
        client,
        workflow_id="wf_scope_review",
        ticket_id="tkt_scope_review_001",
        node_id="node_scope_review",
        output_schema_ref="consensus_document",
        allowed_write_set=["reports/meeting/*"],
        input_artifact_refs=["art://inputs/brief.md", "art://inputs/scope-notes.md"],
        acceptance_criteria=["Must produce a consensus document", "Must include follow-up tickets"],
        allowed_tools=["read_artifact", "write_artifact"],
        context_query_plan={
            "keywords": ["scope", "decision", "meeting"],
            "semantic_queries": ["current scope tradeoffs"],
            "max_context_tokens": 3000,
        },
    )
    maker_response = client.post(
        "/api/v1/commands/ticket-result-submit",
        json=_consensus_document_result_submit_payload(
            workflow_id="wf_scope_review",
            ticket_id="tkt_scope_review_001",
            node_id="node_scope_review",
            include_review_request=True,
            review_request=_meeting_escalation_review_request(),
        ),
    )
    assert maker_response.status_code == 200
    assert maker_response.json()["status"] == "ACCEPTED"

    repository = client.app.state.repository
    checker_ticket_id = repository.get_current_node_projection("wf_scope_review", "node_scope_review")[
        "latest_ticket_id"
    ]
    checker_lease = client.post(
        "/api/v1/commands/ticket-lease",
        json=_ticket_lease_payload(
            workflow_id="wf_scope_review",
            ticket_id=checker_ticket_id,
            node_id="node_scope_review",
            leased_by="emp_checker_1",
        ),
    )
    checker_start = client.post(
        "/api/v1/commands/ticket-start",
        json=_ticket_start_payload(
            workflow_id="wf_scope_review",
            ticket_id=checker_ticket_id,
            node_id="node_scope_review",
            started_by="emp_checker_1",
        ),
    )
    checker_result = client.post(
        "/api/v1/commands/ticket-result-submit",
        json=_maker_checker_result_submit_payload(
            workflow_id="wf_scope_review",
            ticket_id=checker_ticket_id,
            node_id="node_scope_review",
            review_status="APPROVED_WITH_NOTES",
            idempotency_key=f"ticket-result-submit:wf_scope_review:{checker_ticket_id}:approved",
        ),
    )

    approvals = repository.list_open_approvals()
    assert checker_lease.status_code == 200
    assert checker_start.status_code == 200
    assert checker_result.status_code == 200
    assert checker_result.json()["status"] == "ACCEPTED"
    assert len(approvals) == 1
    assert approvals[0]["approval_type"] == "MEETING_ESCALATION"
    assert approvals[0]["payload"]["review_pack"]["meta"]["review_type"] == "MEETING_ESCALATION"
    assert approvals[0]["payload"]["review_pack"]["maker_checker_summary"]["review_status"] == (
        "APPROVED_WITH_NOTES"
    )
    assert approvals[0]["payload"]["review_pack"]["maker_checker_summary"]["checker_employee_id"] == (
        "emp_checker_1"
    )


def test_meeting_escalation_checker_changes_required_creates_consensus_fix_ticket_and_excludes_original_maker(
    client,
    set_ticket_time,
):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    _create_lease_and_start_ticket(
        client,
        workflow_id="wf_scope_rework",
        ticket_id="tkt_scope_rework_001",
        node_id="node_scope_rework",
        output_schema_ref="consensus_document",
        allowed_write_set=["reports/meeting/*"],
        input_artifact_refs=["art://inputs/brief.md", "art://inputs/scope-notes.md"],
        acceptance_criteria=["Must produce a consensus document", "Must include follow-up tickets"],
        allowed_tools=["read_artifact", "write_artifact"],
        context_query_plan={
            "keywords": ["scope", "decision", "meeting"],
            "semantic_queries": ["current scope tradeoffs"],
            "max_context_tokens": 3000,
        },
    )
    maker_response = client.post(
        "/api/v1/commands/ticket-result-submit",
        json=_consensus_document_result_submit_payload(
            workflow_id="wf_scope_rework",
            ticket_id="tkt_scope_rework_001",
            node_id="node_scope_rework",
            include_review_request=True,
            review_request=_meeting_escalation_review_request(),
        ),
    )
    assert maker_response.status_code == 200
    assert maker_response.json()["status"] == "ACCEPTED"

    repository = client.app.state.repository
    checker_ticket_id = repository.get_current_node_projection("wf_scope_rework", "node_scope_rework")[
        "latest_ticket_id"
    ]
    client.post(
        "/api/v1/commands/ticket-lease",
        json=_ticket_lease_payload(
            workflow_id="wf_scope_rework",
            ticket_id=checker_ticket_id,
            node_id="node_scope_rework",
            leased_by="emp_checker_1",
        ),
    )
    client.post(
        "/api/v1/commands/ticket-start",
        json=_ticket_start_payload(
            workflow_id="wf_scope_rework",
            ticket_id=checker_ticket_id,
            node_id="node_scope_rework",
            started_by="emp_checker_1",
        ),
    )
    checker_result = client.post(
        "/api/v1/commands/ticket-result-submit",
        json=_maker_checker_result_submit_payload(
            workflow_id="wf_scope_rework",
            ticket_id=checker_ticket_id,
            node_id="node_scope_rework",
            review_status="CHANGES_REQUIRED",
            findings=[
                {
                    "finding_id": "finding_scope_unbounded",
                    "severity": "high",
                    "category": "SCOPE_DISCIPLINE",
                    "headline": "Consensus still includes non-MVP scope.",
                    "summary": "Document keeps remote handoff inside the current round.",
                    "required_action": "Remove non-MVP scope before board review.",
                    "blocking": True,
                }
            ],
            idempotency_key=f"ticket-result-submit:wf_scope_rework:{checker_ticket_id}:changes-required",
        ),
    )

    node_projection = repository.get_current_node_projection("wf_scope_rework", "node_scope_rework")
    assert node_projection is not None
    fix_ticket = repository.get_current_ticket_projection(node_projection["latest_ticket_id"])
    with repository.connection() as connection:
        fix_created_spec = repository.get_latest_ticket_created_payload(
            connection,
            node_projection["latest_ticket_id"],
        )

    assert checker_result.status_code == 200
    assert checker_result.json()["status"] == "ACCEPTED"
    assert fix_ticket is not None
    assert fix_ticket["ticket_id"] not in {"tkt_scope_rework_001", checker_ticket_id}
    assert fix_ticket["status"] == TICKET_STATUS_PENDING
    assert fix_created_spec is not None
    assert fix_created_spec["parent_ticket_id"] == checker_ticket_id
    assert fix_created_spec["role_profile_ref"] == "ui_designer_primary"
    assert fix_created_spec["output_schema_ref"] == "consensus_document"
    assert fix_created_spec["excluded_employee_ids"] == ["emp_frontend_2"]
    assert fix_created_spec["maker_checker_context"]["original_review_request"]["review_type"] == (
        "MEETING_ESCALATION"
    )
    assert fix_created_spec["maker_checker_context"]["blocking_finding_refs"] == [
        "finding_scope_unbounded"
    ]
    assert "Remove non-MVP scope before board review." in fix_created_spec["acceptance_criteria"][-1]


def test_checker_changes_required_creates_fix_ticket_instead_of_board_review(client, set_ticket_time):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    _create_lease_and_start_ticket(client)
    maker_response = client.post(
        "/api/v1/commands/ticket-result-submit",
        json=_ticket_result_submit_payload(include_review_request=True),
    )
    assert maker_response.status_code == 200
    assert maker_response.json()["status"] == "ACCEPTED"

    repository = client.app.state.repository
    current_node = repository.get_current_node_projection("wf_seed", "node_homepage_visual")
    assert current_node is not None
    checker_ticket_id = current_node["latest_ticket_id"]

    checker_lease = client.post(
        "/api/v1/commands/ticket-lease",
        json=_ticket_lease_payload(
            ticket_id=checker_ticket_id,
            leased_by="emp_checker_1",
        ),
    )
    checker_start = client.post(
        "/api/v1/commands/ticket-start",
        json=_ticket_start_payload(
            ticket_id=checker_ticket_id,
            started_by="emp_checker_1",
        ),
    )
    checker_result = client.post(
        "/api/v1/commands/ticket-result-submit",
        json=_maker_checker_result_submit_payload(
            ticket_id=checker_ticket_id,
            review_status="CHANGES_REQUIRED",
            idempotency_key=f"ticket-result-submit:wf_seed:{checker_ticket_id}:changes-required",
        ),
    )

    node_projection = repository.get_current_node_projection("wf_seed", "node_homepage_visual")
    assert node_projection is not None
    fix_ticket = repository.get_current_ticket_projection(node_projection["latest_ticket_id"])
    with repository.connection() as connection:
        fix_created_spec = repository.get_latest_ticket_created_payload(
            connection,
            node_projection["latest_ticket_id"],
        )
    inbox_response = client.get("/api/v1/projections/inbox")

    assert checker_lease.status_code == 200
    assert checker_lease.json()["status"] == "ACCEPTED"
    assert checker_start.status_code == 200
    assert checker_start.json()["status"] == "ACCEPTED"
    assert checker_result.status_code == 200
    assert checker_result.json()["status"] == "ACCEPTED"
    assert fix_ticket is not None
    assert fix_ticket["ticket_id"] not in {"tkt_visual_001", checker_ticket_id}
    assert fix_ticket["status"] == TICKET_STATUS_PENDING
    assert fix_created_spec is not None
    assert fix_created_spec["parent_ticket_id"] == checker_ticket_id
    assert fix_created_spec["role_profile_ref"] == "frontend_engineer_primary"
    assert fix_created_spec["output_schema_ref"] == "ui_milestone_review"
    assert fix_created_spec["excluded_employee_ids"] == ["emp_frontend_2"]
    maker_checker_context = fix_created_spec["maker_checker_context"]
    assert maker_checker_context["checker_ticket_id"] == checker_ticket_id
    assert maker_checker_context["rework_streak_count"] == 1
    assert maker_checker_context["rework_fingerprint"]
    assert maker_checker_context["blocking_finding_refs"] == ["finding_hero_hierarchy"]
    assert maker_checker_context["required_fixes"] == [
        {
            "finding_id": "finding_hero_hierarchy",
            "headline": "Hero hierarchy is not strong enough yet.",
            "required_action": "Strengthen hero hierarchy before board review.",
            "severity": "high",
            "category": "VISUAL_HIERARCHY",
        }
    ]
    assert fix_created_spec["acceptance_criteria"] == [
        "Must satisfy approved visual direction",
        "Must produce 2 options",
        "Must include rationale and risks",
        "Close checker blocking finding finding_hero_hierarchy: Strengthen hero hierarchy before board review.",
    ]
    assert repository.list_open_approvals() == []
    assert inbox_response.json()["data"]["items"] == []


def test_repeated_checker_changes_required_opens_incident_instead_of_creating_next_fix_ticket(
    client,
    set_ticket_time,
):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    _create_lease_and_start_ticket(client)
    maker_response = client.post(
        "/api/v1/commands/ticket-result-submit",
        json=_ticket_result_submit_payload(include_review_request=True),
    )
    assert maker_response.status_code == 200

    repository = client.app.state.repository
    first_checker_ticket_id = repository.get_current_node_projection("wf_seed", "node_homepage_visual")[
        "latest_ticket_id"
    ]
    client.post(
        "/api/v1/commands/ticket-lease",
        json=_ticket_lease_payload(ticket_id=first_checker_ticket_id, leased_by="emp_checker_1"),
    )
    client.post(
        "/api/v1/commands/ticket-start",
        json=_ticket_start_payload(ticket_id=first_checker_ticket_id, started_by="emp_checker_1"),
    )
    first_checker_result = client.post(
        "/api/v1/commands/ticket-result-submit",
        json=_maker_checker_result_submit_payload(
            ticket_id=first_checker_ticket_id,
            review_status="CHANGES_REQUIRED",
            idempotency_key=f"ticket-result-submit:wf_seed:{first_checker_ticket_id}:changes-required-1",
        ),
    )
    assert first_checker_result.status_code == 200

    first_fix_ticket_id = repository.get_current_node_projection("wf_seed", "node_homepage_visual")[
        "latest_ticket_id"
    ]
    client.post(
        "/api/v1/commands/ticket-lease",
        json=_ticket_lease_payload(ticket_id=first_fix_ticket_id, leased_by="emp_frontend_2"),
    )
    client.post(
        "/api/v1/commands/ticket-start",
        json=_ticket_start_payload(ticket_id=first_fix_ticket_id, started_by="emp_frontend_2"),
    )
    first_fix_submit = client.post(
        "/api/v1/commands/ticket-result-submit",
        json=_ticket_result_submit_payload(
            ticket_id=first_fix_ticket_id,
            include_review_request=True,
            artifact_refs=[
                "art://homepage/rework-option-a.png",
                "art://homepage/rework-option-b.png",
            ],
            idempotency_key=f"ticket-result-submit:wf_seed:{first_fix_ticket_id}:rework-submit",
        ),
    )
    assert first_fix_submit.status_code == 200
    assert first_fix_submit.json()["status"] == "ACCEPTED"

    second_checker_ticket_id = repository.get_current_node_projection("wf_seed", "node_homepage_visual")[
        "latest_ticket_id"
    ]
    assert second_checker_ticket_id != first_checker_ticket_id
    assert second_checker_ticket_id != first_fix_ticket_id
    client.post(
        "/api/v1/commands/ticket-lease",
        json=_ticket_lease_payload(ticket_id=second_checker_ticket_id, leased_by="emp_checker_1"),
    )
    client.post(
        "/api/v1/commands/ticket-start",
        json=_ticket_start_payload(ticket_id=second_checker_ticket_id, started_by="emp_checker_1"),
    )
    second_checker_result = client.post(
        "/api/v1/commands/ticket-result-submit",
        json=_maker_checker_result_submit_payload(
            ticket_id=second_checker_ticket_id,
            review_status="CHANGES_REQUIRED",
            idempotency_key=f"ticket-result-submit:wf_seed:{second_checker_ticket_id}:changes-required-2",
        ),
    )

    current_node = repository.get_current_node_projection("wf_seed", "node_homepage_visual")
    latest_ticket = repository.get_current_ticket_projection(current_node["latest_ticket_id"])
    incidents = repository.list_open_incidents()
    inbox_response = client.get("/api/v1/projections/inbox")

    assert second_checker_result.status_code == 200
    assert second_checker_result.json()["status"] == "ACCEPTED"
    assert latest_ticket is not None
    assert latest_ticket["ticket_id"] == second_checker_ticket_id
    assert latest_ticket["status"] == TICKET_STATUS_COMPLETED
    assert len(incidents) == 1
    assert incidents[0]["incident_type"] == "MAKER_CHECKER_REWORK_ESCALATION"
    assert incidents[0]["payload"]["rework_streak_count"] == 2
    assert incidents[0]["payload"]["latest_checker_ticket_id"] == second_checker_ticket_id
    assert incidents[0]["payload"]["rework_fingerprint"]
    assert client.app.state.repository.count_events_by_type(EVENT_CIRCUIT_BREAKER_OPENED) == 1
    assert repository.list_open_approvals() == []
    assert inbox_response.json()["data"]["items"][0]["title"] == (
        "Maker-checker rework escalation in node_homepage_visual"
    )
    assert "Repeated checker findings hit the rework threshold" in inbox_response.json()["data"]["items"][0][
        "summary"
    ]
    assert inbox_response.json()["data"]["items"][0]["badges"] == [
        "maker_checker",
        "rework",
        "circuit_breaker",
    ]


def test_different_checker_rework_fingerprint_continues_fix_chain_without_incident(client, set_ticket_time):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    _create_lease_and_start_ticket(client)
    client.post(
        "/api/v1/commands/ticket-result-submit",
        json=_ticket_result_submit_payload(include_review_request=True),
    )

    repository = client.app.state.repository
    first_checker_ticket_id = repository.get_current_node_projection("wf_seed", "node_homepage_visual")[
        "latest_ticket_id"
    ]
    client.post(
        "/api/v1/commands/ticket-lease",
        json=_ticket_lease_payload(ticket_id=first_checker_ticket_id, leased_by="emp_checker_1"),
    )
    client.post(
        "/api/v1/commands/ticket-start",
        json=_ticket_start_payload(ticket_id=first_checker_ticket_id, started_by="emp_checker_1"),
    )
    client.post(
        "/api/v1/commands/ticket-result-submit",
        json=_maker_checker_result_submit_payload(
            ticket_id=first_checker_ticket_id,
            review_status="CHANGES_REQUIRED",
            idempotency_key=f"ticket-result-submit:wf_seed:{first_checker_ticket_id}:changes-required-1",
        ),
    )

    first_fix_ticket_id = repository.get_current_node_projection("wf_seed", "node_homepage_visual")[
        "latest_ticket_id"
    ]
    client.post(
        "/api/v1/commands/ticket-lease",
        json=_ticket_lease_payload(ticket_id=first_fix_ticket_id, leased_by="emp_frontend_2"),
    )
    client.post(
        "/api/v1/commands/ticket-start",
        json=_ticket_start_payload(ticket_id=first_fix_ticket_id, started_by="emp_frontend_2"),
    )
    first_fix_submit = client.post(
        "/api/v1/commands/ticket-result-submit",
        json=_ticket_result_submit_payload(
            ticket_id=first_fix_ticket_id,
            include_review_request=True,
            artifact_refs=[
                "art://homepage/rework-option-a.png",
                "art://homepage/rework-option-b.png",
            ],
            idempotency_key=f"ticket-result-submit:wf_seed:{first_fix_ticket_id}:rework-submit",
        ),
    )
    assert first_fix_submit.status_code == 200
    assert first_fix_submit.json()["status"] == "ACCEPTED"

    second_checker_ticket_id = repository.get_current_node_projection("wf_seed", "node_homepage_visual")[
        "latest_ticket_id"
    ]
    assert second_checker_ticket_id != first_fix_ticket_id
    different_findings = [
        {
            "finding_id": "finding_navigation_density",
            "severity": "high",
            "category": "CONTENT_DENSITY",
            "headline": "Navigation density is still too high.",
            "summary": "The primary navigation continues to compete with the hero.",
            "required_action": "Reduce navigation density before board review.",
            "blocking": True,
        }
    ]
    client.post(
        "/api/v1/commands/ticket-lease",
        json=_ticket_lease_payload(ticket_id=second_checker_ticket_id, leased_by="emp_checker_1"),
    )
    client.post(
        "/api/v1/commands/ticket-start",
        json=_ticket_start_payload(ticket_id=second_checker_ticket_id, started_by="emp_checker_1"),
    )
    second_checker_result = client.post(
        "/api/v1/commands/ticket-result-submit",
        json=_maker_checker_result_submit_payload(
            ticket_id=second_checker_ticket_id,
            review_status="CHANGES_REQUIRED",
            findings=different_findings,
            idempotency_key=f"ticket-result-submit:wf_seed:{second_checker_ticket_id}:changes-required-2",
        ),
    )

    current_node = repository.get_current_node_projection("wf_seed", "node_homepage_visual")
    next_fix_ticket = repository.get_current_ticket_projection(current_node["latest_ticket_id"])
    with repository.connection() as connection:
        next_fix_created_spec = repository.get_latest_ticket_created_payload(
            connection,
            current_node["latest_ticket_id"],
        )

    assert second_checker_result.status_code == 200
    assert second_checker_result.json()["status"] == "ACCEPTED"
    assert next_fix_ticket is not None
    assert next_fix_ticket["ticket_id"] not in {second_checker_ticket_id, first_fix_ticket_id}
    assert next_fix_ticket["status"] == TICKET_STATUS_PENDING
    assert repository.list_open_incidents() == []
    assert next_fix_created_spec["maker_checker_context"]["rework_streak_count"] == 1
    assert next_fix_created_spec["maker_checker_context"]["blocking_finding_refs"] == [
        "finding_navigation_density"
    ]


def test_review_room_route_returns_existing_projection(client):
    approval = _seed_review_request(client)

    response = client.get(f"/api/v1/projections/review-room/{approval['review_pack_id']}")

    assert response.status_code == 200
    body = response.json()["data"]
    assert body["review_pack"]["meta"]["approval_id"] == approval["approval_id"]
    assert body["review_pack"]["subject"]["source_ticket_id"] != "tkt_visual_001"
    assert body["review_pack"]["trigger"]["trigger_event_id"].startswith("evt_")
    assert body["review_pack"]["decision_form"]["command_target_version"] >= 1
    assert body["available_actions"] == ["APPROVE", "REJECT", "MODIFY_CONSTRAINTS"]


def test_review_room_route_includes_board_advisory_context(client):
    approval = _seed_review_request(client, workflow_id="wf_review_room_advisory")

    response = client.get(f"/api/v1/projections/review-room/{approval['review_pack_id']}")

    assert response.status_code == 200
    body = response.json()["data"]
    advisory_context = body["review_pack"]["advisory_context"]
    assert advisory_context["approval_id"] == approval["approval_id"]
    assert advisory_context["review_pack_id"] == approval["review_pack_id"]
    assert advisory_context["trigger_type"] == "CONSTRAINT_CHANGE"
    assert advisory_context["status"] == "OPEN"
    assert advisory_context["supports_governance_patch"] is True
    assert advisory_context["current_governance_modes"] == {
        "approval_mode": "AUTO_CEO",
        "audit_mode": "MINIMAL",
    }
    assert advisory_context["affected_nodes"] == ["node_homepage_visual"]


def test_review_room_developer_inspector_returns_materialized_payloads(client):
    _seed_cross_workflow_compile_history(client)
    approval = _seed_review_request(client, materialize_real_compile=True)

    response = client.get(
        f"/api/v1/projections/review-room/{approval['review_pack_id']}/developer-inspector"
    )
    body = response.json()["data"]
    store = client.app.state.developer_inspector_store
    repository = client.app.state.repository
    latest_bundle = repository.get_latest_compiled_context_bundle_by_ticket("tkt_visual_001")
    latest_manifest = repository.get_latest_compile_manifest_by_ticket("tkt_visual_001")

    assert response.status_code == 200
    assert latest_bundle is not None
    assert latest_manifest is not None
    assert body["review_pack_id"] == approval["review_pack_id"]
    assert body["compiled_context_bundle_ref"] == "ctx://homepage/visual-v1"
    assert body["compile_manifest_ref"] == "manifest://homepage/visual-v1"
    assert body["availability"] == "ready"
    assert body["compile_summary"]["source_count"] >= 1
    assert body["compile_summary"]["degraded_source_count"] >= 1
    assert body["compile_summary"]["reason_counts"]["ARTIFACT_NOT_INDEXED"] >= 1
    assert body["compile_summary"]["retrieved_source_count"] == 3
    assert body["compile_summary"]["retrieval_channel_counts"] == {
        "artifact_summaries": 1,
        "incident_summaries": 1,
        "review_summaries": 1,
    }
    assert body["compile_summary"]["dropped_retrieval_count"] == 0
    assert body["compile_summary"]["total_budget_tokens"] == 3000
    assert 0 < body["compile_summary"]["used_budget_tokens"] <= body["compile_summary"]["total_budget_tokens"]
    assert (
        body["compile_summary"]["remaining_budget_tokens"]
        == body["compile_summary"]["total_budget_tokens"] - body["compile_summary"]["used_budget_tokens"]
    )
    assert body["compile_summary"]["truncated_tokens"] >= 0
    assert body["compile_summary"]["dropped_explicit_source_count"] == 0
    assert body["compiled_context_bundle"]["meta"]["bundle_id"] == latest_bundle["bundle_id"]
    assert body["compile_manifest"]["compile_meta"]["compile_id"] == latest_manifest["compile_id"]
    assert store.resolve_path("ctx://homepage/visual-v1").exists()
    assert store.resolve_path("manifest://homepage/visual-v1").exists()


def test_review_room_developer_inspector_returns_rendered_execution_payload_and_summary(client):
    _seed_cross_workflow_compile_history(client)
    approval = _seed_review_request(
        client,
        materialize_real_compile=True,
        rendered_execution_payload_ref="render://homepage/visual-v1",
    )

    response = client.get(
        f"/api/v1/projections/review-room/{approval['review_pack_id']}/developer-inspector"
    )

    assert response.status_code == 200
    body = response.json()["data"]
    assert body["availability"] == "ready"
    assert body["rendered_execution_payload_ref"] == "render://homepage/visual-v1"
    assert body["rendered_execution_payload"]["meta"]["render_target"] == "json_messages_v1"
    assert body["render_summary"]["control_message_count"] == 3
    assert body["render_summary"]["data_message_count"] == len(
        body["compiled_context_bundle"]["context_blocks"]
    )
    assert body["rendered_execution_payload"]["summary"] == body["render_summary"]
    assert body["rendered_execution_payload"]["messages"][-1]["channel"] == "OUTPUT_CONTRACT_REMINDER"


def test_review_room_developer_inspector_compile_summary_counts_media_reference_only(client):
    _seed_input_artifact(
        client=client,
        artifact_ref="art://inputs/brief.md",
        logical_path="artifacts/inputs/mock.png",
        content_bytes=b"\x89PNG\r\n\x1a\nmock-image",
        kind="IMAGE",
        media_type="image/png",
    )
    approval = _seed_review_request(client, materialize_real_compile=True)

    response = client.get(
        f"/api/v1/projections/review-room/{approval['review_pack_id']}/developer-inspector"
    )

    assert response.status_code == 200
    body = response.json()["data"]
    assert body["compile_summary"]["reason_counts"]["MEDIA_REFERENCE_ONLY"] >= 1
    assert body["compile_summary"]["media_reference_count"] >= 1
    assert body["compile_summary"]["preview_kind_counts"]["INLINE_MEDIA"] >= 1


def test_review_room_developer_inspector_compile_summary_counts_inline_fragments(client):
    _seed_input_artifact(
        client=client,
        artifact_ref="art://inputs/brief.md",
        logical_path="artifacts/inputs/brief.md",
        content=(
            "# Intro\n\n"
            + ("This introduction is intentionally verbose and non-actionable. " * 320)
            + "\n\n## Acceptance Contract\n\n"
            "This section defines the homepage visual output contract, review path, and brand risk reminders.\n\n"
            "## Delivery Notes\n\nShip the homepage visual option with explicit brand review evidence.\n"
        ),
    )
    approval = _seed_review_request(client, materialize_real_compile=True)

    response = client.get(
        f"/api/v1/projections/review-room/{approval['review_pack_id']}/developer-inspector"
    )

    assert response.status_code == 200
    body = response.json()["data"]
    assert body["compile_summary"]["inline_fragment_count"] >= 1
    assert body["compile_summary"]["fragment_strategy_counts"]["MARKDOWN_SECTION_MATCH"] >= 1


def test_review_room_developer_inspector_compile_summary_counts_preview_and_download_strategies(client):
    _seed_input_artifact(
        client=client,
        artifact_ref="art://inputs/brief.md",
        logical_path="artifacts/inputs/brief.md",
        content=("Neutral source content without keyword matches. " * 800),
        kind="TEXT",
        media_type="text/plain",
    )
    _seed_input_artifact(
        client=client,
        artifact_ref="art://inputs/brand-guide.md",
        logical_path="artifacts/inputs/archive.zip",
        content_bytes=b"PK\x03\x04mock-zip",
        kind="BINARY",
        media_type="application/zip",
    )
    approval = _seed_review_request(client, materialize_real_compile=True)

    response = client.get(
        f"/api/v1/projections/review-room/{approval['review_pack_id']}/developer-inspector"
    )

    assert response.status_code == 200
    body = response.json()["data"]
    assert body["compile_summary"]["preview_strategy_counts"]["HEAD_EXCERPT"] >= 1
    assert body["compile_summary"]["download_attachment_count"] >= 1
    assert body["compile_summary"]["preview_kind_counts"]["DOWNLOAD_ONLY"] >= 1


def test_review_room_developer_inspector_returns_partial_when_refs_are_unmaterialized(client):
    approval = _seed_review_request(client)

    response = client.get(
        f"/api/v1/projections/review-room/{approval['review_pack_id']}/developer-inspector"
    )
    body = response.json()["data"]

    assert response.status_code == 200
    assert body["availability"] == "partial"
    assert body["compiled_context_bundle_ref"] == "ctx://homepage/visual-v1"
    assert body["compile_manifest_ref"] == "manifest://homepage/visual-v1"
    assert body["rendered_execution_payload_ref"] is None
    assert body["compile_summary"] is None
    assert body["render_summary"] is None
    assert body["compiled_context_bundle"] is None
    assert body["compile_manifest"] is None
    assert body["rendered_execution_payload"] is None


def test_review_room_developer_inspector_returns_404_for_missing_review_pack(client):
    response = client.get("/api/v1/projections/review-room/brp_missing/developer-inspector")

    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_ticket_artifacts_projection_returns_404_for_missing_ticket(client):
    response = client.get("/api/v1/projections/tickets/tkt_missing/artifacts")

    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_ticket_artifacts_projection_exposes_cleanup_audit_fields(client, set_ticket_time):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    _create_lease_and_start_ticket(client)
    artifact_ref = "art://reports/homepage/ticket-cleanup-fields.md"

    submit_response = client.post(
        "/api/v1/commands/ticket-result-submit",
        json=_ticket_result_submit_payload(
            artifact_refs=[artifact_ref],
            payload={
                "summary": "Ticket artifact projection should expose cleanup audit fields.",
                "recommended_option_id": "option_a",
                "options": [
                    {
                        "option_id": "option_a",
                        "label": "Option A",
                        "summary": "Projection field option.",
                        "artifact_refs": [artifact_ref],
                    }
                ],
            },
            written_artifacts=[
                {
                    "path": "reports/review/ticket-cleanup-fields.md",
                    "artifact_ref": artifact_ref,
                    "kind": "MARKDOWN",
                    "content_text": "# Cleanup\n\nProjection audit fields.\n",
                    "retention_class": "EPHEMERAL",
                    "retention_ttl_sec": 60,
                }
            ],
            idempotency_key="ticket-result-submit:wf_seed:tkt_visual_001:ticket-cleanup-fields",
        ),
    )
    set_ticket_time("2026-03-28T10:02:00+08:00")
    cleanup_response = client.post(
        "/api/v1/commands/artifact-cleanup",
        json={
            "cleaned_by": "emp_ops_1",
            "idempotency_key": "artifact-cleanup:ticket-cleanup-fields",
        },
    )
    projection_response = client.get("/api/v1/projections/tickets/tkt_visual_001/artifacts")
    projected_artifact = next(
        item for item in projection_response.json()["data"]["artifacts"] if item["artifact_ref"] == artifact_ref
    )

    assert submit_response.status_code == 200
    assert cleanup_response.status_code == 200
    assert projection_response.status_code == 200
    assert projected_artifact["lifecycle_status"] == "EXPIRED"
    assert projected_artifact["deleted_by"] == "emp_ops_1"
    assert projected_artifact["delete_reason"] == "Expired by artifact cleanup."
    assert projected_artifact["storage_deleted_at"] is not None


def test_ticket_complete_rejects_legacy_developer_inspector_payloads(client):
    _create_lease_and_start_ticket(client)
    payload = _ticket_complete_payload()
    payload["review_request"]["developer_inspector_payloads"] = {
        "compiled_context_bundle": {"meta": {"bundle_id": "legacy_bundle"}},
        "compile_manifest": {"compile_meta": {"compile_id": "legacy_manifest"}},
    }

    response = client.post("/api/v1/commands/ticket-complete", json=payload)

    assert response.status_code == 422
    assert "developer_inspector_payloads" in response.text

def test_ticket_complete_rejects_invalid_developer_inspector_ref(client):
    _create_lease_and_start_ticket(client)
    response = client.post(
        "/api/v1/commands/ticket-complete",
        json=_ticket_complete_payload(
            compiled_context_bundle_ref="ctx://homepage/../escape",
        ),
    )

    assert response.status_code == 422
    assert "unsafe segment" in response.text


def test_missing_review_room_returns_404(client):
    response = client.get("/api/v1/projections/review-room/brp_missing")

    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_employee_hire_request_opens_core_hire_approval_in_inbox_and_review_room(client):
    workflow_response = client.post("/api/v1/commands/project-init", json=_project_init_payload("Staff workflow"))
    workflow_id = workflow_response.json()["causation_hint"].split(":", 1)[1]

    response = client.post(
        "/api/v1/commands/employee-hire-request",
        json=_employee_hire_request_payload(workflow_id),
    )

    inbox_response = client.get("/api/v1/projections/inbox")
    assert response.status_code == 200
    assert response.json()["status"] == "ACCEPTED"
    items = [
        item
        for item in inbox_response.json()["data"]["items"]
        if item["item_type"] == "CORE_HIRE_APPROVAL"
    ]
    assert len(items) == 1
    assert items[0]["item_type"] == "CORE_HIRE_APPROVAL"
    assert items[0]["route_target"]["view"] == "review_room"

    review_pack_id = items[0]["route_target"]["review_pack_id"]
    review_room_response = client.get(f"/api/v1/projections/review-room/{review_pack_id}")

    assert review_room_response.status_code == 200
    review_pack = review_room_response.json()["data"]["review_pack"]
    assert review_pack["meta"]["review_type"] == "CORE_HIRE_APPROVAL"
    assert review_pack["subject"]["change_kind"] == "EMPLOYEE_HIRE"
    assert review_pack["subject"]["employee_id"] == "emp_frontend_backup"
    assert review_pack["employee_change"]["skill_profile"]["system_scope"] == "surface_polish"
    assert review_pack["employee_change"]["personality_profile"]["risk_posture"] == "cautious"
    assert review_pack["employee_change"]["aesthetic_profile"]["surface_preference"] == "polished"


def test_employee_hire_request_rejects_high_overlap_same_role_profile(client):
    workflow_response = client.post("/api/v1/commands/project-init", json=_project_init_payload("Staff workflow"))
    workflow_id = workflow_response.json()["causation_hint"].split(":", 1)[1]

    response = client.post(
        "/api/v1/commands/employee-hire-request",
        json=_employee_hire_request_payload(
            workflow_id,
            employee_id="emp_frontend_overlap",
            skill_profile={"primary_domain": "frontend"},
            personality_profile={"style": "maker"},
            aesthetic_profile={"preference": "minimal"},
        ),
    )

    assert response.status_code == 200
    assert response.json()["status"] == "REJECTED"
    assert "too similar" in response.json()["reason"].lower()


def test_employee_hire_request_rejects_unsupported_mainline_staffing_combo(client):
    workflow_response = client.post("/api/v1/commands/project-init", json=_project_init_payload("Staff workflow"))
    workflow_id = workflow_response.json()["causation_hint"].split(":", 1)[1]

    response = client.post(
        "/api/v1/commands/employee-hire-request",
        json=_employee_hire_request_payload(
            workflow_id,
            employee_id="emp_platform_ops",
            role_type="platform_engineer",
            role_profile_refs=["platform_ops_primary"],
        ),
    )

    assert response.status_code == 200
    assert response.json()["status"] == "REJECTED"
    assert "not on the current local mvp staffing path" in response.json()["reason"].lower()


def test_employee_hire_request_accepts_governance_cto_on_board_workforce_path(client):
    workflow_response = client.post("/api/v1/commands/project-init", json=_project_init_payload("Staff workflow"))
    workflow_id = workflow_response.json()["causation_hint"].split(":", 1)[1]

    response = client.post(
        "/api/v1/commands/employee-hire-request",
        json=_employee_hire_request_payload(
            workflow_id,
            employee_id="emp_cto_governance",
            role_type="governance_cto",
            role_profile_refs=["cto_primary"],
            skill_profile={"primary_domain": "architecture"},
            personality_profile={"risk_posture": "guarded"},
            aesthetic_profile={"surface_preference": "clarifying"},
            request_summary="Hire a CTO governance role for architecture direction.",
        ),
    )

    assert response.status_code == 200
    assert response.json()["status"] == "ACCEPTED"


def test_employee_replace_request_rejects_role_profile_mismatch_for_supported_role(client):
    workflow_response = client.post("/api/v1/commands/project-init", json=_project_init_payload("Replace maker"))
    workflow_id = workflow_response.json()["causation_hint"].split(":", 1)[1]

    response = client.post(
        "/api/v1/commands/employee-replace-request",
        json=_employee_replace_request_payload(
            workflow_id,
            replacement_employee_id="emp_frontend_backup_replace",
            replacement_role_type="frontend_engineer",
            replacement_role_profile_refs=["checker_primary"],
        ),
    )

    assert response.status_code == 200
    assert response.json()["status"] == "REJECTED"
    assert "must use role profile refs" in response.json()["reason"].lower()


def test_board_approve_core_hire_request_adds_employee_to_workforce_projection(client):
    workflow_response = client.post("/api/v1/commands/project-init", json=_project_init_payload("Staff workflow"))
    workflow_id = workflow_response.json()["causation_hint"].split(":", 1)[1]
    client.post(
        "/api/v1/commands/employee-hire-request",
        json=_employee_hire_request_payload(workflow_id),
    )

    repository = client.app.state.repository
    approval = repository.list_open_approvals()[0]
    option_id = approval["payload"]["review_pack"]["options"][0]["option_id"]

    approve_response = client.post(
        "/api/v1/commands/board-approve",
        json={
            "review_pack_id": approval["review_pack_id"],
            "review_pack_version": approval["review_pack_version"],
            "command_target_version": approval["command_target_version"],
            "approval_id": approval["approval_id"],
            "selected_option_id": option_id,
            "board_comment": "Approve this backup hire.",
            "idempotency_key": f"board-approve:{approval['approval_id']}:hire",
        },
    )

    workforce_response = client.get("/api/v1/projections/workforce")
    hired_employee = repository.get_employee_projection("emp_frontend_backup")

    assert approve_response.status_code == 200
    assert approve_response.json()["status"] == "ACCEPTED"
    assert hired_employee is not None
    assert hired_employee["state"] == "ACTIVE"
    assert hired_employee["board_approved"] is True
    assert hired_employee["personality_profile_json"]["risk_posture"] == "cautious"
    frontend_lane = next(
        lane
        for lane in workforce_response.json()["data"]["role_lanes"]
        if lane["role_type"] == "frontend_engineer"
    )
    assert [worker["employee_id"] for worker in frontend_lane["workers"]] == [
        "emp_frontend_2",
        "emp_frontend_backup",
    ]
    hired_worker = next(worker for worker in frontend_lane["workers"] if worker["employee_id"] == "emp_frontend_backup")
    assert hired_worker["profile_summary"]
    assert hired_worker["skill_profile"]["system_scope"] == "surface_polish"


def test_board_approve_core_hire_request_adds_governance_cto_to_workforce_lane(client):
    workflow_response = client.post("/api/v1/commands/project-init", json=_project_init_payload("Staff workflow"))
    workflow_id = workflow_response.json()["causation_hint"].split(":", 1)[1]
    client.post(
        "/api/v1/commands/employee-hire-request",
        json=_employee_hire_request_payload(
            workflow_id,
            employee_id="emp_cto_governance",
            role_type="governance_cto",
            role_profile_refs=["cto_primary"],
            skill_profile={"primary_domain": "architecture"},
            personality_profile={"risk_posture": "guarded"},
            aesthetic_profile={"surface_preference": "clarifying"},
            request_summary="Hire a CTO governance role for architecture direction.",
        ),
    )

    repository = client.app.state.repository
    approval = repository.list_open_approvals()[0]
    option_id = approval["payload"]["review_pack"]["options"][0]["option_id"]

    approve_response = client.post(
        "/api/v1/commands/board-approve",
        json={
            "review_pack_id": approval["review_pack_id"],
            "review_pack_version": approval["review_pack_version"],
            "command_target_version": approval["command_target_version"],
            "approval_id": approval["approval_id"],
            "selected_option_id": option_id,
            "board_comment": "Approve the CTO governance role.",
            "idempotency_key": f"board-approve:{approval['approval_id']}:hire-cto",
        },
    )

    workforce_response = client.get("/api/v1/projections/workforce")
    hired_employee = repository.get_employee_projection("emp_cto_governance")

    assert approve_response.status_code == 200
    assert approve_response.json()["status"] == "ACCEPTED"
    assert hired_employee is not None
    assert hired_employee["state"] == "ACTIVE"
    cto_lane = next(
        lane
        for lane in workforce_response.json()["data"]["role_lanes"]
        if lane["role_type"] == "governance_cto"
    )
    hired_worker = next(worker for worker in cto_lane["workers"] if worker["employee_id"] == "emp_cto_governance")
    assert hired_worker["source_template_id"] == "cto_governance"
    assert hired_worker["available_actions"] == [
        {
            "action_type": "FREEZE",
            "enabled": True,
            "disabled_reason": None,
            "template_id": None,
        },
        {
            "action_type": "RESTORE",
            "enabled": False,
            "disabled_reason": "Only frozen workers can be restored.",
            "template_id": None,
        },
        {
            "action_type": "REPLACE",
            "enabled": True,
            "disabled_reason": None,
            "template_id": "cto_governance_backup",
        },
    ]


def test_employee_replace_request_rejects_high_overlap_against_other_active_same_role_worker(client):
    workflow_response = client.post("/api/v1/commands/project-init", json=_project_init_payload("Replace maker"))
    workflow_id = workflow_response.json()["causation_hint"].split(":", 1)[1]

    _seed_worker(client, employee_id="emp_frontend_3")

    response = client.post(
        "/api/v1/commands/employee-replace-request",
        json=_employee_replace_request_payload(
            workflow_id,
            replacement_employee_id="emp_frontend_overlap_replace",
            replacement_skill_profile={"primary_domain": "frontend"},
            replacement_personality_profile={"style": "maker"},
            replacement_aesthetic_profile={"preference": "minimal"},
        ),
    )

    assert response.status_code == 200
    assert response.json()["status"] == "REJECTED"
    assert "too similar" in response.json()["reason"].lower()


def test_workforce_projection_exposes_staffing_templates_and_server_driven_actions(client):
    workflow_response = client.post("/api/v1/commands/project-init", json=_project_init_payload("Staff workflow"))
    workflow_id = workflow_response.json()["causation_hint"].split(":", 1)[1]

    client.post(
        "/api/v1/commands/employee-freeze",
        json=_employee_freeze_payload(
            workflow_id,
            employee_id="emp_checker_1",
        ),
    )

    workforce_response = client.get("/api/v1/projections/workforce")

    assert workforce_response.status_code == 200
    body = workforce_response.json()["data"]
    assert [template["template_id"] for template in body["hire_templates"]] == [
        "frontend_engineer_backup",
        "checker_backup",
        "backend_engineer_backup",
        "database_engineer_backup",
        "platform_sre_backup",
        "architect_governance_backup",
        "cto_governance_backup",
    ]
    assert [template["template_id"] for template in body["role_templates_catalog"]["role_templates"]] == [
        "scope_consensus_primary",
        "frontend_delivery_primary",
        "quality_checker_primary",
        "backend_execution_reserved",
        "database_execution_reserved",
        "platform_sre_reserved",
        "architect_governance",
        "cto_governance",
    ]
    assert [kind["kind_ref"] for kind in body["role_templates_catalog"]["document_kinds"]] == [
        "architecture_brief",
        "technology_decision",
        "milestone_plan",
        "detailed_design",
        "backlog_recommendation",
    ]
    assert [fragment["fragment_id"] for fragment in body["role_templates_catalog"]["fragments"]] == [
        "skill_frontend_ui",
        "skill_backend_services",
        "skill_database_reliability",
        "skill_platform_operations",
        "skill_architecture_governance",
        "skill_quality_validation",
        "delivery_execution_loop",
        "delivery_document_first",
        "review_internal_gate",
    ]
    assert body["role_templates_catalog"]["role_templates"][0]["status"] == "LIVE"
    assert body["role_templates_catalog"]["role_templates"][0]["canonical_role_ref"] == "ui_designer_primary"
    assert body["role_templates_catalog"]["role_templates"][3]["provider_target_ref"] == "role_profile:backend_engineer_primary"
    assert body["role_templates_catalog"]["role_templates"][0]["mainline_boundary"] == {
        "boundary_status": "LIVE_ON_MAINLINE",
        "active_path_refs": [
            "catalog_readonly",
            "scope_consensus",
            "governance_document_live",
        ],
        "blocked_path_refs": [],
    }
    assert body["role_templates_catalog"]["role_templates"][1]["mainline_boundary"] == {
        "boundary_status": "LIVE_ON_MAINLINE",
        "active_path_refs": [
            "catalog_readonly",
            "governance_document_live",
            "implementation_delivery",
            "final_review",
            "closeout",
        ],
        "blocked_path_refs": [],
    }
    assert body["role_templates_catalog"]["role_templates"][2]["mainline_boundary"] == {
        "boundary_status": "LIVE_ON_MAINLINE",
        "active_path_refs": [
            "catalog_readonly",
            "checker_gate",
        ],
        "blocked_path_refs": [],
    }
    assert body["role_templates_catalog"]["role_templates"][3]["status"] == "LIVE"
    assert body["role_templates_catalog"]["role_templates"][6]["status"] == "LIVE"
    assert body["role_templates_catalog"]["role_templates"][3]["mainline_boundary"] == {
        "boundary_status": "LIVE_ON_MAINLINE",
        "active_path_refs": [
            "catalog_readonly",
            "staffing",
            "workforce_lane",
            "implementation_delivery",
        ],
        "blocked_path_refs": [
            "ceo_create_ticket",
        ],
    }
    assert body["role_templates_catalog"]["role_templates"][6]["mainline_boundary"] == {
        "boundary_status": "LIVE_ON_MAINLINE",
        "active_path_refs": [
            "catalog_readonly",
            "staffing",
            "workforce_lane",
            "ceo_create_ticket",
            "governance_document_live",
        ],
        "blocked_path_refs": [],
    }

    frontend_lane = next(
        lane
        for lane in body["role_lanes"]
        if lane["role_type"] == "frontend_engineer"
    )
    active_frontend_worker = next(
        worker
        for worker in frontend_lane["workers"]
        if worker["employee_id"] == "emp_frontend_2"
    )
    assert active_frontend_worker["employment_state"] == "ACTIVE"
    assert active_frontend_worker["profile_summary"]
    assert active_frontend_worker["skill_profile"]["primary_domain"] == "frontend"
    assert active_frontend_worker["source_template_id"] == "frontend_delivery_primary"
    assert active_frontend_worker["source_fragment_refs"] == [
        "skill_frontend_ui",
        "delivery_execution_loop",
    ]
    assert active_frontend_worker["available_actions"] == [
        {
            "action_type": "FREEZE",
            "enabled": True,
            "disabled_reason": None,
            "template_id": None,
        },
        {
            "action_type": "RESTORE",
            "enabled": False,
            "disabled_reason": "Only frozen workers can be restored.",
            "template_id": None,
        },
        {
            "action_type": "REPLACE",
            "enabled": True,
            "disabled_reason": None,
            "template_id": "frontend_engineer_backup",
        },
    ]

    checker_lane = next(lane for lane in body["role_lanes"] if lane["role_type"] == "checker")
    frozen_checker = next(worker for worker in checker_lane["workers"] if worker["employee_id"] == "emp_checker_1")
    assert frozen_checker["employment_state"] == "FROZEN"
    assert frozen_checker["available_actions"] == [
        {
            "action_type": "FREEZE",
            "enabled": False,
            "disabled_reason": "Only active workers can be frozen.",
            "template_id": None,
        },
        {
            "action_type": "RESTORE",
            "enabled": True,
            "disabled_reason": None,
            "template_id": None,
        },
        {
            "action_type": "REPLACE",
            "enabled": False,
            "disabled_reason": "Only active workers can be replaced.",
            "template_id": "checker_backup",
        },
    ]


def test_board_approve_employee_replace_request_marks_old_employee_replaced(client):
    workflow_response = client.post("/api/v1/commands/project-init", json=_project_init_payload("Replace maker"))
    workflow_id = workflow_response.json()["causation_hint"].split(":", 1)[1]

    client.post(
        "/api/v1/commands/employee-replace-request",
        json=_employee_replace_request_payload(
            workflow_id,
            replacement_employee_id="emp_frontend_backup_replace",
        ),
    )

    repository = client.app.state.repository
    approval = repository.list_open_approvals()[0]
    option_id = approval["payload"]["review_pack"]["options"][0]["option_id"]

    approve_response = client.post(
        "/api/v1/commands/board-approve",
        json={
            "review_pack_id": approval["review_pack_id"],
            "review_pack_version": approval["review_pack_version"],
            "command_target_version": approval["command_target_version"],
            "approval_id": approval["approval_id"],
            "selected_option_id": option_id,
            "board_comment": "Replace the current maker with backup coverage.",
            "idempotency_key": f"board-approve:{approval['approval_id']}:replace",
        },
    )

    replaced_employee = repository.get_employee_projection("emp_frontend_2")
    replacement_employee = repository.get_employee_projection("emp_frontend_backup_replace")

    assert approve_response.status_code == 200
    assert approve_response.json()["status"] == "ACCEPTED"
    assert replaced_employee is not None
    assert replaced_employee["state"] == "REPLACED"
    assert replacement_employee is not None
    assert replacement_employee["state"] == "ACTIVE"


def test_employee_freeze_requeues_leased_ticket_and_excludes_frozen_employee(client, set_ticket_time):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    workflow_response = client.post(
        "/api/v1/commands/project-init",
        json=_project_init_payload("Freeze leased ticket containment"),
    )
    workflow_id = workflow_response.json()["causation_hint"].split(":", 1)[1]

    _create_and_lease_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_frozen_leased",
        node_id="node_frozen_leased",
    )

    freeze_response = client.post(
        "/api/v1/commands/employee-freeze",
        json=_employee_freeze_payload(workflow_id),
    )

    repository = client.app.state.repository
    ticket_projection = repository.get_current_ticket_projection("tkt_frozen_leased")
    with repository.connection() as connection:
        updated_created_spec = repository.get_latest_ticket_created_payload(
            connection,
            "tkt_frozen_leased",
        )

    assert freeze_response.status_code == 200
    assert freeze_response.json()["status"] == "ACCEPTED"
    assert ticket_projection is not None
    assert ticket_projection["status"] == TICKET_STATUS_PENDING
    assert ticket_projection["lease_owner"] is None
    assert updated_created_spec is not None
    assert updated_created_spec["excluded_employee_ids"] == ["emp_frontend_2"]


def test_board_approve_employee_replace_request_requeues_leased_ticket_from_replaced_employee(
    client,
    set_ticket_time,
):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    workflow_response = client.post(
        "/api/v1/commands/project-init",
        json=_project_init_payload("Replace leased maker"),
    )
    workflow_id = workflow_response.json()["causation_hint"].split(":", 1)[1]

    _create_and_lease_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_replaced_leased",
        node_id="node_replaced_leased",
    )
    client.post(
        "/api/v1/commands/employee-replace-request",
        json=_employee_replace_request_payload(
            workflow_id,
            replacement_employee_id="emp_frontend_backup_replace",
        ),
    )

    repository = client.app.state.repository
    approval = repository.list_open_approvals()[0]
    option_id = approval["payload"]["review_pack"]["options"][0]["option_id"]
    approve_response = client.post(
        "/api/v1/commands/board-approve",
        json={
            "review_pack_id": approval["review_pack_id"],
            "review_pack_version": approval["review_pack_version"],
            "command_target_version": approval["command_target_version"],
            "approval_id": approval["approval_id"],
            "selected_option_id": option_id,
            "board_comment": "Replace the leased maker with backup coverage.",
            "idempotency_key": f"board-approve:{approval['approval_id']}:replace-leased",
        },
    )

    replaced_employee = repository.get_employee_projection("emp_frontend_2")
    replacement_employee = repository.get_employee_projection("emp_frontend_backup_replace")
    ticket_projection = repository.get_current_ticket_projection("tkt_replaced_leased")
    with repository.connection() as connection:
        updated_created_spec = repository.get_latest_ticket_created_payload(
            connection,
            "tkt_replaced_leased",
        )

    assert approve_response.status_code == 200
    assert approve_response.json()["status"] == "ACCEPTED"
    assert replaced_employee is not None
    assert replaced_employee["state"] == "REPLACED"
    assert replacement_employee is not None
    assert replacement_employee["state"] == "ACTIVE"
    assert ticket_projection is not None
    assert ticket_projection["status"] == TICKET_STATUS_PENDING
    assert ticket_projection["lease_owner"] is None
    assert updated_created_spec is not None
    assert updated_created_spec["excluded_employee_ids"] == ["emp_frontend_2"]


def test_employee_freeze_blocks_manual_lease_and_worker_runtime_bootstrap(
    client,
    set_ticket_time,
    monkeypatch,
):
    monkeypatch.setenv("BOARDROOM_OS_WORKER_BOOTSTRAP_SIGNING_SECRET", "bootstrap-secret")
    monkeypatch.setenv("BOARDROOM_OS_WORKER_SESSION_TTL_SEC", "600")
    monkeypatch.setenv("BOARDROOM_OS_WORKER_DELIVERY_SIGNING_SECRET", "delivery-secret")
    set_ticket_time("2026-03-28T10:00:00+08:00")
    workflow_response = client.post("/api/v1/commands/project-init", json=_project_init_payload("Freeze maker"))
    workflow_id = workflow_response.json()["causation_hint"].split(":", 1)[1]

    _create_and_lease_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_frozen_runtime",
        node_id="node_frozen_runtime",
    )
    active_runtime_response = client.get(
        "/api/v1/worker-runtime/assignments",
        headers=_worker_bootstrap_headers(),
    )

    freeze_response = client.post(
        "/api/v1/commands/employee-freeze",
        json=_employee_freeze_payload(workflow_id),
    )
    create_response = client.post(
        "/api/v1/commands/ticket-create",
        json=_ticket_create_payload(
            workflow_id=workflow_id,
            ticket_id="tkt_frozen_worker",
            node_id="node_frozen_worker",
        ),
    )
    lease_response = client.post(
        "/api/v1/commands/ticket-lease",
        json=_ticket_lease_payload(
            workflow_id=workflow_id,
            ticket_id="tkt_frozen_worker",
            node_id="node_frozen_worker",
            leased_by="emp_frontend_2",
        ),
    )
    runtime_response = client.get(
        "/api/v1/worker-runtime/assignments",
        headers=_worker_bootstrap_headers(issued_at="2026-03-28T10:06:00+08:00"),
    )

    assert active_runtime_response.status_code == 200
    assert freeze_response.status_code == 200
    assert freeze_response.json()["status"] == "ACCEPTED"
    assert create_response.status_code == 200
    assert create_response.json()["status"] == "ACCEPTED"
    assert lease_response.status_code == 200
    assert lease_response.json()["status"] == "REJECTED"
    assert "not active" in lease_response.json()["reason"].lower()
    assert runtime_response.status_code == 403
    assert "not active" in runtime_response.json()["detail"].lower()


def test_employee_freeze_containment_opens_staffing_incident_for_executing_ticket(client, set_ticket_time):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    workflow_response = client.post(
        "/api/v1/commands/project-init",
        json=_project_init_payload("Freeze executing ticket containment"),
    )
    workflow_id = workflow_response.json()["causation_hint"].split(":", 1)[1]

    _create_lease_and_start_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_frozen_executing",
        node_id="node_frozen_executing",
    )

    freeze_response = client.post(
        "/api/v1/commands/employee-freeze",
        json=_employee_freeze_payload(workflow_id),
    )

    repository = client.app.state.repository
    ticket_projection = repository.get_current_ticket_projection("tkt_frozen_executing")
    node_projection = repository.get_current_node_projection(workflow_id, "node_frozen_executing")
    open_incidents = repository.list_open_incidents()
    dashboard_response = client.get("/api/v1/projections/dashboard")
    inbox_response = client.get("/api/v1/projections/inbox")
    workforce_response = client.get("/api/v1/projections/workforce")
    frontend_lane = next(
        lane
        for lane in workforce_response.json()["data"]["role_lanes"]
        if lane["role_type"] == "frontend_engineer"
    )
    contained_worker = next(
        worker for worker in frontend_lane["workers"] if worker["employee_id"] == "emp_frontend_2"
    )

    assert freeze_response.status_code == 200
    assert freeze_response.json()["status"] == "ACCEPTED"
    assert ticket_projection is not None
    assert ticket_projection["status"] == TICKET_STATUS_CANCEL_REQUESTED
    assert ticket_projection["lease_owner"] == "emp_frontend_2"
    assert node_projection is not None
    assert node_projection["status"] == NODE_STATUS_CANCEL_REQUESTED
    assert len(open_incidents) == 1
    assert open_incidents[0]["incident_type"] == "STAFFING_CONTAINMENT"
    assert open_incidents[0]["ticket_id"] == "tkt_frozen_executing"
    assert open_incidents[0]["payload"]["employee_id"] == "emp_frontend_2"
    assert dashboard_response.status_code == 200
    assert dashboard_response.json()["data"]["ops_strip"]["open_incidents"] == 1
    assert dashboard_response.json()["data"]["ops_strip"]["open_circuit_breakers"] == 1
    assert dashboard_response.json()["data"]["inbox_counts"]["incidents_pending"] == 1
    assert dashboard_response.json()["data"]["pipeline_summary"]["blocked_node_ids"] == [
        "node_ceo_architecture_brief",
        "node_frozen_executing",
    ]
    inbox_items = [
        item for item in inbox_response.json()["data"]["items"] if item["source_ref"] == open_incidents[0]["incident_id"]
    ]
    assert len(inbox_items) == 1
    assert inbox_items[0]["item_type"] == "INCIDENT_ESCALATION"
    assert "staffing containment" in inbox_items[0]["title"].lower()
    assert "staffing_containment" in inbox_items[0]["badges"]
    assert contained_worker["activity_state"] == "FUSED"
    assert contained_worker["current_ticket_id"] == "tkt_frozen_executing"
    assert workforce_response.json()["data"]["summary"]["workers_in_staffing_containment"] == 1


def test_employee_restore_reactivates_frozen_employee_and_workforce_projection(client):
    workflow_response = client.post("/api/v1/commands/project-init", json=_project_init_payload("Restore maker"))
    workflow_id = workflow_response.json()["causation_hint"].split(":", 1)[1]

    freeze_response = client.post(
        "/api/v1/commands/employee-freeze",
        json=_employee_freeze_payload(workflow_id),
    )
    restore_response = client.post(
        "/api/v1/commands/employee-restore",
        json=_employee_restore_payload(workflow_id),
    )

    repository = client.app.state.repository
    restored_employee = repository.get_employee_projection("emp_frontend_2")
    workforce_response = client.get("/api/v1/projections/workforce")
    frontend_lane = next(
        lane
        for lane in workforce_response.json()["data"]["role_lanes"]
        if lane["role_type"] == "frontend_engineer"
    )
    restored_worker = next(
        worker for worker in frontend_lane["workers"] if worker["employee_id"] == "emp_frontend_2"
    )

    assert freeze_response.status_code == 200
    assert freeze_response.json()["status"] == "ACCEPTED"
    assert restore_response.status_code == 200
    assert restore_response.json()["status"] == "ACCEPTED"
    assert restored_employee is not None
    assert restored_employee["state"] == "ACTIVE"
    assert restored_worker["employment_state"] == "ACTIVE"
    assert restored_worker["activity_state"] == "IDLE"


def test_employee_restore_recovers_frozen_requeued_ticket_and_clears_only_temporary_exclusion(
    client,
    set_ticket_time,
):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    workflow_response = client.post(
        "/api/v1/commands/project-init",
        json=_project_init_payload("Restore requeued ticket"),
    )
    workflow_id = workflow_response.json()["causation_hint"].split(":", 1)[1]

    _create_and_lease_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_restore_requeued",
        node_id="node_restore_requeued",
        allowed_write_set=["artifacts/ui/homepage/*"],
    )
    repository = client.app.state.repository
    with repository.transaction() as connection:
        repository.insert_event(
            connection,
            event_type=EVENT_TICKET_CREATED,
            actor_type="system",
            actor_id="test-setup",
            workflow_id=workflow_id,
            idempotency_key="test-setup:restore-requeued:baseline-exclusion",
            causation_id=None,
            correlation_id=workflow_id,
            payload={
                **repository.get_latest_ticket_created_payload(connection, "tkt_restore_requeued"),
                "excluded_employee_ids": ["emp_frontend_backup"],
            },
            occurred_at=datetime.fromisoformat("2026-03-28T10:00:30+08:00"),
        )
        repository.refresh_projections(connection)
    client.post(
        "/api/v1/commands/ticket-lease",
        json=_ticket_lease_payload(
            workflow_id=workflow_id,
            ticket_id="tkt_restore_requeued",
            node_id="node_restore_requeued",
            leased_by="emp_frontend_2",
        ),
    )

    freeze_response = client.post(
        "/api/v1/commands/employee-freeze",
        json=_employee_freeze_payload(workflow_id),
    )
    restore_response = client.post(
        "/api/v1/commands/employee-restore",
        json=_employee_restore_payload(workflow_id),
    )

    ticket_projection = repository.get_current_ticket_projection("tkt_restore_requeued")
    with repository.connection() as connection:
        updated_created_spec = repository.get_latest_ticket_created_payload(
            connection,
            "tkt_restore_requeued",
        )

    assert freeze_response.status_code == 200
    assert restore_response.status_code == 200
    assert restore_response.json()["status"] == "ACCEPTED"
    assert ticket_projection is not None
    assert ticket_projection["status"] == TICKET_STATUS_PENDING
    assert ticket_projection["lease_owner"] is None
    assert updated_created_spec is not None
    assert updated_created_spec["excluded_employee_ids"] == ["emp_frontend_backup"]


def test_employee_restore_rejects_missing_active_and_replaced_employees(client):
    workflow_response = client.post("/api/v1/commands/project-init", json=_project_init_payload("Restore guardrails"))
    workflow_id = workflow_response.json()["causation_hint"].split(":", 1)[1]

    missing_response = client.post(
        "/api/v1/commands/employee-restore",
        json=_employee_restore_payload(workflow_id, employee_id="emp_missing"),
    )
    active_response = client.post(
        "/api/v1/commands/employee-restore",
        json=_employee_restore_payload(workflow_id),
    )

    client.post(
        "/api/v1/commands/employee-replace-request",
        json=_employee_replace_request_payload(
            workflow_id,
            replacement_employee_id="emp_frontend_backup_restore_guard",
        ),
    )
    repository = client.app.state.repository
    approval = repository.list_open_approvals()[0]
    option_id = approval["payload"]["review_pack"]["options"][0]["option_id"]
    approve_response = client.post(
        "/api/v1/commands/board-approve",
        json={
            "review_pack_id": approval["review_pack_id"],
            "review_pack_version": approval["review_pack_version"],
            "command_target_version": approval["command_target_version"],
            "approval_id": approval["approval_id"],
            "selected_option_id": option_id,
            "board_comment": "Approve replacement before restore guard test.",
            "idempotency_key": f"board-approve:{approval['approval_id']}:restore-guard",
        },
    )
    replaced_response = client.post(
        "/api/v1/commands/employee-restore",
        json=_employee_restore_payload(workflow_id, employee_id="emp_frontend_2"),
    )

    assert missing_response.status_code == 200
    assert missing_response.json()["status"] == "REJECTED"
    assert "does not exist" in missing_response.json()["reason"].lower()
    assert active_response.status_code == 200
    assert active_response.json()["status"] == "REJECTED"
    assert "not frozen" in active_response.json()["reason"].lower()
    assert approve_response.status_code == 200
    assert approve_response.json()["status"] == "ACCEPTED"
    assert replaced_response.status_code == 200
    assert replaced_response.json()["status"] == "REJECTED"
    assert "not frozen" in replaced_response.json()["reason"].lower()


def test_employee_restore_reenables_manual_lease_and_worker_runtime_bootstrap(
    client,
    set_ticket_time,
    monkeypatch,
):
    monkeypatch.setenv("BOARDROOM_OS_WORKER_BOOTSTRAP_SIGNING_SECRET", "bootstrap-secret")
    monkeypatch.setenv("BOARDROOM_OS_WORKER_SESSION_TTL_SEC", "600")
    monkeypatch.setenv("BOARDROOM_OS_WORKER_DELIVERY_SIGNING_SECRET", "delivery-secret")
    set_ticket_time("2026-03-28T10:00:00+08:00")
    workflow_response = client.post(
        "/api/v1/commands/project-init",
        json=_project_init_payload("Restore runtime access"),
    )
    workflow_id = workflow_response.json()["causation_hint"].split(":", 1)[1]

    freeze_response = client.post(
        "/api/v1/commands/employee-freeze",
        json=_employee_freeze_payload(workflow_id),
    )
    blocked_runtime_response = client.get(
        "/api/v1/worker-runtime/assignments",
        headers=_worker_bootstrap_headers(),
    )
    restore_response = client.post(
        "/api/v1/commands/employee-restore",
        json=_employee_restore_payload(workflow_id),
    )
    _ensure_runtime_provider_ready_for_ticket(
        client,
        role_profile_ref="frontend_engineer_primary",
        output_schema_ref="ui_milestone_review",
    )
    create_response = client.post(
        "/api/v1/commands/ticket-create",
        json=_ticket_create_payload(
            workflow_id=workflow_id,
            ticket_id="tkt_restored_worker",
            node_id="node_restored_worker",
        ),
    )
    lease_response = client.post(
        "/api/v1/commands/ticket-lease",
        json=_ticket_lease_payload(
            workflow_id=workflow_id,
            ticket_id="tkt_restored_worker",
            node_id="node_restored_worker",
            leased_by="emp_frontend_2",
        ),
    )
    active_runtime_response = client.get(
        "/api/v1/worker-runtime/assignments",
        headers=_worker_bootstrap_headers(issued_at="2026-03-28T10:06:00+08:00"),
    )

    assert freeze_response.status_code == 200
    assert freeze_response.json()["status"] == "ACCEPTED"
    assert blocked_runtime_response.status_code == 403
    assert "not active" in blocked_runtime_response.json()["detail"].lower()
    assert restore_response.status_code == 200
    assert restore_response.json()["status"] == "ACCEPTED"
    assert create_response.status_code == 200
    assert create_response.json()["status"] == "ACCEPTED"
    assert lease_response.status_code == 200
    assert lease_response.json()["status"] == "ACCEPTED"
    assert active_runtime_response.status_code == 200


def test_incident_resolve_can_restore_and_retry_staffing_containment_with_preserved_maker_checker_context(
    client,
    set_ticket_time,
):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    workflow_response = client.post(
        "/api/v1/commands/project-init",
        json=_project_init_payload("Recover staffing-contained meeting fix ticket"),
    )
    workflow_id = workflow_response.json()["causation_hint"].split(":", 1)[1]

    hire_response = client.post(
        "/api/v1/commands/employee-hire-request",
        json=_employee_hire_request_payload(
            workflow_id,
            employee_id="emp_frontend_backup_staffing",
        ),
    )
    assert hire_response.status_code == 200
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
            "board_comment": "Approve backup staffing for staffing recovery.",
            "idempotency_key": f"board-approve:{approval['approval_id']}:staffing-recovery",
        },
    )
    assert approve_response.status_code == 200

    _create_lease_and_start_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_scope_staffing_001",
        node_id="node_scope_staffing",
        output_schema_ref="consensus_document",
        allowed_write_set=["reports/meeting/*"],
        input_artifact_refs=["art://inputs/brief.md", "art://inputs/scope-notes.md"],
        acceptance_criteria=["Must produce a consensus document", "Must include follow-up tickets"],
        allowed_tools=["read_artifact", "write_artifact"],
        context_query_plan={
            "keywords": ["scope", "decision", "meeting"],
            "semantic_queries": ["current scope tradeoffs"],
            "max_context_tokens": 3000,
        },
    )
    client.post(
        "/api/v1/commands/ticket-result-submit",
        json=_consensus_document_result_submit_payload(
            workflow_id=workflow_id,
            ticket_id="tkt_scope_staffing_001",
            node_id="node_scope_staffing",
            include_review_request=True,
            review_request=_meeting_escalation_review_request(),
        ),
    )

    repository = client.app.state.repository
    checker_ticket_id = repository.get_current_node_projection(workflow_id, "node_scope_staffing")[
        "latest_ticket_id"
    ]
    client.post(
        "/api/v1/commands/ticket-lease",
        json=_ticket_lease_payload(
            workflow_id=workflow_id,
            ticket_id=checker_ticket_id,
            node_id="node_scope_staffing",
            leased_by="emp_checker_1",
        ),
    )
    client.post(
        "/api/v1/commands/ticket-start",
        json=_ticket_start_payload(
            workflow_id=workflow_id,
            ticket_id=checker_ticket_id,
            node_id="node_scope_staffing",
            started_by="emp_checker_1",
        ),
    )
    client.post(
        "/api/v1/commands/ticket-result-submit",
        json=_maker_checker_result_submit_payload(
            workflow_id=workflow_id,
            ticket_id=checker_ticket_id,
            node_id="node_scope_staffing",
            review_status="CHANGES_REQUIRED",
            findings=[
                {
                    "finding_id": "finding_scope_unbounded",
                    "severity": "high",
                    "category": "SCOPE_DISCIPLINE",
                    "headline": "Consensus still includes non-MVP scope.",
                    "summary": "Document keeps remote handoff inside the current round.",
                    "required_action": "Remove non-MVP scope before board review.",
                    "blocking": True,
                }
            ],
            idempotency_key=f"ticket-result-submit:{workflow_id}:{checker_ticket_id}:changes-required",
        ),
    )

    fix_ticket_id = repository.get_current_node_projection(workflow_id, "node_scope_staffing")["latest_ticket_id"]
    client.post(
        "/api/v1/commands/ticket-lease",
        json=_ticket_lease_payload(
            workflow_id=workflow_id,
            ticket_id=fix_ticket_id,
            node_id="node_scope_staffing",
            leased_by="emp_frontend_backup_staffing",
        ),
    )
    client.post(
        "/api/v1/commands/ticket-start",
        json=_ticket_start_payload(
            workflow_id=workflow_id,
            ticket_id=fix_ticket_id,
            node_id="node_scope_staffing",
            started_by="emp_frontend_backup_staffing",
        ),
    )

    freeze_response = client.post(
        "/api/v1/commands/employee-freeze",
        json={
            **_employee_freeze_payload(
                workflow_id,
                employee_id="emp_frontend_backup_staffing",
            ),
            "idempotency_key": f"employee-freeze:{workflow_id}:emp_frontend_backup_staffing",
        },
    )
    assert freeze_response.status_code == 200

    incident = repository.list_open_incidents()[0]
    resolve_response = client.post(
        "/api/v1/commands/incident-resolve",
        json=_incident_resolve_payload(
            incident["incident_id"],
            idempotency_key=f"incident-resolve:{incident['incident_id']}:staffing",
            followup_action="RESTORE_AND_RETRY_LATEST_STAFFING_CONTAINMENT",
        ),
    )

    current_node = repository.get_current_node_projection(workflow_id, "node_scope_staffing")
    assert current_node is not None
    followup_ticket = repository.get_current_ticket_projection(current_node["latest_ticket_id"])
    with repository.connection() as connection:
        followup_created_spec = repository.get_latest_ticket_created_payload(
            connection,
            current_node["latest_ticket_id"],
        )
    incident_response = client.get(f"/api/v1/projections/incidents/{incident['incident_id']}")

    assert resolve_response.status_code == 200
    assert resolve_response.json()["status"] == "ACCEPTED"
    assert followup_ticket is not None
    assert followup_ticket["ticket_id"] != fix_ticket_id
    assert followup_ticket["status"] == TICKET_STATUS_PENDING
    assert followup_created_spec is not None
    assert followup_created_spec["output_schema_ref"] == "consensus_document"
    assert followup_created_spec["maker_checker_context"]["checker_ticket_id"] == checker_ticket_id
    assert followup_created_spec["maker_checker_context"]["original_review_request"]["review_type"] == (
        "MEETING_ESCALATION"
    )
    assert followup_created_spec["ticket_kind"] == "MAKER_REWORK_FIX"
    assert incident_response.json()["data"]["incident"]["payload"]["followup_action"] == (
        "RESTORE_AND_RETRY_LATEST_STAFFING_CONTAINMENT"
    )
    assert incident_response.json()["data"]["incident"]["payload"]["followup_ticket_id"] == (
        followup_ticket["ticket_id"]
    )


def test_staffing_containment_recovery_followup_can_reenter_checker_and_board_review(client, set_ticket_time):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    workflow_response = client.post(
        "/api/v1/commands/project-init",
        json=_project_init_payload("Recover staffing-contained meeting fix ticket back into review"),
    )
    workflow_id = workflow_response.json()["causation_hint"].split(":", 1)[1]

    hire_response = client.post(
        "/api/v1/commands/employee-hire-request",
        json=_employee_hire_request_payload(
            workflow_id,
            employee_id="emp_frontend_backup_staffing",
        ),
    )
    assert hire_response.status_code == 200

    repository = client.app.state.repository
    approval = repository.list_open_approvals()[0]
    option_id = approval["payload"]["review_pack"]["options"][0]["option_id"]
    approve_response = client.post(
        "/api/v1/commands/board-approve",
        json={
            "review_pack_id": approval["review_pack_id"],
            "review_pack_version": approval["review_pack_version"],
            "command_target_version": approval["command_target_version"],
            "approval_id": approval["approval_id"],
            "selected_option_id": option_id,
            "board_comment": "Approve backup staffing for staffing recovery.",
            "idempotency_key": f"board-approve:{approval['approval_id']}:staffing-recovery-review",
        },
    )
    assert approve_response.status_code == 200

    _create_lease_and_start_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_scope_staffing_review_001",
        node_id="node_scope_staffing_review",
        output_schema_ref="consensus_document",
        allowed_write_set=["reports/meeting/*"],
        input_artifact_refs=["art://inputs/brief.md", "art://inputs/scope-notes.md"],
        acceptance_criteria=["Must produce a consensus document", "Must include follow-up tickets"],
        allowed_tools=["read_artifact", "write_artifact"],
        context_query_plan={
            "keywords": ["scope", "decision", "meeting"],
            "semantic_queries": ["current scope tradeoffs"],
            "max_context_tokens": 3000,
        },
    )
    client.post(
        "/api/v1/commands/ticket-result-submit",
        json=_consensus_document_result_submit_payload(
            workflow_id=workflow_id,
            ticket_id="tkt_scope_staffing_review_001",
            node_id="node_scope_staffing_review",
            include_review_request=True,
            review_request=_meeting_escalation_review_request(),
        ),
    )

    checker_ticket_id = repository.get_current_node_projection(workflow_id, "node_scope_staffing_review")[
        "latest_ticket_id"
    ]
    client.post(
        "/api/v1/commands/ticket-lease",
        json=_ticket_lease_payload(
            workflow_id=workflow_id,
            ticket_id=checker_ticket_id,
            node_id="node_scope_staffing_review",
            leased_by="emp_checker_1",
        ),
    )
    client.post(
        "/api/v1/commands/ticket-start",
        json=_ticket_start_payload(
            workflow_id=workflow_id,
            ticket_id=checker_ticket_id,
            node_id="node_scope_staffing_review",
            started_by="emp_checker_1",
        ),
    )
    client.post(
        "/api/v1/commands/ticket-result-submit",
        json=_maker_checker_result_submit_payload(
            workflow_id=workflow_id,
            ticket_id=checker_ticket_id,
            node_id="node_scope_staffing_review",
            review_status="CHANGES_REQUIRED",
            findings=[
                {
                    "finding_id": "finding_scope_unbounded",
                    "severity": "high",
                    "category": "SCOPE_DISCIPLINE",
                    "headline": "Consensus still includes non-MVP scope.",
                    "summary": "Document keeps remote handoff inside the current round.",
                    "required_action": "Remove non-MVP scope before board review.",
                    "blocking": True,
                }
            ],
            idempotency_key=f"ticket-result-submit:{workflow_id}:{checker_ticket_id}:changes-required-review",
        ),
    )

    fix_ticket_id = repository.get_current_node_projection(workflow_id, "node_scope_staffing_review")[
        "latest_ticket_id"
    ]
    client.post(
        "/api/v1/commands/ticket-lease",
        json=_ticket_lease_payload(
            workflow_id=workflow_id,
            ticket_id=fix_ticket_id,
            node_id="node_scope_staffing_review",
            leased_by="emp_frontend_backup_staffing",
        ),
    )
    client.post(
        "/api/v1/commands/ticket-start",
        json=_ticket_start_payload(
            workflow_id=workflow_id,
            ticket_id=fix_ticket_id,
            node_id="node_scope_staffing_review",
            started_by="emp_frontend_backup_staffing",
        ),
    )
    freeze_response = client.post(
        "/api/v1/commands/employee-freeze",
        json={
            **_employee_freeze_payload(
                workflow_id,
                employee_id="emp_frontend_backup_staffing",
            ),
            "idempotency_key": f"employee-freeze:{workflow_id}:emp_frontend_backup_staffing:review",
        },
    )
    assert freeze_response.status_code == 200

    incident = repository.list_open_incidents()[0]
    resolve_response = client.post(
        "/api/v1/commands/incident-resolve",
        json=_incident_resolve_payload(
            incident["incident_id"],
            idempotency_key=f"incident-resolve:{incident['incident_id']}:review-recovery",
            followup_action="RESTORE_AND_RETRY_LATEST_STAFFING_CONTAINMENT",
        ),
    )

    assert resolve_response.status_code == 200
    assert resolve_response.json()["status"] == "ACCEPTED"

    followup_ticket_id = repository.get_current_node_projection(workflow_id, "node_scope_staffing_review")[
        "latest_ticket_id"
    ]
    client.post(
        "/api/v1/commands/ticket-lease",
        json=_ticket_lease_payload(
            workflow_id=workflow_id,
            ticket_id=followup_ticket_id,
            node_id="node_scope_staffing_review",
            leased_by="emp_frontend_2",
        ),
    )
    client.post(
        "/api/v1/commands/ticket-start",
        json=_ticket_start_payload(
            workflow_id=workflow_id,
            ticket_id=followup_ticket_id,
            node_id="node_scope_staffing_review",
            started_by="emp_frontend_2",
        ),
    )
    maker_recovery_response = client.post(
        "/api/v1/commands/ticket-result-submit",
        json=_consensus_document_result_submit_payload(
            workflow_id=workflow_id,
            ticket_id=followup_ticket_id,
            node_id="node_scope_staffing_review",
            include_review_request=False,
            idempotency_key=f"ticket-result-submit:{workflow_id}:{followup_ticket_id}:recovered-maker",
        ),
    )

    assert maker_recovery_response.status_code == 200
    assert maker_recovery_response.json()["status"] == "ACCEPTED"

    recovered_checker_ticket_id = repository.get_current_node_projection(workflow_id, "node_scope_staffing_review")[
        "latest_ticket_id"
    ]
    assert recovered_checker_ticket_id != followup_ticket_id
    client.post(
        "/api/v1/commands/ticket-lease",
        json=_ticket_lease_payload(
            workflow_id=workflow_id,
            ticket_id=recovered_checker_ticket_id,
            node_id="node_scope_staffing_review",
            leased_by="emp_checker_1",
        ),
    )
    client.post(
        "/api/v1/commands/ticket-start",
        json=_ticket_start_payload(
            workflow_id=workflow_id,
            ticket_id=recovered_checker_ticket_id,
            node_id="node_scope_staffing_review",
            started_by="emp_checker_1",
        ),
    )
    checker_recovery_response = client.post(
        "/api/v1/commands/ticket-result-submit",
        json=_maker_checker_result_submit_payload(
            workflow_id=workflow_id,
            ticket_id=recovered_checker_ticket_id,
            node_id="node_scope_staffing_review",
            review_status="APPROVED_WITH_NOTES",
            idempotency_key=f"ticket-result-submit:{workflow_id}:{recovered_checker_ticket_id}:recovered-checker",
        ),
    )

    approvals = [
        item for item in repository.list_open_approvals() if item["workflow_id"] == workflow_id
    ]

    assert checker_recovery_response.status_code == 200
    assert checker_recovery_response.json()["status"] == "ACCEPTED"
    assert len(approvals) == 1
    assert approvals[0]["approval_type"] == "MEETING_ESCALATION"
    assert approvals[0]["payload"]["review_pack"]["meta"]["review_type"] == "MEETING_ESCALATION"
    assert approvals[0]["payload"]["review_pack"]["maker_checker_summary"]["review_status"] == (
        "APPROVED_WITH_NOTES"
    )
    assert repository.list_open_incidents() == []


def test_meeting_escalation_followup_tickets_include_decision_record_guidance(client, set_ticket_time):
    set_ticket_time("2026-04-06T10:00:00+08:00")
    workflow_response = client.post(
        "/api/v1/commands/project-init",
        json=_project_init_payload("Carry ADR guidance into meeting follow-up tickets"),
    )
    workflow_id = workflow_response.json()["causation_hint"].split(":", 1)[1]

    _create_lease_and_start_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_scope_adr_001",
        node_id="node_scope_adr",
        output_schema_ref="consensus_document",
        allowed_write_set=["reports/meeting/*"],
        input_artifact_refs=["art://inputs/brief.md", "art://inputs/scope-notes.md"],
        acceptance_criteria=["Must produce a consensus document", "Must include follow-up tickets"],
        allowed_tools=["read_artifact", "write_artifact"],
        context_query_plan={
            "keywords": ["scope", "decision", "meeting"],
            "semantic_queries": ["current scope tradeoffs"],
            "max_context_tokens": 3000,
        },
    )
    client.post(
        "/api/v1/commands/ticket-result-submit",
        json=_consensus_document_result_submit_payload(
            workflow_id=workflow_id,
            ticket_id="tkt_scope_adr_001",
            node_id="node_scope_adr",
            include_review_request=True,
            review_request=_meeting_escalation_review_request(),
            payload=_consensus_document_payload(
                followup_ticket_id="tkt_scope_adr",
                decision_record={
                    "format": "ADR_V1",
                    "context": "Homepage contract alignment is blocking implementation.",
                    "decision": "Use the narrower runtime contract for MVP.",
                    "rationale": [
                        "It keeps board-approved scope stable.",
                        "It avoids reopening remote handoff this round.",
                    ],
                    "consequences": [
                        "Implementation must stay inside the narrowed contract.",
                        "Deferred alternatives require a later governance ticket.",
                    ],
                    "archived_context_refs": ["art://meeting/meeting-digest.json"],
                },
            ),
            artifact_refs=["art://meeting/consensus-document.json"],
            idempotency_key=f"ticket-result-submit:{workflow_id}:tkt_scope_adr_001:consensus",
        ),
    )

    repository = client.app.state.repository
    checker_ticket_id = repository.get_current_node_projection(workflow_id, "node_scope_adr")["latest_ticket_id"]
    client.post(
        "/api/v1/commands/ticket-lease",
        json=_ticket_lease_payload(
            workflow_id=workflow_id,
            ticket_id=checker_ticket_id,
            node_id="node_scope_adr",
            leased_by="emp_checker_1",
        ),
    )
    client.post(
        "/api/v1/commands/ticket-start",
        json=_ticket_start_payload(
            workflow_id=workflow_id,
            ticket_id=checker_ticket_id,
            node_id="node_scope_adr",
            started_by="emp_checker_1",
        ),
    )
    client.post(
        "/api/v1/commands/ticket-result-submit",
        json=_maker_checker_result_submit_payload(
            workflow_id=workflow_id,
            ticket_id=checker_ticket_id,
            node_id="node_scope_adr",
            review_status="APPROVED_WITH_NOTES",
            idempotency_key=f"ticket-result-submit:{workflow_id}:{checker_ticket_id}:approved-with-notes",
        ),
    )

    approval = next(
        item
        for item in repository.list_open_approvals()
        if item["approval_type"] == "MEETING_ESCALATION"
        and any(
            evidence.get("source_ref") == "art://meeting/consensus-document.json"
            for evidence in item["payload"]["review_pack"].get("evidence_summary", [])
        )
    )
    option_id = approval["payload"]["review_pack"]["options"][0]["option_id"]
    approve_response = client.post(
        "/api/v1/commands/board-approve",
        json={
            "review_pack_id": approval["review_pack_id"],
            "review_pack_version": approval["review_pack_version"],
            "command_target_version": approval["command_target_version"],
            "approval_id": approval["approval_id"],
            "selected_option_id": option_id,
            "board_comment": "Lock the meeting ADR and continue.",
            "idempotency_key": f"board-approve:{approval['approval_id']}:meeting-adr-followup",
        },
    )

    assert approve_response.status_code == 200
    followup_node = repository.get_current_node_projection(workflow_id, "node_followup_scope_adr_build")
    assert followup_node is not None
    with repository.connection() as connection:
        created_spec = repository.get_latest_ticket_created_payload(
            connection,
            followup_node["latest_ticket_id"],
        )

    assert created_spec is not None
    assert any(
        artifact_ref.endswith("/consensus-document.json")
        for artifact_ref in created_spec["input_artifact_refs"]
    )
    assert any(
        process_asset_ref.startswith(build_meeting_decision_process_asset_ref("tkt_scope_adr_001"))
        for process_asset_ref in created_spec["input_process_asset_refs"]
    )
    assert any(
        "Use the narrower runtime contract for MVP." in query
        for query in created_spec["context_query_plan"]["semantic_queries"]
    )
    assert any(
        "Implementation must stay inside the narrowed contract." in criterion
        for criterion in created_spec["acceptance_criteria"]
    )


def test_staffing_containment_incident_projection_exposes_retry_followup_actions(client):
    workflow_id = "wf_scope_staffing_actions"
    repository = client.app.state.repository
    workflow_response = client.post(
        "/api/v1/commands/project-init",
        json=_project_init_payload("Expose staffing containment recovery actions"),
    )
    workflow_id = workflow_response.json()["causation_hint"].split(":", 1)[1]
    client.post(
        "/api/v1/commands/employee-hire-request",
        json=_employee_hire_request_payload(
            workflow_id,
            employee_id="emp_frontend_backup_staffing_actions",
        ),
    )
    approval = repository.list_open_approvals()[0]
    option_id = approval["payload"]["review_pack"]["options"][0]["option_id"]
    client.post(
        "/api/v1/commands/board-approve",
        json={
            "review_pack_id": approval["review_pack_id"],
            "review_pack_version": approval["review_pack_version"],
            "command_target_version": approval["command_target_version"],
            "approval_id": approval["approval_id"],
            "selected_option_id": option_id,
            "board_comment": "Approve backup staffing for containment action test.",
            "idempotency_key": f"board-approve:{approval['approval_id']}:staffing-actions",
        },
    )
    _create_lease_and_start_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_scope_staffing_actions_001",
        node_id="node_scope_staffing_actions",
    )
    client.post(
        "/api/v1/commands/employee-freeze",
        json={
            **_employee_freeze_payload(
                workflow_id,
                employee_id="emp_frontend_2",
            ),
            "idempotency_key": f"employee-freeze:{workflow_id}:emp_frontend_2:actions",
        },
    )

    incident_id = repository.list_open_incidents()[0]["incident_id"]
    incident_response = client.get(f"/api/v1/projections/incidents/{incident_id}")

    assert incident_response.status_code == 200
    assert incident_response.json()["data"]["incident"]["incident_type"] == "STAFFING_CONTAINMENT"
    assert incident_response.json()["data"]["available_followup_actions"] == [
        "RESTORE_ONLY",
        "RESTORE_AND_RETRY_LATEST_STAFFING_CONTAINMENT",
    ]
    assert incident_response.json()["data"]["recommended_followup_action"] == (
        "RESTORE_AND_RETRY_LATEST_STAFFING_CONTAINMENT"
    )


def test_board_approve_command_resolves_open_approval(client):
    approval = _seed_review_request(client)

    response = client.post(
        "/api/v1/commands/board-approve",
        json={
            "review_pack_id": approval["review_pack_id"],
            "review_pack_version": approval["review_pack_version"],
            "command_target_version": approval["command_target_version"],
            "approval_id": approval["approval_id"],
            "selected_option_id": "option_a",
            "board_comment": "Proceed with option A.",
            "idempotency_key": f"board-approve:{approval['approval_id']}:1",
        },
    )

    updated = client.app.state.repository.get_approval_by_review_pack_id(approval["review_pack_id"])
    ticket_projection = client.app.state.repository.get_current_ticket_projection("tkt_visual_001")
    node_projection = client.app.state.repository.get_current_node_projection(
        "wf_seed",
        "node_homepage_visual",
    )
    dashboard_response = client.get("/api/v1/projections/dashboard")
    assert response.status_code == 200
    assert response.json()["status"] == "ACCEPTED"
    assert updated["status"] == APPROVAL_STATUS_APPROVED
    assert updated["payload"]["resolution"]["decision_action"] == "APPROVE"
    assert client.app.state.repository.count_events_by_type(EVENT_BOARD_REVIEW_APPROVED) == 1
    assert ticket_projection["status"] == TICKET_STATUS_COMPLETED
    assert ticket_projection["blocking_reason_code"] is None
    assert node_projection["status"] == NODE_STATUS_COMPLETED
    assert node_projection["blocking_reason_code"] is None
    assert dashboard_response.json()["data"]["ops_strip"]["active_tickets"] == 0
    assert dashboard_response.json()["data"]["ops_strip"]["blocked_nodes"] == 0
    assert dashboard_response.json()["data"]["pipeline_summary"]["blocked_node_ids"] == []


def _expected_closeout_ids(repository, approval: dict) -> tuple[str, str, str]:
    source_ticket_id = approval["payload"]["review_pack"]["subject"]["source_ticket_id"]
    with repository.connection() as connection:
        created_spec = repository.get_latest_ticket_created_payload(connection, source_ticket_id)
    logical_review_ticket_id = (
        str(((created_spec or {}).get("maker_checker_context") or {}).get("maker_ticket_id") or source_ticket_id)
    )
    closeout_ticket_id = (
        f"{logical_review_ticket_id.removesuffix('_review')}_closeout"
        if logical_review_ticket_id.endswith("_review")
        else f"{logical_review_ticket_id}_closeout"
    )
    closeout_node_id = f"node_followup_{closeout_ticket_id.removeprefix('tkt_')}"
    return logical_review_ticket_id, closeout_ticket_id, closeout_node_id


def test_final_review_approval_creates_closeout_ticket_and_completion_summary_uses_closeout_fields(client):
    workflow_id, scope_approval = _project_init_to_scope_approval(client)
    workflow_id, approval, _ = _complete_scope_followup_chain_to_visual_milestone(
        client,
        scope_approval,
        idempotency_suffix="completion-scope",
    )
    repository = client.app.state.repository

    with _suppress_ceo_shadow_side_effects():
        response = client.post(
            "/api/v1/commands/board-approve",
            json={
                "review_pack_id": approval["review_pack_id"],
                "review_pack_version": approval["review_pack_version"],
                "command_target_version": approval["command_target_version"],
                "approval_id": approval["approval_id"],
                "selected_option_id": "option_a",
                "board_comment": "Proceed with option A.",
                "idempotency_key": f"board-approve:{approval['approval_id']}:completion-summary",
            },
        )
    dashboard_response = client.get("/api/v1/projections/dashboard")
    review_room_response = client.get(f"/api/v1/projections/review-room/{approval['review_pack_id']}")

    assert response.status_code == 200
    assert response.json()["status"] == "ACCEPTED"
    assert dashboard_response.status_code == 200
    assert review_room_response.status_code == 200

    logical_review_ticket_id, closeout_ticket_id, closeout_node_id = _complete_closeout_chain_after_final_review_approval(
        client,
        approval,
    )
    dashboard_response = client.get("/api/v1/projections/dashboard")
    review_room_response = client.get(f"/api/v1/projections/review-room/{approval['review_pack_id']}")
    closeout_node = repository.get_current_node_projection(workflow_id, closeout_node_id)
    assert closeout_node is not None
    closeout_ticket = repository.get_current_ticket_projection(closeout_ticket_id)
    checker_ticket = repository.get_current_ticket_projection(closeout_node["latest_ticket_id"])
    with repository.connection() as connection:
        closeout_created_spec = repository.get_latest_ticket_created_payload(
            connection,
            closeout_ticket_id,
        )
        checker_created_spec = repository.get_latest_ticket_created_payload(
            connection,
            closeout_node["latest_ticket_id"],
        )

    assert closeout_ticket is not None
    assert checker_ticket is not None
    assert closeout_created_spec is not None
    assert closeout_created_spec["output_schema_ref"] == "delivery_closeout_package"
    assert closeout_created_spec["delivery_stage"] == "CLOSEOUT"
    assert closeout_created_spec["ticket_id"] == closeout_ticket_id
    assert closeout_created_spec["parent_ticket_id"] == logical_review_ticket_id
    assert closeout_created_spec["deliverable_kind"] == "structured_document_delivery"
    assert closeout_created_spec["allowed_write_set"] == [f"20-evidence/closeout/{closeout_ticket_id}/*"]
    assert closeout_created_spec["auto_review_request"]["review_type"] == "INTERNAL_CLOSEOUT_REVIEW"
    assert any(
        "documentation updates" in criterion.lower() for criterion in closeout_created_spec["acceptance_criteria"]
    )
    manifest_path = (
        get_settings().project_workspace_root
        / workflow_id
        / "00-boardroom"
        / "workflow"
        / "workspace-manifest.json"
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert closeout_created_spec["required_read_refs"] == manifest["canonical_doc_refs"]
    assert closeout_created_spec["doc_update_requirements"] == manifest["default_doc_update_requirements"]
    assert closeout_created_spec["input_process_asset_refs"]
    assert "documentation sync" in closeout_created_spec["auto_review_request"]["why_now"].lower()
    assert closeout_ticket["status"] == TICKET_STATUS_COMPLETED
    assert checker_created_spec["output_schema_ref"] == "maker_checker_verdict"
    assert checker_created_spec["maker_checker_context"]["maker_ticket_id"] == closeout_ticket_id
    assert any(
        ref.startswith(build_closeout_summary_process_asset_ref(closeout_ticket_id))
        for ref in checker_created_spec["input_process_asset_refs"]
    )
    completion_summary = dashboard_response.json()["data"]["completion_summary"]
    assert completion_summary is None
    assert review_room_response.json()["data"]["available_actions"] == []


def test_closeout_internal_checker_approved_returns_completion_summary(client):
    workflow_id, scope_approval = _project_init_to_scope_approval(client)
    workflow_id, approval, _ = _complete_scope_followup_chain_to_visual_milestone(
        client,
        scope_approval,
        idempotency_suffix="closeout-pass-scope",
    )
    repository = client.app.state.repository

    with _suppress_ceo_shadow_side_effects():
        client.post(
            "/api/v1/commands/board-approve",
            json={
                "review_pack_id": approval["review_pack_id"],
                "review_pack_version": approval["review_pack_version"],
                "command_target_version": approval["command_target_version"],
                "approval_id": approval["approval_id"],
                "selected_option_id": "option_a",
                "board_comment": "Proceed with option A.",
                "idempotency_key": f"board-approve:{approval['approval_id']}:closeout-pass-final",
            },
        )

    logical_review_ticket_id, expected_closeout_ticket_id, _ = _complete_closeout_chain_after_final_review_approval(
        client,
        approval,
    )
    dashboard_response = client.get("/api/v1/projections/dashboard")
    expected_build_ticket_id = f"{logical_review_ticket_id.removesuffix('_review')}_build"
    completion_summary = dashboard_response.json()["data"]["completion_summary"]
    assert completion_summary is None
    assert repository.get_current_ticket_projection(expected_closeout_ticket_id)["status"] == TICKET_STATUS_COMPLETED
    assert repository.get_current_ticket_projection(expected_build_ticket_id)["status"] in {
        TICKET_STATUS_COMPLETED,
        TICKET_STATUS_FAILED,
    }
    worktree_path = (
        get_settings().project_workspace_root
        / workflow_id
        / "20-evidence"
        / "worktrees"
        / expected_build_ticket_id
    )
    assert not worktree_path.exists()
    stored_artifact = repository.get_artifact_by_ref(
        f"art://runtime/{expected_closeout_ticket_id}/delivery-closeout-package.json"
    )
    assert stored_artifact is not None
    assert stored_artifact["storage_relpath"] is not None
    artifact_path = client.app.state.artifact_store.root / stored_artifact["storage_relpath"]
    closeout_payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert closeout_payload["documentation_updates"] == [
        {
            "doc_ref": "doc/TODO.md",
            "status": "UPDATED",
            "summary": "Marked P2-GOV-007 as completed after closeout evidence sync landed.",
        },
        {
            "doc_ref": "README.md",
            "status": "NO_CHANGE_REQUIRED",
            "summary": "No public capability or runtime flow changed in this round.",
        },
    ]


def test_final_review_approval_rejects_when_review_gate_merge_conflicts(client):
    workflow_id, scope_approval = _project_init_to_scope_approval(client)
    workflow_id, approval, ids = _complete_scope_followup_chain_to_visual_milestone(
        client,
        scope_approval,
        idempotency_suffix="merge-conflict-scope",
    )
    repository = client.app.state.repository
    logical_review_ticket_id, _, _ = _expected_closeout_ids(repository, approval)
    build_ticket_id = ids["build_ticket_id"]
    project_repo_root = get_settings().project_workspace_root / workflow_id / "10-project"
    assert (project_repo_root / ".git").exists()
    assert Path(_git_output(project_repo_root, "rev-parse", "--show-toplevel")) == project_repo_root
    source_path = project_repo_root / "src" / f"{build_ticket_id}.ts"
    source_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_text("// conflicting mainline change\nexport const scopeFollowupBuild = false;\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=project_repo_root, check=True)
    subprocess.run(
        ["git", "commit", "-m", "test: introduce conflicting mainline change"],
        cwd=project_repo_root,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    with _suppress_ceo_shadow_side_effects():
        response = client.post(
            "/api/v1/commands/board-approve",
            json={
                "review_pack_id": approval["review_pack_id"],
                "review_pack_version": approval["review_pack_version"],
                "command_target_version": approval["command_target_version"],
                "approval_id": approval["approval_id"],
                "selected_option_id": "option_a",
                "board_comment": "Proceed with option A.",
                "idempotency_key": f"board-approve:{approval['approval_id']}:merge-conflict-final",
            },
        )

    assert response.status_code == 200
    assert response.json()["status"] == "REJECTED"
    assert "merge" in (response.json()["reason"] or "").lower()
    refreshed_approval = repository.get_approval_by_review_pack_id(approval["review_pack_id"])
    assert refreshed_approval is not None
    assert refreshed_approval["status"] == APPROVAL_STATUS_OPEN
    open_incidents = repository.list_open_incidents()
    assert any(
        incident["workflow_id"] == workflow_id
        and incident["payload"]["incident_type"] == "REVIEW_GATE_MERGE_FAILED"
        and incident["payload"]["ticket_id"] == build_ticket_id
        for incident in open_incidents
    )
    dashboard_response = client.get("/api/v1/projections/dashboard")
    assert dashboard_response.json()["data"]["completion_summary"] is None


def test_completion_summary_handles_missing_closeout_documentation_updates(client):
    workflow_id, scope_approval = _project_init_to_scope_approval(client)
    workflow_id, approval, _ = _complete_scope_followup_chain_to_visual_milestone(
        client,
        scope_approval,
        idempotency_suffix="closeout-no-docs-scope",
    )
    repository = client.app.state.repository
    with _suppress_ceo_shadow_side_effects():
        client.post(
            "/api/v1/commands/board-approve",
            json={
                "review_pack_id": approval["review_pack_id"],
                "review_pack_version": approval["review_pack_version"],
                "command_target_version": approval["command_target_version"],
                "approval_id": approval["approval_id"],
                "selected_option_id": "option_a",
                "board_comment": "Proceed without documentation summary.",
                "idempotency_key": f"board-approve:{approval['approval_id']}:closeout-no-docs-final",
            },
        )

    _, expected_closeout_ticket_id, _ = _complete_closeout_chain_after_final_review_approval(client, approval)
    with repository.connection() as connection:
        closeout_terminal_event = repository.get_latest_ticket_terminal_event(connection, expected_closeout_ticket_id)
        payload = dict(closeout_terminal_event["payload"])
        payload.pop("documentation_updates", None)
        connection.execute(
            "UPDATE events SET payload_json = ? WHERE event_id = ?",
            (json.dumps(payload, sort_keys=True), closeout_terminal_event["event_id"]),
        )
        repository.refresh_projections(connection)

    dashboard_response = client.get("/api/v1/projections/dashboard")

    completion_summary = dashboard_response.json()["data"]["completion_summary"]
    assert completion_summary is None


def test_dashboard_completion_summary_supports_autopilot_closeout_without_visual_milestone(client):
    workflow_id = "wf_autopilot_closeout_dashboard"
    repository = client.app.state.repository
    _ensure_scoped_workflow(
        client,
        workflow_id=workflow_id,
        tenant_id="tenant_default",
        workspace_id="ws_default",
        goal="Autopilot closeout dashboard completion",
    )
    _persist_workflow_profile(repository, workflow_id, "CEO_AUTOPILOT_FINE_GRAINED")

    _create_lease_and_start_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_autopilot_dashboard_build",
        node_id="node_autopilot_dashboard_build",
        role_profile_ref="frontend_engineer_primary",
        output_schema_ref="source_code_delivery",
        delivery_stage="BUILD",
        allowed_write_set=["artifacts/ui/scope-followups/tkt_autopilot_dashboard_build/*"],
        allowed_tools=["read_artifact", "write_artifact"],
        acceptance_criteria=[
            "Must deliver the approved implementation slice.",
            "Must produce a structured source code delivery.",
        ],
    )
    build_response = client.post(
        "/api/v1/commands/ticket-result-submit",
        json=_source_code_delivery_result_submit_payload(
            workflow_id=workflow_id,
            ticket_id="tkt_autopilot_dashboard_build",
            node_id="node_autopilot_dashboard_build",
        ),
    )
    _seed_created_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_autopilot_dashboard_closeout",
        node_id="node_ceo_delivery_closeout",
        role_profile_ref="frontend_engineer_primary",
        output_schema_ref="delivery_closeout_package",
        delivery_stage="CLOSEOUT",
        allowed_write_set=["20-evidence/closeout/tkt_autopilot_dashboard_closeout/*"],
        allowed_tools=["read_artifact", "write_artifact"],
        acceptance_criteria=[
            "Must capture the approved final delivery choice.",
            "Must produce a structured delivery closeout package.",
        ],
        parent_ticket_id="tkt_autopilot_dashboard_build",
        input_artifact_refs=["art://runtime/tkt_autopilot_dashboard_build/source-code.tsx"],
        input_process_asset_refs=[
            build_source_code_delivery_process_asset_ref("tkt_autopilot_dashboard_build"),
        ],
    )
    lease_response = client.post(
        "/api/v1/commands/ticket-lease",
        json=_ticket_lease_payload(
            workflow_id=workflow_id,
            ticket_id="tkt_autopilot_dashboard_closeout",
            node_id="node_ceo_delivery_closeout",
            leased_by="emp_frontend_2",
        ),
    )
    start_response = client.post(
        "/api/v1/commands/ticket-start",
        json=_ticket_start_payload(
            workflow_id=workflow_id,
            ticket_id="tkt_autopilot_dashboard_closeout",
            node_id="node_ceo_delivery_closeout",
            started_by="emp_frontend_2",
        ),
    )
    closeout_response = client.post(
        "/api/v1/commands/ticket-result-submit",
        json=_delivery_closeout_package_result_submit_payload(
            workflow_id=workflow_id,
            ticket_id="tkt_autopilot_dashboard_closeout",
            node_id="node_ceo_delivery_closeout",
            final_artifact_refs=["art://runtime/tkt_autopilot_dashboard_build/source-code.tsx"],
        ),
    )
    auto_advance_workflow_to_next_stop(
        repository,
        workflow_id=workflow_id,
        idempotency_key_prefix="test-autopilot:dashboard-closeout",
        max_steps=1,
        max_dispatches=1,
    )

    dashboard_response = client.get("/api/v1/projections/dashboard")
    workflow_projection = repository.get_workflow_projection(workflow_id)
    completion_summary = dashboard_response.json()["data"]["completion_summary"]
    active_workflow = dashboard_response.json()["data"]["active_workflow"]

    assert build_response.status_code == 200
    assert build_response.json()["status"] == "ACCEPTED"
    assert lease_response.status_code == 200
    assert lease_response.json()["status"] == "ACCEPTED"
    assert start_response.status_code == 200
    assert start_response.json()["status"] == "ACCEPTED"
    assert closeout_response.status_code == 200
    assert closeout_response.json()["status"] == "ACCEPTED"
    assert dashboard_response.status_code == 200
    assert completion_summary is not None
    assert completion_summary["workflow_id"] == workflow_id
    assert completion_summary["final_review_pack_id"] is None
    assert completion_summary["approved_at"] is None
    assert completion_summary["final_review_approved_at"] is None
    assert completion_summary["board_comment"] is None
    assert completion_summary["selected_option_id"] is None
    assert completion_summary["closeout_ticket_id"] == "tkt_autopilot_dashboard_closeout"
    assert completion_summary["closeout_artifact_refs"] == [
        "art://runtime/tkt_autopilot_dashboard_closeout/delivery-closeout-package.json"
    ]
    source_delivery_summary = completion_summary["source_delivery_summary"]
    assert source_delivery_summary is not None
    assert source_delivery_summary["ticket_id"] == "tkt_autopilot_dashboard_build"
    assert source_delivery_summary["summary"] == "Source code delivery prepared for tkt_autopilot_dashboard_build."
    assert source_delivery_summary["source_file_refs"] == ["art://runtime/tkt_autopilot_dashboard_build/source-code.tsx"]
    assert source_delivery_summary["source_file_count"] == 1
    assert source_delivery_summary["verification_evidence_refs"] == []
    assert source_delivery_summary["verification_evidence_count"] == 0
    assert source_delivery_summary["git_commit_sha"] is None
    assert source_delivery_summary["git_branch_ref"] is None
    assert source_delivery_summary["git_merge_status"] is None
    assert completion_summary["workflow_chain_report_artifact_ref"] == (
        f"art://workflow-chain/{workflow_id}/workflow-chain-report.json"
    )
    assert workflow_projection is not None
    assert workflow_projection["status"] == "COMPLETED"
    assert workflow_projection["current_stage"] == "closeout"
    assert active_workflow is not None
    assert active_workflow["status"] == "COMPLETED"
    assert active_workflow["current_stage"] == "closeout"


def test_closeout_internal_checker_allows_documentation_follow_up_as_notes_when_handoff_is_complete(client):
    workflow_id = "wf_closeout_doc_notes"
    closeout_node_id = "node_closeout_doc_notes"
    closeout_ticket_id = "tkt_closeout_doc_notes"
    repository = client.app.state.repository

    _create_lease_and_start_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id=closeout_ticket_id,
        node_id=closeout_node_id,
        role_profile_ref="frontend_engineer_primary",
        output_schema_ref="delivery_closeout_package",
        allowed_write_set=[f"20-evidence/closeout/{closeout_ticket_id}/*"],
        allowed_tools=["read_artifact", "write_artifact"],
        acceptance_criteria=[
            "Must capture the approved final delivery choice.",
            "Must produce a structured delivery closeout package.",
        ],
        input_artifact_refs=["art://runtime/tkt_review_final/option-a.json"],
        delivery_stage="CLOSEOUT",
    )
    maker_response = client.post(
        "/api/v1/commands/ticket-result-submit",
        json=_delivery_closeout_package_result_submit_payload(
            workflow_id=workflow_id,
            ticket_id=closeout_ticket_id,
            node_id=closeout_node_id,
            include_review_request=True,
            documentation_updates=[
                {
                    "doc_ref": "README.md",
                    "status": "FOLLOW_UP_REQUIRED",
                    "summary": "Public wording still needs one final copy pass after closeout.",
                }
            ],
        ),
    )

    checker_ticket_id = repository.get_current_node_projection(workflow_id, closeout_node_id)["latest_ticket_id"]
    client.post(
        "/api/v1/commands/ticket-lease",
        json=_ticket_lease_payload(
            workflow_id=workflow_id,
            ticket_id=checker_ticket_id,
            node_id=closeout_node_id,
            leased_by="emp_checker_1",
        ),
    )
    client.post(
        "/api/v1/commands/ticket-start",
        json=_ticket_start_payload(
            workflow_id=workflow_id,
            ticket_id=checker_ticket_id,
            node_id=closeout_node_id,
            started_by="emp_checker_1",
        ),
    )
    checker_response = client.post(
        "/api/v1/commands/ticket-result-submit",
        json=_maker_checker_result_submit_payload(
            workflow_id=workflow_id,
            ticket_id=checker_ticket_id,
            node_id=closeout_node_id,
            review_status="APPROVED_WITH_NOTES",
            findings=[
                {
                    "finding_id": "finding_doc_follow_up_required",
                    "severity": "medium",
                    "category": "DOCUMENTATION_SYNC",
                    "headline": "One affected document still needs a follow-up pass.",
                    "summary": "README wording is still marked FOLLOW_UP_REQUIRED, but final evidence and handoff notes are complete.",
                    "required_action": "Finish the public wording follow-up outside the current closeout path.",
                    "blocking": False,
                }
            ],
            idempotency_key=f"ticket-result-submit:{workflow_id}:{checker_ticket_id}:doc-follow-up-notes",
        ),
    )

    node_projection = repository.get_current_node_projection(workflow_id, closeout_node_id)
    current_ticket = repository.get_current_ticket_projection(node_projection["latest_ticket_id"])

    assert maker_response.status_code == 200
    assert maker_response.json()["status"] == "ACCEPTED"
    assert checker_response.status_code == 200
    assert checker_response.json()["status"] == "ACCEPTED"
    assert node_projection["status"] == "COMPLETED"
    assert current_ticket is not None
    assert current_ticket["ticket_id"] == checker_ticket_id
    assert current_ticket["status"] == TICKET_STATUS_COMPLETED


def test_completion_summary_returns_null_source_delivery_summary_when_closeout_lacks_source_delivery_asset(client):
    workflow_id, scope_approval = _project_init_to_scope_approval(client)
    workflow_id, approval, _ = _complete_scope_followup_chain_to_visual_milestone(
        client,
        scope_approval,
        idempotency_suffix="closeout-null-source-scope",
    )
    repository = client.app.state.repository
    with _suppress_ceo_shadow_side_effects():
        client.post(
            "/api/v1/commands/board-approve",
            json={
                "review_pack_id": approval["review_pack_id"],
                "review_pack_version": approval["review_pack_version"],
                "command_target_version": approval["command_target_version"],
                "approval_id": approval["approval_id"],
                "selected_option_id": "option_a",
                "board_comment": "Proceed without source delivery summary.",
                "idempotency_key": f"board-approve:{approval['approval_id']}:closeout-null-source-final",
            },
        )

    _, expected_closeout_ticket_id, _ = _complete_closeout_chain_after_final_review_approval(client, approval)
    with repository.connection() as connection:
        closeout_created_event = repository.get_latest_ticket_created_payload(connection, expected_closeout_ticket_id)
        assert closeout_created_event is not None
        closeout_created_event["input_process_asset_refs"] = []
        ticket_created_event = connection.execute(
            """
            SELECT event_id
            FROM events
            WHERE event_type = 'TICKET_CREATED' AND json_extract(payload_json, '$.ticket_id') = ?
            ORDER BY occurred_at DESC, event_id DESC
            LIMIT 1
            """,
            (expected_closeout_ticket_id,),
        ).fetchone()
        assert ticket_created_event is not None
        connection.execute(
            "UPDATE events SET payload_json = ? WHERE event_id = ?",
            (json.dumps(closeout_created_event, sort_keys=True), ticket_created_event["event_id"]),
        )
        repository.refresh_projections(connection)

    dashboard_response = client.get("/api/v1/projections/dashboard")
    completion_summary = dashboard_response.json()["data"]["completion_summary"]
    assert completion_summary is None


def test_closeout_internal_checker_changes_required_creates_fix_ticket_and_blocks_completion(client):
    workflow_id = "wf_closeout_rework"
    closeout_node_id = "node_closeout_rework"
    closeout_ticket_id = "tkt_closeout_rework"
    repository = client.app.state.repository

    _create_lease_and_start_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id=closeout_ticket_id,
        node_id=closeout_node_id,
        role_profile_ref="frontend_engineer_primary",
        output_schema_ref="delivery_closeout_package",
        allowed_write_set=[f"20-evidence/closeout/{closeout_ticket_id}/*"],
        allowed_tools=["read_artifact", "write_artifact"],
        acceptance_criteria=[
            "Must capture the approved final delivery choice.",
            "Must produce a structured delivery closeout package.",
        ],
        input_artifact_refs=[
            "art://runtime/tkt_review_final/option-a.json",
            "art://runtime/tkt_review_final/option-b.json",
        ],
        delivery_stage="CLOSEOUT",
    )
    maker_response = client.post(
        "/api/v1/commands/ticket-result-submit",
        json=_delivery_closeout_package_result_submit_payload(
            workflow_id=workflow_id,
            ticket_id=closeout_ticket_id,
            node_id=closeout_node_id,
            include_review_request=True,
            documentation_updates=[
                {
                    "doc_ref": "README.md",
                    "status": "FOLLOW_UP_REQUIRED",
                    "summary": "Public wording still needs one final copy pass after closeout.",
                }
            ],
        ),
    )

    checker_ticket_id = repository.get_current_node_projection(workflow_id, closeout_node_id)["latest_ticket_id"]
    client.post(
        "/api/v1/commands/ticket-lease",
        json=_ticket_lease_payload(
            workflow_id=workflow_id,
            ticket_id=checker_ticket_id,
            node_id=closeout_node_id,
            leased_by="emp_checker_1",
        ),
    )
    client.post(
        "/api/v1/commands/ticket-start",
        json=_ticket_start_payload(
            workflow_id=workflow_id,
            ticket_id=checker_ticket_id,
            node_id=closeout_node_id,
            started_by="emp_checker_1",
        ),
    )
    checker_response = client.post(
        "/api/v1/commands/ticket-result-submit",
        json=_maker_checker_result_submit_payload(
            workflow_id=workflow_id,
            ticket_id=checker_ticket_id,
            node_id=closeout_node_id,
            review_status="CHANGES_REQUIRED",
            findings=[
                {
                    "finding_id": "finding_closeout_missing_handoff",
                    "severity": "high",
                    "category": "DOCUMENTATION_SYNC",
                    "headline": "Closeout package still has blocking documentation follow-up and weak handoff notes.",
                    "summary": "Final delivery package leaves README marked FOLLOW_UP_REQUIRED and does not explain how the approved board choice should be handed off.",
                    "required_action": "Rewrite the closeout package with explicit handoff notes, final evidence links, and updated documentation sync status.",
                    "blocking": True,
                }
            ],
            idempotency_key=f"ticket-result-submit:{workflow_id}:{checker_ticket_id}:closeout-changes-required",
        ),
    )
    dashboard_response = client.get("/api/v1/projections/dashboard")

    node_projection = repository.get_current_node_projection(workflow_id, closeout_node_id)
    fix_ticket = repository.get_current_ticket_projection(node_projection["latest_ticket_id"])
    with repository.connection() as connection:
        fix_created_spec = repository.get_latest_ticket_created_payload(
            connection,
            node_projection["latest_ticket_id"],
        )

    assert maker_response.status_code == 200
    assert maker_response.json()["status"] == "ACCEPTED"
    assert checker_response.status_code == 200
    assert fix_ticket is not None
    assert fix_created_spec["output_schema_ref"] == "delivery_closeout_package"
    assert fix_created_spec["delivery_stage"] == "CLOSEOUT"
    assert fix_created_spec["excluded_employee_ids"] == ["emp_frontend_2"]
    assert fix_created_spec["maker_checker_context"]["original_review_request"]["review_type"] == (
        "INTERNAL_CLOSEOUT_REVIEW"
    )
    assert dashboard_response.json()["data"]["completion_summary"] is None


def test_board_approve_scope_review_accepts_backend_build_followup_owner_role(client, set_ticket_time):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    _, approval = _project_init_to_scope_approval(client)
    followup_ticket_id = _scope_followup_payload(client, approval)["followup_tickets"][0]["ticket_id"]

    consensus_artifact_ref = approval["payload"]["review_pack"]["evidence_summary"][0]["source_ref"]
    artifact_path = _artifact_storage_path(client, consensus_artifact_ref)
    payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    payload["followup_tickets"][0]["owner_role"] = "backend_engineer"
    payload["followup_tickets"][0]["delivery_stage"] = "BUILD"
    artifact_path.write_text(json.dumps(payload), encoding="utf-8")

    response = _approve_open_review(client, approval, idempotency_suffix="unsupported-role")

    updated = client.app.state.repository.get_approval_by_review_pack_id(approval["review_pack_id"])
    followup_ticket = client.app.state.repository.get_current_ticket_projection(followup_ticket_id)
    with client.app.state.repository.connection() as connection:
        created_spec = client.app.state.repository.get_latest_ticket_created_payload(connection, followup_ticket_id)

    assert response.status_code == 200
    assert response.json()["status"] == "ACCEPTED"
    assert updated["status"] == APPROVAL_STATUS_APPROVED
    assert followup_ticket is not None
    assert created_spec["role_profile_ref"] == "backend_engineer_primary"
    assert created_spec["delivery_stage"] == "BUILD"


def test_board_approve_scope_review_rejects_backend_followup_outside_build_stage(client, set_ticket_time):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    _, approval = _project_init_to_scope_approval(client)
    followup_ticket_id = _scope_followup_payload(client, approval)["followup_tickets"][0]["ticket_id"]

    consensus_artifact_ref = approval["payload"]["review_pack"]["evidence_summary"][0]["source_ref"]
    artifact_path = _artifact_storage_path(client, consensus_artifact_ref)
    payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    payload["followup_tickets"][0]["owner_role"] = "backend_engineer"
    payload["followup_tickets"][0]["delivery_stage"] = "REVIEW"
    artifact_path.write_text(json.dumps(payload), encoding="utf-8")

    response = _approve_open_review(client, approval, idempotency_suffix="backend-review-stage")

    updated = client.app.state.repository.get_approval_by_review_pack_id(approval["review_pack_id"])
    followup_ticket = client.app.state.repository.get_current_ticket_projection(followup_ticket_id)

    assert response.status_code == 200
    assert response.json()["status"] == "REJECTED"
    assert "owner_role" in response.json()["reason"]
    assert updated["status"] == APPROVAL_STATUS_OPEN
    assert followup_ticket is None


def test_board_approve_scope_review_rejects_when_consensus_artifact_is_missing(client, set_ticket_time):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    _, approval = _project_init_to_scope_approval(client)

    consensus_artifact_ref = approval["payload"]["review_pack"]["evidence_summary"][0]["source_ref"]
    artifact_path = _artifact_storage_path(client, consensus_artifact_ref)
    artifact_path.unlink()

    response = _approve_open_review(client, approval, idempotency_suffix="missing-artifact")

    updated = client.app.state.repository.get_approval_by_review_pack_id(approval["review_pack_id"])

    assert response.status_code == 200
    assert response.json()["status"] == "REJECTED"
    assert "consensus" in response.json()["reason"].lower()
    assert updated["status"] == APPROVAL_STATUS_OPEN


def test_board_approve_scope_review_rejects_when_consensus_artifact_is_not_json(client, set_ticket_time):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    _, approval = _project_init_to_scope_approval(client)

    consensus_artifact_ref = approval["payload"]["review_pack"]["evidence_summary"][0]["source_ref"]
    artifact_path = _artifact_storage_path(client, consensus_artifact_ref)
    artifact_path.write_text("{not-valid-json", encoding="utf-8")

    response = _approve_open_review(client, approval, idempotency_suffix="invalid-artifact")

    updated = client.app.state.repository.get_approval_by_review_pack_id(approval["review_pack_id"])

    assert response.status_code == 200
    assert response.json()["status"] == "REJECTED"
    assert "json" in response.json()["reason"].lower()
    assert updated["status"] == APPROVAL_STATUS_OPEN


def test_board_approve_scope_review_rejects_when_followup_ticket_id_already_exists(client, set_ticket_time):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    workflow_id, approval = _project_init_to_scope_approval(client)

    consensus_artifact_ref = approval["payload"]["review_pack"]["evidence_summary"][0]["source_ref"]
    artifact_path = _artifact_storage_path(client, consensus_artifact_ref)
    payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    payload["followup_tickets"][0]["ticket_id"] = approval["payload"]["review_pack"]["subject"]["source_ticket_id"]
    artifact_path.write_text(json.dumps(payload), encoding="utf-8")

    response = _approve_open_review(client, approval, idempotency_suffix="duplicate-followup")

    updated = client.app.state.repository.get_approval_by_review_pack_id(approval["review_pack_id"])
    existing_ticket = client.app.state.repository.get_current_ticket_projection(
        approval["payload"]["review_pack"]["subject"]["source_ticket_id"]
    )
    scope_node = client.app.state.repository.get_current_node_projection(workflow_id, "node_scope_decision")

    assert response.status_code == 200
    assert response.json()["status"] == "REJECTED"
    assert "already exists" in response.json()["reason"]
    assert updated["status"] == APPROVAL_STATUS_OPEN
    assert existing_ticket is not None
    assert scope_node is not None
    assert scope_node["status"] == NODE_STATUS_BLOCKED_FOR_BOARD_REVIEW


def test_board_reject_command_resolves_open_approval(client):
    approval = _seed_review_request(client, workflow_id="wf_reject")

    response = client.post(
        "/api/v1/commands/board-reject",
        json={
            "review_pack_id": approval["review_pack_id"],
            "review_pack_version": approval["review_pack_version"],
            "command_target_version": approval["command_target_version"],
            "approval_id": approval["approval_id"],
            "board_comment": "Current direction is too weak.",
            "rejection_reasons": ["visual_impact_insufficient"],
            "idempotency_key": f"board-reject:{approval['approval_id']}:1",
        },
    )

    updated = client.app.state.repository.get_approval_by_review_pack_id(approval["review_pack_id"])
    review_ticket_id = approval["payload"]["review_pack"]["subject"]["source_ticket_id"]
    ticket_projection = client.app.state.repository.get_current_ticket_projection(review_ticket_id)
    node_projection = client.app.state.repository.get_current_node_projection(
        "wf_reject",
        "node_homepage_visual",
    )
    dashboard_response = client.get("/api/v1/projections/dashboard")
    assert response.status_code == 200
    assert response.json()["status"] == "ACCEPTED"
    assert updated["status"] == APPROVAL_STATUS_REJECTED
    assert updated["payload"]["resolution"]["decision_action"] == "REJECT"
    assert client.app.state.repository.count_events_by_type(EVENT_BOARD_REVIEW_REJECTED) == 1
    assert ticket_projection["status"] == TICKET_STATUS_REWORK_REQUIRED
    assert ticket_projection["blocking_reason_code"] == BLOCKING_REASON_BOARD_REJECTED
    assert node_projection["status"] == NODE_STATUS_REWORK_REQUIRED
    assert node_projection["blocking_reason_code"] == BLOCKING_REASON_BOARD_REJECTED
    assert dashboard_response.json()["data"]["ops_strip"]["active_tickets"] == 1
    assert dashboard_response.json()["data"]["ops_strip"]["blocked_nodes"] == 0
    assert dashboard_response.json()["data"]["pipeline_summary"]["blocked_node_ids"] == []


def test_modify_constraints_enters_board_advisory_change_flow_without_resolving_open_approval(client):
    workflow_id = "wf_modify"
    _ensure_scoped_workflow(
        client,
        workflow_id=workflow_id,
        tenant_id="tenant_default",
        workspace_id="ws_default",
        goal="Enter advisory change flow without resolving the board review.",
    )
    approval = _seed_review_request(client, workflow_id=workflow_id)
    repository = client.app.state.repository
    graph_version_before = build_ticket_graph_snapshot(repository, workflow_id).graph_version

    with _suppress_ceo_shadow_side_effects():
        response = client.post(
            "/api/v1/commands/modify-constraints",
            json={
                "review_pack_id": approval["review_pack_id"],
                "review_pack_version": approval["review_pack_version"],
                "command_target_version": approval["command_target_version"],
                "approval_id": approval["approval_id"],
                "constraint_patch": {
                    "add_rules": ["Strengthen first-screen contrast and hierarchy"],
                    "remove_rules": [],
                    "replace_rules": [],
                },
                "board_comment": "Rework with stronger hierarchy.",
                "idempotency_key": f"board-modify:{approval['approval_id']}:enter-flow",
            },
        )

    updated = repository.get_approval_by_review_pack_id(approval["review_pack_id"])
    advisory_session = repository.get_board_advisory_session_for_approval(approval["approval_id"])
    review_room = client.get(f"/api/v1/projections/review-room/{approval['review_pack_id']}")
    graph_version_after = build_ticket_graph_snapshot(repository, workflow_id).graph_version

    assert response.status_code == 200
    assert response.json()["status"] == "ACCEPTED"
    assert updated["status"] == APPROVAL_STATUS_OPEN
    assert updated["payload"].get("resolution") in (None, {})
    assert advisory_session is not None
    assert advisory_session["status"] == "DRAFTING"
    assert advisory_session["approved_patch_ref"] is None
    assert advisory_session["decision_pack_refs"] == [
        f"pa://decision-summary/{advisory_session['session_id']}@1"
    ]
    assert graph_version_after == graph_version_before
    assert review_room.status_code == 200
    advisory_context = review_room.json()["data"]["review_pack"]["advisory_context"]
    assert advisory_context["status"] == "DRAFTING"
    assert advisory_context["change_flow_status"] == "DRAFTING"
    assert advisory_context["working_turns"][0]["actor_type"] == "board"
    assert advisory_context["working_turns"][0]["content"] == "Rework with stronger hierarchy."


def test_board_advisory_append_turn_persists_working_context_without_changing_graph(client):
    workflow_id = "wf_advisory_append_turn"
    _ensure_scoped_workflow(
        client,
        workflow_id=workflow_id,
        tenant_id="tenant_default",
        workspace_id="ws_default",
        goal="Persist advisory working turns without mutating the graph.",
    )
    approval = _seed_review_request(client, workflow_id=workflow_id)
    repository = client.app.state.repository

    with _suppress_ceo_shadow_side_effects():
        enter_response = client.post(
            "/api/v1/commands/modify-constraints",
            json={
                "review_pack_id": approval["review_pack_id"],
                "review_pack_version": approval["review_pack_version"],
                "command_target_version": approval["command_target_version"],
                "approval_id": approval["approval_id"],
                "constraint_patch": {
                    "add_rules": ["Keep the board in the loop before runtime import."],
                    "remove_rules": [],
                    "replace_rules": [],
                },
                "board_comment": "We need a structured change flow first.",
                "idempotency_key": f"board-modify:{approval['approval_id']}:draft-enter",
            },
        )
    assert enter_response.status_code == 200
    assert enter_response.json()["status"] == "ACCEPTED"

    advisory_session = repository.get_board_advisory_session_for_approval(approval["approval_id"])
    assert advisory_session is not None
    graph_version_before = build_ticket_graph_snapshot(repository, workflow_id).graph_version

    append_response = client.post(
        "/api/v1/commands/board-advisory-append-turn",
        json={
            "session_id": advisory_session["session_id"],
            "actor_type": "board",
            "content": "Please compare the pros and cons before you suggest any patch.",
            "idempotency_key": f"board-advisory-turn:{advisory_session['session_id']}:1",
        },
    )

    review_room = client.get(f"/api/v1/projections/review-room/{approval['review_pack_id']}")
    graph_version_after = build_ticket_graph_snapshot(repository, workflow_id).graph_version

    assert append_response.status_code == 200
    assert append_response.json()["status"] == "ACCEPTED"
    assert graph_version_after == graph_version_before
    advisory_context = review_room.json()["data"]["review_pack"]["advisory_context"]
    assert advisory_context["status"] == "DRAFTING"
    assert [item["content"] for item in advisory_context["working_turns"]] == [
        "We need a structured change flow first.",
        "Please compare the pros and cons before you suggest any patch.",
    ]


def test_board_advisory_request_analysis_records_pending_run_before_execution(client):
    workflow_id = "wf_modify_advisory_pending"
    _ensure_scoped_workflow(
        client,
        workflow_id=workflow_id,
        tenant_id="tenant_default",
        workspace_id="ws_default",
        goal="Queue advisory analysis before the dedicated run executes.",
    )
    approval = _seed_review_request(client, workflow_id=workflow_id)
    repository = client.app.state.repository

    with _suppress_ceo_shadow_side_effects():
        enter_response = client.post(
            "/api/v1/commands/modify-constraints",
            json={
                "review_pack_id": approval["review_pack_id"],
                "review_pack_version": approval["review_pack_version"],
                "command_target_version": approval["command_target_version"],
                "approval_id": approval["approval_id"],
                "constraint_patch": {
                    "add_rules": ["Queue the advisory analysis run before any patch proposal is imported."],
                    "remove_rules": [],
                    "replace_rules": [],
                },
                "board_comment": "Create the analysis run first, then execute it outside the request transaction.",
                "idempotency_key": f"board-modify:{approval['approval_id']}:pending-enter",
            },
        )
    assert enter_response.status_code == 200
    assert enter_response.json()["status"] == "ACCEPTED"

    advisory_session = repository.get_board_advisory_session_for_approval(approval["approval_id"])
    assert advisory_session is not None

    with patch("app.core.approval_handlers.run_board_advisory_analysis", return_value=None, create=True):
        response = client.post(
            "/api/v1/commands/board-advisory-request-analysis",
            json={
                "session_id": advisory_session["session_id"],
                "idempotency_key": f"board-advisory-analysis:{advisory_session['session_id']}:pending",
            },
        )

    advisory_session = repository.get_board_advisory_session_for_approval(approval["approval_id"])
    updated = repository.get_approval_by_review_pack_id(approval["review_pack_id"])
    review_room = client.get(f"/api/v1/projections/review-room/{approval['review_pack_id']}")

    assert response.status_code == 200
    assert response.json()["status"] == "ACCEPTED"
    assert advisory_session is not None
    assert advisory_session["status"] == "PENDING_ANALYSIS"
    assert advisory_session["latest_patch_proposal_ref"] is None
    assert advisory_session["approved_patch_ref"] is None
    assert advisory_session["latest_analysis_run_id"]
    assert advisory_session["latest_analysis_status"] == "PENDING"
    assert advisory_session["latest_analysis_incident_id"] is None
    assert advisory_session["latest_analysis_error"] is None
    assert updated is not None
    assert updated["status"] == APPROVAL_STATUS_OPEN
    assert repository.count_events_by_type("BOARD_ADVISORY_ANALYSIS_REQUESTED") == 1
    advisory_context = review_room.json()["data"]["review_pack"]["advisory_context"]
    assert advisory_context["change_flow_status"] == "PENDING_ANALYSIS"
    assert advisory_context["latest_analysis_run_id"] == advisory_session["latest_analysis_run_id"]
    assert advisory_context["latest_analysis_status"] == "PENDING"


def test_board_advisory_analysis_run_uses_live_mode_when_real_architect_and_target_binding_exist(client):
    workflow_id = "wf_advisory_analysis_live_target_binding"
    _ensure_scoped_workflow(
        client,
        workflow_id=workflow_id,
        tenant_id="tenant_default",
        workspace_id="ws_default",
        goal="Advisory analysis should enter live mode when a real architect exists and the architect target binding resolves.",
    )
    approval = _seed_review_request(client, workflow_id=workflow_id)
    repository = client.app.state.repository
    _seed_worker(
        client,
        employee_id="emp_architect_live_target_binding",
        role_type="governance_architect",
        provider_id="",
        role_profile_refs=["architect_primary"],
    )
    _assert_command_accepted(
        client.post(
            "/api/v1/commands/runtime-provider-upsert",
            json=_runtime_provider_upsert_payload(
                role_bindings=[
                    {
                        "target_ref": "ceo_shadow",
                        "provider_model_entry_refs": ["prov_openai_compat::gpt-5.3-codex"],
                        "max_context_window_override": None,
                        "reasoning_effort_override": None,
                    },
                    {
                        "target_ref": EXECUTION_TARGET_ARCHITECT_GOVERNANCE_DOCUMENT,
                        "provider_model_entry_refs": ["prov_openai_compat::gpt-5.3-codex"],
                        "max_context_window_override": None,
                        "reasoning_effort_override": None,
                    },
                ],
                idempotency_key=f"runtime-provider-upsert:{workflow_id}:architect-target-binding",
            ),
        )
    )

    with _suppress_ceo_shadow_side_effects():
        enter_response = client.post(
            "/api/v1/commands/modify-constraints",
            json={
                "review_pack_id": approval["review_pack_id"],
                "review_pack_version": approval["review_pack_version"],
                "command_target_version": approval["command_target_version"],
                "approval_id": approval["approval_id"],
                "constraint_patch": {
                    "add_rules": ["Let the architect role binding drive advisory live analysis."],
                    "remove_rules": [],
                    "replace_rules": [],
                },
                "board_comment": "Use the architect target binding instead of an employee-level provider field.",
                "idempotency_key": f"board-modify:{approval['approval_id']}:architect-target-binding",
            },
        )
    _assert_command_accepted(enter_response)

    advisory_session = repository.get_board_advisory_session_for_approval(approval["approval_id"])
    assert advisory_session is not None

    with patch("app.core.approval_handlers.run_board_advisory_analysis", return_value=None, create=True):
        response = client.post(
            "/api/v1/commands/board-advisory-request-analysis",
            json={
                "session_id": advisory_session["session_id"],
                "idempotency_key": f"board-advisory-analysis:{advisory_session['session_id']}:live-target-binding",
            },
        )

    updated_session = repository.get_board_advisory_session_for_approval(approval["approval_id"])
    assert response.status_code == 200
    assert response.json()["status"] == "ACCEPTED"
    assert updated_session is not None
    run = repository.get_board_advisory_analysis_run(str(updated_session["latest_analysis_run_id"]))
    assert run is not None
    assert run["executor_mode"] == "LIVE_PROVIDER"


def test_board_advisory_analysis_run_uses_live_mode_when_real_contract_matching_executor_and_advisory_target_binding_exist(
    client,
):
    workflow_id = "wf_advisory_analysis_live_contract_executor"
    _ensure_scoped_workflow(
        client,
        workflow_id=workflow_id,
        tenant_id="tenant_default",
        workspace_id="ws_default",
        goal="Advisory analysis should enter live mode when a real board-approved executor satisfies the advisory contract.",
    )
    approval = _seed_review_request(client, workflow_id=workflow_id)
    repository = client.app.state.repository
    _seed_worker(
        client,
        employee_id="emp_cto_live_advisory_contract",
        role_type="cto",
        provider_id="",
        role_profile_refs=["cto_primary"],
    )
    _assert_command_accepted(
        client.post(
            "/api/v1/commands/runtime-provider-upsert",
            json=_runtime_provider_upsert_payload(
                role_bindings=[
                    {
                        "target_ref": "ceo_shadow",
                        "provider_model_entry_refs": ["prov_openai_compat::gpt-5.3-codex"],
                        "max_context_window_override": None,
                        "reasoning_effort_override": None,
                    },
                    {
                        "target_ref": "execution_target:board_advisory_analysis",
                        "provider_model_entry_refs": ["prov_openai_compat::gpt-5.3-codex"],
                        "max_context_window_override": None,
                        "reasoning_effort_override": None,
                    },
                ],
                idempotency_key=f"runtime-provider-upsert:{workflow_id}:advisory-target-binding",
            ),
        )
    )

    with _suppress_ceo_shadow_side_effects():
        enter_response = client.post(
            "/api/v1/commands/modify-constraints",
            json={
                "review_pack_id": approval["review_pack_id"],
                "review_pack_version": approval["review_pack_version"],
                "command_target_version": approval["command_target_version"],
                "approval_id": approval["approval_id"],
                "constraint_patch": {
                    "add_rules": ["Let the advisory contract choose the live executor instead of the architect role preset."],
                    "remove_rules": [],
                    "replace_rules": [],
                },
                "board_comment": "A contract-matching board-approved executor should be enough for advisory live analysis.",
                "idempotency_key": f"board-modify:{approval['approval_id']}:advisory-contract-executor",
            },
        )
    _assert_command_accepted(enter_response)

    advisory_session = repository.get_board_advisory_session_for_approval(approval["approval_id"])
    assert advisory_session is not None

    with patch("app.core.approval_handlers.run_board_advisory_analysis", return_value=None, create=True):
        response = client.post(
            "/api/v1/commands/board-advisory-request-analysis",
            json={
                "session_id": advisory_session["session_id"],
                "idempotency_key": f"board-advisory-analysis:{advisory_session['session_id']}:live-contract-executor",
            },
        )

    updated_session = repository.get_board_advisory_session_for_approval(approval["approval_id"])
    assert response.status_code == 200
    assert response.json()["status"] == "ACCEPTED"
    assert updated_session is not None
    run = repository.get_board_advisory_analysis_run(str(updated_session["latest_analysis_run_id"]))
    assert run is not None
    assert run["executor_mode"] == "LIVE_PROVIDER"


def test_board_advisory_analysis_run_uses_live_mode_when_real_architect_and_default_provider_exist(client):
    workflow_id = "wf_advisory_analysis_live_default_provider"
    _ensure_scoped_workflow(
        client,
        workflow_id=workflow_id,
        tenant_id="tenant_default",
        workspace_id="ws_default",
        goal="Advisory analysis should enter live mode when a real architect exists and only the default provider is configured.",
    )
    approval = _seed_review_request(client, workflow_id=workflow_id)
    repository = client.app.state.repository
    _seed_worker(
        client,
        employee_id="emp_architect_live_default_provider",
        role_type="governance_architect",
        provider_id="",
        role_profile_refs=["architect_primary"],
    )
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
                )
            ],
            role_bindings=[],
        )
    )

    with _suppress_ceo_shadow_side_effects():
        enter_response = client.post(
            "/api/v1/commands/modify-constraints",
            json={
                "review_pack_id": approval["review_pack_id"],
                "review_pack_version": approval["review_pack_version"],
                "command_target_version": approval["command_target_version"],
                "approval_id": approval["approval_id"],
                "constraint_patch": {
                    "add_rules": ["Let the default runtime provider back the architect advisory analysis."],
                    "remove_rules": [],
                    "replace_rules": [],
                },
                "board_comment": "A real architect exists, so the default provider should be enough for live analysis.",
                "idempotency_key": f"board-modify:{approval['approval_id']}:default-provider",
            },
        )
    _assert_command_accepted(enter_response)

    advisory_session = repository.get_board_advisory_session_for_approval(approval["approval_id"])
    assert advisory_session is not None

    with patch("app.core.approval_handlers.run_board_advisory_analysis", return_value=None, create=True):
        response = client.post(
            "/api/v1/commands/board-advisory-request-analysis",
            json={
                "session_id": advisory_session["session_id"],
                "idempotency_key": f"board-advisory-analysis:{advisory_session['session_id']}:live-default-provider",
            },
        )

    updated_session = repository.get_board_advisory_session_for_approval(approval["approval_id"])
    assert response.status_code == 200
    assert response.json()["status"] == "ACCEPTED"
    assert updated_session is not None
    run = repository.get_board_advisory_analysis_run(str(updated_session["latest_analysis_run_id"]))
    assert run is not None
    assert run["executor_mode"] == "LIVE_PROVIDER"


def test_board_advisory_analysis_run_rejects_legacy_architect_target_binding_without_advisory_target(
    client,
):
    workflow_id = "wf_advisory_analysis_legacy_architect_binding_only"
    _ensure_scoped_workflow(
        client,
        workflow_id=workflow_id,
        tenant_id="tenant_default",
        workspace_id="ws_default",
        goal="Advisory analysis should not treat the old architect target binding as the advisory live target.",
    )
    approval = _seed_review_request(client, workflow_id=workflow_id)
    repository = client.app.state.repository
    _seed_worker(
        client,
        employee_id="emp_cto_legacy_binding_only",
        role_type="cto",
        provider_id="",
        role_profile_refs=["cto_primary"],
    )
    _assert_command_accepted(
        client.post(
            "/api/v1/commands/runtime-provider-upsert",
            json=_runtime_provider_upsert_payload(
                role_bindings=[
                    {
                        "target_ref": EXECUTION_TARGET_ARCHITECT_GOVERNANCE_DOCUMENT,
                        "provider_model_entry_refs": ["prov_openai_compat::gpt-5.3-codex"],
                        "max_context_window_override": None,
                        "reasoning_effort_override": None,
                    }
                ],
                idempotency_key=f"runtime-provider-upsert:{workflow_id}:legacy-architect-binding-only",
            ),
        )
    )

    with _suppress_ceo_shadow_side_effects():
        enter_response = client.post(
            "/api/v1/commands/modify-constraints",
            json={
                "review_pack_id": approval["review_pack_id"],
                "review_pack_version": approval["review_pack_version"],
                "command_target_version": approval["command_target_version"],
                "approval_id": approval["approval_id"],
                "constraint_patch": {
                    "add_rules": ["Do not let the legacy architect target masquerade as the advisory target."],
                    "remove_rules": [],
                    "replace_rules": [],
                },
                "board_comment": "The advisory target should be explicit.",
                "idempotency_key": f"board-modify:{approval['approval_id']}:legacy-architect-binding-only",
            },
        )
    _assert_command_accepted(enter_response)

    advisory_session = repository.get_board_advisory_session_for_approval(approval["approval_id"])
    assert advisory_session is not None

    response = client.post(
        "/api/v1/commands/board-advisory-request-analysis",
        json={
            "session_id": advisory_session["session_id"],
            "idempotency_key": f"board-advisory-analysis:{advisory_session['session_id']}:legacy-architect-binding-only",
        },
    )

    updated_session = repository.get_board_advisory_session_for_approval(approval["approval_id"])
    open_incidents = [
        item
        for item in repository.list_open_incidents()
        if item["workflow_id"] == workflow_id and item["incident_type"] == "BOARD_ADVISORY_ANALYSIS_FAILED"
    ]
    assert response.status_code == 200
    assert response.json()["status"] == "ACCEPTED"
    assert updated_session is not None
    run = repository.get_board_advisory_analysis_run(str(updated_session["latest_analysis_run_id"]))
    assert run is not None
    assert updated_session["status"] == "ANALYSIS_REJECTED"
    assert updated_session["latest_analysis_status"] == "FAILED"
    assert updated_session["latest_patch_proposal_ref"] is None
    assert len(open_incidents) == 1


def test_board_advisory_analysis_run_fails_without_real_contract_matching_executor_even_if_provider_binding_exists(
    client,
    monkeypatch,
):
    workflow_id = "wf_advisory_analysis_fails_without_real_executor"
    _ensure_scoped_workflow(
        client,
        workflow_id=workflow_id,
        tenant_id="tenant_default",
        workspace_id="ws_default",
        goal="Mainline advisory analysis must fail when no board-approved contract-matching executor exists.",
    )
    approval = _seed_review_request(client, workflow_id=workflow_id)
    repository = client.app.state.repository
    _seed_worker(
        client,
        employee_id="emp_cto_advisory_incident",
        role_type="cto",
        provider_id="",
        role_profile_refs=["cto_primary"],
    )
    _assert_command_accepted(
        client.post(
            "/api/v1/commands/runtime-provider-upsert",
            json=_runtime_provider_upsert_payload(
                role_bindings=[
                    {
                        "target_ref": "execution_target:board_advisory_analysis",
                        "provider_model_entry_refs": ["prov_openai_compat::gpt-5.3-codex"],
                        "max_context_window_override": None,
                        "reasoning_effort_override": None,
                    }
                ],
                idempotency_key=f"runtime-provider-upsert:{workflow_id}:advisory-incident",
            ),
        )
    )
    _assert_command_accepted(
        client.post(
            "/api/v1/commands/runtime-provider-upsert",
            json=_runtime_provider_upsert_payload(
                role_bindings=[
                    {
                        "target_ref": "execution_target:board_advisory_analysis",
                        "provider_model_entry_refs": ["prov_openai_compat::gpt-5.3-codex"],
                        "max_context_window_override": None,
                        "reasoning_effort_override": None,
                    }
                ],
                idempotency_key=f"runtime-provider-upsert:{workflow_id}:no-real-executor",
            ),
        )
    )

    with _suppress_ceo_shadow_side_effects():
        enter_response = client.post(
            "/api/v1/commands/modify-constraints",
            json={
                "review_pack_id": approval["review_pack_id"],
                "review_pack_version": approval["review_pack_version"],
                "command_target_version": approval["command_target_version"],
                "approval_id": approval["approval_id"],
                "constraint_patch": {
                    "add_rules": ["Fail advisory analysis when no board-approved contract-matching executor exists."],
                    "remove_rules": [],
                    "replace_rules": [],
                },
                "board_comment": "No real contract-matching executor is on the roster for this flow.",
                "idempotency_key": f"board-modify:{approval['approval_id']}:no-real-executor",
            },
        )
    _assert_command_accepted(enter_response)

    advisory_session = repository.get_board_advisory_session_for_approval(approval["approval_id"])
    assert advisory_session is not None

    response = client.post(
        "/api/v1/commands/board-advisory-request-analysis",
        json={
            "session_id": advisory_session["session_id"],
            "idempotency_key": f"board-advisory-analysis:{advisory_session['session_id']}:no-real-executor",
        },
    )

    updated_session = repository.get_board_advisory_session_for_approval(approval["approval_id"])
    open_incidents = [
        item
        for item in repository.list_open_incidents()
        if item["workflow_id"] == workflow_id and item["incident_type"] == "BOARD_ADVISORY_ANALYSIS_FAILED"
    ]
    assert response.status_code == 200
    assert response.json()["status"] == "ACCEPTED"
    assert updated_session is not None
    run = repository.get_board_advisory_analysis_run(str(updated_session["latest_analysis_run_id"]))
    assert run is not None
    assert updated_session["status"] == "ANALYSIS_REJECTED"
    assert updated_session["latest_analysis_status"] == "FAILED"
    assert updated_session["latest_patch_proposal_ref"] is None
    assert len(open_incidents) == 1


def test_board_advisory_analysis_contract_mismatch_opens_incident_without_synthetic_fallback(
    client,
    monkeypatch,
):
    workflow_id = "wf_advisory_analysis_contract_mismatch"
    _ensure_scoped_workflow(
        client,
        workflow_id=workflow_id,
        tenant_id="tenant_default",
        workspace_id="ws_default",
        goal="A real executor that does not satisfy the advisory contract should fail explicitly instead of falling back.",
    )
    approval = _seed_review_request(client, workflow_id=workflow_id)
    repository = client.app.state.repository
    _seed_worker(
        client,
        employee_id="emp_backend_advisory_contract_mismatch",
        role_type="backend_engineer",
        provider_id="",
        role_profile_refs=["backend_engineer_primary"],
    )
    monkeypatch.setattr(
        repository,
        "list_employee_projections",
        lambda **kwargs: [
            {
                "employee_id": "emp_backend_advisory_contract_mismatch",
                "role_type": "backend_engineer",
                "skill_profile_json": {},
                "personality_profile_json": {},
                "aesthetic_profile_json": {},
                "provider_id": "",
                "role_profile_refs": ["backend_engineer_primary"],
                "state": "ACTIVE",
                "board_approved": True,
            }
        ],
    )
    _assert_command_accepted(
        client.post(
            "/api/v1/commands/runtime-provider-upsert",
            json=_runtime_provider_upsert_payload(
                role_bindings=[
                    {
                        "target_ref": "execution_target:board_advisory_analysis",
                        "provider_model_entry_refs": ["prov_openai_compat::gpt-5.3-codex"],
                        "max_context_window_override": None,
                        "reasoning_effort_override": None,
                    }
                ],
                idempotency_key=f"runtime-provider-upsert:{workflow_id}:contract-mismatch",
            ),
        )
    )

    with _suppress_ceo_shadow_side_effects():
        enter_response = client.post(
            "/api/v1/commands/modify-constraints",
            json={
                "review_pack_id": approval["review_pack_id"],
                "review_pack_version": approval["review_pack_version"],
                "command_target_version": approval["command_target_version"],
                "approval_id": approval["approval_id"],
                "constraint_patch": {
                    "add_rules": ["Fail if only a contract-mismatched executor is available."],
                    "remove_rules": [],
                    "replace_rules": [],
                },
                "board_comment": "Do not silently use the synthetic advisory executor when a real but incompatible worker exists.",
                "idempotency_key": f"board-modify:{approval['approval_id']}:contract-mismatch",
            },
        )
    _assert_command_accepted(enter_response)

    advisory_session = repository.get_board_advisory_session_for_approval(approval["approval_id"])
    assert advisory_session is not None

    response = client.post(
        "/api/v1/commands/board-advisory-request-analysis",
        json={
            "session_id": advisory_session["session_id"],
            "idempotency_key": f"board-advisory-analysis:{advisory_session['session_id']}:contract-mismatch",
        },
    )

    updated_session = repository.get_board_advisory_session_for_approval(approval["approval_id"])
    open_incidents = [
        item
        for item in repository.list_open_incidents()
        if item["workflow_id"] == workflow_id and item["incident_type"] == "BOARD_ADVISORY_ANALYSIS_FAILED"
    ]

    assert response.status_code == 200
    assert response.json()["status"] == "ACCEPTED"
    assert updated_session is not None
    assert updated_session["status"] == "ANALYSIS_REJECTED"
    assert updated_session["latest_analysis_status"] == "FAILED"
    assert updated_session["latest_analysis_incident_id"] is not None
    assert "contract" in str(updated_session["latest_analysis_error"] or "").lower()
    assert updated_session["latest_patch_proposal_ref"] is None
    assert len(open_incidents) == 1


def test_board_advisory_analysis_live_provider_pause_opens_incident_without_deterministic_fallback(
    client,
    monkeypatch,
):
    workflow_id = "wf_advisory_analysis_live_provider_paused"
    _ensure_scoped_workflow(
        client,
        workflow_id=workflow_id,
        tenant_id="tenant_default",
        workspace_id="ws_default",
        goal="A paused live provider must fail advisory analysis explicitly instead of falling back to deterministic mode.",
    )
    approval = _seed_review_request(client, workflow_id=workflow_id)
    repository = client.app.state.repository
    _seed_worker(
        client,
        employee_id="emp_architect_live_provider_paused",
        role_type="governance_architect",
        provider_id="",
        role_profile_refs=["architect_primary"],
    )
    _assert_command_accepted(
        client.post(
            "/api/v1/commands/runtime-provider-upsert",
            json=_runtime_provider_upsert_payload(
                role_bindings=[
                    {
                        "target_ref": "ceo_shadow",
                        "provider_model_entry_refs": ["prov_openai_compat::gpt-5.3-codex"],
                        "max_context_window_override": None,
                        "reasoning_effort_override": None,
                    },
                    {
                        "target_ref": EXECUTION_TARGET_ARCHITECT_GOVERNANCE_DOCUMENT,
                        "provider_model_entry_refs": ["prov_openai_compat::gpt-5.3-codex"],
                        "max_context_window_override": None,
                        "reasoning_effort_override": None,
                    },
                ],
                idempotency_key=f"runtime-provider-upsert:{workflow_id}:paused-provider",
            ),
        )
    )

    with _suppress_ceo_shadow_side_effects():
        enter_response = client.post(
            "/api/v1/commands/modify-constraints",
            json={
                "review_pack_id": approval["review_pack_id"],
                "review_pack_version": approval["review_pack_version"],
                "command_target_version": approval["command_target_version"],
                "approval_id": approval["approval_id"],
                "constraint_patch": {
                    "add_rules": ["If the live provider is paused, fail and recover explicitly."],
                    "remove_rules": [],
                    "replace_rules": [],
                },
                "board_comment": "Do not silently downgrade this analysis run.",
                "idempotency_key": f"board-modify:{approval['approval_id']}:paused-provider",
            },
        )
    _assert_command_accepted(enter_response)

    advisory_session = repository.get_board_advisory_session_for_approval(approval["approval_id"])
    assert advisory_session is not None
    monkeypatch.setattr(
        repository,
        "has_open_circuit_breaker_for_provider",
        lambda provider_id, **kwargs: provider_id == OPENAI_COMPAT_PROVIDER_ID,
    )

    response = client.post(
        "/api/v1/commands/board-advisory-request-analysis",
        json={
            "session_id": advisory_session["session_id"],
            "idempotency_key": f"board-advisory-analysis:{advisory_session['session_id']}:paused-provider",
        },
    )

    updated_session = repository.get_board_advisory_session_for_approval(approval["approval_id"])
    open_incidents = [
        item
        for item in repository.list_open_incidents()
        if item["workflow_id"] == workflow_id and item["incident_type"] == "BOARD_ADVISORY_ANALYSIS_FAILED"
    ]

    assert response.status_code == 200
    assert response.json()["status"] == "ACCEPTED"
    assert updated_session is not None
    assert updated_session["status"] == "ANALYSIS_REJECTED"
    assert updated_session["latest_analysis_status"] == "FAILED"
    assert updated_session["latest_analysis_incident_id"] is not None
    assert "paused" in str(updated_session["latest_analysis_error"] or "").lower()
    assert updated_session["latest_patch_proposal_ref"] is None
    assert len(open_incidents) == 1


def test_board_advisory_request_analysis_creates_patch_proposal_without_resolving_approval(client):
    workflow_id = "wf_modify_advisory"
    _ensure_scoped_workflow(
        client,
        workflow_id=workflow_id,
        tenant_id="tenant_default",
        workspace_id="ws_default",
        goal="Generate a board advisory patch proposal without applying it.",
    )
    approval = _seed_review_request(client, workflow_id=workflow_id)
    repository = client.app.state.repository
    original_profile = repository.get_latest_governance_profile(workflow_id)
    assert original_profile is not None

    with _suppress_ceo_shadow_side_effects():
        enter_response = client.post(
            "/api/v1/commands/modify-constraints",
            json={
                "review_pack_id": approval["review_pack_id"],
                "review_pack_version": approval["review_pack_version"],
                "command_target_version": approval["command_target_version"],
                "approval_id": approval["approval_id"],
                "constraint_patch": {
                    "add_rules": ["Preserve the current implementation slice but raise review rigor."],
                    "remove_rules": [],
                    "replace_rules": [],
                },
                "governance_patch": {
                    "approval_mode": "EXPERT_GATED",
                    "audit_mode": "TICKET_TRACE",
                },
                "board_comment": "Tighten governance before the next replan pass.",
                "idempotency_key": f"board-modify:{approval['approval_id']}:advisory-enter",
            },
        )
    assert enter_response.status_code == 200
    assert enter_response.json()["status"] == "ACCEPTED"

    advisory_session = repository.get_board_advisory_session_for_approval(approval["approval_id"])
    assert advisory_session is not None
    graph_version_before = build_ticket_graph_snapshot(repository, workflow_id).graph_version

    response = client.post(
        "/api/v1/commands/board-advisory-request-analysis",
        json={
            "session_id": advisory_session["session_id"],
            "idempotency_key": f"board-advisory-analysis:{advisory_session['session_id']}:1",
        },
    )

    advisory_session = repository.get_board_advisory_session_for_approval(approval["approval_id"])
    latest_profile = repository.get_latest_governance_profile(workflow_id)
    review_room = client.get(f"/api/v1/projections/review-room/{approval['review_pack_id']}")
    graph_version_after = build_ticket_graph_snapshot(repository, workflow_id).graph_version

    assert response.status_code == 200
    assert response.json()["status"] == "ACCEPTED"
    assert advisory_session is not None
    assert advisory_session["status"] == "PENDING_BOARD_CONFIRMATION"
    assert advisory_session["latest_analysis_run_id"]
    assert advisory_session["latest_analysis_status"] == "SUCCEEDED"
    assert advisory_session["latest_analysis_incident_id"] is None
    assert advisory_session["latest_analysis_error"] is None
    assert advisory_session["latest_analysis_trace_artifact_ref"] is not None
    assert advisory_session["latest_patch_proposal_ref"] is not None
    assert advisory_session["approved_patch_ref"] is None
    updated = repository.get_approval_by_review_pack_id(approval["review_pack_id"])
    assert updated is not None
    assert updated["status"] == APPROVAL_STATUS_OPEN
    assert graph_version_after == graph_version_before
    assert latest_profile is not None
    assert latest_profile["profile_id"] == original_profile["profile_id"]
    advisory_context = review_room.json()["data"]["review_pack"]["advisory_context"]
    assert advisory_context["change_flow_status"] == "PENDING_BOARD_CONFIRMATION"
    assert advisory_context["latest_patch_proposal_ref"] == advisory_session["latest_patch_proposal_ref"]
    assert advisory_context["latest_analysis_run_id"] == advisory_session["latest_analysis_run_id"]
    assert advisory_context["latest_analysis_status"] == "SUCCEEDED"
    assert advisory_context["latest_analysis_trace_artifact_ref"] == advisory_session["latest_analysis_trace_artifact_ref"]
    assert advisory_context["proposal_summary"]
    assert advisory_context["pros"]
    assert advisory_context["cons"]
    assert advisory_context["risk_alerts"]


def test_board_advisory_request_analysis_accepts_add_node_patch_proposal(client, monkeypatch):
    workflow_id = "wf_modify_advisory_add_node"
    _ensure_scoped_workflow(
        client,
        workflow_id=workflow_id,
        tenant_id="tenant_default",
        workspace_id="ws_default",
        goal="Persist add-node placeholder proposals without resolving the approval.",
    )
    approval = _seed_review_request(client, workflow_id=workflow_id)
    repository = client.app.state.repository
    _seed_worker(
        client,
        employee_id="emp_cto_advisory_incident",
        role_type="cto",
        provider_id="",
        role_profile_refs=["cto_primary"],
    )
    _assert_command_accepted(
        client.post(
            "/api/v1/commands/runtime-provider-upsert",
            json=_runtime_provider_upsert_payload(
                role_bindings=[
                    {
                        "target_ref": "execution_target:board_advisory_analysis",
                        "provider_model_entry_refs": ["prov_openai_compat::gpt-5.3-codex"],
                        "max_context_window_override": None,
                        "reasoning_effort_override": None,
                    }
                ],
                idempotency_key=f"runtime-provider-upsert:{workflow_id}:advisory-incident",
            ),
        )
    )

    with _suppress_ceo_shadow_side_effects():
        enter_response = client.post(
            "/api/v1/commands/modify-constraints",
            json={
                "review_pack_id": approval["review_pack_id"],
                "review_pack_version": approval["review_pack_version"],
                "command_target_version": approval["command_target_version"],
                "approval_id": approval["approval_id"],
                "constraint_patch": {
                    "add_rules": ["Allow the advisory flow to propose a graph-only placeholder node."],
                    "remove_rules": [],
                    "replace_rules": [],
                },
                "board_comment": "The analysis output should be able to add a new placeholder node.",
                "idempotency_key": f"board-modify:{approval['approval_id']}:advisory-add-node-enter",
            },
        )
    assert enter_response.status_code == 200
    assert enter_response.json()["status"] == "ACCEPTED"

    advisory_session = repository.get_board_advisory_session_for_approval(approval["approval_id"])
    assert advisory_session is not None
    proposal = GraphPatchProposal.model_validate(
        {
            "proposal_ref": f"pa://graph-patch-proposal/{advisory_session['session_id']}@1",
            "workflow_id": workflow_id,
            "session_id": advisory_session["session_id"],
            "base_graph_version": build_ticket_graph_snapshot(repository, workflow_id).graph_version,
            "proposal_summary": "Add a placeholder node for the follow-up implementation slice.",
            "impact_summary": "The graph should show a planned node before a real ticket exists.",
            "add_nodes": [
                {
                    "node_id": "node_advisory_placeholder_build",
                    "node_kind": "IMPLEMENTATION",
                    "deliverable_kind": "source_code_delivery",
                    "role_hint": "frontend_engineer_primary",
                    "parent_node_id": "node_homepage_visual",
                    "dependency_node_ids": [],
                }
            ],
            "source_decision_pack_ref": advisory_session["decision_pack_refs"][0],
            "proposal_hash": "hash-advisory-add-node-proposal",
        }
    )

    with (
        patch("app.core.approval_handlers.build_graph_patch_proposal", return_value=proposal),
        patch("app.core.board_advisory_analysis.build_graph_patch_proposal", return_value=proposal),
        patch("app.core.board_advisory.build_graph_patch_proposal", return_value=proposal),
    ):
        response = client.post(
            "/api/v1/commands/board-advisory-request-analysis",
            json={
                "session_id": advisory_session["session_id"],
                "idempotency_key": f"board-advisory-analysis:{advisory_session['session_id']}:add-node",
            },
        )

    advisory_session = repository.get_board_advisory_session_for_approval(approval["approval_id"])

    assert response.status_code == 200
    assert response.json()["status"] == "ACCEPTED"
    assert advisory_session is not None
    assert advisory_session["status"] == "PENDING_BOARD_CONFIRMATION"
    assert advisory_session["latest_patch_proposal_ref"] == proposal.proposal_ref
    assert advisory_session["latest_patch_proposal"]["add_nodes"][0]["node_id"] == "node_advisory_placeholder_build"


def test_board_advisory_analysis_failure_opens_incident_and_rerun_recovery(client, monkeypatch):
    workflow_id = "wf_advisory_analysis_incident"
    _ensure_scoped_workflow(
        client,
        workflow_id=workflow_id,
        tenant_id="tenant_default",
        workspace_id="ws_default",
        goal="Fail advisory analysis explicitly and recover it with an idempotent rerun.",
    )
    approval = _seed_review_request(client, workflow_id=workflow_id)
    repository = client.app.state.repository
    _seed_worker(
        client,
        employee_id="emp_cto_advisory_incident",
        role_type="cto",
        provider_id="",
        role_profile_refs=["cto_primary"],
    )
    _assert_command_accepted(
        client.post(
            "/api/v1/commands/runtime-provider-upsert",
            json=_runtime_provider_upsert_payload(
                role_bindings=[
                    {
                        "target_ref": "execution_target:board_advisory_analysis",
                        "provider_model_entry_refs": ["prov_openai_compat::gpt-5.3-codex"],
                        "max_context_window_override": None,
                        "reasoning_effort_override": None,
                    }
                ],
                idempotency_key=f"runtime-provider-upsert:{workflow_id}:advisory-incident",
            ),
        )
    )

    with _suppress_ceo_shadow_side_effects():
        enter_response = client.post(
            "/api/v1/commands/modify-constraints",
            json={
                "review_pack_id": approval["review_pack_id"],
                "review_pack_version": approval["review_pack_version"],
                "command_target_version": approval["command_target_version"],
                "approval_id": approval["approval_id"],
                "constraint_patch": {
                    "add_rules": ["Fail the analysis explicitly if the patch proposal cannot be produced."],
                    "remove_rules": [],
                    "replace_rules": [],
                },
                "board_comment": "This change flow must open an incident instead of silently falling back.",
                "idempotency_key": f"board-modify:{approval['approval_id']}:analysis-incident-enter",
            },
        )
    assert enter_response.status_code == 200
    assert enter_response.json()["status"] == "ACCEPTED"

    advisory_session = repository.get_board_advisory_session_for_approval(approval["approval_id"])
    assert advisory_session is not None

    proposal = GraphPatchProposal.model_validate(
        {
            "proposal_ref": f"pa://graph-patch-proposal/{advisory_session['session_id']}@1",
            "workflow_id": workflow_id,
            "session_id": advisory_session["session_id"],
            "base_graph_version": build_ticket_graph_snapshot(repository, workflow_id).graph_version,
            "proposal_summary": "Recover the advisory flow after the provider comes back.",
            "impact_summary": "Freeze the current execution node until the tighter advisory policy lands.",
            "freeze_node_ids": ["node_homepage_visual"],
            "source_decision_pack_ref": advisory_session["decision_pack_refs"][0],
            "proposal_hash": "hash-advisory-rerun-recovery",
        }
    )
    provider_results = [
        RuntimeError("simulated advisory analysis failure"),
        OpenAICompatProviderResult(
            output_text=json.dumps(proposal.model_dump(mode="json")),
            response_id="resp_advisory_rerun_recovery",
        ),
    ]

    def _fake_invoke_openai_compat_response(*args, **kwargs):
        next_result = provider_results.pop(0)
        if isinstance(next_result, Exception):
            raise next_result
        return next_result

    with patch(
        "app.core.board_advisory_analysis.invoke_openai_compat_response",
        side_effect=_fake_invoke_openai_compat_response,
    ):
        response = client.post(
            "/api/v1/commands/board-advisory-request-analysis",
            json={
                "session_id": advisory_session["session_id"],
                "idempotency_key": f"board-advisory-analysis:{advisory_session['session_id']}:incident",
            },
        )

    advisory_session = repository.get_board_advisory_session_for_approval(approval["approval_id"])
    open_incidents = [
        item
        for item in repository.list_open_incidents()
        if item["workflow_id"] == workflow_id and item["incident_type"] == "BOARD_ADVISORY_ANALYSIS_FAILED"
    ]

    assert response.status_code == 200
    assert response.json()["status"] == "ACCEPTED"
    assert advisory_session is not None
    assert advisory_session["status"] == "ANALYSIS_REJECTED"
    assert advisory_session["latest_analysis_status"] == "FAILED"
    assert advisory_session["latest_analysis_incident_id"] is not None
    assert advisory_session["latest_analysis_error"]
    assert advisory_session["latest_patch_proposal_ref"] is None
    assert len(open_incidents) == 1
    assert open_incidents[0]["incident_type"] == "BOARD_ADVISORY_ANALYSIS_FAILED"
    assert open_incidents[0]["incident_id"] == advisory_session["latest_analysis_incident_id"]

    incident_id = str(advisory_session["latest_analysis_incident_id"])
    incident_response = client.get(f"/api/v1/projections/incidents/{incident_id}")
    assert incident_response.status_code == 200
    assert incident_response.json()["data"]["available_followup_actions"] == [
        "RERUN_BOARD_ADVISORY_ANALYSIS",
        "RESTORE_ONLY",
    ]
    assert incident_response.json()["data"]["recommended_followup_action"] == "RERUN_BOARD_ADVISORY_ANALYSIS"

    with patch(
        "app.core.board_advisory_analysis.invoke_openai_compat_response",
        side_effect=_fake_invoke_openai_compat_response,
    ):
        rerun_response = client.post(
            "/api/v1/commands/incident-resolve",
            json=_incident_resolve_payload(
                incident_id,
                idempotency_key=f"incident-resolve:{incident_id}:rerun-advisory-analysis",
                followup_action="RERUN_BOARD_ADVISORY_ANALYSIS",
                resolution_summary="Rerun the advisory analysis after the analysis harness is available again.",
            ),
        )

    advisory_session = repository.get_board_advisory_session_for_approval(approval["approval_id"])
    updated = repository.get_approval_by_review_pack_id(approval["review_pack_id"])
    open_incidents = [
        item
        for item in repository.list_open_incidents()
        if item["workflow_id"] == workflow_id and item["incident_type"] == "BOARD_ADVISORY_ANALYSIS_FAILED"
    ]

    assert rerun_response.status_code == 200
    assert rerun_response.json()["status"] == "ACCEPTED"
    assert advisory_session is not None
    assert advisory_session["status"] == "PENDING_BOARD_CONFIRMATION"
    assert advisory_session["latest_analysis_status"] == "SUCCEEDED"
    assert advisory_session["latest_analysis_incident_id"] is None
    assert advisory_session["latest_patch_proposal_ref"] is not None
    assert updated is not None
    assert updated["status"] == APPROVAL_STATUS_OPEN
    assert open_incidents == []


def test_board_advisory_apply_patch_resolves_approval_and_advances_graph_version(client):
    workflow_id = "wf_advisory_apply_patch"
    _ensure_scoped_workflow(
        client,
        workflow_id=workflow_id,
        tenant_id="tenant_default",
        workspace_id="ws_default",
        goal="Apply an approved advisory patch into the runtime graph.",
    )
    approval = _seed_review_request(client, workflow_id=workflow_id)
    repository = client.app.state.repository
    original_profile = repository.get_latest_governance_profile(workflow_id)
    assert original_profile is not None

    with _suppress_ceo_shadow_side_effects():
        enter_response = client.post(
            "/api/v1/commands/modify-constraints",
            json={
                "review_pack_id": approval["review_pack_id"],
                "review_pack_version": approval["review_pack_version"],
                "command_target_version": approval["command_target_version"],
                "approval_id": approval["approval_id"],
                "constraint_patch": {
                    "add_rules": ["Tighten the branch before the next runtime pass."],
                    "remove_rules": [],
                    "replace_rules": [],
                },
                "governance_patch": {
                    "approval_mode": "EXPERT_GATED",
                    "audit_mode": "TICKET_TRACE",
                },
                "board_comment": "We need a reviewed patch before runtime import.",
                "idempotency_key": f"board-modify:{approval['approval_id']}:apply-enter",
            },
        )
    assert enter_response.status_code == 200
    assert enter_response.json()["status"] == "ACCEPTED"

    advisory_session = repository.get_board_advisory_session_for_approval(approval["approval_id"])
    assert advisory_session is not None
    graph_version_before = build_ticket_graph_snapshot(repository, workflow_id).graph_version

    analysis_response = client.post(
        "/api/v1/commands/board-advisory-request-analysis",
        json={
            "session_id": advisory_session["session_id"],
            "idempotency_key": f"board-advisory-analysis:{advisory_session['session_id']}:apply",
        },
    )
    assert analysis_response.status_code == 200
    assert analysis_response.json()["status"] == "ACCEPTED"

    advisory_session = repository.get_board_advisory_session_for_approval(approval["approval_id"])
    assert advisory_session is not None
    apply_response = client.post(
        "/api/v1/commands/board-advisory-apply-patch",
        json={
            "session_id": advisory_session["session_id"],
            "proposal_ref": advisory_session["latest_patch_proposal_ref"],
            "idempotency_key": f"board-advisory-apply:{advisory_session['session_id']}:1",
        },
    )

    advisory_session = repository.get_board_advisory_session_for_approval(approval["approval_id"])
    latest_profile = repository.get_latest_governance_profile(workflow_id)
    updated = repository.get_approval_by_review_pack_id(approval["review_pack_id"])
    graph_snapshot = build_ticket_graph_snapshot(repository, workflow_id)

    assert apply_response.status_code == 200
    assert apply_response.json()["status"] == "ACCEPTED"
    assert advisory_session is not None
    assert advisory_session["status"] == "APPLIED"
    assert advisory_session["approved_patch_ref"] is not None
    assert advisory_session["patched_graph_version"] == graph_snapshot.graph_version
    assert advisory_session["patched_graph_version"] != graph_version_before
    assert updated["status"] == APPROVAL_STATUS_MODIFIED_CONSTRAINTS
    assert updated["payload"]["resolution"]["decision_action"] == "MODIFY_CONSTRAINTS"
    assert latest_profile is not None
    assert latest_profile["profile_id"] != original_profile["profile_id"]
    assert latest_profile["supersedes_ref"] == original_profile["profile_id"]
    assert latest_profile["approval_mode"] == "EXPERT_GATED"
    assert latest_profile["audit_mode"] == "TICKET_TRACE"
    assert "node_homepage_visual" not in graph_snapshot.index_summary.ready_node_ids
    assert "node_homepage_visual" in graph_snapshot.index_summary.blocked_node_ids
    assert any(
        item.reason_code == "ADVISORY_PATCH_FROZEN"
        and "node_homepage_visual" in item.node_ids
        for item in graph_snapshot.index_summary.blocked_reasons
    )


def test_board_advisory_apply_patch_accepts_add_node_placeholder_without_runtime_ready_pollution(client, monkeypatch):
    workflow_id = "wf_advisory_apply_add_node"
    _ensure_scoped_workflow(
        client,
        workflow_id=workflow_id,
        tenant_id="tenant_default",
        workspace_id="ws_default",
        goal="Apply an advisory add-node patch as a graph-only placeholder.",
    )
    approval = _seed_review_request(client, workflow_id=workflow_id)
    repository = client.app.state.repository
    _seed_worker(
        client,
        employee_id="emp_cto_advisory_incident",
        role_type="cto",
        provider_id="",
        role_profile_refs=["cto_primary"],
    )
    _assert_command_accepted(
        client.post(
            "/api/v1/commands/runtime-provider-upsert",
            json=_runtime_provider_upsert_payload(
                idempotency_key=f"runtime-provider-upsert:{workflow_id}:advisory-incident",
            ),
        )
    )
    monkeypatch.setattr(repository, "list_employee_projections", lambda **kwargs: [])

    with _suppress_ceo_shadow_side_effects():
        enter_response = client.post(
            "/api/v1/commands/modify-constraints",
            json={
                "review_pack_id": approval["review_pack_id"],
                "review_pack_version": approval["review_pack_version"],
                "command_target_version": approval["command_target_version"],
                "approval_id": approval["approval_id"],
                "constraint_patch": {
                    "add_rules": ["Plan a placeholder node before runtime ticket creation."],
                    "remove_rules": [],
                    "replace_rules": [],
                },
                "board_comment": "Import the placeholder into the graph without treating it as ready work.",
                "idempotency_key": f"board-modify:{approval['approval_id']}:apply-add-node-enter",
            },
        )
    assert enter_response.status_code == 200
    assert enter_response.json()["status"] == "ACCEPTED"

    advisory_session = repository.get_board_advisory_session_for_approval(approval["approval_id"])
    assert advisory_session is not None
    proposal = GraphPatchProposal.model_validate(
        {
            "proposal_ref": f"pa://graph-patch-proposal/{advisory_session['session_id']}@1",
            "workflow_id": workflow_id,
            "session_id": advisory_session["session_id"],
            "base_graph_version": build_ticket_graph_snapshot(repository, workflow_id).graph_version,
            "proposal_summary": "Add the planned implementation node.",
            "impact_summary": "The graph should show a placeholder node without creating a runtime ticket.",
            "add_nodes": [
                {
                    "node_id": "node_apply_placeholder_build",
                    "node_kind": "IMPLEMENTATION",
                    "deliverable_kind": "source_code_delivery",
                    "role_hint": "frontend_engineer_primary",
                    "parent_node_id": "node_homepage_visual",
                    "dependency_node_ids": [],
                }
            ],
            "focus_node_ids": ["node_apply_placeholder_build"],
            "source_decision_pack_ref": advisory_session["decision_pack_refs"][0],
            "proposal_hash": "hash-apply-add-node-placeholder",
        }
    )
    with repository.transaction() as connection:
        repository.store_board_advisory_patch_proposal(
            connection,
            session_id=advisory_session["session_id"],
            proposal_ref=proposal.proposal_ref,
            proposal=proposal.model_dump(mode="json"),
            decision_pack_refs=list(advisory_session["decision_pack_refs"]),
            updated_at=datetime.fromisoformat("2026-04-16T22:10:00+08:00"),
        )

    apply_response = client.post(
        "/api/v1/commands/board-advisory-apply-patch",
        json={
            "session_id": advisory_session["session_id"],
            "proposal_ref": proposal.proposal_ref,
            "idempotency_key": f"board-advisory-apply:{advisory_session['session_id']}:add-node",
        },
    )

    advisory_session = repository.get_board_advisory_session_for_approval(approval["approval_id"])
    graph_snapshot = build_ticket_graph_snapshot(repository, workflow_id)
    placeholder_node = next(
        node for node in graph_snapshot.nodes if node.graph_node_id == "node_apply_placeholder_build"
    )

    assert apply_response.status_code == 200
    assert apply_response.json()["status"] == "ACCEPTED"
    assert advisory_session is not None
    assert advisory_session["status"] == "APPLIED"
    assert placeholder_node.is_placeholder is True
    assert placeholder_node.ticket_id is None
    assert "node_apply_placeholder_build" not in graph_snapshot.index_summary.ready_graph_node_ids
    assert "node_apply_placeholder_build" not in graph_snapshot.index_summary.ready_node_ids


def test_board_advisory_apply_patch_rejects_stale_proposal(client):
    workflow_id = "wf_advisory_apply_stale"
    _ensure_scoped_workflow(
        client,
        workflow_id=workflow_id,
        tenant_id="tenant_default",
        workspace_id="ws_default",
        goal="Reject advisory patch import when the proposal graph version is stale.",
    )
    approval = _seed_review_request(client, workflow_id=workflow_id)
    repository = client.app.state.repository

    with _suppress_ceo_shadow_side_effects():
        enter_response = client.post(
            "/api/v1/commands/modify-constraints",
            json={
                "review_pack_id": approval["review_pack_id"],
                "review_pack_version": approval["review_pack_version"],
                "command_target_version": approval["command_target_version"],
                "approval_id": approval["approval_id"],
                "constraint_patch": {
                    "add_rules": ["Freeze the current branch until the board confirms the patch."],
                    "remove_rules": [],
                    "replace_rules": [],
                },
                "board_comment": "Prepare the patch but do not apply it yet.",
                "idempotency_key": f"board-modify:{approval['approval_id']}:stale-enter",
            },
        )
    assert enter_response.status_code == 200
    assert enter_response.json()["status"] == "ACCEPTED"

    advisory_session = repository.get_board_advisory_session_for_approval(approval["approval_id"])
    assert advisory_session is not None
    analysis_response = client.post(
        "/api/v1/commands/board-advisory-request-analysis",
        json={
            "session_id": advisory_session["session_id"],
            "idempotency_key": f"board-advisory-analysis:{advisory_session['session_id']}:stale",
        },
    )
    assert analysis_response.status_code == 200
    assert analysis_response.json()["status"] == "ACCEPTED"

    mutate_response = client.post(
        "/api/v1/commands/ticket-create",
        json=_ticket_create_payload(
            workflow_id=workflow_id,
            ticket_id="tkt_advisory_stale_extra",
            node_id="node_advisory_stale_extra",
            output_schema_ref="source_code_delivery",
            delivery_stage="BUILD",
            parent_ticket_id=approval["payload"]["review_pack"]["subject"]["source_ticket_id"],
        ),
    )
    assert mutate_response.status_code == 200
    assert mutate_response.json()["status"] == "ACCEPTED"

    advisory_session = repository.get_board_advisory_session_for_approval(approval["approval_id"])
    assert advisory_session is not None
    apply_response = client.post(
        "/api/v1/commands/board-advisory-apply-patch",
        json={
            "session_id": advisory_session["session_id"],
            "proposal_ref": advisory_session["latest_patch_proposal_ref"],
            "idempotency_key": f"board-advisory-apply:{advisory_session['session_id']}:stale",
        },
    )

    updated = repository.get_approval_by_review_pack_id(approval["review_pack_id"])
    advisory_session = repository.get_board_advisory_session_for_approval(approval["approval_id"])

    assert apply_response.status_code == 200
    assert apply_response.json()["status"] == "REJECTED"
    assert "stale" in str(apply_response.json()["reason"] or "").lower()
    assert updated["status"] == APPROVAL_STATUS_OPEN
    assert advisory_session is not None
    assert advisory_session["status"] == "PENDING_BOARD_CONFIRMATION"
    assert advisory_session["approved_patch_ref"] is None


def test_board_advisory_apply_patch_rejects_patch_that_removes_executing_node(client):
    workflow_id = "wf_advisory_apply_remove_executing"
    _ensure_scoped_workflow(
        client,
        workflow_id=workflow_id,
        tenant_id="tenant_default",
        workspace_id="ws_default",
        goal="Reject advisory patches that try to remove executing nodes.",
    )
    approval = _seed_review_request(client, workflow_id=workflow_id)
    repository = client.app.state.repository
    _create_lease_and_start_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_advisory_remove_executing",
        node_id="node_advisory_remove_executing",
        output_schema_ref=SOURCE_CODE_DELIVERY_SCHEMA_REF,
        delivery_stage="BUILD",
    )

    with _suppress_ceo_shadow_side_effects():
        enter_response = client.post(
            "/api/v1/commands/modify-constraints",
            json={
                "review_pack_id": approval["review_pack_id"],
                "review_pack_version": approval["review_pack_version"],
                "command_target_version": approval["command_target_version"],
                "approval_id": approval["approval_id"],
                "constraint_patch": {
                    "add_rules": ["Do not let graph patches silently remove executing nodes."],
                    "remove_rules": [],
                    "replace_rules": [],
                },
                "board_comment": "Patch validation must reject executing-node removal.",
                "idempotency_key": f"board-modify:{approval['approval_id']}:remove-executing",
            },
        )
    assert enter_response.status_code == 200
    assert enter_response.json()["status"] == "ACCEPTED"

    advisory_session = repository.get_board_advisory_session_for_approval(approval["approval_id"])
    assert advisory_session is not None
    proposal = GraphPatchProposal.model_validate(
        {
            "proposal_ref": f"pa://graph-patch-proposal/{advisory_session['session_id']}@1",
            "workflow_id": workflow_id,
            "session_id": advisory_session["session_id"],
            "base_graph_version": build_ticket_graph_snapshot(repository, workflow_id).graph_version,
            "proposal_summary": "Remove the executing node from the graph.",
            "impact_summary": "This proposal should fail because the target node is still executing.",
            "remove_node_ids": ["node_advisory_remove_executing"],
            "source_decision_pack_ref": advisory_session["decision_pack_refs"][0],
            "proposal_hash": "hash-remove-executing-node",
        }
    )
    with repository.transaction() as connection:
        repository.store_board_advisory_patch_proposal(
            connection,
            session_id=advisory_session["session_id"],
            proposal_ref=proposal.proposal_ref,
            proposal=proposal.model_dump(mode="json"),
            decision_pack_refs=list(advisory_session["decision_pack_refs"]),
            updated_at=datetime.fromisoformat("2026-04-16T21:30:00+08:00"),
        )

    apply_response = client.post(
        "/api/v1/commands/board-advisory-apply-patch",
        json={
            "session_id": advisory_session["session_id"],
            "proposal_ref": proposal.proposal_ref,
            "idempotency_key": f"board-advisory-apply:{advisory_session['session_id']}:remove-executing",
        },
    )

    updated = repository.get_approval_by_review_pack_id(approval["review_pack_id"])
    advisory_session = repository.get_board_advisory_session_for_approval(approval["approval_id"])

    assert apply_response.status_code == 200
    assert apply_response.json()["status"] == "REJECTED"
    assert "execut" in str(apply_response.json()["reason"] or "").lower()
    assert updated["status"] == APPROVAL_STATUS_OPEN
    assert advisory_session is not None
    assert advisory_session["status"] == "PENDING_BOARD_CONFIRMATION"
    assert advisory_session["approved_patch_ref"] is None


def test_board_advisory_apply_patch_rejects_synthetic_review_lane_targets(client):
    workflow_id = "wf_advisory_apply_review_lane"
    _ensure_scoped_workflow(
        client,
        workflow_id=workflow_id,
        tenant_id="tenant_default",
        workspace_id="ws_default",
        goal="Reject advisory patches that try to target synthetic review graph lanes.",
    )
    approval = _seed_review_request(client, workflow_id=workflow_id)
    repository = client.app.state.repository
    monkeypatch.setattr(repository, "list_employee_projections", lambda **kwargs: [])

    with _suppress_ceo_shadow_side_effects():
        enter_response = client.post(
            "/api/v1/commands/modify-constraints",
            json={
                "review_pack_id": approval["review_pack_id"],
                "review_pack_version": approval["review_pack_version"],
                "command_target_version": approval["command_target_version"],
                "approval_id": approval["approval_id"],
                "constraint_patch": {
                    "add_rules": ["Reject graph patches that point at synthetic review lanes."],
                    "remove_rules": [],
                    "replace_rules": [],
                },
                "board_comment": "The patch layer must reject review-lane targets explicitly.",
                "idempotency_key": f"board-modify:{approval['approval_id']}:review-lane",
            },
        )
    assert enter_response.status_code == 200
    assert enter_response.json()["status"] == "ACCEPTED"

    advisory_session = repository.get_board_advisory_session_for_approval(approval["approval_id"])
    assert advisory_session is not None
    proposal = GraphPatchProposal.model_validate(
        {
            "proposal_ref": f"pa://graph-patch-proposal/{advisory_session['session_id']}@1",
            "workflow_id": workflow_id,
            "session_id": advisory_session["session_id"],
            "base_graph_version": build_ticket_graph_snapshot(repository, workflow_id).graph_version,
            "proposal_summary": "Freeze the synthetic review lane.",
            "impact_summary": "This proposal should fail because review lanes are not valid patch targets.",
            "freeze_node_ids": ["node_homepage_visual::review"],
            "source_decision_pack_ref": advisory_session["decision_pack_refs"][0],
            "proposal_hash": "hash-review-lane-target",
        }
    )
    with repository.transaction() as connection:
        repository.store_board_advisory_patch_proposal(
            connection,
            session_id=advisory_session["session_id"],
            proposal_ref=proposal.proposal_ref,
            proposal=proposal.model_dump(mode="json"),
            decision_pack_refs=list(advisory_session["decision_pack_refs"]),
            updated_at=datetime.fromisoformat("2026-04-16T21:40:00+08:00"),
        )

    apply_response = client.post(
        "/api/v1/commands/board-advisory-apply-patch",
        json={
            "session_id": advisory_session["session_id"],
            "proposal_ref": proposal.proposal_ref,
            "idempotency_key": f"board-advisory-apply:{advisory_session['session_id']}:review-lane",
        },
    )

    updated = repository.get_approval_by_review_pack_id(approval["review_pack_id"])
    advisory_session = repository.get_board_advisory_session_for_approval(approval["approval_id"])

    assert apply_response.status_code == 200
    assert apply_response.json()["status"] == "REJECTED"
    assert "review lane" in str(apply_response.json()["reason"] or "").lower()
    assert updated["status"] == APPROVAL_STATUS_OPEN
    assert advisory_session is not None
    assert advisory_session["status"] == "PENDING_BOARD_CONFIRMATION"
    assert advisory_session["approved_patch_ref"] is None


def test_board_advisory_full_timeline_archive_materializes_versions_and_surfaces_latest_refs(client):
    workflow_id = "wf_advisory_full_timeline_archive"
    _ensure_scoped_workflow(
        client,
        workflow_id=workflow_id,
        tenant_id="tenant_default",
        workspace_id="ws_default",
        goal="Materialize advisory transcript archives for FULL_TIMELINE governance.",
    )
    approval = _seed_review_request(client, workflow_id=workflow_id)
    repository = client.app.state.repository

    with _suppress_ceo_shadow_side_effects():
        enter_response = client.post(
            "/api/v1/commands/modify-constraints",
            json={
                "review_pack_id": approval["review_pack_id"],
                "review_pack_version": approval["review_pack_version"],
                "command_target_version": approval["command_target_version"],
                "approval_id": approval["approval_id"],
                "constraint_patch": {
                    "add_rules": ["Keep a full advisory transcript for every change-flow step."],
                    "remove_rules": [],
                    "replace_rules": [],
                },
                "governance_patch": {
                    "audit_mode": "FULL_TIMELINE",
                },
                "board_comment": "Archive every advisory turn before runtime import.",
                "idempotency_key": f"board-modify:{approval['approval_id']}:full-timeline",
            },
        )
    assert enter_response.status_code == 200
    assert enter_response.json()["status"] == "ACCEPTED"

    advisory_session = repository.get_board_advisory_session_for_approval(approval["approval_id"])
    assert advisory_session is not None
    session_id = str(advisory_session["session_id"])
    expected_v1_timeline_ref = f"pa://timeline-index/{session_id}@1"
    expected_v1_transcript_artifact_ref = f"art://board-advisory/{workflow_id}/{session_id}/transcript-v1.json"
    expected_v1_timeline_artifact_ref = f"art://board-advisory/{workflow_id}/{session_id}/timeline-index-v1.json"

    assert advisory_session["timeline_archive_version_int"] == 1
    assert advisory_session["latest_timeline_index_ref"] == expected_v1_timeline_ref
    assert advisory_session["latest_transcript_archive_artifact_ref"] == expected_v1_transcript_artifact_ref
    assert repository.get_artifact_by_ref(expected_v1_transcript_artifact_ref) is not None
    assert repository.get_artifact_by_ref(expected_v1_timeline_artifact_ref) is not None

    append_response = client.post(
        "/api/v1/commands/board-advisory-append-turn",
        json={
            "session_id": session_id,
            "actor_type": "board",
            "content": "Capture the trade-offs before you suggest the next patch.",
            "idempotency_key": f"board-advisory-turn:{session_id}:full-timeline-v2",
        },
    )
    assert append_response.status_code == 200
    assert append_response.json()["status"] == "ACCEPTED"

    advisory_session = repository.get_board_advisory_session_for_approval(approval["approval_id"])
    assert advisory_session is not None
    expected_v2_timeline_ref = f"pa://timeline-index/{session_id}@2"
    expected_v2_transcript_artifact_ref = f"art://board-advisory/{workflow_id}/{session_id}/transcript-v2.json"

    assert advisory_session["timeline_archive_version_int"] == 2
    assert advisory_session["latest_timeline_index_ref"] == expected_v2_timeline_ref
    assert advisory_session["latest_transcript_archive_artifact_ref"] == expected_v2_transcript_artifact_ref
    assert repository.get_artifact_by_ref(expected_v1_transcript_artifact_ref) is not None
    assert repository.get_artifact_by_ref(expected_v2_transcript_artifact_ref) is not None

    analysis_response = client.post(
        "/api/v1/commands/board-advisory-request-analysis",
        json={
            "session_id": session_id,
            "idempotency_key": f"board-advisory-analysis:{session_id}:full-timeline-v3",
        },
    )
    assert analysis_response.status_code == 200
    assert analysis_response.json()["status"] == "ACCEPTED"

    advisory_session = repository.get_board_advisory_session_for_approval(approval["approval_id"])
    assert advisory_session is not None
    assert advisory_session["timeline_archive_version_int"] == 3
    assert advisory_session["latest_timeline_index_ref"] == f"pa://timeline-index/{session_id}@3"

    apply_response = client.post(
        "/api/v1/commands/board-advisory-apply-patch",
        json={
            "session_id": session_id,
            "proposal_ref": advisory_session["latest_patch_proposal_ref"],
            "idempotency_key": f"board-advisory-apply:{session_id}:full-timeline-v4",
        },
    )
    assert apply_response.status_code == 200
    assert apply_response.json()["status"] == "ACCEPTED"

    advisory_session = repository.get_board_advisory_session_for_approval(approval["approval_id"])
    review_room = client.get(f"/api/v1/projections/review-room/{approval['review_pack_id']}")

    assert advisory_session is not None
    assert advisory_session["timeline_archive_version_int"] == 4
    assert advisory_session["latest_timeline_index_ref"] == f"pa://timeline-index/{session_id}@4"
    assert advisory_session["latest_transcript_archive_artifact_ref"] == (
        f"art://board-advisory/{workflow_id}/{session_id}/transcript-v4.json"
    )
    assert review_room.status_code == 200
    advisory_context = review_room.json()["data"]["review_pack"]["advisory_context"]
    assert advisory_context["timeline_archive_version_int"] == 4
    assert advisory_context["latest_timeline_index_ref"] == f"pa://timeline-index/{session_id}@4"
    assert advisory_context["latest_transcript_archive_artifact_ref"] == (
        f"art://board-advisory/{workflow_id}/{session_id}/transcript-v4.json"
    )


def test_board_advisory_full_timeline_archive_failure_rejects_without_advancing_state(client):
    workflow_id = "wf_advisory_full_timeline_archive_failure"
    _ensure_scoped_workflow(
        client,
        workflow_id=workflow_id,
        tenant_id="tenant_default",
        workspace_id="ws_default",
        goal="Reject advisory updates when FULL_TIMELINE archive materialization fails.",
    )
    approval = _seed_review_request(client, workflow_id=workflow_id)
    repository = client.app.state.repository

    with _suppress_ceo_shadow_side_effects():
        enter_response = client.post(
            "/api/v1/commands/modify-constraints",
            json={
                "review_pack_id": approval["review_pack_id"],
                "review_pack_version": approval["review_pack_version"],
                "command_target_version": approval["command_target_version"],
                "approval_id": approval["approval_id"],
                "constraint_patch": {
                    "add_rules": ["Keep the archive step explicit."],
                    "remove_rules": [],
                    "replace_rules": [],
                },
                "governance_patch": {
                    "audit_mode": "FULL_TIMELINE",
                },
                "board_comment": "The archive must succeed before the next advisory step is accepted.",
                "idempotency_key": f"board-modify:{approval['approval_id']}:full-timeline-failure-enter",
            },
        )
    assert enter_response.status_code == 200
    assert enter_response.json()["status"] == "ACCEPTED"

    advisory_session = repository.get_board_advisory_session_for_approval(approval["approval_id"])
    assert advisory_session is not None
    version_before = advisory_session["timeline_archive_version_int"]
    turn_count_before = len(advisory_session["working_turns"])

    with patch(
        "app.core.approval_handlers._materialize_board_advisory_full_timeline_archive",
        side_effect=RuntimeError("simulated full timeline archive failure"),
    ):
        append_response = client.post(
            "/api/v1/commands/board-advisory-append-turn",
            json={
                "session_id": advisory_session["session_id"],
                "actor_type": "board",
                "content": "This draft note should be rejected because archive materialization failed.",
                "idempotency_key": f"board-advisory-turn:{advisory_session['session_id']}:full-timeline-failure",
            },
        )

    advisory_session = repository.get_board_advisory_session_for_approval(approval["approval_id"])
    assert append_response.status_code == 200
    assert append_response.json()["status"] == "REJECTED"
    assert "archive" in str(append_response.json()["reason"] or "").lower()
    assert advisory_session is not None
    assert advisory_session["status"] == "DRAFTING"
    assert advisory_session["timeline_archive_version_int"] == version_before
    assert len(advisory_session["working_turns"]) == turn_count_before


def test_board_approve_dismisses_linked_board_advisory_session(client):
    workflow_id = "wf_board_advisory_dismissed"
    approval = _seed_review_request(client, workflow_id=workflow_id)
    repository = client.app.state.repository
    session_before = repository.get_board_advisory_session_for_approval(approval["approval_id"])
    assert session_before is not None
    assert session_before["status"] == "OPEN"

    response = _approve_open_review(client, approval, idempotency_suffix="dismiss-advisory")

    session_after = repository.get_board_advisory_session_for_approval(approval["approval_id"])
    assert response.status_code == 200
    assert response.json()["status"] == "ACCEPTED"
    assert session_after is not None
    assert session_after["session_id"] == session_before["session_id"]
    assert session_after["status"] == "DISMISSED"
    assert session_after["decision_pack_refs"] == []
    assert session_after["approved_patch_ref"] is None
    assert session_after["board_decision"] is None


def test_modify_constraints_rejects_invalid_governance_patch(client):
    approval = _seed_review_request(client, workflow_id="wf_invalid_governance_patch")
    repository = client.app.state.repository

    response = client.post(
        "/api/v1/commands/modify-constraints",
        json={
            "review_pack_id": approval["review_pack_id"],
            "review_pack_version": approval["review_pack_version"],
            "command_target_version": approval["command_target_version"],
            "approval_id": approval["approval_id"],
            "constraint_patch": {
                "add_rules": ["Do not continue until governance is corrected."],
                "remove_rules": [],
                "replace_rules": [],
            },
            "governance_patch": {
                "approval_mode": "AUTO_CEO",
                "audit_mode": "INVALID_AUDIT_MODE",
            },
            "board_comment": "This governance patch is intentionally invalid.",
            "idempotency_key": f"board-modify:{approval['approval_id']}:invalid-governance",
        },
    )

    updated = repository.get_approval_by_review_pack_id(approval["review_pack_id"])
    advisory_session = repository.get_board_advisory_session_for_approval(approval["approval_id"])
    latest_profile = repository.get_latest_governance_profile("wf_invalid_governance_patch")

    assert response.status_code == 200
    assert response.json()["status"] == "REJECTED"
    assert "audit_mode" in str(response.json()["reason"] or "")
    assert updated["status"] == APPROVAL_STATUS_OPEN
    assert advisory_session is not None
    assert advisory_session["status"] == "OPEN"
    assert advisory_session["decision_pack_refs"] == []
    assert advisory_session["approved_patch_ref"] is None
    assert latest_profile is not None
    assert latest_profile["approval_mode"] == "AUTO_CEO"
    assert latest_profile["audit_mode"] == "MINIMAL"


def test_stale_board_command_is_rejected_without_resolving_approval(client):
    approval = _seed_review_request(client, workflow_id="wf_stale")

    response = client.post(
        "/api/v1/commands/board-approve",
        json={
            "review_pack_id": approval["review_pack_id"],
            "review_pack_version": approval["review_pack_version"] + 1,
            "command_target_version": approval["command_target_version"],
            "approval_id": approval["approval_id"],
            "selected_option_id": "option_a",
            "board_comment": "Proceed with option A.",
            "idempotency_key": f"board-approve:{approval['approval_id']}:stale",
        },
    )

    updated = client.app.state.repository.get_approval_by_review_pack_id(approval["review_pack_id"])
    assert response.status_code == 200
    assert response.json()["status"] == "REJECTED"
    assert updated["status"] == APPROVAL_STATUS_OPEN
    assert client.app.state.repository.count_events_by_type(EVENT_BOARD_REVIEW_APPROVED) == 0


def test_ticket_create_is_rejected_when_node_is_blocked_for_board_review(client):
    _seed_review_request(client)

    response = client.post(
        "/api/v1/commands/ticket-create",
        json=_ticket_create_payload(ticket_id="tkt_visual_002"),
    )

    assert response.status_code == 200
    assert response.json()["status"] == "REJECTED"
    assert "BLOCKED_FOR_BOARD_REVIEW" in response.json()["reason"]


def test_ticket_create_is_rejected_when_node_is_completed(client):
    _create_lease_and_start_ticket(client)
    client.post("/api/v1/commands/ticket-complete", json=_ticket_complete_payload(include_review_request=False))

    response = client.post(
        "/api/v1/commands/ticket-create",
        json=_ticket_create_payload(ticket_id="tkt_visual_002"),
    )

    assert response.status_code == 200
    assert response.json()["status"] == "REJECTED"
    assert "COMPLETED" in response.json()["reason"]


def test_ticket_complete_is_allowed_after_rework_required(client):
    approval = _seed_review_request(client, workflow_id="wf_rework")
    reject_response = client.post(
        "/api/v1/commands/board-reject",
        json={
            "review_pack_id": approval["review_pack_id"],
            "review_pack_version": approval["review_pack_version"],
            "command_target_version": approval["command_target_version"],
            "approval_id": approval["approval_id"],
            "board_comment": "Current direction is too weak.",
            "rejection_reasons": ["visual_impact_insufficient"],
            "idempotency_key": f"board-reject:{approval['approval_id']}:rework",
        },
    )
    assert reject_response.json()["status"] == "ACCEPTED"

    _create_lease_and_start_ticket(
        client,
        workflow_id="wf_rework",
        ticket_id="tkt_visual_002",
        attempt_no=2,
    )
    response = client.post(
        "/api/v1/commands/ticket-complete",
        json=_ticket_complete_payload(
            workflow_id="wf_rework",
            ticket_id="tkt_visual_002",
            include_review_request=False,
        ),
    )
    node_projection = client.app.state.repository.get_current_node_projection(
        "wf_rework",
        "node_homepage_visual",
    )

    assert response.status_code == 200
    assert response.json()["status"] == "ACCEPTED"
    assert node_projection["latest_ticket_id"] == "tkt_visual_002"
    assert node_projection["status"] == NODE_STATUS_COMPLETED


def test_board_command_is_rejected_when_projection_is_not_currently_blocked(client):
    approval = _seed_review_request(client, workflow_id="wf_guard")
    repository = client.app.state.repository
    subject = (((approval.get("payload") or {}).get("review_pack") or {}).get("subject") or {})
    source_ticket_id = str(subject.get("source_ticket_id") or "").strip()
    source_graph_node_id = str(subject.get("source_graph_node_id") or "").strip()

    with repository.transaction() as connection:
        connection.execute(
            "UPDATE ticket_projection SET status = ?, blocking_reason_code = NULL WHERE ticket_id = ?",
            (TICKET_STATUS_COMPLETED, source_ticket_id),
        )
        connection.execute(
            """
            UPDATE runtime_node_projection
            SET status = ?, blocking_reason_code = NULL
            WHERE workflow_id = ? AND graph_node_id = ?
            """,
            (NODE_STATUS_COMPLETED, "wf_guard", source_graph_node_id),
        )

    response = client.post(
        "/api/v1/commands/board-approve",
        json={
            "review_pack_id": approval["review_pack_id"],
            "review_pack_version": approval["review_pack_version"],
            "command_target_version": approval["command_target_version"],
            "approval_id": approval["approval_id"],
            "selected_option_id": "option_a",
            "board_comment": "Proceed with option A.",
            "idempotency_key": f"board-approve:{approval['approval_id']}:projection-guard",
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "REJECTED"
    assert "blocked for board review" in response.json()["reason"].lower()


def test_board_command_rejects_when_runtime_projection_is_not_currently_blocked(client):
    workflow_id = "wf_guard_runtime_projection"
    approval = _seed_review_request(client, workflow_id=workflow_id)
    repository = client.app.state.repository
    subject = (((approval.get("payload") or {}).get("review_pack") or {}).get("subject") or {})

    assert str(subject.get("source_graph_node_id") or "").strip() == "node_homepage_visual::review"

    with repository.transaction() as connection:
        connection.execute(
            """
            UPDATE runtime_node_projection
            SET status = ?, blocking_reason_code = NULL
            WHERE workflow_id = ? AND graph_node_id = ?
            """,
            (NODE_STATUS_COMPLETED, workflow_id, "node_homepage_visual::review"),
        )

    response = client.post(
        "/api/v1/commands/board-approve",
        json={
            "review_pack_id": approval["review_pack_id"],
            "review_pack_version": approval["review_pack_version"],
            "command_target_version": approval["command_target_version"],
            "approval_id": approval["approval_id"],
            "selected_option_id": "option_a",
            "board_comment": "Proceed with option A.",
            "idempotency_key": f"board-approve:{approval['approval_id']}:runtime-projection-guard",
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "REJECTED"
    assert "blocked for board review" in response.json()["reason"].lower()


def test_event_stream_returns_incremental_events_after_cursor(client):
    client.post("/api/v1/commands/project-init", json=_project_init_payload("Ship MVP A"))
    initial_cursor = client.get("/api/v1/projections/dashboard").json()["cursor"]

    client.post("/api/v1/commands/project-init", json=_project_init_payload("Ship MVP B"))

    with client.stream("GET", f"/api/v1/events/stream?after={initial_cursor}") as response:
        body = "".join(response.iter_text())

    assert response.status_code == 200
    assert "BOARD_DIRECTIVE_RECEIVED" in body
    assert "WORKFLOW_CREATED" in body
    assert "event: heartbeat" in body


def test_ticket_complete_stream_carries_ticket_and_review_events(client):
    initial_cursor = client.get("/api/v1/projections/dashboard").json()["cursor"]
    _seed_review_request(client)

    with client.stream("GET", f"/api/v1/events/stream?after={initial_cursor}") as response:
        body = "".join(response.iter_text())

    assert response.status_code == 200
    assert "TICKET_CREATED" in body
    assert "TICKET_LEASED" in body
    assert "TICKET_STARTED" in body
    assert "TICKET_COMPLETED" in body
    assert "BOARD_REVIEW_REQUIRED" in body
    assert "tkt_visual_001" in body
    assert "node_homepage_visual" in body


def test_ticket_fail_and_retry_stream_carries_failure_events(client, set_ticket_time):
    initial_cursor = client.get("/api/v1/projections/dashboard").json()["cursor"]
    set_ticket_time("2026-03-28T10:00:00+08:00")
    _create_lease_and_start_ticket(client)
    client.post(
        "/api/v1/commands/ticket-fail",
        json=_ticket_fail_payload(failure_kind="SCHEMA_ERROR"),
    )

    with client.stream("GET", f"/api/v1/events/stream?after={initial_cursor}") as response:
        body = "".join(response.iter_text())

    assert response.status_code == 200
    assert "TICKET_FAILED" in body
    assert "TICKET_RETRY_SCHEDULED" in body


def test_scheduler_timeout_stream_carries_timeout_events(client, set_ticket_time):
    initial_cursor = client.get("/api/v1/projections/dashboard").json()["cursor"]
    set_ticket_time("2026-03-28T10:00:00+08:00")
    _create_lease_and_start_ticket(client, retry_budget=1)

    set_ticket_time("2026-03-28T10:31:00+08:00")
    client.post("/api/v1/commands/scheduler-tick", json=_scheduler_tick_payload(idempotency_key="scheduler-tick:stream"))

    with client.stream("GET", f"/api/v1/events/stream?after={initial_cursor}") as response:
        body = "".join(response.iter_text())

    assert response.status_code == 200
    assert "TICKET_TIMED_OUT" in body
    assert "TICKET_RETRY_SCHEDULED" in body


def test_timeout_incident_stream_carries_incident_and_breaker_events(client, set_ticket_time):
    initial_cursor = client.get("/api/v1/projections/dashboard").json()["cursor"]
    set_ticket_time("2026-03-28T10:00:00+08:00")
    _create_lease_and_start_ticket(client, retry_budget=2)

    set_ticket_time("2026-03-28T10:31:00+08:00")
    client.post(
        "/api/v1/commands/scheduler-tick",
        json=_scheduler_tick_payload(idempotency_key="scheduler-tick:stream-incident-first"),
    )

    repository = client.app.state.repository
    retried_ticket_id = repository.get_current_node_projection("wf_seed", "node_homepage_visual")["latest_ticket_id"]

    set_ticket_time("2026-03-28T10:32:00+08:00")
    client.post(
        "/api/v1/commands/ticket-start",
        json=_ticket_start_payload(ticket_id=retried_ticket_id),
    )

    set_ticket_time("2026-03-28T11:18:00+08:00")
    client.post(
        "/api/v1/commands/scheduler-tick",
        json=_scheduler_tick_payload(idempotency_key="scheduler-tick:stream-incident-second"),
    )

    with client.stream("GET", f"/api/v1/events/stream?after={initial_cursor}") as response:
        body = "".join(response.iter_text())

    assert response.status_code == 200
    assert "INCIDENT_OPENED" in body
    assert "CIRCUIT_BREAKER_OPENED" in body


def test_incident_resolve_stream_carries_breaker_closed_and_incident_closed_events(client, set_ticket_time):
    initial_cursor = client.get("/api/v1/projections/dashboard").json()["cursor"]
    set_ticket_time("2026-03-28T10:00:00+08:00")
    _create_lease_and_start_ticket(client, retry_budget=2)

    set_ticket_time("2026-03-28T10:31:00+08:00")
    client.post(
        "/api/v1/commands/scheduler-tick",
        json=_scheduler_tick_payload(idempotency_key="scheduler-tick:close-stream-first"),
    )

    repository = client.app.state.repository
    retried_ticket_id = repository.get_current_node_projection("wf_seed", "node_homepage_visual")["latest_ticket_id"]

    set_ticket_time("2026-03-28T10:32:00+08:00")
    client.post(
        "/api/v1/commands/ticket-start",
        json=_ticket_start_payload(ticket_id=retried_ticket_id),
    )

    set_ticket_time("2026-03-28T11:18:00+08:00")
    client.post(
        "/api/v1/commands/scheduler-tick",
        json=_scheduler_tick_payload(idempotency_key="scheduler-tick:close-stream-second"),
    )

    incident_id = [
        event["payload"]["incident_id"]
        for event in repository.list_events_for_testing()
        if event["event_type"] == EVENT_INCIDENT_OPENED
    ][0]

    set_ticket_time("2026-03-28T11:20:00+08:00")
    client.post(
        "/api/v1/commands/incident-resolve",
        json=_incident_resolve_payload(incident_id, idempotency_key="incident-resolve:stream"),
    )

    with client.stream("GET", f"/api/v1/events/stream?after={initial_cursor}") as response:
        body = "".join(response.iter_text())

    assert response.status_code == 200
    assert "CIRCUIT_BREAKER_CLOSED" in body
    assert "INCIDENT_RECOVERY_STARTED" in body


def test_invalid_project_init_returns_422_without_writing_events(client):
    response = client.post(
        "/api/v1/commands/project-init",
        json={
            "north_star_goal": "",
            "hard_constraints": [],
            "budget_cap": -1,
            "deadline_at": None,
        },
    )

    repository = client.app.state.repository
    assert response.status_code == 422
    assert repository.count_events_by_type(EVENT_SYSTEM_INITIALIZED) == 1
    assert repository.count_events_by_type(EVENT_WORKFLOW_CREATED) == 0


def test_ticket_complete_review_request_emits_required_event(client):
    _seed_review_request(client, workflow_id="wf_event")

    assert client.app.state.repository.count_events_by_type(EVENT_TICKET_COMPLETED) == 2
    assert client.app.state.repository.count_events_by_type(EVENT_BOARD_REVIEW_REQUIRED) == 1


def test_worker_runtime_projection_requires_scope_pair(client):
    response = client.get("/api/v1/projections/worker-runtime?tenant_id=tenant_default")

    assert response.status_code == 400


def test_worker_admin_bindings_requires_scope_pair(client):
    response = client.get(
        "/api/v1/worker-admin/bindings?tenant_id=tenant_default",
        headers=_worker_admin_headers(),
    )

    assert response.status_code == 400


def test_worker_admin_requires_operator_headers(client):
    response = client.get(
        "/api/v1/worker-admin/bindings",
        params={
            "worker_id": "emp_frontend_2",
            "tenant_id": "tenant_default",
            "workspace_id": "ws_default",
        },
    )

    assert response.status_code == 401


def test_worker_admin_rejects_legacy_headers_without_signed_token(client):
    response = client.get(
        "/api/v1/worker-admin/bindings",
        params={
            "worker_id": "emp_frontend_2",
            "tenant_id": "tenant_default",
            "workspace_id": "ws_default",
        },
        headers=_legacy_worker_admin_headers(),
    )

    assert response.status_code == 401
    assert "X-Boardroom-Operator-Token" in response.json()["detail"]


def test_worker_admin_rejects_mismatched_assertion_headers_against_signed_token(client):
    response = client.get(
        "/api/v1/worker-admin/bindings",
        params={
            "worker_id": "emp_frontend_2",
            "tenant_id": "tenant_default",
            "workspace_id": "ws_default",
        },
        headers=_worker_admin_headers(asserted_operator_id="other@example.com"),
    )

    assert response.status_code == 400


def test_worker_admin_accepts_token_only_without_legacy_assertion_headers(client):
    response = client.get(
        "/api/v1/worker-admin/bindings",
        params={
            "worker_id": "emp_frontend_2",
            "tenant_id": "tenant_default",
            "workspace_id": "ws_default",
        },
        headers=_worker_admin_headers(include_assertion_headers=False),
    )

    assert response.status_code == 200


def test_worker_admin_revoke_session_requires_session_id_or_complete_scope(client):
    response = client.post(
        "/api/v1/worker-admin/revoke-session",
        json={"worker_id": "emp_frontend_2"},
        headers=_worker_admin_headers(),
    )

    assert response.status_code == 400


def test_worker_admin_scope_viewer_reads_own_scope_only_and_cannot_write(client):
    scope_headers = _worker_admin_headers(
        operator_id="tenant.viewer@example.com",
        role="scope_viewer",
        tenant_id="tenant_default",
        workspace_id="ws_default",
    )

    own_scope_response = client.get(
        "/api/v1/worker-admin/scope-summary",
        params={"tenant_id": "tenant_default", "workspace_id": "ws_default"},
        headers=scope_headers,
    )
    missing_scope_response = client.get(
        "/api/v1/worker-admin/bindings",
        params={"worker_id": "emp_frontend_2"},
        headers=scope_headers,
    )
    other_scope_response = client.get(
        "/api/v1/worker-admin/scope-summary",
        params={"tenant_id": "tenant_blue", "workspace_id": "ws_design"},
        headers=scope_headers,
    )
    write_response = client.post(
        "/api/v1/worker-admin/create-binding",
        json={
            "worker_id": "emp_frontend_2",
            "tenant_id": "tenant_default",
            "workspace_id": "ws_default",
        },
        headers=scope_headers,
    )

    assert own_scope_response.status_code == 200
    assert missing_scope_response.status_code == 403
    assert other_scope_response.status_code == 403
    assert write_response.status_code == 403


def test_worker_admin_scope_admin_requires_explicit_scope_and_rejects_mismatched_issued_by(
    client,
    monkeypatch,
):
    monkeypatch.setenv("BOARDROOM_OS_WORKER_BOOTSTRAP_SIGNING_SECRET", "bootstrap-secret")
    scope_headers = _worker_admin_headers(
        operator_id="tenant.admin@example.com",
        role="scope_admin",
        tenant_id="tenant_blue",
        workspace_id="ws_design",
    )

    missing_scope_response = client.post(
        "/api/v1/worker-admin/issue-bootstrap",
        json={"worker_id": "emp_frontend_2", "ttl_sec": 120},
        headers=scope_headers,
    )
    mismatched_actor_response = client.post(
        "/api/v1/worker-admin/issue-bootstrap",
        json={
            "worker_id": "emp_frontend_2",
            "tenant_id": "tenant_blue",
            "workspace_id": "ws_design",
            "ttl_sec": 120,
            "issued_by": "other@example.com",
        },
        headers=scope_headers,
    )
    success_response = client.post(
        "/api/v1/worker-admin/issue-bootstrap",
        json={
            "worker_id": "emp_frontend_2",
            "tenant_id": "tenant_blue",
            "workspace_id": "ws_design",
            "ttl_sec": 120,
            "reason": "tenant scope bootstrap",
        },
        headers=scope_headers,
    )

    assert missing_scope_response.status_code == 403
    assert mismatched_actor_response.status_code == 400
    assert success_response.status_code == 200
    assert success_response.json()["issued_by"] == "tenant.admin@example.com"


def test_worker_admin_scope_admin_cannot_revoke_foreign_session_or_grant(
    client,
    set_ticket_time,
    monkeypatch,
):
    monkeypatch.setenv("BOARDROOM_OS_WORKER_BOOTSTRAP_SIGNING_SECRET", "bootstrap-secret")
    monkeypatch.setenv("BOARDROOM_OS_WORKER_SESSION_TTL_SEC", "600")
    monkeypatch.setenv("BOARDROOM_OS_WORKER_DELIVERY_SIGNING_SECRET", "delivery-secret")

    set_ticket_time("2026-03-28T10:00:00+08:00")
    _seed_input_artifact(client)
    _create_and_lease_ticket(
        client,
        workflow_id="wf_worker_admin_scope_permission",
        ticket_id="tkt_worker_admin_scope_permission",
        node_id="node_worker_admin_scope_permission",
    )

    issue_response = client.post(
        "/api/v1/worker-admin/issue-bootstrap",
        json={"worker_id": "emp_frontend_2", "ttl_sec": 120},
        headers=_worker_admin_headers(),
    )
    assert issue_response.status_code == 200
    assignments_data, execution_package = _bootstrap_worker_execution_package(
        client,
        issue_response.json()["bootstrap_token"],
    )
    preview_url = execution_package["compiled_execution_package"]["atomic_context_bundle"]["context_blocks"][0][
        "content_payload"
    ]["preview_url"]
    preview_grant_id = _decode_worker_delivery_token_payload(
        _query_value(preview_url, "access_token") or ""
    )["grant_id"]
    scope_headers = _worker_admin_headers(
        operator_id="tenant.admin@example.com",
        role="scope_admin",
        tenant_id="tenant_blue",
        workspace_id="ws_design",
    )

    revoke_session_response = client.post(
        "/api/v1/worker-admin/revoke-session",
        json={
            "session_id": assignments_data["session_id"],
            "revoked_by": "tenant.admin@example.com",
            "reason": "cross scope revoke",
        },
        headers=scope_headers,
    )
    revoke_grant_response = client.post(
        "/api/v1/worker-admin/revoke-delivery-grant",
        json={
            "grant_id": preview_grant_id,
            "revoked_by": "tenant.admin@example.com",
            "reason": "cross scope revoke",
        },
        headers=scope_headers,
    )

    assert revoke_session_response.status_code == 403
    assert revoke_grant_response.status_code == 403


def test_worker_admin_revoke_session_rejects_mismatched_revoked_by_header(
    client,
    set_ticket_time,
    monkeypatch,
):
    monkeypatch.setenv("BOARDROOM_OS_WORKER_BOOTSTRAP_SIGNING_SECRET", "bootstrap-secret")
    monkeypatch.setenv("BOARDROOM_OS_WORKER_SESSION_TTL_SEC", "600")

    set_ticket_time("2026-03-28T10:00:00+08:00")
    _create_and_lease_ticket(
        client,
        workflow_id="wf_worker_admin_actor_mismatch",
        ticket_id="tkt_worker_admin_actor_mismatch",
        node_id="node_worker_admin_actor_mismatch",
    )

    issue_response = client.post(
        "/api/v1/worker-admin/issue-bootstrap",
        json={"worker_id": "emp_frontend_2", "ttl_sec": 120},
        headers=_worker_admin_headers(),
    )
    assert issue_response.status_code == 200
    assignments_data = client.get(
        "/api/v1/worker-runtime/assignments",
        headers={"X-Boardroom-Worker-Bootstrap": issue_response.json()["bootstrap_token"]},
    ).json()["data"]

    revoke_response = client.post(
        "/api/v1/worker-admin/revoke-session",
        json={
            "session_id": assignments_data["session_id"],
            "revoked_by": "other@example.com",
            "reason": "actor mismatch",
        },
        headers=_worker_admin_headers(),
    )

    assert revoke_response.status_code == 400


def test_worker_admin_bindings_returns_scope_filtered_bindings(
    client,
    monkeypatch,
    capsys,
):
    monkeypatch.setenv("BOARDROOM_OS_WORKER_BOOTSTRAP_SIGNING_SECRET", "bootstrap-secret")

    from app.worker_auth_cli import main

    assert main(["issue-bootstrap", "--worker-id", "emp_frontend_2"]) == 0
    capsys.readouterr()
    assert (
        main(
            [
                "issue-bootstrap",
                "--worker-id",
                "emp_frontend_2",
                "--tenant-id",
                "tenant_blue",
                "--workspace-id",
                "ws_design",
            ]
        )
        == 0
    )
    capsys.readouterr()

    response = client.get(
        "/api/v1/worker-admin/bindings",
        params={
            "worker_id": "emp_frontend_2",
            "tenant_id": "tenant_blue",
            "workspace_id": "ws_design",
        },
        headers=_worker_admin_headers(),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 1
    assert data["bindings"][0]["worker_id"] == "emp_frontend_2"
    assert data["bindings"][0]["tenant_id"] == "tenant_blue"
    assert data["bindings"][0]["workspace_id"] == "ws_design"


def test_worker_admin_sessions_returns_scope_filtered_active_sessions(
    client,
    set_ticket_time,
    monkeypatch,
):
    monkeypatch.setenv("BOARDROOM_OS_WORKER_BOOTSTRAP_SIGNING_SECRET", "bootstrap-secret")
    monkeypatch.setenv("BOARDROOM_OS_WORKER_SESSION_TTL_SEC", "600")

    repository = client.app.state.repository
    with repository.transaction() as connection:
        repository.ensure_worker_bootstrap_state(
            connection,
            worker_id="emp_frontend_2",
            tenant_id="tenant_default",
            workspace_id="ws_default",
            at=datetime.fromisoformat("2026-03-28T10:00:00+08:00"),
        )
        repository.ensure_worker_bootstrap_state(
            connection,
            worker_id="emp_frontend_2",
            tenant_id="tenant_blue",
            workspace_id="ws_design",
            at=datetime.fromisoformat("2026-03-28T10:00:00+08:00"),
        )

    set_ticket_time("2026-03-28T10:00:00+08:00")
    _create_and_lease_ticket(
        client,
        workflow_id="wf_worker_admin_sessions_default",
        ticket_id="tkt_worker_admin_sessions_default",
        node_id="node_worker_admin_sessions_default",
    )
    _create_and_lease_ticket(
        client,
        workflow_id="wf_worker_admin_sessions_blue",
        ticket_id="tkt_worker_admin_sessions_blue",
        node_id="node_worker_admin_sessions_blue",
        tenant_id="tenant_blue",
        workspace_id="ws_design",
    )

    default_issue = client.post(
        "/api/v1/worker-admin/issue-bootstrap",
        json={
            "worker_id": "emp_frontend_2",
            "tenant_id": "tenant_default",
            "workspace_id": "ws_default",
            "ttl_sec": 120,
        },
        headers=_worker_admin_headers(),
    )
    blue_issue = client.post(
        "/api/v1/worker-admin/issue-bootstrap",
        json={
            "worker_id": "emp_frontend_2",
            "tenant_id": "tenant_blue",
            "workspace_id": "ws_design",
            "ttl_sec": 120,
        },
        headers=_worker_admin_headers(),
    )
    assert default_issue.status_code == 200
    assert blue_issue.status_code == 200

    default_assignments = client.get(
        "/api/v1/worker-runtime/assignments",
        headers={"X-Boardroom-Worker-Bootstrap": default_issue.json()["bootstrap_token"]},
    )
    blue_assignments = client.get(
        "/api/v1/worker-runtime/assignments",
        headers={"X-Boardroom-Worker-Bootstrap": blue_issue.json()["bootstrap_token"]},
    )
    assert default_assignments.status_code == 200
    assert blue_assignments.status_code == 200

    repository = client.app.state.repository
    with repository.transaction() as connection:
        connection.execute(
            """
            UPDATE worker_session
            SET revoked_at = ?, revoked_via = ?, revoke_reason = ?
            WHERE session_id = ?
            """,
            (
                "2026-03-28T10:02:00+08:00",
                "test",
                "inactive session for filtering",
                default_assignments.json()["data"]["session_id"],
            ),
        )

    response = client.get(
        "/api/v1/worker-admin/sessions",
        params={
            "worker_id": "emp_frontend_2",
            "tenant_id": "tenant_blue",
            "workspace_id": "ws_design",
            "active_only": "true",
        },
        headers=_worker_admin_headers(),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 1
    assert payload["sessions"][0]["worker_id"] == "emp_frontend_2"
    assert payload["sessions"][0]["tenant_id"] == "tenant_blue"
    assert payload["sessions"][0]["workspace_id"] == "ws_design"
    assert payload["sessions"][0]["is_active"] is True


def test_worker_admin_delivery_grants_supports_scope_and_ticket_filters(
    client,
    set_ticket_time,
    monkeypatch,
):
    monkeypatch.setenv("BOARDROOM_OS_WORKER_BOOTSTRAP_SIGNING_SECRET", "bootstrap-secret")
    monkeypatch.setenv("BOARDROOM_OS_WORKER_SESSION_TTL_SEC", "600")
    monkeypatch.setenv("BOARDROOM_OS_WORKER_DELIVERY_SIGNING_SECRET", "delivery-secret")

    set_ticket_time("2026-03-28T10:00:00+08:00")
    _seed_input_artifact(client)
    _create_and_lease_ticket(
        client,
        workflow_id="wf_worker_admin_grants_default",
        ticket_id="tkt_worker_admin_grants_default",
        node_id="node_worker_admin_grants_default",
    )
    _create_and_lease_ticket(
        client,
        workflow_id="wf_worker_admin_grants_blue",
        ticket_id="tkt_worker_admin_grants_blue",
        node_id="node_worker_admin_grants_blue",
        tenant_id="tenant_blue",
        workspace_id="ws_design",
    )

    default_issue = client.post(
        "/api/v1/worker-admin/issue-bootstrap",
        json={"worker_id": "emp_frontend_2", "ttl_sec": 120},
        headers=_worker_admin_headers(),
    )
    blue_issue = client.post(
        "/api/v1/worker-admin/issue-bootstrap",
        json={
            "worker_id": "emp_frontend_2",
            "tenant_id": "tenant_blue",
            "workspace_id": "ws_design",
            "ttl_sec": 120,
        },
        headers=_worker_admin_headers(),
    )
    assert default_issue.status_code == 200
    assert blue_issue.status_code == 200

    _bootstrap_worker_execution_package(client, default_issue.json()["bootstrap_token"])
    blue_assignments, _ = _bootstrap_worker_execution_package(client, blue_issue.json()["bootstrap_token"])

    response = client.get(
        "/api/v1/worker-admin/delivery-grants",
        params={
            "worker_id": "emp_frontend_2",
            "tenant_id": "tenant_blue",
            "workspace_id": "ws_design",
            "ticket_id": "tkt_worker_admin_grants_blue",
            "session_id": blue_assignments["session_id"],
            "active_only": "true",
        },
        headers=_worker_admin_headers(),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] > 0
    assert all(item["worker_id"] == "emp_frontend_2" for item in payload["delivery_grants"])
    assert all(item["tenant_id"] == "tenant_blue" for item in payload["delivery_grants"])
    assert all(item["workspace_id"] == "ws_design" for item in payload["delivery_grants"])
    assert all(item["ticket_id"] == "tkt_worker_admin_grants_blue" for item in payload["delivery_grants"])
    assert all(item["session_id"] == blue_assignments["session_id"] for item in payload["delivery_grants"])
    assert all(item["is_active"] is True for item in payload["delivery_grants"])


def test_worker_admin_auth_rejections_supports_scope_and_route_filters(
    client,
    set_ticket_time,
    monkeypatch,
):
    monkeypatch.setenv("BOARDROOM_OS_WORKER_BOOTSTRAP_SIGNING_SECRET", "bootstrap-secret")
    monkeypatch.setenv("BOARDROOM_OS_WORKER_SESSION_TTL_SEC", "600")

    set_ticket_time("2026-03-28T10:00:00+08:00")
    _create_and_lease_ticket(
        client,
        workflow_id="wf_worker_admin_rejections_blue",
        ticket_id="tkt_worker_admin_rejections_blue",
        node_id="node_worker_admin_rejections_blue",
        tenant_id="tenant_blue",
        workspace_id="ws_design",
    )

    issue_response = client.post(
        "/api/v1/worker-admin/issue-bootstrap",
        json={
            "worker_id": "emp_frontend_2",
            "tenant_id": "tenant_blue",
            "workspace_id": "ws_design",
            "ttl_sec": 120,
        },
        headers=_worker_admin_headers(),
    )
    assert issue_response.status_code == 200

    assignments_response = client.get(
        "/api/v1/worker-runtime/assignments",
        headers={"X-Boardroom-Worker-Bootstrap": issue_response.json()["bootstrap_token"]},
    )
    assert assignments_response.status_code == 200
    session_token = assignments_response.json()["data"]["session_token"]

    repository = client.app.state.repository
    with repository.transaction() as connection:
        connection.execute(
            """
            UPDATE ticket_projection
            SET workspace_id = ?
            WHERE ticket_id = ?
            """,
            ("ws_other", "tkt_worker_admin_rejections_blue"),
        )

    rejected_response = client.get(
        "/api/v1/worker-runtime/assignments",
        headers=_worker_session_headers(session_token),
    )
    assert rejected_response.status_code == 403

    response = client.get(
        "/api/v1/worker-admin/auth-rejections",
        params={
            "worker_id": "emp_frontend_2",
            "tenant_id": "tenant_blue",
            "workspace_id": "ws_design",
            "route_family": "assignments",
        },
        headers=_worker_admin_headers(),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 1
    assert payload["auth_rejections"][0]["route_family"] == "assignments"
    assert payload["auth_rejections"][0]["reason_code"] == "workspace_mismatch"
    assert payload["auth_rejections"][0]["tenant_id"] == "tenant_blue"
    assert payload["auth_rejections"][0]["workspace_id"] == "ws_design"


def test_worker_admin_scope_summary_aggregates_workers_within_scope(
    client,
    set_ticket_time,
    monkeypatch,
):
    monkeypatch.setenv("BOARDROOM_OS_WORKER_BOOTSTRAP_SIGNING_SECRET", "bootstrap-secret")
    monkeypatch.setenv("BOARDROOM_OS_WORKER_SESSION_TTL_SEC", "600")
    monkeypatch.setenv("BOARDROOM_OS_WORKER_DELIVERY_SIGNING_SECRET", "delivery-secret")

    _seed_worker(client, employee_id="emp_frontend_3")

    set_ticket_time("2026-03-28T10:00:00+08:00")
    _seed_input_artifact(client)
    _create_and_lease_ticket(
        client,
        workflow_id="wf_worker_admin_summary_2",
        ticket_id="tkt_worker_admin_summary_2",
        node_id="node_worker_admin_summary_2",
        leased_by="emp_frontend_2",
        tenant_id="tenant_blue",
        workspace_id="ws_design",
    )
    _create_and_lease_ticket(
        client,
        workflow_id="wf_worker_admin_summary_3",
        ticket_id="tkt_worker_admin_summary_3",
        node_id="node_worker_admin_summary_3",
        leased_by="emp_frontend_3",
        tenant_id="tenant_blue",
        workspace_id="ws_design",
    )

    issue_worker_2 = client.post(
        "/api/v1/worker-admin/issue-bootstrap",
        json={
            "worker_id": "emp_frontend_2",
            "tenant_id": "tenant_blue",
            "workspace_id": "ws_design",
            "ttl_sec": 120,
            "issued_by": "ops@example.com",
        },
        headers=_worker_admin_headers(),
    )
    issue_worker_3 = client.post(
        "/api/v1/worker-admin/issue-bootstrap",
        json={
            "worker_id": "emp_frontend_3",
            "tenant_id": "tenant_blue",
            "workspace_id": "ws_design",
            "ttl_sec": 120,
            "issued_by": "ops@example.com",
        },
        headers=_worker_admin_headers(),
    )
    assert issue_worker_2.status_code == 200
    assert issue_worker_3.status_code == 200

    worker_2_assignments, _ = _bootstrap_worker_execution_package(client, issue_worker_2.json()["bootstrap_token"])
    client.get(
        "/api/v1/worker-runtime/assignments",
        headers={"X-Boardroom-Worker-Bootstrap": issue_worker_3.json()["bootstrap_token"]},
    )

    repository = client.app.state.repository
    with repository.transaction() as connection:
        connection.execute(
            """
            UPDATE ticket_projection
            SET workspace_id = ?
            WHERE ticket_id = ?
            """,
            ("ws_other", "tkt_worker_admin_summary_2"),
        )

    rejected_response = client.get(
        "/api/v1/worker-runtime/assignments",
        headers=_worker_session_headers(worker_2_assignments["session_token"]),
    )
    assert rejected_response.status_code == 403

    response = client.get(
        "/api/v1/worker-admin/scope-summary",
        params={
            "tenant_id": "tenant_blue",
            "workspace_id": "ws_design",
        },
        headers=_worker_admin_headers(),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["filters"]["tenant_id"] == "tenant_blue"
    assert payload["filters"]["workspace_id"] == "ws_design"
    assert payload["summary"]["binding_count"] == 2
    assert payload["summary"]["active_bootstrap_issue_count"] == 2
    assert payload["summary"]["active_session_count"] == 2
    assert payload["summary"]["active_delivery_grant_count"] > 0
    assert payload["summary"]["recent_rejection_count"] == 1
    assert payload["summary"]["active_ticket_count"] == 1
    assert {item["worker_id"] for item in payload["workers"]} == {"emp_frontend_2", "emp_frontend_3"}
    worker_2 = next(item for item in payload["workers"] if item["worker_id"] == "emp_frontend_2")
    assert worker_2["active_bootstrap_issue_count"] == 1
    assert worker_2["active_session_count"] == 1
    assert worker_2["active_ticket_count"] == 0
    assert worker_2["recent_rejection_count"] == 1


def test_worker_admin_contain_scope_dry_run_returns_targets_without_writing_state(
    client,
    set_ticket_time,
    monkeypatch,
):
    monkeypatch.setenv("BOARDROOM_OS_WORKER_BOOTSTRAP_SIGNING_SECRET", "bootstrap-secret")
    monkeypatch.setenv("BOARDROOM_OS_WORKER_SESSION_TTL_SEC", "600")
    monkeypatch.setenv("BOARDROOM_OS_WORKER_DELIVERY_SIGNING_SECRET", "delivery-secret")

    set_ticket_time("2026-03-28T10:00:00+08:00")
    _seed_input_artifact(client)
    _create_and_lease_ticket(
        client,
        workflow_id="wf_worker_admin_contain_dry_run",
        ticket_id="tkt_worker_admin_contain_dry_run",
        node_id="node_worker_admin_contain_dry_run",
        tenant_id="tenant_blue",
        workspace_id="ws_design",
    )

    issue_response = client.post(
        "/api/v1/worker-admin/issue-bootstrap",
        json={
            "worker_id": "emp_frontend_2",
            "tenant_id": "tenant_blue",
            "workspace_id": "ws_design",
            "ttl_sec": 120,
            "issued_by": "ops@example.com",
        },
        headers=_worker_admin_headers(),
    )
    assert issue_response.status_code == 200
    issued_payload = issue_response.json()
    assignments_data, execution_package = _bootstrap_worker_execution_package(
        client,
        issued_payload["bootstrap_token"],
    )
    preview_url = execution_package["compiled_execution_package"]["atomic_context_bundle"]["context_blocks"][0][
        "content_payload"
    ]["preview_url"]

    repository = client.app.state.repository
    with repository.connection() as connection:
        before_issue_count = len(
            repository.list_worker_bootstrap_issues(
                connection,
                worker_id="emp_frontend_2",
                tenant_id="tenant_blue",
                workspace_id="ws_design",
                active_only=True,
                at=datetime.fromisoformat("2026-03-28T10:00:00+08:00"),
            )
        )
        before_session_count = len(
            repository.list_worker_sessions(
                connection,
                worker_id="emp_frontend_2",
                tenant_id="tenant_blue",
                workspace_id="ws_design",
                active_only=True,
            )
        )
        before_grants = repository.list_worker_delivery_grants(
            connection,
            worker_id="emp_frontend_2",
            tenant_id="tenant_blue",
            workspace_id="ws_design",
            active_only=True,
        )

    response = client.post(
        "/api/v1/worker-admin/contain-scope",
        json={
            "tenant_id": "tenant_blue",
            "workspace_id": "ws_design",
            "dry_run": True,
            "revoke_bootstrap_issues": True,
            "revoke_sessions": True,
            "revoked_by": "ops@example.com",
            "reason": "Tenant incident containment.",
        },
        headers=_worker_admin_headers(),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["dry_run"] is True
    assert payload["executed"] is False
    assert payload["filters"]["tenant_id"] == "tenant_blue"
    assert payload["filters"]["workspace_id"] == "ws_design"
    assert payload["requested_actions"]["revoke_bootstrap_issues"] is True
    assert payload["requested_actions"]["revoke_sessions"] is True
    assert payload["impact_summary"]["active_bootstrap_issue_count"] == 1
    assert payload["impact_summary"]["active_session_count"] == 1
    assert payload["impact_summary"]["active_delivery_grant_count"] == len(before_grants)
    assert payload["target_ids"]["worker_ids"] == ["emp_frontend_2"]
    assert payload["target_ids"]["bootstrap_issue_ids"] == [issued_payload["issue_id"]]
    assert payload["target_ids"]["session_ids"] == [assignments_data["session_id"]]
    assert len(payload["target_ids"]["delivery_grant_ids"]) == len(before_grants)

    with repository.connection() as connection:
        after_issue_count = len(
            repository.list_worker_bootstrap_issues(
                connection,
                worker_id="emp_frontend_2",
                tenant_id="tenant_blue",
                workspace_id="ws_design",
                active_only=True,
                at=datetime.fromisoformat("2026-03-28T10:00:00+08:00"),
            )
        )
        after_session_count = len(
            repository.list_worker_sessions(
                connection,
                worker_id="emp_frontend_2",
                tenant_id="tenant_blue",
                workspace_id="ws_design",
                active_only=True,
            )
        )
        after_grants = repository.list_worker_delivery_grants(
            connection,
            worker_id="emp_frontend_2",
            tenant_id="tenant_blue",
            workspace_id="ws_design",
            active_only=True,
        )
    assert after_issue_count == before_issue_count
    assert after_session_count == before_session_count
    assert len(after_grants) == len(before_grants)

    bootstrap_retry = client.get(
        "/api/v1/worker-runtime/assignments",
        headers={"X-Boardroom-Worker-Bootstrap": issued_payload["bootstrap_token"]},
    )
    session_retry = client.get(
        "/api/v1/worker-runtime/assignments",
        headers=_worker_session_headers(assignments_data["session_token"]),
    )
    preview_retry = client.get(_local_path_from_url(preview_url))
    assert bootstrap_retry.status_code == 200
    assert session_retry.status_code == 200
    assert preview_retry.status_code == 200


def test_worker_admin_contain_scope_execute_only_revokes_target_scope(
    client,
    set_ticket_time,
    monkeypatch,
):
    monkeypatch.setenv("BOARDROOM_OS_WORKER_BOOTSTRAP_SIGNING_SECRET", "bootstrap-secret")
    monkeypatch.setenv("BOARDROOM_OS_WORKER_SESSION_TTL_SEC", "600")
    monkeypatch.setenv("BOARDROOM_OS_WORKER_DELIVERY_SIGNING_SECRET", "delivery-secret")

    repository = client.app.state.repository
    with repository.transaction() as connection:
        repository.ensure_worker_bootstrap_state(
            connection,
            worker_id="emp_frontend_2",
            tenant_id="tenant_default",
            workspace_id="ws_default",
            at=datetime.fromisoformat("2026-03-28T10:00:00+08:00"),
        )
        repository.ensure_worker_bootstrap_state(
            connection,
            worker_id="emp_frontend_2",
            tenant_id="tenant_blue",
            workspace_id="ws_design",
            at=datetime.fromisoformat("2026-03-28T10:00:00+08:00"),
        )

    set_ticket_time("2026-03-28T10:00:00+08:00")
    _seed_input_artifact(client)
    _create_and_lease_ticket(
        client,
        workflow_id="wf_worker_admin_contain_default",
        ticket_id="tkt_worker_admin_contain_default",
        node_id="node_worker_admin_contain_default",
    )
    _create_and_lease_ticket(
        client,
        workflow_id="wf_worker_admin_contain_blue",
        ticket_id="tkt_worker_admin_contain_blue",
        node_id="node_worker_admin_contain_blue",
        tenant_id="tenant_blue",
        workspace_id="ws_design",
    )

    default_issue = client.post(
        "/api/v1/worker-admin/issue-bootstrap",
        json={
            "worker_id": "emp_frontend_2",
            "tenant_id": "tenant_default",
            "workspace_id": "ws_default",
            "ttl_sec": 120,
            "issued_by": "ops@example.com",
        },
        headers=_worker_admin_headers(),
    )
    blue_issue = client.post(
        "/api/v1/worker-admin/issue-bootstrap",
        json={
            "worker_id": "emp_frontend_2",
            "tenant_id": "tenant_blue",
            "workspace_id": "ws_design",
            "ttl_sec": 120,
            "issued_by": "ops@example.com",
        },
        headers=_worker_admin_headers(),
    )
    assert default_issue.status_code == 200
    assert blue_issue.status_code == 200

    default_assignments, _ = _bootstrap_worker_execution_package(client, default_issue.json()["bootstrap_token"])
    blue_assignments, blue_execution_package = _bootstrap_worker_execution_package(
        client,
        blue_issue.json()["bootstrap_token"],
    )
    blue_preview_url = blue_execution_package["compiled_execution_package"]["atomic_context_bundle"]["context_blocks"][
        0
    ]["content_payload"]["preview_url"]

    with repository.connection() as connection:
        blue_active_grants = repository.list_worker_delivery_grants(
            connection,
            worker_id="emp_frontend_2",
            tenant_id="tenant_blue",
            workspace_id="ws_design",
            active_only=True,
        )

    response = client.post(
        "/api/v1/worker-admin/contain-scope",
        json={
            "tenant_id": "tenant_blue",
            "workspace_id": "ws_design",
            "dry_run": False,
            "revoke_bootstrap_issues": True,
            "revoke_sessions": True,
            "revoked_by": "ops@example.com",
            "reason": "Tenant incident containment.",
            "expected_active_bootstrap_issue_count": 1,
            "expected_active_session_count": 1,
            "expected_active_delivery_grant_count": len(blue_active_grants),
        },
        headers=_worker_admin_headers(),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["dry_run"] is False
    assert payload["executed"] is True
    assert payload["result"]["revoked_bootstrap_issue_count"] == 1
    assert payload["result"]["revoked_session_count"] == 1
    assert payload["result"]["revoked_delivery_grant_count"] == len(blue_active_grants)
    assert payload["result"]["revoked_by"] == "ops@example.com"
    assert payload["result"]["revoke_reason"] == "Tenant incident containment."

    blue_bootstrap_retry = client.get(
        "/api/v1/worker-runtime/assignments",
        headers={"X-Boardroom-Worker-Bootstrap": blue_issue.json()["bootstrap_token"]},
    )
    blue_session_retry = client.get(
        "/api/v1/worker-runtime/assignments",
        headers=_worker_session_headers(blue_assignments["session_token"]),
    )
    blue_preview_retry = client.get(_local_path_from_url(blue_preview_url))
    default_session_retry = client.get(
        "/api/v1/worker-runtime/assignments",
        headers=_worker_session_headers(default_assignments["session_token"]),
    )

    assert blue_bootstrap_retry.status_code == 401
    assert blue_session_retry.status_code == 401
    assert blue_preview_retry.status_code == 401
    assert default_session_retry.status_code == 200


def test_worker_admin_contain_scope_returns_conflict_when_expected_counts_are_stale(
    client,
    set_ticket_time,
    monkeypatch,
):
    monkeypatch.setenv("BOARDROOM_OS_WORKER_BOOTSTRAP_SIGNING_SECRET", "bootstrap-secret")
    monkeypatch.setenv("BOARDROOM_OS_WORKER_SESSION_TTL_SEC", "600")
    monkeypatch.setenv("BOARDROOM_OS_WORKER_DELIVERY_SIGNING_SECRET", "delivery-secret")

    set_ticket_time("2026-03-28T10:00:00+08:00")
    _seed_input_artifact(client)
    _create_and_lease_ticket(
        client,
        workflow_id="wf_worker_admin_contain_conflict",
        ticket_id="tkt_worker_admin_contain_conflict",
        node_id="node_worker_admin_contain_conflict",
        tenant_id="tenant_blue",
        workspace_id="ws_design",
    )

    issue_response = client.post(
        "/api/v1/worker-admin/issue-bootstrap",
        json={
            "worker_id": "emp_frontend_2",
            "tenant_id": "tenant_blue",
            "workspace_id": "ws_design",
            "ttl_sec": 120,
            "issued_by": "ops@example.com",
        },
        headers=_worker_admin_headers(),
    )
    assert issue_response.status_code == 200
    assignments_data, execution_package = _bootstrap_worker_execution_package(
        client,
        issue_response.json()["bootstrap_token"],
    )
    preview_url = execution_package["compiled_execution_package"]["atomic_context_bundle"]["context_blocks"][0][
        "content_payload"
    ]["preview_url"]

    response = client.post(
        "/api/v1/worker-admin/contain-scope",
        json={
            "tenant_id": "tenant_blue",
            "workspace_id": "ws_design",
            "dry_run": False,
            "revoke_bootstrap_issues": True,
            "revoke_sessions": True,
            "revoked_by": "ops@example.com",
            "reason": "Tenant incident containment.",
            "expected_active_bootstrap_issue_count": 2,
            "expected_active_session_count": 1,
            "expected_active_delivery_grant_count": 999,
        },
        headers=_worker_admin_headers(),
    )

    assert response.status_code == 409

    bootstrap_retry = client.get(
        "/api/v1/worker-runtime/assignments",
        headers={"X-Boardroom-Worker-Bootstrap": issue_response.json()["bootstrap_token"]},
    )
    session_retry = client.get(
        "/api/v1/worker-runtime/assignments",
        headers=_worker_session_headers(assignments_data["session_token"]),
    )
    preview_retry = client.get(_local_path_from_url(preview_url))

    assert bootstrap_retry.status_code == 200
    assert session_retry.status_code == 200
    assert preview_retry.status_code == 200


def test_worker_admin_bootstrap_issues_active_only_filters_revoked_and_expired(
    client,
    set_ticket_time,
    monkeypatch,
):
    monkeypatch.setenv("BOARDROOM_OS_WORKER_BOOTSTRAP_SIGNING_SECRET", "bootstrap-secret")

    repository = client.app.state.repository
    set_ticket_time("2026-03-28T10:00:00+08:00")
    with repository.transaction() as connection:
        state = repository.ensure_worker_bootstrap_state(
            connection,
            worker_id="emp_frontend_2",
            tenant_id="tenant_blue",
            workspace_id="ws_design",
            at=datetime.fromisoformat("2026-03-28T10:00:00+08:00"),
        )
        active_issue = repository.create_worker_bootstrap_issue(
            connection,
            worker_id="emp_frontend_2",
            tenant_id="tenant_blue",
            workspace_id="ws_design",
            credential_version=int(state["credential_version"]),
            issued_at=datetime.fromisoformat("2026-03-28T10:05:00+08:00"),
            expires_at=datetime.fromisoformat("2026-03-28T11:05:00+08:00"),
            issued_via="test",
            issued_by="ops@example.com",
            reason="active issue",
        )
        revoked_issue = repository.create_worker_bootstrap_issue(
            connection,
            worker_id="emp_frontend_2",
            tenant_id="tenant_blue",
            workspace_id="ws_design",
            credential_version=int(state["credential_version"]),
            issued_at=datetime.fromisoformat("2026-03-28T10:04:00+08:00"),
            expires_at=datetime.fromisoformat("2026-03-28T11:04:00+08:00"),
            issued_via="test",
            issued_by="ops@example.com",
            reason="revoked issue",
        )
        repository.revoke_worker_bootstrap_issues(
            connection,
            issue_id=str(revoked_issue["issue_id"]),
            revoked_at=datetime.fromisoformat("2026-03-28T10:06:00+08:00"),
        )
        repository.create_worker_bootstrap_issue(
            connection,
            worker_id="emp_frontend_2",
            tenant_id="tenant_blue",
            workspace_id="ws_design",
            credential_version=int(state["credential_version"]),
            issued_at=datetime.fromisoformat("2026-03-28T09:00:00+08:00"),
            expires_at=datetime.fromisoformat("2026-03-28T09:30:00+08:00"),
            issued_via="test",
            issued_by="ops@example.com",
            reason="expired issue",
        )

    set_ticket_time("2026-03-28T10:10:00+08:00")
    response = client.get(
        "/api/v1/worker-admin/bootstrap-issues",
        params={
            "worker_id": "emp_frontend_2",
            "tenant_id": "tenant_blue",
            "workspace_id": "ws_design",
            "active_only": "true",
        },
        headers=_worker_admin_headers(),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 1
    assert data["bootstrap_issues"][0]["issue_id"] == str(active_issue["issue_id"])
    assert data["bootstrap_issues"][0]["reason"] == "active issue"


def test_worker_admin_create_binding_is_idempotent(client):
    first_response = client.post(
        "/api/v1/worker-admin/create-binding",
        json={
            "worker_id": "emp_frontend_2",
            "tenant_id": "tenant_blue",
            "workspace_id": "ws_design",
        },
        headers=_worker_admin_headers(),
    )
    second_response = client.post(
        "/api/v1/worker-admin/create-binding",
        json={
            "worker_id": "emp_frontend_2",
            "tenant_id": "tenant_blue",
            "workspace_id": "ws_design",
        },
        headers=_worker_admin_headers(),
    )

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    repository = client.app.state.repository
    bindings = repository.list_worker_bootstrap_states(worker_id="emp_frontend_2")
    assert len(bindings) == 1
    assert bindings[0]["tenant_id"] == "tenant_blue"
    assert bindings[0]["workspace_id"] == "ws_design"


def test_worker_admin_issue_bootstrap_returns_usable_token_and_enforces_explicit_scope(
    client,
    set_ticket_time,
    monkeypatch,
):
    monkeypatch.setenv("BOARDROOM_OS_WORKER_BOOTSTRAP_SIGNING_SECRET", "bootstrap-secret")
    monkeypatch.setenv("BOARDROOM_OS_WORKER_SESSION_TTL_SEC", "600")

    repository = client.app.state.repository
    with repository.transaction() as connection:
        repository.ensure_worker_bootstrap_state(
            connection,
            worker_id="emp_frontend_2",
            tenant_id="tenant_default",
            workspace_id="ws_default",
            at=datetime.fromisoformat("2026-03-28T10:00:00+08:00"),
        )
        repository.ensure_worker_bootstrap_state(
            connection,
            worker_id="emp_frontend_2",
            tenant_id="tenant_blue",
            workspace_id="ws_design",
            at=datetime.fromisoformat("2026-03-28T10:00:00+08:00"),
        )

    set_ticket_time("2026-03-28T10:00:00+08:00")
    _create_and_lease_ticket(
        client,
        workflow_id="wf_worker_admin_issue",
        ticket_id="tkt_worker_admin_issue",
        node_id="node_worker_admin_issue",
        tenant_id="tenant_blue",
        workspace_id="ws_design",
    )

    missing_scope_response = client.post(
        "/api/v1/worker-admin/issue-bootstrap",
        json={"worker_id": "emp_frontend_2", "ttl_sec": 120},
        headers=_worker_admin_headers(),
    )
    scoped_response = client.post(
        "/api/v1/worker-admin/issue-bootstrap",
        json={
            "worker_id": "emp_frontend_2",
            "tenant_id": "tenant_blue",
            "workspace_id": "ws_design",
            "ttl_sec": 120,
            "issued_by": "ops@example.com",
            "reason": "tenant admin bootstrap",
        },
        headers=_worker_admin_headers(),
    )

    assert missing_scope_response.status_code == 400
    assert scoped_response.status_code == 200
    payload = scoped_response.json()
    assert payload["tenant_id"] == "tenant_blue"
    assert payload["workspace_id"] == "ws_design"
    assert payload["issued_by"] == "ops@example.com"

    assignments_response = client.get(
        "/api/v1/worker-runtime/assignments",
        headers={"X-Boardroom-Worker-Bootstrap": payload["bootstrap_token"]},
    )
    assert assignments_response.status_code == 200
    assert assignments_response.json()["data"]["workspace_id"] == "ws_design"


def test_worker_admin_revoke_bootstrap_invalidates_issue_backed_token(
    client,
    set_ticket_time,
    monkeypatch,
):
    monkeypatch.setenv("BOARDROOM_OS_WORKER_BOOTSTRAP_SIGNING_SECRET", "bootstrap-secret")
    monkeypatch.setenv("BOARDROOM_OS_WORKER_SESSION_TTL_SEC", "600")

    set_ticket_time("2026-03-28T10:00:00+08:00")
    _create_and_lease_ticket(
        client,
        workflow_id="wf_worker_admin_revoke",
        ticket_id="tkt_worker_admin_revoke",
        node_id="node_worker_admin_revoke",
    )

    issue_response = client.post(
        "/api/v1/worker-admin/issue-bootstrap",
        json={"worker_id": "emp_frontend_2", "ttl_sec": 120},
        headers=_worker_admin_headers(),
    )
    assert issue_response.status_code == 200
    issued_payload = issue_response.json()

    revoke_response = client.post(
        "/api/v1/worker-admin/revoke-bootstrap",
        json={"worker_id": "emp_frontend_2"},
        headers=_worker_admin_headers(),
    )
    assignments_response = client.get(
        "/api/v1/worker-runtime/assignments",
        headers={"X-Boardroom-Worker-Bootstrap": issued_payload["bootstrap_token"]},
    )

    assert revoke_response.status_code == 200
    assert revoke_response.json()["worker_id"] == "emp_frontend_2"
    assert assignments_response.status_code == 401


def test_worker_admin_revoke_session_by_session_id_cascades_grants_and_updates_projection(
    client,
    set_ticket_time,
    monkeypatch,
):
    monkeypatch.setenv("BOARDROOM_OS_WORKER_BOOTSTRAP_SIGNING_SECRET", "bootstrap-secret")
    monkeypatch.setenv("BOARDROOM_OS_WORKER_SESSION_TTL_SEC", "600")
    monkeypatch.setenv("BOARDROOM_OS_WORKER_DELIVERY_SIGNING_SECRET", "delivery-secret")

    set_ticket_time("2026-03-28T10:00:00+08:00")
    _seed_input_artifact(client)
    _create_and_lease_ticket(
        client,
        workflow_id="wf_worker_admin_revoke_session",
        ticket_id="tkt_worker_admin_revoke_session",
        node_id="node_worker_admin_revoke_session",
    )

    issue_response = client.post(
        "/api/v1/worker-admin/issue-bootstrap",
        json={"worker_id": "emp_frontend_2", "ttl_sec": 120},
        headers=_worker_admin_headers(),
    )
    assert issue_response.status_code == 200
    issued_payload = issue_response.json()
    assignments_data, _ = _bootstrap_worker_execution_package(client, issued_payload["bootstrap_token"])

    repository = client.app.state.repository
    with repository.connection() as connection:
        session_grants = repository.list_worker_delivery_grants(
            connection,
            session_id=assignments_data["session_id"],
        )
    assert session_grants

    revoke_response = client.post(
        "/api/v1/worker-admin/revoke-session",
        json={
            "session_id": assignments_data["session_id"],
            "revoked_by": "ops@example.com",
            "reason": "Tenant incident session revoke.",
        },
        headers=_worker_admin_headers(),
    )
    assert revoke_response.status_code == 200
    revoke_payload = revoke_response.json()
    assert revoke_payload["session_id"] == assignments_data["session_id"]
    assert revoke_payload["worker_id"] == "emp_frontend_2"
    assert revoke_payload["tenant_id"] == "tenant_default"
    assert revoke_payload["workspace_id"] == "ws_default"
    assert revoke_payload["revoked_count"] == 1
    assert revoke_payload["revoked_delivery_grant_count"] == len(session_grants)
    assert revoke_payload["revoked_via"] == "worker_admin_api"
    assert revoke_payload["revoked_by"] == "ops@example.com"
    assert revoke_payload["revoke_reason"] == "Tenant incident session revoke."

    assignments_response = client.get(
        "/api/v1/worker-runtime/assignments",
        headers=_worker_session_headers(assignments_data["session_token"]),
    )
    assert assignments_response.status_code == 401

    projection_response = client.get(
        "/api/v1/projections/worker-runtime",
        params={
            "worker_id": "emp_frontend_2",
            "tenant_id": "tenant_default",
            "workspace_id": "ws_default",
            "grant_limit": 20,
        },
    )
    assert projection_response.status_code == 200
    projection = projection_response.json()["data"]
    session_item = next(
        item for item in projection["sessions"] if item["session_id"] == assignments_data["session_id"]
    )
    assert session_item["revoke_reason"] == "Tenant incident session revoke."
    assert session_item["revoked_via"] == "worker_admin_api"
    assert session_item["revoked_by"] == "ops@example.com"
    revoked_grants = [
        item for item in projection["delivery_grants"] if item["session_id"] == assignments_data["session_id"]
    ]
    assert revoked_grants
    assert all(item["revoked_via"] == "worker_admin_api" for item in revoked_grants)
    assert all(item["revoked_by"] == "ops@example.com" for item in revoked_grants)
    assert all(item["revoke_reason"] == "Tenant incident session revoke." for item in revoked_grants)


def test_worker_admin_revoke_session_by_scope_only_hits_requested_scope(
    client,
    set_ticket_time,
    monkeypatch,
):
    monkeypatch.setenv("BOARDROOM_OS_WORKER_BOOTSTRAP_SIGNING_SECRET", "bootstrap-secret")
    monkeypatch.setenv("BOARDROOM_OS_WORKER_SESSION_TTL_SEC", "600")

    repository = client.app.state.repository
    with repository.transaction() as connection:
        repository.ensure_worker_bootstrap_state(
            connection,
            worker_id="emp_frontend_2",
            tenant_id="tenant_default",
            workspace_id="ws_default",
            at=datetime.fromisoformat("2026-03-28T10:00:00+08:00"),
        )
        repository.ensure_worker_bootstrap_state(
            connection,
            worker_id="emp_frontend_2",
            tenant_id="tenant_blue",
            workspace_id="ws_design",
            at=datetime.fromisoformat("2026-03-28T10:00:00+08:00"),
        )

    set_ticket_time("2026-03-28T10:00:00+08:00")
    _create_and_lease_ticket(
        client,
        workflow_id="wf_worker_admin_scope_default",
        ticket_id="tkt_worker_admin_scope_default",
        node_id="node_worker_admin_scope_default",
    )
    _create_and_lease_ticket(
        client,
        workflow_id="wf_worker_admin_scope_blue",
        ticket_id="tkt_worker_admin_scope_blue",
        node_id="node_worker_admin_scope_blue",
        tenant_id="tenant_blue",
        workspace_id="ws_design",
    )

    default_issue = client.post(
        "/api/v1/worker-admin/issue-bootstrap",
        json={
            "worker_id": "emp_frontend_2",
            "tenant_id": "tenant_default",
            "workspace_id": "ws_default",
            "ttl_sec": 120,
        },
        headers=_worker_admin_headers(),
    )
    blue_issue = client.post(
        "/api/v1/worker-admin/issue-bootstrap",
        json={
            "worker_id": "emp_frontend_2",
            "tenant_id": "tenant_blue",
            "workspace_id": "ws_design",
            "ttl_sec": 120,
        },
        headers=_worker_admin_headers(),
    )
    assert default_issue.status_code == 200
    assert blue_issue.status_code == 200

    default_assignments = client.get(
        "/api/v1/worker-runtime/assignments",
        headers={"X-Boardroom-Worker-Bootstrap": default_issue.json()["bootstrap_token"]},
    )
    blue_assignments = client.get(
        "/api/v1/worker-runtime/assignments",
        headers={"X-Boardroom-Worker-Bootstrap": blue_issue.json()["bootstrap_token"]},
    )
    default_session = default_assignments.json()["data"]
    blue_session = blue_assignments.json()["data"]

    revoke_response = client.post(
        "/api/v1/worker-admin/revoke-session",
        json={
            "worker_id": "emp_frontend_2",
            "tenant_id": "tenant_blue",
            "workspace_id": "ws_design",
            "revoked_by": "ops@example.com",
            "reason": "Tenant-blue scope revoke.",
        },
        headers=_worker_admin_headers(),
    )
    assert revoke_response.status_code == 200
    revoke_payload = revoke_response.json()
    assert revoke_payload["session_id"] is None
    assert revoke_payload["worker_id"] == "emp_frontend_2"
    assert revoke_payload["tenant_id"] == "tenant_blue"
    assert revoke_payload["workspace_id"] == "ws_design"
    assert revoke_payload["revoked_count"] == 1
    assert revoke_payload["revoked_via"] == "worker_admin_api"

    revoked_response = client.get(
        "/api/v1/worker-runtime/assignments",
        headers=_worker_session_headers(blue_session["session_token"]),
    )
    surviving_response = client.get(
        "/api/v1/worker-runtime/assignments",
        headers=_worker_session_headers(default_session["session_token"]),
    )

    assert revoked_response.status_code == 401
    assert surviving_response.status_code == 200


def test_worker_admin_revoke_delivery_grant_only_revokes_target_and_exposes_audit_fields(
    client,
    set_ticket_time,
    monkeypatch,
):
    monkeypatch.setenv("BOARDROOM_OS_WORKER_BOOTSTRAP_SIGNING_SECRET", "bootstrap-secret")
    monkeypatch.setenv("BOARDROOM_OS_WORKER_SESSION_TTL_SEC", "600")
    monkeypatch.setenv("BOARDROOM_OS_WORKER_DELIVERY_SIGNING_SECRET", "delivery-secret")

    set_ticket_time("2026-03-28T10:00:00+08:00")
    _seed_input_artifact(client)
    _create_and_lease_ticket(
        client,
        workflow_id="wf_worker_admin_revoke_grant",
        ticket_id="tkt_worker_admin_revoke_grant",
        node_id="node_worker_admin_revoke_grant",
    )

    issue_response = client.post(
        "/api/v1/worker-admin/issue-bootstrap",
        json={"worker_id": "emp_frontend_2", "ttl_sec": 120},
        headers=_worker_admin_headers(),
    )
    assert issue_response.status_code == 200
    _, execution_package = _bootstrap_worker_execution_package(
        client,
        issue_response.json()["bootstrap_token"],
    )
    context_payload = execution_package["compiled_execution_package"]["atomic_context_bundle"]["context_blocks"][0][
        "content_payload"
    ]
    preview_url = context_payload["preview_url"]
    content_url = context_payload["content_url"]
    preview_grant_id = _decode_worker_delivery_token_payload(
        _query_value(preview_url, "access_token") or ""
    )["grant_id"]

    revoke_response = client.post(
        "/api/v1/worker-admin/revoke-delivery-grant",
        json={
            "grant_id": preview_grant_id,
            "revoked_by": "ops@example.com",
            "reason": "Manual preview revoke from HTTP.",
        },
        headers=_worker_admin_headers(),
    )
    assert revoke_response.status_code == 200
    revoke_payload = revoke_response.json()
    assert revoke_payload["grant_id"] == preview_grant_id
    assert revoke_payload["revoked_count"] == 1
    assert revoke_payload["revoked_via"] == "worker_admin_api"
    assert revoke_payload["revoked_by"] == "ops@example.com"
    assert revoke_payload["revoke_reason"] == "Manual preview revoke from HTTP."

    preview_response = client.get(_local_path_from_url(preview_url))
    content_response = client.get(_local_path_from_url(content_url))
    assert preview_response.status_code == 401
    assert content_response.status_code == 200

    projection_response = client.get(
        "/api/v1/projections/worker-runtime",
        params={
            "worker_id": "emp_frontend_2",
            "tenant_id": "tenant_default",
            "workspace_id": "ws_default",
            "grant_limit": 20,
        },
    )
    assert projection_response.status_code == 200
    projection = projection_response.json()["data"]
    grant_item = next(item for item in projection["delivery_grants"] if item["grant_id"] == preview_grant_id)
    assert grant_item["revoked_via"] == "worker_admin_api"
    assert grant_item["revoked_by"] == "ops@example.com"
    assert grant_item["revoke_reason"] == "Manual preview revoke from HTTP."


def test_worker_admin_cleanup_bindings_honors_dry_run_and_deletes_only_cleanup_eligible(client):
    repository = client.app.state.repository
    with repository.transaction() as connection:
        repository.ensure_worker_bootstrap_state(
            connection,
            worker_id="emp_frontend_2",
            tenant_id="tenant_default",
            workspace_id="ws_default",
            at=datetime.fromisoformat("2026-03-28T10:00:00+08:00"),
        )
        repository.ensure_worker_bootstrap_state(
            connection,
            worker_id="emp_frontend_2",
            tenant_id="tenant_blue",
            workspace_id="ws_design",
            at=datetime.fromisoformat("2026-03-28T10:00:00+08:00"),
        )
        repository.create_worker_bootstrap_issue(
            connection,
            worker_id="emp_frontend_2",
            tenant_id="tenant_default",
            workspace_id="ws_default",
            credential_version=1,
            issued_at=datetime.fromisoformat("2026-03-28T10:01:00+08:00"),
            expires_at=datetime.fromisoformat("2026-03-28T11:01:00+08:00"),
            issued_via="test",
            issued_by="ops@example.com",
            reason="keep binding active",
        )
        repository.revoke_worker_bootstrap_state(
            connection,
            worker_id="emp_frontend_2",
            tenant_id="tenant_blue",
            workspace_id="ws_design",
            revoked_at=datetime.fromisoformat("2026-03-28T10:05:00+08:00"),
        )

    dry_run_response = client.post(
        "/api/v1/worker-admin/cleanup-bindings",
        json={"worker_id": "emp_frontend_2", "dry_run": True},
        headers=_worker_admin_headers(),
    )
    execute_response = client.post(
        "/api/v1/worker-admin/cleanup-bindings",
        json={"worker_id": "emp_frontend_2", "dry_run": False},
        headers=_worker_admin_headers(),
    )

    assert dry_run_response.status_code == 200
    assert dry_run_response.json()["deleted_count"] == 0
    assert execute_response.status_code == 200
    assert execute_response.json()["deleted_count"] == 1

    remaining_bindings = repository.list_worker_bootstrap_states(worker_id="emp_frontend_2")
    assert len(remaining_bindings) == 1
    assert remaining_bindings[0]["tenant_id"] == "tenant_default"
    assert remaining_bindings[0]["workspace_id"] == "ws_default"


def test_worker_admin_audit_projection_lists_logged_actions_with_dry_run_and_scope_filters(client, monkeypatch):
    monkeypatch.setenv("BOARDROOM_OS_WORKER_BOOTSTRAP_SIGNING_SECRET", "bootstrap-secret")

    create_response = client.post(
        "/api/v1/worker-admin/create-binding",
        json={
            "worker_id": "emp_frontend_2",
            "tenant_id": "tenant_blue",
            "workspace_id": "ws_design",
        },
        headers=_worker_admin_headers(),
    )
    issue_response = client.post(
        "/api/v1/worker-admin/issue-bootstrap",
        json={
            "worker_id": "emp_frontend_2",
            "tenant_id": "tenant_blue",
            "workspace_id": "ws_design",
            "ttl_sec": 120,
            "reason": "tenant scoped bootstrap",
        },
        headers=_worker_admin_headers(),
    )
    cleanup_response = client.post(
        "/api/v1/worker-admin/cleanup-bindings",
        json={
            "worker_id": "emp_frontend_2",
            "tenant_id": "tenant_blue",
            "workspace_id": "ws_design",
            "dry_run": True,
        },
        headers=_worker_admin_headers(),
    )
    audit_response = client.get(
        "/api/v1/projections/worker-admin-audit",
        params={"tenant_id": "tenant_blue", "workspace_id": "ws_design", "limit": 10},
        headers=_worker_admin_headers(),
    )

    assert create_response.status_code == 200
    assert issue_response.status_code == 200
    assert cleanup_response.status_code == 200
    assert audit_response.status_code == 200
    payload = audit_response.json()["data"]
    assert payload["summary"]["count"] == 3
    assert payload["filters"]["tenant_id"] == "tenant_blue"
    assert payload["filters"]["workspace_id"] == "ws_design"
    assert payload["filters"]["limit"] == 10
    assert [item["action_type"] for item in payload["actions"]] == [
        "cleanup_bindings",
        "issue_bootstrap",
        "create_binding",
    ]
    assert payload["actions"][0]["dry_run"] is True
    assert payload["actions"][0]["details"]["executed"] is False
    assert payload["actions"][1]["operator_id"] == "ops@example.com"
    assert payload["actions"][1]["operator_role"] == "platform_admin"
    assert payload["actions"][1]["auth_source"] == "signed_token"
    assert payload["actions"][1]["details"]["succeeded"] is True


def test_worker_admin_trusted_proxy_is_optional_by_default(client):
    response = client.get(
        "/api/v1/worker-admin/bindings",
        params={"tenant_id": "tenant_default", "workspace_id": "ws_default"},
        headers=_worker_admin_headers(),
    )

    assert response.status_code == 200


def test_worker_admin_trusted_proxy_missing_assertion_is_rejected_and_visible(client, monkeypatch):
    monkeypatch.setenv("BOARDROOM_OS_WORKER_ADMIN_TRUSTED_PROXY_IDS", "proxy-a,proxy-b")

    rejected_response = client.get(
        "/api/v1/worker-admin/bindings",
        params={"tenant_id": "tenant_default", "workspace_id": "ws_default"},
        headers=_worker_admin_headers(),
    )
    projection_without_proxy = client.get(
        "/api/v1/projections/worker-admin-auth-rejections",
        params={"route_path": "/api/v1/worker-admin/bindings", "limit": 10},
        headers=_worker_admin_headers(),
    )
    projection_with_proxy = client.get(
        "/api/v1/projections/worker-admin-auth-rejections",
        params={"route_path": "/api/v1/worker-admin/bindings", "limit": 10},
        headers=_worker_admin_headers(trusted_proxy_id="proxy-a"),
    )

    assert rejected_response.status_code == 403
    assert rejected_response.json()["detail"] == "Worker-admin trusted proxy assertion is required."
    assert projection_without_proxy.status_code == 403
    assert projection_with_proxy.status_code == 200
    payload = projection_with_proxy.json()["data"]
    assert payload["summary"]["trusted_proxy_enforced"] is True
    assert payload["summary"]["trusted_proxy_ids"] == ["proxy-a", "proxy-b"]
    assert payload["rejections"][0]["reason_code"] == "missing_trusted_proxy_assertion"
    assert payload["rejections"][0]["trusted_proxy_id"] is None
    assert payload["rejections"][0]["source_ip"] == "testclient"


def test_worker_admin_trusted_proxy_rejects_untrusted_proxy_and_accepts_allowed_proxy(client, monkeypatch):
    monkeypatch.setenv("BOARDROOM_OS_WORKER_ADMIN_TRUSTED_PROXY_IDS", "proxy-a,proxy-b")

    rejected_response = client.get(
        "/api/v1/worker-admin/bindings",
        params={"tenant_id": "tenant_default", "workspace_id": "ws_default"},
        headers=_worker_admin_headers(trusted_proxy_id="proxy-x"),
    )
    accepted_response = client.get(
        "/api/v1/worker-admin/bindings",
        params={"tenant_id": "tenant_default", "workspace_id": "ws_default"},
        headers=_worker_admin_headers(trusted_proxy_id="proxy-a"),
    )
    projection_response = client.get(
        "/api/v1/projections/worker-admin-auth-rejections",
        params={"route_path": "/api/v1/worker-admin/bindings", "limit": 10},
        headers=_worker_admin_headers(trusted_proxy_id="proxy-a"),
    )

    assert rejected_response.status_code == 403
    assert rejected_response.json()["detail"] == "Worker-admin trusted proxy assertion is not allowed."
    assert accepted_response.status_code == 200
    assert projection_response.status_code == 200
    payload = projection_response.json()["data"]
    assert payload["rejections"][0]["reason_code"] == "untrusted_proxy_assertion"
    assert payload["rejections"][0]["trusted_proxy_id"] == "proxy-x"
    assert payload["rejections"][0]["source_ip"] == "testclient"


def test_worker_admin_audit_projection_exposes_trusted_proxy_context(client, monkeypatch):
    monkeypatch.setenv("BOARDROOM_OS_WORKER_ADMIN_TRUSTED_PROXY_IDS", "proxy-a")

    create_response = client.post(
        "/api/v1/worker-admin/create-binding",
        json={
            "worker_id": "emp_frontend_2",
            "tenant_id": "tenant_blue",
            "workspace_id": "ws_design",
        },
        headers=_worker_admin_headers(trusted_proxy_id="proxy-a"),
    )
    audit_response = client.get(
        "/api/v1/projections/worker-admin-audit",
        params={"tenant_id": "tenant_blue", "workspace_id": "ws_design", "limit": 10},
        headers=_worker_admin_headers(trusted_proxy_id="proxy-a"),
    )

    assert create_response.status_code == 200
    assert audit_response.status_code == 200
    payload = audit_response.json()["data"]
    assert payload["actions"][0]["trusted_proxy_id"] == "proxy-a"
    assert payload["actions"][0]["source_ip"] == "testclient"


def test_worker_admin_audit_projection_scope_viewer_reads_only_own_scope(client):
    own_scope_headers = _worker_admin_headers(
        operator_id="tenant.viewer@example.com",
        role="scope_viewer",
        tenant_id="tenant_blue",
        workspace_id="ws_design",
    )

    own_scope_response = client.get(
        "/api/v1/projections/worker-admin-audit",
        params={"tenant_id": "tenant_blue", "workspace_id": "ws_design"},
        headers=own_scope_headers,
    )
    other_scope_response = client.get(
        "/api/v1/projections/worker-admin-audit",
        params={"tenant_id": "tenant_default", "workspace_id": "ws_default"},
        headers=own_scope_headers,
    )
    missing_scope_response = client.get(
        "/api/v1/projections/worker-admin-audit",
        params={"operator_id": "tenant.viewer@example.com"},
        headers=own_scope_headers,
    )

    assert own_scope_response.status_code == 200
    assert other_scope_response.status_code == 403
    assert missing_scope_response.status_code == 403


def test_worker_admin_rejects_signed_token_with_naive_datetime_claims(client):
    import base64
    import hashlib
    import hmac

    payload = {
        "version": "v1",
        "operator_id": "ops@example.com",
        "role": "platform_admin",
        "tenant_id": None,
        "workspace_id": None,
        "issued_at": "2026-03-28T10:00:00",
        "expires_at": "2026-03-28T11:00:00",
    }
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    payload_segment = base64.urlsafe_b64encode(serialized).decode("ascii").rstrip("=")
    signature = hmac.new(b"operator-secret", serialized, hashlib.sha256).digest()
    signature_segment = base64.urlsafe_b64encode(signature).decode("ascii").rstrip("=")
    token = f"{payload_segment}.{signature_segment}"

    response = client.get(
        "/api/v1/worker-admin/bindings",
        params={
            "worker_id": "emp_frontend_2",
            "tenant_id": "tenant_default",
            "workspace_id": "ws_default",
        },
        headers={"X-Boardroom-Operator-Token": token},
    )

    assert response.status_code == 401


def test_worker_admin_operator_tokens_lists_scope_local_tokens_and_blocks_platform_revoke(client):
    platform_headers, platform_issue = _persisted_worker_admin_headers(
        client,
        operator_id="ops@example.com",
        role="platform_admin",
    )
    _, _ = _persisted_worker_admin_headers(
        client,
        operator_id="tenant.admin@example.com",
        role="scope_admin",
        tenant_id="tenant_blue",
        workspace_id="ws_design",
    )
    _, _ = _persisted_worker_admin_headers(
        client,
        operator_id="tenant.viewer@example.com",
        role="scope_viewer",
        tenant_id="tenant_blue",
        workspace_id="ws_design",
    )
    scope_headers, _ = _persisted_worker_admin_headers(
        client,
        operator_id="tenant.admin@example.com",
        role="scope_admin",
        tenant_id="tenant_blue",
        workspace_id="ws_design",
    )

    list_response = client.get(
        "/api/v1/worker-admin/operator-tokens",
        params={"tenant_id": "tenant_blue", "workspace_id": "ws_design", "active_only": True},
        headers=scope_headers,
    )
    revoke_response = client.post(
        "/api/v1/worker-admin/revoke-operator-token",
        json={
            "token_id": platform_issue["token_id"],
            "revoked_by": "tenant.admin@example.com",
            "reason": "should not be allowed",
        },
        headers=scope_headers,
    )
    platform_list_response = client.get(
        "/api/v1/worker-admin/operator-tokens",
        params={"active_only": True},
        headers=platform_headers,
    )

    assert list_response.status_code == 200
    payload = list_response.json()
    assert payload["count"] >= 2
    assert all(item["tenant_id"] == "tenant_blue" for item in payload["tokens"])
    assert all(item["workspace_id"] == "ws_design" for item in payload["tokens"])
    assert all(item["role"] != "platform_admin" for item in payload["tokens"])
    assert revoke_response.status_code == 403
    assert platform_list_response.status_code == 200
    assert any(
        item["token_id"] == platform_issue["token_id"]
        for item in platform_list_response.json()["tokens"]
    )


def test_worker_admin_revoked_operator_token_is_rejected_and_visible_in_auth_rejection_projection(
    client,
):
    headers, token_issue = _persisted_worker_admin_headers(
        client,
        operator_id="ops@example.com",
        role="platform_admin",
    )
    repository = client.app.state.repository
    revoked_at = datetime.now().astimezone()
    with repository.transaction() as connection:
        repository.revoke_worker_admin_token_issue(
            connection,
            token_id=token_issue["token_id"],
            revoked_at=revoked_at,
            revoked_by="ops@example.com",
            revoke_reason="manual test revoke",
        )

    rejected_response = client.get("/api/v1/worker-admin/bindings", headers=headers)
    projection_response = client.get(
        "/api/v1/projections/worker-admin-auth-rejections",
        params={"token_id": token_issue["token_id"], "limit": 10},
        headers=_worker_admin_headers(),
    )

    assert rejected_response.status_code == 401
    assert rejected_response.json()["detail"] == "Worker-admin operator token has been revoked."
    assert projection_response.status_code == 200
    projection_payload = projection_response.json()
    assert projection_payload["data"]["summary"]["count"] == 1
    assert projection_payload["data"]["rejections"][0]["token_id"] == token_issue["token_id"]
    assert projection_payload["data"]["rejections"][0]["reason_code"] == "revoked_token"


def test_worker_admin_missing_token_is_logged_in_auth_rejection_projection(client):
    rejected_response = client.get("/api/v1/worker-admin/bindings")
    projection_response = client.get(
        "/api/v1/projections/worker-admin-auth-rejections",
        params={"route_path": "/api/v1/worker-admin/bindings", "limit": 10},
        headers=_worker_admin_headers(),
    )

    assert rejected_response.status_code == 401
    assert projection_response.status_code == 200
    assert projection_response.json()["data"]["rejections"][0]["reason_code"] == "missing_operator_token"


def test_worker_admin_audit_projection_validates_positive_limit(client):
    response = client.get(
        "/api/v1/projections/worker-admin-audit",
        params={
            "tenant_id": "tenant_default",
            "workspace_id": "ws_default",
            "limit": -1,
        },
        headers=_worker_admin_headers(),
    )

    assert response.status_code == 422


def test_worker_runtime_projection_returns_scope_aligned_operational_view(
    client,
    set_ticket_time,
    monkeypatch,
    capsys,
):
    monkeypatch.setenv("BOARDROOM_OS_WORKER_BOOTSTRAP_SIGNING_SECRET", "bootstrap-secret")
    monkeypatch.setenv("BOARDROOM_OS_WORKER_SESSION_TTL_SEC", "600")
    monkeypatch.setenv("BOARDROOM_OS_WORKER_DELIVERY_SIGNING_SECRET", "delivery-secret")

    from app.worker_auth_cli import main

    set_ticket_time("2026-03-28T10:00:00+08:00")
    _seed_input_artifact(client)
    _create_and_lease_ticket(
        client,
        workflow_id="wf_projection_scope",
        ticket_id="tkt_projection_scope",
        node_id="node_projection_scope",
        tenant_id="tenant_blue",
        workspace_id="ws_design",
    )
    _create_and_lease_ticket(
        client,
        workflow_id="wf_projection_scope",
        ticket_id="tkt_projection_reject",
        node_id="node_projection_reject",
        tenant_id="tenant_blue",
        workspace_id="ws_design",
    )

    assert (
        main(
            [
                "issue-bootstrap",
                "--worker-id",
                "emp_frontend_2",
                "--tenant-id",
                "tenant_blue",
                "--workspace-id",
                "ws_design",
                "--ttl-sec",
                "120",
            ]
        )
        == 0
    )
    bootstrap_output = json.loads(capsys.readouterr().out)
    assignments_data, _ = _bootstrap_worker_execution_package(client, bootstrap_output["bootstrap_token"])

    repository = client.app.state.repository
    with repository.transaction() as connection:
        connection.execute(
            """
            UPDATE ticket_projection
            SET workspace_id = ?
            WHERE ticket_id = ?
            """,
            ("ws_other", "tkt_projection_reject"),
        )

    rejected_response = client.get(
        "/api/v1/worker-runtime/assignments",
        headers=_worker_session_headers(assignments_data["session_token"]),
    )
    assert rejected_response.status_code == 403

    response = client.get(
        "/api/v1/projections/worker-runtime",
        params={
            "worker_id": "emp_frontend_2",
            "tenant_id": "tenant_blue",
            "workspace_id": "ws_design",
            "grant_limit": 20,
            "rejection_limit": 10,
        },
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["summary"]["binding_count"] == 1
    assert data["summary"]["cleanup_eligible_binding_count"] == 0
    assert data["summary"]["active_session_count"] == 1
    assert data["summary"]["active_delivery_grant_count"] > 0
    assert data["summary"]["recent_rejection_count"] == 1
    assert data["filters"]["worker_id"] == "emp_frontend_2"
    assert data["filters"]["tenant_id"] == "tenant_blue"
    assert data["filters"]["workspace_id"] == "ws_design"
    assert data["bindings"][0]["tenant_id"] == "tenant_blue"
    assert data["bindings"][0]["workspace_id"] == "ws_design"
    assert data["bindings"][0]["active_ticket_count"] == 1
    assert data["bindings"][0]["active_session_count"] == 1
    assert data["bindings"][0]["latest_bootstrap_issue_source"] == "worker_auth_cli"
    assert data["bindings"][0]["cleanup_eligible"] is False
    assert data["sessions"][0]["is_active"] is True
    assert all(grant["is_active"] is True for grant in data["delivery_grants"])
    assert data["auth_rejections"][0]["reason_code"] == "workspace_mismatch"
    assert data["auth_rejections"][0]["route_family"] == "assignments"


def test_worker_runtime_projection_active_only_hides_inactive_sessions_and_grants_but_keeps_binding(
    client,
    set_ticket_time,
    monkeypatch,
    capsys,
):
    monkeypatch.setenv("BOARDROOM_OS_WORKER_BOOTSTRAP_SIGNING_SECRET", "bootstrap-secret")
    monkeypatch.setenv("BOARDROOM_OS_WORKER_SESSION_TTL_SEC", "600")
    monkeypatch.setenv("BOARDROOM_OS_WORKER_DELIVERY_SIGNING_SECRET", "delivery-secret")

    from app.worker_auth_cli import main

    set_ticket_time("2026-03-28T10:00:00+08:00")
    _seed_input_artifact(client)
    _create_and_lease_ticket(
        client,
        workflow_id="wf_projection_active",
        ticket_id="tkt_projection_active",
        node_id="node_projection_active",
    )

    assert main(["issue-bootstrap", "--worker-id", "emp_frontend_2", "--ttl-sec", "120"]) == 0
    bootstrap_output = json.loads(capsys.readouterr().out)
    assignments_data, _ = _bootstrap_worker_execution_package(client, bootstrap_output["bootstrap_token"])

    repository = client.app.state.repository
    with repository.transaction() as connection:
        connection.execute(
            """
            UPDATE worker_session
            SET expires_at = ?, revoked_at = ?
            WHERE session_id = ?
            """,
            (
                "2026-03-28T10:01:00+08:00",
                "2026-03-28T10:01:00+08:00",
                assignments_data["session_id"],
            ),
        )
        connection.execute(
            """
            UPDATE worker_delivery_grant
            SET expires_at = ?, revoked_at = ?
            WHERE session_id = ?
            """,
            (
                "2026-03-28T10:01:00+08:00",
                "2026-03-28T10:01:00+08:00",
                assignments_data["session_id"],
            ),
        )

    set_ticket_time("2026-03-28T10:05:00+08:00")
    response = client.get(
        "/api/v1/projections/worker-runtime",
        params={
            "worker_id": "emp_frontend_2",
            "tenant_id": "tenant_default",
            "workspace_id": "ws_default",
            "active_only": "true",
        },
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["summary"]["binding_count"] == 1
    assert data["summary"]["active_session_count"] == 0
    assert data["summary"]["active_delivery_grant_count"] == 0
    assert len(data["bindings"]) == 1
    assert data["sessions"] == []
    assert data["delivery_grants"] == []


def test_worker_runtime_assignments_reject_revoked_bootstrap_issue_but_accept_legacy_bootstrap_token(
    client,
    set_ticket_time,
    monkeypatch,
    capsys,
):
    monkeypatch.setenv("BOARDROOM_OS_WORKER_BOOTSTRAP_SIGNING_SECRET", "bootstrap-secret")
    monkeypatch.setenv("BOARDROOM_OS_WORKER_SESSION_TTL_SEC", "600")

    from app.worker_auth_cli import main

    set_ticket_time("2026-03-28T10:00:00+08:00")
    _create_and_lease_ticket(
        client,
        workflow_id="wf_issue_runtime",
        ticket_id="tkt_issue_runtime",
        node_id="node_issue_runtime",
    )

    assert (
        main(
            [
                "issue-bootstrap",
                "--worker-id",
                "emp_frontend_2",
                "--ttl-sec",
                "120",
                "--issued-by",
                "ops@example.com",
            ]
        )
        == 0
    )
    bootstrap_output = json.loads(capsys.readouterr().out)

    repository = client.app.state.repository
    with repository.transaction() as connection:
        repository.revoke_worker_bootstrap_issues(
            connection,
            issue_id=bootstrap_output["issue_id"],
            revoked_at=datetime.fromisoformat("2026-03-28T10:01:00+08:00"),
        )

    issue_backed_response = client.get(
        "/api/v1/worker-runtime/assignments",
        headers={"X-Boardroom-Worker-Bootstrap": bootstrap_output["bootstrap_token"]},
    )
    legacy_response = client.get(
        "/api/v1/worker-runtime/assignments",
        headers=_worker_bootstrap_headers(issued_at="2026-03-28T10:01:00+08:00", ttl_sec=120),
    )

    assert issue_backed_response.status_code == 401
    assert legacy_response.status_code == 200
