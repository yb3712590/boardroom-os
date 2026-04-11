from __future__ import annotations

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
SCENARIO_CONSTRAINTS = [
    (
        "该项目全权授予CEO自由裁量的权利，进度完全由CEO自主推进无需经过董事会审议，包括招聘，"
        "召集架构师、系统分析师选型和详细梳理系统，分配开发工作，审阅测试结果，审阅里程碑，"
        "交给运维人员发布，向董事会交付报告。"
    ),
    "CEO 必须真实招聘并真实使用 architect_primary，系统分析职责并入架构治理链。",
    (
        "需求拆解必须足够原子，workflow 最终 ticket 总数不得少于 30，"
        "并覆盖架构、详细设计、前端、后端、数据、测试、评审、发布、closeout。"
    ),
    "开发、测试、平台岗位允许继续扩招，且同岗人员画像必须明显拉开风险偏好、质疑方式、节奏和审美。",
    (
        "图书馆管理系统至少覆盖：认证与 RBAC、读者档案、馆藏目录、检索、借阅归还、预约、罚金、"
        "库存与盘点、公告、统计报表、审计日志、部署发布、运维监控与交付报告。"
    ),
]


def build_scenario_paths(scenario_root: Path | None = None) -> ScenarioPaths:
    return _build_scenario_paths(DEFAULT_SCENARIO_SLUG, scenario_root)


def _assert_library_outcome(
    paths: ScenarioPaths,
    repository,
    workflow_id: str,
    common: dict[str, Any],
) -> dict[str, Any]:
    tickets = common["tickets"]
    if len(tickets) < 30:
        raise AssertionError(f"Workflow produced {len(tickets)} tickets, expected at least 30.")

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
