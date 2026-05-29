from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Mapping

from boardroom_os.agents.profiles import ModelExecutionProfileId
from boardroom_os.agents.seat import (
    AgentSeat,
    AgentSeatRef,
    RoleCategory,
    SeatDemand,
    SeatLifecycleProjection,
    SeatLifecycleStatus,
)
from boardroom_os.agents.skills import CapabilityTag, RoleProfileId, SkillRef
from boardroom_os.events.record import EventRecord
from boardroom_os.events.types import (
    ActorRef,
    EventId,
    EventPayloadRef,
    EventType,
    ProjectRef,
)
from boardroom_os.graph.projection import TicketGraphProjector
from boardroom_os.graph.seat_assignment import (
    SeatAssignmentGraph,
    SeatAssignmentPayload,
    SeatAssignmentProjector,
)
from boardroom_os.graph.ticket import (
    TicketBlockedPayload,
    TicketCreatedPayload,
    TicketGraph,
    TicketId,
    TicketStatus,
)
from tests.proving.fixtures.tiny_fullstack_contracts import (
    TinyScenarioActiveContracts,
    build_tiny_scenario_active_contracts,
)

PROJECT_REF = ProjectRef(value="project-tiny-fullstack")
BASE_TIMESTAMP = datetime(2026, 5, 29, 9, 0, tzinfo=UTC)

TICKET_GOVERNANCE_ID = TicketId(value="ticket-tiny-governance")
TICKET_ARCHITECTURE_ID = TicketId(value="ticket-tiny-architecture")
TICKET_BACKEND_API_ID = TicketId(value="ticket-tiny-backend-api")
TICKET_FRONTEND_UI_ID = TicketId(value="ticket-tiny-frontend-ui")
TICKET_TESTS_ID = TicketId(value="ticket-tiny-tests")
TICKET_DOCS_RUN_MANIFEST_ID = TicketId(value="ticket-tiny-docs-run-manifest")
TICKET_CHECKER_ID = TicketId(value="ticket-tiny-checker")

SEAT_CEO_REF = AgentSeatRef(value="seat-tiny-ceo")
SEAT_ARCHITECT_REF = AgentSeatRef(value="seat-tiny-architect")
SEAT_WORKER_BACKEND_REF = AgentSeatRef(value="seat-tiny-worker-backend")
SEAT_WORKER_FRONTEND_REF = AgentSeatRef(value="seat-tiny-worker-frontend")
SEAT_WORKER_TESTS_REF = AgentSeatRef(value="seat-tiny-worker-tests")
SEAT_WORKER_DOCS_REF = AgentSeatRef(value="seat-tiny-worker-docs")
SEAT_CHECKER_REF = AgentSeatRef(value="seat-tiny-checker")


class TinyTicketGraphPayloadResolver:
    def __init__(
        self,
        *,
        ticket_created_payloads: Mapping[EventPayloadRef, TicketCreatedPayload],
        seat_assignment_payloads: Mapping[EventPayloadRef, SeatAssignmentPayload],
        ticket_blocked_payloads: Mapping[EventPayloadRef, TicketBlockedPayload] | None = None,
    ) -> None:
        self._ticket_created_payloads = dict(ticket_created_payloads)
        self._seat_assignment_payloads = dict(seat_assignment_payloads)
        self._ticket_blocked_payloads = dict(ticket_blocked_payloads or {})

    def resolve_ticket_created(
        self,
        payload_ref: EventPayloadRef,
    ) -> TicketCreatedPayload:
        return self._ticket_created_payloads[payload_ref]

    def resolve_ticket_blocked(
        self,
        payload_ref: EventPayloadRef,
    ) -> TicketBlockedPayload:
        return self._ticket_blocked_payloads[payload_ref]

    def resolve_seat_assignment(
        self,
        payload_ref: EventPayloadRef,
    ) -> SeatAssignmentPayload:
        return self._seat_assignment_payloads[payload_ref]

    def with_assignment_payload(
        self,
        payload_ref: EventPayloadRef,
        payload: SeatAssignmentPayload,
    ) -> "TinyTicketGraphPayloadResolver":
        assignment_payloads = dict(self._seat_assignment_payloads)
        assignment_payloads[payload_ref] = payload
        return TinyTicketGraphPayloadResolver(
            ticket_created_payloads=self._ticket_created_payloads,
            seat_assignment_payloads=assignment_payloads,
            ticket_blocked_payloads=self._ticket_blocked_payloads,
        )


