from __future__ import annotations

from fastapi import APIRouter, Body, Path, Request

from app.contracts.artifacts import (
    ArtifactUploadPartEnvelope,
    ArtifactUploadSessionCreateRequest,
    ArtifactUploadSessionEnvelope,
)
from app.core.artifact_store import ArtifactStore
from app.core.artifact_uploads import (
    abort_artifact_upload_session,
    complete_artifact_upload_session,
    create_artifact_upload_session,
    upload_artifact_upload_part,
)
from app.db.repository import ControlPlaneRepository

router = APIRouter(prefix="/api/v1/artifact-uploads", tags=["artifact-uploads"])


@router.post("/sessions", response_model=ArtifactUploadSessionEnvelope)
def create_session(
    request: Request,
    payload: ArtifactUploadSessionCreateRequest,
) -> ArtifactUploadSessionEnvelope:
    repository: ControlPlaneRepository = request.app.state.repository
    artifact_store: ArtifactStore = request.app.state.artifact_store
    return create_artifact_upload_session(repository, artifact_store, payload)


@router.put("/sessions/{session_id}/parts/{part_number}", response_model=ArtifactUploadPartEnvelope)
def upload_part(
    request: Request,
    session_id: str = Path(min_length=1),
    part_number: int = Path(ge=1),
    content: bytes = Body(),
) -> ArtifactUploadPartEnvelope:
    repository: ControlPlaneRepository = request.app.state.repository
    artifact_store: ArtifactStore = request.app.state.artifact_store
    return upload_artifact_upload_part(
        repository,
        artifact_store,
        session_id=session_id,
        part_number=part_number,
        content=content,
    )


@router.post("/sessions/{session_id}/complete", response_model=ArtifactUploadSessionEnvelope)
def complete_session(
    request: Request,
    session_id: str = Path(min_length=1),
) -> ArtifactUploadSessionEnvelope:
    repository: ControlPlaneRepository = request.app.state.repository
    artifact_store: ArtifactStore = request.app.state.artifact_store
    return complete_artifact_upload_session(
        repository,
        artifact_store,
        session_id=session_id,
    )


@router.post("/sessions/{session_id}/abort", response_model=ArtifactUploadSessionEnvelope)
def abort_session(
    request: Request,
    session_id: str = Path(min_length=1),
) -> ArtifactUploadSessionEnvelope:
    repository: ControlPlaneRepository = request.app.state.repository
    artifact_store: ArtifactStore = request.app.state.artifact_store
    return abort_artifact_upload_session(
        repository,
        artifact_store,
        session_id=session_id,
    )
