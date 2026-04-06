from __future__ import annotations

from datetime import datetime

from pydantic import Field

from app.contracts.common import ProjectionEnvelopeBase, StrictModel
from app.contracts.commands import ElicitationAnswer
from app.contracts.runtime import RenderedExecutionPayloadSummary
from app.contracts.events import EventSeverity


class WorkspaceSummary(StrictModel):
    workspace_id: str
    workspace_name: str


class ActiveWorkflowProjection(StrictModel):
    workflow_id: str
    title: str
    north_star_goal: str
    status: str
    current_stage: str
    started_at: datetime
    deadline_at: datetime | None = None


class OpsStripProjection(StrictModel):
    budget_total: int
    budget_used: int
    budget_remaining: int
    token_burn_rate_5m: int
    active_tickets: int
    blocked_nodes: int
    open_incidents: int
    open_circuit_breakers: int
    provider_health_summary: str


class DashboardRuntimeStatusProjection(StrictModel):
    effective_mode: str
    provider_label: str
    model: str | None = None
    configured_worker_count: int
    provider_health_summary: str
    reason: str


class DashboardCompletionSummaryProjection(StrictModel):
    workflow_id: str
    final_review_pack_id: str
    approved_at: datetime
    final_review_approved_at: datetime
    closeout_completed_at: datetime
    closeout_ticket_id: str
    title: str
    summary: str
    selected_option_id: str | None = None
    board_comment: str | None = None
    artifact_refs: list[str]
    closeout_artifact_refs: list[str]
    documentation_sync_summary: str | None = None
    documentation_update_count: int = 0
    documentation_follow_up_count: int = 0


class NodeCountsProjection(StrictModel):
    pending: int
    executing: int
    under_review: int
    blocked_for_board: int
    fused: int
    completed: int


class PhaseSummaryProjection(StrictModel):
    phase_id: str
    label: str
    status: str
    node_counts: NodeCountsProjection


class PipelineSummaryProjection(StrictModel):
    phases: list[PhaseSummaryProjection]
    critical_path_node_ids: list[str]
    blocked_node_ids: list[str]


class InboxCountsProjection(StrictModel):
    approvals_pending: int
    incidents_pending: int
    budget_alerts: int
    provider_alerts: int


class ArtifactMaintenanceProjection(StrictModel):
    auto_cleanup_enabled: bool
    cleanup_interval_sec: int
    ephemeral_default_ttl_sec: int
    retention_defaults: dict[str, int | None]
    pending_expired_count: int
    pending_storage_cleanup_count: int
    delete_failed_count: int
    legacy_unknown_retention_count: int
    last_run_at: datetime | None = None
    last_cleaned_by: str | None = None
    last_trigger: str | None = None
    last_expired_count: int = 0
    last_storage_deleted_count: int = 0


class WorkforceSummaryProjection(StrictModel):
    active_workers: int
    idle_workers: int
    overloaded_workers: int
    active_checkers: int
    workers_in_rework_loop: int
    workers_in_staffing_containment: int = 0


class WorkforceActionProjection(StrictModel):
    action_type: str
    enabled: bool
    disabled_reason: str | None = None
    template_id: str | None = None


class StaffingHireTemplateProjection(StrictModel):
    template_id: str
    label: str
    role_type: str
    role_profile_refs: list[str]
    employee_id_hint: str
    provider_id: str | None = None
    request_summary: str
    skill_profile: dict[str, str] = Field(default_factory=dict)
    personality_profile: dict[str, str] = Field(default_factory=dict)
    aesthetic_profile: dict[str, str] = Field(default_factory=dict)


class WorkforceWorkerProjection(StrictModel):
    employee_id: str
    role_type: str
    employment_state: str
    activity_state: str
    current_ticket_id: str | None = None
    current_node_id: str | None = None
    provider_id: str | None = None
    skill_profile: dict[str, str] = Field(default_factory=dict)
    personality_profile: dict[str, str] = Field(default_factory=dict)
    aesthetic_profile: dict[str, str] = Field(default_factory=dict)
    profile_summary: str = Field(min_length=1)
    last_update_at: datetime | None = None
    available_actions: list[WorkforceActionProjection] = Field(default_factory=list)


