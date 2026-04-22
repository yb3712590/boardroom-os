from __future__ import annotations

from tests.scenario._entry import run_stage_entry, skipif_scenario_stage_disabled


pytestmark = skipif_scenario_stage_disabled()


def test_library_management_stage_05_closeout_mainline_merge() -> None:
    run_stage_entry("stage_05_closeout_mainline_merge")
