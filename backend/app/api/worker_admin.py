from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from app.contracts.worker_admin import (
    WorkerAdminBindingsResponse,
    WorkerAdminBootstrapIssuesResponse,
    WorkerAdminCleanupBindingsRequest,
    WorkerAdminCleanupBindingsResponse,
    WorkerAdminCreateBindingRequest,
    WorkerAdminCreateBindingResponse,
    WorkerAdminIssueBootstrapRequest,
    WorkerAdminIssueBootstrapResponse,
    WorkerAdminRevokeBootstrapRequest,
    WorkerAdminRevokeBootstrapResponse,
)
from app.core.worker_admin import (
    cleanup_bindings,
    create_binding,
    list_binding_admin_views,
    list_bootstrap_issues,
    revoke_bootstrap,
    resolve_scope_args,
    issue_bootstrap,
)
from app.db.repository import ControlPlaneRepository

router = APIRouter(prefix="/api/v1/worker-admin", tags=["worker-admin"])


def _translate_worker_admin_error(exc: Exception) -> HTTPException:
    return HTTPException(status_code=400, detail=str(exc))


@router.get("/bindings", response_model=WorkerAdminBindingsResponse)
def get_worker_admin_bindings(
    request: Request,
    worker_id: str | None = None,
    tenant_id: str | None = None,
    workspace_id: str | None = None,
) -> WorkerAdminBindingsResponse:
    repository: ControlPlaneRepository = request.app.state.repository
    try:
        resolve_scope_args(tenant_id, workspace_id)
        bindings = list_binding_admin_views(
            repository,
            worker_id=worker_id,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
        )
    except (RuntimeError, ValueError) as exc:
        raise _translate_worker_admin_error(exc) from exc
    return WorkerAdminBindingsResponse(bindings=bindings, count=len(bindings))


@router.get("/bootstrap-issues", response_model=WorkerAdminBootstrapIssuesResponse)
def get_worker_admin_bootstrap_issues(
    request: Request,
    worker_id: str | None = None,
    tenant_id: str | None = None,
    workspace_id: str | None = None,
    active_only: bool = False,
) -> WorkerAdminBootstrapIssuesResponse:
    repository: ControlPlaneRepository = request.app.state.repository
    try:
        resolve_scope_args(tenant_id, workspace_id)
        bootstrap_issues = list_bootstrap_issues(
            repository,
            worker_id=worker_id,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            active_only=active_only,
        )
    except (RuntimeError, ValueError) as exc:
        raise _translate_worker_admin_error(exc) from exc
    return WorkerAdminBootstrapIssuesResponse(
        bootstrap_issues=bootstrap_issues,
        count=len(bootstrap_issues),
    )


@router.post("/create-binding", response_model=WorkerAdminCreateBindingResponse)
def post_worker_admin_create_binding(
    request: Request,
    payload: WorkerAdminCreateBindingRequest,
) -> WorkerAdminCreateBindingResponse:
    repository: ControlPlaneRepository = request.app.state.repository
    try:
        binding = create_binding(
            repository,
            worker_id=payload.worker_id,
            tenant_id=payload.tenant_id,
            workspace_id=payload.workspace_id,
        )
    except (RuntimeError, ValueError) as exc:
        raise _translate_worker_admin_error(exc) from exc
    return WorkerAdminCreateBindingResponse.model_validate(binding)


@router.post("/issue-bootstrap", response_model=WorkerAdminIssueBootstrapResponse)
def post_worker_admin_issue_bootstrap(
    request: Request,
    payload: WorkerAdminIssueBootstrapRequest,
) -> WorkerAdminIssueBootstrapResponse:
    repository: ControlPlaneRepository = request.app.state.repository
    try:
        issued = issue_bootstrap(
            repository,
            worker_id=payload.worker_id,
            ttl_sec=payload.ttl_sec,
            tenant_id=payload.tenant_id,
            workspace_id=payload.workspace_id,
            issued_by=payload.issued_by,
            reason=payload.reason,
            issued_via="worker_admin_api",
        )
    except (RuntimeError, ValueError) as exc:
        raise _translate_worker_admin_error(exc) from exc
    return WorkerAdminIssueBootstrapResponse.model_validate(issued)


@router.post("/revoke-bootstrap", response_model=WorkerAdminRevokeBootstrapResponse)
def post_worker_admin_revoke_bootstrap(
    request: Request,
    payload: WorkerAdminRevokeBootstrapRequest,
) -> WorkerAdminRevokeBootstrapResponse:
    repository: ControlPlaneRepository = request.app.state.repository
    try:
        revoked = revoke_bootstrap(
            repository,
            worker_id=payload.worker_id,
            tenant_id=payload.tenant_id,
            workspace_id=payload.workspace_id,
        )
    except (RuntimeError, ValueError) as exc:
        raise _translate_worker_admin_error(exc) from exc
    return WorkerAdminRevokeBootstrapResponse.model_validate(revoked)


@router.post("/cleanup-bindings", response_model=WorkerAdminCleanupBindingsResponse)
def post_worker_admin_cleanup_bindings(
    request: Request,
    payload: WorkerAdminCleanupBindingsRequest,
) -> WorkerAdminCleanupBindingsResponse:
    repository: ControlPlaneRepository = request.app.state.repository
    try:
        cleaned = cleanup_bindings(
            repository,
            worker_id=payload.worker_id,
            tenant_id=payload.tenant_id,
            workspace_id=payload.workspace_id,
            dry_run=payload.dry_run,
        )
    except (RuntimeError, ValueError) as exc:
        raise _translate_worker_admin_error(exc) from exc
    return WorkerAdminCleanupBindingsResponse.model_validate(cleaned)
