from __future__ import annotations

from typing import Iterable

from app.contracts.runtime import CompileRequest, CompiledTaskFrame, SkillBinding
from app.core.versioning import build_skill_binding_id


SKILL_IMPLEMENTATION = "implementation"
SKILL_REVIEW = "review"
SKILL_DEBUGGING = "debugging"
SKILL_PLANNING_GOVERNANCE = "planning_governance"

_KNOWN_SKILL_IDS = {
    SKILL_IMPLEMENTATION,
    SKILL_REVIEW,
    SKILL_DEBUGGING,
    SKILL_PLANNING_GOVERNANCE,
}


def _normalize_forced_skill_ids(values: Iterable[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for item in values:
        skill_id = str(item).strip()
        if not skill_id:
            continue
        if skill_id not in _KNOWN_SKILL_IDS:
            raise ValueError(f"SkillBinding received an unknown forced skill id: {skill_id}")
        if skill_id in seen:
            continue
        seen.add(skill_id)
        normalized.append(skill_id)
    return normalized


def resolve_skill_binding(
    *,
    compile_request: CompileRequest,
    task_frame: CompiledTaskFrame,
) -> SkillBinding:
    forced_skill_ids = _normalize_forced_skill_ids(compile_request.execution.forced_skill_ids)
    base_skill_id = SKILL_IMPLEMENTATION
    conflict_resolution = "no_conflict"
    binding_reason = "Implementation delivery uses the implementation skill pack."

    if task_frame.task_category == "debugging":
        base_skill_id = SKILL_DEBUGGING
        conflict_resolution = "debugging_overrides_implementation"
        binding_reason = "Retry or incident context forces the debugging skill pack."
    elif task_frame.task_category == "review":
        base_skill_id = SKILL_REVIEW
        conflict_resolution = "review_excludes_implementation"
        binding_reason = "Review deliverables use the review skill pack."
    elif task_frame.task_category == "planning":
        base_skill_id = SKILL_PLANNING_GOVERNANCE
        conflict_resolution = "planning_excludes_implementation"
        binding_reason = "Structured governance delivery uses the planning skill pack."

    resolved_skill_ids = [base_skill_id]
    for skill_id in forced_skill_ids:
        if skill_id == base_skill_id:
            continue
        if task_frame.task_category in {"review", "planning", "debugging"}:
            raise ValueError(
                "SkillBinding rejected a forced skill id that conflicts with the current task category."
            )
        resolved_skill_ids.append(skill_id)

    return SkillBinding(
        binding_id=build_skill_binding_id(
            compile_request.meta.ticket_id,
            compile_request.meta.attempt_no,
        ),
        binding_version=compile_request.meta.attempt_no,
        task_category=task_frame.task_category,
        audit_mode=compile_request.governance_mode_slice.audit_mode,
        forced_skill_ids=forced_skill_ids,
        resolved_skill_ids=resolved_skill_ids,
        binding_reason=binding_reason,
        binding_scope="execution_package",
        conflict_resolution=conflict_resolution,
    )
