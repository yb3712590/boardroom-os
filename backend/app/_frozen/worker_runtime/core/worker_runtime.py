from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import urlencode

from fastapi import HTTPException, Request

from app.config import get_settings
from app.core.context_compiler import compile_and_persist_execution_artifacts
from app.core.output_schemas import get_output_schema_body
from app.core.time import now_local
from app.core.worker_bootstrap_tokens import (
    WorkerBootstrapTokenClaims,
    WorkerSessionTokenClaims,
    issue_worker_session_token as issue_worker_session_access_token,
    validate_worker_bootstrap_token,
    validate_worker_session_token,
)
from app.core.worker_delivery_tokens import (
    WorkerArtifactAction,
    WorkerCommandName,
    WorkerDeliveryScope,
    WorkerDeliveryTokenClaims,
    issue_worker_delivery_token,
    validate_worker_delivery_token,
)
from app.db.repository import ControlPlaneRepository

ACTIVE_WORKER_TICKET_STATUSES = {"LEASED", "EXECUTING", "CANCEL_REQUESTED"}


@dataclass(frozen=True)
class WorkerPrincipal:
    worker_id: str
    tenant_id: str
    workspace_id: str
    session_id: str | None = None
    credential_version: int | None = None


@dataclass(frozen=True)
class WorkerAssignmentAuthContext:
    principal: WorkerPrincipal
    session_id: str
    session_token: str
    session_expires_at: datetime


class WorkerAuthError(Exception):
    def __init__(
        self,
        *,
        status_code: int,
        detail: str,
        reason_code: str,
        worker_id: str | None = None,
        session_id: str | None = None,
        grant_id: str | None = None,
        ticket_id: str | None = None,
        tenant_id: str | None = None,
        workspace_id: str | None = None,
    ) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail
        self.reason_code = reason_code
        self.worker_id = worker_id
        self.session_id = session_id
        self.grant_id = grant_id
        self.ticket_id = ticket_id
        self.tenant_id = tenant_id
        self.workspace_id = workspace_id


def _raise_worker_auth_error(
    *,
    status_code: int,
    detail: str,
    reason_code: str,
    worker_id: str | None = None,
    session_id: str | None = None,
    grant_id: str | None = None,
    ticket_id: str | None = None,
    tenant_id: str | None = None,
    workspace_id: str | None = None,
) -> None:
    raise WorkerAuthError(
        status_code=status_code,
        detail=detail,
        reason_code=reason_code,
        worker_id=worker_id,
        session_id=session_id,
        grant_id=grant_id,
        ticket_id=ticket_id,
        tenant_id=tenant_id,
        workspace_id=workspace_id,
    )


def _log_worker_auth_rejection(
    repository: ControlPlaneRepository,
    *,
    route_family: str,
    error: WorkerAuthError,
    occurred_at: datetime,
) -> None:
    with repository.transaction() as connection:
        repository.append_worker_auth_rejection_log(
            connection,
            occurred_at=occurred_at,
            route_family=route_family,
            reason_code=error.reason_code,
            worker_id=error.worker_id,
            session_id=error.session_id,
            grant_id=error.grant_id,
            ticket_id=error.ticket_id,
            tenant_id=error.tenant_id,
            workspace_id=error.workspace_id,
        )


def _resolve_worker_bootstrap_signing_secret() -> str:
    settings = get_settings()
    signing_secret = settings.worker_bootstrap_signing_secret or settings.worker_shared_secret
    if not signing_secret:
        raise HTTPException(
            status_code=503,
            detail="Worker bootstrap signing secret is not configured.",
        )
    return signing_secret


def _resolve_worker_delivery_signing_secret() -> str:
    settings = get_settings()
    signing_secret = (
        settings.worker_delivery_signing_secret
        or settings.worker_shared_secret
        or settings.worker_bootstrap_signing_secret
    )
    if not signing_secret:
        raise HTTPException(
            status_code=503,
            detail="Worker delivery signing secret is not configured.",
        )
    return signing_secret


def _resolve_worker_public_base_url(request: Request) -> str:
    settings = get_settings()
    return settings.public_base_url or str(request.base_url).rstrip("/")


def _resolve_worker_session_ttl_sec() -> int:
    return get_settings().worker_session_ttl_sec


def _resolve_worker_delivery_token_ttl_sec() -> int:
    return get_settings().worker_delivery_token_ttl_sec


def _require_delivery_access_token(access_token: str | None) -> str:
    if not access_token:
        raise HTTPException(status_code=401, detail="Worker delivery access_token is required.")
    return access_token


def _require_active_worker_projection(
    repository: ControlPlaneRepository,
    worker_id: str,
    *,
    connection=None,
) -> dict[str, Any]:
    employee = repository.get_employee_projection(worker_id, connection=connection)
    if employee is None:
        raise HTTPException(
            status_code=403,
            detail=f"Worker '{worker_id}' is not registered.",
        )
    if str(employee.get("state") or "") != "ACTIVE":
        raise HTTPException(
            status_code=403,
            detail=f"Worker '{worker_id}' is not active.",
        )
    return employee


def _issue_worker_session_token(
    *,
    session_id: str,
    worker_id: str,
    credential_version: int,
    tenant_id: str,
    workspace_id: str,
    issued_at: datetime,
) -> tuple[str, datetime]:
    return issue_worker_session_access_token(
        signing_secret=_resolve_worker_bootstrap_signing_secret(),
        session_id=session_id,
        worker_id=worker_id,
        credential_version=credential_version,
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        issued_at=issued_at,
        ttl_sec=_resolve_worker_session_ttl_sec(),
    )


