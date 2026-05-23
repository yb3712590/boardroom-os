# V2-060B PackageAssembler（项目包装配器）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement V2-060B PackageAssembler（项目包装配器） so `10-project` generated project package（生成项目包） is represented as a strict, side-effect-free PackageAssembly（项目包装配结果） rather than a loose source artifact（源码产物） list.

**Architecture:** Add one focused module, `src/boardroom_os/workspace/assembler.py`, containing package artifact path（包产物路径）, artifact kind（产物类型）, artifact（产物）, assembly（装配结果）, and `assemble_package`（装配项目包函数） validation logic. Keep V2-060B pure: no directory creation, no file writes, no file copies, no hash calculation, no SourceInventory（源码清单）, and no RunManifest（运行清单） command binding beyond requiring `run-manifest.json` as an artifact.

**Tech Stack:** Python 3, Pydantic BaseModel（Pydantic 模型）, pytest, existing Boardroom OS V2 PackageContract（包合同） and WorkspaceManifest（工作区清单） models.

---

## File Structure

- Create `src/boardroom_os/workspace/assembler.py`
  - Own all package artifact（包产物）, package assembly（项目包装配结果）, and package coverage（包覆盖）validation.
  - Import only `contracts`（合同） and `workspace.manifest`（工作区清单） primitives.
  - Do not import runtime/execution/evidence/checker modules.
- Modify `src/boardroom_os/workspace/__init__.py`
  - Export V2-060B public assembler（项目包装配器）types.
- Create `tests/proving/test_package_assembler.py`
  - Negative/fail-closed tests first, then happy path tests.
- Modify `doc/04-implementation/INDEX.md`
  - Add this implementation plan entry.
- Modify after implementation verification only:
  - `doc/04-implementation/backlog.md`
  - `doc/04-implementation/acceptance-criteria.md`
  - `doc/05-project-log/2026-05.md`

---

### Task 1: Add negative tests for required package metadata and package-root boundary

**Files:**
- Create: `tests/proving/test_package_assembler.py`
- No production code yet.

- [ ] **Step 1: Write failing negative tests**

Create `tests/proving/test_package_assembler.py` with this content:

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
from boardroom_os.workspace.manifest import WorkflowRef, WorkspacePath, build_workspace_manifest

_VERIFY_ERRORS = (ValueError, ValidationError)


def _profile() -> MethodologyProfile:
    template_kind = MethodologyTemplateKind.HYBRID
    return MethodologyProfile(
        methodology_profile_id=ContractId(value="methodology-profile.package-assembler"),
        project_charter_ref=ContractId(value="project.charter.package-assembler"),
        template_kind=template_kind,
        documentation_density=DocumentationDensity.STANDARD,
        docs_template_key=docs_template_key_for(template_kind),
        documentation_obligations=default_documentation_obligations_for(template_kind),
    )


def _surface(
    *,
    surface_ref: str,
    name: str,
    paths: tuple[str, ...],
    acceptance_refs: tuple[str, ...],
) -> SourceSurface:
    return SourceSurface(
        source_surface_ref=SourceSurfaceRef(value=surface_ref),
        name=name,
        paths=paths,
        owned_by=OwnerSeatRef(value="worker-package"),
        acceptance_refs=tuple(AcceptanceRef(value=ref) for ref in acceptance_refs),
        required_tests=(RequiredTestRef(value="pytest-package"),),
    )


def _command(command_id: str, label: str) -> PackageCommand:
    return PackageCommand(
        command_id=ContractId(value=command_id),
        label=label,
        command=("python", "-m", "pytest"),
        cwd=".",
    )


def _package_contract(
    *,
    docs_required: bool = True,
    project_type: PackageProjectType = PackageProjectType.SOFTWARE,
    source_surfaces: tuple[SourceSurface, ...] | None = None,
):
    profile = _profile()
    surfaces = source_surfaces or (
        _surface(
            surface_ref="backend-api",
            name="Backend API",
            paths=("backend/",),
            acceptance_refs=("AC-BACKEND",),
        ),
        _surface(
            surface_ref="frontend-ui",
            name="Frontend UI",
            paths=("frontend/",),
            acceptance_refs=("AC-FRONTEND",),
        ),
        _surface(
            surface_ref="package-tests",
            name="Package Tests",
            paths=("tests/",),
            acceptance_refs=("AC-TESTS",),
        ),
        _surface(
            surface_ref="run-manifest",
            name="Run Manifest",
            paths=("run-manifest.json",),
            acceptance_refs=("AC-RUN",),
        ),
        _surface(
            surface_ref="project-docs",
            name="Project Docs",
            paths=("docs/",),
            acceptance_refs=("AC-DOCS",),
        ),
    )
    return create_package_contract(
        methodology_registry=MethodologyProfileRegistry.from_profiles(profile),
        package_contract_id=ContractId(value="package-contract.package-assembler"),
        project_charter_ref=ContractId(value="project.charter.package-assembler"),
        package_root="10-project",
        project_type=project_type,
        source_surfaces=surfaces,
        run_commands=(_command("run-package", "Run package"),),
        test_commands=(_command("test-package", "Test package"),),
        integration_boundaries=(IntegrationBoundary(value="local-http-api"),),
        docs_required=docs_required,
        closeout_required=True,
        methodology_profile_ref=profile.methodology_profile_id,
        docs_template_key=profile.docs_template_key,
        documentation_obligations=profile.documentation_obligations,
    )


