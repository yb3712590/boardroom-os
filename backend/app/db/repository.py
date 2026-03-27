from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

from app.core.constants import (
    EVENT_BOARD_DIRECTIVE_RECEIVED,
    EVENT_SYSTEM_INITIALIZED,
    EVENT_WORKFLOW_CREATED,
)
from app.core.ids import new_prefixed_id
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
                    "related_ref": converted["workflow_id"],
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

    def list_events_for_testing(self) -> list[dict[str, Any]]:
        self.initialize()
        with self.connection() as connection:
            return self.list_all_events(connection)

    def _convert_event_row(self, row: sqlite3.Row) -> dict[str, Any]:
        converted = dict(row)
        converted["occurred_at"] = datetime.fromisoformat(converted["occurred_at"])
        return converted

    def _event_category(self, event_type: str) -> str:
        if event_type == EVENT_SYSTEM_INITIALIZED:
            return "system"
        return "workflow"

    def _event_severity(self, event_type: str) -> str:
        if event_type in {
            EVENT_SYSTEM_INITIALIZED,
            EVENT_BOARD_DIRECTIVE_RECEIVED,
            EVENT_WORKFLOW_CREATED,
        }:
            return "info"
        return "debug"

    def _event_preview_message(self, event: dict[str, Any]) -> str:
        if event["event_type"] == EVENT_SYSTEM_INITIALIZED:
            return "SYSTEM_INITIALIZED by system"
        if event["event_type"] == EVENT_BOARD_DIRECTIVE_RECEIVED:
            return "BOARD_DIRECTIVE_RECEIVED from board"
        if event["event_type"] == EVENT_WORKFLOW_CREATED:
            return f"WORKFLOW_CREATED for {event['workflow_id']}"
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
        return {
            "invalidate": ["dashboard", "inbox"],
            "refresh_policy": "debounced",
            "refresh_after_ms": 250,
            "toast": "Workflow created.",
        }
