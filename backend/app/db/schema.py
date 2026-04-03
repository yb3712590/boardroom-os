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
    tenant_id TEXT NOT NULL,
    workspace_id TEXT NOT NULL,
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

CREATE TABLE IF NOT EXISTS ticket_projection (
    ticket_id TEXT PRIMARY KEY,
    workflow_id TEXT NOT NULL,
    node_id TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    workspace_id TEXT NOT NULL,
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
);

CREATE TABLE IF NOT EXISTS node_projection (
    workflow_id TEXT NOT NULL,
    node_id TEXT NOT NULL,
    latest_ticket_id TEXT NOT NULL,
    status TEXT NOT NULL,
    blocking_reason_code TEXT,
    updated_at TEXT NOT NULL,
    version INTEGER NOT NULL,
    PRIMARY KEY (workflow_id, node_id)
);

CREATE TABLE IF NOT EXISTS employee_projection (
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
);

CREATE TABLE IF NOT EXISTS worker_bootstrap_state (
    worker_id TEXT NOT NULL,
    credential_version INTEGER NOT NULL,
    tenant_id TEXT NOT NULL,
    workspace_id TEXT NOT NULL,
    revoked_before TEXT,
    rotated_at TEXT,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (worker_id, tenant_id, workspace_id)
);

CREATE TABLE IF NOT EXISTS worker_session (
    session_id TEXT PRIMARY KEY,
    worker_id TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    workspace_id TEXT NOT NULL,
    issued_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    revoked_at TEXT,
    credential_version INTEGER NOT NULL
);

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
    revoke_reason TEXT
);

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
);

CREATE TABLE IF NOT EXISTS incident_projection (
    incident_id TEXT PRIMARY KEY,
    workflow_id TEXT NOT NULL,
    node_id TEXT,
    ticket_id TEXT,
    provider_id TEXT,
    incident_type TEXT NOT NULL,
    status TEXT NOT NULL,
    severity TEXT,
    fingerprint TEXT NOT NULL,
    circuit_breaker_state TEXT,
    opened_at TEXT NOT NULL,
    closed_at TEXT,
    payload_json TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    version INTEGER NOT NULL
);

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
);

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
);

CREATE TABLE IF NOT EXISTS compiled_execution_package (
    compile_request_id TEXT PRIMARY KEY,
    ticket_id TEXT NOT NULL,
    workflow_id TEXT NOT NULL,
    node_id TEXT NOT NULL,
    compiler_version TEXT NOT NULL,
    compiled_at TEXT NOT NULL,
    package_version TEXT NOT NULL,
    payload_json TEXT NOT NULL
);

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
    comparison_json TEXT NOT NULL
);

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
    expires_at TEXT,
    deleted_at TEXT,
    deleted_by TEXT,
    delete_reason TEXT,
    storage_deleted_at TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_compiled_context_bundle_ticket_id
ON compiled_context_bundle(ticket_id);

CREATE INDEX IF NOT EXISTS idx_compiled_context_bundle_compile_request_id
ON compiled_context_bundle(compile_request_id);

CREATE INDEX IF NOT EXISTS idx_compile_manifest_ticket_id
ON compile_manifest(ticket_id);

CREATE INDEX IF NOT EXISTS idx_compile_manifest_compile_request_id
ON compile_manifest(compile_request_id);

CREATE INDEX IF NOT EXISTS idx_compiled_execution_package_ticket_id
ON compiled_execution_package(ticket_id);

CREATE INDEX IF NOT EXISTS idx_compiled_execution_package_compile_request_id
ON compiled_execution_package(compile_request_id);

CREATE INDEX IF NOT EXISTS idx_artifact_index_ticket_id
ON artifact_index(ticket_id);

CREATE INDEX IF NOT EXISTS idx_artifact_index_workflow_id
ON artifact_index(workflow_id);

CREATE INDEX IF NOT EXISTS idx_artifact_index_node_id
ON artifact_index(node_id);

CREATE INDEX IF NOT EXISTS idx_incident_projection_workflow_id
ON incident_projection(workflow_id);

CREATE INDEX IF NOT EXISTS idx_incident_projection_status
ON incident_projection(status);

CREATE INDEX IF NOT EXISTS idx_incident_projection_provider_id
ON incident_projection(provider_id);

CREATE INDEX IF NOT EXISTS idx_incident_projection_fingerprint
ON incident_projection(fingerprint);

CREATE INDEX IF NOT EXISTS idx_worker_session_worker_id
ON worker_session(worker_id);

CREATE INDEX IF NOT EXISTS idx_worker_bootstrap_state_worker_id
ON worker_bootstrap_state(worker_id);

CREATE INDEX IF NOT EXISTS idx_worker_bootstrap_state_scope
ON worker_bootstrap_state(tenant_id, workspace_id);

CREATE INDEX IF NOT EXISTS idx_worker_session_scope
ON worker_session(tenant_id, workspace_id);

CREATE INDEX IF NOT EXISTS idx_worker_session_expires_at
ON worker_session(expires_at);

CREATE INDEX IF NOT EXISTS idx_worker_delivery_grant_session_id
ON worker_delivery_grant(session_id);

CREATE INDEX IF NOT EXISTS idx_worker_delivery_grant_ticket_id
ON worker_delivery_grant(ticket_id);

CREATE INDEX IF NOT EXISTS idx_worker_delivery_grant_scope
ON worker_delivery_grant(tenant_id, workspace_id);

CREATE INDEX IF NOT EXISTS idx_worker_delivery_grant_expires_at
ON worker_delivery_grant(expires_at);

CREATE INDEX IF NOT EXISTS idx_worker_delivery_grant_revoked_at
ON worker_delivery_grant(revoked_at);

CREATE INDEX IF NOT EXISTS idx_worker_auth_rejection_log_occurred_at
ON worker_auth_rejection_log(occurred_at);

CREATE INDEX IF NOT EXISTS idx_worker_auth_rejection_log_scope
ON worker_auth_rejection_log(tenant_id, workspace_id);
"""

TABLE_SCHEMA_SQL = SCHEMA_SQL.split("CREATE INDEX IF NOT EXISTS", 1)[0]
