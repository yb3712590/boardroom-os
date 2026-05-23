# V2-060C SourceInventory（源码清单）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement V2-060C SourceInventory（源码清单） so final package files can prove implementation lineage（实现来源链） with path, sha256, producer ticket, provider attempt, acceptance refs, and verified evidence refs.

**Architecture:** Add one focused module, `src/boardroom_os/workspace/source_inventory.py`, containing source file path（源码文件路径）, source file record（源码文件记录）, lineage record（来源链记录）, inventory entry（清单条目）, inventory（清单）, and `build_source_inventory`（构建源码清单函数） validation logic. Keep V2-060C pure: no filesystem traversal, no git calls, no directory creation, no file writes, no evidence verification, and no run-manifest command binding.

**Tech Stack:** Python 3, Pydantic BaseModel（Pydantic 模型）, pytest, existing Boardroom OS V2 PackageContract（包合同）, PackageAssembly（项目包装配结果）, TicketId（任务 ID）, ProviderAttemptRef（模型调用尝试引用）, VerifiedEvidenceRef（已验证证据引用）, and ArtifactSha256（产物哈希） models.

---

## File Structure

- Create `src/boardroom_os/workspace/source_inventory.py`
  - Own all SourceInventory（源码清单）types and builder validation.
  - Import `PackageContract`（包合同）, `PackageAssembly`（项目包装配结果）, `PackageArtifactKind`（包产物类型）, `TicketId`（任务 ID）, `ProviderAttemptRef`（模型调用尝试引用）, `VerifiedEvidenceRef`（已验证证据引用）, and `ArtifactSha256`（产物哈希）.
  - Do not import runtime, provider executor, checker, command runner, or git adapters.
- Modify `src/boardroom_os/workspace/__init__.py`
  - Export V2-060C public SourceInventory（源码清单）types.
- Create `tests/negative/test_source_inventory_ref_only_rejected.py`
  - Backlog-required negative/fail-closed tests first.
- Create `tests/proving/test_source_inventory.py`
  - Package/contract consistency tests and happy path tests.
- Modify `doc/04-implementation/INDEX.md`
  - Add this implementation plan entry.
- Modify after implementation verification only:
  - `doc/04-implementation/backlog.md`
  - `doc/04-implementation/acceptance-criteria.md`
  - `doc/05-project-log/2026-05.md`

---

### Task 1: Add backlog-required fail-closed tests

**Files:**
- Create: `tests/negative/test_source_inventory_ref_only_rejected.py`
- No production code yet.

- [ ] **Step 1: Write failing negative tests**

Create `tests/negative/test_source_inventory_ref_only_rejected.py` with this content:

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
from boardroom_os.evidence.verifier import VerifiedEvidenceRef
from boardroom_os.execution.context_index import ProviderAttemptRef
from boardroom_os.graph.ticket import TicketId
from boardroom_os.workspace.assembler import PackageArtifact, PackageArtifactKind, PackageArtifactPath, assemble_package
from boardroom_os.workspace.manifest import WorkflowRef, WorkspacePath, build_workspace_manifest

_VERIFY_ERRORS = (ValueError, ValidationError)
_SHA = "a" * 64


def _profile() -> MethodologyProfile:
    template_kind = MethodologyTemplateKind.HYBRID
    return MethodologyProfile(
        methodology_profile_id=ContractId(value="methodology-profile.source-inventory"),
        project_charter_ref=ContractId(value="project.charter.source-inventory"),
        template_kind=template_kind,
        documentation_density=DocumentationDensity.STANDARD,
        docs_template_key=docs_template_key_for(template_kind),
        documentation_obligations=default_documentation_obligations_for(template_kind),
    )


def _surface(surface_ref: str, paths: tuple[str, ...], acceptance_refs: tuple[str, ...]) -> SourceSurface:
    return SourceSurface(
        source_surface_ref=SourceSurfaceRef(value=surface_ref),
        name=surface_ref.replace("-", " ").title(),
        paths=paths,
        owned_by=OwnerSeatRef(value="worker-source-inventory"),
        acceptance_refs=tuple(AcceptanceRef(value=ref) for ref in acceptance_refs),
        required_tests=(RequiredTestRef(value="pytest-source-inventory"),),
    )


def _command(command_id: str) -> PackageCommand:
    return PackageCommand(
        command_id=ContractId(value=command_id),
        label=command_id,
        command=("python", "-m", "pytest"),
        cwd=".",
    )


def _package_contract():
    profile = _profile()
    return create_package_contract(
        methodology_registry=MethodologyProfileRegistry.from_profiles(profile),
        package_contract_id=ContractId(value="package-contract.source-inventory"),
        project_charter_ref=ContractId(value="project.charter.source-inventory"),
        package_root="10-project",
        project_type=PackageProjectType.SOFTWARE,
        source_surfaces=(
            _surface("backend-api", ("backend/",), ("AC-BACKEND",)),
            _surface("frontend-ui", ("frontend/",), ("AC-FRONTEND",)),
            _surface("package-tests", ("tests/",), ("AC-TESTS",)),
            _surface("run-manifest", ("run-manifest.json",), ("AC-RUN",)),
            _surface("project-docs", ("docs/",), ("AC-DOCS",)),
        ),
        run_commands=(_command("run-source-inventory"),),
        test_commands=(_command("test-source-inventory"),),
        integration_boundaries=(IntegrationBoundary(value="local-http-api"),),
        docs_required=True,
        closeout_required=True,
        methodology_profile_ref=profile.methodology_profile_id,
        docs_template_key=profile.docs_template_key,
        documentation_obligations=profile.documentation_obligations,
    )


def _artifact(relative_path: str, kind: PackageArtifactKind, surface_ref: str = "backend-api", acceptance_ref: str = "AC-BACKEND") -> PackageArtifact:
    if kind in {PackageArtifactKind.README, PackageArtifactKind.AGENTS}:
        return PackageArtifact(relative_path=PackageArtifactPath(value=relative_path), artifact_kind=kind)
    return PackageArtifact(
        relative_path=PackageArtifactPath(value=relative_path),
        artifact_kind=kind,
        source_surface_refs=(SourceSurfaceRef(value=surface_ref),),
        acceptance_refs=(AcceptanceRef(value=acceptance_ref),),
    )


