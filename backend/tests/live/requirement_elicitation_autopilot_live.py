from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from tests.live._autopilot_live_harness import (
    LiveScenarioDefinition,
    ScenarioPaths,
    build_scenario_paths as _build_scenario_paths,
    run_cli,
    run_live_scenario as _run_live_scenario,
)

DEFAULT_SCENARIO_SLUG = "requirement_elicitation_autopilot_live"
SCENARIO_GOAL = "全自动澄清并交付一个高校实验室预约与审批系统"
SCENARIO_CONSTRAINTS = [
    (
        "该项目全权授予CEO自由裁量的权利，进度完全由CEO自主推进无需经过董事会审议，包括需求澄清、"
        "招聘、架构梳理、开发实施、测试验收与 closeout。"
    ),
    "初始化输入存在明显信息缺口，必须先走 REQUIREMENT_ELICITATION，再继续 architecture_brief 与 implementation fanout。",
    "在需求澄清批准前，不得提前创建 source_code_delivery 实现票。",
    "需求澄清完成后，仍必须进入 architecture_brief、source_code_delivery、delivery_closeout_package 主线。",
]


def build_scenario_paths(scenario_root: Path | None = None) -> ScenarioPaths:
    return _build_scenario_paths(DEFAULT_SCENARIO_SLUG, scenario_root)


def _assert_requirement_elicitation_outcome(
    paths: ScenarioPaths,
    repository,
    workflow_id: str,
    common: dict[str, Any],
) -> dict[str, Any]:
    approvals = common["approvals"]
    elicitation_approvals = [
        approval
        for approval in approvals
        if approval["approval_type"] == "REQUIREMENT_ELICITATION" and approval["status"] == "APPROVED"
    ]
    if not elicitation_approvals:
        raise AssertionError("No approved REQUIREMENT_ELICITATION approval was recorded.")

    created_specs = common["created_specs"]
    tickets = common["tickets"]
    source_code_tickets = [
        ticket
        for ticket in tickets
        if str((created_specs.get(str(ticket["ticket_id"])) or {}).get("output_schema_ref") or "") == "source_code_delivery"
    ]
    if not source_code_tickets:
        raise AssertionError("No source_code_delivery ticket was created after requirement elicitation.")
    latest_elicitation_resolved_at = max(approval["resolved_at"] for approval in elicitation_approvals)
    first_source_created_at = min(ticket["created_at"] for ticket in source_code_tickets)
    if first_source_created_at <= latest_elicitation_resolved_at:
        raise AssertionError("source_code_delivery fanout started before requirement elicitation was approved.")

    if not any(
        str((created_specs.get(str(ticket["ticket_id"])) or {}).get("output_schema_ref") or "") == "architecture_brief"
        for ticket in tickets
    ):
        raise AssertionError("No architecture_brief ticket was created after requirement elicitation.")

    return {
        "requirement_elicitation_approval_ids": [approval["approval_id"] for approval in elicitation_approvals],
        "requirement_elicitation_count": len(elicitation_approvals),
        "first_source_code_ticket_id": str(source_code_tickets[0]["ticket_id"]),
    }


SCENARIO = LiveScenarioDefinition(
    slug=DEFAULT_SCENARIO_SLUG,
    description="Run the requirement elicitation autopilot live scenario.",
    goal=SCENARIO_GOAL,
    constraints=SCENARIO_CONSTRAINTS,
    force_requirement_elicitation=True,
    assert_outcome=_assert_requirement_elicitation_outcome,
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
