from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.contracts.ticket_graph import (
    TicketGraphBlockedReasonSummary,
    TicketGraphEdge,
    TicketGraphIndexSummary,
    TicketGraphNode,
    TicketGraphReductionIssue,
    TicketGraphSnapshot,
)
from app.core.output_schemas import (
    DELIVERY_CLOSEOUT_PACKAGE_SCHEMA_REF,
    GOVERNANCE_DOCUMENT_SCHEMA_REFS,
    MAKER_CHECKER_VERDICT_SCHEMA_REF,
)
from app.core.versioning import resolve_workflow_graph_version

if TYPE_CHECKING:
    import sqlite3

    from app.db.repository import ControlPlaneRepository


def _graph_node_id(ticket_id: str) -> str:
    return f"ticket:{ticket_id}"


def _resolve_dependency_gate_refs(created_spec: dict[str, Any]) -> list[str]:
    dispatch_intent = created_spec.get("dispatch_intent") or {}
    if not isinstance(dispatch_intent, dict):
        return []
    refs: list[str] = []
    for item in list(dispatch_intent.get("dependency_gate_refs") or []):
        value = str(item).strip()
        if value and value not in refs:
            refs.append(value)
    return refs


def _resolve_node_kind(created_spec: dict[str, Any]) -> str:
    output_schema_ref = str(created_spec.get("output_schema_ref") or "").strip()
    delivery_stage = str(created_spec.get("delivery_stage") or "").strip().upper()
    if output_schema_ref in GOVERNANCE_DOCUMENT_SCHEMA_REFS:
        return "GOVERNANCE"
    if output_schema_ref == MAKER_CHECKER_VERDICT_SCHEMA_REF or delivery_stage in {"CHECK", "REVIEW"}:
        return "REVIEW"
    if output_schema_ref == DELIVERY_CLOSEOUT_PACKAGE_SCHEMA_REF or delivery_stage == "CLOSEOUT":
        return "CLOSEOUT"
    return "IMPLEMENTATION"


def _append_edge(
    edges: list[TicketGraphEdge],
    seen_edges: set[tuple[str, str, str]],
    *,
    edge_type: str,
    graph_version: str,
    workflow_id: str,
    source_ticket_id: str,
    target_ticket_id: str,
    source_node_id: str,
    target_node_id: str,
) -> None:
    key = (edge_type, source_ticket_id, target_ticket_id)
    if key in seen_edges:
        return
    seen_edges.add(key)
    edges.append(
        TicketGraphEdge(
            edge_type=edge_type,
            workflow_id=workflow_id,
            graph_version=graph_version,
            source_graph_node_id=_graph_node_id(source_ticket_id),
            target_graph_node_id=_graph_node_id(target_ticket_id),
            source_ticket_id=source_ticket_id,
            target_ticket_id=target_ticket_id,
            source_node_id=source_node_id,
            target_node_id=target_node_id,
        )
    )


def _append_blocked_reason(
    blocked_reason_map: dict[str, dict[str, set[str]]],
    *,
    reason_code: str,
    ticket_id: str | None,
    node_id: str | None,
) -> None:
    entry = blocked_reason_map.setdefault(reason_code, {"ticket_ids": set(), "node_ids": set()})
    if ticket_id:
        entry["ticket_ids"].add(ticket_id)
    if node_id:
        entry["node_ids"].add(node_id)