def _validate_bootstrap_claims_against_state(
    claims: WorkerBootstrapTokenClaims,
    state: dict[str, Any],
) -> None:
    if claims.credential_version != int(state.get("credential_version") or 0):
        _raise_worker_auth_error(
            status_code=401,
            detail="Worker bootstrap token is invalid.",
            reason_code="bootstrap_invalid",
            worker_id=claims.worker_id,
            tenant_id=claims.tenant_id,
            workspace_id=claims.workspace_id,
        )
    if claims.tenant_id != str(state.get("tenant_id") or "") or claims.workspace_id != str(
        state.get("workspace_id") or ""
    ):
        _raise_worker_auth_error(
            status_code=401,
            detail="Worker bootstrap token scope does not match the stored worker binding.",
            reason_code="session_scope_mismatch",
            worker_id=claims.worker_id,
            tenant_id=claims.tenant_id,
            workspace_id=claims.workspace_id,
        )
    revoked_before = state.get("revoked_before")
    if revoked_before is not None and claims.issued_at < revoked_before:
        _raise_worker_auth_error(
            status_code=401,
            detail="Worker bootstrap token has been revoked.",
            reason_code="bootstrap_revoked",
            worker_id=claims.worker_id,
            tenant_id=claims.tenant_id,
            workspace_id=claims.workspace_id,
        )


def _validate_bootstrap_issue_against_claims(
    claims: WorkerBootstrapTokenClaims,
    *,
    issue_row: dict[str, Any] | None,
    at: datetime,
) -> None:
    if claims.issue_id is None:
        return
    if issue_row is None:
        _raise_worker_auth_error(
            status_code=401,
            detail="Worker bootstrap token is invalid.",
            reason_code="bootstrap_invalid",
            worker_id=claims.worker_id,
            tenant_id=claims.tenant_id,
            workspace_id=claims.workspace_id,
        )
    if issue_row.get("revoked_at") is not None:
        _raise_worker_auth_error(
            status_code=401,
            detail="Worker bootstrap token has been revoked.",
            reason_code="bootstrap_revoked",
            worker_id=claims.worker_id,
            tenant_id=claims.tenant_id,
            workspace_id=claims.workspace_id,
        )
    if issue_row.get("expires_at") is None or issue_row["expires_at"] <= at:
        _raise_worker_auth_error(
            status_code=401,
            detail="Worker bootstrap token has expired.",
            reason_code="bootstrap_expired",
            worker_id=claims.worker_id,
            tenant_id=claims.tenant_id,
            workspace_id=claims.workspace_id,
        )
    if (
        str(issue_row.get("worker_id") or "") != claims.worker_id
        or str(issue_row.get("tenant_id") or "") != claims.tenant_id
        or str(issue_row.get("workspace_id") or "") != claims.workspace_id
        or int(issue_row.get("credential_version") or 0) != claims.credential_version
        or issue_row.get("issued_at") != claims.issued_at
        or issue_row.get("expires_at") != claims.expires_at
    ):
        _raise_worker_auth_error(
            status_code=401,
            detail="Worker bootstrap token is invalid.",
            reason_code="bootstrap_invalid",
            worker_id=claims.worker_id,
            tenant_id=claims.tenant_id,
            workspace_id=claims.workspace_id,
        )


def _validate_session_claims_against_state(
    claims: WorkerSessionTokenClaims | WorkerDeliveryTokenClaims,
    *,
    state: dict[str, Any] | None,
    session_row: dict[str, Any] | None,
    at: datetime,
) -> None:
    if state is None:
        _raise_worker_auth_error(
            status_code=401,
            detail="Worker session token is invalid.",
            reason_code="session_invalid",
            worker_id=claims.worker_id,
            session_id=getattr(claims, "session_id", None),
            tenant_id=claims.tenant_id,
            workspace_id=claims.workspace_id,
        )
    if claims.credential_version != int(state.get("credential_version") or 0):
        _raise_worker_auth_error(
            status_code=401,
            detail="Worker session token is invalid.",
            reason_code="session_invalid",
            worker_id=claims.worker_id,
            session_id=getattr(claims, "session_id", None),
            tenant_id=claims.tenant_id,
            workspace_id=claims.workspace_id,
        )
    if claims.tenant_id != str(state.get("tenant_id") or "") or claims.workspace_id != str(
        state.get("workspace_id") or ""
    ):
        _raise_worker_auth_error(
            status_code=401,
            detail="Worker session token scope does not match the stored worker binding.",
            reason_code="session_scope_mismatch",
            worker_id=claims.worker_id,
            session_id=getattr(claims, "session_id", None),
            tenant_id=claims.tenant_id,
            workspace_id=claims.workspace_id,
        )
    if session_row is None:
        _raise_worker_auth_error(
            status_code=401,
            detail="Worker session token is invalid.",
            reason_code="session_invalid",
            worker_id=claims.worker_id,
            session_id=getattr(claims, "session_id", None),
            tenant_id=claims.tenant_id,
            workspace_id=claims.workspace_id,
        )
    if session_row.get("worker_id") != claims.worker_id:
        _raise_worker_auth_error(
            status_code=401,
            detail="Worker session token is invalid.",
            reason_code="session_invalid",
            worker_id=claims.worker_id,
            session_id=getattr(claims, "session_id", None),
            tenant_id=claims.tenant_id,
            workspace_id=claims.workspace_id,
        )
    if int(session_row.get("credential_version") or 0) != claims.credential_version:
        _raise_worker_auth_error(
            status_code=401,
            detail="Worker session token is invalid.",
            reason_code="session_invalid",
            worker_id=claims.worker_id,
            session_id=getattr(claims, "session_id", None),
            tenant_id=claims.tenant_id,
            workspace_id=claims.workspace_id,
        )
    if claims.tenant_id != str(session_row.get("tenant_id") or "") or claims.workspace_id != str(
        session_row.get("workspace_id") or ""
    ):
        _raise_worker_auth_error(
            status_code=401,
            detail="Worker session token scope does not match the active session.",
            reason_code="session_scope_mismatch",
            worker_id=claims.worker_id,
            session_id=getattr(claims, "session_id", None),
            tenant_id=claims.tenant_id,
            workspace_id=claims.workspace_id,
        )
    revoked_at = session_row.get("revoked_at")
    if revoked_at is not None:
        _raise_worker_auth_error(
            status_code=401,
            detail="Worker session token has been revoked.",
            reason_code="session_revoked",
            worker_id=claims.worker_id,
            session_id=getattr(claims, "session_id", None),
            tenant_id=claims.tenant_id,
            workspace_id=claims.workspace_id,
        )
    expires_at = session_row.get("expires_at")
    if expires_at is None or expires_at <= at:
        _raise_worker_auth_error(
            status_code=401,
            detail="Worker session token has expired.",
            reason_code="session_expired",
            worker_id=claims.worker_id,
            session_id=getattr(claims, "session_id", None),
            tenant_id=claims.tenant_id,
            workspace_id=claims.workspace_id,
        )


