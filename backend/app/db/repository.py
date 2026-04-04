from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from app.config import get_settings
from app.contracts.runtime import CompileManifest, CompiledContextBundle, CompiledExecutionPackage
from app.core.artifact_store import ArtifactStore
from app.core.artifacts import (
    ARTIFACT_RETENTION_CLASS_SOURCE_LEGACY_COMPAT,
    ARTIFACT_RETENTION_POLICY_BACKFILLED_CLASS_DEFAULT,
    ARTIFACT_RETENTION_POLICY_LEGACY_UNKNOWN,
    ARTIFACT_RETENTION_POLICY_NO_EXPIRY,
    build_artifact_access_descriptor,
    build_artifact_retention_defaults,
    normalize_artifact_kind,
)
from app.core.constants import (
    APPROVAL_STATUS_OPEN,
    CIRCUIT_BREAKER_STATE_CLOSED,
    CIRCUIT_BREAKER_STATE_OPEN,
    DEFAULT_TENANT_ID,
    DEFAULT_WORKSPACE_ID,
    EVENT_EMPLOYEE_HIRED,
    EVENT_EMPLOYEE_FROZEN,
    EVENT_EMPLOYEE_REPLACED,
    EVENT_ARTIFACT_CLEANUP_COMPLETED,
    EVENT_ARTIFACT_DELETED,
    EVENT_ARTIFACT_EXPIRED,
    EVENT_CIRCUIT_BREAKER_CLOSED,
    EVENT_CIRCUIT_BREAKER_OPENED,
    NODE_STATUS_BLOCKED_FOR_BOARD_REVIEW,
    NODE_STATUS_COMPLETED,
    EVENT_BOARD_DIRECTIVE_RECEIVED,
    EVENT_BOARD_REVIEW_APPROVED,
    EVENT_BOARD_REVIEW_REJECTED,
    EVENT_BOARD_REVIEW_REQUIRED,
    EVENT_INCIDENT_CLOSED,
    EVENT_INCIDENT_RECOVERY_STARTED,
    EVENT_INCIDENT_OPENED,
    EVENT_SYSTEM_INITIALIZED,
    EVENT_TICKET_CANCELLED,
    EVENT_TICKET_CANCEL_REQUESTED,
    EVENT_TICKET_COMPLETED,
    EVENT_TICKET_CREATED,
    EVENT_TICKET_FAILED,
    EVENT_TICKET_LEASED,
    EVENT_TICKET_RETRY_SCHEDULED,
    EVENT_TICKET_STARTED,
    EVENT_TICKET_TIMED_OUT,
    EVENT_WORKFLOW_CREATED,
    INCIDENT_TYPE_REPEATED_FAILURE_ESCALATION,
    INCIDENT_TYPE_PROVIDER_EXECUTION_PAUSED,
    NODE_STATUS_CANCELLED,
    TICKET_STATUS_EXECUTING,
    TICKET_STATUS_LEASED,
    TICKET_STATUS_PENDING,
)
from app.core.ids import new_prefixed_id
from app.core.reducer import (
    rebuild_employee_projections,
    rebuild_incident_projections,
    rebuild_node_projections,
    rebuild_ticket_projections,
    rebuild_workflow_projections,
)
from app.core.time import now_local
from app.db.schema import TABLE_SCHEMA_SQL

DEFAULT_EMPLOYEE_ROSTER = (
    {
        "employee_id": "emp_frontend_2",
        "role_type": "frontend_engineer",
        "skill_profile_json": {"primary_domain": "frontend"},
        "personality_profile_json": {"style": "maker"},
        "aesthetic_profile_json": {"preference": "minimal"},
        "state": "ACTIVE",
        "board_approved": True,
        "provider_id": "prov_openai_compat",
        "role_profile_refs_json": ["frontend_engineer_primary"],
    },
    {
        "employee_id": "emp_checker_1",
        "role_type": "checker",
        "skill_profile_json": {"primary_domain": "quality"},
        "personality_profile_json": {"style": "checker"},
        "aesthetic_profile_json": {"preference": "structured"},
        "state": "ACTIVE",
        "board_approved": True,
        "provider_id": "prov_openai_compat",
        "role_profile_refs_json": ["checker_primary"],
    },
)


