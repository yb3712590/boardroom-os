from __future__ import annotations

import sqlite3
from datetime import datetime

from app.core.constants import DEFAULT_TENANT_ID, DEFAULT_WORKSPACE_ID
from app.db.repository import ControlPlaneRepository


def test_initialize_backfills_default_scope_for_legacy_rows(db_path):
    connection = sqlite3.connect(db_path)
    connection.execute(
        """
        CREATE TABLE workflow_projection (
            workflow_id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            north_star_goal TEXT NOT NULL,
            current_stage TEXT NOT NULL,
            status TEXT NOT NULL,
            budget_total INTEGER NOT NULL,
            budget_used INTEGER NOT NULL,
            board_gate_state TEXT NOT NULL,
            deadline_at TEXT,
            started_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            version INTEGER NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE ticket_projection (
            ticket_id TEXT PRIMARY KEY,
            workflow_id TEXT NOT NULL,
            node_id TEXT NOT NULL,
            status TEXT NOT NULL,
            lease_owner TEXT,
            lease_expires_at TEXT,
            started_at TEXT,
            last_heartbeat_at TEXT,
            heartbeat_expires_at TEXT,
            heartbeat_timeout_sec INTEGER,
            retry_count INTEGER NOT NULL DEFAULT 0,
            retry_budget INTEGER,
            timeout_sla_sec INTEGER,
            priority TEXT,
            last_failure_kind TEXT,
            last_failure_message TEXT,
            last_failure_fingerprint TEXT,
            blocking_reason_code TEXT,
            updated_at TEXT NOT NULL,
            version INTEGER NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE worker_bootstrap_state (
            worker_id TEXT PRIMARY KEY,
            credential_version INTEGER NOT NULL,
            revoked_before TEXT,
            rotated_at TEXT,
            updated_at TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE worker_session (
            session_id TEXT PRIMARY KEY,
            worker_id TEXT NOT NULL,
            issued_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL,
            revoked_at TEXT,
            credential_version INTEGER NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE worker_delivery_grant (
            grant_id TEXT PRIMARY KEY,
            scope TEXT NOT NULL,
            worker_id TEXT NOT NULL,
            session_id TEXT NOT NULL,
            credential_version INTEGER NOT NULL,
            ticket_id TEXT NOT NULL,
            artifact_ref TEXT,
            artifact_action TEXT,
            command_name TEXT,
            issued_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            revoked_at TEXT,
            revoke_reason TEXT
        )
        """
    )
    connection.execute(
        """
        INSERT INTO workflow_projection (
            workflow_id,
            title,
            north_star_goal,
            current_stage,
            status,
            budget_total,
            budget_used,
            board_gate_state,
            deadline_at,
            started_at,
            updated_at,
            version
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "wf_legacy",
            "Legacy workflow",
            "Legacy goal",
            "DISCOVERY",
            "ACTIVE",
            10,
            0,
            "OPEN",
            None,
            "2026-03-30T10:00:00+08:00",
            "2026-03-30T10:00:00+08:00",
            1,
        ),
    )
    connection.execute(
        """
        INSERT INTO ticket_projection (
            ticket_id,
            workflow_id,
            node_id,
            status,
            lease_owner,
            lease_expires_at,
            started_at,
            last_heartbeat_at,
            heartbeat_expires_at,
            heartbeat_timeout_sec,
            retry_count,
            retry_budget,
            timeout_sla_sec,
            priority,
            last_failure_kind,
            last_failure_message,
            last_failure_fingerprint,
            blocking_reason_code,
            updated_at,
            version
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "tkt_legacy",
            "wf_legacy",
            "node_legacy",
            "LEASED",
            "emp_frontend_2",
            "2026-03-30T10:30:00+08:00",
            None,
            None,
            None,
            600,
            0,
            1,
            1800,
            "high",
            None,
            None,
            None,
            None,
            "2026-03-30T10:00:00+08:00",
            1,
        ),
    )
    connection.execute(
        """
        INSERT INTO worker_bootstrap_state (
            worker_id,
            credential_version,
            revoked_before,
            rotated_at,
            updated_at
        ) VALUES (?, ?, ?, ?, ?)
        """,
        ("emp_frontend_2", 1, None, None, "2026-03-30T10:00:00+08:00"),
    )
    connection.execute(
        """
        INSERT INTO worker_session (
            session_id,
            worker_id,
            issued_at,
            expires_at,
            last_seen_at,
            revoked_at,
            credential_version
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "wsess_legacy",
            "emp_frontend_2",
            "2026-03-30T10:00:00+08:00",
            "2026-03-30T11:00:00+08:00",
            "2026-03-30T10:00:00+08:00",
            None,
            1,
        ),
    )
    connection.execute(
        """
        INSERT INTO worker_delivery_grant (
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
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "wgrant_legacy",
            "execution_package",
            "emp_frontend_2",
            "wsess_legacy",
            1,
            "tkt_legacy",
            None,
            None,
            None,
            "2026-03-30T10:00:00+08:00",
            "2026-03-30T11:00:00+08:00",
            None,
            None,
        ),
    )
    connection.commit()
    connection.close()

    repository = ControlPlaneRepository(db_path, 1000)
    repository.initialize()

    workflow = repository.get_workflow_projection("wf_legacy")
    ticket = repository.get_current_ticket_projection("tkt_legacy")
    bootstrap_state = repository.get_worker_bootstrap_state(
        "emp_frontend_2",
        tenant_id=DEFAULT_TENANT_ID,
        workspace_id=DEFAULT_WORKSPACE_ID,
    )
    session = repository.get_worker_session("wsess_legacy")
    grant = repository.get_worker_delivery_grant("wgrant_legacy")
    bindings = repository.list_worker_bootstrap_states(worker_id="emp_frontend_2")

    assert workflow is not None
    assert ticket is not None
    assert bootstrap_state is not None
    assert session is not None
    assert grant is not None
    assert len(bindings) == 1
    assert workflow["tenant_id"] == DEFAULT_TENANT_ID
    assert workflow["workspace_id"] == DEFAULT_WORKSPACE_ID
    assert ticket["tenant_id"] == DEFAULT_TENANT_ID
    assert ticket["workspace_id"] == DEFAULT_WORKSPACE_ID
    assert bootstrap_state["tenant_id"] == DEFAULT_TENANT_ID
    assert bootstrap_state["workspace_id"] == DEFAULT_WORKSPACE_ID
    assert session["tenant_id"] == DEFAULT_TENANT_ID
    assert session["workspace_id"] == DEFAULT_WORKSPACE_ID
    assert grant["tenant_id"] == DEFAULT_TENANT_ID
    assert grant["workspace_id"] == DEFAULT_WORKSPACE_ID


