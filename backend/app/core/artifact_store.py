from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from app.contracts.common import JsonValue


@dataclass(frozen=True)
class MaterializedArtifact:
    logical_path: str
    storage_relpath: str
    content_hash: str
    size_bytes: int


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


class ArtifactStore:
    def __init__(self, root: Path):
        self.root = root

    def resolve_path(self, logical_path: str) -> Path:
        normalized = normalize_artifact_logical_path(logical_path)
        return self.root / normalized

    def materialize_json(self, logical_path: str, payload: JsonValue) -> MaterializedArtifact:
        serialized = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
        return self._write_bytes(logical_path, serialized.encode("utf-8"))

    def materialize_text(self, logical_path: str, content: str) -> MaterializedArtifact:
        return self._write_bytes(logical_path, content.encode("utf-8"))

    def materialize_bytes(self, logical_path: str, content: bytes) -> MaterializedArtifact:
        return self._write_bytes(logical_path, content)

    def read_bytes(self, storage_relpath: str) -> bytes:
        normalized = normalize_artifact_logical_path(storage_relpath)
        return (self.root / normalized).read_bytes()

    def delete(self, storage_relpath: str) -> None:
        normalized = normalize_artifact_logical_path(storage_relpath)
        target_path = self.root / normalized
        target_path.unlink(missing_ok=True)

    def _write_bytes(self, logical_path: str, content: bytes) -> MaterializedArtifact:
        target_path = self.resolve_path(logical_path)
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
            content_hash=hashlib.sha256(content).hexdigest(),
            size_bytes=len(content),
        )
