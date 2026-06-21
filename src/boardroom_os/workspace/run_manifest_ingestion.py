from __future__ import annotations

import hashlib
import json
from typing import Any, Literal, Mapping, Self

from pydantic import BaseModel, ConfigDict, field_validator, model_validator


class RunManifestRawAssertion(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    probe_id: str
    step_id: str
    assertion_index: int
    raw_type: str
    raw_payload: dict[str, Any]
    source_ref: str

    @field_validator("probe_id", "step_id", "raw_type", "source_ref")
    @classmethod
    def _reject_empty_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("text fields must not be empty")
        return normalized

    @field_validator("assertion_index")
    @classmethod
    def _reject_negative_index(cls, value: int) -> int:
        if value < 0:
            raise ValueError("assertion_index must be non-negative")
        return value

    @field_validator("raw_payload")
    @classmethod
    def _reject_empty_payload(cls, value: dict[str, Any]) -> dict[str, Any]:
        if not value:
            raise ValueError("raw_payload must not be empty")
        return dict(value)


class RunManifestSkeletonSummary(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    command_ids: tuple[str, ...]
    service_command_ids: tuple[str, ...]
    behavioral_probe_ids: tuple[str, ...]
    step_ids: tuple[str, ...]
    raw_assertion_count: int
    unknown_assertion_count: int

    @field_validator("command_ids", "service_command_ids", "behavioral_probe_ids", "step_ids")
    @classmethod
    def _reject_empty_tuple_items(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(value.strip() for value in values)
        if len(normalized) != len(values) or any(not value for value in normalized):
            raise ValueError("summary tuples must contain non-empty text")
        return normalized

    @field_validator("raw_assertion_count", "unknown_assertion_count")
    @classmethod
    def _reject_negative_counts(cls, value: int) -> int:
        if value < 0:
            raise ValueError("summary counts must be non-negative")
        return value

    @model_validator(mode="after")
    def _validate_counts(self) -> Self:
        if self.unknown_assertion_count > self.raw_assertion_count:
            raise ValueError("unknown_assertion_count cannot exceed raw_assertion_count")
        return self


class RunManifestIngestionContext(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    source_ref: str
    raw_manifest_ref: str
    raw_manifest_sha256: str
    skeleton_summary: RunManifestSkeletonSummary
    raw_assertions: tuple[RunManifestRawAssertion, ...]
    ingestion_status: Literal["context_only"] = "context_only"

    @field_validator("source_ref", "raw_manifest_ref", "raw_manifest_sha256")
    @classmethod
    def _reject_empty_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("text fields must not be empty")
        return normalized

    @field_validator("raw_manifest_sha256")
    @classmethod
    def _validate_sha256_ref(cls, value: str) -> str:
        if not value.startswith("sha256:") or len(value) != len("sha256:") + 64:
            raise ValueError("raw_manifest_sha256 must use sha256:<64 lowercase hex>")
        digest = value.removeprefix("sha256:")
        if not all(char in "0123456789abcdef" for char in digest):
            raise ValueError("raw_manifest_sha256 must use sha256:<64 lowercase hex>")
        return value


def ingest_run_manifest_artifact(
    *,
    artifact: Mapping[str, Any],
    source_ref: str,
    raw_manifest_ref: str,
) -> RunManifestIngestionContext:
    if not isinstance(artifact, Mapping):
        raise ValueError("RunManifest artifact must be an object")
    source_ref = _non_empty_text(source_ref, "source_ref")
    raw_manifest_ref = _non_empty_text(raw_manifest_ref, "raw_manifest_ref")
    raw_assertions = tuple(_iter_raw_assertions(artifact, source_ref=source_ref))
    return RunManifestIngestionContext(
        source_ref=source_ref,
        raw_manifest_ref=raw_manifest_ref,
        raw_manifest_sha256=_artifact_sha256(artifact),
        skeleton_summary=RunManifestSkeletonSummary(
            command_ids=tuple(_command_ids(artifact)),
            service_command_ids=tuple(_service_command_ids(artifact)),
            behavioral_probe_ids=tuple(_behavioral_probe_ids(artifact)),
            step_ids=tuple(_step_ids(artifact)),
            raw_assertion_count=len(raw_assertions),
            unknown_assertion_count=len(raw_assertions),
        ),
        raw_assertions=raw_assertions,
    )


def _iter_raw_assertions(
    artifact: Mapping[str, Any],
    *,
    source_ref: str,
) -> tuple[RunManifestRawAssertion, ...]:
    assertions: list[RunManifestRawAssertion] = []
    for probe in _mapping_items(artifact.get("behavioral_probes")):
        probe_id = _string_value(probe.get("probe_id"), fallback="unknown-probe")
        for step in _mapping_items(probe.get("steps") or probe.get("http_steps")):
            step_id = _string_value(step.get("step_id"), fallback="unknown-step")
            for index, assertion in _raw_assertion_items(step.get("assertions")):
                raw_type = _string_value(
                    assertion.get("kind") or assertion.get("type") or assertion.get("operator"),
                    fallback="unknown",
                )
                assertions.append(
                    RunManifestRawAssertion(
                        probe_id=probe_id,
                        step_id=step_id,
                        assertion_index=index,
                        raw_type=raw_type,
                        raw_payload=dict(assertion),
                        source_ref=f"{source_ref}#{probe_id}/{step_id}/assertions/{index}",
                    )
                )
    return tuple(assertions)


def _raw_assertion_items(value: Any) -> tuple[tuple[int, dict[str, Any]], ...]:
    if not isinstance(value, list | tuple):
        return ()
    assertions: list[tuple[int, dict[str, Any]]] = []
    for index, item in enumerate(value):
        if isinstance(item, Mapping):
            assertions.append((index, dict(item)))
            continue
        assertions.append((index, {"value": item}))
    return tuple(assertions)


def _command_ids(artifact: Mapping[str, Any]) -> tuple[str, ...]:
    return tuple(
        _string_value(command.get("command_id"), fallback="")
        for command in _mapping_items(artifact.get("commands"))
        if _string_value(command.get("command_id"), fallback="")
    )


def _service_command_ids(artifact: Mapping[str, Any]) -> tuple[str, ...]:
    values: list[str] = []
    for service in _mapping_items(artifact.get("service_contracts")):
        command_id = _string_value(
            service.get("command_id") or service.get("run_command_id"),
            fallback="",
        )
        if command_id:
            values.append(command_id)
    return tuple(values)


def _behavioral_probe_ids(artifact: Mapping[str, Any]) -> tuple[str, ...]:
    return tuple(
        _string_value(probe.get("probe_id"), fallback="")
        for probe in _mapping_items(artifact.get("behavioral_probes"))
        if _string_value(probe.get("probe_id"), fallback="")
    )


def _step_ids(artifact: Mapping[str, Any]) -> tuple[str, ...]:
    values: list[str] = []
    for probe in _mapping_items(artifact.get("behavioral_probes")):
        for step in _mapping_items(probe.get("steps") or probe.get("http_steps")):
            step_id = _string_value(step.get("step_id"), fallback="")
            if step_id:
                values.append(step_id)
    return tuple(values)


def _mapping_items(value: Any) -> tuple[Mapping[str, Any], ...]:
    if not isinstance(value, list | tuple):
        return ()
    return tuple(item for item in value if isinstance(item, Mapping))


def _string_value(value: Any, *, fallback: str) -> str:
    if isinstance(value, Mapping) and isinstance(value.get("value"), str):
        value = value["value"]
    if isinstance(value, str) and value.strip():
        return value.strip()
    return fallback


def _non_empty_text(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must not be empty")
    return value.strip()


def _artifact_sha256(artifact: Mapping[str, Any]) -> str:
    canonical = json.dumps(
        artifact,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


__all__ = [
    "RunManifestIngestionContext",
    "RunManifestRawAssertion",
    "RunManifestSkeletonSummary",
    "ingest_run_manifest_artifact",
]
