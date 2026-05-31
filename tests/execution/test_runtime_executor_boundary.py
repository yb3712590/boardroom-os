from datetime import UTC, datetime
from pathlib import Path
import sys

import pytest

from boardroom_os.agents.categories import RoleCategory
from boardroom_os.agents.policy import RoleProfileProjection
from boardroom_os.agents.profiles import ModelExecutionProfile, ModelExecutionProfileId
from boardroom_os.agents.seat import (
    AgentSeat,
    AgentSeatRef,
    SeatLifecycleProjection,
    SeatLifecycleStatus,
)
from boardroom_os.agents.skills import CapabilityTag, RoleProfileId, SkillRef
from boardroom_os.agents.team import AgentTeamProjection
from boardroom_os.contracts.evidence_obligation import (
    EvidenceObligation,
    RequiredArtifactType,
    RequiredVerifier,
)
from boardroom_os.contracts.package import (
    IntegrationBoundary,
    PackageCommand,
    PackageContract,
    PackageProjectType,
)
from boardroom_os.contracts.source_surface import OwnerSeatRef, RequiredTestRef, SourceSurface
from boardroom_os.contracts.types import (
    AcceptanceRef,
    ContractId,
    EvidenceObligationRef,
    SourceSurfaceRef,
)
from boardroom_os.events.types import ActorRef, EventPayloadRef, EventType, ProjectRef
from boardroom_os.execution.context_index import ProviderAttemptRef
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
from boardroom_os.execution.runtime_executor import (
    RuntimeEventBoundary,
    RuntimeEventSequencer,
    RuntimeExecutionInput,
    RuntimeExecutor,
    build_command_run_recorded_event,
    build_execution_started_event,
    build_provider_attempt_recorded_event,
)
from boardroom_os.execution.verification_run import (
    EnvironmentProfileRef,
    RunnerRef,
    VerificationRunRef,
    WorkspaceSnapshotRef,
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
from tests.fixtures.execution.role_prompt_hooks import baseline_role_prompt_hook


def test_runtime_executor_public_api_is_exported_from_execution_package() -> None:
    from boardroom_os.execution import RuntimeExecutor as ExportedRuntimeExecutor
    from boardroom_os.execution import RuntimeExecutionInput as ExportedRuntimeExecutionInput
    from boardroom_os.execution import RuntimeEventBoundary as ExportedRuntimeEventBoundary

    assert ExportedRuntimeExecutor is RuntimeExecutor
    assert ExportedRuntimeExecutionInput is RuntimeExecutionInput
    assert ExportedRuntimeEventBoundary is RuntimeEventBoundary


BASE_TIMESTAMP = datetime(2026, 5, 19, 9, 0, tzinfo=UTC)
PROJECT_REF = ProjectRef(value="project.runtime.executor")
RUNTIME_ACTOR_REF = ActorRef(value="actor.runtime.executor")
WORKER_ACTOR_REF = ActorRef(value="actor.worker.backend")
WORKER_SEAT_REF = AgentSeatRef(value="seat.worker.backend")


def _model_execution_profile() -> ModelExecutionProfile:
    return ModelExecutionProfile(
        model_execution_profile_id=ModelExecutionProfileId(value="model.worker.backend"),
        provider="anthropic",
        model="claude-opus-4-7",
        reasoning_effort="medium",
        context_window=200000,
        temperature=0.2,
        tool_permissions=("provider.invoke", "process.run"),
        fallback_policy_ref=ContractId(value="fallback.default"),
    )


def _worker_seat() -> AgentSeat:
    return AgentSeat(
        seat_ref=WORKER_SEAT_REF,
        actor_ref=WORKER_ACTOR_REF,
        project_ref=PROJECT_REF,
        role_profile_ref=RoleProfileId(value="role.worker.backend"),
        role_category=RoleCategory.IMPLEMENTATION,
        capability_tags=(CapabilityTag(value="task.implementation"),),
        model_execution_profile_ref=ModelExecutionProfileId(value="model.worker.backend"),
        skill_refs=(SkillRef(value="skill.runtime-test"),),
        context_budget_tokens=4096,
        lifecycle_status=SeatLifecycleStatus.ACTIVE,
    )


def _agent_team_projection() -> AgentTeamProjection:
    seat = _worker_seat()
    return AgentTeamProjection(
        graph_version=7,
        role_profiles=RoleProfileProjection(profiles=()),
        seat_lifecycle=SeatLifecycleProjection(
            graph_version=7,
            seats={seat.seat_ref: seat},
            active_seats={seat.seat_ref: seat},
            replacement_refs={},
        ),
    )


def _package_command(command_id: str = "command.runtime.test", exit_code: int = 0) -> PackageCommand:
    code = "import sys; sys.stdout.buffer.write(b'ok\\n')" if exit_code == 0 else "import sys; print('bad'); sys.exit(2)"
    return PackageCommand(
        command_id=ContractId(value=command_id),
        label="Run runtime test command",
        command=(sys.executable, "-c", code),
        cwd=".",
    )


def _evidence_obligation() -> EvidenceObligation:
    return EvidenceObligation(
        evidence_obligation_id=EvidenceObligationRef(value="evidence.runtime.source"),
        acceptance_refs=(AcceptanceRef(value="AC-RUNTIME"),),
        source_surface_refs=(SourceSurfaceRef(value="surface.runtime"),),
        required_artifact_type=RequiredArtifactType(value="source"),
        required_verifier=RequiredVerifier(value="source_inventory"),
        blocking=True,
    )


def _execution_package(*commands: PackageCommand) -> ExecutionPackage:
    selected_commands = commands or (_package_command(),)
    return ExecutionPackage(
        execution_package_id=ExecutionPackageId(value="execution-package.runtime"),
        ticket_ref=TicketId(value="ticket.runtime"),
        graph_version=7,
        seat_ref=WORKER_SEAT_REF,
        model_execution_profile=_model_execution_profile(),
        role_prompt_hook=baseline_role_prompt_hook(),
        objective="Execute runtime boundary package.",
        context_refs=(ContextRef(value="context.runtime"),),
        constraints=("Stay inside runtime boundary.",),
        acceptance_refs=(AcceptanceRef(value="AC-RUNTIME"),),
        source_surface_refs=(SourceSurfaceRef(value="surface.runtime"),),
        allowed_read_refs=(AllowedReadRef(value="README.md"),),
        allowed_write_set=(AllowedWritePath(value="src/runtime.py"),),
        required_outputs=(RequiredOutput(value="runtime fact records"),),
        commands=selected_commands,
        evidence_obligations=(_evidence_obligation(),),
        fallback_policy_ref=FallbackPolicyRef(value="fallback.default"),
        audit_requirements=(AuditRequirement(value="record runtime facts"),),
    )


def _source_surface() -> SourceSurface:
    return SourceSurface(
        source_surface_ref=SourceSurfaceRef(value="surface.runtime"),
        name="Runtime surface",
        paths=("src",),
        owned_by=OwnerSeatRef(value="owner.runtime"),
        acceptance_refs=(AcceptanceRef(value="AC-RUNTIME"),),
        required_tests=(RequiredTestRef(value="command.runtime.test"),),
    )


def _package_contract(*commands: PackageCommand) -> PackageContract:
    selected_commands = commands or (_package_command(),)
    return PackageContract(
        package_contract_id=ContractId(value="package-contract.runtime"),
        project_charter_ref=ContractId(value="project-charter.runtime"),
        package_root="10-project",
        project_type=PackageProjectType.SOFTWARE,
        source_surfaces=(_source_surface(),),
        run_commands=(_package_command(command_id="command.runtime.run"),),
        test_commands=selected_commands,
        integration_boundaries=(IntegrationBoundary(value="local-process"),),
        docs_required=False,
        closeout_required=True,
    )


class FailedProviderTransport:
    def invoke(self, request: ProviderRequest) -> ProviderAttempt:
        profile = request.model_execution_profile
        return ProviderAttempt(
            provider_attempt_id="provider-attempt.failed-runtime",
            provider=profile.provider,
            model=profile.model,
            reasoning_effort=profile.reasoning_effort,
            input_package_ref=request.execution_package_ref,
            seat_ref=request.seat_ref,
            role_prompt_hook_ref=request.role_prompt_hook_ref,
            role_prompt_hook_version=request.role_prompt_hook_version,
            role_prompt_hook_sha256=request.role_prompt_hook_sha256,
            status=ProviderAttemptStatus.FAILED,
            outcome=ProviderAttemptOutcome.PRIMARY_PROVIDER_OUTPUT,
            started_at=BASE_TIMESTAMP,
            finished_at=BASE_TIMESTAMP,
            failure_kind="provider_unavailable",
        )


def _successful_provider_transport() -> FakeProviderTransport:
    return FakeProviderTransport(
        response=ProviderResponse(
            raw_output_ref="provider-artifact.raw.runtime",
            parsed_output_ref="provider-artifact.parsed.runtime",
            summary="Runtime executor success output.",
        ),
        attempt_id="provider-attempt.runtime",
        started_at=BASE_TIMESTAMP,
        finished_at=BASE_TIMESTAMP,
    )


def _runtime_input(
    *,
    provider_adapter: object,
    execution_package: ExecutionPackage | None = None,
    package_contract: PackageContract | None = None,
    command_ids: tuple[ContractId, ...] = (ContractId(value="command.runtime.test"),),
    package_root: Path,
) -> RuntimeExecutionInput:
    package = execution_package or _execution_package()
    return RuntimeExecutionInput(
        execution_package=package,
        package_contract=package_contract or _package_contract(*package.commands),
        agent_team_projection=_agent_team_projection(),
        provider_adapter=provider_adapter,
        project_ref=PROJECT_REF,
        runtime_actor_ref=RUNTIME_ACTOR_REF,
        first_fact_graph_version=8,
        package_root=package_root,
        runner_ref=RunnerRef(value="runner.runtime"),
        environment_profile_ref=EnvironmentProfileRef(value="environment.runtime"),
        workspace_snapshot_ref=WorkspaceSnapshotRef(value="workspace.runtime"),
        command_ids=command_ids,
        timestamp=BASE_TIMESTAMP,
    )



def test_runtime_event_boundary_allows_only_runtime_fact_events() -> None:
    allowed_event_types = (
        EventType.EXECUTION_STARTED,
        EventType.PROVIDER_ATTEMPT_RECORDED,
        EventType.TOOL_ATTEMPT_RECORDED,
        EventType.WORK_PRODUCT_SUBMITTED,
        EventType.COMMAND_RUN_RECORDED,
    )

    assert (
        tuple(
            RuntimeEventBoundary.require_runtime_fact_event(event_type)
            for event_type in allowed_event_types
        )
        == allowed_event_types
    )


def test_runtime_executor_assigns_deterministic_monotonic_graph_versions() -> None:
    sequencer = RuntimeEventSequencer(base_graph_version=7, first_fact_graph_version=8)

    assert sequencer.next_graph_version() == 8
    assert sequencer.next_graph_version() == 9
    assert sequencer.next_graph_version() == 10


def test_runtime_event_sequencer_keeps_cursor_out_of_public_model_surface() -> None:
    sequencer = RuntimeEventSequencer(base_graph_version=7, first_fact_graph_version=8)

    assert "next_fact_graph_version" not in sequencer.model_dump()

    with pytest.raises((AttributeError, TypeError, ValueError)):
        sequencer.next_fact_graph_version = -3

    assert sequencer.next_graph_version() == 8
    assert sequencer.next_graph_version() == 9


def test_runtime_event_sequencer_rejects_first_fact_graph_version_not_after_base() -> None:
    with pytest.raises(ValueError, match="greater than base_graph_version"):
        RuntimeEventSequencer(base_graph_version=7, first_fact_graph_version=7)


def test_runtime_execution_input_rejects_duplicate_command_ids(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="command_ids must be unique"):
        _runtime_input(
            provider_adapter=_successful_provider_transport(),
            package_root=tmp_path,
            command_ids=(
                ContractId(value="command.runtime.test"),
                ContractId(value="command.runtime.test"),
            ),
        )


def test_runtime_event_factories_emit_expected_payload_refs_and_types() -> None:
    execution_package_id = ExecutionPackageId(value="execution-package.runtime.executor")
    provider_attempt_ref = ProviderAttemptRef(value="provider-attempt.runtime.executor")
    verification_run_ref = VerificationRunRef(value="verification-run.runtime.executor")

    execution_started_event = build_execution_started_event(
        execution_package_id=execution_package_id,
        project_ref=PROJECT_REF,
        actor_ref=RUNTIME_ACTOR_REF,
        graph_version=8,
        timestamp=BASE_TIMESTAMP,
    )
    provider_attempt_event = build_provider_attempt_recorded_event(
        provider_attempt_ref=provider_attempt_ref,
        project_ref=PROJECT_REF,
        actor_ref=RUNTIME_ACTOR_REF,
        graph_version=9,
        timestamp=BASE_TIMESTAMP,
    )
    command_run_event = build_command_run_recorded_event(
        verification_run_ref=verification_run_ref,
        project_ref=PROJECT_REF,
        actor_ref=RUNTIME_ACTOR_REF,
        graph_version=10,
        timestamp=BASE_TIMESTAMP,
    )

    assert execution_started_event.event_type is EventType.EXECUTION_STARTED
    assert execution_started_event.payload_refs == (
        EventPayloadRef(value=execution_package_id.value),
    )
    assert provider_attempt_event.event_type is EventType.PROVIDER_ATTEMPT_RECORDED
    assert provider_attempt_event.payload_refs == (
        EventPayloadRef(value=provider_attempt_ref.value),
    )
    assert command_run_event.event_type is EventType.COMMAND_RUN_RECORDED
    assert command_run_event.payload_refs == (
        EventPayloadRef(value=verification_run_ref.value),
    )


def test_runtime_executor_records_failed_provider_attempt_without_work_product_or_command_run(
    tmp_path: Path,
) -> None:
    result = RuntimeExecutor().execute_package(
        _runtime_input(provider_adapter=FailedProviderTransport(), package_root=tmp_path)
    )

    assert result.provider_attempt.provider_attempt_id.value == "provider-attempt.failed-runtime"
    assert result.provider_attempt.status is ProviderAttemptStatus.FAILED
    assert result.work_product_submission is None
    assert result.verification_runs == ()
    assert result.stdout_by_verification_run == {}
    assert result.stderr_by_verification_run == {}
    assert tuple(event.event_type for event in result.events) == (
        EventType.EXECUTION_STARTED,
        EventType.PROVIDER_ATTEMPT_RECORDED,
    )
    assert tuple(event.graph_version for event in result.events) == (8, 9)


def test_runtime_executor_records_provider_attempt_work_product_and_command_run_facts(
    tmp_path: Path,
) -> None:
    result = RuntimeExecutor().execute_package(
        _runtime_input(provider_adapter=_successful_provider_transport(), package_root=tmp_path)
    )

    assert result.provider_attempt.provider_attempt_id.value == "provider-attempt.runtime"
    assert result.provider_attempt.status is ProviderAttemptStatus.SUCCEEDED
    assert result.work_product_submission is not None
    assert (
        result.work_product_submission.work_product.producer_attempt_ref.value
        == "provider-attempt.runtime"
    )
    assert len(result.verification_runs) == 1
    verification_run = result.verification_runs[0]
    assert verification_run.command_id.value == "command.runtime.test"
    assert result.stdout_by_verification_run[verification_run.verification_run_id] == "ok\n"
    assert result.stderr_by_verification_run[verification_run.verification_run_id] == ""
    assert tuple(event.event_type for event in result.events) == (
        EventType.EXECUTION_STARTED,
        EventType.PROVIDER_ATTEMPT_RECORDED,
        EventType.WORK_PRODUCT_SUBMITTED,
        EventType.COMMAND_RUN_RECORDED,
    )
    assert tuple(event.graph_version for event in result.events) == (8, 9, 10, 11)
    assert EventType.TICKET_COMPLETED not in tuple(event.event_type for event in result.events)



def test_runtime_executor_records_failed_command_run_as_fact(tmp_path: Path) -> None:
    failing_command = _package_command(exit_code=2)
    package = _execution_package(failing_command)

    result = RuntimeExecutor().execute_package(
        _runtime_input(
            provider_adapter=_successful_provider_transport(),
            execution_package=package,
            package_contract=_package_contract(failing_command),
            package_root=tmp_path,
        )
    )

    assert result.work_product_submission is not None
    assert tuple(run.exit_code for run in result.verification_runs) == (2,)
    assert tuple(run.status.value for run in result.verification_runs) == ("failed",)
    assert tuple(event.event_type for event in result.events) == (
        EventType.EXECUTION_STARTED,
        EventType.PROVIDER_ATTEMPT_RECORDED,
        EventType.WORK_PRODUCT_SUBMITTED,
        EventType.COMMAND_RUN_RECORDED,
    )
    assert EventType.TICKET_COMPLETED not in tuple(event.event_type for event in result.events)
