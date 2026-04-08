from __future__ import annotations

from typing import Any

from app.core.persona_profiles import (
    clone_persona_template,
    get_hire_persona_template_id,
)


_BOARD_WORKFORCE_STAFFING_HIRE_TEMPLATES: tuple[dict[str, Any], ...] = (
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
    {
        "template_id": "backend_engineer_backup",
        "label": "Backend Engineer / 服务交付",
        "role_type": "backend_engineer",
        "role_profile_refs": ["backend_engineer_primary"],
        "employee_id_hint": "emp_backend_backup",
        "provider_id": "prov_openai_compat",
        "request_summary": "Hire a backend engineer for service delivery.",
        **clone_persona_template(get_hire_persona_template_id("backend_engineer")),
    },
    {
        "template_id": "database_engineer_backup",
        "label": "Database Engineer / 数据可靠性",
        "role_type": "database_engineer",
        "role_profile_refs": ["database_engineer_primary"],
        "employee_id_hint": "emp_database_backup",
        "provider_id": "prov_openai_compat",
        "request_summary": "Hire a database engineer for migration and reliability work.",
        **clone_persona_template(get_hire_persona_template_id("database_engineer")),
    },
    {
        "template_id": "platform_sre_backup",
        "label": "Platform / SRE",
        "role_type": "platform_sre",
        "role_profile_refs": ["platform_sre_primary"],
        "employee_id_hint": "emp_platform_backup",
        "provider_id": "prov_openai_compat",
        "request_summary": "Hire a platform engineer for runtime and operations stability.",
        **clone_persona_template(get_hire_persona_template_id("platform_sre")),
    },
    {
        "template_id": "architect_governance_backup",
        "label": "架构师 / 设计评审",
        "role_type": "governance_architect",
        "role_profile_refs": ["architect_primary"],
        "employee_id_hint": "emp_architect_governance",
        "provider_id": "prov_openai_compat",
        "request_summary": "Hire an architect governance role for design review and alignment.",
        **clone_persona_template(get_hire_persona_template_id("governance_architect")),
    },
    {
        "template_id": "cto_governance_backup",
        "label": "CTO / 架构治理",
        "role_type": "governance_cto",
        "role_profile_refs": ["cto_primary"],
        "employee_id_hint": "emp_cto_governance",
        "provider_id": "prov_openai_compat",
        "request_summary": "Hire a CTO governance role for architecture direction.",
        **clone_persona_template(get_hire_persona_template_id("governance_cto")),
    },
)

_CEO_LIMITED_STAFFING_ROLE_TYPES = frozenset(
    {
        "frontend_engineer",
        "checker",
        "backend_engineer",
        "database_engineer",
        "platform_sre",
        "governance_architect",
        "governance_cto",
    }
)


def _clone_template(template: dict[str, Any]) -> dict[str, Any]:
    return {
        **template,
        "role_profile_refs": list(template.get("role_profile_refs") or []),
        "skill_profile": dict(template.get("skill_profile") or {}),
        "personality_profile": dict(template.get("personality_profile") or {}),
        "aesthetic_profile": dict(template.get("aesthetic_profile") or {}),
    }


def _get_staffing_template_for_role(
    templates: tuple[dict[str, Any], ...],
    role_type: str,
) -> dict[str, Any] | None:
    normalized_role_type = str(role_type or "").strip()
    for template in templates:
        if template["role_type"] == normalized_role_type:
            return _clone_template(template)
    return None


def _resolve_staffing_combo(
    templates: tuple[dict[str, Any], ...],
    role_type: str,
    role_profile_refs: list[str] | tuple[str, ...],
    *,
    unsupported_reason: str,
    mismatch_reason: str,
) -> tuple[dict[str, Any] | None, str | None]:
    template = _get_staffing_template_for_role(templates, role_type)
    normalized_role_type = str(role_type or "").strip()
    normalized_refs = [str(value).strip() for value in role_profile_refs if str(value).strip()]

    if template is None:
        return None, unsupported_reason.format(role_type=normalized_role_type)

    expected_refs = list(template["role_profile_refs"])
    if normalized_refs != expected_refs:
        return None, mismatch_reason.format(role_type=normalized_role_type, expected_refs=expected_refs)

    return template, None


def list_board_workforce_staffing_hire_templates() -> list[dict[str, Any]]:
    return [_clone_template(template) for template in _BOARD_WORKFORCE_STAFFING_HIRE_TEMPLATES]


def get_board_workforce_staffing_template_for_role(role_type: str) -> dict[str, Any] | None:
    return _get_staffing_template_for_role(_BOARD_WORKFORCE_STAFFING_HIRE_TEMPLATES, role_type)


def board_workforce_staffing_template_id_for_role(role_type: str) -> str | None:
    template = get_board_workforce_staffing_template_for_role(role_type)
    if template is None:
        return None
    return str(template["template_id"])


def resolve_board_workforce_staffing_combo(
    role_type: str,
    role_profile_refs: list[str] | tuple[str, ...],
) -> tuple[dict[str, Any] | None, str | None]:
    return _resolve_staffing_combo(
        _BOARD_WORKFORCE_STAFFING_HIRE_TEMPLATES,
        role_type,
        role_profile_refs,
        unsupported_reason="Role type {role_type} is not on the current local MVP staffing path.",
        mismatch_reason=(
            "Role type {role_type} must use role profile refs {expected_refs} "
            "on the current local MVP staffing path."
        ),
    )


def resolve_limited_ceo_staffing_combo(
    role_type: str,
    role_profile_refs: list[str] | tuple[str, ...],
) -> tuple[dict[str, Any] | None, str | None]:
    if str(role_type or "").strip() not in _CEO_LIMITED_STAFFING_ROLE_TYPES:
        return (
            None,
            f"Role type {str(role_type or '').strip()} is not on the current limited CEO staffing path.",
        )
    return _resolve_staffing_combo(
        _BOARD_WORKFORCE_STAFFING_HIRE_TEMPLATES,
        role_type,
        role_profile_refs,
        unsupported_reason="Role type {role_type} is not on the current limited CEO staffing path.",
        mismatch_reason=(
            "Role type {role_type} must use role profile refs {expected_refs} "
            "on the current limited CEO staffing path."
        ),
    )
