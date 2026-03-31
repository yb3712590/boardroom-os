from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from app.contracts.worker_admin import (
    WorkerAdminContainScopeRequest,
    WorkerAdminContainScopeResponse,
    WorkerAdminAuthRejectionsResponse,
    WorkerAdminBindingsResponse,
    WorkerAdminBootstrapIssuesResponse,
    WorkerAdminCleanupBindingsRequest,
    WorkerAdminCleanupBindingsResponse,
    WorkerAdminCreateBindingRequest,
    WorkerAdminCreateBindingResponse,
    WorkerAdminDeliveryGrantsResponse,
    WorkerAdminIssueBootstrapRequest,
    WorkerAdminIssueBootstrapResponse,
    WorkerAdminRevokeBootstrapRequest,
    WorkerAdminRevokeBootstrapResponse,
    WorkerAdminRevokeDeliveryGrantRequest,
    WorkerAdminRevokeDeliveryGrantResponse,
    WorkerAdminRevokeSessionRequest,
    WorkerAdminRevokeSessionResponse,
    WorkerAdminScopeSummaryResponse,
    WorkerAdminSessionsResponse,
)
from app.core.worker_admin import (
    WORKER_ADMIN_API_VIA,
    WorkerAdminConflictError,
    build_scope_summary,
    cleanup_bindings,
    contain_scope,
    create_binding,
    list_auth_rejections,
    list_delivery_grants,
    revoke_delivery_grant,
    revoke_session,
    list_binding_admin_views,
    list_bootstrap_issues,
    list_sessions,
    revoke_bootstrap,
    resolve_scope_args,
    issue_bootstrap,
)
from app.db.repository import ControlPlaneRepository

router = APIRouter(prefix="/api/v1/worker-admin", tags=["worker-admin"])


def _translate_worker_admin_error(exc: Exception) -> HTTPException:
    return HTTPException(status_code=400, detail=str(exc))


def _translate_worker_admin_conflict(exc: WorkerAdminConflictError) -> HTTPException:
    return HTTPException(status_code=409, detail=str(exc))


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


@router.get("/sessions", response_model=WorkerAdminSessionsResponse)
def get_worker_admin_sessions(
    request: Request,
    worker_id: str | None = None,
    tenant_id: str | None = None,
    workspace_id: str | None = None,
    active_only: bool = False,
) -> WorkerAdminSessionsResponse:
    repository: ControlPlaneRepository = request.app.state.repository
    try:
        sessions = list_sessions(
            repository,
            worker_id=worker_id,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            active_only=active_only,
        )
    except (RuntimeError, ValueError) as exc:
        raise _translate_worker_admin_error(exc) from exc
    return WorkerAdminSessionsResponse(sessions=sessions, count=len(sessions))


@router.get("/delivery-grants", response_model=WorkerAdminDeliveryGrantsResponse)
def get_worker_admin_delivery_grants(
    request: Request,
    worker_id: str | None = None,
    session_id: str | None = None,
    ticket_id: str | None = None,
    tenant_id: str | None = None,
    workspace_id: str | None = None,
    active_only: bool = False,
) -> WorkerAdminDeliveryGrantsResponse:
    repository: ControlPlaneRepository = request.app.state.repository
    try:
        delivery_grants = list_delivery_grants(
            repository,
            worker_id=worker_id,
            session_id=session_id,
            ticket_id=ticket_id,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            active_only=active_only,
        )
    except (RuntimeError, ValueError) as exc:
        raise _translate_worker_admin_error(exc) from exc
    return WorkerAdminDeliveryGrantsResponse(
        delivery_grants=delivery_grants,
        count=len(delivery_grants),
    )


