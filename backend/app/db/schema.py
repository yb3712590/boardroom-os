from __future__ import annotations

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS events (
    sequence_no INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL UNIQUE,
    workflow_id TEXT,
    event_type TEXT NOT NULL,
    actor_type TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    idempotency_key TEXT NOT NULL UNIQUE,
    causation_id TEXT,
    correlation_id TEXT,
    payload_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS workflow_projection (
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
);

CREATE TABLE IF NOT EXISTS approval_projection (
    approval_id TEXT PRIMARY KEY,
    review_pack_id TEXT,
    workflow_id TEXT NOT NULL,
    approval_type TEXT NOT NULL,
    status TEXT NOT NULL,
    requested_by TEXT NOT NULL,
    resolved_by TEXT,
    resolved_at TEXT,
    created_at TEXT,
    updated_at TEXT,
    review_pack_version INTEGER,
    command_target_version INTEGER,
    payload_json TEXT NOT NULL
);
"""
