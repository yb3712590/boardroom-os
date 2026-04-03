from __future__ import annotations

from collections.abc import Callable
from typing import Any

from app.contracts.commands import DeliveryStage
from app.contracts.ceo_actions import CEOActionBatch


UI_MILESTONE_REVIEW_SCHEMA_REF = "ui_milestone_review"
UI_MILESTONE_REVIEW_SCHEMA_VERSION = 1
UI_MILESTONE_REVIEW_SCHEMA_ID = (
    f"{UI_MILESTONE_REVIEW_SCHEMA_REF}_v{UI_MILESTONE_REVIEW_SCHEMA_VERSION}"
)
CONSENSUS_DOCUMENT_SCHEMA_REF = "consensus_document"
CONSENSUS_DOCUMENT_SCHEMA_VERSION = 1
IMPLEMENTATION_BUNDLE_SCHEMA_REF = "implementation_bundle"
IMPLEMENTATION_BUNDLE_SCHEMA_VERSION = 1
DELIVERY_CHECK_REPORT_SCHEMA_REF = "delivery_check_report"
DELIVERY_CHECK_REPORT_SCHEMA_VERSION = 1
DELIVERY_CLOSEOUT_PACKAGE_SCHEMA_REF = "delivery_closeout_package"
DELIVERY_CLOSEOUT_PACKAGE_SCHEMA_VERSION = 1
MAKER_CHECKER_VERDICT_SCHEMA_REF = "maker_checker_verdict"
MAKER_CHECKER_VERDICT_SCHEMA_VERSION = 1
CEO_ACTION_BATCH_SCHEMA_REF = "ceo_action_batch"
CEO_ACTION_BATCH_SCHEMA_VERSION = 1

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
                        "delivery_stage": {
                            "type": "string",
                            "enum": [stage.value for stage in DeliveryStage],
                        },
                    },
                },
            },
        },
    }


def _implementation_bundle_schema_body() -> dict[str, Any]:
    return {
        "type": "object",
        "required": ["summary", "deliverable_artifact_refs"],
        "properties": {
            "summary": {"type": "string"},
            "deliverable_artifact_refs": {
                "type": "array",
                "minItems": 1,
                "items": {"type": "string"},
            },
            "implementation_notes": {
                "type": "array",
                "items": {"type": "string"},
            },
        },
    }


def _delivery_check_report_schema_body() -> dict[str, Any]:
    return {
        "type": "object",
        "required": ["summary", "status", "findings"],
        "properties": {
            "summary": {"type": "string"},
            "status": {
                "type": "string",
                "enum": ["PASS", "PASS_WITH_NOTES", "FAIL"],
            },
            "findings": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["finding_id", "summary", "blocking"],
                    "properties": {
                        "finding_id": {"type": "string"},
                        "summary": {"type": "string"},
                        "blocking": {"type": "boolean"},
                    },
                },
            },
        },
    }


