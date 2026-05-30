from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from boardroom_os.adapters.process_runner import (
    CommandRunner,
    CommandRunnerError,
    CommandRunnerInput,
    ProcessResult,
)
from boardroom_os.agents.profiles import ModelExecutionProfile
from boardroom_os.agents.seat import AgentSeatRef
from boardroom_os.contracts.evidence_obligation import EvidenceObligation, RequiredArtifactType
from boardroom_os.contracts.package import IntegrationBoundary, PackageCommand, PackageContract, PackageProjectType
from boardroom_os.contracts.source_surface import OwnerSeatRef, RequiredTestRef, SourceSurface
from boardroom_os.contracts.types import AcceptanceRef, ContractId, EvidenceObligationRef, SourceSurfaceRef
from boardroom_os.execution.package import (
    AllowedReadRef,
    AllowedWritePath,
    AuditRequirement,
    ContextRef,
    ExecutionPackage,
    ExecutionPackageId,
    ExecutionPackageRef,
    FallbackPolicyRef,
    RequiredOutput,
)
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


def _started_at() -> datetime:
    return datetime(2026, 5, 18, 9, 0, tzinfo=UTC)


def _finished_at() -> datetime:
    return datetime(2026, 5, 18, 9, 0, 1, tzinfo=UTC)


def _command() -> PackageCommand:
    return PackageCommand(
        command_id=ContractId(value="command.test"),
        label="Run tests",
        command=("python", "-c", "print('ok')"),
        cwd=".",
    )


def _verification_run_fields(**overrides: object) -> dict[str, object]:
    command = _command()
    fields: dict[str, object] = {
        "verification_run_id": VerificationRunRef(value="verification-run.command.test.1"),
        "execution_package_ref": ExecutionPackageRef(value="execution-package.backend-api"),
        "ticket_ref": TicketId(value="ticket.backend-api"),
        "command_id": command.command_id,
        "command": command.command,
        "cwd": command.cwd,
        "exit_code": 0,
        "status": VerificationRunStatus.PASSED,
        "stdout_ref": CommandOutputRef(value="command-output.verification-run.command.test.1.stdout"),
        "stderr_ref": CommandOutputRef(value="command-output.verification-run.command.test.1.stderr"),
        "duration_ms": 1000,
        "started_at": _started_at(),
        "finished_at": _finished_at(),
        "runner_ref": RunnerRef(value="runner.local-subprocess"),
        "environment_profile_ref": EnvironmentProfileRef(value="environment.local-python"),
        "workspace_snapshot_ref": WorkspaceSnapshotRef(value="workspace-snapshot.test"),
    }
    fields.update(overrides)
    return fields


def test_verification_run_accepts_valid_command_fact() -> None:
    verification_run = VerificationRun(**_verification_run_fields())

    assert verification_run.status is VerificationRunStatus.PASSED
    assert verification_run.exit_code == 0
    assert verification_run.command_id == ContractId(value="command.test")
    assert verification_run.command == ("python", "-c", "print('ok')")
    assert verification_run.cwd == "."
    assert verification_run.stdout_ref == CommandOutputRef(
        value="command-output.verification-run.command.test.1.stdout"
    )
    assert verification_run.stderr_ref == CommandOutputRef(
        value="command-output.verification-run.command.test.1.stderr"
    )
    assert verification_run.runner_ref == RunnerRef(value="runner.local-subprocess")
    assert verification_run.environment_profile_ref == EnvironmentProfileRef(
        value="environment.local-python"
    )
    assert verification_run.workspace_snapshot_ref == WorkspaceSnapshotRef(value="workspace-snapshot.test")


def test_verification_run_rejects_synthetic_success_without_exit_code() -> None:
    fields = _verification_run_fields()
    del fields["exit_code"]

    with pytest.raises(ValidationError):
        VerificationRun(**fields)


@pytest.mark.parametrize("missing_field", ["stdout_ref", "stderr_ref"])
def test_verification_run_requires_stdout_and_stderr_refs(missing_field: str) -> None:
    fields = _verification_run_fields()
    del fields[missing_field]

    with pytest.raises(ValidationError):
        VerificationRun(**fields)


