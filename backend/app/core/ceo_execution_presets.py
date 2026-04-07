from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.contracts.ceo_actions import CEOCreateTicketPayload
from app.contracts.commands import DeliveryStage, TicketCreateCommand
from app.core.execution_targets import infer_execution_contract_payload
from app.core.ids import new_prefixed_id
from app.core.output_schemas import (
    CONSENSUS_DOCUMENT_SCHEMA_REF,
    CONSENSUS_DOCUMENT_SCHEMA_VERSION,
    DELIVERY_CHECK_REPORT_SCHEMA_REF,
    DELIVERY_CHECK_REPORT_SCHEMA_VERSION,
    DELIVERY_CLOSEOUT_PACKAGE_SCHEMA_REF,
    DELIVERY_CLOSEOUT_PACKAGE_SCHEMA_VERSION,
    IMPLEMENTATION_BUNDLE_SCHEMA_REF,
    IMPLEMENTATION_BUNDLE_SCHEMA_VERSION,
    UI_MILESTONE_REVIEW_SCHEMA_REF,
    UI_MILESTONE_REVIEW_SCHEMA_VERSION,
)


@dataclass(frozen=True)
class CEOCreateTicketPreset:
    role_profile_ref: str
    output_schema_ref: str
    output_schema_version: int
    constraints_ref: str
    priority: str
    delivery_stage: DeliveryStage | None


_CREATE_TICKET_PRESETS: dict[tuple[str, str], CEOCreateTicketPreset] = {
    ("ui_designer_primary", CONSENSUS_DOCUMENT_SCHEMA_REF): CEOCreateTicketPreset(
        role_profile_ref="ui_designer_primary",
        output_schema_ref=CONSENSUS_DOCUMENT_SCHEMA_REF,
        output_schema_version=CONSENSUS_DOCUMENT_SCHEMA_VERSION,
        constraints_ref="project_init_scope_lock",
        priority="high",
        delivery_stage=None,
    ),
    ("frontend_engineer_primary", IMPLEMENTATION_BUNDLE_SCHEMA_REF): CEOCreateTicketPreset(
        role_profile_ref="frontend_engineer_primary",
        output_schema_ref=IMPLEMENTATION_BUNDLE_SCHEMA_REF,
        output_schema_version=IMPLEMENTATION_BUNDLE_SCHEMA_VERSION,
        constraints_ref="approved_scope_followup_build",
        priority="high",
        delivery_stage=DeliveryStage.BUILD,
    ),
    ("checker_primary", DELIVERY_CHECK_REPORT_SCHEMA_REF): CEOCreateTicketPreset(
        role_profile_ref="checker_primary",
        output_schema_ref=DELIVERY_CHECK_REPORT_SCHEMA_REF,
        output_schema_version=DELIVERY_CHECK_REPORT_SCHEMA_VERSION,
        constraints_ref="approved_scope_followup_check",
        priority="high",
        delivery_stage=DeliveryStage.CHECK,
    ),
    ("frontend_engineer_primary", UI_MILESTONE_REVIEW_SCHEMA_REF): CEOCreateTicketPreset(
        role_profile_ref="frontend_engineer_primary",
        output_schema_ref=UI_MILESTONE_REVIEW_SCHEMA_REF,
        output_schema_version=UI_MILESTONE_REVIEW_SCHEMA_VERSION,
        constraints_ref="approved_scope_followup_review",
        priority="medium",
        delivery_stage=DeliveryStage.REVIEW,
    ),
    ("frontend_engineer_primary", DELIVERY_CLOSEOUT_PACKAGE_SCHEMA_REF): CEOCreateTicketPreset(
        role_profile_ref="frontend_engineer_primary",
        output_schema_ref=DELIVERY_CLOSEOUT_PACKAGE_SCHEMA_REF,
        output_schema_version=DELIVERY_CLOSEOUT_PACKAGE_SCHEMA_VERSION,
        constraints_ref="approved_scope_followup_closeout",
        priority="high",
        delivery_stage=DeliveryStage.CLOSEOUT,
    ),
}


PROJECT_INIT_SCOPE_NODE_ID = "node_scope_decision"


def build_project_init_scope_ticket_id(workflow_id: str) -> str:
    return f"tkt_{workflow_id}_scope_decision"


def build_project_init_scope_summary(north_star_goal: str) -> str:
    clean_goal = north_star_goal.strip() or "the current workflow"
    return (
        "Prepare the kickoff consensus report and the first batch of follow-up ticket outlines for "
        f"{clean_goal}."
    )


def build_project_init_brief_artifact_ref(workflow_id: str) -> str:
    return f"art://project-init/{workflow_id}/board-brief.md"


