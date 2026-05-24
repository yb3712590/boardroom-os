from __future__ import annotations

import hashlib
import json
from datetime import datetime
from enum import StrEnum
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Self

from pydantic import BaseModel, ConfigDict, field_serializer, field_validator, model_validator

from boardroom_os.agents.profiles import RoleProfileRegistry
from boardroom_os.agents.skills import (
    McpInterfaceRef,
    McpInterfaceRegistry,
    PromptRef,
    PromptSourceRegistry,
    RoleProfileId,
    SkillFileRef,
    SkillFileSourceRegistry,
)
from boardroom_os.contracts.types import NonEmptyTextValue
from boardroom_os.workspace.manifest import WorkspaceManifest, WorkspaceManifestRef

_MANIFEST_PATH = "00-boardroom/agents/asset-import-manifest.yaml"
_AGENT_ROOT = "00-boardroom/agents"
_REPO_LAYOUT_PREFIXES = ("src", "src/boardroom_os", "tests", "doc", "scripts", "examples", "backend")
_WORKSPACE_SECTION_PREFIXES = ("00-boardroom", "10-project", "20-evidence", "30-audit")
_HEX_DIGITS = frozenset("0123456789abcdef")


class AgentAssetImportError(ValueError):
    pass


class AgentAssetImportManifestRef(NonEmptyTextValue):
    pass


class AgentAssetBundleSourceRef(NonEmptyTextValue):
    pass


class AgentAssetRef(NonEmptyTextValue):
    pass


class AgentAssetSha256(NonEmptyTextValue):
    @field_validator("value", mode="before")
    @classmethod
    def _reject_invalid_sha256(cls, value: object) -> str:
        normalized = str(value).strip()
        if len(normalized) != 64 or any(char not in _HEX_DIGITS for char in normalized):
            raise ValueError("sha256 must be a 64-character lowercase hex digest")
        return normalized


class AgentAssetSourcePath(NonEmptyTextValue):
    @field_validator("value")
    @classmethod
    def _reject_unsafe_source_path(cls, value: str) -> str:
        normalized = _validate_relative_file_path(value, field_name="source_path")
        first_segment = normalized.split("/", 1)[0]
        if first_segment in _WORKSPACE_SECTION_PREFIXES:
            raise ValueError("source_path must not use generated workspace section prefixes")
        if _uses_reserved_repo_prefix(normalized):
            raise ValueError("source_path must not use framework repository layout")
        return normalized


class AgentAssetTargetPath(NonEmptyTextValue):
    @field_validator("value")
    @classmethod
    def _reject_unsafe_target_path(cls, value: str) -> str:
        normalized = _validate_relative_file_path(value, field_name="target_path")
        if not normalized.startswith(f"{_AGENT_ROOT}/"):
            raise ValueError("target_path must be under 00-boardroom/agents")
        if normalized == _MANIFEST_PATH:
            raise ValueError("target_path must not point to asset-import-manifest.yaml")
        return normalized


class AgentAssetManifestPath(NonEmptyTextValue):
    @field_validator("value")
    @classmethod
    def _require_manifest_path(cls, value: str) -> str:
        normalized = _validate_relative_file_path(value, field_name="manifest_path")
        if normalized != _MANIFEST_PATH:
            raise ValueError("manifest_path must be 00-boardroom/agents/asset-import-manifest.yaml")
        return normalized


class AgentAssetBundleSourceKind(StrEnum):
    LOCAL_BUNDLE = "local_bundle"


class AgentAssetKind(StrEnum):
    ROLE_CONFIG = "role_config"
    SKILL_FILE = "skill_file"
    PROMPT_FILE = "prompt_file"
    MCP_INTERFACE_MANIFEST = "mcp_interface_manifest"


_TARGET_PREFIX_BY_KIND: dict[AgentAssetKind, str] = {
    AgentAssetKind.ROLE_CONFIG: "00-boardroom/agents/roles/",
    AgentAssetKind.SKILL_FILE: "00-boardroom/agents/skills/",
    AgentAssetKind.PROMPT_FILE: "00-boardroom/agents/prompts/",
    AgentAssetKind.MCP_INTERFACE_MANIFEST: "00-boardroom/agents/mcp/",
}


