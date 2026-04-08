from __future__ import annotations

from typing import Any


ROLE_TEMPLATE_STATUS_LIVE = "LIVE"
ROLE_TEMPLATE_STATUS_NOT_ENABLED = "NOT_ENABLED"

MAINLINE_BOUNDARY_STATUS_LIVE = "LIVE_ON_MAINLINE"
MAINLINE_BOUNDARY_STATUS_CATALOG_ONLY = "CATALOG_ONLY"

MAINLINE_PATH_CATALOG_READONLY = "catalog_readonly"
MAINLINE_PATH_SCOPE_CONSENSUS = "scope_consensus"
MAINLINE_PATH_GOVERNANCE_DOCUMENT_LIVE = "governance_document_live"
MAINLINE_PATH_CEO_CREATE_TICKET = "ceo_create_ticket"
MAINLINE_PATH_IMPLEMENTATION_DELIVERY = "implementation_delivery"
MAINLINE_PATH_CHECKER_GATE = "checker_gate"
MAINLINE_PATH_FINAL_REVIEW = "final_review"
MAINLINE_PATH_CLOSEOUT = "closeout"
MAINLINE_PATH_PROVIDER_FUTURE_SLOT = "provider_future_slot"
MAINLINE_PATH_STAFFING = "staffing"
MAINLINE_PATH_WORKFORCE_LANE = "workforce_lane"

MAINLINE_BLOCKED_PATH_STAFFING = "staffing"
MAINLINE_BLOCKED_PATH_CEO_CREATE_TICKET = "ceo_create_ticket"
MAINLINE_BLOCKED_PATH_RUNTIME_EXECUTION = "runtime_execution"
MAINLINE_BLOCKED_PATH_WORKFORCE_LANE = "workforce_lane"

PARTICIPATION_MODE_HIGH_FREQUENCY_DELIVERY = "HIGH_FREQUENCY_DELIVERY"
PARTICIPATION_MODE_HIGH_FREQUENCY_REVIEW = "HIGH_FREQUENCY_REVIEW"
PARTICIPATION_MODE_LOW_FREQUENCY_HIGH_LEVERAGE = "LOW_FREQUENCY_HIGH_LEVERAGE"

ROLE_TEMPLATE_NOT_ENABLED_REASON = "角色模板已定义，但尚未纳入当前主线。"


def _mainline_boundary(
    *,
    boundary_status: str,
    active_path_refs: tuple[str, ...],
    blocked_path_refs: tuple[str, ...] = (),
) -> dict[str, Any]:
    return {
        "boundary_status": boundary_status,
        "active_path_refs": list(active_path_refs),
        "blocked_path_refs": list(blocked_path_refs),
    }

_ROLE_TEMPLATE_DOCUMENT_KINDS: tuple[dict[str, str], ...] = (
    {
        "kind_ref": "architecture_brief",
        "label": "架构方案",
        "summary": "定义目标架构、关键边界和主要权衡。",
    },
    {
        "kind_ref": "technology_decision",
        "label": "技术选型",
        "summary": "记录候选方案对比、最终选择和约束。",
    },
    {
        "kind_ref": "milestone_plan",
        "label": "里程碑拆解",
        "summary": "拆分里程碑顺序、验收节点和交付节奏。",
    },
    {
        "kind_ref": "detailed_design",
        "label": "详细设计",
        "summary": "补充实现边界、接口约定和关键设计细节。",
    },
    {
        "kind_ref": "backlog_recommendation",
        "label": "TODO / Backlog 建议",
        "summary": "给出后续执行切片建议，不直接启用新的 runtime 角色。",
    },
)