def test_worker_bootstrap_multi_scope_rotation_and_revoke_are_scope_bound(db_path):
    repository = ControlPlaneRepository(db_path, 1000)
    repository.initialize()
    issued_at = datetime.fromisoformat("2026-03-30T10:00:00+08:00")
    expires_at = datetime.fromisoformat("2026-03-30T11:00:00+08:00")
    rotated_at = datetime.fromisoformat("2026-03-30T10:05:00+08:00")
    revoked_at = datetime.fromisoformat("2026-03-30T10:10:00+08:00")

    with repository.transaction() as connection:
        default_binding = repository.ensure_worker_bootstrap_state(
            connection,
            worker_id="emp_frontend_2",
            tenant_id="tenant_default",
            workspace_id="ws_default",
            at=issued_at,
        )
        alternate_binding = repository.ensure_worker_bootstrap_state(
            connection,
            worker_id="emp_frontend_2",
            tenant_id="tenant_blue",
            workspace_id="ws_design",
            at=issued_at,
        )
        default_session = repository.create_worker_session(
            connection,
            worker_id="emp_frontend_2",
            tenant_id="tenant_default",
            workspace_id="ws_default",
            issued_at=issued_at,
            expires_at=expires_at,
            credential_version=int(default_binding["credential_version"]),
        )
        alternate_session = repository.create_worker_session(
            connection,
            worker_id="emp_frontend_2",
            tenant_id="tenant_blue",
            workspace_id="ws_design",
            issued_at=issued_at,
            expires_at=expires_at,
            credential_version=int(alternate_binding["credential_version"]),
        )
        default_grant = repository.create_worker_delivery_grant(
            connection,
            scope="execution_package",
            worker_id="emp_frontend_2",
            session_id=str(default_session["session_id"]),
            credential_version=int(default_binding["credential_version"]),
            tenant_id="tenant_default",
            workspace_id="ws_default",
            ticket_id="tkt_default",
            issued_at=issued_at,
            expires_at=expires_at,
        )
        alternate_grant = repository.create_worker_delivery_grant(
            connection,
            scope="execution_package",
            worker_id="emp_frontend_2",
            session_id=str(alternate_session["session_id"]),
            credential_version=int(alternate_binding["credential_version"]),
            tenant_id="tenant_blue",
            workspace_id="ws_design",
            ticket_id="tkt_blue",
            issued_at=issued_at,
            expires_at=expires_at,
        )

        rotated_binding = repository.rotate_worker_bootstrap_state(
            connection,
            worker_id="emp_frontend_2",
            tenant_id="tenant_default",
            workspace_id="ws_default",
            rotated_at=rotated_at,
        )

        default_session_after_rotate = repository.get_worker_session(
            str(default_session["session_id"]),
            connection=connection,
        )
        alternate_session_after_rotate = repository.get_worker_session(
            str(alternate_session["session_id"]),
            connection=connection,
        )
        default_grant_after_rotate = repository.get_worker_delivery_grant(
            str(default_grant["grant_id"]),
            connection=connection,
        )
        alternate_grant_after_rotate = repository.get_worker_delivery_grant(
            str(alternate_grant["grant_id"]),
            connection=connection,
        )

        revoked_binding = repository.revoke_worker_bootstrap_state(
            connection,
            worker_id="emp_frontend_2",
            tenant_id="tenant_blue",
            workspace_id="ws_design",
            revoked_at=revoked_at,
        )

        alternate_session_after_revoke = repository.get_worker_session(
            str(alternate_session["session_id"]),
            connection=connection,
        )
        alternate_grant_after_revoke = repository.get_worker_delivery_grant(
            str(alternate_grant["grant_id"]),
            connection=connection,
        )

    bindings = repository.list_worker_bootstrap_states(worker_id="emp_frontend_2")

    assert len(bindings) == 2
    assert rotated_binding["credential_version"] == 2
    assert rotated_binding["tenant_id"] == "tenant_default"
    assert rotated_binding["workspace_id"] == "ws_default"
    assert default_session_after_rotate is not None
    assert default_session_after_rotate["revoked_at"] == rotated_at
    assert alternate_session_after_rotate is not None
    assert alternate_session_after_rotate["revoked_at"] is None
    assert default_grant_after_rotate is not None
    assert default_grant_after_rotate["revoked_at"] == rotated_at
    assert alternate_grant_after_rotate is not None
    assert alternate_grant_after_rotate["revoked_at"] is None
    assert revoked_binding["tenant_id"] == "tenant_blue"
    assert revoked_binding["workspace_id"] == "ws_design"
    assert revoked_binding["revoked_before"] == revoked_at
    assert alternate_session_after_revoke is not None
    assert alternate_session_after_revoke["revoked_at"] == revoked_at
    assert alternate_grant_after_revoke is not None
    assert alternate_grant_after_revoke["revoked_at"] == revoked_at


