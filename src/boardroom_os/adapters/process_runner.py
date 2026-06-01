from __future__ import annotations

import hashlib
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

from pydantic import BaseModel, ConfigDict, StrictInt, field_validator, model_validator

from boardroom_os.contracts.package import PackageCommand, PackageContract
from boardroom_os.contracts.types import ContractId
from boardroom_os.evidence.service_run import (
    ServiceReadinessUrl,
    ServiceRunEvidence,
    ServiceRunEvidenceRef,
    stderr_ref_for_service_run,
    stdout_ref_for_service_run,
)
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


class ServiceProcessHandle(Protocol):
    @property
    def pid(self) -> int: ...

    def poll(self) -> int | None: ...

    def terminate(self) -> None: ...

    def kill(self) -> None: ...

    def communicate(self, timeout: float | None = None) -> tuple[str | bytes, str | bytes]: ...


class ServiceProcessExecutor(Protocol):
    def start(self, *, command: tuple[str, ...], cwd: Path) -> ServiceProcessHandle: ...


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


class SubprocessServiceExecutor:
    def start(self, *, command: tuple[str, ...], cwd: Path) -> ServiceProcessHandle:
        try:
            return subprocess.Popen(
                command,
                cwd=cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        except OSError as error:
            raise CommandRunnerError("failed to execute declared service command") from error


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
        execution_package_command = _resolve_execution_package_command(runner_input)
        contract_command = _resolve_package_contract_command(runner_input)
        _validate_package_command_match(
            execution_package_command=execution_package_command,
            contract_command=contract_command,
        )
        resolved_cwd = _resolve_cwd(
            package_root=runner_input.package_root,
            declared_cwd=execution_package_command.cwd,
        )

        started_at = _require_timezone_aware(self._clock.now())
        try:
            process_result = self._process_executor.run(
                command=execution_package_command.command,
                cwd=resolved_cwd,
            )
        except Exception as error:
            raise CommandRunnerError("failed to execute declared command") from error
        finished_at = _require_timezone_aware(self._clock.now())
        if finished_at < started_at:
            raise CommandRunnerError("clock finished_at must not be earlier than started_at")

        exit_code = _require_exit_code(process_result)
        stdout_text = _require_output(process_result, "stdout")
        stderr_text = _require_output(process_result, "stderr")

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
        return _resolve_execution_package_command(runner_input)

    def _resolve_package_contract_command(
        self,
        runner_input: CommandRunnerInput,
    ) -> PackageCommand:
        return _resolve_package_contract_command(runner_input)

    def _validate_package_command_match(
        self,
        *,
        execution_package_command: PackageCommand,
        contract_command: PackageCommand,
    ) -> None:
        _validate_package_command_match(
            execution_package_command=execution_package_command,
            contract_command=contract_command,
        )

    def _resolve_cwd(self, *, package_root: Path, declared_cwd: str) -> Path:
        return _resolve_cwd(package_root=package_root, declared_cwd=declared_cwd)

    def _require_timezone_aware(self, value: datetime) -> datetime:
        return _require_timezone_aware(value)

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
        return _require_exit_code(process_result)

    def _require_output(self, process_result: ProcessResult, field_name: str) -> str:
        return _require_output(process_result, field_name)

    def _decode_output(self, value: str | bytes) -> str:
        return _decode_output(value)


class ServiceRunnerInput(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    execution_package: ExecutionPackage
    package_contract: PackageContract
    command_id: ContractId
    package_root: Path
    readiness_url: ServiceReadinessUrl
    runner_ref: RunnerRef
    environment_profile_ref: EnvironmentProfileRef
    workspace_snapshot_ref: WorkspaceSnapshotRef
    timeout_seconds: float = 10.0
    poll_interval_seconds: float = 0.1

    @model_validator(mode="before")
    @classmethod
    def _normalize_readiness_url(cls, data: Any) -> Any:
        if isinstance(data, dict) and isinstance(data.get("readiness_url"), str):
            normalized = dict(data)
            normalized["readiness_url"] = ServiceReadinessUrl(
                value=normalized["readiness_url"]
            )
            return normalized
        return data

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

    @field_validator("timeout_seconds", "poll_interval_seconds")
    @classmethod
    def _require_positive_interval(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("timeout and poll intervals must be positive")
        return value


class ServiceRunnerResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    service_run_evidence: ServiceRunEvidence
    stdout: str
    stderr: str


class HttpReadinessProbe:
    def probe(self, readiness_url: ServiceReadinessUrl) -> tuple[int, bytes]:
        try:
            with urlopen(readiness_url.value, timeout=1) as response:
                return response.status, response.read()
        except HTTPError as error:
            return error.code, error.read()
        except URLError as error:
            raise CommandRunnerError("readiness probe failed") from error


class ServiceRunner:
    def __init__(
        self,
        *,
        service_executor: ServiceProcessExecutor | None = None,
        readiness_probe: HttpReadinessProbe | None = None,
        clock: Clock | None = None,
    ) -> None:
        self._service_executor = service_executor or SubprocessServiceExecutor()
        self._readiness_probe = readiness_probe or HttpReadinessProbe()
        self._clock = clock or SystemClock()

    def run(self, runner_input: ServiceRunnerInput) -> ServiceRunnerResult:
        execution_package_command = _resolve_execution_package_command(runner_input)
        contract_command = _resolve_package_contract_command(runner_input)
        _validate_package_command_match(
            execution_package_command=execution_package_command,
            contract_command=contract_command,
        )
        resolved_cwd = _resolve_cwd(
            package_root=runner_input.package_root,
            declared_cwd=execution_package_command.cwd,
        )
        started_at = _require_timezone_aware(self._clock.now())
        try:
            process = self._service_executor.start(
                command=execution_package_command.command,
                cwd=resolved_cwd,
            )
        except Exception as error:
            raise CommandRunnerError("failed to execute declared service command") from error

        ready_at: datetime | None = None
        probe_status: int | None = None
        probe_body: bytes | None = None
        deadline = time.monotonic() + runner_input.timeout_seconds
        try:
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    stdout_text, stderr_text = _communicate_service_process(process)
                    raise ServiceRunnerError(
                        "service process exited before readiness probe passed"
                    ) from _ServiceProcessOutputError(stdout_text, stderr_text)
                try:
                    probe_status, probe_body = self._readiness_probe.probe(
                        runner_input.readiness_url
                    )
                except CommandRunnerError:
                    time.sleep(runner_input.poll_interval_seconds)
                    continue
                if 200 <= probe_status < 300:
                    ready_at = _require_timezone_aware(self._clock.now())
                    break
                time.sleep(runner_input.poll_interval_seconds)
            if ready_at is None or probe_status is None or probe_body is None:
                raise ServiceRunnerError("service readiness probe failed before timeout")
        finally:
            stopped_at, stdout_text, stderr_text = self._stop_process(process)

        if stopped_at < started_at:
            raise ServiceRunnerError("clock stopped_at must not be earlier than started_at")
        service_run_evidence_id = ServiceRunEvidenceRef(
            value=(
                "service-run."
                f"{runner_input.execution_package.execution_package_id.value}."
                f"{runner_input.command_id.value}"
            )
        )
        service_run_evidence = ServiceRunEvidence(
            service_run_evidence_id=service_run_evidence_id,
            execution_package_ref=ExecutionPackageRef(
                value=runner_input.execution_package.execution_package_id.value
            ),
            ticket_ref=runner_input.execution_package.ticket_ref,
            command_id=execution_package_command.command_id,
            command=execution_package_command.command,
            cwd=execution_package_command.cwd,
            process_id=process.pid,
            readiness_url=runner_input.readiness_url,
            probe_status_code=probe_status,
            probe_body_sha256=hashlib.sha256(probe_body).hexdigest(),
            stdout_ref=stdout_ref_for_service_run(service_run_evidence_id),
            stderr_ref=stderr_ref_for_service_run(service_run_evidence_id),
            started_at=started_at,
            ready_at=ready_at,
            stopped_at=stopped_at,
            runner_ref=runner_input.runner_ref,
            environment_profile_ref=runner_input.environment_profile_ref,
            workspace_snapshot_ref=runner_input.workspace_snapshot_ref,
        )
        return ServiceRunnerResult(
            service_run_evidence=service_run_evidence,
            stdout=stdout_text,
            stderr=stderr_text,
        )

    def _stop_process(
        self,
        process: ServiceProcessHandle,
    ) -> tuple[datetime, str, str]:
        if process.poll() is None:
            process.terminate()
        try:
            stdout, stderr = process.communicate(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()
            stdout, stderr = process.communicate(timeout=2)
        stopped_at = _require_timezone_aware(self._clock.now())
        return stopped_at, _decode_output(stdout), _decode_output(stderr)


class _ServiceProcessOutputError(Exception):
    def __init__(self, stdout: str, stderr: str) -> None:
        super().__init__("service process output captured before readiness")
        self.stdout = stdout
        self.stderr = stderr


class ServiceRunnerError(CommandRunnerError):
    pass


def _resolve_execution_package_command(
    runner_input: CommandRunnerInput | ServiceRunnerInput,
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
    runner_input: CommandRunnerInput | ServiceRunnerInput,
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
    *,
    execution_package_command: PackageCommand,
    contract_command: PackageCommand,
) -> None:
    if execution_package_command != contract_command:
        raise CommandRunnerError(
            "execution package PackageCommand must equal package contract PackageCommand"
        )


def _resolve_cwd(*, package_root: Path, declared_cwd: str) -> Path:
    declared_path = Path(declared_cwd)
    if declared_path.is_absolute() or ".." in declared_path.parts:
        raise CommandRunnerError("declared cwd must stay within package root")
    resolved_root = package_root.resolve()
    resolved_cwd = (resolved_root / declared_path).resolve()
    if resolved_cwd != resolved_root and resolved_root not in resolved_cwd.parents:
        raise CommandRunnerError("resolved cwd must stay within package root")
    return resolved_cwd


def _require_timezone_aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise CommandRunnerError("clock.now() must return timezone-aware datetime")
    return value


def _require_process_result_field(
    process_result: ProcessResult,
    field_name: str,
) -> int | str | bytes:
    if not hasattr(process_result, field_name):
        raise CommandRunnerError(
            f"process result missing required field: {field_name}"
        )
    return getattr(process_result, field_name)


def _require_exit_code(process_result: ProcessResult) -> int:
    value = _require_process_result_field(process_result, "exit_code")
    if type(value) is not int:
        raise CommandRunnerError("process result invalid field type: exit_code")
    return value


def _require_output(process_result: ProcessResult, field_name: str) -> str:
    value = _require_process_result_field(process_result, field_name)
    if not isinstance(value, str | bytes):
        raise CommandRunnerError(f"process result invalid field type: {field_name}")
    return _decode_output(value)


def _decode_output(value: str | bytes) -> str:
    if isinstance(value, bytes):
        try:
            return value.decode("utf-8", errors="strict")
        except UnicodeDecodeError as error:
            raise CommandRunnerError("process output must be valid utf-8") from error
    return value


def _communicate_service_process(process: ServiceProcessHandle) -> tuple[str, str]:
    stdout, stderr = process.communicate(timeout=2)
    return _decode_output(stdout), _decode_output(stderr)


__all__ = [
    "Clock",
    "CommandRunner",
    "CommandRunnerError",
    "CommandRunnerInput",
    "CommandRunnerResult",
    "HttpReadinessProbe",
    "ProcessExecutor",
    "ProcessResult",
    "ServiceProcessExecutor",
    "ServiceProcessHandle",
    "ServiceRunner",
    "ServiceRunnerError",
    "ServiceRunnerInput",
    "ServiceRunnerResult",
    "SubprocessExecutor",
    "SubprocessServiceExecutor",
    "SystemClock",
]
