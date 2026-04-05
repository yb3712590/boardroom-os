from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app._frozen.worker_admin.api.worker_admin_auth import (
    WorkerAdminOperatorContext,
    get_worker_admin_operator_context,
    require_worker_admin_read_scope,
)
from app.contracts.projections import (
    WorkerAdminAuditProjectionEnvelope,
    WorkerAdminAuthRejectionProjectionEnvelope,
)
from app.core.projections import (
    build_worker_admin_audit_projection,
    build_worker_admin_auth_rejection_projection,
)
from app.db.repository import ControlPlaneRepository

router = APIRouter(prefix="/api/v1/projections", tags=["projections"])


@router.get("/worker-admin-audit", response_model=WorkerAdminAuditProjectionEnvelope)
def get_worker_admin_audit_projection(
    request: Request,
    tenant_id: str | None = None,
    workspace_id: str | None = None,
    worker_id: str | None = None,
    operator_id: str | None = None,
    action_type: str | None = None,
    dry_run: bool | None = None,
    limit: int = Query(default=50, ge=1),
    operator: WorkerAdminOperatorContext = Depends(get_worker_admin_operator_context),
) -> WorkerAdminAuditProjectionEnvelope:
    if (tenant_id is None) != (workspace_id is None):
        raise HTTPException(
            status_code=400,
            detail="tenant_id and workspace_id must be provided together.",
        )
    require_worker_admin_read_scope(
        operator,
        tenant_id=tenant_id,
        workspace_id=workspace_id,
    )
    repository: ControlPlaneRepository = request.app.state.repository
    return build_worker_admin_audit_projection(
        repository,
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        worker_id=worker_id,
        operator_id=operator_id,
        action_type=action_type,
        dry_run=dry_run,
        limit=limit,
    )


@router.get(
    "/worker-admin-auth-rejections",
    response_model=WorkerAdminAuthRejectionProjectionEnvelope,
)
def get_worker_admin_auth_rejection_projection(
    request: Request,
    tenant_id: str | None = None,
    workspace_id: str | None = None,
    operator_id: str | None = None,
    operator_role: str | None = None,
    token_id: str | None = None,
    route_path: str | None = None,
    limit: int = Query(default=50, ge=1),
    operator: WorkerAdminOperatorContext = Depends(get_worker_admin_operator_context),
) -> WorkerAdminAuthRejectionProjectionEnvelope:
    if (tenant_id is None) != (workspace_id is None):
        raise HTTPException(
            status_code=400,
            detail="tenant_id and workspace_id must be provided together.",
        )
    require_worker_admin_read_scope(
        operator,
        tenant_id=tenant_id,
        workspace_id=workspace_id,
    )
    repository: ControlPlaneRepository = request.app.state.repository
    return build_worker_admin_auth_rejection_projection(
        repository,
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        operator_id=operator_id,
        operator_role=operator_role,
        token_id=token_id,
        route_path=route_path,
        limit=limit,
    )
