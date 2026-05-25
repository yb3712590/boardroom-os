from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from enum import StrEnum
from typing import Any, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    ValidationError,
    computed_field,
    field_serializer,
    field_validator,
    model_validator,
)

from boardroom_os.agents.skills import _normalize_ref_fields
from boardroom_os.closeout.gate import (
    EventRangeRef,
    ProjectionVersionRef,
    ReplayBundleReadiness,
    ReplaySummaryHash,
)
from boardroom_os.contracts.types import NonEmptyTextValue
from boardroom_os.events.record import EventRecord
from boardroom_os.events.types import EventId, ProjectRef
from boardroom_os.graph.replay import ProjectionReplaySummary

_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
_ZERO_HASH = "0" * 64


class ReplayBundleError(ValueError):
    pass


def _is_placeholder_hash(value: str) -> bool:
    return len(set(value)) == 1



def _validate_replay_summary_hash(value: ReplaySummaryHash) -> ReplaySummaryHash:
    return value


class ReplayBundleRef(NonEmptyTextValue):
    pass


class ReplayAttestationRef(NonEmptyTextValue):
    pass


class ReplayReportRef(NonEmptyTextValue):
    pass


class ReplayManifestRef(NonEmptyTextValue):
    pass


class ReplayContentRef(NonEmptyTextValue):
    pass


class ReplayContentHash(NonEmptyTextValue):
    @field_validator("value")
    @classmethod
    def _require_lowercase_sha256(cls, value: str) -> str:
        if not _SHA256_PATTERN.fullmatch(value):
            raise ValueError("sha256 must be a 64-character lowercase hex digest")
        if _is_placeholder_hash(value):
            raise ValueError("sha256 must not be a placeholder or synthetic digest")
        return value


class ReplayPreviousHash(NonEmptyTextValue):
    @field_validator("value")
    @classmethod
    def _require_lowercase_sha256(cls, value: str) -> str:
        if not _SHA256_PATTERN.fullmatch(value):
            raise ValueError("sha256 must be a 64-character lowercase hex digest")
        return value


class ReplayAttestationKind(StrEnum):
    SEAT_ASSIGNMENT_GRAPH = "seat_assignment_graph"


class ReplayManifestKind(StrEnum):
    EVENT_WINDOW = "event_window"
    PAYLOAD_MANIFEST = "payload_manifest"
    ARTIFACT_MANIFEST = "artifact_manifest"
    HASH_MANIFEST = "hash_manifest"
    REPLAY_REPORT = "replay_report"


