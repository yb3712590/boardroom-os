from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from app.core.artifact_store import ArtifactStore
from app.core.constants import (
    DEFAULT_TENANT_ID,
    DEFAULT_WORKSPACE_ID,
    EVENT_EMPLOYEE_HIRED,
    EVENT_SYSTEM_INITIALIZED,
)
from app.db.repository import ControlPlaneRepository


def test_initialize_writes_single_system_initialized_event_before_employee_seed(db_path):
    repository = ControlPlaneRepository(db_path, 1000)

    repository.initialize()
    events = repository.list_events_for_testing()

    assert repository.count_events_by_type(EVENT_SYSTEM_INITIALIZED) == 1
    assert events[0]["event_type"] == EVENT_SYSTEM_INITIALIZED
    assert events[1]["event_type"] == EVENT_EMPLOYEE_HIRED

    reloaded = ControlPlaneRepository(db_path, 1000)
    reloaded.initialize()

    assert reloaded.count_events_by_type(EVENT_SYSTEM_INITIALIZED) == 1


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
            trusted_proxy_id="proxy-a",
            source_ip="10.0.0.1",
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
            trusted_proxy_id="proxy-a",
            source_ip="10.0.0.1",
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
    assert issue_action["trusted_proxy_id"] == "proxy-a"
    assert issue_action["source_ip"] == "10.0.0.1"
    assert issue_action["details"]["reason"] == "tenant scoped bootstrap"
    assert cleanup_action["dry_run"] is True
    assert cleanup_action["details"]["executed"] is False
    assert len(listed) == 1
    assert listed[0]["action_id"] == issue_action["action_id"]
    assert listed[0]["trusted_proxy_id"] == "proxy-a"
    assert listed[0]["source_ip"] == "10.0.0.1"
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
            trusted_proxy_id=None,
            source_ip="10.0.0.2",
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
            trusted_proxy_id="proxy-a",
            source_ip="10.0.0.3",
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
    assert listed[0]["trusted_proxy_id"] == "proxy-a"
    assert listed[0]["source_ip"] == "10.0.0.3"


def test_initialize_backfills_worker_admin_log_columns_for_legacy_tables(db_path):
    connection = sqlite3.connect(db_path)
    connection.execute(
        """
        CREATE TABLE worker_admin_auth_rejection_log (
            rejection_id TEXT PRIMARY KEY,
            occurred_at TEXT NOT NULL,
            route_path TEXT NOT NULL,
            reason_code TEXT NOT NULL,
            operator_id TEXT,
            operator_role TEXT,
            token_id TEXT,
            tenant_id TEXT,
            workspace_id TEXT
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE worker_admin_action_log (
            action_id TEXT PRIMARY KEY,
            occurred_at TEXT NOT NULL,
            operator_id TEXT NOT NULL,
            operator_role TEXT NOT NULL,
            auth_source TEXT NOT NULL,
            tenant_id TEXT,
            workspace_id TEXT,
            worker_id TEXT,
            session_id TEXT,
            grant_id TEXT,
            issue_id TEXT,
            action_type TEXT NOT NULL,
            dry_run INTEGER NOT NULL DEFAULT 0,
            details_json TEXT NOT NULL
        )
        """
    )
    connection.commit()
    connection.close()

    repository = ControlPlaneRepository(db_path, 1000)
    repository.initialize()

    connection = sqlite3.connect(db_path)
    rejection_columns = {
        row[1]
        for row in connection.execute("PRAGMA table_info(worker_admin_auth_rejection_log)").fetchall()
    }
    action_columns = {
        row[1] for row in connection.execute("PRAGMA table_info(worker_admin_action_log)").fetchall()
    }
    connection.close()

    assert "trusted_proxy_id" in rejection_columns
    assert "source_ip" in rejection_columns
    assert "trusted_proxy_id" in action_columns
    assert "source_ip" in action_columns


