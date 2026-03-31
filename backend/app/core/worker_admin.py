from __future__ import annotations

from argparse import Namespace
from collections import defaultdict
from datetime import datetime, timedelta

from app.config import get_settings
from app.core.constants import DEFAULT_TENANT_ID, DEFAULT_WORKSPACE_ID
from app.core.time import now_local
from app.core.worker_bootstrap_tokens import issue_worker_bootstrap_token
from app.db.repository import ControlPlaneRepository

ISSUED_VIA_WORKER_AUTH_CLI = "worker_auth_cli"
ISSUED_VIA_WORKER_ADMIN_AUTH_CLI = "worker_admin_auth_cli"
WORKER_ADMIN_API_VIA = "worker_admin_api"
WORKER_ADMIN_SCOPE_CONTAINMENT_VIA = "worker_admin_scope_containment"
WORKER_BOOTSTRAP_REVOKE_VIA = "worker_bootstrap_revoke"
WORKER_BOOTSTRAP_ROTATE_VIA = "worker_bootstrap_rotate"
DEFAULT_SESSION_REVOKE_REASON = "Manually revoked worker session."
DEFAULT_DELIVERY_GRANT_REVOKE_REASON = "Manually revoked worker delivery grant."
DEFAULT_OPERATOR_TOKEN_REVOKE_REASON = "Manually revoked worker-admin operator token."


class WorkerAdminConflictError(RuntimeError):
    """Raised when a worker-admin write request conflicts with current runtime state."""


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


def _is_worker_session_active(session: dict[str, object], *, at: datetime) -> bool:
    expires_at = session.get("expires_at")
    return bool(session.get("revoked_at") is None and expires_at is not None and expires_at > at)


def _is_worker_delivery_grant_active(grant: dict[str, object], *, at: datetime) -> bool:
    expires_at = grant.get("expires_at")
    return bool(grant.get("revoked_at") is None and expires_at is not None and expires_at > at)


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


