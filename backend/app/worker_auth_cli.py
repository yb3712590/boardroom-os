from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta
from typing import Sequence

from app.config import get_settings
from app.core.constants import DEFAULT_TENANT_ID, DEFAULT_WORKSPACE_ID
from app.core.time import now_local
from app.core.worker_bootstrap_tokens import issue_worker_bootstrap_token
from app.db.repository import ControlPlaneRepository

ISSUED_VIA_WORKER_AUTH_CLI = "worker_auth_cli"


def _build_repository() -> ControlPlaneRepository:
    settings = get_settings()
    repository = ControlPlaneRepository(
        settings.db_path,
        settings.busy_timeout_ms,
        settings.recent_event_limit,
    )
    repository.initialize()
    return repository


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


def _resolve_requested_bootstrap_ttl_sec(args: argparse.Namespace) -> int:
    ttl_sec = getattr(args, "ttl_sec", None)
    resolved = _resolve_bootstrap_default_ttl_sec() if ttl_sec is None else int(ttl_sec)
    max_ttl_sec = _resolve_bootstrap_max_ttl_sec()
    if resolved <= 0:
        raise RuntimeError("Bootstrap TTL must be greater than zero.")
    if resolved > max_ttl_sec:
        raise RuntimeError(
            f"Requested bootstrap TTL exceeds configured max TTL ({max_ttl_sec} seconds)."
        )
    return resolved


def _require_active_worker(repository: ControlPlaneRepository, worker_id: str, *, connection=None) -> None:
    employee = repository.get_employee_projection(worker_id, connection=connection)
    if employee is None:
        raise RuntimeError(f"Worker '{worker_id}' is not registered.")
    if str(employee.get("state") or "") != "ACTIVE":
        raise RuntimeError(f"Worker '{worker_id}' is not active.")


def _print_json(payload: dict[str, object]) -> None:
    print(json.dumps(payload, sort_keys=True))


def _serialize_datetimes(payload: dict[str, object]) -> dict[str, object]:
    serialized: dict[str, object] = {}
    for key, value in payload.items():
        if isinstance(value, datetime):
            serialized[key] = value.isoformat()
        else:
            serialized[key] = value
    return serialized


def _resolve_scope_args(args: argparse.Namespace) -> tuple[str | None, str | None]:
    tenant_id = getattr(args, "tenant_id", None)
    workspace_id = getattr(args, "workspace_id", None)
    if (tenant_id is None) != (workspace_id is None):
        raise RuntimeError("Please provide both --tenant-id and --workspace-id together.")
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
            "Worker has multiple bootstrap bindings. Please explicitly provide both --tenant-id and --workspace-id."
        )

    selected = bindings[0]
    return str(selected["tenant_id"]), str(selected["workspace_id"]), selected


def _create_binding(args: argparse.Namespace) -> int:
    repository = _build_repository()
    created_at = now_local()
    with repository.transaction() as connection:
        _require_active_worker(repository, args.worker_id, connection=connection)
        tenant_id, workspace_id = _resolve_scope_args(args)
        if tenant_id is None or workspace_id is None:
            raise RuntimeError("create-binding requires both --tenant-id and --workspace-id.")
        binding = repository.ensure_worker_bootstrap_state(
            connection,
            worker_id=args.worker_id,
            at=created_at,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
        )
    _print_json(_serialize_datetimes(binding))
    return 0


