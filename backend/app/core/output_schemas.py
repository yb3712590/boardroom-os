from __future__ import annotations

from collections.abc import Callable
import re
from typing import Any

from app.contracts.advisory import GraphPatchProposal
from app.contracts.commands import DeliveryStage
from app.contracts.ceo_actions import CEOActionBatch


UI_MILESTONE_REVIEW_SCHEMA_REF = "ui_milestone_review"
UI_MILESTONE_REVIEW_SCHEMA_VERSION = 1
UI_MILESTONE_REVIEW_SCHEMA_ID = (
    f"{UI_MILESTONE_REVIEW_SCHEMA_REF}_v{UI_MILESTONE_REVIEW_SCHEMA_VERSION}"
)
CONSENSUS_DOCUMENT_SCHEMA_REF = "consensus_document"
CONSENSUS_DOCUMENT_SCHEMA_VERSION = 1
ARCHITECTURE_BRIEF_SCHEMA_REF = "architecture_brief"
ARCHITECTURE_BRIEF_SCHEMA_VERSION = 1
TECHNOLOGY_DECISION_SCHEMA_REF = "technology_decision"
TECHNOLOGY_DECISION_SCHEMA_VERSION = 1
MILESTONE_PLAN_SCHEMA_REF = "milestone_plan"
MILESTONE_PLAN_SCHEMA_VERSION = 1
DETAILED_DESIGN_SCHEMA_REF = "detailed_design"
DETAILED_DESIGN_SCHEMA_VERSION = 1
BACKLOG_RECOMMENDATION_SCHEMA_REF = "backlog_recommendation"
BACKLOG_RECOMMENDATION_SCHEMA_VERSION = 1
SOURCE_CODE_DELIVERY_SCHEMA_REF = "source_code_delivery"
SOURCE_CODE_DELIVERY_SCHEMA_VERSION = 1
DELIVERY_CHECK_REPORT_SCHEMA_REF = "delivery_check_report"
DELIVERY_CHECK_REPORT_SCHEMA_VERSION = 1
DELIVERY_CLOSEOUT_PACKAGE_SCHEMA_REF = "delivery_closeout_package"
DELIVERY_CLOSEOUT_PACKAGE_SCHEMA_VERSION = 1
MAKER_CHECKER_VERDICT_SCHEMA_REF = "maker_checker_verdict"
MAKER_CHECKER_VERDICT_SCHEMA_VERSION = 1
CEO_ACTION_BATCH_SCHEMA_REF = "ceo_action_batch"
CEO_ACTION_BATCH_SCHEMA_VERSION = 1
GRAPH_PATCH_PROPOSAL_SCHEMA_REF = "graph_patch_proposal"
GRAPH_PATCH_PROPOSAL_SCHEMA_VERSION = 2
DOCUMENTATION_UPDATE_STATUSES = {"UPDATED", "NO_CHANGE_REQUIRED", "FOLLOW_UP_REQUIRED"}
GOVERNANCE_DOCUMENT_SCHEMA_REFS = (
    ARCHITECTURE_BRIEF_SCHEMA_REF,
    TECHNOLOGY_DECISION_SCHEMA_REF,
    MILESTONE_PLAN_SCHEMA_REF,
    DETAILED_DESIGN_SCHEMA_REF,
    BACKLOG_RECOMMENDATION_SCHEMA_REF,
)
_BACKLOG_RECOMMENDATION_TARGET_ROLES = (
    "frontend_engineer",
    "frontend_engineer_primary",
    "backend_engineer",
    "backend_engineer_primary",
    "database_engineer",
    "database_engineer_primary",
    "platform_sre",
    "platform_sre_primary",
    "checker",
    "checker_primary",
    "architect",
    "architect_primary",
    "governance_architect",
    "cto",
    "cto_primary",
    "governance_cto",
)

OutputSchemaValidator = Callable[[dict[str, Any]], None]
_MISSING = object()
_SOURCE_CODE_PLACEHOLDER_NAME_RE = re.compile(r"^source(?:-\d+)?\.(?:ts|tsx|js|jsx|py|sql|sh|txt)$", re.IGNORECASE)
_SOURCE_CODE_PLACEHOLDER_CONTENT_PATTERNS = (
    "runtimeSourceDelivery = true",
    "generated for ",
)


def build_backlog_recommendation_artifact_ref(ticket_id: str) -> str:
    return f"art://runtime/{ticket_id}/{BACKLOG_RECOMMENDATION_SCHEMA_REF}.json"


def build_backlog_recommendation_artifact_path(ticket_id: str) -> str:
    return f"reports/governance/{ticket_id}/{BACKLOG_RECOMMENDATION_SCHEMA_REF}.json"


class OutputSchemaValidationError(ValueError):
    def __init__(
        self,
        *,
        field_path: str,
        expected: str,
        actual: str,
        message: str,
    ) -> None:
        super().__init__(message)
        self.field_path = field_path
        self.expected = expected
        self.actual = actual


def _describe_actual(value: Any) -> str:
    if value is _MISSING:
        return "missing"
    if value is None:
        return "null"
    if isinstance(value, bool):
        return f"boolean({str(value).lower()})"
    if isinstance(value, str):
        return "empty string" if not value.strip() else "string"
    if isinstance(value, list):
        return "empty array" if not value else f"array(len={len(value)})"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


def _raise_schema_validation_error(
    *,
    field_path: str,
    expected: str,
    actual_value: Any,
    message: str,
) -> None:
    raise OutputSchemaValidationError(
        field_path=field_path,
        expected=expected,
        actual=_describe_actual(actual_value),
        message=message,
    )


def _require_object(payload: Any, *, field_path: str = "payload", label: str = "Result payload") -> dict[str, Any]:
    if not isinstance(payload, dict):
        _raise_schema_validation_error(
            field_path=field_path,
            expected="object",
            actual_value=payload,
            message=f"{label} must be an object.",
        )
    return payload


def _require_non_empty_string(payload: dict[str, Any], key: str, *, label: str) -> str:
    value = payload.get(key, _MISSING)
    if not isinstance(value, str) or not value.strip():
        _raise_schema_validation_error(
            field_path=key,
            expected="non-empty string",
            actual_value=value,
            message=f"{label} must be a non-empty string.",
        )
    return value


def _require_array(
    payload: dict[str, Any],
    key: str,
    *,
    label: str,
    non_empty: bool = False,
) -> list[Any]:
    value = payload.get(key, _MISSING)
    if not isinstance(value, list) or (non_empty and not value):
        _raise_schema_validation_error(
            field_path=key,
            expected="non-empty array" if non_empty else "array",
            actual_value=value,
            message=f"{label} must be a {'non-empty array' if non_empty else 'array'}.",
        )
    return value


