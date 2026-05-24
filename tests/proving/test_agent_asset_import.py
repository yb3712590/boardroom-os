from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from boardroom_os.agents.categories import RoleCategory
from boardroom_os.agents.profiles import RoleProfile, RoleProfileRegistry
from boardroom_os.agents.skills import (
    CapabilityDefinition,
    CapabilityRegistry,
    CapabilityTag,
    McpInterfaceDefinition,
    McpInterfaceRef,
    McpInterfaceRegistry,
    PromptRef,
    PromptSource,
    PromptSourceRegistry,
    RoleProfileId,
    SkillFileRef,
    SkillFileSource,
    SkillFileSourceRegistry,
)
from boardroom_os.contracts.types import ContractId
from boardroom_os.workspace.manifest import (
    WorkflowRef,
    WorkspaceManifest,
    WorkspaceManifestRef,
    WorkspacePath,
    WorkspaceSection,
    WorkspaceSectionPath,
)

_VERIFY_ERRORS = (ValueError, ValidationError)
_NOW = datetime(2026, 5, 23, 9, 41, tzinfo=UTC)


def _capability_registry() -> CapabilityRegistry:
    return CapabilityRegistry.from_definitions(
        CapabilityDefinition(
            capability_tag=CapabilityTag(value="task.implementation"),
            description="Implement assigned source changes.",
        ),
        CapabilityDefinition(
            capability_tag=CapabilityTag(value="role.worker"),
            description="Worker role capability.",
        ),
    )


def _role_registry(*, role_ref: str = "role.worker.v1") -> RoleProfileRegistry:
    return RoleProfileRegistry.from_profiles(
        RoleProfile(
            role_profile_id=RoleProfileId(value=role_ref),
            role_category=RoleCategory.IMPLEMENTATION,
            role_name="Worker",
            responsibilities=("Implement assigned work.",),
            capability_tags=(
                CapabilityTag(value="task.implementation"),
                CapabilityTag(value="role.worker"),
            ),
            input_contracts=(ContractId(value="contract.execution-package"),),
            output_contracts=(ContractId(value="contract.work-product"),),
            forbidden_actions=("complete tickets directly",),
        ),
        capability_registry=_capability_registry(),
    )


def _skill_file_registry(*, skill_ref: str = "skill.worker.v1") -> SkillFileSourceRegistry:
    return SkillFileSourceRegistry.from_sources(
        SkillFileSource(
            skill_file_ref=SkillFileRef(value=skill_ref),
            skill_file_path="00-boardroom/agents/skills/worker.md",
            skill_kind="claude_code_skill",
            required_sections=("purpose", "inputs", "outputs"),
        )
    )


def _prompt_registry(*, prompt_refs: tuple[str, ...] = ("prompt.worker.v1",)) -> PromptSourceRegistry:
    return PromptSourceRegistry.from_sources(
        *(
            PromptSource(
                prompt_ref=PromptRef(value=prompt_ref),
                prompt_path=f"00-boardroom/agents/prompts/{prompt_ref.split('.')[-2]}.md",
                prompt_kind="system",
                required_variables=("execution_package",),
            )
            for prompt_ref in prompt_refs
        )
    )


def _mcp_registry(*, mcp_ref: str = "mcp.filesystem.read.v1") -> McpInterfaceRegistry:
    return McpInterfaceRegistry.from_interfaces(
        McpInterfaceDefinition(
            mcp_interface_ref=McpInterfaceRef(value=mcp_ref),
            server_ref="mcp.filesystem",
            tool_name="read_file",
            allowed_operations=("read",),
            required_capability_tags=(CapabilityTag(value="task.implementation"),),
        ),
        capability_registry=_capability_registry(),
    )


def _registries(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "role_profile_registry": _role_registry(),
        "skill_file_registry": _skill_file_registry(),
        "prompt_registry": _prompt_registry(),
        "mcp_interface_registry": _mcp_registry(),
    }
    values.update(overrides)
    return values


