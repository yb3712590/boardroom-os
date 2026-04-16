from __future__ import annotations

from contextlib import nullcontext
from datetime import datetime
from typing import Any

from app.contracts.ceo import GraphHealthFindingDigest, GraphHealthReportDigest
from app.core.constants import (
    BLOCKING_REASON_ADVISORY_PATCH_FROZEN,
    EVENT_BOARD_REVIEW_REQUIRED,
    EVENT_GRAPH_PATCH_APPLIED,
    EVENT_INCIDENT_CLOSED,
    EVENT_INCIDENT_OPENED,
    EVENT_TICKET_EXECUTION_PRECONDITION_BLOCKED,
    EVENT_TICKET_EXECUTION_PRECONDITION_CLEARED,
)
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
_QUEUE_STARVATION_MULTIPLIER = 3
_READY_BLOCKED_THRASHING_THRESHOLD = 3
_READY_BLOCKED_THRASHING_WINDOW = 24
_READY_NODE_STALE_MULTIPLIER = 2
_CROSS_VERSION_SLA_MULTIPLIER = 2
_CROSS_VERSION_SLA_VERSION_DELTA_THRESHOLD = 3
_PATH_EDGE_TYPES = {"PARENT_OF", "DEPENDS_ON"}
_READY_BLOCKED_EVENT_TYPES = (
    EVENT_TICKET_EXECUTION_PRECONDITION_BLOCKED,
    EVENT_TICKET_EXECUTION_PRECONDITION_CLEARED,
    EVENT_BOARD_REVIEW_REQUIRED,
    EVENT_INCIDENT_OPENED,
    EVENT_INCIDENT_CLOSED,
    EVENT_GRAPH_PATCH_APPLIED,
)


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


def _workflow_ticket_projections(
    repository: ControlPlaneRepository,
    *,
    workflow_id: str,
    connection,
) -> dict[str, dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT *
        FROM ticket_projection
        WHERE workflow_id = ?
        ORDER BY updated_at ASC, ticket_id ASC
        """,
        (workflow_id,),
    ).fetchall()
    return {
        str(row["ticket_id"]).strip(): repository._convert_ticket_projection_row(row)
        for row in rows
        if str(row["ticket_id"]).strip()
    }


def _workflow_node_projections(
    repository: ControlPlaneRepository,
    *,
    workflow_id: str,
    connection,
) -> dict[str, dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT *
        FROM node_projection
        WHERE workflow_id = ?
        ORDER BY updated_at ASC, node_id ASC
        """,
        (workflow_id,),
    ).fetchall()
    return {
        str(row["node_id"]).strip(): repository._convert_node_projection_row(row)
        for row in rows
        if str(row["node_id"]).strip()
    }


def _latest_ticket_id_by_graph_node_id(graph_snapshot) -> dict[str, str]:
    latest_ticket_id_by_graph_node_id: dict[str, str] = {}
    for node in graph_snapshot.nodes:
        node_id = str(node.graph_node_id or "").strip()
        ticket_id = str(node.ticket_id or "").strip()
        if not node_id or not ticket_id:
            continue
        latest_ticket_id_by_graph_node_id[node_id] = ticket_id
    return latest_ticket_id_by_graph_node_id


def _graph_node_by_graph_node_id(graph_snapshot) -> dict[str, Any]:
    return {
        str(node.graph_node_id or "").strip(): node
        for node in graph_snapshot.nodes
        if str(node.graph_node_id or "").strip()
    }


def _runtime_node_ids_for_graph_node_ids(
    graph_snapshot,
    graph_node_ids: list[str] | tuple[str, ...] | set[str],
) -> list[str]:
    graph_node_by_id = _graph_node_by_graph_node_id(graph_snapshot)
    runtime_node_ids: set[str] = set()
    for graph_node_id in graph_node_ids:
        graph_node = graph_node_by_id.get(str(graph_node_id or "").strip())
        if graph_node is None:
            continue
        runtime_node_id = str(graph_node.runtime_node_id or graph_node.node_id or "").strip()
        if runtime_node_id:
            runtime_node_ids.add(runtime_node_id)
    return sorted(runtime_node_ids)


