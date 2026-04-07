from __future__ import annotations

from app.core.process_assets import build_result_process_assets


def test_build_result_process_assets_adds_governance_document_asset() -> None:
    created_spec = {
        "output_schema_ref": "architecture_brief",
    }
    result_payload = {
        "title": "Architecture brief for governance chain",
        "summary": "Keep the next slice aligned to the MVP boundary.",
        "document_kind_ref": "architecture_brief",
        "linked_document_refs": ["doc://governance/technology-decision/current"],
        "linked_artifact_refs": ["art://inputs/board-brief.md"],
        "source_process_asset_refs": ["pa://artifact/art%3A%2F%2Finputs%2Fboard-brief.md"],
        "decisions": ["Keep the next slice local-first."],
        "constraints": ["Do not widen into remote handoff."],
        "sections": [],
        "followup_recommendations": [
            {
                "recommendation_id": "rec_followup_build",
                "summary": "Prepare the next implementation ticket without widening scope.",
                "target_role": "frontend_engineer",
            }
        ],
    }

    produced_assets = build_result_process_assets(
        ticket_id="tkt_gov_doc_source",
        created_spec=created_spec,
        result_payload=result_payload,
        artifact_refs=["art://runtime/tkt_gov_doc_source/architecture-brief.json"],
    )

    governance_assets = [
        asset for asset in produced_assets if asset["process_asset_kind"] == "GOVERNANCE_DOCUMENT"
    ]

    assert governance_assets == [
        {
            "process_asset_ref": "pa://governance-document/tkt_gov_doc_source",
            "process_asset_kind": "GOVERNANCE_DOCUMENT",
            "producer_ticket_id": "tkt_gov_doc_source",
            "summary": "Keep the next slice aligned to the MVP boundary.",
            "consumable_by": ["context_compiler", "followup_ticket", "review"],
            "source_metadata": {
                "document_kind_ref": "architecture_brief",
                "source_artifact_ref": "art://runtime/tkt_gov_doc_source/architecture-brief.json",
            },
        }
    ]