def _require_string_array(
    payload: dict[str, Any],
    key: str,
    *,
    label: str,
    non_empty: bool = False,
) -> list[str]:
    values = _require_array(payload, key, label=label, non_empty=non_empty)
    for index, item in enumerate(values):
        if not isinstance(item, str) or not item.strip():
            _raise_schema_validation_error(
                field_path=f"{key}[{index}]",
                expected="non-empty string",
                actual_value=item,
                message=f"{label} items must be non-empty strings.",
            )
    return values


def _require_enum(payload: dict[str, Any], key: str, *, expected_values: set[str], label: str) -> str:
    value = payload.get(key, _MISSING)
    if not isinstance(value, str) or value not in expected_values:
        _raise_schema_validation_error(
            field_path=key,
            expected=f"one of {', '.join(sorted(expected_values))}",
            actual_value=value,
            message=f"{label} must be {', '.join(sorted(expected_values))}.",
        )
    return value


def _validate_documentation_updates(
    payload: dict[str, Any],
    *,
    key: str = "documentation_updates",
    label: str = "Delivery closeout package payload.documentation_updates",
) -> None:
    value = payload.get(key, _MISSING)
    if value is _MISSING:
        return
    if not isinstance(value, list):
        _raise_schema_validation_error(
            field_path=key,
            expected="array",
            actual_value=value,
            message=f"{label} must be an array.",
        )
    for index, item in enumerate(value):
        field_prefix = f"{key}[{index}]"
        if not isinstance(item, dict):
            _raise_schema_validation_error(
                field_path=field_prefix,
                expected="object",
                actual_value=item,
                message=f"{label} items must be objects.",
            )

        doc_ref = item.get("doc_ref", _MISSING)
        if not isinstance(doc_ref, str) or not doc_ref.strip():
            _raise_schema_validation_error(
                field_path=f"{field_prefix}.doc_ref",
                expected="non-empty string",
                actual_value=doc_ref,
                message="Each documentation update requires a non-empty doc_ref.",
            )

        status = item.get("status", _MISSING)
        if not isinstance(status, str) or status not in DOCUMENTATION_UPDATE_STATUSES:
            _raise_schema_validation_error(
                field_path=f"{field_prefix}.status",
                expected=f"one of {', '.join(sorted(DOCUMENTATION_UPDATE_STATUSES))}",
                actual_value=status,
                message="Each documentation update status must be one of "
                f"{', '.join(sorted(DOCUMENTATION_UPDATE_STATUSES))}.",
            )

        summary = item.get("summary", _MISSING)
        if not isinstance(summary, str) or not summary.strip():
            _raise_schema_validation_error(
                field_path=f"{field_prefix}.summary",
                expected="non-empty string",
                actual_value=summary,
                message="Each documentation update requires a non-empty summary.",
            )


