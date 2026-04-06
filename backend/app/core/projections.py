from __future__ import annotations

import json
from datetime import datetime
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
    CEOShadowProjectionData,
    CEOShadowExecutedActionProjection,
    CEOShadowProjectionEnvelope,
    CEOShadowRunProjection,
    CEOShadowValidatedActionProjection,
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
    MeetingDetailProjectionData,
    MeetingDecisionRecordProjection,
    MeetingDetailProjectionEnvelope,
    MeetingParticipantProjection,
    MeetingRoundProjection,
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
    StaffingHireTemplateProjection,
    WorkforceActionProjection,
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
from app.core.artifact_store import ArtifactStore
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
    EMPLOYEE_STATE_ACTIVE,
    EMPLOYEE_STATE_FROZEN,
    EMPLOYEE_STATE_REPLACED,
    SCHEMA_VERSION,
    TICKET_STATUS_BLOCKED_FOR_BOARD_REVIEW,
    TICKET_STATUS_COMPLETED,
)
from app.core.developer_inspector import DeveloperInspectorStore
from app.core.governance_templates import (
    list_role_template_catalog_entries,
    list_role_template_document_kinds,
    list_role_template_fragments,
    role_template_source_for_worker,
)
from app.core.output_schemas import DELIVERY_CLOSEOUT_PACKAGE_SCHEMA_REF
from app.core.workflow_relationships import (
    list_workflow_ticket_snapshots,
    resolve_display_ticket_spec as _shared_resolve_display_ticket_spec,
    resolve_logical_ticket_id as _shared_resolve_logical_ticket_id,
    resolve_phase_label as _shared_resolve_phase_label,
)
from app.core.staffing_catalog import (
    list_mainline_staffing_hire_templates,
    mainline_staffing_template_id_for_role,
)
from app.core.runtime_provider_config import (
    FUTURE_ROLE_BINDING_SLOTS,
    RuntimeProviderConfigStore,
    count_configured_workers,
    find_provider_entry,
    mask_api_key,
    resolve_runtime_provider_config,
    runtime_target_label,
    runtime_provider_effective_mode,
    runtime_provider_health_details,
    runtime_provider_health_summary,
)
from app.core.time import now_local
from app.core.worker_scope_ops import (
    list_auth_rejections,
    list_binding_admin_views,
    list_delivery_grants,
    list_sessions,
)
from app.db.repository import ControlPlaneRepository

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
    health_summary = runtime_provider_health_summary(config, repository)
    default_provider = find_provider_entry(config, config.default_provider_id)
    return RuntimeProviderProjectionData(
        mode=(
            "DETERMINISTIC"
            if default_provider is None
            else (
                "OPENAI_COMPAT"
                if default_provider.adapter_kind == "openai_compat"
                else "CLAUDE_CODE_CLI"
            )
        ),
        effective_mode=effective_mode,
        provider_health_summary=health_summary,
        provider_id=default_provider.provider_id if default_provider is not None else None,
        base_url=default_provider.base_url if default_provider is not None else None,
        model=default_provider.model if default_provider is not None else None,
        timeout_sec=default_provider.timeout_sec if default_provider is not None else 30.0,
        reasoning_effort=default_provider.reasoning_effort if default_provider is not None else None,
        api_key_configured=bool(default_provider.api_key) if default_provider is not None else False,
        api_key_masked=mask_api_key(default_provider.api_key) if default_provider is not None else None,
        configured_worker_count=(
            count_configured_workers(repository, provider_id=default_provider.provider_id)
            if default_provider is not None
            else 0
        ),
        effective_reason=effective_reason,
        default_provider_id=config.default_provider_id,
        providers=[
            {
                "provider_id": provider.provider_id,
                "adapter_kind": provider.adapter_kind,
                "label": provider.label,
                "enabled": provider.enabled,
                "base_url": provider.base_url,
                "api_key_configured": bool(provider.api_key),
                "api_key_masked": mask_api_key(provider.api_key),
                "model": provider.model,
                "timeout_sec": provider.timeout_sec,
                "reasoning_effort": provider.reasoning_effort,
                "command_path": provider.command_path,
                "capability_tags": [tag.value for tag in provider.capability_tags],
                "fallback_provider_ids": list(provider.fallback_provider_ids),
                "health_status": runtime_provider_health_details(provider, repository)[0],
                "health_reason": runtime_provider_health_details(provider, repository)[1],
                "configured_worker_count": count_configured_workers(repository, provider_id=provider.provider_id),
                "is_default": provider.provider_id == config.default_provider_id,
            }
            for provider in config.providers
        ],
        role_bindings=[
            {
                "target_ref": binding.target_ref,
                "target_label": runtime_target_label(binding.target_ref),
                "provider_id": binding.provider_id,
                "model": binding.model,
            }
            for binding in config.role_bindings
        ],
        future_binding_slots=list(FUTURE_ROLE_BINDING_SLOTS),
    )


