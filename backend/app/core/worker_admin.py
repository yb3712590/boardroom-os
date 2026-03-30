from __future__ import annotations

from argparse import Namespace
from datetime import datetime, timedelta

from app.config import get_settings
from app.core.constants import DEFAULT_TENANT_ID, DEFAULT_WORKSPACE_ID
from app.core.time import now_local
from app.core.worker_bootstrap_tokens import issue_worker_bootstrap_token
from app.db.repository import ControlPlaneRepository

ISSUED_VIA_WORKER_AUTH_CLI = "worker_auth_cli"
WORKER_ADMIN_API_VIA = "worker_admin_api"
WORKER_BOOTSTRAP_REVOKE_VIA = "worker_bootstrap_revoke"
WORKER_BOOTSTRAP_ROTATE_VIA = "worker_bootstrap_rotate"
DEFAULT_SESSION_REVOKE_REASON = "Manually revoked worker session."
DEFAULT_DELIVERY_GRANT_REVOKE_REASON = "Manually revoked worker delivery grant."


def _resolve_bootstrap_signing_secret() -> str:
    settings = get_settings()
    signing_secret = settings.worker_bootstrap_signing_secret or settings.worker_shared_secret
    if not signing_secret:
        raise RuntimeError("Worker bootstrap signing secret is not configured.")
    return signing_secret


def _resolve_bootstrap_default_ttl_sec() -> int:
    return get_settings().worker_bootstrap_default_ttl_sec


def _resolve_bootstrap_max_ttl_sec() -> int:
    return get_settings().worker_bootstrap_max_ttl_sec


def _validate_bootstrap_tenant_allowed(tenant_id: str) -> None:
    allowed_tenant_ids = get_settings().worker_bootstrap_allowed_tenant_ids
    if allowed_tenant_ids and tenant_id not in allowed_tenant_ids:
        raise RuntimeError(
            f"Tenant '{tenant_id}' is not allowed by BOARDROOM_OS_WORKER_BOOTSTRAP_ALLOWED_TENANT_IDS."
        )


def _resolve_requested_bootstrap_ttl_sec(ttl_sec: int | None) -> int:
    resolved = _resolve_bootstrap_default_ttl_sec() if ttl_sec is None else int(ttl_sec)
    max_ttl_sec = _resolve_bootstrap_max_ttl_sec()
    if resolved <= 0:
        raise RuntimeError("Bootstrap TTL must be greater than zero.")
    if resolved > max_ttl_sec:
        raise RuntimeError(
            f"Requested bootstrap TTL exceeds configured max TTL ({max_ttl_sec} seconds)."
        )
    return resolved


def _require_active_worker(
    repository: ControlPlaneRepository,
    worker_id: str,
    *,
    connection,
) -> None:
    employee = repository.get_employee_projection(worker_id, connection=connection)
    if employee is None:
        raise RuntimeError(f"Worker '{worker_id}' is not registered.")
    if str(employee.get("state") or "") != "ACTIVE":
        raise RuntimeError(f"Worker '{worker_id}' is not active.")


def resolve_scope_args(
    tenant_id: str | None,
    workspace_id: str | None,
) -> tuple[str | None, str | None]:
    if (tenant_id is None) != (workspace_id is None):
        raise RuntimeError("Please provide both tenant_id and workspace_id together.")
    return tenant_id, workspace_id


def _select_worker_binding(
    repository: ControlPlaneRepository,
    connection,
    *,
    worker_id: str,
    tenant_id: str | None,
    workspace_id: str | None,
    allow_create: bool,
) -> tuple[str, str, dict[str, object] | None]:
    bindings = repository.list_worker_bootstrap_states(connection, worker_id=worker_id)
    if tenant_id is not None and workspace_id is not None:
        selected = repository.get_worker_bootstrap_state(
            worker_id,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            connection=connection,
        )
        if selected is None and not allow_create:
            raise RuntimeError(
                "Worker bootstrap binding was not found for the requested tenant/workspace scope."
            )
        return tenant_id, workspace_id, selected

    if not bindings:
        if allow_create:
            return DEFAULT_TENANT_ID, DEFAULT_WORKSPACE_ID, None
        raise RuntimeError("Worker does not have any bootstrap bindings yet.")
    if len(bindings) > 1:
        raise RuntimeError(
            "Worker has multiple bootstrap bindings. Please explicitly provide both tenant_id and workspace_id."
        )

    selected = bindings[0]
    return str(selected["tenant_id"]), str(selected["workspace_id"]), selected


def create_binding(
    repository: ControlPlaneRepository,
    *,
    worker_id: str,
    tenant_id: str,
    workspace_id: str,
) -> dict[str, object]:
    created_at = now_local()
    with repository.transaction() as connection:
        _require_active_worker(repository, worker_id, connection=connection)
        return repository.ensure_worker_bootstrap_state(
            connection,
            worker_id=worker_id,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            at=created_at,
        )


