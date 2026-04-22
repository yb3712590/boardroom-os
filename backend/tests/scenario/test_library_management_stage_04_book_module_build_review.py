from __future__ import annotations

from tests.scenario._entry import run_stage_entry, skipif_scenario_stage_disabled


pytestmark = skipif_scenario_stage_disabled()


def test_library_management_stage_04_book_module_build_review() -> None:
    run_stage_entry("stage_04_book_module_build_review")
