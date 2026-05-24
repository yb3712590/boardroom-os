# V2-060F AgentAssetImport（智能体资产导入）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development（子代理驱动开发，推荐） or superpowers:executing-plans（按计划执行） to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement V2-060F AgentAssetImport（智能体资产导入） so local role config（角色配置）, skill file（技能文件）, prompt file（提示词文件）, and MCP interface manifest（MCP 接口清单） assets can be materialized into a generated project workspace（生成项目工作区） under `00-boardroom/agents/`, with a cumulative `asset-import-manifest.yaml`（资产导入清单） that preserves source lineage（来源链） and keeps ExecutionPackage compiler（执行包编译器） at 0 external file inputs.

**Architecture:** Add one focused workspace module, `src/boardroom_os/workspace/agent_asset_import.py`, containing typed import manifest models, registry binding validation（注册表绑定校验）, canonical JSON manifest dumping（规范 JSON 清单导出）, and the narrow `materialize_agent_assets`（物化智能体资产函数） filesystem boundary. The model layer is pure and fail-closed; the materializer is the only code that reads source bytes or writes workspace files.

**Tech Stack:** Python 3, Pydantic BaseModel（Pydantic 模型）, pytest, `pathlib.Path`, `hashlib.sha256`, existing WorkspaceManifest（工作区清单）, RoleProfileRegistry（角色模板注册表）, SkillFileSourceRegistry（技能文件来源注册表）, PromptSourceRegistry（提示词来源注册表）, and McpInterfaceRegistry（MCP 接口注册表） models.

---

## File Structure

- Create `src/boardroom_os/workspace/agent_asset_import.py`
  - Own `AgentAssetImportError`（智能体资产导入错误）, value objects, `AgentAssetKind`（智能体资产类型）, `AgentAssetImportEntry`（智能体资产导入条目）, `AgentAssetImportBatch`（智能体资产导入批次）, `AgentAssetImportManifest`（智能体资产导入清单）, `AgentAssetMaterializationResult`（智能体资产物化结果）, `validate_agent_asset_registry_bindings`（校验智能体资产注册表绑定函数）, `dump_agent_asset_import_manifest`（导出资产导入清单函数）, and `materialize_agent_assets`（物化智能体资产函数）.
  - Import typed facts from `agents`, `contracts.types`, and `workspace.manifest` only.
  - Do not import ExecutionPackage compiler（执行包编译器）, provider executor（模型执行器）, runtime executor（运行时执行器）, CommandRunner（命令执行器）, closeout（收尾）, git adapters（Git 适配器）, or legacy implementation.
- Create `tests/proving/test_agent_asset_import.py`
  - Write backlog-required negative tests first.
  - Cover optional asset kinds（按需资产类型）, registry binding（注册表绑定）, prefix append（前缀追加）, idempotency（幂等）, canonical JSON（规范 JSON）, and filesystem materialization（文件系统物化）.
- Modify `src/boardroom_os/workspace/__init__.py`
  - Export the V2-060F public API.
- Modify `doc/04-implementation/INDEX.md`
  - Add this implementation plan entry.
- Modify after implementation verification only:
  - `doc/04-implementation/backlog.md`
  - `doc/04-implementation/acceptance-criteria.md`
  - `doc/05-project-log/2026-05.md`

---

### Task 1: Add fail-closed tests and fixtures

**Files:**
- Create: `tests/proving/test_agent_asset_import.py`
- No production code yet.

- [ ] **Step 1: Add common fixtures**

Create fixture helpers that construct:

- `WorkspaceManifest`（工作区清单） via `build_workspace_manifest(...)`.
- `RoleProfileRegistry`（角色模板注册表） with one `RoleProfileId(value="role.worker.v1")`.
- `SkillFileSourceRegistry`（技能文件来源注册表） with one `SkillFileRef(value="skill.worker.v1")`.
- `PromptSourceRegistry`（提示词来源注册表） with one `PromptRef(value="prompt.worker.v1")`.
- `McpInterfaceRegistry`（MCP 接口注册表） with one `McpInterfaceRef(value="mcp.filesystem.read.v1")`.
- `tmp_path` source bundle files under `roles/`, `skills/`, `prompts/`, and `mcp/`.
- Helper `_sha256(path: Path) -> str` that hashes real bytes.
- Helper `_manifest(...)` that returns an `AgentAssetImportManifest`（智能体资产导入清单） with stable timezone-aware `imported_at`（导入时间）.

