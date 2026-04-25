from __future__ import annotations

import fnmatch
import hashlib
import json
import sqlite3
from datetime import datetime, timedelta
from typing import Any

from app.config import get_settings
from app.contracts.commands import (
    CommandAckEnvelope,
    CommandAckStatus,
    DeveloperInspectorRefs,
    IncidentFollowupAction,
    IncidentResolveCommand,
    SchedulerWorkerCandidate,
    SchedulerTickCommand,
    TicketBoardReviewRequest,
    TicketCancelCommand,
    TicketCompletedCommand,
    TicketCreateCommand,
    TicketFailCommand,
    TicketGitCommitRecord,
    TicketHeartbeatCommand,
    TicketLeaseCommand,
    TicketResultStatus,
    TicketResultSubmitCommand,
    TicketWrittenArtifact,
    TicketStartCommand,
)
from app.core.artifact_store import ArtifactStore, MaterializedArtifact, normalize_artifact_logical_path
from app.core.artifacts import (
    ARTIFACT_LIFECYCLE_ACTIVE,
    ARTIFACT_RETENTION_PERSISTENT,
    is_binary_artifact_kind,
)
from app.core.constants import (
    CIRCUIT_BREAKER_STATE_CLOSED,
    CIRCUIT_BREAKER_STATE_OPEN,
    DEFAULT_LEASE_TIMEOUT_SEC,
    DEFAULT_REPEAT_FAILURE_THRESHOLD,
    DEFAULT_TIMEOUT_BACKOFF_CAP_MULTIPLIER,
    DEFAULT_TIMEOUT_BACKOFF_MULTIPLIER,
    DEFAULT_TIMEOUT_REPEAT_THRESHOLD,
    EMPLOYEE_STATE_ACTIVE,
    EVENT_CIRCUIT_BREAKER_CLOSED,
    EVENT_CIRCUIT_BREAKER_OPENED,
    EVENT_INCIDENT_CLOSED,
    EVENT_INCIDENT_RECOVERY_STARTED,
    EVENT_INCIDENT_OPENED,
    EVENT_TICKET_CANCELLED,
    EVENT_TICKET_CANCEL_REQUESTED,
    EVENT_TICKET_COMPLETED,
    EVENT_TICKET_CREATED,
    EVENT_TICKET_EXECUTION_PRECONDITION_BLOCKED,
    EVENT_TICKET_EXECUTION_PRECONDITION_CLEARED,
    EVENT_TICKET_FAILED,
    EVENT_TICKET_HEARTBEAT_RECORDED,
    EVENT_TICKET_LEASED,
    EVENT_TICKET_RETRY_SCHEDULED,
    EVENT_TICKET_STARTED,
    EVENT_TICKET_TIMED_OUT,
    FAILURE_KIND_PROVIDER_RATE_LIMITED,
    FAILURE_KIND_UPSTREAM_UNAVAILABLE,
    INCIDENT_TYPE_BOARD_ADVISORY_ANALYSIS_FAILED,
    INCIDENT_TYPE_DECOMPOSITION_RECOVERY,
    INCIDENT_TYPE_REPEATED_FAILURE_ESCALATION,
    INCIDENT_TYPE_MAKER_CHECKER_REWORK_ESCALATION,
    INCIDENT_TYPE_CEO_SHADOW_PIPELINE_FAILED,
    INCIDENT_TYPE_GRAPH_HEALTH_CRITICAL,
    INCIDENT_TYPE_PLANNED_PLACEHOLDER_GATE_BLOCKED,
    INCIDENT_TYPE_RUNTIME_LIVENESS_CRITICAL,
    INCIDENT_TYPE_RUNTIME_LIVENESS_UNAVAILABLE,
    INCIDENT_TYPE_REQUIRED_HOOK_GATE_BLOCKED,
    INCIDENT_TYPE_STAFFING_CONTAINMENT,
    INCIDENT_TYPE_TICKET_GRAPH_UNAVAILABLE,
    INCIDENT_STATUS_CLOSED,
    INCIDENT_STATUS_OPEN,
    INCIDENT_STATUS_RECOVERING,
    INCIDENT_TYPE_PROVIDER_EXECUTION_PAUSED,
    INCIDENT_TYPE_RUNTIME_TIMEOUT_ESCALATION,
    NODE_STATUS_CANCEL_REQUESTED,
    NODE_STATUS_CANCELLED,
    NODE_STATUS_COMPLETED,
    NODE_STATUS_EXECUTING,
    NODE_STATUS_PENDING,
    NODE_STATUS_REWORK_REQUIRED,
    PROVIDER_FINGERPRINT_PREFIX,
    PROVIDER_PAUSE_FAILURE_KINDS,
    TICKET_STATUS_EXECUTING,
    TICKET_STATUS_LEASED,
    TICKET_STATUS_PENDING,
    TICKET_STATUS_CANCEL_REQUESTED,
    TICKET_STATUS_CANCELLED,
    TICKET_STATUS_BLOCKED_FOR_BOARD_REVIEW,
    TICKET_STATUS_COMPLETED,
    TICKET_STATUS_FAILED,
    TICKET_STATUS_REWORK_REQUIRED,
    TICKET_STATUS_TIMED_OUT,
    TIMEOUT_FAMILY_RUNTIME,
    BLOCKING_REASON_PROVIDER_REQUIRED,
)
from app.core.context_compiler import export_latest_compile_artifacts_to_developer_inspector
from app.core.board_advisory_analysis import (
    create_board_advisory_analysis_run,
    run_board_advisory_analysis,
)
from app.core.ceo_scheduler import (
    CeoShadowPipelineError,
    SCHEDULER_IDLE_MAINTENANCE_TRIGGER,
    is_ticket_graph_unavailable_error,
    run_ceo_shadow_for_trigger,
    trigger_ceo_shadow_with_recovery,
)
from app.core.ceo_execution_presets import build_internal_governance_review_request
from app.core.decomposition import build_decomposition_recovery_plan, build_decomposition_ticket_specs
from app.core.developer_inspector import DeveloperInspectorStore, PersistedDeveloperInspectorArtifact
from app.core.execution_targets import (
    employee_supports_execution_contract,
    infer_execution_contract_payload,
    resolve_execution_target_ref_from_ticket_spec,
)
from app.core.incident_followups import resolve_ceo_shadow_source_ticket_context
from app.core.graph_identity import (
    GRAPH_LANE_EXECUTION,
    resolve_ticket_graph_identity,
)
from app.core.planned_placeholder_gate import PlannedPlaceholderGateBlock
from app.core.ids import new_prefixed_id
from app.core.output_schemas import (
    ARCHITECTURE_BRIEF_SCHEMA_REF,
    ARCHITECTURE_BRIEF_SCHEMA_VERSION,
    BACKLOG_RECOMMENDATION_SCHEMA_REF,
    BACKLOG_RECOMMENDATION_SCHEMA_VERSION,
    CONSENSUS_DOCUMENT_SCHEMA_REF,
    CONSENSUS_DOCUMENT_SCHEMA_VERSION,
    DETAILED_DESIGN_SCHEMA_REF,
    DETAILED_DESIGN_SCHEMA_VERSION,
    DELIVERY_CLOSEOUT_PACKAGE_SCHEMA_REF,
    DELIVERY_CLOSEOUT_PACKAGE_SCHEMA_VERSION,
    DELIVERY_CHECK_REPORT_SCHEMA_REF,
    DELIVERY_CHECK_REPORT_SCHEMA_VERSION,
    MAKER_CHECKER_VERDICT_SCHEMA_REF,
    MAKER_CHECKER_VERDICT_SCHEMA_VERSION,
    MILESTONE_PLAN_SCHEMA_REF,
    MILESTONE_PLAN_SCHEMA_VERSION,
    OutputSchemaValidationError,
    SOURCE_CODE_DELIVERY_SCHEMA_REF,
    SOURCE_CODE_DELIVERY_SCHEMA_VERSION,
    TECHNOLOGY_DECISION_SCHEMA_REF,
    TECHNOLOGY_DECISION_SCHEMA_VERSION,
    UI_MILESTONE_REVIEW_SCHEMA_REF,
    UI_MILESTONE_REVIEW_SCHEMA_VERSION,
    build_backlog_recommendation_artifact_path,
    build_backlog_recommendation_artifact_ref,
    validate_output_payload,
)
from app.core.process_assets import (
    build_closeout_summary_process_asset_ref,
    build_compiled_context_bundle_process_asset_ref,
    build_compiled_execution_package_process_asset_ref,
    build_compile_manifest_process_asset_ref,
    build_governance_document_process_asset_ref,
    build_meeting_decision_process_asset_ref,
    build_result_process_assets,
    build_source_code_delivery_process_asset_ref,
    dedupe_process_asset_refs,
    get_ticket_output_process_asset_refs,
    merge_input_process_asset_refs,
    parse_process_asset_ref,
)
from app.core.runtime_provider_config import (
    find_provider_entry,
    provider_effective_mode,
    resolve_provider_failover_selections,
    resolve_provider_selection,
    resolve_runtime_provider_config,
)
from app.core.project_workspaces import (
    build_effective_workspace_written_artifacts,
    bootstrap_ticket_dossier,
    commit_project_checkout,
    ensure_project_checkout,
    finalize_workspace_ticket_git_status,
    infer_ticket_workspace_bootstrap,
    is_workspace_managed_source_code_ticket,
    materialize_workspace_delivery_files,
    project_workspace_manifest_exists,
    resolve_ticket_checkout_truth,
    resolve_source_code_ticket_from_chain,
    sync_active_worktree_index,
    sync_ticket_boardroom_views,
    update_ticket_git_closeout_notes,
    write_artifact_capture_receipt,
    write_documentation_sync_receipt,
    write_worktree_checkout_receipt,
    write_evidence_capture_receipt,
    write_git_closeout_receipt,
    write_worker_postrun_receipt,
)
from app.core.runtime_node_lifecycle import (
    REASON_CODE_PLANNED_PLACEHOLDER_NOT_MATERIALIZED,
    RuntimeNodeLifecycleError,
    build_runtime_node_lifecycle_reason,
    require_materialized_runtime_node,
    resolve_runtime_node_lifecycle,
)
from app.core.runtime_node_views import (
    MATERIALIZATION_STATE_MATERIALIZED,
    MATERIALIZATION_STATE_PLANNED,
)
from app.core.role_hooks import HookGateStatus, evaluate_ticket_required_hook_gate, replay_required_hook_receipts
from app.core.ticket_graph import build_ticket_graph_snapshot
from app.core.ticket_artifacts import (
    PreparedTicketArtifact,
    cleanup_materialized_artifacts,
    match_allowed_write_set,
    prepare_written_artifacts,
    save_prepared_artifact_record,
)
from app.core.ticket_context_archive import latest_provider_audit_for_ticket, write_ticket_context_markdown
from app.core.time import now_local
from app.core.workflow_autopilot import workflow_uses_ceo_board_delegate
from app.core.workflow_scope import resolve_workflow_scope
from app.core.workspace_path_contracts import (
    is_workspace_managed_write_set,
    rebind_ticket_id_in_allowed_write_set,
)
from app.db.repository import ControlPlaneRepository


MAKER_CHECKER_REVIEW_TICKET_KIND = "MAKER_CHECKER_REVIEW"
MAKER_REWORK_FIX_TICKET_KIND = "MAKER_REWORK_FIX"
GOVERNANCE_DOCUMENT_REVIEW_TARGETS = {
    ("INTERNAL_GOVERNANCE_REVIEW", ARCHITECTURE_BRIEF_SCHEMA_REF, ARCHITECTURE_BRIEF_SCHEMA_VERSION),
    ("INTERNAL_GOVERNANCE_REVIEW", TECHNOLOGY_DECISION_SCHEMA_REF, TECHNOLOGY_DECISION_SCHEMA_VERSION),
    ("INTERNAL_GOVERNANCE_REVIEW", MILESTONE_PLAN_SCHEMA_REF, MILESTONE_PLAN_SCHEMA_VERSION),
    ("INTERNAL_GOVERNANCE_REVIEW", DETAILED_DESIGN_SCHEMA_REF, DETAILED_DESIGN_SCHEMA_VERSION),
    ("INTERNAL_GOVERNANCE_REVIEW", BACKLOG_RECOMMENDATION_SCHEMA_REF, BACKLOG_RECOMMENDATION_SCHEMA_VERSION),
}
GOVERNANCE_DOCUMENT_SCHEMA_REFS = {
    ARCHITECTURE_BRIEF_SCHEMA_REF,
    TECHNOLOGY_DECISION_SCHEMA_REF,
    MILESTONE_PLAN_SCHEMA_REF,
    DETAILED_DESIGN_SCHEMA_REF,
    BACKLOG_RECOMMENDATION_SCHEMA_REF,
}
MAKER_CHECKER_SUPPORTED_TARGETS = {
    ("VISUAL_MILESTONE", UI_MILESTONE_REVIEW_SCHEMA_REF, UI_MILESTONE_REVIEW_SCHEMA_VERSION),
    (
        "MEETING_ESCALATION",
        CONSENSUS_DOCUMENT_SCHEMA_REF,
        CONSENSUS_DOCUMENT_SCHEMA_VERSION,
    ),
    (
        "INTERNAL_DELIVERY_REVIEW",
        SOURCE_CODE_DELIVERY_SCHEMA_REF,
        SOURCE_CODE_DELIVERY_SCHEMA_VERSION,
    ),
    (
        "INTERNAL_CHECK_REVIEW",
        DELIVERY_CHECK_REPORT_SCHEMA_REF,
        DELIVERY_CHECK_REPORT_SCHEMA_VERSION,
    ),
    (
        "INTERNAL_CLOSEOUT_REVIEW",
        DELIVERY_CLOSEOUT_PACKAGE_SCHEMA_REF,
        DELIVERY_CLOSEOUT_PACKAGE_SCHEMA_VERSION,
    ),
} | GOVERNANCE_DOCUMENT_REVIEW_TARGETS


def _match_allowed_write_set(path: str, allowed_write_set: list[str]) -> bool:
    return match_allowed_write_set(path, allowed_write_set)


def _trigger_ceo_shadow_safely(
    repository: ControlPlaneRepository,
    *,
    workflow_id: str,
    trigger_type: str,
    trigger_ref: str | None,
) -> None:
    if trigger_type == EVENT_INCIDENT_RECOVERY_STARTED:
        try:
            run_ceo_shadow_for_trigger(
                repository,
                workflow_id=workflow_id,
                trigger_type=trigger_type,
                trigger_ref=trigger_ref,
            )
        except Exception:
            return
        return
    trigger_ceo_shadow_with_recovery(
        repository,
        workflow_id=workflow_id,
        trigger_type=trigger_type,
        trigger_ref=trigger_ref,
        idempotency_key_base=f"ticket-trigger:{workflow_id}:{trigger_type}:{trigger_ref or 'none'}",
    )


def _duplicate_ack(
    *,
    command_id: str,
    idempotency_key: str,
    received_at: datetime,
    ticket_id: str,
    action: str,
) -> CommandAckEnvelope:
    return CommandAckEnvelope(
        command_id=command_id,
        idempotency_key=idempotency_key,
        status=CommandAckStatus.DUPLICATE,
        received_at=received_at,
        reason=f"An identical {action} command was already accepted.",
        causation_hint=f"ticket:{ticket_id}",
    )


def _rejected_ack(
    *,
    command_id: str,
    idempotency_key: str,
    received_at: datetime,
    ticket_id: str,
    reason: str,
) -> CommandAckEnvelope:
    return CommandAckEnvelope(
        command_id=command_id,
        idempotency_key=idempotency_key,
        status=CommandAckStatus.REJECTED,
        received_at=received_at,
        reason=reason,
        causation_hint=f"ticket:{ticket_id}",
    )


def _scheduler_duplicate_ack(
    *,
    command_id: str,
    idempotency_key: str,
    received_at: datetime,
) -> CommandAckEnvelope:
    return CommandAckEnvelope(
        command_id=command_id,
        idempotency_key=idempotency_key,
        status=CommandAckStatus.DUPLICATE,
        received_at=received_at,
        reason="An identical scheduler-tick command was already accepted.",
        causation_hint="scheduler:tick",
    )


def _incident_duplicate_ack(
    *,
    command_id: str,
    idempotency_key: str,
    received_at: datetime,
    incident_id: str,
) -> CommandAckEnvelope:
    return CommandAckEnvelope(
        command_id=command_id,
        idempotency_key=idempotency_key,
        status=CommandAckStatus.DUPLICATE,
        received_at=received_at,
        reason="An identical incident-resolve command was already accepted.",
        causation_hint=f"incident:{incident_id}",
    )


def _incident_rejected_ack(
    *,
    command_id: str,
    idempotency_key: str,
    received_at: datetime,
    incident_id: str,
    reason: str,
) -> CommandAckEnvelope:
    return CommandAckEnvelope(
        command_id=command_id,
        idempotency_key=idempotency_key,
        status=CommandAckStatus.REJECTED,
        received_at=received_at,
        reason=reason,
        causation_hint=f"incident:{incident_id}",
    )


def _cancel_duplicate_ack(
    *,
    command_id: str,
    idempotency_key: str,
    received_at: datetime,
    ticket_id: str,
) -> CommandAckEnvelope:
    return CommandAckEnvelope(
        command_id=command_id,
        idempotency_key=idempotency_key,
        status=CommandAckStatus.DUPLICATE,
        received_at=received_at,
        reason="An identical ticket-cancel command was already accepted.",
        causation_hint=f"ticket:{ticket_id}",
    )


def _prepare_ticket_artifacts(
    *,
    artifact_store: ArtifactStore | None,
    written_artifacts: list,
    created_at: datetime,
    workflow_id: str,
    ticket_id: str,
) -> tuple[list[PreparedTicketArtifact], list[MaterializedArtifact]]:
    return prepare_written_artifacts(
        artifact_store=artifact_store,
        written_artifacts=written_artifacts,
        created_at=created_at,
        workflow_id=workflow_id,
        ticket_id=ticket_id,
    )


def _insert_ticket_cancelled_event(
    *,
    repository: ControlPlaneRepository,
    connection,
    command_id: str,
    occurred_at: datetime,
    workflow_id: str,
    ticket_id: str,
    node_id: str,
    cancelled_by: str,
    reason: str,
    idempotency_key: str,
) -> None:
    event_row = repository.insert_event(
        connection,
        event_type=EVENT_TICKET_CANCELLED,
        actor_type="operator",
        actor_id=cancelled_by,
        workflow_id=workflow_id,
        idempotency_key=idempotency_key,
        causation_id=command_id,
        correlation_id=workflow_id,
        payload={
            "ticket_id": ticket_id,
            "node_id": node_id,
            "cancelled_by": cancelled_by,
            "reason": reason,
        },
        occurred_at=occurred_at,
    )
    if event_row is None:
        raise RuntimeError("Ticket cancellation idempotency conflict.")


def _build_review_pack(
    *,
    payload: TicketCompletedCommand,
    source_graph_node_id: str,
    trigger_event_id: str,
    command_target_version: int,
    occurred_at: datetime,
) -> dict:
    review_request = payload.review_request
    if review_request is None:
        raise RuntimeError("review_request is required to build a review pack.")

    return {
        "meta": {
            "review_pack_version": 1,
            "workflow_id": payload.workflow_id,
            "review_type": review_request.review_type.value,
            "created_at": occurred_at.isoformat(),
            "priority": review_request.priority.value,
        },
        "subject": {
            "title": review_request.title,
            "subtitle": review_request.subtitle,
            "source_graph_node_id": source_graph_node_id,
            "source_ticket_id": payload.ticket_id,
            "blocking_scope": review_request.blocking_scope.value,
        },
        "trigger": {
            "trigger_event_id": trigger_event_id,
            "trigger_reason": review_request.trigger_reason,
            "why_now": review_request.why_now,
        },
        "recommendation": {
            "recommended_action": review_request.recommended_action.value,
            "recommended_option_id": review_request.recommended_option_id,
            "summary": review_request.recommendation_summary,
        },
        "options": [option.model_dump(mode="json") for option in review_request.options],
        "evidence_summary": [
            evidence.model_dump(mode="json") for evidence in review_request.evidence_summary
        ],
        "delta_summary": review_request.delta_summary,
        "maker_checker_summary": review_request.maker_checker_summary,
        "risk_summary": review_request.risk_summary,
        "budget_impact": review_request.budget_impact,
        "decision_form": {
            "allowed_actions": [action.value for action in review_request.available_actions],
            "command_target_version": command_target_version,
            "requires_comment_on_reject": True,
            "requires_constraint_patch_on_modify": True,
        },
        "developer_inspector_refs": (
            review_request.developer_inspector_refs.model_dump(mode="json", exclude_none=True)
            if review_request.developer_inspector_refs is not None
            else None
        ),
        "elicitation_questionnaire": (
            [item.model_dump(mode="json") for item in review_request.elicitation_questionnaire]
            if review_request.elicitation_questionnaire is not None
            else None
        ),
    }


