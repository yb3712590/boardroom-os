from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from app.config import get_settings
from app.contracts.ceo_actions import CEOCreateTicketPayload
from app.contracts.commands import DeliveryStage, TicketCreateCommand
from app.core.execution_targets import infer_execution_contract_payload
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
    DELIVERY_CHECK_REPORT_SCHEMA_REF,
    DELIVERY_CHECK_REPORT_SCHEMA_VERSION,
    DELIVERY_CLOSEOUT_PACKAGE_SCHEMA_REF,
    DELIVERY_CLOSEOUT_PACKAGE_SCHEMA_VERSION,
    GOVERNANCE_DOCUMENT_SCHEMA_REFS,
    MILESTONE_PLAN_SCHEMA_REF,
    MILESTONE_PLAN_SCHEMA_VERSION,
    SOURCE_CODE_DELIVERY_SCHEMA_REF,
    SOURCE_CODE_DELIVERY_SCHEMA_VERSION,
    TECHNOLOGY_DECISION_SCHEMA_REF,
    TECHNOLOGY_DECISION_SCHEMA_VERSION,
    UI_MILESTONE_REVIEW_SCHEMA_REF,
    UI_MILESTONE_REVIEW_SCHEMA_VERSION,
)
from app.core.process_assets import get_ticket_output_process_asset_refs

