from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

import boardroom_os.agents.policy as policy_module
import boardroom_os.agents.seat as seat_module
from boardroom_os.agents.policy import (
    BootstrapGovernanceAuthority,
    GovernanceAuthorityProjector,
    RoleProfileChange,
    RoleProfileChangeAction,
    RoleProfileProjection,
    SeatPolicyError,
)
from boardroom_os.agents.profiles import (
    ModelExecutionProfile,
    ModelExecutionProfileId,
    ModelExecutionProfileRegistry,
    RoleProfile,
)
from boardroom_os.agents.seat import RoleCategory
from boardroom_os.agents.skills import CapabilityTag, RoleProfileId, SkillRef
from boardroom_os.contracts.types import ContractId
from boardroom_os.events.record import EventRecord
from boardroom_os.events.types import (
    ActorRef,
    EventId,
    EventPayloadRef,
    EventType,
    ProjectRef,
)

BASE_TIMESTAMP = datetime(2026, 5, 17, 12, 0, tzinfo=UTC)


class InMemoryGovernanceAuthorityPayloadResolver:
    def __init__(
        self,
        bootstrap_payloads: dict[str, BootstrapGovernanceAuthority] | None = None,
        seat_payloads: dict[str, object] | None = None,
    ) -> None:
        self._bootstrap_payloads = bootstrap_payloads or {}
        self._seat_payloads = seat_payloads or {}
        self.bootstrap_calls: list[str] = []
        self.seat_calls: list[str] = []

    def resolve_bootstrap_governance_authority(
        self,
        payload_ref: EventPayloadRef,
    ) -> BootstrapGovernanceAuthority:
        self.bootstrap_calls.append(payload_ref.value)
        return self._bootstrap_payloads[payload_ref.value]

    def resolve_seat_lifecycle_event(self, payload_ref: EventPayloadRef) -> object:
        self.seat_calls.append(payload_ref.value)
        return self._seat_payloads[payload_ref.value]


def _bootstrap_authority(**overrides: object) -> BootstrapGovernanceAuthority:
    values = {
        "authority_scope": ("role_profile_write", "seat_lifecycle_write"),
    }
    values.update(overrides)
    return BootstrapGovernanceAuthority(**values)


def _role_profile(**overrides: object) -> RoleProfile:
    values = {
        "role_profile_id": RoleProfileId(value="role.governance.bootstrap"),
        "role_category": RoleCategory.GOVERNANCE,
        "role_name": "Bootstrap Governance",
        "responsibilities": (
            "Register the first governance role profile.",
            "Define initial team composition controls.",
        ),
        "capability_tags": (
            CapabilityTag(value="team.composition"),
            CapabilityTag(value="governance.bootstrap"),
        ),
        "input_contracts": (ContractId(value="contract.bootstrap.authority"),),
        "output_contracts": (ContractId(value="contract.role_profile_registry"),),
        "forbidden_actions": (
            "register implementation role before governance bootstrap",
        ),
    }
    values.update(overrides)
    return RoleProfile(**values)


def _role_profile_change(**overrides: object) -> RoleProfileChange:
    values = {
        "graph_version": 2,
        "action": RoleProfileChangeAction.REGISTERED,
        "actor_ref": ActorRef(value="actor.bootstrap"),
        "role_profile": _role_profile(),
    }
    values.update(overrides)
    return RoleProfileChange(**values)


def _model_profile(**overrides: object) -> ModelExecutionProfile:
    values = {
        "model_execution_profile_id": ModelExecutionProfileId(value="model.governance.ceo"),
        "provider": "anthropic",
        "model": "claude-sonnet-4-6",
        "reasoning_effort": "medium",
        "context_window": 200000,
        "temperature": 0.2,
        "tool_permissions": ("filesystem.read",),
        "fallback_policy_ref": ContractId(value="fallback.governance.record_failure"),
    }
    values.update(overrides)
    return ModelExecutionProfile(**values)


def _model_registry() -> ModelExecutionProfileRegistry:
    return ModelExecutionProfileRegistry.from_profiles(_model_profile())


def _agent_seat(**overrides: object) -> object:
    values = {
        "seat_ref": {"value": "seat.governance.ceo.primary"},
        "actor_ref": {"value": "actor.ceo"},
        "project_ref": {"value": "project.boardroom-os"},
        "role_profile_ref": {"value": "role.governance.bootstrap"},
        "role_category": "governance",
        "capability_tags": ["team.composition"],
        "model_execution_profile_ref": {"value": "model.governance.ceo"},
        "skill_refs": [{"value": "skill.governance.ceo"}],
        "context_budget_tokens": 4096,
        "lifecycle_status": "created",
    }
    values.update(overrides)
    return seat_module.AgentSeat.model_validate(values)


