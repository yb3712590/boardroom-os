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