@pytest.mark.parametrize(
    ("exit_code", "status"),
    [
        (1, VerificationRunStatus.PASSED),
        (0, VerificationRunStatus.FAILED),
    ],
)
def test_verification_run_rejects_status_that_disagrees_with_exit_code(
    exit_code: int,
    status: VerificationRunStatus,
) -> None:
    with pytest.raises(ValidationError, match="status must match exit_code"):
        VerificationRun(
            **_verification_run_fields(
                exit_code=exit_code,
                status=status,
            )
        )


def test_verification_run_requires_environment_profile_ref() -> None:
    fields = _verification_run_fields()
    del fields["environment_profile_ref"]

    with pytest.raises(ValidationError):
        VerificationRun(**fields)


def test_verification_run_requires_workspace_snapshot_ref() -> None:
    fields = _verification_run_fields()
    del fields["workspace_snapshot_ref"]

    with pytest.raises(ValidationError):
        VerificationRun(**fields)


@pytest.mark.parametrize(
    ("timestamp_field", "timestamp_value"),
    [
        ("started_at", datetime(2026, 5, 18, 9, 0)),
        ("finished_at", datetime(2026, 5, 18, 9, 0, 1)),
    ],
)
def test_verification_run_rejects_naive_timestamps(
    timestamp_field: str,
    timestamp_value: datetime,
) -> None:
    with pytest.raises(ValidationError, match="timezone-aware"):
        VerificationRun(**_verification_run_fields(**{timestamp_field: timestamp_value}))


def test_verification_run_rejects_finished_at_before_started_at() -> None:
    with pytest.raises(ValidationError, match="finished_at"):
        VerificationRun(
            **_verification_run_fields(
                started_at=_finished_at(),
                finished_at=_started_at(),
            )
        )


def test_verification_run_accepts_duration_equal_to_millisecond_time_window() -> None:
    verification_run = VerificationRun(
        **_verification_run_fields(
            duration_ms=1001,
            started_at=_started_at(),
            finished_at=_started_at() + timedelta(milliseconds=1001),
        )
    )

    assert verification_run.duration_ms == 1001


def test_verification_run_rejects_duration_longer_than_time_window() -> None:
    with pytest.raises(ValidationError, match="duration_ms"):
        VerificationRun(
            **_verification_run_fields(
                duration_ms=2000,
                started_at=_started_at(),
                finished_at=_started_at() + timedelta(milliseconds=1000),
            )
        )


def _python_command(command_id: str = "command.test", *, label: str = "Run tests", cwd: str = ".") -> PackageCommand:
    return PackageCommand(
        command_id=ContractId(value=command_id),
        label=label,
        command=(sys.executable, "-c", "print('ok')"),
        cwd=cwd,
    )


def _different_output_python_command() -> PackageCommand:
    return PackageCommand(
        command_id=ContractId(value="command.test"),
        label="Run tests",
        command=(sys.executable, "-c", "print('different')"),
        cwd=".",
    )


def _unused_test_command() -> PackageCommand:
    return PackageCommand(
        command_id=ContractId(value="command.unused-test"),
        label="Unused test command",
        command=(sys.executable, "-c", "print('unused')"),
        cwd=".",
    )


def _model_execution_profile() -> ModelExecutionProfile:
    return ModelExecutionProfile(
        model_execution_profile_id="model-profile.worker",
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
        evidence_obligation_id=EvidenceObligationRef(value="evidence-obligation.command"),
        acceptance_refs=(AcceptanceRef(value="AC-COMMAND"),),
        source_surface_refs=(SourceSurfaceRef(value="surface.tests"),),
        required_artifact_type=RequiredArtifactType(value="command_run"),
        required_verifier={"value": "command_runner"},
        blocking=True,
    )


def _source_surface() -> SourceSurface:
    return SourceSurface(
        source_surface_ref=SourceSurfaceRef(value="surface.tests"),
        name="Tests",
        paths=("tests",),
        owned_by=OwnerSeatRef(value="owner.tests"),
        acceptance_refs=(AcceptanceRef(value="AC-COMMAND"),),
        required_tests=(RequiredTestRef(value="command.test"),),
    )


