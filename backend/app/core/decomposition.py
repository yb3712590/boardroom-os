from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

NO_DECOMPOSITION = "NO_DECOMPOSITION"
DECOMPOSE_NOW = "DECOMPOSE_NOW"
REJECT_UNBOUNDED_REQUEST = "REJECT_UNBOUNDED_REQUEST"
RECOVERY_SEGMENT_OUTPUT_SCHEMA_REF = "architecture_brief_segment"
RECOVERY_SEGMENT_OUTPUT_SCHEMA_VERSION = 1
DECOMPOSITION_DECISION_KINDS = {
    NO_DECOMPOSITION,
    DECOMPOSE_NOW,
    REJECT_UNBOUNDED_REQUEST,
}

FORBIDDEN_DECOMPOSITION_FIELDS = {
    "default_provider",
    "default_provider_id",
    "fallback_provider",
    "fallback_provider_ids",
    "provider_response_id",
    "local_deterministic",
    "legacy_model",
    "legacy_provider",
    "model",
    "model_id",
    "provider",
    "provider_id",
}


@dataclass(frozen=True)
class DecompositionDecision:
    decision_kind: str
    reason: str
    evidence_refs: list[str]
    target_output_schema_ref: str
    target_output_schema_version: int
    uses_provider_hidden_state: bool

    def to_payload(self) -> dict[str, Any]:
        return {
            "decision_kind": self.decision_kind,
            "reason": self.reason,
            "evidence_refs": list(self.evidence_refs),
            "target_output_schema_ref": self.target_output_schema_ref,
            "target_output_schema_version": self.target_output_schema_version,
            "uses_provider_hidden_state": self.uses_provider_hidden_state,
        }


def _require_mapping(value: Any, *, field_path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{field_path} must be an object.")
    return value


def _require_string(payload: dict[str, Any], key: str, *, field_path: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_path}.{key} must be a non-empty string.")
    return value


def _require_int(payload: dict[str, Any], key: str, *, field_path: str) -> int:
    value = payload.get(key)
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ValueError(f"{field_path}.{key} must be a positive integer.")
    return value


def _require_string_list(
    payload: dict[str, Any],
    key: str,
    *,
    field_path: str,
    non_empty: bool = False,
) -> list[str]:
    value = payload.get(key)
    if not isinstance(value, list) or (non_empty and not value):
        raise ValueError(f"{field_path}.{key} must be a {'non-empty ' if non_empty else ''}array.")
    result: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"{field_path}.{key}[{index}] must be a non-empty string.")
        result.append(item)
    return result


def _scan_forbidden_fields(value: Any, *, field_path: str = "payload") -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            key_string = str(key)
            if key_string in FORBIDDEN_DECOMPOSITION_FIELDS:
                raise ValueError(f"Decomposition plan must not include forbidden field {key_string}.")
            _scan_forbidden_fields(nested, field_path=f"{field_path}.{key_string}")
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            _scan_forbidden_fields(nested, field_path=f"{field_path}[{index}]")


def validate_decomposition_decision(payload: dict[str, Any]) -> dict[str, Any]:
    payload = _require_mapping(payload, field_path="payload")
    decision_kind = _require_string(payload, "decision_kind", field_path="payload")
    if decision_kind not in DECOMPOSITION_DECISION_KINDS:
        raise ValueError(f"Unsupported decomposition decision_kind: {decision_kind}.")
    _require_string(payload, "reason", field_path="payload")
    _require_string_list(payload, "evidence_refs", field_path="payload")
    _require_string(payload, "target_output_schema_ref", field_path="payload")
    _require_int(payload, "target_output_schema_version", field_path="payload")
    if payload.get("uses_provider_hidden_state") is not False:
        raise ValueError("Decomposition decision must declare provider hidden state as false.")
    _scan_forbidden_fields(payload)
    return payload


