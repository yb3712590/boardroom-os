from __future__ import annotations

from datetime import datetime

from app.core.deliverable_contract import (
    ContractEvaluationStatus,
    ConvergenceAllowedGap,
    ConvergencePolicy,
    DeliverableEvaluationPolicy,
    DeliverableEvidencePack,
    EvidencePack,
    checker_contract_gate,
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


def test_required_source_surfaces_compile_from_scope_assets_and_allowed_write_set() -> None:
    contract = compile_deliverable_contract(
        workflow_id="wf_round9b_surfaces",
        graph_version="gv_9b_surfaces",
        locked_scope=[
            {
                "scope_ref": "scope://loan/runtime",
                "surface_id": "surface.loan_backend",
                "summary": "Loan APIs stay in backend service code.",
                "acceptance_criteria_refs": ["AC-loan-api"],
                "required_capabilities": ["source.modify.backend"],
                "required_evidence_kinds": ["source_inventory", "unit_test"],
                "minimum_non_placeholder_evidence": ["business source inventory", "loan API unit assertions"],
            }
        ],
        acceptance_criteria=[
            {
                "criterion_id": "AC-loan-api",
                "description": "Loan API validates borrow and return behavior.",
            }
        ],
        metadata={
            "governance_decisions": [
                {
                    "asset_ref": "decision://loan/backend-only",
                    "surface_id": "surface.loan_backend",
                    "acceptance_criteria_refs": ["AC-loan-api"],
                }
            ],
            "architecture_design_assets": [
                {
                    "asset_ref": "design://loan/service-boundary",
                    "surface_id": "surface.loan_backend",
                }
            ],
            "backlog_recommendations": [
                {
                    "asset_ref": "backlog://loan/followup",
                    "surface_id": "surface.loan_backend",
                }
            ],
            "allowed_write_set": [
                {
                    "surface_id": "surface.loan_backend",
                    "capability": "source.modify.backend",
                    "required_tests": ["pytest backend/tests/test_loan_api.py -q"],
                }
            ],
        },
    )

    surface = contract.required_source_surfaces[0]
    assert surface.surface_id == "surface.loan_backend"
    assert surface.path_patterns == ["10-project/src/backend/**"]
    assert surface.owning_capabilities == ["source.modify.backend"]
    assert surface.acceptance_criteria_refs == ["AC-loan-api"]
    assert surface.required_evidence_kinds == ["source_inventory", "unit_test"]
    assert surface.minimum_non_placeholder_evidence == [
        "business source inventory",
        "loan API unit assertions",
    ]
    assert surface.required_tests == ["pytest backend/tests/test_loan_api.py -q"]
    assert surface.metadata["locked_scope_refs"] == ["scope://loan/runtime"]
    assert surface.metadata["governance_decision_refs"] == ["decision://loan/backend-only"]
    assert surface.metadata["architecture_design_asset_refs"] == ["design://loan/service-boundary"]
    assert surface.metadata["backlog_recommendation_refs"] == ["backlog://loan/followup"]


def test_evidence_pack_maps_current_source_test_check_git_and_closeout_to_acceptance() -> None:
    contract = compile_deliverable_contract(
        workflow_id="wf_round9b_mapping",
        graph_version="gv_9b_mapping",
        acceptance_criteria=[
            {
                "criterion_id": "AC-loan-api",
                "description": "Loan API behavior is implemented and verified.",
                "priority": "MUST",
            }
        ],
        required_source_surfaces=[
            {
                "surface_id": "surface.loan_backend",
                "path_patterns": ["10-project/src/backend/**"],
                "owning_capabilities": ["source.modify.backend"],
                "acceptance_criteria_refs": ["AC-loan-api"],
                "required_evidence_kinds": [
                    "source_inventory",
                    "unit_test",
                    "maker_checker_verdict",
                    "git_closeout",
                    "risk_disposition",
                ],
                "minimum_non_placeholder_evidence": ["business source inventory", "loan API assertions"],
            }
        ],
        required_evidence=[
            {
                "evidence_id": "ev_source",
                "evidence_kind": "source_inventory",
                "acceptance_criteria_refs": ["AC-loan-api"],
                "source_surface_refs": ["surface.loan_backend"],
            },
            {
                "evidence_id": "ev_unit",
                "evidence_kind": "unit_test",
                "acceptance_criteria_refs": ["AC-loan-api"],
                "source_surface_refs": ["surface.loan_backend"],
            },
            {
                "evidence_id": "ev_check",
                "evidence_kind": "maker_checker_verdict",
                "acceptance_criteria_refs": ["AC-loan-api"],
                "source_surface_refs": ["surface.loan_backend"],
            },
            {
                "evidence_id": "ev_git",
                "evidence_kind": "git_closeout",
                "acceptance_criteria_refs": ["AC-loan-api"],
                "source_surface_refs": ["surface.loan_backend"],
            },
            {
                "evidence_id": "ev_closeout",
                "evidence_kind": "risk_disposition",
                "acceptance_criteria_refs": ["AC-loan-api"],
                "source_surface_refs": ["surface.loan_backend"],
            },
        ],
    )
    refs = [
        "art://workspace/tkt_impl/source/src/backend/loans.py",
        "art://workspace/tkt_impl/tests/attempt-1/pytest.json",
        "art://runtime/tkt_check/delivery-check-report.json",
        "art://runtime/tkt_impl/git/attempt-1/commit.json",
        "art://runtime/tkt_closeout/delivery-closeout-package.json",
    ]
    evidence_pack = EvidencePack.model_validate(
        {
            "workflow_id": "wf_round9b_mapping",
            "graph_version": "gv_9b_mapping",
            "evidence": [
                {
                    "evidence_ref": refs[0],
                    "evidence_kind": "source_inventory",
                    "producer_ticket_id": "tkt_impl",
                    "producer_node_ref": "node://impl",
                    "source_surface_refs": ["surface.loan_backend"],
                    "artifact_kind": "WORKSPACE_SOURCE",
                    "legality_status": "ACCEPTED",
                    "current_pointer_status": "CURRENT",
                    "acceptance_criteria_refs": ["AC-loan-api"],
                    "placeholder": False,
                    "archive": False,
                    "metadata": {"business_assertion_refs": ["loan-create", "loan-return"]},
                },
                {
                    "evidence_ref": refs[1],
                    "evidence_kind": "unit_test",
                    "producer_ticket_id": "tkt_impl",
                    "producer_node_ref": "node://impl",
                    "source_surface_refs": ["surface.loan_backend"],
                    "artifact_kind": "TEST_EVIDENCE",
                    "legality_status": "ACCEPTED",
                    "current_pointer_status": "CURRENT",
                    "acceptance_criteria_refs": ["AC-loan-api"],
                    "placeholder": False,
                    "archive": False,
                    "metadata": {"business_assertion_refs": ["test_loan_borrow", "test_loan_return"]},
                },
                {
                    "evidence_ref": refs[2],
                    "evidence_kind": "maker_checker_verdict",
                    "producer_ticket_id": "tkt_check",
                    "producer_node_ref": "node://check",
                    "source_surface_refs": ["surface.loan_backend"],
                    "artifact_kind": "DELIVERY_CHECK_REPORT",
                    "legality_status": "ACCEPTED",
                    "current_pointer_status": "CURRENT",
                    "acceptance_criteria_refs": ["AC-loan-api"],
                    "placeholder": False,
                    "archive": False,
                    "metadata": {"business_assertion_refs": ["checker-reviewed-loan-api"]},
                },
                {
                    "evidence_ref": refs[3],
                    "evidence_kind": "git_closeout",
                    "producer_ticket_id": "tkt_impl",
                    "producer_node_ref": "node://impl",
                    "source_surface_refs": ["surface.loan_backend"],
                    "artifact_kind": "GIT_EVIDENCE",
                    "legality_status": "ACCEPTED",
                    "current_pointer_status": "CURRENT",
                    "acceptance_criteria_refs": ["AC-loan-api"],
                    "placeholder": False,
                    "archive": False,
                    "metadata": {"business_assertion_refs": ["changed-file-inventory"]},
                },
                {
                    "evidence_ref": refs[4],
                    "evidence_kind": "risk_disposition",
                    "producer_ticket_id": "tkt_closeout",
                    "producer_node_ref": "node://closeout",
                    "source_surface_refs": ["surface.loan_backend"],
                    "artifact_kind": "CLOSEOUT_PACKAGE",
                    "legality_status": "ACCEPTED",
                    "current_pointer_status": "CURRENT",
                    "acceptance_criteria_refs": ["AC-loan-api"],
                    "placeholder": False,
                    "archive": False,
                    "metadata": {"business_assertion_refs": ["risk-accepted-none"]},
                },
            ],
            "final_evidence_refs": refs,
        }
    )

    evaluation = evaluate_deliverable_contract(
        contract,
        evidence_pack,
        DeliverableEvaluationPolicy(policy_ref="policy:round9b"),
    )

    assert evaluation.status == "SATISFIED"
    assert evaluation.blocking_finding_count == 0


def test_critical_acceptance_missing_source_test_check_git_or_closeout_evidence_blocks() -> None:
    contract = compile_deliverable_contract(
        workflow_id="wf_round9b_missing_acceptance_evidence",
        graph_version="gv_9b_missing_acceptance_evidence",
        acceptance_criteria=[
            {
                "criterion_id": "AC-critical",
                "description": "Critical behavior has complete source, test, check, git, and closeout evidence.",
                "priority": "MUST",
            }
        ],
        required_source_surfaces=[
            {
                "surface_id": "surface.critical",
                "path_patterns": ["10-project/src/backend/**"],
                "owning_capabilities": ["source.modify.backend"],
                "acceptance_criteria_refs": ["AC-critical"],
                "required_evidence_kinds": [
                    "source_inventory",
                    "unit_test",
                    "maker_checker_verdict",
                    "git_closeout",
                    "risk_disposition",
                ],
                "minimum_non_placeholder_evidence": ["critical source", "critical test assertions"],
            }
        ],
    )
    evaluation = evaluate_deliverable_contract(
        contract,
        EvidencePack.model_validate(
            {
                "workflow_id": "wf_round9b_missing_acceptance_evidence",
                "graph_version": "gv_9b_missing_acceptance_evidence",
                "evidence": [
                    {
                        "evidence_ref": "art://workspace/tkt_impl/source/src/backend/critical.py",
                        "evidence_kind": "source_inventory",
                        "producer_ticket_id": "tkt_impl",
                        "producer_node_ref": "node://impl",
                        "source_surface_refs": ["surface.critical"],
                        "artifact_kind": "WORKSPACE_SOURCE",
                        "legality_status": "ACCEPTED",
                        "current_pointer_status": "CURRENT",
                        "acceptance_criteria_refs": ["AC-critical"],
                        "placeholder": False,
                        "archive": False,
                        "metadata": {"business_assertion_refs": ["critical-source"]},
                    }
                ],
                "final_evidence_refs": ["art://workspace/tkt_impl/source/src/backend/critical.py"],
            }
        ),
        DeliverableEvaluationPolicy(policy_ref="policy:round9b"),
    )

    assert evaluation.status == "BLOCKED"
    assert [
        finding.reason_code for finding in evaluation.findings
    ] == ["acceptance_missing_required_evidence"]
    assert evaluation.findings[0].acceptance_criteria_refs == ["AC-critical"]
    assert evaluation.findings[0].source_surface_refs == ["surface.critical"]
    assert evaluation.findings[0].metadata["missing_evidence_kinds"] == [
        "git_closeout",
        "maker_checker_verdict",
        "risk_disposition",
        "unit_test",
    ]


def test_placeholder_source_and_generic_test_evidence_fail_closed() -> None:
    contract = compile_deliverable_contract(
        workflow_id="wf_round9b_placeholder",
        graph_version="gv_9b_placeholder",
        acceptance_criteria=[
            {
                "criterion_id": "AC-placeholder",
                "description": "Placeholder source and shallow tests cannot satisfy delivery.",
            }
        ],
        required_evidence=[
            {
                "evidence_id": "ev_source",
                "evidence_kind": "source_inventory",
                "acceptance_criteria_refs": ["AC-placeholder"],
                "source_surface_refs": ["surface.placeholder"],
            },
            {
                "evidence_id": "ev_unit",
                "evidence_kind": "unit_test",
                "acceptance_criteria_refs": ["AC-placeholder"],
                "source_surface_refs": ["surface.placeholder"],
            },
        ],
        required_source_surfaces=[
            {
                "surface_id": "surface.placeholder",
                "path_patterns": ["10-project/src/backend/**"],
                "owning_capabilities": ["source.modify.backend"],
                "acceptance_criteria_refs": ["AC-placeholder"],
                "required_evidence_kinds": ["source_inventory", "unit_test"],
                "minimum_non_placeholder_evidence": ["business source inventory", "business test assertions"],
            }
        ],
    )
    evidence_pack = EvidencePack.model_validate(
        {
            "workflow_id": "wf_round9b_placeholder",
            "graph_version": "gv_9b_placeholder",
            "evidence": [
                {
                    "evidence_ref": "art://workspace/tkt_impl/source/source.py",
                    "evidence_kind": "source_inventory",
                    "producer_ticket_id": "tkt_impl",
                    "producer_node_ref": "node://impl",
                    "source_surface_refs": ["surface.placeholder"],
                    "artifact_kind": "WORKSPACE_SOURCE",
                    "legality_status": "PLACEHOLDER",
                    "current_pointer_status": "CURRENT",
                    "acceptance_criteria_refs": ["AC-placeholder"],
                    "placeholder": True,
                    "archive": False,
                    "metadata": {"placeholder_reasons": ["source.py placeholder"]},
                },
                {
                    "evidence_ref": "art://workspace/tkt_impl/tests/attempt-1/pytest.json",
                    "evidence_kind": "unit_test",
                    "producer_ticket_id": "tkt_impl",
                    "producer_node_ref": "node://impl",
                    "source_surface_refs": ["surface.placeholder"],
                    "artifact_kind": "TEST_EVIDENCE",
                    "legality_status": "ACCEPTED",
                    "current_pointer_status": "CURRENT",
                    "acceptance_criteria_refs": ["AC-placeholder"],
                    "placeholder": False,
                    "archive": False,
                    "metadata": {
                        "placeholder_reasons": ["generic 1 passed"],
                        "stdout_fallback": True,
                    },
                },
            ],
            "final_evidence_refs": [
                "art://workspace/tkt_impl/source/source.py",
                "art://workspace/tkt_impl/tests/attempt-1/pytest.json",
            ],
        }
    )

    evaluation = evaluate_deliverable_contract(
        contract,
        evidence_pack,
        DeliverableEvaluationPolicy(policy_ref="policy:round9b"),
    )

    assert evaluation.status == "BLOCKED"
    assert [finding.reason_code for finding in evaluation.findings] == [
        "invalid_evidence_for_contract",
        "missing_required_evidence",
        "acceptance_missing_required_evidence",
    ]
    assert evaluation.findings[0].evidence_refs == [
        "art://workspace/tkt_impl/source/source.py",
        "art://workspace/tkt_impl/tests/attempt-1/pytest.json",
    ]


def test_superseded_archive_unknown_and_stale_pointer_evidence_do_not_satisfy_required_evidence() -> None:
    contract = compile_deliverable_contract(
        workflow_id="wf_round9b_legality",
        graph_version="gv_9b_legality",
        acceptance_criteria=[
            {
                "criterion_id": "AC-legality",
                "description": "Only current accepted evidence can satisfy acceptance.",
            }
        ],
        required_evidence=[
            {
                "evidence_id": "ev_source",
                "evidence_kind": "source_inventory",
                "acceptance_criteria_refs": ["AC-legality"],
                "source_surface_refs": ["surface.legality"],
                "minimum_count": 4,
            }
        ],
    )
    evidence_pack = EvidencePack.model_validate(
        {
            "workflow_id": "wf_round9b_legality",
            "graph_version": "gv_9b_legality",
            "evidence": [
                {
                    "evidence_ref": "art://workspace/tkt_old/source/src/backend/old.py",
                    "evidence_kind": "source_inventory",
                    "producer_ticket_id": "tkt_old",
                    "producer_node_ref": "node://old",
                    "source_surface_refs": ["surface.legality"],
                    "artifact_kind": "WORKSPACE_SOURCE",
                    "legality_status": "SUPERSEDED",
                    "current_pointer_status": "SUPERSEDED",
                    "acceptance_criteria_refs": ["AC-legality"],
                    "superseded_by_refs": ["art://workspace/tkt_new/source/src/backend/new.py"],
                    "placeholder": False,
                    "archive": False,
                },
                {
                    "evidence_ref": "art://archive/tkt_old/source.json",
                    "evidence_kind": "source_inventory",
                    "producer_ticket_id": "tkt_old",
                    "producer_node_ref": "node://old",
                    "source_surface_refs": ["surface.legality"],
                    "artifact_kind": "ARCHIVE",
                    "legality_status": "ARCHIVE",
                    "current_pointer_status": "ARCHIVE",
                    "acceptance_criteria_refs": ["AC-legality"],
                    "placeholder": False,
                    "archive": True,
                },
                {
                    "evidence_ref": "art://workspace/tkt_missing/source/src/backend/missing.py",
                    "evidence_kind": "source_inventory",
                    "producer_ticket_id": "tkt_missing",
                    "producer_node_ref": "node://missing",
                    "source_surface_refs": ["surface.legality"],
                    "artifact_kind": "UNKNOWN",
                    "legality_status": "UNKNOWN_REF",
                    "current_pointer_status": "UNKNOWN",
                    "acceptance_criteria_refs": ["AC-legality"],
                    "placeholder": False,
                    "archive": False,
                },
                {
                    "evidence_ref": "art://workspace/tkt_stale/source/src/backend/stale.py",
                    "evidence_kind": "source_inventory",
                    "producer_ticket_id": "tkt_stale",
                    "producer_node_ref": "node://stale",
                    "source_surface_refs": ["surface.legality"],
                    "artifact_kind": "WORKSPACE_SOURCE",
                    "legality_status": "STALE_CURRENT_POINTER",
                    "current_pointer_status": "STALE",
                    "acceptance_criteria_refs": ["AC-legality"],
                    "placeholder": False,
                    "archive": False,
                },
            ],
            "final_evidence_refs": [
                "art://workspace/tkt_old/source/src/backend/old.py",
                "art://archive/tkt_old/source.json",
                "art://workspace/tkt_missing/source/src/backend/missing.py",
                "art://workspace/tkt_stale/source/src/backend/stale.py",
            ],
        }
    )

    evaluation = evaluate_deliverable_contract(
        contract,
        evidence_pack,
        DeliverableEvaluationPolicy(policy_ref="policy:round9b"),
    )

    assert evaluation.status == "BLOCKED"
    assert [finding.reason_code for finding in evaluation.findings] == [
        "invalid_evidence_for_contract",
        "missing_required_evidence",
    ]
    assert evaluation.findings[0].metadata["invalid_statuses"] == [
        "ARCHIVE",
        "STALE_CURRENT_POINTER",
        "SUPERSEDED",
        "UNKNOWN_REF",
    ]


def _blocking_contract_evaluation():
    contract = compile_deliverable_contract(
        workflow_id="wf_round9c_blocking",
        graph_version="gv_9c",
        acceptance_criteria=[
            {
                "criterion_id": "AC-contract-gap",
                "description": "Blocking gaps cannot be approved by checker verdict alone.",
            }
        ],
        required_evidence=[
            {
                "evidence_id": "ev_contract_gap",
                "evidence_kind": "source_inventory",
                "acceptance_criteria_refs": ["AC-contract-gap"],
                "source_surface_refs": ["surface.contract_gap"],
            }
        ],
    )
    return evaluate_deliverable_contract(
        contract,
        EvidencePack.model_validate(
            {
                "workflow_id": "wf_round9c_blocking",
                "graph_version": "gv_9c",
                "final_evidence_refs": ["art://runtime/tkt_closeout/delivery-closeout-package.json"],
            }
        ),
        DeliverableEvaluationPolicy(policy_ref="policy:round9c"),
    )


def test_approved_with_notes_does_not_allow_blocking_contract_gap() -> None:
    gate = checker_contract_gate(
        evaluation=_blocking_contract_evaluation(),
        review_status="APPROVED_WITH_NOTES",
        checked_at=datetime.fromisoformat("2026-05-04T10:00:00+08:00"),
    )

    assert gate.allowed is False
    assert gate.reason_code == "deliverable_contract_blocked"
    assert gate.requires_convergence_policy is True
    assert gate.blocking_finding_count == 1


def test_approved_with_notes_allows_non_blocking_notes_when_contract_is_satisfied() -> None:
    contract = compile_deliverable_contract(
        workflow_id="wf_round9c_nonblocking",
        graph_version="gv_9c",
        acceptance_criteria=[
            {
                "criterion_id": "AC-nonblocking",
                "description": "Non-blocking checker notes can pass with contract evidence.",
            }
        ],
        required_evidence=[
            {
                "evidence_id": "ev_source",
                "evidence_kind": "source_inventory",
                "acceptance_criteria_refs": ["AC-nonblocking"],
            }
        ],
    )
    evaluation = evaluate_deliverable_contract(
        contract,
        EvidencePack.model_validate(
            {
                "workflow_id": "wf_round9c_nonblocking",
                "graph_version": "gv_9c",
                "evidence": [
                    {
                        "evidence_ref": "art://workspace/tkt_impl/source/src/backend/app.py",
                        "evidence_kind": "source_inventory",
                        "acceptance_criteria_refs": ["AC-nonblocking"],
                        "legality_status": "ACCEPTED",
                    }
                ],
                "final_evidence_refs": ["art://workspace/tkt_impl/source/src/backend/app.py"],
            }
        ),
        DeliverableEvaluationPolicy(policy_ref="policy:round9c"),
    )

    gate = checker_contract_gate(
        evaluation=evaluation,
        review_status="APPROVED_WITH_NOTES",
        checked_at=datetime.fromisoformat("2026-05-04T10:00:00+08:00"),
    )

    assert evaluation.status == ContractEvaluationStatus.SATISFIED
    assert gate.allowed is True
    assert gate.reason_code == "contract_satisfied"
    assert gate.requires_convergence_policy is False


def test_failed_delivery_report_requires_structured_convergence_policy() -> None:
    gate = checker_contract_gate(
        evaluation=_blocking_contract_evaluation(),
        review_status="APPROVED",
        failed_delivery_report=True,
        checked_at=datetime.fromisoformat("2026-05-04T10:00:00+08:00"),
    )

    assert gate.allowed is False
    assert gate.reason_code == "convergence_policy_required"
    assert gate.requires_convergence_policy is True


def test_convergence_policy_allows_only_declared_gap_scope_and_expiry() -> None:
    evaluation = _blocking_contract_evaluation()
    finding = evaluation.findings[0]
    checked_at = datetime.fromisoformat("2026-05-04T10:00:00+08:00")
    policy = ConvergencePolicy(
        policy_ref="conv://round9c/allow-contract-gap",
        allow_failed_delivery_report=True,
        allowed_gaps=[
            ConvergenceAllowedGap(
                finding_id=finding.finding_id,
                reason_code=finding.reason_code,
                risk_disposition="accepted for checkpoint-only delivery",
                approver_ref="approval://board/round9c",
                source_ref="decision://round9c/contract-gap",
                expires_at=datetime.fromisoformat("2026-05-05T10:00:00+08:00"),
                scope_refs=["AC-contract-gap"],
            )
        ],
    )

    allowed_gate = checker_contract_gate(
        evaluation=evaluation,
        review_status="APPROVED_WITH_NOTES",
        convergence_policy=policy,
        failed_delivery_report=True,
        scope_refs=["AC-contract-gap"],
        checked_at=checked_at,
    )
    scope_mismatch_gate = checker_contract_gate(
        evaluation=evaluation,
        review_status="APPROVED_WITH_NOTES",
        convergence_policy=policy,
        failed_delivery_report=True,
        scope_refs=["AC-other"],
        checked_at=checked_at,
    )
    expired_gate = checker_contract_gate(
        evaluation=evaluation,
        review_status="APPROVED_WITH_NOTES",
        convergence_policy=policy,
        failed_delivery_report=True,
        scope_refs=["AC-contract-gap"],
        checked_at=datetime.fromisoformat("2026-05-06T10:00:00+08:00"),
    )

    assert allowed_gate.allowed is True
    assert allowed_gate.reason_code == "convergence_policy_allowed"
    assert allowed_gate.allowed_gap_refs == [finding.finding_id]
    assert scope_mismatch_gate.allowed is False
    assert scope_mismatch_gate.reason_code == "deliverable_contract_blocked"
    assert expired_gate.allowed is False
    assert expired_gate.reason_code == "deliverable_contract_blocked"


def test_convergence_policy_default_checked_at_handles_timezone_expiry() -> None:
    evaluation = _blocking_contract_evaluation()
    finding = evaluation.findings[0]
    policy = ConvergencePolicy(
        policy_ref="conv://round9c/tz-aware",
        allow_failed_delivery_report=True,
        allowed_gaps=[
            ConvergenceAllowedGap(
                finding_id=finding.finding_id,
                reason_code=finding.reason_code,
                risk_disposition="accepted before expiry",
                approver_ref="approval://board/round9c",
                source_ref="decision://round9c/tz-aware",
                expires_at=datetime.fromisoformat("2099-05-04T10:00:00+08:00"),
                scope_refs=["AC-contract-gap"],
            )
        ],
    )

    gate = checker_contract_gate(
        evaluation=evaluation,
        review_status="APPROVED",
        convergence_policy=policy,
        failed_delivery_report=True,
    )

    assert gate.allowed is True


def test_convergence_policy_must_cover_every_blocking_gap() -> None:
    contract = compile_deliverable_contract(
        workflow_id="wf_round9c_two_gaps",
        graph_version="gv_9c",
        acceptance_criteria=[
            {"criterion_id": "AC-one", "description": "First required evidence."},
            {"criterion_id": "AC-two", "description": "Second required evidence."},
        ],
        required_evidence=[
            {
                "evidence_id": "ev_one",
                "evidence_kind": "source_inventory",
                "acceptance_criteria_refs": ["AC-one"],
            },
            {
                "evidence_id": "ev_two",
                "evidence_kind": "unit_test",
                "acceptance_criteria_refs": ["AC-two"],
            },
        ],
    )
    evaluation = evaluate_deliverable_contract(
        contract,
        EvidencePack.model_validate(
            {
                "workflow_id": "wf_round9c_two_gaps",
                "graph_version": "gv_9c",
                "final_evidence_refs": ["art://runtime/tkt_closeout/delivery-closeout-package.json"],
            }
        ),
        DeliverableEvaluationPolicy(policy_ref="policy:round9c"),
    )
    policy = ConvergencePolicy(
        policy_ref="conv://round9c/partial",
        allow_failed_delivery_report=True,
        allowed_gaps=[
            ConvergenceAllowedGap(
                finding_id=evaluation.findings[0].finding_id,
                reason_code=evaluation.findings[0].reason_code,
                risk_disposition="accepted for one gap only",
                approver_ref="approval://board/round9c",
                source_ref="decision://round9c/partial",
                scope_refs=["AC-one"],
            )
        ],
    )

    gate = checker_contract_gate(
        evaluation=evaluation,
        review_status="APPROVED",
        convergence_policy=policy,
        failed_delivery_report=True,
        scope_refs=["AC-one"],
        checked_at=datetime.fromisoformat("2026-05-04T10:00:00+08:00"),
    )

    assert gate.allowed is False
    assert gate.reason_code == "deliverable_contract_blocked"
    assert gate.blocking_finding_count == 1
