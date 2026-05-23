# V2-060D RunManifest（运行清单）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement V2-060D RunManifest（运行清单） so generated software packages prove their declared run/test commands（运行/测试命令） mirror PackageContract（包合同） and can be bound before CommandRunner（命令执行器） produces VerificationRun（验证运行） evidence.

**Architecture:** Add one focused module, `src/boardroom_os/workspace/run_manifest.py`, containing RunManifest（运行清单） types, command mirror validation, and command binding validation. Keep CommandRunner（命令执行器） and RuntimeExecutor（运行时执行器） signatures unchanged; V2-060D only adds an explicit binding gate that callers use before invoking CommandRunner.

**Tech Stack:** Python 3, Pydantic BaseModel（Pydantic 模型）, pytest, existing Boardroom OS V2 PackageContract（包合同）, PackageCommand（包命令）, WorkspaceManifest（工作区清单）, ExecutionPackage（执行包）, CommandRunner（命令执行器）, and VerificationRun（验证运行） models.

---

## File Structure

- Create `src/boardroom_os/workspace/run_manifest.py`
  - Own RunManifest（运行清单）, RunManifestCommand（运行清单命令）, RunManifestBinding（运行清单绑定）, `build_run_manifest`（构建运行清单函数）, and `validate_run_manifest_binding`（校验运行清单绑定函数）.
  - Import `PackageContract`（包合同）, `PackageCommand`（包命令）, `PackageProjectType`（包项目类型）, `ContractId`（合同 ID）, `NonEmptyTextValue`（非空文本值）, `WorkspaceManifest`（工作区清单）, `WorkspaceManifestRef`（工作区清单引用）, and `WorkspacePath`（工作区路径）.
  - Do not import runtime executor, provider executor, evidence verifier, closeout, git adapters, or filesystem writers.
- Modify `src/boardroom_os/workspace/__init__.py`
  - Export V2-060D public RunManifest（运行清单） types and functions.
- Create `tests/proving/test_run_manifest.py`
  - Backlog-required negative/fail-closed tests first.
  - Include reviewer-requested happy path that calls `validate_run_manifest_binding(...)` before `CommandRunner.run(...)`.
- Modify `doc/04-implementation/INDEX.md`
  - Add this implementation plan entry.
- Modify after implementation verification only:
  - `doc/04-implementation/backlog.md`
  - `doc/04-implementation/acceptance-criteria.md`
  - `doc/05-project-log/2026-05.md`

---

### Task 1: Add backlog-required fail-closed tests

**Files:**
- Create: `tests/proving/test_run_manifest.py`
- No production code yet.

- [ ] **Step 1: Write failing negative tests**

Create `tests/proving/test_run_manifest.py` with this starter content:

