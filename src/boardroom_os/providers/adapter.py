from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Protocol, Self

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from boardroom_os.agents.profiles import ModelExecutionProfile
from boardroom_os.agents.role_prompt_hooks import (
    RolePromptHookRef,
    RolePromptHookSha256,
)
from boardroom_os.agents.seat import AgentSeatRef
from boardroom_os.agents.skills import _normalize_ref_fields
from boardroom_os.execution.package import ExecutionPackageRef
from boardroom_os.providers.attempt import (
    ProviderArtifactRef,
    ProviderAttempt,
    ProviderAttemptOutcome,
    ProviderAttemptStatus,
)


class ProviderRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    execution_package_ref: ExecutionPackageRef
    seat_ref: AgentSeatRef
    model_execution_profile: ModelExecutionProfile
    role_prompt_hook_ref: RolePromptHookRef
    role_prompt_hook_version: str
    role_prompt_hook_sha256: RolePromptHookSha256
    prompt: str

    @model_validator(mode="before")
    @classmethod
    def _normalize_yaml_refs(cls, data: Any) -> Any:
        return _normalize_ref_fields(
            data,
            {
                "execution_package_ref": ExecutionPackageRef,
                "seat_ref": AgentSeatRef,
                "role_prompt_hook_ref": RolePromptHookRef,
                "role_prompt_hook_sha256": RolePromptHookSha256,
            },
        )

    @field_validator("role_prompt_hook_version", "prompt")
    @classmethod
    def _reject_empty_prompt(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("prompt must not be empty")
        return normalized


class ProviderResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    raw_output_ref: ProviderArtifactRef
    parsed_output_ref: ProviderArtifactRef
    summary: str

    @model_validator(mode="before")
    @classmethod
    def _normalize_yaml_refs(cls, data: Any) -> Any:
        return _normalize_ref_fields(
            data,
            {
                "raw_output_ref": ProviderArtifactRef,
                "parsed_output_ref": ProviderArtifactRef,
            },
        )

    @field_validator("summary")
    @classmethod
    def _reject_empty_summary(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("summary must not be empty")
        return normalized


class ProviderAdapter(Protocol):
    def invoke(self, request: ProviderRequest) -> ProviderAttempt: ...


class FakeProviderTransport:
    def __init__(
        self,
        *,
        response: ProviderResponse,
        attempt_id: str = "provider-attempt.fake",
        started_at: datetime | None = None,
        finished_at: datetime | None = None,
    ) -> None:
        self._response = response
        self._attempt_id = attempt_id
        self._started_at = started_at
        self._finished_at = finished_at

    def invoke(self, request: ProviderRequest) -> ProviderAttempt:
        started_at = self._started_at or datetime.now(UTC)
        finished_at = self._finished_at or started_at
        profile = request.model_execution_profile
        return ProviderAttempt(
            provider_attempt_id=self._attempt_id,
            provider=profile.provider,
            model=profile.model,
            reasoning_effort=profile.reasoning_effort,
            input_package_ref=request.execution_package_ref,
            seat_ref=request.seat_ref,
            role_prompt_hook_ref=request.role_prompt_hook_ref,
            role_prompt_hook_version=request.role_prompt_hook_version,
            role_prompt_hook_sha256=request.role_prompt_hook_sha256,
            status=ProviderAttemptStatus.SUCCEEDED,
            outcome=ProviderAttemptOutcome.PRIMARY_PROVIDER_OUTPUT,
            started_at=started_at,
            finished_at=finished_at,
            raw_output_ref=self._response.raw_output_ref,
            parsed_output_ref=self._response.parsed_output_ref,
        )


__all__ = [
    "FakeProviderTransport",
    "ProviderAdapter",
    "ProviderRequest",
    "ProviderResponse",
]
