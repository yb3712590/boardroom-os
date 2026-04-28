from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from app.contracts.advisory import BoardAdvisoryAnalysisRun, BoardAdvisorySession
from app.config import get_settings
from app.contracts.governance import GovernanceProfile
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
    EVENT_ARTIFACT_IMPORTED,
    EVENT_SCHEDULER_ORCHESTRATION_RECORDED,
    EVENT_CIRCUIT_BREAKER_CLOSED,
    EVENT_CIRCUIT_BREAKER_OPENED,
    NODE_STATUS_BLOCKED_FOR_BOARD_REVIEW,
    NODE_STATUS_COMPLETED,
    EVENT_BOARD_DIRECTIVE_RECEIVED,
    EVENT_BOARD_ADVISORY_SESSION_OPENED,
    EVENT_BOARD_REVIEW_APPROVED,
    EVENT_BOARD_REVIEW_REJECTED,
    EVENT_BOARD_REVIEW_REQUIRED,
    EVENT_MEETING_CONCLUDED,
    EVENT_MEETING_REQUESTED,
    EVENT_MEETING_ROUND_COMPLETED,
    EVENT_MEETING_STARTED,
    EVENT_INCIDENT_CLOSED,
    EVENT_INCIDENT_RECOVERY_STARTED,
    EVENT_INCIDENT_OPENED,
    EVENT_SYSTEM_INITIALIZED,
    EVENT_PROVIDER_ATTEMPT_FINISHED,
    EVENT_PROVIDER_ATTEMPT_STARTED,
    EVENT_PROVIDER_FAILOVER_SELECTED,
    EVENT_PROVIDER_FIRST_TOKEN_RECEIVED,
    EVENT_PROVIDER_RETRY_SCHEDULED,
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
    SYSTEM_INITIALIZED_KEY,
)
from app.core.ids import new_prefixed_id
from app.core.persona_profiles import (
    build_default_employee_roster,
    normalize_employee_projection_profiles,
)
from app.core.board_advisory import (
    build_board_advisory_session,
    review_pack_requires_board_advisory,
)
from app.core.graph_identity import GraphIdentityResolutionError, resolve_ticket_graph_identity
from app.core.review_subjects import (
    resolve_graph_only_review_subject_execution_identity,
    resolve_review_subject_execution_identity,
)
from app.core.versioning import (
    build_compiled_context_bundle_version_ref,
    build_compiled_execution_package_version_ref,
    build_compile_manifest_version_ref,
    resolve_workflow_graph_version,
    split_versioned_ref,
    validate_supersedes_ref,
)
from app.core.reducer import (
    rebuild_employee_projections,
    rebuild_incident_projections,
    rebuild_node_projections,
    rebuild_process_asset_index,
    rebuild_runtime_node_projections,
    rebuild_ticket_projections,
    rebuild_workflow_projections,
)
from app.core.time import now_local
from app.db.schema import TABLE_SCHEMA_SQL

