from __future__ import annotations

from typing import Any


UI_MILESTONE_REVIEW_SCHEMA_REF = "ui_milestone_review"
UI_MILESTONE_REVIEW_SCHEMA_VERSION = 1
UI_MILESTONE_REVIEW_SCHEMA_ID = (
    f"{UI_MILESTONE_REVIEW_SCHEMA_REF}_v{UI_MILESTONE_REVIEW_SCHEMA_VERSION}"
)


def schema_id(schema_ref: str, schema_version: int) -> str:
    return f"{schema_ref}_v{schema_version}"


def get_output_schema_body(schema_ref: str, schema_version: int) -> dict[str, Any]:
    if (
        schema_ref == UI_MILESTONE_REVIEW_SCHEMA_REF
        and schema_version == UI_MILESTONE_REVIEW_SCHEMA_VERSION
    ):
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

    if schema_ref != UI_MILESTONE_REVIEW_SCHEMA_REF or schema_version != UI_MILESTONE_REVIEW_SCHEMA_VERSION:
        raise ValueError(f"Unsupported output schema: {schema_ref}@{schema_version}")

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
