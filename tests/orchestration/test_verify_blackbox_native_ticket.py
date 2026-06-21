from __future__ import annotations

from datetime import UTC, datetime

from boardroom_os.agents.categories import RoleCategory
from boardroom_os.agents.policy import RoleProfileProjection
from boardroom_os.agents.profiles import ModelExecutionProfileId, ModelExecutionProfileRegistry, RoleProfile
from boardroom_os.agents.seat import (
    AgentSeat,
    AgentSeatRef,
    SeatDemand,
    SeatLifecycleProjection,
    SeatLifecycleStatus,
)
from boardroom_os.agents.skills import CapabilityTag, RoleProfileId, SkillRef
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
from boardroom_os.events.record import EventRecord
from boardroom_os.events.types import (
    ActorRef,
    EventId,
    EventPayloadRef,
    EventType,
    ProjectRef,
)
from boardroom_os.execution.compiler import (
    ExecutionPackageCompiler,
    ExecutionPackageCompilerInput,
    ExecutionWorkspaceContext,
    VerificationExecutionContext,
)
from boardroom_os.execution.package import ContextRef
from boardroom_os.graph.projection import TicketGraphProjector
from boardroom_os.graph.seat_assignment import SeatAssignmentPayload, SeatAssignmentProjector
from boardroom_os.graph.ticket import TicketCreatedPayload, TicketId
from boardroom_os.orchestration.verification import (
    VerificationMilestoneRequest,
    VerifyBlackboxTicketIntent,
)
from tests.fixtures.execution.compiler import _model_profile
from tests.fixtures.execution.role_prompt_hooks import (
    baseline_role_prompt_hook_fields_for_category,
    baseline_role_prompt_hook_registry,
)


BASE_TIMESTAMP = datetime(2026, 6, 21, 12, 0, tzinfo=UTC)
PROJECT_REF = ProjectRef(value="project.tiny-fullstack")
TICKET_ID = TicketId(value="ticket.verify-blackbox.generated")
ACCEPTANCE_REF = AcceptanceRef(value="AC-LIVE-BLACKBOX-001")
SOURCE_SURFACE_REF = SourceSurfaceRef(value="surface.run-manifest")
EVIDENCE_OBLIGATION_REF = EvidenceObligationRef(value="evidence.live-blackbox")
RAW_MANIFEST_CONTEXT_REF = ContextRef(value="context.run-manifest.generated.raw")
SKELETON_SUMMARY_REF = ContextRef(value="context.run-manifest.generated.skeleton")
WORKSPACE_CONTEXT_REF = ContextRef(value="context.workspace.tiny-fullstack")
SHARED_WORKSPACE_CONTEXT_REF = ContextRef(value="context.workspace.shared")


class InMemoryResolver:
    def __init__(
        self,
        *,
        created_payload: TicketCreatedPayload,
        assignment_payload: SeatAssignmentPayload | None = None,
    ) -> None:
        self.created_payload = created_payload
        self.assignment_payload = assignment_payload or SeatAssignmentPayload(
            ticket_id=TICKET_ID,
            seat_ref=AgentSeatRef(value="seat.tester.blackbox"),
        )

    def resolve_ticket_created(self, payload_ref: EventPayloadRef) -> TicketCreatedPayload:
        return self.created_payload

    def resolve_ticket_blocked(self, payload_ref: EventPayloadRef):
        raise KeyError(payload_ref.value)

    def resolve_seat_assignment(self, payload_ref: EventPayloadRef) -> SeatAssignmentPayload:
        return self.assignment_payload


def test_verify_blackbox_intent_builds_ticket_created_payload() -> None:
    request = _verification_request()

    intent = VerifyBlackboxTicketIntent.from_request(request)
    payload = intent.to_ticket_created_payload()

    assert payload.ticket_id == TICKET_ID
    assert payload.purpose == "verify-blackbox"
    assert payload.seat_demand == SeatDemand(
        required_role_category=RoleCategory.VERIFICATION,
        required_capability_tags=(CapabilityTag(value="task.verify-blackbox"),),
    )
    assert payload.acceptance_refs == (ACCEPTANCE_REF.value,)
    assert payload.source_surface_refs == (SOURCE_SURFACE_REF.value,)
    assert payload.evidence_obligations == (EVIDENCE_OBLIGATION_REF.value,)
    assert RAW_MANIFEST_CONTEXT_REF.value in payload.allowed_read_refs
    assert "acceptance-contract-001" in payload.allowed_read_refs
    assert "package-contract-001" in payload.allowed_read_refs
    assert WORKSPACE_CONTEXT_REF.value in payload.allowed_read_refs
    assert SHARED_WORKSPACE_CONTEXT_REF.value in payload.allowed_read_refs
    assert "docs/README.md" in payload.allowed_read_refs
    assert payload.allowed_write_set == ()


