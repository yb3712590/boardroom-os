from __future__ import annotations

from typing import Any

from pydantic import Field

from app.contracts.common import StrictModel


class RecentAssetDigest(StrictModel):
    source_ref: str = Field(min_length=1)
    asset_kind: str = Field(min_length=1)
    summary: str = Field(min_length=1)


class ProjectMapSliceDigest(StrictModel):
    process_asset_ref: str = Field(min_length=1)
    workflow_id: str = Field(min_length=1)
    graph_version: str = Field(min_length=1)
    module_paths: list[str] = Field(default_factory=list)
    document_surfaces: list[str] = Field(default_factory=list)
    decision_asset_refs: list[str] = Field(default_factory=list)
    failure_fingerprint_refs: list[str] = Field(default_factory=list)
    source_process_asset_refs: list[str] = Field(default_factory=list)


class FailureFingerprintDigest(StrictModel):
    process_asset_ref: str = Field(min_length=1)
    incident_id: str = Field(min_length=1)
    workflow_id: str = Field(min_length=1)
    incident_type: str = Field(min_length=1)
    severity: str | None = None
    fingerprint: str = Field(min_length=1)
    node_id: str | None = None
    ticket_id: str | None = None
    related_process_asset_refs: list[str] = Field(default_factory=list)


class GraphHealthFindingDigest(StrictModel):
    finding_type: str = Field(min_length=1)
    severity: str = Field(min_length=1)
    affected_nodes: list[str] = Field(default_factory=list)
    metric_value: int | float
    threshold: int | float
    description: str = Field(min_length=1)
    suggested_action: str = Field(min_length=1)


class GraphHealthReportDigest(StrictModel):
    report_id: str = Field(min_length=1)
    workflow_id: str = Field(min_length=1)
    graph_version: str = Field(min_length=1)
    overall_health: str = Field(min_length=1)
    findings: list[GraphHealthFindingDigest] = Field(default_factory=list)
    recommended_actions: list[str] = Field(default_factory=list)


class BoardAdvisorySessionDigest(StrictModel):
    session_id: str = Field(min_length=1)
    approval_id: str = Field(min_length=1)
    review_pack_id: str = Field(min_length=1)
    trigger_type: str = Field(min_length=1)
    status: str = Field(min_length=1)
    source_version: str = Field(min_length=1)
    governance_profile_ref: str = Field(min_length=1)
    affected_nodes: list[str] = Field(default_factory=list)
    decision_pack_refs: list[str] = Field(default_factory=list)
    approved_patch_ref: str | None = None
    decision_action: str | None = None
    board_comment: str | None = None


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
    board_advisory_sessions: list[BoardAdvisorySessionDigest] = Field(default_factory=list)
    project_map_slices: list[ProjectMapSliceDigest] = Field(default_factory=list)
    graph_health_report: GraphHealthReportDigest | None = None
    memory_budget_ratios: dict[str, int] = Field(default_factory=dict)
    default_read_order: list[str] = Field(default_factory=list)


class ReplanFocus(StrictModel):
    task_sensemaking: dict[str, Any] = Field(default_factory=dict)
    capability_plan: dict[str, Any] = Field(default_factory=dict)
    controller_state: dict[str, Any] = Field(default_factory=dict)
    meeting_candidates: list[dict[str, Any]] = Field(default_factory=list)
    latest_advisory_decision: dict[str, Any] | None = None
    failure_fingerprints: list[FailureFingerprintDigest] = Field(default_factory=list)
