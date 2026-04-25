from __future__ import annotations

from contextlib import nullcontext
from typing import Any

from app.contracts.ceo import GraphHealthFindingDigest, GraphHealthReportDigest
from app.core.constants import (
    BLOCKING_REASON_ADVISORY_PATCH_FROZEN,
    EVENT_GRAPH_PATCH_APPLIED,
    EVENT_INCIDENT_OPENED,
)
from app.core.graph_health_policy import DEFAULT_GRAPH_HEALTH_POLICY, GraphHealthPolicy
from app.core.graph_patch_reducer import (
    graph_patch_target_node_ids,
    load_graph_patch_event_records,
)
from app.core.output_schemas import MAKER_CHECKER_VERDICT_SCHEMA_REF
from app.core.ticket_graph import build_ticket_graph_snapshot
from app.core.time import now_local
from app.db.repository import ControlPlaneRepository

_PATH_EDGE_TYPES = {"PARENT_OF", "DEPENDS_ON"}
_APPROVED_REVIEW_STATUSES = {"APPROVED", "APPROVED_WITH_NOTES"}


class GraphHealthUnavailableError(RuntimeError):
    pass


def _raise_graph_health_unavailable(reason: str) -> None:
    raise GraphHealthUnavailableError(f"graph unavailable: {reason}")


def _policy_severity(policy: GraphHealthPolicy, finding_type: str) -> str:
    return str(policy.finding_severities.get(finding_type) or "WARNING")


def _workflow_incidents(
    repository: ControlPlaneRepository,
    *,
    workflow_id: str,
    policy: GraphHealthPolicy,
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
        (workflow_id, policy.persistent_failure_zone_window),
    ).fetchall()
    return [repository._convert_incident_projection_row(row) for row in rows]


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


def _runtime_node_id_for_graph_node(node) -> str:
    runtime_node_id = str(getattr(node, "runtime_node_id", None) or "").strip()
    if runtime_node_id:
        return runtime_node_id
    if not bool(getattr(node, "is_placeholder", False)):
        return str(getattr(node, "node_id", None) or "").strip()
    return ""


def _latest_execution_graph_node_for_runtime_node(
    repository: ControlPlaneRepository,
    *,
    graph_snapshot,
    workflow_id: str,
    runtime_node_id: str,
    connection,
):
    candidates = []
    for node in graph_snapshot.nodes:
        ticket_id = str(getattr(node, "ticket_id", None) or "").strip()
        if not ticket_id:
            continue
        if _runtime_node_id_for_graph_node(node) != runtime_node_id:
            continue
        if str(getattr(node, "graph_lane_kind", None) or "").strip() == "review":
            continue
        if str(getattr(node, "output_schema_ref", None) or "").strip() == MAKER_CHECKER_VERDICT_SCHEMA_REF:
            continue
        ticket_projection = repository.get_current_ticket_projection(ticket_id, connection=connection)
        if ticket_projection is None or str(ticket_projection.get("workflow_id") or "").strip() != workflow_id:
            continue
        candidates.append((ticket_projection.get("updated_at"), ticket_id, node, ticket_projection))
    if not candidates:
        return None, None
    candidates.sort(key=lambda item: (item[0].isoformat() if item[0] is not None else "", item[1]))
    _, _, node, ticket_projection = candidates[-1]
    return node, ticket_projection


def _review_status_for_ticket(
    repository: ControlPlaneRepository,
    *,
    ticket_id: str,
    connection,
) -> str:
    terminal_event = repository.get_latest_ticket_terminal_event(connection, ticket_id)
    terminal_payload = (terminal_event or {}).get("payload") or {}
    result_payload = terminal_payload.get("payload") or {}
    return str(result_payload.get("review_status") or terminal_payload.get("review_status") or "").strip()


