from __future__ import annotations

import json
from datetime import datetime


def test_worker_admin_auth_cli_issue_token_prints_usable_signed_token_and_persists_issue(
    monkeypatch, capsys, db_path
):
    monkeypatch.setenv("BOARDROOM_OS_WORKER_ADMIN_SIGNING_SECRET", "operator-secret")

    from app.core.worker_admin_tokens import validate_worker_admin_token
    from app.db.repository import ControlPlaneRepository
    from app.worker_admin_auth_cli import main

    exit_code = main(
        [
            "issue-token",
            "--operator-id",
            "tenant.admin@example.com",
            "--role",
            "scope_admin",
            "--tenant-id",
            "tenant_blue",
            "--workspace-id",
            "ws_design",
            "--ttl-sec",
            "120",
        ]
    )
    output = json.loads(capsys.readouterr().out)

    claims = validate_worker_admin_token(
        output["operator_token"],
        signing_secret="operator-secret",
        at=datetime.fromisoformat(output["issued_at"]),
    )
    repository = ControlPlaneRepository(db_path, 1000)
    repository.initialize()
    token_issue = repository.get_worker_admin_token_issue(output["token_id"])

    assert exit_code == 0
    assert output["operator_id"] == "tenant.admin@example.com"
    assert output["role"] == "scope_admin"
    assert output["tenant_id"] == "tenant_blue"
    assert output["workspace_id"] == "ws_design"
    assert output["token_id"].startswith("wop_")
    assert output["operator_token"]
    assert claims.token_id == output["token_id"]
    assert claims.operator_id == "tenant.admin@example.com"
    assert claims.role == "scope_admin"
    assert claims.tenant_id == "tenant_blue"
    assert claims.workspace_id == "ws_design"
    assert token_issue is not None
    assert token_issue["token_id"] == output["token_id"]
    assert token_issue["operator_id"] == "tenant.admin@example.com"
    assert token_issue["role"] == "scope_admin"
    assert token_issue["issued_via"] == "worker_admin_auth_cli"


def test_worker_admin_auth_cli_rejects_partial_scope_without_traceback(monkeypatch, capsys):
    monkeypatch.setenv("BOARDROOM_OS_WORKER_ADMIN_SIGNING_SECRET", "operator-secret")

    from app.worker_admin_auth_cli import main

    exit_code = main(
        [
            "issue-token",
            "--operator-id",
            "tenant.admin@example.com",
            "--role",
            "scope_admin",
            "--tenant-id",
            "tenant_blue",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "workspace" in captured.err
    assert "Traceback" not in captured.err


def test_worker_admin_auth_cli_rejects_excessive_ttl(monkeypatch, capsys):
    monkeypatch.setenv("BOARDROOM_OS_WORKER_ADMIN_SIGNING_SECRET", "operator-secret")
    monkeypatch.setenv("BOARDROOM_OS_WORKER_ADMIN_MAX_TTL_SEC", "1800")

    from app.worker_admin_auth_cli import main

    exit_code = main(
        [
            "issue-token",
            "--operator-id",
            "ops@example.com",
            "--role",
            "platform_admin",
            "--ttl-sec",
            "7200",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "max TTL" in captured.err


def test_worker_admin_auth_cli_lists_and_revokes_tokens(monkeypatch, capsys, db_path):
    monkeypatch.setenv("BOARDROOM_OS_WORKER_ADMIN_SIGNING_SECRET", "operator-secret")

    from app.worker_admin_auth_cli import main

    issue_exit_code = main(
        [
            "issue-token",
            "--operator-id",
            "tenant.viewer@example.com",
            "--role",
            "scope_viewer",
            "--tenant-id",
            "tenant_blue",
            "--workspace-id",
            "ws_design",
            "--ttl-sec",
            "300",
        ]
    )
    issued = json.loads(capsys.readouterr().out)

    list_exit_code = main(
        [
            "list-tokens",
            "--tenant-id",
            "tenant_blue",
            "--workspace-id",
            "ws_design",
            "--active-only",
        ]
    )
    listed = json.loads(capsys.readouterr().out)

    revoke_exit_code = main(
        [
            "revoke-token",
            "--token-id",
            issued["token_id"],
            "--revoked-by",
            "ops@example.com",
            "--reason",
            "tenant offboarding",
        ]
    )
    revoked = json.loads(capsys.readouterr().out)

    assert issue_exit_code == 0
    assert list_exit_code == 0
    assert revoke_exit_code == 0
    assert listed["count"] == 1
    assert listed["tokens"][0]["token_id"] == issued["token_id"]
    assert revoked["token_id"] == issued["token_id"]
    assert revoked["revoked_by"] == "ops@example.com"
    assert revoked["revoke_reason"] == "tenant offboarding"
