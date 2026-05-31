from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

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
    PackageContract,
    PackageProjectType,
    create_package_contract,
)
from boardroom_os.contracts.source_surface import OwnerSeatRef, RequiredTestRef, SourceSurface
from boardroom_os.contracts.types import AcceptanceRef, ContractId, EvidenceObligationRef, SourceSurfaceRef
from boardroom_os.workspace.manifest import WorkflowRef, WorkspacePath, WorkspaceSection, build_workspace_manifest
from tests.fixtures.execution.role_prompt_hooks import baseline_role_prompt_hook

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
    project_type: PackageProjectType = PackageProjectType.SOFTWARE,
    run_commands: tuple[PackageCommand, ...] | None = None,
    test_commands: tuple[PackageCommand, ...] | None = None,
    package_root: str = "10-project",
    docs_required: bool = True,
):
    profile = _profile()
    contract_fields = {
        "package_contract_id": ContractId(value="package-contract.run-manifest"),
        "project_charter_ref": ContractId(value="project.charter.run-manifest"),
        "package_root": package_root,
        "project_type": project_type,
        "source_surfaces": (
            _surface("backend-api", ("backend/",), ("AC-BACKEND",)),
            _surface("package-tests", ("tests/",), ("AC-TESTS",)),
            _surface("run-manifest", ("run-manifest.json",), ("AC-RUN",)),
            _surface("project-docs", ("docs/",), ("AC-DOCS",)),
        ),
        "run_commands": (_command("run-package", label="Run package"),) if run_commands is None else run_commands,
        "test_commands": (_command("test-package", label="Test package"),) if test_commands is None else test_commands,
        "integration_boundaries": (IntegrationBoundary(value="local-process"),),
        "docs_required": docs_required,
        "closeout_required": True,
        "methodology_profile_ref": profile.methodology_profile_id if docs_required else None,
        "docs_template_key": profile.docs_template_key if docs_required else None,
        "documentation_obligations": profile.documentation_obligations if docs_required else (),
    }
    if not docs_required:
        return PackageContract(**contract_fields)
    return create_package_contract(
        methodology_registry=MethodologyProfileRegistry.from_profiles(profile),
        **contract_fields,
    )


def _workspace_manifest(package_contract=None):
    contract = package_contract or _package_contract()
    return build_workspace_manifest(
        workflow_ref=WorkflowRef(value="workflow-run-manifest"),
        workspace_root=WorkspacePath(value="workspace/workflow-run-manifest"),
        package_contract=contract,
    )


def _tamper_manifest_command(manifest, command_id: str, **updates):
    target_command_id = ContractId(value=command_id)
    return manifest.model_copy(
        update={
            "commands": tuple(
                command.model_copy(update=updates) if command.command_id == target_command_id else command
                for command in manifest.commands
            )
        }
    )


def test_workspace_package_exports_run_manifest_public_api() -> None:
    from boardroom_os.workspace import (
        RunManifest,
        RunManifestBinding,
        RunManifestCommand,
        RunManifestCommandKind,
        RunManifestError,
        RunManifestRef,
        build_run_manifest,
        validate_run_manifest_binding,
    )

    assert RunManifest is not None
    assert RunManifestBinding is not None
    assert RunManifestCommand is not None
    assert RunManifestCommandKind.RUN.value == "run"
    assert RunManifestError is not None
    assert RunManifestRef is not None
    assert build_run_manifest is not None
    assert validate_run_manifest_binding is not None


def test_build_run_manifest_rejects_software_package_without_run_commands() -> None:
    from boardroom_os.workspace.run_manifest import build_run_manifest

    valid_contract = _package_contract()
    invalid_contract = valid_contract.model_copy(update={"run_commands": ()})

    with pytest.raises(_VERIFY_ERRORS, match="run command|run commands"):
        build_run_manifest(
            workspace_manifest=_workspace_manifest(valid_contract),
            package_contract=invalid_contract,
        )


def test_build_run_manifest_rejects_software_package_without_test_commands() -> None:
    from boardroom_os.workspace.run_manifest import build_run_manifest

    valid_contract = _package_contract()
    invalid_contract = valid_contract.model_copy(update={"test_commands": ()})

    with pytest.raises(_VERIFY_ERRORS, match="test command|test commands"):
        build_run_manifest(
            workspace_manifest=_workspace_manifest(valid_contract),
            package_contract=invalid_contract,
        )


