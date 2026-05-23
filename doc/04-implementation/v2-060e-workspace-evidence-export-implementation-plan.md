# V2-060E WorkspaceEvidenceExport（工作区证据导出）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development（子代理驱动开发，推荐） or superpowers:executing-plans（按计划执行） to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement V2-060E WorkspaceEvidenceExport（工作区证据导出） so PackageAssembly（项目包装配结果）, SourceInventory（源码清单）, RunManifest（运行清单）, VerificationRun（验证运行）, VerifiedEvidence（已验证证据） and FinalEvidenceTable（最终证据表） are synchronized into a closeout-ready（可收尾） `20-evidence` bundle plan without writing files.

**Architecture:** Add one focused pure-domain module, `src/boardroom_os/workspace/evidence_export.py`, containing WorkspaceEvidenceBundle（工作区证据包） types, EvidenceBundleArtifact（证据包产物） types, deterministic artifact planning, and fail-closed cross-model validation. The builder consumes already-typed upstream facts only; it does not create directories, write JSON, copy stdout/stderr, run commands, call git, or re-verify EvidenceClaim（证据声明）.

**Tech Stack:** Python 3, Pydantic BaseModel（Pydantic 模型）, pytest, existing Boardroom OS V2 WorkspaceManifest（工作区清单）, PackageAssembly（项目包装配结果）, SourceInventory（源码清单）, RunManifest（运行清单）, VerificationRun（验证运行）, VerifiedEvidence（已验证证据）, and FinalEvidenceTable（最终证据表） models.

---

## File Structure

- Create `src/boardroom_os/workspace/evidence_export.py`
  - Own `WorkspaceEvidenceExportError`（工作区证据导出错误）, `WorkspaceEvidenceBundleRef`（工作区证据包引用）, `EvidenceBundleArtifactPath`（证据包产物路径）, `EvidenceBundleArtifactKind`（证据包产物类型）, `EvidenceBundleArtifact`（证据包产物）, `WorkspaceEvidenceBundle`（工作区证据包）, and `build_workspace_evidence_bundle`（构建工作区证据包函数）.
  - Import only typed facts from contracts, workspace, execution, and evidence modules.
  - Do not import filesystem writers, runtime executor, provider executor, CommandRunner（命令执行器）, closeout, git adapters, or legacy implementation.
- Create `tests/proving/test_workspace_evidence_export.py`
  - Write backlog-required negative tests first.
  - Cover review-required INV-X1 / INV-X2 / orphan evidence（孤儿证据） / orphan run（孤儿验证运行） checks.
  - End with deterministic happy path（正向路径） proving the five required `20-evidence` artifacts.
- Modify `src/boardroom_os/workspace/__init__.py`
  - Export the V2-060E public API.
- Modify `doc/04-implementation/INDEX.md`
  - Add this implementation plan entry.
- Modify after implementation verification only:
  - `doc/04-implementation/backlog.md`
  - `doc/04-implementation/acceptance-criteria.md`
  - `doc/05-project-log/2026-05.md`

---

### Task 1: Add fail-closed tests for evidence bundle export

**Files:**
- Create: `tests/proving/test_workspace_evidence_export.py`
- No production code yet.

- [ ] **Step 1: Write failing negative tests and fixtures**

Create `tests/proving/test_workspace_evidence_export.py` with fixtures that construct a tiny but real typed chain:

```python
from __future__ import annotations

from datetime import UTC, datetime
from dataclasses import replace

import pytest
from pydantic import ValidationError

from boardroom_os.agents.profiles import ModelExecutionProfile
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
from boardroom_os.evidence.claim import EvidenceArtifactRef, EvidenceClaimRef, EvidenceSourceKind, EvidenceSourceRef, EvidenceSourceSurfaceRef
from boardroom_os.evidence.verifier import ArtifactSha256, VerifiedArtifact, VerifiedEvidence, VerifiedEvidenceRef
from boardroom_os.evidence.table import FinalEvidenceRow, FinalEvidenceStatus, FinalEvidenceTable, FinalEvidenceTableRef
from boardroom_os.execution.context_index import ProviderAttemptRef
from boardroom_os.execution.package import ExecutionPackageId, ExecutionPackageRef
from boardroom_os.execution.verification_run import (
    CommandOutputRef,
    EnvironmentProfileRef,
    RunnerRef,
    VerificationRun,
    VerificationRunRef,
    VerificationRunStatus,
    WorkspaceSnapshotRef,
)
from boardroom_os.graph.ticket import TicketId
from boardroom_os.workspace.assembler import PackageArtifact, PackageArtifactKind, PackageArtifactPath, assemble_package
from boardroom_os.workspace.manifest import WorkflowRef, WorkspacePath, build_workspace_manifest
from boardroom_os.workspace.run_manifest import build_run_manifest
from boardroom_os.workspace.source_inventory import (
    PackageCommitRef,
    SourceFilePath,
    SourceFileRecord,
    SourceLineageRecord,
    build_source_inventory,
)

_VERIFY_ERRORS = (ValueError, ValidationError)
_NOW = datetime(2026, 5, 23, tzinfo=UTC)


def _profile() -> MethodologyProfile:
    template_kind = MethodologyTemplateKind.HYBRID
    return MethodologyProfile(
        methodology_profile_id=ContractId(value="methodology-profile.workspace-evidence-export"),
        project_charter_ref=ContractId(value="project-charter.workspace-evidence-export"),
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
        owned_by=OwnerSeatRef(value="worker.workspace-evidence-export"),
        acceptance_refs=tuple(AcceptanceRef(value=ref) for ref in acceptance_refs),
        required_tests=(RequiredTestRef(value="pytest.workspace-evidence-export"),),
    )


def _command(command_id: str) -> PackageCommand:
    return PackageCommand(
        command_id=ContractId(value=command_id),
        label=command_id.replace("-", " ").title(),
        command=("python", "-m", "pytest"),
        cwd=".",
    )


def _package_contract():
    profile = _profile()
    return create_package_contract(
        methodology_registry=MethodologyProfileRegistry.from_profiles(profile),
        package_contract_id=ContractId(value="package-contract.workspace-evidence-export"),
        project_charter_ref=ContractId(value="project-charter.workspace-evidence-export"),
        package_root="10-project",
        project_type=PackageProjectType.SOFTWARE,
        source_surfaces=(
            _surface("app-source", ("app.py",), ("AC-APP",)),
            _surface("app-tests", ("test_app.py",), ("AC-TEST",)),
            _surface("run-manifest", ("run-manifest.json",), ("AC-RUN",)),
            _surface("package-contract", ("package-contract.json",), ("AC-CONTRACT",)),
        ),
        run_commands=(_command("run-app"),),
        test_commands=(_command("test-app"),),
        integration_boundaries=(IntegrationBoundary(value="local-process"),),
        docs_required=False,
        closeout_required=True,
        methodology_profile_ref=profile.methodology_profile_id,
        docs_template_key=profile.docs_template_key,
        documentation_obligations=profile.documentation_obligations,
    )


def _facts():
    contract = _package_contract()
    workspace_manifest = build_workspace_manifest(
        workflow_ref=WorkflowRef(value="workflow.workspace-evidence-export"),
        workspace_root=WorkspacePath(value="workspaces/workspace-evidence-export"),
        package_contract=contract,
    )
    source_surface = contract.source_surfaces[0].source_surface_ref
    acceptance_ref = AcceptanceRef(value="AC-APP")
    package_assembly = assemble_package(
        workspace_manifest=workspace_manifest,
        package_contract=contract,
        artifacts=(
            PackageArtifact(relative_path=PackageArtifactPath(value="README.md"), artifact_kind=PackageArtifactKind.README),
            PackageArtifact(relative_path=PackageArtifactPath(value="AGENTS.md"), artifact_kind=PackageArtifactKind.AGENTS),
            PackageArtifact(
                relative_path=PackageArtifactPath(value="package-contract.json"),
                artifact_kind=PackageArtifactKind.PACKAGE_CONTRACT,
                source_surface_refs=(contract.source_surfaces[3].source_surface_ref,),
                acceptance_refs=(AcceptanceRef(value="AC-CONTRACT"),),
            ),
            PackageArtifact(
                relative_path=PackageArtifactPath(value="run-manifest.json"),
                artifact_kind=PackageArtifactKind.RUN_MANIFEST,
                source_surface_refs=(contract.source_surfaces[2].source_surface_ref,),
                acceptance_refs=(AcceptanceRef(value="AC-RUN"),),
            ),
            PackageArtifact(
                relative_path=PackageArtifactPath(value="app.py"),
                artifact_kind=PackageArtifactKind.SOURCE,
                source_surface_refs=(source_surface,),
                acceptance_refs=(acceptance_ref,),
            ),
            PackageArtifact(
                relative_path=PackageArtifactPath(value="test_app.py"),
                artifact_kind=PackageArtifactKind.TEST,
                source_surface_refs=(contract.source_surfaces[1].source_surface_ref,),
                acceptance_refs=(AcceptanceRef(value="AC-TEST"),),
            ),
        ),
    )
    run_manifest = build_run_manifest(workspace_manifest=workspace_manifest, package_contract=contract)
    verification_run = _verification_run("verification-run.app")
    verified_evidence = _verified_evidence("verified-evidence.app", verification_run.verification_run_id, acceptance_ref, source_surface)
    source_inventory = build_source_inventory(
        package_assembly=package_assembly,
        package_contract=contract,
        package_commit_ref=PackageCommitRef(value="package-commit.workspace-evidence-export"),
        source_files=(
            SourceFileRecord(
                path=SourceFilePath(value="app.py"),
                sha256=ArtifactSha256(value="a" * 64),
            ),
        ),
        lineage_records=(
            SourceLineageRecord(
                path=SourceFilePath(value="app.py"),
                source_surface_ref=source_surface,
                producer_ticket_ref=TicketId(value="ticket.app"),
                producer_attempt_ref=ProviderAttemptRef(value="provider-attempt.app"),
                acceptance_refs=(acceptance_ref,),
                evidence_refs=(verified_evidence.verified_evidence_id,),
            ),
        ),
    )
    final_evidence_table = _final_table(
        rows=(
            FinalEvidenceRow(
                acceptance_ref=acceptance_ref,
                statement="App acceptance is satisfied by verified command evidence.",
                status=FinalEvidenceStatus.SATISFIED,
                verified_evidence_refs=(verified_evidence.verified_evidence_id,),
                blockers=(),
            ),
        ),
    )
    return {
        "workspace_manifest": workspace_manifest,
        "package_assembly": package_assembly,
        "source_inventory": source_inventory,
        "run_manifest": run_manifest,
        "verification_runs": (verification_run,),
        "verified_evidence": (verified_evidence,),
        "final_evidence_table": final_evidence_table,
    }


def _verification_run(ref: str, *, status: VerificationRunStatus = VerificationRunStatus.PASSED, exit_code: int = 0) -> VerificationRun:
    return VerificationRun(
        verification_run_id=VerificationRunRef(value=ref),
        execution_package_ref=ExecutionPackageRef(value="execution-package.app"),
        ticket_ref=TicketId(value="ticket.app"),
        command_id=ContractId(value="test-app"),
        command=("python", "-m", "pytest"),
        cwd=".",
        exit_code=exit_code,
        status=status,
        stdout_ref=CommandOutputRef(value=f"command-output.{ref}.stdout"),
        stderr_ref=CommandOutputRef(value=f"command-output.{ref}.stderr"),
        duration_ms=25,
        started_at=_NOW,
        finished_at=_NOW,
        runner_ref=RunnerRef(value="runner.local"),
        environment_profile_ref=EnvironmentProfileRef(value="environment.local"),
        workspace_snapshot_ref=WorkspaceSnapshotRef(value="workspace-snapshot.app"),
    )


def _verified_evidence(ref: str, run_ref: VerificationRunRef, acceptance_ref: AcceptanceRef, source_surface_ref: SourceSurfaceRef) -> VerifiedEvidence:
    return VerifiedEvidence(
        verified_evidence_id=VerifiedEvidenceRef(value=ref),
        evidence_claim_ref=EvidenceClaimRef(value=f"evidence-claim.{ref}"),
        evidence_obligation_ref=EvidenceObligationRef(value="evidence-obligation.app"),
        producer_attempt_ref=ProviderAttemptRef(value="provider-attempt.app"),
        source_kind=EvidenceSourceKind.PROVIDER_ATTEMPT,
        source_ref=EvidenceSourceRef(value="provider-attempt.app"),
        expected_purpose="implementation",
        required_artifact_type=RequiredArtifactType(value="source"),
        acceptance_refs=(acceptance_ref,),
        source_surface_refs=(EvidenceSourceSurfaceRef(value=source_surface_ref.value),),
        verified_artifacts=(
            VerifiedArtifact(
                artifact_ref=EvidenceArtifactRef(value="artifact.app"),
                sha256=ArtifactSha256(value="b" * 64),
                producer_attempt_ref=ProviderAttemptRef(value="provider-attempt.app"),
                source_ref=EvidenceSourceRef(value="provider-attempt.app"),
                artifact_kind=RequiredArtifactType(value="source"),
            ),
        ),
        verification_run_refs=(run_ref,),
        verified_at=_NOW,
    )


def _final_table(*, rows: tuple[FinalEvidenceRow, ...], complete: bool | None = None) -> FinalEvidenceTable:
    return FinalEvidenceTable(
        final_evidence_table_id=FinalEvidenceTableRef(value="final-evidence-table.workspace-evidence-export"),
        acceptance_contract_ref=ContractId(value="acceptance-contract.workspace-evidence-export"),
        generated_at=_NOW,
        rows=rows,
        complete=complete,
    )
```

