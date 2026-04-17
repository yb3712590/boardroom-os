from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.core.graph_identity import apply_legacy_graph_contract_compat, resolve_ticket_graph_identity
from app.core.output_schemas import CONSENSUS_DOCUMENT_SCHEMA_REF, MAKER_CHECKER_VERDICT_SCHEMA_REF
from app.core.ticket_graph import build_ticket_graph_snapshot
from app.db.repository import ControlPlaneRepository


@dataclass(frozen=True)
class WorkflowTicketSnapshot:
    node_id: str
    ticket_id: str | None
    parent_ticket_id: str | None
    phase: str
    delivery_stage: str | None
    node_status: str
    ticket_status: str | None
    role_profile_ref: str | None
    output_schema_ref: str | None
    lease_owner: str | None
    expected_artifact_scope: list[str]
    blocking_reason_code: str | None
    sort_updated_at: datetime | None


@dataclass(frozen=True)
class WorkflowRuntimeRelation:
    graph_node_id: str
    node_id: str
    ticket_id: str
    ticket_status: str | None
    role_profile_ref: str | None
    output_schema_ref: str | None
    delivery_stage: str | None
    lease_owner: str | None
    sort_updated_at: datetime | None


@dataclass(frozen=True)
class WorkflowRuntimeOrgRelations:
    current: WorkflowRuntimeRelation
    upstream_provider: WorkflowRuntimeRelation | None
    downstream_candidates: list[WorkflowRuntimeRelation]
    collaborator_candidates: list[WorkflowRuntimeRelation]


def resolve_phase_label(created_spec: dict[str, Any] | None) -> str:
    if created_spec is None:
        return "Build"
    delivery_stage = str(created_spec.get("delivery_stage") or "").strip().upper()
    maker_checker_context = created_spec.get("maker_checker_context") or {}
    maker_ticket_spec = maker_checker_context.get("maker_ticket_spec") or {}
    maker_delivery_stage = str(maker_ticket_spec.get("delivery_stage") or "").strip().upper()
    original_review_request = maker_checker_context.get("original_review_request") or {}
    review_type = str(original_review_request.get("review_type") or "")
    output_schema_ref = str(created_spec.get("output_schema_ref") or "")
    if output_schema_ref == CONSENSUS_DOCUMENT_SCHEMA_REF or review_type == "MEETING_ESCALATION":
        return "Plan"
    if delivery_stage == "BUILD":
        return "Build"
    if delivery_stage == "CHECK":
        return "Check"
    if delivery_stage in {"REVIEW", "CLOSEOUT"} or maker_delivery_stage in {
        "REVIEW",
        "CLOSEOUT",
    } or review_type == "VISUAL_MILESTONE":
        return "Review"
    return "Build"


def resolve_display_ticket_spec(created_spec: dict[str, Any] | None) -> dict[str, Any] | None:
    if created_spec is None:
        return None
    maker_checker_context = created_spec.get("maker_checker_context") or {}
    maker_ticket_spec = maker_checker_context.get("maker_ticket_spec")
    if (
        str(created_spec.get("output_schema_ref") or "") == MAKER_CHECKER_VERDICT_SCHEMA_REF
        and isinstance(maker_ticket_spec, dict)
        and maker_ticket_spec
    ):
        return maker_ticket_spec
    return created_spec


def resolve_logical_ticket_id(
    created_spec: dict[str, Any] | None,
    display_spec: dict[str, Any] | None,
    latest_ticket_id: str,
) -> str:
    if display_spec is not None:
        logical_ticket_id = str(display_spec.get("ticket_id") or "").strip()
        if logical_ticket_id:
            return logical_ticket_id
    maker_checker_context = created_spec.get("maker_checker_context") if created_spec is not None else None
    if isinstance(maker_checker_context, dict):
        maker_ticket_id = str(maker_checker_context.get("maker_ticket_id") or "").strip()
        if maker_ticket_id:
            return maker_ticket_id
    return latest_ticket_id