```python
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from boardroom_os.adapters.process_runner import CommandRunner, CommandRunnerInput, ProcessResult
from boardroom_os.agents.profiles import ModelExecutionProfile
from boardroom_os.agents.seat import AgentSeatRef
from boardroom_os.contracts.evidence_obligation import EvidenceObligation, RequiredArtifactType
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
from boardroom_os.contracts.types import AcceptanceRef, ContractId, EvidenceObligationRef, SourceSurfaceRef
from boardroom_os.execution.package import (
    AllowedReadRef,
    AllowedWritePath,
    AuditRequirement,
    ContextRef,
    ExecutionPackage,
    ExecutionPackageId,
    FallbackPolicyRef,
    RequiredOutput,
)
from boardroom_os.execution.verification_run import EnvironmentProfileRef, RunnerRef, WorkspaceSnapshotRef
from boardroom_os.graph.ticket import TicketId
from boardroom_os.workspace.manifest import WorkflowRef, WorkspacePath, build_workspace_manifest

_VERIFY_ERRORS = (ValueError, ValidationError)


def _profile() -> MethodologyProfile:
    template_kind = MethodologyTemplateKind.HYBRID
    return MethodologyProfile(
        methodology_profile_id=ContractId(value="methodology-profile.run-manifest"),
        project_charter_ref=ContractId(value="project.charter.run-manifest"),
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
        owned_by=OwnerSeatRef(value="worker-run-manifest"),
        acceptance_refs=tuple(AcceptanceRef(value=ref) for ref in acceptance_refs),
        required_tests=(RequiredTestRef(value="pytest-run-manifest"),),
    )


def _command(command_id: str, *, label: str | None = None, command: tuple[str, ...] | None = None, cwd: str = ".") -> PackageCommand:
    return PackageCommand(
        command_id=ContractId(value=command_id),
        label=label or command_id,
        command=command or (sys.executable, "-c", "print('ok')"),
        cwd=cwd,
    )


def _package_contract(
    *,
    run_commands: tuple[PackageCommand, ...] | None = None,
    test_commands: tuple[PackageCommand, ...] | None = None,
    package_root: str = "10-project",
):
    profile = _profile()
    return create_package_contract(
        methodology_registry=MethodologyProfileRegistry.from_profiles(profile),
        package_contract_id=ContractId(value="package-contract.run-manifest"),
        project_charter_ref=ContractId(value="project.charter.run-manifest"),
        package_root=package_root,
        project_type=PackageProjectType.SOFTWARE,
        source_surfaces=(
            _surface("backend-api", ("backend/",), ("AC-BACKEND",)),
            _surface("package-tests", ("tests/",), ("AC-TESTS",)),
            _surface("run-manifest", ("run-manifest.json",), ("AC-RUN",)),
            _surface("project-docs", ("docs/",), ("AC-DOCS",)),
        ),
        run_commands=(_command("run-package", label="Run package"),) if run_commands is None else run_commands,
        test_commands=(_command("test-package", label="Test package"),) if test_commands is None else test_commands,
        integration_boundaries=(IntegrationBoundary(value="local-process"),),
        docs_required=True,
        closeout_required=True,
        methodology_profile_ref=profile.methodology_profile_id,
        docs_template_key=profile.docs_template_key,
        documentation_obligations=profile.documentation_obligations,
    )


def _workspace_manifest(package_contract=None):
    contract = package_contract or _package_contract()
    return build_workspace_manifest(
        workflow_ref=WorkflowRef(value="workflow-run-manifest"),
        workspace_root=WorkspacePath(value="workspace/workflow-run-manifest"),
        package_contract=contract,
    )


def test_build_run_manifest_rejects_software_package_without_run_commands() -> None:
    from boardroom_os.workspace.run_manifest import build_run_manifest

    package_contract = PackageProjectType.SOFTWARE
    with pytest.raises(_VERIFY_ERRORS, match="run command|run commands"):
        build_run_manifest(
            workspace_manifest=_workspace_manifest(_package_contract(run_commands=())),
            package_contract=_package_contract(run_commands=()),
        )


def test_build_run_manifest_rejects_software_package_without_test_commands() -> None:
    from boardroom_os.workspace.run_manifest import build_run_manifest

    with pytest.raises(_VERIFY_ERRORS, match="test command|test commands"):
        build_run_manifest(
            workspace_manifest=_workspace_manifest(_package_contract(test_commands=())),
            package_contract=_package_contract(test_commands=()),
        )


def test_binding_rejects_runner_command_not_declared_in_run_manifest() -> None:
    from boardroom_os.workspace.run_manifest import build_run_manifest, validate_run_manifest_binding

    package_contract = _package_contract()
    manifest = build_run_manifest(
        workspace_manifest=_workspace_manifest(package_contract),
        package_contract=package_contract,
    )

    with pytest.raises(_VERIFY_ERRORS, match="run manifest|declared"):
        validate_run_manifest_binding(
            run_manifest=manifest,
            package_contract=package_contract,
            command_id=ContractId(value="undeclared-command"),
        )
```

- [ ] **Step 2: Run tests to verify RED**

Run:

```bash
PYTHONPATH="src;." python -m pytest tests/proving/test_run_manifest.py -q
```

Expected: FAIL because `boardroom_os.workspace.run_manifest` does not exist.

---

### Task 2: Implement minimal RunManifest model and builder

**Files:**
- Create: `src/boardroom_os/workspace/run_manifest.py`
- Test: `tests/proving/test_run_manifest.py`

- [ ] **Step 1: Write minimal production code**

Create `src/boardroom_os/workspace/run_manifest.py` with this implementation:

```python
from __future__ import annotations

from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, field_serializer, field_validator, model_validator

from boardroom_os.contracts.package import PackageCommand, PackageContract, PackageProjectType
from boardroom_os.contracts.types import ContractId, NonEmptyTextValue
from boardroom_os.workspace.manifest import WorkspaceManifest, WorkspaceManifestRef, WorkspacePath


class RunManifestError(ValueError):
    pass


class RunManifestRef(NonEmptyTextValue):
    pass


class RunManifestCommandKind(StrEnum):
    RUN = "run"
    TEST = "test"


class RunManifestCommand(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    command_id: ContractId
    kind: RunManifestCommandKind
    label: str
    command: tuple[str, ...]
    cwd: str

    @field_validator("label", "cwd")
    @classmethod
    def _reject_empty_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("text fields must not be empty")
        return normalized

    @field_validator("command")
    @classmethod
    def _reject_empty_command(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(value.strip() for value in values)
        if not normalized:
            raise ValueError("command must not be empty")
        if any(not value for value in normalized):
            raise ValueError("command must not contain empty items")
        return normalized

    @classmethod
    def from_package_command(cls, *, package_command: PackageCommand, kind: RunManifestCommandKind) -> Self:
        return cls(
            command_id=package_command.command_id,
            kind=kind,
            label=package_command.label,
            command=package_command.command,
            cwd=package_command.cwd,
        )


class RunManifest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    run_manifest_id: RunManifestRef
    workspace_manifest_ref: WorkspaceManifestRef
    package_contract_ref: ContractId
    package_root: WorkspacePath
    commands: tuple[RunManifestCommand, ...]

    @field_serializer("run_manifest_id", "workspace_manifest_ref", "package_contract_ref", "package_root")
    def _serialize_refs(
        self,
        value: RunManifestRef | WorkspaceManifestRef | ContractId | WorkspacePath,
    ) -> dict[str, str]:
        return value.model_dump()

    @field_serializer("commands")
    def _serialize_commands(self, values: tuple[RunManifestCommand, ...]) -> list[dict[str, object]]:
        return [value.model_dump() for value in values]

    @field_validator("commands")
    @classmethod
    def _reject_empty_commands(cls, values: tuple[RunManifestCommand, ...]) -> tuple[RunManifestCommand, ...]:
        if not values:
            raise ValueError("run manifest commands must not be empty")
        return values

    @model_validator(mode="after")
    def _validate_unique_command_ids(self) -> Self:
        command_ids = [command.command_id.value for command in self.commands]
        if len(command_ids) != len(set(command_ids)):
            raise ValueError("run manifest command ids must be unique")
        return self


class RunManifestBinding(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    run_manifest_ref: RunManifestRef
    package_contract_ref: ContractId
    command_id: ContractId
    kind: RunManifestCommandKind
    command: tuple[str, ...]
    cwd: str



def build_run_manifest(
    *,
    workspace_manifest: WorkspaceManifest,
    package_contract: PackageContract,
) -> RunManifest:
    _validate_workspace_contract_binding(
        workspace_manifest=workspace_manifest,
        package_contract=package_contract,
    )
    _validate_runnable_package_commands(package_contract)

    commands = tuple(
        sorted(
            (
                *(RunManifestCommand.from_package_command(
                    package_command=command,
                    kind=RunManifestCommandKind.RUN,
                ) for command in package_contract.run_commands),
                *(RunManifestCommand.from_package_command(
                    package_command=command,
                    kind=RunManifestCommandKind.TEST,
                ) for command in package_contract.test_commands),
            ),
            key=lambda command: (command.kind.value, command.command_id.value),
        )
    )

    return RunManifest(
        run_manifest_id=RunManifestRef(
            value=(
                "run-manifest."
                f"{workspace_manifest.workspace_manifest_id.value}."
                f"{package_contract.package_contract_id.value}"
            )
        ),
        workspace_manifest_ref=workspace_manifest.workspace_manifest_id,
        package_contract_ref=package_contract.package_contract_id,
        package_root=workspace_manifest.package_root,
        commands=commands,
    )


def validate_run_manifest_binding(
    *,
    run_manifest: RunManifest,
    package_contract: PackageContract,
    command_id: ContractId,
) -> RunManifestBinding:
    if run_manifest.package_contract_ref != package_contract.package_contract_id:
        raise RunManifestError("run manifest package_contract_ref must match package contract")
    if run_manifest.package_root.value != package_contract.package_root:
        raise RunManifestError("run manifest package root must match package contract")

    manifest_command = _single_manifest_command(run_manifest=run_manifest, command_id=command_id)
    contract_command, expected_kind = _single_contract_command(package_contract=package_contract, command_id=command_id)
    expected_manifest_command = RunManifestCommand.from_package_command(
        package_command=contract_command,
        kind=expected_kind,
    )
    if manifest_command != expected_manifest_command:
        raise RunManifestError("run manifest command must match package contract command")

    return RunManifestBinding(
        run_manifest_ref=run_manifest.run_manifest_id,
        package_contract_ref=package_contract.package_contract_id,
        command_id=manifest_command.command_id,
        kind=manifest_command.kind,
        command=manifest_command.command,
        cwd=manifest_command.cwd,
    )


def _validate_workspace_contract_binding(*, workspace_manifest: WorkspaceManifest, package_contract: PackageContract) -> None:
    if workspace_manifest.package_contract_ref != package_contract.package_contract_id:
        raise RunManifestError("workspace manifest package_contract_ref must match package contract")
    if workspace_manifest.package_root.value != package_contract.package_root:
        raise RunManifestError("workspace manifest package root must match package contract")
    if package_contract.package_root != "10-project":
        raise RunManifestError("package root must be 10-project")


def _validate_runnable_package_commands(package_contract: PackageContract) -> None:
    if package_contract.project_type not in {PackageProjectType.SOFTWARE, PackageProjectType.MIXED}:
        return
    if not package_contract.run_commands:
        raise RunManifestError("software and mixed packages require run commands")
    if not package_contract.test_commands:
        raise RunManifestError("software and mixed packages require test commands")


def _single_manifest_command(*, run_manifest: RunManifest, command_id: ContractId) -> RunManifestCommand:
    matches = tuple(command for command in run_manifest.commands if command.command_id == command_id)
    if len(matches) != 1:
        raise RunManifestError("command is not declared in run manifest")
    return matches[0]


def _single_contract_command(*, package_contract: PackageContract, command_id: ContractId) -> tuple[PackageCommand, RunManifestCommandKind]:
    matches: list[tuple[PackageCommand, RunManifestCommandKind]] = []
    matches.extend((command, RunManifestCommandKind.RUN) for command in package_contract.run_commands if command.command_id == command_id)
    matches.extend((command, RunManifestCommandKind.TEST) for command in package_contract.test_commands if command.command_id == command_id)
    if len(matches) != 1:
        raise RunManifestError("expected exactly one command in package contract")
    return matches[0]


__all__ = [
    "RunManifest",
    "RunManifestBinding",
    "RunManifestCommand",
    "RunManifestCommandKind",
    "RunManifestError",
    "RunManifestRef",
    "build_run_manifest",
    "validate_run_manifest_binding",
]
```