def _workspace_manifest(workflow_ref: str = "workflow.agent-assets") -> WorkspaceManifest:
    return WorkspaceManifest(
        workspace_manifest_id=WorkspaceManifestRef(value=f"workspace-manifest.{workflow_ref}"),
        workflow_ref=WorkflowRef(value=workflow_ref),
        workspace_root=WorkspacePath(value=f"workspaces/{workflow_ref}"),
        package_contract_ref=ContractId(value="package-contract.agent-assets"),
        sections=(
            WorkspaceSectionPath(section=WorkspaceSection.BOARDROOM, relative_path=WorkspacePath(value="00-boardroom")),
            WorkspaceSectionPath(section=WorkspaceSection.PROJECT, relative_path=WorkspacePath(value="10-project")),
            WorkspaceSectionPath(section=WorkspaceSection.EVIDENCE, relative_path=WorkspacePath(value="20-evidence")),
            WorkspaceSectionPath(section=WorkspaceSection.AUDIT, relative_path=WorkspacePath(value="30-audit")),
        ),
    )


def _write_file(root: Path, relative_path: str, content: bytes) -> str:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return hashlib.sha256(content).hexdigest()


def _write_source_bundle(source_root: Path, *, include_mcp: bool = True, extra_prompt: bool = False) -> dict[str, str]:
    hashes = {
        "role": _write_file(source_root, "roles/worker.yaml", b"role: worker\n"),
        "skill": _write_file(source_root, "skills/worker.md", b"# Worker skill\n"),
        "prompt": _write_file(source_root, "prompts/worker.md", b"You are a worker.\n"),
    }
    if include_mcp:
        hashes["mcp"] = _write_file(source_root, "mcp/filesystem.yaml", b"tool: read_file\n")
    if extra_prompt:
        hashes["extra_prompt"] = _write_file(source_root, "prompts/reviewer.md", b"You are a reviewer.\n")
    return hashes


def _entry(kind: str, *, sha256: str, asset_ref: str | None = None, source_path: str | None = None, target_path: str | None = None):
    from boardroom_os.workspace.agent_asset_import import (
        AgentAssetImportEntry,
        AgentAssetKind,
        AgentAssetRef,
        AgentAssetSha256,
        AgentAssetSourcePath,
        AgentAssetTargetPath,
    )

    defaults = {
        "role_config": ("role.worker.v1", "roles/worker.yaml", "00-boardroom/agents/roles/worker.yaml"),
        "skill_file": ("skill.worker.v1", "skills/worker.md", "00-boardroom/agents/skills/worker.md"),
        "prompt_file": ("prompt.worker.v1", "prompts/worker.md", "00-boardroom/agents/prompts/worker.md"),
        "mcp_interface_manifest": (
            "mcp.filesystem.read.v1",
            "mcp/filesystem.yaml",
            "00-boardroom/agents/mcp/filesystem.yaml",
        ),
    }
    default_ref, default_source, default_target = defaults[kind]
    return AgentAssetImportEntry(
        asset_ref=AgentAssetRef(value=asset_ref or default_ref),
        asset_kind=AgentAssetKind(kind),
        source_path=AgentAssetSourcePath(value=source_path or default_source),
        target_path=AgentAssetTargetPath(value=target_path or default_target),
        sha256=AgentAssetSha256(value=sha256),
    )


def _batch(*, source_ref: str = "agent-assets.initial.v1", entries: tuple[object, ...], imported_at: datetime = _NOW):
    from boardroom_os.workspace.agent_asset_import import AgentAssetBundleSourceKind, AgentAssetBundleSourceRef, AgentAssetImportBatch

    return AgentAssetImportBatch(
        source_ref=AgentAssetBundleSourceRef(value=source_ref),
        source_kind=AgentAssetBundleSourceKind.LOCAL_BUNDLE,
        imported_at=imported_at,
        entries=entries,
    )


