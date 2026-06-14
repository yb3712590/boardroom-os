from enum import StrEnum

from pydantic import BaseModel, ConfigDict, field_validator


class NonEmptyEventValue(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    value: str

    @field_validator("value")
    @classmethod
    def _reject_empty_value(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("value must not be empty")
        return normalized


class EventId(NonEmptyEventValue):
    pass


class EventRef(NonEmptyEventValue):
    pass


class ProjectRef(NonEmptyEventValue):
    pass


class ActorRef(NonEmptyEventValue):
    pass


class EventPayloadRef(NonEmptyEventValue):
    pass


class EventType(StrEnum):
    TICKET_CREATED = "ticket_created"
    TICKET_LEASED = "ticket_leased"
    TICKET_BLOCKED = "ticket_blocked"
    TICKET_CHECKED = "ticket_checked"
    TICKET_COMPLETED = "ticket_completed"
    TICKET_REWORKED = "ticket_reworked"
    BOOTSTRAP_GOVERNANCE_AUTHORITY = "bootstrap_governance_authority"
    ROLE_PROFILE_REGISTERED = "role_profile_registered"
    ROLE_PROFILE_REPLACED = "role_profile_replaced"
    ROLE_PROFILE_SUPERSEDED = "role_profile_superseded"
    SEAT_CREATED = "seat_created"
    SEAT_ACTIVATED = "seat_activated"
    SEAT_DEACTIVATED = "seat_deactivated"
    SEAT_REPLACED = "seat_replaced"
    SEAT_SUPERSEDED = "seat_superseded"
    SEAT_ASSIGNED = "seat_assigned"
    EXECUTION_STARTED = "execution_started"
    PROVIDER_ATTEMPT_RECORDED = "provider_attempt_recorded"
    TOOL_ATTEMPT_RECORDED = "tool_attempt_recorded"
    WORK_PRODUCT_SUBMITTED = "work_product_submitted"
    COMMAND_RUN_RECORDED = "command_run_recorded"
    CLOSEOUT_COMMITTED = "closeout_committed"
    REWORK_REQUESTED = "rework_requested"
    REWORK_PLANNED = "rework_planned"
    REWORK_GRAPH_PATCH_REVIEWED = "rework_graph_patch_reviewed"
    REWORK_GRAPH_PATCH_APPROVED = "rework_graph_patch_approved"
    REWORK_TICKET_CREATED = "rework_ticket_created"
    REWORK_ATTEMPT_STARTED = "rework_attempt_started"
    REWORK_ATTEMPT_SUBMITTED = "rework_attempt_submitted"
    REWORK_REVIEWED = "rework_reviewed"
    REWORK_ACCEPTED = "rework_accepted"
    REWORK_ESCALATED = "rework_escalated"
    REWORK_EXHAUSTED = "rework_exhausted"