- [ ] **Step 2: Run tests to verify initial pass**

Run:

```bash
PYTHONPATH="src;." python -m pytest tests/proving/test_run_manifest.py -q
```

Expected: PASS for the three starter tests.

---

### Task 3: Add manifest/contract mismatch coverage

**Files:**
- Modify: `tests/proving/test_run_manifest.py`
- Modify if needed: `src/boardroom_os/workspace/run_manifest.py`

- [ ] **Step 1: Add mismatch tests**

Append these tests to `tests/proving/test_run_manifest.py`:

```python
@pytest.mark.parametrize(
    "replacement_command",
    [
        _command("run-package", label="Different label"),
        _command("run-package", command=(sys.executable, "-c", "print('different')")),
        _command("run-package", cwd="backend"),
    ],
    ids=["label", "command", "cwd"],
)
def test_binding_rejects_manifest_command_that_differs_from_package_contract(replacement_command: PackageCommand) -> None:
    from boardroom_os.workspace.run_manifest import RunManifest, build_run_manifest, validate_run_manifest_binding

    package_contract = _package_contract()
    manifest = build_run_manifest(
        workspace_manifest=_workspace_manifest(package_contract),
        package_contract=package_contract,
    )
    replacement_manifest = RunManifest(
        run_manifest_id=manifest.run_manifest_id,
        workspace_manifest_ref=manifest.workspace_manifest_ref,
        package_contract_ref=manifest.package_contract_ref,
        package_root=manifest.package_root,
        commands=tuple(
            command.model_copy(
                update={
                    "label": replacement_command.label,
                    "command": replacement_command.command,
                    "cwd": replacement_command.cwd,
                }
            ) if command.command_id == replacement_command.command_id else command
            for command in manifest.commands
        ),
    )

    with pytest.raises(_VERIFY_ERRORS, match="match package contract"):
        validate_run_manifest_binding(
            run_manifest=replacement_manifest,
            package_contract=package_contract,
            command_id=ContractId(value="run-package"),
        )


def test_binding_rejects_manifest_command_with_wrong_kind() -> None:
    from boardroom_os.workspace.run_manifest import RunManifest, RunManifestCommandKind, build_run_manifest, validate_run_manifest_binding

    package_contract = _package_contract()
    manifest = build_run_manifest(
        workspace_manifest=_workspace_manifest(package_contract),
        package_contract=package_contract,
    )
    replacement_manifest = RunManifest(
        run_manifest_id=manifest.run_manifest_id,
        workspace_manifest_ref=manifest.workspace_manifest_ref,
        package_contract_ref=manifest.package_contract_ref,
        package_root=manifest.package_root,
        commands=tuple(
            command.model_copy(update={"kind": RunManifestCommandKind.TEST})
            if command.command_id == ContractId(value="run-package")
            else command
            for command in manifest.commands
        ),
    )

    with pytest.raises(_VERIFY_ERRORS, match="match package contract"):
        validate_run_manifest_binding(
            run_manifest=replacement_manifest,
            package_contract=package_contract,
            command_id=ContractId(value="run-package"),
        )


def test_binding_rejects_manifest_missing_package_contract_command() -> None:
    from boardroom_os.workspace.run_manifest import RunManifest, build_run_manifest, validate_run_manifest_binding

    package_contract = _package_contract()
    manifest = build_run_manifest(
        workspace_manifest=_workspace_manifest(package_contract),
        package_contract=package_contract,
    )
    replacement_manifest = RunManifest(
        run_manifest_id=manifest.run_manifest_id,
        workspace_manifest_ref=manifest.workspace_manifest_ref,
        package_contract_ref=manifest.package_contract_ref,
        package_root=manifest.package_root,
        commands=tuple(command for command in manifest.commands if command.command_id != ContractId(value="run-package")),
    )

    with pytest.raises(_VERIFY_ERRORS, match="run manifest|declared"):
        validate_run_manifest_binding(
            run_manifest=replacement_manifest,
            package_contract=package_contract,
            command_id=ContractId(value="run-package"),
        )


def test_binding_rejects_manifest_with_extra_package_contract_command() -> None:
    from boardroom_os.workspace.run_manifest import RunManifest, RunManifestCommand, RunManifestCommandKind, build_run_manifest, validate_run_manifest_binding

    package_contract = _package_contract()
    manifest = build_run_manifest(
        workspace_manifest=_workspace_manifest(package_contract),
        package_contract=package_contract,
    )
    extra_command = RunManifestCommand(
        command_id=ContractId(value="manifest-only"),
        kind=RunManifestCommandKind.RUN,
        label="Manifest only",
        command=(sys.executable, "-c", "print('manifest-only')"),
        cwd=".",
    )
    replacement_manifest = RunManifest(
        run_manifest_id=manifest.run_manifest_id,
        workspace_manifest_ref=manifest.workspace_manifest_ref,
        package_contract_ref=manifest.package_contract_ref,
        package_root=manifest.package_root,
        commands=(*manifest.commands, extra_command),
    )

    with pytest.raises(_VERIFY_ERRORS, match="package contract"):
        validate_run_manifest_binding(
            run_manifest=replacement_manifest,
            package_contract=package_contract,
            command_id=ContractId(value="manifest-only"),
        )
```

