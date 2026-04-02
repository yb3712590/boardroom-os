from __future__ import annotations

from typing import Any

from app.contracts.events import EventSeverity
from app.contracts.projections import (
    ActiveWorkflowProjection,
    ArtifactCleanupCandidateProjection,
    ArtifactCleanupCandidatesProjectionData,
    ArtifactCleanupCandidatesProjectionEnvelope,
    ArtifactCleanupCandidatesProjectionFilters,
    ArtifactMaintenanceProjection,
    DashboardCompletionSummaryProjection,
    DashboardProjectionData,
    DashboardProjectionEnvelope,
    DashboardRuntimeStatusProjection,
    DependencyInspectorCurrentStopProjection,
    DependencyInspectorNodeProjection,
    DependencyInspectorProjectionData,
    DependencyInspectorProjectionEnvelope,
    DependencyInspectorSummaryProjection,
    DependencyInspectorWorkflowProjection,
    EventStreamPreviewItem,
    IncidentDetailProjectionData,
    IncidentDetailProjectionEnvelope,
    IncidentProjectionItem,
    InboxCountsProjection,
    InboxItemProjection,
    NodeCountsProjection,
    WorkerAdminAuditProjectionData,
    WorkerAdminAuditProjectionEnvelope,
    WorkerAdminAuditProjectionFilters,
    WorkerAdminAuditProjectionItem,
    WorkerAdminAuditProjectionSummary,
    WorkerAdminAuthRejectionProjectionData,
    WorkerAdminAuthRejectionProjectionEnvelope,
    WorkerAdminAuthRejectionProjectionFilters,
    WorkerAdminAuthRejectionProjectionItem,
    WorkerAdminAuthRejectionProjectionSummary,
    InboxProjectionData,
    InboxProjectionEnvelope,
    OpsStripProjection,
    PhaseSummaryProjection,
    PipelineSummaryProjection,
    RuntimeProviderProjectionData,
    RuntimeProviderProjectionEnvelope,
    ReviewRoomDraftDefaults,
    ReviewRoomDeveloperInspectorProjectionData,
    ReviewRoomDeveloperInspectorProjectionEnvelope,
    ReviewRoomDeveloperInspectorCompileSummary,
    ReviewRoomProjectionData,
    ReviewRoomProjectionEnvelope,
    RouteTarget,
    TicketArtifactProjection,
    TicketArtifactsProjectionData,
    TicketArtifactsProjectionEnvelope,
    WorkerAuthRejectionAdminProjection,
    WorkerBindingAdminProjection,
    WorkerDeliveryGrantAdminProjection,
    WorkerRuntimeProjectionData,
    WorkerRuntimeProjectionEnvelope,
    WorkerRuntimeProjectionFilters,
    WorkerRuntimeProjectionSummary,
    WorkerSessionAdminProjection,
    WorkforceProjectionData,
    WorkforceProjectionEnvelope,
    WorkforceRoleLaneProjection,
    WorkforceSummaryProjection,
    WorkforceWorkerProjection,
    WorkspaceSummary,
)
from app.contracts.runtime import RenderedExecutionPayloadSummary
from app.contracts.commands import IncidentFollowupAction
from app.config import get_settings
from app.core.artifacts import build_artifact_metadata, build_artifact_retention_defaults
from app.core.constants import (
    APPROVAL_STATUS_OPEN,
    CIRCUIT_BREAKER_STATE_OPEN,
    INCIDENT_TYPE_PROVIDER_EXECUTION_PAUSED,
    INCIDENT_TYPE_MAKER_CHECKER_REWORK_ESCALATION,
    INCIDENT_TYPE_REPEATED_FAILURE_ESCALATION,
    INCIDENT_TYPE_RUNTIME_TIMEOUT_ESCALATION,
    INCIDENT_TYPE_STAFFING_CONTAINMENT,
    NODE_STATUS_BLOCKED_FOR_BOARD_REVIEW,
    NODE_STATUS_CANCEL_REQUESTED,
    NODE_STATUS_COMPLETED,
    NODE_STATUS_EXECUTING,
    NODE_STATUS_PENDING,
    NODE_STATUS_REWORK_REQUIRED,
    SCHEMA_VERSION,
    TICKET_STATUS_BLOCKED_FOR_BOARD_REVIEW,
    TICKET_STATUS_COMPLETED,
)
from app.core.developer_inspector import DeveloperInspectorStore
from app.core.output_schemas import CONSENSUS_DOCUMENT_SCHEMA_REF, MAKER_CHECKER_VERDICT_SCHEMA_REF
from app.core.runtime_provider_config import (
    RuntimeProviderConfigStore,
    count_configured_workers,
    mask_api_key,
    resolve_runtime_provider_config,
    runtime_provider_effective_mode,
)
from app.core.time import now_local
from app.db.repository import ControlPlaneRepository


def _is_worker_session_active(session: dict[str, object], *, at) -> bool:
    expires_at = session.get("expires_at")
    return bool(session.get("revoked_at") is None and expires_at is not None and expires_at > at)


def _is_worker_delivery_grant_active(grant: dict[str, object], *, at) -> bool:
    expires_at = grant.get("expires_at")
    return bool(grant.get("revoked_at") is None and expires_at is not None and expires_at > at)


def _build_workforce_summary(repository: ControlPlaneRepository) -> WorkforceSummaryProjection:
    employees = repository.list_employee_projections(board_approved_only=True)
    busy_tickets = repository.list_ticket_projections_by_statuses_readonly(
        ["LEASED", "EXECUTING", "CANCEL_REQUESTED"]
    )
    rework_tickets = repository.list_ticket_projections_by_statuses_readonly(
        ["PENDING", "LEASED", "EXECUTING", "CANCEL_REQUESTED"]
    )
    now = now_local()

    busy_workers: set[str] = set()
    contained_workers: set[str] = set()
    workers_in_rework_loop: set[str] = set()
    for ticket in busy_tickets:
        owner = ticket.get("lease_owner")
        if owner is None:
            continue
        if ticket["status"] == "CANCEL_REQUESTED":
            contained_workers.add(owner)
            continue
        if ticket["status"] == "EXECUTING":
            busy_workers.add(owner)
            continue
        lease_expiry = ticket.get("lease_expires_at")
        if lease_expiry is not None and lease_expiry > now:
            busy_workers.add(owner)

    with repository.connection() as connection:
        for ticket in rework_tickets:
            created_spec = repository.get_latest_ticket_created_payload(
                connection,
                str(ticket["ticket_id"]),
            )
            if not isinstance(created_spec, dict):
                continue
            if str(created_spec.get("ticket_kind") or "") != "MAKER_REWORK_FIX":
                continue
            delivery_stage = str(created_spec.get("delivery_stage") or "").strip().upper()
            maker_checker_context = created_spec.get("maker_checker_context") or {}
            maker_ticket_spec = maker_checker_context.get("maker_ticket_spec") or {}
            maker_delivery_stage = str(maker_ticket_spec.get("delivery_stage") or "").strip().upper()
            if delivery_stage not in {"BUILD", "CHECK"} and maker_delivery_stage not in {"BUILD", "CHECK"}:
                continue
            maker_employee_id = str(maker_checker_context.get("maker_completed_by") or "").strip()
            if maker_employee_id:
                workers_in_rework_loop.add(maker_employee_id)

    active_workers = 0
    idle_workers = 0
    active_checkers = 0
    for employee in employees:
        role_type = employee.get("role_type")
        state = str(employee.get("state") or "UNKNOWN")
        if employee["employee_id"] in contained_workers:
            continue
        if state != "ACTIVE":
            continue
        is_busy = employee["employee_id"] in busy_workers
        if role_type == "checker":
            if is_busy:
                active_checkers += 1
            continue
        if is_busy:
            active_workers += 1
        else:
            idle_workers += 1

    return WorkforceSummaryProjection(
        active_workers=active_workers,
        idle_workers=idle_workers,
        overloaded_workers=0,
        active_checkers=active_checkers,
        workers_in_rework_loop=len(workers_in_rework_loop),
        workers_in_staffing_containment=len(contained_workers),
    )


def _build_runtime_provider_projection_data(
    repository: ControlPlaneRepository,
    runtime_provider_store: RuntimeProviderConfigStore,
) -> RuntimeProviderProjectionData:
    config = resolve_runtime_provider_config(runtime_provider_store)
    effective_mode, effective_reason = runtime_provider_effective_mode(config, repository)
    return RuntimeProviderProjectionData(
        mode=config.mode,
        effective_mode=effective_mode,
        provider_id=config.provider_id,
        base_url=config.base_url,
        model=config.model,
        timeout_sec=config.timeout_sec,
        reasoning_effort=config.reasoning_effort,
        api_key_configured=bool(config.api_key),
        api_key_masked=mask_api_key(config.api_key),
        configured_worker_count=count_configured_workers(repository, provider_id=config.provider_id),
        effective_reason=effective_reason,
    )