def _seat_lifecycle_event(**overrides: object) -> object:
    values = {
        "graph_version": 2,
        "action": "created",
        "actor_ref": {"value": "actor.bootstrap"},
        "seat": _agent_seat(),
    }
    values.update(overrides)
    return seat_module.SeatLifecycleEvent.model_validate(values)


def _event(
    *,
    event_id: str,
    event_type: EventType,
    payload_ref: str,
    graph_version: int,
    actor_ref: str = "actor.bootstrap",
    payload_refs: tuple[str, ...] | None = None,
) -> EventRecord:
    refs = payload_refs or (payload_ref,)
    return EventRecord(
        event_id=EventId(value=event_id),
        event_type=event_type,
        project_ref=ProjectRef(value="project.boardroom-os"),
        actor_ref=ActorRef(value=actor_ref),
        timestamp=BASE_TIMESTAMP,
        graph_version=graph_version,
        payload_refs=tuple(EventPayloadRef(value=ref) for ref in refs),
    )


def _bootstrap_event(
    *,
    event_id: str = "evt-bootstrap-governance-authority",
    payload_ref: str = "payload:bootstrap-governance-authority",
    graph_version: int = 1,
    actor_ref: str = "actor.bootstrap",
    payload_refs: tuple[str, ...] | None = None,
) -> EventRecord:
    return _event(
        event_id=event_id,
        event_type=EventType.BOOTSTRAP_GOVERNANCE_AUTHORITY,
        payload_ref=payload_ref,
        graph_version=graph_version,
        actor_ref=actor_ref,
        payload_refs=payload_refs,
    )


def _seat_event(
    *,
    event_id: str,
    event_type: EventType,
    payload_ref: str,
    graph_version: int,
    actor_ref: str,
) -> EventRecord:
    return _event(
        event_id=event_id,
        event_type=event_type,
        payload_ref=payload_ref,
        graph_version=graph_version,
        actor_ref=actor_ref,
    )


def _governance_authority(
    *,
    authority_scope: tuple[str, ...] = ("role_profile_write", "seat_lifecycle_write"),
) -> object:
    resolver = InMemoryGovernanceAuthorityPayloadResolver(
        {
            "payload:bootstrap-governance-authority": _bootstrap_authority(
                authority_scope=authority_scope,
            ),
        }
    )
    return GovernanceAuthorityProjector(resolver).project((_bootstrap_event(),))


def _governance_projection() -> RoleProfileProjection:
    return RoleProfileProjection.apply_changes(
        changes=(
            _role_profile_change(
                role_profile=_role_profile(),
            ),
        ),
        governance_authority=_governance_authority(),
    )


def _seat_projector(*, seat_payloads: dict[str, object]) -> object:
    return seat_module.SeatLifecycleProjector(
        payload_resolver=InMemoryGovernanceAuthorityPayloadResolver(
            {
                "payload:bootstrap-governance-authority": _bootstrap_authority(),
            },
            seat_payloads=seat_payloads,
        )
    )


def _active_backend_worker_seat(**overrides: object) -> seat_module.AgentSeat:
    values = {
        "seat_ref": "seat.worker.backend.primary",
        "actor_ref": "actor.worker.backend",
        "project_ref": "project.boardroom-os",
        "role_profile_ref": "role.worker.backend",
        "role_category": RoleCategory.IMPLEMENTATION,
        "capability_tags": ["task.implementation", "surface.backend"],
        "model_execution_profile_ref": "model.worker.backend",
        "skill_refs": ["skill.worker.backend"],
        "context_budget_tokens": 4096,
        "lifecycle_status": seat_module.SeatLifecycleStatus.ACTIVE,
    }
    values.update(overrides)
    return seat_module.AgentSeat.model_validate(values)


def _active_frontend_worker_seat(**overrides: object) -> seat_module.AgentSeat:
    values = {
        "seat_ref": "seat.worker.frontend.primary",
        "actor_ref": "actor.worker.frontend",
        "project_ref": "project.boardroom-os",
        "role_profile_ref": "role.worker.frontend",
        "role_category": RoleCategory.IMPLEMENTATION,
        "capability_tags": ["task.implementation", "surface.frontend"],
        "model_execution_profile_ref": "model.worker.frontend",
        "skill_refs": ["skill.worker.frontend"],
        "context_budget_tokens": 4096,
        "lifecycle_status": seat_module.SeatLifecycleStatus.ACTIVE,
    }
    values.update(overrides)
    return seat_module.AgentSeat.model_validate(values)