def _graph_node_ids_for_runtime_node_ids(
    graph_snapshot,
    runtime_node_ids: list[str] | tuple[str, ...] | set[str],
) -> list[str]:
    runtime_node_id_set = {
        str(node_id or "").strip()
        for node_id in runtime_node_ids
        if str(node_id or "").strip()
    }
    graph_node_ids = {
        str(node.graph_node_id or "").strip()
        for node in graph_snapshot.nodes
        if str(node.graph_node_id or "").strip()
        and str(node.runtime_node_id or node.node_id or "").strip() in runtime_node_id_set
    }
    return sorted(graph_node_ids)


def _finding_digest(
    graph_snapshot,
    *,
    finding_type: str,
    severity: str,
    affected_graph_node_ids: list[str] | tuple[str, ...] | set[str],
    metric_value: int | float,
    threshold: int | float,
    description: str,
    suggested_action: str,
) -> GraphHealthFindingDigest:
    normalized_graph_node_ids = sorted(
        {
            str(node_id or "").strip()
            for node_id in affected_graph_node_ids
            if str(node_id or "").strip()
        }
    )
    return GraphHealthFindingDigest(
        finding_type=finding_type,
        severity=severity,
        affected_nodes=_runtime_node_ids_for_graph_node_ids(graph_snapshot, normalized_graph_node_ids),
        affected_graph_node_ids=normalized_graph_node_ids,
        metric_value=metric_value,
        threshold=threshold,
        description=description,
        suggested_action=suggested_action,
    )


def _require_datetime(
    value: Any,
    *,
    reason: str,
) -> datetime:
    if not isinstance(value, datetime):
        _raise_graph_health_unavailable(reason)
    return value


def _require_int(
    value: Any,
    *,
    reason: str,
) -> int:
    if not isinstance(value, int):
        _raise_graph_health_unavailable(reason)
    return int(value)


def _graph_version_int(graph_version: str) -> int:
    normalized = str(graph_version or "").strip()
    if not normalized.startswith("gv_") or not normalized[3:].isdigit():
        _raise_graph_health_unavailable(f"invalid graph version {normalized or '<empty>'}.")
    return int(normalized[3:])


def _normalize_node_id(value: Any) -> str:
    return str(value or "").strip()


def _require_string_node_list(
    value: Any,
    *,
    event_id: str,
    field_name: str,
) -> list[str]:
    if not isinstance(value, list):
        _raise_graph_health_unavailable(
            f"{event_id} field {field_name} must be list[str]."
        )
    normalized: list[str] = []
    for item in value:
        if not isinstance(item, str):
            _raise_graph_health_unavailable(
                f"{event_id} field {field_name} must be list[str]."
            )
        node_id = item.strip()
        if node_id:
            normalized.append(node_id)
    return normalized


def _workflow_timeline_events(
    repository: ControlPlaneRepository,
    *,
    workflow_id: str,
    event_types: tuple[str, ...],
    connection,
    limit: int,
) -> list[dict[str, Any]]:
    placeholders = ", ".join("?" for _ in event_types)
    rows = list(
        connection.execute(
            f"""
            SELECT *
            FROM (
                SELECT *
                FROM events
                WHERE workflow_id = ? AND event_type IN ({placeholders})
                ORDER BY sequence_no DESC
                LIMIT ?
            )
            ORDER BY sequence_no ASC
            """,
            (workflow_id, *event_types, limit),
        ).fetchall()
    )
    return [repository._convert_event_row(row) for row in rows]