def _require_non_negative_int(value: Any, *, field_path: str, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        _raise_schema_validation_error(
            field_path=field_path,
            expected="non-negative integer",
            actual_value=value,
            message=f"{label} must be a non-negative integer.",
        )
    return value


def _require_positive_number(value: Any, *, field_path: str, label: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool) or value <= 0:
        _raise_schema_validation_error(
            field_path=field_path,
            expected="positive number",
            actual_value=value,
            message=f"{label} must be a positive number.",
        )
    return float(value)


def _looks_like_placeholder_source_file(*, path: str, content: str) -> bool:
    normalized_path = path.replace("\\", "/").strip()
    filename = normalized_path.rsplit("/", 1)[-1]
    if _SOURCE_CODE_PLACEHOLDER_NAME_RE.match(filename):
        return True
    return any(marker in content for marker in _SOURCE_CODE_PLACEHOLDER_CONTENT_PATTERNS)


def _validate_source_code_delivery_source_files(
    payload: dict[str, Any],
    *,
    source_file_refs: list[str],
) -> list[dict[str, Any]]:
    source_files = _require_array(
        payload,
        "source_files",
        label="Source code delivery payload.source_files",
        non_empty=True,
    )
    normalized_source_files: list[dict[str, Any]] = []
    seen_artifact_refs: set[str] = set()
    for index, item in enumerate(source_files):
        field_prefix = f"source_files[{index}]"
        if not isinstance(item, dict):
            _raise_schema_validation_error(
                field_path=field_prefix,
                expected="object",
                actual_value=item,
                message="Each source_files item must be an object.",
            )
        artifact_ref = item.get("artifact_ref", _MISSING)
        if not isinstance(artifact_ref, str) or not artifact_ref.strip():
            _raise_schema_validation_error(
                field_path=f"{field_prefix}.artifact_ref",
                expected="non-empty string",
                actual_value=artifact_ref,
                message="Each source_files item requires artifact_ref.",
            )
        normalized_artifact_ref = artifact_ref.strip()
        if normalized_artifact_ref in seen_artifact_refs:
            _raise_schema_validation_error(
                field_path=f"{field_prefix}.artifact_ref",
                expected="unique artifact_ref",
                actual_value=artifact_ref,
                message="source_files artifact_ref values must be unique.",
            )
        seen_artifact_refs.add(normalized_artifact_ref)

        path = item.get("path", _MISSING)
        if not isinstance(path, str) or not path.strip():
            _raise_schema_validation_error(
                field_path=f"{field_prefix}.path",
                expected="non-empty string",
                actual_value=path,
                message="Each source_files item requires path.",
            )
        content = item.get("content", _MISSING)
        if not isinstance(content, str) or not content.strip():
            _raise_schema_validation_error(
                field_path=f"{field_prefix}.content",
                expected="non-empty string",
                actual_value=content,
                message="Each source_files item requires content.",
            )
        normalized_content = content.strip()
        if len(normalized_content) < 24 or _looks_like_placeholder_source_file(path=path, content=content):
            _raise_schema_validation_error(
                field_path=f"{field_prefix}.content",
                expected="non-placeholder source content",
                actual_value=content,
                message="source_files content must be non-placeholder source code.",
            )
        normalized_source_files.append(
            {
                "artifact_ref": normalized_artifact_ref,
                "path": path.strip(),
                "content": content,
            }
        )

    normalized_source_file_refs = [item.strip() for item in source_file_refs]
    if normalized_source_file_refs != [item["artifact_ref"] for item in normalized_source_files]:
        _raise_schema_validation_error(
            field_path="source_file_refs",
            expected="same artifact_ref order as source_files",
            actual_value=source_file_refs,
            message="source_file_refs must match source_files artifact_ref values in order.",
        )
    return normalized_source_files


def _validate_source_code_delivery_verification_runs(payload: dict[str, Any]) -> list[dict[str, Any]]:
    verification_runs = _require_array(
        payload,
        "verification_runs",
        label="Source code delivery payload.verification_runs",
        non_empty=True,
    )
    normalized_runs: list[dict[str, Any]] = []
    seen_artifact_refs: set[str] = set()
    for index, item in enumerate(verification_runs):
        field_prefix = f"verification_runs[{index}]"
        if not isinstance(item, dict):
            _raise_schema_validation_error(
                field_path=field_prefix,
                expected="object",
                actual_value=item,
                message="Each verification_runs item must be an object.",
            )
        artifact_ref = item.get("artifact_ref", _MISSING)
        if not isinstance(artifact_ref, str) or not artifact_ref.strip():
            _raise_schema_validation_error(
                field_path=f"{field_prefix}.artifact_ref",
                expected="non-empty string",
                actual_value=artifact_ref,
                message="Each verification_runs item requires artifact_ref.",
            )
        normalized_artifact_ref = artifact_ref.strip()
        if normalized_artifact_ref in seen_artifact_refs:
            _raise_schema_validation_error(
                field_path=f"{field_prefix}.artifact_ref",
                expected="unique artifact_ref",
                actual_value=artifact_ref,
                message="verification_runs artifact_ref values must be unique.",
            )
        seen_artifact_refs.add(normalized_artifact_ref)
        for key in ("path", "runner", "command", "status", "stdout", "stderr"):
            value = item.get(key, _MISSING)
            if not isinstance(value, str):
                _raise_schema_validation_error(
                    field_path=f"{field_prefix}.{key}",
                    expected="string",
                    actual_value=value,
                    message=f"Each verification_runs item requires string {key}.",
                )
        if not str(item.get("path") or "").strip():
            _raise_schema_validation_error(
                field_path=f"{field_prefix}.path",
                expected="non-empty string",
                actual_value=item.get("path", _MISSING),
                message="Each verification_runs item requires path.",
            )
        if not str(item.get("runner") or "").strip():
            _raise_schema_validation_error(
                field_path=f"{field_prefix}.runner",
                expected="non-empty string",
                actual_value=item.get("runner", _MISSING),
                message="Each verification_runs item requires runner.",
            )
        if not str(item.get("command") or "").strip():
            _raise_schema_validation_error(
                field_path=f"{field_prefix}.command",
                expected="non-empty string",
                actual_value=item.get("command", _MISSING),
                message="Each verification_runs item requires command.",
            )
        if str(item.get("status") or "").strip() not in {"passed", "failed"}:
            _raise_schema_validation_error(
                field_path=f"{field_prefix}.status",
                expected="passed or failed",
                actual_value=item.get("status", _MISSING),
                message="Each verification_runs item status must be passed or failed.",
            )
        _require_non_negative_int(
            item.get("exit_code", _MISSING),
            field_path=f"{field_prefix}.exit_code",
            label="Each verification_runs item exit_code",
        )
        _require_positive_number(
            item.get("duration_sec", _MISSING),
            field_path=f"{field_prefix}.duration_sec",
            label="Each verification_runs item duration_sec",
        )
        discovered_count = _require_non_negative_int(
            item.get("discovered_count", _MISSING),
            field_path=f"{field_prefix}.discovered_count",
            label="Each verification_runs item discovered_count",
        )
        passed_count = _require_non_negative_int(
            item.get("passed_count", _MISSING),
            field_path=f"{field_prefix}.passed_count",
            label="Each verification_runs item passed_count",
        )
        failed_count = _require_non_negative_int(
            item.get("failed_count", _MISSING),
            field_path=f"{field_prefix}.failed_count",
            label="Each verification_runs item failed_count",
        )
        _require_non_negative_int(
            item.get("skipped_count", _MISSING),
            field_path=f"{field_prefix}.skipped_count",
            label="Each verification_runs item skipped_count",
        )
        failures = item.get("failures", _MISSING)
        if not isinstance(failures, list):
            _raise_schema_validation_error(
                field_path=f"{field_prefix}.failures",
                expected="array",
                actual_value=failures,
                message="Each verification_runs item requires failures array.",
            )
        stdout = str(item.get("stdout") or "")
        if not stdout.strip():
            _raise_schema_validation_error(
                field_path=f"{field_prefix}.stdout",
                expected="non-empty string",
                actual_value=item.get("stdout", _MISSING),
                message="Each verification_runs item requires raw stdout output.",
            )
        if discovered_count <= 0 or passed_count + failed_count > discovered_count:
            _raise_schema_validation_error(
                field_path=f"{field_prefix}.discovered_count",
                expected="count compatible with pass/fail totals",
                actual_value=item.get("discovered_count", _MISSING),
                message="verification_runs counts must describe at least one discovered test.",
            )
        normalized_runs.append(
            {
                "artifact_ref": normalized_artifact_ref,
                "path": str(item["path"]).strip(),
                "runner": str(item["runner"]).strip(),
                "command": str(item["command"]).strip(),
                "status": str(item["status"]).strip(),
                "exit_code": int(item["exit_code"]),
                "duration_sec": float(item["duration_sec"]),
                "stdout": stdout,
                "stderr": str(item["stderr"]),
                "discovered_count": discovered_count,
                "passed_count": passed_count,
                "failed_count": failed_count,
                "skipped_count": int(item["skipped_count"]),
                "failures": list(failures),
            }
        )
    return normalized_runs


def schema_id(schema_ref: str, schema_version: int) -> str:
    return f"{schema_ref}_v{schema_version}"


def _normalize_openai_strict_schema(schema: object) -> object:
    if isinstance(schema, list):
        return [_normalize_openai_strict_schema(item) for item in schema]
    if not isinstance(schema, dict):
        return schema

    normalized = {
        str(key): _normalize_openai_strict_schema(value)
        for key, value in schema.items()
    }

    if normalized.get("type") == "object":
        properties = normalized.get("properties")
        if not isinstance(properties, dict):
            properties = {}
        normalized["properties"] = properties
        existing_required = normalized.get("required")
        if not isinstance(existing_required, list):
            existing_required = []
        required_keys = []
        seen_required: set[str] = set()
        for key in [*existing_required, *properties.keys()]:
            key_str = str(key)
            if key_str in seen_required:
                continue
            seen_required.add(key_str)
            required_keys.append(key_str)
        normalized["required"] = required_keys
        normalized["additionalProperties"] = False

    return normalized


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
            "decision_record": {
                "type": "object",
                "required": [
                    "format",
                    "context",
                    "decision",
                    "rationale",
                    "consequences",
                    "archived_context_refs",
                ],
                "properties": {
                    "format": {"type": "string", "enum": ["ADR_V1"]},
                    "context": {"type": "string"},
                    "decision": {"type": "string"},
                    "rationale": {
                        "type": "array",
                        "minItems": 1,
                        "items": {"type": "string"},
                    },
                    "consequences": {
                        "type": "array",
                        "minItems": 1,
                        "items": {"type": "string"},
                    },
                    "archived_context_refs": {
                        "type": "array",
                        "minItems": 1,
                        "items": {"type": "string"},
                    },
                },
            },
            "followup_tickets": {
                "type": "array",
                "minItems": 1,
                "items": {
                    "type": "object",
                    "required": ["ticket_id", "task_title", "owner_role", "summary"],
                    "properties": {
                        "ticket_id": {"type": "string"},
                        "task_title": {"type": "string"},
                        "owner_role": {"type": "string"},
                        "summary": {"type": "string"},
                        "delivery_stage": {
                            "type": "string",
                            "enum": [stage.value for stage in DeliveryStage],
                        },
                        "dependency_ticket_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                    },
                },
            },
        },
    }


