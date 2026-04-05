from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Literal, cast

from fastapi import Header, HTTPException, Request

from app.config import get_settings
from app.core.time import now_local
from app.core.worker_admin_tokens import WorkerAdminTokenValidationError, validate_worker_admin_token

WorkerAdminOperatorRole = Literal["platform_admin", "scope_admin", "scope_viewer"]

_VALID_OPERATOR_ROLES = {"platform_admin", "scope_admin", "scope_viewer"}


@dataclass(frozen=True)
class WorkerAdminOperatorContext:
    operator_id: str
    role: WorkerAdminOperatorRole
    token_id: str | None = None
    tenant_id: str | None = None
    workspace_id: str | None = None
    trusted_proxy_id: str | None = None
    source_ip: str | None = None
    auth_source: str = "signed_token"
    auth_rejection_logger: Callable[..., None] | None = None

    @property
    def is_platform_admin(self) -> bool:
        return self.role == "platform_admin"

    @property
    def can_write(self) -> bool:
        return self.role in {"platform_admin", "scope_admin"}

    def log_auth_rejection(
        self,
        reason_code: str,
        *,
        tenant_id: str | None = None,
        workspace_id: str | None = None,
    ) -> None:
        if self.auth_rejection_logger is None:
            return
        self.auth_rejection_logger(
            reason_code=reason_code,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
        )


def _normalize_required_header(value: str | None, *, header_name: str) -> str:
    normalized = (value or "").strip()
    if not normalized:
        raise HTTPException(status_code=401, detail=f"Missing required worker-admin header '{header_name}'.")
    return normalized


def _normalize_optional_header(value: str | None) -> str | None:
    normalized = (value or "").strip()
    return normalized or None


def _resolve_worker_admin_signing_secret() -> str:
    signing_secret = get_settings().worker_admin_signing_secret
    if not signing_secret:
        raise HTTPException(
            status_code=503,
            detail="Worker-admin trusted entry is not configured.",
        )
    return signing_secret


def _resolve_request_source_ip(request: Request) -> str | None:
    client = request.client
    if client is None:
        return None
    normalized = (client.host or "").strip()
    return normalized or None


def _append_worker_admin_auth_rejection_log(
    request: Request,
    *,
    reason_code: str,
    operator_id: str | None,
    operator_role: str | None,
    token_id: str | None,
    tenant_id: str | None,
    workspace_id: str | None,
    trusted_proxy_id: str | None = None,
    source_ip: str | None = None,
) -> None:
    repository = getattr(request.app.state, "repository", None)
    if repository is None:
        return
    with repository.transaction() as connection:
        repository.append_worker_admin_auth_rejection_log(
            connection,
            occurred_at=now_local(),
            route_path=request.url.path,
            reason_code=reason_code,
            operator_id=operator_id,
            operator_role=operator_role,
            token_id=token_id,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            trusted_proxy_id=trusted_proxy_id,
            source_ip=source_ip,
        )


def _assert_worker_admin_header_match(
    *,
    request: Request,
    header_name: str,
    asserted_value: str | None,
    expected_value: str | None,
    reason_code: str,
    operator_id: str | None,
    operator_role: str | None,
    token_id: str | None,
    tenant_id: str | None,
    workspace_id: str | None,
    trusted_proxy_id: str | None = None,
    source_ip: str | None = None,
) -> None:
    normalized = _normalize_optional_header(asserted_value)
    if normalized is None:
        return
    if normalized != expected_value:
        _append_worker_admin_auth_rejection_log(
            request,
            reason_code=reason_code,
            operator_id=operator_id,
            operator_role=operator_role,
            token_id=token_id,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            trusted_proxy_id=trusted_proxy_id,
            source_ip=source_ip,
        )
        raise HTTPException(
            status_code=400,
            detail=f"{header_name} must match the signed worker-admin operator token when provided.",
        )


def _require_worker_admin_trusted_proxy(
    request: Request,
    *,
    x_boardroom_trusted_proxy_id: str | None,
) -> tuple[str | None, str | None]:
    trusted_proxy_id = _normalize_optional_header(x_boardroom_trusted_proxy_id)
    source_ip = _resolve_request_source_ip(request)
    trusted_proxy_ids = get_settings().worker_admin_trusted_proxy_ids
    if not trusted_proxy_ids:
        return trusted_proxy_id, source_ip
    if trusted_proxy_id is None:
        _append_worker_admin_auth_rejection_log(
            request,
            reason_code="missing_trusted_proxy_assertion",
            operator_id=None,
            operator_role=None,
            token_id=None,
            tenant_id=None,
            workspace_id=None,
            trusted_proxy_id=None,
            source_ip=source_ip,
        )
        raise HTTPException(
            status_code=403,
            detail="Worker-admin trusted proxy assertion is required.",
        )
    if trusted_proxy_id not in trusted_proxy_ids:
        _append_worker_admin_auth_rejection_log(
            request,
            reason_code="untrusted_proxy_assertion",
            operator_id=None,
            operator_role=None,
            token_id=None,
            tenant_id=None,
            workspace_id=None,
            trusted_proxy_id=trusted_proxy_id,
            source_ip=source_ip,
        )
        raise HTTPException(
            status_code=403,
            detail="Worker-admin trusted proxy assertion is not allowed.",
        )
    return trusted_proxy_id, source_ip


