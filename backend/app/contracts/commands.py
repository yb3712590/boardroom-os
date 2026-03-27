from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import Field

from app.contracts.common import StrictModel


class CommandAckStatus(StrEnum):
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    DUPLICATE = "DUPLICATE"


class ProjectInitCommand(StrictModel):
    north_star_goal: str = Field(min_length=1)
    hard_constraints: list[str]
    budget_cap: int = Field(ge=0)
    deadline_at: datetime | None = None


class CommandAckEnvelope(StrictModel):
    command_id: str
    idempotency_key: str
    status: CommandAckStatus
    received_at: datetime
    reason: str | None = None
    causation_hint: str | None = None
