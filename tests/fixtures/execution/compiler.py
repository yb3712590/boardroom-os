from boardroom_os.agents.categories import RoleCategory
from boardroom_os.agents.policy import RoleProfileProjection
from boardroom_os.agents.profiles import ModelExecutionProfile, ModelExecutionProfileRegistry, RoleProfile
from boardroom_os.agents.seat import (
    AgentSeat,
    AgentSeatRef,
    SeatDemand,
    SeatLifecycleProjection,
    SeatLifecycleStatus,
)
from boardroom_os.agents.skills import CapabilityTag, SkillRef
from boardroom_os.agents.team import AgentTeamProjection
from boardroom_os.contracts.acceptance import (
    AcceptanceContract,
    AcceptanceCriterion,
    EvidenceRequirement,
    VerificationStrategy,
)
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
    ContractStatus,
    EvidenceObligationRef,
    SourceSurfaceRef,
)
from boardroom_os.events.types import ActorRef, ProjectRef
from boardroom_os.execution.compiler import (
    ExecutionPackageCompiler,
    ExecutionPackageCompilerError,
    ExecutionPackageCompilerInput,
    ExecutionWorkspaceContext,
)
from boardroom_os.execution.package import ContextRef
from boardroom_os.graph.seat_assignment import SeatAssignmentGraph
from boardroom_os.graph.ticket import TicketId, TicketNode, TicketStatus

PROJECT_REF = ProjectRef(value="project.boardroom-os")
DEFAULT_TICKET_ID = TicketId(value="ticket.backend")
DEFAULT_ACCEPTANCE_REF = AcceptanceRef(value="AC-BACKEND-001")
DEFAULT_SOURCE_SURFACE_REF = SourceSurfaceRef(value="surface.backend")
DEFAULT_EVIDENCE_OBLIGATION_REF = EvidenceObligationRef(value="evidence.backend.patch")
DEFAULT_REQUIRED_TEST_REF = RequiredTestRef(value="test.pytest.backend")
DEFAULT_SEAT_CAPABILITY = CapabilityTag(value="task.implementation")


def _role_profile(
    *,
    role_profile_id: str = "role.worker.backend",
    capability_tags: tuple[CapabilityTag, ...] = (DEFAULT_SEAT_CAPABILITY,),
    forbidden_actions: tuple[str, ...] = ("Do not bypass required tests.",),
) -> RoleProfile:
    return RoleProfile(
        role_profile_id=role_profile_id,
        role_category=RoleCategory.IMPLEMENTATION,
        role_name="Backend Worker",
        responsibilities=("Implement backend changes.",),
        capability_tags=capability_tags,
        input_contracts=(ContractId(value="contract.execution.package"),),
        output_contracts=(ContractId(value="contract.work.product"),),
        forbidden_actions=forbidden_actions,
    )


def _seat(
    *,
    seat_ref: str = "seat.worker.backend",
    role_profile_ref: str = "role.worker.backend",
    capability_tags: tuple[CapabilityTag, ...] = (DEFAULT_SEAT_CAPABILITY,),
    model_execution_profile_ref: str = "model.worker.backend",
    lifecycle_status: SeatLifecycleStatus = SeatLifecycleStatus.ACTIVE,
) -> AgentSeat:
    return AgentSeat(
        seat_ref=seat_ref,
        actor_ref=ActorRef(value="actor.worker.backend"),
        project_ref=PROJECT_REF,
        role_profile_ref=role_profile_ref,
        role_category=RoleCategory.IMPLEMENTATION,
        capability_tags=capability_tags,
        model_execution_profile_ref=model_execution_profile_ref,
        skill_refs=(SkillRef(value="skill.worker.execute"),),
        context_budget_tokens=8192,
        lifecycle_status=lifecycle_status,
    )


def _model_profile(
    *,
    model_execution_profile_id: str = "model.worker.backend",
    fallback_policy_ref: str = "fallback.worker.record_failure",
) -> ModelExecutionProfile:
    return ModelExecutionProfile(
        model_execution_profile_id=model_execution_profile_id,
        provider="anthropic",
        model="claude-sonnet-4-6",
        reasoning_effort="medium",
        context_window=200000,
        temperature=0.2,
        tool_permissions=("filesystem.write",),
        fallback_policy_ref=ContractId(value=fallback_policy_ref),
    )