def _build_dashboard_completion_summary(
    repository: ControlPlaneRepository,
    workflow_id: str,
) -> DashboardCompletionSummaryProjection | None:
    with repository.connection() as connection:
        node_rows = connection.execute(
            "SELECT status FROM node_projection WHERE workflow_id = ?",
            (workflow_id,),
        ).fetchall()
        if not node_rows:
            return None
        if any(str(row["status"]) != NODE_STATUS_COMPLETED for row in node_rows):
            return None

        active_ticket_count = int(
            connection.execute(
                """
                SELECT COUNT(*) AS total
                FROM ticket_projection
                WHERE workflow_id = ? AND status IN (?, ?, ?, ?, ?, ?)
                """,
                (
                    workflow_id,
                    "PENDING",
                    "LEASED",
                    "EXECUTING",
                    "BLOCKED_FOR_BOARD_REVIEW",
                    "REWORK_REQUIRED",
                    "CANCEL_REQUESTED",
                ),
            ).fetchone()["total"]
        )
        if active_ticket_count > 0:
            return None

        open_approval_count = int(
            connection.execute(
                "SELECT COUNT(*) AS total FROM approval_projection WHERE workflow_id = ? AND status = ?",
                (workflow_id, APPROVAL_STATUS_OPEN),
            ).fetchone()["total"]
        )
        if open_approval_count > 0:
            return None

        open_incident_count = int(
            connection.execute(
                "SELECT COUNT(*) AS total FROM incident_projection WHERE workflow_id = ? AND status = ?",
                (workflow_id, "OPEN"),
            ).fetchone()["total"]
        )
        if open_incident_count > 0:
            return None

        row = connection.execute(
            """
            SELECT * FROM approval_projection
            WHERE workflow_id = ? AND status = ?
            ORDER BY resolved_at DESC, updated_at DESC, approval_id DESC
            LIMIT 1
            """,
            (workflow_id, "APPROVED"),
        ).fetchone()
    if row is None:
        return None

    approval = repository._convert_approval_row(row)
    payload = approval.get("payload") or {}
    review_pack = payload.get("review_pack") or {}
    resolution = payload.get("resolution") or {}
    selected_option_id = resolution.get("selected_option_id")
    selected_option = next(
        (
            option
            for option in review_pack.get("options") or []
            if option.get("option_id") == selected_option_id
        ),
        None,
    )
    recommendation = review_pack.get("recommendation") or {}
    subject = review_pack.get("subject") or {}
    resolved_at = approval.get("resolved_at")
    if resolved_at is None:
        return None

    return DashboardCompletionSummaryProjection(
        workflow_id=workflow_id,
        final_review_pack_id=str(approval["review_pack_id"]),
        approved_at=resolved_at,
        title=str(subject.get("title") or review_pack.get("title") or approval["review_pack_id"]),
        summary=str(recommendation.get("summary") or resolution.get("board_comment") or ""),
        selected_option_id=selected_option_id,
        board_comment=resolution.get("board_comment"),
        artifact_refs=list((selected_option or {}).get("artifact_refs") or []),
    )


def _empty_phase_counts() -> dict[str, int]:
    return {
        "pending": 0,
        "executing": 0,
        "under_review": 0,
        "blocked_for_board": 0,
        "fused": 0,
        "completed": 0,
    }


def _derive_phase_status(counts: dict[str, int]) -> str:
    if counts["fused"] > 0:
        return "FUSED"
    if counts["blocked_for_board"] > 0:
        return "BLOCKED_FOR_BOARD"
    if counts["executing"] > 0:
        return "EXECUTING"
    if counts["under_review"] > 0:
        return "UNDER_REVIEW"
    if counts["pending"] > 0:
        return "PENDING"
    if counts["completed"] > 0:
        return "COMPLETED"
    return "PENDING"


def _resolve_phase_label(created_spec: dict[str, Any] | None) -> str:
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
    if delivery_stage == "REVIEW" or maker_delivery_stage == "REVIEW" or review_type == "VISUAL_MILESTONE":
        return "Review"
    return "Build"


def _resolve_display_ticket_spec(created_spec: dict[str, Any] | None) -> dict[str, Any] | None:
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