def test_build_run_manifest_allows_documentation_package_without_commands() -> None:
    from boardroom_os.workspace.run_manifest import build_run_manifest

    package_contract = _package_contract(
        project_type=PackageProjectType.DOCUMENTATION,
        run_commands=(),
        test_commands=(),
    )

    manifest = build_run_manifest(
        workspace_manifest=_workspace_manifest(package_contract),
        package_contract=package_contract,
    )

    assert manifest.commands == ()


def test_run_manifest_rejects_duplicate_command_ids() -> None:
    from boardroom_os.workspace.run_manifest import RunManifest, build_run_manifest

    package_contract = _package_contract()
    manifest = build_run_manifest(
        workspace_manifest=_workspace_manifest(package_contract),
        package_contract=package_contract,
    )
    duplicated_commands = (
        manifest.commands[0],
        manifest.commands[1].model_copy(update={"command_id": manifest.commands[0].command_id}),
    )

    with pytest.raises(_VERIFY_ERRORS, match="unique|duplicate|command ids"):
        RunManifest.model_validate(manifest.model_dump() | {"commands": duplicated_commands})


def test_run_manifest_command_rejects_empty_command() -> None:
    from boardroom_os.workspace.run_manifest import RunManifestCommand, RunManifestCommandKind

    with pytest.raises(_VERIFY_ERRORS, match="command"):
        RunManifestCommand(
            command_id=ContractId(value="run-package"),
            kind=RunManifestCommandKind.RUN,
            label="Run package",
            command=(),
            cwd=".",
        )


def test_run_manifest_command_rejects_empty_command_item() -> None:
    from boardroom_os.workspace.run_manifest import RunManifestCommand, RunManifestCommandKind

    with pytest.raises(_VERIFY_ERRORS, match="command"):
        RunManifestCommand(
            command_id=ContractId(value="run-package"),
            kind=RunManifestCommandKind.RUN,
            label="Run package",
            command=(sys.executable, "   "),
            cwd=".",
        )


def test_run_manifest_command_rejects_empty_cwd() -> None:
    from boardroom_os.workspace.run_manifest import RunManifestCommand, RunManifestCommandKind

    with pytest.raises(_VERIFY_ERRORS, match="empty|cwd|text fields"):
        RunManifestCommand(
            command_id=ContractId(value="run-package"),
            kind=RunManifestCommandKind.RUN,
            label="Run package",
            command=(sys.executable, "-c", "print('ok')"),
            cwd="   ",
        )


def test_run_manifest_command_rejects_extra_fields() -> None:
    from boardroom_os.workspace.run_manifest import RunManifestCommand, RunManifestCommandKind

    with pytest.raises(_VERIFY_ERRORS, match="extra|unexpected|forbidden"):
        RunManifestCommand(
            command_id=ContractId(value="run-package"),
            kind=RunManifestCommandKind.RUN,
            label="Run package",
            command=(sys.executable, "-c", "print('ok')"),
            cwd=".",
            unexpected="x",
        )


def test_run_manifest_rejects_extra_fields() -> None:
    from boardroom_os.workspace.run_manifest import RunManifest, build_run_manifest

    package_contract = _package_contract()
    manifest = build_run_manifest(
        workspace_manifest=_workspace_manifest(package_contract),
        package_contract=package_contract,
    )

    with pytest.raises(_VERIFY_ERRORS, match="extra|unexpected|forbidden"):
        RunManifest(
            run_manifest_id=manifest.run_manifest_id,
            workspace_manifest_ref=manifest.workspace_manifest_ref,
            package_contract_ref=manifest.package_contract_ref,
            package_root=manifest.package_root,
            commands=manifest.commands,
            unexpected="x",
        )


def test_build_run_manifest_rejects_workspace_package_contract_ref_mismatch() -> None:
    from boardroom_os.workspace.run_manifest import build_run_manifest

    package_contract = _package_contract()
    workspace_manifest = _workspace_manifest(package_contract).model_copy(
        update={"package_contract_ref": ContractId(value="package-contract.other")}
    )

    with pytest.raises(_VERIFY_ERRORS, match="package_contract_ref|package contract"):
        build_run_manifest(
            workspace_manifest=workspace_manifest,
            package_contract=package_contract,
        )


def test_build_run_manifest_rejects_workspace_package_root_mismatch() -> None:
    from boardroom_os.workspace.run_manifest import build_run_manifest

    package_contract = _package_contract()
    base_workspace_manifest = _workspace_manifest(package_contract)
    workspace_manifest = base_workspace_manifest.model_copy(
        update={
            "sections": tuple(
                section.model_copy(update={"relative_path": WorkspacePath(value="11-project")})
                if section.section is WorkspaceSection.PROJECT
                else section
                for section in base_workspace_manifest.sections
            )
        }
    )

    with pytest.raises(_VERIFY_ERRORS, match="package root"):
        build_run_manifest(
            workspace_manifest=workspace_manifest,
            package_contract=package_contract,
        )