@dataclass(frozen=True)
class TinyTicketGraphFixture:
    contracts: TinyScenarioActiveContracts
    seats: tuple[AgentSeat, ...]
    seat_projection: SeatLifecycleProjection
    payload_resolver: TinyTicketGraphPayloadResolver
    ticket_graph_projector: TicketGraphProjector
    seat_assignment_projector: SeatAssignmentProjector
    ticket_graph: TicketGraph
    seat_assignment_graph: SeatAssignmentGraph
    ticket_ids: tuple[TicketId, ...]
    implementation_ticket_ids: tuple[TicketId, ...]
    ticket_payloads_by_id: Mapping[TicketId, TicketCreatedPayload]
    ticket_payloads_by_ref: Mapping[EventPayloadRef, TicketCreatedPayload]
    seat_assignment_payloads_by_ref: Mapping[EventPayloadRef, SeatAssignmentPayload]
    ticket_payload_refs_by_id: Mapping[TicketId, EventPayloadRef]
    assignment_payload_refs_by_ticket_id: Mapping[TicketId, EventPayloadRef]
    ticket_created_events: tuple[EventRecord, ...]
    seat_assignment_events: tuple[EventRecord, ...]
    events: tuple[EventRecord, ...]

    def build_seat_assignment_projector(
        self,
        payload_resolver: TinyTicketGraphPayloadResolver,
    ) -> SeatAssignmentProjector:
        return SeatAssignmentProjector(
            ticket_projector=TicketGraphProjector(payload_resolver),
            payload_resolver=payload_resolver,
            seat_projection=self.seat_projection,
        )

    def project_with_completed_dependency_nodes(
        self,
        completed_ticket_ids: tuple[TicketId, ...],
    ) -> SeatAssignmentGraph:
        completed = set(completed_ticket_ids)
        ticket_graph = TicketGraph.from_nodes(
            graph_version=self.seat_assignment_graph.graph_version + 1,
            nodes=tuple(
                node.model_copy(update={"status": TicketStatus.COMPLETED})
                if ticket_id in completed
                else node
                for ticket_id, node in self.seat_assignment_graph.nodes.items()
            ),
        )
        return SeatAssignmentGraph.from_ticket_graph(
            ticket_graph,
            seat_assignments=dict(self.seat_assignment_graph.seat_assignments),
            seat_blockers={},
        )


