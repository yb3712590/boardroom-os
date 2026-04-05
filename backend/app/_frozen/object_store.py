from __future__ import annotations

import hashlib
from collections.abc import Callable
from typing import Any, Protocol


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


class S3CompatibleObjectStoreBackend:
    def __init__(
        self,
        *,
        bucket: str,
        client: ObjectStoreClient,
        object_key_builder: Callable[..., str],
        logical_path_normalizer: Callable[[str], str],
        materialized_artifact_factory: Callable[..., Any],
        storage_backend_label: str,
    ):
        self.bucket = bucket
        self.client = client
        self._object_key_builder = object_key_builder
        self._logical_path_normalizer = logical_path_normalizer
        self._materialized_artifact_factory = materialized_artifact_factory
        self._storage_backend_label = storage_backend_label

    def materialize_bytes(
        self,
        *,
        workflow_id: str,
        ticket_id: str,
        artifact_ref: str,
        logical_path: str,
        content: bytes,
        media_type: str | None,
    ) -> Any:
        object_key = self._object_key_builder(
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
        return self._materialized_artifact_factory(
            logical_path=self._logical_path_normalizer(logical_path),
            storage_relpath=None,
            storage_backend=self._storage_backend_label,
            storage_object_key=object_key,
            content_hash=hashlib.sha256(content).hexdigest(),
            size_bytes=len(content),
        )

    def read_bytes(self, storage_object_key: str) -> bytes:
        normalized = self._logical_path_normalizer(storage_object_key)
        return self.client.get_object(bucket=self.bucket, key=normalized)

    def delete(self, storage_object_key: str) -> None:
        normalized = self._logical_path_normalizer(storage_object_key)
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


def build_optional_artifact_store_backend(
    *,
    settings,
    object_key_builder: Callable[..., str],
    logical_path_normalizer: Callable[[str], str],
    materialized_artifact_factory: Callable[..., Any],
    storage_backend_label: str,
) -> S3CompatibleObjectStoreBackend | None:
    if not settings.artifact_object_store_enabled:
        return None
    if not settings.artifact_object_store_bucket:
        raise RuntimeError("Object store bucket is required when object storage is enabled.")
    return S3CompatibleObjectStoreBackend(
        bucket=settings.artifact_object_store_bucket,
        client=build_s3_compatible_object_store_client(settings),
        object_key_builder=object_key_builder,
        logical_path_normalizer=logical_path_normalizer,
        materialized_artifact_factory=materialized_artifact_factory,
        storage_backend_label=storage_backend_label,
    )
