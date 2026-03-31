from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from typing import Sequence

from fastapi import HTTPException

from app.config import get_settings
from app.core.time import now_local
from app.core.worker_admin_tokens import issue_worker_admin_token


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


def _issue_token(args: argparse.Namespace) -> int:
    issued_at = now_local()
    ttl_sec = _resolve_requested_worker_admin_ttl_sec(getattr(args, "ttl_sec", None))
    operator_token, expires_at = issue_worker_admin_token(
        signing_secret=_resolve_worker_admin_signing_secret(),
        operator_id=args.operator_id,
        role=args.role,
        tenant_id=args.tenant_id,
        workspace_id=args.workspace_id,
        issued_at=issued_at,
        ttl_sec=ttl_sec,
        max_ttl_sec=get_settings().worker_admin_max_ttl_sec,
    )
    _print_json(
        {
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
