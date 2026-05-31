import pytest

from boardroom_os.agents.categories import RoleCategory
from boardroom_os.agents.policy import RoleProfileProjection
from boardroom_os.agents.profiles import ModelExecutionProfile
from boardroom_os.agents.seat import AgentSeat, AgentSeatRef, SeatLifecycleProjection, SeatLifecycleStatus
from boardroom_os.agents.skills import CapabilityTag, SkillRef
from boardroom_os.agents.team import AgentTeamProjection
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
from boardroom_os.events.types import ActorRef, EventType
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
    RuntimeExecutorError,
)
from boardroom_os.graph.ticket import TicketId
from tests.fixtures.execution.role_prompt_hooks import baseline_role_prompt_hook


@pytest.fixture
def runtime_actor_ref() -> ActorRef:
    return ActorRef(value="actor.runtime.executor")


@pytest.fixture
def model_execution_profile() -> ModelExecutionProfile:
    return ModelExecutionProfile(
        model_execution_profile_id="model.runtime.executor",
        provider="anthropic",
        model="claude-sonnet-4-6",
        reasoning_effort="medium",
        context_window=200000,
        temperature=0.2,
        tool_permissions=("filesystem.write",),
        fallback_policy_ref=ContractId(value="fallback.runtime.record_failure"),
    )


def _seat(
    *,
    seat_ref: AgentSeatRef | str,
    actor_ref: ActorRef | str,
    role_category: RoleCategory,
    model_execution_profile: ModelExecutionProfile,
    capability_tags: tuple[CapabilityTag, ...] | None = None,
    lifecycle_status: SeatLifecycleStatus = SeatLifecycleStatus.ACTIVE,
) -> AgentSeat:
    resolved_actor_ref = actor_ref if isinstance(actor_ref, ActorRef) else ActorRef(value=actor_ref)
    resolved_seat_ref = seat_ref if isinstance(seat_ref, AgentSeatRef) else AgentSeatRef(value=seat_ref)
    default_capability_tag = {
        RoleCategory.GOVERNANCE: CapabilityTag(value="team.composition"),
        RoleCategory.ARCHITECTURE: CapabilityTag(value="task.architecture"),
        RoleCategory.IMPLEMENTATION: CapabilityTag(value="task.implementation"),
        RoleCategory.VERIFICATION: CapabilityTag(value="task.verification"),
        RoleCategory.AUDIT: CapabilityTag(value="task.audit"),
        RoleCategory.INTEGRATION: CapabilityTag(value="task.integration"),
    }[role_category]
    return AgentSeat(
        seat_ref=resolved_seat_ref,
        actor_ref=resolved_actor_ref,
        project_ref="project.runtime.boundary",
        role_profile_ref=f"role.{role_category.value}.default",
        role_category=role_category,
        capability_tags=capability_tags or (default_capability_tag,),
        model_execution_profile_ref=model_execution_profile.model_execution_profile_id,
        skill_refs=(SkillRef(value="skill.runtime.execute"),),
        context_budget_tokens=4096,
        lifecycle_status=lifecycle_status,
    )


def _agent_team_projection(
    *,
    seats: tuple[AgentSeat, ...] | None = None,
    active_seats: tuple[AgentSeat, ...],
) -> AgentTeamProjection:
    resolved_seats = seats if seats is not None else active_seats
    return AgentTeamProjection(
        graph_version=7,
        role_profiles=RoleProfileProjection(profiles=()),
        seat_lifecycle=SeatLifecycleProjection(
            graph_version=7,
            seats={seat.seat_ref: seat for seat in resolved_seats},
            active_seats={seat.seat_ref: seat for seat in active_seats},
            replacement_refs={},
        ),
    )


