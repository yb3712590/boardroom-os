from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from app.contracts.common import StrictModel

AdvisoryTriggerType = Literal["CONSTRAINT_CHANGE"]
AdvisoryStatus = Literal["OPEN", "DECIDED", "DISMISSED"]
GovernanceApprovalMode = Literal["AUTO_CEO", "EXPERT_GATED"]
GovernanceAuditMode = Literal["MINIMAL", "TICKET_TRACE", "FULL_TIMELINE"]


class GovernancePatch(StrictModel):
    approval_mode: GovernanceApprovalMode | None = None
    audit_mode: GovernanceAuditMode | None = None

    @model_validator(mode="after")
    def validate_non_empty(self) -> "GovernancePatch":
        if self.approval_mode is None and self.audit_mode is None:
            raise ValueError("governance_patch must change approval_mode or audit_mode.")
        return self


class BoardAdvisoryDecision(StrictModel):
    decision_action: Literal["MODIFY_CONSTRAINTS"]
    board_comment: str = Field(min_length=1)
    constraint_patch: dict[str, list[str]] = Field(default_factory=dict)
    governance_patch: GovernancePatch | None = None
    source_artifact_ref: str | None = None


class BoardAdvisorySession(StrictModel):
    session_id: str = Field(min_length=1)
    workflow_id: str = Field(min_length=1)
    approval_id: str = Field(min_length=1)
    review_pack_id: str = Field(min_length=1)
    trigger_type: AdvisoryTriggerType
    source_version: str = Field(min_length=1)
    governance_profile_ref: str = Field(min_length=1)
    affected_nodes: list[str] = Field(default_factory=list)
    decision_pack_refs: list[str] = Field(default_factory=list)
    board_decision: BoardAdvisoryDecision | None = None
    approved_patch_ref: str | None = None
    status: AdvisoryStatus
