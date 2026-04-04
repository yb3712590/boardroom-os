from __future__ import annotations

from datetime import datetime
from typing import Any

from app.db.repository import ControlPlaneRepository


_ACTIVE_TICKET_STATUSES = [
    "PENDING",
    "LEASED",
    "EXECUTING",
    "BLOCKED_FOR_BOARD_REVIEW",
    "REWORK_REQUIRED",
    "CANCEL_REQUESTED",
]
_WORKING_TICKET_STATUSES = {
    "LEASED",
    "EXECUTING",
}


def _serialize_timestamp(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def _enum_value(value: Any) -> Any:
    return value.value if hasattr(value, "value") else value


def build_ceo_shadow_snapshot(
    repository: ControlPlaneRepository,
    *,
    workflow_id: str,
    trigger_type: str,
    trigger_ref: str | None,
) -> dict[str, Any]:
    repository.initialize()
    workflow = repository.get_workflow_projection(workflow_id)
    if workflow is None:
        raise ValueError(f"Workflow {workflow_id} does not exist.")

    open_approvals = [
        approval
        for approval in repository.list_open_approvals()
        if approval["workflow_id"] == workflow_id
    ]
    open_incidents = [
        incident
        for incident in repository.list_open_incidents()
        if incident["workflow_id"] == workflow_id
    ]

    with repository.connection() as connection:
        ticket_rows = connection.execute(
            """
            SELECT * FROM ticket_projection
            WHERE workflow_id = ?
            ORDER BY updated_at DESC, ticket_id DESC
            """,
            (workflow_id,),
        ).fetchall()
        node_rows = connection.execute(
            """
            SELECT * FROM node_projection
            WHERE workflow_id = ?
            ORDER BY updated_at DESC, node_id DESC
            """,
            (workflow_id,),
        ).fetchall()

    tickets = [repository._convert_ticket_projection_row(row) for row in ticket_rows]
    nodes = [repository._convert_node_projection_row(row) for row in node_rows]
    employees = repository.list_employee_projections()
    ready_tickets = [ticket for ticket in tickets if ticket["status"] == "PENDING"]

    return {
        "trigger": {
            "trigger_type": trigger_type,
            "trigger_ref": trigger_ref,
        },
        "workflow": {
            "workflow_id": workflow["workflow_id"],
            "title": workflow["title"],
            "north_star_goal": workflow["north_star_goal"],
            "status": workflow["status"],
            "current_stage": workflow["current_stage"],
            "budget_total": workflow["budget_total"],
            "budget_used": workflow["budget_used"],
            "board_gate_state": workflow["board_gate_state"],
            "deadline_at": _serialize_timestamp(workflow.get("deadline_at")),
        },
        "ticket_summary": {
            "total": len(tickets),
            "ready_count": len(ready_tickets),
            "active_count": sum(1 for ticket in tickets if ticket["status"] in _ACTIVE_TICKET_STATUSES),
            "working_count": sum(1 for ticket in tickets if ticket["status"] in _WORKING_TICKET_STATUSES),
            "completed_count": sum(1 for ticket in tickets if ticket["status"] == "COMPLETED"),
            "failed_count": sum(1 for ticket in tickets if ticket["status"] in {"FAILED", "TIMED_OUT"}),
        },
        "tickets": [
            {
                "ticket_id": ticket["ticket_id"],
                "node_id": ticket["node_id"],
                "status": ticket["status"],
                "priority": ticket.get("priority"),
                "lease_owner": ticket.get("lease_owner"),
                "retry_count": ticket.get("retry_count"),
                "retry_budget": ticket.get("retry_budget"),
                "last_failure_kind": ticket.get("last_failure_kind"),
                "blocking_reason_code": ticket.get("blocking_reason_code"),
                "updated_at": _serialize_timestamp(ticket.get("updated_at")),
            }
            for ticket in tickets[:25]
        ],
        "nodes": [
            {
                "node_id": node["node_id"],
                "latest_ticket_id": node["latest_ticket_id"],
                "status": node["status"],
                "blocking_reason_code": node.get("blocking_reason_code"),
                "updated_at": _serialize_timestamp(node.get("updated_at")),
            }
            for node in nodes[:25]
        ],
        "approvals": [
            {
                "approval_id": approval["approval_id"],
                "approval_type": approval["approval_type"],
                "review_pack_id": approval["review_pack_id"],
                "priority": (approval.get("payload") or {}).get("priority"),
                "created_at": _serialize_timestamp(approval.get("created_at")),
            }
            for approval in open_approvals
        ],
        "incidents": [
            {
                "incident_id": incident["incident_id"],
                "incident_type": incident["incident_type"],
                "status": incident["status"],
                "severity": incident.get("severity"),
                "fingerprint": incident["fingerprint"],
                "ticket_id": incident.get("ticket_id"),
                "provider_id": incident.get("provider_id"),
                "opened_at": _serialize_timestamp(incident.get("opened_at")),
            }
            for incident in open_incidents
        ],
        "employees": [
            {
                "employee_id": employee["employee_id"],
                "role_type": employee["role_type"],
                "state": employee["state"],
                "board_approved": bool(employee.get("board_approved")),
                "provider_id": employee.get("provider_id"),
                "role_profile_refs": list(employee.get("role_profile_refs") or []),
            }
            for employee in employees
        ],
        "recent_events": [
            {
                "event_id": preview["event_id"],
                "occurred_at": _serialize_timestamp(preview["occurred_at"]),
                "category": preview["category"],
                "severity": _enum_value(preview["severity"]),
                "message": preview["message"],
                "related_ref": preview.get("related_ref"),
            }
            for preview in repository.get_recent_event_previews()
        ],
    }