class WorkforceRoleLaneProjection(StrictModel):
    role_type: str
    active_count: int
    idle_count: int
    workers: list[WorkforceWorkerProjection]


class WorkforceProjectionData(StrictModel):
    summary: WorkforceSummaryProjection
    hire_templates: list[StaffingHireTemplateProjection] = Field(default_factory=list)
    role_lanes: list[WorkforceRoleLaneProjection]


class WorkforceProjectionEnvelope(ProjectionEnvelopeBase):
    data: WorkforceProjectionData


class CEOShadowValidatedActionProjection(StrictModel):
    action_type: str
    payload: dict[str, object]
    reason: str


class CEOShadowExecutedActionProjection(StrictModel):
    action_type: str
    payload: dict[str, object]
    execution_status: str
    reason: str
    command_status: str | None = None
    causation_hint: str | None = None


class CEOShadowRunProjection(StrictModel):
    run_id: str
    occurred_at: datetime
    trigger_type: str
    trigger_ref: str | None = None
    effective_mode: str
    provider_health_summary: str
    model: str | None = None
    prompt_version: str
    provider_response_id: str | None = None
    fallback_reason: str | None = None
    proposed_action_batch: dict[str, object]
    accepted_actions: list[CEOShadowValidatedActionProjection]
    rejected_actions: list[CEOShadowValidatedActionProjection]
    executed_actions: list[CEOShadowExecutedActionProjection]
    execution_summary: dict[str, object]
    deterministic_fallback_used: bool = False
    deterministic_fallback_reason: str | None = None
    comparison: dict[str, object]


class CEOShadowProjectionData(StrictModel):
    workflow_id: str
    runs: list[CEOShadowRunProjection]


class CEOShadowProjectionEnvelope(ProjectionEnvelopeBase):
    data: CEOShadowProjectionData


class EventStreamPreviewItem(StrictModel):
    event_id: str
    occurred_at: datetime
    category: str
    severity: EventSeverity
    message: str
    related_ref: str | None = None


class DashboardProjectionData(StrictModel):
    workspace: WorkspaceSummary
    active_workflow: ActiveWorkflowProjection | None = None
    ops_strip: OpsStripProjection
    runtime_status: DashboardRuntimeStatusProjection
    pipeline_summary: PipelineSummaryProjection
    inbox_counts: InboxCountsProjection
    workforce_summary: WorkforceSummaryProjection
    artifact_maintenance: ArtifactMaintenanceProjection
    completion_summary: DashboardCompletionSummaryProjection | None = None
    event_stream_preview: list[EventStreamPreviewItem]


class DashboardProjectionEnvelope(ProjectionEnvelopeBase):
    data: DashboardProjectionData


class RouteTarget(StrictModel):
    view: str
    review_pack_id: str | None = None
    incident_id: str | None = None
    meeting_id: str | None = None


class InboxItemProjection(StrictModel):
    inbox_item_id: str
    workflow_id: str
    item_type: str
    priority: str
    status: str
    created_at: datetime
    sla_due_at: datetime | None = None
    title: str
    summary: str
    source_ref: str
    route_target: RouteTarget
    badges: list[str]


class InboxProjectionData(StrictModel):
    items: list[InboxItemProjection]


class InboxProjectionEnvelope(ProjectionEnvelopeBase):
    data: InboxProjectionData


class MeetingParticipantProjection(StrictModel):
    employee_id: str
    role_type: str
    meeting_responsibility: str
    is_recorder: bool = False


class MeetingRoundProjection(StrictModel):
    round_type: str
    round_index: int
    summary: str
    notes: list[str] = Field(default_factory=list)
    completed_at: datetime


class MeetingDecisionRecordProjection(StrictModel):
    format: str
    context: str
    decision: str
    rationale: list[str] = Field(default_factory=list)
    consequences: list[str] = Field(default_factory=list)
    archived_context_refs: list[str] = Field(default_factory=list)


