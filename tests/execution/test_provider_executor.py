from __future__ import annotations

from datetime import UTC, datetime

from boardroom_os.agents.profiles import ModelExecutionProfile
from boardroom_os.agents.seat import AgentSeatRef
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
from boardroom_os.execution.context_index import build_agent_context_snapshot
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
    ProviderExecutorInput,
    render_prompt_from_snapshot,
)
from boardroom_os.graph.ticket import TicketId
from boardroom_os.providers.adapter import FakeProviderTransport, ProviderRequest, ProviderResponse
from boardroom_os.providers.attempt import (
    ProviderArtifactRef,
    ProviderAttempt,
    ProviderAttemptOutcome,
    ProviderAttemptStatus,
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


def _execution_package(
    *,
    allowed_read_refs: tuple[AllowedReadRef, ...] | None = None,
) -> ExecutionPackage:
    return ExecutionPackage(
        execution_package_id=ExecutionPackageId(value="exec.ticket.backend.1"),
        ticket_ref=TicketId(value="ticket.backend"),
        graph_version=7,
        seat_ref=AgentSeatRef(value="seat.worker.backend"),
        model_execution_profile=_model_execution_profile(),
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
        allowed_read_refs=(
            (AllowedReadRef(value="README.md"),)
            if allowed_read_refs is None
            else allowed_read_refs
        ),
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


class FailedProviderTransport:
    def invoke(self, request: ProviderRequest) -> ProviderAttempt:
        profile = request.model_execution_profile
        return ProviderAttempt(
            provider_attempt_id="provider-attempt.failed",
            provider=profile.provider,
            model=profile.model,
            reasoning_effort=profile.reasoning_effort,
            input_package_ref=request.execution_package_ref,
            seat_ref=request.seat_ref,
            status=ProviderAttemptStatus.FAILED,
            outcome=ProviderAttemptOutcome.PRIMARY_PROVIDER_OUTPUT,
            started_at=_started_at(),
            finished_at=_finished_at(),
            failure_kind="transport_error",
        )


def test_render_prompt_from_snapshot_is_deterministic() -> None:
    snapshot = build_agent_context_snapshot(_execution_package())

    first = render_prompt_from_snapshot(snapshot)
    second = render_prompt_from_snapshot(snapshot)

    assert first == second
    assert "objective" in first
    assert "Implement backend API" in first
    assert "allowed_write_set" in first
    assert "backend/app.py" in first
    assert "evidence_obligations" in first
    assert "source_patch" in first


def test_render_prompt_from_snapshot_includes_empty_allowed_read_refs() -> None:
    snapshot = build_agent_context_snapshot(_execution_package(allowed_read_refs=()))

    prompt = render_prompt_from_snapshot(snapshot)

    assert "allowed_read_refs" in prompt
    assert '"allowed_read_refs":[]' in prompt


def test_provider_executor_invokes_provider_from_execution_package() -> None:
    package = _execution_package()
    executor = ProviderExecutor()

    result = executor.execute(
        ProviderExecutorInput(
            execution_package=package,
            provider_adapter=_provider_adapter(),
        )
    )

    attempt = result.provider_attempt
    profile = package.model_execution_profile

    assert attempt.provider_attempt_id.value == "provider-attempt.1"
    assert attempt.input_package_ref.value == package.execution_package_id.value
    assert attempt.seat_ref == package.seat_ref
    assert attempt.provider == profile.provider
    assert attempt.model == profile.model
    assert attempt.reasoning_effort == profile.reasoning_effort
    assert attempt.status is ProviderAttemptStatus.SUCCEEDED
    assert attempt.raw_output_ref == ProviderArtifactRef(value="artifact.raw.1")
    assert attempt.parsed_output_ref == ProviderArtifactRef(value="artifact.parsed.1")
    assert result.context_snapshot == build_agent_context_snapshot(package)
    assert result.prompt == render_prompt_from_snapshot(result.context_snapshot)


def test_provider_executor_returns_failed_attempt_without_raising() -> None:
    package = _execution_package()
    executor = ProviderExecutor()

    result = executor.execute(
        ProviderExecutorInput(
            execution_package=package,
            provider_adapter=FailedProviderTransport(),
        )
    )

    attempt = result.provider_attempt

    assert attempt.provider_attempt_id.value == "provider-attempt.failed"
    assert attempt.status is ProviderAttemptStatus.FAILED
    assert attempt.failure_kind == "transport_error"
    assert attempt.input_package_ref.value == package.execution_package_id.value
    assert result.context_snapshot.execution_package_ref.value == package.execution_package_id.value