def _validate_delivery_grant_against_claims(
    grant: dict[str, Any] | None,
    *,
    claims: WorkerDeliveryTokenClaims,
    at: datetime,
) -> None:
    if grant is None:
        _raise_worker_auth_error(
            status_code=401,
            detail="Worker delivery token is invalid.",
            reason_code="grant_invalid",
            worker_id=claims.worker_id,
            session_id=claims.session_id,
            grant_id=claims.grant_id,
            ticket_id=claims.ticket_id,
            tenant_id=claims.tenant_id,
            workspace_id=claims.workspace_id,
        )
    if str(grant.get("scope") or "") != claims.scope:
        _raise_worker_auth_error(
            status_code=401,
            detail="Worker delivery token is invalid.",
            reason_code="grant_invalid",
            worker_id=claims.worker_id,
            session_id=claims.session_id,
            grant_id=claims.grant_id,
            ticket_id=claims.ticket_id,
            tenant_id=claims.tenant_id,
            workspace_id=claims.workspace_id,
        )
    if str(grant.get("worker_id") or "") != claims.worker_id:
        _raise_worker_auth_error(
            status_code=401,
            detail="Worker delivery token is invalid.",
            reason_code="grant_invalid",
            worker_id=claims.worker_id,
            session_id=claims.session_id,
            grant_id=claims.grant_id,
            ticket_id=claims.ticket_id,
            tenant_id=claims.tenant_id,
            workspace_id=claims.workspace_id,
        )
    if str(grant.get("session_id") or "") != claims.session_id:
        _raise_worker_auth_error(
            status_code=401,
            detail="Worker delivery token is invalid.",
            reason_code="grant_invalid",
            worker_id=claims.worker_id,
            session_id=claims.session_id,
            grant_id=claims.grant_id,
            ticket_id=claims.ticket_id,
            tenant_id=claims.tenant_id,
            workspace_id=claims.workspace_id,
        )
    if int(grant.get("credential_version") or 0) != claims.credential_version:
        _raise_worker_auth_error(
            status_code=401,
            detail="Worker delivery token is invalid.",
            reason_code="grant_invalid",
            worker_id=claims.worker_id,
            session_id=claims.session_id,
            grant_id=claims.grant_id,
            ticket_id=claims.ticket_id,
            tenant_id=claims.tenant_id,
            workspace_id=claims.workspace_id,
        )
    if claims.tenant_id != str(grant.get("tenant_id") or "") or claims.workspace_id != str(
        grant.get("workspace_id") or ""
    ):
        _raise_worker_auth_error(
            status_code=401,
            detail="Worker delivery token scope does not match the persisted grant.",
            reason_code="grant_scope_mismatch",
            worker_id=claims.worker_id,
            session_id=claims.session_id,
            grant_id=claims.grant_id,
            ticket_id=claims.ticket_id,
            tenant_id=claims.tenant_id,
            workspace_id=claims.workspace_id,
        )
    if str(grant.get("ticket_id") or "") != claims.ticket_id:
        _raise_worker_auth_error(
            status_code=401,
            detail="Worker delivery token is invalid.",
            reason_code="grant_invalid",
            worker_id=claims.worker_id,
            session_id=claims.session_id,
            grant_id=claims.grant_id,
            ticket_id=claims.ticket_id,
            tenant_id=claims.tenant_id,
            workspace_id=claims.workspace_id,
        )
    if (grant.get("artifact_ref") or None) != claims.artifact_ref:
        _raise_worker_auth_error(
            status_code=401,
            detail="Worker delivery token is invalid.",
            reason_code="grant_invalid",
            worker_id=claims.worker_id,
            session_id=claims.session_id,
            grant_id=claims.grant_id,
            ticket_id=claims.ticket_id,
            tenant_id=claims.tenant_id,
            workspace_id=claims.workspace_id,
        )
    if (grant.get("artifact_action") or None) != claims.artifact_action:
        _raise_worker_auth_error(
            status_code=401,
            detail="Worker delivery token is invalid.",
            reason_code="grant_invalid",
            worker_id=claims.worker_id,
            session_id=claims.session_id,
            grant_id=claims.grant_id,
            ticket_id=claims.ticket_id,
            tenant_id=claims.tenant_id,
            workspace_id=claims.workspace_id,
        )
    if (grant.get("command_name") or None) != claims.command_name:
        _raise_worker_auth_error(
            status_code=401,
            detail="Worker delivery token is invalid.",
            reason_code="grant_invalid",
            worker_id=claims.worker_id,
            session_id=claims.session_id,
            grant_id=claims.grant_id,
            ticket_id=claims.ticket_id,
            tenant_id=claims.tenant_id,
            workspace_id=claims.workspace_id,
        )
    revoked_at = grant.get("revoked_at")
    if revoked_at is not None:
        _raise_worker_auth_error(
            status_code=401,
            detail="Worker delivery token has been revoked.",
            reason_code="grant_revoked",
            worker_id=claims.worker_id,
            session_id=claims.session_id,
            grant_id=claims.grant_id,
            ticket_id=claims.ticket_id,
            tenant_id=claims.tenant_id,
            workspace_id=claims.workspace_id,
        )
    expires_at = grant.get("expires_at")
    if expires_at is None or expires_at <= at:
        _raise_worker_auth_error(
            status_code=401,
            detail="Worker delivery token has expired.",
            reason_code="grant_expired",
            worker_id=claims.worker_id,
            session_id=claims.session_id,
            grant_id=claims.grant_id,
            ticket_id=claims.ticket_id,
            tenant_id=claims.tenant_id,
            workspace_id=claims.workspace_id,
        )


