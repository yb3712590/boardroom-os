from __future__ import annotations

import json
from typing import Any, Mapping

from app.config import get_settings
from app.contracts.advisory import GovernancePatch, GraphPatchProposal, BoardAdvisoryDecision
from app.contracts.commands import (
    BoardAdvisoryAppendTurnCommand,
    BoardAdvisoryApplyPatchCommand,
    BoardApproveCommand,
    BoardRejectCommand,
    BoardAdvisoryRequestAnalysisCommand,
    CommandAckEnvelope,
    ElicitationQuestion,
    CommandAckStatus,
    DispatchIntent,
    DeliveryStage,
    ElicitationAnswer,
    ModifyConstraintsCommand,
    TicketCreateCommand,
)
from app.contracts.ceo_actions import CEOCreateTicketPayload
from app.core.ceo_execution_presets import (
    build_project_init_scope_ticket_id,
    build_ceo_create_ticket_command,
)
from app.core.ceo_scheduler import trigger_ceo_shadow_with_recovery
from app.core.constants import (
    APPROVAL_STATUS_APPROVED,
    APPROVAL_STATUS_MODIFIED_CONSTRAINTS,
    APPROVAL_STATUS_OPEN,
    APPROVAL_STATUS_REJECTED,
    EMPLOYEE_STATE_ACTIVE,
    EVENT_BOARD_DIRECTIVE_RECEIVED,
    EVENT_BOARD_ADVISORY_ANALYSIS_REQUESTED,
    EVENT_BOARD_ADVISORY_CHANGE_FLOW_ENTERED,
    EVENT_BOARD_ADVISORY_DECISION_RECORDED,
    EVENT_BOARD_ADVISORY_SESSION_DISMISSED,
    EVENT_BOARD_ADVISORY_TURN_APPENDED,
    EVENT_BOARD_REVIEW_APPROVED,
    EVENT_BOARD_REVIEW_REJECTED,
    EVENT_EMPLOYEE_HIRED,
    EVENT_EMPLOYEE_REPLACED,
    EVENT_GRAPH_PATCH_APPLIED,
    EVENT_INCIDENT_OPENED,
    EVENT_TICKET_CREATED,
    INCIDENT_STATUS_OPEN,
    INCIDENT_TYPE_REVIEW_GATE_MERGE_FAILED,
    NODE_STATUS_BLOCKED_FOR_BOARD_REVIEW,
    TICKET_STATUS_BLOCKED_FOR_BOARD_REVIEW,
)
from app.core.board_advisory import (
    advisory_decision_artifact_ref,
    advisory_decision_logical_path,
    advisory_decision_process_asset_ref,
    advisory_graph_patch_artifact_ref,
    advisory_graph_patch_logical_path,
    advisory_graph_patch_process_asset_ref,
    advisory_patch_proposal_artifact_ref,
    advisory_patch_proposal_logical_path,
    advisory_patch_proposal_process_asset_ref,
    advisory_timeline_index_artifact_ref,
    advisory_timeline_index_logical_path,
    advisory_timeline_index_process_asset_ref,
    advisory_transcript_archive_artifact_ref,
    advisory_transcript_archive_logical_path,
    advisory_change_flow_can_append_turn,
    advisory_change_flow_can_apply,
    advisory_change_flow_can_request_analysis,
    board_advisory_requires_full_timeline_archive,
    advisory_supports_governance_patch,
    build_board_advisory_turn,
    build_board_advisory_context,
    build_board_advisory_decision,
    build_board_advisory_decision_artifact_payload,
    build_board_advisory_timeline_index_payload,
    build_board_advisory_transcript_payload,
    build_graph_patch_from_proposal,
    build_graph_patch_proposal,
    build_governance_profile_from_patch,
    review_pack_requires_board_advisory,
)
from app.core.board_advisory_analysis import (
    create_board_advisory_analysis_run,
    run_board_advisory_analysis,
)
from app.core.execution_targets import infer_execution_contract_payload
from app.core.graph_patch_reducer import (
    GraphPatchEventRecord,
    GraphPatchReducerUnavailableError,
    reduce_graph_patch_overlay,
)
from app.core.ids import new_prefixed_id
from app.core.output_schemas import (
    DELIVERY_CLOSEOUT_PACKAGE_SCHEMA_REF,
    DELIVERY_CLOSEOUT_PACKAGE_SCHEMA_VERSION,
    DELIVERY_CHECK_REPORT_SCHEMA_REF,
    DELIVERY_CHECK_REPORT_SCHEMA_VERSION,
    SOURCE_CODE_DELIVERY_SCHEMA_REF,
    SOURCE_CODE_DELIVERY_SCHEMA_VERSION,
    UI_MILESTONE_REVIEW_SCHEMA_REF,
)
from app.core.persona_profiles import normalize_persona_profiles
from app.core.project_workspaces import (
    finalize_workspace_ticket_git_status,
    is_workspace_managed_source_code_ticket,
    merge_ticket_branch_into_main,
    resolve_source_code_ticket_from_chain,
    resolve_ticket_checkout_truth,
    sync_active_worktree_index,
    sync_ticket_boardroom_views,
)
from app.core.review_subjects import (
    resolve_graph_only_review_subject_execution_identity,
    resolve_review_subject_execution_identity,
    resolve_review_subject_identity,
)
from app.core.process_assets import (
    build_decision_summary_process_asset_ref,
    build_graph_patch_process_asset_ref,
    build_graph_patch_proposal_process_asset_ref,
    build_source_code_delivery_process_asset_ref,
    get_ticket_output_process_asset_refs,
    merge_input_process_asset_refs,
)
from app.core.requirement_elicitation import (
    build_enriched_board_brief_markdown,
    build_requirement_elicitation_markdown,
    build_requirement_elicitation_questionnaire,
    build_requirement_elicitation_review_payload,
    normalize_elicitation_answers,
    summarize_elicitation_answers,
)
from app.core.staffing_containment import contain_employee_active_tickets
from app.core.ticket_graph import build_ticket_graph_snapshot
from app.core.ticket_handlers import handle_ticket_create
from app.core.time import now_local
from app.core.workflow_auto_advance import auto_advance_workflow_to_next_stop
from app.core.workflow_autopilot import (
    build_ceo_delegate_board_approval_command,
)
from app.core.workflow_progression import build_project_init_kickoff_spec
from app.db.repository import ControlPlaneRepository
from app.core.versioning import resolve_workflow_graph_version

SCOPE_APPROVAL_AUTO_ADVANCE_MAX_STEPS = 6
PROJECT_INIT_AUTO_ADVANCE_MAX_STEPS = 6


def _trigger_ceo_shadow_safely(
    repository: ControlPlaneRepository,
    *,
    workflow_id: str,
    approval_id: str,
) -> None:
    trigger_ceo_shadow_with_recovery(
        repository,
        workflow_id=workflow_id,
        trigger_type="APPROVAL_RESOLVED",
        trigger_ref=approval_id,
        idempotency_key_base=f"approval-trigger:{workflow_id}:{approval_id}",
    )


def _rejected_ack(
    *,
    command_id: str,
    idempotency_key: str,
    received_at,
    reason: str,
    causation_hint: str | None = None,
) -> CommandAckEnvelope:
    return CommandAckEnvelope(
        command_id=command_id,
        idempotency_key=idempotency_key,
        status=CommandAckStatus.REJECTED,
        received_at=received_at,
        reason=reason,
        causation_hint=causation_hint,
    )


def _duplicate_ack(
    *,
    command_id: str,
    idempotency_key: str,
    received_at,
    approval_id: str,
) -> CommandAckEnvelope:
    return CommandAckEnvelope(
        command_id=command_id,
        idempotency_key=idempotency_key,
        status=CommandAckStatus.DUPLICATE,
        received_at=received_at,
        reason="An identical board command was already accepted.",
        causation_hint=f"approval:{approval_id}",
    )


def _validate_approval_version_guard(
    approval: dict[str, Any] | None,
    *,
    approval_id: str,
    review_pack_id: str,
    review_pack_version: int,
    command_target_version: int,
) -> str | None:
    if approval is None:
        return "Approval target not found."
    if approval["approval_id"] != approval_id or approval["review_pack_id"] != review_pack_id:
        return "Approval target does not match review pack."
    if approval["review_pack_version"] != review_pack_version:
        return "Review pack outdated. Reload review-room projection."
    if approval["command_target_version"] != command_target_version:
        return "Projection target outdated. Reload review-room projection."
    return None


def _validate_open_approval(
    approval: dict[str, Any] | None,
    *,
    approval_id: str,
    review_pack_id: str,
    review_pack_version: int,
    command_target_version: int,
) -> str | None:
    version_guard_reason = _validate_approval_version_guard(
        approval,
        approval_id=approval_id,
        review_pack_id=review_pack_id,
        review_pack_version=review_pack_version,
        command_target_version=command_target_version,
    )
    if version_guard_reason is not None:
        return version_guard_reason
    if approval is not None and approval["status"] != APPROVAL_STATUS_OPEN:
        return f"Approval is already resolved with status {approval['status']}."
    return None


def _validate_blocked_projection(
    repository: ControlPlaneRepository,
    approval: dict[str, Any],
) -> str | None:
    subject = approval["payload"].get("review_pack", {}).get("subject", {})
    workflow_id = approval["workflow_id"]
    ticket_id, graph_node_id, node_id = resolve_review_subject_identity(
        repository,
        workflow_id=workflow_id,
        subject=subject,
    )
    if not ticket_id:
        return None
    ticket_projection = repository.get_current_ticket_projection(ticket_id)
    if ticket_projection is None:
        return "Ticket or runtime node projection for this approval is missing. Reload dashboard state."
    runtime_node_projection = repository.get_runtime_node_projection(workflow_id, graph_node_id)
    if runtime_node_projection is None:
        return "Ticket or runtime node projection for this approval is missing. Reload review-room projection."
    if ticket_projection["status"] != TICKET_STATUS_BLOCKED_FOR_BOARD_REVIEW:
        return "Ticket is not currently blocked for board review."
    if runtime_node_projection["status"] != NODE_STATUS_BLOCKED_FOR_BOARD_REVIEW:
        return "Node is not currently blocked for board review."
    if ticket_projection["workflow_id"] != workflow_id or ticket_projection["node_id"] != str(
        runtime_node_projection.get("node_id") or node_id
    ):
        return "Ticket projection does not match the approval target."
    if runtime_node_projection["latest_ticket_id"] != ticket_id:
        return "Runtime node projection no longer points at this approval ticket."
    return None


