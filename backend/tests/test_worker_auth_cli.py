from __future__ import annotations

import base64
import json
from datetime import datetime
from urllib.parse import parse_qs, urlsplit


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


def _create_leased_worker_ticket(client, *, workflow_id: str, ticket_id: str, node_id: str) -> None:
    client.post(
        "/api/v1/commands/ticket-create",
        json={
            "ticket_id": ticket_id,
            "workflow_id": workflow_id,
            "node_id": node_id,
            "parent_ticket_id": None,
            "attempt_no": 1,
            "role_profile_ref": "ui_designer_primary",
            "constraints_ref": "global_constraints_v3",
            "input_artifact_refs": ["art://inputs/brief.md"],
            "context_query_plan": {
                "keywords": ["homepage"],
                "semantic_queries": ["approved direction"],
                "max_context_tokens": 3000,
            },
            "acceptance_criteria": ["Must produce a structured result"],
            "output_schema_ref": "ui_milestone_review",
            "output_schema_version": 1,
            "allowed_tools": ["read_artifact", "write_artifact"],
            "allowed_write_set": ["artifacts/ui/homepage/*"],
            "lease_timeout_sec": 600,
            "retry_budget": 1,
            "priority": "high",
            "timeout_sla_sec": 1800,
            "deadline_at": "2026-03-28T18:00:00+08:00",
            "escalation_policy": {
                "on_timeout": "retry",
                "on_schema_error": "retry",
                "on_repeat_failure": "escalate_ceo",
            },
            "tenant_id": "tenant_default",
            "workspace_id": "ws_default",
            "idempotency_key": f"ticket-create:{workflow_id}:{ticket_id}",
        },
    )
    client.post(
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


def _seed_input_artifact(
    client,
    *,
    artifact_ref: str = "art://inputs/brief.md",
    logical_path: str = "artifacts/inputs/brief.md",
    content: str = "# Brief\n\nMaterialized input.\n",
) -> None:
    repository = client.app.state.repository
    artifact_store = client.app.state.artifact_store
    materialized = artifact_store.materialize_text(logical_path, content)
    with repository.transaction() as connection:
        repository.save_artifact_record(
            connection,
            artifact_ref=artifact_ref,
            workflow_id="wf_seed_inputs",
            ticket_id="tkt_seed_inputs",
            node_id="node_seed_inputs",
            logical_path=logical_path,
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


def _bootstrap_worker_execution_package(client, bootstrap_token: str) -> tuple[dict, dict]:
    assignments_response = client.get(
        "/api/v1/worker-runtime/assignments",
        headers={"X-Boardroom-Worker-Bootstrap": bootstrap_token},
    )
    assignments_data = assignments_response.json()["data"]
    execution_package_url = assignments_data["assignments"][0]["execution_package_url"]
    execution_package_response = client.get(_local_path_from_url(execution_package_url))
    return assignments_data, execution_package_response.json()["data"]


def test_worker_auth_cli_issue_bootstrap_prints_usable_token(db_path, monkeypatch, capsys):
    monkeypatch.setenv("BOARDROOM_OS_WORKER_BOOTSTRAP_SIGNING_SECRET", "bootstrap-secret")

    from app.worker_auth_cli import main

    exit_code = main(["issue-bootstrap", "--worker-id", "emp_frontend_2", "--ttl-sec", "120"])
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert output["worker_id"] == "emp_frontend_2"
    assert output["credential_version"] == 1
    assert output["tenant_id"] == "tenant_default"
    assert output["workspace_id"] == "ws_default"
    assert output["bootstrap_token"]
    assert output["expires_at"]


def test_worker_auth_cli_rotate_bootstrap_bumps_credential_version(db_path, monkeypatch, capsys):
    monkeypatch.setenv("BOARDROOM_OS_WORKER_BOOTSTRAP_SIGNING_SECRET", "bootstrap-secret")

    from app.worker_auth_cli import main

    assert main(["issue-bootstrap", "--worker-id", "emp_frontend_2"]) == 0
    capsys.readouterr()

    exit_code = main(["rotate-bootstrap", "--worker-id", "emp_frontend_2", "--ttl-sec", "120"])
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert output["worker_id"] == "emp_frontend_2"
    assert output["credential_version"] == 2
    assert output["tenant_id"] == "tenant_default"
    assert output["workspace_id"] == "ws_default"
    assert output["bootstrap_token"]


def test_worker_auth_cli_list_bindings_returns_all_worker_scopes(db_path, monkeypatch, capsys):
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

    exit_code = main(["list-bindings", "--worker-id", "emp_frontend_2"])
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert output["count"] == 2
    assert {(
        binding["tenant_id"],
        binding["workspace_id"],
    ) for binding in output["bindings"]} == {
        ("tenant_default", "ws_default"),
        ("tenant_blue", "ws_design"),
    }


def test_worker_auth_cli_requires_explicit_scope_when_worker_has_multiple_bindings(
    db_path,
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

    assert main(["issue-bootstrap", "--worker-id", "emp_frontend_2"]) == 1
    assert "explicitly" in capsys.readouterr().err.lower()

    assert main(["rotate-bootstrap", "--worker-id", "emp_frontend_2"]) == 1
    assert "explicitly" in capsys.readouterr().err.lower()

    assert main(["revoke-bootstrap", "--worker-id", "emp_frontend_2"]) == 1
    assert "explicitly" in capsys.readouterr().err.lower()


def test_worker_auth_cli_list_delivery_grants_supports_tenant_and_workspace_filters(
    client,
    db_path,
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
    _create_leased_worker_ticket(
        client,
        workflow_id="wf_cli_scope",
        ticket_id="tkt_cli_scope",
        node_id="node_cli_scope",
    )

    assert main(["issue-bootstrap", "--worker-id", "emp_frontend_2", "--ttl-sec", "120"]) == 0
    bootstrap_output = json.loads(capsys.readouterr().out)
    _bootstrap_worker_execution_package(client, bootstrap_output["bootstrap_token"])

    exit_code = main(
        [
            "list-delivery-grants",
            "--tenant-id",
            "tenant_default",
            "--workspace-id",
            "ws_default",
        ]
    )
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert output["count"] > 0
    assert all(grant["tenant_id"] == "tenant_default" for grant in output["grants"])
    assert all(grant["workspace_id"] == "ws_default" for grant in output["grants"])


def test_worker_auth_cli_list_sessions_filters_by_scope(
    client,
    db_path,
    set_ticket_time,
    monkeypatch,
    capsys,
):
    monkeypatch.setenv("BOARDROOM_OS_WORKER_BOOTSTRAP_SIGNING_SECRET", "bootstrap-secret")
    monkeypatch.setenv("BOARDROOM_OS_WORKER_SESSION_TTL_SEC", "600")

    from app.worker_auth_cli import main

    set_ticket_time("2026-03-28T10:00:00+08:00")
    _create_leased_worker_ticket(
        client,
        workflow_id="wf_cli_sessions",
        ticket_id="tkt_cli_sessions",
        node_id="node_cli_sessions",
    )

    assert main(["issue-bootstrap", "--worker-id", "emp_frontend_2", "--ttl-sec", "120"]) == 0
    bootstrap_output = json.loads(capsys.readouterr().out)
    assignments_response = client.get(
        "/api/v1/worker-runtime/assignments",
        headers={"X-Boardroom-Worker-Bootstrap": bootstrap_output["bootstrap_token"]},
    )
    assert assignments_response.status_code == 200

    exit_code = main(
        [
            "list-sessions",
            "--worker-id",
            "emp_frontend_2",
            "--tenant-id",
            "tenant_default",
            "--workspace-id",
            "ws_default",
        ]
    )
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert output["count"] == 1
    assert output["sessions"][0]["worker_id"] == "emp_frontend_2"
    assert output["sessions"][0]["tenant_id"] == "tenant_default"
    assert output["sessions"][0]["workspace_id"] == "ws_default"


def test_worker_auth_cli_list_auth_rejections_returns_scope_filtered_rows(
    client,
    db_path,
    set_ticket_time,
    monkeypatch,
    capsys,
):
    monkeypatch.setenv("BOARDROOM_OS_WORKER_BOOTSTRAP_SIGNING_SECRET", "bootstrap-secret")
    monkeypatch.setenv("BOARDROOM_OS_WORKER_SESSION_TTL_SEC", "600")

    from app.worker_auth_cli import main

    set_ticket_time("2026-03-28T10:00:00+08:00")
    _create_leased_worker_ticket(
        client,
        workflow_id="wf_cli_rejections",
        ticket_id="tkt_cli_rejections",
        node_id="node_cli_rejections",
    )

    assert main(["issue-bootstrap", "--worker-id", "emp_frontend_2", "--ttl-sec", "120"]) == 0
    bootstrap_output = json.loads(capsys.readouterr().out)
    assignments_response = client.get(
        "/api/v1/worker-runtime/assignments",
        headers={"X-Boardroom-Worker-Bootstrap": bootstrap_output["bootstrap_token"]},
    )
    session_token = assignments_response.json()["data"]["session_token"]

    repository = client.app.state.repository
    with repository.transaction() as connection:
        connection.execute(
            """
            UPDATE ticket_projection
            SET workspace_id = ?
            WHERE ticket_id = ?
            """,
            ("ws_other", "tkt_cli_rejections"),
        )

    rejected_response = client.get(
        "/api/v1/worker-runtime/assignments",
        headers={"X-Boardroom-Worker-Session": session_token},
    )
    assert rejected_response.status_code == 403

    exit_code = main(
        [
            "list-auth-rejections",
            "--worker-id",
            "emp_frontend_2",
            "--tenant-id",
            "tenant_default",
            "--workspace-id",
            "ws_default",
            "--route-family",
            "assignments",
        ]
    )
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert output["count"] == 1
    assert output["rejections"][0]["route_family"] == "assignments"
    assert output["rejections"][0]["reason_code"] == "workspace_mismatch"


def test_worker_auth_cli_revoke_bootstrap_invalidates_old_token(
    client,
    db_path,
    set_ticket_time,
    monkeypatch,
    capsys,
):
    monkeypatch.setenv("BOARDROOM_OS_WORKER_BOOTSTRAP_SIGNING_SECRET", "bootstrap-secret")
    monkeypatch.setenv("BOARDROOM_OS_WORKER_SESSION_TTL_SEC", "600")
    monkeypatch.setenv("BOARDROOM_OS_WORKER_DELIVERY_SIGNING_SECRET", "delivery-secret")

    from app.worker_auth_cli import main

    set_ticket_time("2026-03-28T10:00:00+08:00")
    client.post(
        "/api/v1/commands/ticket-create",
        json={
            "ticket_id": "tkt_cli_revoke_bootstrap",
            "workflow_id": "wf_cli_revoke_bootstrap",
            "node_id": "node_cli_revoke_bootstrap",
            "parent_ticket_id": None,
            "attempt_no": 1,
            "role_profile_ref": "ui_designer_primary",
            "constraints_ref": "global_constraints_v3",
            "input_artifact_refs": ["art://inputs/brief.md"],
            "context_query_plan": {
                "keywords": ["homepage"],
                "semantic_queries": ["approved direction"],
                "max_context_tokens": 3000,
            },
            "acceptance_criteria": ["Must produce a structured result"],
            "output_schema_ref": "ui_milestone_review",
            "output_schema_version": 1,
            "allowed_tools": ["read_artifact", "write_artifact"],
            "allowed_write_set": ["artifacts/ui/homepage/*"],
            "lease_timeout_sec": 600,
            "retry_budget": 1,
            "priority": "high",
            "timeout_sla_sec": 1800,
            "deadline_at": "2026-03-28T18:00:00+08:00",
            "escalation_policy": {
                "on_timeout": "retry",
                "on_schema_error": "retry",
                "on_repeat_failure": "escalate_ceo",
            },
            "idempotency_key": "ticket-create:wf_cli_revoke_bootstrap:tkt_cli_revoke_bootstrap",
        },
    )
    client.post(
        "/api/v1/commands/ticket-lease",
        json={
            "workflow_id": "wf_cli_revoke_bootstrap",
            "ticket_id": "tkt_cli_revoke_bootstrap",
            "node_id": "node_cli_revoke_bootstrap",
            "leased_by": "emp_frontend_2",
            "lease_timeout_sec": 600,
            "idempotency_key": "ticket-lease:wf_cli_revoke_bootstrap:tkt_cli_revoke_bootstrap",
        },
    )

    assert main(["issue-bootstrap", "--worker-id", "emp_frontend_2", "--ttl-sec", "120"]) == 0
    issued_output = json.loads(capsys.readouterr().out)

    assert main(["revoke-bootstrap", "--worker-id", "emp_frontend_2"]) == 0
    capsys.readouterr()

    response = client.get(
        "/api/v1/worker-runtime/assignments",
        headers={"X-Boardroom-Worker-Bootstrap": issued_output["bootstrap_token"]},
    )

    assert response.status_code == 401


def test_worker_auth_cli_revoke_session_only_revokes_target_session(
    client,
    db_path,
    set_ticket_time,
    monkeypatch,
    capsys,
):
    monkeypatch.setenv("BOARDROOM_OS_WORKER_BOOTSTRAP_SIGNING_SECRET", "bootstrap-secret")
    monkeypatch.setenv("BOARDROOM_OS_WORKER_SESSION_TTL_SEC", "600")
    monkeypatch.setenv("BOARDROOM_OS_WORKER_DELIVERY_SIGNING_SECRET", "delivery-secret")

    from app.worker_auth_cli import main

    set_ticket_time("2026-03-28T10:00:00+08:00")
    client.post(
        "/api/v1/commands/ticket-create",
        json={
            "ticket_id": "tkt_cli_revoke_session",
            "workflow_id": "wf_cli_revoke_session",
            "node_id": "node_cli_revoke_session",
            "parent_ticket_id": None,
            "attempt_no": 1,
            "role_profile_ref": "ui_designer_primary",
            "constraints_ref": "global_constraints_v3",
            "input_artifact_refs": ["art://inputs/brief.md"],
            "context_query_plan": {
                "keywords": ["homepage"],
                "semantic_queries": ["approved direction"],
                "max_context_tokens": 3000,
            },
            "acceptance_criteria": ["Must produce a structured result"],
            "output_schema_ref": "ui_milestone_review",
            "output_schema_version": 1,
            "allowed_tools": ["read_artifact", "write_artifact"],
            "allowed_write_set": ["artifacts/ui/homepage/*"],
            "lease_timeout_sec": 600,
            "retry_budget": 1,
            "priority": "high",
            "timeout_sla_sec": 1800,
            "deadline_at": "2026-03-28T18:00:00+08:00",
            "escalation_policy": {
                "on_timeout": "retry",
                "on_schema_error": "retry",
                "on_repeat_failure": "escalate_ceo",
            },
            "idempotency_key": "ticket-create:wf_cli_revoke_session:tkt_cli_revoke_session",
        },
    )
    client.post(
        "/api/v1/commands/ticket-lease",
        json={
            "workflow_id": "wf_cli_revoke_session",
            "ticket_id": "tkt_cli_revoke_session",
            "node_id": "node_cli_revoke_session",
            "leased_by": "emp_frontend_2",
            "lease_timeout_sec": 600,
            "idempotency_key": "ticket-lease:wf_cli_revoke_session:tkt_cli_revoke_session",
        },
    )

    assert main(["issue-bootstrap", "--worker-id", "emp_frontend_2", "--ttl-sec", "120"]) == 0
    first_bootstrap = json.loads(capsys.readouterr().out)
    assert main(["issue-bootstrap", "--worker-id", "emp_frontend_2", "--ttl-sec", "120"]) == 0
    second_bootstrap = json.loads(capsys.readouterr().out)

    first_response = client.get(
        "/api/v1/worker-runtime/assignments",
        headers={"X-Boardroom-Worker-Bootstrap": first_bootstrap["bootstrap_token"]},
    )
    second_response = client.get(
        "/api/v1/worker-runtime/assignments",
        headers={"X-Boardroom-Worker-Bootstrap": second_bootstrap["bootstrap_token"]},
    )
    first_session = first_response.json()["data"]
    second_session = second_response.json()["data"]

    assert (
        main(
            [
                "revoke-session",
                "--session-id",
                first_session["session_id"],
                "--revoked-by",
                "ops@example.com",
                "--reason",
                "Manual session revoke from CLI test.",
            ]
        )
        == 0
    )
    output = json.loads(capsys.readouterr().out)

    revoked_response = client.get(
        "/api/v1/worker-runtime/assignments",
        headers={"X-Boardroom-Worker-Session": first_session["session_token"]},
    )
    surviving_response = client.get(
        "/api/v1/worker-runtime/assignments",
        headers={"X-Boardroom-Worker-Session": second_session["session_token"]},
    )

    repository = client.app.state.repository
    with repository.connection() as connection:
        session_row = repository.get_worker_session(first_session["session_id"], connection=connection)
        session_grants = repository.list_worker_delivery_grants(
            connection,
            session_id=first_session["session_id"],
        )

    assert output["session_id"] == first_session["session_id"]
    assert output["revoked_count"] == 1
    assert output["revoked_delivery_grant_count"] == len(session_grants)
    assert output["revoked_via"] == "worker_auth_cli"
    assert output["revoked_by"] == "ops@example.com"
    assert output["revoke_reason"] == "Manual session revoke from CLI test."
    assert session_row is not None
    assert session_row["revoked_via"] == "worker_auth_cli"
    assert session_row["revoked_by"] == "ops@example.com"
    assert session_row["revoke_reason"] == "Manual session revoke from CLI test."
    assert session_grants
    assert all(grant["revoked_via"] == "worker_auth_cli" for grant in session_grants)
    assert all(grant["revoked_by"] == "ops@example.com" for grant in session_grants)
    assert all(grant["revoke_reason"] == "Manual session revoke from CLI test." for grant in session_grants)
    assert revoked_response.status_code == 401
    assert surviving_response.status_code == 200


def test_worker_auth_cli_list_delivery_grants_returns_current_grants(
    client,
    db_path,
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
    _create_leased_worker_ticket(
        client,
        workflow_id="wf_cli_list_grants",
        ticket_id="tkt_cli_list_grants",
        node_id="node_cli_list_grants",
    )

    assert main(["issue-bootstrap", "--worker-id", "emp_frontend_2", "--ttl-sec", "120"]) == 0
    bootstrap_output = json.loads(capsys.readouterr().out)
    _, execution_package = _bootstrap_worker_execution_package(
        client,
        bootstrap_output["bootstrap_token"],
    )

    exit_code = main(["list-delivery-grants", "--ticket-id", "tkt_cli_list_grants"])
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert output["grants"]
    assert any(grant["scope"] == "execution_package" for grant in output["grants"])
    assert any(grant["artifact_action"] == "preview" for grant in output["grants"])
    assert execution_package["command_endpoints"]["ticket_start_url"]


def test_worker_auth_cli_revoke_delivery_grant_only_revokes_target_url(
    client,
    db_path,
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
    _create_leased_worker_ticket(
        client,
        workflow_id="wf_cli_revoke_grant",
        ticket_id="tkt_cli_revoke_grant",
        node_id="node_cli_revoke_grant",
    )

    assert main(["issue-bootstrap", "--worker-id", "emp_frontend_2", "--ttl-sec", "120"]) == 0
    bootstrap_output = json.loads(capsys.readouterr().out)
    _, execution_package = _bootstrap_worker_execution_package(
        client,
        bootstrap_output["bootstrap_token"],
    )
    context_payload = execution_package["compiled_execution_package"]["atomic_context_bundle"]["context_blocks"][0][
        "content_payload"
    ]
    preview_url = context_payload["preview_url"]
    content_url = context_payload["content_url"]
    preview_grant_id = _decode_worker_delivery_token_payload(
        _query_value(preview_url, "access_token") or ""
    )["grant_id"]

    exit_code = main(
        [
            "revoke-delivery-grant",
            "--grant-id",
            preview_grant_id,
            "--revoked-by",
            "ops@example.com",
            "--reason",
            "Manual single-URL revoke from CLI test.",
        ]
    )
    output = json.loads(capsys.readouterr().out)
    preview_response = client.get(_local_path_from_url(preview_url))
    content_response = client.get(_local_path_from_url(content_url))

    assert exit_code == 0
    assert output["revoked_count"] == 1
    assert output["revoked_via"] == "worker_auth_cli"
    assert output["revoked_by"] == "ops@example.com"
    assert output["revoke_reason"] == "Manual single-URL revoke from CLI test."
    repository = client.app.state.repository
    with repository.connection() as connection:
        grant_row = repository.get_worker_delivery_grant(preview_grant_id, connection=connection)
    assert grant_row is not None
    assert grant_row["revoked_via"] == "worker_auth_cli"
    assert grant_row["revoked_by"] == "ops@example.com"
    assert grant_row["revoke_reason"] == "Manual single-URL revoke from CLI test."
    assert preview_response.status_code == 401
    assert content_response.status_code == 200


def test_worker_auth_cli_create_binding_is_idempotent_and_list_bindings_returns_admin_fields(
    db_path,
    monkeypatch,
    capsys,
):
    monkeypatch.setenv("BOARDROOM_OS_WORKER_BOOTSTRAP_SIGNING_SECRET", "bootstrap-secret")

    from app.worker_auth_cli import main

    exit_code = main(
        [
            "create-binding",
            "--worker-id",
            "emp_frontend_2",
            "--tenant-id",
            "tenant_blue",
            "--workspace-id",
            "ws_design",
        ]
    )
    created_output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert created_output["tenant_id"] == "tenant_blue"
    assert created_output["workspace_id"] == "ws_design"

    exit_code = main(
        [
            "create-binding",
            "--worker-id",
            "emp_frontend_2",
            "--tenant-id",
            "tenant_blue",
            "--workspace-id",
            "ws_design",
        ]
    )
    second_output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert second_output == created_output

    exit_code = main(["list-bindings", "--worker-id", "emp_frontend_2"])
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    binding = output["bindings"][0]
    assert binding["tenant_id"] == "tenant_blue"
    assert binding["workspace_id"] == "ws_design"
    assert binding["active_session_count"] == 0
    assert binding["active_delivery_grant_count"] == 0
    assert binding["active_ticket_count"] == 0
    assert binding["latest_bootstrap_issue_at"] is None
    assert binding["latest_bootstrap_issue_source"] is None
    assert binding["cleanup_eligible"] is True


def test_worker_auth_cli_cleanup_bindings_supports_dry_run_and_removes_only_eligible_scope(
    db_path,
    monkeypatch,
    capsys,
):
    monkeypatch.setenv("BOARDROOM_OS_WORKER_BOOTSTRAP_SIGNING_SECRET", "bootstrap-secret")

    from app.worker_auth_cli import main

    assert (
        main(
            [
                "create-binding",
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
    assert (
        main(
            [
                "create-binding",
                "--worker-id",
                "emp_frontend_2",
                "--tenant-id",
                "tenant_green",
                "--workspace-id",
                "ws_ops",
            ]
        )
        == 0
    )
    capsys.readouterr()
    assert (
        main(
            [
                "issue-bootstrap",
                "--worker-id",
                "emp_frontend_2",
                "--tenant-id",
                "tenant_green",
                "--workspace-id",
                "ws_ops",
                "--ttl-sec",
                "120",
            ]
        )
        == 0
    )
    capsys.readouterr()

    exit_code = main(["cleanup-bindings", "--worker-id", "emp_frontend_2", "--dry-run"])
    dry_run_output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert dry_run_output["dry_run"] is True
    assert dry_run_output["deleted_count"] == 0
    assert {(
        binding["tenant_id"],
        binding["workspace_id"],
        binding["cleanup_eligible"],
    ) for binding in dry_run_output["bindings"]} == {
        ("tenant_blue", "ws_design", True),
        ("tenant_green", "ws_ops", False),
    }

    exit_code = main(["cleanup-bindings", "--worker-id", "emp_frontend_2"])
    cleanup_output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert cleanup_output["dry_run"] is False
    assert cleanup_output["deleted_count"] == 1

    exit_code = main(["list-bindings", "--worker-id", "emp_frontend_2"])
    remaining_output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert remaining_output["count"] == 1
    assert remaining_output["bindings"][0]["tenant_id"] == "tenant_green"
    assert remaining_output["bindings"][0]["workspace_id"] == "ws_ops"


def test_worker_auth_cli_issue_bootstrap_returns_issue_metadata_and_honors_ttl_policy(
    db_path,
    monkeypatch,
    capsys,
):
    monkeypatch.setenv("BOARDROOM_OS_WORKER_BOOTSTRAP_SIGNING_SECRET", "bootstrap-secret")
    monkeypatch.setenv("BOARDROOM_OS_WORKER_BOOTSTRAP_DEFAULT_TTL_SEC", "300")
    monkeypatch.setenv("BOARDROOM_OS_WORKER_BOOTSTRAP_MAX_TTL_SEC", "600")

    from app.worker_auth_cli import main

    exit_code = main(
        [
            "issue-bootstrap",
            "--worker-id",
            "emp_frontend_2",
            "--issued-by",
            "ops@example.com",
            "--reason",
            "Initial runtime bootstrap",
        ]
    )
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert output["issue_id"]
    assert output["issued_via"] == "worker_auth_cli"
    assert output["issued_by"] == "ops@example.com"
    assert output["reason"] == "Initial runtime bootstrap"

    assert main(["issue-bootstrap", "--worker-id", "emp_frontend_2", "--ttl-sec", "601"]) == 1
    assert "max" in capsys.readouterr().err.lower()


def test_worker_auth_cli_issue_bootstrap_rejects_tenant_outside_allowlist(
    db_path,
    monkeypatch,
    capsys,
):
    monkeypatch.setenv("BOARDROOM_OS_WORKER_BOOTSTRAP_SIGNING_SECRET", "bootstrap-secret")
    monkeypatch.setenv("BOARDROOM_OS_WORKER_BOOTSTRAP_ALLOWED_TENANT_IDS", "tenant_default")

    from app.worker_auth_cli import main

    assert (
        main(
            [
                "create-binding",
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
        == 1
    )
    assert "allow" in capsys.readouterr().err.lower()
