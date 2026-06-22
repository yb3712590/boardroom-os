from __future__ import annotations

import argparse
from pathlib import Path

from boardroom_os.orchestration.prd_delivery import (
    PrdDeliveryInput,
    PrdDeliveryTerminalStatus,
    run_prd_delivery,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the Boardroom OS native PRD-to-delivery chain."
    )
    parser.add_argument("--prd", type=Path, required=True)
    parser.add_argument(
        "--workspace-root",
        type=Path,
        default=Path(".evidence/atomic-agent/prd-delivery-workspace"),
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("examples/generated-workspaces/prd-delivery"),
    )
    parser.add_argument(
        "--runtime-config",
        type=Path,
        default=Path("config/boardroom-runtime.v2-090f.yaml"),
    )
    parser.add_argument(
        "--providers-config",
        type=Path,
        default=Path("config/boardroom-providers.v2-090f.yaml"),
    )
    parser.add_argument(
        "--roles-config",
        type=Path,
        default=Path("config/boardroom-roles.v2-090f.yaml"),
    )
    parser.add_argument("--reset", action="store_true")
    parser.add_argument("--publish", action="store_true")
    args = parser.parse_args(argv)

    result = run_prd_delivery(
        PrdDeliveryInput(
            prd_path=args.prd,
            workspace_root=args.workspace_root,
            output_root=args.output_root,
            runtime_config_path=args.runtime_config,
            providers_config_path=args.providers_config,
            roles_config_path=args.roles_config,
            require_real_provider=True,
            reset=args.reset,
            publish=args.publish,
        )
    )
    print(result.terminal_status.value)
    if result.audit_path is not None:
        print(result.audit_path.as_posix())
    return _exit_code(result.terminal_status)


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
