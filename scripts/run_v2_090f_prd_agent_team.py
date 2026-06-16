from __future__ import annotations

import argparse
import os
from pathlib import Path

from boardroom_os.proving.v2_090f_prd_agent_team import (
    build_v2_090f_planning_provider_adapter,
    load_v2_090f_prd,
    reset_v2_090f_workspace,
    resolve_v2_090f_config_paths_from_env,
    run_v2_090f_planning_preflight,
    run_v2_090f_provider_planning_stage,
    run_v2_090f_closeout_stage,
    run_v2_090f_worker_execution_stage,
    validate_agent_team_autonomy_inputs,
)
from boardroom_os.proving.v2_090f_rework_entry import (
    V2_090FReworkEntryStatus,
    V2_090FReworkEntryValidationInput,
    run_v2_090f_rework_entry_validation,
)
from boardroom_os.config.boardroom import load_boardroom_settings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run V2-090F PRD-to-delivery agent team proving."
    )
    parser.add_argument("--prd", required=True)
    parser.add_argument("--reset", action="store_true")
    parser.add_argument(
        "--workspace-root",
        default=".evidence/atomic-agent/v2-090f-prd-agent-team-workspace",
    )
    parser.add_argument(
        "--output-root",
        default="examples/generated-workspaces/tiny-fullstack",
    )
    parser.add_argument(
        "--stage",
        choices=("planning", "worker", "full", "rework-entry"),
        default="planning",
    )
    args = parser.parse_args(argv)

    prd = load_v2_090f_prd(Path(args.prd))
    validate_agent_team_autonomy_inputs(
        prd_text=prd.text,
        predefined_ticket_refs=(),
    )
    if os.environ.get("BOARDROOM_RUN_REAL_PROVIDER_PROVING") != "1":
        print("BOARDROOM_RUN_REAL_PROVIDER_PROVING=1 is required for V2-090F")
        return 2
    if args.reset:
        reset_v2_090f_workspace(Path(args.workspace_root))
    env_values = dict(os.environ)
    result = run_v2_090f_planning_preflight(
        prd=prd,
        output_root=Path(args.output_root),
        env_values=env_values,
    )
    settings = load_boardroom_settings(
        paths=resolve_v2_090f_config_paths_from_env(env_values),
        env_values=env_values,
    )
    result = run_v2_090f_provider_planning_stage(
        prd=prd,
        output_root=Path(args.output_root),
        settings=settings,
        provider_adapter_factory=lambda seat_ref, output_name: build_v2_090f_planning_provider_adapter(
            settings=settings,
            seat_ref=seat_ref,
            output_root=Path(args.output_root),
        ),
    )
    if args.stage in {"worker", "full", "rework-entry"}:
        result = run_v2_090f_worker_execution_stage(
            output_root=Path(args.output_root),
            workspace_root=Path(args.workspace_root),
            settings=settings,
        )
    if args.stage in {"full", "rework-entry"}:
        result = run_v2_090f_closeout_stage(
            output_root=Path(args.output_root),
            workspace_root=Path(args.workspace_root),
            settings=settings,
        )
    if args.stage == "rework-entry":
        validation_result = run_v2_090f_rework_entry_validation(
            V2_090FReworkEntryValidationInput(
                output_root=Path(args.output_root),
                workspace_root=Path(args.workspace_root),
                run_id="run.v2-090f.rework-entry",
                cycle_id="rework-cycle.v2-090f.rework-entry",
                max_rounds=2,
                require_real_provider=True,
            )
        )
        status_value = validation_result.status.value
        print(status_value)
        if status_value in {
            V2_090FReworkEntryStatus.PASSED_WITHOUT_REWORK_CANDIDATE.value,
            V2_090FReworkEntryStatus.REWORK_ACCEPTED_CANDIDATE.value,
        }:
            return 0
        if status_value == V2_090FReworkEntryStatus.REWORK_ESCALATED_OR_EXHAUSTED.value:
            return 4
        return 5
    if args.stage == "full":
        print(result["status"])
        return 0
    print(result["blocker"])
    return 3


if __name__ == "__main__":
    raise SystemExit(main())
