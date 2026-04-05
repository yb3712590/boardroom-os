from __future__ import annotations

from pathlib import Path

from app.api.router_registry import ALL_ROUTE_GROUPS, FROZEN_ROUTE_GROUPS
from app.core.api_surface import API_SURFACE_GROUP_ORDER, collect_api_surface_groups
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


def _read_repo_text(ref: str) -> str:
    return (REPO_ROOT / ref).read_text(encoding="utf-8")


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
    api_surface_groups = collect_api_surface_groups(app)
    boundaries_by_slug = {entry.slug: entry for entry in FROZEN_CAPABILITY_BOUNDARIES}

    assert set(boundaries_by_slug) == {
        "worker_admin",
        "multi_tenant_scope",
        "artifact_uploads_and_object_store",
        "external_worker_handoff",
    }
    assert boundaries_by_slug["worker_admin"].route_prefixes == ("/api/v1/worker-admin",)
    assert boundaries_by_slug["worker_admin"].api_surface_groups == (
        "worker-admin",
        "worker-admin-projections",
    )
    assert boundaries_by_slug["worker_admin"].storage_table_refs == (
        "worker_bootstrap_state",
        "worker_bootstrap_issue",
        "worker_session",
        "worker_delivery_grant",
        "worker_admin_token_issue",
        "worker_admin_auth_rejection_log",
        "worker_admin_action_log",
    )
    assert boundaries_by_slug["artifact_uploads_and_object_store"].route_prefixes == (
        "/api/v1/artifact-uploads",
    )
    assert boundaries_by_slug["artifact_uploads_and_object_store"].api_surface_groups == (
        "artifact-uploads",
        "commands",
        "worker-runtime",
    )
    assert boundaries_by_slug["artifact_uploads_and_object_store"].storage_table_refs == (
        "artifact_upload_session",
        "artifact_upload_part",
    )
    assert boundaries_by_slug["external_worker_handoff"].route_prefixes == ("/api/v1/worker-runtime",)
    assert boundaries_by_slug["external_worker_handoff"].api_surface_groups == (
        "worker-runtime",
        "worker-runtime-projections",
    )
    assert boundaries_by_slug["external_worker_handoff"].storage_table_refs == (
        "worker_bootstrap_state",
        "worker_session",
        "worker_delivery_grant",
        "worker_auth_rejection_log",
    )
    assert boundaries_by_slug["multi_tenant_scope"].route_prefixes == ()
    assert boundaries_by_slug["multi_tenant_scope"].api_surface_groups == (
        "commands",
        "projections",
        "worker-admin",
        "worker-admin-projections",
        "worker-runtime",
        "worker-runtime-projections",
    )
    assert boundaries_by_slug["multi_tenant_scope"].storage_table_refs == ()

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
        "backend/app/core/artifact_handlers.py",
        "backend/app/core/worker_runtime.py",
    )
    assert boundaries_by_slug["artifact_uploads_and_object_store"].test_refs == (
        "backend/tests/test_api.py",
        "backend/tests/test_repository.py",
    )
    assert boundaries_by_slug["artifact_uploads_and_object_store"].migration_preconditions == (
        "The ticket result-submit path has already been decoupled from upload-session consumption and must stay that way.",
        "Object-store support must remain a minimal storage backend and must not be expanded during this cleanup round.",
    )

    assert boundaries_by_slug["external_worker_handoff"].entrypoint_refs == (
        "backend/app/api/worker_runtime.py",
        "backend/app/api/worker_runtime_projections.py",
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
        for group_name in entry.api_surface_groups:
            assert group_name in api_surface_groups
        for table_name in entry.storage_table_refs:
            assert f"CREATE TABLE IF NOT EXISTS {table_name}" in _read_repo_text(
                "backend/app/db/repository.py"
            )
        for ref in entry.code_refs + entry.entrypoint_refs + entry.mainline_dependency_refs + entry.test_refs:
            assert (REPO_ROOT / ref).exists(), ref


def test_frozen_capability_boundaries_capture_shared_scope_and_bridge_constraints() -> None:
    boundaries_by_slug = {entry.slug: entry for entry in FROZEN_CAPABILITY_BOUNDARIES}

    artifact_boundary = boundaries_by_slug["artifact_uploads_and_object_store"]
    assert artifact_boundary.mainline_dependency_refs == (
        "backend/app/core/artifact_handlers.py",
        "backend/app/core/worker_runtime.py",
    )
    assert "ticket-result-submit 已不再依赖 upload session" in artifact_boundary.notes
    assert artifact_boundary.migration_blocker_refs == (
        "backend/app/api/artifact_uploads.py",
        "backend/app/core/artifact_handlers.py",
        "backend/app/db/repository.py",
    )
    assert artifact_boundary.migration_blocker_summary == (
        "主线 result-submit 已与 upload session 解耦，但 upload 导入入口和 artifact upload session 存储仍需保留。"
    )
    assert artifact_boundary.api_surface_groups == ("artifact-uploads", "commands", "worker-runtime")
    assert artifact_boundary.storage_table_refs == ("artifact_upload_session", "artifact_upload_part")

    scope_boundary = boundaries_by_slug["multi_tenant_scope"]
    assert "shared data shape" in scope_boundary.notes
    assert any("Physical migration is blocked" in item for item in scope_boundary.migration_preconditions)
    assert scope_boundary.migration_blocker_refs == (
        "backend/app/contracts/runtime.py",
        "backend/app/contracts/worker_admin.py",
        "backend/app/contracts/worker_runtime.py",
    )
    assert scope_boundary.migration_blocker_summary == (
        "主线 command 侧已去掉 tenant_id/workspace_id，但 runtime 和冻结 contracts 仍保留多租户 shape。"
    )
    assert scope_boundary.api_surface_groups == (
        "commands",
        "projections",
        "worker-admin",
        "worker-admin-projections",
        "worker-runtime",
        "worker-runtime-projections",
    )
    assert scope_boundary.storage_table_refs == ()

    handoff_boundary = boundaries_by_slug["external_worker_handoff"]
    assert handoff_boundary.migration_blocker_refs == (
        "backend/app/api/worker_runtime_projections.py",
        "backend/app/api/worker_runtime.py",
        "backend/app/core/worker_runtime.py",
        "backend/app/db/repository.py",
        "backend/app/worker_auth_cli.py",
    )
    assert handoff_boundary.migration_blocker_summary == (
        "worker-runtime 路由、投影、CLI 和 worker bootstrap/session/delivery-grant schema 仍需成组保留。"
    )
    assert handoff_boundary.api_surface_groups == ("worker-runtime", "worker-runtime-projections")
    assert handoff_boundary.storage_table_refs == (
        "worker_bootstrap_state",
        "worker_session",
        "worker_delivery_grant",
        "worker_auth_rejection_log",
    )


def test_frozen_capability_api_surface_groups_stay_within_documented_group_order() -> None:
    allowed_group_names = set(API_SURFACE_GROUP_ORDER)

    assert allowed_group_names >= {
        group_name
        for entry in FROZEN_CAPABILITY_BOUNDARIES
        for group_name in entry.api_surface_groups
    }
    assert API_SURFACE_GROUP_ORDER == ALL_ROUTE_GROUPS
    assert set(FROZEN_ROUTE_GROUPS) == {
        "artifact-uploads",
        "worker-runtime",
        "worker-admin",
        "worker-admin-projections",
        "worker-runtime-projections",
    }


def test_worker_admin_boundary_uses_dedicated_projection_entrypoint() -> None:
    projection_entrypoint = REPO_ROOT / "backend/app/api/worker_admin_projections.py"

    assert projection_entrypoint.exists()


def test_worker_auth_cli_no_longer_imports_worker_admin_core_module() -> None:
    worker_auth_cli_source = _read_repo_text("backend/app/worker_auth_cli.py")

    assert "from app.core.worker_admin import" not in worker_auth_cli_source
    assert "from app.core.worker_scope_ops import" in worker_auth_cli_source


def test_multi_tenant_scope_blockers_now_live_in_runtime_and_frozen_contracts() -> None:
    scope_boundary = {
        entry.slug: entry for entry in FROZEN_CAPABILITY_BOUNDARIES
    }["multi_tenant_scope"]

    runtime_source = _read_repo_text("backend/app/contracts/runtime.py")
    worker_admin_contract_source = _read_repo_text("backend/app/contracts/worker_admin.py")
    worker_runtime_contract_source = _read_repo_text("backend/app/contracts/worker_runtime.py")
    commands_source = _read_repo_text("backend/app/contracts/commands.py")

    assert scope_boundary.migration_blocker_refs[0] == "backend/app/contracts/runtime.py"
    assert "class ProjectInitCommand" in commands_source
    assert "tenant_id: str | None" not in commands_source
    assert "workspace_id: str | None" not in commands_source
    assert "scope_tenant_id" in runtime_source and "scope_workspace_id" in runtime_source
    assert "tenant_id" in worker_admin_contract_source and "workspace_id" in worker_admin_contract_source
    assert "tenant_id" in worker_runtime_contract_source and "workspace_id" in worker_runtime_contract_source


def test_artifact_upload_bridge_has_moved_out_of_result_submit_path() -> None:
    artifact_boundary = {
        entry.slug: entry for entry in FROZEN_CAPABILITY_BOUNDARIES
    }["artifact_uploads_and_object_store"]
    artifact_handlers_source = _read_repo_text("backend/app/core/artifact_handlers.py")
    ticket_artifacts_source = _read_repo_text("backend/app/core/ticket_artifacts.py")
    commands_source = _read_repo_text("backend/app/contracts/commands.py")
    ticket_handlers_source = _read_repo_text("backend/app/core/ticket_handlers.py")
    worker_runtime_source = _read_repo_text("backend/app/core/worker_runtime.py")
    repository_source = _read_repo_text("backend/app/db/repository.py")
    ticket_written_artifact_section = commands_source.split("class TicketWrittenArtifact", 1)[1].split(
        "class TicketResultSubmitCommand",
        1,
    )[0]

    assert "upload_session_id" not in ticket_written_artifact_section
    assert "class TicketArtifactImportUploadCommand" in commands_source
    assert "from app.core.artifact_uploads import require_completed_artifact_upload_session" not in ticket_handlers_source
    assert "session = require_completed_artifact_upload_session(" not in ticket_handlers_source
    assert "repository.consume_artifact_upload_session(" not in ticket_handlers_source
    assert "require_completed_artifact_upload_session" in ticket_artifacts_source
    assert "handle_ticket_artifact_import_upload" in artifact_handlers_source
    assert "consume_artifact_upload_session" in artifact_handlers_source
    assert "ticket-artifact-import-upload" in worker_runtime_source
    assert "def consume_artifact_upload_session(" in repository_source
    assert artifact_boundary.migration_blocker_summary.endswith("仍需保留。")


def test_external_worker_handoff_blockers_still_exist_as_one_runtime_unit() -> None:
    handoff_boundary = {
        entry.slug: entry for entry in FROZEN_CAPABILITY_BOUNDARIES
    }["external_worker_handoff"]
    worker_runtime_projection_api_source = _read_repo_text(
        "backend/app/api/worker_runtime_projections.py"
    )
    worker_runtime_api_source = _read_repo_text("backend/app/api/worker_runtime.py")
    projections_api_source = _read_repo_text("backend/app/api/projections.py")
    worker_runtime_core_source = _read_repo_text("backend/app/core/worker_runtime.py")
    worker_auth_cli_source = _read_repo_text("backend/app/worker_auth_cli.py")
    repository_source = _read_repo_text("backend/app/db/repository.py")
    main_source = _read_repo_text("backend/app/main.py")
    router_registry_source = _read_repo_text("backend/app/api/router_registry.py")

    assert 'APIRouter(prefix="/api/v1/worker-runtime"' in worker_runtime_api_source
    assert "from app.api.router_registry import include_registered_routers" in main_source
    assert "include_registered_routers(app)" in main_source
    assert '@router.get("/worker-runtime"' not in projections_api_source
    assert '@router.get("/worker-runtime"' in worker_runtime_projection_api_source
    assert 'group_name="worker-runtime"' in router_registry_source
    assert 'group_name="worker-runtime-projections"' in router_registry_source
    assert "def _create_or_refresh_worker_session(" in worker_runtime_core_source
    assert 'prog="python -m app.worker_auth_cli"' in worker_auth_cli_source
    assert "CREATE TABLE IF NOT EXISTS worker_bootstrap_state" in repository_source
    assert "CREATE TABLE IF NOT EXISTS worker_session" in repository_source
    assert "CREATE TABLE IF NOT EXISTS worker_delivery_grant" in repository_source
    assert handoff_boundary.migration_blocker_summary.endswith("schema 仍需成组保留。")


def test_external_worker_handoff_projection_builder_uses_worker_scope_helpers() -> None:
    projections_source = _read_repo_text("backend/app/core/projections.py")

    assert "from app.core.worker_scope_ops import (" in projections_source
    assert "list_auth_rejections" in projections_source
    assert "list_binding_admin_views" in projections_source
    assert "list_delivery_grants" in projections_source
    assert "list_sessions" in projections_source

    worker_runtime_section = projections_source.split("def build_worker_runtime_projection(", 1)[1].split(
        "def build_worker_admin_audit_projection(",
        1,
    )[0]
    assert "repository.list_worker_binding_admin_views(" not in worker_runtime_section
    assert "repository.list_worker_sessions(" not in worker_runtime_section
    assert "repository.list_worker_delivery_grants(" not in worker_runtime_section
    assert "repository.list_worker_auth_rejection_logs(" not in worker_runtime_section
    assert "list_binding_admin_views(" in worker_runtime_section
    assert "list_sessions(" in worker_runtime_section
    assert "list_delivery_grants(" in worker_runtime_section
    assert "list_auth_rejections(" in worker_runtime_section
