from datetime import UTC, datetime

import pytest

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
from boardroom_os.agents.team import (
    AgentTeamProjectionError,
    AgentTeamProjector,
    AgentTeamPayloadResolver,
)
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
CEO_SEAT_REF = AgentSeatRef(value="seat.governance.ceo.primary")
CEO_ROLE_PROFILE_REF = RoleProfileId(value="role.governance.ceo")
CEO_MODEL_PROFILE_REF = ModelExecutionProfileId(value="model.governance.ceo")


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
    project_ref: ProjectRef | str = PROJECT_REF,
) -> EventRecord:
    return EventRecord(
        event_id=EventId(value=event_id),
        event_type=event_type,
        project_ref=project_ref
        if isinstance(project_ref, ProjectRef)
        else ProjectRef(value=project_ref),
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
    role_profile_id: RoleProfileId | str = CEO_ROLE_PROFILE_REF,
    role_category: RoleCategory = RoleCategory.GOVERNANCE,
    role_name: str = "CEO Governance",
    capability_tags: tuple[CapabilityTag, ...] = (CapabilityTag(value="team.composition"),),
) -> RoleProfile:
    return RoleProfile(
        role_profile_id=role_profile_id
        if isinstance(role_profile_id, RoleProfileId)
        else RoleProfileId(value=role_profile_id),
        role_category=role_category,
        role_name=role_name,
        responsibilities=("Govern team composition.",),
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
    action: str = "registered",
) -> dict[str, object]:
    actor = actor_ref if isinstance(actor_ref, ActorRef) else ActorRef(value=actor_ref)
    return {
        "graph_version": graph_version,
        "action": action,
        "actor_ref": actor.model_dump(mode="json"),
        "role_profile": role_profile.model_dump(mode="json"),
    }


def _model_profile(
    *,
    model_execution_profile_id: ModelExecutionProfileId | str = CEO_MODEL_PROFILE_REF,
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
        _model_profile(),
        _model_profile(model_execution_profile_id="model.worker.backend"),
    )


