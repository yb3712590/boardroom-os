from __future__ import annotations

from datetime import datetime
from typing import Any

from app.contracts.commands import (
    ElicitationAnswer,
    ElicitationQuestion,
    ElicitationQuestionOption,
    ElicitationResponseKind,
    ProjectInitCommand,
    ReviewAction,
    ReviewPriority,
    ReviewType,
)

REQUIREMENT_ELICITATION_ARTIFACT_KIND = "REQUIREMENT_ELICITATION"
REQUIREMENT_ELICITATION_SOURCE_REF = "project-init"


def detect_requirement_elicitation_weak_signals(payload: ProjectInitCommand) -> list[str]:
    weak_signals: list[str] = []
    normalized_goal = " ".join(payload.north_star_goal.split())
    if len(normalized_goal) < 40:
        weak_signals.append("north_star_goal_too_short")
    if len([item for item in payload.hard_constraints if str(item).strip()]) < 2:
        weak_signals.append("hard_constraints_too_few")
    if payload.budget_cap == 0:
        weak_signals.append("budget_cap_zero")
    if payload.deadline_at is None:
        weak_signals.append("deadline_missing")
    return weak_signals


def should_require_requirement_elicitation(payload: ProjectInitCommand) -> tuple[bool, list[str]]:
    weak_signals = detect_requirement_elicitation_weak_signals(payload)
    return payload.force_requirement_elicitation or len(weak_signals) >= 3, weak_signals


def build_requirement_elicitation_questionnaire() -> list[ElicitationQuestion]:
    return [
        ElicitationQuestion(
            question_id="delivery_scope",
            prompt="What is the narrowest acceptable delivery slice?",
            response_kind=ElicitationResponseKind.SINGLE_SELECT,
            required=True,
            options=[
                ElicitationQuestionOption(
                    option_id="scope_mvp_slice",
                    label="Single MVP slice",
                    summary="One board-reviewable delivery path only.",
                ),
                ElicitationQuestionOption(
                    option_id="scope_review_plus_closeout",
                    label="Review plus closeout",
                    summary="Ship one delivery path through board review and closeout.",
                ),
            ],
        ),
        ElicitationQuestion(
            question_id="core_roles",
            prompt="Which core roles must stay on the initial path?",
            response_kind=ElicitationResponseKind.MULTI_SELECT,
            required=True,
            options=[
                ElicitationQuestionOption(
                    option_id="role_frontend_engineer",
                    label="Frontend engineer",
                    summary="Own the main source code delivery.",
                ),
                ElicitationQuestionOption(
                    option_id="role_checker",
                    label="Checker",
                    summary="Keep maker-checker on the initial path.",
                ),
                ElicitationQuestionOption(
                    option_id="role_meeting_room",
                    label="Meeting room only when blocked",
                    summary="Open meetings only for bounded technical decisions.",
                ),
            ],
        ),
        ElicitationQuestion(
            question_id="quality_bar",
            prompt="What quality bar must the team hit before board review?",
            response_kind=ElicitationResponseKind.SINGLE_SELECT,
            required=True,
            options=[
                ElicitationQuestionOption(
                    option_id="quality_board_review_ready",
                    label="Board-review ready",
                    summary="Need real evidence, checker pass, and a review pack.",
                ),
                ElicitationQuestionOption(
                    option_id="quality_build_first",
                    label="Build first, tighten later",
                    summary="Prefer speed, accept some polish follow-up after the first pass.",
                ),
            ],
        ),
        ElicitationQuestion(
            question_id="hard_boundaries",
            prompt="What hard boundaries must the team keep?",
            response_kind=ElicitationResponseKind.TEXT,
            required=True,
            options=[],
        ),
    ]


def build_requirement_elicitation_review_payload(
    *,
    workflow_id: str,
    occurred_at: datetime,
    weak_signals: list[str],
    board_brief_artifact_ref: str,
    draft_answers: list[ElicitationAnswer] | None = None,
) -> dict[str, Any]:
    questionnaire = build_requirement_elicitation_questionnaire()
    trigger_reason = (
        "Initial board directive is still below the minimum executable threshold."
        if weak_signals
        else "Board explicitly requested a requirement elicitation pass before scope kickoff."
    )
    return {
        "review_pack": {
            "meta": {
                "review_pack_version": 1,
                "workflow_id": workflow_id,
                "review_type": ReviewType.REQUIREMENT_ELICITATION.value,
                "created_at": occurred_at.isoformat(),
                "priority": ReviewPriority.HIGH.value,
            },
            "subject": {
                "title": "Clarify initialization inputs",
                "subtitle": "Capture the missing board answers before scope kickoff starts.",
                "blocking_scope": "WORKFLOW",
            },
            "trigger": {
                "trigger_event_id": f"evt_requirement_elicitation:{workflow_id}",
                "trigger_reason": trigger_reason,
                "why_now": "Need structured answers before scope kickoff starts.",
            },
            "recommendation": {
                "recommended_action": ReviewAction.APPROVE.value,
                "recommended_option_id": "elicitation_continue",
                "summary": "Capture the missing delivery answers and continue to scope kickoff.",
            },
            "options": [
                {
                    "option_id": "elicitation_continue",
                    "label": "Continue after clarification",
                    "summary": "Use the structured answers as the new startup brief.",
                    "artifact_refs": [],
                }
            ],
            "elicitation_questionnaire": [
                question.model_dump(mode="json") for question in questionnaire
            ],
            "evidence_summary": [
                {
                    "evidence_id": "ev_project_init_brief",
                    "headline": "Current board brief",
                    "summary": "Use the current project-init brief as the baseline while filling in the missing answers.",
                    "source_ref": board_brief_artifact_ref,
                }
            ],
            "delta_summary": {
                "weak_signals": weak_signals,
            },
            "decision_form": {
                "allowed_actions": [
                    ReviewAction.APPROVE.value,
                    ReviewAction.MODIFY_CONSTRAINTS.value,
                ],
                "command_target_version": 0,
                "requires_comment_on_reject": True,
                "requires_constraint_patch_on_modify": True,
            },
        },
        "available_actions": [
            ReviewAction.APPROVE.value,
            ReviewAction.MODIFY_CONSTRAINTS.value,
        ],
        "draft_defaults": {
            "selected_option_id": "elicitation_continue",
            "comment_template": "",
            "elicitation_answers": [
                answer.model_dump(mode="json") for answer in (draft_answers or [])
            ],
        },
        "inbox_title": "Clarify initialization inputs",
        "inbox_summary": "Board answers are required before scope kickoff can start.",
        "badges": ["requirement_elicitation", "board_gate", "project_init"],
        "priority": ReviewPriority.HIGH.value,
    }