class AgentAssetImportEntry(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    asset_ref: AgentAssetRef
    asset_kind: AgentAssetKind
    source_path: AgentAssetSourcePath
    target_path: AgentAssetTargetPath
    sha256: AgentAssetSha256

    @model_validator(mode="after")
    def _validate_kind_target_prefix(self) -> Self:
        expected_prefix = _TARGET_PREFIX_BY_KIND[self.asset_kind]
        if not self.target_path.value.startswith(expected_prefix):
            raise ValueError(f"target_path must be under {expected_prefix} for {self.asset_kind.value}")
        return self

    @field_serializer("asset_ref", "source_path", "target_path", "sha256")
    def _serialize_ref(self, value: NonEmptyTextValue) -> dict[str, str]:
        return value.model_dump()

    @field_serializer("asset_kind")
    def _serialize_asset_kind(self, value: AgentAssetKind) -> str:
        return value.value


class AgentAssetImportBatch(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    source_ref: AgentAssetBundleSourceRef
    source_kind: AgentAssetBundleSourceKind
    imported_at: datetime
    entries: tuple[AgentAssetImportEntry, ...]

    @field_validator("imported_at")
    @classmethod
    def _require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("imported_at must include timezone")
        return value

    @model_validator(mode="after")
    def _validate_entries(self) -> Self:
        if not self.entries:
            raise ValueError("entries must not be empty")
        if self.source_kind is not AgentAssetBundleSourceKind.LOCAL_BUNDLE:
            raise ValueError("source_kind must be local_bundle")
        _require_unique_values((entry.asset_ref.value for entry in self.entries), "asset_ref values must be unique within batch")
        _require_unique_values((entry.source_path.value for entry in self.entries), "source_path values must be unique within batch")
        _require_unique_values((entry.target_path.value for entry in self.entries), "target_path values must be unique within batch")
        if tuple(sorted(self.entries, key=lambda entry: entry.target_path.value)) != self.entries:
            raise ValueError("entries must be sorted by target_path")
        return self

    @field_serializer("source_ref")
    def _serialize_source_ref(self, value: AgentAssetBundleSourceRef) -> dict[str, str]:
        return value.model_dump()

    @field_serializer("source_kind")
    def _serialize_source_kind(self, value: AgentAssetBundleSourceKind) -> str:
        return value.value

    @field_serializer("imported_at")
    def _serialize_imported_at(self, value: datetime) -> str:
        return value.isoformat().replace("+00:00", "Z")

    @field_serializer("entries")
    def _serialize_entries(self, values: tuple[AgentAssetImportEntry, ...]) -> list[dict[str, object]]:
        return [value.model_dump(mode="json") for value in values]


class AgentAssetImportManifest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    agent_asset_import_manifest_id: AgentAssetImportManifestRef
    workspace_manifest_ref: WorkspaceManifestRef
    manifest_path: AgentAssetManifestPath
    batches: tuple[AgentAssetImportBatch, ...]

    @model_validator(mode="after")
    def _validate_manifest(self) -> Self:
        expected_id = f"agent-asset-import.{self.workspace_manifest_ref.value}"
        if self.agent_asset_import_manifest_id.value != expected_id:
            raise ValueError(f"agent_asset_import_manifest_id must be {expected_id}")
        if not self.batches:
            raise ValueError("batches must not be empty")
        _require_unique_values((batch.source_ref.value for batch in self.batches), "source_ref values must be unique")
        asset_refs: dict[str, AgentAssetImportEntry] = {}
        target_paths: dict[str, AgentAssetImportEntry] = {}
        for batch in self.batches:
            for entry in batch.entries:
                existing_asset = asset_refs.get(entry.asset_ref.value)
                if existing_asset is not None and (
                    existing_asset.sha256 != entry.sha256 or existing_asset.target_path != entry.target_path
                ):
                    raise ValueError("asset_ref cannot be reused with different sha256 or target_path")
                asset_refs[entry.asset_ref.value] = entry

                existing_target = target_paths.get(entry.target_path.value)
                if existing_target is not None and existing_target.sha256 != entry.sha256:
                    raise ValueError("target_path cannot be reused with different sha256")
                target_paths[entry.target_path.value] = entry
        return self

    @field_serializer("agent_asset_import_manifest_id", "workspace_manifest_ref", "manifest_path")
    def _serialize_ref(self, value: NonEmptyTextValue) -> dict[str, str]:
        return value.model_dump()

    @field_serializer("batches")
    def _serialize_batches(self, values: tuple[AgentAssetImportBatch, ...]) -> list[dict[str, object]]:
        return [value.model_dump(mode="json") for value in values]


class AgentAssetMaterializationResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    agent_asset_import_manifest_ref: AgentAssetImportManifestRef
    workspace_manifest_ref: WorkspaceManifestRef
    manifest_path: AgentAssetManifestPath
    materialized_source_refs: tuple[AgentAssetBundleSourceRef, ...]
    materialized_asset_refs: tuple[AgentAssetRef, ...]
    materialized_target_paths: tuple[AgentAssetTargetPath, ...]
    manifest_sha256: AgentAssetSha256

    @model_validator(mode="after")
    def _validate_result(self) -> Self:
        _require_unique_values((ref.value for ref in self.materialized_source_refs), "materialized_source_refs must be unique")
        _require_unique_values((ref.value for ref in self.materialized_asset_refs), "materialized_asset_refs must be unique")
        _require_unique_values((path.value for path in self.materialized_target_paths), "materialized_target_paths must be unique")
        return self

    @field_serializer(
        "agent_asset_import_manifest_ref",
        "workspace_manifest_ref",
        "manifest_path",
        "manifest_sha256",
    )
    def _serialize_ref(self, value: NonEmptyTextValue) -> dict[str, str]:
        return value.model_dump()

    @field_serializer("materialized_source_refs", "materialized_asset_refs", "materialized_target_paths")
    def _serialize_ref_tuple(self, values: tuple[NonEmptyTextValue, ...]) -> list[dict[str, str]]:
        return [value.model_dump() for value in values]


def validate_agent_asset_registry_bindings(
    *,
    manifest: AgentAssetImportManifest,
    role_profile_registry: RoleProfileRegistry,
    skill_file_registry: SkillFileSourceRegistry,
    prompt_registry: PromptSourceRegistry,
    mcp_interface_registry: McpInterfaceRegistry,
) -> None:
    for batch in manifest.batches:
        for entry in batch.entries:
            if entry.asset_kind is AgentAssetKind.ROLE_CONFIG:
                ref = RoleProfileId(value=entry.asset_ref.value)
                if not role_profile_registry.contains(ref):
                    raise AgentAssetImportError(f"unknown role asset_ref: {entry.asset_ref.value}")
            elif entry.asset_kind is AgentAssetKind.SKILL_FILE:
                ref = SkillFileRef(value=entry.asset_ref.value)
                if not skill_file_registry.contains(ref):
                    raise AgentAssetImportError(f"unknown skill_file asset_ref: {entry.asset_ref.value}")
            elif entry.asset_kind is AgentAssetKind.PROMPT_FILE:
                ref = PromptRef(value=entry.asset_ref.value)
                if not prompt_registry.contains(ref):
                    raise AgentAssetImportError(f"unknown prompt asset_ref: {entry.asset_ref.value}")
            elif entry.asset_kind is AgentAssetKind.MCP_INTERFACE_MANIFEST:
                ref = McpInterfaceRef(value=entry.asset_ref.value)
                if not mcp_interface_registry.contains(ref):
                    raise AgentAssetImportError(f"unknown mcp asset_ref: {entry.asset_ref.value}")


def dump_agent_asset_import_manifest(manifest: AgentAssetImportManifest) -> str:
    return json.dumps(
        manifest.model_dump(mode="json"),
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    ) + "\n"


def materialize_agent_assets(
    manifest: AgentAssetImportManifest,
    *,
    workspace_manifest: WorkspaceManifest,
    source_root: Path,
    workspace_root: Path,
    role_profile_registry: RoleProfileRegistry,
    skill_file_registry: SkillFileSourceRegistry,
    prompt_registry: PromptSourceRegistry,
    mcp_interface_registry: McpInterfaceRegistry,
) -> AgentAssetMaterializationResult:
    if workspace_manifest.workspace_manifest_id != manifest.workspace_manifest_ref:
        raise AgentAssetImportError("workspace_manifest_ref must match workspace_manifest.workspace_manifest_id")
    if not source_root.exists() or not source_root.is_dir():
        raise AgentAssetImportError("source_root must exist and be a directory")
    if not workspace_root.exists() or not workspace_root.is_dir():
        raise AgentAssetImportError("workspace_root must exist and be a directory")

    validate_agent_asset_registry_bindings(
        manifest=manifest,
        role_profile_registry=role_profile_registry,
        skill_file_registry=skill_file_registry,
        prompt_registry=prompt_registry,
        mcp_interface_registry=mcp_interface_registry,
    )

    source_root_resolved = source_root.resolve()
    workspace_root_resolved = workspace_root.resolve()
    agent_root_resolved = _resolve_under(workspace_root_resolved, _AGENT_ROOT, boundary_name="workspace")
    if agent_root_resolved.exists() and agent_root_resolved.resolve() != agent_root_resolved:
        raise AgentAssetImportError("workspace agent root must not escape workspace")
    manifest_file = _resolve_under(workspace_root_resolved, manifest.manifest_path.value, boundary_name="workspace")
    if not _is_relative_to(manifest_file, agent_root_resolved):
        raise AgentAssetImportError("manifest file must stay under 00-boardroom/agents")

    existing_manifest = _load_existing_manifest(manifest_file)
    pending_batches = _pending_batches(existing_manifest=existing_manifest, manifest=manifest)
    historical_batches = manifest.batches[: len(manifest.batches) - len(pending_batches)]

    for batch in historical_batches:
        for entry in batch.entries:
            _confirm_historical_entry(workspace_root_resolved=workspace_root_resolved, agent_root_resolved=agent_root_resolved, entry=entry)

    for batch in pending_batches:
        for entry in batch.entries:
            _materialize_new_entry(
                source_root_resolved=source_root_resolved,
                workspace_root_resolved=workspace_root_resolved,
                agent_root_resolved=agent_root_resolved,
                entry=entry,
            )

    manifest_sha256 = _write_manifest_file(manifest_file=manifest_file, manifest=manifest, existing_manifest=existing_manifest)
    entries = tuple(entry for batch in manifest.batches for entry in batch.entries)
    return AgentAssetMaterializationResult(
        agent_asset_import_manifest_ref=manifest.agent_asset_import_manifest_id,
        workspace_manifest_ref=manifest.workspace_manifest_ref,
        manifest_path=manifest.manifest_path,
        materialized_source_refs=tuple(batch.source_ref for batch in manifest.batches),
        materialized_asset_refs=tuple(entry.asset_ref for entry in entries),
        materialized_target_paths=tuple(entry.target_path for entry in entries),
        manifest_sha256=manifest_sha256,
    )


def _validate_relative_file_path(value: str, *, field_name: str) -> str:
    normalized = NonEmptyTextValue(value=value).value
    if "\\" in normalized:
        raise ValueError(f"{field_name} must use forward slashes")
    if normalized.endswith("/"):
        raise ValueError(f"{field_name} must name a file")
    if PurePosixPath(normalized).is_absolute() or PureWindowsPath(normalized).drive:
        raise ValueError(f"{field_name} must be relative")
    segments = normalized.split("/")
    if any(segment in {"", ".", ".."} for segment in segments):
        raise ValueError(f"{field_name} must not contain empty, current, or parent segments")
    return normalized


def _uses_reserved_repo_prefix(value: str) -> bool:
    return any(value == prefix or value.startswith(f"{prefix}/") for prefix in _REPO_LAYOUT_PREFIXES)


def _require_unique_values(values: object, message: str) -> None:
    collected = tuple(values)
    if len(collected) != len(set(collected)):
        raise ValueError(message)


def _load_existing_manifest(path: Path) -> AgentAssetImportManifest | None:
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return AgentAssetImportManifest.model_validate(raw)
    except Exception as exc:
        raise AgentAssetImportError("existing asset-import-manifest.yaml must be canonical JSON AgentAssetImportManifest") from exc


def _pending_batches(
    *,
    existing_manifest: AgentAssetImportManifest | None,
    manifest: AgentAssetImportManifest,
) -> tuple[AgentAssetImportBatch, ...]:
    if existing_manifest is None:
        return manifest.batches
    if existing_manifest.agent_asset_import_manifest_id != manifest.agent_asset_import_manifest_id:
        raise AgentAssetImportError("existing manifest id must match")
    if existing_manifest.workspace_manifest_ref != manifest.workspace_manifest_ref:
        raise AgentAssetImportError("existing manifest workspace_manifest_ref must match")
    if existing_manifest.manifest_path != manifest.manifest_path:
        raise AgentAssetImportError("existing manifest_path must match")
    if len(existing_manifest.batches) > len(manifest.batches):
        raise AgentAssetImportError("existing manifest must be a prefix of current manifest")
    for index, existing_batch in enumerate(existing_manifest.batches):
        if existing_batch != manifest.batches[index]:
            raise AgentAssetImportError("existing manifest historical batch must match prefix")
    return manifest.batches[len(existing_manifest.batches) :]


def _materialize_new_entry(
    *,
    source_root_resolved: Path,
    workspace_root_resolved: Path,
    agent_root_resolved: Path,
    entry: AgentAssetImportEntry,
) -> None:
    source_file = _resolve_under(source_root_resolved, entry.source_path.value, boundary_name="source")
    if source_file.is_symlink():
        raise AgentAssetImportError("source file must not be a symlink")
    if not source_file.exists() or not source_file.is_file():
        raise AgentAssetImportError("source file must exist and be a regular file")
    source_hash = _sha256_file(source_file)
    if source_hash != entry.sha256:
        raise AgentAssetImportError("source file sha256 does not match manifest entry")
    target_file = _resolve_target(workspace_root_resolved, agent_root_resolved, entry.target_path.value)
    if target_file.exists():
        if _sha256_file(target_file) != entry.sha256:
            raise AgentAssetImportError("target file exists with different sha256")
        return
    target_file.parent.mkdir(parents=True, exist_ok=True)
    target_file.write_bytes(source_file.read_bytes())


def _confirm_historical_entry(
    *,
    workspace_root_resolved: Path,
    agent_root_resolved: Path,
    entry: AgentAssetImportEntry,
) -> None:
    target_file = _resolve_target(workspace_root_resolved, agent_root_resolved, entry.target_path.value)
    if not target_file.exists() or not target_file.is_file():
        raise AgentAssetImportError("historical target file must exist")
    if _sha256_file(target_file) != entry.sha256:
        raise AgentAssetImportError("historical target file sha256 must match")


def _write_manifest_file(
    *,
    manifest_file: Path,
    manifest: AgentAssetImportManifest,
    existing_manifest: AgentAssetImportManifest | None,
) -> AgentAssetSha256:
    text = dump_agent_asset_import_manifest(manifest)
    if existing_manifest is not None and existing_manifest == manifest:
        existing_text = manifest_file.read_text(encoding="utf-8")
        if existing_text != text:
            raise AgentAssetImportError("existing manifest content must match canonical JSON")
        return _sha256_bytes(existing_text.encode("utf-8"))
    manifest_file.parent.mkdir(parents=True, exist_ok=True)
    manifest_file.write_text(text, encoding="utf-8")
    written_text = manifest_file.read_text(encoding="utf-8")
    if written_text != text:
        raise AgentAssetImportError("asset-import-manifest.yaml content mismatch after write")
    return _sha256_bytes(written_text.encode("utf-8"))


def _resolve_target(workspace_root_resolved: Path, agent_root_resolved: Path, relative_path: str) -> Path:
    target = _resolve_under(workspace_root_resolved, relative_path, boundary_name="workspace")
    if not _is_relative_to(target, agent_root_resolved):
        raise AgentAssetImportError("target file must stay under 00-boardroom/agents")
    return target


def _resolve_under(root: Path, relative_path: str, *, boundary_name: str) -> Path:
    root_resolved = root.resolve()
    resolved = (root_resolved / relative_path).resolve()
    if not _is_relative_to(resolved, root_resolved):
        raise AgentAssetImportError(f"{boundary_name} path escapes root")
    return resolved


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _sha256_file(path: Path) -> AgentAssetSha256:
    return _sha256_bytes(path.read_bytes())


def _sha256_bytes(content: bytes) -> AgentAssetSha256:
    return AgentAssetSha256(value=hashlib.sha256(content).hexdigest())


__all__ = [
    "AgentAssetBundleSourceKind",
    "AgentAssetBundleSourceRef",
    "AgentAssetImportBatch",
    "AgentAssetImportEntry",
    "AgentAssetImportError",
    "AgentAssetImportManifest",
    "AgentAssetImportManifestRef",
    "AgentAssetKind",
    "AgentAssetManifestPath",
    "AgentAssetMaterializationResult",
    "AgentAssetRef",
    "AgentAssetSha256",
    "AgentAssetSourcePath",
    "AgentAssetTargetPath",
    "dump_agent_asset_import_manifest",
    "materialize_agent_assets",
    "validate_agent_asset_registry_bindings",
]
