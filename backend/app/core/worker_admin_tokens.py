from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

from fastapi import HTTPException

WorkerAdminOperatorRole = Literal["platform_admin", "scope_admin", "scope_viewer"]

TOKEN_VERSION = "v1"
_VALID_OPERATOR_ROLES = {"platform_admin", "scope_admin", "scope_viewer"}


@dataclass(frozen=True)
class WorkerAdminTokenClaims:
    version: str
    operator_id: str
    role: WorkerAdminOperatorRole
    tenant_id: str | None
    workspace_id: str | None
    issued_at: datetime
    expires_at: datetime


def _base64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _base64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(f"{value}{padding}")


def _serialize_payload(payload: dict[str, str | None]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _parse_datetime(value: str, *, detail: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=detail) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise HTTPException(status_code=401, detail=detail)
    return parsed


def _normalize_scope_pair_for_validation(
    *,
    tenant_id: str | None,
    workspace_id: str | None,
    detail: str,
) -> tuple[str | None, str | None]:
    normalized_tenant_id = (tenant_id or "").strip() or None
    normalized_workspace_id = (workspace_id or "").strip() or None
    if (normalized_tenant_id is None) != (normalized_workspace_id is None):
        raise HTTPException(status_code=401, detail=detail)
    return normalized_tenant_id, normalized_workspace_id


def _normalize_scope_pair_for_issue(
    *,
    tenant_id: str | None,
    workspace_id: str | None,
) -> tuple[str | None, str | None]:
    normalized_tenant_id = (tenant_id or "").strip() or None
    normalized_workspace_id = (workspace_id or "").strip() or None
    if (normalized_tenant_id is None) != (normalized_workspace_id is None):
        raise RuntimeError("tenant_id and workspace_id must be provided together.")
    return normalized_tenant_id, normalized_workspace_id


def issue_worker_admin_token(
    *,
    signing_secret: str,
    operator_id: str,
    role: WorkerAdminOperatorRole,
    tenant_id: str | None,
    workspace_id: str | None,
    issued_at: datetime,
    ttl_sec: int,
    max_ttl_sec: int | None = None,
) -> tuple[str, datetime]:
    normalized_operator_id = operator_id.strip()
    if not normalized_operator_id:
        raise RuntimeError("operator_id is required.")
    if role not in _VALID_OPERATOR_ROLES:
        raise RuntimeError("role must be one of platform_admin, scope_admin, or scope_viewer.")
    normalized_tenant_id, normalized_workspace_id = _normalize_scope_pair_for_issue(
        tenant_id=tenant_id,
        workspace_id=workspace_id,
    )
    if role in {"scope_admin", "scope_viewer"} and (
        normalized_tenant_id is None or normalized_workspace_id is None
    ):
        raise RuntimeError("Scoped worker-admin operator tokens require tenant_id and workspace_id.")
    if ttl_sec <= 0:
        raise RuntimeError("ttl_sec must be greater than zero.")
    if max_ttl_sec is not None and ttl_sec > max_ttl_sec:
        raise RuntimeError(
            f"Requested worker-admin token TTL exceeds configured max TTL ({max_ttl_sec} seconds)."
        )

    expires_at = issued_at + timedelta(seconds=ttl_sec)
    payload = {
        "version": TOKEN_VERSION,
        "operator_id": normalized_operator_id,
        "role": role,
        "tenant_id": normalized_tenant_id,
        "workspace_id": normalized_workspace_id,
        "issued_at": issued_at.isoformat(),
        "expires_at": expires_at.isoformat(),
    }
    serialized = _serialize_payload(payload)
    signature = hmac.new(signing_secret.encode("utf-8"), serialized, hashlib.sha256).digest()
    return f"{_base64url_encode(serialized)}.{_base64url_encode(signature)}", expires_at


def validate_worker_admin_token(
    token: str,
    *,
    signing_secret: str,
    at: datetime,
) -> WorkerAdminTokenClaims:
    detail = "Worker-admin operator token is invalid."
    try:
        payload_segment, signature_segment = token.split(".", 1)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=detail) from exc

    try:
        payload_bytes = _base64url_decode(payload_segment)
        actual_signature = _base64url_decode(signature_segment)
    except (ValueError, binascii.Error) as exc:
        raise HTTPException(status_code=401, detail=detail) from exc

    expected_signature = hmac.new(
        signing_secret.encode("utf-8"),
        payload_bytes,
        hashlib.sha256,
    ).digest()
    if not hmac.compare_digest(actual_signature, expected_signature):
        raise HTTPException(status_code=401, detail=detail)

    try:
        payload = json.loads(payload_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=401, detail=detail) from exc

    if payload.get("version") != TOKEN_VERSION:
        raise HTTPException(status_code=401, detail=detail)

    issued_at = _parse_datetime(str(payload.get("issued_at") or ""), detail=detail)
    expires_at = _parse_datetime(str(payload.get("expires_at") or ""), detail=detail)
    if expires_at <= at:
        raise HTTPException(status_code=401, detail="Worker-admin operator token has expired.")

    operator_id = str(payload.get("operator_id") or "").strip()
    role = str(payload.get("role") or "").strip()
    tenant_id, workspace_id = _normalize_scope_pair_for_validation(
        tenant_id=payload.get("tenant_id"),
        workspace_id=payload.get("workspace_id"),
        detail=detail,
    )
    if not operator_id or role not in _VALID_OPERATOR_ROLES:
        raise HTTPException(status_code=401, detail=detail)
    if role in {"scope_admin", "scope_viewer"} and (tenant_id is None or workspace_id is None):
        raise HTTPException(status_code=401, detail=detail)

    return WorkerAdminTokenClaims(
        version=str(payload["version"]),
        operator_id=operator_id,
        role=role,  # type: ignore[arg-type]
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        issued_at=issued_at,
        expires_at=expires_at,
    )