def _dedupe_artifact_refs(values: list[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped


def _dedupe_string_values(values: list[str | None]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not value:
            continue
        normalized = str(value)
        if normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(normalized)
    return deduped


def _maker_checker_support_key(
    review_request: TicketBoardReviewRequest | None,
    created_spec: dict[str, Any] | None,
) -> tuple[str, str, int] | None:
    if review_request is None or created_spec is None:
        return None
    return (
        review_request.review_type.value,
        str(created_spec.get("output_schema_ref") or ""),
        int(created_spec.get("output_schema_version") or 0),
    )


def _supports_maker_checker(
    review_request: TicketBoardReviewRequest | None,
    created_spec: dict[str, Any] | None,
) -> bool:
    return _maker_checker_support_key(review_request, created_spec) in MAKER_CHECKER_SUPPORTED_TARGETS


def _maker_checker_subject_label(review_request: TicketBoardReviewRequest | None) -> str:
    if review_request is None:
        return "submitted deliverable"
    if review_request.review_type.value == "VISUAL_MILESTONE":
        return "submitted visual milestone"
    if review_request.review_type.value == "MEETING_ESCALATION":
        return "submitted consensus document"
    if review_request.review_type.value == "INTERNAL_GOVERNANCE_REVIEW":
        return "submitted governance document"
    if review_request.review_type.value == "INTERNAL_DELIVERY_REVIEW":
        return "submitted source code delivery"
    if review_request.review_type.value == "INTERNAL_CHECK_REVIEW":
        return "submitted delivery check report"
    if review_request.review_type.value == "INTERNAL_CLOSEOUT_REVIEW":
        return "submitted delivery closeout package"
    return "submitted deliverable"


def _is_internal_delivery_review_request(review_request: TicketBoardReviewRequest | None) -> bool:
    return bool(
        review_request is not None
        and review_request.review_type.value == "INTERNAL_DELIVERY_REVIEW"
    )


def _is_internal_check_review_request(review_request: TicketBoardReviewRequest | None) -> bool:
    return bool(
        review_request is not None
        and review_request.review_type.value == "INTERNAL_CHECK_REVIEW"
    )


def _is_internal_only_review_request(review_request: TicketBoardReviewRequest | None) -> bool:
    return bool(
        review_request is not None
        and review_request.review_type.value
        in {
            "INTERNAL_GOVERNANCE_REVIEW",
            "INTERNAL_DELIVERY_REVIEW",
            "INTERNAL_CHECK_REVIEW",
            "INTERNAL_CLOSEOUT_REVIEW",
        }
    )


def _build_maker_checker_input_artifact_refs(
    *,
    created_spec: dict[str, Any],
    review_request: TicketBoardReviewRequest,
    maker_artifact_refs: list[str],
) -> list[str]:
    if review_request.review_type.value in {
        "INTERNAL_GOVERNANCE_REVIEW",
        "INTERNAL_CHECK_REVIEW",
        "INTERNAL_CLOSEOUT_REVIEW",
    }:
        return _dedupe_artifact_refs(
            list(maker_artifact_refs) + list(created_spec.get("input_artifact_refs") or [])
        )
    if maker_artifact_refs:
        return maker_artifact_refs
    return list(created_spec.get("input_artifact_refs") or [])


def _build_maker_checker_input_process_asset_refs(
    *,
    created_spec: dict[str, Any],
    review_request: TicketBoardReviewRequest,
    maker_process_asset_refs: list[str],
) -> list[str]:
    existing_process_asset_refs = list(created_spec.get("input_process_asset_refs") or [])
    if review_request.review_type.value in {
        "INTERNAL_GOVERNANCE_REVIEW",
        "INTERNAL_CHECK_REVIEW",
        "INTERNAL_CLOSEOUT_REVIEW",
    }:
        return dedupe_process_asset_refs(
            list(maker_process_asset_refs) + existing_process_asset_refs
        )
    if maker_process_asset_refs:
        return dedupe_process_asset_refs(maker_process_asset_refs)
    return merge_input_process_asset_refs(
        existing_process_asset_refs=existing_process_asset_refs,
        artifact_refs=list(created_spec.get("input_artifact_refs") or []),
    )


def _ticket_kind(created_spec: dict[str, Any] | None) -> str | None:
    if created_spec is None or created_spec.get("ticket_kind") is None:
        return None
    return str(created_spec["ticket_kind"])


def _resolve_original_review_request(
    payload: TicketCompletedCommand,
    created_spec: dict[str, Any] | None,
) -> TicketBoardReviewRequest | None:
    if payload.review_request is not None:
        return payload.review_request
    if created_spec is None:
        return None
    auto_review_request = created_spec.get("auto_review_request")
    if isinstance(auto_review_request, dict):
        parsed_auto_review_request = TicketBoardReviewRequest.model_validate(auto_review_request)
        if parsed_auto_review_request.review_type.value == "INTERNAL_GOVERNANCE_REVIEW":
            return parsed_auto_review_request
    maker_checker_context = created_spec.get("maker_checker_context") or {}
    original_review_request = maker_checker_context.get("original_review_request")
    if not isinstance(original_review_request, dict):
        return None
    return TicketBoardReviewRequest.model_validate(original_review_request)


def _should_route_to_maker_checker(
    *,
    review_request: TicketBoardReviewRequest | None,
    created_spec: dict[str, Any] | None,
) -> bool:
    if not _supports_maker_checker(review_request, created_spec):
        return False
    if created_spec is None:
        return False
    if _ticket_kind(created_spec) == MAKER_CHECKER_REVIEW_TICKET_KIND:
        return False
    return True


def _build_generated_maker_checker_summary(
    *,
    checker_payload: dict[str, Any],
    checker_completed_by: str,
    checker_created_spec: dict[str, Any] | None,
) -> dict[str, Any]:
    maker_checker_context = (checker_created_spec or {}).get("maker_checker_context") or {}
    top_findings: list[dict[str, Any]] = []
    findings = checker_payload.get("findings")
    if isinstance(findings, list):
        for finding in findings:
            if not isinstance(finding, dict):
                continue
            top_findings.append(
                {
                    "finding_id": finding.get("finding_id"),
                    "severity": finding.get("severity"),
                    "headline": finding.get("headline"),
                }
            )
    return {
        "maker_employee_id": maker_checker_context.get("maker_completed_by"),
        "checker_employee_id": checker_completed_by,
        "review_status": checker_payload.get("review_status"),
        "top_findings": top_findings,
    }


def _extract_blocking_checker_findings(checker_payload: dict[str, Any]) -> list[dict[str, Any]]:
    blocking_findings: list[dict[str, Any]] = []
    findings = checker_payload.get("findings")
    if not isinstance(findings, list):
        return blocking_findings

    for finding in findings:
        if not isinstance(finding, dict) or not finding.get("blocking"):
            continue
        finding_id = str(finding.get("finding_id") or "").strip()
        if not finding_id:
            continue
        blocking_findings.append(
            {
                "finding_id": finding_id,
                "headline": str(finding.get("headline") or "").strip(),
                "required_action": str(finding.get("required_action") or "").strip(),
                "severity": str(finding.get("severity") or "").strip(),
                "category": str(finding.get("category") or "").strip(),
            }
        )
    return blocking_findings


def _build_rework_fingerprint(blocking_findings: list[dict[str, Any]]) -> str:
    canonical_findings = [
        {
            "category": finding["category"],
            "headline": finding["headline"],
            "required_action": finding["required_action"],
        }
        for finding in blocking_findings
    ]
    canonical_findings.sort(
        key=lambda item: (
            item["category"],
            item["headline"],
            item["required_action"],
        )
    )
    digest = hashlib.sha256(
        json.dumps(
            canonical_findings,
            sort_keys=True,
            ensure_ascii=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return f"mkrw:{digest}"


def _calculate_maker_checker_rework_streak(
    repository: ControlPlaneRepository,
    connection,
    *,
    checker_created_spec: dict[str, Any],
    rework_fingerprint: str,
) -> int:
    parent_ticket_id = checker_created_spec.get("parent_ticket_id")
    if not parent_ticket_id:
        return 1

    parent_created_spec = repository.get_latest_ticket_created_payload(connection, parent_ticket_id)
    if parent_created_spec is None or _ticket_kind(parent_created_spec) != MAKER_REWORK_FIX_TICKET_KIND:
        return 1

    parent_context = parent_created_spec.get("maker_checker_context") or {}
    if parent_context.get("rework_fingerprint") != rework_fingerprint:
        return 1
    return max(1, int(parent_context.get("rework_streak_count") or 0) + 1)


def _calculate_maker_checker_rework_cycle_count(
    repository: ControlPlaneRepository,
    connection,
    *,
    checker_created_spec: dict[str, Any],
) -> int:
    cycle_count = 1
    parent_ticket_id = checker_created_spec.get("parent_ticket_id")
    seen_ticket_ids: set[str] = set()
    while parent_ticket_id and parent_ticket_id not in seen_ticket_ids:
        seen_ticket_ids.add(parent_ticket_id)
        parent_created_spec = repository.get_latest_ticket_created_payload(connection, parent_ticket_id)
        if parent_created_spec is None:
            break
        if _ticket_kind(parent_created_spec) == MAKER_REWORK_FIX_TICKET_KIND:
            cycle_count += 1
        parent_ticket_id = parent_created_spec.get("parent_ticket_id")
    return max(1, cycle_count)


def _should_escalate_maker_checker_rework(
    *,
    created_spec: dict[str, Any],
    rework_streak_count: int,
) -> bool:
    escalation_policy = created_spec.get("escalation_policy") or {}
    return (
        escalation_policy.get("on_repeat_failure") == "escalate_ceo"
        and rework_streak_count >= _resolve_repeat_failure_threshold(created_spec)
    )


def _should_autopilot_converge_maker_checker_rework(
    *,
    workflow: dict[str, Any] | None,
    review_request: TicketBoardReviewRequest | None,
    created_spec: dict[str, Any],
    rework_cycle_count: int,
) -> bool:
    return bool(
        workflow_uses_ceo_board_delegate(workflow)
        and review_request is not None
        and _is_internal_only_review_request(review_request)
        and rework_cycle_count >= _resolve_repeat_failure_threshold(created_spec)
    )


def _build_autopilot_converged_checker_result_payload(
    checker_result_payload: dict[str, Any],
) -> dict[str, Any]:
    note = "Autopilot reached the graduation-project rework cap and accepted this checker pass with notes."
    findings = [
        {
            **finding,
            "blocking": False,
        }
        for finding in list(checker_result_payload.get("findings") or [])
        if isinstance(finding, dict)
    ]
    summary = str(checker_result_payload.get("summary") or "").strip()
    return {
        **checker_result_payload,
        "summary": f"{summary} {note}".strip(),
        "review_status": "APPROVED_WITH_NOTES",
        "findings": findings,
        "autopilot_convergence_applied": True,
        "autopilot_convergence_note": note,
    }


def _resolve_maker_checker_rework_incident_fingerprint(
    workflow_id: str,
    node_id: str,
    rework_fingerprint: str,
) -> str:
    return f"{workflow_id}:{node_id}:maker-checker-rework:{rework_fingerprint}"


def _build_maker_checker_ticket_payload(
    *,
    workflow_id: str,
    node_id: str,
    source_ticket_id: str,
    created_spec: dict[str, Any],
    review_request: TicketBoardReviewRequest,
    maker_completed_by: str,
    maker_artifact_refs: list[str],
    maker_process_asset_refs: list[str],
) -> dict[str, Any]:
    context_query_plan = dict(created_spec.get("context_query_plan") or {})
    max_context_tokens = int(context_query_plan.get("max_context_tokens") or 0)
    if max_context_tokens <= 0:
        max_context_tokens = get_settings().default_max_context_tokens

    maker_ticket_spec = {
        "role_profile_ref": created_spec.get("role_profile_ref"),
        "constraints_ref": created_spec.get("constraints_ref"),
        "context_query_plan": context_query_plan,
        "acceptance_criteria": list(created_spec.get("acceptance_criteria") or []),
        "output_schema_ref": created_spec.get("output_schema_ref"),
        "output_schema_version": created_spec.get("output_schema_version"),
        "input_process_asset_refs": list(created_spec.get("input_process_asset_refs") or []),
        "delivery_stage": created_spec.get("delivery_stage"),
        "allowed_tools": list(created_spec.get("allowed_tools") or []),
        "allowed_write_set": list(created_spec.get("allowed_write_set") or []),
        "lease_timeout_sec": created_spec.get("lease_timeout_sec"),
        "retry_budget": created_spec.get("retry_budget"),
        "priority": created_spec.get("priority"),
        "timeout_sla_sec": created_spec.get("timeout_sla_sec"),
        "deadline_at": created_spec.get("deadline_at"),
        "tenant_id": created_spec.get("tenant_id"),
        "workspace_id": created_spec.get("workspace_id"),
        "excluded_employee_ids": list(created_spec.get("excluded_employee_ids") or []),
        "meeting_context": dict(created_spec.get("meeting_context") or {})
        if isinstance(created_spec.get("meeting_context"), dict)
        else None,
        "escalation_policy": dict(created_spec.get("escalation_policy") or {}),
    }
    input_artifact_refs = _build_maker_checker_input_artifact_refs(
        created_spec=created_spec,
        review_request=review_request,
        maker_artifact_refs=maker_artifact_refs,
    )
    input_process_asset_refs = _build_maker_checker_input_process_asset_refs(
        created_spec=created_spec,
        review_request=review_request,
        maker_process_asset_refs=maker_process_asset_refs,
    )
    return {
        "ticket_id": new_prefixed_id("tkt"),
        "workflow_id": workflow_id,
        "node_id": node_id,
        "parent_ticket_id": source_ticket_id,
        "attempt_no": int(created_spec.get("attempt_no") or 1) + 1,
        "role_profile_ref": "checker_primary",
        "constraints_ref": str(created_spec.get("constraints_ref") or ""),
        "input_artifact_refs": input_artifact_refs,
        "input_process_asset_refs": input_process_asset_refs,
        "context_query_plan": {
            "keywords": list(context_query_plan.get("keywords") or []),
            "semantic_queries": list(context_query_plan.get("semantic_queries") or []),
            "max_context_tokens": max_context_tokens,
        },
        "acceptance_criteria": [
            (
                "Must return a structured maker-checker verdict for the "
                f"{_maker_checker_subject_label(review_request)}."
            ),
        ],
        "output_schema_ref": MAKER_CHECKER_VERDICT_SCHEMA_REF,
        "output_schema_version": MAKER_CHECKER_VERDICT_SCHEMA_VERSION,
        "execution_contract": infer_execution_contract_payload(
            role_profile_ref="checker_primary",
            output_schema_ref=MAKER_CHECKER_VERDICT_SCHEMA_REF,
        ),
        "allowed_tools": ["read_artifact"],
        "allowed_write_set": [],
        "lease_timeout_sec": int(created_spec.get("lease_timeout_sec") or DEFAULT_LEASE_TIMEOUT_SEC),
        "retry_budget": int(created_spec.get("retry_budget") or 0),
        "priority": str(created_spec.get("priority") or "high"),
        "timeout_sla_sec": int(created_spec.get("timeout_sla_sec") or 1800),
        "deadline_at": created_spec.get("deadline_at"),
        "tenant_id": created_spec.get("tenant_id"),
        "workspace_id": created_spec.get("workspace_id"),
        "delivery_stage": created_spec.get("delivery_stage"),
        "escalation_policy": dict(created_spec.get("escalation_policy") or {}),
        "ticket_kind": MAKER_CHECKER_REVIEW_TICKET_KIND,
        "graph_contract": {
            "lane_kind": "review",
        },
        "maker_checker_context": {
            "maker_ticket_id": source_ticket_id,
            "maker_completed_by": maker_completed_by,
            "maker_artifact_refs": input_artifact_refs,
            "maker_process_asset_refs": input_process_asset_refs,
            "maker_ticket_spec": maker_ticket_spec,
            "original_review_request": review_request.model_dump(mode="json"),
        },
    }


def _build_fix_ticket_payload(
    *,
    workflow_id: str,
    node_id: str,
    checker_ticket_id: str,
    checker_created_spec: dict[str, Any],
    checker_result_payload: dict[str, Any],
    blocking_findings: list[dict[str, Any]],
    rework_fingerprint: str,
    rework_streak_count: int,
) -> dict[str, Any]:
    maker_checker_context = checker_created_spec.get("maker_checker_context") or {}
    maker_ticket_spec = dict(maker_checker_context.get("maker_ticket_spec") or {})
    original_review_request = maker_checker_context.get("original_review_request")
    context_query_plan = dict(maker_ticket_spec.get("context_query_plan") or {})
    max_context_tokens = int(context_query_plan.get("max_context_tokens") or 0)
    if max_context_tokens <= 0:
        max_context_tokens = get_settings().default_max_context_tokens
    input_artifact_refs = _dedupe_artifact_refs(
        list(maker_checker_context.get("maker_artifact_refs") or [])
        + list(checker_result_payload.get("artifact_refs") or [])
    ) or list(checker_created_spec.get("input_artifact_refs") or [])
    input_process_asset_refs = merge_input_process_asset_refs(
        existing_process_asset_refs=(
            list(maker_checker_context.get("maker_process_asset_refs") or [])
            or list(checker_created_spec.get("input_process_asset_refs") or [])
        ),
        artifact_refs=list(checker_result_payload.get("artifact_refs") or []),
    )
    required_fixes = [
        {
            "finding_id": finding["finding_id"],
            "headline": finding["headline"],
            "required_action": finding["required_action"],
            "severity": finding["severity"],
            "category": finding["category"],
        }
        for finding in blocking_findings
    ]
    acceptance_criteria = list(maker_ticket_spec.get("acceptance_criteria") or [])
    acceptance_criteria.extend(
        [
            (
                f"Close checker blocking finding {finding['finding_id']}: "
                f"{finding['required_action']}"
            )
            for finding in required_fixes
        ]
    )
    excluded_employee_ids = _dedupe_string_values(
        list(maker_ticket_spec.get("excluded_employee_ids") or [])
        + [maker_checker_context.get("maker_completed_by")]
    )
    next_ticket_id = new_prefixed_id("tkt")
    maker_ticket_id = str(maker_checker_context.get("maker_ticket_id") or "").strip()
    return {
        "ticket_id": next_ticket_id,
        "workflow_id": workflow_id,
        "node_id": node_id,
        "parent_ticket_id": checker_ticket_id,
        "attempt_no": int(checker_created_spec.get("attempt_no") or 1) + 1,
        "role_profile_ref": str(maker_ticket_spec.get("role_profile_ref") or "ui_designer_primary"),
        "constraints_ref": str(maker_ticket_spec.get("constraints_ref") or ""),
        "input_artifact_refs": input_artifact_refs,
        "input_process_asset_refs": input_process_asset_refs,
        "context_query_plan": {
            "keywords": list(context_query_plan.get("keywords") or []),
            "semantic_queries": list(context_query_plan.get("semantic_queries") or []),
            "max_context_tokens": max_context_tokens,
        },
        "acceptance_criteria": acceptance_criteria,
        "output_schema_ref": str(maker_ticket_spec.get("output_schema_ref") or UI_MILESTONE_REVIEW_SCHEMA_REF),
        "output_schema_version": int(
            maker_ticket_spec.get("output_schema_version") or UI_MILESTONE_REVIEW_SCHEMA_VERSION
        ),
        "execution_contract": dict(maker_ticket_spec.get("execution_contract") or {})
        or infer_execution_contract_payload(
            role_profile_ref=str(maker_ticket_spec.get("role_profile_ref") or "ui_designer_primary"),
            output_schema_ref=str(
                maker_ticket_spec.get("output_schema_ref") or UI_MILESTONE_REVIEW_SCHEMA_REF
            ),
        ),
        "allowed_tools": list(maker_ticket_spec.get("allowed_tools") or []),
        "allowed_write_set": rebind_ticket_id_in_allowed_write_set(
            list(maker_ticket_spec.get("allowed_write_set") or []),
            previous_ticket_id=maker_ticket_id,
            next_ticket_id=next_ticket_id,
        ),
        "lease_timeout_sec": int(maker_ticket_spec.get("lease_timeout_sec") or DEFAULT_LEASE_TIMEOUT_SEC),
        "retry_budget": int(maker_ticket_spec.get("retry_budget") or 0),
        "priority": str(maker_ticket_spec.get("priority") or "high"),
        "timeout_sla_sec": int(maker_ticket_spec.get("timeout_sla_sec") or 1800),
        "deadline_at": maker_ticket_spec.get("deadline_at"),
        "tenant_id": maker_ticket_spec.get("tenant_id"),
        "workspace_id": maker_ticket_spec.get("workspace_id"),
        "delivery_stage": maker_ticket_spec.get("delivery_stage"),
        "auto_review_request": (
            dict(original_review_request) if isinstance(original_review_request, dict) else None
        ),
        "excluded_employee_ids": excluded_employee_ids,
        "escalation_policy": dict(maker_ticket_spec.get("escalation_policy") or {}),
        "ticket_kind": MAKER_REWORK_FIX_TICKET_KIND,
        "graph_contract": {
            "lane_kind": "execution",
        },
        "maker_checker_context": {
            "maker_ticket_id": maker_checker_context.get("maker_ticket_id"),
            "maker_completed_by": maker_checker_context.get("maker_completed_by"),
            "maker_artifact_refs": input_artifact_refs,
            "maker_process_asset_refs": input_process_asset_refs,
            "maker_ticket_spec": maker_ticket_spec,
            "original_review_request": original_review_request,
            "checker_ticket_id": checker_ticket_id,
            "blocking_finding_refs": [finding["finding_id"] for finding in required_fixes],
            "required_fixes": required_fixes,
            "rework_fingerprint": rework_fingerprint,
            "rework_streak_count": rework_streak_count,
        },
    }


def _open_maker_checker_rework_incident(
    *,
    repository: ControlPlaneRepository,
    connection,
    command_id: str,
    occurred_at: datetime,
    workflow_id: str,
    ticket_id: str,
    node_id: str,
    rework_fingerprint: str,
    rework_streak_count: int,
    blocking_findings: list[dict[str, Any]],
    idempotency_key_base: str,
) -> str:
    existing_incident = repository.get_open_incident_for_node(workflow_id, node_id, connection=connection)
    if existing_incident is not None:
        return str(existing_incident["incident_id"])

    incident_id = new_prefixed_id("inc")
    incident_payload = {
        "incident_id": incident_id,
        "ticket_id": ticket_id,
        "node_id": node_id,
        "incident_type": INCIDENT_TYPE_MAKER_CHECKER_REWORK_ESCALATION,
        "status": INCIDENT_STATUS_OPEN,
        "severity": "high",
        "fingerprint": _resolve_maker_checker_rework_incident_fingerprint(
            workflow_id,
            node_id,
            rework_fingerprint,
        ),
        "rework_fingerprint": rework_fingerprint,
        "rework_streak_count": rework_streak_count,
        "latest_checker_ticket_id": ticket_id,
        "latest_blocking_findings": blocking_findings,
    }
    incident_event = repository.insert_event(
        connection,
        event_type=EVENT_INCIDENT_OPENED,
        actor_type="system",
        actor_id="maker-checker-router",
        workflow_id=workflow_id,
        idempotency_key=f"{idempotency_key_base}:incident-opened:{ticket_id}",
        causation_id=command_id,
        correlation_id=workflow_id,
        payload=incident_payload,
        occurred_at=occurred_at,
    )
    if incident_event is None:
        raise RuntimeError("Maker-checker rework incident opening idempotency conflict.")

    breaker_event = repository.insert_event(
        connection,
        event_type=EVENT_CIRCUIT_BREAKER_OPENED,
        actor_type="system",
        actor_id="maker-checker-router",
        workflow_id=workflow_id,
        idempotency_key=f"{idempotency_key_base}:circuit-breaker-opened:{ticket_id}",
        causation_id=command_id,
        correlation_id=workflow_id,
        payload={
            "incident_id": incident_id,
            "ticket_id": ticket_id,
            "node_id": node_id,
            "circuit_breaker_state": CIRCUIT_BREAKER_STATE_OPEN,
            "fingerprint": incident_payload["fingerprint"],
        },
        occurred_at=occurred_at,
    )
    if breaker_event is None:
        raise RuntimeError("Maker-checker rework circuit breaker opening idempotency conflict.")

    return incident_id


def _insert_followup_ticket_created_event(
    *,
    repository: ControlPlaneRepository,
    connection,
    command_id: str,
    occurred_at: datetime,
    workflow_id: str,
    ticket_payload: dict[str, Any],
    idempotency_key: str,
    actor_id: str,
) -> str:
    resolved_ticket_payload = _ensure_ticket_execution_contract_payload(ticket_payload)
    created_event = repository.insert_event(
        connection,
        event_type=EVENT_TICKET_CREATED,
        actor_type="system",
        actor_id=actor_id,
        workflow_id=workflow_id,
        idempotency_key=idempotency_key,
        causation_id=command_id,
        correlation_id=workflow_id,
        payload=resolved_ticket_payload,
        occurred_at=occurred_at,
    )
    if created_event is None:
        raise RuntimeError("Follow-up ticket creation idempotency conflict.")
    return str(resolved_ticket_payload["ticket_id"])


def _ensure_ticket_execution_contract_payload(ticket_payload: dict[str, Any]) -> dict[str, Any]:
    resolved_payload = dict(ticket_payload)
    execution_contract = resolved_payload.get("execution_contract")
    if not isinstance(execution_contract, dict):
        raise ValueError("Ticket payload requires execution_contract.")
    graph_contract = resolved_payload.get("graph_contract")
    if not isinstance(graph_contract, dict) or not str(graph_contract.get("lane_kind") or "").strip():
        raise ValueError("Ticket payload requires graph_contract.lane_kind.")
    if (
        resolved_payload.get("auto_review_request") is None
        and str(resolved_payload.get("output_schema_ref") or "") in GOVERNANCE_DOCUMENT_SCHEMA_REFS
    ):
        resolved_payload["auto_review_request"] = build_internal_governance_review_request(
            str(resolved_payload.get("summary") or "")
        )
    workspace_bootstrap = infer_ticket_workspace_bootstrap(resolved_payload)
    resolved_payload["project_workspace_ref"] = workspace_bootstrap.project_workspace_ref
    resolved_payload["project_methodology_profile"] = workspace_bootstrap.project_methodology_profile.value
    resolved_payload["deliverable_kind"] = workspace_bootstrap.deliverable_kind.value
    resolved_payload["canonical_doc_refs"] = list(workspace_bootstrap.canonical_doc_refs)
    resolved_payload["required_read_refs"] = list(workspace_bootstrap.required_read_refs)
    resolved_payload["doc_update_requirements"] = list(workspace_bootstrap.doc_update_requirements)
    resolved_payload["git_policy"] = workspace_bootstrap.git_policy.value
    if workspace_bootstrap.project_checkout_ref is not None:
        resolved_payload["project_checkout_ref"] = workspace_bootstrap.project_checkout_ref
    if workspace_bootstrap.git_branch_ref is not None:
        resolved_payload["git_branch_ref"] = workspace_bootstrap.git_branch_ref
    return resolved_payload


def _normalized_failure_detail(failure_detail: dict | None) -> dict:
    if failure_detail is None:
        return {}
    return json.loads(json.dumps(failure_detail, sort_keys=True))


def _build_failure_payload(
    *,
    failure_kind: str,
    failure_message: str,
    failure_detail: dict | None,
) -> dict[str, Any]:
    normalized_detail = _normalized_failure_detail(failure_detail)
    fingerprint_source = {
        "failure_kind": failure_kind,
        "failure_message": failure_message,
        "failure_detail": normalized_detail,
    }
    fingerprint = hashlib.sha256(
        json.dumps(
            fingerprint_source,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("utf-8")
    ).hexdigest()
    return {
        "failure_kind": failure_kind,
        "failure_message": failure_message,
        "failure_detail": normalized_detail,
        "failure_fingerprint": fingerprint,
    }


DISPATCH_INTENT_INVALID_FAILURE_KIND = "DISPATCH_INTENT_INVALID"
DEPENDENCY_GATE_INVALID_FAILURE_KIND = "DEPENDENCY_GATE_INVALID"
DEPENDENCY_GATE_UNHEALTHY_FAILURE_KIND = "DEPENDENCY_GATE_UNHEALTHY"
UPSTREAM_DEPENDENCY_UNHEALTHY_FAILURE_KIND = "UPSTREAM_DEPENDENCY_UNHEALTHY"
WORKSPACE_HOOK_VALIDATION_FAILURE_KIND = "WORKSPACE_HOOK_VALIDATION_ERROR"
DECOMPOSITION_RECOVERY_FAILURE_KINDS = {
    "REQUEST_TOO_LARGE",
    "CONTEXT_TOO_LARGE",
    "OUTPUT_TOO_LARGE",
    "NEEDS_DECOMPOSITION",
}
DEPENDENCY_TERMINAL_FAILURE_STATUSES = {
    TICKET_STATUS_FAILED,
    TICKET_STATUS_TIMED_OUT,
    TICKET_STATUS_CANCELLED,
}


def _validate_source_code_delivery_hooks(
    *,
    created_spec: dict[str, Any],
    payload: TicketResultSubmitCommand,
) -> str | None:
    if str(created_spec.get("deliverable_kind") or "") != "source_code_delivery":
        return None
    if not is_workspace_managed_write_set(list(created_spec.get("allowed_write_set") or [])):
        return None

    result_payload = payload.payload if isinstance(payload.payload, dict) else {}
    source_files = [
        dict(item)
        for item in list(result_payload.get("source_files") or [])
        if isinstance(item, dict)
    ]
    verification_runs = [
        dict(item)
        for item in list(result_payload.get("verification_runs") or [])
        if isinstance(item, dict)
    ]
    written_artifacts_by_ref = {
        str(item.artifact_ref): item
        for item in payload.written_artifacts
    }
    source_file_refs = list(result_payload.get("source_file_refs") or [])
    if not source_file_refs:
        return "Code delivery tickets must include payload.source_file_refs."
    project_source_artifact_refs = {
        str(item.artifact_ref)
        for item in payload.written_artifacts
        if str(item.path or "").startswith("10-project/")
        and not str(item.path or "").startswith("10-project/docs/")
    }
    if not project_source_artifact_refs:
        return "Code delivery tickets must write at least one source artifact under 10-project/ outside docs."
    for artifact_ref in source_file_refs:
        written_artifact = written_artifacts_by_ref.get(str(artifact_ref))
        if written_artifact is None:
            return f"payload.source_file_refs includes unknown artifact_ref {artifact_ref}."
        path = str(written_artifact.path or "")
        if not path.startswith("10-project/") or path.startswith("10-project/docs/"):
            return (
                "Code delivery tickets must keep payload.source_file_refs inside "
                f"10-project/ source paths; got {path}."
            )
    source_files_by_ref = {
        str(item.get("artifact_ref") or "").strip(): item
        for item in source_files
        if str(item.get("artifact_ref") or "").strip()
    }
    for artifact_ref in source_file_refs:
        source_file = source_files_by_ref.get(str(artifact_ref))
        if source_file is None:
            return f"payload.source_files is missing artifact_ref {artifact_ref}."
        if str(source_file.get("path") or "").strip() != str(written_artifacts_by_ref[artifact_ref].path or "").strip():
            return f"payload.source_files path must match written_artifacts for {artifact_ref}."

    documentation_updates = list(result_payload.get("documentation_updates") or [])
    updates_by_ref = {
        str(item.get("doc_ref") or "").strip(): item
        for item in documentation_updates
        if isinstance(item, dict) and str(item.get("doc_ref") or "").strip()
    }
    for doc_ref in list(created_spec.get("doc_update_requirements") or []):
        update = updates_by_ref.get(str(doc_ref))
        if update is None:
            return f"Code delivery tickets must report documentation_updates for {doc_ref}."
        if str(update.get("status") or "") not in {"UPDATED", "NO_CHANGE_REQUIRED"}:
            return (
                "Code delivery tickets must mark required documentation updates as "
                f"UPDATED or NO_CHANGE_REQUIRED; got {update.get('status')} for {doc_ref}."
            )

    available_artifact_refs = set(payload.artifact_refs)
    available_artifact_refs.update(str(item.artifact_ref) for item in payload.written_artifacts)
    if not payload.verification_evidence_refs:
        return "Code delivery tickets must include verification_evidence_refs."
    expected_verification_refs = [
        str(item.get("artifact_ref") or "").strip()
        for item in verification_runs
        if str(item.get("artifact_ref") or "").strip()
    ]
    if list(payload.verification_evidence_refs) != expected_verification_refs:
        return "Code delivery tickets must keep verification_evidence_refs aligned with payload.verification_runs."
    verification_paths: list[str] = []
    for artifact_ref in payload.verification_evidence_refs:
        if artifact_ref not in available_artifact_refs:
            return f"verification_evidence_refs includes unknown artifact_ref {artifact_ref}."
        written_artifact = written_artifacts_by_ref.get(str(artifact_ref))
        if written_artifact is None:
            return f"verification_evidence_refs includes non-materialized artifact_ref {artifact_ref}."
        verification_path = str(written_artifact.path or "")
        verification_paths.append(verification_path)
        if not verification_path.startswith("20-evidence/tests/"):
            return (
                "Code delivery tickets must keep verification evidence inside "
                f"20-evidence/tests/; got {verification_path}."
            )
    if not all("/attempt-" in path for path in verification_paths):
        return "Code delivery tickets must version verification evidence paths by attempt."

    git_written_artifacts = [
        item
        for item in payload.written_artifacts
        if str(item.path or "").startswith("20-evidence/git/")
    ]
    if not git_written_artifacts:
        return "Code delivery tickets must persist git evidence under 20-evidence/git/."
    if not all("/attempt-" in str(item.path or "") for item in git_written_artifacts):
        return "Code delivery tickets must version git evidence paths by attempt."
    return None


def _validate_structured_document_delivery_hooks(
    *,
    created_spec: dict[str, Any],
    payload: TicketResultSubmitCommand,
) -> str | None:
    if str(created_spec.get("deliverable_kind") or "") != "structured_document_delivery":
        return None

    declared_artifact_refs = [
        str(item).strip()
        for item in payload.artifact_refs
        if str(item).strip()
    ]
    if not declared_artifact_refs:
        return "Structured document tickets must include at least one declared artifact_ref."

    written_artifacts_by_ref = {
        str(item.artifact_ref): item
        for item in payload.written_artifacts
        if str(item.artifact_ref)
    }
    if not written_artifacts_by_ref:
        return "Structured document tickets must persist at least one written artifact."

    if not any(artifact_ref in written_artifacts_by_ref for artifact_ref in declared_artifact_refs):
        return (
            "Structured document tickets must persist at least one declared artifact_ref "
            "inside written_artifacts."
        )

    return None


def _closeout_known_final_artifact_refs(
    repository: ControlPlaneRepository,
    *,
    created_spec: dict[str, Any],
) -> set[str]:
    known_artifact_refs = {
        str(item).strip()
        for item in list(created_spec.get("input_artifact_refs") or [])
        if str(item).strip()
    }
    with repository.connection() as connection:
        parent_ticket_id = str(created_spec.get("parent_ticket_id") or "").strip()
        if parent_ticket_id:
            parent_terminal_event = repository.get_latest_ticket_terminal_event(connection, parent_ticket_id)
            parent_terminal_payload = parent_terminal_event.get("payload") if parent_terminal_event is not None else {}
            if isinstance(parent_terminal_payload, dict):
                for artifact_ref in list(parent_terminal_payload.get("artifact_refs") or []):
                    normalized_artifact_ref = str(artifact_ref).strip()
                    if normalized_artifact_ref:
                        known_artifact_refs.add(normalized_artifact_ref)
        for process_asset_ref in list(created_spec.get("input_process_asset_refs") or []):
            try:
                kind, ticket_id = parse_process_asset_ref(str(process_asset_ref))
            except ValueError:
                continue
            if kind != "source-code-delivery":
                continue
            terminal_event = repository.get_latest_ticket_terminal_event(connection, ticket_id)
            terminal_payload = terminal_event.get("payload") if terminal_event is not None else {}
            if not isinstance(terminal_payload, dict):
                continue
            for artifact_ref in list(terminal_payload.get("artifact_refs") or []):
                normalized_artifact_ref = str(artifact_ref).strip()
                if normalized_artifact_ref:
                    known_artifact_refs.add(normalized_artifact_ref)
            for artifact_ref in list(terminal_payload.get("verification_evidence_refs") or []):
                normalized_artifact_ref = str(artifact_ref).strip()
                if normalized_artifact_ref:
                    known_artifact_refs.add(normalized_artifact_ref)
    return known_artifact_refs


def _validate_closeout_delivery_hooks(
    repository: ControlPlaneRepository,
    *,
    created_spec: dict[str, Any],
    payload: TicketResultSubmitCommand,
) -> str | None:
    if str(created_spec.get("output_schema_ref") or "").strip() != DELIVERY_CLOSEOUT_PACKAGE_SCHEMA_REF:
        return None

    result_payload = payload.payload if isinstance(payload.payload, dict) else {}
    final_artifact_refs = [
        str(item).strip()
        for item in list(result_payload.get("final_artifact_refs") or [])
        if str(item).strip()
    ]
    if not final_artifact_refs:
        return "Closeout tickets must include payload.final_artifact_refs."

    known_artifact_refs = _closeout_known_final_artifact_refs(
        repository,
        created_spec=created_spec,
    )
    if not known_artifact_refs:
        return "Closeout tickets must reference known delivery evidence before completion."
    for artifact_ref in final_artifact_refs:
        if artifact_ref not in known_artifact_refs:
            return (
                "Closeout tickets must keep payload.final_artifact_refs aligned with known delivery evidence; "
                f"got {artifact_ref}."
            )
    return None


def _validate_governance_document_hooks(
    *,
    created_spec: dict[str, Any],
    payload: TicketResultSubmitCommand,
) -> str | None:
    output_schema_ref = str(created_spec.get("output_schema_ref") or "").strip()
    if output_schema_ref not in GOVERNANCE_DOCUMENT_SCHEMA_REFS:
        return None

    result_payload = payload.payload if isinstance(payload.payload, dict) else {}
    document_kind_ref = str(result_payload.get("document_kind_ref") or "").strip()
    if document_kind_ref != output_schema_ref:
        return (
            "Governance document tickets must keep payload.document_kind_ref aligned with "
            f"{output_schema_ref}; got {document_kind_ref or '<missing>'}."
        )

    return None


def _validate_backlog_recommendation_hooks(
    *,
    created_spec: dict[str, Any],
    payload: TicketResultSubmitCommand,
) -> str | None:
    output_schema_ref = str(created_spec.get("output_schema_ref") or "").strip()
    if output_schema_ref != BACKLOG_RECOMMENDATION_SCHEMA_REF:
        return None

    expected_artifact_ref = build_backlog_recommendation_artifact_ref(payload.ticket_id)
    expected_path = build_backlog_recommendation_artifact_path(payload.ticket_id)
    canonical_artifact = next(
        (
            item
            for item in payload.written_artifacts
            if str(item.artifact_ref or "").strip() == expected_artifact_ref
        ),
        None,
    )
    if canonical_artifact is None:
        return "Backlog recommendation tickets must write the canonical backlog JSON artifact."
    if str(canonical_artifact.kind or "").upper() != "JSON":
        return "Canonical backlog recommendation artifact must be JSON."
    if str(canonical_artifact.path or "").strip() != expected_path:
        return "Canonical backlog recommendation artifact path does not match the required governance path."
    if expected_artifact_ref not in set(str(item).strip() for item in payload.artifact_refs):
        return "Backlog recommendation artifact_refs must include the canonical backlog JSON artifact."
    if canonical_artifact.content_json != payload.payload:
        return "Canonical backlog recommendation artifact content_json must exactly match payload."

    return None


def _render_governance_audit_markdown(
    *,
    ticket_id: str,
    output_schema_ref: str,
    result_payload: dict[str, Any],
) -> str:
    title = (
        str(result_payload.get("title") or "").strip()
        or f"{output_schema_ref} - {ticket_id}"
    )
    summary = str(result_payload.get("summary") or "").strip() or "未提供摘要。"
    decisions = [
        str(item).strip()
        for item in list(result_payload.get("decisions") or [])
        if str(item).strip()
    ]
    constraints = [
        str(item).strip()
        for item in list(result_payload.get("constraints") or [])
        if str(item).strip()
    ]
    sections = [
        dict(item)
        for item in list(result_payload.get("sections") or [])
        if isinstance(item, dict)
    ]

    lines = [
        f"# {title}",
        "",
        "## 摘要",
        summary,
        "",
        "## 关键决策",
    ]
    if decisions:
        lines.extend(f"{index}. {item}" for index, item in enumerate(decisions, start=1))
    else:
        lines.append("1. 无")
    lines.extend(["", "## 关键约束"])
    if constraints:
        lines.extend(f"{index}. {item}" for index, item in enumerate(constraints, start=1))
    else:
        lines.append("1. 无")
    lines.extend(["", "## 各节要点"])
    if not sections:
        lines.append("暂无分节内容。")
    for index, section in enumerate(sections, start=1):
        label = str(section.get("label") or f"Section {index}").strip()
        section_summary = str(section.get("summary") or "").strip()
        content_markdown = str(section.get("content_markdown") or "").strip()
        lines.extend(
            [
                "",
                f"### {index}. {label}",
            ]
        )
        if section_summary:
            lines.extend(
                [
                    "",
                    section_summary,
                ]
            )
        if content_markdown:
            lines.extend(
                [
                    "",
                    content_markdown,
                ]
            )
    return "\n".join(lines).rstrip() + "\n"


def _build_governance_audit_written_artifact(
    *,
    created_spec: dict[str, Any],
    payload: TicketResultSubmitCommand,
    written_artifacts: list[TicketWrittenArtifact],
) -> TicketWrittenArtifact | None:
    output_schema_ref = str(created_spec.get("output_schema_ref") or "").strip()
    result_payload = payload.payload if isinstance(payload.payload, dict) else {}
    if output_schema_ref not in GOVERNANCE_DOCUMENT_SCHEMA_REFS or not isinstance(result_payload, dict):
        return None

    written_artifacts_by_ref = {
        str(item.artifact_ref): item
        for item in written_artifacts
        if str(item.artifact_ref or "").strip()
    }
    primary_artifact: TicketWrittenArtifact | None = None
    for artifact_ref in list(payload.artifact_refs):
        candidate = written_artifacts_by_ref.get(str(artifact_ref))
        if candidate is None:
            continue
        if str(candidate.kind or "").upper() != "JSON":
            continue
        primary_artifact = candidate
        break
    if primary_artifact is None:
        return None

    primary_path = str(primary_artifact.path or "").strip()
    if not primary_path:
        return None
    audit_path = _governance_audit_sidecar_path(primary_path)
    if any(str(item.path or "").strip() == audit_path for item in written_artifacts):
        return None

    primary_artifact_ref = str(primary_artifact.artifact_ref or "").strip()
    audit_artifact_ref = _governance_audit_sidecar_ref(primary_artifact_ref)
    return TicketWrittenArtifact.model_validate(
        {
            "path": audit_path,
            "artifact_ref": audit_artifact_ref,
            "kind": "MARKDOWN",
            "content_text": _render_governance_audit_markdown(
                ticket_id=payload.ticket_id,
                output_schema_ref=output_schema_ref,
                result_payload=result_payload,
            ),
        }
    )


def _governance_audit_sidecar_path(primary_path: str) -> str:
    return (
        f"{primary_path[:-5]}.audit.md"
        if primary_path.endswith(".json")
        else f"{primary_path}.audit.md"
    )


def _governance_audit_sidecar_ref(primary_artifact_ref: str) -> str:
    return (
        f"{primary_artifact_ref[:-5]}.audit.md"
        if primary_artifact_ref.endswith(".json")
        else f"{primary_artifact_ref}.audit.md"
    )


def _is_allowed_auto_governance_audit_sidecar(
    item: TicketWrittenArtifact,
    *,
    governance_audit_artifact: TicketWrittenArtifact | None,
    submitted_artifacts: list[TicketWrittenArtifact],
    allowed_write_set: list[str],
) -> bool:
    if governance_audit_artifact is None:
        return False
    item_path = str(item.path or "").strip()
    audit_path = str(governance_audit_artifact.path or "").strip()
    if not item_path or item_path != audit_path:
        return False
    item_ref = str(item.artifact_ref or "").strip()
    audit_ref = str(governance_audit_artifact.artifact_ref or "").strip()
    if item_ref != audit_ref:
        return False

    for submitted in submitted_artifacts:
        primary_path = str(submitted.path or "").strip()
        if not primary_path or str(submitted.kind or "").upper() != "JSON":
            continue
        if _governance_audit_sidecar_path(primary_path) != item_path:
            continue
        primary_ref = str(submitted.artifact_ref or "").strip()
        if primary_ref and _governance_audit_sidecar_ref(primary_ref) != item_ref:
            continue
        return _match_allowed_write_set(primary_path, allowed_write_set)
    return False


def _developer_inspector_refs_for_ticket(ticket_id: str) -> DeveloperInspectorRefs:
    return DeveloperInspectorRefs(
        compiled_context_bundle_ref=f"ctx://compile/{ticket_id}",
        compile_manifest_ref=f"manifest://compile/{ticket_id}",
        rendered_execution_payload_ref=f"render://compile/{ticket_id}",
    )


def _ticket_context_terminal_state(repository: ControlPlaneRepository, ticket_id: str) -> dict[str, Any]:
    ticket = repository.get_current_ticket_projection(ticket_id)
    artifact_paths = [
        str(item.get("logical_path") or "").strip()
        for item in repository.list_ticket_artifacts(ticket_id)
        if str(item.get("logical_path") or "").strip()
    ]
    result_status = "executing"
    with repository.connection() as connection:
        terminal_event = repository.get_latest_ticket_terminal_event(connection, ticket_id)
    if terminal_event is not None:
        event_type = str(terminal_event.get("event_type") or "").strip()
        if event_type == EVENT_TICKET_COMPLETED:
            result_status = "completed"
        elif event_type == EVENT_TICKET_TIMED_OUT:
            result_status = "timed_out"
        elif event_type == EVENT_TICKET_FAILED:
            result_status = "failed"
    return {
        "status": str((ticket or {}).get("status") or "UNKNOWN"),
        "result_status": result_status,
        "artifact_paths": artifact_paths,
    }


def _refresh_ticket_context_archive(repository: ControlPlaneRepository, ticket_id: str) -> None:
    settings = get_settings()
    if settings.ticket_context_archive_root is None:
        return
    latest_execution_package = repository.get_latest_compiled_execution_package_by_ticket(ticket_id)
    if latest_execution_package is None:
        return
    latest_compile_manifest = repository.get_latest_compile_manifest_by_ticket(ticket_id)
    write_ticket_context_markdown(
        settings.ticket_context_archive_root,
        latest_execution_package.get("payload") or {},
        developer_inspector_refs=_developer_inspector_refs_for_ticket(ticket_id),
        compile_manifest=(latest_compile_manifest or {}).get("payload") or {},
        terminal_state={
            **_ticket_context_terminal_state(repository, ticket_id),
            "stale_against_latest": False,
        },
        provider_audit=latest_provider_audit_for_ticket(repository, ticket_id),
    )


def _resolve_dispatch_intent(created_spec: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(created_spec, dict):
        return {}
    dispatch_intent = created_spec.get("dispatch_intent")
    if not isinstance(dispatch_intent, dict):
        return {}
    return dispatch_intent


def _normalized_dependency_gate_refs(raw_refs: list[Any] | tuple[Any, ...] | None) -> list[str]:
    dependency_refs: list[str] = []
    seen_dependency_refs: set[str] = set()
    for raw_ref in raw_refs or ():
        normalized_ref = str(raw_ref or "").strip()
        if not normalized_ref or normalized_ref in seen_dependency_refs:
            continue
        dependency_refs.append(normalized_ref)
        seen_dependency_refs.add(normalized_ref)
    return dependency_refs


def _resolve_dependency_gate_refs(created_spec: dict[str, Any]) -> list[str]:
    return _normalized_dependency_gate_refs(_resolve_dispatch_intent(created_spec).get("dependency_gate_refs"))


def _resolve_dispatch_assignee_employee_id(created_spec: dict[str, Any]) -> str | None:
    assignee_employee_id = str(_resolve_dispatch_intent(created_spec).get("assignee_employee_id") or "").strip()
    return assignee_employee_id or None


def _resolve_dependency_ticket_refs(created_spec: dict[str, Any]) -> list[str]:
    dependency_refs = _resolve_dependency_gate_refs(created_spec)
    parent_ticket_id = str(created_spec.get("parent_ticket_id") or "").strip()
    if parent_ticket_id and parent_ticket_id not in dependency_refs:
        dependency_refs.append(parent_ticket_id)
    return dependency_refs


def _dependency_gate_would_create_cycle(
    repository: ControlPlaneRepository,
    connection,
    *,
    ticket_id: str,
    dependency_gate_refs: list[str],
) -> bool:
    pending_ticket_ids = list(dependency_gate_refs)
    seen_ticket_ids: set[str] = set()
    while pending_ticket_ids:
        dependency_ticket_id = pending_ticket_ids.pop()
        if dependency_ticket_id == ticket_id:
            return True
        if dependency_ticket_id in seen_ticket_ids:
            continue
        seen_ticket_ids.add(dependency_ticket_id)
        dependency_spec = repository.get_latest_ticket_created_payload(connection, dependency_ticket_id)
        if dependency_spec is None:
            continue
        pending_ticket_ids.extend(_resolve_dependency_ticket_refs(dependency_spec))
    return False


def _validate_ticket_dependency_gates(
    repository: ControlPlaneRepository,
    connection,
    *,
    workflow_id: str,
    ticket_id: str,
    dependency_gate_refs: list[str],
) -> str | None:
    for dependency_ticket_id in dependency_gate_refs:
        if dependency_ticket_id == ticket_id:
            return f"dispatch_intent.dependency_gate_refs cannot include ticket {ticket_id} itself."
        dependency_ticket = repository.get_current_ticket_projection(dependency_ticket_id, connection=connection)
        if dependency_ticket is None:
            return f"dispatch_intent.dependency_gate_refs ticket {dependency_ticket_id} does not exist."
        if str(dependency_ticket.get("workflow_id") or "") != workflow_id:
            return (
                "dispatch_intent.dependency_gate_refs must stay inside the current workflow; "
                f"{dependency_ticket_id} belongs to {dependency_ticket.get('workflow_id')}."
            )
    if _dependency_gate_would_create_cycle(
        repository,
        connection,
        ticket_id=ticket_id,
        dependency_gate_refs=dependency_gate_refs,
    ):
        return "dispatch_intent.dependency_gate_refs would create a dependency cycle."
    return None


def _build_scheduler_failure_event(
    repository: ControlPlaneRepository,
    connection,
    *,
    command_id: str,
    occurred_at: datetime,
    workflow_id: str,
    ticket_id: str,
    node_id: str,
    failure_payload: dict[str, Any],
    idempotency_key: str,
) -> dict | None:
    return repository.insert_event(
        connection,
        event_type=EVENT_TICKET_FAILED,
        actor_type="system",
        actor_id="scheduler",
        workflow_id=workflow_id,
        idempotency_key=idempotency_key,
        causation_id=command_id,
        correlation_id=workflow_id,
        payload={
            "ticket_id": ticket_id,
            "node_id": node_id,
            "failed_by": "scheduler",
            **failure_payload,
        },
        occurred_at=occurred_at,
    )


TIMEOUT_FAILURE_KINDS = {"TIMEOUT_SLA_EXCEEDED", "HEARTBEAT_TIMEOUT"}


def _resolve_ticket_lease_timeout_sec(created_spec: dict[str, Any]) -> int:
    return int(created_spec.get("lease_timeout_sec") or DEFAULT_LEASE_TIMEOUT_SEC)


def _resolve_timeout_repeat_threshold(created_spec: dict[str, Any]) -> int:
    escalation_policy = created_spec.get("escalation_policy") or {}
    return int(escalation_policy.get("timeout_repeat_threshold") or DEFAULT_TIMEOUT_REPEAT_THRESHOLD)


def _resolve_repeat_failure_threshold(created_spec: dict[str, Any]) -> int:
    escalation_policy = created_spec.get("escalation_policy") or {}
    return int(
        escalation_policy.get("repeat_failure_threshold") or DEFAULT_REPEAT_FAILURE_THRESHOLD
    )


def _resolve_timeout_backoff_multiplier(created_spec: dict[str, Any]) -> float:
    escalation_policy = created_spec.get("escalation_policy") or {}
    return float(
        escalation_policy.get("timeout_backoff_multiplier") or DEFAULT_TIMEOUT_BACKOFF_MULTIPLIER
    )


def _resolve_timeout_backoff_cap_multiplier(created_spec: dict[str, Any]) -> float:
    escalation_policy = created_spec.get("escalation_policy") or {}
    return float(
        escalation_policy.get("timeout_backoff_cap_multiplier")
        or DEFAULT_TIMEOUT_BACKOFF_CAP_MULTIPLIER
    )


def _resolve_timeout_fingerprint(workflow_id: str, node_id: str) -> str:
    return f"{workflow_id}:{node_id}:{TIMEOUT_FAMILY_RUNTIME}"


def _resolve_provider_fingerprint(provider_id: str) -> str:
    return f"{PROVIDER_FINGERPRINT_PREFIX}:{provider_id}"


def _resolve_repeated_failure_incident_fingerprint(
    workflow_id: str,
    node_id: str,
    failure_fingerprint: str,
) -> str:
    return f"{workflow_id}:{node_id}:repeat-failure:{failure_fingerprint}"


def _resolve_ticket_graph_unavailable_incident_fingerprint(
    workflow_id: str,
    source_component: str,
) -> str:
    return f"{workflow_id}:{INCIDENT_TYPE_TICKET_GRAPH_UNAVAILABLE}:{source_component}"


def _resolve_ceo_shadow_pipeline_failure_fingerprint(
    workflow_id: str,
    trigger_type: str,
    trigger_ref: str | None,
    source_stage: str,
    error_class: str,
) -> str:
    return f"{workflow_id}:{trigger_type}:{trigger_ref or 'none'}:{source_stage}:{error_class}"


def _resolve_graph_health_critical_incident_fingerprint(
    workflow_id: str,
    graph_version: str,
    finding_type: str,
    affected_nodes: list[str],
) -> str:
    normalized_nodes = ",".join(sorted(str(node_id).strip() for node_id in affected_nodes if str(node_id).strip()))
    return f"{workflow_id}:{graph_version}:{finding_type}:{normalized_nodes or 'workflow'}"


def _resolve_planned_placeholder_gate_blocked_incident_fingerprint(
    workflow_id: str,
    *,
    node_id: str,
    graph_version: str,
    source_component: str,
    reason_code: str,
) -> str:
    return f"{workflow_id}:{node_id}:{graph_version}:{source_component}:{reason_code}"


def _resolve_provider_id_for_ticket(
    repository: ControlPlaneRepository,
    connection,
    *,
    ticket: dict[str, Any] | None = None,
    lease_owner: str | None = None,
    failure_detail: dict[str, Any] | None = None,
) -> str | None:
    if failure_detail is not None:
        provider_id = failure_detail.get("provider_id")
        if provider_id:
            return str(provider_id)

    resolved_owner = lease_owner or (str(ticket["lease_owner"]) if ticket and ticket.get("lease_owner") else None)
    if resolved_owner is None:
        return None

    employee = repository.get_employee_projection(resolved_owner, connection=connection)
    if employee is None or not employee.get("provider_id"):
        return None
    return str(employee["provider_id"])


def _employee_is_active(
    repository: ControlPlaneRepository,
    connection,
    *,
    employee_id: str,
) -> bool:
    employee = repository.get_employee_projection(employee_id, connection=connection)
    return bool(employee is not None and str(employee.get("state") or "") == EMPLOYEE_STATE_ACTIVE)


def _is_provider_pause_failure(failure_kind: str) -> bool:
    return failure_kind in PROVIDER_PAUSE_FAILURE_KINDS


def _should_open_provider_incident_for_failure(failure_kind: str) -> bool:
    return _is_provider_pause_failure(failure_kind)


def _is_provider_paused(
    repository: ControlPlaneRepository,
    connection,
    provider_id: str | None,
) -> bool:
    if provider_id is None:
        return False
    return repository.has_open_circuit_breaker_for_provider(provider_id, connection=connection)


def _allow_paused_provider_start(provider_id: str | None) -> bool:
    if provider_id is None:
        return False
    config = resolve_runtime_provider_config()
    provider = find_provider_entry(config, provider_id)
    return provider is not None and provider.enabled


def _build_provider_candidate_chain(
    primary_selection,
    failover_selections: list[Any],
) -> list[str]:
    candidate_chain: list[str] = []
    for selection in [primary_selection, *failover_selections]:
        if selection is None:
            continue
        provider_id = str(selection.provider.provider_id)
        if provider_id not in candidate_chain:
            candidate_chain.append(provider_id)
    return candidate_chain


def _build_ticket_execution_precondition_fingerprint(
    *,
    ticket_id: str,
    reason_code: str,
    execution_target_ref: str,
    provider_effective_mode: str,
    provider_candidate_chain: list[str],
    provider_reason: str,
) -> str:
    fingerprint_source = {
        "ticket_id": ticket_id,
        "reason_code": reason_code,
        "execution_target_ref": execution_target_ref,
        "provider_effective_mode": provider_effective_mode,
        "provider_candidate_chain": list(provider_candidate_chain),
        "provider_reason": provider_reason,
    }
    digest = hashlib.sha256(
        json.dumps(fingerprint_source, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    return f"{ticket_id}:{reason_code}:{digest}"


def _evaluate_ticket_execution_precondition(
    repository: ControlPlaneRepository,
    connection,
    *,
    ticket: dict[str, Any],
    created_spec: dict[str, Any] | None,
    lease_owner: str | None,
) -> dict[str, Any] | None:
    if (
        isinstance(created_spec, dict)
        and isinstance(created_spec.get("meeting_context"), dict)
        and str(created_spec.get("output_schema_ref") or "") == CONSENSUS_DOCUMENT_SCHEMA_REF
    ):
        return None

    execution_target_ref = resolve_execution_target_ref_from_ticket_spec(created_spec)
    if execution_target_ref is None:
        return None

    config = resolve_runtime_provider_config()
    selection = resolve_provider_selection(
        config,
        target_ref=execution_target_ref,
        employee_provider_id=_resolve_provider_id_for_ticket(
            repository,
            connection,
            ticket=ticket,
            lease_owner=lease_owner,
        ),
        runtime_preference=(created_spec or {}).get("runtime_preference"),
    )
    if selection is None:
        unavailable_effective_mode = "PROVIDER_REQUIRED_UNAVAILABLE"
        provider_reason = "No live provider was available for runtime execution."
        provider_candidate_chain: list[str] = []
        return {
            "blocked": True,
            "reason_code": BLOCKING_REASON_PROVIDER_REQUIRED,
            "execution_target_ref": execution_target_ref,
            "provider_candidate_chain": provider_candidate_chain,
            "provider_effective_mode": unavailable_effective_mode,
            "provider_reason": provider_reason,
            "fingerprint": _build_ticket_execution_precondition_fingerprint(
                ticket_id=str(ticket["ticket_id"]),
                reason_code=BLOCKING_REASON_PROVIDER_REQUIRED,
                execution_target_ref=execution_target_ref,
                provider_effective_mode=unavailable_effective_mode,
                provider_candidate_chain=provider_candidate_chain,
                provider_reason=provider_reason,
            ),
        }

    failover_selections = resolve_provider_failover_selections(
        config,
        repository,
        target_ref=execution_target_ref,
        primary_selection=selection,
    )
    provider_candidate_chain = _build_provider_candidate_chain(selection, failover_selections)
    provider_effective_mode_value, effective_reason = provider_effective_mode(selection.provider, repository)
    provider_reason = effective_reason
    blocked = False
    if repository.has_open_circuit_breaker_for_provider(selection.provider.provider_id, connection=connection):
        blocked = True
        provider_reason = "Provider execution is currently paused by an open incident."
    elif selection.provider.adapter_kind == "openai_compat" and not all(
        (selection.provider.base_url, selection.provider.api_key, selection.actual_model or selection.provider.model)
    ):
        blocked = True
        provider_reason = "Provider config is incomplete for OpenAI Compat execution."
    elif selection.provider.adapter_kind == "claude_code_cli" and not all(
        (selection.provider.command_path, selection.actual_model or selection.provider.model)
    ):
        blocked = True
        provider_reason = "Provider config is incomplete for Claude Code execution."

    result = {
        "blocked": blocked,
        "reason_code": BLOCKING_REASON_PROVIDER_REQUIRED,
        "execution_target_ref": execution_target_ref,
        "provider_candidate_chain": provider_candidate_chain,
        "provider_effective_mode": provider_effective_mode_value,
        "provider_reason": provider_reason,
        "fingerprint": None,
    }
    if blocked:
        result["fingerprint"] = _build_ticket_execution_precondition_fingerprint(
            ticket_id=str(ticket["ticket_id"]),
            reason_code=BLOCKING_REASON_PROVIDER_REQUIRED,
            execution_target_ref=execution_target_ref,
            provider_effective_mode=provider_effective_mode_value,
            provider_candidate_chain=provider_candidate_chain,
            provider_reason=provider_reason,
        )
    return result


def _latest_ticket_execution_precondition_block_fingerprint(
    connection,
    *,
    workflow_id: str,
    ticket_id: str,
    reason_code: str,
) -> str | None:
    row = connection.execute(
        """
        SELECT payload_json
        FROM events
        WHERE workflow_id = ? AND event_type = ?
        ORDER BY sequence_no DESC
        """,
        (workflow_id, EVENT_TICKET_EXECUTION_PRECONDITION_BLOCKED),
    ).fetchall()
    for item in row:
        payload = json.loads(item["payload_json"])
        if (
            str(payload.get("ticket_id") or "") == ticket_id
            and str(payload.get("reason_code") or "") == reason_code
        ):
            fingerprint = str(payload.get("fingerprint") or "").strip()
            if fingerprint:
                return fingerprint
    return None


def _sync_ticket_execution_precondition_state(
    repository: ControlPlaneRepository,
    connection,
    *,
    command_id: str,
    occurred_at: datetime,
    workflow_id: str,
    ticket: dict[str, Any],
    node_id: str,
    precondition_result: dict[str, Any] | None,
    actor_id: str,
) -> bool:
    if precondition_result is None:
        return False

    current_ticket = repository.get_current_ticket_projection(str(ticket["ticket_id"]), connection=connection)
    current_node = repository.get_current_node_projection(workflow_id, node_id, connection=connection)
    current_blocking_reason = str(
        (current_ticket or {}).get("blocking_reason_code")
        or (current_node or {}).get("blocking_reason_code")
        or ""
    ).strip()

    if precondition_result["blocked"]:
        event_row = repository.insert_event(
            connection,
            event_type=EVENT_TICKET_EXECUTION_PRECONDITION_BLOCKED,
            actor_type="system",
            actor_id=actor_id,
            workflow_id=workflow_id,
            idempotency_key=(
                f"ticket-precondition-blocked:{workflow_id}:{ticket['ticket_id']}:"
                f"{precondition_result['reason_code']}:{precondition_result['fingerprint']}"
            ),
            causation_id=command_id,
            correlation_id=workflow_id,
            payload={
                "ticket_id": ticket["ticket_id"],
                "node_id": node_id,
                "reason_code": precondition_result["reason_code"],
                "execution_target_ref": precondition_result["execution_target_ref"],
                "provider_candidate_chain": list(precondition_result["provider_candidate_chain"]),
                "provider_effective_mode": precondition_result["provider_effective_mode"],
                "provider_reason": precondition_result["provider_reason"],
                "fingerprint": precondition_result["fingerprint"],
            },
            occurred_at=occurred_at,
        )
        if event_row is not None:
            repository.refresh_projections(connection)
        return True

    if current_blocking_reason != BLOCKING_REASON_PROVIDER_REQUIRED:
        return False

    previous_fingerprint = _latest_ticket_execution_precondition_block_fingerprint(
        connection,
        workflow_id=workflow_id,
        ticket_id=str(ticket["ticket_id"]),
        reason_code=BLOCKING_REASON_PROVIDER_REQUIRED,
    )
    if not previous_fingerprint:
        return False

    event_row = repository.insert_event(
        connection,
        event_type=EVENT_TICKET_EXECUTION_PRECONDITION_CLEARED,
        actor_type="system",
        actor_id=actor_id,
        workflow_id=workflow_id,
        idempotency_key=(
            f"ticket-precondition-cleared:{workflow_id}:{ticket['ticket_id']}:"
            f"{BLOCKING_REASON_PROVIDER_REQUIRED}:{previous_fingerprint}"
        ),
        causation_id=command_id,
        correlation_id=workflow_id,
        payload={
            "ticket_id": ticket["ticket_id"],
            "node_id": node_id,
            "reason_code": BLOCKING_REASON_PROVIDER_REQUIRED,
            "execution_target_ref": precondition_result["execution_target_ref"],
            "provider_candidate_chain": list(precondition_result["provider_candidate_chain"]),
            "provider_effective_mode": precondition_result["provider_effective_mode"],
            "provider_reason": precondition_result["provider_reason"],
            "previous_fingerprint": previous_fingerprint,
        },
        occurred_at=occurred_at,
    )
    if event_row is not None:
        repository.refresh_projections(connection)
    return False


def _resolve_timeout_root_created_spec(
    repository: ControlPlaneRepository,
    connection,
    created_spec: dict[str, Any],
) -> dict[str, Any]:
    root_spec = created_spec
    parent_ticket_id = created_spec.get("parent_ticket_id")
    seen_ticket_ids: set[str] = set()
    while parent_ticket_id and parent_ticket_id not in seen_ticket_ids:
        seen_ticket_ids.add(parent_ticket_id)
        parent_spec = repository.get_latest_ticket_created_payload(connection, parent_ticket_id)
        if parent_spec is None:
            break
        root_spec = parent_spec
        parent_ticket_id = parent_spec.get("parent_ticket_id")
    return root_spec


def _apply_timeout_backoff(current_value: int, root_value: int, multiplier: float, cap_multiplier: float) -> int:
    increased_value = int(current_value * multiplier)
    capped_value = int(root_value * cap_multiplier)
    return max(current_value, min(increased_value, capped_value))


def _calculate_timeout_streak(
    repository: ControlPlaneRepository,
    connection,
    *,
    workflow_id: str,
    node_id: str,
    created_spec: dict[str, Any],
) -> int:
    streak = 1
    parent_ticket_id = created_spec.get("parent_ticket_id")
    seen_ticket_ids: set[str] = set()

    while parent_ticket_id and parent_ticket_id not in seen_ticket_ids:
        seen_ticket_ids.add(parent_ticket_id)
        parent_spec = repository.get_latest_ticket_created_payload(connection, parent_ticket_id)
        if parent_spec is None:
            break
        if parent_spec.get("workflow_id") != workflow_id or parent_spec.get("node_id") != node_id:
            break
        terminal_event = repository.get_latest_ticket_terminal_event(connection, parent_ticket_id)
        if terminal_event is None or terminal_event["event_type"] != EVENT_TICKET_TIMED_OUT:
            break
        if terminal_event["payload"].get("failure_kind") not in TIMEOUT_FAILURE_KINDS:
            break
        streak += 1
        parent_ticket_id = parent_spec.get("parent_ticket_id")

    return streak


def _calculate_failure_streak(
    repository: ControlPlaneRepository,
    connection,
    *,
    workflow_id: str,
    node_id: str,
    created_spec: dict[str, Any],
    failure_fingerprint: str,
) -> int:
    streak = 1
    parent_ticket_id = created_spec.get("parent_ticket_id")
    seen_ticket_ids: set[str] = set()

    while parent_ticket_id and parent_ticket_id not in seen_ticket_ids:
        seen_ticket_ids.add(parent_ticket_id)
        parent_spec = repository.get_latest_ticket_created_payload(connection, parent_ticket_id)
        if parent_spec is None:
            break
        if parent_spec.get("workflow_id") != workflow_id or parent_spec.get("node_id") != node_id:
            break
        terminal_event = repository.get_latest_ticket_terminal_event(connection, parent_ticket_id)
        if terminal_event is None or terminal_event["event_type"] != EVENT_TICKET_FAILED:
            break
        parent_failure_kind = str(terminal_event["payload"].get("failure_kind") or "")
        if _is_provider_pause_failure(parent_failure_kind):
            break
        if terminal_event["payload"].get("failure_fingerprint") != failure_fingerprint:
            break
        streak += 1
        parent_ticket_id = parent_spec.get("parent_ticket_id")

    return streak


def _retry_budget(current_ticket: dict[str, Any], created_spec: dict[str, Any]) -> int:
    return int(created_spec.get("retry_budget") or current_ticket.get("retry_budget") or 0)


def _retry_count(current_ticket: dict[str, Any], created_spec: dict[str, Any]) -> int:
    return int(current_ticket.get("retry_count") or created_spec.get("retry_count") or 0)


def _resolve_heartbeat_timeout_sec(current_ticket: dict[str, Any]) -> int:
    return int(current_ticket.get("heartbeat_timeout_sec") or DEFAULT_LEASE_TIMEOUT_SEC)


def _delivery_stage_parent_completed(
    repository: ControlPlaneRepository,
    connection,
    created_spec: dict[str, Any],
) -> bool:
    delivery_stage = str(created_spec.get("delivery_stage") or "").strip()
    parent_ticket_id = str(created_spec.get("parent_ticket_id") or "").strip()
    if not delivery_stage or not parent_ticket_id:
        return True
    current_node_id = str(created_spec.get("node_id") or "").strip()
    parent_ticket = repository.get_current_ticket_projection(parent_ticket_id, connection=connection)
    if parent_ticket is None:
        return False
    parent_node_id = str(parent_ticket.get("node_id") or "").strip()
    if current_node_id and parent_node_id and current_node_id == parent_node_id:
        return True
    if parent_ticket["status"] != TICKET_STATUS_COMPLETED:
        return False
    parent_workflow_id = str(parent_ticket.get("workflow_id") or created_spec.get("workflow_id") or "").strip()
    if not parent_node_id or not parent_workflow_id:
        return True
    parent_node = repository.get_current_node_projection(
        parent_workflow_id,
        parent_node_id,
        connection=connection,
    )
    return parent_node is not None and parent_node["status"] == NODE_STATUS_COMPLETED


def _evaluate_delivery_stage_parent_dependency(
    repository: ControlPlaneRepository,
    connection,
    *,
    created_spec: dict[str, Any],
) -> tuple[bool, dict[str, Any] | None]:
    delivery_stage = str(created_spec.get("delivery_stage") or "").strip()
    parent_ticket_id = str(created_spec.get("parent_ticket_id") or "").strip()
    if not delivery_stage or not parent_ticket_id:
        return True, None
    current_node_id = str(created_spec.get("node_id") or "").strip()
    parent_ticket = repository.get_current_ticket_projection(parent_ticket_id, connection=connection)
    if parent_ticket is None:
        return False, _build_failure_payload(
            failure_kind=DEPENDENCY_GATE_INVALID_FAILURE_KIND,
            failure_message="Delivery-stage parent ticket is missing.",
            failure_detail={
                "dependency_ticket_id": parent_ticket_id,
                "dependency_type": "delivery_stage_parent",
            },
        )
    parent_node_id = str(parent_ticket.get("node_id") or "").strip()
    if current_node_id and parent_node_id and current_node_id == parent_node_id:
        return True, None
    parent_workflow_id = str(parent_ticket.get("workflow_id") or created_spec.get("workflow_id") or "").strip()
    parent_node = (
        repository.get_current_node_projection(
            parent_workflow_id,
            parent_node_id,
            connection=connection,
        )
        if parent_node_id and parent_workflow_id
        else None
    )
    if parent_node is not None:
        if parent_node["status"] == NODE_STATUS_COMPLETED:
            return True, None
        if parent_node["status"] == NODE_STATUS_CANCELLED:
            return False, _build_failure_payload(
                failure_kind=UPSTREAM_DEPENDENCY_UNHEALTHY_FAILURE_KIND,
                failure_message="Delivery-stage parent node was cancelled.",
                failure_detail={
                    "dependency_ticket_id": parent_ticket_id,
                    "dependency_status": parent_node["status"],
                    "dependency_type": "delivery_stage_parent",
                },
            )
        if str(parent_node.get("latest_ticket_id") or "") != parent_ticket_id:
            return False, None
    if parent_ticket["status"] == TICKET_STATUS_CANCELLED:
        return False, _build_failure_payload(
            failure_kind=UPSTREAM_DEPENDENCY_UNHEALTHY_FAILURE_KIND,
            failure_message="Delivery-stage parent ticket is no longer healthy.",
            failure_detail={
                "dependency_ticket_id": parent_ticket_id,
                "dependency_status": parent_ticket["status"],
                "dependency_type": "delivery_stage_parent",
            },
        )
    if parent_ticket["status"] != TICKET_STATUS_COMPLETED:
        return False, None
    parent_created_spec = repository.get_latest_ticket_created_payload(connection, parent_ticket_id) or {}
    parent_gate_result = evaluate_ticket_required_hook_gate(
        repository,
        ticket=parent_ticket,
        created_spec=parent_created_spec,
        connection=connection,
    )
    if parent_gate_result.status == HookGateStatus.BLOCKED:
        return False, None
    if not parent_node_id or not parent_workflow_id:
        return True, None
    if parent_node is None:
        return False, _build_failure_payload(
            failure_kind=DEPENDENCY_GATE_INVALID_FAILURE_KIND,
            failure_message="Delivery-stage parent node projection is missing.",
            failure_detail={
                "dependency_ticket_id": parent_ticket_id,
                "dependency_type": "delivery_stage_parent",
            },
        )
    return parent_node["status"] == NODE_STATUS_COMPLETED, None


def _evaluate_dispatch_dependency_gates(
    repository: ControlPlaneRepository,
    connection,
    *,
    created_spec: dict[str, Any],
) -> tuple[bool, dict[str, Any] | None]:
    for dependency_ticket_id in _resolve_dependency_gate_refs(created_spec):
        dependency_ticket = repository.get_current_ticket_projection(dependency_ticket_id, connection=connection)
        if dependency_ticket is None:
            return False, _build_failure_payload(
                failure_kind=DEPENDENCY_GATE_INVALID_FAILURE_KIND,
                failure_message="Dependency gate ticket is missing.",
                failure_detail={
                    "dependency_ticket_id": dependency_ticket_id,
                    "dependency_type": "dispatch_intent_gate",
                },
            )
        dependency_status = str(dependency_ticket.get("status") or "")
        if dependency_status in DEPENDENCY_TERMINAL_FAILURE_STATUSES:
            recovery_state = _dependency_gate_recovery_state(
                repository,
                connection,
                dependency_ticket_id=dependency_ticket_id,
            )
            if recovery_state == "blocked":
                return False, None
            if recovery_state == "satisfied":
                continue
            return False, _build_failure_payload(
                failure_kind=DEPENDENCY_GATE_UNHEALTHY_FAILURE_KIND,
                failure_message="Dependency gate ticket is no longer healthy.",
                failure_detail={
                    "dependency_ticket_id": dependency_ticket_id,
                    "dependency_status": dependency_status,
                    "dependency_type": "dispatch_intent_gate",
                },
            )
        if dependency_status != TICKET_STATUS_COMPLETED:
            return False, None
        dependency_created_spec = repository.get_latest_ticket_created_payload(connection, dependency_ticket_id) or {}
        dependency_gate_result = evaluate_ticket_required_hook_gate(
            repository,
            ticket=dependency_ticket,
            created_spec=dependency_created_spec,
            connection=connection,
        )
        if dependency_gate_result.status == HookGateStatus.BLOCKED:
            return False, None
    return True, None


DEPENDENCY_GATE_RECOVERY_BLOCKING_STATUSES = {
    TICKET_STATUS_PENDING,
    TICKET_STATUS_LEASED,
    TICKET_STATUS_EXECUTING,
    TICKET_STATUS_BLOCKED_FOR_BOARD_REVIEW,
    TICKET_STATUS_REWORK_REQUIRED,
}

DEPENDENCY_GATE_RESTORE_AND_RETRY_ACTIONS = {
    IncidentFollowupAction.RESTORE_AND_RETRY_LATEST_FAILURE.value,
    IncidentFollowupAction.RESTORE_AND_RETRY_LATEST_TIMEOUT.value,
    IncidentFollowupAction.RESTORE_AND_RETRY_LATEST_PROVIDER_FAILURE.value,
    IncidentFollowupAction.RESTORE_AND_RETRY_LATEST_STAFFING_CONTAINMENT.value,
}


def _dependency_gate_recovery_state(
    repository: ControlPlaneRepository,
    connection,
    *,
    dependency_ticket_id: str,
) -> str | None:
    incident = repository.get_latest_incident_for_ticket(
        dependency_ticket_id,
        statuses=[INCIDENT_STATUS_OPEN, INCIDENT_STATUS_RECOVERING],
        connection=connection,
    )
    if incident is None:
        return None

    restore_action = str((incident.get("payload") or {}).get("followup_action") or "").strip() or None
    if incident["incident_type"] == INCIDENT_TYPE_CEO_SHADOW_PIPELINE_FAILED:
        source_ticket_context = resolve_ceo_shadow_source_ticket_context(
            repository,
            incident,
            connection=connection,
        )
        restore_action = source_ticket_context["recommended_restore_action"] or restore_action

    if restore_action not in DEPENDENCY_GATE_RESTORE_AND_RETRY_ACTIONS:
        return None

    incident_status = str(incident.get("status") or "").strip()
    if incident_status == INCIDENT_STATUS_OPEN:
        return "blocked"
    if incident_status != INCIDENT_STATUS_RECOVERING:
        return None

    followup_ticket_id = str((incident.get("payload") or {}).get("followup_ticket_id") or "").strip()
    if not followup_ticket_id:
        return "blocked"

    followup_ticket = repository.get_current_ticket_projection(followup_ticket_id, connection=connection)
    if followup_ticket is None:
        return None

    followup_status = str(followup_ticket.get("status") or "").strip()
    if followup_status == TICKET_STATUS_COMPLETED:
        return "satisfied"
    if followup_status in DEPENDENCY_GATE_RECOVERY_BLOCKING_STATUSES:
        return "blocked"
    return None


def _expected_primary_artifact_ref(created_spec: dict[str, Any], ticket_id: str) -> str | None:
    output_schema_ref = str(created_spec.get("output_schema_ref") or "").strip()
    if output_schema_ref == DELIVERY_CHECK_REPORT_SCHEMA_REF:
        return f"art://runtime/{ticket_id}/delivery-check-report.json"
    if output_schema_ref == DELIVERY_CLOSEOUT_PACKAGE_SCHEMA_REF:
        return f"art://runtime/{ticket_id}/delivery-closeout-package.json"
    if output_schema_ref == CONSENSUS_DOCUMENT_SCHEMA_REF:
        return f"art://runtime/{ticket_id}/consensus-document.json"
    return None


def _delivery_stage_rank(created_spec: dict[str, Any]) -> int:
    delivery_stage = str(created_spec.get("delivery_stage") or "").strip()
    return {
        "BUILD": 0,
        "CHECK": 1,
        "REVIEW": 2,
        "CLOSEOUT": 3,
    }.get(delivery_stage, 99)


def _replace_process_asset_refs_for_ticket_replacements(
    refs: list[str],
    *,
    ticket_replacements: dict[str, str],
) -> list[str]:
    replaced_refs: list[str] = []
    for process_asset_ref in refs:
        normalized_ref = str(process_asset_ref).strip()
        if not normalized_ref:
            continue
        try:
            kind, target = parse_process_asset_ref(normalized_ref)
        except ValueError:
            replaced_refs.append(normalized_ref)
            continue
        replacement_ticket_id = ticket_replacements.get(target)
        if replacement_ticket_id is None:
            replaced_refs.append(normalized_ref)
            continue
        if kind == "compiled-context-bundle":
            replaced_refs.append(build_compiled_context_bundle_process_asset_ref(replacement_ticket_id))
        elif kind == "compile-manifest":
            replaced_refs.append(build_compile_manifest_process_asset_ref(replacement_ticket_id))
        elif kind == "compiled-execution-package":
            replaced_refs.append(build_compiled_execution_package_process_asset_ref(replacement_ticket_id))
        elif kind == "meeting-decision-record":
            replaced_refs.append(build_meeting_decision_process_asset_ref(replacement_ticket_id))
        elif kind == "source-code-delivery":
            replaced_refs.append(build_source_code_delivery_process_asset_ref(replacement_ticket_id))
        elif kind == "closeout-summary":
            replaced_refs.append(build_closeout_summary_process_asset_ref(replacement_ticket_id))
        elif kind == "governance-document":
            replaced_refs.append(build_governance_document_process_asset_ref(replacement_ticket_id))
        else:
            replaced_refs.append(normalized_ref)
    return dedupe_process_asset_refs(replaced_refs)


def _recreate_pending_delivery_descendants_for_retry(
    *,
    repository: ControlPlaneRepository,
    connection,
    command_id: str,
    occurred_at: datetime,
    workflow_id: str,
    failed_ticket_id: str,
    replacement_ticket_id: str,
    replacement_created_spec: dict[str, Any],
    idempotency_key_base: str,
) -> None:
    current_node_id = str(replacement_created_spec.get("node_id") or "").strip()
    ticket_replacements = {failed_ticket_id: replacement_ticket_id}
    artifact_replacements: dict[str, str] = {}
    lineage_ticket_id = failed_ticket_id
    seen_ticket_ids: set[str] = set()
    while lineage_ticket_id and lineage_ticket_id not in seen_ticket_ids:
        seen_ticket_ids.add(lineage_ticket_id)
        ticket_replacements[lineage_ticket_id] = replacement_ticket_id
        old_artifact_ref = _expected_primary_artifact_ref(replacement_created_spec, lineage_ticket_id)
        new_artifact_ref = _expected_primary_artifact_ref(replacement_created_spec, replacement_ticket_id)
        if old_artifact_ref and new_artifact_ref:
            artifact_replacements[old_artifact_ref] = new_artifact_ref
        lineage_created_spec = repository.get_latest_ticket_created_payload(connection, lineage_ticket_id)
        if lineage_created_spec is None:
            break
        parent_ticket_id = str(lineage_created_spec.get("parent_ticket_id") or "").strip()
        if not parent_ticket_id:
            break
        parent_spec = repository.get_latest_ticket_created_payload(connection, parent_ticket_id)
        if parent_spec is None:
            break
        if (
            str(parent_spec.get("workflow_id") or "").strip() != workflow_id
            or str(parent_spec.get("node_id") or "").strip() != current_node_id
        ):
            break
        lineage_ticket_id = parent_ticket_id

    pending_tickets = [
        ticket
        for ticket in repository.list_ticket_projections_by_statuses(connection, [TICKET_STATUS_PENDING])
        if ticket["workflow_id"] == workflow_id
    ]
    pending_specs: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for ticket in pending_tickets:
        created_spec = repository.get_latest_ticket_created_payload(connection, ticket["ticket_id"])
        if created_spec is None:
            continue
        pending_specs.append((ticket, created_spec))

    pending_specs.sort(key=lambda item: (_delivery_stage_rank(item[1]), item[0]["updated_at"], item[0]["ticket_id"]))

    for ticket, created_spec in pending_specs:
        parent_ticket_id = str(created_spec.get("parent_ticket_id") or "").strip()
        if parent_ticket_id not in ticket_replacements:
            continue

        next_ticket_id = new_prefixed_id("tkt")
        _insert_ticket_cancelled_event(
            repository=repository,
            connection=connection,
            command_id=command_id,
            occurred_at=occurred_at,
            workflow_id=workflow_id,
            ticket_id=str(ticket["ticket_id"]),
            node_id=str(ticket["node_id"]),
            cancelled_by="incident-recovery",
            reason=(
                f"Superseded by retry follow-up ticket {next_ticket_id} after incident recovery "
                f"for {replacement_ticket_id}."
            ),
            idempotency_key=f"{idempotency_key_base}:cancel-descendant:{ticket['ticket_id']}",
        )
        next_created_spec = {
            **created_spec,
            "ticket_id": next_ticket_id,
            "parent_ticket_id": ticket_replacements[parent_ticket_id],
            "idempotency_key": f"incident-recovery-recreate:{workflow_id}:{next_ticket_id}",
            "allowed_write_set": rebind_ticket_id_in_allowed_write_set(
                list(created_spec.get("allowed_write_set") or []),
                previous_ticket_id=str(ticket["ticket_id"]),
                next_ticket_id=next_ticket_id,
            ),
            "input_artifact_refs": [
                artifact_replacements.get(str(artifact_ref), str(artifact_ref))
                for artifact_ref in (created_spec.get("input_artifact_refs") or [])
            ],
            "input_process_asset_refs": merge_input_process_asset_refs(
                existing_process_asset_refs=_replace_process_asset_refs_for_ticket_replacements(
                    list(created_spec.get("input_process_asset_refs") or []),
                    ticket_replacements=ticket_replacements,
                ),
                artifact_refs=[
                    artifact_replacements.get(str(artifact_ref), str(artifact_ref))
                    for artifact_ref in (created_spec.get("input_artifact_refs") or [])
                ],
            ),
        }
        next_created_spec = _ensure_ticket_execution_contract_payload(next_created_spec)
        created_event = repository.insert_event(
            connection,
            event_type=EVENT_TICKET_CREATED,
            actor_type="operator",
            actor_id="incident-recovery",
            workflow_id=workflow_id,
            idempotency_key=f"{idempotency_key_base}:recreate-descendant:{ticket['ticket_id']}",
            causation_id=command_id,
            correlation_id=workflow_id,
            payload=next_created_spec,
            occurred_at=occurred_at,
        )
        if created_event is None:
            raise RuntimeError("Incident recovery descendant recreation idempotency conflict.")

        ticket_replacements[ticket["ticket_id"]] = next_ticket_id
        old_ref = _expected_primary_artifact_ref(created_spec, ticket["ticket_id"])
        new_ref = _expected_primary_artifact_ref(created_spec, next_ticket_id)
        if old_ref and new_ref:
            artifact_replacements[old_ref] = new_ref


def _resolve_current_heartbeat_expiry(
    current_ticket: dict[str, Any],
) -> datetime | None:
    heartbeat_expires_at = current_ticket.get("heartbeat_expires_at")
    if heartbeat_expires_at is not None:
        return heartbeat_expires_at

    heartbeat_timeout_sec = current_ticket.get("heartbeat_timeout_sec")
    if heartbeat_timeout_sec is None:
        return None

    last_signal_at = (
        current_ticket.get("last_heartbeat_at")
        or current_ticket.get("started_at")
        or current_ticket.get("updated_at")
    )
    if last_signal_at is None:
        return None

    return last_signal_at + timedelta(seconds=int(heartbeat_timeout_sec))


def _should_retry_failure(
    *,
    current_ticket: dict[str, Any],
    created_spec: dict[str, Any],
    failure_kind: str,
) -> bool:
    retry_budget = _retry_budget(current_ticket, created_spec)
    retry_count = _retry_count(current_ticket, created_spec)
    if retry_count >= retry_budget:
        return False

    escalation_policy = created_spec.get("escalation_policy") or {}
    if failure_kind == "SCHEMA_ERROR":
        return escalation_policy.get("on_schema_error") == "retry"
    return retry_budget > retry_count


def _should_retry_timeout(
    *,
    current_ticket: dict[str, Any],
    created_spec: dict[str, Any],
) -> bool:
    retry_budget = _retry_budget(current_ticket, created_spec)
    retry_count = _retry_count(current_ticket, created_spec)
    if retry_count >= retry_budget:
        return False
    escalation_policy = created_spec.get("escalation_policy") or {}
    return escalation_policy.get("on_timeout") == "retry"


def _should_escalate_repeat_failure(
    *,
    created_spec: dict[str, Any],
    failure_kind: str,
    failure_streak_count: int,
) -> bool:
    if _is_provider_pause_failure(failure_kind):
        return False
    escalation_policy = created_spec.get("escalation_policy") or {}
    return (
        escalation_policy.get("on_repeat_failure") == "escalate_ceo"
        and failure_streak_count >= _resolve_repeat_failure_threshold(created_spec)
    )


def _validate_restore_and_retry_followup(
    *,
    repository: ControlPlaneRepository,
    connection,
    incident: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    incident_ticket_id = incident.get("ticket_id")
    if incident_ticket_id is None:
        raise ValueError(f"Incident {incident['incident_id']} is missing its source ticket.")

    latest_terminal_event = repository.get_latest_ticket_terminal_event(connection, incident_ticket_id)
    if latest_terminal_event is None:
        raise ValueError(
            f"Incident {incident['incident_id']} cannot restore and retry because the source ticket "
            "has no terminal event."
        )
    if latest_terminal_event["event_type"] != EVENT_TICKET_TIMED_OUT:
        raise ValueError(
            f"Incident {incident['incident_id']} cannot restore and retry because the latest terminal "
            "event is not a timeout."
        )

    created_spec = repository.get_latest_ticket_created_payload(connection, incident_ticket_id)
    if created_spec is None:
        raise ValueError(
            f"Incident {incident['incident_id']} cannot restore and retry because the source ticket "
            "created spec is missing."
        )

    current_ticket = repository.get_current_ticket_projection(incident_ticket_id, connection=connection)
    if current_ticket is None:
        raise ValueError(
            f"Incident {incident['incident_id']} cannot restore and retry because the source ticket "
            "projection is missing."
        )

    return current_ticket, created_spec


def _validate_restore_and_retry_failure_followup(
    *,
    repository: ControlPlaneRepository,
    connection,
    incident: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    incident_ticket_id = incident.get("ticket_id")
    if incident_ticket_id is None:
        raise ValueError(f"Incident {incident['incident_id']} is missing its source ticket.")

    latest_terminal_event = repository.get_latest_ticket_terminal_event(connection, incident_ticket_id)
    if latest_terminal_event is None:
        raise ValueError(
            f"Incident {incident['incident_id']} cannot restore and retry because the source ticket "
            "has no terminal event."
        )
    if latest_terminal_event["event_type"] != EVENT_TICKET_FAILED:
        raise ValueError(
            f"Incident {incident['incident_id']} cannot restore and retry because the latest terminal "
            "event is not an ordinary failure."
        )

    latest_failure_kind = str(latest_terminal_event["payload"].get("failure_kind") or "")
    if _is_provider_pause_failure(latest_failure_kind):
        raise ValueError(
            f"Incident {incident['incident_id']} cannot restore and retry because the latest terminal "
            "event is not an ordinary failure."
        )

    created_spec = repository.get_latest_ticket_created_payload(connection, incident_ticket_id)
    if created_spec is None:
        raise ValueError(
            f"Incident {incident['incident_id']} cannot restore and retry because the source ticket "
            "created spec is missing."
        )

    current_ticket = repository.get_current_ticket_projection(incident_ticket_id, connection=connection)
    if current_ticket is None:
        raise ValueError(
            f"Incident {incident['incident_id']} cannot restore and retry because the source ticket "
            "projection is missing."
        )

    return current_ticket, created_spec


def _validate_restore_and_retry_provider_followup(
    *,
    repository: ControlPlaneRepository,
    connection,
    incident: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    incident_ticket_id = incident.get("ticket_id")
    if incident_ticket_id is None:
        raise ValueError(f"Incident {incident['incident_id']} is missing its source ticket.")

    latest_terminal_event = repository.get_latest_ticket_terminal_event(connection, incident_ticket_id)
    if latest_terminal_event is None:
        raise ValueError(
            f"Incident {incident['incident_id']} cannot restore and retry because the source ticket "
            "has no terminal event."
        )
    if latest_terminal_event["event_type"] != EVENT_TICKET_FAILED:
        raise ValueError(
            f"Incident {incident['incident_id']} cannot restore and retry because the latest terminal "
            "event is not a provider failure."
        )
    latest_failure_kind = latest_terminal_event["payload"].get("failure_kind")
    if not _is_provider_pause_failure(str(latest_failure_kind)):
        raise ValueError(
            f"Incident {incident['incident_id']} cannot restore and retry because the latest terminal "
            "event is not a provider failure."
        )

    created_spec = repository.get_latest_ticket_created_payload(connection, incident_ticket_id)
    if created_spec is None:
        raise ValueError(
            f"Incident {incident['incident_id']} cannot restore and retry because the source ticket "
            "created spec is missing."
        )

    current_ticket = repository.get_current_ticket_projection(incident_ticket_id, connection=connection)
    if current_ticket is None:
        raise ValueError(
            f"Incident {incident['incident_id']} cannot restore and retry because the source ticket "
            "projection is missing."
        )

    return current_ticket, created_spec


def _validate_restore_and_retry_staffing_followup(
    *,
    repository: ControlPlaneRepository,
    connection,
    incident: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    incident_ticket_id = incident.get("ticket_id")
    if incident_ticket_id is None:
        raise ValueError(f"Incident {incident['incident_id']} is missing its source ticket.")

    created_spec = repository.get_latest_ticket_created_payload(connection, incident_ticket_id)
    if created_spec is None:
        raise ValueError(
            f"Incident {incident['incident_id']} cannot restore and retry because the source ticket "
            "created spec is missing."
        )

    current_ticket = repository.get_current_ticket_projection(incident_ticket_id, connection=connection)
    if current_ticket is None:
        raise ValueError(
            f"Incident {incident['incident_id']} cannot restore and retry because the source ticket "
            "projection is missing."
        )
    if current_ticket["status"] not in {TICKET_STATUS_CANCEL_REQUESTED, TICKET_STATUS_CANCELLED}:
        raise ValueError(
            f"Incident {incident['incident_id']} cannot restore and retry because the source ticket "
            "is not contained in a recoverable cancellation state."
        )

    return current_ticket, created_spec


def _schedule_staffing_recovery_followup(
    *,
    repository: ControlPlaneRepository,
    connection,
    command_id: str,
    occurred_at: datetime,
    workflow_id: str,
    source_ticket: dict[str, Any],
    created_spec: dict[str, Any],
    idempotency_key_base: str,
) -> str:
    source_ticket_id = str(source_ticket["ticket_id"])
    node_id = str(source_ticket["node_id"])
    if source_ticket["status"] == TICKET_STATUS_CANCEL_REQUESTED:
        cancelled_event = repository.insert_event(
            connection,
            event_type=EVENT_TICKET_CANCELLED,
            actor_type="operator",
            actor_id="incident-recovery",
            workflow_id=workflow_id,
            idempotency_key=f"{idempotency_key_base}:staffing-cancelled:{source_ticket_id}",
            causation_id=command_id,
            correlation_id=workflow_id,
            payload={
                "ticket_id": source_ticket_id,
                "node_id": node_id,
                "cancelled_by": "incident-recovery",
                "reason": "Staffing containment recovery superseded the contained execution attempt.",
            },
            occurred_at=occurred_at,
        )
        if cancelled_event is None:
            raise RuntimeError("Staffing containment cancellation idempotency conflict.")

    next_ticket_id = new_prefixed_id("tkt")
    next_ticket_payload = {
        **created_spec,
        "ticket_id": next_ticket_id,
        "parent_ticket_id": source_ticket_id,
        "attempt_no": int(created_spec.get("attempt_no") or 1) + 1,
        "idempotency_key": f"staffing-recovery-create:{workflow_id}:{next_ticket_id}",
    }
    next_ticket_payload["staffing_recovery"] = {
        "recovered_from_ticket_id": source_ticket_id,
        "recovered_at": occurred_at.isoformat(),
    }
    next_ticket_payload = _ensure_ticket_execution_contract_payload(next_ticket_payload)
    created_event = repository.insert_event(
        connection,
        event_type=EVENT_TICKET_CREATED,
        actor_type="operator",
        actor_id="incident-recovery",
        workflow_id=workflow_id,
        idempotency_key=f"{idempotency_key_base}:staffing-recovery-create:{next_ticket_id}",
        causation_id=command_id,
        correlation_id=workflow_id,
        payload=next_ticket_payload,
        occurred_at=occurred_at,
    )
    if created_event is None:
        raise RuntimeError("Staffing containment follow-up ticket creation idempotency conflict.")
    return next_ticket_id


def _schedule_retry(
    *,
    repository: ControlPlaneRepository,
    connection,
    command_id: str,
    occurred_at: datetime,
    workflow_id: str,
    failed_ticket_id: str,
    node_id: str,
    created_spec: dict[str, Any],
    failure_payload: dict[str, Any],
    retry_source_event_type: str,
    idempotency_key_base: str,
) -> str:
    next_ticket_id = new_prefixed_id("tkt")
    next_attempt_no = int(created_spec.get("attempt_no") or 1) + 1
    next_retry_count = int(created_spec.get("retry_count") or 0) + 1

    retry_event = repository.insert_event(
        connection,
        event_type=EVENT_TICKET_RETRY_SCHEDULED,
        actor_type="system",
        actor_id="scheduler",
        workflow_id=workflow_id,
        idempotency_key=f"{idempotency_key_base}:retry-scheduled:{failed_ticket_id}",
        causation_id=command_id,
        correlation_id=workflow_id,
        payload={
            "ticket_id": failed_ticket_id,
            "node_id": node_id,
            "next_ticket_id": next_ticket_id,
            "next_attempt_no": next_attempt_no,
            "retry_count": next_retry_count,
            "retry_source_event_type": retry_source_event_type,
            "failure_fingerprint": failure_payload["failure_fingerprint"],
        },
        occurred_at=occurred_at,
    )
    if retry_event is None:
        raise RuntimeError("Retry scheduling idempotency conflict.")

    next_ticket_payload = {
        **created_spec,
        "ticket_id": next_ticket_id,
        "parent_ticket_id": failed_ticket_id,
        "attempt_no": next_attempt_no,
        "retry_count": next_retry_count,
        "allowed_write_set": rebind_ticket_id_in_allowed_write_set(
            list(created_spec.get("allowed_write_set") or []),
            previous_ticket_id=failed_ticket_id,
            next_ticket_id=next_ticket_id,
        ),
        "idempotency_key": f"system-retry-create:{workflow_id}:{next_ticket_id}",
    }
    if retry_source_event_type == EVENT_TICKET_TIMED_OUT:
        root_spec = _resolve_timeout_root_created_spec(repository, connection, created_spec)
        next_ticket_payload["timeout_sla_sec"] = _apply_timeout_backoff(
            int(created_spec.get("timeout_sla_sec") or 0),
            int(root_spec.get("timeout_sla_sec") or 0),
            _resolve_timeout_backoff_multiplier(created_spec),
            _resolve_timeout_backoff_cap_multiplier(created_spec),
        )
        next_ticket_payload["lease_timeout_sec"] = _apply_timeout_backoff(
            _resolve_ticket_lease_timeout_sec(created_spec),
            _resolve_ticket_lease_timeout_sec(root_spec),
            _resolve_timeout_backoff_multiplier(created_spec),
            _resolve_timeout_backoff_cap_multiplier(created_spec),
        )
    next_ticket_payload = _ensure_ticket_execution_contract_payload(next_ticket_payload)
    created_event = repository.insert_event(
        connection,
        event_type=EVENT_TICKET_CREATED,
        actor_type="system",
        actor_id="scheduler",
        workflow_id=workflow_id,
        idempotency_key=f"{idempotency_key_base}:retry-create:{next_ticket_id}",
        causation_id=command_id,
        correlation_id=workflow_id,
        payload=next_ticket_payload,
        occurred_at=occurred_at,
    )
    if created_event is None:
        raise RuntimeError("Retry ticket creation idempotency conflict.")
    return next_ticket_id


def _build_decomposition_recovery_ticket_spec(
    *,
    source_created_spec: dict[str, Any],
    source_ticket_id: str,
    planned: dict[str, Any],
    dependency_gate_refs: list[str],
    occurred_at: datetime,
) -> dict[str, Any]:
    retry_budget = int(source_created_spec.get("retry_budget") or 0)
    escalation_policy = dict(source_created_spec.get("escalation_policy") or {})
    return {
        **source_created_spec,
        "ticket_id": planned["ticket_id"],
        "node_id": planned["node_id"],
        "parent_ticket_id": source_ticket_id,
        "attempt_no": 1,
        "retry_count": 0,
        "role_profile_ref": planned["role_profile_ref"],
        "summary": planned["summary"],
        "input_artifact_refs": list(planned["input_artifact_refs"]),
        "context_query_plan": {
            "keywords": list(planned.get("context_keywords") or []),
            "semantic_queries": [str(planned.get("semantic_query") or planned["summary"])],
            "max_context_tokens": int(
                ((source_created_spec.get("context_query_plan") or {}).get("max_context_tokens") or 3000)
            ),
        },
        "acceptance_criteria": list(planned["acceptance_criteria"]),
        "output_schema_ref": planned["output_schema_ref"],
        "output_schema_version": planned["output_schema_version"],
        "allowed_tools": list(source_created_spec.get("allowed_tools") or ["read_artifact", "write_artifact"]),
        "allowed_write_set": list(planned["allowed_write_set"]),
        "retry_budget": retry_budget,
        "escalation_policy": escalation_policy,
        "dispatch_intent": {
            **dict(source_created_spec.get("dispatch_intent") or {}),
            "dependency_gate_refs": list(dependency_gate_refs),
        },
        "decomposition_recovery": {
            "source_ticket_id": source_ticket_id,
            "source_node_id": source_created_spec.get("node_id"),
            "created_at": occurred_at.isoformat(),
        },
        "idempotency_key": f"decomposition-recovery-create:{planned['ticket_id']}",
    }


def _open_decomposition_recovery_incident(
    *,
    repository: ControlPlaneRepository,
    connection,
    command_id: str,
    occurred_at: datetime,
    workflow_id: str,
    ticket_id: str,
    node_id: str,
    created_spec: dict[str, Any],
    failure_payload: dict[str, Any],
    idempotency_key_base: str,
) -> str | None:
    existing_incident = repository.get_open_incident_for_node(workflow_id, node_id, connection=connection)
    if existing_incident is not None:
        return None

    incident_id = new_prefixed_id("inc")
    blocked_reason: str | None = None
    decomposition_plan: dict[str, Any] | None = None
    created_segment_ticket_ids: list[str] = []
    aggregator_ticket_id: str | None = None
    try:
        decomposition_plan = build_decomposition_recovery_plan(
            workflow_id=workflow_id,
            source_ticket_id=ticket_id,
            source_node_id=node_id,
            created_spec=created_spec,
            failure_payload=failure_payload,
        )
        ticket_specs = build_decomposition_ticket_specs(
            decomposition_plan,
            build_ticket_spec=lambda planned, dependency_gate_refs: _build_decomposition_recovery_ticket_spec(
                source_created_spec=created_spec,
                source_ticket_id=ticket_id,
                planned=planned,
                dependency_gate_refs=dependency_gate_refs,
                occurred_at=occurred_at,
            ),
        )
        for ticket_spec in ticket_specs:
            created_ticket_id = _insert_followup_ticket_created_event(
                repository=repository,
                connection=connection,
                command_id=command_id,
                occurred_at=occurred_at,
                workflow_id=workflow_id,
                ticket_payload=ticket_spec,
                idempotency_key=f"{idempotency_key_base}:decomposition-recovery-create:{ticket_spec['ticket_id']}",
                actor_id="decomposition-recovery",
            )
            if created_ticket_id == decomposition_plan["aggregator"]["ticket_id"]:
                aggregator_ticket_id = created_ticket_id
            else:
                created_segment_ticket_ids.append(created_ticket_id)
        recovery_status = "CREATED"
        incident_status = INCIDENT_STATUS_OPEN
    except ValueError as exc:
        blocked_reason = str(exc)
        recovery_status = "BLOCKED"
        incident_status = INCIDENT_STATUS_OPEN

    recovery_payload = {
        "source_ticket_id": ticket_id,
        "source_node_id": node_id,
        "source_output_schema_ref": created_spec.get("output_schema_ref"),
        "source_output_schema_version": created_spec.get("output_schema_version"),
        "failure_kind": failure_payload["failure_kind"],
        "failure_fingerprint": failure_payload["failure_fingerprint"],
        "recovery_policy": "decompose_failed_ticket_without_retry",
        "recovery_status": recovery_status,
        "blocked_reason": blocked_reason,
        "decomposition_decision": (
            {key: decomposition_plan[key] for key in (
                "decision_kind",
                "reason",
                "evidence_refs",
                "target_output_schema_ref",
                "target_output_schema_version",
                "uses_provider_hidden_state",
            )}
            if decomposition_plan is not None
            else None
        ),
        "decomposition_plan": decomposition_plan,
        "created_segment_ticket_ids": created_segment_ticket_ids,
        "aggregator_ticket_id": aggregator_ticket_id,
    }
    incident_payload = {
        "incident_id": incident_id,
        "ticket_id": ticket_id,
        "node_id": node_id,
        "incident_type": INCIDENT_TYPE_DECOMPOSITION_RECOVERY,
        "severity": "high",
        "status": incident_status,
        "fingerprint": f"{workflow_id}:{node_id}:decomposition-recovery:{failure_payload['failure_fingerprint']}",
        "opened_at": occurred_at.isoformat(),
        "summary": "Ticket failure requires explicit decomposition recovery instead of retrying the same large ticket.",
        "failure_kind": failure_payload["failure_kind"],
        "failure_message": failure_payload["failure_message"],
        "failure_fingerprint": failure_payload["failure_fingerprint"],
        "decomposition_recovery": recovery_payload,
    }
    incident_event = repository.insert_event(
        connection,
        event_type=EVENT_INCIDENT_OPENED,
        actor_type="system",
        actor_id="decomposition-recovery",
        workflow_id=workflow_id,
        idempotency_key=f"{idempotency_key_base}:decomposition-recovery-incident:{ticket_id}",
        causation_id=command_id,
        correlation_id=workflow_id,
        payload=incident_payload,
        occurred_at=occurred_at,
    )
    if incident_event is None:
        raise RuntimeError("Decomposition recovery incident idempotency conflict.")
    return aggregator_ticket_id


def _auto_close_recovering_incidents_for_completed_ticket(
    *,
    repository: ControlPlaneRepository,
    connection,
    command_id: str,
    occurred_at: datetime,
    workflow_id: str,
    completed_ticket_id: str,
) -> None:
    incidents = repository.list_recovering_incidents_for_followup_ticket(
        connection,
        completed_ticket_id,
    )
    for incident in incidents:
        event_row = repository.insert_event(
            connection,
            event_type=EVENT_INCIDENT_CLOSED,
            actor_type="system",
            actor_id="runtime",
            workflow_id=workflow_id,
            idempotency_key=f"auto-close-incident:{incident['incident_id']}:{completed_ticket_id}",
            causation_id=command_id,
            correlation_id=workflow_id,
            payload={
                "incident_id": incident["incident_id"],
                "ticket_id": completed_ticket_id,
                "node_id": incident.get("node_id"),
                "provider_id": incident.get("provider_id"),
                "status": INCIDENT_STATUS_CLOSED,
                "followup_action": (incident.get("payload") or {}).get("followup_action"),
                "followup_ticket_id": completed_ticket_id,
                "auto_closed_by": "runtime",
                "close_reason": "Follow-up ticket completed successfully.",
                "incident_type": incident["incident_type"],
            },
            occurred_at=occurred_at,
        )
        if event_row is None:
            raise RuntimeError("Recovering incident auto-close idempotency conflict.")


def _open_timeout_incident(
    *,
    repository: ControlPlaneRepository,
    connection,
    command_id: str,
    occurred_at: datetime,
    workflow_id: str,
    ticket_id: str,
    node_id: str,
    timeout_streak_count: int,
    failure_payload: dict[str, Any],
    idempotency_key_base: str,
) -> str:
    existing_incident = repository.get_open_incident_for_node(workflow_id, node_id, connection=connection)
    if existing_incident is not None:
        return str(existing_incident["incident_id"])

    incident_id = new_prefixed_id("inc")
    fingerprint = _resolve_timeout_fingerprint(workflow_id, node_id)
    incident_payload = {
        "incident_id": incident_id,
        "ticket_id": ticket_id,
        "node_id": node_id,
        "incident_type": INCIDENT_TYPE_RUNTIME_TIMEOUT_ESCALATION,
        "status": INCIDENT_STATUS_OPEN,
        "severity": "high",
        "fingerprint": fingerprint,
        "timeout_streak_count": timeout_streak_count,
        "latest_failure_kind": failure_payload.get("failure_kind"),
        "latest_failure_message": failure_payload.get("failure_message"),
        "latest_failure_fingerprint": failure_payload.get("failure_fingerprint"),
    }
    incident_event = repository.insert_event(
        connection,
        event_type=EVENT_INCIDENT_OPENED,
        actor_type="system",
        actor_id="scheduler",
        workflow_id=workflow_id,
        idempotency_key=f"{idempotency_key_base}:incident-opened:{ticket_id}",
        causation_id=command_id,
        correlation_id=workflow_id,
        payload=incident_payload,
        occurred_at=occurred_at,
    )
    if incident_event is None:
        raise RuntimeError("Incident opening idempotency conflict.")

    breaker_event = repository.insert_event(
        connection,
        event_type=EVENT_CIRCUIT_BREAKER_OPENED,
        actor_type="system",
        actor_id="scheduler",
        workflow_id=workflow_id,
        idempotency_key=f"{idempotency_key_base}:circuit-breaker-opened:{ticket_id}",
        causation_id=command_id,
        correlation_id=workflow_id,
        payload={
            "incident_id": incident_id,
            "ticket_id": ticket_id,
            "node_id": node_id,
            "circuit_breaker_state": CIRCUIT_BREAKER_STATE_OPEN,
            "fingerprint": fingerprint,
        },
        occurred_at=occurred_at,
    )
    if breaker_event is None:
        raise RuntimeError("Circuit breaker opening idempotency conflict.")

    return incident_id


def _open_repeated_failure_incident(
    *,
    repository: ControlPlaneRepository,
    connection,
    command_id: str,
    occurred_at: datetime,
    workflow_id: str,
    ticket_id: str,
    node_id: str,
    failure_streak_count: int,
    failure_payload: dict[str, Any],
    idempotency_key_base: str,
) -> str:
    existing_incident = repository.get_open_incident_for_node(workflow_id, node_id, connection=connection)
    if existing_incident is not None:
        return str(existing_incident["incident_id"])

    incident_id = new_prefixed_id("inc")
    failure_fingerprint = str(failure_payload.get("failure_fingerprint") or "unknown-failure")
    incident_payload = {
        "incident_id": incident_id,
        "ticket_id": ticket_id,
        "node_id": node_id,
        "incident_type": INCIDENT_TYPE_REPEATED_FAILURE_ESCALATION,
        "status": INCIDENT_STATUS_OPEN,
        "severity": "high",
        "fingerprint": _resolve_repeated_failure_incident_fingerprint(
            workflow_id,
            node_id,
            failure_fingerprint,
        ),
        "failure_streak_count": failure_streak_count,
        "latest_failure_kind": failure_payload.get("failure_kind"),
        "latest_failure_message": failure_payload.get("failure_message"),
        "latest_failure_fingerprint": failure_fingerprint,
    }
    incident_event = repository.insert_event(
        connection,
        event_type=EVENT_INCIDENT_OPENED,
        actor_type="system",
        actor_id="runtime",
        workflow_id=workflow_id,
        idempotency_key=f"{idempotency_key_base}:incident-opened:{ticket_id}",
        causation_id=command_id,
        correlation_id=workflow_id,
        payload=incident_payload,
        occurred_at=occurred_at,
    )
    if incident_event is None:
        raise RuntimeError("Repeated failure incident opening idempotency conflict.")

    breaker_event = repository.insert_event(
        connection,
        event_type=EVENT_CIRCUIT_BREAKER_OPENED,
        actor_type="system",
        actor_id="runtime",
        workflow_id=workflow_id,
        idempotency_key=f"{idempotency_key_base}:circuit-breaker-opened:{ticket_id}",
        causation_id=command_id,
        correlation_id=workflow_id,
        payload={
            "incident_id": incident_id,
            "ticket_id": ticket_id,
            "node_id": node_id,
            "circuit_breaker_state": CIRCUIT_BREAKER_STATE_OPEN,
            "fingerprint": incident_payload["fingerprint"],
        },
        occurred_at=occurred_at,
    )
    if breaker_event is None:
        raise RuntimeError("Repeated failure circuit breaker opening idempotency conflict.")

    return incident_id


def _open_provider_incident(
    *,
    repository: ControlPlaneRepository,
    connection,
    command_id: str,
    occurred_at: datetime,
    workflow_id: str,
    ticket_id: str,
    node_id: str,
    provider_id: str,
    failure_payload: dict[str, Any],
    idempotency_key_base: str,
) -> str:
    existing_incident = repository.get_open_incident_for_provider(provider_id, connection=connection)
    if existing_incident is not None:
        return str(existing_incident["incident_id"])

    incident_id = new_prefixed_id("inc")
    fingerprint = _resolve_provider_fingerprint(provider_id)
    incident_payload = {
        "incident_id": incident_id,
        "ticket_id": ticket_id,
        "node_id": node_id,
        "provider_id": provider_id,
        "incident_type": INCIDENT_TYPE_PROVIDER_EXECUTION_PAUSED,
        "status": INCIDENT_STATUS_OPEN,
        "severity": "high",
        "fingerprint": fingerprint,
        "pause_reason": failure_payload.get("failure_kind"),
        "latest_failure_kind": failure_payload.get("failure_kind"),
        "latest_failure_message": failure_payload.get("failure_message"),
        "latest_failure_fingerprint": failure_payload.get("failure_fingerprint"),
    }
    incident_event = repository.insert_event(
        connection,
        event_type=EVENT_INCIDENT_OPENED,
        actor_type="system",
        actor_id="runtime",
        workflow_id=workflow_id,
        idempotency_key=f"{idempotency_key_base}:incident-opened:{ticket_id}",
        causation_id=command_id,
        correlation_id=workflow_id,
        payload=incident_payload,
        occurred_at=occurred_at,
    )
    if incident_event is None:
        raise RuntimeError("Provider incident opening idempotency conflict.")

    breaker_event = repository.insert_event(
        connection,
        event_type=EVENT_CIRCUIT_BREAKER_OPENED,
        actor_type="system",
        actor_id="runtime",
        workflow_id=workflow_id,
        idempotency_key=f"{idempotency_key_base}:circuit-breaker-opened:{ticket_id}",
        causation_id=command_id,
        correlation_id=workflow_id,
        payload={
            "incident_id": incident_id,
            "ticket_id": ticket_id,
            "node_id": node_id,
            "provider_id": provider_id,
            "circuit_breaker_state": CIRCUIT_BREAKER_STATE_OPEN,
            "fingerprint": fingerprint,
        },
        occurred_at=occurred_at,
    )
    if breaker_event is None:
        raise RuntimeError("Provider circuit breaker opening idempotency conflict.")

    return incident_id


def open_ticket_graph_unavailable_incident(
    repository: ControlPlaneRepository,
    *,
    workflow_id: str,
    source_component: str,
    error: Exception,
    idempotency_key_base: str,
    actor_id: str = "autopilot-controller",
) -> str:
    command_id = new_prefixed_id("cmd")
    occurred_at = now_local()
    fingerprint = _resolve_ticket_graph_unavailable_incident_fingerprint(workflow_id, source_component)

    with repository.transaction() as connection:
        existing_row = connection.execute(
            """
            SELECT incident_id
            FROM incident_projection
            WHERE workflow_id = ? AND fingerprint = ? AND status = ?
            ORDER BY opened_at DESC, incident_id DESC
            LIMIT 1
            """,
            (workflow_id, fingerprint, INCIDENT_STATUS_OPEN),
        ).fetchone()
        if existing_row is not None:
            return str(existing_row["incident_id"])

        incident_id = new_prefixed_id("inc")
        incident_payload = {
            "incident_id": incident_id,
            "ticket_id": None,
            "node_id": None,
            "incident_type": INCIDENT_TYPE_TICKET_GRAPH_UNAVAILABLE,
            "status": INCIDENT_STATUS_OPEN,
            "severity": "high",
            "fingerprint": fingerprint,
            "source_component": source_component,
            "source_stage": "ticket_graph_snapshot",
            "error_class": error.__class__.__name__,
            "error_message": str(error),
        }
        incident_event = repository.insert_event(
            connection,
            event_type=EVENT_INCIDENT_OPENED,
            actor_type="system",
            actor_id=actor_id,
            workflow_id=workflow_id,
            idempotency_key=f"{idempotency_key_base}:incident-opened:{source_component}",
            causation_id=command_id,
            correlation_id=workflow_id,
            payload=incident_payload,
            occurred_at=occurred_at,
        )
        if incident_event is None:
            raise RuntimeError("Ticket graph unavailable incident opening idempotency conflict.")

        breaker_event = repository.insert_event(
            connection,
            event_type=EVENT_CIRCUIT_BREAKER_OPENED,
            actor_type="system",
            actor_id=actor_id,
            workflow_id=workflow_id,
            idempotency_key=f"{idempotency_key_base}:circuit-breaker-opened:{source_component}",
            causation_id=command_id,
            correlation_id=workflow_id,
            payload={
                "incident_id": incident_id,
                "ticket_id": None,
                "node_id": None,
                "circuit_breaker_state": CIRCUIT_BREAKER_STATE_OPEN,
                "fingerprint": fingerprint,
            },
            occurred_at=occurred_at,
        )
        if breaker_event is None:
            raise RuntimeError("Ticket graph unavailable circuit breaker opening idempotency conflict.")

        repository.refresh_projections(connection)
        return incident_id


def open_planned_placeholder_gate_blocked_incident(
    repository: ControlPlaneRepository,
    *,
    workflow_id: str,
    blocked_placeholder: PlannedPlaceholderGateBlock,
    trigger_type: str,
    trigger_ref: str | None,
    idempotency_key_base: str,
    actor_id: str = "autopilot-controller",
) -> str:
    command_id = new_prefixed_id("cmd")
    occurred_at = now_local()
    fingerprint = _resolve_planned_placeholder_gate_blocked_incident_fingerprint(
        workflow_id,
        node_id=blocked_placeholder.node_id,
        graph_version=blocked_placeholder.graph_version,
        source_component=blocked_placeholder.source_component,
        reason_code=blocked_placeholder.reason_code,
    )

    with repository.transaction() as connection:
        existing_row = connection.execute(
            """
            SELECT incident_id
            FROM incident_projection
            WHERE workflow_id = ? AND fingerprint = ? AND status = ?
            ORDER BY opened_at DESC, incident_id DESC
            LIMIT 1
            """,
            (workflow_id, fingerprint, INCIDENT_STATUS_OPEN),
        ).fetchone()
        if existing_row is not None:
            return str(existing_row["incident_id"])

        incident_id = new_prefixed_id("inc")
        incident_payload = {
            "incident_id": incident_id,
            "ticket_id": None,
            "node_id": blocked_placeholder.node_id,
            "incident_type": INCIDENT_TYPE_PLANNED_PLACEHOLDER_GATE_BLOCKED,
            "status": INCIDENT_STATUS_OPEN,
            "severity": "high",
            "fingerprint": fingerprint,
            "reason_code": blocked_placeholder.reason_code,
            "graph_node_id": blocked_placeholder.graph_node_id,
            "graph_version": blocked_placeholder.graph_version,
            "source_component": blocked_placeholder.source_component,
            "trigger_type": trigger_type,
            "trigger_ref": trigger_ref,
            "materialization_hint": blocked_placeholder.materialization_hint,
        }
        incident_event = repository.insert_event(
            connection,
            event_type=EVENT_INCIDENT_OPENED,
            actor_type="system",
            actor_id=actor_id,
            workflow_id=workflow_id,
            idempotency_key=f"{idempotency_key_base}:incident-opened:planned-placeholder",
            causation_id=command_id,
            correlation_id=workflow_id,
            payload=incident_payload,
            occurred_at=occurred_at,
        )
        if incident_event is None:
            raise RuntimeError("Planned placeholder gate incident opening idempotency conflict.")

        breaker_event = repository.insert_event(
            connection,
            event_type=EVENT_CIRCUIT_BREAKER_OPENED,
            actor_type="system",
            actor_id=actor_id,
            workflow_id=workflow_id,
            idempotency_key=f"{idempotency_key_base}:circuit-breaker-opened:planned-placeholder",
            causation_id=command_id,
            correlation_id=workflow_id,
            payload={
                "incident_id": incident_id,
                "ticket_id": None,
                "node_id": blocked_placeholder.node_id,
                "circuit_breaker_state": CIRCUIT_BREAKER_STATE_OPEN,
                "fingerprint": fingerprint,
            },
            occurred_at=occurred_at,
        )
        if breaker_event is None:
            raise RuntimeError("Planned placeholder gate circuit breaker opening idempotency conflict.")

        repository.refresh_projections(connection)
        return incident_id


def open_graph_health_critical_incident(
    repository: ControlPlaneRepository,
    *,
    workflow_id: str,
    report: dict[str, Any],
    idempotency_key_base: str,
    actor_id: str = "autopilot-controller",
) -> str | None:
    return _open_monitor_critical_incident(
        repository,
        workflow_id=workflow_id,
        report=report,
        idempotency_key_base=idempotency_key_base,
        actor_id=actor_id,
        incident_type=INCIDENT_TYPE_GRAPH_HEALTH_CRITICAL,
        incident_label="Graph health",
    )


def open_runtime_liveness_critical_incident(
    repository: ControlPlaneRepository,
    *,
    workflow_id: str,
    report: dict[str, Any],
    idempotency_key_base: str,
    actor_id: str = "autopilot-controller",
) -> str | None:
    return _open_monitor_critical_incident(
        repository,
        workflow_id=workflow_id,
        report=report,
        idempotency_key_base=idempotency_key_base,
        actor_id=actor_id,
        incident_type=INCIDENT_TYPE_RUNTIME_LIVENESS_CRITICAL,
        incident_label="Runtime liveness",
    )


def _open_monitor_critical_incident(
    repository: ControlPlaneRepository,
    *,
    workflow_id: str,
    report: dict[str, Any],
    idempotency_key_base: str,
    actor_id: str,
    incident_type: str,
    incident_label: str,
) -> str | None:
    if str(report.get("overall_health") or "") != "CRITICAL":
        return None
    findings = [
        item
        for item in list(report.get("findings") or [])
        if str(item.get("severity") or "").upper() == "CRITICAL"
    ]
    if not findings:
        return None
    primary_finding = dict(findings[0])
    graph_version = str(report.get("graph_version") or "").strip()
    if not graph_version:
        raise ValueError("Graph health report is missing graph_version.")
    finding_type = str(primary_finding.get("finding_type") or "").strip()
    if not finding_type:
        raise ValueError("Graph health report is missing finding_type.")
    affected_nodes = [
        str(node_id).strip()
        for node_id in list(primary_finding.get("affected_nodes") or [])
        if str(node_id).strip()
    ]
    affected_graph_node_ids = [
        str(node_id).strip()
        for node_id in list(primary_finding.get("affected_graph_node_ids") or [])
        if str(node_id).strip()
    ]
    fingerprint = _resolve_graph_health_critical_incident_fingerprint(
        workflow_id,
        graph_version,
        finding_type,
        affected_nodes,
    )
    command_id = new_prefixed_id("cmd")
    occurred_at = now_local()

    with repository.transaction() as connection:
        existing_row = connection.execute(
            """
            SELECT incident_id
            FROM incident_projection
            WHERE workflow_id = ? AND fingerprint = ? AND status = ?
            ORDER BY opened_at DESC, incident_id DESC
            LIMIT 1
            """,
            (workflow_id, fingerprint, INCIDENT_STATUS_OPEN),
        ).fetchone()
        if existing_row is not None:
            return str(existing_row["incident_id"])

        incident_id = new_prefixed_id("inc")
        linked_node_id = affected_nodes[0] if len(affected_nodes) == 1 else None
        linked_ticket_id = None
        if linked_node_id:
            node_projection = repository.get_current_node_projection(
                workflow_id,
                linked_node_id,
                connection=connection,
            )
            if node_projection is not None:
                linked_ticket_id = str(node_projection.get("latest_ticket_id") or "").strip() or None
        incident_payload = {
            "incident_id": incident_id,
            "ticket_id": linked_ticket_id,
            "node_id": linked_node_id,
            "incident_type": incident_type,
            "status": INCIDENT_STATUS_OPEN,
            "severity": "high",
            "fingerprint": fingerprint,
            "report_id": report.get("report_id"),
            "graph_version": graph_version,
            "finding_type": finding_type,
            "affected_nodes": affected_nodes,
            "affected_graph_node_ids": affected_graph_node_ids,
            "metric_value": primary_finding.get("metric_value"),
            "threshold": primary_finding.get("threshold"),
            "description": primary_finding.get("description"),
            "recommended_actions": list(report.get("recommended_actions") or []),
            "trigger_type": SCHEDULER_IDLE_MAINTENANCE_TRIGGER,
            "trigger_ref": graph_version,
        }
        incident_event = repository.insert_event(
            connection,
            event_type=EVENT_INCIDENT_OPENED,
            actor_type="system",
            actor_id=actor_id,
            workflow_id=workflow_id,
            idempotency_key=f"{idempotency_key_base}:incident-opened:{finding_type}",
            causation_id=command_id,
            correlation_id=workflow_id,
            payload=incident_payload,
            occurred_at=occurred_at,
        )
        if incident_event is None:
            raise RuntimeError(f"{incident_label} critical incident opening idempotency conflict.")

        breaker_event = repository.insert_event(
            connection,
            event_type=EVENT_CIRCUIT_BREAKER_OPENED,
            actor_type="system",
            actor_id=actor_id,
            workflow_id=workflow_id,
            idempotency_key=f"{idempotency_key_base}:circuit-breaker-opened:{finding_type}",
            causation_id=command_id,
            correlation_id=workflow_id,
            payload={
                "incident_id": incident_id,
                "ticket_id": linked_ticket_id,
                "node_id": linked_node_id,
                "circuit_breaker_state": CIRCUIT_BREAKER_STATE_OPEN,
                "fingerprint": fingerprint,
            },
            occurred_at=occurred_at,
        )
        if breaker_event is None:
            raise RuntimeError(f"{incident_label} critical circuit breaker opening idempotency conflict.")

        repository.refresh_projections(connection)
        return incident_id


def open_runtime_liveness_unavailable_incident(
    repository: ControlPlaneRepository,
    *,
    workflow_id: str,
    error: Exception,
    idempotency_key_base: str,
    actor_id: str = "autopilot-controller",
) -> str:
    command_id = new_prefixed_id("cmd")
    occurred_at = now_local()
    fingerprint = (
        f"{workflow_id}:runtime-liveness:{error.__class__.__name__}:{str(error).strip() or 'error'}"
    )

    with repository.transaction() as connection:
        existing_row = connection.execute(
            """
            SELECT incident_id
            FROM incident_projection
            WHERE workflow_id = ? AND fingerprint = ? AND status = ?
            ORDER BY opened_at DESC, incident_id DESC
            LIMIT 1
            """,
            (workflow_id, fingerprint, INCIDENT_STATUS_OPEN),
        ).fetchone()
        if existing_row is not None:
            return str(existing_row["incident_id"])

        incident_id = new_prefixed_id("inc")
        incident_payload = {
            "incident_id": incident_id,
            "ticket_id": None,
            "node_id": None,
            "incident_type": INCIDENT_TYPE_RUNTIME_LIVENESS_UNAVAILABLE,
            "status": INCIDENT_STATUS_OPEN,
            "severity": "high",
            "fingerprint": fingerprint,
            "source_component": "runtime_liveness_report",
            "source_stage": "runtime_liveness_report",
            "error_class": error.__class__.__name__,
            "error_message": str(error),
        }
        incident_event = repository.insert_event(
            connection,
            event_type=EVENT_INCIDENT_OPENED,
            actor_type="system",
            actor_id=actor_id,
            workflow_id=workflow_id,
            idempotency_key=f"{idempotency_key_base}:incident-opened:runtime-liveness",
            causation_id=command_id,
            correlation_id=workflow_id,
            payload=incident_payload,
            occurred_at=occurred_at,
        )
        if incident_event is None:
            raise RuntimeError("Runtime liveness unavailable incident opening idempotency conflict.")

        breaker_event = repository.insert_event(
            connection,
            event_type=EVENT_CIRCUIT_BREAKER_OPENED,
            actor_type="system",
            actor_id=actor_id,
            workflow_id=workflow_id,
            idempotency_key=f"{idempotency_key_base}:circuit-breaker-opened:runtime-liveness",
            causation_id=command_id,
            correlation_id=workflow_id,
            payload={
                "incident_id": incident_id,
                "ticket_id": None,
                "node_id": None,
                "circuit_breaker_state": CIRCUIT_BREAKER_STATE_OPEN,
                "fingerprint": fingerprint,
            },
            occurred_at=occurred_at,
        )
        if breaker_event is None:
            raise RuntimeError("Runtime liveness unavailable circuit breaker opening idempotency conflict.")

        repository.refresh_projections(connection)
        return incident_id


def open_ceo_shadow_pipeline_failed_incident(
    repository: ControlPlaneRepository,
    *,
    workflow_id: str,
    error: CeoShadowPipelineError,
    idempotency_key_base: str,
    actor_id: str = "ceo-shadow-trigger",
) -> str:
    command_id = new_prefixed_id("cmd")
    occurred_at = now_local()
    fingerprint = _resolve_ceo_shadow_pipeline_failure_fingerprint(
        workflow_id,
        error.trigger_type,
        error.trigger_ref,
        error.source_stage,
        error.error_class,
    )

    with repository.transaction() as connection:
        existing_row = connection.execute(
            """
            SELECT incident_id
            FROM incident_projection
            WHERE workflow_id = ? AND fingerprint = ? AND status = ?
            ORDER BY opened_at DESC, incident_id DESC
            LIMIT 1
            """,
            (workflow_id, fingerprint, INCIDENT_STATUS_OPEN),
        ).fetchone()
        if existing_row is not None:
            return str(existing_row["incident_id"])

        incident_id = new_prefixed_id("inc")
        source_ticket_id: str | None = None
        source_node_id: str | None = None
        if error.trigger_type in {EVENT_TICKET_FAILED, EVENT_TICKET_TIMED_OUT}:
            source_ticket_id = str(error.trigger_ref or "").strip() or None
            if source_ticket_id is not None:
                source_ticket = repository.get_current_ticket_projection(source_ticket_id, connection=connection)
                source_node_id = str((source_ticket or {}).get("node_id") or "").strip() or None
        incident_payload = {
            "incident_id": incident_id,
            "ticket_id": source_ticket_id,
            "node_id": source_node_id,
            "incident_type": INCIDENT_TYPE_CEO_SHADOW_PIPELINE_FAILED,
            "status": INCIDENT_STATUS_OPEN,
            "severity": "high",
            "fingerprint": fingerprint,
            "trigger_type": error.trigger_type,
            "trigger_ref": error.trigger_ref,
            "source_stage": error.source_stage,
            "error_class": error.error_class,
            "error_message": error.error_message,
            "failure_fingerprint": fingerprint,
        }
        incident_event = repository.insert_event(
            connection,
            event_type=EVENT_INCIDENT_OPENED,
            actor_type="system",
            actor_id=actor_id,
            workflow_id=workflow_id,
            idempotency_key=f"{idempotency_key_base}:incident-opened:{error.source_stage}",
            causation_id=command_id,
            correlation_id=workflow_id,
            payload=incident_payload,
            occurred_at=occurred_at,
        )
        if incident_event is None:
            raise RuntimeError("CEO shadow pipeline incident opening idempotency conflict.")

        breaker_event = repository.insert_event(
            connection,
            event_type=EVENT_CIRCUIT_BREAKER_OPENED,
            actor_type="system",
            actor_id=actor_id,
            workflow_id=workflow_id,
            idempotency_key=f"{idempotency_key_base}:circuit-breaker-opened:{error.source_stage}",
            causation_id=command_id,
            correlation_id=workflow_id,
            payload={
                "incident_id": incident_id,
                "ticket_id": None,
                "node_id": None,
                "circuit_breaker_state": CIRCUIT_BREAKER_STATE_OPEN,
                "fingerprint": fingerprint,
            },
            occurred_at=occurred_at,
        )
        if breaker_event is None:
            raise RuntimeError("CEO shadow pipeline circuit breaker opening idempotency conflict.")

        repository.refresh_projections(connection)
        return incident_id


def _dispatch_sort_key(ticket: dict[str, Any]) -> tuple[int, datetime, str]:
    priority_rank = {
        "critical": 0,
        "high": 1,
        "medium": 2,
        "low": 3,
    }
    return (
        priority_rank.get(str(ticket.get("priority")).lower(), 4),
        ticket["updated_at"],
        ticket["ticket_id"],
    )


def _add_worker_candidate(
    worker_candidates: list[str],
    worker_by_id: dict[str, set[str]],
    *,
    employee_id: str,
    role_profile_refs: list[str],
) -> None:
    if employee_id in worker_by_id:
        return
    normalized_role_profiles = set(role_profile_refs)
    if "frontend_engineer_primary" in normalized_role_profiles:
        normalized_role_profiles.add("ui_designer_primary")
    worker_by_id[employee_id] = normalized_role_profiles
    worker_candidates.append(employee_id)


def _resolve_scheduler_workers(
    repository: ControlPlaneRepository,
    connection,
    workers: list[SchedulerWorkerCandidate] | None,
) -> tuple[list[str], dict[str, set[str]]]:
    worker_candidates: list[str] = []
    worker_by_id: dict[str, set[str]] = {}

    for employee in repository.list_scheduler_worker_candidates(connection):
        _add_worker_candidate(
            worker_candidates,
            worker_by_id,
            employee_id=employee["employee_id"],
            role_profile_refs=list(employee.get("role_profile_refs", [])),
        )

    for worker in workers or []:
        _add_worker_candidate(
            worker_candidates,
            worker_by_id,
            employee_id=worker.employee_id,
            role_profile_refs=list(worker.role_profile_refs),
        )

    return worker_candidates, worker_by_id


def _worker_is_dispatchable_for_ticket(
    repository: ControlPlaneRepository,
    connection,
    *,
    worker_id: str,
    target_role_profile: str,
    worker_by_id: dict[str, set[str]],
    busy_workers: set[str],
) -> bool:
    return (
        worker_id not in busy_workers
        and target_role_profile in worker_by_id.get(worker_id, set())
        and not _is_provider_paused(
            repository,
            connection,
            _resolve_provider_id_for_ticket(
                repository,
                connection,
                lease_owner=worker_id,
            ),
        )
    )


def _should_relax_singleton_rework_exclusions(
    repository: ControlPlaneRepository,
    connection,
    *,
    created_spec: dict[str, Any],
    target_role_profile: str,
    excluded_employee_ids: set[str],
    worker_candidates: list[str],
    worker_by_id: dict[str, set[str]],
    busy_workers: set[str],
) -> bool:
    if _ticket_kind(created_spec) != MAKER_REWORK_FIX_TICKET_KIND or not excluded_employee_ids:
        return False

    has_non_excluded_candidate = any(
        worker_id not in excluded_employee_ids
        and _worker_is_dispatchable_for_ticket(
            repository,
            connection,
            worker_id=worker_id,
            target_role_profile=target_role_profile,
            worker_by_id=worker_by_id,
            busy_workers=busy_workers,
        )
        for worker_id in worker_candidates
    )
    if has_non_excluded_candidate:
        return False

    return any(
        worker_id in excluded_employee_ids
        and _worker_is_dispatchable_for_ticket(
            repository,
            connection,
            worker_id=worker_id,
            target_role_profile=target_role_profile,
            worker_by_id=worker_by_id,
            busy_workers=busy_workers,
        )
        for worker_id in worker_candidates
    )


def run_scheduler_tick(
    repository: ControlPlaneRepository,
    *,
    idempotency_key: str,
    max_dispatches: int,
    workers: list[SchedulerWorkerCandidate] | None = None,
) -> CommandAckEnvelope:
    command_id = new_prefixed_id("cmd")
    received_at = now_local()

    with repository.transaction() as connection:
        existing_event = repository.get_event_by_idempotency_key(connection, idempotency_key)
        if existing_event is not None:
            return _scheduler_duplicate_ack(
                command_id=command_id,
                idempotency_key=idempotency_key,
                received_at=received_at,
            )

        event_index = 0

        def next_idempotency_key(suffix: str) -> str:
            nonlocal event_index
            key = idempotency_key if event_index == 0 else f"{idempotency_key}:{event_index}:{suffix}"
            event_index += 1
            return key

        changed_state = False
        ceo_failure_triggers: list[tuple[str, str]] = []
        timed_out_ticket_ids: set[str] = set()
        total_timeout_candidates = repository.list_total_timeout_ticket_candidates(connection, received_at)
        for ticket in total_timeout_candidates:
            timeout_payload = _build_failure_payload(
                failure_kind="TIMEOUT_SLA_EXCEEDED",
                failure_message="Ticket exceeded timeout SLA.",
                failure_detail={"timeout_sla_sec": ticket.get("timeout_sla_sec")},
            )
            timeout_event = repository.insert_event(
                connection,
                event_type=EVENT_TICKET_TIMED_OUT,
                actor_type="system",
                actor_id="scheduler",
                workflow_id=ticket["workflow_id"],
                idempotency_key=next_idempotency_key(f"timed-out:{ticket['ticket_id']}"),
                causation_id=command_id,
                correlation_id=ticket["workflow_id"],
                payload={
                    "ticket_id": ticket["ticket_id"],
                    "node_id": ticket["node_id"],
                    **timeout_payload,
                },
                occurred_at=received_at,
            )
            if timeout_event is None:
                return _scheduler_duplicate_ack(
                    command_id=command_id,
                    idempotency_key=idempotency_key,
                    received_at=received_at,
                )
            changed_state = True
            timed_out_ticket_ids.add(ticket["ticket_id"])

            created_spec = repository.get_latest_ticket_created_payload(connection, ticket["ticket_id"])
            if created_spec is None:
                continue
            timeout_streak_count = _calculate_timeout_streak(
                repository,
                connection,
                workflow_id=ticket["workflow_id"],
                node_id=ticket["node_id"],
                created_spec=created_spec,
            )
            timeout_threshold = _resolve_timeout_repeat_threshold(created_spec)
            if timeout_streak_count >= timeout_threshold:
                _open_timeout_incident(
                    repository=repository,
                    connection=connection,
                    command_id=command_id,
                    occurred_at=received_at,
                    workflow_id=ticket["workflow_id"],
                    ticket_id=ticket["ticket_id"],
                    node_id=ticket["node_id"],
                    timeout_streak_count=timeout_streak_count,
                    failure_payload=timeout_payload,
                    idempotency_key_base=f"{idempotency_key}:timeout:{ticket['ticket_id']}",
                )
                changed_state = True
                continue
            if _should_retry_timeout(current_ticket=ticket, created_spec=created_spec):
                _schedule_retry(
                    repository=repository,
                    connection=connection,
                    command_id=command_id,
                    occurred_at=received_at,
                    workflow_id=ticket["workflow_id"],
                    failed_ticket_id=ticket["ticket_id"],
                    node_id=ticket["node_id"],
                    created_spec=created_spec,
                    failure_payload=timeout_payload,
                    retry_source_event_type=EVENT_TICKET_TIMED_OUT,
                    idempotency_key_base=f"{idempotency_key}:timeout:{ticket['ticket_id']}",
                )
                changed_state = True

        heartbeat_timeout_candidates = repository.list_heartbeat_timeout_ticket_candidates(
            connection,
            received_at,
        )
        for ticket in heartbeat_timeout_candidates:
            if ticket["ticket_id"] in timed_out_ticket_ids:
                continue
            timeout_payload = _build_failure_payload(
                failure_kind="HEARTBEAT_TIMEOUT",
                failure_message="Ticket missed the required heartbeat window.",
                failure_detail={
                    "heartbeat_expires_at": (
                        ticket["heartbeat_expires_at"].isoformat()
                        if ticket.get("heartbeat_expires_at") is not None
                        else None
                    ),
                    "heartbeat_timeout_sec": ticket.get("heartbeat_timeout_sec"),
                },
            )
            timeout_event = repository.insert_event(
                connection,
                event_type=EVENT_TICKET_TIMED_OUT,
                actor_type="system",
                actor_id="scheduler",
                workflow_id=ticket["workflow_id"],
                idempotency_key=next_idempotency_key(f"heartbeat-timed-out:{ticket['ticket_id']}"),
                causation_id=command_id,
                correlation_id=ticket["workflow_id"],
                payload={
                    "ticket_id": ticket["ticket_id"],
                    "node_id": ticket["node_id"],
                    **timeout_payload,
                },
                occurred_at=received_at,
            )
            if timeout_event is None:
                return _scheduler_duplicate_ack(
                    command_id=command_id,
                    idempotency_key=idempotency_key,
                    received_at=received_at,
                )
            changed_state = True
            timed_out_ticket_ids.add(ticket["ticket_id"])

            created_spec = repository.get_latest_ticket_created_payload(connection, ticket["ticket_id"])
            if created_spec is None:
                continue
            timeout_streak_count = _calculate_timeout_streak(
                repository,
                connection,
                workflow_id=ticket["workflow_id"],
                node_id=ticket["node_id"],
                created_spec=created_spec,
            )
            timeout_threshold = _resolve_timeout_repeat_threshold(created_spec)
            if timeout_streak_count >= timeout_threshold:
                _open_timeout_incident(
                    repository=repository,
                    connection=connection,
                    command_id=command_id,
                    occurred_at=received_at,
                    workflow_id=ticket["workflow_id"],
                    ticket_id=ticket["ticket_id"],
                    node_id=ticket["node_id"],
                    timeout_streak_count=timeout_streak_count,
                    failure_payload=timeout_payload,
                    idempotency_key_base=f"{idempotency_key}:heartbeat-timeout:{ticket['ticket_id']}",
                )
                changed_state = True
                continue
            if _should_retry_timeout(current_ticket=ticket, created_spec=created_spec):
                _schedule_retry(
                    repository=repository,
                    connection=connection,
                    command_id=command_id,
                    occurred_at=received_at,
                    workflow_id=ticket["workflow_id"],
                    failed_ticket_id=ticket["ticket_id"],
                    node_id=ticket["node_id"],
                    created_spec=created_spec,
                    failure_payload=timeout_payload,
                    retry_source_event_type=EVENT_TICKET_TIMED_OUT,
                    idempotency_key_base=f"{idempotency_key}:heartbeat-timeout:{ticket['ticket_id']}",
                )
                changed_state = True

        repository.refresh_projections(connection)

        worker_candidates, worker_by_id = _resolve_scheduler_workers(repository, connection, workers)

        all_busy_tickets = repository.list_ticket_projections_by_statuses(
            connection,
            [TICKET_STATUS_LEASED, TICKET_STATUS_EXECUTING],
        )
        busy_workers: set[str] = set()
        for ticket in all_busy_tickets:
            owner = ticket.get("lease_owner")
            if owner is None:
                continue
            if ticket["status"] == TICKET_STATUS_EXECUTING:
                busy_workers.add(owner)
                continue
            lease_expiry = ticket.get("lease_expires_at")
            if lease_expiry is not None and lease_expiry > received_at:
                busy_workers.add(owner)

        dispatchable_tickets = sorted(
            repository.list_dispatchable_ticket_projections(connection, received_at),
            key=_dispatch_sort_key,
        )
        dispatched = 0
        final_review_approved_at_by_workflow: dict[str, datetime | None] = {}
        completed_delivery_stage_nodes_by_workflow: dict[str, set[tuple[str, str]]] = {}

        def _latest_final_review_approved_at(workflow_id: str) -> datetime | None:
            if workflow_id not in final_review_approved_at_by_workflow:
                row = connection.execute(
                    """
                    SELECT resolved_at
                    FROM approval_projection
                    WHERE workflow_id = ? AND status = ? AND approval_type = ?
                    ORDER BY resolved_at DESC, updated_at DESC, approval_id DESC
                    LIMIT 1
                    """,
                    (workflow_id, "APPROVED", "VISUAL_MILESTONE"),
                ).fetchone()
                final_review_approved_at_by_workflow[workflow_id] = (
                    row["resolved_at"] if row is not None else None
                )
            return final_review_approved_at_by_workflow[workflow_id]

        def _completed_delivery_stage_nodes(workflow_id: str) -> set[tuple[str, str]]:
            if workflow_id not in completed_delivery_stage_nodes_by_workflow:
                rows = connection.execute(
                    """
                    SELECT ticket_id, node_id
                    FROM ticket_projection
                    WHERE workflow_id = ? AND status = ?
                    ORDER BY updated_at DESC, ticket_id DESC
                    """,
                    (workflow_id, TICKET_STATUS_COMPLETED),
                ).fetchall()
                completed_nodes: set[tuple[str, str]] = set()
                for row in rows:
                    ticket_id = str(row["ticket_id"] or "").strip()
                    node_id = str(row["node_id"] or "").strip()
                    if not ticket_id or not node_id:
                        continue
                    completed_spec = repository.get_latest_ticket_created_payload(connection, ticket_id) or {}
                    delivery_stage = str(completed_spec.get("delivery_stage") or "").strip().upper()
                    if delivery_stage in {"BUILD", "CHECK", "REVIEW"}:
                        completed_nodes.add((node_id, delivery_stage))
                completed_delivery_stage_nodes_by_workflow[workflow_id] = completed_nodes
            return completed_delivery_stage_nodes_by_workflow[workflow_id]

        def _is_shadowed_by_final_review(
            ticket_projection: dict[str, Any],
            created_spec: dict[str, Any],
        ) -> bool:
            delivery_stage = str(created_spec.get("delivery_stage") or "").strip().upper()
            if delivery_stage not in {"BUILD", "CHECK", "REVIEW"}:
                return False
            workflow_id = str(ticket_projection.get("workflow_id") or "").strip()
            approved_at = _latest_final_review_approved_at(workflow_id)
            updated_at = ticket_projection.get("updated_at")
            if approved_at is None or not isinstance(updated_at, datetime) or updated_at > approved_at:
                return False
            node_id = str(ticket_projection.get("node_id") or created_spec.get("node_id") or "").strip()
            if not node_id:
                return False
            return (node_id, delivery_stage) in _completed_delivery_stage_nodes(workflow_id)

        for ticket in dispatchable_tickets:
            if dispatched >= max_dispatches:
                break

            node_projection = repository.get_current_node_projection(
                ticket["workflow_id"],
                ticket["node_id"],
                connection=connection,
            )
            if node_projection is None:
                continue
            if (
                node_projection["latest_ticket_id"] != ticket["ticket_id"]
                or node_projection["status"] != NODE_STATUS_PENDING
            ):
                continue
            if repository.has_open_circuit_breaker_for_node(
                ticket["workflow_id"],
                ticket["node_id"],
                connection=connection,
            ):
                continue

            created_spec = repository.get_latest_ticket_created_payload(connection, ticket["ticket_id"])
            if created_spec is None:
                continue
            if _is_shadowed_by_final_review(ticket, created_spec):
                continue
            parent_ready, parent_failure_payload = _evaluate_delivery_stage_parent_dependency(
                repository,
                connection,
                created_spec=created_spec,
            )
            if parent_failure_payload is not None:
                failed_event = _build_scheduler_failure_event(
                    repository,
                    connection,
                    command_id=command_id,
                    occurred_at=received_at,
                    workflow_id=ticket["workflow_id"],
                    ticket_id=ticket["ticket_id"],
                    node_id=ticket["node_id"],
                    failure_payload=parent_failure_payload,
                    idempotency_key=next_idempotency_key(
                        f"failed:{ticket['ticket_id']}:delivery-stage-parent"
                    ),
                )
                if failed_event is None:
                    return _scheduler_duplicate_ack(
                        command_id=command_id,
                        idempotency_key=idempotency_key,
                        received_at=received_at,
                    )
                repository.refresh_projections(connection)
                changed_state = True
                ceo_failure_triggers.append((ticket["workflow_id"], ticket["ticket_id"]))
                continue
            if not parent_ready:
                continue
            dependency_gates_ready, dependency_gate_failure_payload = _evaluate_dispatch_dependency_gates(
                repository,
                connection,
                created_spec=created_spec,
            )
            if dependency_gate_failure_payload is not None:
                failed_event = _build_scheduler_failure_event(
                    repository,
                    connection,
                    command_id=command_id,
                    occurred_at=received_at,
                    workflow_id=ticket["workflow_id"],
                    ticket_id=ticket["ticket_id"],
                    node_id=ticket["node_id"],
                    failure_payload=dependency_gate_failure_payload,
                    idempotency_key=next_idempotency_key(
                        f"failed:{ticket['ticket_id']}:dependency-gate"
                    ),
                )
                if failed_event is None:
                    return _scheduler_duplicate_ack(
                        command_id=command_id,
                        idempotency_key=idempotency_key,
                        received_at=received_at,
                    )
                repository.refresh_projections(connection)
                changed_state = True
                ceo_failure_triggers.append((ticket["workflow_id"], ticket["ticket_id"]))
                continue
            if not dependency_gates_ready:
                continue
            target_role_profile = created_spec.get("role_profile_ref")
            if not target_role_profile:
                continue
            lease_timeout_sec = _resolve_ticket_lease_timeout_sec(created_spec)
            excluded_employee_ids = {
                str(employee_id)
                for employee_id in (created_spec.get("excluded_employee_ids") or [])
                if employee_id
            }
            effective_excluded_employee_ids = (
                set()
                if _should_relax_singleton_rework_exclusions(
                    repository,
                    connection,
                    created_spec=created_spec,
                    target_role_profile=str(target_role_profile),
                    excluded_employee_ids=excluded_employee_ids,
                    worker_candidates=worker_candidates,
                    worker_by_id=worker_by_id,
                    busy_workers=busy_workers,
                )
                else excluded_employee_ids
            )
            selected_worker_id: str | None = None
            selected_worker_precondition: dict[str, Any] | None = None
            selected_assignee_employee_id = _resolve_dispatch_assignee_employee_id(created_spec)
            if selected_assignee_employee_id is not None:
                if selected_assignee_employee_id not in worker_by_id:
                    continue
                if (
                    selected_assignee_employee_id in busy_workers
                    or selected_assignee_employee_id in effective_excluded_employee_ids
                ):
                    continue
                selected_assignee = repository.get_employee_projection(
                    selected_assignee_employee_id,
                    connection=connection,
                )
                if selected_assignee is None:
                    dispatch_failure_payload = _build_failure_payload(
                        failure_kind=DISPATCH_INTENT_INVALID_FAILURE_KIND,
                        failure_message="Dispatch intent assignee is missing from the employee registry.",
                        failure_detail={
                            "assignee_employee_id": selected_assignee_employee_id,
                        },
                    )
                elif str(selected_assignee.get("state") or "") != EMPLOYEE_STATE_ACTIVE:
                    dispatch_failure_payload = _build_failure_payload(
                        failure_kind=DISPATCH_INTENT_INVALID_FAILURE_KIND,
                        failure_message="Dispatch intent assignee is not currently active.",
                        failure_detail={
                            "assignee_employee_id": selected_assignee_employee_id,
                            "employee_state": selected_assignee.get("state"),
                        },
                    )
                elif not employee_supports_execution_contract(
                    employee=selected_assignee,
                    execution_contract=created_spec.get("execution_contract"),
                ):
                    dispatch_failure_payload = _build_failure_payload(
                        failure_kind=DISPATCH_INTENT_INVALID_FAILURE_KIND,
                        failure_message="Dispatch intent assignee no longer satisfies the execution contract.",
                        failure_detail={
                            "assignee_employee_id": selected_assignee_employee_id,
                            "execution_contract": created_spec.get("execution_contract"),
                        },
                    )
                elif _is_provider_paused(
                    repository,
                    connection,
                    _resolve_provider_id_for_ticket(
                        repository,
                        connection,
                        lease_owner=selected_assignee_employee_id,
                    ),
                ):
                    continue
                else:
                    dispatch_failure_payload = None
                    selected_worker_id = selected_assignee_employee_id
                    selected_worker_precondition = _evaluate_ticket_execution_precondition(
                        repository,
                        connection,
                        ticket=ticket,
                        created_spec=created_spec,
                        lease_owner=selected_worker_id,
                    )
                if dispatch_failure_payload is not None:
                    failed_event = _build_scheduler_failure_event(
                        repository,
                        connection,
                        command_id=command_id,
                        occurred_at=received_at,
                        workflow_id=ticket["workflow_id"],
                        ticket_id=ticket["ticket_id"],
                        node_id=ticket["node_id"],
                        failure_payload=dispatch_failure_payload,
                        idempotency_key=next_idempotency_key(
                            f"failed:{ticket['ticket_id']}:dispatch-intent"
                        ),
                    )
                    if failed_event is None:
                        return _scheduler_duplicate_ack(
                            command_id=command_id,
                            idempotency_key=idempotency_key,
                            received_at=received_at,
                        )
                    repository.refresh_projections(connection)
                    changed_state = True
                    ceo_failure_triggers.append((ticket["workflow_id"], ticket["ticket_id"]))
                    continue
            else:
                blocked_precondition_result: dict[str, Any] | None = None
                for worker_id in worker_candidates:
                    if worker_id in effective_excluded_employee_ids:
                        continue
                    if not _worker_is_dispatchable_for_ticket(
                        repository,
                        connection,
                        worker_id=worker_id,
                        target_role_profile=str(target_role_profile),
                        worker_by_id=worker_by_id,
                        busy_workers=busy_workers,
                    ):
                        continue
                    precondition_result = _evaluate_ticket_execution_precondition(
                        repository,
                        connection,
                        ticket=ticket,
                        created_spec=created_spec,
                        lease_owner=worker_id,
                    )
                    if precondition_result is not None and precondition_result["blocked"]:
                        if blocked_precondition_result is None:
                            blocked_precondition_result = precondition_result
                        continue
                    selected_worker_id = worker_id
                    selected_worker_precondition = precondition_result
                    break
                if selected_worker_id is None and blocked_precondition_result is not None:
                    _sync_ticket_execution_precondition_state(
                        repository,
                        connection,
                        command_id=command_id,
                        occurred_at=received_at,
                        workflow_id=ticket["workflow_id"],
                        ticket=ticket,
                        node_id=ticket["node_id"],
                        precondition_result=blocked_precondition_result,
                        actor_id="scheduler",
                    )
                    changed_state = True
                    continue
            if selected_worker_id is None:
                continue

            if selected_worker_precondition is not None and _sync_ticket_execution_precondition_state(
                repository,
                connection,
                command_id=command_id,
                occurred_at=received_at,
                workflow_id=ticket["workflow_id"],
                ticket=ticket,
                node_id=ticket["node_id"],
                precondition_result=selected_worker_precondition,
                actor_id="scheduler",
            ):
                changed_state = True
                continue

            lease_event = repository.insert_event(
                connection,
                event_type=EVENT_TICKET_LEASED,
                actor_type="system",
                actor_id="scheduler",
                workflow_id=ticket["workflow_id"],
                idempotency_key=next_idempotency_key(
                    f"lease:{ticket['ticket_id']}:{selected_worker_id}"
                ),
                causation_id=command_id,
                correlation_id=ticket["workflow_id"],
                payload={
                    "ticket_id": ticket["ticket_id"],
                    "node_id": ticket["node_id"],
                    "leased_by": selected_worker_id,
                    "lease_timeout_sec": lease_timeout_sec,
                    "lease_expires_at": (received_at + timedelta(seconds=lease_timeout_sec)).isoformat(),
                },
                occurred_at=received_at,
            )
            if lease_event is None:
                return _scheduler_duplicate_ack(
                    command_id=command_id,
                    idempotency_key=idempotency_key,
                    received_at=received_at,
                )

            busy_workers.add(selected_worker_id)
            dispatched += 1
            changed_state = True

        if changed_state or dispatched > 0:
            repository.refresh_projections(connection)

    for workflow_id, ticket_id in ceo_failure_triggers:
        _trigger_ceo_shadow_safely(
            repository,
            workflow_id=workflow_id,
            trigger_type=EVENT_TICKET_FAILED,
            trigger_ref=ticket_id,
        )

    return CommandAckEnvelope(
        command_id=command_id,
        idempotency_key=idempotency_key,
        status=CommandAckStatus.ACCEPTED,
        received_at=received_at,
        reason=None,
        causation_hint="scheduler:tick",
    )


def handle_retry_ticket_from_ceo(
    repository: ControlPlaneRepository,
    *,
    workflow_id: str,
    ticket_id: str,
    node_id: str,
    reason: str,
    idempotency_key: str,
) -> CommandAckEnvelope:
    command_id = new_prefixed_id("cmd")
    received_at = now_local()

    with repository.transaction() as connection:
        existing_event = repository.get_event_by_idempotency_key(connection, idempotency_key)
        if existing_event is not None:
            return CommandAckEnvelope(
                command_id=command_id,
                idempotency_key=idempotency_key,
                status=CommandAckStatus.DUPLICATE,
                received_at=received_at,
                reason="An identical CEO retry execution was already accepted.",
                causation_hint=f"event:{existing_event['event_id']}",
            )

        current_ticket = repository.get_current_ticket_projection(ticket_id, connection=connection)
        if current_ticket is None:
            return _rejected_ack(
                command_id=command_id,
                idempotency_key=idempotency_key,
                received_at=received_at,
                ticket_id=ticket_id,
                reason=f"Ticket {ticket_id} does not exist in projection state.",
            )
        if current_ticket["workflow_id"] != workflow_id or current_ticket["node_id"] != node_id:
            return _rejected_ack(
                command_id=command_id,
                idempotency_key=idempotency_key,
                received_at=received_at,
                ticket_id=ticket_id,
                reason="Ticket does not match the requested workflow or node.",
            )
        if current_ticket["status"] not in {TICKET_STATUS_FAILED, TICKET_STATUS_TIMED_OUT}:
            return _rejected_ack(
                command_id=command_id,
                idempotency_key=idempotency_key,
                received_at=received_at,
                ticket_id=ticket_id,
                reason=f"Ticket {ticket_id} is not on a retryable terminal state.",
            )

        created_spec = repository.get_latest_ticket_created_payload(connection, ticket_id)
        if created_spec is None:
            return _rejected_ack(
                command_id=command_id,
                idempotency_key=idempotency_key,
                received_at=received_at,
                ticket_id=ticket_id,
                reason=f"Ticket {ticket_id} is missing its created spec.",
            )

        latest_terminal_event = repository.get_latest_ticket_terminal_event(connection, ticket_id)
        if latest_terminal_event is None:
            return _rejected_ack(
                command_id=command_id,
                idempotency_key=idempotency_key,
                received_at=received_at,
                ticket_id=ticket_id,
                reason=f"Ticket {ticket_id} has no terminal event to retry from.",
            )

        failure_payload = _build_failure_payload(
            failure_kind=str(
                latest_terminal_event["payload"].get("failure_kind")
                or current_ticket.get("last_failure_kind")
                or "RETRY_REQUESTED"
            ),
            failure_message=str(
                latest_terminal_event["payload"].get("failure_message")
                or reason
                or "CEO requested a retry for the latest terminal ticket."
            ),
            failure_detail=latest_terminal_event["payload"].get("failure_detail"),
        )

        retry_source_event_type = latest_terminal_event["event_type"]
        if retry_source_event_type == EVENT_TICKET_TIMED_OUT:
            if not _should_retry_timeout(current_ticket=current_ticket, created_spec=created_spec):
                return _rejected_ack(
                    command_id=command_id,
                    idempotency_key=idempotency_key,
                    received_at=received_at,
                    ticket_id=ticket_id,
                    reason=f"Ticket {ticket_id} exhausted its timeout retry budget or timeout retry is disabled.",
                )
        elif retry_source_event_type == EVENT_TICKET_FAILED:
            latest_failure_kind = str(latest_terminal_event["payload"].get("failure_kind") or "")
            if not _should_retry_failure(
                current_ticket=current_ticket,
                created_spec=created_spec,
                failure_kind=latest_failure_kind,
            ):
                return _rejected_ack(
                    command_id=command_id,
                    idempotency_key=idempotency_key,
                    received_at=received_at,
                    ticket_id=ticket_id,
                    reason=f"Ticket {ticket_id} exhausted its failure retry budget or failure retry is disabled.",
                )
        else:
            return _rejected_ack(
                command_id=command_id,
                idempotency_key=idempotency_key,
                received_at=received_at,
                ticket_id=ticket_id,
                reason=f"Ticket {ticket_id} cannot be retried from terminal event {retry_source_event_type}.",
            )

        next_ticket_id = _schedule_retry(
            repository=repository,
            connection=connection,
            command_id=command_id,
            occurred_at=received_at,
            workflow_id=workflow_id,
            failed_ticket_id=ticket_id,
            node_id=node_id,
            created_spec=created_spec,
            failure_payload=failure_payload,
            retry_source_event_type=retry_source_event_type,
            idempotency_key_base=idempotency_key,
        )
        repository.refresh_projections(connection)

    return CommandAckEnvelope(
        command_id=command_id,
        idempotency_key=idempotency_key,
        status=CommandAckStatus.ACCEPTED,
        received_at=received_at,
        reason=None,
        causation_hint=f"ticket:{next_ticket_id}",
    )


def handle_incident_resolve(
    repository: ControlPlaneRepository,
    payload: IncidentResolveCommand,
) -> CommandAckEnvelope:
    command_id = new_prefixed_id("cmd")
    received_at = now_local()

    with repository.transaction() as connection:
        existing_event = repository.get_event_by_idempotency_key(connection, payload.idempotency_key)
        if existing_event is not None:
            return _incident_duplicate_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                incident_id=payload.incident_id,
            )

        incident = repository.get_incident_projection(payload.incident_id, connection=connection)
        if incident is None:
            return _incident_rejected_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                incident_id=payload.incident_id,
                reason=f"Incident {payload.incident_id} does not exist.",
            )
        if incident["status"] != INCIDENT_STATUS_OPEN:
            return _incident_rejected_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                incident_id=payload.incident_id,
                reason=f"Incident {payload.incident_id} is not open for recovery.",
            )
        if incident.get("circuit_breaker_state") != CIRCUIT_BREAKER_STATE_OPEN:
            return _incident_rejected_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                incident_id=payload.incident_id,
                reason=(
                    f"Incident {payload.incident_id} cannot be resolved because its circuit breaker "
                    "is not OPEN."
                ),
            )

        workflow_id = incident["workflow_id"]
        followup_ticket_id: str | None = None
        followup_action = payload.followup_action.value
        retry_ticket: dict[str, Any] | None = None
        retry_created_spec: dict[str, Any] | None = None
        replay_result = None
        rerun_context: dict[str, Any] | None = None
        advisory_rerun_context: dict[str, Any] | None = None
        if payload.followup_action == IncidentFollowupAction.RESTORE_AND_RETRY_LATEST_TIMEOUT:
            source_ticket_context = resolve_ceo_shadow_source_ticket_context(
                repository,
                incident,
                connection=connection,
            )
            if incident["incident_type"] not in {
                INCIDENT_TYPE_RUNTIME_TIMEOUT_ESCALATION,
                INCIDENT_TYPE_CEO_SHADOW_PIPELINE_FAILED,
            }:
                return _incident_rejected_ack(
                    command_id=command_id,
                    idempotency_key=payload.idempotency_key,
                    received_at=received_at,
                    incident_id=payload.incident_id,
                    reason=(
                        f"Incident {payload.incident_id} does not support timeout retry recovery."
                    ),
                )
            if (
                incident["incident_type"] == INCIDENT_TYPE_CEO_SHADOW_PIPELINE_FAILED
                and source_ticket_context["recommended_restore_action"]
                != IncidentFollowupAction.RESTORE_AND_RETRY_LATEST_TIMEOUT.value
            ):
                return _incident_rejected_ack(
                    command_id=command_id,
                    idempotency_key=payload.idempotency_key,
                    received_at=received_at,
                    incident_id=payload.incident_id,
                    reason=(
                        f"Incident {payload.incident_id} does not support timeout retry recovery."
                    ),
                )
            try:
                retry_ticket, retry_created_spec = _validate_restore_and_retry_followup(
                    repository=repository,
                    connection=connection,
                    incident=incident,
                )
            except ValueError as exc:
                return _incident_rejected_ack(
                    command_id=command_id,
                    idempotency_key=payload.idempotency_key,
                    received_at=received_at,
                    incident_id=payload.incident_id,
                    reason=str(exc),
                )
        elif payload.followup_action == IncidentFollowupAction.RESTORE_AND_RETRY_LATEST_FAILURE:
            source_ticket_context = resolve_ceo_shadow_source_ticket_context(
                repository,
                incident,
                connection=connection,
            )
            if incident["incident_type"] not in {
                INCIDENT_TYPE_REPEATED_FAILURE_ESCALATION,
                INCIDENT_TYPE_CEO_SHADOW_PIPELINE_FAILED,
            }:
                return _incident_rejected_ack(
                    command_id=command_id,
                    idempotency_key=payload.idempotency_key,
                    received_at=received_at,
                    incident_id=payload.incident_id,
                    reason=(
                        f"Incident {payload.incident_id} does not support ordinary failure retry recovery."
                    ),
                )
            if (
                incident["incident_type"] == INCIDENT_TYPE_CEO_SHADOW_PIPELINE_FAILED
                and source_ticket_context["recommended_restore_action"]
                != IncidentFollowupAction.RESTORE_AND_RETRY_LATEST_FAILURE.value
            ):
                return _incident_rejected_ack(
                    command_id=command_id,
                    idempotency_key=payload.idempotency_key,
                    received_at=received_at,
                    incident_id=payload.incident_id,
                    reason=(
                        f"Incident {payload.incident_id} does not support ordinary failure retry recovery."
                    ),
                )
            try:
                retry_ticket, retry_created_spec = _validate_restore_and_retry_failure_followup(
                    repository=repository,
                    connection=connection,
                    incident=incident,
                )
            except ValueError as exc:
                return _incident_rejected_ack(
                    command_id=command_id,
                    idempotency_key=payload.idempotency_key,
                    received_at=received_at,
                    incident_id=payload.incident_id,
                    reason=str(exc),
                )
        elif payload.followup_action == IncidentFollowupAction.RESTORE_AND_RETRY_LATEST_PROVIDER_FAILURE:
            if incident["incident_type"] != INCIDENT_TYPE_PROVIDER_EXECUTION_PAUSED:
                return _incident_rejected_ack(
                    command_id=command_id,
                    idempotency_key=payload.idempotency_key,
                    received_at=received_at,
                    incident_id=payload.incident_id,
                    reason=(
                        f"Incident {payload.incident_id} does not support provider retry recovery."
                    ),
                )
            try:
                retry_ticket, retry_created_spec = _validate_restore_and_retry_provider_followup(
                    repository=repository,
                    connection=connection,
                    incident=incident,
                )
            except ValueError as exc:
                return _incident_rejected_ack(
                    command_id=command_id,
                    idempotency_key=payload.idempotency_key,
                    received_at=received_at,
                    incident_id=payload.incident_id,
                    reason=str(exc),
                )
        elif (
            payload.followup_action
            == IncidentFollowupAction.RESTORE_AND_RETRY_LATEST_STAFFING_CONTAINMENT
        ):
            if incident["incident_type"] != INCIDENT_TYPE_STAFFING_CONTAINMENT:
                return _incident_rejected_ack(
                    command_id=command_id,
                    idempotency_key=payload.idempotency_key,
                    received_at=received_at,
                    incident_id=payload.incident_id,
                    reason=(
                        f"Incident {payload.incident_id} does not support staffing containment recovery."
                    ),
                )
            try:
                retry_ticket, retry_created_spec = _validate_restore_and_retry_staffing_followup(
                    repository=repository,
                    connection=connection,
                    incident=incident,
                )
            except ValueError as exc:
                return _incident_rejected_ack(
                    command_id=command_id,
                    idempotency_key=payload.idempotency_key,
                    received_at=received_at,
                    incident_id=payload.incident_id,
                    reason=str(exc),
                )
        elif payload.followup_action == IncidentFollowupAction.REPLAY_REQUIRED_HOOKS:
            if incident["incident_type"] != INCIDENT_TYPE_REQUIRED_HOOK_GATE_BLOCKED:
                return _incident_rejected_ack(
                    command_id=command_id,
                    idempotency_key=payload.idempotency_key,
                    received_at=received_at,
                    incident_id=payload.incident_id,
                    reason=(
                        f"Incident {payload.incident_id} does not support required hook replay recovery."
                    ),
                )
            incident_ticket_id = str(incident.get("ticket_id") or "").strip()
            if not incident_ticket_id:
                return _incident_rejected_ack(
                    command_id=command_id,
                    idempotency_key=payload.idempotency_key,
                    received_at=received_at,
                    incident_id=payload.incident_id,
                    reason="Required hook gate incident is missing its source ticket.",
                )
            try:
                replay_result = replay_required_hook_receipts(
                    repository,
                    workflow_id=workflow_id,
                    ticket_id=incident_ticket_id,
                    connection=connection,
                )
            except ValueError as exc:
                return _incident_rejected_ack(
                    command_id=command_id,
                    idempotency_key=payload.idempotency_key,
                    received_at=received_at,
                    incident_id=payload.incident_id,
                    reason=str(exc),
                )
        elif payload.followup_action == IncidentFollowupAction.REBUILD_TICKET_GRAPH:
            if incident["incident_type"] != INCIDENT_TYPE_TICKET_GRAPH_UNAVAILABLE:
                return _incident_rejected_ack(
                    command_id=command_id,
                    idempotency_key=payload.idempotency_key,
                    received_at=received_at,
                    incident_id=payload.incident_id,
                    reason=(
                        f"Incident {payload.incident_id} does not support ticket graph rebuild recovery."
                    ),
                )
            try:
                build_ticket_graph_snapshot(
                    repository,
                    workflow_id,
                    connection=connection,
                )
            except Exception as exc:
                return _incident_rejected_ack(
                    command_id=command_id,
                    idempotency_key=payload.idempotency_key,
                    received_at=received_at,
                    incident_id=payload.incident_id,
                    reason=f"Ticket graph rebuild failed: {exc}",
                )
        elif payload.followup_action == IncidentFollowupAction.RERUN_CEO_SHADOW:
            if incident["incident_type"] not in {
                INCIDENT_TYPE_CEO_SHADOW_PIPELINE_FAILED,
                INCIDENT_TYPE_GRAPH_HEALTH_CRITICAL,
                INCIDENT_TYPE_PLANNED_PLACEHOLDER_GATE_BLOCKED,
                INCIDENT_TYPE_RUNTIME_LIVENESS_CRITICAL,
            }:
                return _incident_rejected_ack(
                    command_id=command_id,
                    idempotency_key=payload.idempotency_key,
                    received_at=received_at,
                    incident_id=payload.incident_id,
                    reason=f"Incident {payload.incident_id} does not support CEO shadow rerun recovery.",
                )
            rerun_context = {
                "workflow_id": workflow_id,
                "trigger_type": str(
                    (incident.get("payload") or {}).get("trigger_type")
                    or (
                        SCHEDULER_IDLE_MAINTENANCE_TRIGGER
                        if incident["incident_type"] in {
                            INCIDENT_TYPE_GRAPH_HEALTH_CRITICAL,
                            INCIDENT_TYPE_RUNTIME_LIVENESS_CRITICAL,
                        }
                        else ""
                    )
                ).strip(),
                "trigger_ref": (
                    str((incident.get("payload") or {}).get("trigger_ref"))
                    if (incident.get("payload") or {}).get("trigger_ref") is not None
                    else None
                ),
                "incident": incident,
            }
            if not rerun_context["trigger_type"]:
                return _incident_rejected_ack(
                    command_id=command_id,
                    idempotency_key=payload.idempotency_key,
                    received_at=received_at,
                    incident_id=payload.incident_id,
                    reason="CEO shadow incident is missing its original trigger_type.",
                )
        elif payload.followup_action == IncidentFollowupAction.RERUN_BOARD_ADVISORY_ANALYSIS:
            if incident["incident_type"] != INCIDENT_TYPE_BOARD_ADVISORY_ANALYSIS_FAILED:
                return _incident_rejected_ack(
                    command_id=command_id,
                    idempotency_key=payload.idempotency_key,
                    received_at=received_at,
                    incident_id=payload.incident_id,
                    reason=f"Incident {payload.incident_id} does not support advisory analysis rerun recovery.",
                )
            session_id = str((incident.get("payload") or {}).get("session_id") or "").strip()
            if not session_id:
                return _incident_rejected_ack(
                    command_id=command_id,
                    idempotency_key=payload.idempotency_key,
                    received_at=received_at,
                    incident_id=payload.incident_id,
                    reason="Board advisory analysis incident is missing its session_id.",
                )
            advisory_rerun_context = {
                "workflow_id": workflow_id,
                "session_id": session_id,
                "incident": incident,
            }

        if rerun_context is None and advisory_rerun_context is None:
            resolution_payload = {
                "incident_id": payload.incident_id,
                "node_id": incident.get("node_id"),
                "ticket_id": incident.get("ticket_id"),
                "provider_id": incident.get("provider_id"),
                "resolved_by": payload.resolved_by,
                "resolution_summary": payload.resolution_summary,
                "followup_action": followup_action,
                "followup_ticket_id": None,
                "incident_type": incident["incident_type"],
            }
            if payload.followup_action == IncidentFollowupAction.REPLAY_REQUIRED_HOOKS:
                resolution_payload["replayed_hook_ids"] = list(replay_result.replayed_hook_ids)

            breaker_closed_event = repository.insert_event(
                connection,
                event_type=EVENT_CIRCUIT_BREAKER_CLOSED,
                actor_type="operator",
                actor_id=payload.resolved_by,
                workflow_id=workflow_id,
                idempotency_key=f"{payload.idempotency_key}:breaker-closed",
                causation_id=command_id,
                correlation_id=workflow_id,
                payload={
                    **resolution_payload,
                    "circuit_breaker_state": CIRCUIT_BREAKER_STATE_CLOSED,
                },
                occurred_at=received_at,
            )
            if breaker_closed_event is None:
                return _incident_duplicate_ack(
                    command_id=command_id,
                    idempotency_key=payload.idempotency_key,
                    received_at=received_at,
                    incident_id=payload.incident_id,
                )

            if payload.followup_action in {
                IncidentFollowupAction.RESTORE_AND_RETRY_LATEST_FAILURE,
                IncidentFollowupAction.RESTORE_AND_RETRY_LATEST_TIMEOUT,
                IncidentFollowupAction.RESTORE_AND_RETRY_LATEST_PROVIDER_FAILURE,
                IncidentFollowupAction.RESTORE_AND_RETRY_LATEST_STAFFING_CONTAINMENT,
            }:
                assert retry_ticket is not None
                assert retry_created_spec is not None
                if (
                    payload.followup_action
                    == IncidentFollowupAction.RESTORE_AND_RETRY_LATEST_STAFFING_CONTAINMENT
                ):
                    followup_ticket_id = _schedule_staffing_recovery_followup(
                        repository=repository,
                        connection=connection,
                        command_id=command_id,
                        occurred_at=received_at,
                        workflow_id=workflow_id,
                        source_ticket=retry_ticket,
                        created_spec=retry_created_spec,
                        idempotency_key_base=f"{payload.idempotency_key}:followup-staffing",
                    )
                else:
                    retry_source_event_type = (
                        EVENT_TICKET_TIMED_OUT
                        if payload.followup_action == IncidentFollowupAction.RESTORE_AND_RETRY_LATEST_TIMEOUT
                        else EVENT_TICKET_FAILED
                    )
                    followup_ticket_id = _schedule_retry(
                        repository=repository,
                        connection=connection,
                        command_id=command_id,
                        occurred_at=received_at,
                        workflow_id=workflow_id,
                        failed_ticket_id=str(incident["ticket_id"]),
                        node_id=str(incident["node_id"]),
                        created_spec=retry_created_spec,
                        failure_payload={
                            "failure_fingerprint": (
                                (incident.get("payload") or {}).get("latest_failure_fingerprint")
                                or incident.get("fingerprint")
                            ),
                        },
                        retry_source_event_type=retry_source_event_type,
                        idempotency_key_base=f"{payload.idempotency_key}:followup-timeout",
                    )
                    _recreate_pending_delivery_descendants_for_retry(
                        repository=repository,
                        connection=connection,
                        command_id=command_id,
                        occurred_at=received_at,
                        workflow_id=workflow_id,
                        failed_ticket_id=str(incident["ticket_id"]),
                        replacement_ticket_id=followup_ticket_id,
                        replacement_created_spec=retry_created_spec,
                        idempotency_key_base=f"{payload.idempotency_key}:followup-descendants",
                    )
                resolution_payload["followup_ticket_id"] = followup_ticket_id

            incident_recovery_event = repository.insert_event(
                connection,
                event_type=EVENT_INCIDENT_RECOVERY_STARTED,
                actor_type="operator",
                actor_id=payload.resolved_by,
                workflow_id=workflow_id,
                idempotency_key=payload.idempotency_key,
                causation_id=command_id,
                correlation_id=workflow_id,
                payload={
                    **resolution_payload,
                    "status": INCIDENT_STATUS_RECOVERING,
                },
                occurred_at=received_at,
            )
            if incident_recovery_event is None:
                return _incident_duplicate_ack(
                    command_id=command_id,
                    idempotency_key=payload.idempotency_key,
                    received_at=received_at,
                    incident_id=payload.incident_id,
                )

            repository.refresh_projections(connection)

    if rerun_context is not None:
        try:
            run_ceo_shadow_for_trigger(
                repository,
                workflow_id=str(rerun_context["workflow_id"]),
                trigger_type=str(rerun_context["trigger_type"]),
                trigger_ref=rerun_context["trigger_ref"],
            )
        except CeoShadowPipelineError as exc:
            return _incident_rejected_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                incident_id=payload.incident_id,
                reason=str(exc),
            )
        except Exception as exc:
            reason = (
                f"CEO shadow rerun failed because the ticket graph is still unavailable: {exc}"
                if is_ticket_graph_unavailable_error(exc)
                else f"CEO shadow rerun failed: {exc}"
            )
            return _incident_rejected_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                incident_id=payload.incident_id,
                reason=reason,
            )

        with repository.transaction() as connection:
            resolution_payload = {
                "incident_id": payload.incident_id,
                "node_id": None,
                "ticket_id": None,
                "provider_id": None,
                "resolved_by": payload.resolved_by,
                "resolution_summary": payload.resolution_summary,
                "followup_action": followup_action,
                "followup_ticket_id": None,
                "incident_type": INCIDENT_TYPE_CEO_SHADOW_PIPELINE_FAILED,
            }
            incident_recovery_event = repository.insert_event(
                connection,
                event_type=EVENT_INCIDENT_RECOVERY_STARTED,
                actor_type="operator",
                actor_id=payload.resolved_by,
                workflow_id=str(rerun_context["workflow_id"]),
                idempotency_key=payload.idempotency_key,
                causation_id=command_id,
                correlation_id=str(rerun_context["workflow_id"]),
                payload={
                    **resolution_payload,
                    "status": INCIDENT_STATUS_RECOVERING,
                },
                occurred_at=received_at,
            )
            if incident_recovery_event is None:
                return _incident_duplicate_ack(
                    command_id=command_id,
                    idempotency_key=payload.idempotency_key,
                    received_at=received_at,
                    incident_id=payload.incident_id,
                )
            breaker_closed_event = repository.insert_event(
                connection,
                event_type=EVENT_CIRCUIT_BREAKER_CLOSED,
                actor_type="operator",
                actor_id=payload.resolved_by,
                workflow_id=str(rerun_context["workflow_id"]),
                idempotency_key=f"{payload.idempotency_key}:breaker-closed",
                causation_id=command_id,
                correlation_id=str(rerun_context["workflow_id"]),
                payload={
                    **resolution_payload,
                    "circuit_breaker_state": CIRCUIT_BREAKER_STATE_CLOSED,
                },
                occurred_at=received_at,
            )
            if breaker_closed_event is None:
                return _incident_duplicate_ack(
                    command_id=command_id,
                    idempotency_key=payload.idempotency_key,
                    received_at=received_at,
                    incident_id=payload.incident_id,
                )
            incident_closed_event = repository.insert_event(
                connection,
                event_type=EVENT_INCIDENT_CLOSED,
                actor_type="operator",
                actor_id=payload.resolved_by,
                workflow_id=str(rerun_context["workflow_id"]),
                idempotency_key=f"{payload.idempotency_key}:incident-closed",
                causation_id=command_id,
                correlation_id=str(rerun_context["workflow_id"]),
                payload={
                    **resolution_payload,
                    "status": INCIDENT_STATUS_CLOSED,
                    "close_reason": "CEO shadow rerun completed successfully.",
                },
                occurred_at=received_at,
            )
            if incident_closed_event is None:
                return _incident_duplicate_ack(
                    command_id=command_id,
                    idempotency_key=payload.idempotency_key,
                    received_at=received_at,
                    incident_id=payload.incident_id,
                )
            repository.refresh_projections(connection)

        return CommandAckEnvelope(
            command_id=command_id,
            idempotency_key=payload.idempotency_key,
            status=CommandAckStatus.ACCEPTED,
            received_at=received_at,
            reason=None,
            causation_hint=f"incident:{payload.incident_id}",
        )

    if advisory_rerun_context is not None:
        with repository.transaction() as connection:
            session = repository.get_board_advisory_session(
                str(advisory_rerun_context["session_id"]),
                connection=connection,
            )
            if session is None:
                return _incident_rejected_ack(
                    command_id=command_id,
                    idempotency_key=payload.idempotency_key,
                    received_at=received_at,
                    incident_id=payload.incident_id,
                    reason="Board advisory session is missing for advisory analysis rerun.",
                )
            rerun = create_board_advisory_analysis_run(
                repository,
                connection,
                session=session,
                idempotency_key=f"{payload.idempotency_key}:board-advisory-analysis-rerun",
                occurred_at=received_at,
            )
            repository.refresh_projections(connection)

        rerun_session = run_board_advisory_analysis(repository, str(rerun["run_id"]))
        if str(rerun_session.get("status") or "") != "PENDING_BOARD_CONFIRMATION":
            return _incident_rejected_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                incident_id=payload.incident_id,
                reason=str(rerun_session.get("latest_analysis_error") or "Board advisory analysis rerun failed."),
            )

        with repository.transaction() as connection:
            resolution_payload = {
                "incident_id": payload.incident_id,
                "node_id": incident.get("node_id"),
                "ticket_id": incident.get("ticket_id"),
                "provider_id": incident.get("provider_id"),
                "resolved_by": payload.resolved_by,
                "resolution_summary": payload.resolution_summary,
                "followup_action": followup_action,
                "followup_ticket_id": None,
                "incident_type": INCIDENT_TYPE_BOARD_ADVISORY_ANALYSIS_FAILED,
            }
            incident_recovery_event = repository.insert_event(
                connection,
                event_type=EVENT_INCIDENT_RECOVERY_STARTED,
                actor_type="operator",
                actor_id=payload.resolved_by,
                workflow_id=str(advisory_rerun_context["workflow_id"]),
                idempotency_key=payload.idempotency_key,
                causation_id=command_id,
                correlation_id=str(advisory_rerun_context["workflow_id"]),
                payload={
                    **resolution_payload,
                    "status": INCIDENT_STATUS_RECOVERING,
                },
                occurred_at=received_at,
            )
            if incident_recovery_event is None:
                return _incident_duplicate_ack(
                    command_id=command_id,
                    idempotency_key=payload.idempotency_key,
                    received_at=received_at,
                    incident_id=payload.incident_id,
                )
            breaker_closed_event = repository.insert_event(
                connection,
                event_type=EVENT_CIRCUIT_BREAKER_CLOSED,
                actor_type="operator",
                actor_id=payload.resolved_by,
                workflow_id=str(advisory_rerun_context["workflow_id"]),
                idempotency_key=f"{payload.idempotency_key}:breaker-closed",
                causation_id=command_id,
                correlation_id=str(advisory_rerun_context["workflow_id"]),
                payload={
                    **resolution_payload,
                    "circuit_breaker_state": CIRCUIT_BREAKER_STATE_CLOSED,
                },
                occurred_at=received_at,
            )
            if breaker_closed_event is None:
                return _incident_duplicate_ack(
                    command_id=command_id,
                    idempotency_key=payload.idempotency_key,
                    received_at=received_at,
                    incident_id=payload.incident_id,
                )
            incident_closed_event = repository.insert_event(
                connection,
                event_type=EVENT_INCIDENT_CLOSED,
                actor_type="operator",
                actor_id=payload.resolved_by,
                workflow_id=str(advisory_rerun_context["workflow_id"]),
                idempotency_key=f"{payload.idempotency_key}:incident-closed",
                causation_id=command_id,
                correlation_id=str(advisory_rerun_context["workflow_id"]),
                payload={
                    **resolution_payload,
                    "status": INCIDENT_STATUS_CLOSED,
                    "close_reason": "Board advisory analysis rerun completed successfully.",
                },
                occurred_at=received_at,
            )
            if incident_closed_event is None:
                return _incident_duplicate_ack(
                    command_id=command_id,
                    idempotency_key=payload.idempotency_key,
                    received_at=received_at,
                    incident_id=payload.incident_id,
                )
            repository.refresh_projections(connection)

        return CommandAckEnvelope(
            command_id=command_id,
            idempotency_key=payload.idempotency_key,
            status=CommandAckStatus.ACCEPTED,
            received_at=received_at,
            reason=None,
            causation_hint=f"incident:{payload.incident_id}",
        )

    _trigger_ceo_shadow_safely(
        repository,
        workflow_id=workflow_id,
        trigger_type=EVENT_INCIDENT_RECOVERY_STARTED,
        trigger_ref=payload.incident_id,
    )
    return CommandAckEnvelope(
        command_id=command_id,
        idempotency_key=payload.idempotency_key,
        status=CommandAckStatus.ACCEPTED,
        received_at=received_at,
        reason=None,
        causation_hint=f"incident:{payload.incident_id}",
    )


def handle_ticket_cancel(
    repository: ControlPlaneRepository,
    payload: TicketCancelCommand,
) -> CommandAckEnvelope:
    command_id = new_prefixed_id("cmd")
    received_at = now_local()

    with repository.transaction() as connection:
        existing_event = repository.get_event_by_idempotency_key(connection, payload.idempotency_key)
        if existing_event is not None:
            return _cancel_duplicate_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                ticket_id=payload.ticket_id,
            )

        current_ticket = repository.get_current_ticket_projection(payload.ticket_id, connection=connection)
        current_node = repository.get_current_node_projection(
            payload.workflow_id,
            payload.node_id,
            connection=connection,
        )
        if current_ticket is None or current_node is None:
            return _rejected_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                ticket_id=payload.ticket_id,
                reason="Ticket must exist before it can be cancelled.",
            )
        if current_ticket["workflow_id"] != payload.workflow_id or current_ticket["node_id"] != payload.node_id:
            return _rejected_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                ticket_id=payload.ticket_id,
                reason="Ticket projection does not match the requested workflow or node.",
            )
        if current_node["latest_ticket_id"] != payload.ticket_id:
            return _rejected_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                ticket_id=payload.ticket_id,
                reason="Node projection no longer points at this ticket.",
            )
        if current_ticket["status"] == TICKET_STATUS_CANCELLED:
            return _rejected_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                ticket_id=payload.ticket_id,
                reason=f"Ticket {payload.ticket_id} is already cancelled.",
            )
        if current_ticket["status"] == TICKET_STATUS_COMPLETED:
            return _rejected_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                ticket_id=payload.ticket_id,
                reason=f"Ticket {payload.ticket_id} is already completed.",
            )
        if current_ticket["status"] in {TICKET_STATUS_FAILED, TICKET_STATUS_TIMED_OUT}:
            return _rejected_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                ticket_id=payload.ticket_id,
                reason=f"Ticket {payload.ticket_id} is already terminal.",
            )

        if current_ticket["status"] == TICKET_STATUS_EXECUTING:
            event_row = repository.insert_event(
                connection,
                event_type=EVENT_TICKET_CANCEL_REQUESTED,
                actor_type="operator",
                actor_id=payload.cancelled_by,
                workflow_id=payload.workflow_id,
                idempotency_key=payload.idempotency_key,
                causation_id=command_id,
                correlation_id=payload.workflow_id,
                payload={
                    "ticket_id": payload.ticket_id,
                    "node_id": payload.node_id,
                    "cancelled_by": payload.cancelled_by,
                    "reason": payload.reason,
                },
                occurred_at=received_at,
            )
            if event_row is None:
                return _cancel_duplicate_ack(
                    command_id=command_id,
                    idempotency_key=payload.idempotency_key,
                    received_at=received_at,
                    ticket_id=payload.ticket_id,
                )
        else:
            _insert_ticket_cancelled_event(
                repository=repository,
                connection=connection,
                command_id=command_id,
                occurred_at=received_at,
                workflow_id=payload.workflow_id,
                ticket_id=payload.ticket_id,
                node_id=payload.node_id,
                cancelled_by=payload.cancelled_by,
                reason=payload.reason,
                idempotency_key=payload.idempotency_key,
            )

        repository.refresh_projections(connection)

    if project_workspace_manifest_exists(payload.workflow_id):
        with repository.connection() as connection:
            created_spec = repository.get_latest_ticket_created_payload(connection, payload.ticket_id) or {}
            current_ticket = repository.get_current_ticket_projection(payload.ticket_id, connection=connection) or {}
        if (
            is_workspace_managed_source_code_ticket(created_spec)
            and str(current_ticket.get("status") or "") == TICKET_STATUS_CANCELLED
        ):
            finalize_workspace_ticket_git_status(
                workflow_id=payload.workflow_id,
                ticket_id=payload.ticket_id,
                created_spec=created_spec,
                merge_status="NOT_REQUESTED",
            )
        sync_ticket_boardroom_views(
            repository,
            workflow_id=payload.workflow_id,
            ticket_id=payload.ticket_id,
        )
        sync_active_worktree_index(repository, workflow_id=payload.workflow_id)

    return CommandAckEnvelope(
        command_id=command_id,
        idempotency_key=payload.idempotency_key,
        status=CommandAckStatus.ACCEPTED,
        received_at=received_at,
        reason=None,
        causation_hint=f"ticket:{payload.ticket_id}",
    )


