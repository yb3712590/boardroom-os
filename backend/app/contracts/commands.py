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


class BoardApproveCommand(StrictModel):
    review_pack_id: str = Field(min_length=1)
    review_pack_version: int = Field(ge=1)
    command_target_version: int = Field(ge=0)
    approval_id: str = Field(min_length=1)
    selected_option_id: str = Field(min_length=1)
    board_comment: str = Field(min_length=1)
    idempotency_key: str = Field(min_length=1)


class BoardRejectCommand(StrictModel):
    review_pack_id: str = Field(min_length=1)
    review_pack_version: int = Field(ge=1)
    command_target_version: int = Field(ge=0)
    approval_id: str = Field(min_length=1)
    board_comment: str = Field(min_length=1)
    rejection_reasons: list[str] = Field(min_length=1)
    idempotency_key: str = Field(min_length=1)


class ConstraintPatch(StrictModel):
    add_rules: list[str]
    remove_rules: list[str]
    replace_rules: list[str]


class ModifyConstraintsCommand(StrictModel):
    review_pack_id: str = Field(min_length=1)
    review_pack_version: int = Field(ge=1)
    command_target_version: int = Field(ge=0)
    approval_id: str = Field(min_length=1)
    constraint_patch: ConstraintPatch
    board_comment: str = Field(min_length=1)
    idempotency_key: str = Field(min_length=1)


class CommandAckEnvelope(StrictModel):
    command_id: str
    idempotency_key: str
    status: CommandAckStatus
    received_at: datetime
    reason: str | None = None
    causation_hint: str | None = None
