# V2-060A WorkspaceManifest（工作区清单）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement V2-060A WorkspaceManifest（工作区清单） so generated project workspace（生成项目工作区） is locked to the auditable four-zone layout `00-boardroom` / `10-project` / `20-evidence` / `30-audit` and bound to PackageContract（包合同） fail-closed.

**Architecture:** Add one focused module, `src/boardroom_os/workspace/manifest.py`, containing value objects（值对象）, section enum（分区枚举）, section path schema（分区路径结构）, `WorkspaceManifest`（工作区清单）, and `build_workspace_manifest`（构建工作区清单函数）. Keep V2-060A pure and side-effect free: no directory creation, no package assembly, no SourceInventory（源码清单）, no evidence export（证据导出）.

**Tech Stack:** Python 3, Pydantic BaseModel（Pydantic 模型）, pytest, existing Boardroom OS V2 contracts models（合同模型）.

---

## File Structure

- Create `src/boardroom_os/workspace/__init__.py`
  - Export V2-060A public workspace manifest（工作区清单）types.
- Create `src/boardroom_os/workspace/manifest.py`
  - Own all workspace path（工作区路径）, section（分区）, manifest（清单）, and factory（工厂函数）logic.
  - Do not import runtime/execution/evidence/checker modules.
- Create `tests/proving/test_workspace_manifest.py`
  - Negative/fail-closed tests first, then happy path tests.
- Modify `doc/04-implementation/INDEX.md`
  - Add this implementation plan entry.
- Modify after implementation verification only:
  - `doc/04-implementation/backlog.md`
  - `doc/04-implementation/acceptance-criteria.md`
  - `doc/05-project-log/2026-05.md`

---

### Task 1: Add negative tests for strict four-zone manifest construction

**Files:**
- Create: `tests/proving/test_workspace_manifest.py`
- No production code yet.

- [ ] **Step 1: Write failing negative tests**

Create `tests/proving/test_workspace_manifest.py` with this content:

