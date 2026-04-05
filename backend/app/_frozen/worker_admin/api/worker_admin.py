from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request

from app._frozen.worker_admin.api.worker_admin_auth import (
    WorkerAdminOperatorContext,
    get_worker_admin_operator_context,
    require_worker_admin_read_scope,
    require_worker_admin_write_scope,
    require_worker_admin_write_target_scope,
    resolve_worker_admin_actor,
)

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
    WorkerAdminOperatorTokensResponse,
    WorkerAdminRevokeBootstrapRequest,
    WorkerAdminRevokeBootstrapResponse,
    WorkerAdminRevokeDeliveryGrantRequest,
    WorkerAdminRevokeDeliveryGrantResponse,
    WorkerAdminRevokeOperatorTokenRequest,
    WorkerAdminRevokeOperatorTokenResponse,
    WorkerAdminRevokeSessionRequest,
    WorkerAdminRevokeSessionResponse,
    WorkerAdminScopeSummaryResponse,
    WorkerAdminSessionsResponse,
)
from app._frozen.worker_admin.core.worker_admin import (
    DEFAULT_OPERATOR_TOKEN_REVOKE_REASON,
    WorkerAdminConflictError,
    build_scope_summary,
    contain_scope,
    list_operator_tokens,
    revoke_operator_token,
)
from app.core.worker_scope_ops import (
    WORKER_ADMIN_API_VIA,
    cleanup_bindings,
    create_binding,
    issue_bootstrap,
    list_auth_rejections,
    list_binding_admin_views,
    list_bootstrap_issues,
    list_delivery_grants,
    list_sessions,
    resolve_scope_args,
    revoke_bootstrap,
    revoke_delivery_grant,
    revoke_session,
)
from app.db.repository import ControlPlaneRepository
from app.core.time import now_local

router = APIRouter(prefix="/api/v1/worker-admin", tags=["worker-admin"])


def _translate_worker_admin_error(exc: Exception) -> HTTPException:
    return HTTPException(status_code=400, detail=str(exc))


def _translate_worker_admin_conflict(exc: WorkerAdminConflictError) -> HTTPException:
    return HTTPException(status_code=409, detail=str(exc))


