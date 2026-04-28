from __future__ import annotations

from dataclasses import dataclass

from app.core.output_schemas import (
    ARCHITECTURE_BRIEF_SCHEMA_REF,
    BACKLOG_RECOMMENDATION_SCHEMA_REF,
    CONSENSUS_DOCUMENT_SCHEMA_REF,
    DETAILED_DESIGN_SCHEMA_REF,
    DELIVERY_CHECK_REPORT_SCHEMA_REF,
    DELIVERY_CLOSEOUT_PACKAGE_SCHEMA_REF,
    GOVERNANCE_DOCUMENT_SCHEMA_REFS,
    MAKER_CHECKER_VERDICT_SCHEMA_REF,
    MILESTONE_PLAN_SCHEMA_REF,
    SOURCE_CODE_DELIVERY_SCHEMA_REF,
    TECHNOLOGY_DECISION_SCHEMA_REF,
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
class StaffingCapacityTruth:
    role_type: str
    role_profile_refs: tuple[str, ...]
    max_active_count: int
    busy_worker_policy: str
    cap_reached_policy: str
    public_hire_overlap_policy: str
    notes: str


@dataclass(frozen=True)
class FrozenCapabilityBoundary:
    slug: str
    label: str
    boundary_status: str
    route_prefixes: tuple[str, ...]
    api_surface_groups: tuple[str, ...]
    storage_table_refs: tuple[str, ...]
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
        stage_id="project_init_to_governance_kickoff",
        label="Project init -> governance kickoff",
        truth_status="REAL",
        actual_owner_roles=("governance_architect",),
        actual_role_profiles=("architect_primary",),
        output_schema_refs=(ARCHITECTURE_BRIEF_SCHEMA_REF,),
        notes="project-init 现在先按 architect_primary 的治理 kickoff 选人；缺人时先由 CEO 直雇注册，再进入治理文档主线。",
    ),
    MainlineWorkflowStageTruth(
        stage_id="build_internal_maker_checker",
        label="Build internal maker-checker",
        truth_status="REAL",
        actual_owner_roles=("frontend_engineer", "checker"),
        actual_role_profiles=("frontend_engineer_primary", "checker_primary"),
        output_schema_refs=(SOURCE_CODE_DELIVERY_SCHEMA_REF, MAKER_CHECKER_VERDICT_SCHEMA_REF),
        notes="BUILD 先产出 source_code_delivery，再走内部 checker。frontend_engineer 现在已有独立 runtime worker。",
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
        role_profile_ref="backend_engineer_primary",
        output_schema_ref=SOURCE_CODE_DELIVERY_SCHEMA_REF,
        supported_modes=("OPENAI_COMPAT_LIVE",),
        notes="新增 backend 实施角色现在已进入正式 BUILD runtime 路径。",
    ),
    RuntimeSupportRow(
        role_profile_ref="database_engineer_primary",
        output_schema_ref=SOURCE_CODE_DELIVERY_SCHEMA_REF,
        supported_modes=("OPENAI_COMPAT_LIVE",),
        notes="新增 database 实施角色现在已进入正式 BUILD runtime 路径。",
    ),
    RuntimeSupportRow(
        role_profile_ref="platform_sre_primary",
        output_schema_ref=SOURCE_CODE_DELIVERY_SCHEMA_REF,
        supported_modes=("OPENAI_COMPAT_LIVE",),
        notes="新增 platform 实施角色现在已进入正式 BUILD runtime 路径。",
    ),
    RuntimeSupportRow(
        role_profile_ref="ui_designer_primary",
        output_schema_ref=CONSENSUS_DOCUMENT_SCHEMA_REF,
        supported_modes=("OPENAI_COMPAT_LIVE",),
        notes="当前共识文档仍由主线 maker 角色产出。",
    ),
    *(
        RuntimeSupportRow(
            role_profile_ref="ui_designer_primary",
            output_schema_ref=output_schema_ref,
            supported_modes=("OPENAI_COMPAT_LIVE",),
            notes="当前治理文档可由现有 live planning 角色产出，不额外启用治理新角色。",
        )
        for output_schema_ref in GOVERNANCE_DOCUMENT_SCHEMA_REFS
    ),
    *(
        RuntimeSupportRow(
            role_profile_ref="architect_primary",
            output_schema_ref=output_schema_ref,
            supported_modes=("OPENAI_COMPAT_LIVE",),
            notes="架构治理角色现在已进入正式治理文档 runtime 路径。",
        )
        for output_schema_ref in (
            ARCHITECTURE_BRIEF_SCHEMA_REF,
            TECHNOLOGY_DECISION_SCHEMA_REF,
            DETAILED_DESIGN_SCHEMA_REF,
        )
    ),
    *(
        RuntimeSupportRow(
            role_profile_ref="cto_primary",
            output_schema_ref=output_schema_ref,
            supported_modes=("OPENAI_COMPAT_LIVE",),
            notes="CTO 治理角色现在已进入正式治理文档 runtime 路径。",
        )
        for output_schema_ref in (
            ARCHITECTURE_BRIEF_SCHEMA_REF,
            TECHNOLOGY_DECISION_SCHEMA_REF,
            MILESTONE_PLAN_SCHEMA_REF,
            BACKLOG_RECOMMENDATION_SCHEMA_REF,
        )
    ),
    *(
        RuntimeSupportRow(
            role_profile_ref="frontend_engineer_primary",
            output_schema_ref=output_schema_ref,
            supported_modes=("OPENAI_COMPAT_LIVE",),
            notes="当前治理文档也可由现有 frontend live 角色产出，保持文档家族与角色目录解耦。",
        )
        for output_schema_ref in GOVERNANCE_DOCUMENT_SCHEMA_REFS
    ),
    RuntimeSupportRow(
        role_profile_ref="frontend_engineer_primary",
        output_schema_ref=SOURCE_CODE_DELIVERY_SCHEMA_REF,
        supported_modes=("OPENAI_COMPAT_LIVE",),
        notes="BUILD 阶段的源码交付当前由 frontend_engineer_primary 产出。",
    ),
    RuntimeSupportRow(
        role_profile_ref="checker_primary",
        output_schema_ref=DELIVERY_CHECK_REPORT_SCHEMA_REF,
        supported_modes=("OPENAI_COMPAT_LIVE",),
        notes="CHECK 阶段的交付检查报告当前由 checker_primary 产出。",
    ),
    RuntimeSupportRow(
        role_profile_ref="frontend_engineer_primary",
        output_schema_ref=UI_MILESTONE_REVIEW_SCHEMA_REF,
        supported_modes=("OPENAI_COMPAT_LIVE",),
        notes="最终 REVIEW 包当前由 frontend_engineer_primary 产出。",
    ),
    RuntimeSupportRow(
        role_profile_ref="frontend_engineer_primary",
        output_schema_ref=DELIVERY_CLOSEOUT_PACKAGE_SCHEMA_REF,
        supported_modes=("OPENAI_COMPAT_LIVE",),
        notes="最终 closeout package 当前由 frontend_engineer_primary 产出。",
    ),
    RuntimeSupportRow(
        role_profile_ref="checker_primary",
        output_schema_ref=MAKER_CHECKER_VERDICT_SCHEMA_REF,
        supported_modes=("OPENAI_COMPAT_LIVE",),
        notes="所有主线 maker-checker verdict 当前都由 checker_primary 产出。",
    ),
)