def build_tiny_ticket_graph_fixture() -> TinyTicketGraphFixture:
    contracts = build_tiny_scenario_active_contracts()
    seats = _active_seats()
    ticket_payloads_by_id = _ticket_payloads_by_id(contracts)
    ticket_payload_refs_by_id = {
        ticket_id: EventPayloadRef(value=f"payload:{ticket_id.value}:created")
        for ticket_id in ticket_payloads_by_id
    }
    assignment_payload_refs_by_ticket_id = {
        ticket_id: EventPayloadRef(value=f"payload:{ticket_id.value}:seat-assigned")
        for ticket_id in ticket_payloads_by_id
    }
    ticket_payloads_by_ref = {
        ticket_payload_refs_by_id[ticket_id]: payload
        for ticket_id, payload in ticket_payloads_by_id.items()
    }
    seat_assignment_payloads_by_ref = _seat_assignment_payloads_by_ref(
        assignment_payload_refs_by_ticket_id,
    )
    payload_resolver = TinyTicketGraphPayloadResolver(
        ticket_created_payloads=ticket_payloads_by_ref,
        seat_assignment_payloads=seat_assignment_payloads_by_ref,
    )
    ticket_created_events = _ticket_created_events(ticket_payload_refs_by_id)
    seat_assignment_events = _seat_assignment_events(assignment_payload_refs_by_ticket_id)
    events = ticket_created_events + seat_assignment_events
    seat_projection = SeatLifecycleProjection(
        graph_version=1,
        seats={seat.seat_ref: seat for seat in seats},
        active_seats={seat.seat_ref: seat for seat in seats},
        replacement_refs={},
    )
    ticket_graph_projector = TicketGraphProjector(payload_resolver)
    seat_assignment_projector = SeatAssignmentProjector(
        ticket_projector=ticket_graph_projector,
        payload_resolver=payload_resolver,
        seat_projection=seat_projection,
    )

    return TinyTicketGraphFixture(
        contracts=contracts,
        seats=seats,
        seat_projection=seat_projection,
        payload_resolver=payload_resolver,
        ticket_graph_projector=ticket_graph_projector,
        seat_assignment_projector=seat_assignment_projector,
        ticket_graph=ticket_graph_projector.project(events),
        seat_assignment_graph=seat_assignment_projector.project(events),
        ticket_ids=tuple(ticket_payloads_by_id),
        implementation_ticket_ids=(
            TICKET_BACKEND_API_ID,
            TICKET_FRONTEND_UI_ID,
            TICKET_TESTS_ID,
            TICKET_DOCS_RUN_MANIFEST_ID,
        ),
        ticket_payloads_by_id=ticket_payloads_by_id,
        ticket_payloads_by_ref=ticket_payloads_by_ref,
        seat_assignment_payloads_by_ref=seat_assignment_payloads_by_ref,
        ticket_payload_refs_by_id=ticket_payload_refs_by_id,
        assignment_payload_refs_by_ticket_id=assignment_payload_refs_by_ticket_id,
        ticket_created_events=ticket_created_events,
        seat_assignment_events=seat_assignment_events,
        events=events,
    )


def _active_seats() -> tuple[AgentSeat, ...]:
    return (
        _seat(
            seat_ref=SEAT_CEO_REF,
            actor_ref="actor.tiny.ceo",
            role_profile_ref="role.governance.ceo",
            role_category=RoleCategory.GOVERNANCE,
            capability_tags=("team.governance",),
            model_execution_profile_ref="model.governance.ceo",
            skill_refs=("skill.governance.ceo",),
        ),
        _seat(
            seat_ref=SEAT_ARCHITECT_REF,
            actor_ref="actor.tiny.architect",
            role_profile_ref="role.architecture.lead",
            role_category=RoleCategory.ARCHITECTURE,
            capability_tags=("architecture.solution",),
            model_execution_profile_ref="model.architecture.lead",
            skill_refs=("skill.architecture.lead",),
        ),
        _seat(
            seat_ref=SEAT_WORKER_BACKEND_REF,
            actor_ref="actor.tiny.worker.backend",
            role_profile_ref="role.implementation.backend",
            role_category=RoleCategory.IMPLEMENTATION,
            capability_tags=("task.implementation", "surface.backend", "surface.persistence"),
            model_execution_profile_ref="model.implementation.backend",
            skill_refs=("skill.implementation.backend",),
        ),
        _seat(
            seat_ref=SEAT_WORKER_FRONTEND_REF,
            actor_ref="actor.tiny.worker.frontend",
            role_profile_ref="role.implementation.frontend",
            role_category=RoleCategory.IMPLEMENTATION,
            capability_tags=("task.implementation", "surface.frontend"),
            model_execution_profile_ref="model.implementation.frontend",
            skill_refs=("skill.implementation.frontend",),
        ),
        _seat(
            seat_ref=SEAT_WORKER_TESTS_REF,
            actor_ref="actor.tiny.worker.tests",
            role_profile_ref="role.implementation.tests",
            role_category=RoleCategory.IMPLEMENTATION,
            capability_tags=("task.implementation", "surface.tests"),
            model_execution_profile_ref="model.implementation.tests",
            skill_refs=("skill.implementation.tests",),
        ),
        _seat(
            seat_ref=SEAT_WORKER_DOCS_REF,
            actor_ref="actor.tiny.worker.docs",
            role_profile_ref="role.implementation.docs",
            role_category=RoleCategory.IMPLEMENTATION,
            capability_tags=("task.implementation", "surface.docs", "surface.run_manifest"),
            model_execution_profile_ref="model.implementation.docs",
            skill_refs=("skill.implementation.docs",),
        ),
        _seat(
            seat_ref=SEAT_CHECKER_REF,
            actor_ref="actor.tiny.checker",
            role_profile_ref="role.verification.checker",
            role_category=RoleCategory.VERIFICATION,
            capability_tags=("quality.verification",),
            model_execution_profile_ref="model.verification.checker",
            skill_refs=("skill.verification.checker",),
        ),
    )


