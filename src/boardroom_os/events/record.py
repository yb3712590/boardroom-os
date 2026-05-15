from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator

from boardroom_os.events.types import (
    ActorRef,
    EventId,
    EventPayloadRef,
    EventRef,
    EventType,
    ProjectRef,
)


class EventRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    event_id: EventId
    event_type: EventType
    project_ref: ProjectRef
    actor_ref: ActorRef
    timestamp: datetime
    graph_version: int = Field(gt=0)
    payload_refs: tuple[EventPayloadRef, ...]
    causation_refs: tuple[EventRef, ...] = ()
    correlation_refs: tuple[EventRef, ...] = ()

    @field_validator("timestamp")
    @classmethod
    def _require_timezone(cls, timestamp: datetime) -> datetime:
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise ValueError("timestamp must include timezone")
        return timestamp

    @field_validator("payload_refs")
    @classmethod
    def _reject_empty_payload_refs(
        cls,
        payload_refs: tuple[EventPayloadRef, ...],
    ) -> tuple[EventPayloadRef, ...]:
        if not payload_refs:
            raise ValueError("payload refs must not be empty")
        return payload_refs

    @field_serializer("timestamp")
    def _serialize_timestamp(self, timestamp: datetime) -> str:
        return timestamp.isoformat()

    def stable_dump(self) -> dict[str, object]:
        return self.model_dump(mode="json")
