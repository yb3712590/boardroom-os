from __future__ import annotations

from dataclasses import dataclass

from app.core.output_schemas import (
    CONSENSUS_DOCUMENT_SCHEMA_REF,
    DELIVERY_CHECK_REPORT_SCHEMA_REF,
    DELIVERY_CLOSEOUT_PACKAGE_SCHEMA_REF,
    IMPLEMENTATION_BUNDLE_SCHEMA_REF,
    MAKER_CHECKER_VERDICT_SCHEMA_REF,
    UI_MILESTONE_REVIEW_SCHEMA_REF,
)


@dataclass(frozen=True)
class MainlineWorkflowStageTruth:
    stage_id: str
    label: str
    truth_status: str
    actual_owner_roles: tuple[str, ...]
    actual_role_profiles: tuple[str, ...]
    output_schema_refs: tuple[str, ...]
    notes: str


@dataclass(frozen=True)
class RuntimeSupportRow:
    role_profile_ref: str
    output_schema_ref: str
    supported_modes: tuple[str, ...]
    notes: str


@dataclass(frozen=True)
class FrozenCapabilityBoundary:
    slug: str
    label: str
    boundary_status: str
    route_prefixes: tuple[str, ...]
    code_refs: tuple[str, ...]
    entrypoint_refs: tuple[str, ...]
    mainline_dependency_refs: tuple[str, ...]
    test_refs: tuple[str, ...]
    migration_preconditions: tuple[str, ...]
    migration_blocker_refs: tuple[str, ...]
    migration_blocker_summary: str
    notes: str


MAINLINE_WORKFLOW_STAGE_TRUTH: tuple[MainlineWorkflowStageTruth, ...] = (
    MainlineWorkflowStageTruth(
        stage_id="project_init_to_scope_review",
        label="Project init -> scope review",
        truth_status="REAL",
        actual_owner_roles=("frontend_engineer",),
        actual_role_profiles=("ui_designer_primary",),
        output_schema_refs=(CONSENSUS_DOCUMENT_SCHEMA_REF,),
        notes="project-init 已自动推进到首个 scope review，scope 审批是真实董事会停点。",
    ),
    MainlineWorkflowStageTruth(
        stage_id="build_internal_maker_checker",
        label="Build internal maker-checker",
        truth_status="REAL",
        actual_owner_roles=("frontend_engineer", "checker"),
        actual_role_profiles=("frontend_engineer_primary", "checker_primary"),
        output_schema_refs=(IMPLEMENTATION_BUNDLE_SCHEMA_REF, MAKER_CHECKER_VERDICT_SCHEMA_REF),
        notes="BUILD 先产出 implementation_bundle，再走内部 checker。frontend_engineer 现在已有独立 runtime worker。",
    ),
    MainlineWorkflowStageTruth(
        stage_id="check_internal_maker_checker",
        label="Check internal maker-checker",
        truth_status="REAL",
        actual_owner_roles=("checker",),
        actual_role_profiles=("checker_primary",),
        output_schema_refs=(DELIVERY_CHECK_REPORT_SCHEMA_REF, MAKER_CHECKER_VERDICT_SCHEMA_REF),
        notes="CHECK 已有独立的 delivery_check_report 内审闭环，通过后才会放行最终 REVIEW。",
    ),
    MainlineWorkflowStageTruth(
        stage_id="final_board_review",
        label="Final board review",
        truth_status="REAL",
        actual_owner_roles=("frontend_engineer",),
        actual_role_profiles=("frontend_engineer_primary",),
        output_schema_refs=(UI_MILESTONE_REVIEW_SCHEMA_REF,),
        notes="最终董事会 REVIEW 只在真正 board-facing 的 review pack 上进入 Inbox -> Review Room。",
    ),
    MainlineWorkflowStageTruth(
        stage_id="closeout_internal_maker_checker",
        label="Closeout internal maker-checker",
        truth_status="REAL",
        actual_owner_roles=("frontend_engineer", "checker"),
        actual_role_profiles=("frontend_engineer_primary", "checker_primary"),
        output_schema_refs=(DELIVERY_CLOSEOUT_PACKAGE_SCHEMA_REF, MAKER_CHECKER_VERDICT_SCHEMA_REF),
        notes="最终 board approve 后会自动补 closeout ticket，closeout 完成后才显示 workflow completion。",
    ),
)


