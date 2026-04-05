from __future__ import annotations

from pathlib import Path

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


REPO_ROOT = Path(__file__).resolve().parents[2]


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
        ("frontend_engineer_primary", IMPLEMENTATION_BUNDLE_SCHEMA_REF),
        ("frontend_engineer_primary", UI_MILESTONE_REVIEW_SCHEMA_REF),
        ("frontend_engineer_primary", DELIVERY_CLOSEOUT_PACKAGE_SCHEMA_REF),
        ("checker_primary", DELIVERY_CHECK_REPORT_SCHEMA_REF),
        ("checker_primary", MAKER_CHECKER_VERDICT_SCHEMA_REF),
    }


def test_mainline_truth_records_frontend_followup_mapping_as_current_reality() -> None:
    stage_truth_by_id = {entry.stage_id: entry for entry in MAINLINE_WORKFLOW_STAGE_TRUTH}
    build_stage = stage_truth_by_id["build_internal_maker_checker"]

    assert FOLLOWUP_OWNER_ROLE_TO_PROFILE["frontend_engineer"] == "frontend_engineer_primary"
    assert "frontend_engineer" in build_stage.actual_owner_roles
    assert "frontend_engineer_primary" in build_stage.actual_role_profiles
    assert "独立 runtime worker" in build_stage.notes


def test_frozen_capability_boundaries_match_current_mounted_routes_and_documented_refs() -> None:
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

    assert boundaries_by_slug["worker_admin"].entrypoint_refs == (
        "backend/app/api/worker_admin.py",
        "backend/app/api/worker_admin_projections.py",
        "backend/app/worker_admin_auth_cli.py",
    )
    assert boundaries_by_slug["worker_admin"].mainline_dependency_refs == ()
    assert boundaries_by_slug["worker_admin"].test_refs == (
        "backend/tests/test_api.py",
        "backend/tests/test_worker_admin_auth_cli.py",
        "backend/tests/test_repository.py",
    )
    assert boundaries_by_slug["worker_admin"].migration_preconditions == (
        "Worker-admin API, auth projection, and CLI entrypoints must either move together or stay in place.",
        "No current mainline workflow path may import worker_admin modules directly before any physical migration starts.",
    )

    assert boundaries_by_slug["multi_tenant_scope"].entrypoint_refs == (
        "backend/app/api/projections.py",
        "backend/app/contracts/commands.py",
        "backend/app/contracts/runtime.py",
        "backend/app/contracts/worker_admin.py",
        "backend/app/contracts/worker_runtime.py",
    )
    assert boundaries_by_slug["multi_tenant_scope"].mainline_dependency_refs == (
        "backend/app/core/ticket_handlers.py",
        "backend/app/core/approval_handlers.py",
        "backend/app/core/ceo_execution_presets.py",
    )
    assert boundaries_by_slug["multi_tenant_scope"].test_refs == (
        "backend/tests/test_api.py",
        "backend/tests/test_context_compiler.py",
        "backend/tests/test_repository.py",
    )
    assert boundaries_by_slug["multi_tenant_scope"].migration_preconditions == (
        "tenant_id/workspace_id must stay available in shared contracts and projections used by the current local MVP.",
        "Physical migration is blocked until multi-tenant scope is decoupled from command, runtime, and projection data shapes.",
    )

    assert boundaries_by_slug["artifact_uploads_and_object_store"].entrypoint_refs == (
        "backend/app/api/artifact_uploads.py",
        "backend/app/core/artifact_uploads.py",
        "backend/app/core/artifact_store.py",
    )
    assert boundaries_by_slug["artifact_uploads_and_object_store"].mainline_dependency_refs == (
        "backend/app/core/ticket_handlers.py",
    )
    assert boundaries_by_slug["artifact_uploads_and_object_store"].test_refs == (
        "backend/tests/test_api.py",
        "backend/tests/test_repository.py",
    )
    assert boundaries_by_slug["artifact_uploads_and_object_store"].migration_preconditions == (
        "The ticket result-submit path must stop calling require_completed_artifact_upload_session before artifact upload code can move.",
        "Object-store support must remain a minimal storage backend and must not be expanded during this cleanup round.",
    )

    assert boundaries_by_slug["external_worker_handoff"].entrypoint_refs == (
        "backend/app/api/worker_runtime.py",
        "backend/app/api/projections.py",
        "backend/app/worker_auth_cli.py",
    )
    assert boundaries_by_slug["external_worker_handoff"].mainline_dependency_refs == ()
    assert boundaries_by_slug["external_worker_handoff"].test_refs == (
        "backend/tests/test_api.py",
        "backend/tests/test_worker_auth_cli.py",
        "backend/tests/conftest.py",
    )
    assert boundaries_by_slug["external_worker_handoff"].migration_preconditions == (
        "Worker-runtime delivery routes and the worker-runtime projection must stay aligned until the handoff surface is retired together.",
        "No physical migration should start while worker bootstrap, session, and delivery-grant storage still share the active repository schema.",
    )

    for entry in FROZEN_CAPABILITY_BOUNDARIES:
        for route_prefix in entry.route_prefixes:
            assert any(path.startswith(route_prefix) for path in route_paths)
        for ref in entry.code_refs + entry.entrypoint_refs + entry.mainline_dependency_refs + entry.test_refs:
            assert (REPO_ROOT / ref).exists(), ref


def test_frozen_capability_boundaries_capture_shared_scope_and_bridge_constraints() -> None:
    boundaries_by_slug = {entry.slug: entry for entry in FROZEN_CAPABILITY_BOUNDARIES}

    artifact_boundary = boundaries_by_slug["artifact_uploads_and_object_store"]
    assert artifact_boundary.mainline_dependency_refs == ("backend/app/core/ticket_handlers.py",)
    assert "require_completed_artifact_upload_session" in artifact_boundary.notes

    scope_boundary = boundaries_by_slug["multi_tenant_scope"]
    assert "shared data shape" in scope_boundary.notes
    assert any("Physical migration is blocked" in item for item in scope_boundary.migration_preconditions)


def test_worker_admin_boundary_uses_dedicated_projection_entrypoint() -> None:
    projection_entrypoint = REPO_ROOT / "backend/app/api/worker_admin_projections.py"

    assert projection_entrypoint.exists()


def test_worker_auth_cli_no_longer_imports_worker_admin_core_module() -> None:
    worker_auth_cli_source = (REPO_ROOT / "backend/app/worker_auth_cli.py").read_text(encoding="utf-8")

    assert "from app.core.worker_admin import" not in worker_auth_cli_source
    assert "from app.core.worker_scope_ops import" in worker_auth_cli_source