def _active_checker_seat(**overrides: object) -> seat_module.AgentSeat:
    values = {
        "seat_ref": "seat.checker.primary",
        "actor_ref": "actor.checker",
        "project_ref": "project.boardroom-os",
        "role_profile_ref": "role.checker.qa",
        "role_category": RoleCategory.VERIFICATION,
        "capability_tags": ["quality.verification"],
        "model_execution_profile_ref": "model.checker.qa",
        "skill_refs": ["skill.checker.qa"],
        "context_budget_tokens": 4096,
        "lifecycle_status": seat_module.SeatLifecycleStatus.ACTIVE,
    }
    values.update(overrides)
    return seat_module.AgentSeat.model_validate(values)


def _frontend_demand() -> seat_module.SeatDemand:
    return seat_module.SeatDemand(
        required_role_category=RoleCategory.IMPLEMENTATION,
        required_capability_tags=(CapabilityTag(value="surface.frontend"),),
    )


def _verification_demand() -> seat_module.SeatDemand:
    return seat_module.SeatDemand(
        required_role_category=RoleCategory.VERIFICATION,
        required_capability_tags=(CapabilityTag(value="quality.verification"),),
    )


def test_policy_rejects_default_worker_fallback_for_frontend_demand() -> None:
    policy = policy_module.SeatPolicy(
        active_seats={
            _active_backend_worker_seat().seat_ref: _active_backend_worker_seat(),
        }
    )

    match = policy.match(_frontend_demand())

    assert match.seat_ref is None
    assert match.blockers == (
        "team composition gap: missing active seat for capability tags: surface.frontend",
    )


def test_policy_rejects_missing_role_category_active_seat() -> None:
    policy = policy_module.SeatPolicy(
        active_seats={
            _active_backend_worker_seat().seat_ref: _active_backend_worker_seat(),
        }
    )

    match = policy.match(_verification_demand())

    assert match.seat_ref is None
    assert match.blockers == (
        "team composition gap: missing active seat for role category: verification",
    )


def test_policy_matches_after_ceo_adds_frontend_role_and_seat() -> None:
    frontend_seat = _active_frontend_worker_seat()
    policy = policy_module.SeatPolicy(
        active_seats={
            _active_backend_worker_seat().seat_ref: _active_backend_worker_seat(),
            frontend_seat.seat_ref: frontend_seat,
        }
    )

    match = policy.match(_frontend_demand())

    assert match.seat_ref == frontend_seat.seat_ref
    assert match.blockers == ()


def test_policy_rejects_checker_worker_same_role_category() -> None:
    worker_seat = _active_backend_worker_seat(seat_ref="seat.worker.backend.primary")
    checker_seat = _active_frontend_worker_seat(seat_ref="seat.worker.frontend.checker")
    policy = policy_module.SeatPolicy(
        active_seats={
            worker_seat.seat_ref: worker_seat,
            checker_seat.seat_ref: checker_seat,
        }
    )

    with pytest.raises(SeatPolicyError, match="independent checker"):
        policy.require_independent_checker(worker_seat.seat_ref, checker_seat.seat_ref)


def test_policy_rejects_same_seat_for_worker_and_checker() -> None:
    worker_seat = _active_backend_worker_seat()
    policy = policy_module.SeatPolicy(active_seats={worker_seat.seat_ref: worker_seat})

    with pytest.raises(SeatPolicyError, match="independent checker"):
        policy.require_independent_checker(worker_seat.seat_ref, worker_seat.seat_ref)


def test_policy_rejects_missing_checker_active_seat() -> None:
    worker_seat = _active_backend_worker_seat()
    checker_seat = _active_checker_seat()
    policy = policy_module.SeatPolicy(active_seats={worker_seat.seat_ref: worker_seat})

    with pytest.raises(SeatPolicyError, match="active seat"):
        policy.require_independent_checker(worker_seat.seat_ref, checker_seat.seat_ref)


def test_bootstrap_authority_must_be_graph_version_one() -> None:
    with pytest.raises(ValidationError):
        BootstrapGovernanceAuthority.model_validate(
            {
                "graph_version": 2,
                "authority_scope": ["role_profile_write"],
            }
        )



def test_governance_authority_projector_rejects_missing_bootstrap() -> None:
    projector = GovernanceAuthorityProjector(InMemoryGovernanceAuthorityPayloadResolver())

    with pytest.raises(SeatPolicyError, match="missing bootstrap governance authority"):
        projector.project(
            (
                _event(
                    event_id="evt-role-profile-registered",
                    event_type=EventType.ROLE_PROFILE_REGISTERED,
                    payload_ref="payload:role-profile-registered",
                    graph_version=2,
                ),
            )
        )