def test_worker_bootstrap_issue_round_trip_and_scope_revoke(db_path):
    repository = ControlPlaneRepository(db_path, 1000)
    repository.initialize()
    issued_at = datetime.fromisoformat("2026-03-30T10:00:00+08:00")
    expires_at = datetime.fromisoformat("2026-03-30T12:00:00+08:00")
    revoked_at = datetime.fromisoformat("2026-03-30T11:00:00+08:00")

    with repository.transaction() as connection:
        repository.ensure_worker_bootstrap_state(
            connection,
            worker_id="emp_frontend_2",
            tenant_id="tenant_default",
            workspace_id="ws_default",
            at=issued_at,
        )
        repository.ensure_worker_bootstrap_state(
            connection,
            worker_id="emp_frontend_2",
            tenant_id="tenant_blue",
            workspace_id="ws_design",
            at=issued_at,
        )
        default_issue = repository.create_worker_bootstrap_issue(
            connection,
            worker_id="emp_frontend_2",
            tenant_id="tenant_default",
            workspace_id="ws_default",
            credential_version=1,
            issued_at=issued_at,
            expires_at=expires_at,
            issued_via="worker_auth_cli",
            issued_by="ops@example.com",
            reason="Default scope bootstrap",
        )
        alternate_issue = repository.create_worker_bootstrap_issue(
            connection,
            worker_id="emp_frontend_2",
            tenant_id="tenant_blue",
            workspace_id="ws_design",
            credential_version=1,
            issued_at=issued_at,
            expires_at=expires_at,
            issued_via="worker_auth_cli",
            issued_by="ops@example.com",
            reason="Design scope bootstrap",
        )

        revoked_count = repository.revoke_worker_bootstrap_issues(
            connection,
            worker_id="emp_frontend_2",
            tenant_id="tenant_default",
            workspace_id="ws_default",
            revoked_at=revoked_at,
        )

        default_issue_after_revoke = repository.get_worker_bootstrap_issue(
            str(default_issue["issue_id"]),
            connection=connection,
        )
        alternate_issue_after_revoke = repository.get_worker_bootstrap_issue(
            str(alternate_issue["issue_id"]),
            connection=connection,
        )

    active_issues = repository.list_worker_bootstrap_issues(
        worker_id="emp_frontend_2",
        active_only=True,
        at=issued_at,
    )

    assert revoked_count == 1
    assert default_issue_after_revoke is not None
    assert default_issue_after_revoke["revoked_at"] == revoked_at
    assert alternate_issue_after_revoke is not None
    assert alternate_issue_after_revoke["revoked_at"] is None
    assert len(active_issues) == 1
    assert active_issues[0]["tenant_id"] == "tenant_blue"
    assert active_issues[0]["workspace_id"] == "ws_design"


