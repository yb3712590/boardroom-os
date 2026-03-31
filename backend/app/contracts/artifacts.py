from __future__ import annotations

from datetime import datetime

from app.contracts.common import JsonValue, StrictModel


class ArtifactMetadata(StrictModel):
    artifact_ref: str
    workflow_id: str
    ticket_id: str
    node_id: str
    path: str
    kind: str
    media_type: str | None = None
    status: str
    materialization_status: str
    lifecycle_status: str
    retention_class: str
    retention_class_source: str | None = None
    retention_ttl_sec: int | None = None
    retention_policy_source: str | None = None
    expires_at: datetime | None = None
    deleted_at: datetime | None = None
    deleted_by: str | None = None
    delete_reason: str | None = None
    storage_backend: str
    storage_object_key: str | None = None
    storage_delete_status: str
    storage_delete_error: str | None = None
    storage_deleted_at: datetime | None = None
    size_bytes: int | None = None
    content_hash: str | None = None
    created_at: datetime
    content_url: str
    download_url: str
    preview_url: str


class ArtifactMetadataEnvelope(StrictModel):
    data: ArtifactMetadata


class ArtifactPreviewData(StrictModel):
    artifact_ref: str
    preview_kind: str
    media_type: str | None = None
    lifecycle_status: str
    content_url: str | None = None
    download_url: str | None = None
    json_content: JsonValue | None = None
    text_content: str | None = None


class ArtifactPreviewEnvelope(StrictModel):
    data: ArtifactPreviewData


class ArtifactUploadSessionCreateRequest(StrictModel):
    filename: str | None = None
    media_type: str | None = None


class ArtifactUploadSessionData(StrictModel):
    session_id: str
    status: str
    filename: str | None = None
    media_type: str | None = None
    size_bytes: int | None = None
    content_hash: str | None = None
    part_count: int
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None
    aborted_at: datetime | None = None
    consumed_at: datetime | None = None
    consumed_by_artifact_ref: str | None = None


class ArtifactUploadSessionEnvelope(StrictModel):
    data: ArtifactUploadSessionData


class ArtifactUploadPartData(StrictModel):
    session_id: str
    part_number: int
    size_bytes: int
    uploaded_at: datetime
    status: str


class ArtifactUploadPartEnvelope(StrictModel):
    data: ArtifactUploadPartData