class MeetingDetailProjectionData(StrictModel):
    meeting_id: str
    workflow_id: str
    meeting_type: str
    topic: str
    status: str
    review_status: str | None = None
    source_ticket_id: str
    source_node_id: str
    review_pack_id: str | None = None
    opened_at: datetime
    updated_at: datetime
    closed_at: datetime | None = None
    current_round: str | None = None
    recorder_employee_id: str
    participants: list[MeetingParticipantProjection]
    rounds: list[MeetingRoundProjection]
    consensus_summary: str | None = None
    no_consensus_reason: str | None = None
    decision_record: MeetingDecisionRecordProjection | None = None


class MeetingDetailProjectionEnvelope(ProjectionEnvelopeBase):
    data: MeetingDetailProjectionData


class DependencyInspectorWorkflowProjection(StrictModel):
    workflow_id: str
    title: str
    current_stage: str
    status: str


class DependencyInspectorCurrentStopProjection(StrictModel):
    reason: str
    node_id: str | None = None
    ticket_id: str | None = None
    review_pack_id: str | None = None
    incident_id: str | None = None


class DependencyInspectorSummaryProjection(StrictModel):
    total_nodes: int
    critical_path_nodes: int
    blocked_nodes: int
    open_approvals: int
    open_incidents: int
    current_stop: DependencyInspectorCurrentStopProjection | None = None


class DependencyInspectorNodeProjection(StrictModel):
    node_id: str
    ticket_id: str | None = None
    parent_ticket_id: str | None = None
    phase: str
    delivery_stage: str | None = None
    node_status: str
    ticket_status: str | None = None
    role_profile_ref: str | None = None
    output_schema_ref: str | None = None
    lease_owner: str | None = None
    depends_on_ticket_id: str | None = None
    dependent_ticket_ids: list[str]
    block_reason: str
    is_critical_path: bool
    is_blocked: bool
    expected_artifact_scope: list[str]
    open_review_pack_id: str | None = None
    open_incident_id: str | None = None


class DependencyInspectorProjectionData(StrictModel):
    workflow: DependencyInspectorWorkflowProjection
    summary: DependencyInspectorSummaryProjection
    nodes: list[DependencyInspectorNodeProjection]


class DependencyInspectorProjectionEnvelope(ProjectionEnvelopeBase):
    data: DependencyInspectorProjectionData


class RuntimeProviderProjectionData(StrictModel):
    mode: str
    effective_mode: str
    provider_health_summary: str
    provider_id: str
    base_url: str | None = None
    model: str | None = None
    timeout_sec: float
    reasoning_effort: str | None = None
    api_key_configured: bool
    api_key_masked: str | None = None
    configured_worker_count: int
    effective_reason: str


class RuntimeProviderProjectionEnvelope(ProjectionEnvelopeBase):
    data: RuntimeProviderProjectionData


class ReviewRoomDraftDefaults(StrictModel):
    selected_option_id: str | None = None
    comment_template: str = ""
    elicitation_answers: list[ElicitationAnswer] = Field(default_factory=list)


class ReviewRoomProjectionData(StrictModel):
    review_pack: dict | None = None
    available_actions: list[str]
    draft_defaults: ReviewRoomDraftDefaults


class ReviewRoomProjectionEnvelope(ProjectionEnvelopeBase):
    data: ReviewRoomProjectionData


class ReviewRoomDeveloperInspectorCompileSummary(StrictModel):
    source_count: int
    inline_full_count: int
    inline_fragment_count: int
    inline_partial_count: int
    reference_only_count: int
    degraded_source_count: int
    missing_critical_source_count: int
    reason_counts: dict[str, int]
    retrieved_source_count: int = 0
    retrieval_channel_counts: dict[str, int] = Field(default_factory=dict)
    dropped_retrieval_count: int = 0
    total_budget_tokens: int = 0
    used_budget_tokens: int = 0
    remaining_budget_tokens: int = 0
    truncated_tokens: int = 0
    dropped_explicit_source_count: int = 0
    media_reference_count: int = 0
    download_attachment_count: int = 0
    fragment_strategy_counts: dict[str, int] = Field(default_factory=dict)
    preview_strategy_counts: dict[str, int] = Field(default_factory=dict)
    preview_kind_counts: dict[str, int] = Field(default_factory=dict)


