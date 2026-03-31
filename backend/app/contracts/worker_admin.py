from __future__ import annotations

from datetime import datetime

from pydantic import Field

from app.contracts.common import StrictModel


class WorkerAdminBindingItem(StrictModel):
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
    bootstrap_issue_count: int
    latest_bootstrap_issue_at: datetime | None = None
    latest_bootstrap_issue_source: str | None = None
    cleanup_eligible: bool


class WorkerAdminOperatorTokenItem(StrictModel):
    token_id: str
    operator_id: str
    role: str
    tenant_id: str | None = None
    workspace_id: str | None = None
    issued_at: datetime
    expires_at: datetime
    issued_via: str
    issued_by: str | None = None
    revoked_at: datetime | None = None
    revoked_by: str | None = None
    revoke_reason: str | None = None
    is_active: bool


class WorkerAdminOperatorTokensResponse(StrictModel):
    tokens: list[WorkerAdminOperatorTokenItem]
    count: int


class WorkerAdminBindingsResponse(StrictModel):
    bindings: list[WorkerAdminBindingItem]
    count: int


class WorkerAdminBootstrapIssueItem(StrictModel):
    issue_id: str
    worker_id: str
    tenant_id: str
    workspace_id: str
    credential_version: int
    issued_at: datetime
    expires_at: datetime
    issued_via: str
    issued_by: str | None = None
    reason: str | None = None
    revoked_at: datetime | None = None


class WorkerAdminBootstrapIssuesResponse(StrictModel):
    bootstrap_issues: list[WorkerAdminBootstrapIssueItem]
    count: int


class WorkerAdminSessionItem(StrictModel):
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


class WorkerAdminSessionsResponse(StrictModel):
    sessions: list[WorkerAdminSessionItem]
    count: int


class WorkerAdminDeliveryGrantItem(StrictModel):
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


class WorkerAdminDeliveryGrantsResponse(StrictModel):
    delivery_grants: list[WorkerAdminDeliveryGrantItem]
    count: int


class WorkerAdminAuthRejectionItem(StrictModel):
    occurred_at: datetime
    route_family: str
    reason_code: str
    worker_id: str | None = None
    session_id: str | None = None
    grant_id: str | None = None
    ticket_id: str | None = None
    tenant_id: str | None = None
    workspace_id: str | None = None


class WorkerAdminAuthRejectionsResponse(StrictModel):
    auth_rejections: list[WorkerAdminAuthRejectionItem]
    count: int


class WorkerAdminScopeSummaryFilters(StrictModel):
    tenant_id: str
    workspace_id: str
    worker_id: str | None = None


class WorkerAdminScopeSummary(StrictModel):
    binding_count: int
    cleanup_eligible_binding_count: int
    active_bootstrap_issue_count: int
    active_session_count: int
    active_delivery_grant_count: int
    recent_rejection_count: int
    active_ticket_count: int


class WorkerAdminScopeWorkerSummaryItem(StrictModel):
    worker_id: str
    binding_count: int
    cleanup_eligible_binding_count: int
    active_bootstrap_issue_count: int
    active_session_count: int
    active_delivery_grant_count: int
    active_ticket_count: int
    recent_rejection_count: int
    latest_bootstrap_issue_at: datetime | None = None
    latest_rejection_at: datetime | None = None


class WorkerAdminScopeSummaryResponse(StrictModel):
    filters: WorkerAdminScopeSummaryFilters
    summary: WorkerAdminScopeSummary
    workers: list[WorkerAdminScopeWorkerSummaryItem]


class WorkerAdminContainScopeFilters(StrictModel):
    tenant_id: str
    workspace_id: str
    worker_id: str | None = None


class WorkerAdminContainScopeRequestedActions(StrictModel):
    revoke_bootstrap_issues: bool
    revoke_sessions: bool


class WorkerAdminContainScopeImpactSummary(StrictModel):
    active_bootstrap_issue_count: int
    active_session_count: int
    active_delivery_grant_count: int


class WorkerAdminContainScopeTargetIds(StrictModel):
    worker_ids: list[str]
    bootstrap_issue_ids: list[str]
    session_ids: list[str]
    delivery_grant_ids: list[str]


class WorkerAdminContainScopeResult(StrictModel):
    revoked_bootstrap_issue_count: int
    revoked_session_count: int
    revoked_delivery_grant_count: int
    revoked_at: datetime
    revoked_by: str
    revoke_reason: str


