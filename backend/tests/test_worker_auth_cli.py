from __future__ import annotations

import json


def test_worker_auth_cli_issue_bootstrap_prints_usable_token(db_path, monkeypatch, capsys):
    monkeypatch.setenv("BOARDROOM_OS_WORKER_BOOTSTRAP_SIGNING_SECRET", "bootstrap-secret")

    from app.worker_auth_cli import main

    exit_code = main(["issue-bootstrap", "--worker-id", "emp_frontend_2", "--ttl-sec", "120"])
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert output["worker_id"] == "emp_frontend_2"
    assert output["credential_version"] == 1
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
    assert output["bootstrap_token"]


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

    assert main(["revoke-session", "--session-id", first_session["session_id"]]) == 0
    capsys.readouterr()

    revoked_response = client.get(
        "/api/v1/worker-runtime/assignments",
        headers={"X-Boardroom-Worker-Session": first_session["session_token"]},
    )
    surviving_response = client.get(
        "/api/v1/worker-runtime/assignments",
        headers={"X-Boardroom-Worker-Session": second_session["session_token"]},
    )

    assert revoked_response.status_code == 401
    assert surviving_response.status_code == 200