def handle_ticket_create(
    repository: ControlPlaneRepository,
    payload: TicketCreateCommand,
) -> CommandAckEnvelope:
    command_id = new_prefixed_id("cmd")
    received_at = now_local()

    with repository.transaction() as connection:
        existing_event = repository.get_event_by_idempotency_key(connection, payload.idempotency_key)
        if existing_event is not None:
            return _duplicate_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                ticket_id=payload.ticket_id,
                action="ticket-create",
            )

        current_ticket = repository.get_current_ticket_projection(payload.ticket_id, connection=connection)
        if current_ticket is not None:
            return _rejected_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                ticket_id=payload.ticket_id,
                reason=f"Ticket {payload.ticket_id} already exists in projection state.",
            )

        try:
            node_view = resolve_runtime_node_lifecycle(
                repository,
                payload.workflow_id,
                payload.node_id,
                connection=connection,
            )
        except RuntimeNodeLifecycleError as exc:
            return _rejected_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                ticket_id=payload.ticket_id,
                reason=str(exc),
            )
        current_runtime_node = (
            repository.get_runtime_node_projection(
                payload.workflow_id,
                str(node_view.graph_node_id or payload.node_id),
                connection=connection,
            )
            if node_view.materialization_state == MATERIALIZATION_STATE_MATERIALIZED
            else None
        )
        if (
            node_view.materialization_state == MATERIALIZATION_STATE_MATERIALIZED
            and current_runtime_node is not None
            and current_runtime_node["status"] != NODE_STATUS_REWORK_REQUIRED
        ):
            return _rejected_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                ticket_id=payload.ticket_id,
                reason=(
                    f"Node {payload.node_id} cannot accept a new ticket while status is "
                    f"{current_runtime_node['status']}."
                ),
            )

        workflow = repository.get_workflow_projection(payload.workflow_id, connection=connection)
        tenant_id, workspace_id = resolve_workflow_scope(workflow)
        try:
            event_payload = _ensure_ticket_execution_contract_payload(payload.model_dump(mode="json"))
        except ValueError as exc:
            return _rejected_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                ticket_id=payload.ticket_id,
                reason=str(exc),
            )
        assignee_employee_id = _resolve_dispatch_assignee_employee_id(event_payload)
        if assignee_employee_id is not None:
            assignee = repository.get_employee_projection(assignee_employee_id, connection=connection)
            if assignee is None:
                return _rejected_ack(
                    command_id=command_id,
                    idempotency_key=payload.idempotency_key,
                    received_at=received_at,
                    ticket_id=payload.ticket_id,
                    reason=f"dispatch_intent.assignee_employee_id {assignee_employee_id} does not exist.",
                )
            if str(assignee.get("state") or "") != EMPLOYEE_STATE_ACTIVE:
                return _rejected_ack(
                    command_id=command_id,
                    idempotency_key=payload.idempotency_key,
                    received_at=received_at,
                    ticket_id=payload.ticket_id,
                    reason=f"dispatch_intent.assignee_employee_id {assignee_employee_id} is not active.",
                )
            if not employee_supports_execution_contract(
                employee=assignee,
                execution_contract=event_payload.get("execution_contract"),
            ):
                return _rejected_ack(
                    command_id=command_id,
                    idempotency_key=payload.idempotency_key,
                    received_at=received_at,
                    ticket_id=payload.ticket_id,
                    reason=(
                        "dispatch_intent.assignee_employee_id "
                        f"{assignee_employee_id} does not satisfy required capability tags."
                    ),
                )
        dependency_gate_error = _validate_ticket_dependency_gates(
            repository,
            connection,
            workflow_id=payload.workflow_id,
            ticket_id=payload.ticket_id,
            dependency_gate_refs=_resolve_dependency_gate_refs(event_payload),
        )
        if dependency_gate_error is not None:
            return _rejected_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                ticket_id=payload.ticket_id,
                reason=dependency_gate_error,
            )

        event_row = repository.insert_event(
            connection,
            event_type=EVENT_TICKET_CREATED,
            actor_type="system",
            actor_id="system",
            workflow_id=payload.workflow_id,
            idempotency_key=payload.idempotency_key,
            causation_id=command_id,
            correlation_id=payload.workflow_id,
            payload={
                **event_payload,
                "tenant_id": tenant_id,
                "workspace_id": workspace_id,
            },
            occurred_at=received_at,
        )
        if event_row is None:
            return _duplicate_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                ticket_id=payload.ticket_id,
                action="ticket-create",
            )

        repository.refresh_projections(connection)

    if project_workspace_manifest_exists(payload.workflow_id):
        bootstrap_ticket_dossier(
            repository,
            workflow_id=payload.workflow_id,
            ticket_id=payload.ticket_id,
            node_id=payload.node_id,
            summary=str(event_payload.get("acceptance_criteria", [""])[0] or payload.ticket_id),
            required_read_refs=list(event_payload.get("required_read_refs") or []),
            doc_update_requirements=list(event_payload.get("doc_update_requirements") or []),
            git_policy=event_payload.get("git_policy"),
            deliverable_kind=event_payload.get("deliverable_kind"),
            allowed_write_set=list(event_payload.get("allowed_write_set") or []),
            project_checkout_ref=event_payload.get("project_checkout_ref"),
            git_branch_ref=event_payload.get("git_branch_ref"),
        )
        sync_ticket_boardroom_views(
            repository,
            workflow_id=payload.workflow_id,
            ticket_id=payload.ticket_id,
        )

    return CommandAckEnvelope(
        command_id=command_id,
        idempotency_key=payload.idempotency_key,
        status=CommandAckStatus.ACCEPTED,
        received_at=received_at,
        reason=None,
        causation_hint=f"ticket:{payload.ticket_id}",
    )


