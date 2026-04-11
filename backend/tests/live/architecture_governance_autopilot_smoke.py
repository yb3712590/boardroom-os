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

DEFAULT_SCENARIO_SLUG = "architecture_governance_autopilot_smoke"
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


def _assert_architecture_governance_smoke_checkpoint(
    paths: ScenarioPaths | None,
    repository,
    workflow_id: str,
    snapshot: dict[str, Any],
) -> dict[str, Any] | None:
    approved_architect_ticket_ids = snapshot["architect_ticket_ids"]
    approvals = [
        approval
        for approval in snapshot["approvals"]
        if approval["approval_type"] == "MEETING_ESCALATION" and approval["status"] == "APPROVED"
    ]
    governance_architect_employee_ids = sorted(
        str(employee["employee_id"])
        for employee in snapshot["employees"]
        if str(employee.get("role_type") or "") == "governance_architect"
    )
    if not approved_architect_ticket_ids or not approvals or not governance_architect_employee_ids:
        return None

    created_specs = snapshot["created_specs"]
    source_code_tickets = [
        ticket
        for ticket in snapshot["tickets"]
        if str((created_specs.get(str(ticket["ticket_id"])) or {}).get("output_schema_ref") or "") == "source_code_delivery"
    ]
    if source_code_tickets:
        raise AssertionError("Smoke checkpoint must stop before source_code_delivery fanout starts.")

    return {
        "approved_architect_governance_ticket_ids": approved_architect_ticket_ids,
        "approved_meeting_escalation_count": len(approvals),
        "governance_architect_employee_ids": governance_architect_employee_ids,
    }


def _assert_smoke_outcome(
    paths: ScenarioPaths,
    repository,
    workflow_id: str,
    common: dict[str, Any],
) -> dict[str, Any]:
    raise AssertionError("Architecture governance smoke should exit through checkpoint mode before full completion.")


SCENARIO = LiveScenarioDefinition(
    slug=DEFAULT_SCENARIO_SLUG,
    description="Run the architecture governance checkpoint smoke scenario.",
    goal=SCENARIO_GOAL,
    constraints=SCENARIO_CONSTRAINTS,
    assert_outcome=_assert_smoke_outcome,
    checkpoint_assertion=_assert_architecture_governance_smoke_checkpoint,
    checkpoint_label="architecture_governance_gate",
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
