from __future__ import annotations

from contextlib import nullcontext
from typing import Any

from app.contracts.ceo import GraphHealthFindingDigest, GraphHealthReportDigest
from app.core.ticket_graph import build_ticket_graph_snapshot
from app.db.repository import ControlPlaneRepository

_FANOUT_TOO_WIDE_THRESHOLD = 10
_CRITICAL_PATH_TOO_DEEP_THRESHOLD = 15
_PERSISTENT_FAILURE_ZONE_THRESHOLD = 3
_PERSISTENT_FAILURE_ZONE_WINDOW = 10


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


def _critical_path_findings(graph_snapshot) -> list[GraphHealthFindingDigest]:
    parent_by_ticket_id = {
        node.ticket_id: node.parent_ticket_id
        for node in graph_snapshot.nodes
        if node.ticket_id
    }
    node_id_by_ticket_id = {
        node.ticket_id: node.node_id
        for node in graph_snapshot.nodes
        if node.ticket_id and node.node_id
    }

    depth_cache: dict[str, int] = {}

    def _depth(ticket_id: str) -> int:
        if ticket_id in depth_cache:
            return depth_cache[ticket_id]
        parent_ticket_id = parent_by_ticket_id.get(ticket_id)
        if not parent_ticket_id:
            depth_cache[ticket_id] = 1
            return 1
        depth_cache[ticket_id] = 1 + _depth(parent_ticket_id)
        return depth_cache[ticket_id]

    deepest_ticket_id: str | None = None
    deepest_depth = 0
    for ticket_id in parent_by_ticket_id:
        depth = _depth(ticket_id)
        if depth > deepest_depth:
            deepest_depth = depth
            deepest_ticket_id = ticket_id

    if deepest_depth <= _CRITICAL_PATH_TOO_DEEP_THRESHOLD or deepest_ticket_id is None:
        return []
    return [
        GraphHealthFindingDigest(
            finding_type="CRITICAL_PATH_TOO_DEEP",
            severity="WARNING",
            affected_nodes=[node_id_by_ticket_id.get(deepest_ticket_id, deepest_ticket_id)],
            metric_value=deepest_depth,
            threshold=_CRITICAL_PATH_TOO_DEEP_THRESHOLD,
            description=(
                f"The longest parent chain reached depth {deepest_depth}, exceeding the current "
                f"threshold {_CRITICAL_PATH_TOO_DEEP_THRESHOLD}."
            ),
            suggested_action="Reduce the longest chain or regroup low-value intermediate steps.",
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
            *_critical_path_findings(graph_snapshot),
            *_persistent_failure_zone_findings(
                repository,
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
