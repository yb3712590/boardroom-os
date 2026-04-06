from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.core.output_schemas import CONSENSUS_DOCUMENT_SCHEMA_REF, MAKER_CHECKER_VERDICT_SCHEMA_REF
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
) -> list[WorkflowTicketSnapshot]:
    node_rows = connection.execute(
        """
        SELECT * FROM node_projection
        WHERE workflow_id = ?
        ORDER BY updated_at ASC, node_id ASC
        """,
        (workflow_id,),
    ).fetchall()

    snapshots: list[WorkflowTicketSnapshot] = []
    for row in node_rows:
        node = repository._convert_node_projection_row(row)
        node_id = str(node["node_id"])
        latest_ticket_id = str(node.get("latest_ticket_id") or "").strip()
        current_ticket = (
            repository.get_current_ticket_projection(latest_ticket_id, connection=connection)
            if latest_ticket_id
            else None
        )
        created_spec = (
            repository.get_latest_ticket_created_payload(connection, latest_ticket_id)
            if latest_ticket_id
            else None
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
                node_id=node_id,
                ticket_id=logical_ticket_id or None,
                parent_ticket_id=(
                    str(display_spec.get("parent_ticket_id") or "").strip() or None
                    if display_spec is not None
                    else None
                ),
                phase=resolve_phase_label(created_spec),
                delivery_stage=(
                    str(display_spec.get("delivery_stage") or "").strip().upper() or None
                    if display_spec is not None
                    else None
                ),
                node_status=str(node["status"]),
                ticket_status=(
                    str(current_ticket.get("status") or "").strip() or None
                    if current_ticket is not None
                    else None
                ),
                role_profile_ref=(
                    str(display_spec.get("role_profile_ref") or "").strip() or None
                    if display_spec is not None
                    else None
                ),
                output_schema_ref=(
                    str(display_spec.get("output_schema_ref") or "").strip() or None
                    if display_spec is not None
                    else None
                ),
                lease_owner=(
                    str(current_ticket.get("lease_owner") or "").strip() or None
                    if current_ticket is not None
                    else None
                ),
                expected_artifact_scope=(
                    list(display_spec.get("allowed_write_set") or [])
                    if display_spec is not None
                    else []
                ),
                blocking_reason_code=(
                    str(current_ticket.get("blocking_reason_code") or "").strip() or None
                    if current_ticket is not None
                    else None
                ),
                sort_updated_at=(
                    current_ticket.get("updated_at") if current_ticket is not None else node.get("updated_at")
                ),
            )
        )
    return snapshots