def _apply_employee_change_approval(
    repository: ControlPlaneRepository,
    connection,
    *,
    approval: dict[str, Any],
    command_id: str,
    occurred_at,
    idempotency_key: str,
) -> str | None:
    if approval["approval_type"] != "CORE_HIRE_APPROVAL":
        return None

    review_pack = approval["payload"].get("review_pack") or {}
    employee_change = review_pack.get("employee_change") or {}
    change_kind = str(employee_change.get("change_kind") or "")

    if change_kind == "EMPLOYEE_HIRE":
        normalized_profiles = normalize_persona_profiles(
            str(employee_change.get("role_type") or ""),
            skill_profile=employee_change.get("skill_profile"),
            personality_profile=employee_change.get("personality_profile"),
            aesthetic_profile=employee_change.get("aesthetic_profile"),
        )
        repository.insert_event(
            connection,
            event_type=EVENT_EMPLOYEE_HIRED,
            actor_type="board",
            actor_id="board",
            workflow_id=approval["workflow_id"],
            idempotency_key=f"{idempotency_key}:employee-hired",
            causation_id=command_id,
            correlation_id=approval["workflow_id"],
            payload={
                "employee_id": employee_change["employee_id"],
                "role_type": employee_change["role_type"],
                "skill_profile": normalized_profiles["skill_profile"],
                "personality_profile": normalized_profiles["personality_profile"],
                "aesthetic_profile": normalized_profiles["aesthetic_profile"],
                "state": EMPLOYEE_STATE_ACTIVE,
                "board_approved": True,
                "provider_id": employee_change.get("provider_id"),
                "role_profile_refs": list(employee_change.get("role_profile_refs") or []),
            },
            occurred_at=occurred_at,
        )
        return str(employee_change["employee_id"])

    if change_kind == "EMPLOYEE_REPLACE":
        replaced_employee_id = str(employee_change["employee_id"])
        replacement_employee_id = str(employee_change["replacement_employee_id"])
        normalized_profiles = normalize_persona_profiles(
            str(employee_change.get("replacement_role_type") or ""),
            skill_profile=employee_change.get("replacement_skill_profile"),
            personality_profile=employee_change.get("replacement_personality_profile"),
            aesthetic_profile=employee_change.get("replacement_aesthetic_profile"),
        )
        repository.insert_event(
            connection,
            event_type=EVENT_EMPLOYEE_HIRED,
            actor_type="board",
            actor_id="board",
            workflow_id=approval["workflow_id"],
            idempotency_key=f"{idempotency_key}:employee-replacement-hired",
            causation_id=command_id,
            correlation_id=approval["workflow_id"],
            payload={
                "employee_id": replacement_employee_id,
                "role_type": employee_change["replacement_role_type"],
                "skill_profile": normalized_profiles["skill_profile"],
                "personality_profile": normalized_profiles["personality_profile"],
                "aesthetic_profile": normalized_profiles["aesthetic_profile"],
                "state": EMPLOYEE_STATE_ACTIVE,
                "board_approved": True,
                "provider_id": employee_change.get("replacement_provider_id"),
                "role_profile_refs": list(employee_change.get("replacement_role_profile_refs") or []),
            },
            occurred_at=occurred_at,
        )
        repository.insert_event(
            connection,
            event_type=EVENT_EMPLOYEE_REPLACED,
            actor_type="board",
            actor_id="board",
            workflow_id=approval["workflow_id"],
            idempotency_key=f"{idempotency_key}:employee-replaced",
            causation_id=command_id,
            correlation_id=approval["workflow_id"],
            payload={
                "employee_id": replaced_employee_id,
                "replacement_employee_id": replacement_employee_id,
            },
            occurred_at=occurred_at,
        )
        contain_employee_active_tickets(
            repository,
            connection,
            employee_id=replaced_employee_id,
            action_kind=EVENT_EMPLOYEE_REPLACED,
            reason="Board-approved employee replacement removed the original assignee from active duty.",
            occurred_at=occurred_at,
            command_id=command_id,
            idempotency_key_base=idempotency_key,
            replacement_employee_id=replacement_employee_id,
        )
        return replacement_employee_id

    return None
