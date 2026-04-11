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

DEFAULT_SCENARIO_SLUG = "architecture_governance_autopilot_live"
SCENARIO_GOAL = "全自动架构拆解并交付一个跨部门会议室预订与审批系统"
SCENARIO_CONSTRAINTS = [
    (
        "该项目全权授予CEO自由裁量的权利，进度完全由CEO自主推进无需经过董事会审议，包括招聘、"
        "技术决策会议、架构治理文档、开发实施、测试验收与 closeout。"
    ),
    "CEO 必须真实招聘并真实使用 architect_primary。",
    "implementation fanout 前必须先完成 architect_primary 治理文档，并通过一次技术决策会议锁定架构边界。",
    "meeting gate 放行前，不得提前创建 source_code_delivery 实现票。",
]


def build_scenario_paths(scenario_root: Path | None = None) -> ScenarioPaths:
    return _build_scenario_paths(DEFAULT_SCENARIO_SLUG, scenario_root)


def _assert_architecture_governance_outcome(
    paths: ScenarioPaths,
    repository,
    workflow_id: str,
    common: dict[str, Any],
) -> dict[str, Any]:
    approved_architect_ticket_ids = common["architect_ticket_ids"]
    if not approved_architect_ticket_ids:
        raise AssertionError("No approved architect governance ticket was recorded.")

    approvals = [
        approval
        for approval in common["approvals"]
        if approval["approval_type"] == "MEETING_ESCALATION" and approval["status"] == "APPROVED"
    ]
    if len(approvals) < 2:
        raise AssertionError("Architecture scenario expected at least two approved MEETING_ESCALATION reviews.")

    created_specs = common["created_specs"]
    tickets = common["tickets"]
    source_code_tickets = [
        ticket
        for ticket in tickets
        if str((created_specs.get(str(ticket["ticket_id"])) or {}).get("output_schema_ref") or "") == "source_code_delivery"
    ]
    if not source_code_tickets:
        raise AssertionError("No source_code_delivery ticket was created after the governance gate.")

    second_meeting_resolved_at = approvals[1]["resolved_at"]
    first_source_created_at = min(ticket["created_at"] for ticket in source_code_tickets)
    if first_source_created_at <= second_meeting_resolved_at:
        raise AssertionError("source_code_delivery fanout started before the architecture meeting gate was approved.")

    return {
        "approved_meeting_escalation_count": len(approvals),
        "approved_architect_governance_ticket_ids": approved_architect_ticket_ids,
        "first_source_code_ticket_id": str(source_code_tickets[0]["ticket_id"]),
    }


SCENARIO = LiveScenarioDefinition(
    slug=DEFAULT_SCENARIO_SLUG,
    description="Run the architecture governance autopilot live scenario.",
    goal=SCENARIO_GOAL,
    constraints=SCENARIO_CONSTRAINTS,
    assert_outcome=_assert_architecture_governance_outcome,
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
