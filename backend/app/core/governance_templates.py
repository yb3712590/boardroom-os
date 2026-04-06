from __future__ import annotations

from typing import Any


GOVERNANCE_TEMPLATE_STATUS_NOT_ENABLED = "NOT_ENABLED"
GOVERNANCE_PARTICIPATION_MODE_LOW_FREQUENCY = "LOW_FREQUENCY_HIGH_LEVERAGE"
GOVERNANCE_EXECUTION_BOUNDARY_READ_ONLY = "默认不承担日常编码、测试或持续实施主力工作。"
GOVERNANCE_TEMPLATE_NOT_ENABLED_REASON = "治理模板角色尚未纳入当前主线。"

_GOVERNANCE_DOCUMENT_KINDS: tuple[dict[str, str], ...] = (
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

_GOVERNANCE_ROLE_TEMPLATES: tuple[dict[str, Any], ...] = (
    {
        "template_id": "cto_governance",
        "label": "CTO / 架构治理",
        "role_type": "governance_cto",
        "role_profile_ref": "cto_primary",
        "provider_target_ref": "role_profile:cto_primary",
        "participation_mode": GOVERNANCE_PARTICIPATION_MODE_LOW_FREQUENCY,
        "execution_boundary": GOVERNANCE_EXECUTION_BOUNDARY_READ_ONLY,
        "status": GOVERNANCE_TEMPLATE_STATUS_NOT_ENABLED,
        "default_document_kind_refs": [
            "architecture_brief",
            "technology_decision",
            "milestone_plan",
            "backlog_recommendation",
        ],
        "summary": "负责高杠杆架构判断、关键治理决策和主线切片方向建议。",
    },
    {
        "template_id": "architect_governance",
        "label": "架构师 / 设计评审",
        "role_type": "governance_architect",
        "role_profile_ref": "architect_primary",
        "provider_target_ref": "role_profile:architect_primary",
        "participation_mode": GOVERNANCE_PARTICIPATION_MODE_LOW_FREQUENCY,
        "execution_boundary": GOVERNANCE_EXECUTION_BOUNDARY_READ_ONLY,
        "status": GOVERNANCE_TEMPLATE_STATUS_NOT_ENABLED,
        "default_document_kind_refs": [
            "architecture_brief",
            "technology_decision",
            "detailed_design",
        ],
        "summary": "负责设计评审、方案收敛和实现边界校准，不承担日常编码主力。",
    },
)


def _clone_document_kind(kind: dict[str, str]) -> dict[str, str]:
    return dict(kind)


def _clone_role_template(template: dict[str, Any]) -> dict[str, Any]:
    return {
        **template,
        "default_document_kind_refs": list(template.get("default_document_kind_refs") or []),
    }


def list_governance_document_kinds() -> list[dict[str, str]]:
    return [_clone_document_kind(kind) for kind in _GOVERNANCE_DOCUMENT_KINDS]


def list_governance_role_templates() -> list[dict[str, Any]]:
    return [_clone_role_template(template) for template in _GOVERNANCE_ROLE_TEMPLATES]


def list_runtime_provider_future_binding_slots() -> list[dict[str, str]]:
    return [
        {
            "target_ref": str(template["provider_target_ref"]),
            "label": str(template["label"]),
            "status": str(template["status"]),
            "reason": GOVERNANCE_TEMPLATE_NOT_ENABLED_REASON,
        }
        for template in list_governance_role_templates()
    ]
