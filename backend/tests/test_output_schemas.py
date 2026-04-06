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
                    "delivery_stage": "BUILD",
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


def test_output_schema_registry_rejects_invalid_consensus_document_delivery_stage() -> None:
    with pytest.raises(ValueError, match="delivery_stage"):
        validate_output_payload(
            schema_ref="consensus_document",
            schema_version=1,
            submitted_schema_version="consensus_document_v1",
            payload={
                "topic": "Resolve homepage interaction conflict",
                "participants": ["emp_frontend_2", "emp_checker_1"],
                "followup_tickets": [
                    {
                        "ticket_id": "tkt_followup_001",
                        "owner_role": "frontend_engineer",
                        "summary": "Implement approved homepage direction",
                        "delivery_stage": "LAUNCH",
                    }
                ],
            },
        )


def test_output_schema_registry_exposes_maker_checker_verdict_schema() -> None:
    schema = get_output_schema_body("maker_checker_verdict", 1)

    assert schema["type"] == "object"
    assert "summary" in schema["required"]
    assert "review_status" in schema["required"]
    assert "findings" in schema["required"]


def test_output_schema_registry_accepts_valid_maker_checker_verdict_payload() -> None:
    validate_output_payload(
        schema_ref="maker_checker_verdict",
        schema_version=1,
        submitted_schema_version="maker_checker_verdict_v1",
        payload={
            "summary": "Checker approved the visual milestone with one non-blocking note.",
            "review_status": "APPROVED_WITH_NOTES",
            "findings": [
                {
                    "finding_id": "finding_cta_spacing",
                    "severity": "low",
                    "category": "VISUAL_POLISH",
                    "headline": "CTA spacing can be tightened slightly.",
                    "summary": "Current CTA spacing is acceptable but leaves room for polish.",
                    "required_action": "Tighten CTA spacing during downstream implementation.",
                    "blocking": False,
                }
            ],
        },
    )


def test_output_schema_registry_rejects_changes_required_without_blocking_finding() -> None:
    with pytest.raises(ValueError, match="blocking"):
        validate_output_payload(
            schema_ref="maker_checker_verdict",
            schema_version=1,
            submitted_schema_version="maker_checker_verdict_v1",
            payload={
                "summary": "Checker requires changes before the board sees this milestone.",
                "review_status": "CHANGES_REQUIRED",
                "findings": [
                    {
                        "finding_id": "finding_weak_hierarchy",
                        "severity": "high",
                        "category": "VISUAL_HIERARCHY",
                        "headline": "Visual hierarchy is still weak.",
                        "summary": "The hero does not establish clear first-screen priority.",
                        "required_action": "Strengthen the hero hierarchy before resubmitting.",
                        "blocking": False,
                    }
                ],
            },
        )


def test_output_schema_registry_exposes_implementation_bundle_schema() -> None:
    schema = get_output_schema_body("implementation_bundle", 1)

    assert schema["type"] == "object"
    assert "summary" in schema["required"]
    assert "deliverable_artifact_refs" in schema["required"]


def test_output_schema_registry_accepts_valid_implementation_bundle_payload() -> None:
    validate_output_payload(
        schema_ref="implementation_bundle",
        schema_version=1,
        submitted_schema_version="implementation_bundle_v1",
        payload={
            "summary": "Homepage implementation bundle is ready for internal checking.",
            "deliverable_artifact_refs": ["art://runtime/tkt_followup_scope_build/implementation-bundle.json"],
            "implementation_notes": ["Hero layout and CTA hierarchy now follow the approved scope lock."],
        },
    )


def test_output_schema_registry_exposes_delivery_check_report_schema() -> None:
    schema = get_output_schema_body("delivery_check_report", 1)

    assert schema["type"] == "object"
    assert "summary" in schema["required"]
    assert "status" in schema["required"]
    assert "findings" in schema["required"]