_ROLE_TEMPLATE_FRAGMENTS: tuple[dict[str, Any], ...] = (
    {
        "fragment_id": "skill_frontend_ui",
        "fragment_kind": "skill_domain",
        "label": "Frontend / UI",
        "summary": "面向 Boardroom shell、界面交互和前端交付。",
        "payload": {
            "primary_domain": "frontend",
            "system_scope": "delivery_slice",
        },
    },
    {
        "fragment_id": "skill_backend_services",
        "fragment_kind": "skill_domain",
        "label": "Backend services",
        "summary": "面向服务实现、接口编排和后端交付。",
        "payload": {
            "primary_domain": "backend",
            "system_scope": "service_delivery",
        },
    },
    {
        "fragment_id": "skill_database_reliability",
        "fragment_kind": "skill_domain",
        "label": "Database reliability",
        "summary": "面向数据模型、迁移和数据库可靠性边界。",
        "payload": {
            "primary_domain": "data",
            "system_scope": "data_reliability",
        },
    },
    {
        "fragment_id": "skill_platform_operations",
        "fragment_kind": "skill_domain",
        "label": "Platform / operations",
        "summary": "面向部署、观测性和运行环境稳定性。",
        "payload": {
            "primary_domain": "platform",
            "system_scope": "runtime_operations",
        },
    },
    {
        "fragment_id": "skill_architecture_governance",
        "fragment_kind": "skill_domain",
        "label": "Architecture governance",
        "summary": "面向架构判断、关键决策和实现边界校准。",
        "payload": {
            "primary_domain": "architecture",
            "decision_scope": "architecture",
        },
    },
    {
        "fragment_id": "skill_quality_validation",
        "fragment_kind": "skill_domain",
        "label": "Quality validation",
        "summary": "面向交付检查、缺陷识别和审查闭环。",
        "payload": {
            "primary_domain": "quality",
            "system_scope": "release_guard",
        },
    },
    {
        "fragment_id": "delivery_execution_loop",
        "fragment_kind": "delivery_mode",
        "label": "Execution loop",
        "summary": "默认面向高频实施、返工和交付循环。",
        "payload": {
            "default_mode": "execution",
        },
    },
    {
        "fragment_id": "delivery_document_first",
        "fragment_kind": "delivery_mode",
        "label": "Document first",
        "summary": "默认面向低频、高杠杆、文档先行的参与方式。",
        "payload": {
            "default_mode": "document",
        },
    },
    {
        "fragment_id": "review_internal_gate",
        "fragment_kind": "review_mode",
        "label": "Internal review gate",
        "summary": "默认面向内部 checker gate，而不是主实施。",
        "payload": {
            "default_mode": "checker_gate",
        },
    },
)

