from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4


@dataclass(frozen=True)
class ParsedDeveloperInspectorRef:
    ref: str
    scheme: str
    relative_key: str
    artifact_kind: str


def parse_developer_inspector_ref(ref: str) -> ParsedDeveloperInspectorRef:
    if "://" not in ref:
        raise ValueError("Developer inspector ref must use a supported scheme.")
    scheme, relative_key = ref.split("://", 1)
    artifact_kind = {
        "ctx": "compiled_context_bundle",
        "manifest": "compile_manifest",
        "render": "rendered_execution_payload",
    }.get(scheme)
    if artifact_kind is None:
        raise ValueError("Developer inspector ref must use ctx://, manifest://, or render://.")
    if not relative_key:
        raise ValueError("Developer inspector ref path cannot be empty.")

    segments = relative_key.split("/")
    if any(
        not segment or segment in {".", ".."} or "\\" in segment or ":" in segment
        for segment in segments
    ):
        raise ValueError("Developer inspector ref path contains an unsafe segment.")

    return ParsedDeveloperInspectorRef(
        ref=ref,
        scheme=scheme,
        relative_key=relative_key,
        artifact_kind=artifact_kind,
    )


@dataclass(frozen=True)
class PersistedDeveloperInspectorArtifact:
    ref: str
    path: Path


class DeveloperInspectorStore:
    def __init__(self, root: Path):
        self.root = root

    def resolve_path(self, ref: str) -> Path:
        parsed = parse_developer_inspector_ref(ref)
        return self.root / parsed.artifact_kind / f"{parsed.relative_key}.json"

    def write_json(self, ref: str, payload: dict) -> PersistedDeveloperInspectorArtifact:
        target_path = self.resolve_path(ref)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = target_path.with_name(f"{target_path.name}.{uuid4().hex}.tmp")
        serialized = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False)
        try:
            temp_path.write_text(serialized + "\n", encoding="utf-8")
            temp_path.replace(target_path)
        finally:
            temp_path.unlink(missing_ok=True)
        return PersistedDeveloperInspectorArtifact(ref=ref, path=target_path)

    def read_json(self, ref: str) -> dict | None:
        target_path = self.resolve_path(ref)
        if not target_path.exists():
            return None
        return json.loads(target_path.read_text(encoding="utf-8"))

    def delete_ref(self, ref: str) -> None:
        self.resolve_path(ref).unlink(missing_ok=True)