def is_project_init_scope_preset(*, role_profile_ref: str, output_schema_ref: str) -> bool:
    return role_profile_ref == "ui_designer_primary" and output_schema_ref == CONSENSUS_DOCUMENT_SCHEMA_REF


def supports_ceo_create_ticket_preset(*, role_profile_ref: str, output_schema_ref: str) -> bool:
    return (role_profile_ref, output_schema_ref) in _CREATE_TICKET_PRESETS


def _build_project_init_auto_review_request(ticket_id: str) -> dict[str, Any]:
    return {
        "review_type": "MEETING_ESCALATION",
        "priority": "high",
        "title": "Review scope decision consensus",
        "subtitle": "Initial scope decision is ready for board lock-in.",
        "blocking_scope": "WORKFLOW",
        "trigger_reason": "Project init produced the first scope decision that needs explicit board confirmation.",
        "why_now": "Execution should not widen before the first scope lock is approved.",
        "recommended_action": "APPROVE",
        "recommended_option_id": "consensus_scope_lock",
        "recommendation_summary": "The narrowest scope that still ships the workflow is ready for board review.",
        "options": [
            {
                "option_id": "consensus_scope_lock",
                "label": "Lock consensus scope",
                "summary": "Proceed with the converged scope and follow-up tickets.",
                "artifact_refs": [],
                "pros": ["Keeps delivery scope stable"],
                "cons": ["Defers non-critical stretch ideas"],
                "risks": ["Some polish moves slip to later rounds"],
            }
        ],
        "evidence_summary": [
            {
                "evidence_id": "ev_scope_consensus",
                "source_type": "CONSENSUS_DOCUMENT",
                "headline": "Generated scope consensus document",
                "summary": "The first scope decision is ready for board review.",
                "source_ref": None,
            }
        ],
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
        "draft_selected_option_id": "consensus_scope_lock",
        "comment_template": "",
        "inbox_title": "Review scope decision consensus",
        "inbox_summary": "A consensus document is ready for board review.",
        "badges": ["meeting", "board_gate", "scope"],
        "developer_inspector_refs": {
            "compiled_context_bundle_ref": f"ctx://compile/{ticket_id}",
            "compile_manifest_ref": f"manifest://compile/{ticket_id}",
            "rendered_execution_payload_ref": f"render://compile/{ticket_id}",
        },
    }


def _build_consensus_review_request(summary: str) -> dict[str, Any]:
    clean_summary = summary.strip() or "A scope consensus document is ready for board review."
    return {
        "review_type": "MEETING_ESCALATION",
        "priority": "high",
        "title": "Review scope decision consensus",
        "subtitle": "CEO proposed a scope decision that needs board lock-in.",
        "blocking_scope": "WORKFLOW",
        "trigger_reason": "CEO proposed a new scope consensus ticket on the current mainline path.",
        "why_now": "Execution should not widen before the proposed scope lock is approved.",
        "recommended_action": "APPROVE",
        "recommended_option_id": "consensus_scope_lock",
        "recommendation_summary": clean_summary,
        "options": [
            {
                "option_id": "consensus_scope_lock",
                "label": "Lock proposed scope",
                "summary": clean_summary,
                "artifact_refs": [],
                "pros": ["Keeps delivery scope explicit and reviewable."],
                "cons": ["Defers non-critical stretch ideas."],
                "risks": ["A weak scope split could still need board correction."],
            }
        ],
        "evidence_summary": [
            {
                "evidence_id": "ev_scope_consensus",
                "source_type": "CONSENSUS_DOCUMENT",
                "headline": "Generated scope consensus document",
                "summary": clean_summary,
                "source_ref": None,
            }
        ],
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
        "draft_selected_option_id": "consensus_scope_lock",
        "comment_template": "",
        "inbox_title": "Review scope decision consensus",
        "inbox_summary": "A consensus document is ready for board review.",
        "badges": ["meeting", "board_gate", "scope"],
    }