@router.get("/auth-rejections", response_model=WorkerAdminAuthRejectionsResponse)
def get_worker_admin_auth_rejections(
    request: Request,
    worker_id: str | None = None,
    tenant_id: str | None = None,
    workspace_id: str | None = None,
    route_family: str | None = None,
) -> WorkerAdminAuthRejectionsResponse:
    repository: ControlPlaneRepository = request.app.state.repository
    try:
        auth_rejections = list_auth_rejections(
            repository,
            worker_id=worker_id,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            route_family=route_family,
        )
    except (RuntimeError, ValueError) as exc:
        raise _translate_worker_admin_error(exc) from exc
    return WorkerAdminAuthRejectionsResponse(
        auth_rejections=auth_rejections,
        count=len(auth_rejections),
    )


@router.get("/scope-summary", response_model=WorkerAdminScopeSummaryResponse)
def get_worker_admin_scope_summary(
    request: Request,
    tenant_id: str,
    workspace_id: str,
    worker_id: str | None = None,
) -> WorkerAdminScopeSummaryResponse:
    repository: ControlPlaneRepository = request.app.state.repository
    try:
        summary = build_scope_summary(
            repository,
            worker_id=worker_id,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
        )
    except (RuntimeError, ValueError) as exc:
        raise _translate_worker_admin_error(exc) from exc
    return WorkerAdminScopeSummaryResponse.model_validate(summary)


@router.post("/contain-scope", response_model=WorkerAdminContainScopeResponse)
def post_worker_admin_contain_scope(
    request: Request,
    payload: WorkerAdminContainScopeRequest,
) -> WorkerAdminContainScopeResponse:
    repository: ControlPlaneRepository = request.app.state.repository
    try:
        result = contain_scope(
            repository,
            tenant_id=payload.tenant_id,
            workspace_id=payload.workspace_id,
            worker_id=payload.worker_id,
            dry_run=payload.dry_run,
            revoke_bootstrap_issues=payload.revoke_bootstrap_issues,
            revoke_sessions=payload.revoke_sessions,
            revoked_by=payload.revoked_by,
            reason=payload.reason,
            expected_active_bootstrap_issue_count=payload.expected_active_bootstrap_issue_count,
            expected_active_session_count=payload.expected_active_session_count,
            expected_active_delivery_grant_count=payload.expected_active_delivery_grant_count,
        )
    except WorkerAdminConflictError as exc:
        raise _translate_worker_admin_conflict(exc) from exc
    except (RuntimeError, ValueError) as exc:
        raise _translate_worker_admin_error(exc) from exc
    return WorkerAdminContainScopeResponse.model_validate(result)


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
            issued_via=WORKER_ADMIN_API_VIA,
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


@router.post("/revoke-session", response_model=WorkerAdminRevokeSessionResponse)
def post_worker_admin_revoke_session(
    request: Request,
    payload: WorkerAdminRevokeSessionRequest,
) -> WorkerAdminRevokeSessionResponse:
    repository: ControlPlaneRepository = request.app.state.repository
    try:
        revoked = revoke_session(
            repository,
            session_id=payload.session_id,
            worker_id=payload.worker_id,
            tenant_id=payload.tenant_id,
            workspace_id=payload.workspace_id,
            revoked_by=payload.revoked_by,
            reason=payload.reason,
            revoked_via=WORKER_ADMIN_API_VIA,
        )
    except (RuntimeError, ValueError) as exc:
        raise _translate_worker_admin_error(exc) from exc
    return WorkerAdminRevokeSessionResponse.model_validate(revoked)


@router.post("/revoke-delivery-grant", response_model=WorkerAdminRevokeDeliveryGrantResponse)
def post_worker_admin_revoke_delivery_grant(
    request: Request,
    payload: WorkerAdminRevokeDeliveryGrantRequest,
) -> WorkerAdminRevokeDeliveryGrantResponse:
    repository: ControlPlaneRepository = request.app.state.repository
    try:
        revoked = revoke_delivery_grant(
            repository,
            grant_id=payload.grant_id,
            revoked_by=payload.revoked_by,
            reason=payload.reason,
            revoked_via=WORKER_ADMIN_API_VIA,
        )
    except (RuntimeError, ValueError) as exc:
        raise _translate_worker_admin_error(exc) from exc
    return WorkerAdminRevokeDeliveryGrantResponse.model_validate(revoked)


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