def test_artifact_cleanup_candidates_ignore_storage_already_deleted_rows(db_path):
    repository = ControlPlaneRepository(db_path, 1000)
    repository.initialize()
    created_at = datetime.fromisoformat("2026-03-31T15:00:00+08:00")
    expires_before = datetime.fromisoformat("2026-03-31T15:10:00+08:00")

    with repository.transaction() as connection:
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
                "art://cleanup/already-cleared.md",
                "wf_cleanup",
                "tkt_cleanup",
                "node_cleanup",
                "artifacts/cleanup/already-cleared.md",
                "MARKDOWN",
                "text/markdown",
                "MATERIALIZED",
                "EXPIRED",
                "artifacts/cleanup/already-cleared.md",
                "hash-cleared",
                12,
                "EPHEMERAL",
                created_at.isoformat(),
                created_at.isoformat(),
                "emp_ops_1",
                "Expired by artifact cleanup.",
                created_at.isoformat(),
                created_at.isoformat(),
            ),
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
                "art://cleanup/pending-delete.md",
                "wf_cleanup",
                "tkt_cleanup",
                "node_cleanup",
                "artifacts/cleanup/pending-delete.md",
                "MARKDOWN",
                "text/markdown",
                "MATERIALIZED",
                "EXPIRED",
                "artifacts/cleanup/pending-delete.md",
                "hash-pending",
                12,
                "EPHEMERAL",
                created_at.isoformat(),
                created_at.isoformat(),
                "emp_ops_1",
                "Expired by artifact cleanup.",
                None,
                created_at.isoformat(),
            ),
        )
        candidates = repository.list_artifacts_for_cleanup(
            connection,
            expires_before=expires_before,
        )

    assert [item["artifact_ref"] for item in candidates] == ["art://cleanup/pending-delete.md"]


def test_initialize_backfills_legacy_ephemeral_artifact_retention_and_marks_existing_expiry_unknown(
    db_path,
    monkeypatch,
):
    monkeypatch.setenv("BOARDROOM_OS_ARTIFACT_EPHEMERAL_DEFAULT_TTL_SEC", "604800")
    created_at = datetime.fromisoformat("2026-03-29T09:00:00+08:00")
    explicit_expires_at = datetime.fromisoformat("2026-03-29T10:00:00+08:00")
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
            "art://legacy/ephemeral-missing-expiry.md",
            "wf_legacy",
            "tkt_legacy",
            "node_legacy",
            "artifacts/legacy/ephemeral-missing-expiry.md",
            "MARKDOWN",
            "text/markdown",
            "MATERIALIZED",
            "ACTIVE",
            "artifacts/legacy/ephemeral-missing-expiry.md",
            "hash-missing",
            32,
            "EPHEMERAL",
            None,
            None,
            None,
            None,
            None,
            created_at.isoformat(),
        ),
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
            "art://legacy/ephemeral-existing-expiry.md",
            "wf_legacy",
            "tkt_legacy",
            "node_legacy",
            "artifacts/legacy/ephemeral-existing-expiry.md",
            "MARKDOWN",
            "text/markdown",
            "MATERIALIZED",
            "ACTIVE",
            "artifacts/legacy/ephemeral-existing-expiry.md",
            "hash-explicit",
            32,
            "EPHEMERAL",
            explicit_expires_at.isoformat(),
            None,
            None,
            None,
            None,
            created_at.isoformat(),
        ),
    )
    connection.commit()
    connection.close()

    repository = ControlPlaneRepository(db_path, 1000)
    repository.initialize()

    backfilled = repository.get_artifact_by_ref("art://legacy/ephemeral-missing-expiry.md")
    preserved = repository.get_artifact_by_ref("art://legacy/ephemeral-existing-expiry.md")

    assert backfilled is not None
    assert preserved is not None
    assert backfilled["expires_at"] == created_at + timedelta(seconds=604800)
    assert backfilled["retention_ttl_sec"] == 604800
    assert backfilled["retention_policy_source"] == "BACKFILLED_CLASS_DEFAULT"
    assert backfilled["retention_class_source"] == "LEGACY_COMPAT"
    assert preserved["expires_at"] == explicit_expires_at
    assert preserved["retention_ttl_sec"] is None
    assert preserved["retention_policy_source"] == "LEGACY_UNKNOWN"
    assert preserved["retention_class_source"] == "LEGACY_COMPAT"

    repository.initialize()
    backfilled_after_second_initialize = repository.get_artifact_by_ref(
        "art://legacy/ephemeral-missing-expiry.md"
    )
    assert backfilled_after_second_initialize is not None
    assert backfilled_after_second_initialize["expires_at"] == created_at + timedelta(seconds=604800)


