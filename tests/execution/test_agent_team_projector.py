from datetime import UTC, datetime

from boardroom_os.agents.profiles import (
    ModelExecutionProfile,
    ModelExecutionProfileId,
    ModelExecutionProfileRegistry,
    RoleProfile,
)
from boardroom_os.agents.policy import BootstrapGovernanceAuthority
from boardroom_os.agents.seat import (
    AgentSeat,
    AgentSeatRef,
    RoleCategory,
    SeatLifecycleAction,
    SeatLifecycleEvent,
    SeatLifecycleStatus,
)
from boardroom_os.agents.skills import CapabilityTag, RoleProfileId, SkillRef
from boardroom_os.agents.team import AgentTeamPayloadResolver, AgentTeamProjector
from boardroom_os.contracts.types import ContractId
from boardroom_os.events.record import EventRecord
from boardroom_os.events.types import (
    ActorRef,
    EventId,
    EventPayloadRef,
    EventType,
    ProjectRef,
)
from tests.fixtures.execution.role_prompt_hooks import (
    baseline_role_prompt_hook_fields_for_category,
)

BASE_TIMESTAMP = datetime(2026, 5, 17, 18, 0, tzinfo=UTC)
PROJECT_REF = ProjectRef(value="project.boardroom-os")
BOOTSTRAP_ACTOR_REF = ActorRef(value="actor.bootstrap")
CEO_ACTOR_REF = ActorRef(value="actor.ceo")
WORKER_ACTOR_REF = ActorRef(value="actor.worker.backend")
CEO_SEAT_REF = AgentSeatRef(value="seat.governance.ceo.primary")
WORKER_SEAT_REF = AgentSeatRef(value="seat.worker.backend.primary")
CEO_ROLE_PROFILE_REF = RoleProfileId(value="role.governance.ceo")
WORKER_ROLE_PROFILE_REF = RoleProfileId(value="role.worker.backend")
CEO_MODEL_PROFILE_REF = ModelExecutionProfileId(value="model.governance.ceo")
WORKER_MODEL_PROFILE_REF = ModelExecutionProfileId(value="model.worker.backend")


class InMemoryAgentTeamPayloadResolver(AgentTeamPayloadResolver):
    def __init__(
        self,
        *,
        bootstrap_payloads: dict[str, BootstrapGovernanceAuthority] | None = None,
        role_profile_payloads: dict[str, object] | None = None,
        seat_lifecycle_payloads: dict[str, object] | None = None,
    ) -> None:
        self._bootstrap_payloads = bootstrap_payloads or {}
        self._role_profile_payloads = role_profile_payloads or {}
        self._seat_lifecycle_payloads = seat_lifecycle_payloads or {}

    def resolve_bootstrap_governance_authority(
        self,
        payload_ref: EventPayloadRef,
    ) -> BootstrapGovernanceAuthority:
        return self._bootstrap_payloads[payload_ref.value]

    def resolve_role_profile_change(self, payload_ref: EventPayloadRef) -> object:
        return self._role_profile_payloads[payload_ref.value]

    def resolve_seat_lifecycle_event(self, payload_ref: EventPayloadRef) -> object:
        return self._seat_lifecycle_payloads[payload_ref.value]


def _event(
    *,
    event_id: str,
    event_type: EventType,
    payload_ref: str,
    graph_version: int,
    actor_ref: ActorRef | str,
) -> EventRecord:
    return EventRecord(
        event_id=EventId(value=event_id),
        event_type=event_type,
        project_ref=PROJECT_REF,
        actor_ref=actor_ref if isinstance(actor_ref, ActorRef) else ActorRef(value=actor_ref),
        timestamp=BASE_TIMESTAMP,
        graph_version=graph_version,
        payload_refs=(EventPayloadRef(value=payload_ref),),
    )


def _bootstrap_authority() -> BootstrapGovernanceAuthority:
    return BootstrapGovernanceAuthority(
        authority_scope=("role_profile_write", "seat_lifecycle_write")
    )


def _role_profile(
    *,
    role_profile_id: RoleProfileId | str,
    role_category: RoleCategory,
    role_name: str,
    capability_tags: tuple[CapabilityTag, ...],
) -> RoleProfile:
    return RoleProfile(
        role_profile_id=role_profile_id
        if isinstance(role_profile_id, RoleProfileId)
        else RoleProfileId(value=role_profile_id),
        role_category=role_category,
        role_name=role_name,
        responsibilities=("Produce work within the approved role boundary.",),
        capability_tags=capability_tags,
        input_contracts=(ContractId(value="contract.execution_package"),),
        output_contracts=(ContractId(value="contract.work_product"),),
        forbidden_actions=("skip governance",),
        **baseline_role_prompt_hook_fields_for_category(role_category),
    )


