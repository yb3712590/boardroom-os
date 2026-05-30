from __future__ import annotations

import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, StrictInt, field_validator

from boardroom_os.contracts.package import PackageCommand, PackageContract
from boardroom_os.contracts.types import ContractId
from boardroom_os.execution.package import ExecutionPackage, ExecutionPackageRef
from boardroom_os.execution.verification_run import (
    EnvironmentProfileRef,
    RunnerRef,
    VerificationRun,
    VerificationRunRef,
    WorkspaceSnapshotRef,
    status_from_exit_code,
    stderr_ref_for,
    stdout_ref_for,
)


class CommandRunnerError(ValueError):
    pass


class ProcessResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    exit_code: StrictInt
    stdout: str | bytes
    stderr: str | bytes


class ProcessExecutor(Protocol):
    def run(self, *, command: tuple[str, ...], cwd: Path) -> ProcessResult: ...


class SubprocessExecutor:
    def run(self, *, command: tuple[str, ...], cwd: Path) -> ProcessResult:
        try:
            completed_process = subprocess.run(
                command,
                cwd=cwd,
                capture_output=True,
                check=False,
            )
        except OSError as error:
            raise CommandRunnerError("failed to execute declared command") from error
        return ProcessResult(
            exit_code=completed_process.returncode,
            stdout=completed_process.stdout,
            stderr=completed_process.stderr,
        )


class Clock(Protocol):
    def now(self) -> datetime: ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


