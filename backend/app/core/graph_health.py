from __future__ import annotations

from contextlib import nullcontext
from datetime import datetime
from typing import Any

from app.contracts.ceo import GraphHealthFindingDigest, GraphHealthReportDigest
from app.core.constants import BLOCKING_REASON_ADVISORY_PATCH_FROZEN
from app.core.graph_patch_reducer import (
    graph_patch_target_node_ids,
    load_graph_patch_event_records,
)
from app.core.ticket_graph import build_ticket_graph_snapshot
from app.core.time import now_local
from app.db.repository import ControlPlaneRepository

_BOTTLENECK_MULTIPLIER = 3
_FANOUT_TOO_WIDE_THRESHOLD = 10
_CRITICAL_PATH_TOO_DEEP_THRESHOLD = 15
_FREEZE_SPREAD_RATIO_THRESHOLD = 0.3
_GRAPH_THRASHING_THRESHOLD = 3
_GRAPH_THRASHING_WINDOW = 10
_PERSISTENT_FAILURE_ZONE_THRESHOLD = 3
_PERSISTENT_FAILURE_ZONE_WINDOW = 10
_READY_NODE_STALE_MULTIPLIER = 2
_PATH_EDGE_TYPES = {"PARENT_OF", "DEPENDS_ON"}


class GraphHealthUnavailableError(RuntimeError):
    pass


def _raise_graph_health_unavailable(reason: str) -> None:
    raise GraphHealthUnavailableError(f"graph unavailable: {reason}")