_ROLE_TEMPLATE_CATALOG: tuple[dict[str, Any], ...] = (
    {
        "template_id": "scope_consensus_primary",
        "template_kind": "live_execution",
        "label": "Scope Consensus / 需求澄清",
        "role_family": "frontend_uiux",
        "role_type": "frontend_engineer",
        "canonical_role_ref": "ui_designer_primary",
        "alias_role_profile_refs": [],
        "provider_target_ref": "role_profile:ui_designer_primary",
        "participation_mode": PARTICIPATION_MODE_HIGH_FREQUENCY_DELIVERY,
        "execution_boundary": "当前只用于 project-init / scope review 共识链，不承担主线实施主力。",
        "status": ROLE_TEMPLATE_STATUS_LIVE,
        "default_document_kind_refs": ["architecture_brief"],
        "responsibility_summary": "负责 scope 共识、需求澄清和早期界面方向收敛。",
        "summary": "Keep project-init and scope review aligned before implementation.",
        "composition": {
            "fragment_refs": [
                "skill_frontend_ui",
                "delivery_document_first",
            ],
        },
        "mainline_boundary": _mainline_boundary(
            boundary_status=MAINLINE_BOUNDARY_STATUS_LIVE,
            active_path_refs=(
                MAINLINE_PATH_CATALOG_READONLY,
                MAINLINE_PATH_SCOPE_CONSENSUS,
                MAINLINE_PATH_GOVERNANCE_DOCUMENT_LIVE,
            ),
        ),
        "future_provider_binding_enabled": False,
    },
    {
        "template_id": "frontend_delivery_primary",
        "template_kind": "live_execution",
        "label": "Frontend Engineer / 实施交付",
        "role_family": "frontend_uiux",
        "role_type": "frontend_engineer",
        "canonical_role_ref": "frontend_engineer_primary",
        "alias_role_profile_refs": [],
        "provider_target_ref": "role_profile:frontend_engineer_primary",
        "participation_mode": PARTICIPATION_MODE_HIGH_FREQUENCY_DELIVERY,
        "execution_boundary": "当前负责 BUILD / REVIEW / closeout 的主实施与交付整理。",
        "status": ROLE_TEMPLATE_STATUS_LIVE,
        "default_document_kind_refs": ["detailed_design"],
        "responsibility_summary": "负责前端实现、交付整理和最终 review 包。",
        "summary": "Own the implementation path for the thin boardroom shell.",
        "composition": {
            "fragment_refs": [
                "skill_frontend_ui",
                "delivery_execution_loop",
            ],
        },
        "mainline_boundary": _mainline_boundary(
            boundary_status=MAINLINE_BOUNDARY_STATUS_LIVE,
            active_path_refs=(
                MAINLINE_PATH_CATALOG_READONLY,
                MAINLINE_PATH_GOVERNANCE_DOCUMENT_LIVE,
                MAINLINE_PATH_IMPLEMENTATION_DELIVERY,
                MAINLINE_PATH_FINAL_REVIEW,
                MAINLINE_PATH_CLOSEOUT,
            ),
        ),
        "future_provider_binding_enabled": False,
    },
    {
        "template_id": "quality_checker_primary",
        "template_kind": "live_execution",
        "label": "Checker / 质量审查",
        "role_family": "test_or_checker",
        "role_type": "checker",
        "canonical_role_ref": "checker_primary",
        "alias_role_profile_refs": [],
        "provider_target_ref": "role_profile:checker_primary",
        "participation_mode": PARTICIPATION_MODE_HIGH_FREQUENCY_REVIEW,
        "execution_boundary": "当前负责 maker-checker 质量门和 closeout 审查，不承担主实施。",
        "status": ROLE_TEMPLATE_STATUS_LIVE,
        "default_document_kind_refs": [],
        "responsibility_summary": "负责交付检查、maker-checker verdict 和 closeout 审查。",
        "summary": "Keep implementation quality and auditability in check.",
        "composition": {
            "fragment_refs": [
                "skill_quality_validation",
                "review_internal_gate",
            ],
        },
        "mainline_boundary": _mainline_boundary(
            boundary_status=MAINLINE_BOUNDARY_STATUS_LIVE,
            active_path_refs=(
                MAINLINE_PATH_CATALOG_READONLY,
                MAINLINE_PATH_CHECKER_GATE,
            ),
        ),
        "future_provider_binding_enabled": False,
    },
    {
        "template_id": "backend_execution_reserved",
        "template_kind": "reserved_execution",
        "label": "Backend Engineer / 服务交付",
        "role_family": "backend_engineer",
        "role_type": "backend_engineer",
        "canonical_role_ref": "backend_engineer_primary",
        "alias_role_profile_refs": [],
        "provider_target_ref": "role_profile:backend_engineer_primary",
        "participation_mode": PARTICIPATION_MODE_HIGH_FREQUENCY_DELIVERY,
        "execution_boundary": "已定义为未来执行角色，但当前不进入主线 staffing 或 runtime。",
        "status": ROLE_TEMPLATE_STATUS_NOT_ENABLED,
        "default_document_kind_refs": ["detailed_design"],
        "responsibility_summary": "负责服务实现、接口落地和集成切片。",
        "summary": "Reserved for future backend delivery slices.",
        "composition": {
            "fragment_refs": [
                "skill_backend_services",
                "delivery_execution_loop",
            ],
        },
        "mainline_boundary": _mainline_boundary(
            boundary_status=MAINLINE_BOUNDARY_STATUS_CATALOG_ONLY,
            active_path_refs=(
                MAINLINE_PATH_CATALOG_READONLY,
                MAINLINE_PATH_PROVIDER_FUTURE_SLOT,
                MAINLINE_PATH_STAFFING,
                MAINLINE_PATH_WORKFORCE_LANE,
            ),
            blocked_path_refs=(
                MAINLINE_BLOCKED_PATH_CEO_CREATE_TICKET,
                MAINLINE_BLOCKED_PATH_RUNTIME_EXECUTION,
            ),
        ),
        "future_provider_binding_enabled": True,
    },
    {
        "template_id": "database_execution_reserved",
        "template_kind": "reserved_execution",
        "label": "Database Engineer / 数据可靠性",
        "role_family": "database_engineer",
        "role_type": "database_engineer",
        "canonical_role_ref": "database_engineer_primary",
        "alias_role_profile_refs": [],
        "provider_target_ref": "role_profile:database_engineer_primary",
        "participation_mode": PARTICIPATION_MODE_HIGH_FREQUENCY_DELIVERY,
        "execution_boundary": "已定义为未来执行角色，但当前不进入主线 staffing 或 runtime。",
        "status": ROLE_TEMPLATE_STATUS_NOT_ENABLED,
        "default_document_kind_refs": ["detailed_design"],
        "responsibility_summary": "负责数据模型、迁移和数据库可靠性边界。",
        "summary": "Reserved for future database-heavy slices.",
        "composition": {
            "fragment_refs": [
                "skill_database_reliability",
                "delivery_execution_loop",
            ],
        },
        "mainline_boundary": _mainline_boundary(
            boundary_status=MAINLINE_BOUNDARY_STATUS_CATALOG_ONLY,
            active_path_refs=(
                MAINLINE_PATH_CATALOG_READONLY,
                MAINLINE_PATH_PROVIDER_FUTURE_SLOT,
                MAINLINE_PATH_STAFFING,
                MAINLINE_PATH_WORKFORCE_LANE,
            ),
            blocked_path_refs=(
                MAINLINE_BLOCKED_PATH_CEO_CREATE_TICKET,
                MAINLINE_BLOCKED_PATH_RUNTIME_EXECUTION,
            ),
        ),
        "future_provider_binding_enabled": True,
    },
    {
        "template_id": "platform_sre_reserved",
        "template_kind": "reserved_execution",
        "label": "Platform / SRE",
        "role_family": "platform_sre",
        "role_type": "platform_sre",
        "canonical_role_ref": "platform_sre_primary",
        "alias_role_profile_refs": [],
        "provider_target_ref": "role_profile:platform_sre_primary",
        "participation_mode": PARTICIPATION_MODE_HIGH_FREQUENCY_DELIVERY,
        "execution_boundary": "已定义为未来执行角色，但当前不进入主线 staffing 或 runtime。",
        "status": ROLE_TEMPLATE_STATUS_NOT_ENABLED,
        "default_document_kind_refs": ["detailed_design"],
        "responsibility_summary": "负责部署、稳定性和运行环境治理。",
        "summary": "Reserved for future platform and reliability work.",
        "composition": {
            "fragment_refs": [
                "skill_platform_operations",
                "delivery_execution_loop",
            ],
        },
        "mainline_boundary": _mainline_boundary(
            boundary_status=MAINLINE_BOUNDARY_STATUS_CATALOG_ONLY,
            active_path_refs=(
                MAINLINE_PATH_CATALOG_READONLY,
                MAINLINE_PATH_PROVIDER_FUTURE_SLOT,
                MAINLINE_PATH_STAFFING,
                MAINLINE_PATH_WORKFORCE_LANE,
            ),
            blocked_path_refs=(
                MAINLINE_BLOCKED_PATH_CEO_CREATE_TICKET,
                MAINLINE_BLOCKED_PATH_RUNTIME_EXECUTION,
            ),
        ),
        "future_provider_binding_enabled": True,
    },
    {
        "template_id": "architect_governance",
        "template_kind": "governance",
        "label": "架构师 / 设计评审",
        "role_family": "architect",
        "role_type": "governance_architect",
        "canonical_role_ref": "architect_primary",
        "alias_role_profile_refs": [],
        "provider_target_ref": "role_profile:architect_primary",
        "participation_mode": PARTICIPATION_MODE_LOW_FREQUENCY_HIGH_LEVERAGE,
        "execution_boundary": "默认不承担日常编码、测试或持续实施主力工作。",
        "status": ROLE_TEMPLATE_STATUS_NOT_ENABLED,
        "default_document_kind_refs": [
            "architecture_brief",
            "technology_decision",
            "detailed_design",
        ],
        "responsibility_summary": "负责设计评审、方案收敛和实现边界校准。",
        "summary": "Review design detail and keep implementation aligned to architecture.",
        "composition": {
            "fragment_refs": [
                "skill_architecture_governance",
                "delivery_document_first",
            ],
        },
        "mainline_boundary": _mainline_boundary(
            boundary_status=MAINLINE_BOUNDARY_STATUS_CATALOG_ONLY,
            active_path_refs=(
                MAINLINE_PATH_CATALOG_READONLY,
                MAINLINE_PATH_PROVIDER_FUTURE_SLOT,
                MAINLINE_PATH_STAFFING,
                MAINLINE_PATH_WORKFORCE_LANE,
                MAINLINE_PATH_CEO_CREATE_TICKET,
            ),
            blocked_path_refs=(
                MAINLINE_BLOCKED_PATH_RUNTIME_EXECUTION,
            ),
        ),
        "future_provider_binding_enabled": True,
    },
    {
        "template_id": "cto_governance",
        "template_kind": "governance",
        "label": "CTO / 架构治理",
        "role_family": "cto",
        "role_type": "governance_cto",
        "canonical_role_ref": "cto_primary",
        "alias_role_profile_refs": [],
        "provider_target_ref": "role_profile:cto_primary",
        "participation_mode": PARTICIPATION_MODE_LOW_FREQUENCY_HIGH_LEVERAGE,
        "execution_boundary": "默认不承担日常编码、测试或持续实施主力工作。",
        "status": ROLE_TEMPLATE_STATUS_NOT_ENABLED,
        "default_document_kind_refs": [
            "architecture_brief",
            "technology_decision",
            "milestone_plan",
            "backlog_recommendation",
        ],
        "responsibility_summary": "负责高杠杆架构判断、关键治理决策和主线切片方向建议。",
        "summary": "Shape architecture, major decisions, and backlog direction.",
        "composition": {
            "fragment_refs": [
                "skill_architecture_governance",
                "delivery_document_first",
            ],
        },
        "mainline_boundary": _mainline_boundary(
            boundary_status=MAINLINE_BOUNDARY_STATUS_CATALOG_ONLY,
            active_path_refs=(
                MAINLINE_PATH_CATALOG_READONLY,
                MAINLINE_PATH_PROVIDER_FUTURE_SLOT,
                MAINLINE_PATH_STAFFING,
                MAINLINE_PATH_WORKFORCE_LANE,
                MAINLINE_PATH_CEO_CREATE_TICKET,
            ),
            blocked_path_refs=(
                MAINLINE_BLOCKED_PATH_RUNTIME_EXECUTION,
            ),
        ),
        "future_provider_binding_enabled": True,
    },
)


