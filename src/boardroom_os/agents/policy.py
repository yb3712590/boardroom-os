from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from boardroom_os.agents.categories import RoleCategory
from boardroom_os.agents.profiles import RoleProfile
from boardroom_os.agents.seat import (
    TEAM_COMPOSITION_CAPABILITY,
    AgentSeat,
    AgentSeatRef,
    SeatDemand,
)
from boardroom_os.agents.skills import CapabilityTag, RoleProfileId
from boardroom_os.events.record import EventRecord
from boardroom_os.events.types import ActorRef, EventPayloadRef, EventType


class SeatPolicyError(ValueError):
    pass


class SeatPolicyMatch(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    seat_ref: AgentSeatRef | None
    blockers: tuple[str, ...]


class SeatPolicy:
    def __init__(self, *, active_seats: dict[AgentSeatRef, AgentSeat]) -> None:
        self._active_seats = active_seats

    def match(self, demand: SeatDemand) -> SeatPolicyMatch:
        matching_role_seats = tuple(
            seat
            for seat in self._active_seats.values()
            if seat.role_category is demand.required_role_category
        )
        required_capability_tags = set(demand.required_capability_tags)
        for seat in matching_role_seats:
            if required_capability_tags.issubset(set(seat.capability_tags)):
                return SeatPolicyMatch(seat_ref=seat.seat_ref, blockers=())

        if not matching_role_seats:
            return SeatPolicyMatch(
                seat_ref=None,
                blockers=(
                    "team composition gap: missing active seat for role category: "
                    f"{demand.required_role_category.value}",
                ),
            )

        missing_capability_tags = ", ".join(
            capability_tag.value for capability_tag in demand.required_capability_tags
        )
        return SeatPolicyMatch(
            seat_ref=None,
            blockers=(
                "team composition gap: missing active seat for capability tags: "
                f"{missing_capability_tags}",
            ),
        )

    def require_independent_checker(
        self,
        worker_seat_ref: AgentSeatRef,
        checker_seat_ref: AgentSeatRef,
    ) -> None:
        if worker_seat_ref == checker_seat_ref:
            raise SeatPolicyError(
                "independent checker requires different active seats for worker and checker"
            )

        worker_seat = self._active_seats.get(worker_seat_ref)
        if worker_seat is None:
            raise SeatPolicyError(
                f"worker seat must be an active seat: {worker_seat_ref.value}"
            )

        checker_seat = self._active_seats.get(checker_seat_ref)
        if checker_seat is None:
            raise SeatPolicyError(
                f"checker seat must be an active seat: {checker_seat_ref.value}"
            )

        if worker_seat.role_category is checker_seat.role_category:
            raise SeatPolicyError(
                "independent checker requires different role categories for worker and checker"
            )


class BootstrapGovernanceAuthority(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    graph_version: Literal[1] = 1
    authority_scope: tuple[str, ...]

    @field_validator("authority_scope")
    @classmethod
    def _reject_empty_authority_scope(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if not values:
            raise ValueError("authority_scope must not be empty")
        normalized_values: list[str] = []
        for value in values:
            normalized = value.strip()
            if not normalized:
                raise ValueError("authority_scope must not contain empty values")
            normalized_values.append(normalized)
        return tuple(normalized_values)

    def grants(self, scope: str) -> bool:
        return scope in self.authority_scope


class GovernanceAuthorityProjection(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    bootstrap_actor_ref: ActorRef
    bootstrap_authority: BootstrapGovernanceAuthority

    def grants(self, scope: str) -> bool:
        return self.bootstrap_authority.grants(scope)


class GovernanceAuthorityProjector:
    def __init__(self, payload_resolver: object) -> None:
        self._payload_resolver = payload_resolver

    def project(
        self,
        events: tuple[EventRecord, ...],
    ) -> GovernanceAuthorityProjection:
        if not events:
            raise SeatPolicyError("events must not be empty")

        bootstrap_event: EventRecord | None = None
        for event in sorted(events, key=lambda item: item.graph_version):
            if event.event_type is EventType.BOOTSTRAP_GOVERNANCE_AUTHORITY:
                if event.graph_version != 1:
                    raise SeatPolicyError(
                        "bootstrap governance authority event must be graph_version=1"
                    )
                if bootstrap_event is not None:
                    raise SeatPolicyError("duplicate bootstrap governance authority")
                bootstrap_event = event
                continue

            if bootstrap_event is None:
                raise SeatPolicyError("missing bootstrap governance authority")

        if bootstrap_event is None:
            raise SeatPolicyError("missing bootstrap governance authority")

        if len(bootstrap_event.payload_refs) != 1:
            raise SeatPolicyError(
                "bootstrap governance authority event must have exactly one payload_ref"
            )

        authority = self._resolve_bootstrap_governance_authority(
            bootstrap_event.payload_refs[0]
        )
        return GovernanceAuthorityProjection(
            bootstrap_actor_ref=bootstrap_event.actor_ref,
            bootstrap_authority=authority,
        )

    def _resolve_bootstrap_governance_authority(
        self,
        payload_ref: EventPayloadRef,
    ) -> BootstrapGovernanceAuthority:
        try:
            return self._payload_resolver.resolve_bootstrap_governance_authority(payload_ref)
        except Exception as error:
            raise SeatPolicyError(
                f"payload_ref could not be resolved: {payload_ref.value}"
            ) from error


class RoleProfileChangeAction(StrEnum):
    REGISTERED = "registered"
    REPLACED = "replaced"
    SUPERSEDED = "superseded"


class RoleProfileChange(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    graph_version: int = Field(gt=0)
    action: RoleProfileChangeAction
    actor_ref: ActorRef
    role_profile: RoleProfile


class RoleProfileProjection(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    profiles: tuple[RoleProfile, ...]

    @classmethod
    def apply_changes(
        cls,
        *,
        changes: tuple[RoleProfileChange, ...],
        governance_authority: GovernanceAuthorityProjection,
        active_seats: dict[AgentSeatRef, AgentSeat] | None = None,
    ) -> "RoleProfileProjection":
        profiles: list[RoleProfile] = []
        active_seats = active_seats or {}
        for change in sorted(changes, key=lambda item: item.graph_version):
            if change.action is not RoleProfileChangeAction.REGISTERED:
                raise SeatPolicyError(
                    f"unsupported role profile change action: {change.action.value}"
                )

            if change.actor_ref == governance_authority.bootstrap_actor_ref:
                cls._apply_bootstrap_registration(
                    change=change,
                    profiles=profiles,
                    governance_authority=governance_authority,
                )
                continue

            if not cls._actor_has_active_governance_authority(
                actor_ref=change.actor_ref,
                active_seats=active_seats,
            ):
                if profiles:
                    raise SeatPolicyError(
                        "role profile registration requires active governance seat"
                    )
                raise SeatPolicyError("non-bootstrap actor role profile registration is closed")

            profiles.append(change.role_profile)

        return cls(profiles=tuple(profiles))

    @classmethod
    def _apply_bootstrap_registration(
        cls,
        *,
        change: RoleProfileChange,
        profiles: list[RoleProfile],
        governance_authority: GovernanceAuthorityProjection,
    ) -> None:
        if profiles:
            raise SeatPolicyError(
                "bootstrap actor may only register the first governance role"
            )

        role_profile = change.role_profile
        if role_profile.role_category is not RoleCategory.GOVERNANCE:
            raise SeatPolicyError(
                "bootstrap actor may only register the first governance role"
            )

        if TEAM_COMPOSITION_CAPABILITY not in role_profile.capability_tags:
            raise SeatPolicyError(
                "bootstrap governance role must include capability_tag team.composition"
            )

        if not governance_authority.grants("role_profile_write"):
            raise SeatPolicyError(
                "bootstrap governance authority missing scope: role_profile_write"
            )

        profiles.append(role_profile)

    @classmethod
    def _actor_has_active_governance_authority(
        cls,
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

    def contains(self, role_profile_id: RoleProfileId) -> bool:
        return any(
            profile.role_profile_id == role_profile_id for profile in self.profiles
        )
