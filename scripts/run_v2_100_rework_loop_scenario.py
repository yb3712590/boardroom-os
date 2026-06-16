from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from boardroom_os.proving.v2_100_resettable_fixture import build_v2_100_scenario_input
from boardroom_os.proving.v2_100_rework_loop import (
    export_v2_100_rework_audit,
    run_v2_100_rework_loop_scenario,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the V2-100E rework loop scenario.")
    parser.add_argument("--snapshot", required=True, type=Path)
    parser.add_argument("--env", required=True, type=Path)
    parser.add_argument("--export-root", required=True, type=Path)
    parser.add_argument("--max-rounds", type=int, default=2)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    scenario_input = build_v2_100_scenario_input(
        snapshot_summary_path=args.snapshot,
        export_root=args.export_root,
        provider_env_path=args.env,
        require_real_provider=True,
        max_rounds=args.max_rounds,
    )
    result = run_v2_100_rework_loop_scenario(scenario_input)
    audit_export = export_v2_100_rework_audit(result, args.export_root)
    result_with_export = result.model_copy(update={"audit_export": audit_export})
    print(
        json.dumps(
            result_with_export.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
