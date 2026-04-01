from __future__ import annotations

import base64
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

import pytest
from fastapi.testclient import TestClient

from app.core.context_compiler import compile_and_persist_execution_artifacts
from app.core.constants import (
    APPROVAL_STATUS_APPROVED,
    APPROVAL_STATUS_MODIFIED_CONSTRAINTS,
    APPROVAL_STATUS_OPEN,
    APPROVAL_STATUS_REJECTED,
    BLOCKING_REASON_BOARD_REJECTED,
    BLOCKING_REASON_BOARD_REVIEW_REQUIRED,
    BLOCKING_REASON_MODIFY_CONSTRAINTS,
    EVENT_BOARD_REVIEW_APPROVED,
    EVENT_BOARD_REVIEW_REJECTED,
    EVENT_BOARD_REVIEW_REQUIRED,
    EVENT_ARTIFACT_CLEANUP_COMPLETED,
    EVENT_CIRCUIT_BREAKER_OPENED,
    EVENT_INCIDENT_OPENED,
    EVENT_INCIDENT_RECOVERY_STARTED,
    EVENT_SYSTEM_INITIALIZED,
    EVENT_TICKET_CANCELLED,
    EVENT_TICKET_CANCEL_REQUESTED,
    EVENT_TICKET_COMPLETED,
    EVENT_TICKET_CREATED,
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

    import app.core.artifact_store as artifact_store_module

    monkeypatch.setattr(
        artifact_store_module,
        "build_s3_compatible_object_store_client",
        lambda settings: fake_client,
    )
    from app.main import create_app
    with TestClient(create_app()) as client:
        yield client, fake_client


def _project_init_payload(goal: str, budget_cap: int = 500000) -> dict:
    return {
        "north_star_goal": goal,
        "hard_constraints": ["Keep governance explicit."],
        "budget_cap": budget_cap,
        "deadline_at": None,
    }


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
                role_type,
                "{}",
                "{}",
                "{}",
                "ACTIVE",
                1,
                provider_id,
                json.dumps(role_profile_refs or ["ui_designer_primary"], sort_keys=True),
                "2026-03-28T10:00:00+08:00",
                1,
            ),
        )


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
    if result_status == "failed":
        result_payload["failure_kind"] = "RUNTIME_ERROR"
        result_payload["failure_message"] = "Structured runtime result reported failure."
        result_payload["failure_detail"] = {"step": "render", "exit_code": 1}
    if include_review_request:
        result_payload["review_request"] = _ticket_complete_payload(
            workflow_id=workflow_id,
            ticket_id=ticket_id,
            node_id=node_id,
            include_review_request=True,
        )["review_request"]
    return result_payload


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
    role_profile_ref: str = "ui_designer_primary",
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
    tenant_id: str | None = None,
    workspace_id: str | None = None,
) -> dict:
    payload = {
        "ticket_id": ticket_id,
        "workflow_id": workflow_id,
        "node_id": node_id,
        "parent_ticket_id": None,
        "attempt_no": attempt_no,
        "role_profile_ref": role_profile_ref,
        "constraints_ref": "global_constraints_v3",
        "input_artifact_refs": ["art://inputs/brief.md", "art://inputs/brand-guide.md"],
        "context_query_plan": {
            "keywords": ["homepage", "brand", "visual"],
            "semantic_queries": ["approved visual direction"],
            "max_context_tokens": 3000,
        },
        "acceptance_criteria": [
            "Must satisfy approved visual direction",
            "Must produce 2 options",
            "Must include rationale and risks",
        ],
        "output_schema_ref": "ui_milestone_review",
        "output_schema_version": 1,
        "allowed_tools": ["read_artifact", "write_artifact", "image_gen"],
        "allowed_write_set": allowed_write_set or ["artifacts/ui/homepage/*", "reports/review/*"],
        "lease_timeout_sec": lease_timeout_sec,
        "retry_budget": retry_budget,
        "priority": "high",
        "timeout_sla_sec": 1800,
        "deadline_at": "2026-03-28T18:00:00+08:00",
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
    return payload


def _ticket_start_payload(
    workflow_id: str = "wf_seed",
    ticket_id: str = "tkt_visual_001",
    node_id: str = "node_homepage_visual",
    started_by: str = "emp_frontend_2",
) -> dict:
    return {
        "workflow_id": workflow_id,
        "ticket_id": ticket_id,
        "node_id": node_id,
        "started_by": started_by,
        "idempotency_key": f"ticket-start:{workflow_id}:{ticket_id}",
    }


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
) -> dict:
    return {
        "workflow_id": workflow_id,
        "ticket_id": ticket_id,
        "node_id": node_id,
        "failed_by": "emp_frontend_2",
        "failure_kind": failure_kind,
        "failure_message": failure_message,
        "failure_detail": failure_detail or {"step": "render", "exit_code": 1},
        "idempotency_key": f"ticket-fail:{workflow_id}:{ticket_id}:{failure_kind}",
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


def _create_and_lease_ticket(
    client,
    workflow_id: str = "wf_seed",
    ticket_id: str = "tkt_visual_001",
    node_id: str = "node_homepage_visual",
    attempt_no: int = 1,
    leased_by: str = "emp_frontend_2",
    lease_timeout_sec: int = 600,
    role_profile_ref: str = "ui_designer_primary",
    retry_budget: int = 2,
    on_timeout: str = "retry",
    on_schema_error: str = "retry",
    on_repeat_failure: str = "escalate_ceo",
    repeat_failure_threshold: int = 2,
    timeout_repeat_threshold: int = 2,
    timeout_backoff_multiplier: float = 1.5,
    timeout_backoff_cap_multiplier: float = 2.0,
    allowed_write_set: list[str] | None = None,
    tenant_id: str | None = None,
    workspace_id: str | None = None,
) -> None:
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
            tenant_id=tenant_id,
            workspace_id=workspace_id,
        ),
    )
    assert create_response.status_code == 200
    assert create_response.json()["status"] == "ACCEPTED"

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
    role_profile_ref: str = "ui_designer_primary",
    retry_budget: int = 2,
    on_timeout: str = "retry",
    on_schema_error: str = "retry",
    on_repeat_failure: str = "escalate_ceo",
    repeat_failure_threshold: int = 2,
    timeout_repeat_threshold: int = 2,
    timeout_backoff_multiplier: float = 1.5,
    timeout_backoff_cap_multiplier: float = 2.0,
    allowed_write_set: list[str] | None = None,
    tenant_id: str | None = None,
    workspace_id: str | None = None,
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
        tenant_id=tenant_id,
        workspace_id=workspace_id,
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
    assert employees[1]["role_profile_refs"] == ["ui_designer_primary"]


