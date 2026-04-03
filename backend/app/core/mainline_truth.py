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
        actual_role_profiles=("ui_designer_primary", "checker_primary"),
        output_schema_refs=(IMPLEMENTATION_BUNDLE_SCHEMA_REF, MAKER_CHECKER_VERDICT_SCHEMA_REF),
        notes=(
            "BUILD 先产出 implementation_bundle，再走内部 checker。当前 frontend_engineer "
            "owner role 仍映射到 ui_designer_primary，不是独立 worker。"
        ),
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
        actual_role_profiles=("ui_designer_primary",),
        output_schema_refs=(UI_MILESTONE_REVIEW_SCHEMA_REF,),
        notes="最终董事会 REVIEW 只在真正 board-facing 的 review pack 上进入 Inbox -> Review Room。",
    ),
    MainlineWorkflowStageTruth(
        stage_id="closeout_internal_maker_checker",
        label="Closeout internal maker-checker",
        truth_status="REAL",
        actual_owner_roles=("frontend_engineer", "checker"),
        actual_role_profiles=("ui_designer_primary", "checker_primary"),
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
        role_profile_ref="ui_designer_primary",
        output_schema_ref=IMPLEMENTATION_BUNDLE_SCHEMA_REF,
        supported_modes=("LOCAL_DETERMINISTIC", "OPENAI_COMPAT_LIVE"),
        notes="BUILD 阶段的实现包当前仍由 ui_designer_primary 产出。",
    ),
    RuntimeSupportRow(
        role_profile_ref="checker_primary",
        output_schema_ref=DELIVERY_CHECK_REPORT_SCHEMA_REF,
        supported_modes=("LOCAL_DETERMINISTIC", "OPENAI_COMPAT_LIVE"),
        notes="CHECK 阶段的交付检查报告当前由 checker_primary 产出。",
    ),
    RuntimeSupportRow(
        role_profile_ref="ui_designer_primary",
        output_schema_ref=UI_MILESTONE_REVIEW_SCHEMA_REF,
        supported_modes=("LOCAL_DETERMINISTIC", "OPENAI_COMPAT_LIVE"),
        notes="最终 REVIEW 包仍由 ui_designer_primary 产出。",
    ),
    RuntimeSupportRow(
        role_profile_ref="ui_designer_primary",
        output_schema_ref=DELIVERY_CLOSEOUT_PACKAGE_SCHEMA_REF,
        supported_modes=("LOCAL_DETERMINISTIC", "OPENAI_COMPAT_LIVE"),
        notes="最终 closeout package 当前由 ui_designer_primary 产出。",
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
        notes="HTTP 管理面和操作人令牌链仍保留在仓库中，但当前默认不继续扩张。",
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
        notes="tenant/workspace scope 仍真实存在于数据结构和 handoff 链上，但不属于当前 MVP 主线卖点。",
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
        notes="控制面上传和可选对象存储仍可运行，但当前只按最小解堵保留，不继续平台化。",
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
        notes="外部 worker bootstrap、session 和 delivery grant 仍在仓库中，但当前默认不作为主线继续推进。",
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
