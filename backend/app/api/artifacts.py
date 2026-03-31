from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request, Response

from app.contracts.artifacts import (
    ArtifactMetadata,
    ArtifactMetadataEnvelope,
    ArtifactPreviewData,
    ArtifactPreviewEnvelope,
)
from app.core.artifact_store import ArtifactStore
from app.core.artifacts import (
    ARTIFACT_LIFECYCLE_ACTIVE,
    ARTIFACT_STATUS_MATERIALIZED,
    build_artifact_metadata,
    classify_artifact_preview_kind,
    resolve_artifact_lifecycle_status,
)
from app.db.repository import ControlPlaneRepository

router = APIRouter(prefix="/api/v1/artifacts", tags=["artifacts"])


def _get_artifact_or_404(
    repository: ControlPlaneRepository,
    artifact_ref: str,
) -> dict:
    artifact = repository.get_artifact_by_ref(artifact_ref)
    if artifact is None:
        raise HTTPException(status_code=404, detail=f"Artifact '{artifact_ref}' was not found.")
    return artifact


@router.get("/by-ref", response_model=ArtifactMetadataEnvelope)
def get_artifact_by_ref(request: Request, artifact_ref: str = Query(min_length=1)) -> ArtifactMetadataEnvelope:
    repository: ControlPlaneRepository = request.app.state.repository
    artifact = _get_artifact_or_404(repository, artifact_ref)
    return ArtifactMetadataEnvelope(data=ArtifactMetadata.model_validate(build_artifact_metadata(artifact)))


@router.get("/content")
def get_artifact_content(
    request: Request,
    artifact_ref: str = Query(min_length=1),
    disposition: Literal["inline", "attachment"] = "inline",
) -> Response:
    repository: ControlPlaneRepository = request.app.state.repository
    artifact_store: ArtifactStore = request.app.state.artifact_store
    artifact = _get_artifact_or_404(repository, artifact_ref)
    lifecycle_status = resolve_artifact_lifecycle_status(artifact)
    if lifecycle_status != ARTIFACT_LIFECYCLE_ACTIVE:
        raise HTTPException(
            status_code=410,
            detail=f"Artifact '{artifact_ref}' is no longer available ({lifecycle_status}).",
        )
    if artifact.get("materialization_status") != ARTIFACT_STATUS_MATERIALIZED or (
        not artifact.get("storage_relpath") and not artifact.get("storage_object_key")
    ):
        raise HTTPException(
            status_code=409,
            detail=f"Artifact '{artifact_ref}' is registered but not materialized.",
        )

    content = artifact_store.read_bytes(
        str(artifact["storage_relpath"]) if artifact.get("storage_relpath") else None,
        storage_object_key=(
            str(artifact["storage_object_key"]) if artifact.get("storage_object_key") else None
        ),
    )
    filename = Path(str(artifact["logical_path"])).name
    media_type = artifact.get("media_type") or "application/octet-stream"
    headers = {"Content-Disposition": f'{disposition}; filename="{filename}"'}
    return Response(content=content, media_type=media_type, headers=headers)


@router.get("/preview", response_model=ArtifactPreviewEnvelope)
def get_artifact_preview(
    request: Request,
    artifact_ref: str = Query(min_length=1),
) -> ArtifactPreviewEnvelope:
    repository: ControlPlaneRepository = request.app.state.repository
    artifact_store: ArtifactStore = request.app.state.artifact_store
    artifact = _get_artifact_or_404(repository, artifact_ref)
    metadata = build_artifact_metadata(artifact)
    lifecycle_status = resolve_artifact_lifecycle_status(artifact)
    if lifecycle_status != ARTIFACT_LIFECYCLE_ACTIVE:
        raise HTTPException(
            status_code=410,
            detail=f"Artifact '{artifact_ref}' is no longer available ({lifecycle_status}).",
        )
    if artifact.get("materialization_status") != ARTIFACT_STATUS_MATERIALIZED or (
        not artifact.get("storage_relpath") and not artifact.get("storage_object_key")
    ):
        raise HTTPException(
            status_code=409,
            detail=f"Artifact '{artifact_ref}' is registered but not materialized.",
        )

    preview_kind = classify_artifact_preview_kind(
        kind=str(artifact["kind"]),
        media_type=artifact.get("media_type"),
    )
    preview_payload = {
        "artifact_ref": artifact_ref,
        "preview_kind": preview_kind,
        "media_type": artifact.get("media_type"),
        "lifecycle_status": metadata["lifecycle_status"],
        "content_url": metadata["content_url"],
        "download_url": metadata["download_url"],
        "json_content": None,
        "text_content": None,
    }

    content = artifact_store.read_bytes(
        str(artifact["storage_relpath"]) if artifact.get("storage_relpath") else None,
        storage_object_key=(
            str(artifact["storage_object_key"]) if artifact.get("storage_object_key") else None
        ),
    )
    if preview_kind == "JSON":
        preview_payload["json_content"] = json.loads(content.decode("utf-8"))
    elif preview_kind == "TEXT":
        preview_payload["text_content"] = content.decode("utf-8")

    return ArtifactPreviewEnvelope(data=ArtifactPreviewData.model_validate(preview_payload))