```python
from __future__ import annotations

import pytest
from pydantic import ValidationError

from boardroom_os.contracts.methodology import (
    DocumentationDensity,
    MethodologyProfile,
    MethodologyProfileRegistry,
    MethodologyTemplateKind,
    default_documentation_obligations_for,
    docs_template_key_for,
)
from boardroom_os.contracts.package import (
    IntegrationBoundary,
    PackageCommand,
    PackageProjectType,
    create_package_contract,
)
from boardroom_os.contracts.source_surface import OwnerSeatRef, RequiredTestRef, SourceSurface
from boardroom_os.contracts.types import AcceptanceRef, ContractId, SourceSurfaceRef

_VERIFY_ERRORS = (ValueError, ValidationError)


def _surface(
    *,
    surface_ref: str = "backend-api",
    paths: tuple[str, ...] = ("backend/",),
    acceptance_refs: tuple[str, ...] = ("AC-BACKEND",),
) -> SourceSurface:
    return SourceSurface(
        source_surface_ref=SourceSurfaceRef(value=surface_ref),
        name="Backend API",
        paths=paths,
        owned_by=OwnerSeatRef(value="worker-backend"),
        acceptance_refs=tuple(AcceptanceRef(value=ref) for ref in acceptance_refs),
        required_tests=(RequiredTestRef(value="pytest-backend"),),
    )


def _command(command_id: str = "test-backend") -> PackageCommand:
    return PackageCommand(
        command_id=ContractId(value=command_id),
        label="Run backend tests",
        command=("pytest", "tests/backend"),
        cwd=".",
    )


def _profile() -> MethodologyProfile:
    template_kind = MethodologyTemplateKind.HYBRID
    return MethodologyProfile(
        methodology_profile_id=ContractId(value="methodology-profile.workspace"),
        project_charter_ref=ContractId(value="project.charter.workspace"),
        template_kind=template_kind,
        documentation_density=DocumentationDensity.STANDARD,
        docs_template_key=docs_template_key_for(template_kind),
        documentation_obligations=default_documentation_obligations_for(template_kind),
    )


def _package_contract(*, package_root: str = "10-project"):
    profile = _profile()
    return create_package_contract(
        methodology_registry=MethodologyProfileRegistry.from_profiles(profile),
        package_contract_id=ContractId(value="package-contract.workspace"),
        project_charter_ref=ContractId(value="project.charter.workspace"),
        package_root=package_root,
        project_type=PackageProjectType.SOFTWARE,
        source_surfaces=(
            _surface(),
            SourceSurface(
                source_surface_ref=SourceSurfaceRef(value="run-manifest"),
                name="Run Manifest",
                paths=("run-manifest.json",),
                owned_by=OwnerSeatRef(value="worker-backend"),
                acceptance_refs=(AcceptanceRef(value="AC-RUN"),),
                required_tests=(RequiredTestRef(value="pytest-backend"),),
            ),
        ),
        run_commands=(_command("run-backend"),),
        test_commands=(_command("test-backend"),),
        integration_boundaries=(IntegrationBoundary(value="backend-http-api"),),
        docs_required=True,
        closeout_required=True,
        methodology_profile_ref=profile.methodology_profile_id,
        docs_template_key=profile.docs_template_key,
        documentation_obligations=profile.documentation_obligations,
    )


def _manifest_sections():
    from boardroom_os.workspace.manifest import WorkspaceSection, WorkspaceSectionPath, WorkspacePath

    return (
        WorkspaceSectionPath(section=WorkspaceSection.BOARDROOM, relative_path=WorkspacePath(value="00-boardroom")),
        WorkspaceSectionPath(section=WorkspaceSection.PROJECT, relative_path=WorkspacePath(value="10-project")),
        WorkspaceSectionPath(section=WorkspaceSection.EVIDENCE, relative_path=WorkspacePath(value="20-evidence")),
        WorkspaceSectionPath(section=WorkspaceSection.AUDIT, relative_path=WorkspacePath(value="30-audit")),
    )


def _manifest(**overrides: object):
    from boardroom_os.workspace.manifest import (
        WorkflowRef,
        WorkspaceManifest,
        WorkspaceManifestRef,
        WorkspacePath,
    )

    fields: dict[str, object] = {
        "workspace_manifest_id": WorkspaceManifestRef(value="workspace-manifest.workflow-tiny"),
        "workflow_ref": WorkflowRef(value="workflow-tiny"),
        "workspace_root": WorkspacePath(value="workspace/workflow-tiny"),
        "package_contract_ref": ContractId(value="package-contract.workspace"),
        "sections": _manifest_sections(),
    }
    fields.update(overrides)
    return WorkspaceManifest(**fields)


def test_workspace_manifest_rejects_missing_project_section() -> None:
    sections = tuple(section for section in _manifest_sections() if section.relative_path.value != "10-project")

    with pytest.raises(_VERIFY_ERRORS, match="project|10-project"):
        _manifest(sections=sections)


def test_workspace_manifest_rejects_missing_evidence_section() -> None:
    sections = tuple(section for section in _manifest_sections() if section.relative_path.value != "20-evidence")

    with pytest.raises(_VERIFY_ERRORS, match="evidence|20-evidence"):
        _manifest(sections=sections)


@pytest.mark.parametrize("package_root", ["/tmp/project", "../10-project", "project", "10-project/src"])
def test_build_workspace_manifest_rejects_package_root_outside_workspace(package_root: str) -> None:
    from boardroom_os.workspace.manifest import WorkflowRef, WorkspaceManifestError, WorkspacePath, build_workspace_manifest

    with pytest.raises(WorkspaceManifestError, match="package root"):
        build_workspace_manifest(
            workflow_ref=WorkflowRef(value="workflow-tiny"),
            workspace_root=WorkspacePath(value="workspace/workflow-tiny"),
            package_contract=_package_contract(package_root=package_root),
        )
```

- [ ] **Step 2: Run tests to verify RED**

Run:

```bash
PYTHONPATH="src:." python -m pytest tests/proving/test_workspace_manifest.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'boardroom_os.workspace.manifest'`.

---

### Task 2: Implement minimal manifest models and package-root factory gate

**Files:**
- Create: `src/boardroom_os/workspace/__init__.py`
- Create: `src/boardroom_os/workspace/manifest.py`
- Test: `tests/proving/test_workspace_manifest.py`

- [ ] **Step 1: Create `manifest.py` with minimal implementation**

Create `src/boardroom_os/workspace/manifest.py` with this content:

```python
from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, field_serializer, field_validator, model_validator

from boardroom_os.contracts.package import PackageContract
from boardroom_os.contracts.types import ContractId, NonEmptyTextValue


class WorkspaceManifestError(ValueError):
    pass


class WorkspaceManifestRef(NonEmptyTextValue):
    pass


class WorkflowRef(NonEmptyTextValue):
    pass


class WorkspacePath(NonEmptyTextValue):
    @field_validator("value")
    @classmethod
    def _validate_logical_relative_path(cls, value: str) -> str:
        normalized = value.strip().rstrip("/")
        if not normalized:
            raise ValueError("workspace path must not be empty")
        if normalized.startswith("/"):
            raise ValueError("workspace path must be relative")
        if "\\" in normalized:
            raise ValueError("workspace path must use forward slashes")
        if len(normalized) >= 2 and normalized[1] == ":":
            raise ValueError("workspace path must not include a drive prefix")
        parts = normalized.split("/")
        if any(part == "" for part in parts):
            raise ValueError("workspace path must not contain empty segments")
        if any(part in {".", ".."} for part in parts):
            raise ValueError("workspace path must not contain dot segments")
        return normalized


class WorkspaceSection(StrEnum):
    BOARDROOM = "boardroom"
    PROJECT = "project"
    EVIDENCE = "evidence"
    AUDIT = "audit"


_CANONICAL_SECTION_PATHS: dict[WorkspaceSection, str] = {
    WorkspaceSection.BOARDROOM: "00-boardroom",
    WorkspaceSection.PROJECT: "10-project",
    WorkspaceSection.EVIDENCE: "20-evidence",
    WorkspaceSection.AUDIT: "30-audit",
}

_SECTION_ORDER: tuple[WorkspaceSection, ...] = (
    WorkspaceSection.BOARDROOM,
    WorkspaceSection.PROJECT,
    WorkspaceSection.EVIDENCE,
    WorkspaceSection.AUDIT,
)

_RESERVED_REPO_ROOTS = {"src", "tests", "doc", "scripts", "examples", "backend"}


class WorkspaceSectionPath(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    section: WorkspaceSection
    relative_path: WorkspacePath

    @model_validator(mode="after")
    def _validate_canonical_section_path(self) -> WorkspaceSectionPath:
        expected_path = _CANONICAL_SECTION_PATHS[self.section]
        if self.relative_path.value != expected_path:
            raise ValueError(f"{self.section.value} section must be {expected_path}")
        return self

    @field_serializer("relative_path")
    def _serialize_relative_path(self, value: WorkspacePath) -> dict[str, str]:
        return value.model_dump()


class WorkspaceManifest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    workspace_manifest_id: WorkspaceManifestRef
    workflow_ref: WorkflowRef
    workspace_root: WorkspacePath
    package_contract_ref: ContractId
    sections: tuple[WorkspaceSectionPath, ...]

    @model_validator(mode="after")
    def _validate_manifest(self) -> WorkspaceManifest:
        expected_id = f"workspace-manifest.{self.workflow_ref.value}"
        if self.workspace_manifest_id.value != expected_id:
            raise ValueError("workspace_manifest_id must be derived from workflow_ref")

        root_first_segment = self.workspace_root.value.split("/", 1)[0]
        if root_first_segment in _RESERVED_REPO_ROOTS:
            raise ValueError("workspace_root must not point at the framework repository layout")

        by_section: dict[WorkspaceSection, WorkspaceSectionPath] = {}
        for section_path in self.sections:
            if section_path.section in by_section:
                raise ValueError("workspace sections must be unique")
            by_section[section_path.section] = section_path

        if set(by_section) != set(_SECTION_ORDER):
            raise ValueError("workspace manifest must contain boardroom, project, evidence, and audit sections")

        ordered_sections = tuple(by_section[section] for section in _SECTION_ORDER)
        object.__setattr__(self, "sections", ordered_sections)
        return self

    @property
    def boardroom_root(self) -> WorkspacePath:
        return self.section_path(WorkspaceSection.BOARDROOM)

    @property
    def package_root(self) -> WorkspacePath:
        return self.section_path(WorkspaceSection.PROJECT)

    @property
    def evidence_root(self) -> WorkspacePath:
        return self.section_path(WorkspaceSection.EVIDENCE)

    @property
    def audit_root(self) -> WorkspacePath:
        return self.section_path(WorkspaceSection.AUDIT)

    def section_path(self, section: WorkspaceSection) -> WorkspacePath:
        for section_path in self.sections:
            if section_path.section is section:
                return section_path.relative_path
        raise WorkspaceManifestError(f"missing workspace section: {section.value}")

    def full_section_path(self, section: WorkspaceSection) -> WorkspacePath:
        return WorkspacePath(value=f"{self.workspace_root.value}/{self.section_path(section).value}")

    @field_serializer("workspace_manifest_id", "workflow_ref", "workspace_root", "package_contract_ref")
    def _serialize_value_objects(self, value: NonEmptyTextValue | ContractId) -> dict[str, str]:
        return value.model_dump()

    @field_serializer("sections")
    def _serialize_sections(self, values: tuple[WorkspaceSectionPath, ...]) -> list[dict[str, object]]:
        return [value.model_dump() for value in values]


def _canonical_sections() -> tuple[WorkspaceSectionPath, ...]:
    return tuple(
        WorkspaceSectionPath(section=section, relative_path=WorkspacePath(value=path))
        for section, path in _CANONICAL_SECTION_PATHS.items()
    )


def build_workspace_manifest(
    *,
    workflow_ref: WorkflowRef,
    workspace_root: WorkspacePath,
    package_contract: PackageContract,
) -> WorkspaceManifest:
    if package_contract.package_root != _CANONICAL_SECTION_PATHS[WorkspaceSection.PROJECT]:
        raise WorkspaceManifestError("package root must be 10-project inside the workspace")
    return WorkspaceManifest(
        workspace_manifest_id=WorkspaceManifestRef(value=f"workspace-manifest.{workflow_ref.value}"),
        workflow_ref=workflow_ref,
        workspace_root=workspace_root,
        package_contract_ref=package_contract.package_contract_id,
        sections=_canonical_sections(),
    )
```