def _seat(
    *,
    seat_ref: AgentSeatRef,
    actor_ref: str,
    role_profile_ref: str,
    role_category: RoleCategory,
    capability_tags: tuple[str, ...],
    model_execution_profile_ref: str,
    skill_refs: tuple[str, ...],
) -> AgentSeat:
    return AgentSeat(
        seat_ref=seat_ref,
        actor_ref=ActorRef(value=actor_ref),
        project_ref=PROJECT_REF,
        role_profile_ref=RoleProfileId(value=role_profile_ref),
        role_category=role_category,
        capability_tags=tuple(CapabilityTag(value=value) for value in capability_tags),
        model_execution_profile_ref=ModelExecutionProfileId(
            value=model_execution_profile_ref,
        ),
        skill_refs=tuple(SkillRef(value=value) for value in skill_refs),
        context_budget_tokens=8192,
        lifecycle_status=SeatLifecycleStatus.ACTIVE,
    )


def _ticket_payloads_by_id(
    contracts: TinyScenarioActiveContracts,
) -> dict[TicketId, TicketCreatedPayload]:
    all_acceptance_refs = _acceptance_refs_for(contracts)
    all_surface_refs = _source_surface_refs_for(contracts)
    all_obligation_refs = _obligation_refs_for(contracts)
    api_refs = contracts.required_acceptance_refs_by_category["api"]
    persistence_refs = contracts.required_acceptance_refs_by_category["persistence"]
    ui_refs = contracts.required_acceptance_refs_by_category["ui"]
    run_test_refs = contracts.required_acceptance_refs_by_category["run_test"]

    return {
        TICKET_GOVERNANCE_ID: _ticket_payload(
            ticket_id=TICKET_GOVERNANCE_ID,
            purpose="Govern tiny scenario contract-first execution boundary.",
            role_category=RoleCategory.GOVERNANCE,
            capability_tags=("team.governance",),
            acceptance_refs=all_acceptance_refs,
            source_surface_refs=all_surface_refs,
            evidence_obligations=all_obligation_refs,
            allowed_write_set=("00-boardroom/**",),
        ),
        TICKET_ARCHITECTURE_ID: _ticket_payload(
            ticket_id=TICKET_ARCHITECTURE_ID,
            purpose="Plan tiny package surfaces and implementation sequence.",
            role_category=RoleCategory.ARCHITECTURE,
            capability_tags=("architecture.solution",),
            acceptance_refs=all_acceptance_refs,
            source_surface_refs=all_surface_refs,
            evidence_obligations=all_obligation_refs,
            allowed_write_set=("10-project/package-contract.json", "30-audit/ticket-graph.json"),
        ),
        TICKET_BACKEND_API_ID: _ticket_payload(
            ticket_id=TICKET_BACKEND_API_ID,
            purpose="Implement backend API and SQLite persistence surfaces.",
            role_category=RoleCategory.IMPLEMENTATION,
            capability_tags=("task.implementation", "surface.backend", "surface.persistence"),
            acceptance_refs=api_refs + persistence_refs,
            source_surface_refs=("backend-api", "persistence", "tests"),
            evidence_obligations=_obligation_refs_for(
                contracts,
                acceptance_refs=api_refs + persistence_refs,
            ),
            allowed_write_set=("backend/app.py", "backend/db.py"),
        ),
        TICKET_FRONTEND_UI_ID: _ticket_payload(
            ticket_id=TICKET_FRONTEND_UI_ID,
            purpose="Implement frontend UI that calls the backend API.",
            role_category=RoleCategory.IMPLEMENTATION,
            capability_tags=("task.implementation", "surface.frontend"),
            acceptance_refs=ui_refs,
            source_surface_refs=("frontend-ui", "tests"),
            evidence_obligations=_obligation_refs_for(contracts, acceptance_refs=ui_refs),
            allowed_write_set=("frontend/index.html", "frontend/app.js"),
        ),
        TICKET_TESTS_ID: _ticket_payload(
            ticket_id=TICKET_TESTS_ID,
            purpose="Implement API, persistence, and frontend-backend tests.",
            role_category=RoleCategory.IMPLEMENTATION,
            capability_tags=("task.implementation", "surface.tests"),
            acceptance_refs=api_refs + persistence_refs + ui_refs + run_test_refs,
            source_surface_refs=(
                "backend-api",
                "persistence",
                "frontend-ui",
                "tests",
                "run-manifest",
            ),
            evidence_obligations=_obligation_refs_for(
                contracts,
                acceptance_refs=api_refs + persistence_refs + ui_refs + run_test_refs,
            ),
            allowed_write_set=("backend/tests/test_api.py", "tests/integration/test_frontend_backend.py"),
        ),
        TICKET_DOCS_RUN_MANIFEST_ID: _ticket_payload(
            ticket_id=TICKET_DOCS_RUN_MANIFEST_ID,
            purpose="Create docs and run manifest for the tiny package.",
            role_category=RoleCategory.IMPLEMENTATION,
            capability_tags=("task.implementation", "surface.docs", "surface.run_manifest"),
            acceptance_refs=run_test_refs,
            source_surface_refs=("docs", "run-manifest", "tests"),
            evidence_obligations=_obligation_refs_for(
                contracts,
                acceptance_refs=run_test_refs,
            ),
            allowed_write_set=("README.md", "AGENTS.md", "run-manifest.json"),
        ),
        TICKET_CHECKER_ID: _ticket_payload(
            ticket_id=TICKET_CHECKER_ID,
            purpose="Verify implementation evidence readiness before closeout.",
            role_category=RoleCategory.VERIFICATION,
            capability_tags=("quality.verification",),
            depends_on=(
                TICKET_BACKEND_API_ID,
                TICKET_FRONTEND_UI_ID,
                TICKET_TESTS_ID,
                TICKET_DOCS_RUN_MANIFEST_ID,
            ),
            acceptance_refs=all_acceptance_refs,
            source_surface_refs=all_surface_refs,
            evidence_obligations=all_obligation_refs,
            allowed_write_set=("20-evidence/**",),
        ),
    }


