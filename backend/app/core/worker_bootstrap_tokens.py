from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import datetime, timedelta

from fastapi import HTTPException

TOKEN_VERSION = "v1"


@dataclass(frozen=True)
class WorkerBootstrapTokenClaims:
    version: str
    worker_id: str
    credential_version: int
    tenant_id: str
    workspace_id: str
    issue_id: str | None
    issued_at: datetime
    expires_at: datetime


@dataclass(frozen=True)
class WorkerSessionTokenClaims:
    version: str
    session_id: str
    worker_id: str
    credential_version: int
    tenant_id: str
    workspace_id: str
    issued_at: datetime
    expires_at: datetime


def _base64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _base64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(f"{value}{padding}")


def _serialize_payload(payload: dict[str, str | int]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _parse_datetime(value: str, *, detail: str) -> datetime:
    try:
        return datetime.fromisoformat(value)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=detail) from exc


def _parse_int(value: str | int, *, detail: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=401, detail=detail) from exc


def _issue_token(signing_secret: str, payload: dict[str, str | int]) -> str:
    serialized = _serialize_payload(payload)
    signature = hmac.new(signing_secret.encode("utf-8"), serialized, hashlib.sha256).digest()
    return f"{_base64url_encode(serialized)}.{_base64url_encode(signature)}"


def _load_payload(token: str, *, signing_secret: str, detail: str) -> dict[str, str | int]:
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
    return payload


def issue_worker_bootstrap_token(
    *,
    signing_secret: str,
    worker_id: str,
    credential_version: int,
    tenant_id: str,
    workspace_id: str,
    issue_id: str | None,
    issued_at: datetime,
    ttl_sec: int,
) -> tuple[str, datetime]:
    expires_at = issued_at + timedelta(seconds=ttl_sec)
    payload = {
        "version": TOKEN_VERSION,
        "worker_id": worker_id,
        "credential_version": credential_version,
        "tenant_id": tenant_id,
        "workspace_id": workspace_id,
        "issued_at": issued_at.isoformat(),
        "expires_at": expires_at.isoformat(),
    }
    if issue_id:
        payload["issue_id"] = issue_id
    return _issue_token(signing_secret, payload), expires_at


def validate_worker_bootstrap_token(
    token: str,
    *,
    signing_secret: str,
    at: datetime,
) -> WorkerBootstrapTokenClaims:
    detail = "Worker bootstrap token is invalid."
    payload = _load_payload(token, signing_secret=signing_secret, detail=detail)
    issued_at = _parse_datetime(str(payload.get("issued_at") or ""), detail=detail)
    expires_at = _parse_datetime(str(payload.get("expires_at") or ""), detail=detail)
    if expires_at <= at:
        raise HTTPException(status_code=401, detail="Worker bootstrap token has expired.")
    worker_id = str(payload.get("worker_id") or "")
    credential_version = _parse_int(payload.get("credential_version"), detail=detail)
    tenant_id = str(payload.get("tenant_id") or "")
    workspace_id = str(payload.get("workspace_id") or "")
    issue_id = str(payload.get("issue_id") or "") or None
    if not worker_id or credential_version <= 0 or not tenant_id or not workspace_id:
        raise HTTPException(status_code=401, detail=detail)
    return WorkerBootstrapTokenClaims(
        version=str(payload["version"]),
        worker_id=worker_id,
        credential_version=credential_version,
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        issue_id=issue_id,
        issued_at=issued_at,
        expires_at=expires_at,
    )


def issue_worker_session_token(
    *,
    signing_secret: str,
    session_id: str,
    worker_id: str,
    credential_version: int,
    tenant_id: str,
    workspace_id: str,
    issued_at: datetime,
    ttl_sec: int,
) -> tuple[str, datetime]:
    expires_at = issued_at + timedelta(seconds=ttl_sec)
    payload = {
        "version": TOKEN_VERSION,
        "session_id": session_id,
        "worker_id": worker_id,
        "credential_version": credential_version,
        "tenant_id": tenant_id,
        "workspace_id": workspace_id,
        "issued_at": issued_at.isoformat(),
        "expires_at": expires_at.isoformat(),
    }
    return _issue_token(signing_secret, payload), expires_at


def validate_worker_session_token(
    token: str,
    *,
    signing_secret: str,
    at: datetime,
) -> WorkerSessionTokenClaims:
    detail = "Worker session token is invalid."
    payload = _load_payload(token, signing_secret=signing_secret, detail=detail)
    issued_at = _parse_datetime(str(payload.get("issued_at") or ""), detail=detail)
    expires_at = _parse_datetime(str(payload.get("expires_at") or ""), detail=detail)
    if expires_at <= at:
        raise HTTPException(status_code=401, detail="Worker session token has expired.")
    session_id = str(payload.get("session_id") or "")
    worker_id = str(payload.get("worker_id") or "")
    credential_version = _parse_int(payload.get("credential_version"), detail=detail)
    tenant_id = str(payload.get("tenant_id") or "")
    workspace_id = str(payload.get("workspace_id") or "")
    if not session_id or not worker_id or credential_version <= 0 or not tenant_id or not workspace_id:
        raise HTTPException(status_code=401, detail=detail)
    return WorkerSessionTokenClaims(
        version=str(payload["version"]),
        session_id=session_id,
        worker_id=worker_id,
        credential_version=credential_version,
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        issued_at=issued_at,
        expires_at=expires_at,
    )