def _issue_bootstrap(args: argparse.Namespace) -> int:
    repository = _build_repository()
    issued_at = now_local()
    ttl_sec = _resolve_requested_bootstrap_ttl_sec(args)
    planned_expires_at = issued_at + timedelta(seconds=ttl_sec)
    with repository.transaction() as connection:
        _require_active_worker(repository, args.worker_id, connection=connection)
        tenant_id, workspace_id = _resolve_scope_args(args)
        tenant_id, workspace_id, _ = _select_worker_binding(
            repository,
            connection,
            worker_id=args.worker_id,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            allow_create=True,
        )
        _validate_bootstrap_tenant_allowed(tenant_id)
        state = repository.ensure_worker_bootstrap_state(
            connection,
            worker_id=args.worker_id,
            at=issued_at,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
        )
        issue = repository.create_worker_bootstrap_issue(
            connection,
            worker_id=args.worker_id,
            tenant_id=str(state["tenant_id"]),
            workspace_id=str(state["workspace_id"]),
            credential_version=int(state["credential_version"]),
            issued_at=issued_at,
            expires_at=planned_expires_at,
            issued_via=ISSUED_VIA_WORKER_AUTH_CLI,
            issued_by=args.issued_by,
            reason=args.reason,
        )
    token, expires_at = issue_worker_bootstrap_token(
        signing_secret=_resolve_bootstrap_signing_secret(),
        worker_id=args.worker_id,
        credential_version=int(state["credential_version"]),
        tenant_id=str(state["tenant_id"]),
        workspace_id=str(state["workspace_id"]),
        issue_id=str(issue["issue_id"]),
        issued_at=issued_at,
        ttl_sec=ttl_sec,
    )
    _print_json(
        {
            "issue_id": str(issue["issue_id"]),
            "worker_id": args.worker_id,
            "credential_version": int(state["credential_version"]),
            "tenant_id": str(state["tenant_id"]),
            "workspace_id": str(state["workspace_id"]),
            "issued_via": ISSUED_VIA_WORKER_AUTH_CLI,
            "issued_by": args.issued_by,
            "reason": args.reason,
            "bootstrap_token": token,
            "issued_at": issued_at.isoformat(),
            "expires_at": expires_at.isoformat(),
        }
    )
    return 0


def _rotate_bootstrap(args: argparse.Namespace) -> int:
    repository = _build_repository()
    rotated_at = now_local()
    ttl_sec = _resolve_requested_bootstrap_ttl_sec(args)
    planned_expires_at = rotated_at + timedelta(seconds=ttl_sec)
    with repository.transaction() as connection:
        _require_active_worker(repository, args.worker_id, connection=connection)
        tenant_id, workspace_id = _resolve_scope_args(args)
        tenant_id, workspace_id, _ = _select_worker_binding(
            repository,
            connection,
            worker_id=args.worker_id,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            allow_create=False,
        )
        _validate_bootstrap_tenant_allowed(tenant_id)
        state = repository.rotate_worker_bootstrap_state(
            connection,
            worker_id=args.worker_id,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            rotated_at=rotated_at,
        )
        issue = repository.create_worker_bootstrap_issue(
            connection,
            worker_id=args.worker_id,
            tenant_id=str(state["tenant_id"]),
            workspace_id=str(state["workspace_id"]),
            credential_version=int(state["credential_version"]),
            issued_at=rotated_at,
            expires_at=planned_expires_at,
            issued_via=ISSUED_VIA_WORKER_AUTH_CLI,
            issued_by=args.issued_by,
            reason=args.reason,
        )
    token, expires_at = issue_worker_bootstrap_token(
        signing_secret=_resolve_bootstrap_signing_secret(),
        worker_id=args.worker_id,
        credential_version=int(state["credential_version"]),
        tenant_id=str(state["tenant_id"]),
        workspace_id=str(state["workspace_id"]),
        issue_id=str(issue["issue_id"]),
        issued_at=rotated_at,
        ttl_sec=ttl_sec,
    )
    _print_json(
        {
            "issue_id": str(issue["issue_id"]),
            "worker_id": args.worker_id,
            "credential_version": int(state["credential_version"]),
            "tenant_id": str(state["tenant_id"]),
            "workspace_id": str(state["workspace_id"]),
            "issued_via": ISSUED_VIA_WORKER_AUTH_CLI,
            "issued_by": args.issued_by,
            "reason": args.reason,
            "bootstrap_token": token,
            "issued_at": rotated_at.isoformat(),
            "expires_at": expires_at.isoformat(),
            "rotated_at": rotated_at.isoformat(),
        }
    )
    return 0


def _revoke_bootstrap(args: argparse.Namespace) -> int:
    repository = _build_repository()
    revoked_at = now_local()
    with repository.transaction() as connection:
        _require_active_worker(repository, args.worker_id, connection=connection)
        tenant_id, workspace_id = _resolve_scope_args(args)
        tenant_id, workspace_id, _ = _select_worker_binding(
            repository,
            connection,
            worker_id=args.worker_id,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            allow_create=False,
        )
        state = repository.revoke_worker_bootstrap_state(
            connection,
            worker_id=args.worker_id,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            revoked_at=revoked_at,
        )
    _print_json(
        {
            "worker_id": args.worker_id,
            "credential_version": int(state["credential_version"]),
            "tenant_id": str(state["tenant_id"]),
            "workspace_id": str(state["workspace_id"]),
            "revoked_before": revoked_at.isoformat(),
        }
    )
    return 0