def _ticket_payload(
    *,
    ticket_id: TicketId,
    purpose: str,
    role_category: RoleCategory,
    capability_tags: tuple[str, ...],
    acceptance_refs: tuple[str, ...],
    source_surface_refs: tuple[str, ...],
    evidence_obligations: tuple[str, ...],
    allowed_write_set: tuple[str, ...],
    depends_on: tuple[TicketId, ...] = (),
) -> TicketCreatedPayload:
    return TicketCreatedPayload(
        ticket_id=ticket_id,
        purpose=purpose,
        seat_demand=SeatDemand(
            required_role_category=role_category,
            required_capability_tags=tuple(
                CapabilityTag(value=value)
                for value in capability_tags
            ),
        ),
        depends_on=depends_on,
        acceptance_refs=acceptance_refs,
        source_surface_refs=source_surface_refs,
        evidence_obligations=evidence_obligations,
        allowed_read_refs=(
            "contract:acceptance-contract-tiny-fullstack",
            "contract:package-contract-tiny-fullstack",
        ),
        allowed_write_set=allowed_write_set,
        attempt_count=0,
    )


def _seat_assignment_payloads_by_ref(
    assignment_payload_refs_by_ticket_id: Mapping[TicketId, EventPayloadRef],
) -> dict[EventPayloadRef, SeatAssignmentPayload]:
    seat_refs_by_ticket_id = {
        TICKET_GOVERNANCE_ID: SEAT_CEO_REF,
        TICKET_ARCHITECTURE_ID: SEAT_ARCHITECT_REF,
        TICKET_BACKEND_API_ID: SEAT_WORKER_BACKEND_REF,
        TICKET_FRONTEND_UI_ID: SEAT_WORKER_FRONTEND_REF,
        TICKET_TESTS_ID: SEAT_WORKER_TESTS_REF,
        TICKET_DOCS_RUN_MANIFEST_ID: SEAT_WORKER_DOCS_REF,
        TICKET_CHECKER_ID: SEAT_CHECKER_REF,
    }
    return {
        assignment_payload_refs_by_ticket_id[ticket_id]: SeatAssignmentPayload(
            ticket_id=ticket_id,
            seat_ref=seat_ref,
        )
        for ticket_id, seat_ref in seat_refs_by_ticket_id.items()
    }


