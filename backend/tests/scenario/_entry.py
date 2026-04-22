from __future__ import annotations

import pytest

from tests.scenario._runner import (
    default_scenario_test_config_path,
    is_scenario_test_enabled,
    run_configured_stage,
)


def skipif_scenario_stage_disabled() -> pytest.MarkDecorator:
    return pytest.mark.skipif(
        not is_scenario_test_enabled(),
        reason="Set BOARDROOM_OS_SCENARIO_TEST_ENABLE=1 to run gated scenario stage tests.",
    )


def run_stage_entry(stage_id: str) -> None:
    result = run_configured_stage(default_scenario_test_config_path(), stage_id)
    assert result.success is True