- [ ] **Step 2: Run tests**

Run:

```bash
PYTHONPATH="src;." python -m pytest tests/proving/test_run_manifest.py -q
```

Expected: PASS.

---

### Task 4: Add structural validation tests

**Files:**
- Modify: `tests/proving/test_run_manifest.py`
- Modify if needed: `src/boardroom_os/workspace/run_manifest.py`

- [ ] **Step 1: Add structural fail-closed tests**

Append these tests:

```python
def test_run_manifest_rejects_duplicate_command_ids() -> None:
    from boardroom_os.workspace.run_manifest import RunManifest, RunManifestCommand, RunManifestCommandKind, RunManifestRef

    command = RunManifestCommand(
        command_id=ContractId(value="duplicate-command"),
        kind=RunManifestCommandKind.RUN,
        label="Duplicate",
        command=(sys.executable, "-c", "print('ok')"),
        cwd=".",
    )

    with pytest.raises(_VERIFY_ERRORS, match="unique"):
        RunManifest(
            run_manifest_id=RunManifestRef(value="run-manifest.duplicate"),
            workspace_manifest_ref=_workspace_manifest().workspace_manifest_id,
            package_contract_ref=ContractId(value="package-contract.run-manifest"),
            package_root=WorkspacePath(value="10-project"),
            commands=(command, command),
        )


@pytest.mark.parametrize(
    "fields",
    [
        {"command": ()},
        {"command": ("python", "")},
        {"cwd": " "},
    ],
    ids=["empty-command", "empty-command-item", "empty-cwd"],
)
def test_run_manifest_command_rejects_invalid_command_shape(fields: dict[str, object]) -> None:
    from boardroom_os.workspace.run_manifest import RunManifestCommand, RunManifestCommandKind

    data = {
        "command_id": ContractId(value="invalid-command"),
        "kind": RunManifestCommandKind.RUN,
        "label": "Invalid command",
        "command": (sys.executable, "-c", "print('ok')"),
        "cwd": ".",
    }
    data.update(fields)

    with pytest.raises(_VERIFY_ERRORS, match="command|text fields"):
        RunManifestCommand(**data)


def test_build_run_manifest_rejects_workspace_package_contract_mismatch() -> None:
    from boardroom_os.workspace.manifest import WorkspaceManifest
    from boardroom_os.workspace.run_manifest import build_run_manifest

    package_contract = _package_contract()
    manifest = _workspace_manifest(package_contract).model_copy(
        update={"package_contract_ref": ContractId(value="package-contract.other")}
    )

    with pytest.raises(_VERIFY_ERRORS, match="package_contract_ref"):
        build_run_manifest(
            workspace_manifest=manifest,
            package_contract=package_contract,
        )


def test_build_run_manifest_rejects_package_root_mismatch() -> None:
    from boardroom_os.workspace.run_manifest import build_run_manifest

    package_contract = _package_contract()
    manifest = _workspace_manifest(package_contract).model_copy(
        update={"sections": _workspace_manifest(package_contract).sections}
    )
    bad_contract = _package_contract(package_root="project")

    with pytest.raises(_VERIFY_ERRORS, match="package root|10-project"):
        build_run_manifest(
            workspace_manifest=manifest,
            package_contract=bad_contract,
        )


def test_run_manifest_rejects_extra_fields() -> None:
    from boardroom_os.workspace.run_manifest import RunManifestCommand, RunManifestCommandKind

    with pytest.raises(ValidationError):
        RunManifestCommand.model_validate(
            {
                "command_id": ContractId(value="extra-command"),
                "kind": RunManifestCommandKind.RUN,
                "label": "Extra command",
                "command": (sys.executable, "-c", "print('ok')"),
                "cwd": ".",
                "unexpected": "field",
            }
        )
```

