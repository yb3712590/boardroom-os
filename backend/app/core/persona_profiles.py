from __future__ import annotations

import hashlib
import random
from copy import deepcopy
from typing import Any, Iterable, Mapping


SKILL_PROFILE_DIMENSIONS = (
    "primary_domain",
    "system_scope",
    "validation_bias",
)
PERSONALITY_PROFILE_DIMENSIONS = (
    "risk_posture",
    "challenge_style",
    "execution_pace",
    "detail_rigor",
    "communication_style",
)
AESTHETIC_PROFILE_DIMENSIONS = (
    "surface_preference",
    "information_density",
    "motion_tolerance",
)

PERSONALITY_HIGH_OVERLAP_THRESHOLD = 4
AESTHETIC_HIGH_OVERLAP_THRESHOLD = 2

_ALLOWED_VALUES_BY_DIMENSION = {
    "primary_domain": {"frontend", "quality", "backend", "data", "platform", "architecture"},
    "system_scope": {
        "delivery_slice",
        "surface_polish",
        "release_guard",
        "release_sweep",
        "service_delivery",
        "data_reliability",
        "runtime_operations",
        "design_review",
        "governance_direction",
    },
    "validation_bias": {"balanced", "finish_first", "evidence_first", "regression_first"},
    "risk_posture": {"assertive", "cautious", "guarded"},
    "challenge_style": {"constructive", "probing", "adversarial"},
    "execution_pace": {"fast", "measured", "deliberate"},
    "detail_rigor": {"focused", "rigorous", "sweeping"},
    "communication_style": {"direct", "concise", "forensic"},
    "surface_preference": {"functional", "polished", "systematic", "clarifying"},
    "information_density": {"balanced", "layered", "dense"},
    "motion_tolerance": {"measured", "restrained", "minimal"},
}

