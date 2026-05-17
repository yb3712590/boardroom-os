from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator, model_validator

from boardroom_os.agents.categories import RoleCategory


class AgentSeatRef(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    value: str

    @field_validator("value")
    @classmethod
    def _reject_empty_value(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("value must not be empty")
        return normalized


from boardroom_os.agents.profiles import ModelExecutionProfileId, RoleProfile
from boardroom_os.agents.skills import (
    CapabilityTag,
    RoleProfileId,
    SkillRef,
    _normalize_ref_fields,
)
from boardroom_os.events.record import EventRecord
from boardroom_os.events.types import ActorRef, EventPayloadRef, EventType, ProjectRef

TEAM_COMPOSITION_CAPABILITY = CapabilityTag(value="team.composition")


class SeatLifecycleStatus(StrEnum):
    CREATED = "created"
    ACTIVE = "active"
    DEACTIVATED = "deactivated"
    REPLACED = "replaced"
    SUPERSEDED = "superseded"


class SeatLifecycleAction(StrEnum):
    CREATED = "created"
    ACTIVATED = "activated"
    DEACTIVATED = "deactivated"
    REPLACED = "replaced"
    SUPERSEDED = "superseded"


class SeatDemand(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    required_role_category: RoleCategory
    required_capability_tags: tuple[CapabilityTag, ...]

    @model_validator(mode="before")
    @classmethod
    def _normalize_yaml_refs(cls, data: Any) -> Any:
        return _normalize_ref_fields(
            data,
            {},
            {"required_capability_tags": CapabilityTag},
        )

    @field_validator("required_capability_tags")
    @classmethod
    def _reject_empty_required_capability_tags(
        cls,
        values: tuple[CapabilityTag, ...],
    ) -> tuple[CapabilityTag, ...]:
        if not values:
            raise ValueError("required_capability_tags must not be empty")
        return values


def seat_demand_blockers(*, seat: "AgentSeat", demand: SeatDemand) -> tuple[str, ...]:
    if seat.role_category is not demand.required_role_category:
        return (
            "team composition gap: role category mismatch: "
            f"{seat.role_category.value} != {demand.required_role_category.value}",
        )

    missing_capability_tags = tuple(
        capability_tag.value
        for capability_tag in demand.required_capability_tags
        if capability_tag not in seat.capability_tags
    )
    if missing_capability_tags:
        return (
            "team composition gap: missing capability tags: "
            + ", ".join(missing_capability_tags),
        )

    return ()


class AgentSeat(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    version: Literal[1] = 1
    seat_ref: AgentSeatRef
    actor_ref: ActorRef
    project_ref: ProjectRef
    role_profile_ref: RoleProfileId
    role_category: RoleCategory
    capability_tags: tuple[CapabilityTag, ...]
    model_execution_profile_ref: ModelExecutionProfileId
    skill_refs: tuple[SkillRef, ...]
    context_budget_tokens: StrictInt
    lifecycle_status: SeatLifecycleStatus

    @model_validator(mode="before")
    @classmethod
    def _normalize_yaml_refs(cls, data: Any) -> Any:
        return _normalize_ref_fields(
            data,
            {
                "seat_ref": AgentSeatRef,
                "actor_ref": ActorRef,
                "project_ref": ProjectRef,
                "role_profile_ref": RoleProfileId,
                "model_execution_profile_ref": ModelExecutionProfileId,
            },
            {
                "capability_tags": CapabilityTag,
                "skill_refs": SkillRef,
            },
        )

    @field_validator("capability_tags")
    @classmethod
    def _reject_empty_capability_tags(
        cls,
        values: tuple[CapabilityTag, ...],
    ) -> tuple[CapabilityTag, ...]:
        if not values:
            raise ValueError("capability_tags must not be empty")
        return values

    @field_validator("skill_refs")
    @classmethod
    def _reject_empty_skill_refs(cls, values: tuple[SkillRef, ...]) -> tuple[SkillRef, ...]:
        if not values:
            raise ValueError("skill_refs must not be empty")
        return values

    @field_validator("context_budget_tokens")
    @classmethod
    def _reject_non_positive_context_budget(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("context_budget_tokens must be positive")
        return value


class SeatLifecycleEvent(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    graph_version: int = Field(gt=0)
    action: SeatLifecycleAction
    actor_ref: ActorRef
    seat: AgentSeat
    replacement_seat_ref: AgentSeatRef | None = None

    @model_validator(mode="before")
    @classmethod
    def _normalize_yaml_refs(cls, data: Any) -> Any:
        return _normalize_ref_fields(
            data,
            {
                "actor_ref": ActorRef,
                "replacement_seat_ref": AgentSeatRef,
            },
        )

    @model_validator(mode="after")
    def _require_replacement_for_replaced(self) -> "SeatLifecycleEvent":
        if self.action is SeatLifecycleAction.REPLACED and self.replacement_seat_ref is None:
            raise ValueError("replacement_seat_ref is required for replaced lifecycle events")
        if self.action is not SeatLifecycleAction.REPLACED and self.replacement_seat_ref is not None:
            raise ValueError("replacement_seat_ref is only allowed for replaced lifecycle events")
        return self


class SeatLifecycleProjection(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    graph_version: int = 0
    seats: dict[AgentSeatRef, AgentSeat] = Field(default_factory=dict)
    active_seats: dict[AgentSeatRef, AgentSeat] = Field(default_factory=dict)
    replacement_refs: dict[AgentSeatRef, AgentSeatRef] = Field(default_factory=dict)


class SeatLifecycleProjectionError(ValueError):
    pass


class SeatLifecyclePayloadResolver(Protocol):
    def resolve_seat_lifecycle_event(
        self,
        payload_ref: EventPayloadRef,
    ) -> SeatLifecycleEvent: ...


class GovernanceAuthorityView(Protocol):
    bootstrap_actor_ref: ActorRef

    def grants(self, scope: str) -> bool: ...


class RoleProfileProjectionView(Protocol):
    profiles: tuple[RoleProfile, ...]


class ModelExecutionProfileRegistryView(Protocol):
    def contains(self, model_execution_profile_ref: ModelExecutionProfileId) -> bool: ...


class SeatLifecycleProjector:
    def __init__(self, *, payload_resolver: SeatLifecyclePayloadResolver) -> None:
        self._payload_resolver = payload_resolver

    def project(
        self,
        *,
        events: tuple[EventRecord, ...],
        governance_authority: GovernanceAuthorityView,
        role_profiles: RoleProfileProjectionView,
        model_execution_profiles: ModelExecutionProfileRegistryView,
    ) -> SeatLifecycleProjection:
        seats_by_ref: dict[AgentSeatRef, AgentSeat] = {}
        active_seats: dict[AgentSeatRef, AgentSeat] = {}
        replacement_refs: dict[AgentSeatRef, AgentSeatRef] = {}
        graph_version = 0

        for event in sorted(events, key=lambda item: item.graph_version):
            action = self._seat_action_for_event(event.event_type)
            if action is None:
                continue
            if len(event.payload_refs) != 1:
                raise SeatLifecycleProjectionError(
                    "seat lifecycle event must have exactly one payload_ref"
                )

            lifecycle_event = self._resolve_seat_lifecycle_event(event.payload_refs[0])
            if lifecycle_event.action is not action:
                raise SeatLifecycleProjectionError(
                    "seat lifecycle payload action does not match event type"
                )
            if lifecycle_event.graph_version != event.graph_version:
                raise SeatLifecycleProjectionError(
                    "seat lifecycle payload graph_version does not match event graph_version"
                )
            if lifecycle_event.actor_ref != event.actor_ref:
                raise SeatLifecycleProjectionError(
                    "seat lifecycle payload actor_ref does not match event actor_ref"
                )
            if lifecycle_event.seat.project_ref != event.project_ref:
                raise SeatLifecycleProjectionError(
                    "seat project_ref must match event project_ref"
                )

            self._validate_seat(
                seat=lifecycle_event.seat,
                role_profiles=role_profiles,
                model_execution_profiles=model_execution_profiles,
            )
            self._require_actor_authorized(
                actor_ref=event.actor_ref,
                lifecycle_event=lifecycle_event,
                governance_authority=governance_authority,
                seats_by_ref=seats_by_ref,
                active_seats=active_seats,
            )
            self._apply_lifecycle_event(
                lifecycle_event=lifecycle_event,
                seats_by_ref=seats_by_ref,
                active_seats=active_seats,
                replacement_refs=replacement_refs,
            )
            graph_version = event.graph_version

        return SeatLifecycleProjection(
            graph_version=graph_version,
            seats=seats_by_ref,
            active_seats=active_seats,
            replacement_refs=replacement_refs,
        )

    def _resolve_seat_lifecycle_event(
        self,
        payload_ref: EventPayloadRef,
    ) -> SeatLifecycleEvent:
        try:
            return self._payload_resolver.resolve_seat_lifecycle_event(payload_ref)
        except Exception as error:
            raise SeatLifecycleProjectionError(
                f"payload_ref could not be resolved: {payload_ref.value}"
            ) from error

    def _seat_action_for_event(self, event_type: EventType) -> SeatLifecycleAction | None:
        return {
            EventType.SEAT_CREATED: SeatLifecycleAction.CREATED,
            EventType.SEAT_ACTIVATED: SeatLifecycleAction.ACTIVATED,
            EventType.SEAT_DEACTIVATED: SeatLifecycleAction.DEACTIVATED,
            EventType.SEAT_REPLACED: SeatLifecycleAction.REPLACED,
            EventType.SEAT_SUPERSEDED: SeatLifecycleAction.SUPERSEDED,
        }.get(event_type)

    def _validate_seat(
        self,
        *,
        seat: AgentSeat,
        role_profiles: RoleProfileProjectionView,
        model_execution_profiles: ModelExecutionProfileRegistryView,
    ) -> None:
        role_profile = self._resolve_role_profile(role_profiles, seat.role_profile_ref)
        if seat.role_category is not role_profile.role_category:
            raise SeatLifecycleProjectionError("seat role_category must match role profile")
        if not model_execution_profiles.contains(seat.model_execution_profile_ref):
            raise SeatLifecycleProjectionError(
                "unknown model_execution_profile_ref: "
                f"{seat.model_execution_profile_ref.value}"
            )

        role_capability_tags = set(role_profile.capability_tags)
        extra_capability_tags = tuple(
            capability_tag.value
            for capability_tag in seat.capability_tags
            if capability_tag not in role_capability_tags
        )
        if extra_capability_tags:
            raise SeatLifecycleProjectionError(
                "seat capability_tags must be a non-empty subset of role capability_tags: "
                + ", ".join(extra_capability_tags)
            )

    def _resolve_role_profile(
        self,
        role_profiles: RoleProfileProjectionView,
        role_profile_ref: RoleProfileId,
    ) -> RoleProfile:
        for role_profile in role_profiles.profiles:
            if role_profile.role_profile_id == role_profile_ref:
                return role_profile
        raise SeatLifecycleProjectionError(
            f"unknown role_profile_ref: {role_profile_ref.value}"
        )

    def _require_actor_authorized(
        self,
        *,
        actor_ref: ActorRef,
        lifecycle_event: SeatLifecycleEvent,
        governance_authority: GovernanceAuthorityView,
        seats_by_ref: dict[AgentSeatRef, AgentSeat],
        active_seats: dict[AgentSeatRef, AgentSeat],
    ) -> None:
        if self._actor_has_active_governance_authority(actor_ref, active_seats):
            return
        if actor_ref == governance_authority.bootstrap_actor_ref:
            self._require_bootstrap_window(
                lifecycle_event=lifecycle_event,
                governance_authority=governance_authority,
                seats_by_ref=seats_by_ref,
                active_seats=active_seats,
            )
            return
        raise SeatLifecycleProjectionError(
            f"actor is not authorized for seat lifecycle changes: {actor_ref.value}"
        )

    def _actor_has_active_governance_authority(
        self,
        actor_ref: ActorRef,
        active_seats: dict[AgentSeatRef, AgentSeat],
    ) -> bool:
        for seat in active_seats.values():
            if seat.actor_ref != actor_ref:
                continue
            if seat.role_category is not RoleCategory.GOVERNANCE:
                continue
            if TEAM_COMPOSITION_CAPABILITY not in seat.capability_tags:
                continue
            return True
        return False

    def _require_bootstrap_window(
        self,
        *,
        lifecycle_event: SeatLifecycleEvent,
        governance_authority: GovernanceAuthorityView,
        seats_by_ref: dict[AgentSeatRef, AgentSeat],
        active_seats: dict[AgentSeatRef, AgentSeat],
    ) -> None:
        if not governance_authority.grants("seat_lifecycle_write"):
            raise SeatLifecycleProjectionError(
                "bootstrap governance authority missing scope: seat_lifecycle_write"
            )

        seat = lifecycle_event.seat
        if seat.role_category is not RoleCategory.GOVERNANCE:
            raise SeatLifecycleProjectionError(
                "bootstrap actor may only create and activate the initial governance CEO seat"
            )
        if TEAM_COMPOSITION_CAPABILITY not in seat.capability_tags:
            raise SeatLifecycleProjectionError(
                "bootstrap actor may only create and activate the initial governance CEO seat"
            )

        current_seat = seats_by_ref.get(seat.seat_ref)
        if not seats_by_ref:
            if lifecycle_event.action is SeatLifecycleAction.CREATED:
                return
            raise SeatLifecycleProjectionError(
                "bootstrap actor may only create and activate the initial governance CEO seat"
            )

        if (
            lifecycle_event.action is SeatLifecycleAction.ACTIVATED
            and current_seat is not None
            and current_seat.seat_ref == seat.seat_ref
            and current_seat.lifecycle_status is SeatLifecycleStatus.CREATED
            and not active_seats
            and len(seats_by_ref) == 1
        ):
            return

        raise SeatLifecycleProjectionError(
            "bootstrap actor may only create and activate the initial governance CEO seat"
        )

    def _apply_lifecycle_event(
        self,
        *,
        lifecycle_event: SeatLifecycleEvent,
        seats_by_ref: dict[AgentSeatRef, AgentSeat],
        active_seats: dict[AgentSeatRef, AgentSeat],
        replacement_refs: dict[AgentSeatRef, AgentSeatRef],
    ) -> None:
        action = lifecycle_event.action
        seat = lifecycle_event.seat
        current_seat = seats_by_ref.get(seat.seat_ref)
        expected_status = self._status_for_action(action)
        if seat.lifecycle_status is not expected_status:
            raise SeatLifecycleProjectionError(
                f"seat lifecycle_status must be {expected_status.value} for action {action.value}"
            )

        if current_seat is None:
            if action is not SeatLifecycleAction.CREATED:
                raise SeatLifecycleProjectionError(
                    f"invalid seat lifecycle transition: none -> {action.value}"
                )
            seats_by_ref[seat.seat_ref] = seat
            return

        current_status = current_seat.lifecycle_status
        if current_status in {
            SeatLifecycleStatus.REPLACED,
            SeatLifecycleStatus.SUPERSEDED,
        }:
            raise SeatLifecycleProjectionError(
                f"seat is terminal and cannot change: {seat.seat_ref.value}"
            )

        if action is SeatLifecycleAction.CREATED:
            raise SeatLifecycleProjectionError(
                f"seat_ref must be unique: {seat.seat_ref.value}"
            )

        self._require_static_seat_fields_unchanged(current_seat, seat)

        if action is SeatLifecycleAction.ACTIVATED:
            if current_status not in {
                SeatLifecycleStatus.CREATED,
                SeatLifecycleStatus.DEACTIVATED,
            }:
                raise SeatLifecycleProjectionError(
                    f"invalid seat lifecycle transition: {current_status.value} -> active"
                )
            seats_by_ref[seat.seat_ref] = seat
            active_seats[seat.seat_ref] = seat
            return
        if action is SeatLifecycleAction.DEACTIVATED:
            if current_status not in {
                SeatLifecycleStatus.CREATED,
                SeatLifecycleStatus.ACTIVE,
            }:
                raise SeatLifecycleProjectionError(
                    f"invalid seat lifecycle transition: {current_status.value} -> deactivated"
                )
            seats_by_ref[seat.seat_ref] = seat
            active_seats.pop(seat.seat_ref, None)
            return
        if action is SeatLifecycleAction.REPLACED:
            if current_status is not SeatLifecycleStatus.ACTIVE:
                raise SeatLifecycleProjectionError(
                    f"invalid seat lifecycle transition: {current_status.value} -> replaced"
                )
            replacement_seat_ref = lifecycle_event.replacement_seat_ref
            if replacement_seat_ref is None:
                raise SeatLifecycleProjectionError(
                    "replacement_seat_ref is required for replaced lifecycle events"
                )
            if replacement_seat_ref == seat.seat_ref:
                raise SeatLifecycleProjectionError("replacement seat cannot point to itself")
            replacement_seat = seats_by_ref.get(replacement_seat_ref)
            if replacement_seat is None:
                raise SeatLifecycleProjectionError(
                    f"replacement seat does not exist: {replacement_seat_ref.value}"
                )
            if replacement_seat.project_ref != seat.project_ref:
                raise SeatLifecycleProjectionError(
                    "replacement seat must belong to the same project"
                )
            if replacement_seat_ref not in active_seats:
                raise SeatLifecycleProjectionError(
                    f"replacement seat must already be active: {replacement_seat_ref.value}"
                )
            seats_by_ref[seat.seat_ref] = seat
            active_seats.pop(seat.seat_ref, None)
            replacement_refs[seat.seat_ref] = replacement_seat_ref
            return
        if action is SeatLifecycleAction.SUPERSEDED:
            if current_status not in {
                SeatLifecycleStatus.ACTIVE,
                SeatLifecycleStatus.DEACTIVATED,
            }:
                raise SeatLifecycleProjectionError(
                    f"invalid seat lifecycle transition: {current_status.value} -> superseded"
                )
            seats_by_ref[seat.seat_ref] = seat
            active_seats.pop(seat.seat_ref, None)
            return

        raise SeatLifecycleProjectionError(
            f"unsupported seat lifecycle action: {action.value}"
        )

    def _require_static_seat_fields_unchanged(
        self,
        current_seat: AgentSeat,
        next_seat: AgentSeat,
    ) -> None:
        static_field_names = (
            "seat_ref",
            "actor_ref",
            "project_ref",
            "role_profile_ref",
            "role_category",
            "capability_tags",
            "model_execution_profile_ref",
            "skill_refs",
            "context_budget_tokens",
        )
        changed_field_names = tuple(
            field_name
            for field_name in static_field_names
            if getattr(current_seat, field_name) != getattr(next_seat, field_name)
        )
        if changed_field_names:
            raise SeatLifecycleProjectionError(
                "static seat fields must not change during lifecycle events: "
                + ", ".join(changed_field_names)
            )

    def _status_for_action(self, action: SeatLifecycleAction) -> SeatLifecycleStatus:
        return {
            SeatLifecycleAction.CREATED: SeatLifecycleStatus.CREATED,
            SeatLifecycleAction.ACTIVATED: SeatLifecycleStatus.ACTIVE,
            SeatLifecycleAction.DEACTIVATED: SeatLifecycleStatus.DEACTIVATED,
            SeatLifecycleAction.REPLACED: SeatLifecycleStatus.REPLACED,
            SeatLifecycleAction.SUPERSEDED: SeatLifecycleStatus.SUPERSEDED,
        }[action]
