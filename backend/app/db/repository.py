from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any

from app.core.constants import (
    APPROVAL_STATUS_OPEN,
    NODE_STATUS_BLOCKED_FOR_BOARD_REVIEW,
    NODE_STATUS_COMPLETED,
    EVENT_BOARD_DIRECTIVE_RECEIVED,
    EVENT_BOARD_REVIEW_APPROVED,
    EVENT_BOARD_REVIEW_REJECTED,
    EVENT_BOARD_REVIEW_REQUIRED,
    EVENT_SYSTEM_INITIALIZED,
    EVENT_TICKET_COMPLETED,
    EVENT_WORKFLOW_CREATED,
)
from app.core.ids import new_prefixed_id
from app.core.reducer import (
    rebuild_node_projections,
    rebuild_ticket_projections,
    rebuild_workflow_projections,
)
from app.db.schema import SCHEMA_SQL


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
                    retry_count,
                    retry_budget,
                    timeout_sla_sec,
                    priority,
                    blocking_reason_code,
                    updated_at,
                    version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    projection["ticket_id"],
                    projection["workflow_id"],
                    projection["node_id"],
                    projection["status"],
                    projection.get("lease_owner"),
                    projection.get("lease_expires_at"),
                    projection.get("retry_count", 0),
                    projection.get("retry_budget"),
                    projection.get("timeout_sla_sec"),
                    projection.get("priority"),
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

    def refresh_projections(self, connection: sqlite3.Connection) -> None:
        events = self.list_all_events(connection)
        self.replace_workflow_projections(connection, rebuild_workflow_projections(events))
        self.replace_ticket_projections(connection, rebuild_ticket_projections(events))
        self.replace_node_projections(connection, rebuild_node_projections(events))

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

    def get_current_ticket_projection(self, ticket_id: str) -> dict[str, Any] | None:
        self.initialize()
        with self.connection() as connection:
            row = connection.execute(
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
    ) -> dict[str, Any] | None:
        self.initialize()
        with self.connection() as connection:
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
                    "related_ref": converted.get("ticket_id") or converted.get("workflow_id") or converted["event_id"],
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

    def _convert_ticket_projection_row(self, row: sqlite3.Row) -> dict[str, Any]:
        converted = dict(row)
        converted["retry_count"] = int(converted.get("retry_count") or 0)
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
        converted["version"] = int(converted["version"])
        return converted

    def _event_category(self, event_type: str) -> str:
        if event_type == EVENT_SYSTEM_INITIALIZED:
            return "system"
        if event_type == EVENT_TICKET_COMPLETED:
            return "ticket"
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
            EVENT_TICKET_COMPLETED,
            EVENT_BOARD_REVIEW_APPROVED,
        }:
            return "info"
        if event_type in {EVENT_BOARD_REVIEW_REQUIRED, EVENT_BOARD_REVIEW_REJECTED}:
            return "warning"
        return "debug"

    def _event_preview_message(self, event: dict[str, Any]) -> str:
        if event["event_type"] == EVENT_SYSTEM_INITIALIZED:
            return "SYSTEM_INITIALIZED by system"
        if event["event_type"] == EVENT_BOARD_DIRECTIVE_RECEIVED:
            return "BOARD_DIRECTIVE_RECEIVED from board"
        if event["event_type"] == EVENT_WORKFLOW_CREATED:
            return f"WORKFLOW_CREATED for {event['workflow_id']}"
        if event["event_type"] == EVENT_TICKET_COMPLETED:
            return f"TICKET_COMPLETED for {event.get('ticket_id') or event['workflow_id']}"
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
            "retry_count": "INTEGER DEFAULT 0",
            "retry_budget": "INTEGER",
            "timeout_sla_sec": "INTEGER",
            "priority": "TEXT",
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
