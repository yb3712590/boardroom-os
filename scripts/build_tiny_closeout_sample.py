from __future__ import annotations

import argparse
from pathlib import Path
import sys

from boardroom_os.proving.v2_090f_prd_agent_team import check_v2_090f_sample_tree


DEFAULT_OUTPUT_ROOT = Path("examples/generated-workspaces/tiny-fullstack")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build or check the V2-090F PRD-to-delivery agent team golden sample."
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=DEFAULT_OUTPUT_ROOT,
        help="Repository-relative sample output root.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Validate the existing V2-090F sample without provider calls or writes.",
    )
    args = parser.parse_args(argv)

    if args.check:
        return check_v2_090f_agent_team_sample(args.output_root)
    return run_v2_090f_agent_team_build(args.output_root)


def check_v2_090f_agent_team_sample(output_root: Path) -> int:
    try:
        check_v2_090f_sample_tree(output_root)
    except Exception as error:
        print(f"tiny closeout sample check failed: {error}", file=sys.stderr)
        return 1
    print(f"tiny closeout sample check passed: {output_root.as_posix()}")
    return 0


def run_v2_090f_agent_team_build(output_root: Path) -> int:
    from scripts.run_v2_090f_native_golden_sample import main as run_native_sample

    return run_native_sample(
        [
            "--reset",
            "--output-root",
            str(output_root),
        ]
    )


if __name__ == "__main__":
    raise SystemExit(main())