if TYPE_CHECKING:
    from app.db.repository import ControlPlaneRepository


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
    ("frontend_engineer_primary", SOURCE_CODE_DELIVERY_SCHEMA_REF): CEOCreateTicketPreset(
        role_profile_ref="frontend_engineer_primary",
        output_schema_ref=SOURCE_CODE_DELIVERY_SCHEMA_REF,
        output_schema_version=SOURCE_CODE_DELIVERY_SCHEMA_VERSION,
        constraints_ref="approved_scope_followup_build",
        priority="high",
        delivery_stage=DeliveryStage.BUILD,
    ),
    ("backend_engineer_primary", SOURCE_CODE_DELIVERY_SCHEMA_REF): CEOCreateTicketPreset(
        role_profile_ref="backend_engineer_primary",
        output_schema_ref=SOURCE_CODE_DELIVERY_SCHEMA_REF,
        output_schema_version=SOURCE_CODE_DELIVERY_SCHEMA_VERSION,
        constraints_ref="approved_scope_followup_build",
        priority="high",
        delivery_stage=DeliveryStage.BUILD,
    ),
    ("database_engineer_primary", SOURCE_CODE_DELIVERY_SCHEMA_REF): CEOCreateTicketPreset(
        role_profile_ref="database_engineer_primary",
        output_schema_ref=SOURCE_CODE_DELIVERY_SCHEMA_REF,
        output_schema_version=SOURCE_CODE_DELIVERY_SCHEMA_VERSION,
        constraints_ref="approved_scope_followup_build",
        priority="high",
        delivery_stage=DeliveryStage.BUILD,
    ),
    ("platform_sre_primary", SOURCE_CODE_DELIVERY_SCHEMA_REF): CEOCreateTicketPreset(
        role_profile_ref="platform_sre_primary",
        output_schema_ref=SOURCE_CODE_DELIVERY_SCHEMA_REF,
        output_schema_version=SOURCE_CODE_DELIVERY_SCHEMA_VERSION,
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

_GOVERNANCE_DOCUMENT_PRESET_VERSION_BY_SCHEMA = {
    ARCHITECTURE_BRIEF_SCHEMA_REF: ARCHITECTURE_BRIEF_SCHEMA_VERSION,
    TECHNOLOGY_DECISION_SCHEMA_REF: TECHNOLOGY_DECISION_SCHEMA_VERSION,
    MILESTONE_PLAN_SCHEMA_REF: MILESTONE_PLAN_SCHEMA_VERSION,
    DETAILED_DESIGN_SCHEMA_REF: DETAILED_DESIGN_SCHEMA_VERSION,
    BACKLOG_RECOMMENDATION_SCHEMA_REF: BACKLOG_RECOMMENDATION_SCHEMA_VERSION,
}
_GOVERNANCE_DOCUMENT_ROLE_PROFILES: dict[str, tuple[str, ...]] = {
    "ui_designer_primary": tuple(GOVERNANCE_DOCUMENT_SCHEMA_REFS),
    "frontend_engineer_primary": tuple(GOVERNANCE_DOCUMENT_SCHEMA_REFS),
    "architect_primary": (
        ARCHITECTURE_BRIEF_SCHEMA_REF,
        TECHNOLOGY_DECISION_SCHEMA_REF,
        DETAILED_DESIGN_SCHEMA_REF,
    ),
    "cto_primary": (
        ARCHITECTURE_BRIEF_SCHEMA_REF,
        TECHNOLOGY_DECISION_SCHEMA_REF,
        MILESTONE_PLAN_SCHEMA_REF,
        BACKLOG_RECOMMENDATION_SCHEMA_REF,
    ),
}
GOVERNANCE_DOCUMENT_CHAIN_ORDER = (
    ARCHITECTURE_BRIEF_SCHEMA_REF,
    TECHNOLOGY_DECISION_SCHEMA_REF,
    MILESTONE_PLAN_SCHEMA_REF,
    DETAILED_DESIGN_SCHEMA_REF,
    BACKLOG_RECOMMENDATION_SCHEMA_REF,
)

for role_profile_ref, output_schema_refs in _GOVERNANCE_DOCUMENT_ROLE_PROFILES.items():
    for output_schema_ref in output_schema_refs:
        _CREATE_TICKET_PRESETS[(role_profile_ref, output_schema_ref)] = CEOCreateTicketPreset(
            role_profile_ref=role_profile_ref,
            output_schema_ref=output_schema_ref,
            output_schema_version=_GOVERNANCE_DOCUMENT_PRESET_VERSION_BY_SCHEMA[output_schema_ref],
            constraints_ref=f"ceo_governance_document_{output_schema_ref}",
            priority="high" if output_schema_ref in {ARCHITECTURE_BRIEF_SCHEMA_REF, DETAILED_DESIGN_SCHEMA_REF} else "medium",
            delivery_stage=None,
        )


PROJECT_INIT_SCOPE_NODE_ID = "node_scope_decision"
PROJECT_INIT_AUTOPILOT_ARCHITECTURE_NODE_ID = "node_ceo_architecture_brief"


def build_project_init_scope_ticket_id(workflow_id: str) -> str:
    return f"tkt_{workflow_id}_scope_decision"


def build_project_init_scope_summary(north_star_goal: str) -> str:
    clean_goal = north_star_goal.strip() or "the current workflow"
    return (
        "Prepare the kickoff consensus report and the first batch of follow-up ticket outlines for "
        f"{clean_goal}."
    )


def build_autopilot_architecture_brief_summary(north_star_goal: str) -> str:
    clean_goal = north_star_goal.strip() or "the current workflow"
    return (
        "Clarify the delivery architecture for "
        f"{clean_goal}, extract concrete user-facing requirements, and decompose the work into fine-grained atomic tasks."
    )


def build_project_init_brief_artifact_ref(workflow_id: str) -> str:
    return f"art://project-init/{workflow_id}/board-brief.md"


def is_project_init_scope_preset(*, role_profile_ref: str, output_schema_ref: str) -> bool:
    return role_profile_ref == "ui_designer_primary" and output_schema_ref == CONSENSUS_DOCUMENT_SCHEMA_REF


def supports_ceo_create_ticket_preset(*, role_profile_ref: str, output_schema_ref: str) -> bool:
    return (role_profile_ref, output_schema_ref) in _CREATE_TICKET_PRESETS


def is_governance_document_preset(output_schema_ref: str) -> bool:
    return output_schema_ref in GOVERNANCE_DOCUMENT_SCHEMA_REFS


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
    clean_summary = summary.strip() or "Source code delivery is ready for internal delivery review."
    return {
        "review_type": "INTERNAL_DELIVERY_REVIEW",
        "priority": "high",
        "title": "Check approved source code delivery",
        "subtitle": "Internal checker should validate the build output before downstream checking starts.",
        "blocking_scope": "NODE_ONLY",
        "trigger_reason": "Source code delivery reached the internal checker gate.",
        "why_now": "Downstream delivery check should only consume implementation that already passed peer review.",
        "recommended_action": "APPROVE",
        "recommended_option_id": "internal_delivery_ok",
        "recommendation_summary": clean_summary,
        "options": [
            {
                "option_id": "internal_delivery_ok",
                "label": "Pass source delivery",
                "summary": clean_summary,
                "artifact_refs": [],
                "pros": ["Lets downstream checking continue without reopening scope."],
                "cons": ["Leaves only non-blocking polish to later steps."],
                "risks": ["Implementation notes may still need follow-up after checking."],
            }
        ],
        "evidence_summary": [
            {
                "evidence_id": "ev_internal_source_code_delivery",
                "source_type": "SOURCE_CODE_DELIVERY",
                "headline": "Source code delivery is ready for peer review",
                "summary": clean_summary,
                "source_ref": None,
            }
        ],
        "available_actions": ["APPROVE", "REJECT", "MODIFY_CONSTRAINTS"],
        "draft_selected_option_id": "internal_delivery_ok",
        "comment_template": "",
        "badges": ["internal_delivery", "scope_followup", "build_gate"],
    }


def build_internal_governance_review_request(summary: str) -> dict[str, Any]:
    clean_summary = summary.strip() or "Governance document is ready for internal review."
    return {
        "review_type": "INTERNAL_GOVERNANCE_REVIEW",
        "priority": "high",
        "title": "Check governance document",
        "subtitle": "Internal checker should validate the document chain before downstream tickets consume it.",
        "blocking_scope": "NODE_ONLY",
        "trigger_reason": "Governance document reached the internal governance checker gate.",
        "why_now": "Downstream planning and implementation should only consume governance guidance that already passed internal review.",
        "recommended_action": "APPROVE",
        "recommended_option_id": "internal_governance_ok",
        "recommendation_summary": clean_summary,
        "options": [
            {
                "option_id": "internal_governance_ok",
                "label": "Pass governance doc",
                "summary": clean_summary,
                "artifact_refs": [],
                "pros": ["Lets downstream tickets consume a checked governance document."],
                "cons": ["Leaves only non-blocking polish outside the current governance gate."],
                "risks": ["Weakly linked decisions or constraints may still need one more rework pass."],
            }
        ],
        "evidence_summary": [
            {
                "evidence_id": "ev_internal_governance_document",
                "source_type": "GOVERNANCE_DOCUMENT",
                "headline": "Governance document is ready for peer review",
                "summary": clean_summary,
                "source_ref": None,
            }
        ],
        "available_actions": ["APPROVE", "REJECT", "MODIFY_CONSTRAINTS"],
        "draft_selected_option_id": "internal_governance_ok",
        "comment_template": "",
        "badges": ["internal_governance", "document_gate"],
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
        *GOVERNANCE_DOCUMENT_SCHEMA_REFS,
        DELIVERY_CHECK_REPORT_SCHEMA_REF,
        DELIVERY_CLOSEOUT_PACKAGE_SCHEMA_REF,
    }:
        return ["read_artifact", "write_artifact"]
    return ["read_artifact", "write_artifact", "image_gen"]


def _allowed_write_set_for_preset(ticket_id: str, preset: CEOCreateTicketPreset) -> list[str]:
    if preset.output_schema_ref == CONSENSUS_DOCUMENT_SCHEMA_REF:
        return ["reports/meeting/*"]
    if preset.output_schema_ref in GOVERNANCE_DOCUMENT_SCHEMA_REFS:
        return [f"reports/governance/{ticket_id}/*"]
    if preset.output_schema_ref == SOURCE_CODE_DELIVERY_SCHEMA_REF:
        return [
            "10-project/src/*",
            "10-project/docs/*",
            "20-evidence/tests/*",
            "20-evidence/git/*",
        ]
    if preset.output_schema_ref == DELIVERY_CHECK_REPORT_SCHEMA_REF:
        return [f"reports/check/{ticket_id}/*"]
    if preset.output_schema_ref == DELIVERY_CLOSEOUT_PACKAGE_SCHEMA_REF:
        return [f"20-evidence/closeout/{ticket_id}/*"]
    return [
        f"artifacts/ui/scope-followups/{ticket_id}/*",
        f"reports/review/{ticket_id}/*",
    ]


def _context_keywords_for_preset(preset: CEOCreateTicketPreset) -> list[str]:
    if preset.output_schema_ref == CONSENSUS_DOCUMENT_SCHEMA_REF:
        return ["scope", "constraints", "board review"]
    if preset.output_schema_ref == ARCHITECTURE_BRIEF_SCHEMA_REF:
        return ["architecture", "constraints", "delivery path"]
    if preset.output_schema_ref == TECHNOLOGY_DECISION_SCHEMA_REF:
        return ["technology decision", "trade-offs", "constraints"]
    if preset.output_schema_ref == MILESTONE_PLAN_SCHEMA_REF:
        return ["milestones", "sequence", "delivery plan"]
    if preset.output_schema_ref == DETAILED_DESIGN_SCHEMA_REF:
        return ["detailed design", "interfaces", "implementation boundary"]
    if preset.output_schema_ref == BACKLOG_RECOMMENDATION_SCHEMA_REF:
        return ["backlog", "follow-up slices", "delivery recommendation"]
    if preset.output_schema_ref == SOURCE_CODE_DELIVERY_SCHEMA_REF:
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
    if preset.output_schema_ref in GOVERNANCE_DOCUMENT_SCHEMA_REFS:
        return [
            f"Must produce a structured governance document for this delivery need: {clean_summary}",
            f"Must use document_kind_ref `{preset.output_schema_ref}` and keep the result auditable.",
            "Must keep downstream implementation explicit instead of jumping straight into code.",
        ]
    if preset.output_schema_ref == SOURCE_CODE_DELIVERY_SCHEMA_REF:
        return [
            f"Must implement this approved scope follow-up: {clean_summary}",
            "Must stay inside the locked scope from the approved consensus document.",
            "Must produce a structured source code delivery package.",
        ]
    if preset.output_schema_ref == DELIVERY_CHECK_REPORT_SCHEMA_REF:
        return [
            f"Must check this approved scope follow-up: {clean_summary}",
            "Must verify the source code delivery still stays inside the locked scope.",
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
    if preset.output_schema_ref in GOVERNANCE_DOCUMENT_SCHEMA_REFS:
        return build_internal_governance_review_request(summary)
    if preset.output_schema_ref == SOURCE_CODE_DELIVERY_SCHEMA_REF:
        return _build_internal_delivery_review_request(summary)
    if preset.output_schema_ref == DELIVERY_CHECK_REPORT_SCHEMA_REF:
        return _build_internal_check_review_request(summary)
    if preset.output_schema_ref == DELIVERY_CLOSEOUT_PACKAGE_SCHEMA_REF:
        return _build_closeout_review_request(summary)
    if preset.output_schema_ref == UI_MILESTONE_REVIEW_SCHEMA_REF:
        return _build_visual_review_request(summary)
    return None


def _inherit_input_artifact_refs_for_preset(
    repository: "ControlPlaneRepository" | None,
    *,
    payload: CEOCreateTicketPayload,
    preset: CEOCreateTicketPreset,
) -> list[str]:
    if repository is None or preset.output_schema_ref != DELIVERY_CLOSEOUT_PACKAGE_SCHEMA_REF:
        return []

    inherited_artifact_refs: list[str] = []
    source_ticket_ids: list[str] = []
    if payload.parent_ticket_id:
        source_ticket_ids.append(payload.parent_ticket_id)
    if payload.dispatch_intent is not None:
        for dependency_ticket_id in list(payload.dispatch_intent.dependency_gate_refs or []):
            normalized_ticket_id = str(dependency_ticket_id).strip()
            if normalized_ticket_id and normalized_ticket_id not in source_ticket_ids:
                source_ticket_ids.append(normalized_ticket_id)
    with repository.connection() as connection:
        for source_ticket_id in source_ticket_ids:
            terminal_event = repository.get_latest_ticket_terminal_event(connection, source_ticket_id)
            terminal_payload = terminal_event.get("payload") if terminal_event is not None else {}
            for artifact_ref in list((terminal_payload or {}).get("artifact_refs") or []):
                normalized_artifact_ref = str(artifact_ref).strip()
                if normalized_artifact_ref and normalized_artifact_ref not in inherited_artifact_refs:
                    inherited_artifact_refs.append(normalized_artifact_ref)
    return inherited_artifact_refs


def build_ceo_create_ticket_command(
    *,
    workflow: dict[str, Any],
    payload: CEOCreateTicketPayload,
    repository: "ControlPlaneRepository" | None = None,
) -> TicketCreateCommand:
    preset = _CREATE_TICKET_PRESETS[(payload.role_profile_ref, payload.output_schema_ref)]
    is_project_init_scope = is_project_init_scope_preset(
        role_profile_ref=payload.role_profile_ref,
        output_schema_ref=payload.output_schema_ref,
    )
    is_autopilot_architecture_kickoff = (
        payload.node_id == PROJECT_INIT_AUTOPILOT_ARCHITECTURE_NODE_ID
        and payload.output_schema_ref == ARCHITECTURE_BRIEF_SCHEMA_REF
        and payload.parent_ticket_id is None
    )
    ticket_id = (
        build_project_init_scope_ticket_id(payload.workflow_id)
        if is_project_init_scope
        else new_prefixed_id("tkt")
    )
    node_id = PROJECT_INIT_SCOPE_NODE_ID if is_project_init_scope else payload.node_id
    input_artifact_refs = (
        [build_project_init_brief_artifact_ref(payload.workflow_id)]
        if is_project_init_scope or is_autopilot_architecture_kickoff
        else []
    )
    for artifact_ref in _inherit_input_artifact_refs_for_preset(
        repository,
        payload=payload,
        preset=preset,
    ):
        if artifact_ref not in input_artifact_refs:
            input_artifact_refs.append(artifact_ref)
    inherited_process_asset_refs: list[str] = []
    if repository is not None and preset.output_schema_ref != CONSENSUS_DOCUMENT_SCHEMA_REF:
        source_ticket_ids: list[str] = []
        if payload.parent_ticket_id:
            source_ticket_ids.append(payload.parent_ticket_id)
        if payload.dispatch_intent is not None:
            for dependency_ticket_id in list(payload.dispatch_intent.dependency_gate_refs or []):
                normalized_ticket_id = str(dependency_ticket_id).strip()
                if normalized_ticket_id and normalized_ticket_id not in source_ticket_ids:
                    source_ticket_ids.append(normalized_ticket_id)
        with repository.connection() as connection:
            for source_ticket_id in source_ticket_ids:
                source_created_spec = repository.get_latest_ticket_created_payload(connection, source_ticket_id) or {}
                if str(source_created_spec.get("output_schema_ref") or "").strip() not in GOVERNANCE_DOCUMENT_SCHEMA_REFS:
                    continue
                for process_asset_ref in get_ticket_output_process_asset_refs(
                    repository,
                    connection,
                    source_ticket_id,
                ):
                    if process_asset_ref not in inherited_process_asset_refs:
                        inherited_process_asset_refs.append(process_asset_ref)
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
        input_process_asset_refs=inherited_process_asset_refs,
        context_query_plan={
            "keywords": (
                ["scope", "constraints", "board review"]
                if is_project_init_scope
                else _context_keywords_for_preset(preset)
            ),
            "semantic_queries": semantic_queries,
            "max_context_tokens": get_settings().default_max_context_tokens,
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
        runtime_preference=payload.runtime_preference,
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