def test_initialize_backfills_legacy_review_evidence_artifact_retention(
    db_path,
    monkeypatch,
):
    monkeypatch.setenv("BOARDROOM_OS_ARTIFACT_REVIEW_EVIDENCE_DEFAULT_TTL_SEC", "2592000")
    created_at = datetime.fromisoformat("2026-03-29T09:00:00+08:00")
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
            "art://legacy/review-evidence-missing-expiry.md",
            "wf_legacy",
            "tkt_legacy",
            "node_legacy",
            "artifacts/legacy/review-evidence-missing-expiry.md",
            "MARKDOWN",
            "text/markdown",
            "MATERIALIZED",
            "ACTIVE",
            "artifacts/legacy/review-evidence-missing-expiry.md",
            "hash-review-evidence",
            64,
            "REVIEW_EVIDENCE",
            None,
            None,
            None,
            None,
            None,
            created_at.isoformat(),
        ),
    )
    connection.commit()
    connection.close()

    repository = ControlPlaneRepository(db_path, 1000)
    repository.initialize()

    backfilled = repository.get_artifact_by_ref("art://legacy/review-evidence-missing-expiry.md")

    assert backfilled is not None
    assert backfilled["retention_class"] == "REVIEW_EVIDENCE"
    assert backfilled["expires_at"] == created_at + timedelta(seconds=2592000)
    assert backfilled["retention_ttl_sec"] == 2592000
    assert backfilled["retention_policy_source"] == "BACKFILLED_CLASS_DEFAULT"
    assert backfilled["retention_class_source"] == "LEGACY_COMPAT"


def test_initialize_adds_retention_class_source_column_as_legacy_compat(db_path):
    created_at = datetime.fromisoformat("2026-03-29T09:00:00+08:00")
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
            retention_ttl_sec INTEGER,
            retention_policy_source TEXT,
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
            retention_ttl_sec,
            retention_policy_source,
            expires_at,
            deleted_at,
            deleted_by,
            delete_reason,
            storage_deleted_at,
            created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "art://legacy/no-class-source.md",
            "wf_legacy",
            "tkt_legacy",
            "node_legacy",
            "reports/review/no-class-source.md",
            "MARKDOWN",
            "text/markdown",
            "MATERIALIZED",
            "ACTIVE",
            "reports/review/no-class-source.md",
            "hash-no-class-source",
            64,
            "REVIEW_EVIDENCE",
            1800,
            "CLASS_DEFAULT",
            "2026-03-29T09:30:00+08:00",
            None,
            None,
            None,
            None,
            created_at.isoformat(),
        ),
    )
    connection.commit()
    connection.close()

    repository = ControlPlaneRepository(db_path, 1000)
    repository.initialize()

    artifact = repository.get_artifact_by_ref("art://legacy/no-class-source.md")

    assert artifact is not None
    assert artifact["retention_class"] == "REVIEW_EVIDENCE"
    assert artifact["retention_ttl_sec"] == 1800
    assert artifact["retention_policy_source"] == "CLASS_DEFAULT"
    assert artifact["retention_class_source"] == "LEGACY_COMPAT"


