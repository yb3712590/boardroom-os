from __future__ import annotations

from datetime import datetime
from typing import Any

from app.contracts.ceo import (
    FailureFingerprintDigest,
    GraphHealthReportDigest,
    ProjectionSnapshot,
    ProjectMapSliceDigest,
    RecentAssetDigest,
    ReplanFocus,
    RuntimeLivenessReportDigest,
)
from app.core.board_advisory import (
    BOARD_ADVISORY_STATUS_OPEN,
    build_board_advisory_snapshot_entry,
    build_latest_advisory_decision,
)
from app.core.constants import NODE_STATUS_COMPLETED
from app.core.ceo_meeting_policy import build_ceo_meeting_candidates
from app.core.graph_health import build_graph_health_report
from app.core.runtime_liveness import build_runtime_liveness_report
from app.core.governance_profiles import require_governance_profile
from app.core.output_schemas import (
    CONSENSUS_DOCUMENT_SCHEMA_REF,
    GOVERNANCE_DOCUMENT_SCHEMA_REFS,
    MAKER_CHECKER_VERDICT_SCHEMA_REF,
)
from app.core.persona_profiles import normalize_persona_profiles
from app.core.process_assets import (
    build_failure_fingerprint_process_asset_ref,
    build_project_map_slice_process_asset_ref,
    resolve_process_asset,
)
from app.core.ticket_graph import build_ticket_graph_snapshot
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
_MEMORY_BUDGET_RATIOS = {
    "m0_constitution": 10,
    "m1_control_snapshot": 40,
    "m2_replan_focus": 20,
    "m3_process_assets": 20,
    "reserve": 10,
}
_DEFAULT_READ_ORDER = [
    "projection_snapshot",
    "ticket_graph",
    "open_incidents",
    "open_board_items",
    "board_advisory_sessions",
    "project_map_slices",
    "failure_fingerprints",
    "graph_health_report",
    "runtime_liveness_report",
    "recent_asset_digests",
]


def _serialize_timestamp(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def _enum_value(value: Any) -> Any:
    return value.value if hasattr(value, "value") else value


def _build_idle_maintenance_signals(
    tickets: list[dict[str, Any]],
    *,
    ready_ticket_ids: list[str] | None = None,
    reduction_issue_count: int = 0,
) -> list[str]:
    signals: list[str] = []
    if not tickets or all(ticket["status"] in _TERMINAL_TICKET_STATUSES for ticket in tickets):
        signals.append("NO_TICKET_STARTED")

    if list(ready_ticket_ids or []):
        signals.append("READY_TICKET")
    if int(reduction_issue_count) > 0:
        signals.append("INVALID_DEPENDENCY_OR_DISPATCH")

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
                "source_graph_node_id": str(
                    meeting.get("source_graph_node_id") or meeting["source_node_id"]
                ),
                "source_node_id": str(meeting["source_node_id"]),
                "topic": str(meeting["topic"]),
                "consensus_summary": str(meeting.get("consensus_summary") or ""),
                "review_status": str(meeting.get("review_status") or ""),
                "closed_at": _serialize_timestamp(meeting.get("closed_at")),
            }
        )
    return candidates


def _build_recent_asset_digests(reuse_candidates: dict[str, Any]) -> list[dict[str, Any]]:
    digests: list[RecentAssetDigest] = []
    for item in list(reuse_candidates.get("recent_completed_tickets") or []):
        source_ref = (
            str(((item.get("artifact_refs") or [None])[0]) or "").strip()
            or str(item.get("ticket_id") or "").strip()
        )
        summary = str(item.get("summary") or "").strip()
        asset_kind = str(item.get("output_schema_ref") or "ticket").strip()
        if source_ref and summary and asset_kind:
            digests.append(
                RecentAssetDigest(
                    source_ref=source_ref,
                    asset_kind=asset_kind,
                    summary=summary,
                )
            )
    for item in list(reuse_candidates.get("recent_closed_meetings") or []):
        source_ref = str(item.get("meeting_id") or "").strip()
        summary = str(item.get("consensus_summary") or "").strip()
        if source_ref and summary:
            digests.append(
                RecentAssetDigest(
                    source_ref=source_ref,
                    asset_kind="meeting_decision_record",
                    summary=summary,
                )
            )
    return [item.model_dump(mode="json") for item in digests[:5]]


def _build_project_map_slices(
    repository: ControlPlaneRepository,
    *,
    workflow_id: str,
    connection,
) -> list[dict[str, Any]]:
    resolved_asset = resolve_process_asset(
        repository,
        build_project_map_slice_process_asset_ref(workflow_id),
        connection=connection,
    )
    payload = dict(resolved_asset.json_content or {})
    return [
        ProjectMapSliceDigest(
            process_asset_ref=str(resolved_asset.process_asset_ref),
            workflow_id=str(payload.get("workflow_id") or workflow_id),
            graph_version=str(payload.get("graph_version") or ""),
            module_paths=list(payload.get("module_paths") or []),
            document_surfaces=list(payload.get("document_surfaces") or []),
            decision_asset_refs=list(payload.get("decision_asset_refs") or []),
            failure_fingerprint_refs=list(payload.get("failure_fingerprint_refs") or []),
            source_process_asset_refs=list(payload.get("source_process_asset_refs") or []),
        ).model_dump(mode="json")
    ]


