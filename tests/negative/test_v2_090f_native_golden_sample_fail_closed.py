from __future__ import annotations

from pathlib import Path


def test_v2_090f_old_rework_entry_files_are_not_active_paths() -> None:
    root = Path(__file__).resolve().parents[2]

    assert not (root / "scripts/run_v2_090f_prd_agent_team.py").exists()
    assert not (root / "src/boardroom_os/proving/v2_090f_rework_entry.py").exists()


def test_v2_090f_active_paths_do_not_expose_rework_stage_switch() -> None:
    root = Path(__file__).resolve().parents[2]
    active_paths = (
        root / "src/boardroom_os/orchestration/prd_delivery.py",
        root / "src/boardroom_os/proving/v2_090f_native_golden_sample.py",
        root / "scripts/run_boardroom_prd_delivery.py",
        root / "scripts/run_v2_090f_native_golden_sample.py",
        root / "scripts/build_tiny_closeout_sample.py",
    )

    for path in active_paths:
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        assert "--stage" not in text
        assert "rework-entry" not in text


def test_v2_090f_native_done_proof_rejects_shortcut_tokens() -> None:
    root = Path(__file__).resolve().parents[2]
    active_paths = (
        root / "src/boardroom_os/orchestration/prd_delivery.py",
        root / "src/boardroom_os/proving/v2_090f_native_golden_sample.py",
        root / "scripts/run_v2_090f_native_golden_sample.py",
    )
    forbidden = (
        "v2-090k-failure-snapshot",
        "V2-100E",
        "run_v2_100e",
        "deterministic_provider_fixture=True",
        "raw exception success",
    )

    for path in active_paths:
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        for token in forbidden:
            assert token not in text