def test_list_worker_binding_admin_views_reports_counts_and_cleanup_eligibility(db_path):
    repository = ControlPlaneRepository(db_path, 1000)
    repository.initialize()
    issued_at = datetime.fromisoformat("2026-03-30T10:00:00+08:00")
    expires_at = datetime.fromisoformat("2026-03-30T12:00:00+08:00")

    with repository.transaction() as connection:
        busy_binding = repository.ensure_worker_bootstrap_state(
            connection,
            worker_id="emp_frontend_2",
            tenant_id="tenant_default",
            workspace_id="ws_default",
            at=issued_at,
        )
        repository.ensure_worker_bootstrap_state(
            connection,
            worker_id="emp_frontend_2",
            tenant_id="tenant_blue",
            workspace_id="ws_design",
            at=issued_at,
        )
        repository.create_worker_bootstrap_issue(
            connection,
            worker_id="emp_frontend_2",
            tenant_id="tenant_default",
            workspace_id="ws_default",
            credential_version=1,
            issued_at=issued_at,
            expires_at=expires_at,
            issued_via="worker_auth_cli",
            issued_by="ops@example.com",
            reason="Default scope bootstrap",
        )
        session = repository.create_worker_session(
            connection,
            worker_id="emp_frontend_2",
            tenant_id="tenant_default",
            workspace_id="ws_default",
            issued_at=issued_at,
            expires_at=expires_at,
            credential_version=int(busy_binding["credential_version"]),
        )
        repository.create_worker_delivery_grant(
            connection,
            scope="execution_package",
            worker_id="emp_frontend_2",
            session_id=str(session["session_id"]),
            credential_version=int(busy_binding["credential_version"]),
            tenant_id="tenant_default",
            workspace_id="ws_default",
            ticket_id="tkt_default",
            issued_at=issued_at,
            expires_at=expires_at,
        )
        connection.execute(
            """
            INSERT INTO workflow_projection (
                workflow_id,
                title,
                north_star_goal,
                current_stage,
                status,
                board_gate_state,
                budget_total,
                budget_used,
                deadline_at,
                started_at,
                updated_at,
                version,
                tenant_id,
                workspace_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "wf_worker_admin",
                "Worker Admin",
                "Track worker admin state",
                "EXECUTION",
                "EXECUTING",
                "UNREQUESTED",
                10,
                0,
                None,
                issued_at.isoformat(),
                issued_at.isoformat(),
                1,
                "tenant_default",
                "ws_default",
            ),
        )
        connection.execute(
            """
            INSERT INTO ticket_projection (
                ticket_id,
                workflow_id,
                node_id,
                status,
                lease_owner,
                lease_expires_at,
                started_at,
                last_heartbeat_at,
                heartbeat_expires_at,
                heartbeat_timeout_sec,
                retry_count,
                retry_budget,
                timeout_sla_sec,
                priority,
                last_failure_kind,
                last_failure_message,
                last_failure_fingerprint,
                blocking_reason_code,
                updated_at,
                version,
                tenant_id,
                workspace_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "tkt_worker_admin",
                "wf_worker_admin",
                "node_worker_admin",
                "LEASED",
                "emp_frontend_2",
                expires_at.isoformat(),
                None,
                None,
                None,
                600,
                0,
                1,
                1800,
                "high",
                None,
                None,
                None,
                None,
                issued_at.isoformat(),
                1,
                "tenant_default",
                "ws_default",
            ),
        )

    bindings = repository.list_worker_binding_admin_views(
        worker_id="emp_frontend_2",
        at=issued_at,
    )

    assert len(bindings) == 2
    default_binding = next(
        binding for binding in bindings if binding["tenant_id"] == "tenant_default"
    )
    assert default_binding["active_session_count"] == 1
    assert default_binding["active_delivery_grant_count"] == 1
    assert default_binding["active_ticket_count"] == 1
    assert default_binding["latest_bootstrap_issue_source"] == "worker_auth_cli"
    assert default_binding["latest_bootstrap_issue_at"] == issued_at
    assert default_binding["cleanup_eligible"] is False

    design_binding = next(binding for binding in bindings if binding["tenant_id"] == "tenant_blue")
    assert design_binding["active_session_count"] == 0
    assert design_binding["active_delivery_grant_count"] == 0
    assert design_binding["active_ticket_count"] == 0
    assert design_binding["latest_bootstrap_issue_at"] is None
    assert design_binding["latest_bootstrap_issue_source"] is None
    assert design_binding["cleanup_eligible"] is True