def _manifest(package_contract=None):
    contract = package_contract or _package_contract()
    return build_workspace_manifest(
        workflow_ref=WorkflowRef(value="workflow-package-assembler"),
        workspace_root=WorkspacePath(value="workspace/workflow-package-assembler"),
        package_contract=contract,
    )


def _artifact(
    relative_path: str,
    kind,
    *,
    source_surface_refs: tuple[str, ...] = (),
    acceptance_refs: tuple[str, ...] = (),
):
    from boardroom_os.workspace.assembler import PackageArtifact, PackageArtifactPath

    return PackageArtifact(
        relative_path=PackageArtifactPath(value=relative_path),
        artifact_kind=kind,
        source_surface_refs=tuple(SourceSurfaceRef(value=ref) for ref in source_surface_refs),
        acceptance_refs=tuple(AcceptanceRef(value=ref) for ref in acceptance_refs),
    )


def _tiny_artifacts():
    from boardroom_os.workspace.assembler import PackageArtifactKind

    return (
        _artifact("README.md", PackageArtifactKind.README),
        _artifact("AGENTS.md", PackageArtifactKind.AGENTS),
        _artifact(
            "package-contract.json",
            PackageArtifactKind.PACKAGE_CONTRACT,
            source_surface_refs=("backend-api",),
            acceptance_refs=("AC-BACKEND",),
        ),
        _artifact(
            "run-manifest.json",
            PackageArtifactKind.RUN_MANIFEST,
            source_surface_refs=("run-manifest",),
            acceptance_refs=("AC-RUN",),
        ),
        _artifact(
            "backend/app.py",
            PackageArtifactKind.SOURCE,
            source_surface_refs=("backend-api",),
            acceptance_refs=("AC-BACKEND",),
        ),
        _artifact(
            "frontend/App.tsx",
            PackageArtifactKind.SOURCE,
            source_surface_refs=("frontend-ui",),
            acceptance_refs=("AC-FRONTEND",),
        ),
        _artifact(
            "tests/test_app.py",
            PackageArtifactKind.TEST,
            source_surface_refs=("package-tests",),
            acceptance_refs=("AC-TESTS",),
        ),
        _artifact(
            "docs/usage.md",
            PackageArtifactKind.DOC,
            source_surface_refs=("project-docs",),
            acceptance_refs=("AC-DOCS",),
        ),
    )


def _assemble(artifacts=None, package_contract=None):
    from boardroom_os.workspace.assembler import assemble_package

    contract = package_contract or _package_contract()
    return assemble_package(
        workspace_manifest=_manifest(contract),
        package_contract=contract,
        artifacts=artifacts or _tiny_artifacts(),
    )


def test_package_assembler_rejects_missing_package_contract_artifact() -> None:
    artifacts = tuple(
        artifact for artifact in _tiny_artifacts() if artifact.relative_path.value != "package-contract.json"
    )

    with pytest.raises(_VERIFY_ERRORS, match="package-contract.json"):
        _assemble(artifacts=artifacts)


def test_package_assembler_rejects_missing_run_manifest_artifact() -> None:
    artifacts = tuple(
        artifact for artifact in _tiny_artifacts() if artifact.relative_path.value != "run-manifest.json"
    )

    with pytest.raises(_VERIFY_ERRORS, match="run-manifest.json"):
        _assemble(artifacts=artifacts)


@pytest.mark.parametrize(
    "bad_path",
    [
        "/tmp/app.py",
        "../app.py",
        "20-evidence/source.json",
        "30-audit/process-audit.md",
        "00-boardroom/tickets/ticket.json",
        "10-project/src/app.py",
    ],
)
def test_package_artifact_path_rejects_paths_outside_package_root(bad_path: str) -> None:
    from boardroom_os.workspace.assembler import PackageArtifactKind

    with pytest.raises(_VERIFY_ERRORS):
        _artifact(
            bad_path,
            PackageArtifactKind.SOURCE,
            source_surface_refs=("backend-api",),
            acceptance_refs=("AC-BACKEND",),
        )
```

- [ ] **Step 2: Run tests to verify RED**

Run:

```bash
PYTHONPATH="src;." python -m pytest tests/proving/test_package_assembler.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'boardroom_os.workspace.assembler'`.

---

### Task 2: Implement minimal assembler models and required artifact gates

**Files:**
- Create: `src/boardroom_os/workspace/assembler.py`
- Modify: `src/boardroom_os/workspace/__init__.py`
- Test: `tests/proving/test_package_assembler.py`

- [ ] **Step 1: Create `assembler.py` with minimal implementation**

Create `src/boardroom_os/workspace/assembler.py` with this content:

```python
from __future__ import annotations

from enum import StrEnum
from pathlib import PurePosixPath, PureWindowsPath
from typing import Self

from pydantic import BaseModel, ConfigDict, field_serializer, field_validator, model_validator

from boardroom_os.contracts.package import PackageContract, PackageProjectType
from boardroom_os.contracts.types import AcceptanceRef, ContractId, NonEmptyTextValue, SourceSurfaceRef
from boardroom_os.workspace.manifest import WorkspaceManifest, WorkspaceManifestRef, WorkspacePath


class PackageAssemblerError(ValueError):
    pass


class PackageAssemblyRef(NonEmptyTextValue):
    pass