def _create_or_refresh_worker_session(
    repository: ControlPlaneRepository,
    *,
    worker_id: str,
    credential_version: int,
    tenant_id: str,
    workspace_id: str,
    at: datetime,
    session_id: str | None = None,
) -> dict[str, Any]:
    expires_at = at + timedelta(seconds=_resolve_worker_session_ttl_sec())
    with repository.transaction() as connection:
        if session_id is None:
            return repository.create_worker_session(
                connection,
                worker_id=worker_id,
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                issued_at=at,
                expires_at=expires_at,
                credential_version=credential_version,
            )
        refreshed = repository.refresh_worker_session(
            connection,
            session_id=session_id,
            refreshed_at=at,
            expires_at=expires_at,
        )
        if refreshed is None:
            _raise_worker_auth_error(
                status_code=401,
                detail="Worker session token is invalid.",
                reason_code="session_invalid",
                worker_id=worker_id,
                session_id=session_id,
                tenant_id=tenant_id,
                workspace_id=workspace_id,
            )
        return refreshed


def _build_assignment_auth_context_from_session_row(
    session_row: dict[str, Any],
    *,
    at: datetime,
) -> WorkerAssignmentAuthContext:
    session_token, session_expires_at = _issue_worker_session_token(
        session_id=str(session_row["session_id"]),
        worker_id=str(session_row["worker_id"]),
        credential_version=int(session_row["credential_version"]),
        tenant_id=str(session_row["tenant_id"]),
        workspace_id=str(session_row["workspace_id"]),
        issued_at=at,
    )
    return WorkerAssignmentAuthContext(
        principal=WorkerPrincipal(
            worker_id=str(session_row["worker_id"]),
            tenant_id=str(session_row["tenant_id"]),
            workspace_id=str(session_row["workspace_id"]),
            session_id=str(session_row["session_id"]),
            credential_version=int(session_row["credential_version"]),
        ),
        session_id=str(session_row["session_id"]),
        session_token=session_token,
        session_expires_at=session_expires_at,
    )


def _authenticate_worker_bootstrap(
    request: Request,
    *,
    bootstrap_token: str,
) -> WorkerAssignmentAuthContext:
    repository: ControlPlaneRepository = request.app.state.repository
    current_time = now_local()
    claims = validate_worker_bootstrap_token(
        bootstrap_token,
        signing_secret=_resolve_worker_bootstrap_signing_secret(),
        at=current_time,
    )
    with repository.transaction() as connection:
        state = repository.ensure_worker_bootstrap_state(
            connection,
            worker_id=claims.worker_id,
            at=current_time,
            tenant_id=claims.tenant_id,
            workspace_id=claims.workspace_id,
        )
        issue_row = (
            repository.get_worker_bootstrap_issue(claims.issue_id, connection=connection)
            if claims.issue_id is not None
            else None
        )
        _validate_bootstrap_issue_against_claims(
            claims,
            issue_row=issue_row,
            at=current_time,
        )
        _validate_bootstrap_claims_against_state(claims, state)
        _require_active_worker_projection(repository, claims.worker_id, connection=connection)
    session_row = _create_or_refresh_worker_session(
        repository,
        worker_id=claims.worker_id,
        credential_version=int(state["credential_version"]),
        tenant_id=str(state["tenant_id"]),
        workspace_id=str(state["workspace_id"]),
        at=current_time,
    )
    return _build_assignment_auth_context_from_session_row(session_row, at=current_time)


def _authenticate_worker_session(
    request: Request,
    *,
    session_token: str,
) -> WorkerAssignmentAuthContext:
    repository: ControlPlaneRepository = request.app.state.repository
    current_time = now_local()
    claims = validate_worker_session_token(
        session_token,
        signing_secret=_resolve_worker_bootstrap_signing_secret(),
        at=current_time,
    )
    with repository.transaction() as connection:
        state = repository.ensure_worker_bootstrap_state(
            connection,
            worker_id=claims.worker_id,
            at=current_time,
            tenant_id=claims.tenant_id,
            workspace_id=claims.workspace_id,
        )
        session_row = repository.get_worker_session(claims.session_id, connection=connection)
        _validate_session_claims_against_state(
            claims,
            state=state,
            session_row=session_row,
            at=current_time,
        )
        _require_active_worker_projection(repository, claims.worker_id, connection=connection)
    refreshed_session = _create_or_refresh_worker_session(
        repository,
        worker_id=claims.worker_id,
        credential_version=claims.credential_version,
        tenant_id=claims.tenant_id,
        workspace_id=claims.workspace_id,
        at=current_time,
        session_id=claims.session_id,
    )
    return _build_assignment_auth_context_from_session_row(refreshed_session, at=current_time)