- [ ] **Step 2: Create package exports**

Create `src/boardroom_os/workspace/__init__.py` with this content:

```python
"""Generated project workspace primitives for Boardroom OS V2."""

from boardroom_os.workspace.manifest import (
    WorkflowRef,
    WorkspaceManifest,
    WorkspaceManifestError,
    WorkspaceManifestRef,
    WorkspacePath,
    WorkspaceSection,
    WorkspaceSectionPath,
    build_workspace_manifest,
)

__all__ = [
    "WorkflowRef",
    "WorkspaceManifest",
    "WorkspaceManifestError",
    "WorkspaceManifestRef",
    "WorkspacePath",
    "WorkspaceSection",
    "WorkspaceSectionPath",
    "build_workspace_manifest",
]
```

- [ ] **Step 3: Run Task 1 tests**

Run:

```bash
PYTHONPATH="src:." python -m pytest tests/proving/test_workspace_manifest.py -q
```

Expected: PASS for the initial negative tests.

---

### Task 3: Add full fail-closed tests for path, section, repo-layout, and extra-field boundaries

**Files:**
- Modify: `tests/proving/test_workspace_manifest.py`
- Modify if needed: `src/boardroom_os/workspace/manifest.py`

- [ ] **Step 1: Add fail-closed tests**

Append these tests to `tests/proving/test_workspace_manifest.py`:

```python
@pytest.mark.parametrize(
    ("section_name", "bad_path", "expected"),
    [
        ("PROJECT", "project", "10-project"),
        ("PROJECT", "src", "10-project"),
        ("PROJECT", "src/boardroom_os", "10-project"),
        ("EVIDENCE", "evidence", "20-evidence"),
        ("EVIDENCE", "10-project/evidence", "20-evidence"),
        ("AUDIT", "audit", "30-audit"),
        ("BOARDROOM", "boardroom", "00-boardroom"),
    ],
)
def test_workspace_section_path_rejects_non_canonical_section_roots(
    section_name: str,
    bad_path: str,
    expected: str,
) -> None:
    from boardroom_os.workspace.manifest import WorkspaceSection, WorkspaceSectionPath, WorkspacePath

    with pytest.raises(_VERIFY_ERRORS, match=expected):
        WorkspaceSectionPath(
            section=getattr(WorkspaceSection, section_name),
            relative_path=WorkspacePath(value=bad_path),
        )


def test_workspace_manifest_rejects_duplicate_sections() -> None:
    sections = _manifest_sections()

    with pytest.raises(_VERIFY_ERRORS, match="unique"):
        _manifest(sections=sections[:3] + (sections[1],))


def test_workspace_manifest_rejects_unknown_durable_section() -> None:
    with pytest.raises(_VERIFY_ERRORS):
        _manifest(
            sections=tuple(section.model_dump() for section in _manifest_sections())
            + ({"section": "cache", "relative_path": {"value": "40-cache"}},),
        )


@pytest.mark.parametrize(
    "bad_path",
    [
        "/workspace/workflow-tiny",
        "C:/workspace/workflow-tiny",
        "C:\\workspace\\workflow-tiny",
        "workspace//workflow-tiny",
        "workspace/./workflow-tiny",
        "workspace/../workflow-tiny",
        "workspace/workflow-tiny/..",
    ],
)
def test_workspace_path_rejects_unsafe_paths(bad_path: str) -> None:
    from boardroom_os.workspace.manifest import WorkspacePath

    with pytest.raises(_VERIFY_ERRORS):
        WorkspacePath(value=bad_path)


@pytest.mark.parametrize("workspace_root", ["src/boardroom_os", "tests", "doc", "scripts", "examples", "backend/app"])
def test_workspace_manifest_rejects_framework_repo_layout_as_workspace_root(workspace_root: str) -> None:
    from boardroom_os.workspace.manifest import WorkspacePath

    with pytest.raises(_VERIFY_ERRORS, match="framework repository layout"):
        _manifest(workspace_root=WorkspacePath(value=workspace_root))


def test_workspace_manifest_rejects_id_that_does_not_match_workflow_ref() -> None:
    from boardroom_os.workspace.manifest import WorkspaceManifestRef

    with pytest.raises(_VERIFY_ERRORS, match="workflow_ref"):
        _manifest(workspace_manifest_id=WorkspaceManifestRef(value="workspace-manifest.other"))


def test_workspace_manifest_rejects_extra_fields() -> None:
    from boardroom_os.workspace.manifest import WorkspaceManifest

    fields = _manifest().model_dump()
    fields["scratch_root"] = {"value": "scratch"}

    with pytest.raises(_VERIFY_ERRORS):
        WorkspaceManifest(**fields)


@pytest.mark.parametrize("forbidden_section", ["40-cache", "secrets", "runtime-scratch"])
def test_workspace_manifest_rejects_cache_secret_or_scratch_as_section(forbidden_section: str) -> None:
    with pytest.raises(_VERIFY_ERRORS):
        _manifest(
            sections=tuple(section.model_dump() for section in _manifest_sections())
            + ({"section": "project", "relative_path": {"value": forbidden_section}},),
        )
```

- [ ] **Step 2: Run tests to verify RED or confirm current implementation covers them**

Run:

```bash
PYTHONPATH="src:." python -m pytest tests/proving/test_workspace_manifest.py -q
```

Expected: PASS if Task 2 implementation already covers these invariants; otherwise FAIL only on the newly exposed invariant.

- [ ] **Step 3: Patch implementation only if tests fail**

If failures show gaps, patch `src/boardroom_os/workspace/manifest.py` without adding new responsibilities. The only expected fixes are:

```python
# If model_dump dict revalidation produces string section comparison issues,
# compare with equality instead of identity in section_path.
if section_path.section == section:
    return section_path.relative_path
```

or tightening error messages. Do not add filesystem calls.

- [ ] **Step 4: Run focused tests**

Run:

```bash
PYTHONPATH="src:." python -m pytest tests/proving/test_workspace_manifest.py -q
```

Expected: PASS for all negative tests.

---

### Task 4: Add happy path tests for tiny manifest roots, full paths, stable dumps, and exports

**Files:**
- Modify: `tests/proving/test_workspace_manifest.py`
- Modify if needed: `src/boardroom_os/workspace/manifest.py`
- Modify if needed: `src/boardroom_os/workspace/__init__.py`

- [ ] **Step 1: Add happy path tests**

Append these tests to `tests/proving/test_workspace_manifest.py`:

```python
def test_tiny_workspace_manifest_locates_all_four_canonical_roots() -> None:
    from boardroom_os.workspace.manifest import WorkflowRef, WorkspacePath, build_workspace_manifest

    manifest = build_workspace_manifest(
        workflow_ref=WorkflowRef(value="workflow-tiny"),
        workspace_root=WorkspacePath(value="workspace/workflow-tiny"),
        package_contract=_package_contract(),
    )

    assert manifest.boardroom_root.value == "00-boardroom"
    assert manifest.package_root.value == "10-project"
    assert manifest.evidence_root.value == "20-evidence"
    assert manifest.audit_root.value == "30-audit"
    assert manifest.package_contract_ref == ContractId(value="package-contract.workspace")


def test_workspace_manifest_full_section_path_is_logical_and_stable() -> None:
    from boardroom_os.workspace.manifest import WorkflowRef, WorkspacePath, WorkspaceSection, build_workspace_manifest

    manifest = build_workspace_manifest(
        workflow_ref=WorkflowRef(value="workflow-tiny"),
        workspace_root=WorkspacePath(value="workspace/workflow-tiny"),
        package_contract=_package_contract(),
    )

    assert manifest.full_section_path(WorkspaceSection.PROJECT).value == "workspace/workflow-tiny/10-project"
    assert manifest.full_section_path(WorkspaceSection.EVIDENCE).value == "workspace/workflow-tiny/20-evidence"
    assert manifest.full_section_path(WorkspaceSection.AUDIT).value == "workspace/workflow-tiny/30-audit"


def test_workspace_manifest_dump_has_stable_section_order() -> None:
    manifest = _manifest(sections=tuple(reversed(_manifest_sections())))

    dumped = manifest.model_dump()

    assert dumped["workspace_manifest_id"] == {"value": "workspace-manifest.workflow-tiny"}
    assert [section["section"] for section in dumped["sections"]] == [
        "boardroom",
        "project",
        "evidence",
        "audit",
    ]
    assert [section["relative_path"]["value"] for section in dumped["sections"]] == [
        "00-boardroom",
        "10-project",
        "20-evidence",
        "30-audit",
    ]


def test_workspace_manifest_build_is_deterministic() -> None:
    from boardroom_os.workspace.manifest import WorkflowRef, WorkspacePath, build_workspace_manifest

    manifest_a = build_workspace_manifest(
        workflow_ref=WorkflowRef(value="workflow-tiny"),
        workspace_root=WorkspacePath(value="workspace/workflow-tiny"),
        package_contract=_package_contract(),
    )
    manifest_b = build_workspace_manifest(
        workflow_ref=WorkflowRef(value="workflow-tiny"),
        workspace_root=WorkspacePath(value="workspace/workflow-tiny"),
        package_contract=_package_contract(),
    )

    assert manifest_a == manifest_b
    assert manifest_a.workspace_manifest_id.value == "workspace-manifest.workflow-tiny"


def test_workspace_package_exports_manifest_types() -> None:
    from boardroom_os.workspace import (
        WorkflowRef,
        WorkspaceManifest,
        WorkspaceManifestError,
        WorkspaceManifestRef,
        WorkspacePath,
        WorkspaceSection,
        WorkspaceSectionPath,
        build_workspace_manifest,
    )

    assert WorkflowRef.__name__ == "WorkflowRef"
    assert WorkspaceManifest.__name__ == "WorkspaceManifest"
    assert WorkspaceManifestError.__name__ == "WorkspaceManifestError"
    assert WorkspaceManifestRef.__name__ == "WorkspaceManifestRef"
    assert WorkspacePath.__name__ == "WorkspacePath"
    assert WorkspaceSection.PROJECT == "project"
    assert WorkspaceSectionPath.__name__ == "WorkspaceSectionPath"
    assert build_workspace_manifest.__name__ == "build_workspace_manifest"
```

- [ ] **Step 2: Run happy path tests**

Run:

```bash
PYTHONPATH="src:." python -m pytest tests/proving/test_workspace_manifest.py -q
```

Expected: PASS.

- [ ] **Step 3: Patch implementation only if happy path exposes a mismatch**

Allowed patches:

```python
# If Pydantic enum serialization returns WorkspaceSection instead of string,
# keep ConfigDict default and assert equality through enum value in tests,
# or add model_config = ConfigDict(frozen=True, extra="forbid", use_enum_values=True)
# to WorkspaceSectionPath if all tests prefer strings.
```