def list_binding_admin_views(
    repository: ControlPlaneRepository,
    *,
    worker_id: str | None = None,
    tenant_id: str | None = None,
    workspace_id: str | None = None,
) -> list[dict[str, object]]:
    tenant_id, workspace_id = resolve_scope_args(tenant_id, workspace_id)
    listed_at = now_local()
    with repository.connection() as connection:
        return repository.list_worker_binding_admin_views(
            connection,
            worker_id=worker_id,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            at=listed_at,
        )


def list_bootstrap_issues(
    repository: ControlPlaneRepository,
    *,
    worker_id: str | None = None,
    tenant_id: str | None = None,
    workspace_id: str | None = None,
    active_only: bool = False,
) -> list[dict[str, object]]:
    tenant_id, workspace_id = resolve_scope_args(tenant_id, workspace_id)
    listed_at = now_local()
    with repository.connection() as connection:
        return repository.list_worker_bootstrap_issues(
            connection,
            worker_id=worker_id,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            active_only=active_only,
            at=listed_at,
        )


def issue_bootstrap(
    repository: ControlPlaneRepository,
    *,
    worker_id: str,
    ttl_sec: int | None = None,
    tenant_id: str | None = None,
    workspace_id: str | None = None,
    issued_by: str | None = None,
    reason: str | None = None,
    issued_via: str = ISSUED_VIA_WORKER_AUTH_CLI,
) -> dict[str, object]:
    tenant_id, workspace_id = resolve_scope_args(tenant_id, workspace_id)
    issued_at = now_local()
    resolved_ttl_sec = _resolve_requested_bootstrap_ttl_sec(ttl_sec)
    planned_expires_at = issued_at + timedelta(seconds=resolved_ttl_sec)
    with repository.transaction() as connection:
        _require_active_worker(repository, worker_id, connection=connection)
        tenant_id, workspace_id, _ = _select_worker_binding(
            repository,
            connection,
            worker_id=worker_id,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            allow_create=True,
        )
        _validate_bootstrap_tenant_allowed(tenant_id)
        state = repository.ensure_worker_bootstrap_state(
            connection,
            worker_id=worker_id,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            at=issued_at,
        )
        issue = repository.create_worker_bootstrap_issue(
            connection,
            worker_id=worker_id,
            tenant_id=str(state["tenant_id"]),
            workspace_id=str(state["workspace_id"]),
            credential_version=int(state["credential_version"]),
            issued_at=issued_at,
            expires_at=planned_expires_at,
            issued_via=issued_via,
            issued_by=issued_by,
            reason=reason,
        )
    token, expires_at = issue_worker_bootstrap_token(
        signing_secret=_resolve_bootstrap_signing_secret(),
        worker_id=worker_id,
        credential_version=int(state["credential_version"]),
        tenant_id=str(state["tenant_id"]),
        workspace_id=str(state["workspace_id"]),
        issue_id=str(issue["issue_id"]),
        issued_at=issued_at,
        ttl_sec=resolved_ttl_sec,
    )
    return {
        "issue_id": str(issue["issue_id"]),
        "worker_id": worker_id,
        "credential_version": int(state["credential_version"]),
        "tenant_id": str(state["tenant_id"]),
        "workspace_id": str(state["workspace_id"]),
        "issued_via": issued_via,
        "issued_by": issued_by,
        "reason": reason,
        "bootstrap_token": token,
        "issued_at": issued_at,
        "expires_at": expires_at,
    }


def revoke_bootstrap(
    repository: ControlPlaneRepository,
    *,
    worker_id: str,
    tenant_id: str | None = None,
    workspace_id: str | None = None,
) -> dict[str, object]:
    tenant_id, workspace_id = resolve_scope_args(tenant_id, workspace_id)
    revoked_at = now_local()
    with repository.transaction() as connection:
        _require_active_worker(repository, worker_id, connection=connection)
        tenant_id, workspace_id, _ = _select_worker_binding(
            repository,
            connection,
            worker_id=worker_id,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            allow_create=False,
        )
        state = repository.revoke_worker_bootstrap_state(
            connection,
            worker_id=worker_id,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            revoked_at=revoked_at,
        )
    return {
        "worker_id": worker_id,
        "credential_version": int(state["credential_version"]),
        "tenant_id": str(state["tenant_id"]),
        "workspace_id": str(state["workspace_id"]),
        "revoked_before": revoked_at,
    }


