from __future__ import annotations

from datetime import datetime
from typing import Any

from app.core.constants import NODE_STATUS_COMPLETED
from app.core.ceo_meeting_policy import build_ceo_meeting_candidates
from app.core.output_schemas import (
    CONSENSUS_DOCUMENT_SCHEMA_REF,
    GOVERNANCE_DOCUMENT_SCHEMA_REFS,
    MAKER_CHECKER_VERDICT_SCHEMA_REF,
)
from app.core.persona_profiles import normalize_persona_profiles
from app.core.workflow_controller import build_workflow_controller_view
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
_TERMINAL_TICKET_STATUSES = {
    "COMPLETED",
    "CANCELLED",
}
_RECENT_COMPLETED_TICKET_LIMIT = 5
_RECENT_CLOSED_MEETING_LIMIT = 3
_APPROVED_INTERNAL_REVIEW_STATUSES = {"APPROVED", "APPROVED_WITH_NOTES"}


def _serialize_timestamp(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def _enum_value(value: Any) -> Any:
    return value.value if hasattr(value, "value") else value


def _build_idle_maintenance_signals(tickets: list[dict[str, Any]]) -> list[str]:
    signals: list[str] = []
    if not tickets or all(ticket["status"] in _TERMINAL_TICKET_STATUSES for ticket in tickets):
        signals.append("NO_TICKET_STARTED")

    if any(ticket["status"] == "PENDING" for ticket in tickets):
        signals.append("READY_TICKET")

    latest_ticket_id_by_node: dict[str, str] = {}
    latest_ticket_sort_key_by_node: dict[str, tuple[float, str]] = {}
    for ticket in tickets:
        node_id = str(ticket.get("node_id") or "").strip()
        ticket_id = str(ticket.get("ticket_id") or "").strip()
        updated_at = ticket.get("updated_at")
        if not node_id or not ticket_id or not isinstance(updated_at, datetime):
            continue
        sort_key = (updated_at.timestamp(), ticket_id)
        if sort_key >= latest_ticket_sort_key_by_node.get(node_id, (float("-inf"), "")):
            latest_ticket_sort_key_by_node[node_id] = sort_key
            latest_ticket_id_by_node[node_id] = ticket_id

    has_invalid_dependency = False
    has_failed_ticket = False
    for ticket in tickets:
        if ticket["status"] not in {"FAILED", "TIMED_OUT"}:
            continue
        node_id = str(ticket.get("node_id") or "").strip()
        ticket_id = str(ticket.get("ticket_id") or "").strip()
        if node_id and latest_ticket_id_by_node.get(node_id) not in {None, ticket_id}:
            continue
        failure_kind = str(ticket.get("last_failure_kind") or "").strip().upper()
        if "DEPENDENCY" in failure_kind or failure_kind == "DISPATCH_INTENT_INVALID":
            has_invalid_dependency = True
        else:
            has_failed_ticket = True

    if has_invalid_dependency:
        signals.append("INVALID_DEPENDENCY_OR_DISPATCH")
    if has_failed_ticket:
        signals.append("FAILED_TICKET")

    return signals


def _latest_snapshot_timestamp(
    tickets: list[dict[str, Any]],
    nodes: list[dict[str, Any]],
    approvals: list[dict[str, Any]],
    incidents: list[dict[str, Any]],
) -> str | None:
    candidates: list[datetime] = []
    for value in (
        *[ticket.get("updated_at") for ticket in tickets],
        *[node.get("updated_at") for node in nodes],
        *[approval.get("created_at") for approval in approvals],
        *[incident.get("opened_at") for incident in incidents],
    ):
        if isinstance(value, datetime):
            candidates.append(value)
    if not candidates:
        return None
    return max(candidates).isoformat()


def _build_recent_completed_ticket_reuse_candidates(
    repository: ControlPlaneRepository,
    *,
    tickets: list[dict[str, Any]],
    nodes: list[dict[str, Any]],
    connection,
) -> list[dict[str, Any]]:
    completed_tickets = [ticket for ticket in tickets if ticket["status"] == "COMPLETED"]
    nodes_by_id = {
        str(node.get("node_id") or "").strip(): node
        for node in nodes
        if str(node.get("node_id") or "").strip()
    }
    latest_ticket_id_by_node: dict[str, str] = {}
    latest_ticket_sort_key_by_node: dict[str, tuple[float, str]] = {}
    for ticket in tickets:
        node_id = str(ticket.get("node_id") or "").strip()
        ticket_id = str(ticket.get("ticket_id") or "").strip()
        updated_at = ticket.get("updated_at")
        if not node_id or not ticket_id or not isinstance(updated_at, datetime):
            continue
        sort_key = (updated_at.timestamp(), ticket_id)
        if sort_key >= latest_ticket_sort_key_by_node.get(node_id, (float("-inf"), "")):
            latest_ticket_sort_key_by_node[node_id] = sort_key
            latest_ticket_id_by_node[node_id] = ticket_id
    candidates: list[dict[str, Any]] = []
    seen_logical_ticket_ids: set[str] = set()
    for ticket in completed_tickets:
        if len(candidates) >= _RECENT_COMPLETED_TICKET_LIMIT:
            break
        ticket_id = str(ticket["ticket_id"])
        created_spec = repository.get_latest_ticket_created_payload(connection, ticket_id) or {}
        terminal_event = repository.get_latest_ticket_terminal_event(connection, ticket_id)
        output_schema_ref = str(created_spec.get("output_schema_ref") or "").strip()
        logical_ticket_id = ticket_id
        logical_created_spec = created_spec
        logical_terminal_event = terminal_event
        if output_schema_ref == CONSENSUS_DOCUMENT_SCHEMA_REF:
            node_id = str(ticket.get("node_id") or "").strip()
            node_projection = nodes_by_id.get(node_id) or {}
            if str(node_projection.get("status") or "").strip() != NODE_STATUS_COMPLETED:
                continue
        if output_schema_ref in GOVERNANCE_DOCUMENT_SCHEMA_REFS:
            continue
        if output_schema_ref == MAKER_CHECKER_VERDICT_SCHEMA_REF:
            maker_checker_context = created_spec.get("maker_checker_context") or {}
            maker_ticket_id = str(maker_checker_context.get("maker_ticket_id") or "").strip()
            maker_created_spec = maker_checker_context.get("maker_ticket_spec")
            if not isinstance(maker_created_spec, dict) or not maker_created_spec:
                maker_created_spec = (
                    repository.get_latest_ticket_created_payload(connection, maker_ticket_id)
                    if maker_ticket_id
                    else {}
                ) or {}
            maker_output_schema_ref = str(maker_created_spec.get("output_schema_ref") or "").strip()
            if maker_output_schema_ref in GOVERNANCE_DOCUMENT_SCHEMA_REFS:
                if latest_ticket_id_by_node.get(str(ticket.get("node_id") or "").strip()) != ticket_id:
                    continue
                completion_payload = terminal_event.get("payload") if terminal_event is not None else {}
                review_status = str(
                    (completion_payload or {}).get("maker_checker_summary", {}).get("review_status")
                    or (completion_payload or {}).get("review_status")
                    or ""
                ).strip()
                if review_status not in _APPROVED_INTERNAL_REVIEW_STATUSES:
                    continue
                logical_ticket_id = maker_ticket_id or ticket_id
                logical_created_spec = maker_created_spec
                logical_terminal_event = repository.get_latest_ticket_terminal_event(connection, logical_ticket_id)
        if not logical_ticket_id or logical_ticket_id in seen_logical_ticket_ids:
            continue
        artifact_refs = [
            str(artifact.get("artifact_ref") or "")
            for artifact in repository.list_ticket_artifacts(logical_ticket_id, connection=connection)
            if str(artifact.get("artifact_ref") or "").strip()
        ]
        completion_payload = logical_terminal_event.get("payload") if logical_terminal_event is not None else {}
        summary = str(logical_created_spec.get("summary") or "").strip() or str(
            (completion_payload or {}).get("completion_summary") or ""
        ).strip()
        completed_at = (
            terminal_event.get("occurred_at")
            if terminal_event is not None and str(terminal_event.get("event_type") or "") == "TICKET_COMPLETED"
            else ticket.get("updated_at")
        )
        candidates.append(
            {
                "ticket_id": logical_ticket_id,
                "node_id": str(ticket["node_id"]),
                "output_schema_ref": str(logical_created_spec.get("output_schema_ref") or ""),
                "summary": summary,
                "artifact_refs": artifact_refs,
                "completed_at": _serialize_timestamp(completed_at),
            }
        )
        seen_logical_ticket_ids.add(logical_ticket_id)
    return candidates


def _build_recent_closed_meeting_reuse_candidates(
    repository: ControlPlaneRepository,
    *,
    workflow_id: str,
    connection,
) -> list[dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT * FROM meeting_projection
        WHERE workflow_id = ? AND closed_at IS NOT NULL
        ORDER BY closed_at DESC, meeting_id DESC
        LIMIT ?
        """,
        (workflow_id, _RECENT_CLOSED_MEETING_LIMIT),
    ).fetchall()
    candidates: list[dict[str, Any]] = []
    for row in rows:
        meeting = repository._convert_meeting_projection_row(row)
        candidates.append(
            {
                "meeting_id": str(meeting["meeting_id"]),
                "source_ticket_id": str(meeting["source_ticket_id"]),
                "source_node_id": str(meeting["source_node_id"]),
                "topic": str(meeting["topic"]),
                "consensus_summary": str(meeting.get("consensus_summary") or ""),
                "review_status": str(meeting.get("review_status") or ""),
                "closed_at": _serialize_timestamp(meeting.get("closed_at")),
            }
        )
    return candidates


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

    employees = repository.list_employee_projections()
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
        reuse_candidates = {
            "recent_completed_tickets": _build_recent_completed_ticket_reuse_candidates(
                repository,
                tickets=tickets,
                nodes=nodes,
                connection=connection,
            ),
            "recent_closed_meetings": _build_recent_closed_meeting_reuse_candidates(
                repository,
                workflow_id=workflow_id,
                connection=connection,
            ),
        }
        controller_view = build_workflow_controller_view(
            repository,
            workflow=workflow,
            tickets=tickets,
            nodes=nodes,
            approvals=open_approvals,
            incidents=open_incidents,
            employees=employees,
            trigger_ref=trigger_ref,
            meeting_candidates=build_ceo_meeting_candidates(
                repository,
                workflow_id=workflow_id,
                trigger_type=trigger_type,
                trigger_ref=trigger_ref,
                approvals=open_approvals,
                incidents=open_incidents,
            ),
            connection=connection,
        )
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
            "workflow_profile": workflow.get("workflow_profile"),
            "status": workflow["status"],
            "current_stage": workflow["current_stage"],
            "budget_total": workflow["budget_total"],
            "budget_used": workflow["budget_used"],
            "board_gate_state": workflow["board_gate_state"],
            "deadline_at": _serialize_timestamp(workflow.get("deadline_at")),
            "updated_at": _serialize_timestamp(workflow.get("updated_at")),
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
        "idle_maintenance": {
            "signal_types": _build_idle_maintenance_signals(tickets),
            "latest_state_change_at": _latest_snapshot_timestamp(
                tickets,
                nodes,
                open_approvals,
                open_incidents,
            ),
        },
        "employees": [
            {
                "employee_id": employee["employee_id"],
                "role_type": employee["role_type"],
                "state": employee["state"],
                "board_approved": bool(employee.get("board_approved")),
                "provider_id": employee.get("provider_id"),
                "role_profile_refs": list(employee.get("role_profile_refs") or []),
                **{
                    key: value
                    for key, value in normalize_persona_profiles(
                        str(employee.get("role_type") or ""),
                        skill_profile=employee.get("skill_profile_json"),
                        personality_profile=employee.get("personality_profile_json"),
                        aesthetic_profile=employee.get("aesthetic_profile_json"),
                    ).items()
                    if key in {"skill_profile", "personality_profile", "aesthetic_profile", "profile_summary"}
                },
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
        "reuse_candidates": reuse_candidates,
        "meeting_candidates": controller_view["meeting_candidates"],
        "task_sensemaking": controller_view["task_sensemaking"],
        "capability_plan": controller_view["capability_plan"],
        "controller_state": controller_view["controller_state"],
    }