def test_governance_authority_projector_rejects_duplicate_bootstrap() -> None:
    projector = GovernanceAuthorityProjector(InMemoryGovernanceAuthorityPayloadResolver())

    with pytest.raises(SeatPolicyError, match="duplicate bootstrap governance authority"):
        projector.project(
            (
                _bootstrap_event(
                    event_id="evt-bootstrap-governance-authority-1",
                    payload_ref="payload:bootstrap-governance-authority-1",
                    graph_version=1,
                ),
                _bootstrap_event(
                    event_id="evt-bootstrap-governance-authority-2",
                    payload_ref="payload:bootstrap-governance-authority-2",
                    graph_version=1,
                ),
            )
        )



def test_governance_authority_projector_rejects_bootstrap_event_after_graph_version_one() -> None:
    projector = GovernanceAuthorityProjector(
        InMemoryGovernanceAuthorityPayloadResolver(
            {
                "payload:bootstrap-governance-authority": _bootstrap_authority(),
            }
        )
    )

    with pytest.raises(SeatPolicyError, match="graph_version=1"):
        projector.project((_bootstrap_event(graph_version=2),))



def test_governance_authority_projector_rejects_multiple_bootstrap_payload_refs() -> None:
    projector = GovernanceAuthorityProjector(InMemoryGovernanceAuthorityPayloadResolver())

    with pytest.raises(SeatPolicyError, match="exactly one payload_ref"):
        projector.project(
            (
                _bootstrap_event(
                    payload_refs=(
                        "payload:bootstrap-governance-authority",
                        "payload:unexpected-extra-bootstrap-authority",
                    ),
                ),
            )
        )



def test_governance_authority_projector_wraps_bootstrap_payload_resolution_failure() -> None:
    projector = GovernanceAuthorityProjector(InMemoryGovernanceAuthorityPayloadResolver())

    with pytest.raises(SeatPolicyError, match="payload_ref could not be resolved"):
        projector.project((_bootstrap_event(),))



def test_role_profile_projection_allows_limited_bootstrap_sequence() -> None:
    resolver = InMemoryGovernanceAuthorityPayloadResolver(
        {
            "payload:bootstrap-governance-authority": _bootstrap_authority(),
        }
    )
    authority = GovernanceAuthorityProjector(resolver).project((_bootstrap_event(),))

    projection = RoleProfileProjection.apply_changes(
        changes=(
            _role_profile_change(
                role_profile=_role_profile(),
            ),
        ),
        governance_authority=authority,
    )

    assert resolver.bootstrap_calls == ["payload:bootstrap-governance-authority"]
    assert projection.contains(RoleProfileId(value="role.governance.bootstrap"))
    assert projection.profiles[0].role_category is RoleCategory.GOVERNANCE



def test_non_bootstrap_actor_cannot_register_first_governance_role() -> None:
    resolver = InMemoryGovernanceAuthorityPayloadResolver(
        {
            "payload:bootstrap-governance-authority": _bootstrap_authority(),
        }
    )
    authority = GovernanceAuthorityProjector(resolver).project((_bootstrap_event(),))

    with pytest.raises(
        SeatPolicyError,
        match="non-bootstrap actor role profile registration is closed",
    ):
        RoleProfileProjection.apply_changes(
            changes=(
                _role_profile_change(
                    actor_ref=ActorRef(value="actor.ceo"),
                ),
            ),
            governance_authority=authority,
        )



def test_active_governance_actor_can_register_subsequent_role_profile() -> None:
    authority = _governance_authority()
    active_governance_seat = _agent_seat(lifecycle_status="active")
    frontend_role = _role_profile(
        role_profile_id=RoleProfileId(value="role.worker.frontend"),
        role_category=RoleCategory.IMPLEMENTATION,
        role_name="Frontend Worker",
        responsibilities=("Implement frontend source changes.",),
        capability_tags=(
            CapabilityTag(value="task.implementation"),
            CapabilityTag(value="surface.frontend"),
        ),
        input_contracts=(ContractId(value="contract.execution_package"),),
        output_contracts=(ContractId(value="contract.work_product"),),
        forbidden_actions=("modify governance contract",),
    )

    projection = RoleProfileProjection.apply_changes(
        changes=(
            _role_profile_change(role_profile=_role_profile()),
            _role_profile_change(
                graph_version=3,
                actor_ref=active_governance_seat.actor_ref,
                role_profile=frontend_role,
            ),
        ),
        governance_authority=authority,
        active_seats={active_governance_seat.seat_ref: active_governance_seat},
    )

    assert projection.contains(RoleProfileId(value="role.worker.frontend"))