class ReviewRoomDeveloperInspectorProjectionData(StrictModel):
    review_pack_id: str
    compiled_context_bundle_ref: str | None = None
    compile_manifest_ref: str | None = None
    rendered_execution_payload_ref: str | None = None
    compiled_context_bundle: dict | None = None
    compile_manifest: dict | None = None
    rendered_execution_payload: dict | None = None
    compile_summary: ReviewRoomDeveloperInspectorCompileSummary | None = None
    render_summary: RenderedExecutionPayloadSummary | None = None
    availability: str


class ReviewRoomDeveloperInspectorProjectionEnvelope(ProjectionEnvelopeBase):
    data: ReviewRoomDeveloperInspectorProjectionData


class TicketArtifactProjection(StrictModel):
    artifact_ref: str
    path: str
    kind: str
    media_type: str | None = None
    status: str
    materialization_status: str
    lifecycle_status: str
    retention_class: str | None = None
    retention_class_source: str | None = None
    retention_ttl_sec: int | None = None
    retention_policy_source: str | None = None
    expires_at: datetime | None = None
    deleted_at: datetime | None = None
    deleted_by: str | None = None
    delete_reason: str | None = None
    storage_backend: str
    storage_delete_status: str
    storage_deleted_at: datetime | None = None
    size_bytes: int | None = None
    content_hash: str | None = None
    content_url: str | None = None
    download_url: str | None = None
    preview_url: str | None = None
    created_at: datetime


class TicketArtifactsProjectionData(StrictModel):
    ticket_id: str
    artifacts: list[TicketArtifactProjection]


class TicketArtifactsProjectionEnvelope(ProjectionEnvelopeBase):
    data: TicketArtifactsProjectionData


class ArtifactCleanupCandidateProjection(StrictModel):
    artifact_ref: str
    ticket_id: str
    path: str
    lifecycle_status: str
    retention_class: str | None = None
    retention_class_source: str | None = None
    retention_ttl_sec: int | None = None
    retention_policy_source: str | None = None
    expires_at: datetime | None = None
    storage_backend: str
    storage_delete_status: str
    storage_deleted_at: datetime | None = None
    cleanup_reason: str


class ArtifactCleanupCandidatesProjectionFilters(StrictModel):
    ticket_id: str | None = None
    retention_class: str | None = None
    limit: int


class ArtifactCleanupCandidatesProjectionData(StrictModel):
    filters: ArtifactCleanupCandidatesProjectionFilters
    artifacts: list[ArtifactCleanupCandidateProjection]


class ArtifactCleanupCandidatesProjectionEnvelope(ProjectionEnvelopeBase):
    data: ArtifactCleanupCandidatesProjectionData


class IncidentProjectionItem(StrictModel):
    incident_id: str
    workflow_id: str
    node_id: str | None = None
    ticket_id: str | None = None
    provider_id: str | None = None
    incident_type: str
    status: str
    severity: str | None = None
    fingerprint: str
    circuit_breaker_state: str | None = None
    opened_at: datetime
    closed_at: datetime | None = None
    payload: dict


class IncidentDetailProjectionData(StrictModel):
    incident: IncidentProjectionItem
    available_followup_actions: list[str]
    recommended_followup_action: str | None = None


class IncidentDetailProjectionEnvelope(ProjectionEnvelopeBase):
    data: IncidentDetailProjectionData


class WorkerRuntimeProjectionSummary(StrictModel):
    binding_count: int
    cleanup_eligible_binding_count: int
    active_session_count: int
    active_delivery_grant_count: int
    recent_rejection_count: int


class WorkerRuntimeProjectionFilters(StrictModel):
    worker_id: str | None = None
    tenant_id: str | None = None
    workspace_id: str | None = None
    active_only: bool = False
    rejection_limit: int
    grant_limit: int


class WorkerBindingAdminProjection(StrictModel):
    worker_id: str
    credential_version: int
    tenant_id: str
    workspace_id: str
    revoked_before: datetime | None = None
    rotated_at: datetime | None = None
    updated_at: datetime
    active_session_count: int
    active_delivery_grant_count: int
    active_ticket_count: int
    latest_bootstrap_issue_at: datetime | None = None
    latest_bootstrap_issue_source: str | None = None
    cleanup_eligible: bool


