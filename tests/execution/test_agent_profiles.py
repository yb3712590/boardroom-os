import pytest
from pydantic import ValidationError

from boardroom_os.agents.profiles import (
    ModelExecutionProfile,
    ModelExecutionProfileId,
    ModelExecutionProfileRegistry,
    RoleProfile,
    RoleProfileId,
    RoleProfileRegistry,
)
from boardroom_os.agents.seat import RoleCategory
from boardroom_os.agents.skills import (
    CapabilityDefinition,
    CapabilityRegistry,
    CapabilityTag,
    McpInterfaceDefinition,
    McpInterfaceRef,
    McpInterfaceRegistry,
    PromptRef,
    PromptSource,
    PromptSourceRegistry,
    SkillBinding,
    SkillBindingRegistry,
    SkillFileRef,
    SkillFileSource,
    SkillFileSourceRegistry,
    SkillRef,
    TicketTypeRef,
)
from boardroom_os.contracts.types import ContractId


def _capability_registry() -> CapabilityRegistry:
    return CapabilityRegistry.from_definitions(
        CapabilityDefinition(
            capability_tag=CapabilityTag(value="role.worker"),
            description="Worker-side execution role.",
        ),
        CapabilityDefinition(
            capability_tag=CapabilityTag(value="task.implementation"),
            description="Implement assigned source changes.",
        ),
        CapabilityDefinition(
            capability_tag=CapabilityTag(value="surface.backend"),
            description="Operate on backend source surfaces.",
        ),
        CapabilityDefinition(
            capability_tag=CapabilityTag(value="quality.verification"),
            description="Inspect or verify delivery evidence.",
        ),
    )


def _worker_role(**overrides: object) -> RoleProfile:
    values = {
        "role_profile_id": RoleProfileId(value="role.worker.backend"),
        "role_category": RoleCategory.IMPLEMENTATION,
        "role_name": "Backend Worker",
        "responsibilities": (
            "Implement backend source changes inside allowed_write_set.",
            "Produce work products and evidence claims.",
        ),
        "capability_tags": (
            CapabilityTag(value="role.worker"),
            CapabilityTag(value="task.implementation"),
            CapabilityTag(value="surface.backend"),
        ),
        "input_contracts": (ContractId(value="contract.execution_package"),),
        "output_contracts": (
            ContractId(value="contract.work_product"),
            ContractId(value="contract.evidence_claim"),
        ),
        "forbidden_actions": (
            "modify acceptance contract",
            "write outside allowed_write_set",
            "mark ticket completed",
        ),
    }
    values.update(overrides)
    return RoleProfile(**values)


def _role_registry() -> RoleProfileRegistry:
    return RoleProfileRegistry.from_profiles(
        _worker_role(), capability_registry=_capability_registry()
    )


def _prompt_registry() -> PromptSourceRegistry:
    return PromptSourceRegistry.from_sources(
        PromptSource(
            prompt_ref=PromptRef(value="prompt.backend_implementation.system.v1"),
            prompt_path="00-boardroom/agents/prompts/backend-implementation-system.md",
            prompt_kind="system",
            required_variables=(
                "execution_package",
                "acceptance_refs",
                "allowed_write_set",
                "evidence_obligations",
            ),
        ),
        PromptSource(
            prompt_ref=PromptRef(value="prompt.evidence_claim.worker.v1"),
            prompt_path="00-boardroom/agents/prompts/evidence-claim-worker.md",
            prompt_kind="instruction",
            required_variables=("work_product", "evidence_obligations"),
        ),
    )


def _skill_file_registry() -> SkillFileSourceRegistry:
    return SkillFileSourceRegistry.from_sources(
        SkillFileSource(
            skill_file_ref=SkillFileRef(value="skill_doc.backend_implementation.v1"),
            skill_file_path="00-boardroom/agents/skill-files/backend-implementation/SKILL.md",
            skill_kind="claude_code_skill",
            required_sections=("purpose", "inputs", "outputs", "constraints"),
        )
    )