def list_sessions(
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
        sessions = repository.list_worker_sessions(
            connection,
            worker_id=worker_id,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            active_only=False,
        )
    items = [
        {
            **session,
            "is_active": _is_worker_session_active(session, at=listed_at),
        }
        for session in sorted(
            sessions,
            key=lambda item: (item["issued_at"], str(item["session_id"])),
            reverse=True,
        )
    ]
    if active_only:
        items = [item for item in items if bool(item["is_active"])]
    return items


def list_delivery_grants(
    repository: ControlPlaneRepository,
    *,
    worker_id: str | None = None,
    session_id: str | None = None,
    ticket_id: str | None = None,
    tenant_id: str | None = None,
    workspace_id: str | None = None,
    active_only: bool = False,
) -> list[dict[str, object]]:
    tenant_id, workspace_id = resolve_scope_args(tenant_id, workspace_id)
    listed_at = now_local()
    with repository.connection() as connection:
        grants = repository.list_worker_delivery_grants(
            connection,
            worker_id=worker_id,
            session_id=session_id,
            ticket_id=ticket_id,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            active_only=False,
        )
    items = [
        {
            **grant,
            "is_active": _is_worker_delivery_grant_active(grant, at=listed_at),
        }
        for grant in sorted(
            grants,
            key=lambda item: (item["issued_at"], str(item["grant_id"])),
            reverse=True,
        )
    ]
    if active_only:
        items = [item for item in items if bool(item["is_active"])]
    return items


def list_auth_rejections(
    repository: ControlPlaneRepository,
    *,
    worker_id: str | None = None,
    tenant_id: str | None = None,
    workspace_id: str | None = None,
    route_family: str | None = None,
) -> list[dict[str, object]]:
    tenant_id, workspace_id = resolve_scope_args(tenant_id, workspace_id)
    with repository.connection() as connection:
        rejections = repository.list_worker_auth_rejection_logs(
            connection,
            worker_id=worker_id,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            route_family=route_family,
        )
    return [
        {
            "occurred_at": rejection["occurred_at"],
            "route_family": rejection["route_family"],
            "reason_code": rejection["reason_code"],
            "worker_id": rejection.get("worker_id"),
            "session_id": rejection.get("session_id"),
            "grant_id": rejection.get("grant_id"),
            "ticket_id": rejection.get("ticket_id"),
            "tenant_id": rejection.get("tenant_id"),
            "workspace_id": rejection.get("workspace_id"),
        }
        for rejection in sorted(
            rejections,
            key=lambda item: (item["occurred_at"], str(item.get("rejection_id") or "")),
            reverse=True,
        )
    ]


def list_operator_tokens(
    repository: ControlPlaneRepository,
    *,
    operator_id: str | None = None,
    role: str | None = None,
    tenant_id: str | None = None,
    workspace_id: str | None = None,
    active_only: bool = False,
) -> list[dict[str, object]]:
    tenant_id, workspace_id = resolve_scope_args(tenant_id, workspace_id)
    listed_at = now_local()
    with repository.connection() as connection:
        token_issues = repository.list_worker_admin_token_issues(
            connection,
            operator_id=operator_id,
            role=role,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            active_only=False,
        )
    items = [
        {
            **token_issue,
            "is_active": bool(
                token_issue.get("revoked_at") is None
                and token_issue.get("expires_at") is not None
                and token_issue["expires_at"] > listed_at
            ),
        }
        for token_issue in token_issues
    ]
    if active_only:
        items = [item for item in items if bool(item["is_active"])]
    return items


def revoke_operator_token(
    repository: ControlPlaneRepository,
    *,
    token_id: str,
    revoked_by: str,
    reason: str | None = None,
) -> dict[str, object]:
    revoked_at = now_local()
    with repository.transaction() as connection:
        revoked = repository.revoke_worker_admin_token_issue(
            connection,
            token_id=token_id,
            revoked_at=revoked_at,
            revoked_by=revoked_by,
            revoke_reason=reason or DEFAULT_OPERATOR_TOKEN_REVOKE_REASON,
        )
    return revoked


def build_scope_summary(
    repository: ControlPlaneRepository,
    *,
    tenant_id: str,
    workspace_id: str,
    worker_id: str | None = None,
) -> dict[str, object]:
    resolve_scope_args(tenant_id, workspace_id)
    listed_at = now_local()
    bindings = list_binding_admin_views(
        repository,
        worker_id=worker_id,
        tenant_id=tenant_id,
        workspace_id=workspace_id,
    )
    bootstrap_issues = list_bootstrap_issues(
        repository,
        worker_id=worker_id,
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        active_only=True,
    )
    sessions = list_sessions(
        repository,
        worker_id=worker_id,
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        active_only=False,
    )
    delivery_grants = list_delivery_grants(
        repository,
        worker_id=worker_id,
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        active_only=False,
    )
    auth_rejections = list_auth_rejections(
        repository,
        worker_id=worker_id,
        tenant_id=tenant_id,
        workspace_id=workspace_id,
    )

    active_sessions = [item for item in sessions if bool(item["is_active"])]
    active_delivery_grants = [item for item in delivery_grants if bool(item["is_active"])]

    by_worker: dict[str, dict[str, object]] = defaultdict(
        lambda: {
            "worker_id": "",
            "binding_count": 0,
            "cleanup_eligible_binding_count": 0,
            "active_bootstrap_issue_count": 0,
            "active_session_count": 0,
            "active_delivery_grant_count": 0,
            "active_ticket_count": 0,
            "recent_rejection_count": 0,
            "latest_bootstrap_issue_at": None,
            "latest_rejection_at": None,
        }
    )

    for binding in bindings:
        worker_summary = by_worker[str(binding["worker_id"])]
        worker_summary["worker_id"] = str(binding["worker_id"])
        worker_summary["binding_count"] = int(worker_summary["binding_count"]) + 1
        worker_summary["active_ticket_count"] = int(worker_summary["active_ticket_count"]) + int(
            binding["active_ticket_count"]
        )
        if bool(binding.get("cleanup_eligible")):
            worker_summary["cleanup_eligible_binding_count"] = int(
                worker_summary["cleanup_eligible_binding_count"]
            ) + 1

    for issue in bootstrap_issues:
        worker_summary = by_worker[str(issue["worker_id"])]
        worker_summary["worker_id"] = str(issue["worker_id"])
        worker_summary["active_bootstrap_issue_count"] = int(
            worker_summary["active_bootstrap_issue_count"]
        ) + 1
        latest_issue_at = worker_summary["latest_bootstrap_issue_at"]
        if latest_issue_at is None or issue["issued_at"] > latest_issue_at:
            worker_summary["latest_bootstrap_issue_at"] = issue["issued_at"]

    for session in active_sessions:
        worker_summary = by_worker[str(session["worker_id"])]
        worker_summary["worker_id"] = str(session["worker_id"])
        worker_summary["active_session_count"] = int(worker_summary["active_session_count"]) + 1

    for grant in active_delivery_grants:
        worker_summary = by_worker[str(grant["worker_id"])]
        worker_summary["worker_id"] = str(grant["worker_id"])
        worker_summary["active_delivery_grant_count"] = int(
            worker_summary["active_delivery_grant_count"]
        ) + 1

    for rejection in auth_rejections:
        worker_id_value = rejection.get("worker_id")
        if worker_id_value is None:
            continue
        worker_summary = by_worker[str(worker_id_value)]
        worker_summary["worker_id"] = str(worker_id_value)
        worker_summary["recent_rejection_count"] = int(worker_summary["recent_rejection_count"]) + 1
        latest_rejection_at = worker_summary["latest_rejection_at"]
        if latest_rejection_at is None or rejection["occurred_at"] > latest_rejection_at:
            worker_summary["latest_rejection_at"] = rejection["occurred_at"]

    worker_items = sorted(by_worker.values(), key=lambda item: str(item["worker_id"]))
    return {
        "filters": {
            "tenant_id": tenant_id,
            "workspace_id": workspace_id,
            "worker_id": worker_id,
        },
        "summary": {
            "binding_count": len(bindings),
            "cleanup_eligible_binding_count": sum(
                1 for binding in bindings if bool(binding.get("cleanup_eligible"))
            ),
            "active_bootstrap_issue_count": len(bootstrap_issues),
            "active_session_count": len(active_sessions),
            "active_delivery_grant_count": len(active_delivery_grants),
            "recent_rejection_count": len(auth_rejections),
            "active_ticket_count": sum(int(binding["active_ticket_count"]) for binding in bindings),
        },
        "workers": worker_items,
    }


def _collect_scope_containment_state(
    repository: ControlPlaneRepository,
    *,
    connection,
    tenant_id: str,
    workspace_id: str,
    worker_id: str | None,
    at: datetime,
) -> dict[str, object]:
    bindings = repository.list_worker_binding_admin_views(
        connection,
        worker_id=worker_id,
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        at=at,
    )
    bootstrap_issues = repository.list_worker_bootstrap_issues(
        connection,
        worker_id=worker_id,
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        active_only=True,
        at=at,
    )
    sessions = repository.list_worker_sessions(
        connection,
        worker_id=worker_id,
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        active_only=False,
    )
    active_sessions = [
        session for session in sessions if _is_worker_session_active(session, at=at)
    ]
    delivery_grants = repository.list_worker_delivery_grants(
        connection,
        worker_id=worker_id,
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        active_only=False,
    )
    active_delivery_grants = [
        grant for grant in delivery_grants if _is_worker_delivery_grant_active(grant, at=at)
    ]
    worker_ids = sorted(
        {
            str(binding["worker_id"])
            for binding in bindings
        }
        | {str(issue["worker_id"]) for issue in bootstrap_issues}
        | {str(session["worker_id"]) for session in active_sessions}
        | {str(grant["worker_id"]) for grant in active_delivery_grants}
    )
    return {
        "worker_ids": worker_ids,
        "bootstrap_issues": sorted(
            bootstrap_issues,
            key=lambda item: (item["issued_at"], str(item["issue_id"])),
            reverse=True,
        ),
        "active_sessions": sorted(
            active_sessions,
            key=lambda item: (item["issued_at"], str(item["session_id"])),
            reverse=True,
        ),
        "active_delivery_grants": sorted(
            active_delivery_grants,
            key=lambda item: (item["issued_at"], str(item["grant_id"])),
            reverse=True,
        ),
    }


def contain_scope(
    repository: ControlPlaneRepository,
    *,
    tenant_id: str,
    workspace_id: str,
    worker_id: str | None = None,
    dry_run: bool,
    revoke_bootstrap_issues: bool,
    revoke_sessions: bool,
    revoked_by: str | None = None,
    reason: str | None = None,
    expected_active_bootstrap_issue_count: int | None = None,
    expected_active_session_count: int | None = None,
    expected_active_delivery_grant_count: int | None = None,
) -> dict[str, object]:
    resolve_scope_args(tenant_id, workspace_id)
    if not revoke_bootstrap_issues and not revoke_sessions:
        raise RuntimeError("Please enable at least one containment action.")
    if not dry_run:
        if not revoked_by:
            raise RuntimeError("revoked_by is required when dry_run is false.")
        if not reason:
            raise RuntimeError("reason is required when dry_run is false.")
        if expected_active_bootstrap_issue_count is None:
            raise RuntimeError("expected_active_bootstrap_issue_count is required when dry_run is false.")
        if expected_active_session_count is None:
            raise RuntimeError("expected_active_session_count is required when dry_run is false.")
        if expected_active_delivery_grant_count is None:
            raise RuntimeError("expected_active_delivery_grant_count is required when dry_run is false.")

    at = now_local()
    with repository.transaction() as connection:
        state = _collect_scope_containment_state(
            repository,
            connection=connection,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            worker_id=worker_id,
            at=at,
        )
        bootstrap_issues = state["bootstrap_issues"] if revoke_bootstrap_issues else []
        active_sessions = state["active_sessions"] if revoke_sessions else []
        active_delivery_grants = state["active_delivery_grants"] if revoke_sessions else []

        impact_summary = {
            "active_bootstrap_issue_count": len(bootstrap_issues),
            "active_session_count": len(active_sessions),
            "active_delivery_grant_count": len(active_delivery_grants),
        }
        target_ids = {
            "worker_ids": list(state["worker_ids"]),
            "bootstrap_issue_ids": sorted(str(item["issue_id"]) for item in bootstrap_issues),
            "session_ids": sorted(str(item["session_id"]) for item in active_sessions),
            "delivery_grant_ids": sorted(str(item["grant_id"]) for item in active_delivery_grants),
        }

        if dry_run:
            return {
                "filters": {
                    "tenant_id": tenant_id,
                    "workspace_id": workspace_id,
                    "worker_id": worker_id,
                },
                "requested_actions": {
                    "revoke_bootstrap_issues": revoke_bootstrap_issues,
                    "revoke_sessions": revoke_sessions,
                },
                "impact_summary": impact_summary,
                "target_ids": target_ids,
                "dry_run": True,
                "executed": False,
                "result": None,
            }

        expected_counts = {
            "active_bootstrap_issue_count": int(expected_active_bootstrap_issue_count),
            "active_session_count": int(expected_active_session_count),
            "active_delivery_grant_count": int(expected_active_delivery_grant_count),
        }
        if impact_summary != expected_counts:
            raise WorkerAdminConflictError(
                "Containment target counts changed since preview. Refresh the scope view and retry."
            )

        revoked_bootstrap_issue_count = 0
        if revoke_bootstrap_issues:
            for issue in bootstrap_issues:
                revoked_bootstrap_issue_count += repository.revoke_worker_bootstrap_issues(
                    connection,
                    issue_id=str(issue["issue_id"]),
                    revoked_at=at,
                )

        revoked_session_count = 0
        revoked_delivery_grant_count = 0
        if revoke_sessions:
            revoked_delivery_grant_count = len(active_delivery_grants)
            for session in active_sessions:
                revoked_session_count += repository.revoke_worker_sessions(
                    connection,
                    session_id=str(session["session_id"]),
                    revoked_at=at,
                    revoke_reason=reason,
                    revoked_via=WORKER_ADMIN_SCOPE_CONTAINMENT_VIA,
                    revoked_by=revoked_by,
                )

    return {
        "filters": {
            "tenant_id": tenant_id,
            "workspace_id": workspace_id,
            "worker_id": worker_id,
        },
        "requested_actions": {
            "revoke_bootstrap_issues": revoke_bootstrap_issues,
            "revoke_sessions": revoke_sessions,
        },
        "impact_summary": impact_summary,
        "target_ids": target_ids,
        "dry_run": False,
        "executed": True,
        "result": {
            "revoked_bootstrap_issue_count": revoked_bootstrap_issue_count,
            "revoked_session_count": revoked_session_count,
            "revoked_delivery_grant_count": revoked_delivery_grant_count,
            "revoked_at": at,
            "revoked_by": revoked_by,
            "revoke_reason": reason,
        },
    }


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