def _clone_document_kind(kind: dict[str, str]) -> dict[str, str]:
    return dict(kind)


def _clone_fragment(fragment: dict[str, Any]) -> dict[str, Any]:
    return {
        **fragment,
        "payload": dict(fragment.get("payload") or {}),
    }


def _clone_role_template(template: dict[str, Any]) -> dict[str, Any]:
    return {
        **template,
        "alias_role_profile_refs": list(template.get("alias_role_profile_refs") or []),
        "default_document_kind_refs": list(template.get("default_document_kind_refs") or []),
        "composition": {
            "fragment_refs": list((template.get("composition") or {}).get("fragment_refs") or []),
        },
        "mainline_boundary": {
            "boundary_status": str((template.get("mainline_boundary") or {}).get("boundary_status") or ""),
            "active_path_refs": list((template.get("mainline_boundary") or {}).get("active_path_refs") or []),
            "blocked_path_refs": list((template.get("mainline_boundary") or {}).get("blocked_path_refs") or []),
        },
    }


def list_role_template_document_kinds() -> list[dict[str, str]]:
    return [_clone_document_kind(kind) for kind in _ROLE_TEMPLATE_DOCUMENT_KINDS]


def list_role_template_fragments() -> list[dict[str, Any]]:
    return [_clone_fragment(fragment) for fragment in _ROLE_TEMPLATE_FRAGMENTS]