def test_verify_blackbox_ticket_enters_ready_queue_through_ticket_graph() -> None:
    payload = VerifyBlackboxTicketIntent.from_request(
        _verification_request()
    ).to_ticket_created_payload()
    resolver = InMemoryResolver(created_payload=payload)

    ticket_graph = TicketGraphProjector(payload_resolver=resolver).project(
        (_ticket_created_event(),)
    )

    assert TICKET_ID in ticket_graph.ready_queue
    assert ticket_graph.nodes[TICKET_ID].purpose == "verify-blackbox"


def test_verify_blackbox_execution_package_is_compiled_from_graph_assignment() -> None:
    execution_package = _compile_verify_blackbox_execution_package()

    assert execution_package.ticket_ref == TICKET_ID
    assert execution_package.seat_ref == AgentSeatRef(value="seat.tester.blackbox")
    assert execution_package.allowed_write_set == ()
    assert RAW_MANIFEST_CONTEXT_REF in execution_package.context_refs
    assert SKELETON_SUMMARY_REF in execution_package.context_refs
    assert ContextRef(value="docs/README.md") in execution_package.context_refs
    assert ContextRef(value="docs/RUNBOOK.md") in execution_package.context_refs
    assert ContextRef(value="failure.raw-run-error") in execution_package.context_refs


def _compile_verify_blackbox_execution_package():
    seat_assignment_graph = _seat_assignment_graph_from_events()

    return ExecutionPackageCompiler().compile(
        ExecutionPackageCompilerInput.model_construct(
            ticket_ref=TICKET_ID,
            seat_assignment_graph=seat_assignment_graph,
            agent_team_projection=_agent_team_projection(),
            acceptance_contract=_acceptance_contract(),
            package_contract=_package_contract(),
            evidence_obligations=(_evidence_obligation(),),
            model_execution_profiles=ModelExecutionProfileRegistry.from_profiles(
                _model_profile(model_execution_profile_id="model.tester.blackbox")
            ),
            role_prompt_hook_registry=baseline_role_prompt_hook_registry(),
            workspace_context=ExecutionWorkspaceContext(
                workspace_ref=WORKSPACE_CONTEXT_REF,
                package_root="10-project",
                context_refs=(SHARED_WORKSPACE_CONTEXT_REF,),
            ),
            verification_context=VerificationExecutionContext(
                raw_manifest_context_ref=RAW_MANIFEST_CONTEXT_REF,
                skeleton_summary_ref=SKELETON_SUMMARY_REF,
                package_contract_ref=ContextRef(value="package-contract-001"),
                acceptance_contract_ref=ContextRef(value="acceptance-contract-001"),
                project_doc_refs=(
                    ContextRef(value="docs/README.md"),
                    ContextRef(value="docs/RUNBOOK.md"),
                ),
                source_surface_refs=(ContextRef(value=SOURCE_SURFACE_REF.value),),
                observed_failure_refs=(ContextRef(value="failure.raw-run-error"),),
            ),
        )
    )


def _verification_request() -> VerificationMilestoneRequest:
    return VerificationMilestoneRequest(
        ticket_id=TICKET_ID,
        raw_manifest_context_ref=RAW_MANIFEST_CONTEXT_REF,
        skeleton_summary_ref=SKELETON_SUMMARY_REF,
        acceptance_refs=(ACCEPTANCE_REF,),
        acceptance_contract_ref=ContextRef(value="acceptance-contract-001"),
        package_contract_ref=ContextRef(value="package-contract-001"),
        workspace_context_refs=(
            WORKSPACE_CONTEXT_REF,
            SHARED_WORKSPACE_CONTEXT_REF,
        ),
        source_surface_refs=(SOURCE_SURFACE_REF,),
        evidence_obligation_refs=(EVIDENCE_OBLIGATION_REF,),
        project_doc_refs=(
            ContextRef(value="docs/README.md"),
            ContextRef(value="docs/RUNBOOK.md"),
        ),
        observed_failure_refs=(ContextRef(value="failure.raw-run-error"),),
    )


def _seat_assignment_graph_from_events(
    *,
    assign: bool = True,
    ticket_payload: TicketCreatedPayload | None = None,
):
    payload = ticket_payload or VerifyBlackboxTicketIntent.from_request(
        _verification_request()
    ).to_ticket_created_payload()
    resolver = InMemoryResolver(created_payload=payload)
    events = (_ticket_created_event(), _seat_assigned_event()) if assign else (_ticket_created_event(),)
    return SeatAssignmentProjector(
        ticket_projector=TicketGraphProjector(resolver),
        payload_resolver=resolver,
        seat_projection=_seat_projection(),
    ).project(events)


def _ticket_created_event() -> EventRecord:
    return EventRecord(
        event_id=EventId(value="evt.verify-blackbox.created"),
        event_type=EventType.TICKET_CREATED,
        project_ref=PROJECT_REF,
        actor_ref=ActorRef(value="seat.ceo"),
        timestamp=BASE_TIMESTAMP,
        graph_version=1,
        payload_refs=(EventPayloadRef(value="payload.verify-blackbox.created"),),
    )