def _fanout_findings(graph_snapshot) -> list[GraphHealthFindingDigest]:
    edge_counts: dict[str, int] = {}
    for edge in graph_snapshot.edges:
        if edge.edge_type != "PARENT_OF":
            continue
        edge_counts[edge.source_graph_node_id] = edge_counts.get(edge.source_graph_node_id, 0) + 1
    findings: list[GraphHealthFindingDigest] = []
    for graph_node_id, count in sorted(edge_counts.items()):
        if count <= _FANOUT_TOO_WIDE_THRESHOLD:
            continue
        findings.append(
            _finding_digest(
                graph_snapshot,
                finding_type="FANOUT_TOO_WIDE",
                severity="WARNING",
                affected_graph_node_ids=[graph_node_id],
                metric_value=count,
                threshold=_FANOUT_TOO_WIDE_THRESHOLD,
                description=(
                    f"Node {graph_node_id} fans out to {count} direct child nodes, exceeding the "
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
        dependent_counts[edge.source_graph_node_id] = dependent_counts.get(edge.source_graph_node_id, 0) + 1
    if not dependent_counts:
        return []
    average_dependents = sum(dependent_counts.values()) / max(len(graph_snapshot.nodes), 1)
    threshold = round(average_dependents * _BOTTLENECK_MULTIPLIER, 2)
    findings: list[GraphHealthFindingDigest] = []
    for graph_node_id, count in sorted(dependent_counts.items()):
        if count <= threshold:
            continue
        findings.append(
            _finding_digest(
                graph_snapshot,
                finding_type="BOTTLENECK_DETECTED",
                severity="WARNING",
                affected_graph_node_ids=[graph_node_id],
                metric_value=count,
                threshold=threshold,
                description=(
                    f"Node {graph_node_id} is a dependency bottleneck with {count} downstream nodes, "
                    f"exceeding the current threshold {threshold}."
                ),
                suggested_action="Split the shared dependency or introduce an intermediate aggregation boundary.",
            )
        )
    return findings


def _critical_path_findings(graph_snapshot) -> list[GraphHealthFindingDigest]:
    incoming_nodes_by_node_id: dict[str, list[str]] = {
        node.graph_node_id: []
        for node in graph_snapshot.nodes
        if node.graph_node_id
    }
    depth_cache: dict[str, int] = {}
    active_node_ids: set[str] = set()

    for edge in graph_snapshot.edges:
        if edge.edge_type not in _PATH_EDGE_TYPES:
            continue
        incoming_nodes_by_node_id.setdefault(edge.target_graph_node_id, []).append(edge.source_graph_node_id)

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

    deepest_graph_node_id: str | None = None
    deepest_depth = 0
    for node in graph_snapshot.nodes:
        graph_node_id = str(node.graph_node_id or "").strip()
        if not graph_node_id:
            continue
        depth = _depth(graph_node_id)
        if depth > deepest_depth:
            deepest_depth = depth
            deepest_graph_node_id = graph_node_id

    if deepest_depth <= _CRITICAL_PATH_TOO_DEEP_THRESHOLD or deepest_graph_node_id is None:
        return []
    return [
        _finding_digest(
            graph_snapshot,
            finding_type="CRITICAL_PATH_TOO_DEEP",
            severity="WARNING",
            affected_graph_node_ids=[deepest_graph_node_id],
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
        str(node.graph_node_id).strip()
        for node in graph_snapshot.nodes
        if str(node.graph_node_id or "").strip() and str(node.node_kind or "").strip() == "CLOSEOUT"
    }
    if not closeout_node_ids:
        return []

    reverse_adjacency: dict[str, set[str]] = {}
    for edge in graph_snapshot.edges:
        if edge.edge_type not in _PATH_EDGE_TYPES:
            continue
        reverse_adjacency.setdefault(edge.target_graph_node_id, set()).add(edge.source_graph_node_id)

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
        str(node.graph_node_id).strip()
        for node in graph_snapshot.nodes
        if str(node.graph_node_id or "").strip()
        and str(node.graph_node_id).strip() not in reachable_node_ids
    )
    if not orphan_node_ids:
        return []
    return [
        _finding_digest(
            graph_snapshot,
            finding_type="ORPHAN_SUBGRAPH",
            severity="CRITICAL",
            affected_graph_node_ids=orphan_node_ids,
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
    graph_snapshot,
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
            _finding_digest(
                graph_snapshot,
                finding_type="PERSISTENT_FAILURE_ZONE",
                severity="CRITICAL",
                affected_graph_node_ids=_graph_node_ids_for_runtime_node_ids(
                    graph_snapshot,
                    [node_id],
                ),
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
    total_node_count = len(
        [node for node in graph_snapshot.nodes if str(node.graph_node_id or "").strip()]
    )
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
    frozen_graph_node_ids = sorted(
        graph_node_id
        for graph_node_id in list(graph_snapshot.index_summary.blocked_graph_node_ids or [])
        if graph_node_id in _graph_node_ids_for_runtime_node_ids(graph_snapshot, frozen_node_ids)
    )
    frozen_count = len(frozen_graph_node_ids)
    frozen_ratio = frozen_count / total_node_count
    if frozen_ratio <= _FREEZE_SPREAD_RATIO_THRESHOLD:
        return []
    return [
        _finding_digest(
            graph_snapshot,
            finding_type="FREEZE_SPREAD_TOO_WIDE",
            severity="WARNING",
            affected_graph_node_ids=frozen_graph_node_ids,
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
    graph_snapshot,
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
            _finding_digest(
                graph_snapshot,
                finding_type="GRAPH_THRASHING",
                severity="CRITICAL",
                affected_graph_node_ids=list(touched_node_ids),
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


def _queue_starvation_findings(
    repository: ControlPlaneRepository,
    *,
    graph_snapshot,
    workflow_id: str,
    connection,
) -> list[GraphHealthFindingDigest]:
    ready_node_ids = [
        str(node_id).strip()
        for node_id in list(graph_snapshot.index_summary.ready_graph_node_ids or [])
        if str(node_id).strip()
    ]
    if not ready_node_ids or list(graph_snapshot.index_summary.in_flight_graph_node_ids or []):
        return []

    latest_ticket_id_by_node_id = _latest_ticket_id_by_graph_node_id(graph_snapshot)
    ticket_by_ticket_id = _workflow_ticket_projections(
        repository,
        workflow_id=workflow_id,
        connection=connection,
    )
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
        updated_at = _require_datetime(
            ticket.get("updated_at"),
            reason=f"ready ticket {ticket_id} is missing updated_at.",
        )
        timeout_sla_sec = _require_int(
            ticket.get("timeout_sla_sec"),
            reason=f"ready ticket {ticket_id} is missing timeout_sla_sec.",
        )
        _require_int(
            ticket.get("version"),
            reason=f"ready ticket {ticket_id} is missing version.",
        )
        starvation_threshold_sec = timeout_sla_sec * _QUEUE_STARVATION_MULTIPLIER
        starvation_age_sec = int((current_time - updated_at).total_seconds())
        if starvation_age_sec <= starvation_threshold_sec:
            continue
        findings.append(
            _finding_digest(
                graph_snapshot,
                finding_type="QUEUE_STARVATION",
                severity="CRITICAL",
                affected_graph_node_ids=[node_id],
                metric_value=starvation_age_sec,
                threshold=starvation_threshold_sec,
                description=(
                    f"Ready node {node_id} has been waiting {starvation_age_sec} seconds with "
                    "no in-flight execution, so the queue is starving."
                ),
                suggested_action="Rerun the CEO or inspect scheduler progress before the ready queue stalls further.",
            )
        )
    return findings


def _ready_blocked_thrashing_findings(
    repository: ControlPlaneRepository,
    *,
    graph_snapshot,
    workflow_id: str,
    connection,
) -> list[GraphHealthFindingDigest]:
    events = _workflow_timeline_events(
        repository,
        workflow_id=workflow_id,
        event_types=_READY_BLOCKED_EVENT_TYPES,
        connection=connection,
        limit=_READY_BLOCKED_THRASHING_WINDOW,
    )
    state_history_by_node_id: dict[str, list[str]] = {}

    for event in events:
        event_type = str(event.get("event_type") or "").strip()
        event_id = str(event.get("event_id") or "").strip() or "event"
        payload = event.get("payload")
        if not isinstance(payload, dict):
            _raise_graph_health_unavailable(f"{event_id} payload must be an object.")

        transitions: list[tuple[str, str]] = []
        if event_type == EVENT_TICKET_EXECUTION_PRECONDITION_BLOCKED:
            node_id = _normalize_node_id(payload.get("node_id"))
            if not node_id:
                _raise_graph_health_unavailable(f"{event_id} is missing node_id.")
            transitions.append((node_id, "BLOCKED"))
        elif event_type == EVENT_TICKET_EXECUTION_PRECONDITION_CLEARED:
            node_id = _normalize_node_id(payload.get("node_id"))
            if not node_id:
                _raise_graph_health_unavailable(f"{event_id} is missing node_id.")
            transitions.append((node_id, "READY"))
        elif event_type == EVENT_BOARD_REVIEW_REQUIRED:
            node_id = _normalize_node_id(payload.get("node_id"))
            if not node_id:
                _raise_graph_health_unavailable(f"{event_id} is missing node_id.")
            transitions.append((node_id, "BLOCKED"))
        elif event_type == EVENT_INCIDENT_OPENED:
            node_id = _normalize_node_id(payload.get("node_id"))
            if node_id:
                transitions.append((node_id, "BLOCKED"))
        elif event_type == EVENT_INCIDENT_CLOSED:
            node_id = _normalize_node_id(payload.get("node_id"))
            if node_id:
                transitions.append((node_id, "READY"))
        elif event_type == EVENT_GRAPH_PATCH_APPLIED:
            for node_id in _require_string_node_list(
                payload.get("freeze_node_ids") or [],
                event_id=event_id,
                field_name="freeze_node_ids",
            ):
                transitions.append((node_id, "BLOCKED"))
            for node_id in _require_string_node_list(
                payload.get("unfreeze_node_ids") or [],
                event_id=event_id,
                field_name="unfreeze_node_ids",
            ):
                transitions.append((node_id, "READY"))

        for node_id, next_state in transitions:
            history = state_history_by_node_id.setdefault(node_id, [])
            if history and history[-1] == next_state:
                continue
            history.append(next_state)

    findings: list[GraphHealthFindingDigest] = []
    for node_id, history in sorted(state_history_by_node_id.items()):
        oscillation_count = min(history.count("READY"), history.count("BLOCKED"))
        if oscillation_count < _READY_BLOCKED_THRASHING_THRESHOLD:
            continue
        findings.append(
            _finding_digest(
                graph_snapshot,
                finding_type="READY_BLOCKED_THRASHING",
                severity="WARNING",
                affected_graph_node_ids=_graph_node_ids_for_runtime_node_ids(
                    graph_snapshot,
                    [node_id],
                ),
                metric_value=oscillation_count,
                threshold=_READY_BLOCKED_THRASHING_THRESHOLD,
                description=(
                    f"Node {node_id} oscillated between READY and BLOCKED {oscillation_count} "
                    f"times in the last {_READY_BLOCKED_THRASHING_WINDOW} explicit timeline events."
                ),
                suggested_action="Stabilize the blocking source before requeueing more work on the same node.",
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
        for node_id in list(graph_snapshot.index_summary.ready_graph_node_ids or [])
        if str(node_id).strip()
    ]
    if not ready_node_ids:
        return []
    latest_ticket_id_by_node_id = _latest_ticket_id_by_graph_node_id(graph_snapshot)
    ticket_by_ticket_id = _workflow_ticket_projections(
        repository,
        workflow_id=workflow_id,
        connection=connection,
    )
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
        updated_at = _require_datetime(
            ticket.get("updated_at"),
            reason=f"ready ticket {ticket_id} is missing updated_at.",
        )
        timeout_sla_sec = _require_int(
            ticket.get("timeout_sla_sec"),
            reason=f"ready ticket {ticket_id} is missing timeout_sla_sec.",
        )
        stale_threshold_sec = timeout_sla_sec * _READY_NODE_STALE_MULTIPLIER
        stale_age_sec = int((current_time - updated_at).total_seconds())
        if stale_age_sec <= stale_threshold_sec:
            continue
        findings.append(
            _finding_digest(
                graph_snapshot,
                finding_type="READY_NODE_STALE",
                severity="WARNING",
                affected_graph_node_ids=[node_id],
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


def _cross_version_sla_breach_findings(
    repository: ControlPlaneRepository,
    *,
    graph_snapshot,
    workflow_id: str,
    connection,
) -> list[GraphHealthFindingDigest]:
    blocked_node_ids = [
        str(node_id).strip()
        for node_id in list(graph_snapshot.index_summary.blocked_graph_node_ids or [])
        if str(node_id).strip()
    ]
    if not blocked_node_ids:
        return []

    current_graph_version_int = _graph_version_int(graph_snapshot.graph_version)
    latest_ticket_id_by_node_id = _latest_ticket_id_by_graph_node_id(graph_snapshot)
    ticket_by_ticket_id = _workflow_ticket_projections(
        repository,
        workflow_id=workflow_id,
        connection=connection,
    )
    node_by_node_id = _workflow_node_projections(
        repository,
        workflow_id=workflow_id,
        connection=connection,
    )
    graph_node_by_graph_node_id = _graph_node_by_graph_node_id(graph_snapshot)
    current_time = now_local()
    findings: list[GraphHealthFindingDigest] = []
    for node_id in blocked_node_ids:
        ticket_id = latest_ticket_id_by_node_id.get(node_id)
        if not ticket_id:
            _raise_graph_health_unavailable(
                f"blocked node {node_id} is missing its latest ticket projection."
            )
        ticket = ticket_by_ticket_id.get(ticket_id)
        if ticket is None:
            _raise_graph_health_unavailable(
                f"blocked node {node_id} points to missing ticket {ticket_id}."
            )
        graph_node = graph_node_by_graph_node_id.get(node_id)
        runtime_node_id = str(
            graph_node.runtime_node_id if graph_node is not None else ""
        ).strip()
        node_projection = node_by_node_id.get(runtime_node_id)
        if node_projection is None:
            _raise_graph_health_unavailable(
                f"blocked node {node_id} is missing node projection."
            )
        ticket_updated_at = _require_datetime(
            ticket.get("updated_at"),
            reason=f"blocked ticket {ticket_id} is missing updated_at.",
        )
        node_updated_at = _require_datetime(
            node_projection.get("updated_at"),
            reason=f"blocked node {node_id} is missing updated_at.",
        )
        timeout_sla_sec = _require_int(
            ticket.get("timeout_sla_sec"),
            reason=f"blocked ticket {ticket_id} is missing timeout_sla_sec.",
        )
        ticket_version = _require_int(
            ticket.get("version"),
            reason=f"blocked ticket {ticket_id} is missing version.",
        )
        node_version = _require_int(
            node_projection.get("version"),
            reason=f"blocked node {node_id} is missing version.",
        )
        latest_projection_version = max(ticket_version, node_version)
        version_delta = current_graph_version_int - latest_projection_version
        if version_delta < _CROSS_VERSION_SLA_VERSION_DELTA_THRESHOLD:
            continue
        blocked_updated_at = max(ticket_updated_at, node_updated_at)
        blocked_age_sec = int((current_time - blocked_updated_at).total_seconds())
        blocked_threshold_sec = timeout_sla_sec * _CROSS_VERSION_SLA_MULTIPLIER
        if blocked_age_sec <= blocked_threshold_sec:
            continue
        findings.append(
            _finding_digest(
                graph_snapshot,
                finding_type="CROSS_VERSION_SLA_BREACH",
                severity="CRITICAL",
                affected_graph_node_ids=[node_id],
                metric_value=version_delta,
                threshold=_CROSS_VERSION_SLA_VERSION_DELTA_THRESHOLD,
                description=(
                    f"Blocked node {node_id} stayed unresolved for {blocked_age_sec} seconds "
                    f"while the graph advanced {version_delta} versions."
                ),
                suggested_action="Rerun the CEO or clear the blocker before more graph versions accumulate on stale work.",
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
            *_queue_starvation_findings(
                repository,
                graph_snapshot=graph_snapshot,
                workflow_id=workflow_id,
                connection=resolved_connection,
            ),
            *_graph_thrashing_findings(
                repository,
                graph_snapshot=graph_snapshot,
                workflow_id=workflow_id,
                connection=resolved_connection,
            ),
            *_persistent_failure_zone_findings(
                repository,
                graph_snapshot=graph_snapshot,
                workflow_id=workflow_id,
                connection=resolved_connection,
            ),
            *_freeze_spread_findings(graph_snapshot),
            *_ready_blocked_thrashing_findings(
                repository,
                graph_snapshot=graph_snapshot,
                workflow_id=workflow_id,
                connection=resolved_connection,
            ),
            *_ready_node_stale_findings(
                repository,
                graph_snapshot=graph_snapshot,
                workflow_id=workflow_id,
                connection=resolved_connection,
            ),
            *_cross_version_sla_breach_findings(
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
