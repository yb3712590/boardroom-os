from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta
from typing import Sequence

from fastapi import HTTPException

from app.config import get_settings
from app._frozen.worker_admin.core.worker_admin import (
    DEFAULT_OPERATOR_TOKEN_REVOKE_REASON,
    ISSUED_VIA_WORKER_ADMIN_AUTH_CLI,
    list_operator_tokens,
    revoke_operator_token,
)
from app.core.time import now_local
from app.core.worker_admin_tokens import issue_worker_admin_token
from app.db.repository import ControlPlaneRepository


def _serialize_datetimes(payload: dict[str, object]) -> dict[str, object]:
    serialized: dict[str, object] = {}
    for key, value in payload.items():
        if isinstance(value, datetime):
            serialized[key] = value.isoformat()
        else:
            serialized[key] = value
    return serialized


def _print_json(payload: dict[str, object]) -> None:
    print(json.dumps(_serialize_datetimes(payload), sort_keys=True))


def _resolve_worker_admin_signing_secret() -> str:
    signing_secret = get_settings().worker_admin_signing_secret
    if not signing_secret:
        raise RuntimeError("BOARDROOM_OS_WORKER_ADMIN_SIGNING_SECRET is not configured.")
    return signing_secret


def _resolve_requested_worker_admin_ttl_sec(ttl_sec: int | None) -> int:
    settings = get_settings()
    resolved = settings.worker_admin_default_ttl_sec if ttl_sec is None else int(ttl_sec)
    if resolved <= 0:
        raise RuntimeError("Worker-admin token TTL must be greater than zero.")
    if resolved > settings.worker_admin_max_ttl_sec:
        raise RuntimeError(
            "Requested worker-admin token TTL exceeds configured max TTL "
            f"({settings.worker_admin_max_ttl_sec} seconds)."
        )
    return resolved


def _build_repository() -> ControlPlaneRepository:
    settings = get_settings()
    repository = ControlPlaneRepository(
        settings.db_path,
        settings.busy_timeout_ms,
        settings.recent_event_limit,
    )
    repository.initialize()
    return repository


def _issue_token(args: argparse.Namespace) -> int:
    repository = _build_repository()
    issued_at = now_local()
    ttl_sec = _resolve_requested_worker_admin_ttl_sec(getattr(args, "ttl_sec", None))
    expires_at = issued_at + timedelta(seconds=ttl_sec)
    with repository.transaction() as connection:
        token_issue = repository.create_worker_admin_token_issue(
            connection,
            token_id=None,
            operator_id=args.operator_id,
            role=args.role,
            tenant_id=args.tenant_id,
            workspace_id=args.workspace_id,
            issued_at=issued_at,
            expires_at=expires_at,
            issued_via=ISSUED_VIA_WORKER_ADMIN_AUTH_CLI,
            issued_by=args.operator_id,
        )
        operator_token, expires_at = issue_worker_admin_token(
            signing_secret=_resolve_worker_admin_signing_secret(),
            operator_id=args.operator_id,
            role=args.role,
            tenant_id=args.tenant_id,
            workspace_id=args.workspace_id,
            token_id=str(token_issue["token_id"]),
            issued_at=issued_at,
            ttl_sec=ttl_sec,
            max_ttl_sec=get_settings().worker_admin_max_ttl_sec,
        )
        repository.update_worker_admin_token_issue_expiry(
            connection,
            token_id=str(token_issue["token_id"]),
            expires_at=expires_at,
        )
        repository.append_worker_admin_action_log(
            connection,
            occurred_at=issued_at,
            operator_id=args.operator_id,
            operator_role=args.role,
            auth_source="local_cli",
            action_type="issue_operator_token",
            dry_run=False,
            tenant_id=args.tenant_id,
            workspace_id=args.workspace_id,
            details={
                "token_id": str(token_issue["token_id"]),
                "target_operator_id": args.operator_id,
                "target_role": args.role,
                "issued_via": ISSUED_VIA_WORKER_ADMIN_AUTH_CLI,
                "succeeded": True,
            },
        )
    _print_json(
        {
            "token_id": str(token_issue["token_id"]),
            "operator_id": args.operator_id,
            "role": args.role,
            "tenant_id": args.tenant_id,
            "workspace_id": args.workspace_id,
            "operator_token": operator_token,
            "issued_at": issued_at,
            "expires_at": expires_at,
        }
    )
    return 0


def _list_tokens(args: argparse.Namespace) -> int:
    repository = _build_repository()
    tokens = list_operator_tokens(
        repository,
        operator_id=getattr(args, "operator_id", None),
        role=getattr(args, "role", None),
        tenant_id=getattr(args, "tenant_id", None),
        workspace_id=getattr(args, "workspace_id", None),
        active_only=bool(getattr(args, "active_only", False)),
    )
    _print_json(
        {
            "tokens": [_serialize_datetimes(token) for token in tokens],
            "count": len(tokens),
        }
    )
    return 0


def _revoke_token(args: argparse.Namespace) -> int:
    repository = _build_repository()
    revoked = revoke_operator_token(
        repository,
        token_id=args.token_id,
        revoked_by=args.revoked_by,
        reason=args.reason,
    )
    with repository.transaction() as connection:
        repository.append_worker_admin_action_log(
            connection,
            occurred_at=revoked["revoked_at"],
            operator_id=args.revoked_by,
            operator_role="platform_admin",
            auth_source="local_cli",
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
        )
    _print_json(
        {
            **_serialize_datetimes(revoked),
            "revoke_reason": revoked.get("revoke_reason"),
        }
    )
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m app.worker_admin_auth_cli")
    subparsers = parser.add_subparsers(dest="command", required=True)

    issue_token_parser = subparsers.add_parser("issue-token")
    issue_token_parser.add_argument("--operator-id", required=True)
    issue_token_parser.add_argument(
        "--role",
        required=True,
        choices=["platform_admin", "scope_admin", "scope_viewer"],
    )
    issue_token_parser.add_argument("--tenant-id")
    issue_token_parser.add_argument("--workspace-id")
    issue_token_parser.add_argument("--ttl-sec", type=int)
    issue_token_parser.set_defaults(handler=_issue_token)

    list_tokens_parser = subparsers.add_parser("list-tokens")
    list_tokens_parser.add_argument("--operator-id")
    list_tokens_parser.add_argument(
        "--role",
        choices=["platform_admin", "scope_admin", "scope_viewer"],
    )
    list_tokens_parser.add_argument("--tenant-id")
    list_tokens_parser.add_argument("--workspace-id")
    list_tokens_parser.add_argument("--active-only", action="store_true")
    list_tokens_parser.set_defaults(handler=_list_tokens)

    revoke_token_parser = subparsers.add_parser("revoke-token")
    revoke_token_parser.add_argument("--token-id", required=True)
    revoke_token_parser.add_argument("--revoked-by", required=True)
    revoke_token_parser.add_argument(
        "--reason",
        default=DEFAULT_OPERATOR_TOKEN_REVOKE_REASON,
    )
    revoke_token_parser.set_defaults(handler=_revoke_token)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    try:
        args = parser.parse_args(list(argv) if argv is not None else None)
        return int(args.handler(args))
    except (RuntimeError, HTTPException) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
