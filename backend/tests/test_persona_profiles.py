from app.core.persona_profiles import (
    build_default_employee_roster,
    build_seeded_persona_variant,
    build_high_overlap_rejection_reason,
    clone_persona_template,
    find_same_role_high_overlap_conflict,
    get_hire_persona_template_id,
    normalize_persona_profiles,
)


def test_normalize_persona_profiles_backfills_legacy_frontend_fields():
    normalized = normalize_persona_profiles(
        "frontend_engineer",
        skill_profile={"primary_domain": "frontend"},
        personality_profile={"style": "maker"},
        aesthetic_profile={"preference": "minimal"},
    )

    assert normalized["skill_profile"] == {
        "primary_domain": "frontend",
        "system_scope": "delivery_slice",
        "validation_bias": "balanced",
    }
    assert normalized["personality_profile"] == {
        "risk_posture": "assertive",
        "challenge_style": "constructive",
        "execution_pace": "fast",
        "detail_rigor": "focused",
        "communication_style": "direct",
    }
    assert normalized["aesthetic_profile"] == {
        "surface_preference": "functional",
        "information_density": "balanced",
        "motion_tolerance": "measured",
    }
    assert normalized["profile_summary"].startswith("Skill frontend")


def test_find_same_role_high_overlap_conflict_detects_active_board_approved_duplicate():
    conflict = find_same_role_high_overlap_conflict(
        role_type="frontend_engineer",
        skill_profile={"primary_domain": "frontend"},
        personality_profile={"style": "maker"},
        aesthetic_profile={"preference": "minimal"},
        employees=[
            {
                "employee_id": "emp_frontend_2",
                "role_type": "frontend_engineer",
                "state": "ACTIVE",
                "board_approved": True,
                "skill_profile_json": {"primary_domain": "frontend"},
                "personality_profile_json": {"style": "maker"},
                "aesthetic_profile_json": {"preference": "minimal"},
            }
        ],
    )

    assert conflict is not None
    assert conflict["employee_id"] == "emp_frontend_2"
    assert conflict["personality_overlap_count"] == 5
    assert conflict["aesthetic_overlap_count"] == 3
    assert "too similar" in build_high_overlap_rejection_reason(
        role_type="frontend_engineer",
        conflict=conflict,
    ).lower()


def test_normalize_persona_profiles_supports_reserved_and_governance_roles():
    normalized = normalize_persona_profiles(
        "governance_cto",
        skill_profile={"primary_domain": "architecture"},
        personality_profile={"risk_posture": "guarded"},
        aesthetic_profile={"surface_preference": "clarifying"},
    )

    assert normalized["skill_profile"] == {
        "primary_domain": "architecture",
        "system_scope": "governance_direction",
        "validation_bias": "balanced",
    }
    assert normalized["personality_profile"] == {
        "risk_posture": "guarded",
        "challenge_style": "probing",
        "execution_pace": "deliberate",
        "detail_rigor": "rigorous",
        "communication_style": "direct",
    }
    assert normalized["aesthetic_profile"] == {
        "surface_preference": "clarifying",
        "information_density": "layered",
        "motion_tolerance": "restrained",
    }
    assert "architecture" in normalized["profile_summary"].lower()


def test_build_seeded_persona_variant_is_deterministic_and_diverges_from_base_template():
    template_id = get_hire_persona_template_id("frontend_engineer")
    base_template = clone_persona_template(template_id)
    base_normalized = normalize_persona_profiles(
        "frontend_engineer",
        template_id=template_id,
        skill_profile=base_template["skill_profile"],
        personality_profile=base_template["personality_profile"],
        aesthetic_profile=base_template["aesthetic_profile"],
    )

    first = build_seeded_persona_variant(
        "frontend_engineer",
        template_id=template_id,
        variant_key="emp_frontend_variant_01",
        seed=17,
    )
    second = build_seeded_persona_variant(
        "frontend_engineer",
        template_id=template_id,
        variant_key="emp_frontend_variant_01",
        seed=17,
    )
    third = build_seeded_persona_variant(
        "frontend_engineer",
        template_id=template_id,
        variant_key="emp_frontend_variant_02",
        seed=17,
    )

    assert first == second
    assert first["template_id"] == template_id
    assert first["personality_profile"] != base_normalized["personality_profile"]
    assert first["aesthetic_profile"] != base_normalized["aesthetic_profile"]
    assert third["profile_summary"] != first["profile_summary"]


def test_build_default_employee_roster_supports_provider_override(monkeypatch):
    monkeypatch.setenv("BOARDROOM_OS_DEFAULT_EMPLOYEE_PROVIDER_ID", "prov_openai_compat_truerealbill")

    roster = build_default_employee_roster()

    assert {employee["provider_id"] for employee in roster} == {"prov_openai_compat_truerealbill"}
