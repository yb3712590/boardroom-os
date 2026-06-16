from __future__ import annotations

import json
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class V2_090FReworkEntryStatus(StrEnum):
    PASSED_WITHOUT_REWORK_CANDIDATE = "passed_without_rework_candidate"
    REWORK_ACCEPTED_CANDIDATE = "rework_accepted_candidate"
    REWORK_ESCALATED_OR_EXHAUSTED = "rework_escalated_or_exhausted"
    BLOCKED_BY_MISSING_REWORK_ENTRY = "blocked_by_missing_rework_entry"


class V2_090FTicketGraphNodeSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    ticket_id: str
    owner_seat_ref: str
    status: str
    acceptance_ref_count: int = Field(ge=0)
    evidence_obligation_count: int = Field(ge=0)


class V2_090FTicketGraphSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    graph_version: int = Field(gt=0)
    source_ref: str
    nodes: tuple[V2_090FTicketGraphNodeSnapshot, ...]
    edges: tuple[tuple[str, str], ...] = ()
    ticket_graph_patch_ref: str | None = None

    @model_validator(mode="after")
    def _validate_patch_binding(self) -> "V2_090FTicketGraphSnapshot":
        if "after-rework" in self.source_ref and not self.ticket_graph_patch_ref:
            raise ValueError("after-rework graph requires ticket_graph_patch_ref")
        if not self.nodes:
            raise ValueError("ticket graph snapshot nodes must not be empty")
        return self


class V2_090FReworkEntryValidationInput(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    output_root: Path
    workspace_root: Path
    run_id: str
    cycle_id: str
    max_rounds: int = Field(gt=0)
    require_real_provider: bool = True


class V2_090FReworkEntryValidationResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: V2_090FReworkEntryStatus
    before_graph_json_path: Path
    before_graph_mermaid_path: Path
    after_graph_json_path: Path | None = None
    after_graph_mermaid_path: Path | None = None
    blocker_report_path: Path
    rework_request_path: Path | None = None
    rework_plan_path: Path | None = None
    ticket_graph_patch_path: Path | None = None
    terminal_path: Path
    report_path: Path
    checked_refs: tuple[str, ...]

    @model_validator(mode="after")
    def _validate_rework_accepted_paths(self) -> "V2_090FReworkEntryValidationResult":
        if self.status is not V2_090FReworkEntryStatus.REWORK_ACCEPTED_CANDIDATE:
            return self
        required_paths = {
            "after_graph_json_path": self.after_graph_json_path,
            "after_graph_mermaid_path": self.after_graph_mermaid_path,
            "rework_request_path": self.rework_request_path,
            "rework_plan_path": self.rework_plan_path,
            "ticket_graph_patch_path": self.ticket_graph_patch_path,
        }
        missing = [name for name, value in required_paths.items() if value is None]
        if missing:
            raise ValueError(
                "rework_accepted_candidate requires paths: " + ", ".join(missing)
            )
        return self


def _node_ref(node: dict[str, Any]) -> str:
    value = node.get("node_ref") or node.get("ticket_id")
    if not isinstance(value, str) or not value.strip():
        raise ValueError("ticket graph node requires node_ref or ticket_id")
    return value.strip()


def _node_status(node: dict[str, Any]) -> str:
    value = node.get("status", "unknown")
    if not isinstance(value, str) or not value.strip():
        raise ValueError("ticket graph node status must be text")
    return value.strip()


def _count_list_field(node: dict[str, Any], field_name: str) -> int:
    value = node.get(field_name)
    if value is None:
        return 0
    if not isinstance(value, list):
        raise ValueError(f"ticket graph {field_name} must be a list")
    return len(value)


def load_v2_090f_ticket_graph_snapshot(output_root: Path) -> V2_090FTicketGraphSnapshot:
    """Read generated ticket graph and return a before-rework snapshot."""

    source_path = Path(output_root) / "00-boardroom" / "generated-ticket-graph.json"
    data = json.loads(source_path.read_text(encoding="utf-8"))
    ticket_graph = data.get("provider_output", {}).get("ticket_graph")
    if not isinstance(ticket_graph, dict):
        raise ValueError("generated-ticket-graph.json requires provider_output.ticket_graph")
    raw_nodes = ticket_graph.get("nodes")
    if not isinstance(raw_nodes, list) or not raw_nodes:
        raise ValueError("ticket graph snapshot nodes must not be empty")

    nodes: list[V2_090FTicketGraphNodeSnapshot] = []
    edge_set: set[tuple[str, str]] = set()
    for raw_node in raw_nodes:
        if not isinstance(raw_node, dict):
            raise ValueError("ticket graph node must be an object")
        ticket_id = _node_ref(raw_node)
        owner_seat_ref = raw_node.get("owner_seat_ref")
        if not isinstance(owner_seat_ref, str) or not owner_seat_ref.strip():
            raise ValueError("ticket graph node requires owner_seat_ref")
        nodes.append(
            V2_090FTicketGraphNodeSnapshot(
                ticket_id=ticket_id,
                owner_seat_ref=owner_seat_ref.strip(),
                status=_node_status(raw_node),
                acceptance_ref_count=_count_list_field(raw_node, "acceptance_refs"),
                evidence_obligation_count=_count_list_field(raw_node, "evidence_obligations"),
            )
        )
        depends_on = raw_node.get("depends_on", [])
        if depends_on is None:
            depends_on = []
        if not isinstance(depends_on, list):
            raise ValueError("ticket graph depends_on must be a list")
        for dependency in depends_on:
            if not isinstance(dependency, str) or not dependency.strip():
                raise ValueError("ticket graph depends_on entries must be text")
            edge_set.add((dependency.strip(), ticket_id))

    return V2_090FTicketGraphSnapshot(
        graph_version=ticket_graph["graph_version"],
        source_ref="00-boardroom/generated-ticket-graph.json",
        nodes=tuple(nodes),
        edges=tuple(sorted(edge_set)),
    )


def render_v2_090f_ticket_graph_mermaid(snapshot: V2_090FTicketGraphSnapshot) -> str:
    """Render a graph TD Mermaid view for a V2-090F ticket graph snapshot."""

    labels = {
        node.ticket_id: (
            f"{node.ticket_id}\\n{node.owner_seat_ref}\\n{node.status}\\n"
            f"AC:{node.acceptance_ref_count} EV:{node.evidence_obligation_count}"
        )
        for node in snapshot.nodes
    }
    lines = ["graph TD"]
    for node in snapshot.nodes:
        lines.append(f'  "{labels[node.ticket_id]}"')
    for source, target in snapshot.edges:
        source_label = labels.get(source, source)
        target_label = labels.get(target, target)
        lines.append(f'  "{source_label}" --> "{target_label}"')
    return "\n".join(lines) + "\n"
