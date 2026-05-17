from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from boardroom_os.agents.categories import RoleCategory
from boardroom_os.agents.policy import (
    BootstrapGovernanceAuthority,
    GovernanceAuthorityProjection,
    GovernanceAuthorityProjector,
    RoleProfileChange,
    RoleProfileChangeAction,
    RoleProfileProjection,
    SeatPolicyError,
)
from boardroom_os.agents.profiles import RoleProfile
from boardroom_os.agents.seat import (
    TEAM_COMPOSITION_CAPABILITY,
    AgentSeat,
    AgentSeatRef,
    ModelExecutionProfileRegistryView,
    SeatLifecycleEvent,
    SeatLifecycleProjection,
    SeatLifecycleProjectionError,
    SeatLifecycleProjector,
)
from boardroom_os.events.record import EventRecord
from boardroom_os.events.types import ActorRef, EventPayloadRef, EventType


class AgentTeamProjectionError(ValueError):
    pass


class AgentTeamPayloadResolver(Protocol):
    def resolve_bootstrap_governance_authority(
        self,
        payload_ref: EventPayloadRef,
    ) -> BootstrapGovernanceAuthority: ...

    def resolve_role_profile_change(
        self,
        payload_ref: EventPayloadRef,
    ) -> RoleProfileChange | dict[str, object]: ...

    def resolve_seat_lifecycle_event(
        self,
        payload_ref: EventPayloadRef,
    ) -> SeatLifecycleEvent: ...


