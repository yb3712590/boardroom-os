from __future__ import annotations

from datetime import datetime

from app.contracts.common import ProjectionEnvelopeBase, StrictModel
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


class WorkforceSummaryProjection(StrictModel):
    active_workers: int
    idle_workers: int
    overloaded_workers: int
    active_checkers: int
    workers_in_rework_loop: int


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
    pipeline_summary: PipelineSummaryProjection
    inbox_counts: InboxCountsProjection
    workforce_summary: WorkforceSummaryProjection
    event_stream_preview: list[EventStreamPreviewItem]


class DashboardProjectionEnvelope(ProjectionEnvelopeBase):
    data: DashboardProjectionData


class RouteTarget(StrictModel):
    view: str
    review_pack_id: str | None = None
    incident_id: str | None = None


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


class ReviewRoomDraftDefaults(StrictModel):
    selected_option_id: str | None = None
    comment_template: str = ""


class ReviewRoomProjectionData(StrictModel):
    review_pack: dict | None = None
    available_actions: list[str]
    draft_defaults: ReviewRoomDraftDefaults


class ReviewRoomProjectionEnvelope(ProjectionEnvelopeBase):
    data: ReviewRoomProjectionData


class ReviewRoomDeveloperInspectorProjectionData(StrictModel):
    review_pack_id: str
    compiled_context_bundle_ref: str | None = None
    compile_manifest_ref: str | None = None
    compiled_context_bundle: dict | None = None
    compile_manifest: dict | None = None
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
    expires_at: datetime | None = None
    deleted_at: datetime | None = None
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


class WorkerAdminAuthRejectionProjectionItem(StrictModel):
    occurred_at: datetime
    route_path: str
    reason_code: str
    operator_id: str | None = None
    operator_role: str | None = None
    token_id: str | None = None
    tenant_id: str | None = None
    workspace_id: str | None = None


class WorkerAdminAuthRejectionProjectionData(StrictModel):
    summary: WorkerAdminAuthRejectionProjectionSummary
    filters: WorkerAdminAuthRejectionProjectionFilters
    rejections: list[WorkerAdminAuthRejectionProjectionItem]


class WorkerAdminAuthRejectionProjectionEnvelope(ProjectionEnvelopeBase):
    data: WorkerAdminAuthRejectionProjectionData