Then add negative tests in this order:

```python
def test_missing_final_evidence_row_blocks_export() -> None:
    from boardroom_os.workspace.evidence_export import build_workspace_evidence_bundle

    facts = _facts()
    facts["final_evidence_table"] = _final_table(
        rows=(
            FinalEvidenceRow(
                acceptance_ref=AcceptanceRef(value="AC-APP"),
                statement="Missing evidence should block closeout.",
                status=FinalEvidenceStatus.MISSING,
                verified_evidence_refs=(),
                blockers=(),
            ),
        )
    )

    with pytest.raises(_VERIFY_ERRORS, match="final evidence table.*satisfied"):
        build_workspace_evidence_bundle(**facts)


def test_failed_final_evidence_row_blocks_export() -> None:
    from boardroom_os.workspace.evidence_export import build_workspace_evidence_bundle

    facts = _facts()
    facts["final_evidence_table"] = _final_table(
        rows=(
            FinalEvidenceRow(
                acceptance_ref=AcceptanceRef(value="AC-APP"),
                statement="Failed evidence should block closeout.",
                status=FinalEvidenceStatus.FAILED,
                verified_evidence_refs=facts["verified_evidence"][0].verified_evidence_id,
                blockers=(),
            ),
        )
    )

    with pytest.raises(_VERIFY_ERRORS, match="final evidence table.*satisfied"):
        build_workspace_evidence_bundle(**facts)


def test_empty_source_inventory_blocks_export() -> None:
    from boardroom_os.workspace.evidence_export import build_workspace_evidence_bundle

    facts = _facts()
    data = facts["source_inventory"].model_dump()
    data["entries"] = []

    with pytest.raises(_VERIFY_ERRORS, match="entries"):
        facts["source_inventory"].__class__(**data)


def test_source_inventory_package_assembly_mismatch_blocks_export() -> None:
    from boardroom_os.workspace.evidence_export import build_workspace_evidence_bundle

    facts = _facts()
    data = facts["source_inventory"].model_dump()
    data["package_assembly_ref"] = {"value": "package-assembly.other"}
    facts["source_inventory"] = facts["source_inventory"].__class__(**data)

    with pytest.raises(_VERIFY_ERRORS, match="package_assembly_ref"):
        build_workspace_evidence_bundle(**facts)


def test_verification_run_missing_stdout_or_stderr_fails_at_model_layer() -> None:
    data = _verification_run("verification-run.malformed").model_dump()
    data.pop("stdout_ref")

    with pytest.raises(ValidationError, match="stdout_ref"):
        VerificationRun(**data)


def test_failed_verification_run_blocks_export() -> None:
    from boardroom_os.workspace.evidence_export import build_workspace_evidence_bundle

    facts = _facts()
    facts["verification_runs"] = (_verification_run("verification-run.app", status=VerificationRunStatus.FAILED, exit_code=1),)

    with pytest.raises(_VERIFY_ERRORS, match="verification run.*passed"):
        build_workspace_evidence_bundle(**facts)


def test_duplicate_verification_run_id_blocks_export() -> None:
    from boardroom_os.workspace.evidence_export import build_workspace_evidence_bundle

    facts = _facts()
    facts["verification_runs"] = (facts["verification_runs"][0], facts["verification_runs"][0])

    with pytest.raises(_VERIFY_ERRORS, match="verification run.*unique"):
        build_workspace_evidence_bundle(**facts)


def test_run_manifest_workspace_mismatch_blocks_export() -> None:
    from boardroom_os.workspace.evidence_export import build_workspace_evidence_bundle

    facts = _facts()
    data = facts["run_manifest"].model_dump()
    data["workspace_manifest_ref"] = {"value": "workspace-manifest.other"}
    facts["run_manifest"] = facts["run_manifest"].__class__(**data)

    with pytest.raises(_VERIFY_ERRORS, match="run manifest.*workspace"):
        build_workspace_evidence_bundle(**facts)


def test_source_inventory_evidence_not_in_final_table_blocks_export() -> None:
    from boardroom_os.workspace.evidence_export import build_workspace_evidence_bundle

    facts = _facts()
    row = facts["final_evidence_table"].rows[0]
    facts["final_evidence_table"] = _final_table(
        rows=(
            FinalEvidenceRow(
                acceptance_ref=row.acceptance_ref,
                statement=row.statement,
                status=FinalEvidenceStatus.SATISFIED,
                verified_evidence_refs=(VerifiedEvidenceRef(value="verified-evidence.other"),),
                blockers=(),
            ),
        )
    )

    with pytest.raises(_VERIFY_ERRORS, match="source inventory evidence refs.*final evidence table"):
        build_workspace_evidence_bundle(**facts)


def test_final_table_unknown_verified_evidence_ref_blocks_export() -> None:
    from boardroom_os.workspace.evidence_export import build_workspace_evidence_bundle

    facts = _facts()
    facts["verified_evidence"] = ()

    with pytest.raises(_VERIFY_ERRORS, match="verified evidence.*resolve"):
        build_workspace_evidence_bundle(**facts)


def test_orphan_verification_run_blocks_export() -> None:
    from boardroom_os.workspace.evidence_export import build_workspace_evidence_bundle

    facts = _facts()
    facts["verification_runs"] = (*facts["verification_runs"], _verification_run("verification-run.orphan"))

    with pytest.raises(_VERIFY_ERRORS, match="orphan verification run"):
        build_workspace_evidence_bundle(**facts)
```

