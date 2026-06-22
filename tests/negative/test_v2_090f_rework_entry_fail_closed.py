from __future__ import annotations

import json
from pathlib import Path

import pytest

from boardroom_os.proving.v2_090f_rework_entry import (
    V2_090FReworkEntryStatus,
    V2_090FReworkEntryValidationInput,
    V2_090FTicketGraphSnapshot,
    run_v2_090f_rework_entry_validation,
)
from tests.proving.test_v2_090f_rework_entry_validation import (
    _write_generated_graph,
)


def test_rework_entry_rejects_after_graph_without_patch_ref():
    with pytest.raises(ValueError, match="ticket_graph_patch_ref"):
        V2_090FTicketGraphSnapshot(
            graph_version=9,
            source_ref="00-boardroom/ticket-graph.after-rework.json",
            nodes=(
                {
                    "ticket_id": "ticket.rework.response-shape",
                    "owner_seat_ref": "seat.worker.implementation",
                    "status": "ready",
                    "acceptance_ref_count": 1,
                    "evidence_obligation_count": 1,
                },
            ),
            ticket_graph_patch_ref=None,
        )


def test_raw_exception_does_not_create_rework_request(tmp_path):
    output_root = _write_generated_graph(tmp_path, graph_version=4, status="blocked")
    workspace_root = tmp_path / "workspace"
    (output_root / "30-audit").mkdir(parents=True)
    (output_root / "30-audit/raw-closeout-error.txt").write_text(
        "ValueError: live blackbox evidence is required before closeout",
        encoding="utf-8",
    )

    result = run_v2_090f_rework_entry_validation(
        V2_090FReworkEntryValidationInput(
            output_root=output_root,
            workspace_root=workspace_root,
            run_id="run.v2-090f.raw-error",
            cycle_id="rework-cycle.v2-090f.raw-error",
            max_rounds=1,
            require_real_provider=False,
        )
    )

    assert result.status is V2_090FReworkEntryStatus.BLOCKED_BY_MISSING_REWORK_ENTRY
    assert result.rework_request_path is None
    assert "blocked_by_missing_rework_entry" in result.terminal_path.read_text(
        encoding="utf-8"
    )


def test_rework_entry_active_path_does_not_import_v2_100e_continuation_shortcut():
    root = Path(__file__).resolve().parents[2]
    text = (root / "src/boardroom_os/proving/v2_090f_rework_entry.py").read_text(
        encoding="utf-8"
    )

    assert "run_v2_100_rework_loop_for_request" not in text
    assert "export_v2_100_rework_audit" not in text
