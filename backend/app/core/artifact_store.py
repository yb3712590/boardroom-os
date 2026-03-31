from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from uuid import uuid4

from app.contracts.common import JsonValue

STORAGE_BACKEND_LOCAL_FILE = "LOCAL_FILE"
STORAGE_BACKEND_OBJECT_STORE = "OBJECT_STORE"

STORAGE_DELETE_STATUS_PRESENT = "PRESENT"
STORAGE_DELETE_STATUS_DELETE_PENDING = "DELETE_PENDING"
STORAGE_DELETE_STATUS_DELETE_FAILED = "DELETE_FAILED"
STORAGE_DELETE_STATUS_DELETED = "DELETED"


@dataclass(frozen=True)
class MaterializedArtifact:
    logical_path: str
    storage_relpath: str | None
    storage_backend: str
    storage_object_key: str | None
    content_hash: str
    size_bytes: int
    storage_delete_status: str = STORAGE_DELETE_STATUS_PRESENT


@dataclass(frozen=True)
class CompletedUpload:
    staging_relpath: str
    content_hash: str
    size_bytes: int
    part_count: int


class ObjectStoreClient(Protocol):
    def put_object(
        self,
        *,
        bucket: str,
        key: str,
        body: bytes,
        media_type: str | None = None,
    ) -> None: ...

    def get_object(self, *, bucket: str, key: str) -> bytes: ...

    def delete_object(self, *, bucket: str, key: str) -> None: ...


def normalize_artifact_logical_path(logical_path: str) -> str:
    normalized = logical_path.replace("\\", "/").strip("/")
    if not normalized:
        raise ValueError("Artifact path cannot be empty.")

    segments = normalized.split("/")
    if any(
        not segment or segment in {".", ".."} or ":" in segment
        for segment in segments
    ):
        raise ValueError("Artifact path contains an unsafe segment.")
    return "/".join(segments)


def normalize_upload_session_id(session_id: str) -> str:
    normalized = session_id.strip()
    if not normalized:
        raise ValueError("Upload session_id cannot be empty.")
    normalized = normalized.replace("\\", "/")
    if "/" in normalized or ":" in normalized or ".." in normalized:
        raise ValueError("Upload session_id contains an unsafe segment.")
    return normalized


def build_artifact_object_key(
    *,
    workflow_id: str,
    ticket_id: str,
    artifact_ref: str,
    logical_path: str,
) -> str:
    basename = Path(logical_path).name
    artifact_ref_hash = hashlib.sha256(artifact_ref.encode("utf-8")).hexdigest()
    return normalize_artifact_logical_path(
        f"artifacts/{workflow_id}/{ticket_id}/{artifact_ref_hash}/{basename}"
    )


class _LocalFileArtifactBackend:
    def __init__(self, root: Path):
        self.root = root

    def materialize_bytes(self, logical_path: str, content: bytes) -> MaterializedArtifact:
        target_path = self.root / normalize_artifact_logical_path(logical_path)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = target_path.with_name(f"{target_path.name}.{uuid4().hex}.tmp")
        try:
            temp_path.write_bytes(content)
            temp_path.replace(target_path)
        finally:
            temp_path.unlink(missing_ok=True)

        normalized = normalize_artifact_logical_path(logical_path)
        return MaterializedArtifact(
            logical_path=normalized,
            storage_relpath=normalized,
            storage_backend=STORAGE_BACKEND_LOCAL_FILE,
            storage_object_key=None,
            content_hash=hashlib.sha256(content).hexdigest(),
            size_bytes=len(content),
        )

    def read_bytes(self, storage_relpath: str) -> bytes:
        normalized = normalize_artifact_logical_path(storage_relpath)
        return (self.root / normalized).read_bytes()

    def delete(self, storage_relpath: str) -> None:
        normalized = normalize_artifact_logical_path(storage_relpath)
        target_path = self.root / normalized
        target_path.unlink(missing_ok=True)


class _S3CompatibleObjectStoreBackend:
    def __init__(self, *, bucket: str, client: ObjectStoreClient):
        self.bucket = bucket
        self.client = client

    def materialize_bytes(
        self,
        *,
        workflow_id: str,
        ticket_id: str,
        artifact_ref: str,
        logical_path: str,
        content: bytes,
        media_type: str | None,
    ) -> MaterializedArtifact:
        object_key = build_artifact_object_key(
            workflow_id=workflow_id,
            ticket_id=ticket_id,
            artifact_ref=artifact_ref,
            logical_path=logical_path,
        )
        self.client.put_object(
            bucket=self.bucket,
            key=object_key,
            body=content,
            media_type=media_type,
        )
        return MaterializedArtifact(
            logical_path=normalize_artifact_logical_path(logical_path),
            storage_relpath=None,
            storage_backend=STORAGE_BACKEND_OBJECT_STORE,
            storage_object_key=object_key,
            content_hash=hashlib.sha256(content).hexdigest(),
            size_bytes=len(content),
        )

    def read_bytes(self, storage_object_key: str) -> bytes:
        normalized = normalize_artifact_logical_path(storage_object_key)
        return self.client.get_object(bucket=self.bucket, key=normalized)

    def delete(self, storage_object_key: str) -> None:
        normalized = normalize_artifact_logical_path(storage_object_key)
        self.client.delete_object(bucket=self.bucket, key=normalized)


