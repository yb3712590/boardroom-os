from __future__ import annotations

import pytest

from boardroom_os.proving.v2_090f_rework_entry import V2_090FTicketGraphSnapshot


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