def test_output_schema_registry_accepts_valid_delivery_check_report_payload() -> None:
    validate_output_payload(
        schema_ref="delivery_check_report",
        schema_version=1,
        submitted_schema_version="delivery_check_report_v1",
        payload={
            "summary": "Internal check confirmed the implementation still stays inside the approved scope.",
            "status": "PASS_WITH_NOTES",
            "findings": [
                {
                    "finding_id": "finding_scope_copy",
                    "summary": "Keep the launch copy trimmed to the approved scope.",
                    "blocking": False,
                }
            ],
        },
    )


def test_output_schema_registry_accepts_valid_delivery_closeout_package_payload_with_documentation_updates() -> None:
    validate_output_payload(
        schema_ref="delivery_closeout_package",
        schema_version=1,
        submitted_schema_version="delivery_closeout_package_v1",
        payload={
            "summary": "Delivery closeout package is ready for internal review.",
            "final_artifact_refs": ["art://runtime/tkt_closeout_001/delivery-closeout-package.json"],
            "handoff_notes": [
                "Board-approved final option is captured in this closeout package.",
                "Final evidence remains linked back to the board review pack.",
            ],
            "documentation_updates": [
                {
                    "doc_ref": "doc/TODO.md",
                    "status": "UPDATED",
                    "summary": "Marked P2-GOV-007 as completed after closeout evidence sync landed.",
                },
                {
                    "doc_ref": "README.md",
                    "status": "NO_CHANGE_REQUIRED",
                    "summary": "No public capability or runtime flow changed in this round.",
                },
            ],
        },
    )


def test_output_schema_registry_rejects_delivery_closeout_package_invalid_documentation_update_status() -> None:
    with pytest.raises(Exception) as exc_info:
        validate_output_payload(
            schema_ref="delivery_closeout_package",
            schema_version=1,
            submitted_schema_version="delivery_closeout_package_v1",
            payload={
                "summary": "Delivery closeout package is ready for internal review.",
                "final_artifact_refs": ["art://runtime/tkt_closeout_001/delivery-closeout-package.json"],
                "handoff_notes": ["Final evidence remains linked back to the board review pack."],
                "documentation_updates": [
                    {
                        "doc_ref": "doc/TODO.md",
                        "status": "PENDING",
                        "summary": "This should be rejected.",
                    }
                ],
            },
        )
    assert getattr(exc_info.value, "field_path", None) == "documentation_updates[0].status"


@pytest.mark.parametrize(
    ("field_name", "field_value"),
    [
        ("doc_ref", ""),
        ("summary", ""),
    ],
)
def test_output_schema_registry_rejects_delivery_closeout_package_documentation_update_missing_required_text(
    field_name: str,
    field_value: str,
) -> None:
    documentation_update = {
        "doc_ref": "doc/TODO.md",
        "status": "UPDATED",
        "summary": "Marked P2-GOV-007 as completed after closeout evidence sync landed.",
    }
    documentation_update[field_name] = field_value

    with pytest.raises(Exception) as exc_info:
        validate_output_payload(
            schema_ref="delivery_closeout_package",
            schema_version=1,
            submitted_schema_version="delivery_closeout_package_v1",
            payload={
                "summary": "Delivery closeout package is ready for internal review.",
                "final_artifact_refs": ["art://runtime/tkt_closeout_001/delivery-closeout-package.json"],
                "handoff_notes": ["Final evidence remains linked back to the board review pack."],
                "documentation_updates": [documentation_update],
            },
        )
    assert getattr(exc_info.value, "field_path", None) == f"documentation_updates[0].{field_name}"


def test_output_schema_registry_exposes_structured_failure_detail_for_missing_required_field() -> None:
    with pytest.raises(Exception) as exc_info:
        validate_output_payload(
            schema_ref="ui_milestone_review",
            schema_version=1,
            submitted_schema_version="ui_milestone_review_v1",
            payload={
                "summary": "Provider left out the options array.",
                "recommended_option_id": "option_a",
            },
        )

    assert getattr(exc_info.value, "field_path", None) == "options"
    assert getattr(exc_info.value, "expected", None) == "non-empty array"
    assert getattr(exc_info.value, "actual", None) == "missing"