Use existing V2-030A fixture style from `tests/execution/test_agent_profiles.py`.

- [ ] **Step 2: Add model-layer negative tests**

Add tests in this order:

```python
def test_agent_asset_import_manifest_rejects_missing_workspace_manifest_ref_or_batches() -> None: ...
def test_agent_asset_import_manifest_rejects_missing_or_wrong_manifest_path() -> None: ...
def test_agent_asset_import_batch_rejects_missing_source_ref_source_kind_or_imported_at() -> None: ...
def test_agent_asset_import_batch_rejects_naive_imported_at() -> None: ...
def test_agent_asset_import_manifest_allows_subset_of_asset_kinds() -> None: ...
def test_agent_asset_import_entry_rejects_missing_source_path_target_path_or_sha256() -> None: ...
def test_agent_asset_paths_reject_absolute_windows_drive_and_backslash() -> None: ...
def test_agent_asset_paths_reject_escape_current_parent_empty_or_workspace_misuse() -> None: ...
def test_agent_asset_target_path_must_stay_under_boardroom_agents() -> None: ...
def test_agent_asset_target_path_must_match_asset_kind_prefix() -> None: ...
def test_agent_asset_sha256_must_be_lowercase_hex_digest() -> None: ...
def test_agent_asset_import_manifest_rejects_duplicate_asset_source_or_target_refs_within_batch() -> None: ...
def test_agent_asset_import_manifest_rejects_redefined_source_ref_or_mutated_historical_asset() -> None: ...
```

Expected model behavior:

- `entries` can contain only the asset kinds actually used by the project.
- Four-kind coverage is not a model invariant.
- Reusing a registry ref with different bytes or target path across batches fails; content evolution requires a new ref.

- [ ] **Step 3: Add registry binding negative tests**

Add tests:

```python
def test_registry_binding_rejects_role_asset_ref_missing_from_role_registry() -> None: ...
def test_registry_binding_rejects_skill_file_ref_missing_from_skill_file_registry() -> None: ...
def test_registry_binding_rejects_prompt_ref_missing_from_prompt_registry() -> None: ...
def test_registry_binding_rejects_mcp_ref_missing_from_mcp_registry() -> None: ...
def test_materializer_rejects_unbound_asset_before_file_io() -> None: ...
```

The last test should prove no target file and no `asset-import-manifest.yaml` are created when registry binding fails.

- [ ] **Step 4: Add materializer negative tests**

Add tests:

```python
def test_materializer_rejects_workspace_manifest_ref_mismatch() -> None: ...
def test_materializer_rejects_missing_source_file_for_new_batch() -> None: ...
def test_materializer_rejects_source_directory_or_symlink() -> None: ...
def test_materializer_rejects_source_hash_mismatch() -> None: ...
def test_materializer_rejects_existing_target_with_different_hash() -> None: ...
def test_materializer_rejects_existing_manifest_that_is_not_prefix() -> None: ...
def test_materializer_rejects_existing_manifest_with_mutated_historical_batch() -> None: ...
def test_materializer_rejects_source_root_or_workspace_root_missing() -> None: ...
def test_materializer_does_not_write_outside_boardroom_agents() -> None: ...
def test_materializer_rejects_missing_or_changed_historical_target() -> None: ...
```

- [ ] **Step 5: Run tests to verify RED**

Run:

```bash
PYTHONPATH="src;." python -m pytest tests/proving/test_agent_asset_import.py -q
```

Expected: FAIL because `boardroom_os.workspace.agent_asset_import` does not exist.