MAINLINE_RUNTIME_SUPPORT_MATRIX: tuple[RuntimeSupportRow, ...] = (
    RuntimeSupportRow(
        role_profile_ref="ui_designer_primary",
        output_schema_ref=CONSENSUS_DOCUMENT_SCHEMA_REF,
        supported_modes=("LOCAL_DETERMINISTIC", "OPENAI_COMPAT_LIVE"),
        notes="当前共识文档仍由主线 maker 角色产出。",
    ),
    RuntimeSupportRow(
        role_profile_ref="frontend_engineer_primary",
        output_schema_ref=IMPLEMENTATION_BUNDLE_SCHEMA_REF,
        supported_modes=("LOCAL_DETERMINISTIC", "OPENAI_COMPAT_LIVE"),
        notes="BUILD 阶段的实现包当前由 frontend_engineer_primary 产出。",
    ),
    RuntimeSupportRow(
        role_profile_ref="checker_primary",
        output_schema_ref=DELIVERY_CHECK_REPORT_SCHEMA_REF,
        supported_modes=("LOCAL_DETERMINISTIC", "OPENAI_COMPAT_LIVE"),
        notes="CHECK 阶段的交付检查报告当前由 checker_primary 产出。",
    ),
    RuntimeSupportRow(
        role_profile_ref="frontend_engineer_primary",
        output_schema_ref=UI_MILESTONE_REVIEW_SCHEMA_REF,
        supported_modes=("LOCAL_DETERMINISTIC", "OPENAI_COMPAT_LIVE"),
        notes="最终 REVIEW 包当前由 frontend_engineer_primary 产出。",
    ),
    RuntimeSupportRow(
        role_profile_ref="frontend_engineer_primary",
        output_schema_ref=DELIVERY_CLOSEOUT_PACKAGE_SCHEMA_REF,
        supported_modes=("LOCAL_DETERMINISTIC", "OPENAI_COMPAT_LIVE"),
        notes="最终 closeout package 当前由 frontend_engineer_primary 产出。",
    ),
    RuntimeSupportRow(
        role_profile_ref="checker_primary",
        output_schema_ref=MAKER_CHECKER_VERDICT_SCHEMA_REF,
        supported_modes=("LOCAL_DETERMINISTIC", "OPENAI_COMPAT_LIVE"),
        notes="所有主线 maker-checker verdict 当前都由 checker_primary 产出。",
    ),
)