def handle_ticket_lease(
    repository: ControlPlaneRepository,
    payload: TicketLeaseCommand,
) -> CommandAckEnvelope:
    command_id = new_prefixed_id("cmd")
    received_at = now_local()
    lease_expires_at = received_at + timedelta(seconds=payload.lease_timeout_sec)

    with repository.transaction() as connection:
        existing_event = repository.get_event_by_idempotency_key(connection, payload.idempotency_key)
        if existing_event is not None:
            return _duplicate_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                ticket_id=payload.ticket_id,
                action="ticket-lease",
            )

        current_ticket = repository.get_current_ticket_projection(payload.ticket_id, connection=connection)
        current_node = repository.get_current_node_projection(
            payload.workflow_id,
            payload.node_id,
            connection=connection,
        )
        if current_ticket is None or current_node is None:
            return _rejected_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                ticket_id=payload.ticket_id,
                reason="Ticket must be created before it can be leased.",
            )
        if current_ticket["workflow_id"] != payload.workflow_id or current_ticket["node_id"] != payload.node_id:
            return _rejected_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                ticket_id=payload.ticket_id,
                reason="Ticket projection does not match the requested workflow or node.",
            )
        if current_node["latest_ticket_id"] != payload.ticket_id:
            return _rejected_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                ticket_id=payload.ticket_id,
                reason="Node projection no longer points at this ticket.",
            )
        if current_ticket["status"] not in {TICKET_STATUS_PENDING, TICKET_STATUS_LEASED}:
            return _rejected_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                ticket_id=payload.ticket_id,
                reason=(
                    f"Ticket {payload.ticket_id} can only be leased from PENDING or LEASED; "
                    f"current status is {current_ticket['status']}."
                ),
            )

        current_owner = current_ticket.get("lease_owner")
        current_expiry = current_ticket.get("lease_expires_at")
        lease_is_active = current_expiry is not None and current_expiry > received_at
        if current_ticket["status"] == TICKET_STATUS_LEASED and lease_is_active:
            if current_owner != payload.leased_by:
                return _rejected_ack(
                    command_id=command_id,
                    idempotency_key=payload.idempotency_key,
                    received_at=received_at,
                    ticket_id=payload.ticket_id,
                    reason=(
                        f"Ticket {payload.ticket_id} is currently leased by {current_owner} until "
                        f"{current_expiry.isoformat()}."
                    ),
                )

        if not _employee_is_active(
            repository,
            connection,
            employee_id=payload.leased_by,
        ):
            return _rejected_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                ticket_id=payload.ticket_id,
                reason=f"Worker {payload.leased_by} is not active.",
            )

        provider_id = _resolve_provider_id_for_ticket(
            repository,
            connection,
            lease_owner=payload.leased_by,
        )
        if _is_provider_paused(repository, connection, provider_id):
            return _rejected_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                ticket_id=payload.ticket_id,
                reason=(
                    f"Ticket {payload.ticket_id} cannot be leased because worker provider "
                    f"{provider_id} is currently paused."
                ),
            )

        created_spec = repository.get_latest_ticket_created_payload(connection, payload.ticket_id)
        precondition_result = _evaluate_ticket_execution_precondition(
            repository,
            connection,
            ticket=current_ticket,
            created_spec=created_spec,
            lease_owner=payload.leased_by,
        )
        if precondition_result is not None and _sync_ticket_execution_precondition_state(
            repository,
            connection,
            command_id=command_id,
            occurred_at=received_at,
            workflow_id=payload.workflow_id,
            ticket=current_ticket,
            node_id=payload.node_id,
            precondition_result=precondition_result,
            actor_id="ticket-lease",
        ):
            return _rejected_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                ticket_id=payload.ticket_id,
                reason=str(precondition_result["provider_reason"]),
            )

        event_row = repository.insert_event(
            connection,
            event_type=EVENT_TICKET_LEASED,
            actor_type="worker",
            actor_id=payload.leased_by,
            workflow_id=payload.workflow_id,
            idempotency_key=payload.idempotency_key,
            causation_id=command_id,
            correlation_id=payload.workflow_id,
            payload={
                "ticket_id": payload.ticket_id,
                "node_id": payload.node_id,
                "leased_by": payload.leased_by,
                "lease_timeout_sec": payload.lease_timeout_sec,
                "lease_expires_at": lease_expires_at.isoformat(),
            },
            occurred_at=received_at,
        )
        if event_row is None:
            return _duplicate_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                ticket_id=payload.ticket_id,
                action="ticket-lease",
            )

        repository.refresh_projections(connection)

    if project_workspace_manifest_exists(payload.workflow_id):
        with repository.connection() as connection:
            created_spec = repository.get_latest_ticket_created_payload(connection, payload.ticket_id) or {}
        if is_workspace_managed_source_code_ticket(created_spec):
            checkout_truth = resolve_ticket_checkout_truth(
                payload.workflow_id,
                payload.ticket_id,
                created_spec,
            )
            checkout_path = ensure_project_checkout(
                workflow_id=payload.workflow_id,
                ticket_id=payload.ticket_id,
                branch_ref=checkout_truth["git_branch_ref"],
            )
            write_worktree_checkout_receipt(
                workflow_id=payload.workflow_id,
                ticket_id=payload.ticket_id,
                project_checkout_ref=checkout_truth["project_checkout_ref"],
                project_checkout_path=checkout_path,
                git_branch_ref=checkout_truth["git_branch_ref"],
            )
            update_ticket_git_closeout_notes(
                workflow_id=payload.workflow_id,
                ticket_id=payload.ticket_id,
                git_policy=str(created_spec.get("git_policy") or ""),
                git_branch_ref=checkout_truth["git_branch_ref"],
                project_checkout_ref=checkout_truth["project_checkout_ref"],
                project_checkout_path=str(checkout_path),
                merge_status="EXECUTING",
            )
        sync_ticket_boardroom_views(
            repository,
            workflow_id=payload.workflow_id,
            ticket_id=payload.ticket_id,
        )
        sync_active_worktree_index(repository, workflow_id=payload.workflow_id)

    return CommandAckEnvelope(
        command_id=command_id,
        idempotency_key=payload.idempotency_key,
        status=CommandAckStatus.ACCEPTED,
        received_at=received_at,
        reason=None,
        causation_hint=f"ticket:{payload.ticket_id}",
    )


