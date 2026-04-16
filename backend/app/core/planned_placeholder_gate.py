from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from app.contracts.ticket_graph import TicketGraphSnapshot
from app.core.runtime_node_lifecycle import (
    REASON_CODE_PLANNED_PLACEHOLDER_NOT_MATERIALIZED,
    resolve_runtime_node_lifecycle,
)

if TYPE_CHECKING:
    from app.db.repository import ControlPlaneRepository


@dataclass(frozen=True)
class PlannedPlaceholderGateBlock:
    workflow_id: str
    node_id: str
    graph_node_id: str
    graph_version: str
    reason_code: str
    source_component: str = "workflow_auto_advance"
    materialization_hint: str = "create_ticket"


def detect_planned_placeholder_gate_block(
    repository: "ControlPlaneRepository",
    *,
    workflow_id: str,
    snapshot: dict[str, Any],
) -> PlannedPlaceholderGateBlock | None:
    ticket_graph_payload = snapshot.get("ticket_graph") or {}
    if not isinstance(ticket_graph_payload, dict) or not ticket_graph_payload:
        return None
    focus_node_ids = [
        str(node_id).strip()
        for node_id in list((snapshot.get("replan_focus") or {}).get("focus_node_ids") or [])
        if str(node_id).strip()
    ]
    if not focus_node_ids:
        return None

    ticket_graph_snapshot = TicketGraphSnapshot.model_validate(ticket_graph_payload)
    for node_id in focus_node_ids:
        node_view = resolve_runtime_node_lifecycle(
            repository,
            workflow_id,
            node_id,
            graph_snapshot=ticket_graph_snapshot,
        )
        if node_view.materialization_state != "planned_placeholder":
            continue
        return PlannedPlaceholderGateBlock(
            workflow_id=workflow_id,
            node_id=node_id,
            graph_node_id=node_view.graph_node_id or node_id,
            graph_version=ticket_graph_snapshot.graph_version,
            reason_code=REASON_CODE_PLANNED_PLACEHOLDER_NOT_MATERIALIZED,
        )
    return None


__all__ = [
    "PlannedPlaceholderGateBlock",
    "detect_planned_placeholder_gate_block",
]