class CommandRunnerInput(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    execution_package: ExecutionPackage
    package_contract: PackageContract
    command_id: ContractId
    package_root: Path
    runner_ref: RunnerRef
    environment_profile_ref: EnvironmentProfileRef
    workspace_snapshot_ref: WorkspaceSnapshotRef

    @field_validator("execution_package", mode="wrap")
    @classmethod
    def _require_execution_package_instance(
        cls,
        value: Any,
        handler: Any,
    ) -> ExecutionPackage:
        if not isinstance(value, ExecutionPackage):
            raise ValueError("execution_package must be an ExecutionPackage")
        return value

    @field_validator("package_contract", mode="wrap")
    @classmethod
    def _require_package_contract_instance(
        cls,
        value: Any,
        handler: Any,
    ) -> PackageContract:
        if not isinstance(value, PackageContract):
            raise ValueError("package_contract must be a PackageContract")
        return value


class CommandRunnerResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    verification_run: VerificationRun
    stdout: str
    stderr: str


class CommandRunner:
    def __init__(
        self,
        *,
        process_executor: ProcessExecutor | None = None,
        clock: Clock | None = None,
    ) -> None:
        self._process_executor = process_executor or SubprocessExecutor()
        self._clock = clock or SystemClock()

    def run(self, runner_input: CommandRunnerInput) -> CommandRunnerResult:
        execution_package_command = self._resolve_execution_package_command(runner_input)
        contract_command = self._resolve_package_contract_command(runner_input)
        self._validate_package_command_match(
            execution_package_command=execution_package_command,
            contract_command=contract_command,
        )
        resolved_cwd = self._resolve_cwd(
            package_root=runner_input.package_root,
            declared_cwd=execution_package_command.cwd,
        )

        started_at = self._require_timezone_aware(self._clock.now())
        try:
            process_result = self._process_executor.run(
                command=execution_package_command.command,
                cwd=resolved_cwd,
            )
        except Exception as error:
            raise CommandRunnerError("failed to execute declared command") from error
        finished_at = self._require_timezone_aware(self._clock.now())
        if finished_at < started_at:
            raise CommandRunnerError("clock finished_at must not be earlier than started_at")

        exit_code = self._require_exit_code(process_result)
        stdout_text = self._require_output(process_result, "stdout")
        stderr_text = self._require_output(process_result, "stderr")

        verification_run_id = VerificationRunRef(
            value=(
                "verification-run."
                f"{runner_input.execution_package.execution_package_id.value}."
                f"{runner_input.command_id.value}"
            )
        )
        verification_run = VerificationRun(
            verification_run_id=verification_run_id,
            execution_package_ref=ExecutionPackageRef(
                value=runner_input.execution_package.execution_package_id.value
            ),
            ticket_ref=runner_input.execution_package.ticket_ref,
            command_id=execution_package_command.command_id,
            command=execution_package_command.command,
            cwd=execution_package_command.cwd,
            exit_code=exit_code,
            status=status_from_exit_code(exit_code),
            stdout_ref=stdout_ref_for(verification_run_id),
            stderr_ref=stderr_ref_for(verification_run_id),
            duration_ms=max(0, int((finished_at - started_at).total_seconds() * 1000)),
            started_at=started_at,
            finished_at=finished_at,
            runner_ref=runner_input.runner_ref,
            environment_profile_ref=runner_input.environment_profile_ref,
            workspace_snapshot_ref=runner_input.workspace_snapshot_ref,
        )
        return CommandRunnerResult(
            verification_run=verification_run,
            stdout=stdout_text,
            stderr=stderr_text,
        )

    def _resolve_execution_package_command(
        self,
        runner_input: CommandRunnerInput,
    ) -> PackageCommand:
        matches = tuple(
            command
            for command in runner_input.execution_package.commands
            if command.command_id == runner_input.command_id
        )
        if len(matches) != 1:
            raise CommandRunnerError(
                "expected exactly one command in execution package for command_id: "
                f"{runner_input.command_id.value}"
            )
        return matches[0]

    def _resolve_package_contract_command(
        self,
        runner_input: CommandRunnerInput,
    ) -> PackageCommand:
        matches = tuple(
            command
            for command in (
                *runner_input.package_contract.run_commands,
                *runner_input.package_contract.test_commands,
            )
            if command.command_id == runner_input.command_id
        )
        if len(matches) != 1:
            raise CommandRunnerError(
                "expected exactly one command in package contract for command_id: "
                f"{runner_input.command_id.value}"
            )
        return matches[0]

    def _validate_package_command_match(
        self,
        *,
        execution_package_command: PackageCommand,
        contract_command: PackageCommand,
    ) -> None:
        if execution_package_command != contract_command:
            raise CommandRunnerError(
                "execution package PackageCommand must equal package contract PackageCommand"
            )

    def _resolve_cwd(self, *, package_root: Path, declared_cwd: str) -> Path:
        declared_path = Path(declared_cwd)
        if declared_path.is_absolute() or ".." in declared_path.parts:
            raise CommandRunnerError("declared cwd must stay within package root")
        resolved_root = package_root.resolve()
        resolved_cwd = (resolved_root / declared_path).resolve()
        if resolved_cwd != resolved_root and resolved_root not in resolved_cwd.parents:
            raise CommandRunnerError("resolved cwd must stay within package root")
        return resolved_cwd

    def _require_timezone_aware(self, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise CommandRunnerError("clock.now() must return timezone-aware datetime")
        return value

    def _require_process_result_field(
        self,
        process_result: ProcessResult,
        field_name: str,
    ) -> int | str | bytes:
        if not hasattr(process_result, field_name):
            raise CommandRunnerError(
                f"process result missing required field: {field_name}"
            )
        return getattr(process_result, field_name)

    def _require_exit_code(self, process_result: ProcessResult) -> int:
        value = self._require_process_result_field(process_result, "exit_code")
        if type(value) is not int:
            raise CommandRunnerError("process result invalid field type: exit_code")
        return value

    def _require_output(self, process_result: ProcessResult, field_name: str) -> str:
        value = self._require_process_result_field(process_result, field_name)
        if not isinstance(value, str | bytes):
            raise CommandRunnerError(f"process result invalid field type: {field_name}")
        return self._decode_output(value)

    def _decode_output(self, value: str | bytes) -> str:
        if isinstance(value, bytes):
            try:
                return value.decode("utf-8", errors="strict")
            except UnicodeDecodeError as error:
                raise CommandRunnerError("process output must be valid utf-8") from error
        return value


__all__ = [
    "Clock",
    "CommandRunner",
    "CommandRunnerError",
    "CommandRunnerInput",
    "CommandRunnerResult",
    "ProcessExecutor",
    "ProcessResult",
    "SubprocessExecutor",
    "SystemClock",
]