def _role_change(
    *,
    graph_version: int,
    actor_ref: ActorRef | str,
    role_profile: RoleProfile,
) -> dict[str, object]:
    actor = actor_ref if isinstance(actor_ref, ActorRef) else ActorRef(value=actor_ref)
    return {
        "graph_version": graph_version,
        "action": "registered",
        "actor_ref": actor.model_dump(mode="json"),
        "role_profile": role_profile.model_dump(mode="json"),
    }


def _model_profile(
    *,
    model_execution_profile_id: ModelExecutionProfileId | str,
) -> ModelExecutionProfile:
    return ModelExecutionProfile(
        model_execution_profile_id=model_execution_profile_id
        if isinstance(model_execution_profile_id, ModelExecutionProfileId)
        else ModelExecutionProfileId(value=model_execution_profile_id),
        provider="anthropic",
        model="claude-sonnet-4-6",
        reasoning_effort="medium",
        context_window=200000,
        temperature=0.2,
        tool_permissions=("filesystem.read",),
        fallback_policy_ref=ContractId(value="fallback.governance.record_failure"),
    )


def _model_registry() -> ModelExecutionProfileRegistry:
    return ModelExecutionProfileRegistry.from_profiles(
        _model_profile(model_execution_profile_id=CEO_MODEL_PROFILE_REF),
        _model_profile(model_execution_profile_id=WORKER_MODEL_PROFILE_REF),
    )


def _seat(
    *,
    seat_ref: AgentSeatRef | str,
    actor_ref: ActorRef | str,
    role_profile_ref: RoleProfileId | str,
    role_category: RoleCategory,
    capability_tags: tuple[CapabilityTag, ...],
    model_execution_profile_ref: ModelExecutionProfileId | str,
    lifecycle_status: SeatLifecycleStatus,
) -> AgentSeat:
    return AgentSeat(
        seat_ref=seat_ref if isinstance(seat_ref, AgentSeatRef) else AgentSeatRef(value=seat_ref),
        actor_ref=actor_ref if isinstance(actor_ref, ActorRef) else ActorRef(value=actor_ref),
        project_ref=PROJECT_REF,
        role_profile_ref=role_profile_ref
        if isinstance(role_profile_ref, RoleProfileId)
        else RoleProfileId(value=role_profile_ref),
        role_category=role_category,
        capability_tags=capability_tags,
        model_execution_profile_ref=model_execution_profile_ref
        if isinstance(model_execution_profile_ref, ModelExecutionProfileId)
        else ModelExecutionProfileId(value=model_execution_profile_ref),
        skill_refs=(SkillRef(value="skill.team.default"),),
        context_budget_tokens=4096,
        lifecycle_status=lifecycle_status,
    )


def _seat_event_payload(
    *,
    graph_version: int,
    actor_ref: ActorRef | str,
    action: SeatLifecycleAction,
    seat: AgentSeat,
) -> SeatLifecycleEvent:
    return SeatLifecycleEvent(
        graph_version=graph_version,
        action=action,
        actor_ref=actor_ref if isinstance(actor_ref, ActorRef) else ActorRef(value=actor_ref),
        seat=seat,
    )


