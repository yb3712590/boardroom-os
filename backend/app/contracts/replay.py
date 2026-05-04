from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field

from app.contracts.common import JsonValue, StrictModel


ReplayStatus = Literal["READY", "FAILED"]


class ReplayResumeRequest(StrictModel):
    resume_kind: str
    event_cursor: str | None
    graph_version: str | None = None
    expected_graph_patch_hash: str | None = None
    ticket_id: str | None = None
    incident_id: str | None = None
    projection_version: int | None
    event_range: dict[str, int] | None
    schema_version: str
    contract_version: str
    request_hash: str
    diagnostic: dict[str, JsonValue]


class ReplayWatermark(StrictModel):
    resume_kind: str
    event_cursor: str
    projection_version: int
    event_range: dict[str, int]
    schema_version: str
    contract_version: str
    event_log_hash: str
    request_hash: str
    watermark_hash: str


class ReplayCheckpoint(StrictModel):
    checkpoint_id: str
    checkpoint_version: str
    event_watermark: ReplayWatermark
    projection_version: int
    schema_version: str
    contract_version: str
    invalidated_by: list[str]
    created_at: datetime
    checkpoint_hash: str
    covered_projections: tuple[str, ...]
    compatibility: dict[str, JsonValue]
    projection_payloads: dict[str, list[dict[str, JsonValue]]]


class ReplayHashManifest(StrictModel):
    status: ReplayStatus
    source_event_range: dict[str, int] | None
    checkpoint_refs: list[dict[str, JsonValue]]
    artifact_refs: list[str]
    storage_refs: list[dict[str, JsonValue]]
    content_hashes: dict[str, str | None]
    materialization_status: dict[str, str]
    document_materialized_views: dict[str, JsonValue]
    diagnostics: list[dict[str, JsonValue]]
    replay_compatibility: dict[str, JsonValue]
    manifest_hash: str


class ReplayBundleReport(StrictModel):
    status: ReplayStatus
    resume_source: dict[str, JsonValue]
    source_event_range: dict[str, int] | None
    checkpoint_watermark: dict[str, JsonValue] | None
    checkpoint_refs: list[dict[str, JsonValue]]
    projection_version: int | None
    artifact_hash_manifest: dict[str, JsonValue]
    document_materialized_views: dict[str, JsonValue]
    diagnostics: dict[str, JsonValue]
    replay_compatibility: dict[str, JsonValue]
    report_hash: str


class ReplayImportManifest(StrictModel):
    status: ReplayStatus
    manifest_version: str
    input_db_path: str
    artifact_root: str
    log_refs: list[str]
    input_hashes: dict[str, JsonValue]
    schema: dict[str, JsonValue]
    event_range: dict[str, int] | None
    event_count: int
    workflow_ids: list[str]
    artifact_count: int
    local_file_artifact_count: int
    inline_db_artifact_count: int
    import_diagnostics: list[dict[str, JsonValue]]
    idempotency_key: str
    manifest_hash: str


class ReplayCaseResult(StrictModel):
    case_id: str
    status: ReplayStatus
    source_manifest_hash: str
    event_range: dict[str, int] | None
    provider_failure_kind: str | None
    attempt_refs: list[dict[str, JsonValue]]
    raw_archive_refs: list[str]
    source_ticket_context: dict[str, JsonValue]
    provider_provenance: dict[str, JsonValue]
    retry_recovery_outcome: dict[str, JsonValue]
    late_event_guard: dict[str, JsonValue]
    diagnostics: list[dict[str, JsonValue]]
    issue_classification: str
    br_id: str | None = None
    contract_findings: list[dict[str, JsonValue]] = Field(default_factory=list)
    rework_incident_outcome: dict[str, JsonValue] = Field(default_factory=dict)
    evidence_refs: dict[str, JsonValue] = Field(default_factory=dict)
    contract_gate: dict[str, JsonValue] = Field(default_factory=dict)
    rework_target: dict[str, JsonValue] = Field(default_factory=dict)
    graph_terminal_override_used: bool = False
    graph_pointer_summary: dict[str, JsonValue] = Field(default_factory=dict)
    policy_proposal: dict[str, JsonValue] = Field(default_factory=dict)
    graph_diagnostics: list[dict[str, JsonValue]] = Field(default_factory=list)
    effective_edge_summary: dict[str, JsonValue] = Field(default_factory=dict)


class ReplayResumeResult(StrictModel):
    status: ReplayStatus
    resume_request: ReplayResumeRequest
    replay_watermark: ReplayWatermark | None
    event_cursor: str | None
    projection_version: int | None
    event_range: dict[str, int] | None
    schema_version: str
    contract_version: str
    projection_summary: dict[str, JsonValue] | None = None
    diagnostic: dict[str, JsonValue]