_PERSONA_TEMPLATES: dict[str, dict[str, dict[str, str]]] = {
    "frontend_core_builder": {
        "skill_profile": {
            "primary_domain": "frontend",
            "system_scope": "delivery_slice",
            "validation_bias": "balanced",
        },
        "personality_profile": {
            "risk_posture": "assertive",
            "challenge_style": "constructive",
            "execution_pace": "fast",
            "detail_rigor": "focused",
            "communication_style": "direct",
        },
        "aesthetic_profile": {
            "surface_preference": "functional",
            "information_density": "balanced",
            "motion_tolerance": "measured",
        },
    },
    "frontend_polish_counterweight": {
        "skill_profile": {
            "primary_domain": "frontend",
            "system_scope": "surface_polish",
            "validation_bias": "finish_first",
        },
        "personality_profile": {
            "risk_posture": "cautious",
            "challenge_style": "probing",
            "execution_pace": "measured",
            "detail_rigor": "rigorous",
            "communication_style": "concise",
        },
        "aesthetic_profile": {
            "surface_preference": "polished",
            "information_density": "layered",
            "motion_tolerance": "restrained",
        },
    },
    "checker_evidence_guard": {
        "skill_profile": {
            "primary_domain": "quality",
            "system_scope": "release_guard",
            "validation_bias": "evidence_first",
        },
        "personality_profile": {
            "risk_posture": "guarded",
            "challenge_style": "probing",
            "execution_pace": "measured",
            "detail_rigor": "rigorous",
            "communication_style": "forensic",
        },
        "aesthetic_profile": {
            "surface_preference": "systematic",
            "information_density": "dense",
            "motion_tolerance": "minimal",
        },
    },
    "checker_release_sweeper": {
        "skill_profile": {
            "primary_domain": "quality",
            "system_scope": "release_sweep",
            "validation_bias": "regression_first",
        },
        "personality_profile": {
            "risk_posture": "cautious",
            "challenge_style": "constructive",
            "execution_pace": "deliberate",
            "detail_rigor": "sweeping",
            "communication_style": "concise",
        },
        "aesthetic_profile": {
            "surface_preference": "clarifying",
            "information_density": "balanced",
            "motion_tolerance": "restrained",
        },
    },
    "backend_service_builder": {
        "skill_profile": {
            "primary_domain": "backend",
            "system_scope": "service_delivery",
            "validation_bias": "balanced",
        },
        "personality_profile": {
            "risk_posture": "assertive",
            "challenge_style": "constructive",
            "execution_pace": "fast",
            "detail_rigor": "focused",
            "communication_style": "direct",
        },
        "aesthetic_profile": {
            "surface_preference": "functional",
            "information_density": "balanced",
            "motion_tolerance": "measured",
        },
    },
    "backend_integration_counterweight": {
        "skill_profile": {
            "primary_domain": "backend",
            "system_scope": "service_delivery",
            "validation_bias": "evidence_first",
        },
        "personality_profile": {
            "risk_posture": "cautious",
            "challenge_style": "probing",
            "execution_pace": "measured",
            "detail_rigor": "rigorous",
            "communication_style": "concise",
        },
        "aesthetic_profile": {
            "surface_preference": "systematic",
            "information_density": "layered",
            "motion_tolerance": "restrained",
        },
    },
    "database_reliability_guard": {
        "skill_profile": {
            "primary_domain": "data",
            "system_scope": "data_reliability",
            "validation_bias": "evidence_first",
        },
        "personality_profile": {
            "risk_posture": "guarded",
            "challenge_style": "probing",
            "execution_pace": "measured",
            "detail_rigor": "rigorous",
            "communication_style": "forensic",
        },
        "aesthetic_profile": {
            "surface_preference": "systematic",
            "information_density": "dense",
            "motion_tolerance": "minimal",
        },
    },
    "database_change_guard": {
        "skill_profile": {
            "primary_domain": "data",
            "system_scope": "data_reliability",
            "validation_bias": "regression_first",
        },
        "personality_profile": {
            "risk_posture": "cautious",
            "challenge_style": "constructive",
            "execution_pace": "deliberate",
            "detail_rigor": "sweeping",
            "communication_style": "concise",
        },
        "aesthetic_profile": {
            "surface_preference": "clarifying",
            "information_density": "balanced",
            "motion_tolerance": "restrained",
        },
    },
    "platform_operations_guard": {
        "skill_profile": {
            "primary_domain": "platform",
            "system_scope": "runtime_operations",
            "validation_bias": "evidence_first",
        },
        "personality_profile": {
            "risk_posture": "guarded",
            "challenge_style": "probing",
            "execution_pace": "measured",
            "detail_rigor": "rigorous",
            "communication_style": "forensic",
        },
        "aesthetic_profile": {
            "surface_preference": "systematic",
            "information_density": "dense",
            "motion_tolerance": "minimal",
        },
    },
    "platform_reliability_counterweight": {
        "skill_profile": {
            "primary_domain": "platform",
            "system_scope": "runtime_operations",
            "validation_bias": "regression_first",
        },
        "personality_profile": {
            "risk_posture": "cautious",
            "challenge_style": "constructive",
            "execution_pace": "deliberate",
            "detail_rigor": "sweeping",
            "communication_style": "concise",
        },
        "aesthetic_profile": {
            "surface_preference": "clarifying",
            "information_density": "balanced",
            "motion_tolerance": "restrained",
        },
    },
    "architecture_design_reviewer": {
        "skill_profile": {
            "primary_domain": "architecture",
            "system_scope": "design_review",
            "validation_bias": "evidence_first",
        },
        "personality_profile": {
            "risk_posture": "guarded",
            "challenge_style": "probing",
            "execution_pace": "measured",
            "detail_rigor": "rigorous",
            "communication_style": "direct",
        },
        "aesthetic_profile": {
            "surface_preference": "clarifying",
            "information_density": "layered",
            "motion_tolerance": "restrained",
        },
    },
    "architecture_governance_director": {
        "skill_profile": {
            "primary_domain": "architecture",
            "system_scope": "governance_direction",
            "validation_bias": "balanced",
        },
        "personality_profile": {
            "risk_posture": "guarded",
            "challenge_style": "probing",
            "execution_pace": "deliberate",
            "detail_rigor": "rigorous",
            "communication_style": "direct",
        },
        "aesthetic_profile": {
            "surface_preference": "clarifying",
            "information_density": "layered",
            "motion_tolerance": "restrained",
        },
    },
}

_BASELINE_TEMPLATE_BY_ROLE_TYPE = {
    "frontend_engineer": "frontend_core_builder",
    "checker": "checker_evidence_guard",
    "backend_engineer": "backend_service_builder",
    "database_engineer": "database_reliability_guard",
    "platform_sre": "platform_operations_guard",
    "governance_architect": "architecture_design_reviewer",
    "governance_cto": "architecture_governance_director",
}
_HIRE_TEMPLATE_BY_ROLE_TYPE = {
    "frontend_engineer": "frontend_polish_counterweight",
    "checker": "checker_release_sweeper",
    "backend_engineer": "backend_integration_counterweight",
    "database_engineer": "database_change_guard",
    "platform_sre": "platform_reliability_counterweight",
    "governance_architect": "architecture_design_reviewer",
    "governance_cto": "architecture_governance_director",
}
_LEGACY_STYLE_TEMPLATE_BY_ROLE_TYPE = {
    ("frontend_engineer", "maker"): "frontend_core_builder",
    ("checker", "checker"): "checker_evidence_guard",
}
_LEGACY_PREFERENCE_TEMPLATE_BY_ROLE_TYPE = {
    ("frontend_engineer", "minimal"): "frontend_core_builder",
    ("checker", "structured"): "checker_evidence_guard",
    ("checker", "systematic"): "checker_evidence_guard",
}


