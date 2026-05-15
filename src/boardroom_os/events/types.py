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
    EXECUTION_STARTED = "execution_started"
    PROVIDER_ATTEMPT_RECORDED = "provider_attempt_recorded"
    TOOL_ATTEMPT_RECORDED = "tool_attempt_recorded"
    WORK_PRODUCT_SUBMITTED = "work_product_submitted"
    COMMAND_RUN_RECORDED = "command_run_recorded"