def _package_contract(*commands: PackageCommand) -> PackageContract:
    selected_commands = commands or (_python_command(),)
    return PackageContract(
        package_contract_id=ContractId(value="package-contract.tiny"),
        project_charter_ref=ContractId(value="project-charter.tiny"),
        package_root="10-project",
        project_type=PackageProjectType.SOFTWARE,
        source_surfaces=(_source_surface(),),
        run_commands=selected_commands,
        test_commands=(_unused_test_command(),),
        integration_boundaries=(IntegrationBoundary(value="local-process"),),
        docs_required=False,
        closeout_required=True,
    )


def _execution_package(*commands: PackageCommand) -> ExecutionPackage:
    selected_commands = commands or (_python_command(),)
    return ExecutionPackage(
        execution_package_id=ExecutionPackageId(value="execution-package.command"),
        ticket_ref=TicketId(value="ticket.command"),
        graph_version=11,
        seat_ref=AgentSeatRef(value="seat.worker.command"),
        model_execution_profile=_model_execution_profile(),
        objective="Run declared verification command.",
        context_refs=(ContextRef(value="context.contracts"),),
        constraints=("Only run declared package commands.",),
        acceptance_refs=(AcceptanceRef(value="AC-COMMAND"),),
        source_surface_refs=(SourceSurfaceRef(value="surface.tests"),),
        allowed_read_refs=(AllowedReadRef(value="read.package"),),
        allowed_write_set=(AllowedWritePath(value="tests"),),
        required_outputs=(RequiredOutput(value="command evidence"),),
        commands=selected_commands,
        evidence_obligations=(_evidence_obligation(),),
        fallback_policy_ref=FallbackPolicyRef(value="fallback-policy.default"),
        audit_requirements=(AuditRequirement(value="record command run"),),
    )


