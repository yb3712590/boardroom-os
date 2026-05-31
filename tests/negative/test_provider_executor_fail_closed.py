from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from boardroom_os.agents.categories import RoleCategory
from boardroom_os.agents.profiles import ModelExecutionProfile, RoleProfile
from boardroom_os.agents.seat import AgentSeatRef
from boardroom_os.agents.skills import CapabilityTag, RoleProfileId
from boardroom_os.contracts.evidence_obligation import (
    EvidenceObligation,
    RequiredArtifactType,
    RequiredVerifier,
)
from boardroom_os.contracts.package import PackageCommand
from boardroom_os.contracts.types import (
    AcceptanceRef,
    ContractId,
    EvidenceObligationRef,
    SourceSurfaceRef,
)
from boardroom_os.execution.package import (
    AllowedReadRef,
    AllowedWritePath,
    AuditRequirement,
    ContextRef,
    ExecutionPackage,
    ExecutionPackageId,
    FallbackPolicyRef,
    RequiredOutput,
)
from boardroom_os.execution.provider_executor import (
    ProviderExecutor,
    ProviderExecutorError,
    ProviderExecutorInput,
)
from boardroom_os.graph.ticket import TicketId
from boardroom_os.providers.adapter import (
    FakeProviderTransport,
    ProviderRequest,
    ProviderResponse,
)
from boardroom_os.providers.attempt import (
    ProviderAttempt,
    ProviderAttemptOutcome,
    ProviderAttemptStatus,
)
from tests.fixtures.execution.role_prompt_hooks import (
    baseline_role_prompt_hook,
    baseline_role_prompt_hook_fields_for_category,
)


def _model_execution_profile() -> ModelExecutionProfile:
    return ModelExecutionProfile(
        model_execution_profile_id="model-profile.worker.default",
        provider="anthropic",
        model="claude-opus-4-7",
        reasoning_effort="medium",
        context_window=200000,
        temperature=0.2,
        tool_permissions=("filesystem.write",),
        fallback_policy_ref="fallback.default",
    )


def _evidence_obligation() -> EvidenceObligation:
    return EvidenceObligation(
        evidence_obligation_id=EvidenceObligationRef(value="evidence.source.backend"),
        acceptance_refs=(AcceptanceRef(value="AC-BACKEND"),),
        source_surface_refs=(SourceSurfaceRef(value="surface.backend"),),
        required_artifact_type=RequiredArtifactType(value="source_patch"),
        required_verifier=RequiredVerifier(value="checker"),
        blocking=True,
    )


def _command() -> PackageCommand:
    return PackageCommand(
        command_id=ContractId(value="cmd.test"),
        label="Run tests",
        command=("pytest", "tests"),
        cwd="10-project",
    )


def _execution_package() -> ExecutionPackage:
    return ExecutionPackage(
        execution_package_id=ExecutionPackageId(value="exec.ticket.backend.1"),
        ticket_ref=TicketId(value="ticket.backend"),
        graph_version=7,
        seat_ref=AgentSeatRef(value="seat.worker.backend"),
        model_execution_profile=_model_execution_profile(),
        role_prompt_hook=baseline_role_prompt_hook(),
        objective="Implement backend API",
        context_refs=(
            ContextRef(value="contract.acceptance.active"),
            ContextRef(value="contract.package.active"),
        ),
        constraints=(
            "Only write paths listed in allowed_write_set.",
            "Do not modify active contracts or governance state.",
        ),
        acceptance_refs=(AcceptanceRef(value="AC-BACKEND"),),
        source_surface_refs=(SourceSurfaceRef(value="surface.backend"),),
        allowed_read_refs=(AllowedReadRef(value="README.md"),),
        allowed_write_set=(AllowedWritePath(value="backend/app.py"),),
        required_outputs=(RequiredOutput(value="source:surface.backend"),),
        commands=(_command(),),
        evidence_obligations=(_evidence_obligation(),),
        fallback_policy_ref=FallbackPolicyRef(value="fallback.default"),
        audit_requirements=(AuditRequirement(value="record.received_execution_package"),),
    )


def _started_at() -> datetime:
    return datetime(2026, 5, 18, 9, 0, tzinfo=UTC)