class WorkerSessionAdminProjection(StrictModel):
    session_id: str
    worker_id: str
    tenant_id: str
    workspace_id: str
    issued_at: datetime
    expires_at: datetime
    last_seen_at: datetime
    revoked_at: datetime | None = None
    credential_version: int
    revoke_reason: str | None = None
    revoked_via: str | None = None
    revoked_by: str | None = None
    is_active: bool


class WorkerDeliveryGrantAdminProjection(StrictModel):
    grant_id: str
    scope: str
    worker_id: str
    session_id: str
    credential_version: int
    tenant_id: str
    workspace_id: str
    ticket_id: str
    artifact_ref: str | None = None
    artifact_action: str | None = None
    command_name: str | None = None
    issued_at: datetime
    expires_at: datetime
    revoked_at: datetime | None = None
    revoke_reason: str | None = None
    revoked_via: str | None = None
    revoked_by: str | None = None
    is_active: bool


class WorkerAuthRejectionAdminProjection(StrictModel):
    occurred_at: datetime
    route_family: str
    reason_code: str
    worker_id: str | None = None
    session_id: str | None = None
    grant_id: str | None = None
    ticket_id: str | None = None
    tenant_id: str | None = None
    workspace_id: str | None = None


class WorkerRuntimeProjectionData(StrictModel):
    summary: WorkerRuntimeProjectionSummary
    filters: WorkerRuntimeProjectionFilters
    bindings: list[WorkerBindingAdminProjection]
    sessions: list[WorkerSessionAdminProjection]
    delivery_grants: list[WorkerDeliveryGrantAdminProjection]
    auth_rejections: list[WorkerAuthRejectionAdminProjection]


class WorkerRuntimeProjectionEnvelope(ProjectionEnvelopeBase):
    data: WorkerRuntimeProjectionData


class WorkerAdminAuditProjectionFilters(StrictModel):
    tenant_id: str | None = None
    workspace_id: str | None = None
    worker_id: str | None = None
    operator_id: str | None = None
    action_type: str | None = None
    dry_run: bool | None = None
    limit: int


class WorkerAdminAuditProjectionSummary(StrictModel):
    count: int


class WorkerAdminAuditProjectionItem(StrictModel):
    action_id: str
    occurred_at: datetime
    operator_id: str
    operator_role: str
    auth_source: str
    trusted_proxy_id: str | None = None
    source_ip: str | None = None
    tenant_id: str | None = None
    workspace_id: str | None = None
    worker_id: str | None = None
    session_id: str | None = None
    grant_id: str | None = None
    issue_id: str | None = None
    action_type: str
    dry_run: bool
    details: dict[str, object]


class WorkerAdminAuditProjectionData(StrictModel):
    summary: WorkerAdminAuditProjectionSummary
    filters: WorkerAdminAuditProjectionFilters
    actions: list[WorkerAdminAuditProjectionItem]


class WorkerAdminAuditProjectionEnvelope(ProjectionEnvelopeBase):
    data: WorkerAdminAuditProjectionData


class WorkerAdminAuthRejectionProjectionFilters(StrictModel):
    tenant_id: str | None = None
    workspace_id: str | None = None
    operator_id: str | None = None
    operator_role: str | None = None
    token_id: str | None = None
    route_path: str | None = None
    limit: int


class WorkerAdminAuthRejectionProjectionSummary(StrictModel):
    count: int
    trusted_proxy_enforced: bool
    trusted_proxy_ids: list[str]


class WorkerAdminAuthRejectionProjectionItem(StrictModel):
    occurred_at: datetime
    route_path: str
    reason_code: str
    operator_id: str | None = None
    operator_role: str | None = None
    token_id: str | None = None
    trusted_proxy_id: str | None = None
    source_ip: str | None = None
    tenant_id: str | None = None
    workspace_id: str | None = None


class WorkerAdminAuthRejectionProjectionData(StrictModel):
    summary: WorkerAdminAuthRejectionProjectionSummary
    filters: WorkerAdminAuthRejectionProjectionFilters
    rejections: list[WorkerAdminAuthRejectionProjectionItem]


class WorkerAdminAuthRejectionProjectionEnvelope(ProjectionEnvelopeBase):
    data: WorkerAdminAuthRejectionProjectionData
