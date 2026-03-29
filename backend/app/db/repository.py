from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from app.contracts.runtime import CompileManifest, CompiledContextBundle
from app.core.constants import (
    APPROVAL_STATUS_OPEN,
    CIRCUIT_BREAKER_STATE_CLOSED,
    CIRCUIT_BREAKER_STATE_OPEN,
    EVENT_CIRCUIT_BREAKER_CLOSED,
    EVENT_CIRCUIT_BREAKER_OPENED,
    NODE_STATUS_BLOCKED_FOR_BOARD_REVIEW,
    NODE_STATUS_COMPLETED,
    EVENT_BOARD_DIRECTIVE_RECEIVED,
    EVENT_BOARD_REVIEW_APPROVED,
    EVENT_BOARD_REVIEW_REJECTED,
    EVENT_BOARD_REVIEW_REQUIRED,
    EVENT_INCIDENT_CLOSED,
    EVENT_INCIDENT_OPENED,
    EVENT_SYSTEM_INITIALIZED,
    EVENT_TICKET_COMPLETED,
    EVENT_TICKET_CREATED,
    EVENT_TICKET_FAILED,
    EVENT_TICKET_LEASED,
    EVENT_TICKET_RETRY_SCHEDULED,
    EVENT_TICKET_STARTED,
    EVENT_TICKET_TIMED_OUT,
    EVENT_WORKFLOW_CREATED,
    INCIDENT_TYPE_PROVIDER_EXECUTION_PAUSED,
    TICKET_STATUS_EXECUTING,
    TICKET_STATUS_LEASED,
    TICKET_STATUS_PENDING,
)
from app.core.ids import new_prefixed_id
from app.core.reducer import (
    rebuild_incident_projections,
    rebuild_node_projections,
    rebuild_ticket_projections,
    rebuild_workflow_projections,
)
from app.core.time import now_local
from app.db.schema import SCHEMA_SQL

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
        "role_profile_refs_json": ["ui_designer_primary"],
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
    def __init__(self, db_path: Path, busy_timeout_ms: int, recent_event_limit: int = 10):
        self.db_path = db_path
        self.busy_timeout_ms = busy_timeout_ms
        self.recent_event_limit = recent_event_limit

    def initialize(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as connection:
            connection.executescript(SCHEMA_SQL)
            self._ensure_approval_projection_shape(connection)
            self._ensure_ticket_projection_shape(connection)
            self._ensure_node_projection_shape(connection)
            self._ensure_employee_projection_shape(connection)
            self._ensure_incident_projection_shape(connection)
            self._seed_employee_roster(connection)

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
                    projection["workflow_id"],
                    projection["title"],
                    projection["north_star_goal"],
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
                    projection["ticket_id"],
                    projection["workflow_id"],
                    projection["node_id"],
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
            return dict(row)

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
                        converted.get("incident_id")
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
                WHERE status <> ?
                """,
                (NODE_STATUS_COMPLETED,),
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
        converted["provider_id"] = converted.get("provider_id")
        converted["board_approved"] = bool(converted.get("board_approved"))
        converted["version"] = int(converted.get("version") or 0)
        return converted

    def _convert_incident_projection_row(self, row: sqlite3.Row) -> dict[str, Any]:
        converted = dict(row)
        for field in ("opened_at", "closed_at", "updated_at"):
            if converted.get(field):
                converted[field] = datetime.fromisoformat(converted[field])
        converted["payload"] = json.loads(converted["payload_json"])
        converted["version"] = int(converted.get("version") or 0)
        return converted

    def _event_category(self, event_type: str) -> str:
        if event_type == EVENT_SYSTEM_INITIALIZED:
            return "system"
        if event_type in {
            EVENT_TICKET_CREATED,
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
        return "workflow"

    def _event_severity(self, event_type: str) -> str:
        if event_type in {
            EVENT_SYSTEM_INITIALIZED,
            EVENT_BOARD_DIRECTIVE_RECEIVED,
            EVENT_WORKFLOW_CREATED,
            EVENT_TICKET_CREATED,
            EVENT_TICKET_RETRY_SCHEDULED,
            EVENT_TICKET_LEASED,
            EVENT_TICKET_STARTED,
            EVENT_TICKET_COMPLETED,
            EVENT_BOARD_REVIEW_APPROVED,
            EVENT_INCIDENT_CLOSED,
            EVENT_CIRCUIT_BREAKER_CLOSED,
        }:
            return "info"
        if event_type in {
            EVENT_TICKET_FAILED,
            EVENT_TICKET_TIMED_OUT,
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
        if event["event_type"] == EVENT_TICKET_COMPLETED:
            return f"TICKET_COMPLETED for {event.get('ticket_id') or event['workflow_id']}"
        if event["event_type"] == EVENT_TICKET_FAILED:
            return f"TICKET_FAILED for {event.get('ticket_id') or event['workflow_id']}"
        if event["event_type"] == EVENT_TICKET_TIMED_OUT:
            return f"TICKET_TIMED_OUT for {event.get('ticket_id') or event['workflow_id']}"
        if event["event_type"] == EVENT_TICKET_RETRY_SCHEDULED:
            return f"TICKET_RETRY_SCHEDULED for {event.get('ticket_id') or event['workflow_id']}"
        if event["event_type"] == EVENT_INCIDENT_OPENED:
            if event.get("payload", {}).get("incident_type") == INCIDENT_TYPE_PROVIDER_EXECUTION_PAUSED:
                provider_id = event.get("provider_id") or event.get("payload", {}).get("provider_id")
                return f"PROVIDER_INCIDENT_OPENED for {provider_id or event['workflow_id']}"
            return f"INCIDENT_OPENED for {event.get('incident_id') or event['workflow_id']}"
        if event["event_type"] == EVENT_INCIDENT_CLOSED:
            if event.get("payload", {}).get("incident_type") == INCIDENT_TYPE_PROVIDER_EXECUTION_PAUSED:
                provider_id = event.get("provider_id") or event.get("payload", {}).get("provider_id")
                return f"PROVIDER_INCIDENT_CLOSED for {provider_id or event['workflow_id']}"
            return f"INCIDENT_CLOSED for {event.get('incident_id') or event['workflow_id']}"
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

    def _ensure_ticket_projection_shape(self, connection: sqlite3.Connection) -> None:
        existing_columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(ticket_projection)").fetchall()
        }
        required_columns = {
            "ticket_id": "TEXT",
            "workflow_id": "TEXT",
            "node_id": "TEXT",
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

    def _seed_employee_roster(self, connection: sqlite3.Connection) -> None:
        existing_count = connection.execute(
            "SELECT COUNT(*) AS total FROM employee_projection"
        ).fetchone()
        if existing_count is not None and int(existing_count["total"]) > 0:
            return

        seeded_at = now_local().isoformat()
        for employee in DEFAULT_EMPLOYEE_ROSTER:
            connection.execute(
                """
                INSERT OR IGNORE INTO employee_projection (
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
                    employee["employee_id"],
                    employee["role_type"],
                    json.dumps(employee["skill_profile_json"], sort_keys=True),
                    json.dumps(employee["personality_profile_json"], sort_keys=True),
                    json.dumps(employee["aesthetic_profile_json"], sort_keys=True),
                    employee["state"],
                    1 if employee["board_approved"] else 0,
                    employee.get("provider_id"),
                    json.dumps(employee["role_profile_refs_json"], sort_keys=True),
                    seeded_at,
                    1,
                ),
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
