from __future__ import annotations

import os
from pathlib import Path

import pytest


@pytest.mark.skipif(
    os.environ.get("BOARDROOM_RUN_REAL_PROVIDER_PROVING") != "1"
    or not os.environ.get("OPENAI_API_KEY"),
    reason="V2-090F native golden sample requires explicit opt-in and provider secret",
)
def test_v2_090f_native_golden_sample_real_provider(tmp_path: Path) -> None:
    from boardroom_os.orchestration.prd_delivery import PrdDeliveryTerminalStatus
    from boardroom_os.proving.v2_090f_native_golden_sample import (
        V2_090FNativeGoldenSampleInput,
        run_v2_090f_native_golden_sample,
    )

    result = run_v2_090f_native_golden_sample(
        V2_090FNativeGoldenSampleInput(
            workspace_root=tmp_path / "workspace",
            output_root=tmp_path / "tiny-fullstack",
            require_real_provider=True,
            reset=True,
        )
    )

    assert result.delivery_result.terminal_status in {
        PrdDeliveryTerminalStatus.PASSED_WITHOUT_REWORK,
        PrdDeliveryTerminalStatus.PASSED_AFTER_REWORK,
        PrdDeliveryTerminalStatus.ESCALATED_OR_EXHAUSTED,
        PrdDeliveryTerminalStatus.BLOCKED_FAIL_CLOSED,
    }
    assert result.done_candidate is (
        result.delivery_result.terminal_status
        in {
            PrdDeliveryTerminalStatus.PASSED_WITHOUT_REWORK,
            PrdDeliveryTerminalStatus.PASSED_AFTER_REWORK,
        }
    )
    assert result.delivery_result.audit_path is not None
    assert result.delivery_result.audit_path.is_file()