def _manifest(workspace_manifest: WorkspaceManifest, *, batches: tuple[object, ...]):
    from boardroom_os.workspace.agent_asset_import import (
        AgentAssetImportManifest,
        AgentAssetImportManifestRef,
        AgentAssetManifestPath,
    )

    return AgentAssetImportManifest(
        agent_asset_import_manifest_id=AgentAssetImportManifestRef(
            value=f"agent-asset-import.{workspace_manifest.workspace_manifest_id.value}"
        ),
        workspace_manifest_ref=workspace_manifest.workspace_manifest_id,
        manifest_path=AgentAssetManifestPath(value="00-boardroom/agents/asset-import-manifest.yaml"),
        batches=batches,
    )


def _full_manifest(source_root: Path, *, include_mcp: bool = True) -> AgentAssetImportManifest:
    hashes = _write_source_bundle(source_root, include_mcp=include_mcp)
    entries = (
        _entry("role_config", sha256=hashes["role"]),
        _entry("skill_file", sha256=hashes["skill"]),
        _entry("prompt_file", sha256=hashes["prompt"]),
    )
    if include_mcp:
        entries = (*entries, _entry("mcp_interface_manifest", sha256=hashes["mcp"]))
    return _manifest(_workspace_manifest(), batches=(_batch(entries=tuple(sorted(entries, key=lambda entry: entry.target_path.value))),))


def _materialize(manifest, source_root: Path, workspace_root: Path, **registry_overrides: object):
    from boardroom_os.workspace.agent_asset_import import materialize_agent_assets

    return materialize_agent_assets(
        manifest,
        workspace_manifest=_workspace_manifest(),
        source_root=source_root,
        workspace_root=workspace_root,
        **_registries(**registry_overrides),
    )


def _workspace_root(tmp_path: Path) -> Path:
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir(parents=True, exist_ok=True)
    return workspace_root


def _source_root(tmp_path: Path) -> Path:
    source_root = tmp_path / "source"
    source_root.mkdir(parents=True, exist_ok=True)
    return source_root


def test_agent_asset_import_manifest_rejects_missing_workspace_manifest_ref_or_batches(tmp_path: Path) -> None:
    from boardroom_os.workspace.agent_asset_import import AgentAssetImportManifest

    manifest = _full_manifest(_source_root(tmp_path))
    for field_name in ("workspace_manifest_ref", "batches"):
        data = manifest.model_dump(mode="json")
        data.pop(field_name)
        with pytest.raises(_VERIFY_ERRORS, match=field_name):
            AgentAssetImportManifest.model_validate(data)


def test_agent_asset_import_manifest_rejects_missing_or_wrong_manifest_path(tmp_path: Path) -> None:
    from boardroom_os.workspace.agent_asset_import import AgentAssetImportManifest

    data = _full_manifest(_source_root(tmp_path)).model_dump(mode="json")
    data.pop("manifest_path")
    with pytest.raises(_VERIFY_ERRORS, match="manifest_path"):
        AgentAssetImportManifest.model_validate(data)

    data = _full_manifest(_source_root(tmp_path)).model_dump(mode="json")
    data["manifest_path"] = {"value": "00-boardroom/agents/other.yaml"}
    with pytest.raises(_VERIFY_ERRORS, match="asset-import-manifest"):
        AgentAssetImportManifest.model_validate(data)


def test_agent_asset_import_batch_rejects_missing_source_ref_source_kind_or_imported_at(tmp_path: Path) -> None:
    from boardroom_os.workspace.agent_asset_import import AgentAssetImportBatch

    batch = _full_manifest(_source_root(tmp_path)).batches[0]
    for field_name in ("source_ref", "source_kind", "imported_at"):
        data = batch.model_dump(mode="json")
        data.pop(field_name)
        with pytest.raises(_VERIFY_ERRORS, match=field_name):
            AgentAssetImportBatch.model_validate(data)


def test_agent_asset_import_batch_rejects_naive_imported_at(tmp_path: Path) -> None:
    from boardroom_os.workspace.agent_asset_import import AgentAssetImportBatch

    data = _full_manifest(_source_root(tmp_path)).batches[0].model_dump(mode="json")
    data["imported_at"] = "2026-05-23T09:41:00"
    with pytest.raises(_VERIFY_ERRORS, match="timezone"):
        AgentAssetImportBatch.model_validate(data)