def test_initialize_adds_artifact_storage_columns_with_local_defaults(db_path):
    created_at = datetime.fromisoformat("2026-03-31T17:00:00+08:00")
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
            retention_class_source TEXT,
            retention_ttl_sec INTEGER,
            retention_policy_source TEXT,
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
            retention_class_source,
            retention_ttl_sec,
            retention_policy_source,
            expires_at,
            deleted_at,
            deleted_by,
            delete_reason,
            storage_deleted_at,
            created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "art://legacy/storage-defaults.bin",
            "wf_legacy",
            "tkt_legacy",
            "node_legacy",
            "artifacts/legacy/storage-defaults.bin",
            "IMAGE",
            "application/octet-stream",
            "MATERIALIZED",
            "ACTIVE",
            "artifacts/legacy/storage-defaults.bin",
            "hash-storage-defaults",
            128,
            "PERSISTENT",
            "EXPLICIT",
            None,
            "NO_EXPIRY",
            None,
            None,
            None,
            None,
            None,
            created_at.isoformat(),
        ),
    )
    connection.commit()
    connection.close()

    repository = ControlPlaneRepository(db_path, 1000)
    repository.initialize()

    artifact = repository.get_artifact_by_ref("art://legacy/storage-defaults.bin")
    with repository.connection() as connection:
        artifact_columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(artifact_index)").fetchall()
        }

    assert artifact is not None
    assert "storage_backend" in artifact_columns
    assert "storage_object_key" in artifact_columns
    assert "storage_delete_status" in artifact_columns
    assert "storage_delete_error" in artifact_columns
    assert artifact["storage_backend"] == "LOCAL_FILE"
    assert artifact["storage_object_key"] is None
    assert artifact["storage_delete_status"] == "PRESENT"
    assert artifact["storage_delete_error"] is None


def test_artifact_upload_session_lifecycle_and_consume_guard(db_path):
    repository = ControlPlaneRepository(db_path, 1000)
    repository.initialize()
    created_at = datetime.fromisoformat("2026-03-31T18:00:00+08:00")
    completed_at = datetime.fromisoformat("2026-03-31T18:05:00+08:00")
    consumed_at = datetime.fromisoformat("2026-03-31T18:06:00+08:00")

    with repository.transaction() as connection:
        repository.create_artifact_upload_session(
            connection,
            session_id="upl_session_001",
            created_at=created_at,
            created_by="emp_frontend_2",
            filename="bundle.zip",
            media_type="application/zip",
        )
        repository.save_artifact_upload_part(
            connection,
            session_id="upl_session_001",
            part_number=1,
            staging_relpath="uploads/upl_session_001/part-0001.bin",
            size_bytes=3,
            content_hash="hash-part-1",
            uploaded_at=created_at,
        )
        repository.save_artifact_upload_part(
            connection,
            session_id="upl_session_001",
            part_number=2,
            staging_relpath="uploads/upl_session_001/part-0002.bin",
            size_bytes=4,
            content_hash="hash-part-2",
            uploaded_at=created_at,
        )
        repository.complete_artifact_upload_session(
            connection,
            session_id="upl_session_001",
            completed_at=completed_at,
            assembled_staging_relpath="uploads/upl_session_001/assembled.bin",
            size_bytes=7,
            content_hash="hash-assembled",
            part_count=2,
        )
        first_consume = repository.consume_artifact_upload_session(
            connection,
            session_id="upl_session_001",
            consumed_at=consumed_at,
            consumed_by_artifact_ref="art://runtime/tkt_visual_001/bundle.zip",
        )
        second_consume = repository.consume_artifact_upload_session(
            connection,
            session_id="upl_session_001",
            consumed_at=consumed_at,
            consumed_by_artifact_ref="art://runtime/tkt_visual_001/bundle-copy.zip",
        )

    session = repository.get_artifact_upload_session("upl_session_001")
    parts = repository.list_artifact_upload_parts("upl_session_001")

    assert first_consume is True
    assert second_consume is False
    assert session is not None
    assert session["status"] == "CONSUMED"
    assert session["filename"] == "bundle.zip"
    assert session["media_type"] == "application/zip"
    assert session["size_bytes"] == 7
    assert session["content_hash"] == "hash-assembled"
    assert session["part_count"] == 2
    assert session["assembled_staging_relpath"] == "uploads/upl_session_001/assembled.bin"
    assert session["consumed_by_artifact_ref"] == "art://runtime/tkt_visual_001/bundle.zip"
    assert [part["part_number"] for part in parts] == [1, 2]


