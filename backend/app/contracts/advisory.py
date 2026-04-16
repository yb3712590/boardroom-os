from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field, model_validator

from app.contracts.common import StrictModel

AdvisoryTriggerType = Literal["CONSTRAINT_CHANGE"]
AdvisoryStatus = Literal[
    "OPEN",
    "DRAFTING",
    "PENDING_ANALYSIS",
    "PENDING_BOARD_CONFIRMATION",
    "APPLIED",
    "ANALYSIS_REJECTED",
    "DISMISSED",
]
GovernanceApprovalMode = Literal["AUTO_CEO", "EXPERT_GATED"]
GovernanceAuditMode = Literal["MINIMAL", "TICKET_TRACE", "FULL_TIMELINE"]
AdvisoryTurnActorType = Literal["board", "ceo", "architect"]


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


class BoardAdvisoryTurn(StrictModel):
    turn_id: str = Field(min_length=1)
    actor_type: AdvisoryTurnActorType
    content: str = Field(min_length=1)
    created_at: datetime


class GraphPatchProposal(StrictModel):
    proposal_ref: str = Field(min_length=1)
    workflow_id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    base_graph_version: str = Field(min_length=1)
    proposal_summary: str = Field(min_length=1)
    pros: list[str] = Field(default_factory=list)
    cons: list[str] = Field(default_factory=list)
    risk_alerts: list[str] = Field(default_factory=list)
    impact_summary: str = Field(min_length=1)
    freeze_node_ids: list[str] = Field(default_factory=list)
    unfreeze_node_ids: list[str] = Field(default_factory=list)
    focus_node_ids: list[str] = Field(default_factory=list)
    source_decision_pack_ref: str = Field(min_length=1)
    proposal_hash: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_patch_targets(self) -> "GraphPatchProposal":
        freeze_node_ids = {node_id for node_id in self.freeze_node_ids if node_id}
        unfreeze_node_ids = {node_id for node_id in self.unfreeze_node_ids if node_id}
        if freeze_node_ids & unfreeze_node_ids:
            raise ValueError("graph patch proposal cannot freeze and unfreeze the same node.")
        if not freeze_node_ids and not unfreeze_node_ids and not self.focus_node_ids:
            raise ValueError("graph patch proposal must change at least one node.")
        return self


class GraphPatch(StrictModel):
    patch_ref: str = Field(min_length=1)
    workflow_id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    proposal_ref: str = Field(min_length=1)
    base_graph_version: str = Field(min_length=1)
    freeze_node_ids: list[str] = Field(default_factory=list)
    unfreeze_node_ids: list[str] = Field(default_factory=list)
    focus_node_ids: list[str] = Field(default_factory=list)
    reason_summary: str = Field(min_length=1)
    patch_hash: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_patch_targets(self) -> "GraphPatch":
        freeze_node_ids = {node_id for node_id in self.freeze_node_ids if node_id}
        unfreeze_node_ids = {node_id for node_id in self.unfreeze_node_ids if node_id}
        if freeze_node_ids & unfreeze_node_ids:
            raise ValueError("graph patch cannot freeze and unfreeze the same node.")
        if not freeze_node_ids and not unfreeze_node_ids and not self.focus_node_ids:
            raise ValueError("graph patch must change at least one node.")
        return self


class BoardAdvisorySession(StrictModel):
    session_id: str = Field(min_length=1)
    workflow_id: str = Field(min_length=1)
    approval_id: str = Field(min_length=1)
    review_pack_id: str = Field(min_length=1)
    trigger_type: AdvisoryTriggerType
    source_version: str = Field(min_length=1)
    governance_profile_ref: str = Field(min_length=1)
    affected_nodes: list[str] = Field(default_factory=list)
    working_turns: list[BoardAdvisoryTurn] = Field(default_factory=list)
    decision_pack_refs: list[str] = Field(default_factory=list)
    board_decision: BoardAdvisoryDecision | None = None
    latest_patch_proposal_ref: str | None = None
    latest_patch_proposal: GraphPatchProposal | None = None
    approved_patch_ref: str | None = None
    approved_patch: GraphPatch | None = None
    patched_graph_version: str | None = None
    latest_timeline_index_ref: str | None = None
    latest_transcript_archive_artifact_ref: str | None = None
    timeline_archive_version_int: int | None = Field(default=None, ge=1)
    focus_node_ids: list[str] = Field(default_factory=list)
    latest_analysis_error: str | None = None
    status: AdvisoryStatus