def _approved_review_ticket_ids_for_maker(
    repository: ControlPlaneRepository,
    *,
    graph_snapshot,
    runtime_node_id: str,
    maker_ticket_id: str,
    connection,
) -> set[str]:
    review_ticket_ids = {
        str(edge.source_ticket_id or "").strip()
        for edge in graph_snapshot.edges
        if str(edge.edge_type or "").strip() == "REVIEWS"
        and str(edge.source_ticket_id or "").strip()
        and (
            str(edge.target_ticket_id or "").strip() == maker_ticket_id
            or str(edge.target_runtime_node_id or "").strip() == runtime_node_id
        )
    }
    for node in graph_snapshot.nodes:
        ticket_id = str(getattr(node, "ticket_id", None) or "").strip()
        if not ticket_id:
            continue
        if str(getattr(node, "graph_lane_kind", None) or "").strip() != "review":
            continue
        created_spec = repository.get_latest_ticket_created_payload(connection, ticket_id) or {}
        maker_context = created_spec.get("maker_checker_context") or {}
        if str(maker_context.get("maker_ticket_id") or "").strip() == maker_ticket_id:
            review_ticket_ids.add(ticket_id)

    approved_ticket_ids: set[str] = set()
    for review_ticket_id in review_ticket_ids:
        review_projection = repository.get_current_ticket_projection(review_ticket_id, connection=connection)
        if review_projection is None or str(review_projection.get("status") or "").strip() != "COMPLETED":
            continue
        created_spec = repository.get_latest_ticket_created_payload(connection, review_ticket_id) or {}
        if str(created_spec.get("output_schema_ref") or "").strip() != MAKER_CHECKER_VERDICT_SCHEMA_REF:
            continue
        if _review_status_for_ticket(repository, ticket_id=review_ticket_id, connection=connection) in _APPROVED_REVIEW_STATUSES:
            approved_ticket_ids.add(review_ticket_id)
    return approved_ticket_ids


def _runtime_node_has_recovered_latest_retry(
    repository: ControlPlaneRepository,
    *,
    graph_snapshot,
    workflow_id: str,
    runtime_node_id: str,
    connection,
) -> bool:
    latest_node, latest_ticket = _latest_execution_graph_node_for_runtime_node(
        repository,
        graph_snapshot=graph_snapshot,
        workflow_id=workflow_id,
        runtime_node_id=runtime_node_id,
        connection=connection,
    )
    if latest_node is None or latest_ticket is None:
        return False
    if str(latest_ticket.get("status") or "").strip() != "COMPLETED":
        return False
    maker_ticket_id = str(latest_ticket.get("ticket_id") or "").strip()
    if not maker_ticket_id:
        return False
    if bool(
        _approved_review_ticket_ids_for_maker(
            repository,
            graph_snapshot=graph_snapshot,
            runtime_node_id=runtime_node_id,
            maker_ticket_id=maker_ticket_id,
            connection=connection,
        )
    ):
        return True

    for node in graph_snapshot.nodes:
        if str(getattr(node, "graph_lane_kind", None) or "").strip() != "review":
            continue
        review_ticket_id = str(getattr(node, "ticket_id", None) or "").strip()
        if not review_ticket_id:
            continue
        created_spec = repository.get_latest_ticket_created_payload(connection, review_ticket_id) or {}
        maker_context = created_spec.get("maker_checker_context") or {}
        context_maker_ticket_id = str(maker_context.get("maker_ticket_id") or "").strip()
        if context_maker_ticket_id != maker_ticket_id:
            continue
        review_projection = repository.get_current_ticket_projection(review_ticket_id, connection=connection)
        if review_projection is None or str(review_projection.get("status") or "").strip() != "COMPLETED":
            continue
        if _review_status_for_ticket(repository, ticket_id=review_ticket_id, connection=connection) in _APPROVED_REVIEW_STATUSES:
            return True
    return False


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
        runtime_node_id = str(graph_node.runtime_node_id or "").strip()
        if not runtime_node_id and not bool(getattr(graph_node, "is_placeholder", False)):
            runtime_node_id = str(graph_node.node_id or "").strip()
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
        and (
            str(node.runtime_node_id or "").strip()
            or (
                str(node.node_id or "").strip()
                if not bool(getattr(node, "is_placeholder", False))
                else ""
            )
        )
        in runtime_node_id_set
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