def test_initialize_builds_retrieval_fts_tables_and_backfills_existing_rows(db_path):
    artifact_store = ArtifactStore(Path(db_path).with_suffix(".artifacts"))
    repository = ControlPlaneRepository(db_path, 1000, artifact_store=artifact_store)
    repository.initialize()

    materialized = artifact_store.materialize_text(
        "artifacts/history/homepage-notes.md",
        "# Homepage\n\nApproved direction keeps brand visible in the hero.\n",
        media_type="text/markdown",
    )

    with repository.transaction() as connection:
        connection.execute(
            """
            INSERT INTO workflow_projection (
                workflow_id,
                title,
                north_star_goal,
                tenant_id,
                workspace_id,
                current_stage,
                status,
                budget_total,
                budget_used,
                board_gate_state,
                deadline_at,
                started_at,
                updated_at,
                version
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "wf_history",
                "History workflow",
                "Keep prior context searchable",
                DEFAULT_TENANT_ID,
                DEFAULT_WORKSPACE_ID,
                "REVIEW",
                "ACTIVE",
                100,
                20,
                "NOT_REQUIRED",
                None,
                "2026-04-01T09:00:00+08:00",
                "2026-04-01T09:10:00+08:00",
                1,
            ),
        )
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
                "apr_history",
                "brp_history",
                "wf_history",
                "VISUAL_MILESTONE",
                "APPROVED",
                "emp_frontend_1",
                "board_1",
                "2026-04-01T09:20:00+08:00",
                "2026-04-01T09:10:00+08:00",
                "2026-04-01T09:20:00+08:00",
                1,
                1,
                '{"review_pack":{"subject":{"title":"Homepage review approval","source_ticket_id":"tkt_history"},"recommendation":{"summary":"Approved homepage direction with strong brand hierarchy."}},"inbox_title":"Homepage review approval","inbox_summary":"Approved homepage direction with strong brand hierarchy.","resolution":{"board_comment":"Approved and archived for later retrieval."}}',
            ),
        )
        connection.execute(
            """
            INSERT INTO incident_projection (
                incident_id,
                workflow_id,
                node_id,
                ticket_id,
                provider_id,
                incident_type,
                status,
                severity,
                fingerprint,
                circuit_breaker_state,
                opened_at,
                closed_at,
                payload_json,
                updated_at,
                version
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "inc_history",
                "wf_history",
                "node_history",
                "tkt_history",
                None,
                "CHECKER_REJECTED",
                "OPEN",
                "HIGH",
                "fingerprint-brand",
                None,
                "2026-04-01T09:30:00+08:00",
                None,
                '{"headline":"Homepage checker rejection","summary":"Homepage run failed after checker rejected weak brand alignment."}',
                "2026-04-01T09:30:00+08:00",
                1,
            ),
        )
        repository.save_artifact_record(
            connection,
            artifact_ref="art://history/homepage-notes.md",
            workflow_id="wf_history",
            ticket_id="tkt_history",
            node_id="node_history",
            logical_path="artifacts/history/homepage-notes.md",
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
            created_at=datetime.fromisoformat("2026-04-01T09:40:00+08:00"),
        )

    reloaded = ControlPlaneRepository(db_path, 1000, artifact_store=artifact_store)
    reloaded.initialize()

    with reloaded.connection() as connection:
        tables = {
            row["name"]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type IN ('table', 'view')"
            ).fetchall()
        }

    assert "retrieval_review_summary_fts" in tables
    assert "retrieval_incident_summary_fts" in tables
    assert "retrieval_artifact_summary_fts" in tables
    assert reloaded.list_retrieval_review_summary_candidates(
        tenant_id=DEFAULT_TENANT_ID,
        workspace_id=DEFAULT_WORKSPACE_ID,
        exclude_workflow_id="wf_current",
        normalized_terms=["homepage", "brand", "direction"],
        limit=5,
    )[0]["review_pack_id"] == "brp_history"
    assert reloaded.list_retrieval_incident_summary_candidates(
        tenant_id=DEFAULT_TENANT_ID,
        workspace_id=DEFAULT_WORKSPACE_ID,
        exclude_workflow_id="wf_current",
        normalized_terms=["homepage", "brand"],
        limit=5,
    )[0]["incident_id"] == "inc_history"
    assert reloaded.list_retrieval_artifact_summary_candidates(
        tenant_id=DEFAULT_TENANT_ID,
        workspace_id=DEFAULT_WORKSPACE_ID,
        exclude_workflow_id="wf_current",
        normalized_terms=["homepage", "brand", "hero"],
        limit=5,
    )[0]["artifact_ref"] == "art://history/homepage-notes.md"