class AgentTeamProjection(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    graph_version: int = Field(gt=0)
    role_profiles: RoleProfileProjection
    seat_lifecycle: SeatLifecycleProjection

    @property
    def active_seats(self) -> dict[AgentSeatRef, AgentSeat]:
        return self.seat_lifecycle.active_seats


class RoleProfileChangeProjector:
    def __init__(self, *, payload_resolver: AgentTeamPayloadResolver) -> None:
        self._payload_resolver = payload_resolver

    def project(self, event: EventRecord) -> RoleProfileChange:
        if event.event_type is not EventType.ROLE_PROFILE_REGISTERED:
            raise AgentTeamProjectionError(
                f"unsupported role profile change event: {event.event_type.value}"
            )
        if len(event.payload_refs) != 1:
            raise AgentTeamProjectionError(
                "role profile event must have exactly one payload_ref"
            )

        payload_ref = event.payload_refs[0]
        try:
            raw_payload = self._payload_resolver.resolve_role_profile_change(payload_ref)
        except Exception as error:
            raise AgentTeamProjectionError(
                f"role profile payload_ref could not be resolved: {payload_ref.value}"
            ) from error

        try:
            change = RoleProfileChange.model_validate(raw_payload)
        except ValidationError as error:
            raise AgentTeamProjectionError(
                f"role profile payload is invalid: {payload_ref.value}"
            ) from error

        if change.action is not RoleProfileChangeAction.REGISTERED:
            raise AgentTeamProjectionError(
                f"unsupported role profile change action: {change.action.value}"
            )
        if change.graph_version != event.graph_version:
            raise AgentTeamProjectionError(
                "role profile payload graph_version does not match event graph_version"
            )
        if change.actor_ref != event.actor_ref:
            raise AgentTeamProjectionError(
                "role profile payload actor_ref does not match event actor_ref"
            )
        return change


class AgentTeamProjector:
    _ROLE_PROFILE_EVENT_TYPES = {
        EventType.ROLE_PROFILE_REGISTERED,
        EventType.ROLE_PROFILE_REPLACED,
        EventType.ROLE_PROFILE_SUPERSEDED,
    }
    _SEAT_LIFECYCLE_EVENT_TYPES = {
        EventType.SEAT_CREATED,
        EventType.SEAT_ACTIVATED,
        EventType.SEAT_DEACTIVATED,
        EventType.SEAT_REPLACED,
        EventType.SEAT_SUPERSEDED,
    }

    def __init__(
        self,
        *,
        payload_resolver: AgentTeamPayloadResolver,
    ) -> None:
        self._payload_resolver = payload_resolver
        self._governance_authority_projector = GovernanceAuthorityProjector(payload_resolver)
        self._role_profile_change_projector = RoleProfileChangeProjector(
            payload_resolver=payload_resolver
        )
        self._seat_lifecycle_projector = SeatLifecycleProjector(
            payload_resolver=payload_resolver
        )

    def project(
        self,
        events: tuple[EventRecord, ...],
        *,
        model_execution_profiles: ModelExecutionProfileRegistryView,
    ) -> AgentTeamProjection:
        self._validate_events(events)
        governance_authority = self._project_governance_authority(events)

        profiles: list[RoleProfile] = []
        role_profiles = RoleProfileProjection(profiles=())
        seat_events: list[EventRecord] = []
        seat_lifecycle = SeatLifecycleProjection()

        for event in events:
            if event.event_type in self._ROLE_PROFILE_EVENT_TYPES:
                change = self._role_profile_change_projector.project(event)
                self._apply_role_profile_change(
                    change=change,
                    governance_authority=governance_authority,
                    profiles=profiles,
                    active_seats=seat_lifecycle.active_seats,
                )
                role_profiles = RoleProfileProjection(profiles=tuple(profiles))
                continue

            if event.event_type in self._SEAT_LIFECYCLE_EVENT_TYPES:
                seat_events.append(event)
                seat_lifecycle = self._project_seat_lifecycle(
                    events=tuple(seat_events),
                    governance_authority=governance_authority,
                    role_profiles=role_profiles,
                    model_execution_profiles=model_execution_profiles,
                )

        return AgentTeamProjection(
            graph_version=events[-1].graph_version,
            role_profiles=role_profiles,
            seat_lifecycle=seat_lifecycle,
        )

    def _validate_events(self, events: tuple[EventRecord, ...]) -> None:
        if not events:
            raise AgentTeamProjectionError("events must not be empty")

        project_ref = events[0].project_ref
        previous_graph_version = 0
        for event in events:
            if event.project_ref != project_ref:
                raise AgentTeamProjectionError("events must share a single project_ref")
            if event.graph_version <= previous_graph_version:
                raise AgentTeamProjectionError(
                    "events must have strictly increasing graph_version"
                )
            previous_graph_version = event.graph_version

    def _project_governance_authority(
        self,
        events: tuple[EventRecord, ...],
    ) -> GovernanceAuthorityProjection:
        bootstrap_count = sum(
            1
            for event in events
            if event.event_type is EventType.BOOTSTRAP_GOVERNANCE_AUTHORITY
        )
        if bootstrap_count == 0:
            raise AgentTeamProjectionError("missing bootstrap governance authority")
        if bootstrap_count > 1:
            raise AgentTeamProjectionError("duplicate bootstrap governance authority")

        try:
            return self._governance_authority_projector.project(events)
        except SeatPolicyError as error:
            raise AgentTeamProjectionError(str(error)) from error

    def _apply_role_profile_change(
        self,
        *,
        change: RoleProfileChange,
        governance_authority: GovernanceAuthorityProjection,
        profiles: list[RoleProfile],
        active_seats: dict[AgentSeatRef, AgentSeat],
    ) -> None:
        if change.actor_ref == governance_authority.bootstrap_actor_ref:
            self._apply_bootstrap_registration(
                change=change,
                governance_authority=governance_authority,
                profiles=profiles,
            )
            return

        if not self._actor_has_active_governance_authority(
            actor_ref=change.actor_ref,
            active_seats=active_seats,
        ):
            if profiles:
                raise AgentTeamProjectionError(
                    "role profile registration requires active governance seat"
                )
            raise AgentTeamProjectionError(
                "non-bootstrap actor role profile registration is closed"
            )

        self._require_unique_role_profile_id(
            role_profile=change.role_profile,
            profiles=profiles,
        )
        profiles.append(change.role_profile)

    def _apply_bootstrap_registration(
        self,
        *,
        change: RoleProfileChange,
        governance_authority: GovernanceAuthorityProjection,
        profiles: list[RoleProfile],
    ) -> None:
        if profiles:
            raise AgentTeamProjectionError(
                "bootstrap actor may only register the first governance role"
            )

        role_profile = change.role_profile
        if role_profile.role_category is not RoleCategory.GOVERNANCE:
            raise AgentTeamProjectionError(
                "bootstrap actor may only register the first governance role"
            )
        if TEAM_COMPOSITION_CAPABILITY not in role_profile.capability_tags:
            raise AgentTeamProjectionError(
                "bootstrap governance role must include capability_tag team.composition"
            )
        if not governance_authority.grants("role_profile_write"):
            raise AgentTeamProjectionError(
                "bootstrap governance authority missing scope: role_profile_write"
            )

        self._require_unique_role_profile_id(
            role_profile=role_profile,
            profiles=profiles,
        )
        profiles.append(role_profile)

    def _require_unique_role_profile_id(
        self,
        *,
        role_profile: RoleProfile,
        profiles: list[RoleProfile],
    ) -> None:
        if any(
            existing_profile.role_profile_id == role_profile.role_profile_id
            for existing_profile in profiles
        ):
            raise AgentTeamProjectionError(
                "role_profile_id must be unique: "
                f"{role_profile.role_profile_id.value}"
            )

    def _actor_has_active_governance_authority(
        self,
        *,
        actor_ref: ActorRef,
        active_seats: dict[AgentSeatRef, AgentSeat],
    ) -> bool:
        return any(
            seat.actor_ref == actor_ref
            and seat.role_category is RoleCategory.GOVERNANCE
            and TEAM_COMPOSITION_CAPABILITY in seat.capability_tags
            for seat in active_seats.values()
        )

    def _project_seat_lifecycle(
        self,
        *,
        events: tuple[EventRecord, ...],
        governance_authority: GovernanceAuthorityProjection,
        role_profiles: RoleProfileProjection,
        model_execution_profiles: ModelExecutionProfileRegistryView,
    ) -> SeatLifecycleProjection:
        try:
            return self._seat_lifecycle_projector.project(
                events=events,
                governance_authority=governance_authority,
                role_profiles=role_profiles,
                model_execution_profiles=model_execution_profiles,
            )
        except SeatLifecycleProjectionError as error:
            message = str(error)
            if "payload_ref could not be resolved" in message:
                message = message.replace(
                    "payload_ref could not be resolved",
                    "seat lifecycle payload_ref could not be resolved",
                )
            raise AgentTeamProjectionError(message) from error