def _normalize_string(value: Any) -> str | None:
    normalized = str(value or "").strip().lower()
    return normalized or None


def _humanize(value: str) -> str:
    return value.replace("_", " ")


def clone_persona_template(template_id: str) -> dict[str, dict[str, str]]:
    template = _PERSONA_TEMPLATES.get(template_id)
    if template is None:
        raise KeyError(f"Unknown persona template: {template_id}")
    return deepcopy(template)


def get_baseline_persona_template_id(role_type: str) -> str:
    normalized_role_type = str(role_type or "").strip()
    return _BASELINE_TEMPLATE_BY_ROLE_TYPE.get(normalized_role_type, "frontend_core_builder")


def get_hire_persona_template_id(role_type: str) -> str:
    normalized_role_type = str(role_type or "").strip()
    return _HIRE_TEMPLATE_BY_ROLE_TYPE.get(normalized_role_type, get_baseline_persona_template_id(normalized_role_type))


def build_default_employee_roster() -> tuple[dict[str, Any], ...]:
    frontend = clone_persona_template(get_baseline_persona_template_id("frontend_engineer"))
    checker = clone_persona_template(get_baseline_persona_template_id("checker"))
    return (
        {
            "employee_id": "emp_frontend_2",
            "role_type": "frontend_engineer",
            "skill_profile_json": frontend["skill_profile"],
            "personality_profile_json": frontend["personality_profile"],
            "aesthetic_profile_json": frontend["aesthetic_profile"],
            "state": "ACTIVE",
            "board_approved": True,
            "provider_id": "prov_openai_compat",
            "role_profile_refs_json": ["frontend_engineer_primary"],
        },
        {
            "employee_id": "emp_checker_1",
            "role_type": "checker",
            "skill_profile_json": checker["skill_profile"],
            "personality_profile_json": checker["personality_profile"],
            "aesthetic_profile_json": checker["aesthetic_profile"],
            "state": "ACTIVE",
            "board_approved": True,
            "provider_id": "prov_openai_compat",
            "role_profile_refs_json": ["checker_primary"],
        },
    )


def _stable_variant_rng(*parts: object) -> random.Random:
    digest = hashlib.sha256(
        "::".join(str(part) for part in parts).encode("utf-8")
    ).hexdigest()
    return random.Random(int(digest[:16], 16))


def _pick_alternative_value(
    *,
    dimension: str,
    current_value: str,
    rng: random.Random,
) -> str:
    choices = sorted(
        value
        for value in _ALLOWED_VALUES_BY_DIMENSION[dimension]
        if value != current_value
    )
    return rng.choice(choices) if choices else current_value