def _serialize_worker_admin_audit_details(value):
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {
            str(key): _serialize_worker_admin_audit_details(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_serialize_worker_admin_audit_details(item) for item in value]
    return value


def _append_worker_admin_action_log(
    repository: ControlPlaneRepository,
    *,
    operator: WorkerAdminOperatorContext,
    action_type: str,
    dry_run: bool,
    tenant_id: str | None,
    workspace_id: str | None,
    worker_id: str | None = None,
    session_id: str | None = None,
    grant_id: str | None = None,
    issue_id: str | None = None,
    details: dict[str, object] | None = None,
    occurred_at: datetime | None = None,
) -> None:
    with repository.transaction() as connection:
        repository.append_worker_admin_action_log(
            connection,
            occurred_at=occurred_at or now_local(),
            operator_id=operator.operator_id,
            operator_role=operator.role,
            auth_source=operator.auth_source,
            trusted_proxy_id=operator.trusted_proxy_id,
            source_ip=operator.source_ip,
            action_type=action_type,
            dry_run=dry_run,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            worker_id=worker_id,
            session_id=session_id,
            grant_id=grant_id,
            issue_id=issue_id,
            details=_serialize_worker_admin_audit_details(details or {}),
        )


@router.get("/bindings", response_model=WorkerAdminBindingsResponse)
def get_worker_admin_bindings(
    request: Request,
    worker_id: str | None = None,
    tenant_id: str | None = None,
    workspace_id: str | None = None,
    operator: WorkerAdminOperatorContext = Depends(get_worker_admin_operator_context),
) -> WorkerAdminBindingsResponse:
    repository: ControlPlaneRepository = request.app.state.repository
    try:
        resolve_scope_args(tenant_id, workspace_id)
        require_worker_admin_read_scope(
            operator,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
        )
        bindings = list_binding_admin_views(
            repository,
            worker_id=worker_id,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
        )
    except (RuntimeError, ValueError) as exc:
        raise _translate_worker_admin_error(exc) from exc
    return WorkerAdminBindingsResponse(bindings=bindings, count=len(bindings))


@router.get("/operator-tokens", response_model=WorkerAdminOperatorTokensResponse)
def get_worker_admin_operator_tokens(
    request: Request,
    operator_id: str | None = None,
    role: str | None = None,
    tenant_id: str | None = None,
    workspace_id: str | None = None,
    active_only: bool = False,
    operator: WorkerAdminOperatorContext = Depends(get_worker_admin_operator_context),
) -> WorkerAdminOperatorTokensResponse:
    repository: ControlPlaneRepository = request.app.state.repository
    try:
        resolve_scope_args(tenant_id, workspace_id)
        require_worker_admin_read_scope(
            operator,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
        )
        tokens = list_operator_tokens(
            repository,
            operator_id=operator_id,
            role=role,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            active_only=active_only,
        )
    except (RuntimeError, ValueError) as exc:
        raise _translate_worker_admin_error(exc) from exc
    return WorkerAdminOperatorTokensResponse(tokens=tokens, count=len(tokens))


@router.get("/bootstrap-issues", response_model=WorkerAdminBootstrapIssuesResponse)
def get_worker_admin_bootstrap_issues(
    request: Request,
    worker_id: str | None = None,
    tenant_id: str | None = None,
    workspace_id: str | None = None,
    active_only: bool = False,
    operator: WorkerAdminOperatorContext = Depends(get_worker_admin_operator_context),
) -> WorkerAdminBootstrapIssuesResponse:
    repository: ControlPlaneRepository = request.app.state.repository
    try:
        resolve_scope_args(tenant_id, workspace_id)
        require_worker_admin_read_scope(
            operator,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
        )
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
    operator: WorkerAdminOperatorContext = Depends(get_worker_admin_operator_context),
) -> WorkerAdminSessionsResponse:
    repository: ControlPlaneRepository = request.app.state.repository
    try:
        resolve_scope_args(tenant_id, workspace_id)
        require_worker_admin_read_scope(
            operator,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
        )
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
    operator: WorkerAdminOperatorContext = Depends(get_worker_admin_operator_context),
) -> WorkerAdminDeliveryGrantsResponse:
    repository: ControlPlaneRepository = request.app.state.repository
    try:
        resolve_scope_args(tenant_id, workspace_id)
        require_worker_admin_read_scope(
            operator,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
        )
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
    operator: WorkerAdminOperatorContext = Depends(get_worker_admin_operator_context),
) -> WorkerAdminAuthRejectionsResponse:
    repository: ControlPlaneRepository = request.app.state.repository
    try:
        resolve_scope_args(tenant_id, workspace_id)
        require_worker_admin_read_scope(
            operator,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
        )
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
    operator: WorkerAdminOperatorContext = Depends(get_worker_admin_operator_context),
) -> WorkerAdminScopeSummaryResponse:
    repository: ControlPlaneRepository = request.app.state.repository
    try:
        require_worker_admin_read_scope(
            operator,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
        )
        summary = build_scope_summary(
            repository,
            worker_id=worker_id,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
        )
    except (RuntimeError, ValueError) as exc:
        raise _translate_worker_admin_error(exc) from exc
    return WorkerAdminScopeSummaryResponse.model_validate(summary)


@router.post("/revoke-operator-token", response_model=WorkerAdminRevokeOperatorTokenResponse)
def post_worker_admin_revoke_operator_token(
    request: Request,
    payload: WorkerAdminRevokeOperatorTokenRequest,
    operator: WorkerAdminOperatorContext = Depends(get_worker_admin_operator_context),
) -> WorkerAdminRevokeOperatorTokenResponse:
    repository: ControlPlaneRepository = request.app.state.repository
    try:
        token_issue = repository.get_worker_admin_token_issue(payload.token_id)
        if token_issue is None:
            raise RuntimeError("Worker-admin operator token issue was not found.")
        require_worker_admin_write_scope(
            operator,
            tenant_id=token_issue.get("tenant_id"),
            workspace_id=token_issue.get("workspace_id"),
            explicit_scope_required_for_scoped=False,
        )
        if not operator.is_platform_admin and str(token_issue["role"]) == "platform_admin":
            operator.log_auth_rejection("revoke_platform_token_forbidden")
            raise HTTPException(
                status_code=403,
                detail="Scoped worker-admin operators cannot revoke platform_admin tokens.",
            )
        revoked_by = resolve_worker_admin_actor(
            operator,
            asserted_actor=payload.revoked_by,
            field_name="revoked_by",
        )
        revoked = revoke_operator_token(
            repository,
            token_id=payload.token_id,
            revoked_by=revoked_by,
            reason=payload.reason or DEFAULT_OPERATOR_TOKEN_REVOKE_REASON,
        )
    except HTTPException:
        raise
    except (RuntimeError, ValueError) as exc:
        raise _translate_worker_admin_error(exc) from exc
    _append_worker_admin_action_log(
        repository,
        operator=operator,
        action_type="revoke_operator_token",
        dry_run=False,
        tenant_id=revoked.get("tenant_id"),
        workspace_id=revoked.get("workspace_id"),
        details={
            "token_id": revoked["token_id"],
            "target_operator_id": revoked["operator_id"],
            "target_role": revoked["role"],
            "revoke_reason": revoked.get("revoke_reason"),
            "succeeded": True,
        },
        occurred_at=revoked.get("revoked_at"),
    )
    return WorkerAdminRevokeOperatorTokenResponse.model_validate(revoked)