def test_bootstrap_actor_cannot_register_second_role_profile() -> None:
    resolver = InMemoryGovernanceAuthorityPayloadResolver(
        {
            "payload:bootstrap-governance-authority": _bootstrap_authority(),
        }
    )
    authority = GovernanceAuthorityProjector(resolver).project((_bootstrap_event(),))

    with pytest.raises(
        SeatPolicyError,
        match="bootstrap actor may only register the first governance role",
    ):
        RoleProfileProjection.apply_changes(
            changes=(
                _role_profile_change(
                    graph_version=2,
                    role_profile=_role_profile(
                        role_profile_id=RoleProfileId(value="role.governance.bootstrap"),
                    ),
                ),
                _role_profile_change(
                    graph_version=3,
                    role_profile=_role_profile(
                        role_profile_id=RoleProfileId(value="role.governance.ceo"),
                        role_name="CEO Governance",
                    ),
                ),
            ),
            governance_authority=authority,
        )



def test_bootstrap_actor_cannot_register_non_governance_role() -> None:
    resolver = InMemoryGovernanceAuthorityPayloadResolver(
        {
            "payload:bootstrap-governance-authority": _bootstrap_authority(),
        }
    )
    authority = GovernanceAuthorityProjector(resolver).project((_bootstrap_event(),))

    with pytest.raises(
        SeatPolicyError,
        match="bootstrap actor may only register the first governance role",
    ):
        RoleProfileProjection.apply_changes(
            changes=(
                _role_profile_change(
                    role_profile=_role_profile(
                        role_profile_id=RoleProfileId(value="role.worker.backend"),
                        role_category=RoleCategory.IMPLEMENTATION,
                        role_name="Backend Worker",
                        responsibilities=(
                            "Implement backend source changes.",
                            "Return work product references within role boundary.",
                        ),
                        capability_tags=(CapabilityTag(value="task.implementation"),),
                        input_contracts=(ContractId(value="contract.execution_package"),),
                        output_contracts=(ContractId(value="contract.work_product"),),
                        forbidden_actions=("modify governance contract",),
                    )
                ),
            ),
            governance_authority=authority,
        )



def test_governance_role_without_team_composition_capability_is_rejected() -> None:
    resolver = InMemoryGovernanceAuthorityPayloadResolver(
        {
            "payload:bootstrap-governance-authority": _bootstrap_authority(),
        }
    )
    authority = GovernanceAuthorityProjector(resolver).project((_bootstrap_event(),))

    with pytest.raises(SeatPolicyError, match="team.composition"):
        RoleProfileProjection.apply_changes(
            changes=(
                _role_profile_change(
                    role_profile=_role_profile(
                        capability_tags=(CapabilityTag(value="governance.bootstrap"),),
                    )
                ),
            ),
            governance_authority=authority,
        )



def test_bootstrap_authority_without_role_profile_write_scope_is_rejected() -> None:
    resolver = InMemoryGovernanceAuthorityPayloadResolver(
        {
            "payload:bootstrap-governance-authority": _bootstrap_authority(
                authority_scope=("seat_write",),
            ),
        }
    )
    authority = GovernanceAuthorityProjector(resolver).project((_bootstrap_event(),))

    with pytest.raises(SeatPolicyError, match="role_profile_write"):
        RoleProfileProjection.apply_changes(
            changes=(
                _role_profile_change(
                    role_profile=_role_profile(),
                ),
            ),
            governance_authority=authority,
        )



@pytest.mark.parametrize(
    "action",
    [
        RoleProfileChangeAction.REPLACED,
        RoleProfileChangeAction.SUPERSEDED,
    ],
)
def test_role_profile_projection_rejects_non_registered_action(
    action: RoleProfileChangeAction,
) -> None:
    resolver = InMemoryGovernanceAuthorityPayloadResolver(
        {
            "payload:bootstrap-governance-authority": _bootstrap_authority(),
        }
    )
    authority = GovernanceAuthorityProjector(resolver).project((_bootstrap_event(),))

    with pytest.raises(SeatPolicyError, match="unsupported role profile change action"):
        RoleProfileProjection.apply_changes(
            changes=(
                _role_profile_change(
                    action=action,
                ),
            ),
            governance_authority=authority,
        )