def _seat_assigned_event() -> EventRecord:
    return EventRecord(
        event_id=EventId(value="evt.verify-blackbox.assigned"),
        event_type=EventType.SEAT_ASSIGNED,
        project_ref=PROJECT_REF,
        actor_ref=ActorRef(value="seat.ceo"),
        timestamp=BASE_TIMESTAMP,
        graph_version=2,
        payload_refs=(EventPayloadRef(value="payload.verify-blackbox.assigned"),),
    )


def _seat_projection() -> SeatLifecycleProjection:
    seat = _tester_seat()
    return SeatLifecycleProjection(
        graph_version=2,
        seats={seat.seat_ref: seat},
        active_seats={seat.seat_ref: seat},
        replacement_refs={},
    )


def _tester_seat() -> AgentSeat:
    return AgentSeat(
        seat_ref=AgentSeatRef(value="seat.tester.blackbox"),
        actor_ref=ActorRef(value="actor.tester.blackbox"),
        project_ref=PROJECT_REF,
        role_profile_ref=RoleProfileId(value="role.tester.blackbox"),
        role_category=RoleCategory.VERIFICATION,
        capability_tags=(CapabilityTag(value="task.verify-blackbox"),),
        model_execution_profile_ref=ModelExecutionProfileId(value="model.tester.blackbox"),
        skill_refs=(SkillRef(value="skill.blackbox.verification"),),
        context_budget_tokens=8192,
        lifecycle_status=SeatLifecycleStatus.ACTIVE,
    )


def _agent_team_projection() -> AgentTeamProjection:
    seat = _tester_seat()
    return AgentTeamProjection(
        graph_version=2,
        role_profiles=RoleProfileProjection(
            profiles=(
                RoleProfile(
                    role_profile_id=RoleProfileId(value="role.tester.blackbox"),
                    role_category=RoleCategory.VERIFICATION,
                    role_name="Blackbox Tester",
                    responsibilities=("Plan blackbox verification from contracts.",),
                    capability_tags=(CapabilityTag(value="task.verify-blackbox"),),
                    input_contracts=(ContractId(value="contract.execution.package"),),
                    output_contracts=(ContractId(value="contract.blackbox.plan"),),
                    forbidden_actions=("Do not write implementation files.",),
                    **baseline_role_prompt_hook_fields_for_category(
                        RoleCategory.VERIFICATION
                    ),
                ),
            )
        ),
        seat_lifecycle=SeatLifecycleProjection(
            graph_version=2,
            seats={seat.seat_ref: seat},
            active_seats={seat.seat_ref: seat},
            replacement_refs={},
        ),
    )


def _acceptance_contract() -> AcceptanceContract:
    return AcceptanceContract.model_construct(
        acceptance_contract_id=ContractId(value="acceptance-contract-001"),
        project_charter_ref=ContractId(value="charter-001"),
        status=ContractStatus.active(),
        criteria=(
            AcceptanceCriterion(
                acceptance_ref=ACCEPTANCE_REF,
                statement="Generated package behavior is verified through blackbox facts.",
                evidence_required=(EvidenceRequirement(value="live_blackbox_integration"),),
                blocking=True,
                source_surface_refs=(SOURCE_SURFACE_REF,),
                verification_strategy=VerificationStrategy(value="live_blackbox"),
            ),
        ),
    )


def _package_contract() -> PackageContract:
    return PackageContract(
        package_contract_id=ContractId(value="package-contract-001"),
        project_charter_ref=ContractId(value="charter-001"),
        package_root="10-project",
        project_type=PackageProjectType.SOFTWARE,
        source_surfaces=(
            SourceSurface(
                source_surface_ref=SOURCE_SURFACE_REF,
                name="Run manifest surface",
                paths=("00-boardroom/generated-run-manifest.json",),
                owned_by=OwnerSeatRef(value="tester.blackbox"),
                acceptance_refs=(ACCEPTANCE_REF,),
                required_tests=(RequiredTestRef(value="test.live-blackbox"),),
            ),
        ),
        run_commands=(
            PackageCommand(
                command_id=ContractId(value="run.backend"),
                label="Run backend",
                command=("python", "-m", "app"),
                cwd=".",
            ),
        ),
        test_commands=(
            PackageCommand(
                command_id=ContractId(value="test.live-blackbox"),
                label="Run live blackbox checks",
                command=("pytest", "tests/live"),
                cwd=".",
            ),
        ),
        integration_boundaries=(IntegrationBoundary(value="backend-http-api"),),
        docs_required=False,
        closeout_required=True,
    )


def _evidence_obligation() -> EvidenceObligation:
    return EvidenceObligation(
        evidence_obligation_id=EVIDENCE_OBLIGATION_REF,
        acceptance_refs=(ACCEPTANCE_REF,),
        source_surface_refs=(SOURCE_SURFACE_REF,),
        required_artifact_type=RequiredArtifactType(value="live_blackbox_integration"),
        required_verifier=RequiredVerifier(value="live_blackbox"),
        blocking=True,
    )