def test_retrieval_candidates_sort_by_match_quality_then_recency_and_deduplicate_source_ref(db_path):
    repository = ControlPlaneRepository(db_path, 1000)

    ordered = repository._sort_retrieval_candidates(
        [
            {
                "channel": "review_summaries",
                "source_ref": "dup-review",
                "matched_terms": ["homepage"],
                "updated_at": datetime.fromisoformat("2026-04-01T09:00:00+08:00"),
            },
            {
                "channel": "review_summaries",
                "source_ref": "dup-review",
                "matched_terms": ["homepage", "brand"],
                "updated_at": datetime.fromisoformat("2026-04-01T09:30:00+08:00"),
            },
            {
                "channel": "incident_summaries",
                "source_ref": "incident-newer",
                "matched_terms": ["homepage", "brand"],
                "updated_at": datetime.fromisoformat("2026-04-01T09:20:00+08:00"),
            },
            {
                "channel": "artifact_summaries",
                "source_ref": "artifact-older",
                "matched_terms": ["homepage", "brand"],
                "updated_at": datetime.fromisoformat("2026-04-01T09:10:00+08:00"),
            },
        ]
    )

    assert [candidate["source_ref"] for candidate in ordered] == [
        "dup-review",
        "incident-newer",
        "artifact-older",
    ]