def test_agent_asset_import_manifest_allows_subset_of_asset_kinds(tmp_path: Path) -> None:
    manifest = _full_manifest(_source_root(tmp_path), include_mcp=False)

    assert [entry.asset_kind.value for entry in manifest.batches[0].entries] == ["prompt_file", "role_config", "skill_file"]


def test_agent_asset_import_entry_rejects_missing_source_path_target_path_or_sha256(tmp_path: Path) -> None:
    from boardroom_os.workspace.agent_asset_import import AgentAssetImportEntry

    entry = _full_manifest(_source_root(tmp_path)).batches[0].entries[0]
    for field_name in ("source_path", "target_path", "sha256"):
        data = entry.model_dump(mode="json")
        data.pop(field_name)
        with pytest.raises(_VERIFY_ERRORS, match=field_name):
            AgentAssetImportEntry.model_validate(data)


@pytest.mark.parametrize("path", ("/roles/worker.yaml", "C:/roles/worker.yaml", "roles\\worker.yaml"))
def test_agent_asset_paths_reject_absolute_windows_drive_and_backslash(path: str) -> None:
    from boardroom_os.workspace.agent_asset_import import AgentAssetSourcePath, AgentAssetTargetPath

    with pytest.raises(_VERIFY_ERRORS):
        AgentAssetSourcePath(value=path)
    with pytest.raises(_VERIFY_ERRORS):
        AgentAssetTargetPath(value=path.replace("roles", "00-boardroom/agents/roles"))


@pytest.mark.parametrize(
    "path",
    (
        "roles/../worker.yaml",
        "roles/./worker.yaml",
        "roles//worker.yaml",
        "roles/",
        "00-boardroom/agents/roles/worker.yaml",
        "10-project/prompts/worker.md",
        "src/boardroom_os/agents/worker.md",
        "doc/worker.md",
    ),
)
def test_agent_asset_paths_reject_escape_current_parent_empty_or_workspace_misuse(path: str) -> None:
    from boardroom_os.workspace.agent_asset_import import AgentAssetSourcePath

    with pytest.raises(_VERIFY_ERRORS):
        AgentAssetSourcePath(value=path)


def test_agent_asset_target_path_must_stay_under_boardroom_agents() -> None:
    from boardroom_os.workspace.agent_asset_import import AgentAssetTargetPath

    for path in ("10-project/roles/worker.yaml", "00-boardroom/other/worker.yaml", "20-evidence/worker.yaml"):
        with pytest.raises(_VERIFY_ERRORS, match="00-boardroom/agents"):
            AgentAssetTargetPath(value=path)


def test_agent_asset_target_path_must_match_asset_kind_prefix(tmp_path: Path) -> None:
    hashes = _write_source_bundle(_source_root(tmp_path))

    with pytest.raises(_VERIFY_ERRORS, match="target_path"):
        _entry(
            "prompt_file",
            sha256=hashes["prompt"],
            target_path="00-boardroom/agents/roles/worker.yaml",
        )


@pytest.mark.parametrize("sha256", ("", "abc", "A" * 64, "g" * 64, "sha256:" + "a" * 64, "a" * 63))
def test_agent_asset_sha256_must_be_lowercase_hex_digest(sha256: str) -> None:
    from boardroom_os.workspace.agent_asset_import import AgentAssetSha256

    with pytest.raises(_VERIFY_ERRORS, match="sha256"):
        AgentAssetSha256(value=sha256)


def test_agent_asset_import_manifest_rejects_duplicate_asset_source_or_target_refs_within_batch(tmp_path: Path) -> None:
    hashes = _write_source_bundle(_source_root(tmp_path))
    role_entry = _entry("role_config", sha256=hashes["role"])
    other_role = _entry(
        "role_config",
        sha256=hashes["role"],
        asset_ref="role.worker.v2",
        source_path="roles/worker-v2.yaml",
        target_path="00-boardroom/agents/roles/worker-v2.yaml",
    )

    for duplicated_entries in (
        (role_entry, role_entry),
        (role_entry, other_role.model_copy(update={"source_path": role_entry.source_path})),
        (role_entry, other_role.model_copy(update={"target_path": role_entry.target_path})),
    ):
        with pytest.raises(_VERIFY_ERRORS, match="unique"):
            _batch(entries=duplicated_entries)


