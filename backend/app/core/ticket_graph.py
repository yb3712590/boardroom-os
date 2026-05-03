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
from app.core.constants import (
    BLOCKING_REASON_ADVISORY_PATCH_FROZEN,
    NODE_STATUS_BLOCKED_FOR_BOARD_REVIEW,
    NODE_STATUS_CANCELLED,
    NODE_STATUS_CANCEL_REQUESTED,
    NODE_STATUS_COMPLETED,
    NODE_STATUS_EXECUTING,
    NODE_STATUS_PENDING,
    NODE_STATUS_REWORK_REQUIRED,
    NODE_STATUS_SUPERSEDED,
)
from app.core.graph_identity import (
    GRAPH_LANE_EXECUTION,
    TicketGraphIdentity,
    resolve_graph_lane_kind,
    resolve_ticket_graph_identity,
)
from app.core.graph_patch_reducer import (
    load_graph_patch_event_records,
    reduce_graph_patch_overlay,
)
from app.core.output_schemas import (
    DELIVERY_CLOSEOUT_PACKAGE_SCHEMA_REF,
    GOVERNANCE_DOCUMENT_SCHEMA_REFS,
    MAKER_CHECKER_VERDICT_SCHEMA_REF,
)
from app.core.role_hooks import HookGateStatus, evaluate_ticket_required_hook_gate
from app.core.versioning import resolve_workflow_graph_version

if TYPE_CHECKING:
    import sqlite3

    from app.db.repository import ControlPlaneRepository