def _build_workforce_hire_templates() -> list[StaffingHireTemplateProjection]:
    return [
        StaffingHireTemplateProjection(
            template_id=str(template["template_id"]),
            label=str(template["label"]),
            role_type=str(template["role_type"]),
            role_profile_refs=list(template.get("role_profile_refs") or []),
            employee_id_hint=str(template["employee_id_hint"]),
            provider_id=template.get("provider_id"),
            request_summary=str(template["request_summary"]),
            skill_profile=dict(template.get("skill_profile") or {}),
            personality_profile=dict(template.get("personality_profile") or {}),
            aesthetic_profile=dict(template.get("aesthetic_profile") or {}),
        )
        for template in list_mainline_staffing_hire_templates()
    ]


def _build_role_templates_catalog_projection() -> dict[str, Any]:
    return {
        "role_templates": [
            {
                "template_id": str(template["template_id"]),
                "template_kind": str(template["template_kind"]),
                "label": str(template["label"]),
                "role_family": str(template["role_family"]),
                "role_type": str(template["role_type"]),
                "canonical_role_ref": str(template["canonical_role_ref"]),
                "alias_role_profile_refs": list(template.get("alias_role_profile_refs") or []),
                "provider_target_ref": str(template["provider_target_ref"]),
                "participation_mode": str(template["participation_mode"]),
                "execution_boundary": str(template["execution_boundary"]),
                "status": str(template["status"]),
                "default_document_kind_refs": list(template.get("default_document_kind_refs") or []),
                "responsibility_summary": str(template["responsibility_summary"]),
                "summary": str(template["summary"]),
                "composition": {
                    "fragment_refs": list((template.get("composition") or {}).get("fragment_refs") or []),
                },
            }
            for template in list_role_template_catalog_entries()
        ],
        "document_kinds": [
            {
                "kind_ref": str(kind["kind_ref"]),
                "label": str(kind["label"]),
                "summary": str(kind["summary"]),
            }
            for kind in list_role_template_document_kinds()
        ],
        "fragments": [
            {
                "fragment_id": str(fragment["fragment_id"]),
                "fragment_kind": str(fragment["fragment_kind"]),
                "label": str(fragment["label"]),
                "summary": str(fragment["summary"]),
                "payload": dict(fragment.get("payload") or {}),
            }
            for fragment in list_role_template_fragments()
        ],
    }