def _resolve_logical_ticket_id(
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


def _build_pipeline_summary(
    repository: ControlPlaneRepository,
    *,
    workflow_id: str | None,
    pending_approvals: int,
) -> PipelineSummaryProjection:
    phase_specs = [
        ("phase_intake", "Intake"),
        ("phase_plan", "Plan"),
        ("phase_build", "Build"),
        ("phase_check", "Check"),
        ("phase_review", "Review"),
    ]
    phase_counts = {phase_id: _empty_phase_counts() for phase_id, _ in phase_specs}
    critical_path_node_ids: list[str] = []
    blocked_node_ids: list[str] = []

    if workflow_id is None:
        phases = [
            PhaseSummaryProjection(
                phase_id=phase_id,
                label=label,
                status="PENDING",
                node_counts=NodeCountsProjection(**phase_counts[phase_id]),
            )
            for phase_id, label in phase_specs
        ]
        return PipelineSummaryProjection(
            phases=phases,
            critical_path_node_ids=critical_path_node_ids,
            blocked_node_ids=blocked_node_ids,
        )

    with repository.connection() as connection:
        node_rows = connection.execute(
            """
            SELECT node_id, status, latest_ticket_id
            FROM node_projection
            WHERE workflow_id = ?
            ORDER BY updated_at ASC, node_id ASC
            """,
            (workflow_id,),
        ).fetchall()
        incident_rows = connection.execute(
            """
            SELECT node_id
            FROM incident_projection
            WHERE workflow_id = ? AND status = ? AND circuit_breaker_state = ?
            ORDER BY opened_at ASC, incident_id ASC
            """,
            (workflow_id, "OPEN", CIRCUIT_BREAKER_STATE_OPEN),
        ).fetchall()

    open_breaker_nodes = {str(row["node_id"]) for row in incident_rows if row["node_id"] is not None}
    if not node_rows:
        phase_counts["phase_intake"]["executing"] = 1
    else:
        phase_counts["phase_intake"]["completed"] = 1

    seen_node_ids: set[str] = set()
    with repository.connection() as connection:
        for row in node_rows:
            node_id = str(row["node_id"])
            node_status = str(row["status"])
            latest_ticket_id = str(row["latest_ticket_id"] or "")
            created_spec = (
                repository.get_latest_ticket_created_payload(connection, latest_ticket_id)
                if latest_ticket_id
                else None
            )
            phase_id = f"phase_{_resolve_phase_label(created_spec).lower()}"
            seen_node_ids.add(node_id)
            if node_status in {
                NODE_STATUS_EXECUTING,
                NODE_STATUS_BLOCKED_FOR_BOARD_REVIEW,
                NODE_STATUS_REWORK_REQUIRED,
            }:
                critical_path_node_ids.append(node_id)
            if node_status == NODE_STATUS_BLOCKED_FOR_BOARD_REVIEW:
                blocked_node_ids.append(node_id)

            if node_status == NODE_STATUS_PENDING:
                phase_counts[phase_id]["pending"] += 1
                continue
            if node_status == NODE_STATUS_EXECUTING:
                if node_id in open_breaker_nodes:
                    phase_counts[phase_id]["fused"] += 1
                else:
                    phase_counts[phase_id]["executing"] += 1
                continue
            if node_status == NODE_STATUS_BLOCKED_FOR_BOARD_REVIEW:
                phase_counts[phase_id]["blocked_for_board"] += 1
                continue
            if node_status == NODE_STATUS_REWORK_REQUIRED:
                if node_id in open_breaker_nodes:
                    phase_counts[phase_id]["fused"] += 1
                else:
                    phase_counts[phase_id]["under_review"] += 1
                continue
            if node_status == NODE_STATUS_COMPLETED:
                phase_counts[phase_id]["completed"] += 1
                continue
            if node_status == NODE_STATUS_CANCEL_REQUESTED:
                phase_counts[phase_id]["fused"] += 1

    for node_id in sorted(open_breaker_nodes - seen_node_ids):
        critical_path_node_ids.append(node_id)
        phase_counts["phase_build"]["fused"] += 1

    blocked_for_board_total = sum(item["blocked_for_board"] for item in phase_counts.values())
    if pending_approvals > blocked_for_board_total:
        phase_counts["phase_review"]["blocked_for_board"] += pending_approvals - blocked_for_board_total

    phases = [
        PhaseSummaryProjection(
            phase_id=phase_id,
            label=label,
            status=_derive_phase_status(phase_counts[phase_id]),
            node_counts=NodeCountsProjection(**phase_counts[phase_id]),
        )
        for phase_id, label in phase_specs
    ]
    return PipelineSummaryProjection(
        phases=phases,
        critical_path_node_ids=sorted(set(critical_path_node_ids)),
        blocked_node_ids=sorted(set(blocked_node_ids)),
    )


def build_dependency_inspector_projection(
    repository: ControlPlaneRepository,
    workflow_id: str,
) -> DependencyInspectorProjectionEnvelope | None:
    repository.initialize()
    workflow = repository.get_workflow_projection(workflow_id)
    if workflow is None:
        return None

    generated_at = now_local()
    cursor, projection_version = repository.get_cursor_and_version()
    approvals = [item for item in repository.list_open_approvals() if item["workflow_id"] == workflow_id]

    with repository.connection() as connection:
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
            SELECT * FROM incident_projection
            WHERE workflow_id = ? AND status = ?
            ORDER BY opened_at ASC, incident_id ASC
            """,
            (workflow_id, "OPEN"),
        ).fetchall()

        approval_by_node_id: dict[str, dict[str, Any]] = {}
        for approval in approvals:
            subject = (((approval.get("payload") or {}).get("review_pack") or {}).get("subject") or {})
            source_node_id = str(subject.get("source_node_id") or "").strip()
            if source_node_id and source_node_id not in approval_by_node_id:
                approval_by_node_id[source_node_id] = approval

        incident_by_node_id: dict[str, dict[str, Any]] = {}
        for row in incident_rows:
            incident = repository._convert_incident_projection_row(row)
            node_id = str(incident.get("node_id") or "").strip()
            if node_id and node_id not in incident_by_node_id:
                incident_by_node_id[node_id] = incident

        raw_nodes: list[dict[str, Any]] = []
        current_ticket_status_by_logical_id: dict[str, str] = {}
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
            display_spec = _resolve_display_ticket_spec(created_spec)
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
            logical_ticket_id = _resolve_logical_ticket_id(created_spec, display_spec, latest_ticket_id)
            parent_ticket_id = (
                str(display_spec.get("parent_ticket_id") or "").strip()
                if display_spec is not None
                else ""
            )
            phase = _resolve_phase_label(created_spec)
            delivery_stage = (
                str(display_spec.get("delivery_stage") or "").strip().upper() or None
                if display_spec is not None
                else None
            )
            approval = approval_by_node_id.get(node_id)
            incident = incident_by_node_id.get(node_id)
            ticket_status = str(current_ticket.get("status") or "").strip() if current_ticket is not None else None
            raw_nodes.append(
                {
                    "node_id": node_id,
                    "ticket_id": logical_ticket_id or None,
                    "parent_ticket_id": parent_ticket_id or None,
                    "phase": phase,
                    "delivery_stage": delivery_stage,
                    "node_status": str(node["status"]),
                    "ticket_status": ticket_status or None,
                    "role_profile_ref": (
                        str(display_spec.get("role_profile_ref") or "").strip() or None
                        if display_spec is not None
                        else None
                    ),
                    "output_schema_ref": (
                        str(display_spec.get("output_schema_ref") or "").strip() or None
                        if display_spec is not None
                        else None
                    ),
                    "lease_owner": (
                        str(current_ticket.get("lease_owner") or "").strip() or None
                        if current_ticket is not None
                        else None
                    ),
                    "expected_artifact_scope": (
                        list(display_spec.get("allowed_write_set") or [])
                        if display_spec is not None
                        else []
                    ),
                    "open_review_pack_id": approval.get("review_pack_id") if approval is not None else None,
                    "open_incident_id": incident.get("incident_id") if incident is not None else None,
                    "sort_key": (
                        current_ticket.get("updated_at") if current_ticket is not None else node.get("updated_at"),
                        logical_ticket_id or node_id,
                    ),
                }
            )
            if logical_ticket_id and ticket_status:
                current_ticket_status_by_logical_id[logical_ticket_id] = ticket_status

    for item in raw_nodes:
        parent_ticket_id = item["parent_ticket_id"]
        if item["open_incident_id"] is not None:
            block_reason = "INCIDENT_OPEN"
        elif item["open_review_pack_id"] is not None or (
            item["node_status"] == NODE_STATUS_BLOCKED_FOR_BOARD_REVIEW
            or item["ticket_status"] == TICKET_STATUS_BLOCKED_FOR_BOARD_REVIEW
        ):
            block_reason = "BOARD_REVIEW_OPEN"
        elif parent_ticket_id and current_ticket_status_by_logical_id.get(parent_ticket_id) != TICKET_STATUS_COMPLETED:
            block_reason = "WAITING_PARENT"
        elif item["node_status"] == NODE_STATUS_COMPLETED or item["ticket_status"] == TICKET_STATUS_COMPLETED:
            block_reason = "COMPLETED"
        else:
            block_reason = "READY"
        item["block_reason"] = block_reason

    children_by_parent: dict[str, list[dict[str, Any]]] = {}
    item_by_ticket_id = {
        str(item["ticket_id"]): item
        for item in raw_nodes
        if item.get("ticket_id") is not None
    }
    for item in raw_nodes:
        parent_ticket_id = item["parent_ticket_id"]
        if parent_ticket_id:
            children_by_parent.setdefault(parent_ticket_id, []).append(item)

    def _node_sort_key(item: dict[str, Any]) -> tuple[object, str]:
        return (item["sort_key"][0] or generated_at, str(item.get("ticket_id") or item["node_id"]))

    ordered_nodes: list[dict[str, Any]] = []
    visited_node_ids: set[str] = set()

    def _append_branch(item: dict[str, Any]) -> None:
        node_id = str(item["node_id"])
        if node_id in visited_node_ids:
            return
        visited_node_ids.add(node_id)
        ordered_nodes.append(item)
        child_items = sorted(children_by_parent.get(str(item.get("ticket_id") or ""), []), key=_node_sort_key)
        for child in child_items:
            _append_branch(child)

    root_nodes = sorted(
        [
            item
            for item in raw_nodes
            if item["parent_ticket_id"] is None or item["parent_ticket_id"] not in item_by_ticket_id
        ],
        key=_node_sort_key,
    )
    for item in root_nodes:
        _append_branch(item)
    for item in sorted(raw_nodes, key=_node_sort_key):
        _append_branch(item)

    current_stop_node: dict[str, Any] | None = None
    for reason in ("INCIDENT_OPEN", "BOARD_REVIEW_OPEN", "WAITING_PARENT"):
        current_stop_node = next((item for item in ordered_nodes if item["block_reason"] == reason), None)
        if current_stop_node is not None:
            break

    critical_path_ticket_ids: set[str] = set()
    critical_path_node_ids: set[str] = set()
    if current_stop_node is not None:
        critical_path_node_ids.add(str(current_stop_node["node_id"]))
        parent_ticket_id = str(current_stop_node.get("ticket_id") or "").strip()
        while parent_ticket_id:
            critical_path_ticket_ids.add(parent_ticket_id)
            parent_item = item_by_ticket_id.get(parent_ticket_id) or {}
            if parent_item:
                critical_path_node_ids.add(str(parent_item["node_id"]))
            parent_ticket_id = str(parent_item.get("parent_ticket_id") or "").strip()

    order_index = {
        str(item.get("ticket_id") or item["node_id"]): index
        for index, item in enumerate(ordered_nodes)
    }
    dependent_ticket_ids_by_ticket_id = {
        ticket_id: sorted(
            [str(child.get("ticket_id")) for child in children if child.get("ticket_id")],
            key=lambda child_ticket_id: order_index.get(child_ticket_id, 0),
        )
        for ticket_id, children in children_by_parent.items()
    }

    nodes = [
        DependencyInspectorNodeProjection(
            node_id=str(item["node_id"]),
            ticket_id=item["ticket_id"],
            parent_ticket_id=item["parent_ticket_id"],
            phase=str(item["phase"]),
            delivery_stage=item["delivery_stage"],
            node_status=str(item["node_status"]),
            ticket_status=item["ticket_status"],
            role_profile_ref=item["role_profile_ref"],
            output_schema_ref=item["output_schema_ref"],
            lease_owner=item["lease_owner"],
            depends_on_ticket_id=item["parent_ticket_id"],
            dependent_ticket_ids=dependent_ticket_ids_by_ticket_id.get(str(item.get("ticket_id") or ""), []),
            block_reason=str(item["block_reason"]),
            is_critical_path=(
                bool(item.get("ticket_id") and str(item["ticket_id"]) in critical_path_ticket_ids)
                or str(item["node_id"]) in critical_path_node_ids
            ),
            is_blocked=str(item["block_reason"]) in {"INCIDENT_OPEN", "BOARD_REVIEW_OPEN", "WAITING_PARENT"},
            expected_artifact_scope=list(item["expected_artifact_scope"]),
            open_review_pack_id=item["open_review_pack_id"],
            open_incident_id=item["open_incident_id"],
        )
        for item in ordered_nodes
    ]

    current_stop = (
        DependencyInspectorCurrentStopProjection(
            reason=str(current_stop_node["block_reason"]),
            node_id=str(current_stop_node["node_id"]),
            ticket_id=current_stop_node["ticket_id"],
            review_pack_id=current_stop_node["open_review_pack_id"],
            incident_id=current_stop_node["open_incident_id"],
        )
        if current_stop_node is not None
        else None
    )

    return DependencyInspectorProjectionEnvelope(
        schema_version=SCHEMA_VERSION,
        generated_at=generated_at,
        projection_version=projection_version,
        cursor=cursor,
        data=DependencyInspectorProjectionData(
            workflow=DependencyInspectorWorkflowProjection(
                workflow_id=str(workflow["workflow_id"]),
                title=str(workflow["title"]),
                current_stage=str(workflow["current_stage"]),
                status=str(workflow["status"]),
            ),
            summary=DependencyInspectorSummaryProjection(
                total_nodes=len(nodes),
                critical_path_nodes=sum(1 for item in nodes if item.is_critical_path),
                blocked_nodes=sum(1 for item in nodes if item.is_blocked),
                open_approvals=len(approvals),
                open_incidents=len(incident_rows),
                current_stop=current_stop,
            ),
            nodes=nodes,
        ),
    )


def build_workforce_projection(repository: ControlPlaneRepository) -> WorkforceProjectionEnvelope:
    repository.initialize()
    cursor, projection_version = repository.get_cursor_and_version()
    employees = repository.list_employee_projections()
    summary = _build_workforce_summary(repository)
    busy_tickets = repository.list_ticket_projections_by_statuses_readonly(
        ["LEASED", "EXECUTING", "CANCEL_REQUESTED"]
    )
    now = now_local()

    active_ticket_by_worker: dict[str, dict[str, Any]] = {}
    for ticket in busy_tickets:
        owner = ticket.get("lease_owner")
        if owner is None:
            continue
        if ticket["status"] == "LEASED":
            lease_expires_at = ticket.get("lease_expires_at")
            if lease_expires_at is None or lease_expires_at <= now:
                continue
        active_ticket_by_worker[str(owner)] = ticket

    lanes: dict[str, dict[str, Any]] = {}
    for employee in employees:
        role_type = str(employee.get("role_type") or "unknown")
        lane = lanes.setdefault(
            role_type,
            {
                "role_type": role_type,
                "active_count": 0,
                "idle_count": 0,
                "workers": [],
            },
        )
        employee_id = str(employee["employee_id"])
        ticket = active_ticket_by_worker.get(employee_id)
        state = str(employee.get("state") or "UNKNOWN")
        if ticket is not None and ticket["status"] == "CANCEL_REQUESTED":
            activity_state = "FUSED"
        elif state != "ACTIVE":
            activity_state = "OFFLINE"
        elif ticket is None:
            activity_state = "IDLE"
            lane["idle_count"] += 1
        elif role_type == "checker":
            activity_state = "REVIEWING"
            lane["active_count"] += 1
        else:
            activity_state = "EXECUTING"
            lane["active_count"] += 1

        lane["workers"].append(
            WorkforceWorkerProjection(
                employee_id=employee_id,
                role_type=role_type,
                employment_state=state,
                activity_state=activity_state,
                current_ticket_id=str(ticket.get("ticket_id")) if ticket is not None else None,
                current_node_id=str(ticket.get("node_id")) if ticket is not None else None,
                provider_id=employee.get("provider_id"),
                last_update_at=employee.get("updated_at"),
            )
        )

    role_lanes = []
    for role_type in sorted(lanes):
        lane = lanes[role_type]
        role_lanes.append(
            WorkforceRoleLaneProjection(
                role_type=lane["role_type"],
                active_count=lane["active_count"],
                idle_count=lane["idle_count"],
                workers=sorted(lane["workers"], key=lambda worker: worker.employee_id),
            )
        )

    return WorkforceProjectionEnvelope(
        schema_version=SCHEMA_VERSION,
        generated_at=now_local(),
        projection_version=projection_version,
        cursor=cursor,
        data=WorkforceProjectionData(summary=summary, role_lanes=role_lanes),
    )


def build_runtime_provider_projection(
    repository: ControlPlaneRepository,
    runtime_provider_store: RuntimeProviderConfigStore,
) -> RuntimeProviderProjectionEnvelope:
    repository.initialize()
    cursor, projection_version = repository.get_cursor_and_version()
    return RuntimeProviderProjectionEnvelope(
        schema_version=SCHEMA_VERSION,
        generated_at=now_local(),
        projection_version=projection_version,
        cursor=cursor,
        data=_build_runtime_provider_projection_data(repository, runtime_provider_store),
    )


def build_dashboard_projection(
    repository: ControlPlaneRepository,
    runtime_provider_store: RuntimeProviderConfigStore,
) -> DashboardProjectionEnvelope:
    repository.initialize()
    generated_at = now_local()
    active_workflow = repository.get_active_workflow()
    cursor, projection_version = repository.get_cursor_and_version()
    pending_approvals = repository.count_open_approvals()
    open_incident_rows = repository.list_open_incidents()
    open_incidents = len(open_incident_rows)
    open_circuit_breakers = repository.count_open_circuit_breakers()
    open_provider_incidents = repository.count_open_provider_incidents()
    active_tickets = repository.count_active_tickets()
    blocked_node_ids = sorted(
        {
            *repository.list_blocked_node_ids(),
            *[
                str(incident["node_id"])
                for incident in open_incident_rows
                if incident.get("node_id") is not None
                and incident.get("circuit_breaker_state") == CIRCUIT_BREAKER_STATE_OPEN
            ],
        }
    )
    blocked_nodes = len(blocked_node_ids)
    artifact_cleanup_summary = repository.get_artifact_cleanup_summary(at=generated_at)
    latest_cleanup_event = artifact_cleanup_summary["latest_cleanup_event"]
    artifact_cleanup_payload = latest_cleanup_event.get("payload", {}) if latest_cleanup_event else {}
    settings = get_settings()

    if active_workflow is None:
        active_workflow_projection = None
        budget_total = 0
        budget_used = 0
        pipeline_summary = _build_pipeline_summary(
            repository,
            workflow_id=None,
            pending_approvals=pending_approvals,
        )
    else:
        active_workflow_projection = ActiveWorkflowProjection(
            workflow_id=active_workflow["workflow_id"],
            title=active_workflow["title"],
            north_star_goal=active_workflow["north_star_goal"],
            status=active_workflow["status"],
            current_stage=active_workflow["current_stage"],
            started_at=active_workflow["started_at"],
            deadline_at=active_workflow["deadline_at"],
        )
        budget_total = active_workflow["budget_total"]
        budget_used = active_workflow["budget_used"]
        pipeline_summary = _build_pipeline_summary(
            repository,
            workflow_id=active_workflow["workflow_id"],
            pending_approvals=pending_approvals,
        )

    preview_events = [
        EventStreamPreviewItem(
            event_id=event["event_id"],
            occurred_at=event["occurred_at"],
            category=event["category"],
            severity=EventSeverity(event["severity"]),
            message=event["message"],
            related_ref=event["related_ref"],
        )
        for event in repository.get_recent_event_previews()
    ]
    runtime_provider = _build_runtime_provider_projection_data(repository, runtime_provider_store)
    completion_summary = (
        _build_dashboard_completion_summary(repository, active_workflow["workflow_id"])
        if active_workflow is not None
        else None
    )

    return DashboardProjectionEnvelope(
        schema_version=SCHEMA_VERSION,
        generated_at=generated_at,
        projection_version=projection_version,
        cursor=cursor,
        data=DashboardProjectionData(
            workspace=WorkspaceSummary(
                workspace_id="ws_default",
                workspace_name="Default Workspace",
            ),
            active_workflow=active_workflow_projection,
            ops_strip=OpsStripProjection(
                budget_total=budget_total,
                budget_used=budget_used,
                budget_remaining=max(budget_total - budget_used, 0),
                token_burn_rate_5m=0,
                active_tickets=active_tickets,
                blocked_nodes=blocked_nodes,
                open_incidents=open_incidents,
                open_circuit_breakers=open_circuit_breakers,
                provider_health_summary="DEGRADED" if open_provider_incidents > 0 else "UNKNOWN",
            ),
            runtime_status=DashboardRuntimeStatusProjection(
                effective_mode=runtime_provider.effective_mode,
                provider_label=(
                    "OpenAI Compat"
                    if runtime_provider.mode == "OPENAI_COMPAT"
                    else "Local Deterministic"
                ),
                model=runtime_provider.model,
                configured_worker_count=runtime_provider.configured_worker_count,
                provider_health_summary="DEGRADED" if open_provider_incidents > 0 else "UNKNOWN",
                reason=runtime_provider.effective_reason,
            ),
            pipeline_summary=PipelineSummaryProjection(
                phases=pipeline_summary.phases,
                critical_path_node_ids=pipeline_summary.critical_path_node_ids,
                blocked_node_ids=blocked_node_ids,
            ),
            inbox_counts=InboxCountsProjection(
                approvals_pending=pending_approvals,
                incidents_pending=open_incidents,
                budget_alerts=0,
                provider_alerts=open_provider_incidents,
            ),
            workforce_summary=_build_workforce_summary(repository),
            artifact_maintenance=ArtifactMaintenanceProjection(
                auto_cleanup_enabled=settings.artifact_cleanup_interval_sec > 0,
                cleanup_interval_sec=settings.artifact_cleanup_interval_sec,
                ephemeral_default_ttl_sec=settings.artifact_ephemeral_default_ttl_sec,
                retention_defaults=build_artifact_retention_defaults(
                    default_ephemeral_ttl_sec=settings.artifact_ephemeral_default_ttl_sec,
                    default_operational_evidence_ttl_sec=(
                        settings.artifact_operational_evidence_default_ttl_sec
                    ),
                    default_review_evidence_ttl_sec=settings.artifact_review_evidence_default_ttl_sec,
                ),
                pending_expired_count=int(artifact_cleanup_summary["pending_expired_count"]),
                pending_storage_cleanup_count=int(artifact_cleanup_summary["pending_storage_cleanup_count"]),
                delete_failed_count=int(artifact_cleanup_summary["delete_failed_count"]),
                legacy_unknown_retention_count=int(
                    artifact_cleanup_summary["legacy_unknown_retention_count"]
                ),
                last_run_at=latest_cleanup_event["occurred_at"] if latest_cleanup_event else None,
                last_cleaned_by=artifact_cleanup_payload.get("cleaned_by"),
                last_trigger=artifact_cleanup_payload.get("trigger"),
                last_expired_count=int(artifact_cleanup_payload.get("expired_count") or 0),
                last_storage_deleted_count=int(
                    artifact_cleanup_payload.get("storage_deleted_count") or 0
                ),
            ),
            completion_summary=completion_summary,
            event_stream_preview=preview_events,
        ),
    )


def build_inbox_projection(repository: ControlPlaneRepository) -> InboxProjectionEnvelope:
    repository.initialize()
    cursor, projection_version = repository.get_cursor_and_version()
    items = []
    for approval in repository.list_open_approvals():
        payload = approval["payload"]
        items.append(
            InboxItemProjection(
                inbox_item_id=f"inbox_{approval['approval_id']}",
                workflow_id=approval["workflow_id"],
                item_type=(
                    "CORE_HIRE_APPROVAL"
                    if approval["approval_type"] == "CORE_HIRE_APPROVAL"
                    else "BOARD_APPROVAL"
                ),
                priority=payload.get("priority", "medium"),
                status=approval["status"],
                created_at=approval["created_at"],
                sla_due_at=None,
                title=payload.get("inbox_title", approval["review_pack_id"]),
                summary=payload.get("inbox_summary", "Board review pending."),
                source_ref=approval["approval_id"],
                route_target=RouteTarget(
                    view="review_room",
                    review_pack_id=approval["review_pack_id"],
                ),
                badges=payload.get("badges", []),
            )
        )
    for incident in repository.list_open_incidents():
        if incident.get("provider_id") is not None:
            provider_id = str(incident["provider_id"])
            pause_reason = str((incident.get("payload") or {}).get("pause_reason") or "PROVIDER_FAILURE")
            items.append(
                InboxItemProjection(
                    inbox_item_id=f"inbox_{incident['incident_id']}",
                    workflow_id=incident["workflow_id"],
                    item_type="PROVIDER_INCIDENT",
                    priority=str(incident.get("severity") or "high"),
                    status=incident["status"],
                    created_at=incident["opened_at"],
                    sla_due_at=None,
                    title=f"Provider pause on {provider_id}",
                    summary=(
                        f"Provider {provider_id} entered paused state because of {pause_reason.lower()}."
                    ),
                    source_ref=incident["incident_id"],
                    route_target=RouteTarget(
                        view="incident_detail",
                        incident_id=incident["incident_id"],
                    ),
                    badges=["provider", "execution_pause"],
                )
            )
            continue
        if incident.get("incident_type") == INCIDENT_TYPE_REPEATED_FAILURE_ESCALATION:
            node_id = incident.get("node_id") or "unknown-node"
            latest_failure_kind = str(
                (incident.get("payload") or {}).get("latest_failure_kind") or "RUNTIME_ERROR"
            )
            items.append(
                InboxItemProjection(
                    inbox_item_id=f"inbox_{incident['incident_id']}",
                    workflow_id=incident["workflow_id"],
                    item_type="INCIDENT_ESCALATION",
                    priority=str(incident.get("severity") or "high"),
                    status=incident["status"],
                    created_at=incident["opened_at"],
                    sla_due_at=None,
                    title=f"Repeated failure escalation in {node_id}",
                    summary=(
                        f"Node {node_id} repeated the same {latest_failure_kind.lower()} "
                        "fingerprint and opened a circuit breaker."
                    ),
                    source_ref=incident["incident_id"],
                    route_target=RouteTarget(
                        view="incident_detail",
                        incident_id=incident["incident_id"],
                    ),
                    badges=["repeat_failure", "circuit_breaker"],
                )
            )
            continue
        if incident.get("incident_type") == INCIDENT_TYPE_MAKER_CHECKER_REWORK_ESCALATION:
            node_id = incident.get("node_id") or "unknown-node"
            rework_streak_count = int(
                (incident.get("payload") or {}).get("rework_streak_count") or 0
            )
            items.append(
                InboxItemProjection(
                    inbox_item_id=f"inbox_{incident['incident_id']}",
                    workflow_id=incident["workflow_id"],
                    item_type="INCIDENT_ESCALATION",
                    priority=str(incident.get("severity") or "high"),
                    status=incident["status"],
                    created_at=incident["opened_at"],
                    sla_due_at=None,
                    title=f"Maker-checker rework escalation in {node_id}",
                    summary=(
                        f"Repeated checker findings hit the rework threshold ({rework_streak_count}) "
                        "and opened a circuit breaker."
                    ),
                    source_ref=incident["incident_id"],
                    route_target=RouteTarget(
                        view="incident_detail",
                        incident_id=incident["incident_id"],
                    ),
                    badges=["maker_checker", "rework", "circuit_breaker"],
                )
            )
            continue
        if incident.get("incident_type") == INCIDENT_TYPE_STAFFING_CONTAINMENT:
            node_id = str(incident.get("node_id") or "unknown-node")
            employee_id = str((incident.get("payload") or {}).get("employee_id") or "unknown-worker")
            action_kind = str((incident.get("payload") or {}).get("action_kind") or "EMPLOYEE_CHANGE")
            items.append(
                InboxItemProjection(
                    inbox_item_id=f"inbox_{incident['incident_id']}",
                    workflow_id=incident["workflow_id"],
                    item_type="INCIDENT_ESCALATION",
                    priority=str(incident.get("severity") or "high"),
                    status=incident["status"],
                    created_at=incident["opened_at"],
                    sla_due_at=None,
                    title=f"Staffing containment on {node_id}",
                    summary=(
                        f"Ticket ownership on {node_id} was contained after {employee_id} "
                        f"hit {action_kind.lower()}."
                    ),
                    source_ref=incident["incident_id"],
                    route_target=RouteTarget(
                        view="incident_detail",
                        incident_id=incident["incident_id"],
                    ),
                    badges=["staffing_containment", "circuit_breaker"],
                )
            )
            continue
        items.append(
            InboxItemProjection(
                inbox_item_id=f"inbox_{incident['incident_id']}",
                workflow_id=incident["workflow_id"],
                item_type="INCIDENT_ESCALATION",
                priority=str(incident.get("severity") or "high"),
                status=incident["status"],
                created_at=incident["opened_at"],
                sla_due_at=None,
                title=f"Repeated timeout escalation in {incident.get('node_id') or 'unknown-node'}",
                summary=(
                    f"Node {incident.get('node_id') or 'unknown-node'} hit repeated runtime timeout "
                    "threshold and opened a circuit breaker."
                ),
                source_ref=incident["incident_id"],
                route_target=RouteTarget(
                    view="incident_detail",
                    incident_id=incident["incident_id"],
                ),
                badges=["runtime_timeout", "circuit_breaker"],
            )
        )
    items.sort(key=lambda item: item.created_at, reverse=True)
    return InboxProjectionEnvelope(
        schema_version=SCHEMA_VERSION,
        generated_at=now_local(),
        projection_version=projection_version,
        cursor=cursor,
        data=InboxProjectionData(items=items),
    )


def build_review_room_projection(
    repository: ControlPlaneRepository,
    review_pack_id: str,
) -> ReviewRoomProjectionEnvelope | None:
    repository.initialize()
    approval = repository.get_approval_by_review_pack_id(review_pack_id)
    if approval is None:
        return None

    cursor, projection_version = repository.get_cursor_and_version()
    payload = approval["payload"]
    available_actions = payload.get("available_actions", [])
    if approval["status"] != APPROVAL_STATUS_OPEN:
        available_actions = []

    return ReviewRoomProjectionEnvelope(
        schema_version=SCHEMA_VERSION,
        generated_at=now_local(),
        projection_version=projection_version,
        cursor=cursor,
        data=ReviewRoomProjectionData(
            review_pack=payload.get("review_pack"),
            available_actions=available_actions,
            draft_defaults=ReviewRoomDraftDefaults(**payload.get("draft_defaults", {})),
        ),
    )


def build_review_room_developer_inspector_projection(
    repository: ControlPlaneRepository,
    review_pack_id: str,
    developer_inspector_store: DeveloperInspectorStore,
) -> ReviewRoomDeveloperInspectorProjectionEnvelope | None:
    repository.initialize()
    approval = repository.get_approval_by_review_pack_id(review_pack_id)
    if approval is None:
        return None

    cursor, projection_version = repository.get_cursor_and_version()
    review_pack = approval["payload"].get("review_pack") or {}
    refs = review_pack.get("developer_inspector_refs") or {}
    compiled_context_bundle_ref = refs.get("compiled_context_bundle_ref")
    compile_manifest_ref = refs.get("compile_manifest_ref")
    rendered_execution_payload_ref = refs.get("rendered_execution_payload_ref")
    compiled_context_bundle = (
        developer_inspector_store.read_json(compiled_context_bundle_ref)
        if compiled_context_bundle_ref is not None
        else None
    )
    compile_manifest = (
        developer_inspector_store.read_json(compile_manifest_ref)
        if compile_manifest_ref is not None
        else None
    )
    rendered_execution_payload = (
        developer_inspector_store.read_json(rendered_execution_payload_ref)
        if rendered_execution_payload_ref is not None
        else None
    )

    ref_count = sum(
        ref is not None
        for ref in (
            compiled_context_bundle_ref,
            compile_manifest_ref,
            rendered_execution_payload_ref,
        )
    )
    materialized_count = sum(
        payload is not None
        for payload in (
            compiled_context_bundle,
            compile_manifest,
            rendered_execution_payload,
        )
    )
    availability = "missing"
    if ref_count > 0 and ref_count == materialized_count:
        availability = "ready"
    elif ref_count > 0 or materialized_count > 0:
        availability = "partial"

    compile_summary = None
    render_summary = None
    if compile_manifest is not None:
        source_entries = list(compile_manifest.get("source_log") or [])
        budget_plan = dict(compile_manifest.get("budget_plan") or {})
        budget_actual = dict(compile_manifest.get("budget_actual") or {})
        final_bundle_stats = dict(compile_manifest.get("final_bundle_stats") or {})
        reason_counts: dict[str, int] = {}
        retrieval_channel_counts: dict[str, int] = {}
        inline_full_count = 0
        inline_fragment_count = 0
        inline_partial_count = 0
        reference_only_count = 0
        degraded_source_count = 0
        missing_critical_source_count = 0
        retrieved_source_count = 0
        dropped_retrieval_count = 0
        dropped_explicit_source_count = 0
        for entry in source_entries:
            if not isinstance(entry, dict):
                continue
            content_mode = str(entry.get("content_mode") or "REFERENCE_ONLY")
            if content_mode == "INLINE_FULL":
                inline_full_count += 1
            elif content_mode == "INLINE_FRAGMENT":
                inline_fragment_count += 1
                degraded_source_count += 1
            elif content_mode == "INLINE_PARTIAL":
                inline_partial_count += 1
                degraded_source_count += 1
            else:
                reference_only_count += 1
                degraded_source_count += 1

            reason_code = entry.get("reason_code")
            if isinstance(reason_code, str) and reason_code:
                reason_counts[reason_code] = reason_counts.get(reason_code, 0) + 1
            source_kind = str(entry.get("source_kind") or "")
            if source_kind.startswith("RETRIEVAL_") and entry.get("status") != "DROPPED":
                retrieved_source_count += 1
                if source_kind == "RETRIEVAL_REVIEW_MATCH":
                    channel = "review_summaries"
                elif source_kind == "RETRIEVAL_INCIDENT_MATCH":
                    channel = "incident_summaries"
                else:
                    channel = "artifact_summaries"
                retrieval_channel_counts[channel] = retrieval_channel_counts.get(channel, 0) + 1
            if reason_code == "RETRIEVAL_DROPPED_FOR_BUDGET":
                dropped_retrieval_count += 1
            if (
                source_kind == "ARTIFACT_REFERENCE"
                and entry.get("status") == "DROPPED"
            ):
                dropped_explicit_source_count += 1
            if entry.get("status") == "MISSING" and entry.get("critical") is True:
                missing_critical_source_count += 1

        total_budget_tokens = int(budget_plan.get("total_budget_tokens") or 0)
        used_budget_tokens = int(budget_actual.get("final_bundle_tokens") or 0)
        remaining_budget_tokens = max(total_budget_tokens - used_budget_tokens, 0)
        truncated_tokens = int(budget_actual.get("truncated_tokens") or 0)
        if int(final_bundle_stats.get("dropped_explicit_source_count") or 0) > dropped_explicit_source_count:
            dropped_explicit_source_count = int(final_bundle_stats.get("dropped_explicit_source_count") or 0)

        media_reference_count = 0
        download_attachment_count = 0
        fragment_strategy_counts: dict[str, int] = {}
        preview_strategy_counts: dict[str, int] = {}
        preview_kind_counts: dict[str, int] = {}
        if compiled_context_bundle is not None:
            for block in list(compiled_context_bundle.get("context_blocks") or []):
                if not isinstance(block, dict):
                    continue
                content_payload = block.get("content_payload") or {}
                if not isinstance(content_payload, dict):
                    continue
                fragment_strategy = content_payload.get("content_fragment_strategy")
                if isinstance(fragment_strategy, str) and fragment_strategy:
                    fragment_strategy_counts[fragment_strategy] = (
                        fragment_strategy_counts.get(fragment_strategy, 0) + 1
                    )
                preview_strategy = content_payload.get("content_preview_strategy")
                if isinstance(preview_strategy, str) and preview_strategy:
                    preview_strategy_counts[preview_strategy] = (
                        preview_strategy_counts.get(preview_strategy, 0) + 1
                    )
                preview_kind = content_payload.get("preview_kind")
                if isinstance(preview_kind, str) and preview_kind:
                    preview_kind_counts[preview_kind] = preview_kind_counts.get(preview_kind, 0) + 1
                    if preview_kind == "INLINE_MEDIA":
                        media_reference_count += 1
                    elif preview_kind == "DOWNLOAD_ONLY":
                        download_attachment_count += 1

        compile_summary = ReviewRoomDeveloperInspectorCompileSummary(
            source_count=len(source_entries),
            inline_full_count=inline_full_count,
            inline_fragment_count=inline_fragment_count,
            inline_partial_count=inline_partial_count,
            reference_only_count=reference_only_count,
            degraded_source_count=degraded_source_count,
            missing_critical_source_count=missing_critical_source_count,
            reason_counts=reason_counts,
            retrieved_source_count=retrieved_source_count,
            retrieval_channel_counts=retrieval_channel_counts,
            dropped_retrieval_count=dropped_retrieval_count,
            total_budget_tokens=total_budget_tokens,
            used_budget_tokens=used_budget_tokens,
            remaining_budget_tokens=remaining_budget_tokens,
            truncated_tokens=truncated_tokens,
            dropped_explicit_source_count=dropped_explicit_source_count,
            media_reference_count=media_reference_count,
            download_attachment_count=download_attachment_count,
            fragment_strategy_counts=fragment_strategy_counts,
            preview_strategy_counts=preview_strategy_counts,
            preview_kind_counts=preview_kind_counts,
        )
    if rendered_execution_payload is not None:
        summary_payload = rendered_execution_payload.get("summary") or {}
        if summary_payload:
            render_summary = RenderedExecutionPayloadSummary.model_validate(summary_payload)

    return ReviewRoomDeveloperInspectorProjectionEnvelope(
        schema_version=SCHEMA_VERSION,
        generated_at=now_local(),
        projection_version=projection_version,
        cursor=cursor,
        data=ReviewRoomDeveloperInspectorProjectionData(
            review_pack_id=review_pack_id,
            compiled_context_bundle_ref=compiled_context_bundle_ref,
            compile_manifest_ref=compile_manifest_ref,
            rendered_execution_payload_ref=rendered_execution_payload_ref,
            compiled_context_bundle=compiled_context_bundle,
            compile_manifest=compile_manifest,
            rendered_execution_payload=rendered_execution_payload,
            compile_summary=compile_summary,
            render_summary=render_summary,
            availability=availability,
        ),
    )


def build_ticket_artifacts_projection(
    repository: ControlPlaneRepository,
    ticket_id: str,
) -> TicketArtifactsProjectionEnvelope | None:
    repository.initialize()
    ticket = repository.get_current_ticket_projection(ticket_id)
    if ticket is None:
        return None

    cursor, projection_version = repository.get_cursor_and_version()
    artifacts = repository.list_ticket_artifacts(ticket_id)
    return TicketArtifactsProjectionEnvelope(
        schema_version=SCHEMA_VERSION,
        generated_at=now_local(),
        projection_version=projection_version,
        cursor=cursor,
        data=TicketArtifactsProjectionData(
            ticket_id=ticket_id,
            artifacts=[
                TicketArtifactProjection(
                    artifact_ref=metadata["artifact_ref"],
                    path=metadata["path"],
                    kind=metadata["kind"],
                    media_type=metadata["media_type"],
                    status=metadata["status"],
                    materialization_status=metadata["materialization_status"],
                    lifecycle_status=metadata["lifecycle_status"],
                    retention_class=metadata["retention_class"],
                    retention_class_source=metadata["retention_class_source"],
                    retention_ttl_sec=metadata["retention_ttl_sec"],
                    retention_policy_source=metadata["retention_policy_source"],
                    expires_at=metadata["expires_at"],
                    deleted_at=metadata["deleted_at"],
                    deleted_by=metadata["deleted_by"],
                    delete_reason=metadata["delete_reason"],
                    storage_backend=metadata["storage_backend"],
                    storage_delete_status=metadata["storage_delete_status"],
                    storage_deleted_at=metadata["storage_deleted_at"],
                    size_bytes=metadata["size_bytes"],
                    content_hash=metadata["content_hash"],
                    content_url=metadata["content_url"],
                    download_url=metadata["download_url"],
                    preview_url=metadata["preview_url"],
                    created_at=metadata["created_at"],
                )
                for artifact in artifacts
                for metadata in [build_artifact_metadata(artifact)]
            ],
        ),
    )


def build_artifact_cleanup_candidates_projection(
    repository: ControlPlaneRepository,
    *,
    ticket_id: str | None = None,
    retention_class: str | None = None,
    limit: int = 50,
) -> ArtifactCleanupCandidatesProjectionEnvelope:
    repository.initialize()
    generated_at = now_local()
    cursor, projection_version = repository.get_cursor_and_version()
    artifacts = repository.list_artifact_cleanup_candidates(
        at=generated_at,
        ticket_id=ticket_id,
        retention_class=retention_class,
        limit=limit,
    )
    projected_artifacts: list[ArtifactCleanupCandidateProjection] = []
    for artifact in artifacts:
        metadata = build_artifact_metadata(artifact, at=generated_at)
        cleanup_reason = "STORAGE_DELETE_PENDING"
        if (
            metadata["lifecycle_status"] == "EXPIRED"
            and metadata["storage_deleted_at"] is None
        ) or (
            artifact.get("lifecycle_status") == "ACTIVE"
            and metadata["expires_at"] is not None
            and metadata["expires_at"] <= generated_at
        ):
            cleanup_reason = "EXPIRED_DUE"
        projected_artifacts.append(
            ArtifactCleanupCandidateProjection(
                artifact_ref=metadata["artifact_ref"],
                ticket_id=metadata["ticket_id"],
                path=metadata["path"],
                lifecycle_status=metadata["lifecycle_status"],
                retention_class=metadata["retention_class"],
                retention_class_source=metadata["retention_class_source"],
                retention_ttl_sec=metadata["retention_ttl_sec"],
                retention_policy_source=metadata["retention_policy_source"],
                expires_at=metadata["expires_at"],
                storage_backend=metadata["storage_backend"],
                storage_delete_status=metadata["storage_delete_status"],
                storage_deleted_at=metadata["storage_deleted_at"],
                cleanup_reason=cleanup_reason,
            )
        )
    return ArtifactCleanupCandidatesProjectionEnvelope(
        schema_version=SCHEMA_VERSION,
        generated_at=generated_at,
        projection_version=projection_version,
        cursor=cursor,
        data=ArtifactCleanupCandidatesProjectionData(
            filters=ArtifactCleanupCandidatesProjectionFilters(
                ticket_id=ticket_id,
                retention_class=retention_class,
                limit=limit,
            ),
            artifacts=projected_artifacts,
        ),
    )


def build_incident_detail_projection(
    repository: ControlPlaneRepository,
    incident_id: str,
) -> IncidentDetailProjectionEnvelope | None:
    repository.initialize()
    incident = repository.get_incident_projection(incident_id)
    if incident is None:
        return None

    cursor, projection_version = repository.get_cursor_and_version()
    incident_type = str(incident["incident_type"])
    available_followup_actions = [IncidentFollowupAction.RESTORE_ONLY.value]
    recommended_followup_action: str | None = IncidentFollowupAction.RESTORE_ONLY.value
    if incident_type == INCIDENT_TYPE_RUNTIME_TIMEOUT_ESCALATION:
        available_followup_actions.append(
            IncidentFollowupAction.RESTORE_AND_RETRY_LATEST_TIMEOUT.value
        )
        recommended_followup_action = IncidentFollowupAction.RESTORE_AND_RETRY_LATEST_TIMEOUT.value
    elif incident_type == INCIDENT_TYPE_REPEATED_FAILURE_ESCALATION:
        available_followup_actions.append(
            IncidentFollowupAction.RESTORE_AND_RETRY_LATEST_FAILURE.value
        )
        recommended_followup_action = IncidentFollowupAction.RESTORE_AND_RETRY_LATEST_FAILURE.value
    elif incident_type == INCIDENT_TYPE_PROVIDER_EXECUTION_PAUSED:
        available_followup_actions.append(
            IncidentFollowupAction.RESTORE_AND_RETRY_LATEST_PROVIDER_FAILURE.value
        )
        recommended_followup_action = (
            IncidentFollowupAction.RESTORE_AND_RETRY_LATEST_PROVIDER_FAILURE.value
        )
    elif incident_type == INCIDENT_TYPE_STAFFING_CONTAINMENT:
        available_followup_actions.append(
            IncidentFollowupAction.RESTORE_AND_RETRY_LATEST_STAFFING_CONTAINMENT.value
        )
        recommended_followup_action = (
            IncidentFollowupAction.RESTORE_AND_RETRY_LATEST_STAFFING_CONTAINMENT.value
        )

    return IncidentDetailProjectionEnvelope(
        schema_version=SCHEMA_VERSION,
        generated_at=now_local(),
        projection_version=projection_version,
        cursor=cursor,
        data=IncidentDetailProjectionData(
            incident=IncidentProjectionItem(
                incident_id=incident["incident_id"],
                workflow_id=incident["workflow_id"],
                node_id=incident.get("node_id"),
                ticket_id=incident.get("ticket_id"),
                provider_id=incident.get("provider_id"),
                incident_type=incident["incident_type"],
                status=incident["status"],
                severity=incident.get("severity"),
                fingerprint=incident["fingerprint"],
                circuit_breaker_state=incident.get("circuit_breaker_state"),
                opened_at=incident["opened_at"],
                closed_at=incident.get("closed_at"),
                payload=incident.get("payload") or {},
            ),
            available_followup_actions=available_followup_actions,
            recommended_followup_action=recommended_followup_action,
        ),
    )


def build_worker_runtime_projection(
    repository: ControlPlaneRepository,
    *,
    worker_id: str | None,
    tenant_id: str | None,
    workspace_id: str | None,
    active_only: bool,
    rejection_limit: int,
    grant_limit: int,
) -> WorkerRuntimeProjectionEnvelope:
    repository.initialize()
    generated_at = now_local()
    cursor, projection_version = repository.get_cursor_and_version()
    bindings = repository.list_worker_binding_admin_views(
        worker_id=worker_id,
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        at=generated_at,
    )
    sessions = repository.list_worker_sessions(
        worker_id=worker_id,
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        active_only=False,
    )
    session_items = [
        WorkerSessionAdminProjection(
            session_id=str(session["session_id"]),
            worker_id=str(session["worker_id"]),
            tenant_id=str(session["tenant_id"]),
            workspace_id=str(session["workspace_id"]),
            issued_at=session["issued_at"],
            expires_at=session["expires_at"],
            last_seen_at=session["last_seen_at"],
            revoked_at=session.get("revoked_at"),
            credential_version=int(session["credential_version"]),
            revoke_reason=session.get("revoke_reason"),
            revoked_via=session.get("revoked_via"),
            revoked_by=session.get("revoked_by"),
            is_active=_is_worker_session_active(session, at=generated_at),
        )
        for session in sorted(
            sessions,
            key=lambda item: (item["issued_at"], str(item["session_id"])),
            reverse=True,
        )
    ]
    if active_only:
        session_items = [item for item in session_items if item.is_active]

    grants = repository.list_worker_delivery_grants(
        worker_id=worker_id,
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        active_only=False,
    )
    grant_items = [
        WorkerDeliveryGrantAdminProjection(
            grant_id=str(grant["grant_id"]),
            scope=str(grant["scope"]),
            worker_id=str(grant["worker_id"]),
            session_id=str(grant["session_id"]),
            credential_version=int(grant["credential_version"]),
            tenant_id=str(grant["tenant_id"]),
            workspace_id=str(grant["workspace_id"]),
            ticket_id=str(grant["ticket_id"]),
            artifact_ref=grant.get("artifact_ref"),
            artifact_action=grant.get("artifact_action"),
            command_name=grant.get("command_name"),
            issued_at=grant["issued_at"],
            expires_at=grant["expires_at"],
            revoked_at=grant.get("revoked_at"),
            revoke_reason=grant.get("revoke_reason"),
            revoked_via=grant.get("revoked_via"),
            revoked_by=grant.get("revoked_by"),
            is_active=_is_worker_delivery_grant_active(grant, at=generated_at),
        )
        for grant in sorted(
            grants,
            key=lambda item: (item["issued_at"], str(item["grant_id"])),
            reverse=True,
        )
    ]
    if active_only:
        grant_items = [item for item in grant_items if item.is_active]
    grant_items = grant_items[:grant_limit]

    rejections = repository.list_worker_auth_rejection_logs(
        worker_id=worker_id,
        tenant_id=tenant_id,
        workspace_id=workspace_id,
    )
    rejection_items = [
        WorkerAuthRejectionAdminProjection(
            occurred_at=rejection["occurred_at"],
            route_family=str(rejection["route_family"]),
            reason_code=str(rejection["reason_code"]),
            worker_id=rejection.get("worker_id"),
            session_id=rejection.get("session_id"),
            grant_id=rejection.get("grant_id"),
            ticket_id=rejection.get("ticket_id"),
            tenant_id=rejection.get("tenant_id"),
            workspace_id=rejection.get("workspace_id"),
        )
        for rejection in sorted(
            rejections,
            key=lambda item: (item["occurred_at"], str(item.get("rejection_id") or "")),
            reverse=True,
        )[:rejection_limit]
    ]

    return WorkerRuntimeProjectionEnvelope(
        schema_version=SCHEMA_VERSION,
        generated_at=generated_at,
        projection_version=projection_version,
        cursor=cursor,
        data=WorkerRuntimeProjectionData(
            summary=WorkerRuntimeProjectionSummary(
                binding_count=len(bindings),
                cleanup_eligible_binding_count=sum(
                    1 for binding in bindings if bool(binding.get("cleanup_eligible"))
                ),
                active_session_count=sum(1 for item in session_items if item.is_active),
                active_delivery_grant_count=sum(1 for item in grant_items if item.is_active),
                recent_rejection_count=len(rejection_items),
            ),
            filters=WorkerRuntimeProjectionFilters(
                worker_id=worker_id,
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                active_only=active_only,
                rejection_limit=rejection_limit,
                grant_limit=grant_limit,
            ),
            bindings=[
                WorkerBindingAdminProjection(
                    worker_id=str(binding["worker_id"]),
                    credential_version=int(binding["credential_version"]),
                    tenant_id=str(binding["tenant_id"]),
                    workspace_id=str(binding["workspace_id"]),
                    revoked_before=binding.get("revoked_before"),
                    rotated_at=binding.get("rotated_at"),
                    updated_at=binding["updated_at"],
                    active_session_count=int(binding["active_session_count"]),
                    active_delivery_grant_count=int(binding["active_delivery_grant_count"]),
                    active_ticket_count=int(binding["active_ticket_count"]),
                    latest_bootstrap_issue_at=binding.get("latest_bootstrap_issue_at"),
                    latest_bootstrap_issue_source=binding.get("latest_bootstrap_issue_source"),
                    cleanup_eligible=bool(binding["cleanup_eligible"]),
                )
                for binding in bindings
            ],
            sessions=session_items,
            delivery_grants=grant_items,
            auth_rejections=rejection_items,
        ),
    )


def build_worker_admin_audit_projection(
    repository: ControlPlaneRepository,
    *,
    tenant_id: str | None,
    workspace_id: str | None,
    worker_id: str | None,
    operator_id: str | None,
    action_type: str | None,
    dry_run: bool | None,
    limit: int,
) -> WorkerAdminAuditProjectionEnvelope:
    repository.initialize()
    generated_at = now_local()
    cursor, projection_version = repository.get_cursor_and_version()
    actions = repository.list_worker_admin_action_logs(
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        worker_id=worker_id,
        operator_id=operator_id,
        action_type=action_type,
        dry_run=dry_run,
        limit=limit,
    )
    return WorkerAdminAuditProjectionEnvelope(
        schema_version=SCHEMA_VERSION,
        generated_at=generated_at,
        projection_version=projection_version,
        cursor=cursor,
        data=WorkerAdminAuditProjectionData(
            summary=WorkerAdminAuditProjectionSummary(count=len(actions)),
            filters=WorkerAdminAuditProjectionFilters(
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                worker_id=worker_id,
                operator_id=operator_id,
                action_type=action_type,
                dry_run=dry_run,
                limit=limit,
            ),
            actions=[
                WorkerAdminAuditProjectionItem(
                    action_id=str(action["action_id"]),
                    occurred_at=action["occurred_at"],
                    operator_id=str(action["operator_id"]),
                    operator_role=str(action["operator_role"]),
                    auth_source=str(action["auth_source"]),
                    trusted_proxy_id=action.get("trusted_proxy_id"),
                    source_ip=action.get("source_ip"),
                    tenant_id=action.get("tenant_id"),
                    workspace_id=action.get("workspace_id"),
                    worker_id=action.get("worker_id"),
                    session_id=action.get("session_id"),
                    grant_id=action.get("grant_id"),
                    issue_id=action.get("issue_id"),
                    action_type=str(action["action_type"]),
                    dry_run=bool(action["dry_run"]),
                    details=dict(action.get("details") or {}),
                )
                for action in actions
            ],
        ),
    )


def build_worker_admin_auth_rejection_projection(
    repository: ControlPlaneRepository,
    *,
    tenant_id: str | None,
    workspace_id: str | None,
    operator_id: str | None,
    operator_role: str | None,
    token_id: str | None,
    route_path: str | None,
    limit: int,
) -> WorkerAdminAuthRejectionProjectionEnvelope:
    repository.initialize()
    generated_at = now_local()
    cursor, projection_version = repository.get_cursor_and_version()
    trusted_proxy_ids = list(get_settings().worker_admin_trusted_proxy_ids)
    rejections = repository.list_worker_admin_auth_rejection_logs(
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        operator_id=operator_id,
        operator_role=operator_role,
        token_id=token_id,
        route_path=route_path,
        limit=limit,
    )
    return WorkerAdminAuthRejectionProjectionEnvelope(
        schema_version=SCHEMA_VERSION,
        generated_at=generated_at,
        projection_version=projection_version,
        cursor=cursor,
        data=WorkerAdminAuthRejectionProjectionData(
            summary=WorkerAdminAuthRejectionProjectionSummary(
                count=len(rejections),
                trusted_proxy_enforced=bool(trusted_proxy_ids),
                trusted_proxy_ids=trusted_proxy_ids,
            ),
            filters=WorkerAdminAuthRejectionProjectionFilters(
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                operator_id=operator_id,
                operator_role=operator_role,
                token_id=token_id,
                route_path=route_path,
                limit=limit,
            ),
            rejections=[
                WorkerAdminAuthRejectionProjectionItem(
                    occurred_at=rejection["occurred_at"],
                    route_path=str(rejection["route_path"]),
                    reason_code=str(rejection["reason_code"]),
                    operator_id=rejection.get("operator_id"),
                    operator_role=rejection.get("operator_role"),
                    token_id=rejection.get("token_id"),
                    trusted_proxy_id=rejection.get("trusted_proxy_id"),
                    source_ip=rejection.get("source_ip"),
                    tenant_id=rejection.get("tenant_id"),
                    workspace_id=rejection.get("workspace_id"),
                )
                for rejection in rejections
            ],
        ),
    )
