from __future__ import annotations

from typing import Any

from pydantic import Field

from app.contracts.common import StrictModel


class RecentAssetDigest(StrictModel):
    source_ref: str = Field(min_length=1)
    asset_kind: str = Field(min_length=1)
    summary: str = Field(min_length=1)


class ProjectionSnapshot(StrictModel):
    workflow_status: str = Field(min_length=1)
    graph_version: str = Field(min_length=1)
    governance_profile_ref: str = Field(min_length=1)
    approval_mode: str = Field(min_length=1)
    audit_mode: str = Field(min_length=1)
    ready_nodes: list[str] = Field(default_factory=list)
    blocked_nodes: list[str] = Field(default_factory=list)
    open_incidents: list[str] = Field(default_factory=list)
    open_board_items: list[str] = Field(default_factory=list)
    pending_expert_gates: list[str] = Field(default_factory=list)
    recent_asset_digests: list[RecentAssetDigest] = Field(default_factory=list)
    reuse_candidates: dict[str, Any] = Field(default_factory=dict)
    memory_budget_ratios: dict[str, int] = Field(default_factory=dict)
    default_read_order: list[str] = Field(default_factory=list)


class ReplanFocus(StrictModel):
    task_sensemaking: dict[str, Any] = Field(default_factory=dict)
    capability_plan: dict[str, Any] = Field(default_factory=dict)
    controller_state: dict[str, Any] = Field(default_factory=dict)
    meeting_candidates: list[dict[str, Any]] = Field(default_factory=list)