def _runner_input(
    *,
    execution_package: ExecutionPackage | None = None,
    package_contract: PackageContract | None = None,
    command_id: ContractId | None = None,
    package_root: Path,
) -> CommandRunnerInput:
    return CommandRunnerInput(
        execution_package=execution_package or _execution_package(),
        package_contract=package_contract or _package_contract(),
        command_id=command_id or ContractId(value="command.test"),
        package_root=package_root,
        runner_ref=RunnerRef(value="runner.local-subprocess"),
        environment_profile_ref=EnvironmentProfileRef(value="environment.local-python"),
        workspace_snapshot_ref=WorkspaceSnapshotRef(value="workspace-snapshot.test"),
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


class MalformedProcessResultExecutor:
    def __init__(self, process_result: ProcessResult) -> None:
        self._process_result = process_result

    def run(self, *, command: tuple[str, ...], cwd: Path) -> ProcessResult:
        return self._process_result


class RaisingProcessExecutor:
    def run(self, *, command: tuple[str, ...], cwd: Path) -> ProcessResult:
        raise OSError("platform-specific failure")


class RaisingCommandRunnerErrorExecutor:
    def run(self, *, command: tuple[str, ...], cwd: Path) -> ProcessResult:
        raise CommandRunnerError("unstable detail")


class SequenceClock:
    def __init__(self, *timestamps: datetime) -> None:
        self._timestamps = list(timestamps)

    def now(self) -> datetime:
        return self._timestamps.pop(0)


def test_command_runner_rejects_command_not_in_package_contract(tmp_path: Path) -> None:
    with pytest.raises(CommandRunnerError, match="package contract"):
        CommandRunner().run(
            _runner_input(
                execution_package=_execution_package(_python_command("command.only-execution")),
                package_contract=_package_contract(_python_command("command.other")),
                command_id=ContractId(value="command.only-execution"),
                package_root=tmp_path,
            )
        )


def test_command_runner_rejects_command_not_in_execution_package(tmp_path: Path) -> None:
    with pytest.raises(CommandRunnerError, match="execution package"):
        CommandRunner().run(
            _runner_input(
                execution_package=_execution_package(_python_command("command.other")),
                package_contract=_package_contract(_python_command("command.only-contract")),
                command_id=ContractId(value="command.only-contract"),
                package_root=tmp_path,
            )
        )


@pytest.mark.parametrize(
    "contract_command",
    [
        _python_command(label="Different label"),
        _different_output_python_command(),
        _python_command(cwd="tests"),
    ],
    ids=["label", "command", "cwd"],
)
def test_command_runner_rejects_command_contract_mismatch(
    tmp_path: Path,
    contract_command: PackageCommand,
) -> None:
    with pytest.raises(CommandRunnerError, match="PackageCommand"):
        CommandRunner().run(
            _runner_input(
                execution_package=_execution_package(_python_command()),
                package_contract=_package_contract(contract_command),
                package_root=tmp_path,
            )
        )


@pytest.mark.parametrize(
    "cwd",
    [
        pytest.param("..", id="outside-root"),
        pytest.param("tests/..", id="parent-traversal"),
    ],
)
def test_command_runner_rejects_cwd_outside_package_root(
    tmp_path: Path,
    cwd: str,
) -> None:
    escape_command = _python_command(cwd=cwd)

    with pytest.raises(CommandRunnerError, match="package root|cwd"):
        CommandRunner().run(
            _runner_input(
                execution_package=_execution_package(escape_command),
                package_contract=_package_contract(escape_command),
                package_root=tmp_path,
            )
        )


def test_command_runner_rejects_absolute_declared_cwd(tmp_path: Path) -> None:
    absolute_command = _python_command(cwd=str(tmp_path))

    with pytest.raises(CommandRunnerError, match="package root|cwd"):
        CommandRunner().run(
            _runner_input(
                execution_package=_execution_package(absolute_command),
                package_contract=_package_contract(absolute_command),
                package_root=tmp_path,
            )
        )


@pytest.mark.parametrize(
    ("process_result", "missing_field"),
    [
        (ProcessResult.model_construct(stdout="", stderr=""), "exit_code"),
        (ProcessResult.model_construct(exit_code=0, stderr=""), "stdout"),
        (ProcessResult.model_construct(exit_code=0, stdout=""), "stderr"),
    ],
)
def test_command_runner_rejects_process_result_missing_required_field(
    tmp_path: Path,
    process_result: ProcessResult,
    missing_field: str,
) -> None:
    with pytest.raises(CommandRunnerError, match=missing_field):
        CommandRunner(process_executor=MalformedProcessResultExecutor(process_result)).run(
            _runner_input(package_root=tmp_path)
        )


@pytest.mark.parametrize(
    ("process_result", "invalid_field"),
    [
        (ProcessResult.model_construct(exit_code=None, stdout="", stderr=""), "exit_code"),
        (ProcessResult.model_construct(exit_code="0", stdout="", stderr=""), "exit_code"),
        (ProcessResult.model_construct(exit_code=True, stdout="", stderr=""), "exit_code"),
        (ProcessResult.model_construct(exit_code=False, stdout="", stderr=""), "exit_code"),
        (ProcessResult.model_construct(exit_code=0, stdout=None, stderr=""), "stdout"),
        (ProcessResult.model_construct(exit_code=0, stdout="", stderr=None), "stderr"),
    ],
)
def test_command_runner_rejects_process_result_invalid_field_type(
    tmp_path: Path,
    process_result: ProcessResult,
    invalid_field: str,
) -> None:
    with pytest.raises(CommandRunnerError, match=invalid_field):
        CommandRunner(process_executor=MalformedProcessResultExecutor(process_result)).run(
            _runner_input(package_root=tmp_path)
        )


@pytest.mark.parametrize(
    "process_executor",
    [
        RaisingProcessExecutor(),
        RaisingCommandRunnerErrorExecutor(),
    ],
)
def test_command_runner_normalizes_process_executor_error(
    tmp_path: Path,
    process_executor: object,
) -> None:
    with pytest.raises(CommandRunnerError, match="failed to execute declared command"):
        CommandRunner(process_executor=process_executor).run(
            _runner_input(package_root=tmp_path)
        )


def test_command_runner_rejects_naive_clock_timestamp(tmp_path: Path) -> None:
    naive_clock = SequenceClock(
        datetime(2026, 5, 18, 9, 0),
        datetime(2026, 5, 18, 9, 0, 1),
    )

    with pytest.raises(CommandRunnerError, match="timezone-aware"):
        CommandRunner(clock=naive_clock).run(_runner_input(package_root=tmp_path))


def test_command_runner_rejects_clock_rollback(tmp_path: Path) -> None:
    rollback_clock = SequenceClock(_finished_at(), _started_at())

    with pytest.raises(CommandRunnerError, match="finished_at"):
        CommandRunner(clock=rollback_clock).run(_runner_input(package_root=tmp_path))


def test_command_runner_records_successful_declared_command(tmp_path: Path) -> None:
    process_executor = CapturingProcessExecutor(
        ProcessResult(exit_code=0, stdout="ok\n", stderr="")
    )
    clock = SequenceClock(_started_at(), _finished_at())

    result = CommandRunner(process_executor=process_executor, clock=clock).run(
        _runner_input(package_root=tmp_path)
    )

    assert process_executor.commands == [_python_command().command]
    assert process_executor.cwd_values == [tmp_path.resolve()]
    assert result.stdout == "ok\n"
    assert result.stderr == ""
    assert result.verification_run.verification_run_id == VerificationRunRef(
        value="verification-run.execution-package.command.command.test"
    )
    assert result.verification_run.execution_package_ref == ExecutionPackageRef(
        value="execution-package.command"
    )
    assert result.verification_run.ticket_ref == TicketId(value="ticket.command")
    assert result.verification_run.command_id == ContractId(value="command.test")
    assert result.verification_run.command == _python_command().command
    assert result.verification_run.cwd == "."
    assert result.verification_run.exit_code == 0
    assert result.verification_run.status is VerificationRunStatus.PASSED
    assert result.verification_run.stdout_ref == CommandOutputRef(
        value="command-output.verification-run.execution-package.command.command.test.stdout"
    )
    assert result.verification_run.stderr_ref == CommandOutputRef(
        value="command-output.verification-run.execution-package.command.command.test.stderr"
    )
    assert result.verification_run.duration_ms == 1000
    assert result.verification_run.started_at == _started_at()
    assert result.verification_run.finished_at == _finished_at()
    assert result.verification_run.runner_ref == RunnerRef(value="runner.local-subprocess")
    assert result.verification_run.environment_profile_ref == EnvironmentProfileRef(
        value="environment.local-python"
    )
    assert result.verification_run.workspace_snapshot_ref == WorkspaceSnapshotRef(
        value="workspace-snapshot.test"
    )


def test_command_runner_records_failed_declared_command(tmp_path: Path) -> None:
    process_executor = CapturingProcessExecutor(
        ProcessResult(exit_code=2, stdout=b"", stderr=b"failed\n")
    )
    clock = SequenceClock(_started_at(), _finished_at())

    result = CommandRunner(process_executor=process_executor, clock=clock).run(
        _runner_input(package_root=tmp_path)
    )

    assert result.stdout == ""
    assert result.stderr == "failed\n"
    assert result.verification_run.exit_code == 2
    assert result.verification_run.status is VerificationRunStatus.FAILED
    assert result.verification_run.duration_ms == 1000


def test_command_runner_rejects_non_utf8_process_output(tmp_path: Path) -> None:
    process_executor = CapturingProcessExecutor(
        ProcessResult(exit_code=0, stdout=b"\xff", stderr=b"")
    )

    with pytest.raises(CommandRunnerError, match="utf-8"):
        CommandRunner(process_executor=process_executor).run(
            _runner_input(package_root=tmp_path)
        )


def test_subprocess_executor_rejects_non_utf8_process_output(tmp_path: Path) -> None:
    command = PackageCommand(
        command_id=ContractId(value="command.test"),
        label="Emit non UTF-8 bytes",
        command=(sys.executable, "-c", "import sys; sys.stdout.buffer.write(b'\\xff')"),
        cwd=".",
    )

    with pytest.raises(CommandRunnerError, match="utf-8"):
        CommandRunner().run(
            _runner_input(
                execution_package=_execution_package(command),
                package_contract=_package_contract(command),
                package_root=tmp_path,
            )
        )