class _Boto3S3CompatibleObjectStoreClient:
    def __init__(self, *, endpoint: str, access_key: str, secret_key: str, region: str | None):
        try:
            import boto3
        except ImportError as exc:
            raise RuntimeError(
                "S3-compatible object storage requires boto3 to be installed."
            ) from exc

        session = boto3.session.Session(
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region,
        )
        self._client = session.client("s3", endpoint_url=endpoint)

    def put_object(
        self,
        *,
        bucket: str,
        key: str,
        body: bytes,
        media_type: str | None = None,
    ) -> None:
        kwargs: dict[str, object] = {"Bucket": bucket, "Key": key, "Body": body}
        if media_type:
            kwargs["ContentType"] = media_type
        self._client.put_object(**kwargs)

    def get_object(self, *, bucket: str, key: str) -> bytes:
        response = self._client.get_object(Bucket=bucket, Key=key)
        return response["Body"].read()

    def delete_object(self, *, bucket: str, key: str) -> None:
        self._client.delete_object(Bucket=bucket, Key=key)


def build_s3_compatible_object_store_client(settings) -> ObjectStoreClient:
    if not settings.artifact_object_store_endpoint:
        raise RuntimeError("Object store endpoint is required when object storage is enabled.")
    if not settings.artifact_object_store_access_key:
        raise RuntimeError("Object store access key is required when object storage is enabled.")
    if not settings.artifact_object_store_secret_key:
        raise RuntimeError("Object store secret key is required when object storage is enabled.")
    return _Boto3S3CompatibleObjectStoreClient(
        endpoint=settings.artifact_object_store_endpoint,
        access_key=settings.artifact_object_store_access_key,
        secret_key=settings.artifact_object_store_secret_key,
        region=settings.artifact_object_store_region,
    )