def handle_ticket_start(
    repository: ControlPlaneRepository,
    payload: TicketStartCommand,
) -> CommandAckEnvelope:
    command_id = new_prefixed_id("cmd")
    received_at = now_local()

    with repository.transaction() as connection:
        existing_event = repository.get_event_by_idempotency_key(connection, payload.idempotency_key)
        if existing_event is not None:
            return _duplicate_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                ticket_id=payload.ticket_id,
                action="ticket-start",
            )

        try:
            node_view = resolve_runtime_node_lifecycle(
                repository,
                payload.workflow_id,
                payload.node_id,
                connection=connection,
            )
        except RuntimeNodeLifecycleError as exc:
            return _rejected_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                ticket_id=payload.ticket_id,
                reason=str(exc),
            )
        if node_view.materialization_state == MATERIALIZATION_STATE_PLANNED:
            return _rejected_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                ticket_id=payload.ticket_id,
                reason=build_runtime_node_lifecycle_reason(
                    workflow_id=payload.workflow_id,
                    node_id=payload.node_id,
                    reason_code=REASON_CODE_PLANNED_PLACEHOLDER_NOT_MATERIALIZED,
                    operation="ticket-start",
                ),
            )
        current_ticket = repository.get_current_ticket_projection(payload.ticket_id, connection=connection)
        current_runtime_node = repository.get_runtime_node_projection(
            payload.workflow_id,
            str(node_view.graph_node_id or payload.node_id),
            connection=connection,
        )
        current_node = repository.get_current_node_projection(
            payload.workflow_id,
            payload.node_id,
            connection=connection,
        )
        if current_ticket is None:
            return _rejected_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                ticket_id=payload.ticket_id,
                reason="Ticket must be created before it can be started.",
            )
        current_ticket_spec = repository.get_latest_ticket_created_payload(connection, payload.ticket_id) or {}
        graph_identity = resolve_ticket_graph_identity(
            ticket_id=payload.ticket_id,
            created_spec=current_ticket_spec,
            runtime_node_id=payload.node_id,
        )
        current_runtime_node = repository.get_runtime_node_projection(
            payload.workflow_id,
            str(graph_identity.graph_node_id or payload.node_id),
            connection=connection,
        )
        active_node_projection = current_runtime_node
        if active_node_projection is None:
            return _rejected_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                ticket_id=payload.ticket_id,
                reason="Runtime node projection is missing for the current graph lane.",
            )
        if current_ticket["workflow_id"] != payload.workflow_id or current_ticket["node_id"] != payload.node_id:
            return _rejected_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                ticket_id=payload.ticket_id,
                reason="Ticket projection does not match the requested workflow or node.",
            )
        if active_node_projection["latest_ticket_id"] != payload.ticket_id:
            return _rejected_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                ticket_id=payload.ticket_id,
                reason=(
                    "Runtime node projection no longer points at this ticket."
                    if uses_runtime_node_truth
                    else "Node projection no longer points at this ticket."
                ),
            )
        version_guard_reason = repository.validate_projection_version_guard(
            current_ticket=current_ticket,
            current_node=current_node,
            current_runtime_node=current_runtime_node,
            expected_ticket_version=payload.expected_ticket_version,
            expected_node_version=payload.expected_node_version,
            expected_runtime_node_version=payload.expected_runtime_node_version,
        )
        if version_guard_reason is not None:
            return _rejected_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                ticket_id=payload.ticket_id,
                reason=version_guard_reason,
            )
        if active_node_projection["status"] != NODE_STATUS_PENDING:
            return _rejected_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                ticket_id=payload.ticket_id,
                reason=(
                    f"Ticket {payload.ticket_id} can only start while node {payload.node_id} is "
                    f"PENDING; current node status is {active_node_projection['status']}."
                ),
            )
        if current_ticket["status"] != TICKET_STATUS_LEASED:
            return _rejected_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                ticket_id=payload.ticket_id,
                reason=(
                    f"Ticket {payload.ticket_id} can only start from LEASED; current ticket status "
                    f"is {current_ticket['status']}."
                ),
            )

        lease_owner = current_ticket.get("lease_owner")
        lease_expires_at = current_ticket.get("lease_expires_at")
        if lease_owner != payload.started_by:
            return _rejected_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                ticket_id=payload.ticket_id,
                reason=(
                    f"Ticket {payload.ticket_id} is leased by {lease_owner}; "
                    f"{payload.started_by} cannot start it."
                ),
            )
        if lease_expires_at is None or lease_expires_at <= received_at:
            return _rejected_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                ticket_id=payload.ticket_id,
                reason=f"Ticket {payload.ticket_id} lease is missing or expired.",
            )

        if lease_owner is None or not _employee_is_active(
            repository,
            connection,
            employee_id=str(lease_owner),
        ):
            return _rejected_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                ticket_id=payload.ticket_id,
                reason=f"Worker {lease_owner} is not active.",
            )

        provider_id = _resolve_provider_id_for_ticket(
            repository,
            connection,
            ticket=current_ticket,
            lease_owner=lease_owner,
        )
        if _is_provider_paused(repository, connection, provider_id) and not _allow_paused_provider_start(
            provider_id
        ):
            return _rejected_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                ticket_id=payload.ticket_id,
                reason=(
                    f"Ticket {payload.ticket_id} cannot start because worker provider {provider_id} "
                    "is currently paused."
                ),
            )

        created_spec = repository.get_latest_ticket_created_payload(connection, payload.ticket_id)
        precondition_result = _evaluate_ticket_execution_precondition(
            repository,
            connection,
            ticket=current_ticket,
            created_spec=created_spec,
            lease_owner=str(lease_owner),
        )
        if precondition_result is not None and _sync_ticket_execution_precondition_state(
            repository,
            connection,
            command_id=command_id,
            occurred_at=received_at,
            workflow_id=payload.workflow_id,
            ticket=current_ticket,
            node_id=payload.node_id,
            precondition_result=precondition_result,
            actor_id="ticket-start",
        ):
            return _rejected_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                ticket_id=payload.ticket_id,
                reason=str(precondition_result["provider_reason"]),
            )

        event_row = repository.insert_event(
            connection,
            event_type=EVENT_TICKET_STARTED,
            actor_type="worker",
            actor_id=payload.started_by,
            workflow_id=payload.workflow_id,
            idempotency_key=payload.idempotency_key,
            causation_id=command_id,
            correlation_id=payload.workflow_id,
            payload={
                "ticket_id": payload.ticket_id,
                "node_id": payload.node_id,
                "started_by": payload.started_by,
            },
            occurred_at=received_at,
        )
        if event_row is None:
            return _duplicate_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                ticket_id=payload.ticket_id,
                action="ticket-start",
            )

        repository.refresh_projections(connection)

    if project_workspace_manifest_exists(payload.workflow_id):
        sync_active_worktree_index(repository, workflow_id=payload.workflow_id)

    return CommandAckEnvelope(
        command_id=command_id,
        idempotency_key=payload.idempotency_key,
        status=CommandAckStatus.ACCEPTED,
        received_at=received_at,
        reason=None,
        causation_hint=f"ticket:{payload.ticket_id}",
    )