class WorkerAdminContainScopeRequest(StrictModel):
    tenant_id: str = Field(min_length=1)
    workspace_id: str = Field(min_length=1)
    worker_id: str | None = None
    dry_run: bool = False
    revoke_bootstrap_issues: bool = True
    revoke_sessions: bool = True
    revoked_by: str | None = None
    reason: str | None = None
    expected_active_bootstrap_issue_count: int | None = Field(default=None, ge=0)
    expected_active_session_count: int | None = Field(default=None, ge=0)
    expected_active_delivery_grant_count: int | None = Field(default=None, ge=0)


class WorkerAdminContainScopeResponse(StrictModel):
    filters: WorkerAdminContainScopeFilters
    requested_actions: WorkerAdminContainScopeRequestedActions
    impact_summary: WorkerAdminContainScopeImpactSummary
    target_ids: WorkerAdminContainScopeTargetIds
    dry_run: bool
    executed: bool
    result: WorkerAdminContainScopeResult | None = None


class WorkerAdminCreateBindingRequest(StrictModel):
    worker_id: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    workspace_id: str = Field(min_length=1)


class WorkerAdminCreateBindingResponse(StrictModel):
    worker_id: str
    credential_version: int
    tenant_id: str
    workspace_id: str
    revoked_before: datetime | None = None
    rotated_at: datetime | None = None
    updated_at: datetime


class WorkerAdminIssueBootstrapRequest(StrictModel):
    worker_id: str = Field(min_length=1)
    ttl_sec: int | None = Field(default=None, gt=0)
    tenant_id: str | None = None
    workspace_id: str | None = None
    issued_by: str | None = None
    reason: str | None = None


class WorkerAdminIssueBootstrapResponse(StrictModel):
    issue_id: str
    worker_id: str
    credential_version: int
    tenant_id: str
    workspace_id: str
    issued_via: str
    issued_by: str | None = None
    reason: str | None = None
    bootstrap_token: str
    issued_at: datetime
    expires_at: datetime


class WorkerAdminRevokeBootstrapRequest(StrictModel):
    worker_id: str = Field(min_length=1)
    tenant_id: str | None = None
    workspace_id: str | None = None


class WorkerAdminRevokeBootstrapResponse(StrictModel):
    worker_id: str
    credential_version: int
    tenant_id: str
    workspace_id: str
    revoked_before: datetime


class WorkerAdminRevokeSessionRequest(StrictModel):
    session_id: str | None = None
    worker_id: str | None = None
    tenant_id: str | None = None
    workspace_id: str | None = None
    revoked_by: str | None = None
    reason: str | None = None


class WorkerAdminRevokeSessionResponse(StrictModel):
    session_id: str | None = None
    worker_id: str
    tenant_id: str
    workspace_id: str
    revoked_count: int
    revoked_delivery_grant_count: int
    revoked_at: datetime
    revoked_via: str
    revoked_by: str | None = None
    revoke_reason: str


class WorkerAdminRevokeDeliveryGrantRequest(StrictModel):
    grant_id: str = Field(min_length=1)
    revoked_by: str | None = None
    reason: str | None = None


class WorkerAdminRevokeDeliveryGrantResponse(StrictModel):
    grant_id: str
    session_id: str
    worker_id: str
    tenant_id: str
    workspace_id: str
    revoked_count: int
    revoked_at: datetime
    revoked_via: str
    revoked_by: str | None = None
    revoke_reason: str


class WorkerAdminCleanupBindingsRequest(StrictModel):
    worker_id: str = Field(min_length=1)
    tenant_id: str | None = None
    workspace_id: str | None = None
    dry_run: bool = False


class WorkerAdminCleanupBindingsResponse(StrictModel):
    bindings: list[WorkerAdminBindingItem]
    count: int
    deleted_count: int
    dry_run: bool
    cleaned_at: datetime


class WorkerAdminRevokeOperatorTokenRequest(StrictModel):
    token_id: str = Field(min_length=1)
    revoked_by: str | None = None
    reason: str | None = None


class WorkerAdminRevokeOperatorTokenResponse(StrictModel):
    token_id: str
    operator_id: str
    role: str
    tenant_id: str | None = None
    workspace_id: str | None = None
    issued_at: datetime
    expires_at: datetime
    issued_via: str
    issued_by: str | None = None
    revoked_at: datetime | None = None
    revoked_by: str | None = None
    revoke_reason: str | None = None