def _package_assembly():
    package_contract = _package_contract()
    workspace_manifest = build_workspace_manifest(
        workflow_ref=WorkflowRef(value="workflow-source-inventory"),
        workspace_root=WorkspacePath(value="workspace/workflow-source-inventory"),
        package_contract=package_contract,
    )
    return assemble_package(
        workspace_manifest=workspace_manifest,
        package_contract=package_contract,
        artifacts=(
            _artifact("README.md", PackageArtifactKind.README),
            _artifact("AGENTS.md", PackageArtifactKind.AGENTS),
            _artifact("package-contract.json", PackageArtifactKind.PACKAGE_CONTRACT),
            _artifact("run-manifest.json", PackageArtifactKind.RUN_MANIFEST, "run-manifest", "AC-RUN"),
            _artifact("backend/app.py", PackageArtifactKind.SOURCE, "backend-api", "AC-BACKEND"),
            _artifact("frontend/App.tsx", PackageArtifactKind.SOURCE, "frontend-ui", "AC-FRONTEND"),
            _artifact("tests/test_app.py", PackageArtifactKind.TEST, "package-tests", "AC-TESTS"),
            _artifact("docs/usage.md", PackageArtifactKind.DOC, "project-docs", "AC-DOCS"),
        ),
    )


def _source_file(path: str = "backend/app.py", sha256: str = _SHA):
    from boardroom_os.workspace.source_inventory import SourceFilePath, SourceFileRecord

    return SourceFileRecord(path=SourceFilePath(value=path), sha256=sha256)


def _lineage(
    path: str = "backend/app.py",
    surface_ref: str = "backend-api",
    acceptance_ref: str = "AC-BACKEND",
    *,
    producer_ticket_ref: TicketId | None = None,
    producer_attempt_ref: ProviderAttemptRef | None = None,
    evidence_refs: tuple[VerifiedEvidenceRef, ...] | None = None,
):
    from boardroom_os.workspace.source_inventory import SourceFilePath, SourceLineageRecord

    return SourceLineageRecord(
        path=SourceFilePath(value=path),
        source_surface_ref=SourceSurfaceRef(value=surface_ref),
        producer_ticket_ref=producer_ticket_ref or TicketId(value="ticket.backend"),
        producer_attempt_ref=producer_attempt_ref or ProviderAttemptRef(value="provider-attempt.backend.1"),
        acceptance_refs=(AcceptanceRef(value=acceptance_ref),),
        evidence_refs=evidence_refs or (VerifiedEvidenceRef(value="verified-evidence.backend"),),
    )


def _build(*, source_files=None, lineage_records=None, package_commit_ref="commit.source-inventory"):
    from boardroom_os.workspace.source_inventory import PackageCommitRef, build_source_inventory

    return build_source_inventory(
        package_assembly=_package_assembly(),
        package_contract=_package_contract(),
        package_commit_ref=PackageCommitRef(value=package_commit_ref),
        source_files=source_files if source_files is not None else (_source_file(),),
        lineage_records=lineage_records if lineage_records is not None else (_lineage(),),
    )


def test_source_inventory_rejects_ref_only_package_assembly() -> None:
    with pytest.raises(_VERIFY_ERRORS, match="source files|lineage|ref-only"):
        _build(source_files=(), lineage_records=())


def test_source_inventory_rejects_source_file_without_sha256() -> None:
    from boardroom_os.workspace.source_inventory import SourceFilePath, SourceFileRecord

    with pytest.raises(_VERIFY_ERRORS, match="sha256|Field required"):
        SourceFileRecord.model_validate({"path": SourceFilePath(value="backend/app.py")})


def test_source_inventory_rejects_malformed_sha256() -> None:
    with pytest.raises(_VERIFY_ERRORS, match="sha256"):
        _source_file(sha256="ABC")


def test_source_inventory_rejects_lineage_without_producer_ticket_ref() -> None:
    from boardroom_os.workspace.source_inventory import SourceFilePath, SourceLineageRecord

    with pytest.raises(_VERIFY_ERRORS, match="producer_ticket_ref|Field required"):
        SourceLineageRecord.model_validate(
            {
                "path": SourceFilePath(value="backend/app.py"),
                "source_surface_ref": SourceSurfaceRef(value="backend-api"),
                "producer_attempt_ref": ProviderAttemptRef(value="provider-attempt.backend.1"),
                "acceptance_refs": (AcceptanceRef(value="AC-BACKEND"),),
                "evidence_refs": (VerifiedEvidenceRef(value="verified-evidence.backend"),),
            }
        )


def test_source_inventory_rejects_lineage_without_producer_attempt_ref() -> None:
    from boardroom_os.workspace.source_inventory import SourceFilePath, SourceLineageRecord

    with pytest.raises(_VERIFY_ERRORS, match="producer_attempt_ref|Field required"):
        SourceLineageRecord.model_validate(
            {
                "path": SourceFilePath(value="backend/app.py"),
                "source_surface_ref": SourceSurfaceRef(value="backend-api"),
                "producer_ticket_ref": TicketId(value="ticket.backend"),
                "acceptance_refs": (AcceptanceRef(value="AC-BACKEND"),),
                "evidence_refs": (VerifiedEvidenceRef(value="verified-evidence.backend"),),
            }
        )


def test_source_inventory_rejects_lineage_without_acceptance_refs() -> None:
    from boardroom_os.workspace.source_inventory import SourceFilePath, SourceLineageRecord

    with pytest.raises(_VERIFY_ERRORS, match="acceptance refs|Field required"):
        SourceLineageRecord.model_validate(
            {
                "path": SourceFilePath(value="backend/app.py"),
                "source_surface_ref": SourceSurfaceRef(value="backend-api"),
                "producer_ticket_ref": TicketId(value="ticket.backend"),
                "producer_attempt_ref": ProviderAttemptRef(value="provider-attempt.backend.1"),
                "evidence_refs": (VerifiedEvidenceRef(value="verified-evidence.backend"),),
            }
        )


