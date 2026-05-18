from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from boardroom_os.agents.skills import _normalize_ref_fields
from boardroom_os.contracts.types import ContractId, NonEmptyTextValue
from boardroom_os.execution.package import ExecutionPackageRef
from boardroom_os.graph.ticket import TicketId


class VerificationRunRef(NonEmptyTextValue):
    pass


class CommandOutputRef(NonEmptyTextValue):
    pass


class RunnerRef(NonEmptyTextValue):
    pass


class EnvironmentProfileRef(NonEmptyTextValue):
    pass


class WorkspaceSnapshotRef(NonEmptyTextValue):
    pass


class VerificationRunStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"


def status_from_exit_code(exit_code: int) -> VerificationRunStatus:
    if exit_code == 0:
        return VerificationRunStatus.PASSED
    return VerificationRunStatus.FAILED


def stdout_ref_for(verification_run_id: VerificationRunRef) -> CommandOutputRef:
    return CommandOutputRef(value=f"command-output.{verification_run_id.value}.stdout")


def stderr_ref_for(verification_run_id: VerificationRunRef) -> CommandOutputRef:
    return CommandOutputRef(value=f"command-output.{verification_run_id.value}.stderr")


class VerificationRun(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    version: Literal[1] = 1
    verification_run_id: VerificationRunRef
    execution_package_ref: ExecutionPackageRef
    ticket_ref: TicketId
    command_id: ContractId
    command: tuple[str, ...]
    cwd: str
    exit_code: int
    status: VerificationRunStatus
    stdout_ref: CommandOutputRef
    stderr_ref: CommandOutputRef
    duration_ms: int
    started_at: datetime
    finished_at: datetime
    runner_ref: RunnerRef
    environment_profile_ref: EnvironmentProfileRef
    workspace_snapshot_ref: WorkspaceSnapshotRef

    @model_validator(mode="before")
    @classmethod
    def _normalize_yaml_refs(cls, data: Any) -> Any:
        return _normalize_ref_fields(
            data,
            {
                "verification_run_id": VerificationRunRef,
                "execution_package_ref": ExecutionPackageRef,
                "ticket_ref": TicketId,
                "command_id": ContractId,
                "stdout_ref": CommandOutputRef,
                "stderr_ref": CommandOutputRef,
                "runner_ref": RunnerRef,
                "environment_profile_ref": EnvironmentProfileRef,
                "workspace_snapshot_ref": WorkspaceSnapshotRef,
            },
        )

    @field_validator("command")
    @classmethod
    def _reject_empty_command(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(value.strip() for value in values)
        if not normalized:
            raise ValueError("command must not be empty")
        if any(not value for value in normalized):
            raise ValueError("command must not contain empty items")
        return normalized

    @field_validator("cwd")
    @classmethod
    def _reject_empty_cwd(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("cwd must not be empty")
        return normalized

    @field_validator("duration_ms")
    @classmethod
    def _reject_negative_duration(cls, value: int) -> int:
        if value < 0:
            raise ValueError("duration_ms must be non-negative")
        return value

    @field_validator("started_at", "finished_at")
    @classmethod
    def _require_timezone_aware_datetime(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("datetime fields must be timezone-aware")
        return value

    @model_validator(mode="after")
    def _validate_verification_run(self) -> Self:
        if self.finished_at < self.started_at:
            raise ValueError("finished_at must not be earlier than started_at")
        time_window = self.finished_at - self.started_at
        window_us = (
            time_window.days * 24 * 60 * 60 * 1_000_000
            + time_window.seconds * 1_000_000
            + time_window.microseconds
        )
        if self.duration_ms * 1000 > window_us:
            raise ValueError("duration_ms must not exceed started_at/finished_at time window")
        if self.status is not status_from_exit_code(self.exit_code):
            raise ValueError("status must match exit_code")
        return self


__all__ = [
    "CommandOutputRef",
    "EnvironmentProfileRef",
    "RunnerRef",
    "VerificationRun",
    "VerificationRunRef",
    "VerificationRunStatus",
    "WorkspaceSnapshotRef",
    "status_from_exit_code",
    "stderr_ref_for",
    "stdout_ref_for",
]