def test_agent_seat_rejects_unknown_schema_version() -> None:
    assert _agent_seat().version == 1

    with pytest.raises(ValidationError):
        seat_module.AgentSeat.model_validate(
            {
                "version": 2,
                "seat_ref": "seat.governance.ceo.primary",
                "actor_ref": "actor.ceo",
                "project_ref": "project.boardroom-os",
                "role_profile_ref": "role.governance.bootstrap",
                "role_category": "governance",
                "capability_tags": ["team.composition"],
                "model_execution_profile_ref": "model.governance.ceo",
                "skill_refs": ["skill.governance.ceo"],
                "context_budget_tokens": 4096,
                "lifecycle_status": "created",
            }
        )



def test_agent_seat_requires_actor_ref_and_positive_context_budget() -> None:
    with pytest.raises(ValidationError):
        seat_module.AgentSeat.model_validate(
            {
                "seat_ref": "seat.governance.ceo.primary",
                "project_ref": "project.boardroom-os",
                "role_profile_ref": "role.governance.bootstrap",
                "role_category": "governance",
                "capability_tags": ["team.composition"],
                "model_execution_profile_ref": "model.governance.ceo",
                "skill_refs": ["skill.governance.ceo"],
                "context_budget_tokens": 4096,
                "lifecycle_status": "created",
            }
        )

    with pytest.raises(ValidationError):
        seat_module.AgentSeat.model_validate(
            {
                "seat_ref": "seat.governance.ceo.primary",
                "actor_ref": "actor.ceo",
                "project_ref": "project.boardroom-os",
                "role_profile_ref": "role.governance.bootstrap",
                "role_category": "governance",
                "capability_tags": ["team.composition"],
                "model_execution_profile_ref": "model.governance.ceo",
                "skill_refs": ["skill.governance.ceo"],
                "context_budget_tokens": 0,
                "lifecycle_status": "created",
            }
        )



def test_seat_lifecycle_rejects_replace_without_replacement() -> None:
    with pytest.raises(ValidationError, match="replacement_seat_ref"):
        _seat_lifecycle_event(action="replaced", seat=_agent_seat(lifecycle_status="replaced"))



def test_seat_lifecycle_bootstrap_actor_can_only_activate_initial_ceo_seat() -> None:
    created_seat = _agent_seat()
    active_seat = _agent_seat(lifecycle_status="active")
    projector = _seat_projector(
        seat_payloads={
            "payload:seat-created": _seat_lifecycle_event(seat=created_seat),
            "payload:seat-activated": _seat_lifecycle_event(
                graph_version=3,
                action="activated",
                seat=active_seat,
            ),
        }
    )

    projection = projector.project(
        events=(
            _seat_event(
                event_id="evt-seat-created",
                event_type=EventType.SEAT_CREATED,
                payload_ref="payload:seat-created",
                graph_version=2,
                actor_ref="actor.bootstrap",
            ),
            _seat_event(
                event_id="evt-seat-activated",
                event_type=EventType.SEAT_ACTIVATED,
                payload_ref="payload:seat-activated",
                graph_version=3,
                actor_ref="actor.bootstrap",
            ),
        ),
        governance_authority=_governance_authority(),
        role_profiles=_governance_projection(),
        model_execution_profiles=_model_registry(),
    )

    assert projection.active_seats[created_seat.seat_ref].lifecycle_status is seat_module.SeatLifecycleStatus.ACTIVE



def test_bootstrap_actor_requires_seat_lifecycle_write_scope() -> None:
    created_seat = _agent_seat()
    active_seat = _agent_seat(lifecycle_status="active")
    projector = _seat_projector(
        seat_payloads={
            "payload:seat-created": _seat_lifecycle_event(seat=created_seat),
            "payload:seat-activated": _seat_lifecycle_event(
                graph_version=3,
                action="activated",
                seat=active_seat,
            ),
        }
    )

    with pytest.raises(seat_module.SeatLifecycleProjectionError, match="seat_lifecycle_write"):
        projector.project(
            events=(
                _seat_event(
                    event_id="evt-seat-created",
                    event_type=EventType.SEAT_CREATED,
                    payload_ref="payload:seat-created",
                    graph_version=2,
                    actor_ref="actor.bootstrap",
                ),
                _seat_event(
                    event_id="evt-seat-activated",
                    event_type=EventType.SEAT_ACTIVATED,
                    payload_ref="payload:seat-activated",
                    graph_version=3,
                    actor_ref="actor.bootstrap",
                ),
            ),
            governance_authority=_governance_authority(
                authority_scope=("role_profile_write",),
            ),
            role_profiles=_governance_projection(),
            model_execution_profiles=_model_registry(),
        )



