from __future__ import annotations

import json

from boardroom_os.proving.v2_090f_rework_entry import (
    V2_090FReworkEntryStatus,
    V2_090FReworkEntryValidationInput,
    load_v2_090f_ticket_graph_snapshot,
    render_v2_090f_ticket_graph_mermaid,
    run_v2_090f_rework_entry_validation,
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


def test_passed_closeout_writes_no_blocker_candidate_report(tmp_path):
    output_root = tmp_path / "tiny-fullstack"
    workspace_root = tmp_path / "workspace"
    (output_root / "00-boardroom").mkdir(parents=True)
    (output_root / "20-evidence/closeout").mkdir(parents=True)
    (output_root / "00-boardroom/generated-ticket-graph.json").write_text(
        json.dumps(
            {
                "provider_output": {
                    "artifact_name": "ticket-graph",
                    "ticket_graph": {
                        "graph_version": 3,
                        "nodes": [
                            {
                                "node_ref": "ticket.worker.implementation",
                                "owner_seat_ref": "seat.worker.implementation",
                                "status": "completed",
                                "acceptance_refs": ["AC-1"],
                                "evidence_obligations": ["evidence.source"],
                            }
                        ],
                    },
                }
            }
        ),
        encoding="utf-8",
    )
    (output_root / "20-evidence/closeout/closeout-gate-result.json").write_text(
        json.dumps(
            {
                "closeout_gate_result_id": "closeout-gate-result.v2-090f.generated",
                "verdict": "passed",
                "blockers": [],
                "checked_refs": ["source-inventory.v2-090f.generated"],
            }
        ),
        encoding="utf-8",
    )
    (output_root / "closeout-package.json").write_text(
        json.dumps(
            {
                "closeout_package_id": "closeout-package.v2-090f.generated",
                "verdict": "passed",
            }
        ),
        encoding="utf-8",
    )

    result = run_v2_090f_rework_entry_validation(
        V2_090FReworkEntryValidationInput(
            output_root=output_root,
            workspace_root=workspace_root,
            run_id="run.v2-090f.test",
            cycle_id="rework-cycle.v2-090f.test",
            max_rounds=1,
            require_real_provider=False,
        )
    )

    assert result.status is V2_090FReworkEntryStatus.PASSED_WITHOUT_REWORK_CANDIDATE
    assert result.before_graph_json_path.is_file()
    assert result.before_graph_mermaid_path.is_file()
    assert result.after_graph_json_path is None
    assert result.rework_request_path is None
    assert "passed_without_rework_candidate" in result.report_path.read_text(
        encoding="utf-8"
    )
