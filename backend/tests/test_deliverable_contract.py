from __future__ import annotations

from app.core.deliverable_contract import (
    DeliverableEvaluationPolicy,
    DeliverableEvidencePack,
    compile_deliverable_contract,
    evaluate_deliverable_contract,
)


def test_prd_acceptance_compiles_to_versioned_deliverable_contract() -> None:
    contract = compile_deliverable_contract(
        workflow_id="wf_round9a",
        graph_version="gv_9a",
        source_prd_refs=["prd://round9a/main"],
        locked_scope=[{"scope_ref": "scope://round9a/locked", "summary": "Round 9A contract skeleton"}],
        acceptance_criteria=[
            "The final closeout must prove the PRD acceptance criteria.",
            {
                "criterion_id": "AC-evidence",
                "description": "Every required evidence item maps to an acceptance criterion.",
                "source_refs": ["prd://round9a/main#ac-evidence"],
            },
        ],
        required_evidence=[
            {
                "evidence_id": "ev_source_inventory",
                "evidence_kind": "source_inventory",
                "acceptance_criteria_refs": ["AC-evidence"],
            }
        ],
        required_source_surfaces=[
            {
                "surface_id": "surface.application",
                "path_patterns": ["10-project/src/app/**"],
                "owning_capabilities": ["source.modify.application"],
                "acceptance_criteria_refs": ["AC-evidence"],
                "required_evidence_kinds": ["source_inventory"],
            }
        ],
        closeout_requirements=[
            {
                "obligation_id": "closeout.final_evidence",
                "summary": "Closeout package includes final evidence refs.",
                "required_evidence_refs": ["ev_source_inventory"],
            }
        ],
    )

    assert contract.contract_version == "v1"
    assert contract.contract_id.startswith("dc_wf_round9a_v1_")
    assert contract.workflow_id == "wf_round9a"
    assert contract.graph_version == "gv_9a"
    assert contract.source_prd_refs == ["prd://round9a/main"]
    assert [item.criterion_id for item in contract.acceptance_criteria] == [
        "AC-evidence",
        contract.acceptance_criteria[1].criterion_id,
    ]
    assert contract.required_source_surfaces[0].surface_id == "surface.application"
    assert contract.required_evidence[0].evidence_kind == "source_inventory"
    assert contract.closeout_requirements[0].required_evidence_refs == ["ev_source_inventory"]


def test_empty_acceptance_fail_closed() -> None:
    contract = compile_deliverable_contract(
        workflow_id="wf_empty_acceptance",
        graph_version="gv_empty",
        acceptance_criteria=[],
    )

    evaluation = evaluate_deliverable_contract(
        contract,
        DeliverableEvidencePack(workflow_id="wf_empty_acceptance", graph_version="gv_empty"),
        DeliverableEvaluationPolicy(policy_ref="policy:round9a"),
    )

    assert evaluation.status == "BLOCKED"
    assert evaluation.blocking_finding_count == 2
    assert [finding.reason_code for finding in evaluation.findings] == [
        "missing_acceptance_criteria",
        "empty_final_evidence",
    ]
    assert all(finding.blocking for finding in evaluation.findings)


def test_missing_required_evidence_is_blocking_finding() -> None:
    contract = compile_deliverable_contract(
        workflow_id="wf_missing_evidence",
        graph_version="gv_missing_evidence",
        acceptance_criteria=[
            {
                "criterion_id": "AC-source-inventory",
                "description": "Source inventory proves changed files.",
            }
        ],
        required_evidence=[
            {
                "evidence_id": "ev_source_inventory",
                "evidence_kind": "source_inventory",
                "acceptance_criteria_refs": ["AC-source-inventory"],
            }
        ],
    )

    evaluation = evaluate_deliverable_contract(
        contract,
        DeliverableEvidencePack(
            workflow_id="wf_missing_evidence",
            graph_version="gv_missing_evidence",
            final_evidence_refs=["art://runtime/tkt_closeout/delivery-closeout-package.json"],
        ),
        DeliverableEvaluationPolicy(policy_ref="policy:round9a"),
    )

    assert evaluation.status == "BLOCKED"
    assert evaluation.blocking_finding_count == 1
    assert evaluation.findings[0].reason_code == "missing_required_evidence"
    assert evaluation.findings[0].required_evidence_refs == ["ev_source_inventory"]
    assert evaluation.findings[0].acceptance_criteria_refs == ["AC-source-inventory"]


def test_unknown_evidence_kind_and_empty_final_evidence_fail_closed() -> None:
    contract = compile_deliverable_contract(
        workflow_id="wf_unknown_evidence",
        graph_version="gv_unknown_evidence",
        acceptance_criteria=["Acceptance must have known evidence kinds."],
    )

    evaluation = evaluate_deliverable_contract(
        contract,
        DeliverableEvidencePack.model_validate(
            {
                "workflow_id": "wf_unknown_evidence",
                "graph_version": "gv_unknown_evidence",
                "evidence": [
                    {
                        "evidence_ref": "art://runtime/tkt_1/provider-raw-transcript.json",
                        "evidence_kind": "provider_raw_transcript",
                        "acceptance_criteria_refs": [contract.acceptance_criteria[0].criterion_id],
                    }
                ],
                "final_evidence_refs": [],
            }
        ),
        DeliverableEvaluationPolicy(policy_ref="policy:round9a"),
    )

    assert evaluation.status == "BLOCKED"
    assert [finding.reason_code for finding in evaluation.findings] == [
        "unknown_evidence_kind",
        "empty_final_evidence",
    ]
    assert evaluation.findings[0].evidence_refs == [
        "art://runtime/tkt_1/provider-raw-transcript.json"
    ]


def test_repeated_evaluation_is_byte_stable() -> None:
    contract = compile_deliverable_contract(
        workflow_id="wf_stable_eval",
        graph_version="gv_stable",
        acceptance_criteria=[
            {
                "criterion_id": "AC-runtime-smoke",
                "description": "Runtime smoke evidence proves the behavior.",
            }
        ],
        required_evidence=[
            {
                "evidence_id": "ev_runtime_smoke",
                "evidence_kind": "runtime_smoke",
                "acceptance_criteria_refs": ["AC-runtime-smoke"],
            }
        ],
    )
    evidence_pack = DeliverableEvidencePack.model_validate(
        {
            "workflow_id": "wf_stable_eval",
            "graph_version": "gv_stable",
            "evidence": [
                {
                    "evidence_ref": "art://runtime/tkt_1/runtime-smoke.json",
                    "evidence_kind": "runtime_smoke",
                    "acceptance_criteria_refs": ["AC-runtime-smoke"],
                    "producer_ticket_id": "tkt_1",
                    "artifact_kind": "runtime_smoke",
                    "legality_status": "ACCEPTED",
                }
            ],
            "final_evidence_refs": ["art://runtime/tkt_1/runtime-smoke.json"],
        }
    )
    policy = DeliverableEvaluationPolicy(policy_ref="policy:round9a")

    first = evaluate_deliverable_contract(contract, evidence_pack, policy).model_dump(mode="json")
    second = evaluate_deliverable_contract(contract, evidence_pack, policy).model_dump(mode="json")

    assert first == second
    assert first["status"] == "SATISFIED"
    assert first["blocking_finding_count"] == 0
    assert first["evaluation_fingerprint"].startswith(f"de_{contract.contract_id}_")