- [ ] **Step 2: Run tests to verify RED**

Run:

```bash
PYTHONPATH="src;." python -m pytest tests/proving/test_workspace_evidence_export.py -q
```

Expected: FAIL because `boardroom_os.workspace.evidence_export` does not exist.

---

### Task 2: Implement artifact path and artifact models

**Files:**
- Create: `src/boardroom_os/workspace/evidence_export.py`
- Test: `tests/proving/test_workspace_evidence_export.py`

- [ ] **Step 1: Add core artifact models**

Create `src/boardroom_os/workspace/evidence_export.py` with:

```python
from __future__ import annotations

from enum import StrEnum
from pathlib import PurePosixPath, PureWindowsPath
from typing import Self

from pydantic import BaseModel, ConfigDict, field_serializer, field_validator, model_validator

from boardroom_os.contracts.types import ContractId, NonEmptyTextValue
from boardroom_os.evidence.table import FinalEvidenceStatus, FinalEvidenceTable, FinalEvidenceTableRef
from boardroom_os.evidence.verifier import VerifiedEvidence, VerifiedEvidenceRef
from boardroom_os.execution.verification_run import VerificationRun, VerificationRunRef, VerificationRunStatus
from boardroom_os.workspace.assembler import PackageArtifactKind, PackageAssembly, PackageAssemblyRef
from boardroom_os.workspace.manifest import WorkspaceManifest, WorkspaceManifestRef
from boardroom_os.workspace.run_manifest import RunManifest, RunManifestRef
from boardroom_os.workspace.source_inventory import SourceInventory, SourceInventoryRef


class WorkspaceEvidenceExportError(ValueError):
    pass


class WorkspaceEvidenceBundleRef(NonEmptyTextValue):
    pass


class EvidenceBundleArtifactPath(NonEmptyTextValue):
    @field_validator("value")
    @classmethod
    def _reject_unsafe_evidence_artifact_path(cls, value: str) -> str:
        normalized = super()._reject_empty_value(value)
        if "\\" in normalized:
            raise ValueError("evidence artifact path must use forward slashes")
        if normalized.endswith("/"):
            raise ValueError("evidence artifact path must name a file")
        if PurePosixPath(normalized).is_absolute() or PureWindowsPath(normalized).drive:
            raise ValueError("evidence artifact path must be relative")

        segments = normalized.split("/")
        if any(segment in {"", ".", ".."} for segment in segments):
            raise ValueError("evidence artifact path must not contain empty, current, or parent segments")
        if segments[0] != "20-evidence":
            raise ValueError("evidence artifact path must be under 20-evidence")
        if normalized == "src/boardroom_os" or normalized.startswith("src/boardroom_os/"):
            raise ValueError("evidence artifact path must not target framework repository layout")
        if segments[0] in {"00-boardroom", "10-project", "30-audit", "doc", "scripts", "examples"}:
            raise ValueError("evidence artifact path must be under 20-evidence")
        return normalized


class EvidenceBundleArtifactKind(StrEnum):
    BUNDLE_MANIFEST = "bundle_manifest"
    SOURCE_INVENTORY = "source_inventory"
    RUN_MANIFEST = "run_manifest"
    VERIFICATION_RUNS = "verification_runs"
    FINAL_EVIDENCE_TABLE = "final_evidence_table"


_ARTIFACT_PATH_BY_KIND: dict[EvidenceBundleArtifactKind, str] = {
    EvidenceBundleArtifactKind.SOURCE_INVENTORY: "20-evidence/source-inventory/source-inventory.json",
    EvidenceBundleArtifactKind.VERIFICATION_RUNS: "20-evidence/tests/verification-runs.json",
    EvidenceBundleArtifactKind.RUN_MANIFEST: "20-evidence/tests/run-manifest.json",
    EvidenceBundleArtifactKind.FINAL_EVIDENCE_TABLE: "20-evidence/closeout/final-evidence-table.json",
    EvidenceBundleArtifactKind.BUNDLE_MANIFEST: "20-evidence/closeout/evidence-bundle-manifest.json",
}


class EvidenceBundleArtifact(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    relative_path: EvidenceBundleArtifactPath
    artifact_kind: EvidenceBundleArtifactKind
    source_ref: NonEmptyTextValue
    related_refs: tuple[NonEmptyTextValue, ...]

    @field_validator("related_refs")
    @classmethod
    def _reject_empty_related_refs(cls, values: tuple[NonEmptyTextValue, ...]) -> tuple[NonEmptyTextValue, ...]:
        if not values:
            raise ValueError("related_refs must not be empty")
        return values

    @model_validator(mode="after")
    def _validate_kind_path_match(self) -> Self:
        expected_path = _ARTIFACT_PATH_BY_KIND[self.artifact_kind]
        if self.relative_path.value != expected_path:
            raise ValueError(f"{self.artifact_kind.value} must export to {expected_path}")
        return self

    @field_serializer("relative_path", "source_ref")
    def _serialize_ref(self, value: NonEmptyTextValue) -> dict[str, str]:
        return value.model_dump()

    @field_serializer("artifact_kind")
    def _serialize_artifact_kind(self, value: EvidenceBundleArtifactKind) -> str:
        return value.value

    @field_serializer("related_refs")
    def _serialize_related_refs(self, values: tuple[NonEmptyTextValue, ...]) -> list[dict[str, str]]:
        return [value.model_dump() for value in values]
```

