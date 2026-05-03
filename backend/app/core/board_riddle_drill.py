from __future__ import annotations

import json
import random
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from time import perf_counter
from typing import Any

from app.contracts.runtime import (
    RenderedExecutionMessage,
    RenderedExecutionPayload,
    RenderedExecutionPayloadMeta,
    RenderedExecutionPayloadSummary,
)
from app.core.constants import EMPLOYEE_STATE_ACTIVE, EVENT_EMPLOYEE_HIRED
from app.core.persona_profiles import (
    AESTHETIC_PROFILE_DIMENSIONS,
    PERSONALITY_PROFILE_DIMENSIONS,
    build_high_overlap_rejection_reason,
    clone_persona_template,
    find_same_role_high_overlap_conflict,
    normalize_persona_profiles,
)
from app.core.provider_openai_compat import (
    OpenAICompatProviderError,
    invoke_openai_compat_response,
    resolve_openai_compat_result_payload,
)
from app.core.runtime import _build_openai_compat_provider_config
from app.core.runtime_provider_config import (
    OPENAI_COMPAT_PROVIDER_ID,
    ROLE_BINDING_CEO_SHADOW,
    RuntimeProviderAdapterKind,
    RuntimeProviderConfigStore,
    resolve_provider_selection,
    resolve_runtime_provider_config,
    runtime_provider_health_details,
)
from app.core.staffing_catalog import list_board_workforce_staffing_hire_templates, resolve_board_workforce_staffing_combo
from app.core.time import now_local
from app.db.repository import ControlPlaneRepository


class BoardRiddleDrillError(RuntimeError):
    def __init__(self, *, failure_kind: str, message: str) -> None:
        super().__init__(message)
        self.failure_kind = failure_kind


_PERSONALITY_ALLOWED_VALUES = {
    "risk_posture": ("assertive", "cautious", "guarded"),
    "challenge_style": ("constructive", "probing", "adversarial"),
    "execution_pace": ("fast", "measured", "deliberate"),
    "detail_rigor": ("focused", "rigorous", "sweeping"),
    "communication_style": ("direct", "concise", "forensic"),
}
_AESTHETIC_ALLOWED_VALUES = {
    "surface_preference": ("functional", "polished", "systematic", "clarifying"),
    "information_density": ("balanced", "layered", "dense"),
    "motion_tolerance": ("measured", "restrained", "minimal"),
}
_ROLE_SEQUENCE = (
    "frontend_engineer",
    "checker",
    "backend_engineer",
    "database_engineer",
    "platform_sre",
    "governance_architect",
    "governance_cto",
)
_BOARD_RIDDLE_EMPLOYEE_TARGET_REF = "board_riddle_drill:employee_assignment"
_ROLE_NAMES_ZH = {
    "frontend_engineer": "前端工程师",
    "checker": "质量检查员",
    "backend_engineer": "后端工程师",
    "database_engineer": "数据库工程师",
    "platform_sre": "平台与稳定性工程师",
    "governance_architect": "治理架构师",
    "governance_cto": "治理 CTO",
}
_SKILL_VALUE_LABELS_ZH = {
    "frontend": "前端",
    "quality": "质量",
    "backend": "后端",
    "data": "数据",
    "platform": "平台",
    "architecture": "架构",
    "delivery_slice": "交付切片",
    "surface_polish": "界面润色",
    "release_guard": "发布守门",
    "release_sweep": "发布扫尾",
    "service_delivery": "服务交付",
    "data_reliability": "数据可靠性",
    "runtime_operations": "运行稳定性",
    "design_review": "设计评审",
    "governance_direction": "治理方向",
    "balanced": "平衡",
    "finish_first": "先完成后细化",
    "evidence_first": "证据优先",
    "regression_first": "回归优先",
}
_PERSONALITY_VALUE_LABELS_ZH = {
    "assertive": "积极",
    "cautious": "谨慎",
    "guarded": "保守",
    "constructive": "建设性",
    "probing": "追问式",
    "adversarial": "对抗式",
    "fast": "快速",
    "measured": "稳健",
    "deliberate": "审慎",
    "focused": "聚焦",
    "rigorous": "严谨",
    "sweeping": "全面",
    "direct": "直接",
    "concise": "简洁",
    "forensic": "取证式",
}
_AESTHETIC_VALUE_LABELS_ZH = {
    "functional": "功能导向",
    "polished": "精修",
    "systematic": "系统化",
    "clarifying": "澄清导向",
    "balanced": "均衡",
    "layered": "分层",
    "dense": "高密度",
    "measured": "克制",
    "restrained": "保守",
    "minimal": "极简",
}