def test_worker_admin_action_log_round_trips_filters_and_details(db_path):
    repository = ControlPlaneRepository(db_path, 1000)
    repository.initialize()
    occurred_at = datetime.fromisoformat("2026-03-31T12:00:00+08:00")

    with repository.transaction() as connection:
        issue_action = repository.append_worker_admin_action_log(
            connection,
            occurred_at=occurred_at,
            operator_id="ops@example.com",
            operator_role="platform_admin",
            auth_source="signed_token",
            action_type="issue_bootstrap",
            dry_run=False,
            tenant_id="tenant_blue",
            workspace_id="ws_design",
            worker_id="emp_frontend_2",
            details={
                "reason": "tenant scoped bootstrap",
                "issued": True,
                "succeeded": True,
            },
        )
        cleanup_action = repository.append_worker_admin_action_log(
            connection,
            occurred_at=datetime.fromisoformat("2026-03-31T12:05:00+08:00"),
            operator_id="tenant.viewer@example.com",
            operator_role="scope_viewer",
            auth_source="signed_token",
            action_type="cleanup_bindings",
            dry_run=True,
            tenant_id="tenant_blue",
            workspace_id="ws_design",
            worker_id="emp_frontend_2",
            details={
                "executed": False,
                "candidate_count": 1,
                "succeeded": True,
            },
        )

    listed = repository.list_worker_admin_action_logs(
        tenant_id="tenant_blue",
        workspace_id="ws_design",
        operator_id="ops@example.com",
        action_type="issue_bootstrap",
        dry_run=False,
        limit=10,
    )

    assert issue_action["operator_id"] == "ops@example.com"
    assert issue_action["operator_role"] == "platform_admin"
    assert issue_action["auth_source"] == "signed_token"
    assert issue_action["action_type"] == "issue_bootstrap"
    assert issue_action["details"]["reason"] == "tenant scoped bootstrap"
    assert cleanup_action["dry_run"] is True
    assert cleanup_action["details"]["executed"] is False
    assert len(listed) == 1
    assert listed[0]["action_id"] == issue_action["action_id"]
    assert listed[0]["details"]["succeeded"] is True