def test_build_run_manifest_rejects_non_canonical_package_root() -> None:
    from boardroom_os.workspace.run_manifest import build_run_manifest

    package_contract = _package_contract().model_copy(update={"package_root": "11-project"})
    base_workspace_manifest = _workspace_manifest()
    workspace_manifest = base_workspace_manifest.model_copy(
        update={
            "package_contract_ref": package_contract.package_contract_id,
            "sections": tuple(
                section.model_copy(update={"relative_path": WorkspacePath(value="11-project")})
                if section.section is WorkspaceSection.PROJECT
                else section
                for section in base_workspace_manifest.sections
            ),
        }
    )

    with pytest.raises(_VERIFY_ERRORS, match="10-project|package root"):
        build_run_manifest(
            workspace_manifest=workspace_manifest,
            package_contract=package_contract,
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


def test_binding_rejects_manifest_command_label_that_differs_from_package_contract() -> None:
    from boardroom_os.workspace.run_manifest import build_run_manifest, validate_run_manifest_binding

    package_contract = _package_contract()
    manifest = build_run_manifest(
        workspace_manifest=_workspace_manifest(package_contract),
        package_contract=package_contract,
    )
    tampered_manifest = _tamper_manifest_command(manifest, "run-package", label="Tampered run package")

    with pytest.raises(_VERIFY_ERRORS, match="package contract command|run manifest command|label"):
        validate_run_manifest_binding(
            run_manifest=tampered_manifest,
            package_contract=package_contract,
            command_id=ContractId(value="run-package"),
        )


def test_binding_rejects_manifest_command_tuple_that_differs_from_package_contract() -> None:
    from boardroom_os.workspace.run_manifest import build_run_manifest, validate_run_manifest_binding

    package_contract = _package_contract()
    manifest = build_run_manifest(
        workspace_manifest=_workspace_manifest(package_contract),
        package_contract=package_contract,
    )
    tampered_manifest = _tamper_manifest_command(
        manifest,
        "run-package",
        command=(sys.executable, "-c", "print('tampered')"),
    )

    with pytest.raises(_VERIFY_ERRORS, match="package contract command|run manifest command|command"):
        validate_run_manifest_binding(
            run_manifest=tampered_manifest,
            package_contract=package_contract,
            command_id=ContractId(value="run-package"),
        )


def test_binding_rejects_manifest_command_cwd_that_differs_from_package_contract() -> None:
    from boardroom_os.workspace.run_manifest import build_run_manifest, validate_run_manifest_binding

    package_contract = _package_contract()
    manifest = build_run_manifest(
        workspace_manifest=_workspace_manifest(package_contract),
        package_contract=package_contract,
    )
    tampered_manifest = _tamper_manifest_command(manifest, "run-package", cwd="other-directory")

    with pytest.raises(_VERIFY_ERRORS, match="package contract command|run manifest command|cwd"):
        validate_run_manifest_binding(
            run_manifest=tampered_manifest,
            package_contract=package_contract,
            command_id=ContractId(value="run-package"),
        )


def test_binding_rejects_manifest_command_kind_that_differs_from_package_contract() -> None:
    from boardroom_os.workspace.run_manifest import RunManifestCommandKind, build_run_manifest, validate_run_manifest_binding

    package_contract = _package_contract()
    manifest = build_run_manifest(
        workspace_manifest=_workspace_manifest(package_contract),
        package_contract=package_contract,
    )
    tampered_manifest = _tamper_manifest_command(manifest, "run-package", kind=RunManifestCommandKind.TEST)

    with pytest.raises(_VERIFY_ERRORS, match="package contract command|run manifest command|kind"):
        validate_run_manifest_binding(
            run_manifest=tampered_manifest,
            package_contract=package_contract,
            command_id=ContractId(value="run-package"),
        )


def test_binding_rejects_run_manifest_missing_declared_package_contract_command() -> None:
    from boardroom_os.workspace.run_manifest import build_run_manifest, validate_run_manifest_binding

    package_contract = _package_contract()
    manifest = build_run_manifest(
        workspace_manifest=_workspace_manifest(package_contract),
        package_contract=package_contract,
    )
    tampered_manifest = manifest.model_copy(
        update={
            "commands": tuple(
                command for command in manifest.commands if command.command_id != ContractId(value="test-package")
            )
        }
    )

    with pytest.raises(_VERIFY_ERRORS, match="run manifest|package contract|command"):
        validate_run_manifest_binding(
            run_manifest=tampered_manifest,
            package_contract=package_contract,
            command_id=ContractId(value="run-package"),
        )


def test_binding_rejects_run_manifest_command_not_declared_by_package_contract() -> None:
    from boardroom_os.workspace.run_manifest import (
        RunManifestCommand,
        RunManifestCommandKind,
        build_run_manifest,
        validate_run_manifest_binding,
    )

    package_contract = _package_contract()
    manifest = build_run_manifest(
        workspace_manifest=_workspace_manifest(package_contract),
        package_contract=package_contract,
    )
    tampered_manifest = manifest.model_copy(
        update={
            "commands": (
                *manifest.commands,
                RunManifestCommand(
                    command_id=ContractId(value="extra-package"),
                    kind=RunManifestCommandKind.RUN,
                    label="Extra package",
                    command=(sys.executable, "-c", "print('extra')"),
                    cwd=".",
                ),
            )
        }
    )

    with pytest.raises(_VERIFY_ERRORS, match="run manifest|package contract|command"):
        validate_run_manifest_binding(
            run_manifest=tampered_manifest,
            package_contract=package_contract,
            command_id=ContractId(value="run-package"),
        )


def test_binding_rejects_forged_run_manifest_id() -> None:
    from boardroom_os.workspace.run_manifest import RunManifestRef, build_run_manifest, validate_run_manifest_binding

    package_contract = _package_contract()
    manifest = build_run_manifest(
        workspace_manifest=_workspace_manifest(package_contract),
        package_contract=package_contract,
    ).model_copy(update={"run_manifest_id": RunManifestRef(value="run-manifest.forged")})

    with pytest.raises(_VERIFY_ERRORS, match="run manifest id"):
        validate_run_manifest_binding(
            run_manifest=manifest,
            package_contract=package_contract,
            command_id=ContractId(value="run-package"),
        )


def test_binding_rejects_non_canonical_package_root_even_when_manifest_and_contract_match() -> None:
    from boardroom_os.workspace.run_manifest import build_run_manifest, validate_run_manifest_binding

    package_contract = _package_contract()
    manifest = build_run_manifest(
        workspace_manifest=_workspace_manifest(package_contract),
        package_contract=package_contract,
    )
    non_canonical_contract = package_contract.model_copy(update={"package_root": "other-root"})
    non_canonical_manifest = manifest.model_copy(update={"package_root": WorkspacePath(value="other-root")})

    with pytest.raises(_VERIFY_ERRORS, match="10-project|package root"):
        validate_run_manifest_binding(
            run_manifest=non_canonical_manifest,
            package_contract=non_canonical_contract,
            command_id=ContractId(value="run-package"),
        )


def test_binding_allows_declared_command_to_run_through_command_runner() -> None:
    from boardroom_os.adapters.process_runner import CommandRunner, CommandRunnerInput, ProcessResult
    from boardroom_os.agents.profiles import ModelExecutionProfile
    from boardroom_os.agents.seat import AgentSeatRef
    from boardroom_os.contracts.evidence_obligation import EvidenceObligation, RequiredArtifactType
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
    from boardroom_os.execution.verification_run import (
        EnvironmentProfileRef,
        RunnerRef,
        VerificationRunStatus,
        WorkspaceSnapshotRef,
    )
    from boardroom_os.graph.ticket import TicketId
    from boardroom_os.workspace.run_manifest import build_run_manifest, validate_run_manifest_binding

    run_command = _command("run-package", label="Run package", command=(sys.executable, "-c", "print('ok')"))
    package_contract = _package_contract(run_commands=(run_command,), docs_required=False)
    manifest = build_run_manifest(
        workspace_manifest=_workspace_manifest(package_contract),
        package_contract=package_contract,
    )
    binding = validate_run_manifest_binding(
        run_manifest=manifest,
        package_contract=package_contract,
        command_id=ContractId(value="run-package"),
    )
    execution_package = ExecutionPackage(
        execution_package_id=ExecutionPackageId(value="execution-package.run-manifest"),
        ticket_ref=TicketId(value="ticket.run-manifest"),
        graph_version=1,
        seat_ref=AgentSeatRef(value="seat.run-manifest"),
        model_execution_profile=ModelExecutionProfile(
            model_execution_profile_id="model-profile.run-manifest",
            provider="anthropic",
            model="claude-opus-4-7",
            reasoning_effort="medium",
            context_window=200000,
            temperature=0.2,
            tool_permissions=("process.run",),
            fallback_policy_ref="fallback-policy.default",
        ),
        role_prompt_hook=baseline_role_prompt_hook(),
        objective="Run declared command through the run manifest binding.",
        context_refs=(ContextRef(value="context.run-manifest"),),
        constraints=("Use only the declared run manifest command.",),
        acceptance_refs=(AcceptanceRef(value="AC-RUN"),),
        source_surface_refs=(SourceSurfaceRef(value="run-manifest"),),
        allowed_read_refs=(AllowedReadRef(value="read.run-manifest"),),
        allowed_write_set=(AllowedWritePath(value="tests/proving"),),
        required_outputs=(RequiredOutput(value="verification run"),),
        commands=(run_command,),
        evidence_obligations=(
            EvidenceObligation(
                evidence_obligation_id=EvidenceObligationRef(value="evidence-obligation.run-manifest"),
                acceptance_refs=(AcceptanceRef(value="AC-RUN"),),
                source_surface_refs=(SourceSurfaceRef(value="run-manifest"),),
                required_artifact_type=RequiredArtifactType(value="command_run"),
                required_verifier={"value": "command_runner"},
                blocking=True,
            ),
        ),
        fallback_policy_ref=FallbackPolicyRef(value="fallback-policy.default"),
        audit_requirements=(AuditRequirement(value="record verification run"),),
    )
    process_executor = CapturingProcessExecutor(ProcessResult(exit_code=0, stdout="ok\n", stderr=""))
    runner_ref = RunnerRef(value="runner.local-subprocess")
    environment_profile_ref = EnvironmentProfileRef(value="environment.local-python")
    workspace_snapshot_ref = WorkspaceSnapshotRef(value="workspace-snapshot.run-manifest")

    package_root = Path(".")
    result = CommandRunner(
        process_executor=process_executor,
        clock=SequenceClock(_started_at(), _finished_at()),
    ).run(
        CommandRunnerInput(
            execution_package=execution_package,
            package_contract=package_contract,
            command_id=binding.command_id,
            package_root=package_root,
            runner_ref=runner_ref,
            environment_profile_ref=environment_profile_ref,
            workspace_snapshot_ref=workspace_snapshot_ref,
        )
    )

    assert execution_package.commands == (run_command,)
    assert process_executor.commands == [binding.command]
    assert process_executor.cwd_values == [package_root.resolve()]
    assert result.stdout == "ok\n"
    assert result.stderr == ""
    assert result.verification_run.command_id == binding.command_id
    assert result.verification_run.command == binding.command
    assert result.verification_run.cwd == binding.cwd
    assert result.verification_run.exit_code == 0
    assert result.verification_run.status is VerificationRunStatus.PASSED
    assert result.verification_run.verification_run_id.value == "verification-run.execution-package.run-manifest.run-package"
    assert result.verification_run.stdout_ref.value == (
        f"command-output.{result.verification_run.verification_run_id.value}.stdout"
    )
    assert result.verification_run.stderr_ref.value == (
        f"command-output.{result.verification_run.verification_run_id.value}.stderr"
    )
    assert result.verification_run.runner_ref == runner_ref
    assert result.verification_run.environment_profile_ref == environment_profile_ref
    assert result.verification_run.workspace_snapshot_ref == workspace_snapshot_ref


class CapturingProcessExecutor:
    def __init__(self, process_result) -> None:
        self._process_result = process_result
        self.commands: list[tuple[str, ...]] = []
        self.cwd_values: list[Path] = []

    def run(self, *, command: tuple[str, ...], cwd: Path):
        self.commands.append(command)
        self.cwd_values.append(cwd)
        return self._process_result


class SequenceClock:
    def __init__(self, *timestamps: datetime) -> None:
        self._timestamps = list(timestamps)

    def now(self) -> datetime:
        return self._timestamps.pop(0)


def _started_at() -> datetime:
    return datetime(2026, 5, 23, 9, 0, tzinfo=UTC)


def _finished_at() -> datetime:
    return datetime(2026, 5, 23, 9, 0, 1, tzinfo=UTC)


def test_model_dump_serializes_command_kind_as_string() -> None:
    from boardroom_os.workspace.run_manifest import RunManifestCommandKind, build_run_manifest

    package_contract = _package_contract()
    manifest = build_run_manifest(
        workspace_manifest=_workspace_manifest(package_contract),
        package_contract=package_contract,
    )

    kind = manifest.model_dump()["commands"][0]["kind"]

    assert kind in {"run", "test"}
    assert not isinstance(kind, RunManifestCommandKind)