def _mcp_registry() -> McpInterfaceRegistry:
    return McpInterfaceRegistry.from_interfaces(
        McpInterfaceDefinition(
            mcp_interface_ref=McpInterfaceRef(value="mcp.filesystem.read_project"),
            server_ref="mcp.filesystem",
            tool_name="read_file",
            allowed_operations=("read",),
            required_capability_tags=(CapabilityTag(value="task.implementation"),),
        ),
        McpInterfaceDefinition(
            mcp_interface_ref=McpInterfaceRef(value="mcp.filesystem.edit_project"),
            server_ref="mcp.filesystem",
            tool_name="edit_file",
            allowed_operations=("read", "write"),
            required_capability_tags=(
                CapabilityTag(value="task.implementation"),
                CapabilityTag(value="surface.backend"),
            ),
        ),
        McpInterfaceDefinition(
            mcp_interface_ref=McpInterfaceRef(value="mcp.process.run_declared_tests"),
            server_ref="mcp.process",
            tool_name="run_command",
            allowed_operations=("execute",),
            required_capability_tags=(CapabilityTag(value="quality.verification"),),
        ),
        capability_registry=_capability_registry(),
    )


def _backend_skill(**overrides: object) -> SkillBinding:
    values = {
        "skill_ref": SkillRef(value="skill.backend.implementation"),
        "purpose": "Implement backend source changes for assigned implementation tickets.",
        "skill_file_ref": SkillFileRef(value="skill_doc.backend_implementation.v1"),
        "allowed_roles": (RoleProfileId(value="role.worker.backend"),),
        "required_for_ticket_types": (TicketTypeRef(value="ticket.implementation"),),
        "capability_tags": (
            CapabilityTag(value="task.implementation"),
            CapabilityTag(value="surface.backend"),
            CapabilityTag(value="quality.verification"),
        ),
        "prompt_refs": (
            PromptRef(value="prompt.backend_implementation.system.v1"),
            PromptRef(value="prompt.evidence_claim.worker.v1"),
        ),
        "mcp_interface_refs": (
            McpInterfaceRef(value="mcp.filesystem.read_project"),
            McpInterfaceRef(value="mcp.filesystem.edit_project"),
            McpInterfaceRef(value="mcp.process.run_declared_tests"),
        ),
        "input_requirements": (
            "execution package",
            "active acceptance contract refs",
            "allowed write set",
            "evidence obligations",
        ),
        "output_effects": ("work product", "evidence claim draft"),
    }
    values.update(overrides)
    return SkillBinding(**values)


def _skill_registry(*bindings: SkillBinding) -> SkillBindingRegistry:
    return SkillBindingRegistry.from_bindings(
        *(bindings or (_backend_skill(),)),
        role_registry=_role_registry(),
        capability_registry=_capability_registry(),
        prompt_registry=_prompt_registry(),
        skill_file_registry=_skill_file_registry(),
        mcp_interface_registry=_mcp_registry(),
    )


def test_role_profile_rejects_provider_fields() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        RoleProfile.model_validate(
            {
                "role_profile_id": {"value": "role.worker.backend"},
                "role_category": "implementation",
                "role_name": "Backend Worker",
                "responsibilities": ["Implement backend source changes."],
                "capability_tags": [{"value": "role.worker"}],
                "input_contracts": [{"value": "contract.execution_package"}],
                "output_contracts": [{"value": "contract.work_product"}],
                "forbidden_actions": ["mark ticket completed"],
                "provider": "anthropic",
            }
        )


def test_role_registry_rejects_unknown_capability_tag() -> None:
    role = _worker_role(
        capability_tags=(
            CapabilityTag(value="role.worker"),
            CapabilityTag(value="task.unknown"),
        )
    )

    with pytest.raises(ValueError, match="unknown capability_tag: task.unknown"):
        RoleProfileRegistry.from_profiles(role, capability_registry=_capability_registry())


def test_skill_registry_rejects_unknown_allowed_role() -> None:
    skill = _backend_skill(allowed_roles=(RoleProfileId(value="role.worker.missing"),))

    with pytest.raises(ValueError, match="unknown allowed role: role.worker.missing"):
        _skill_registry(skill)