def _delivery_closeout_package_schema_body() -> dict[str, Any]:
    return {
        "type": "object",
        "required": ["summary", "final_artifact_refs", "handoff_notes"],
        "properties": {
            "summary": {"type": "string"},
            "final_artifact_refs": {
                "type": "array",
                "minItems": 1,
                "items": {"type": "string"},
            },
            "handoff_notes": {
                "type": "array",
                "items": {"type": "string"},
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


def _ceo_action_batch_schema_body() -> dict[str, Any]:
    return {
        "type": "object",
        "required": ["summary", "actions"],
        "properties": {
            "summary": {"type": "string"},
            "actions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["action_type", "payload"],
                    "properties": {
                        "action_type": {"type": "string"},
                        "payload": {"type": "object"},
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
        delivery_stage = item.get("delivery_stage")
        if not isinstance(ticket_id, str) or not ticket_id:
            raise ValueError("Each consensus followup ticket requires ticket_id.")
        if not isinstance(owner_role, str) or not owner_role:
            raise ValueError("Each consensus followup ticket requires owner_role.")
        if not isinstance(summary, str) or not summary:
            raise ValueError("Each consensus followup ticket requires summary.")
        if delivery_stage is not None:
            if not isinstance(delivery_stage, str) or delivery_stage not in {
                DeliveryStage.BUILD.value,
                DeliveryStage.CHECK.value,
                DeliveryStage.REVIEW.value,
            }:
                raise ValueError(
                    "Each consensus followup ticket delivery_stage must be one of BUILD, CHECK, REVIEW."
                )


def _validate_implementation_bundle_payload(payload: dict[str, Any]) -> None:
    if not isinstance(payload, dict):
        raise ValueError("Result payload must be an object.")

    summary = payload.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        raise ValueError("Implementation bundle payload.summary must be a non-empty string.")

    deliverable_artifact_refs = payload.get("deliverable_artifact_refs")
    if not isinstance(deliverable_artifact_refs, list) or not deliverable_artifact_refs or not all(
        isinstance(item, str) and item for item in deliverable_artifact_refs
    ):
        raise ValueError(
            "Implementation bundle payload.deliverable_artifact_refs must be a non-empty array."
        )

    implementation_notes = payload.get("implementation_notes")
    if implementation_notes is not None and (
        not isinstance(implementation_notes, list)
        or not all(isinstance(item, str) and item for item in implementation_notes)
    ):
        raise ValueError("Implementation bundle payload.implementation_notes must be an array of strings.")


def _validate_delivery_check_report_payload(payload: dict[str, Any]) -> None:
    if not isinstance(payload, dict):
        raise ValueError("Result payload must be an object.")

    summary = payload.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        raise ValueError("Delivery check report payload.summary must be a non-empty string.")

    status = payload.get("status")
    if not isinstance(status, str) or status not in {"PASS", "PASS_WITH_NOTES", "FAIL"}:
        raise ValueError("Delivery check report payload.status must be PASS, PASS_WITH_NOTES, or FAIL.")

    findings = payload.get("findings")
    if not isinstance(findings, list):
        raise ValueError("Delivery check report payload.findings must be an array.")
    for finding in findings:
        if not isinstance(finding, dict):
            raise ValueError("Each delivery check finding must be an object.")
        if not isinstance(finding.get("finding_id"), str) or not finding.get("finding_id"):
            raise ValueError("Each delivery check finding requires finding_id.")
        if not isinstance(finding.get("summary"), str) or not finding.get("summary"):
            raise ValueError("Each delivery check finding requires summary.")
        if not isinstance(finding.get("blocking"), bool):
            raise ValueError("Each delivery check finding requires boolean blocking.")


def _validate_delivery_closeout_package_payload(payload: dict[str, Any]) -> None:
    if not isinstance(payload, dict):
        raise ValueError("Result payload must be an object.")

    summary = payload.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        raise ValueError("Delivery closeout package payload.summary must be a non-empty string.")

    final_artifact_refs = payload.get("final_artifact_refs")
    if not isinstance(final_artifact_refs, list) or not final_artifact_refs or not all(
        isinstance(item, str) and item for item in final_artifact_refs
    ):
        raise ValueError(
            "Delivery closeout package payload.final_artifact_refs must be a non-empty array."
        )

    handoff_notes = payload.get("handoff_notes")
    if not isinstance(handoff_notes, list) or not all(
        isinstance(item, str) and item.strip() for item in handoff_notes
    ):
        raise ValueError("Delivery closeout package payload.handoff_notes must be an array of strings.")


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


def _validate_ceo_action_batch_payload(payload: dict[str, Any]) -> None:
    CEOActionBatch.model_validate(payload)


OUTPUT_SCHEMA_REGISTRY: dict[tuple[str, int], dict[str, Any]] = {
    (UI_MILESTONE_REVIEW_SCHEMA_REF, UI_MILESTONE_REVIEW_SCHEMA_VERSION): {
        "body": _ui_milestone_review_schema_body,
        "validator": _validate_ui_milestone_review_payload,
    },
    (CONSENSUS_DOCUMENT_SCHEMA_REF, CONSENSUS_DOCUMENT_SCHEMA_VERSION): {
        "body": _consensus_document_schema_body,
        "validator": _validate_consensus_document_payload,
    },
    (IMPLEMENTATION_BUNDLE_SCHEMA_REF, IMPLEMENTATION_BUNDLE_SCHEMA_VERSION): {
        "body": _implementation_bundle_schema_body,
        "validator": _validate_implementation_bundle_payload,
    },
    (DELIVERY_CHECK_REPORT_SCHEMA_REF, DELIVERY_CHECK_REPORT_SCHEMA_VERSION): {
        "body": _delivery_check_report_schema_body,
        "validator": _validate_delivery_check_report_payload,
    },
    (DELIVERY_CLOSEOUT_PACKAGE_SCHEMA_REF, DELIVERY_CLOSEOUT_PACKAGE_SCHEMA_VERSION): {
        "body": _delivery_closeout_package_schema_body,
        "validator": _validate_delivery_closeout_package_payload,
    },
    (MAKER_CHECKER_VERDICT_SCHEMA_REF, MAKER_CHECKER_VERDICT_SCHEMA_VERSION): {
        "body": _maker_checker_verdict_schema_body,
        "validator": _validate_maker_checker_verdict_payload,
    },
    (CEO_ACTION_BATCH_SCHEMA_REF, CEO_ACTION_BATCH_SCHEMA_VERSION): {
        "body": _ceo_action_batch_schema_body,
        "validator": _validate_ceo_action_batch_payload,
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