def _dedupe_artifact_refs(values: list[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped
def _build_closeout_internal_review_request(summary: str) -> dict[str, Any]:
    clean_summary = summary.strip() or "Delivery closeout package is ready for final internal review."
    return {
        "review_type": "INTERNAL_CLOSEOUT_REVIEW",
        "priority": "high",
        "title": "Check delivery closeout package",
        "subtitle": "Internal checker should validate final evidence, handoff notes, and documentation sync before the workflow closes.",
        "blocking_scope": "NODE_ONLY",
        "trigger_reason": "Final board-approved delivery package reached the closeout checker gate.",
        "why_now": "Workflow completion should only happen after the final handoff package, evidence links, and documentation sync notes are internally checked.",
        "recommended_action": "APPROVE",
        "recommended_option_id": "internal_closeout_ok",
        "recommendation_summary": clean_summary,
        "options": [
            {
                "option_id": "internal_closeout_ok",
                "label": "Pass closeout package",
                "summary": clean_summary,
                "artifact_refs": [],
                "pros": ["Lets the workflow close on a checked final delivery package."],
                "cons": ["Leaves only non-blocking polish outside the current MVP closeout path."],
                "risks": [
                    "FOLLOW_UP_REQUIRED documentation notes should stay non-blocking only when handoff and evidence are still complete."
                ],
            }
        ],
        "evidence_summary": [
            {
                "evidence_id": "ev_delivery_closeout_package",
                "source_type": "DELIVERY_CLOSEOUT_PACKAGE",
                "headline": "Delivery closeout package is ready for internal review",
                "summary": clean_summary,
                "source_ref": None,
            }
        ],
        "available_actions": ["APPROVE", "REJECT", "MODIFY_CONSTRAINTS"],
        "draft_selected_option_id": "internal_closeout_ok",
        "comment_template": "",
        "badges": ["internal_closeout", "closeout_gate"],
    }


def _load_project_init_directive_payload(
    repository: ControlPlaneRepository,
    connection,
    *,
    workflow_id: str,
) -> dict[str, Any]:
    for event in reversed(repository.list_all_events(connection)):
        if event["workflow_id"] != workflow_id:
            continue
        if event["event_type"] != EVENT_BOARD_DIRECTIVE_RECEIVED:
            continue
        payload = event.get("payload") or {}
        if isinstance(payload, dict):
            return payload
    raise ValueError("Project-init directive payload is missing.")


def _save_text_artifact(
    repository: ControlPlaneRepository,
    connection,
    *,
    artifact_ref: str,
    logical_path: str,
    workflow_id: str,
    ticket_id: str,
    node_id: str,
    content: str,
    kind: str,
    occurred_at,
) -> None:
    artifact_store = repository.artifact_store
    if artifact_store is None:
        raise ValueError("Artifact store is required to record requirement elicitation artifacts.")
    materialized = artifact_store.materialize_text(
        logical_path,
        content,
        workflow_id=workflow_id,
        ticket_id=ticket_id,
        artifact_ref=artifact_ref,
        media_type="text/markdown",
    )
    repository.save_artifact_record(
        connection,
        artifact_ref=artifact_ref,
        workflow_id=workflow_id,
        ticket_id=ticket_id,
        node_id=node_id,
        logical_path=logical_path,
        kind=kind,
        media_type="text/markdown",
        materialization_status="MATERIALIZED",
        lifecycle_status="ACTIVE",
        storage_backend=materialized.storage_backend,
        storage_relpath=materialized.storage_relpath,
        storage_object_key=materialized.storage_object_key,
        storage_delete_status=materialized.storage_delete_status,
        storage_delete_error=None,
        content_hash=materialized.content_hash,
        size_bytes=materialized.size_bytes,
        retention_class="PERSISTENT",
        retention_class_source="explicit",
        retention_ttl_sec=None,
        retention_policy_source="explicit_class",
        expires_at=None,
        deleted_at=None,
        deleted_by=None,
        delete_reason=None,
        created_at=occurred_at,
    )


def _save_json_artifact(
    repository: ControlPlaneRepository,
    connection,
    *,
    artifact_ref: str,
    logical_path: str,
    workflow_id: str,
    ticket_id: str,
    node_id: str,
    payload: dict[str, Any],
    kind: str,
    occurred_at,
) -> None:
    artifact_store = repository.artifact_store
    if artifact_store is None:
        raise ValueError("Artifact store is required to record board advisory artifacts.")
    materialized = artifact_store.materialize_json(
        logical_path,
        payload,
        workflow_id=workflow_id,
        ticket_id=ticket_id,
        artifact_ref=artifact_ref,
    )
    repository.save_artifact_record(
        connection,
        artifact_ref=artifact_ref,
        workflow_id=workflow_id,
        ticket_id=ticket_id,
        node_id=node_id,
        logical_path=logical_path,
        kind=kind,
        media_type="application/json",
        materialization_status="MATERIALIZED",
        lifecycle_status="ACTIVE",
        storage_backend=materialized.storage_backend,
        storage_relpath=materialized.storage_relpath,
        storage_object_key=materialized.storage_object_key,
        storage_delete_status=materialized.storage_delete_status,
        storage_delete_error=None,
        content_hash=materialized.content_hash,
        size_bytes=materialized.size_bytes,
        retention_class="PERSISTENT",
        retention_class_source="explicit",
        retention_ttl_sec=None,
        retention_policy_source="explicit_class",
        expires_at=None,
        deleted_at=None,
        deleted_by=None,
        delete_reason=None,
        created_at=occurred_at,
    )


def _require_board_advisory_session(
    repository: ControlPlaneRepository,
    connection,
    *,
    approval: dict[str, Any],
) -> dict[str, Any] | None:
    review_pack = ((approval.get("payload") or {}).get("review_pack") or {})
    if not review_pack_requires_board_advisory(review_pack):
        return None
    session = repository.get_board_advisory_session_for_approval(
        str(approval["approval_id"]),
        connection=connection,
    )
    if session is None:
        raise ValueError("Board advisory session is required before resolving this review pack.")
    return session


def _board_advisory_artifact_subject(
    repository: ControlPlaneRepository,
    connection,
    *,
    session: dict[str, Any],
) -> tuple[str, str, str]:
    approval = repository.get_approval_by_id(connection, str(session["approval_id"])) or {}
    review_pack = ((approval.get("payload") or {}).get("review_pack") or {}) if isinstance(approval, dict) else {}
    subject = review_pack.get("subject") or {}
    source_ticket_id, source_graph_node_id, source_node_id = resolve_graph_only_review_subject_execution_identity(
        repository,
        workflow_id=str(session.get("workflow_id") or ""),
        subject=subject,
        connection=connection,
    )
    normalized_ticket_id = source_ticket_id or (
        str(subject.get("source_ticket_id") or session["approval_id"]).strip() or str(session["approval_id"])
    )
    return normalized_ticket_id, str(source_graph_node_id), str(source_node_id)


def _resolve_review_pack_execution_subject(
    repository: ControlPlaneRepository,
    connection,
    *,
    workflow_id: str,
    subject: Mapping[str, Any] | None,
    fallback_ticket_id: str | None = None,
) -> tuple[str | None, str, str]:
    source_ticket_id, source_graph_node_id, source_node_id = resolve_graph_only_review_subject_execution_identity(
        repository,
        workflow_id=workflow_id,
        subject=subject,
        connection=connection,
    )
    normalized_ticket_id = str(source_ticket_id or fallback_ticket_id or "").strip() or None
    return normalized_ticket_id, str(source_graph_node_id), str(source_node_id)


def _materialize_board_advisory_full_timeline_archive(
    repository: ControlPlaneRepository,
    connection,
    *,
    session: dict[str, Any],
    current_profile: dict[str, Any],
    occurred_at,
    latest_analysis_archive_artifact_ref: str | None = None,
) -> dict[str, Any]:
    if not board_advisory_requires_full_timeline_archive(
        session,
        current_profile=current_profile,
    ):
        return session
    session_id = str(session.get("session_id") or "").strip()
    workflow_id = str(session.get("workflow_id") or "").strip()
    approval_id = str(session.get("approval_id") or "").strip()
    review_pack_id = str(session.get("review_pack_id") or "").strip()
    if not session_id or not workflow_id or not approval_id or not review_pack_id:
        raise ValueError("Board advisory session is missing required identifiers for FULL_TIMELINE archive materialization.")

    timeline_archive_version_int = int(session.get("timeline_archive_version_int") or 0) + 1
    transcript_artifact_ref = advisory_transcript_archive_artifact_ref(
        workflow_id=workflow_id,
        session_id=session_id,
        version_int=timeline_archive_version_int,
    )
    timeline_index_ref = advisory_timeline_index_process_asset_ref(
        session_id,
        version_int=timeline_archive_version_int,
    )
    timeline_index_artifact_ref = advisory_timeline_index_artifact_ref(
        workflow_id=workflow_id,
        session_id=session_id,
        version_int=timeline_archive_version_int,
    )
    source_ticket_id, _source_graph_node_id, source_node_id = _board_advisory_artifact_subject(
        repository,
        connection,
        session=session,
    )
    transcript_payload = build_board_advisory_transcript_payload(
        session=session,
        current_profile=current_profile,
    )
    _save_json_artifact(
        repository,
        connection,
        artifact_ref=transcript_artifact_ref,
        logical_path=advisory_transcript_archive_logical_path(
            session_id=session_id,
            version_int=timeline_archive_version_int,
        ),
        workflow_id=workflow_id,
        ticket_id=source_ticket_id,
        node_id=source_node_id,
        payload=transcript_payload,
        kind="JSON",
        occurred_at=occurred_at,
    )
    _save_json_artifact(
        repository,
        connection,
        artifact_ref=timeline_index_artifact_ref,
        logical_path=advisory_timeline_index_logical_path(
            session_id=session_id,
            version_int=timeline_archive_version_int,
        ),
        workflow_id=workflow_id,
        ticket_id=source_ticket_id,
        node_id=source_node_id,
        payload=build_board_advisory_timeline_index_payload(
            session=session,
            current_profile=current_profile,
            timeline_archive_version_int=timeline_archive_version_int,
            transcript_archive_artifact_ref=transcript_artifact_ref,
            latest_analysis_archive_artifact_ref=latest_analysis_archive_artifact_ref,
        ),
        kind="JSON",
        occurred_at=occurred_at,
    )
    return repository.update_board_advisory_timeline_archive(
        connection,
        session_id=session_id,
        latest_timeline_index_ref=timeline_index_ref,
        latest_transcript_archive_artifact_ref=transcript_artifact_ref,
        timeline_archive_version_int=timeline_archive_version_int,
        updated_at=occurred_at,
    )


def _materialize_board_advisory_full_timeline_archive_checked(
    repository: ControlPlaneRepository,
    connection,
    *,
    session: dict[str, Any],
    current_profile: dict[str, Any],
    occurred_at,
    latest_analysis_archive_artifact_ref: str | None = None,
) -> dict[str, Any]:
    try:
        return _materialize_board_advisory_full_timeline_archive(
            repository,
            connection,
            session=session,
            current_profile=current_profile,
            occurred_at=occurred_at,
            latest_analysis_archive_artifact_ref=latest_analysis_archive_artifact_ref,
        )
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError(f"Board advisory FULL_TIMELINE archive materialization failed: {exc}") from exc


def _dismiss_board_advisory_session_if_needed(
    repository: ControlPlaneRepository,
    connection,
    *,
    approval: dict[str, Any],
    command_id: str,
    occurred_at,
    idempotency_key: str,
) -> None:
    session = _require_board_advisory_session(repository, connection, approval=approval)
    if session is None:
        return
    updated_session = repository.dismiss_board_advisory_session(
        connection,
        session_id=str(session["session_id"]),
        updated_at=occurred_at,
    )
    current_profile = repository.get_latest_governance_profile(str(approval["workflow_id"]), connection=connection)
    if current_profile is None:
        raise ValueError("Governance profile is required before dismissing the board advisory session.")
    updated_session = _materialize_board_advisory_full_timeline_archive_checked(
        repository,
        connection,
        session=updated_session,
        current_profile=current_profile,
        occurred_at=occurred_at,
    )
    advisory_event = repository.insert_event(
        connection,
        event_type=EVENT_BOARD_ADVISORY_SESSION_DISMISSED,
        actor_type="board",
        actor_id="board",
        workflow_id=approval["workflow_id"],
        idempotency_key=idempotency_key,
        causation_id=command_id,
        correlation_id=approval["workflow_id"],
        payload={
            "session_id": session["session_id"],
            "approval_id": approval["approval_id"],
            "review_pack_id": approval["review_pack_id"],
            "trigger_type": session["trigger_type"],
            "status": updated_session["status"],
        },
        occurred_at=occurred_at,
    )
    if advisory_event is None:
        raise RuntimeError("Board advisory dismissal idempotency conflict.")


def _resolve_governance_patch_or_reject(
    payload: ModifyConstraintsCommand,
) -> tuple[GovernancePatch | None, str | None]:
    raw_patch = payload.governance_patch
    if raw_patch is None:
        return None, None
    try:
        return GovernancePatch.model_validate(raw_patch), None
    except Exception as exc:
        return None, str(exc)


def _record_board_advisory_decision(
    repository: ControlPlaneRepository,
    connection,
    *,
    approval: dict[str, Any],
    governance_patch: GovernancePatch | None,
    constraint_patch: dict[str, list[str]],
    board_comment: str,
    command_id: str,
    occurred_at,
    idempotency_key: str,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    session = _require_board_advisory_session(repository, connection, approval=approval)
    if session is None:
        raise ValueError("Board advisory decision is only valid for advisory-backed review packs.")
    workflow_id = str(approval["workflow_id"])
    review_pack = ((approval.get("payload") or {}).get("review_pack") or {})
    subject = review_pack.get("subject") or {}
    source_ticket_id, _source_graph_node_id, source_node_id = _board_advisory_artifact_subject(
        repository,
        connection,
        session=session,
    )
    current_profile = repository.get_latest_governance_profile(workflow_id, connection=connection)
    if current_profile is None:
        raise ValueError("Governance profile is required before recording a board advisory decision.")
    next_profile = (
        build_governance_profile_from_patch(
            current_profile,
            governance_patch,
            source_ref=advisory_decision_process_asset_ref(str(session["session_id"])),
            effective_from_event="pending-board-advisory-decision",
        )
        if governance_patch is not None
        else None
    )
    artifact_ref = advisory_decision_artifact_ref(
        workflow_id=workflow_id,
        session_id=str(session["session_id"]),
    )
    board_decision = build_board_advisory_decision(
        board_comment=board_comment,
        constraint_patch=constraint_patch,
        governance_patch=governance_patch,
        source_artifact_ref=artifact_ref,
    )
    decision_payload = build_board_advisory_decision_artifact_payload(
        session=session,
        board_decision=board_decision,
        current_profile=current_profile,
        next_profile=next_profile,
    )
    _save_json_artifact(
        repository,
        connection,
        artifact_ref=artifact_ref,
        logical_path=advisory_decision_logical_path(session_id=str(session["session_id"])),
        workflow_id=workflow_id,
        ticket_id=source_ticket_id,
        node_id=source_node_id,
        payload=decision_payload,
        kind="JSON",
        occurred_at=occurred_at,
    )
    decision_process_asset_ref = build_decision_summary_process_asset_ref(str(session["session_id"]), version_int=1)
    advisory_event = repository.insert_event(
        connection,
        event_type=EVENT_BOARD_ADVISORY_DECISION_RECORDED,
        actor_type="board",
        actor_id="board",
        workflow_id=workflow_id,
        idempotency_key=idempotency_key,
        causation_id=command_id,
        correlation_id=workflow_id,
        payload={
            "session_id": session["session_id"],
            "approval_id": approval["approval_id"],
            "review_pack_id": approval["review_pack_id"],
            "decision_action": "MODIFY_CONSTRAINTS",
            "decision_pack_refs": [decision_process_asset_ref],
            "approved_patch_ref": decision_process_asset_ref,
            "board_comment": board_comment,
            "constraint_patch": constraint_patch,
            "governance_patch": (
                governance_patch.model_dump(mode="json", exclude_none=True)
                if governance_patch is not None
                else None
            ),
        },
        occurred_at=occurred_at,
    )
    if advisory_event is None:
        raise RuntimeError("Board advisory decision idempotency conflict.")
    updated_session = repository.decide_board_advisory_session(
        connection,
        session_id=str(session["session_id"]),
        board_decision=board_decision.model_dump(mode="json", exclude_none=True),
        decision_pack_refs=[decision_process_asset_ref],
        approved_patch_ref=decision_process_asset_ref,
        updated_at=occurred_at,
    )
    if next_profile is not None:
        next_profile = next_profile.model_copy(
            update={
                "source_ref": decision_process_asset_ref,
                "effective_from_event": str(advisory_event["event_id"]),
            }
        )
        repository.save_governance_profile(connection, next_profile)
        return updated_session, next_profile.model_dump(mode="json")
    return updated_session, None


def _enter_board_advisory_change_flow(
    repository: ControlPlaneRepository,
    connection,
    *,
    approval: dict[str, Any],
    governance_patch: GovernancePatch | None,
    constraint_patch: dict[str, list[str]],
    board_comment: str,
    command_id: str,
    occurred_at,
    idempotency_key: str,
) -> dict[str, Any]:
    session = _require_board_advisory_session(repository, connection, approval=approval)
    if session is None:
        raise ValueError("Board advisory change flow is only valid for advisory-backed review packs.")
    workflow_id = str(approval["workflow_id"])
    source_ticket_id, _source_graph_node_id, source_node_id = _board_advisory_artifact_subject(
        repository,
        connection,
        session=session,
    )
    current_profile = repository.get_latest_governance_profile(workflow_id, connection=connection)
    if current_profile is None:
        raise ValueError("Governance profile is required before entering the advisory change flow.")
    artifact_ref = advisory_decision_artifact_ref(
        workflow_id=workflow_id,
        session_id=str(session["session_id"]),
    )
    board_decision = build_board_advisory_decision(
        board_comment=board_comment,
        constraint_patch=constraint_patch,
        governance_patch=governance_patch,
        source_artifact_ref=artifact_ref,
    )
    decision_payload = build_board_advisory_decision_artifact_payload(
        session=session,
        board_decision=board_decision,
        current_profile=current_profile,
        next_profile=None,
    )
    _save_json_artifact(
        repository,
        connection,
        artifact_ref=artifact_ref,
        logical_path=advisory_decision_logical_path(session_id=str(session["session_id"])),
        workflow_id=workflow_id,
        ticket_id=source_ticket_id,
        node_id=source_node_id,
        payload=decision_payload,
        kind="JSON",
        occurred_at=occurred_at,
    )
    decision_process_asset_ref = build_decision_summary_process_asset_ref(str(session["session_id"]), version_int=1)
    working_turn = build_board_advisory_turn(
        actor_type="board",
        content=board_comment,
        created_at=occurred_at,
    ).model_dump(mode="json")
    updated_session = repository.start_board_advisory_change_flow(
        connection,
        session_id=str(session["session_id"]),
        board_decision=board_decision.model_dump(mode="json", exclude_none=True),
        decision_pack_refs=[decision_process_asset_ref],
        working_turn=working_turn,
        updated_at=occurred_at,
    )
    updated_session = _materialize_board_advisory_full_timeline_archive_checked(
        repository,
        connection,
        session=updated_session,
        current_profile=current_profile,
        occurred_at=occurred_at,
    )
    advisory_event = repository.insert_event(
        connection,
        event_type=EVENT_BOARD_ADVISORY_CHANGE_FLOW_ENTERED,
        actor_type="board",
        actor_id="board",
        workflow_id=workflow_id,
        idempotency_key=idempotency_key,
        causation_id=command_id,
        correlation_id=workflow_id,
        payload={
            "session_id": session["session_id"],
            "approval_id": approval["approval_id"],
            "review_pack_id": approval["review_pack_id"],
            "decision_action": "MODIFY_CONSTRAINTS",
            "decision_pack_refs": [decision_process_asset_ref],
            "board_comment": board_comment,
            "constraint_patch": constraint_patch,
            "governance_patch": (
                governance_patch.model_dump(mode="json", exclude_none=True)
                if governance_patch is not None
                else None
            ),
            "working_turn": working_turn,
            "status": "DRAFTING",
        },
        occurred_at=occurred_at,
    )
    if advisory_event is None:
        raise RuntimeError("Board advisory change-flow entry idempotency conflict.")
    return updated_session


def _append_board_advisory_turn(
    repository: ControlPlaneRepository,
    connection,
    *,
    session_id: str,
    actor_type: str,
    content: str,
    command_id: str,
    occurred_at,
    idempotency_key: str,
) -> dict[str, Any]:
    session = repository.get_board_advisory_session(session_id, connection=connection)
    if session is None:
        raise ValueError("Board advisory session is missing.")
    if not advisory_change_flow_can_append_turn(str(session.get("status") or "")):
        raise ValueError("Board advisory turn can only be appended while drafting.")
    current_profile = repository.get_latest_governance_profile(str(session["workflow_id"]), connection=connection)
    if current_profile is None:
        raise ValueError("Governance profile is required before appending a board advisory turn.")
    working_turn = build_board_advisory_turn(
        actor_type=actor_type,
        content=content,
        created_at=occurred_at,
    ).model_dump(mode="json")
    updated_session = repository.append_board_advisory_turn(
        connection,
        session_id=session_id,
        working_turn=working_turn,
        updated_at=occurred_at,
    )
    updated_session = _materialize_board_advisory_full_timeline_archive_checked(
        repository,
        connection,
        session=updated_session,
        current_profile=current_profile,
        occurred_at=occurred_at,
    )
    advisory_event = repository.insert_event(
        connection,
        event_type=EVENT_BOARD_ADVISORY_TURN_APPENDED,
        actor_type=actor_type,
        actor_id=actor_type,
        workflow_id=str(session["workflow_id"]),
        idempotency_key=idempotency_key,
        causation_id=command_id,
        correlation_id=str(session["workflow_id"]),
        payload={
            "session_id": session_id,
            "approval_id": session["approval_id"],
            "review_pack_id": session["review_pack_id"],
            "working_turn": working_turn,
            "status": "DRAFTING",
        },
        occurred_at=occurred_at,
    )
    if advisory_event is None:
        raise RuntimeError("Board advisory turn idempotency conflict.")
    return updated_session


def _request_board_advisory_analysis(
    repository: ControlPlaneRepository,
    connection,
    *,
    session_id: str,
    command_id: str,
    occurred_at,
    idempotency_key: str,
) -> tuple[dict[str, Any], str]:
    session = repository.get_board_advisory_session(session_id, connection=connection)
    if session is None:
        raise ValueError("Board advisory session is missing.")
    if not advisory_change_flow_can_request_analysis(str(session.get("status") or "")):
        raise ValueError("Board advisory analysis can only be requested while drafting.")
    board_decision = session.get("board_decision")
    if not isinstance(board_decision, dict):
        raise ValueError("Board advisory session is missing its drafting decision summary.")
    current_profile = repository.get_latest_governance_profile(str(session["workflow_id"]), connection=connection)
    if current_profile is None:
        raise ValueError("Governance profile is required before requesting advisory analysis.")
    run = create_board_advisory_analysis_run(
        repository,
        connection,
        session=session,
        idempotency_key=idempotency_key,
        occurred_at=occurred_at,
    )
    updated_session = repository.get_board_advisory_session(session_id, connection=connection)
    if updated_session is None:
        raise RuntimeError("Board advisory session row vanished after analysis run creation.")
    updated_session = _materialize_board_advisory_full_timeline_archive_checked(
        repository,
        connection,
        session=updated_session,
        current_profile=current_profile,
        occurred_at=occurred_at,
    )
    advisory_event = repository.insert_event(
        connection,
        event_type=EVENT_BOARD_ADVISORY_ANALYSIS_REQUESTED,
        actor_type="ceo",
        actor_id="ceo",
        workflow_id=str(session["workflow_id"]),
        idempotency_key=idempotency_key,
        causation_id=command_id,
        correlation_id=str(session["workflow_id"]),
        payload={
            "session_id": session_id,
            "approval_id": session["approval_id"],
            "review_pack_id": session["review_pack_id"],
            "run_id": run["run_id"],
            "source_graph_version": run["source_graph_version"],
            "status": "PENDING_ANALYSIS",
        },
        occurred_at=occurred_at,
    )
    if advisory_event is None:
        raise RuntimeError("Board advisory analysis request idempotency conflict.")
    return updated_session, str(run["run_id"])


def _apply_board_advisory_patch(
    repository: ControlPlaneRepository,
    connection,
    *,
    session_id: str,
    proposal_ref: str,
    command_id: str,
    occurred_at,
    idempotency_key: str,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    session = repository.get_board_advisory_session(session_id, connection=connection)
    if session is None:
        raise ValueError("Board advisory session is missing.")
    if not advisory_change_flow_can_apply(str(session.get("status") or "")):
        raise ValueError("Board advisory patch can only be applied after a proposal is ready for confirmation.")
    if str(session.get("latest_patch_proposal_ref") or "") != proposal_ref:
        raise ValueError("Board advisory patch proposal does not match the latest proposal for this session.")
    current_graph_version = resolve_workflow_graph_version(
        repository,
        str(session["workflow_id"]),
        connection=connection,
    )
    proposal = session.get("latest_patch_proposal")
    if not isinstance(proposal, dict):
        raise ValueError("Board advisory session is missing its latest graph patch proposal.")
    normalized_proposal = GraphPatchProposal.model_validate(proposal)
    if normalized_proposal.base_graph_version != current_graph_version:
        raise ValueError(
            f"Graph patch proposal is stale: expected {normalized_proposal.base_graph_version}, got {current_graph_version}."
        )
    graph_snapshot = build_ticket_graph_snapshot(
        repository,
        str(session["workflow_id"]),
        connection=connection,
    )
    existing_graph_node_ids = {
        str(node.graph_node_id or "").strip()
        for node in graph_snapshot.nodes
        if str(node.graph_node_id or "").strip()
    }
    duplicate_add_node_ids = sorted(
        {
            str(item.node_id).strip()
            for item in list(normalized_proposal.add_nodes or [])
            if str(item.node_id).strip() in existing_graph_node_ids
        }
    )
    if duplicate_add_node_ids:
        raise ValueError(
            "Graph patch proposal add_nodes must use new node ids: "
            + ", ".join(duplicate_add_node_ids)
        )
    graph_patch = build_graph_patch_from_proposal(
        normalized_proposal,
        session_id=session_id,
    )
    try:
        reduce_graph_patch_overlay(
            patch_records=[
                GraphPatchEventRecord(
                    event_id=f"pending:{session_id}",
                    sequence_no=0,
                    patch=graph_patch,
                )
            ],
            known_node_ids={
                str(node.graph_node_id or "").strip()
                for node in graph_snapshot.nodes
                if str(node.graph_node_id or "").strip()
            },
            known_patch_target_node_ids={
                str(node.runtime_node_id or node.node_id or "").strip()
                for node in graph_snapshot.nodes
                if str(node.graph_lane_kind or "") == "execution"
                and str(node.runtime_node_id or node.node_id or "").strip()
            },
            base_edge_keys={
                (edge.edge_type, edge.source_graph_node_id, edge.target_graph_node_id)
                for edge in graph_snapshot.edges
                if edge.edge_type != "REPLACES"
            },
            ticket_status_by_node_id={
                str(node.graph_node_id or "").strip(): node.ticket_status
                for node in graph_snapshot.nodes
                if str(node.graph_node_id or "").strip()
            },
            node_status_by_node_id={
                str(node.graph_node_id or "").strip(): node.node_status
                for node in graph_snapshot.nodes
                if str(node.graph_node_id or "").strip()
            },
        )
    except GraphPatchReducerUnavailableError as exc:
        raise ValueError(str(exc)) from exc
    board_decision = BoardAdvisoryDecision.model_validate(session.get("board_decision") or {})
    workflow_id = str(session["workflow_id"])
    review_pack = ((repository.get_approval_by_id(connection, str(session["approval_id"])) or {}).get("payload") or {}).get(
        "review_pack"
    ) or {}
    subject = review_pack.get("subject") or {}
    source_ticket_id, _source_graph_node_id, source_node_id = _board_advisory_artifact_subject(
        repository,
        connection,
        session=session,
    )
    patch_artifact_ref = advisory_graph_patch_artifact_ref(
        workflow_id=workflow_id,
        session_id=session_id,
    )
    _save_json_artifact(
        repository,
        connection,
        artifact_ref=patch_artifact_ref,
        logical_path=advisory_graph_patch_logical_path(session_id=session_id),
        workflow_id=workflow_id,
        ticket_id=source_ticket_id,
        node_id=source_node_id,
        payload=graph_patch.model_dump(mode="json"),
        kind="JSON",
        occurred_at=occurred_at,
    )
    event_row = repository.insert_event(
        connection,
        event_type=EVENT_BOARD_REVIEW_REJECTED,
        actor_type="board",
        actor_id="board",
        workflow_id=workflow_id,
        idempotency_key=f"{idempotency_key}:board-review-rejected",
        causation_id=command_id,
        correlation_id=workflow_id,
        payload={
            "approval_id": session["approval_id"],
            "review_pack_id": session["review_pack_id"],
            "node_id": source_node_id,
            "ticket_id": source_ticket_id,
            "board_comment": board_decision.board_comment,
            "constraint_patch": board_decision.constraint_patch,
            "governance_patch": (
                board_decision.governance_patch.model_dump(mode="json", exclude_none=True)
                if board_decision.governance_patch is not None
                else None
            ),
            "decision_action": "MODIFY_CONSTRAINTS",
        },
        occurred_at=occurred_at,
    )
    if event_row is None:
        raise RuntimeError("Board advisory board-review resolution idempotency conflict.")
    advisory_event = repository.insert_event(
        connection,
        event_type=EVENT_BOARD_ADVISORY_DECISION_RECORDED,
        actor_type="board",
        actor_id="board",
        workflow_id=workflow_id,
        idempotency_key=f"{idempotency_key}:advisory-decision-recorded",
        causation_id=command_id,
        correlation_id=workflow_id,
        payload={
            "session_id": session_id,
            "approval_id": session["approval_id"],
            "review_pack_id": session["review_pack_id"],
            "decision_action": "MODIFY_CONSTRAINTS",
            "decision_pack_refs": [
                *list(session.get("decision_pack_refs") or []),
                build_graph_patch_process_asset_ref(session_id, version_int=1),
            ],
            "latest_patch_proposal_ref": proposal_ref,
            "approved_patch_ref": build_graph_patch_process_asset_ref(session_id, version_int=1),
            "board_comment": board_decision.board_comment,
            "constraint_patch": board_decision.constraint_patch,
            "governance_patch": (
                board_decision.governance_patch.model_dump(mode="json", exclude_none=True)
                if board_decision.governance_patch is not None
                else None
            ),
        },
        occurred_at=occurred_at,
    )
    if advisory_event is None:
        raise RuntimeError("Board advisory decision idempotency conflict.")
    patch_event = repository.insert_event(
        connection,
        event_type=EVENT_GRAPH_PATCH_APPLIED,
        actor_type="board",
        actor_id="board",
        workflow_id=workflow_id,
        idempotency_key=idempotency_key,
        causation_id=command_id,
        correlation_id=workflow_id,
        payload=graph_patch.model_dump(mode="json"),
        occurred_at=occurred_at,
    )
    if patch_event is None:
        raise RuntimeError("Graph patch application idempotency conflict.")
    patched_graph_version = resolve_workflow_graph_version(
        repository,
        workflow_id,
        connection=connection,
    )
    decision_pack_refs = list(session.get("decision_pack_refs") or [])
    patch_ref = build_graph_patch_process_asset_ref(session_id, version_int=1)
    if patch_ref not in decision_pack_refs:
        decision_pack_refs.append(patch_ref)
    updated_session = repository.decide_board_advisory_session(
        connection,
        session_id=session_id,
        board_decision=board_decision.model_dump(mode="json", exclude_none=True),
        decision_pack_refs=decision_pack_refs,
        approved_patch_ref=patch_ref,
        approved_patch=graph_patch.model_dump(mode="json"),
        patched_graph_version=patched_graph_version,
        focus_node_ids=list(graph_patch.focus_node_ids),
        updated_at=occurred_at,
    )
    superseding_governance_profile: dict[str, Any] | None = None
    if board_decision.governance_patch is not None:
        current_profile = repository.get_latest_governance_profile(workflow_id, connection=connection)
        if current_profile is None:
            raise ValueError("Governance profile is required before applying a board advisory patch.")
        next_profile = build_governance_profile_from_patch(
            current_profile,
            board_decision.governance_patch,
            source_ref=patch_ref,
            effective_from_event=str(patch_event["event_id"]),
        )
        if next_profile is not None:
            repository.save_governance_profile(connection, next_profile)
            superseding_governance_profile = next_profile.model_dump(mode="json")
    archive_profile = repository.get_latest_governance_profile(workflow_id, connection=connection)
    if archive_profile is None:
        raise ValueError("Governance profile is required before materializing the board advisory timeline archive.")
    updated_session = _materialize_board_advisory_full_timeline_archive_checked(
        repository,
        connection,
        session=updated_session,
        current_profile=archive_profile,
        occurred_at=occurred_at,
    )
    approval = repository.resolve_approval(
        connection,
        approval_id=str(session["approval_id"]),
        status=APPROVAL_STATUS_MODIFIED_CONSTRAINTS,
        resolved_by="board",
        resolved_at=occurred_at,
        review_pack_version=int((repository.get_approval_by_id(connection, str(session["approval_id"])) or {}).get("review_pack_version") or 1) + 1,
        command_target_version=int(event_row["sequence_no"]),
        resolution={
            "decision_action": "MODIFY_CONSTRAINTS",
            "board_comment": board_decision.board_comment,
            "constraint_patch": board_decision.constraint_patch,
            "governance_patch": (
                board_decision.governance_patch.model_dump(mode="json", exclude_none=True)
                if board_decision.governance_patch is not None
                else None
            ),
            "latest_patch_proposal_ref": proposal_ref,
            "approved_patch_ref": patch_ref,
            "patched_graph_version": patched_graph_version,
            "superseding_governance_profile_ref": (
                superseding_governance_profile.get("profile_id")
                if isinstance(superseding_governance_profile, dict)
                else None
            ),
        },
    )
    return updated_session, superseding_governance_profile


def _normalize_requirement_elicitation_answers(
    approval: dict[str, Any],
    *,
    answers: list[ElicitationAnswer],
) -> tuple[list[ElicitationAnswer], list[str]]:
    review_pack = approval["payload"].get("review_pack") or {}
    raw_questionnaire = review_pack.get("elicitation_questionnaire") or []
    questionnaire = (
        [ElicitationQuestion.model_validate(item) for item in raw_questionnaire]
        if raw_questionnaire
        else build_requirement_elicitation_questionnaire()
    )
    normalized_answers = normalize_elicitation_answers(questionnaire, answers)
    weak_signals = list(((review_pack.get("delta_summary") or {}).get("weak_signals") or []))
    return normalized_answers, weak_signals


def _record_requirement_elicitation_artifacts(
    repository: ControlPlaneRepository,
    connection,
    *,
    approval: dict[str, Any],
    answers: list[ElicitationAnswer],
    board_comment: str,
    occurred_at,
) -> tuple[str, str]:
    workflow_id = approval["workflow_id"]
    source_ticket_id = build_project_init_scope_ticket_id(workflow_id)
    workflow_projection = repository.get_workflow_projection(workflow_id, connection=connection)
    kickoff_spec = build_project_init_kickoff_spec(workflow_projection)
    source_node_id = str(kickoff_spec["node_id"])
    directive_payload = _load_project_init_directive_payload(
        repository,
        connection,
        workflow_id=workflow_id,
    )
    questionnaire = build_requirement_elicitation_questionnaire()
    answers_summary = summarize_elicitation_answers(questionnaire, answers)
    weak_signals = list(
        (((approval["payload"].get("review_pack") or {}).get("delta_summary") or {}).get("weak_signals") or [])
    )
    elicitation_artifact_ref = f"art://project-init/{workflow_id}/requirements-elicitation.md"
    elicitation_logical_path = f"inputs/project-init/{workflow_id}/requirements-elicitation.md"
    enriched_brief_artifact_ref = f"art://project-init/{workflow_id}/board-brief-enriched.md"
    enriched_brief_logical_path = f"inputs/project-init/{workflow_id}/board-brief-enriched.md"
    _save_text_artifact(
        repository,
        connection,
        artifact_ref=elicitation_artifact_ref,
        logical_path=elicitation_logical_path,
        workflow_id=workflow_id,
        ticket_id=source_ticket_id,
        node_id=source_node_id,
        content=build_requirement_elicitation_markdown(
            workflow_id=workflow_id,
            weak_signals=weak_signals,
            answers_summary=answers_summary,
            board_comment=board_comment,
        ),
        kind="MARKDOWN",
        occurred_at=occurred_at,
    )
    _save_text_artifact(
        repository,
        connection,
        artifact_ref=enriched_brief_artifact_ref,
        logical_path=enriched_brief_logical_path,
        workflow_id=workflow_id,
        ticket_id=source_ticket_id,
        node_id=source_node_id,
        content=build_enriched_board_brief_markdown(
            workflow_id=workflow_id,
            north_star_goal=str(directive_payload.get("north_star_goal") or ""),
            budget_cap=int(directive_payload.get("budget_cap") or 0),
            deadline_at=str(directive_payload.get("deadline_at") or "") or None,
            hard_constraints=[
                str(item).strip()
                for item in directive_payload.get("hard_constraints") or []
                if str(item).strip()
            ],
            answers_summary=answers_summary,
        ),
        kind="MARKDOWN",
        occurred_at=occurred_at,
    )
    return elicitation_artifact_ref, enriched_brief_artifact_ref


def _kickoff_scope_after_requirement_elicitation(
    repository: ControlPlaneRepository,
    *,
    workflow_id: str,
    artifact_refs: list[str],
    idempotency_key_prefix: str,
) -> str | None:
    workflow = repository.get_workflow_projection(workflow_id)
    if workflow is None:
        raise ValueError("Workflow projection missing during requirement elicitation approval.")
    kickoff_spec = build_project_init_kickoff_spec(workflow)
    command = build_ceo_create_ticket_command(
        workflow=workflow,
        payload=CEOCreateTicketPayload(
            workflow_id=workflow_id,
            node_id=str(kickoff_spec["node_id"]),
            role_profile_ref=str(kickoff_spec["role_profile_ref"]),
            output_schema_ref=str(kickoff_spec["output_schema_ref"]),
            summary=str(kickoff_spec["summary"]),
            parent_ticket_id=None,
        ),
        repository=repository,
    )
    command = command.model_copy(
        update={
            "input_artifact_refs": list(dict.fromkeys(list(command.input_artifact_refs) + artifact_refs)),
            "idempotency_key": f"{idempotency_key_prefix}:scope-kickoff",
        }
    )
    ack = handle_ticket_create(repository, command)
    if ack.status.value not in {"ACCEPTED", "DUPLICATE"}:
        raise ValueError(ack.reason or "Scope kickoff could not be created after requirement elicitation.")
    auto_advance_workflow_to_next_stop(
        repository,
        workflow_id=workflow_id,
        idempotency_key_prefix=f"{idempotency_key_prefix}:auto-advance",
        max_steps=PROJECT_INIT_AUTO_ADVANCE_MAX_STEPS,
    )
    return ack.causation_hint


def _resolve_approval_source_ticket_specs(
    repository: ControlPlaneRepository,
    connection,
    *,
    approval: dict[str, Any],
) -> tuple[str, dict[str, Any] | None, str, dict[str, Any] | None]:
    review_pack = approval["payload"].get("review_pack") or {}
    subject = review_pack.get("subject") or {}
    source_ticket_id = str(subject.get("source_ticket_id") or "").strip()
    if not source_ticket_id:
        return "", None, "", None

    created_spec = repository.get_latest_ticket_created_payload(connection, source_ticket_id)
    if created_spec is None:
        return source_ticket_id, None, source_ticket_id, None

    maker_checker_context = created_spec.get("maker_checker_context") or {}
    maker_ticket_spec = maker_checker_context.get("maker_ticket_spec") or {}
    logical_source_ticket_id = str(maker_checker_context.get("maker_ticket_id") or source_ticket_id)
    logical_created_spec = (
        maker_ticket_spec
        if str(created_spec.get("output_schema_ref") or "") == "maker_checker_verdict"
        and isinstance(maker_ticket_spec, dict)
        and maker_ticket_spec
        else created_spec
    )
    return source_ticket_id, created_spec, logical_source_ticket_id, logical_created_spec


def _closeout_ticket_id_for_review_ticket(review_ticket_id: str) -> str:
    if review_ticket_id.endswith("_review"):
        return f"{review_ticket_id.removesuffix('_review')}_closeout"
    return f"{review_ticket_id}_closeout"


def _closeout_node_id_for_ticket(closeout_ticket_id: str) -> str:
    return f"node_followup_{closeout_ticket_id.removeprefix('tkt_')}"


def _resolve_review_gate_source_code_ticket(
    repository: ControlPlaneRepository,
    connection,
    *,
    approval: dict[str, Any],
) -> tuple[str | None, dict[str, Any] | None]:
    _, _, logical_source_ticket_id, logical_created_spec = _resolve_approval_source_ticket_specs(
        repository,
        connection,
        approval=approval,
    )
    if not logical_source_ticket_id or logical_created_spec is None:
        return None, None
    source_code_ticket_id = resolve_source_code_ticket_from_chain(
        repository,
        connection=connection,
        ticket_id=logical_source_ticket_id,
    )
    if source_code_ticket_id is None:
        return None, None
    source_created_spec = repository.get_latest_ticket_created_payload(connection, source_code_ticket_id) or {}
    return source_code_ticket_id, source_created_spec


def _open_review_gate_merge_failed_incident(
    repository: ControlPlaneRepository,
    connection,
    *,
    command_id: str,
    occurred_at,
    workflow_id: str,
    ticket_id: str,
    node_id: str,
    git_branch_ref: str,
    merge_error: str,
    idempotency_key: str,
) -> str:
    existing_incident = repository.get_open_incident_for_node(workflow_id, node_id, connection=connection)
    if existing_incident is not None:
        return str(existing_incident["incident_id"])

    incident_id = new_prefixed_id("inc")
    incident_event = repository.insert_event(
        connection,
        event_type=EVENT_INCIDENT_OPENED,
        actor_type="system",
        actor_id="review-gate",
        workflow_id=workflow_id,
        idempotency_key=idempotency_key,
        causation_id=command_id,
        correlation_id=workflow_id,
        payload={
            "incident_id": incident_id,
            "ticket_id": ticket_id,
            "node_id": node_id,
            "incident_type": INCIDENT_TYPE_REVIEW_GATE_MERGE_FAILED,
            "status": INCIDENT_STATUS_OPEN,
            "severity": "high",
            "fingerprint": f"review-gate-merge:{workflow_id}:{ticket_id}",
            "git_branch_ref": git_branch_ref,
            "merge_error": merge_error,
        },
        occurred_at=occurred_at,
    )
    if incident_event is None:
        raise RuntimeError("Review gate merge incident opening idempotency conflict.")
    return incident_id


def _build_post_review_closeout_ticket_payload(
    repository: ControlPlaneRepository,
    connection,
    *,
    approval: dict[str, Any],
    selected_option_id: str,
) -> dict[str, Any] | None:
    if approval["approval_type"] != "VISUAL_MILESTONE":
        return None

    _, _, logical_source_ticket_id, logical_created_spec = _resolve_approval_source_ticket_specs(
        repository,
        connection,
        approval=approval,
    )
    if not logical_source_ticket_id or logical_created_spec is None:
        return None
    if str(logical_created_spec.get("delivery_stage") or "") != DeliveryStage.REVIEW.value:
        return None
    if str(logical_created_spec.get("output_schema_ref") or "") != UI_MILESTONE_REVIEW_SCHEMA_REF:
        return None

    closeout_ticket_id = _closeout_ticket_id_for_review_ticket(logical_source_ticket_id)
    closeout_node_id = _closeout_node_id_for_ticket(closeout_ticket_id)
    if repository.get_current_ticket_projection(closeout_ticket_id, connection=connection) is not None:
        return None
    if (
        repository.get_current_node_projection(approval["workflow_id"], closeout_node_id, connection=connection)
        is not None
    ):
        return None

    review_pack = approval["payload"].get("review_pack") or {}
    resolution = approval["payload"].get("resolution") or {}
    selected_option = next(
        (
            option
            for option in review_pack.get("options") or []
            if option.get("option_id") == selected_option_id
        ),
        None,
    )
    recommendation = review_pack.get("recommendation") or {}
    closeout_summary = str(
        (selected_option or {}).get("summary")
        or recommendation.get("summary")
        or review_pack.get("title")
        or "Board-approved delivery closeout package"
    ).strip()
    evidence_refs = [
        str(item.get("source_ref") or "").strip()
        for item in review_pack.get("evidence_summary") or []
        if str(item.get("source_ref") or "").strip()
    ]
    selected_artifact_refs = [
        str(item).strip()
        for item in ((selected_option or {}).get("artifact_refs") or [])
        if str(item).strip()
    ]
    source_process_asset_refs = get_ticket_output_process_asset_refs(
        repository,
        connection,
        logical_source_ticket_id,
    )
    input_artifact_refs = _dedupe_artifact_refs(
        list(logical_created_spec.get("input_artifact_refs") or []) + evidence_refs + selected_artifact_refs
    )
    input_process_asset_refs = merge_input_process_asset_refs(
        existing_process_asset_refs=list(logical_created_spec.get("input_process_asset_refs") or []),
        artifact_refs=input_artifact_refs,
        produced_process_asset_refs=source_process_asset_refs,
    )

    return TicketCreateCommand(
        ticket_id=closeout_ticket_id,
        workflow_id=approval["workflow_id"],
        node_id=closeout_node_id,
        parent_ticket_id=logical_source_ticket_id,
        attempt_no=1,
        role_profile_ref=str(logical_created_spec.get("role_profile_ref") or "ui_designer_primary"),
        constraints_ref="approved_scope_delivery_closeout",
        graph_contract={"lane_kind": "execution"},
        execution_contract=infer_execution_contract_payload(
            role_profile_ref=str(logical_created_spec.get("role_profile_ref") or "ui_designer_primary"),
            output_schema_ref=DELIVERY_CLOSEOUT_PACKAGE_SCHEMA_REF,
        ),
        input_artifact_refs=input_artifact_refs,
        input_process_asset_refs=input_process_asset_refs,
        context_query_plan={
            "keywords": ["approved final review", "delivery closeout", "handoff"],
            "semantic_queries": [closeout_summary],
            "max_context_tokens": get_settings().default_max_context_tokens,
        },
        acceptance_criteria=[
            f"Must capture the approved final delivery choice: {closeout_summary}",
            "Must gather the final delivery artifact references chosen in board review.",
            "Must provide minimal handoff notes for the approved delivery package.",
            "Must report documentation updates, or explicitly mark affected docs as no change required.",
            "Must stay inside the already approved scope.",
        ],
        output_schema_ref=DELIVERY_CLOSEOUT_PACKAGE_SCHEMA_REF,
        output_schema_version=DELIVERY_CLOSEOUT_PACKAGE_SCHEMA_VERSION,
        allowed_tools=["read_artifact", "write_artifact"],
        allowed_write_set=[f"20-evidence/closeout/{closeout_ticket_id}/*"],
        retry_budget=1,
        priority="high",
        timeout_sla_sec=1800,
        deadline_at=logical_created_spec.get("deadline_at"),
        delivery_stage=DeliveryStage.CLOSEOUT,
        auto_review_request=_build_closeout_internal_review_request(closeout_summary),
        escalation_policy={
            "on_timeout": "retry",
            "on_schema_error": "retry",
            "on_repeat_failure": "escalate_ceo",
        },
        idempotency_key=f"board-approved-closeout:{approval['approval_id']}:{closeout_ticket_id}",
    ).model_dump(mode="json")


def _handle_board_approve(
    repository: ControlPlaneRepository,
    payload: BoardApproveCommand,
    *,
    actor_type: str,
    actor_id: str,
    resolved_by: str,
    trigger_ceo_shadow: bool,
) -> CommandAckEnvelope:
    command_id = new_prefixed_id("cmd")
    received_at = now_local()
    created_followup_ticket_ids: list[str] = []
    kickoff_causation_hint: str | None = None
    kickoff_artifact_refs: list[str] = []
    pending_closeout_ticket_payload: dict[str, Any] | None = None
    with repository.transaction() as connection:
        existing_event = repository.get_event_by_idempotency_key(connection, payload.idempotency_key)
        if existing_event is not None:
            return _duplicate_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                approval_id=payload.approval_id,
            )

        approval = repository.get_approval_by_id(connection, payload.approval_id)
        reason = _validate_open_approval(
            approval,
            approval_id=payload.approval_id,
            review_pack_id=payload.review_pack_id,
            review_pack_version=payload.review_pack_version,
            command_target_version=payload.command_target_version,
        )
        if reason is not None:
            return _rejected_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                reason=reason,
                causation_hint=f"approval:{payload.approval_id}",
            )
        projection_reason = _validate_blocked_projection(repository, approval)
        if projection_reason is not None:
            return _rejected_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                reason=projection_reason,
                causation_hint=f"approval:{payload.approval_id}",
            )

        subject = approval["payload"].get("review_pack", {}).get("subject", {})
        normalized_elicitation_answers: list[ElicitationAnswer] = []
        review_gate_source_ticket_id: str | None = None
        review_gate_source_created_spec: dict[str, Any] | None = None
        if approval["approval_type"] == "REQUIREMENT_ELICITATION":
            try:
                normalized_elicitation_answers, _ = _normalize_requirement_elicitation_answers(
                    approval,
                    answers=list(payload.elicitation_answers),
                )
            except ValueError as exc:
                return _rejected_ack(
                    command_id=command_id,
                    idempotency_key=payload.idempotency_key,
                    received_at=received_at,
                    reason=str(exc),
                    causation_hint=f"approval:{payload.approval_id}",
                )
        elif approval["approval_type"] == "VISUAL_MILESTONE":
                _source_ticket_id, _source_graph_node_id, source_node_id = _resolve_review_pack_execution_subject(
                    repository,
                    connection,
                    workflow_id=approval["workflow_id"],
                    subject=subject,
                    fallback_ticket_id=str(subject.get("source_ticket_id") or "").strip() or None,
                )
                (
                    review_gate_source_ticket_id,
                    review_gate_source_created_spec,
                ) = _resolve_review_gate_source_code_ticket(
                    repository,
                    connection,
                    approval=approval,
                )
                if (
                    review_gate_source_ticket_id is not None
                    and review_gate_source_created_spec is not None
                    and is_workspace_managed_source_code_ticket(review_gate_source_created_spec)
                ):
                    checkout_truth = resolve_ticket_checkout_truth(
                        approval["workflow_id"],
                        review_gate_source_ticket_id,
                        review_gate_source_created_spec,
                    )
                    try:
                        merge_ticket_branch_into_main(
                            workflow_id=approval["workflow_id"],
                            ticket_id=review_gate_source_ticket_id,
                            git_branch_ref=checkout_truth["git_branch_ref"],
                        )
                    except RuntimeError as exc:
                        incident_id = _open_review_gate_merge_failed_incident(
                            repository,
                            connection,
                            command_id=command_id,
                            occurred_at=received_at,
                            workflow_id=approval["workflow_id"],
                            ticket_id=review_gate_source_ticket_id,
                            node_id=source_node_id,
                            git_branch_ref=checkout_truth["git_branch_ref"],
                            merge_error=str(exc),
                            idempotency_key=f"{payload.idempotency_key}:review-gate-merge-incident",
                        )
                        repository.refresh_projections(connection)
                        return _rejected_ack(
                            command_id=command_id,
                            idempotency_key=payload.idempotency_key,
                            received_at=received_at,
                            reason=f"Review gate merge failed: {exc}",
                            causation_hint=f"incident:{incident_id}",
                        )
                    finalize_workspace_ticket_git_status(
                        workflow_id=approval["workflow_id"],
                        ticket_id=review_gate_source_ticket_id,
                        created_spec=review_gate_source_created_spec,
                        merge_status="MERGED",
                    )
                    sync_ticket_boardroom_views(
                        repository,
                        workflow_id=approval["workflow_id"],
                        ticket_id=review_gate_source_ticket_id,
                        connection=connection,
                    )
                    sync_active_worktree_index(
                        repository,
                        workflow_id=approval["workflow_id"],
                        connection=connection,
                    )

        source_ticket_id, _source_graph_node_id, source_node_id = _resolve_review_pack_execution_subject(
            repository,
            connection,
            workflow_id=approval["workflow_id"],
            subject=subject,
            fallback_ticket_id=str(subject.get("source_ticket_id") or "").strip() or None,
        )
        event_row = repository.insert_event(
            connection,
            event_type=EVENT_BOARD_REVIEW_APPROVED,
            actor_type=actor_type,
            actor_id=actor_id,
            workflow_id=approval["workflow_id"],
            idempotency_key=payload.idempotency_key,
            causation_id=command_id,
            correlation_id=approval["workflow_id"],
            payload={
                "approval_id": payload.approval_id,
                "review_pack_id": payload.review_pack_id,
                "node_id": source_node_id,
                "ticket_id": source_ticket_id,
                "selected_option_id": payload.selected_option_id,
                "board_comment": payload.board_comment,
                "elicitation_answers": [
                    item.model_dump(mode="json") for item in normalized_elicitation_answers
                ],
            },
            occurred_at=received_at,
        )
        if event_row is None:
            return _duplicate_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                approval_id=payload.approval_id,
            )

        employee_causation_hint = _apply_employee_change_approval(
            repository,
            connection,
            approval=approval,
            command_id=command_id,
            occurred_at=received_at,
            idempotency_key=payload.idempotency_key,
        )

        repository.resolve_approval(
            connection,
            approval_id=payload.approval_id,
            status=APPROVAL_STATUS_APPROVED,
            resolved_by=resolved_by,
            resolved_at=received_at,
            review_pack_version=payload.review_pack_version + 1,
            command_target_version=int(event_row["sequence_no"]),
            resolution={
                "decision_action": "APPROVE",
                "selected_option_id": payload.selected_option_id,
                "board_comment": payload.board_comment,
                "elicitation_answers": [
                    item.model_dump(mode="json") for item in normalized_elicitation_answers
                ],
            },
        )
        try:
            _dismiss_board_advisory_session_if_needed(
                repository,
                connection,
                approval=approval,
                command_id=command_id,
                occurred_at=received_at,
                idempotency_key=f"{payload.idempotency_key}:board-advisory-dismiss",
            )
        except ValueError as exc:
            connection.rollback()
            return _rejected_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                reason=str(exc),
                causation_hint=f"approval:{payload.approval_id}",
            )
        if approval["approval_type"] == "REQUIREMENT_ELICITATION":
            elicitation_artifact_ref, enriched_brief_artifact_ref = _record_requirement_elicitation_artifacts(
                repository,
                connection,
                approval=repository.get_approval_by_id(connection, payload.approval_id) or approval,
                answers=normalized_elicitation_answers,
                board_comment=payload.board_comment,
                occurred_at=received_at,
            )
            kickoff_artifact_refs = [elicitation_artifact_ref, enriched_brief_artifact_ref]
            repository.refresh_projections(connection)
        else:
            pending_closeout_ticket_payload = _build_post_review_closeout_ticket_payload(
                repository,
                connection,
                approval=repository.get_approval_by_id(connection, payload.approval_id) or approval,
                selected_option_id=payload.selected_option_id,
            )
            repository.refresh_projections(connection)

    if approval["approval_type"] == "REQUIREMENT_ELICITATION":
        kickoff_causation_hint = _kickoff_scope_after_requirement_elicitation(
            repository,
            workflow_id=approval["workflow_id"],
            artifact_refs=kickoff_artifact_refs,
            idempotency_key_prefix=payload.idempotency_key,
        )
        created_followup_ticket_ids.append(build_project_init_scope_ticket_id(approval["workflow_id"]))
    elif pending_closeout_ticket_payload is not None:
        created_followup_ticket_ids.append(
            handle_ticket_create(
                repository,
                TicketCreateCommand.model_validate(
                    {
                        **pending_closeout_ticket_payload,
                        "idempotency_key": f"{payload.idempotency_key}:closeout-create",
                    }
                ),
            )
        )

    if (
        approval["approval_type"] != "REQUIREMENT_ELICITATION"
        and repository.get_workflow_projection(approval["workflow_id"]) is not None
    ):
        auto_advance_workflow_to_next_stop(
            repository,
            workflow_id=approval["workflow_id"],
            idempotency_key_prefix=f"{payload.idempotency_key}:workflow-auto-advance",
            max_steps=SCOPE_APPROVAL_AUTO_ADVANCE_MAX_STEPS,
            max_dispatches=1,
        )

    if trigger_ceo_shadow and approval["approval_type"] != "REQUIREMENT_ELICITATION":
        _trigger_ceo_shadow_safely(
            repository,
            workflow_id=approval["workflow_id"],
            approval_id=payload.approval_id,
        )
    return CommandAckEnvelope(
        command_id=command_id,
        idempotency_key=payload.idempotency_key,
        status=CommandAckStatus.ACCEPTED,
        received_at=received_at,
        reason=None,
        causation_hint=(
            f"employee:{employee_causation_hint}"
            if employee_causation_hint is not None
            else (
                kickoff_causation_hint
                if kickoff_causation_hint is not None
                else (
                f"ticket:{created_followup_ticket_ids[0]}"
                if created_followup_ticket_ids
                else f"approval:{payload.approval_id}"
                )
            )
        ),
    )


