from __future__ import annotations

from collections import defaultdict
from datetime import datetime

from app.core.time import now_local
from app.core.worker_scope_ops import (
    _is_worker_delivery_grant_active,
    _is_worker_session_active,
    list_auth_rejections,
    list_binding_admin_views,
    list_bootstrap_issues,
    list_delivery_grants,
    list_sessions,
    resolve_scope_args,
)
from app.db.repository import ControlPlaneRepository

ISSUED_VIA_WORKER_ADMIN_AUTH_CLI = "worker_admin_auth_cli"
WORKER_ADMIN_SCOPE_CONTAINMENT_VIA = "worker_admin_scope_containment"
DEFAULT_OPERATOR_TOKEN_REVOKE_REASON = "Manually revoked worker-admin operator token."


class WorkerAdminConflictError(RuntimeError):
    """Raised when a worker-admin write request conflicts with current runtime state."""


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
        {str(binding["worker_id"]) for binding in bindings}
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


__all__ = [
    "DEFAULT_OPERATOR_TOKEN_REVOKE_REASON",
    "ISSUED_VIA_WORKER_ADMIN_AUTH_CLI",
    "WORKER_ADMIN_SCOPE_CONTAINMENT_VIA",
    "WorkerAdminConflictError",
    "build_scope_summary",
    "contain_scope",
    "list_operator_tokens",
    "revoke_operator_token",
]
