from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from boardroom_os.agents.role_prompt_hooks import (
    RolePromptHookRef,
    RolePromptHookSha256,
)
from boardroom_os.agents.seat import AgentSeatRef
from boardroom_os.agents.skills import _normalize_ref_fields
from boardroom_os.contracts.types import NonEmptyTextValue
from boardroom_os.execution.context_index import ProviderAttemptRef
from boardroom_os.execution.fallback import FallbackKind
from boardroom_os.execution.package import ExecutionPackageRef


class ProviderAttemptStatus(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class ProviderAttemptOutcome(StrEnum):
    PRIMARY_PROVIDER_OUTPUT = "primary_provider_output"
    FALLBACK_ARTIFACT = "fallback_artifact"


class ProviderArtifactRef(NonEmptyTextValue):
    pass


class ProviderAttempt(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    version: Literal[1] = 1
    provider_attempt_id: ProviderAttemptRef
    provider: str
    model: str
    reasoning_effort: str
    input_package_ref: ExecutionPackageRef
    seat_ref: AgentSeatRef
    role_prompt_hook_ref: RolePromptHookRef
    role_prompt_hook_version: str
    role_prompt_hook_sha256: RolePromptHookSha256
    status: ProviderAttemptStatus
    outcome: ProviderAttemptOutcome
    fallback_kind: FallbackKind | None = None
    started_at: datetime
    finished_at: datetime
    raw_output_ref: ProviderArtifactRef | None = None
    parsed_output_ref: ProviderArtifactRef | None = None
    failure_kind: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _normalize_yaml_refs(cls, data: Any) -> Any:
        return _normalize_ref_fields(
            data,
            {
                "provider_attempt_id": ProviderAttemptRef,
                "input_package_ref": ExecutionPackageRef,
                "seat_ref": AgentSeatRef,
                "role_prompt_hook_ref": RolePromptHookRef,
                "role_prompt_hook_sha256": RolePromptHookSha256,
                "raw_output_ref": ProviderArtifactRef,
                "parsed_output_ref": ProviderArtifactRef,
            },
        )

    @field_validator("provider", "model", "reasoning_effort", "role_prompt_hook_version")
    @classmethod
    def _reject_empty_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("text fields must not be empty")
        return normalized

    @field_validator("started_at", "finished_at")
    @classmethod
    def _require_timezone_aware_datetime(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("datetime fields must be timezone-aware")
        return value

    @field_validator("failure_kind")
    @classmethod
    def _normalize_failure_kind(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip()

    @model_validator(mode="after")
    def _validate_attempt(self) -> Self:
        if self.finished_at < self.started_at:
            raise ValueError("finished_at must not be earlier than started_at")
        if self.outcome is ProviderAttemptOutcome.FALLBACK_ARTIFACT:
            if self.fallback_kind is None:
                raise ValueError("fallback outcome requires fallback_kind")
        elif self.fallback_kind is not None:
            raise ValueError("primary provider output must not include fallback_kind")
        if self.status is ProviderAttemptStatus.SUCCEEDED:
            if self.raw_output_ref is None or self.parsed_output_ref is None:
                raise ValueError(
                    "succeeded attempts require raw_output_ref and parsed_output_ref"
                )
            if self.failure_kind is not None:
                raise ValueError("succeeded attempts must not include failure_kind")
            return self
        if not self.failure_kind:
            raise ValueError("failed attempts require a non-empty failure_kind")
        return self


__all__ = [
    "ProviderArtifactRef",
    "ProviderAttempt",
    "ProviderAttemptOutcome",
    "ProviderAttemptStatus",
]
