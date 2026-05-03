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
    workflow_profile TEXT NOT NULL DEFAULT 'STANDARD',
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
    actor_id TEXT,
    assignment_id TEXT,
    lease_id TEXT,
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

CREATE TABLE IF NOT EXISTS assignment_projection (
    assignment_id TEXT PRIMARY KEY,
    workflow_id TEXT NOT NULL,
    ticket_id TEXT NOT NULL,
    node_id TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    required_capabilities_json TEXT NOT NULL,
    provider_selection_json TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL,
    assignment_reason TEXT,
    assigned_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    version INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS lease_projection (
    lease_id TEXT PRIMARY KEY,
    assignment_id TEXT NOT NULL,
    workflow_id TEXT NOT NULL,
    ticket_id TEXT NOT NULL,
    node_id TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    status TEXT NOT NULL,
    lease_timeout_sec INTEGER,
    lease_expires_at TEXT,
    started_at TEXT,
    closed_at TEXT,
    failure_kind TEXT,
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
);

CREATE TABLE IF NOT EXISTS execution_attempt_projection (
    attempt_id TEXT PRIMARY KEY,
    workflow_id TEXT NOT NULL,
    ticket_id TEXT NOT NULL,
    node_id TEXT NOT NULL,
    attempt_no INTEGER NOT NULL,
    idempotency_key TEXT NOT NULL,
    provider_policy_ref TEXT NOT NULL,
    deadline_at TEXT NOT NULL,
    last_heartbeat_at TEXT,
    state TEXT NOT NULL,
    failure_kind TEXT,
    failure_fingerprint TEXT,
    updated_at TEXT NOT NULL,
    version INTEGER NOT NULL
);

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

CREATE TABLE IF NOT EXISTS actor_projection (
    actor_id TEXT PRIMARY KEY,
    employee_id TEXT,
    status TEXT NOT NULL,
    capability_set_json TEXT NOT NULL,
    provider_preferences_json TEXT NOT NULL,
    availability_json TEXT NOT NULL,
    created_from_policy TEXT,
    deactivated_reason TEXT,
    replaced_by_actor_id TEXT,
    replacement_reason TEXT,
    replacement_plan_json TEXT,
    lifecycle_reason TEXT,
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
);

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
    latest_analysis_run_id TEXT,
    latest_analysis_status TEXT,
    latest_analysis_incident_id TEXT,
    latest_analysis_error TEXT,
    latest_analysis_trace_artifact_ref TEXT,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

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
    preferred_provider_id TEXT,
    preferred_model TEXT,
    actual_provider_id TEXT,
    actual_model TEXT,
    selection_reason TEXT,
    policy_reason TEXT,
    prompt_version TEXT NOT NULL,
    provider_response_id TEXT,
    provider_policy_ref TEXT,
    provider_attempt_id TEXT,
    provider_timeout_policy_json TEXT NOT NULL DEFAULT '{}',
    provider_failure_detail_json TEXT NOT NULL DEFAULT '{}',
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

CREATE INDEX IF NOT EXISTS idx_process_asset_index_producer_ticket
ON process_asset_index(producer_ticket_id);

CREATE INDEX IF NOT EXISTS idx_process_asset_index_workflow_kind_node
ON process_asset_index(workflow_id, process_asset_kind, producer_node_id, visibility_status);

CREATE INDEX IF NOT EXISTS idx_process_asset_index_kind_visibility
ON process_asset_index(process_asset_kind, visibility_status);

CREATE UNIQUE INDEX IF NOT EXISTS idx_board_advisory_session_approval_id
ON board_advisory_session(approval_id);

CREATE UNIQUE INDEX IF NOT EXISTS idx_board_advisory_session_review_pack_id
ON board_advisory_session(review_pack_id);

CREATE INDEX IF NOT EXISTS idx_board_advisory_session_workflow_id
ON board_advisory_session(workflow_id);

CREATE INDEX IF NOT EXISTS idx_board_advisory_analysis_run_session_id
ON board_advisory_analysis_run(session_id);

CREATE INDEX IF NOT EXISTS idx_board_advisory_analysis_run_workflow_id
ON board_advisory_analysis_run(workflow_id);

CREATE UNIQUE INDEX IF NOT EXISTS idx_board_advisory_analysis_run_idempotency_key
ON board_advisory_analysis_run(idempotency_key);

CREATE INDEX IF NOT EXISTS idx_artifact_index_ticket_id
ON artifact_index(ticket_id);

CREATE INDEX IF NOT EXISTS idx_artifact_index_workflow_id
ON artifact_index(workflow_id);

CREATE INDEX IF NOT EXISTS idx_artifact_index_node_id
ON artifact_index(node_id);

CREATE INDEX IF NOT EXISTS idx_actor_projection_status
ON actor_projection(status);

CREATE INDEX IF NOT EXISTS idx_actor_projection_employee_id
ON actor_projection(employee_id);

CREATE INDEX IF NOT EXISTS idx_incident_projection_workflow_id
ON incident_projection(workflow_id);

CREATE INDEX IF NOT EXISTS idx_incident_projection_status
ON incident_projection(status);

CREATE INDEX IF NOT EXISTS idx_incident_projection_provider_id
ON incident_projection(provider_id);

CREATE INDEX IF NOT EXISTS idx_incident_projection_fingerprint
ON incident_projection(fingerprint);

CREATE INDEX IF NOT EXISTS idx_execution_attempt_projection_ticket
ON execution_attempt_projection(ticket_id);

CREATE INDEX IF NOT EXISTS idx_execution_attempt_projection_state
ON execution_attempt_projection(state);

CREATE INDEX IF NOT EXISTS idx_meeting_projection_workflow_id
ON meeting_projection(workflow_id);

CREATE INDEX IF NOT EXISTS idx_meeting_projection_status
ON meeting_projection(status);

CREATE INDEX IF NOT EXISTS idx_meeting_projection_normalized_topic
ON meeting_projection(workflow_id, normalized_topic);

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