def test_agent_asset_import_manifest_rejects_redefined_source_ref_or_mutated_historical_asset(tmp_path: Path) -> None:
    hashes = _write_source_bundle(_source_root(tmp_path))
    role_entry = _entry("role_config", sha256=hashes["role"])
    batch_a = _batch(source_ref="agent-assets.a.v1", entries=(role_entry,))
    batch_redefined = _batch(source_ref="agent-assets.a.v1", entries=(role_entry,))

    with pytest.raises(_VERIFY_ERRORS, match="source_ref"):
        _manifest(_workspace_manifest(), batches=(batch_a, batch_redefined))

    mutated_entry = _entry("role_config", sha256="a" * 64)
    batch_b = _batch(source_ref="agent-assets.b.v1", entries=(mutated_entry,))
    with pytest.raises(_VERIFY_ERRORS, match="asset_ref|target_path"):
        _manifest(_workspace_manifest(), batches=(batch_a, batch_b))


def test_registry_binding_rejects_role_asset_ref_missing_from_role_registry(tmp_path: Path) -> None:
    from boardroom_os.workspace.agent_asset_import import AgentAssetImportError, validate_agent_asset_registry_bindings

    manifest = _full_manifest(_source_root(tmp_path))
    with pytest.raises(AgentAssetImportError, match="role.worker.v1"):
        validate_agent_asset_registry_bindings(
            manifest=manifest,
            **_registries(role_profile_registry=_role_registry(role_ref="role.other.v1")),
        )


def test_registry_binding_rejects_skill_file_ref_missing_from_skill_file_registry(tmp_path: Path) -> None:
    from boardroom_os.workspace.agent_asset_import import AgentAssetImportError, validate_agent_asset_registry_bindings

    manifest = _full_manifest(_source_root(tmp_path))
    with pytest.raises(AgentAssetImportError, match="skill.worker.v1"):
        validate_agent_asset_registry_bindings(
            manifest=manifest,
            **_registries(skill_file_registry=_skill_file_registry(skill_ref="skill.other.v1")),
        )


def test_registry_binding_rejects_prompt_ref_missing_from_prompt_registry(tmp_path: Path) -> None:
    from boardroom_os.workspace.agent_asset_import import AgentAssetImportError, validate_agent_asset_registry_bindings

    manifest = _full_manifest(_source_root(tmp_path))
    with pytest.raises(AgentAssetImportError, match="prompt.worker.v1"):
        validate_agent_asset_registry_bindings(
            manifest=manifest,
            **_registries(prompt_registry=_prompt_registry(prompt_refs=("prompt.other.v1",))),
        )


def test_registry_binding_rejects_mcp_ref_missing_from_mcp_registry(tmp_path: Path) -> None:
    from boardroom_os.workspace.agent_asset_import import AgentAssetImportError, validate_agent_asset_registry_bindings

    manifest = _full_manifest(_source_root(tmp_path))
    with pytest.raises(AgentAssetImportError, match="mcp.filesystem.read.v1"):
        validate_agent_asset_registry_bindings(
            manifest=manifest,
            **_registries(mcp_interface_registry=_mcp_registry(mcp_ref="mcp.other.read.v1")),
        )


def test_materializer_rejects_unbound_asset_before_file_io(tmp_path: Path) -> None:
    from boardroom_os.workspace.agent_asset_import import AgentAssetImportError

    source_root = _source_root(tmp_path)
    workspace_root = _workspace_root(tmp_path)
    manifest = _full_manifest(source_root)

    with pytest.raises(AgentAssetImportError, match="role.worker.v1"):
        _materialize(manifest, source_root, workspace_root, role_profile_registry=_role_registry(role_ref="role.other.v1"))

    assert not (workspace_root / "00-boardroom").exists()