def _revoke_session(args: argparse.Namespace) -> int:
    repository = _build_repository()
    revoked_at = now_local()
    with repository.transaction() as connection:
        revoked_count = repository.revoke_worker_sessions(
            connection,
            session_id=args.session_id,
            worker_id=args.worker_id,
            revoked_at=revoked_at,
        )
    _print_json(
        {
            "worker_id": args.worker_id,
            "session_id": args.session_id,
            "revoked_count": revoked_count,
            "revoked_at": revoked_at.isoformat(),
        }
    )
    return 0


def _list_delivery_grants(args: argparse.Namespace) -> int:
    repository = _build_repository()
    with repository.connection() as connection:
        grants = repository.list_worker_delivery_grants(
            connection,
            worker_id=args.worker_id,
            session_id=args.session_id,
            ticket_id=args.ticket_id,
            tenant_id=args.tenant_id,
            workspace_id=args.workspace_id,
        )
    _print_json(
        {
            "grants": [_serialize_datetimes(grant) for grant in grants],
            "count": len(grants),
        }
    )
    return 0


def _list_sessions(args: argparse.Namespace) -> int:
    repository = _build_repository()
    with repository.connection() as connection:
        sessions = repository.list_worker_sessions(
            connection,
            worker_id=args.worker_id,
            tenant_id=args.tenant_id,
            workspace_id=args.workspace_id,
            active_only=args.active_only,
        )
    _print_json(
        {
            "sessions": [_serialize_datetimes(session) for session in sessions],
            "count": len(sessions),
        }
    )
    return 0


def _list_bindings(args: argparse.Namespace) -> int:
    repository = _build_repository()
    listed_at = now_local()
    with repository.connection() as connection:
        bindings = repository.list_worker_binding_admin_views(
            connection,
            worker_id=args.worker_id,
            tenant_id=args.tenant_id,
            workspace_id=args.workspace_id,
            at=listed_at,
        )
    _print_json(
        {
            "bindings": [_serialize_datetimes(binding) for binding in bindings],
            "count": len(bindings),
        }
    )
    return 0


def _cleanup_bindings(args: argparse.Namespace) -> int:
    repository = _build_repository()
    cleaned_at = now_local()
    with repository.transaction() as connection:
        bindings = repository.list_worker_binding_admin_views(
            connection,
            worker_id=args.worker_id,
            tenant_id=args.tenant_id,
            workspace_id=args.workspace_id,
            at=cleaned_at,
        )
        deleted_count = 0
        if not args.dry_run:
            for binding in bindings:
                if not bool(binding.get("cleanup_eligible")):
                    continue
                deleted_count += repository.delete_worker_bootstrap_state(
                    connection,
                    worker_id=str(binding["worker_id"]),
                    tenant_id=str(binding["tenant_id"]),
                    workspace_id=str(binding["workspace_id"]),
                )
    _print_json(
        {
            "bindings": [_serialize_datetimes(binding) for binding in bindings],
            "count": len(bindings),
            "deleted_count": deleted_count,
            "dry_run": bool(args.dry_run),
            "cleaned_at": cleaned_at.isoformat(),
        }
    )
    return 0


def _list_auth_rejections(args: argparse.Namespace) -> int:
    repository = _build_repository()
    with repository.connection() as connection:
        rejections = repository.list_worker_auth_rejection_logs(
            connection,
            worker_id=args.worker_id,
            tenant_id=args.tenant_id,
            workspace_id=args.workspace_id,
            route_family=args.route_family,
        )
    _print_json(
        {
            "rejections": [_serialize_datetimes(rejection) for rejection in rejections],
            "count": len(rejections),
        }
    )
    return 0


