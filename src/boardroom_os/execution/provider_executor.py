from __future__ import annotations

import json
from enum import Enum
from typing import Any, Mapping

from pydantic import BaseModel, ConfigDict, field_validator

from boardroom_os.execution.context_index import AgentContextSnapshot, build_agent_context_snapshot
from boardroom_os.execution.package import ExecutionPackage
from boardroom_os.providers.adapter import ProviderRequest
from boardroom_os.providers.attempt import ProviderAttempt


class ProviderExecutorError(ValueError):
    pass


# 只渲染 agent 需阅读的任务内容；provenance 和模型配置由 ProviderRequest 字段承载。
_PROMPT_FIELDS = (
    "objective",
    "context_refs",
    "constraints",
    "acceptance_refs",
    "source_surface_refs",
    "allowed_read_refs",
    "allowed_write_set",
    "required_outputs",
    "commands",
    "evidence_obligations",
    "fallback_policy_ref",
    "audit_requirements",
)


class ProviderExecutorInput(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    execution_package: ExecutionPackage
    provider_adapter: Any

    @field_validator("provider_adapter")
    @classmethod
    def _reject_missing_provider_adapter(cls, value: Any) -> Any:
        if not callable(getattr(value, "invoke", None)):
            raise ValueError("provider_adapter must expose callable invoke")
        return value


class ProviderExecutorResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    context_snapshot: AgentContextSnapshot
    prompt: str
    provider_attempt: ProviderAttempt


class ProviderExecutor:
    def execute(self, provider_input: ProviderExecutorInput) -> ProviderExecutorResult:
        context_snapshot = build_agent_context_snapshot(provider_input.execution_package)
        prompt = render_prompt_from_snapshot(context_snapshot)
        request = ProviderRequest(
            execution_package_ref=context_snapshot.execution_package_ref,
            seat_ref=context_snapshot.seat_ref,
            model_execution_profile=context_snapshot.model_execution_profile,
            prompt=prompt,
        )
        provider_attempt = provider_input.provider_adapter.invoke(request)
        self._validate_attempt_binding(provider_attempt, context_snapshot)
        return ProviderExecutorResult(
            context_snapshot=context_snapshot,
            prompt=prompt,
            provider_attempt=provider_attempt,
        )

    def _validate_attempt_binding(
        self,
        provider_attempt: ProviderAttempt,
        context_snapshot: AgentContextSnapshot,
    ) -> None:
        profile = context_snapshot.model_execution_profile
        mismatches: list[str] = []
        if provider_attempt.input_package_ref != context_snapshot.execution_package_ref:
            mismatches.append("input_package_ref")
        if provider_attempt.seat_ref != context_snapshot.seat_ref:
            mismatches.append("seat_ref")
        if provider_attempt.provider != profile.provider:
            mismatches.append("provider")
        if provider_attempt.model != profile.model:
            mismatches.append("model")
        if provider_attempt.reasoning_effort != profile.reasoning_effort:
            mismatches.append("reasoning_effort")
        if mismatches:
            joined_fields = ", ".join(mismatches)
            raise ProviderExecutorError(
                f"provider attempt binding mismatch: {joined_fields}"
            )


def _canonicalize_prompt_value(value: object) -> object:
    if isinstance(value, BaseModel):
        field_names = tuple(type(value).model_fields)
        if field_names == ("value",):
            return getattr(value, "value")
        return {
            field_name: _canonicalize_prompt_value(getattr(value, field_name))
            for field_name in field_names
        }
    if isinstance(value, tuple | list):
        return [_canonicalize_prompt_value(item) for item in value]
    if isinstance(value, Mapping):
        return {
            str(key): _canonicalize_prompt_value(item)
            for key, item in value.items()
        }
    if isinstance(value, Enum):
        return value.value
    return value


def render_prompt_from_snapshot(snapshot: AgentContextSnapshot) -> str:
    payload = {
        field_name: _canonicalize_prompt_value(getattr(snapshot, field_name))
        for field_name in _PROMPT_FIELDS
    }
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


__all__ = [
    "ProviderExecutor",
    "ProviderExecutorError",
    "ProviderExecutorInput",
    "ProviderExecutorResult",
    "render_prompt_from_snapshot",
]