- [ ] **Step 2: Run tests**

Run:

```bash
PYTHONPATH="src;." python -m pytest tests/proving/test_run_manifest.py -q
```

Expected: PASS.

---

### Task 5: Add binding→runner happy path

**Files:**
- Modify: `tests/proving/test_run_manifest.py`
- Modify if needed: `src/boardroom_os/workspace/run_manifest.py`

- [ ] **Step 1: Add ExecutionPackage（执行包） and runner fixtures**

Append these helpers and test:

```python
def _model_execution_profile() -> ModelExecutionProfile:
    return ModelExecutionProfile(
        model_execution_profile_id="model-profile.run-manifest",
        provider="anthropic",
        model="claude-opus-4-7",
        reasoning_effort="medium",
        context_window=200000,
        temperature=0.2,
        tool_permissions=("process.run",),
        fallback_policy_ref="fallback-policy.default",
    )


def _evidence_obligation() -> EvidenceObligation:
    return EvidenceObligation(
        evidence_obligation_id=EvidenceObligationRef(value="evidence-obligation.run-manifest"),
        acceptance_refs=(AcceptanceRef(value="AC-RUN"),),
        source_surface_refs=(SourceSurfaceRef(value="run-manifest"),),
        required_artifact_type=RequiredArtifactType(value="command_run"),
        required_verifier={"value": "command_runner"},
        blocking=True,
    )


def _execution_package(*commands: PackageCommand) -> ExecutionPackage:
    return ExecutionPackage(
        execution_package_id=ExecutionPackageId(value="execution-package.run-manifest"),
        ticket_ref=TicketId(value="ticket.run-manifest"),
        graph_version=11,
        seat_ref=AgentSeatRef(value="seat.worker.run-manifest"),
        model_execution_profile=_model_execution_profile(),
        objective="Run declared package command after run manifest binding.",
        context_refs=(ContextRef(value="context.run-manifest"),),
        constraints=("Only run commands declared by the run manifest and package contract.",),
        acceptance_refs=(AcceptanceRef(value="AC-RUN"),),
        source_surface_refs=(SourceSurfaceRef(value="run-manifest"),),
        allowed_read_refs=(AllowedReadRef(value="read.package"),),
        allowed_write_set=(AllowedWritePath(value="tests"),),
        required_outputs=(RequiredOutput(value="command evidence"),),
        commands=commands,
        evidence_obligations=(_evidence_obligation(),),
        fallback_policy_ref=FallbackPolicyRef(value="fallback-policy.default"),
        audit_requirements=(AuditRequirement(value="record command run"),),
    )


class CapturingProcessExecutor:
    def __init__(self, process_result: ProcessResult) -> None:
        self._process_result = process_result
        self.commands: list[tuple[str, ...]] = []
        self.cwd_values: list[Path] = []

    def run(self, *, command: tuple[str, ...], cwd: Path) -> ProcessResult:
        self.commands.append(command)
        self.cwd_values.append(cwd)
        return self._process_result


def test_bound_declared_command_can_be_run_by_command_runner(tmp_path: Path) -> None:
    from boardroom_os.workspace.run_manifest import RunManifestCommandKind, build_run_manifest, validate_run_manifest_binding

    run_command = _command("run-package", label="Run package", command=(sys.executable, "-c", "print('run-ok')"))
    test_command = _command("test-package", label="Test package", command=(sys.executable, "-c", "print('test-ok')"))
    package_contract = _package_contract(run_commands=(run_command,), test_commands=(test_command,))
    run_manifest = build_run_manifest(
        workspace_manifest=_workspace_manifest(package_contract),
        package_contract=package_contract,
    )

    binding = validate_run_manifest_binding(
        run_manifest=run_manifest,
        package_contract=package_contract,
        command_id=run_command.command_id,
    )

    process_executor = CapturingProcessExecutor(ProcessResult(exit_code=0, stdout="run-ok\n", stderr=""))
    result = CommandRunner(process_executor=process_executor).run(
        CommandRunnerInput(
            execution_package=_execution_package(run_command),
            package_contract=package_contract,
            command_id=binding.command_id,
            package_root=tmp_path,
            runner_ref=RunnerRef(value="runner.local-subprocess"),
            environment_profile_ref=EnvironmentProfileRef(value="environment.local-python"),
            workspace_snapshot_ref=WorkspaceSnapshotRef(value="workspace-snapshot.run-manifest"),
        )
    )

    assert binding.kind is RunManifestCommandKind.RUN
    assert binding.command == run_command.command
    assert process_executor.commands == [run_command.command]
    assert process_executor.cwd_values == [tmp_path.resolve()]
    assert result.stdout == "run-ok\n"
    assert result.stderr == ""
    assert result.verification_run.command_id == run_command.command_id
    assert result.verification_run.command == run_command.command
    assert result.verification_run.cwd == run_command.cwd
    assert result.verification_run.exit_code == 0
    assert result.verification_run.stdout_ref.value.endswith(".stdout")
    assert result.verification_run.stderr_ref.value.endswith(".stderr")
```