def get_worker_admin_operator_context(
    request: Request,
    x_boardroom_trusted_proxy_id: str | None = Header(default=None, alias="X-Boardroom-Trusted-Proxy-Id"),
    x_boardroom_operator_token: str | None = Header(default=None, alias="X-Boardroom-Operator-Token"),
    x_boardroom_operator_id: str | None = Header(default=None, alias="X-Boardroom-Operator-Id"),
    x_boardroom_operator_role: str | None = Header(default=None, alias="X-Boardroom-Operator-Role"),
    x_boardroom_operator_tenant_id: str | None = Header(
        default=None,
        alias="X-Boardroom-Operator-Tenant-Id",
    ),
    x_boardroom_operator_workspace_id: str | None = Header(
        default=None,
        alias="X-Boardroom-Operator-Workspace-Id",
    ),
) -> WorkerAdminOperatorContext:
    trusted_proxy_id, source_ip = _require_worker_admin_trusted_proxy(
        request,
        x_boardroom_trusted_proxy_id=x_boardroom_trusted_proxy_id,
    )
    if _normalize_optional_header(x_boardroom_operator_token) is None:
        _append_worker_admin_auth_rejection_log(
            request,
            reason_code="missing_operator_token",
            operator_id=None,
            operator_role=None,
            token_id=None,
            tenant_id=None,
            workspace_id=None,
            trusted_proxy_id=trusted_proxy_id,
            source_ip=source_ip,
        )
    operator_token = _normalize_required_header(
        x_boardroom_operator_token,
        header_name="X-Boardroom-Operator-Token",
    )
    try:
        claims = validate_worker_admin_token(
            operator_token,
            signing_secret=_resolve_worker_admin_signing_secret(),
            at=now_local(),
            repository=request.app.state.repository,
            require_persisted_issue=True,
        )
    except WorkerAdminTokenValidationError as exc:
        _append_worker_admin_auth_rejection_log(
            request,
            reason_code=exc.reason_code,
            operator_id=exc.operator_id,
            operator_role=exc.role,
            token_id=exc.token_id,
            tenant_id=exc.tenant_id,
            workspace_id=exc.workspace_id,
            trusted_proxy_id=trusted_proxy_id,
            source_ip=source_ip,
        )
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    asserted_tenant_id = _normalize_optional_header(x_boardroom_operator_tenant_id)
    asserted_workspace_id = _normalize_optional_header(x_boardroom_operator_workspace_id)
    if (asserted_tenant_id is None) != (asserted_workspace_id is None):
        _append_worker_admin_auth_rejection_log(
            request,
            reason_code="invalid_scope_headers",
            operator_id=claims.operator_id,
            operator_role=claims.role,
            token_id=claims.token_id,
            tenant_id=claims.tenant_id,
            workspace_id=claims.workspace_id,
            trusted_proxy_id=trusted_proxy_id,
            source_ip=source_ip,
        )
        raise HTTPException(
            status_code=400,
            detail="Worker-admin operator scope headers must provide both tenant and workspace together.",
        )

    _assert_worker_admin_header_match(
        request=request,
        header_name="X-Boardroom-Operator-Id",
        asserted_value=x_boardroom_operator_id,
        expected_value=claims.operator_id,
        reason_code="assertion_header_mismatch",
        operator_id=claims.operator_id,
        operator_role=claims.role,
        token_id=claims.token_id,
        tenant_id=claims.tenant_id,
        workspace_id=claims.workspace_id,
        trusted_proxy_id=trusted_proxy_id,
        source_ip=source_ip,
    )
    _assert_worker_admin_header_match(
        request=request,
        header_name="X-Boardroom-Operator-Role",
        asserted_value=x_boardroom_operator_role,
        expected_value=claims.role,
        reason_code="assertion_header_mismatch",
        operator_id=claims.operator_id,
        operator_role=claims.role,
        token_id=claims.token_id,
        tenant_id=claims.tenant_id,
        workspace_id=claims.workspace_id,
        trusted_proxy_id=trusted_proxy_id,
        source_ip=source_ip,
    )
    if asserted_tenant_id is not None or asserted_workspace_id is not None:
        _assert_worker_admin_header_match(
            request=request,
            header_name="X-Boardroom-Operator-Tenant-Id",
            asserted_value=asserted_tenant_id,
            expected_value=claims.tenant_id,
            reason_code="assertion_header_mismatch",
            operator_id=claims.operator_id,
            operator_role=claims.role,
            token_id=claims.token_id,
            tenant_id=claims.tenant_id,
            workspace_id=claims.workspace_id,
            trusted_proxy_id=trusted_proxy_id,
            source_ip=source_ip,
        )
        _assert_worker_admin_header_match(
            request=request,
            header_name="X-Boardroom-Operator-Workspace-Id",
            asserted_value=asserted_workspace_id,
            expected_value=claims.workspace_id,
            reason_code="assertion_header_mismatch",
            operator_id=claims.operator_id,
            operator_role=claims.role,
            token_id=claims.token_id,
            tenant_id=claims.tenant_id,
            workspace_id=claims.workspace_id,
            trusted_proxy_id=trusted_proxy_id,
            source_ip=source_ip,
        )

    return WorkerAdminOperatorContext(
        operator_id=claims.operator_id,
        role=cast(WorkerAdminOperatorRole, claims.role),
        token_id=claims.token_id,
        tenant_id=claims.tenant_id,
        workspace_id=claims.workspace_id,
        trusted_proxy_id=trusted_proxy_id,
        source_ip=source_ip,
        auth_source="signed_token",
        auth_rejection_logger=lambda **kwargs: _append_worker_admin_auth_rejection_log(
            request,
            reason_code=str(kwargs["reason_code"]),
            operator_id=claims.operator_id,
            operator_role=claims.role,
            token_id=claims.token_id,
            tenant_id=kwargs.get("tenant_id", claims.tenant_id),
            workspace_id=kwargs.get("workspace_id", claims.workspace_id),
            trusted_proxy_id=trusted_proxy_id,
            source_ip=source_ip,
        ),
    )


