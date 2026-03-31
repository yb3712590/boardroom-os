from __future__ import annotations

import hashlib
from datetime import datetime

from fastapi import HTTPException

from app.contracts.artifacts import (
    ArtifactUploadPartData,
    ArtifactUploadPartEnvelope,
    ArtifactUploadSessionCreateRequest,
    ArtifactUploadSessionData,
    ArtifactUploadSessionEnvelope,
)
from app.core.artifact_store import ArtifactStore
from app.core.ids import new_prefixed_id
from app.core.time import now_local
from app.db.repository import ControlPlaneRepository


def _build_upload_session_envelope(session: dict) -> ArtifactUploadSessionEnvelope:
    payload = {
        "session_id": session["session_id"],
        "status": session["status"],
        "filename": session.get("filename"),
        "media_type": session.get("media_type"),
        "size_bytes": session.get("size_bytes"),
        "content_hash": session.get("content_hash"),
        "part_count": session.get("part_count") or 0,
        "created_at": session["created_at"],
        "updated_at": session["updated_at"],
        "completed_at": session.get("completed_at"),
        "aborted_at": session.get("aborted_at"),
        "consumed_at": session.get("consumed_at"),
        "consumed_by_artifact_ref": session.get("consumed_by_artifact_ref"),
    }
    return ArtifactUploadSessionEnvelope(
        data=ArtifactUploadSessionData.model_validate(payload)
    )


def create_artifact_upload_session(
    repository: ControlPlaneRepository,
    artifact_store: ArtifactStore,
    payload: ArtifactUploadSessionCreateRequest,
) -> ArtifactUploadSessionEnvelope:
    created_at = now_local()
    session_id = new_prefixed_id("upl")
    with repository.transaction() as connection:
        repository.create_artifact_upload_session(
            connection,
            session_id=session_id,
            created_at=created_at,
            created_by="local_api",
            filename=payload.filename,
            media_type=payload.media_type,
        )
        session = repository.get_artifact_upload_session(session_id, connection=connection)
    if session is None:
        raise RuntimeError("Artifact upload session was not persisted.")
    return _build_upload_session_envelope(session)


def upload_artifact_upload_part(
    repository: ControlPlaneRepository,
    artifact_store: ArtifactStore,
    *,
    session_id: str,
    part_number: int,
    content: bytes,
) -> ArtifactUploadPartEnvelope:
    uploaded_at = now_local()
    with repository.transaction() as connection:
        session = repository.get_artifact_upload_session(session_id, connection=connection)
        if session is None:
            raise HTTPException(
                status_code=404,
                detail=f"Artifact upload session '{session_id}' was not found.",
            )
        if session["status"] in {"ABORTED", "CONSUMED"}:
            raise HTTPException(
                status_code=409,
                detail=f"Artifact upload session '{session_id}' is no longer writable.",
            )
        if session["status"] == "COMPLETED":
            raise HTTPException(
                status_code=409,
                detail=f"Artifact upload session '{session_id}' is already completed.",
            )
        staging_relpath = artifact_store.write_upload_part(session_id, part_number, content)
        repository.save_artifact_upload_part(
            connection,
            session_id=session_id,
            part_number=part_number,
            staging_relpath=staging_relpath,
            size_bytes=len(content),
            content_hash=hashlib.sha256(content).hexdigest(),
            uploaded_at=uploaded_at,
        )
    return ArtifactUploadPartEnvelope(
        data=ArtifactUploadPartData(
            session_id=session_id,
            part_number=part_number,
            size_bytes=len(content),
            uploaded_at=uploaded_at,
            status="UPLOADING",
        )
    )


def complete_artifact_upload_session(
    repository: ControlPlaneRepository,
    artifact_store: ArtifactStore,
    *,
    session_id: str,
) -> ArtifactUploadSessionEnvelope:
    completed_at = now_local()
    with repository.transaction() as connection:
        session = repository.get_artifact_upload_session(session_id, connection=connection)
        if session is None:
            raise HTTPException(
                status_code=404,
                detail=f"Artifact upload session '{session_id}' was not found.",
            )
        if session["status"] == "ABORTED":
            raise HTTPException(
                status_code=409,
                detail=f"Artifact upload session '{session_id}' was aborted.",
            )
        if session["status"] == "CONSUMED":
            raise HTTPException(
                status_code=409,
                detail=f"Artifact upload session '{session_id}' was already consumed.",
            )
        if session["status"] == "COMPLETED":
            return _build_upload_session_envelope(session)

        parts = repository.list_artifact_upload_parts(session_id, connection=connection)
        if not parts:
            raise HTTPException(
                status_code=409,
                detail=f"Artifact upload session '{session_id}' has no parts to complete.",
            )
        expected_numbers = list(range(1, len(parts) + 1))
        actual_numbers = [part["part_number"] for part in parts]
        if actual_numbers != expected_numbers:
            raise HTTPException(
                status_code=409,
                detail=f"Artifact upload session '{session_id}' has missing part numbers.",
            )

        assembled = artifact_store.assemble_upload(
            session_id,
            [str(part["staging_relpath"]) for part in parts],
        )
        repository.complete_artifact_upload_session(
            connection,
            session_id=session_id,
            completed_at=completed_at,
            assembled_staging_relpath=assembled.staging_relpath,
            size_bytes=assembled.size_bytes,
            content_hash=assembled.content_hash,
            part_count=assembled.part_count,
        )
        completed_session = repository.get_artifact_upload_session(session_id, connection=connection)
    if completed_session is None:
        raise RuntimeError("Artifact upload session completion did not persist.")
    return _build_upload_session_envelope(completed_session)


def abort_artifact_upload_session(
    repository: ControlPlaneRepository,
    artifact_store: ArtifactStore,
    *,
    session_id: str,
) -> ArtifactUploadSessionEnvelope:
    aborted_at = now_local()
    with repository.transaction() as connection:
        session = repository.get_artifact_upload_session(session_id, connection=connection)
        if session is None:
            raise HTTPException(
                status_code=404,
                detail=f"Artifact upload session '{session_id}' was not found.",
            )
        repository.abort_artifact_upload_session(
            connection,
            session_id=session_id,
            aborted_at=aborted_at,
        )
        parts = repository.list_artifact_upload_parts(session_id, connection=connection)
        for part in parts:
            artifact_store.delete_upload_path(str(part["staging_relpath"]))
        artifact_store.delete_upload_path(session.get("assembled_staging_relpath"))
        aborted_session = repository.get_artifact_upload_session(session_id, connection=connection)
    if aborted_session is None:
        raise RuntimeError("Artifact upload session abort did not persist.")
    return _build_upload_session_envelope(aborted_session)


def require_completed_artifact_upload_session(
    repository: ControlPlaneRepository,
    *,
    session_id: str,
    at: datetime | None = None,
) -> dict:
    session = repository.get_artifact_upload_session(session_id)
    if session is None:
        raise ValueError(f"Artifact upload session '{session_id}' was not found.")
    if session["status"] != "COMPLETED":
        raise ValueError(f"Artifact upload session '{session_id}' is not completed.")
    return session
