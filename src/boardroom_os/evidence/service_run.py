from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, StrictInt, field_validator, model_validator

from boardroom_os.agents.skills import _normalize_ref_fields
from boardroom_os.contracts.hashes import Sha256Hex
from boardroom_os.contracts.types import ContractId, NonEmptyTextValue
from boardroom_os.execution.package import ExecutionPackageRef
from boardroom_os.execution.verification_run import (
    CommandOutputRef,
    EnvironmentProfileRef,
    RunnerRef,
    WorkspaceSnapshotRef,
)
from boardroom_os.graph.ticket import TicketId


class ServiceRunEvidenceRef(NonEmptyTextValue):
    pass


class ServiceReadinessUrl(NonEmptyTextValue):
    @field_validator("value")
    @classmethod
    def _require_http_url(cls, value: str) -> str:
        normalized = super()._reject_empty_value(value)
        if not normalized.startswith(("http://", "https://")):
            raise ValueError("readiness_url must be an HTTP URL")
        return normalized


class ServiceProbeResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    readiness_url: ServiceReadinessUrl
    status_code: StrictInt
    body_sha256: Sha256Hex
    probed_at: datetime

    @model_validator(mode="before")
    @classmethod
    def _normalize_refs(cls, data: Any) -> Any:
        return _normalize_ref_fields(
            data,
            {
                "readiness_url": ServiceReadinessUrl,
                "body_sha256": Sha256Hex,
            },
        )

    @field_validator("status_code")
    @classmethod
    def _require_2xx_status(cls, value: int) -> int:
        if value < 200 or value >= 300:
            raise ValueError("readiness probe status_code must be 2xx")
        return value

    @field_validator("probed_at")
    @classmethod
    def _require_timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("probed_at must be timezone-aware")
        return value


class ServiceRunEvidence(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    version: Literal[1] = 1
    service_run_evidence_id: ServiceRunEvidenceRef
    execution_package_ref: ExecutionPackageRef
    ticket_ref: TicketId
    command_id: ContractId
    command: tuple[str, ...]
    cwd: str
    process_id: StrictInt
    readiness_url: ServiceReadinessUrl
    probe_status_code: StrictInt
    probe_body_sha256: Sha256Hex
    stdout_ref: CommandOutputRef
    stderr_ref: CommandOutputRef
    started_at: datetime
    ready_at: datetime
    stopped_at: datetime | None = None
    runner_ref: RunnerRef
    environment_profile_ref: EnvironmentProfileRef
    workspace_snapshot_ref: WorkspaceSnapshotRef

    @model_validator(mode="before")
    @classmethod
    def _normalize_refs(cls, data: Any) -> Any:
        return _normalize_ref_fields(
            data,
            {
                "service_run_evidence_id": ServiceRunEvidenceRef,
                "execution_package_ref": ExecutionPackageRef,
                "ticket_ref": TicketId,
                "command_id": ContractId,
                "readiness_url": ServiceReadinessUrl,
                "probe_body_sha256": Sha256Hex,
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

    @field_validator("process_id")
    @classmethod
    def _require_positive_process_id(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("process_id must be positive")
        return value

    @field_validator("probe_status_code")
    @classmethod
    def _require_successful_probe(cls, value: int) -> int:
        if value < 200 or value >= 300:
            raise ValueError("readiness probe status must be 2xx")
        return value

    @field_validator("started_at", "ready_at", "stopped_at")
    @classmethod
    def _require_timezone_aware_datetime(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("datetime fields must be timezone-aware")
        return value

    @model_validator(mode="after")
    def _validate_service_window(self) -> Self:
        if self.ready_at < self.started_at:
            raise ValueError("ready_at must not be earlier than started_at")
        if self.stopped_at is not None and self.stopped_at <= self.ready_at:
            raise ValueError("stopped_at must be later than ready_at")
        return self


def stdout_ref_for_service_run(service_run_evidence_id: ServiceRunEvidenceRef) -> CommandOutputRef:
    return CommandOutputRef(value=f"command-output.{service_run_evidence_id.value}.stdout")


def stderr_ref_for_service_run(service_run_evidence_id: ServiceRunEvidenceRef) -> CommandOutputRef:
    return CommandOutputRef(value=f"command-output.{service_run_evidence_id.value}.stderr")


__all__ = [
    "ServiceProbeResult",
    "ServiceReadinessUrl",
    "ServiceRunEvidence",
    "ServiceRunEvidenceRef",
    "stderr_ref_for_service_run",
    "stdout_ref_for_service_run",
]