- [ ] **Step 2: Run targeted tests**

Run:

```bash
PYTHONPATH="src;." python -m pytest tests/proving/test_workspace_evidence_export.py -q
```

Expected: tests still fail because `WorkspaceEvidenceBundle` and builder are not implemented yet.

---

### Task 3: Implement bundle model and deterministic artifact planning

**Files:**
- Modify: `src/boardroom_os/workspace/evidence_export.py`
- Test: `tests/proving/test_workspace_evidence_export.py`

- [ ] **Step 1: Add WorkspaceEvidenceBundle model**

Append:

```python
class WorkspaceEvidenceBundle(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    workspace_evidence_bundle_id: WorkspaceEvidenceBundleRef
    workspace_manifest_ref: WorkspaceManifestRef
    package_assembly_ref: PackageAssemblyRef
    package_contract_ref: ContractId
    source_inventory_ref: SourceInventoryRef
    run_manifest_ref: RunManifestRef
    final_evidence_table_ref: FinalEvidenceTableRef
    verification_run_refs: tuple[VerificationRunRef, ...]
    verified_evidence_refs: tuple[VerifiedEvidenceRef, ...]
    artifacts: tuple[EvidenceBundleArtifact, ...]
    closeout_ready: bool

    @model_validator(mode="after")
    def _validate_bundle_shape(self) -> Self:
        if self.closeout_ready is not True:
            raise ValueError("closeout_ready must be true for exported workspace evidence bundle")
        paths = [artifact.relative_path.value for artifact in self.artifacts]
        if len(paths) != len(set(paths)):
            raise ValueError("evidence artifact paths must be unique")
        kinds = [artifact.artifact_kind for artifact in self.artifacts]
        if set(kinds) != set(EvidenceBundleArtifactKind):
            raise ValueError("required evidence bundle artifact kinds are missing")
        if tuple(sorted(self.verification_run_refs, key=lambda ref: ref.value)) != self.verification_run_refs:
            raise ValueError("verification_run_refs must be sorted")
        if tuple(sorted(self.verified_evidence_refs, key=lambda ref: ref.value)) != self.verified_evidence_refs:
            raise ValueError("verified_evidence_refs must be sorted")
        return self

    @field_serializer(
        "workspace_evidence_bundle_id",
        "workspace_manifest_ref",
        "package_assembly_ref",
        "package_contract_ref",
        "source_inventory_ref",
        "run_manifest_ref",
        "final_evidence_table_ref",
    )
    def _serialize_ref(self, value: NonEmptyTextValue) -> dict[str, str]:
        return value.model_dump()

    @field_serializer("verification_run_refs", "verified_evidence_refs")
    def _serialize_ref_tuple(self, values: tuple[NonEmptyTextValue, ...]) -> list[dict[str, str]]:
        return [value.model_dump() for value in values]

    @field_serializer("artifacts")
    def _serialize_artifacts(self, values: tuple[EvidenceBundleArtifact, ...]) -> list[dict[str, object]]:
        return [value.model_dump() for value in values]
```

- [ ] **Step 2: Add artifact builder helper**

Append:

```python
def _build_artifacts(
    *,
    workspace_manifest: WorkspaceManifest,
    package_assembly: PackageAssembly,
    source_inventory: SourceInventory,
    run_manifest: RunManifest,
    verification_run_refs: tuple[VerificationRunRef, ...],
    verified_evidence_refs: tuple[VerifiedEvidenceRef, ...],
    final_evidence_table: FinalEvidenceTable,
    bundle_id: WorkspaceEvidenceBundleRef,
) -> tuple[EvidenceBundleArtifact, ...]:
    evidence_root = workspace_manifest.evidence_root.value
    path_by_kind = {
        kind: EvidenceBundleArtifactPath(value=path.replace("20-evidence", evidence_root, 1))
        for kind, path in _ARTIFACT_PATH_BY_KIND.items()
    }
    related_refs: tuple[NonEmptyTextValue, ...] = (
        workspace_manifest.workspace_manifest_id,
        package_assembly.package_assembly_id,
        package_assembly.package_contract_ref,
        source_inventory.source_inventory_id,
        run_manifest.run_manifest_id,
        final_evidence_table.final_evidence_table_id,
        *verification_run_refs,
        *verified_evidence_refs,
    )
    artifacts = (
        EvidenceBundleArtifact(
            relative_path=path_by_kind[EvidenceBundleArtifactKind.SOURCE_INVENTORY],
            artifact_kind=EvidenceBundleArtifactKind.SOURCE_INVENTORY,
            source_ref=source_inventory.source_inventory_id,
            related_refs=related_refs,
        ),
        EvidenceBundleArtifact(
            relative_path=path_by_kind[EvidenceBundleArtifactKind.VERIFICATION_RUNS],
            artifact_kind=EvidenceBundleArtifactKind.VERIFICATION_RUNS,
            source_ref=NonEmptyTextValue(value="verification-runs"),
            related_refs=(*related_refs, *verification_run_refs),
        ),
        EvidenceBundleArtifact(
            relative_path=path_by_kind[EvidenceBundleArtifactKind.RUN_MANIFEST],
            artifact_kind=EvidenceBundleArtifactKind.RUN_MANIFEST,
            source_ref=run_manifest.run_manifest_id,
            related_refs=related_refs,
        ),
        EvidenceBundleArtifact(
            relative_path=path_by_kind[EvidenceBundleArtifactKind.FINAL_EVIDENCE_TABLE],
            artifact_kind=EvidenceBundleArtifactKind.FINAL_EVIDENCE_TABLE,
            source_ref=final_evidence_table.final_evidence_table_id,
            related_refs=related_refs,
        ),
        EvidenceBundleArtifact(
            relative_path=path_by_kind[EvidenceBundleArtifactKind.BUNDLE_MANIFEST],
            artifact_kind=EvidenceBundleArtifactKind.BUNDLE_MANIFEST,
            source_ref=bundle_id,
            related_refs=related_refs,
        ),
    )
    return tuple(sorted(artifacts, key=lambda artifact: artifact.relative_path.value))
```

- [ ] **Step 3: Run targeted tests**

Run:

```bash
PYTHONPATH="src;." python -m pytest tests/proving/test_workspace_evidence_export.py -q
```

Expected: tests still fail because builder validation is not implemented.

---

### Task 4: Implement cross-model fail-closed validation

**Files:**
- Modify: `src/boardroom_os/workspace/evidence_export.py`
- Test: `tests/proving/test_workspace_evidence_export.py`

- [ ] **Step 1: Add validation helpers**

Append:

```python
def _validate_workspace_package_source_run_refs(
    *,
    workspace_manifest: WorkspaceManifest,
    package_assembly: PackageAssembly,
    source_inventory: SourceInventory,
    run_manifest: RunManifest,
) -> None:
    if workspace_manifest.package_contract_ref != package_assembly.package_contract_ref:
        raise WorkspaceEvidenceExportError("workspace/package package_contract_ref must match")
    if workspace_manifest.package_contract_ref != source_inventory.package_contract_ref:
        raise WorkspaceEvidenceExportError("source inventory package_contract_ref must match workspace manifest")
    if workspace_manifest.package_contract_ref != run_manifest.package_contract_ref:
        raise WorkspaceEvidenceExportError("run manifest package_contract_ref must match workspace manifest")
    if package_assembly.workspace_manifest_ref != workspace_manifest.workspace_manifest_id:
        raise WorkspaceEvidenceExportError("package assembly workspace_manifest_ref must match workspace manifest")
    if run_manifest.workspace_manifest_ref != workspace_manifest.workspace_manifest_id:
        raise WorkspaceEvidenceExportError("run manifest workspace_manifest_ref must match workspace manifest")
    if source_inventory.package_assembly_ref != package_assembly.package_assembly_id:
        raise WorkspaceEvidenceExportError("source inventory package_assembly_ref must match package assembly")


def _validate_run_manifest_mirror(*, package_assembly: PackageAssembly, run_manifest: RunManifest) -> None:
    run_manifest_artifacts = tuple(
        artifact for artifact in package_assembly.artifacts if artifact.artifact_kind is PackageArtifactKind.RUN_MANIFEST
    )
    if len(run_manifest_artifacts) != 1:
        raise WorkspaceEvidenceExportError("package assembly must contain exactly one run manifest artifact")
    if run_manifest.run_manifest_id.value != f"run-manifest.{package_assembly.workspace_manifest_ref.value}.{package_assembly.package_contract_ref.value}":
        raise WorkspaceEvidenceExportError("run manifest mirror must reference the same run_manifest_id")


def _validate_final_evidence_table(final_evidence_table: FinalEvidenceTable) -> set[str]:
    if not final_evidence_table.rows:
        raise WorkspaceEvidenceExportError("final evidence table rows must not be empty")
    if final_evidence_table.complete is not True:
        raise WorkspaceEvidenceExportError("final evidence table must be complete")
    final_refs: set[str] = set()
    for row in final_evidence_table.rows:
        if row.status is not FinalEvidenceStatus.SATISFIED:
            raise WorkspaceEvidenceExportError("final evidence table rows must all be satisfied")
        for evidence_ref in row.verified_evidence_refs:
            final_refs.add(evidence_ref.value)
    if not final_refs:
        raise WorkspaceEvidenceExportError("final evidence table must reference verified evidence")
    return final_refs


def _validate_verification_runs(verification_runs: tuple[VerificationRun, ...]) -> tuple[VerificationRunRef, ...]:
    if not verification_runs:
        raise WorkspaceEvidenceExportError("verification runs must not be empty")
    refs = tuple(run.verification_run_id for run in verification_runs)
    ref_values = tuple(ref.value for ref in refs)
    if len(ref_values) != len(set(ref_values)):
        raise WorkspaceEvidenceExportError("verification run refs must be unique")
    for run in verification_runs:
        if run.status is not VerificationRunStatus.PASSED:
            raise WorkspaceEvidenceExportError("verification run status must be passed")
    return tuple(sorted(refs, key=lambda ref: ref.value))


def _validate_verified_evidence(verified_evidence: tuple[VerifiedEvidence, ...]) -> tuple[VerifiedEvidenceRef, ...]:
    if not verified_evidence:
        raise WorkspaceEvidenceExportError("verified evidence must not be empty")
    refs = tuple(evidence.verified_evidence_id for evidence in verified_evidence)
    ref_values = tuple(ref.value for ref in refs)
    if len(ref_values) != len(set(ref_values)):
        raise WorkspaceEvidenceExportError("verified evidence refs must be unique")
    return tuple(sorted(refs, key=lambda ref: ref.value))
```

- [ ] **Step 2: Add INV-X1 / INV-X2 / orphan evidence validation**

Append:

```python
def _validate_evidence_ref_closure(
    *,
    source_inventory: SourceInventory,
    verification_runs: tuple[VerificationRun, ...],
    verified_evidence: tuple[VerifiedEvidence, ...],
    final_evidence_table: FinalEvidenceTable,
    final_table_evidence_refs: set[str],
) -> None:
    source_inventory_evidence_refs = {
        evidence_ref.value
        for entry in source_inventory.entries
        for evidence_ref in entry.evidence_refs
    }
    if not source_inventory_evidence_refs:
        raise WorkspaceEvidenceExportError("source inventory entries must reference verified evidence")
    if not source_inventory_evidence_refs.issubset(final_table_evidence_refs):
        raise WorkspaceEvidenceExportError("source inventory evidence refs must be acknowledged by final evidence table")

    verified_evidence_by_ref = {evidence.verified_evidence_id.value: evidence for evidence in verified_evidence}
    unresolved_final_refs = final_table_evidence_refs - set(verified_evidence_by_ref)
    if unresolved_final_refs:
        raise WorkspaceEvidenceExportError("final evidence table verified evidence refs must resolve to verified evidence input")

    linked_evidence_refs = final_table_evidence_refs | source_inventory_evidence_refs
    verification_run_refs = {run.verification_run_id.value for run in verification_runs}
    linked_run_refs: set[str] = set()
    for evidence_ref in linked_evidence_refs:
        evidence = verified_evidence_by_ref.get(evidence_ref)
        if evidence is None:
            raise WorkspaceEvidenceExportError("verified evidence refs must resolve")
        linked_run_refs.update(run_ref.value for run_ref in evidence.verification_run_refs)

    orphan_runs = verification_run_refs - linked_run_refs
    if orphan_runs:
        raise WorkspaceEvidenceExportError("orphan verification run cannot be exported")
```

