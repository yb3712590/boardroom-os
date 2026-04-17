from __future__ import annotations

from contextlib import nullcontext
from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.contracts.ticket_graph import TicketGraphSnapshot
from app.core.graph_identity import GRAPH_LANE_EXECUTION
from app.core.planned_placeholder_constants import (
    PLANNED_PLACEHOLDER_STATUS_BLOCKED,
    PLANNED_PLACEHOLDER_STATUS_PLANNED,
)
from app.core.ticket_graph import build_ticket_graph_snapshot

if TYPE_CHECKING:
    import sqlite3

    from app.db.repository import ControlPlaneRepository


MATERIALIZATION_STATE_MATERIALIZED = "materialized"
MATERIALIZATION_STATE_PLANNED = "planned_placeholder"
MATERIALIZATION_STATE_MISSING = "missing"


class RuntimeNodeViewResolutionError(RuntimeError):
    pass


@dataclass(frozen=True)
class RuntimeNodeView:
    node_id: str
    graph_node_id: str | None
    runtime_node_id: str | None
    ticket_id: str | None
    is_placeholder: bool
    materialization_state: str
    placeholder_status: str | None = None
    reason_code: str | None = None
    open_incident_id: str | None = None
    materialization_hint: str | None = None


def _execution_graph_nodes_by_node_id(
    graph_snapshot: TicketGraphSnapshot,
) -> tuple[dict[str, object], dict[str, object]]:
    materialized_by_node_id: dict[str, object] = {}
    placeholder_by_node_id: dict[str, object] = {}
    for graph_node in graph_snapshot.nodes:
        node_id = str(getattr(graph_node, "node_id", "") or "").strip()
        if not node_id:
            continue
        if str(getattr(graph_node, "graph_lane_kind", "") or "") != GRAPH_LANE_EXECUTION:
            continue
        target = placeholder_by_node_id if bool(getattr(graph_node, "is_placeholder", False)) else materialized_by_node_id
        if node_id in target:
            raise RuntimeNodeViewResolutionError(
                f"runtime node view found multiple execution-lane graph nodes for node_id {node_id}."
            )
        target[node_id] = graph_node
    return materialized_by_node_id, placeholder_by_node_id


