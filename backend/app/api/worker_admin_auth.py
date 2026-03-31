from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, cast

from fastapi import Header, HTTPException

from app.config import get_settings
from app.core.time import now_local
from app.core.worker_admin_tokens import validate_worker_admin_token

WorkerAdminOperatorRole = Literal["platform_admin", "scope_admin", "scope_viewer"]

_VALID_OPERATOR_ROLES = {"platform_admin", "scope_admin", "scope_viewer"}


@dataclass(frozen=True)
class WorkerAdminOperatorContext:
    operator_id: str
    role: WorkerAdminOperatorRole
    tenant_id: str | None = None
    workspace_id: str | None = None
    auth_source: str = "signed_token"

    @property
    def is_platform_admin(self) -> bool:
        return self.role == "platform_admin"

    @property
    def can_write(self) -> bool:
        return self.role in {"platform_admin", "scope_admin"}


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


def _assert_worker_admin_header_match(
    *,
    header_name: str,
    asserted_value: str | None,
    expected_value: str | None,
) -> None:
    normalized = _normalize_optional_header(asserted_value)
    if normalized is None:
        return
    if normalized != expected_value:
        raise HTTPException(
            status_code=400,
            detail=f"{header_name} must match the signed worker-admin operator token when provided.",
        )


def get_worker_admin_operator_context(
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
    operator_token = _normalize_required_header(
        x_boardroom_operator_token,
        header_name="X-Boardroom-Operator-Token",
    )
    claims = validate_worker_admin_token(
        operator_token,
        signing_secret=_resolve_worker_admin_signing_secret(),
        at=now_local(),
    )

    asserted_tenant_id = _normalize_optional_header(x_boardroom_operator_tenant_id)
    asserted_workspace_id = _normalize_optional_header(x_boardroom_operator_workspace_id)
    if (asserted_tenant_id is None) != (asserted_workspace_id is None):
        raise HTTPException(
            status_code=400,
            detail="Worker-admin operator scope headers must provide both tenant and workspace together.",
        )

    _assert_worker_admin_header_match(
        header_name="X-Boardroom-Operator-Id",
        asserted_value=x_boardroom_operator_id,
        expected_value=claims.operator_id,
    )
    _assert_worker_admin_header_match(
        header_name="X-Boardroom-Operator-Role",
        asserted_value=x_boardroom_operator_role,
        expected_value=claims.role,
    )
    if asserted_tenant_id is not None or asserted_workspace_id is not None:
        _assert_worker_admin_header_match(
            header_name="X-Boardroom-Operator-Tenant-Id",
            asserted_value=asserted_tenant_id,
            expected_value=claims.tenant_id,
        )
        _assert_worker_admin_header_match(
            header_name="X-Boardroom-Operator-Workspace-Id",
            asserted_value=asserted_workspace_id,
            expected_value=claims.workspace_id,
        )

    return WorkerAdminOperatorContext(
        operator_id=claims.operator_id,
        role=cast(WorkerAdminOperatorRole, claims.role),
        tenant_id=claims.tenant_id,
        workspace_id=claims.workspace_id,
        auth_source="signed_token",
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
        raise HTTPException(
            status_code=403,
            detail="Scoped worker-admin operators must query an explicit tenant/workspace scope.",
        )
    if tenant_id != operator.tenant_id or workspace_id != operator.workspace_id:
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
        raise HTTPException(status_code=403, detail="Worker-admin operator does not have write access.")
    if operator.is_platform_admin:
        return
    if explicit_scope_required_for_scoped and (tenant_id is None or workspace_id is None):
        raise HTTPException(
            status_code=403,
            detail="Scoped worker-admin operators must write against an explicit tenant/workspace scope.",
        )
    if tenant_id is not None and workspace_id is not None:
        if tenant_id != operator.tenant_id or workspace_id != operator.workspace_id:
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
        raise HTTPException(
            status_code=400,
            detail=f"{field_name} must match X-Boardroom-Operator-Id when provided.",
        )
    return operator.operator_id
