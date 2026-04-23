from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from tests.live._configured_runner import run_configured_live_scenario
from tests.live._config import load_live_scenario_config


def main(argv: list[str] | None = None) -> int:
    bootstrap_parser = argparse.ArgumentParser(add_help=False)
    bootstrap_parser.add_argument("--config", type=Path, required=True)
    bootstrap_args, _ = bootstrap_parser.parse_known_args(argv)
    config = load_live_scenario_config(bootstrap_args.config)

    parser = argparse.ArgumentParser(description=config.scenario.description)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--clean", action="store_true", help="Delete and recreate the scenario directory first.")
    parser.add_argument("--max-ticks", type=int, default=config.runtime.max_ticks)
    parser.add_argument("--timeout-sec", type=int, default=config.runtime.timeout_sec)
    parser.add_argument("--seed", type=int, default=config.runtime.seed)
    parser.add_argument("--scenario-root", type=Path, default=None)
    args = parser.parse_args(argv)

    report = run_configured_live_scenario(
        args.config,
        clean=args.clean,
        max_ticks=args.max_ticks,
        timeout_sec=args.timeout_sec,
        seed=args.seed,
        scenario_root=args.scenario_root,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