def test_skill_registry_rejects_unknown_instruction_refs() -> None:
    skill = _backend_skill(
        skill_file_ref=SkillFileRef(value="skill_doc.missing.v1"),
        prompt_refs=(PromptRef(value="prompt.missing.system.v1"),),
        mcp_interface_refs=(McpInterfaceRef(value="mcp.missing.edit_project"),),
    )

    with pytest.raises(ValueError, match="unknown skill_file_ref: skill_doc.missing.v1"):
        _skill_registry(skill)


def test_skill_registry_rejects_unknown_capability_tag() -> None:
    skill = _backend_skill(capability_tags=(CapabilityTag(value="task.unknown"),))

    with pytest.raises(ValueError, match="unknown capability_tag: task.unknown"):
        _skill_registry(skill)


def test_skill_registry_rejects_mcp_interface_capability_gap() -> None:
    skill = _backend_skill(
        capability_tags=(CapabilityTag(value="task.implementation"),),
        mcp_interface_refs=(McpInterfaceRef(value="mcp.filesystem.edit_project"),),
    )

    with pytest.raises(
        ValueError,
        match="skill.backend.implementation missing capability tags for mcp.filesystem.edit_project: surface.backend",
    ):
        _skill_registry(skill)


def test_model_execution_profile_requires_provider_and_model() -> None:
    with pytest.raises(ValidationError):
        ModelExecutionProfile.model_validate(
            {
                "model_execution_profile_id": {"value": "model.worker.opus.high"},
                "model": "claude-opus-4-7",
                "reasoning_effort": "high",
                "context_window": 200000,
                "temperature": 0.2,
                "tool_permissions": ["filesystem.read"],
                "fallback_policy_ref": {"value": "fallback.provider_unavailable.record_failure"},
            }
        )

    with pytest.raises(ValidationError):
        ModelExecutionProfile.model_validate(
            {
                "model_execution_profile_id": {"value": "model.worker.opus.high"},
                "provider": "anthropic",
                "reasoning_effort": "high",
                "context_window": 200000,
                "temperature": 0.2,
                "tool_permissions": ["filesystem.read"],
                "fallback_policy_ref": {"value": "fallback.provider_unavailable.record_failure"},
            }
        )


def test_model_execution_profile_rejects_credentials() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        ModelExecutionProfile.model_validate(
            {
                "model_execution_profile_id": {"value": "model.worker.opus.high"},
                "provider": "anthropic",
                "model": "claude-opus-4-7",
                "reasoning_effort": "high",
                "context_window": 200000,
                "temperature": 0.2,
                "tool_permissions": ["filesystem.read"],
                "fallback_policy_ref": {"value": "fallback.provider_unavailable.record_failure"},
                "api_key": "must-not-enter-governance-config",
            }
        )