def _ticket(
    *,
    ticket_id: TicketId = DEFAULT_TICKET_ID,
    acceptance_refs: tuple[str, ...] = (DEFAULT_ACCEPTANCE_REF.value,),
    source_surface_refs: tuple[str, ...] = (DEFAULT_SOURCE_SURFACE_REF.value,),
    evidence_obligations: tuple[str, ...] = (DEFAULT_EVIDENCE_OBLIGATION_REF.value,),
    allowed_write_set: tuple[str, ...] = ("src/backend/app.py",),
    seat_demand: SeatDemand | None = None,
    status: TicketStatus = TicketStatus.READY,
) -> TicketNode:
    return TicketNode(
        ticket_id=ticket_id,
        purpose="Implement backend fail-closed behavior.",
        seat_demand=seat_demand
        or SeatDemand(
            required_role_category=RoleCategory.IMPLEMENTATION,
            required_capability_tags=(DEFAULT_SEAT_CAPABILITY,),
        ),
        depends_on=(),
        acceptance_refs=acceptance_refs,
        source_surface_refs=source_surface_refs,
        evidence_obligations=evidence_obligations,
        allowed_read_refs=("README.md",),
        allowed_write_set=allowed_write_set,
        attempt_count=0,
        status=status,
    )


def _seat_assignment_graph(
    *,
    ticket: TicketNode | None = None,
    graph_version: int = 7,
    ready_queue: tuple[TicketId, ...] | None = None,
    seat_assignments: dict[TicketId, str | AgentSeatRef] | None = None,
    seat_blockers: dict[TicketId, tuple[str, ...]] | None = None,
) -> SeatAssignmentGraph:
    resolved_ticket = ticket or _ticket()
    assignments = seat_assignments
    if assignments is None:
        assignments = {resolved_ticket.ticket_id: AgentSeatRef(value="seat.worker.backend")}
    return SeatAssignmentGraph(
        graph_version=graph_version,
        nodes={resolved_ticket.ticket_id: resolved_ticket},
        blocked_by={},
        ready_queue=ready_queue if ready_queue is not None else (resolved_ticket.ticket_id,),
        completed_nodes=(),
        seat_assignments={
            ticket_id: seat_ref
            if isinstance(seat_ref, AgentSeatRef)
            else AgentSeatRef(value=seat_ref)
            for ticket_id, seat_ref in assignments.items()
        },
        seat_blockers=seat_blockers or {},
    )


def _agent_team_projection(
    *,
    seat: AgentSeat | None = None,
    role_profiles: tuple[RoleProfile, ...] | None = None,
    graph_version: int = 7,
    active_seats: dict[str, AgentSeat] | None = None,
) -> AgentTeamProjection:
    resolved_seat = seat or _seat()
    resolved_role_profiles = role_profiles or (_role_profile(),)
    active = active_seats
    if active is None:
        active = {resolved_seat.seat_ref.value: resolved_seat}
    return AgentTeamProjection(
        graph_version=graph_version,
        role_profiles=RoleProfileProjection(profiles=resolved_role_profiles),
        seat_lifecycle=SeatLifecycleProjection(
            graph_version=graph_version,
            seats={resolved_seat.seat_ref: resolved_seat},
            active_seats={
                seat_ref: active_seat
                for seat_ref, active_seat in (
                    (resolved_seat.seat_ref, active.get(resolved_seat.seat_ref.value)),
                )
                if active_seat is not None
            },
            replacement_refs={},
        ),
    )


def _acceptance_contract(
    *,
    status: ContractStatus | None = None,
    criteria: tuple[AcceptanceCriterion, ...] | None = None,
) -> AcceptanceContract:
    resolved_criteria = criteria or (
        AcceptanceCriterion(
            acceptance_ref=DEFAULT_ACCEPTANCE_REF,
            statement="Backend implementation satisfies the blocking contract.",
            evidence_required=(EvidenceRequirement(value="source_patch"),),
            blocking=True,
            source_surface_refs=(DEFAULT_SOURCE_SURFACE_REF,),
            verification_strategy=VerificationStrategy(value="checker"),
        ),
    )
    return AcceptanceContract.model_construct(
        acceptance_contract_id=ContractId(value="acceptance-contract-001"),
        project_charter_ref=ContractId(value="charter-001"),
        status=status or ContractStatus.active(),
        criteria=resolved_criteria,
    )


