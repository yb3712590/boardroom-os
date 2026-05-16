from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, field_validator, model_validator


class _NonEmptyAgentValue(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    value: str

    @field_validator("value")
    @classmethod
    def _reject_empty_value(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("value must not be empty")
        return normalized


class _LayeredAgentValue(_NonEmptyAgentValue):
    @field_validator("value")
    @classmethod
    def _require_layered_value(cls, value: str) -> str:
        normalized = value.strip()
        parts = normalized.split(".")
        if len(parts) < 2 or any(not part for part in parts):
            raise ValueError("value must use layered dot notation")
        return normalized


class CapabilityTag(_LayeredAgentValue):
    pass


class SkillRef(_LayeredAgentValue):
    pass


class SkillFileRef(_LayeredAgentValue):
    pass


class PromptRef(_LayeredAgentValue):
    pass


class McpInterfaceRef(_LayeredAgentValue):
    pass


class TicketTypeRef(_LayeredAgentValue):
    pass


class RoleProfileId(_LayeredAgentValue):
    pass


class CapabilityDefinition(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    capability_tag: CapabilityTag
    description: str

    @model_validator(mode="before")
    @classmethod
    def _normalize_yaml_refs(cls, data: Any) -> Any:
        return _normalize_ref_fields(data, {"capability_tag": CapabilityTag})

    @field_validator("description")
    @classmethod
    def _reject_empty_description(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("description must not be empty")
        return normalized


class CapabilityRegistry(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    version: Literal[1] = 1
    capabilities: tuple[CapabilityDefinition, ...]

    @classmethod
    def from_definitions(cls, *capabilities: CapabilityDefinition) -> Self:
        return cls(capabilities=capabilities)

    @model_validator(mode="after")
    def _require_unique_capabilities(self) -> Self:
        if not self.capabilities:
            raise ValueError("capabilities must not be empty")
        seen: set[CapabilityTag] = set()
        for capability in self.capabilities:
            if capability.capability_tag in seen:
                raise ValueError("capability_tag values must be unique")
            seen.add(capability.capability_tag)
        return self

    def contains(self, capability_tag: CapabilityTag) -> bool:
        return any(
            capability.capability_tag == capability_tag
            for capability in self.capabilities
        )

    def require_all(self, capability_tags: tuple[CapabilityTag, ...]) -> None:
        for capability_tag in capability_tags:
            if not self.contains(capability_tag):
                raise ValueError(f"unknown capability_tag: {capability_tag.value}")


class PromptSource(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    prompt_ref: PromptRef
    prompt_path: str
    prompt_kind: str
    required_variables: tuple[str, ...]

    @model_validator(mode="before")
    @classmethod
    def _normalize_yaml_refs(cls, data: Any) -> Any:
        return _normalize_ref_fields(data, {"prompt_ref": PromptRef})

    @field_validator("prompt_path", "prompt_kind")
    @classmethod
    def _reject_empty_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("text fields must not be empty")
        return normalized

    @field_validator("required_variables")
    @classmethod
    def _reject_empty_required_variables(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _validate_non_empty_text_tuple(value, "required_variables")


class PromptSourceRegistry(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    version: Literal[1] = 1
    prompts: tuple[PromptSource, ...]

    @classmethod
    def from_sources(cls, *prompts: PromptSource) -> Self:
        return cls(prompts=prompts)

    @model_validator(mode="after")
    def _require_unique_prompts(self) -> Self:
        _require_non_empty_unique_refs(
            self.prompts,
            "prompts",
            lambda prompt: prompt.prompt_ref,
            "prompt_ref",
        )
        return self

    def contains(self, prompt_ref: PromptRef) -> bool:
        return any(prompt.prompt_ref == prompt_ref for prompt in self.prompts)

    def require_all(self, prompt_refs: tuple[PromptRef, ...]) -> None:
        for prompt_ref in prompt_refs:
            if not self.contains(prompt_ref):
                raise ValueError(f"unknown prompt_ref: {prompt_ref.value}")


class SkillFileSource(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    skill_file_ref: SkillFileRef
    skill_file_path: str
    skill_kind: str
    required_sections: tuple[str, ...]

    @model_validator(mode="before")
    @classmethod
    def _normalize_yaml_refs(cls, data: Any) -> Any:
        return _normalize_ref_fields(data, {"skill_file_ref": SkillFileRef})

    @field_validator("skill_file_path", "skill_kind")
    @classmethod
    def _reject_empty_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("text fields must not be empty")
        return normalized

    @field_validator("required_sections")
    @classmethod
    def _reject_empty_required_sections(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _validate_non_empty_text_tuple(value, "required_sections")


class SkillFileSourceRegistry(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    version: Literal[1] = 1
    skill_files: tuple[SkillFileSource, ...]

    @classmethod
    def from_sources(cls, *skill_files: SkillFileSource) -> Self:
        return cls(skill_files=skill_files)

    @model_validator(mode="after")
    def _require_unique_skill_files(self) -> Self:
        _require_non_empty_unique_refs(
            self.skill_files,
            "skill_files",
            lambda skill_file: skill_file.skill_file_ref,
            "skill_file_ref",
        )
        return self

    def contains(self, skill_file_ref: SkillFileRef) -> bool:
        return any(
            skill_file.skill_file_ref == skill_file_ref
            for skill_file in self.skill_files
        )

    def require(self, skill_file_ref: SkillFileRef) -> None:
        if not self.contains(skill_file_ref):
            raise ValueError(f"unknown skill_file_ref: {skill_file_ref.value}")


class McpInterfaceDefinition(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    mcp_interface_ref: McpInterfaceRef
    server_ref: str
    tool_name: str
    allowed_operations: tuple[str, ...]
    required_capability_tags: tuple[CapabilityTag, ...]

    @model_validator(mode="before")
    @classmethod
    def _normalize_yaml_refs(cls, data: Any) -> Any:
        return _normalize_ref_fields(
            data,
            {"mcp_interface_ref": McpInterfaceRef},
            {"required_capability_tags": CapabilityTag},
        )

    @field_validator("server_ref", "tool_name")
    @classmethod
    def _reject_empty_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("text fields must not be empty")
        return normalized

    @field_validator("allowed_operations")
    @classmethod
    def _reject_empty_allowed_operations(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _validate_non_empty_text_tuple(value, "allowed_operations")

    @field_validator("required_capability_tags")
    @classmethod
    def _reject_empty_required_capability_tags(
        cls, value: tuple[CapabilityTag, ...]
    ) -> tuple[CapabilityTag, ...]:
        if not value:
            raise ValueError("required_capability_tags must not be empty")
        return value


class McpInterfaceRegistry(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    version: Literal[1] = 1
    interfaces: tuple[McpInterfaceDefinition, ...]

    @classmethod
    def from_interfaces(
        cls,
        *interfaces: McpInterfaceDefinition,
        capability_registry: CapabilityRegistry,
    ) -> Self:
        capability_registry.require_all(
            tuple(
                capability_tag
                for interface in interfaces
                for capability_tag in interface.required_capability_tags
            )
        )
        return cls(interfaces=interfaces)

    @model_validator(mode="after")
    def _require_unique_interfaces(self) -> Self:
        _require_non_empty_unique_refs(
            self.interfaces,
            "interfaces",
            lambda interface: interface.mcp_interface_ref,
            "mcp_interface_ref",
        )
        return self

    def contains(self, mcp_interface_ref: McpInterfaceRef) -> bool:
        return any(
            interface.mcp_interface_ref == mcp_interface_ref
            for interface in self.interfaces
        )

    def get(self, mcp_interface_ref: McpInterfaceRef) -> McpInterfaceDefinition | None:
        return next(
            (
                interface
                for interface in self.interfaces
                if interface.mcp_interface_ref == mcp_interface_ref
            ),
            None,
        )

    def require_all(self, mcp_interface_refs: tuple[McpInterfaceRef, ...]) -> None:
        for mcp_interface_ref in mcp_interface_refs:
            if not self.contains(mcp_interface_ref):
                raise ValueError(f"unknown mcp_interface_ref: {mcp_interface_ref.value}")


class SkillBinding(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    version: Literal[1] = 1
    skill_ref: SkillRef
    purpose: str
    skill_file_ref: SkillFileRef
    allowed_roles: tuple[RoleProfileId, ...]
    required_for_ticket_types: tuple[TicketTypeRef, ...]
    capability_tags: tuple[CapabilityTag, ...]
    prompt_refs: tuple[PromptRef, ...]
    mcp_interface_refs: tuple[McpInterfaceRef, ...]
    input_requirements: tuple[str, ...]
    output_effects: tuple[str, ...]

    @model_validator(mode="before")
    @classmethod
    def _normalize_yaml_refs(cls, data: Any) -> Any:
        return _normalize_ref_fields(
            data,
            {
                "skill_ref": SkillRef,
                "skill_file_ref": SkillFileRef,
            },
            {
                "allowed_roles": RoleProfileId,
                "required_for_ticket_types": TicketTypeRef,
                "capability_tags": CapabilityTag,
                "prompt_refs": PromptRef,
                "mcp_interface_refs": McpInterfaceRef,
            },
        )

    @field_validator("purpose")
    @classmethod
    def _reject_empty_purpose(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("purpose must not be empty")
        return normalized

    @field_validator("allowed_roles")
    @classmethod
    def _reject_empty_allowed_roles(
        cls, value: tuple[RoleProfileId, ...]
    ) -> tuple[RoleProfileId, ...]:
        if not value:
            raise ValueError("allowed_roles must not be empty")
        return value

    @field_validator("required_for_ticket_types")
    @classmethod
    def _reject_empty_ticket_types(
        cls, value: tuple[TicketTypeRef, ...]
    ) -> tuple[TicketTypeRef, ...]:
        if not value:
            raise ValueError("required_for_ticket_types must not be empty")
        return value

    @field_validator("capability_tags")
    @classmethod
    def _reject_empty_capability_tags(
        cls, value: tuple[CapabilityTag, ...]
    ) -> tuple[CapabilityTag, ...]:
        if not value:
            raise ValueError("capability_tags must not be empty")
        return value

    @field_validator("prompt_refs")
    @classmethod
    def _reject_empty_prompt_refs(cls, value: tuple[PromptRef, ...]) -> tuple[PromptRef, ...]:
        if not value:
            raise ValueError("prompt_refs must not be empty")
        return value

    @field_validator("mcp_interface_refs")
    @classmethod
    def _reject_empty_mcp_refs(
        cls, value: tuple[McpInterfaceRef, ...]
    ) -> tuple[McpInterfaceRef, ...]:
        if not value:
            raise ValueError("mcp_interface_refs must not be empty")
        return value

    @field_validator("input_requirements", "output_effects")
    @classmethod
    def _reject_empty_text_tuples(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _validate_non_empty_text_tuple(value, "text tuple")

    def capability_tag_values(self) -> tuple[str, ...]:
        return tuple(capability_tag.value for capability_tag in self.capability_tags)


class SkillBindingRegistry(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    version: Literal[1] = 1
    bindings: tuple[SkillBinding, ...]

    @classmethod
    def from_bindings(
        cls,
        *bindings: SkillBinding,
        role_registry: Any,
        capability_registry: CapabilityRegistry,
        prompt_registry: PromptSourceRegistry,
        skill_file_registry: SkillFileSourceRegistry,
        mcp_interface_registry: McpInterfaceRegistry,
    ) -> Self:
        if not bindings:
            raise ValueError("bindings must not be empty")
        for binding in bindings:
            for role_ref in binding.allowed_roles:
                if not role_registry.contains(role_ref):
                    raise ValueError(f"unknown allowed role: {role_ref.value}")
            capability_registry.require_all(binding.capability_tags)
            skill_file_registry.require(binding.skill_file_ref)
            prompt_registry.require_all(binding.prompt_refs)
            mcp_interface_registry.require_all(binding.mcp_interface_refs)
            for mcp_interface_ref in binding.mcp_interface_refs:
                interface = mcp_interface_registry.get(mcp_interface_ref)
                if interface is None:
                    raise ValueError(f"unknown mcp_interface_ref: {mcp_interface_ref.value}")
                missing = tuple(
                    capability_tag.value
                    for capability_tag in interface.required_capability_tags
                    if capability_tag not in binding.capability_tags
                )
                if missing:
                    raise ValueError(
                        f"{binding.skill_ref.value} missing capability tags for "
                        f"{mcp_interface_ref.value}: {', '.join(missing)}"
                    )
        return cls(bindings=bindings)

    @model_validator(mode="after")
    def _require_unique_bindings(self) -> Self:
        _require_non_empty_unique_refs(
            self.bindings,
            "bindings",
            lambda binding: binding.skill_ref,
            "skill_ref",
        )
        return self

    def contains(self, skill_ref: SkillRef) -> bool:
        return any(binding.skill_ref == skill_ref for binding in self.bindings)


class _RefProtocol(BaseModel):
    value: str


def _normalize_ref_fields(
    data: Any,
    scalar_ref_fields: dict[str, Any],
    tuple_ref_fields: dict[str, Any] | None = None,
) -> Any:
    if not isinstance(data, dict):
        return data
    normalized = dict(data)
    for field_name, ref_type in scalar_ref_fields.items():
        if field_name in normalized:
            normalized[field_name] = _normalize_ref_value(normalized[field_name], ref_type)
    for field_name, ref_type in (tuple_ref_fields or {}).items():
        if field_name in normalized:
            normalized[field_name] = tuple(
                _normalize_ref_value(item, ref_type) for item in normalized[field_name]
            )
    return normalized


def _normalize_ref_value(value: Any, ref_type: Any) -> Any:
    if isinstance(value, ref_type):
        return value
    if isinstance(value, str):
        return ref_type(value=value)
    if isinstance(value, dict) and set(value) == {"value"}:
        return ref_type(value=value["value"])
    return value


def _validate_non_empty_text_tuple(values: tuple[str, ...], field_name: str) -> tuple[str, ...]:
    if not values:
        raise ValueError(f"{field_name} must not be empty")
    normalized_values: list[str] = []
    for value in values:
        normalized = value.strip()
        if not normalized:
            raise ValueError(f"{field_name} must not contain empty values")
        normalized_values.append(normalized)
    return tuple(normalized_values)


def _require_non_empty_unique_refs(
    values: tuple[Any, ...],
    field_name: str,
    ref_getter: Any,
    ref_name: str,
) -> None:
    if not values:
        raise ValueError(f"{field_name} must not be empty")
    seen: set[Any] = set()
    for value in values:
        ref = ref_getter(value)
        if ref in seen:
            raise ValueError(f"{ref_name} values must be unique")
        seen.add(ref)