def require_worker_admin_read_scope(
    operator: WorkerAdminOperatorContext,
    *,
    tenant_id: str | None,
    workspace_id: str | None,
) -> None:
    if operator.is_platform_admin:
        return
    if tenant_id is None or workspace_id is None:
        operator.log_auth_rejection("missing_scope_for_scoped_read")
        raise HTTPException(
            status_code=403,
            detail="Scoped worker-admin operators must query an explicit tenant/workspace scope.",
        )
    if tenant_id != operator.tenant_id or workspace_id != operator.workspace_id:
        operator.log_auth_rejection(
            "scope_read_forbidden",
            tenant_id=tenant_id,
            workspace_id=workspace_id,
        )
        raise HTTPException(
            status_code=403,
            detail="Worker-admin operator cannot read outside the assigned tenant/workspace scope.",
        )


def require_worker_admin_write_scope(
    operator: WorkerAdminOperatorContext,
    *,
    tenant_id: str | None,
    workspace_id: str | None,
    explicit_scope_required_for_scoped: bool = False,
) -> None:
    if not operator.can_write:
        operator.log_auth_rejection("write_not_allowed", tenant_id=tenant_id, workspace_id=workspace_id)
        raise HTTPException(status_code=403, detail="Worker-admin operator does not have write access.")
    if operator.is_platform_admin:
        return
    if explicit_scope_required_for_scoped and (tenant_id is None or workspace_id is None):
        operator.log_auth_rejection("missing_scope_for_scoped_write")
        raise HTTPException(
            status_code=403,
            detail="Scoped worker-admin operators must write against an explicit tenant/workspace scope.",
        )
    if tenant_id is not None and workspace_id is not None:
        if tenant_id != operator.tenant_id or workspace_id != operator.workspace_id:
            operator.log_auth_rejection(
                "scope_write_forbidden",
                tenant_id=tenant_id,
                workspace_id=workspace_id,
            )
            raise HTTPException(
                status_code=403,
                detail="Worker-admin operator cannot write outside the assigned tenant/workspace scope.",
            )


def require_worker_admin_write_target_scope(
    operator: WorkerAdminOperatorContext,
    *,
    tenant_id: str,
    workspace_id: str,
) -> None:
    require_worker_admin_write_scope(
        operator,
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        explicit_scope_required_for_scoped=False,
    )


def resolve_worker_admin_actor(
    operator: WorkerAdminOperatorContext,
    *,
    asserted_actor: str | None,
    field_name: str,
) -> str:
    asserted = _normalize_optional_header(asserted_actor)
    if asserted is not None and asserted != operator.operator_id:
        operator.log_auth_rejection("actor_assertion_mismatch")
        raise HTTPException(
            status_code=400,
            detail=f"{field_name} must match X-Boardroom-Operator-Id when provided.",
        )
    return operator.operator_id