class ArtifactStore:
    def __init__(
        self,
        root: Path,
        *,
        upload_staging_root: Path | None = None,
        upload_part_size_limit_bytes: int = 5 * 1024 * 1024,
        upload_max_size_bytes: int = 100 * 1024 * 1024,
        upload_max_part_count: int = 10_000,
        object_store_bucket: str | None = None,
        object_store_client: ObjectStoreClient | None = None,
    ):
        self.root = root
        self.upload_staging_root = upload_staging_root or root.parent / "artifact_uploads"
        self.upload_part_size_limit_bytes = upload_part_size_limit_bytes
        self.upload_max_size_bytes = upload_max_size_bytes
        self.upload_max_part_count = upload_max_part_count
        self._local_backend = _LocalFileArtifactBackend(root)
        self._object_store_backend = (
            _S3CompatibleObjectStoreBackend(
                bucket=object_store_bucket,
                client=object_store_client,
            )
            if object_store_bucket and object_store_client is not None
            else None
        )

    @property
    def storage_backend(self) -> str:
        return (
            STORAGE_BACKEND_OBJECT_STORE
            if self._object_store_backend is not None
            else STORAGE_BACKEND_LOCAL_FILE
        )

    def resolve_path(self, logical_path: str) -> Path:
        normalized = normalize_artifact_logical_path(logical_path)
        return self.root / normalized

    def materialize_json(
        self,
        logical_path: str,
        payload: JsonValue,
        *,
        workflow_id: str | None = None,
        ticket_id: str | None = None,
        artifact_ref: str | None = None,
    ) -> MaterializedArtifact:
        serialized = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
        return self._write_bytes(
            logical_path,
            serialized.encode("utf-8"),
            media_type="application/json",
            workflow_id=workflow_id,
            ticket_id=ticket_id,
            artifact_ref=artifact_ref,
        )

    def materialize_text(
        self,
        logical_path: str,
        content: str,
        *,
        workflow_id: str | None = None,
        ticket_id: str | None = None,
        artifact_ref: str | None = None,
        media_type: str | None = None,
    ) -> MaterializedArtifact:
        return self._write_bytes(
            logical_path,
            content.encode("utf-8"),
            media_type=media_type,
            workflow_id=workflow_id,
            ticket_id=ticket_id,
            artifact_ref=artifact_ref,
        )

    def materialize_bytes(
        self,
        logical_path: str,
        content: bytes,
        *,
        workflow_id: str | None = None,
        ticket_id: str | None = None,
        artifact_ref: str | None = None,
        media_type: str | None = None,
    ) -> MaterializedArtifact:
        return self._write_bytes(
            logical_path,
            content,
            media_type=media_type,
            workflow_id=workflow_id,
            ticket_id=ticket_id,
            artifact_ref=artifact_ref,
        )

    def materialize_staged_upload(
        self,
        logical_path: str,
        staging_relpath: str,
        *,
        workflow_id: str,
        ticket_id: str,
        artifact_ref: str,
        media_type: str | None = None,
    ) -> MaterializedArtifact:
        content = self.read_upload_bytes(staging_relpath)
        return self.materialize_bytes(
            logical_path,
            content,
            workflow_id=workflow_id,
            ticket_id=ticket_id,
            artifact_ref=artifact_ref,
            media_type=media_type,
        )

    def read_bytes(
        self,
        storage_relpath: str | None = None,
        *,
        storage_object_key: str | None = None,
    ) -> bytes:
        if storage_object_key:
            if self._object_store_backend is None:
                raise RuntimeError("Object-store artifact access was requested without an object store backend.")
            return self._object_store_backend.read_bytes(storage_object_key)
        if storage_relpath is None:
            raise ValueError("Artifact read requires storage_relpath or storage_object_key.")
        return self._local_backend.read_bytes(storage_relpath)

    def delete(
        self,
        storage_relpath: str | None = None,
        *,
        storage_object_key: str | None = None,
    ) -> None:
        if storage_object_key:
            if self._object_store_backend is None:
                raise RuntimeError("Object-store artifact delete was requested without an object store backend.")
            self._object_store_backend.delete(storage_object_key)
            return
        if storage_relpath is None:
            return
        self._local_backend.delete(storage_relpath)

    def write_upload_part(self, session_id: str, part_number: int, content: bytes) -> str:
        if part_number < 1:
            raise ValueError("Upload part_number must be greater than 0.")
        if part_number > self.upload_max_part_count:
            raise ValueError("Upload exceeds the configured max part count.")
        if len(content) > self.upload_part_size_limit_bytes:
            raise ValueError("Upload part exceeds the configured max part size.")

        normalized_session_id = normalize_upload_session_id(session_id)
        relative_path = normalize_artifact_logical_path(
            f"{normalized_session_id}/parts/part-{part_number:05d}.bin"
        )
        target_path = self.upload_staging_root / relative_path
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_bytes(content)
        return relative_path

    def assemble_upload(
        self,
        session_id: str,
        part_relpaths: list[str],
    ) -> CompletedUpload:
        if not part_relpaths:
            raise ValueError("Upload session has no parts to assemble.")

        normalized_session_id = normalize_upload_session_id(session_id)
        relative_path = normalize_artifact_logical_path(
            f"{normalized_session_id}/assembled/payload.bin"
        )
        target_path = self.upload_staging_root / relative_path
        target_path.parent.mkdir(parents=True, exist_ok=True)

        hasher = hashlib.sha256()
        total_size = 0
        with target_path.open("wb") as assembled_file:
            for relative_part in part_relpaths:
                content = self.read_upload_bytes(relative_part)
                total_size += len(content)
                if total_size > self.upload_max_size_bytes:
                    raise ValueError("Upload exceeds the configured max total size.")
                hasher.update(content)
                assembled_file.write(content)

        return CompletedUpload(
            staging_relpath=relative_path,
            content_hash=hasher.hexdigest(),
            size_bytes=total_size,
            part_count=len(part_relpaths),
        )

    def read_upload_bytes(self, staging_relpath: str) -> bytes:
        normalized = normalize_artifact_logical_path(staging_relpath)
        return (self.upload_staging_root / normalized).read_bytes()

    def delete_upload_path(self, staging_relpath: str | None) -> None:
        if not staging_relpath:
            return
        normalized = normalize_artifact_logical_path(staging_relpath)
        target_path = self.upload_staging_root / normalized
        target_path.unlink(missing_ok=True)

    def _write_bytes(
        self,
        logical_path: str,
        content: bytes,
        *,
        media_type: str | None,
        workflow_id: str | None,
        ticket_id: str | None,
        artifact_ref: str | None,
    ) -> MaterializedArtifact:
        if self._object_store_backend is None:
            return self._local_backend.materialize_bytes(logical_path, content)
        if not workflow_id or not ticket_id or not artifact_ref:
            raise ValueError(
                "workflow_id, ticket_id, and artifact_ref are required for object-store artifacts."
            )
        return self._object_store_backend.materialize_bytes(
            workflow_id=workflow_id,
            ticket_id=ticket_id,
            artifact_ref=artifact_ref,
            logical_path=logical_path,
            content=content,
            media_type=media_type,
        )


def build_artifact_store(settings) -> ArtifactStore:
    object_store_client = None
    object_store_bucket = None
    if settings.artifact_object_store_enabled:
        if not settings.artifact_object_store_bucket:
            raise RuntimeError("Object store bucket is required when object storage is enabled.")
        object_store_client = build_s3_compatible_object_store_client(settings)
        object_store_bucket = settings.artifact_object_store_bucket
    return ArtifactStore(
        settings.artifact_store_root,
        upload_staging_root=settings.artifact_upload_staging_root,
        upload_part_size_limit_bytes=settings.artifact_upload_part_size_limit_bytes,
        upload_max_size_bytes=settings.artifact_upload_max_size_bytes,
        upload_max_part_count=settings.artifact_upload_max_part_count,
        object_store_bucket=object_store_bucket,
        object_store_client=object_store_client,
    )