def list_workflow_ticket_snapshots(
    repository: ControlPlaneRepository,
    workflow_id: str,
    *,
    connection,
    graph_snapshot=None,
) -> list[WorkflowTicketSnapshot]:
    normalized_workflow_id = str(workflow_id or "").strip()
    if not normalized_workflow_id:
        raise ValueError("Workflow ticket snapshots require workflow_id.")
    graph_snapshot = graph_snapshot or build_ticket_graph_snapshot(
        repository,
        normalized_workflow_id,
        connection=connection,
    )
    ticket_projection_by_ticket_id = _ticket_projection_by_workflow(
        repository,
        normalized_workflow_id,
        connection=connection,
    )

    graph_nodes = sorted(
        (
            node
            for node in graph_snapshot.nodes
            if node.ticket_id is not None and not bool(node.is_placeholder)
        ),
        key=lambda node: (
            (
                ticket_projection_by_ticket_id.get(str(node.ticket_id), {}).get("updated_at").timestamp()
                if isinstance(
                    ticket_projection_by_ticket_id.get(str(node.ticket_id), {}).get("updated_at"),
                    datetime,
                )
                else float("-inf")
            ),
            str(node.graph_node_id),
        ),
    )

    snapshots: list[WorkflowTicketSnapshot] = []
    for graph_node in graph_nodes:
        latest_ticket_id = str(graph_node.ticket_id or "").strip()
        if not latest_ticket_id:
            continue
        current_ticket = ticket_projection_by_ticket_id.get(latest_ticket_id)
        if current_ticket is None:
            raise ValueError(
                "Workflow ticket snapshot found graph node without ticket_projection: "
                f"{normalized_workflow_id}:{graph_node.graph_node_id}:{latest_ticket_id}"
            )
        created_spec = (
            repository.get_latest_ticket_created_payload(connection, latest_ticket_id)
            if latest_ticket_id
            else None
        )
        if created_spec is None:
            raise ValueError(
                "Workflow ticket snapshot found graph node without ticket-create payload: "
                f"{normalized_workflow_id}:{graph_node.graph_node_id}:{latest_ticket_id}"
            )
        display_spec = resolve_display_ticket_spec(created_spec)
        maker_checker_context = created_spec.get("maker_checker_context") if created_spec is not None else None
        if (
            created_spec is not None
            and str(created_spec.get("output_schema_ref") or "") == MAKER_CHECKER_VERDICT_SCHEMA_REF
            and isinstance(maker_checker_context, dict)
        ):
            maker_ticket_id = str(maker_checker_context.get("maker_ticket_id") or "").strip()
            if maker_ticket_id:
                maker_created_spec = repository.get_latest_ticket_created_payload(connection, maker_ticket_id)
                if maker_created_spec is not None:
                    display_spec = maker_created_spec
        logical_ticket_id = resolve_logical_ticket_id(created_spec, display_spec, latest_ticket_id)
        snapshots.append(
            WorkflowTicketSnapshot(
                node_id=str(graph_node.node_id),
                ticket_id=logical_ticket_id or None,
                parent_ticket_id=(
                    str(graph_node.parent_ticket_id or "").strip()
                    or (
                        str(display_spec.get("parent_ticket_id") or "").strip()
                        if display_spec is not None
                        else ""
                    )
                    or None
                ),
                phase=resolve_phase_label(created_spec),
                delivery_stage=(
                    str(graph_node.delivery_stage or "").strip().upper()
                    or (
                        str(display_spec.get("delivery_stage") or "").strip().upper()
                        if display_spec is not None
                        else ""
                    )
                    or None
                ),
                node_status=(
                    str(graph_node.node_status or "").strip()
                    or str(current_ticket.get("status") or "").strip()
                    or "PENDING"
                ),
                ticket_status=(
                    str(current_ticket.get("status") or "").strip() or None
                ),
                role_profile_ref=(
                    str(graph_node.role_profile_ref or "").strip()
                    or (
                        str(display_spec.get("role_profile_ref") or "").strip()
                        if display_spec is not None
                        else ""
                    )
                    or None
                ),
                output_schema_ref=(
                    str(graph_node.output_schema_ref or "").strip()
                    or (
                        str(display_spec.get("output_schema_ref") or "").strip()
                        if display_spec is not None
                        else ""
                    )
                    or None
                ),
                lease_owner=(
                    str(current_ticket.get("lease_owner") or "").strip() or None
                ),
                expected_artifact_scope=(
                    list(display_spec.get("allowed_write_set") or [])
                    if display_spec is not None
                    else []
                ),
                blocking_reason_code=(
                    str(graph_node.blocking_reason_code or "").strip()
                    or str(current_ticket.get("blocking_reason_code") or "").strip()
                    or None
                ),
                sort_updated_at=(
                    current_ticket.get("updated_at") if current_ticket is not None else None
                ),
            )
        )
    return snapshots


