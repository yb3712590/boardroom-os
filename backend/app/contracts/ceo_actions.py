from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import Field

from app.contracts.common import StrictModel
from app.contracts.commands import DispatchIntent, ExecutionContract, MeetingType


class CEOActionType(StrEnum):
    CREATE_TICKET = "CREATE_TICKET"
    RETRY_TICKET = "RETRY_TICKET"
    HIRE_EMPLOYEE = "HIRE_EMPLOYEE"
    REQUEST_MEETING = "REQUEST_MEETING"
    ESCALATE_TO_BOARD = "ESCALATE_TO_BOARD"
    NO_ACTION = "NO_ACTION"


class CEOCreateTicketPayload(StrictModel):
    workflow_id: str = Field(min_length=1)
    node_id: str = Field(min_length=1)
    role_profile_ref: str = Field(min_length=1)
    output_schema_ref: str = Field(min_length=1)
    execution_contract: ExecutionContract | None = None
    dispatch_intent: DispatchIntent | None = None
    summary: str = Field(min_length=1)
    parent_ticket_id: str | None = None


class CEORetryTicketPayload(StrictModel):
    workflow_id: str = Field(min_length=1)
    ticket_id: str = Field(min_length=1)
    node_id: str = Field(min_length=1)
    reason: str = Field(min_length=1)


class CEOHireEmployeePayload(StrictModel):
    workflow_id: str = Field(min_length=1)
    role_type: str = Field(min_length=1)
    role_profile_refs: list[str] = Field(min_length=1)
    request_summary: str = Field(min_length=1)
    employee_id_hint: str | None = None
    provider_id: str | None = None


class CEORequestMeetingPayload(StrictModel):
    workflow_id: str = Field(min_length=1)
    meeting_type: Literal[MeetingType.TECHNICAL_DECISION]
    source_node_id: str = Field(min_length=1)
    source_ticket_id: str = Field(min_length=1)
    topic: str = Field(min_length=1)
    participant_employee_ids: list[str] = Field(min_length=2, max_length=4)
    recorder_employee_id: str = Field(min_length=1)
    input_artifact_refs: list[str] = Field(default_factory=list)
    reason: str = Field(min_length=1)


class CEOEscalateToBoardPayload(StrictModel):
    workflow_id: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    target_ref: str | None = None
    review_type: str | None = None


class CEONoActionPayload(StrictModel):
    reason: str = Field(min_length=1)


class CEOCreateTicketAction(StrictModel):
    action_type: Literal[CEOActionType.CREATE_TICKET]
    payload: CEOCreateTicketPayload


class CEORetryTicketAction(StrictModel):
    action_type: Literal[CEOActionType.RETRY_TICKET]
    payload: CEORetryTicketPayload


class CEOHireEmployeeAction(StrictModel):
    action_type: Literal[CEOActionType.HIRE_EMPLOYEE]
    payload: CEOHireEmployeePayload


class CEORequestMeetingAction(StrictModel):
    action_type: Literal[CEOActionType.REQUEST_MEETING]
    payload: CEORequestMeetingPayload


class CEOEscalateToBoardAction(StrictModel):
    action_type: Literal[CEOActionType.ESCALATE_TO_BOARD]
    payload: CEOEscalateToBoardPayload


class CEONoAction(StrictModel):
    action_type: Literal[CEOActionType.NO_ACTION]
    payload: CEONoActionPayload


CEOAction = Annotated[
    CEOCreateTicketAction
    | CEORetryTicketAction
    | CEOHireEmployeeAction
    | CEORequestMeetingAction
    | CEOEscalateToBoardAction
    | CEONoAction,
    Field(discriminator="action_type"),
]


class CEOActionBatch(StrictModel):
    summary: str = Field(min_length=1)
    actions: list[CEOAction] = Field(default_factory=list)