def authenticate_worker_assignments_request(
    request: Request,
    *,
    bootstrap_token: str | None,
    session_token: str | None,
) -> WorkerAssignmentAuthContext:
    repository: ControlPlaneRepository = request.app.state.repository
    current_time = now_local()
    try:
        if bootstrap_token:
            return _authenticate_worker_bootstrap(
                request,
                bootstrap_token=bootstrap_token,
            )
        if session_token:
            return _authenticate_worker_session(
                request,
                session_token=session_token,
            )
        raise HTTPException(
            status_code=401,
            detail="Worker bootstrap or session headers are required.",
        )
    except WorkerAuthError as exc:
        _log_worker_auth_rejection(
            repository,
            route_family="assignments",
            error=exc,
            occurred_at=current_time,
        )
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


def _issue_worker_delivery_token(
    request: Request,
    *,
    scope: WorkerDeliveryScope,
    worker_id: str,
    session_id: str,
    credential_version: int,
    tenant_id: str,
    workspace_id: str,
    ticket_id: str,
    issued_at: datetime,
    artifact_ref: str | None = None,
    artifact_action: WorkerArtifactAction | None = None,
    command_name: WorkerCommandName | None = None,
) -> tuple[str, datetime]:
    repository: ControlPlaneRepository = request.app.state.repository
    ttl_sec = _resolve_worker_delivery_token_ttl_sec()
    expires_at = issued_at + timedelta(seconds=ttl_sec)
    with repository.transaction() as connection:
        grant = repository.create_worker_delivery_grant(
            connection,
            scope=scope,
            worker_id=worker_id,
            session_id=session_id,
            credential_version=credential_version,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            ticket_id=ticket_id,
            artifact_ref=artifact_ref,
            artifact_action=artifact_action,
            command_name=command_name,
            issued_at=issued_at,
            expires_at=expires_at,
        )
    token, _ = issue_worker_delivery_token(
        signing_secret=_resolve_worker_delivery_signing_secret(),
        grant_id=str(grant["grant_id"]),
        scope=scope,
        worker_id=worker_id,
        session_id=session_id,
        credential_version=credential_version,
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        ticket_id=ticket_id,
        issued_at=issued_at,
        ttl_sec=ttl_sec,
        artifact_ref=artifact_ref,
        artifact_action=artifact_action,
        command_name=command_name,
    )
    return token, expires_at


def authenticate_worker(
    request: Request,
    *,
    worker_key: str | None,
    worker_id: str | None,
) -> WorkerPrincipal:
    settings = get_settings()
    if not settings.worker_shared_secret:
        raise HTTPException(
            status_code=503,
            detail="Worker runtime shared secret is not configured.",
        )
    if not worker_key or not worker_id:
        raise HTTPException(
            status_code=401,
            detail="Worker runtime authentication headers are required.",
        )
    if worker_key != settings.worker_shared_secret:
        raise HTTPException(
            status_code=401,
            detail="Worker runtime shared secret is invalid.",
        )

    repository: ControlPlaneRepository = request.app.state.repository
    _require_active_worker_projection(repository, worker_id)
    return WorkerPrincipal(
        worker_id=worker_id,
        tenant_id="tenant_default",
        workspace_id="ws_default",
    )


def authenticate_worker_request(
    request: Request,
    *,
    access_token: str | None,
    scope: WorkerDeliveryScope,
    ticket_id: str,
    artifact_ref: str | None = None,
    artifact_action: WorkerArtifactAction | None = None,
    command_name: WorkerCommandName | None = None,
) -> WorkerPrincipal:
    current_time = now_local()
    repository: ControlPlaneRepository = request.app.state.repository
    try:
        claims = validate_worker_delivery_token(
            _require_delivery_access_token(access_token),
            signing_secret=_resolve_worker_delivery_signing_secret(),
            expected_scope=scope,
            expected_ticket_id=ticket_id,
            expected_artifact_ref=artifact_ref,
            expected_artifact_action=artifact_action,
            expected_command_name=command_name,
            at=current_time,
        )
        with repository.transaction() as connection:
            grant = repository.get_worker_delivery_grant(claims.grant_id, connection=connection)
            _validate_delivery_grant_against_claims(
                grant,
                claims=claims,
                at=current_time,
            )
            state = repository.get_worker_bootstrap_state(
                claims.worker_id,
                tenant_id=claims.tenant_id,
                workspace_id=claims.workspace_id,
                connection=connection,
            )
            session_row = repository.get_worker_session(claims.session_id, connection=connection)
            _validate_session_claims_against_state(
                claims,
                state=state,
                session_row=session_row,
                at=current_time,
            )
            _require_active_worker_projection(repository, claims.worker_id, connection=connection)
            ticket = repository.get_current_ticket_projection(ticket_id, connection=connection)
            _validate_ticket_scope_and_ownership(
                repository,
                ticket=ticket,
                principal=WorkerPrincipal(
                    worker_id=claims.worker_id,
                    tenant_id=claims.tenant_id,
                    workspace_id=claims.workspace_id,
                    session_id=claims.session_id,
                    credential_version=claims.credential_version,
                ),
                connection=connection,
            )
        return WorkerPrincipal(
            worker_id=claims.worker_id,
            tenant_id=claims.tenant_id,
            workspace_id=claims.workspace_id,
            session_id=claims.session_id,
            credential_version=claims.credential_version,
        )
    except WorkerAuthError as exc:
        _log_worker_auth_rejection(
            repository,
            route_family=scope,
            error=exc,
            occurred_at=current_time,
        )
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


