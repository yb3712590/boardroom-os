from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.config import get_settings
from app.core.artifact_store import ArtifactStore, MaterializedArtifact, normalize_artifact_logical_path
from app.core.artifact_uploads import require_completed_artifact_upload_session
from app.core.artifacts import (
    ARTIFACT_LIFECYCLE_ACTIVE,
    ARTIFACT_STATUS_MATERIALIZED,
    ARTIFACT_STATUS_REGISTERED_ONLY,
    decode_artifact_base64,
    resolve_artifact_media_type,
    resolve_artifact_retention,
    normalize_retention_class,
)
from app.core.workspace_path_contracts import match_contract_write_set
from app.db.repository import ControlPlaneRepository


@dataclass(frozen=True)
class PreparedTicketArtifact:
    artifact_ref: str
    logical_path: str
    kind: str
    media_type: str | None
    materialization_status: str
    lifecycle_status: str
    storage_backend: str
    storage_relpath: str | None
    storage_object_key: str | None
    storage_delete_status: str
    storage_delete_error: str | None
    content_hash: str | None
    size_bytes: int | None
    retention_class: str
    retention_class_source: str
    retention_ttl_sec: int | None
    retention_policy_source: str
    expires_at: datetime | None
    deleted_at: datetime | None
    deleted_by: str | None
    delete_reason: str | None


def match_allowed_write_set(path: str, allowed_write_set: list[str]) -> bool:
    return match_contract_write_set(path, allowed_write_set)


def _resolve_retention(
    *,
    created_at: datetime,
    logical_path: str,
    explicit_retention_class: str | None,
    retention_ttl_sec: int | None,
) -> Any:
    settings = get_settings()
    return resolve_artifact_retention(
        created_at=created_at,
        logical_path=logical_path,
        retention_class=explicit_retention_class,
        retention_ttl_sec=retention_ttl_sec,
        default_ephemeral_ttl_sec=settings.artifact_ephemeral_default_ttl_sec,
        default_operational_evidence_ttl_sec=settings.artifact_operational_evidence_default_ttl_sec,
        default_review_evidence_ttl_sec=settings.artifact_review_evidence_default_ttl_sec,
    )


def _build_prepared_materialized_artifact(
    *,
    artifact_ref: str,
    logical_path: str,
    normalized_kind: str,
    media_type: str | None,
    materialized: MaterializedArtifact,
    retention: Any,
) -> PreparedTicketArtifact:
    return PreparedTicketArtifact(
        artifact_ref=artifact_ref,
        logical_path=logical_path,
        kind=normalized_kind,
        media_type=media_type,
        materialization_status=ARTIFACT_STATUS_MATERIALIZED,
        lifecycle_status=ARTIFACT_LIFECYCLE_ACTIVE,
        storage_backend=materialized.storage_backend,
        storage_relpath=materialized.storage_relpath,
        storage_object_key=materialized.storage_object_key,
        storage_delete_status=materialized.storage_delete_status,
        storage_delete_error=None,
        content_hash=materialized.content_hash,
        size_bytes=materialized.size_bytes,
        retention_class=retention.retention_class,
        retention_class_source=retention.retention_class_source,
        retention_ttl_sec=retention.retention_ttl_sec,
        retention_policy_source=retention.retention_policy_source,
        expires_at=retention.expires_at,
        deleted_at=None,
        deleted_by=None,
        delete_reason=None,
    )