def _build_internal_delivery_review_request(summary: str) -> dict[str, Any]:
    clean_summary = summary.strip() or "Implementation bundle is ready for internal delivery review."
    return {
        "review_type": "INTERNAL_DELIVERY_REVIEW",
        "priority": "high",
        "title": "Check approved implementation bundle",
        "subtitle": "Internal checker should validate the build output before downstream checking starts.",
        "blocking_scope": "NODE_ONLY",
        "trigger_reason": "Build bundle reached the internal checker gate.",
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


def _build_internal_check_review_request(summary: str) -> dict[str, Any]:
    clean_summary = summary.strip() or "Delivery check report is ready for internal review."
    return {
        "review_type": "INTERNAL_CHECK_REVIEW",
        "priority": "high",
        "title": "Check approved delivery check report",
        "subtitle": "Internal checker should validate the check report before final board review starts.",
        "blocking_scope": "NODE_ONLY",
        "trigger_reason": "Delivery check report reached the internal checker gate.",
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


def _build_visual_review_request(summary: str) -> dict[str, Any]:
    clean_summary = summary.strip() or "Implementation is ready for final board review."
    return {
        "review_type": "VISUAL_MILESTONE",
        "priority": "high",
        "title": "Review approved scope implementation",
        "subtitle": "The first visual execution pass under the locked scope is ready.",
        "blocking_scope": "NODE_ONLY",
        "trigger_reason": "Implementation reached a visual milestone review checkpoint.",
        "why_now": "Implementation should stay aligned before more build work piles on.",
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


def _build_closeout_review_request(summary: str) -> dict[str, Any]:
    clean_summary = summary.strip() or "Delivery closeout package is ready for final internal review."
    return {
        "review_type": "INTERNAL_CLOSEOUT_REVIEW",
        "priority": "high",
        "title": "Check delivery closeout package",
        "subtitle": "Internal checker should validate final evidence, handoff notes, and documentation sync before the workflow closes.",
        "blocking_scope": "NODE_ONLY",
        "trigger_reason": "Final delivery package reached the closeout checker gate.",
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


def _allowed_tools_for_preset(preset: CEOCreateTicketPreset) -> list[str]:
    if preset.output_schema_ref in {
        CONSENSUS_DOCUMENT_SCHEMA_REF,
        DELIVERY_CHECK_REPORT_SCHEMA_REF,
        DELIVERY_CLOSEOUT_PACKAGE_SCHEMA_REF,
    }:
        return ["read_artifact", "write_artifact"]
    return ["read_artifact", "write_artifact", "image_gen"]


def _allowed_write_set_for_preset(ticket_id: str, preset: CEOCreateTicketPreset) -> list[str]:
    if preset.output_schema_ref == CONSENSUS_DOCUMENT_SCHEMA_REF:
        return ["reports/meeting/*"]
    if preset.output_schema_ref == IMPLEMENTATION_BUNDLE_SCHEMA_REF:
        return [f"artifacts/ui/scope-followups/{ticket_id}/*"]
    if preset.output_schema_ref == DELIVERY_CHECK_REPORT_SCHEMA_REF:
        return [f"reports/check/{ticket_id}/*"]
    if preset.output_schema_ref == DELIVERY_CLOSEOUT_PACKAGE_SCHEMA_REF:
        return [f"reports/closeout/{ticket_id}/*"]
    return [
        f"artifacts/ui/scope-followups/{ticket_id}/*",
        f"reports/review/{ticket_id}/*",
    ]


def _context_keywords_for_preset(preset: CEOCreateTicketPreset) -> list[str]:
    if preset.output_schema_ref == CONSENSUS_DOCUMENT_SCHEMA_REF:
        return ["scope", "constraints", "board review"]
    if preset.output_schema_ref == IMPLEMENTATION_BUNDLE_SCHEMA_REF:
        return ["approved scope", "implementation", "build"]
    if preset.output_schema_ref == DELIVERY_CHECK_REPORT_SCHEMA_REF:
        return ["approved scope", "internal check", "qa"]
    if preset.output_schema_ref == DELIVERY_CLOSEOUT_PACKAGE_SCHEMA_REF:
        return ["approved final review", "delivery closeout", "handoff"]
    return ["approved scope", "review package", "visual"]


def _acceptance_criteria_for_preset(summary: str, preset: CEOCreateTicketPreset) -> list[str]:
    clean_summary = summary.strip() or "Prepare the next mainline deliverable."
    if preset.output_schema_ref == CONSENSUS_DOCUMENT_SCHEMA_REF:
        return [
            f"Must produce a scope consensus for this delivery need: {clean_summary}",
            "Must keep the proposal explicit, reviewable, and auditable.",
            "Must produce a structured consensus document.",
        ]
    if preset.output_schema_ref == IMPLEMENTATION_BUNDLE_SCHEMA_REF:
        return [
            f"Must implement this approved scope follow-up: {clean_summary}",
            "Must stay inside the locked scope from the approved consensus document.",
            "Must produce a structured implementation bundle.",
        ]
    if preset.output_schema_ref == DELIVERY_CHECK_REPORT_SCHEMA_REF:
        return [
            f"Must check this approved scope follow-up: {clean_summary}",
            "Must verify the implementation bundle still stays inside the locked scope.",
            "Must produce a structured delivery check report.",
        ]
    if preset.output_schema_ref == DELIVERY_CLOSEOUT_PACKAGE_SCHEMA_REF:
        return [
            f"Must capture the approved final delivery choice: {clean_summary}",
            "Must gather the final delivery artifact references chosen in board review.",
            "Must provide minimal handoff notes for the approved delivery package.",
            "Must report documentation updates, or explicitly mark affected docs as no change required.",
            "Must stay inside the already approved scope.",
        ]
    return [
        f"Must prepare this approved scope review package: {clean_summary}",
        "Must stay inside the locked scope from the approved consensus document.",
        "Must produce a visual milestone review package.",
    ]


def _review_request_for_preset(summary: str, preset: CEOCreateTicketPreset) -> dict[str, Any] | None:
    if preset.output_schema_ref == CONSENSUS_DOCUMENT_SCHEMA_REF:
        return _build_consensus_review_request(summary)
    if preset.output_schema_ref == IMPLEMENTATION_BUNDLE_SCHEMA_REF:
        return _build_internal_delivery_review_request(summary)
    if preset.output_schema_ref == DELIVERY_CHECK_REPORT_SCHEMA_REF:
        return _build_internal_check_review_request(summary)
    if preset.output_schema_ref == DELIVERY_CLOSEOUT_PACKAGE_SCHEMA_REF:
        return _build_closeout_review_request(summary)
    if preset.output_schema_ref == UI_MILESTONE_REVIEW_SCHEMA_REF:
        return _build_visual_review_request(summary)
    return None


def build_ceo_create_ticket_command(
    *,
    workflow: dict[str, Any],
    payload: CEOCreateTicketPayload,
) -> TicketCreateCommand:
    preset = _CREATE_TICKET_PRESETS[(payload.role_profile_ref, payload.output_schema_ref)]
    is_project_init_scope = is_project_init_scope_preset(
        role_profile_ref=payload.role_profile_ref,
        output_schema_ref=payload.output_schema_ref,
    )
    ticket_id = (
        build_project_init_scope_ticket_id(payload.workflow_id)
        if is_project_init_scope
        else new_prefixed_id("tkt")
    )
    node_id = PROJECT_INIT_SCOPE_NODE_ID if is_project_init_scope else payload.node_id
    input_artifact_refs = (
        [build_project_init_brief_artifact_ref(payload.workflow_id)]
        if is_project_init_scope
        else []
    )
    semantic_queries = [
        str(workflow.get("north_star_goal") or payload.summary).strip() or payload.summary
    ]
    return TicketCreateCommand(
        ticket_id=ticket_id,
        workflow_id=payload.workflow_id,
        node_id=node_id,
        parent_ticket_id=payload.parent_ticket_id,
        attempt_no=1,
        role_profile_ref=preset.role_profile_ref,
        constraints_ref=preset.constraints_ref,
        input_artifact_refs=input_artifact_refs,
        context_query_plan={
            "keywords": (
                ["scope", "constraints", "board review"]
                if is_project_init_scope
                else _context_keywords_for_preset(preset)
            ),
            "semantic_queries": semantic_queries,
            "max_context_tokens": 3000,
        },
        acceptance_criteria=(
            [
                "Must produce a consensus document",
                "Must include follow-up tickets",
            ]
            if is_project_init_scope
            else _acceptance_criteria_for_preset(payload.summary, preset)
        ),
        output_schema_ref=preset.output_schema_ref,
        output_schema_version=preset.output_schema_version,
        allowed_tools=_allowed_tools_for_preset(preset),
        allowed_write_set=_allowed_write_set_for_preset(ticket_id, preset),
        retry_budget=1,
        priority=preset.priority,
        timeout_sla_sec=1800,
        deadline_at=workflow.get("deadline_at"),
        delivery_stage=preset.delivery_stage,
        execution_contract=(
            payload.execution_contract
            if payload.execution_contract is not None
            else infer_execution_contract_payload(
                role_profile_ref=preset.role_profile_ref,
                output_schema_ref=preset.output_schema_ref,
            )
        ),
        dispatch_intent=payload.dispatch_intent,
        auto_review_request=(
            _build_project_init_auto_review_request(ticket_id)
            if is_project_init_scope
            else _review_request_for_preset(payload.summary, preset)
        ),
        escalation_policy={
            "on_timeout": "retry",
            "on_schema_error": "retry",
            "on_repeat_failure": "escalate_ceo",
        },
        idempotency_key=f"ceo-create-ticket:{payload.workflow_id}:{node_id}",
    )
