from __future__ import annotations

from collections.abc import Callable
from typing import Any


UI_MILESTONE_REVIEW_SCHEMA_REF = "ui_milestone_review"
UI_MILESTONE_REVIEW_SCHEMA_VERSION = 1
UI_MILESTONE_REVIEW_SCHEMA_ID = (
    f"{UI_MILESTONE_REVIEW_SCHEMA_REF}_v{UI_MILESTONE_REVIEW_SCHEMA_VERSION}"
)
CONSENSUS_DOCUMENT_SCHEMA_REF = "consensus_document"
CONSENSUS_DOCUMENT_SCHEMA_VERSION = 1
MAKER_CHECKER_VERDICT_SCHEMA_REF = "maker_checker_verdict"
MAKER_CHECKER_VERDICT_SCHEMA_VERSION = 1

OutputSchemaValidator = Callable[[dict[str, Any]], None]


def schema_id(schema_ref: str, schema_version: int) -> str:
    return f"{schema_ref}_v{schema_version}"


def _ui_milestone_review_schema_body() -> dict[str, Any]:
    return {
        "type": "object",
        "required": ["summary", "recommended_option_id", "options"],
        "properties": {
            "summary": {"type": "string"},
            "recommended_option_id": {"type": "string"},
            "options": {
                "type": "array",
                "minItems": 1,
                "items": {
                    "type": "object",
                    "required": ["option_id", "label", "summary"],
                    "properties": {
                        "option_id": {"type": "string"},
                        "label": {"type": "string"},
                        "summary": {"type": "string"},
                        "artifact_refs": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                    },
                },
            },
        },
    }


def _consensus_document_schema_body() -> dict[str, Any]:
    return {
        "type": "object",
        "required": ["topic", "participants", "followup_tickets"],
        "properties": {
            "topic": {"type": "string"},
            "participants": {
                "type": "array",
                "minItems": 1,
                "items": {"type": "string"},
            },
            "input_artifact_refs": {
                "type": "array",
                "items": {"type": "string"},
            },
            "consensus_summary": {"type": "string"},
            "rejected_options": {
                "type": "array",
                "items": {"type": "string"},
            },
            "open_questions": {
                "type": "array",
                "items": {"type": "string"},
            },
            "followup_tickets": {
                "type": "array",
                "minItems": 1,
                "items": {
                    "type": "object",
                    "required": ["ticket_id", "owner_role", "summary"],
                    "properties": {
                        "ticket_id": {"type": "string"},
                        "owner_role": {"type": "string"},
                        "summary": {"type": "string"},
                    },
                },
            },
        },
    }


def _maker_checker_verdict_schema_body() -> dict[str, Any]:
    return {
        "type": "object",
        "required": ["summary", "review_status", "findings"],
        "properties": {
            "summary": {"type": "string"},
            "review_status": {
                "type": "string",
                "enum": [
                    "APPROVED",
                    "APPROVED_WITH_NOTES",
                    "CHANGES_REQUIRED",
                    "ESCALATED",
                ],
            },
            "findings": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": [
                        "finding_id",
                        "severity",
                        "category",
                        "headline",
                        "summary",
                        "required_action",
                        "blocking",
                    ],
                    "properties": {
                        "finding_id": {"type": "string"},
                        "severity": {"type": "string"},
                        "category": {"type": "string"},
                        "headline": {"type": "string"},
                        "summary": {"type": "string"},
                        "required_action": {"type": "string"},
                        "blocking": {"type": "boolean"},
                    },
                },
            },
        },
    }


def _validate_ui_milestone_review_payload(payload: dict[str, Any]) -> None:
    if not isinstance(payload, dict):
        raise ValueError("Result payload must be an object.")

    summary = payload.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        raise ValueError("Result payload.summary must be a non-empty string.")

    options = payload.get("options")
    if not isinstance(options, list) or not options:
        raise ValueError("Result payload.options must be a non-empty array.")

    option_ids: set[str] = set()
    for option in options:
        if not isinstance(option, dict):
            raise ValueError("Each result payload option must be an object.")
        option_id = option.get("option_id")
        label = option.get("label")
        option_summary = option.get("summary")
        if not isinstance(option_id, str) or not option_id:
            raise ValueError("Each result payload option requires option_id.")
        if not isinstance(label, str) or not label:
            raise ValueError("Each result payload option requires label.")
        if not isinstance(option_summary, str) or not option_summary:
            raise ValueError("Each result payload option requires summary.")
        option_ids.add(option_id)

    recommended_option_id = payload.get("recommended_option_id")
    if not isinstance(recommended_option_id, str) or recommended_option_id not in option_ids:
        raise ValueError(
            "Result payload.recommended_option_id must match one of the provided options."
        )


