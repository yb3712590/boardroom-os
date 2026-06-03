from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from enum import StrEnum
from typing import Any, Iterable, Literal, Mapping, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    SkipValidation,
    ValidationError,
    computed_field,
    field_serializer,
    field_validator,
    model_validator,
)

from boardroom_os.agents.skills import _normalize_ref_fields
from boardroom_os.checker.verdict import CheckerVerdict
from boardroom_os.closeout.closure import (
    CloseoutClosureError,
    assert_source_inventory_evidence_refs_resolve,
)
from boardroom_os.closeout.gate import (
    GitAuditReadiness,
    ProcessAuditArtifactPath,
    ProcessAuditReadiness,
    ReplayBundleReadiness,
)
from boardroom_os.contracts.acceptance import AcceptanceContract
from boardroom_os.contracts.package import PackageContract
from boardroom_os.contracts.refs import (
    NamespacedRefError,
    assert_namespace_segment,
    assert_namespaced_ref_binding,
    canonical_sort_for_hash,
    namespaced_ref,
)
from boardroom_os.contracts.types import NonEmptyTextValue
from boardroom_os.evidence.table import FinalEvidenceTable
from boardroom_os.evidence.verifier import VerifiedEvidence
from boardroom_os.evidence.live_blackbox import LiveBlackboxIntegrationEvidence
from boardroom_os.evidence.service_run import ServiceRunEvidence
from boardroom_os.events.record import EventRecord
from boardroom_os.events.types import EventType, ProjectRef
from boardroom_os.execution.context_index import AgentContextIndex, ProviderAttemptRef
from boardroom_os.execution.verification_run import VerificationRun, VerificationRunStatus
from boardroom_os.workspace.evidence_export import WorkspaceEvidenceBundle
from boardroom_os.workspace.run_manifest import RunManifest
from boardroom_os.workspace.source_inventory import SourceInventory
from boardroom_os.audit.git_version_audit import (
    GitVersionAuditBundle,
    git_version_audit_readiness,
    source_inventory_hash,
)
from boardroom_os.audit.replay_bundle import ReplayBundle

_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")

REQUIRED_PROCESS_AUDIT_ARTIFACT_PATHS = (
    "30-audit/process-audit.md",
    "30-audit/timeline.json",
    "30-audit/decision-log.md",
    "30-audit/agent-context-index.json",
    "30-audit/ticket-graph.md",
    "30-audit/artifact-lineage.json",
    "30-audit/evidence-map.json",
    "30-audit/git-version-audit.md",
    "30-audit/closeout-summary.md",
    "30-audit/replay-bundle-report.json",
)

_REQUIRED_PATH_SET = set(REQUIRED_PROCESS_AUDIT_ARTIFACT_PATHS)
_REQUIRED_TIMELINE_EVENT_KINDS = {
    "seat_assigned",
    "ticket_created",
    "ticket_started",
    "provider_attempt_recorded",
    "work_product_submitted",
    "command_run_recorded",
}
_EVENT_TYPE_TO_TIMELINE_KIND: dict[EventType, str] = {
    EventType.TICKET_CREATED: "ticket_created",
    EventType.TICKET_LEASED: "ticket_started",
    EventType.SEAT_ASSIGNED: "seat_assigned",
    EventType.PROVIDER_ATTEMPT_RECORDED: "provider_attempt_recorded",
    EventType.WORK_PRODUCT_SUBMITTED: "work_product_submitted",
    EventType.COMMAND_RUN_RECORDED: "command_run_recorded",
}
_LINEAGE_REQUIRED_FIELDS = {
    "path",
    "sha256",
    "source_surface_ref",
    "producer_ticket_ref",
    "producer_attempt_ref",
    "consumer_ticket_refs",
    "acceptance_refs",
    "evidence_refs",
    "evidence_bindings",
    "evidence_map_ref",
    "final_evidence_table_ref",
}
_LINEAGE_EVIDENCE_BINDING_REQUIRED_FIELDS = {
    "evidence_claim_ref",
    "verified_evidence_ref",
    "verifier_ref",
    "verification_run_ref",
    "service_run_refs",
    "live_blackbox_evidence_refs",
    "run_manifest_ref",
}
_LINEAGE_EVIDENCE_BINDING_REQUIRED_TEXT_FIELDS = {
    "evidence_claim_ref",
    "verified_evidence_ref",
    "verifier_ref",
    "run_manifest_ref",
}
_FALLBACK_LINEAGE_REQUIRED_FIELDS = {
    "fallback_decision_record_ref",
    "fallback_decision_recorded_ref",
    "verifier_ref",
    "evidence_map_ref",
}
_FALLBACK_LINEAGE_REQUIRED_NONEMPTY_FIELDS = _FALLBACK_LINEAGE_REQUIRED_FIELDS - {
    "fallback_decision_recorded_ref"
}


class ProcessAuditError(ValueError):
    pass


class ProcessAuditBundleRef(NonEmptyTextValue):
    pass


class ProcessAuditReportRef(NonEmptyTextValue):
    pass


class ProcessAuditArtifactRef(NonEmptyTextValue):
    pass


class ProcessAuditManifestRef(NonEmptyTextValue):
    pass


class ProcessAuditContentRef(NonEmptyTextValue):
    pass


class ProcessAuditContentHash(NonEmptyTextValue):
    @field_validator("value")
    @classmethod
    def _require_lowercase_sha256(cls, value: str) -> str:
        if not _SHA256_PATTERN.fullmatch(value):
            raise ValueError("sha256 must be a 64-character lowercase hex digest")
        if len(set(value)) == 1:
            raise ValueError("sha256 must not be a placeholder or synthetic digest")
        return value


class ProcessAuditCheckedRef(NonEmptyTextValue):
    pass


class ProcessAuditArtifactKind(StrEnum):
    PROCESS_AUDIT = "process_audit"
    TIMELINE = "timeline"
    DECISION_LOG = "decision_log"
    AGENT_CONTEXT_INDEX = "agent_context_index"
    TICKET_GRAPH = "ticket_graph"
    ARTIFACT_LINEAGE = "artifact_lineage"
    EVIDENCE_MAP = "evidence_map"
    GIT_VERSION_AUDIT = "git_version_audit"
    CLOSEOUT_SUMMARY = "closeout_summary"
    REPLAY_BUNDLE_REPORT = "replay_bundle_report"


class ProcessAuditArtifactFormat(StrEnum):
    MARKDOWN = "markdown"
    JSON = "json"


_PATH_KIND_FORMAT: dict[str, tuple[ProcessAuditArtifactKind, ProcessAuditArtifactFormat]] = {
    "30-audit/process-audit.md": (
        ProcessAuditArtifactKind.PROCESS_AUDIT,
        ProcessAuditArtifactFormat.MARKDOWN,
    ),
    "30-audit/timeline.json": (
        ProcessAuditArtifactKind.TIMELINE,
        ProcessAuditArtifactFormat.JSON,
    ),
    "30-audit/decision-log.md": (
        ProcessAuditArtifactKind.DECISION_LOG,
        ProcessAuditArtifactFormat.MARKDOWN,
    ),
    "30-audit/agent-context-index.json": (
        ProcessAuditArtifactKind.AGENT_CONTEXT_INDEX,
        ProcessAuditArtifactFormat.JSON,
    ),
    "30-audit/ticket-graph.md": (
        ProcessAuditArtifactKind.TICKET_GRAPH,
        ProcessAuditArtifactFormat.MARKDOWN,
    ),
    "30-audit/artifact-lineage.json": (
        ProcessAuditArtifactKind.ARTIFACT_LINEAGE,
        ProcessAuditArtifactFormat.JSON,
    ),
    "30-audit/evidence-map.json": (
        ProcessAuditArtifactKind.EVIDENCE_MAP,
        ProcessAuditArtifactFormat.JSON,
    ),
    "30-audit/git-version-audit.md": (
        ProcessAuditArtifactKind.GIT_VERSION_AUDIT,
        ProcessAuditArtifactFormat.MARKDOWN,
    ),
    "30-audit/closeout-summary.md": (
        ProcessAuditArtifactKind.CLOSEOUT_SUMMARY,
        ProcessAuditArtifactFormat.MARKDOWN,
    ),
    "30-audit/replay-bundle-report.json": (
        ProcessAuditArtifactKind.REPLAY_BUNDLE_REPORT,
        ProcessAuditArtifactFormat.JSON,
    ),
}

_KIND_PATH = {kind: path for path, (kind, _format) in _PATH_KIND_FORMAT.items()}


def _canonical_jsonable(value: Any) -> Any:
    if isinstance(value, BaseModel):
        field_names = tuple(type(value).model_fields)
        if field_names == ("value",):
            return value.value
        return value.model_dump(mode="json")
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, tuple | list):
        return [_canonical_jsonable(item) for item in value]
    if isinstance(value, Mapping):
        return {str(key): _canonical_jsonable(item) for key, item in value.items()}
    return value