@router.post("/contain-scope", response_model=WorkerAdminContainScopeResponse)
def post_worker_admin_contain_scope(
    request: Request,
    payload: WorkerAdminContainScopeRequest,
    operator: WorkerAdminOperatorContext = Depends(get_worker_admin_operator_context),
) -> WorkerAdminContainScopeResponse:
    repository: ControlPlaneRepository = request.app.state.repository
    try:
        require_worker_admin_write_scope(
            operator,
            tenant_id=payload.tenant_id,
            workspace_id=payload.workspace_id,
            explicit_scope_required_for_scoped=True,
        )
        revoked_by = resolve_worker_admin_actor(
            operator,
            asserted_actor=payload.revoked_by,
            field_name="revoked_by",
        )
        result = contain_scope(
            repository,
            tenant_id=payload.tenant_id,
            workspace_id=payload.workspace_id,
            worker_id=payload.worker_id,
            dry_run=payload.dry_run,
            revoke_bootstrap_issues=payload.revoke_bootstrap_issues,
            revoke_sessions=payload.revoke_sessions,
            revoked_by=revoked_by,
            reason=payload.reason,
            expected_active_bootstrap_issue_count=payload.expected_active_bootstrap_issue_count,
            expected_active_session_count=payload.expected_active_session_count,
            expected_active_delivery_grant_count=payload.expected_active_delivery_grant_count,
        )
    except WorkerAdminConflictError as exc:
        raise _translate_worker_admin_conflict(exc) from exc
    except (RuntimeError, ValueError) as exc:
        raise _translate_worker_admin_error(exc) from exc
    _append_worker_admin_action_log(
        repository,
        operator=operator,
        action_type="contain_scope",
        dry_run=bool(result["dry_run"]),
        tenant_id=payload.tenant_id,
        workspace_id=payload.workspace_id,
        worker_id=payload.worker_id,
        details={
            "requested_actions": result["requested_actions"],
            "impact_summary": result["impact_summary"],
            "executed": result["executed"],
            "result": result.get("result"),
            "succeeded": True,
        },
    )
    return WorkerAdminContainScopeResponse.model_validate(result)


@router.post("/create-binding", response_model=WorkerAdminCreateBindingResponse)
def post_worker_admin_create_binding(
    request: Request,
    payload: WorkerAdminCreateBindingRequest,
    operator: WorkerAdminOperatorContext = Depends(get_worker_admin_operator_context),
) -> WorkerAdminCreateBindingResponse:
    repository: ControlPlaneRepository = request.app.state.repository
    try:
        require_worker_admin_write_scope(
            operator,
            tenant_id=payload.tenant_id,
            workspace_id=payload.workspace_id,
            explicit_scope_required_for_scoped=True,
        )
        binding = create_binding(
            repository,
            worker_id=payload.worker_id,
            tenant_id=payload.tenant_id,
            workspace_id=payload.workspace_id,
        )
    except (RuntimeError, ValueError) as exc:
        raise _translate_worker_admin_error(exc) from exc
    _append_worker_admin_action_log(
        repository,
        operator=operator,
        action_type="create_binding",
        dry_run=False,
        tenant_id=payload.tenant_id,
        workspace_id=payload.workspace_id,
        worker_id=payload.worker_id,
        details={
            "credential_version": binding["credential_version"],
            "succeeded": True,
        },
        occurred_at=binding["updated_at"],
    )
    return WorkerAdminCreateBindingResponse.model_validate(binding)