def test_source_inventory_rejects_lineage_without_evidence_refs() -> None:
    from boardroom_os.workspace.source_inventory import SourceFilePath, SourceLineageRecord

    with pytest.raises(_VERIFY_ERRORS, match="evidence refs|Field required"):
        SourceLineageRecord.model_validate(
            {
                "path": SourceFilePath(value="backend/app.py"),
                "source_surface_ref": SourceSurfaceRef(value="backend-api"),
                "producer_ticket_ref": TicketId(value="ticket.backend"),
                "producer_attempt_ref": ProviderAttemptRef(value="provider-attempt.backend.1"),
                "acceptance_refs": (AcceptanceRef(value="AC-BACKEND"),),
            }
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH="src:." python -m pytest tests/negative/test_source_inventory_ref_only_rejected.py -q`

Expected: FAIL with `ModuleNotFoundError: No module named 'boardroom_os.workspace.source_inventory'`.

---

### Task 2: Add SourceInventory models and pass required-field negatives

**Files:**
- Create: `src/boardroom_os/workspace/source_inventory.py`
- Modify: `src/boardroom_os/workspace/__init__.py`
- Test: `tests/negative/test_source_inventory_ref_only_rejected.py`

- [ ] **Step 1: Implement initial models and ref-only builder guard**

Create `src/boardroom_os/workspace/source_inventory.py` with this content:

```python
from __future__ import annotations

from pathlib import PurePosixPath, PureWindowsPath
from typing import Self

from pydantic import BaseModel, ConfigDict, field_serializer, field_validator, model_validator

from boardroom_os.contracts.package import PackageContract
from boardroom_os.contracts.types import AcceptanceRef, ContractId, NonEmptyTextValue, SourceSurfaceRef
from boardroom_os.evidence.verifier import ArtifactSha256, VerifiedEvidenceRef
from boardroom_os.execution.context_index import ProviderAttemptRef
from boardroom_os.graph.ticket import TicketId
from boardroom_os.workspace.assembler import PackageArtifactKind, PackageAssembly, PackageAssemblyRef
from boardroom_os.workspace.manifest import WorkspacePath


class SourceInventoryError(ValueError):
    pass


class SourceInventoryRef(NonEmptyTextValue):
    pass


class PackageCommitRef(NonEmptyTextValue):
    pass


class SourceFilePath(NonEmptyTextValue):
    @field_validator("value")
    @classmethod
    def _reject_unsafe_source_file_path(cls, value: str) -> str:
        normalized = super()._reject_empty_value(value)
        if "\\" in normalized:
            raise ValueError("source file path must use forward slashes")
        if normalized.endswith("/"):
            raise ValueError("source file path must name a file")
        if PurePosixPath(normalized).is_absolute() or PureWindowsPath(normalized).drive:
            raise ValueError("source file path must be relative to package root")

        segments = normalized.split("/")
        if any(segment in {"", ".", ".."} for segment in segments):
            raise ValueError("source file path must not contain empty, current, or parent segments")
        if segments[0] in {"00-boardroom", "10-project", "20-evidence", "30-audit"}:
            raise ValueError("source file path must be relative to workspace package root 10-project")
        if normalized == "src/boardroom_os" or normalized.startswith("src/boardroom_os/"):
            raise ValueError("source file path must not target framework repository layout")
        if segments[0] in {"doc", "scripts", "examples"}:
            raise ValueError("source file path must not target framework repository layout")
        return normalized


class SourceFileRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    path: SourceFilePath
    sha256: ArtifactSha256


class SourceLineageRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    path: SourceFilePath
    source_surface_ref: SourceSurfaceRef
    producer_ticket_ref: TicketId
    producer_attempt_ref: ProviderAttemptRef
    acceptance_refs: tuple[AcceptanceRef, ...]
    evidence_refs: tuple[VerifiedEvidenceRef, ...]

    @field_validator("acceptance_refs")
    @classmethod
    def _reject_empty_acceptance_refs(cls, values: tuple[AcceptanceRef, ...]) -> tuple[AcceptanceRef, ...]:
        if not values:
            raise ValueError("acceptance refs must not be empty")
        return values

    @field_validator("evidence_refs")
    @classmethod
    def _reject_empty_evidence_refs(cls, values: tuple[VerifiedEvidenceRef, ...]) -> tuple[VerifiedEvidenceRef, ...]:
        if not values:
            raise ValueError("evidence refs must not be empty")
        return values


class SourceInventoryEntry(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    path: SourceFilePath
    sha256: ArtifactSha256
    source_surface_ref: SourceSurfaceRef
    producer_ticket_ref: TicketId
    producer_attempt_ref: ProviderAttemptRef
    acceptance_refs: tuple[AcceptanceRef, ...]
    evidence_refs: tuple[VerifiedEvidenceRef, ...]

    @field_validator("acceptance_refs")
    @classmethod
    def _reject_empty_acceptance_refs(cls, values: tuple[AcceptanceRef, ...]) -> tuple[AcceptanceRef, ...]:
        if not values:
            raise ValueError("acceptance refs must not be empty")
        return values

    @field_validator("evidence_refs")
    @classmethod
    def _reject_empty_evidence_refs(cls, values: tuple[VerifiedEvidenceRef, ...]) -> tuple[VerifiedEvidenceRef, ...]:
        if not values:
            raise ValueError("evidence refs must not be empty")
        return values


class SourceInventory(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    source_inventory_id: SourceInventoryRef
    package_assembly_ref: PackageAssemblyRef
    package_contract_ref: ContractId
    package_commit_ref: PackageCommitRef
    package_root: WorkspacePath
    entries: tuple[SourceInventoryEntry, ...]

    @field_validator("entries")
    @classmethod
    def _reject_empty_entries(cls, values: tuple[SourceInventoryEntry, ...]) -> tuple[SourceInventoryEntry, ...]:
        if not values:
            raise ValueError("entries must not be empty")
        return values

    @field_serializer("source_inventory_id", "package_assembly_ref", "package_contract_ref", "package_commit_ref", "package_root")
    def _serialize_refs(self, value: SourceInventoryRef | PackageAssemblyRef | ContractId | PackageCommitRef | WorkspacePath) -> dict[str, str]:
        return value.model_dump()


def build_source_inventory(
    *,
    package_assembly: PackageAssembly,
    package_contract: PackageContract,
    package_commit_ref: PackageCommitRef,
    source_files: tuple[SourceFileRecord, ...],
    lineage_records: tuple[SourceLineageRecord, ...],
) -> SourceInventory:
    if not source_files or not lineage_records:
        raise SourceInventoryError("source inventory cannot be ref-only; source files and lineage records are required")
    if package_assembly.package_contract_ref != package_contract.package_contract_id:
        raise SourceInventoryError("package assembly package_contract_ref must match package contract")
    if package_assembly.package_root.value != package_contract.package_root or package_contract.package_root != "10-project":
        raise SourceInventoryError("package root must be 10-project")

    entries = tuple(
        SourceInventoryEntry(
            path=source_file.path,
            sha256=source_file.sha256,
            source_surface_ref=lineage_records[0].source_surface_ref,
            producer_ticket_ref=lineage_records[0].producer_ticket_ref,
            producer_attempt_ref=lineage_records[0].producer_attempt_ref,
            acceptance_refs=lineage_records[0].acceptance_refs,
            evidence_refs=lineage_records[0].evidence_refs,
        )
        for source_file in source_files
    )
    return SourceInventory(
        source_inventory_id=SourceInventoryRef(
            value=f"source-inventory.{package_assembly.package_assembly_id.value}.{package_commit_ref.value}"
        ),
        package_assembly_ref=package_assembly.package_assembly_id,
        package_contract_ref=package_contract.package_contract_id,
        package_commit_ref=package_commit_ref,
        package_root=package_assembly.package_root,
        entries=entries,
    )
```

- [ ] **Step 2: Export public objects**

Modify `src/boardroom_os/workspace/__init__.py` by adding imports:

```python
from boardroom_os.workspace.source_inventory import (
    PackageCommitRef,
    SourceFilePath,
    SourceFileRecord,
    SourceInventory,
    SourceInventoryEntry,
    SourceInventoryError,
    SourceInventoryRef,
    SourceLineageRecord,
    build_source_inventory,
)
```

Add these names to `__all__`:

```python
    "PackageCommitRef",
    "SourceFilePath",
    "SourceFileRecord",
    "SourceInventory",
    "SourceInventoryEntry",
    "SourceInventoryError",
    "SourceInventoryRef",
    "SourceLineageRecord",
    "build_source_inventory",
```

- [ ] **Step 3: Run tests to verify required-field negatives pass**

Run: `PYTHONPATH="src:." python -m pytest tests/negative/test_source_inventory_ref_only_rejected.py -q`

Expected: PASS for the initial negative suite.

---

### Task 3: Add package/path/lineage consistency negative tests

**Files:**
- Modify: `tests/negative/test_source_inventory_ref_only_rejected.py`
- Modify: `src/boardroom_os/workspace/source_inventory.py`

- [ ] **Step 1: Append failing consistency tests**

Append this content to `tests/negative/test_source_inventory_ref_only_rejected.py`:

```python

@pytest.mark.parametrize(
    "bad_path",
    [
        "/tmp/app.py",
        "../app.py",
        "backend\\app.py",
        "10-project/backend/app.py",
        "20-evidence/source.json",
        "30-audit/process-audit.md",
        "src/boardroom_os/runtime.py",
        "doc/source.md",
        "scripts/build.py",
        "examples/demo.py",
    ],
)
def test_source_file_path_rejects_paths_outside_package_root_or_framework_paths(bad_path: str) -> None:
    from boardroom_os.workspace.source_inventory import SourceFilePath

    with pytest.raises(_VERIFY_ERRORS, match="source file path|package root|framework|relative|parent"):
        SourceFilePath(value=bad_path)


def test_source_inventory_rejects_duplicate_source_file_paths() -> None:
    with pytest.raises(_VERIFY_ERRORS, match="source file paths must be unique"):
        _build(source_files=(_source_file(), _source_file()), lineage_records=(_lineage(),))


def test_source_inventory_rejects_duplicate_lineage_paths() -> None:
    with pytest.raises(_VERIFY_ERRORS, match="lineage paths must be unique"):
        _build(source_files=(_source_file(),), lineage_records=(_lineage(), _lineage()))


def test_source_inventory_rejects_source_file_missing_lineage() -> None:
    with pytest.raises(_VERIFY_ERRORS, match="missing lineage"):
        _build(source_files=(_source_file("backend/app.py"),), lineage_records=(_lineage("frontend/App.tsx", "frontend-ui", "AC-FRONTEND"),))


def test_source_inventory_rejects_lineage_for_unknown_source_file() -> None:
    with pytest.raises(_VERIFY_ERRORS, match="lineage path is missing source file"):
        _build(
            source_files=(_source_file("backend/app.py"),),
            lineage_records=(
                _lineage("backend/app.py"),
                _lineage("frontend/App.tsx", "frontend-ui", "AC-FRONTEND"),
            ),
        )


def test_source_inventory_rejects_lineage_path_not_in_package_assembly() -> None:
    with pytest.raises(_VERIFY_ERRORS, match="lineage path is not in package assembly"):
        _build(source_files=(_source_file("backend/ghost.py"),), lineage_records=(_lineage("backend/ghost.py"),))


def test_source_inventory_rejects_missing_implementation_bearing_artifact_entry() -> None:
    with pytest.raises(_VERIFY_ERRORS, match="missing source inventory entry"):
        _build(source_files=(_source_file("backend/app.py"),), lineage_records=(_lineage("backend/app.py"),))


def test_source_inventory_rejects_unknown_source_surface_ref() -> None:
    with pytest.raises(_VERIFY_ERRORS, match="unknown source surface"):
        _build(source_files=(_source_file(),), lineage_records=(_lineage(surface_ref="unknown-surface"),))


def test_source_inventory_rejects_acceptance_ref_outside_source_surface() -> None:
    with pytest.raises(_VERIFY_ERRORS, match="acceptance refs outside source surface"):
        _build(source_files=(_source_file(),), lineage_records=(_lineage(acceptance_ref="AC-FRONTEND"),))


def test_source_inventory_rejects_source_surface_not_compatible_with_package_artifact() -> None:
    with pytest.raises(_VERIFY_ERRORS, match="source surface is not compatible"):
        _build(
            source_files=(_source_file("backend/app.py"),),
            lineage_records=(_lineage("backend/app.py", "frontend-ui", "AC-FRONTEND"),),
        )


def test_source_inventory_rejects_acceptance_refs_that_do_not_cover_package_artifact() -> None:
    with pytest.raises(_VERIFY_ERRORS, match="acceptance refs do not cover package artifact"):
        _build(
            source_files=(_source_file("backend/app.py"),),
            lineage_records=(_lineage("backend/app.py", "backend-api", "AC-OTHER"),),
        )


def test_source_inventory_rejects_package_contract_mismatch() -> None:
    from boardroom_os.workspace.source_inventory import PackageCommitRef, build_source_inventory

    package_contract = _package_contract()
    other_contract = package_contract.model_copy(update={"package_contract_id": ContractId(value="package-contract.other")})

    with pytest.raises(_VERIFY_ERRORS, match="package_contract_ref"):
        build_source_inventory(
            package_assembly=_package_assembly(),
            package_contract=other_contract,
            package_commit_ref=PackageCommitRef(value="commit.source-inventory"),
            source_files=(_source_file(),),
            lineage_records=(_lineage(),),
        )


def test_source_inventory_rejects_empty_package_commit_ref() -> None:
    from boardroom_os.workspace.source_inventory import PackageCommitRef

    with pytest.raises(_VERIFY_ERRORS, match="value must not be empty"):
        PackageCommitRef(value=" ")


def test_source_inventory_models_reject_extra_fields() -> None:
    from boardroom_os.workspace.source_inventory import SourceFileRecord

    with pytest.raises(_VERIFY_ERRORS, match="Extra inputs"):
        SourceFileRecord.model_validate(
            {
                "path": {"value": "backend/app.py"},
                "sha256": {"value": _SHA},
                "unexpected": "field",
            }
        )
```

- [ ] **Step 2: Run tests to verify new consistency tests fail**

Run: `PYTHONPATH="src:." python -m pytest tests/negative/test_source_inventory_ref_only_rejected.py -q`

Expected: FAIL on semantic validation tests because the builder is still minimal.

- [ ] **Step 3: Implement full builder validation**

Replace `build_source_inventory` in `src/boardroom_os/workspace/source_inventory.py` with:

```python
def build_source_inventory(
    *,
    package_assembly: PackageAssembly,
    package_contract: PackageContract,
    package_commit_ref: PackageCommitRef,
    source_files: tuple[SourceFileRecord, ...],
    lineage_records: tuple[SourceLineageRecord, ...],
) -> SourceInventory:
    if not source_files or not lineage_records:
        raise SourceInventoryError("source inventory cannot be ref-only; source files and lineage records are required")
    if package_assembly.package_contract_ref != package_contract.package_contract_id:
        raise SourceInventoryError("package assembly package_contract_ref must match package contract")
    if package_assembly.package_root.value != package_contract.package_root or package_contract.package_root != "10-project":
        raise SourceInventoryError("package root must be 10-project")

    source_files_by_path = _unique_source_files_by_path(source_files)
    lineage_by_path = _unique_lineage_by_path(lineage_records)
    _validate_source_and_lineage_paths(source_files_by_path, lineage_by_path)

    artifacts_by_path = {artifact.relative_path.value: artifact for artifact in package_assembly.artifacts}
    implementation_artifact_paths = {
        artifact.relative_path.value
        for artifact in package_assembly.artifacts
        if artifact.artifact_kind in _IMPLEMENTATION_BEARING_ARTIFACT_KINDS
    }
    source_surfaces_by_ref = {surface.source_surface_ref.value: surface for surface in package_contract.source_surfaces}

    entries: list[SourceInventoryEntry] = []
    for path in sorted(source_files_by_path):
        if path not in implementation_artifact_paths:
            raise SourceInventoryError("lineage path is not in package assembly implementation artifacts")
        source_file = source_files_by_path[path]
        lineage = lineage_by_path[path]
        artifact = artifacts_by_path[path]
        surface = source_surfaces_by_ref.get(lineage.source_surface_ref.value)
        if surface is None:
            raise SourceInventoryError(f"unknown source surface ref: {lineage.source_surface_ref.value}")
        if lineage.source_surface_ref not in artifact.source_surface_refs:
            raise SourceInventoryError("source surface is not compatible with package artifact")

        surface_acceptance_refs = {acceptance_ref.value for acceptance_ref in surface.acceptance_refs}
        lineage_acceptance_refs = {acceptance_ref.value for acceptance_ref in lineage.acceptance_refs}
        artifact_acceptance_refs = {acceptance_ref.value for acceptance_ref in artifact.acceptance_refs}
        if not lineage_acceptance_refs.issubset(surface_acceptance_refs):
            raise SourceInventoryError("lineage acceptance refs outside source surface")
        if not artifact_acceptance_refs.issubset(lineage_acceptance_refs):
            raise SourceInventoryError("source inventory acceptance refs do not cover package artifact")

        entries.append(
            SourceInventoryEntry(
                path=source_file.path,
                sha256=source_file.sha256,
                source_surface_ref=lineage.source_surface_ref,
                producer_ticket_ref=lineage.producer_ticket_ref,
                producer_attempt_ref=lineage.producer_attempt_ref,
                acceptance_refs=lineage.acceptance_refs,
                evidence_refs=lineage.evidence_refs,
            )
        )

    entry_paths = {entry.path.value for entry in entries}
    missing_paths = implementation_artifact_paths - entry_paths
    if missing_paths:
        raise SourceInventoryError(f"missing source inventory entry for {sorted(missing_paths)[0]}")

    return SourceInventory(
        source_inventory_id=SourceInventoryRef(
            value=f"source-inventory.{package_assembly.package_assembly_id.value}.{package_commit_ref.value}"
        ),
        package_assembly_ref=package_assembly.package_assembly_id,
        package_contract_ref=package_contract.package_contract_id,
        package_commit_ref=package_commit_ref,
        package_root=package_assembly.package_root,
        entries=tuple(entries),
    )


_IMPLEMENTATION_BEARING_ARTIFACT_KINDS = frozenset(
    {
        PackageArtifactKind.SOURCE,
        PackageArtifactKind.TEST,
        PackageArtifactKind.DOC,
    }
)


def _unique_source_files_by_path(source_files: tuple[SourceFileRecord, ...]) -> dict[str, SourceFileRecord]:
    by_path: dict[str, SourceFileRecord] = {}
    for source_file in source_files:
        path = source_file.path.value
        if path in by_path:
            raise SourceInventoryError("source file paths must be unique")
        by_path[path] = source_file
    return by_path


def _unique_lineage_by_path(lineage_records: tuple[SourceLineageRecord, ...]) -> dict[str, SourceLineageRecord]:
    by_path: dict[str, SourceLineageRecord] = {}
    for lineage in lineage_records:
        path = lineage.path.value
        if path in by_path:
            raise SourceInventoryError("lineage paths must be unique")
        by_path[path] = lineage
    return by_path


def _validate_source_and_lineage_paths(
    source_files_by_path: dict[str, SourceFileRecord],
    lineage_by_path: dict[str, SourceLineageRecord],
) -> None:
    source_paths = set(source_files_by_path)
    lineage_paths = set(lineage_by_path)
    missing_lineage = source_paths - lineage_paths
    if missing_lineage:
        raise SourceInventoryError("source file is missing lineage")
    missing_source_file = lineage_paths - source_paths
    if missing_source_file:
        raise SourceInventoryError("lineage path is missing source file")
```

- [ ] **Step 4: Run tests to verify negative suite passes**

Run: `PYTHONPATH="src:." python -m pytest tests/negative/test_source_inventory_ref_only_rejected.py -q`

Expected: PASS.

---

### Task 4: Add happy path and serialization tests

**Files:**
- Create: `tests/proving/test_source_inventory.py`
- Modify: `src/boardroom_os/workspace/source_inventory.py` only if tests expose a gap.

- [ ] **Step 1: Write happy path tests**

Create `tests/proving/test_source_inventory.py` with this content:

```python
from __future__ import annotations

from boardroom_os.contracts.methodology import (
    DocumentationDensity,
    MethodologyProfile,
    MethodologyProfileRegistry,
    MethodologyTemplateKind,
    default_documentation_obligations_for,
    docs_template_key_for,
)
from boardroom_os.contracts.package import IntegrationBoundary, PackageCommand, PackageProjectType, create_package_contract
from boardroom_os.contracts.source_surface import OwnerSeatRef, RequiredTestRef, SourceSurface
from boardroom_os.contracts.types import AcceptanceRef, ContractId, SourceSurfaceRef
from boardroom_os.evidence.verifier import VerifiedEvidenceRef
from boardroom_os.execution.context_index import ProviderAttemptRef
from boardroom_os.graph.ticket import TicketId
from boardroom_os.workspace.assembler import PackageArtifact, PackageArtifactKind, PackageArtifactPath, assemble_package
from boardroom_os.workspace.manifest import WorkflowRef, WorkspacePath, build_workspace_manifest
from boardroom_os.workspace.source_inventory import (
    PackageCommitRef,
    SourceFilePath,
    SourceFileRecord,
    SourceLineageRecord,
    build_source_inventory,
)


def _profile() -> MethodologyProfile:
    template_kind = MethodologyTemplateKind.HYBRID
    return MethodologyProfile(
        methodology_profile_id=ContractId(value="methodology-profile.source-inventory-happy"),
        project_charter_ref=ContractId(value="project.charter.source-inventory-happy"),
        template_kind=template_kind,
        documentation_density=DocumentationDensity.STANDARD,
        docs_template_key=docs_template_key_for(template_kind),
        documentation_obligations=default_documentation_obligations_for(template_kind),
    )


def _surface(surface_ref: str, paths: tuple[str, ...], acceptance_refs: tuple[str, ...]) -> SourceSurface:
    return SourceSurface(
        source_surface_ref=SourceSurfaceRef(value=surface_ref),
        name=surface_ref.replace("-", " ").title(),
        paths=paths,
        owned_by=OwnerSeatRef(value="worker-source-inventory"),
        acceptance_refs=tuple(AcceptanceRef(value=ref) for ref in acceptance_refs),
        required_tests=(RequiredTestRef(value="pytest-source-inventory"),),
    )


def _command(command_id: str) -> PackageCommand:
    return PackageCommand(
        command_id=ContractId(value=command_id),
        label=command_id,
        command=("python", "-m", "pytest"),
        cwd=".",
    )


def _package_contract():
    profile = _profile()
    return create_package_contract(
        methodology_registry=MethodologyProfileRegistry.from_profiles(profile),
        package_contract_id=ContractId(value="package-contract.source-inventory-happy"),
        project_charter_ref=ContractId(value="project.charter.source-inventory-happy"),
        package_root="10-project",
        project_type=PackageProjectType.SOFTWARE,
        source_surfaces=(
            _surface("backend-api", ("backend/",), ("AC-BACKEND",)),
            _surface("frontend-ui", ("frontend/",), ("AC-FRONTEND",)),
            _surface("package-tests", ("tests/",), ("AC-TESTS",)),
            _surface("run-manifest", ("run-manifest.json",), ("AC-RUN",)),
            _surface("project-docs", ("docs/",), ("AC-DOCS",)),
        ),
        run_commands=(_command("run-source-inventory"),),
        test_commands=(_command("test-source-inventory"),),
        integration_boundaries=(IntegrationBoundary(value="local-http-api"),),
        docs_required=True,
        closeout_required=True,
        methodology_profile_ref=profile.methodology_profile_id,
        docs_template_key=profile.docs_template_key,
        documentation_obligations=profile.documentation_obligations,
    )


def _artifact(relative_path: str, kind: PackageArtifactKind, surface_ref: str = "backend-api", acceptance_ref: str = "AC-BACKEND") -> PackageArtifact:
    if kind in {PackageArtifactKind.README, PackageArtifactKind.AGENTS}:
        return PackageArtifact(relative_path=PackageArtifactPath(value=relative_path), artifact_kind=kind)
    return PackageArtifact(
        relative_path=PackageArtifactPath(value=relative_path),
        artifact_kind=kind,
        source_surface_refs=(SourceSurfaceRef(value=surface_ref),),
        acceptance_refs=(AcceptanceRef(value=acceptance_ref),),
    )


def _package_assembly(package_contract):
    workspace_manifest = build_workspace_manifest(
        workflow_ref=WorkflowRef(value="workflow-source-inventory-happy"),
        workspace_root=WorkspacePath(value="workspace/workflow-source-inventory-happy"),
        package_contract=package_contract,
    )
    return assemble_package(
        workspace_manifest=workspace_manifest,
        package_contract=package_contract,
        artifacts=(
            _artifact("README.md", PackageArtifactKind.README),
            _artifact("AGENTS.md", PackageArtifactKind.AGENTS),
            _artifact("package-contract.json", PackageArtifactKind.PACKAGE_CONTRACT),
            _artifact("run-manifest.json", PackageArtifactKind.RUN_MANIFEST, "run-manifest", "AC-RUN"),
            _artifact("backend/app.py", PackageArtifactKind.SOURCE, "backend-api", "AC-BACKEND"),
            _artifact("frontend/App.tsx", PackageArtifactKind.SOURCE, "frontend-ui", "AC-FRONTEND"),
            _artifact("tests/test_app.py", PackageArtifactKind.TEST, "package-tests", "AC-TESTS"),
            _artifact("docs/usage.md", PackageArtifactKind.DOC, "project-docs", "AC-DOCS"),
        ),
    )


def _source_file(path: str, sha: str) -> SourceFileRecord:
    return SourceFileRecord(path=SourceFilePath(value=path), sha256=sha)


def _lineage(path: str, surface_ref: str, acceptance_ref: str) -> SourceLineageRecord:
    normalized = path.replace("/", ".").replace("_", "-")
    return SourceLineageRecord(
        path=SourceFilePath(value=path),
        source_surface_ref=SourceSurfaceRef(value=surface_ref),
        producer_ticket_ref=TicketId(value=f"ticket.{normalized}"),
        producer_attempt_ref=ProviderAttemptRef(value=f"provider-attempt.{normalized}.1"),
        acceptance_refs=(AcceptanceRef(value=acceptance_ref),),
        evidence_refs=(VerifiedEvidenceRef(value=f"verified-evidence.{normalized}"),),
    )


def test_source_inventory_builds_deterministic_lineage_for_package_files() -> None:
    package_contract = _package_contract()
    package_assembly = _package_assembly(package_contract)

    inventory = build_source_inventory(
        package_assembly=package_assembly,
        package_contract=package_contract,
        package_commit_ref=PackageCommitRef(value="commit.source-inventory-happy"),
        source_files=(
            _source_file("tests/test_app.py", "c" * 64),
            _source_file("backend/app.py", "a" * 64),
            _source_file("docs/usage.md", "d" * 64),
            _source_file("frontend/App.tsx", "b" * 64),
        ),
        lineage_records=(
            _lineage("frontend/App.tsx", "frontend-ui", "AC-FRONTEND"),
            _lineage("docs/usage.md", "project-docs", "AC-DOCS"),
            _lineage("backend/app.py", "backend-api", "AC-BACKEND"),
            _lineage("tests/test_app.py", "package-tests", "AC-TESTS"),
        ),
    )

    assert inventory.source_inventory_id.value == (
        f"source-inventory.{package_assembly.package_assembly_id.value}.commit.source-inventory-happy"
    )
    assert inventory.package_assembly_ref == package_assembly.package_assembly_id
    assert inventory.package_contract_ref == package_contract.package_contract_id
    assert inventory.package_commit_ref == PackageCommitRef(value="commit.source-inventory-happy")
    assert inventory.package_root.value == "10-project"
    assert tuple(entry.path.value for entry in inventory.entries) == (
        "backend/app.py",
        "docs/usage.md",
        "frontend/App.tsx",
        "tests/test_app.py",
    )
    assert tuple(entry.sha256.value for entry in inventory.entries) == (
        "a" * 64,
        "d" * 64,
        "b" * 64,
        "c" * 64,
    )
    assert inventory.entries[0].producer_ticket_ref == TicketId(value="ticket.backend.app.py")
    assert inventory.entries[0].producer_attempt_ref == ProviderAttemptRef(value="provider-attempt.backend.app.py.1")
    assert inventory.entries[0].evidence_refs == (VerifiedEvidenceRef(value="verified-evidence.backend.app.py"),)


def test_source_inventory_model_dump_is_audit_friendly() -> None:
    package_contract = _package_contract()
    package_assembly = _package_assembly(package_contract)
    inventory = build_source_inventory(
        package_assembly=package_assembly,
        package_contract=package_contract,
        package_commit_ref=PackageCommitRef(value="commit.source-inventory-happy"),
        source_files=(
            _source_file("backend/app.py", "a" * 64),
            _source_file("frontend/App.tsx", "b" * 64),
            _source_file("tests/test_app.py", "c" * 64),
            _source_file("docs/usage.md", "d" * 64),
        ),
        lineage_records=(
            _lineage("backend/app.py", "backend-api", "AC-BACKEND"),
            _lineage("frontend/App.tsx", "frontend-ui", "AC-FRONTEND"),
            _lineage("tests/test_app.py", "package-tests", "AC-TESTS"),
            _lineage("docs/usage.md", "project-docs", "AC-DOCS"),
        ),
    )

    dumped = inventory.model_dump()

    assert dumped["package_root"] == {"value": "10-project"}
    assert dumped["entries"][0]["path"] == {"value": "backend/app.py"}
    assert dumped["entries"][0]["sha256"] == {"value": "a" * 64}
    assert dumped["entries"][0]["producer_ticket_ref"] == {"value": "ticket.backend.app.py"}
    assert dumped["entries"][0]["producer_attempt_ref"] == {"value": "provider-attempt.backend.app.py.1"}
    assert dumped["entries"][0]["acceptance_refs"] == [{"value": "AC-BACKEND"}]
    assert dumped["entries"][0]["evidence_refs"] == [{"value": "verified-evidence.backend.app.py"}]
```

- [ ] **Step 2: Run happy path tests**

Run: `PYTHONPATH="src:." python -m pytest tests/proving/test_source_inventory.py -q`

Expected: PASS.

- [ ] **Step 3: Run V2-060C focused tests**

Run: `PYTHONPATH="src:." python -m pytest tests/negative/test_source_inventory_ref_only_rejected.py tests/proving/test_source_inventory.py -q`

Expected: PASS.

---

### Task 5: Run integration verification and update implementation docs

**Files:**
- Modify: `doc/04-implementation/backlog.md`
- Modify: `doc/04-implementation/acceptance-criteria.md`
- Modify: `doc/05-project-log/2026-05.md`
- Modify: `doc/04-implementation/INDEX.md`

- [ ] **Step 1: Run related verification suite**

Run: `PYTHONPATH="src:." python -m pytest tests/contracts/test_package_contract.py tests/negative/test_package_contract_fail_closed.py tests/proving/test_workspace_manifest.py tests/proving/test_package_assembler.py tests/negative/test_source_inventory_ref_only_rejected.py tests/proving/test_source_inventory.py -q`

Expected: PASS.

Run: `PYTHONPATH="src:." python -m pytest tests/contracts tests/proving/test_workspace_manifest.py tests/proving/test_package_assembler.py tests/negative/test_source_inventory_ref_only_rejected.py tests/proving/test_source_inventory.py -q`

Expected: PASS.

- [ ] **Step 2: Update `doc/04-implementation/backlog.md`**

Change V2-060C status from `TODO` to `DONE`; update TL;DR current unfinished work package from `V2-060C` to `V2-060D`; update Phase 6 progress from `2 / 6` to `3 / 6`; update total from `37 / 53` to `38 / 53`; append completion evidence under V2-060C.

Use this completion evidence text:

```markdown
- 完成证据：2026-05-23 新增 SourceInventory（源码清单）、SourceInventoryEntry（源码清单条目）、SourceFileRecord（源码文件记录）、SourceLineageRecord（源码来源链记录）、SourceFilePath（源码文件路径）、PackageCommitRef（包提交引用）和 build_source_inventory（构建源码清单函数）；保持纯领域模型 + adapter 输入形状，不读取磁盘、不调用 git、不创建目录、不写文件、不导出 `20-evidence`。负例证明 ref-only inventory（只有引用的清单）、缺 sha256、缺 producer_ticket_ref（生产任务引用）、缺 producer_attempt_ref（生产模型尝试引用）、缺 acceptance_refs（验收引用）、缺 evidence_refs（证据引用）、包外路径、重复路径、缺来源链、未知 source surface（源码实现面）、acceptance 越界、source surface 与 package artifact（包产物）不兼容、PackageContract（包合同）错绑和 extra fields（额外字段）均 fail closed；正例证明 backend/frontend/tests/docs 文件可映射到 SourceSurface（源码实现面）、TicketId（任务 ID）、ProviderAttemptRef（模型调用尝试引用）和 VerifiedEvidenceRef（已验证证据引用），并生成 deterministic SourceInventory（确定性源码清单）。验证命令：`PYTHONPATH="src:." python -m pytest tests/negative/test_source_inventory_ref_only_rejected.py tests/proving/test_source_inventory.py -q`；`PYTHONPATH="src:." python -m pytest tests/contracts/test_package_contract.py tests/negative/test_package_contract_fail_closed.py tests/proving/test_workspace_manifest.py tests/proving/test_package_assembler.py tests/negative/test_source_inventory_ref_only_rejected.py tests/proving/test_source_inventory.py -q`；`PYTHONPATH="src:." python -m pytest tests/contracts tests/proving/test_workspace_manifest.py tests/proving/test_package_assembler.py tests/negative/test_source_inventory_ref_only_rejected.py tests/proving/test_source_inventory.py -q`。
```

- [ ] **Step 3: Update `doc/04-implementation/acceptance-criteria.md`**

Change Phase 6 AC-V2-EVIDENCE-002 checkbox to checked:

```markdown
- [x] AC-V2-EVIDENCE-002（source inventory lineage）— 由 V2-060C `test_source_inventory_ref_only_rejected.py` 证明：ref-only / 缺 sha256 / 缺 producer_ticket_ref / 缺 producer_attempt_ref / 缺 acceptance_refs / 缺 evidence_refs 必须失败；`test_source_inventory.py` 证明 backend/frontend/tests/docs 文件可绑定 source surface、producer ticket、provider attempt 和 verified evidence refs
```

Keep remaining Phase 6 boxes unchecked until V2-060D/E/F finish.

- [ ] **Step 4: Update `doc/05-project-log/2026-05.md`**

Append one 2026-05-23 V2-060C entry with output files and verification commands.

- [ ] **Step 5: Update `doc/04-implementation/INDEX.md`**

Add this row below the V2-060C spec row if not already present:

```markdown
| `v2-060c-source-inventory-implementation-plan.md` | V2-060C SourceInventory（源码清单）实施计划 |
```

- [ ] **Step 6: Run final verification after docs update**

Run: `PYTHONPATH="src:." python -m pytest tests/negative/test_source_inventory_ref_only_rejected.py tests/proving/test_source_inventory.py -q`

Expected: PASS.

---

## Self-Review Checklist

- Spec coverage: Tasks cover pure model boundary, TicketId reuse, run-manifest exclusion from V2-060C SourceInventory, ref-only rejection, required lineage fields, package/contract consistency, happy path, exports, and docs protocol.
- Placeholder scan: No `TBD`, `TODO`, or unspecified test steps remain.
- Type consistency: `producer_ticket_ref` uses `TicketId`; `producer_attempt_ref` uses `ProviderAttemptRef`; `evidence_refs` uses `VerifiedEvidenceRef`; `sha256` uses `ArtifactSha256`; `PackageArtifactKind.RUN_MANIFEST` is required by PackageAssembly but excluded from V2-060C implementation-bearing inventory coverage.