def _validate_ticket_scope_and_ownership(
    repository: ControlPlaneRepository,
    *,
    ticket: dict[str, Any] | None,
    principal: WorkerPrincipal,
    connection=None,
) -> dict[str, Any]:
    if ticket is None:
        _raise_worker_auth_error(
            status_code=404,
            detail="Worker ticket was not found.",
            reason_code="ticket_not_found",
            worker_id=principal.worker_id,
            session_id=principal.session_id,
            tenant_id=principal.tenant_id,
            workspace_id=principal.workspace_id,
        )
    if ticket.get("lease_owner") != principal.worker_id or ticket["status"] not in ACTIVE_WORKER_TICKET_STATUSES:
        _raise_worker_auth_error(
            status_code=403,
            detail=f"Worker '{principal.worker_id}' does not currently own ticket '{ticket['ticket_id']}'.",
            reason_code="ticket_ownership_mismatch",
            worker_id=principal.worker_id,
            session_id=principal.session_id,
            ticket_id=str(ticket["ticket_id"]),
            tenant_id=principal.tenant_id,
            workspace_id=principal.workspace_id,
        )
    if str(ticket.get("tenant_id") or "") != principal.tenant_id:
        _raise_worker_auth_error(
            status_code=403,
            detail="Worker tenant does not match the ticket tenant scope.",
            reason_code="tenant_mismatch",
            worker_id=principal.worker_id,
            session_id=principal.session_id,
            ticket_id=str(ticket["ticket_id"]),
            tenant_id=principal.tenant_id,
            workspace_id=principal.workspace_id,
        )
    if str(ticket.get("workspace_id") or "") != principal.workspace_id:
        _raise_worker_auth_error(
            status_code=403,
            detail="Worker workspace does not match the ticket workspace scope.",
            reason_code="workspace_mismatch",
            worker_id=principal.worker_id,
            session_id=principal.session_id,
            ticket_id=str(ticket["ticket_id"]),
            tenant_id=principal.tenant_id,
            workspace_id=principal.workspace_id,
        )
    workflow = repository.get_workflow_projection(str(ticket["workflow_id"]), connection=connection)
    if workflow is not None:
        if str(workflow.get("tenant_id") or "") != principal.tenant_id:
            _raise_worker_auth_error(
                status_code=403,
                detail="Worker tenant does not match the workflow tenant scope.",
                reason_code="tenant_mismatch",
                worker_id=principal.worker_id,
                session_id=principal.session_id,
                ticket_id=str(ticket["ticket_id"]),
                tenant_id=principal.tenant_id,
                workspace_id=principal.workspace_id,
            )
        if str(workflow.get("workspace_id") or "") != principal.workspace_id:
            _raise_worker_auth_error(
                status_code=403,
                detail="Worker workspace does not match the workflow workspace scope.",
                reason_code="workspace_mismatch",
                worker_id=principal.worker_id,
                session_id=principal.session_id,
                ticket_id=str(ticket["ticket_id"]),
                tenant_id=principal.tenant_id,
                workspace_id=principal.workspace_id,
            )
    return ticket


def build_worker_artifact_urls(
    request: Request,
    *,
    worker_id: str,
    session_id: str,
    credential_version: int,
    tenant_id: str,
    workspace_id: str,
    ticket_id: str,
    artifact_ref: str,
    issued_at: datetime,
) -> tuple[dict[str, str], datetime]:
    base_url = _resolve_worker_public_base_url(request)
    content_token, expires_at = _issue_worker_delivery_token(
        request,
        scope="artifact_read",
        worker_id=worker_id,
        session_id=session_id,
        credential_version=credential_version,
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        ticket_id=ticket_id,
        artifact_ref=artifact_ref,
        artifact_action="content_inline",
        issued_at=issued_at,
    )
    download_token, _ = _issue_worker_delivery_token(
        request,
        scope="artifact_read",
        worker_id=worker_id,
        session_id=session_id,
        credential_version=credential_version,
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        ticket_id=ticket_id,
        artifact_ref=artifact_ref,
        artifact_action="content_attachment",
        issued_at=issued_at,
    )
    preview_token, _ = _issue_worker_delivery_token(
        request,
        scope="artifact_read",
        worker_id=worker_id,
        session_id=session_id,
        credential_version=credential_version,
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        ticket_id=ticket_id,
        artifact_ref=artifact_ref,
        artifact_action="preview",
        issued_at=issued_at,
    )
    return {
        "content_url": (
            f"{base_url}/api/v1/worker-runtime/artifacts/content?"
            f"{urlencode({'artifact_ref': artifact_ref, 'ticket_id': ticket_id, 'disposition': 'inline', 'access_token': content_token})}"
        ),
        "download_url": (
            f"{base_url}/api/v1/worker-runtime/artifacts/content?"
            f"{urlencode({'artifact_ref': artifact_ref, 'ticket_id': ticket_id, 'disposition': 'attachment', 'access_token': download_token})}"
        ),
        "preview_url": (
            f"{base_url}/api/v1/worker-runtime/artifacts/preview?"
            f"{urlencode({'artifact_ref': artifact_ref, 'ticket_id': ticket_id, 'access_token': preview_token})}"
        ),
    }, expires_at