Prefer matching existing project style: many modules keep enum values in dumps via `use_enum_values=True` only when needed. Do not add unrelated serializer logic.

---

### Task 5: Run focused regression tests and inspect side-effect boundary

**Files:**
- No new files.
- May modify `src/boardroom_os/workspace/manifest.py` only for issues revealed by tests.

- [ ] **Step 1: Run V2-060A focused tests**

Run:

```bash
PYTHONPATH="src:." python -m pytest tests/proving/test_workspace_manifest.py -q
```

Expected: all tests pass.

- [ ] **Step 2: Run contract regression tests that PackageContract binding depends on**

Run:

```bash
PYTHONPATH="src:." python -m pytest tests/contracts/test_package_contract.py tests/negative/test_package_contract_fail_closed.py tests/proving/test_workspace_manifest.py -q
```

Expected: all tests pass.

- [ ] **Step 3: Run broader affected suite**

Run:

```bash
PYTHONPATH="src:." python -m pytest tests/contracts tests/proving/test_workspace_manifest.py -q
```

Expected: all tests pass.

- [ ] **Step 4: Confirm implementation has no filesystem side effects**

Run:

```bash
grep -R "mkdir\|write_text\|open(\|shutil\|Path(" -n src/boardroom_os/workspace tests/proving/test_workspace_manifest.py || true
```

Expected: no production filesystem writes in `src/boardroom_os/workspace/manifest.py`. If the grep prints test helper imports only, inspect them; V2-060A production code must not create directories or files.

---

### Task 6: Update completion docs after verification

**Files:**
- Modify: `doc/04-implementation/backlog.md`
- Modify: `doc/04-implementation/acceptance-criteria.md`
- Modify: `doc/05-project-log/2026-05.md`
- Modify: `doc/04-implementation/INDEX.md`

- [ ] **Step 1: Update backlog status and progress**

In `doc/04-implementation/backlog.md`:

1. Top TL;DR:
   - Change `当前未完成工作包` from `V2-060A` to `V2-060B`.
   - Change current focus from workspace manifest（工作区清单） to package assembler（包装配器）.
2. Progress overview:
   - Change Phase 6 from `0 / 6` to `1 / 6`.
   - Change total from `35 / 53` to `36 / 53`.
   - Status remains Phase 6 in progress / started.
3. V2-060A section:
   - Change the current work-package status value from pending to completed.
   - Add completion evidence including the exact verification commands from Task 5 and the exact parenthesized pytest summary printed by each command.

Use this completion evidence wording and replace only the three parenthesized pytest summaries with the exact summaries printed by the terminal during Task 5:

```markdown
- 完成证据：2026-05-22 新增 WorkspaceManifest（工作区清单）、WorkspaceSection（工作区分区）、WorkspacePath（工作区路径）和 build_workspace_manifest（构建工作区清单函数），严格固定 generated project workspace（生成项目工作区）四区：`00-boardroom`、`10-project`、`20-evidence`、`30-audit`。负例证明缺 `10-project`、缺 `20-evidence`、PackageContract.package_root（包合同包根）逃逸 workspace（工作区）、非 canonical section path（非规范分区路径）、重复/额外 section（重复/额外分区）、unsafe path（不安全路径）、framework repo layout misuse（框架仓库布局误用）和 extra fields（额外字段）均 fail closed；正例证明 tiny workspace manifest（微型工作区清单）可定位 package/evidence/audit roots（包/证据/审计根）并稳定序列化。验证命令：`PYTHONPATH="src:." python -m pytest tests/proving/test_workspace_manifest.py -q`（复制该命令的 pytest summary）；`PYTHONPATH="src:." python -m pytest tests/contracts/test_package_contract.py tests/negative/test_package_contract_fail_closed.py tests/proving/test_workspace_manifest.py -q`（复制该命令的 pytest summary）；`PYTHONPATH="src:." python -m pytest tests/contracts tests/proving/test_workspace_manifest.py -q`（复制该命令的 pytest summary）。
```

- [ ] **Step 2: Update acceptance criteria Phase 6 checkbox**

In `doc/04-implementation/acceptance-criteria.md`, Phase 6 checklist currently has:

```markdown
- [ ] V2-060A ~ V2-060F 六个工作包全部 DONE
```