def test_artifact_retrieval_skips_non_active_or_non_materialized_rows(db_path):
    artifact_store = ArtifactStore(Path(db_path).with_suffix(".artifacts"))
    repository = ControlPlaneRepository(db_path, 1000, artifact_store=artifact_store)
    repository.initialize()

    materialized = artifact_store.materialize_text(
        "artifacts/history/active-homepage.md",
        "Homepage guidance keeps the brand visible.",
        media_type="text/markdown",
    )

    with repository.transaction() as connection:
        connection.execute(
            """
            INSERT INTO workflow_projection (
                workflow_id,
                title,
                north_star_goal,
                tenant_id,
                workspace_id,
                current_stage,
                status,
                budget_total,
                budget_used,
                board_gate_state,
                deadline_at,
                started_at,
                updated_at,
                version
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "wf_history",
                "History workflow",
                "Keep prior context searchable",
                DEFAULT_TENANT_ID,
                DEFAULT_WORKSPACE_ID,
                "REVIEW",
                "ACTIVE",
                100,
                20,
                "NOT_REQUIRED",
                None,
                "2026-04-01T09:00:00+08:00",
                "2026-04-01T09:10:00+08:00",
                1,
            ),
        )
        repository.save_artifact_record(
            connection,
            artifact_ref="art://history/active.md",
            workflow_id="wf_history",
            ticket_id="tkt_history",
            node_id="node_history",
            logical_path="artifacts/history/active-homepage.md",
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
            created_at=datetime.fromisoformat("2026-04-01T09:40:00+08:00"),
        )
        repository.save_artifact_record(
            connection,
            artifact_ref="art://history/pending.md",
            workflow_id="wf_history",
            ticket_id="tkt_history",
            node_id="node_history",
            logical_path="artifacts/history/pending-homepage.md",
            kind="MARKDOWN",
            media_type="text/markdown",
            materialization_status="PENDING",
            lifecycle_status="ACTIVE",
            storage_relpath=None,
            content_hash=None,
            size_bytes=None,
            retention_class="PERSISTENT",
            expires_at=None,
            deleted_at=None,
            deleted_by=None,
            delete_reason=None,
            created_at=datetime.fromisoformat("2026-04-01T09:41:00+08:00"),
        )
        repository.update_artifact_lifecycle(
            connection,
            artifact_ref="art://history/active.md",
            lifecycle_status="DELETED",
            deleted_at=datetime.fromisoformat("2026-04-01T09:50:00+08:00"),
            deleted_by="emp_ops_1",
            delete_reason="cleanup",
        )

    candidates = repository.list_retrieval_artifact_summary_candidates(
        tenant_id=DEFAULT_TENANT_ID,
        workspace_id=DEFAULT_WORKSPACE_ID,
        exclude_workflow_id="wf_current",
        normalized_terms=["homepage", "brand"],
        limit=5,
    )

    assert candidates == []


def test_initialize_backfills_legacy_employee_rows_into_employee_events(db_path):
    connection = sqlite3.connect(db_path)
    connection.execute(
        """
        CREATE TABLE employee_projection (
            employee_id TEXT PRIMARY KEY,
            role_type TEXT NOT NULL,
            skill_profile_json TEXT,
            personality_profile_json TEXT,
            aesthetic_profile_json TEXT,
            state TEXT NOT NULL,
            board_approved INTEGER NOT NULL,
            provider_id TEXT,
            role_profile_refs_json TEXT,
            updated_at TEXT NOT NULL,
            version INTEGER NOT NULL
        )
        """
    )
    connection.execute(
        """
        INSERT INTO employee_projection (
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
            "emp_legacy_frontend",
            "frontend_engineer",
            '{"primary_domain":"frontend"}',
            '{"style":"maker"}',
            '{"preference":"minimal"}',
            "ACTIVE",
            1,
            "prov_openai_compat",
            '["frontend_engineer_primary"]',
            "2026-04-01T10:00:00+08:00",
            4,
        ),
    )
    connection.commit()
    connection.close()

    repository = ControlPlaneRepository(db_path, 1000)
    repository.initialize()

    employees = repository.list_employee_projections()

    assert repository.count_events_by_type(EVENT_EMPLOYEE_HIRED) == 1
    assert employees == [
        {
            "employee_id": "emp_legacy_frontend",
            "role_type": "frontend_engineer",
            "skill_profile_json": {
                "primary_domain": "frontend",
                "system_scope": "delivery_slice",
                "validation_bias": "balanced",
            },
            "personality_profile_json": {
                "risk_posture": "assertive",
                "challenge_style": "constructive",
                "execution_pace": "fast",
                "detail_rigor": "focused",
                "communication_style": "direct",
            },
            "aesthetic_profile_json": {
                "surface_preference": "functional",
                "information_density": "balanced",
                "motion_tolerance": "measured",
            },
            "state": "ACTIVE",
            "board_approved": True,
            "provider_id": "prov_openai_compat",
            "role_profile_refs": ["frontend_engineer_primary"],
            "profile_summary": (
                "Skill frontend, delivery slice, balanced. "
                "Personality assertive, constructive, fast, focused, direct. "
                "Aesthetic functional, balanced, measured."
                ),
                "updated_at": datetime.fromisoformat("2026-04-01T10:00:00+08:00"),
                "version": 2,
            }
        ]