def _ticket_created_events(
    ticket_payload_refs_by_id: Mapping[TicketId, EventPayloadRef],
) -> tuple[EventRecord, ...]:
    return tuple(
        _event(
            event_id=f"evt:{ticket_id.value}:created",
            event_type=EventType.TICKET_CREATED,
            payload_ref=payload_ref,
            graph_version=index,
            actor_ref=SEAT_ARCHITECT_REF.value,
        )
        for index, (ticket_id, payload_ref) in enumerate(
            ticket_payload_refs_by_id.items(),
            start=1,
        )
    )


def _seat_assignment_events(
    assignment_payload_refs_by_ticket_id: Mapping[TicketId, EventPayloadRef],
) -> tuple[EventRecord, ...]:
    return tuple(
        _event(
            event_id=f"evt:{ticket_id.value}:seat-assigned",
            event_type=EventType.SEAT_ASSIGNED,
            payload_ref=payload_ref,
            graph_version=index,
            actor_ref=SEAT_CEO_REF.value,
        )
        for index, (ticket_id, payload_ref) in enumerate(
            assignment_payload_refs_by_ticket_id.items(),
            start=len(assignment_payload_refs_by_ticket_id) + 1,
        )
    )


def _event(
    *,
    event_id: str,
    event_type: EventType,
    payload_ref: EventPayloadRef,
    graph_version: int,
    actor_ref: str,
) -> EventRecord:
    return EventRecord(
        event_id=EventId(value=event_id),
        event_type=event_type,
        project_ref=PROJECT_REF,
        actor_ref=ActorRef(value=actor_ref),
        timestamp=BASE_TIMESTAMP,
        graph_version=graph_version,
        payload_refs=(payload_ref,),
    )


def _acceptance_refs_for(
    contracts: TinyScenarioActiveContracts,
) -> tuple[str, ...]:
    return tuple(
        acceptance_ref.value
        for acceptance_ref in contracts.contract_gate.acceptance_refs
    )


def _source_surface_refs_for(
    contracts: TinyScenarioActiveContracts,
) -> tuple[str, ...]:
    return tuple(
        source_surface_ref.value
        for source_surface_ref in contracts.contract_gate.source_surface_refs
    )


def _obligation_refs_for(
    contracts: TinyScenarioActiveContracts,
    *,
    acceptance_refs: tuple[str, ...] | None = None,
) -> tuple[str, ...]:
    allowed_acceptance_refs = set(acceptance_refs) if acceptance_refs is not None else None
    return tuple(
        obligation.evidence_obligation_id.value
        for obligation in contracts.contract_gate.evidence_obligations
        if allowed_acceptance_refs is None
        or any(ref.value in allowed_acceptance_refs for ref in obligation.acceptance_refs)
    )