def prepare_written_artifacts(
    *,
    artifact_store: ArtifactStore | None,
    written_artifacts: list[Any],
    created_at: datetime,
    workflow_id: str,
    ticket_id: str,
) -> tuple[list[PreparedTicketArtifact], list[MaterializedArtifact]]:
    seen_refs: set[str] = set()
    seen_paths: set[str] = set()
    prepared: list[PreparedTicketArtifact] = []
    materialized_artifacts: list[MaterializedArtifact] = []

    for item in written_artifacts:
        if item.artifact_ref in seen_refs:
            raise ValueError("Structured result contains a duplicate artifact_ref.")
        seen_refs.add(item.artifact_ref)

        logical_path = normalize_artifact_logical_path(item.path)
        if logical_path in seen_paths:
            raise ValueError("Structured result contains a duplicate artifact path.")
        seen_paths.add(logical_path)

        normalized_kind = item.kind.upper()
        explicit_retention_class = (
            item.retention_class.value if hasattr(item.retention_class, "value") else item.retention_class
        )
        if explicit_retention_class is not None:
            normalize_retention_class(explicit_retention_class)

        if normalized_kind == "JSON":
            if item.content_json is None:
                raise ValueError("JSON artifacts require content_json.")
            if item.content_text is not None:
                raise ValueError("JSON artifacts must not include content_text.")
            if item.content_base64 is not None:
                raise ValueError("JSON artifacts must not include content_base64.")
        elif normalized_kind in {"TEXT", "MARKDOWN"}:
            if item.content_text is None:
                raise ValueError(f"{normalized_kind} artifacts require content_text.")
            if item.content_json is not None:
                raise ValueError(f"{normalized_kind} artifacts must not include content_json.")
            if item.content_base64 is not None:
                raise ValueError(f"{normalized_kind} artifacts must not include content_base64.")
        else:
            if item.content_json is not None or item.content_text is not None:
                raise ValueError(
                    f"{normalized_kind} artifacts cannot include inline structured content in the current MVP."
                )
            if item.content_base64 is not None:
                decode_artifact_base64(item.content_base64)

        media_type = resolve_artifact_media_type(normalized_kind, logical_path, item.media_type)
        retention = _resolve_retention(
            created_at=created_at,
            logical_path=logical_path,
            explicit_retention_class=explicit_retention_class,
            retention_ttl_sec=item.retention_ttl_sec,
        )

        if normalized_kind == "JSON":
            if artifact_store is None:
                raise RuntimeError("Artifact store is required to materialize JSON artifacts.")
            materialized = artifact_store.materialize_json(
                logical_path,
                item.content_json,
                workflow_id=workflow_id,
                ticket_id=ticket_id,
                artifact_ref=item.artifact_ref,
            )
            materialized_artifacts.append(materialized)
            prepared.append(
                _build_prepared_materialized_artifact(
                    artifact_ref=item.artifact_ref,
                    logical_path=logical_path,
                    normalized_kind=normalized_kind,
                    media_type=media_type,
                    materialized=materialized,
                    retention=retention,
                )
            )
            continue

        if normalized_kind in {"TEXT", "MARKDOWN"}:
            if artifact_store is None:
                raise RuntimeError(f"Artifact store is required to materialize {normalized_kind} artifacts.")
            materialized = artifact_store.materialize_text(
                logical_path,
                item.content_text or "",
                workflow_id=workflow_id,
                ticket_id=ticket_id,
                artifact_ref=item.artifact_ref,
                media_type=media_type,
            )
            materialized_artifacts.append(materialized)
            prepared.append(
                _build_prepared_materialized_artifact(
                    artifact_ref=item.artifact_ref,
                    logical_path=logical_path,
                    normalized_kind=normalized_kind,
                    media_type=media_type,
                    materialized=materialized,
                    retention=retention,
                )
            )
            continue

        if item.content_base64 is not None:
            if artifact_store is None:
                raise RuntimeError(f"Artifact store is required to materialize {normalized_kind} artifacts.")
            materialized = artifact_store.materialize_bytes(
                logical_path,
                decode_artifact_base64(item.content_base64),
                workflow_id=workflow_id,
                ticket_id=ticket_id,
                artifact_ref=item.artifact_ref,
                media_type=media_type,
            )
            materialized_artifacts.append(materialized)
            prepared.append(
                _build_prepared_materialized_artifact(
                    artifact_ref=item.artifact_ref,
                    logical_path=logical_path,
                    normalized_kind=normalized_kind,
                    media_type=media_type,
                    materialized=materialized,
                    retention=retention,
                )
            )
            continue

        prepared.append(
            PreparedTicketArtifact(
                artifact_ref=item.artifact_ref,
                logical_path=logical_path,
                kind=normalized_kind,
                media_type=media_type,
                materialization_status=ARTIFACT_STATUS_REGISTERED_ONLY,
                lifecycle_status=ARTIFACT_LIFECYCLE_ACTIVE,
                storage_backend="LOCAL_FILE",
                storage_relpath=None,
                storage_object_key=None,
                storage_delete_status="DELETED",
                storage_delete_error=None,
                content_hash=None,
                size_bytes=None,
                retention_class=retention.retention_class,
                retention_class_source=retention.retention_class_source,
                retention_ttl_sec=retention.retention_ttl_sec,
                retention_policy_source=retention.retention_policy_source,
                expires_at=retention.expires_at,
                deleted_at=None,
                deleted_by=None,
                delete_reason=None,
            )
        )

    return prepared, materialized_artifacts


