from __future__ import annotations

import json
from types import SimpleNamespace

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


def _write_generated_graph(tmp_path, *, graph_version: int, status: str):
    output_root = tmp_path / "tiny-fullstack"
    boardroom_root = output_root / "00-boardroom"
    boardroom_root.mkdir(parents=True, exist_ok=True)
    (boardroom_root / "generated-ticket-graph.json").write_text(
        json.dumps(
            {
                "provider_output": {
                    "artifact_name": "ticket-graph",
                    "ticket_graph": {
                        "graph_version": graph_version,
                        "nodes": [
                            {
                                "node_ref": "ticket.worker.implementation",
                                "owner_seat_ref": "seat.worker.implementation",
                                "status": status,
                                "acceptance_refs": ["AC-AGENT-DECLARED-LIBRARY"],
                                "source_surface_refs": ["surface.agent-service"],
                                "evidence_obligations": ["evidence.live-blackbox"],
                                "depends_on": ["ticket.architect.plan"],
                            }
                        ],
                    },
                }
            }
        ),
        encoding="utf-8",
    )
    (boardroom_root / "generated-contracts.json").write_text(
        json.dumps(
            {
                "acceptance_contract": {
                    "criteria": [
                        {
                            "acceptance_ref": "AC-AGENT-DECLARED-LIBRARY",
                            "blocking": True,
                            "evidence_required": ["live_blackbox"],
                            "source_surface_refs": ["surface.agent-service"],
                        }
                    ]
                },
                "package_contract": {
                    "package_contract_id": "package-contract.agent",
                    "source_surfaces": [
                        {
                            "source_surface_ref": "surface.agent-service",
                            "acceptance_refs": ["AC-AGENT-DECLARED-LIBRARY"],
                        }
                    ],
                },
                "evidence_obligations": [
                    {
                        "evidence_obligation_id": "evidence.live-blackbox",
                        "acceptance_refs": ["AC-AGENT-DECLARED-LIBRARY"],
                        "required_artifact_type": "live_blackbox",
                        "blocking": True,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return output_root


def _write_closeout_gate_result(output_root, *, verdict: str, blockers: list[dict[str, str]]):
    closeout_root = output_root / "20-evidence/closeout"
    closeout_root.mkdir(parents=True, exist_ok=True)
    (closeout_root / "closeout-gate-result.json").write_text(
        json.dumps(
            {
                "version": 1,
                "closeout_gate_result_id": {
                    "value": "closeout-gate-result.v2-090f.generated"
                },
                "verdict": verdict,
                "blockers": blockers,
                "checked_refs": ["source-inventory.v2-090f.generated"],
            }
        ),
        encoding="utf-8",
    )


def test_closeout_gate_blocker_projects_to_rework_request(tmp_path, monkeypatch):
    output_root = _write_generated_graph(tmp_path, graph_version=4, status="blocked")
    workspace_root = tmp_path / "workspace"
    _write_closeout_gate_result(
        output_root,
        verdict="blocked",
        blockers=[
            {
                "code": "command_evidence_not_final",
                "message": "service/live evidence missing",
                "related_ref": "cmd.agent-service",
            }
        ],
    )
    monkeypatch.setattr(
        "boardroom_os.proving.v2_090f_rework_entry.run_v2_100_rework_loop_for_request",
        lambda scenario_input, *, request, round_provider=None: _accepted_v2_100_result_with_patch(
            after_graph_version=5,
            patch_ref="ticket-graph-patch.v2-090f.request",
        ),
    )

    result = run_v2_090f_rework_entry_validation(
        V2_090FReworkEntryValidationInput(
            output_root=output_root,
            workspace_root=workspace_root,
            run_id="run.v2-090f.blocked",
            cycle_id="rework-cycle.v2-090f.blocked",
            max_rounds=1,
            require_real_provider=False,
        )
    )

    request = json.loads(result.rework_request_path.read_text(encoding="utf-8"))
    assert result.rework_request_path.is_file()
    assert request["rework_request_id"]["value"].startswith("rework-request.closeout.")
    assert request["issues"][0]["blocker_refs"]


def _closeout_blocker():
    return {
        "code": "command_evidence_not_final",
        "message": "service/live evidence missing",
        "related_ref": "cmd.agent-service",
    }


def _accepted_v2_100_result_with_patch(*, after_graph_version: int, patch_ref: str):
    patch = SimpleNamespace(
        ticket_graph_patch_id=SimpleNamespace(value=patch_ref),
        affected_ticket_refs=(SimpleNamespace(value="ticket.rework.response-shape"),),
        operations=(
            SimpleNamespace(
                operation_id=SimpleNamespace(value="patch-op.v2-090f.response-shape"),
                target_ticket_refs=(SimpleNamespace(value="ticket.rework.response-shape"),),
            ),
        ),
    )
    round_result = SimpleNamespace(
        patch=patch,
        plan_output=SimpleNamespace(
            plan=SimpleNamespace(
                model_dump=lambda mode="json": {
                    "rework_plan_id": "rework-plan.v2-090f.test"
                }
            )
        ),
        remaining_blocker_refs=(),
        accepted_blocker_refs=(
            SimpleNamespace(
                value="closeout-gate-blocker.command_evidence_not_final.cmd.agent-service"
            ),
        ),
    )
    return SimpleNamespace(
        terminal_status=SimpleNamespace(value="accepted"),
        rounds=(round_result,),
        final_projection=SimpleNamespace(graph_version=after_graph_version),
    )


def test_rework_continuation_exports_before_and_after_graph(tmp_path, monkeypatch):
    output_root = _write_generated_graph(tmp_path, graph_version=4, status="blocked")
    _write_closeout_gate_result(
        output_root,
        verdict="blocked",
        blockers=[
            {
                "code": "command_evidence_not_final",
                "message": "service/live evidence missing",
                "related_ref": "cmd.agent-service",
            }
        ],
    )
    captured = {}

    def fake_run_v2_100_rework_loop_for_request(
        scenario_input, *, request, round_provider=None
    ):
        captured["scenario_input"] = scenario_input
        captured["request"] = request
        return _accepted_v2_100_result_with_patch(
            after_graph_version=12,
            patch_ref="ticket-graph-patch.v2-090f.response-shape",
        )

    monkeypatch.setattr(
        "boardroom_os.proving.v2_090f_rework_entry.run_v2_100_rework_loop_for_request",
        fake_run_v2_100_rework_loop_for_request,
    )

    result = run_v2_090f_rework_entry_validation(
        V2_090FReworkEntryValidationInput(
            output_root=output_root,
            workspace_root=tmp_path / "workspace",
            run_id="run.v2-090f.rework",
            cycle_id="rework-cycle.v2-090f.rework",
            max_rounds=2,
            require_real_provider=False,
        )
    )

    before_graph = json.loads(result.before_graph_json_path.read_text(encoding="utf-8"))
    after_graph = json.loads(result.after_graph_json_path.read_text(encoding="utf-8"))

    assert result.status is V2_090FReworkEntryStatus.REWORK_ACCEPTED_CANDIDATE
    assert after_graph["graph_version"] > before_graph["graph_version"]
    assert (
        after_graph["ticket_graph_patch_ref"]
        == "ticket-graph-patch.v2-090f.response-shape"
    )
    assert "ticket.rework." in result.after_graph_mermaid_path.read_text(encoding="utf-8")