def _execution_package(
    *,
    seat_ref: AgentSeatRef,
    model_execution_profile: ModelExecutionProfile,
) -> ExecutionPackage:
    return ExecutionPackage(
        execution_package_id=ExecutionPackageId(value="execution-package.runtime-boundary"),
        ticket_ref=TicketId(value="ticket.runtime-boundary"),
        graph_version=7,
        seat_ref=seat_ref,
        model_execution_profile=model_execution_profile,
        role_prompt_hook=baseline_role_prompt_hook(),
        objective="Execute the assigned worker package.",
        context_refs=(ContextRef(value="context.runtime.boundary"),),
        constraints=("Stay inside the assigned execution seat.",),
        acceptance_refs=(AcceptanceRef(value="AC-RUNTIME-BOUNDARY"),),
        source_surface_refs=(SourceSurfaceRef(value="surface.runtime.boundary"),),
        allowed_read_refs=(AllowedReadRef(value="contracts/runtime-boundary.md"),),
        allowed_write_set=(AllowedWritePath(value="src/runtime_executor.py"),),
        required_outputs=(RequiredOutput(value="runtime execution evidence"),),
        commands=(
            PackageCommand(
                command_id=ContractId(value="cmd.runtime.boundary"),
                label="Run runtime boundary checks",
                command=("pytest", "tests/negative/test_runtime_cannot_govern.py"),
                cwd=".",
            ),
        ),
        evidence_obligations=(
            EvidenceObligation(
                evidence_obligation_id=EvidenceObligationRef(value="evidence.runtime.boundary"),
                acceptance_refs=(AcceptanceRef(value="AC-RUNTIME-BOUNDARY"),),
                source_surface_refs=(SourceSurfaceRef(value="surface.runtime.boundary"),),
                required_artifact_type=RequiredArtifactType(value="runtime_boundary_assertion"),
                required_verifier=RequiredVerifier(value="runtime_executor"),
                blocking=True,
            ),
        ),
        fallback_policy_ref=FallbackPolicyRef(value="fallback.runtime.record_failure"),
        audit_requirements=(AuditRequirement(value="record runtime actor and seat boundary"),),
    )


def test_runtime_event_boundary_rejects_ticket_completed() -> None:
    with pytest.raises(RuntimeExecutorError, match="governance event"):
        RuntimeEventBoundary.require_runtime_fact_event(EventType.TICKET_COMPLETED)


def test_runtime_event_sequencer_rejects_non_advancing_first_fact_graph_version() -> None:
    with pytest.raises(ValueError, match="greater than base_graph_version"):
        RuntimeEventSequencer(base_graph_version=7, first_fact_graph_version=7)


def test_runtime_event_boundary_rejects_project_completed_reserved_name() -> None:
    with pytest.raises(RuntimeExecutorError, match="governance event"):
        RuntimeEventBoundary.require_runtime_fact_event("project_completed")


def test_runtime_event_boundary_rejects_closeout_committed_reserved_name() -> None:
    with pytest.raises(RuntimeExecutorError, match="governance event"):
        RuntimeEventBoundary.require_runtime_fact_event("closeout_committed")


def test_runtime_event_boundary_rejects_unknown_raw_event_name() -> None:
    with pytest.raises(RuntimeExecutorError, match="unknown runtime event"):
        RuntimeEventBoundary.require_runtime_fact_event("runtime_magic_success")


def test_runtime_rejects_runtime_actor_that_matches_active_governance_seat_actor(
    runtime_actor_ref: ActorRef,
    model_execution_profile: ModelExecutionProfile,
) -> None:
    governance_seat = _seat(
        seat_ref="seat.governance.ceo",
        actor_ref=runtime_actor_ref,
        role_category=RoleCategory.GOVERNANCE,
        model_execution_profile=model_execution_profile,
    )
    execution_seat = _seat(
        seat_ref="seat.worker.backend",
        actor_ref="actor.worker.backend",
        role_category=RoleCategory.IMPLEMENTATION,
        model_execution_profile=model_execution_profile,
    )
    execution_package = _execution_package(
        seat_ref=execution_seat.seat_ref,
        model_execution_profile=model_execution_profile,
    )

    with pytest.raises(RuntimeExecutorError, match="active seat actor"):
        RuntimeEventBoundary.require_execution_actor_boundary(
            execution_package,
            _agent_team_projection(active_seats=(governance_seat, execution_seat)),
            runtime_actor_ref,
        )


def test_runtime_rejects_runtime_actor_that_matches_active_worker_seat_actor(
    runtime_actor_ref: ActorRef,
    model_execution_profile: ModelExecutionProfile,
) -> None:
    worker_seat = _seat(
        seat_ref="seat.worker.backend",
        actor_ref=runtime_actor_ref,
        role_category=RoleCategory.IMPLEMENTATION,
        model_execution_profile=model_execution_profile,
    )
    execution_package = _execution_package(
        seat_ref=worker_seat.seat_ref,
        model_execution_profile=model_execution_profile,
    )

    with pytest.raises(RuntimeExecutorError, match="active seat actor"):
        RuntimeEventBoundary.require_execution_actor_boundary(
            execution_package,
            _agent_team_projection(active_seats=(worker_seat,)),
            runtime_actor_ref,
        )


