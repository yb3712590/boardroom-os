from __future__ import annotations

import argparse
from pathlib import Path

from boardroom_os.orchestration.prd_delivery import PrdDeliveryTerminalStatus
from boardroom_os.proving.v2_090f_native_golden_sample import (
    V2_090F_DEFAULT_OUTPUT_ROOT,
    V2_090F_DEFAULT_WORKSPACE_ROOT,
    V2_090FNativeGoldenSampleInput,
    run_v2_090f_native_golden_sample,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the V2-090F native golden sample proving entry."
    )
    parser.add_argument(
        "--workspace-root",
        type=Path,
        default=V2_090F_DEFAULT_WORKSPACE_ROOT,
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=V2_090F_DEFAULT_OUTPUT_ROOT,
    )
    parser.add_argument("--reset", action="store_true")
    parser.add_argument("--publish", action="store_true")
    args = parser.parse_args(argv)

    result = run_v2_090f_native_golden_sample(
        V2_090FNativeGoldenSampleInput(
            workspace_root=args.workspace_root,
            output_root=args.output_root,
            require_real_provider=True,
            reset=args.reset,
            publish=args.publish,
        )
    )
    print(result.delivery_result.terminal_status.value)
    if result.delivery_result.audit_path is not None:
        print(result.delivery_result.audit_path.as_posix())
    return _exit_code(result.delivery_result.terminal_status)


def _exit_code(status: PrdDeliveryTerminalStatus) -> int:
    if status in {
        PrdDeliveryTerminalStatus.PASSED_WITHOUT_REWORK,
        PrdDeliveryTerminalStatus.PASSED_AFTER_REWORK,
    }:
        return 0
    if status is PrdDeliveryTerminalStatus.ESCALATED_OR_EXHAUSTED:
        return 4
    return 5


if __name__ == "__main__":
    raise SystemExit(main())