def _ticket_projection_by_workflow(
    repository: ControlPlaneRepository,
    workflow_id: str,
    *,
    connection,
) -> dict[str, dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT * FROM ticket_projection
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


def _build_runtime_relation(
    repository: ControlPlaneRepository,
    *,
    workflow_id: str,
    graph_node_id: str,
    ticket_id: str,
    graph_node_by_graph_node_id: dict[str, Any],
    ticket_projection_by_ticket_id: dict[str, dict[str, Any]],
    connection,
) -> WorkflowRuntimeRelation:
    normalized_graph_node_id = str(graph_node_id or "").strip()
    normalized_ticket_id = str(ticket_id or "").strip()
    if not normalized_graph_node_id or not normalized_ticket_id:
        raise ValueError("Runtime org relation requires both graph_node_id and ticket_id.")
    graph_node = graph_node_by_graph_node_id.get(normalized_graph_node_id)
    if graph_node is None:
        raise ValueError(
            f"Workflow {workflow_id} is missing graph node {normalized_graph_node_id} for runtime org context."
        )
    ticket_projection = ticket_projection_by_ticket_id.get(normalized_ticket_id)
    if ticket_projection is None:
        raise ValueError(
            f"Workflow {workflow_id} is missing ticket_projection {normalized_ticket_id} for runtime org context."
        )
    return WorkflowRuntimeRelation(
        graph_node_id=normalized_graph_node_id,
        node_id=str(graph_node.node_id),
        ticket_id=normalized_ticket_id,
        ticket_status=(str(ticket_projection.get("status") or "").strip() or None),
        role_profile_ref=(str(graph_node.role_profile_ref or "").strip() or None),
        output_schema_ref=(str(graph_node.output_schema_ref or "").strip() or None),
        delivery_stage=(str(graph_node.delivery_stage or "").strip().upper() or None),
        lease_owner=(str(ticket_projection.get("lease_owner") or "").strip() or None),
        sort_updated_at=ticket_projection.get("updated_at"),
    )


def resolve_runtime_org_context_relations(
    repository: ControlPlaneRepository,
    workflow_id: str,
    ticket_id: str,
    *,
    connection,
) -> WorkflowRuntimeOrgRelations:
    normalized_workflow_id = str(workflow_id or "").strip()
    normalized_ticket_id = str(ticket_id or "").strip()
    if not normalized_workflow_id or not normalized_ticket_id:
        raise ValueError("Runtime org context requires workflow_id and ticket_id.")

    current_ticket = repository.get_current_ticket_projection(normalized_ticket_id, connection=connection)
    if current_ticket is None:
        raise ValueError(
            f"Workflow {normalized_workflow_id} is missing current ticket {normalized_ticket_id} for runtime org context."
        )
    created_spec = apply_legacy_graph_contract_compat(
        repository.get_latest_ticket_created_payload(connection, normalized_ticket_id) or {}
    )
    if not created_spec:
        raise ValueError(
            f"Workflow {normalized_workflow_id} is missing ticket-create spec for {normalized_ticket_id}."
        )
    graph_identity = resolve_ticket_graph_identity(
        ticket_id=normalized_ticket_id,
        created_spec=created_spec,
        runtime_node_id=str(current_ticket.get("node_id") or ""),
    )
    graph_snapshot = build_ticket_graph_snapshot(
        repository,
        normalized_workflow_id,
        connection=connection,
    )
    graph_node_by_graph_node_id = {
        str(node.graph_node_id).strip(): node
        for node in graph_snapshot.nodes
        if str(node.graph_node_id or "").strip()
    }
    ticket_projection_by_ticket_id = _ticket_projection_by_workflow(
        repository,
        normalized_workflow_id,
        connection=connection,
    )
    current_relation = _build_runtime_relation(
        repository,
        workflow_id=normalized_workflow_id,
        graph_node_id=graph_identity.graph_node_id,
        ticket_id=normalized_ticket_id,
        graph_node_by_graph_node_id=graph_node_by_graph_node_id,
        ticket_projection_by_ticket_id=ticket_projection_by_ticket_id,
        connection=connection,
    )

    incoming_parent_edges = [
        edge
        for edge in graph_snapshot.edges
        if edge.edge_type == "PARENT_OF" and edge.target_graph_node_id == graph_identity.graph_node_id
    ]
    if len(incoming_parent_edges) > 1:
        raise ValueError(
            "Runtime org context expected at most one parent edge for "
            f"{graph_identity.graph_node_id}, got {len(incoming_parent_edges)}."
        )

    upstream_provider = None
    parent_graph_node_id = None
    if incoming_parent_edges:
        parent_edge = incoming_parent_edges[0]
        parent_graph_node_id = str(parent_edge.source_graph_node_id or "").strip() or None
        parent_ticket_id = str(parent_edge.source_ticket_id or "").strip()
        if parent_graph_node_id is None or not parent_ticket_id:
            raise ValueError(
                f"Runtime org context found incomplete parent edge for {graph_identity.graph_node_id}."
            )
        upstream_provider = _build_runtime_relation(
            repository,
            workflow_id=normalized_workflow_id,
            graph_node_id=parent_graph_node_id,
            ticket_id=parent_ticket_id,
            graph_node_by_graph_node_id=graph_node_by_graph_node_id,
            ticket_projection_by_ticket_id=ticket_projection_by_ticket_id,
            connection=connection,
        )

    downstream_candidates = [
        _build_runtime_relation(
            repository,
            workflow_id=normalized_workflow_id,
            graph_node_id=str(edge.target_graph_node_id or ""),
            ticket_id=str(edge.target_ticket_id or ""),
            graph_node_by_graph_node_id=graph_node_by_graph_node_id,
            ticket_projection_by_ticket_id=ticket_projection_by_ticket_id,
            connection=connection,
        )
        for edge in graph_snapshot.edges
        if edge.edge_type == "PARENT_OF"
        and edge.source_graph_node_id == graph_identity.graph_node_id
        and str(edge.target_ticket_id or "").strip()
    ]

    collaborator_candidates: list[WorkflowRuntimeRelation] = []
    if parent_graph_node_id is not None:
        collaborator_candidates = [
            _build_runtime_relation(
                repository,
                workflow_id=normalized_workflow_id,
                graph_node_id=str(edge.target_graph_node_id or ""),
                ticket_id=str(edge.target_ticket_id or ""),
                graph_node_by_graph_node_id=graph_node_by_graph_node_id,
                ticket_projection_by_ticket_id=ticket_projection_by_ticket_id,
                connection=connection,
            )
            for edge in graph_snapshot.edges
            if edge.edge_type == "PARENT_OF"
            and edge.source_graph_node_id == parent_graph_node_id
            and edge.target_graph_node_id != graph_identity.graph_node_id
            and str(edge.target_ticket_id or "").strip()
        ]

    return WorkflowRuntimeOrgRelations(
        current=current_relation,
        upstream_provider=upstream_provider,
        downstream_candidates=downstream_candidates,
        collaborator_candidates=collaborator_candidates,
    )