Do not check that aggregate line yet. V2-060A has no dedicated checkbox in current acceptance file. Leave Phase 6 AC checkboxes open except any text update needed to mention V2-060A under Workspace / package / evidence synchronization only if implementation reveals a necessary wording correction. Default: no checkbox change for V2-060A.

- [ ] **Step 3: Add project log entry**

Append to `doc/05-project-log/2026-05.md` under 2026-05-22:

```markdown
### V2-060A WorkspaceManifest（工作区清单）（2026-05-22）

- 工作包：V2-060A
- 状态：DONE
- 关键产出文件：`src/boardroom_os/workspace/manifest.py`、`src/boardroom_os/workspace/__init__.py`、`tests/proving/test_workspace_manifest.py`
- 关键实现：新增 WorkspaceManifest（工作区清单）、WorkspaceSection（工作区分区）、WorkspaceSectionPath（工作区分区路径）、WorkspacePath（工作区路径）和 build_workspace_manifest（构建工作区清单函数），将 generated project workspace（生成项目工作区）严格固定为 `00-boardroom` / `10-project` / `20-evidence` / `30-audit` 四区，并把 PackageContract.package_root（包合同包根）绑定到 `10-project`。
- Negative tests：覆盖缺 `10-project`、缺 `20-evidence`、PackageContract.package_root（包合同包根）为 absolute / parent traversal / non-canonical path（绝对路径 / 上级目录逃逸 / 非规范路径）、非 canonical section root（非规范分区根）、重复 section（重复分区）、额外 durable section（额外持久分区）、unsafe WorkspacePath（不安全工作区路径）、framework repo layout misuse（框架仓库布局误用）、manifest id mismatch（清单 ID 不匹配）和 extra fields（额外字段）均 fail closed。
- Happy path：tiny PackageContract（微型包合同）可构建 deterministic WorkspaceManifest（确定性工作区清单），稳定定位 boardroom/package/evidence/audit roots（治理/包/证据/审计根）和 full section paths（完整分区路径），并通过 workspace package exports（工作区包导出）消费。
- 验证证据：`PYTHONPATH="src:." python -m pytest tests/proving/test_workspace_manifest.py -q`（复制该命令的 pytest summary）；`PYTHONPATH="src:." python -m pytest tests/contracts/test_package_contract.py tests/negative/test_package_contract_fail_closed.py tests/proving/test_workspace_manifest.py -q`（复制该命令的 pytest summary）；`PYTHONPATH="src:." python -m pytest tests/contracts tests/proving/test_workspace_manifest.py -q`（复制该命令的 pytest summary）。
```

- [ ] **Step 4: Update implementation INDEX**

Add this line to `doc/04-implementation/INDEX.md` near the V2-060A spec entry:

```markdown
| `v2-060a-workspace-manifest-implementation-plan.md` | V2-060A WorkspaceManifest（工作区清单）实施计划 |
```

- [ ] **Step 5: Run final verification after docs update**

Run:

```bash
PYTHONPATH="src:." python -m pytest tests/contracts/test_package_contract.py tests/negative/test_package_contract_fail_closed.py tests/proving/test_workspace_manifest.py -q
```

Expected: all tests pass.

---

### Task 7: Final review and handoff

**Files:**
- Inspect all changed files.

- [ ] **Step 1: Check git diff**

Run:

```bash
git diff -- src/boardroom_os/workspace/__init__.py src/boardroom_os/workspace/manifest.py tests/proving/test_workspace_manifest.py doc/04-implementation/backlog.md doc/04-implementation/acceptance-criteria.md doc/04-implementation/INDEX.md doc/05-project-log/2026-05.md
```

Expected: diff only includes V2-060A implementation, tests, and required docs updates.

- [ ] **Step 2: Verify no accidental old implementation reads or imports**

Run:

```bash
grep -R "backend/app/core\|doc/refactor\|doc/live-report\|doc/tests" -n src/boardroom_os/workspace tests/proving/test_workspace_manifest.py doc/04-implementation/v2-060a-workspace-manifest-implementation-plan.md || true
```

Expected: no output.

- [ ] **Step 3: Summarize actual verification evidence**

Prepare final handoff with:

- changed code files;
- changed docs files;
- exact pytest commands and passed counts;
- note that V2-060B is next;
- note that V2-060A did not create directories or write package/evidence files.

Do not claim Phase 6 complete; only V2-060A is complete.