- [ ] **Step 3: Run targeted tests**

Run:

```bash
PYTHONPATH="src;." python -m pytest tests/proving/test_workspace_evidence_export.py -q
```

Expected: most negative tests pass; happy path is not present yet.

---

### Task 5: Implement builder and happy path tests

**Files:**
- Modify: `src/boardroom_os/workspace/evidence_export.py`
- Modify: `tests/proving/test_workspace_evidence_export.py`

- [ ] **Step 1: Add builder**

Append:

```python
def build_workspace_evidence_bundle(
    *,
    workspace_manifest: WorkspaceManifest,
    package_assembly: PackageAssembly,
    source_inventory: SourceInventory,
    run_manifest: RunManifest,
    verification_runs: tuple[VerificationRun, ...],
    verified_evidence: tuple[VerifiedEvidence, ...],
    final_evidence_table: FinalEvidenceTable,
) -> WorkspaceEvidenceBundle:
    _validate_workspace_package_source_run_refs(
        workspace_manifest=workspace_manifest,
        package_assembly=package_assembly,
        source_inventory=source_inventory,
        run_manifest=run_manifest,
    )
    _validate_run_manifest_mirror(package_assembly=package_assembly, run_manifest=run_manifest)
    final_table_evidence_refs = _validate_final_evidence_table(final_evidence_table)
    verification_run_refs = _validate_verification_runs(verification_runs)
    verified_evidence_refs = _validate_verified_evidence(verified_evidence)
    _validate_evidence_ref_closure(
        source_inventory=source_inventory,
        verification_runs=verification_runs,
        verified_evidence=verified_evidence,
        final_evidence_table=final_evidence_table,
        final_table_evidence_refs=final_table_evidence_refs,
    )

    bundle_id = WorkspaceEvidenceBundleRef(
        value=(
            "workspace-evidence-bundle."
            f"{workspace_manifest.workspace_manifest_id.value}."
            f"{package_assembly.package_assembly_id.value}."
            f"{final_evidence_table.final_evidence_table_id.value}"
        )
    )
    artifacts = _build_artifacts(
        workspace_manifest=workspace_manifest,
        package_assembly=package_assembly,
        source_inventory=source_inventory,
        run_manifest=run_manifest,
        verification_run_refs=verification_run_refs,
        verified_evidence_refs=verified_evidence_refs,
        final_evidence_table=final_evidence_table,
        bundle_id=bundle_id,
    )
    return WorkspaceEvidenceBundle(
        workspace_evidence_bundle_id=bundle_id,
        workspace_manifest_ref=workspace_manifest.workspace_manifest_id,
        package_assembly_ref=package_assembly.package_assembly_id,
        package_contract_ref=workspace_manifest.package_contract_ref,
        source_inventory_ref=source_inventory.source_inventory_id,
        run_manifest_ref=run_manifest.run_manifest_id,
        final_evidence_table_ref=final_evidence_table.final_evidence_table_id,
        verification_run_refs=verification_run_refs,
        verified_evidence_refs=verified_evidence_refs,
        artifacts=artifacts,
        closeout_ready=True,
    )
```

- [ ] **Step 2: Add happy path tests**

Append to `tests/proving/test_workspace_evidence_export.py`:

```python
def test_build_workspace_evidence_bundle_returns_closeout_ready_plan() -> None:
    from boardroom_os.workspace.evidence_export import EvidenceBundleArtifactKind, build_workspace_evidence_bundle

    facts = _facts()
    bundle = build_workspace_evidence_bundle(**facts)

    assert bundle.closeout_ready is True
    assert bundle.workspace_manifest_ref == facts["workspace_manifest"].workspace_manifest_id
    assert bundle.package_assembly_ref == facts["package_assembly"].package_assembly_id
    assert bundle.package_contract_ref == facts["workspace_manifest"].package_contract_ref
    assert bundle.source_inventory_ref == facts["source_inventory"].source_inventory_id
    assert bundle.run_manifest_ref == facts["run_manifest"].run_manifest_id
    assert bundle.final_evidence_table_ref == facts["final_evidence_table"].final_evidence_table_id
    assert bundle.verification_run_refs == (facts["verification_runs"][0].verification_run_id,)
    assert bundle.verified_evidence_refs == (facts["verified_evidence"][0].verified_evidence_id,)
    assert {artifact.artifact_kind for artifact in bundle.artifacts} == set(EvidenceBundleArtifactKind)
    assert tuple(artifact.relative_path.value for artifact in bundle.artifacts) == tuple(
        sorted(artifact.relative_path.value for artifact in bundle.artifacts)
    )
    assert all(artifact.relative_path.value.startswith("20-evidence/") for artifact in bundle.artifacts)


def test_build_workspace_evidence_bundle_is_deterministic() -> None:
    from boardroom_os.workspace.evidence_export import build_workspace_evidence_bundle

    facts = _facts()
    first = build_workspace_evidence_bundle(**facts)
    second = build_workspace_evidence_bundle(**facts)

    assert first.workspace_evidence_bundle_id == second.workspace_evidence_bundle_id
    assert first.model_dump() == second.model_dump()
```

- [ ] **Step 3: Run targeted tests**

Run:

```bash
PYTHONPATH="src;." python -m pytest tests/proving/test_workspace_evidence_export.py -q
```

Expected: PASS.

---

### Task 6: Add direct path/model guard tests and public exports

**Files:**
- Modify: `tests/proving/test_workspace_evidence_export.py`
- Modify: `src/boardroom_os/workspace/evidence_export.py`
- Modify: `src/boardroom_os/workspace/__init__.py`

- [ ] **Step 1: Add model guard tests**

Append tests:

```python
def test_evidence_bundle_artifact_path_rejects_non_evidence_locations() -> None:
    from boardroom_os.workspace.evidence_export import EvidenceBundleArtifactPath

    for path in (
        "10-project/evidence.json",
        "00-boardroom/evidence.json",
        "30-audit/evidence.json",
        "src/boardroom_os/evidence.json",
        "doc/evidence.json",
        "/20-evidence/tests/run.json",
        "20-evidence/../run.json",
        "20-evidence/tests/",
    ):
        with pytest.raises(_VERIFY_ERRORS):
            EvidenceBundleArtifactPath(value=path)


def test_workspace_evidence_bundle_rejects_forged_closeout_ready_without_artifacts() -> None:
    from boardroom_os.workspace.evidence_export import WorkspaceEvidenceBundle, WorkspaceEvidenceBundleRef

    facts = _facts()
    with pytest.raises(_VERIFY_ERRORS, match="artifact"):
        WorkspaceEvidenceBundle(
            workspace_evidence_bundle_id=WorkspaceEvidenceBundleRef(value="workspace-evidence-bundle.forged"),
            workspace_manifest_ref=facts["workspace_manifest"].workspace_manifest_id,
            package_assembly_ref=facts["package_assembly"].package_assembly_id,
            package_contract_ref=facts["workspace_manifest"].package_contract_ref,
            source_inventory_ref=facts["source_inventory"].source_inventory_id,
            run_manifest_ref=facts["run_manifest"].run_manifest_id,
            final_evidence_table_ref=facts["final_evidence_table"].final_evidence_table_id,
            verification_run_refs=(),
            verified_evidence_refs=(),
            artifacts=(),
            closeout_ready=True,
        )
```

- [ ] **Step 2: Add `__all__` to production module**

Append:

```python
__all__ = [
    "EvidenceBundleArtifact",
    "EvidenceBundleArtifactKind",
    "EvidenceBundleArtifactPath",
    "WorkspaceEvidenceBundle",
    "WorkspaceEvidenceBundleRef",
    "WorkspaceEvidenceExportError",
    "build_workspace_evidence_bundle",
]
```

- [ ] **Step 3: Export from workspace package**

Modify `src/boardroom_os/workspace/__init__.py`:

```python
from boardroom_os.workspace.evidence_export import (
    EvidenceBundleArtifact,
    EvidenceBundleArtifactKind,
    EvidenceBundleArtifactPath,
    WorkspaceEvidenceBundle,
    WorkspaceEvidenceBundleRef,
    WorkspaceEvidenceExportError,
    build_workspace_evidence_bundle,
)
```

Add the same seven names to `__all__`.

- [ ] **Step 4: Run targeted tests**

Run:

```bash
PYTHONPATH="src;." python -m pytest tests/proving/test_workspace_evidence_export.py -q
```

Expected: PASS.

---

### Task 7: Run verification and fix implementation drift

**Files:**
- Modify only files needed to fix failing tests.

- [ ] **Step 1: Run focused workspace/evidence tests**

Run:

```bash
PYTHONPATH="src;." python -m pytest tests/proving/test_workspace_evidence_export.py tests/proving/test_source_inventory.py tests/proving/test_run_manifest.py tests/evidence/test_final_evidence_table.py tests/evidence/test_evidence_verifier.py -q
```

Expected: PASS.

- [ ] **Step 2: Run broader proving test subset**

Run:

```bash
PYTHONPATH="src;." python -m pytest tests/proving -q
```

Expected: PASS.

- [ ] **Step 3: Inspect git diff**

Run:

```bash
git diff -- src/boardroom_os/workspace/evidence_export.py src/boardroom_os/workspace/__init__.py tests/proving/test_workspace_evidence_export.py doc/04-implementation/v2-060e-workspace-evidence-export-implementation-plan.md doc/04-implementation/INDEX.md
```

Expected: only V2-060E implementation, tests, and docs index/plan changes are present.

---

### Task 8: Complete documentation update protocol

**Files:**
- Modify: `doc/04-implementation/backlog.md`
- Modify: `doc/04-implementation/acceptance-criteria.md`
- Modify: `doc/05-project-log/2026-05.md`

- [ ] **Step 1: Update backlog status**

In `doc/04-implementation/backlog.md`, mark V2-060E（WorkspaceEvidenceExport，工作区证据导出） as DONE only after tests pass. Keep V2-060F open.

- [ ] **Step 2: Update Phase 6 acceptance checkbox**

In `doc/04-implementation/acceptance-criteria.md`, change only this checkbox:

```markdown
- [x] Workspace / package / evidence 三者同步 — 由 V2-060E `test_workspace_evidence_export.py` 证明
```

Do not mark V2-060F, Phase 6 total, or Phase 6 completion gates done.

- [ ] **Step 3: Update monthly project log**

In `doc/05-project-log/2026-05.md`, add a concise entry for 2026-05-23 stating that V2-060E completed WorkspaceEvidenceBundle（工作区证据包） pure bundle plan, fail-closed cross-model evidence ref closure, deterministic `20-evidence` artifact plan, and no filesystem materialization.

- [ ] **Step 4: Run final targeted verification**

Run:

```bash
PYTHONPATH="src;." python -m pytest tests/proving/test_workspace_evidence_export.py tests/proving/test_source_inventory.py tests/proving/test_run_manifest.py tests/evidence/test_final_evidence_table.py -q
```

Expected: PASS.

---

## Self-Review

- Spec coverage: The plan covers all V2-060E goals: new bundle/artifact models, deterministic fixed artifact plan, fail-closed FinalEvidenceTable（最终证据表） checks, SourceInventory（源码清单） lineage closure, VerificationRun（验证运行） status/uniqueness/orphan checks, VerifiedEvidence（已验证证据） resolution, artifact path guards, derived `closeout_ready`, and happy path model dump determinism.
- Review coverage: The plan explicitly includes INV-X1, INV-X2, orphan evidence（孤儿证据）, orphan run（孤儿验证运行）, `workspace_manifest.evidence_root`-derived paths, RunManifest（运行清单） mirror identity, and `20-evidence/closeout` reserved path scope.
- Boundary coverage: The production module imports no filesystem writer, CommandRunner（命令执行器）, runtime executor（运行时执行器）, provider executor（模型执行器）, git adapter（Git 适配器）, closeout module（收尾模块）, or legacy implementation.
- Placeholder scan: No TBD/TODO/“implement later” placeholders remain.