def test_materializer_rejects_workspace_manifest_ref_mismatch(tmp_path: Path) -> None:
    from boardroom_os.workspace.agent_asset_import import AgentAssetImportError, materialize_agent_assets

    source_root = _source_root(tmp_path)
    workspace_root = _workspace_root(tmp_path)
    manifest = _full_manifest(source_root)

    with pytest.raises(AgentAssetImportError, match="workspace_manifest_ref"):
        materialize_agent_assets(
            manifest,
            workspace_manifest=_workspace_manifest("workflow.other"),
            source_root=source_root,
            workspace_root=workspace_root,
            **_registries(),
        )


def test_materializer_rejects_missing_source_file_for_new_batch(tmp_path: Path) -> None:
    from boardroom_os.workspace.agent_asset_import import AgentAssetImportError

    source_root = _source_root(tmp_path)
    workspace_root = _workspace_root(tmp_path)
    manifest = _full_manifest(source_root)
    (source_root / "roles/worker.yaml").unlink()

    with pytest.raises(AgentAssetImportError, match="source file"):
        _materialize(manifest, source_root, workspace_root)


def test_materializer_rejects_source_directory_or_symlink(tmp_path: Path) -> None:
    from boardroom_os.workspace.agent_asset_import import AgentAssetImportError

    source_root = _source_root(tmp_path)
    workspace_root = _workspace_root(tmp_path)
    manifest = _full_manifest(source_root)
    role_path = source_root / "roles/worker.yaml"
    role_path.unlink()
    role_path.mkdir()

    with pytest.raises(AgentAssetImportError, match="regular file"):
        _materialize(manifest, source_root, workspace_root)

    symlink_source = _source_root(tmp_path / "symlink-case")
    symlink_workspace = _workspace_root(tmp_path / "symlink-case")
    symlink_manifest = _full_manifest(symlink_source)
    symlink_path = symlink_source / "roles/worker.yaml"
    symlink_path.unlink()
    try:
        symlink_path.symlink_to(symlink_source / "skills/worker.md")
    except OSError:
        pytest.skip("symlink creation is unavailable on this platform")

    with pytest.raises(AgentAssetImportError, match="symlink"):
        _materialize(symlink_manifest, symlink_source, symlink_workspace)


def test_materializer_rejects_source_hash_mismatch(tmp_path: Path) -> None:
    from boardroom_os.workspace.agent_asset_import import AgentAssetImportError

    source_root = _source_root(tmp_path)
    workspace_root = _workspace_root(tmp_path)
    _write_source_bundle(source_root)
    bad_entry = _entry("role_config", sha256="a" * 64)
    manifest = _manifest(_workspace_manifest(), batches=(_batch(entries=(bad_entry,)),))

    with pytest.raises(AgentAssetImportError, match="sha256"):
        _materialize(manifest, source_root, workspace_root)


def test_materializer_rejects_existing_target_with_different_hash(tmp_path: Path) -> None:
    from boardroom_os.workspace.agent_asset_import import AgentAssetImportError

    source_root = _source_root(tmp_path)
    workspace_root = _workspace_root(tmp_path)
    manifest = _full_manifest(source_root)
    target = workspace_root / "00-boardroom/agents/roles/worker.yaml"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"different\n")

    with pytest.raises(AgentAssetImportError, match="target file"):
        _materialize(manifest, source_root, workspace_root)


def test_materializer_rejects_existing_manifest_that_is_not_prefix(tmp_path: Path) -> None:
    from boardroom_os.workspace.agent_asset_import import AgentAssetImportError, dump_agent_asset_import_manifest

    source_root = _source_root(tmp_path)
    workspace_root = _workspace_root(tmp_path)
    manifest = _full_manifest(source_root)
    other_manifest = _manifest(
        _workspace_manifest(),
        batches=(_batch(source_ref="agent-assets.other.v1", entries=manifest.batches[0].entries),),
    )
    manifest_path = workspace_root / "00-boardroom/agents/asset-import-manifest.yaml"
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_text(dump_agent_asset_import_manifest(other_manifest), encoding="utf-8")

    with pytest.raises(AgentAssetImportError, match="prefix"):
        _materialize(manifest, source_root, workspace_root)


