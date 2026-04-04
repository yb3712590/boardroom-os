from app.core.persona_profiles import (
    build_high_overlap_rejection_reason,
    find_same_role_high_overlap_conflict,
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