@router.post("/issue-bootstrap", response_model=WorkerAdminIssueBootstrapResponse)
def post_worker_admin_issue_bootstrap(
    request: Request,
    payload: WorkerAdminIssueBootstrapRequest,
    operator: WorkerAdminOperatorContext = Depends(get_worker_admin_operator_context),
) -> WorkerAdminIssueBootstrapResponse:
    repository: ControlPlaneRepository = request.app.state.repository
    try:
        require_worker_admin_write_scope(
            operator,
            tenant_id=payload.tenant_id,
            workspace_id=payload.workspace_id,
            explicit_scope_required_for_scoped=True,
        )
        issued_by = resolve_worker_admin_actor(
            operator,
            asserted_actor=payload.issued_by,
            field_name="issued_by",
        )
        issued = issue_bootstrap(
            repository,
            worker_id=payload.worker_id,
            ttl_sec=payload.ttl_sec,
            tenant_id=payload.tenant_id,
            workspace_id=payload.workspace_id,
            issued_by=issued_by,
            reason=payload.reason,
            issued_via=WORKER_ADMIN_API_VIA,
        )
    except (RuntimeError, ValueError) as exc:
        raise _translate_worker_admin_error(exc) from exc
    _append_worker_admin_action_log(
        repository,
        operator=operator,
        action_type="issue_bootstrap",
        dry_run=False,
        tenant_id=str(issued["tenant_id"]),
        workspace_id=str(issued["workspace_id"]),
        worker_id=payload.worker_id,
        issue_id=str(issued["issue_id"]),
        details={
            "issued_via": issued["issued_via"],
            "reason": payload.reason,
            "expires_at": issued["expires_at"],
            "succeeded": True,
        },
        occurred_at=issued["issued_at"],
    )
    return WorkerAdminIssueBootstrapResponse.model_validate(issued)


@router.post("/revoke-bootstrap", response_model=WorkerAdminRevokeBootstrapResponse)
def post_worker_admin_revoke_bootstrap(
    request: Request,
    payload: WorkerAdminRevokeBootstrapRequest,
    operator: WorkerAdminOperatorContext = Depends(get_worker_admin_operator_context),
) -> WorkerAdminRevokeBootstrapResponse:
    repository: ControlPlaneRepository = request.app.state.repository
    try:
        require_worker_admin_write_scope(
            operator,
            tenant_id=payload.tenant_id,
            workspace_id=payload.workspace_id,
            explicit_scope_required_for_scoped=True,
        )
        revoked = revoke_bootstrap(
            repository,
            worker_id=payload.worker_id,
            tenant_id=payload.tenant_id,
            workspace_id=payload.workspace_id,
        )
    except (RuntimeError, ValueError) as exc:
        raise _translate_worker_admin_error(exc) from exc
    _append_worker_admin_action_log(
        repository,
        operator=operator,
        action_type="revoke_bootstrap",
        dry_run=False,
        tenant_id=str(revoked["tenant_id"]),
        workspace_id=str(revoked["workspace_id"]),
        worker_id=payload.worker_id,
        details={
            "credential_version": revoked["credential_version"],
            "revoked_before": revoked["revoked_before"],
            "succeeded": True,
        },
        occurred_at=revoked["revoked_before"],
    )
    return WorkerAdminRevokeBootstrapResponse.model_validate(revoked)


@router.post("/revoke-session", response_model=WorkerAdminRevokeSessionResponse)
def post_worker_admin_revoke_session(
    request: Request,
    payload: WorkerAdminRevokeSessionRequest,
    operator: WorkerAdminOperatorContext = Depends(get_worker_admin_operator_context),
) -> WorkerAdminRevokeSessionResponse:
    repository: ControlPlaneRepository = request.app.state.repository
    try:
        if payload.session_id is not None:
            session = repository.get_worker_session(payload.session_id)
            if session is not None:
                require_worker_admin_write_target_scope(
                    operator,
                    tenant_id=str(session["tenant_id"]),
                    workspace_id=str(session["workspace_id"]),
                )
            else:
                require_worker_admin_write_scope(
                    operator,
                    tenant_id=None,
                    workspace_id=None,
                )
        else:
            require_worker_admin_write_scope(
                operator,
                tenant_id=payload.tenant_id,
                workspace_id=payload.workspace_id,
                explicit_scope_required_for_scoped=True,
            )
        revoked_by = resolve_worker_admin_actor(
            operator,
            asserted_actor=payload.revoked_by,
            field_name="revoked_by",
        )
        revoked = revoke_session(
            repository,
            session_id=payload.session_id,
            worker_id=payload.worker_id,
            tenant_id=payload.tenant_id,
            workspace_id=payload.workspace_id,
            revoked_by=revoked_by,
            reason=payload.reason,
            revoked_via=WORKER_ADMIN_API_VIA,
        )
    except (RuntimeError, ValueError) as exc:
        raise _translate_worker_admin_error(exc) from exc
    _append_worker_admin_action_log(
        repository,
        operator=operator,
        action_type="revoke_session",
        dry_run=False,
        tenant_id=str(revoked["tenant_id"]),
        workspace_id=str(revoked["workspace_id"]),
        worker_id=str(revoked["worker_id"]),
        session_id=payload.session_id,
        details={
            "revoked_count": revoked["revoked_count"],
            "revoked_delivery_grant_count": revoked["revoked_delivery_grant_count"],
            "revoke_reason": revoked["revoke_reason"],
            "revoked_via": revoked["revoked_via"],
            "succeeded": True,
        },
        occurred_at=revoked["revoked_at"],
    )
    return WorkerAdminRevokeSessionResponse.model_validate(revoked)