def build_worker_execution_package_url(
    request: Request,
    *,
    worker_id: str,
    session_id: str,
    credential_version: int,
    tenant_id: str,
    workspace_id: str,
    ticket_id: str,
    issued_at: datetime,
) -> tuple[str, datetime]:
    base_url = _resolve_worker_public_base_url(request)
    token, expires_at = _issue_worker_delivery_token(
        request,
        scope="execution_package",
        worker_id=worker_id,
        session_id=session_id,
        credential_version=credential_version,
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        ticket_id=ticket_id,
        issued_at=issued_at,
    )
    return (
        f"{base_url}/api/v1/worker-runtime/tickets/{ticket_id}/execution-package?"
        f"{urlencode({'access_token': token})}",
        expires_at,
    )


def _build_worker_command_url(
    request: Request,
    *,
    worker_id: str,
    session_id: str,
    credential_version: int,
    tenant_id: str,
    workspace_id: str,
    ticket_id: str,
    command_name: WorkerCommandName,
    issued_at: datetime,
) -> tuple[str, datetime]:
    base_url = _resolve_worker_public_base_url(request)
    token, expires_at = _issue_worker_delivery_token(
        request,
        scope="command",
        worker_id=worker_id,
        session_id=session_id,
        credential_version=credential_version,
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        ticket_id=ticket_id,
        command_name=command_name,
        issued_at=issued_at,
    )
    return (
        f"{base_url}/api/v1/worker-runtime/commands/{command_name}?"
        f"{urlencode({'access_token': token})}",
        expires_at,
    )


def build_worker_command_endpoints(
    request: Request,
    *,
    worker_id: str,
    session_id: str,
    credential_version: int,
    tenant_id: str,
    workspace_id: str,
    ticket_id: str,
    issued_at: datetime,
) -> tuple[dict[str, str], datetime]:
    ticket_start_url, expires_at = _build_worker_command_url(
        request,
        worker_id=worker_id,
        session_id=session_id,
        credential_version=credential_version,
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        ticket_id=ticket_id,
        command_name="ticket-start",
        issued_at=issued_at,
    )
    ticket_heartbeat_url, _ = _build_worker_command_url(
        request,
        worker_id=worker_id,
        session_id=session_id,
        credential_version=credential_version,
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        ticket_id=ticket_id,
        command_name="ticket-heartbeat",
        issued_at=issued_at,
    )
    ticket_result_submit_url, _ = _build_worker_command_url(
        request,
        worker_id=worker_id,
        session_id=session_id,
        credential_version=credential_version,
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        ticket_id=ticket_id,
        command_name="ticket-result-submit",
        issued_at=issued_at,
    )
    ticket_artifact_import_upload_url, _ = _build_worker_command_url(
        request,
        worker_id=worker_id,
        session_id=session_id,
        credential_version=credential_version,
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        ticket_id=ticket_id,
        command_name="ticket-artifact-import-upload",
        issued_at=issued_at,
    )
    return {
        "ticket_start_url": ticket_start_url,
        "ticket_heartbeat_url": ticket_heartbeat_url,
        "ticket_result_submit_url": ticket_result_submit_url,
        "ticket_artifact_import_upload_url": ticket_artifact_import_upload_url,
    }, expires_at


def list_worker_assignments(
    repository: ControlPlaneRepository,
    *,
    principal: WorkerPrincipal,
) -> list[dict[str, Any]]:
    current_time = now_local()
    try:
        repository.initialize()
        with repository.connection() as connection:
            tickets = repository.list_ticket_projections_by_statuses(
                connection,
                list(ACTIVE_WORKER_TICKET_STATUSES),
            )
            owned_tickets = [
                ticket
                for ticket in tickets
                if ticket.get("lease_owner") == principal.worker_id
                and ticket["status"] in ACTIVE_WORKER_TICKET_STATUSES
            ]
            scoped_tickets: list[dict[str, Any]] = []
            for ticket in owned_tickets:
                ticket_tenant_id = str(ticket.get("tenant_id") or "")
                ticket_workspace_id = str(ticket.get("workspace_id") or "")
                if (
                    ticket_tenant_id == principal.tenant_id
                    and ticket_workspace_id == principal.workspace_id
                ):
                    scoped_tickets.append(
                        _validate_ticket_scope_and_ownership(
                            repository,
                            ticket=ticket,
                            principal=principal,
                            connection=connection,
                        )
                    )
                    continue

                alternate_binding = repository.get_worker_bootstrap_state(
                    principal.worker_id,
                    tenant_id=ticket_tenant_id,
                    workspace_id=ticket_workspace_id,
                    connection=connection,
                )
                if alternate_binding is not None:
                    continue

                _validate_ticket_scope_and_ownership(
                    repository,
                    ticket=ticket,
                    principal=principal,
                    connection=connection,
                )
            return scoped_tickets
    except WorkerAuthError as exc:
        _log_worker_auth_rejection(
            repository,
            route_family="assignments",
            error=exc,
            occurred_at=current_time,
        )
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


def require_worker_owned_ticket(
    repository: ControlPlaneRepository,
    *,
    ticket_id: str,
    principal: WorkerPrincipal,
) -> dict[str, Any]:
    repository.initialize()
    with repository.connection() as connection:
        ticket = repository.get_current_ticket_projection(ticket_id, connection=connection)
        return _validate_ticket_scope_and_ownership(
            repository,
            ticket=ticket,
            principal=principal,
            connection=connection,
        )


