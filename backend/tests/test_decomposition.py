from __future__ import annotations

import pytest

from app.core.decomposition import (
    DECOMPOSE_NOW,
    NO_DECOMPOSITION,
    REJECT_UNBOUNDED_REQUEST,
    DecompositionDecision,
    build_decomposition_recovery_plan,
    build_decomposition_ticket_specs,
    validate_decomposition_plan,
)


def _sample_plan() -> dict[str, object]:
    return {
        "plan_id": "decomp_wf_demo_architecture_brief",
        "decision_kind": DECOMPOSE_NOW,
        "reason": "The request spans multiple independent architecture concerns.",
        "evidence_refs": ["art://project-init/wf_demo/board-brief.md"],
        "target_output_schema_ref": "architecture_brief",
        "target_output_schema_version": 1,
        "uses_provider_hidden_state": False,
        "final_output_schema_ref": "architecture_brief",
        "final_output_schema_version": 1,
        "segment_output_schema_ref": "architecture_brief_segment",
        "segment_output_schema_version": 1,
        "role_profile_ref": "architect_primary",
        "segments": [
            {
                "segment_id": "scope",
                "ticket_id": "tkt_wf_demo_ceo_scope",
                "node_id": "node_ceo_scope",
                "summary": "Clarify scope and goals.",
                "input_artifact_refs": ["art://project-init/wf_demo/board-brief.md"],
                "acceptance_criteria": ["Produce an auditable scope segment artifact."],
                "artifact_ref": "art://runtime/tkt_wf_demo_ceo_scope/architecture_brief_segment.json",
                "artifact_path": "reports/governance/tkt_wf_demo_ceo_scope/architecture_brief_segment.json",
            },
            {
                "segment_id": "risks",
                "ticket_id": "tkt_wf_demo_ceo_risks",
                "node_id": "node_ceo_risks",
                "summary": "Clarify risks and verification.",
                "input_artifact_refs": ["art://project-init/wf_demo/board-brief.md"],
                "acceptance_criteria": ["Produce an auditable risk segment artifact."],
                "artifact_ref": "art://runtime/tkt_wf_demo_ceo_risks/architecture_brief_segment.json",
                "artifact_path": "reports/governance/tkt_wf_demo_ceo_risks/architecture_brief_segment.json",
            },
        ],
        "aggregator": {
            "ticket_id": "tkt_wf_demo_ceo_architecture_brief",
            "node_id": "node_ceo_architecture_brief",
            "summary": "Synthesize final architecture brief from segment artifacts.",
            "role_profile_ref": "architect_primary",
            "input_artifact_refs": [
                "art://project-init/wf_demo/board-brief.md",
                "art://runtime/tkt_wf_demo_ceo_scope/architecture_brief_segment.json",
                "art://runtime/tkt_wf_demo_ceo_risks/architecture_brief_segment.json",
            ],
            "acceptance_criteria": ["Reduce all segment artifacts into the final architecture_brief."],
            "artifact_path": "reports/governance/tkt_wf_demo_ceo_architecture_brief/architecture_brief.json",
            "dependency_policy": "all_segments_complete",
            "reduce_instructions": "Read every segment artifact and synthesize the final schema without hidden state.",
        },
    }


def test_ceo_decomposition_decision_contract_expresses_all_actions() -> None:
    for action in (NO_DECOMPOSITION, DECOMPOSE_NOW, REJECT_UNBOUNDED_REQUEST):
        decision = DecompositionDecision(
            decision_kind=action,
            reason="Explicit CEO assessment.",
            evidence_refs=["art://inputs/request.md"],
            target_output_schema_ref="architecture_brief",
            target_output_schema_version=1,
            uses_provider_hidden_state=False,
        )

        assert decision.to_payload()["decision_kind"] == action
        assert decision.to_payload()["uses_provider_hidden_state"] is False


