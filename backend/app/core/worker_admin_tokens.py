from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any
from typing import Literal

from fastapi import HTTPException

if TYPE_CHECKING:
    from app.db.repository import ControlPlaneRepository

WorkerAdminOperatorRole = Literal["platform_admin", "scope_admin", "scope_viewer"]

LEGACY_TOKEN_VERSION = "v1"
TOKEN_VERSION = "v2"
_VALID_OPERATOR_ROLES = {"platform_admin", "scope_admin", "scope_viewer"}


class WorkerAdminTokenValidationError(HTTPException):
    def __init__(
        self,
        *,
        detail: str,
        reason_code: str,
        operator_id: str | None = None,
        role: str | None = None,
        token_id: str | None = None,
        tenant_id: str | None = None,
        workspace_id: str | None = None,
    ):
        super().__init__(status_code=401, detail=detail)
        self.reason_code = reason_code
        self.operator_id = operator_id
        self.role = role
        self.token_id = token_id
        self.tenant_id = tenant_id
        self.workspace_id = workspace_id


@dataclass(frozen=True)
class WorkerAdminTokenClaims:
    version: str
    token_id: str | None
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


def _raise_validation_error(*, detail: str, reason_code: str) -> None:
    raise WorkerAdminTokenValidationError(detail=detail, reason_code=reason_code)


def _parse_datetime(value: str, *, detail: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise WorkerAdminTokenValidationError(detail=detail, reason_code="invalid_token") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        _raise_validation_error(detail=detail, reason_code="invalid_token")
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
        _raise_validation_error(detail=detail, reason_code="invalid_token")
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
    token_id: str | None = None,
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
        "version": TOKEN_VERSION if token_id is not None else LEGACY_TOKEN_VERSION,
        "token_id": token_id.strip() if token_id is not None else None,
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
    repository: ControlPlaneRepository | None = None,
    require_persisted_issue: bool = False,
) -> WorkerAdminTokenClaims:
    detail = "Worker-admin operator token is invalid."
    try:
        payload_segment, signature_segment = token.split(".", 1)
    except ValueError as exc:
        raise WorkerAdminTokenValidationError(detail=detail, reason_code="invalid_token") from exc

    try:
        payload_bytes = _base64url_decode(payload_segment)
        actual_signature = _base64url_decode(signature_segment)
    except (ValueError, binascii.Error) as exc:
        raise WorkerAdminTokenValidationError(detail=detail, reason_code="invalid_token") from exc

    expected_signature = hmac.new(
        signing_secret.encode("utf-8"),
        payload_bytes,
        hashlib.sha256,
    ).digest()
    if not hmac.compare_digest(actual_signature, expected_signature):
        _raise_validation_error(detail=detail, reason_code="invalid_token")

    try:
        payload = json.loads(payload_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise WorkerAdminTokenValidationError(detail=detail, reason_code="invalid_token") from exc

    version = str(payload.get("version") or "").strip()
    if version not in {LEGACY_TOKEN_VERSION, TOKEN_VERSION}:
        _raise_validation_error(detail=detail, reason_code="invalid_token")

    operator_id = str(payload.get("operator_id") or "").strip()
    role = str(payload.get("role") or "").strip()
    token_id = str(payload.get("token_id") or "").strip() or None
    tenant_id, workspace_id = _normalize_scope_pair_for_validation(
        tenant_id=payload.get("tenant_id"),
        workspace_id=payload.get("workspace_id"),
        detail=detail,
    )
    issued_at = _parse_datetime(str(payload.get("issued_at") or ""), detail=detail)
    expires_at = _parse_datetime(str(payload.get("expires_at") or ""), detail=detail)
    if expires_at <= at:
        raise WorkerAdminTokenValidationError(
            detail="Worker-admin operator token has expired.",
            reason_code="expired_token",
            operator_id=operator_id,
            role=role,
            token_id=token_id,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
        )
    if not operator_id or role not in _VALID_OPERATOR_ROLES:
        _raise_validation_error(detail=detail, reason_code="invalid_token")
    if role in {"scope_admin", "scope_viewer"} and (tenant_id is None or workspace_id is None):
        _raise_validation_error(detail=detail, reason_code="invalid_token")
    if version == TOKEN_VERSION and token_id is None:
        _raise_validation_error(detail=detail, reason_code="invalid_token")

    if version == TOKEN_VERSION and repository is not None and require_persisted_issue:
        token_issue = repository.get_worker_admin_token_issue(token_id or "")
        if token_issue is None:
            raise WorkerAdminTokenValidationError(
                detail=detail,
                reason_code="token_issue_not_found",
                operator_id=operator_id,
                role=role,
                token_id=token_id,
                tenant_id=tenant_id,
                workspace_id=workspace_id,
            )
        if token_issue.get("revoked_at") is not None:
            raise WorkerAdminTokenValidationError(
                detail="Worker-admin operator token has been revoked.",
                reason_code="revoked_token",
                operator_id=operator_id,
                role=role,
                token_id=token_id,
                tenant_id=tenant_id,
                workspace_id=workspace_id,
            )
        if token_issue["expires_at"] <= at:
            raise WorkerAdminTokenValidationError(
                detail="Worker-admin operator token has expired.",
                reason_code="expired_token",
                operator_id=operator_id,
                role=role,
                token_id=token_id,
                tenant_id=tenant_id,
                workspace_id=workspace_id,
            )
        persisted_fields: dict[str, Any] = {
            "operator_id": token_issue.get("operator_id"),
            "role": token_issue.get("role"),
            "tenant_id": token_issue.get("tenant_id"),
            "workspace_id": token_issue.get("workspace_id"),
            "issued_at": token_issue.get("issued_at"),
            "expires_at": token_issue.get("expires_at"),
        }
        claimed_fields: dict[str, Any] = {
            "operator_id": operator_id,
            "role": role,
            "tenant_id": tenant_id,
            "workspace_id": workspace_id,
            "issued_at": issued_at,
            "expires_at": expires_at,
        }
        if persisted_fields != claimed_fields:
            _raise_validation_error(detail=detail, reason_code="invalid_token")

    return WorkerAdminTokenClaims(
        version=version,
        token_id=token_id,
        operator_id=operator_id,
        role=role,  # type: ignore[arg-type]
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        issued_at=issued_at,
        expires_at=expires_at,
    )