def _validate_consensus_document_payload(payload: dict[str, Any]) -> None:
    if not isinstance(payload, dict):
        raise ValueError("Result payload must be an object.")

    topic = payload.get("topic")
    if not isinstance(topic, str) or not topic.strip():
        raise ValueError("Consensus document payload.topic must be a non-empty string.")

    participants = payload.get("participants")
    if not isinstance(participants, list) or not participants or not all(
        isinstance(item, str) and item for item in participants
    ):
        raise ValueError("Consensus document payload.participants must be a non-empty array.")

    followup_tickets = payload.get("followup_tickets")
    if not isinstance(followup_tickets, list) or not followup_tickets:
        raise ValueError("Consensus document payload.followup_tickets must be a non-empty array.")

    for item in followup_tickets:
        if not isinstance(item, dict):
            raise ValueError("Each consensus followup ticket must be an object.")
        ticket_id = item.get("ticket_id")
        owner_role = item.get("owner_role")
        summary = item.get("summary")
        if not isinstance(ticket_id, str) or not ticket_id:
            raise ValueError("Each consensus followup ticket requires ticket_id.")
        if not isinstance(owner_role, str) or not owner_role:
            raise ValueError("Each consensus followup ticket requires owner_role.")
        if not isinstance(summary, str) or not summary:
            raise ValueError("Each consensus followup ticket requires summary.")


def _validate_maker_checker_verdict_payload(payload: dict[str, Any]) -> None:
    if not isinstance(payload, dict):
        raise ValueError("Result payload must be an object.")

    summary = payload.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        raise ValueError("Maker-checker verdict payload.summary must be a non-empty string.")

    review_status = payload.get("review_status")
    supported_statuses = {
        "APPROVED",
        "APPROVED_WITH_NOTES",
        "CHANGES_REQUIRED",
        "ESCALATED",
    }
    if not isinstance(review_status, str) or review_status not in supported_statuses:
        raise ValueError(
            "Maker-checker verdict payload.review_status must be one of "
            "APPROVED, APPROVED_WITH_NOTES, CHANGES_REQUIRED, ESCALATED."
        )

    findings = payload.get("findings")
    if not isinstance(findings, list):
        raise ValueError("Maker-checker verdict payload.findings must be an array.")

    has_blocking_finding = False
    for finding in findings:
        if not isinstance(finding, dict):
            raise ValueError("Each maker-checker finding must be an object.")
        finding_id = finding.get("finding_id")
        severity = finding.get("severity")
        category = finding.get("category")
        headline = finding.get("headline")
        finding_summary = finding.get("summary")
        required_action = finding.get("required_action")
        blocking = finding.get("blocking")
        if not isinstance(finding_id, str) or not finding_id:
            raise ValueError("Each maker-checker finding requires finding_id.")
        if not isinstance(severity, str) or not severity:
            raise ValueError("Each maker-checker finding requires severity.")
        if not isinstance(category, str) or not category:
            raise ValueError("Each maker-checker finding requires category.")
        if not isinstance(headline, str) or not headline:
            raise ValueError("Each maker-checker finding requires headline.")
        if not isinstance(finding_summary, str) or not finding_summary:
            raise ValueError("Each maker-checker finding requires summary.")
        if not isinstance(required_action, str) or not required_action:
            raise ValueError("Each maker-checker finding requires required_action.")
        if not isinstance(blocking, bool):
            raise ValueError("Each maker-checker finding requires boolean blocking.")
        has_blocking_finding = has_blocking_finding or blocking

    if review_status == "CHANGES_REQUIRED" and not has_blocking_finding:
        raise ValueError(
            "Maker-checker CHANGES_REQUIRED verdict must include at least one blocking finding."
        )


OUTPUT_SCHEMA_REGISTRY: dict[tuple[str, int], dict[str, Any]] = {
    (UI_MILESTONE_REVIEW_SCHEMA_REF, UI_MILESTONE_REVIEW_SCHEMA_VERSION): {
        "body": _ui_milestone_review_schema_body,
        "validator": _validate_ui_milestone_review_payload,
    },
    (CONSENSUS_DOCUMENT_SCHEMA_REF, CONSENSUS_DOCUMENT_SCHEMA_VERSION): {
        "body": _consensus_document_schema_body,
        "validator": _validate_consensus_document_payload,
    },
    (MAKER_CHECKER_VERDICT_SCHEMA_REF, MAKER_CHECKER_VERDICT_SCHEMA_VERSION): {
        "body": _maker_checker_verdict_schema_body,
        "validator": _validate_maker_checker_verdict_payload,
    },
}


def get_output_schema_body(schema_ref: str, schema_version: int) -> dict[str, Any]:
    registry_entry = OUTPUT_SCHEMA_REGISTRY.get((schema_ref, schema_version))
    if registry_entry is not None:
        return registry_entry["body"]()
    return {
        "type": "object",
        "unsupported_schema": schema_id(schema_ref, schema_version),
    }


def validate_output_payload(
    *,
    schema_ref: str,
    schema_version: int,
    submitted_schema_version: str,
    payload: dict[str, Any],
) -> None:
    expected_schema_id = schema_id(schema_ref, schema_version)
    if submitted_schema_version != expected_schema_id:
        raise ValueError(
            f"Expected schema_version {expected_schema_id}, got {submitted_schema_version}."
        )

    registry_entry = OUTPUT_SCHEMA_REGISTRY.get((schema_ref, schema_version))
    if registry_entry is None:
        raise ValueError(f"Unsupported output schema: {schema_ref}@{schema_version}")
    registry_entry["validator"](payload)