class ReplayEventWindow(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    project_ref: ProjectRef
    first_graph_version: int = Field(gt=0)
    last_graph_version: int = Field(gt=0)
    first_event_id: EventId
    last_event_id: EventId
    event_count: int = Field(gt=0)

    @model_validator(mode="before")
    @classmethod
    def _normalize_refs(cls, data: Any) -> Any:
        return _normalize_ref_fields(
            data,
            {
                "project_ref": ProjectRef,
                "first_event_id": EventId,
                "last_event_id": EventId,
            },
        )

    @model_validator(mode="after")
    def _validate_window(self) -> Self:
        if self.first_graph_version > self.last_graph_version:
            raise ReplayBundleError("event range must be ordered")
        expected_count = self.last_graph_version - self.first_graph_version + 1
        if self.event_count != expected_count:
            raise ReplayBundleError("event_count must match contiguous graph_version range")
        return self


class ReplayEventHashNode(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    event_id: EventId
    graph_version: int = Field(gt=0)
    event_hash: ReplayContentHash
    previous_hash: ReplayPreviousHash
    chain_hash: ReplayContentHash

    @model_validator(mode="before")
    @classmethod
    def _normalize_refs(cls, data: Any) -> Any:
        return _normalize_ref_fields(
            data,
            {
                "event_id": EventId,
                "event_hash": ReplayContentHash,
                "previous_hash": ReplayPreviousHash,
                "chain_hash": ReplayContentHash,
            },
        )


class ReplayManifestEntry(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    manifest_ref: ReplayManifestRef
    kind: ReplayManifestKind
    content_ref: ReplayContentRef
    sha256: ReplayContentHash

    @model_validator(mode="before")
    @classmethod
    def _normalize_refs(cls, data: Any) -> Any:
        return _normalize_ref_fields(
            data,
            {
                "manifest_ref": ReplayManifestRef,
                "content_ref": ReplayContentRef,
                "sha256": ReplayContentHash,
            },
        )

    @field_validator("content_ref")
    @classmethod
    def _reject_unsafe_content_ref(cls, value: ReplayContentRef) -> ReplayContentRef:
        ref = value.value
        if (
            ref.startswith("/")
            or "\\" in ref
            or re.match(r"^[A-Za-z]:", ref)
            or ref in {".", ".."}
            or ref.endswith("/")
            or ref.endswith("/.")
            or ref.endswith("/..")
            or "/./" in ref
            or ref.startswith("./")
            or ref.startswith("../")
            or "/../" in ref
        ):
            raise ReplayBundleError("content_ref must be audit-friendly")
        return value

    @field_serializer("kind")
    def _serialize_kind(self, value: ReplayManifestKind) -> str:
        return value.value


class ReplayArtifactManifestEntry(ReplayManifestEntry):
    pass


class ReplayPayloadManifest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    payload_manifest_id: ReplayManifestRef
    project_ref: ProjectRef
    entries: tuple[ReplayManifestEntry, ...]

    @model_validator(mode="before")
    @classmethod
    def _normalize_refs(cls, data: Any) -> Any:
        if isinstance(data, dict) and "entries" in data and not isinstance(
            data["entries"], list | tuple
        ):
            raise ReplayBundleError("entries must be a tuple or list")
        return _normalize_ref_fields(
            data,
            {
                "payload_manifest_id": ReplayManifestRef,
                "project_ref": ProjectRef,
            },
        )

    @field_validator("entries")
    @classmethod
    def _validate_entries(
        cls,
        values: tuple[ReplayManifestEntry, ...],
    ) -> tuple[ReplayManifestEntry, ...]:
        if not values:
            raise ReplayBundleError("payload manifest entries must not be empty")
        refs = [entry.content_ref.value for entry in values]
        if len(set(refs)) != len(refs):
            raise ReplayBundleError("payload manifest content refs must be unique")
        return values


class ReplayArtifactManifest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    artifact_manifest_id: ReplayManifestRef
    project_ref: ProjectRef
    entries: tuple[ReplayArtifactManifestEntry, ...]

    @model_validator(mode="before")
    @classmethod
    def _normalize_refs(cls, data: Any) -> Any:
        if isinstance(data, dict) and "entries" in data and not isinstance(
            data["entries"], list | tuple
        ):
            raise ReplayBundleError("entries must be a tuple or list")
        return _normalize_ref_fields(
            data,
            {
                "artifact_manifest_id": ReplayManifestRef,
                "project_ref": ProjectRef,
            },
        )

    @field_validator("entries")
    @classmethod
    def _validate_entries(
        cls,
        values: tuple[ReplayArtifactManifestEntry, ...],
    ) -> tuple[ReplayArtifactManifestEntry, ...]:
        if not values:
            raise ReplayBundleError("artifact manifest entries must not be empty")
        manifest_refs = [entry.manifest_ref.value for entry in values]
        content_refs = [entry.content_ref.value for entry in values]
        if len(set(manifest_refs)) != len(manifest_refs):
            raise ReplayBundleError("artifact manifest refs must be unique")
        if len(set(content_refs)) != len(content_refs):
            raise ReplayBundleError("artifact manifest content refs must be unique")
        return values


    @property
    def entries_by_kind(
        self,
    ) -> dict[ReplayManifestKind, ReplayArtifactManifestEntry]:
        return {entry.kind: entry for entry in self.entries}


class ReplayReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    replay_report_id: ReplayReportRef
    project_ref: ProjectRef
    projection_kind: Literal["seat_assignment_graph"]
    projection_version: ProjectionVersionRef
    event_range: ReplayEventWindow
    event_count: int = Field(gt=0)
    summary_hash: ReplaySummaryHash
    replay_passed: StrictBool
    blockers: tuple[str, ...]
    generated_at: datetime

    @model_validator(mode="before")
    @classmethod
    def _normalize_refs(cls, data: Any) -> Any:
        if isinstance(data, dict) and "blockers" in data and not isinstance(
            data["blockers"], list | tuple
        ):
            raise ReplayBundleError("blockers must be a tuple or list")
        return _normalize_ref_fields(
            data,
            {
                "replay_report_id": ReplayReportRef,
                "project_ref": ProjectRef,
                "projection_version": ProjectionVersionRef,
                "summary_hash": ReplaySummaryHash,
            },
        )

    @field_validator("generated_at")
    @classmethod
    def _require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ReplayBundleError("generated_at must include timezone")
        return value

    @field_validator("blockers")
    @classmethod
    def _validate_blockers(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(value.strip() for value in values)
        if any(not value for value in normalized):
            raise ReplayBundleError("blockers must not contain empty values")
        return normalized

    @field_validator("summary_hash")
    @classmethod
    def _validate_summary_hash(
        cls,
        value: ReplaySummaryHash,
    ) -> ReplaySummaryHash:
        return _validate_replay_summary_hash(value)

    @model_validator(mode="after")
    def _validate_report(self) -> Self:
        if self.event_count != self.event_range.event_count:
            raise ReplayBundleError("replay report event_count mismatch")
        if self.replay_passed is not True:
            raise ReplayBundleError("replay_passed must be true")
        if self.blockers:
            raise ReplayBundleError("blockers must be empty in replay report v1")
        return self


class ReplayAttestation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    attestation_id: ReplayAttestationRef
    kind: ReplayAttestationKind
    projection_kind: Literal["seat_assignment_graph"]
    project_ref: ProjectRef
    projection_version: ProjectionVersionRef
    event_window: ReplayEventWindow
    event_window_hash: ReplayContentHash
    payload_manifest_ref: ReplayManifestRef
    artifact_manifest_ref: ReplayManifestRef
    hash_manifest_ref: ReplayManifestRef
    replay_report_ref: ReplayReportRef
    summary_hash: ReplaySummaryHash
    replay_passed: StrictBool

    @model_validator(mode="before")
    @classmethod
    def _normalize_refs(cls, data: Any) -> Any:
        return _normalize_ref_fields(
            data,
            {
                "attestation_id": ReplayAttestationRef,
                "project_ref": ProjectRef,
                "projection_version": ProjectionVersionRef,
                "event_window_hash": ReplayContentHash,
                "payload_manifest_ref": ReplayManifestRef,
                "artifact_manifest_ref": ReplayManifestRef,
                "hash_manifest_ref": ReplayManifestRef,
                "replay_report_ref": ReplayReportRef,
                "summary_hash": ReplaySummaryHash,
            },
        )

    @model_validator(mode="after")
    def _validate_attestation(self) -> Self:
        _validate_replay_summary_hash(self.summary_hash)
        if self.projection_kind != self.kind.value:
            raise ReplayBundleError("projection_kind must match attestation kind value")
        if self.project_ref != self.event_window.project_ref:
            raise ReplayBundleError("attestation project_ref must match event_window")
        if self.replay_passed is not True:
            raise ReplayBundleError("attestation replay_passed must be true")
        return self

    @field_serializer("kind")
    def _serialize_kind(self, value: ReplayAttestationKind) -> str:
        return value.value


class ReplayHashManifest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    hash_manifest_id: ReplayManifestRef
    project_ref: ProjectRef
    event_hash_chain: tuple[ReplayEventHashNode, ...]
    terminal_event_chain_hash: ReplayContentHash
    event_window_hash: ReplayContentHash
    payload_manifest_hash: ReplayContentHash
    artifact_manifest_hash: ReplayContentHash
    replay_report_hash: ReplayContentHash
    attestation_hashes: dict[str, ReplayContentHash]

    @model_validator(mode="before")
    @classmethod
    def _normalize_refs(cls, data: Any) -> Any:
        normalized = _normalize_ref_fields(
            data,
            {
                "hash_manifest_id": ReplayManifestRef,
                "project_ref": ProjectRef,
                "terminal_event_chain_hash": ReplayContentHash,
                "event_window_hash": ReplayContentHash,
                "payload_manifest_hash": ReplayContentHash,
                "artifact_manifest_hash": ReplayContentHash,
                "replay_report_hash": ReplayContentHash,
            },
        )
        if isinstance(normalized, dict) and "attestation_hashes" in normalized:
            normalized = dict(normalized)
            normalized["attestation_hashes"] = {
                key: _normalize_ref_fields(
                    {"value": value} if isinstance(value, str) else value,
                    {"value": ReplayContentHash},
                )["value"]
                if not isinstance(value, ReplayContentHash)
                else value
                for key, value in normalized["attestation_hashes"].items()
            }
        return normalized

    @field_validator("event_hash_chain")
    @classmethod
    def _validate_chain(
        cls,
        values: tuple[ReplayEventHashNode, ...],
    ) -> tuple[ReplayEventHashNode, ...]:
        if not values:
            raise ReplayBundleError("event hash chain must not be empty")
        previous_graph_version: int | None = None
        previous_chain_hash: str = _ZERO_HASH
        seen_event_ids: set[str] = set()
        for index, node in enumerate(values):
            if node.event_id.value in seen_event_ids:
                raise ReplayBundleError("event hash chain event ids must be unique")
            seen_event_ids.add(node.event_id.value)
            if previous_graph_version is not None and node.graph_version != previous_graph_version + 1:
                raise ReplayBundleError("event hash chain graph_version must be contiguous")
            expected_previous = _ZERO_HASH if index == 0 else previous_chain_hash
            if node.previous_hash.value != expected_previous:
                raise ReplayBundleError("event hash chain previous_hash mismatch")
            expected_chain = _sha256_text(node.previous_hash.value + node.event_hash.value)
            if node.chain_hash.value != expected_chain:
                raise ReplayBundleError("event hash chain chain_hash mismatch")
            previous_graph_version = node.graph_version
            previous_chain_hash = node.chain_hash.value
        return values

    @field_validator("attestation_hashes")
    @classmethod
    def _validate_attestation_hashes(
        cls,
        values: dict[str, ReplayContentHash],
    ) -> dict[str, ReplayContentHash]:
        if not values:
            raise ReplayBundleError("attestation_hashes must not be empty")
        normalized: dict[str, ReplayContentHash] = {}
        for key, value in values.items():
            normalized_key = key.strip()
            if not normalized_key:
                raise ReplayBundleError("attestation_hashes keys must not be empty")
            if normalized_key in normalized:
                raise ReplayBundleError("attestation_hashes keys must be unique after trim")
            normalized[normalized_key] = value
        return normalized

    @model_validator(mode="after")
    def _validate_terminal_hash(self) -> Self:
        if self.terminal_event_chain_hash != self.event_hash_chain[-1].chain_hash:
            raise ReplayBundleError("event hash chain terminal hash mismatch")
        return self


class ReplayBundle(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    version: Literal[1] = 1
    replay_bundle_id: ReplayBundleRef
    project_ref: ProjectRef
    generated_at: datetime
    events: tuple[EventRecord, ...]
    attestations: tuple[ReplayAttestation, ...]
    payload_manifest: ReplayPayloadManifest
    hash_manifest: ReplayHashManifest
    artifact_manifest: ReplayArtifactManifest
    replay_report: ReplayReport
    checked_refs: tuple[str, ...]

    @model_validator(mode="before")
    @classmethod
    def _normalize_refs(cls, data: Any) -> Any:
        if isinstance(data, dict) and "checked_refs" in data and not isinstance(
            data["checked_refs"], list | tuple
        ):
            raise ReplayBundleError("checked_refs must be a tuple or list")
        if isinstance(data, dict) and "events" in data and not isinstance(
            data["events"], list | tuple
        ):
            raise ReplayBundleError("events must be a tuple or list")
        return _normalize_ref_fields(
            data,
            {
                "replay_bundle_id": ReplayBundleRef,
                "project_ref": ProjectRef,
            },
        )

    @field_validator("generated_at")
    @classmethod
    def _require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ReplayBundleError("generated_at must include timezone")
        return value

    @field_validator("checked_refs")
    @classmethod
    def _validate_checked_refs(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(value.strip() for value in values)
        if not normalized:
            raise ReplayBundleError("checked_refs must not be empty")
        if any(not value for value in normalized):
            raise ReplayBundleError("checked_refs must not contain empty values")
        if len(set(normalized)) != len(normalized):
            raise ReplayBundleError("checked_refs must be unique")
        return normalized

    @model_validator(mode="after")
    def _validate_bundle(self) -> Self:
        if len(self.attestations) != 1:
            raise ReplayBundleError("ReplayBundle v1 requires exactly one attestation")
        attestation = self.attestations[0]
        _validate_events_against_window(self.events, attestation.event_window)
        if attestation.kind is not ReplayAttestationKind.SEAT_ASSIGNMENT_GRAPH:
            raise ReplayBundleError("ReplayBundle v1 only supports seat_assignment_graph")
        if self.project_ref != attestation.project_ref:
            raise ReplayBundleError("bundle project_ref must match attestation")
        if self.project_ref != self.payload_manifest.project_ref:
            raise ReplayBundleError("bundle project_ref must match payload manifest")
        if self.project_ref != self.hash_manifest.project_ref:
            raise ReplayBundleError("bundle project_ref must match hash manifest")
        if self.project_ref != self.artifact_manifest.project_ref:
            raise ReplayBundleError("bundle project_ref must match artifact manifest")
        if self.project_ref != self.replay_report.project_ref:
            raise ReplayBundleError("bundle project_ref must match replay report")
        if attestation.artifact_manifest_ref.value != self.artifact_manifest.artifact_manifest_id.value:
            raise ReplayBundleError("artifact_manifest_ref must close over artifact manifest")
        if attestation.hash_manifest_ref.value != self.hash_manifest.hash_manifest_id.value:
            raise ReplayBundleError("hash_manifest_ref must close over hash manifest")
        if attestation.replay_report_ref.value != self.replay_report.replay_report_id.value:
            raise ReplayBundleError("replay_report_ref must close over replay report")
        if attestation.payload_manifest_ref.value != self.payload_manifest.payload_manifest_id.value:
            raise ReplayBundleError("payload_manifest_ref must close over payload manifest")
        attestation_hash_keys = set(self.hash_manifest.attestation_hashes)
        expected_attestation_hash_keys = {attestation.attestation_id.value}
        if attestation_hash_keys != expected_attestation_hash_keys:
            raise ReplayBundleError("attestation_hashes must cover bundle attestations exactly")
        return self

    @computed_field
    @property
    def bundle_hash(self) -> str:
        payload = self.model_dump(mode="json", exclude={"bundle_hash"})
        return _hash_jsonable(payload)


class ReplayBundleBuilderInput(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    project_ref: ProjectRef
    events: tuple[EventRecord, ...]
    projection_summary: ProjectionReplaySummary
    projection_version: ProjectionVersionRef
    payload_manifest_ref: ReplayManifestRef
    payload_manifest_entries: tuple[ReplayManifestEntry, ...]
    event_window_ref: ReplayManifestRef
    artifact_manifest_ref: ReplayManifestRef
    artifact_manifest_entries: tuple[ReplayArtifactManifestEntry, ...]
    hash_manifest_ref: ReplayManifestRef
    replay_report_ref: ReplayReportRef
    generated_at: datetime

    @model_validator(mode="before")
    @classmethod
    def _normalize_refs(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        tuple_fields = (
            "events",
            "payload_manifest_entries",
            "artifact_manifest_entries",
        )
        for field_name in tuple_fields:
            if field_name in data and not isinstance(data[field_name], list | tuple):
                raise ReplayBundleError(f"{field_name} must be a tuple or list")
        return _normalize_ref_fields(
            data,
            {
                "project_ref": ProjectRef,
                "projection_version": ProjectionVersionRef,
                "payload_manifest_ref": ReplayManifestRef,
                "event_window_ref": ReplayManifestRef,
                "artifact_manifest_ref": ReplayManifestRef,
                "hash_manifest_ref": ReplayManifestRef,
                "replay_report_ref": ReplayReportRef,
            },
        )

    @field_validator("generated_at")
    @classmethod
    def _require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ReplayBundleError("generated_at must include timezone")
        return value

    @field_validator("events")
    @classmethod
    def _validate_events(cls, values: tuple[EventRecord, ...]) -> tuple[EventRecord, ...]:
        if not values:
            raise ReplayBundleError("events must not be empty")
        previous_graph_version: int | None = None
        for event in values:
            if previous_graph_version is not None:
                if event.graph_version <= previous_graph_version:
                    raise ReplayBundleError("events graph_version must be strictly ordered")
                if event.graph_version != previous_graph_version + 1:
                    raise ReplayBundleError("events graph_version must be contiguous")
            previous_graph_version = event.graph_version
        return values

    @model_validator(mode="after")
    def _validate_input(self) -> Self:
        for event in self.events:
            if event.project_ref != self.project_ref:
                raise ReplayBundleError("event project_ref mismatch")
        summary = self.projection_summary
        if summary.project_ref != self.project_ref:
            raise ReplayBundleError("projection_summary project_ref mismatch")
        if summary.projection_kind != ReplayAttestationKind.SEAT_ASSIGNMENT_GRAPH.value:
            raise ReplayBundleError("projection kind mismatch")
        if summary.event_range.first_graph_version != self.events[0].graph_version:
            raise ReplayBundleError("projection_summary event_range mismatch")
        if summary.event_range.last_graph_version != self.events[-1].graph_version:
            raise ReplayBundleError("projection_summary event_range mismatch")
        if summary.event_range.first_event_id != self.events[0].event_id:
            raise ReplayBundleError("projection_summary event_range mismatch")
        if summary.event_range.last_event_id != self.events[-1].event_id:
            raise ReplayBundleError("projection_summary event_range mismatch")
        if summary.event_count != len(self.events):
            raise ReplayBundleError("projection_summary event_count mismatch")
        if summary.graph_version != self.events[-1].graph_version:
            raise ReplayBundleError("projection_summary graph_version mismatch")
        return self


def build_replay_bundle(builder_input: ReplayBundleBuilderInput) -> ReplayBundle:
    if not isinstance(builder_input, ReplayBundleBuilderInput):
        raise ReplayBundleError("builder_input must be ReplayBundleBuilderInput")
    builder_input = _validate_builder_input_instance(builder_input)
    if ReplayAttestationKind.SEAT_ASSIGNMENT_GRAPH.value != builder_input.projection_summary.projection_kind:
        raise ReplayBundleError("projection kind mismatch")
    expected_projection_version = _projection_version_for_kind(
        builder_input.projection_summary.projection_kind
    )
    if builder_input.projection_version.value != expected_projection_version:
        raise ReplayBundleError("projection version mismatch")

    payload_manifest = ReplayPayloadManifest(
        payload_manifest_id=builder_input.payload_manifest_ref,
        project_ref=builder_input.project_ref,
        entries=builder_input.payload_manifest_entries,
    )
    _validate_payload_manifest_coverage(builder_input.events, payload_manifest)

    input_artifact_manifest = ReplayArtifactManifest(
        artifact_manifest_id=builder_input.artifact_manifest_ref,
        project_ref=builder_input.project_ref,
        entries=builder_input.artifact_manifest_entries,
    )

    event_window = ReplayEventWindow(
        project_ref=builder_input.project_ref,
        first_graph_version=builder_input.events[0].graph_version,
        last_graph_version=builder_input.events[-1].graph_version,
        first_event_id=builder_input.events[0].event_id,
        last_event_id=builder_input.events[-1].event_id,
        event_count=len(builder_input.events),
    )
    event_window_ref = _event_range_ref(builder_input.project_ref, event_window)
    _validate_required_artifact_entries(
        input_artifact_manifest,
        builder_input,
        event_window_ref,
    )
    event_hash_chain = _build_event_hash_chain(builder_input.events)
    terminal_event_chain_hash = event_hash_chain[-1].chain_hash
    event_window_hash = ReplayContentHash(
        value=_hash_jsonable(
            {
                "event_window": event_window.model_dump(mode="json"),
                "terminal_event_chain_hash": terminal_event_chain_hash.value,
                "event_window_ref": event_window_ref.value,
            }
        )
    )

    replay_report = ReplayReport(
        replay_report_id=builder_input.replay_report_ref,
        project_ref=builder_input.project_ref,
        projection_kind=ReplayAttestationKind.SEAT_ASSIGNMENT_GRAPH.value,
        projection_version=builder_input.projection_version,
        event_range=event_window,
        event_count=builder_input.projection_summary.event_count,
        summary_hash=ReplaySummaryHash(value=builder_input.projection_summary.summary_hash),
        replay_passed=True,
        blockers=(),
        generated_at=builder_input.generated_at,
    )

    attestation = ReplayAttestation(
        attestation_id=ReplayAttestationRef(
            value=(
                "attestation."
                f"{builder_input.project_ref.value}."
                f"{builder_input.projection_summary.summary_hash[:12]}"
            )
        ),
        kind=ReplayAttestationKind.SEAT_ASSIGNMENT_GRAPH,
        projection_kind=ReplayAttestationKind.SEAT_ASSIGNMENT_GRAPH.value,
        project_ref=builder_input.project_ref,
        projection_version=builder_input.projection_version,
        event_window=event_window,
        event_window_hash=event_window_hash,
        payload_manifest_ref=builder_input.payload_manifest_ref,
        artifact_manifest_ref=builder_input.artifact_manifest_ref,
        hash_manifest_ref=builder_input.hash_manifest_ref,
        replay_report_ref=builder_input.replay_report_ref,
        summary_hash=ReplaySummaryHash(value=builder_input.projection_summary.summary_hash),
        replay_passed=True,
    )

    hash_manifest_input = _hash_manifest_logical_input(
        event_hash_chain=event_hash_chain,
        terminal_event_chain_hash=terminal_event_chain_hash,
        event_window_hash=event_window_hash,
        payload_manifest=payload_manifest,
        replay_report=replay_report,
        attestation=attestation,
    )
    artifact_manifest = _build_artifact_manifest(
        input_artifact_manifest=input_artifact_manifest,
        builder_input=builder_input,
        event_window=event_window,
        terminal_event_chain_hash=terminal_event_chain_hash,
        event_window_hash=event_window_hash,
        payload_manifest=payload_manifest,
        replay_report=replay_report,
        attestation=attestation,
        hash_manifest_input=hash_manifest_input,
    )

    payload_manifest_hash = ReplayContentHash(value=_hash_model(payload_manifest))
    artifact_manifest_hash = ReplayContentHash(value=_hash_model(artifact_manifest))
    replay_report_hash = ReplayContentHash(value=_hash_model(replay_report))
    attestation_hash = ReplayContentHash(value=_hash_model(attestation))
    hash_manifest = ReplayHashManifest(
        hash_manifest_id=builder_input.hash_manifest_ref,
        project_ref=builder_input.project_ref,
        event_hash_chain=event_hash_chain,
        terminal_event_chain_hash=terminal_event_chain_hash,
        event_window_hash=event_window_hash,
        payload_manifest_hash=payload_manifest_hash,
        artifact_manifest_hash=artifact_manifest_hash,
        replay_report_hash=replay_report_hash,
        attestation_hashes={attestation.attestation_id.value: attestation_hash},
    )

    checked_refs = tuple(
        dict.fromkeys(
            [
                *(event.event_id.value for event in builder_input.events),
                *(
                    payload_ref.value
                    for event in builder_input.events
                    for payload_ref in event.payload_refs
                ),
                event_window_ref.value,
                builder_input.payload_manifest_ref.value,
                builder_input.artifact_manifest_ref.value,
                builder_input.hash_manifest_ref.value,
                builder_input.replay_report_ref.value,
                builder_input.projection_summary.summary_hash,
            ]
        )
    )

    replay_bundle_id = ReplayBundleRef(
        value=(
            "replay-bundle."
            f"{builder_input.project_ref.value}."
            f"{builder_input.projection_summary.summary_hash[:12]}"
        )
    )

    return ReplayBundle(
        replay_bundle_id=replay_bundle_id,
        project_ref=builder_input.project_ref,
        generated_at=builder_input.generated_at,
        events=builder_input.events,
        attestations=(attestation,),
        payload_manifest=payload_manifest,
        hash_manifest=hash_manifest,
        artifact_manifest=artifact_manifest,
        replay_report=replay_report,
        checked_refs=checked_refs,
    )


def replay_bundle_readiness(bundle: ReplayBundle) -> ReplayBundleReadiness:
    try:
        validated_bundle = _validate_bundle_instance(bundle)
    except ValidationError as error:
        raise ReplayBundleError(str(error)) from error
    attestation = validated_bundle.attestations[0]
    _revalidate_hash_manifest(validated_bundle)
    _validate_report_alignment(validated_bundle)
    return ReplayBundleReadiness(
        replay_passed=True,
        summary_hash=attestation.summary_hash,
        event_range=_event_range_ref(
            validated_bundle.project_ref,
            attestation.event_window,
        ),
        projection_versions=(attestation.projection_version,),
        hash_chain_verified=True,
    )


def _validate_bundle_instance(bundle: ReplayBundle) -> ReplayBundle:
    if not isinstance(bundle, ReplayBundle):
        raise ReplayBundleError("bundle must be ReplayBundle")
    return ReplayBundle.model_validate(
        bundle.model_dump(mode="python", exclude={"bundle_hash"})
    )


def _validate_builder_input_instance(
    builder_input: ReplayBundleBuilderInput,
) -> ReplayBundleBuilderInput:
    return ReplayBundleBuilderInput.model_validate(
        builder_input.model_dump(
            mode="python",
            exclude={"projection_summary": {"summary_hash"}},
        )
    )


def _revalidate_hash_manifest(bundle: ReplayBundle) -> None:
    manifest = bundle.hash_manifest
    attestation = bundle.attestations[0]
    _validate_event_hash_chain_for_readiness(
        manifest,
        attestation.event_window,
        bundle.events,
    )
    if attestation.event_window_hash != manifest.event_window_hash:
        raise ReplayBundleError(
            "attestation event_window_hash must match hash manifest event_window_hash"
        )
    expected_event_window_hash = ReplayContentHash(
        value=_hash_jsonable(
            {
                "event_window": attestation.event_window.model_dump(mode="json"),
                "terminal_event_chain_hash": manifest.terminal_event_chain_hash.value,
                "event_window_ref": bundle.artifact_manifest.entries_by_kind[
                    ReplayManifestKind.EVENT_WINDOW
                ].content_ref.value,
            }
        )
    )
    if manifest.event_window_hash != expected_event_window_hash:
        raise ReplayBundleError("hash manifest mismatch: event_window_hash")
    if manifest.payload_manifest_hash.value != _hash_model(bundle.payload_manifest):
        raise ReplayBundleError("hash manifest mismatch: payload_manifest_hash")
    if manifest.artifact_manifest_hash.value != _hash_model(bundle.artifact_manifest):
        raise ReplayBundleError("hash manifest mismatch: artifact_manifest_hash")
    if manifest.replay_report_hash.value != _hash_model(bundle.replay_report):
        raise ReplayBundleError("hash manifest mismatch: replay_report_hash")
    expected_attestation_hash = _hash_model(attestation)
    actual_attestation_hash = manifest.attestation_hashes.get(attestation.attestation_id.value)
    if actual_attestation_hash is None:
        raise ReplayBundleError("hash manifest mismatch: missing attestation hash")
    if actual_attestation_hash.value != expected_attestation_hash:
        raise ReplayBundleError("hash manifest mismatch: attestation hash")
    _validate_artifact_manifest_hashes(
        bundle=bundle,
        event_window_hash=expected_event_window_hash,
        hash_manifest_input=_hash_manifest_logical_input(
            event_hash_chain=manifest.event_hash_chain,
            terminal_event_chain_hash=manifest.terminal_event_chain_hash,
            event_window_hash=manifest.event_window_hash,
            payload_manifest=bundle.payload_manifest,
            replay_report=bundle.replay_report,
            attestation=attestation,
        ),
    )


def _validate_event_hash_chain_for_readiness(
    manifest: ReplayHashManifest,
    event_window: ReplayEventWindow,
    events: tuple[EventRecord, ...],
) -> None:
    if not manifest.event_hash_chain:
        raise ReplayBundleError("event hash chain missing")
    _validate_events_against_window(events, event_window)
    if len(manifest.event_hash_chain) != event_window.event_count:
        raise ReplayBundleError("event hash chain must match event_window event_count")
    first_node = manifest.event_hash_chain[0]
    last_node = manifest.event_hash_chain[-1]
    if (
        first_node.graph_version != event_window.first_graph_version
        or first_node.event_id != event_window.first_event_id
        or last_node.graph_version != event_window.last_graph_version
        or last_node.event_id != event_window.last_event_id
    ):
        raise ReplayBundleError("event hash chain must match event_window boundaries")
    previous_graph_version: int | None = None
    previous_chain_hash = _ZERO_HASH
    seen_event_ids: set[str] = set()
    for index, node in enumerate(manifest.event_hash_chain):
        if node.event_id.value in seen_event_ids:
            raise ReplayBundleError("event hash chain event ids must be unique")
        seen_event_ids.add(node.event_id.value)
        if previous_graph_version is not None and node.graph_version != previous_graph_version + 1:
            raise ReplayBundleError("event hash chain graph_version must be contiguous")
        event = events[index]
        if node.event_id != event.event_id or node.graph_version != event.graph_version:
            raise ReplayBundleError("event hash chain must match archived EventRecord order")
        expected_event_hash = _hash_jsonable(event.model_dump(mode="json"))
        if node.event_hash.value != expected_event_hash:
            raise ReplayBundleError(
                "event hash must match canonical EventRecord hash"
            )
        expected_previous = _ZERO_HASH if index == 0 else previous_chain_hash
        if node.previous_hash.value != expected_previous:
            raise ReplayBundleError("event hash chain previous_hash mismatch")
        expected_chain = _sha256_text(node.previous_hash.value + node.event_hash.value)
        if node.chain_hash.value != expected_chain:
            raise ReplayBundleError("event hash chain chain_hash mismatch")
        previous_graph_version = node.graph_version
        previous_chain_hash = node.chain_hash.value
    if manifest.terminal_event_chain_hash != manifest.event_hash_chain[-1].chain_hash:
        raise ReplayBundleError("event hash chain terminal hash mismatch")



def _validate_artifact_manifest_hashes(
    *,
    bundle: ReplayBundle,
    event_window_hash: ReplayContentHash,
    hash_manifest_input: dict[str, Any],
) -> None:
    expected_hashes = _expected_artifact_entry_hashes(
        artifact_manifest=bundle.artifact_manifest,
        event_window_hash=event_window_hash,
        payload_manifest=bundle.payload_manifest,
        replay_report=bundle.replay_report,
        attestation=bundle.attestations[0],
        hash_manifest_input=hash_manifest_input,
    )
    expected_content_ref_values = {
        ReplayManifestKind.EVENT_WINDOW: _event_range_ref(
            bundle.project_ref,
            bundle.attestations[0].event_window,
        ).value,
        ReplayManifestKind.PAYLOAD_MANIFEST: bundle.payload_manifest.payload_manifest_id.value,
        ReplayManifestKind.ARTIFACT_MANIFEST: bundle.artifact_manifest.artifact_manifest_id.value,
        ReplayManifestKind.HASH_MANIFEST: bundle.hash_manifest.hash_manifest_id.value,
        ReplayManifestKind.REPLAY_REPORT: bundle.replay_report.replay_report_id.value,
    }
    missing_kinds = set(expected_hashes) - {entry.kind for entry in bundle.artifact_manifest.entries}
    if missing_kinds:
        missing = ",".join(sorted(kind.value for kind in missing_kinds))
        raise ReplayBundleError(f"artifact manifest missing required kind: {missing}")
    for entry in bundle.artifact_manifest.entries:
        expected_ref = expected_content_ref_values[entry.kind]
        if entry.content_ref.value != expected_ref:
            raise ReplayBundleError(f"artifact manifest content ref mismatch: {entry.kind.value}")
        expected_hash = expected_hashes[entry.kind]
        if entry.sha256.value != expected_hash:
            raise ReplayBundleError(f"artifact manifest hash mismatch: {entry.kind.value}")



def _validate_report_alignment(bundle: ReplayBundle) -> None:
    attestation = bundle.attestations[0]
    report = bundle.replay_report
    if report.projection_version != attestation.projection_version:
        raise ReplayBundleError("projection version mismatch")
    if report.summary_hash != attestation.summary_hash:
        raise ReplayBundleError("replay report summary_hash mismatch")
    if report.event_range != attestation.event_window:
        raise ReplayBundleError("replay report event_range mismatch")
    if report.projection_kind != attestation.projection_kind:
        raise ReplayBundleError("replay report projection_kind mismatch")


def _build_event_hash_chain(events: tuple[EventRecord, ...]) -> tuple[ReplayEventHashNode, ...]:
    chain: list[ReplayEventHashNode] = []
    previous_hash = _ZERO_HASH
    previous_graph_version: int | None = None
    for event in events:
        if previous_graph_version is not None and event.graph_version != previous_graph_version + 1:
            raise ReplayBundleError("event hash chain requires contiguous graph_version")
        event_hash = ReplayContentHash(value=_hash_jsonable(event.model_dump(mode="json")))
        chain_hash = ReplayContentHash(value=_sha256_text(previous_hash + event_hash.value))
        chain.append(
            ReplayEventHashNode(
                event_id=event.event_id,
                graph_version=event.graph_version,
                event_hash=event_hash,
                previous_hash=ReplayPreviousHash(value=previous_hash),
                chain_hash=chain_hash,
            )
        )
        previous_hash = chain_hash.value
        previous_graph_version = event.graph_version
    return tuple(chain)


def _validate_events_against_window(
    events: tuple[EventRecord, ...],
    event_window: ReplayEventWindow,
) -> None:
    if len(events) != event_window.event_count:
        raise ReplayBundleError("events must match event_window event_count")
    if not events:
        raise ReplayBundleError("events must not be empty")
    if (
        events[0].event_id != event_window.first_event_id
        or events[0].graph_version != event_window.first_graph_version
        or events[-1].event_id != event_window.last_event_id
        or events[-1].graph_version != event_window.last_graph_version
    ):
        raise ReplayBundleError("events must match event_window boundaries")
    previous_graph_version: int | None = None
    for event in events:
        if event.project_ref != event_window.project_ref:
            raise ReplayBundleError("events project_ref must match event_window")
        if previous_graph_version is not None and event.graph_version != previous_graph_version + 1:
            raise ReplayBundleError("events graph_version must be contiguous")
        previous_graph_version = event.graph_version



def _validate_payload_manifest_coverage(
    events: tuple[EventRecord, ...],
    payload_manifest: ReplayPayloadManifest,
) -> None:
    expected_payload_refs = {
        payload_ref.value for event in events for payload_ref in event.payload_refs
    }
    actual_payload_refs = {entry.content_ref.value for entry in payload_manifest.entries}
    if expected_payload_refs != actual_payload_refs:
        raise ReplayBundleError("payload manifest must cover every event payload ref")


def _validate_required_artifact_entries(
    artifact_manifest: ReplayArtifactManifest,
    builder_input: ReplayBundleBuilderInput,
    expected_event_window_ref: EventRangeRef,
) -> None:
    entries_by_kind = artifact_manifest.entries_by_kind
    required_kinds = {
        ReplayManifestKind.EVENT_WINDOW: expected_event_window_ref.value,
        ReplayManifestKind.PAYLOAD_MANIFEST: builder_input.payload_manifest_ref.value,
        ReplayManifestKind.ARTIFACT_MANIFEST: builder_input.artifact_manifest_ref.value,
        ReplayManifestKind.HASH_MANIFEST: builder_input.hash_manifest_ref.value,
        ReplayManifestKind.REPLAY_REPORT: builder_input.replay_report_ref.value,
    }
    for kind, expected_ref in required_kinds.items():
        entry = entries_by_kind.get(kind)
        if entry is None:
            raise ReplayBundleError("artifact manifest missing required hash entry")
        if entry.content_ref.value != expected_ref:
            raise ReplayBundleError("artifact manifest content ref mismatch")



def _build_artifact_manifest(
    *,
    input_artifact_manifest: ReplayArtifactManifest,
    builder_input: ReplayBundleBuilderInput,
    event_window: ReplayEventWindow,
    terminal_event_chain_hash: ReplayContentHash,
    event_window_hash: ReplayContentHash,
    payload_manifest: ReplayPayloadManifest,
    replay_report: ReplayReport,
    attestation: ReplayAttestation,
    hash_manifest_input: dict[str, Any],
) -> ReplayArtifactManifest:
    expected_hashes = _expected_artifact_entry_hashes(
        artifact_manifest=input_artifact_manifest,
        event_window_hash=event_window_hash,
        payload_manifest=payload_manifest,
        replay_report=replay_report,
        attestation=attestation,
        hash_manifest_input=hash_manifest_input,
    )
    return ReplayArtifactManifest(
        artifact_manifest_id=builder_input.artifact_manifest_ref,
        project_ref=builder_input.project_ref,
        entries=tuple(
            ReplayArtifactManifestEntry(
                manifest_ref=entry.manifest_ref,
                kind=entry.kind,
                content_ref=entry.content_ref,
                sha256=expected_hashes[entry.kind],
            )
            for entry in input_artifact_manifest.entries
        ),
    )



def _expected_artifact_entry_hashes(
    *,
    artifact_manifest: ReplayArtifactManifest,
    event_window_hash: ReplayContentHash,
    payload_manifest: ReplayPayloadManifest,
    replay_report: ReplayReport,
    attestation: ReplayAttestation,
    hash_manifest_input: dict[str, Any],
) -> dict[ReplayManifestKind, str]:
    return {
        ReplayManifestKind.EVENT_WINDOW: _hash_jsonable(
            {
                "event_window": attestation.event_window.model_dump(mode="json"),
                "event_window_hash": event_window_hash.value,
            }
        ),
        ReplayManifestKind.PAYLOAD_MANIFEST: _hash_model(payload_manifest),
        ReplayManifestKind.ARTIFACT_MANIFEST: _artifact_manifest_structure_hash(
            artifact_manifest
        ),
        ReplayManifestKind.HASH_MANIFEST: _hash_jsonable(hash_manifest_input),
        ReplayManifestKind.REPLAY_REPORT: _hash_model(replay_report),
    }



def _artifact_manifest_structure_hash(artifact_manifest: ReplayArtifactManifest) -> str:
    return _hash_jsonable(
        {
            "artifact_manifest_id": artifact_manifest.artifact_manifest_id.model_dump(mode="json"),
            "project_ref": artifact_manifest.project_ref.model_dump(mode="json"),
            "entries": [
                entry.model_dump(mode="json", exclude={"sha256"})
                for entry in artifact_manifest.entries
            ],
        }
    )



def _hash_manifest_logical_input(
    *,
    event_hash_chain: tuple[ReplayEventHashNode, ...],
    terminal_event_chain_hash: ReplayContentHash,
    event_window_hash: ReplayContentHash,
    payload_manifest: ReplayPayloadManifest,
    replay_report: ReplayReport,
    attestation: ReplayAttestation,
) -> dict[str, Any]:
    return {
        "event_hash_chain": [node.model_dump(mode="json") for node in event_hash_chain],
        "terminal_event_chain_hash": terminal_event_chain_hash.model_dump(mode="json"),
        "event_window_hash": event_window_hash.model_dump(mode="json"),
        "payload_manifest_hash": _hash_model(payload_manifest),
        "replay_report_hash": _hash_model(replay_report),
        "attestation_hashes": {
            attestation.attestation_id.value: _hash_model(attestation),
        },
    }



def _projection_version_for_kind(projection_kind: str) -> str:
    if projection_kind == ReplayAttestationKind.SEAT_ASSIGNMENT_GRAPH.value:
        return "projection.seat_assignment_graph.v1"
    raise ReplayBundleError("projection kind mismatch")



def _event_range_ref(
    project_ref: ProjectRef,
    event_window: ReplayEventWindow,
) -> EventRangeRef:
    return EventRangeRef(
        value=(
            "event-range."
            f"{project_ref.value}."
            f"{event_window.first_graph_version}-{event_window.last_graph_version}"
        )
    )



def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _hash_jsonable(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _hash_model(model: BaseModel) -> str:
    return _hash_jsonable(model.model_dump(mode="json"))


__all__ = [
    "ReplayArtifactManifest",
    "ReplayArtifactManifestEntry",
    "ReplayAttestation",
    "ReplayAttestationKind",
    "ReplayBundle",
    "ReplayBundleBuilderInput",
    "ReplayBundleError",
    "ReplayBundleRef",
    "ReplayContentHash",
    "ReplayPreviousHash",
    "ReplayEventHashNode",
    "ReplayEventWindow",
    "ReplayHashManifest",
    "ReplayManifestEntry",
    "ReplayManifestKind",
    "ReplayPayloadManifest",
    "ReplayReport",
    "build_replay_bundle",
    "replay_bundle_readiness",
]