FROZEN_CAPABILITY_BOUNDARIES: tuple[FrozenCapabilityBoundary, ...] = (
    FrozenCapabilityBoundary(
        slug="worker_admin",
        label="Worker admin control plane",
        boundary_status="FROZEN_PRESENT",
        route_prefixes=("/api/v1/worker-admin",),
        code_refs=(
            "backend/app/api/worker_admin.py",
            "backend/app/api/worker_admin_auth.py",
            "backend/app/core/worker_admin.py",
        ),
        entrypoint_refs=(
            "backend/app/api/worker_admin.py",
            "backend/app/api/worker_admin_projections.py",
            "backend/app/worker_admin_auth_cli.py",
        ),
        mainline_dependency_refs=(),
        test_refs=(
            "backend/tests/test_api.py",
            "backend/tests/test_worker_admin_auth_cli.py",
            "backend/tests/test_repository.py",
        ),
        migration_preconditions=(
            "Worker-admin API, auth projection, and CLI entrypoints must either move together or stay in place.",
            "No current mainline workflow path may import worker_admin modules directly before any physical migration starts.",
        ),
        migration_blocker_refs=(
            "backend/app/api/worker_admin.py",
            "backend/app/api/worker_admin_auth.py",
            "backend/app/api/worker_admin_projections.py",
            "backend/app/main.py",
            "backend/app/worker_admin_auth_cli.py",
        ),
        migration_blocker_summary=(
            "worker-admin 仍要把 API、auth、projection 和 CLI 作为同一组入口一起迁，当前只完成了前置拆分。"
        ),
        notes=(
            "HTTP 管理面和操作人令牌链仍保留在仓库中，但当前默认不继续扩张。"
            "它现在是保留的运维面，不是主线业务依赖。"
            "P1-CLN-001 的前置拆分已完成，但 `_frozen/` 物理迁移仍未启动。"
        ),
    ),
    FrozenCapabilityBoundary(
        slug="multi_tenant_scope",
        label="Multi-tenant scope binding",
        boundary_status="FROZEN_PRESENT",
        route_prefixes=(),
        code_refs=(
            "backend/app/contracts/worker_admin.py",
            "backend/app/contracts/worker_runtime.py",
            "backend/app/core/worker_runtime.py",
        ),
        entrypoint_refs=(
            "backend/app/api/projections.py",
            "backend/app/contracts/commands.py",
            "backend/app/contracts/runtime.py",
            "backend/app/contracts/worker_admin.py",
            "backend/app/contracts/worker_runtime.py",
        ),
        mainline_dependency_refs=(
            "backend/app/core/ticket_handlers.py",
            "backend/app/core/approval_handlers.py",
            "backend/app/core/ceo_execution_presets.py",
        ),
        test_refs=(
            "backend/tests/test_api.py",
            "backend/tests/test_context_compiler.py",
            "backend/tests/test_repository.py",
        ),
        migration_preconditions=(
            "tenant_id/workspace_id must stay available in shared contracts and projections used by the current local MVP.",
            "Physical migration is blocked until multi-tenant scope is decoupled from command, runtime, and projection data shapes.",
        ),
        migration_blocker_refs=(
            "backend/app/contracts/commands.py",
            "backend/app/contracts/runtime.py",
            "backend/app/contracts/worker_admin.py",
            "backend/app/contracts/worker_runtime.py",
            "backend/app/core/approval_handlers.py",
            "backend/app/core/ceo_execution_presets.py",
            "backend/app/core/ticket_handlers.py",
        ),
        migration_blocker_summary=(
            "tenant_id/workspace_id 仍是主线 contracts、审批恢复和 ticket 创建形状的一部分。"
        ),
        notes=(
            "tenant/workspace scope 仍真实存在于数据结构和 handoff 链上，但不属于当前 MVP 主线卖点。"
            "这块是共享数据结构（shared data shape），不是可以独立搬走的冻结目录。"
        ),
    ),
    FrozenCapabilityBoundary(
        slug="artifact_uploads_and_object_store",
        label="Artifact uploads and object store",
        boundary_status="FROZEN_PRESENT",
        route_prefixes=("/api/v1/artifact-uploads",),
        code_refs=(
            "backend/app/api/artifact_uploads.py",
            "backend/app/core/artifact_uploads.py",
            "backend/app/core/artifact_store.py",
        ),
        entrypoint_refs=(
            "backend/app/api/artifact_uploads.py",
            "backend/app/core/artifact_uploads.py",
            "backend/app/core/artifact_store.py",
        ),
        mainline_dependency_refs=("backend/app/core/ticket_handlers.py",),
        test_refs=(
            "backend/tests/test_api.py",
            "backend/tests/test_repository.py",
        ),
        migration_preconditions=(
            "The ticket result-submit path must stop calling require_completed_artifact_upload_session before artifact upload code can move.",
            "Object-store support must remain a minimal storage backend and must not be expanded during this cleanup round.",
        ),
        migration_blocker_refs=(
            "backend/app/contracts/commands.py",
            "backend/app/core/ticket_handlers.py",
            "backend/app/db/repository.py",
        ),
        migration_blocker_summary=(
            "ticket-result-submit 仍接受 upload_session_id，并且提交与消费路径仍依赖 artifact upload session。"
        ),
        notes=(
            "控制面上传和可选对象存储仍可运行，但当前只按最小解堵保留，不继续平台化。"
            "其中 require_completed_artifact_upload_session 仍被主线 ticket-result-submit 桥接使用。"
        ),
    ),
    FrozenCapabilityBoundary(
        slug="external_worker_handoff",
        label="External worker handoff",
        boundary_status="FROZEN_PRESENT",
        route_prefixes=("/api/v1/worker-runtime",),
        code_refs=(
            "backend/app/api/worker_runtime.py",
            "backend/app/core/worker_runtime.py",
            "backend/app/worker_auth_cli.py",
        ),
        entrypoint_refs=(
            "backend/app/api/worker_runtime.py",
            "backend/app/api/projections.py",
            "backend/app/worker_auth_cli.py",
        ),
        mainline_dependency_refs=(),
        test_refs=(
            "backend/tests/test_api.py",
            "backend/tests/test_worker_auth_cli.py",
            "backend/tests/conftest.py",
        ),
        migration_preconditions=(
            "Worker-runtime delivery routes and the worker-runtime projection must stay aligned until the handoff surface is retired together.",
            "No physical migration should start while worker bootstrap, session, and delivery-grant storage still share the active repository schema.",
        ),
        migration_blocker_refs=(
            "backend/app/api/projections.py",
            "backend/app/api/worker_runtime.py",
            "backend/app/core/worker_runtime.py",
            "backend/app/db/repository.py",
            "backend/app/worker_auth_cli.py",
        ),
        migration_blocker_summary=(
            "worker-runtime 路由、投影、CLI 和 worker bootstrap/session/delivery-grant schema 仍需成组保留。"
        ),
        notes=(
            "外部 worker bootstrap、session 和 delivery grant 仍在仓库中，但当前默认不作为主线继续推进。"
            "它现在是保留的交接面，不是当前 MVP 的主链卖点。"
        ),
    ),
)


__all__ = [
    "FROZEN_CAPABILITY_BOUNDARIES",
    "FrozenCapabilityBoundary",
    "MAINLINE_RUNTIME_SUPPORT_MATRIX",
    "MAINLINE_WORKFLOW_STAGE_TRUTH",
    "MainlineWorkflowStageTruth",
    "RuntimeSupportRow",
]