def _build_failure_fingerprints(
    repository: ControlPlaneRepository,
    *,
    workflow_id: str,
    connection,
) -> list[dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT incident_id
        FROM incident_projection
        WHERE workflow_id = ?
        ORDER BY opened_at DESC, incident_id DESC
        LIMIT 3
        """,
        (workflow_id,),
    ).fetchall()
    digests: list[dict[str, Any]] = []
    for row in rows:
        incident_id = str(row["incident_id"]).strip()
        if not incident_id:
            continue
        resolved_asset = resolve_process_asset(
            repository,
            build_failure_fingerprint_process_asset_ref(incident_id),
            connection=connection,
        )
        payload = dict(resolved_asset.json_content or {})
        digests.append(
            FailureFingerprintDigest(
                process_asset_ref=str(resolved_asset.process_asset_ref),
                incident_id=str(payload.get("incident_id") or incident_id),
                workflow_id=str(payload.get("workflow_id") or workflow_id),
                incident_type=str(payload.get("incident_type") or ""),
                severity=payload.get("severity"),
                fingerprint=str(payload.get("fingerprint") or ""),
                node_id=payload.get("node_id"),
                ticket_id=payload.get("ticket_id"),
                related_process_asset_refs=list(payload.get("related_process_asset_refs") or []),
            ).model_dump(mode="json")
        )
    return digests


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
        governance_profile = require_governance_profile(
            repository,
            workflow_id=workflow_id,
            connection=connection,
        )
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
        ticket_graph_snapshot = build_ticket_graph_snapshot(
            repository,
            workflow_id,
            connection=connection,
        )
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
        advisory_sessions = repository.list_board_advisory_sessions(
            workflow_id,
            statuses=[
                BOARD_ADVISORY_STATUS_OPEN,
                "DRAFTING",
                "PENDING_ANALYSIS",
                "PENDING_BOARD_CONFIRMATION",
                "ANALYSIS_REJECTED",
                "APPLIED",
            ],
            connection=connection,
        )
        project_map_slices = _build_project_map_slices(
            repository,
            workflow_id=workflow_id,
            connection=connection,
        )
        failure_fingerprints = _build_failure_fingerprints(
            repository,
            workflow_id=workflow_id,
            connection=connection,
        )
        graph_health_report = GraphHealthReportDigest.model_validate(
            build_graph_health_report(
                repository,
                workflow_id,
                connection=connection,
            )
        ).model_dump(mode="json")
        runtime_liveness_report = RuntimeLivenessReportDigest.model_validate(
            build_runtime_liveness_report(
                repository,
                workflow_id,
                connection=connection,
            )
        ).model_dump(mode="json")
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
            ticket_graph_snapshot=ticket_graph_snapshot,
            connection=connection,
        )
    ready_ticket_id_set = set(ticket_graph_snapshot.index_summary.ready_ticket_ids)
    ready_tickets = [
        ticket
        for ticket in tickets
        if str(ticket.get("ticket_id") or "") in ready_ticket_id_set
    ]
    latest_advisory_session = advisory_sessions[0] if advisory_sessions else None
    projection_snapshot = ProjectionSnapshot(
        workflow_status=str(workflow["status"]),
        graph_version=ticket_graph_snapshot.graph_version,
        governance_profile_ref=governance_profile.profile_id,
        approval_mode=governance_profile.approval_mode,
        audit_mode=governance_profile.audit_mode,
        ready_nodes=list(ticket_graph_snapshot.index_summary.ready_node_ids),
        blocked_nodes=list(ticket_graph_snapshot.index_summary.blocked_node_ids),
        open_incidents=[str(item["incident_id"]) for item in open_incidents],
        open_board_items=[str(item["approval_id"]) for item in open_approvals],
        pending_expert_gates=(
            [str(item["approval_id"]) for item in open_approvals]
            if governance_profile.approval_mode == "EXPERT_GATED"
            else []
        ),
        recent_asset_digests=_build_recent_asset_digests(reuse_candidates),
        reuse_candidates=reuse_candidates,
        board_advisory_sessions=[
            build_board_advisory_snapshot_entry(item)
            for item in advisory_sessions
        ],
        project_map_slices=project_map_slices,
        graph_health_report=graph_health_report,
        runtime_liveness_report=runtime_liveness_report,
        memory_budget_ratios=dict(_MEMORY_BUDGET_RATIOS),
        default_read_order=list(_DEFAULT_READ_ORDER),
    )
    replan_focus = ReplanFocus(
        task_sensemaking=controller_view["task_sensemaking"],
        capability_plan=controller_view["capability_plan"],
        controller_state=controller_view["controller_state"],
        meeting_candidates=controller_view["meeting_candidates"],
        latest_advisory_decision=build_latest_advisory_decision(
            latest_advisory_session,
            current_profile=governance_profile,
        ),
        latest_patch_proposal_ref=(
            str(latest_advisory_session.get("latest_patch_proposal_ref") or "")
            if latest_advisory_session is not None
            else None
        )
        or None,
        patched_graph_version=(
            str(latest_advisory_session.get("patched_graph_version") or "")
            if latest_advisory_session is not None
            else None
        )
        or None,
        focus_node_ids=list((latest_advisory_session or {}).get("focus_node_ids") or []),
        failure_fingerprints=failure_fingerprints,
    )

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
            "signal_types": _build_idle_maintenance_signals(
                tickets,
                ready_ticket_ids=list(ticket_graph_snapshot.index_summary.ready_ticket_ids),
                reduction_issue_count=ticket_graph_snapshot.index_summary.reduction_issue_count,
            ),
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
        "projection_snapshot": projection_snapshot.model_dump(mode="json"),
        "replan_focus": replan_focus.model_dump(mode="json"),
        "reuse_candidates": reuse_candidates,
        "meeting_candidates": controller_view["meeting_candidates"],
        "task_sensemaking": controller_view["task_sensemaking"],
        "capability_plan": controller_view["capability_plan"],
        "controller_state": controller_view["controller_state"],
        "ticket_graph": ticket_graph_snapshot.model_dump(mode="json"),
    }