def test_decompose_now_plan_expands_segment_tickets_and_aggregator_dependencies() -> None:
    plan = validate_decomposition_plan(_sample_plan())

    specs = build_decomposition_ticket_specs(
        plan,
        build_ticket_spec=lambda planned, dependency_gate_refs: {
            "ticket_id": planned["ticket_id"],
            "node_id": planned["node_id"],
            "output_schema_ref": planned["output_schema_ref"],
            "input_artifact_refs": planned["input_artifact_refs"],
            "allowed_write_set": planned["allowed_write_set"],
            "dispatch_intent": {"dependency_gate_refs": dependency_gate_refs},
        },
    )

    segment_specs = specs[:-1]
    aggregator_spec = specs[-1]
    segment_ticket_ids = [spec["ticket_id"] for spec in segment_specs]
    segment_artifact_refs = [
        "art://runtime/tkt_wf_demo_ceo_scope/architecture_brief_segment.json",
        "art://runtime/tkt_wf_demo_ceo_risks/architecture_brief_segment.json",
    ]

    assert len(specs) == 3
    assert [spec["dispatch_intent"]["dependency_gate_refs"] for spec in segment_specs] == [[], []]
    assert aggregator_spec["dispatch_intent"]["dependency_gate_refs"] == segment_ticket_ids
    assert aggregator_spec["input_artifact_refs"] == [
        "art://project-init/wf_demo/board-brief.md",
        *segment_artifact_refs,
    ]


def test_decomposition_plan_rejects_provider_hidden_state_and_fallback_fields() -> None:
    plan = _sample_plan()
    plan["uses_provider_hidden_state"] = True

    with pytest.raises(ValueError, match="provider hidden state"):
        validate_decomposition_plan(plan)

    plan = _sample_plan()
    plan["segments"][0]["fallback_provider_ids"] = ["provider_a"]  # type: ignore[index]

    with pytest.raises(ValueError, match="fallback_provider_ids"):
        validate_decomposition_plan(plan)


def test_recovery_decomposition_plan_is_auditable_and_avoids_provider_state() -> None:
    plan = build_decomposition_recovery_plan(
        workflow_id="wf_recovery",
        source_ticket_id="tkt_large_request",
        source_node_id="node_large_request",
        created_spec={
            "ticket_id": "tkt_large_request",
            "node_id": "node_large_request",
            "role_profile_ref": "architect_primary",
            "summary": "Create a complete governance brief.",
            "input_artifact_refs": ["art://inputs/brief.md"],
            "output_schema_ref": "architecture_brief",
            "output_schema_version": 1,
        },
        failure_payload={
            "failure_kind": "REQUEST_TOO_LARGE",
            "failure_message": "Request exceeded provider context limits.",
            "failure_fingerprint": "fp_large_request",
            "failure_detail": {"limit": "context"},
        },
    )

    validated = validate_decomposition_plan(plan)

    assert validated["decision_kind"] == DECOMPOSE_NOW
    assert validated["uses_provider_hidden_state"] is False
    assert validated["target_output_schema_ref"] == "architecture_brief"
    assert validated["final_output_schema_ref"] == "architecture_brief"
    assert validated["segment_output_schema_ref"] == "architecture_brief_segment"
    assert [segment["segment_id"] for segment in validated["segments"]] == [
        "scope_and_requirements",
        "solution_and_risks",
    ]
    assert validated["aggregator"]["dependency_policy"] == "all_segments_complete"
    assert any("fp_large_request" in evidence_ref for evidence_ref in validated["evidence_refs"])
    assert "provider_id" not in str(validated)
    assert "fallback_provider_ids" not in str(validated)
    assert "local_deterministic" not in str(validated)
    assert "provider_response_id" not in str(validated)


def test_recovery_decomposition_plan_blocks_without_replayable_source_spec() -> None:
    with pytest.raises(ValueError, match="source ticket created spec"):
        build_decomposition_recovery_plan(
            workflow_id="wf_recovery",
            source_ticket_id="tkt_large_request",
            source_node_id="node_large_request",
            created_spec={
                "ticket_id": "tkt_large_request",
                "node_id": "node_large_request",
                "role_profile_ref": "architect_primary",
                "input_artifact_refs": ["art://inputs/brief.md"],
                "output_schema_ref": "architecture_brief",
            },
            failure_payload={
                "failure_kind": "REQUEST_TOO_LARGE",
                "failure_message": "Request exceeded provider context limits.",
                "failure_fingerprint": "fp_large_request",
            },
        )