def _workflow_incidents(
    repository: ControlPlaneRepository,
    *,
    workflow_id: str,
    connection,
) -> list[dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT *
        FROM incident_projection
        WHERE workflow_id = ?
        ORDER BY opened_at DESC, incident_id DESC
        LIMIT ?
        """,
        (workflow_id, _PERSISTENT_FAILURE_ZONE_WINDOW),
    ).fetchall()
    return [repository._convert_incident_projection_row(row) for row in rows]


def _fanout_findings(graph_snapshot) -> list[GraphHealthFindingDigest]:
    edge_counts: dict[str, int] = {}
    for edge in graph_snapshot.edges:
        if edge.edge_type != "PARENT_OF":
            continue
        edge_counts[edge.source_node_id] = edge_counts.get(edge.source_node_id, 0) + 1
    findings: list[GraphHealthFindingDigest] = []
    for node_id, count in sorted(edge_counts.items()):
        if count <= _FANOUT_TOO_WIDE_THRESHOLD:
            continue
        findings.append(
            GraphHealthFindingDigest(
                finding_type="FANOUT_TOO_WIDE",
                severity="WARNING",
                affected_nodes=[node_id],
                metric_value=count,
                threshold=_FANOUT_TOO_WIDE_THRESHOLD,
                description=(
                    f"Node {node_id} fans out to {count} direct child nodes, exceeding the "
                    f"current threshold {_FANOUT_TOO_WIDE_THRESHOLD}."
                ),
                suggested_action="Split the wide branch behind an intermediate aggregation step.",
            )
        )
    return findings


def _bottleneck_findings(graph_snapshot) -> list[GraphHealthFindingDigest]:
    if not graph_snapshot.nodes:
        return []
    dependent_counts: dict[str, int] = {}
    for edge in graph_snapshot.edges:
        if edge.edge_type != "DEPENDS_ON":
            continue
        dependent_counts[edge.source_node_id] = dependent_counts.get(edge.source_node_id, 0) + 1
    if not dependent_counts:
        return []
    average_dependents = sum(dependent_counts.values()) / max(len(graph_snapshot.nodes), 1)
    threshold = round(average_dependents * _BOTTLENECK_MULTIPLIER, 2)
    findings: list[GraphHealthFindingDigest] = []
    for node_id, count in sorted(dependent_counts.items()):
        if count <= threshold:
            continue
        findings.append(
            GraphHealthFindingDigest(
                finding_type="BOTTLENECK_DETECTED",
                severity="WARNING",
                affected_nodes=[node_id],
                metric_value=count,
                threshold=threshold,
                description=(
                    f"Node {node_id} is a dependency bottleneck with {count} downstream nodes, "
                    f"exceeding the current threshold {threshold}."
                ),
                suggested_action="Split the shared dependency or introduce an intermediate aggregation boundary.",
            )
        )
    return findings


def _critical_path_findings(graph_snapshot) -> list[GraphHealthFindingDigest]:
    incoming_nodes_by_node_id: dict[str, list[str]] = {
        node.node_id: []
        for node in graph_snapshot.nodes
        if node.node_id
    }
    depth_cache: dict[str, int] = {}
    active_node_ids: set[str] = set()

    for edge in graph_snapshot.edges:
        if edge.edge_type not in _PATH_EDGE_TYPES:
            continue
        if edge.source_node_id == edge.target_node_id:
            continue
        incoming_nodes_by_node_id.setdefault(edge.target_node_id, []).append(edge.source_node_id)

    def _depth(node_id: str) -> int:
        if node_id in depth_cache:
            return depth_cache[node_id]
        if node_id in active_node_ids:
            raise ValueError(f"Graph health cannot evaluate a cyclic path around node {node_id}.")
        active_node_ids.add(node_id)
        parents = incoming_nodes_by_node_id.get(node_id) or []
        if not parents:
            depth_cache[node_id] = 1
            active_node_ids.discard(node_id)
            return 1
        depth_cache[node_id] = 1 + max(_depth(parent_node_id) for parent_node_id in parents)
        active_node_ids.discard(node_id)
        return depth_cache[node_id]

    deepest_node_id: str | None = None
    deepest_depth = 0
    for node in graph_snapshot.nodes:
        node_id = str(node.node_id or "").strip()
        if not node_id:
            continue
        depth = _depth(node_id)
        if depth > deepest_depth:
            deepest_depth = depth
            deepest_node_id = node_id

    if deepest_depth <= _CRITICAL_PATH_TOO_DEEP_THRESHOLD or deepest_node_id is None:
        return []
    return [
        GraphHealthFindingDigest(
            finding_type="CRITICAL_PATH_TOO_DEEP",
            severity="WARNING",
            affected_nodes=[deepest_node_id],
            metric_value=deepest_depth,
            threshold=_CRITICAL_PATH_TOO_DEEP_THRESHOLD,
            description=(
                f"The longest parent chain reached depth {deepest_depth}, exceeding the current "
                f"threshold {_CRITICAL_PATH_TOO_DEEP_THRESHOLD}."
            ),
            suggested_action="Reduce the longest chain or regroup low-value intermediate steps.",
        )
    ]


def _orphan_subgraph_findings(graph_snapshot) -> list[GraphHealthFindingDigest]:
    closeout_node_ids = {
        str(node.node_id).strip()
        for node in graph_snapshot.nodes
        if str(node.node_id or "").strip() and str(node.node_kind or "").strip() == "CLOSEOUT"
    }
    if not closeout_node_ids:
        return []

    reverse_adjacency: dict[str, set[str]] = {}
    for edge in graph_snapshot.edges:
        if edge.edge_type not in _PATH_EDGE_TYPES:
            continue
        reverse_adjacency.setdefault(edge.target_node_id, set()).add(edge.source_node_id)

    reachable_node_ids = set(closeout_node_ids)
    frontier = list(closeout_node_ids)
    while frontier:
        current_node_id = frontier.pop()
        for parent_node_id in reverse_adjacency.get(current_node_id, set()):
            if parent_node_id in reachable_node_ids:
                continue
            reachable_node_ids.add(parent_node_id)
            frontier.append(parent_node_id)

    orphan_node_ids = sorted(
        str(node.node_id).strip()
        for node in graph_snapshot.nodes
        if str(node.node_id or "").strip()
        and str(node.node_id).strip() not in reachable_node_ids
    )
    if not orphan_node_ids:
        return []
    return [
        GraphHealthFindingDigest(
            finding_type="ORPHAN_SUBGRAPH",
            severity="CRITICAL",
            affected_nodes=orphan_node_ids,
            metric_value=len(orphan_node_ids),
            threshold=0,
            description=(
                f"{len(orphan_node_ids)} node(s) are disconnected from every closeout path and "
                "will not converge without an explicit graph change."
            ),
            suggested_action="Reconnect the orphan branch to a closeout path or cancel it explicitly.",
        )
    ]


def _persistent_failure_zone_findings(
    repository: ControlPlaneRepository,
    *,
    workflow_id: str,
    connection,
) -> list[GraphHealthFindingDigest]:
    incidents = _workflow_incidents(
        repository,
        workflow_id=workflow_id,
        connection=connection,
    )
    counts: dict[str, int] = {}
    for incident in incidents:
        node_id = str(incident.get("node_id") or "").strip()
        fingerprint = str(incident.get("fingerprint") or "").strip()
        if not node_id or not fingerprint:
            continue
        counts[node_id] = counts.get(node_id, 0) + 1

    findings: list[GraphHealthFindingDigest] = []
    for node_id, count in sorted(counts.items()):
        if count < _PERSISTENT_FAILURE_ZONE_THRESHOLD:
            continue
        findings.append(
            GraphHealthFindingDigest(
                finding_type="PERSISTENT_FAILURE_ZONE",
                severity="CRITICAL",
                affected_nodes=[node_id],
                metric_value=count,
                threshold=_PERSISTENT_FAILURE_ZONE_THRESHOLD,
                description=(
                    f"Node {node_id} appeared in {count} recent explicit incidents, so the "
                    "failure zone is no longer safe to ignore."
                ),
                suggested_action="Pause new fanout and rerun the CEO against the latest graph health snapshot.",
            )
        )
    return findings


def _freeze_spread_findings(graph_snapshot) -> list[GraphHealthFindingDigest]:
    total_node_count = len([node for node in graph_snapshot.nodes if str(node.node_id or "").strip()])
    if total_node_count <= 0:
        return []
    frozen_reason = next(
        (
            blocked_reason
            for blocked_reason in graph_snapshot.index_summary.blocked_reasons
            if blocked_reason.reason_code == BLOCKING_REASON_ADVISORY_PATCH_FROZEN
        ),
        None,
    )
    frozen_node_ids = sorted(
        str(node_id).strip()
        for node_id in list(getattr(frozen_reason, "node_ids", []) or [])
        if str(node_id).strip()
    )
    frozen_count = len(frozen_node_ids)
    frozen_ratio = frozen_count / total_node_count
    if frozen_ratio <= _FREEZE_SPREAD_RATIO_THRESHOLD:
        return []
    return [
        GraphHealthFindingDigest(
            finding_type="FREEZE_SPREAD_TOO_WIDE",
            severity="WARNING",
            affected_nodes=frozen_node_ids,
            metric_value=frozen_count,
            threshold=round(total_node_count * _FREEZE_SPREAD_RATIO_THRESHOLD, 2),
            description=(
                f"{frozen_count} of {total_node_count} nodes are frozen by an advisory patch, "
                f"exceeding the current spread threshold {_FREEZE_SPREAD_RATIO_THRESHOLD:.0%}."
            ),
            suggested_action="Review whether the freeze can be narrowed or the branch should be replanned.",
        )
    ]


def _graph_thrashing_findings(
    repository: ControlPlaneRepository,
    *,
    workflow_id: str,
    connection,
) -> list[GraphHealthFindingDigest]:
    patch_events = load_graph_patch_event_records(
        repository,
        workflow_id,
        connection=connection,
        limit=_GRAPH_THRASHING_WINDOW,
    )
    touched_counts: dict[tuple[str, ...], int] = {}
    for event in patch_events:
        touched_node_ids = tuple(sorted(graph_patch_target_node_ids(event.patch)))
        if not touched_node_ids:
            continue
        touched_counts[touched_node_ids] = touched_counts.get(touched_node_ids, 0) + 1

    findings: list[GraphHealthFindingDigest] = []
    for touched_node_ids, count in sorted(touched_counts.items()):
        if count <= _GRAPH_THRASHING_THRESHOLD:
            continue
        findings.append(
            GraphHealthFindingDigest(
                finding_type="GRAPH_THRASHING",
                severity="CRITICAL",
                affected_nodes=list(touched_node_ids),
                metric_value=count,
                threshold=_GRAPH_THRASHING_THRESHOLD,
                description=(
                    f"The same graph patch target set was rewritten {count} times in the last "
                    f"{_GRAPH_THRASHING_WINDOW} graph patch events."
                ),
                suggested_action="Open a board advisory session or rerun the CEO before applying more graph churn.",
            )
        )
    return findings


def _ready_node_stale_findings(
    repository: ControlPlaneRepository,
    *,
    graph_snapshot,
    workflow_id: str,
    connection,
) -> list[GraphHealthFindingDigest]:
    ready_node_ids = [
        str(node_id).strip()
        for node_id in list(graph_snapshot.index_summary.ready_node_ids or [])
        if str(node_id).strip()
    ]
    if not ready_node_ids:
        return []
    latest_ticket_id_by_node_id = {
        str(node.node_id).strip(): str(node.ticket_id).strip()
        for node in graph_snapshot.nodes
        if str(node.node_id or "").strip() and str(node.ticket_id or "").strip()
    }
    ticket_rows = connection.execute(
        """
        SELECT *
        FROM ticket_projection
        WHERE workflow_id = ?
        ORDER BY updated_at ASC, ticket_id ASC
        """,
        (workflow_id,),
    ).fetchall()
    ticket_by_ticket_id = {
        str(row["ticket_id"]).strip(): repository._convert_ticket_projection_row(row)
        for row in ticket_rows
        if str(row["ticket_id"]).strip()
    }
    current_time = now_local()
    findings: list[GraphHealthFindingDigest] = []
    for node_id in ready_node_ids:
        ticket_id = latest_ticket_id_by_node_id.get(node_id)
        if not ticket_id:
            _raise_graph_health_unavailable(
                f"ready node {node_id} is missing its latest ticket projection."
            )
        ticket = ticket_by_ticket_id.get(ticket_id)
        if ticket is None:
            _raise_graph_health_unavailable(
                f"ready node {node_id} points to missing ticket {ticket_id}."
            )
        updated_at = ticket.get("updated_at")
        if not isinstance(updated_at, datetime):
            _raise_graph_health_unavailable(
                f"ready ticket {ticket_id} is missing updated_at."
            )
        timeout_sla_sec = ticket.get("timeout_sla_sec")
        if not isinstance(timeout_sla_sec, int):
            _raise_graph_health_unavailable(
                f"ready ticket {ticket_id} is missing timeout_sla_sec."
            )
        stale_threshold_sec = timeout_sla_sec * _READY_NODE_STALE_MULTIPLIER
        stale_age_sec = int((current_time - updated_at).total_seconds())
        if stale_age_sec <= stale_threshold_sec:
            continue
        findings.append(
            GraphHealthFindingDigest(
                finding_type="READY_NODE_STALE",
                severity="WARNING",
                affected_nodes=[node_id],
                metric_value=stale_age_sec,
                threshold=stale_threshold_sec,
                description=(
                    f"Ready node {node_id} has waited {stale_age_sec} seconds since its last "
                    f"ticket update, exceeding the current stale threshold {stale_threshold_sec}."
                ),
                suggested_action="Check scheduler progress or rerun the CEO before the ready node goes stale.",
            )
        )
    return findings


def build_graph_health_report(
    repository: ControlPlaneRepository,
    workflow_id: str,
    *,
    connection=None,
) -> GraphHealthReportDigest:
    with repository.connection() if connection is None else nullcontext(connection) as resolved_connection:
        graph_snapshot = build_ticket_graph_snapshot(
            repository,
            workflow_id,
            connection=resolved_connection,
        )
        findings = [
            *_fanout_findings(graph_snapshot),
            *_bottleneck_findings(graph_snapshot),
            *_critical_path_findings(graph_snapshot),
            *_orphan_subgraph_findings(graph_snapshot),
            *_graph_thrashing_findings(
                repository,
                workflow_id=workflow_id,
                connection=resolved_connection,
            ),
            *_persistent_failure_zone_findings(
                repository,
                workflow_id=workflow_id,
                connection=resolved_connection,
            ),
            *_freeze_spread_findings(graph_snapshot),
            *_ready_node_stale_findings(
                repository,
                graph_snapshot=graph_snapshot,
                workflow_id=workflow_id,
                connection=resolved_connection,
            ),
        ]
    overall_health = "HEALTHY"
    if any(item.severity == "CRITICAL" for item in findings):
        overall_health = "CRITICAL"
    elif findings:
        overall_health = "WARNING"
    recommended_actions = list(
        dict.fromkeys(item.suggested_action for item in findings if item.suggested_action)
    )
    return GraphHealthReportDigest(
        report_id=f"ghr://{workflow_id}/{graph_snapshot.graph_version}",
        workflow_id=workflow_id,
        graph_version=graph_snapshot.graph_version,
        overall_health=overall_health,
        findings=findings,
        recommended_actions=recommended_actions,
    )
