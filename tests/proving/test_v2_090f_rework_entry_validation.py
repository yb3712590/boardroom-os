from __future__ import annotations

import json

from boardroom_os.proving.v2_090f_rework_entry import (
    load_v2_090f_ticket_graph_snapshot,
    render_v2_090f_ticket_graph_mermaid,
)


def test_ticket_graph_snapshot_exports_required_labels(tmp_path):
    output_root = tmp_path / "tiny-fullstack"
    boardroom_root = output_root / "00-boardroom"
    boardroom_root.mkdir(parents=True)
    (boardroom_root / "generated-ticket-graph.json").write_text(
        json.dumps(
            {
                "provider_output": {
                    "artifact_name": "ticket-graph",
                    "ticket_graph": {
                        "graph_version": 7,
                        "nodes": [
                            {
                                "node_ref": "ticket.worker.implementation",
                                "owner_seat_ref": "seat.worker.implementation",
                                "status": "blocked",
                                "acceptance_refs": ["AC-1", "AC-2"],
                                "evidence_obligations": ["evidence.source"],
                                "depends_on": ["ticket.architect.plan"],
                            }
                        ],
                    },
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    snapshot = load_v2_090f_ticket_graph_snapshot(output_root)
    mermaid = render_v2_090f_ticket_graph_mermaid(snapshot)

    assert snapshot.graph_version == 7
    assert snapshot.nodes[0].ticket_id == "ticket.worker.implementation"
    assert snapshot.nodes[0].acceptance_ref_count == 2
    assert snapshot.nodes[0].evidence_obligation_count == 1
    assert (
        '"ticket.worker.implementation\\nseat.worker.implementation\\nblocked\\nAC:2 EV:1"'
        in mermaid
    )