def _build_workforce_available_actions(employee: dict[str, Any]) -> list[WorkforceActionProjection]:
    state = str(employee.get("state") or "UNKNOWN").strip().upper()
    role_type = str(employee.get("role_type") or "").strip()
    template_id = mainline_staffing_template_id_for_role(role_type)

    if state == EMPLOYEE_STATE_ACTIVE:
        replace_enabled = template_id is not None
        return [
            WorkforceActionProjection(action_type="FREEZE", enabled=True, disabled_reason=None, template_id=None),
            WorkforceActionProjection(
                action_type="RESTORE",
                enabled=False,
                disabled_reason="Only frozen workers can be restored.",
                template_id=None,
            ),
            WorkforceActionProjection(
                action_type="REPLACE",
                enabled=replace_enabled,
                disabled_reason=(
                    None
                    if replace_enabled
                    else "No supported replacement template exists on the current local MVP staffing path."
                ),
                template_id=template_id,
            ),
        ]

    if state == EMPLOYEE_STATE_FROZEN:
        return [
            WorkforceActionProjection(
                action_type="FREEZE",
                enabled=False,
                disabled_reason="Only active workers can be frozen.",
                template_id=None,
            ),
            WorkforceActionProjection(action_type="RESTORE", enabled=True, disabled_reason=None, template_id=None),
            WorkforceActionProjection(
                action_type="REPLACE",
                enabled=False,
                disabled_reason="Only active workers can be replaced.",
                template_id=template_id,
            ),
        ]

    if state == EMPLOYEE_STATE_REPLACED:
        return [
            WorkforceActionProjection(
                action_type="FREEZE",
                enabled=False,
                disabled_reason="Replaced workers cannot be frozen again.",
                template_id=None,
            ),
            WorkforceActionProjection(
                action_type="RESTORE",
                enabled=False,
                disabled_reason="Replaced workers cannot be restored.",
                template_id=None,
            ),
            WorkforceActionProjection(
                action_type="REPLACE",
                enabled=False,
                disabled_reason="Replaced workers cannot be replaced again.",
                template_id=template_id,
            ),
        ]

    return [
        WorkforceActionProjection(
            action_type="FREEZE",
            enabled=False,
            disabled_reason="This worker is not on an actionable employment state.",
            template_id=None,
        ),
        WorkforceActionProjection(
            action_type="RESTORE",
            enabled=False,
            disabled_reason="This worker is not on an actionable employment state.",
            template_id=None,
        ),
        WorkforceActionProjection(
            action_type="REPLACE",
            enabled=False,
            disabled_reason="This worker is not on an actionable employment state.",
            template_id=template_id,
        ),
    ]


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

        final_review_row = connection.execute(
            """
            SELECT * FROM approval_projection
            WHERE workflow_id = ? AND status = ? AND approval_type = ?
            ORDER BY resolved_at DESC, updated_at DESC, approval_id DESC
            LIMIT 1
            """,
            (workflow_id, "APPROVED", "VISUAL_MILESTONE"),
        ).fetchone()
        if final_review_row is None:
            return None

        closeout_ticket: dict[str, Any] | None = None
        for ticket in repository.list_ticket_projections_by_statuses(connection, [TICKET_STATUS_COMPLETED]):
            if ticket["workflow_id"] != workflow_id:
                continue
            created_spec = repository.get_latest_ticket_created_payload(connection, ticket["ticket_id"])
            if (
                created_spec is not None
                and str(created_spec.get("output_schema_ref") or "") == DELIVERY_CLOSEOUT_PACKAGE_SCHEMA_REF
            ):
                closeout_ticket = ticket
        if closeout_ticket is None:
            return None

        closeout_terminal_event = repository.get_latest_ticket_terminal_event(
            connection,
            str(closeout_ticket["ticket_id"]),
        )
        if closeout_terminal_event is None:
            return None

    if final_review_row is None:
        return None

    approval = repository._convert_approval_row(final_review_row)
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
    closeout_payload = closeout_terminal_event.get("payload") or {}
    closeout_completed_at = closeout_terminal_event.get("occurred_at")
    if closeout_completed_at is None:
        return None
    (
        documentation_sync_summary,
        documentation_update_count,
        documentation_follow_up_count,
    ) = _summarize_closeout_documentation_updates(closeout_payload.get("documentation_updates"))

    return DashboardCompletionSummaryProjection(
        workflow_id=workflow_id,
        final_review_pack_id=str(approval["review_pack_id"]),
        approved_at=resolved_at,
        final_review_approved_at=resolved_at,
        closeout_completed_at=closeout_completed_at,
        closeout_ticket_id=str(closeout_ticket["ticket_id"]),
        title=str(subject.get("title") or review_pack.get("title") or approval["review_pack_id"]),
        summary=str(
            closeout_payload.get("completion_summary")
            or recommendation.get("summary")
            or resolution.get("board_comment")
            or ""
        ),
        selected_option_id=selected_option_id,
        board_comment=resolution.get("board_comment"),
        artifact_refs=list((selected_option or {}).get("artifact_refs") or []),
        closeout_artifact_refs=list(closeout_payload.get("artifact_refs") or []),
        documentation_sync_summary=documentation_sync_summary,
        documentation_update_count=documentation_update_count,
        documentation_follow_up_count=documentation_follow_up_count,
    )