def handle_board_approve(
    repository: ControlPlaneRepository,
    payload: BoardApproveCommand,
) -> CommandAckEnvelope:
    return _handle_board_approve(
        repository,
        payload,
        actor_type="board",
        actor_id="board",
        resolved_by="board",
        trigger_ceo_shadow=True,
    )


def handle_ceo_delegate_approve(
    repository: ControlPlaneRepository,
    approval: dict[str, Any],
    *,
    idempotency_key_prefix: str,
) -> CommandAckEnvelope:
    command = build_ceo_delegate_board_approval_command(
        approval,
        idempotency_key_prefix=idempotency_key_prefix,
    )
    return _handle_board_approve(
        repository,
        command,
        actor_type="ceo",
        actor_id="ceo",
        resolved_by="ceo_delegate",
        trigger_ceo_shadow=False,
    )


def handle_board_reject(
    repository: ControlPlaneRepository,
    payload: BoardRejectCommand,
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
                approval_id=payload.approval_id,
            )

        approval = repository.get_approval_by_id(connection, payload.approval_id)
        reason = _validate_open_approval(
            approval,
            approval_id=payload.approval_id,
            review_pack_id=payload.review_pack_id,
            review_pack_version=payload.review_pack_version,
            command_target_version=payload.command_target_version,
        )
        if reason is not None:
            return _rejected_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                reason=reason,
                causation_hint=f"approval:{payload.approval_id}",
            )
        projection_reason = _validate_blocked_projection(repository, approval)
        if projection_reason is not None:
            return _rejected_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                reason=projection_reason,
                causation_hint=f"approval:{payload.approval_id}",
            )

        subject = approval["payload"].get("review_pack", {}).get("subject", {})
        source_ticket_id, _source_graph_node_id, source_node_id = _resolve_review_pack_execution_subject(
            repository,
            connection,
            workflow_id=approval["workflow_id"],
            subject=subject,
            fallback_ticket_id=str(subject.get("source_ticket_id") or "").strip() or None,
        )

        event_row = repository.insert_event(
            connection,
            event_type=EVENT_BOARD_REVIEW_REJECTED,
            actor_type="board",
            actor_id="board",
            workflow_id=approval["workflow_id"],
            idempotency_key=payload.idempotency_key,
            causation_id=command_id,
            correlation_id=approval["workflow_id"],
            payload={
                "approval_id": payload.approval_id,
                "review_pack_id": payload.review_pack_id,
                "node_id": source_node_id,
                "ticket_id": source_ticket_id,
                "board_comment": payload.board_comment,
                "rejection_reasons": payload.rejection_reasons,
                "decision_action": "REJECT",
            },
            occurred_at=received_at,
        )
        if event_row is None:
            return _duplicate_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                approval_id=payload.approval_id,
            )

        repository.resolve_approval(
            connection,
            approval_id=payload.approval_id,
            status=APPROVAL_STATUS_REJECTED,
            resolved_by="board",
            resolved_at=received_at,
            review_pack_version=payload.review_pack_version + 1,
            command_target_version=int(event_row["sequence_no"]),
            resolution={
                "decision_action": "REJECT",
                "board_comment": payload.board_comment,
                "rejection_reasons": payload.rejection_reasons,
            },
        )
        try:
            _dismiss_board_advisory_session_if_needed(
                repository,
                connection,
                approval=approval,
                command_id=command_id,
                occurred_at=received_at,
                idempotency_key=f"{payload.idempotency_key}:board-advisory-dismiss",
            )
        except ValueError as exc:
            connection.rollback()
            return _rejected_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                reason=str(exc),
                causation_hint=f"approval:{payload.approval_id}",
            )
        repository.refresh_projections(connection)

    if approval["approval_type"] == "VISUAL_MILESTONE":
        with repository.connection() as connection:
            source_code_ticket_id, source_created_spec = _resolve_review_gate_source_code_ticket(
                repository,
                connection,
                approval=approval,
            )
        if (
            source_code_ticket_id is not None
            and source_created_spec is not None
            and is_workspace_managed_source_code_ticket(source_created_spec)
        ):
            finalize_workspace_ticket_git_status(
                workflow_id=approval["workflow_id"],
                ticket_id=source_code_ticket_id,
                created_spec=source_created_spec,
                merge_status="NOT_REQUESTED",
            )
            sync_ticket_boardroom_views(
                repository,
                workflow_id=approval["workflow_id"],
                ticket_id=source_code_ticket_id,
            )
            sync_active_worktree_index(repository, workflow_id=approval["workflow_id"])

    _trigger_ceo_shadow_safely(
        repository,
        workflow_id=approval["workflow_id"],
        approval_id=payload.approval_id,
    )
    return CommandAckEnvelope(
        command_id=command_id,
        idempotency_key=payload.idempotency_key,
        status=CommandAckStatus.ACCEPTED,
        received_at=received_at,
        reason=None,
        causation_hint=f"approval:{payload.approval_id}",
    )


