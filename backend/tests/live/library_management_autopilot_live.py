from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from tests.live._autopilot_live_harness import (
    APPROVED_ARCHITECT_GOVERNANCE_SCHEMA_REFS,
    LiveScenarioDefinition,
    ScenarioPaths,
    _write_json,
    build_scenario_paths as _build_scenario_paths,
    run_cli,
    run_live_scenario as _run_live_scenario,
    reset_scenario_root,
)

DEFAULT_SCENARIO_SLUG = "library_management_autopilot_live"
SCENARIO_GOAL = "全自动开发一个计算机系毕业设计-有精美设计的图书馆管理系统"
REQUIRED_LIBRARY_CAPABILITIES = {
    "reader_search": ["reader_search", "图书查询", "检索"],
    "reader_reservation": ["reader_reservation", "预约"],
    "reader_loan_history": ["reader_loan_history", "借阅记录", "借阅历史"],
    "reader_profile": ["reader_profile", "个人中心", "读者档案"],
    "admin_procurement": ["admin_procurement", "图书采购", "采购"],
    "admin_cataloging": ["admin_cataloging", "编目"],
    "admin_inventory": ["admin_inventory", "库存"],
    "admin_user_management": ["admin_user_management", "用户管理"],
    "admin_system_config": ["admin_system_config", "系统配置"],
}
SCENARIO_CONSTRAINTS = [
    (
        "该项目全权授予CEO自由裁量的权利，进度完全由CEO自主推进无需经过董事会审议，包括招聘，"
        "召集架构师、系统分析师选型和详细梳理系统，分配开发工作，审阅测试结果，审阅里程碑，"
        "交给运维人员发布，向董事会交付报告。"
    ),
    "CEO 必须真实招聘并真实使用 architect_primary，系统分析职责并入架构治理链。",
    (
        "本次长测不再以 raw ticket 数量作为项目规模限制，也不得用最小 ticket 数量兜底；"
        "成功口径看 graph runtime 是否收敛、功能模块是否命中、source delivery 证据是否完整。"
    ),
    (
        "读者自助部分只需要实现：图书查询 reader_search、预约 reader_reservation、"
        "借阅记录 reader_loan_history、个人中心 reader_profile。"
    ),
    (
        "后台管理部分只需要实现：图书采购 admin_procurement、编目 admin_cataloging、"
        "库存 admin_inventory、用户管理 admin_user_management、系统配置 admin_system_config。"
    ),
    (
        "不要扩展认证与 RBAC、罚金、公告、统计报表、审计日志、运维监控等旧大而全模块，"
        "除非它们是用户管理、系统配置或交付 closeout 的最小支撑。"
    ),
]


def build_scenario_paths(scenario_root: Path | None = None) -> ScenarioPaths:
    return _build_scenario_paths(DEFAULT_SCENARIO_SLUG, scenario_root)


def _json_corpus(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).lower()
    except TypeError:
        return str(value).lower()


def _library_scope_corpus(common: dict[str, Any]) -> str:
    return "\n".join(
        [
            _json_corpus(common.get("created_specs") or {}),
            _json_corpus(common.get("terminals") or {}),
        ]
    )


def _missing_library_capabilities(common: dict[str, Any]) -> list[str]:
    corpus = _library_scope_corpus(common)
    return [
        capability
        for capability, terms in REQUIRED_LIBRARY_CAPABILITIES.items()
        if not any(term.lower() in corpus for term in terms)
    ]


def _assert_library_outcome(
    paths: ScenarioPaths,
    repository,
    workflow_id: str,
    common: dict[str, Any],
) -> dict[str, Any]:
    employees = common["employees"]
    if not any(str(employee.get("role_type") or "") == "governance_architect" for employee in employees):
        raise AssertionError("No approved governance_architect employee was hired.")

    audits = common["audits"]
    architect_audits = [item for item in audits if item["role_profile_ref"] == "architect_primary"]
    if not architect_audits:
        raise AssertionError("No architect_primary runtime ticket completed with recorded assumptions.")
    if not any(
        audit["assumptions"].get("actual_model") == "gpt-5.4"
        and audit["assumptions"].get("effective_reasoning_effort") == "xhigh"
        for audit in architect_audits
    ):
        raise AssertionError("Architect runtime audit did not record gpt-5.4 @ xhigh.")

    approved_architect_ticket_ids = common["architect_ticket_ids"]
    if not approved_architect_ticket_ids:
        raise AssertionError("No approved architect_primary governance document evidence was recorded.")

    non_architect_audits = [item for item in audits if item["role_profile_ref"] != "architect_primary"]
    if not non_architect_audits:
        raise AssertionError("No non-architect runtime tickets completed.")
    invalid_non_architect = [
        item
        for item in non_architect_audits
        if item["assumptions"].get("actual_model") != "gpt-5.4"
        or item["assumptions"].get("effective_reasoning_effort") != "high"
    ]
    if invalid_non_architect:
        raise AssertionError(f"Non-architect runtime audits deviated from gpt-5.4 @ high: {invalid_non_architect}")

    missing_capabilities = _missing_library_capabilities(common)
    if missing_capabilities:
        raise AssertionError(f"Library delivery missed required capabilities: {missing_capabilities}")

    approved_architect_output_schema_refs = sorted(
        {
            str((common["created_specs"].get(ticket_id) or {}).get("output_schema_ref") or "")
            for ticket_id in approved_architect_ticket_ids
            if str((common["created_specs"].get(ticket_id) or {}).get("output_schema_ref") or "")
            in APPROVED_ARCHITECT_GOVERNANCE_SCHEMA_REFS
        }
    )

    return {
        "architect_ticket_ids": [item["ticket_id"] for item in architect_audits],
        "approved_architect_governance_ticket_ids": approved_architect_ticket_ids,
        "approved_architect_governance_schema_refs": approved_architect_output_schema_refs,
        "scope_capabilities": list(REQUIRED_LIBRARY_CAPABILITIES),
    }


SCENARIO = LiveScenarioDefinition(
    slug=DEFAULT_SCENARIO_SLUG,
    description="Run the library management autopilot live scenario.",
    goal=SCENARIO_GOAL,
    constraints=SCENARIO_CONSTRAINTS,
    assert_outcome=_assert_library_outcome,
)


def run_live_scenario(
    *,
    clean: bool = True,
    max_ticks: int = 180,
    timeout_sec: int = 7200,
    seed: int = 17,
    scenario_root: Path | None = None,
) -> dict[str, Any]:
    return _run_live_scenario(
        SCENARIO,
        clean=clean,
        max_ticks=max_ticks,
        timeout_sec=timeout_sec,
        seed=seed,
        scenario_root=scenario_root,
    )


def main(argv: list[str] | None = None) -> int:
    return run_cli(SCENARIO, argv)


if __name__ == "__main__":
    raise SystemExit(main())