def handle_ticket_heartbeat(
    repository: ControlPlaneRepository,
    payload: TicketHeartbeatCommand,
) -> CommandAckEnvelope:
    command_id = new_prefixed_id("cmd")
    received_at = now_local()

    with repository.transaction() as connection:
        existing_event = repository.get_event_by_idempotency_key(connection, payload.idempotency_key)
        if existing_event is not None:
            return _duplicate_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                ticket_id=payload.ticket_id,
                action="ticket-heartbeat",
            )

        current_ticket = repository.get_current_ticket_projection(payload.ticket_id, connection=connection)
        current_node = repository.get_current_node_projection(
            payload.workflow_id,
            payload.node_id,
            connection=connection,
        )
        if current_ticket is None or current_node is None:
            return _rejected_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                ticket_id=payload.ticket_id,
                reason="Ticket must be created and started before it can report heartbeat.",
            )
        if current_ticket["workflow_id"] != payload.workflow_id or current_ticket["node_id"] != payload.node_id:
            return _rejected_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                ticket_id=payload.ticket_id,
                reason="Ticket projection does not match the requested workflow or node.",
            )
        if current_node["latest_ticket_id"] != payload.ticket_id:
            return _rejected_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                ticket_id=payload.ticket_id,
                reason="Node projection no longer points at this ticket.",
            )
        if current_ticket["status"] != TICKET_STATUS_EXECUTING or current_node["status"] != NODE_STATUS_EXECUTING:
            return _rejected_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                ticket_id=payload.ticket_id,
                reason=(
                    f"Ticket {payload.ticket_id} can only report heartbeat while ticket/node status is "
                    f"EXECUTING/EXECUTING; current status is "
                    f"{current_ticket['status']}/{current_node['status']}."
                ),
            )

        lease_owner = current_ticket.get("lease_owner")
        if lease_owner != payload.reported_by:
            return _rejected_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                ticket_id=payload.ticket_id,
                reason=(
                    f"Ticket {payload.ticket_id} is leased by {lease_owner}; "
                    f"{payload.reported_by} cannot report heartbeat."
                ),
            )

        current_heartbeat_expiry = _resolve_current_heartbeat_expiry(current_ticket)
        if current_heartbeat_expiry is None or current_heartbeat_expiry <= received_at:
            return _rejected_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                ticket_id=payload.ticket_id,
                reason=f"Ticket {payload.ticket_id} heartbeat window is missing or expired.",
            )

        heartbeat_timeout_sec = _resolve_heartbeat_timeout_sec(current_ticket)
        heartbeat_expires_at = received_at + timedelta(seconds=heartbeat_timeout_sec)
        event_row = repository.insert_event(
            connection,
            event_type=EVENT_TICKET_HEARTBEAT_RECORDED,
            actor_type="worker",
            actor_id=payload.reported_by,
            workflow_id=payload.workflow_id,
            idempotency_key=payload.idempotency_key,
            causation_id=command_id,
            correlation_id=payload.workflow_id,
            payload={
                "ticket_id": payload.ticket_id,
                "node_id": payload.node_id,
                "reported_by": payload.reported_by,
                "heartbeat_expires_at": heartbeat_expires_at.isoformat(),
            },
            occurred_at=received_at,
        )
        if event_row is None:
            return _duplicate_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                ticket_id=payload.ticket_id,
                action="ticket-heartbeat",
            )

        repository.refresh_projections(connection)

    return CommandAckEnvelope(
        command_id=command_id,
        idempotency_key=payload.idempotency_key,
        status=CommandAckStatus.ACCEPTED,
        received_at=received_at,
        reason=None,
        causation_hint=f"ticket:{payload.ticket_id}",
    )


