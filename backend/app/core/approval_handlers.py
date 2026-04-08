from __future__ import annotations

import json
from typing import Any

from app.contracts.commands import (
    BoardApproveCommand,
    BoardRejectCommand,
    CommandAckEnvelope,
    ElicitationQuestion,
    CommandAckStatus,
    DeliveryStage,
    ElicitationAnswer,
    ModifyConstraintsCommand,
    TicketCreateCommand,
)
from app.contracts.ceo_actions import CEOCreateTicketPayload
from app.core.ceo_execution_presets import (
    PROJECT_INIT_SCOPE_NODE_ID,
    build_ceo_create_ticket_command,
    build_project_init_scope_summary,
)
from app.core.ceo_scheduler import run_ceo_shadow_for_trigger
from app.core.constants import (
    APPROVAL_STATUS_APPROVED,
    APPROVAL_STATUS_MODIFIED_CONSTRAINTS,
    APPROVAL_STATUS_OPEN,
    APPROVAL_STATUS_REJECTED,
    EMPLOYEE_STATE_ACTIVE,
    EVENT_BOARD_DIRECTIVE_RECEIVED,
    EVENT_BOARD_REVIEW_APPROVED,
    EVENT_BOARD_REVIEW_REJECTED,
    EVENT_EMPLOYEE_HIRED,
    EVENT_EMPLOYEE_REPLACED,
    EVENT_TICKET_CREATED,
    NODE_STATUS_BLOCKED_FOR_BOARD_REVIEW,
    TICKET_STATUS_BLOCKED_FOR_BOARD_REVIEW,
)
from app.core.ids import new_prefixed_id
from app.core.output_schemas import (
    CONSENSUS_DOCUMENT_SCHEMA_REF,
    CONSENSUS_DOCUMENT_SCHEMA_VERSION,
    DELIVERY_CLOSEOUT_PACKAGE_SCHEMA_REF,
    DELIVERY_CLOSEOUT_PACKAGE_SCHEMA_VERSION,
    DELIVERY_CHECK_REPORT_SCHEMA_REF,
    DELIVERY_CHECK_REPORT_SCHEMA_VERSION,
    IMPLEMENTATION_BUNDLE_SCHEMA_REF,
    IMPLEMENTATION_BUNDLE_SCHEMA_VERSION,
    UI_MILESTONE_REVIEW_SCHEMA_REF,
    schema_id,
    validate_output_payload,
)
from app.core.persona_profiles import normalize_persona_profiles
from app.core.process_assets import get_ticket_output_process_asset_refs, merge_input_process_asset_refs
from app.core.requirement_elicitation import (
    build_enriched_board_brief_markdown,
    build_requirement_elicitation_markdown,
    build_requirement_elicitation_questionnaire,
    build_requirement_elicitation_review_payload,
    normalize_elicitation_answers,
    summarize_elicitation_answers,
)
from app.core.staffing_containment import contain_employee_active_tickets
from app.core.ticket_handlers import handle_ticket_create
from app.core.time import now_local
from app.core.workflow_auto_advance import auto_advance_workflow_to_next_stop
from app.core.workflow_scope import with_workflow_scope
from app.db.repository import ControlPlaneRepository

SCOPE_APPROVAL_AUTO_ADVANCE_MAX_STEPS = 6
FOLLOWUP_OWNER_ROLE_TO_PROFILE_BY_STAGE = {
    DeliveryStage.BUILD: {
        "frontend_engineer": "frontend_engineer_primary",
        "backend_engineer": "backend_engineer_primary",
        "database_engineer": "database_engineer_primary",
        "platform_sre": "platform_sre_primary",
    },
    DeliveryStage.CHECK: {
        "checker": "checker_primary",
    },
    DeliveryStage.REVIEW: {
        "frontend_engineer": "frontend_engineer_primary",
    },
}
FOLLOWUP_OWNER_ROLE_TO_PROFILE = {
    owner_role: role_profile_ref
    for stage_mapping in FOLLOWUP_OWNER_ROLE_TO_PROFILE_BY_STAGE.values()
    for owner_role, role_profile_ref in stage_mapping.items()
}
SUPPORTED_SCOPE_FOLLOWUP_DELIVERY_STAGES = {
    DeliveryStage.BUILD,
    DeliveryStage.CHECK,
    DeliveryStage.REVIEW,
}
PROJECT_INIT_AUTO_ADVANCE_MAX_STEPS = 6