def _seat(
    *,
    seat_ref: AgentSeatRef | str = CEO_SEAT_REF,
    actor_ref: ActorRef | str = CEO_ACTOR_REF,
    role_profile_ref: RoleProfileId | str = CEO_ROLE_PROFILE_REF,
    role_category: RoleCategory = RoleCategory.GOVERNANCE,
    capability_tags: tuple[CapabilityTag, ...] = (CapabilityTag(value="team.composition"),),
    model_execution_profile_ref: ModelExecutionProfileId | str = CEO_MODEL_PROFILE_REF,
    lifecycle_status: SeatLifecycleStatus = SeatLifecycleStatus.CREATED,
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


def _resolver(
    *,
    bootstrap_payloads: dict[str, BootstrapGovernanceAuthority] | None = None,
    role_profile_payloads: dict[str, object] | None = None,
    seat_lifecycle_payloads: dict[str, object] | None = None,
) -> InMemoryAgentTeamPayloadResolver:
    return InMemoryAgentTeamPayloadResolver(
        bootstrap_payloads=bootstrap_payloads
        or {"payload:bootstrap": _bootstrap_authority()},
        role_profile_payloads=role_profile_payloads or {},
        seat_lifecycle_payloads=seat_lifecycle_payloads or {},
    )


def _base_events() -> tuple[EventRecord, ...]:
    return (
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
    )


def _projector(
    *,
    resolver: InMemoryAgentTeamPayloadResolver | None = None,
) -> AgentTeamProjector:
    return AgentTeamProjector(
        payload_resolver=resolver
        or _resolver(
            role_profile_payloads={
                "payload:role-ceo-registered": _role_change(
                    graph_version=2,
                    actor_ref=BOOTSTRAP_ACTOR_REF,
                    role_profile=_role_profile(),
                ),
            },
            seat_lifecycle_payloads={
                "payload:seat-ceo-created": _seat_event_payload(
                    graph_version=3,
                    actor_ref=BOOTSTRAP_ACTOR_REF,
                    action=SeatLifecycleAction.CREATED,
                    seat=_seat(lifecycle_status=SeatLifecycleStatus.CREATED),
                ),
                "payload:seat-ceo-activated": _seat_event_payload(
                    graph_version=4,
                    actor_ref=BOOTSTRAP_ACTOR_REF,
                    action=SeatLifecycleAction.ACTIVATED,
                    seat=_seat(lifecycle_status=SeatLifecycleStatus.ACTIVE),
                ),
            },
        )
    )


def test_agent_team_projector_rejects_unsorted_events() -> None:
    projector = _projector()

    with pytest.raises(AgentTeamProjectionError, match="strictly increasing"):
        projector.project(
            (_base_events()[1], _base_events()[0]),
            model_execution_profiles=_model_registry(),
        )


def test_agent_team_projector_rejects_project_mismatch() -> None:
    projector = _projector()
    bootstrap_event, role_event, seat_created_event, seat_activated_event = _base_events()

    with pytest.raises(AgentTeamProjectionError, match="single project_ref"):
        projector.project(
            (
                bootstrap_event,
                role_event,
                _event(
                    event_id=seat_created_event.event_id.value,
                    event_type=seat_created_event.event_type,
                    payload_ref=seat_created_event.payload_refs[0].value,
                    graph_version=seat_created_event.graph_version,
                    actor_ref=seat_created_event.actor_ref,
                    project_ref="project.other",
                ),
                seat_activated_event,
            ),
            model_execution_profiles=_model_registry(),
        )


def test_agent_team_projector_rejects_role_profile_payload_resolution_failure() -> None:
    projector = _projector(resolver=_resolver())

    with pytest.raises(
        AgentTeamProjectionError,
        match="role profile payload_ref could not be resolved",
    ):
        projector.project(_base_events(), model_execution_profiles=_model_registry())


def test_agent_team_projector_rejects_invalid_role_profile_payload_schema() -> None:
    resolver = _resolver(
        role_profile_payloads={"payload:role-ceo-registered": {}},
        seat_lifecycle_payloads={
            "payload:seat-ceo-created": _seat_event_payload(
                graph_version=3,
                actor_ref=BOOTSTRAP_ACTOR_REF,
                action=SeatLifecycleAction.CREATED,
                seat=_seat(lifecycle_status=SeatLifecycleStatus.CREATED),
            ),
            "payload:seat-ceo-activated": _seat_event_payload(
                graph_version=4,
                actor_ref=BOOTSTRAP_ACTOR_REF,
                action=SeatLifecycleAction.ACTIVATED,
                seat=_seat(lifecycle_status=SeatLifecycleStatus.ACTIVE),
            ),
        },
    )

    with pytest.raises(
        AgentTeamProjectionError,
        match="role profile payload is invalid",
    ) as error_info:
        _projector(resolver=resolver).project(
            _base_events(), model_execution_profiles=_model_registry()
        )

    assert "could not be resolved" not in str(error_info.value)


def test_agent_team_projector_rejects_role_profile_payload_graph_version_mismatch() -> None:
    resolver = _resolver(
        role_profile_payloads={
            "payload:role-ceo-registered": _role_change(
                graph_version=99,
                actor_ref=BOOTSTRAP_ACTOR_REF,
                role_profile=_role_profile(),
            ),
        },
        seat_lifecycle_payloads={
            "payload:seat-ceo-created": _seat_event_payload(
                graph_version=3,
                actor_ref=BOOTSTRAP_ACTOR_REF,
                action=SeatLifecycleAction.CREATED,
                seat=_seat(lifecycle_status=SeatLifecycleStatus.CREATED),
            ),
            "payload:seat-ceo-activated": _seat_event_payload(
                graph_version=4,
                actor_ref=BOOTSTRAP_ACTOR_REF,
                action=SeatLifecycleAction.ACTIVATED,
                seat=_seat(lifecycle_status=SeatLifecycleStatus.ACTIVE),
            ),
        },
    )

    with pytest.raises(AgentTeamProjectionError, match="graph_version"):
        _projector(resolver=resolver).project(_base_events(), model_execution_profiles=_model_registry())


def test_agent_team_projector_rejects_role_profile_payload_actor_mismatch() -> None:
    resolver = _resolver(
        role_profile_payloads={
            "payload:role-ceo-registered": _role_change(
                graph_version=2,
                actor_ref="actor.other",
                role_profile=_role_profile(),
            ),
        },
        seat_lifecycle_payloads={
            "payload:seat-ceo-created": _seat_event_payload(
                graph_version=3,
                actor_ref=BOOTSTRAP_ACTOR_REF,
                action=SeatLifecycleAction.CREATED,
                seat=_seat(lifecycle_status=SeatLifecycleStatus.CREATED),
            ),
            "payload:seat-ceo-activated": _seat_event_payload(
                graph_version=4,
                actor_ref=BOOTSTRAP_ACTOR_REF,
                action=SeatLifecycleAction.ACTIVATED,
                seat=_seat(lifecycle_status=SeatLifecycleStatus.ACTIVE),
            ),
        },
    )

    with pytest.raises(AgentTeamProjectionError, match="actor_ref"):
        _projector(resolver=resolver).project(_base_events(), model_execution_profiles=_model_registry())


@pytest.mark.parametrize(
    ("event_type", "action"),
    [
        (EventType.ROLE_PROFILE_REPLACED, "registered"),
        (EventType.ROLE_PROFILE_REGISTERED, "replaced"),
        (EventType.ROLE_PROFILE_SUPERSEDED, "superseded"),
    ],
)
def test_agent_team_projector_rejects_unsupported_role_profile_replacement_events(
    event_type: EventType,
    action: str,
) -> None:
    events = (
        _event(
            event_id="evt-bootstrap",
            event_type=EventType.BOOTSTRAP_GOVERNANCE_AUTHORITY,
            payload_ref="payload:bootstrap",
            graph_version=1,
            actor_ref=BOOTSTRAP_ACTOR_REF,
        ),
        _event(
            event_id="evt-role-change",
            event_type=event_type,
            payload_ref="payload:role-change",
            graph_version=2,
            actor_ref=BOOTSTRAP_ACTOR_REF,
        ),
    )
    resolver = _resolver(
        role_profile_payloads={
            "payload:role-change": _role_change(
                graph_version=2,
                actor_ref=BOOTSTRAP_ACTOR_REF,
                role_profile=_role_profile(),
                action=action,
            )
        }
    )

    with pytest.raises(AgentTeamProjectionError, match="unsupported role profile change"):
        _projector(resolver=resolver).project(events, model_execution_profiles=_model_registry())


def test_agent_team_projector_rejects_seat_lifecycle_unknown_role_profile() -> None:
    worker_role = _role_profile(
        role_profile_id="role.worker.backend",
        role_category=RoleCategory.IMPLEMENTATION,
        role_name="Backend Worker",
        capability_tags=(CapabilityTag(value="task.implementation"),),
    )
    resolver = _resolver(
        role_profile_payloads={
            "payload:role-ceo-registered": _role_change(
                graph_version=2,
                actor_ref=BOOTSTRAP_ACTOR_REF,
                role_profile=_role_profile(),
            ),
        },
        seat_lifecycle_payloads={
            "payload:seat-ceo-created": _seat_event_payload(
                graph_version=3,
                actor_ref=BOOTSTRAP_ACTOR_REF,
                action=SeatLifecycleAction.CREATED,
                seat=_seat(role_profile_ref=worker_role.role_profile_id),
            ),
            "payload:seat-ceo-activated": _seat_event_payload(
                graph_version=4,
                actor_ref=BOOTSTRAP_ACTOR_REF,
                action=SeatLifecycleAction.ACTIVATED,
                seat=_seat(
                    role_profile_ref=worker_role.role_profile_id,
                    lifecycle_status=SeatLifecycleStatus.ACTIVE,
                ),
            ),
        },
    )

    with pytest.raises(AgentTeamProjectionError, match="unknown role_profile_ref"):
        _projector(resolver=resolver).project(_base_events(), model_execution_profiles=_model_registry())


def test_agent_team_projector_rejects_seat_lifecycle_payload_resolution_failure() -> None:
    resolver = _resolver(
        role_profile_payloads={
            "payload:role-ceo-registered": _role_change(
                graph_version=2,
                actor_ref=BOOTSTRAP_ACTOR_REF,
                role_profile=_role_profile(),
            ),
        }
    )

    with pytest.raises(
        AgentTeamProjectionError,
        match="seat lifecycle payload_ref could not be resolved",
    ):
        _projector(resolver=resolver).project(_base_events(), model_execution_profiles=_model_registry())


def test_agent_team_projector_rejects_missing_bootstrap_governance_authority() -> None:
    events = _base_events()[1:]
    resolver = _resolver(
        role_profile_payloads={
            "payload:role-ceo-registered": _role_change(
                graph_version=2,
                actor_ref=BOOTSTRAP_ACTOR_REF,
                role_profile=_role_profile(),
            ),
        }
    )

    with pytest.raises(
        AgentTeamProjectionError,
        match="missing bootstrap governance authority",
    ):
        _projector(resolver=resolver).project(events, model_execution_profiles=_model_registry())


def test_agent_team_projector_rejects_duplicate_bootstrap_governance_authority() -> None:
    events = (
        _base_events()[0],
        _event(
            event_id="evt-bootstrap-duplicate",
            event_type=EventType.BOOTSTRAP_GOVERNANCE_AUTHORITY,
            payload_ref="payload:bootstrap-duplicate",
            graph_version=2,
            actor_ref=BOOTSTRAP_ACTOR_REF,
        ),
    )
    resolver = _resolver(
        bootstrap_payloads={
            "payload:bootstrap": _bootstrap_authority(),
            "payload:bootstrap-duplicate": _bootstrap_authority(),
        }
    )

    with pytest.raises(
        AgentTeamProjectionError,
        match="duplicate bootstrap governance authority",
    ):
        _projector(resolver=resolver).project(events, model_execution_profiles=_model_registry())


def test_agent_team_projector_rejects_duplicate_role_profile_id_registration() -> None:
    duplicate_ceo_role = _role_profile(role_name="Duplicate CEO Governance")
    events = (
        *_base_events(),
        _event(
            event_id="evt-role-ceo-duplicate-registered",
            event_type=EventType.ROLE_PROFILE_REGISTERED,
            payload_ref="payload:role-ceo-duplicate-registered",
            graph_version=5,
            actor_ref=CEO_ACTOR_REF,
        ),
    )
    resolver = _resolver(
        role_profile_payloads={
            "payload:role-ceo-registered": _role_change(
                graph_version=2,
                actor_ref=BOOTSTRAP_ACTOR_REF,
                role_profile=_role_profile(),
            ),
            "payload:role-ceo-duplicate-registered": _role_change(
                graph_version=5,
                actor_ref=CEO_ACTOR_REF,
                role_profile=duplicate_ceo_role,
            ),
        },
        seat_lifecycle_payloads={
            "payload:seat-ceo-created": _seat_event_payload(
                graph_version=3,
                actor_ref=BOOTSTRAP_ACTOR_REF,
                action=SeatLifecycleAction.CREATED,
                seat=_seat(lifecycle_status=SeatLifecycleStatus.CREATED),
            ),
            "payload:seat-ceo-activated": _seat_event_payload(
                graph_version=4,
                actor_ref=BOOTSTRAP_ACTOR_REF,
                action=SeatLifecycleAction.ACTIVATED,
                seat=_seat(lifecycle_status=SeatLifecycleStatus.ACTIVE),
            ),
        },
    )

    with pytest.raises(AgentTeamProjectionError, match="role_profile_id must be unique"):
        _projector(resolver=resolver).project(
            events, model_execution_profiles=_model_registry()
        )


def test_agent_team_projector_rejects_registration_after_governance_seat_deactivated() -> None:
    worker_role = _role_profile(
        role_profile_id="role.worker.backend",
        role_category=RoleCategory.IMPLEMENTATION,
        role_name="Backend Worker",
        capability_tags=(CapabilityTag(value="task.implementation"),),
    )
    events = (
        *_base_events(),
        _event(
            event_id="evt-seat-ceo-deactivated",
            event_type=EventType.SEAT_DEACTIVATED,
            payload_ref="payload:seat-ceo-deactivated",
            graph_version=5,
            actor_ref=CEO_ACTOR_REF,
        ),
        _event(
            event_id="evt-role-worker-registered",
            event_type=EventType.ROLE_PROFILE_REGISTERED,
            payload_ref="payload:role-worker-registered",
            graph_version=6,
            actor_ref=CEO_ACTOR_REF,
        ),
    )
    resolver = _resolver(
        role_profile_payloads={
            "payload:role-ceo-registered": _role_change(
                graph_version=2,
                actor_ref=BOOTSTRAP_ACTOR_REF,
                role_profile=_role_profile(),
            ),
            "payload:role-worker-registered": _role_change(
                graph_version=6,
                actor_ref=CEO_ACTOR_REF,
                role_profile=worker_role,
            ),
        },
        seat_lifecycle_payloads={
            "payload:seat-ceo-created": _seat_event_payload(
                graph_version=3,
                actor_ref=BOOTSTRAP_ACTOR_REF,
                action=SeatLifecycleAction.CREATED,
                seat=_seat(lifecycle_status=SeatLifecycleStatus.CREATED),
            ),
            "payload:seat-ceo-activated": _seat_event_payload(
                graph_version=4,
                actor_ref=BOOTSTRAP_ACTOR_REF,
                action=SeatLifecycleAction.ACTIVATED,
                seat=_seat(lifecycle_status=SeatLifecycleStatus.ACTIVE),
            ),
            "payload:seat-ceo-deactivated": _seat_event_payload(
                graph_version=5,
                actor_ref=CEO_ACTOR_REF,
                action=SeatLifecycleAction.DEACTIVATED,
                seat=_seat(lifecycle_status=SeatLifecycleStatus.DEACTIVATED),
            ),
        },
    )

    with pytest.raises(AgentTeamProjectionError, match="active governance seat"):
        _projector(resolver=resolver).project(events, model_execution_profiles=_model_registry())