- [ ] **Step 2: Run tests**

Run:

```bash
PYTHONPATH="src;." python -m pytest tests/proving/test_run_manifest.py -q
```

Expected: PASS, including the binding→runner happy path.

---

### Task 6: Export workspace public API and run focused regression

**Files:**
- Modify: `src/boardroom_os/workspace/__init__.py`
- Test: `tests/proving/test_run_manifest.py`

- [ ] **Step 1: Export new public objects**

Modify `src/boardroom_os/workspace/__init__.py` to import and list:

```python
from boardroom_os.workspace.run_manifest import (
    RunManifest,
    RunManifestBinding,
    RunManifestCommand,
    RunManifestCommandKind,
    RunManifestError,
    RunManifestRef,
    build_run_manifest,
    validate_run_manifest_binding,
)
```

Add these names to `__all__`:

```python
"RunManifest",
"RunManifestBinding",
"RunManifestCommand",
"RunManifestCommandKind",
"RunManifestError",
"RunManifestRef",
"build_run_manifest",
"validate_run_manifest_binding",
```

- [ ] **Step 2: Run workspace/proving regression**

Run:

```bash
PYTHONPATH="src;." python -m pytest tests/proving/test_workspace_manifest.py tests/proving/test_package_assembler.py tests/negative/test_source_inventory_ref_only_rejected.py tests/proving/test_source_inventory.py tests/proving/test_run_manifest.py -q
```

Expected: PASS.

---

### Task 7: Update implementation docs after code verification

**Files:**
- Modify: `doc/04-implementation/backlog.md`
- Modify: `doc/04-implementation/acceptance-criteria.md`
- Modify: `doc/05-project-log/2026-05.md`
- Modify: `doc/04-implementation/INDEX.md`

- [ ] **Step 1: Update backlog status and progress**

In `doc/04-implementation/backlog.md`:

- Change top TL;DR current unfinished package from `V2-060D` to `V2-060E`.
- Change V2-060D status from `TODO` to `DONE`.
- Change Phase 6 progress from `3 / 6` to `4 / 6`.
- Change total progress from `38 / 53` to `39 / 53`.
- Add V2-060D completion evidence after the V2-060D acceptance line.

Completion evidence text:

```markdown
- 完成证据：2026-05-23 新增 RunManifest（运行清单）、RunManifestCommand（运行清单命令）、RunManifestBinding（运行清单绑定）、build_run_manifest（构建运行清单函数）和 validate_run_manifest_binding（校验运行清单绑定函数）；保持纯领域模型 + 显式绑定校验边界，不写文件、不导出 `20-evidence`、不修改 CommandRunner（命令执行器）或 RuntimeExecutor（运行时执行器）签名。负例证明软件项目缺 run/test commands（运行/测试命令）、runner 执行未声明命令、manifest command（清单命令）与 PackageContract（包合同）不一致、command kind（命令类型）错标、manifest 缺/多命令、重复 command_id、workspace/contract/package_root mismatch（工作区/合同/包根不一致）、命令形状错误和 extra fields（额外字段）均 fail closed；正例证明 RunManifest（运行清单）稳定镜像 PackageContract（包合同）命令，并按评审建议串联 validate_run_manifest_binding（校验运行清单绑定）→ CommandRunner.run（命令执行器运行）生成真实 VerificationRun（验证运行）。验证命令：`PYTHONPATH="src;." python -m pytest tests/proving/test_run_manifest.py -q`；`PYTHONPATH="src;." python -m pytest tests/proving/test_workspace_manifest.py tests/proving/test_package_assembler.py tests/negative/test_source_inventory_ref_only_rejected.py tests/proving/test_source_inventory.py tests/proving/test_run_manifest.py -q`；`PYTHONPATH="src;." python -m pytest tests/contracts/test_package_contract.py tests/negative/test_package_contract_fail_closed.py tests/execution/test_command_runner.py tests/proving/test_run_manifest.py -q`。
```

- [ ] **Step 2: Update acceptance criteria**