def _summarize_closeout_documentation_updates(documentation_updates: Any) -> tuple[str | None, int, int]:
    if not isinstance(documentation_updates, list) or not documentation_updates:
        return None, 0, 0

    documentation_update_count = 0
    documentation_follow_up_count = 0
    for item in documentation_updates:
        if not isinstance(item, dict):
            continue
        doc_ref = str(item.get("doc_ref") or "").strip()
        status = str(item.get("status") or "").strip()
        summary = str(item.get("summary") or "").strip()
        if not doc_ref or not status or not summary:
            continue
        documentation_update_count += 1
        if status == "FOLLOW_UP_REQUIRED":
            documentation_follow_up_count += 1

    if documentation_update_count == 0:
        return None, 0, 0

    update_label = "update" if documentation_update_count == 1 else "updates"
    follow_up_label = "item" if documentation_follow_up_count == 1 else "items"
    summary = (
        f"{documentation_update_count} documentation {update_label} recorded; "
        f"{documentation_follow_up_count} follow-up {follow_up_label}."
    )
    return summary, documentation_update_count, documentation_follow_up_count


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
    return _shared_resolve_phase_label(created_spec)


def _resolve_display_ticket_spec(created_spec: dict[str, Any] | None) -> dict[str, Any] | None:
    return _shared_resolve_display_ticket_spec(created_spec)