def validate_decomposition_plan(payload: dict[str, Any]) -> dict[str, Any]:
    payload = _require_mapping(payload, field_path="payload")
    _scan_forbidden_fields(payload)
    validate_decomposition_decision(payload)
    if payload["decision_kind"] != DECOMPOSE_NOW:
        raise ValueError("Decomposition plan must use DECOMPOSE_NOW decision_kind.")

    _require_string(payload, "plan_id", field_path="payload")
    final_schema_ref = _require_string(payload, "final_output_schema_ref", field_path="payload")
    final_schema_version = _require_int(payload, "final_output_schema_version", field_path="payload")
    segment_schema_ref = _require_string(payload, "segment_output_schema_ref", field_path="payload")
    segment_schema_version = _require_int(payload, "segment_output_schema_version", field_path="payload")
    role_profile_ref = _require_string(payload, "role_profile_ref", field_path="payload")

    segments = payload.get("segments")
    if not isinstance(segments, list) or not segments:
        raise ValueError("payload.segments must be a non-empty array.")
    segment_ticket_ids: list[str] = []
    segment_artifact_refs: list[str] = []
    for index, segment_value in enumerate(segments):
        segment = _require_mapping(segment_value, field_path=f"payload.segments[{index}]")
        _require_string(segment, "segment_id", field_path=f"payload.segments[{index}]")
        segment_ticket_ids.append(_require_string(segment, "ticket_id", field_path=f"payload.segments[{index}]"))
        _require_string(segment, "node_id", field_path=f"payload.segments[{index}]")
        _require_string(segment, "summary", field_path=f"payload.segments[{index}]")
        _require_string_list(segment, "input_artifact_refs", field_path=f"payload.segments[{index}]")
        _require_string_list(
            segment,
            "acceptance_criteria",
            field_path=f"payload.segments[{index}]",
            non_empty=True,
        )
        segment_artifact_refs.append(
            _require_string(segment, "artifact_ref", field_path=f"payload.segments[{index}]")
        )
        _require_string(segment, "artifact_path", field_path=f"payload.segments[{index}]")

    if len(set(segment_ticket_ids)) != len(segment_ticket_ids):
        raise ValueError("payload.segments ticket_id values must be unique.")
    if len(set(segment_artifact_refs)) != len(segment_artifact_refs):
        raise ValueError("payload.segments artifact_ref values must be unique.")

    aggregator = _require_mapping(payload.get("aggregator"), field_path="payload.aggregator")
    _require_string(aggregator, "ticket_id", field_path="payload.aggregator")
    _require_string(aggregator, "node_id", field_path="payload.aggregator")
    _require_string(aggregator, "summary", field_path="payload.aggregator")
    aggregator_role = _require_string(aggregator, "role_profile_ref", field_path="payload.aggregator")
    if aggregator_role != role_profile_ref:
        raise ValueError("payload.aggregator.role_profile_ref must match payload.role_profile_ref.")
    aggregator_input_refs = _require_string_list(
        aggregator,
        "input_artifact_refs",
        field_path="payload.aggregator",
        non_empty=True,
    )
    missing_segment_refs = [ref for ref in segment_artifact_refs if ref not in aggregator_input_refs]
    if missing_segment_refs:
        raise ValueError("payload.aggregator.input_artifact_refs must include every segment artifact_ref.")
    _require_string_list(
        aggregator,
        "acceptance_criteria",
        field_path="payload.aggregator",
        non_empty=True,
    )
    _require_string(aggregator, "artifact_path", field_path="payload.aggregator")
    dependency_policy = _require_string(aggregator, "dependency_policy", field_path="payload.aggregator")
    if dependency_policy != "all_segments_complete":
        raise ValueError("payload.aggregator.dependency_policy must be all_segments_complete.")
    _require_string(aggregator, "reduce_instructions", field_path="payload.aggregator")

    if payload["target_output_schema_ref"] != final_schema_ref:
        raise ValueError("target_output_schema_ref must match final_output_schema_ref.")
    if payload["target_output_schema_version"] != final_schema_version:
        raise ValueError("target_output_schema_version must match final_output_schema_version.")
    if final_schema_ref == segment_schema_ref and final_schema_version == segment_schema_version:
        raise ValueError("Segment output schema must differ from final output schema.")
    return payload


def _dedupe_string_values(values: list[Any]) -> list[str]:
    result: list[str] = []
    for value in values:
        if not isinstance(value, str) or not value.strip():
            continue
        if value not in result:
            result.append(value)
    return result