def test_seat_lifecycle_rejects_static_field_rewrite_on_activation() -> None:
    created_seat = _agent_seat()
    active_seat_with_changed_model = _agent_seat(
        lifecycle_status="active",
        model_execution_profile_ref={"value": "model.governance.ceo.alternate"},
    )
    model_registry = ModelExecutionProfileRegistry.from_profiles(
        _model_profile(),
        _model_profile(
            model_execution_profile_id=ModelExecutionProfileId(
                value="model.governance.ceo.alternate"
            ),
        ),
    )
    projector = _seat_projector(
        seat_payloads={
            "payload:seat-created": _seat_lifecycle_event(seat=created_seat),
            "payload:seat-activated": _seat_lifecycle_event(
                graph_version=3,
                action="activated",
                seat=active_seat_with_changed_model,
            ),
        }
    )

    with pytest.raises(seat_module.SeatLifecycleProjectionError, match="static seat fields"):
        projector.project(
            events=(
                _seat_event(
                    event_id="evt-seat-created",
                    event_type=EventType.SEAT_CREATED,
                    payload_ref="payload:seat-created",
                    graph_version=2,
                    actor_ref="actor.bootstrap",
                ),
                _seat_event(
                    event_id="evt-seat-activated",
                    event_type=EventType.SEAT_ACTIVATED,
                    payload_ref="payload:seat-activated",
                    graph_version=3,
                    actor_ref="actor.bootstrap",
                ),
            ),
            governance_authority=_governance_authority(),
            role_profiles=_governance_projection(),
            model_execution_profiles=model_registry,
        )



def test_bootstrap_actor_cannot_activate_second_seat_after_ceo_exists() -> None:
    first_created = _agent_seat()
    first_active = _agent_seat(lifecycle_status="active")
    second_created = _agent_seat(
        seat_ref={"value": "seat.governance.ceo.secondary"},
        actor_ref={"value": "actor.governance.second"},
    )
    projector = _seat_projector(
        seat_payloads={
            "payload:seat-1-created": _seat_lifecycle_event(seat=first_created),
            "payload:seat-1-activated": _seat_lifecycle_event(
                graph_version=3,
                action="activated",
                seat=first_active,
            ),
            "payload:seat-2-created": _seat_lifecycle_event(
                graph_version=4,
                seat=second_created,
            ),
        }
    )

    with pytest.raises(seat_module.SeatLifecycleProjectionError, match="bootstrap actor"):
        projector.project(
            events=(
                _seat_event(
                    event_id="evt-seat-1-created",
                    event_type=EventType.SEAT_CREATED,
                    payload_ref="payload:seat-1-created",
                    graph_version=2,
                    actor_ref="actor.bootstrap",
                ),
                _seat_event(
                    event_id="evt-seat-1-activated",
                    event_type=EventType.SEAT_ACTIVATED,
                    payload_ref="payload:seat-1-activated",
                    graph_version=3,
                    actor_ref="actor.bootstrap",
                ),
                _seat_event(
                    event_id="evt-seat-2-created",
                    event_type=EventType.SEAT_CREATED,
                    payload_ref="payload:seat-2-created",
                    graph_version=4,
                    actor_ref="actor.bootstrap",
                ),
            ),
            governance_authority=_governance_authority(),
            role_profiles=_governance_projection(),
            model_execution_profiles=_model_registry(),
        )