def handle_modify_constraints(
    repository: ControlPlaneRepository,
    payload: ModifyConstraintsCommand,
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
                approval_id=payload.approval_id,
            )

        approval = repository.get_approval_by_id(connection, payload.approval_id)
        reason = _validate_open_approval(
            approval,
            approval_id=payload.approval_id,
            review_pack_id=payload.review_pack_id,
            review_pack_version=payload.review_pack_version,
            command_target_version=payload.command_target_version,
        )
        if reason is not None:
            return _rejected_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                reason=reason,
                causation_hint=f"approval:{payload.approval_id}",
            )
        projection_reason = _validate_blocked_projection(repository, approval)
        if projection_reason is not None:
            return _rejected_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                reason=projection_reason,
                causation_hint=f"approval:{payload.approval_id}",
            )

        review_pack = (approval["payload"].get("review_pack") or {})
        subject = review_pack.get("subject", {})
        source_ticket_id, _source_graph_node_id, source_node_id = _resolve_review_pack_execution_subject(
            repository,
            connection,
            workflow_id=approval["workflow_id"],
            subject=subject,
            fallback_ticket_id=str(subject.get("source_ticket_id") or "").strip() or None,
        )
        governance_patch, governance_patch_error = _resolve_governance_patch_or_reject(payload)
        if governance_patch_error is not None:
            return _rejected_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                reason=governance_patch_error,
                causation_hint=f"approval:{payload.approval_id}",
            )
        if governance_patch is not None and not advisory_supports_governance_patch(review_pack):
            return _rejected_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                reason="This review pack does not support governance_patch.",
                causation_hint=f"approval:{payload.approval_id}",
            )
        normalized_elicitation_answers: list[ElicitationAnswer] = []
        if approval["approval_type"] == "REQUIREMENT_ELICITATION":
            try:
                normalized_elicitation_answers, weak_signals = _normalize_requirement_elicitation_answers(
                    approval,
                    answers=list(payload.elicitation_answers),
                )
            except ValueError as exc:
                return _rejected_ack(
                    command_id=command_id,
                    idempotency_key=payload.idempotency_key,
                received_at=received_at,
                reason=str(exc),
                causation_hint=f"approval:{payload.approval_id}",
            )

        if review_pack_requires_board_advisory(review_pack):
            try:
                _enter_board_advisory_change_flow(
                    repository,
                    connection,
                    approval=approval,
                    governance_patch=governance_patch,
                    constraint_patch=payload.constraint_patch.model_dump(mode="json"),
                    board_comment=payload.board_comment,
                    command_id=command_id,
                    occurred_at=received_at,
                    idempotency_key=payload.idempotency_key,
                )
            except ValueError as exc:
                connection.rollback()
                return _rejected_ack(
                    command_id=command_id,
                    idempotency_key=payload.idempotency_key,
                    received_at=received_at,
                    reason=str(exc),
                    causation_hint=f"approval:{payload.approval_id}",
                )
            repository.refresh_projections(connection)
            return CommandAckEnvelope(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                status=CommandAckStatus.ACCEPTED,
                received_at=received_at,
                causation_hint=f"approval:{payload.approval_id}",
            )

        event_row = repository.insert_event(
            connection,
            event_type=EVENT_BOARD_REVIEW_REJECTED,
            actor_type="board",
            actor_id="board",
            workflow_id=approval["workflow_id"],
            idempotency_key=payload.idempotency_key,
            causation_id=command_id,
            correlation_id=approval["workflow_id"],
            payload={
                "approval_id": payload.approval_id,
                "review_pack_id": payload.review_pack_id,
                "node_id": source_node_id,
                "ticket_id": source_ticket_id,
                "board_comment": payload.board_comment,
                "constraint_patch": payload.constraint_patch.model_dump(mode="json"),
                "governance_patch": (
                    governance_patch.model_dump(mode="json", exclude_none=True)
                    if governance_patch is not None
                    else None
                ),
                "decision_action": "MODIFY_CONSTRAINTS",
                "elicitation_answers": [
                    item.model_dump(mode="json") for item in normalized_elicitation_answers
                ],
            },
            occurred_at=received_at,
        )
        if event_row is None:
            return _duplicate_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                approval_id=payload.approval_id,
            )

        superseding_governance_profile: dict[str, Any] | None = None
        if review_pack_requires_board_advisory(review_pack):
            _, superseding_governance_profile = _record_board_advisory_decision(
                repository,
                connection,
                approval=approval,
                governance_patch=governance_patch,
                constraint_patch=payload.constraint_patch.model_dump(mode="json"),
                board_comment=payload.board_comment,
                command_id=command_id,
                occurred_at=received_at,
                idempotency_key=f"{payload.idempotency_key}:board-advisory-decision",
            )
        repository.resolve_approval(
            connection,
            approval_id=payload.approval_id,
            status=APPROVAL_STATUS_MODIFIED_CONSTRAINTS,
            resolved_by="board",
            resolved_at=received_at,
            review_pack_version=payload.review_pack_version + 1,
            command_target_version=int(event_row["sequence_no"]),
            resolution={
                "decision_action": "MODIFY_CONSTRAINTS",
                "board_comment": payload.board_comment,
                "constraint_patch": payload.constraint_patch.model_dump(mode="json"),
                "governance_patch": (
                    governance_patch.model_dump(mode="json", exclude_none=True)
                    if governance_patch is not None
                    else None
                ),
                "superseding_governance_profile_ref": (
                    superseding_governance_profile.get("profile_id")
                    if isinstance(superseding_governance_profile, dict)
                    else None
                ),
                "elicitation_answers": [
                    item.model_dump(mode="json") for item in normalized_elicitation_answers
                ],
            },
        )
        if approval["approval_type"] == "REQUIREMENT_ELICITATION":
            _record_requirement_elicitation_artifacts(
                repository,
                connection,
                approval=repository.get_approval_by_id(connection, payload.approval_id) or approval,
                answers=normalized_elicitation_answers,
                board_comment=payload.board_comment,
                occurred_at=received_at,
            )
            reopened_payload = build_requirement_elicitation_review_payload(
                workflow_id=approval["workflow_id"],
                occurred_at=received_at,
                weak_signals=weak_signals,
                board_brief_artifact_ref=f"art://project-init/{approval['workflow_id']}/board-brief.md",
                draft_answers=normalized_elicitation_answers,
            )
            repository.create_approval_request(
                connection,
                workflow_id=approval["workflow_id"],
                approval_type="REQUIREMENT_ELICITATION",
                requested_by="system",
                review_pack=reopened_payload["review_pack"],
                available_actions=reopened_payload["available_actions"],
                draft_defaults=reopened_payload["draft_defaults"],
                inbox_title=reopened_payload["inbox_title"],
                inbox_summary=reopened_payload["inbox_summary"],
                badges=reopened_payload["badges"],
                priority=reopened_payload["priority"],
                occurred_at=received_at,
                idempotency_key=f"{payload.idempotency_key}:reopen-requirement-elicitation",
            )
        repository.refresh_projections(connection)

    if approval["approval_type"] == "VISUAL_MILESTONE":
        with repository.connection() as connection:
            source_code_ticket_id, source_created_spec = _resolve_review_gate_source_code_ticket(
                repository,
                connection,
                approval=approval,
            )
        if (
            source_code_ticket_id is not None
            and source_created_spec is not None
            and is_workspace_managed_source_code_ticket(source_created_spec)
        ):
            finalize_workspace_ticket_git_status(
                workflow_id=approval["workflow_id"],
                ticket_id=source_code_ticket_id,
                created_spec=source_created_spec,
                merge_status="NOT_REQUESTED",
            )
            sync_ticket_boardroom_views(
                repository,
                workflow_id=approval["workflow_id"],
                ticket_id=source_code_ticket_id,
            )
            sync_active_worktree_index(repository, workflow_id=approval["workflow_id"])

    if approval["approval_type"] != "REQUIREMENT_ELICITATION":
        _trigger_ceo_shadow_safely(
            repository,
            workflow_id=approval["workflow_id"],
            approval_id=payload.approval_id,
        )
    return CommandAckEnvelope(
        command_id=command_id,
        idempotency_key=payload.idempotency_key,
        status=CommandAckStatus.ACCEPTED,
        received_at=received_at,
        reason=None,
        causation_hint=f"approval:{payload.approval_id}",
    )