def test_yaml_shaped_agent_configs_compile_to_registries() -> None:
    capability_registry = CapabilityRegistry.model_validate(
        {
            "version": 1,
            "capabilities": [
                {
                    "capability_tag": "role.worker",
                    "description": "Worker-side execution role.",
                },
                {
                    "capability_tag": "task.implementation",
                    "description": "Implement assigned source changes.",
                },
                {
                    "capability_tag": "surface.backend",
                    "description": "Operate on backend source surfaces.",
                },
                {
                    "capability_tag": "quality.verification",
                    "description": "Inspect or verify delivery evidence.",
                },
            ],
        }
    )
    role = RoleProfile.model_validate(
        {
            "version": 1,
            "role_profile_id": "role.worker.backend",
            "role_category": "implementation",
            "role_name": "Backend Worker",
            "responsibilities": [
                "Implement backend source changes inside allowed_write_set.",
                "Produce work products and evidence claims.",
            ],
            "capability_tags": [
                "role.worker",
                "task.implementation",
                "surface.backend",
            ],
            "input_contracts": ["contract.execution_package"],
            "output_contracts": [
                "contract.work_product",
                "contract.evidence_claim",
            ],
            "forbidden_actions": [
                "modify acceptance contract",
                "write outside allowed_write_set",
                "mark ticket completed",
            ],
        }
    )
    role_registry = RoleProfileRegistry.from_profiles(
        role, capability_registry=capability_registry
    )
    prompt_registry = PromptSourceRegistry.model_validate(
        {
            "version": 1,
            "prompts": [
                {
                    "prompt_ref": "prompt.backend_implementation.system.v1",
                    "prompt_path": "00-boardroom/agents/prompts/backend-implementation-system.md",
                    "prompt_kind": "system",
                    "required_variables": [
                        "execution_package",
                        "acceptance_refs",
                        "allowed_write_set",
                        "evidence_obligations",
                    ],
                }
            ],
        }
    )
    skill_file_registry = SkillFileSourceRegistry.model_validate(
        {
            "version": 1,
            "skill_files": [
                {
                    "skill_file_ref": "skill_doc.backend_implementation.v1",
                    "skill_file_path": "00-boardroom/agents/skill-files/backend-implementation/SKILL.md",
                    "skill_kind": "claude_code_skill",
                    "required_sections": ["purpose", "inputs", "outputs", "constraints"],
                }
            ],
        }
    )
    mcp_registry = McpInterfaceRegistry.from_interfaces(
        *McpInterfaceRegistry.model_validate(
            {
                "version": 1,
                "interfaces": [
                    {
                        "mcp_interface_ref": "mcp.filesystem.edit_project",
                        "server_ref": "mcp.filesystem",
                        "tool_name": "edit_file",
                        "allowed_operations": ["read", "write"],
                        "required_capability_tags": [
                            "task.implementation",
                            "surface.backend",
                        ],
                    }
                ],
            }
        ).interfaces,
        capability_registry=capability_registry,
    )
    skill = SkillBinding.model_validate(
        {
            "version": 1,
            "skill_ref": "skill.backend.implementation",
            "purpose": "Implement backend source changes for assigned implementation tickets.",
            "skill_file_ref": "skill_doc.backend_implementation.v1",
            "allowed_roles": ["role.worker.backend"],
            "required_for_ticket_types": ["ticket.implementation"],
            "capability_tags": ["task.implementation", "surface.backend"],
            "prompt_refs": ["prompt.backend_implementation.system.v1"],
            "mcp_interface_refs": ["mcp.filesystem.edit_project"],
            "input_requirements": [
                "execution package",
                "active acceptance contract refs",
                "allowed write set",
                "evidence obligations",
            ],
            "output_effects": ["work product", "evidence claim draft"],
        }
    )
    model_profile = ModelExecutionProfile.model_validate(
        {
            "version": 1,
            "model_execution_profile_id": "model.worker.opus.high",
            "provider": "anthropic",
            "model": "claude-opus-4-7",
            "reasoning_effort": "high",
            "context_window": 200000,
            "temperature": 0.2,
            "tool_permissions": [
                "filesystem.read",
                "filesystem.edit",
                "process.run_declared_tests",
            ],
            "fallback_policy_ref": "fallback.provider_unavailable.record_failure",
        }
    )

    skill_registry = SkillBindingRegistry.from_bindings(
        skill,
        role_registry=role_registry,
        capability_registry=capability_registry,
        prompt_registry=prompt_registry,
        skill_file_registry=skill_file_registry,
        mcp_interface_registry=mcp_registry,
    )
    model_registry = ModelExecutionProfileRegistry.from_profiles(model_profile)

    assert skill_registry.contains(SkillRef(value="skill.backend.implementation"))
    assert model_registry.contains(ModelExecutionProfileId(value="model.worker.opus.high"))
    assert role.capability_tag_values() == (
        "role.worker",
        "task.implementation",
        "surface.backend",
    )


def test_skill_binding_normalizes_object_shaped_allowed_roles() -> None:
    skill = SkillBinding.model_validate(
        {
            "version": 1,
            "skill_ref": "skill.backend.implementation",
            "purpose": "Implement backend source changes for assigned implementation tickets.",
            "skill_file_ref": "skill_doc.backend_implementation.v1",
            "allowed_roles": [{"value": "role.worker.backend"}],
            "required_for_ticket_types": ["ticket.implementation"],
            "capability_tags": ["task.implementation", "surface.backend"],
            "prompt_refs": ["prompt.backend_implementation.system.v1"],
            "mcp_interface_refs": ["mcp.filesystem.edit_project"],
            "input_requirements": ["execution package"],
            "output_effects": ["work product"],
        }
    )

    assert skill.allowed_roles == (RoleProfileId(value="role.worker.backend"),)
    _skill_registry(skill)