def prepare_imported_upload_artifact(
    *,
    repository: ControlPlaneRepository,
    artifact_store: ArtifactStore | None,
    artifact_ref: str,
    path: str,
    kind: str,
    media_type: str | None,
    upload_session_id: str,
    retention_class: str | None,
    retention_ttl_sec: int | None,
    created_at: datetime,
    workflow_id: str,
    ticket_id: str,
) -> tuple[PreparedTicketArtifact, MaterializedArtifact]:
    if artifact_store is None:
        raise RuntimeError("Artifact store is required to import uploaded artifacts.")

    logical_path = normalize_artifact_logical_path(path)
    normalized_kind = kind.upper()
    explicit_retention_class = retention_class.value if hasattr(retention_class, "value") else retention_class
    if explicit_retention_class is not None:
        normalize_retention_class(explicit_retention_class)

    resolved_media_type = resolve_artifact_media_type(normalized_kind, logical_path, media_type)
    retention = _resolve_retention(
        created_at=created_at,
        logical_path=logical_path,
        explicit_retention_class=explicit_retention_class,
        retention_ttl_sec=retention_ttl_sec,
    )
    session = require_completed_artifact_upload_session(repository, session_id=upload_session_id)
    materialized = artifact_store.materialize_staged_upload(
        logical_path,
        str(session["assembled_staging_relpath"]),
        workflow_id=workflow_id,
        ticket_id=ticket_id,
        artifact_ref=artifact_ref,
        media_type=resolved_media_type,
    )
    return (
        _build_prepared_materialized_artifact(
            artifact_ref=artifact_ref,
            logical_path=logical_path,
            normalized_kind=normalized_kind,
            media_type=resolved_media_type,
            materialized=materialized,
            retention=retention,
        ),
        materialized,
    )


def save_prepared_artifact_record(
    repository: ControlPlaneRepository,
    connection: Any,
    *,
    prepared_artifact: PreparedTicketArtifact,
    workflow_id: str,
    ticket_id: str,
    node_id: str,
    created_at: datetime,
) -> None:
    repository.save_artifact_record(
        connection,
        artifact_ref=prepared_artifact.artifact_ref,
        workflow_id=workflow_id,
        ticket_id=ticket_id,
        node_id=node_id,
        logical_path=prepared_artifact.logical_path,
        kind=prepared_artifact.kind,
        media_type=prepared_artifact.media_type,
        materialization_status=prepared_artifact.materialization_status,
        lifecycle_status=prepared_artifact.lifecycle_status,
        storage_backend=prepared_artifact.storage_backend,
        storage_relpath=prepared_artifact.storage_relpath,
        storage_object_key=prepared_artifact.storage_object_key,
        storage_delete_status=prepared_artifact.storage_delete_status,
        storage_delete_error=prepared_artifact.storage_delete_error,
        content_hash=prepared_artifact.content_hash,
        size_bytes=prepared_artifact.size_bytes,
        retention_class=prepared_artifact.retention_class,
        retention_class_source=prepared_artifact.retention_class_source,
        retention_ttl_sec=prepared_artifact.retention_ttl_sec,
        retention_policy_source=prepared_artifact.retention_policy_source,
        expires_at=prepared_artifact.expires_at,
        deleted_at=prepared_artifact.deleted_at,
        deleted_by=prepared_artifact.deleted_by,
        delete_reason=prepared_artifact.delete_reason,
        created_at=created_at,
    )


def cleanup_materialized_artifacts(
    artifact_store: ArtifactStore | None,
    materialized_artifacts: list[MaterializedArtifact],
) -> None:
    if artifact_store is None:
        return
    for artifact in materialized_artifacts:
        artifact_store.delete(
            artifact.storage_relpath,
            storage_object_key=artifact.storage_object_key,
        )