def _validate_consensus_decision_record(payload: dict[str, Any]) -> None:
    decision_record = payload.get("decision_record", _MISSING)
    if decision_record is _MISSING:
        return

    decision_record = _require_object(
        decision_record,
        field_path="decision_record",
        label="Consensus document payload.decision_record",
    )
    record_format = decision_record.get("format", _MISSING)
    if record_format != "ADR_V1":
        _raise_schema_validation_error(
            field_path="decision_record.format",
            expected="literal 'ADR_V1'",
            actual_value=record_format,
            message="Consensus document payload.decision_record.format must be ADR_V1.",
        )

    for key in ("context", "decision"):
        _require_non_empty_string(
            decision_record,
            key,
            label=f"Consensus document payload.decision_record.{key}",
        )

    for key in ("rationale", "consequences", "archived_context_refs"):
        _require_string_array(
            decision_record,
            key,
            label=f"Consensus document payload.decision_record.{key}",
            non_empty=True,
        )


def _governance_document_schema_body(document_kind_ref: str) -> dict[str, Any]:
    return {
        "type": "object",
        "required": [
            "title",
            "summary",
            "document_kind_ref",
            "decisions",
            "constraints",
            "sections",
        ],
        "properties": {
            "title": {"type": "string"},
            "summary": {"type": "string"},
            "document_kind_ref": {"type": "string", "enum": [document_kind_ref]},
            "linked_document_refs": {
                "type": "array",
                "items": {"type": "string"},
            },
            "linked_artifact_refs": {
                "type": "array",
                "items": {"type": "string"},
            },
            "source_process_asset_refs": {
                "type": "array",
                "items": {"type": "string"},
            },
            "decisions": {
                "type": "array",
                "items": {"type": "string"},
            },
            "constraints": {
                "type": "array",
                "items": {"type": "string"},
            },
            "sections": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["section_id", "label", "summary"],
                    "properties": {
                        "section_id": {"type": "string"},
                        "label": {"type": "string"},
                        "summary": {"type": "string"},
                        "content_markdown": {"type": "string"},
                        "content_json": {"type": "object"},
                    },
                },
            },
            "followup_recommendations": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["recommendation_id", "summary", "target_role"],
                    "properties": {
                        "recommendation_id": {"type": "string"},
                        "summary": {"type": "string"},
                        "target_role": {"type": "string"},
                    },
                },
            },
        },
    }


def _backlog_recommendation_schema_body() -> dict[str, Any]:
    body = _governance_document_schema_body(BACKLOG_RECOMMENDATION_SCHEMA_REF)
    body["required"] = [*body["required"], "implementation_handoff"]
    body["properties"]["implementation_handoff"] = {
        "type": "object",
        "required": ["tickets", "dependency_graph", "recommended_sequence"],
        "properties": {
            "tickets": {
                "type": "array",
                "minItems": 1,
                "items": {
                    "type": "object",
                    "required": ["ticket_id", "name", "summary", "scope", "target_role"],
                    "properties": {
                        "ticket_id": {"type": "string"},
                        "name": {"type": "string"},
                        "summary": {"type": "string"},
                        "scope": {
                            "type": "array",
                            "minItems": 1,
                            "items": {"type": "string"},
                        },
                        "target_role": {
                            "type": "string",
                            "enum": sorted(_BACKLOG_RECOMMENDATION_TARGET_ROLES),
                        },
                    },
                },
            },
            "dependency_graph": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["ticket_id", "depends_on"],
                    "properties": {
                        "ticket_id": {"type": "string"},
                        "depends_on": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                    },
                },
            },
            "recommended_sequence": {
                "type": "array",
                "minItems": 1,
                "items": {"type": "string"},
            },
        },
    }
    return body


def _validate_governance_document_payload(
    payload: dict[str, Any],
    *,
    expected_document_kind_ref: str,
) -> None:
    payload = _require_object(payload)
    _require_non_empty_string(payload, "title", label="Governance document payload.title")
    _require_non_empty_string(payload, "summary", label="Governance document payload.summary")
    document_kind_ref = _require_non_empty_string(
        payload,
        "document_kind_ref",
        label="Governance document payload.document_kind_ref",
    )
    if document_kind_ref != expected_document_kind_ref:
        _raise_schema_validation_error(
            field_path="document_kind_ref",
            expected=f"literal {expected_document_kind_ref}",
            actual_value=document_kind_ref,
            message=(
                "Governance document payload.document_kind_ref must match "
                f"{expected_document_kind_ref}."
            ),
        )

    for key in (
        "linked_document_refs",
        "linked_artifact_refs",
        "source_process_asset_refs",
        "decisions",
        "constraints",
    ):
        value = payload.get(key, _MISSING)
        if value is _MISSING:
            if key in {"decisions", "constraints"}:
                _raise_schema_validation_error(
                    field_path=key,
                    expected="array",
                    actual_value=value,
                    message=f"Governance document payload.{key} must be an array.",
                )
            continue
        _require_string_array(payload, key, label=f"Governance document payload.{key}")

    sections = _require_array(payload, "sections", label="Governance document payload.sections")
    for index, section in enumerate(sections):
        if not isinstance(section, dict):
            _raise_schema_validation_error(
                field_path=f"sections[{index}]",
                expected="object",
                actual_value=section,
                message="Governance document payload.sections items must be objects.",
            )
        for key in ("section_id", "label", "summary"):
            value = section.get(key, _MISSING)
            if not isinstance(value, str) or not value.strip():
                _raise_schema_validation_error(
                    field_path=f"sections[{index}].{key}",
                    expected="non-empty string",
                    actual_value=value,
                    message=f"Governance document payload.sections[{index}].{key} must be a non-empty string.",
                )
        content_markdown = section.get("content_markdown", _MISSING)
        content_json = section.get("content_json", _MISSING)
        has_markdown = isinstance(content_markdown, str) and bool(content_markdown.strip())
        has_json = isinstance(content_json, dict)
        if not has_markdown and not has_json:
            _raise_schema_validation_error(
                field_path=f"sections[{index}]",
                expected="content_markdown or content_json",
                actual_value=section,
                message=(
                    "Governance document payload.sections items must include non-empty "
                    "content_markdown or object content_json."
                ),
            )

    followup_recommendations = payload.get("followup_recommendations", _MISSING)
    if followup_recommendations is _MISSING:
        return
    followup_recommendations = _require_array(
        payload,
        "followup_recommendations",
        label="Governance document payload.followup_recommendations",
    )
    for index, recommendation in enumerate(followup_recommendations):
        if not isinstance(recommendation, dict):
            _raise_schema_validation_error(
                field_path=f"followup_recommendations[{index}]",
                expected="object",
                actual_value=recommendation,
                message="Governance document followup recommendations must be objects.",
            )
        for key in ("recommendation_id", "summary", "target_role"):
            value = recommendation.get(key, _MISSING)
            if not isinstance(value, str) or not value.strip():
                _raise_schema_validation_error(
                    field_path=f"followup_recommendations[{index}].{key}",
                expected="non-empty string",
                actual_value=value,
                message=(
                    "Governance document followup recommendations require "
                    f"{key}."
                ),
            )