def build_runtime_node_views(
    repository: "ControlPlaneRepository",
    workflow_id: str,
    *,
    graph_snapshot: TicketGraphSnapshot | None = None,
    connection: "sqlite3.Connection" | None = None,
) -> dict[str, RuntimeNodeView]:
    if graph_snapshot is None:
        graph_snapshot = build_ticket_graph_snapshot(
            repository,
            workflow_id,
            connection=connection,
        )

    with (
        repository.connection() if connection is None else nullcontext(connection)
    ) as resolved_connection:
        runtime_rows = resolved_connection.execute(
            """
            SELECT *
            FROM runtime_node_projection
            WHERE workflow_id = ?
            ORDER BY graph_node_id ASC
            """,
            (workflow_id,),
        ).fetchall()
        runtime_projection_by_graph_node_id = {
            str(row["graph_node_id"]).strip(): repository._convert_runtime_node_projection_row(row)
            for row in runtime_rows
            if str(row["graph_node_id"]).strip()
        }
        placeholder_rows = resolved_connection.execute(
            """
            SELECT *
            FROM planned_placeholder_projection
            WHERE workflow_id = ?
            ORDER BY node_id ASC
            """,
            (workflow_id,),
        ).fetchall()
        placeholder_projection_by_node_id = {
            str(row["node_id"]).strip(): repository._convert_planned_placeholder_projection_row(row)
            for row in placeholder_rows
            if str(row["node_id"]).strip()
        }

    materialized_graph_nodes, placeholder_graph_nodes = _execution_graph_nodes_by_node_id(graph_snapshot)
    valid_ticket_ids_by_node_id: dict[str, set[str]] = {}
    for graph_node in graph_snapshot.nodes:
        if bool(getattr(graph_node, "is_placeholder", False)):
            continue
        node_id = str(getattr(graph_node, "node_id", "") or "").strip()
        ticket_id = str(getattr(graph_node, "ticket_id", "") or "").strip()
        if node_id and ticket_id:
            valid_ticket_ids_by_node_id.setdefault(node_id, set()).add(ticket_id)
    conflicting_node_ids = sorted(set(materialized_graph_nodes) & set(placeholder_graph_nodes))
    if conflicting_node_ids:
        raise RuntimeNodeViewResolutionError(
            "runtime node view found conflicting materialized and placeholder graph nodes for "
            + ", ".join(conflicting_node_ids)
            + "."
        )

    views: dict[str, RuntimeNodeView] = {}

    for node_id, graph_node in sorted(materialized_graph_nodes.items()):
        graph_node_id = str(getattr(graph_node, "graph_node_id", "") or "").strip()
        runtime_projection = runtime_projection_by_graph_node_id.get(graph_node_id)
        if runtime_projection is None:
            raise RuntimeNodeViewResolutionError(
                "execution graph lane contains materialized nodes without runtime_node_projection: "
                + graph_node_id
                + "."
            )
        runtime_node_id = str(runtime_projection.get("runtime_node_id") or "").strip()
        projection_node_id = str(runtime_projection.get("node_id") or "").strip()
        if (
            projection_node_id != node_id
            or runtime_node_id != str(getattr(graph_node, "runtime_node_id", "") or "").strip()
        ):
            raise RuntimeNodeViewResolutionError(
                f"runtime_node_projection {graph_node_id} does not match graph/runtime node identity."
            )
        latest_ticket_id = str(runtime_projection.get("latest_ticket_id") or "").strip() or None
        graph_ticket_id = str(getattr(graph_node, "ticket_id", "") or "").strip() or None
        valid_ticket_ids = valid_ticket_ids_by_node_id.get(node_id, set())
        if latest_ticket_id is not None and latest_ticket_id not in valid_ticket_ids:
            raise RuntimeNodeViewResolutionError(
                f"runtime node {node_id} latest ticket {latest_ticket_id!r} is not present in any graph lane."
            )
        views[node_id] = RuntimeNodeView(
            node_id=node_id,
            graph_node_id=graph_node_id or None,
            runtime_node_id=runtime_node_id or node_id,
            ticket_id=graph_ticket_id,
            is_placeholder=False,
            materialization_state=MATERIALIZATION_STATE_MATERIALIZED,
        )

    extra_runtime_projection_ids = sorted(
        set(runtime_projection_by_graph_node_id)
        - {
            str(getattr(graph_node, "graph_node_id", "") or "").strip()
            for graph_node in materialized_graph_nodes.values()
        }
    )
    if extra_runtime_projection_ids:
        raise RuntimeNodeViewResolutionError(
            "runtime_node_projection contains graph nodes missing from the execution graph lane: "
            + ", ".join(extra_runtime_projection_ids)
            + "."
        )

    missing_placeholder_projection_ids = sorted(
        set(placeholder_graph_nodes) - set(placeholder_projection_by_node_id)
    )
    if missing_placeholder_projection_ids:
        raise RuntimeNodeViewResolutionError(
            "execution graph lane contains placeholder nodes without planned_placeholder_projection: "
            + ", ".join(missing_placeholder_projection_ids)
            + "."
        )
    extra_placeholder_projection_ids = sorted(
        set(placeholder_projection_by_node_id) - set(placeholder_graph_nodes)
    )
    if extra_placeholder_projection_ids:
        raise RuntimeNodeViewResolutionError(
            "planned_placeholder_projection contains nodes missing from the execution graph lane: "
            + ", ".join(extra_placeholder_projection_ids)
            + "."
        )

    for node_id, graph_node in sorted(placeholder_graph_nodes.items()):
        if node_id in views:
            raise RuntimeNodeViewResolutionError(
                f"runtime node {node_id} is both materialized and a placeholder."
            )
        placeholder_projection = placeholder_projection_by_node_id.get(node_id)
        if placeholder_projection is None:
            raise RuntimeNodeViewResolutionError(
                f"runtime placeholder {node_id} is missing planned_placeholder_projection."
            )
        placeholder_status = str(placeholder_projection.get("status") or "").strip().upper()
        if placeholder_status not in {
            PLANNED_PLACEHOLDER_STATUS_PLANNED,
            PLANNED_PLACEHOLDER_STATUS_BLOCKED,
        }:
            raise RuntimeNodeViewResolutionError(
                f"runtime placeholder {node_id} has invalid placeholder status {placeholder_status!r}."
            )
        views[node_id] = RuntimeNodeView(
            node_id=node_id,
            graph_node_id=str(getattr(graph_node, "graph_node_id", "") or "").strip() or node_id,
            runtime_node_id=None,
            ticket_id=None,
            is_placeholder=True,
            materialization_state=MATERIALIZATION_STATE_PLANNED,
            placeholder_status=placeholder_status,
            reason_code=str(placeholder_projection.get("reason_code") or "").strip() or None,
            open_incident_id=str(placeholder_projection.get("open_incident_id") or "").strip() or None,
            materialization_hint=str(placeholder_projection.get("materialization_hint") or "").strip() or None,
        )

    return views


def resolve_runtime_node_view(
    repository: "ControlPlaneRepository",
    workflow_id: str,
    node_id: str,
    *,
    graph_snapshot: TicketGraphSnapshot | None = None,
    connection: "sqlite3.Connection" | None = None,
) -> RuntimeNodeView:
    normalized_node_id = str(node_id or "").strip()
    if not normalized_node_id:
        raise RuntimeNodeViewResolutionError("runtime node view requires a non-empty node_id.")
    views = build_runtime_node_views(
        repository,
        workflow_id,
        graph_snapshot=graph_snapshot,
        connection=connection,
    )
    return views.get(
        normalized_node_id,
        RuntimeNodeView(
            node_id=normalized_node_id,
            graph_node_id=None,
            runtime_node_id=None,
            ticket_id=None,
            is_placeholder=False,
            materialization_state=MATERIALIZATION_STATE_MISSING,
            placeholder_status=None,
            reason_code=None,
            open_incident_id=None,
            materialization_hint=None,
        ),
    )