def test_agent_config_rejects_unknown_schema_version() -> None:
    with pytest.raises(ValidationError):
        RoleProfile.model_validate(
            {
                "version": 2,
                "role_profile_id": "role.worker.backend",
                "role_category": "implementation",
                "role_name": "Backend Worker",
                "responsibilities": ["Implement backend source changes."],
                "capability_tags": ["role.worker"],
                "input_contracts": ["contract.execution_package"],
                "output_contracts": ["contract.work_product"],
                "forbidden_actions": ["mark ticket completed"],
            }
        )

    with pytest.raises(ValidationError):
        SkillBinding.model_validate(
            {
                "version": 2,
                "skill_ref": "skill.backend.implementation",
                "purpose": "Implement backend source changes.",
                "skill_file_ref": "skill_doc.backend_implementation.v1",
                "allowed_roles": ["role.worker.backend"],
                "required_for_ticket_types": ["ticket.implementation"],
                "capability_tags": ["task.implementation"],
                "prompt_refs": ["prompt.backend_implementation.system.v1"],
                "mcp_interface_refs": ["mcp.filesystem.read_project"],
                "input_requirements": ["execution package"],
                "output_effects": ["work product"],
            }
        )

    with pytest.raises(ValidationError):
        ModelExecutionProfile.model_validate(
            {
                "version": 2,
                "model_execution_profile_id": "model.worker.opus.high",
                "provider": "anthropic",
                "model": "claude-opus-4-7",
                "reasoning_effort": "high",
                "context_window": 200000,
                "temperature": 0.2,
                "tool_permissions": ["filesystem.read"],
                "fallback_policy_ref": "fallback.provider_unavailable.record_failure",
            }
        )


def test_layered_agent_config_templates_compile_to_registries() -> None:
    capability_registry = _capability_registry()
    role_registry = RoleProfileRegistry.from_profiles(
        _worker_role(), capability_registry=capability_registry
    )
    prompt_registry = _prompt_registry()
    skill_file_registry = _skill_file_registry()
    mcp_registry = _mcp_registry()

    skill_registry = SkillBindingRegistry.from_bindings(
        _backend_skill(),
        role_registry=role_registry,
        capability_registry=capability_registry,
        prompt_registry=prompt_registry,
        skill_file_registry=skill_file_registry,
        mcp_interface_registry=mcp_registry,
    )

    model_registry = ModelExecutionProfileRegistry.from_profiles(
        ModelExecutionProfile(
            model_execution_profile_id=ModelExecutionProfileId(
                value="model.worker.opus.high"
            ),
            provider="anthropic",
            model="claude-opus-4-7",
            reasoning_effort="high",
            context_window=200000,
            temperature=0.2,
            tool_permissions=(
                "filesystem.read",
                "filesystem.edit",
                "process.run_declared_tests",
            ),
            fallback_policy_ref=ContractId(
                value="fallback.provider_unavailable.record_failure"
            ),
        ),
        ModelExecutionProfile(
            model_execution_profile_id=ModelExecutionProfileId(
                value="model.worker.sonnet.medium"
            ),
            provider="anthropic",
            model="claude-sonnet-4-6",
            reasoning_effort="medium",
            context_window=200000,
            temperature=0.2,
            tool_permissions=("filesystem.read", "process.run_declared_tests"),
            fallback_policy_ref=ContractId(
                value="fallback.provider_unavailable.record_failure"
            ),
        ),
    )

    assert role_registry.contains(RoleProfileId(value="role.worker.backend"))
    assert skill_registry.contains(SkillRef(value="skill.backend.implementation"))
    assert model_registry.contains(ModelExecutionProfileId(value="model.worker.opus.high"))
    assert model_registry.contains(
        ModelExecutionProfileId(value="model.worker.sonnet.medium")
    )
    assert _worker_role().capability_tag_values() == (
        "role.worker",
        "task.implementation",
        "surface.backend",
    )