def _hash_jsonable(value: Any) -> str:
    encoded = json.dumps(
        _canonical_jsonable(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _hash_content(content: Any, artifact_format: ProcessAuditArtifactFormat) -> str:
    if artifact_format is ProcessAuditArtifactFormat.MARKDOWN:
        return _sha256_text(str(content))
    return _hash_jsonable(content)


def _hash_model(model: BaseModel) -> str:
    return _hash_jsonable(model.model_dump(mode="json"))


def _reject_unsafe_ref(value: str, *, field_name: str) -> str:
    if (
        value.startswith("/")
        or "\\" in value
        or re.match(r"^[A-Za-z]:", value)
        or value in {".", ".."}
        or value.endswith("/")
        or value.endswith("/.")
        or value.endswith("/..")
        or value.startswith("./")
        or value.startswith("../")
        or "/./" in value
        or "/../" in value
    ):
        raise ProcessAuditError(f"{field_name} must be audit-friendly relative path/ref")
    return value


def _validate_artifact_path_value(value: str) -> str:
    _reject_unsafe_ref(value, field_name="artifact path")
    if not value.startswith("30-audit/"):
        raise ProcessAuditError("artifact path must be under 30-audit")
    if value not in _REQUIRED_PATH_SET:
        raise ProcessAuditError("artifact path must be a required process audit path")
    return value


def _ref_value(value: Any) -> str:
    if isinstance(value, BaseModel) and tuple(type(value).model_fields) == ("value",):
        return str(value.value)
    if hasattr(value, "value"):
        return str(value.value)
    return str(value)


def _unique_strings(values: tuple[str, ...], *, field_name: str) -> tuple[str, ...]:
    normalized = tuple(value.strip() for value in values)
    if not normalized:
        raise ProcessAuditError(f"{field_name} must not be empty")
    if any(not value for value in normalized):
        raise ProcessAuditError(f"{field_name} must not contain empty values")
    if len(set(normalized)) != len(normalized):
        raise ProcessAuditError(f"{field_name} must be unique")
    return normalized


def _required_attr(value: Any, attr_name: str, *, context: str) -> Any:
    if not hasattr(value, attr_name):
        raise ProcessAuditError(f"{context} missing {attr_name}")
    attr_value = getattr(value, attr_name)
    if attr_value is None:
        raise ProcessAuditError(f"{context} missing {attr_name}")
    return attr_value


def _required_nonempty_iterable_attr(value: Any, attr_name: str, *, context: str) -> tuple[Any, ...]:
    attr_value = _required_attr(value, attr_name, context=context)
    if isinstance(attr_value, str | bytes | Mapping):
        raise ProcessAuditError(f"{context} missing {attr_name}")
    try:
        resolved = tuple(attr_value)
    except TypeError as error:
        raise ProcessAuditError(f"{context} missing {attr_name}") from error
    if not resolved:
        raise ProcessAuditError(f"{context} missing {attr_name}")
    return resolved


_SOURCE_INVENTORY_ENTRY_LINEAGE_FIELDS = (
    "path",
    "sha256",
    "source_surface_ref",
    "producer_ticket_ref",
    "producer_attempt_ref",
    "consumer_ticket_refs",
    "acceptance_refs",
    "evidence_refs",
)


def _source_inventory_entry_lineage_attrs(entry: Any) -> dict[str, Any]:
    return {
        field_name: _required_attr(
            entry,
            field_name,
            context="source inventory entry",
        )
        for field_name in _SOURCE_INVENTORY_ENTRY_LINEAGE_FIELDS
    }


def _validate_source_inventory_entry_lineage_fields(builder_input: ProcessAuditBuilderInput) -> None:
    expected_provider_refs = {ref.value for ref in builder_input.provider_attempt_refs}
    actual_provider_refs: set[str] = set()
    for entry in getattr(builder_input.source_inventory, "entries", ()):
        attrs = _source_inventory_entry_lineage_attrs(entry)
        actual_provider_refs.add(_ref_value(attrs["producer_attempt_ref"]))
    if not actual_provider_refs.issubset(expected_provider_refs):
        raise ProcessAuditError(
            "source inventory producer_attempt_refs mismatch: "
            f"extra={sorted(actual_provider_refs - expected_provider_refs)}"
        )


def _validate_source_inventory_consumer_ticket_closure(
    builder_input: ProcessAuditBuilderInput,
) -> None:
    tickets_by_ref = {
        _ref_value(_required_attr(ticket, "ticket_ref", context="ticket graph summary ticket")): ticket
        for ticket in _ticket_graph_summary_tickets(builder_input.ticket_graph_summary)
    }
    for entry in builder_input.source_inventory.entries:
        attrs = _source_inventory_entry_lineage_attrs(entry)
        source_surface_ref = _ref_value(attrs["source_surface_ref"])
        acceptance_refs = {_ref_value(ref) for ref in attrs["acceptance_refs"]}
        for consumer_ticket_ref in attrs["consumer_ticket_refs"]:
            ticket_ref = _ref_value(consumer_ticket_ref)
            ticket = tickets_by_ref.get(ticket_ref)
            if ticket is None:
                raise ProcessAuditError(
                    "source inventory consumer_ticket_refs outside ticket scope"
                )
            ticket_surface_refs = {
                _ref_value(ref)
                for ref in _required_nonempty_iterable_attr(
                    ticket,
                    "source_surface_refs",
                    context="ticket graph summary ticket",
                )
            }
            ticket_acceptance_refs = {
                _ref_value(ref)
                for ref in _required_nonempty_iterable_attr(
                    ticket,
                    "acceptance_refs",
                    context="ticket graph summary ticket",
                )
            }
            if (
                source_surface_ref not in ticket_surface_refs
                or not acceptance_refs.issubset(ticket_acceptance_refs)
            ):
                raise ProcessAuditError(
                    "source inventory consumer_ticket_refs outside ticket scope"
                )


class ProcessAuditArtifact(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    artifact_id: ProcessAuditArtifactRef
    path: ProcessAuditArtifactPath
    kind: ProcessAuditArtifactKind
    format: ProcessAuditArtifactFormat
    content_ref: ProcessAuditContentRef
    content: Any
    sha256: ProcessAuditContentHash
    source_refs: tuple[str, ...]

    @model_validator(mode="before")
    @classmethod
    def _normalize_refs(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        if "source_refs" in data and not isinstance(data["source_refs"], list | tuple):
            raise ProcessAuditError("source_refs must be a tuple or list")
        return _normalize_ref_fields(
            data,
            {
                "artifact_id": ProcessAuditArtifactRef,
                "path": ProcessAuditArtifactPath,
                "content_ref": ProcessAuditContentRef,
                "sha256": ProcessAuditContentHash,
            },
        )

    @field_validator("content_ref")
    @classmethod
    def _reject_unsafe_content_ref(
        cls, value: ProcessAuditContentRef
    ) -> ProcessAuditContentRef:
        _reject_unsafe_ref(value.value, field_name="content_ref")
        return value

    @field_validator("source_refs")
    @classmethod
    def _validate_source_refs(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        return _unique_strings(values, field_name="source_refs")

    @model_validator(mode="after")
    def _validate_artifact(self) -> Self:
        _validate_artifact_path_value(self.path.value)
        expected = _PATH_KIND_FORMAT[self.path.value]
        if self.kind is not expected[0]:
            raise ProcessAuditError("artifact kind must match artifact path")
        if self.format is not expected[1]:
            raise ProcessAuditError("artifact format must match artifact path suffix")
        if self.content is None:
            raise ProcessAuditError("artifact content must not be empty")
        if isinstance(self.content, str) and not self.content.strip():
            raise ProcessAuditError("artifact content must not be empty")
        expected_hash = _hash_content(self.content, self.format)
        if self.sha256.value != expected_hash:
            raise ProcessAuditError("artifact sha256 must match canonical content")
        return self

    @field_serializer("kind")
    def _serialize_kind(self, value: ProcessAuditArtifactKind) -> str:
        return value.value

    @field_serializer("format")
    def _serialize_format(self, value: ProcessAuditArtifactFormat) -> str:
        return value.value


class ProcessAuditArtifactManifestEntry(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    artifact_ref: ProcessAuditArtifactRef
    path: ProcessAuditArtifactPath
    kind: ProcessAuditArtifactKind
    format: ProcessAuditArtifactFormat
    content_ref: ProcessAuditContentRef
    sha256: ProcessAuditContentHash

    @model_validator(mode="before")
    @classmethod
    def _normalize_refs(cls, data: Any) -> Any:
        return _normalize_ref_fields(
            data,
            {
                "artifact_ref": ProcessAuditArtifactRef,
                "path": ProcessAuditArtifactPath,
                "content_ref": ProcessAuditContentRef,
                "sha256": ProcessAuditContentHash,
            },
        )

    @model_validator(mode="after")
    def _validate_entry(self) -> Self:
        _validate_artifact_path_value(self.path.value)
        expected = _PATH_KIND_FORMAT[self.path.value]
        if self.kind is not expected[0]:
            raise ProcessAuditError("artifact manifest kind must match path")
        if self.format is not expected[1]:
            raise ProcessAuditError("artifact manifest format must match path")
        _reject_unsafe_ref(self.content_ref.value, field_name="content_ref")
        return self

    @field_serializer("kind")
    def _serialize_kind(self, value: ProcessAuditArtifactKind) -> str:
        return value.value

    @field_serializer("format")
    def _serialize_format(self, value: ProcessAuditArtifactFormat) -> str:
        return value.value


class ProcessAuditArtifactManifest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    artifact_manifest_id: ProcessAuditManifestRef
    project_ref: ProjectRef
    entries: tuple[ProcessAuditArtifactManifestEntry, ...]

    @model_validator(mode="before")
    @classmethod
    def _normalize_refs(cls, data: Any) -> Any:
        if isinstance(data, dict) and "entries" in data and not isinstance(
            data["entries"], list | tuple
        ):
            raise ProcessAuditError("artifact manifest entries must be a tuple or list")
        return _normalize_ref_fields(
            data,
            {
                "artifact_manifest_id": ProcessAuditManifestRef,
                "project_ref": ProjectRef,
            },
        )

    @field_validator("entries")
    @classmethod
    def _validate_entries(
        cls, values: tuple[ProcessAuditArtifactManifestEntry, ...]
    ) -> tuple[ProcessAuditArtifactManifestEntry, ...]:
        if len(values) != len(REQUIRED_PROCESS_AUDIT_ARTIFACT_PATHS):
            raise ProcessAuditError("artifact manifest must cover required process audit artifacts")
        paths = [entry.path.value for entry in values]
        if set(paths) != _REQUIRED_PATH_SET:
            raise ProcessAuditError("artifact manifest paths must match required process audit artifacts")
        if len(set(paths)) != len(paths):
            raise ProcessAuditError("artifact manifest paths must be unique")
        artifact_refs = [entry.artifact_ref.value for entry in values]
        content_refs = [entry.content_ref.value for entry in values]
        if len(set(artifact_refs)) != len(artifact_refs):
            raise ProcessAuditError("artifact manifest artifact refs must be unique")
        if len(set(content_refs)) != len(content_refs):
            raise ProcessAuditError("artifact manifest content refs must be unique")
        return values

    @property
    def entries_by_path(self) -> dict[str, ProcessAuditArtifactManifestEntry]:
        return {entry.path.value: entry for entry in self.entries}


class ProcessAuditHashManifest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    hash_manifest_id: ProcessAuditManifestRef
    project_ref: ProjectRef
    artifact_hashes: dict[str, ProcessAuditContentHash]
    artifact_manifest_hash: ProcessAuditContentHash
    process_audit_report_hash: ProcessAuditContentHash
    bundle_payload_hash: ProcessAuditContentHash

    @model_validator(mode="before")
    @classmethod
    def _normalize_refs(cls, data: Any) -> Any:
        normalized = _normalize_ref_fields(
            data,
            {
                "hash_manifest_id": ProcessAuditManifestRef,
                "project_ref": ProjectRef,
                "artifact_manifest_hash": ProcessAuditContentHash,
                "process_audit_report_hash": ProcessAuditContentHash,
                "bundle_payload_hash": ProcessAuditContentHash,
            },
        )
        if isinstance(normalized, dict) and "artifact_hashes" in normalized:
            try:
                normalized = dict(normalized)
                normalized["artifact_hashes"] = {
                    path: _process_audit_content_hash(value)
                    for path, value in normalized["artifact_hashes"].items()
                }
            except (TypeError, ValueError, ValidationError) as error:
                raise ProcessAuditError("hash manifest artifact hash invalid") from error
        return normalized

    @field_validator("artifact_hashes")
    @classmethod
    def _validate_artifact_hashes(
        cls, values: dict[str, ProcessAuditContentHash]
    ) -> dict[str, ProcessAuditContentHash]:
        if set(values) != _REQUIRED_PATH_SET:
            raise ProcessAuditError("hash manifest artifact hashes must cover required paths")
        for path in values:
            _validate_artifact_path_value(path)
        return dict(values)


def _process_audit_content_hash(value: Any) -> ProcessAuditContentHash:
    if isinstance(value, ProcessAuditContentHash):
        return value
    if isinstance(value, dict):
        return ProcessAuditContentHash.model_validate(value)
    return ProcessAuditContentHash(value=value)


class ProcessAuditReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    process_audit_report_id: ProcessAuditReportRef
    project_ref: ProjectRef
    generated_at: datetime
    process_audit_ref: ProcessAuditArtifactRef
    timeline_ref: ProcessAuditArtifactRef
    decision_log_ref: ProcessAuditArtifactRef
    agent_context_index_ref: ProcessAuditArtifactRef
    ticket_graph_ref: ProcessAuditArtifactRef
    artifact_lineage_ref: ProcessAuditArtifactRef
    evidence_map_ref: ProcessAuditArtifactRef
    git_audit_ref: ProcessAuditArtifactRef
    closeout_summary_ref: ProcessAuditArtifactRef
    replay_bundle_report_ref: ProcessAuditArtifactRef
    checked_refs: tuple[str, ...]
    expected_evidence_map_rows: tuple[dict[str, Any], ...]
    expected_artifact_lineage_rows: tuple[dict[str, Any], ...]
    expected_fallback_lineage_rows: tuple[dict[str, Any], ...] = ()
    expected_fallback_decision_refs: tuple[str, ...] = ()
    replay_summary_hash: str
    replay_projection_versions: tuple[str, ...]

    @model_validator(mode="before")
    @classmethod
    def _normalize_refs(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        for field_name in (
            "checked_refs",
            "expected_evidence_map_rows",
            "expected_artifact_lineage_rows",
            "expected_fallback_lineage_rows",
            "expected_fallback_decision_refs",
            "replay_projection_versions",
        ):
            if field_name in data and not isinstance(data[field_name], list | tuple):
                raise ProcessAuditError(f"{field_name} must be a tuple or list")
        return _normalize_ref_fields(
            data,
            {
                "process_audit_report_id": ProcessAuditReportRef,
                "project_ref": ProjectRef,
                "process_audit_ref": ProcessAuditArtifactRef,
                "timeline_ref": ProcessAuditArtifactRef,
                "decision_log_ref": ProcessAuditArtifactRef,
                "agent_context_index_ref": ProcessAuditArtifactRef,
                "ticket_graph_ref": ProcessAuditArtifactRef,
                "artifact_lineage_ref": ProcessAuditArtifactRef,
                "evidence_map_ref": ProcessAuditArtifactRef,
                "git_audit_ref": ProcessAuditArtifactRef,
                "closeout_summary_ref": ProcessAuditArtifactRef,
                "replay_bundle_report_ref": ProcessAuditArtifactRef,
            },
        )

    @field_validator("generated_at")
    @classmethod
    def _require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ProcessAuditError("generated_at must include timezone")
        return value

    @field_validator("checked_refs", "replay_projection_versions")
    @classmethod
    def _validate_required_unique_strings(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        return _unique_strings(values, field_name="report refs")

    @field_validator("expected_fallback_decision_refs")
    @classmethod
    def _validate_optional_unique_strings(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(value.strip() for value in values)
        if any(not value for value in normalized):
            raise ProcessAuditError("fallback decision refs must not contain empty values")
        if len(set(normalized)) != len(normalized):
            raise ProcessAuditError("fallback decision refs must be unique")
        return normalized

    @field_validator("expected_evidence_map_rows")
    @classmethod
    def _validate_expected_evidence_map_rows(
        cls, values: tuple[dict[str, Any], ...]
    ) -> tuple[dict[str, Any], ...]:
        if not values:
            raise ProcessAuditError("expected evidence map rows must not be empty")
        return values

    @field_validator("expected_artifact_lineage_rows")
    @classmethod
    def _validate_expected_artifact_lineage_rows(
        cls, values: tuple[dict[str, Any], ...]
    ) -> tuple[dict[str, Any], ...]:
        if not values:
            raise ProcessAuditError("expected artifact lineage rows must not be empty")
        return values

    @field_validator("expected_fallback_lineage_rows")
    @classmethod
    def _validate_expected_fallback_lineage_rows(
        cls, values: tuple[dict[str, Any], ...]
    ) -> tuple[dict[str, Any], ...]:
        return values

    @field_validator("replay_summary_hash")
    @classmethod
    def _validate_replay_summary_hash(cls, value: str) -> str:
        if not _SHA256_PATTERN.fullmatch(value):
            raise ProcessAuditError("replay summary_hash must be a sha256 digest")
        return value


class ProcessAuditBundle(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    version: Literal[1] = 1
    process_audit_bundle_id: ProcessAuditBundleRef
    project_ref: ProjectRef
    generated_at: datetime
    artifacts: tuple[ProcessAuditArtifact, ...]
    artifact_manifest: ProcessAuditArtifactManifest
    hash_manifest: ProcessAuditHashManifest
    process_audit_report: ProcessAuditReport
    checked_refs: tuple[str, ...]

    @model_validator(mode="before")
    @classmethod
    def _normalize_refs(cls, data: Any) -> Any:
        if isinstance(data, dict):
            for field_name in ("artifacts", "checked_refs"):
                if field_name in data and not isinstance(data[field_name], list | tuple):
                    raise ProcessAuditError(f"{field_name} must be a tuple or list")
        return _normalize_ref_fields(
            data,
            {
                "process_audit_bundle_id": ProcessAuditBundleRef,
                "project_ref": ProjectRef,
            },
        )

    @field_validator("generated_at")
    @classmethod
    def _require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ProcessAuditError("generated_at must include timezone")
        return value

    @field_validator("checked_refs")
    @classmethod
    def _validate_checked_refs(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        return _unique_strings(values, field_name="checked_refs")

    @model_validator(mode="after")
    def _validate_bundle(self) -> Self:
        _validate_bundle_shape(self)
        _revalidate_artifact_manifest(self)
        _revalidate_hash_manifest(self)
        _validate_report_alignment(self)
        return self

    @computed_field
    @property
    def bundle_hash(self) -> str:
        return self.hash_manifest.bundle_payload_hash.value


def _require_instance(value: Any, expected_type: type[Any], field_name: str) -> Any:
    if not isinstance(value, expected_type):
        raise ProcessAuditError(f"{field_name} must be {expected_type.__name__}")
    return value


class ProcessAuditBuilderInput(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    project_ref: ProjectRef
    generated_at: datetime
    package_contract: SkipValidation[PackageContract]
    acceptance_contract: SkipValidation[AcceptanceContract]
    agent_context_index: BaseModel
    ticket_graph_summary: BaseModel
    source_inventory: SkipValidation[SourceInventory]
    run_manifest: SkipValidation[RunManifest]
    workspace_evidence_bundle: SkipValidation[WorkspaceEvidenceBundle]
    final_evidence_table: SkipValidation[FinalEvidenceTable]
    checker_verdict: SkipValidation[CheckerVerdict]
    verification_runs: tuple[SkipValidation[VerificationRun], ...]
    service_runs: tuple[SkipValidation[ServiceRunEvidence], ...] = ()
    live_blackbox_evidence: tuple[SkipValidation[LiveBlackboxIntegrationEvidence], ...] = ()
    verified_evidence: tuple[SkipValidation[VerifiedEvidence], ...]
    provider_attempt_refs: tuple[ProviderAttemptRef, ...]
    replay_bundle: SkipValidation[ReplayBundle]
    replay_readiness: SkipValidation[ReplayBundleReadiness]
    git_version_audit_bundle: SkipValidation[GitVersionAuditBundle]
    git_audit_readiness: SkipValidation[GitAuditReadiness]
    run_id: str | None = None

    @field_validator("run_id")
    @classmethod
    def _validate_run_id(cls, value: str | None) -> str | None:
        if value is None:
            return value
        try:
            return assert_namespace_segment(value, field_name="run_id")
        except NamespacedRefError as error:
            raise ProcessAuditError(str(error)) from error

    @model_validator(mode="before")
    @classmethod
    def _normalize_refs(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        for field_name in (
            "verification_runs",
            "service_runs",
            "live_blackbox_evidence",
            "verified_evidence",
            "provider_attempt_refs",
        ):
            if field_name in data and not isinstance(data[field_name], list | tuple):
                raise ProcessAuditError(f"{field_name} must be a tuple or list")
        return _normalize_ref_fields(
            data,
            {"project_ref": ProjectRef},
            {"provider_attempt_refs": ProviderAttemptRef},
        )

    @field_validator("generated_at")
    @classmethod
    def _require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ProcessAuditError("generated_at must include timezone")
        return value

    @field_validator("package_contract", mode="before")
    @classmethod
    def _require_package_contract(cls, value: Any) -> Any:
        return _require_instance(value, PackageContract, "package_contract")

    @field_validator("acceptance_contract", mode="before")
    @classmethod
    def _require_acceptance_contract(cls, value: Any) -> Any:
        return _require_instance(value, AcceptanceContract, "acceptance_contract")

    @field_validator("source_inventory", mode="before")
    @classmethod
    def _require_source_inventory(cls, value: Any) -> Any:
        return _require_instance(value, SourceInventory, "source_inventory")

    @field_validator("run_manifest", mode="before")
    @classmethod
    def _require_run_manifest(cls, value: Any) -> Any:
        return _require_instance(value, RunManifest, "run_manifest")

    @field_validator("workspace_evidence_bundle", mode="before")
    @classmethod
    def _require_workspace_evidence_bundle(cls, value: Any) -> Any:
        return _require_instance(
            value,
            WorkspaceEvidenceBundle,
            "workspace_evidence_bundle",
        )

    @field_validator("final_evidence_table", mode="before")
    @classmethod
    def _require_final_evidence_table(cls, value: Any) -> Any:
        return _require_instance(value, FinalEvidenceTable, "final_evidence_table")

    @field_validator("checker_verdict", mode="before")
    @classmethod
    def _require_checker_verdict(cls, value: Any) -> Any:
        return _require_instance(value, CheckerVerdict, "checker_verdict")

    @field_validator("replay_bundle", mode="before")
    @classmethod
    def _require_replay_bundle(cls, value: Any) -> Any:
        return _require_instance(value, ReplayBundle, "replay_bundle")

    @field_validator("replay_readiness", mode="before")
    @classmethod
    def _require_replay_readiness(cls, value: Any) -> Any:
        return _require_instance(value, ReplayBundleReadiness, "replay_readiness")

    @field_validator("git_version_audit_bundle", mode="before")
    @classmethod
    def _require_git_version_audit_bundle(cls, value: Any) -> Any:
        return _require_instance(
            value,
            GitVersionAuditBundle,
            "git_version_audit_bundle",
        )

    @field_validator("git_audit_readiness", mode="before")
    @classmethod
    def _require_git_audit_readiness(cls, value: Any) -> Any:
        return _require_instance(value, GitAuditReadiness, "git_audit_readiness")

    @field_validator("agent_context_index", mode="before")
    @classmethod
    def _require_agent_context_index(cls, value: Any) -> Any:
        return _require_instance(value, AgentContextIndex, "agent_context_index")

    @field_validator("ticket_graph_summary", mode="before")
    @classmethod
    def _require_projection_model(cls, value: Any) -> Any:
        if not isinstance(value, BaseModel):
            raise ProcessAuditError("builder input fields must be typed model instances")
        return value

    @field_validator("verification_runs")
    @classmethod
    def _validate_verification_runs(
        cls, values: tuple[VerificationRun, ...]
    ) -> tuple[VerificationRun, ...]:
        if not values:
            raise ProcessAuditError("verification_runs must not be empty")
        return values

    @field_validator("service_runs")
    @classmethod
    def _validate_service_runs(
        cls, values: tuple[ServiceRunEvidence, ...]
    ) -> tuple[ServiceRunEvidence, ...]:
        refs = [service.service_run_evidence_id.value for service in values]
        if len(set(refs)) != len(refs):
            raise ProcessAuditError("service_run refs must be unique")
        return values

    @field_validator("live_blackbox_evidence")
    @classmethod
    def _validate_live_blackbox_evidence(
        cls, values: tuple[LiveBlackboxIntegrationEvidence, ...]
    ) -> tuple[LiveBlackboxIntegrationEvidence, ...]:
        refs = [evidence.live_blackbox_evidence_id.value for evidence in values]
        if len(set(refs)) != len(refs):
            raise ProcessAuditError("live blackbox evidence refs must be unique")
        return values

    @field_validator("verified_evidence")
    @classmethod
    def _validate_verified_evidence(
        cls, values: tuple[VerifiedEvidence, ...]
    ) -> tuple[VerifiedEvidence, ...]:
        if not values:
            raise ProcessAuditError("verified_evidence must not be empty")
        return values

    @field_validator("provider_attempt_refs")
    @classmethod
    def _validate_provider_attempt_refs(
        cls, values: tuple[ProviderAttemptRef, ...]
    ) -> tuple[ProviderAttemptRef, ...]:
        if not values:
            raise ProcessAuditError("provider_attempt_refs must not be empty")
        if len({value.value for value in values}) != len(values):
            raise ProcessAuditError("provider_attempt_refs must be unique")
        return values

    @model_validator(mode="after")
    def _validate_input(self) -> Self:
        if self.replay_bundle.project_ref != self.project_ref:
            raise ProcessAuditError("replay bundle project_ref mismatch")
        if self.git_version_audit_bundle.project_ref != self.project_ref:
            raise ProcessAuditError("git version audit bundle project_ref mismatch")
        for event in _audit_events(self):
            if event.project_ref != self.project_ref:
                raise ProcessAuditError("event project_ref mismatch")
        if self.source_inventory.package_contract_ref != self.package_contract.package_contract_id:
            raise ProcessAuditError("source inventory package contract mismatch")
        if self.run_manifest.package_contract_ref != self.package_contract.package_contract_id:
            raise ProcessAuditError("run manifest package contract mismatch")
        if self.workspace_evidence_bundle.final_evidence_table_ref != self.final_evidence_table.final_evidence_table_id:
            raise ProcessAuditError("workspace evidence bundle final table mismatch")
        if self.checker_verdict.final_evidence_table_ref != self.final_evidence_table.final_evidence_table_id:
            raise ProcessAuditError("checker verdict final table mismatch")
        _validate_event_timeline_closure(self)
        _validate_agent_context_index_closure(self)
        _validate_source_inventory_entry_lineage_fields(self)
        _validate_source_inventory_consumer_ticket_closure(self)
        _validate_evidence_closure(self)
        _validate_git_version_audit_binding(self)
        _validate_replay_readiness_binding(self)
        derived_git_audit_readiness = git_version_audit_readiness(
            self.git_version_audit_bundle
        )
        if derived_git_audit_readiness != self.git_audit_readiness:
            raise ProcessAuditError("git version audit readiness mismatch")
        return self


def _validate_replay_readiness_binding(builder_input: ProcessAuditBuilderInput) -> None:
    if len(builder_input.replay_bundle.attestations) != 1:
        raise ProcessAuditError("replay bundle attestation count mismatch")
    attestation = builder_input.replay_bundle.attestations[0]
    readiness = builder_input.replay_readiness
    expected_event_range = (
        "event-range."
        f"{builder_input.replay_bundle.project_ref.value}."
        f"{attestation.event_window.first_graph_version}-{attestation.event_window.last_graph_version}"
    )
    if readiness.replay_passed is not True or readiness.hash_chain_verified is not True:
        raise ProcessAuditError("replay readiness mismatch")
    if readiness.payload_sha256_verified is not True:
        raise ProcessAuditError("replay readiness payload sha256 mismatch")
    if readiness.summary_hash != attestation.summary_hash:
        raise ProcessAuditError("replay readiness mismatch")
    if readiness.event_range.value != expected_event_range:
        raise ProcessAuditError("replay readiness mismatch")
    if readiness.projection_versions != (attestation.projection_version,):
        raise ProcessAuditError("replay readiness mismatch")
    if readiness.payload_manifest_ref.value != builder_input.replay_bundle.payload_manifest.payload_manifest_id.value:
        raise ProcessAuditError("replay readiness payload manifest mismatch")
    if readiness.payload_manifest_hash.value != builder_input.replay_bundle.hash_manifest.payload_manifest_hash.value:
        raise ProcessAuditError("replay readiness payload manifest mismatch")


def _audit_events(builder_input: ProcessAuditBuilderInput) -> tuple[EventRecord, ...]:
    events = tuple(builder_input.replay_bundle.events)
    if not events:
        raise ProcessAuditError("events must not be empty")
    return events


def _validate_event_timeline_closure(builder_input: ProcessAuditBuilderInput) -> None:
    previous_graph_version = 0
    kinds: set[str] = set()
    events_by_graph_version: dict[int, EventRecord] = {}
    for event in _audit_events(builder_input):
        if event.graph_version <= previous_graph_version:
            raise ProcessAuditError("events must be strictly increasing by graph_version")
        previous_graph_version = event.graph_version
        kinds.add(_timeline_kind_from_event(event))
        events_by_graph_version[event.graph_version] = event

    missing = _REQUIRED_TIMELINE_EVENT_KINDS - kinds
    if missing:
        raise ProcessAuditError(f"timeline missing real event kind: {sorted(missing)[0]}")

    for attestation in builder_input.replay_bundle.attestations:
        event_window = attestation.event_window
        covered_versions = range(
            event_window.first_graph_version,
            event_window.last_graph_version + 1,
        )
        for graph_version in covered_versions:
            if graph_version not in events_by_graph_version:
                raise ProcessAuditError("events must cover replay bundle event window")
        first_event = events_by_graph_version[event_window.first_graph_version]
        last_event = events_by_graph_version[event_window.last_graph_version]
        if first_event.event_id != event_window.first_event_id or last_event.event_id != event_window.last_event_id:
            raise ProcessAuditError("events must match replay bundle event window")


def _agent_context_entries(agent_context_index: BaseModel) -> tuple[Any, ...]:
    try:
        return _required_nonempty_iterable_attr(
            agent_context_index,
            "entries",
            context="agent context index",
        )
    except ProcessAuditError as error:
        if "missing entries" in str(error):
            entries = getattr(agent_context_index, "entries", None)
            if isinstance(entries, tuple | list) and not entries:
                raise ProcessAuditError("agent context index entries must not be empty") from error
        raise


def _agent_context_entry_provider_attempt_refs(entry: Any) -> tuple[Any, ...]:
    try:
        return _required_nonempty_iterable_attr(
            entry,
            "provider_attempt_refs",
            context="agent context index",
        )
    except ProcessAuditError as error:
        if "missing provider_attempt_refs" in str(error):
            raise ProcessAuditError("agent context index missing provider_attempt_refs") from error
        raise


def _agent_context_provider_attempt_refs(agent_context_index: BaseModel) -> set[str]:
    refs: set[str] = set()
    for entry in _agent_context_entries(agent_context_index):
        snapshot = _required_attr(
            entry,
            "snapshot",
            context="agent context index entry",
        )
        _required_attr(
            snapshot,
            "execution_package_ref",
            context="agent context snapshot",
        )
        _required_attr(
            snapshot,
            "model_execution_profile",
            context="agent context snapshot",
        )
        provider_attempt_refs = _agent_context_entry_provider_attempt_refs(entry)
        for provider_attempt_ref in provider_attempt_refs:
            value = _ref_value(provider_attempt_ref)
            if value in refs:
                raise ProcessAuditError("agent context provider_attempt_refs must be unique")
            refs.add(value)
    return refs


def _validate_agent_context_index_closure(builder_input: ProcessAuditBuilderInput) -> None:
    expected_refs = {ref.value for ref in builder_input.provider_attempt_refs}
    actual_refs = _agent_context_provider_attempt_refs(builder_input.agent_context_index)
    if actual_refs != expected_refs:
        raise ProcessAuditError(
            "agent context provider_attempt_refs mismatch: "
            f"missing={sorted(expected_refs - actual_refs)}; "
            f"extra={sorted(actual_refs - expected_refs)}"
        )


def _final_table_verified_evidence_refs(builder_input: ProcessAuditBuilderInput) -> set[str]:
    return {
        evidence_ref.value
        for row in builder_input.final_evidence_table.rows
        for evidence_ref in row.verified_evidence_refs
    }


def _source_inventory_evidence_refs(builder_input: ProcessAuditBuilderInput) -> set[str]:
    return {
        evidence_ref.value
        for entry in builder_input.source_inventory.entries
        for evidence_ref in entry.evidence_refs
    }


def _validate_evidence_closure(builder_input: ProcessAuditBuilderInput) -> None:
    verified_refs = {evidence.verified_evidence_id.value for evidence in builder_input.verified_evidence}
    if len(verified_refs) != len(builder_input.verified_evidence):
        raise ProcessAuditError("verified_evidence refs must be unique")
    for evidence in builder_input.verified_evidence:
        _evidence_binding_refs_for_evidence(evidence)
    verification_run_refs = {
        run.verification_run_id.value for run in builder_input.verification_runs
    }
    actual_service_run_refs = {
        service.service_run_evidence_id.value for service in builder_input.service_runs
    }
    actual_live_blackbox_refs = {
        evidence.live_blackbox_evidence_id.value
        for evidence in builder_input.live_blackbox_evidence
    }
    service_run_refs = {
        ref.value for ref in builder_input.workspace_evidence_bundle.service_run_refs
    }
    live_blackbox_evidence_refs = {
        ref.value for ref in builder_input.workspace_evidence_bundle.live_blackbox_evidence_refs
    }
    if actual_service_run_refs != service_run_refs:
        raise ProcessAuditError("workspace evidence bundle service_run_refs mismatch")
    if actual_live_blackbox_refs != live_blackbox_evidence_refs:
        raise ProcessAuditError("workspace evidence bundle live_blackbox_evidence_refs mismatch")
    for evidence in builder_input.live_blackbox_evidence:
        required_service_refs = {
            evidence.backend_service_run_ref.value,
            evidence.frontend_service_run_ref.value,
        }
        if not required_service_refs.issubset(actual_service_run_refs):
            raise ProcessAuditError(
                "live blackbox evidence service run refs must resolve to service runs"
            )
    linked_run_refs = {
        run_ref.value
        for evidence in builder_input.verified_evidence
        for run_ref in evidence.verification_run_refs
    }
    linked_service_run_refs = {
        service_ref.value
        for evidence in builder_input.verified_evidence
        for service_ref in evidence.service_run_refs
    }
    linked_live_blackbox_refs = {
        live_ref.value
        for evidence in builder_input.verified_evidence
        for live_ref in evidence.live_blackbox_evidence_refs
    }
    missing_run_refs = linked_run_refs - verification_run_refs
    if missing_run_refs:
        raise ProcessAuditError(
            "verified evidence references missing verification runs: "
            f"{sorted(missing_run_refs)}"
        )
    missing_service_refs = linked_service_run_refs - service_run_refs
    if missing_service_refs:
        raise ProcessAuditError(
            "verified evidence references missing service runs: "
            f"{sorted(missing_service_refs)}"
        )
    missing_live_refs = linked_live_blackbox_refs - live_blackbox_evidence_refs
    if missing_live_refs:
        raise ProcessAuditError(
            "verified evidence references missing live blackbox evidence: "
            f"{sorted(missing_live_refs)}"
        )
    unlinked_service_refs = service_run_refs - linked_service_run_refs - {
        ref
        for evidence in builder_input.live_blackbox_evidence
        for ref in (
            evidence.backend_service_run_ref.value,
            evidence.frontend_service_run_ref.value,
        )
    }
    if unlinked_service_refs:
        raise ProcessAuditError(
            "workspace evidence bundle service_run_refs missing verified evidence: "
            f"{sorted(unlinked_service_refs)}"
        )
    unlinked_live_refs = live_blackbox_evidence_refs - linked_live_blackbox_refs
    if unlinked_live_refs:
        raise ProcessAuditError(
            "workspace evidence bundle live_blackbox_evidence_refs missing verified evidence: "
            f"{sorted(unlinked_live_refs)}"
        )

    final_table_refs = _final_table_verified_evidence_refs(builder_input)
    missing_final_refs = final_table_refs - verified_refs
    if missing_final_refs:
        raise ProcessAuditError(
            "final evidence table references missing verified evidence: "
            f"{sorted(missing_final_refs)}"
        )

    try:
        assert_source_inventory_evidence_refs_resolve(
            builder_input.source_inventory.source_inventory_id.value,
            builder_input.source_inventory,
            builder_input.verified_evidence,
        )
    except CloseoutClosureError as error:
        raise ProcessAuditError(f"source inventory evidence_refs missing verified evidence: {error}") from error

    dangling_source_refs = _source_inventory_evidence_refs(builder_input) - final_table_refs
    if dangling_source_refs:
        raise ProcessAuditError(
            "source inventory evidence_refs missing from final evidence table: "
            f"{sorted(dangling_source_refs)}"
        )


def _validate_git_version_audit_binding(builder_input: ProcessAuditBuilderInput) -> None:
    git_bundle = builder_input.git_version_audit_bundle
    expected_source_inventory_hash = source_inventory_hash(builder_input.source_inventory)
    if git_bundle.report.source_inventory_ref != builder_input.source_inventory.source_inventory_id:
        raise ProcessAuditError("git version audit source_inventory_ref mismatch")
    if git_bundle.report.source_inventory_hash != expected_source_inventory_hash:
        raise ProcessAuditError("git version audit source inventory hash mismatch")
    if git_bundle.fact_set.source_inventory_hash != expected_source_inventory_hash:
        raise ProcessAuditError("git version audit fact source inventory hash mismatch")
    if git_bundle.report.package_commit_ref != builder_input.source_inventory.package_commit_ref:
        raise ProcessAuditError("git version audit package_commit_ref mismatch")

    verification_run_refs = {run.verification_run_id.value for run in builder_input.verification_runs}
    report_command_refs = set(git_bundle.report.command_evidence_refs)
    bindings_by_ref = {
        binding.verification_run_ref.value: binding
        for binding in git_bundle.command_evidence_bindings
    }
    if (
        report_command_refs != verification_run_refs
        or set(bindings_by_ref) != verification_run_refs
        or len(bindings_by_ref) != len(git_bundle.command_evidence_bindings)
    ):
        raise ProcessAuditError("git version audit command evidence refs mismatch")
    for run in builder_input.verification_runs:
        binding = bindings_by_ref[run.verification_run_id.value]
        if run.status is not VerificationRunStatus.PASSED or run.exit_code != 0:
            raise ProcessAuditError("git version audit verification run facts mismatch")
        if (
            binding.command_id != run.command_id
            or binding.command != run.command
            or binding.cwd != run.cwd
            or binding.workspace_snapshot_ref != run.workspace_snapshot_ref
        ):
            raise ProcessAuditError("git version audit verification run facts mismatch")
        if binding.run_manifest_ref != builder_input.run_manifest.run_manifest_id:
            raise ProcessAuditError("git version audit run_manifest_ref mismatch")
    for binding in git_bundle.command_evidence_bindings:
        if binding.package_contract_ref != builder_input.package_contract.package_contract_id:
            raise ProcessAuditError("git version audit package_contract_ref mismatch")
        if binding.source_inventory_hash != expected_source_inventory_hash:
            raise ProcessAuditError("git version audit binding source inventory hash mismatch")


def build_process_audit_bundle(builder_input: ProcessAuditBuilderInput) -> ProcessAuditBundle:
    if not isinstance(builder_input, ProcessAuditBuilderInput):
        raise ProcessAuditError("builder_input must be ProcessAuditBuilderInput")
    builder_input = _validate_builder_input_instance(builder_input)

    _validate_agent_context_index_payload(_agent_context_index_payload(builder_input))
    checked_refs = _checked_refs(builder_input)
    artifacts = _build_artifacts(builder_input, checked_refs)
    artifact_manifest = _build_artifact_manifest(builder_input, artifacts)
    report = _build_report(builder_input, artifacts, checked_refs)
    artifact_hashes = {
        artifact.path.value: artifact.sha256 for artifact in artifacts
    }
    hash_manifest_without_bundle_hash = _process_audit_hash_manifest_payload(
        builder_input=builder_input,
        artifact_hashes=artifact_hashes,
        artifact_manifest=artifact_manifest,
        report=report,
    )
    bundle_id_placeholder = ProcessAuditBundleRef(
        value=namespaced_ref(
            kind="process-audit-bundle",
            project_ref=builder_input.project_ref.value,
            content_hash=hash_manifest_without_bundle_hash["artifact_manifest_hash"].value,
            run_id=builder_input.run_id,
        )
    )
    bundle_payload_hash = ProcessAuditContentHash(
        value=_hash_bundle_payload(
            process_audit_bundle_id=bundle_id_placeholder,
            project_ref=builder_input.project_ref,
            generated_at=builder_input.generated_at,
            artifacts=artifacts,
            artifact_manifest=artifact_manifest,
            hash_manifest_without_bundle_hash=hash_manifest_without_bundle_hash,
            process_audit_report=report,
            checked_refs=checked_refs,
        )
    )
    bundle_id = ProcessAuditBundleRef(
        value=namespaced_ref(
            kind="process-audit-bundle",
            project_ref=builder_input.project_ref.value,
            content_hash=bundle_payload_hash.value,
            run_id=builder_input.run_id,
        )
    )
    bundle_payload_hash = ProcessAuditContentHash(
        value=_hash_bundle_payload(
            process_audit_bundle_id=bundle_id,
            project_ref=builder_input.project_ref,
            generated_at=builder_input.generated_at,
            artifacts=artifacts,
            artifact_manifest=artifact_manifest,
            hash_manifest_without_bundle_hash=hash_manifest_without_bundle_hash,
            process_audit_report=report,
            checked_refs=checked_refs,
        )
    )
    hash_manifest = ProcessAuditHashManifest(
        **hash_manifest_without_bundle_hash,
        bundle_payload_hash=bundle_payload_hash,
    )
    return ProcessAuditBundle(
        process_audit_bundle_id=bundle_id,
        project_ref=builder_input.project_ref,
        generated_at=builder_input.generated_at,
        artifacts=artifacts,
        artifact_manifest=artifact_manifest,
        hash_manifest=hash_manifest,
        process_audit_report=report,
        checked_refs=checked_refs,
    )


def _revalidate_builder_model(value: BaseModel, expected_type: type[BaseModel], field_name: str) -> None:
    try:
        expected_type.model_validate(value.model_dump(mode="python"))
    except (TypeError, ValueError, ValidationError) as error:
        raise ProcessAuditError(f"{field_name} must be valid {expected_type.__name__}") from error


def _validate_builder_input_instance(
    builder_input: ProcessAuditBuilderInput,
) -> ProcessAuditBuilderInput:
    try:
        _revalidate_builder_model(builder_input.source_inventory, SourceInventory, "source_inventory")
        _revalidate_builder_model(builder_input.run_manifest, RunManifest, "run_manifest")
        _revalidate_builder_model(builder_input.agent_context_index, AgentContextIndex, "agent_context_index")
        validated = ProcessAuditBuilderInput.model_validate(builder_input)
        return validated
    except ValidationError as error:
        raise ProcessAuditError(str(error)) from error


def process_audit_readiness(bundle: ProcessAuditBundle) -> ProcessAuditReadiness:
    if not isinstance(bundle, ProcessAuditBundle):
        raise ProcessAuditError("bundle must be ProcessAuditBundle")
    _validate_bundle_shape(bundle)
    run_id = _validate_artifact_namespaces(bundle)
    _validate_manifest_entry_namespaces(bundle, run_id)
    try:
        validated_bundle = _validate_bundle_instance(bundle)
    except ValidationError as error:
        raise ProcessAuditError(str(error)) from error
    _revalidate_artifact_manifest(validated_bundle)
    _revalidate_hash_manifest(validated_bundle)
    _validate_report_alignment(validated_bundle)
    _validate_timeline(validated_bundle)
    _validate_decision_log(validated_bundle)
    _validate_agent_context_index(validated_bundle)
    _validate_artifact_lineage(validated_bundle)
    _validate_evidence_map(validated_bundle)
    _validate_git_version_audit(validated_bundle)
    _validate_replay_bundle_report(validated_bundle)
    return ProcessAuditReadiness(
        artifact_paths=tuple(
            artifact.path for artifact in sorted(
                validated_bundle.artifacts,
                key=lambda item: REQUIRED_PROCESS_AUDIT_ARTIFACT_PATHS.index(item.path.value),
            )
        ),
        all_artifacts_present=True,
        timeline_key_events_present=True,
        agent_context_index_complete=True,
        artifact_lineage_complete=True,
        evidence_map_consistent_with_final_table=True,
    )


def _process_audit_hash_manifest_payload(
    *,
    builder_input: ProcessAuditBuilderInput,
    artifact_hashes: dict[str, ProcessAuditContentHash],
    artifact_manifest: ProcessAuditArtifactManifest,
    report: ProcessAuditReport,
) -> dict[str, Any]:
    artifact_manifest_hash = ProcessAuditContentHash(value=_hash_model(artifact_manifest))
    process_audit_report_hash = ProcessAuditContentHash(value=_hash_model(report))
    hash_manifest_id = ProcessAuditManifestRef(
        value=namespaced_ref(
            kind="process-audit-hash-manifest",
            project_ref=builder_input.project_ref.value,
            content_hash=_hash_jsonable(
                {
                    "project_ref": builder_input.project_ref.value,
                    "artifact_hashes": artifact_hashes,
                    "artifact_manifest_hash": artifact_manifest_hash.value,
                    "process_audit_report_hash": process_audit_report_hash.value,
                }
            ),
            run_id=builder_input.run_id,
        )
    )
    return {
        "hash_manifest_id": hash_manifest_id,
        "project_ref": builder_input.project_ref,
        "artifact_hashes": artifact_hashes,
        "artifact_manifest_hash": artifact_manifest_hash,
        "process_audit_report_hash": process_audit_report_hash,
    }


def _build_artifacts(
    builder_input: ProcessAuditBuilderInput,
    checked_refs: tuple[str, ...],
) -> tuple[ProcessAuditArtifact, ...]:
    content_by_kind = {
        ProcessAuditArtifactKind.PROCESS_AUDIT: _process_audit_markdown(builder_input),
        ProcessAuditArtifactKind.TIMELINE: _timeline_payload(builder_input),
        ProcessAuditArtifactKind.DECISION_LOG: _decision_log_markdown(builder_input),
        ProcessAuditArtifactKind.AGENT_CONTEXT_INDEX: _agent_context_index_payload(builder_input),
        ProcessAuditArtifactKind.TICKET_GRAPH: _ticket_graph_markdown(builder_input),
        ProcessAuditArtifactKind.EVIDENCE_MAP: _evidence_map_payload(builder_input),
        ProcessAuditArtifactKind.GIT_VERSION_AUDIT: _git_version_audit_markdown(builder_input),
        ProcessAuditArtifactKind.CLOSEOUT_SUMMARY: _closeout_summary_markdown(builder_input),
        ProcessAuditArtifactKind.REPLAY_BUNDLE_REPORT: _replay_bundle_report_payload(builder_input),
    }
    evidence_map_hash = _hash_content(
        content_by_kind[ProcessAuditArtifactKind.EVIDENCE_MAP],
        ProcessAuditArtifactFormat.JSON,
    )
    evidence_map_ref = _process_audit_ref(
        kind="process-audit-artifact",
        project_ref=builder_input.project_ref,
        content_hash=evidence_map_hash,
        run_id=builder_input.run_id,
        artifact_kind=ProcessAuditArtifactKind.EVIDENCE_MAP,
    )
    content_by_kind[ProcessAuditArtifactKind.ARTIFACT_LINEAGE] = _artifact_lineage_payload(
        builder_input,
        evidence_map_ref=evidence_map_ref,
    )
    artifacts: list[ProcessAuditArtifact] = []
    for path in REQUIRED_PROCESS_AUDIT_ARTIFACT_PATHS:
        kind, artifact_format = _PATH_KIND_FORMAT[path]
        content = content_by_kind[kind]
        content_hash = _hash_content(content, artifact_format)
        artifacts.append(
            ProcessAuditArtifact(
                artifact_id=ProcessAuditArtifactRef(
                    value=_process_audit_ref(
                        kind="process-audit-artifact",
                        project_ref=builder_input.project_ref,
                        content_hash=content_hash,
                        run_id=builder_input.run_id,
                        artifact_kind=kind,
                    )
                ),
                path=ProcessAuditArtifactPath(value=path),
                kind=kind,
                format=artifact_format,
                content_ref=ProcessAuditContentRef(
                    value=_process_audit_ref(
                        kind="process-audit-content",
                        project_ref=builder_input.project_ref,
                        content_hash=content_hash,
                        run_id=builder_input.run_id,
                        artifact_kind=kind,
                    )
                ),
                content=content,
                sha256=ProcessAuditContentHash(value=content_hash),
                source_refs=checked_refs,
            )
        )
    return tuple(artifacts)


def _build_artifact_manifest(
    builder_input: ProcessAuditBuilderInput,
    artifacts: tuple[ProcessAuditArtifact, ...],
) -> ProcessAuditArtifactManifest:
    artifact_manifest_id = ProcessAuditManifestRef(
        value=namespaced_ref(
            kind="process-audit-artifact-manifest",
            project_ref=builder_input.project_ref.value,
            content_hash=_hash_jsonable(
                [
                    {
                        "artifact_ref": artifact.artifact_id.value,
                        "path": artifact.path.value,
                        "kind": artifact.kind.value,
                        "format": artifact.format.value,
                        "content_ref": artifact.content_ref.value,
                        "sha256": artifact.sha256.value,
                    }
                    for artifact in artifacts
                ]
            ),
            run_id=builder_input.run_id,
        )
    )
    return ProcessAuditArtifactManifest(
        artifact_manifest_id=artifact_manifest_id,
        project_ref=builder_input.project_ref,
        entries=tuple(
            ProcessAuditArtifactManifestEntry(
                artifact_ref=artifact.artifact_id,
                path=artifact.path,
                kind=artifact.kind,
                format=artifact.format,
                content_ref=artifact.content_ref,
                sha256=artifact.sha256,
            )
            for artifact in artifacts
        ),
    )


def _build_report(
    builder_input: ProcessAuditBuilderInput,
    artifacts: tuple[ProcessAuditArtifact, ...],
    checked_refs: tuple[str, ...],
) -> ProcessAuditReport:
    by_kind = {artifact.kind: artifact for artifact in artifacts}
    report_payload_hash = _hash_jsonable(
        {
            "project_ref": builder_input.project_ref.value,
            "generated_at": builder_input.generated_at.isoformat(),
            "artifact_refs": {
                kind.value: artifact.artifact_id.value for kind, artifact in by_kind.items()
            },
            "checked_refs": checked_refs,
            "replay_summary_hash": builder_input.replay_readiness.summary_hash.value,
            "replay_projection_versions": tuple(
                version.value for version in builder_input.replay_readiness.projection_versions
            ),
        }
    )
    return ProcessAuditReport(
        process_audit_report_id=ProcessAuditReportRef(
            value=namespaced_ref(
                kind="process-audit-report",
                project_ref=builder_input.project_ref.value,
                content_hash=report_payload_hash,
                run_id=builder_input.run_id,
            )
        ),
        project_ref=builder_input.project_ref,
        generated_at=builder_input.generated_at,
        process_audit_ref=by_kind[ProcessAuditArtifactKind.PROCESS_AUDIT].artifact_id,
        timeline_ref=by_kind[ProcessAuditArtifactKind.TIMELINE].artifact_id,
        decision_log_ref=by_kind[ProcessAuditArtifactKind.DECISION_LOG].artifact_id,
        agent_context_index_ref=by_kind[ProcessAuditArtifactKind.AGENT_CONTEXT_INDEX].artifact_id,
        ticket_graph_ref=by_kind[ProcessAuditArtifactKind.TICKET_GRAPH].artifact_id,
        artifact_lineage_ref=by_kind[ProcessAuditArtifactKind.ARTIFACT_LINEAGE].artifact_id,
        evidence_map_ref=by_kind[ProcessAuditArtifactKind.EVIDENCE_MAP].artifact_id,
        git_audit_ref=by_kind[ProcessAuditArtifactKind.GIT_VERSION_AUDIT].artifact_id,
        closeout_summary_ref=by_kind[ProcessAuditArtifactKind.CLOSEOUT_SUMMARY].artifact_id,
        replay_bundle_report_ref=by_kind[ProcessAuditArtifactKind.REPLAY_BUNDLE_REPORT].artifact_id,
        checked_refs=checked_refs,
        expected_evidence_map_rows=tuple(_evidence_map_payload(builder_input)["rows"]),
        expected_artifact_lineage_rows=tuple(
            _artifact_lineage_payload(
                builder_input,
                evidence_map_ref=by_kind[ProcessAuditArtifactKind.EVIDENCE_MAP].artifact_id.value,
            )["lineages"]
        ),
        expected_fallback_lineage_rows=tuple(
            _artifact_lineage_payload(
                builder_input,
                evidence_map_ref=by_kind[ProcessAuditArtifactKind.EVIDENCE_MAP].artifact_id.value,
            )["fallback_lineages"]
        ),
        expected_fallback_decision_refs=_canonical_sorted_unique_strings(
            _fallback_decision_refs(builder_input)
        ),
        replay_summary_hash=builder_input.replay_readiness.summary_hash.value,
        replay_projection_versions=tuple(
            version.value for version in builder_input.replay_readiness.projection_versions
        ),
    )


def _markdown_lines(*lines: str) -> str:
    return "\n\n".join(lines)


def _canonical_sorted_unique_strings(values: Iterable[str]) -> tuple[str, ...]:
    return canonical_sort_for_hash(
        tuple(dict.fromkeys(values)),
        key=lambda value: value,
    )


def _process_audit_markdown(builder_input: ProcessAuditBuilderInput) -> str:
    return _markdown_lines(
        "# Process Audit",
        "## Requirement interpretation",
        f"Package contract: {builder_input.package_contract.package_contract_id.value}",
        f"Acceptance contract: {builder_input.acceptance_contract.acceptance_contract_id.value}",
        "## Contract formation",
        "AcceptanceContract and PackageContract constrain implementation evidence.",
        "## Team execution",
        "Agent seats received ExecutionPackage context and recorded ProviderAttempt facts.",
        "## Evidence verification",
        f"Final evidence table: {builder_input.final_evidence_table.final_evidence_table_id.value}",
        "## Checker review",
        f"Checker verdict: {builder_input.checker_verdict.checker_verdict_id.value}",
        "## Replay and closeout readiness",
        f"Replay bundle: {builder_input.replay_bundle.replay_bundle_id.value}",
    )


def _timeline_payload(builder_input: ProcessAuditBuilderInput) -> dict[str, Any]:
    events = _audit_events(builder_input)
    event_log_items = [_timeline_item_from_event(event) for event in events]
    return {
        "project_ref": builder_input.project_ref.value,
        "archived_event_refs": [event.event_id.value for event in events],
        "events": event_log_items,
    }


def _timeline_kind_from_event(event: EventRecord) -> str:
    return _EVENT_TYPE_TO_TIMELINE_KIND.get(event.event_type, event.event_type.value)


def _timeline_item_from_event(event: EventRecord) -> dict[str, Any]:
    return {
        "event_ref": event.event_id.value,
        "kind": _timeline_kind_from_event(event),
        "timestamp": event.timestamp.isoformat(),
        "actor_ref": event.actor_ref.value,
        "graph_version": event.graph_version,
        "payload_refs": [payload_ref.value for payload_ref in event.payload_refs],
        "causation_refs": [event_ref.value for event_ref in event.causation_refs],
        "correlation_refs": [event_ref.value for event_ref in event.correlation_refs],
        "source": "event_log",
    }


def _ticket_graph_summary_tickets(ticket_graph_summary: Any) -> tuple[Any, ...]:
    tickets = _required_attr(
        ticket_graph_summary,
        "tickets",
        context="ticket graph summary",
    )
    if isinstance(tickets, str | bytes | Mapping):
        raise ProcessAuditError("ticket graph summary missing tickets")
    try:
        resolved_tickets = tuple(tickets)
    except TypeError as error:
        raise ProcessAuditError("ticket graph summary missing tickets") from error
    if not resolved_tickets:
        raise ProcessAuditError("ticket graph summary missing tickets")
    return resolved_tickets


def _ticket_refs(builder_input: ProcessAuditBuilderInput) -> tuple[str, ...]:
    return tuple(
        _ref_value(
            _required_attr(
                ticket,
                "ticket_ref",
                context="ticket graph summary ticket",
            )
        )
        for ticket in _ticket_graph_summary_tickets(builder_input.ticket_graph_summary)
    )


def _decision_log_markdown(builder_input: ProcessAuditBuilderInput) -> str:
    return _markdown_lines(
        "# Decision Log",
        "## CEO / Human Board Decision",
        "CEO / human board accepted the directive and required evidence-backed closeout.",
        "## Architect / Contract Decision",
        f"Package contract {builder_input.package_contract.package_contract_id.value} governs delivery.",
        "## Checker Decision",
        f"Checker verdict {builder_input.checker_verdict.checker_verdict_id.value} is recorded.",
        "## Closeout Readiness Decision",
        "Closeout can only proceed after replay, git, evidence, and process audit readiness.",
    )


def _agent_context_index_payload(builder_input: ProcessAuditBuilderInput) -> dict[str, Any]:
    return {"entries": list(_agent_context_index_entries(builder_input.agent_context_index))}


def _agent_context_index_entries(agent_context_index: BaseModel) -> tuple[dict[str, Any], ...]:
    entries: list[dict[str, Any]] = []
    for entry in _agent_context_entries(agent_context_index):
        entry_id = _required_attr(
            entry,
            "entry_id",
            context="agent context index entry",
        )
        snapshot = _required_attr(
            entry,
            "snapshot",
            context="agent context index entry",
        )
        context_snapshot_id = _required_attr(
            snapshot,
            "context_snapshot_id",
            context="agent context snapshot",
        )
        snapshot_fingerprint = _required_attr(
            snapshot,
            "snapshot_fingerprint",
            context="agent context snapshot",
        )
        execution_package_ref = _required_attr(
            snapshot,
            "execution_package_ref",
            context="agent context snapshot",
        )
        model_execution_profile = _required_attr(
            snapshot,
            "model_execution_profile",
            context="agent context snapshot",
        )
        provider_attempt_refs = _agent_context_entry_provider_attempt_refs(entry)
        entries.append(
            {
                "entry_id": _ref_value(entry_id),
                "snapshot_ref": _ref_value(context_snapshot_id),
                "snapshot_fingerprint": snapshot_fingerprint,
                "execution_package_ref": _ref_value(execution_package_ref),
                "model_execution_profile": _model_execution_profile_payload(
                    model_execution_profile
                ),
                "provider_attempt_refs": [
                    _ref_value(ref) for ref in provider_attempt_refs
                ],
            }
        )
    return canonical_sort_for_hash(
        entries,
        key=lambda item: item["entry_id"],
    )


def _model_execution_profile_payload(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    return _canonical_jsonable(value)



def _ticket_graph_markdown(builder_input: ProcessAuditBuilderInput) -> str:
    lines = ["# Ticket Graph"]
    for ticket in _ticket_graph_summary_tickets(builder_input.ticket_graph_summary):
        ticket_ref = _required_attr(
            ticket,
            "ticket_ref",
            context="ticket graph summary ticket",
        )
        status = _required_attr(
            ticket,
            "status",
            context="ticket graph summary ticket",
        )
        owner_seat_ref = _required_attr(
            ticket,
            "owner_seat_ref",
            context="ticket graph summary ticket",
        )
        acceptance_refs = _required_nonempty_iterable_attr(
            ticket,
            "acceptance_refs",
            context="ticket graph summary ticket",
        )
        acceptance_ref_text = ", ".join(_ref_value(ref) for ref in acceptance_refs)
        lines.extend(
            (
                f"## {_ref_value(ticket_ref)}",
                f"Status: {_ref_value(status)}",
                f"Acceptance refs: {acceptance_ref_text}",
                f"Owner seat: {_ref_value(owner_seat_ref)}",
            )
        )
    return _markdown_lines(*lines)


def _evidence_bindings_for_entry(
    builder_input: ProcessAuditBuilderInput,
    evidence_refs: tuple[Any, ...],
) -> list[dict[str, Any]]:
    evidence_by_ref = {
        evidence.verified_evidence_id.value: evidence
        for evidence in builder_input.verified_evidence
    }
    run_manifest_ref = builder_input.run_manifest.run_manifest_id.value
    bindings: list[dict[str, str]] = []
    for evidence_ref in evidence_refs:
        evidence = evidence_by_ref.get(evidence_ref.value)
        if evidence is None:
            raise ProcessAuditError("source inventory evidence_refs missing verified evidence")
        binding_refs = _evidence_binding_refs_for_evidence(evidence)
        bindings.append(
            {
                "evidence_claim_ref": evidence.evidence_claim_ref.value,
                "verified_evidence_ref": evidence.verified_evidence_id.value,
                "verifier_ref": _verifier_ref_for_evidence(builder_input, evidence),
                "verification_run_ref": binding_refs["verification_run_ref"],
                "service_run_refs": binding_refs["service_run_refs"],
                "live_blackbox_evidence_refs": binding_refs["live_blackbox_evidence_refs"],
                "run_manifest_ref": run_manifest_ref,
            }
        )
    return sorted(bindings, key=lambda item: item["verified_evidence_ref"])


def _artifact_lineage_payload(
    builder_input: ProcessAuditBuilderInput,
    *,
    evidence_map_ref: str,
) -> dict[str, Any]:
    lineages = []
    for entry in canonical_sort_for_hash(
        builder_input.source_inventory.entries,
        key=lambda entry: _ref_value(
            _required_attr(entry, "path", context="source inventory entry")
        ),
    ):
        attrs = _source_inventory_entry_lineage_attrs(entry)
        lineages.append(
            {
                "path": attrs["path"].value,
                "sha256": attrs["sha256"].value,
                "source_surface_ref": attrs["source_surface_ref"].value,
                "producer_ticket_ref": attrs["producer_ticket_ref"].value,
                "producer_attempt_ref": attrs["producer_attempt_ref"].value,
                "consumer_ticket_refs": [
                    ref.value for ref in attrs["consumer_ticket_refs"]
                ],
                "acceptance_refs": [ref.value for ref in attrs["acceptance_refs"]],
                "evidence_refs": [ref.value for ref in attrs["evidence_refs"]],
                "evidence_bindings": _evidence_bindings_for_entry(
                    builder_input,
                    attrs["evidence_refs"],
                ),
                "evidence_map_ref": evidence_map_ref,
                "final_evidence_table_ref": builder_input.final_evidence_table.final_evidence_table_id.value,
            }
        )
    fallback_lineages = []
    for evidence in canonical_sort_for_hash(
        (
            evidence
            for evidence in builder_input.verified_evidence
            if evidence.fallback_decision_record_ref is not None
        ),
        key=lambda evidence: evidence.fallback_decision_record_ref.value,
    ):
        if evidence.fallback_decision_record_ref is None:
            continue
        fallback_lineages.append(
            {
                "fallback_decision_record_ref": evidence.fallback_decision_record_ref.value,
                "fallback_decision_recorded_ref": (
                    evidence.fallback_decision_recorded_ref.value
                    if evidence.fallback_decision_recorded_ref is not None
                    else None
                ),
                "verifier_ref": _verifier_ref_for_evidence(builder_input, evidence),
                "evidence_map_ref": evidence_map_ref,
            }
        )
    return {
        "checker_verdict_ref": builder_input.checker_verdict.checker_verdict_id.value,
        "lineages": lineages,
        "fallback_lineages": fallback_lineages,
    }


def _evidence_binding_refs_for_evidence(evidence: VerifiedEvidence) -> dict[str, Any]:
    if not isinstance(evidence, VerifiedEvidence):
        raise ProcessAuditError("verified evidence must resolve to VerifiedEvidence")
    verification_run_refs = tuple(ref.value for ref in evidence.verification_run_refs)
    service_run_refs = tuple(ref.value for ref in evidence.service_run_refs)
    live_blackbox_evidence_refs = tuple(
        ref.value for ref in evidence.live_blackbox_evidence_refs
    )
    if not verification_run_refs and not service_run_refs and not live_blackbox_evidence_refs:
        raise ProcessAuditError(
            "verified evidence missing verification_run_refs, service_run_refs, "
            f"or live_blackbox_evidence_refs: {evidence.verified_evidence_id.value}"
        )
    return {
        "verification_run_ref": verification_run_refs[0] if verification_run_refs else None,
        "service_run_refs": sorted(service_run_refs),
        "live_blackbox_evidence_refs": sorted(live_blackbox_evidence_refs),
    }


def _verification_ref_for_evidence(evidence: VerifiedEvidence) -> str | None:
    binding_refs = _evidence_binding_refs_for_evidence(evidence)
    verification_run_ref = binding_refs["verification_run_ref"]
    return verification_run_ref


def _verifier_ref_for_evidence(
    builder_input: ProcessAuditBuilderInput,
    evidence: VerifiedEvidence,
) -> str:
    verification_run_ref = _verification_ref_for_evidence(evidence)
    if verification_run_ref is None:
        if evidence.service_run_refs:
            return "service-runner"
        if evidence.live_blackbox_evidence_refs:
            return "live-blackbox-verifier"
        raise ProcessAuditError("verified evidence missing verifier source")
    verification_run = next(
        (
            run
            for run in builder_input.verification_runs
            if run.verification_run_id.value == verification_run_ref
        ),
        None,
    )
    if verification_run is None:
        raise ProcessAuditError("verified evidence references missing verification runs")
    return verification_run.runner_ref.value



def _evidence_map_payload(builder_input: ProcessAuditBuilderInput) -> dict[str, Any]:
    source_entries_by_evidence: dict[str, list[str]] = {}
    for entry in builder_input.source_inventory.entries:
        for evidence_ref in entry.evidence_refs:
            source_entries_by_evidence.setdefault(evidence_ref.value, []).append(entry.path.value)
    verified_by_ref = {
        evidence.verified_evidence_id.value: evidence for evidence in builder_input.verified_evidence
    }
    rows = []
    for row in builder_input.final_evidence_table.rows:
        evidence_refs = [ref.value for ref in row.verified_evidence_refs]
        verification_refs: list[str] = []
        service_refs: list[str] = []
        live_refs: list[str] = []
        source_inventory_refs: list[str] = []
        for evidence_ref in evidence_refs:
            evidence = verified_by_ref.get(evidence_ref)
            if evidence is not None:
                verification_refs.extend(ref.value for ref in evidence.verification_run_refs)
                service_refs.extend(ref.value for ref in evidence.service_run_refs)
                live_refs.extend(ref.value for ref in evidence.live_blackbox_evidence_refs)
            source_inventory_refs.extend(source_entries_by_evidence.get(evidence_ref, ()))
        rows.append(
            {
                "acceptance_ref": row.acceptance_ref.value,
                "criterion_ref": row.acceptance_ref.value,
                "status": row.status.value,
                "verified_evidence_refs": evidence_refs,
                "source_inventory_refs": sorted(set(source_inventory_refs)),
                "verification_run_refs": sorted(set(verification_refs)),
                "service_run_refs": sorted(set(service_refs)),
                "live_blackbox_evidence_refs": sorted(set(live_refs)),
                "checker_verdict_ref": builder_input.checker_verdict.checker_verdict_id.value,
            }
        )
    return {
        "final_evidence_table_ref": builder_input.final_evidence_table.final_evidence_table_id.value,
        "rows": rows,
    }


def _git_version_audit_markdown(builder_input: ProcessAuditBuilderInput) -> str:
    git_bundle = builder_input.git_version_audit_bundle
    report = git_bundle.report
    fact_set = git_bundle.fact_set
    binding_ids = ", ".join(
        binding.binding_id.value for binding in git_bundle.command_evidence_bindings
    )
    changed_files = (
        ", ".join(file.path for file in fact_set.changed_files)
        if fact_set.changed_files
        else "none"
    )
    return _markdown_lines(
        "# Git Version Audit",
        f"Git bundle id: {git_bundle.git_version_audit_bundle_id.value}",
        f"Git report id: {report.git_version_audit_report_id.value}",
        f"Git hash manifest id: {git_bundle.hash_manifest.hash_manifest_id.value}",
        f"Git fact set id: {fact_set.fact_set_id.value}",
        f"Final commit SHA: {fact_set.final_commit_sha.value}",
        f"Base commit SHA: {fact_set.base_commit_sha.value}",
        f"Git clean status: {fact_set.dirty_status.value}",
        f"Git clean: {report.git_clean}",
        f"Source inventory hash: {fact_set.source_inventory_hash.value}",
        f"Source inventory ref: {report.source_inventory_ref.value}",
        f"Source inventory hash matches: {report.source_inventory_hash_matches}",
        f"Package commit ref: {report.package_commit_ref.value}",
        f"Branch ref: {fact_set.branch_ref.value}",
        f"Worktree ref: {fact_set.worktree_ref.value}",
        f"Package root: {fact_set.package_root}",
        f"Changed files: {changed_files}",
        f"Diff summary ref: {fact_set.diff_summary.diff_summary_id.value}",
        f"Diff summary text: {fact_set.diff_summary.summary_text}",
        f"Final command evidence at final commit: {report.final_command_evidence_at_final_commit}",
        f"Command evidence refs: {', '.join(report.command_evidence_refs)}",
        f"Command binding ids: {binding_ids}",
    )


def _closeout_summary_markdown(builder_input: ProcessAuditBuilderInput) -> str:
    return _markdown_lines(
        "# Closeout Summary",
        f"Package contract: {builder_input.package_contract.package_contract_id.value}",
        f"Source inventory: {builder_input.source_inventory.source_inventory_id.value}",
        f"Final evidence table: {builder_input.final_evidence_table.final_evidence_table_id.value}",
        f"Checker verdict: {builder_input.checker_verdict.checker_verdict_id.value}",
        f"Replay summary hash: {builder_input.replay_readiness.summary_hash.value}",
        "Remaining blockers: none",
    )


def _replay_bundle_report_payload(builder_input: ProcessAuditBuilderInput) -> dict[str, Any]:
    readiness = builder_input.replay_readiness
    return {
        "replay_bundle_ref": builder_input.replay_bundle.replay_bundle_id.value,
        "replay_report_ref": builder_input.replay_bundle.replay_report.replay_report_id.value,
        "projection_kind": builder_input.replay_bundle.replay_report.projection_kind,
        "projection_versions": [version.value for version in readiness.projection_versions],
        "event_range": readiness.event_range.value,
        "summary_hash": readiness.summary_hash.value,
        "hash_chain_verified": readiness.hash_chain_verified,
        "replay_passed": readiness.replay_passed,
    }


def _checked_refs(builder_input: ProcessAuditBuilderInput) -> tuple[str, ...]:
    git_bundle = builder_input.git_version_audit_bundle
    sorted_command_bindings = canonical_sort_for_hash(
        git_bundle.command_evidence_bindings,
        key=lambda binding: binding.verification_run_ref.value,
    )
    refs = [
        builder_input.project_ref.value,
        builder_input.package_contract.package_contract_id.value,
        builder_input.acceptance_contract.acceptance_contract_id.value,
        builder_input.source_inventory.source_inventory_id.value,
        builder_input.workspace_evidence_bundle.workspace_evidence_bundle_id.value,
        builder_input.final_evidence_table.final_evidence_table_id.value,
        builder_input.checker_verdict.checker_verdict_id.value,
        builder_input.checker_verdict.source_diff_ref.value,
        builder_input.package_contract.package_contract_id.value,
        builder_input.replay_bundle.replay_bundle_id.value,
        builder_input.replay_bundle.replay_report.replay_report_id.value,
        builder_input.replay_readiness.summary_hash.value,
        builder_input.replay_readiness.event_range.value,
        builder_input.replay_readiness.payload_manifest_ref.value,
        builder_input.replay_readiness.payload_manifest_hash.value,
        *(version.value for version in builder_input.replay_readiness.projection_versions),
        *REQUIRED_PROCESS_AUDIT_ARTIFACT_PATHS,
        git_bundle.git_version_audit_bundle_id.value,
        git_bundle.report.git_version_audit_report_id.value,
        git_bundle.hash_manifest.hash_manifest_id.value,
        git_bundle.fact_set.fact_set_id.value,
        builder_input.git_audit_readiness.final_commit_sha.value,
        builder_input.git_audit_readiness.source_inventory_hash.value,
        *(binding.binding_id.value for binding in sorted_command_bindings),
        *(binding.run_manifest_ref.value for binding in sorted_command_bindings),
        *(binding.package_contract_ref.value for binding in sorted_command_bindings),
        *(binding.command_id.value for binding in sorted_command_bindings),
        *(binding.source_inventory_hash.value for binding in sorted_command_bindings),
        *(event.event_id.value for event in _audit_events(builder_input)),
        *(
            attempt.value
            for attempt in canonical_sort_for_hash(
                builder_input.provider_attempt_refs,
                key=lambda ref: ref.value,
            )
        ),
        *(
            run.verification_run_id.value
            for run in canonical_sort_for_hash(
                builder_input.verification_runs,
                key=lambda run: run.verification_run_id.value,
            )
        ),
        *(
            service.service_run_evidence_id.value
            for service in canonical_sort_for_hash(
                builder_input.service_runs,
                key=lambda service: service.service_run_evidence_id.value,
            )
        ),
        *(
            service.readiness_url.value
            for service in canonical_sort_for_hash(
                builder_input.service_runs,
                key=lambda service: service.service_run_evidence_id.value,
            )
        ),
        *(
            service.probe_body_sha256.value
            for service in canonical_sort_for_hash(
                builder_input.service_runs,
                key=lambda service: service.service_run_evidence_id.value,
            )
        ),
        *(
            evidence.live_blackbox_evidence_id.value
            for evidence in canonical_sort_for_hash(
                builder_input.live_blackbox_evidence,
                key=lambda evidence: evidence.live_blackbox_evidence_id.value,
            )
        ),
        *(
            evidence.verified_evidence_id.value
            for evidence in canonical_sort_for_hash(
                builder_input.verified_evidence,
                key=lambda evidence: evidence.verified_evidence_id.value,
            )
        ),
        *(
            entry.path.value
            for entry in canonical_sort_for_hash(
                builder_input.source_inventory.entries,
                key=lambda entry: entry.path.value,
            )
        ),
        *canonical_sort_for_hash(
            _agent_context_checked_refs(builder_input.agent_context_index),
            key=lambda ref: ref,
        ),
        *(
            evidence.fallback_decision_record_ref.value
            for evidence in canonical_sort_for_hash(
                (
                    evidence
                    for evidence in builder_input.verified_evidence
                    if evidence.fallback_decision_record_ref is not None
                ),
                key=lambda evidence: evidence.fallback_decision_record_ref.value,
            )
        ),
    ]
    return tuple(dict.fromkeys(refs))


def _agent_context_checked_refs(agent_context_index: BaseModel) -> tuple[str, ...]:
    refs: list[str] = []
    for entry in getattr(agent_context_index, "entries", ()):
        if hasattr(entry, "entry_id"):
            refs.append(_ref_value(getattr(entry, "entry_id")))
        snapshot = getattr(entry, "snapshot", None)
        if snapshot is not None:
            if hasattr(snapshot, "context_snapshot_id"):
                refs.append(_ref_value(getattr(snapshot, "context_snapshot_id")))
            fingerprint = getattr(snapshot, "snapshot_fingerprint", None)
            if fingerprint:
                refs.append(str(fingerprint))
            if getattr(snapshot, "execution_package_ref", None):
                refs.append(_ref_value(snapshot.execution_package_ref))
        refs.extend(_ref_value(ref) for ref in getattr(entry, "provider_attempt_refs", ()))
    return tuple(dict.fromkeys(refs))


def _fallback_decision_refs(builder_input: ProcessAuditBuilderInput) -> tuple[str, ...]:
    return tuple(
        evidence.fallback_decision_record_ref.value
        for evidence in builder_input.verified_evidence
        if evidence.fallback_decision_record_ref is not None
    )


def _process_audit_ref(
    *,
    kind: str,
    project_ref: ProjectRef,
    content_hash: str,
    run_id: str | None,
    artifact_kind: ProcessAuditArtifactKind | None = None,
) -> str:
    return namespaced_ref(
        kind=kind,
        project_ref=project_ref.value,
        content_hash=content_hash,
        run_id=run_id,
        extra_suffix=artifact_kind.value if artifact_kind is not None else None,
    )


def _validate_process_audit_ref_binding(
    value: str,
    *,
    kind: str,
    project_ref: str,
    content_hashes: tuple[str, ...],
    run_id: str | None,
    extra_suffix: str | None,
    field_name: str,
) -> None:
    errors: list[NamespacedRefError] = []
    for content_hash in tuple(dict.fromkeys(content_hashes)):
        try:
            assert_namespaced_ref_binding(
                value,
                kind=kind,
                project_ref=project_ref,
                content_hash=content_hash,
                run_id=run_id,
                extra_suffix=extra_suffix,
                field_name=field_name,
            )
            return
        except NamespacedRefError as error:
            errors.append(error)
    if errors:
        raise errors[0]


def _validate_process_audit_artifact_namespace(
    artifact: ProcessAuditArtifact,
    *,
    project_ref: ProjectRef,
    run_id: str | None,
    content_hashes: tuple[str, ...],
) -> None:
    try:
        _validate_process_audit_ref_binding(
            artifact.artifact_id.value,
            kind="process-audit-artifact",
            project_ref=project_ref.value,
            content_hashes=content_hashes,
            run_id=run_id,
            extra_suffix=artifact.kind.value if run_id is not None else None,
            field_name="process audit artifact ref",
        )
        _validate_process_audit_ref_binding(
            artifact.content_ref.value,
            kind="process-audit-content",
            project_ref=project_ref.value,
            content_hashes=content_hashes,
            run_id=run_id,
            extra_suffix=artifact.kind.value if run_id is not None else None,
            field_name="process audit content ref",
        )
    except NamespacedRefError as error:
        raise ProcessAuditError(str(error)) from error


def _run_id_from_process_audit_ref(
    value: str,
    *,
    expected_kind: str,
    field_name: str,
) -> str | None:
    parts = value.split(".")
    if len(parts) == 3:
        return None
    if len(parts) == 5 and parts[0] == expected_kind:
        return parts[3]
    raise ProcessAuditError(f"{field_name} namespace binding mismatch")


def _namespace_content_hashes(
    *,
    bundle: ProcessAuditBundle,
    artifact: ProcessAuditArtifact,
) -> tuple[str, ...]:
    hashes = [artifact.sha256.value]
    entry = bundle.artifact_manifest.entries_by_path.get(artifact.path.value)
    if entry is not None:
        hashes.append(entry.sha256.value)
    hash_manifest_value = bundle.hash_manifest.artifact_hashes.get(artifact.path.value)
    if hash_manifest_value is not None:
        hashes.append(hash_manifest_value.value)
    return tuple(dict.fromkeys(hashes))


def _validate_artifact_namespaces(bundle: ProcessAuditBundle) -> str | None:
    run_ids: set[str | None] = set()
    for artifact in bundle.artifacts:
        run_id = _run_id_from_process_audit_ref(
            artifact.artifact_id.value,
            expected_kind="process-audit-artifact",
            field_name="process audit artifact ref",
        )
        run_ids.add(run_id)
        _validate_process_audit_artifact_namespace(
            artifact,
            project_ref=bundle.project_ref,
            run_id=run_id,
            content_hashes=_namespace_content_hashes(bundle=bundle, artifact=artifact),
        )
    if len(run_ids) != 1:
        raise ProcessAuditError("process audit artifact ref namespace binding mismatch")
    return next(iter(run_ids))


def _validate_manifest_entry_namespaces(bundle: ProcessAuditBundle, run_id: str | None) -> None:
    artifacts_by_path = {artifact.path.value: artifact for artifact in bundle.artifacts}
    for entry in bundle.artifact_manifest.entries:
        artifact = artifacts_by_path[entry.path.value]
        content_hashes = tuple(dict.fromkeys((artifact.sha256.value, entry.sha256.value)))
        try:
            _validate_process_audit_ref_binding(
                entry.artifact_ref.value,
                kind="process-audit-artifact",
                project_ref=bundle.project_ref.value,
                content_hashes=content_hashes,
                run_id=run_id,
                extra_suffix=artifact.kind.value if run_id is not None else None,
                field_name="process audit artifact ref",
            )
            _validate_process_audit_ref_binding(
                entry.content_ref.value,
                kind="process-audit-content",
                project_ref=bundle.project_ref.value,
                content_hashes=content_hashes,
                run_id=run_id,
                extra_suffix=artifact.kind.value if run_id is not None else None,
                field_name="process audit content ref",
            )
        except NamespacedRefError as error:
            raise ProcessAuditError(str(error)) from error


def _validate_bundle_instance(bundle: ProcessAuditBundle) -> ProcessAuditBundle:
    if not isinstance(bundle, ProcessAuditBundle):
        raise ProcessAuditError("bundle must be ProcessAuditBundle")
    return ProcessAuditBundle.model_validate(
        bundle.model_dump(mode="python", exclude={"bundle_hash"})
    )


def _validate_bundle_shape(bundle: ProcessAuditBundle) -> None:
    if len(bundle.artifacts) != len(REQUIRED_PROCESS_AUDIT_ARTIFACT_PATHS):
        raise ProcessAuditError("process audit artifacts must cover every required artifact")
    paths = [artifact.path.value for artifact in bundle.artifacts]
    if set(paths) != _REQUIRED_PATH_SET:
        raise ProcessAuditError("process audit artifact paths must match required artifact paths")
    if len(set(paths)) != len(paths):
        raise ProcessAuditError("process audit artifact paths must be unique")
    kinds = [artifact.kind for artifact in bundle.artifacts]
    if len(set(kinds)) != len(kinds):
        raise ProcessAuditError("process audit artifact kinds must be unique")
    if bundle.project_ref != bundle.artifact_manifest.project_ref:
        raise ProcessAuditError("bundle project_ref must match artifact manifest")
    if bundle.project_ref != bundle.hash_manifest.project_ref:
        raise ProcessAuditError("bundle project_ref must match hash manifest")
    if bundle.project_ref != bundle.process_audit_report.project_ref:
        raise ProcessAuditError("bundle project_ref must match process audit report")


def _revalidate_artifact_manifest(bundle: ProcessAuditBundle) -> None:
    artifacts_by_path = {artifact.path.value: artifact for artifact in bundle.artifacts}
    entries_by_path = bundle.artifact_manifest.entries_by_path
    if set(artifacts_by_path) != _REQUIRED_PATH_SET:
        raise ProcessAuditError("artifact manifest requires all process audit artifacts")
    if set(entries_by_path) != set(artifacts_by_path):
        raise ProcessAuditError("artifact manifest paths must match artifacts")
    for path, artifact in artifacts_by_path.items():
        entry = entries_by_path[path]
        if entry.artifact_ref != artifact.artifact_id:
            raise ProcessAuditError("artifact manifest artifact ref mismatch")
        if entry.kind is not artifact.kind:
            raise ProcessAuditError("artifact manifest kind mismatch")
        if entry.format is not artifact.format:
            raise ProcessAuditError("artifact manifest format mismatch")
        if entry.content_ref != artifact.content_ref:
            raise ProcessAuditError("artifact manifest content ref mismatch")
        if entry.sha256 != artifact.sha256:
            raise ProcessAuditError("artifact manifest hash mismatch; hash manifest stale")


def _revalidate_hash_manifest(bundle: ProcessAuditBundle) -> None:
    expected_artifact_hashes = {
        artifact.path.value: artifact.sha256.value for artifact in bundle.artifacts
    }
    actual_artifact_hashes = {
        path: value.value for path, value in bundle.hash_manifest.artifact_hashes.items()
    }
    if actual_artifact_hashes != expected_artifact_hashes:
        raise ProcessAuditError("hash manifest artifact hash mismatch")
    if bundle.hash_manifest.artifact_manifest_hash.value != _hash_model(bundle.artifact_manifest):
        raise ProcessAuditError("hash manifest artifact_manifest_hash mismatch")
    if bundle.hash_manifest.process_audit_report_hash.value != _hash_model(bundle.process_audit_report):
        raise ProcessAuditError("hash manifest process_audit_report_hash mismatch")
    expected_bundle_payload_hash = _hash_bundle_payload(
        process_audit_bundle_id=bundle.process_audit_bundle_id,
        project_ref=bundle.project_ref,
        generated_at=bundle.generated_at,
        artifacts=bundle.artifacts,
        artifact_manifest=bundle.artifact_manifest,
        hash_manifest_without_bundle_hash={
            "hash_manifest_id": bundle.hash_manifest.hash_manifest_id,
            "project_ref": bundle.hash_manifest.project_ref,
            "artifact_hashes": bundle.hash_manifest.artifact_hashes,
            "artifact_manifest_hash": bundle.hash_manifest.artifact_manifest_hash,
            "process_audit_report_hash": bundle.hash_manifest.process_audit_report_hash,
        },
        process_audit_report=bundle.process_audit_report,
        checked_refs=bundle.checked_refs,
    )
    if bundle.hash_manifest.bundle_payload_hash.value != expected_bundle_payload_hash:
        raise ProcessAuditError("hash manifest bundle payload hash mismatch")


def _hash_bundle_payload(
    *,
    process_audit_bundle_id: ProcessAuditBundleRef,
    project_ref: ProjectRef,
    generated_at: datetime,
    artifacts: tuple[ProcessAuditArtifact, ...],
    artifact_manifest: ProcessAuditArtifactManifest,
    hash_manifest_without_bundle_hash: Mapping[str, Any],
    process_audit_report: ProcessAuditReport,
    checked_refs: tuple[str, ...],
) -> str:
    return _hash_jsonable(
        {
            "version": 1,
            "process_audit_bundle_id": process_audit_bundle_id,
            "project_ref": project_ref,
            "generated_at": generated_at.isoformat(),
            "artifacts": [artifact.model_dump(mode="json") for artifact in artifacts],
            "artifact_manifest": artifact_manifest.model_dump(mode="json"),
            "hash_manifest": _canonical_jsonable(hash_manifest_without_bundle_hash),
            "process_audit_report": process_audit_report.model_dump(mode="json"),
            "checked_refs": checked_refs,
        }
    )


def _validate_report_alignment(bundle: ProcessAuditBundle) -> None:
    report = bundle.process_audit_report
    artifact_refs = {artifact.artifact_id.value for artifact in bundle.artifacts}
    report_refs = {
        report.process_audit_ref.value,
        report.timeline_ref.value,
        report.decision_log_ref.value,
        report.agent_context_index_ref.value,
        report.ticket_graph_ref.value,
        report.artifact_lineage_ref.value,
        report.evidence_map_ref.value,
        report.git_audit_ref.value,
        report.closeout_summary_ref.value,
        report.replay_bundle_report_ref.value,
    }
    if artifact_refs != report_refs:
        raise ProcessAuditError("process audit report must index all artifacts")
    if tuple(report.checked_refs) != tuple(bundle.checked_refs):
        raise ProcessAuditError("process audit report checked_refs mismatch")


def _artifact_by_kind(
    bundle: ProcessAuditBundle, kind: ProcessAuditArtifactKind
) -> ProcessAuditArtifact:
    for artifact in bundle.artifacts:
        if artifact.kind is kind:
            return artifact
    raise ProcessAuditError(f"missing process audit artifact: {kind.value}")


def _validate_timeline(bundle: ProcessAuditBundle) -> None:
    artifact = _artifact_by_kind(bundle, ProcessAuditArtifactKind.TIMELINE)
    content = artifact.content
    if not isinstance(content, dict) or not isinstance(content.get("events"), list | tuple):
        raise ProcessAuditError("timeline key events must be present")
    kinds = {str(event.get("kind")) for event in content["events"] if isinstance(event, dict)}
    missing = _REQUIRED_TIMELINE_EVENT_KINDS - kinds
    if missing:
        raise ProcessAuditError(f"timeline missing key event: {sorted(missing)[0]}")


def _validate_decision_log(bundle: ProcessAuditBundle) -> None:
    artifact = _artifact_by_kind(bundle, ProcessAuditArtifactKind.DECISION_LOG)
    content = str(artifact.content)
    if "## CEO / Human Board Decision" not in content or "CEO / human board" not in content:
        raise ProcessAuditError("decision log must include CEO / human board decision")


def _validate_agent_context_index(bundle: ProcessAuditBundle) -> None:
    artifact = _artifact_by_kind(bundle, ProcessAuditArtifactKind.AGENT_CONTEXT_INDEX)
    content = artifact.content
    if not isinstance(content, dict) or not content.get("entries"):
        raise ProcessAuditError("agent context index entries must not be empty")
    for entry in content["entries"]:
        if not isinstance(entry, dict):
            raise ProcessAuditError("agent context index entries must be objects")
        if not entry.get("execution_package_ref"):
            raise ProcessAuditError("agent context index missing execution_package_ref")
        if not entry.get("model_execution_profile"):
            raise ProcessAuditError("agent context index missing model_execution_profile")
        if not entry.get("provider_attempt_refs"):
            raise ProcessAuditError("agent context index missing provider_attempt_refs")


def _validate_artifact_lineage_ref_container(value: Any) -> None:
    if not isinstance(value, list | tuple) or not value:
        raise ProcessAuditError("artifact lineage missing producer attempt or closeout link")
    if any(not isinstance(item, str) or not item for item in value):
        raise ProcessAuditError("artifact lineage missing producer attempt or closeout link")


def _validate_artifact_lineage_evidence_bindings(lineage: dict[str, Any]) -> None:
    bindings = lineage["evidence_bindings"]
    if not isinstance(bindings, list | tuple) or not bindings:
        raise ProcessAuditError("artifact lineage missing producer attempt or closeout link")
    binding_refs: list[str] = []
    for binding in bindings:
        if not isinstance(binding, dict) or not (
            _LINEAGE_EVIDENCE_BINDING_REQUIRED_FIELDS <= set(binding)
        ):
            raise ProcessAuditError("artifact lineage missing producer attempt or closeout link")
        if any(
            not isinstance(binding[field], str) or not binding[field]
            for field in _LINEAGE_EVIDENCE_BINDING_REQUIRED_TEXT_FIELDS
        ):
            raise ProcessAuditError("artifact lineage missing producer attempt or closeout link")
        verification_run_ref = binding["verification_run_ref"]
        if verification_run_ref is not None and (
            not isinstance(verification_run_ref, str) or not verification_run_ref
        ):
            raise ProcessAuditError("artifact lineage missing producer attempt or closeout link")
        for field in ("service_run_refs", "live_blackbox_evidence_refs"):
            refs = binding[field]
            if not isinstance(refs, list | tuple):
                raise ProcessAuditError("artifact lineage missing producer attempt or closeout link")
            if any(not isinstance(ref, str) or not ref for ref in refs):
                raise ProcessAuditError("artifact lineage missing producer attempt or closeout link")
        if (
            verification_run_ref is None
            and not binding["service_run_refs"]
            and not binding["live_blackbox_evidence_refs"]
        ):
            raise ProcessAuditError("artifact lineage missing producer attempt or closeout link")
        if (
            verification_run_ref is not None
            and binding["verifier_ref"] == verification_run_ref
        ):
            raise ProcessAuditError(
                "artifact lineage evidence bindings must distinguish verifier and verification run"
            )
        binding_refs.append(binding["verified_evidence_ref"])
    if sorted(binding_refs) != sorted(lineage["evidence_refs"]):
        raise ProcessAuditError("artifact lineage evidence bindings must match evidence_refs")


def _validate_artifact_lineage(bundle: ProcessAuditBundle) -> None:
    artifact = _artifact_by_kind(bundle, ProcessAuditArtifactKind.ARTIFACT_LINEAGE)
    evidence_map_artifact = _artifact_by_kind(bundle, ProcessAuditArtifactKind.EVIDENCE_MAP)
    content = artifact.content
    if not isinstance(content, dict):
        raise ProcessAuditError("artifact lineage content must be an object")
    if content.get("checker_verdict_ref") != bundle.process_audit_report.checked_refs[6]:
        raise ProcessAuditError("artifact lineage missing producer attempt or closeout link")
    lineages = content.get("lineages")
    if not lineages:
        raise ProcessAuditError("artifact lineage must include producer attempt lineage")
    seen_primary_paths: set[str] = set()
    for lineage in lineages:
        if not isinstance(lineage, dict) or not _LINEAGE_REQUIRED_FIELDS <= set(lineage):
            raise ProcessAuditError("artifact lineage missing producer attempt or closeout link")
        if any(not lineage[field] for field in _LINEAGE_REQUIRED_FIELDS):
            raise ProcessAuditError("artifact lineage missing producer attempt or closeout link")
        path = lineage["path"]
        if not isinstance(path, str) or not path:
            raise ProcessAuditError("artifact lineage missing producer attempt or closeout link")
        if path in seen_primary_paths:
            raise ProcessAuditError("artifact lineage primary rows must be unique")
        seen_primary_paths.add(path)
        for tuple_field in ("consumer_ticket_refs", "acceptance_refs", "evidence_refs"):
            _validate_artifact_lineage_ref_container(lineage[tuple_field])
        if lineage["evidence_map_ref"] != evidence_map_artifact.artifact_id.value:
            raise ProcessAuditError("artifact lineage missing producer attempt or closeout link")
        _validate_artifact_lineage_evidence_bindings(lineage)
    expected_lineages = bundle.process_audit_report.expected_artifact_lineage_rows
    if _canonical_jsonable(tuple(lineages)) != _canonical_jsonable(expected_lineages):
        raise ProcessAuditError(
            "artifact lineage inconsistent with expected source inventory lineage"
        )
    expected_fallback_refs = set(bundle.process_audit_report.expected_fallback_decision_refs)
    expected_fallback_recorded_refs = {
        lineage["fallback_decision_record_ref"]: lineage["fallback_decision_recorded_ref"]
        for lineage in bundle.process_audit_report.expected_fallback_lineage_rows
    }
    fallback_lineages = content.get("fallback_lineages") or ()
    actual_fallback_refs: list[str] = []
    actual_fallback_recorded_refs: dict[str, str | None] = {}
    for lineage in fallback_lineages:
        if not isinstance(lineage, dict) or not _FALLBACK_LINEAGE_REQUIRED_FIELDS <= set(lineage):
            raise ProcessAuditError("fallback lineage missing decision record")
        if any(not lineage[field] for field in _FALLBACK_LINEAGE_REQUIRED_NONEMPTY_FIELDS):
            raise ProcessAuditError("fallback lineage missing decision record")
        decision_ref = lineage["fallback_decision_record_ref"]
        if lineage["evidence_map_ref"] != evidence_map_artifact.artifact_id.value:
            raise ProcessAuditError("fallback lineage missing decision record")
        actual_fallback_refs.append(decision_ref)
        actual_fallback_recorded_refs[decision_ref] = lineage.get(
            "fallback_decision_recorded_ref"
        )
    if len(set(actual_fallback_refs)) != len(actual_fallback_refs):
        raise ProcessAuditError(
            "fallback lineage decision refs must match expected fallback decisions"
        )
    if (
        set(actual_fallback_refs) != expected_fallback_refs
        or actual_fallback_recorded_refs != expected_fallback_recorded_refs
    ):
        raise ProcessAuditError(
            "fallback lineage decision refs must match expected fallback decisions"
        )


def _validate_evidence_map(bundle: ProcessAuditBundle) -> None:
    artifact = _artifact_by_kind(bundle, ProcessAuditArtifactKind.EVIDENCE_MAP)
    content = artifact.content
    if not isinstance(content, dict) or not isinstance(content.get("rows"), list | tuple):
        raise ProcessAuditError("evidence map rows must match final evidence table")
    actual_rows = tuple(content["rows"])
    expected_rows = bundle.process_audit_report.expected_evidence_map_rows
    if _canonical_jsonable(actual_rows) != _canonical_jsonable(expected_rows):
        raise ProcessAuditError("evidence map inconsistent with final evidence table verified_evidence_refs")


def _validate_git_version_audit(bundle: ProcessAuditBundle) -> None:
    artifact = _artifact_by_kind(bundle, ProcessAuditArtifactKind.GIT_VERSION_AUDIT)
    content = str(artifact.content)
    required_labels = (
        "Final commit SHA",
        "Git clean status",
        "Source inventory hash",
    )
    for label in required_labels:
        if label not in content:
            raise ProcessAuditError(f"git audit missing {label.lower()}")


def _validate_replay_bundle_report(bundle: ProcessAuditBundle) -> None:
    artifact = _artifact_by_kind(bundle, ProcessAuditArtifactKind.REPLAY_BUNDLE_REPORT)
    content = artifact.content
    if not isinstance(content, dict):
        raise ProcessAuditError("replay bundle report must be an object")
    report = bundle.process_audit_report
    if content.get("summary_hash") != report.replay_summary_hash:
        raise ProcessAuditError("replay bundle report summary_hash mismatch")
    if tuple(content.get("projection_versions", ())) != report.replay_projection_versions:
        raise ProcessAuditError("replay bundle report projection version mismatch")
    if content.get("replay_passed") is not True or content.get("hash_chain_verified") is not True:
        raise ProcessAuditError("replay bundle report must prove replay readiness")


def _validate_agent_context_index_payload(payload: dict[str, Any]) -> None:
    if not payload.get("entries"):
        raise ProcessAuditError("agent context index entries must not be empty")
    for entry in payload["entries"]:
        if not entry.get("execution_package_ref"):
            raise ProcessAuditError("agent context index missing execution_package_ref")
        if not entry.get("model_execution_profile"):
            raise ProcessAuditError("agent context index missing model_execution_profile")
        if not entry.get("provider_attempt_refs"):
            raise ProcessAuditError("agent context index missing provider_attempt_refs")


__all__ = [
    "REQUIRED_PROCESS_AUDIT_ARTIFACT_PATHS",
    "ProcessAuditArtifact",
    "ProcessAuditArtifactFormat",
    "ProcessAuditArtifactKind",
    "ProcessAuditArtifactManifest",
    "ProcessAuditArtifactManifestEntry",
    "ProcessAuditArtifactRef",
    "ProcessAuditBundle",
    "ProcessAuditBundleRef",
    "ProcessAuditBuilderInput",
    "ProcessAuditCheckedRef",
    "ProcessAuditContentHash",
    "ProcessAuditContentRef",
    "ProcessAuditError",
    "ProcessAuditHashManifest",
    "ProcessAuditManifestRef",
    "ProcessAuditReport",
    "ProcessAuditReportRef",
    "build_process_audit_bundle",
    "process_audit_readiness",
]