In `doc/04-implementation/acceptance-criteria.md`, change:

```markdown
- [ ] AC-V2-PACKAGE-002（package 必须可运行）— 由 V2-060D `test_run_manifest.py` 证明
```

to:

```markdown
- [x] AC-V2-PACKAGE-002（package 必须可运行）— 由 V2-060D `test_run_manifest.py` 证明：软件项目缺 run/test commands、manifest command 与 PackageContract 不一致、runner 执行未声明 command 必须失败；declared command 经 RunManifestBinding 后可由 CommandRunner 生成真实 VerificationRun
```

- [ ] **Step 3: Update monthly log**

Append one dated entry to `doc/05-project-log/2026-05.md` if a `2026-05-23 V2-060D` entry does not already exist:

```markdown
### 2026-05-23 — V2-060D RunManifest（运行清单）与 command binding（命令绑定）

- 产出：`src/boardroom_os/workspace/run_manifest.py`、`tests/proving/test_run_manifest.py`。
- Negative tests：软件项目缺 run/test commands、runner 执行未声明命令、manifest command 与 PackageContract 不一致、command kind 错标、manifest 缺/多命令、重复 command_id、workspace/contract/package_root mismatch、命令形状错误和 extra fields 均 fail closed。
- Happy path：RunManifest 稳定镜像 PackageContract run/test commands；`validate_run_manifest_binding(...)` 严格串联 `CommandRunner.run(...)` 并生成真实 VerificationRun。
- 验证：`PYTHONPATH="src;." python -m pytest tests/proving/test_run_manifest.py -q`；`PYTHONPATH="src;." python -m pytest tests/proving/test_workspace_manifest.py tests/proving/test_package_assembler.py tests/negative/test_source_inventory_ref_only_rejected.py tests/proving/test_source_inventory.py tests/proving/test_run_manifest.py -q`；`PYTHONPATH="src;." python -m pytest tests/contracts/test_package_contract.py tests/negative/test_package_contract_fail_closed.py tests/execution/test_command_runner.py tests/proving/test_run_manifest.py -q`。
- Follow-up：V2-070A CloseoutGate（收尾门禁）spec 需增加负例：closeout 时若任一 declared command 未经 RunManifestBinding（运行清单绑定）即作为 final command evidence（最终命令证据）使用，必须失败。
```

- [ ] **Step 4: Update implementation index**

Ensure `doc/04-implementation/INDEX.md` contains:

```markdown
| `v2-060d-run-manifest-spec.md` | V2-060D RunManifest（运行清单）同行评审 spec |
| `v2-060d-run-manifest-implementation-plan.md` | V2-060D RunManifest（运行清单）实施计划 |
```

---

### Task 8: Final verification

**Files:**
- No code changes unless verification reveals a defect.

- [ ] **Step 1: Run focused verification**

Run:

```bash
PYTHONPATH="src;." python -m pytest tests/proving/test_run_manifest.py -q
```

Expected: all V2-060D tests pass.

- [ ] **Step 2: Run integration-relevant verification**

Run:

```bash
PYTHONPATH="src;." python -m pytest tests/contracts/test_package_contract.py tests/negative/test_package_contract_fail_closed.py tests/execution/test_command_runner.py tests/proving/test_workspace_manifest.py tests/proving/test_package_assembler.py tests/negative/test_source_inventory_ref_only_rejected.py tests/proving/test_source_inventory.py tests/proving/test_run_manifest.py -q
```

Expected: all selected contract/execution/workspace tests pass.

- [ ] **Step 3: Inspect git diff**

Run:

```bash
git diff -- doc/04-implementation/INDEX.md doc/04-implementation/v2-060d-run-manifest-spec.md doc/04-implementation/v2-060d-run-manifest-implementation-plan.md src/boardroom_os/workspace/run_manifest.py src/boardroom_os/workspace/__init__.py tests/proving/test_run_manifest.py doc/04-implementation/backlog.md doc/04-implementation/acceptance-criteria.md doc/05-project-log/2026-05.md
```

Expected: diff only contains V2-060D spec/plan, RunManifest implementation, tests, exports, and required backlog/acceptance/log updates.

---

## Self-Review

- Spec coverage: the plan covers RunManifest（运行清单） schema, command kind（命令类型）, package/workspace binding, manifest/contract exact mirror validation, undeclared command rejection, binding→runner happy path, no file writes, and documentation updates.
- Reviewer suggestions: Task 5 explicitly serializes `validate_run_manifest_binding(...)` before `CommandRunner.run(...)`; Task 7 records the V2-070A CloseoutGate（收尾门禁） follow-up without implementing it in V2-060D.
- No implementation task changes CommandRunner（命令执行器） or RuntimeExecutor（运行时执行器） signatures.
- No task reads legacy implementation or writes generated workspace directories.