def test_worker_admin_token_issue_round_trips_filters_and_revoke(db_path):
    repository = ControlPlaneRepository(db_path, 1000)
    repository.initialize()
    issued_at = datetime.fromisoformat("2026-03-31T13:00:00+08:00")
    expires_at = datetime.fromisoformat("2026-03-31T13:15:00+08:00")
    revoked_at = datetime.fromisoformat("2026-03-31T13:05:00+08:00")

    with repository.transaction() as connection:
        global_issue = repository.create_worker_admin_token_issue(
            connection,
            token_id="wop_global",
            operator_id="ops@example.com",
            role="platform_admin",
            tenant_id=None,
            workspace_id=None,
            issued_at=issued_at,
            expires_at=expires_at,
            issued_via="worker_admin_auth_cli",
            issued_by="ops@example.com",
        )
        scoped_issue = repository.create_worker_admin_token_issue(
            connection,
            token_id="wop_scope",
            operator_id="tenant.admin@example.com",
            role="scope_admin",
            tenant_id="tenant_blue",
            workspace_id="ws_design",
            issued_at=issued_at,
            expires_at=expires_at,
            issued_via="worker_admin_auth_cli",
            issued_by="ops@example.com",
        )
        repository.revoke_worker_admin_token_issue(
            connection,
            token_id="wop_scope",
            revoked_at=revoked_at,
            revoked_by="ops@example.com",
            revoke_reason="tenant offboarding",
        )

    active_scoped = repository.list_worker_admin_token_issues(
        tenant_id="tenant_blue",
        workspace_id="ws_design",
        active_only=True,
    )
    all_scoped = repository.list_worker_admin_token_issues(
        tenant_id="tenant_blue",
        workspace_id="ws_design",
        active_only=False,
    )

    assert global_issue["token_id"] == "wop_global"
    assert scoped_issue["token_id"] == "wop_scope"
    assert all_scoped[0]["token_id"] == "wop_scope"
    assert all_scoped[0]["revoked_by"] == "ops@example.com"
    assert all_scoped[0]["revoke_reason"] == "tenant offboarding"
    assert active_scoped == []


def test_worker_admin_auth_rejection_log_round_trips_filters(db_path):
    repository = ControlPlaneRepository(db_path, 1000)
    repository.initialize()

    with repository.transaction() as connection:
        repository.append_worker_admin_auth_rejection_log(
            connection,
            occurred_at=datetime.fromisoformat("2026-03-31T14:00:00+08:00"),
            route_path="/api/v1/worker-admin/bindings",
            reason_code="missing_operator_token",
            operator_id=None,
            operator_role=None,
            token_id=None,
            tenant_id=None,
            workspace_id=None,
        )
        repository.append_worker_admin_auth_rejection_log(
            connection,
            occurred_at=datetime.fromisoformat("2026-03-31T14:05:00+08:00"),
            route_path="/api/v1/worker-admin/operator-tokens",
            reason_code="revoked_token",
            operator_id="tenant.admin@example.com",
            operator_role="scope_admin",
            token_id="wop_scope",
            tenant_id="tenant_blue",
            workspace_id="ws_design",
        )

    listed = repository.list_worker_admin_auth_rejection_logs(
        tenant_id="tenant_blue",
        workspace_id="ws_design",
        token_id="wop_scope",
        route_path="/api/v1/worker-admin/operator-tokens",
    )

    assert len(listed) == 1
    assert listed[0]["reason_code"] == "revoked_token"
    assert listed[0]["operator_id"] == "tenant.admin@example.com"
    assert listed[0]["operator_role"] == "scope_admin"
    assert listed[0]["token_id"] == "wop_scope"