def normalize_elicitation_answers(
    questionnaire: list[ElicitationQuestion],
    answers: list[ElicitationAnswer],
) -> list[ElicitationAnswer]:
    answer_map = {answer.question_id: answer for answer in answers}
    normalized: list[ElicitationAnswer] = []
    for question in questionnaire:
        answer = answer_map.get(question.question_id)
        if answer is None:
            if question.required:
                raise ValueError(f"Missing elicitation answer for {question.question_id}.")
            normalized.append(ElicitationAnswer(question_id=question.question_id))
            continue
        option_ids = {option.option_id for option in question.options}
        selected_option_ids = [item for item in answer.selected_option_ids if item]
        if any(item not in option_ids for item in selected_option_ids):
            raise ValueError(f"Invalid elicitation option for {question.question_id}.")
        text = answer.text.strip()
        if question.response_kind == ElicitationResponseKind.SINGLE_SELECT:
            if len(selected_option_ids) != 1:
                raise ValueError(f"Elicitation question {question.question_id} requires one selection.")
        elif question.response_kind == ElicitationResponseKind.MULTI_SELECT:
            if question.required and not selected_option_ids:
                raise ValueError(f"Elicitation question {question.question_id} requires at least one selection.")
        elif question.response_kind == ElicitationResponseKind.TEXT:
            if question.required and not text:
                raise ValueError(f"Elicitation question {question.question_id} requires text.")
        normalized.append(
            ElicitationAnswer(
                question_id=question.question_id,
                selected_option_ids=selected_option_ids,
                text=text,
            )
        )
    return normalized


def summarize_elicitation_answers(
    questionnaire: list[ElicitationQuestion],
    answers: list[ElicitationAnswer],
) -> list[dict[str, Any]]:
    question_map = {question.question_id: question for question in questionnaire}
    summary: list[dict[str, Any]] = []
    for answer in answers:
        question = question_map[answer.question_id]
        options = {option.option_id: option.label for option in question.options}
        summary.append(
            {
                "question_id": answer.question_id,
                "prompt": question.prompt,
                "selected_option_ids": list(answer.selected_option_ids),
                "selected_option_labels": [
                    options[option_id] for option_id in answer.selected_option_ids if option_id in options
                ],
                "text": answer.text,
            }
        )
    return summary


def build_requirement_elicitation_markdown(
    *,
    workflow_id: str,
    weak_signals: list[str],
    answers_summary: list[dict[str, Any]],
    board_comment: str,
) -> str:
    lines = [
        f"# Requirement Elicitation for {workflow_id}",
        "",
        "## Weak signals",
    ]
    if weak_signals:
        lines.extend(f"- {item}" for item in weak_signals)
    else:
        lines.append("- force_requirement_elicitation")
    lines.extend(["", "## Answers"])
    for item in answers_summary:
        lines.append(f"### {item['prompt']}")
        if item["selected_option_labels"]:
            lines.extend(f"- {label}" for label in item["selected_option_labels"])
        if item["text"]:
            lines.append(item["text"])
        lines.append("")
    lines.extend(["## Board comment", board_comment])
    return "\n".join(lines).strip() + "\n"


def build_enriched_board_brief_markdown(
    *,
    workflow_id: str,
    north_star_goal: str,
    budget_cap: int,
    deadline_at: str | None,
    hard_constraints: list[str],
    answers_summary: list[dict[str, Any]],
) -> str:
    lines = [
        f"# Enriched Board Brief for {workflow_id}",
        "",
        f"- North star goal: {north_star_goal}",
        f"- Budget cap: {budget_cap}",
        f"- Deadline: {deadline_at or 'None'}",
        "",
        "## Hard constraints",
        *(f"- {item}" for item in hard_constraints),
        "",
        "## Requirement elicitation answers",
    ]
    for item in answers_summary:
        lines.append(f"### {item['prompt']}")
        if item["selected_option_labels"]:
            lines.extend(f"- {label}" for label in item["selected_option_labels"])
        if item["text"]:
            lines.append(item["text"])
        lines.append("")
    return "\n".join(lines).strip() + "\n"
