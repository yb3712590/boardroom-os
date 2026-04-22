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
SCENARIO_GOAL = "实现一个完全匿名、单机运行的极简图书流转终端，只回答馆里有什么书以及这本书现在能不能拿走。"
REQUIRED_LIBRARY_CAPABILITIES = {
    "books": ["books", "books table", "books terminal", "book tracker"],
    "title": ["title", "书名"],
    "author": ["author", "作者"],
    "IN_LIBRARY": ["in_library"],
    "CHECKED_OUT": ["checked_out"],
    "add": [" add ", "add book", "新增图书", "入库"],
    "check out": ["check out", "checked out", "借出"],
    "return": [" return ", "归还"],
    "remove": ["remove", "下架", "删除图书"],
    "terminal": ["terminal", "终端", "hacker-console"],
    "console": ["console", "控制台", "单色文本", "monochrome"],
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
        "核心目标固定为极简图书流转终端：匿名、单机、只回答“馆里有什么书”和“这本书现在能不能拿走”。"
    ),
    (
        "绝对禁止 Auth / RBAC、登录注册、权限分层；系统固定为单租户无头模式，不区分管理员和普通读者。"
    ),
    (
        "绝对禁止借阅时长、逾期、罚款、时间轴计算；借阅动作只表现为状态切换，不要求记录时间戳。"
    ),
    (
        "绝对禁止分类表、标签表、馆藏位置表；所有书籍拍平在同一个维度，不做 taxonomy 扩展。"
    ),
    (
        "绝对禁止用户借阅历史、借阅人台账和个人中心；只记录书被借走这个状态，不记录是谁借的。"
    ),
    (
        "唯一数据模型只允许 books 一张表，字段固定为 id、title、author、status；status 只允许 IN_LIBRARY 和 CHECKED_OUT。"
    ),
    (
        "核心状态机只允许 Add、Check Out、Return、Remove 四个动作；不要扩展预约、采购、编目、库存盘点、系统配置等旧模块。"
    ),
    (
        "前端 UI 必须采用深色、单色文本、高信息密度的 terminal / console 风格；不要动画、阴影、圆角或传统后台卡片。"
    ),
    (
        "交互只保留一个新增输入框和一个纯文本列表；列表负责展示 books、title、author、status，并支持借出、归还、下架切换。"
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
    corpus = f" {_library_scope_corpus(common)} "
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
