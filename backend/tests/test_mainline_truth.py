from __future__ import annotations

from app.core.approval_handlers import FOLLOWUP_OWNER_ROLE_TO_PROFILE
from app.core.mainline_truth import (
    FROZEN_CAPABILITY_BOUNDARIES,
    MAINLINE_RUNTIME_SUPPORT_MATRIX,
    MAINLINE_WORKFLOW_STAGE_TRUTH,
)
from app.core.output_schemas import (
    CONSENSUS_DOCUMENT_SCHEMA_REF,
    DELIVERY_CHECK_REPORT_SCHEMA_REF,
    DELIVERY_CLOSEOUT_PACKAGE_SCHEMA_REF,
    IMPLEMENTATION_BUNDLE_SCHEMA_REF,
    MAKER_CHECKER_VERDICT_SCHEMA_REF,
    UI_MILESTONE_REVIEW_SCHEMA_REF,
)
from app.core.runtime import SUPPORTED_RUNTIME_OUTPUT_SCHEMAS, SUPPORTED_RUNTIME_ROLE_PROFILES
from app.main import create_app


def test_mainline_runtime_support_matrix_matches_runtime_constants() -> None:
    expected_role_profiles = {entry.role_profile_ref for entry in MAINLINE_RUNTIME_SUPPORT_MATRIX}
    expected_output_schemas = {entry.output_schema_ref for entry in MAINLINE_RUNTIME_SUPPORT_MATRIX}

    assert expected_role_profiles == SUPPORTED_RUNTIME_ROLE_PROFILES
    assert expected_output_schemas == SUPPORTED_RUNTIME_OUTPUT_SCHEMAS
    assert {
        (entry.role_profile_ref, entry.output_schema_ref)
        for entry in MAINLINE_RUNTIME_SUPPORT_MATRIX
    } == {
        ("ui_designer_primary", CONSENSUS_DOCUMENT_SCHEMA_REF),
        ("ui_designer_primary", IMPLEMENTATION_BUNDLE_SCHEMA_REF),
        ("ui_designer_primary", UI_MILESTONE_REVIEW_SCHEMA_REF),
        ("ui_designer_primary", DELIVERY_CLOSEOUT_PACKAGE_SCHEMA_REF),
        ("checker_primary", DELIVERY_CHECK_REPORT_SCHEMA_REF),
        ("checker_primary", MAKER_CHECKER_VERDICT_SCHEMA_REF),
    }


def test_mainline_truth_records_frontend_followup_mapping_as_current_reality() -> None:
    stage_truth_by_id = {entry.stage_id: entry for entry in MAINLINE_WORKFLOW_STAGE_TRUTH}
    build_stage = stage_truth_by_id["build_internal_maker_checker"]

    assert FOLLOWUP_OWNER_ROLE_TO_PROFILE["frontend_engineer"] == "ui_designer_primary"
    assert "frontend_engineer" in build_stage.actual_owner_roles
    assert "ui_designer_primary" in build_stage.actual_role_profiles
    assert "不是独立 worker" in build_stage.notes


def test_frozen_capability_boundaries_match_current_mounted_routes() -> None:
    app = create_app()
    route_paths = {route.path for route in app.routes}
    boundaries_by_slug = {entry.slug: entry for entry in FROZEN_CAPABILITY_BOUNDARIES}

    assert set(boundaries_by_slug) == {
        "worker_admin",
        "multi_tenant_scope",
        "artifact_uploads_and_object_store",
        "external_worker_handoff",
    }
    assert boundaries_by_slug["worker_admin"].route_prefixes == ("/api/v1/worker-admin",)
    assert boundaries_by_slug["artifact_uploads_and_object_store"].route_prefixes == (
        "/api/v1/artifact-uploads",
    )
    assert boundaries_by_slug["external_worker_handoff"].route_prefixes == ("/api/v1/worker-runtime",)
    assert boundaries_by_slug["multi_tenant_scope"].route_prefixes == ()

    for entry in FROZEN_CAPABILITY_BOUNDARIES:
        for route_prefix in entry.route_prefixes:
            assert any(path.startswith(route_prefix) for path in route_paths)