def build_seeded_persona_variant(
    role_type: str,
    *,
    variant_key: str,
    seed: int,
    template_id: str | None = None,
    skill_profile: Mapping[str, Any] | None = None,
    personality_profile: Mapping[str, Any] | None = None,
    aesthetic_profile: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    base = normalize_persona_profiles(
        role_type,
        template_id=template_id,
        skill_profile=skill_profile,
        personality_profile=personality_profile,
        aesthetic_profile=aesthetic_profile,
    )
    rng = _stable_variant_rng(seed, role_type, variant_key, base["template_id"])

    variant_skill_profile = dict(base["skill_profile"])
    variant_personality_profile = dict(base["personality_profile"])
    variant_aesthetic_profile = dict(base["aesthetic_profile"])

    variant_skill_profile["validation_bias"] = _pick_alternative_value(
        dimension="validation_bias",
        current_value=variant_skill_profile["validation_bias"],
        rng=rng,
    )

    personality_dimensions = list(PERSONALITY_PROFILE_DIMENSIONS)
    rng.shuffle(personality_dimensions)
    for dimension in personality_dimensions[:3]:
        variant_personality_profile[dimension] = _pick_alternative_value(
            dimension=dimension,
            current_value=variant_personality_profile[dimension],
            rng=rng,
        )

    aesthetic_dimensions = list(AESTHETIC_PROFILE_DIMENSIONS)
    rng.shuffle(aesthetic_dimensions)
    for dimension in aesthetic_dimensions[:2]:
        variant_aesthetic_profile[dimension] = _pick_alternative_value(
            dimension=dimension,
            current_value=variant_aesthetic_profile[dimension],
            rng=rng,
        )

    return normalize_persona_profiles(
        role_type,
        template_id=base["template_id"],
        skill_profile=variant_skill_profile,
        personality_profile=variant_personality_profile,
        aesthetic_profile=variant_aesthetic_profile,
    )


def _resolve_legacy_template_id(
    role_type: str,
    skill_profile: Mapping[str, Any],
    personality_profile: Mapping[str, Any],
    aesthetic_profile: Mapping[str, Any],
) -> str | None:
    style = _normalize_string(personality_profile.get("style"))
    if style is not None:
        template_id = _LEGACY_STYLE_TEMPLATE_BY_ROLE_TYPE.get((role_type, style))
        if template_id is not None:
            return template_id
    preference = _normalize_string(aesthetic_profile.get("preference"))
    if preference is not None:
        template_id = _LEGACY_PREFERENCE_TEMPLATE_BY_ROLE_TYPE.get((role_type, preference))
        if template_id is not None:
            return template_id
    primary_domain = _normalize_string(skill_profile.get("primary_domain"))
    if role_type == "checker" or primary_domain == "quality":
        return "checker_evidence_guard"
    if role_type == "frontend_engineer" or primary_domain == "frontend":
        return "frontend_core_builder"
    if role_type == "backend_engineer" or primary_domain == "backend":
        return "backend_service_builder"
    if role_type == "database_engineer" or primary_domain == "data":
        return "database_reliability_guard"
    if role_type == "platform_sre" or primary_domain == "platform":
        return "platform_operations_guard"
    if role_type == "governance_architect":
        return "architecture_design_reviewer"
    if role_type == "governance_cto" or primary_domain == "architecture":
        return "architecture_governance_director"
    return None


def _normalize_profile_group(
    raw_profile: Mapping[str, Any],
    default_profile: Mapping[str, str],
    dimensions: tuple[str, ...],
) -> dict[str, str]:
    normalized: dict[str, str] = {}
    for dimension in dimensions:
        raw_value = _normalize_string(raw_profile.get(dimension))
        if raw_value in _ALLOWED_VALUES_BY_DIMENSION[dimension]:
            normalized[dimension] = raw_value
        else:
            normalized[dimension] = str(default_profile[dimension])
    return normalized


def normalize_persona_profiles(
    role_type: str,
    *,
    skill_profile: Mapping[str, Any] | None = None,
    personality_profile: Mapping[str, Any] | None = None,
    aesthetic_profile: Mapping[str, Any] | None = None,
    template_id: str | None = None,
) -> dict[str, Any]:
    raw_skill = dict(skill_profile or {})
    raw_personality = dict(personality_profile or {})
    raw_aesthetic = dict(aesthetic_profile or {})
    effective_template_id = template_id or _resolve_legacy_template_id(
        str(role_type or "").strip(),
        raw_skill,
        raw_personality,
        raw_aesthetic,
    )
    if effective_template_id is None:
        effective_template_id = get_baseline_persona_template_id(role_type)
    defaults = clone_persona_template(effective_template_id)

    normalized_skill = _normalize_profile_group(raw_skill, defaults["skill_profile"], SKILL_PROFILE_DIMENSIONS)
    normalized_personality = _normalize_profile_group(
        raw_personality,
        defaults["personality_profile"],
        PERSONALITY_PROFILE_DIMENSIONS,
    )
    normalized_aesthetic = _normalize_profile_group(
        raw_aesthetic,
        defaults["aesthetic_profile"],
        AESTHETIC_PROFILE_DIMENSIONS,
    )

    return {
        "skill_profile": normalized_skill,
        "personality_profile": normalized_personality,
        "aesthetic_profile": normalized_aesthetic,
        "profile_summary": build_persona_summary(
            skill_profile=normalized_skill,
            personality_profile=normalized_personality,
            aesthetic_profile=normalized_aesthetic,
        ),
        "template_id": effective_template_id,
    }


def build_persona_summary(
    *,
    skill_profile: Mapping[str, str],
    personality_profile: Mapping[str, str],
    aesthetic_profile: Mapping[str, str],
) -> str:
    skill_summary = ", ".join(_humanize(str(skill_profile[dimension])) for dimension in SKILL_PROFILE_DIMENSIONS)
    personality_summary = ", ".join(
        _humanize(str(personality_profile[dimension])) for dimension in PERSONALITY_PROFILE_DIMENSIONS
    )
    aesthetic_summary = ", ".join(
        _humanize(str(aesthetic_profile[dimension])) for dimension in AESTHETIC_PROFILE_DIMENSIONS
    )
    return (
        f"Skill {skill_summary}. "
        f"Personality {personality_summary}. "
        f"Aesthetic {aesthetic_summary}."
    )


def normalize_employee_projection_profiles(employee: Mapping[str, Any]) -> dict[str, Any]:
    normalized = normalize_persona_profiles(
        str(employee.get("role_type") or ""),
        skill_profile=employee.get("skill_profile_json"),
        personality_profile=employee.get("personality_profile_json"),
        aesthetic_profile=employee.get("aesthetic_profile_json"),
    )
    return {
        **dict(employee),
        "skill_profile_json": normalized["skill_profile"],
        "personality_profile_json": normalized["personality_profile"],
        "aesthetic_profile_json": normalized["aesthetic_profile"],
        "profile_summary": normalized["profile_summary"],
    }


def count_matching_profile_dimensions(
    first_profile: Mapping[str, str],
    second_profile: Mapping[str, str],
    dimensions: Iterable[str],
) -> int:
    return sum(1 for dimension in dimensions if first_profile.get(dimension) == second_profile.get(dimension))


def find_same_role_high_overlap_conflict(
    *,
    role_type: str,
    skill_profile: Mapping[str, Any],
    personality_profile: Mapping[str, Any],
    aesthetic_profile: Mapping[str, Any],
    employees: Iterable[Mapping[str, Any]],
    exclude_employee_ids: Iterable[str] = (),
) -> dict[str, Any] | None:
    normalized_candidate = normalize_persona_profiles(
        role_type,
        skill_profile=skill_profile,
        personality_profile=personality_profile,
        aesthetic_profile=aesthetic_profile,
    )
    excluded_ids = {str(employee_id).strip() for employee_id in exclude_employee_ids if str(employee_id).strip()}

    conflicts: list[dict[str, Any]] = []
    for employee in employees:
        employee_id = str(employee.get("employee_id") or "").strip()
        if not employee_id or employee_id in excluded_ids:
            continue
        if str(employee.get("state") or "").strip().upper() != "ACTIVE":
            continue
        if not bool(employee.get("board_approved")):
            continue
        if str(employee.get("role_type") or "").strip() != str(role_type or "").strip():
            continue

        normalized_existing = normalize_persona_profiles(
            role_type,
            skill_profile=employee.get("skill_profile_json") or employee.get("skill_profile"),
            personality_profile=employee.get("personality_profile_json") or employee.get("personality_profile"),
            aesthetic_profile=employee.get("aesthetic_profile_json") or employee.get("aesthetic_profile"),
        )
        if (
            normalized_existing["skill_profile"]["primary_domain"]
            != normalized_candidate["skill_profile"]["primary_domain"]
        ):
            continue

        personality_overlap_count = count_matching_profile_dimensions(
            normalized_candidate["personality_profile"],
            normalized_existing["personality_profile"],
            PERSONALITY_PROFILE_DIMENSIONS,
        )
        aesthetic_overlap_count = count_matching_profile_dimensions(
            normalized_candidate["aesthetic_profile"],
            normalized_existing["aesthetic_profile"],
            AESTHETIC_PROFILE_DIMENSIONS,
        )
        if (
            personality_overlap_count >= PERSONALITY_HIGH_OVERLAP_THRESHOLD
            and aesthetic_overlap_count >= AESTHETIC_HIGH_OVERLAP_THRESHOLD
        ):
            conflicts.append(
                {
                    "employee_id": employee_id,
                    "personality_overlap_count": personality_overlap_count,
                    "aesthetic_overlap_count": aesthetic_overlap_count,
                    "existing_profile_summary": normalized_existing["profile_summary"],
                    "candidate_profile_summary": normalized_candidate["profile_summary"],
                }
            )

    if not conflicts:
        return None

    conflicts.sort(
        key=lambda item: (
            -int(item["personality_overlap_count"]),
            -int(item["aesthetic_overlap_count"]),
            str(item["employee_id"]),
        )
    )
    return conflicts[0]


def build_high_overlap_rejection_reason(
    *,
    role_type: str,
    conflict: Mapping[str, Any],
) -> str:
    return (
        f"Candidate {role_type} profile is too similar to active board-approved worker "
        f"{conflict['employee_id']} on the current local MVP staffing path "
        f"(personality overlap {conflict['personality_overlap_count']}/5, "
        f"aesthetic overlap {conflict['aesthetic_overlap_count']}/3). "
        f"Existing profile: {conflict['existing_profile_summary']}"
    )
