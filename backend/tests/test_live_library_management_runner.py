from __future__ import annotations

from pathlib import Path

from tests.live.library_management_autopilot_live import build_scenario_paths, reset_scenario_root


def test_reset_scenario_root_recreates_expected_layout(tmp_path: Path):
    paths = build_scenario_paths(tmp_path / "library_management_autopilot_live")
    paths.ticket_context_archive_root.mkdir(parents=True, exist_ok=True)
    stale_file = paths.ticket_context_archive_root / "stale.md"
    stale_file.write_text("stale", encoding="utf-8")

    reset_scenario_root(paths, clean=True)

    assert paths.root.exists()
    assert paths.artifact_store_root.exists()
    assert paths.artifact_upload_root.exists()
    assert paths.developer_inspector_root.exists()
    assert paths.ticket_context_archive_root.exists()
    assert not stale_file.exists()