class PackageArtifactPath(NonEmptyTextValue):
    @field_validator("value")
    @classmethod
    def _reject_unsafe_package_path(cls, value: str) -> str:
        normalized = super()._reject_empty_value(value)
        if "\\" in normalized:
            raise ValueError("package artifact path must use forward slashes")
        if normalized.endswith("/"):
            raise ValueError("package artifact path must name a file")
        if PurePosixPath(normalized).is_absolute() or PureWindowsPath(normalized).drive:
            raise ValueError("package artifact path must be relative to package root")
        segments = normalized.split("/")
        if any(segment in {"", ".", ".."} for segment in segments):
            raise ValueError("package artifact path must not contain empty, current, or parent segments")
        forbidden_prefixes = ("00-boardroom/", "10-project/", "20-evidence/", "30-audit/")
        if normalized.startswith(forbidden_prefixes):
            raise ValueError("package artifact path must be relative to 10-project")
        framework_prefixes = ("src/boardroom_os/", "doc/", "scripts/", "examples/")
        if normalized.startswith(framework_prefixes):
            raise ValueError("package artifact path must not target framework repository layout")
        return normalized


class PackageArtifactKind(StrEnum):
    README = "readme"
    AGENTS = "agents"
    PACKAGE_CONTRACT = "package_contract"
    RUN_MANIFEST = "run_manifest"
    SOURCE = "source"
    TEST = "test"
    DOC = "doc"