---

### Task 2: Implement value objects and import manifest models

**Files:**
- Create: `src/boardroom_os/workspace/agent_asset_import.py`
- Test: `tests/proving/test_agent_asset_import.py`

- [ ] **Step 1: Add imports and public constants**

Implement imports:

```python
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
```

Add canonical constants:

```python
_MANIFEST_PATH = "00-boardroom/agents/asset-import-manifest.yaml"
_AGENT_ROOT = "00-boardroom/agents"
_REPO_LAYOUT_PREFIXES = ("src", "src/boardroom_os", "tests", "doc", "scripts", "examples", "backend")
_WORKSPACE_SECTION_PREFIXES = ("00-boardroom", "10-project", "20-evidence", "30-audit")
```

- [ ] **Step 2: Add value objects**

Implement:

```python
class AgentAssetImportError(ValueError): ...
class AgentAssetImportManifestRef(NonEmptyTextValue): ...
class AgentAssetBundleSourceRef(NonEmptyTextValue): ...
class AgentAssetRef(NonEmptyTextValue): ...
class AgentAssetSha256(NonEmptyTextValue): ...
class AgentAssetSourcePath(NonEmptyTextValue): ...
class AgentAssetTargetPath(NonEmptyTextValue): ...
class AgentAssetManifestPath(NonEmptyTextValue): ...
```

Path validators must reject:

- absolute POSIX path（POSIX 绝对路径）
- Windows drive（Windows 盘符）
- backslash（反斜杠）
- empty/current/parent segments（空/当前/父级路径段）
- trailing slash（尾部斜杠）
- framework repo layout misuse（框架仓库布局误用） where relevant
- workspace section misuse（工作区分区误用） for source paths

`AgentAssetTargetPath` must require `00-boardroom/agents/` and reject `_MANIFEST_PATH`.

`AgentAssetManifestPath` must equal `_MANIFEST_PATH` exactly.

`AgentAssetSha256` must be exactly 64 lowercase hex characters.

- [ ] **Step 3: Add enums and model classes**

Implement:

```python
class AgentAssetBundleSourceKind(StrEnum):
    LOCAL_BUNDLE = "local_bundle"

class AgentAssetKind(StrEnum):
    ROLE_CONFIG = "role_config"
    SKILL_FILE = "skill_file"
    PROMPT_FILE = "prompt_file"
    MCP_INTERFACE_MANIFEST = "mcp_interface_manifest"
```

Add target prefix map:

```python
_TARGET_PREFIX_BY_KIND = {
    AgentAssetKind.ROLE_CONFIG: "00-boardroom/agents/roles/",
    AgentAssetKind.SKILL_FILE: "00-boardroom/agents/skills/",
    AgentAssetKind.PROMPT_FILE: "00-boardroom/agents/prompts/",
    AgentAssetKind.MCP_INTERFACE_MANIFEST: "00-boardroom/agents/mcp/",
}
```

Implement frozen Pydantic models with `extra="forbid"`:

- `AgentAssetImportEntry`
- `AgentAssetImportBatch`
- `AgentAssetImportManifest`
- `AgentAssetMaterializationResult`

Key validators:

- entries sorted by `target_path.value`.
- batch-level unique `asset_ref`, `source_path`, and `target_path`.
- manifest-level unique `source_ref`.
- cross-batch repeated `asset_ref` allowed only with identical `sha256` and `target_path`.
- cross-batch repeated `target_path` allowed only with identical `sha256`.
- `agent_asset_import_manifest_id.value == f"agent-asset-import.{workspace_manifest_ref.value}"`.
- `imported_at` must be timezone-aware.
- result ref/path/hash fields must be internally consistent.

- [ ] **Step 4: Add field serializers**

Serialize refs and paths as `{"value": ...}` using existing project style.

Serialize enums as their `.value`.

Serialize tuple fields as lists through `model_dump(mode="json")`.

- [ ] **Step 5: Run targeted tests**

Run:

```bash
PYTHONPATH="src;." python -m pytest tests/proving/test_agent_asset_import.py -q
```

Expected: model-layer tests pass; registry/materializer tests still fail.

---

### Task 3: Implement registry binding and canonical manifest dump

**Files:**
- Modify: `src/boardroom_os/workspace/agent_asset_import.py`
- Test: `tests/proving/test_agent_asset_import.py`

- [ ] **Step 1: Add registry binding validation**

Implement:

```python
def validate_agent_asset_registry_bindings(
    *,
    manifest: AgentAssetImportManifest,
    role_profile_registry: RoleProfileRegistry,
    skill_file_registry: SkillFileSourceRegistry,
    prompt_registry: PromptSourceRegistry,
    mcp_interface_registry: McpInterfaceRegistry,
) -> None: ...
```

Mapping:

- `role_config` -> `RoleProfileRegistry.contains(RoleProfileId(asset_ref.value))`
- `skill_file` -> `SkillFileSourceRegistry.contains(SkillFileRef(asset_ref.value))`
- `prompt_file` -> `PromptSourceRegistry.contains(PromptRef(asset_ref.value))`
- `mcp_interface_manifest` -> `McpInterfaceRegistry.contains(McpInterfaceRef(asset_ref.value))`

Raise `AgentAssetImportError`（智能体资产导入错误） on any missing ref.

- [ ] **Step 2: Add canonical JSON dump helper**

Implement:

```python
def dump_agent_asset_import_manifest(manifest: AgentAssetImportManifest) -> str:
    return json.dumps(
        manifest.model_dump(mode="json"),
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    ) + "\n"
```

- [ ] **Step 3: Add manifest parse helper**

Implement a private helper:

```python
def _load_existing_manifest(path: Path) -> AgentAssetImportManifest | None: ...
```

Rules:

- missing file returns `None`.
- invalid JSON or invalid model raises `AgentAssetImportError`.
- no YAML parser dependency.

- [ ] **Step 4: Run targeted tests**

Run:

```bash
PYTHONPATH="src;." python -m pytest tests/proving/test_agent_asset_import.py -q
```

Expected: registry binding tests pass; materializer tests still fail.

---

### Task 4: Implement materializer filesystem boundary

**Files:**
- Modify: `src/boardroom_os/workspace/agent_asset_import.py`
- Test: `tests/proving/test_agent_asset_import.py`

- [ ] **Step 1: Add path and hash helpers**

Implement private helpers:

```python
def _sha256_bytes(content: bytes) -> AgentAssetSha256: ...
def _sha256_file(path: Path) -> AgentAssetSha256: ...
def _resolve_under(root: Path, relative_path: str, *, boundary_name: str) -> Path: ...
def _is_relative_to(path: Path, root: Path) -> bool: ...
def _entry_by_source_ref(manifest: AgentAssetImportManifest) -> dict[str, AgentAssetImportBatch]: ...
```

`_resolve_under` must resolve symlinks and reject path escape.

- [ ] **Step 2: Add prefix append validation**

Implement helper:

```python
def _pending_batches(
    *,
    existing_manifest: AgentAssetImportManifest | None,
    manifest: AgentAssetImportManifest,
) -> tuple[AgentAssetImportBatch, ...]: ...
```

Rules:

- if no existing manifest, all batches are pending.
- if identical manifest, pending is empty.
- if existing batches are an exact prefix, pending is suffix.
- mismatched ID/ref/path, mutated historical batch, malformed redefinition, or non-prefix order raises `AgentAssetImportError`.

- [ ] **Step 3: Add target confirmation and write helpers**

Implement:

```python
def _materialize_new_entry(...): ...
def _confirm_historical_entry(...): ...
def _write_manifest_file(...): ...
```

New entry behavior:

- source must exist, be a regular file, and not be symlink.
- source hash must match `entry.sha256`.
- target path must resolve under `workspace_root / "00-boardroom/agents"`.
- existing same-hash target is idempotent.
- existing different-hash target fails.
- parent directories may be created.