def _finished_at() -> datetime:
    return datetime(2026, 5, 18, 9, 1, tzinfo=UTC)



def _provider_adapter() -> FakeProviderTransport:
    return FakeProviderTransport(
        response=ProviderResponse(
            raw_output_ref="artifact.raw.1",
            parsed_output_ref="artifact.parsed.1",
            summary="Backend API implementation",
        ),
        attempt_id="provider-attempt.1",
        started_at=_started_at(),
        finished_at=_finished_at(),
    )


class MisbindingFakeProviderTransport:
    def __init__(self, **overrides: object) -> None:
        self._overrides = overrides
        self.calls = 0

    def invoke(self, request: ProviderRequest) -> ProviderAttempt:
        self.calls += 1
        profile = request.model_execution_profile
        fields = {
            "provider_attempt_id": f"provider-attempt.misbinding.{self.calls}",
            "provider": profile.provider,
            "model": profile.model,
            "reasoning_effort": profile.reasoning_effort,
            "input_package_ref": request.execution_package_ref,
            "seat_ref": request.seat_ref,
            "role_prompt_hook_ref": request.role_prompt_hook_ref,
            "role_prompt_hook_version": request.role_prompt_hook_version,
            "role_prompt_hook_sha256": request.role_prompt_hook_sha256,
            "status": ProviderAttemptStatus.SUCCEEDED,
            "outcome": ProviderAttemptOutcome.PRIMARY_PROVIDER_OUTPUT,
            "started_at": _started_at(),
            "finished_at": _finished_at(),
            "raw_output_ref": "artifact.raw.1",
            "parsed_output_ref": "artifact.parsed.1",
        }
        fields.update(self._overrides)
        return ProviderAttempt(**fields)


def test_provider_executor_input_requires_execution_package() -> None:
    with pytest.raises(ValidationError):
        ProviderExecutorInput(provider_adapter=_provider_adapter())


def test_provider_executor_input_rejects_extra_role_or_ticket_fields() -> None:
    role_profile = RoleProfile(
        role_profile_id=RoleProfileId(value="role.worker.backend"),
        role_category=RoleCategory.IMPLEMENTATION,
        role_name="Backend Worker",
        responsibilities=("Implement backend source",),
        capability_tags=(CapabilityTag(value="implementation.backend"),),
        input_contracts=(ContractId(value="contract.acceptance"),),
        output_contracts=(ContractId(value="contract.source"),),
        forbidden_actions=("complete tickets",),
        **baseline_role_prompt_hook_fields_for_category(RoleCategory.IMPLEMENTATION),
    )

    with pytest.raises(ValidationError):
        ProviderExecutorInput(
            execution_package=_execution_package(),
            provider_adapter=_provider_adapter(),
            role_profile=role_profile,
        )

    with pytest.raises(ValidationError):
        ProviderExecutorInput(
            execution_package=_execution_package(),
            provider_adapter=_provider_adapter(),
            ticket_ref=TicketId(value="ticket.backend"),
        )


def test_provider_executor_input_rejects_non_callable_provider_invoke() -> None:
    class NonCallableInvokeProviderAdapter:
        invoke = 1

    with pytest.raises(ValidationError, match="callable invoke"):
        ProviderExecutorInput(
            execution_package=_execution_package(),
            provider_adapter=NonCallableInvokeProviderAdapter(),
        )


@pytest.mark.parametrize(
    ("overrides", "error_match"),
    [
        ({"input_package_ref": "exec.other"}, "input_package_ref"),
        ({"seat_ref": "seat.other"}, "seat_ref"),
        ({"provider": "other-provider"}, "mismatch: provider"),
        ({"model": "other-model"}, "model"),
        ({"reasoning_effort": "high"}, "reasoning_effort"),
    ],
)
def test_provider_executor_rejects_misbound_provider_attempt(
    overrides: dict[str, object],
    error_match: str,
) -> None:
    adapter = MisbindingFakeProviderTransport(**overrides)

    with pytest.raises(ProviderExecutorError, match=error_match):
        ProviderExecutor().execute(
            ProviderExecutorInput(
                execution_package=_execution_package(),
                provider_adapter=adapter,
            )
        )

    assert adapter.calls == 1