@router.post("/revoke-delivery-grant", response_model=WorkerAdminRevokeDeliveryGrantResponse)
def post_worker_admin_revoke_delivery_grant(
    request: Request,
    payload: WorkerAdminRevokeDeliveryGrantRequest,
    operator: WorkerAdminOperatorContext = Depends(get_worker_admin_operator_context),
) -> WorkerAdminRevokeDeliveryGrantResponse:
    repository: ControlPlaneRepository = request.app.state.repository
    try:
        grant = repository.get_worker_delivery_grant(payload.grant_id)
        if grant is not None:
            require_worker_admin_write_target_scope(
                operator,
                tenant_id=str(grant["tenant_id"]),
                workspace_id=str(grant["workspace_id"]),
            )
        else:
            require_worker_admin_write_scope(
                operator,
                tenant_id=None,
                workspace_id=None,
            )
        revoked_by = resolve_worker_admin_actor(
            operator,
            asserted_actor=payload.revoked_by,
            field_name="revoked_by",
        )
        revoked = revoke_delivery_grant(
            repository,
            grant_id=payload.grant_id,
            revoked_by=revoked_by,
            reason=payload.reason,
            revoked_via=WORKER_ADMIN_API_VIA,
        )
    except (RuntimeError, ValueError) as exc:
        raise _translate_worker_admin_error(exc) from exc
    _append_worker_admin_action_log(
        repository,
        operator=operator,
        action_type="revoke_delivery_grant",
        dry_run=False,
        tenant_id=str(revoked["tenant_id"]),
        workspace_id=str(revoked["workspace_id"]),
        worker_id=str(revoked["worker_id"]),
        session_id=str(revoked["session_id"]),
        grant_id=payload.grant_id,
        details={
            "revoked_count": revoked["revoked_count"],
            "revoke_reason": revoked["revoke_reason"],
            "revoked_via": revoked["revoked_via"],
            "succeeded": True,
        },
        occurred_at=revoked["revoked_at"],
    )
    return WorkerAdminRevokeDeliveryGrantResponse.model_validate(revoked)


@router.post("/cleanup-bindings", response_model=WorkerAdminCleanupBindingsResponse)
def post_worker_admin_cleanup_bindings(
    request: Request,
    payload: WorkerAdminCleanupBindingsRequest,
    operator: WorkerAdminOperatorContext = Depends(get_worker_admin_operator_context),
) -> WorkerAdminCleanupBindingsResponse:
    repository: ControlPlaneRepository = request.app.state.repository
    try:
        require_worker_admin_write_scope(
            operator,
            tenant_id=payload.tenant_id,
            workspace_id=payload.workspace_id,
            explicit_scope_required_for_scoped=True,
        )
        cleaned = cleanup_bindings(
            repository,
            worker_id=payload.worker_id,
            tenant_id=payload.tenant_id,
            workspace_id=payload.workspace_id,
            dry_run=payload.dry_run,
        )
    except (RuntimeError, ValueError) as exc:
        raise _translate_worker_admin_error(exc) from exc
    _append_worker_admin_action_log(
        repository,
        operator=operator,
        action_type="cleanup_bindings",
        dry_run=bool(payload.dry_run),
        tenant_id=payload.tenant_id,
        workspace_id=payload.workspace_id,
        worker_id=payload.worker_id,
        details={
            "executed": not bool(payload.dry_run),
            "candidate_count": cleaned["count"],
            "deleted_count": cleaned["deleted_count"],
            "binding_scopes": [
                {
                    "tenant_id": str(binding["tenant_id"]),
                    "workspace_id": str(binding["workspace_id"]),
                }
                for binding in cleaned["bindings"]
            ],
            "succeeded": True,
        },
        occurred_at=cleaned["cleaned_at"],
    )
    return WorkerAdminCleanupBindingsResponse.model_validate(cleaned)
