from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, StrictFloat, StrictInt, field_validator, model_validator

from boardroom_os.agents.skills import (
    CapabilityRegistry,
    CapabilityTag,
    RoleProfileId,
    _LayeredAgentValue,
    _normalize_ref_fields,
)
from boardroom_os.contracts.types import ContractId


class ModelExecutionProfileId(_LayeredAgentValue):
    pass


class RoleProfile(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    version: Literal[1] = 1
    role_profile_id: RoleProfileId
    role_name: str
    responsibilities: tuple[str, ...]
    capability_tags: tuple[CapabilityTag, ...]
    input_contracts: tuple[ContractId, ...]
    output_contracts: tuple[ContractId, ...]
    forbidden_actions: tuple[str, ...]

    @model_validator(mode="before")
    @classmethod
    def _normalize_yaml_refs(cls, data: Any) -> Any:
        return _normalize_ref_fields(
            data,
            {"role_profile_id": RoleProfileId},
            {
                "capability_tags": CapabilityTag,
                "input_contracts": ContractId,
                "output_contracts": ContractId,
            },
        )

    @field_validator("role_name")
    @classmethod
    def _reject_empty_role_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("role_name must not be empty")
        return normalized

    @field_validator("responsibilities", "forbidden_actions")
    @classmethod
    def _reject_empty_text_tuples(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if not values:
            raise ValueError("text tuples must not be empty")
        normalized_values: list[str] = []
        for value in values:
            normalized = value.strip()
            if not normalized:
                raise ValueError("text tuples must not contain empty values")
            normalized_values.append(normalized)
        return tuple(normalized_values)

    @field_validator("capability_tags")
    @classmethod
    def _reject_empty_capability_tags(
        cls, values: tuple[CapabilityTag, ...]
    ) -> tuple[CapabilityTag, ...]:
        if not values:
            raise ValueError("capability_tags must not be empty")
        return values

    @field_validator("input_contracts", "output_contracts")
    @classmethod
    def _reject_empty_contracts(cls, values: tuple[ContractId, ...]) -> tuple[ContractId, ...]:
        if not values:
            raise ValueError("contract refs must not be empty")
        return values

    def capability_tag_values(self) -> tuple[str, ...]:
        return tuple(capability_tag.value for capability_tag in self.capability_tags)


class RoleProfileRegistry(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    version: Literal[1] = 1
    profiles: tuple[RoleProfile, ...]

    @classmethod
    def from_profiles(
        cls,
        *profiles: RoleProfile,
        capability_registry: CapabilityRegistry,
    ) -> Self:
        if not profiles:
            raise ValueError("profiles must not be empty")
        for profile in profiles:
            capability_registry.require_all(profile.capability_tags)
        return cls(profiles=profiles)

    @model_validator(mode="after")
    def _require_unique_profiles(self) -> Self:
        seen: set[RoleProfileId] = set()
        for profile in self.profiles:
            if profile.role_profile_id in seen:
                raise ValueError("role_profile_id values must be unique")
            seen.add(profile.role_profile_id)
        return self

    def contains(self, role_profile_ref: RoleProfileId) -> bool:
        return any(
            profile.role_profile_id == role_profile_ref
            for profile in self.profiles
        )


class ModelExecutionProfile(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    version: Literal[1] = 1
    model_execution_profile_id: ModelExecutionProfileId
    provider: str
    model: str
    reasoning_effort: str
    context_window: StrictInt
    temperature: StrictFloat
    tool_permissions: tuple[str, ...]
    fallback_policy_ref: ContractId

    @model_validator(mode="before")
    @classmethod
    def _normalize_yaml_refs(cls, data: Any) -> Any:
        return _normalize_ref_fields(
            data,
            {
                "model_execution_profile_id": ModelExecutionProfileId,
                "fallback_policy_ref": ContractId,
            },
        )

    @field_validator("provider", "model", "reasoning_effort")
    @classmethod
    def _reject_empty_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("text fields must not be empty")
        return normalized

    @field_validator("context_window")
    @classmethod
    def _reject_non_positive_context_window(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("context_window must be positive")
        return value

    @field_validator("temperature")
    @classmethod
    def _reject_invalid_temperature(cls, value: float) -> float:
        if value < 0 or value > 2:
            raise ValueError("temperature must be between 0 and 2")
        return value

    @field_validator("tool_permissions")
    @classmethod
    def _reject_empty_tool_permissions(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if not values:
            raise ValueError("tool_permissions must not be empty")
        normalized_values: list[str] = []
        for value in values:
            normalized = value.strip()
            if not normalized:
                raise ValueError("tool_permissions must not contain empty values")
            normalized_values.append(normalized)
        return tuple(normalized_values)


class ModelExecutionProfileRegistry(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    version: Literal[1] = 1
    profiles: tuple[ModelExecutionProfile, ...]

    @classmethod
    def from_profiles(cls, *profiles: ModelExecutionProfile) -> Self:
        return cls(profiles=profiles)

    @model_validator(mode="after")
    def _require_unique_profiles(self) -> Self:
        if not self.profiles:
            raise ValueError("profiles must not be empty")
        seen: set[ModelExecutionProfileId] = set()
        for profile in self.profiles:
            if profile.model_execution_profile_id in seen:
                raise ValueError("model_execution_profile_id values must be unique")
            seen.add(profile.model_execution_profile_id)
        return self

    def contains(self, model_execution_profile_ref: ModelExecutionProfileId) -> bool:
        return any(
            profile.model_execution_profile_id == model_execution_profile_ref
            for profile in self.profiles
        )
