from __future__ import annotations

import pytest

from app.core.output_schemas import get_output_schema_body, validate_output_payload


def test_output_schema_registry_exposes_consensus_document_schema() -> None:
    schema = get_output_schema_body("consensus_document", 1)

    assert schema["type"] == "object"
    assert "topic" in schema["required"]
    assert "participants" in schema["required"]
    assert "followup_tickets" in schema["required"]


def test_output_schema_registry_accepts_valid_consensus_document_payload() -> None:
    validate_output_payload(
        schema_ref="consensus_document",
        schema_version=1,
        submitted_schema_version="consensus_document_v1",
        payload={
            "topic": "Resolve homepage interaction conflict",
            "participants": ["emp_frontend_2", "emp_checker_1"],
            "input_artifact_refs": ["art://inputs/brief.md"],
            "consensus_summary": "Use the stronger hierarchy with a simplified motion pass.",
            "rejected_options": ["full-motion-hero"],
            "open_questions": [],
            "followup_tickets": [
                {
                    "ticket_id": "tkt_followup_001",
                    "owner_role": "frontend_engineer",
                    "summary": "Implement approved homepage direction",
                }
            ],
        },
    )


def test_output_schema_registry_rejects_invalid_consensus_document_payload() -> None:
    with pytest.raises(ValueError, match="participants must be a non-empty array"):
        validate_output_payload(
            schema_ref="consensus_document",
            schema_version=1,
            submitted_schema_version="consensus_document_v1",
            payload={
                "topic": "Resolve homepage interaction conflict",
                "participants": [],
                "followup_tickets": [],
            },
        )
