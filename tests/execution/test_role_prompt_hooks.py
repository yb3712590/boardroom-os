from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from boardroom_os.agents.categories import RoleCategory
from boardroom_os.agents.profiles import RoleProfile, RoleProfileRegistry
from boardroom_os.agents.role_prompt_hooks import (
    RolePromptHook,
    RolePromptHookRegistry,
    RolePromptHookRef,
    RolePromptHookSha256,
    build_baseline_role_prompt_hook_registry,
)
from boardroom_os.agents.skills import (
    CapabilityDefinition,
    CapabilityRegistry,
    CapabilityTag,
    RoleProfileId,
)
from boardroom_os.contracts.types import ContractId
from boardroom_os.evidence.verifier import EvidenceVerificationBlockerCode, EvidenceVerifier
from boardroom_os.execution.compiler import ExecutionPackageCompilerError
from boardroom_os.execution.context_index import build_agent_context_snapshot
from boardroom_os.execution.provider_executor import ProviderExecutor, ProviderExecutorInput
from boardroom_os.providers.adapter import FakeProviderTransport, ProviderResponse
from tests.evidence.test_evidence_verifier import _input
from tests.fixtures.execution.compiler import (
    _agent_team_projection,
    _compile,
    _compiler_input,
    _role_profile,
)


def _capability_registry() -> CapabilityRegistry:
    return CapabilityRegistry.from_definitions(
        CapabilityDefinition(
            capability_tag=CapabilityTag(value="task.implementation"),
            description="Implement assigned source changes.",
        ),
    )


def _baseline_worker_hook() -> RolePromptHook:
    return build_baseline_role_prompt_hook_registry().require(
        RolePromptHookRef(value="role-prompt-hook.baseline.worker.v1")
    )


def _worker_role_hook_fields(hook: RolePromptHook | None = None) -> dict[str, object]:
    resolved_hook = hook or _baseline_worker_hook()
    return {
        "role_prompt_hook_ref": resolved_hook.hook_ref,
        "role_prompt_hook_version": resolved_hook.hook_version,
        "role_prompt_hook_sha256": resolved_hook.content_sha256,
    }


def _role_profile_fields() -> dict[str, object]:
    return {
        "role_profile_id": RoleProfileId(value="role.worker.backend"),
        "role_category": RoleCategory.IMPLEMENTATION,
        "role_name": "Backend Worker",
        "responsibilities": ("Implement backend source changes.",),
        "capability_tags": (CapabilityTag(value="task.implementation"),),
        "input_contracts": (ContractId(value="contract.execution_package"),),
        "output_contracts": (ContractId(value="contract.work_product"),),
        "forbidden_actions": ("Do not mark ticket completed.",),
        **_worker_role_hook_fields(),
    }


def test_role_profile_requires_role_prompt_hook_audit_fields() -> None:
    for field_name in (
        "role_prompt_hook_ref",
        "role_prompt_hook_version",
        "role_prompt_hook_sha256",
    ):
        fields = _role_profile_fields()
        fields.pop(field_name)

        with pytest.raises(ValidationError, match=field_name):
            RoleProfile(**fields)


def test_role_prompt_hook_registry_rejects_bypass_claims() -> None:
    worker_hook = _baseline_worker_hook()
    unsafe_texts = (
        (
            "role-prompt-hook.unsafe.worker.contracts.v1",
            "This hook bypasses AcceptanceContract, PackageContract, "
            "EvidenceVerifier, and CloseoutGate.",
        ),
        (
            "role-prompt-hook.unsafe.worker.reducer.v1",
            "This hook replaces the reducer for ticket completion.",
        ),
    )

    for hook_ref, unsafe_text in unsafe_texts:
        unsafe_hook = RolePromptHook(
            hook_ref=hook_ref,
            role_kind="worker",
            role_category=RoleCategory.IMPLEMENTATION,
            hook_version="v1",
            template_path="src/boardroom_os/agents/prompt_templates/baseline/v1/worker.md",
            content_sha256=RolePromptHookSha256.from_text(unsafe_text),
            prompt_text=unsafe_text,
            policy_refs=worker_hook.policy_refs,
            required_responsibilities=worker_hook.required_responsibilities,
        )

        with pytest.raises(ValueError, match="must not claim to bypass"):
            RolePromptHookRegistry.from_hooks(unsafe_hook)


def test_architect_hook_requires_run_command_and_service_boundary_responsibility() -> None:
    architect = build_baseline_role_prompt_hook_registry().require(
        RolePromptHookRef(value="role-prompt-hook.baseline.architect.v1")
    )
    weakened = architect.model_copy(
        update={
            "required_responsibilities": tuple(
                responsibility
                for responsibility in architect.required_responsibilities
                if "run command" not in responsibility
                and "service boundary" not in responsibility
            )
        }
    )

    with pytest.raises(ValueError, match="run command.*service boundary"):
        RolePromptHookRegistry.from_hooks(weakened)


