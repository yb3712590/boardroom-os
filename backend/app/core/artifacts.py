from __future__ import annotations

import base64
import binascii
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import quote

from app.core.time import now_local

ARTIFACT_STATUS_MATERIALIZED = "MATERIALIZED"
ARTIFACT_STATUS_REGISTERED_ONLY = "REGISTERED_ONLY"

ARTIFACT_LIFECYCLE_ACTIVE = "ACTIVE"
ARTIFACT_LIFECYCLE_DELETED = "DELETED"
ARTIFACT_LIFECYCLE_EXPIRED = "EXPIRED"

ARTIFACT_RETENTION_PERSISTENT = "PERSISTENT"
ARTIFACT_RETENTION_EPHEMERAL = "EPHEMERAL"


def normalize_artifact_kind(kind: str) -> str:
    return kind.upper().strip()


def normalize_retention_class(retention_class: str | None) -> str:
    normalized = (retention_class or ARTIFACT_RETENTION_PERSISTENT).upper().strip()
    if normalized not in {ARTIFACT_RETENTION_PERSISTENT, ARTIFACT_RETENTION_EPHEMERAL}:
        raise ValueError(
            "Artifact retention_class must be PERSISTENT or EPHEMERAL."
        )
    return normalized


def is_binary_artifact_kind(kind: str) -> bool:
    return normalize_artifact_kind(kind) not in {"JSON", "TEXT", "MARKDOWN"}