def _revoke_delivery_grant(args: argparse.Namespace) -> int:
    repository = _build_repository()
    revoked_at = now_local()
    with repository.transaction() as connection:
        revoked_count = repository.revoke_worker_delivery_grants(
            connection,
            grant_id=args.grant_id,
            revoked_at=revoked_at,
            revoke_reason=args.reason,
        )
    _print_json(
        {
            "grant_id": args.grant_id,
            "revoked_count": revoked_count,
            "revoked_at": revoked_at.isoformat(),
            "reason": args.reason,
        }
    )
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m app.worker_auth_cli")
    subparsers = parser.add_subparsers(dest="command", required=True)

    create_binding_parser = subparsers.add_parser("create-binding")
    create_binding_parser.add_argument("--worker-id", required=True)
    create_binding_parser.add_argument("--tenant-id", required=True)
    create_binding_parser.add_argument("--workspace-id", required=True)
    create_binding_parser.set_defaults(handler=_create_binding)

    issue_parser = subparsers.add_parser("issue-bootstrap")
    issue_parser.add_argument("--worker-id", required=True)
    issue_parser.add_argument("--ttl-sec", type=int)
    issue_parser.add_argument("--tenant-id")
    issue_parser.add_argument("--workspace-id")
    issue_parser.add_argument("--issued-by")
    issue_parser.add_argument("--reason")
    issue_parser.set_defaults(handler=_issue_bootstrap)

    rotate_parser = subparsers.add_parser("rotate-bootstrap")
    rotate_parser.add_argument("--worker-id", required=True)
    rotate_parser.add_argument("--ttl-sec", type=int)
    rotate_parser.add_argument("--tenant-id")
    rotate_parser.add_argument("--workspace-id")
    rotate_parser.add_argument("--issued-by")
    rotate_parser.add_argument("--reason")
    rotate_parser.set_defaults(handler=_rotate_bootstrap)

    revoke_bootstrap_parser = subparsers.add_parser("revoke-bootstrap")
    revoke_bootstrap_parser.add_argument("--worker-id", required=True)
    revoke_bootstrap_parser.add_argument("--tenant-id")
    revoke_bootstrap_parser.add_argument("--workspace-id")
    revoke_bootstrap_parser.set_defaults(handler=_revoke_bootstrap)

    revoke_session_parser = subparsers.add_parser("revoke-session")
    revoke_group = revoke_session_parser.add_mutually_exclusive_group(required=True)
    revoke_group.add_argument("--session-id")
    revoke_group.add_argument("--worker-id")
    revoke_session_parser.set_defaults(handler=_revoke_session)

    list_grants_parser = subparsers.add_parser("list-delivery-grants")
    list_grants_parser.add_argument("--worker-id")
    list_grants_parser.add_argument("--session-id")
    list_grants_parser.add_argument("--ticket-id")
    list_grants_parser.add_argument("--tenant-id")
    list_grants_parser.add_argument("--workspace-id")
    list_grants_parser.set_defaults(handler=_list_delivery_grants)

    list_sessions_parser = subparsers.add_parser("list-sessions")
    list_sessions_parser.add_argument("--worker-id")
    list_sessions_parser.add_argument("--tenant-id")
    list_sessions_parser.add_argument("--workspace-id")
    list_sessions_parser.add_argument("--active-only", action="store_true")
    list_sessions_parser.set_defaults(handler=_list_sessions)

    list_bindings_parser = subparsers.add_parser("list-bindings")
    list_bindings_parser.add_argument("--worker-id", required=True)
    list_bindings_parser.add_argument("--tenant-id")
    list_bindings_parser.add_argument("--workspace-id")
    list_bindings_parser.set_defaults(handler=_list_bindings)

    cleanup_bindings_parser = subparsers.add_parser("cleanup-bindings")
    cleanup_bindings_parser.add_argument("--worker-id", required=True)
    cleanup_bindings_parser.add_argument("--tenant-id")
    cleanup_bindings_parser.add_argument("--workspace-id")
    cleanup_bindings_parser.add_argument("--dry-run", action="store_true")
    cleanup_bindings_parser.set_defaults(handler=_cleanup_bindings)

    list_auth_rejections_parser = subparsers.add_parser("list-auth-rejections")
    list_auth_rejections_parser.add_argument("--worker-id")
    list_auth_rejections_parser.add_argument("--tenant-id")
    list_auth_rejections_parser.add_argument("--workspace-id")
    list_auth_rejections_parser.add_argument("--route-family")
    list_auth_rejections_parser.set_defaults(handler=_list_auth_rejections)

    revoke_grant_parser = subparsers.add_parser("revoke-delivery-grant")
    revoke_grant_parser.add_argument("--grant-id", required=True)
    revoke_grant_parser.add_argument(
        "--reason",
        default="Manually revoked worker delivery grant.",
    )
    revoke_grant_parser.set_defaults(handler=_revoke_delivery_grant)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    try:
        args = parser.parse_args(list(argv) if argv is not None else None)
        return int(args.handler(args))
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