def _board_riddle_ticket_id(workflow_id: str, suffix: str) -> str:
    return f"tkt_{workflow_id}_{suffix}"


def _artifact_ref(workflow_id: str) -> str:
    return f"art://board-riddle-drill/{workflow_id}/board-report.json"


def _process_archive_artifact_ref(workflow_id: str) -> str:
    return f"art://board-riddle-drill/{workflow_id}/process-archive.json"


def _employee_id(workflow_id: str, index: int) -> str:
    return f"emp_{workflow_id.removeprefix('wf_')[:6]}_{index:02d}"


def _label_zh(value: str, mapping: dict[str, str]) -> str:
    return mapping.get(value, value.replace("_", " "))


def _build_profile_summary_zh(
    *,
    skill_profile: dict[str, str],
    personality_profile: dict[str, str],
    aesthetic_profile: dict[str, str],
) -> str:
    return (
        "技能："
        f"{_label_zh(skill_profile['primary_domain'], _SKILL_VALUE_LABELS_ZH)} / "
        f"{_label_zh(skill_profile['system_scope'], _SKILL_VALUE_LABELS_ZH)} / "
        f"{_label_zh(skill_profile['validation_bias'], _SKILL_VALUE_LABELS_ZH)}。"
        "性格："
        f"{_label_zh(personality_profile['risk_posture'], _PERSONALITY_VALUE_LABELS_ZH)} / "
        f"{_label_zh(personality_profile['challenge_style'], _PERSONALITY_VALUE_LABELS_ZH)} / "
        f"{_label_zh(personality_profile['execution_pace'], _PERSONALITY_VALUE_LABELS_ZH)} / "
        f"{_label_zh(personality_profile['detail_rigor'], _PERSONALITY_VALUE_LABELS_ZH)} / "
        f"{_label_zh(personality_profile['communication_style'], _PERSONALITY_VALUE_LABELS_ZH)}。"
        "审美："
        f"{_label_zh(aesthetic_profile['surface_preference'], _AESTHETIC_VALUE_LABELS_ZH)} / "
        f"{_label_zh(aesthetic_profile['information_density'], _AESTHETIC_VALUE_LABELS_ZH)} / "
        f"{_label_zh(aesthetic_profile['motion_tolerance'], _AESTHETIC_VALUE_LABELS_ZH)}。"
    )


def _rotate_value(values: tuple[str, ...], current: str, offset: int) -> str:
    ordered = [value for value in values if value != current]
    return ordered[offset % len(ordered)]


def _variant_persona_from_template(template: dict[str, Any], *, variant_index: int) -> dict[str, Any]:
    if variant_index <= 0:
        return {
            "skill_profile": dict(template["skill_profile"]),
            "personality_profile": dict(template["personality_profile"]),
            "aesthetic_profile": dict(template["aesthetic_profile"]),
        }

    skill_profile = dict(template["skill_profile"])
    personality_profile = dict(template["personality_profile"])
    aesthetic_profile = dict(template["aesthetic_profile"])

    for offset in range(2):
        dimension = PERSONALITY_PROFILE_DIMENSIONS[(variant_index + offset) % len(PERSONALITY_PROFILE_DIMENSIONS)]
        personality_profile[dimension] = _rotate_value(
            _PERSONALITY_ALLOWED_VALUES[dimension],
            personality_profile[dimension],
            variant_index + offset,
        )

    for offset in range(2):
        dimension = AESTHETIC_PROFILE_DIMENSIONS[(variant_index + offset) % len(AESTHETIC_PROFILE_DIMENSIONS)]
        aesthetic_profile[dimension] = _rotate_value(
            _AESTHETIC_ALLOWED_VALUES[dimension],
            aesthetic_profile[dimension],
            variant_index + offset,
        )

    return {
        "skill_profile": skill_profile,
        "personality_profile": personality_profile,
        "aesthetic_profile": aesthetic_profile,
    }