def _worker_ticket_scope(
    repository: ControlPlaneRepository,
    *,
    principal: WorkerPrincipal,
    ticket_id: str,
) -> tuple[set[str], set[str]]:
    repository.initialize()
    with repository.connection() as connection:
        ticket = repository.get_current_ticket_projection(ticket_id, connection=connection)
        validated_ticket = _validate_ticket_scope_and_ownership(
            repository,
            ticket=ticket,
            principal=principal,
            connection=connection,
        )
        created_spec = repository.get_latest_ticket_created_payload(
            connection,
            validated_ticket["ticket_id"],
        ) or {}

    owned_ticket_ids = {str(validated_ticket["ticket_id"])}
    allowed_input_refs = {
        str(artifact_ref)
        for artifact_ref in list(created_spec.get("input_artifact_refs") or [])
    }
    return owned_ticket_ids, allowed_input_refs


def require_worker_access_to_artifact(
    repository: ControlPlaneRepository,
    *,
    artifact_ref: str,
    ticket_id: str,
    principal: WorkerPrincipal,
) -> dict[str, Any] | None:
    owned_ticket_ids, allowed_input_refs = _worker_ticket_scope(
        repository,
        principal=principal,
        ticket_id=ticket_id,
    )
    artifact = repository.get_artifact_by_ref(artifact_ref)

    if artifact_ref in allowed_input_refs:
        return artifact
    if artifact is not None and artifact.get("ticket_id") in owned_ticket_ids:
        return artifact

    raise HTTPException(
        status_code=403,
        detail=f"Worker '{principal.worker_id}' cannot access artifact '{artifact_ref}'.",
    )


def ensure_worker_execution_handoff(
    repository: ControlPlaneRepository,
    *,
    ticket: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    latest_bundle = repository.get_latest_compiled_context_bundle_by_ticket(ticket["ticket_id"])
    latest_manifest = repository.get_latest_compile_manifest_by_ticket(ticket["ticket_id"])
    latest_execution_package = repository.get_latest_compiled_execution_package_by_ticket(ticket["ticket_id"])

    compile_request_id = latest_execution_package["compile_request_id"] if latest_execution_package else None
    if (
        latest_bundle is None
        or latest_manifest is None
        or latest_execution_package is None
        or latest_bundle["compile_request_id"] != compile_request_id
        or latest_manifest["compile_request_id"] != compile_request_id
    ):
        compile_and_persist_execution_artifacts(repository, ticket)
        latest_bundle = repository.get_latest_compiled_context_bundle_by_ticket(ticket["ticket_id"])
        latest_manifest = repository.get_latest_compile_manifest_by_ticket(ticket["ticket_id"])
        latest_execution_package = repository.get_latest_compiled_execution_package_by_ticket(ticket["ticket_id"])

    if latest_bundle is None or latest_manifest is None or latest_execution_package is None:
        raise RuntimeError("Compiled execution handoff could not be materialized for worker delivery.")
    return latest_bundle, latest_manifest, latest_execution_package


def build_worker_execution_package_payload(
    request: Request,
    *,
    latest_execution_package: dict[str, Any],
    principal: WorkerPrincipal,
    ticket_id: str,
    issued_at: datetime,
) -> tuple[dict[str, Any], datetime | None]:
    payload = deepcopy(latest_execution_package["payload"])
    payload.setdefault("meta", {})
    if isinstance(payload["meta"], dict):
        payload["meta"]["tenant_id"] = principal.tenant_id
        payload["meta"]["workspace_id"] = principal.workspace_id
    delivery_expires_at: datetime | None = None
    for block in payload.get("atomic_context_bundle", {}).get("context_blocks", []):
        content_payload = block.get("content_payload") or {}
        artifact_access = content_payload.get("artifact_access")
        artifact_ref = None
        if isinstance(artifact_access, dict):
            artifact_ref = artifact_access.get("artifact_ref")
        if artifact_ref is None:
            artifact_ref = content_payload.get("artifact_ref") or content_payload.get("source_ref")
        if not isinstance(artifact_ref, str) or not artifact_ref:
            continue
        worker_urls, expires_at = build_worker_artifact_urls(
            request,
            worker_id=principal.worker_id,
            session_id=str(principal.session_id or ""),
            credential_version=int(principal.credential_version or 0),
            tenant_id=principal.tenant_id,
            workspace_id=principal.workspace_id,
            ticket_id=ticket_id,
            artifact_ref=artifact_ref,
            issued_at=issued_at,
        )
        if delivery_expires_at is None:
            delivery_expires_at = expires_at
        if isinstance(artifact_access, dict):
            artifact_access.update(worker_urls)
        content_payload.update(worker_urls)
    return payload, delivery_expires_at


def build_worker_artifact_metadata(
    request: Request,
    *,
    principal: WorkerPrincipal,
    ticket_id: str,
    issued_at: datetime,
    artifact: dict[str, Any],
    metadata: dict[str, Any],
) -> tuple[dict[str, Any], datetime]:
    rewritten = dict(metadata)
    worker_urls, expires_at = build_worker_artifact_urls(
        request,
        worker_id=principal.worker_id,
        session_id=str(principal.session_id or ""),
        credential_version=int(principal.credential_version or 0),
        tenant_id=principal.tenant_id,
        workspace_id=principal.workspace_id,
        ticket_id=ticket_id,
        artifact_ref=str(artifact["artifact_ref"]),
        issued_at=issued_at,
    )
    rewritten.update(worker_urls)
    return rewritten, expires_at


def build_output_schema_body_for_execution_package(
    execution_package_payload: dict[str, Any],
) -> dict[str, Any]:
    execution = execution_package_payload.get("execution") or {}
    return get_output_schema_body(
        str(execution.get("output_schema_ref") or ""),
        int(execution.get("output_schema_version") or 0),
    )