RETRIEVAL_REVIEW_SUMMARY_FTS = "retrieval_review_summary_fts"
RETRIEVAL_INCIDENT_SUMMARY_FTS = "retrieval_incident_summary_fts"
RETRIEVAL_ARTIFACT_SUMMARY_FTS = "retrieval_artifact_summary_fts"


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
            self._ensure_runtime_node_projection_shape(connection)
            self._ensure_planned_placeholder_projection_shape(connection)
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
            self._ensure_meeting_projection_shape(connection)
            self._ensure_compiled_context_bundle_shape(connection)
            self._ensure_compile_manifest_shape(connection)
            self._ensure_compiled_execution_package_shape(connection)
            self._ensure_process_asset_index_shape(connection)
            self._ensure_governance_profile_shape(connection)
            self._ensure_board_advisory_session_shape(connection)
            self._ensure_board_advisory_analysis_run_shape(connection)
            self._ensure_ceo_shadow_run_shape(connection)
            self._ensure_artifact_index_shape(connection)
            self._ensure_artifact_upload_session_shape(connection)
            self._ensure_artifact_upload_part_shape(connection)
            self._ensure_retrieval_review_summary_fts(connection)
            self._ensure_retrieval_incident_summary_fts(connection)
            self._ensure_retrieval_artifact_summary_fts(connection)
            self._backfill_scope_defaults(connection)
            self._backfill_artifact_storage_defaults(connection)
            self._backfill_artifact_retention_defaults(connection)
            self._ensure_system_initialized_event(connection)
            self._bootstrap_employee_events(connection)
            employee_events = self.list_all_events(connection)
            self.replace_employee_projections(
                connection,
                rebuild_employee_projections(employee_events),
            )
            self.replace_process_asset_index(
                connection,
                rebuild_process_asset_index(employee_events),
            )
            self._rebuild_retrieval_review_summary_fts(connection)
            self._rebuild_retrieval_incident_summary_fts(connection)
            self._rebuild_retrieval_artifact_summary_fts(connection)
        self._initialized = True

    def _ensure_system_initialized_event(self, connection: sqlite3.Connection) -> None:
        existing = self.get_event_by_idempotency_key(connection, SYSTEM_INITIALIZED_KEY)
        if existing is not None:
            return
        self.insert_event(
            connection,
            event_type=EVENT_SYSTEM_INITIALIZED,
            actor_type="system",
            actor_id="system",
            workflow_id=None,
            idempotency_key=SYSTEM_INITIALIZED_KEY,
            causation_id=None,
            correlation_id=None,
            payload={"status": "initialized"},
            occurred_at=now_local(),
        )

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
                    workflow_profile,
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
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    projection["workflow_id"],
                    projection["title"],
                    projection["north_star_goal"],
                    projection.get("workflow_profile", "STANDARD"),
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

    def replace_runtime_node_projections(
        self,
        connection: sqlite3.Connection,
        projections: list[dict[str, Any]],
    ) -> None:
        self._ensure_runtime_node_projection_shape(connection)
        connection.execute("DELETE FROM runtime_node_projection")
        for projection in projections:
            connection.execute(
                """
                INSERT INTO runtime_node_projection (
                    workflow_id,
                    graph_node_id,
                    node_id,
                    runtime_node_id,
                    latest_ticket_id,
                    status,
                    blocking_reason_code,
                    graph_version,
                    updated_at,
                    version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    projection["workflow_id"],
                    projection["graph_node_id"],
                    projection["node_id"],
                    projection["runtime_node_id"],
                    projection["latest_ticket_id"],
                    projection["status"],
                    projection.get("blocking_reason_code"),
                    projection.get("graph_version") or resolve_workflow_graph_version(
                        self,
                        str(projection["workflow_id"]),
                        connection=connection,
                    ),
                    projection["updated_at"],
                    projection["version"],
                ),
            )

    def replace_planned_placeholder_projections(
        self,
        connection: sqlite3.Connection,
        projections: list[dict[str, Any]],
    ) -> None:
        connection.execute("DELETE FROM planned_placeholder_projection")
        for projection in projections:
            connection.execute(
                """
                INSERT INTO planned_placeholder_projection (
                    workflow_id,
                    node_id,
                    graph_node_id,
                    graph_version,
                    status,
                    reason_code,
                    open_incident_id,
                    materialization_hint,
                    updated_at,
                    version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    projection["workflow_id"],
                    projection["node_id"],
                    projection["graph_node_id"],
                    projection["graph_version"],
                    projection["status"],
                    projection.get("reason_code"),
                    projection.get("open_incident_id"),
                    projection.get("materialization_hint"),
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
        self._rebuild_retrieval_incident_summary_fts(connection)

    def replace_process_asset_index(
        self,
        connection: sqlite3.Connection,
        projections: list[dict[str, Any]],
    ) -> None:
        connection.execute("DELETE FROM process_asset_index")
        for projection in projections:
            connection.execute(
                """
                INSERT INTO process_asset_index (
                    process_asset_ref,
                    canonical_ref,
                    version_int,
                    supersedes_ref,
                    process_asset_kind,
                    workflow_id,
                    producer_ticket_id,
                    producer_node_id,
                    graph_version,
                    content_hash,
                    visibility_status,
                    linked_process_asset_refs_json,
                    summary,
                    consumable_by_json,
                    source_metadata_json,
                    updated_at,
                    version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    projection["process_asset_ref"],
                    projection["canonical_ref"],
                    projection.get("version_int"),
                    projection.get("supersedes_ref"),
                    projection["process_asset_kind"],
                    projection.get("workflow_id"),
                    projection.get("producer_ticket_id"),
                    projection.get("producer_node_id"),
                    projection.get("graph_version"),
                    projection.get("content_hash"),
                    projection.get("visibility_status", "CONSUMABLE"),
                    json.dumps(projection.get("linked_process_asset_refs") or [], sort_keys=True),
                    projection.get("summary"),
                    json.dumps(projection.get("consumable_by") or [], sort_keys=True),
                    json.dumps(projection.get("source_metadata") or {}, sort_keys=True),
                    projection["updated_at"],
                    projection["version"],
                ),
            )

    def refresh_projections(self, connection: sqlite3.Connection) -> None:
        from app.core.planned_placeholder_projection import rebuild_planned_placeholder_projections

        events = self.list_all_events(connection)
        self.replace_workflow_projections(connection, rebuild_workflow_projections(events))
        self.replace_ticket_projections(connection, rebuild_ticket_projections(events))
        self.replace_node_projections(connection, rebuild_node_projections(events))
        self.replace_runtime_node_projections(connection, rebuild_runtime_node_projections(events))
        self.replace_employee_projections(connection, rebuild_employee_projections(events))
        self.replace_incident_projections(connection, rebuild_incident_projections(events))
        self.replace_process_asset_index(connection, rebuild_process_asset_index(events))
        self.replace_planned_placeholder_projections(
            connection,
            rebuild_planned_placeholder_projections(self, connection=connection),
        )

    def list_process_assets_by_producer_ticket(
        self,
        producer_ticket_id: str,
        *,
        process_asset_kinds: set[str] | None = None,
        visibility_statuses: set[str] | None = None,
        connection: sqlite3.Connection | None = None,
    ) -> list[dict[str, Any]]:
        clauses = ["producer_ticket_id = ?"]
        params: list[Any] = [producer_ticket_id]
        if process_asset_kinds:
            placeholders = ", ".join("?" for _ in process_asset_kinds)
            clauses.append(f"process_asset_kind IN ({placeholders})")
            params.extend(sorted(process_asset_kinds))
        if visibility_statuses:
            placeholders = ", ".join("?" for _ in visibility_statuses)
            clauses.append(f"visibility_status IN ({placeholders})")
            params.extend(sorted(visibility_statuses))
        query = f"""
            SELECT *
            FROM process_asset_index
            WHERE {' AND '.join(clauses)}
            ORDER BY
                CASE process_asset_kind
                    WHEN 'SOURCE_CODE_DELIVERY' THEN 0
                    WHEN 'EVIDENCE_PACK' THEN 1
                    WHEN 'GOVERNANCE_DOCUMENT' THEN 2
                    WHEN 'MEETING_DECISION_RECORD' THEN 3
                    WHEN 'CLOSEOUT_SUMMARY' THEN 4
                    WHEN 'ARTIFACT' THEN 9
                    ELSE 5
                END,
                process_asset_ref ASC
        """
        if connection is not None:
            rows = connection.execute(query, params).fetchall()
            return [self._convert_process_asset_index_row(row) for row in rows]
        self.initialize()
        with self.connection() as owned_connection:
            rows = owned_connection.execute(query, params).fetchall()
            return [self._convert_process_asset_index_row(row) for row in rows]

    def list_process_assets_by_workflow(
        self,
        workflow_id: str,
        *,
        process_asset_kinds: set[str] | None = None,
        visibility_statuses: set[str] | None = None,
        connection: sqlite3.Connection | None = None,
    ) -> list[dict[str, Any]]:
        clauses = ["workflow_id = ?"]
        params: list[Any] = [workflow_id]
        if process_asset_kinds:
            placeholders = ", ".join("?" for _ in process_asset_kinds)
            clauses.append(f"process_asset_kind IN ({placeholders})")
            params.extend(sorted(process_asset_kinds))
        if visibility_statuses:
            placeholders = ", ".join("?" for _ in visibility_statuses)
            clauses.append(f"visibility_status IN ({placeholders})")
            params.extend(sorted(visibility_statuses))
        query = f"""
            SELECT *
            FROM process_asset_index
            WHERE {' AND '.join(clauses)}
            ORDER BY producer_node_id ASC, version ASC, process_asset_ref ASC
        """
        if connection is not None:
            rows = connection.execute(query, params).fetchall()
            return [self._convert_process_asset_index_row(row) for row in rows]
        self.initialize()
        with self.connection() as owned_connection:
            rows = owned_connection.execute(query, params).fetchall()
            return [self._convert_process_asset_index_row(row) for row in rows]

    def get_process_asset_index_entry(
        self,
        process_asset_ref: str,
        *,
        connection: sqlite3.Connection | None = None,
    ) -> dict[str, Any] | None:
        base_ref, version_int = split_versioned_ref(process_asset_ref)
        if version_int is None:
            query = """
                SELECT *
                FROM process_asset_index
                WHERE process_asset_ref = ? OR canonical_ref = ? OR canonical_ref LIKE ?
                ORDER BY version_int DESC, version DESC
                LIMIT 1
            """
            params = (process_asset_ref, process_asset_ref, f"{base_ref}@%")
        else:
            query = """
                SELECT *
                FROM process_asset_index
                WHERE process_asset_ref = ? OR canonical_ref = ?
                LIMIT 1
            """
            params = (process_asset_ref, process_asset_ref)
        if connection is not None:
            row = connection.execute(query, params).fetchone()
            return None if row is None else self._convert_process_asset_index_row(row)
        self.initialize()
        with self.connection() as owned_connection:
            row = owned_connection.execute(query, params).fetchone()
            return None if row is None else self._convert_process_asset_index_row(row)

    def get_default_consumable_process_asset(
        self,
        *,
        workflow_id: str,
        producer_node_id: str,
        process_asset_kind: str,
        graph_version: str | None = None,
        connection: sqlite3.Connection | None = None,
    ) -> dict[str, Any] | None:
        clauses = [
            "workflow_id = ?",
            "producer_node_id = ?",
            "process_asset_kind = ?",
            "visibility_status = 'CONSUMABLE'",
        ]
        params: list[Any] = [workflow_id, producer_node_id, process_asset_kind]
        if graph_version is not None:
            clauses.append("graph_version = ?")
            params.append(graph_version)
        query = f"""
            SELECT *
            FROM process_asset_index
            WHERE {' AND '.join(clauses)}
            ORDER BY version DESC, process_asset_ref DESC
            LIMIT 1
        """
        if connection is not None:
            row = connection.execute(query, params).fetchone()
            return None if row is None else self._convert_process_asset_index_row(row)
        self.initialize()
        with self.connection() as owned_connection:
            row = owned_connection.execute(query, params).fetchone()
            return None if row is None else self._convert_process_asset_index_row(row)

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

    def get_latest_incident_for_ticket(
        self,
        ticket_id: str,
        *,
        statuses: list[str] | tuple[str, ...] | None = None,
        connection: sqlite3.Connection | None = None,
    ) -> dict[str, Any] | None:
        normalized_statuses = [str(status).strip() for status in list(statuses or []) if str(status).strip()]
        query = """
            SELECT * FROM incident_projection
            WHERE ticket_id = ?
        """
        params: list[Any] = [ticket_id]
        if normalized_statuses:
            placeholders = ", ".join("?" for _ in normalized_statuses)
            query += f" AND status IN ({placeholders})"
            params.extend(normalized_statuses)
        query += """
            ORDER BY updated_at DESC, opened_at DESC, incident_id DESC
            LIMIT 1
        """
        if connection is not None:
            row = connection.execute(query, tuple(params)).fetchone()
            if row is None:
                return None
            return self._convert_incident_projection_row(row)

        self.initialize()
        with self.connection() as owned_connection:
            row = owned_connection.execute(query, tuple(params)).fetchone()
            if row is None:
                return None
            return self._convert_incident_projection_row(row)

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

    def get_runtime_node_projection(
        self,
        workflow_id: str,
        graph_node_id: str,
        connection: sqlite3.Connection | None = None,
    ) -> dict[str, Any] | None:
        query = """
            SELECT * FROM runtime_node_projection
            WHERE workflow_id = ? AND graph_node_id = ?
        """
        params = (workflow_id, graph_node_id)
        if connection is not None:
            row = connection.execute(query, params).fetchone()
            if row is None:
                return None
            return self._convert_runtime_node_projection_row(row)

        self.initialize()
        with self.connection() as owned_connection:
            row = owned_connection.execute(query, params).fetchone()
            if row is None:
                return None
            return self._convert_runtime_node_projection_row(row)

    def list_runtime_node_projections(
        self,
        workflow_id: str | None = None,
        connection: sqlite3.Connection | None = None,
    ) -> list[dict[str, Any]]:
        query = """
            SELECT * FROM runtime_node_projection
        """
        params: tuple[Any, ...] = ()
        if workflow_id is not None:
            query += " WHERE workflow_id = ?"
            params = (workflow_id,)
        query += " ORDER BY workflow_id ASC, graph_node_id ASC"
        if connection is not None:
            rows = connection.execute(query, params).fetchall()
            return [self._convert_runtime_node_projection_row(row) for row in rows]

        self.initialize()
        with self.connection() as owned_connection:
            rows = owned_connection.execute(query, params).fetchall()
            return [self._convert_runtime_node_projection_row(row) for row in rows]

    def get_planned_placeholder_projection(
        self,
        workflow_id: str,
        node_id: str,
        connection: sqlite3.Connection | None = None,
    ) -> dict[str, Any] | None:
        query = """
            SELECT * FROM planned_placeholder_projection
            WHERE workflow_id = ? AND node_id = ?
        """
        params = (workflow_id, node_id)
        if connection is not None:
            row = connection.execute(query, params).fetchone()
            if row is None:
                return None
            return self._convert_planned_placeholder_projection_row(row)

        self.initialize()
        with self.connection() as owned_connection:
            row = owned_connection.execute(query, params).fetchone()
            if row is None:
                return None
            return self._convert_planned_placeholder_projection_row(row)

    def list_planned_placeholder_projections(
        self,
        workflow_id: str | None = None,
        connection: sqlite3.Connection | None = None,
    ) -> list[dict[str, Any]]:
        query = """
            SELECT * FROM planned_placeholder_projection
        """
        params: tuple[Any, ...] = ()
        if workflow_id is not None:
            query += " WHERE workflow_id = ?"
            params = (workflow_id,)
        query += " ORDER BY workflow_id ASC, node_id ASC"
        if connection is not None:
            rows = connection.execute(query, params).fetchall()
            return [self._convert_planned_placeholder_projection_row(row) for row in rows]

        self.initialize()
        with self.connection() as owned_connection:
            rows = owned_connection.execute(query, params).fetchall()
            return [self._convert_planned_placeholder_projection_row(row) for row in rows]

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
        preferred_provider_id: str | None,
        preferred_model: str | None,
        actual_provider_id: str | None,
        actual_model: str | None,
        selection_reason: str | None,
        policy_reason: str | None,
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
                preferred_provider_id,
                preferred_model,
                actual_provider_id,
                actual_model,
                selection_reason,
                policy_reason,
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
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                preferred_provider_id,
                preferred_model,
                actual_provider_id,
                actual_model,
                selection_reason,
                policy_reason,
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
        existing = self.get_compiled_context_bundle_by_compile_request_id(
            bundle.meta.compile_request_id,
            connection=connection,
        )
        if existing is not None:
            bundle.meta.version_ref = existing.get("version_ref")
            bundle.meta.version_int = existing.get("version_int")
            bundle.meta.supersedes_ref = existing.get("supersedes_ref")
            return
        version_int = self._next_version_int(
            connection,
            table_name="compiled_context_bundle",
            ticket_id=bundle.meta.ticket_id,
        )
        version_ref = build_compiled_context_bundle_version_ref(
            bundle.meta.ticket_id,
            bundle.meta.attempt_no,
            version_int,
        )
        supersedes_ref = self._previous_version_ref(
            connection,
            table_name="compiled_context_bundle",
            ticket_id=bundle.meta.ticket_id,
        )
        validate_supersedes_ref(
            canonical_ref=version_ref,
            version_int=version_int,
            supersedes_ref=supersedes_ref,
        )
        bundle.meta.version_ref = version_ref
        bundle.meta.version_int = version_int
        bundle.meta.supersedes_ref = supersedes_ref
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
                version_ref,
                version_int,
                supersedes_ref,
                payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                bundle.meta.bundle_id,
                bundle.meta.compile_request_id,
                bundle.meta.ticket_id,
                bundle.meta.workflow_id,
                bundle.meta.node_id,
                bundle.meta.compiler_version,
                bundle.meta.compiled_at.isoformat(),
                version_ref,
                version_ref,
                version_int,
                supersedes_ref,
                json.dumps(payload, sort_keys=True),
            ),
        )

    def save_compile_manifest(
        self,
        connection: sqlite3.Connection,
        manifest: CompileManifest,
    ) -> None:
        existing = self.get_compile_manifest_by_compile_request_id(
            manifest.compile_meta.compile_request_id,
            connection=connection,
        )
        if existing is not None:
            manifest.compile_meta.version_ref = existing.get("version_ref")
            manifest.compile_meta.version_int = existing.get("version_int")
            manifest.compile_meta.supersedes_ref = existing.get("supersedes_ref")
            return
        version_int = self._next_version_int(
            connection,
            table_name="compile_manifest",
            ticket_id=manifest.compile_meta.ticket_id,
        )
        version_ref = build_compile_manifest_version_ref(
            manifest.compile_meta.ticket_id,
            manifest.compile_meta.attempt_no,
            version_int,
        )
        supersedes_ref = self._previous_version_ref(
            connection,
            table_name="compile_manifest",
            ticket_id=manifest.compile_meta.ticket_id,
        )
        validate_supersedes_ref(
            canonical_ref=version_ref,
            version_int=version_int,
            supersedes_ref=supersedes_ref,
        )
        manifest.compile_meta.version_ref = version_ref
        manifest.compile_meta.version_int = version_int
        manifest.compile_meta.supersedes_ref = supersedes_ref
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
                version_ref,
                version_int,
                supersedes_ref,
                payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                version_ref,
                version_ref,
                version_int,
                supersedes_ref,
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
        existing = self.get_compiled_execution_package(
            execution_package.meta.compile_request_id,
            connection=connection,
        )
        if existing is not None:
            execution_package.meta.version_ref = existing.get("version_ref")
            execution_package.meta.version_int = existing.get("version_int")
            execution_package.meta.supersedes_ref = existing.get("supersedes_ref")
            return
        version_int = self._next_version_int(
            connection,
            table_name="compiled_execution_package",
            ticket_id=execution_package.meta.ticket_id,
        )
        version_ref = build_compiled_execution_package_version_ref(
            execution_package.meta.ticket_id,
            execution_package.meta.attempt_no,
            version_int,
        )
        supersedes_ref = self._previous_version_ref(
            connection,
            table_name="compiled_execution_package",
            ticket_id=execution_package.meta.ticket_id,
        )
        validate_supersedes_ref(
            canonical_ref=version_ref,
            version_int=version_int,
            supersedes_ref=supersedes_ref,
        )
        execution_package.meta.version_ref = version_ref
        execution_package.meta.version_int = version_int
        execution_package.meta.supersedes_ref = supersedes_ref
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
                version_ref,
                version_int,
                supersedes_ref,
                payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                execution_package.meta.compile_request_id,
                execution_package.meta.ticket_id,
                execution_package.meta.workflow_id,
                execution_package.meta.node_id,
                execution_package.meta.compiler_version,
                compiled_at.isoformat(),
                version_ref,
                version_ref,
                version_int,
                supersedes_ref,
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

    def get_compiled_context_bundle_by_compile_request_id(
        self,
        compile_request_id: str,
        connection: sqlite3.Connection | None = None,
    ) -> dict[str, Any] | None:
        query = """
            SELECT * FROM compiled_context_bundle
            WHERE compile_request_id = ?
            ORDER BY version_int DESC, compiled_at DESC, bundle_id DESC
            LIMIT 1
        """
        if connection is not None:
            row = connection.execute(query, (compile_request_id,)).fetchone()
            return None if row is None else self._convert_compiled_context_bundle_row(row)

        self.initialize()
        with self.connection() as owned_connection:
            row = owned_connection.execute(query, (compile_request_id,)).fetchone()
            return None if row is None else self._convert_compiled_context_bundle_row(row)

    def get_latest_compiled_context_bundle_by_ticket(
        self,
        ticket_id: str,
        connection: sqlite3.Connection | None = None,
    ) -> dict[str, Any] | None:
        query = """
            SELECT * FROM compiled_context_bundle
            WHERE ticket_id = ?
            ORDER BY version_int DESC, compiled_at DESC, bundle_id DESC
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

    def get_compile_manifest_by_compile_request_id(
        self,
        compile_request_id: str,
        connection: sqlite3.Connection | None = None,
    ) -> dict[str, Any] | None:
        query = """
            SELECT * FROM compile_manifest
            WHERE compile_request_id = ?
            ORDER BY version_int DESC, compiled_at DESC, compile_id DESC
            LIMIT 1
        """
        if connection is not None:
            row = connection.execute(query, (compile_request_id,)).fetchone()
            return None if row is None else self._convert_compile_manifest_row(row)

        self.initialize()
        with self.connection() as owned_connection:
            row = owned_connection.execute(query, (compile_request_id,)).fetchone()
            return None if row is None else self._convert_compile_manifest_row(row)

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
            ORDER BY version_int DESC, compiled_at DESC, compile_id DESC
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
            ORDER BY version_int DESC, compiled_at DESC, compile_request_id DESC
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

    def get_compiled_execution_package_version(
        self,
        ticket_id: str,
        version_int: int,
        connection: sqlite3.Connection | None = None,
    ) -> dict[str, Any] | None:
        query = """
            SELECT * FROM compiled_execution_package
            WHERE ticket_id = ? AND version_int = ?
            LIMIT 1
        """
        params = (ticket_id, int(version_int))
        if connection is not None:
            row = connection.execute(query, params).fetchone()
            return None if row is None else self._convert_compiled_execution_package_row(row)

        self.initialize()
        with self.connection() as owned_connection:
            row = owned_connection.execute(query, params).fetchone()
            return None if row is None else self._convert_compiled_execution_package_row(row)

    def get_compiled_context_bundle_version(
        self,
        ticket_id: str,
        version_int: int,
        connection: sqlite3.Connection | None = None,
    ) -> dict[str, Any] | None:
        query = """
            SELECT * FROM compiled_context_bundle
            WHERE ticket_id = ? AND version_int = ?
            LIMIT 1
        """
        params = (ticket_id, int(version_int))
        if connection is not None:
            row = connection.execute(query, params).fetchone()
            return None if row is None else self._convert_compiled_context_bundle_row(row)

        self.initialize()
        with self.connection() as owned_connection:
            row = owned_connection.execute(query, params).fetchone()
            return None if row is None else self._convert_compiled_context_bundle_row(row)

    def get_compile_manifest_version(
        self,
        ticket_id: str,
        version_int: int,
        connection: sqlite3.Connection | None = None,
    ) -> dict[str, Any] | None:
        query = """
            SELECT * FROM compile_manifest
            WHERE ticket_id = ? AND version_int = ?
            LIMIT 1
        """
        params = (ticket_id, int(version_int))
        if connection is not None:
            row = connection.execute(query, params).fetchone()
            return None if row is None else self._convert_compile_manifest_row(row)

        self.initialize()
        with self.connection() as owned_connection:
            row = owned_connection.execute(query, params).fetchone()
            return None if row is None else self._convert_compile_manifest_row(row)

    def save_governance_profile(
        self,
        connection: sqlite3.Connection,
        profile: GovernanceProfile,
    ) -> GovernanceProfile:
        if profile.supersedes_ref is not None:
            previous = connection.execute(
                """
                SELECT profile_id
                FROM governance_profile
                WHERE workflow_id = ? AND profile_id = ?
                LIMIT 1
                """,
                (profile.workflow_id, profile.supersedes_ref),
            ).fetchone()
            if previous is None:
                raise ValueError("governance profile supersedes_ref must reference an existing row.")
        elif int(profile.version_int) != 1:
            raise ValueError("governance profile supersedes_ref is required when version_int > 1.")

        connection.execute(
            """
            INSERT INTO governance_profile (
                profile_id,
                workflow_id,
                approval_mode,
                audit_mode,
                auto_approval_scope_json,
                expert_review_targets_json,
                audit_materialization_policy_json,
                source_ref,
                supersedes_ref,
                effective_from_event,
                version_int
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                profile.profile_id,
                profile.workflow_id,
                profile.approval_mode,
                profile.audit_mode,
                json.dumps(profile.auto_approval_scope, sort_keys=True),
                json.dumps(profile.expert_review_targets, sort_keys=True),
                json.dumps(profile.audit_materialization_policy, sort_keys=True),
                profile.source_ref,
                profile.supersedes_ref,
                profile.effective_from_event,
                int(profile.version_int),
            ),
        )
        return profile

    def get_latest_governance_profile(
        self,
        workflow_id: str,
        connection: sqlite3.Connection | None = None,
    ) -> dict[str, Any] | None:
        query = """
            SELECT * FROM governance_profile
            WHERE workflow_id = ?
            ORDER BY version_int DESC, profile_id DESC
            LIMIT 1
        """
        if connection is not None:
            row = connection.execute(query, (workflow_id,)).fetchone()
            return None if row is None else self._convert_governance_profile_row(row)

        self.initialize()
        with self.connection() as owned_connection:
            row = owned_connection.execute(query, (workflow_id,)).fetchone()
            return None if row is None else self._convert_governance_profile_row(row)

    def list_governance_profiles(
        self,
        workflow_id: str,
        connection: sqlite3.Connection | None = None,
    ) -> list[dict[str, Any]]:
        query = """
            SELECT * FROM governance_profile
            WHERE workflow_id = ?
            ORDER BY version_int DESC, profile_id DESC
        """
        if connection is not None:
            rows = connection.execute(query, (workflow_id,)).fetchall()
            return [self._convert_governance_profile_row(row) for row in rows]

        self.initialize()
        with self.connection() as owned_connection:
            rows = owned_connection.execute(query, (workflow_id,)).fetchall()
            return [self._convert_governance_profile_row(row) for row in rows]

    def create_board_advisory_session(
        self,
        connection: sqlite3.Connection,
        session: BoardAdvisorySession,
    ) -> dict[str, Any]:
        connection.execute(
            """
            INSERT INTO board_advisory_session (
                session_id,
                workflow_id,
                approval_id,
                review_pack_id,
                trigger_type,
                source_version,
                governance_profile_ref,
                affected_nodes_json,
                working_turns_json,
                decision_pack_refs_json,
                board_decision_json,
                latest_patch_proposal_ref,
                latest_patch_proposal_json,
                approved_patch_ref,
                approved_patch_json,
                patched_graph_version,
                latest_timeline_index_ref,
                latest_transcript_archive_artifact_ref,
                timeline_archive_version_int,
                focus_node_ids_json,
                latest_analysis_run_id,
                latest_analysis_status,
                latest_analysis_incident_id,
                latest_analysis_error,
                latest_analysis_trace_artifact_ref,
                status,
                created_at,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session.session_id,
                session.workflow_id,
                session.approval_id,
                session.review_pack_id,
                session.trigger_type,
                session.source_version,
                session.governance_profile_ref,
                json.dumps(session.affected_nodes, sort_keys=True),
                json.dumps([item.model_dump(mode="json") for item in session.working_turns], sort_keys=True),
                json.dumps(session.decision_pack_refs, sort_keys=True),
                (
                    json.dumps(session.board_decision.model_dump(mode="json"), sort_keys=True)
                    if session.board_decision is not None
                    else None
                ),
                session.latest_patch_proposal_ref,
                (
                    json.dumps(session.latest_patch_proposal.model_dump(mode="json"), sort_keys=True)
                    if session.latest_patch_proposal is not None
                    else None
                ),
                session.approved_patch_ref,
                (
                    json.dumps(session.approved_patch.model_dump(mode="json"), sort_keys=True)
                    if session.approved_patch is not None
                    else None
                ),
                session.patched_graph_version,
                session.latest_timeline_index_ref,
                session.latest_transcript_archive_artifact_ref,
                session.timeline_archive_version_int,
                json.dumps(session.focus_node_ids, sort_keys=True),
                session.latest_analysis_run_id,
                session.latest_analysis_status,
                session.latest_analysis_incident_id,
                session.latest_analysis_error,
                session.latest_analysis_trace_artifact_ref,
                session.status,
                now_local().isoformat(),
                now_local().isoformat(),
            ),
        )
        created = self.get_board_advisory_session(session.session_id, connection=connection)
        if created is None:
            raise RuntimeError("Board advisory session row was not persisted.")
        return created

    def get_board_advisory_session(
        self,
        session_id: str,
        connection: sqlite3.Connection | None = None,
    ) -> dict[str, Any] | None:
        query = """
            SELECT * FROM board_advisory_session
            WHERE session_id = ?
            LIMIT 1
        """
        if connection is not None:
            row = connection.execute(query, (session_id,)).fetchone()
            return None if row is None else self._convert_board_advisory_session_row(row)

        self.initialize()
        with self.connection() as owned_connection:
            row = owned_connection.execute(query, (session_id,)).fetchone()
            return None if row is None else self._convert_board_advisory_session_row(row)

    def get_board_advisory_session_for_approval(
        self,
        approval_id: str,
        connection: sqlite3.Connection | None = None,
    ) -> dict[str, Any] | None:
        query = """
            SELECT * FROM board_advisory_session
            WHERE approval_id = ?
            LIMIT 1
        """
        if connection is not None:
            row = connection.execute(query, (approval_id,)).fetchone()
            return None if row is None else self._convert_board_advisory_session_row(row)

        self.initialize()
        with self.connection() as owned_connection:
            row = owned_connection.execute(query, (approval_id,)).fetchone()
            return None if row is None else self._convert_board_advisory_session_row(row)

    def list_board_advisory_sessions(
        self,
        workflow_id: str,
        *,
        statuses: list[str] | None = None,
        connection: sqlite3.Connection | None = None,
    ) -> list[dict[str, Any]]:
        params: list[Any] = [workflow_id]
        status_clause = ""
        if statuses:
            placeholders = ", ".join("?" for _ in statuses)
            status_clause = f" AND status IN ({placeholders})"
            params.extend(statuses)
        query = f"""
            SELECT * FROM board_advisory_session
            WHERE workflow_id = ?{status_clause}
            ORDER BY updated_at DESC, session_id DESC
        """
        if connection is not None:
            rows = connection.execute(query, tuple(params)).fetchall()
            return [self._convert_board_advisory_session_row(row) for row in rows]

        self.initialize()
        with self.connection() as owned_connection:
            rows = owned_connection.execute(query, tuple(params)).fetchall()
            return [self._convert_board_advisory_session_row(row) for row in rows]

    def decide_board_advisory_session(
        self,
        connection: sqlite3.Connection,
        *,
        session_id: str,
        board_decision: dict[str, Any],
        decision_pack_refs: list[str],
        approved_patch_ref: str,
        approved_patch: dict[str, Any] | None = None,
        patched_graph_version: str | None = None,
        focus_node_ids: list[str] | None = None,
        updated_at: datetime,
    ) -> dict[str, Any]:
        current = self.get_board_advisory_session(session_id, connection=connection)
        if current is None:
            raise ValueError("Board advisory session is missing.")
        if str(current.get("status") or "") not in {"PENDING_BOARD_CONFIRMATION", "OPEN"}:
            raise ValueError("Board advisory session must be ready for board confirmation.")
        connection.execute(
            """
            UPDATE board_advisory_session
            SET decision_pack_refs_json = ?,
                board_decision_json = ?,
                approved_patch_ref = ?,
                approved_patch_json = ?,
                patched_graph_version = ?,
                focus_node_ids_json = ?,
                status = ?,
                updated_at = ?
            WHERE session_id = ?
            """,
            (
                json.dumps(list(decision_pack_refs), sort_keys=True),
                json.dumps(board_decision, sort_keys=True),
                approved_patch_ref,
                json.dumps(approved_patch, sort_keys=True) if approved_patch is not None else None,
                patched_graph_version,
                json.dumps(list(focus_node_ids or []), sort_keys=True),
                "APPLIED",
                updated_at.isoformat(),
                session_id,
            ),
        )
        updated = self.get_board_advisory_session(session_id, connection=connection)
        if updated is None:
            raise RuntimeError("Board advisory session row vanished after decision update.")
        return updated

    def update_board_advisory_timeline_archive(
        self,
        connection: sqlite3.Connection,
        *,
        session_id: str,
        latest_timeline_index_ref: str,
        latest_transcript_archive_artifact_ref: str,
        timeline_archive_version_int: int,
        updated_at: datetime,
    ) -> dict[str, Any]:
        current = self.get_board_advisory_session(session_id, connection=connection)
        if current is None:
            raise ValueError("Board advisory session is missing.")
        connection.execute(
            """
            UPDATE board_advisory_session
            SET latest_timeline_index_ref = ?,
                latest_transcript_archive_artifact_ref = ?,
                timeline_archive_version_int = ?,
                updated_at = ?
            WHERE session_id = ?
            """,
            (
                latest_timeline_index_ref,
                latest_transcript_archive_artifact_ref,
                timeline_archive_version_int,
                updated_at.isoformat(),
                session_id,
            ),
        )
        updated = self.get_board_advisory_session(session_id, connection=connection)
        if updated is None:
            raise RuntimeError("Board advisory session row vanished after timeline archive update.")
        return updated

    def dismiss_board_advisory_session(
        self,
        connection: sqlite3.Connection,
        *,
        session_id: str,
        updated_at: datetime,
    ) -> dict[str, Any]:
        current = self.get_board_advisory_session(session_id, connection=connection)
        if current is None:
            raise ValueError("Board advisory session is missing.")
        if str(current.get("status") or "") in {"APPLIED", "DISMISSED"}:
            raise ValueError("Board advisory session can no longer be dismissed.")
        connection.execute(
            """
            UPDATE board_advisory_session
            SET status = ?,
                updated_at = ?
            WHERE session_id = ?
            """,
            (
                "DISMISSED",
                updated_at.isoformat(),
                session_id,
            ),
        )
        updated = self.get_board_advisory_session(session_id, connection=connection)
        if updated is None:
            raise RuntimeError("Board advisory session row vanished after dismissal.")
        return updated

    def start_board_advisory_change_flow(
        self,
        connection: sqlite3.Connection,
        *,
        session_id: str,
        board_decision: dict[str, Any],
        decision_pack_refs: list[str],
        working_turn: dict[str, Any],
        updated_at: datetime,
    ) -> dict[str, Any]:
        current = self.get_board_advisory_session(session_id, connection=connection)
        if current is None:
            raise ValueError("Board advisory session is missing.")
        if str(current.get("status") or "") not in {"OPEN", "DRAFTING", "ANALYSIS_REJECTED"}:
            raise ValueError("Board advisory change flow cannot be started from the current state.")
        existing_turns = list(current.get("working_turns") or [])
        existing_turns.append(dict(working_turn))
        connection.execute(
            """
            UPDATE board_advisory_session
            SET working_turns_json = ?,
                decision_pack_refs_json = ?,
                board_decision_json = ?,
                latest_patch_proposal_ref = NULL,
                latest_patch_proposal_json = NULL,
                approved_patch_ref = NULL,
                approved_patch_json = NULL,
                patched_graph_version = NULL,
                focus_node_ids_json = '[]',
                latest_analysis_run_id = NULL,
                latest_analysis_status = NULL,
                latest_analysis_incident_id = NULL,
                latest_analysis_error = NULL,
                latest_analysis_trace_artifact_ref = NULL,
                status = ?,
                updated_at = ?
            WHERE session_id = ?
            """,
            (
                json.dumps(existing_turns, sort_keys=True),
                json.dumps(list(decision_pack_refs), sort_keys=True),
                json.dumps(board_decision, sort_keys=True),
                "DRAFTING",
                updated_at.isoformat(),
                session_id,
            ),
        )
        updated = self.get_board_advisory_session(session_id, connection=connection)
        if updated is None:
            raise RuntimeError("Board advisory session row vanished after change-flow entry.")
        return updated

    def append_board_advisory_turn(
        self,
        connection: sqlite3.Connection,
        *,
        session_id: str,
        working_turn: dict[str, Any],
        updated_at: datetime,
    ) -> dict[str, Any]:
        current = self.get_board_advisory_session(session_id, connection=connection)
        if current is None:
            raise ValueError("Board advisory session is missing.")
        if str(current.get("status") or "") not in {"DRAFTING", "ANALYSIS_REJECTED"}:
            raise ValueError("Board advisory turn can only be appended while drafting.")
        working_turns = list(current.get("working_turns") or [])
        working_turns.append(dict(working_turn))
        connection.execute(
            """
            UPDATE board_advisory_session
            SET working_turns_json = ?,
                status = ?,
                latest_analysis_run_id = NULL,
                latest_analysis_status = NULL,
                latest_analysis_incident_id = NULL,
                latest_analysis_error = NULL,
                latest_analysis_trace_artifact_ref = NULL,
                updated_at = ?
            WHERE session_id = ?
            """,
            (
                json.dumps(working_turns, sort_keys=True),
                "DRAFTING",
                updated_at.isoformat(),
                session_id,
            ),
        )
        updated = self.get_board_advisory_session(session_id, connection=connection)
        if updated is None:
            raise RuntimeError("Board advisory session row vanished after turn append.")
        return updated

    def store_board_advisory_patch_proposal(
        self,
        connection: sqlite3.Connection,
        *,
        session_id: str,
        proposal_ref: str,
        proposal: dict[str, Any],
        decision_pack_refs: list[str],
        updated_at: datetime,
    ) -> dict[str, Any]:
        current = self.get_board_advisory_session(session_id, connection=connection)
        if current is None:
            raise ValueError("Board advisory session is missing.")
        connection.execute(
            """
            UPDATE board_advisory_session
            SET latest_patch_proposal_ref = ?,
                latest_patch_proposal_json = ?,
                decision_pack_refs_json = ?,
                latest_analysis_status = 'SUCCEEDED',
                latest_analysis_incident_id = NULL,
                latest_analysis_error = NULL,
                status = ?,
                updated_at = ?
            WHERE session_id = ?
            """,
            (
                proposal_ref,
                json.dumps(proposal, sort_keys=True),
                json.dumps(list(decision_pack_refs), sort_keys=True),
                "PENDING_BOARD_CONFIRMATION",
                updated_at.isoformat(),
                session_id,
            ),
        )
        updated = self.get_board_advisory_session(session_id, connection=connection)
        if updated is None:
            raise RuntimeError("Board advisory session row vanished after proposal update.")
        return updated

    def reject_board_advisory_analysis(
        self,
        connection: sqlite3.Connection,
        *,
        session_id: str,
        error_message: str,
        updated_at: datetime,
    ) -> dict[str, Any]:
        current = self.get_board_advisory_session(session_id, connection=connection)
        if current is None:
            raise ValueError("Board advisory session is missing.")
        connection.execute(
            """
            UPDATE board_advisory_session
            SET latest_analysis_error = ?,
                latest_analysis_status = 'FAILED',
                status = ?,
                updated_at = ?
            WHERE session_id = ?
            """,
            (
                error_message,
                "ANALYSIS_REJECTED",
                updated_at.isoformat(),
                session_id,
            ),
        )
        updated = self.get_board_advisory_session(session_id, connection=connection)
        if updated is None:
            raise RuntimeError("Board advisory session row vanished after analysis rejection.")
        return updated

    def create_board_advisory_analysis_run(
        self,
        connection: sqlite3.Connection,
        run: BoardAdvisoryAnalysisRun,
    ) -> dict[str, Any]:
        connection.execute(
            """
            INSERT INTO board_advisory_analysis_run (
                run_id,
                session_id,
                workflow_id,
                source_graph_version,
                status,
                idempotency_key,
                attempt_int,
                executor_mode,
                compile_request_id,
                compiled_execution_package_ref,
                proposal_ref,
                analysis_trace_artifact_ref,
                incident_id,
                error_code,
                error_message,
                created_at,
                started_at,
                finished_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run.run_id,
                run.session_id,
                run.workflow_id,
                run.source_graph_version,
                run.status,
                run.idempotency_key,
                run.attempt_int,
                run.executor_mode,
                run.compile_request_id,
                run.compiled_execution_package_ref,
                run.proposal_ref,
                run.analysis_trace_artifact_ref,
                run.incident_id,
                run.error_code,
                run.error_message,
                run.created_at.isoformat(),
                run.started_at.isoformat() if run.started_at is not None else None,
                run.finished_at.isoformat() if run.finished_at is not None else None,
            ),
        )
        created = self.get_board_advisory_analysis_run(run.run_id, connection=connection)
        if created is None:
            raise RuntimeError("Board advisory analysis run row was not persisted.")
        return created

    def get_board_advisory_analysis_run(
        self,
        run_id: str,
        connection: sqlite3.Connection | None = None,
    ) -> dict[str, Any] | None:
        query = """
            SELECT * FROM board_advisory_analysis_run
            WHERE run_id = ?
            LIMIT 1
        """
        if connection is not None:
            row = connection.execute(query, (run_id,)).fetchone()
            return None if row is None else self._convert_board_advisory_analysis_run_row(row)

        self.initialize()
        with self.connection() as owned_connection:
            row = owned_connection.execute(query, (run_id,)).fetchone()
            return None if row is None else self._convert_board_advisory_analysis_run_row(row)

    def get_latest_board_advisory_analysis_run(
        self,
        session_id: str,
        connection: sqlite3.Connection | None = None,
    ) -> dict[str, Any] | None:
        query = """
            SELECT * FROM board_advisory_analysis_run
            WHERE session_id = ?
            ORDER BY attempt_int DESC, created_at DESC, run_id DESC
            LIMIT 1
        """
        if connection is not None:
            row = connection.execute(query, (session_id,)).fetchone()
            return None if row is None else self._convert_board_advisory_analysis_run_row(row)

        self.initialize()
        with self.connection() as owned_connection:
            row = owned_connection.execute(query, (session_id,)).fetchone()
            return None if row is None else self._convert_board_advisory_analysis_run_row(row)

    def list_board_advisory_analysis_runs(
        self,
        session_id: str,
        *,
        statuses: list[str] | None = None,
        connection: sqlite3.Connection | None = None,
    ) -> list[dict[str, Any]]:
        params: list[Any] = [session_id]
        status_clause = ""
        if statuses:
            placeholders = ", ".join("?" for _ in statuses)
            status_clause = f" AND status IN ({placeholders})"
            params.extend(statuses)
        query = f"""
            SELECT * FROM board_advisory_analysis_run
            WHERE session_id = ?{status_clause}
            ORDER BY attempt_int DESC, created_at DESC, run_id DESC
        """
        if connection is not None:
            rows = connection.execute(query, tuple(params)).fetchall()
            return [self._convert_board_advisory_analysis_run_row(row) for row in rows]

        self.initialize()
        with self.connection() as owned_connection:
            rows = owned_connection.execute(query, tuple(params)).fetchall()
            return [self._convert_board_advisory_analysis_run_row(row) for row in rows]

    def queue_board_advisory_analysis_run(
        self,
        connection: sqlite3.Connection,
        *,
        session_id: str,
        run_id: str,
        updated_at: datetime,
    ) -> dict[str, Any]:
        current = self.get_board_advisory_session(session_id, connection=connection)
        if current is None:
            raise ValueError("Board advisory session is missing.")
        connection.execute(
            """
            UPDATE board_advisory_session
            SET latest_analysis_run_id = ?,
                latest_analysis_status = 'PENDING',
                latest_analysis_incident_id = NULL,
                latest_analysis_error = NULL,
                latest_analysis_trace_artifact_ref = NULL,
                status = 'PENDING_ANALYSIS',
                updated_at = ?
            WHERE session_id = ?
            """,
            (
                run_id,
                updated_at.isoformat(),
                session_id,
            ),
        )
        updated = self.get_board_advisory_session(session_id, connection=connection)
        if updated is None:
            raise RuntimeError("Board advisory session row vanished after analysis queue.")
        return updated

    def start_board_advisory_analysis_run(
        self,
        connection: sqlite3.Connection,
        *,
        run_id: str,
        compile_request_id: str,
        compiled_execution_package_ref: str,
        started_at: datetime,
    ) -> dict[str, Any]:
        current = self.get_board_advisory_analysis_run(run_id, connection=connection)
        if current is None:
            raise ValueError("Board advisory analysis run is missing.")
        connection.execute(
            """
            UPDATE board_advisory_analysis_run
            SET status = 'RUNNING',
                compile_request_id = ?,
                compiled_execution_package_ref = ?,
                started_at = ?
            WHERE run_id = ?
            """,
            (
                compile_request_id,
                compiled_execution_package_ref,
                started_at.isoformat(),
                run_id,
            ),
        )
        connection.execute(
            """
            UPDATE board_advisory_session
            SET latest_analysis_status = 'RUNNING',
                updated_at = ?
            WHERE session_id = ?
            """,
            (
                started_at.isoformat(),
                current["session_id"],
            ),
        )
        updated = self.get_board_advisory_analysis_run(run_id, connection=connection)
        if updated is None:
            raise RuntimeError("Board advisory analysis run row vanished after start.")
        return updated

    def complete_board_advisory_analysis_run(
        self,
        connection: sqlite3.Connection,
        *,
        run_id: str,
        proposal_ref: str,
        analysis_trace_artifact_ref: str | None,
        finished_at: datetime,
    ) -> dict[str, Any]:
        current = self.get_board_advisory_analysis_run(run_id, connection=connection)
        if current is None:
            raise ValueError("Board advisory analysis run is missing.")
        connection.execute(
            """
            UPDATE board_advisory_analysis_run
            SET status = 'SUCCEEDED',
                proposal_ref = ?,
                analysis_trace_artifact_ref = ?,
                incident_id = NULL,
                error_code = NULL,
                error_message = NULL,
                finished_at = ?
            WHERE run_id = ?
            """,
            (
                proposal_ref,
                analysis_trace_artifact_ref,
                finished_at.isoformat(),
                run_id,
            ),
        )
        connection.execute(
            """
            UPDATE board_advisory_session
            SET latest_analysis_run_id = ?,
                latest_analysis_status = 'SUCCEEDED',
                latest_analysis_incident_id = NULL,
                latest_analysis_error = NULL,
                latest_analysis_trace_artifact_ref = ?,
                updated_at = ?
            WHERE session_id = ?
            """,
            (
                run_id,
                analysis_trace_artifact_ref,
                finished_at.isoformat(),
                current["session_id"],
            ),
        )
        updated = self.get_board_advisory_analysis_run(run_id, connection=connection)
        if updated is None:
            raise RuntimeError("Board advisory analysis run row vanished after completion.")
        return updated

    def fail_board_advisory_analysis_run(
        self,
        connection: sqlite3.Connection,
        *,
        run_id: str,
        incident_id: str | None,
        error_code: str,
        error_message: str,
        analysis_trace_artifact_ref: str | None,
        finished_at: datetime,
    ) -> dict[str, Any]:
        current = self.get_board_advisory_analysis_run(run_id, connection=connection)
        if current is None:
            raise ValueError("Board advisory analysis run is missing.")
        connection.execute(
            """
            UPDATE board_advisory_analysis_run
            SET status = 'FAILED',
                incident_id = ?,
                error_code = ?,
                error_message = ?,
                analysis_trace_artifact_ref = ?,
                finished_at = ?
            WHERE run_id = ?
            """,
            (
                incident_id,
                error_code,
                error_message,
                analysis_trace_artifact_ref,
                finished_at.isoformat(),
                run_id,
            ),
        )
        connection.execute(
            """
            UPDATE board_advisory_session
            SET latest_analysis_run_id = ?,
                latest_analysis_status = 'FAILED',
                latest_analysis_incident_id = ?,
                latest_analysis_error = ?,
                latest_analysis_trace_artifact_ref = ?,
                status = 'ANALYSIS_REJECTED',
                updated_at = ?
            WHERE session_id = ?
            """,
            (
                run_id,
                incident_id,
                error_message,
                analysis_trace_artifact_ref,
                finished_at.isoformat(),
                current["session_id"],
            ),
        )
        updated = self.get_board_advisory_analysis_run(run_id, connection=connection)
        if updated is None:
            raise RuntimeError("Board advisory analysis run row vanished after failure.")
        return updated

    def get_cursor_and_version(
        self,
        connection: sqlite3.Connection | None = None,
    ) -> tuple[str | None, int]:
        query = """
            SELECT event_id, sequence_no
            FROM events
            ORDER BY sequence_no DESC
            LIMIT 1
        """
        if connection is not None:
            row = connection.execute(query).fetchone()
            if row is None:
                return None, 0
            return row["event_id"], int(row["sequence_no"])

        self.initialize()
        with self.connection() as owned_connection:
            row = owned_connection.execute(query).fetchone()
            if row is None:
                return None, 0
            return row["event_id"], int(row["sequence_no"])

    def validate_projection_version_guard(
        self,
        *,
        current_ticket: dict[str, Any],
        current_node: dict[str, Any] | None,
        current_runtime_node: dict[str, Any] | None,
        expected_ticket_version: int | None,
        expected_node_version: int | None,
        expected_runtime_node_version: int | None,
    ) -> str | None:
        if (
            expected_ticket_version is None
            and expected_node_version is None
            and expected_runtime_node_version is None
        ):
            return None
        if expected_ticket_version is not None and int(current_ticket["version"]) != int(expected_ticket_version):
            return (
                "Projection target outdated. Reload ticket state before retrying "
                f"(ticket version {current_ticket['version']} != expected {expected_ticket_version})."
            )
        if expected_node_version is not None:
            if current_node is None:
                return "Projection target outdated. Reload ticket state before retrying (node projection is missing)."
            if int(current_node["version"]) != int(expected_node_version):
                return (
                    "Projection target outdated. Reload ticket state before retrying "
                    f"(node version {current_node['version']} != expected {expected_node_version})."
                )
        if expected_runtime_node_version is not None:
            if current_runtime_node is None:
                return (
                    "Projection target outdated. Reload ticket state before retrying "
                    "(runtime node projection is missing)."
                )
            if int(current_runtime_node["version"]) != int(expected_runtime_node_version):
                return (
                    "Projection target outdated. Reload ticket state before retrying "
                    f"(runtime node version {current_runtime_node['version']} != expected "
                    f"{expected_runtime_node_version})."
                )
        return None

    def validate_compiled_execution_package_guard(
        self,
        connection: sqlite3.Connection,
        *,
        ticket_id: str,
        compile_request_id: str | None,
        compiled_execution_package_version_ref: str | None,
    ) -> str | None:
        if not compile_request_id and not compiled_execution_package_version_ref:
            return None
        latest_package = self.get_latest_compiled_execution_package_by_ticket(
            ticket_id,
            connection=connection,
        )
        if latest_package is None:
            return "Compiled execution package is missing for this ticket."
        if (
            compile_request_id is not None
            and str(latest_package["compile_request_id"]) != str(compile_request_id)
        ):
            return (
                "Compiled execution package is outdated. Reload runtime state before retrying "
                f"(compile request {latest_package['compile_request_id']} != expected {compile_request_id})."
            )
        if (
            compiled_execution_package_version_ref is not None
            and str(latest_package["version_ref"]) != str(compiled_execution_package_version_ref)
        ):
            return (
                "Compiled execution package is outdated. Reload runtime state before retrying "
                f"(package version {latest_package['version_ref']} != expected {compiled_execution_package_version_ref})."
            )
        latest_payload = latest_package.get("payload") or {}
        latest_meta = latest_payload.get("meta") or {}
        expected_runtime_node_version = latest_meta.get("runtime_node_projection_version")
        if expected_runtime_node_version is not None:
            latest_created_spec = self.get_latest_ticket_created_payload(
                connection,
                ticket_id,
            ) or {}
            try:
                graph_identity = resolve_ticket_graph_identity(
                    ticket_id=ticket_id,
                    created_spec=latest_created_spec,
                    runtime_node_id=str(latest_meta.get("node_id") or ""),
                )
            except GraphIdentityResolutionError as exc:
                return (
                    "Compiled execution package is outdated. Reload runtime state before retrying "
                    f"({exc})."
                )
            current_runtime_node = self.get_runtime_node_projection(
                str(latest_meta.get("workflow_id") or ""),
                str(graph_identity.graph_node_id),
                connection=connection,
            )
            if current_runtime_node is None:
                return (
                    "Compiled execution package is outdated. Reload runtime state before retrying "
                    "(runtime node projection is missing)."
                )
            if int(current_runtime_node["version"]) != int(expected_runtime_node_version):
                return (
                    "Compiled execution package is outdated. Reload runtime state before retrying "
                    f"(runtime node version {current_runtime_node['version']} != expected "
                    f"{expected_runtime_node_version})."
                )
            expected_graph_version = str(latest_meta.get("graph_version") or "").strip()
            current_graph_version = str(current_runtime_node.get("graph_version") or "").strip()
            if expected_graph_version and current_graph_version and current_graph_version != expected_graph_version:
                return (
                    "PACKAGE_STALE: Compiled execution package graph version is outdated. "
                    f"Reload runtime state before retrying (graph version {current_graph_version} "
                    f"!= expected {expected_graph_version})."
                )
        indexed_guard_asset_kinds = {
            "SOURCE_CODE_DELIVERY",
            "EVIDENCE_PACK",
            "GOVERNANCE_DOCUMENT",
            "MEETING_DECISION_RECORD",
            "CLOSEOUT_SUMMARY",
        }
        for block in list(
            ((latest_payload.get("atomic_context_bundle") or {}).get("context_blocks") or [])
        ):
            if not isinstance(block, dict) or block.get("source_kind") != "PROCESS_ASSET":
                continue
            content_payload = block.get("content_payload") or {}
            if not isinstance(content_payload, dict):
                content_payload = {}
            process_asset_kind = str(content_payload.get("process_asset_kind") or "").strip()
            if process_asset_kind not in indexed_guard_asset_kinds:
                continue
            source_ref = str(content_payload.get("process_asset_ref") or block.get("source_ref") or "").strip()
            if not source_ref:
                continue
            index_entry = self.get_process_asset_index_entry(source_ref, connection=connection)
            if index_entry is None:
                return f"EVIDENCE_GAP: Process asset {source_ref} is missing from process_asset_index."
            visibility_status = str(index_entry.get("visibility_status") or "").strip()
            if visibility_status != "CONSUMABLE":
                reason_code = "PACKAGE_STALE" if visibility_status == "SUPERSEDED" else "EVIDENCE_LINEAGE_BREAK"
                return (
                    f"{reason_code}: Process asset {source_ref} is {visibility_status} "
                    "and cannot be consumed by this compiled execution package."
                )
            source_metadata = content_payload.get("source_metadata") or {}
            if not isinstance(source_metadata, dict):
                source_metadata = {}
            expected_content_hash = str(source_metadata.get("content_hash") or "").strip()
            current_content_hash = str(index_entry.get("content_hash") or "").strip()
            if expected_content_hash and current_content_hash and current_content_hash != expected_content_hash:
                return (
                    f"PACKAGE_STALE: Process asset {source_ref} content hash changed "
                    f"({current_content_hash} != expected {expected_content_hash})."
                )
        return None

    def _next_version_int(
        self,
        connection: sqlite3.Connection,
        *,
        table_name: str,
        ticket_id: str,
    ) -> int:
        row = connection.execute(
            f"SELECT MAX(version_int) AS max_version FROM {table_name} WHERE ticket_id = ?",
            (ticket_id,),
        ).fetchone()
        return int(row["max_version"] or 0) + 1

    def _previous_version_ref(
        self,
        connection: sqlite3.Connection,
        *,
        table_name: str,
        ticket_id: str,
    ) -> str | None:
        row = connection.execute(
            f"""
            SELECT version_ref
            FROM {table_name}
            WHERE ticket_id = ?
            ORDER BY version_int DESC
            LIMIT 1
            """,
            (ticket_id,),
        ).fetchone()
        if row is None:
            return None
        version_ref = str(row["version_ref"] or "").strip()
        return version_ref or None

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
        self._rebuild_retrieval_artifact_summary_fts(connection)

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
        connection: sqlite3.Connection | None = None,
    ) -> list[dict[str, Any]]:
        self.initialize()
        match_query = self._build_retrieval_match_query(normalized_terms)
        if match_query is None:
            return []

        candidates: list[dict[str, Any]] = []
        if connection is not None:
            owned_connection = None
            active_connection = connection
        else:
            owned_connection = self.connection()
            active_connection = owned_connection.__enter__()
        try:
            self._rebuild_retrieval_review_summary_fts(active_connection)
            rows = active_connection.execute(
                f"""
                SELECT
                    source_ref,
                    updated_at,
                    headline_text,
                    summary_text,
                    detail_text,
                    bm25({RETRIEVAL_REVIEW_SUMMARY_FTS}) AS fts_rank
                FROM {RETRIEVAL_REVIEW_SUMMARY_FTS}
                WHERE {RETRIEVAL_REVIEW_SUMMARY_FTS} MATCH ?
                  AND workflow_id != ?
                  AND status != ?
                  AND tenant_id = ?
                  AND workspace_id = ?
                ORDER BY bm25({RETRIEVAL_REVIEW_SUMMARY_FTS}), updated_at DESC, source_ref ASC
                LIMIT ?
                """,
                (
                    match_query,
                    exclude_workflow_id,
                    APPROVAL_STATUS_OPEN,
                    tenant_id,
                    workspace_id,
                    max(limit * 4, 24),
                ),
            ).fetchall()
            for row in rows:
                approval = self.get_approval_by_id(active_connection, str(row["source_ref"]))
                if approval is None:
                    continue
                payload = approval["payload"]
                review_pack = payload.get("review_pack") or {}
                subject = review_pack.get("subject") or {}
                recommendation = review_pack.get("recommendation") or {}
                resolution = payload.get("resolution") or {}
                matched_terms = self._matched_retrieval_terms(
                    normalized_terms,
                    [row["headline_text"], row["summary_text"], row["detail_text"]],
                )
                if not matched_terms:
                    continue
                candidates.append(
                    {
                        "channel": "review_summaries",
                        "source_ref": approval["review_pack_id"],
                        "source_workflow_id": approval["workflow_id"],
                        "source_ticket_id": subject.get("source_ticket_id"),
                        "review_pack_id": approval["review_pack_id"],
                        "headline": str(
                            row["headline_text"]
                            or subject.get("title")
                            or payload.get("inbox_title")
                            or approval["review_pack_id"]
                        ),
                        "summary": str(
                            row["summary_text"]
                            or recommendation.get("summary")
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
                        "updated_at": approval.get("updated_at"),
                        "fts_rank": float(row["fts_rank"]) if row["fts_rank"] is not None else None,
                    }
                )
        finally:
            if owned_connection is not None:
                owned_connection.__exit__(None, None, None)

        return [
            {key: value for key, value in candidate.items() if key != "fts_rank"}
            for candidate in self._sort_retrieval_candidates(candidates)[:limit]
        ]

    def list_retrieval_incident_summary_candidates(
        self,
        *,
        tenant_id: str,
        workspace_id: str,
        exclude_workflow_id: str,
        normalized_terms: list[str],
        limit: int,
        connection: sqlite3.Connection | None = None,
    ) -> list[dict[str, Any]]:
        self.initialize()
        match_query = self._build_retrieval_match_query(normalized_terms)
        if match_query is None:
            return []

        candidates: list[dict[str, Any]] = []
        if connection is not None:
            owned_connection = None
            active_connection = connection
        else:
            owned_connection = self.connection()
            active_connection = owned_connection.__enter__()
        try:
            self._rebuild_retrieval_incident_summary_fts(active_connection)
            rows = active_connection.execute(
                f"""
                SELECT
                    source_ref,
                    updated_at,
                    incident_type,
                    fingerprint,
                    headline_text,
                    summary_text,
                    bm25({RETRIEVAL_INCIDENT_SUMMARY_FTS}) AS fts_rank
                FROM {RETRIEVAL_INCIDENT_SUMMARY_FTS}
                WHERE {RETRIEVAL_INCIDENT_SUMMARY_FTS} MATCH ?
                  AND workflow_id != ?
                  AND tenant_id = ?
                  AND workspace_id = ?
                ORDER BY bm25({RETRIEVAL_INCIDENT_SUMMARY_FTS}), updated_at DESC, source_ref ASC
                LIMIT ?
                """,
                (
                    match_query,
                    exclude_workflow_id,
                    tenant_id,
                    workspace_id,
                    max(limit * 4, 24),
                ),
            ).fetchall()
            for row in rows:
                incident = self.get_incident_projection(str(row["source_ref"]), active_connection)
                if incident is None:
                    continue
                payload = incident["payload"]
                matched_terms = self._matched_retrieval_terms(
                    normalized_terms,
                    [
                        row["headline_text"],
                        row["summary_text"],
                        row["incident_type"],
                        row["fingerprint"],
                    ],
                )
                if not matched_terms:
                    continue
                candidates.append(
                    {
                        "channel": "incident_summaries",
                        "source_ref": incident["incident_id"],
                        "source_workflow_id": incident["workflow_id"],
                        "source_ticket_id": incident.get("ticket_id"),
                        "incident_id": incident["incident_id"],
                        "headline": str(
                            row["headline_text"]
                            or payload.get("headline")
                            or incident.get("incident_type")
                            or incident["incident_id"]
                        ),
                        "summary": str(
                            row["summary_text"] or payload.get("summary") or "Historical incident summary."
                        ),
                        "matched_terms": matched_terms,
                        "why_it_matched": (
                            "Matched "
                            + ", ".join(matched_terms)
                            + " in a historical incident summary from the same local workspace."
                        ),
                        "updated_at": incident.get("updated_at"),
                        "fts_rank": float(row["fts_rank"]) if row["fts_rank"] is not None else None,
                    }
                )
        finally:
            if owned_connection is not None:
                owned_connection.__exit__(None, None, None)

        return [
            {key: value for key, value in candidate.items() if key != "fts_rank"}
            for candidate in self._sort_retrieval_candidates(candidates)[:limit]
        ]

    def list_retrieval_artifact_summary_candidates(
        self,
        *,
        tenant_id: str,
        workspace_id: str,
        exclude_workflow_id: str,
        normalized_terms: list[str],
        limit: int,
        connection: sqlite3.Connection | None = None,
    ) -> list[dict[str, Any]]:
        self.initialize()
        match_query = self._build_retrieval_match_query(normalized_terms)
        if match_query is None:
            return []

        candidates: list[dict[str, Any]] = []
        if connection is not None:
            owned_connection = None
            active_connection = connection
        else:
            owned_connection = self.connection()
            active_connection = owned_connection.__enter__()
        try:
            self._rebuild_retrieval_artifact_summary_fts(active_connection)
            rows = active_connection.execute(
                f"""
                SELECT
                    source_ref,
                    updated_at,
                    path_text,
                    kind_text,
                    media_type_text,
                    summary_text,
                    body_text,
                    bm25({RETRIEVAL_ARTIFACT_SUMMARY_FTS}) AS fts_rank
                FROM {RETRIEVAL_ARTIFACT_SUMMARY_FTS}
                WHERE {RETRIEVAL_ARTIFACT_SUMMARY_FTS} MATCH ?
                  AND workflow_id != ?
                  AND tenant_id = ?
                  AND workspace_id = ?
                  AND lifecycle_status = 'ACTIVE'
                  AND materialization_status = 'MATERIALIZED'
                ORDER BY bm25({RETRIEVAL_ARTIFACT_SUMMARY_FTS}), updated_at DESC, source_ref ASC
                LIMIT ?
                """,
                (
                    match_query,
                    exclude_workflow_id,
                    tenant_id,
                    workspace_id,
                    max(limit * 4, 24),
                ),
            ).fetchall()
            for row in rows:
                artifact = self.get_artifact_by_ref(str(row["source_ref"]), active_connection)
                if artifact is None:
                    continue
                coarse_matched_terms = self._matched_retrieval_terms(
                    normalized_terms,
                    [row["path_text"], row["kind_text"], row["media_type_text"]],
                )
                if not coarse_matched_terms:
                    continue
                matched_terms = self._matched_retrieval_terms(
                    normalized_terms,
                    [row["path_text"], row["body_text"]],
                )
                if not matched_terms:
                    continue
                access = build_artifact_access_descriptor(
                    artifact,
                    artifact_ref=str(artifact["artifact_ref"]),
                )
                candidates.append(
                    {
                        "channel": "artifact_summaries",
                        "source_ref": artifact["artifact_ref"],
                        "source_workflow_id": artifact["workflow_id"],
                        "source_ticket_id": artifact.get("ticket_id"),
                        "artifact_ref": artifact["artifact_ref"],
                        "preview_url": access.get("preview_url"),
                        "headline": str(row["path_text"] or artifact.get("path") or artifact["artifact_ref"]),
                        "summary": str(
                            row["summary_text"]
                            or self._summarize_retrieval_text(str(row["body_text"] or ""))
                        ),
                        "matched_terms": matched_terms,
                        "why_it_matched": (
                            "Matched "
                            + ", ".join(matched_terms)
                            + " in a historical artifact from the same local workspace."
                        ),
                        "updated_at": artifact.get("created_at"),
                        "fts_rank": float(row["fts_rank"]) if row["fts_rank"] is not None else None,
                    }
                )
        finally:
            if owned_connection is not None:
                owned_connection.__exit__(None, None, None)

        return [
            {key: value for key, value in candidate.items() if key != "fts_rank"}
            for candidate in self._sort_retrieval_candidates(candidates)[:limit]
        ]

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
        self._rebuild_retrieval_artifact_summary_fts(connection)

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
        self._rebuild_retrieval_artifact_summary_fts(connection)

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
        self._rebuild_retrieval_artifact_summary_fts(connection)

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
        self._rebuild_retrieval_artifact_summary_fts(connection)

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

    def create_meeting_projection(
        self,
        connection: sqlite3.Connection,
        *,
        meeting_id: str,
        workflow_id: str,
        meeting_type: str,
        topic: str,
        normalized_topic: str,
        status: str,
        source_ticket_id: str,
        source_graph_node_id: str,
        opened_at: datetime,
        updated_at: datetime,
        recorder_employee_id: str,
        participants: list[dict[str, Any]],
        rounds: list[dict[str, Any]] | None = None,
        current_round: str | None = None,
        review_status: str | None = None,
        review_pack_id: str | None = None,
        closed_at: datetime | None = None,
        consensus_summary: str | None = None,
        no_consensus_reason: str | None = None,
    ) -> None:
        _, normalized_source_graph_node_id, normalized_source_node_id = resolve_graph_only_review_subject_execution_identity(
            self,
            workflow_id=workflow_id,
            subject={
                "source_ticket_id": source_ticket_id,
                "source_graph_node_id": source_graph_node_id,
            },
            connection=connection,
        )
        connection.execute(
            """
            INSERT INTO meeting_projection (
                meeting_id,
                workflow_id,
                meeting_type,
                topic,
                normalized_topic,
                status,
                review_status,
                source_ticket_id,
                source_graph_node_id,
                source_node_id,
                review_pack_id,
                opened_at,
                updated_at,
                closed_at,
                current_round,
                recorder_employee_id,
                participants_json,
                rounds_json,
                consensus_summary,
                no_consensus_reason
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                meeting_id,
                workflow_id,
                meeting_type,
                topic,
                normalized_topic,
                status,
                review_status,
                source_ticket_id,
                normalized_source_graph_node_id,
                normalized_source_node_id,
                review_pack_id,
                opened_at.isoformat(),
                updated_at.isoformat(),
                None if closed_at is None else closed_at.isoformat(),
                current_round,
                recorder_employee_id,
                json.dumps(participants, sort_keys=True),
                json.dumps(rounds or [], sort_keys=True),
                consensus_summary,
                no_consensus_reason,
            ),
        )

    def update_meeting_projection(
        self,
        connection: sqlite3.Connection,
        meeting_id: str,
        **updates: Any,
    ) -> None:
        if not updates:
            return

        normalized_updates = dict(updates)
        if "participants" in normalized_updates:
            normalized_updates["participants_json"] = json.dumps(
                normalized_updates.pop("participants"),
                sort_keys=True,
            )
        if "rounds" in normalized_updates:
            normalized_updates["rounds_json"] = json.dumps(
                normalized_updates.pop("rounds"),
                sort_keys=True,
            )
        if isinstance(normalized_updates.get("opened_at"), datetime):
            normalized_updates["opened_at"] = normalized_updates["opened_at"].isoformat()
        if isinstance(normalized_updates.get("updated_at"), datetime):
            normalized_updates["updated_at"] = normalized_updates["updated_at"].isoformat()
        if isinstance(normalized_updates.get("closed_at"), datetime):
            normalized_updates["closed_at"] = normalized_updates["closed_at"].isoformat()

        assignments = ", ".join(f"{column} = ?" for column in normalized_updates)
        params = list(normalized_updates.values()) + [meeting_id]
        connection.execute(
            f"UPDATE meeting_projection SET {assignments} WHERE meeting_id = ?",
            params,
        )

    def get_meeting_projection(
        self,
        meeting_id: str,
        *,
        connection: sqlite3.Connection | None = None,
    ) -> dict[str, Any] | None:
        query = "SELECT * FROM meeting_projection WHERE meeting_id = ?"
        params = (meeting_id,)
        if connection is not None:
            row = connection.execute(query, params).fetchone()
            return None if row is None else self._convert_meeting_projection_row(row)

        self.initialize()
        with self.connection() as owned_connection:
            row = owned_connection.execute(query, params).fetchone()
            return None if row is None else self._convert_meeting_projection_row(row)

    def list_open_meeting_projections(
        self,
        workflow_id: str | None = None,
        *,
        connection: sqlite3.Connection | None = None,
    ) -> list[dict[str, Any]]:
        query = """
            SELECT * FROM meeting_projection
            WHERE status IN (?, ?, ?, ?)
        """
        params: list[Any] = ["REQUESTED", "OPEN", "IN_ROUND", "CONSENSUS_SUBMITTED"]
        if workflow_id is not None:
            query += " AND workflow_id = ?"
            params.append(workflow_id)
        query += " ORDER BY opened_at DESC, meeting_id DESC"
        if connection is not None:
            rows = connection.execute(query, tuple(params)).fetchall()
            return [self._convert_meeting_projection_row(row) for row in rows]

        self.initialize()
        with self.connection() as owned_connection:
            rows = owned_connection.execute(query, tuple(params)).fetchall()
            return [self._convert_meeting_projection_row(row) for row in rows]

    def find_open_meeting_by_normalized_topic(
        self,
        workflow_id: str,
        normalized_topic: str,
        *,
        connection: sqlite3.Connection | None = None,
    ) -> dict[str, Any] | None:
        query = """
            SELECT * FROM meeting_projection
            WHERE workflow_id = ? AND normalized_topic = ?
              AND status IN (?, ?, ?, ?)
            ORDER BY opened_at DESC, meeting_id DESC
            LIMIT 1
        """
        params = (
            workflow_id,
            normalized_topic,
            "REQUESTED",
            "OPEN",
            "IN_ROUND",
            "CONSENSUS_SUBMITTED",
        )
        if connection is not None:
            row = connection.execute(query, params).fetchone()
            return None if row is None else self._convert_meeting_projection_row(row)

        self.initialize()
        with self.connection() as owned_connection:
            row = owned_connection.execute(query, params).fetchone()
            return None if row is None else self._convert_meeting_projection_row(row)

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
        subject = review_pack_payload.get("subject")
        approval_event_ticket_id: str | None = None
        approval_event_node_id: str | None = None
        if isinstance(subject, dict) and any(
            str(subject.get(field) or "").strip()
            for field in ("source_graph_node_id", "source_ticket_id", "source_node_id")
        ):
            approval_event_ticket_id, _approval_event_graph_node_id, approval_event_node_id = (
                resolve_graph_only_review_subject_execution_identity(
                    self,
                    workflow_id=workflow_id,
                    subject=subject,
                    connection=connection,
                )
            )

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
                "node_id": approval_event_node_id,
                "ticket_id": approval_event_ticket_id,
            },
            occurred_at=occurred_at,
        )
        if event_row is None:
            existing = self.get_approval_by_id(connection, approval_id)
            if existing is None:
                raise RuntimeError("Approval request idempotency conflict without existing approval row.")
            if review_pack_requires_board_advisory(review_pack_payload):
                self._ensure_board_advisory_session_for_approval(
                    connection,
                    approval=existing,
                    review_pack=review_pack_payload,
                )
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
        self._rebuild_retrieval_review_summary_fts(connection)
        created = self.get_approval_by_id(connection, approval_id)
        if created is None:
            raise RuntimeError("Approval row was not persisted.")
        if review_pack_requires_board_advisory(review_pack_payload):
            self._ensure_board_advisory_session_for_approval(
                connection,
                approval=created,
                review_pack=review_pack_payload,
            )
            created = self.get_approval_by_id(connection, approval_id)
            if created is None:
                raise RuntimeError("Approval row vanished after advisory session creation.")
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
        self._rebuild_retrieval_review_summary_fts(connection)
        updated = self.get_approval_by_id(connection, approval_id)
        if updated is None:
            raise RuntimeError("Approval disappeared after resolution.")
        return updated

    def _ensure_board_advisory_session_for_approval(
        self,
        connection: sqlite3.Connection,
        *,
        approval: dict[str, Any],
        review_pack: dict[str, Any],
    ) -> dict[str, Any]:
        existing = self.get_board_advisory_session_for_approval(
            str(approval["approval_id"]),
            connection=connection,
        )
        if existing is not None:
            return existing
        workflow_id = str(approval["workflow_id"])
        governance_profile = self.get_latest_governance_profile(workflow_id, connection=connection)
        if governance_profile is None:
            raise RuntimeError("Governance profile is required before creating a board advisory session.")
        session = build_board_advisory_session(
            workflow_id=workflow_id,
            approval_id=str(approval["approval_id"]),
            review_pack_id=str(approval["review_pack_id"]),
            review_pack=review_pack,
            source_version=resolve_workflow_graph_version(self, workflow_id, connection=connection),
            governance_profile_ref=str(governance_profile["profile_id"]),
        )
        created = self.create_board_advisory_session(connection, session)
        advisory_event = self.insert_event(
            connection,
            event_type=EVENT_BOARD_ADVISORY_SESSION_OPENED,
            actor_type="system",
            actor_id="board-review",
            workflow_id=workflow_id,
            idempotency_key=f"board-advisory-open:{approval['approval_id']}",
            causation_id=None,
            correlation_id=workflow_id,
            payload={
                "session_id": created["session_id"],
                "approval_id": created["approval_id"],
                "review_pack_id": created["review_pack_id"],
                "trigger_type": created["trigger_type"],
                "source_version": created["source_version"],
                "governance_profile_ref": created["governance_profile_ref"],
                "affected_nodes": list(created["affected_nodes"]),
                "status": created["status"],
            },
            occurred_at=approval["created_at"],
        )
        if advisory_event is None:
            raise RuntimeError("Board advisory session open event idempotency conflict.")
        return created

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

    def _convert_meeting_projection_row(self, row: sqlite3.Row) -> dict[str, Any]:
        converted = dict(row)
        for field in ("opened_at", "updated_at", "closed_at"):
            if converted.get(field):
                converted[field] = datetime.fromisoformat(converted[field])
        converted["participants"] = json.loads(converted.get("participants_json") or "[]")
        converted["rounds"] = json.loads(converted.get("rounds_json") or "[]")
        return converted

    def _convert_compiled_context_bundle_row(self, row: sqlite3.Row) -> dict[str, Any]:
        converted = dict(row)
        converted["compiled_at"] = datetime.fromisoformat(converted["compiled_at"])
        converted["payload"] = json.loads(converted["payload_json"])
        converted["version_int"] = int(converted.get("version_int") or 0)
        return converted

    def _convert_compile_manifest_row(self, row: sqlite3.Row) -> dict[str, Any]:
        converted = dict(row)
        converted["compiled_at"] = datetime.fromisoformat(converted["compiled_at"])
        converted["payload"] = json.loads(converted["payload_json"])
        converted["version_int"] = int(converted.get("version_int") or 0)
        return converted

    def _convert_compiled_execution_package_row(self, row: sqlite3.Row) -> dict[str, Any]:
        converted = dict(row)
        converted["compiled_at"] = datetime.fromisoformat(converted["compiled_at"])
        converted["payload"] = json.loads(converted["payload_json"])
        converted["version_int"] = int(converted.get("version_int") or 0)
        return converted

    def _convert_process_asset_index_row(self, row: sqlite3.Row) -> dict[str, Any]:
        converted = dict(row)
        if converted.get("updated_at"):
            converted["updated_at"] = datetime.fromisoformat(converted["updated_at"])
        converted["version_int"] = (
            int(converted["version_int"]) if converted.get("version_int") is not None else None
        )
        converted["linked_process_asset_refs"] = json.loads(
            converted.get("linked_process_asset_refs_json") or "[]"
        )
        converted["consumable_by"] = json.loads(converted.get("consumable_by_json") or "[]")
        converted["source_metadata"] = json.loads(converted.get("source_metadata_json") or "{}")
        return converted

    def _convert_governance_profile_row(self, row: sqlite3.Row) -> dict[str, Any]:
        converted = dict(row)
        converted["version_int"] = int(converted.get("version_int") or 0)
        converted["auto_approval_scope"] = json.loads(converted.get("auto_approval_scope_json") or "[]")
        converted["expert_review_targets"] = json.loads(converted.get("expert_review_targets_json") or "[]")
        converted["audit_materialization_policy"] = json.loads(
            converted.get("audit_materialization_policy_json") or "{}"
        )
        converted.pop("auto_approval_scope_json", None)
        converted.pop("expert_review_targets_json", None)
        converted.pop("audit_materialization_policy_json", None)
        return converted

    def _convert_board_advisory_session_row(self, row: sqlite3.Row) -> dict[str, Any]:
        converted = dict(row)
        converted["affected_nodes"] = json.loads(converted.get("affected_nodes_json") or "[]")
        converted["working_turns"] = json.loads(converted.get("working_turns_json") or "[]")
        converted["decision_pack_refs"] = json.loads(converted.get("decision_pack_refs_json") or "[]")
        converted["board_decision"] = (
            json.loads(converted["board_decision_json"])
            if converted.get("board_decision_json") not in {None, ""}
            else None
        )
        converted["latest_patch_proposal"] = (
            json.loads(converted["latest_patch_proposal_json"])
            if converted.get("latest_patch_proposal_json") not in {None, ""}
            else None
        )
        converted["approved_patch"] = (
            json.loads(converted["approved_patch_json"])
            if converted.get("approved_patch_json") not in {None, ""}
            else None
        )
        converted["focus_node_ids"] = json.loads(converted.get("focus_node_ids_json") or "[]")
        for field in ("created_at", "updated_at"):
            if converted.get(field):
                converted[field] = datetime.fromisoformat(converted[field])
        converted.pop("affected_nodes_json", None)
        converted.pop("working_turns_json", None)
        converted.pop("decision_pack_refs_json", None)
        converted.pop("board_decision_json", None)
        converted.pop("latest_patch_proposal_json", None)
        converted.pop("approved_patch_json", None)
        converted.pop("focus_node_ids_json", None)
        return converted

    def _convert_board_advisory_analysis_run_row(self, row: sqlite3.Row) -> dict[str, Any]:
        converted = dict(row)
        for field in ("created_at", "started_at", "finished_at"):
            if converted.get(field):
                converted[field] = datetime.fromisoformat(converted[field])
        converted["attempt_int"] = int(converted.get("attempt_int") or 0)
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
        converted["workflow_profile"] = str(converted.get("workflow_profile") or "STANDARD")
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

    def _convert_planned_placeholder_projection_row(self, row: sqlite3.Row) -> dict[str, Any]:
        converted = dict(row)
        if converted.get("updated_at"):
            converted["updated_at"] = datetime.fromisoformat(converted["updated_at"])
        converted["version"] = int(converted.get("version") or 0)
        return converted

    def _convert_runtime_node_projection_row(self, row: sqlite3.Row) -> dict[str, Any]:
        converted = dict(row)
        if converted.get("updated_at"):
            converted["updated_at"] = datetime.fromisoformat(converted["updated_at"])
        converted["version"] = int(converted.get("version") or 0)
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
        return normalize_employee_projection_profiles(converted)

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

    def _build_retrieval_match_query(self, normalized_terms: list[str]) -> str | None:
        unique_terms = [term.strip().lower() for term in normalized_terms if term and term.strip()]
        if not unique_terms:
            return None
        deduplicated = list(dict.fromkeys(unique_terms))
        return " OR ".join(f'"{term.replace("\"", "\"\"")}"' for term in deduplicated)

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
        ordered = sorted(
            candidates,
            key=lambda candidate: (
                -len(candidate.get("matched_terms") or []),
                float(candidate.get("fts_rank") or 1_000_000.0),
                -(
                    candidate["updated_at"].timestamp()
                    if isinstance(candidate.get("updated_at"), datetime)
                    else 0.0
                ),
                str(candidate.get("channel") or ""),
                str(candidate.get("source_ref") or ""),
            ),
        )
        deduplicated: list[dict[str, Any]] = []
        seen_source_refs: set[str] = set()
        for candidate in ordered:
            source_ref = str(candidate.get("source_ref") or "")
            if source_ref in seen_source_refs:
                continue
            seen_source_refs.add(source_ref)
            deduplicated.append(candidate)
        return deduplicated

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

    def _ensure_retrieval_review_summary_fts(self, connection: sqlite3.Connection) -> None:
        connection.execute(
            f"""
            CREATE VIRTUAL TABLE IF NOT EXISTS {RETRIEVAL_REVIEW_SUMMARY_FTS}
            USING fts5(
                source_ref UNINDEXED,
                workflow_id UNINDEXED,
                tenant_id UNINDEXED,
                workspace_id UNINDEXED,
                status UNINDEXED,
                updated_at UNINDEXED,
                source_ticket_id UNINDEXED,
                headline_text,
                summary_text,
                detail_text
            )
            """
        )

    def _ensure_retrieval_incident_summary_fts(self, connection: sqlite3.Connection) -> None:
        connection.execute(
            f"""
            CREATE VIRTUAL TABLE IF NOT EXISTS {RETRIEVAL_INCIDENT_SUMMARY_FTS}
            USING fts5(
                source_ref UNINDEXED,
                workflow_id UNINDEXED,
                tenant_id UNINDEXED,
                workspace_id UNINDEXED,
                status UNINDEXED,
                updated_at UNINDEXED,
                source_ticket_id UNINDEXED,
                incident_type,
                fingerprint,
                headline_text,
                summary_text
            )
            """
        )

    def _ensure_retrieval_artifact_summary_fts(self, connection: sqlite3.Connection) -> None:
        connection.execute(
            f"""
            CREATE VIRTUAL TABLE IF NOT EXISTS {RETRIEVAL_ARTIFACT_SUMMARY_FTS}
            USING fts5(
                source_ref UNINDEXED,
                workflow_id UNINDEXED,
                tenant_id UNINDEXED,
                workspace_id UNINDEXED,
                lifecycle_status UNINDEXED,
                materialization_status UNINDEXED,
                updated_at UNINDEXED,
                source_ticket_id UNINDEXED,
                path_text,
                kind_text,
                media_type_text,
                summary_text,
                body_text
            )
            """
        )

    def _rebuild_retrieval_review_summary_fts(self, connection: sqlite3.Connection) -> None:
        connection.execute(f"DELETE FROM {RETRIEVAL_REVIEW_SUMMARY_FTS}")
        rows = connection.execute(
            """
            SELECT
                approval_projection.*,
                COALESCE(workflow_projection.tenant_id, ?) AS scope_tenant_id,
                COALESCE(workflow_projection.workspace_id, ?) AS scope_workspace_id
            FROM approval_projection
            LEFT JOIN workflow_projection
              ON workflow_projection.workflow_id = approval_projection.workflow_id
            """
            ,
            (DEFAULT_TENANT_ID, DEFAULT_WORKSPACE_ID),
        ).fetchall()
        for row in rows:
            approval = self._convert_approval_row(row)
            payload = approval["payload"]
            review_pack = payload.get("review_pack") or {}
            subject = review_pack.get("subject") or {}
            recommendation = review_pack.get("recommendation") or {}
            resolution = payload.get("resolution") or {}
            headline_text = str(subject.get("title") or payload.get("inbox_title") or "")
            summary_text = str(
                recommendation.get("summary")
                or payload.get("inbox_summary")
                or resolution.get("board_comment")
                or ""
            )
            detail_text = str(
                " ".join(
                    value
                    for value in [
                        payload.get("inbox_title"),
                        payload.get("inbox_summary"),
                        resolution.get("board_comment"),
                    ]
                    if isinstance(value, str) and value.strip()
                )
            )
            connection.execute(
                f"""
                INSERT INTO {RETRIEVAL_REVIEW_SUMMARY_FTS} (
                    source_ref,
                    workflow_id,
                    tenant_id,
                    workspace_id,
                    status,
                    updated_at,
                    source_ticket_id,
                    headline_text,
                    summary_text,
                    detail_text
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    approval["approval_id"],
                    approval["workflow_id"],
                    str(row["scope_tenant_id"] or DEFAULT_TENANT_ID),
                    str(row["scope_workspace_id"] or DEFAULT_WORKSPACE_ID),
                    approval["status"],
                    approval["updated_at"].isoformat() if approval.get("updated_at") else "",
                    subject.get("source_ticket_id"),
                    headline_text,
                    summary_text,
                    detail_text,
                ),
            )

    def _rebuild_retrieval_incident_summary_fts(self, connection: sqlite3.Connection) -> None:
        connection.execute(f"DELETE FROM {RETRIEVAL_INCIDENT_SUMMARY_FTS}")
        rows = connection.execute(
            """
            SELECT
                incident_projection.*,
                COALESCE(workflow_projection.tenant_id, ?) AS scope_tenant_id,
                COALESCE(workflow_projection.workspace_id, ?) AS scope_workspace_id
            FROM incident_projection
            LEFT JOIN workflow_projection
              ON workflow_projection.workflow_id = incident_projection.workflow_id
            """,
            (DEFAULT_TENANT_ID, DEFAULT_WORKSPACE_ID),
        ).fetchall()
        for row in rows:
            incident = self._convert_incident_projection_row(row)
            payload = incident["payload"]
            connection.execute(
                f"""
                INSERT INTO {RETRIEVAL_INCIDENT_SUMMARY_FTS} (
                    source_ref,
                    workflow_id,
                    tenant_id,
                    workspace_id,
                    status,
                    updated_at,
                    source_ticket_id,
                    incident_type,
                    fingerprint,
                    headline_text,
                    summary_text
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    incident["incident_id"],
                    incident["workflow_id"],
                    str(row["scope_tenant_id"] or DEFAULT_TENANT_ID),
                    str(row["scope_workspace_id"] or DEFAULT_WORKSPACE_ID),
                    incident["status"],
                    incident["updated_at"].isoformat() if incident.get("updated_at") else "",
                    incident.get("ticket_id"),
                    incident.get("incident_type"),
                    incident.get("fingerprint"),
                    str(payload.get("headline") or ""),
                    str(payload.get("summary") or ""),
                ),
            )

    def _rebuild_retrieval_artifact_summary_fts(self, connection: sqlite3.Connection) -> None:
        connection.execute(f"DELETE FROM {RETRIEVAL_ARTIFACT_SUMMARY_FTS}")
        if self.artifact_store is None:
            return

        rows = connection.execute(
            """
            SELECT
                artifact_index.*,
                COALESCE(workflow_projection.tenant_id, ?) AS scope_tenant_id,
                COALESCE(workflow_projection.workspace_id, ?) AS scope_workspace_id
            FROM artifact_index
            LEFT JOIN workflow_projection
              ON workflow_projection.workflow_id = artifact_index.workflow_id
            """,
            (DEFAULT_TENANT_ID, DEFAULT_WORKSPACE_ID),
        ).fetchall()
        for row in rows:
            artifact = self._convert_artifact_index_row(row)
            if str(artifact.get("lifecycle_status") or "") != "ACTIVE":
                continue
            if str(artifact.get("materialization_status") or "") != "MATERIALIZED":
                continue
            if normalize_artifact_kind(str(artifact.get("kind") or "")) not in {"TEXT", "MARKDOWN", "JSON"}:
                continue
            artifact_body = self._read_retrieval_artifact_body(artifact)
            if artifact_body is None:
                continue
            connection.execute(
                f"""
                INSERT INTO {RETRIEVAL_ARTIFACT_SUMMARY_FTS} (
                    source_ref,
                    workflow_id,
                    tenant_id,
                    workspace_id,
                    lifecycle_status,
                    materialization_status,
                    updated_at,
                    source_ticket_id,
                    path_text,
                    kind_text,
                    media_type_text,
                    summary_text,
                    body_text
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    artifact["artifact_ref"],
                    artifact["workflow_id"],
                    str(row["scope_tenant_id"] or DEFAULT_TENANT_ID),
                    str(row["scope_workspace_id"] or DEFAULT_WORKSPACE_ID),
                    artifact.get("lifecycle_status"),
                    artifact.get("materialization_status"),
                    artifact["created_at"].isoformat() if artifact.get("created_at") else "",
                    artifact.get("ticket_id"),
                    str(artifact.get("path") or ""),
                    str(artifact.get("kind") or ""),
                    str(artifact.get("media_type") or ""),
                    self._summarize_retrieval_text(artifact_body),
                    artifact_body,
                ),
            )

    def _event_category(self, event_type: str) -> str:
        if event_type == EVENT_SYSTEM_INITIALIZED:
            return "system"
        if event_type == EVENT_SCHEDULER_ORCHESTRATION_RECORDED:
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
            EVENT_PROVIDER_ATTEMPT_STARTED,
            EVENT_PROVIDER_FIRST_TOKEN_RECEIVED,
            EVENT_PROVIDER_RETRY_SCHEDULED,
            EVENT_PROVIDER_ATTEMPT_FINISHED,
            EVENT_PROVIDER_FAILOVER_SELECTED,
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
            EVENT_ARTIFACT_IMPORTED,
            EVENT_ARTIFACT_CLEANUP_COMPLETED,
            EVENT_SCHEDULER_ORCHESTRATION_RECORDED,
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
            EVENT_PROVIDER_ATTEMPT_STARTED,
            EVENT_PROVIDER_FIRST_TOKEN_RECEIVED,
            EVENT_PROVIDER_RETRY_SCHEDULED,
            EVENT_PROVIDER_ATTEMPT_FINISHED,
            EVENT_PROVIDER_FAILOVER_SELECTED,
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
        if event["event_type"] == EVENT_PROVIDER_ATTEMPT_STARTED:
            return f"PROVIDER_ATTEMPT_STARTED for {event.get('ticket_id') or event['workflow_id']}"
        if event["event_type"] == EVENT_PROVIDER_FIRST_TOKEN_RECEIVED:
            return f"PROVIDER_FIRST_TOKEN_RECEIVED for {event.get('ticket_id') or event['workflow_id']}"
        if event["event_type"] == EVENT_PROVIDER_RETRY_SCHEDULED:
            return f"PROVIDER_RETRY_SCHEDULED for {event.get('ticket_id') or event['workflow_id']}"
        if event["event_type"] == EVENT_PROVIDER_ATTEMPT_FINISHED:
            return f"PROVIDER_ATTEMPT_FINISHED for {event.get('ticket_id') or event['workflow_id']}"
        if event["event_type"] == EVENT_PROVIDER_FAILOVER_SELECTED:
            return f"PROVIDER_FAILOVER_SELECTED for {event.get('ticket_id') or event['workflow_id']}"
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
        if event["event_type"] == EVENT_ARTIFACT_IMPORTED:
            return f"ARTIFACT_IMPORTED for {event.get('artifact_ref') or event['workflow_id']}"
        if event["event_type"] == EVENT_ARTIFACT_DELETED:
            return f"ARTIFACT_DELETED for {event.get('artifact_ref') or event['workflow_id']}"
        if event["event_type"] == EVENT_ARTIFACT_EXPIRED:
            return f"ARTIFACT_EXPIRED for {event.get('artifact_ref') or event['workflow_id']}"
        if event["event_type"] == EVENT_ARTIFACT_CLEANUP_COMPLETED:
            expired_count = event.get("payload", {}).get("expired_count")
            return f"ARTIFACT_CLEANUP_COMPLETED expired={expired_count}"
        if event["event_type"] == EVENT_SCHEDULER_ORCHESTRATION_RECORDED:
            trace_id = event.get("payload", {}).get("runner_idempotency_key") or event["workflow_id"]
            return f"SCHEDULER_ORCHESTRATION_RECORDED {trace_id}"
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
        if event_type == EVENT_SCHEDULER_ORCHESTRATION_RECORDED:
            return {
                "invalidate": ["dashboard"],
                "refresh_policy": "debounced",
                "refresh_after_ms": 250,
                "toast": "Scheduler orchestration recorded.",
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
        if event_type in {
            EVENT_PROVIDER_ATTEMPT_STARTED,
            EVENT_PROVIDER_FIRST_TOKEN_RECEIVED,
            EVENT_PROVIDER_RETRY_SCHEDULED,
            EVENT_PROVIDER_ATTEMPT_FINISHED,
            EVENT_PROVIDER_FAILOVER_SELECTED,
        }:
            return {
                "invalidate": ["dashboard"],
                "refresh_policy": "debounced",
                "refresh_after_ms": 250,
                "toast": "Provider audit updated.",
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
            "workflow_profile": "TEXT NOT NULL DEFAULT 'STANDARD'",
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
            "graph_version": "TEXT",
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

    def _ensure_runtime_node_projection_shape(self, connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS runtime_node_projection (
                workflow_id TEXT NOT NULL,
                graph_node_id TEXT NOT NULL,
                node_id TEXT NOT NULL,
                runtime_node_id TEXT NOT NULL,
                latest_ticket_id TEXT NOT NULL,
                status TEXT NOT NULL,
                blocking_reason_code TEXT,
                graph_version TEXT,
                updated_at TEXT NOT NULL,
                version INTEGER NOT NULL,
                PRIMARY KEY (workflow_id, graph_node_id)
            )
            """
        )
        existing_columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(runtime_node_projection)").fetchall()
        }
        required_columns = {
            "workflow_id": "TEXT",
            "graph_node_id": "TEXT",
            "node_id": "TEXT",
            "runtime_node_id": "TEXT",
            "latest_ticket_id": "TEXT",
            "status": "TEXT",
            "blocking_reason_code": "TEXT",
            "updated_at": "TEXT",
            "version": "INTEGER",
        }
        for column_name, column_type in required_columns.items():
            if column_name not in existing_columns:
                connection.execute(
                    f"ALTER TABLE runtime_node_projection ADD COLUMN {column_name} {column_type}"
                )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_runtime_node_projection_node_id ON runtime_node_projection(node_id)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_runtime_node_projection_runtime_node_id ON runtime_node_projection(runtime_node_id)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_runtime_node_projection_latest_ticket_id ON runtime_node_projection(latest_ticket_id)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_runtime_node_projection_status ON runtime_node_projection(status)"
        )

    def _ensure_planned_placeholder_projection_shape(self, connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS planned_placeholder_projection (
                workflow_id TEXT NOT NULL,
                node_id TEXT NOT NULL,
                graph_node_id TEXT NOT NULL,
                graph_version TEXT NOT NULL,
                status TEXT NOT NULL,
                reason_code TEXT,
                open_incident_id TEXT,
                materialization_hint TEXT,
                updated_at TEXT NOT NULL,
                version INTEGER NOT NULL,
                PRIMARY KEY (workflow_id, node_id)
            )
            """
        )
        existing_columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(planned_placeholder_projection)").fetchall()
        }
        required_columns = {
            "workflow_id": "TEXT",
            "node_id": "TEXT",
            "graph_node_id": "TEXT",
            "graph_version": "TEXT",
            "status": "TEXT",
            "reason_code": "TEXT",
            "open_incident_id": "TEXT",
            "materialization_hint": "TEXT",
            "updated_at": "TEXT",
            "version": "INTEGER",
        }
        for column_name, column_type in required_columns.items():
            if column_name not in existing_columns:
                connection.execute(
                    f"ALTER TABLE planned_placeholder_projection ADD COLUMN {column_name} {column_type}"
                )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_planned_placeholder_projection_workflow_id ON planned_placeholder_projection(workflow_id)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_planned_placeholder_projection_status ON planned_placeholder_projection(status)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_planned_placeholder_projection_graph_node_id ON planned_placeholder_projection(graph_node_id)"
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

    def _ensure_meeting_projection_shape(self, connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS meeting_projection (
                meeting_id TEXT PRIMARY KEY,
                workflow_id TEXT NOT NULL,
                meeting_type TEXT NOT NULL,
                topic TEXT NOT NULL,
                normalized_topic TEXT NOT NULL,
                status TEXT NOT NULL,
                review_status TEXT,
                source_ticket_id TEXT NOT NULL,
                source_graph_node_id TEXT NOT NULL,
                source_node_id TEXT NOT NULL,
                review_pack_id TEXT,
                opened_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                closed_at TEXT,
                current_round TEXT,
                recorder_employee_id TEXT NOT NULL,
                participants_json TEXT NOT NULL,
                rounds_json TEXT NOT NULL,
                consensus_summary TEXT,
                no_consensus_reason TEXT
            )
            """
        )
        existing_columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(meeting_projection)").fetchall()
        }
        required_columns = {
            "meeting_id": "TEXT",
            "workflow_id": "TEXT",
            "meeting_type": "TEXT",
            "topic": "TEXT",
            "normalized_topic": "TEXT",
            "status": "TEXT",
            "review_status": "TEXT",
            "source_ticket_id": "TEXT",
            "source_graph_node_id": "TEXT",
            "source_node_id": "TEXT",
            "review_pack_id": "TEXT",
            "opened_at": "TEXT",
            "updated_at": "TEXT",
            "closed_at": "TEXT",
            "current_round": "TEXT",
            "recorder_employee_id": "TEXT",
            "participants_json": "TEXT",
            "rounds_json": "TEXT",
            "consensus_summary": "TEXT",
            "no_consensus_reason": "TEXT",
        }
        for column_name, column_type in required_columns.items():
            if column_name not in existing_columns:
                connection.execute(
                    f"ALTER TABLE meeting_projection ADD COLUMN {column_name} {column_type}"
                )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_meeting_projection_workflow_id ON meeting_projection(workflow_id)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_meeting_projection_status ON meeting_projection(status)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_meeting_projection_normalized_topic ON meeting_projection(workflow_id, normalized_topic)"
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
                version_ref TEXT,
                version_int INTEGER,
                supersedes_ref TEXT,
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
            "version_ref": "TEXT",
            "version_int": "INTEGER",
            "supersedes_ref": "TEXT",
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
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_compiled_context_bundle_ticket_version ON compiled_context_bundle(ticket_id, version_int)"
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
                version_ref TEXT,
                version_int INTEGER,
                supersedes_ref TEXT,
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
            "version_ref": "TEXT",
            "version_int": "INTEGER",
            "supersedes_ref": "TEXT",
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
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_compile_manifest_ticket_version ON compile_manifest(ticket_id, version_int)"
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
                version_ref TEXT,
                version_int INTEGER,
                supersedes_ref TEXT,
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
            "version_ref": "TEXT",
            "version_int": "INTEGER",
            "supersedes_ref": "TEXT",
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
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_compiled_execution_package_ticket_version ON compiled_execution_package(ticket_id, version_int)"
        )

    def _ensure_process_asset_index_shape(self, connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS process_asset_index (
                process_asset_ref TEXT PRIMARY KEY,
                canonical_ref TEXT NOT NULL,
                version_int INTEGER,
                supersedes_ref TEXT,
                process_asset_kind TEXT NOT NULL,
                workflow_id TEXT,
                producer_ticket_id TEXT,
                producer_node_id TEXT,
                graph_version TEXT,
                content_hash TEXT,
                visibility_status TEXT NOT NULL,
                linked_process_asset_refs_json TEXT NOT NULL DEFAULT '[]',
                summary TEXT,
                consumable_by_json TEXT NOT NULL DEFAULT '[]',
                source_metadata_json TEXT NOT NULL DEFAULT '{}',
                updated_at TEXT NOT NULL,
                version INTEGER NOT NULL
            )
            """
        )
        existing_columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(process_asset_index)").fetchall()
        }
        required_columns = {
            "process_asset_ref": "TEXT",
            "canonical_ref": "TEXT",
            "version_int": "INTEGER",
            "supersedes_ref": "TEXT",
            "process_asset_kind": "TEXT",
            "workflow_id": "TEXT",
            "producer_ticket_id": "TEXT",
            "producer_node_id": "TEXT",
            "graph_version": "TEXT",
            "content_hash": "TEXT",
            "visibility_status": "TEXT",
            "linked_process_asset_refs_json": "TEXT NOT NULL DEFAULT '[]'",
            "summary": "TEXT",
            "consumable_by_json": "TEXT NOT NULL DEFAULT '[]'",
            "source_metadata_json": "TEXT NOT NULL DEFAULT '{}'",
            "updated_at": "TEXT",
            "version": "INTEGER",
        }
        for column_name, column_type in required_columns.items():
            if column_name not in existing_columns:
                connection.execute(
                    f"ALTER TABLE process_asset_index ADD COLUMN {column_name} {column_type}"
                )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_process_asset_index_producer_ticket ON process_asset_index(producer_ticket_id)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_process_asset_index_workflow_kind_node ON process_asset_index(workflow_id, process_asset_kind, producer_node_id, visibility_status)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_process_asset_index_kind_visibility ON process_asset_index(process_asset_kind, visibility_status)"
        )

    def _ensure_governance_profile_shape(self, connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS governance_profile (
                profile_id TEXT PRIMARY KEY,
                workflow_id TEXT NOT NULL,
                approval_mode TEXT NOT NULL,
                audit_mode TEXT NOT NULL,
                auto_approval_scope_json TEXT NOT NULL DEFAULT '[]',
                expert_review_targets_json TEXT NOT NULL DEFAULT '[]',
                audit_materialization_policy_json TEXT NOT NULL DEFAULT '{}',
                source_ref TEXT NOT NULL,
                supersedes_ref TEXT,
                effective_from_event TEXT NOT NULL,
                version_int INTEGER NOT NULL
            )
            """
        )
        existing_columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(governance_profile)").fetchall()
        }
        required_columns = {
            "profile_id": "TEXT",
            "workflow_id": "TEXT",
            "approval_mode": "TEXT",
            "audit_mode": "TEXT",
            "auto_approval_scope_json": "TEXT NOT NULL DEFAULT '[]'",
            "expert_review_targets_json": "TEXT NOT NULL DEFAULT '[]'",
            "audit_materialization_policy_json": "TEXT NOT NULL DEFAULT '{}'",
            "source_ref": "TEXT",
            "supersedes_ref": "TEXT",
            "effective_from_event": "TEXT",
            "version_int": "INTEGER",
        }
        for column_name, column_type in required_columns.items():
            if column_name not in existing_columns:
                connection.execute(
                    f"ALTER TABLE governance_profile ADD COLUMN {column_name} {column_type}"
                )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_governance_profile_workflow_version ON governance_profile(workflow_id, version_int)"
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
                preferred_provider_id TEXT,
                preferred_model TEXT,
                actual_provider_id TEXT,
                actual_model TEXT,
                selection_reason TEXT,
                policy_reason TEXT,
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
            "preferred_provider_id": "TEXT",
            "preferred_model": "TEXT",
            "actual_provider_id": "TEXT",
            "actual_model": "TEXT",
            "selection_reason": "TEXT",
            "policy_reason": "TEXT",
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

    def _ensure_board_advisory_session_shape(self, connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS board_advisory_session (
                session_id TEXT PRIMARY KEY,
                workflow_id TEXT NOT NULL,
                approval_id TEXT NOT NULL UNIQUE,
                review_pack_id TEXT NOT NULL UNIQUE,
                trigger_type TEXT NOT NULL,
                source_version TEXT NOT NULL,
                governance_profile_ref TEXT NOT NULL,
                affected_nodes_json TEXT NOT NULL,
                working_turns_json TEXT NOT NULL DEFAULT '[]',
                decision_pack_refs_json TEXT NOT NULL,
                board_decision_json TEXT,
                latest_patch_proposal_ref TEXT,
                latest_patch_proposal_json TEXT,
                approved_patch_ref TEXT,
                approved_patch_json TEXT,
                patched_graph_version TEXT,
                latest_timeline_index_ref TEXT,
                latest_transcript_archive_artifact_ref TEXT,
                timeline_archive_version_int INTEGER,
                focus_node_ids_json TEXT NOT NULL DEFAULT '[]',
                latest_analysis_error TEXT,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        existing_columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(board_advisory_session)").fetchall()
        }
        required_columns = {
            "session_id": "TEXT",
            "workflow_id": "TEXT",
            "approval_id": "TEXT",
            "review_pack_id": "TEXT",
            "trigger_type": "TEXT",
            "source_version": "TEXT",
            "governance_profile_ref": "TEXT",
            "affected_nodes_json": "TEXT NOT NULL DEFAULT '[]'",
            "working_turns_json": "TEXT NOT NULL DEFAULT '[]'",
            "decision_pack_refs_json": "TEXT NOT NULL DEFAULT '[]'",
            "board_decision_json": "TEXT",
            "latest_patch_proposal_ref": "TEXT",
            "latest_patch_proposal_json": "TEXT",
            "approved_patch_ref": "TEXT",
            "approved_patch_json": "TEXT",
            "patched_graph_version": "TEXT",
            "latest_timeline_index_ref": "TEXT",
                "latest_transcript_archive_artifact_ref": "TEXT",
                "timeline_archive_version_int": "INTEGER",
                "focus_node_ids_json": "TEXT NOT NULL DEFAULT '[]'",
                "latest_analysis_run_id": "TEXT",
                "latest_analysis_status": "TEXT",
                "latest_analysis_incident_id": "TEXT",
                "latest_analysis_error": "TEXT",
                "latest_analysis_trace_artifact_ref": "TEXT",
                "status": "TEXT",
                "created_at": "TEXT",
                "updated_at": "TEXT",
            }
        for column_name, column_type in required_columns.items():
            if column_name not in existing_columns:
                connection.execute(
                    f"ALTER TABLE board_advisory_session ADD COLUMN {column_name} {column_type}"
                )
        connection.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_board_advisory_session_approval_id ON board_advisory_session(approval_id)"
        )
        connection.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_board_advisory_session_review_pack_id ON board_advisory_session(review_pack_id)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_board_advisory_session_workflow_id ON board_advisory_session(workflow_id)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_board_advisory_session_status ON board_advisory_session(status)"
        )

    def _ensure_board_advisory_analysis_run_shape(self, connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS board_advisory_analysis_run (
                run_id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                workflow_id TEXT NOT NULL,
                source_graph_version TEXT NOT NULL,
                status TEXT NOT NULL,
                idempotency_key TEXT NOT NULL UNIQUE,
                attempt_int INTEGER NOT NULL,
                executor_mode TEXT NOT NULL,
                compile_request_id TEXT,
                compiled_execution_package_ref TEXT,
                proposal_ref TEXT,
                analysis_trace_artifact_ref TEXT,
                incident_id TEXT,
                error_code TEXT,
                error_message TEXT,
                created_at TEXT NOT NULL,
                started_at TEXT,
                finished_at TEXT
            )
            """
        )
        existing_columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(board_advisory_analysis_run)").fetchall()
        }
        required_columns = {
            "run_id": "TEXT",
            "session_id": "TEXT",
            "workflow_id": "TEXT",
            "source_graph_version": "TEXT",
            "status": "TEXT",
            "idempotency_key": "TEXT",
            "attempt_int": "INTEGER",
            "executor_mode": "TEXT",
            "compile_request_id": "TEXT",
            "compiled_execution_package_ref": "TEXT",
            "proposal_ref": "TEXT",
            "analysis_trace_artifact_ref": "TEXT",
            "incident_id": "TEXT",
            "error_code": "TEXT",
            "error_message": "TEXT",
            "created_at": "TEXT",
            "started_at": "TEXT",
            "finished_at": "TEXT",
        }
        for column_name, column_type in required_columns.items():
            if column_name not in existing_columns:
                connection.execute(
                    f"ALTER TABLE board_advisory_analysis_run ADD COLUMN {column_name} {column_type}"
                )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_board_advisory_analysis_run_session_id ON board_advisory_analysis_run(session_id)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_board_advisory_analysis_run_workflow_id ON board_advisory_analysis_run(workflow_id)"
        )
        connection.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_board_advisory_analysis_run_idempotency_key ON board_advisory_analysis_run(idempotency_key)"
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
            for employee in build_default_employee_roster():
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