def _trigger_ceo_shadow_safely(
    repository: ControlPlaneRepository,
    *,
    workflow_id: str,
    approval_id: str,
) -> None:
    try:
        run_ceo_shadow_for_trigger(
            repository,
            workflow_id=workflow_id,
            trigger_type="APPROVAL_RESOLVED",
            trigger_ref=approval_id,
        )
    except Exception:
        return


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


def _validate_open_approval(
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
    if approval["status"] != APPROVAL_STATUS_OPEN:
        return f"Approval is already resolved with status {approval['status']}."
    if approval["review_pack_version"] != review_pack_version:
        return "Review pack outdated. Reload review-room projection."
    if approval["command_target_version"] != command_target_version:
        return "Projection target outdated. Reload review-room projection."
    return None


def _validate_blocked_projection(
    repository: ControlPlaneRepository,
    approval: dict[str, Any],
) -> str | None:
    subject = approval["payload"].get("review_pack", {}).get("subject", {})
    workflow_id = approval["workflow_id"]
    ticket_id = subject.get("source_ticket_id")
    node_id = subject.get("source_node_id")
    if ticket_id is None or node_id is None:
        return None

    ticket_projection = repository.get_current_ticket_projection(ticket_id)
    node_projection = repository.get_current_node_projection(workflow_id, node_id)
    if ticket_projection is None or node_projection is None:
        return "Ticket or node projection for this approval is missing. Reload dashboard state."
    if ticket_projection["status"] != TICKET_STATUS_BLOCKED_FOR_BOARD_REVIEW:
        return "Ticket is not currently blocked for board review."
    if node_projection["status"] != NODE_STATUS_BLOCKED_FOR_BOARD_REVIEW:
        return "Node is not currently blocked for board review."
    if ticket_projection["workflow_id"] != workflow_id or ticket_projection["node_id"] != node_id:
        return "Ticket projection does not match the approval target."
    if node_projection["latest_ticket_id"] != ticket_id:
        return "Node projection no longer points at this approval ticket."
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


def _build_scope_followup_review_request(summary: str) -> dict[str, Any]:
    clean_summary = summary.strip() or "Approved scope follow-up implementation is ready for review."
    return {
        "review_type": "VISUAL_MILESTONE",
        "priority": "high",
        "title": "Review approved scope implementation",
        "subtitle": "The first visual execution pass under the locked scope is ready.",
        "blocking_scope": "NODE_ONLY",
        "trigger_reason": "Board-approved scope follow-up reached a visual milestone review checkpoint.",
        "why_now": "Implementation should stay aligned with the approved scope before more build work piles on.",
        "recommended_action": "APPROVE",
        "recommended_option_id": "option_a",
        "recommendation_summary": clean_summary,
        "options": [
            {
                "option_id": "option_a",
                "label": "Approved scope implementation",
                "summary": clean_summary,
                "artifact_refs": [],
                "pros": ["Keeps implementation aligned with the approved scope lock."],
                "cons": ["Non-critical stretch ideas remain deferred."],
                "risks": ["Visual polish may still need a follow-up rework pass."],
            }
        ],
        "evidence_summary": [],
        "risk_summary": {
            "user_risk": "LOW",
            "engineering_risk": "MEDIUM",
            "schedule_risk": "LOW",
            "budget_risk": "LOW",
        },
        "budget_impact": {
            "tokens_spent_so_far": 0,
            "tokens_if_approved_estimate_range": {"min_tokens": 100, "max_tokens": 250},
            "tokens_if_rework_estimate_range": {"min_tokens": 350, "max_tokens": 700},
            "estimate_confidence": "medium",
            "budget_risk": "LOW",
        },
        "available_actions": ["APPROVE", "REJECT", "MODIFY_CONSTRAINTS"],
        "draft_selected_option_id": "option_a",
        "comment_template": "",
        "inbox_title": "Review approved scope implementation",
        "inbox_summary": "A visual implementation pass is ready under the approved scope.",
        "badges": ["visual", "board_gate", "scope_followup"],
    }


def _build_scope_followup_internal_delivery_review_request(summary: str) -> dict[str, Any]:
    clean_summary = summary.strip() or "Approved scope implementation bundle is ready for internal delivery review."
    return {
        "review_type": "INTERNAL_DELIVERY_REVIEW",
        "priority": "high",
        "title": "Check approved implementation bundle",
        "subtitle": "Internal checker should validate the build output before downstream checking starts.",
        "blocking_scope": "NODE_ONLY",
        "trigger_reason": "Approved scope build bundle reached the internal checker gate.",
        "why_now": "Downstream delivery check should only consume implementation that already passed peer review.",
        "recommended_action": "APPROVE",
        "recommended_option_id": "internal_delivery_ok",
        "recommendation_summary": clean_summary,
        "options": [
            {
                "option_id": "internal_delivery_ok",
                "label": "Pass implementation bundle",
                "summary": clean_summary,
                "artifact_refs": [],
                "pros": ["Lets downstream checking continue without reopening scope."],
                "cons": ["Leaves only non-blocking polish to later steps."],
                "risks": ["Implementation notes may still need follow-up after checking."],
            }
        ],
        "evidence_summary": [
            {
                "evidence_id": "ev_internal_delivery_bundle",
                "source_type": "IMPLEMENTATION_BUNDLE",
                "headline": "Implementation bundle is ready for peer review",
                "summary": clean_summary,
                "source_ref": None,
            }
        ],
        "available_actions": ["APPROVE", "REJECT", "MODIFY_CONSTRAINTS"],
        "draft_selected_option_id": "internal_delivery_ok",
        "comment_template": "",
        "badges": ["internal_delivery", "scope_followup", "build_gate"],
    }


def _build_scope_followup_internal_check_review_request(summary: str) -> dict[str, Any]:
    clean_summary = summary.strip() or "Approved scope delivery check report is ready for internal review."
    return {
        "review_type": "INTERNAL_CHECK_REVIEW",
        "priority": "high",
        "title": "Check approved delivery check report",
        "subtitle": "Internal checker should validate the check report before final board review starts.",
        "blocking_scope": "NODE_ONLY",
        "trigger_reason": "Approved scope delivery check report reached the internal checker gate.",
        "why_now": "Final board review should only consume a delivery check report that already passed peer review.",
        "recommended_action": "APPROVE",
        "recommended_option_id": "internal_check_ok",
        "recommendation_summary": clean_summary,
        "options": [
            {
                "option_id": "internal_check_ok",
                "label": "Pass check report",
                "summary": clean_summary,
                "artifact_refs": [],
                "pros": ["Lets final review start on already-verified check evidence."],
                "cons": ["Leaves only non-blocking polish to later steps."],
                "risks": ["Weakly justified check notes may still need a real rework pass."],
            }
        ],
        "evidence_summary": [
            {
                "evidence_id": "ev_internal_check_report",
                "source_type": "DELIVERY_CHECK_REPORT",
                "headline": "Delivery check report is ready for peer review",
                "summary": clean_summary,
                "source_ref": None,
            }
        ],
        "available_actions": ["APPROVE", "REJECT", "MODIFY_CONSTRAINTS"],
        "draft_selected_option_id": "internal_check_ok",
        "comment_template": "",
        "badges": ["internal_check", "scope_followup", "check_gate"],
    }


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
    source_ticket_id = f"tkt_{workflow_id}_scope_decision"
    source_node_id = PROJECT_INIT_SCOPE_NODE_ID
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
    command = build_ceo_create_ticket_command(
        workflow=workflow,
        payload=CEOCreateTicketPayload(
            workflow_id=workflow_id,
            node_id=PROJECT_INIT_SCOPE_NODE_ID,
            role_profile_ref="ui_designer_primary",
            output_schema_ref="consensus_document",
            summary=build_project_init_scope_summary(str(workflow.get("north_star_goal") or workflow.get("title") or "")),
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


def _scope_followup_expected_artifact_ref(ticket_id: str, delivery_stage: DeliveryStage) -> str | None:
    if delivery_stage == DeliveryStage.BUILD:
        return f"art://runtime/{ticket_id}/implementation-bundle.json"
    if delivery_stage == DeliveryStage.CHECK:
        return f"art://runtime/{ticket_id}/delivery-check-report.json"
    return None


def _build_scope_followup_allowed_write_set(ticket_id: str, delivery_stage: DeliveryStage) -> list[str]:
    if delivery_stage == DeliveryStage.BUILD:
        return [f"artifacts/ui/scope-followups/{ticket_id}/*"]
    if delivery_stage == DeliveryStage.CHECK:
        return [f"reports/check/{ticket_id}/*"]
    return [
        f"artifacts/ui/scope-followups/{ticket_id}/*",
        f"reports/review/{ticket_id}/*",
    ]


def _scope_followup_output_contract(delivery_stage: DeliveryStage) -> tuple[str, int]:
    if delivery_stage == DeliveryStage.BUILD:
        return IMPLEMENTATION_BUNDLE_SCHEMA_REF, IMPLEMENTATION_BUNDLE_SCHEMA_VERSION
    if delivery_stage == DeliveryStage.CHECK:
        return DELIVERY_CHECK_REPORT_SCHEMA_REF, DELIVERY_CHECK_REPORT_SCHEMA_VERSION
    return "ui_milestone_review", 1


def _scope_followup_priority(delivery_stage: DeliveryStage) -> str:
    if delivery_stage == DeliveryStage.REVIEW:
        return "medium"
    return "high"


def _scope_followup_allowed_tools(delivery_stage: DeliveryStage) -> list[str]:
    if delivery_stage == DeliveryStage.CHECK:
        return ["read_artifact", "write_artifact"]
    return ["read_artifact", "write_artifact", "image_gen"]


def _scope_followup_context_keywords(delivery_stage: DeliveryStage) -> list[str]:
    if delivery_stage == DeliveryStage.BUILD:
        return ["approved scope", "implementation", "build"]
    if delivery_stage == DeliveryStage.CHECK:
        return ["approved scope", "internal check", "qa"]
    return ["approved scope", "review package", "visual"]


def _scope_followup_acceptance_criteria(summary: str, delivery_stage: DeliveryStage) -> list[str]:
    if delivery_stage == DeliveryStage.BUILD:
        return [
            f"Must implement this approved scope follow-up: {summary}",
            "Must stay inside the locked scope from the approved consensus document.",
            "Must produce a structured implementation bundle.",
        ]
    if delivery_stage == DeliveryStage.CHECK:
        return [
            f"Must check this approved scope follow-up: {summary}",
            "Must verify the implementation bundle still stays inside the locked scope.",
            "Must produce a structured delivery check report.",
        ]
    return [
        f"Must prepare this approved scope review package: {summary}",
        "Must stay inside the locked scope from the approved consensus document.",
        "Must produce a visual milestone review package.",
    ]


def _meeting_decision_guidance(consensus_payload: dict[str, Any]) -> tuple[list[str], list[str]]:
    decision_record = consensus_payload.get("decision_record")
    if not isinstance(decision_record, dict):
        return [], []

    decision = str(decision_record.get("decision") or "").strip()
    consequences = [
        str(item).strip()
        for item in (decision_record.get("consequences") or [])
        if str(item).strip()
    ]
    semantic_queries = [item for item in [decision, *consequences] if item]
    acceptance_criteria = (
        [f"Must follow the locked meeting ADR decision: {decision}"] if decision else []
    ) + [f"Must respect this locked meeting ADR consequence: {item}" for item in consequences]
    return semantic_queries, acceptance_criteria


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
        constraints_ref="approved_scope_followup_closeout",
        input_artifact_refs=input_artifact_refs,
        input_process_asset_refs=input_process_asset_refs,
        context_query_plan={
            "keywords": ["approved final review", "delivery closeout", "handoff"],
            "semantic_queries": [closeout_summary],
            "max_context_tokens": 3000,
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
        allowed_write_set=[f"reports/closeout/{closeout_ticket_id}/*"],
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


def _load_scope_consensus_payload(
    repository: ControlPlaneRepository,
    connection,
    *,
    approval: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    review_pack = approval["payload"].get("review_pack") or {}
    evidence_summary = review_pack.get("evidence_summary") or []
    artifact_ref = str((evidence_summary[0] or {}).get("source_ref") or "").strip() if evidence_summary else ""
    if not artifact_ref:
        raise ValueError("Scope review is missing the approved consensus artifact reference.")

    artifact = repository.get_artifact_by_ref(artifact_ref, connection=connection)
    if artifact is None:
        raise ValueError("Approved consensus artifact record is missing.")
    if repository.artifact_store is None:
        raise ValueError("Artifact store is required to read the approved consensus artifact.")

    try:
        body = repository.artifact_store.read_bytes(
            artifact.get("storage_relpath"),
            storage_object_key=artifact.get("storage_object_key"),
        )
    except Exception as exc:  # pragma: no cover - exact backend failure varies
        raise ValueError("Approved consensus artifact could not be read.") from exc

    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Approved consensus artifact is not valid JSON.") from exc
    if not isinstance(payload, dict):
        raise ValueError("Approved consensus artifact JSON root must be an object.")

    validate_output_payload(
        schema_ref=CONSENSUS_DOCUMENT_SCHEMA_REF,
        schema_version=CONSENSUS_DOCUMENT_SCHEMA_VERSION,
        submitted_schema_version=schema_id(
            CONSENSUS_DOCUMENT_SCHEMA_REF,
            CONSENSUS_DOCUMENT_SCHEMA_VERSION,
        ),
        payload=payload,
    )
    return artifact_ref, payload


def _build_scope_followup_ticket_payloads(
    repository: ControlPlaneRepository,
    connection,
    *,
    approval: dict[str, Any],
) -> list[dict[str, Any]]:
    review_pack = approval["payload"].get("review_pack") or {}
    subject = review_pack.get("subject") or {}
    source_ticket_id = str(subject.get("source_ticket_id") or "").strip()
    if not source_ticket_id:
        return []

    created_spec = repository.get_latest_ticket_created_payload(connection, source_ticket_id)
    if created_spec is None:
        raise ValueError("Approved scope ticket spec could not be loaded.")
    maker_checker_context = created_spec.get("maker_checker_context") or {}
    maker_ticket_id = str(maker_checker_context.get("maker_ticket_id") or "").strip()
    if (
        str(created_spec.get("output_schema_ref") or "") != CONSENSUS_DOCUMENT_SCHEMA_REF
        and maker_ticket_id
    ):
        maker_created_spec = repository.get_latest_ticket_created_payload(connection, maker_ticket_id)
        if maker_created_spec is None:
            raise ValueError("Approved scope maker ticket spec could not be loaded.")
        created_spec = maker_created_spec
        source_ticket_id = maker_ticket_id
    if str(created_spec.get("output_schema_ref") or "") != CONSENSUS_DOCUMENT_SCHEMA_REF:
        return []

    consensus_artifact_ref, consensus_payload = _load_scope_consensus_payload(
        repository,
        connection,
        approval=approval,
    )
    workflow = repository.get_workflow_projection(approval["workflow_id"], connection=connection)
    source_process_asset_refs = get_ticket_output_process_asset_refs(
        repository,
        connection,
        source_ticket_id,
    )
    input_artifact_refs = _dedupe_artifact_refs(
        [consensus_artifact_ref] + list(created_spec.get("input_artifact_refs") or [])
    )
    input_process_asset_refs = merge_input_process_asset_refs(
        existing_process_asset_refs=list(created_spec.get("input_process_asset_refs") or []),
        artifact_refs=input_artifact_refs,
        produced_process_asset_refs=source_process_asset_refs,
    )
    followup_items = list(consensus_payload.get("followup_tickets") or [])
    seen_ticket_ids: set[str] = set()
    seen_node_ids: set[str] = set()
    ticket_payloads: list[dict[str, Any]] = []
    prior_ticket_id = source_ticket_id
    chained_artifact_refs: list[str] = []
    extra_semantic_queries: list[str] = []
    extra_acceptance_criteria: list[str] = []
    if approval["approval_type"] == "MEETING_ESCALATION":
        extra_semantic_queries, extra_acceptance_criteria = _meeting_decision_guidance(consensus_payload)

    for raw_followup in followup_items:
        followup = dict(raw_followup)
        followup_ticket_id = str(followup.get("ticket_id") or "").strip()
        owner_role = str(followup.get("owner_role") or "").strip()
        followup_summary = str(followup.get("summary") or "").strip()
        delivery_stage = DeliveryStage(
            str(followup.get("delivery_stage") or DeliveryStage.REVIEW.value).strip()
        )
        if delivery_stage not in SUPPORTED_SCOPE_FOLLOWUP_DELIVERY_STAGES:
            raise ValueError(
                f"Unsupported approved follow-up delivery_stage '{delivery_stage.value}'."
            )

        if followup_ticket_id in seen_ticket_ids:
            raise ValueError(
                f"Approved consensus contains duplicate follow-up ticket_id '{followup_ticket_id}'."
            )
        seen_ticket_ids.add(followup_ticket_id)

        role_profile_ref = FOLLOWUP_OWNER_ROLE_TO_PROFILE_BY_STAGE.get(delivery_stage, {}).get(owner_role)
        if role_profile_ref is None:
            raise ValueError(f"Unsupported approved follow-up owner_role '{owner_role}'.")
        if repository.get_current_ticket_projection(followup_ticket_id, connection=connection) is not None:
            raise ValueError(f"Follow-up ticket {followup_ticket_id} already exists in projection state.")

        node_id = f"node_followup_{followup_ticket_id.removeprefix('tkt_')}"
        if node_id in seen_node_ids:
            raise ValueError(f"Approved consensus contains duplicate follow-up node_id '{node_id}'.")
        seen_node_ids.add(node_id)
        if repository.get_current_node_projection(approval["workflow_id"], node_id, connection=connection) is not None:
            raise ValueError(f"Follow-up node {node_id} already exists in projection state.")

        output_schema_ref, output_schema_version = _scope_followup_output_contract(delivery_stage)
        ticket_command = TicketCreateCommand(
            ticket_id=followup_ticket_id,
            workflow_id=approval["workflow_id"],
            node_id=node_id,
            parent_ticket_id=prior_ticket_id,
            attempt_no=1,
            role_profile_ref=role_profile_ref,
            constraints_ref=f"approved_scope_followup_{delivery_stage.value.lower()}",
            input_artifact_refs=_dedupe_artifact_refs(input_artifact_refs + chained_artifact_refs),
            input_process_asset_refs=merge_input_process_asset_refs(
                existing_process_asset_refs=input_process_asset_refs,
                artifact_refs=chained_artifact_refs,
            ),
            context_query_plan={
                "keywords": _scope_followup_context_keywords(delivery_stage),
                "semantic_queries": [followup_summary, *extra_semantic_queries],
                "max_context_tokens": 3000,
            },
            acceptance_criteria=[
                *_scope_followup_acceptance_criteria(followup_summary, delivery_stage),
                *extra_acceptance_criteria,
            ],
            output_schema_ref=output_schema_ref,
            output_schema_version=output_schema_version,
            allowed_tools=_scope_followup_allowed_tools(delivery_stage),
            allowed_write_set=_build_scope_followup_allowed_write_set(
                followup_ticket_id,
                delivery_stage,
            ),
            retry_budget=1,
            priority=_scope_followup_priority(delivery_stage),
            timeout_sla_sec=1800,
            deadline_at=created_spec.get("deadline_at"),
            delivery_stage=delivery_stage,
            auto_review_request=(
                _build_scope_followup_internal_delivery_review_request(followup_summary)
                if delivery_stage == DeliveryStage.BUILD
                else _build_scope_followup_internal_check_review_request(followup_summary)
                if delivery_stage == DeliveryStage.CHECK
                else _build_scope_followup_review_request(followup_summary)
                if delivery_stage == DeliveryStage.REVIEW
                else None
            ),
            escalation_policy={
                "on_timeout": "retry",
                "on_schema_error": "retry",
                "on_repeat_failure": "escalate_ceo",
            },
            idempotency_key=(
                f"board-approved-scope-followup:{approval['approval_id']}:{followup_ticket_id}"
            ),
        )
        ticket_payloads.append(ticket_command.model_dump(mode="json"))
        prior_ticket_id = followup_ticket_id
        expected_artifact_ref = _scope_followup_expected_artifact_ref(followup_ticket_id, delivery_stage)
        if expected_artifact_ref is not None:
            chained_artifact_refs.append(expected_artifact_ref)

    return ticket_payloads


def _insert_scope_followup_ticket_created_event(
    repository: ControlPlaneRepository,
    connection,
    *,
    command_id: str,
    occurred_at,
    workflow_id: str,
    idempotency_key: str,
    ticket_payload: dict[str, Any],
) -> str:
    event_row = repository.insert_event(
        connection,
        event_type=EVENT_TICKET_CREATED,
        actor_type="system",
        actor_id="board-followup-router",
        workflow_id=workflow_id,
        idempotency_key=idempotency_key,
        causation_id=command_id,
        correlation_id=workflow_id,
        payload=with_workflow_scope(
            ticket_payload,
            repository.get_workflow_projection(workflow_id, connection=connection),
        ),
        occurred_at=occurred_at,
    )
    if event_row is None:
        raise RuntimeError("Scope follow-up ticket creation idempotency conflict.")
    return str(ticket_payload["ticket_id"])
def handle_board_approve(
    repository: ControlPlaneRepository,
    payload: BoardApproveCommand,
) -> CommandAckEnvelope:
    command_id = new_prefixed_id("cmd")
    received_at = now_local()
    created_followup_ticket_ids: list[str] = []
    kickoff_causation_hint: str | None = None
    kickoff_artifact_refs: list[str] = []
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
        followup_ticket_payloads: list[dict[str, Any]] = []
        normalized_elicitation_answers: list[ElicitationAnswer] = []
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
        else:
            try:
                followup_ticket_payloads = _build_scope_followup_ticket_payloads(
                    repository,
                    connection,
                    approval=approval,
                )
            except ValueError as exc:
                return _rejected_ack(
                    command_id=command_id,
                    idempotency_key=payload.idempotency_key,
                    received_at=received_at,
                    reason=str(exc),
                    causation_hint=f"approval:{payload.approval_id}",
                )

        event_row = repository.insert_event(
            connection,
            event_type=EVENT_BOARD_REVIEW_APPROVED,
            actor_type="board",
            actor_id="board",
            workflow_id=approval["workflow_id"],
            idempotency_key=payload.idempotency_key,
            causation_id=command_id,
            correlation_id=approval["workflow_id"],
            payload={
                "approval_id": payload.approval_id,
                "review_pack_id": payload.review_pack_id,
                "node_id": subject.get("source_node_id"),
                "ticket_id": subject.get("source_ticket_id"),
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
            resolved_by="board",
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
            closeout_ticket_payload = _build_post_review_closeout_ticket_payload(
                repository,
                connection,
                approval=repository.get_approval_by_id(connection, payload.approval_id) or approval,
                selected_option_id=payload.selected_option_id,
            )
            for index, followup_ticket_payload in enumerate(followup_ticket_payloads):
                created_followup_ticket_ids.append(
                    _insert_scope_followup_ticket_created_event(
                        repository,
                        connection,
                        command_id=command_id,
                        occurred_at=received_at,
                        workflow_id=approval["workflow_id"],
                        idempotency_key=f"{payload.idempotency_key}:scope-followup-create:{index}",
                        ticket_payload=followup_ticket_payload,
                    )
                )
            if closeout_ticket_payload is not None:
                created_followup_ticket_ids.append(
                    _insert_scope_followup_ticket_created_event(
                        repository,
                        connection,
                        command_id=command_id,
                        occurred_at=received_at,
                        workflow_id=approval["workflow_id"],
                        idempotency_key=f"{payload.idempotency_key}:closeout-create",
                        ticket_payload=closeout_ticket_payload,
                    )
                )
            repository.refresh_projections(connection)

    if approval["approval_type"] == "REQUIREMENT_ELICITATION":
        kickoff_causation_hint = _kickoff_scope_after_requirement_elicitation(
            repository,
            workflow_id=approval["workflow_id"],
            artifact_refs=kickoff_artifact_refs,
            idempotency_key_prefix=payload.idempotency_key,
        )
        created_followup_ticket_ids.append(f"tkt_{approval['workflow_id']}_scope_decision")

    if approval["approval_type"] != "REQUIREMENT_ELICITATION":
        auto_advance_workflow_to_next_stop(
            repository,
            workflow_id=approval["workflow_id"],
            idempotency_key_prefix=f"{payload.idempotency_key}:workflow-auto-advance",
            max_steps=SCOPE_APPROVAL_AUTO_ADVANCE_MAX_STEPS,
            max_dispatches=1,
        )

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
                "node_id": subject.get("source_node_id"),
                "ticket_id": subject.get("source_ticket_id"),
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
        repository.refresh_projections(connection)

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

        subject = approval["payload"].get("review_pack", {}).get("subject", {})
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
                "node_id": subject.get("source_node_id"),
                "ticket_id": subject.get("source_ticket_id"),
                "board_comment": payload.board_comment,
                "constraint_patch": payload.constraint_patch.model_dump(mode="json"),
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