def _fanout_findings(
    graph_snapshot,
    *,
    policy: GraphHealthPolicy,
) -> list[GraphHealthFindingDigest]:
    edge_counts: dict[str, int] = {}
    for edge in graph_snapshot.edges:
        if edge.edge_type != "PARENT_OF":
            continue
        edge_counts[edge.source_graph_node_id] = edge_counts.get(edge.source_graph_node_id, 0) + 1
    findings: list[GraphHealthFindingDigest] = []
    for graph_node_id, count in sorted(edge_counts.items()):
        if count <= policy.fanout_too_wide_threshold:
            continue
        findings.append(
            _finding_digest(
                graph_snapshot,
                finding_type="FANOUT_TOO_WIDE",
                severity=_policy_severity(policy, "FANOUT_TOO_WIDE"),
                affected_graph_node_ids=[graph_node_id],
                metric_value=count,
                threshold=policy.fanout_too_wide_threshold,
                description=(
                    f"Node {graph_node_id} fans out to {count} direct child nodes, exceeding the "
                    f"current threshold {policy.fanout_too_wide_threshold}."
                ),
                suggested_action="Split the wide branch behind an intermediate aggregation step.",
            )
        )
    return findings


def _bottleneck_findings(
    graph_snapshot,
    *,
    policy: GraphHealthPolicy,
) -> list[GraphHealthFindingDigest]:
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
    threshold = round(average_dependents * policy.bottleneck_multiplier, 2)
    findings: list[GraphHealthFindingDigest] = []
    for graph_node_id, count in sorted(dependent_counts.items()):
        if count <= threshold:
            continue
        findings.append(
            _finding_digest(
                graph_snapshot,
                finding_type="BOTTLENECK_DETECTED",
                severity=_policy_severity(policy, "BOTTLENECK_DETECTED"),
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


def _critical_path_findings(
    graph_snapshot,
    *,
    policy: GraphHealthPolicy,
) -> list[GraphHealthFindingDigest]:
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

    if deepest_depth <= policy.critical_path_too_deep_threshold or deepest_graph_node_id is None:
        return []
    return [
        _finding_digest(
            graph_snapshot,
            finding_type="CRITICAL_PATH_TOO_DEEP",
            severity=_policy_severity(policy, "CRITICAL_PATH_TOO_DEEP"),
            affected_graph_node_ids=[deepest_graph_node_id],
            metric_value=deepest_depth,
            threshold=policy.critical_path_too_deep_threshold,
            description=(
                f"The longest parent chain reached depth {deepest_depth}, exceeding the current "
                f"threshold {policy.critical_path_too_deep_threshold}."
            ),
            suggested_action="Reduce the longest chain or regroup low-value intermediate steps.",
        )
    ]


def _orphan_subgraph_findings(
    graph_snapshot,
    *,
    policy: GraphHealthPolicy,
) -> list[GraphHealthFindingDigest]:
    closeout_node_ids = {
        str(node.graph_node_id).strip()
        for node in graph_snapshot.nodes
        if str(node.graph_node_id or "").strip() and str(node.node_kind or "").strip() == "CLOSEOUT"
    }
    if not closeout_node_ids:
        return []

    reverse_adjacency: dict[str, set[str]] = {}
    for edge in graph_snapshot.edges:
        if edge.edge_type not in {*_PATH_EDGE_TYPES, "REVIEWS"}:
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
            severity=_policy_severity(policy, "ORPHAN_SUBGRAPH"),
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
    policy: GraphHealthPolicy,
    connection,
) -> list[GraphHealthFindingDigest]:
    incidents = _workflow_incidents(
        repository,
        workflow_id=workflow_id,
        policy=policy,
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
        if count < policy.persistent_failure_zone_threshold:
            continue
        if _runtime_node_has_recovered_latest_retry(
            repository,
            graph_snapshot=graph_snapshot,
            workflow_id=workflow_id,
            runtime_node_id=node_id,
            connection=connection,
        ):
            continue
        findings.append(
            _finding_digest(
                graph_snapshot,
                finding_type="PERSISTENT_FAILURE_ZONE",
                severity=_policy_severity(policy, "PERSISTENT_FAILURE_ZONE"),
                affected_graph_node_ids=_graph_node_ids_for_runtime_node_ids(
                    graph_snapshot,
                    [node_id],
                ),
                metric_value=count,
                threshold=policy.persistent_failure_zone_threshold,
                description=(
                    f"Node {node_id} appeared in {count} recent explicit incidents, so the "
                    "failure zone is no longer safe to ignore."
                ),
                suggested_action="Pause new fanout and rerun the CEO against the latest graph health snapshot.",
            )
        )
    return findings


def _freeze_spread_findings(
    graph_snapshot,
    *,
    policy: GraphHealthPolicy,
) -> list[GraphHealthFindingDigest]:
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
    if frozen_ratio <= policy.freeze_spread_ratio_threshold:
        return []
    return [
        _finding_digest(
            graph_snapshot,
            finding_type="FREEZE_SPREAD_TOO_WIDE",
            severity=_policy_severity(policy, "FREEZE_SPREAD_TOO_WIDE"),
            affected_graph_node_ids=frozen_graph_node_ids,
            metric_value=frozen_count,
            threshold=round(total_node_count * policy.freeze_spread_ratio_threshold, 2),
            description=(
                f"{frozen_count} of {total_node_count} nodes are frozen by an advisory patch, "
                f"exceeding the current spread threshold {policy.freeze_spread_ratio_threshold:.0%}."
            ),
            suggested_action="Review whether the freeze can be narrowed or the branch should be replanned.",
        )
    ]


def _graph_thrashing_findings(
    repository: ControlPlaneRepository,
    *,
    graph_snapshot,
    workflow_id: str,
    policy: GraphHealthPolicy,
    connection,
) -> list[GraphHealthFindingDigest]:
    patch_events = load_graph_patch_event_records(
        repository,
        workflow_id,
        connection=connection,
        limit=policy.graph_thrashing_window,
    )
    touched_counts: dict[tuple[str, ...], int] = {}
    for event in patch_events:
        touched_node_ids = tuple(sorted(graph_patch_target_node_ids(event.patch)))
        if not touched_node_ids:
            continue
        touched_counts[touched_node_ids] = touched_counts.get(touched_node_ids, 0) + 1

    findings: list[GraphHealthFindingDigest] = []
    for touched_node_ids, count in sorted(touched_counts.items()):
        if count <= policy.graph_thrashing_threshold:
            continue
        findings.append(
            _finding_digest(
                graph_snapshot,
                finding_type="GRAPH_THRASHING",
                severity=_policy_severity(policy, "GRAPH_THRASHING"),
                affected_graph_node_ids=list(touched_node_ids),
                metric_value=count,
                threshold=policy.graph_thrashing_threshold,
                description=(
                    f"The same graph patch target set was rewritten {count} times in the last "
                    f"{policy.graph_thrashing_window} graph patch events."
                ),
                suggested_action="Open a board advisory session or rerun the CEO before applying more graph churn.",
            )
        )
    return findings


def build_graph_health_report(
    repository: ControlPlaneRepository,
    workflow_id: str,
    *,
    policy: GraphHealthPolicy = DEFAULT_GRAPH_HEALTH_POLICY,
    connection=None,
) -> GraphHealthReportDigest:
    with repository.connection() if connection is None else nullcontext(connection) as resolved_connection:
        graph_snapshot = build_ticket_graph_snapshot(
            repository,
            workflow_id,
            connection=resolved_connection,
        )
        findings = [
            *_fanout_findings(graph_snapshot, policy=policy),
            *_bottleneck_findings(graph_snapshot, policy=policy),
            *_critical_path_findings(graph_snapshot, policy=policy),
            *_orphan_subgraph_findings(graph_snapshot, policy=policy),
            *_graph_thrashing_findings(
                repository,
                graph_snapshot=graph_snapshot,
                workflow_id=workflow_id,
                policy=policy,
                connection=resolved_connection,
            ),
            *_persistent_failure_zone_findings(
                repository,
                graph_snapshot=graph_snapshot,
                workflow_id=workflow_id,
                policy=policy,
                connection=resolved_connection,
            ),
            *_freeze_spread_findings(graph_snapshot, policy=policy),
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