@pytest.mark.parametrize(
    "role_category",
    (
        RoleCategory.GOVERNANCE,
        RoleCategory.ARCHITECTURE,
        RoleCategory.AUDIT,
    ),
)
def test_runtime_rejects_execution_package_for_governance_architecture_or_audit_seat(
    role_category: RoleCategory,
    runtime_actor_ref: ActorRef,
    model_execution_profile: ModelExecutionProfile,
) -> None:
    blocked_seat = _seat(
        seat_ref=f"seat.{role_category.value}.default",
        actor_ref=f"actor.{role_category.value}.default",
        role_category=role_category,
        model_execution_profile=model_execution_profile,
    )
    execution_package = _execution_package(
        seat_ref=blocked_seat.seat_ref,
        model_execution_profile=model_execution_profile,
    )

    with pytest.raises(RuntimeExecutorError) as error_info:
        RuntimeEventBoundary.require_execution_actor_boundary(
            execution_package,
            _agent_team_projection(active_seats=(blocked_seat,)),
            runtime_actor_ref,
        )

    message = str(error_info.value)
    assert "role category" in message
    assert blocked_seat.seat_ref.value in message
    assert "implementation" in message
    assert "verification" in message
    assert "integration" in message


@pytest.mark.parametrize(
    "role_category",
    (
        RoleCategory.IMPLEMENTATION,
        RoleCategory.VERIFICATION,
        RoleCategory.INTEGRATION,
    ),
)
def test_runtime_accepts_execution_package_for_executable_seat_category(
    role_category: RoleCategory,
    runtime_actor_ref: ActorRef,
    model_execution_profile: ModelExecutionProfile,
) -> None:
    execution_seat = _seat(
        seat_ref=f"seat.{role_category.value}.default",
        actor_ref=f"actor.{role_category.value}.default",
        role_category=role_category,
        model_execution_profile=model_execution_profile,
    )
    execution_package = _execution_package(
        seat_ref=execution_seat.seat_ref,
        model_execution_profile=model_execution_profile,
    )

    RuntimeEventBoundary.require_execution_actor_boundary(
        execution_package,
        _agent_team_projection(active_seats=(execution_seat,)),
        runtime_actor_ref,
    )


def test_runtime_rejects_execution_package_targeting_inactive_seat_even_when_seat_exists(
    runtime_actor_ref: ActorRef,
    model_execution_profile: ModelExecutionProfile,
) -> None:
    inactive_worker_seat = _seat(
        seat_ref="seat.worker.inactive",
        actor_ref="actor.worker.inactive",
        role_category=RoleCategory.IMPLEMENTATION,
        model_execution_profile=model_execution_profile,
        lifecycle_status=SeatLifecycleStatus.DEACTIVATED,
    )
    active_worker_seat = _seat(
        seat_ref="seat.worker.active",
        actor_ref="actor.worker.active",
        role_category=RoleCategory.IMPLEMENTATION,
        model_execution_profile=model_execution_profile,
    )
    execution_package = _execution_package(
        seat_ref=inactive_worker_seat.seat_ref,
        model_execution_profile=model_execution_profile,
    )

    with pytest.raises(RuntimeExecutorError, match="active execution seat"):
        RuntimeEventBoundary.require_execution_actor_boundary(
            execution_package,
            _agent_team_projection(
                seats=(inactive_worker_seat, active_worker_seat),
                active_seats=(active_worker_seat,),
            ),
            runtime_actor_ref,
        )


def test_runtime_rejects_missing_active_execution_seat(
    runtime_actor_ref: ActorRef,
    model_execution_profile: ModelExecutionProfile,
) -> None:
    active_worker_seat = _seat(
        seat_ref="seat.worker.active",
        actor_ref="actor.worker.active",
        role_category=RoleCategory.IMPLEMENTATION,
        model_execution_profile=model_execution_profile,
    )
    execution_package = _execution_package(
        seat_ref=AgentSeatRef(value="seat.worker.missing"),
        model_execution_profile=model_execution_profile,
    )

    with pytest.raises(RuntimeExecutorError, match="active execution seat"):
        RuntimeEventBoundary.require_execution_actor_boundary(
            execution_package,
            _agent_team_projection(active_seats=(active_worker_seat,)),
            runtime_actor_ref,
        )