def test_agent_team_projector_orchestrates_role_and_seat_facts_before_compilation() -> None:
    ceo_role = _role_profile(
        role_profile_id=CEO_ROLE_PROFILE_REF,
        role_category=RoleCategory.GOVERNANCE,
        role_name="CEO Governance",
        capability_tags=(CapabilityTag(value="team.composition"),),
    )
    worker_role = _role_profile(
        role_profile_id=WORKER_ROLE_PROFILE_REF,
        role_category=RoleCategory.IMPLEMENTATION,
        role_name="Backend Worker",
        capability_tags=(CapabilityTag(value="task.implementation"),),
    )
    ceo_created_seat = _seat(
        seat_ref=CEO_SEAT_REF,
        actor_ref=CEO_ACTOR_REF,
        role_profile_ref=CEO_ROLE_PROFILE_REF,
        role_category=RoleCategory.GOVERNANCE,
        capability_tags=(CapabilityTag(value="team.composition"),),
        model_execution_profile_ref=CEO_MODEL_PROFILE_REF,
        lifecycle_status=SeatLifecycleStatus.CREATED,
    )
    ceo_active_seat = _seat(
        seat_ref=CEO_SEAT_REF,
        actor_ref=CEO_ACTOR_REF,
        role_profile_ref=CEO_ROLE_PROFILE_REF,
        role_category=RoleCategory.GOVERNANCE,
        capability_tags=(CapabilityTag(value="team.composition"),),
        model_execution_profile_ref=CEO_MODEL_PROFILE_REF,
        lifecycle_status=SeatLifecycleStatus.ACTIVE,
    )
    worker_created_seat = _seat(
        seat_ref=WORKER_SEAT_REF,
        actor_ref=WORKER_ACTOR_REF,
        role_profile_ref=WORKER_ROLE_PROFILE_REF,
        role_category=RoleCategory.IMPLEMENTATION,
        capability_tags=(CapabilityTag(value="task.implementation"),),
        model_execution_profile_ref=WORKER_MODEL_PROFILE_REF,
        lifecycle_status=SeatLifecycleStatus.CREATED,
    )
    worker_active_seat = _seat(
        seat_ref=WORKER_SEAT_REF,
        actor_ref=WORKER_ACTOR_REF,
        role_profile_ref=WORKER_ROLE_PROFILE_REF,
        role_category=RoleCategory.IMPLEMENTATION,
        capability_tags=(CapabilityTag(value="task.implementation"),),
        model_execution_profile_ref=WORKER_MODEL_PROFILE_REF,
        lifecycle_status=SeatLifecycleStatus.ACTIVE,
    )
    events = (
        _event(
            event_id="evt-bootstrap",
            event_type=EventType.BOOTSTRAP_GOVERNANCE_AUTHORITY,
            payload_ref="payload:bootstrap",
            graph_version=1,
            actor_ref=BOOTSTRAP_ACTOR_REF,
        ),
        _event(
            event_id="evt-role-ceo-registered",
            event_type=EventType.ROLE_PROFILE_REGISTERED,
            payload_ref="payload:role-ceo-registered",
            graph_version=2,
            actor_ref=BOOTSTRAP_ACTOR_REF,
        ),
        _event(
            event_id="evt-seat-ceo-created",
            event_type=EventType.SEAT_CREATED,
            payload_ref="payload:seat-ceo-created",
            graph_version=3,
            actor_ref=BOOTSTRAP_ACTOR_REF,
        ),
        _event(
            event_id="evt-seat-ceo-activated",
            event_type=EventType.SEAT_ACTIVATED,
            payload_ref="payload:seat-ceo-activated",
            graph_version=4,
            actor_ref=BOOTSTRAP_ACTOR_REF,
        ),
        _event(
            event_id="evt-role-worker-registered",
            event_type=EventType.ROLE_PROFILE_REGISTERED,
            payload_ref="payload:role-worker-registered",
            graph_version=5,
            actor_ref=CEO_ACTOR_REF,
        ),
        _event(
            event_id="evt-seat-worker-created",
            event_type=EventType.SEAT_CREATED,
            payload_ref="payload:seat-worker-created",
            graph_version=6,
            actor_ref=CEO_ACTOR_REF,
        ),
        _event(
            event_id="evt-seat-worker-activated",
            event_type=EventType.SEAT_ACTIVATED,
            payload_ref="payload:seat-worker-activated",
            graph_version=7,
            actor_ref=CEO_ACTOR_REF,
        ),
    )
    resolver = InMemoryAgentTeamPayloadResolver(
        bootstrap_payloads={"payload:bootstrap": _bootstrap_authority()},
        role_profile_payloads={
            "payload:role-ceo-registered": _role_change(
                graph_version=2,
                actor_ref=BOOTSTRAP_ACTOR_REF,
                role_profile=ceo_role,
            ),
            "payload:role-worker-registered": _role_change(
                graph_version=5,
                actor_ref=CEO_ACTOR_REF,
                role_profile=worker_role,
            ),
        },
        seat_lifecycle_payloads={
            "payload:seat-ceo-created": _seat_event_payload(
                graph_version=3,
                actor_ref=BOOTSTRAP_ACTOR_REF,
                action=SeatLifecycleAction.CREATED,
                seat=ceo_created_seat,
            ),
            "payload:seat-ceo-activated": _seat_event_payload(
                graph_version=4,
                actor_ref=BOOTSTRAP_ACTOR_REF,
                action=SeatLifecycleAction.ACTIVATED,
                seat=ceo_active_seat,
            ),
            "payload:seat-worker-created": _seat_event_payload(
                graph_version=6,
                actor_ref=CEO_ACTOR_REF,
                action=SeatLifecycleAction.CREATED,
                seat=worker_created_seat,
            ),
            "payload:seat-worker-activated": _seat_event_payload(
                graph_version=7,
                actor_ref=CEO_ACTOR_REF,
                action=SeatLifecycleAction.ACTIVATED,
                seat=worker_active_seat,
            ),
        },
    )

    projection = AgentTeamProjector(payload_resolver=resolver).project(
        events,
        model_execution_profiles=_model_registry(),
    )

    assert projection.graph_version == 7
    assert projection.seat_lifecycle.graph_version == 7
    assert WORKER_SEAT_REF in projection.seat_lifecycle.active_seats
    assert projection.active_seats == projection.seat_lifecycle.active_seats
    assert projection.role_profiles.contains(RoleProfileId(value="role.worker.backend"))
    assert projection.active_seats[WORKER_SEAT_REF].role_profile_ref == WORKER_ROLE_PROFILE_REF
    assert projection.active_seats[WORKER_SEAT_REF].lifecycle_status is SeatLifecycleStatus.ACTIVE