def _build_candidate_entry(
    *,
    workflow_id: str,
    employee_index: int,
    role_type: str,
    role_profile_refs: list[str],
    raw_skill_profile: dict[str, str],
    raw_personality_profile: dict[str, str],
    raw_aesthetic_profile: dict[str, str],
) -> dict[str, Any]:
    normalized = normalize_persona_profiles(
        role_type,
        skill_profile=raw_skill_profile,
        personality_profile=raw_personality_profile,
        aesthetic_profile=raw_aesthetic_profile,
    )
    return {
        "employee_id": _employee_id(workflow_id, employee_index),
        "role_type": role_type,
        "role_name_zh": _ROLE_NAMES_ZH.get(role_type, role_type),
        "role_profile_refs": list(role_profile_refs),
        "provider_id": OPENAI_COMPAT_PROVIDER_ID,
        "template_id": normalized["template_id"],
        "skill_profile": normalized["skill_profile"],
        "personality_profile": normalized["personality_profile"],
        "aesthetic_profile": normalized["aesthetic_profile"],
        "profile_summary": normalized["profile_summary"],
        "profile_summary_zh": _build_profile_summary_zh(
            skill_profile=normalized["skill_profile"],
            personality_profile=normalized["personality_profile"],
            aesthetic_profile=normalized["aesthetic_profile"],
        ),
    }


def _accepted_candidates(
    repository: ControlPlaneRepository,
    *,
    workflow_id: str,
    requested_headcount: int,
) -> list[dict[str, Any]]:
    templates_by_role = {
        str(template["role_type"]): template
        for template in list_board_workforce_staffing_hire_templates()
    }
    existing_employees = repository.list_employee_projections(
        states=[EMPLOYEE_STATE_ACTIVE],
        board_approved_only=True,
    )
    per_role_counts: dict[str, int] = {}
    accepted_candidates: list[dict[str, Any]] = []

    def _projection_shape(candidate: dict[str, Any]) -> dict[str, Any]:
        return {
            "employee_id": candidate["employee_id"],
            "role_type": candidate["role_type"],
            "state": EMPLOYEE_STATE_ACTIVE,
            "board_approved": True,
            "skill_profile_json": candidate["skill_profile"],
            "personality_profile_json": candidate["personality_profile"],
            "aesthetic_profile_json": candidate["aesthetic_profile"],
        }

    safety_counter = 0
    while len(accepted_candidates) < requested_headcount:
        role_type = _ROLE_SEQUENCE[safety_counter % len(_ROLE_SEQUENCE)]
        template = templates_by_role[role_type]
        variant_index = per_role_counts.get(role_type, 0)
        per_role_counts[role_type] = variant_index + 1
        persona = _variant_persona_from_template(template, variant_index=variant_index)
        candidate = _build_candidate_entry(
            workflow_id=workflow_id,
            employee_index=len(accepted_candidates) + 1,
            role_type=role_type,
            role_profile_refs=list(template["role_profile_refs"]),
            raw_skill_profile=persona["skill_profile"],
            raw_personality_profile=persona["personality_profile"],
            raw_aesthetic_profile=persona["aesthetic_profile"],
        )
        _, staffing_reason = resolve_board_workforce_staffing_combo(
            candidate["role_type"],
            candidate["role_profile_refs"],
        )
        conflict = None
        if staffing_reason is None:
            conflict = find_same_role_high_overlap_conflict(
                role_type=candidate["role_type"],
                skill_profile=candidate["skill_profile"],
                personality_profile=candidate["personality_profile"],
                aesthetic_profile=candidate["aesthetic_profile"],
                employees=[*existing_employees, *[_projection_shape(item) for item in accepted_candidates]],
            )
        if staffing_reason is None and conflict is None:
            accepted_candidates.append(
                {
                    **candidate,
                    "status": "ACCEPTED",
                    "rejection_reason": None,
                }
            )
        safety_counter += 1
        if safety_counter > requested_headcount * 20:
            raise BoardRiddleDrillError(
                failure_kind="RECRUITMENT_EXHAUSTED",
                message="Board riddle drill could not generate enough accepted employees.",
            )
    return accepted_candidates