def test_materializer_rejects_existing_manifest_with_mutated_historical_batch(tmp_path: Path) -> None:
    from boardroom_os.workspace.agent_asset_import import AgentAssetImportError

    source_root = _source_root(tmp_path)
    workspace_root = _workspace_root(tmp_path)
    manifest = _full_manifest(source_root)
    _materialize(manifest, source_root, workspace_root)
    mutated_entry = manifest.batches[0].entries[0].model_copy(update={"sha256": type(manifest.batches[0].entries[0].sha256)(value="a" * 64)})
    mutated_batch = manifest.batches[0].model_copy(update={"entries": (mutated_entry, *manifest.batches[0].entries[1:])})
    mutated_manifest = manifest.model_copy(update={"batches": (mutated_batch,)})

    with pytest.raises(AgentAssetImportError, match="historical|prefix"):
        _materialize(mutated_manifest, source_root, workspace_root)


def test_materializer_rejects_source_root_or_workspace_root_missing(tmp_path: Path) -> None:
    from boardroom_os.workspace.agent_asset_import import AgentAssetImportError

    source_root = _source_root(tmp_path)
    workspace_root = _workspace_root(tmp_path)
    manifest = _full_manifest(source_root)

    with pytest.raises(AgentAssetImportError, match="source_root"):
        _materialize(manifest, tmp_path / "missing-source", workspace_root)
    with pytest.raises(AgentAssetImportError, match="workspace_root"):
        _materialize(manifest, source_root, tmp_path / "missing-workspace")


def test_materializer_does_not_write_outside_boardroom_agents(tmp_path: Path) -> None:
    from boardroom_os.workspace.agent_asset_import import AgentAssetImportError

    source_root = _source_root(tmp_path)
    workspace_root = _workspace_root(tmp_path)
    outside_root = tmp_path / "outside"
    outside_root.mkdir()
    manifest = _full_manifest(source_root)
    boardroom_path = workspace_root / "00-boardroom"
    try:
        boardroom_path.symlink_to(outside_root, target_is_directory=True)
    except OSError:
        pytest.skip("symlink creation is unavailable on this platform")

    with pytest.raises(AgentAssetImportError, match="workspace"):
        _materialize(manifest, source_root, workspace_root)


def test_materializer_rejects_missing_or_changed_historical_target(tmp_path: Path) -> None:
    from boardroom_os.workspace.agent_asset_import import AgentAssetImportError

    source_root = _source_root(tmp_path)
    workspace_root = _workspace_root(tmp_path)
    manifest = _full_manifest(source_root)
    _materialize(manifest, source_root, workspace_root)
    target = workspace_root / "00-boardroom/agents/roles/worker.yaml"
    target.unlink()

    with pytest.raises(AgentAssetImportError, match="historical target"):
        _materialize(manifest, source_root, workspace_root)


def test_materializer_imports_local_agent_asset_bundle_into_boardroom_agents_snapshot(tmp_path: Path) -> None:
    source_root = _source_root(tmp_path)
    workspace_root = _workspace_root(tmp_path)
    manifest = _full_manifest(source_root)

    result = _materialize(manifest, source_root, workspace_root)

    assert (workspace_root / "00-boardroom/agents/roles/worker.yaml").read_bytes() == b"role: worker\n"
    assert (workspace_root / "00-boardroom/agents/skills/worker.md").read_bytes() == b"# Worker skill\n"
    assert (workspace_root / "00-boardroom/agents/prompts/worker.md").read_bytes() == b"You are a worker.\n"
    assert (workspace_root / "00-boardroom/agents/mcp/filesystem.yaml").read_bytes() == b"tool: read_file\n"
    manifest_text = (workspace_root / "00-boardroom/agents/asset-import-manifest.yaml").read_text(encoding="utf-8")
    assert str(source_root) not in manifest_text
    assert str(workspace_root) not in manifest_text
    assert result.materialized_asset_refs == tuple(entry.asset_ref for entry in manifest.batches[0].entries)
    assert result.manifest_sha256.value == hashlib.sha256(manifest_text.encode("utf-8")).hexdigest()