MAINLINE_STAFFING_CAPACITY_TRUTH: tuple[StaffingCapacityTruth, ...] = (
    StaffingCapacityTruth(
        role_type="frontend_engineer",
        role_profile_refs=("frontend_engineer_primary",),
        max_active_count=2,
        busy_worker_policy="HIRE_WHEN_BELOW_CAP",
        cap_reached_policy="STAFFING_WAIT",
        public_hire_overlap_policy="STRICT_ROLE_ALREADY_COVERED",
        notes="CEO 自动招聘可在 active frontend worker 忙碌且未达 cap 时补容量；手工招聘仍走严格重复画像护栏。",
    ),
    StaffingCapacityTruth(
        role_type="checker",
        role_profile_refs=("checker_primary",),
        max_active_count=2,
        busy_worker_policy="HIRE_WHEN_BELOW_CAP",
        cap_reached_policy="STAFFING_WAIT",
        public_hire_overlap_policy="STRICT_ROLE_ALREADY_COVERED",
        notes="checker 可按容量补到 2 名 active board-approved 员工；provider paused / worker excluded 不触发扩招。",
    ),
    StaffingCapacityTruth(
        role_type="backend_engineer",
        role_profile_refs=("backend_engineer_primary",),
        max_active_count=2,
        busy_worker_policy="HIRE_WHEN_BELOW_CAP",
        cap_reached_policy="STAFFING_WAIT",
        public_hire_overlap_policy="STRICT_ROLE_ALREADY_COVERED",
        notes="backend ready ticket 遇到现有 worker busy 时允许补容量；达到 2 人后进入 STAFFING_CAP_REACHED 等待。",
    ),
    StaffingCapacityTruth(
        role_type="database_engineer",
        role_profile_refs=("database_engineer_primary",),
        max_active_count=2,
        busy_worker_policy="HIRE_WHEN_BELOW_CAP",
        cap_reached_policy="STAFFING_WAIT",
        public_hire_overlap_policy="STRICT_ROLE_ALREADY_COVERED",
        notes="database worker 的自动扩容语义与 backend 一致，只统计 active board-approved 且覆盖 role_profile 的员工。",
    ),
    StaffingCapacityTruth(
        role_type="platform_sre",
        role_profile_refs=("platform_sre_primary",),
        max_active_count=2,
        busy_worker_policy="HIRE_WHEN_BELOW_CAP",
        cap_reached_policy="STAFFING_WAIT",
        public_hire_overlap_policy="STRICT_ROLE_ALREADY_COVERED",
        notes="platform worker 的自动扩容语义与 backend 一致；冻结、替换和未审批员工不计入 cap。",
    ),
    StaffingCapacityTruth(
        role_type="governance_architect",
        role_profile_refs=("architect_primary",),
        max_active_count=2,
        busy_worker_policy="HIRE_WHEN_BELOW_CAP",
        cap_reached_policy="STAFFING_WAIT",
        public_hire_overlap_policy="STRICT_ROLE_ALREADY_COVERED",
        notes="architect governance 可补一名容量 worker，但仍只服务治理文档主线，不进入 staged BUILD/CHECK/REVIEW owner_role。",
    ),
    StaffingCapacityTruth(
        role_type="governance_cto",
        role_profile_refs=("cto_primary",),
        max_active_count=1,
        busy_worker_policy="HIRE_WHEN_BELOW_CAP",
        cap_reached_policy="STAFFING_WAIT",
        public_hire_overlap_policy="STRICT_ROLE_ALREADY_COVERED",
        notes="CTO governance 是 singleton capacity；已有 active cto 时即使 busy 也等待，不再补第二名 CTO。",
    ),
)


