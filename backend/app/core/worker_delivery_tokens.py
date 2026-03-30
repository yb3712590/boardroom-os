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


WorkerDeliveryScope = Literal["execution_package", "artifact_read", "command"]
WorkerCommandName = Literal["ticket-start", "ticket-heartbeat", "ticket-result-submit"]

TOKEN_VERSION = "v1"


@dataclass(frozen=True)
class WorkerDeliveryTokenClaims:
    version: str
    scope: WorkerDeliveryScope
    worker_id: str
    session_id: str
    credential_version: int
    ticket_id: str
    artifact_ref: str | None
    command_name: WorkerCommandName | None
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
        return datetime.fromisoformat(value)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=detail) from exc


def issue_worker_delivery_token(
    *,
    signing_secret: str,
    scope: WorkerDeliveryScope,
    worker_id: str,
    session_id: str,
    credential_version: int,
    ticket_id: str,
    issued_at: datetime,
    ttl_sec: int,
    artifact_ref: str | None = None,
    command_name: WorkerCommandName | None = None,
) -> tuple[str, datetime]:
    expires_at = issued_at + timedelta(seconds=ttl_sec)
    payload = {
        "version": TOKEN_VERSION,
        "scope": scope,
        "worker_id": worker_id,
        "session_id": session_id,
        "credential_version": credential_version,
        "ticket_id": ticket_id,
        "artifact_ref": artifact_ref,
        "command_name": command_name,
        "issued_at": issued_at.isoformat(),
        "expires_at": expires_at.isoformat(),
    }
    serialized = _serialize_payload(payload)
    signature = hmac.new(signing_secret.encode("utf-8"), serialized, hashlib.sha256).digest()
    token = f"{_base64url_encode(serialized)}.{_base64url_encode(signature)}"
    return token, expires_at


def validate_worker_delivery_token(
    token: str,
    *,
    signing_secret: str,
    expected_scope: WorkerDeliveryScope,
    expected_ticket_id: str,
    at: datetime,
    expected_artifact_ref: str | None = None,
    expected_command_name: WorkerCommandName | None = None,
) -> WorkerDeliveryTokenClaims:
    try:
        payload_segment, signature_segment = token.split(".", 1)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="Worker delivery token is invalid.") from exc

    try:
        payload_bytes = _base64url_decode(payload_segment)
        actual_signature = _base64url_decode(signature_segment)
    except (ValueError, binascii.Error) as exc:
        raise HTTPException(status_code=401, detail="Worker delivery token is invalid.") from exc

    expected_signature = hmac.new(
        signing_secret.encode("utf-8"),
        payload_bytes,
        hashlib.sha256,
    ).digest()
    if not hmac.compare_digest(actual_signature, expected_signature):
        raise HTTPException(status_code=401, detail="Worker delivery token is invalid.")

    try:
        payload = json.loads(payload_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=401, detail="Worker delivery token is invalid.") from exc

    if payload.get("version") != TOKEN_VERSION:
        raise HTTPException(status_code=401, detail="Worker delivery token is invalid.")

    issued_at = _parse_datetime(
        str(payload.get("issued_at") or ""),
        detail="Worker delivery token is invalid.",
    )
    expires_at = _parse_datetime(
        str(payload.get("expires_at") or ""),
        detail="Worker delivery token is invalid.",
    )
    if expires_at <= at:
        raise HTTPException(status_code=401, detail="Worker delivery token has expired.")

    try:
        credential_version = int(payload.get("credential_version") or 0)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=401, detail="Worker delivery token is invalid.") from exc
    claims = WorkerDeliveryTokenClaims(
        version=str(payload["version"]),
        scope=str(payload.get("scope") or ""),
        worker_id=str(payload.get("worker_id") or ""),
        session_id=str(payload.get("session_id") or ""),
        credential_version=credential_version,
        ticket_id=str(payload.get("ticket_id") or ""),
        artifact_ref=(
            str(payload["artifact_ref"]) if payload.get("artifact_ref") is not None else None
        ),
        command_name=(
            str(payload["command_name"]) if payload.get("command_name") is not None else None
        ),
        issued_at=issued_at,
        expires_at=expires_at,
    )
    if not claims.session_id or claims.credential_version <= 0:
        raise HTTPException(status_code=401, detail="Worker delivery token is invalid.")

    if claims.scope != expected_scope:
        raise HTTPException(status_code=403, detail="Worker delivery token scope does not match this route.")
    if claims.ticket_id != expected_ticket_id:
        raise HTTPException(status_code=403, detail="Worker delivery token does not match this ticket.")
    if expected_artifact_ref is not None and claims.artifact_ref != expected_artifact_ref:
        raise HTTPException(status_code=403, detail="Worker delivery token does not match this artifact.")
    if expected_command_name is not None and claims.command_name != expected_command_name:
        raise HTTPException(status_code=403, detail="Worker delivery token does not match this command.")

    return claims
