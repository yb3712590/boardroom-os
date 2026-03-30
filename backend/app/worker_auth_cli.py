from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from typing import Sequence

from app.config import get_settings
from app.core.time import now_local
from app.core.worker_bootstrap_tokens import issue_worker_bootstrap_token
from app.db.repository import ControlPlaneRepository

DEFAULT_BOOTSTRAP_TTL_SEC = 30 * 24 * 60 * 60


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


def _issue_bootstrap(args: argparse.Namespace) -> int:
    repository = _build_repository()
    issued_at = now_local()
    with repository.transaction() as connection:
        _require_active_worker(repository, args.worker_id, connection=connection)
        state = repository.ensure_worker_bootstrap_state(
            connection,
            worker_id=args.worker_id,
            at=issued_at,
        )
    token, expires_at = issue_worker_bootstrap_token(
        signing_secret=_resolve_bootstrap_signing_secret(),
        worker_id=args.worker_id,
        credential_version=int(state["credential_version"]),
        issued_at=issued_at,
        ttl_sec=args.ttl_sec,
    )
    _print_json(
        {
            "worker_id": args.worker_id,
            "credential_version": int(state["credential_version"]),
            "bootstrap_token": token,
            "issued_at": issued_at.isoformat(),
            "expires_at": expires_at.isoformat(),
        }
    )
    return 0


def _rotate_bootstrap(args: argparse.Namespace) -> int:
    repository = _build_repository()
    rotated_at = now_local()
    with repository.transaction() as connection:
        _require_active_worker(repository, args.worker_id, connection=connection)
        state = repository.rotate_worker_bootstrap_state(
            connection,
            worker_id=args.worker_id,
            rotated_at=rotated_at,
        )
    token, expires_at = issue_worker_bootstrap_token(
        signing_secret=_resolve_bootstrap_signing_secret(),
        worker_id=args.worker_id,
        credential_version=int(state["credential_version"]),
        issued_at=rotated_at,
        ttl_sec=args.ttl_sec,
    )
    _print_json(
        {
            "worker_id": args.worker_id,
            "credential_version": int(state["credential_version"]),
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
        state = repository.revoke_worker_bootstrap_state(
            connection,
            worker_id=args.worker_id,
            revoked_at=revoked_at,
        )
    _print_json(
        {
            "worker_id": args.worker_id,
            "credential_version": int(state["credential_version"]),
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
        )
    _print_json(
        {
            "grants": [_serialize_datetimes(grant) for grant in grants],
            "count": len(grants),
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

    issue_parser = subparsers.add_parser("issue-bootstrap")
    issue_parser.add_argument("--worker-id", required=True)
    issue_parser.add_argument("--ttl-sec", type=int, default=DEFAULT_BOOTSTRAP_TTL_SEC)
    issue_parser.set_defaults(handler=_issue_bootstrap)

    rotate_parser = subparsers.add_parser("rotate-bootstrap")
    rotate_parser.add_argument("--worker-id", required=True)
    rotate_parser.add_argument("--ttl-sec", type=int, default=DEFAULT_BOOTSTRAP_TTL_SEC)
    rotate_parser.set_defaults(handler=_rotate_bootstrap)

    revoke_bootstrap_parser = subparsers.add_parser("revoke-bootstrap")
    revoke_bootstrap_parser.add_argument("--worker-id", required=True)
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
    list_grants_parser.set_defaults(handler=_list_delivery_grants)

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