def handle_ticket_fail(
    repository: ControlPlaneRepository,
    payload: TicketFailCommand,
) -> CommandAckEnvelope:
    command_id = new_prefixed_id("cmd")
    received_at = now_local()
    failed_created_spec: dict[str, Any] | None = None

    with repository.transaction() as connection:
        existing_event = repository.get_event_by_idempotency_key(connection, payload.idempotency_key)
        if existing_event is not None:
            return _duplicate_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                ticket_id=payload.ticket_id,
                action="ticket-fail",
            )

        current_ticket = repository.get_current_ticket_projection(payload.ticket_id, connection=connection)
        current_node = repository.get_current_node_projection(
            payload.workflow_id,
            payload.node_id,
            connection=connection,
        )
        if current_ticket is None or current_node is None:
            return _rejected_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                ticket_id=payload.ticket_id,
                reason="Ticket must be created and started before it can fail.",
            )
        if current_ticket["workflow_id"] != payload.workflow_id or current_ticket["node_id"] != payload.node_id:
            return _rejected_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                ticket_id=payload.ticket_id,
                reason="Ticket projection does not match the requested workflow or node.",
            )
        if current_node["latest_ticket_id"] != payload.ticket_id:
            return _rejected_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                ticket_id=payload.ticket_id,
                reason="Node projection no longer points at this ticket.",
            )
        if current_ticket["status"] != TICKET_STATUS_EXECUTING or current_node["status"] != NODE_STATUS_EXECUTING:
            return _rejected_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                ticket_id=payload.ticket_id,
                reason=(
                    f"Ticket {payload.ticket_id} can only fail while ticket/node status is "
                    f"EXECUTING/EXECUTING; current status is "
                    f"{current_ticket['status']}/{current_node['status']}."
                ),
            )

        created_spec = repository.get_latest_ticket_created_payload(connection, payload.ticket_id)
        failed_created_spec = dict(created_spec or {}) if created_spec is not None else None

        failure_payload = _build_failure_payload(
            failure_kind=payload.failure_kind,
            failure_message=payload.failure_message,
            failure_detail=payload.failure_detail,
        )
        event_row = repository.insert_event(
            connection,
            event_type=EVENT_TICKET_FAILED,
            actor_type="worker",
            actor_id=payload.failed_by,
            workflow_id=payload.workflow_id,
            idempotency_key=payload.idempotency_key,
            causation_id=command_id,
            correlation_id=payload.workflow_id,
            payload={
                "ticket_id": payload.ticket_id,
                "node_id": payload.node_id,
                "failed_by": payload.failed_by,
                **failure_payload,
            },
            occurred_at=received_at,
        )
        if event_row is None:
            return _duplicate_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                ticket_id=payload.ticket_id,
                action="ticket-fail",
            )

        next_ticket_id: str | None = None
        provider_id = _resolve_provider_id_for_ticket(
            repository,
            connection,
            ticket=current_ticket,
            failure_detail=failure_payload.get("failure_detail"),
        )
        if payload.failure_kind in DECOMPOSITION_RECOVERY_FAILURE_KINDS and created_spec is not None:
            next_ticket_id = _open_decomposition_recovery_incident(
                repository=repository,
                connection=connection,
                command_id=command_id,
                occurred_at=received_at,
                workflow_id=payload.workflow_id,
                ticket_id=payload.ticket_id,
                node_id=payload.node_id,
                created_spec=created_spec,
                failure_payload=failure_payload,
                idempotency_key_base=payload.idempotency_key,
            )
        elif _should_open_provider_incident_for_failure(payload.failure_kind) and provider_id is not None:
            _open_provider_incident(
                repository=repository,
                connection=connection,
                command_id=command_id,
                occurred_at=received_at,
                workflow_id=payload.workflow_id,
                ticket_id=payload.ticket_id,
                node_id=payload.node_id,
                provider_id=provider_id,
                failure_payload=failure_payload,
                idempotency_key_base=payload.idempotency_key,
            )
        elif created_spec is not None:
            failure_streak_count = _calculate_failure_streak(
                repository,
                connection,
                workflow_id=payload.workflow_id,
                node_id=payload.node_id,
                created_spec=created_spec,
                failure_fingerprint=str(failure_payload["failure_fingerprint"]),
            )
            if _should_escalate_repeat_failure(
                created_spec=created_spec,
                failure_kind=payload.failure_kind,
                failure_streak_count=failure_streak_count,
            ):
                _open_repeated_failure_incident(
                    repository=repository,
                    connection=connection,
                    command_id=command_id,
                    occurred_at=received_at,
                    workflow_id=payload.workflow_id,
                    ticket_id=payload.ticket_id,
                    node_id=payload.node_id,
                    failure_streak_count=failure_streak_count,
                    failure_payload=failure_payload,
                    idempotency_key_base=payload.idempotency_key,
                )
            elif _should_retry_failure(
                current_ticket=current_ticket,
                created_spec=created_spec,
                failure_kind=payload.failure_kind,
            ):
                next_ticket_id = _schedule_retry(
                    repository=repository,
                    connection=connection,
                    command_id=command_id,
                    occurred_at=received_at,
                    workflow_id=payload.workflow_id,
                    failed_ticket_id=payload.ticket_id,
                    node_id=payload.node_id,
                    created_spec=created_spec,
                    failure_payload=failure_payload,
                    retry_source_event_type=EVENT_TICKET_FAILED,
                    idempotency_key_base=payload.idempotency_key,
                )

        repository.refresh_projections(connection)

    if project_workspace_manifest_exists(payload.workflow_id):
        if failed_created_spec is not None and is_workspace_managed_source_code_ticket(failed_created_spec):
            finalize_workspace_ticket_git_status(
                workflow_id=payload.workflow_id,
                ticket_id=payload.ticket_id,
                created_spec=failed_created_spec,
                merge_status="NOT_REQUESTED",
            )
        sync_active_worktree_index(repository, workflow_id=payload.workflow_id)
    _refresh_ticket_context_archive(repository, payload.ticket_id)

    _trigger_ceo_shadow_safely(
        repository,
        workflow_id=payload.workflow_id,
        trigger_type=EVENT_TICKET_FAILED,
        trigger_ref=payload.ticket_id,
    )
    return CommandAckEnvelope(
        command_id=command_id,
        idempotency_key=payload.idempotency_key,
        status=CommandAckStatus.ACCEPTED,
        received_at=received_at,
        reason=None,
        causation_hint=f"ticket:{next_ticket_id or payload.ticket_id}",
    )