FROZEN_CAPABILITY_BOUNDARIES: tuple[FrozenCapabilityBoundary, ...] = (
    FrozenCapabilityBoundary(
        slug="worker_admin",
        label="Worker admin control plane",
        boundary_status="FROZEN_PRESENT",
        route_prefixes=("/api/v1/worker-admin",),
        api_surface_groups=("worker-admin", "worker-admin-projections"),
        storage_table_refs=(
            "worker_bootstrap_state",
            "worker_bootstrap_issue",
            "worker_session",
            "worker_delivery_grant",
            "worker_admin_token_issue",
            "worker_admin_auth_rejection_log",
            "worker_admin_action_log",
        ),
        code_refs=(
            "backend/app/_frozen/worker_admin/api/worker_admin.py",
            "backend/app/_frozen/worker_admin/api/worker_admin_auth.py",
            "backend/app/_frozen/worker_admin/api/worker_admin_projections.py",
            "backend/app/_frozen/worker_admin/core/worker_admin.py",
            "backend/app/_frozen/worker_admin/cli/worker_admin_auth_cli.py",
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
            "worker-admin 实现已迁入 `_frozen/worker_admin`，但 API、auth、projection 和 CLI 兼容壳仍需成组保留。"
        ),
        notes=(
            "HTTP 管理面和操作人令牌链仍保留在仓库中，但当前默认不继续扩张。"
            "它现在是保留的运维面，不是主线业务依赖。"
            "P1-CLN-001 这轮已把真实实现迁入 `_frozen/worker_admin`，旧入口当前只保留兼容壳。"
        ),
    ),
    FrozenCapabilityBoundary(
        slug="multi_tenant_scope",
        label="Multi-tenant scope binding",
        boundary_status="FROZEN_PRESENT",
        route_prefixes=(),
        api_surface_groups=(
            "commands",
            "projections",
            "worker-admin",
            "worker-admin-projections",
            "worker-runtime",
            "worker-runtime-projections",
        ),
        storage_table_refs=(),
        code_refs=(
            "backend/app/contracts/scope.py",
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
            "backend/app/contracts/scope.py",
            "backend/app/contracts/runtime.py",
            "backend/app/contracts/worker_admin.py",
            "backend/app/contracts/worker_runtime.py",
        ),
        migration_blocker_summary=(
            "主线 command 侧已去掉 tenant_id/workspace_id，但 runtime 和冻结 contracts 仍保留多租户 shape。"
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
        api_surface_groups=("artifact-uploads", "commands", "worker-runtime"),
        storage_table_refs=("artifact_upload_session", "artifact_upload_part"),
        code_refs=(
            "backend/app/_frozen/object_store.py",
        ),
        entrypoint_refs=(
            "backend/app/api/artifact_uploads.py",
            "backend/app/core/artifact_uploads.py",
            "backend/app/core/artifact_store.py",
        ),
        mainline_dependency_refs=(
            "backend/app/core/artifact_store.py",
            "backend/app/core/artifact_handlers.py",
            "backend/app/core/worker_runtime.py",
        ),
        test_refs=(
            "backend/tests/test_api.py",
            "backend/tests/test_repository.py",
        ),
        migration_preconditions=(
            "The ticket result-submit path has already been decoupled from upload-session consumption and must stay that way.",
            "Object-store support must remain a minimal storage backend and must not be expanded during this cleanup round.",
        ),
        migration_blocker_refs=(
            "backend/app/api/artifact_uploads.py",
            "backend/app/core/artifact_handlers.py",
            "backend/app/db/repository.py",
        ),
        migration_blocker_summary=(
            "本地 artifact 存储仍是主线；冻结的只是可选对象存储分支，upload 导入入口和 artifact upload session 存储仍需保留。"
        ),
        notes=(
            "控制面上传和可选对象存储仍可运行，但当前只按最小解堵保留，不继续平台化。"
            "本地 artifact 存储与 upload staging 仍是主线必需；冻结的只是可选对象存储实现。"
            "ticket-result-submit 已不再依赖 upload session；当前桥接只保留在独立的 artifact import-upload 命令。"
            "对象存储 backend 的建链细节这轮已进一步收进 `_frozen/object_store.py`。"
        ),
    ),
    FrozenCapabilityBoundary(
        slug="external_worker_handoff",
        label="External worker handoff",
        boundary_status="FROZEN_PRESENT",
        route_prefixes=("/api/v1/worker-runtime",),
        api_surface_groups=("worker-runtime", "worker-runtime-projections"),
        storage_table_refs=(
            "worker_bootstrap_state",
            "worker_session",
            "worker_delivery_grant",
            "worker_auth_rejection_log",
        ),
        code_refs=(
            "backend/app/_frozen/worker_runtime/api/worker_runtime.py",
            "backend/app/_frozen/worker_runtime/api/worker_runtime_projections.py",
            "backend/app/_frozen/worker_runtime/core/worker_runtime.py",
            "backend/app/_frozen/worker_runtime/cli/worker_auth_cli.py",
        ),
        entrypoint_refs=(
            "backend/app/api/worker_runtime.py",
            "backend/app/api/worker_runtime_projections.py",
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
            "backend/app/api/worker_runtime_projections.py",
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
            "P1-CLN-004 这轮已完成独立 projection 入口前置拆分，但 schema 仍需成组保留。"
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
