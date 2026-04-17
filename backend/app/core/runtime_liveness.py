from __future__ import annotations

from contextlib import nullcontext
from datetime import datetime
from typing import Any

from app.contracts.ceo import GraphHealthFindingDigest, RuntimeLivenessReportDigest
from app.core.constants import (
    EVENT_BOARD_REVIEW_REQUIRED,
    EVENT_GRAPH_PATCH_APPLIED,
    EVENT_INCIDENT_CLOSED,
    EVENT_INCIDENT_OPENED,
    EVENT_TICKET_EXECUTION_PRECONDITION_BLOCKED,
    EVENT_TICKET_EXECUTION_PRECONDITION_CLEARED,
)
from app.core.runtime_liveness_policy import (
    DEFAULT_RUNTIME_LIVENESS_POLICY,
    RuntimeLivenessPolicy,
)
from app.core.ticket_graph import build_ticket_graph_snapshot
from app.core.time import now_local
from app.db.repository import ControlPlaneRepository


class RuntimeLivenessUnavailableError(RuntimeError):
    pass


def _raise_runtime_liveness_unavailable(reason: str) -> None:
    raise RuntimeLivenessUnavailableError(f"runtime liveness unavailable: {reason}")


def _policy_severity(policy: RuntimeLivenessPolicy, finding_type: str) -> str:
    return str(policy.finding_severities.get(finding_type) or "WARNING")


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