def handle_ticket_result_submit(
    repository: ControlPlaneRepository,
    payload: TicketResultSubmitCommand,
    developer_inspector_store: DeveloperInspectorStore | None = None,
    artifact_store: ArtifactStore | None = None,
) -> CommandAckEnvelope:
    try:
        node_view = resolve_runtime_node_lifecycle(
            repository,
            payload.workflow_id,
            payload.node_id,
        )
    except RuntimeNodeLifecycleError as exc:
        return _rejected_ack(
            command_id=new_prefixed_id("cmd"),
            idempotency_key=payload.idempotency_key,
            received_at=now_local(),
            ticket_id=payload.ticket_id,
            reason=str(exc),
        )
    if node_view.materialization_state == MATERIALIZATION_STATE_PLANNED:
        return _rejected_ack(
            command_id=new_prefixed_id("cmd"),
            idempotency_key=payload.idempotency_key,
            received_at=now_local(),
            ticket_id=payload.ticket_id,
            reason=build_runtime_node_lifecycle_reason(
                workflow_id=payload.workflow_id,
                node_id=payload.node_id,
                reason_code=REASON_CODE_PLANNED_PLACEHOLDER_NOT_MATERIALIZED,
                operation="ticket-result-submit",
            ),
        )
    current_ticket = repository.get_current_ticket_projection(payload.ticket_id)
    current_node = repository.get_current_node_projection(payload.workflow_id, payload.node_id)
    with repository.connection() as connection:
        current_ticket_spec = repository.get_latest_ticket_created_payload(connection, payload.ticket_id) or {}
    graph_identity = resolve_ticket_graph_identity(
        ticket_id=payload.ticket_id,
        created_spec=current_ticket_spec,
        runtime_node_id=payload.node_id,
    )
    current_runtime_node = repository.get_runtime_node_projection(
        payload.workflow_id,
        str(graph_identity.graph_node_id or node_view.graph_node_id or payload.node_id),
    )
    active_node_projection = current_runtime_node
    if current_ticket is None or active_node_projection is None:
        return _rejected_ack(
            command_id=new_prefixed_id("cmd"),
            idempotency_key=payload.idempotency_key,
            received_at=now_local(),
            ticket_id=payload.ticket_id,
            reason="Runtime node projection is missing for the current graph lane.",
        )

    if current_ticket["status"] == TICKET_STATUS_CANCELLED:
        return _rejected_ack(
            command_id=new_prefixed_id("cmd"),
            idempotency_key=payload.idempotency_key,
            received_at=now_local(),
            ticket_id=payload.ticket_id,
            reason=f"Ticket {payload.ticket_id} is already cancelled.",
        )

    if (
        current_ticket["status"] == TICKET_STATUS_CANCEL_REQUESTED
        or active_node_projection["status"] == NODE_STATUS_CANCEL_REQUESTED
    ):
        command_id = new_prefixed_id("cmd")
        received_at = now_local()
        with repository.transaction() as connection:
            existing_event = repository.get_event_by_idempotency_key(connection, payload.idempotency_key)
            if existing_event is not None:
                return _duplicate_ack(
                    command_id=command_id,
                    idempotency_key=payload.idempotency_key,
                    received_at=received_at,
                    ticket_id=payload.ticket_id,
                    action="ticket-result-submit",
                )
            _insert_ticket_cancelled_event(
                repository=repository,
                connection=connection,
                command_id=command_id,
                occurred_at=received_at,
                workflow_id=payload.workflow_id,
                ticket_id=payload.ticket_id,
                node_id=payload.node_id,
                cancelled_by=payload.submitted_by,
                reason="Late result arrived after cancellation was requested.",
                idempotency_key=payload.idempotency_key,
            )
            repository.refresh_projections(connection)
        return CommandAckEnvelope(
            command_id=command_id,
            idempotency_key=payload.idempotency_key,
            status=CommandAckStatus.ACCEPTED,
            received_at=received_at,
            reason=None,
            causation_hint=f"ticket:{payload.ticket_id}",
        )

    if current_ticket["status"] != TICKET_STATUS_EXECUTING or active_node_projection["status"] != NODE_STATUS_EXECUTING:
        return _rejected_ack(
            command_id=new_prefixed_id("cmd"),
            idempotency_key=payload.idempotency_key,
            received_at=now_local(),
            ticket_id=payload.ticket_id,
            reason=(
                f"Ticket {payload.ticket_id} can only submit a structured result while ticket/node "
                f"status is EXECUTING/EXECUTING; current status is "
                f"{current_ticket['status']}/{active_node_projection['status']}."
            ),
        )

    if payload.result_status == TicketResultStatus.FAILED:
        return handle_ticket_fail(
            repository,
            TicketFailCommand(
                workflow_id=payload.workflow_id,
                ticket_id=payload.ticket_id,
                node_id=payload.node_id,
                failed_by=payload.submitted_by,
                failure_kind=payload.failure_kind or "RUNTIME_ERROR",
                failure_message=payload.failure_message or payload.summary,
                failure_detail=payload.failure_detail,
                idempotency_key=payload.idempotency_key,
            ),
        )

    with repository.connection() as connection:
        created_spec = repository.get_latest_ticket_created_payload(connection, payload.ticket_id)
        compiled_execution_package_guard_reason = repository.validate_compiled_execution_package_guard(
            connection,
            ticket_id=payload.ticket_id,
            compile_request_id=payload.compile_request_id,
            compiled_execution_package_version_ref=payload.compiled_execution_package_version_ref,
        )

    if created_spec is None:
        return handle_ticket_fail(
            repository,
            TicketFailCommand(
                workflow_id=payload.workflow_id,
                ticket_id=payload.ticket_id,
                node_id=payload.node_id,
                failed_by=payload.submitted_by,
                failure_kind="SCHEMA_ERROR",
                failure_message="Ticket result validation could not load the created ticket spec.",
                failure_detail={},
                idempotency_key=payload.idempotency_key,
            ),
        )
    if compiled_execution_package_guard_reason is not None:
        return _rejected_ack(
            command_id=new_prefixed_id("cmd"),
            idempotency_key=payload.idempotency_key,
            received_at=now_local(),
            ticket_id=payload.ticket_id,
            reason=compiled_execution_package_guard_reason,
        )

    try:
        validate_output_payload(
            schema_ref=str(created_spec.get("output_schema_ref") or ""),
            schema_version=int(created_spec.get("output_schema_version") or 0),
            submitted_schema_version=payload.schema_version,
            payload=payload.payload,
        )
    except OutputSchemaValidationError as exc:
        return handle_ticket_fail(
            repository,
            TicketFailCommand(
                workflow_id=payload.workflow_id,
                ticket_id=payload.ticket_id,
                node_id=payload.node_id,
                failed_by=payload.submitted_by,
                failure_kind="SCHEMA_ERROR",
                failure_message=str(exc),
                failure_detail={
                    "schema_ref": created_spec.get("output_schema_ref"),
                    "schema_version": created_spec.get("output_schema_version"),
                    "field_path": exc.field_path,
                    "expected": exc.expected,
                    "actual": exc.actual,
                },
                idempotency_key=payload.idempotency_key,
            ),
        )
    except ValueError as exc:
        return handle_ticket_fail(
            repository,
            TicketFailCommand(
                workflow_id=payload.workflow_id,
                ticket_id=payload.ticket_id,
                node_id=payload.node_id,
                failed_by=payload.submitted_by,
                failure_kind="SCHEMA_ERROR",
                failure_message=str(exc),
                failure_detail={
                    "schema_ref": created_spec.get("output_schema_ref"),
                    "schema_version": created_spec.get("output_schema_version"),
                },
                idempotency_key=payload.idempotency_key,
            ),
        )

    hook_validation_error = _validate_source_code_delivery_hooks(
        created_spec=created_spec,
        payload=payload,
    )
    if hook_validation_error is None:
        hook_validation_error = _validate_structured_document_delivery_hooks(
            created_spec=created_spec,
            payload=payload,
        )
    if hook_validation_error is None:
        hook_validation_error = _validate_closeout_delivery_hooks(
            repository,
            created_spec=created_spec,
            payload=payload,
        )
    if hook_validation_error is None:
        hook_validation_error = _validate_governance_document_hooks(
            created_spec=created_spec,
            payload=payload,
        )
    if hook_validation_error is None:
        hook_validation_error = _validate_backlog_recommendation_hooks(
            created_spec=created_spec,
            payload=payload,
        )
    if hook_validation_error is not None:
        return handle_ticket_fail(
            repository,
            TicketFailCommand(
                workflow_id=payload.workflow_id,
                ticket_id=payload.ticket_id,
                node_id=payload.node_id,
                failed_by=payload.submitted_by,
                failure_kind=WORKSPACE_HOOK_VALIDATION_FAILURE_KIND,
                failure_message=hook_validation_error,
                failure_detail={},
                idempotency_key=payload.idempotency_key,
            ),
        )

    effective_written_artifacts = list(payload.written_artifacts)
    governance_audit_artifact = _build_governance_audit_written_artifact(
        created_spec=created_spec,
        payload=payload,
        written_artifacts=effective_written_artifacts,
    )
    if governance_audit_artifact is not None:
        effective_written_artifacts.append(governance_audit_artifact)

    allowed_write_set = list(created_spec.get("allowed_write_set") or [])
    violating_paths = [
        item.path
        for item in effective_written_artifacts
        if not _match_allowed_write_set(item.path, allowed_write_set)
        and not _is_allowed_auto_governance_audit_sidecar(
            item,
            governance_audit_artifact=governance_audit_artifact,
            submitted_artifacts=list(payload.written_artifacts),
            allowed_write_set=allowed_write_set,
        )
    ]
    if violating_paths:
        return handle_ticket_fail(
            repository,
            TicketFailCommand(
                workflow_id=payload.workflow_id,
                ticket_id=payload.ticket_id,
                node_id=payload.node_id,
                failed_by=payload.submitted_by,
                failure_kind="WRITE_SET_VIOLATION",
                failure_message="Structured result attempted to write outside the allowed write set.",
                failure_detail={
                    "violating_paths": violating_paths,
                    "allowed_write_set": allowed_write_set,
                },
                idempotency_key=payload.idempotency_key,
            ),
        )

    command_id = new_prefixed_id("cmd")
    received_at = now_local()
    resolved_artifact_store = artifact_store or repository.artifact_store
    effective_git_commit_record = payload.git_commit_record

    if is_workspace_managed_source_code_ticket(created_spec):
        checkout_truth = resolve_ticket_checkout_truth(
            payload.workflow_id,
            payload.ticket_id,
            created_spec,
        )
        checkout_path = ensure_project_checkout(
            workflow_id=payload.workflow_id,
            ticket_id=payload.ticket_id,
            branch_ref=checkout_truth["git_branch_ref"],
        )
        materialize_workspace_delivery_files(
            workflow_id=payload.workflow_id,
            ticket_id=payload.ticket_id,
            project_checkout_path=checkout_path,
            written_artifacts=[
                item.model_dump(mode="json") for item in effective_written_artifacts
            ],
        )
        actual_git_commit_record = commit_project_checkout(
            workflow_id=payload.workflow_id,
            ticket_id=payload.ticket_id,
            project_checkout_path=checkout_path,
            git_branch_ref=checkout_truth["git_branch_ref"],
        )
        effective_git_commit_record = TicketGitCommitRecord.model_validate(actual_git_commit_record)
        effective_written_artifacts = [
            TicketWrittenArtifact.model_validate(item)
            for item in build_effective_workspace_written_artifacts(
                effective_written_artifacts,
                git_commit_record=actual_git_commit_record,
            )
        ]
        materialize_workspace_delivery_files(
            workflow_id=payload.workflow_id,
            ticket_id=payload.ticket_id,
            project_checkout_path=checkout_path,
            written_artifacts=[
                item.model_dump(mode="json") for item in effective_written_artifacts
            ],
        )
        write_worktree_checkout_receipt(
            workflow_id=payload.workflow_id,
            ticket_id=payload.ticket_id,
            project_checkout_ref=checkout_truth["project_checkout_ref"],
            project_checkout_path=checkout_path,
            git_branch_ref=checkout_truth["git_branch_ref"],
        )
        update_ticket_git_closeout_notes(
            workflow_id=payload.workflow_id,
            ticket_id=payload.ticket_id,
            git_policy=str(created_spec.get("git_policy") or ""),
            git_branch_ref=checkout_truth["git_branch_ref"],
            project_checkout_ref=checkout_truth["project_checkout_ref"],
            project_checkout_path=str(checkout_path),
            merge_status="PENDING_REVIEW_GATE",
        )

    materialized_artifacts: list[MaterializedArtifact] = []
    try:
        prepared_artifacts, materialized_artifacts = _prepare_ticket_artifacts(
            artifact_store=resolved_artifact_store,
            written_artifacts=effective_written_artifacts,
            created_at=received_at,
            workflow_id=payload.workflow_id,
            ticket_id=payload.ticket_id,
        )
    except ValueError as exc:
        return handle_ticket_fail(
            repository,
            TicketFailCommand(
                workflow_id=payload.workflow_id,
                ticket_id=payload.ticket_id,
                node_id=payload.node_id,
                failed_by=payload.submitted_by,
                failure_kind="ARTIFACT_VALIDATION_ERROR",
                failure_message=str(exc),
                failure_detail={},
                idempotency_key=payload.idempotency_key,
            ),
        )
    except RuntimeError as exc:
        return handle_ticket_fail(
            repository,
            TicketFailCommand(
                workflow_id=payload.workflow_id,
                ticket_id=payload.ticket_id,
                node_id=payload.node_id,
                failed_by=payload.submitted_by,
                failure_kind="ARTIFACT_PERSIST_ERROR",
                failure_message=str(exc),
                failure_detail={},
                idempotency_key=payload.idempotency_key,
            ),
        )

    persisted_inspector_artifacts: list[PersistedDeveloperInspectorArtifact] = []
    completed_artifact_refs = _dedupe_artifact_refs(
        list(payload.artifact_refs) + [artifact.artifact_ref for artifact in prepared_artifacts]
    )
    produced_process_assets = build_result_process_assets(
        ticket_id=payload.ticket_id,
        created_spec=created_spec,
        result_payload=payload.payload if isinstance(payload.payload, dict) else None,
        artifact_refs=completed_artifact_refs,
        written_artifacts=[
            item.model_dump(mode="json")
            for item in effective_written_artifacts
        ],
        verification_evidence_refs=list(payload.verification_evidence_refs),
        git_commit_record=(
            effective_git_commit_record.model_dump(mode="json")
            if effective_git_commit_record is not None
            else None
        ),
    )
    try:
        with repository.transaction() as connection:
            existing_event = repository.get_event_by_idempotency_key(connection, payload.idempotency_key)
            if existing_event is not None:
                return _duplicate_ack(
                    command_id=command_id,
                    idempotency_key=payload.idempotency_key,
                    received_at=received_at,
                    ticket_id=payload.ticket_id,
                    action="ticket-result-submit",
                )

            for artifact in prepared_artifacts:
                save_prepared_artifact_record(
                    repository,
                    connection,
                    prepared_artifact=artifact,
                    workflow_id=payload.workflow_id,
                    ticket_id=payload.ticket_id,
                    node_id=payload.node_id,
                    created_at=received_at,
                )

            causation_hint = _complete_ticket_locked(
                repository=repository,
                connection=connection,
                command_id=command_id,
                received_at=received_at,
                payload=TicketCompletedCommand(
                    workflow_id=payload.workflow_id,
                    ticket_id=payload.ticket_id,
                    node_id=payload.node_id,
                    completed_by=payload.submitted_by,
                    completion_summary=payload.summary,
                    artifact_refs=completed_artifact_refs,
                    written_artifacts=[
                        TicketWrittenArtifact.model_validate(item.model_dump(mode="json"))
                        for item in effective_written_artifacts
                    ],
                    produced_process_assets=produced_process_assets,
                    verification_evidence_refs=list(payload.verification_evidence_refs),
                    git_commit_record=effective_git_commit_record,
                    review_request=payload.review_request,
                    idempotency_key=payload.idempotency_key,
                ),
                result_payload=payload.payload,
                developer_inspector_store=developer_inspector_store,
                persisted_artifacts=persisted_inspector_artifacts,
            )
    except ValueError as exc:
        cleanup_materialized_artifacts(resolved_artifact_store, materialized_artifacts)
        if developer_inspector_store is not None:
            for artifact in persisted_inspector_artifacts:
                developer_inspector_store.delete_ref(artifact.ref)
        return handle_ticket_fail(
            repository,
            TicketFailCommand(
                workflow_id=payload.workflow_id,
                ticket_id=payload.ticket_id,
                node_id=payload.node_id,
                failed_by=payload.submitted_by,
                failure_kind="ARTIFACT_VALIDATION_ERROR",
                failure_message=str(exc),
                failure_detail={},
                idempotency_key=payload.idempotency_key,
            ),
        )
    except sqlite3.IntegrityError:
        cleanup_materialized_artifacts(resolved_artifact_store, materialized_artifacts)
        return handle_ticket_fail(
            repository,
            TicketFailCommand(
                workflow_id=payload.workflow_id,
                ticket_id=payload.ticket_id,
                node_id=payload.node_id,
                failed_by=payload.submitted_by,
                failure_kind="ARTIFACT_VALIDATION_ERROR",
                failure_message="Artifact ref already exists in artifact index.",
                failure_detail={},
                idempotency_key=payload.idempotency_key,
            ),
        )
    except Exception:
        cleanup_materialized_artifacts(resolved_artifact_store, materialized_artifacts)
        if developer_inspector_store is not None:
            for artifact in persisted_inspector_artifacts:
                developer_inspector_store.delete_ref(artifact.ref)
        raise

    workflow_has_project_workspace = project_workspace_manifest_exists(payload.workflow_id)
    workspace_has_managed_paths = workflow_has_project_workspace and is_workspace_managed_write_set(
        list(created_spec.get("allowed_write_set") or [])
    )
    if (
        str(created_spec.get("deliverable_kind") or "") == "source_code_delivery"
        and workspace_has_managed_paths
    ):
        result_payload = payload.payload if isinstance(payload.payload, dict) else {}
        write_worker_postrun_receipt(
            workflow_id=payload.workflow_id,
            ticket_id=payload.ticket_id,
            documentation_updates=list(result_payload.get("documentation_updates") or []),
        )
        write_evidence_capture_receipt(
            workflow_id=payload.workflow_id,
            ticket_id=payload.ticket_id,
            verification_evidence_refs=list(payload.verification_evidence_refs),
        )
        if effective_git_commit_record is not None:
            write_git_closeout_receipt(
                workflow_id=payload.workflow_id,
                ticket_id=payload.ticket_id,
                git_commit_record=effective_git_commit_record.model_dump(mode="json") if effective_git_commit_record is not None else {},
            )
    elif workspace_has_managed_paths:
        materialize_workspace_delivery_files(
            workflow_id=payload.workflow_id,
            ticket_id=payload.ticket_id,
            project_checkout_path=get_settings().project_workspace_root / payload.workflow_id / "10-project",
            written_artifacts=[
                item.model_dump(mode="json") for item in effective_written_artifacts
            ],
        )
        if str(created_spec.get("deliverable_kind") or "") == "structured_document_delivery":
            write_artifact_capture_receipt(
                workflow_id=payload.workflow_id,
                ticket_id=payload.ticket_id,
                artifact_refs=[str(item).strip() for item in payload.artifact_refs if str(item).strip()],
                written_artifact_paths=[
                    str(item.path or "").strip()
                    for item in effective_written_artifacts
                    if str(item.path or "").strip()
                ],
            )
            if str(created_spec.get("output_schema_ref") or "").strip() == DELIVERY_CLOSEOUT_PACKAGE_SCHEMA_REF:
                result_payload = payload.payload if isinstance(payload.payload, dict) else {}
                write_documentation_sync_receipt(
                    workflow_id=payload.workflow_id,
                    ticket_id=payload.ticket_id,
                    documentation_updates=list(result_payload.get("documentation_updates") or []),
                )
    elif (
        workflow_has_project_workspace
        and str(created_spec.get("deliverable_kind") or "") == "review_evidence"
    ):
        write_artifact_capture_receipt(
            workflow_id=payload.workflow_id,
            ticket_id=payload.ticket_id,
            artifact_refs=[str(item).strip() for item in payload.artifact_refs if str(item).strip()],
            written_artifact_paths=[
                str(item.path or "").strip()
                for item in effective_written_artifacts
                if str(item.path or "").strip()
            ],
        )
    if workflow_has_project_workspace:
        sync_ticket_boardroom_views(
            repository,
            workflow_id=payload.workflow_id,
            ticket_id=payload.ticket_id,
        )
        sync_active_worktree_index(repository, workflow_id=payload.workflow_id)
    _refresh_ticket_context_archive(repository, payload.ticket_id)

    _trigger_ceo_shadow_safely(
        repository,
        workflow_id=payload.workflow_id,
        trigger_type=EVENT_TICKET_COMPLETED,
        trigger_ref=payload.ticket_id,
    )
    return CommandAckEnvelope(
        command_id=command_id,
        idempotency_key=payload.idempotency_key,
        status=CommandAckStatus.ACCEPTED,
        received_at=received_at,
        reason=None,
        causation_hint=causation_hint,
    )


def _complete_ticket_locked(
    *,
    repository: ControlPlaneRepository,
    connection,
    command_id: str,
    received_at: datetime,
    payload: TicketCompletedCommand,
    result_payload: dict[str, Any] | None,
    developer_inspector_store: DeveloperInspectorStore | None,
    persisted_artifacts: list[PersistedDeveloperInspectorArtifact],
) -> str:
    current_ticket = repository.get_current_ticket_projection(
        payload.ticket_id,
        connection=connection,
    )
    if current_ticket is None:
        raise RuntimeError("Ticket projection is missing for the currently executing node.")
    if (
        current_ticket["workflow_id"] != payload.workflow_id
        or current_ticket["node_id"] != payload.node_id
    ):
        raise RuntimeError("Ticket projection does not match the requested workflow or node.")
    if current_ticket["status"] != TICKET_STATUS_EXECUTING:
        raise RuntimeError(
            f"Ticket {payload.ticket_id} cannot be completed while status is {current_ticket['status']}."
        )
    current_ticket_spec = repository.get_latest_ticket_created_payload(connection, payload.ticket_id) or {}
    graph_identity = resolve_ticket_graph_identity(
        ticket_id=payload.ticket_id,
        created_spec=current_ticket_spec,
        runtime_node_id=payload.node_id,
    )
    if graph_identity.graph_lane_kind == GRAPH_LANE_EXECUTION:
        node_view = require_materialized_runtime_node(
            repository,
            payload.workflow_id,
            payload.node_id,
            operation="ticket-complete",
            connection=connection,
        )
        active_node_projection = repository.get_runtime_node_projection(
            payload.workflow_id,
            str(node_view.graph_node_id or graph_identity.graph_node_id or payload.node_id),
            connection=connection,
        )
        pointer_error = "Runtime node projection no longer points at this ticket."
    else:
        active_node_projection = repository.get_runtime_node_projection(
            payload.workflow_id,
            str(graph_identity.graph_node_id or payload.node_id),
            connection=connection,
        )
        pointer_error = "Runtime node projection no longer points at this ticket."
    if active_node_projection is None:
        raise RuntimeError("Runtime node projection is missing for the current graph lane.")
    if active_node_projection["status"] != NODE_STATUS_EXECUTING:
        raise RuntimeError(
            f"Node {payload.node_id} cannot accept a ticket result while status is {active_node_projection['status']}."
        )
    if active_node_projection["latest_ticket_id"] != payload.ticket_id:
        raise RuntimeError(pointer_error)

    created_spec = repository.get_latest_ticket_created_payload(connection, payload.ticket_id)
    effective_review_request = _resolve_original_review_request(payload, created_spec)
    route_to_maker_checker = _should_route_to_maker_checker(
        review_request=effective_review_request,
        created_spec=created_spec,
    )
    checker_ticket_kind = _ticket_kind(created_spec)
    checker_review_status = (
        str(result_payload.get("review_status") or "")
        if isinstance(result_payload, dict)
        else ""
    )
    workflow = repository.get_workflow_projection(payload.workflow_id, connection=connection)
    if (
        checker_ticket_kind == MAKER_CHECKER_REVIEW_TICKET_KIND
        and checker_review_status in {"CHANGES_REQUIRED", "ESCALATED"}
        and created_spec is not None
        and isinstance(result_payload, dict)
    ):
        blocking_findings = _extract_blocking_checker_findings(result_payload)
        rework_fingerprint = _build_rework_fingerprint(blocking_findings)
        rework_streak_count = _calculate_maker_checker_rework_streak(
            repository,
            connection,
            checker_created_spec=created_spec,
            rework_fingerprint=rework_fingerprint,
        )
        rework_cycle_count = _calculate_maker_checker_rework_cycle_count(
            repository,
            connection,
            checker_created_spec=created_spec,
        )
        if _should_autopilot_converge_maker_checker_rework(
            workflow=workflow,
            review_request=effective_review_request,
            created_spec=created_spec,
            rework_cycle_count=rework_cycle_count,
        ):
            result_payload = _build_autopilot_converged_checker_result_payload(result_payload)
            checker_review_status = str(result_payload.get("review_status") or "")
    checker_requires_no_board_gate = bool(
        checker_ticket_kind == MAKER_CHECKER_REVIEW_TICKET_KIND
        and (
            checker_review_status in {"CHANGES_REQUIRED", "ESCALATED"}
            or _is_internal_only_review_request(effective_review_request)
        )
    )
    open_board_review_now = bool(
        effective_review_request is not None
        and not route_to_maker_checker
        and not checker_requires_no_board_gate
    )

    event_row = repository.insert_event(
        connection,
        event_type=EVENT_TICKET_COMPLETED,
        actor_type="worker",
        actor_id=payload.completed_by,
        workflow_id=payload.workflow_id,
        idempotency_key=payload.idempotency_key,
        causation_id=command_id,
        correlation_id=payload.workflow_id,
        payload={
            "ticket_id": payload.ticket_id,
            "node_id": payload.node_id,
            "completion_summary": payload.completion_summary,
                "artifact_refs": payload.artifact_refs,
                "written_artifacts": [
                    item.model_dump(mode="json") for item in payload.written_artifacts
                ],
            "verification_evidence_refs": list(payload.verification_evidence_refs),
            "git_commit_record": (
                payload.git_commit_record.model_dump(mode="json")
                if payload.git_commit_record is not None
                else None
            ),
            "produced_process_assets": [
                item.model_dump(mode="json") for item in payload.produced_process_assets
            ],
            "documentation_updates": (
                list(result_payload.get("documentation_updates") or [])
                if isinstance(result_payload, dict)
                else []
            ),
            "review_status": (
                result_payload.get("review_status")
                if isinstance(result_payload, dict)
                and str((created_spec or {}).get("output_schema_ref") or "") == MAKER_CHECKER_VERDICT_SCHEMA_REF
                else None
            ),
            "board_review_requested": open_board_review_now,
        },
        occurred_at=received_at,
    )
    if event_row is None:
        raise RuntimeError("An identical ticket-complete command was already accepted.")

    causation_hint = f"ticket:{payload.ticket_id}"
    if route_to_maker_checker:
        if created_spec is None or effective_review_request is None:
            raise RuntimeError("Maker-checker routing requires ticket create spec and review request.")
        checker_ticket_payload = _build_maker_checker_ticket_payload(
            workflow_id=payload.workflow_id,
            node_id=payload.node_id,
            source_ticket_id=payload.ticket_id,
            created_spec=created_spec,
            review_request=effective_review_request,
            maker_completed_by=payload.completed_by,
            maker_artifact_refs=_dedupe_artifact_refs(list(payload.artifact_refs)),
            maker_process_asset_refs=[
                item.process_asset_ref for item in payload.produced_process_assets
            ],
        )
        next_ticket_id = _insert_followup_ticket_created_event(
            repository=repository,
            connection=connection,
            command_id=command_id,
            occurred_at=received_at,
            workflow_id=payload.workflow_id,
            ticket_payload=checker_ticket_payload,
            idempotency_key=f"{payload.idempotency_key}:maker-checker-create",
            actor_id="maker-checker-router",
        )
        causation_hint = f"ticket:{next_ticket_id}"
    elif (
        checker_ticket_kind == MAKER_CHECKER_REVIEW_TICKET_KIND
        and checker_review_status in {"CHANGES_REQUIRED", "ESCALATED"}
    ):
        if created_spec is None or not isinstance(result_payload, dict):
            raise RuntimeError("Checker rework routing requires created spec and checker verdict payload.")
        source_code_ticket_id = resolve_source_code_ticket_from_chain(
            repository,
            connection=connection,
            ticket_id=payload.ticket_id,
        )
        blocking_findings = _extract_blocking_checker_findings(result_payload)
        rework_fingerprint = _build_rework_fingerprint(blocking_findings)
        rework_streak_count = _calculate_maker_checker_rework_streak(
            repository,
            connection,
            checker_created_spec=created_spec,
            rework_fingerprint=rework_fingerprint,
        )
        if _should_escalate_maker_checker_rework(
            created_spec=created_spec,
            rework_streak_count=rework_streak_count,
        ) or checker_review_status == "ESCALATED":
            incident_id = _open_maker_checker_rework_incident(
                repository=repository,
                connection=connection,
                command_id=command_id,
                occurred_at=received_at,
                workflow_id=payload.workflow_id,
                ticket_id=payload.ticket_id,
                node_id=payload.node_id,
                rework_fingerprint=rework_fingerprint,
                rework_streak_count=rework_streak_count,
                blocking_findings=blocking_findings,
                idempotency_key_base=f"{payload.idempotency_key}:maker-checker-rework",
            )
            causation_hint = f"incident:{incident_id}"
        else:
            fix_ticket_payload = _build_fix_ticket_payload(
                workflow_id=payload.workflow_id,
                node_id=payload.node_id,
                checker_ticket_id=payload.ticket_id,
                checker_created_spec=created_spec,
                checker_result_payload={
                    **result_payload,
                    "artifact_refs": payload.artifact_refs,
                },
                blocking_findings=blocking_findings,
                rework_fingerprint=rework_fingerprint,
                rework_streak_count=rework_streak_count,
            )
            next_ticket_id = _insert_followup_ticket_created_event(
                repository=repository,
                connection=connection,
                command_id=command_id,
                occurred_at=received_at,
                workflow_id=payload.workflow_id,
                ticket_payload=fix_ticket_payload,
                idempotency_key=f"{payload.idempotency_key}:fix-ticket-create",
                actor_id="maker-checker-router",
            )
            causation_hint = f"ticket:{next_ticket_id}"
        if source_code_ticket_id is not None:
            source_created_spec = repository.get_latest_ticket_created_payload(connection, source_code_ticket_id) or {}
            if is_workspace_managed_source_code_ticket(source_created_spec):
                finalize_workspace_ticket_git_status(
                    workflow_id=payload.workflow_id,
                    ticket_id=source_code_ticket_id,
                    created_spec=source_created_spec,
                    merge_status="NOT_REQUESTED",
                )
    elif effective_review_request is not None:
        if _is_internal_only_review_request(effective_review_request):
            pass
        else:
            review_request_for_approval = effective_review_request
            developer_inspector_source_ticket_id = payload.ticket_id
            if checker_ticket_kind == MAKER_CHECKER_REVIEW_TICKET_KIND:
                if created_spec is None or not isinstance(result_payload, dict):
                    raise RuntimeError("Checker approval routing requires created spec and checker verdict payload.")
                review_request_for_approval = effective_review_request.model_copy(
                    update={
                        "maker_checker_summary": _build_generated_maker_checker_summary(
                            checker_payload=result_payload,
                            checker_completed_by=payload.completed_by,
                            checker_created_spec=created_spec,
                        )
                    }
                )
                maker_checker_context = created_spec.get("maker_checker_context") or {}
                developer_inspector_source_ticket_id = str(
                    maker_checker_context.get("maker_ticket_id") or payload.ticket_id
                )

            if (
                review_request_for_approval.developer_inspector_refs is not None
                and developer_inspector_store is None
            ):
                raise RuntimeError("Developer inspector store is required to export inspector artifacts.")
            if (
                developer_inspector_store is not None
                and review_request_for_approval.developer_inspector_refs is not None
            ):
                persisted_artifacts.extend(
                    export_latest_compile_artifacts_to_developer_inspector(
                        repository,
                        developer_inspector_store,
                        developer_inspector_source_ticket_id,
                        review_request_for_approval.developer_inspector_refs,
                        connection=connection,
                    )
                )
            approval = repository.create_approval_request(
                connection,
                workflow_id=payload.workflow_id,
                approval_type=review_request_for_approval.review_type.value,
                requested_by=payload.completed_by,
                review_pack=_build_review_pack(
                    payload=payload.model_copy(update={"review_request": review_request_for_approval}),
                    source_graph_node_id=resolve_ticket_graph_identity(
                        ticket_id=payload.ticket_id,
                        created_spec=created_spec or {"node_id": payload.node_id},
                        runtime_node_id=payload.node_id,
                    ).graph_node_id,
                    trigger_event_id=event_row["event_id"],
                    command_target_version=int(event_row["sequence_no"]),
                    occurred_at=received_at,
                ),
                available_actions=[action.value for action in review_request_for_approval.available_actions],
                draft_defaults={
                    "selected_option_id": review_request_for_approval.draft_selected_option_id,
                    "comment_template": review_request_for_approval.comment_template,
                },
                inbox_title=review_request_for_approval.inbox_title or review_request_for_approval.title,
                inbox_summary=review_request_for_approval.inbox_summary or payload.completion_summary,
                badges=review_request_for_approval.badges,
                priority=review_request_for_approval.priority.value,
                occurred_at=received_at,
                idempotency_key=f"{payload.idempotency_key}:approval-request",
            )
            meeting_context = None
            direct_meeting_context = created_spec.get("meeting_context") if isinstance(created_spec, dict) else None
            if isinstance(direct_meeting_context, dict):
                meeting_context = direct_meeting_context
            maker_checker_context = (
                created_spec.get("maker_checker_context") if isinstance(created_spec, dict) else None
            )
            if meeting_context is None and isinstance(maker_checker_context, dict):
                maker_ticket_spec = maker_checker_context.get("maker_ticket_spec")
                if isinstance(maker_ticket_spec, dict) and isinstance(maker_ticket_spec.get("meeting_context"), dict):
                    meeting_context = maker_ticket_spec.get("meeting_context")
            if isinstance(meeting_context, dict):
                meeting_id = str(meeting_context.get("meeting_id") or "").strip()
                if meeting_id and repository.get_meeting_projection(meeting_id, connection=connection) is not None:
                    repository.update_meeting_projection(
                        connection,
                        meeting_id,
                        review_pack_id=str(approval["review_pack_id"]),
                        review_status="BOARD_REVIEW_PENDING",
                        updated_at=received_at,
                    )
            causation_hint = f"approval:{approval['approval_id']}"

    _auto_close_recovering_incidents_for_completed_ticket(
        repository=repository,
        connection=connection,
        command_id=command_id,
        occurred_at=received_at,
        workflow_id=payload.workflow_id,
        completed_ticket_id=payload.ticket_id,
    )
    repository.refresh_projections(connection)
    return causation_hint


def handle_ticket_completed(
    repository: ControlPlaneRepository,
    payload: TicketCompletedCommand,
    developer_inspector_store: DeveloperInspectorStore | None = None,
) -> CommandAckEnvelope:
    command_id = new_prefixed_id("cmd")
    received_at = now_local()
    persisted_artifacts: list[PersistedDeveloperInspectorArtifact] = []

    try:
        with repository.transaction() as connection:
            existing_event = repository.get_event_by_idempotency_key(connection, payload.idempotency_key)
            if existing_event is not None:
                return _duplicate_ack(
                    command_id=command_id,
                    idempotency_key=payload.idempotency_key,
                    received_at=received_at,
                    ticket_id=payload.ticket_id,
                    action="ticket-complete",
                )
            try:
                causation_hint = _complete_ticket_locked(
                    repository=repository,
                    connection=connection,
                    command_id=command_id,
                    received_at=received_at,
                    payload=payload,
                    result_payload=None,
                    developer_inspector_store=developer_inspector_store,
                    persisted_artifacts=persisted_artifacts,
                )
            except RuntimeError as exc:
                return _rejected_ack(
                    command_id=command_id,
                    idempotency_key=payload.idempotency_key,
                    received_at=received_at,
                    ticket_id=payload.ticket_id,
                    reason=str(exc),
                )
    except Exception:
        if developer_inspector_store is not None:
            for artifact in persisted_artifacts:
                developer_inspector_store.delete_ref(artifact.ref)
        raise

    _trigger_ceo_shadow_safely(
        repository,
        workflow_id=payload.workflow_id,
        trigger_type=EVENT_TICKET_COMPLETED,
        trigger_ref=payload.ticket_id,
    )
    return CommandAckEnvelope(
        command_id=command_id,
        idempotency_key=payload.idempotency_key,
        status=CommandAckStatus.ACCEPTED,
        received_at=received_at,
        reason=None,
        causation_hint=causation_hint,
    )


def handle_scheduler_tick(
    repository: ControlPlaneRepository,
    payload: SchedulerTickCommand,
) -> CommandAckEnvelope:
    return run_scheduler_tick(
        repository,
        idempotency_key=payload.idempotency_key,
        max_dispatches=payload.max_dispatches,
        workers=payload.workers,
    )