_GRAPH_PATH_EDGE_TYPES = {"PARENT_OF", "DEPENDS_ON"}


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
    source_ticket_id: str | None,
    target_ticket_id: str | None,
    source_graph_node_id: str,
    target_graph_node_id: str,
    source_runtime_node_id: str | None,
    target_runtime_node_id: str | None,
) -> None:
    key = (edge_type, source_graph_node_id, target_graph_node_id)
    if key in seen_edges:
        return
    seen_edges.add(key)
    edges.append(
        TicketGraphEdge(
            edge_type=edge_type,
            workflow_id=workflow_id,
            graph_version=graph_version,
            source_graph_node_id=source_graph_node_id,
            target_graph_node_id=target_graph_node_id,
            source_ticket_id=source_ticket_id,
            target_ticket_id=target_ticket_id,
            source_node_id=source_runtime_node_id or source_graph_node_id,
            target_node_id=target_runtime_node_id or target_graph_node_id,
            source_runtime_node_id=source_runtime_node_id,
            target_runtime_node_id=target_runtime_node_id,
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


def _status_from_ticket_status(ticket_status: str | None) -> str | None:
    normalized = str(ticket_status or "").strip().upper()
    if not normalized:
        return None
    if normalized == "EXECUTING":
        return NODE_STATUS_EXECUTING
    if normalized == "BLOCKED_FOR_BOARD_REVIEW":
        return NODE_STATUS_BLOCKED_FOR_BOARD_REVIEW
    if normalized == "COMPLETED":
        return NODE_STATUS_COMPLETED
    if normalized == "REWORK_REQUIRED":
        return NODE_STATUS_REWORK_REQUIRED
    if normalized in {"FAILED", "TIMED_OUT"}:
        return NODE_STATUS_REWORK_REQUIRED
    if normalized == "CANCELLED":
        return NODE_STATUS_CANCELLED
    if normalized == "CANCEL_REQUESTED":
        return NODE_STATUS_CANCEL_REQUESTED
    return NODE_STATUS_PENDING


def _is_removed_from_effective_graph(node: TicketGraphNode | None) -> bool:
    if node is None:
        return False
    node_status = str(node.node_status or "").strip()
    return node_status in {NODE_STATUS_CANCELLED, NODE_STATUS_SUPERSEDED}


def _effective_graph_node_status(
    *,
    graph_node_id: str,
    ticket_projection: dict[str, Any],
    runtime_node_projection: dict[str, Any],
    is_runtime_latest_ticket: bool,
    node_status_overrides: dict[str, str],
) -> str | None:
    override_status = str(node_status_overrides.get(graph_node_id) or "").strip()
    if override_status:
        return override_status
    if is_runtime_latest_ticket:
        runtime_node_status = str(runtime_node_projection.get("status") or "").strip()
        if runtime_node_status:
            return runtime_node_status
    return _status_from_ticket_status(ticket_projection.get("status"))


def _effective_blocking_reason_code(
    *,
    ticket_projection: dict[str, Any],
    runtime_node_projection: dict[str, Any],
    is_runtime_latest_ticket: bool,
) -> str | None:
    if is_runtime_latest_ticket:
        runtime_reason = str(runtime_node_projection.get("blocking_reason_code") or "").strip()
        if runtime_reason:
            return runtime_reason
    ticket_reason = str(ticket_projection.get("blocking_reason_code") or "").strip()
    return ticket_reason or None


def _should_skip_internal_parent_edge(
    *,
    child_identity: TicketGraphIdentity,
    parent_identity: TicketGraphIdentity,
) -> bool:
    return child_identity.runtime_node_id == parent_identity.runtime_node_id


def _resolve_parent_lane_anchor(
    *,
    ticket_id: str,
    child_identity: TicketGraphIdentity,
    created_specs_by_ticket_id: dict[str, dict[str, Any]],
    identities_by_ticket_id: dict[str, TicketGraphIdentity],
    latest_ticket_id_by_graph_node_id: dict[str, str],
) -> dict[str, Any] | None:
    current_ticket_id = ticket_id
    seen_ticket_ids: set[str] = set()
    while current_ticket_id and current_ticket_id not in seen_ticket_ids:
        seen_ticket_ids.add(current_ticket_id)
        created_spec = created_specs_by_ticket_id.get(current_ticket_id) or {}
        parent_ticket_id = str(created_spec.get("parent_ticket_id") or "").strip()
        if not parent_ticket_id:
            return None
        parent_identity = identities_by_ticket_id.get(parent_ticket_id)
        if parent_identity is None:
            return {
                "issue_code": "graph.parent.missing_ticket",
                "detail": f"Ticket {ticket_id} points to missing parent ticket {parent_ticket_id}.",
                "related_ticket_id": parent_ticket_id,
            }
        if _should_skip_internal_parent_edge(
            child_identity=child_identity,
            parent_identity=parent_identity,
        ):
            current_ticket_id = parent_ticket_id
            continue
        parent_current_ticket_id = latest_ticket_id_by_graph_node_id.get(parent_identity.graph_node_id)
        if not parent_current_ticket_id:
            return {
                "issue_code": "graph.parent.missing_current_lane_ticket",
                "detail": (
                    f"Ticket {ticket_id} points to parent lane {parent_identity.graph_node_id}, "
                    "but the current graph lane has no active ticket."
                ),
                "related_ticket_id": parent_ticket_id,
            }
        return {
            "parent_ticket_id": parent_current_ticket_id,
            "parent_identity": parent_identity,
            "related_ticket_id": parent_ticket_id,
        }
    return None


def _choose_current_ticket_id_for_graph_node(
    *,
    graph_node_id: str,
    candidate_ticket_ids: list[str],
    runtime_node_projection: dict[str, Any],
    node_status_overrides: dict[str, str],
) -> tuple[str | None, dict[str, Any] | None]:
    runtime_latest_ticket_id = str(runtime_node_projection.get("latest_ticket_id") or "").strip()
    if runtime_latest_ticket_id:
        if runtime_latest_ticket_id in candidate_ticket_ids:
            return runtime_latest_ticket_id, None
        return None, {
            "issue_code": "graph.current_pointer.runtime_latest_missing",
            "detail": (
                f"Runtime graph lane {graph_node_id} points to latest ticket "
                f"{runtime_latest_ticket_id}, but that ticket is not present in ticket_projection."
            ),
            "related_ticket_id": runtime_latest_ticket_id,
        }
    if str(node_status_overrides.get(graph_node_id) or "").strip() in {
        NODE_STATUS_CANCELLED,
        NODE_STATUS_SUPERSEDED,
    }:
        return sorted(candidate_ticket_ids)[0] if candidate_ticket_ids else None, None
    if len(candidate_ticket_ids) == 1:
        return candidate_ticket_ids[0], None
    return None, {
        "issue_code": "graph.current_pointer.missing_explicit",
        "detail": (
            f"Graph lane {graph_node_id} has multiple candidate tickets but no explicit "
            "runtime current pointer or replacement edge."
        ),
        "related_ticket_id": ",".join(sorted(candidate_ticket_ids)) or None,
    }


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

    repository.get_workflow_projection(workflow_id, connection=connection)

    ticket_rows = connection.execute(
        """
        SELECT * FROM ticket_projection
        WHERE workflow_id = ?
        ORDER BY updated_at ASC, ticket_id ASC
        """,
        (workflow_id,),
    ).fetchall()
    runtime_node_rows = connection.execute(
        """
        SELECT * FROM runtime_node_projection
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
    ticket_projection_by_ticket_id = {
        str(ticket["ticket_id"]): ticket
        for ticket in tickets
    }
    runtime_node_projection_by_graph_node_id = {
        str(row["graph_node_id"]): repository._convert_runtime_node_projection_row(row)
        for row in runtime_node_rows
    }
    open_incident_runtime_node_ids = {
        str(row["node_id"]).strip()
        for row in incident_rows
        if str(row["node_id"]).strip()
    }
    try:
        graph_version = resolve_workflow_graph_version(
            repository,
            workflow_id,
            connection=connection,
        )
    except ValueError:
        graph_version = "gv_0"

    created_specs_by_ticket_id: dict[str, dict[str, Any]] = {}
    identities_by_ticket_id: dict[str, TicketGraphIdentity] = {}
    latest_ticket_id_by_graph_node_id: dict[str, str] = {}
    candidate_ticket_ids_by_graph_node_id: dict[str, list[str]] = {}
    current_pointer_issues: list[dict[str, Any]] = []

    for ticket in tickets:
        ticket_id = str(ticket["ticket_id"])
        created_spec = repository.get_latest_ticket_created_payload(connection, ticket_id) or {}
        created_specs_by_ticket_id[ticket_id] = created_spec
        identity = resolve_ticket_graph_identity(
            ticket_id=ticket_id,
            created_spec=created_spec,
            runtime_node_id=str(ticket.get("node_id") or created_spec.get("node_id") or "").strip(),
        )
        identities_by_ticket_id[ticket_id] = identity
        candidate_ticket_ids_by_graph_node_id.setdefault(identity.graph_node_id, []).append(ticket_id)

    for graph_node_id, candidate_ticket_ids in sorted(candidate_ticket_ids_by_graph_node_id.items()):
        runtime_node_projection = (
            runtime_node_projection_by_graph_node_id.get(graph_node_id) or {}
        )
        selected_ticket_id, current_pointer_issue = _choose_current_ticket_id_for_graph_node(
            graph_node_id=graph_node_id,
            candidate_ticket_ids=sorted(candidate_ticket_ids),
            runtime_node_projection=runtime_node_projection,
            node_status_overrides={},
        )
        if current_pointer_issue is not None:
            current_pointer_issue["graph_node_id"] = graph_node_id
            current_pointer_issue["node_id"] = identities_by_ticket_id[candidate_ticket_ids[0]].runtime_node_id
            current_pointer_issues.append(current_pointer_issue)
            continue
        if selected_ticket_id:
            latest_ticket_id_by_graph_node_id[graph_node_id] = selected_ticket_id

    nodes: list[TicketGraphNode] = []
    for graph_node_id in sorted(latest_ticket_id_by_graph_node_id):
        ticket_id = latest_ticket_id_by_graph_node_id[graph_node_id]
        ticket_projection = ticket_projection_by_ticket_id.get(ticket_id)
        if ticket_projection is None:
            continue
        identity = identities_by_ticket_id[ticket_id]
        created_spec = created_specs_by_ticket_id.get(ticket_id) or {}
        runtime_node_projection = (
            runtime_node_projection_by_graph_node_id.get(identity.graph_node_id) or {}
        )
        is_runtime_latest_ticket = (
            str(runtime_node_projection.get("latest_ticket_id") or "").strip() == ticket_id
        )
        nodes.append(
            TicketGraphNode(
                graph_node_id=identity.graph_node_id,
                workflow_id=workflow_id,
                graph_version=graph_version,
                ticket_id=ticket_id,
                node_id=identity.runtime_node_id,
                runtime_node_id=identity.runtime_node_id,
                graph_lane_kind=identity.graph_lane_kind,
                node_kind=_resolve_node_kind(created_spec),
                deliverable_kind=str(created_spec.get("deliverable_kind") or "").strip() or None,
                role_hint=str(created_spec.get("role_profile_ref") or "").strip() or None,
                ticket_status=str(ticket_projection.get("status") or "").strip() or None,
                node_status=_effective_graph_node_status(
                    graph_node_id=identity.graph_node_id,
                    ticket_projection=ticket_projection,
                    runtime_node_projection=runtime_node_projection,
                    is_runtime_latest_ticket=is_runtime_latest_ticket,
                    node_status_overrides={},
                ),
                role_profile_ref=str(created_spec.get("role_profile_ref") or "").strip() or None,
                output_schema_ref=str(created_spec.get("output_schema_ref") or "").strip() or None,
                delivery_stage=str(created_spec.get("delivery_stage") or "").strip().upper() or None,
                parent_ticket_id=str(created_spec.get("parent_ticket_id") or "").strip() or None,
                dependency_ticket_ids=_resolve_dependency_gate_refs(created_spec),
                blocking_reason_code=_effective_blocking_reason_code(
                    ticket_projection=ticket_projection,
                    runtime_node_projection=runtime_node_projection,
                    is_runtime_latest_ticket=is_runtime_latest_ticket,
                ),
                is_placeholder=False,
            )
        )

    edges: list[TicketGraphEdge] = []
    seen_edges: set[tuple[str, str, str]] = set()
    reduction_issues: list[TicketGraphReductionIssue] = []
    blocked_ticket_ids_from_issues: set[str] = set()
    blocked_runtime_node_ids_from_issues: set[str] = set()
    blocked_graph_node_ids_from_issues: set[str] = set()
    blocked_reason_map: dict[str, dict[str, set[str]]] = {}

    def record_issue(
        *,
        issue_code: str,
        detail: str,
        ticket_id: str | None,
        node_id: str | None,
        graph_node_id: str | None = None,
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
            blocked_runtime_node_ids_from_issues.add(node_id)
        if graph_node_id:
            blocked_graph_node_ids_from_issues.add(graph_node_id)
        _append_blocked_reason(
            blocked_reason_map,
            reason_code="GRAPH_REDUCTION_ISSUE",
            ticket_id=ticket_id,
            node_id=node_id,
        )

    for current_pointer_issue in current_pointer_issues:
        record_issue(
            issue_code=str(current_pointer_issue.get("issue_code") or "graph.current_pointer.issue"),
            detail=str(current_pointer_issue.get("detail") or ""),
            ticket_id=None,
            node_id=str(current_pointer_issue.get("node_id") or "") or None,
            graph_node_id=str(current_pointer_issue.get("graph_node_id") or "") or None,
            related_ticket_id=str(current_pointer_issue.get("related_ticket_id") or "") or None,
        )

    for graph_node_id in sorted(latest_ticket_id_by_graph_node_id):
        ticket_id = latest_ticket_id_by_graph_node_id[graph_node_id]
        created_spec = created_specs_by_ticket_id.get(ticket_id) or {}
        identity = identities_by_ticket_id[ticket_id]
        parent_lane_anchor = _resolve_parent_lane_anchor(
            ticket_id=ticket_id,
            child_identity=identity,
            created_specs_by_ticket_id=created_specs_by_ticket_id,
            identities_by_ticket_id=identities_by_ticket_id,
            latest_ticket_id_by_graph_node_id=latest_ticket_id_by_graph_node_id,
        )
        if parent_lane_anchor is not None:
            parent_issue_code = str(parent_lane_anchor.get("issue_code") or "").strip()
            if parent_issue_code:
                record_issue(
                    issue_code=parent_issue_code,
                    detail=str(parent_lane_anchor.get("detail") or ""),
                    ticket_id=ticket_id,
                    node_id=identity.runtime_node_id,
                    graph_node_id=identity.graph_node_id,
                    related_ticket_id=str(parent_lane_anchor.get("related_ticket_id") or "") or None,
                )
            else:
                parent_identity = parent_lane_anchor["parent_identity"]
                _append_edge(
                    edges,
                    seen_edges,
                    edge_type="PARENT_OF",
                    graph_version=graph_version,
                    workflow_id=workflow_id,
                    source_ticket_id=str(parent_lane_anchor["parent_ticket_id"]),
                    target_ticket_id=ticket_id,
                    source_graph_node_id=parent_identity.graph_node_id,
                    target_graph_node_id=identity.graph_node_id,
                    source_runtime_node_id=parent_identity.runtime_node_id,
                    target_runtime_node_id=identity.runtime_node_id,
                )

        for dependency_ticket_id in _resolve_dependency_gate_refs(created_spec):
            dependency_identity = identities_by_ticket_id.get(dependency_ticket_id)
            if dependency_identity is None:
                record_issue(
                    issue_code="graph.dependency.missing_ticket",
                    detail=(
                        f"Ticket {ticket_id} depends on missing ticket {dependency_ticket_id}. "
                        "The graph adapter blocks this node instead of silently treating it as ready."
                    ),
                    ticket_id=ticket_id,
                    node_id=identity.runtime_node_id,
                    graph_node_id=identity.graph_node_id,
                    related_ticket_id=dependency_ticket_id,
                )
                continue
            dependency_current_ticket_id = latest_ticket_id_by_graph_node_id.get(
                dependency_identity.graph_node_id
            )
            if not dependency_current_ticket_id:
                record_issue(
                    issue_code="graph.dependency.missing_current_lane_ticket",
                    detail=(
                        f"Ticket {ticket_id} depends on lane {dependency_identity.graph_node_id}, "
                        "but the current graph lane has no active ticket."
                    ),
                    ticket_id=ticket_id,
                    node_id=identity.runtime_node_id,
                    graph_node_id=identity.graph_node_id,
                    related_ticket_id=dependency_ticket_id,
                )
                continue
            _append_edge(
                edges,
                seen_edges,
                edge_type="DEPENDS_ON",
                graph_version=graph_version,
                workflow_id=workflow_id,
                source_ticket_id=dependency_current_ticket_id,
                target_ticket_id=ticket_id,
                source_graph_node_id=dependency_identity.graph_node_id,
                target_graph_node_id=identity.graph_node_id,
                source_runtime_node_id=dependency_identity.runtime_node_id,
                target_runtime_node_id=identity.runtime_node_id,
            )

        maker_ticket_id = str(
            (created_spec.get("maker_checker_context") or {}).get("maker_ticket_id") or ""
        ).strip()
        if resolve_graph_lane_kind(created_spec) == GRAPH_LANE_EXECUTION or not maker_ticket_id:
            continue
        maker_identity = identities_by_ticket_id.get(maker_ticket_id)
        if maker_identity is None:
            record_issue(
                issue_code="graph.review.missing_maker_ticket",
                detail=f"Checker ticket {ticket_id} points to missing maker ticket {maker_ticket_id}.",
                ticket_id=ticket_id,
                node_id=identity.runtime_node_id,
                graph_node_id=identity.graph_node_id,
                related_ticket_id=maker_ticket_id,
            )
            continue
        maker_current_ticket_id = latest_ticket_id_by_graph_node_id.get(
            maker_identity.graph_node_id
        )
        if not maker_current_ticket_id:
            record_issue(
                issue_code="graph.review.missing_current_execution_lane",
                detail=(
                    f"Checker ticket {ticket_id} points to maker lane {maker_identity.graph_node_id}, "
                    "but the current execution lane has no active ticket."
                ),
                ticket_id=ticket_id,
                node_id=identity.runtime_node_id,
                graph_node_id=identity.graph_node_id,
                related_ticket_id=maker_ticket_id,
            )
            continue
        _append_edge(
            edges,
            seen_edges,
            edge_type="REVIEWS",
            graph_version=graph_version,
            workflow_id=workflow_id,
            source_ticket_id=ticket_id,
            target_ticket_id=maker_current_ticket_id,
            source_graph_node_id=identity.graph_node_id,
            target_graph_node_id=maker_identity.graph_node_id,
            source_runtime_node_id=identity.runtime_node_id,
            target_runtime_node_id=maker_identity.runtime_node_id,
        )

    base_edge_keys = {
        (edge.edge_type, edge.source_graph_node_id, edge.target_graph_node_id)
        for edge in edges
        if edge.source_graph_node_id and edge.target_graph_node_id
    }
    all_graph_node_ids = {
        node.graph_node_id
        for node in nodes
        if str(node.graph_node_id or "").strip()
    }
    execution_graph_node_ids = {
        node.graph_node_id
        for node in nodes
        if str(node.graph_lane_kind or "") == GRAPH_LANE_EXECUTION
    }
    ticket_status_by_graph_node_id = {
        node.graph_node_id: str(node.ticket_status or "").strip() or None
        for node in nodes
    }
    node_status_by_graph_node_id = {
        node.graph_node_id: str(node.node_status or "").strip() or None
        for node in nodes
    }
    graph_patch_overlay = reduce_graph_patch_overlay(
        patch_records=load_graph_patch_event_records(
            repository,
            workflow_id,
            connection=connection,
        ),
        known_node_ids=all_graph_node_ids,
        known_patch_target_node_ids=execution_graph_node_ids,
        base_edge_keys=base_edge_keys,
        ticket_status_by_node_id=ticket_status_by_graph_node_id,
        node_status_by_node_id=node_status_by_graph_node_id,
    )
    node_status_overrides = dict(graph_patch_overlay.node_status_overrides)
    for node in nodes:
        override_status = node_status_overrides.get(node.graph_node_id)
        if override_status:
            node.node_status = override_status
    existing_graph_node_ids = {
        str(node.graph_node_id or "").strip()
        for node in nodes
        if str(node.graph_node_id or "").strip()
    }
    for placeholder_node_id, placeholder_node in sorted(graph_patch_overlay.placeholder_nodes.items()):
        if placeholder_node_id in existing_graph_node_ids:
            continue
        override_status = str(node_status_overrides.get(placeholder_node_id) or "").strip()
        if override_status in {NODE_STATUS_CANCELLED, NODE_STATUS_SUPERSEDED}:
            continue
        nodes.append(
            TicketGraphNode(
                graph_node_id=placeholder_node_id,
                workflow_id=workflow_id,
                graph_version=graph_version,
                ticket_id=None,
                node_id=placeholder_node_id,
                runtime_node_id=None,
                graph_lane_kind=GRAPH_LANE_EXECUTION,
                node_kind=str(placeholder_node.node_kind or "").strip(),
                deliverable_kind=str(placeholder_node.deliverable_kind or "").strip() or None,
                role_hint=str(placeholder_node.role_hint or "").strip() or None,
                ticket_status=None,
                node_status=override_status or "PLANNED",
                role_profile_ref=str(placeholder_node.role_hint or "").strip() or None,
                output_schema_ref=None,
                delivery_stage=None,
                parent_ticket_id=None,
                dependency_ticket_ids=[],
                blocking_reason_code=None,
                is_placeholder=True,
            )
        )

    current_node_by_graph_node_id = {node.graph_node_id: node for node in nodes}

    effective_edges: list[TicketGraphEdge] = []
    effective_seen_edges: set[tuple[str, str, str]] = set()
    for edge_type, source_graph_node_id, target_graph_node_id in sorted(graph_patch_overlay.effective_edge_keys):
        source_node = current_node_by_graph_node_id.get(source_graph_node_id)
        target_node = current_node_by_graph_node_id.get(target_graph_node_id)
        if edge_type == "REPLACES":
            source_identity = None
            target_identity = None
            for identity in identities_by_ticket_id.values():
                if identity.graph_node_id == source_graph_node_id:
                    source_identity = identity
                if identity.graph_node_id == target_graph_node_id:
                    target_identity = identity
            _append_edge(
                effective_edges,
                effective_seen_edges,
                edge_type=edge_type,
                graph_version=graph_version,
                workflow_id=workflow_id,
                source_ticket_id=(
                    latest_ticket_id_by_graph_node_id.get(source_graph_node_id)
                    or (source_node.ticket_id if source_node is not None else None)
                ),
                target_ticket_id=(
                    latest_ticket_id_by_graph_node_id.get(target_graph_node_id)
                    or (target_node.ticket_id if target_node is not None else None)
                ),
                source_graph_node_id=source_graph_node_id,
                target_graph_node_id=target_graph_node_id,
                source_runtime_node_id=(
                    str(source_node.runtime_node_id or source_node.node_id)
                    if source_node is not None
                    else (source_identity.runtime_node_id if source_identity is not None else source_graph_node_id)
                ),
                target_runtime_node_id=(
                    str(target_node.runtime_node_id or target_node.node_id)
                    if target_node is not None
                    else (target_identity.runtime_node_id if target_identity is not None else target_graph_node_id)
                ),
            )
            continue
        if source_node is None or target_node is None:
            record_issue(
                issue_code="graph.patch.edge.missing_current_lane",
                detail=(
                    f"Graph patch edge {edge_type}:{source_graph_node_id}->{target_graph_node_id} "
                    "cannot be materialized because one endpoint has no active graph lane."
                ),
                ticket_id=(
                    target_node.ticket_id
                    if source_node is None and target_node is not None
                    else source_node.ticket_id
                    if target_node is None and source_node is not None
                    else None
                ),
                node_id=(
                    str(target_node.runtime_node_id or target_node.node_id)
                    if source_node is None and target_node is not None
                    else str(source_node.runtime_node_id or source_node.node_id)
                    if target_node is None and source_node is not None
                    else None
                ),
                graph_node_id=(
                    source_graph_node_id
                    if source_node is None
                    else target_graph_node_id
                    if target_node is None
                    else None
                ),
            )
            continue
        if _is_removed_from_effective_graph(source_node) or _is_removed_from_effective_graph(target_node):
            continue
        _append_edge(
            effective_edges,
            effective_seen_edges,
            edge_type=edge_type,
            graph_version=graph_version,
            workflow_id=workflow_id,
            source_ticket_id=source_node.ticket_id,
            target_ticket_id=target_node.ticket_id,
            source_graph_node_id=source_graph_node_id,
            target_graph_node_id=target_graph_node_id,
            source_runtime_node_id=str(source_node.runtime_node_id or source_node.node_id),
            target_runtime_node_id=str(target_node.runtime_node_id or target_node.node_id),
        )
    edges = effective_edges

    ready_ticket_ids: list[str] = []
    ready_node_ids: list[str] = []
    ready_graph_node_ids: list[str] = []
    blocked_ticket_ids: list[str] = []
    blocked_node_ids: list[str] = []
    blocked_graph_node_ids: list[str] = []
    in_flight_ticket_ids: list[str] = []
    in_flight_node_ids: list[str] = []
    in_flight_graph_node_ids: list[str] = []

    for node in nodes:
        graph_node_id = str(node.graph_node_id or "").strip()
        runtime_node_id = str(node.runtime_node_id or "").strip()
        ticket_id = str(node.ticket_id or "").strip()
        if bool(getattr(node, "is_placeholder", False)):
            continue
        ticket_projection = ticket_projection_by_ticket_id.get(ticket_id)
        if ticket_projection is None:
            record_issue(
                issue_code="graph.node.latest_ticket_missing",
                detail=f"Graph node {graph_node_id} points to missing latest ticket {ticket_id}.",
                ticket_id=ticket_id,
                node_id=runtime_node_id,
                graph_node_id=graph_node_id,
            )
            continue
        ticket_status = str(ticket_projection.get("status") or "").strip()
        node_status = (
            node_status_overrides.get(graph_node_id)
            or str(node.node_status or "").strip()
        )
        if node_status in {NODE_STATUS_CANCELLED, NODE_STATUS_SUPERSEDED}:
            continue
        created_spec = created_specs_by_ticket_id.get(ticket_id) or {}
        blocking_reason_code = str(node.blocking_reason_code or "").strip()
        hook_gate_result = evaluate_ticket_required_hook_gate(
            repository,
            ticket=ticket_projection,
            created_spec=created_spec,
            connection=connection,
        )
        hook_gate_blocked = hook_gate_result.status == HookGateStatus.BLOCKED
        blocked_by_graph = (
            ticket_id in blocked_ticket_ids_from_issues
            or runtime_node_id in blocked_runtime_node_ids_from_issues
            or graph_node_id in blocked_graph_node_ids_from_issues
        )
        blocked_by_advisory_patch = graph_node_id in graph_patch_overlay.frozen_node_ids
        is_board_review_open = (
            ticket_status == "BLOCKED_FOR_BOARD_REVIEW"
            or node_status == NODE_STATUS_BLOCKED_FOR_BOARD_REVIEW
        )
        has_open_incident = runtime_node_id in open_incident_runtime_node_ids
        is_in_flight = ticket_status in {"LEASED", "EXECUTING"} or node_status == NODE_STATUS_EXECUTING
        if is_in_flight:
            in_flight_ticket_ids.append(ticket_id)
            in_flight_node_ids.append(runtime_node_id)
            in_flight_graph_node_ids.append(graph_node_id)

        if (
            ticket_status == "PENDING"
            and not blocked_by_graph
            and not blocked_by_advisory_patch
            and not hook_gate_blocked
            and not blocking_reason_code
            and not is_board_review_open
            and not has_open_incident
        ):
            ready_ticket_ids.append(ticket_id)
            ready_node_ids.append(runtime_node_id)
            ready_graph_node_ids.append(graph_node_id)
            continue

        if (
            blocked_by_graph
            or blocked_by_advisory_patch
            or hook_gate_blocked
            or blocking_reason_code
            or is_board_review_open
            or has_open_incident
        ):
            blocked_ticket_ids.append(ticket_id)
            blocked_node_ids.append(runtime_node_id)
            blocked_graph_node_ids.append(graph_node_id)
        if blocked_by_advisory_patch:
            _append_blocked_reason(
                blocked_reason_map,
                reason_code=BLOCKING_REASON_ADVISORY_PATCH_FROZEN,
                ticket_id=ticket_id,
                node_id=runtime_node_id,
            )
        if hook_gate_blocked:
            _append_blocked_reason(
                blocked_reason_map,
                reason_code=hook_gate_result.reason_code,
                ticket_id=ticket_id,
                node_id=runtime_node_id,
            )
        if has_open_incident:
            _append_blocked_reason(
                blocked_reason_map,
                reason_code="INCIDENT_OPEN",
                ticket_id=ticket_id,
                node_id=runtime_node_id,
            )
        if is_board_review_open:
            _append_blocked_reason(
                blocked_reason_map,
                reason_code="BOARD_REVIEW_OPEN",
                ticket_id=ticket_id,
                node_id=runtime_node_id,
            )
        if blocking_reason_code:
            _append_blocked_reason(
                blocked_reason_map,
                reason_code=f"EXPLICIT_BLOCKING_REASON:{blocking_reason_code}",
                ticket_id=ticket_id,
                node_id=runtime_node_id,
            )

    critical_path_graph_node_ids: set[str] = set()
    critical_path_runtime_node_ids: set[str] = set()
    reverse_path_adjacency: dict[str, set[str]] = {}
    for edge in edges:
        if edge.edge_type not in _GRAPH_PATH_EDGE_TYPES:
            continue
        reverse_path_adjacency.setdefault(edge.target_graph_node_id, set()).add(edge.source_graph_node_id)
    for current_graph_node_id in [*blocked_graph_node_ids, *in_flight_graph_node_ids]:
        graph_cursor_stack = [current_graph_node_id]
        visited_graph_node_ids: set[str] = set()
        while graph_cursor_stack:
            graph_cursor = graph_cursor_stack.pop()
            if graph_cursor in visited_graph_node_ids:
                continue
            visited_graph_node_ids.add(graph_cursor)
            critical_path_graph_node_ids.add(graph_cursor)
            graph_node = current_node_by_graph_node_id.get(graph_cursor)
            if graph_node is not None:
                critical_path_runtime_node_ids.add(
                    str(graph_node.runtime_node_id or graph_node.node_id)
                )
            graph_cursor_stack.extend(sorted(reverse_path_adjacency.get(graph_cursor, set())))

    blocked_reasons = [
        TicketGraphBlockedReasonSummary(
            reason_code=reason_code,
            ticket_ids=sorted(entry["ticket_ids"]),
            node_ids=sorted(entry["node_ids"]),
            count=max(len(entry["ticket_ids"]), len(entry["node_ids"])),
        )
        for reason_code, entry in sorted(blocked_reason_map.items())
    ]
    inactive_refs = {
        ref
        for node in nodes
        for ref in [str(node.graph_node_id or "").strip(), str(node.ticket_id or "").strip()]
        if ref and str(node.node_status or "").strip() in {NODE_STATUS_CANCELLED, NODE_STATUS_SUPERSEDED}
    }
    replacements_for_policy = [
        {
            "old_node_ref": str(edge.target_graph_node_id or "").strip(),
            "new_node_ref": str(edge.source_graph_node_id or "").strip(),
            "old_ticket_id": str(edge.target_ticket_id or "").strip(),
            "new_ticket_id": str(edge.source_ticket_id or "").strip(),
        }
        for edge in edges
        if str(edge.edge_type or "").strip() == "REPLACES"
    ]
    ticket_lineage_for_policy = []
    for edge in edges:
        if str(edge.edge_type or "").strip() not in {"REPLACES", "PARENT_OF", "REVIEWS"}:
            continue
        ticket_lineage_for_policy.append(
            {
                "lineage_type": str(edge.edge_type or "").strip(),
                "source_node_ref": str(edge.source_graph_node_id or "").strip(),
                "target_node_ref": str(edge.target_graph_node_id or "").strip(),
                "source_ticket_id": str(edge.source_ticket_id or "").strip(),
                "target_ticket_id": str(edge.target_ticket_id or "").strip(),
            }
        )
    from app.core.workflow_progression import ProgressionSnapshot, evaluate_progression_graph

    graph_policy_evaluation = evaluate_progression_graph(
        ProgressionSnapshot(
            workflow_id=workflow_id,
            graph_version=graph_version,
            node_refs=[str(node.graph_node_id or "").strip() for node in nodes],
            ticket_refs=[str(node.ticket_id or "").strip() for node in nodes if node.ticket_id],
            runtime_nodes=[
                {
                    "node_ref": str(row.get("graph_node_id") or "").strip(),
                    "node_id": str(row.get("node_id") or "").strip(),
                    "latest_ticket_id": str(row.get("latest_ticket_id") or "").strip(),
                    "status": str(row.get("status") or "").strip(),
                    "blocking_reason_code": str(row.get("blocking_reason_code") or "").strip(),
                }
                for row in runtime_node_projection_by_graph_node_id.values()
                if str(row.get("graph_node_id") or "").strip()
            ],
            graph_nodes=[
                {
                    "node_ref": str(node.graph_node_id or "").strip(),
                    "node_id": str(node.node_id or "").strip(),
                    "ticket_id": str(node.ticket_id or "").strip(),
                    "ticket_status": str(node.ticket_status or "").strip(),
                    "node_status": str(node.node_status or "").strip(),
                    "blocking_reason_code": str(node.blocking_reason_code or "").strip(),
                }
                for node in nodes
                if str(node.graph_node_id or "").strip()
            ],
            graph_edges=[
                {
                    "edge_type": str(edge.edge_type or "").strip(),
                    "source_node_ref": str(edge.source_graph_node_id or "").strip(),
                    "target_node_ref": str(edge.target_graph_node_id or "").strip(),
                    "source_ticket_id": str(edge.source_ticket_id or "").strip(),
                    "target_ticket_id": str(edge.target_ticket_id or "").strip(),
                }
                for edge in edges
            ],
            ticket_lineage=ticket_lineage_for_policy,
            replacements=replacements_for_policy,
            cancelled_refs=[
                ref
                for ref in inactive_refs
                if any(
                    ref in {str(node.graph_node_id or "").strip(), str(node.ticket_id or "").strip()}
                    and str(node.node_status or "").strip() == NODE_STATUS_CANCELLED
                    for node in nodes
                )
            ],
            superseded_refs=[
                ref
                for ref in inactive_refs
                if any(
                    ref in {str(node.graph_node_id or "").strip(), str(node.ticket_id or "").strip()}
                    and str(node.node_status or "").strip() == NODE_STATUS_SUPERSEDED
                    for node in nodes
                )
            ],
            graph_reduction_issues=[
                {
                    "issue_code": issue.issue_code,
                    "detail": issue.detail,
                    "ticket_id": issue.ticket_id,
                    "node_id": issue.node_id,
                    "node_ref": issue.node_id,
                    "graph_node_id": next(
                        (
                            str(current_pointer_issue.get("graph_node_id") or "").strip()
                            for current_pointer_issue in current_pointer_issues
                            if str(current_pointer_issue.get("node_id") or "").strip()
                            == str(issue.node_id or "").strip()
                            and str(current_pointer_issue.get("issue_code") or "").strip()
                            == str(issue.issue_code or "").strip()
                        ),
                        None,
                    ),
                    "related_ticket_id": issue.related_ticket_id,
                }
                for issue in reduction_issues
            ],
            blocked_ticket_ids=sorted(set(blocked_ticket_ids)),
            blocked_node_refs=sorted(set(blocked_node_ids)),
            in_flight_ticket_ids=sorted(set(in_flight_ticket_ids)),
            in_flight_node_refs=sorted(set(in_flight_node_ids)),
            blocked_reasons=[
                {
                    "reason_code": item.reason_code,
                    "ticket_ids": list(item.ticket_ids),
                    "node_refs": list(item.node_ids),
                }
                for item in blocked_reasons
            ],
        )
    )
    blocked_graph_node_ids_from_reduction_issues = sorted(
        {
            str(issue.get("graph_node_id") or "").strip()
            for issue in current_pointer_issues
            if str(issue.get("graph_node_id") or "").strip()
        }
    )
    blocked_runtime_node_ids_from_reduction_issues = sorted(
        {
            str(issue.get("node_id") or "").strip()
            for issue in current_pointer_issues
            if str(issue.get("node_id") or "").strip()
        }
    )

    return TicketGraphSnapshot(
        workflow_id=workflow_id,
        graph_version=graph_version,
        nodes=sorted(nodes, key=lambda item: (item.graph_node_id, item.ticket_id)),
        edges=sorted(
            edges,
            key=lambda item: (
                item.edge_type,
                item.source_graph_node_id,
                item.target_graph_node_id,
                item.source_ticket_id,
                item.target_ticket_id,
            ),
        ),
        index_summary=TicketGraphIndexSummary(
            ready_ticket_ids=list(graph_policy_evaluation.ready_ticket_ids),
            ready_node_ids=sorted(
                {
                    str(current_node_by_graph_node_id[node_ref].runtime_node_id or current_node_by_graph_node_id[node_ref].node_id)
                    for node_ref in graph_policy_evaluation.ready_node_refs
                    if node_ref in current_node_by_graph_node_id
                }
            ),
            ready_graph_node_ids=list(graph_policy_evaluation.ready_node_refs),
            blocked_ticket_ids=list(graph_policy_evaluation.blocked_ticket_ids),
            blocked_node_ids=sorted(
                {
                    str(current_node_by_graph_node_id[node_ref].runtime_node_id or current_node_by_graph_node_id[node_ref].node_id)
                    for node_ref in graph_policy_evaluation.blocked_node_refs
                    if node_ref in current_node_by_graph_node_id
                }
                | set(blocked_runtime_node_ids_from_reduction_issues)
            ),
            blocked_graph_node_ids=sorted(
                {
                    *graph_policy_evaluation.blocked_node_refs,
                    *blocked_graph_node_ids_from_reduction_issues,
                }
            ),
            in_flight_ticket_ids=list(graph_policy_evaluation.in_flight_ticket_ids),
            in_flight_node_ids=sorted(
                {
                    str(current_node_by_graph_node_id[node_ref].runtime_node_id or current_node_by_graph_node_id[node_ref].node_id)
                    for node_ref in graph_policy_evaluation.in_flight_node_refs
                    if node_ref in current_node_by_graph_node_id
                }
            ),
            in_flight_graph_node_ids=list(graph_policy_evaluation.in_flight_node_refs),
            critical_path_node_ids=sorted(critical_path_runtime_node_ids),
            critical_path_graph_node_ids=sorted(critical_path_graph_node_ids),
            blocked_reasons=blocked_reasons,
            reduction_issue_count=len(reduction_issues),
        ),
        reduction_issues=reduction_issues,
    )