def _workflow_runtime_node_projections(
    repository: ControlPlaneRepository,
    *,
    workflow_id: str,
    connection,
) -> dict[str, dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT *
        FROM runtime_node_projection
        WHERE workflow_id = ?
        ORDER BY updated_at ASC, graph_node_id ASC
        """,
        (workflow_id,),
    ).fetchall()
    return {
        str(row["graph_node_id"]).strip(): repository._convert_runtime_node_projection_row(row)
        for row in rows
        if str(row["graph_node_id"]).strip()
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


def _require_runtime_projection_for_graph_node(
    graph_snapshot,
    runtime_node_by_graph_node_id: dict[str, dict[str, Any]],
    *,
    graph_node_id: str,
    expected_ticket_id: str | None = None,
) -> dict[str, Any]:
    normalized_graph_node_id = str(graph_node_id or "").strip()
    runtime_node = runtime_node_by_graph_node_id.get(normalized_graph_node_id)
    if runtime_node is None:
        _raise_runtime_liveness_unavailable(
            f"graph lane {normalized_graph_node_id} is missing runtime_node_projection."
        )
    graph_node = _graph_node_by_graph_node_id(graph_snapshot).get(normalized_graph_node_id)
    if graph_node is None:
        _raise_runtime_liveness_unavailable(
            f"runtime liveness cannot find graph lane {normalized_graph_node_id} in the graph snapshot."
        )
    runtime_node_id = str(runtime_node.get("runtime_node_id") or "").strip()
    graph_runtime_node_id = str(graph_node.runtime_node_id or "").strip()
    projection_node_id = str(runtime_node.get("node_id") or "").strip()
    graph_node_id_value = str(graph_node.node_id or "").strip()
    if runtime_node_id != graph_runtime_node_id or projection_node_id != graph_node_id_value:
        _raise_runtime_liveness_unavailable(
            f"runtime_node_projection {normalized_graph_node_id} does not match graph/runtime identity."
        )
    latest_ticket_id = str(runtime_node.get("latest_ticket_id") or "").strip()
    graph_ticket_id = str(graph_node.ticket_id or "").strip()
    if expected_ticket_id is not None and latest_ticket_id != expected_ticket_id:
        _raise_runtime_liveness_unavailable(
            f"runtime_node_projection {normalized_graph_node_id} points to {latest_ticket_id or '<missing>'} "
            f"instead of {expected_ticket_id}."
        )
    if latest_ticket_id != graph_ticket_id:
        _raise_runtime_liveness_unavailable(
            f"runtime_node_projection {normalized_graph_node_id} latest ticket {latest_ticket_id or '<missing>'} "
            f"does not match graph ticket {graph_ticket_id or '<missing>'}."
        )
    return runtime_node


def _validate_runtime_truth_for_materialized_graph_lanes(
    graph_snapshot,
    runtime_node_by_graph_node_id: dict[str, dict[str, Any]],
) -> None:
    for graph_node in graph_snapshot.nodes:
        if bool(getattr(graph_node, "is_placeholder", False)):
            continue
        graph_node_id = str(graph_node.graph_node_id or "").strip()
        if not graph_node_id:
            _raise_runtime_liveness_unavailable("materialized graph lane is missing graph_node_id.")
        _require_runtime_projection_for_graph_node(
            graph_snapshot,
            runtime_node_by_graph_node_id,
            graph_node_id=graph_node_id,
            expected_ticket_id=str(graph_node.ticket_id or "").strip() or None,
        )


def _require_datetime(
    value: Any,
    *,
    reason: str,
) -> datetime:
    if not isinstance(value, datetime):
        _raise_runtime_liveness_unavailable(reason)
    return value


def _require_int(
    value: Any,
    *,
    reason: str,
) -> int:
    if not isinstance(value, int):
        _raise_runtime_liveness_unavailable(reason)
    return int(value)


def _graph_version_int(graph_version: str) -> int:
    normalized = str(graph_version or "").strip()
    if not normalized.startswith("gv_") or not normalized[3:].isdigit():
        _raise_runtime_liveness_unavailable(f"invalid graph version {normalized or '<empty>'}.")
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
        _raise_runtime_liveness_unavailable(f"{event_id} field {field_name} must be list[str].")
    normalized: list[str] = []
    for item in value:
        if not isinstance(item, str):
            _raise_runtime_liveness_unavailable(f"{event_id} field {field_name} must be list[str].")
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
    if not event_types:
        return []
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


def _queue_starvation_findings(
    repository: ControlPlaneRepository,
    *,
    graph_snapshot,
    workflow_id: str,
    policy: RuntimeLivenessPolicy,
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
    runtime_node_by_graph_node_id = _workflow_runtime_node_projections(
        repository,
        workflow_id=workflow_id,
        connection=connection,
    )
    current_time = now_local()
    findings: list[GraphHealthFindingDigest] = []
    for node_id in ready_node_ids:
        ticket_id = latest_ticket_id_by_node_id.get(node_id)
        if not ticket_id:
            _raise_runtime_liveness_unavailable(
                f"ready node {node_id} is missing its latest ticket projection."
            )
        ticket = ticket_by_ticket_id.get(ticket_id)
        if ticket is None:
            _raise_runtime_liveness_unavailable(
                f"ready node {node_id} points to missing ticket {ticket_id}."
            )
        runtime_node = _require_runtime_projection_for_graph_node(
            graph_snapshot,
            runtime_node_by_graph_node_id,
            graph_node_id=node_id,
            expected_ticket_id=ticket_id,
        )
        if str(runtime_node.get("status") or "").strip() != "PENDING":
            _raise_runtime_liveness_unavailable(
                f"ready graph lane {node_id} is backed by runtime status {runtime_node.get('status')!r}."
            )
        updated_at = _require_datetime(
            runtime_node.get("updated_at"),
            reason=f"ready runtime node {node_id} is missing updated_at.",
        )
        timeout_sla_sec = _require_int(
            ticket.get("timeout_sla_sec"),
            reason=f"ready ticket {ticket_id} is missing timeout_sla_sec.",
        )
        _require_int(
            runtime_node.get("version"),
            reason=f"ready runtime node {node_id} is missing version.",
        )
        starvation_threshold_sec = timeout_sla_sec * policy.queue_starvation_multiplier
        starvation_age_sec = int((current_time - updated_at).total_seconds())
        if starvation_age_sec <= starvation_threshold_sec:
            continue
        findings.append(
            _finding_digest(
                graph_snapshot,
                finding_type="QUEUE_STARVATION",
                severity=_policy_severity(policy, "QUEUE_STARVATION"),
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
    policy: RuntimeLivenessPolicy,
    connection,
) -> list[GraphHealthFindingDigest]:
    events = _workflow_timeline_events(
        repository,
        workflow_id=workflow_id,
        event_types=policy.ready_blocked_event_types,
        connection=connection,
        limit=policy.ready_blocked_thrashing_window,
    )
    state_history_by_node_id: dict[str, list[str]] = {}

    for event in events:
        event_type = str(event.get("event_type") or "").strip()
        event_id = str(event.get("event_id") or "").strip() or "event"
        payload = event.get("payload")
        if not isinstance(payload, dict):
            _raise_runtime_liveness_unavailable(f"{event_id} payload must be an object.")

        transitions: list[tuple[str, str]] = []
        if event_type == EVENT_TICKET_EXECUTION_PRECONDITION_BLOCKED:
            node_id = _normalize_node_id(payload.get("node_id"))
            if not node_id:
                _raise_runtime_liveness_unavailable(f"{event_id} is missing node_id.")
            transitions.append((node_id, "BLOCKED"))
        elif event_type == EVENT_TICKET_EXECUTION_PRECONDITION_CLEARED:
            node_id = _normalize_node_id(payload.get("node_id"))
            if not node_id:
                _raise_runtime_liveness_unavailable(f"{event_id} is missing node_id.")
            transitions.append((node_id, "READY"))
        elif event_type == EVENT_BOARD_REVIEW_REQUIRED:
            node_id = _normalize_node_id(payload.get("node_id"))
            if not node_id:
                _raise_runtime_liveness_unavailable(f"{event_id} is missing node_id.")
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
        if oscillation_count < policy.ready_blocked_thrashing_threshold:
            continue
        findings.append(
            _finding_digest(
                graph_snapshot,
                finding_type="READY_BLOCKED_THRASHING",
                severity=_policy_severity(policy, "READY_BLOCKED_THRASHING"),
                affected_graph_node_ids=_graph_node_ids_for_runtime_node_ids(
                    graph_snapshot,
                    [node_id],
                ),
                metric_value=oscillation_count,
                threshold=policy.ready_blocked_thrashing_threshold,
                description=(
                    f"Node {node_id} oscillated between READY and BLOCKED {oscillation_count} "
                    f"times in the last {policy.ready_blocked_thrashing_window} explicit timeline events."
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
    policy: RuntimeLivenessPolicy,
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
    runtime_node_by_graph_node_id = _workflow_runtime_node_projections(
        repository,
        workflow_id=workflow_id,
        connection=connection,
    )
    current_time = now_local()
    findings: list[GraphHealthFindingDigest] = []
    for node_id in ready_node_ids:
        ticket_id = latest_ticket_id_by_node_id.get(node_id)
        if not ticket_id:
            _raise_runtime_liveness_unavailable(
                f"ready node {node_id} is missing its latest ticket projection."
            )
        ticket = ticket_by_ticket_id.get(ticket_id)
        if ticket is None:
            _raise_runtime_liveness_unavailable(
                f"ready node {node_id} points to missing ticket {ticket_id}."
            )
        runtime_node = _require_runtime_projection_for_graph_node(
            graph_snapshot,
            runtime_node_by_graph_node_id,
            graph_node_id=node_id,
            expected_ticket_id=ticket_id,
        )
        if str(runtime_node.get("status") or "").strip() != "PENDING":
            _raise_runtime_liveness_unavailable(
                f"ready graph lane {node_id} is backed by runtime status {runtime_node.get('status')!r}."
            )
        updated_at = _require_datetime(
            runtime_node.get("updated_at"),
            reason=f"ready runtime node {node_id} is missing updated_at.",
        )
        timeout_sla_sec = _require_int(
            ticket.get("timeout_sla_sec"),
            reason=f"ready ticket {ticket_id} is missing timeout_sla_sec.",
        )
        stale_threshold_sec = timeout_sla_sec * policy.ready_node_stale_multiplier
        stale_age_sec = int((current_time - updated_at).total_seconds())
        if stale_age_sec <= stale_threshold_sec:
            continue
        findings.append(
            _finding_digest(
                graph_snapshot,
                finding_type="READY_NODE_STALE",
                severity=_policy_severity(policy, "READY_NODE_STALE"),
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
    policy: RuntimeLivenessPolicy,
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
    runtime_node_by_graph_node_id = _workflow_runtime_node_projections(
        repository,
        workflow_id=workflow_id,
        connection=connection,
    )
    current_time = now_local()
    findings: list[GraphHealthFindingDigest] = []
    for node_id in blocked_node_ids:
        ticket_id = latest_ticket_id_by_node_id.get(node_id)
        if not ticket_id:
            _raise_runtime_liveness_unavailable(
                f"blocked node {node_id} is missing its latest ticket projection."
            )
        ticket = ticket_by_ticket_id.get(ticket_id)
        if ticket is None:
            _raise_runtime_liveness_unavailable(
                f"blocked node {node_id} points to missing ticket {ticket_id}."
            )
        runtime_node = _require_runtime_projection_for_graph_node(
            graph_snapshot,
            runtime_node_by_graph_node_id,
            graph_node_id=node_id,
            expected_ticket_id=ticket_id,
        )
        ticket_updated_at = _require_datetime(
            ticket.get("updated_at"),
            reason=f"blocked ticket {ticket_id} is missing updated_at.",
        )
        runtime_updated_at = _require_datetime(
            runtime_node.get("updated_at"),
            reason=f"blocked runtime node {node_id} is missing updated_at.",
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
            runtime_node.get("version"),
            reason=f"blocked runtime node {node_id} is missing version.",
        )
        latest_projection_version = max(ticket_version, node_version)
        version_delta = current_graph_version_int - latest_projection_version
        if version_delta < policy.cross_version_sla_version_delta_threshold:
            continue
        blocked_updated_at = max(ticket_updated_at, runtime_updated_at)
        blocked_age_sec = int((current_time - blocked_updated_at).total_seconds())
        blocked_threshold_sec = timeout_sla_sec * policy.cross_version_sla_multiplier
        if blocked_age_sec <= blocked_threshold_sec:
            continue
        findings.append(
            _finding_digest(
                graph_snapshot,
                finding_type="CROSS_VERSION_SLA_BREACH",
                severity=_policy_severity(policy, "CROSS_VERSION_SLA_BREACH"),
                affected_graph_node_ids=[node_id],
                metric_value=version_delta,
                threshold=policy.cross_version_sla_version_delta_threshold,
                description=(
                    f"Blocked node {node_id} stayed unresolved for {blocked_age_sec} seconds "
                    f"while the graph advanced {version_delta} versions."
                ),
                suggested_action="Rerun the CEO or clear the blocker before more graph versions accumulate on stale work.",
            )
        )
    return findings


def build_runtime_liveness_report(
    repository: ControlPlaneRepository,
    workflow_id: str,
    *,
    policy: RuntimeLivenessPolicy = DEFAULT_RUNTIME_LIVENESS_POLICY,
    connection=None,
) -> RuntimeLivenessReportDigest:
    with repository.connection() if connection is None else nullcontext(connection) as resolved_connection:
        graph_snapshot = build_ticket_graph_snapshot(
            repository,
            workflow_id,
            connection=resolved_connection,
        )
        runtime_node_by_graph_node_id = _workflow_runtime_node_projections(
            repository,
            workflow_id=workflow_id,
            connection=resolved_connection,
        )
        _validate_runtime_truth_for_materialized_graph_lanes(
            graph_snapshot,
            runtime_node_by_graph_node_id,
        )
        findings = [
            *_queue_starvation_findings(
                repository,
                graph_snapshot=graph_snapshot,
                workflow_id=workflow_id,
                policy=policy,
                connection=resolved_connection,
            ),
            *_ready_blocked_thrashing_findings(
                repository,
                graph_snapshot=graph_snapshot,
                workflow_id=workflow_id,
                policy=policy,
                connection=resolved_connection,
            ),
            *_ready_node_stale_findings(
                repository,
                graph_snapshot=graph_snapshot,
                workflow_id=workflow_id,
                policy=policy,
                connection=resolved_connection,
            ),
            *_cross_version_sla_breach_findings(
                repository,
                graph_snapshot=graph_snapshot,
                workflow_id=workflow_id,
                policy=policy,
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
    return RuntimeLivenessReportDigest(
        report_id=f"rlr://{workflow_id}/{graph_snapshot.graph_version}",
        workflow_id=workflow_id,
        graph_version=graph_snapshot.graph_version,
        overall_health=overall_health,
        findings=findings,
        recommended_actions=recommended_actions,
    )