def test_project_init_returns_real_command_ack(client):
    response = client.post("/api/v1/commands/project-init", json=_project_init_payload("Ship MVP A"))

    assert response.status_code == 200
    body = response.json()
    assert body["command_id"].startswith("cmd_")
    assert body["idempotency_key"].startswith("project-init:")
    assert body["status"] == "ACCEPTED"
    assert body["received_at"]


def test_system_initialized_is_written_only_once(client):
    client.post("/api/v1/commands/project-init", json=_project_init_payload("Ship MVP A"))
    duplicate = client.post("/api/v1/commands/project-init", json=_project_init_payload("Ship MVP A"))

    repository = client.app.state.repository
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


def test_ticket_create_persists_explicit_tenant_and_workspace_and_matches_workflow(client):
    workflow_response = client.post(
        "/api/v1/commands/project-init",
        json={
            **_project_init_payload("Ship scoped MVP"),
            "tenant_id": "tenant_blue",
            "workspace_id": "ws_design",
        },
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
    assert ticket_projection["tenant_id"] == "tenant_blue"
    assert ticket_projection["workspace_id"] == "ws_design"


def test_dashboard_returns_latest_active_workflow(client):
    client.post("/api/v1/commands/project-init", json=_project_init_payload("Ship MVP A", budget_cap=500000))
    client.post("/api/v1/commands/project-init", json=_project_init_payload("Ship MVP B", budget_cap=750000))

    response = client.get("/api/v1/projections/dashboard")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["active_workflow"]["north_star_goal"] == "Ship MVP B"
    assert data["ops_strip"]["budget_total"] == 750000
    assert isinstance(data["pipeline_summary"]["phases"], list)


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
    assert (
        first_body["compiled_execution_package"]["execution"]["output_schema_ref"]
        == "ui_milestone_review"
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
    assert len(grants) >= 7
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
    assert artifact_access["kind"] == "IMAGE"
    assert artifact_access["preview_kind"] == "INLINE_MEDIA"
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
    result_payload = _ticket_result_submit_payload(
        workflow_id="wf_worker_runtime",
        ticket_id="tkt_worker_token_result",
        node_id="node_worker_token_result",
        artifact_refs=["art://worker/runtime-token-option-a.json"],
        payload={
            "summary": "Worker runtime produced a structured result through signed command URLs.",
            "recommended_option_id": "option_a",
            "options": [
                {
                    "option_id": "option_a",
                    "label": "Option A",
                    "summary": "Single structured worker option.",
                    "artifact_refs": ["art://worker/runtime-token-option-a.json"],
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

    assert start_response.status_code == 200
    assert heartbeat_response.status_code == 200
    assert result_response.status_code == 200
    assert ticket_projection["status"] == TICKET_STATUS_COMPLETED
    assert artifact_record is not None
    assert artifact_record["materialization_status"] == "MATERIALIZED"


def test_worker_runtime_delivery_routes_reject_workspace_mismatch_and_log_it(
    client,
    set_ticket_time,
    monkeypatch,
):
    monkeypatch.setenv("BOARDROOM_OS_WORKER_BOOTSTRAP_SIGNING_SECRET", "bootstrap-secret")
    monkeypatch.setenv("BOARDROOM_OS_WORKER_DELIVERY_SIGNING_SECRET", "delivery-secret")
    set_ticket_time("2026-03-28T10:00:00+08:00")
    workflow_response = client.post(
        "/api/v1/commands/project-init",
        json={
            **_project_init_payload("Delivery scope workflow"),
            "tenant_id": "tenant_scope",
            "workspace_id": "ws_scope",
        },
    )
    workflow_id = workflow_response.json()["causation_hint"].split(":", 1)[1]
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
    assert node_projection["status"] == NODE_STATUS_COMPLETED


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
                written_artifacts=[
                    {
                        "path": "reports/ops/runtime-bundle.zip",
                        "artifact_ref": artifact_ref,
                        "kind": "BINARY",
                        "media_type": "application/zip",
                        "upload_session_id": session_id,
                    }
                ],
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


def test_incident_resolve_restore_and_retry_rejects_when_retry_budget_is_exhausted(client, set_ticket_time):
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

    assert response.status_code == 200
    assert response.json()["status"] == "REJECTED"
    assert "retry budget" in response.json()["reason"].lower()
    assert incident_response.json()["data"]["incident"]["status"] == "OPEN"
    assert repository.count_events_by_type(EVENT_TICKET_RETRY_SCHEDULED) == 1


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
    assert dashboard_response.json()["data"]["ops_strip"]["provider_health_summary"] == "DEGRADED"
    assert dashboard_response.json()["data"]["inbox_counts"]["provider_alerts"] == 1
    incident_items = [
        item for item in inbox_response.json()["data"]["items"] if item["item_type"] == "PROVIDER_INCIDENT"
    ]
    assert len(incident_items) == 1
    assert incident_response.json()["data"]["incident"]["provider_id"] == "prov_openai_compat"
    assert incident_response.json()["data"]["incident"]["incident_type"] == "PROVIDER_EXECUTION_PAUSED"
    assert incident_response.json()["data"]["incident"]["payload"]["pause_reason"] == "PROVIDER_RATE_LIMITED"


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


def test_incident_resolve_restore_and_retry_latest_failure_rejects_when_retry_budget_is_exhausted(
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

    assert resolve_response.status_code == 200
    assert resolve_response.json()["status"] == "REJECTED"
    assert "retry budget" in resolve_response.json()["reason"].lower()


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
                {"employee_id": "emp_frontend_2", "role_profile_refs": ["ui_designer_primary"]},
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
        role_profile_ref="ui_designer_primary",
    )
    client.post(
        "/api/v1/commands/ticket-create",
        json=_ticket_create_payload(
            workflow_id="wf_busy",
            ticket_id="tkt_pending",
            node_id="node_pending",
            role_profile_ref="ui_designer_primary",
        ),
    )

    set_ticket_time("2026-03-28T10:05:00+08:00")
    response = client.post(
        "/api/v1/commands/scheduler-tick",
        json=_scheduler_tick_payload(
            workers=[
                {"employee_id": "emp_frontend_2", "role_profile_refs": ["ui_designer_primary"]},
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
    assert dashboard_response.json()["data"]["pipeline_summary"]["blocked_node_ids"] == [
        "node_homepage_visual"
    ]


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
    assert fix_created_spec["role_profile_ref"] == "ui_designer_primary"
    assert fix_created_spec["output_schema_ref"] == "ui_milestone_review"
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
    assert body["compile_summary"] is None
    assert body["compiled_context_bundle"] is None
    assert body["compile_manifest"] is None


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


def test_modify_constraints_command_resolves_open_approval(client):
    approval = _seed_review_request(client, workflow_id="wf_modify")

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
            "idempotency_key": f"board-modify:{approval['approval_id']}:1",
        },
    )

    updated = client.app.state.repository.get_approval_by_review_pack_id(approval["review_pack_id"])
    review_ticket_id = approval["payload"]["review_pack"]["subject"]["source_ticket_id"]
    ticket_projection = client.app.state.repository.get_current_ticket_projection(review_ticket_id)
    node_projection = client.app.state.repository.get_current_node_projection(
        "wf_modify",
        "node_homepage_visual",
    )
    assert response.status_code == 200
    assert response.json()["status"] == "ACCEPTED"
    assert updated["status"] == APPROVAL_STATUS_MODIFIED_CONSTRAINTS
    assert updated["payload"]["resolution"]["decision_action"] == "MODIFY_CONSTRAINTS"
    assert ticket_projection["status"] == TICKET_STATUS_REWORK_REQUIRED
    assert ticket_projection["blocking_reason_code"] == BLOCKING_REASON_MODIFY_CONSTRAINTS
    assert node_projection["status"] == NODE_STATUS_REWORK_REQUIRED
    assert node_projection["blocking_reason_code"] == BLOCKING_REASON_MODIFY_CONSTRAINTS


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
    with repository.transaction() as connection:
        connection.execute(
            "UPDATE ticket_projection SET status = ?, blocking_reason_code = NULL WHERE ticket_id = ?",
            (TICKET_STATUS_COMPLETED, "tkt_visual_001"),
        )
        connection.execute(
            """
            UPDATE node_projection
            SET status = ?, blocking_reason_code = NULL
            WHERE workflow_id = ? AND node_id = ?
            """,
            (NODE_STATUS_COMPLETED, "wf_guard", "node_homepage_visual"),
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
    assert repository.count_events_by_type(EVENT_SYSTEM_INITIALIZED) == 0


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
