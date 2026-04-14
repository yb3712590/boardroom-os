from __future__ import annotations

from pydantic import Field

from app.contracts.common import StrictModel


class TicketGraphReductionIssue(StrictModel):
    issue_code: str
    detail: str
    ticket_id: str | None = None
    node_id: str | None = None
    related_ticket_id: str | None = None


class TicketGraphNode(StrictModel):
    graph_node_id: str
    workflow_id: str
    graph_version: str
    ticket_id: str
    node_id: str
    node_kind: str
    ticket_status: str | None = None
    node_status: str | None = None
    role_profile_ref: str | None = None
    output_schema_ref: str | None = None
    delivery_stage: str | None = None
    parent_ticket_id: str | None = None
    dependency_ticket_ids: list[str] = Field(default_factory=list)
    blocking_reason_code: str | None = None


class TicketGraphEdge(StrictModel):
    edge_type: str
    workflow_id: str
    graph_version: str
    source_graph_node_id: str
    target_graph_node_id: str
    source_ticket_id: str
    target_ticket_id: str
    source_node_id: str
    target_node_id: str


class TicketGraphIndexSummary(StrictModel):
    ready_ticket_ids: list[str] = Field(default_factory=list)
    ready_node_ids: list[str] = Field(default_factory=list)
    blocked_ticket_ids: list[str] = Field(default_factory=list)
    blocked_node_ids: list[str] = Field(default_factory=list)
    reduction_issue_count: int = 0


class TicketGraphSnapshot(StrictModel):
    workflow_id: str
    graph_version: str
    source_adapter: str = "legacy_projection_adapter"
    nodes: list[TicketGraphNode] = Field(default_factory=list)
    edges: list[TicketGraphEdge] = Field(default_factory=list)
    index_summary: TicketGraphIndexSummary = Field(default_factory=TicketGraphIndexSummary)
    reduction_issues: list[TicketGraphReductionIssue] = Field(default_factory=list)