def list_role_template_catalog_entries() -> list[dict[str, Any]]:
    return [_clone_role_template(template) for template in _ROLE_TEMPLATE_CATALOG]


def list_runtime_provider_future_binding_slots() -> list[dict[str, Any]]:
    return [
        {
            "target_ref": str(template["provider_target_ref"]),
            "label": str(template["label"]),
            "status": str(template["status"]),
            "reason": ROLE_TEMPLATE_NOT_ENABLED_REASON,
            "blocked_path_refs": list((template.get("mainline_boundary") or {}).get("blocked_path_refs") or []),
        }
        for template in list_role_template_catalog_entries()
        if template.get("future_provider_binding_enabled") and template.get("status") == ROLE_TEMPLATE_STATUS_NOT_ENABLED
    ]


def role_template_source_for_worker(
    *,
    role_type: str | None,
    role_profile_ref: str | None = None,
) -> dict[str, Any] | None:
    normalized_role_profile_ref = str(role_profile_ref or "").strip()
    if normalized_role_profile_ref:
        for template in _ROLE_TEMPLATE_CATALOG:
            if template["canonical_role_ref"] == normalized_role_profile_ref:
                return _clone_role_template(template)

    normalized_role_type = str(role_type or "").strip()
    default_template_id_by_role_type = {
        "frontend_engineer": "frontend_delivery_primary",
        "checker": "quality_checker_primary",
        "backend_engineer": "backend_execution_reserved",
        "database_engineer": "database_execution_reserved",
        "platform_sre": "platform_sre_reserved",
        "governance_architect": "architect_governance",
        "governance_cto": "cto_governance",
    }
    preferred_template_id = default_template_id_by_role_type.get(normalized_role_type)
    if preferred_template_id is not None:
        for template in _ROLE_TEMPLATE_CATALOG:
            if template["template_id"] == preferred_template_id:
                return _clone_role_template(template)
    return None
