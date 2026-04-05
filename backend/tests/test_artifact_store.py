from __future__ import annotations

from types import SimpleNamespace

import app._frozen.object_store as frozen_object_store
from app.core.artifact_store import (
    STORAGE_BACKEND_LOCAL_FILE,
    STORAGE_BACKEND_OBJECT_STORE,
    build_artifact_store,
)


def _artifact_store_settings(tmp_path, *, object_store_enabled: bool) -> SimpleNamespace:
    return SimpleNamespace(
        artifact_store_root=tmp_path / "artifacts",
        artifact_upload_staging_root=tmp_path / "artifact_uploads",
        artifact_upload_part_size_limit_bytes=5 * 1024 * 1024,
        artifact_upload_max_size_bytes=100 * 1024 * 1024,
        artifact_upload_max_part_count=10_000,
        artifact_object_store_enabled=object_store_enabled,
        artifact_object_store_bucket="boardroom-artifacts" if object_store_enabled else None,
        artifact_object_store_endpoint="https://object.local" if object_store_enabled else None,
        artifact_object_store_access_key="local-access" if object_store_enabled else None,
        artifact_object_store_secret_key="local-secret" if object_store_enabled else None,
        artifact_object_store_region="local",
    )


def test_build_artifact_store_delegates_optional_object_store_backend_creation(
    monkeypatch,
    tmp_path,
) -> None:
    settings = _artifact_store_settings(tmp_path, object_store_enabled=True)
    fake_backend = object()
    captured: dict[str, object] = {}

    def _build_optional_backend(**kwargs):
        captured.update(kwargs)
        return fake_backend

    monkeypatch.setattr(
        frozen_object_store,
        "build_optional_artifact_store_backend",
        _build_optional_backend,
    )

    store = build_artifact_store(settings)

    assert store.storage_backend == STORAGE_BACKEND_OBJECT_STORE
    assert store._object_store_backend is fake_backend
    assert captured["settings"] is settings
    assert captured["storage_backend_label"] == STORAGE_BACKEND_OBJECT_STORE


def test_build_artifact_store_keeps_local_storage_when_object_store_disabled(tmp_path) -> None:
    settings = _artifact_store_settings(tmp_path, object_store_enabled=False)

    store = build_artifact_store(settings)
    materialized = store.materialize_text("reports/ops/local-note.txt", "hello")

    assert store.storage_backend == STORAGE_BACKEND_LOCAL_FILE
    assert materialized.storage_backend == STORAGE_BACKEND_LOCAL_FILE
    assert materialized.storage_relpath == "reports/ops/local-note.txt"
    assert (settings.artifact_store_root / "reports/ops/local-note.txt").read_text(encoding="utf-8") == "hello"
