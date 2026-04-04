from __future__ import annotations

from typing import Any

from app.core.persona_profiles import (
    clone_persona_template,
    get_hire_persona_template_id,
)


_MAINLINE_STAFFING_HIRE_TEMPLATES: tuple[dict[str, Any], ...] = (
    {
        "template_id": "frontend_engineer_backup",
        "label": "Frontend backup maker",
        "role_type": "frontend_engineer",
        "role_profile_refs": ["frontend_engineer_primary"],
        "employee_id_hint": "emp_frontend_backup",
        "provider_id": "prov_openai_compat",
        "request_summary": "Hire a backup frontend maker for rework rotation.",
        **clone_persona_template(get_hire_persona_template_id("frontend_engineer")),
    },
    {
        "template_id": "checker_backup",
        "label": "Checker backup",
        "role_type": "checker",
        "role_profile_refs": ["checker_primary"],
        "employee_id_hint": "emp_checker_backup",
        "provider_id": "prov_openai_compat",
        "request_summary": "Hire a backup checker to keep internal review moving.",
        **clone_persona_template(get_hire_persona_template_id("checker")),
    },
)


def _clone_template(template: dict[str, Any]) -> dict[str, Any]:
    return {
        **template,
        "role_profile_refs": list(template.get("role_profile_refs") or []),
        "skill_profile": dict(template.get("skill_profile") or {}),
        "personality_profile": dict(template.get("personality_profile") or {}),
        "aesthetic_profile": dict(template.get("aesthetic_profile") or {}),
    }


def list_mainline_staffing_hire_templates() -> list[dict[str, Any]]:
    return [_clone_template(template) for template in _MAINLINE_STAFFING_HIRE_TEMPLATES]


def get_mainline_staffing_template_for_role(role_type: str) -> dict[str, Any] | None:
    normalized_role_type = str(role_type or "").strip()
    for template in _MAINLINE_STAFFING_HIRE_TEMPLATES:
        if template["role_type"] == normalized_role_type:
            return _clone_template(template)
    return None


def mainline_staffing_template_id_for_role(role_type: str) -> str | None:
    template = get_mainline_staffing_template_for_role(role_type)
    if template is None:
        return None
    return str(template["template_id"])


def resolve_mainline_staffing_combo(
    role_type: str,
    role_profile_refs: list[str] | tuple[str, ...],
) -> tuple[dict[str, Any] | None, str | None]:
    template = get_mainline_staffing_template_for_role(role_type)
    normalized_role_type = str(role_type or "").strip()
    normalized_refs = [str(value).strip() for value in role_profile_refs if str(value).strip()]

    if template is None:
        return (
            None,
            f"Role type {normalized_role_type} is not on the current local MVP staffing path.",
        )

    expected_refs = list(template["role_profile_refs"])
    if normalized_refs != expected_refs:
        return (
            None,
            f"Role type {normalized_role_type} must use role profile refs {expected_refs} on the current local MVP staffing path.",
        )

    return template, None