Historical entry behavior:

- source file is not required.
- target file must exist and match historical sha256.

Manifest write behavior:

- write canonical JSON to `_MANIFEST_PATH` only after all asset entries succeed.
- identical manifest should not rewrite.
- prefix append writes full cumulative manifest.
- after write, hash the manifest content and return it.

- [ ] **Step 4: Implement public materializer**

Implement:

```python
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
) -> AgentAssetMaterializationResult: ...
```

Order:

1. Validate `workspace_manifest.workspace_manifest_id == manifest.workspace_manifest_ref`.
2. Validate `source_root` and `workspace_root` exist and are directories.
3. Run `validate_agent_asset_registry_bindings(...)` before IO.
4. Load existing manifest.
5. Compute pending batches.
6. Confirm historical entries.
7. Materialize pending entries.
8. Write or confirm `asset-import-manifest.yaml`.
9. Return deterministic `AgentAssetMaterializationResult`.

- [ ] **Step 5: Run targeted tests**

Run:

```bash
PYTHONPATH="src;." python -m pytest tests/proving/test_agent_asset_import.py -q
```

Expected: materializer negative tests pass; happy path tests still need to be added.

---

### Task 5: Add happy path, idempotency, and append tests

**Files:**
- Modify: `tests/proving/test_agent_asset_import.py`
- Modify production only if tests reveal drift.

- [ ] **Step 1: Add happy path tests**

Add:

```python
def test_materializer_imports_local_agent_asset_bundle_into_boardroom_agents_snapshot() -> None: ...
def test_materializer_allows_project_asset_kind_subset_without_mcp_asset() -> None: ...
def test_materializer_is_idempotent_when_manifest_is_identical() -> None: ...
def test_materializer_appends_new_source_ref_batch_without_rewriting_history() -> None: ...
def test_agent_asset_import_manifest_model_dump_is_stable_and_audit_friendly() -> None: ...
```

Assertions:

- four-kind bundle writes files under `roles/`, `skills/`, `prompts/`, and `mcp/`.
- subset bundle works with role/skill/prompt only.
- manifest content contains no host absolute `source_root` or `workspace_root`.
- canonical JSON dump is stable.
- append keeps batch A bytes unchanged and writes batch B.
- repeated identical manifest is idempotent.

- [ ] **Step 2: Run targeted tests**

Run:

```bash
PYTHONPATH="src;." python -m pytest tests/proving/test_agent_asset_import.py -q
```

Expected: PASS.

---

### Task 6: Add public exports and integration regression

**Files:**
- Modify: `src/boardroom_os/workspace/agent_asset_import.py`
- Modify: `src/boardroom_os/workspace/__init__.py`
- Test: `tests/proving/test_agent_asset_import.py`

- [ ] **Step 1: Add `__all__` to production module**

Export:

```python
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
```

- [ ] **Step 2: Export from workspace package**

Modify `src/boardroom_os/workspace/__init__.py` to import and expose the same public API.

- [ ] **Step 3: Run integration boundary tests**

Run:

```bash
PYTHONPATH="src;." python -m pytest tests/execution/test_execution_package_compiler.py tests/execution/test_agent_profiles.py tests/proving/test_agent_asset_import.py -q
```

Expected: PASS, proving ExecutionPackage compiler（执行包编译器） still does not require `source_root` or `workspace_root`.

---

### Task 7: Run verification and fix implementation drift

**Files:**
- Modify only files needed to fix failing tests.

- [ ] **Step 1: Run V2-060F focused test**

Run:

```bash
PYTHONPATH="src;." python -m pytest tests/proving/test_agent_asset_import.py -q
```

Expected: PASS.

- [ ] **Step 2: Run Phase 6 proving tests**

Run:

```bash
PYTHONPATH="src;." python -m pytest tests/proving -q
```

Expected: PASS.

- [ ] **Step 3: Run compiler boundary regression**

Run:

```bash
PYTHONPATH="src;." python -m pytest tests/execution/test_execution_package_compiler.py tests/execution/test_agent_profiles.py tests/proving/test_agent_asset_import.py -q
```

Expected: PASS.

- [ ] **Step 4: Run broad regression**

Run:

```bash
PYTHONPATH="src;." python -m pytest tests/contracts tests/reducers tests/execution tests/evidence tests/proving tests/negative -q
```

Expected: PASS.

- [ ] **Step 5: Inspect git diff**

Run:

```bash
git diff -- src/boardroom_os/workspace/agent_asset_import.py src/boardroom_os/workspace/__init__.py tests/proving/test_agent_asset_import.py doc/04-implementation/v2-060f-agent-asset-import-spec.md doc/04-implementation/v2-060f-agent-asset-import-implementation-plan.md doc/04-implementation/INDEX.md
```

Expected: only V2-060F implementation, tests, spec P3 wording, docs index/plan changes are present before final documentation protocol.

---

### Task 8: Complete documentation update protocol

**Files:**
- Modify: `doc/04-implementation/backlog.md`
- Modify: `doc/04-implementation/acceptance-criteria.md`
- Modify: `doc/05-project-log/2026-05.md`
- Modify: `doc/04-implementation/INDEX.md` if needed

- [ ] **Step 1: Update backlog status**

In `doc/04-implementation/backlog.md`, after tests pass:

- Mark V2-060F（AgentAssetImport，智能体资产导入） as DONE.
- Update current unfinished work package to V2-070A.
- Update Phase 6 progress from 5/6 to 6/6.
- Update total progress from 40/53 to 41/53 if still matching current file state.

- [ ] **Step 2: Update Phase 6 acceptance checkboxes**

In `doc/04-implementation/acceptance-criteria.md`, mark:

```markdown
- [x] Agent asset bundle 导入可审计 — 由 V2-060F `test_agent_asset_import.py` 证明：外部 role/skill/prompt/MCP 资产必须物化为 `00-boardroom/agents/` 快照并记录 `asset-import-manifest.yaml` 来源链；ExecutionPackage compiler 保持 0 外部文件输入
- [x] V2-060A ~ V2-060F 六个工作包全部 DONE
- [x] `backlog.md` 进度总览 Phase 6 显示 6/6
```

If Phase 6 is fully closed, also mark its three “进入 Phase 7 前置” items done.

- [ ] **Step 3: Update monthly project log**

In `doc/05-project-log/2026-05.md`, add a concise 2026-05-23 entry stating that V2-060F completed AgentAssetImport（智能体资产导入）, including:

- new module and test file.
- negative coverage for unsafe paths, missing manifest fields, registry binding gaps, hash mismatch, target overwrite, and mutated historical batches.
- happy coverage for four-kind bundle, project-specific asset subset, idempotent rerun, and prefix append.
- verification commands and results.

- [ ] **Step 4: Run final targeted verification**

Run:

```bash
PYTHONPATH="src;." python -m pytest tests/proving/test_agent_asset_import.py tests/proving/test_workspace_manifest.py tests/proving/test_package_assembler.py tests/proving/test_source_inventory.py tests/proving/test_run_manifest.py tests/proving/test_workspace_evidence_export.py tests/execution/test_execution_package_compiler.py tests/execution/test_agent_profiles.py -q
```

Expected: PASS.

---

## Self-Review

- Spec coverage: The plan covers all V2-060F goals: typed manifest models, optional asset kind subset support, V2-030A registry ref binding, cumulative manifest batches, prefix append, sha256 verification, target overwrite protection, canonical JSON, workspace manifest binding, and materializer IO boundary.
- Review coverage: The plan absorbs P3-H by using project-specific asset kind subset language and P3-I by making registry ref content immutability explicit in tests and implementation expectations.
- Boundary coverage: The production module keeps ExecutionPackage compiler（执行包编译器） detached from source_root/workspace_root and imports no runtime/provider/command/git/closeout/legacy modules.
- Placeholder scan: No TBD, TODO, or “implement later” placeholders remain.