class ControlPlaneRepository:
    def __init__(
        self,
        db_path: Path,
        busy_timeout_ms: int,
        recent_event_limit: int = 10,
        artifact_store: ArtifactStore | None = None,
    ):
        self.db_path = db_path
        self.busy_timeout_ms = busy_timeout_ms
        self.recent_event_limit = recent_event_limit
        self.artifact_store = artifact_store
        self._initialized = False

    def initialize(self) -> None:
        if self._initialized:
            return
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as connection:
            connection.executescript(TABLE_SCHEMA_SQL)
            self._ensure_approval_projection_shape(connection)
            self._ensure_workflow_projection_shape(connection)
            self._ensure_ticket_projection_shape(connection)
            self._ensure_node_projection_shape(connection)
            self._ensure_employee_projection_shape(connection)
            self._ensure_worker_bootstrap_state_shape(connection)
            self._ensure_worker_bootstrap_issue_shape(connection)
            self._ensure_worker_session_shape(connection)
            self._ensure_worker_delivery_grant_shape(connection)
            self._ensure_worker_auth_rejection_log_shape(connection)
            self._ensure_worker_admin_token_issue_shape(connection)
            self._ensure_worker_admin_auth_rejection_log_shape(connection)
            self._ensure_worker_admin_action_log_shape(connection)
            self._ensure_incident_projection_shape(connection)
            self._ensure_compiled_context_bundle_shape(connection)
            self._ensure_compile_manifest_shape(connection)
            self._ensure_compiled_execution_package_shape(connection)
            self._ensure_ceo_shadow_run_shape(connection)
            self._ensure_artifact_index_shape(connection)
            self._ensure_artifact_upload_session_shape(connection)
            self._ensure_artifact_upload_part_shape(connection)
            self._backfill_scope_defaults(connection)
            self._backfill_artifact_storage_defaults(connection)
            self._backfill_artifact_retention_defaults(connection)
            self._bootstrap_employee_events(connection)
            employee_events = self.list_all_events(connection)
            self.replace_employee_projections(
                connection,
                rebuild_employee_projections(employee_events),
            )
        self._initialized = True

    @contextmanager
    def connection(self):
        connection = sqlite3.connect(
            self.db_path,
            detect_types=sqlite3.PARSE_DECLTYPES,
            isolation_level=None,
            check_same_thread=False,
        )
        connection.row_factory = sqlite3.Row
        connection.execute(f"PRAGMA busy_timeout = {self.busy_timeout_ms}")
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        try:
            yield connection
        finally:
            connection.close()

    @contextmanager
    def transaction(self):
        with self.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                yield connection
            except Exception:
                connection.rollback()
                raise
            else:
                connection.commit()

    def get_journal_mode(self) -> str:
        self.initialize()
        with self.connection() as connection:
            row = connection.execute("PRAGMA journal_mode").fetchone()
            return str(row[0]).lower()

    def insert_event(
        self,
        connection: sqlite3.Connection,
        *,
        event_type: str,
        actor_type: str,
        actor_id: str,
        workflow_id: str | None,
        idempotency_key: str,
        causation_id: str | None,
        correlation_id: str | None,
        payload: dict[str, Any],
        occurred_at: datetime,
    ) -> sqlite3.Row | None:
        event_id = new_prefixed_id("evt")
        try:
            connection.execute(
                """
                INSERT INTO events (
                    event_id,
                    workflow_id,
                    event_type,
                    actor_type,
                    actor_id,
                    occurred_at,
                    idempotency_key,
                    causation_id,
                    correlation_id,
                    payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    workflow_id,
                    event_type,
                    actor_type,
                    actor_id,
                    occurred_at.isoformat(),
                    idempotency_key,
                    causation_id,
                    correlation_id,
                    json.dumps(payload, sort_keys=True),
                ),
            )
        except sqlite3.IntegrityError:
            return None

        return connection.execute(
            "SELECT * FROM events WHERE idempotency_key = ?",
            (idempotency_key,),
        ).fetchone()

    def get_event_by_idempotency_key(
        self,
        connection: sqlite3.Connection,
        idempotency_key: str,
    ) -> sqlite3.Row | None:
        return connection.execute(
            "SELECT * FROM events WHERE idempotency_key = ?",
            (idempotency_key,),
        ).fetchone()

    def list_all_events(self, connection: sqlite3.Connection) -> list[dict[str, Any]]:
        rows = connection.execute(
            "SELECT * FROM events ORDER BY sequence_no ASC"
        ).fetchall()
        return [self._convert_event_row(row) for row in rows]

    def replace_workflow_projections(
        self,
        connection: sqlite3.Connection,
        projections: list[dict[str, Any]],
    ) -> None:
        connection.execute("DELETE FROM workflow_projection")
        for projection in projections:
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
                    projection["workflow_id"],
                    projection["title"],
                    projection["north_star_goal"],
                    projection["tenant_id"],
                    projection["workspace_id"],
                    projection["current_stage"],
                    projection["status"],
                    projection["budget_total"],
                    projection["budget_used"],
                    projection["board_gate_state"],
                    projection["deadline_at"],
                    projection["started_at"],
                    projection["updated_at"],
                    projection["version"],
                ),
            )

    def replace_ticket_projections(
        self,
        connection: sqlite3.Connection,
        projections: list[dict[str, Any]],
    ) -> None:
        connection.execute("DELETE FROM ticket_projection")
        for projection in projections:
            connection.execute(
                """
                INSERT INTO ticket_projection (
                    ticket_id,
                    workflow_id,
                    node_id,
                    tenant_id,
                    workspace_id,
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
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    projection["ticket_id"],
                    projection["workflow_id"],
                    projection["node_id"],
                    projection["tenant_id"],
                    projection["workspace_id"],
                    projection["status"],
                    projection.get("lease_owner"),
                    projection.get("lease_expires_at"),
                    projection.get("started_at"),
                    projection.get("last_heartbeat_at"),
                    projection.get("heartbeat_expires_at"),
                    projection.get("heartbeat_timeout_sec"),
                    projection.get("retry_count", 0),
                    projection.get("retry_budget"),
                    projection.get("timeout_sla_sec"),
                    projection.get("priority"),
                    projection.get("last_failure_kind"),
                    projection.get("last_failure_message"),
                    projection.get("last_failure_fingerprint"),
                    projection.get("blocking_reason_code"),
                    projection["updated_at"],
                    projection["version"],
                ),
            )

    def replace_node_projections(
        self,
        connection: sqlite3.Connection,
        projections: list[dict[str, Any]],
    ) -> None:
        connection.execute("DELETE FROM node_projection")
        for projection in projections:
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
                    projection["workflow_id"],
                    projection["node_id"],
                    projection["latest_ticket_id"],
                    projection["status"],
                    projection.get("blocking_reason_code"),
                    projection["updated_at"],
                    projection["version"],
                ),
            )

    def replace_employee_projections(
        self,
        connection: sqlite3.Connection,
        projections: list[dict[str, Any]],
    ) -> None:
        connection.execute("DELETE FROM employee_projection")
        for projection in projections:
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
                    projection["employee_id"],
                    projection["role_type"],
                    json.dumps(projection.get("skill_profile_json") or {}, sort_keys=True),
                    json.dumps(projection.get("personality_profile_json") or {}, sort_keys=True),
                    json.dumps(projection.get("aesthetic_profile_json") or {}, sort_keys=True),
                    projection["state"],
                    1 if projection.get("board_approved") else 0,
                    projection.get("provider_id"),
                    json.dumps(projection.get("role_profile_refs") or [], sort_keys=True),
                    projection["updated_at"],
                    projection["version"],
                ),
            )

    def replace_incident_projections(
        self,
        connection: sqlite3.Connection,
        projections: list[dict[str, Any]],
    ) -> None:
        connection.execute("DELETE FROM incident_projection")
        for projection in projections:
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
                    projection["incident_id"],
                    projection["workflow_id"],
                    projection.get("node_id"),
                    projection.get("ticket_id"),
                    projection.get("provider_id"),
                    projection["incident_type"],
                    projection["status"],
                    projection.get("severity"),
                    projection["fingerprint"],
                    projection.get("circuit_breaker_state"),
                    projection["opened_at"],
                    projection.get("closed_at"),
                    json.dumps(projection.get("payload") or {}, sort_keys=True),
                    projection["updated_at"],
                    projection["version"],
                ),
            )

    def refresh_projections(self, connection: sqlite3.Connection) -> None:
        events = self.list_all_events(connection)
        self.replace_workflow_projections(connection, rebuild_workflow_projections(events))
        self.replace_ticket_projections(connection, rebuild_ticket_projections(events))
        self.replace_node_projections(connection, rebuild_node_projections(events))
        self.replace_employee_projections(connection, rebuild_employee_projections(events))
        self.replace_incident_projections(connection, rebuild_incident_projections(events))

    def get_active_workflow(self) -> dict[str, Any] | None:
        self.initialize()
        with self.connection() as connection:
            row = connection.execute(
                """
                SELECT * FROM workflow_projection
                ORDER BY version DESC
                LIMIT 1
                """
            ).fetchone()
            if row is None:
                return None
            return self._convert_workflow_projection_row(row)

    def list_workflow_projections(
        self,
        connection: sqlite3.Connection | None = None,
    ) -> list[dict[str, Any]]:
        query = """
            SELECT * FROM workflow_projection
            ORDER BY version DESC, workflow_id DESC
        """
        if connection is not None:
            rows = connection.execute(query).fetchall()
            return [self._convert_workflow_projection_row(row) for row in rows]

        self.initialize()
        with self.connection() as owned_connection:
            rows = owned_connection.execute(query).fetchall()
            return [self._convert_workflow_projection_row(row) for row in rows]

    def get_workflow_projection(
        self,
        workflow_id: str,
        connection: sqlite3.Connection | None = None,
    ) -> dict[str, Any] | None:
        if connection is not None:
            row = connection.execute(
                "SELECT * FROM workflow_projection WHERE workflow_id = ?",
                (workflow_id,),
            ).fetchone()
            if row is None:
                return None
            return self._convert_workflow_projection_row(row)

        self.initialize()
        with self.connection() as owned_connection:
            row = owned_connection.execute(
                "SELECT * FROM workflow_projection WHERE workflow_id = ?",
                (workflow_id,),
            ).fetchone()
            if row is None:
                return None
            return self._convert_workflow_projection_row(row)

    def get_current_ticket_projection(
        self,
        ticket_id: str,
        connection: sqlite3.Connection | None = None,
    ) -> dict[str, Any] | None:
        if connection is not None:
            row = connection.execute(
                "SELECT * FROM ticket_projection WHERE ticket_id = ?",
                (ticket_id,),
            ).fetchone()
            if row is None:
                return None
            return self._convert_ticket_projection_row(row)

        self.initialize()
        with self.connection() as owned_connection:
            row = owned_connection.execute(
                "SELECT * FROM ticket_projection WHERE ticket_id = ?",
                (ticket_id,),
            ).fetchone()
            if row is None:
                return None
            return self._convert_ticket_projection_row(row)

    def get_current_node_projection(
        self,
        workflow_id: str,
        node_id: str,
        connection: sqlite3.Connection | None = None,
    ) -> dict[str, Any] | None:
        if connection is not None:
            row = connection.execute(
                """
                SELECT * FROM node_projection
                WHERE workflow_id = ? AND node_id = ?
                """,
                (workflow_id, node_id),
            ).fetchone()
            if row is None:
                return None
            return self._convert_node_projection_row(row)

        self.initialize()
        with self.connection() as owned_connection:
            row = owned_connection.execute(
                """
                SELECT * FROM node_projection
                WHERE workflow_id = ? AND node_id = ?
                """,
                (workflow_id, node_id),
            ).fetchone()
            if row is None:
                return None
            return self._convert_node_projection_row(row)

    def get_incident_projection(
        self,
        incident_id: str,
        connection: sqlite3.Connection | None = None,
    ) -> dict[str, Any] | None:
        if connection is not None:
            row = connection.execute(
                "SELECT * FROM incident_projection WHERE incident_id = ?",
                (incident_id,),
            ).fetchone()
            if row is None:
                return None
            return self._convert_incident_projection_row(row)

        self.initialize()
        with self.connection() as owned_connection:
            row = owned_connection.execute(
                "SELECT * FROM incident_projection WHERE incident_id = ?",
                (incident_id,),
            ).fetchone()
            if row is None:
                return None
            return self._convert_incident_projection_row(row)

    def get_open_incident_for_node(
        self,
        workflow_id: str,
        node_id: str,
        connection: sqlite3.Connection | None = None,
    ) -> dict[str, Any] | None:
        query = """
            SELECT * FROM incident_projection
            WHERE workflow_id = ? AND node_id = ? AND status = ?
            ORDER BY opened_at DESC, incident_id DESC
            LIMIT 1
        """
        params = (workflow_id, node_id, "OPEN")
        if connection is not None:
            row = connection.execute(query, params).fetchone()
            if row is None:
                return None
            return self._convert_incident_projection_row(row)

        self.initialize()
        with self.connection() as owned_connection:
            row = owned_connection.execute(query, params).fetchone()
            if row is None:
                return None
            return self._convert_incident_projection_row(row)

    def get_open_incident_for_provider(
        self,
        provider_id: str,
        connection: sqlite3.Connection | None = None,
    ) -> dict[str, Any] | None:
        query = """
            SELECT * FROM incident_projection
            WHERE provider_id = ? AND status = ?
            ORDER BY opened_at DESC, incident_id DESC
            LIMIT 1
        """
        params = (provider_id, "OPEN")
        if connection is not None:
            row = connection.execute(query, params).fetchone()
            if row is None:
                return None
            return self._convert_incident_projection_row(row)

        self.initialize()
        with self.connection() as owned_connection:
            row = owned_connection.execute(query, params).fetchone()
            if row is None:
                return None
            return self._convert_incident_projection_row(row)

    def list_recovering_incidents_for_followup_ticket(
        self,
        connection: sqlite3.Connection,
        followup_ticket_id: str,
    ) -> list[dict[str, Any]]:
        rows = connection.execute(
            """
            SELECT * FROM incident_projection
            WHERE status = ? AND json_extract(payload_json, '$.followup_ticket_id') = ?
            ORDER BY opened_at ASC, incident_id ASC
            """,
            ("RECOVERING", followup_ticket_id),
        ).fetchall()
        return [self._convert_incident_projection_row(row) for row in rows]

    def list_employee_projections(
        self,
        connection: sqlite3.Connection | None = None,
        *,
        states: list[str] | None = None,
        board_approved_only: bool = False,
    ) -> list[dict[str, Any]]:
        if connection is not None:
            return self._list_employee_projections(
                connection,
                states=states,
                board_approved_only=board_approved_only,
            )

        self.initialize()
        with self.connection() as owned_connection:
            return self._list_employee_projections(
                owned_connection,
                states=states,
                board_approved_only=board_approved_only,
            )

    def list_scheduler_worker_candidates(
        self,
        connection: sqlite3.Connection | None = None,
    ) -> list[dict[str, Any]]:
        return self.list_employee_projections(
            connection,
            states=["ACTIVE"],
            board_approved_only=True,
        )

    def get_employee_projection(
        self,
        employee_id: str,
        connection: sqlite3.Connection | None = None,
    ) -> dict[str, Any] | None:
        if connection is not None:
            row = connection.execute(
                "SELECT * FROM employee_projection WHERE employee_id = ?",
                (employee_id,),
            ).fetchone()
            if row is None:
                return None
            return self._convert_employee_projection_row(row)

        self.initialize()
        with self.connection() as owned_connection:
            row = owned_connection.execute(
                "SELECT * FROM employee_projection WHERE employee_id = ?",
                (employee_id,),
            ).fetchone()
            if row is None:
                return None
            return self._convert_employee_projection_row(row)

    def get_worker_bootstrap_state(
        self,
        worker_id: str,
        *,
        tenant_id: str | None = None,
        workspace_id: str | None = None,
        connection: sqlite3.Connection | None = None,
    ) -> dict[str, Any] | None:
        if (tenant_id is None) != (workspace_id is None):
            raise ValueError("tenant_id and workspace_id must be provided together.")
        if tenant_id is None and workspace_id is None:
            bindings = self.list_worker_bootstrap_states(
                connection=connection,
                worker_id=worker_id,
            )
            if len(bindings) != 1:
                return None
            return bindings[0]
        if connection is not None:
            row = connection.execute(
                """
                SELECT * FROM worker_bootstrap_state
                WHERE worker_id = ? AND tenant_id = ? AND workspace_id = ?
                """,
                (worker_id, tenant_id, workspace_id),
            ).fetchone()
            if row is None:
                return None
            return self._convert_worker_bootstrap_state_row(row)

        self.initialize()
        with self.connection() as owned_connection:
            row = owned_connection.execute(
                """
                SELECT * FROM worker_bootstrap_state
                WHERE worker_id = ? AND tenant_id = ? AND workspace_id = ?
                """,
                (worker_id, tenant_id, workspace_id),
            ).fetchone()
            if row is None:
                return None
            return self._convert_worker_bootstrap_state_row(row)

    def list_worker_bootstrap_states(
        self,
        connection: sqlite3.Connection | None = None,
        *,
        worker_id: str | None = None,
        tenant_id: str | None = None,
        workspace_id: str | None = None,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if worker_id is not None:
            clauses.append("worker_id = ?")
            params.append(worker_id)
        if tenant_id is not None:
            clauses.append("tenant_id = ?")
            params.append(tenant_id)
        if workspace_id is not None:
            clauses.append("workspace_id = ?")
            params.append(workspace_id)
        where_clause = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        query = f"""
            SELECT * FROM worker_bootstrap_state
            {where_clause}
            ORDER BY worker_id ASC, tenant_id ASC, workspace_id ASC
        """
        if connection is not None:
            rows = connection.execute(query, tuple(params)).fetchall()
            return [self._convert_worker_bootstrap_state_row(row) for row in rows]

        self.initialize()
        with self.connection() as owned_connection:
            rows = owned_connection.execute(query, tuple(params)).fetchall()
            return [self._convert_worker_bootstrap_state_row(row) for row in rows]

    def list_worker_binding_admin_views(
        self,
        connection: sqlite3.Connection | None = None,
        *,
        worker_id: str | None = None,
        tenant_id: str | None = None,
        workspace_id: str | None = None,
        at: datetime | None = None,
    ) -> list[dict[str, Any]]:
        if (tenant_id is None) != (workspace_id is None):
            raise ValueError("tenant_id and workspace_id must be provided together.")
        active_at = (at or now_local()).isoformat()
        clauses: list[str] = []
        params: list[Any] = [
            active_at,
            active_at,
            TICKET_STATUS_LEASED,
            TICKET_STATUS_EXECUTING,
            "CANCEL_REQUESTED",
        ]
        if worker_id is not None:
            clauses.append("worker_id = ?")
            params.append(worker_id)
        if tenant_id is not None:
            clauses.append("tenant_id = ?")
            params.append(tenant_id)
        if workspace_id is not None:
            clauses.append("workspace_id = ?")
            params.append(workspace_id)
        where_clause = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        query = f"""
            SELECT
                worker_id,
                credential_version,
                tenant_id,
                workspace_id,
                revoked_before,
                rotated_at,
                updated_at,
                (
                    SELECT COUNT(*)
                    FROM worker_session
                    WHERE worker_session.worker_id = worker_bootstrap_state.worker_id
                      AND worker_session.tenant_id = worker_bootstrap_state.tenant_id
                      AND worker_session.workspace_id = worker_bootstrap_state.workspace_id
                      AND worker_session.revoked_at IS NULL
                      AND worker_session.expires_at > ?
                ) AS active_session_count,
                (
                    SELECT COUNT(*)
                    FROM worker_delivery_grant
                    WHERE worker_delivery_grant.worker_id = worker_bootstrap_state.worker_id
                      AND worker_delivery_grant.tenant_id = worker_bootstrap_state.tenant_id
                      AND worker_delivery_grant.workspace_id = worker_bootstrap_state.workspace_id
                      AND worker_delivery_grant.revoked_at IS NULL
                      AND worker_delivery_grant.expires_at > ?
                ) AS active_delivery_grant_count,
                (
                    SELECT COUNT(*)
                    FROM ticket_projection
                    WHERE ticket_projection.lease_owner = worker_bootstrap_state.worker_id
                      AND ticket_projection.tenant_id = worker_bootstrap_state.tenant_id
                      AND ticket_projection.workspace_id = worker_bootstrap_state.workspace_id
                      AND ticket_projection.status IN (?, ?, ?)
                ) AS active_ticket_count,
                (
                    SELECT COUNT(*)
                    FROM worker_bootstrap_issue
                    WHERE worker_bootstrap_issue.worker_id = worker_bootstrap_state.worker_id
                      AND worker_bootstrap_issue.tenant_id = worker_bootstrap_state.tenant_id
                      AND worker_bootstrap_issue.workspace_id = worker_bootstrap_state.workspace_id
                ) AS bootstrap_issue_count,
                (
                    SELECT issued_at
                    FROM worker_bootstrap_issue
                    WHERE worker_bootstrap_issue.worker_id = worker_bootstrap_state.worker_id
                      AND worker_bootstrap_issue.tenant_id = worker_bootstrap_state.tenant_id
                      AND worker_bootstrap_issue.workspace_id = worker_bootstrap_state.workspace_id
                    ORDER BY issued_at DESC, issue_id DESC
                    LIMIT 1
                ) AS latest_bootstrap_issue_at,
                (
                    SELECT issued_via
                    FROM worker_bootstrap_issue
                    WHERE worker_bootstrap_issue.worker_id = worker_bootstrap_state.worker_id
                      AND worker_bootstrap_issue.tenant_id = worker_bootstrap_state.tenant_id
                      AND worker_bootstrap_issue.workspace_id = worker_bootstrap_state.workspace_id
                    ORDER BY issued_at DESC, issue_id DESC
                    LIMIT 1
                ) AS latest_bootstrap_issue_source
            FROM worker_bootstrap_state
            {where_clause}
            ORDER BY worker_id ASC, tenant_id ASC, workspace_id ASC
        """
        if connection is not None:
            rows = connection.execute(query, tuple(params)).fetchall()
            return [self._convert_worker_binding_admin_row(row) for row in rows]

        self.initialize()
        with self.connection() as owned_connection:
            rows = owned_connection.execute(query, tuple(params)).fetchall()
            return [self._convert_worker_binding_admin_row(row) for row in rows]

    def ensure_worker_bootstrap_state(
        self,
        connection: sqlite3.Connection,
        *,
        worker_id: str,
        at: datetime,
        tenant_id: str = DEFAULT_TENANT_ID,
        workspace_id: str = DEFAULT_WORKSPACE_ID,
    ) -> dict[str, Any]:
        existing = self.get_worker_bootstrap_state(
            worker_id,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            connection=connection,
        )
        if existing is not None:
            return existing

        connection.execute(
            """
            INSERT INTO worker_bootstrap_state (
                worker_id,
                credential_version,
                tenant_id,
                workspace_id,
                revoked_before,
                rotated_at,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (worker_id, 1, tenant_id, workspace_id, None, None, at.isoformat()),
        )
        created = self.get_worker_bootstrap_state(
            worker_id,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            connection=connection,
        )
        if created is None:
            raise RuntimeError("Worker bootstrap state could not be created.")
        return created

    def delete_worker_bootstrap_state(
        self,
        connection: sqlite3.Connection,
        *,
        worker_id: str,
        tenant_id: str,
        workspace_id: str,
    ) -> int:
        cursor = connection.execute(
            """
            DELETE FROM worker_bootstrap_state
            WHERE worker_id = ? AND tenant_id = ? AND workspace_id = ?
            """,
            (worker_id, tenant_id, workspace_id),
        )
        return int(cursor.rowcount or 0)

    def get_worker_bootstrap_issue(
        self,
        issue_id: str,
        *,
        connection: sqlite3.Connection | None = None,
    ) -> dict[str, Any] | None:
        if connection is not None:
            row = connection.execute(
                "SELECT * FROM worker_bootstrap_issue WHERE issue_id = ?",
                (issue_id,),
            ).fetchone()
            if row is None:
                return None
            return self._convert_worker_bootstrap_issue_row(row)

        self.initialize()
        with self.connection() as owned_connection:
            row = owned_connection.execute(
                "SELECT * FROM worker_bootstrap_issue WHERE issue_id = ?",
                (issue_id,),
            ).fetchone()
            if row is None:
                return None
            return self._convert_worker_bootstrap_issue_row(row)

    def create_worker_bootstrap_issue(
        self,
        connection: sqlite3.Connection,
        *,
        worker_id: str,
        tenant_id: str,
        workspace_id: str,
        credential_version: int,
        issued_at: datetime,
        expires_at: datetime,
        issued_via: str,
        issued_by: str | None,
        reason: str | None,
    ) -> dict[str, Any]:
        issue_id = new_prefixed_id("wbissue")
        connection.execute(
            """
            INSERT INTO worker_bootstrap_issue (
                issue_id,
                worker_id,
                tenant_id,
                workspace_id,
                credential_version,
                issued_at,
                expires_at,
                issued_via,
                issued_by,
                reason,
                revoked_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                issue_id,
                worker_id,
                tenant_id,
                workspace_id,
                credential_version,
                issued_at.isoformat(),
                expires_at.isoformat(),
                issued_via,
                issued_by,
                reason,
                None,
            ),
        )
        created = self.get_worker_bootstrap_issue(issue_id, connection=connection)
        if created is None:
            raise RuntimeError("Worker bootstrap issue could not be created.")
        return created

    def list_worker_bootstrap_issues(
        self,
        connection: sqlite3.Connection | None = None,
        *,
        issue_id: str | None = None,
        worker_id: str | None = None,
        tenant_id: str | None = None,
        workspace_id: str | None = None,
        active_only: bool = False,
        at: datetime | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        if (tenant_id is None) != (workspace_id is None):
            raise ValueError("tenant_id and workspace_id must be provided together.")
        clauses: list[str] = []
        params: list[Any] = []
        if issue_id is not None:
            clauses.append("issue_id = ?")
            params.append(issue_id)
        if worker_id is not None:
            clauses.append("worker_id = ?")
            params.append(worker_id)
        if tenant_id is not None:
            clauses.append("tenant_id = ?")
            params.append(tenant_id)
        if workspace_id is not None:
            clauses.append("workspace_id = ?")
            params.append(workspace_id)
        if active_only:
            active_at = (at or now_local()).isoformat()
            clauses.append("revoked_at IS NULL")
            clauses.append("expires_at > ?")
            params.append(active_at)
        where_clause = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        limit_clause = f"LIMIT {int(limit)}" if limit is not None else ""
        query = f"""
            SELECT * FROM worker_bootstrap_issue
            {where_clause}
            ORDER BY issued_at DESC, issue_id DESC
            {limit_clause}
        """
        if connection is not None:
            rows = connection.execute(query, tuple(params)).fetchall()
            return [self._convert_worker_bootstrap_issue_row(row) for row in rows]

        self.initialize()
        with self.connection() as owned_connection:
            rows = owned_connection.execute(query, tuple(params)).fetchall()
            return [self._convert_worker_bootstrap_issue_row(row) for row in rows]

    def revoke_worker_bootstrap_issues(
        self,
        connection: sqlite3.Connection,
        *,
        revoked_at: datetime,
        issue_id: str | None = None,
        worker_id: str | None = None,
        tenant_id: str | None = None,
        workspace_id: str | None = None,
    ) -> int:
        if issue_id is None and worker_id is None:
            raise ValueError("Either issue_id or worker_id is required to revoke bootstrap issues.")
        if (tenant_id is None) != (workspace_id is None):
            raise ValueError("tenant_id and workspace_id must be provided together.")

        clauses: list[str] = ["revoked_at IS NULL", "expires_at > ?"]
        params: list[Any] = [revoked_at.isoformat(), revoked_at.isoformat()]
        if issue_id is not None:
            clauses.append("issue_id = ?")
            params.append(issue_id)
        if worker_id is not None:
            clauses.append("worker_id = ?")
            params.append(worker_id)
        if tenant_id is not None:
            clauses.append("tenant_id = ?")
            params.append(tenant_id)
        if workspace_id is not None:
            clauses.append("workspace_id = ?")
            params.append(workspace_id)
        cursor = connection.execute(
            f"""
            UPDATE worker_bootstrap_issue
            SET revoked_at = ?
            WHERE {' AND '.join(clauses)}
            """,
            tuple(params),
        )
        return int(cursor.rowcount or 0)

    def rotate_worker_bootstrap_state(
        self,
        connection: sqlite3.Connection,
        *,
        worker_id: str,
        tenant_id: str,
        workspace_id: str,
        rotated_at: datetime,
    ) -> dict[str, Any]:
        current = self.get_worker_bootstrap_state(
            worker_id,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            connection=connection,
        )
        if current is None:
            raise RuntimeError(
                "Worker bootstrap state could not be found for the requested tenant/workspace scope."
            )
        next_version = int(current["credential_version"]) + 1
        connection.execute(
            """
            UPDATE worker_bootstrap_state
            SET credential_version = ?,
                revoked_before = ?,
                rotated_at = ?,
                updated_at = ?
            WHERE worker_id = ? AND tenant_id = ? AND workspace_id = ?
            """,
            (
                next_version,
                rotated_at.isoformat(),
                rotated_at.isoformat(),
                rotated_at.isoformat(),
                worker_id,
                tenant_id,
                workspace_id,
            ),
        )
        self.revoke_worker_sessions(
            connection,
            worker_id=worker_id,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            revoked_at=rotated_at,
            revoke_reason="Worker bootstrap credential rotated.",
            revoked_via="worker_bootstrap_rotate",
        )
        self.revoke_worker_bootstrap_issues(
            connection,
            worker_id=worker_id,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            revoked_at=rotated_at,
        )
        self.revoke_worker_delivery_grants(
            connection,
            worker_id=worker_id,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            revoked_at=rotated_at,
            revoke_reason="Worker bootstrap credential rotated.",
            revoked_via="worker_bootstrap_rotate",
        )
        rotated = self.get_worker_bootstrap_state(
            worker_id,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            connection=connection,
        )
        if rotated is None:
            raise RuntimeError("Rotated worker bootstrap state could not be loaded.")
        return rotated

    def revoke_worker_bootstrap_state(
        self,
        connection: sqlite3.Connection,
        *,
        worker_id: str,
        tenant_id: str,
        workspace_id: str,
        revoked_at: datetime,
    ) -> dict[str, Any]:
        current = self.get_worker_bootstrap_state(
            worker_id,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            connection=connection,
        )
        if current is None:
            raise RuntimeError(
                "Worker bootstrap state could not be found for the requested tenant/workspace scope."
            )
        connection.execute(
            """
            UPDATE worker_bootstrap_state
            SET revoked_before = ?, updated_at = ?
            WHERE worker_id = ? AND tenant_id = ? AND workspace_id = ?
            """,
            (
                revoked_at.isoformat(),
                revoked_at.isoformat(),
                worker_id,
                tenant_id,
                workspace_id,
            ),
        )
        self.revoke_worker_sessions(
            connection,
            worker_id=worker_id,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            revoked_at=revoked_at,
            revoke_reason="Worker bootstrap credential revoked.",
            revoked_via="worker_bootstrap_revoke",
        )
        self.revoke_worker_bootstrap_issues(
            connection,
            worker_id=worker_id,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            revoked_at=revoked_at,
        )
        self.revoke_worker_delivery_grants(
            connection,
            worker_id=worker_id,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            revoked_at=revoked_at,
            revoke_reason="Worker bootstrap credential revoked.",
            revoked_via="worker_bootstrap_revoke",
        )
        revoked = self.get_worker_bootstrap_state(
            worker_id,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            connection=connection,
        )
        if revoked is None:
            raise RuntimeError("Revoked worker bootstrap state could not be loaded.")
        return revoked

    def get_worker_session(
        self,
        session_id: str,
        connection: sqlite3.Connection | None = None,
    ) -> dict[str, Any] | None:
        if connection is not None:
            row = connection.execute(
                "SELECT * FROM worker_session WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            if row is None:
                return None
            return self._convert_worker_session_row(row)

        self.initialize()
        with self.connection() as owned_connection:
            row = owned_connection.execute(
                "SELECT * FROM worker_session WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            if row is None:
                return None
            return self._convert_worker_session_row(row)

    def create_worker_session(
        self,
        connection: sqlite3.Connection,
        *,
        worker_id: str,
        tenant_id: str,
        workspace_id: str,
        issued_at: datetime,
        expires_at: datetime,
        credential_version: int,
    ) -> dict[str, Any]:
        session_id = new_prefixed_id("wsess")
        connection.execute(
            """
            INSERT INTO worker_session (
                session_id,
                worker_id,
                tenant_id,
                workspace_id,
                issued_at,
                expires_at,
                last_seen_at,
                revoked_at,
                credential_version
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                worker_id,
                tenant_id,
                workspace_id,
                issued_at.isoformat(),
                expires_at.isoformat(),
                issued_at.isoformat(),
                None,
                credential_version,
            ),
        )
        created = self.get_worker_session(session_id, connection=connection)
        if created is None:
            raise RuntimeError("Worker session could not be created.")
        return created

    def refresh_worker_session(
        self,
        connection: sqlite3.Connection,
        *,
        session_id: str,
        refreshed_at: datetime,
        expires_at: datetime,
    ) -> dict[str, Any] | None:
        connection.execute(
            """
            UPDATE worker_session
            SET expires_at = ?, last_seen_at = ?
            WHERE session_id = ?
            """,
            (expires_at.isoformat(), refreshed_at.isoformat(), session_id),
        )
        return self.get_worker_session(session_id, connection=connection)

    def list_worker_sessions(
        self,
        connection: sqlite3.Connection | None = None,
        *,
        worker_id: str | None = None,
        tenant_id: str | None = None,
        workspace_id: str | None = None,
        active_only: bool = False,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if worker_id is not None:
            clauses.append("worker_id = ?")
            params.append(worker_id)
        if tenant_id is not None:
            clauses.append("tenant_id = ?")
            params.append(tenant_id)
        if workspace_id is not None:
            clauses.append("workspace_id = ?")
            params.append(workspace_id)
        if active_only:
            clauses.append("revoked_at IS NULL")
        where_clause = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        query = f"""
            SELECT * FROM worker_session
            {where_clause}
            ORDER BY issued_at ASC, session_id ASC
        """
        if connection is not None:
            rows = connection.execute(query, tuple(params)).fetchall()
            return [self._convert_worker_session_row(row) for row in rows]

        self.initialize()
        with self.connection() as owned_connection:
            rows = owned_connection.execute(query, tuple(params)).fetchall()
            return [self._convert_worker_session_row(row) for row in rows]

    def revoke_worker_sessions(
        self,
        connection: sqlite3.Connection,
        *,
        revoked_at: datetime,
        session_id: str | None = None,
        worker_id: str | None = None,
        tenant_id: str | None = None,
        workspace_id: str | None = None,
        revoke_reason: str | None = None,
        revoked_via: str | None = None,
        revoked_by: str | None = None,
    ) -> int:
        if session_id is None and worker_id is None:
            raise ValueError("Either session_id or worker_id is required to revoke worker sessions.")
        if (tenant_id is None) != (workspace_id is None):
            raise ValueError("tenant_id and workspace_id must be provided together.")

        clauses: list[str] = ["revoked_at IS NULL"]
        params: list[Any] = [
            revoked_at.isoformat(),
            revoke_reason,
            revoked_via,
            revoked_by,
        ]
        if session_id is not None:
            clauses.append("session_id = ?")
            params.append(session_id)
        if worker_id is not None:
            clauses.append("worker_id = ?")
            params.append(worker_id)
        if tenant_id is not None:
            clauses.append("tenant_id = ?")
            params.append(tenant_id)
        if workspace_id is not None:
            clauses.append("workspace_id = ?")
            params.append(workspace_id)
        where_clause = " AND ".join(clauses)
        cursor = connection.execute(
            f"""
            UPDATE worker_session
            SET revoked_at = ?,
                revoke_reason = ?,
                revoked_via = ?,
                revoked_by = ?
            WHERE {where_clause}
            """,
            tuple(params),
        )
        if cursor.rowcount:
            self.revoke_worker_delivery_grants(
                connection,
                session_id=session_id,
                worker_id=worker_id,
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                revoked_at=revoked_at,
                revoke_reason=revoke_reason or "Worker session revoked.",
                revoked_via=revoked_via,
                revoked_by=revoked_by,
            )
        return int(cursor.rowcount or 0)

    def get_worker_delivery_grant(
        self,
        grant_id: str,
        connection: sqlite3.Connection | None = None,
    ) -> dict[str, Any] | None:
        if connection is not None:
            row = connection.execute(
                "SELECT * FROM worker_delivery_grant WHERE grant_id = ?",
                (grant_id,),
            ).fetchone()
            if row is None:
                return None
            return self._convert_worker_delivery_grant_row(row)

        self.initialize()
        with self.connection() as owned_connection:
            row = owned_connection.execute(
                "SELECT * FROM worker_delivery_grant WHERE grant_id = ?",
                (grant_id,),
            ).fetchone()
            if row is None:
                return None
            return self._convert_worker_delivery_grant_row(row)

    def create_worker_delivery_grant(
        self,
        connection: sqlite3.Connection,
        *,
        scope: str,
        worker_id: str,
        session_id: str,
        credential_version: int,
        tenant_id: str,
        workspace_id: str,
        ticket_id: str,
        issued_at: datetime,
        expires_at: datetime,
        artifact_ref: str | None = None,
        artifact_action: str | None = None,
        command_name: str | None = None,
    ) -> dict[str, Any]:
        grant_id = new_prefixed_id("wgrant")
        connection.execute(
            """
            INSERT INTO worker_delivery_grant (
                grant_id,
                scope,
                worker_id,
                session_id,
                credential_version,
                tenant_id,
                workspace_id,
                ticket_id,
                artifact_ref,
                artifact_action,
                command_name,
                issued_at,
                expires_at,
                revoked_at,
                revoke_reason
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                grant_id,
                scope,
                worker_id,
                session_id,
                credential_version,
                tenant_id,
                workspace_id,
                ticket_id,
                artifact_ref,
                artifact_action,
                command_name,
                issued_at.isoformat(),
                expires_at.isoformat(),
                None,
                None,
            ),
        )
        created = self.get_worker_delivery_grant(grant_id, connection=connection)
        if created is None:
            raise RuntimeError("Worker delivery grant could not be created.")
        return created

    def list_worker_delivery_grants(
        self,
        connection: sqlite3.Connection | None = None,
        *,
        worker_id: str | None = None,
        session_id: str | None = None,
        ticket_id: str | None = None,
        tenant_id: str | None = None,
        workspace_id: str | None = None,
        active_only: bool = False,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if worker_id is not None:
            clauses.append("worker_id = ?")
            params.append(worker_id)
        if session_id is not None:
            clauses.append("session_id = ?")
            params.append(session_id)
        if ticket_id is not None:
            clauses.append("ticket_id = ?")
            params.append(ticket_id)
        if tenant_id is not None:
            clauses.append("tenant_id = ?")
            params.append(tenant_id)
        if workspace_id is not None:
            clauses.append("workspace_id = ?")
            params.append(workspace_id)
        if active_only:
            clauses.append("revoked_at IS NULL")
        where_clause = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        query = f"""
            SELECT * FROM worker_delivery_grant
            {where_clause}
            ORDER BY issued_at ASC, grant_id ASC
        """
        if connection is not None:
            rows = connection.execute(query, tuple(params)).fetchall()
            return [self._convert_worker_delivery_grant_row(row) for row in rows]

        self.initialize()
        with self.connection() as owned_connection:
            rows = owned_connection.execute(query, tuple(params)).fetchall()
            return [self._convert_worker_delivery_grant_row(row) for row in rows]

    def revoke_worker_delivery_grants(
        self,
        connection: sqlite3.Connection,
        *,
        revoked_at: datetime,
        revoke_reason: str,
        revoked_via: str | None = None,
        revoked_by: str | None = None,
        grant_id: str | None = None,
        session_id: str | None = None,
        worker_id: str | None = None,
        ticket_id: str | None = None,
        tenant_id: str | None = None,
        workspace_id: str | None = None,
    ) -> int:
        if (
            grant_id is None
            and session_id is None
            and worker_id is None
            and ticket_id is None
            and tenant_id is None
            and workspace_id is None
        ):
            raise ValueError(
                "At least one filter is required to revoke worker delivery grants."
            )
        if (tenant_id is None) != (workspace_id is None):
            raise ValueError("tenant_id and workspace_id must be provided together.")

        clauses: list[str] = ["revoked_at IS NULL"]
        params: list[Any] = [revoked_at.isoformat(), revoke_reason, revoked_via, revoked_by]
        if grant_id is not None:
            clauses.append("grant_id = ?")
            params.append(grant_id)
        if session_id is not None:
            clauses.append("session_id = ?")
            params.append(session_id)
        if worker_id is not None:
            clauses.append("worker_id = ?")
            params.append(worker_id)
        if ticket_id is not None:
            clauses.append("ticket_id = ?")
            params.append(ticket_id)
        if tenant_id is not None:
            clauses.append("tenant_id = ?")
            params.append(tenant_id)
        if workspace_id is not None:
            clauses.append("workspace_id = ?")
            params.append(workspace_id)
        where_clause = " AND ".join(clauses)
        cursor = connection.execute(
            f"""
            UPDATE worker_delivery_grant
            SET revoked_at = ?, revoke_reason = ?, revoked_via = ?, revoked_by = ?
            WHERE {where_clause}
            """,
            tuple(params),
        )
        return int(cursor.rowcount or 0)

    def append_worker_auth_rejection_log(
        self,
        connection: sqlite3.Connection,
        *,
        occurred_at: datetime,
        route_family: str,
        reason_code: str,
        worker_id: str | None = None,
        session_id: str | None = None,
        grant_id: str | None = None,
        ticket_id: str | None = None,
        tenant_id: str | None = None,
        workspace_id: str | None = None,
    ) -> dict[str, Any]:
        rejection_id = new_prefixed_id("wreject")
        connection.execute(
            """
            INSERT INTO worker_auth_rejection_log (
                rejection_id,
                occurred_at,
                route_family,
                reason_code,
                worker_id,
                session_id,
                grant_id,
                ticket_id,
                tenant_id,
                workspace_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                rejection_id,
                occurred_at.isoformat(),
                route_family,
                reason_code,
                worker_id,
                session_id,
                grant_id,
                ticket_id,
                tenant_id,
                workspace_id,
            ),
        )
        row = connection.execute(
            "SELECT * FROM worker_auth_rejection_log WHERE rejection_id = ?",
            (rejection_id,),
        ).fetchone()
        if row is None:
            raise RuntimeError("Worker auth rejection log could not be created.")
        return self._convert_worker_auth_rejection_row(row)

    def list_worker_auth_rejection_logs(
        self,
        connection: sqlite3.Connection | None = None,
        *,
        worker_id: str | None = None,
        tenant_id: str | None = None,
        workspace_id: str | None = None,
        route_family: str | None = None,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if worker_id is not None:
            clauses.append("worker_id = ?")
            params.append(worker_id)
        if tenant_id is not None:
            clauses.append("tenant_id = ?")
            params.append(tenant_id)
        if workspace_id is not None:
            clauses.append("workspace_id = ?")
            params.append(workspace_id)
        if route_family is not None:
            clauses.append("route_family = ?")
            params.append(route_family)
        where_clause = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        query = f"""
            SELECT * FROM worker_auth_rejection_log
            {where_clause}
            ORDER BY occurred_at ASC, rejection_id ASC
        """
        if connection is not None:
            rows = connection.execute(query, tuple(params)).fetchall()
            return [self._convert_worker_auth_rejection_row(row) for row in rows]

        self.initialize()
        with self.connection() as owned_connection:
            rows = owned_connection.execute(query, tuple(params)).fetchall()
            return [self._convert_worker_auth_rejection_row(row) for row in rows]

    def get_worker_admin_token_issue(
        self,
        token_id: str,
        *,
        connection: sqlite3.Connection | None = None,
    ) -> dict[str, Any] | None:
        if connection is not None:
            row = connection.execute(
                "SELECT * FROM worker_admin_token_issue WHERE token_id = ?",
                (token_id,),
            ).fetchone()
            return None if row is None else self._convert_worker_admin_token_issue_row(row)

        self.initialize()
        with self.connection() as owned_connection:
            row = owned_connection.execute(
                "SELECT * FROM worker_admin_token_issue WHERE token_id = ?",
                (token_id,),
            ).fetchone()
            return None if row is None else self._convert_worker_admin_token_issue_row(row)

    def create_worker_admin_token_issue(
        self,
        connection: sqlite3.Connection,
        *,
        token_id: str | None,
        operator_id: str,
        role: str,
        tenant_id: str | None,
        workspace_id: str | None,
        issued_at: datetime,
        expires_at: datetime,
        issued_via: str,
        issued_by: str | None,
    ) -> dict[str, Any]:
        resolved_token_id = token_id or new_prefixed_id("wop")
        connection.execute(
            """
            INSERT INTO worker_admin_token_issue (
                token_id,
                operator_id,
                role,
                tenant_id,
                workspace_id,
                issued_at,
                expires_at,
                issued_via,
                issued_by,
                revoked_at,
                revoked_by,
                revoke_reason
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, NULL)
            """,
            (
                resolved_token_id,
                operator_id,
                role,
                tenant_id,
                workspace_id,
                issued_at.isoformat(),
                expires_at.isoformat(),
                issued_via,
                issued_by,
            ),
        )
        created = self.get_worker_admin_token_issue(resolved_token_id, connection=connection)
        if created is None:
            raise RuntimeError("Worker-admin token issue could not be created.")
        return created

    def update_worker_admin_token_issue_expiry(
        self,
        connection: sqlite3.Connection,
        *,
        token_id: str,
        expires_at: datetime,
    ) -> dict[str, Any]:
        connection.execute(
            """
            UPDATE worker_admin_token_issue
            SET expires_at = ?
            WHERE token_id = ?
            """,
            (expires_at.isoformat(), token_id),
        )
        updated = self.get_worker_admin_token_issue(token_id, connection=connection)
        if updated is None:
            raise RuntimeError("Worker-admin token issue was not found.")
        return updated

    def list_worker_admin_token_issues(
        self,
        connection: sqlite3.Connection | None = None,
        *,
        operator_id: str | None = None,
        role: str | None = None,
        tenant_id: str | None = None,
        workspace_id: str | None = None,
        active_only: bool = False,
        at: datetime | None = None,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if operator_id is not None:
            clauses.append("operator_id = ?")
            params.append(operator_id)
        if role is not None:
            clauses.append("role = ?")
            params.append(role)
        if tenant_id is not None:
            clauses.append("tenant_id = ?")
            params.append(tenant_id)
        if workspace_id is not None:
            clauses.append("workspace_id = ?")
            params.append(workspace_id)
        if active_only:
            active_at = (at or now_local()).isoformat()
            clauses.append("revoked_at IS NULL")
            clauses.append("expires_at > ?")
            params.append(active_at)
        where_clause = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        query = f"""
            SELECT * FROM worker_admin_token_issue
            {where_clause}
            ORDER BY issued_at DESC, token_id DESC
            LIMIT ?
        """
        params.append(int(limit))
        if connection is not None:
            rows = connection.execute(query, tuple(params)).fetchall()
            return [self._convert_worker_admin_token_issue_row(row) for row in rows]

        self.initialize()
        with self.connection() as owned_connection:
            rows = owned_connection.execute(query, tuple(params)).fetchall()
            return [self._convert_worker_admin_token_issue_row(row) for row in rows]

    def revoke_worker_admin_token_issue(
        self,
        connection: sqlite3.Connection,
        *,
        token_id: str,
        revoked_at: datetime,
        revoked_by: str,
        revoke_reason: str,
    ) -> dict[str, Any]:
        existing = self.get_worker_admin_token_issue(token_id, connection=connection)
        if existing is None:
            raise RuntimeError("Worker-admin token issue was not found.")
        connection.execute(
            """
            UPDATE worker_admin_token_issue
            SET revoked_at = ?, revoked_by = ?, revoke_reason = ?
            WHERE token_id = ?
            """,
            (
                revoked_at.isoformat(),
                revoked_by,
                revoke_reason,
                token_id,
            ),
        )
        updated = self.get_worker_admin_token_issue(token_id, connection=connection)
        if updated is None:
            raise RuntimeError("Worker-admin token issue could not be revoked.")
        return updated

    def append_worker_admin_auth_rejection_log(
        self,
        connection: sqlite3.Connection,
        *,
        occurred_at: datetime,
        route_path: str,
        reason_code: str,
        operator_id: str | None,
        operator_role: str | None,
        token_id: str | None,
        tenant_id: str | None,
        workspace_id: str | None,
        trusted_proxy_id: str | None = None,
        source_ip: str | None = None,
    ) -> dict[str, Any]:
        rejection_id = new_prefixed_id("warej")
        connection.execute(
            """
            INSERT INTO worker_admin_auth_rejection_log (
                rejection_id,
                occurred_at,
                route_path,
                reason_code,
                operator_id,
                operator_role,
                token_id,
                tenant_id,
                workspace_id,
                trusted_proxy_id,
                source_ip
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                rejection_id,
                occurred_at.isoformat(),
                route_path,
                reason_code,
                operator_id,
                operator_role,
                token_id,
                tenant_id,
                workspace_id,
                trusted_proxy_id,
                source_ip,
            ),
        )
        row = connection.execute(
            "SELECT * FROM worker_admin_auth_rejection_log WHERE rejection_id = ?",
            (rejection_id,),
        ).fetchone()
        if row is None:
            raise RuntimeError("Worker-admin auth rejection log could not be created.")
        return self._convert_worker_admin_auth_rejection_row(row)

    def list_worker_admin_auth_rejection_logs(
        self,
        connection: sqlite3.Connection | None = None,
        *,
        operator_id: str | None = None,
        operator_role: str | None = None,
        token_id: str | None = None,
        tenant_id: str | None = None,
        workspace_id: str | None = None,
        route_path: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if operator_id is not None:
            clauses.append("operator_id = ?")
            params.append(operator_id)
        if operator_role is not None:
            clauses.append("operator_role = ?")
            params.append(operator_role)
        if token_id is not None:
            clauses.append("token_id = ?")
            params.append(token_id)
        if tenant_id is not None:
            clauses.append("tenant_id = ?")
            params.append(tenant_id)
        if workspace_id is not None:
            clauses.append("workspace_id = ?")
            params.append(workspace_id)
        if route_path is not None:
            clauses.append("route_path = ?")
            params.append(route_path)
        where_clause = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        query = f"""
            SELECT * FROM worker_admin_auth_rejection_log
            {where_clause}
            ORDER BY occurred_at DESC, rejection_id DESC
            LIMIT ?
        """
        params.append(int(limit))
        if connection is not None:
            rows = connection.execute(query, tuple(params)).fetchall()
            return [self._convert_worker_admin_auth_rejection_row(row) for row in rows]

        self.initialize()
        with self.connection() as owned_connection:
            rows = owned_connection.execute(query, tuple(params)).fetchall()
            return [self._convert_worker_admin_auth_rejection_row(row) for row in rows]

    def append_worker_admin_action_log(
        self,
        connection: sqlite3.Connection,
        *,
        occurred_at: datetime,
        operator_id: str,
        operator_role: str,
        auth_source: str,
        action_type: str,
        dry_run: bool,
        tenant_id: str | None = None,
        workspace_id: str | None = None,
        worker_id: str | None = None,
        session_id: str | None = None,
        grant_id: str | None = None,
        issue_id: str | None = None,
        trusted_proxy_id: str | None = None,
        source_ip: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        action_id = new_prefixed_id("wact")
        connection.execute(
            """
            INSERT INTO worker_admin_action_log (
                action_id,
                occurred_at,
                operator_id,
                operator_role,
                auth_source,
                tenant_id,
                workspace_id,
                worker_id,
                session_id,
                grant_id,
                issue_id,
                trusted_proxy_id,
                source_ip,
                action_type,
                dry_run,
                details_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                action_id,
                occurred_at.isoformat(),
                operator_id,
                operator_role,
                auth_source,
                tenant_id,
                workspace_id,
                worker_id,
                session_id,
                grant_id,
                issue_id,
                trusted_proxy_id,
                source_ip,
                action_type,
                1 if dry_run else 0,
                json.dumps(details or {}, sort_keys=True),
            ),
        )
        row = connection.execute(
            "SELECT * FROM worker_admin_action_log WHERE action_id = ?",
            (action_id,),
        ).fetchone()
        if row is None:
            raise RuntimeError("Worker admin action log could not be created.")
        return self._convert_worker_admin_action_log_row(row)

    def list_worker_admin_action_logs(
        self,
        connection: sqlite3.Connection | None = None,
        *,
        tenant_id: str | None = None,
        workspace_id: str | None = None,
        worker_id: str | None = None,
        operator_id: str | None = None,
        action_type: str | None = None,
        dry_run: bool | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if tenant_id is not None:
            clauses.append("tenant_id = ?")
            params.append(tenant_id)
        if workspace_id is not None:
            clauses.append("workspace_id = ?")
            params.append(workspace_id)
        if worker_id is not None:
            clauses.append("worker_id = ?")
            params.append(worker_id)
        if operator_id is not None:
            clauses.append("operator_id = ?")
            params.append(operator_id)
        if action_type is not None:
            clauses.append("action_type = ?")
            params.append(action_type)
        if dry_run is not None:
            clauses.append("dry_run = ?")
            params.append(1 if dry_run else 0)
        where_clause = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        query = f"""
            SELECT * FROM worker_admin_action_log
            {where_clause}
            ORDER BY occurred_at DESC, action_id DESC
            LIMIT ?
        """
        params.append(int(limit))
        if connection is not None:
            rows = connection.execute(query, tuple(params)).fetchall()
            return [self._convert_worker_admin_action_log_row(row) for row in rows]

        self.initialize()
        with self.connection() as owned_connection:
            rows = owned_connection.execute(query, tuple(params)).fetchall()
            return [self._convert_worker_admin_action_log_row(row) for row in rows]

    def append_ceo_shadow_run(
        self,
        connection: sqlite3.Connection,
        *,
        workflow_id: str,
        trigger_type: str,
        trigger_ref: str | None,
        occurred_at: datetime,
        effective_mode: str,
        provider_health_summary: str,
        model: str | None,
        prompt_version: str,
        provider_response_id: str | None,
        fallback_reason: str | None,
        snapshot: dict[str, Any],
        proposed_action_batch: dict[str, Any],
        accepted_actions: list[dict[str, Any]],
        rejected_actions: list[dict[str, Any]],
        executed_actions: list[dict[str, Any]],
        execution_summary: dict[str, Any],
        deterministic_fallback_used: bool,
        deterministic_fallback_reason: str | None,
        comparison: dict[str, Any],
    ) -> dict[str, Any]:
        run_id = new_prefixed_id("ceo")
        connection.execute(
            """
            INSERT INTO ceo_shadow_run (
                run_id,
                workflow_id,
                trigger_type,
                trigger_ref,
                occurred_at,
                effective_mode,
                provider_health_summary,
                model,
                prompt_version,
                provider_response_id,
                fallback_reason,
                snapshot_json,
                proposed_action_batch_json,
                accepted_actions_json,
                rejected_actions_json,
                executed_actions_json,
                execution_summary_json,
                deterministic_fallback_used,
                deterministic_fallback_reason,
                comparison_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                workflow_id,
                trigger_type,
                trigger_ref,
                occurred_at.isoformat(),
                effective_mode,
                provider_health_summary,
                model,
                prompt_version,
                provider_response_id,
                fallback_reason,
                json.dumps(snapshot, sort_keys=True),
                json.dumps(proposed_action_batch, sort_keys=True),
                json.dumps(accepted_actions, sort_keys=True),
                json.dumps(rejected_actions, sort_keys=True),
                json.dumps(executed_actions, sort_keys=True),
                json.dumps(execution_summary, sort_keys=True),
                1 if deterministic_fallback_used else 0,
                deterministic_fallback_reason,
                json.dumps(comparison, sort_keys=True),
            ),
        )
        row = connection.execute(
            "SELECT * FROM ceo_shadow_run WHERE run_id = ?",
            (run_id,),
        ).fetchone()
        if row is None:
            raise RuntimeError("CEO shadow run could not be created.")
        return self._convert_ceo_shadow_run_row(row)

    def list_ceo_shadow_runs(
        self,
        workflow_id: str,
        *,
        limit: int = 20,
        connection: sqlite3.Connection | None = None,
    ) -> list[dict[str, Any]]:
        query = """
            SELECT * FROM ceo_shadow_run
            WHERE workflow_id = ?
            ORDER BY occurred_at DESC, run_id DESC
            LIMIT ?
        """
        params = (workflow_id, int(limit))
        if connection is not None:
            rows = connection.execute(query, params).fetchall()
            return [self._convert_ceo_shadow_run_row(row) for row in rows]

        self.initialize()
        with self.connection() as owned_connection:
            rows = owned_connection.execute(query, params).fetchall()
            return [self._convert_ceo_shadow_run_row(row) for row in rows]

    def get_latest_ceo_shadow_run_for_trigger(
        self,
        workflow_id: str,
        trigger_type: str,
        *,
        connection: sqlite3.Connection | None = None,
    ) -> dict[str, Any] | None:
        query = """
            SELECT * FROM ceo_shadow_run
            WHERE workflow_id = ? AND trigger_type = ?
            ORDER BY occurred_at DESC, run_id DESC
            LIMIT 1
        """
        params = (workflow_id, trigger_type)
        if connection is not None:
            row = connection.execute(query, params).fetchone()
            return None if row is None else self._convert_ceo_shadow_run_row(row)

        self.initialize()
        with self.connection() as owned_connection:
            row = owned_connection.execute(query, params).fetchone()
            return None if row is None else self._convert_ceo_shadow_run_row(row)

    def list_ticket_projections_by_statuses(
        self,
        connection: sqlite3.Connection,
        statuses: list[str],
    ) -> list[dict[str, Any]]:
        if not statuses:
            return []
        placeholders = ", ".join("?" for _ in statuses)
        rows = connection.execute(
            f"""
            SELECT * FROM ticket_projection
            WHERE status IN ({placeholders})
            ORDER BY updated_at ASC, ticket_id ASC
            """,
            tuple(statuses),
        ).fetchall()
        return [self._convert_ticket_projection_row(row) for row in rows]

    def list_ticket_projections_by_statuses_readonly(
        self,
        statuses: list[str],
    ) -> list[dict[str, Any]]:
        self.initialize()
        with self.connection() as connection:
            return self.list_ticket_projections_by_statuses(connection, statuses)

    def list_timed_out_ticket_candidates(
        self,
        connection: sqlite3.Connection,
        now: datetime,
    ) -> list[dict[str, Any]]:
        return self.list_total_timeout_ticket_candidates(connection, now)

    def list_total_timeout_ticket_candidates(
        self,
        connection: sqlite3.Connection,
        now: datetime,
    ) -> list[dict[str, Any]]:
        executing = self.list_ticket_projections_by_statuses(connection, [TICKET_STATUS_EXECUTING])
        return [
            ticket
            for ticket in executing
            if ticket.get("started_at") is not None
            and ticket.get("timeout_sla_sec") is not None
            and ticket["started_at"] + timedelta(seconds=ticket["timeout_sla_sec"]) <= now
        ]

    def list_heartbeat_timeout_ticket_candidates(
        self,
        connection: sqlite3.Connection,
        now: datetime,
    ) -> list[dict[str, Any]]:
        executing = self.list_ticket_projections_by_statuses(connection, [TICKET_STATUS_EXECUTING])
        return [
            ticket
            for ticket in executing
            if ticket.get("heartbeat_expires_at") is not None
            and ticket["heartbeat_expires_at"] <= now
        ]

    def list_dispatchable_ticket_projections(
        self,
        connection: sqlite3.Connection,
        now: datetime,
    ) -> list[dict[str, Any]]:
        candidates = self.list_ticket_projections_by_statuses(
            connection,
            [TICKET_STATUS_PENDING, TICKET_STATUS_LEASED],
        )
        dispatchable = []
        for ticket in candidates:
            if ticket["status"] == TICKET_STATUS_PENDING:
                dispatchable.append(ticket)
                continue
            lease_expiry = ticket.get("lease_expires_at")
            if lease_expiry is not None and lease_expiry <= now:
                dispatchable.append(ticket)
        return dispatchable

    def get_latest_ticket_created_payload(
        self,
        connection: sqlite3.Connection,
        ticket_id: str,
    ) -> dict[str, Any] | None:
        rows = connection.execute(
            """
            SELECT payload_json
            FROM events
            WHERE event_type = ?
            ORDER BY sequence_no DESC
            """,
            (EVENT_TICKET_CREATED,),
        ).fetchall()
        for row in rows:
            payload = json.loads(row["payload_json"])
            if payload.get("ticket_id") == ticket_id:
                return payload
        return None

    def get_latest_ticket_terminal_event(
        self,
        connection: sqlite3.Connection,
        ticket_id: str,
    ) -> dict[str, Any] | None:
        rows = connection.execute(
            """
            SELECT * FROM events
            WHERE event_type IN (?, ?, ?)
            ORDER BY sequence_no DESC
            """,
            (EVENT_TICKET_TIMED_OUT, EVENT_TICKET_FAILED, EVENT_TICKET_COMPLETED),
        ).fetchall()
        for row in rows:
            converted = self._convert_event_row(row)
            if converted.get("ticket_id") == ticket_id:
                return converted
        return None

    def save_compiled_context_bundle(
        self,
        connection: sqlite3.Connection,
        bundle: CompiledContextBundle,
    ) -> None:
        payload = bundle.model_dump(mode="json")
        connection.execute(
            """
            INSERT INTO compiled_context_bundle (
                bundle_id,
                compile_request_id,
                ticket_id,
                workflow_id,
                node_id,
                compiler_version,
                compiled_at,
                bundle_version,
                payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                bundle.meta.bundle_id,
                bundle.meta.compile_request_id,
                bundle.meta.ticket_id,
                bundle.meta.workflow_id,
                bundle.meta.node_id,
                bundle.meta.compiler_version,
                bundle.meta.compiled_at.isoformat(),
                "CompiledContextBundle_v1",
                json.dumps(payload, sort_keys=True),
            ),
        )

    def save_compile_manifest(
        self,
        connection: sqlite3.Connection,
        manifest: CompileManifest,
    ) -> None:
        payload = manifest.model_dump(mode="json")
        connection.execute(
            """
            INSERT INTO compile_manifest (
                compile_id,
                bundle_id,
                compile_request_id,
                ticket_id,
                workflow_id,
                node_id,
                compiler_version,
                compiled_at,
                manifest_version,
                payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                manifest.compile_meta.compile_id,
                manifest.compile_meta.bundle_id,
                manifest.compile_meta.compile_request_id,
                manifest.compile_meta.ticket_id,
                manifest.compile_meta.workflow_id,
                manifest.compile_meta.node_id,
                manifest.compile_meta.compiler_version,
                manifest.compile_meta.compiled_at.isoformat(),
                "CompileManifest_v1",
                json.dumps(payload, sort_keys=True),
            ),
        )

    def save_compiled_execution_package(
        self,
        connection: sqlite3.Connection,
        execution_package: CompiledExecutionPackage,
        *,
        compiled_at: datetime,
    ) -> None:
        payload = execution_package.model_dump(mode="json")
        connection.execute(
            """
            INSERT INTO compiled_execution_package (
                compile_request_id,
                ticket_id,
                workflow_id,
                node_id,
                compiler_version,
                compiled_at,
                package_version,
                payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                execution_package.meta.compile_request_id,
                execution_package.meta.ticket_id,
                execution_package.meta.workflow_id,
                execution_package.meta.node_id,
                execution_package.meta.compiler_version,
                compiled_at.isoformat(),
                "CompiledExecutionPackage_v1",
                json.dumps(payload, sort_keys=True),
            ),
        )

    def get_compiled_context_bundle(
        self,
        bundle_id: str,
        connection: sqlite3.Connection | None = None,
    ) -> dict[str, Any] | None:
        if connection is not None:
            row = connection.execute(
                "SELECT * FROM compiled_context_bundle WHERE bundle_id = ?",
                (bundle_id,),
            ).fetchone()
            if row is None:
                return None
            return self._convert_compiled_context_bundle_row(row)

        self.initialize()
        with self.connection() as owned_connection:
            row = owned_connection.execute(
                "SELECT * FROM compiled_context_bundle WHERE bundle_id = ?",
                (bundle_id,),
            ).fetchone()
            if row is None:
                return None
            return self._convert_compiled_context_bundle_row(row)

    def get_latest_compiled_context_bundle_by_ticket(
        self,
        ticket_id: str,
        connection: sqlite3.Connection | None = None,
    ) -> dict[str, Any] | None:
        query = """
            SELECT * FROM compiled_context_bundle
            WHERE ticket_id = ?
            ORDER BY compiled_at DESC, bundle_id DESC
            LIMIT 1
        """
        if connection is not None:
            row = connection.execute(query, (ticket_id,)).fetchone()
            if row is None:
                return None
            return self._convert_compiled_context_bundle_row(row)

        self.initialize()
        with self.connection() as owned_connection:
            row = owned_connection.execute(query, (ticket_id,)).fetchone()
            if row is None:
                return None
            return self._convert_compiled_context_bundle_row(row)

    def get_compile_manifest(
        self,
        compile_id: str,
        connection: sqlite3.Connection | None = None,
    ) -> dict[str, Any] | None:
        if connection is not None:
            row = connection.execute(
                "SELECT * FROM compile_manifest WHERE compile_id = ?",
                (compile_id,),
            ).fetchone()
            if row is None:
                return None
            return self._convert_compile_manifest_row(row)

        self.initialize()
        with self.connection() as owned_connection:
            row = owned_connection.execute(
                "SELECT * FROM compile_manifest WHERE compile_id = ?",
                (compile_id,),
            ).fetchone()
            if row is None:
                return None
            return self._convert_compile_manifest_row(row)

    def get_compiled_execution_package(
        self,
        compile_request_id: str,
        connection: sqlite3.Connection | None = None,
    ) -> dict[str, Any] | None:
        if connection is not None:
            row = connection.execute(
                "SELECT * FROM compiled_execution_package WHERE compile_request_id = ?",
                (compile_request_id,),
            ).fetchone()
            if row is None:
                return None
            return self._convert_compiled_execution_package_row(row)

        self.initialize()
        with self.connection() as owned_connection:
            row = owned_connection.execute(
                "SELECT * FROM compiled_execution_package WHERE compile_request_id = ?",
                (compile_request_id,),
            ).fetchone()
            if row is None:
                return None
            return self._convert_compiled_execution_package_row(row)

    def get_latest_compile_manifest_by_ticket(
        self,
        ticket_id: str,
        connection: sqlite3.Connection | None = None,
    ) -> dict[str, Any] | None:
        query = """
            SELECT * FROM compile_manifest
            WHERE ticket_id = ?
            ORDER BY compiled_at DESC, compile_id DESC
            LIMIT 1
        """
        if connection is not None:
            row = connection.execute(query, (ticket_id,)).fetchone()
            if row is None:
                return None
            return self._convert_compile_manifest_row(row)

        self.initialize()
        with self.connection() as owned_connection:
            row = owned_connection.execute(query, (ticket_id,)).fetchone()
            if row is None:
                return None
            return self._convert_compile_manifest_row(row)

    def get_latest_compiled_execution_package_by_ticket(
        self,
        ticket_id: str,
        connection: sqlite3.Connection | None = None,
    ) -> dict[str, Any] | None:
        query = """
            SELECT * FROM compiled_execution_package
            WHERE ticket_id = ?
            ORDER BY compiled_at DESC, compile_request_id DESC
            LIMIT 1
        """
        if connection is not None:
            row = connection.execute(query, (ticket_id,)).fetchone()
            if row is None:
                return None
            return self._convert_compiled_execution_package_row(row)

        self.initialize()
        with self.connection() as owned_connection:
            row = owned_connection.execute(query, (ticket_id,)).fetchone()
            if row is None:
                return None
            return self._convert_compiled_execution_package_row(row)

    def get_cursor_and_version(self) -> tuple[str | None, int]:
        self.initialize()
        with self.connection() as connection:
            row = connection.execute(
                """
                SELECT event_id, sequence_no
                FROM events
                ORDER BY sequence_no DESC
                LIMIT 1
                """
            ).fetchone()
            if row is None:
                return None, 0
            return row["event_id"], int(row["sequence_no"])

    def save_artifact_record(
        self,
        connection: sqlite3.Connection,
        *,
        artifact_ref: str,
        workflow_id: str,
        ticket_id: str,
        node_id: str,
        logical_path: str,
        kind: str,
        media_type: str | None,
        materialization_status: str,
        lifecycle_status: str,
        storage_relpath: str | None,
        content_hash: str | None,
        size_bytes: int | None,
        retention_class: str,
        expires_at: datetime | None,
        deleted_at: datetime | None,
        deleted_by: str | None,
        delete_reason: str | None,
        created_at: datetime,
        retention_class_source: str | None = None,
        retention_ttl_sec: int | None = None,
        retention_policy_source: str | None = None,
        storage_backend: str = "LOCAL_FILE",
        storage_object_key: str | None = None,
        storage_delete_status: str | None = "PRESENT",
        storage_delete_error: str | None = None,
        storage_deleted_at: datetime | None = None,
    ) -> None:
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
                storage_backend,
                storage_object_key,
                storage_delete_status,
                storage_delete_error,
                expires_at,
                deleted_at,
                deleted_by,
                delete_reason,
                storage_deleted_at,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
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
                storage_backend,
                storage_object_key,
                storage_delete_status,
                storage_delete_error,
                expires_at.isoformat() if expires_at is not None else None,
                deleted_at.isoformat() if deleted_at is not None else None,
                deleted_by,
                delete_reason,
                storage_deleted_at.isoformat() if storage_deleted_at is not None else None,
                created_at.isoformat(),
            ),
        )

    def create_artifact_upload_session(
        self,
        connection: sqlite3.Connection,
        *,
        session_id: str,
        created_at: datetime,
        created_by: str,
        filename: str | None,
        media_type: str | None,
    ) -> None:
        connection.execute(
            """
            INSERT INTO artifact_upload_session (
                session_id,
                status,
                filename,
                media_type,
                assembled_staging_relpath,
                size_bytes,
                content_hash,
                part_count,
                created_at,
                updated_at,
                completed_at,
                aborted_at,
                consumed_at,
                created_by,
                consumed_by_artifact_ref
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                "INITIATED",
                filename,
                media_type,
                None,
                None,
                None,
                0,
                created_at.isoformat(),
                created_at.isoformat(),
                None,
                None,
                None,
                created_by,
                None,
            ),
        )

    def save_artifact_upload_part(
        self,
        connection: sqlite3.Connection,
        *,
        session_id: str,
        part_number: int,
        staging_relpath: str,
        size_bytes: int,
        content_hash: str,
        uploaded_at: datetime,
    ) -> None:
        connection.execute(
            """
            INSERT INTO artifact_upload_part (
                session_id,
                part_number,
                staging_relpath,
                size_bytes,
                content_hash,
                uploaded_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(session_id, part_number) DO UPDATE SET
                staging_relpath = excluded.staging_relpath,
                size_bytes = excluded.size_bytes,
                content_hash = excluded.content_hash,
                uploaded_at = excluded.uploaded_at
            """,
            (
                session_id,
                part_number,
                staging_relpath,
                size_bytes,
                content_hash,
                uploaded_at.isoformat(),
            ),
        )
        connection.execute(
            """
            UPDATE artifact_upload_session
            SET status = CASE
                    WHEN status = 'INITIATED' THEN 'UPLOADING'
                    ELSE status
                END,
                updated_at = ?
            WHERE session_id = ?
            """,
            (
                uploaded_at.isoformat(),
                session_id,
            ),
        )

    def complete_artifact_upload_session(
        self,
        connection: sqlite3.Connection,
        *,
        session_id: str,
        completed_at: datetime,
        assembled_staging_relpath: str,
        size_bytes: int,
        content_hash: str,
        part_count: int,
    ) -> None:
        connection.execute(
            """
            UPDATE artifact_upload_session
            SET status = 'COMPLETED',
                assembled_staging_relpath = ?,
                size_bytes = ?,
                content_hash = ?,
                part_count = ?,
                completed_at = ?,
                updated_at = ?
            WHERE session_id = ?
            """,
            (
                assembled_staging_relpath,
                size_bytes,
                content_hash,
                part_count,
                completed_at.isoformat(),
                completed_at.isoformat(),
                session_id,
            ),
        )

    def consume_artifact_upload_session(
        self,
        connection: sqlite3.Connection,
        *,
        session_id: str,
        consumed_at: datetime,
        consumed_by_artifact_ref: str,
    ) -> bool:
        cursor = connection.execute(
            """
            UPDATE artifact_upload_session
            SET status = 'CONSUMED',
                consumed_at = ?,
                updated_at = ?,
                consumed_by_artifact_ref = ?
            WHERE session_id = ?
              AND status = 'COMPLETED'
              AND (
                    consumed_by_artifact_ref IS NULL
                    OR TRIM(consumed_by_artifact_ref) = ''
                  )
            """,
            (
                consumed_at.isoformat(),
                consumed_at.isoformat(),
                consumed_by_artifact_ref,
                session_id,
            ),
        )
        return cursor.rowcount > 0

    def abort_artifact_upload_session(
        self,
        connection: sqlite3.Connection,
        *,
        session_id: str,
        aborted_at: datetime,
    ) -> None:
        connection.execute(
            """
            UPDATE artifact_upload_session
            SET status = 'ABORTED',
                aborted_at = ?,
                updated_at = ?
            WHERE session_id = ?
              AND status != 'CONSUMED'
            """,
            (
                aborted_at.isoformat(),
                aborted_at.isoformat(),
                session_id,
            ),
        )

    def get_artifact_upload_session(
        self,
        session_id: str,
        connection: sqlite3.Connection | None = None,
    ) -> dict[str, Any] | None:
        query = "SELECT * FROM artifact_upload_session WHERE session_id = ?"
        if connection is not None:
            row = connection.execute(query, (session_id,)).fetchone()
            if row is None:
                return None
            return self._convert_artifact_upload_session_row(row)

        self.initialize()
        with self.connection() as owned_connection:
            row = owned_connection.execute(query, (session_id,)).fetchone()
            if row is None:
                return None
            return self._convert_artifact_upload_session_row(row)

    def list_artifact_upload_parts(
        self,
        session_id: str,
        connection: sqlite3.Connection | None = None,
    ) -> list[dict[str, Any]]:
        query = """
            SELECT * FROM artifact_upload_part
            WHERE session_id = ?
            ORDER BY part_number ASC
        """
        if connection is not None:
            rows = connection.execute(query, (session_id,)).fetchall()
            return [self._convert_artifact_upload_part_row(row) for row in rows]

        self.initialize()
        with self.connection() as owned_connection:
            rows = owned_connection.execute(query, (session_id,)).fetchall()
            return [self._convert_artifact_upload_part_row(row) for row in rows]

    def get_artifact_by_ref(
        self,
        artifact_ref: str,
        connection: sqlite3.Connection | None = None,
    ) -> dict[str, Any] | None:
        if connection is not None:
            row = connection.execute(
                "SELECT * FROM artifact_index WHERE artifact_ref = ?",
                (artifact_ref,),
            ).fetchone()
            if row is None:
                return None
            return self._convert_artifact_index_row(row)

        self.initialize()
        with self.connection() as owned_connection:
            row = owned_connection.execute(
                "SELECT * FROM artifact_index WHERE artifact_ref = ?",
                (artifact_ref,),
            ).fetchone()
            if row is None:
                return None
            return self._convert_artifact_index_row(row)

    def list_ticket_artifacts(
        self,
        ticket_id: str,
        connection: sqlite3.Connection | None = None,
    ) -> list[dict[str, Any]]:
        query = """
            SELECT * FROM artifact_index
            WHERE ticket_id = ?
            ORDER BY created_at ASC, artifact_ref ASC
        """
        if connection is not None:
            rows = connection.execute(query, (ticket_id,)).fetchall()
            return [self._convert_artifact_index_row(row) for row in rows]

        self.initialize()
        with self.connection() as owned_connection:
            rows = owned_connection.execute(query, (ticket_id,)).fetchall()
            return [self._convert_artifact_index_row(row) for row in rows]

    def list_retrieval_review_summary_candidates(
        self,
        *,
        tenant_id: str,
        workspace_id: str,
        exclude_workflow_id: str,
        normalized_terms: list[str],
        limit: int,
    ) -> list[dict[str, Any]]:
        self.initialize()
        query = """
            SELECT approval_projection.*
            FROM approval_projection
            LEFT JOIN workflow_projection
              ON workflow_projection.workflow_id = approval_projection.workflow_id
            WHERE approval_projection.workflow_id != ?
              AND approval_projection.status != ?
              AND COALESCE(workflow_projection.tenant_id, ?) = ?
              AND COALESCE(workflow_projection.workspace_id, ?) = ?
            ORDER BY approval_projection.updated_at DESC, approval_projection.approval_id DESC
            LIMIT 24
        """
        with self.connection() as connection:
            rows = connection.execute(
                query,
                (
                    exclude_workflow_id,
                    APPROVAL_STATUS_OPEN,
                    DEFAULT_TENANT_ID,
                    tenant_id,
                    DEFAULT_WORKSPACE_ID,
                    workspace_id,
                ),
            ).fetchall()

        candidates: list[dict[str, Any]] = []
        for row in rows:
            converted = self._convert_approval_row(row)
            payload = converted["payload"]
            review_pack = payload.get("review_pack") or {}
            subject = review_pack.get("subject") or {}
            recommendation = review_pack.get("recommendation") or {}
            resolution = payload.get("resolution") or {}
            matched_terms = self._matched_retrieval_terms(
                normalized_terms,
                [
                    subject.get("title"),
                    recommendation.get("summary"),
                    payload.get("inbox_title"),
                    payload.get("inbox_summary"),
                    resolution.get("board_comment"),
                ],
            )
            if not matched_terms:
                continue
            candidates.append(
                {
                    "channel": "review_summaries",
                    "source_ref": converted["review_pack_id"],
                    "source_workflow_id": converted["workflow_id"],
                    "source_ticket_id": subject.get("source_ticket_id"),
                    "review_pack_id": converted["review_pack_id"],
                    "headline": str(subject.get("title") or payload.get("inbox_title") or converted["review_pack_id"]),
                    "summary": str(
                        recommendation.get("summary")
                        or payload.get("inbox_summary")
                        or resolution.get("board_comment")
                        or "Historical review summary."
                    ),
                    "matched_terms": matched_terms,
                    "why_it_matched": (
                        "Matched "
                        + ", ".join(matched_terms)
                        + " in a historical review summary from the same local workspace."
                    ),
                    "updated_at": converted.get("updated_at"),
                }
            )

        return self._sort_retrieval_candidates(candidates)[:limit]

    def list_retrieval_incident_summary_candidates(
        self,
        *,
        tenant_id: str,
        workspace_id: str,
        exclude_workflow_id: str,
        normalized_terms: list[str],
        limit: int,
    ) -> list[dict[str, Any]]:
        self.initialize()
        query = """
            SELECT incident_projection.*
            FROM incident_projection
            LEFT JOIN workflow_projection
              ON workflow_projection.workflow_id = incident_projection.workflow_id
            WHERE incident_projection.workflow_id != ?
              AND COALESCE(workflow_projection.tenant_id, ?) = ?
              AND COALESCE(workflow_projection.workspace_id, ?) = ?
            ORDER BY incident_projection.updated_at DESC, incident_projection.incident_id DESC
            LIMIT 24
        """
        with self.connection() as connection:
            rows = connection.execute(
                query,
                (
                    exclude_workflow_id,
                    DEFAULT_TENANT_ID,
                    tenant_id,
                    DEFAULT_WORKSPACE_ID,
                    workspace_id,
                ),
            ).fetchall()

        candidates: list[dict[str, Any]] = []
        for row in rows:
            converted = self._convert_incident_projection_row(row)
            payload = converted["payload"]
            matched_terms = self._matched_retrieval_terms(
                normalized_terms,
                [
                    payload.get("headline"),
                    payload.get("summary"),
                    converted.get("incident_type"),
                    converted.get("fingerprint"),
                ],
            )
            if not matched_terms:
                continue
            candidates.append(
                {
                    "channel": "incident_summaries",
                    "source_ref": converted["incident_id"],
                    "source_workflow_id": converted["workflow_id"],
                    "source_ticket_id": converted.get("ticket_id"),
                    "incident_id": converted["incident_id"],
                    "headline": str(payload.get("headline") or converted.get("incident_type") or converted["incident_id"]),
                    "summary": str(payload.get("summary") or "Historical incident summary."),
                    "matched_terms": matched_terms,
                    "why_it_matched": (
                        "Matched "
                        + ", ".join(matched_terms)
                        + " in a historical incident summary from the same local workspace."
                    ),
                    "updated_at": converted.get("updated_at"),
                }
            )

        return self._sort_retrieval_candidates(candidates)[:limit]

    def list_retrieval_artifact_summary_candidates(
        self,
        *,
        tenant_id: str,
        workspace_id: str,
        exclude_workflow_id: str,
        normalized_terms: list[str],
        limit: int,
    ) -> list[dict[str, Any]]:
        self.initialize()
        query = """
            SELECT artifact_index.*
            FROM artifact_index
            LEFT JOIN workflow_projection
              ON workflow_projection.workflow_id = artifact_index.workflow_id
            WHERE artifact_index.workflow_id != ?
              AND artifact_index.lifecycle_status = 'ACTIVE'
              AND artifact_index.materialization_status = 'MATERIALIZED'
              AND artifact_index.kind IN ('TEXT', 'MARKDOWN', 'JSON')
              AND COALESCE(workflow_projection.tenant_id, ?) = ?
              AND COALESCE(workflow_projection.workspace_id, ?) = ?
            ORDER BY artifact_index.created_at DESC, artifact_index.artifact_ref DESC
            LIMIT 24
        """
        with self.connection() as connection:
            rows = connection.execute(
                query,
                (
                    exclude_workflow_id,
                    DEFAULT_TENANT_ID,
                    tenant_id,
                    DEFAULT_WORKSPACE_ID,
                    workspace_id,
                ),
            ).fetchall()

        candidates: list[dict[str, Any]] = []
        for row in rows:
            converted = self._convert_artifact_index_row(row)
            coarse_matched_terms = self._matched_retrieval_terms(
                normalized_terms,
                [
                    converted.get("path"),
                    converted.get("kind"),
                    converted.get("media_type"),
                ],
            )
            if not coarse_matched_terms:
                continue
            artifact_body = self._read_retrieval_artifact_body(converted)
            if artifact_body is None:
                continue
            matched_terms = self._matched_retrieval_terms(
                normalized_terms,
                [
                    converted.get("path"),
                    artifact_body,
                ],
            )
            if not matched_terms:
                continue
            access = build_artifact_access_descriptor(
                converted,
                artifact_ref=str(converted["artifact_ref"]),
            )
            candidates.append(
                {
                    "channel": "artifact_summaries",
                    "source_ref": converted["artifact_ref"],
                    "source_workflow_id": converted["workflow_id"],
                    "source_ticket_id": converted.get("ticket_id"),
                    "artifact_ref": converted["artifact_ref"],
                    "preview_url": access.get("preview_url"),
                    "headline": str(converted.get("path") or converted["artifact_ref"]),
                    "summary": self._summarize_retrieval_text(artifact_body),
                    "matched_terms": matched_terms,
                    "why_it_matched": (
                        "Matched "
                        + ", ".join(matched_terms)
                        + " in a historical artifact from the same local workspace."
                    ),
                    "updated_at": converted.get("created_at"),
                }
            )

        return self._sort_retrieval_candidates(candidates)[:limit]

    def list_artifacts_for_cleanup(
        self,
        connection: sqlite3.Connection,
        *,
        expires_before: datetime,
    ) -> list[dict[str, Any]]:
        rows = connection.execute(
            """
            SELECT * FROM artifact_index
            WHERE (lifecycle_status = 'ACTIVE' AND expires_at IS NOT NULL AND expires_at <= ?)
               OR (
                    lifecycle_status IN ('DELETED', 'EXPIRED')
                    AND (
                        storage_delete_status IN ('PRESENT', 'DELETE_PENDING', 'DELETE_FAILED')
                        OR (
                            (storage_delete_status IS NULL OR TRIM(storage_delete_status) = '')
                            AND (
                                (
                                    (storage_relpath IS NOT NULL AND TRIM(storage_relpath) != '')
                                    OR (storage_object_key IS NOT NULL AND TRIM(storage_object_key) != '')
                                )
                                AND storage_deleted_at IS NULL
                            )
                        )
                    )
               )
            ORDER BY created_at ASC, artifact_ref ASC
            """,
            (expires_before.isoformat(),),
        ).fetchall()
        return [self._convert_artifact_index_row(row) for row in rows]

    def list_artifact_cleanup_candidates(
        self,
        *,
        at: datetime,
        ticket_id: str | None = None,
        retention_class: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        self.initialize()
        clauses = [
            """(
                    (lifecycle_status = 'ACTIVE' AND expires_at IS NOT NULL AND expires_at <= ?)
                    OR (
                        lifecycle_status IN ('DELETED', 'EXPIRED')
                        AND (
                            storage_delete_status IN ('PRESENT', 'DELETE_PENDING', 'DELETE_FAILED')
                            OR (
                                (storage_delete_status IS NULL OR TRIM(storage_delete_status) = '')
                                AND (
                                    (
                                        (storage_relpath IS NOT NULL AND TRIM(storage_relpath) != '')
                                        OR (storage_object_key IS NOT NULL AND TRIM(storage_object_key) != '')
                                    )
                                    AND storage_deleted_at IS NULL
                                )
                            )
                        )
                    )
                )"""
        ]
        params: list[Any] = [at.isoformat()]
        if ticket_id is not None:
            clauses.append("ticket_id = ?")
            params.append(ticket_id)
        if retention_class is not None:
            clauses.append("retention_class = ?")
            params.append(retention_class)
        params.append(limit)
        query = f"""
            SELECT * FROM artifact_index
            WHERE {' AND '.join(clauses)}
            ORDER BY created_at ASC, artifact_ref ASC
            LIMIT ?
        """
        with self.connection() as connection:
            rows = connection.execute(query, params).fetchall()
        return [self._convert_artifact_index_row(row) for row in rows]

    def mark_artifact_storage_deleted(
        self,
        connection: sqlite3.Connection,
        *,
        artifact_ref: str,
        storage_deleted_at: datetime,
    ) -> None:
        connection.execute(
            """
            UPDATE artifact_index
            SET storage_deleted_at = ?,
                storage_delete_status = 'DELETED',
                storage_delete_error = NULL
            WHERE artifact_ref = ?
            """,
            (
                storage_deleted_at.isoformat(),
                artifact_ref,
            ),
        )

    def mark_artifact_storage_delete_pending(
        self,
        connection: sqlite3.Connection,
        *,
        artifact_ref: str,
    ) -> None:
        connection.execute(
            """
            UPDATE artifact_index
            SET storage_delete_status = 'DELETE_PENDING',
                storage_delete_error = NULL
            WHERE artifact_ref = ?
            """,
            (artifact_ref,),
        )

    def mark_artifact_storage_delete_failed(
        self,
        connection: sqlite3.Connection,
        *,
        artifact_ref: str,
        error_message: str,
    ) -> None:
        connection.execute(
            """
            UPDATE artifact_index
            SET storage_delete_status = 'DELETE_FAILED',
                storage_delete_error = ?
            WHERE artifact_ref = ?
            """,
            (
                error_message,
                artifact_ref,
            ),
        )

    def update_artifact_lifecycle(
        self,
        connection: sqlite3.Connection,
        *,
        artifact_ref: str,
        lifecycle_status: str,
        deleted_at: datetime | None,
        deleted_by: str | None,
        delete_reason: str | None,
    ) -> None:
        connection.execute(
            """
            UPDATE artifact_index
            SET lifecycle_status = ?,
                deleted_at = ?,
                deleted_by = ?,
                delete_reason = ?
            WHERE artifact_ref = ?
            """,
            (
                lifecycle_status,
                deleted_at.isoformat() if deleted_at is not None else None,
                deleted_by,
                delete_reason,
                artifact_ref,
            ),
        )

    def get_recent_event_previews(self) -> list[dict[str, Any]]:
        self.initialize()
        with self.connection() as connection:
            rows = connection.execute(
                """
                SELECT * FROM events
                ORDER BY sequence_no DESC
                LIMIT ?
                """,
                (self.recent_event_limit,),
            ).fetchall()

        previews = []
        for row in rows:
            converted = self._convert_event_row(row)
            previews.append(
                {
                    "event_id": converted["event_id"],
                    "occurred_at": converted["occurred_at"],
                    "category": self._event_category(converted["event_type"]),
                    "severity": self._event_severity(converted["event_type"]),
                    "message": self._event_preview_message(converted),
                    "related_ref": (
                        converted.get("artifact_ref")
                        or converted.get("incident_id")
                        or converted.get("ticket_id")
                        or converted.get("workflow_id")
                        or converted["event_id"]
                    ),
                }
            )
        return previews

    def list_stream_events(self, after: str | None = None) -> list[dict[str, Any]]:
        self.initialize()
        with self.connection() as connection:
            if after is None:
                rows = connection.execute(
                    "SELECT * FROM events ORDER BY sequence_no ASC"
                ).fetchall()
            else:
                cursor_row = connection.execute(
                    "SELECT sequence_no FROM events WHERE event_id = ?",
                    (after,),
                ).fetchone()
                if cursor_row is None:
                    rows = connection.execute(
                        "SELECT * FROM events ORDER BY sequence_no ASC"
                    ).fetchall()
                else:
                    rows = connection.execute(
                        """
                        SELECT * FROM events
                        WHERE sequence_no > ?
                        ORDER BY sequence_no ASC
                        """,
                        (cursor_row["sequence_no"],),
                    ).fetchall()

        stream_events = []
        for row in rows:
            converted = self._convert_event_row(row)
            stream_events.append(
                {
                    "event_id": converted["event_id"],
                    "occurred_at": converted["occurred_at"],
                    "category": self._event_category(converted["event_type"]),
                    "severity": self._event_severity(converted["event_type"]),
                    "event_type": converted["event_type"],
                    "workflow_id": converted["workflow_id"],
                    "node_id": converted.get("node_id"),
                    "ticket_id": converted.get("ticket_id"),
                    "causation_id": converted["causation_id"],
                    "projection_version_hint": converted["sequence_no"],
                    "ui_hint": self._event_ui_hint(converted["event_type"]),
                }
            )
        return stream_events

    def count_events_by_type(self, event_type: str) -> int:
        self.initialize()
        with self.connection() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS total FROM events WHERE event_type = ?",
                (event_type,),
            ).fetchone()
            return int(row["total"])

    def get_artifact_cleanup_summary(
        self,
        *,
        at: datetime,
    ) -> dict[str, Any]:
        self.initialize()
        with self.connection() as connection:
            pending_expired_row = connection.execute(
                """
                SELECT COUNT(*) AS total
                FROM artifact_index
                WHERE lifecycle_status = 'ACTIVE'
                  AND expires_at IS NOT NULL
                  AND expires_at <= ?
                """,
                (at.isoformat(),),
            ).fetchone()
            pending_storage_row = connection.execute(
                """
                SELECT COUNT(*) AS total
                FROM artifact_index
                WHERE lifecycle_status IN ('DELETED', 'EXPIRED')
                  AND (
                        storage_delete_status IN ('PRESENT', 'DELETE_PENDING', 'DELETE_FAILED')
                        OR (
                            (storage_delete_status IS NULL OR TRIM(storage_delete_status) = '')
                            AND (
                                (
                                    (storage_relpath IS NOT NULL AND TRIM(storage_relpath) != '')
                                    OR (storage_object_key IS NOT NULL AND TRIM(storage_object_key) != '')
                                )
                                AND storage_deleted_at IS NULL
                            )
                        )
                  )
                """,
            ).fetchone()
            delete_failed_row = connection.execute(
                """
                SELECT COUNT(*) AS total
                FROM artifact_index
                WHERE storage_delete_status = 'DELETE_FAILED'
                """,
            ).fetchone()
            legacy_unknown_row = connection.execute(
                """
                SELECT COUNT(*) AS total
                FROM artifact_index
                WHERE retention_policy_source = ?
                """,
                (ARTIFACT_RETENTION_POLICY_LEGACY_UNKNOWN,),
            ).fetchone()
            latest_cleanup_row = connection.execute(
                """
                SELECT * FROM events
                WHERE event_type = ?
                ORDER BY sequence_no DESC
                LIMIT 1
                """,
                (EVENT_ARTIFACT_CLEANUP_COMPLETED,),
            ).fetchone()

        latest_cleanup_event = (
            self._convert_event_row(latest_cleanup_row) if latest_cleanup_row is not None else None
        )
        return {
            "pending_expired_count": int(pending_expired_row["total"]),
            "pending_storage_cleanup_count": int(pending_storage_row["total"]),
            "delete_failed_count": int(delete_failed_row["total"]),
            "legacy_unknown_retention_count": int(legacy_unknown_row["total"]),
            "latest_cleanup_event": latest_cleanup_event,
        }

    def count_open_approvals(self) -> int:
        self.initialize()
        with self.connection() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS total FROM approval_projection WHERE status = ?",
                (APPROVAL_STATUS_OPEN,),
            ).fetchone()
            return int(row["total"])

    def count_open_incidents(self) -> int:
        self.initialize()
        with self.connection() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS total FROM incident_projection WHERE status = ?",
                ("OPEN",),
            ).fetchone()
            return int(row["total"])

    def count_open_circuit_breakers(self) -> int:
        self.initialize()
        with self.connection() as connection:
            row = connection.execute(
                """
                SELECT COUNT(*) AS total
                FROM incident_projection
                WHERE status = ? AND circuit_breaker_state = ?
                """,
                ("OPEN", CIRCUIT_BREAKER_STATE_OPEN),
            ).fetchone()
            return int(row["total"])

    def count_open_provider_incidents(self) -> int:
        self.initialize()
        with self.connection() as connection:
            row = connection.execute(
                """
                SELECT COUNT(*) AS total
                FROM incident_projection
                WHERE status = ? AND provider_id IS NOT NULL
                """,
                ("OPEN",),
            ).fetchone()
            return int(row["total"])

    def list_open_incidents(self) -> list[dict[str, Any]]:
        self.initialize()
        with self.connection() as connection:
            rows = connection.execute(
                """
                SELECT * FROM incident_projection
                WHERE status = ?
                ORDER BY opened_at DESC, incident_id DESC
                """,
                ("OPEN",),
            ).fetchall()
            return [self._convert_incident_projection_row(row) for row in rows]

    def list_open_provider_incidents(self) -> list[dict[str, Any]]:
        self.initialize()
        with self.connection() as connection:
            rows = connection.execute(
                """
                SELECT * FROM incident_projection
                WHERE status = ? AND provider_id IS NOT NULL
                ORDER BY opened_at DESC, incident_id DESC
                """,
                ("OPEN",),
            ).fetchall()
            return [self._convert_incident_projection_row(row) for row in rows]

    def has_open_circuit_breaker_for_node(
        self,
        workflow_id: str,
        node_id: str,
        connection: sqlite3.Connection | None = None,
    ) -> bool:
        query = """
            SELECT 1
            FROM incident_projection
            WHERE workflow_id = ? AND node_id = ? AND status = ? AND circuit_breaker_state = ?
            LIMIT 1
        """
        params = (workflow_id, node_id, "OPEN", CIRCUIT_BREAKER_STATE_OPEN)
        if connection is not None:
            row = connection.execute(query, params).fetchone()
            return row is not None

        self.initialize()
        with self.connection() as owned_connection:
            row = owned_connection.execute(query, params).fetchone()
            return row is not None

    def has_open_circuit_breaker_for_provider(
        self,
        provider_id: str,
        connection: sqlite3.Connection | None = None,
    ) -> bool:
        query = """
            SELECT 1
            FROM incident_projection
            WHERE provider_id = ? AND status = ? AND circuit_breaker_state = ?
            LIMIT 1
        """
        params = (provider_id, "OPEN", CIRCUIT_BREAKER_STATE_OPEN)
        if connection is not None:
            row = connection.execute(query, params).fetchone()
            return row is not None

        self.initialize()
        with self.connection() as owned_connection:
            row = owned_connection.execute(query, params).fetchone()
            return row is not None

    def count_active_tickets(self) -> int:
        self.initialize()
        with self.connection() as connection:
            row = connection.execute(
                """
                SELECT COUNT(*) AS total
                FROM node_projection
                WHERE status NOT IN (?, ?)
                """,
                (NODE_STATUS_COMPLETED, NODE_STATUS_CANCELLED),
            ).fetchone()
            return int(row["total"])

    def count_blocked_nodes(self) -> int:
        self.initialize()
        with self.connection() as connection:
            row = connection.execute(
                """
                SELECT COUNT(*) AS total
                FROM node_projection
                WHERE status = ?
                """,
                (NODE_STATUS_BLOCKED_FOR_BOARD_REVIEW,),
            ).fetchone()
            return int(row["total"])

    def list_blocked_node_ids(self) -> list[str]:
        self.initialize()
        with self.connection() as connection:
            rows = connection.execute(
                """
                SELECT node_id
                FROM node_projection
                WHERE status = ?
                ORDER BY node_id ASC
                """,
                (NODE_STATUS_BLOCKED_FOR_BOARD_REVIEW,),
            ).fetchall()
            return [str(row["node_id"]) for row in rows]

    def list_open_approvals(self) -> list[dict[str, Any]]:
        self.initialize()
        with self.connection() as connection:
            rows = connection.execute(
                """
                SELECT * FROM approval_projection
                WHERE status = ?
                ORDER BY created_at DESC, approval_id DESC
                """,
                (APPROVAL_STATUS_OPEN,),
            ).fetchall()
            return [self._convert_approval_row(row) for row in rows]

    def get_approval_by_review_pack_id(self, review_pack_id: str) -> dict[str, Any] | None:
        self.initialize()
        with self.connection() as connection:
            row = connection.execute(
                "SELECT * FROM approval_projection WHERE review_pack_id = ?",
                (review_pack_id,),
            ).fetchone()
            if row is None:
                return None
            return self._convert_approval_row(row)

    def get_approval_by_id(
        self,
        connection: sqlite3.Connection,
        approval_id: str,
    ) -> dict[str, Any] | None:
        row = connection.execute(
            "SELECT * FROM approval_projection WHERE approval_id = ?",
            (approval_id,),
        ).fetchone()
        if row is None:
            return None
        return self._convert_approval_row(row)

    def create_approval_request(
        self,
        connection: sqlite3.Connection,
        *,
        workflow_id: str,
        approval_type: str,
        requested_by: str,
        review_pack: dict[str, Any],
        available_actions: list[str],
        draft_defaults: dict[str, Any],
        inbox_title: str,
        inbox_summary: str,
        badges: list[str],
        priority: str,
        occurred_at: datetime,
        idempotency_key: str,
    ) -> dict[str, Any]:
        review_pack_payload = deepcopy(review_pack)
        approval_id = review_pack_payload.setdefault("meta", {}).setdefault(
            "approval_id",
            new_prefixed_id("apr"),
        )
        review_pack_id = review_pack_payload["meta"].setdefault(
            "review_pack_id",
            new_prefixed_id("brp"),
        )
        review_pack_version = int(review_pack_payload["meta"].setdefault("review_pack_version", 1))

        event_row = self.insert_event(
            connection,
            event_type=EVENT_BOARD_REVIEW_REQUIRED,
            actor_type="system",
            actor_id=requested_by,
            workflow_id=workflow_id,
            idempotency_key=idempotency_key,
            causation_id=None,
            correlation_id=workflow_id,
            payload={
                "approval_id": approval_id,
                "review_pack_id": review_pack_id,
                "review_type": approval_type,
                "title": inbox_title,
                "node_id": review_pack_payload.get("subject", {}).get("source_node_id"),
                "ticket_id": review_pack_payload.get("subject", {}).get("source_ticket_id"),
            },
            occurred_at=occurred_at,
        )
        if event_row is None:
            existing = self.get_approval_by_id(connection, approval_id)
            if existing is None:
                raise RuntimeError("Approval request idempotency conflict without existing approval row.")
            return existing

        command_target_version = int(event_row["sequence_no"])
        review_pack_payload["meta"]["source_projection_version"] = command_target_version
        decision_form = review_pack_payload.get("decision_form")
        if isinstance(decision_form, dict):
            decision_form["command_target_version"] = command_target_version
        payload = {
            "review_pack": review_pack_payload,
            "available_actions": available_actions,
            "draft_defaults": draft_defaults,
            "inbox_title": inbox_title,
            "inbox_summary": inbox_summary,
            "badges": badges,
            "priority": priority,
        }

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
                approval_id,
                review_pack_id,
                workflow_id,
                approval_type,
                APPROVAL_STATUS_OPEN,
                requested_by,
                None,
                None,
                occurred_at.isoformat(),
                occurred_at.isoformat(),
                review_pack_version,
                command_target_version,
                json.dumps(payload, sort_keys=True),
            ),
        )
        created = self.get_approval_by_id(connection, approval_id)
        if created is None:
            raise RuntimeError("Approval row was not persisted.")
        return created

    def resolve_approval(
        self,
        connection: sqlite3.Connection,
        *,
        approval_id: str,
        status: str,
        resolved_by: str,
        resolved_at: datetime,
        review_pack_version: int,
        command_target_version: int,
        resolution: dict[str, Any],
    ) -> dict[str, Any]:
        approval = self.get_approval_by_id(connection, approval_id)
        if approval is None:
            raise RuntimeError("Approval not found.")

        payload = deepcopy(approval["payload"])
        payload["resolution"] = resolution
        connection.execute(
            """
            UPDATE approval_projection
            SET status = ?,
                resolved_by = ?,
                resolved_at = ?,
                updated_at = ?,
                review_pack_version = ?,
                command_target_version = ?,
                payload_json = ?
            WHERE approval_id = ?
            """,
            (
                status,
                resolved_by,
                resolved_at.isoformat(),
                resolved_at.isoformat(),
                review_pack_version,
                command_target_version,
                json.dumps(payload, sort_keys=True),
                approval_id,
            ),
        )
        updated = self.get_approval_by_id(connection, approval_id)
        if updated is None:
            raise RuntimeError("Approval disappeared after resolution.")
        return updated

    def list_events_for_testing(self) -> list[dict[str, Any]]:
        self.initialize()
        with self.connection() as connection:
            return self.list_all_events(connection)

    def _convert_event_row(self, row: sqlite3.Row) -> dict[str, Any]:
        converted = dict(row)
        converted["occurred_at"] = datetime.fromisoformat(converted["occurred_at"])
        payload = json.loads(converted["payload_json"])
        converted["payload"] = payload
        converted["node_id"] = payload.get("node_id")
        converted["ticket_id"] = payload.get("ticket_id")
        converted["incident_id"] = payload.get("incident_id")
        converted["provider_id"] = payload.get("provider_id")
        converted["artifact_ref"] = payload.get("artifact_ref")
        return converted

    def _convert_approval_row(self, row: sqlite3.Row) -> dict[str, Any]:
        converted = dict(row)
        for field in ("resolved_at", "created_at", "updated_at"):
            if converted.get(field):
                converted[field] = datetime.fromisoformat(converted[field])
        converted["review_pack_version"] = int(converted.get("review_pack_version") or 1)
        converted["command_target_version"] = int(converted.get("command_target_version") or 0)
        converted["payload"] = json.loads(converted["payload_json"])
        return converted

    def _convert_compiled_context_bundle_row(self, row: sqlite3.Row) -> dict[str, Any]:
        converted = dict(row)
        converted["compiled_at"] = datetime.fromisoformat(converted["compiled_at"])
        converted["payload"] = json.loads(converted["payload_json"])
        return converted

    def _convert_compile_manifest_row(self, row: sqlite3.Row) -> dict[str, Any]:
        converted = dict(row)
        converted["compiled_at"] = datetime.fromisoformat(converted["compiled_at"])
        converted["payload"] = json.loads(converted["payload_json"])
        return converted

    def _convert_compiled_execution_package_row(self, row: sqlite3.Row) -> dict[str, Any]:
        converted = dict(row)
        converted["compiled_at"] = datetime.fromisoformat(converted["compiled_at"])
        converted["payload"] = json.loads(converted["payload_json"])
        return converted

    def _convert_ceo_shadow_run_row(self, row: sqlite3.Row) -> dict[str, Any]:
        converted = dict(row)
        converted["occurred_at"] = datetime.fromisoformat(converted["occurred_at"])
        converted["snapshot"] = json.loads(converted["snapshot_json"])
        converted["proposed_action_batch"] = json.loads(converted["proposed_action_batch_json"])
        converted["accepted_actions"] = json.loads(converted["accepted_actions_json"])
        converted["rejected_actions"] = json.loads(converted["rejected_actions_json"])
        converted["executed_actions"] = json.loads(converted.get("executed_actions_json") or "[]")
        converted["execution_summary"] = json.loads(converted.get("execution_summary_json") or "{}")
        converted["deterministic_fallback_used"] = bool(converted.get("deterministic_fallback_used"))
        converted["deterministic_fallback_reason"] = converted.get("deterministic_fallback_reason")
        converted["comparison"] = json.loads(converted["comparison_json"])
        return converted

    def _convert_artifact_index_row(self, row: sqlite3.Row) -> dict[str, Any]:
        converted = dict(row)
        converted["created_at"] = datetime.fromisoformat(converted["created_at"])
        for field in ("expires_at", "deleted_at", "storage_deleted_at"):
            if converted.get(field):
                converted[field] = datetime.fromisoformat(converted[field])
        converted["size_bytes"] = (
            int(converted["size_bytes"]) if converted.get("size_bytes") is not None else None
        )
        converted["retention_ttl_sec"] = (
            int(converted["retention_ttl_sec"])
            if converted.get("retention_ttl_sec") is not None
            else None
        )
        converted["path"] = converted["logical_path"]
        return converted

    def _convert_artifact_upload_session_row(self, row: sqlite3.Row) -> dict[str, Any]:
        converted = dict(row)
        for field in (
            "created_at",
            "updated_at",
            "completed_at",
            "aborted_at",
            "consumed_at",
        ):
            if converted.get(field):
                converted[field] = datetime.fromisoformat(converted[field])
        converted["size_bytes"] = (
            int(converted["size_bytes"]) if converted.get("size_bytes") is not None else None
        )
        converted["part_count"] = int(converted.get("part_count") or 0)
        return converted

    def _convert_artifact_upload_part_row(self, row: sqlite3.Row) -> dict[str, Any]:
        converted = dict(row)
        converted["part_number"] = int(converted["part_number"])
        converted["size_bytes"] = int(converted["size_bytes"])
        converted["uploaded_at"] = datetime.fromisoformat(converted["uploaded_at"])
        return converted

    def _convert_workflow_projection_row(self, row: sqlite3.Row) -> dict[str, Any]:
        converted = dict(row)
        for field in ("deadline_at", "started_at", "updated_at"):
            if converted.get(field):
                converted[field] = datetime.fromisoformat(converted[field])
        converted["budget_total"] = int(converted.get("budget_total") or 0)
        converted["budget_used"] = int(converted.get("budget_used") or 0)
        converted["version"] = int(converted.get("version") or 0)
        return converted

    def _convert_ticket_projection_row(self, row: sqlite3.Row) -> dict[str, Any]:
        converted = dict(row)
        if converted.get("updated_at"):
            converted["updated_at"] = datetime.fromisoformat(converted["updated_at"])
        if converted.get("lease_expires_at"):
            converted["lease_expires_at"] = datetime.fromisoformat(converted["lease_expires_at"])
        for field in ("started_at", "last_heartbeat_at", "heartbeat_expires_at"):
            if converted.get(field):
                converted[field] = datetime.fromisoformat(converted[field])
        converted["retry_count"] = int(converted.get("retry_count") or 0)
        converted["heartbeat_timeout_sec"] = (
            int(converted["heartbeat_timeout_sec"])
            if converted.get("heartbeat_timeout_sec") is not None
            else None
        )
        converted["retry_budget"] = (
            int(converted["retry_budget"]) if converted.get("retry_budget") is not None else None
        )
        converted["timeout_sla_sec"] = (
            int(converted["timeout_sla_sec"])
            if converted.get("timeout_sla_sec") is not None
            else None
        )
        converted["version"] = int(converted["version"])
        return converted

    def _convert_node_projection_row(self, row: sqlite3.Row) -> dict[str, Any]:
        converted = dict(row)
        if converted.get("updated_at"):
            converted["updated_at"] = datetime.fromisoformat(converted["updated_at"])
        converted["version"] = int(converted["version"])
        return converted

    def _convert_employee_projection_row(self, row: sqlite3.Row) -> dict[str, Any]:
        converted = dict(row)
        if converted.get("updated_at"):
            converted["updated_at"] = datetime.fromisoformat(converted["updated_at"])
        for field in ("skill_profile_json", "personality_profile_json", "aesthetic_profile_json"):
            raw_value = converted.get(field)
            converted[field] = json.loads(raw_value) if raw_value else {}
        raw_role_profiles = converted.get("role_profile_refs_json")
        converted["role_profile_refs"] = json.loads(raw_role_profiles) if raw_role_profiles else []
        converted.pop("role_profile_refs_json", None)
        converted["provider_id"] = converted.get("provider_id")
        converted["board_approved"] = bool(converted.get("board_approved"))
        converted["version"] = int(converted.get("version") or 0)
        return converted

    def _convert_worker_bootstrap_state_row(self, row: sqlite3.Row) -> dict[str, Any]:
        converted = dict(row)
        for field in ("revoked_before", "rotated_at", "updated_at"):
            if converted.get(field):
                converted[field] = datetime.fromisoformat(converted[field])
        converted["credential_version"] = int(converted.get("credential_version") or 0)
        return converted

    def _convert_worker_binding_admin_row(self, row: sqlite3.Row) -> dict[str, Any]:
        converted = self._convert_worker_bootstrap_state_row(row)
        converted["active_session_count"] = int(converted.get("active_session_count") or 0)
        converted["active_delivery_grant_count"] = int(
            converted.get("active_delivery_grant_count") or 0
        )
        converted["active_ticket_count"] = int(converted.get("active_ticket_count") or 0)
        converted["bootstrap_issue_count"] = int(converted.get("bootstrap_issue_count") or 0)
        if converted.get("latest_bootstrap_issue_at"):
            converted["latest_bootstrap_issue_at"] = datetime.fromisoformat(
                converted["latest_bootstrap_issue_at"]
            )
        converted["cleanup_eligible"] = (
            converted["active_session_count"] == 0
            and converted["active_delivery_grant_count"] == 0
            and converted["active_ticket_count"] == 0
            and (
                converted.get("revoked_before") is not None
                or converted["bootstrap_issue_count"] == 0
            )
        )
        return converted

    def _convert_worker_bootstrap_issue_row(self, row: sqlite3.Row) -> dict[str, Any]:
        converted = dict(row)
        for field in ("issued_at", "expires_at", "revoked_at"):
            if converted.get(field):
                converted[field] = datetime.fromisoformat(converted[field])
        converted["credential_version"] = int(converted.get("credential_version") or 0)
        return converted

    def _convert_worker_session_row(self, row: sqlite3.Row) -> dict[str, Any]:
        converted = dict(row)
        for field in ("issued_at", "expires_at", "last_seen_at", "revoked_at"):
            if converted.get(field):
                converted[field] = datetime.fromisoformat(converted[field])
        converted["credential_version"] = int(converted.get("credential_version") or 0)
        return converted

    def _convert_worker_delivery_grant_row(self, row: sqlite3.Row) -> dict[str, Any]:
        converted = dict(row)
        for field in ("issued_at", "expires_at", "revoked_at"):
            if converted.get(field):
                converted[field] = datetime.fromisoformat(converted[field])
        converted["credential_version"] = int(converted.get("credential_version") or 0)
        return converted

    def _convert_worker_auth_rejection_row(self, row: sqlite3.Row) -> dict[str, Any]:
        converted = dict(row)
        if converted.get("occurred_at"):
            converted["occurred_at"] = datetime.fromisoformat(converted["occurred_at"])
        return converted

    def _convert_worker_admin_token_issue_row(self, row: sqlite3.Row) -> dict[str, Any]:
        converted = dict(row)
        for field in ("issued_at", "expires_at", "revoked_at"):
            if converted.get(field):
                converted[field] = datetime.fromisoformat(converted[field])
        return converted

    def _convert_worker_admin_auth_rejection_row(self, row: sqlite3.Row) -> dict[str, Any]:
        converted = dict(row)
        if converted.get("occurred_at"):
            converted["occurred_at"] = datetime.fromisoformat(converted["occurred_at"])
        return converted

    def _convert_worker_admin_action_log_row(self, row: sqlite3.Row) -> dict[str, Any]:
        converted = dict(row)
        if converted.get("occurred_at"):
            converted["occurred_at"] = datetime.fromisoformat(converted["occurred_at"])
        converted["dry_run"] = bool(converted.get("dry_run"))
        converted["details"] = json.loads(converted.get("details_json") or "{}")
        return converted

    def _convert_incident_projection_row(self, row: sqlite3.Row) -> dict[str, Any]:
        converted = dict(row)
        for field in ("opened_at", "closed_at", "updated_at"):
            if converted.get(field):
                converted[field] = datetime.fromisoformat(converted[field])
        converted["payload"] = json.loads(converted["payload_json"])
        converted["version"] = int(converted.get("version") or 0)
        return converted

    def _matched_retrieval_terms(
        self,
        normalized_terms: list[str],
        values: list[str | None],
    ) -> list[str]:
        haystack = " ".join(
            str(value).lower()
            for value in values
            if value is not None and str(value).strip()
        )
        return [term for term in normalized_terms if term in haystack]

    def _sort_retrieval_candidates(
        self,
        candidates: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        channel_rank = {
            "review_summaries": 0,
            "incident_summaries": 1,
            "artifact_summaries": 2,
        }
        return sorted(
            candidates,
            key=lambda candidate: (
                -len(candidate.get("matched_terms") or []),
                channel_rank.get(str(candidate.get("channel") or ""), 99),
                -(
                    candidate["updated_at"].timestamp()
                    if isinstance(candidate.get("updated_at"), datetime)
                    else 0.0
                ),
            ),
        )

    def _read_retrieval_artifact_body(self, artifact: dict[str, Any]) -> str | None:
        if self.artifact_store is None:
            return None
        try:
            body = self.artifact_store.read_bytes(
                artifact.get("storage_relpath"),
                storage_object_key=artifact.get("storage_object_key"),
            )
        except Exception:
            return None

        normalized_kind = normalize_artifact_kind(str(artifact.get("kind") or ""))
        if normalized_kind == "JSON":
            try:
                parsed = json.loads(body.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                return None
            return json.dumps(parsed, ensure_ascii=True, sort_keys=True)
        try:
            return body.decode("utf-8")
        except UnicodeDecodeError:
            return None

    def _summarize_retrieval_text(self, value: str, *, limit: int = 180) -> str:
        compact = " ".join(value.split())
        if len(compact) <= limit:
            return compact
        return compact[: limit - 3].rstrip() + "..."

    def _event_category(self, event_type: str) -> str:
        if event_type == EVENT_SYSTEM_INITIALIZED:
            return "system"
        if event_type in {
            EVENT_TICKET_CREATED,
            EVENT_TICKET_CANCEL_REQUESTED,
            EVENT_TICKET_CANCELLED,
            EVENT_TICKET_FAILED,
            EVENT_TICKET_LEASED,
            EVENT_TICKET_RETRY_SCHEDULED,
            EVENT_TICKET_STARTED,
            EVENT_TICKET_COMPLETED,
            EVENT_TICKET_TIMED_OUT,
        }:
            return "ticket"
        if event_type in {
            EVENT_INCIDENT_OPENED,
            EVENT_INCIDENT_RECOVERY_STARTED,
            EVENT_INCIDENT_CLOSED,
            EVENT_CIRCUIT_BREAKER_OPENED,
            EVENT_CIRCUIT_BREAKER_CLOSED,
        }:
            return "system"
        if event_type in {
            EVENT_BOARD_REVIEW_REQUIRED,
            EVENT_BOARD_REVIEW_APPROVED,
            EVENT_BOARD_REVIEW_REJECTED,
        }:
            return "approval"
        if event_type in {
            EVENT_EMPLOYEE_HIRED,
            EVENT_EMPLOYEE_REPLACED,
            EVENT_EMPLOYEE_FROZEN,
        }:
            return "workflow"
        return "workflow"

    def _event_severity(self, event_type: str) -> str:
        if event_type in {
            EVENT_ARTIFACT_CLEANUP_COMPLETED,
            EVENT_ARTIFACT_DELETED,
            EVENT_ARTIFACT_EXPIRED,
            EVENT_SYSTEM_INITIALIZED,
            EVENT_BOARD_DIRECTIVE_RECEIVED,
            EVENT_WORKFLOW_CREATED,
            EVENT_TICKET_CREATED,
            EVENT_TICKET_RETRY_SCHEDULED,
            EVENT_TICKET_LEASED,
            EVENT_TICKET_STARTED,
            EVENT_TICKET_CANCELLED,
            EVENT_TICKET_COMPLETED,
            EVENT_BOARD_REVIEW_APPROVED,
            EVENT_INCIDENT_RECOVERY_STARTED,
            EVENT_INCIDENT_CLOSED,
            EVENT_CIRCUIT_BREAKER_CLOSED,
            EVENT_EMPLOYEE_HIRED,
            EVENT_EMPLOYEE_REPLACED,
            EVENT_EMPLOYEE_FROZEN,
        }:
            return "info"
        if event_type in {
            EVENT_TICKET_FAILED,
            EVENT_TICKET_TIMED_OUT,
            EVENT_TICKET_CANCEL_REQUESTED,
            EVENT_BOARD_REVIEW_REQUIRED,
            EVENT_BOARD_REVIEW_REJECTED,
            EVENT_INCIDENT_OPENED,
        }:
            return "warning"
        if event_type == EVENT_CIRCUIT_BREAKER_OPENED:
            return "critical"
        return "debug"

    def _event_preview_message(self, event: dict[str, Any]) -> str:
        if event["event_type"] == EVENT_SYSTEM_INITIALIZED:
            return "SYSTEM_INITIALIZED by system"
        if event["event_type"] == EVENT_BOARD_DIRECTIVE_RECEIVED:
            return "BOARD_DIRECTIVE_RECEIVED from board"
        if event["event_type"] == EVENT_WORKFLOW_CREATED:
            return f"WORKFLOW_CREATED for {event['workflow_id']}"
        if event["event_type"] == EVENT_TICKET_CREATED:
            return f"TICKET_CREATED for {event.get('ticket_id') or event['workflow_id']}"
        if event["event_type"] == EVENT_TICKET_LEASED:
            return f"TICKET_LEASED for {event.get('ticket_id') or event['workflow_id']}"
        if event["event_type"] == EVENT_TICKET_STARTED:
            return f"TICKET_STARTED for {event.get('ticket_id') or event['workflow_id']}"
        if event["event_type"] == EVENT_TICKET_CANCEL_REQUESTED:
            return f"TICKET_CANCEL_REQUESTED for {event.get('ticket_id') or event['workflow_id']}"
        if event["event_type"] == EVENT_TICKET_CANCELLED:
            return f"TICKET_CANCELLED for {event.get('ticket_id') or event['workflow_id']}"
        if event["event_type"] == EVENT_TICKET_COMPLETED:
            return f"TICKET_COMPLETED for {event.get('ticket_id') or event['workflow_id']}"
        if event["event_type"] == EVENT_TICKET_FAILED:
            return f"TICKET_FAILED for {event.get('ticket_id') or event['workflow_id']}"
        if event["event_type"] == EVENT_TICKET_TIMED_OUT:
            return f"TICKET_TIMED_OUT for {event.get('ticket_id') or event['workflow_id']}"
        if event["event_type"] == EVENT_TICKET_RETRY_SCHEDULED:
            return f"TICKET_RETRY_SCHEDULED for {event.get('ticket_id') or event['workflow_id']}"
        if event["event_type"] == EVENT_ARTIFACT_DELETED:
            return f"ARTIFACT_DELETED for {event.get('artifact_ref') or event['workflow_id']}"
        if event["event_type"] == EVENT_ARTIFACT_EXPIRED:
            return f"ARTIFACT_EXPIRED for {event.get('artifact_ref') or event['workflow_id']}"
        if event["event_type"] == EVENT_ARTIFACT_CLEANUP_COMPLETED:
            expired_count = event.get("payload", {}).get("expired_count")
            return f"ARTIFACT_CLEANUP_COMPLETED expired={expired_count}"
        if event["event_type"] == EVENT_INCIDENT_OPENED:
            if event.get("payload", {}).get("incident_type") == INCIDENT_TYPE_PROVIDER_EXECUTION_PAUSED:
                provider_id = event.get("provider_id") or event.get("payload", {}).get("provider_id")
                return f"PROVIDER_INCIDENT_OPENED for {provider_id or event['workflow_id']}"
            if event.get("payload", {}).get("incident_type") == INCIDENT_TYPE_REPEATED_FAILURE_ESCALATION:
                return f"REPEATED_FAILURE_INCIDENT_OPENED for {event.get('incident_id') or event['workflow_id']}"
            return f"INCIDENT_OPENED for {event.get('incident_id') or event['workflow_id']}"
        if event["event_type"] == EVENT_INCIDENT_CLOSED:
            if event.get("payload", {}).get("incident_type") == INCIDENT_TYPE_PROVIDER_EXECUTION_PAUSED:
                provider_id = event.get("provider_id") or event.get("payload", {}).get("provider_id")
                return f"PROVIDER_INCIDENT_CLOSED for {provider_id or event['workflow_id']}"
            if event.get("payload", {}).get("incident_type") == INCIDENT_TYPE_REPEATED_FAILURE_ESCALATION:
                return f"REPEATED_FAILURE_INCIDENT_CLOSED for {event.get('incident_id') or event['workflow_id']}"
            return f"INCIDENT_CLOSED for {event.get('incident_id') or event['workflow_id']}"
        if event["event_type"] == EVENT_INCIDENT_RECOVERY_STARTED:
            return f"INCIDENT_RECOVERY_STARTED for {event.get('incident_id') or event['workflow_id']}"
        if event["event_type"] == EVENT_CIRCUIT_BREAKER_OPENED:
            if event.get("provider_id") or event.get("payload", {}).get("provider_id"):
                provider_id = event.get("provider_id") or event.get("payload", {}).get("provider_id")
                return f"PROVIDER_BREAKER_OPENED for {provider_id or event['workflow_id']}"
            return f"CIRCUIT_BREAKER_OPENED for {event.get('incident_id') or event['workflow_id']}"
        if event["event_type"] == EVENT_CIRCUIT_BREAKER_CLOSED:
            if event.get("provider_id") or event.get("payload", {}).get("provider_id"):
                provider_id = event.get("provider_id") or event.get("payload", {}).get("provider_id")
                return f"PROVIDER_BREAKER_CLOSED for {provider_id or event['workflow_id']}"
            return f"CIRCUIT_BREAKER_CLOSED for {event.get('incident_id') or event['workflow_id']}"
        if event["event_type"] == EVENT_BOARD_REVIEW_REQUIRED:
            return "BOARD_REVIEW_REQUIRED pending board action"
        if event["event_type"] == EVENT_BOARD_REVIEW_APPROVED:
            return "BOARD_REVIEW_APPROVED by board"
        if event["event_type"] == EVENT_BOARD_REVIEW_REJECTED:
            return "BOARD_REVIEW_REJECTED by board"
        if event["event_type"] == EVENT_EMPLOYEE_HIRED:
            return f"EMPLOYEE_HIRED for {event.get('payload', {}).get('employee_id') or event['workflow_id']}"
        if event["event_type"] == EVENT_EMPLOYEE_REPLACED:
            return (
                f"EMPLOYEE_REPLACED for {event.get('payload', {}).get('employee_id') or event['workflow_id']}"
            )
        if event["event_type"] == EVENT_EMPLOYEE_FROZEN:
            return f"EMPLOYEE_FROZEN for {event.get('payload', {}).get('employee_id') or event['workflow_id']}"
        return event["event_type"]

    def _event_ui_hint(self, event_type: str) -> dict[str, Any]:
        if event_type == EVENT_SYSTEM_INITIALIZED:
            return {
                "invalidate": ["dashboard"],
                "refresh_policy": "debounced",
                "refresh_after_ms": 250,
                "toast": "Boardroom OS backend initialized.",
            }
        if event_type == EVENT_BOARD_DIRECTIVE_RECEIVED:
            return {
                "invalidate": ["dashboard", "inbox"],
                "refresh_policy": "debounced",
                "refresh_after_ms": 250,
                "toast": "Board directive received.",
            }
        if event_type == EVENT_TICKET_COMPLETED:
            return {
                "invalidate": ["dashboard"],
                "refresh_policy": "debounced",
                "refresh_after_ms": 250,
                "toast": "Ticket completed.",
            }
        if event_type == EVENT_TICKET_CREATED:
            return {
                "invalidate": ["dashboard"],
                "refresh_policy": "debounced",
                "refresh_after_ms": 250,
                "toast": "Ticket created.",
            }
        if event_type == EVENT_TICKET_LEASED:
            return {
                "invalidate": ["dashboard"],
                "refresh_policy": "debounced",
                "refresh_after_ms": 250,
                "toast": "Ticket leased.",
            }
        if event_type == EVENT_TICKET_STARTED:
            return {
                "invalidate": ["dashboard"],
                "refresh_policy": "debounced",
                "refresh_after_ms": 250,
                "toast": "Ticket started.",
            }
        if event_type == EVENT_TICKET_CANCEL_REQUESTED:
            return {
                "invalidate": ["dashboard", "incidents"],
                "refresh_policy": "debounced",
                "refresh_after_ms": 250,
                "toast": "Ticket cancellation requested.",
            }
        if event_type == EVENT_TICKET_CANCELLED:
            return {
                "invalidate": ["dashboard", "incidents"],
                "refresh_policy": "debounced",
                "refresh_after_ms": 250,
                "toast": "Ticket cancelled.",
            }
        if event_type == EVENT_TICKET_FAILED:
            return {
                "invalidate": ["dashboard"],
                "refresh_policy": "debounced",
                "refresh_after_ms": 250,
                "toast": "Ticket failed.",
            }
        if event_type == EVENT_TICKET_TIMED_OUT:
            return {
                "invalidate": ["dashboard"],
                "refresh_policy": "debounced",
                "refresh_after_ms": 250,
                "toast": "Ticket timed out.",
            }
        if event_type == EVENT_TICKET_RETRY_SCHEDULED:
            return {
                "invalidate": ["dashboard"],
                "refresh_policy": "debounced",
                "refresh_after_ms": 250,
                "toast": "Ticket retry scheduled.",
            }
        if event_type == EVENT_INCIDENT_OPENED:
            return {
                "invalidate": ["dashboard", "inbox", "incidents"],
                "refresh_policy": "debounced",
                "refresh_after_ms": 250,
                "toast": "Incident opened.",
            }
        if event_type == EVENT_INCIDENT_CLOSED:
            return {
                "invalidate": ["dashboard", "inbox", "incidents"],
                "refresh_policy": "debounced",
                "refresh_after_ms": 250,
                "toast": "Incident closed.",
            }
        if event_type == EVENT_INCIDENT_RECOVERY_STARTED:
            return {
                "invalidate": ["dashboard", "inbox", "incidents"],
                "refresh_policy": "debounced",
                "refresh_after_ms": 250,
                "toast": "Incident recovery started.",
            }
        if event_type == EVENT_CIRCUIT_BREAKER_OPENED:
            return {
                "invalidate": ["dashboard", "inbox", "incidents"],
                "refresh_policy": "debounced",
                "refresh_after_ms": 250,
                "toast": "Execution pause opened.",
            }
        if event_type == EVENT_CIRCUIT_BREAKER_CLOSED:
            return {
                "invalidate": ["dashboard", "inbox", "incidents"],
                "refresh_policy": "debounced",
                "refresh_after_ms": 250,
                "toast": "Execution pause cleared.",
            }
        if event_type == EVENT_BOARD_REVIEW_REQUIRED:
            return {
                "invalidate": ["dashboard", "inbox", "review-room"],
                "refresh_policy": "debounced",
                "refresh_after_ms": 250,
                "toast": "Board review requested.",
            }
        if event_type == EVENT_BOARD_REVIEW_APPROVED:
            return {
                "invalidate": ["dashboard", "inbox", "review-room"],
                "refresh_policy": "debounced",
                "refresh_after_ms": 250,
                "toast": "Board review approved.",
            }
        if event_type == EVENT_BOARD_REVIEW_REJECTED:
            return {
                "invalidate": ["dashboard", "inbox", "review-room"],
                "refresh_policy": "debounced",
                "refresh_after_ms": 250,
                "toast": "Board review rejected.",
            }
        if event_type in {
            EVENT_EMPLOYEE_HIRED,
            EVENT_EMPLOYEE_REPLACED,
            EVENT_EMPLOYEE_FROZEN,
        }:
            return {
                "invalidate": ["dashboard", "inbox", "workforce"],
                "refresh_policy": "debounced",
                "refresh_after_ms": 250,
                "toast": "Workforce roster updated.",
            }
        return {
            "invalidate": ["dashboard", "inbox"],
            "refresh_policy": "debounced",
            "refresh_after_ms": 250,
            "toast": "Workflow created.",
        }

    def _ensure_approval_projection_shape(self, connection: sqlite3.Connection) -> None:
        existing_columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(approval_projection)").fetchall()
        }
        required_columns = {
            "review_pack_id": "TEXT",
            "created_at": "TEXT",
            "updated_at": "TEXT",
            "review_pack_version": "INTEGER",
            "command_target_version": "INTEGER",
        }
        for column_name, column_type in required_columns.items():
            if column_name not in existing_columns:
                connection.execute(
                    f"ALTER TABLE approval_projection ADD COLUMN {column_name} {column_type}"
                )
        connection.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_approval_projection_review_pack_id ON approval_projection(review_pack_id)"
        )

    def _ensure_workflow_projection_shape(self, connection: sqlite3.Connection) -> None:
        existing_columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(workflow_projection)").fetchall()
        }
        required_columns = {
            "workflow_id": "TEXT",
            "title": "TEXT",
            "north_star_goal": "TEXT",
            "tenant_id": "TEXT",
            "workspace_id": "TEXT",
            "current_stage": "TEXT",
            "status": "TEXT",
            "budget_total": "INTEGER",
            "budget_used": "INTEGER",
            "board_gate_state": "TEXT",
            "deadline_at": "TEXT",
            "started_at": "TEXT",
            "updated_at": "TEXT",
            "version": "INTEGER",
        }
        for column_name, column_type in required_columns.items():
            if column_name not in existing_columns:
                connection.execute(
                    f"ALTER TABLE workflow_projection ADD COLUMN {column_name} {column_type}"
                )

    def _ensure_ticket_projection_shape(self, connection: sqlite3.Connection) -> None:
        existing_columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(ticket_projection)").fetchall()
        }
        required_columns = {
            "ticket_id": "TEXT",
            "workflow_id": "TEXT",
            "node_id": "TEXT",
            "tenant_id": "TEXT",
            "workspace_id": "TEXT",
            "status": "TEXT",
            "lease_owner": "TEXT",
            "lease_expires_at": "TEXT",
            "started_at": "TEXT",
            "last_heartbeat_at": "TEXT",
            "heartbeat_expires_at": "TEXT",
            "heartbeat_timeout_sec": "INTEGER",
            "retry_count": "INTEGER DEFAULT 0",
            "retry_budget": "INTEGER",
            "timeout_sla_sec": "INTEGER",
            "priority": "TEXT",
            "last_failure_kind": "TEXT",
            "last_failure_message": "TEXT",
            "last_failure_fingerprint": "TEXT",
            "blocking_reason_code": "TEXT",
            "updated_at": "TEXT",
            "version": "INTEGER",
        }
        for column_name, column_type in required_columns.items():
            if column_name not in existing_columns:
                connection.execute(
                    f"ALTER TABLE ticket_projection ADD COLUMN {column_name} {column_type}"
                )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_ticket_projection_node_id ON ticket_projection(node_id)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_ticket_projection_status ON ticket_projection(status)"
        )

    def _ensure_node_projection_shape(self, connection: sqlite3.Connection) -> None:
        existing_columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(node_projection)").fetchall()
        }
        required_columns = {
            "workflow_id": "TEXT",
            "node_id": "TEXT",
            "latest_ticket_id": "TEXT",
            "status": "TEXT",
            "blocking_reason_code": "TEXT",
            "updated_at": "TEXT",
            "version": "INTEGER",
        }
        for column_name, column_type in required_columns.items():
            if column_name not in existing_columns:
                connection.execute(
                    f"ALTER TABLE node_projection ADD COLUMN {column_name} {column_type}"
                )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_node_projection_status ON node_projection(status)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_node_projection_latest_ticket_id ON node_projection(latest_ticket_id)"
        )

    def _ensure_employee_projection_shape(self, connection: sqlite3.Connection) -> None:
        existing_columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(employee_projection)").fetchall()
        }
        required_columns = {
            "employee_id": "TEXT",
            "role_type": "TEXT",
            "skill_profile_json": "TEXT",
            "personality_profile_json": "TEXT",
            "aesthetic_profile_json": "TEXT",
            "state": "TEXT",
            "board_approved": "INTEGER",
            "provider_id": "TEXT",
            "role_profile_refs_json": "TEXT",
            "updated_at": "TEXT",
            "version": "INTEGER",
        }
        for column_name, column_type in required_columns.items():
            if column_name not in existing_columns:
                connection.execute(
                    f"ALTER TABLE employee_projection ADD COLUMN {column_name} {column_type}"
                )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_employee_projection_state ON employee_projection(state)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_employee_projection_role_type ON employee_projection(role_type)"
        )

    def _ensure_worker_bootstrap_state_shape(self, connection: sqlite3.Connection) -> None:
        if self._worker_bootstrap_state_requires_rebuild(connection):
            self._rebuild_worker_bootstrap_state_table(connection)
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS worker_bootstrap_state (
                worker_id TEXT NOT NULL,
                credential_version INTEGER NOT NULL,
                tenant_id TEXT NOT NULL,
                workspace_id TEXT NOT NULL,
                revoked_before TEXT,
                rotated_at TEXT,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (worker_id, tenant_id, workspace_id)
            )
            """
        )
        existing_columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(worker_bootstrap_state)").fetchall()
        }
        required_columns = {
            "worker_id": "TEXT",
            "credential_version": "INTEGER",
            "tenant_id": "TEXT",
            "workspace_id": "TEXT",
            "revoked_before": "TEXT",
            "rotated_at": "TEXT",
            "updated_at": "TEXT",
        }
        for column_name, column_type in required_columns.items():
            if column_name not in existing_columns:
                connection.execute(
                    f"ALTER TABLE worker_bootstrap_state ADD COLUMN {column_name} {column_type}"
                )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_worker_bootstrap_state_worker_id ON worker_bootstrap_state(worker_id)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_worker_bootstrap_state_scope ON worker_bootstrap_state(tenant_id, workspace_id)"
        )

    def _ensure_worker_session_shape(self, connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS worker_session (
                session_id TEXT PRIMARY KEY,
                worker_id TEXT NOT NULL,
                tenant_id TEXT NOT NULL,
                workspace_id TEXT NOT NULL,
                issued_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                revoked_at TEXT,
                credential_version INTEGER NOT NULL,
                revoke_reason TEXT,
                revoked_via TEXT,
                revoked_by TEXT
            )
            """
        )
        existing_columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(worker_session)").fetchall()
        }
        required_columns = {
            "session_id": "TEXT",
            "worker_id": "TEXT",
            "tenant_id": "TEXT",
            "workspace_id": "TEXT",
            "issued_at": "TEXT",
            "expires_at": "TEXT",
            "last_seen_at": "TEXT",
            "revoked_at": "TEXT",
            "credential_version": "INTEGER",
            "revoke_reason": "TEXT",
            "revoked_via": "TEXT",
            "revoked_by": "TEXT",
        }
        for column_name, column_type in required_columns.items():
            if column_name not in existing_columns:
                connection.execute(
                    f"ALTER TABLE worker_session ADD COLUMN {column_name} {column_type}"
                )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_worker_session_worker_id ON worker_session(worker_id)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_worker_session_expires_at ON worker_session(expires_at)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_worker_session_scope ON worker_session(tenant_id, workspace_id)"
        )

    def _ensure_worker_bootstrap_issue_shape(self, connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS worker_bootstrap_issue (
                issue_id TEXT PRIMARY KEY,
                worker_id TEXT NOT NULL,
                tenant_id TEXT NOT NULL,
                workspace_id TEXT NOT NULL,
                credential_version INTEGER NOT NULL,
                issued_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                issued_via TEXT NOT NULL,
                issued_by TEXT,
                reason TEXT,
                revoked_at TEXT
            )
            """
        )
        existing_columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(worker_bootstrap_issue)").fetchall()
        }
        required_columns = {
            "issue_id": "TEXT",
            "worker_id": "TEXT",
            "tenant_id": "TEXT",
            "workspace_id": "TEXT",
            "credential_version": "INTEGER",
            "issued_at": "TEXT",
            "expires_at": "TEXT",
            "issued_via": "TEXT",
            "issued_by": "TEXT",
            "reason": "TEXT",
            "revoked_at": "TEXT",
        }
        for column_name, column_type in required_columns.items():
            if column_name not in existing_columns:
                connection.execute(
                    f"ALTER TABLE worker_bootstrap_issue ADD COLUMN {column_name} {column_type}"
                )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_worker_bootstrap_issue_worker_id ON worker_bootstrap_issue(worker_id)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_worker_bootstrap_issue_scope ON worker_bootstrap_issue(tenant_id, workspace_id)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_worker_bootstrap_issue_expires_at ON worker_bootstrap_issue(expires_at)"
        )

    def _worker_bootstrap_state_requires_rebuild(self, connection: sqlite3.Connection) -> bool:
        rows = connection.execute("PRAGMA table_info(worker_bootstrap_state)").fetchall()
        if not rows:
            return False
        pk_rows = [row for row in rows if int(row["pk"] or 0) > 0]
        pk_columns = [
            str(row["name"])
            for row in sorted(pk_rows, key=lambda item: int(item["pk"] or 0))
        ]
        return pk_columns != ["worker_id", "tenant_id", "workspace_id"]

    def _rebuild_worker_bootstrap_state_table(self, connection: sqlite3.Connection) -> None:
        existing_columns = {
            str(row["name"])
            for row in connection.execute("PRAGMA table_info(worker_bootstrap_state)").fetchall()
        }
        tenant_expr = "COALESCE(NULLIF(TRIM(tenant_id), ''), ?)" if "tenant_id" in existing_columns else "?"
        workspace_expr = (
            "COALESCE(NULLIF(TRIM(workspace_id), ''), ?)" if "workspace_id" in existing_columns else "?"
        )
        updated_expr = "COALESCE(updated_at, ?)" if "updated_at" in existing_columns else "?"
        migrated_at = now_local().isoformat()

        connection.execute("ALTER TABLE worker_bootstrap_state RENAME TO worker_bootstrap_state_legacy")
        connection.execute(
            """
            CREATE TABLE worker_bootstrap_state (
                worker_id TEXT NOT NULL,
                credential_version INTEGER NOT NULL,
                tenant_id TEXT NOT NULL,
                workspace_id TEXT NOT NULL,
                revoked_before TEXT,
                rotated_at TEXT,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (worker_id, tenant_id, workspace_id)
            )
            """
        )
        connection.execute(
            f"""
            INSERT INTO worker_bootstrap_state (
                worker_id,
                credential_version,
                tenant_id,
                workspace_id,
                revoked_before,
                rotated_at,
                updated_at
            )
            SELECT
                worker_id,
                credential_version,
                {tenant_expr},
                {workspace_expr},
                revoked_before,
                rotated_at,
                {updated_expr}
            FROM worker_bootstrap_state_legacy
            """,
            (
                DEFAULT_TENANT_ID,
                DEFAULT_WORKSPACE_ID,
                migrated_at,
            ),
        )
        connection.execute("DROP TABLE worker_bootstrap_state_legacy")

    def _ensure_worker_delivery_grant_shape(self, connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS worker_delivery_grant (
                grant_id TEXT PRIMARY KEY,
                scope TEXT NOT NULL,
                worker_id TEXT NOT NULL,
                session_id TEXT NOT NULL,
                credential_version INTEGER NOT NULL,
                tenant_id TEXT NOT NULL,
                workspace_id TEXT NOT NULL,
                ticket_id TEXT NOT NULL,
                artifact_ref TEXT,
                artifact_action TEXT,
                command_name TEXT,
                issued_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                revoked_at TEXT,
                revoke_reason TEXT,
                revoked_via TEXT,
                revoked_by TEXT
            )
            """
        )
        existing_columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(worker_delivery_grant)").fetchall()
        }
        required_columns = {
            "grant_id": "TEXT",
            "scope": "TEXT",
            "worker_id": "TEXT",
            "session_id": "TEXT",
            "credential_version": "INTEGER",
            "tenant_id": "TEXT",
            "workspace_id": "TEXT",
            "ticket_id": "TEXT",
            "artifact_ref": "TEXT",
            "artifact_action": "TEXT",
            "command_name": "TEXT",
            "issued_at": "TEXT",
            "expires_at": "TEXT",
            "revoked_at": "TEXT",
            "revoke_reason": "TEXT",
            "revoked_via": "TEXT",
            "revoked_by": "TEXT",
        }
        for column_name, column_type in required_columns.items():
            if column_name not in existing_columns:
                connection.execute(
                    f"ALTER TABLE worker_delivery_grant ADD COLUMN {column_name} {column_type}"
                )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_worker_delivery_grant_session_id ON worker_delivery_grant(session_id)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_worker_delivery_grant_ticket_id ON worker_delivery_grant(ticket_id)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_worker_delivery_grant_expires_at ON worker_delivery_grant(expires_at)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_worker_delivery_grant_revoked_at ON worker_delivery_grant(revoked_at)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_worker_delivery_grant_scope ON worker_delivery_grant(tenant_id, workspace_id)"
        )

    def _ensure_worker_auth_rejection_log_shape(self, connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS worker_auth_rejection_log (
                rejection_id TEXT PRIMARY KEY,
                occurred_at TEXT NOT NULL,
                route_family TEXT NOT NULL,
                reason_code TEXT NOT NULL,
                worker_id TEXT,
                session_id TEXT,
                grant_id TEXT,
                ticket_id TEXT,
                tenant_id TEXT,
                workspace_id TEXT
            )
            """
        )
        existing_columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(worker_auth_rejection_log)").fetchall()
        }
        required_columns = {
            "rejection_id": "TEXT",
            "occurred_at": "TEXT",
            "route_family": "TEXT",
            "reason_code": "TEXT",
            "worker_id": "TEXT",
            "session_id": "TEXT",
            "grant_id": "TEXT",
            "ticket_id": "TEXT",
            "tenant_id": "TEXT",
            "workspace_id": "TEXT",
        }
        for column_name, column_type in required_columns.items():
            if column_name not in existing_columns:
                connection.execute(
                    f"ALTER TABLE worker_auth_rejection_log ADD COLUMN {column_name} {column_type}"
                )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_worker_auth_rejection_log_occurred_at ON worker_auth_rejection_log(occurred_at)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_worker_auth_rejection_log_scope ON worker_auth_rejection_log(tenant_id, workspace_id)"
        )

    def _ensure_worker_admin_token_issue_shape(self, connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS worker_admin_token_issue (
                token_id TEXT PRIMARY KEY,
                operator_id TEXT NOT NULL,
                role TEXT NOT NULL,
                tenant_id TEXT,
                workspace_id TEXT,
                issued_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                issued_via TEXT NOT NULL,
                issued_by TEXT,
                revoked_at TEXT,
                revoked_by TEXT,
                revoke_reason TEXT
            )
            """
        )
        existing_columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(worker_admin_token_issue)").fetchall()
        }
        required_columns = {
            "token_id": "TEXT",
            "operator_id": "TEXT",
            "role": "TEXT",
            "tenant_id": "TEXT",
            "workspace_id": "TEXT",
            "issued_at": "TEXT",
            "expires_at": "TEXT",
            "issued_via": "TEXT",
            "issued_by": "TEXT",
            "revoked_at": "TEXT",
            "revoked_by": "TEXT",
            "revoke_reason": "TEXT",
        }
        for column_name, column_type in required_columns.items():
            if column_name not in existing_columns:
                connection.execute(
                    f"ALTER TABLE worker_admin_token_issue ADD COLUMN {column_name} {column_type}"
                )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_worker_admin_token_issue_operator_id ON worker_admin_token_issue(operator_id)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_worker_admin_token_issue_role ON worker_admin_token_issue(role)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_worker_admin_token_issue_scope ON worker_admin_token_issue(tenant_id, workspace_id)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_worker_admin_token_issue_expires_at ON worker_admin_token_issue(expires_at)"
        )

    def _ensure_worker_admin_auth_rejection_log_shape(self, connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS worker_admin_auth_rejection_log (
                rejection_id TEXT PRIMARY KEY,
                occurred_at TEXT NOT NULL,
                route_path TEXT NOT NULL,
                reason_code TEXT NOT NULL,
                operator_id TEXT,
                operator_role TEXT,
                token_id TEXT,
                tenant_id TEXT,
                workspace_id TEXT,
                trusted_proxy_id TEXT,
                source_ip TEXT
            )
            """
        )
        existing_columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(worker_admin_auth_rejection_log)").fetchall()
        }
        required_columns = {
            "rejection_id": "TEXT",
            "occurred_at": "TEXT",
            "route_path": "TEXT",
            "reason_code": "TEXT",
            "operator_id": "TEXT",
            "operator_role": "TEXT",
            "token_id": "TEXT",
            "tenant_id": "TEXT",
            "workspace_id": "TEXT",
            "trusted_proxy_id": "TEXT",
            "source_ip": "TEXT",
        }
        for column_name, column_type in required_columns.items():
            if column_name not in existing_columns:
                connection.execute(
                    f"ALTER TABLE worker_admin_auth_rejection_log ADD COLUMN {column_name} {column_type}"
                )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_worker_admin_auth_rejection_log_occurred_at ON worker_admin_auth_rejection_log(occurred_at)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_worker_admin_auth_rejection_log_scope ON worker_admin_auth_rejection_log(tenant_id, workspace_id)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_worker_admin_auth_rejection_log_token_id ON worker_admin_auth_rejection_log(token_id)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_worker_admin_auth_rejection_log_operator_id ON worker_admin_auth_rejection_log(operator_id)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_worker_admin_auth_rejection_log_route_path ON worker_admin_auth_rejection_log(route_path)"
        )

    def _ensure_worker_admin_action_log_shape(self, connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS worker_admin_action_log (
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
                trusted_proxy_id TEXT,
                source_ip TEXT,
                action_type TEXT NOT NULL,
                dry_run INTEGER NOT NULL DEFAULT 0,
                details_json TEXT NOT NULL
            )
            """
        )
        existing_columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(worker_admin_action_log)").fetchall()
        }
        required_columns = {
            "action_id": "TEXT",
            "occurred_at": "TEXT",
            "operator_id": "TEXT",
            "operator_role": "TEXT",
            "auth_source": "TEXT",
            "tenant_id": "TEXT",
            "workspace_id": "TEXT",
            "worker_id": "TEXT",
            "session_id": "TEXT",
            "grant_id": "TEXT",
            "issue_id": "TEXT",
            "trusted_proxy_id": "TEXT",
            "source_ip": "TEXT",
            "action_type": "TEXT",
            "dry_run": "INTEGER NOT NULL DEFAULT 0",
            "details_json": "TEXT NOT NULL DEFAULT '{}'",
        }
        for column_name, column_type in required_columns.items():
            if column_name not in existing_columns:
                connection.execute(
                    f"ALTER TABLE worker_admin_action_log ADD COLUMN {column_name} {column_type}"
                )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_worker_admin_action_log_occurred_at ON worker_admin_action_log(occurred_at)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_worker_admin_action_log_scope ON worker_admin_action_log(tenant_id, workspace_id)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_worker_admin_action_log_operator_id ON worker_admin_action_log(operator_id)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_worker_admin_action_log_action_type ON worker_admin_action_log(action_type)"
        )

    def _ensure_incident_projection_shape(self, connection: sqlite3.Connection) -> None:
        existing_columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(incident_projection)").fetchall()
        }
        required_columns = {
            "incident_id": "TEXT",
            "workflow_id": "TEXT",
            "node_id": "TEXT",
            "ticket_id": "TEXT",
            "provider_id": "TEXT",
            "incident_type": "TEXT",
            "status": "TEXT",
            "severity": "TEXT",
            "fingerprint": "TEXT",
            "circuit_breaker_state": "TEXT",
            "opened_at": "TEXT",
            "closed_at": "TEXT",
            "payload_json": "TEXT",
            "updated_at": "TEXT",
            "version": "INTEGER",
        }
        for column_name, column_type in required_columns.items():
            if column_name not in existing_columns:
                connection.execute(
                    f"ALTER TABLE incident_projection ADD COLUMN {column_name} {column_type}"
                )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_incident_projection_status ON incident_projection(status)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_incident_projection_node_id ON incident_projection(node_id)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_incident_projection_provider_id ON incident_projection(provider_id)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_incident_projection_fingerprint ON incident_projection(fingerprint)"
        )

    def _ensure_compiled_context_bundle_shape(self, connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS compiled_context_bundle (
                bundle_id TEXT PRIMARY KEY,
                compile_request_id TEXT NOT NULL,
                ticket_id TEXT NOT NULL,
                workflow_id TEXT NOT NULL,
                node_id TEXT NOT NULL,
                compiler_version TEXT NOT NULL,
                compiled_at TEXT NOT NULL,
                bundle_version TEXT NOT NULL,
                payload_json TEXT NOT NULL
            )
            """
        )
        existing_columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(compiled_context_bundle)").fetchall()
        }
        required_columns = {
            "bundle_id": "TEXT",
            "compile_request_id": "TEXT",
            "ticket_id": "TEXT",
            "workflow_id": "TEXT",
            "node_id": "TEXT",
            "compiler_version": "TEXT",
            "compiled_at": "TEXT",
            "bundle_version": "TEXT",
            "payload_json": "TEXT",
        }
        for column_name, column_type in required_columns.items():
            if column_name not in existing_columns:
                connection.execute(
                    f"ALTER TABLE compiled_context_bundle ADD COLUMN {column_name} {column_type}"
                )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_compiled_context_bundle_ticket_id ON compiled_context_bundle(ticket_id)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_compiled_context_bundle_compile_request_id ON compiled_context_bundle(compile_request_id)"
        )

    def _ensure_compile_manifest_shape(self, connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS compile_manifest (
                compile_id TEXT PRIMARY KEY,
                bundle_id TEXT NOT NULL,
                compile_request_id TEXT NOT NULL,
                ticket_id TEXT NOT NULL,
                workflow_id TEXT NOT NULL,
                node_id TEXT NOT NULL,
                compiler_version TEXT NOT NULL,
                compiled_at TEXT NOT NULL,
                manifest_version TEXT NOT NULL,
                payload_json TEXT NOT NULL
            )
            """
        )
        existing_columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(compile_manifest)").fetchall()
        }
        required_columns = {
            "compile_id": "TEXT",
            "bundle_id": "TEXT",
            "compile_request_id": "TEXT",
            "ticket_id": "TEXT",
            "workflow_id": "TEXT",
            "node_id": "TEXT",
            "compiler_version": "TEXT",
            "compiled_at": "TEXT",
            "manifest_version": "TEXT",
            "payload_json": "TEXT",
        }
        for column_name, column_type in required_columns.items():
            if column_name not in existing_columns:
                connection.execute(
                    f"ALTER TABLE compile_manifest ADD COLUMN {column_name} {column_type}"
                )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_compile_manifest_ticket_id ON compile_manifest(ticket_id)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_compile_manifest_compile_request_id ON compile_manifest(compile_request_id)"
        )

    def _ensure_compiled_execution_package_shape(self, connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS compiled_execution_package (
                compile_request_id TEXT PRIMARY KEY,
                ticket_id TEXT NOT NULL,
                workflow_id TEXT NOT NULL,
                node_id TEXT NOT NULL,
                compiler_version TEXT NOT NULL,
                compiled_at TEXT NOT NULL,
                package_version TEXT NOT NULL,
                payload_json TEXT NOT NULL
            )
            """
        )
        existing_columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(compiled_execution_package)").fetchall()
        }
        required_columns = {
            "compile_request_id": "TEXT",
            "ticket_id": "TEXT",
            "workflow_id": "TEXT",
            "node_id": "TEXT",
            "compiler_version": "TEXT",
            "compiled_at": "TEXT",
            "package_version": "TEXT",
            "payload_json": "TEXT",
        }
        for column_name, column_type in required_columns.items():
            if column_name not in existing_columns:
                connection.execute(
                    f"ALTER TABLE compiled_execution_package ADD COLUMN {column_name} {column_type}"
                )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_compiled_execution_package_ticket_id ON compiled_execution_package(ticket_id)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_compiled_execution_package_compile_request_id ON compiled_execution_package(compile_request_id)"
        )

    def _ensure_ceo_shadow_run_shape(self, connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS ceo_shadow_run (
                run_id TEXT PRIMARY KEY,
                workflow_id TEXT NOT NULL,
                trigger_type TEXT NOT NULL,
                trigger_ref TEXT,
                occurred_at TEXT NOT NULL,
                effective_mode TEXT NOT NULL,
                provider_health_summary TEXT NOT NULL,
                model TEXT,
                prompt_version TEXT NOT NULL,
                provider_response_id TEXT,
                fallback_reason TEXT,
                snapshot_json TEXT NOT NULL,
                proposed_action_batch_json TEXT NOT NULL,
                accepted_actions_json TEXT NOT NULL,
                rejected_actions_json TEXT NOT NULL,
                executed_actions_json TEXT NOT NULL,
                execution_summary_json TEXT NOT NULL,
                deterministic_fallback_used INTEGER NOT NULL DEFAULT 0,
                deterministic_fallback_reason TEXT,
                comparison_json TEXT NOT NULL
            )
            """
        )
        existing_columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(ceo_shadow_run)").fetchall()
        }
        required_columns = {
            "run_id": "TEXT",
            "workflow_id": "TEXT",
            "trigger_type": "TEXT",
            "trigger_ref": "TEXT",
            "occurred_at": "TEXT",
            "effective_mode": "TEXT",
            "provider_health_summary": "TEXT",
            "model": "TEXT",
            "prompt_version": "TEXT",
            "provider_response_id": "TEXT",
            "fallback_reason": "TEXT",
            "snapshot_json": "TEXT",
            "proposed_action_batch_json": "TEXT",
            "accepted_actions_json": "TEXT",
            "rejected_actions_json": "TEXT",
            "executed_actions_json": "TEXT",
            "execution_summary_json": "TEXT",
            "deterministic_fallback_used": "INTEGER NOT NULL DEFAULT 0",
            "deterministic_fallback_reason": "TEXT",
            "comparison_json": "TEXT",
        }
        for column_name, column_type in required_columns.items():
            if column_name not in existing_columns:
                connection.execute(
                    f"ALTER TABLE ceo_shadow_run ADD COLUMN {column_name} {column_type}"
                )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_ceo_shadow_run_workflow_id ON ceo_shadow_run(workflow_id)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_ceo_shadow_run_occurred_at ON ceo_shadow_run(occurred_at)"
        )

    def _ensure_artifact_index_shape(self, connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS artifact_index (
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
                storage_backend TEXT,
                storage_object_key TEXT,
                storage_delete_status TEXT,
                storage_delete_error TEXT,
                expires_at TEXT,
                deleted_at TEXT,
                deleted_by TEXT,
                delete_reason TEXT,
                storage_deleted_at TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        existing_columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(artifact_index)").fetchall()
        }
        required_columns = {
            "artifact_ref": "TEXT",
            "workflow_id": "TEXT",
            "ticket_id": "TEXT",
            "node_id": "TEXT",
            "logical_path": "TEXT",
            "kind": "TEXT",
            "media_type": "TEXT",
            "materialization_status": "TEXT",
            "lifecycle_status": "TEXT",
            "storage_relpath": "TEXT",
            "content_hash": "TEXT",
            "size_bytes": "INTEGER",
            "retention_class": "TEXT",
            "retention_class_source": "TEXT",
            "retention_ttl_sec": "INTEGER",
            "retention_policy_source": "TEXT",
            "storage_backend": "TEXT",
            "storage_object_key": "TEXT",
            "storage_delete_status": "TEXT",
            "storage_delete_error": "TEXT",
            "expires_at": "TEXT",
            "deleted_at": "TEXT",
            "deleted_by": "TEXT",
            "delete_reason": "TEXT",
            "storage_deleted_at": "TEXT",
            "created_at": "TEXT",
        }
        for column_name, column_type in required_columns.items():
            if column_name not in existing_columns:
                connection.execute(
                    f"ALTER TABLE artifact_index ADD COLUMN {column_name} {column_type}"
                )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_artifact_index_ticket_id ON artifact_index(ticket_id)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_artifact_index_workflow_id ON artifact_index(workflow_id)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_artifact_index_node_id ON artifact_index(node_id)"
        )

    def _ensure_artifact_upload_session_shape(self, connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS artifact_upload_session (
                session_id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                filename TEXT,
                media_type TEXT,
                assembled_staging_relpath TEXT,
                size_bytes INTEGER,
                content_hash TEXT,
                part_count INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                completed_at TEXT,
                aborted_at TEXT,
                consumed_at TEXT,
                created_by TEXT NOT NULL,
                consumed_by_artifact_ref TEXT
            )
            """
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_artifact_upload_session_status ON artifact_upload_session(status)"
        )

    def _ensure_artifact_upload_part_shape(self, connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS artifact_upload_part (
                session_id TEXT NOT NULL,
                part_number INTEGER NOT NULL,
                staging_relpath TEXT NOT NULL,
                size_bytes INTEGER NOT NULL,
                content_hash TEXT NOT NULL,
                uploaded_at TEXT NOT NULL,
                PRIMARY KEY (session_id, part_number),
                FOREIGN KEY(session_id) REFERENCES artifact_upload_session(session_id) ON DELETE CASCADE
            )
            """
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_artifact_upload_part_session_id ON artifact_upload_part(session_id)"
        )

    def _backfill_artifact_retention_defaults(self, connection: sqlite3.Connection) -> None:
        settings = get_settings()
        retention_defaults = build_artifact_retention_defaults(
            default_ephemeral_ttl_sec=settings.artifact_ephemeral_default_ttl_sec,
            default_operational_evidence_ttl_sec=(
                settings.artifact_operational_evidence_default_ttl_sec
            ),
            default_review_evidence_ttl_sec=settings.artifact_review_evidence_default_ttl_sec,
        )
        rows = connection.execute(
            """
            SELECT * FROM artifact_index
            WHERE expires_at IS NULL
              AND (
                    retention_policy_source IS NULL
                    OR TRIM(retention_policy_source) = ''
                  )
            """
        ).fetchall()
        for row in rows:
            converted = self._convert_artifact_index_row(row)
            default_ttl_sec = retention_defaults.get(str(converted["retention_class"]))
            if default_ttl_sec is None:
                continue
            expires_at = converted["created_at"] + timedelta(seconds=default_ttl_sec)
            connection.execute(
                """
                UPDATE artifact_index
                SET expires_at = ?,
                    retention_ttl_sec = ?,
                    retention_policy_source = ?
                WHERE artifact_ref = ?
                  AND expires_at IS NULL
                """,
                (
                    expires_at.isoformat(),
                    default_ttl_sec,
                    ARTIFACT_RETENTION_POLICY_BACKFILLED_CLASS_DEFAULT,
                    converted["artifact_ref"],
                ),
            )
        connection.execute(
            """
            UPDATE artifact_index
            SET retention_policy_source = ?
            WHERE expires_at IS NOT NULL
              AND (
                    retention_policy_source IS NULL
                    OR TRIM(retention_policy_source) = ''
                  )
            """,
            (ARTIFACT_RETENTION_POLICY_LEGACY_UNKNOWN,),
        )
        connection.execute(
            """
            UPDATE artifact_index
            SET retention_policy_source = ?
            WHERE expires_at IS NULL
              AND (
                    retention_policy_source IS NULL
                    OR TRIM(retention_policy_source) = ''
                  )
            """,
            (ARTIFACT_RETENTION_POLICY_NO_EXPIRY,),
        )
        connection.execute(
            """
            UPDATE artifact_index
            SET retention_class_source = ?
            WHERE retention_class_source IS NULL
               OR TRIM(retention_class_source) = ''
            """,
            (ARTIFACT_RETENTION_CLASS_SOURCE_LEGACY_COMPAT,),
        )

    def _backfill_artifact_storage_defaults(self, connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            UPDATE artifact_index
            SET storage_backend = 'LOCAL_FILE'
            WHERE storage_backend IS NULL
               OR TRIM(storage_backend) = ''
            """
        )
        connection.execute(
            """
            UPDATE artifact_index
            SET storage_delete_status = CASE
                    WHEN storage_deleted_at IS NOT NULL THEN 'DELETED'
                    WHEN materialization_status = 'MATERIALIZED'
                         AND (
                                (storage_relpath IS NOT NULL AND TRIM(storage_relpath) != '')
                                OR (storage_object_key IS NOT NULL AND TRIM(storage_object_key) != '')
                             )
                        THEN 'PRESENT'
                    ELSE 'DELETED'
                END
            WHERE storage_delete_status IS NULL
               OR TRIM(storage_delete_status) = ''
            """
        )

    def _backfill_scope_defaults(self, connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            UPDATE workflow_projection
            SET tenant_id = ?
            WHERE tenant_id IS NULL OR TRIM(tenant_id) = ''
            """,
            (DEFAULT_TENANT_ID,),
        )
        connection.execute(
            """
            UPDATE workflow_projection
            SET workspace_id = ?
            WHERE workspace_id IS NULL OR TRIM(workspace_id) = ''
            """,
            (DEFAULT_WORKSPACE_ID,),
        )
        connection.execute(
            """
            UPDATE ticket_projection
            SET tenant_id = COALESCE(
                (
                    SELECT CASE
                        WHEN workflow_projection.tenant_id IS NULL OR TRIM(workflow_projection.tenant_id) = ''
                            THEN NULL
                        ELSE workflow_projection.tenant_id
                    END
                    FROM workflow_projection
                    WHERE workflow_projection.workflow_id = ticket_projection.workflow_id
                ),
                ?
            )
            WHERE tenant_id IS NULL OR TRIM(tenant_id) = ''
            """,
            (DEFAULT_TENANT_ID,),
        )
        connection.execute(
            """
            UPDATE ticket_projection
            SET workspace_id = COALESCE(
                (
                    SELECT CASE
                        WHEN workflow_projection.workspace_id IS NULL OR TRIM(workflow_projection.workspace_id) = ''
                            THEN NULL
                        ELSE workflow_projection.workspace_id
                    END
                    FROM workflow_projection
                    WHERE workflow_projection.workflow_id = ticket_projection.workflow_id
                ),
                ?
            )
            WHERE workspace_id IS NULL OR TRIM(workspace_id) = ''
            """,
            (DEFAULT_WORKSPACE_ID,),
        )
        connection.execute(
            """
            UPDATE worker_bootstrap_state
            SET tenant_id = ?
            WHERE tenant_id IS NULL OR TRIM(tenant_id) = ''
            """,
            (DEFAULT_TENANT_ID,),
        )
        connection.execute(
            """
            UPDATE worker_bootstrap_state
            SET workspace_id = ?
            WHERE workspace_id IS NULL OR TRIM(workspace_id) = ''
            """,
            (DEFAULT_WORKSPACE_ID,),
        )
        connection.execute(
            """
            UPDATE worker_session
            SET tenant_id = COALESCE(
                (
                    SELECT CASE
                        WHEN worker_bootstrap_state.tenant_id IS NULL OR TRIM(worker_bootstrap_state.tenant_id) = ''
                            THEN NULL
                        ELSE worker_bootstrap_state.tenant_id
                    END
                    FROM worker_bootstrap_state
                    WHERE worker_bootstrap_state.worker_id = worker_session.worker_id
                ),
                ?
            )
            WHERE tenant_id IS NULL OR TRIM(tenant_id) = ''
            """,
            (DEFAULT_TENANT_ID,),
        )
        connection.execute(
            """
            UPDATE worker_session
            SET workspace_id = COALESCE(
                (
                    SELECT CASE
                        WHEN worker_bootstrap_state.workspace_id IS NULL OR TRIM(worker_bootstrap_state.workspace_id) = ''
                            THEN NULL
                        ELSE worker_bootstrap_state.workspace_id
                    END
                    FROM worker_bootstrap_state
                    WHERE worker_bootstrap_state.worker_id = worker_session.worker_id
                ),
                ?
            )
            WHERE workspace_id IS NULL OR TRIM(workspace_id) = ''
            """,
            (DEFAULT_WORKSPACE_ID,),
        )
        connection.execute(
            """
            UPDATE worker_delivery_grant
            SET tenant_id = COALESCE(
                (
                    SELECT CASE
                        WHEN worker_session.tenant_id IS NULL OR TRIM(worker_session.tenant_id) = ''
                            THEN NULL
                        ELSE worker_session.tenant_id
                    END
                    FROM worker_session
                    WHERE worker_session.session_id = worker_delivery_grant.session_id
                ),
                (
                    SELECT CASE
                        WHEN ticket_projection.tenant_id IS NULL OR TRIM(ticket_projection.tenant_id) = ''
                            THEN NULL
                        ELSE ticket_projection.tenant_id
                    END
                    FROM ticket_projection
                    WHERE ticket_projection.ticket_id = worker_delivery_grant.ticket_id
                ),
                ?
            )
            WHERE tenant_id IS NULL OR TRIM(tenant_id) = ''
            """,
            (DEFAULT_TENANT_ID,),
        )
        connection.execute(
            """
            UPDATE worker_delivery_grant
            SET workspace_id = COALESCE(
                (
                    SELECT CASE
                        WHEN worker_session.workspace_id IS NULL OR TRIM(worker_session.workspace_id) = ''
                            THEN NULL
                        ELSE worker_session.workspace_id
                    END
                    FROM worker_session
                    WHERE worker_session.session_id = worker_delivery_grant.session_id
                ),
                (
                    SELECT CASE
                        WHEN ticket_projection.workspace_id IS NULL OR TRIM(ticket_projection.workspace_id) = ''
                            THEN NULL
                        ELSE ticket_projection.workspace_id
                    END
                    FROM ticket_projection
                    WHERE ticket_projection.ticket_id = worker_delivery_grant.ticket_id
                ),
                ?
            )
            WHERE workspace_id IS NULL OR TRIM(workspace_id) = ''
            """,
            (DEFAULT_WORKSPACE_ID,),
        )

    def _bootstrap_employee_events(self, connection: sqlite3.Connection) -> None:
        existing_employee_events = connection.execute(
            "SELECT COUNT(*) AS total FROM events WHERE event_type = ?",
            (EVENT_EMPLOYEE_HIRED,),
        ).fetchone()
        if existing_employee_events is not None and int(existing_employee_events["total"]) > 0:
            return

        legacy_rows = connection.execute(
            "SELECT * FROM employee_projection ORDER BY employee_id ASC"
        ).fetchall()
        bootstrap_employees: list[dict[str, Any]] = []
        if legacy_rows:
            for row in legacy_rows:
                employee = self._convert_employee_projection_row(row)
                bootstrap_employees.append(
                    {
                        "employee_id": employee["employee_id"],
                        "role_type": employee["role_type"],
                        "skill_profile": dict(employee.get("skill_profile_json") or {}),
                        "personality_profile": dict(employee.get("personality_profile_json") or {}),
                        "aesthetic_profile": dict(employee.get("aesthetic_profile_json") or {}),
                        "state": employee["state"],
                        "board_approved": bool(employee.get("board_approved")),
                        "provider_id": employee.get("provider_id"),
                        "role_profile_refs": list(employee.get("role_profile_refs") or []),
                        "occurred_at": employee.get("updated_at") or now_local(),
                    }
                )
        else:
            seeded_at = now_local()
            for employee in DEFAULT_EMPLOYEE_ROSTER:
                bootstrap_employees.append(
                    {
                        "employee_id": employee["employee_id"],
                        "role_type": employee["role_type"],
                        "skill_profile": dict(employee["skill_profile_json"]),
                        "personality_profile": dict(employee["personality_profile_json"]),
                        "aesthetic_profile": dict(employee["aesthetic_profile_json"]),
                        "state": employee["state"],
                        "board_approved": bool(employee["board_approved"]),
                        "provider_id": employee.get("provider_id"),
                        "role_profile_refs": list(employee["role_profile_refs_json"]),
                        "occurred_at": seeded_at,
                    }
                )

        for employee in bootstrap_employees:
            self.insert_event(
                connection,
                event_type=EVENT_EMPLOYEE_HIRED,
                actor_type="system",
                actor_id="system",
                workflow_id=None,
                idempotency_key=f"employee-bootstrap:{employee['employee_id']}",
                causation_id=None,
                correlation_id=None,
                payload={
                    "employee_id": employee["employee_id"],
                    "role_type": employee["role_type"],
                    "skill_profile": employee["skill_profile"],
                    "personality_profile": employee["personality_profile"],
                    "aesthetic_profile": employee["aesthetic_profile"],
                    "state": employee["state"],
                    "board_approved": employee["board_approved"],
                    "provider_id": employee.get("provider_id"),
                    "role_profile_refs": employee["role_profile_refs"],
                    "bootstrap_source": "legacy_projection_backfill" if legacy_rows else "default_roster_seed",
                },
                occurred_at=employee["occurred_at"],
            )

    def _list_employee_projections(
        self,
        connection: sqlite3.Connection,
        *,
        states: list[str] | None = None,
        board_approved_only: bool = False,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if states:
            placeholders = ", ".join("?" for _ in states)
            clauses.append(f"state IN ({placeholders})")
            params.extend(states)
        if board_approved_only:
            clauses.append("board_approved = 1")

        where_clause = ""
        if clauses:
            where_clause = "WHERE " + " AND ".join(clauses)

        rows = connection.execute(
            f"""
            SELECT * FROM employee_projection
            {where_clause}
            ORDER BY employee_id ASC
            """,
            tuple(params),
        ).fetchall()
        return [self._convert_employee_projection_row(row) for row in rows]