def revoke_session(
    repository: ControlPlaneRepository,
    *,
    session_id: str | None = None,
    worker_id: str | None = None,
    tenant_id: str | None = None,
    workspace_id: str | None = None,
    revoked_by: str | None = None,
    reason: str | None = None,
    revoked_via: str = ISSUED_VIA_WORKER_AUTH_CLI,
) -> dict[str, object]:
    tenant_id, workspace_id = resolve_scope_args(tenant_id, workspace_id)
    if session_id is not None:
        if worker_id is not None or tenant_id is not None or workspace_id is not None:
            raise RuntimeError(
                "Please provide either session_id or worker_id with tenant_id/workspace_id, not both."
            )
    else:
        if worker_id is None or tenant_id is None or workspace_id is None:
            raise RuntimeError(
                "Please provide either session_id or worker_id with tenant_id and workspace_id."
            )

    revoked_at = now_local()
    resolved_reason = reason or DEFAULT_SESSION_REVOKE_REASON
    with repository.transaction() as connection:
        session: dict[str, object] | None = None
        if session_id is not None:
            session = repository.get_worker_session(session_id, connection=connection)
            if session is None:
                raise RuntimeError("Worker session was not found.")
            worker_id = str(session["worker_id"])
            tenant_id = str(session["tenant_id"])
            workspace_id = str(session["workspace_id"])

        revoked_delivery_grant_count = len(
            repository.list_worker_delivery_grants(
                connection,
                session_id=session_id,
                worker_id=worker_id,
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                active_only=True,
            )
        )
        revoked_count = repository.revoke_worker_sessions(
            connection,
            session_id=session_id,
            worker_id=worker_id,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            revoked_at=revoked_at,
            revoke_reason=resolved_reason,
            revoked_via=revoked_via,
            revoked_by=revoked_by,
        )

    return {
        "session_id": session_id,
        "worker_id": worker_id,
        "tenant_id": tenant_id,
        "workspace_id": workspace_id,
        "revoked_count": revoked_count,
        "revoked_delivery_grant_count": revoked_delivery_grant_count,
        "revoked_at": revoked_at,
        "revoked_via": revoked_via,
        "revoked_by": revoked_by,
        "revoke_reason": resolved_reason,
    }


def revoke_delivery_grant(
    repository: ControlPlaneRepository,
    *,
    grant_id: str,
    revoked_by: str | None = None,
    reason: str | None = None,
    revoked_via: str = ISSUED_VIA_WORKER_AUTH_CLI,
) -> dict[str, object]:
    revoked_at = now_local()
    resolved_reason = reason or DEFAULT_DELIVERY_GRANT_REVOKE_REASON
    with repository.transaction() as connection:
        grant = repository.get_worker_delivery_grant(grant_id, connection=connection)
        if grant is None:
            raise RuntimeError("Worker delivery grant was not found.")
        revoked_count = repository.revoke_worker_delivery_grants(
            connection,
            grant_id=grant_id,
            revoked_at=revoked_at,
            revoke_reason=resolved_reason,
            revoked_via=revoked_via,
            revoked_by=revoked_by,
        )
    return {
        "grant_id": grant_id,
        "session_id": str(grant["session_id"]),
        "worker_id": str(grant["worker_id"]),
        "tenant_id": str(grant["tenant_id"]),
        "workspace_id": str(grant["workspace_id"]),
        "revoked_count": revoked_count,
        "revoked_at": revoked_at,
        "revoked_via": revoked_via,
        "revoked_by": revoked_by,
        "revoke_reason": resolved_reason,
    }


def cleanup_bindings(
    repository: ControlPlaneRepository,
    *,
    worker_id: str,
    tenant_id: str | None = None,
    workspace_id: str | None = None,
    dry_run: bool = False,
) -> dict[str, object]:
    tenant_id, workspace_id = resolve_scope_args(tenant_id, workspace_id)
    cleaned_at = now_local()
    with repository.transaction() as connection:
        bindings = repository.list_worker_binding_admin_views(
            connection,
            worker_id=worker_id,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            at=cleaned_at,
        )
        deleted_count = 0
        if not dry_run:
            for binding in bindings:
                if not bool(binding.get("cleanup_eligible")):
                    continue
                deleted_count += repository.delete_worker_bootstrap_state(
                    connection,
                    worker_id=str(binding["worker_id"]),
                    tenant_id=str(binding["tenant_id"]),
                    workspace_id=str(binding["workspace_id"]),
                )
    return {
        "bindings": bindings,
        "count": len(bindings),
        "deleted_count": deleted_count,
        "dry_run": dry_run,
        "cleaned_at": cleaned_at,
    }


def namespace_scope(args: Namespace) -> tuple[str | None, str | None]:
    return resolve_scope_args(getattr(args, "tenant_id", None), getattr(args, "workspace_id", None))