def decode_artifact_base64(content_base64: str) -> bytes:
    try:
        return base64.b64decode(content_base64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("Binary artifacts require valid base64 content_base64.") from exc


def resolve_artifact_media_type(
    kind: str,
    logical_path: str,
    explicit_media_type: str | None = None,
) -> str | None:
    if explicit_media_type:
        return explicit_media_type

    normalized_kind = normalize_artifact_kind(kind)
    if normalized_kind == "JSON":
        return "application/json"
    if normalized_kind == "MARKDOWN":
        return "text/markdown"
    if normalized_kind == "TEXT":
        return "text/plain"
    if normalized_kind == "PDF":
        return "application/pdf"
    if normalized_kind == "IMAGE":
        suffix = logical_path.rsplit(".", 1)[-1].lower() if "." in logical_path else ""
        return {
            "png": "image/png",
            "jpg": "image/jpeg",
            "jpeg": "image/jpeg",
            "gif": "image/gif",
            "webp": "image/webp",
            "svg": "image/svg+xml",
        }.get(suffix, "image/*")

    suffix = logical_path.rsplit(".", 1)[-1].lower() if "." in logical_path else ""
    return {
        "pdf": "application/pdf",
        "zip": "application/zip",
        "json": "application/json",
        "txt": "text/plain",
        "md": "text/markdown",
        "png": "image/png",
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "gif": "image/gif",
        "webp": "image/webp",
    }.get(suffix, "application/octet-stream")


def build_artifact_urls(artifact_ref: str) -> dict[str, str]:
    encoded_ref = quote(artifact_ref, safe="")
    return {
        "content_url": (
            f"/api/v1/artifacts/content?artifact_ref={encoded_ref}&disposition=inline"
        ),
        "download_url": (
            f"/api/v1/artifacts/content?artifact_ref={encoded_ref}&disposition=attachment"
        ),
        "preview_url": f"/api/v1/artifacts/preview?artifact_ref={encoded_ref}",
    }


def compute_artifact_expiry(
    *,
    created_at: datetime,
    retention_ttl_sec: int | None,
) -> datetime | None:
    if retention_ttl_sec is None:
        return None
    return created_at + timedelta(seconds=retention_ttl_sec)


def resolve_artifact_lifecycle_status(
    artifact: dict[str, Any],
    *,
    at: datetime | None = None,
) -> str:
    status = str(artifact.get("lifecycle_status") or ARTIFACT_LIFECYCLE_ACTIVE)
    if status != ARTIFACT_LIFECYCLE_ACTIVE:
        return status

    expires_at = artifact.get("expires_at")
    if expires_at is None:
        return status

    now = at or now_local()
    if expires_at <= now:
        return ARTIFACT_LIFECYCLE_EXPIRED
    return status


def is_artifact_readable(
    artifact: dict[str, Any],
    *,
    at: datetime | None = None,
) -> bool:
    return (
        resolve_artifact_lifecycle_status(artifact, at=at) == ARTIFACT_LIFECYCLE_ACTIVE
        and artifact.get("materialization_status") == ARTIFACT_STATUS_MATERIALIZED
    )


def build_artifact_metadata(
    artifact: dict[str, Any],
    *,
    at: datetime | None = None,
) -> dict[str, Any]:
    lifecycle_status = resolve_artifact_lifecycle_status(artifact, at=at)
    urls = build_artifact_urls(str(artifact["artifact_ref"]))
    return {
        "artifact_ref": artifact["artifact_ref"],
        "workflow_id": artifact["workflow_id"],
        "ticket_id": artifact["ticket_id"],
        "node_id": artifact["node_id"],
        "path": artifact["logical_path"],
        "kind": artifact["kind"],
        "media_type": artifact.get("media_type"),
        "status": artifact["materialization_status"],
        "materialization_status": artifact["materialization_status"],
        "lifecycle_status": lifecycle_status,
        "retention_class": artifact.get("retention_class") or ARTIFACT_RETENTION_PERSISTENT,
        "expires_at": artifact.get("expires_at"),
        "deleted_at": artifact.get("deleted_at"),
        "deleted_by": artifact.get("deleted_by"),
        "delete_reason": artifact.get("delete_reason"),
        "size_bytes": artifact.get("size_bytes"),
        "content_hash": artifact.get("content_hash"),
        "created_at": artifact["created_at"],
        "content_url": urls["content_url"],
        "download_url": urls["download_url"],
        "preview_url": urls["preview_url"],
    }


def build_unindexed_artifact_access_descriptor(artifact_ref: str) -> dict[str, Any]:
    urls = build_artifact_urls(artifact_ref)
    return {
        "artifact_ref": artifact_ref,
        "logical_path": None,
        "media_type": None,
        "materialization_status": ARTIFACT_STATUS_REGISTERED_ONLY,
        "lifecycle_status": ARTIFACT_LIFECYCLE_ACTIVE,
        "size_bytes": None,
        "content_hash": None,
        "content_url": urls["content_url"],
        "preview_url": urls["preview_url"],
        "download_url": urls["download_url"],
    }


def build_artifact_access_descriptor(
    artifact: dict[str, Any] | None,
    *,
    artifact_ref: str,
    at: datetime | None = None,
) -> dict[str, Any]:
    if artifact is None:
        return build_unindexed_artifact_access_descriptor(artifact_ref)

    metadata = build_artifact_metadata(artifact, at=at)
    return {
        "artifact_ref": metadata["artifact_ref"],
        "logical_path": metadata["path"],
        "media_type": metadata["media_type"],
        "materialization_status": metadata["materialization_status"],
        "lifecycle_status": metadata["lifecycle_status"],
        "size_bytes": metadata["size_bytes"],
        "content_hash": metadata["content_hash"],
        "content_url": metadata["content_url"],
        "preview_url": metadata["preview_url"],
        "download_url": metadata["download_url"],
    }


def classify_artifact_preview_kind(
    *,
    kind: str,
    media_type: str | None,
) -> str:
    normalized_kind = normalize_artifact_kind(kind)
    if normalized_kind == "JSON":
        return "JSON"
    if normalized_kind in {"TEXT", "MARKDOWN"}:
        return "TEXT"
    if normalized_kind == "IMAGE":
        return "INLINE_MEDIA"
    if media_type == "application/pdf" or normalized_kind == "PDF":
        return "INLINE_MEDIA"
    return "DOWNLOAD_ONLY"