class PackageArtifact(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    relative_path: PackageArtifactPath
    artifact_kind: PackageArtifactKind
    source_surface_refs: tuple[SourceSurfaceRef, ...] = ()
    acceptance_refs: tuple[AcceptanceRef, ...] = ()

    @model_validator(mode="after")
    def _validate_artifact_metadata(self) -> Self:
        if self.relative_path.value == "README.md" and self.artifact_kind is not PackageArtifactKind.README:
            raise ValueError("README.md must use readme artifact kind")
        if self.relative_path.value == "AGENTS.md" and self.artifact_kind is not PackageArtifactKind.AGENTS:
            raise ValueError("AGENTS.md must use agents artifact kind")
        if self.relative_path.value == "package-contract.json" and self.artifact_kind is not PackageArtifactKind.PACKAGE_CONTRACT:
            raise ValueError("package-contract.json must use package_contract artifact kind")
        if self.relative_path.value == "run-manifest.json" and self.artifact_kind is not PackageArtifactKind.RUN_MANIFEST:
            raise ValueError("run-manifest.json must use run_manifest artifact kind")
        if self.artifact_kind not in {PackageArtifactKind.README, PackageArtifactKind.AGENTS}:
            if not self.source_surface_refs:
                raise ValueError("package artifacts other than README and AGENTS require source_surface_refs")
            if not self.acceptance_refs:
                raise ValueError("package artifacts other than README and AGENTS require acceptance_refs")
        return self

    @field_serializer("relative_path")
    def _serialize_relative_path(self, value: PackageArtifactPath) -> dict[str, str]:
        return value.model_dump()

    @field_serializer("source_surface_refs")
    def _serialize_source_surface_refs(self, values: tuple[SourceSurfaceRef, ...]) -> list[dict[str, str]]:
        return [value.model_dump() for value in values]

    @field_serializer("acceptance_refs")
    def _serialize_acceptance_refs(self, values: tuple[AcceptanceRef, ...]) -> list[dict[str, str]]:
        return [value.model_dump() for value in values]


class PackageAssembly(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    package_assembly_id: PackageAssemblyRef
    workspace_manifest_ref: WorkspaceManifestRef
    package_contract_ref: ContractId
    package_root: WorkspacePath
    artifacts: tuple[PackageArtifact, ...]

    @field_serializer("package_assembly_id", "workspace_manifest_ref", "package_contract_ref", "package_root")
    def _serialize_refs(self, value: NonEmptyTextValue | ContractId | WorkspacePath) -> dict[str, str]:
        return value.model_dump()

    @field_serializer("artifacts")
    def _serialize_artifacts(self, values: tuple[PackageArtifact, ...]) -> list[dict[str, object]]:
        return [value.model_dump() for value in values]


def assemble_package(
    *,
    workspace_manifest: WorkspaceManifest,
    package_contract: PackageContract,
    artifacts: tuple[PackageArtifact, ...],
) -> PackageAssembly:
    if workspace_manifest.package_contract_ref != package_contract.package_contract_id:
        raise PackageAssemblerError("workspace manifest package_contract_ref must match package contract")
    if workspace_manifest.package_root.value != package_contract.package_root:
        raise PackageAssemblerError("package root must match workspace manifest package root")
    if package_contract.package_root != "10-project":
        raise PackageAssemblerError("package root must be 10-project")
    if not artifacts:
        raise PackageAssemblerError("package artifacts must not be empty")

    sorted_artifacts = tuple(sorted(artifacts, key=lambda artifact: artifact.relative_path.value))
    paths = [artifact.relative_path.value for artifact in sorted_artifacts]
    if len(paths) != len(set(paths)):
        raise PackageAssemblerError("package artifact paths must be unique")

    by_path = {artifact.relative_path.value: artifact for artifact in sorted_artifacts}
    _require_path_kind(by_path, "README.md", PackageArtifactKind.README)
    _require_path_kind(by_path, "AGENTS.md", PackageArtifactKind.AGENTS)
    _require_path_kind(by_path, "package-contract.json", PackageArtifactKind.PACKAGE_CONTRACT)
    _require_path_kind(by_path, "run-manifest.json", PackageArtifactKind.RUN_MANIFEST)

    if package_contract.project_type in {PackageProjectType.SOFTWARE, PackageProjectType.MIXED}:
        if not any(artifact.artifact_kind is PackageArtifactKind.SOURCE for artifact in sorted_artifacts):
            raise PackageAssemblerError("software and mixed packages require source artifacts")
        if not any(artifact.artifact_kind is PackageArtifactKind.TEST for artifact in sorted_artifacts):
            raise PackageAssemblerError("software and mixed packages require test artifacts")
    if package_contract.docs_required and not any(
        artifact.artifact_kind is PackageArtifactKind.DOC for artifact in sorted_artifacts
    ):
        raise PackageAssemblerError("docs_required package contracts require doc artifacts")

    _validate_surface_refs(package_contract=package_contract, artifacts=sorted_artifacts)
    _validate_surface_coverage(package_contract=package_contract, artifacts=sorted_artifacts)

    return PackageAssembly(
        package_assembly_id=PackageAssemblyRef(
            value=(
                "package-assembly."
                f"{workspace_manifest.workspace_manifest_id.value}."
                f"{package_contract.package_contract_id.value}"
            )
        ),
        workspace_manifest_ref=workspace_manifest.workspace_manifest_id,
        package_contract_ref=package_contract.package_contract_id,
        package_root=workspace_manifest.package_root,
        artifacts=sorted_artifacts,
    )


def _require_path_kind(
    by_path: dict[str, PackageArtifact],
    path: str,
    expected_kind: PackageArtifactKind,
) -> None:
    artifact = by_path.get(path)
    if artifact is None:
        raise PackageAssemblerError(f"{path} is required")
    if artifact.artifact_kind is not expected_kind:
        raise PackageAssemblerError(f"{path} must use {expected_kind.value} artifact kind")


def _validate_surface_refs(*, package_contract: PackageContract, artifacts: tuple[PackageArtifact, ...]) -> None:
    surfaces_by_ref = {
        surface.source_surface_ref.value: surface for surface in package_contract.source_surfaces
    }
    for artifact in artifacts:
        for surface_ref in artifact.source_surface_refs:
            surface = surfaces_by_ref.get(surface_ref.value)
            if surface is None:
                raise PackageAssemblerError(f"unknown source surface ref: {surface_ref.value}")
            surface_acceptance_refs = {ref.value for ref in surface.acceptance_refs}
            artifact_acceptance_refs = {ref.value for ref in artifact.acceptance_refs}
            if not artifact_acceptance_refs.issubset(surface_acceptance_refs):
                raise PackageAssemblerError(
                    f"artifact {artifact.relative_path.value} references acceptance refs outside source surface {surface_ref.value}"
                )


def _validate_surface_coverage(*, package_contract: PackageContract, artifacts: tuple[PackageArtifact, ...]) -> None:
    artifacts_by_surface: dict[str, list[PackageArtifact]] = {}
    for artifact in artifacts:
        for surface_ref in artifact.source_surface_refs:
            artifacts_by_surface.setdefault(surface_ref.value, []).append(artifact)

    for surface in package_contract.source_surfaces:
        surface_artifacts = artifacts_by_surface.get(surface.source_surface_ref.value, [])
        if not surface_artifacts:
            raise PackageAssemblerError(f"source surface {surface.source_surface_ref.value} is not covered")
        for declared_path in surface.paths:
            if not any(_artifact_matches_declared_path(artifact.relative_path.value, declared_path) for artifact in surface_artifacts):
                raise PackageAssemblerError(
                    f"source surface {surface.source_surface_ref.value} path {declared_path} is not covered"
                )


def _artifact_matches_declared_path(artifact_path: str, declared_path: str) -> bool:
    if declared_path.endswith("/"):
        return artifact_path.startswith(declared_path)
    return artifact_path == declared_path
```

- [ ] **Step 2: Add workspace package exports**

Edit `src/boardroom_os/workspace/__init__.py` so it contains exactly:

```python
from boardroom_os.workspace.assembler import (
    PackageArtifact,
    PackageArtifactKind,
    PackageArtifactPath,
    PackageAssemblerError,
    PackageAssembly,
    PackageAssemblyRef,
    assemble_package,
)
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
    "PackageArtifact",
    "PackageArtifactKind",
    "PackageArtifactPath",
    "PackageAssemblerError",
    "PackageAssembly",
    "PackageAssemblyRef",
    "WorkflowRef",
    "WorkspaceManifest",
    "WorkspaceManifestError",
    "WorkspaceManifestRef",
    "WorkspacePath",
    "WorkspaceSection",
    "WorkspaceSectionPath",
    "assemble_package",
    "build_workspace_manifest",
]
```

- [ ] **Step 3: Run Task 1 tests**

Run:

```bash
PYTHONPATH="src;." python -m pytest tests/proving/test_package_assembler.py -q
```

Expected: PASS for the initial required metadata and package-root boundary tests.

---

### Task 3: Add full fail-closed tests for package artifact validation and source-surface coverage

**Files:**
- Modify: `tests/proving/test_package_assembler.py`
- Modify if needed: `src/boardroom_os/workspace/assembler.py`

- [ ] **Step 1: Add fail-closed tests**

Append these tests to `tests/proving/test_package_assembler.py`:

```python
@pytest.mark.parametrize("bad_path", ["src\\app.py", "src//app.py", "src/./app.py", "src/app.py/", "src/../app.py"])
def test_package_artifact_path_rejects_unsafe_path_shapes(bad_path: str) -> None:
    from boardroom_os.workspace.assembler import PackageArtifactKind

    with pytest.raises(_VERIFY_ERRORS):
        _artifact(
            bad_path,
            PackageArtifactKind.SOURCE,
            source_surface_refs=("backend-api",),
            acceptance_refs=("AC-BACKEND",),
        )


@pytest.mark.parametrize("allowed_path", ["src/app.py", "tests/test_app.py", "backend/app.py", "frontend/App.tsx"])
def test_package_artifact_path_allows_generated_package_source_and_test_prefixes(allowed_path: str) -> None:
    from boardroom_os.workspace.assembler import PackageArtifactKind

    artifact = _artifact(
        allowed_path,
        PackageArtifactKind.SOURCE,
        source_surface_refs=("backend-api",),
        acceptance_refs=("AC-BACKEND",),
    )

    assert artifact.relative_path.value == allowed_path


@pytest.mark.parametrize("framework_path", ["src/boardroom_os/runtime.py", "doc/spec.md", "scripts/build.py", "examples/demo.py"])
def test_package_artifact_path_rejects_framework_repo_prefixes(framework_path: str) -> None:
    from boardroom_os.workspace.assembler import PackageArtifactKind

    with pytest.raises(_VERIFY_ERRORS, match="framework|repository"):
        _artifact(
            framework_path,
            PackageArtifactKind.SOURCE,
            source_surface_refs=("backend-api",),
            acceptance_refs=("AC-BACKEND",),
        )


def test_package_assembler_rejects_manifest_contract_mismatch() -> None:
    from boardroom_os.workspace.assembler import assemble_package

    contract = _package_contract()
    other_contract = create_package_contract(
        methodology_registry=MethodologyProfileRegistry.from_profiles(_profile()),
        package_contract_id=ContractId(value="package-contract.other"),
        project_charter_ref=ContractId(value="project.charter.package-assembler"),
        package_root="10-project",
        project_type=PackageProjectType.SOFTWARE,
        source_surfaces=contract.source_surfaces,
        run_commands=contract.run_commands,
        test_commands=contract.test_commands,
        integration_boundaries=contract.integration_boundaries,
        docs_required=True,
        closeout_required=True,
        methodology_profile_ref=_profile().methodology_profile_id,
        docs_template_key=_profile().docs_template_key,
        documentation_obligations=_profile().documentation_obligations,
    )

    with pytest.raises(_VERIFY_ERRORS, match="package_contract_ref"):
        assemble_package(
            workspace_manifest=_manifest(contract),
            package_contract=other_contract,
            artifacts=_tiny_artifacts(),
        )


def test_package_assembler_rejects_missing_readme() -> None:
    artifacts = tuple(artifact for artifact in _tiny_artifacts() if artifact.relative_path.value != "README.md")

    with pytest.raises(_VERIFY_ERRORS, match="README.md"):
        _assemble(artifacts=artifacts)


def test_package_assembler_rejects_missing_agents() -> None:
    artifacts = tuple(artifact for artifact in _tiny_artifacts() if artifact.relative_path.value != "AGENTS.md")

    with pytest.raises(_VERIFY_ERRORS, match="AGENTS.md"):
        _assemble(artifacts=artifacts)


def test_package_assembler_rejects_software_package_without_source_artifact() -> None:
    artifacts = tuple(artifact for artifact in _tiny_artifacts() if artifact.artifact_kind.value != "source")

    with pytest.raises(_VERIFY_ERRORS, match="source artifacts"):
        _assemble(artifacts=artifacts)


def test_package_assembler_rejects_software_package_without_test_artifact() -> None:
    artifacts = tuple(artifact for artifact in _tiny_artifacts() if artifact.artifact_kind.value != "test")

    with pytest.raises(_VERIFY_ERRORS, match="test artifacts"):
        _assemble(artifacts=artifacts)


def test_package_assembler_rejects_docs_required_without_doc_artifact() -> None:
    artifacts = tuple(artifact for artifact in _tiny_artifacts() if artifact.artifact_kind.value != "doc")

    with pytest.raises(_VERIFY_ERRORS, match="doc artifacts"):
        _assemble(artifacts=artifacts)


def test_package_assembler_rejects_unknown_source_surface_ref() -> None:
    from boardroom_os.workspace.assembler import PackageArtifactKind

    artifacts = _tiny_artifacts() + (
        _artifact(
            "backend/extra.py",
            PackageArtifactKind.SOURCE,
            source_surface_refs=("unknown-surface",),
            acceptance_refs=("AC-BACKEND",),
        ),
    )

    with pytest.raises(_VERIFY_ERRORS, match="unknown source surface"):
        _assemble(artifacts=artifacts)


def test_package_assembler_rejects_acceptance_ref_outside_source_surface() -> None:
    from boardroom_os.workspace.assembler import PackageArtifactKind

    artifacts = _tiny_artifacts() + (
        _artifact(
            "backend/extra.py",
            PackageArtifactKind.SOURCE,
            source_surface_refs=("backend-api",),
            acceptance_refs=("AC-FRONTEND",),
        ),
    )

    with pytest.raises(_VERIFY_ERRORS, match="acceptance refs outside source surface"):
        _assemble(artifacts=artifacts)


def test_package_assembler_rejects_uncovered_source_surface_path() -> None:
    contract = _package_contract(
        source_surfaces=(
            _surface(
                surface_ref="backend-api",
                name="Backend API",
                paths=("backend/", "backend/migrations/"),
                acceptance_refs=("AC-BACKEND",),
            ),
            _surface(
                surface_ref="frontend-ui",
                name="Frontend UI",
                paths=("frontend/",),
                acceptance_refs=("AC-FRONTEND",),
            ),
            _surface(
                surface_ref="package-tests",
                name="Package Tests",
                paths=("tests/",),
                acceptance_refs=("AC-TESTS",),
            ),
            _surface(
                surface_ref="run-manifest",
                name="Run Manifest",
                paths=("run-manifest.json",),
                acceptance_refs=("AC-RUN",),
            ),
            _surface(
                surface_ref="project-docs",
                name="Project Docs",
                paths=("docs/",),
                acceptance_refs=("AC-DOCS",),
            ),
        )
    )

    with pytest.raises(_VERIFY_ERRORS, match="backend/migrations/"):
        _assemble(package_contract=contract)


def test_package_assembler_rejects_duplicate_artifact_paths() -> None:
    artifacts = _tiny_artifacts() + (_tiny_artifacts()[0],)

    with pytest.raises(_VERIFY_ERRORS, match="unique"):
        _assemble(artifacts=artifacts)


def test_package_artifact_rejects_wrong_kind_for_package_contract_file() -> None:
    from boardroom_os.workspace.assembler import PackageArtifactKind

    with pytest.raises(_VERIFY_ERRORS, match="package-contract.json"):
        _artifact(
            "package-contract.json",
            PackageArtifactKind.SOURCE,
            source_surface_refs=("backend-api",),
            acceptance_refs=("AC-BACKEND",),
        )


def test_package_artifact_rejects_wrong_kind_for_run_manifest_file() -> None:
    from boardroom_os.workspace.assembler import PackageArtifactKind

    with pytest.raises(_VERIFY_ERRORS, match="run-manifest.json"):
        _artifact(
            "run-manifest.json",
            PackageArtifactKind.SOURCE,
            source_surface_refs=("run-manifest",),
            acceptance_refs=("AC-RUN",),
        )


def test_package_artifact_rejects_extra_fields() -> None:
    from boardroom_os.workspace.assembler import PackageArtifact, PackageArtifactKind, PackageArtifactPath

    with pytest.raises(ValidationError, match="Extra|extra"):
        PackageArtifact(
            relative_path=PackageArtifactPath(value="backend/app.py"),
            artifact_kind=PackageArtifactKind.SOURCE,
            source_surface_refs=(SourceSurfaceRef(value="backend-api"),),
            acceptance_refs=(AcceptanceRef(value="AC-BACKEND"),),
            sha256="not-in-v2-060b",
        )
```

- [ ] **Step 2: Run tests**

Run:

```bash
PYTHONPATH="src;." python -m pytest tests/proving/test_package_assembler.py -q
```

Expected: PASS. If any test fails, patch only `src/boardroom_os/workspace/assembler.py` to satisfy the documented invariant; do not add filesystem calls.

---

### Task 4: Add happy path tests for deterministic package assembly and exports

**Files:**
- Modify: `tests/proving/test_package_assembler.py`
- Modify if needed: `src/boardroom_os/workspace/assembler.py`
- Modify if needed: `src/boardroom_os/workspace/__init__.py`

- [ ] **Step 1: Add happy path tests**

Append these tests to `tests/proving/test_package_assembler.py`:

```python
def test_package_assembler_builds_tiny_fullstack_package_assembly() -> None:
    from boardroom_os.workspace.assembler import PackageArtifactKind

    assembly = _assemble()

    assert assembly.package_assembly_id.value == (
        "package-assembly.workspace-manifest.workflow-package-assembler."
        "package-contract.package-assembler"
    )
    assert assembly.workspace_manifest_ref.value == "workspace-manifest.workflow-package-assembler"
    assert assembly.package_contract_ref == ContractId(value="package-contract.package-assembler")
    assert assembly.package_root.value == "10-project"
    assert {artifact.relative_path.value for artifact in assembly.artifacts} == {
        "README.md",
        "AGENTS.md",
        "package-contract.json",
        "run-manifest.json",
        "backend/app.py",
        "frontend/App.tsx",
        "tests/test_app.py",
        "docs/usage.md",
    }
    assert any(artifact.artifact_kind is PackageArtifactKind.SOURCE for artifact in assembly.artifacts)
    assert any(artifact.artifact_kind is PackageArtifactKind.TEST for artifact in assembly.artifacts)
    assert any(artifact.artifact_kind is PackageArtifactKind.DOC for artifact in assembly.artifacts)


def test_package_assembler_sorts_artifacts_for_stable_audit_output() -> None:
    reversed_artifacts = tuple(reversed(_tiny_artifacts()))

    assembly = _assemble(artifacts=reversed_artifacts)

    assert [artifact.relative_path.value for artifact in assembly.artifacts] == sorted(
        artifact.relative_path.value for artifact in _tiny_artifacts()
    )


def test_package_assembler_repeated_builds_are_deterministic() -> None:
    first = _assemble()
    second = _assemble()

    assert first == second
    assert first.package_assembly_id == second.package_assembly_id
    assert [artifact.relative_path for artifact in first.artifacts] == [artifact.relative_path for artifact in second.artifacts]


def test_package_assembly_model_dump_is_audit_friendly() -> None:
    dumped = _assemble().model_dump()

    assert dumped["package_assembly_id"] == {
        "value": "package-assembly.workspace-manifest.workflow-package-assembler.package-contract.package-assembler"
    }
    assert dumped["workspace_manifest_ref"] == {"value": "workspace-manifest.workflow-package-assembler"}
    assert dumped["package_contract_ref"] == {"value": "package-contract.package-assembler"}
    assert dumped["package_root"] == {"value": "10-project"}
    assert dumped["artifacts"][0]["relative_path"] == {"value": "AGENTS.md"}


def test_workspace_package_exports_assembler_types() -> None:
    from boardroom_os.workspace import (
        PackageArtifact,
        PackageArtifactKind,
        PackageArtifactPath,
        PackageAssemblerError,
        PackageAssembly,
        PackageAssemblyRef,
        assemble_package,
    )

    assert PackageArtifact.__name__ == "PackageArtifact"
    assert PackageArtifactKind.SOURCE == "source"
    assert PackageArtifactPath.__name__ == "PackageArtifactPath"
    assert PackageAssemblerError.__name__ == "PackageAssemblerError"
    assert PackageAssembly.__name__ == "PackageAssembly"
    assert PackageAssemblyRef.__name__ == "PackageAssemblyRef"
    assert assemble_package.__name__ == "assemble_package"
```

- [ ] **Step 2: Run happy path tests**

Run:

```bash
PYTHONPATH="src;." python -m pytest tests/proving/test_package_assembler.py -q
```

Expected: PASS.

- [ ] **Step 3: Patch implementation only if happy path exposes a mismatch**

Allowed patches:

```python
# If enum identity checks fail after validation, compare enum values instead.
if artifact.artifact_kind == PackageArtifactKind.SOURCE:
    ...
```

Do not add materialization, hashing, file IO, or SourceInventory（源码清单） fields.

---

### Task 5: Run focused regression tests and inspect side-effect boundary

**Files:**
- No new files.
- May modify `src/boardroom_os/workspace/assembler.py` only for issues revealed by tests.

- [ ] **Step 1: Run V2-060B focused tests**

Run:

```bash
PYTHONPATH="src;." python -m pytest tests/proving/test_package_assembler.py -q
```

Expected: all tests pass.

- [ ] **Step 2: Run workspace proving tests**

Run:

```bash
PYTHONPATH="src;." python -m pytest tests/proving/test_workspace_manifest.py tests/proving/test_package_assembler.py -q
```

Expected: all tests pass.

- [ ] **Step 3: Run contract regression tests that PackageContract binding depends on**

Run:

```bash
PYTHONPATH="src;." python -m pytest tests/contracts/test_package_contract.py tests/negative/test_package_contract_fail_closed.py tests/proving/test_workspace_manifest.py tests/proving/test_package_assembler.py -q
```

Expected: all tests pass.

- [ ] **Step 4: Run broader affected suite**

Run:

```bash
PYTHONPATH="src;." python -m pytest tests/contracts tests/proving/test_workspace_manifest.py tests/proving/test_package_assembler.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Confirm implementation has no filesystem side effects**

Run:

```bash
grep -R "mkdir\|write_text\|open(\|shutil\|Path(" -n src/boardroom_os/workspace tests/proving/test_package_assembler.py || true
```

Expected: no production filesystem writes in `src/boardroom_os/workspace/assembler.py`. If grep prints `PurePosixPath` / `PureWindowsPath`, that is allowed for path validation; there must be no directory creation, file writes, copies, or file reads.

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
   - Change `当前未完成工作包` from `V2-060B` to `V2-060C`.
   - Change current focus from package assembler（项目包装配器） to source inventory builder（源码清单构建器）.
2. Progress overview:
   - Change Phase 6 from `1 / 6` to `2 / 6`.
   - Change total from `36 / 53` to `37 / 53`.
   - Status remains Phase 6 in progress.
3. V2-060B section:
   - Change `- 状态：TODO` to `- 状态：DONE`.
   - Add completion evidence after 验收口径.

Use this completion evidence wording and replace the pytest summaries with exact summaries from Task 5:

```markdown
- 完成证据：2026-05-23 新增 PackageArtifact（包产物）、PackageArtifactPath（包产物路径）、PackageArtifactKind（包产物类型）、PackageAssembly（项目包装配结果）和 assemble_package（装配项目包函数）；保持纯装配计划 + 校验边界，不创建目录、不写文件、不计算 hash、不构建 SourceInventory（源码清单）。负例证明缺 `package-contract.json`、缺 `run-manifest.json`、source artifact（源码产物）写到 package root（包根）外、unsafe path（不安全路径）、framework repo prefix（框架仓库前缀）、manifest/contract mismatch（清单/合同不匹配）、缺 README/AGENTS、软件包缺 source/test、docs_required 缺 DOC artifact（文档产物）、未知 source_surface_ref（源码实现面引用）、acceptance_ref 越界、source surface path 未覆盖、重复 artifact path（产物路径）和错误 artifact_kind（产物类型）均 fail closed；正例证明 tiny full-stack package（微型全栈包）包含 README、AGENTS、package-contract、run-manifest、backend/frontend/tests/docs，并生成 deterministic PackageAssembly（确定性项目包装配结果）。验证命令：`PYTHONPATH="src;." python -m pytest tests/proving/test_package_assembler.py -q`（复制该命令的 pytest summary）；`PYTHONPATH="src;." python -m pytest tests/proving/test_workspace_manifest.py tests/proving/test_package_assembler.py -q`（复制该命令的 pytest summary）；`PYTHONPATH="src;." python -m pytest tests/contracts/test_package_contract.py tests/negative/test_package_contract_fail_closed.py tests/proving/test_workspace_manifest.py tests/proving/test_package_assembler.py -q`（复制该命令的 pytest summary）；`PYTHONPATH="src;." python -m pytest tests/contracts tests/proving/test_workspace_manifest.py tests/proving/test_package_assembler.py -q`（复制该命令的 pytest summary）。
```

- [ ] **Step 2: Update acceptance criteria Phase 6 checkbox**

In `doc/04-implementation/acceptance-criteria.md`, Phase 6 checklist has:

```markdown
- [ ] AC-V2-PACKAGE-001（package 是最终输出）— 由 V2-060B `test_package_assembler.py` 证明：缺 package-contract / run-manifest / source 写到 package root 外必须失败
```

Change it to checked:

```markdown
- [x] AC-V2-PACKAGE-001（package 是最终输出）— 由 V2-060B `test_package_assembler.py` 证明：缺 package-contract / run-manifest / source 写到 package root 外必须失败
```

Do not check `V2-060A ~ V2-060F 六个工作包全部 DONE` yet.

- [ ] **Step 3: Add project log entry**

Append to `doc/05-project-log/2026-05.md` under the 2026-05-23 section, or create the date section if it does not exist:

```markdown
### V2-060B PackageAssembler（项目包装配器）（2026-05-23）

- 工作包：V2-060B
- 状态：DONE
- 关键产出文件：`src/boardroom_os/workspace/assembler.py`、`src/boardroom_os/workspace/__init__.py`、`tests/proving/test_package_assembler.py`
- 关键实现：新增 PackageArtifact（包产物）、PackageArtifactPath（包产物路径）、PackageArtifactKind（包产物类型）、PackageAssembly（项目包装配结果）和 assemble_package（装配项目包函数），以纯 typed assembly（类型化装配结果）表达 `10-project` generated project package（生成项目包），并校验 PackageContract.source_surfaces（包合同源码实现面）覆盖关系。
- Negative tests：覆盖缺 `package-contract.json`、缺 `run-manifest.json`、source artifact（源码产物）写到 package root（包根）外、unsafe path（不安全路径）、framework repo prefix（框架仓库前缀）、manifest/contract mismatch（清单/合同不匹配）、缺 README/AGENTS、软件包缺 source/test、docs_required 缺 DOC artifact（文档产物）、未知 source_surface_ref（源码实现面引用）、acceptance_ref 越界、source surface path 未覆盖、重复 artifact path（产物路径）和错误 artifact_kind（产物类型）均 fail closed。
- Happy path：tiny full-stack package（微型全栈包）包含 README、AGENTS、package-contract、run-manifest、backend/frontend/tests/docs，生成 deterministic PackageAssembly（确定性项目包装配结果），并稳定导出 audit-friendly model dump（审计友好模型导出）。
- 验证证据：`PYTHONPATH="src;." python -m pytest tests/proving/test_package_assembler.py -q`（复制该命令的 pytest summary）；`PYTHONPATH="src;." python -m pytest tests/proving/test_workspace_manifest.py tests/proving/test_package_assembler.py -q`（复制该命令的 pytest summary）；`PYTHONPATH="src;." python -m pytest tests/contracts/test_package_contract.py tests/negative/test_package_contract_fail_closed.py tests/proving/test_workspace_manifest.py tests/proving/test_package_assembler.py -q`（复制该命令的 pytest summary）；`PYTHONPATH="src;." python -m pytest tests/contracts tests/proving/test_workspace_manifest.py tests/proving/test_package_assembler.py -q`（复制该命令的 pytest summary）。
```

- [ ] **Step 4: Update implementation INDEX**

Add this line to `doc/04-implementation/INDEX.md` near the V2-060B spec entry:

```markdown
| `v2-060b-package-assembler-implementation-plan.md` | V2-060B PackageAssembler（项目包装配器）实施计划 |
```

- [ ] **Step 5: Run final verification after docs update**

Run:

```bash
PYTHONPATH="src;." python -m pytest tests/contracts/test_package_contract.py tests/negative/test_package_contract_fail_closed.py tests/proving/test_workspace_manifest.py tests/proving/test_package_assembler.py -q
```

Expected: all tests pass.

---

### Task 7: Final review and handoff

**Files:**
- Inspect all changed files.

- [ ] **Step 1: Check git diff**

Run:

```bash
git diff -- src/boardroom_os/workspace/__init__.py src/boardroom_os/workspace/assembler.py tests/proving/test_package_assembler.py doc/04-implementation/backlog.md doc/04-implementation/acceptance-criteria.md doc/04-implementation/INDEX.md doc/04-implementation/v2-060b-package-assembler-spec.md doc/04-implementation/v2-060b-package-assembler-implementation-plan.md doc/05-project-log/2026-05.md
```

Expected: diff only includes V2-060B spec revisions, implementation, tests, implementation plan, and required docs updates.

- [ ] **Step 2: Verify no accidental old implementation reads or imports**

Run:

```bash
grep -R "backend/app/core\|doc/refactor\|doc/live-report\|doc/tests" -n src/boardroom_os/workspace tests/proving/test_package_assembler.py doc/04-implementation/v2-060b-package-assembler-spec.md doc/04-implementation/v2-060b-package-assembler-implementation-plan.md || true
```

Expected: no output.

- [ ] **Step 3: Summarize actual verification evidence**

Prepare final handoff with:

- changed code files;
- changed docs files;
- exact pytest commands and passed counts;
- note that V2-060C is next;
- note that V2-060B did not create directories, write files, calculate hashes, or build SourceInventory（源码清单）.

Do not claim Phase 6 complete; only V2-060B is complete.

---

## Self-Review

- Spec coverage: Tasks 1-4 cover required metadata artifacts, package-root escape rejection, docs_required DOC artifact linkage, explicit generated `src/`/`tests/` allowance, framework prefix rejection, deterministic ID premise, and source-surface directory vs exact-file matching. Task 6 covers backlog, acceptance criteria, monthly log, and INDEX updates.
- Placeholder scan: No TBD/TODO/fill-later placeholders are present. Code snippets define all referenced helper functions and objects before use.
- Type consistency: `PackageArtifactPath`, `PackageArtifactKind`, `PackageArtifact`, `PackageAssemblyRef`, `PackageAssembly`, and `assemble_package` names are consistent across tests, implementation, exports, and docs.