def _validate_backlog_recommendation_payload(payload: dict[str, Any]) -> None:
    payload = _require_object(payload)
    _validate_governance_document_payload(
        payload,
        expected_document_kind_ref=BACKLOG_RECOMMENDATION_SCHEMA_REF,
    )

    implementation_handoff = payload.get("implementation_handoff", _MISSING)
    if implementation_handoff is _MISSING:
        _raise_schema_validation_error(
            field_path="implementation_handoff",
            expected="object",
            actual_value=implementation_handoff,
            message="Backlog recommendation payload.implementation_handoff must be an object.",
        )
    implementation_handoff = _require_object(
        implementation_handoff,
        field_path="implementation_handoff",
        label="Backlog recommendation payload.implementation_handoff",
    )

    tickets = _require_array(
        implementation_handoff,
        "tickets",
        label="Backlog recommendation payload.implementation_handoff.tickets",
        non_empty=True,
    )
    ticket_ids: list[str] = []
    ticket_id_set: set[str] = set()
    for index, ticket in enumerate(tickets):
        field_prefix = f"implementation_handoff.tickets[{index}]"
        if not isinstance(ticket, dict):
            _raise_schema_validation_error(
                field_path=field_prefix,
                expected="object",
                actual_value=ticket,
                message="Backlog recommendation implementation_handoff.tickets items must be objects.",
            )

        for key in ("ticket_id", "name", "summary", "target_role"):
            value = ticket.get(key, _MISSING)
            if not isinstance(value, str) or not value.strip():
                _raise_schema_validation_error(
                    field_path=f"{field_prefix}.{key}",
                    expected="non-empty string",
                    actual_value=value,
                    message=f"Backlog recommendation {field_prefix}.{key} must be a non-empty string.",
                )
        ticket_id = str(ticket["ticket_id"]).strip()
        if ticket_id in ticket_id_set:
            _raise_schema_validation_error(
                field_path=f"{field_prefix}.ticket_id",
                expected="unique ticket_id",
                actual_value=ticket_id,
                message="Backlog recommendation implementation_handoff.tickets ticket_id values must be unique.",
            )
        ticket_id_set.add(ticket_id)
        ticket_ids.append(ticket_id)

        scope = ticket.get("scope", _MISSING)
        if not isinstance(scope, list) or not scope:
            _raise_schema_validation_error(
                field_path=f"{field_prefix}.scope",
                expected="non-empty array",
                actual_value=scope,
                message=f"Backlog recommendation {field_prefix}.scope must be a non-empty array.",
            )
        for scope_index, scope_item in enumerate(scope):
            if not isinstance(scope_item, str) or not scope_item.strip():
                _raise_schema_validation_error(
                    field_path=f"{field_prefix}.scope[{scope_index}]",
                    expected="non-empty string",
                    actual_value=scope_item,
                    message=f"Backlog recommendation {field_prefix}.scope items must be non-empty strings.",
                )

        target_role = str(ticket["target_role"]).strip()
        if target_role not in _BACKLOG_RECOMMENDATION_TARGET_ROLES:
            _raise_schema_validation_error(
                field_path=f"{field_prefix}.target_role",
                expected=f"one of {', '.join(sorted(_BACKLOG_RECOMMENDATION_TARGET_ROLES))}",
                actual_value=target_role,
                message="Backlog recommendation implementation_handoff.tickets target_role must be a supported role.",
            )

    dependency_graph = _require_array(
        implementation_handoff,
        "dependency_graph",
        label="Backlog recommendation payload.implementation_handoff.dependency_graph",
    )
    seen_dependency_ticket_ids: set[str] = set()
    for index, dependency in enumerate(dependency_graph):
        field_prefix = f"implementation_handoff.dependency_graph[{index}]"
        if not isinstance(dependency, dict):
            _raise_schema_validation_error(
                field_path=field_prefix,
                expected="object",
                actual_value=dependency,
                message="Backlog recommendation implementation_handoff.dependency_graph items must be objects.",
            )
        ticket_id = dependency.get("ticket_id", _MISSING)
        if not isinstance(ticket_id, str) or not ticket_id.strip():
            _raise_schema_validation_error(
                field_path=f"{field_prefix}.ticket_id",
                expected="non-empty string",
                actual_value=ticket_id,
                message="Backlog recommendation dependency_graph.ticket_id must be a non-empty string.",
            )
        normalized_ticket_id = str(ticket_id).strip()
        if normalized_ticket_id not in ticket_id_set:
            _raise_schema_validation_error(
                field_path=f"{field_prefix}.ticket_id",
                expected="ticket_id declared in implementation_handoff.tickets",
                actual_value=normalized_ticket_id,
                message="Backlog recommendation dependency_graph.ticket_id must reference a declared ticket.",
            )
        if normalized_ticket_id in seen_dependency_ticket_ids:
            _raise_schema_validation_error(
                field_path=f"{field_prefix}.ticket_id",
                expected="unique ticket_id",
                actual_value=normalized_ticket_id,
                message="Backlog recommendation dependency_graph entries must not duplicate ticket_id.",
            )
        seen_dependency_ticket_ids.add(normalized_ticket_id)

        depends_on = dependency.get("depends_on", _MISSING)
        if not isinstance(depends_on, list):
            _raise_schema_validation_error(
                field_path=f"{field_prefix}.depends_on",
                expected="array",
                actual_value=depends_on,
                message="Backlog recommendation dependency_graph.depends_on must be an array.",
            )
        for dependency_index, dependency_ticket_id in enumerate(depends_on):
            if not isinstance(dependency_ticket_id, str) or not dependency_ticket_id.strip():
                _raise_schema_validation_error(
                    field_path=f"{field_prefix}.depends_on[{dependency_index}]",
                    expected="non-empty string",
                    actual_value=dependency_ticket_id,
                    message="Backlog recommendation dependency ids must be non-empty strings.",
                )
            if str(dependency_ticket_id).strip() not in ticket_id_set:
                _raise_schema_validation_error(
                    field_path=f"{field_prefix}.depends_on[{dependency_index}]",
                    expected="ticket_id declared in implementation_handoff.tickets",
                    actual_value=dependency_ticket_id,
                    message="Backlog recommendation dependency ids must reference declared tickets.",
                )

    recommended_sequence = _require_string_array(
        implementation_handoff,
        "recommended_sequence",
        label="Backlog recommendation payload.implementation_handoff.recommended_sequence",
        non_empty=True,
    )
    normalized_sequence = [str(item).strip() for item in recommended_sequence]
    if len(set(normalized_sequence)) != len(normalized_sequence):
        _raise_schema_validation_error(
            field_path="implementation_handoff.recommended_sequence",
            expected="array of unique ticket_id values",
            actual_value=recommended_sequence,
            message="Backlog recommendation implementation_handoff.recommended_sequence must not contain duplicates.",
        )
    if any(ticket_id not in ticket_id_set for ticket_id in normalized_sequence):
        _raise_schema_validation_error(
            field_path="implementation_handoff.recommended_sequence",
            expected="array containing only declared ticket_id values",
            actual_value=recommended_sequence,
            message="Backlog recommendation implementation_handoff.recommended_sequence must contain only declared ticket_id values.",
        )
    if set(normalized_sequence) != ticket_id_set:
        _raise_schema_validation_error(
            field_path="implementation_handoff.recommended_sequence",
            expected="array covering every declared ticket_id exactly once",
            actual_value=recommended_sequence,
            message="Backlog recommendation implementation_handoff.recommended_sequence must cover every declared ticket_id exactly once.",
        )


