from __future__ import annotations

import json
from datetime import datetime


def test_worker_admin_auth_cli_issue_token_prints_usable_signed_token(monkeypatch, capsys):
    monkeypatch.setenv("BOARDROOM_OS_WORKER_ADMIN_SIGNING_SECRET", "operator-secret")

    from app.core.worker_admin_tokens import validate_worker_admin_token
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

    assert exit_code == 0
    assert output["operator_id"] == "tenant.admin@example.com"
    assert output["role"] == "scope_admin"
    assert output["tenant_id"] == "tenant_blue"
    assert output["workspace_id"] == "ws_design"
    assert output["operator_token"]
    assert claims.operator_id == "tenant.admin@example.com"
    assert claims.role == "scope_admin"
    assert claims.tenant_id == "tenant_blue"
    assert claims.workspace_id == "ws_design"


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