def handle_board_advisory_append_turn(
    repository: ControlPlaneRepository,
    payload: BoardAdvisoryAppendTurnCommand,
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
                approval_id=str((existing_event.get("payload") or {}).get("approval_id") or payload.session_id),
            )
        try:
            session = _append_board_advisory_turn(
                repository,
                connection,
                session_id=payload.session_id,
                actor_type=payload.actor_type,
                content=payload.content,
                command_id=command_id,
                occurred_at=received_at,
                idempotency_key=payload.idempotency_key,
            )
        except ValueError as exc:
            connection.rollback()
            return _rejected_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                reason=str(exc),
                causation_hint=f"board-advisory:{payload.session_id}",
            )
        repository.refresh_projections(connection)

    return CommandAckEnvelope(
        command_id=command_id,
        idempotency_key=payload.idempotency_key,
        status=CommandAckStatus.ACCEPTED,
        received_at=received_at,
        causation_hint=f"approval:{session['approval_id']}",
    )


def handle_board_advisory_request_analysis(
    repository: ControlPlaneRepository,
    payload: BoardAdvisoryRequestAnalysisCommand,
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
                approval_id=str((existing_event.get("payload") or {}).get("approval_id") or payload.session_id),
            )
        try:
            session, run_id = _request_board_advisory_analysis(
                repository,
                connection,
                session_id=payload.session_id,
                command_id=command_id,
                occurred_at=received_at,
                idempotency_key=payload.idempotency_key,
            )
        except ValueError as exc:
            connection.rollback()
            return _rejected_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                reason=str(exc),
                causation_hint=f"board-advisory:{payload.session_id}",
            )
        repository.refresh_projections(connection)

    run_board_advisory_analysis(repository, run_id)
    return CommandAckEnvelope(
        command_id=command_id,
        idempotency_key=payload.idempotency_key,
        status=CommandAckStatus.ACCEPTED,
        received_at=received_at,
        causation_hint=f"approval:{session['approval_id']}",
    )


def handle_board_advisory_apply_patch(
    repository: ControlPlaneRepository,
    payload: BoardAdvisoryApplyPatchCommand,
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
                approval_id=str((existing_event.get("payload") or {}).get("approval_id") or payload.session_id),
            )
        try:
            session, _ = _apply_board_advisory_patch(
                repository,
                connection,
                session_id=payload.session_id,
                proposal_ref=payload.proposal_ref,
                command_id=command_id,
                occurred_at=received_at,
                idempotency_key=payload.idempotency_key,
            )
        except ValueError as exc:
            connection.rollback()
            return _rejected_ack(
                command_id=command_id,
                idempotency_key=payload.idempotency_key,
                received_at=received_at,
                reason=str(exc),
                causation_hint=f"board-advisory:{payload.session_id}",
            )
        repository.refresh_projections(connection)

    _trigger_ceo_shadow_safely(
        repository,
        workflow_id=session["workflow_id"],
        approval_id=session["approval_id"],
    )
    return CommandAckEnvelope(
        command_id=command_id,
        idempotency_key=payload.idempotency_key,
        status=CommandAckStatus.ACCEPTED,
        received_at=received_at,
        causation_hint=f"approval:{session['approval_id']}",
    )