def _resolve_logical_ticket_id(
    created_spec: dict[str, Any] | None,
    display_spec: dict[str, Any] | None,
    latest_ticket_id: str,
) -> str:
    return _shared_resolve_logical_ticket_id(created_spec, display_spec, latest_ticket_id)


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
        for snapshot in list_workflow_ticket_snapshots(repository, workflow_id, connection=connection):
            approval = approval_by_node_id.get(snapshot.node_id)
            incident = incident_by_node_id.get(snapshot.node_id)
            raw_nodes.append(
                {
                    "node_id": snapshot.node_id,
                    "ticket_id": snapshot.ticket_id,
                    "parent_ticket_id": snapshot.parent_ticket_id,
                    "phase": snapshot.phase,
                    "delivery_stage": snapshot.delivery_stage,
                    "node_status": snapshot.node_status,
                    "ticket_status": snapshot.ticket_status,
                    "role_profile_ref": snapshot.role_profile_ref,
                    "output_schema_ref": snapshot.output_schema_ref,
                    "lease_owner": snapshot.lease_owner,
                    "expected_artifact_scope": list(snapshot.expected_artifact_scope),
                    "open_review_pack_id": approval.get("review_pack_id") if approval is not None else None,
                    "open_incident_id": incident.get("incident_id") if incident is not None else None,
                    "sort_key": (
                        snapshot.sort_updated_at,
                        snapshot.ticket_id or snapshot.node_id,
                    ),
                }
            )
            if snapshot.ticket_id and snapshot.ticket_status:
                current_ticket_status_by_logical_id[snapshot.ticket_id] = snapshot.ticket_status

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
        source_template = role_template_source_for_worker(
            role_type=role_type,
            role_profile_ref=str(ticket.get("role_profile_ref") or "") if ticket is not None else None,
        )

        lane["workers"].append(
            WorkforceWorkerProjection(
                employee_id=employee_id,
                role_type=role_type,
                employment_state=state,
                activity_state=activity_state,
                current_ticket_id=str(ticket.get("ticket_id")) if ticket is not None else None,
                current_node_id=str(ticket.get("node_id")) if ticket is not None else None,
                provider_id=employee.get("provider_id"),
                skill_profile=dict(employee.get("skill_profile_json") or {}),
                personality_profile=dict(employee.get("personality_profile_json") or {}),
                aesthetic_profile=dict(employee.get("aesthetic_profile_json") or {}),
                profile_summary=str(employee.get("profile_summary") or ""),
                source_template_id=(
                    str(source_template.get("template_id")) if source_template is not None else None
                ),
                source_fragment_refs=list((source_template.get("composition") or {}).get("fragment_refs") or []),
                last_update_at=employee.get("updated_at"),
                available_actions=_build_workforce_available_actions(employee),
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
        data=WorkforceProjectionData(
            summary=summary,
            hire_templates=_build_workforce_hire_templates(),
            role_templates_catalog=_build_role_templates_catalog_projection(),
            role_lanes=role_lanes,
        ),
    )


def build_ceo_shadow_projection(
    repository: ControlPlaneRepository,
    workflow_id: str,
    *,
    limit: int = 20,
) -> CEOShadowProjectionEnvelope | None:
    repository.initialize()
    workflow = repository.get_workflow_projection(workflow_id)
    if workflow is None:
        return None

    cursor, projection_version = repository.get_cursor_and_version()
    runs = repository.list_ceo_shadow_runs(workflow_id, limit=limit)
    return CEOShadowProjectionEnvelope(
        schema_version=SCHEMA_VERSION,
        generated_at=now_local(),
        projection_version=projection_version,
        cursor=cursor,
        data=CEOShadowProjectionData(
            workflow_id=workflow_id,
            runs=[
                CEOShadowRunProjection(
                    run_id=str(run["run_id"]),
                    occurred_at=run["occurred_at"],
                    trigger_type=str(run["trigger_type"]),
                    trigger_ref=run.get("trigger_ref"),
                    effective_mode=str(run["effective_mode"]),
                    provider_health_summary=str(run["provider_health_summary"]),
                    model=run.get("model"),
                    prompt_version=str(run["prompt_version"]),
                    provider_response_id=run.get("provider_response_id"),
                    fallback_reason=run.get("fallback_reason"),
                    proposed_action_batch=dict(run.get("proposed_action_batch") or {}),
                    accepted_actions=[
                        CEOShadowValidatedActionProjection(
                            action_type=str(item["action_type"]),
                            payload=dict(item.get("payload") or {}),
                            reason=str(item["reason"]),
                        )
                        for item in run.get("accepted_actions") or []
                    ],
                    rejected_actions=[
                        CEOShadowValidatedActionProjection(
                            action_type=str(item["action_type"]),
                            payload=dict(item.get("payload") or {}),
                            reason=str(item["reason"]),
                        )
                        for item in run.get("rejected_actions") or []
                    ],
                    executed_actions=[
                        CEOShadowExecutedActionProjection(
                            action_type=str(item["action_type"]),
                            payload=dict(item.get("payload") or {}),
                            execution_status=str(item.get("execution_status") or "UNKNOWN"),
                            reason=str(item.get("reason") or ""),
                            command_status=(
                                str(item["command_status"])
                                if item.get("command_status") is not None
                                else None
                            ),
                            causation_hint=(
                                str(item["causation_hint"])
                                if item.get("causation_hint") is not None
                                else None
                            ),
                        )
                        for item in run.get("executed_actions") or []
                    ],
                    execution_summary=dict(run.get("execution_summary") or {}),
                    deterministic_fallback_used=bool(run.get("deterministic_fallback_used")),
                    deterministic_fallback_reason=(
                        str(run["deterministic_fallback_reason"])
                        if run.get("deterministic_fallback_reason") is not None
                        else None
                    ),
                    comparison=dict(run.get("comparison") or {}),
                )
                for run in runs
            ],
        ),
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
    provider_health_summary = (
        "PAUSED" if open_provider_incidents > 0 else runtime_provider.provider_health_summary
    )
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
                provider_health_summary=provider_health_summary,
            ),
            runtime_status=DashboardRuntimeStatusProjection(
                effective_mode=runtime_provider.effective_mode,
                provider_label=(
                    "OpenAI Compat"
                    if runtime_provider.mode == "OPENAI_COMPAT"
                    else ("Claude Code CLI" if runtime_provider.mode == "CLAUDE_CODE_CLI" else "Local Deterministic")
                ),
                model=runtime_provider.model,
                configured_worker_count=runtime_provider.configured_worker_count,
                provider_health_summary=provider_health_summary,
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
    for meeting in repository.list_open_meeting_projections():
        items.append(
            InboxItemProjection(
                inbox_item_id=f"inbox_{meeting['meeting_id']}",
                workflow_id=str(meeting["workflow_id"]),
                item_type="MEETING_ROOM",
                priority="high",
                status=str(meeting["status"]),
                created_at=meeting["opened_at"],
                sla_due_at=None,
                title=f"Technical decision meeting: {meeting['topic']}",
                summary=(
                    "Open the meeting room to inspect the current topic, participants, and round-by-round summary."
                ),
                source_ref=str(meeting["meeting_id"]),
                route_target=RouteTarget(
                    view="meeting_room",
                    meeting_id=str(meeting["meeting_id"]),
                ),
                badges=["meeting", "technical_decision"],
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


def _load_meeting_decision_record(
    repository: ControlPlaneRepository,
    *,
    source_ticket_id: str,
    artifact_store: ArtifactStore | None,
) -> MeetingDecisionRecordProjection | None:
    if artifact_store is None:
        return None

    artifact_ref = f"art://runtime/{source_ticket_id}/consensus-document.json"
    artifact = repository.get_artifact_by_ref(artifact_ref)
    if artifact is None:
        return None

    storage_relpath = artifact.get("storage_relpath")
    if not isinstance(storage_relpath, str) or not storage_relpath.strip():
        return None

    try:
        payload = json.loads(artifact_store.read_bytes(storage_relpath).decode("utf-8"))
    except (FileNotFoundError, OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None

    raw_record = payload.get("decision_record")
    if not isinstance(raw_record, dict):
        return None

    try:
        return MeetingDecisionRecordProjection.model_validate(raw_record)
    except Exception:
        return None


def build_meeting_projection(
    repository: ControlPlaneRepository,
    meeting_id: str,
    artifact_store: ArtifactStore | None = None,
) -> MeetingDetailProjectionEnvelope | None:
    repository.initialize()
    meeting = repository.get_meeting_projection(meeting_id)
    if meeting is None:
        return None

    cursor, projection_version = repository.get_cursor_and_version()
    rounds = [
        MeetingRoundProjection(
            round_type=str(item.get("round_type") or ""),
            round_index=int(item.get("round_index") or 0),
            summary=str(item.get("summary") or ""),
            notes=list(item.get("notes") or []),
            completed_at=(
                datetime.fromisoformat(str(item["completed_at"]))
                if not isinstance(item.get("completed_at"), datetime)
                else item["completed_at"]
            ),
        )
        for item in meeting.get("rounds") or []
    ]
    participants = [
        MeetingParticipantProjection(
            employee_id=str(item.get("employee_id") or ""),
            role_type=str(item.get("role_type") or ""),
            meeting_responsibility=str(item.get("meeting_responsibility") or ""),
            is_recorder=bool(item.get("is_recorder")),
        )
        for item in meeting.get("participants") or []
    ]
    decision_record = _load_meeting_decision_record(
        repository,
        source_ticket_id=str(meeting["source_ticket_id"]),
        artifact_store=artifact_store,
    )
    return MeetingDetailProjectionEnvelope(
        schema_version=SCHEMA_VERSION,
        generated_at=now_local(),
        projection_version=projection_version,
        cursor=cursor,
        data=MeetingDetailProjectionData(
            meeting_id=str(meeting["meeting_id"]),
            workflow_id=str(meeting["workflow_id"]),
            meeting_type=str(meeting["meeting_type"]),
            topic=str(meeting["topic"]),
            status=str(meeting["status"]),
            review_status=(
                str(meeting["review_status"]) if meeting.get("review_status") is not None else None
            ),
            source_ticket_id=str(meeting["source_ticket_id"]),
            source_node_id=str(meeting["source_node_id"]),
            review_pack_id=(
                str(meeting["review_pack_id"]) if meeting.get("review_pack_id") is not None else None
            ),
            opened_at=meeting["opened_at"],
            updated_at=meeting["updated_at"],
            closed_at=meeting.get("closed_at"),
            current_round=(str(meeting["current_round"]) if meeting.get("current_round") else None),
            recorder_employee_id=str(meeting["recorder_employee_id"]),
            participants=participants,
            rounds=rounds,
            consensus_summary=(
                str(meeting["consensus_summary"]) if meeting.get("consensus_summary") is not None else None
            ),
            no_consensus_reason=(
                str(meeting["no_consensus_reason"]) if meeting.get("no_consensus_reason") is not None else None
            ),
            decision_record=decision_record,
        ),
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
    bindings = list_binding_admin_views(
        worker_id=worker_id,
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        repository=repository,
    )
    sessions = list_sessions(
        repository=repository,
        worker_id=worker_id,
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        active_only=active_only,
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
            is_active=bool(session.get("is_active")),
        )
        for session in sessions
    ]

    grants = list_delivery_grants(
        repository=repository,
        worker_id=worker_id,
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        active_only=active_only,
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
            is_active=bool(grant.get("is_active")),
        )
        for grant in grants
    ]
    grant_items = grant_items[:grant_limit]

    rejections = list_auth_rejections(
        repository=repository,
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
        for rejection in rejections[:rejection_limit]
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