def build_decomposition_recovery_plan(
    *,
    workflow_id: str,
    source_ticket_id: str,
    source_node_id: str,
    created_spec: dict[str, Any],
    failure_payload: dict[str, Any],
) -> dict[str, Any]:
    created_spec = _require_mapping(created_spec, field_path="source ticket created spec")
    role_profile_ref = _require_string(created_spec, "role_profile_ref", field_path="source ticket created spec")
    final_schema_ref = _require_string(created_spec, "output_schema_ref", field_path="source ticket created spec")
    final_schema_version = _require_int(
        created_spec,
        "output_schema_version",
        field_path="source ticket created spec",
    )
    source_summary = str(created_spec.get("summary") or source_ticket_id).strip()
    input_artifact_refs = _dedupe_string_values(list(created_spec.get("input_artifact_refs") or []))
    if not input_artifact_refs:
        raise ValueError("source ticket created spec.input_artifact_refs must include replayable artifacts.")

    failure_kind = _require_string(failure_payload, "failure_kind", field_path="failure payload")
    failure_message = _require_string(failure_payload, "failure_message", field_path="failure payload")
    failure_fingerprint = _require_string(
        failure_payload,
        "failure_fingerprint",
        field_path="failure payload",
    )
    plan_id = f"decomp_recovery_{workflow_id}_{source_ticket_id}"
    segment_specs = [
        (
            "scope_and_requirements",
            "Clarify source scope, constraints, inputs, and acceptance boundaries.",
            "Must produce a replayable scope-and-requirements segment artifact for the failed source ticket.",
        ),
        (
            "solution_and_risks",
            "Clarify solution structure, risks, verification, and delivery evidence.",
            "Must produce a replayable solution-and-risks segment artifact for the failed source ticket.",
        ),
    ]
    segments: list[dict[str, Any]] = []
    for segment_id, summary, acceptance in segment_specs:
        ticket_id = f"{source_ticket_id}_decomp_{segment_id}"
        segments.append(
            {
                "segment_id": segment_id,
                "ticket_id": ticket_id,
                "node_id": f"{source_node_id}__decomp_{segment_id}",
                "summary": f"{summary} Source ticket: {source_summary}",
                "input_artifact_refs": list(input_artifact_refs),
                "acceptance_criteria": [
                    acceptance,
                    f"Must address failure kind {failure_kind}: {failure_message}",
                    "Must write the segment output as an artifact and avoid hidden provider state.",
                ],
                "artifact_ref": f"art://runtime/{ticket_id}/architecture_brief_segment.json",
                "artifact_path": f"reports/decomposition/{ticket_id}/architecture_brief_segment.json",
            }
        )

    segment_artifact_refs = [segment["artifact_ref"] for segment in segments]
    aggregator_ticket_id = f"{source_ticket_id}_decomp_aggregator"
    plan = {
        "decision_kind": DECOMPOSE_NOW,
        "reason": f"Source ticket failed with {failure_kind}; recover by decomposing into replayable atomic tickets.",
        "evidence_refs": [
            f"ticket://{source_ticket_id}",
            f"node://{source_node_id}",
            f"failure://{failure_fingerprint}",
        ],
        "target_output_schema_ref": final_schema_ref,
        "target_output_schema_version": final_schema_version,
        "uses_provider_hidden_state": False,
        "plan_id": plan_id,
        "final_output_schema_ref": final_schema_ref,
        "final_output_schema_version": final_schema_version,
        "segment_output_schema_ref": RECOVERY_SEGMENT_OUTPUT_SCHEMA_REF,
        "segment_output_schema_version": RECOVERY_SEGMENT_OUTPUT_SCHEMA_VERSION,
        "role_profile_ref": role_profile_ref,
        "segments": segments,
        "aggregator": {
            "ticket_id": aggregator_ticket_id,
            "node_id": f"{source_node_id}__decomp_aggregator",
            "summary": f"Synthesize recovered output for failed source ticket {source_ticket_id}.",
            "role_profile_ref": role_profile_ref,
            "input_artifact_refs": [*input_artifact_refs, *segment_artifact_refs],
            "acceptance_criteria": [
                f"Must synthesize the final {final_schema_ref} from every segment artifact.",
                "Must cite every segment artifact and preserve replayability through artifact refs.",
                "Must not rely on provider hidden conversation or fallback state.",
            ],
            "artifact_path": f"reports/decomposition/{aggregator_ticket_id}/{final_schema_ref}.json",
            "dependency_policy": "all_segments_complete",
            "reduce_instructions": (
                "Read every decomposition segment artifact and synthesize the final schema without hidden state. "
                f"Recover from failure {failure_kind}: {failure_message}"
            ),
        },
    }
    return validate_decomposition_plan(plan)


def build_decomposition_ticket_specs(
    plan: dict[str, Any],
    *,
    build_ticket_spec: Callable[[dict[str, Any], list[str]], dict[str, Any]],
) -> list[dict[str, Any]]:
    plan = validate_decomposition_plan(plan)
    segment_specs: list[dict[str, Any]] = []
    for segment in plan["segments"]:
        planned = {
            "ticket_id": segment["ticket_id"],
            "node_id": segment["node_id"],
            "role_profile_ref": plan["role_profile_ref"],
            "summary": segment["summary"],
            "input_artifact_refs": list(segment["input_artifact_refs"]),
            "context_keywords": ["decomposition", str(segment["segment_id"]).replace("_", " ")],
            "semantic_query": segment["summary"],
            "acceptance_criteria": list(segment["acceptance_criteria"]),
            "output_schema_ref": plan["segment_output_schema_ref"],
            "output_schema_version": plan["segment_output_schema_version"],
            "allowed_write_set": [segment["artifact_path"]],
        }
        segment_specs.append(build_ticket_spec(planned, []))

    segment_ticket_ids = [str(segment["ticket_id"]) for segment in plan["segments"]]
    aggregator = plan["aggregator"]
    planned_aggregator = {
        "ticket_id": aggregator["ticket_id"],
        "node_id": aggregator["node_id"],
        "role_profile_ref": aggregator["role_profile_ref"],
        "summary": aggregator["summary"],
        "input_artifact_refs": list(aggregator["input_artifact_refs"]),
        "context_keywords": ["decomposition", "reduce", plan["final_output_schema_ref"]],
        "semantic_query": aggregator["reduce_instructions"],
        "acceptance_criteria": list(aggregator["acceptance_criteria"]),
        "output_schema_ref": plan["final_output_schema_ref"],
        "output_schema_version": plan["final_output_schema_version"],
        "allowed_write_set": [aggregator["artifact_path"]],
    }
    return [*segment_specs, build_ticket_spec(planned_aggregator, segment_ticket_ids)]