def _source_surface(
    *,
    surface_ref: SourceSurfaceRef = DEFAULT_SOURCE_SURFACE_REF,
    acceptance_refs: tuple[AcceptanceRef, ...] = (DEFAULT_ACCEPTANCE_REF,),
    paths: tuple[str, ...] = ("src/backend/",),
    required_tests: tuple[RequiredTestRef, ...] = (DEFAULT_REQUIRED_TEST_REF,),
) -> SourceSurface:
    return SourceSurface(
        source_surface_ref=surface_ref,
        name="Backend Surface",
        paths=paths,
        owned_by=OwnerSeatRef(value="worker.backend"),
        acceptance_refs=acceptance_refs,
        required_tests=required_tests,
    )


def _command(
    *,
    command_id: str = DEFAULT_REQUIRED_TEST_REF.value,
    command: tuple[str, ...] = ("pytest", "tests/backend"),
) -> PackageCommand:
    return PackageCommand(
        command_id=ContractId(value=command_id),
        label="Run backend tests",
        command=command,
        cwd=".",
    )


def _package_contract(
    *,
    source_surfaces: tuple[SourceSurface, ...] | None = None,
    test_commands: tuple[PackageCommand, ...] | None = None,
) -> PackageContract:
    return PackageContract(
        package_contract_id=ContractId(value="package-contract-001"),
        project_charter_ref=ContractId(value="charter-001"),
        package_root="workspace/backend-service",
        project_type=PackageProjectType.SOFTWARE,
        source_surfaces=source_surfaces or (_source_surface(),),
        run_commands=(
            PackageCommand(
                command_id=ContractId(value="run.backend"),
                label="Run backend",
                command=("python", "-m", "backend"),
                cwd=".",
            ),
        ),
        test_commands=test_commands or (_command(),),
        integration_boundaries=(IntegrationBoundary(value="backend-http-api"),),
        docs_required=False,
        closeout_required=True,
    )


def _evidence_obligation(
    *,
    evidence_obligation_id: EvidenceObligationRef = DEFAULT_EVIDENCE_OBLIGATION_REF,
    acceptance_refs: tuple[AcceptanceRef, ...] = (DEFAULT_ACCEPTANCE_REF,),
    source_surface_refs: tuple[SourceSurfaceRef, ...] = (DEFAULT_SOURCE_SURFACE_REF,),
    required_artifact_type: str = "source_patch",
    blocking: bool = True,
) -> EvidenceObligation:
    return EvidenceObligation(
        evidence_obligation_id=evidence_obligation_id,
        acceptance_refs=acceptance_refs,
        source_surface_refs=source_surface_refs,
        required_artifact_type=RequiredArtifactType(value=required_artifact_type),
        required_verifier=RequiredVerifier(value="checker"),
        blocking=blocking,
    )


def _compiler_input(
    *,
    ticket_ref: TicketId = DEFAULT_TICKET_ID,
    seat_assignment_graph: SeatAssignmentGraph | None = None,
    agent_team_projection: AgentTeamProjection | None = None,
    acceptance_contract: AcceptanceContract | None = None,
    package_contract: PackageContract | None = None,
    evidence_obligations: tuple[EvidenceObligation, ...] | None = None,
    model_execution_profiles: ModelExecutionProfileRegistry | None = None,
    workspace_context: ExecutionWorkspaceContext | None = None,
) -> ExecutionPackageCompilerInput:
    return ExecutionPackageCompilerInput.model_construct(
        ticket_ref=ticket_ref,
        seat_assignment_graph=seat_assignment_graph or _seat_assignment_graph(),
        agent_team_projection=agent_team_projection or _agent_team_projection(),
        acceptance_contract=acceptance_contract or _acceptance_contract(),
        package_contract=package_contract or _package_contract(),
        evidence_obligations=evidence_obligations or (_evidence_obligation(),),
        model_execution_profiles=model_execution_profiles
        or ModelExecutionProfileRegistry.from_profiles(_model_profile()),
        workspace_context=workspace_context
        or ExecutionWorkspaceContext(
            workspace_ref=ContextRef(value="context.workspace.backend"),
            package_root="workspace/backend-service",
            context_refs=(ContextRef(value="context.workspace.shared"),),
        ),
    )


def _compile(**overrides: object):
    compiler = ExecutionPackageCompiler()
    return compiler.compile(_compiler_input(**overrides))