def _forced_rejected_candidates(
    *,
    workflow_id: str,
    requested_headcount: int,
) -> list[dict[str, Any]]:
    rejected_count = max(1, requested_headcount // 5)
    candidates: list[dict[str, Any]] = []
    start_index = requested_headcount + 1
    frontend_duplicate = clone_persona_template("frontend_core_builder")
    checker_duplicate = clone_persona_template("checker_evidence_guard")

    forced = [
        {
            "employee_index": start_index,
            "role_type": "frontend_engineer",
            "role_profile_refs": ["frontend_engineer_primary"],
            **frontend_duplicate,
        },
        {
            "employee_index": start_index + 1,
            "role_type": "checker",
            "role_profile_refs": ["checker_primary"],
            **checker_duplicate,
        },
        {
            "employee_index": start_index + 2,
            "role_type": "backend_engineer",
            "role_profile_refs": ["frontend_engineer_primary"],
            **clone_persona_template("backend_service_builder"),
        },
        {
            "employee_index": start_index + 3,
            "role_type": "prompt_poet",
            "role_profile_refs": ["prompt_poet_primary"],
            **clone_persona_template("frontend_polish_counterweight"),
        },
    ]
    for item in forced[:rejected_count]:
        candidates.append(
            _build_candidate_entry(
                workflow_id=workflow_id,
                employee_index=int(item["employee_index"]),
                role_type=str(item["role_type"]),
                role_profile_refs=list(item["role_profile_refs"]),
                raw_skill_profile=dict(item["skill_profile"]),
                raw_personality_profile=dict(item["personality_profile"]),
                raw_aesthetic_profile=dict(item["aesthetic_profile"]),
            )
        )
    return candidates


def _evaluate_candidates(
    repository: ControlPlaneRepository,
    *,
    workflow_id: str,
    requested_headcount: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    accepted_candidates = _accepted_candidates(
        repository,
        workflow_id=workflow_id,
        requested_headcount=requested_headcount,
    )
    rejected_candidates: list[dict[str, Any]] = []

    def _projection_shape(candidate: dict[str, Any]) -> dict[str, Any]:
        return {
            "employee_id": candidate["employee_id"],
            "role_type": candidate["role_type"],
            "state": EMPLOYEE_STATE_ACTIVE,
            "board_approved": True,
            "skill_profile_json": candidate["skill_profile"],
            "personality_profile_json": candidate["personality_profile"],
            "aesthetic_profile_json": candidate["aesthetic_profile"],
        }

    existing_employees = repository.list_employee_projections(
        states=[EMPLOYEE_STATE_ACTIVE],
        board_approved_only=True,
    )
    for candidate in _forced_rejected_candidates(
        workflow_id=workflow_id,
        requested_headcount=requested_headcount,
    ):
        _, staffing_reason = resolve_board_workforce_staffing_combo(
            candidate["role_type"],
            candidate["role_profile_refs"],
        )
        rejection_reason = staffing_reason
        if rejection_reason is None:
            conflict = find_same_role_high_overlap_conflict(
                role_type=candidate["role_type"],
                skill_profile=candidate["skill_profile"],
                personality_profile=candidate["personality_profile"],
                aesthetic_profile=candidate["aesthetic_profile"],
                employees=[*existing_employees, *[_projection_shape(item) for item in accepted_candidates]],
            )
            if conflict is not None:
                rejection_reason = build_high_overlap_rejection_reason(
                    role_type=candidate["role_type"],
                    conflict=conflict,
                )
        if rejection_reason is None:
            rejection_reason = "受控拒绝候选未命中预期校验，已按演练规则强制记为拒绝。"

        candidate_entry = {
            **candidate,
            "status": "REJECTED",
            "rejection_reason": rejection_reason,
        }
        rejected_candidates.append(candidate_entry)

    return accepted_candidates, rejected_candidates


def _insert_accepted_employees(
    repository: ControlPlaneRepository,
    *,
    workflow_id: str,
    accepted_candidates: list[dict[str, Any]],
) -> None:
    occurred_at = now_local()
    with repository.transaction() as connection:
        for candidate in accepted_candidates:
            repository.insert_event(
                connection,
                event_type=EVENT_EMPLOYEE_HIRED,
                actor_type="system",
                actor_id="board-riddle-drill",
                workflow_id=workflow_id,
                idempotency_key=f"board-riddle-drill:hire:{workflow_id}:{candidate['employee_id']}",
                causation_id=None,
                correlation_id=workflow_id,
                payload={
                    "employee_id": candidate["employee_id"],
                    "role_type": candidate["role_type"],
                    "role_profile_refs": list(candidate["role_profile_refs"]),
                    "skill_profile": dict(candidate["skill_profile"]),
                    "personality_profile": dict(candidate["personality_profile"]),
                    "aesthetic_profile": dict(candidate["aesthetic_profile"]),
                    "state": EMPLOYEE_STATE_ACTIVE,
                    "board_approved": True,
                    "provider_id": candidate["provider_id"],
                },
                occurred_at=occurred_at,
            )
        repository.refresh_projections(connection)


def _build_rendered_payload(
    *,
    workflow_id: str,
    ticket_id: str,
    node_id: str,
    task_payload: dict[str, Any],
) -> RenderedExecutionPayload:
    rendered_at = now_local()
    messages = [
        RenderedExecutionMessage(
            role="system",
            channel="SYSTEM_CONTROLS",
            content_type="JSON",
            content_payload={
                "rules": [
                    "Return JSON only.",
                    "Do not wrap the result in markdown code fences.",
                ]
            },
        ),
        RenderedExecutionMessage(
            role="user",
            channel="TASK_DEFINITION",
            content_type="JSON",
            content_payload=task_payload,
        ),
    ]
    return RenderedExecutionPayload(
        meta=RenderedExecutionPayloadMeta(
            bundle_id=f"ctx_{ticket_id}",
            compile_id=f"cmp_{ticket_id}",
            compile_request_id=f"creq_{ticket_id}",
            ticket_id=ticket_id,
            workflow_id=workflow_id,
            node_id=node_id,
            compiler_version="board-riddle-drill.v1",
            model_profile="board_riddle_drill",
            render_target="json_messages_v1",
            rendered_at=rendered_at,
        ),
        messages=messages,
        summary=RenderedExecutionPayloadSummary(
            total_message_count=len(messages),
            control_message_count=1,
            data_message_count=1,
            retrieval_message_count=0,
            degraded_data_message_count=0,
            reference_message_count=0,
        ),
    )


def _require_live_openai_selection(
    repository: ControlPlaneRepository,
    store: RuntimeProviderConfigStore,
    *,
    target_ref: str,
    preferred_provider_id: str,
    preferred_model: str,
    employee_provider_id: str | None = None,
):
    config = resolve_runtime_provider_config(store)
    selection = resolve_provider_selection(
        config,
        target_ref=target_ref,
        employee_provider_id=employee_provider_id,
        runtime_preference={
            "preferred_provider_id": preferred_provider_id,
            "preferred_model": preferred_model,
        },
    )
    if selection is None:
        raise BoardRiddleDrillError(
            failure_kind="DETERMINISTIC_FALLBACK_FORBIDDEN",
            message="No live provider selection was available for the board riddle drill.",
        )
    if selection.provider.adapter_kind != RuntimeProviderAdapterKind.OPENAI_COMPAT:
        raise BoardRiddleDrillError(
            failure_kind="DETERMINISTIC_FALLBACK_FORBIDDEN",
            message="Board riddle drill currently requires the OpenAI-compatible live provider path.",
        )
    health_status, health_reason = runtime_provider_health_details(selection.provider, repository)
    if health_status != "HEALTHY":
        raise BoardRiddleDrillError(
            failure_kind="DETERMINISTIC_FALLBACK_FORBIDDEN",
            message=health_reason,
        )
    if selection.provider.provider_id != preferred_provider_id:
        raise BoardRiddleDrillError(
            failure_kind="DETERMINISTIC_FALLBACK_FORBIDDEN",
            message="Board riddle drill refused provider fallback away from the requested provider.",
        )
    if str(selection.actual_model or "") != preferred_model:
        raise BoardRiddleDrillError(
            failure_kind="DETERMINISTIC_FALLBACK_FORBIDDEN",
            message="Board riddle drill refused model fallback away from the requested model.",
        )
    return selection


def _build_employee_dispatch_context(
    *,
    candidate: dict[str, Any],
    assignment: dict[str, Any],
) -> dict[str, Any]:
    return {
        "task": "请只用中文回答分配给你的脑筋急转弯，并返回 JSON。",
        "employee": {
            "employee_id": candidate["employee_id"],
            "role_name_zh": candidate["role_name_zh"],
            "profile_summary_zh": candidate["profile_summary_zh"],
        },
        "assignment": {
            "question": str(assignment["question"]),
            "expected_answer_reference": str(assignment["expected_answer"]),
        },
        "board_review_focus": [
            "保留派发上下文归档，供董事会复核。",
            "答案必须是简体中文短句。",
        ],
        "output_contract": {
            "answer": "中文短答案",
            "confidence": "0 到 1 的数字",
        },
    }


def _generate_ceo_assignments(
    repository: ControlPlaneRepository,
    store: RuntimeProviderConfigStore,
    *,
    workflow_id: str,
    accepted_candidates: list[dict[str, Any]],
    preferred_provider_id: str,
    preferred_model: str,
) -> tuple[str, list[dict[str, Any]], str | None]:
    selection = _require_live_openai_selection(
        repository,
        store,
        target_ref=ROLE_BINDING_CEO_SHADOW,
        preferred_provider_id=preferred_provider_id,
        preferred_model=preferred_model,
        employee_provider_id=preferred_provider_id,
    )
    payload = _build_rendered_payload(
        workflow_id=workflow_id,
        ticket_id=_board_riddle_ticket_id(workflow_id, "ceo_assignments"),
        node_id="node_board_riddle_drill_ceo_assignments",
        task_payload={
            "task": "请为每位已录用员工生成一道中文脑筋急转弯，并给出中文标准答案。",
            "accepted_employees": [
                {
                    "employee_id": candidate["employee_id"],
                    "role_name_zh": candidate["role_name_zh"],
                    "profile_summary_zh": candidate["profile_summary_zh"],
                }
                for candidate in accepted_candidates
            ],
            "board_constraints": [
                "题目和标准答案都必须使用简体中文。",
                "题目要适合董事会演练，不涉及危险或敏感内容。",
            ],
            "output_contract": {
                "summary": "中文概述",
                "assignments": [
                    {
                        "employee_id": "employee id from accepted_employees",
                        "question": "中文脑筋急转弯题面",
                        "expected_answer": "中文标准答案",
                    }
                ],
            },
        },
    )
    provider_result = invoke_openai_compat_response(
        _build_openai_compat_provider_config(selection),
        payload,
    )
    parsed = resolve_openai_compat_result_payload(provider_result).payload
    assignments = list(parsed.get("assignments") or [])
    expected_employee_ids = {candidate["employee_id"] for candidate in accepted_candidates}
    returned_employee_ids = {str(item.get("employee_id") or "").strip() for item in assignments if isinstance(item, dict)}
    if len(assignments) != len(accepted_candidates) or returned_employee_ids != expected_employee_ids:
        raise BoardRiddleDrillError(
            failure_kind="PROVIDER_BAD_RESPONSE",
            message="CEO assignment generation did not return one assignment per accepted employee.",
        )
    return str(parsed.get("summary") or "").strip(), assignments, provider_result.response_id


def _run_employee_assignment(
    repository: ControlPlaneRepository,
    store: RuntimeProviderConfigStore,
    *,
    workflow_id: str,
    candidate: dict[str, Any],
    assignment: dict[str, Any],
    preferred_provider_id: str,
    preferred_model: str,
) -> dict[str, Any]:
    selection = _require_live_openai_selection(
        repository,
        store,
        target_ref=_BOARD_RIDDLE_EMPLOYEE_TARGET_REF,
        preferred_provider_id=preferred_provider_id,
        preferred_model=preferred_model,
        employee_provider_id=candidate["provider_id"],
    )
    started_at = perf_counter()
    dispatch_context = _build_employee_dispatch_context(
        candidate=candidate,
        assignment=assignment,
    )
    try:
        payload = _build_rendered_payload(
            workflow_id=workflow_id,
            ticket_id=_board_riddle_ticket_id(workflow_id, candidate["employee_id"]),
            node_id=f"node_board_riddle_drill_{candidate['employee_id']}",
            task_payload=dispatch_context,
        )
        provider_result = invoke_openai_compat_response(
            _build_openai_compat_provider_config(selection),
            payload,
        )
        parsed = resolve_openai_compat_result_payload(provider_result).payload
        answer = str(parsed.get("answer") or "").strip()
        if not answer:
            raise BoardRiddleDrillError(
                failure_kind="PROVIDER_BAD_RESPONSE",
                message=f"{candidate['employee_id']} returned an empty answer.",
            )
        return {
            "employee_id": candidate["employee_id"],
            "status": "COMPLETED",
            "question": str(assignment["question"]),
            "expected_answer": str(assignment["expected_answer"]),
            "submitted_answer": answer,
            "confidence": float(parsed.get("confidence") or 0.0),
            "provider_id": selection.provider.provider_id,
            "model": selection.actual_model or selection.provider.model,
            "response_id": provider_result.response_id,
            "elapsed_ms": round((perf_counter() - started_at) * 1000, 2),
            "dispatch_context": dispatch_context,
        }
    except OpenAICompatProviderError as exc:
        return {
            "employee_id": candidate["employee_id"],
            "status": "FAILED",
            "question": str(assignment["question"]),
            "expected_answer": str(assignment["expected_answer"]),
            "submitted_answer": None,
            "confidence": 0.0,
            "provider_id": selection.provider.provider_id,
            "model": selection.actual_model or selection.provider.model,
            "response_id": None,
            "elapsed_ms": round((perf_counter() - started_at) * 1000, 2),
            "failure_kind": exc.failure_kind,
            "failure_detail": dict(exc.failure_detail),
            "dispatch_context": dispatch_context,
        }


def _write_json_artifact(
    repository: ControlPlaneRepository,
    *,
    workflow_id: str,
    artifact_ref: str,
    logical_path: str,
    node_id: str,
    ticket_suffix: str,
    payload: dict[str, Any],
) -> str:
    artifact_store = repository.artifact_store
    if artifact_store is None:
        raise RuntimeError("Artifact store is required for board riddle drill artifacts.")

    ticket_id = _board_riddle_ticket_id(workflow_id, ticket_suffix)
    materialized = artifact_store.materialize_json(
        logical_path,
        payload,
        workflow_id=workflow_id,
        ticket_id=ticket_id,
        artifact_ref=artifact_ref,
    )
    with repository.transaction() as connection:
        repository.save_artifact_record(
            connection,
            artifact_ref=artifact_ref,
            workflow_id=workflow_id,
            ticket_id=ticket_id,
            node_id=node_id,
            logical_path=logical_path,
            kind="JSON",
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
            created_at=now_local(),
        )
        repository.refresh_projections(connection)
    return artifact_ref


def _write_report_artifact(
    repository: ControlPlaneRepository,
    *,
    workflow_id: str,
    report: dict[str, Any],
) -> str:
    return _write_json_artifact(
        repository,
        workflow_id=workflow_id,
        artifact_ref=_artifact_ref(workflow_id),
        logical_path=f"reports/board-riddle-drill/{workflow_id}/board-report.json",
        node_id="node_board_riddle_drill_report",
        ticket_suffix="board_report",
        payload=report,
    )


def _write_process_archive_artifact(
    repository: ControlPlaneRepository,
    *,
    workflow_id: str,
    archive_payload: dict[str, Any],
) -> str:
    return _write_json_artifact(
        repository,
        workflow_id=workflow_id,
        artifact_ref=_process_archive_artifact_ref(workflow_id),
        logical_path=f"archives/board-riddle-drill/{workflow_id}/process-archive.json",
        node_id="node_board_riddle_drill_process_archive",
        ticket_suffix="process_archive",
        payload=archive_payload,
    )


def run_board_riddle_drill(
    repository: ControlPlaneRepository,
    runtime_provider_store: RuntimeProviderConfigStore,
    *,
    workflow_id: str,
    requested_headcount: int = 20,
    random_seed: int | None = None,
    preferred_provider_id: str = OPENAI_COMPAT_PROVIDER_ID,
    preferred_model: str = "gpt-5.4",
) -> dict[str, Any]:
    repository.initialize()
    if repository.get_workflow_projection(workflow_id) is None:
        raise BoardRiddleDrillError(
            failure_kind="WORKFLOW_NOT_FOUND",
            message=f"Workflow {workflow_id} was not found.",
        )

    accepted_candidates, rejected_candidates = _evaluate_candidates(
        repository,
        workflow_id=workflow_id,
        requested_headcount=requested_headcount,
    )
    _insert_accepted_employees(
        repository,
        workflow_id=workflow_id,
        accepted_candidates=accepted_candidates,
    )
    ceo_summary, assignments, assignment_response_id = _generate_ceo_assignments(
        repository,
        runtime_provider_store,
        workflow_id=workflow_id,
        accepted_candidates=accepted_candidates,
        preferred_provider_id=preferred_provider_id,
        preferred_model=preferred_model,
    )

    assignment_by_employee_id = {
        str(assignment["employee_id"]): assignment for assignment in assignments if isinstance(assignment, dict)
    }
    accepted_shuffled = list(accepted_candidates)
    if random_seed is not None:
        random.Random(random_seed).shuffle(accepted_shuffled)

    execution_results: list[dict[str, Any]] = []
    max_workers = min(8, len(accepted_shuffled)) or 1
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_map = {
            executor.submit(
                _run_employee_assignment,
                repository,
                runtime_provider_store,
                workflow_id=workflow_id,
                candidate=candidate,
                assignment=assignment_by_employee_id[candidate["employee_id"]],
                preferred_provider_id=preferred_provider_id,
                preferred_model=preferred_model,
            ): candidate["employee_id"]
            for candidate in accepted_shuffled
        }
        for future in as_completed(future_map):
            execution_results.append(future.result())

    execution_results.sort(key=lambda item: item["employee_id"])
    completed_answer_count = sum(1 for item in execution_results if item["status"] == "COMPLETED")
    failed_answer_count = sum(1 for item in execution_results if item["status"] == "FAILED")
    recruitment_attempt_count = len(accepted_candidates) + len(rejected_candidates)

    archive_payload = {
        "archive_kind": "BOARD_RIDDLE_DRILL_PROCESS_ARCHIVE",
        "workflow_id": workflow_id,
        "archived_only": True,
        "process_asset_ref": None,
        "included_in_board_review": True,
        "recruitment": {
            "requested_headcount": requested_headcount,
            "accepted_headcount": len(accepted_candidates),
            "rejected_headcount": len(rejected_candidates),
            "attempt_count": recruitment_attempt_count,
        },
        "ceo_assignment_batch": {
            "summary": ceo_summary,
            "response_id": assignment_response_id,
            "assignment_count": len(assignments),
        },
        "dispatch_contexts": [
            {
                "employee_id": item["employee_id"],
                "role_name_zh": next(
                    candidate["role_name_zh"]
                    for candidate in accepted_candidates
                    if candidate["employee_id"] == item["employee_id"]
                ),
                "dispatch_context": item["dispatch_context"],
                "question": item["question"],
                "expected_answer": item["expected_answer"],
                "submitted_answer": item["submitted_answer"],
                "status": item["status"],
                "provider_id": item["provider_id"],
                "model": item["model"],
                "response_id": item["response_id"],
            }
            for item in execution_results
        ],
        "rejected_candidates": rejected_candidates,
        "generated_at": now_local().isoformat(),
    }
    process_archive_artifact_ref = _write_process_archive_artifact(
        repository,
        workflow_id=workflow_id,
        archive_payload=archive_payload,
    )

    report = {
        "scenario_kind": "BOARD_RIDDLE_DRILL",
        "workflow_id": workflow_id,
        "requested_headcount": requested_headcount,
        "accepted_headcount": len(accepted_candidates),
        "rejected_headcount": len(rejected_candidates),
        "recruitment_attempt_count": recruitment_attempt_count,
        "deterministic_fallback_used": False,
        "preferred_provider_id": preferred_provider_id,
        "preferred_model": preferred_model,
        "process_archive_artifact_ref": process_archive_artifact_ref,
        "ceo_assignment_batch": {
            "summary": ceo_summary,
            "response_id": assignment_response_id,
            "assignment_count": len(assignments),
        },
        "roster": {
            "accepted": accepted_candidates,
            "rejected": rejected_candidates,
        },
        "employee_runs": execution_results,
        "board_report": {
            "status": "COMPLETED" if failed_answer_count == 0 else "FAILED",
            "completed_answer_count": completed_answer_count,
            "failed_answer_count": failed_answer_count,
            "summary": (
                f"CEO 已向 {len(assignments)} 名员工派发中文脑筋急转弯，回收 {completed_answer_count} 份答案，"
                f"同时记录 {len(rejected_candidates)} 条受控招聘拒绝。"
            ),
        },
        "board_review": {
            "status": "COMPLETED" if failed_answer_count == 0 else "FAILED",
            "summary": "董事会审核材料已包含派发上下文归档，可复核每名员工收到的中文任务上下文。",
            "completed_answer_count": completed_answer_count,
            "failed_answer_count": failed_answer_count,
            "review_materials": [
                {
                    "label": "派发上下文归档",
                    "artifact_ref": process_archive_artifact_ref,
                    "archived_only": True,
                    "process_asset_ref": None,
                    "summary": f"已归档 {len(execution_results)} 份派发上下文，不作为过程资产。",
                }
            ],
        },
        "generated_at": now_local().isoformat(),
    }
    report["artifact_ref"] = _write_report_artifact(
        repository,
        workflow_id=workflow_id,
        report=report,
    )
    return report