def test_replaced_seat_is_terminal_and_not_active() -> None:
    old_created = _agent_seat()
    old_active = _agent_seat(lifecycle_status="active")
    replacement_created = _agent_seat(
        seat_ref={"value": "seat.governance.ceo.replacement"},
        actor_ref={"value": "actor.governance.replacement"},
    )
    replacement_active = _agent_seat(
        seat_ref={"value": "seat.governance.ceo.replacement"},
        actor_ref={"value": "actor.governance.replacement"},
        lifecycle_status="active",
    )
    old_replaced = _agent_seat(lifecycle_status="replaced")
    projector = _seat_projector(
        seat_payloads={
            "payload:old-created": _seat_lifecycle_event(seat=old_created),
            "payload:old-activated": _seat_lifecycle_event(
                graph_version=3,
                action="activated",
                seat=old_active,
            ),
            "payload:new-created": _seat_lifecycle_event(
                graph_version=4,
                action="created",
                actor_ref={"value": "actor.ceo"},
                seat=replacement_created,
            ),
            "payload:new-activated": _seat_lifecycle_event(
                graph_version=5,
                action="activated",
                actor_ref={"value": "actor.ceo"},
                seat=replacement_active,
            ),
            "payload:old-replaced": _seat_lifecycle_event(
                graph_version=6,
                action="replaced",
                actor_ref={"value": "actor.ceo"},
                seat=old_replaced,
                replacement_seat_ref={"value": "seat.governance.ceo.replacement"},
            ),
            "payload:old-reactivated": _seat_lifecycle_event(
                graph_version=7,
                action="activated",
                actor_ref={"value": "actor.governance.replacement"},
                seat=old_active,
            ),
        }
    )

    projection = projector.project(
        events=(
            _seat_event(
                event_id="evt-old-created",
                event_type=EventType.SEAT_CREATED,
                payload_ref="payload:old-created",
                graph_version=2,
                actor_ref="actor.bootstrap",
            ),
            _seat_event(
                event_id="evt-old-activated",
                event_type=EventType.SEAT_ACTIVATED,
                payload_ref="payload:old-activated",
                graph_version=3,
                actor_ref="actor.bootstrap",
            ),
            _seat_event(
                event_id="evt-new-created",
                event_type=EventType.SEAT_CREATED,
                payload_ref="payload:new-created",
                graph_version=4,
                actor_ref="actor.ceo",
            ),
            _seat_event(
                event_id="evt-new-activated",
                event_type=EventType.SEAT_ACTIVATED,
                payload_ref="payload:new-activated",
                graph_version=5,
                actor_ref="actor.ceo",
            ),
            _seat_event(
                event_id="evt-old-replaced",
                event_type=EventType.SEAT_REPLACED,
                payload_ref="payload:old-replaced",
                graph_version=6,
                actor_ref="actor.ceo",
            ),
        ),
        governance_authority=_governance_authority(),
        role_profiles=_governance_projection(),
        model_execution_profiles=_model_registry(),
    )

    assert old_active.seat_ref not in projection.active_seats
    assert projection.active_seats[replacement_active.seat_ref].seat_ref == replacement_active.seat_ref
    assert projection.replacement_refs[old_active.seat_ref] == replacement_active.seat_ref

    with pytest.raises(seat_module.SeatLifecycleProjectionError, match="terminal"):
        projector.project(
            events=(
                _seat_event(
                    event_id="evt-old-created",
                    event_type=EventType.SEAT_CREATED,
                    payload_ref="payload:old-created",
                    graph_version=2,
                    actor_ref="actor.bootstrap",
                ),
                _seat_event(
                    event_id="evt-old-activated",
                    event_type=EventType.SEAT_ACTIVATED,
                    payload_ref="payload:old-activated",
                    graph_version=3,
                    actor_ref="actor.bootstrap",
                ),
                _seat_event(
                    event_id="evt-new-created",
                    event_type=EventType.SEAT_CREATED,
                    payload_ref="payload:new-created",
                    graph_version=4,
                    actor_ref="actor.ceo",
                ),
                _seat_event(
                    event_id="evt-new-activated",
                    event_type=EventType.SEAT_ACTIVATED,
                    payload_ref="payload:new-activated",
                    graph_version=5,
                    actor_ref="actor.ceo",
                ),
                _seat_event(
                    event_id="evt-old-replaced",
                    event_type=EventType.SEAT_REPLACED,
                    payload_ref="payload:old-replaced",
                    graph_version=6,
                    actor_ref="actor.ceo",
                ),
                _seat_event(
                    event_id="evt-old-reactivated",
                    event_type=EventType.SEAT_ACTIVATED,
                    payload_ref="payload:old-reactivated",
                    graph_version=7,
                    actor_ref="actor.governance.replacement",
                ),
            ),
            governance_authority=_governance_authority(),
            role_profiles=_governance_projection(),
            model_execution_profiles=_model_registry(),
        )



def test_agent_seat_capabilities_must_be_role_subset() -> None:
    projector = _seat_projector(
        seat_payloads={
            "payload:seat-created": _seat_lifecycle_event(
                seat=_agent_seat(capability_tags=["team.composition", "task.implementation"]),
            ),
        }
    )

    with pytest.raises(seat_module.SeatLifecycleProjectionError, match="subset"):
        projector.project(
            events=(
                _seat_event(
                    event_id="evt-seat-created",
                    event_type=EventType.SEAT_CREATED,
                    payload_ref="payload:seat-created",
                    graph_version=2,
                    actor_ref="actor.bootstrap",
                ),
            ),
            governance_authority=_governance_authority(),
            role_profiles=_governance_projection(),
            model_execution_profiles=_model_registry(),
        )
