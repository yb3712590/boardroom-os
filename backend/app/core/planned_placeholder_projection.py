from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.contracts.advisory import GraphPatchAddedNode
from app.core.constants import INCIDENT_STATUS_OPEN, INCIDENT_TYPE_PLANNED_PLACEHOLDER_GATE_BLOCKED
from app.core.graph_patch_reducer import load_graph_patch_event_records
from app.core.planned_placeholder_constants import (
    PLANNED_PLACEHOLDER_MATERIALIZATION_HINT_CREATE_TICKET,
    PLANNED_PLACEHOLDER_REASON_CODE,
    PLANNED_PLACEHOLDER_STATUS_BLOCKED,
    PLANNED_PLACEHOLDER_STATUS_PLANNED,
)
from app.core.versioning import resolve_workflow_graph_version

if TYPE_CHECKING:
    import sqlite3

    from app.db.repository import ControlPlaneRepository


@dataclass(frozen=True)
class PlannedPlaceholderProjectionRow:
    workflow_id: str
    node_id: str
    graph_node_id: str
    graph_version: str
    status: str
    reason_code: str | None
    open_incident_id: str | None
    materialization_hint: str | None
    updated_at: str
    version: int


def rebuild_planned_placeholder_projections(
    repository: "ControlPlaneRepository",
    *,
    connection: "sqlite3.Connection",
) -> list[dict[str, object]]:
    workflow_rows = repository.list_workflow_projections(connection)
    projections: list[dict[str, object]] = []

    for workflow in workflow_rows:
        workflow_id = str(workflow.get("workflow_id") or "").strip()
        if not workflow_id:
            continue
        placeholder_nodes = _reduce_placeholder_nodes_for_workflow(
            repository,
            connection=connection,
            workflow_id=workflow_id,
        )
        if not placeholder_nodes:
            continue
        workflow_updated_at, workflow_version = _resolve_workflow_projection_version(
            connection,
            workflow_id=workflow_id,
        )
        graph_version = resolve_workflow_graph_version(
            repository,
            workflow_id,
            connection=connection,
        )
        open_incidents_by_node_id = _load_open_placeholder_incidents_by_node_id(
            repository,
            connection=connection,
            workflow_id=workflow_id,
        )
        materialized_node_ids = _load_materialized_node_ids(
            connection,
            workflow_id=workflow_id,
        )

        for node_id, placeholder_node in sorted(placeholder_nodes.items()):
            if node_id in materialized_node_ids:
                continue
            open_incident = open_incidents_by_node_id.get(node_id)
            materialization_hint = (
                str(open_incident.get("payload", {}).get("materialization_hint") or "").strip() or None
                if open_incident is not None
                else None
            )
            reason_code = (
                str(open_incident.get("payload", {}).get("reason_code") or "").strip() or None
                if open_incident is not None
                else None
            )
            projections.append(
                PlannedPlaceholderProjectionRow(
                    workflow_id=workflow_id,
                    node_id=node_id,
                    graph_node_id=node_id,
                    graph_version=graph_version,
                    status=(
                        PLANNED_PLACEHOLDER_STATUS_BLOCKED
                        if open_incident is not None
                        else PLANNED_PLACEHOLDER_STATUS_PLANNED
                    ),
                    reason_code=reason_code or PLANNED_PLACEHOLDER_REASON_CODE,
                    open_incident_id=(
                        str(open_incident.get("incident_id") or "").strip() or None
                        if open_incident is not None
                        else None
                    ),
                    materialization_hint=(
                        materialization_hint or PLANNED_PLACEHOLDER_MATERIALIZATION_HINT_CREATE_TICKET
                    ),
                    updated_at=workflow_updated_at,
                    version=workflow_version,
                ).__dict__
            )

    return sorted(projections, key=lambda item: (str(item["workflow_id"]), str(item["node_id"])))


def _reduce_placeholder_nodes_for_workflow(
    repository: "ControlPlaneRepository",
    *,
    connection: "sqlite3.Connection",
    workflow_id: str,
) -> dict[str, GraphPatchAddedNode]:
    patch_records = load_graph_patch_event_records(
        repository,
        workflow_id,
        connection=connection,
    )
    placeholder_nodes: dict[str, GraphPatchAddedNode] = {}
    for record in patch_records:
        patch = record.patch
        for removed_node_id in list(patch.remove_node_ids or []):
            placeholder_nodes.pop(str(removed_node_id).strip(), None)
        for replacement in list(patch.replacements or []):
            placeholder_nodes.pop(str(replacement.old_node_id).strip(), None)
        for added_node in list(patch.add_nodes or []):
            node_id = str(added_node.node_id).strip()
            if not node_id:
                continue
            placeholder_nodes[node_id] = added_node.model_copy()
    return placeholder_nodes


def _load_materialized_node_ids(
    connection: "sqlite3.Connection",
    *,
    workflow_id: str,
) -> set[str]:
    rows = connection.execute(
        """
        SELECT node_id
        FROM node_projection
        WHERE workflow_id = ?
        """,
        (workflow_id,),
    ).fetchall()
    return {str(row["node_id"]).strip() for row in rows if str(row["node_id"]).strip()}


def _resolve_workflow_projection_version(
    connection: "sqlite3.Connection",
    *,
    workflow_id: str,
) -> tuple[str, int]:
    row = connection.execute(
        """
        SELECT occurred_at, sequence_no
        FROM events
        WHERE workflow_id = ?
        ORDER BY sequence_no DESC
        LIMIT 1
        """,
        (workflow_id,),
    ).fetchone()
    if row is None:
        raise RuntimeError(
            f"planned placeholder projection cannot resolve workflow event version for {workflow_id}."
        )
    return str(row["occurred_at"]), int(row["sequence_no"])


def _load_open_placeholder_incidents_by_node_id(
    repository: "ControlPlaneRepository",
    *,
    connection: "sqlite3.Connection",
    workflow_id: str,
) -> dict[str, dict[str, object]]:
    rows = connection.execute(
        """
        SELECT *
        FROM incident_projection
        WHERE workflow_id = ? AND status = ? AND incident_type = ?
        ORDER BY opened_at DESC, incident_id DESC
        """,
        (
            workflow_id,
            INCIDENT_STATUS_OPEN,
            INCIDENT_TYPE_PLANNED_PLACEHOLDER_GATE_BLOCKED,
        ),
    ).fetchall()
    incidents_by_node_id: dict[str, dict[str, object]] = {}
    for row in rows:
        incident = repository._convert_incident_projection_row(row)
        node_id = str(incident.get("node_id") or "").strip()
        if not node_id or node_id in incidents_by_node_id:
            continue
        incidents_by_node_id[node_id] = incident
    return incidents_by_node_id


__all__ = [
    "PLANNED_PLACEHOLDER_MATERIALIZATION_HINT_CREATE_TICKET",
    "PLANNED_PLACEHOLDER_STATUS_BLOCKED",
    "PLANNED_PLACEHOLDER_STATUS_PLANNED",
    "rebuild_planned_placeholder_projections",
]