def test_materializer_allows_project_asset_kind_subset_without_mcp_asset(tmp_path: Path) -> None:
    source_root = _source_root(tmp_path)
    workspace_root = _workspace_root(tmp_path)
    manifest = _full_manifest(source_root, include_mcp=False)

    result = _materialize(manifest, source_root, workspace_root)

    assert tuple(ref.value for ref in result.materialized_asset_refs) == (
        "prompt.worker.v1",
        "role.worker.v1",
        "skill.worker.v1",
    )
    assert not (workspace_root / "00-boardroom/agents/mcp/filesystem.yaml").exists()


def test_materializer_is_idempotent_when_manifest_is_identical(tmp_path: Path) -> None:
    source_root = _source_root(tmp_path)
    workspace_root = _workspace_root(tmp_path)
    manifest = _full_manifest(source_root)

    first = _materialize(manifest, source_root, workspace_root)
    second = _materialize(manifest, source_root, workspace_root)

    assert second.model_dump() == first.model_dump()


def test_materializer_appends_new_source_ref_batch_without_rewriting_history(tmp_path: Path) -> None:
    source_root = _source_root(tmp_path)
    workspace_root = _workspace_root(tmp_path)
    hashes = _write_source_bundle(source_root, include_mcp=False, extra_prompt=True)
    role_entry = _entry("role_config", sha256=hashes["role"])
    batch_a = _batch(source_ref="agent-assets.a.v1", entries=(role_entry,))
    manifest_a = _manifest(_workspace_manifest(), batches=(batch_a,))
    _materialize(manifest_a, source_root, workspace_root, prompt_registry=_prompt_registry(prompt_refs=("prompt.worker.v1", "prompt.reviewer.v1")))
    role_target = workspace_root / "00-boardroom/agents/roles/worker.yaml"
    role_bytes = role_target.read_bytes()

    prompt_entry = _entry(
        "prompt_file",
        sha256=hashes["extra_prompt"],
        asset_ref="prompt.reviewer.v1",
        source_path="prompts/reviewer.md",
        target_path="00-boardroom/agents/prompts/reviewer.md",
    )
    batch_b = _batch(source_ref="agent-assets.b.v1", entries=(prompt_entry,))
    manifest_b = _manifest(_workspace_manifest(), batches=(batch_a, batch_b))
    result = _materialize(manifest_b, source_root, workspace_root, prompt_registry=_prompt_registry(prompt_refs=("prompt.worker.v1", "prompt.reviewer.v1")))

    manifest_json = json.loads((workspace_root / "00-boardroom/agents/asset-import-manifest.yaml").read_text(encoding="utf-8"))
    assert role_target.read_bytes() == role_bytes
    assert (workspace_root / "00-boardroom/agents/prompts/reviewer.md").read_bytes() == b"You are a reviewer.\n"
    assert [batch["source_ref"]["value"] for batch in manifest_json["batches"]] == ["agent-assets.a.v1", "agent-assets.b.v1"]
    assert tuple(ref.value for ref in result.materialized_source_refs) == ("agent-assets.a.v1", "agent-assets.b.v1")


def test_agent_asset_import_manifest_model_dump_is_stable_and_audit_friendly(tmp_path: Path) -> None:
    from boardroom_os.workspace.agent_asset_import import dump_agent_asset_import_manifest

    source_root = _source_root(tmp_path)
    manifest = _full_manifest(source_root)

    first = dump_agent_asset_import_manifest(manifest)
    second = dump_agent_asset_import_manifest(manifest)
    dumped = json.loads(first)

    assert first == second
    assert first.endswith("\n")
    assert first == json.dumps(dumped, sort_keys=True, ensure_ascii=False, separators=(",", ":")) + "\n"
    assert [entry["target_path"]["value"] for entry in dumped["batches"][0]["entries"]] == sorted(
        entry["target_path"]["value"] for entry in dumped["batches"][0]["entries"]
    )
    assert dumped["batches"][0]["imported_at"].endswith("Z")
    assert str(source_root) not in first
    assert "source_path" in first and "target_path" in first and "sha256" in first