def build_ticket_graph_snapshot(
    repository: "ControlPlaneRepository",
    workflow_id: str,
    *,
    connection: "sqlite3.Connection" | None = None,
) -> TicketGraphSnapshot:
    repository.initialize()
    if connection is None:
        with repository.connection() as owned_connection:
            return build_ticket_graph_snapshot(
                repository,
                workflow_id,
                connection=owned_connection,
            )

    workflow = repository.get_workflow_projection(workflow_id)
    if workflow is None:
        raise ValueError(f"Workflow {workflow_id} does not exist.")

    ticket_rows = connection.execute(
        """
        SELECT * FROM ticket_projection
        WHERE workflow_id = ?
        ORDER BY updated_at ASC, ticket_id ASC
        """,
        (workflow_id,),
    ).fetchall()
    node_rows = connection.execute(
        """
        SELECT * FROM node_projection
        WHERE workflow_id = ?
        ORDER BY updated_at ASC, node_id ASC
        """,
        (workflow_id,),
    ).fetchall()
    incident_rows = connection.execute(
        """
        SELECT node_id, circuit_breaker_state
        FROM incident_projection
        WHERE workflow_id = ? AND status = ?
        ORDER BY opened_at ASC, incident_id ASC
        """,
        (workflow_id, "OPEN"),
    ).fetchall()
    tickets = [repository._convert_ticket_projection_row(row) for row in ticket_rows]
    node_projection_by_node_id = {
        str(row["node_id"]): repository._convert_node_projection_row(row)
        for row in node_rows
    }
    open_incident_node_ids = {
        str(row["node_id"]).strip()
        for row in incident_rows
        if str(row["node_id"]).strip()
    }
    latest_ticket_id_by_node_id = {
        node_id: str(node.get("latest_ticket_id") or "").strip()
        for node_id, node in node_projection_by_node_id.items()
        if str(node.get("latest_ticket_id") or "").strip()
    }
    graph_version = resolve_workflow_graph_version(
        repository,
        workflow_id,
        connection=connection,
    )

    ticket_projection_by_ticket_id = {
        str(ticket["ticket_id"]): ticket
        for ticket in tickets
    }
    ticket_node_id_by_ticket_id: dict[str, str] = {}
    created_specs_by_ticket_id: dict[str, dict[str, Any]] = {}
    nodes: list[TicketGraphNode] = []

    for ticket in tickets:
        ticket_id = str(ticket["ticket_id"])
        created_spec = repository.get_latest_ticket_created_payload(connection, ticket_id) or {}
        created_specs_by_ticket_id[ticket_id] = created_spec
        node_id = str(ticket.get("node_id") or created_spec.get("node_id") or "").strip()
        ticket_node_id_by_ticket_id[ticket_id] = node_id
        node_projection = node_projection_by_node_id.get(node_id) or {}
        nodes.append(
            TicketGraphNode(
                graph_node_id=_graph_node_id(ticket_id),
                workflow_id=workflow_id,
                graph_version=graph_version,
                ticket_id=ticket_id,
                node_id=node_id,
                node_kind=_resolve_node_kind(created_spec),
                ticket_status=str(ticket.get("status") or "").strip() or None,
                node_status=str(node_projection.get("status") or "").strip() or None,
                role_profile_ref=str(created_spec.get("role_profile_ref") or "").strip() or None,
                output_schema_ref=str(created_spec.get("output_schema_ref") or "").strip() or None,
                delivery_stage=str(created_spec.get("delivery_stage") or "").strip().upper() or None,
                parent_ticket_id=str(created_spec.get("parent_ticket_id") or "").strip() or None,
                dependency_ticket_ids=_resolve_dependency_gate_refs(created_spec),
                blocking_reason_code=(
                    str(ticket.get("blocking_reason_code") or node_projection.get("blocking_reason_code") or "").strip()
                    or None
                ),
            )
        )

    edges: list[TicketGraphEdge] = []
    seen_edges: set[tuple[str, str, str]] = set()
    reduction_issues: list[TicketGraphReductionIssue] = []
    blocked_ticket_ids_from_issues: set[str] = set()
    blocked_node_ids_from_issues: set[str] = set()
    blocked_reason_map: dict[str, dict[str, set[str]]] = {}

    def record_issue(
        *,
        issue_code: str,
        detail: str,
        ticket_id: str | None,
        node_id: str | None,
        related_ticket_id: str | None = None,
    ) -> None:
        reduction_issues.append(
            TicketGraphReductionIssue(
                issue_code=issue_code,
                detail=detail,
                ticket_id=ticket_id,
                node_id=node_id,
                related_ticket_id=related_ticket_id,
            )
        )
        if ticket_id:
            blocked_ticket_ids_from_issues.add(ticket_id)
        if node_id:
            blocked_node_ids_from_issues.add(node_id)
        _append_blocked_reason(
            blocked_reason_map,
            reason_code="GRAPH_REDUCTION_ISSUE",
            ticket_id=ticket_id,
            node_id=node_id,
        )

    for ticket_id, created_spec in created_specs_by_ticket_id.items():
        node_id = ticket_node_id_by_ticket_id.get(ticket_id)
        parent_ticket_id = str(created_spec.get("parent_ticket_id") or "").strip()
        if parent_ticket_id:
            parent_node_id = ticket_node_id_by_ticket_id.get(parent_ticket_id)
            if parent_node_id is None:
                record_issue(
                    issue_code="graph.parent.missing_ticket",
                    detail=f"Ticket {ticket_id} points to missing parent ticket {parent_ticket_id}.",
                    ticket_id=ticket_id,
                    node_id=node_id,
                    related_ticket_id=parent_ticket_id,
                )
            else:
                _append_edge(
                    edges,
                    seen_edges,
                    edge_type="PARENT_OF",
                    graph_version=graph_version,
                    workflow_id=workflow_id,
                    source_ticket_id=parent_ticket_id,
                    target_ticket_id=ticket_id,
                    source_node_id=parent_node_id,
                    target_node_id=node_id or "",
                )

        for dependency_ticket_id in _resolve_dependency_gate_refs(created_spec):
            dependency_node_id = ticket_node_id_by_ticket_id.get(dependency_ticket_id)
            if dependency_node_id is None:
                record_issue(
                    issue_code="graph.dependency.missing_ticket",
                    detail=(
                        f"Ticket {ticket_id} depends on missing ticket {dependency_ticket_id}. "
                        "The graph adapter blocks this node instead of silently treating it as ready."
                    ),
                    ticket_id=ticket_id,
                    node_id=node_id,
                    related_ticket_id=dependency_ticket_id,
                )
                continue
            _append_edge(
                edges,
                seen_edges,
                edge_type="DEPENDS_ON",
                graph_version=graph_version,
                workflow_id=workflow_id,
                source_ticket_id=dependency_ticket_id,
                target_ticket_id=ticket_id,
                source_node_id=dependency_node_id,
                target_node_id=node_id or "",
            )

        maker_checker_context = created_spec.get("maker_checker_context") or {}
        maker_ticket_id = str(maker_checker_context.get("maker_ticket_id") or "").strip()
        if (
            str(created_spec.get("output_schema_ref") or "").strip() == MAKER_CHECKER_VERDICT_SCHEMA_REF
            and maker_ticket_id
        ):
            maker_node_id = ticket_node_id_by_ticket_id.get(maker_ticket_id)
            if maker_node_id is None:
                record_issue(
                    issue_code="graph.review.missing_maker_ticket",
                    detail=f"Checker ticket {ticket_id} points to missing maker ticket {maker_ticket_id}.",
                    ticket_id=ticket_id,
                    node_id=node_id,
                    related_ticket_id=maker_ticket_id,
                )
            else:
                _append_edge(
                    edges,
                    seen_edges,
                    edge_type="REVIEWS",
                    graph_version=graph_version,
                    workflow_id=workflow_id,
                    source_ticket_id=ticket_id,
                    target_ticket_id=maker_ticket_id,
                    source_node_id=node_id or "",
                    target_node_id=maker_node_id,
                )

    ready_ticket_ids: list[str] = []
    ready_node_ids: list[str] = []
    blocked_ticket_ids: list[str] = []
    blocked_node_ids: list[str] = []
    in_flight_ticket_ids: list[str] = []
    in_flight_node_ids: list[str] = []
    parent_ticket_id_by_ticket_id = {
        ticket_id: str((created_specs_by_ticket_id.get(ticket_id) or {}).get("parent_ticket_id") or "").strip() or None
        for ticket_id in ticket_projection_by_ticket_id
    }

    for node_id, latest_ticket_id in latest_ticket_id_by_node_id.items():
        ticket_projection = ticket_projection_by_ticket_id.get(latest_ticket_id)
        if ticket_projection is None:
            record_issue(
                issue_code="graph.node.latest_ticket_missing",
                detail=f"Node {node_id} points to missing latest ticket {latest_ticket_id}.",
                ticket_id=latest_ticket_id,
                node_id=node_id,
            )
            continue
        ticket_status = str(ticket_projection.get("status") or "").strip()
        node_status = str((node_projection_by_node_id.get(node_id) or {}).get("status") or "").strip()
        blocking_reason_code = str(
            ticket_projection.get("blocking_reason_code")
            or (node_projection_by_node_id.get(node_id) or {}).get("blocking_reason_code")
            or ""
        ).strip()
        blocked_by_graph = latest_ticket_id in blocked_ticket_ids_from_issues or node_id in blocked_node_ids_from_issues
        is_board_review_open = (
            ticket_status == "BLOCKED_FOR_BOARD_REVIEW" or node_status == "BLOCKED_FOR_BOARD_REVIEW"
        )
        has_open_incident = node_id in open_incident_node_ids
        is_in_flight = ticket_status in {"LEASED", "EXECUTING"} or node_status == "EXECUTING"
        if is_in_flight:
            in_flight_ticket_ids.append(latest_ticket_id)
            in_flight_node_ids.append(node_id)

        if (
            ticket_status == "PENDING"
            and not blocked_by_graph
            and not blocking_reason_code
            and not is_board_review_open
            and not has_open_incident
        ):
            ready_ticket_ids.append(latest_ticket_id)
            ready_node_ids.append(node_id)
            continue
        if blocked_by_graph or blocking_reason_code or is_board_review_open or has_open_incident:
            blocked_ticket_ids.append(latest_ticket_id)
            blocked_node_ids.append(node_id)
        if has_open_incident:
            _append_blocked_reason(
                blocked_reason_map,
                reason_code="INCIDENT_OPEN",
                ticket_id=latest_ticket_id,
                node_id=node_id,
            )
        if is_board_review_open:
            _append_blocked_reason(
                blocked_reason_map,
                reason_code="BOARD_REVIEW_OPEN",
                ticket_id=latest_ticket_id,
                node_id=node_id,
            )
        if blocking_reason_code:
            _append_blocked_reason(
                blocked_reason_map,
                reason_code=f"EXPLICIT_BLOCKING_REASON:{blocking_reason_code}",
                ticket_id=latest_ticket_id,
                node_id=node_id,
            )

    critical_path_node_ids: set[str] = set()
    for current_ticket_id in [*blocked_ticket_ids, *in_flight_ticket_ids]:
        parent_cursor = current_ticket_id
        visited_ticket_ids: set[str] = set()
        while parent_cursor and parent_cursor not in visited_ticket_ids:
            visited_ticket_ids.add(parent_cursor)
            node_cursor = ticket_node_id_by_ticket_id.get(parent_cursor)
            if node_cursor:
                critical_path_node_ids.add(node_cursor)
            parent_cursor = parent_ticket_id_by_ticket_id.get(parent_cursor) or None

    blocked_reasons = [
        TicketGraphBlockedReasonSummary(
            reason_code=reason_code,
            ticket_ids=sorted(entry["ticket_ids"]),
            node_ids=sorted(entry["node_ids"]),
            count=max(len(entry["ticket_ids"]), len(entry["node_ids"])),
        )
        for reason_code, entry in sorted(blocked_reason_map.items())
    ]

    return TicketGraphSnapshot(
        workflow_id=workflow_id,
        graph_version=graph_version,
        nodes=nodes,
        edges=edges,
        index_summary=TicketGraphIndexSummary(
            ready_ticket_ids=sorted(set(ready_ticket_ids)),
            ready_node_ids=sorted(set(ready_node_ids)),
            blocked_ticket_ids=sorted(set(blocked_ticket_ids)),
            blocked_node_ids=sorted(set(blocked_node_ids)),
            in_flight_ticket_ids=sorted(set(in_flight_ticket_ids)),
            in_flight_node_ids=sorted(set(in_flight_node_ids)),
            critical_path_node_ids=sorted(critical_path_node_ids),
            blocked_reasons=blocked_reasons,
            reduction_issue_count=len(reduction_issues),
        ),
        reduction_issues=reduction_issues,
    )