def _source_code_delivery_schema_body() -> dict[str, Any]:
    return {
        "type": "object",
        "required": ["summary", "source_file_refs", "source_files", "verification_runs"],
        "properties": {
            "summary": {"type": "string"},
            "source_file_refs": {
                "type": "array",
                "minItems": 1,
                "items": {"type": "string"},
            },
            "source_files": {
                "type": "array",
                "minItems": 1,
                "items": {
                    "type": "object",
                    "required": ["artifact_ref", "path", "content"],
                    "properties": {
                        "artifact_ref": {"type": "string"},
                        "path": {"type": "string"},
                        "content": {"type": "string"},
                    },
                },
            },
            "verification_runs": {
                "type": "array",
                "minItems": 1,
                "items": {
                    "type": "object",
                    "required": [
                        "artifact_ref",
                        "path",
                        "runner",
                        "command",
                        "status",
                        "exit_code",
                        "duration_sec",
                        "stdout",
                        "stderr",
                        "discovered_count",
                        "passed_count",
                        "failed_count",
                        "skipped_count",
                        "failures",
                    ],
                    "properties": {
                        "artifact_ref": {"type": "string"},
                        "path": {"type": "string"},
                        "runner": {"type": "string"},
                        "command": {"type": "string"},
                        "status": {"type": "string", "enum": ["passed", "failed"]},
                        "exit_code": {"type": "integer"},
                        "duration_sec": {"type": "number"},
                        "stdout": {"type": "string"},
                        "stderr": {"type": "string"},
                        "discovered_count": {"type": "integer"},
                        "passed_count": {"type": "integer"},
                        "failed_count": {"type": "integer"},
                        "skipped_count": {"type": "integer"},
                        "failures": {"type": "array"},
                    },
                },
            },
            "implementation_notes": {
                "type": "array",
                "items": {"type": "string"},
            },
            "documentation_updates": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["doc_ref", "status", "summary"],
                    "properties": {
                        "doc_ref": {"type": "string"},
                        "status": {
                            "type": "string",
                            "enum": sorted(DOCUMENTATION_UPDATE_STATUSES),
                        },
                        "summary": {"type": "string"},
                    },
                },
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
            "documentation_updates": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["doc_ref", "status", "summary"],
                    "properties": {
                        "doc_ref": {"type": "string"},
                        "status": {
                            "type": "string",
                            "enum": sorted(DOCUMENTATION_UPDATE_STATUSES),
                        },
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
    payload = _require_object(payload)
    _require_non_empty_string(payload, "summary", label="Result payload.summary")
    options = _require_array(payload, "options", label="Result payload.options", non_empty=True)

    option_ids: set[str] = set()
    for index, option in enumerate(options):
        if not isinstance(option, dict):
            _raise_schema_validation_error(
                field_path=f"options[{index}]",
                expected="object",
                actual_value=option,
                message="Each result payload option must be an object.",
            )
        option_id = option.get("option_id")
        label = option.get("label")
        option_summary = option.get("summary")
        if not isinstance(option_id, str) or not option_id:
            _raise_schema_validation_error(
                field_path=f"options[{index}].option_id",
                expected="non-empty string",
                actual_value=option_id if option_id is not None else _MISSING,
                message="Each result payload option requires option_id.",
            )
        if not isinstance(label, str) or not label:
            _raise_schema_validation_error(
                field_path=f"options[{index}].label",
                expected="non-empty string",
                actual_value=label if label is not None else _MISSING,
                message="Each result payload option requires label.",
            )
        if not isinstance(option_summary, str) or not option_summary:
            _raise_schema_validation_error(
                field_path=f"options[{index}].summary",
                expected="non-empty string",
                actual_value=option_summary if option_summary is not None else _MISSING,
                message="Each result payload option requires summary.",
            )
        option_ids.add(option_id)

    recommended_option_id = payload.get("recommended_option_id")
    if not isinstance(recommended_option_id, str) or recommended_option_id not in option_ids:
        _raise_schema_validation_error(
            field_path="recommended_option_id",
            expected="option_id from options[]",
            actual_value=recommended_option_id if recommended_option_id is not None else _MISSING,
            message="Result payload.recommended_option_id must match one of the provided options.",
        )


def _validate_consensus_document_payload(payload: dict[str, Any]) -> None:
    payload = _require_object(payload)
    _require_non_empty_string(payload, "topic", label="Consensus document payload.topic")
    _require_string_array(
        payload,
        "participants",
        label="Consensus document payload.participants",
        non_empty=True,
    )
    _validate_consensus_decision_record(payload)
    followup_tickets = _require_array(
        payload,
        "followup_tickets",
        label="Consensus document payload.followup_tickets",
        non_empty=True,
    )

    for index, item in enumerate(followup_tickets):
        if not isinstance(item, dict):
            _raise_schema_validation_error(
                field_path=f"followup_tickets[{index}]",
                expected="object",
                actual_value=item,
                message="Each consensus followup ticket must be an object.",
            )
        ticket_id = item.get("ticket_id")
        task_title = item.get("task_title")
        owner_role = item.get("owner_role")
        summary = item.get("summary")
        delivery_stage = item.get("delivery_stage")
        if not isinstance(ticket_id, str) or not ticket_id:
            _raise_schema_validation_error(
                field_path=f"followup_tickets[{index}].ticket_id",
                expected="non-empty string",
                actual_value=ticket_id if ticket_id is not None else _MISSING,
                message="Each consensus followup ticket requires ticket_id.",
            )
        if not isinstance(task_title, str) or not task_title:
            _raise_schema_validation_error(
                field_path=f"followup_tickets[{index}].task_title",
                expected="non-empty string",
                actual_value=task_title if task_title is not None else _MISSING,
                message="Each consensus followup ticket requires task_title.",
            )
        if not isinstance(owner_role, str) or not owner_role:
            _raise_schema_validation_error(
                field_path=f"followup_tickets[{index}].owner_role",
                expected="non-empty string",
                actual_value=owner_role if owner_role is not None else _MISSING,
                message="Each consensus followup ticket requires owner_role.",
            )
        if not isinstance(summary, str) or not summary:
            _raise_schema_validation_error(
                field_path=f"followup_tickets[{index}].summary",
                expected="non-empty string",
                actual_value=summary if summary is not None else _MISSING,
                message="Each consensus followup ticket requires summary.",
            )
        dependency_ticket_ids = item.get("dependency_ticket_ids", [])
        if not isinstance(dependency_ticket_ids, list):
            _raise_schema_validation_error(
                field_path=f"followup_tickets[{index}].dependency_ticket_ids",
                expected="array",
                actual_value=dependency_ticket_ids,
                message="Each consensus followup ticket dependency_ticket_ids must be an array.",
            )
        for dependency_index, dependency_ticket_id in enumerate(dependency_ticket_ids):
            if not isinstance(dependency_ticket_id, str) or not dependency_ticket_id:
                _raise_schema_validation_error(
                    field_path=f"followup_tickets[{index}].dependency_ticket_ids[{dependency_index}]",
                    expected="non-empty string",
                    actual_value=dependency_ticket_id if dependency_ticket_id is not None else _MISSING,
                    message="Each dependency_ticket_ids entry must be a non-empty string.",
                )
        if delivery_stage is not None:
            if not isinstance(delivery_stage, str) or delivery_stage not in {
                DeliveryStage.BUILD.value,
                DeliveryStage.CHECK.value,
                DeliveryStage.REVIEW.value,
            }:
                _raise_schema_validation_error(
                    field_path=f"followup_tickets[{index}].delivery_stage",
                    expected="one of BUILD, CHECK, REVIEW",
                    actual_value=delivery_stage,
                    message="Each consensus followup ticket delivery_stage must be one of BUILD, CHECK, REVIEW.",
                )


def _validate_source_code_delivery_payload(payload: dict[str, Any]) -> None:
    payload = _require_object(payload)
    _require_non_empty_string(payload, "summary", label="Source code delivery payload.summary")
    source_file_refs = _require_string_array(
        payload,
        "source_file_refs",
        label="Source code delivery payload.source_file_refs",
        non_empty=True,
    )
    _validate_source_code_delivery_source_files(payload, source_file_refs=source_file_refs)
    _validate_source_code_delivery_verification_runs(payload)

    implementation_notes = payload.get("implementation_notes")
    if implementation_notes is not None and (
        not isinstance(implementation_notes, list)
        or not all(isinstance(item, str) and item for item in implementation_notes)
    ):
        _raise_schema_validation_error(
            field_path="implementation_notes",
            expected="array of non-empty strings",
            actual_value=implementation_notes,
            message="Source code delivery payload.implementation_notes must be an array of strings.",
        )
    _validate_documentation_updates(payload)


def _validate_delivery_check_report_payload(payload: dict[str, Any]) -> None:
    payload = _require_object(payload)
    _require_non_empty_string(payload, "summary", label="Delivery check report payload.summary")
    _require_enum(
        payload,
        "status",
        expected_values={"PASS", "PASS_WITH_NOTES", "FAIL"},
        label="Delivery check report payload.status",
    )

    findings = _require_array(payload, "findings", label="Delivery check report payload.findings")
    for index, finding in enumerate(findings):
        if not isinstance(finding, dict):
            _raise_schema_validation_error(
                field_path=f"findings[{index}]",
                expected="object",
                actual_value=finding,
                message="Each delivery check finding must be an object.",
            )
        if not isinstance(finding.get("finding_id"), str) or not finding.get("finding_id"):
            _raise_schema_validation_error(
                field_path=f"findings[{index}].finding_id",
                expected="non-empty string",
                actual_value=finding.get("finding_id", _MISSING),
                message="Each delivery check finding requires finding_id.",
            )
        if not isinstance(finding.get("summary"), str) or not finding.get("summary"):
            _raise_schema_validation_error(
                field_path=f"findings[{index}].summary",
                expected="non-empty string",
                actual_value=finding.get("summary", _MISSING),
                message="Each delivery check finding requires summary.",
            )
        if not isinstance(finding.get("blocking"), bool):
            _raise_schema_validation_error(
                field_path=f"findings[{index}].blocking",
                expected="boolean",
                actual_value=finding.get("blocking", _MISSING),
                message="Each delivery check finding requires boolean blocking.",
            )


def _validate_delivery_closeout_package_payload(payload: dict[str, Any]) -> None:
    payload = _require_object(payload)
    _require_non_empty_string(payload, "summary", label="Delivery closeout package payload.summary")
    _require_string_array(
        payload,
        "final_artifact_refs",
        label="Delivery closeout package payload.final_artifact_refs",
        non_empty=True,
    )
    _require_string_array(
        payload,
        "handoff_notes",
        label="Delivery closeout package payload.handoff_notes",
    )
    _validate_documentation_updates(payload)


def _validate_maker_checker_verdict_payload(payload: dict[str, Any]) -> None:
    payload = _require_object(payload)
    _require_non_empty_string(payload, "summary", label="Maker-checker verdict payload.summary")
    review_status = payload.get("review_status")
    supported_statuses = {
        "APPROVED",
        "APPROVED_WITH_NOTES",
        "CHANGES_REQUIRED",
        "ESCALATED",
    }
    if not isinstance(review_status, str) or review_status not in supported_statuses:
        _raise_schema_validation_error(
            field_path="review_status",
            expected="one of APPROVED, APPROVED_WITH_NOTES, CHANGES_REQUIRED, ESCALATED",
            actual_value=review_status if review_status is not None else _MISSING,
            message="Maker-checker verdict payload.review_status must be one of "
            "APPROVED, APPROVED_WITH_NOTES, CHANGES_REQUIRED, ESCALATED.",
        )

    findings = _require_array(payload, "findings", label="Maker-checker verdict payload.findings")

    has_blocking_finding = False
    for index, finding in enumerate(findings):
        if not isinstance(finding, dict):
            _raise_schema_validation_error(
                field_path=f"findings[{index}]",
                expected="object",
                actual_value=finding,
                message="Each maker-checker finding must be an object.",
            )
        finding_id = finding.get("finding_id")
        severity = finding.get("severity")
        category = finding.get("category")
        headline = finding.get("headline")
        finding_summary = finding.get("summary")
        required_action = finding.get("required_action")
        blocking = finding.get("blocking")
        if not isinstance(finding_id, str) or not finding_id:
            _raise_schema_validation_error(
                field_path=f"findings[{index}].finding_id",
                expected="non-empty string",
                actual_value=finding_id if finding_id is not None else _MISSING,
                message="Each maker-checker finding requires finding_id.",
            )
        if not isinstance(severity, str) or not severity:
            _raise_schema_validation_error(
                field_path=f"findings[{index}].severity",
                expected="non-empty string",
                actual_value=severity if severity is not None else _MISSING,
                message="Each maker-checker finding requires severity.",
            )
        if not isinstance(category, str) or not category:
            _raise_schema_validation_error(
                field_path=f"findings[{index}].category",
                expected="non-empty string",
                actual_value=category if category is not None else _MISSING,
                message="Each maker-checker finding requires category.",
            )
        if not isinstance(headline, str) or not headline:
            _raise_schema_validation_error(
                field_path=f"findings[{index}].headline",
                expected="non-empty string",
                actual_value=headline if headline is not None else _MISSING,
                message="Each maker-checker finding requires headline.",
            )
        if not isinstance(finding_summary, str) or not finding_summary:
            _raise_schema_validation_error(
                field_path=f"findings[{index}].summary",
                expected="non-empty string",
                actual_value=finding_summary if finding_summary is not None else _MISSING,
                message="Each maker-checker finding requires summary.",
            )
        if not isinstance(required_action, str) or not required_action:
            _raise_schema_validation_error(
                field_path=f"findings[{index}].required_action",
                expected="non-empty string",
                actual_value=required_action if required_action is not None else _MISSING,
                message="Each maker-checker finding requires required_action.",
            )
        if not isinstance(blocking, bool):
            _raise_schema_validation_error(
                field_path=f"findings[{index}].blocking",
                expected="boolean",
                actual_value=blocking if blocking is not None else _MISSING,
                message="Each maker-checker finding requires boolean blocking.",
            )
        has_blocking_finding = has_blocking_finding or blocking

    if review_status == "CHANGES_REQUIRED" and not has_blocking_finding:
        _raise_schema_validation_error(
            field_path="findings",
            expected="at least one blocking finding",
            actual_value=findings,
            message="Maker-checker CHANGES_REQUIRED verdict must include at least one blocking finding.",
        )


def _validate_ceo_action_batch_payload(payload: dict[str, Any]) -> None:
    CEOActionBatch.model_validate(payload)


def _graph_patch_proposal_schema_body() -> dict[str, Any]:
    return {
        "schema_id": schema_id(GRAPH_PATCH_PROPOSAL_SCHEMA_REF, GRAPH_PATCH_PROPOSAL_SCHEMA_VERSION),
        "description": "Structured board advisory graph patch proposal.",
        "required_fields": [
            "proposal_ref",
            "workflow_id",
            "session_id",
            "base_graph_version",
            "proposal_summary",
            "impact_summary",
            "source_decision_pack_ref",
            "proposal_hash",
        ],
        "optional_fields": [
            "pros",
            "cons",
            "risk_alerts",
            "freeze_node_ids",
            "unfreeze_node_ids",
            "focus_node_ids",
            "replacements",
            "remove_node_ids",
            "add_nodes",
            "edge_additions",
            "edge_removals",
        ],
    }


def _validate_graph_patch_proposal_payload(payload: dict[str, Any]) -> None:
    GraphPatchProposal.model_validate(payload)


OUTPUT_SCHEMA_REGISTRY: dict[tuple[str, int], dict[str, Any]] = {
    (UI_MILESTONE_REVIEW_SCHEMA_REF, UI_MILESTONE_REVIEW_SCHEMA_VERSION): {
        "body": _ui_milestone_review_schema_body,
        "validator": _validate_ui_milestone_review_payload,
    },
    (CONSENSUS_DOCUMENT_SCHEMA_REF, CONSENSUS_DOCUMENT_SCHEMA_VERSION): {
        "body": _consensus_document_schema_body,
        "validator": _validate_consensus_document_payload,
    },
    (ARCHITECTURE_BRIEF_SCHEMA_REF, ARCHITECTURE_BRIEF_SCHEMA_VERSION): {
        "body": lambda: _governance_document_schema_body(ARCHITECTURE_BRIEF_SCHEMA_REF),
        "validator": lambda payload: _validate_governance_document_payload(
            payload,
            expected_document_kind_ref=ARCHITECTURE_BRIEF_SCHEMA_REF,
        ),
    },
    (TECHNOLOGY_DECISION_SCHEMA_REF, TECHNOLOGY_DECISION_SCHEMA_VERSION): {
        "body": lambda: _governance_document_schema_body(TECHNOLOGY_DECISION_SCHEMA_REF),
        "validator": lambda payload: _validate_governance_document_payload(
            payload,
            expected_document_kind_ref=TECHNOLOGY_DECISION_SCHEMA_REF,
        ),
    },
    (MILESTONE_PLAN_SCHEMA_REF, MILESTONE_PLAN_SCHEMA_VERSION): {
        "body": lambda: _governance_document_schema_body(MILESTONE_PLAN_SCHEMA_REF),
        "validator": lambda payload: _validate_governance_document_payload(
            payload,
            expected_document_kind_ref=MILESTONE_PLAN_SCHEMA_REF,
        ),
    },
    (DETAILED_DESIGN_SCHEMA_REF, DETAILED_DESIGN_SCHEMA_VERSION): {
        "body": lambda: _governance_document_schema_body(DETAILED_DESIGN_SCHEMA_REF),
        "validator": lambda payload: _validate_governance_document_payload(
            payload,
            expected_document_kind_ref=DETAILED_DESIGN_SCHEMA_REF,
        ),
    },
    (BACKLOG_RECOMMENDATION_SCHEMA_REF, BACKLOG_RECOMMENDATION_SCHEMA_VERSION): {
        "body": _backlog_recommendation_schema_body,
        "validator": _validate_backlog_recommendation_payload,
    },
    (SOURCE_CODE_DELIVERY_SCHEMA_REF, SOURCE_CODE_DELIVERY_SCHEMA_VERSION): {
        "body": _source_code_delivery_schema_body,
        "validator": _validate_source_code_delivery_payload,
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
    (GRAPH_PATCH_PROPOSAL_SCHEMA_REF, GRAPH_PATCH_PROPOSAL_SCHEMA_VERSION): {
        "body": _graph_patch_proposal_schema_body,
        "validator": _validate_graph_patch_proposal_payload,
    },
}


def get_output_schema_body(schema_ref: str, schema_version: int) -> dict[str, Any]:
    registry_entry = OUTPUT_SCHEMA_REGISTRY.get((schema_ref, schema_version))
    if registry_entry is not None:
        return _normalize_openai_strict_schema(registry_entry["body"]())
    return _normalize_openai_strict_schema({
        "type": "object",
        "unsupported_schema": schema_id(schema_ref, schema_version),
    })


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