def test_baseline_role_prompt_hooks_are_versioned_hashed_and_auditable() -> None:
    registry = build_baseline_role_prompt_hook_registry()

    expected_refs = {
        "role-prompt-hook.baseline.ceo.v1",
        "role-prompt-hook.baseline.architect.v1",
        "role-prompt-hook.baseline.worker.v1",
        "role-prompt-hook.baseline.tester.v1",
        "role-prompt-hook.baseline.checker.v1",
        "role-prompt-hook.baseline.closeout.v1",
    }

    assert {hook.hook_ref.value for hook in registry.hooks} == expected_refs
    for hook in registry.hooks:
        assert hook.hook_version == "v1"
        assert hook.prompt_text.strip()
        assert RolePromptHookSha256.from_text(hook.prompt_text) == hook.content_sha256
        assert hook.policy_refs
        assert hook.required_responsibilities


def test_baseline_registry_builder_is_independent_from_current_working_directory(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.chdir(tmp_path)

    registry = build_baseline_role_prompt_hook_registry()

    for hook in registry.hooks:
        assert hook.template_path.startswith(
            "boardroom_os/agents/prompt_templates/baseline/v1/"
        )
        assert Path(hook.template_path).is_absolute() is False


def test_role_profile_registry_rejects_missing_or_mismatched_hook() -> None:
    registry = build_baseline_role_prompt_hook_registry()
    role = RoleProfile(**_role_profile_fields())

    with pytest.raises(TypeError):
        RoleProfileRegistry.from_profiles(
            role,
            capability_registry=_capability_registry(),
        )

    mismatched_hash_role = role.model_copy(
        update={
            "role_prompt_hook_sha256": RolePromptHookSha256(
                value="0" * 64,
            )
        }
    )

    with pytest.raises(ValueError, match="role prompt hook hash mismatch"):
        RoleProfileRegistry.from_profiles(
            mismatched_hash_role,
            capability_registry=_capability_registry(),
            hook_registry=registry,
        )

    mismatched_category_role = role.model_copy(
        update={"role_category": RoleCategory.VERIFICATION}
    )

    with pytest.raises(ValueError, match="role prompt hook category mismatch"):
        RoleProfileRegistry.from_profiles(
            mismatched_category_role,
            capability_registry=_capability_registry(),
            hook_registry=registry,
        )


def test_execution_package_compiler_fails_closed_on_unresolved_hook_registry() -> None:
    with pytest.raises(ExecutionPackageCompilerError, match="role prompt hook registry"):
        _compile(role_prompt_hook_registry=None)


def test_execution_package_compiler_includes_role_prompt_hook_snapshot() -> None:
    execution_package = _compile()
    worker_hook = _baseline_worker_hook()

    assert execution_package.role_prompt_hook.hook_ref == worker_hook.hook_ref
    assert execution_package.role_prompt_hook.hook_version == worker_hook.hook_version
    assert execution_package.role_prompt_hook.content_sha256 == worker_hook.content_sha256
    assert execution_package.role_prompt_hook.prompt_text == worker_hook.prompt_text

    snapshot = build_agent_context_snapshot(execution_package)
    assert snapshot.role_prompt_hook == execution_package.role_prompt_hook


def test_provider_executor_prompt_and_attempt_include_role_prompt_hook_lineage() -> None:
    package = _compile()
    result = ProviderExecutor().execute(
        ProviderExecutorInput(
            execution_package=package,
            provider_adapter=FakeProviderTransport(
                response=ProviderResponse(
                    raw_output_ref="artifact.raw.worker",
                    parsed_output_ref="artifact.parsed.worker",
                    summary="Backend implementation",
                ),
                attempt_id="provider-attempt.worker",
                started_at=datetime(2026, 5, 31, 9, 0, tzinfo=UTC),
                finished_at=datetime(2026, 5, 31, 9, 1, tzinfo=UTC),
            ),
        )
    )

    hook = package.role_prompt_hook
    assert hook.prompt_text in result.prompt
    assert hook.hook_ref.value in result.prompt
    assert result.provider_attempt.role_prompt_hook_ref == hook.hook_ref
    assert result.provider_attempt.role_prompt_hook_version == hook.hook_version
    assert result.provider_attempt.role_prompt_hook_sha256 == hook.content_sha256


def test_evidence_verifier_blocks_provider_attempt_without_hook_audit_fields() -> None:
    verification_input = _input()
    legacy_attempt = verification_input.provider_attempts[0].model_copy(
        update={
            "role_prompt_hook_ref": None,
            "role_prompt_hook_version": None,
            "role_prompt_hook_sha256": None,
        }
    )

    result = EvidenceVerifier().verify(
        verification_input.model_copy(update={"provider_attempts": (legacy_attempt,)})
    )

    assert result.verified_evidence is None
    assert any(
        blocker.code
        is EvidenceVerificationBlockerCode.PROVIDER_ATTEMPT_ROLE_PROMPT_HOOK_INVALID
        for blocker in result.blockers
    )
