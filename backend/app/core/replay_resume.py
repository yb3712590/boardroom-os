from __future__ import annotations

import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from datetime import datetime
from typing import Any

from app.contracts.replay import (
    ReplayBundleReport,
    ReplayCheckpoint,
    ReplayHashManifest,
    ReplayResumeRequest,
    ReplayResumeResult,
    ReplayWatermark,
)
from app.core.constants import (
    ACTOR_STATUS_ACTIVE,
    BLOCKING_REASON_BOARD_REJECTED,
    BLOCKING_REASON_BOARD_REVIEW_REQUIRED,
    BLOCKING_REASON_MODIFY_CONSTRAINTS,
    BLOCKING_REASON_PROVIDER_REQUIRED,
    EVENT_BOARD_REVIEW_APPROVED,
    EVENT_BOARD_REVIEW_REJECTED,
    EVENT_BOARD_REVIEW_REQUIRED,
    EVENT_CIRCUIT_BREAKER_CLOSED,
    EVENT_CIRCUIT_BREAKER_OPENED,
    EVENT_EMPLOYEE_FROZEN,
    EVENT_EMPLOYEE_HIRED,
    EVENT_EMPLOYEE_REPLACED,
    EVENT_EMPLOYEE_RESTORED,
    EVENT_ACTOR_DEACTIVATED,
    EVENT_ACTOR_ENABLED,
    EVENT_ACTOR_REPLACED,
    EVENT_ACTOR_SUSPENDED,
    EVENT_GRAPH_PATCH_APPLIED,
    EVENT_INCIDENT_CLOSED,
    EVENT_INCIDENT_OPENED,
    EVENT_INCIDENT_RECOVERY_STARTED,
    EVENT_MEETING_CONCLUDED,
    EVENT_MEETING_REQUESTED,
    EVENT_MEETING_STARTED,
    EVENT_PROVIDER_ATTEMPT_FINISHED,
    EVENT_PROVIDER_ATTEMPT_HEARTBEAT_RECORDED,
    EVENT_PROVIDER_ATTEMPT_STARTED,
    EVENT_PROVIDER_ATTEMPT_TIMED_OUT,
    EVENT_PROVIDER_FIRST_TOKEN_RECEIVED,
    EVENT_TICKET_ASSIGNED,
    EVENT_TICKET_CANCELLED,
    EVENT_TICKET_CANCEL_REQUESTED,
    EVENT_TICKET_COMPLETED,
    EVENT_TICKET_CREATED,
    EVENT_TICKET_EXECUTION_PRECONDITION_BLOCKED,
    EVENT_TICKET_EXECUTION_PRECONDITION_CLEARED,
    EVENT_TICKET_FAILED,
    EVENT_TICKET_HEARTBEAT_RECORDED,
    EVENT_TICKET_LEASED,
    EVENT_TICKET_LEASE_GRANTED,
    EVENT_TICKET_RETRY_SCHEDULED,
    EVENT_TICKET_STARTED,
    EVENT_TICKET_TIMED_OUT,
    EVENT_WORKFLOW_CREATED,
    NODE_STATUS_BLOCKED_FOR_BOARD_REVIEW,
    NODE_STATUS_CANCELLED,
    NODE_STATUS_CANCEL_REQUESTED,
    NODE_STATUS_COMPLETED,
    NODE_STATUS_EXECUTING,
    NODE_STATUS_PENDING,
    NODE_STATUS_REWORK_REQUIRED,
    SCHEMA_VERSION,
    TICKET_STATUS_BLOCKED_FOR_BOARD_REVIEW,
    TICKET_STATUS_CANCELLED,
    TICKET_STATUS_CANCEL_REQUESTED,
    TICKET_STATUS_COMPLETED,
    TICKET_STATUS_EXECUTING,
    TICKET_STATUS_FAILED,
    TICKET_STATUS_LEASED,
    TICKET_STATUS_PENDING,
    TICKET_STATUS_REWORK_REQUIRED,
    TICKET_STATUS_TIMED_OUT,
)
from app.core.graph_identity import GraphIdentityResolutionError, resolve_ticket_graph_identity
from app.core.runtime_node_views import RuntimeNodeViewResolutionError, build_runtime_graph_node_views
from app.core.ticket_graph import build_ticket_graph_snapshot
from app.core.workflow_progression import (
    ProgressionSnapshot,
    evaluate_progression_graph,
    recommended_incident_followup_action_from_policy_input,
)
from app.core.reducer import (
    rebuild_actor_projections,
    rebuild_assignment_projections,
    rebuild_employee_projections,
    rebuild_execution_attempt_projections,
    rebuild_incident_projections,
    rebuild_lease_projections,
    rebuild_node_projections,
    rebuild_process_asset_index,
    rebuild_runtime_node_projections,
    rebuild_ticket_projections,
    rebuild_workflow_projections,
)
from app.core.planned_placeholder_projection import rebuild_planned_placeholder_projections
from app.db.repository import ControlPlaneRepository
from app.core.artifact_store import ArtifactStore

REPLAY_RESUME_CONTRACT_VERSION = "replay-resume.v1"
REPLAY_CHECKPOINT_VERSION = "replay-checkpoint.v1"
RESUME_KIND_EVENT_ID = "event_id"
RESUME_KIND_GRAPH_VERSION = "graph_version"
RESUME_KIND_TICKET_ID = "ticket_id"
RESUME_KIND_INCIDENT_ID = "incident_id"
DEFAULT_REPLAY_CHECKPOINT_PROJECTIONS = (
    "workflow",
    "ticket",
    "assignment",
    "lease",
    "node",
    "runtime_node",
    "execution_attempt",
    "actor",
    "employee",
    "incident",
    "process_asset",
    "planned_placeholder",
)
DEFAULT_REPLAY_CHECKPOINT_COMPATIBILITY = {
    "projection_reducer": "reducer.v1",
    "checkpoint_payload": REPLAY_CHECKPOINT_VERSION,
    "artifact_hash_manifest_ref": None,
    "replay_bundle_report_ref": None,
}
DEFAULT_REPLAY_HASH_COMPATIBILITY = {
    "artifact_hash_manifest": "replay-hash-manifest.v1",
    "replay_bundle_report": "replay-bundle-report.v1",
    "document_materialized_view": "DEFERRED_TO_ROUND_10F",
}
_TERMINAL_TICKET_STATUSES = {"CANCELLED", "COMPLETED", "FAILED", "TIMED_OUT"}
_IN_FLIGHT_TICKET_STATUSES = {"LEASED", "EXECUTING"}
_TERMINAL_ATTEMPT_STATES = {"COMPLETED", "FAILED_RETRYABLE", "FAILED_TERMINAL", "TIMED_OUT"}

_GRAPH_MUTATION_EVENTS = {
    EVENT_WORKFLOW_CREATED,
    EVENT_TICKET_CREATED,
    EVENT_TICKET_COMPLETED,
    EVENT_TICKET_CANCELLED,
    EVENT_BOARD_REVIEW_REQUIRED,
    EVENT_BOARD_REVIEW_APPROVED,
    EVENT_BOARD_REVIEW_REJECTED,
    EVENT_GRAPH_PATCH_APPLIED,
    EVENT_MEETING_REQUESTED,
    EVENT_MEETING_STARTED,
    EVENT_MEETING_CONCLUDED,
}


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _event_payload(event: dict[str, Any]) -> dict[str, Any]:
    payload = event.get("payload")
    if isinstance(payload, dict):
        return payload
    payload_json = event.get("payload_json")
    if isinstance(payload_json, str):
        return json.loads(payload_json)
    return {}


def _json_safe(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    return value


def _normalize_occurred_at(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _normalize_event_for_hash(event: dict[str, Any]) -> dict[str, Any]:
    return {
        "sequence_no": int(event["sequence_no"]),
        "event_id": str(event["event_id"]),
        "event_type": str(event["event_type"]),
        "workflow_id": event.get("workflow_id"),
        "occurred_at": _normalize_occurred_at(event.get("occurred_at")),
        "payload": _event_payload(event),
    }


def _failed_result(
    request: ReplayResumeRequest,
    *,
    reason_code: str,
    message: str,
    details: dict[str, Any] | None = None,
) -> ReplayResumeResult:
    diagnostic = {
        "reason_code": reason_code,
        "message": message,
        **(details or {}),
    }
    return ReplayResumeResult(
        status="FAILED",
        resume_request=request,
        replay_watermark=None,
        event_cursor=request.event_cursor,
        projection_version=request.projection_version,
        event_range=None,
        schema_version=request.schema_version,
        contract_version=request.contract_version,
        projection_summary=None,
        diagnostic=diagnostic,
    )


def build_replay_resume_request(
    *,
    resume_kind: str,
    event_cursor: str | None,
    projection_version: int | None,
    graph_version: str | None = None,
    expected_graph_patch_hash: str | None = None,
    ticket_id: str | None = None,
    incident_id: str | None = None,
    event_range: dict[str, int] | None = None,
    schema_version: str = SCHEMA_VERSION,
    contract_version: str = REPLAY_RESUME_CONTRACT_VERSION,
    diagnostic: dict[str, Any] | None = None,
) -> ReplayResumeRequest:
    request_payload = {
        "resume_kind": resume_kind,
        "event_cursor": event_cursor,
        "graph_version": graph_version,
        "expected_graph_patch_hash": expected_graph_patch_hash,
        "ticket_id": ticket_id,
        "incident_id": incident_id,
        "projection_version": projection_version,
        "event_range": event_range,
        "schema_version": schema_version,
        "contract_version": contract_version,
        "diagnostic": diagnostic or {},
    }
    return ReplayResumeRequest(
        **request_payload,
        request_hash=_sha256(request_payload),
    )


def _normalize_replay_resume_request(
    request: ReplayResumeRequest,
    **updates: Any,
) -> ReplayResumeRequest:
    request_payload = {
        "resume_kind": request.resume_kind,
        "event_cursor": request.event_cursor,
        "graph_version": request.graph_version,
        "expected_graph_patch_hash": request.expected_graph_patch_hash,
        "ticket_id": request.ticket_id,
        "incident_id": request.incident_id,
        "projection_version": request.projection_version,
        "event_range": request.event_range,
        "schema_version": request.schema_version,
        "contract_version": request.contract_version,
        "diagnostic": dict(request.diagnostic),
    }
    request_payload.update(updates)
    return ReplayResumeRequest(
        **request_payload,
        request_hash=_sha256(request_payload),
    )


def _event_log_hash(events: list[dict[str, Any]]) -> str:
    return _sha256([_normalize_event_for_hash(event) for event in events])


def _checkpoint_hash_payload(checkpoint: ReplayCheckpoint | dict[str, Any]) -> dict[str, Any]:
    if isinstance(checkpoint, ReplayCheckpoint):
        payload = checkpoint.model_dump(mode="json")
    else:
        payload = dict(checkpoint)
    payload.pop("checkpoint_id", None)
    payload.pop("checkpoint_hash", None)
    payload.pop("invalidated_by", None)
    payload.pop("created_at", None)
    return payload


def _checkpoint_hash(checkpoint: ReplayCheckpoint | dict[str, Any]) -> str:
    return _sha256(_checkpoint_hash_payload(checkpoint))


def _checkpoint_refs(checkpoint: ReplayCheckpoint | None) -> list[dict[str, Any]]:
    if checkpoint is None:
        return []
    return [
        {
            "checkpoint_id": checkpoint.checkpoint_id,
            "checkpoint_hash": checkpoint.checkpoint_hash,
            "event_cursor": checkpoint.event_watermark.event_cursor,
            "watermark_hash": checkpoint.event_watermark.watermark_hash,
            "projection_version": checkpoint.projection_version,
        }
    ]


def _document_materialized_views_deferred() -> dict[str, Any]:
    return {
        "status": "DEFERRED_TO_ROUND_10F",
        "entries": [],
        "diagnostics": [
            {
                "reason_code": "deferred_to_round_10f",
                "message": "Document materialized view hash verification is reserved for Round 10F.",
            }
        ],
    }


def _hash_manifest_hash_payload(manifest: ReplayHashManifest | dict[str, Any]) -> dict[str, Any]:
    if isinstance(manifest, ReplayHashManifest):
        payload = manifest.model_dump(mode="json")
    else:
        payload = dict(manifest)
    payload.pop("manifest_hash", None)
    return payload


def _hash_manifest_hash(manifest: ReplayHashManifest | dict[str, Any]) -> str:
    return _sha256(_hash_manifest_hash_payload(manifest))


def _bundle_report_hash_payload(report: ReplayBundleReport | dict[str, Any]) -> dict[str, Any]:
    if isinstance(report, ReplayBundleReport):
        payload = report.model_dump(mode="json")
    else:
        payload = dict(report)
    payload.pop("report_hash", None)
    return payload


def _bundle_report_hash(report: ReplayBundleReport | dict[str, Any]) -> str:
    return _sha256(_bundle_report_hash_payload(report))


def _artifact_storage_ref(artifact: dict[str, Any]) -> dict[str, Any]:
    return {
        "artifact_ref": str(artifact.get("artifact_ref") or ""),
        "logical_path": artifact.get("logical_path"),
        "materialization_status": artifact.get("materialization_status"),
        "storage_backend": str(artifact.get("storage_backend") or "LOCAL_FILE"),
        "storage_relpath": artifact.get("storage_relpath"),
        "storage_object_key": artifact.get("storage_object_key"),
        "content_hash": artifact.get("content_hash"),
        "size_bytes": artifact.get("size_bytes"),
    }


def build_replay_watermark(
    events: list[dict[str, Any]],
    request: ReplayResumeRequest,
    event_range: dict[str, int],
) -> ReplayWatermark:
    if request.event_cursor is None or request.projection_version is None:
        raise ValueError("event cursor and projection version are required")
    event_log_hash = _event_log_hash(events)
    watermark_payload = {
        "resume_kind": request.resume_kind,
        "event_cursor": request.event_cursor,
        "projection_version": request.projection_version,
        "event_range": event_range,
        "schema_version": request.schema_version,
        "contract_version": request.contract_version,
        "event_log_hash": event_log_hash,
        "request_hash": request.request_hash,
    }
    return ReplayWatermark(
        **watermark_payload,
        watermark_hash=_sha256(watermark_payload),
    )


def build_replay_hash_manifest(
    repository: ControlPlaneRepository,
    artifact_store: ArtifactStore | None,
    artifact_refs: list[str],
    source_event_range: dict[str, int] | None,
    *,
    checkpoint: ReplayCheckpoint | None = None,
    replay_compatibility: dict[str, Any] | None = None,
) -> ReplayHashManifest:
    diagnostics: list[dict[str, Any]] = []
    storage_refs_by_artifact: dict[str, dict[str, Any]] = {}
    content_hashes: dict[str, str | None] = {}
    materialization_status: dict[str, str] = {}
    normalized_artifact_refs = sorted(_stable_unique(list(artifact_refs)))

    for artifact_ref in normalized_artifact_refs:
        artifact = repository.get_artifact_by_ref(artifact_ref)
        if artifact is None:
            diagnostics.append(
                {
                    "reason_code": "missing_artifact",
                    "artifact_ref": artifact_ref,
                    "message": "Replay artifact hash verification requires an artifact_index row.",
                }
            )
            continue

        status = str(artifact.get("materialization_status") or "").strip()
        materialization_status[artifact_ref] = status
        content_hashes[artifact_ref] = (
            str(artifact.get("content_hash")).strip()
            if artifact.get("content_hash") is not None
            else None
        )
        storage_ref = _artifact_storage_ref(artifact)
        storage_refs_by_artifact[artifact_ref] = storage_ref

        if status != "MATERIALIZED":
            diagnostics.append(
                {
                    "reason_code": "artifact_not_materialized",
                    "artifact_ref": artifact_ref,
                    "materialization_status": status,
                    "message": "Replay artifact hash verification only reads storage for MATERIALIZED artifacts.",
                }
            )
            continue

        storage_relpath = str(artifact.get("storage_relpath") or "").strip() or None
        storage_object_key = str(artifact.get("storage_object_key") or "").strip() or None
        if storage_relpath is None and storage_object_key is None:
            diagnostics.append(
                {
                    "reason_code": "unregistered_storage_ref",
                    "artifact_ref": artifact_ref,
                    "message": "Materialized artifact has no registered storage_relpath or storage_object_key.",
                }
            )
            continue

        expected_content_hash = content_hashes[artifact_ref]
        if not expected_content_hash:
            diagnostics.append(
                {
                    "reason_code": "missing_content_hash",
                    "artifact_ref": artifact_ref,
                    "message": "Materialized artifact is missing content_hash in artifact_index.",
                }
            )
            continue

        if artifact_store is None:
            diagnostics.append(
                {
                    "reason_code": "storage_read_failed",
                    "artifact_ref": artifact_ref,
                    "message": "Artifact store is unavailable for replay hash verification.",
                }
            )
            continue

        try:
            content = artifact_store.read_bytes(
                storage_relpath,
                storage_object_key=storage_object_key,
            )
        except Exception as exc:
            diagnostics.append(
                {
                    "reason_code": "storage_read_failed",
                    "artifact_ref": artifact_ref,
                    "error_type": type(exc).__name__,
                    "error_message": str(exc),
                }
            )
            continue

        actual_content_hash = hashlib.sha256(content).hexdigest()
        if actual_content_hash != expected_content_hash:
            diagnostics.append(
                {
                    "reason_code": "artifact_hash_mismatch",
                    "artifact_ref": artifact_ref,
                    "expected_content_hash": expected_content_hash,
                    "actual_content_hash": actual_content_hash,
                }
            )
            continue

        diagnostics.append(
            {
                "reason_code": "artifact_hash_verified",
                "artifact_ref": artifact_ref,
                "content_hash": expected_content_hash,
            }
        )

    failed_reason_codes = {
        "missing_artifact",
        "unregistered_storage_ref",
        "missing_content_hash",
        "storage_read_failed",
        "artifact_hash_mismatch",
    }
    status = (
        "FAILED"
        if any(item.get("reason_code") in failed_reason_codes for item in diagnostics)
        else "READY"
    )
    storage_refs = [
        storage_refs_by_artifact[artifact_ref]
        for artifact_ref in normalized_artifact_refs
        if artifact_ref in storage_refs_by_artifact
    ]
    manifest_payload = {
        "status": status,
        "source_event_range": dict(source_event_range) if source_event_range is not None else None,
        "checkpoint_refs": _checkpoint_refs(checkpoint),
        "artifact_refs": normalized_artifact_refs,
        "storage_refs": storage_refs,
        "content_hashes": content_hashes,
        "materialization_status": materialization_status,
        "document_materialized_views": _document_materialized_views_deferred(),
        "diagnostics": diagnostics,
        "replay_compatibility": dict(replay_compatibility or DEFAULT_REPLAY_HASH_COMPATIBILITY),
        "manifest_hash": "",
    }
    manifest_payload["manifest_hash"] = _hash_manifest_hash(manifest_payload)
    return ReplayHashManifest.model_validate(manifest_payload)


def _events_through_cursor(
    events: list[dict[str, Any]],
    cursor_event: dict[str, Any],
) -> list[dict[str, Any]]:
    cursor_sequence_no = int(cursor_event["sequence_no"])
    return [
        event
        for event in sorted(events, key=lambda item: int(item["sequence_no"]))
        if int(event["sequence_no"]) <= cursor_sequence_no
    ]


def _latest_event(events: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not events:
        return None
    return max(events, key=lambda item: int(item["sequence_no"]))


def _resolve_resume_boundary_event(
    events: list[dict[str, Any]],
    request: ReplayResumeRequest,
) -> ReplayResumeResult | dict[str, Any]:
    if request.event_cursor:
        cursor_event = next(
            (event for event in events if str(event.get("event_id")) == request.event_cursor),
            None,
        )
        if cursor_event is None:
            return _failed_result(
                request,
                reason_code="event_cursor_out_of_range",
                message="Replay resume event cursor was not found in the event log.",
                details={"event_cursor": request.event_cursor},
            )
        return cursor_event
    latest_event = _latest_event(events)
    if latest_event is None:
        return _failed_result(
            request,
            reason_code="event_log_empty",
            message="Replay resume requires at least one event.",
        )
    return latest_event


def _first_missing_sequence_no(events: list[dict[str, Any]], *, start_sequence_no: int = 1) -> int | None:
    if not events:
        return start_sequence_no
    sorted_sequence_numbers = sorted(int(event["sequence_no"]) for event in events)
    expected = start_sequence_no
    for sequence_no in sorted_sequence_numbers:
        if sequence_no != expected:
            return expected
        expected += 1
    return None


def _graph_version_sequence_no(graph_version: str | None) -> int | None:
    normalized = str(graph_version or "").strip()
    if not normalized.startswith("gv_"):
        return None
    suffix = normalized[3:]
    if not suffix.isdigit():
        return None
    sequence_no = int(suffix)
    if sequence_no < 1:
        return None
    return sequence_no


def _event_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))


def _insert_replay_event(
    repository: ControlPlaneRepository,
    connection,
    event: dict[str, Any],
) -> None:
    connection.execute(
        """
        INSERT INTO events (
            sequence_no,
            event_id,
            workflow_id,
            event_type,
            actor_type,
            actor_id,
            occurred_at,
            idempotency_key,
            causation_id,
            correlation_id,
            payload_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            int(event["sequence_no"]),
            str(event["event_id"]),
            event.get("workflow_id"),
            str(event["event_type"]),
            str(event.get("actor_type") or "replay"),
            str(event.get("actor_id") or "replay"),
            _event_datetime(event.get("occurred_at")).isoformat(),
            str(event.get("idempotency_key") or f"replay:{event['event_id']}"),
            event.get("causation_id"),
            event.get("correlation_id") or event.get("workflow_id"),
            json.dumps(_event_payload(event), sort_keys=True),
        ),
    )


def _insert_replay_events(
    repository: ControlPlaneRepository,
    connection,
    events: list[dict[str, Any]],
) -> None:
    for event in sorted(events, key=lambda item: int(item["sequence_no"])):
        _insert_replay_event(repository, connection, event)


def _rebuild_replay_projections(
    repository: ControlPlaneRepository,
    connection,
    events: list[dict[str, Any]],
) -> None:
    repository.replace_workflow_projections(connection, rebuild_workflow_projections(events))
    repository.replace_ticket_projections(connection, rebuild_ticket_projections(events))
    repository.replace_assignment_projections(connection, rebuild_assignment_projections(events))
    repository.replace_lease_projections(connection, rebuild_lease_projections(events))
    repository.replace_node_projections(connection, rebuild_node_projections(events))
    repository.replace_runtime_node_projections(connection, rebuild_runtime_node_projections(events))
    repository.replace_execution_attempt_projections(connection, rebuild_execution_attempt_projections(events))
    repository.replace_actor_projections(connection, rebuild_actor_projections(events))
    repository.replace_employee_projections(connection, rebuild_employee_projections(events))
    repository.replace_incident_projections(connection, rebuild_incident_projections(events))
    repository.replace_process_asset_index(connection, rebuild_process_asset_index(events))
    repository.replace_planned_placeholder_projections(
        connection,
        rebuild_planned_placeholder_projections(repository, connection=connection),
    )


def _projection_payloads_from_replay_events(
    repository: ControlPlaneRepository,
    connection,
    events: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    workflow = rebuild_workflow_projections(events)
    ticket = rebuild_ticket_projections(events)
    assignment = rebuild_assignment_projections(events)
    lease = rebuild_lease_projections(events)
    node = rebuild_node_projections(events)
    runtime_node = rebuild_runtime_node_projections(events)
    execution_attempt = rebuild_execution_attempt_projections(events)
    actor = rebuild_actor_projections(events)
    employee = rebuild_employee_projections(events)
    incident = rebuild_incident_projections(events)
    process_asset = rebuild_process_asset_index(events)
    repository.replace_workflow_projections(connection, workflow)
    repository.replace_ticket_projections(connection, ticket)
    repository.replace_assignment_projections(connection, assignment)
    repository.replace_lease_projections(connection, lease)
    repository.replace_node_projections(connection, node)
    repository.replace_runtime_node_projections(connection, runtime_node)
    repository.replace_execution_attempt_projections(connection, execution_attempt)
    repository.replace_actor_projections(connection, actor)
    repository.replace_employee_projections(connection, employee)
    repository.replace_incident_projections(connection, incident)
    repository.replace_process_asset_index(connection, process_asset)
    planned_placeholder = rebuild_planned_placeholder_projections(repository, connection=connection)
    repository.replace_planned_placeholder_projections(connection, planned_placeholder)
    return {
        "workflow": workflow,
        "ticket": ticket,
        "assignment": assignment,
        "lease": lease,
        "node": node,
        "runtime_node": runtime_node,
        "execution_attempt": execution_attempt,
        "actor": actor,
        "employee": employee,
        "incident": incident,
        "process_asset": process_asset,
        "planned_placeholder": planned_placeholder,
    }


def _replace_replay_projections_from_payloads(
    repository: ControlPlaneRepository,
    connection,
    projection_payloads: dict[str, list[dict[str, Any]]],
) -> None:
    repository.replace_workflow_projections(connection, list(projection_payloads.get("workflow") or []))
    repository.replace_ticket_projections(connection, list(projection_payloads.get("ticket") or []))
    repository.replace_assignment_projections(connection, list(projection_payloads.get("assignment") or []))
    repository.replace_lease_projections(connection, list(projection_payloads.get("lease") or []))
    repository.replace_node_projections(connection, list(projection_payloads.get("node") or []))
    repository.replace_runtime_node_projections(connection, list(projection_payloads.get("runtime_node") or []))
    repository.replace_execution_attempt_projections(connection, list(projection_payloads.get("execution_attempt") or []))
    repository.replace_actor_projections(connection, list(projection_payloads.get("actor") or []))
    repository.replace_employee_projections(connection, list(projection_payloads.get("employee") or []))
    repository.replace_incident_projections(connection, list(projection_payloads.get("incident") or []))
    repository.replace_process_asset_index(connection, list(projection_payloads.get("process_asset") or []))
    repository.replace_planned_placeholder_projections(
        connection,
        list(projection_payloads.get("planned_placeholder") or []),
    )


def _projection_dict(
    projection_payloads: dict[str, list[dict[str, Any]]],
    projection_name: str,
    key_fields: tuple[str, ...],
) -> dict[tuple[Any, ...], dict[str, Any]]:
    return {
        tuple(item.get(field) for field in key_fields): dict(item)
        for item in list(projection_payloads.get(projection_name) or [])
    }


def _projection_values(items: dict[tuple[Any, ...], dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        items[key]
        for key in sorted(
            items,
            key=lambda value: tuple(str(part or "") for part in value),
        )
    ]


def _event_iso(event: dict[str, Any]) -> str:
    occurred_at = event.get("occurred_at")
    if isinstance(occurred_at, datetime):
        return occurred_at.isoformat()
    return str(occurred_at)


def _event_workflow_id(event: dict[str, Any], payload: dict[str, Any]) -> str | None:
    workflow_id = str(payload.get("workflow_id") or event.get("workflow_id") or "").strip()
    return workflow_id or None


def _ticket_projection_base_from_payload(event: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "ticket_id": payload["ticket_id"],
        "workflow_id": event.get("workflow_id") or payload.get("workflow_id"),
        "node_id": payload["node_id"],
        "tenant_id": payload.get("tenant_id") or "tenant_default",
        "workspace_id": payload.get("workspace_id") or "ws_default",
        "status": TICKET_STATUS_PENDING,
        "actor_id": None,
        "assignment_id": None,
        "lease_id": None,
        "lease_owner": None,
        "lease_expires_at": None,
        "started_at": None,
        "last_heartbeat_at": None,
        "heartbeat_expires_at": None,
        "heartbeat_timeout_sec": None,
        "retry_count": payload.get("retry_count", 0),
        "retry_budget": payload.get("retry_budget"),
        "timeout_sla_sec": payload.get("timeout_sla_sec"),
        "priority": payload.get("priority"),
        "last_failure_kind": None,
        "last_failure_message": None,
        "last_failure_fingerprint": None,
        "blocking_reason_code": None,
        "updated_at": _event_iso(event),
        "version": int(event["sequence_no"]),
    }


def _node_projection_base_from_payload(event: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "workflow_id": event.get("workflow_id") or payload.get("workflow_id"),
        "node_id": payload["node_id"],
        "latest_ticket_id": payload["ticket_id"],
        "status": NODE_STATUS_PENDING,
        "blocking_reason_code": None,
        "updated_at": _event_iso(event),
        "version": int(event["sequence_no"]),
    }


def _apply_incremental_projection_events(
    checkpoint_payloads: dict[str, list[dict[str, Any]]],
    incremental_events: list[dict[str, Any]],
    *,
    target_events: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    payloads = {
        name: [dict(item) for item in list(rows or [])]
        for name, rows in checkpoint_payloads.items()
    }
    workflow = _projection_dict(payloads, "workflow", ("workflow_id",))
    ticket = _projection_dict(payloads, "ticket", ("ticket_id",))
    assignment = _projection_dict(payloads, "assignment", ("assignment_id",))
    lease = _projection_dict(payloads, "lease", ("lease_id",))
    node = _projection_dict(payloads, "node", ("workflow_id", "node_id"))
    runtime_node = _projection_dict(payloads, "runtime_node", ("workflow_id", "graph_node_id"))
    execution_attempt = _projection_dict(payloads, "execution_attempt", ("attempt_id",))
    actor = _projection_dict(payloads, "actor", ("actor_id",))
    employee = _projection_dict(payloads, "employee", ("employee_id",))
    incident = _projection_dict(payloads, "incident", ("incident_id",))
    process_asset = _projection_dict(payloads, "process_asset", ("process_asset_ref",))

    created_specs_by_ticket_id: dict[str, dict[str, Any]] = {}
    graph_version_sequence_by_workflow: dict[str, int] = {}
    for event in sorted(target_events, key=lambda item: int(item["sequence_no"])):
        payload = _event_payload(event)
        workflow_id = _event_workflow_id(event, payload)
        if workflow_id and str(event.get("event_type")) in _GRAPH_MUTATION_EVENTS:
            graph_version_sequence_by_workflow[workflow_id] = int(event["sequence_no"])
        ticket_id = str(payload.get("ticket_id") or "").strip()
        if str(event.get("event_type")) == EVENT_TICKET_CREATED and ticket_id:
            created_specs_by_ticket_id[ticket_id] = dict(payload)

    def update_workflow(event: dict[str, Any], payload: dict[str, Any]) -> None:
        workflow_id = _event_workflow_id(event, payload)
        if not workflow_id:
            return
        key = (workflow_id,)
        if str(event["event_type"]) == EVENT_WORKFLOW_CREATED:
            workflow[key] = {
                "workflow_id": workflow_id,
                "title": payload.get("title") or payload.get("north_star_goal") or workflow_id,
                "north_star_goal": payload.get("north_star_goal") or payload.get("title") or workflow_id,
                "workflow_profile": str(payload.get("workflow_profile") or "STANDARD"),
                "tenant_id": payload.get("tenant_id") or "tenant_default",
                "workspace_id": payload.get("workspace_id") or "ws_default",
                "current_stage": "INTAKE",
                "status": "ACTIVE",
                "budget_total": payload.get("budget_cap", 0),
                "budget_used": 0,
                "board_gate_state": "NONE",
                "deadline_at": payload.get("deadline_at"),
                "started_at": _event_iso(event),
                "updated_at": _event_iso(event),
                "version": int(event["sequence_no"]),
            }
            return
        if key in workflow:
            workflow[key] = {
                **workflow[key],
                "updated_at": _event_iso(event),
                "version": int(event["sequence_no"]),
            }

    def update_runtime_node(event: dict[str, Any], payload: dict[str, Any], *, status: str, blocking_reason_code: str | None = None) -> None:
        workflow_id = _event_workflow_id(event, payload)
        ticket_id = str(payload.get("ticket_id") or "").strip()
        if not workflow_id or not ticket_id:
            return
        created_spec = created_specs_by_ticket_id.get(ticket_id)
        if created_spec is None:
            return
        try:
            identity = resolve_ticket_graph_identity(
                ticket_id=ticket_id,
                created_spec=created_spec,
                runtime_node_id=str(payload.get("node_id") or created_spec.get("node_id") or "").strip(),
            )
        except GraphIdentityResolutionError:
            return
        graph_version = f"gv_{max(graph_version_sequence_by_workflow.get(workflow_id, 1), 1)}"
        key = (workflow_id, identity.graph_node_id)
        previous = runtime_node.get(key, {})
        runtime_node[key] = {
            "workflow_id": workflow_id,
            "graph_node_id": identity.graph_node_id,
            "node_id": identity.runtime_node_id,
            "runtime_node_id": identity.runtime_node_id,
            "latest_ticket_id": ticket_id,
            "status": status,
            "blocking_reason_code": blocking_reason_code,
            "graph_version": graph_version,
            "updated_at": _event_iso(event),
            "version": int(event["sequence_no"]),
            **{
                key_name: value
                for key_name, value in previous.items()
                if key_name
                not in {
                    "latest_ticket_id",
                    "status",
                    "blocking_reason_code",
                    "graph_version",
                    "updated_at",
                    "version",
                }
            },
        }

    for event in sorted(incremental_events, key=lambda item: int(item["sequence_no"])):
        payload = _event_payload(event)
        event_type = str(event["event_type"])
        occurred_at = _event_iso(event)
        version = int(event["sequence_no"])
        workflow_id = _event_workflow_id(event, payload)
        update_workflow(event, payload)

        if event_type == EVENT_TICKET_CREATED:
            ticket_id = str(payload.get("ticket_id") or "").strip()
            node_id = str(payload.get("node_id") or "").strip()
            if ticket_id and node_id and workflow_id:
                ticket[(ticket_id,)] = _ticket_projection_base_from_payload(event, payload)
                node[(workflow_id, node_id)] = _node_projection_base_from_payload(event, payload)
                update_runtime_node(event, payload, status=NODE_STATUS_PENDING)
            continue

        ticket_id = str(payload.get("ticket_id") or "").strip()
        node_id = str(payload.get("node_id") or "").strip()
        ticket_key = (ticket_id,)
        previous_ticket = ticket.get(ticket_key)
        if ticket_id and node_id and previous_ticket is None:
            previous_ticket = _ticket_projection_base_from_payload(event, payload)
        if ticket_id and node_id and previous_ticket is not None:
            status_by_event = {
                EVENT_TICKET_ASSIGNED: TICKET_STATUS_PENDING,
                EVENT_TICKET_LEASE_GRANTED: TICKET_STATUS_LEASED,
                EVENT_TICKET_LEASED: TICKET_STATUS_LEASED,
                EVENT_TICKET_STARTED: TICKET_STATUS_EXECUTING,
                EVENT_TICKET_HEARTBEAT_RECORDED: TICKET_STATUS_EXECUTING,
                EVENT_TICKET_EXECUTION_PRECONDITION_BLOCKED: TICKET_STATUS_PENDING,
                EVENT_TICKET_EXECUTION_PRECONDITION_CLEARED: TICKET_STATUS_PENDING,
                EVENT_TICKET_CANCEL_REQUESTED: TICKET_STATUS_CANCEL_REQUESTED,
                EVENT_TICKET_CANCELLED: TICKET_STATUS_CANCELLED,
                EVENT_TICKET_COMPLETED: TICKET_STATUS_COMPLETED,
                EVENT_TICKET_FAILED: TICKET_STATUS_FAILED,
                EVENT_TICKET_TIMED_OUT: TICKET_STATUS_TIMED_OUT,
                EVENT_BOARD_REVIEW_REQUIRED: TICKET_STATUS_BLOCKED_FOR_BOARD_REVIEW,
                EVENT_BOARD_REVIEW_APPROVED: TICKET_STATUS_COMPLETED,
                EVENT_BOARD_REVIEW_REJECTED: TICKET_STATUS_REWORK_REQUIRED,
            }
            if event_type in status_by_event:
                blocking_reason_code = previous_ticket.get("blocking_reason_code")
                if event_type == EVENT_TICKET_EXECUTION_PRECONDITION_BLOCKED:
                    blocking_reason_code = payload.get("reason_code", BLOCKING_REASON_PROVIDER_REQUIRED)
                elif event_type in {
                    EVENT_TICKET_EXECUTION_PRECONDITION_CLEARED,
                    EVENT_TICKET_LEASE_GRANTED,
                    EVENT_TICKET_LEASED,
                    EVENT_TICKET_STARTED,
                    EVENT_TICKET_HEARTBEAT_RECORDED,
                    EVENT_TICKET_CANCEL_REQUESTED,
                    EVENT_TICKET_CANCELLED,
                    EVENT_TICKET_COMPLETED,
                    EVENT_TICKET_FAILED,
                    EVENT_TICKET_TIMED_OUT,
                    EVENT_BOARD_REVIEW_APPROVED,
                }:
                    blocking_reason_code = None
                elif event_type == EVENT_BOARD_REVIEW_REQUIRED:
                    blocking_reason_code = BLOCKING_REASON_BOARD_REVIEW_REQUIRED
                elif event_type == EVENT_BOARD_REVIEW_REJECTED:
                    blocking_reason_code = (
                        BLOCKING_REASON_MODIFY_CONSTRAINTS
                        if payload.get("decision_action") == "MODIFY_CONSTRAINTS"
                        else BLOCKING_REASON_BOARD_REJECTED
                    )
                ticket[ticket_key] = {
                    **previous_ticket,
                    "workflow_id": workflow_id or previous_ticket.get("workflow_id"),
                    "node_id": node_id,
                    "actor_id": payload.get("actor_id", previous_ticket.get("actor_id")),
                    "assignment_id": payload.get("assignment_id", previous_ticket.get("assignment_id")),
                    "lease_id": payload.get("lease_id", previous_ticket.get("lease_id")),
                    "lease_expires_at": payload.get("lease_expires_at", previous_ticket.get("lease_expires_at")),
                    "started_at": occurred_at if event_type == EVENT_TICKET_STARTED else (
                        None if event_type in {EVENT_TICKET_COMPLETED, EVENT_TICKET_FAILED, EVENT_TICKET_TIMED_OUT, EVENT_TICKET_CANCELLED} else previous_ticket.get("started_at")
                    ),
                    "last_heartbeat_at": occurred_at if event_type in {EVENT_TICKET_STARTED, EVENT_TICKET_HEARTBEAT_RECORDED} else (
                        None if event_type in {EVENT_TICKET_COMPLETED, EVENT_TICKET_FAILED, EVENT_TICKET_TIMED_OUT, EVENT_TICKET_CANCELLED} else previous_ticket.get("last_heartbeat_at")
                    ),
                    "heartbeat_expires_at": payload.get("heartbeat_expires_at", previous_ticket.get("heartbeat_expires_at")),
                    "status": status_by_event[event_type],
                    "last_failure_kind": payload.get("failure_kind") if event_type in {EVENT_TICKET_FAILED, EVENT_TICKET_TIMED_OUT} else (
                        None if event_type in {EVENT_TICKET_COMPLETED, EVENT_BOARD_REVIEW_APPROVED} else previous_ticket.get("last_failure_kind")
                    ),
                    "last_failure_message": payload.get("failure_message") if event_type in {EVENT_TICKET_FAILED, EVENT_TICKET_TIMED_OUT} else (
                        None if event_type in {EVENT_TICKET_COMPLETED, EVENT_BOARD_REVIEW_APPROVED} else previous_ticket.get("last_failure_message")
                    ),
                    "last_failure_fingerprint": payload.get("failure_fingerprint") if event_type in {EVENT_TICKET_FAILED, EVENT_TICKET_TIMED_OUT} else (
                        None if event_type in {EVENT_TICKET_COMPLETED, EVENT_BOARD_REVIEW_APPROVED} else previous_ticket.get("last_failure_fingerprint")
                    ),
                    "blocking_reason_code": blocking_reason_code,
                    "updated_at": occurred_at,
                    "version": version,
                }

        if ticket_id and node_id and workflow_id:
            node_status_by_event = {
                EVENT_TICKET_LEASE_GRANTED: NODE_STATUS_PENDING,
                EVENT_TICKET_LEASED: NODE_STATUS_PENDING,
                EVENT_TICKET_STARTED: NODE_STATUS_EXECUTING,
                EVENT_TICKET_HEARTBEAT_RECORDED: NODE_STATUS_EXECUTING,
                EVENT_TICKET_EXECUTION_PRECONDITION_BLOCKED: NODE_STATUS_PENDING,
                EVENT_TICKET_EXECUTION_PRECONDITION_CLEARED: NODE_STATUS_PENDING,
                EVENT_TICKET_CANCEL_REQUESTED: NODE_STATUS_CANCEL_REQUESTED,
                EVENT_TICKET_CANCELLED: NODE_STATUS_CANCELLED,
                EVENT_TICKET_COMPLETED: NODE_STATUS_COMPLETED,
                EVENT_TICKET_FAILED: NODE_STATUS_REWORK_REQUIRED,
                EVENT_TICKET_TIMED_OUT: NODE_STATUS_REWORK_REQUIRED,
                EVENT_BOARD_REVIEW_REQUIRED: NODE_STATUS_BLOCKED_FOR_BOARD_REVIEW,
                EVENT_BOARD_REVIEW_APPROVED: NODE_STATUS_COMPLETED,
                EVENT_BOARD_REVIEW_REJECTED: NODE_STATUS_REWORK_REQUIRED,
            }
            if event_type == EVENT_TICKET_COMPLETED and payload.get("board_review_requested"):
                continue
            if event_type in node_status_by_event:
                blocking_reason_code = None
                if event_type == EVENT_TICKET_EXECUTION_PRECONDITION_BLOCKED:
                    blocking_reason_code = payload.get("reason_code", BLOCKING_REASON_PROVIDER_REQUIRED)
                elif event_type == EVENT_BOARD_REVIEW_REQUIRED:
                    blocking_reason_code = BLOCKING_REASON_BOARD_REVIEW_REQUIRED
                elif event_type == EVENT_BOARD_REVIEW_REJECTED:
                    blocking_reason_code = (
                        BLOCKING_REASON_MODIFY_CONSTRAINTS
                        if payload.get("decision_action") == "MODIFY_CONSTRAINTS"
                        else BLOCKING_REASON_BOARD_REJECTED
                    )
                node[(workflow_id, node_id)] = {
                    **node.get((workflow_id, node_id), _node_projection_base_from_payload(event, payload)),
                    "latest_ticket_id": ticket_id,
                    "status": node_status_by_event[event_type],
                    "blocking_reason_code": blocking_reason_code,
                    "updated_at": occurred_at,
                    "version": version,
                }
                update_runtime_node(
                    event,
                    payload,
                    status=node_status_by_event[event_type],
                    blocking_reason_code=blocking_reason_code,
                )

        if event_type == EVENT_TICKET_ASSIGNED:
            assignment_id = str(payload.get("assignment_id") or "").strip()
            actor_id = str(payload.get("actor_id") or "").strip()
            if assignment_id and actor_id and ticket_id and node_id and workflow_id:
                assignment[(assignment_id,)] = {
                    "assignment_id": assignment_id,
                    "workflow_id": workflow_id,
                    "ticket_id": ticket_id,
                    "node_id": node_id,
                    "actor_id": actor_id,
                    "required_capabilities": list(payload.get("required_capabilities") or []),
                    "provider_selection": {
                        key: payload.get(key)
                        for key in (
                            "preferred_provider_id",
                            "preferred_model",
                            "actual_provider_id",
                            "actual_model",
                            "selection_reason",
                            "policy_reason",
                            "fallback_reason",
                            "provider_health_snapshot",
                            "cost_class",
                            "latency_class",
                        )
                        if key in payload
                    },
                    "status": str(payload.get("status") or "ASSIGNED"),
                    "assignment_reason": str(payload.get("assignment_reason") or payload.get("reason") or ""),
                    "assigned_at": str(payload.get("assigned_at") or occurred_at),
                    "updated_at": occurred_at,
                    "version": version,
                }

        if event_type in {
            EVENT_TICKET_LEASE_GRANTED,
            EVENT_TICKET_STARTED,
            EVENT_TICKET_COMPLETED,
            EVENT_TICKET_FAILED,
            EVENT_TICKET_TIMED_OUT,
            EVENT_TICKET_CANCELLED,
        }:
            lease_id = str(payload.get("lease_id") or "").strip()
            if lease_id:
                previous_lease = lease.get((lease_id,), {})
                if event_type == EVENT_TICKET_LEASE_GRANTED:
                    lease[(lease_id,)] = {
                        "lease_id": lease_id,
                        "assignment_id": str(payload.get("assignment_id") or ""),
                        "workflow_id": workflow_id or "",
                        "ticket_id": ticket_id,
                        "node_id": node_id,
                        "actor_id": str(payload.get("actor_id") or ""),
                        "status": str(payload.get("status") or "LEASED"),
                        "lease_timeout_sec": payload.get("lease_timeout_sec"),
                        "lease_expires_at": payload.get("lease_expires_at"),
                        "started_at": None,
                        "closed_at": None,
                        "failure_kind": None,
                        "updated_at": occurred_at,
                        "version": version,
                    }
                elif previous_lease:
                    lease[(lease_id,)] = {
                        **previous_lease,
                        "status": {
                            EVENT_TICKET_STARTED: "EXECUTING",
                            EVENT_TICKET_COMPLETED: "RELEASED",
                            EVENT_TICKET_FAILED: "FAILED",
                            EVENT_TICKET_TIMED_OUT: "TIMED_OUT",
                            EVENT_TICKET_CANCELLED: "CANCELLED",
                        }[event_type],
                        "started_at": occurred_at if event_type == EVENT_TICKET_STARTED else previous_lease.get("started_at"),
                        "closed_at": None if event_type == EVENT_TICKET_STARTED else occurred_at,
                        "failure_kind": payload.get("failure_kind", previous_lease.get("failure_kind")),
                        "updated_at": occurred_at,
                        "version": version,
                    }

        if event_type in {
            EVENT_PROVIDER_ATTEMPT_STARTED,
            EVENT_PROVIDER_FIRST_TOKEN_RECEIVED,
            EVENT_PROVIDER_ATTEMPT_HEARTBEAT_RECORDED,
            EVENT_PROVIDER_ATTEMPT_FINISHED,
            EVENT_PROVIDER_ATTEMPT_TIMED_OUT,
        }:
            attempt_id = str(payload.get("attempt_id") or "").strip()
            if attempt_id:
                previous_attempt = execution_attempt.get((attempt_id,), {})
                if str(previous_attempt.get("state") or "") in _TERMINAL_ATTEMPT_STATES:
                    continue
                state = str(payload.get("state") or payload.get("status") or previous_attempt.get("state") or "CREATED")
                if event_type in {EVENT_PROVIDER_FIRST_TOKEN_RECEIVED, EVENT_PROVIDER_ATTEMPT_HEARTBEAT_RECORDED}:
                    state = "STREAMING"
                elif event_type == EVENT_PROVIDER_ATTEMPT_FINISHED:
                    raw_state = str(payload.get("state") or "").strip()
                    status = str(payload.get("status") or "").strip().upper()
                    if raw_state:
                        state = raw_state
                    elif status == "COMPLETED":
                        state = "COMPLETED"
                    elif bool(payload.get("retryable")):
                        state = "FAILED_RETRYABLE"
                    else:
                        state = "FAILED_TERMINAL"
                elif event_type == EVENT_PROVIDER_ATTEMPT_TIMED_OUT:
                    state = "TIMED_OUT"
                execution_attempt[(attempt_id,)] = {
                    **previous_attempt,
                    "attempt_id": attempt_id,
                    "workflow_id": workflow_id or previous_attempt.get("workflow_id") or "",
                    "ticket_id": ticket_id or previous_attempt.get("ticket_id") or "",
                    "node_id": node_id or previous_attempt.get("node_id") or "",
                    "attempt_no": int(payload.get("attempt_no") or previous_attempt.get("attempt_no") or 1),
                    "idempotency_key": str(payload.get("idempotency_key") or previous_attempt.get("idempotency_key") or attempt_id),
                    "provider_policy_ref": str(payload.get("provider_policy_ref") or previous_attempt.get("provider_policy_ref") or "provider-policy:unknown"),
                    "deadline_at": str(payload.get("deadline_at") or previous_attempt.get("deadline_at") or occurred_at),
                    "last_heartbeat_at": occurred_at if event_type == EVENT_PROVIDER_ATTEMPT_HEARTBEAT_RECORDED else previous_attempt.get("last_heartbeat_at"),
                    "state": state,
                    "failure_kind": payload.get("failure_kind", previous_attempt.get("failure_kind")),
                    "failure_fingerprint": payload.get("fingerprint") or payload.get("failure_fingerprint", previous_attempt.get("failure_fingerprint")),
                    "updated_at": occurred_at,
                    "version": version,
                }

        if event_type in {EVENT_ACTOR_ENABLED, EVENT_ACTOR_SUSPENDED, EVENT_ACTOR_DEACTIVATED, EVENT_ACTOR_REPLACED}:
            actor_id = str(payload.get("actor_id") or "").strip()
            if actor_id:
                previous_actor = actor.get((actor_id,), {})
                status = {
                    EVENT_ACTOR_ENABLED: ACTOR_STATUS_ACTIVE,
                    EVENT_ACTOR_SUSPENDED: "SUSPENDED",
                    EVENT_ACTOR_DEACTIVATED: "DEACTIVATED",
                    EVENT_ACTOR_REPLACED: "REPLACED",
                }[event_type]
                actor[(actor_id,)] = {
                    **previous_actor,
                    "actor_id": actor_id,
                    "employee_id": payload.get("employee_id", previous_actor.get("employee_id")),
                    "status": status,
                    "capability_set": list(payload.get("capability_set") or previous_actor.get("capability_set") or []),
                    "provider_preferences": dict(payload.get("provider_preferences") or previous_actor.get("provider_preferences") or {}),
                    "availability": dict(payload.get("availability") or previous_actor.get("availability") or {}),
                    "created_from_policy": payload.get("created_from_policy", previous_actor.get("created_from_policy")),
                    "deactivated_reason": payload.get("deactivated_reason"),
                    "replaced_by_actor_id": payload.get("replaced_by_actor_id"),
                    "replacement_reason": payload.get("replacement_reason"),
                    "replacement_plan": payload.get("replacement_plan"),
                    "lifecycle_reason": payload.get("audit_reason"),
                    "updated_at": occurred_at,
                    "version": version,
                }

        if event_type in {EVENT_EMPLOYEE_HIRED, EVENT_EMPLOYEE_REPLACED, EVENT_EMPLOYEE_FROZEN, EVENT_EMPLOYEE_RESTORED}:
            employee_id = str(payload.get("employee_id") or "").strip()
            if employee_id:
                previous_employee = employee.get((employee_id,), {})
                employee[(employee_id,)] = {
                    **previous_employee,
                    "employee_id": employee_id,
                    "role_type": str(payload.get("role_type") or previous_employee.get("role_type") or "unknown"),
                    "skill_profile_json": dict(payload.get("skill_profile") or previous_employee.get("skill_profile_json") or {}),
                    "personality_profile_json": dict(payload.get("personality_profile") or previous_employee.get("personality_profile_json") or {}),
                    "aesthetic_profile_json": dict(payload.get("aesthetic_profile") or previous_employee.get("aesthetic_profile_json") or {}),
                    "state": {
                        EVENT_EMPLOYEE_HIRED: str(payload.get("state") or "ACTIVE"),
                        EVENT_EMPLOYEE_REPLACED: "REPLACED",
                        EVENT_EMPLOYEE_FROZEN: "FROZEN",
                        EVENT_EMPLOYEE_RESTORED: "ACTIVE",
                    }[event_type],
                    "board_approved": bool(payload.get("board_approved", previous_employee.get("board_approved", False))),
                    "provider_id": payload.get("provider_id", previous_employee.get("provider_id")),
                    "role_profile_refs": list(payload.get("role_profile_refs") or previous_employee.get("role_profile_refs") or []),
                    "updated_at": occurred_at,
                    "version": version,
                }

        if event_type in {
            EVENT_INCIDENT_OPENED,
            EVENT_INCIDENT_RECOVERY_STARTED,
            EVENT_INCIDENT_CLOSED,
            EVENT_CIRCUIT_BREAKER_OPENED,
            EVENT_CIRCUIT_BREAKER_CLOSED,
        }:
            incident_id = str(payload.get("incident_id") or "").strip()
            if incident_id:
                previous_incident = incident.get((incident_id,), {})
                incident[(incident_id,)] = {
                    **previous_incident,
                    "incident_id": incident_id,
                    "workflow_id": workflow_id or previous_incident.get("workflow_id") or "",
                    "node_id": payload.get("node_id", previous_incident.get("node_id")),
                    "ticket_id": payload.get("ticket_id", previous_incident.get("ticket_id")),
                    "provider_id": payload.get("provider_id", previous_incident.get("provider_id")),
                    "incident_type": payload.get("incident_type", previous_incident.get("incident_type")),
                    "status": payload.get(
                        "status",
                        "CLOSED" if event_type == EVENT_INCIDENT_CLOSED else (
                            "RECOVERING" if event_type == EVENT_INCIDENT_RECOVERY_STARTED else previous_incident.get("status", "OPEN")
                        ),
                    ),
                    "severity": payload.get("severity", previous_incident.get("severity")),
                    "fingerprint": payload.get("fingerprint", previous_incident.get("fingerprint")),
                    "circuit_breaker_state": payload.get("circuit_breaker_state", previous_incident.get("circuit_breaker_state")),
                    "opened_at": previous_incident.get("opened_at") or occurred_at,
                    "closed_at": occurred_at if event_type == EVENT_INCIDENT_CLOSED else previous_incident.get("closed_at"),
                    "payload": {**dict(previous_incident.get("payload") or {}), **payload},
                    "updated_at": occurred_at,
                    "version": version,
                }

        if event_type == EVENT_TICKET_COMPLETED:
            for asset in list(payload.get("produced_process_assets") or []):
                if not isinstance(asset, dict):
                    continue
                asset_ref = str(asset.get("process_asset_ref") or asset.get("canonical_ref") or "").strip()
                if not asset_ref:
                    continue
                projection = {
                    "process_asset_ref": asset_ref,
                    "canonical_ref": str(asset.get("canonical_ref") or asset_ref),
                    "version_int": asset.get("version_int"),
                    "supersedes_ref": asset.get("supersedes_ref"),
                    "process_asset_kind": str(asset.get("process_asset_kind") or ""),
                    "workflow_id": str(asset.get("workflow_id") or workflow_id or "").strip() or None,
                    "producer_ticket_id": str(asset.get("producer_ticket_id") or ticket_id or "").strip() or None,
                    "producer_node_id": str(asset.get("producer_node_id") or node_id or "").strip() or None,
                    "graph_version": str(asset.get("graph_version") or "").strip() or None,
                    "content_hash": str(asset.get("content_hash") or "").strip() or _sha256(asset),
                    "visibility_status": str(asset.get("visibility_status") or "CONSUMABLE").strip() or "CONSUMABLE",
                    "linked_process_asset_refs": list(asset.get("linked_process_asset_refs") or []),
                    "summary": asset.get("summary"),
                    "consumable_by": list(asset.get("consumable_by") or []),
                    "source_metadata": dict(asset.get("source_metadata") or {}),
                    "updated_at": occurred_at,
                    "version": version,
                }
                process_asset[(asset_ref,)] = projection

    return {
        "workflow": _projection_values(workflow),
        "ticket": _projection_values(ticket),
        "assignment": _projection_values(assignment),
        "lease": _projection_values(lease),
        "node": _projection_values(node),
        "runtime_node": _projection_values(runtime_node),
        "execution_attempt": _projection_values(execution_attempt),
        "actor": _projection_values(actor),
        "employee": _projection_values(employee),
        "incident": _projection_values(incident),
        "process_asset": _projection_values(process_asset),
        "planned_placeholder": [dict(item) for item in list(payloads.get("planned_placeholder") or [])],
    }


def _build_replay_repository(
    temp_dir: str,
    events: list[dict[str, Any]],
) -> ControlPlaneRepository:
    repository = ControlPlaneRepository(Path(temp_dir) / "replay.db", 1000)
    repository.initialize()
    with repository.transaction() as connection:
        connection.execute("DELETE FROM events")
        _insert_replay_events(repository, connection, events)
        replay_events = repository.list_all_events(connection)
        _rebuild_replay_projections(repository, connection, replay_events)
    return repository


def _build_replay_repository_from_checkpoint(
    temp_dir: str,
    checkpoint: ReplayCheckpoint,
    target_events: list[dict[str, Any]],
    incremental_events: list[dict[str, Any]],
) -> ControlPlaneRepository:
    repository = ControlPlaneRepository(Path(temp_dir) / "replay.db", 1000)
    repository.initialize()
    with repository.transaction() as connection:
        connection.execute("DELETE FROM events")
        _insert_replay_events(repository, connection, target_events)
        projection_payloads = _apply_incremental_projection_events(
            checkpoint.projection_payloads,
            incremental_events,
            target_events=target_events,
        )
        _replace_replay_projections_from_payloads(repository, connection, projection_payloads)
        replay_events = repository.list_all_events(connection)
        planned_placeholder = rebuild_planned_placeholder_projections(repository, connection=connection)
        repository.replace_planned_placeholder_projections(connection, planned_placeholder)
    return repository


def _build_replay_checkpoint_from_payloads(
    *,
    event_watermark: ReplayWatermark,
    projection_payloads: dict[str, list[dict[str, Any]]],
    covered_projections: tuple[str, ...],
    compatibility: dict[str, Any],
    created_at: datetime | None = None,
    invalidated_by: list[str] | None = None,
) -> ReplayCheckpoint:
    checkpoint_payload = {
        "checkpoint_id": "pending",
        "checkpoint_version": REPLAY_CHECKPOINT_VERSION,
        "event_watermark": event_watermark.model_dump(mode="json"),
        "projection_version": event_watermark.projection_version,
        "schema_version": event_watermark.schema_version,
        "contract_version": event_watermark.contract_version,
        "invalidated_by": list(invalidated_by or []),
        "created_at": (created_at or datetime.now().astimezone()).isoformat(),
        "checkpoint_hash": "",
        "covered_projections": tuple(covered_projections),
        "compatibility": dict(compatibility),
        "projection_payloads": _json_safe(projection_payloads),
    }
    checkpoint_hash = _checkpoint_hash(checkpoint_payload)
    checkpoint_payload["checkpoint_id"] = f"rcp_{event_watermark.projection_version}_{checkpoint_hash[:16]}"
    checkpoint_payload["checkpoint_hash"] = checkpoint_hash
    return ReplayCheckpoint.model_validate(checkpoint_payload)


def build_replay_checkpoint(
    events: list[dict[str, Any]],
    request: ReplayResumeRequest,
    *,
    covered_projections: tuple[str, ...] = DEFAULT_REPLAY_CHECKPOINT_PROJECTIONS,
    compatibility: dict[str, Any] = DEFAULT_REPLAY_CHECKPOINT_COMPATIBILITY,
) -> ReplayCheckpoint:
    return build_projection_checkpoint_from_replay_events(
        events,
        request,
        covered_projections=covered_projections,
        compatibility=compatibility,
    )


def build_projection_checkpoint_from_replay_events(
    events: list[dict[str, Any]],
    request: ReplayResumeRequest,
    *,
    covered_projections: tuple[str, ...] = DEFAULT_REPLAY_CHECKPOINT_PROJECTIONS,
    compatibility: dict[str, Any] = DEFAULT_REPLAY_CHECKPOINT_COMPATIBILITY,
) -> ReplayCheckpoint:
    if request.event_cursor is None:
        raise ValueError("checkpoint request requires event_cursor")
    cursor_event = next(
        (event for event in events if str(event.get("event_id")) == request.event_cursor),
        None,
    )
    if cursor_event is None:
        raise ValueError(f"checkpoint cursor {request.event_cursor} not found")
    checkpoint_events = _events_through_cursor(events, cursor_event)
    if request.projection_version != int(cursor_event["sequence_no"]):
        raise ValueError("checkpoint projection_version must match event cursor sequence")
    event_range = request.event_range or {
        "start_sequence_no": min(int(event["sequence_no"]) for event in checkpoint_events),
        "end_sequence_no": int(cursor_event["sequence_no"]),
    }
    checkpoint_request = request
    if request.event_range is None:
        checkpoint_request = _normalize_replay_resume_request(request, event_range=event_range)
    event_watermark = build_replay_watermark(checkpoint_events, checkpoint_request, event_range)
    with TemporaryDirectory(prefix="boardroom-checkpoint-build-") as temp_dir:
        repository = ControlPlaneRepository(Path(temp_dir) / "checkpoint.db", 1000)
        repository.initialize()
        with repository.transaction() as connection:
            connection.execute("DELETE FROM events")
            _insert_replay_events(repository, connection, checkpoint_events)
            replay_events = repository.list_all_events(connection)
            projection_payloads = _projection_payloads_from_replay_events(
                repository,
                connection,
                replay_events,
            )
    selected_payloads = {
        projection_name: projection_payloads.get(projection_name, [])
        for projection_name in covered_projections
    }
    return _build_replay_checkpoint_from_payloads(
        event_watermark=event_watermark,
        projection_payloads=selected_payloads,
        covered_projections=tuple(covered_projections),
        compatibility=compatibility,
    )


def _dispatch_full_replay_resume(
    events: list[dict[str, Any]],
    request: ReplayResumeRequest,
) -> ReplayResumeResult:
    if request.resume_kind == RESUME_KIND_EVENT_ID:
        return resume_replay_from_event_id(events, request)
    if request.resume_kind == RESUME_KIND_GRAPH_VERSION:
        return resume_replay_from_graph_version(events, request)
    if request.resume_kind == RESUME_KIND_TICKET_ID:
        return resume_replay_from_ticket_id(events, request)
    if request.resume_kind == RESUME_KIND_INCIDENT_ID:
        return resume_replay_from_incident_id(events, request)
    return _failed_result(
        request,
        reason_code="unsupported_resume_kind",
        message="Replay resume kind is not supported.",
        details={"resume_kind": request.resume_kind},
    )


def _resolve_checkpoint_boundary(
    events: list[dict[str, Any]],
    request: ReplayResumeRequest,
) -> tuple[ReplayResumeRequest, dict[str, Any], list[dict[str, Any]], dict[str, int], ReplayWatermark] | ReplayResumeResult:
    if request.resume_kind == RESUME_KIND_EVENT_ID:
        if not request.event_cursor:
            return _failed_result(
                request,
                reason_code="missing_event_cursor",
                message="Replay resume requires an event cursor.",
            )
        cursor_event = next(
            (event for event in events if str(event.get("event_id")) == request.event_cursor),
            None,
        )
        if cursor_event is None:
            return _failed_result(
                request,
                reason_code="event_cursor_out_of_range",
                message="Replay resume event cursor was not found in the event log.",
                details={"event_cursor": request.event_cursor},
            )
        expected_projection_version = int(cursor_event["sequence_no"])
        if request.projection_version != expected_projection_version:
            return _failed_result(
                request,
                reason_code="projection_version_mismatch",
                message="Replay resume projection version must match the cursor event sequence.",
                details={
                    "expected_projection_version": expected_projection_version,
                    "actual_projection_version": request.projection_version,
                },
            )
        replay_events = _events_through_cursor(events, cursor_event)
        missing_sequence_no = _first_missing_sequence_no(replay_events)
        if missing_sequence_no is not None:
            return _failed_result(
                request,
                reason_code="event_range_not_contiguous",
                message="Replay resume event range is not contiguous.",
                details={"missing_sequence_no": missing_sequence_no},
            )
        event_range = {
            "start_sequence_no": min(int(event["sequence_no"]) for event in replay_events),
            "end_sequence_no": expected_projection_version,
        }
        watermark = build_replay_watermark(replay_events, request, event_range)
        return request, cursor_event, replay_events, event_range, watermark

    if request.resume_kind == RESUME_KIND_GRAPH_VERSION:
        target_sequence_no = _graph_version_sequence_no(request.graph_version)
        if target_sequence_no is None:
            return _failed_result(
                request,
                reason_code="missing_graph_version",
                message="Replay resume requires a valid graph version.",
                details={"graph_version": request.graph_version},
            )
        target_event = next(
            (event for event in events if int(event.get("sequence_no", 0)) == target_sequence_no),
            None,
        )
        if target_event is None:
            return _failed_result(
                request,
                reason_code="graph_version_out_of_range",
                message="Replay resume graph version was not found in the event log.",
                details={"graph_version": request.graph_version},
            )
        if str(target_event.get("event_type")) not in _GRAPH_MUTATION_EVENTS:
            return _failed_result(
                request,
                reason_code="graph_version_not_graph_mutation",
                message="Replay resume graph version does not point to a graph mutation event.",
                details={
                    "graph_version": request.graph_version,
                    "event_type": str(target_event.get("event_type")),
                },
            )
        expected_projection_version = int(target_event["sequence_no"])
        if request.projection_version != expected_projection_version:
            return _failed_result(
                request,
                reason_code="projection_version_mismatch",
                message="Replay resume projection version must match the graph version event sequence.",
                details={
                    "expected_projection_version": expected_projection_version,
                    "actual_projection_version": request.projection_version,
                },
            )
        if str(target_event.get("event_type")) == EVENT_GRAPH_PATCH_APPLIED:
            actual_graph_patch_hash = str(_event_payload(target_event).get("patch_hash") or "").strip()
            if not actual_graph_patch_hash:
                return _failed_result(
                    request,
                    reason_code="graph_patch_hash_missing",
                    message="Replay resume graph patch event is missing patch_hash.",
                    details={"graph_version": request.graph_version},
                )
            if request.expected_graph_patch_hash and actual_graph_patch_hash != request.expected_graph_patch_hash:
                return _failed_result(
                    request,
                    reason_code="graph_patch_hash_mismatch",
                    message="Replay resume graph patch hash does not match the pinned request hash.",
                    details={
                        "expected_graph_patch_hash": request.expected_graph_patch_hash,
                        "actual_graph_patch_hash": actual_graph_patch_hash,
                    },
                )
        replay_events = _events_through_cursor(events, target_event)
        missing_sequence_no = _first_missing_sequence_no(replay_events)
        if missing_sequence_no is not None:
            return _failed_result(
                request,
                reason_code="event_range_not_contiguous",
                message="Replay resume event range is not contiguous.",
                details={"missing_sequence_no": missing_sequence_no},
            )
        event_range = {
            "start_sequence_no": min(int(event["sequence_no"]) for event in replay_events),
            "end_sequence_no": expected_projection_version,
        }
        if request.event_cursor and request.event_cursor != str(target_event["event_id"]):
            return _failed_result(
                request,
                reason_code="event_cursor_mismatch",
                message="Replay resume event cursor must match the graph version event.",
                details={
                    "expected_event_cursor": str(target_event["event_id"]),
                    "actual_event_cursor": request.event_cursor,
                },
            )
        if request.event_range is not None and request.event_range != event_range:
            return _failed_result(
                request,
                reason_code="event_range_mismatch",
                message="Replay resume event range must match the graph version event range.",
                details={
                    "expected_event_range": event_range,
                    "actual_event_range": request.event_range,
                },
            )
        resume_request = _normalize_replay_resume_request(
            request,
            event_cursor=str(target_event["event_id"]),
            event_range=event_range,
        )
        watermark = build_replay_watermark(replay_events, resume_request, event_range)
        return resume_request, target_event, replay_events, event_range, watermark

    if request.resume_kind in {RESUME_KIND_TICKET_ID, RESUME_KIND_INCIDENT_ID}:
        boundary = _resume_replay_context_boundary(events, request)
        if isinstance(boundary, ReplayResumeResult):
            return boundary
        resume_request, replay_events, event_range, watermark = boundary
        target_event = replay_events[-1]
        return resume_request, target_event, replay_events, event_range, watermark

    return _failed_result(
        request,
        reason_code="unsupported_resume_kind",
        message="Replay resume kind is not supported.",
        details={"resume_kind": request.resume_kind},
    )


def validate_replay_checkpoint(
    checkpoint: ReplayCheckpoint,
    request: ReplayResumeRequest,
    events: list[dict[str, Any]],
    *,
    covered_projections: tuple[str, ...] = DEFAULT_REPLAY_CHECKPOINT_PROJECTIONS,
    compatibility: dict[str, Any] = DEFAULT_REPLAY_CHECKPOINT_COMPATIBILITY,
) -> dict[str, Any]:
    invalidated_by: list[str] = []
    details: dict[str, Any] = {
        "checkpoint_id": checkpoint.checkpoint_id,
        "checkpoint_projection_version": checkpoint.projection_version,
        "request_projection_version": request.projection_version,
    }

    if checkpoint.invalidated_by:
        invalidated_by.append("checkpoint_already_invalidated")
    if checkpoint.schema_version != request.schema_version:
        invalidated_by.append("schema_version_mismatch")
    if checkpoint.contract_version != request.contract_version:
        invalidated_by.append("contract_version_mismatch")
    if checkpoint.projection_version != checkpoint.event_watermark.projection_version:
        invalidated_by.append("projection_version_mismatch")
    if request.projection_version is not None and checkpoint.projection_version > request.projection_version:
        invalidated_by.append("projection_version_mismatch")
    if tuple(checkpoint.covered_projections) != tuple(covered_projections):
        invalidated_by.append("covered_projection_set_mismatch")
    if dict(checkpoint.compatibility) != dict(compatibility):
        invalidated_by.append("compatibility_mismatch")

    cursor_event = next(
        (
            event
            for event in events
            if str(event.get("event_id")) == checkpoint.event_watermark.event_cursor
        ),
        None,
    )
    if cursor_event is None:
        invalidated_by.append("event_watermark_mismatch")
    else:
        cursor_sequence_no = int(cursor_event["sequence_no"])
        checkpoint_events = _events_through_cursor(events, cursor_event)
        event_range = {
            "start_sequence_no": min(int(event["sequence_no"]) for event in checkpoint_events),
            "end_sequence_no": cursor_sequence_no,
        }
        if (
            cursor_sequence_no != checkpoint.event_watermark.projection_version
            or event_range != checkpoint.event_watermark.event_range
            or _event_log_hash(checkpoint_events) != checkpoint.event_watermark.event_log_hash
        ):
            invalidated_by.append("event_watermark_mismatch")

    if not invalidated_by and _checkpoint_hash(checkpoint) != checkpoint.checkpoint_hash:
        invalidated_by.append("checkpoint_hash_mismatch")

    return {
        "valid": not invalidated_by,
        "invalidated_by": list(dict.fromkeys(invalidated_by)),
        "diagnostic": details,
    }


def _checkpoint_diagnostic(
    *,
    mode: str,
    checkpoint: ReplayCheckpoint,
    invalidated_by: list[str] | None = None,
    incremental_events: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    incremental_events = incremental_events or []
    return {
        "mode": mode,
        "checkpoint_id": checkpoint.checkpoint_id,
        "checkpoint_projection_version": checkpoint.projection_version,
        "start_after_event_cursor": checkpoint.event_watermark.event_cursor,
        "incremental_event_count": len(incremental_events),
        "incremental_start_sequence_no": (
            min(int(event["sequence_no"]) for event in incremental_events)
            if incremental_events
            else None
        ),
        "invalidated_by": list(invalidated_by or []),
    }


def build_replay_bundle_report(
    resume_result: ReplayResumeResult,
    artifact_manifest: ReplayHashManifest,
    *,
    checkpoint: ReplayCheckpoint | None = None,
    resume_source: dict[str, Any] | None = None,
) -> ReplayBundleReport:
    resolved_resume_source = resume_source or {
        "resume_kind": resume_result.resume_request.resume_kind,
        "event_cursor": resume_result.resume_request.event_cursor,
        "graph_version": resume_result.resume_request.graph_version,
        "ticket_id": resume_result.resume_request.ticket_id,
        "incident_id": resume_result.resume_request.incident_id,
        "request_hash": resume_result.resume_request.request_hash,
    }
    checkpoint_watermark = (
        checkpoint.event_watermark.model_dump(mode="json")
        if checkpoint is not None
        else None
    )
    document_materialized_views = _document_materialized_views_deferred()
    report_status = (
        "READY"
        if resume_result.status == "READY" and artifact_manifest.status == "READY"
        else "FAILED"
    )
    report_payload = {
        "status": report_status,
        "resume_source": resolved_resume_source,
        "source_event_range": (
            dict(resume_result.event_range)
            if resume_result.event_range is not None
            else None
        ),
        "checkpoint_watermark": checkpoint_watermark,
        "checkpoint_refs": _checkpoint_refs(checkpoint),
        "projection_version": resume_result.projection_version,
        "artifact_hash_manifest": artifact_manifest.model_dump(mode="json"),
        "document_materialized_views": document_materialized_views,
        "diagnostics": {
            "resume": dict(resume_result.diagnostic),
            "artifact_hash_manifest": artifact_manifest.diagnostics,
            "document_materialized_views": document_materialized_views["diagnostics"],
        },
        "replay_compatibility": dict(artifact_manifest.replay_compatibility),
        "report_hash": "",
    }
    report_payload["report_hash"] = _bundle_report_hash(report_payload)
    return ReplayBundleReport.model_validate(report_payload)


def _summary_from_checkpoint_repository(
    repository: ControlPlaneRepository,
    replay_events: list[dict[str, Any]],
    request: ReplayResumeRequest,
    target_event: dict[str, Any],
) -> dict[str, Any] | None:
    if request.resume_kind == RESUME_KIND_EVENT_ID:
        return None
    if request.resume_kind == RESUME_KIND_GRAPH_VERSION:
        workflow_id = str(target_event.get("workflow_id") or "").strip()
        return _base_projection_summary(repository, workflow_id)
    if request.resume_kind == RESUME_KIND_TICKET_ID:
        ticket_id = str(request.ticket_id or "").strip()
        ticket = repository.get_current_ticket_projection(ticket_id)
        if ticket is None:
            raise KeyError("ticket_resume_ticket_missing")
        workflow_id = str(ticket["workflow_id"])
        projection_summary = _base_projection_summary(repository, workflow_id)
        projection_summary["ticket_context"] = _ticket_context(
            repository,
            replay_events,
            ticket_id,
        )
        return projection_summary
    if request.resume_kind == RESUME_KIND_INCIDENT_ID:
        incident_id = str(request.incident_id or "").strip()
        incident = repository.get_incident_projection(incident_id)
        if incident is None:
            raise KeyError("incident_resume_incident_missing")
        workflow_id = str(incident["workflow_id"])
        projection_summary = _base_projection_summary(repository, workflow_id)
        projection_summary["incident_context"] = _incident_context(
            repository,
            replay_events,
            incident_id,
            str(request.ticket_id).strip() if request.ticket_id else None,
        )
        return projection_summary
    return None


def resume_replay_with_checkpoint(
    events: list[dict[str, Any]],
    request: ReplayResumeRequest,
    *,
    checkpoint: ReplayCheckpoint | None = None,
    allow_full_replay_fallback: bool = False,
    covered_projections: tuple[str, ...] = DEFAULT_REPLAY_CHECKPOINT_PROJECTIONS,
    compatibility: dict[str, Any] = DEFAULT_REPLAY_CHECKPOINT_COMPATIBILITY,
) -> ReplayResumeResult:
    if checkpoint is None:
        return _dispatch_full_replay_resume(events, request)

    boundary = _resolve_checkpoint_boundary(events, request)
    if isinstance(boundary, ReplayResumeResult):
        return boundary
    resume_request, target_event, replay_events, event_range, watermark = boundary

    validation = validate_replay_checkpoint(
        checkpoint,
        resume_request,
        events,
        covered_projections=covered_projections,
        compatibility=compatibility,
    )
    invalidated_by = list(validation["invalidated_by"])
    if invalidated_by:
        if allow_full_replay_fallback:
            fallback = _dispatch_full_replay_resume(events, request)
            if fallback.status != "READY":
                return fallback
            return fallback.model_copy(
                update={
                    "diagnostic": {
                        **fallback.diagnostic,
                        "checkpoint": _checkpoint_diagnostic(
                            mode="full_replay_fallback",
                            checkpoint=checkpoint,
                            invalidated_by=invalidated_by,
                        ),
                    }
                }
            )
        return _failed_result(
            resume_request,
            reason_code="checkpoint_invalidated",
            message="Replay checkpoint is stale or incompatible.",
            details={
                "invalidated_by": invalidated_by,
                "checkpoint": _checkpoint_diagnostic(
                    mode="invalid",
                    checkpoint=checkpoint,
                    invalidated_by=invalidated_by,
                ),
            },
        )

    incremental_events = [
        event
        for event in replay_events
        if int(event["sequence_no"]) > int(checkpoint.projection_version)
    ]
    try:
        with TemporaryDirectory(prefix="boardroom-checkpoint-replay-") as temp_dir:
            repository = _build_replay_repository_from_checkpoint(
                temp_dir,
                checkpoint,
                replay_events,
                incremental_events,
            )
            projection_summary = _summary_from_checkpoint_repository(
                repository,
                replay_events,
                resume_request,
                target_event,
            )
    except RuntimeNodeViewResolutionError as exc:
        return _failed_result(
            resume_request,
            reason_code="runtime_node_view_broken",
            message="Ticket resume runtime node view is inconsistent.",
            details={"error_message": str(exc), "ticket_id": resume_request.ticket_id},
        )
    except KeyError as exc:
        reason_code = str(exc.args[0])
        return _failed_result(
            resume_request,
            reason_code=reason_code,
            message="Replay checkpoint resume context is incomplete.",
            details={"ticket_id": resume_request.ticket_id, "incident_id": resume_request.incident_id},
        )
    except Exception as exc:
        return _failed_result(
            resume_request,
            reason_code="projection_rebuild_failed",
            message="Replay checkpoint projection replay failed.",
            details={
                "error_type": type(exc).__name__,
                "error_message": str(exc),
            },
        )

    message_by_kind = {
        RESUME_KIND_EVENT_ID: "Replay resume point is ready.",
        RESUME_KIND_GRAPH_VERSION: "Replay graph version resume point is ready.",
        RESUME_KIND_TICKET_ID: "Replay ticket resume point is ready.",
        RESUME_KIND_INCIDENT_ID: "Replay incident resume point is ready.",
    }
    diagnostic = {
        "reason_code": "resume_ready",
        "message": message_by_kind.get(resume_request.resume_kind, "Replay resume point is ready."),
        "checkpoint": _checkpoint_diagnostic(
            mode="incremental",
            checkpoint=checkpoint,
            incremental_events=incremental_events,
        ),
    }
    if resume_request.graph_version:
        diagnostic["graph_version"] = resume_request.graph_version
    if resume_request.ticket_id:
        diagnostic["ticket_id"] = resume_request.ticket_id
    if resume_request.incident_id:
        diagnostic["incident_id"] = resume_request.incident_id
    return ReplayResumeResult(
        status="READY",
        resume_request=resume_request,
        replay_watermark=watermark,
        event_cursor=resume_request.event_cursor,
        projection_version=resume_request.projection_version,
        event_range=event_range,
        schema_version=resume_request.schema_version,
        contract_version=resume_request.contract_version,
        projection_summary=projection_summary,
        diagnostic=diagnostic,
    )


def _policy_snapshot_from_ticket_graph_snapshot(snapshot) -> ProgressionSnapshot:
    inactive_refs = {
        ref
        for node in snapshot.nodes
        for ref in [str(node.graph_node_id or "").strip(), str(node.ticket_id or "").strip()]
        if ref and str(node.node_status or "").strip() in {"CANCELLED", "SUPERSEDED"}
    }
    return ProgressionSnapshot(
        workflow_id=snapshot.workflow_id,
        graph_version=snapshot.graph_version,
        node_refs=[str(node.graph_node_id or "").strip() for node in snapshot.nodes],
        ticket_refs=[str(node.ticket_id or "").strip() for node in snapshot.nodes if node.ticket_id],
        runtime_nodes=[
            {
                "node_ref": str(node.graph_node_id or "").strip(),
                "node_id": str(node.runtime_node_id or node.node_id or "").strip(),
                "latest_ticket_id": str(node.ticket_id or "").strip(),
                "status": str(node.node_status or "").strip(),
                "blocking_reason_code": str(node.blocking_reason_code or "").strip(),
            }
            for node in snapshot.nodes
            if str(node.graph_node_id or "").strip() and node.ticket_id
        ],
        graph_nodes=[
            {
                "node_ref": str(node.graph_node_id or "").strip(),
                "node_id": str(node.node_id or "").strip(),
                "ticket_id": str(node.ticket_id or "").strip(),
                "ticket_status": str(node.ticket_status or "").strip(),
                "node_status": str(node.node_status or "").strip(),
                "blocking_reason_code": str(node.blocking_reason_code or "").strip(),
            }
            for node in snapshot.nodes
            if str(node.graph_node_id or "").strip()
        ],
        graph_edges=[
            {
                "edge_type": str(edge.edge_type or "").strip(),
                "source_node_ref": str(edge.source_graph_node_id or "").strip(),
                "target_node_ref": str(edge.target_graph_node_id or "").strip(),
                "source_ticket_id": str(edge.source_ticket_id or "").strip(),
                "target_ticket_id": str(edge.target_ticket_id or "").strip(),
            }
            for edge in snapshot.edges
        ],
        cancelled_refs=[
            ref
            for ref in inactive_refs
            if any(
                ref in {str(node.graph_node_id or "").strip(), str(node.ticket_id or "").strip()}
                and str(node.node_status or "").strip() == "CANCELLED"
                for node in snapshot.nodes
            )
        ],
        superseded_refs=[
            ref
            for ref in inactive_refs
            if any(
                ref in {str(node.graph_node_id or "").strip(), str(node.ticket_id or "").strip()}
                and str(node.node_status or "").strip() == "SUPERSEDED"
                for node in snapshot.nodes
            )
        ],
        graph_reduction_issues=[
            {
                "issue_code": issue.issue_code,
                "detail": issue.detail,
                "ticket_id": issue.ticket_id,
                "node_id": issue.node_id,
                "node_ref": issue.node_id,
                "related_ticket_id": issue.related_ticket_id,
            }
            for issue in snapshot.reduction_issues
        ],
        blocked_ticket_ids=list(snapshot.index_summary.blocked_ticket_ids),
        blocked_node_refs=list(snapshot.index_summary.blocked_graph_node_ids),
        in_flight_ticket_ids=list(snapshot.index_summary.in_flight_ticket_ids),
        in_flight_node_refs=list(snapshot.index_summary.in_flight_graph_node_ids),
        blocked_reasons=[
            {
                "reason_code": item.reason_code,
                "ticket_ids": list(item.ticket_ids),
                "node_refs": list(item.node_ids),
            }
            for item in snapshot.index_summary.blocked_reasons
        ],
    )


def _projection_summary_from_replay_events(
    events: list[dict[str, Any]],
    *,
    workflow_id: str,
) -> dict[str, Any]:
    with TemporaryDirectory(prefix="boardroom-replay-") as temp_dir:
        repository = _build_replay_repository(temp_dir, events)
        snapshot = build_ticket_graph_snapshot(repository, workflow_id)
        evaluation = evaluate_progression_graph(_policy_snapshot_from_ticket_graph_snapshot(snapshot))
        return {
            "workflow_id": snapshot.workflow_id,
            "graph_version": snapshot.graph_version,
            "current_ticket_ids_by_node_ref": evaluation.current_ticket_ids_by_node_ref,
            "effective_node_refs": evaluation.effective_node_refs,
            "effective_edges": evaluation.effective_edges,
            "ready_ticket_ids": evaluation.ready_ticket_ids,
            "ready_node_refs": evaluation.ready_node_refs,
            "blocked_ticket_ids": evaluation.blocked_ticket_ids,
            "blocked_node_refs": evaluation.blocked_node_refs,
            "in_flight_ticket_ids": evaluation.in_flight_ticket_ids,
            "in_flight_node_refs": evaluation.in_flight_node_refs,
            "completed_ticket_ids": evaluation.completed_ticket_ids,
            "completed_node_refs": evaluation.completed_node_refs,
            "graph_complete": evaluation.graph_complete,
            "stale_orphan_pending_refs": evaluation.stale_orphan_pending_refs,
            "graph_reduction_issues": evaluation.graph_reduction_issues,
            "index_summary": snapshot.index_summary.model_dump(mode="json"),
        }


def _base_projection_summary(repository: ControlPlaneRepository, workflow_id: str) -> dict[str, Any]:
    snapshot = build_ticket_graph_snapshot(repository, workflow_id)
    evaluation = evaluate_progression_graph(_policy_snapshot_from_ticket_graph_snapshot(snapshot))
    return {
        "workflow_id": snapshot.workflow_id,
        "graph_version": snapshot.graph_version,
        "current_ticket_ids_by_node_ref": evaluation.current_ticket_ids_by_node_ref,
        "effective_node_refs": evaluation.effective_node_refs,
        "effective_edges": evaluation.effective_edges,
        "ready_ticket_ids": evaluation.ready_ticket_ids,
        "ready_node_refs": evaluation.ready_node_refs,
        "blocked_ticket_ids": evaluation.blocked_ticket_ids,
        "blocked_node_refs": evaluation.blocked_node_refs,
        "in_flight_ticket_ids": evaluation.in_flight_ticket_ids,
        "in_flight_node_refs": evaluation.in_flight_node_refs,
        "completed_ticket_ids": evaluation.completed_ticket_ids,
        "completed_node_refs": evaluation.completed_node_refs,
        "graph_complete": evaluation.graph_complete,
        "stale_orphan_pending_refs": evaluation.stale_orphan_pending_refs,
        "graph_reduction_issues": evaluation.graph_reduction_issues,
        "index_summary": snapshot.index_summary.model_dump(mode="json"),
    }


def _event_payloads_for_ticket(
    events: list[dict[str, Any]],
    ticket_id: str,
) -> list[dict[str, Any]]:
    return [
        _event_payload(event)
        for event in sorted(events, key=lambda item: int(item["sequence_no"]))
        if str(_event_payload(event).get("ticket_id") or "").strip() == ticket_id
    ]


def _stable_unique(values: list[Any]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = str(value or "").strip()
        if not normalized or normalized in seen:
            continue
        result.append(normalized)
        seen.add(normalized)
    return result


def _related_refs_for_ticket(
    repository: ControlPlaneRepository,
    events: list[dict[str, Any]],
    ticket_id: str,
) -> dict[str, list[str]]:
    ticket_payloads = _event_payloads_for_ticket(events, ticket_id)
    process_assets = repository.list_process_assets_by_producer_ticket(
        ticket_id,
        visibility_statuses={"CONSUMABLE", "SUPERSEDED"},
    )
    return {
        "artifact_refs": _stable_unique(
            [
                ref
                for payload in ticket_payloads
                for ref in [
                    *list(payload.get("input_artifact_refs") or []),
                    *list(payload.get("artifact_refs") or []),
                ]
            ]
        ),
        "evidence_refs": _stable_unique(
            [
                ref
                for payload in ticket_payloads
                for ref in list(payload.get("verification_evidence_refs") or [])
            ]
        ),
        "process_asset_refs": _stable_unique(
            [
                *[asset["process_asset_ref"] for asset in process_assets],
                *[
                    ref
                    for payload in ticket_payloads
                    for ref in list(payload.get("input_process_asset_refs") or [])
                ],
            ]
        ),
    }


def _runtime_node_view_context_for_ticket(
    repository: ControlPlaneRepository,
    workflow_id: str,
    ticket_id: str,
) -> dict[str, Any]:
    views = build_runtime_graph_node_views(repository, workflow_id)
    view = next(
        (
            candidate
            for candidate in views.values()
            if str(candidate.ticket_id or "").strip() == ticket_id
        ),
        None,
    )
    if view is None or view.materialization_state != "materialized":
        raise RuntimeNodeViewResolutionError(
            f"runtime node view missing materialized ticket {ticket_id}."
        )
    return _json_safe(
        {
            "node_id": view.node_id,
            "graph_node_id": view.graph_node_id,
            "runtime_node_id": view.runtime_node_id,
            "ticket_id": view.ticket_id,
            "is_placeholder": view.is_placeholder,
            "materialization_state": view.materialization_state,
            "placeholder_status": view.placeholder_status,
            "reason_code": view.reason_code,
            "open_incident_id": view.open_incident_id,
            "materialization_hint": view.materialization_hint,
        }
    )


def _ticket_context(
    repository: ControlPlaneRepository,
    replay_events: list[dict[str, Any]],
    ticket_id: str,
) -> dict[str, Any]:
    ticket = repository.get_current_ticket_projection(ticket_id)
    if ticket is None:
        raise KeyError("ticket_resume_ticket_missing")
    workflow_id = str(ticket["workflow_id"])
    status = str(ticket["status"])
    runtime_node_view = _runtime_node_view_context_for_ticket(repository, workflow_id, ticket_id)
    assignment = (
        repository.get_assignment_projection(str(ticket.get("assignment_id")))
        if ticket.get("assignment_id")
        else None
    )
    lease = repository.get_lease_projection(str(ticket.get("lease_id"))) if ticket.get("lease_id") else None
    is_in_flight = status in _IN_FLIGHT_TICKET_STATUSES
    if is_in_flight and (assignment is None or lease is None):
        raise KeyError("ticket_resume_in_flight_context_missing")
    related_refs = _related_refs_for_ticket(repository, replay_events, ticket_id)
    return {
        **_json_safe(ticket),
        "is_terminal": status in _TERMINAL_TICKET_STATUSES,
        "is_in_flight": is_in_flight,
        "terminal_state": status if status in _TERMINAL_TICKET_STATUSES else None,
        "runtime_node_view": runtime_node_view,
        "assignment": _json_safe(assignment) if assignment is not None else None,
        "lease": _json_safe(lease) if lease is not None else None,
        "related_artifact_refs": related_refs["artifact_refs"],
        "related_evidence_refs": related_refs["evidence_refs"],
        "related_process_asset_refs": related_refs["process_asset_refs"],
    }


def _incident_lineage_events(
    events: list[dict[str, Any]],
    incident_id: str,
) -> list[dict[str, Any]]:
    return [
        {
            "event_id": str(event["event_id"]),
            "event_type": str(event["event_type"]),
            "sequence_no": int(event["sequence_no"]),
            "payload": _event_payload(event),
        }
        for event in sorted(events, key=lambda item: int(item["sequence_no"]))
        if str(_event_payload(event).get("incident_id") or "").strip() == incident_id
        and str(event.get("event_type"))
        in {EVENT_INCIDENT_OPENED, EVENT_INCIDENT_RECOVERY_STARTED, EVENT_INCIDENT_CLOSED}
    ]


def _recovery_action_lineage(lineage_events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    for event in lineage_events:
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        recovery_action = payload.get("recovery_action")
        if isinstance(recovery_action, dict):
            actions.append(dict(recovery_action))
        for action in list(payload.get("recovery_actions") or []):
            if isinstance(action, dict):
                actions.append(dict(action))
    return _json_safe(actions)


def _incident_context(
    repository: ControlPlaneRepository,
    replay_events: list[dict[str, Any]],
    incident_id: str,
    pinned_ticket_id: str | None,
) -> dict[str, Any]:
    incident = repository.get_incident_projection(incident_id)
    if incident is None:
        raise KeyError("incident_resume_incident_missing")
    incident_ticket_id = str(incident.get("ticket_id") or "").strip()
    source_ticket_id = str(pinned_ticket_id or incident_ticket_id).strip()
    if pinned_ticket_id and incident_ticket_id and pinned_ticket_id != incident_ticket_id:
        raise KeyError("incident_source_ticket_mismatch")
    if not source_ticket_id:
        raise KeyError("incident_source_ticket_missing")
    source_ticket = repository.get_current_ticket_projection(source_ticket_id)
    if source_ticket is None:
        raise KeyError("incident_source_ticket_missing")
    lineage_events = _incident_lineage_events(replay_events, incident_id)
    recovery_actions = _recovery_action_lineage(lineage_events)
    payload = incident.get("payload") if isinstance(incident.get("payload"), dict) else {}
    followup_action = str(payload.get("followup_action") or "").strip() or None
    recommended_followup_action = recommended_incident_followup_action_from_policy_input(incident)
    return {
        **_json_safe(incident),
        "source_ticket_context": _json_safe(source_ticket),
        "followup_action": followup_action,
        "recommended_followup_action": recommended_followup_action,
        "incident_event_lineage": _json_safe(lineage_events),
        "recovery_action_lineage": recovery_actions,
        "rework_restore_policy_input": {
            "actions": recovery_actions,
        },
    }


def resume_replay_from_event_id(
    events: list[dict[str, Any]],
    request: ReplayResumeRequest,
) -> ReplayResumeResult:
    if request.resume_kind != RESUME_KIND_EVENT_ID:
        return _failed_result(
            request,
            reason_code="unsupported_resume_kind",
            message="Only event_id replay resume is supported in Round 10A.",
            details={"resume_kind": request.resume_kind},
        )
    if not request.event_cursor:
        return _failed_result(
            request,
            reason_code="missing_event_cursor",
            message="Replay resume requires an event cursor.",
        )

    cursor_event = next(
        (event for event in events if str(event.get("event_id")) == request.event_cursor),
        None,
    )
    if cursor_event is None:
        return _failed_result(
            request,
            reason_code="event_cursor_out_of_range",
            message="Replay resume event cursor was not found in the event log.",
            details={"event_cursor": request.event_cursor},
        )

    expected_projection_version = int(cursor_event["sequence_no"])
    if request.projection_version != expected_projection_version:
        return _failed_result(
            request,
            reason_code="projection_version_mismatch",
            message="Replay resume projection version must match the cursor event sequence.",
            details={
                "expected_projection_version": expected_projection_version,
                "actual_projection_version": request.projection_version,
            },
        )

    replay_events = _events_through_cursor(events, cursor_event)
    missing_sequence_no = _first_missing_sequence_no(replay_events)
    if missing_sequence_no is not None:
        return _failed_result(
            request,
            reason_code="event_range_not_contiguous",
            message="Replay resume event range is not contiguous.",
            details={"missing_sequence_no": missing_sequence_no},
        )

    start_sequence_no = min(int(event["sequence_no"]) for event in replay_events)
    event_range = {
        "start_sequence_no": start_sequence_no,
        "end_sequence_no": expected_projection_version,
    }
    watermark = build_replay_watermark(replay_events, request, event_range)
    return ReplayResumeResult(
        status="READY",
        resume_request=request,
        replay_watermark=watermark,
        event_cursor=request.event_cursor,
        projection_version=request.projection_version,
        event_range=event_range,
        schema_version=request.schema_version,
        contract_version=request.contract_version,
        projection_summary=None,
        diagnostic={
            "reason_code": "resume_ready",
            "message": "Replay resume point is ready.",
        },
    )


def resume_replay_from_graph_version(
    events: list[dict[str, Any]],
    request: ReplayResumeRequest,
) -> ReplayResumeResult:
    if request.resume_kind != RESUME_KIND_GRAPH_VERSION:
        return _failed_result(
            request,
            reason_code="unsupported_resume_kind",
            message="Only graph_version replay resume is supported by this entrypoint.",
            details={"resume_kind": request.resume_kind},
        )
    target_sequence_no = _graph_version_sequence_no(request.graph_version)
    if target_sequence_no is None:
        return _failed_result(
            request,
            reason_code="missing_graph_version",
            message="Replay resume requires a valid graph version.",
            details={"graph_version": request.graph_version},
        )

    target_event = next(
        (event for event in events if int(event.get("sequence_no", 0)) == target_sequence_no),
        None,
    )
    if target_event is None:
        return _failed_result(
            request,
            reason_code="graph_version_out_of_range",
            message="Replay resume graph version was not found in the event log.",
            details={"graph_version": request.graph_version},
        )
    if str(target_event.get("event_type")) not in _GRAPH_MUTATION_EVENTS:
        return _failed_result(
            request,
            reason_code="graph_version_not_graph_mutation",
            message="Replay resume graph version does not point to a graph mutation event.",
            details={
                "graph_version": request.graph_version,
                "event_type": str(target_event.get("event_type")),
            },
        )

    expected_projection_version = int(target_event["sequence_no"])
    if request.projection_version != expected_projection_version:
        return _failed_result(
            request,
            reason_code="projection_version_mismatch",
            message="Replay resume projection version must match the graph version event sequence.",
            details={
                "expected_projection_version": expected_projection_version,
                "actual_projection_version": request.projection_version,
            },
        )

    if str(target_event.get("event_type")) == EVENT_GRAPH_PATCH_APPLIED and request.expected_graph_patch_hash:
        actual_graph_patch_hash = str(_event_payload(target_event).get("patch_hash") or "").strip()
        if actual_graph_patch_hash != request.expected_graph_patch_hash:
            return _failed_result(
                request,
                reason_code="graph_patch_hash_mismatch",
                message="Replay resume graph patch hash does not match the pinned request hash.",
                details={
                    "expected_graph_patch_hash": request.expected_graph_patch_hash,
                    "actual_graph_patch_hash": actual_graph_patch_hash,
                },
            )
    if str(target_event.get("event_type")) == EVENT_GRAPH_PATCH_APPLIED:
        actual_graph_patch_hash = str(_event_payload(target_event).get("patch_hash") or "").strip()
        if not actual_graph_patch_hash:
            return _failed_result(
                request,
                reason_code="graph_patch_hash_missing",
                message="Replay resume graph patch event is missing patch_hash.",
                details={"graph_version": request.graph_version},
            )

    replay_events = _events_through_cursor(events, target_event)
    missing_sequence_no = _first_missing_sequence_no(replay_events)
    if missing_sequence_no is not None:
        return _failed_result(
            request,
            reason_code="event_range_not_contiguous",
            message="Replay resume event range is not contiguous.",
            details={"missing_sequence_no": missing_sequence_no},
        )

    workflow_id = str(target_event.get("workflow_id") or "").strip()
    if not workflow_id:
        return _failed_result(
            request,
            reason_code="missing_workflow_id",
            message="Replay resume graph version event is missing workflow_id.",
        )

    event_range = {
        "start_sequence_no": min(int(event["sequence_no"]) for event in replay_events),
        "end_sequence_no": expected_projection_version,
    }
    if request.event_cursor and request.event_cursor != str(target_event["event_id"]):
        return _failed_result(
            request,
            reason_code="event_cursor_mismatch",
            message="Replay resume event cursor must match the graph version event.",
            details={
                "expected_event_cursor": str(target_event["event_id"]),
                "actual_event_cursor": request.event_cursor,
            },
        )
    if request.event_range is not None and request.event_range != event_range:
        return _failed_result(
            request,
            reason_code="event_range_mismatch",
            message="Replay resume event range must match the graph version event range.",
            details={
                "expected_event_range": event_range,
                "actual_event_range": request.event_range,
            },
        )
    resume_request = _normalize_replay_resume_request(
        request,
        event_cursor=str(target_event["event_id"]),
        event_range=event_range,
    )
    watermark = build_replay_watermark(replay_events, resume_request, event_range)
    try:
        projection_summary = _projection_summary_from_replay_events(
            replay_events,
            workflow_id=workflow_id,
        )
    except Exception as exc:
        return _failed_result(
            resume_request,
            reason_code="projection_rebuild_failed",
            message="Replay resume projection rebuild failed.",
            details={
                "error_type": type(exc).__name__,
                "error_message": str(exc),
            },
        )
    return ReplayResumeResult(
        status="READY",
        resume_request=resume_request,
        replay_watermark=watermark,
        event_cursor=str(target_event["event_id"]),
        projection_version=resume_request.projection_version,
        event_range=event_range,
        schema_version=resume_request.schema_version,
        contract_version=resume_request.contract_version,
        projection_summary=projection_summary,
        diagnostic={
            "reason_code": "resume_ready",
            "message": "Replay graph version resume point is ready.",
            "graph_version": resume_request.graph_version,
        },
    )


def _resume_replay_context_boundary(
    events: list[dict[str, Any]],
    request: ReplayResumeRequest,
) -> tuple[ReplayResumeRequest, list[dict[str, Any]], dict[str, int], ReplayWatermark] | ReplayResumeResult:
    boundary_event_or_failure = _resolve_resume_boundary_event(events, request)
    if isinstance(boundary_event_or_failure, ReplayResumeResult):
        return boundary_event_or_failure
    boundary_event = boundary_event_or_failure
    expected_projection_version = int(boundary_event["sequence_no"])
    if request.projection_version != expected_projection_version:
        return _failed_result(
            request,
            reason_code="projection_version_mismatch",
            message="Replay resume projection version must match the resume boundary event sequence.",
            details={
                "expected_projection_version": expected_projection_version,
                "actual_projection_version": request.projection_version,
            },
        )

    replay_events = _events_through_cursor(events, boundary_event)
    missing_sequence_no = _first_missing_sequence_no(replay_events)
    if missing_sequence_no is not None:
        return _failed_result(
            request,
            reason_code="event_range_not_contiguous",
            message="Replay resume event range is not contiguous.",
            details={"missing_sequence_no": missing_sequence_no},
        )

    event_range = {
        "start_sequence_no": min(int(event["sequence_no"]) for event in replay_events),
        "end_sequence_no": expected_projection_version,
    }
    if request.event_range is not None and request.event_range != event_range:
        return _failed_result(
            request,
            reason_code="event_range_mismatch",
            message="Replay resume event range must match the resume boundary event range.",
            details={
                "expected_event_range": event_range,
                "actual_event_range": request.event_range,
            },
        )

    resume_request = _normalize_replay_resume_request(
        request,
        event_cursor=str(boundary_event["event_id"]),
        event_range=event_range,
    )
    watermark = build_replay_watermark(replay_events, resume_request, event_range)
    return resume_request, replay_events, event_range, watermark


def resume_replay_from_ticket_id(
    events: list[dict[str, Any]],
    request: ReplayResumeRequest,
) -> ReplayResumeResult:
    if request.resume_kind != RESUME_KIND_TICKET_ID:
        return _failed_result(
            request,
            reason_code="unsupported_resume_kind",
            message="Only ticket_id replay resume is supported by this entrypoint.",
            details={"resume_kind": request.resume_kind},
        )
    ticket_id = str(request.ticket_id or "").strip()
    if not ticket_id:
        return _failed_result(
            request,
            reason_code="missing_ticket_id",
            message="Ticket resume requires a ticket_id.",
        )
    boundary = _resume_replay_context_boundary(events, request)
    if isinstance(boundary, ReplayResumeResult):
        return boundary
    resume_request, replay_events, event_range, watermark = boundary
    try:
        with TemporaryDirectory(prefix="boardroom-replay-ticket-") as temp_dir:
            repository = _build_replay_repository(temp_dir, replay_events)
            ticket = repository.get_current_ticket_projection(ticket_id)
            if ticket is None:
                return _failed_result(
                    resume_request,
                    reason_code="ticket_resume_ticket_missing",
                    message="Ticket resume source ticket is missing after replay.",
                    details={"ticket_id": ticket_id},
                )
            workflow_id = str(ticket["workflow_id"])
            projection_summary = _base_projection_summary(repository, workflow_id)
            projection_summary["ticket_context"] = _ticket_context(
                repository,
                replay_events,
                ticket_id,
            )
    except RuntimeNodeViewResolutionError as exc:
        return _failed_result(
            resume_request,
            reason_code="runtime_node_view_broken",
            message="Ticket resume runtime node view is inconsistent.",
            details={"error_message": str(exc), "ticket_id": ticket_id},
        )
    except KeyError as exc:
        reason_code = str(exc.args[0])
        return _failed_result(
            resume_request,
            reason_code=reason_code,
            message="Ticket resume context is incomplete.",
            details={"ticket_id": ticket_id},
        )
    except Exception as exc:
        return _failed_result(
            resume_request,
            reason_code="projection_rebuild_failed",
            message="Replay resume projection rebuild failed.",
            details={
                "error_type": type(exc).__name__,
                "error_message": str(exc),
            },
        )
    return ReplayResumeResult(
        status="READY",
        resume_request=resume_request,
        replay_watermark=watermark,
        event_cursor=resume_request.event_cursor,
        projection_version=resume_request.projection_version,
        event_range=event_range,
        schema_version=resume_request.schema_version,
        contract_version=resume_request.contract_version,
        projection_summary=projection_summary,
        diagnostic={
            "reason_code": "resume_ready",
            "message": "Replay ticket resume point is ready.",
            "ticket_id": ticket_id,
        },
    )


def resume_replay_from_incident_id(
    events: list[dict[str, Any]],
    request: ReplayResumeRequest,
) -> ReplayResumeResult:
    if request.resume_kind != RESUME_KIND_INCIDENT_ID:
        return _failed_result(
            request,
            reason_code="unsupported_resume_kind",
            message="Only incident_id replay resume is supported by this entrypoint.",
            details={"resume_kind": request.resume_kind},
        )
    incident_id = str(request.incident_id or "").strip()
    if not incident_id:
        return _failed_result(
            request,
            reason_code="missing_incident_id",
            message="Incident resume requires an incident_id.",
        )
    boundary = _resume_replay_context_boundary(events, request)
    if isinstance(boundary, ReplayResumeResult):
        return boundary
    resume_request, replay_events, event_range, watermark = boundary
    try:
        with TemporaryDirectory(prefix="boardroom-replay-incident-") as temp_dir:
            repository = _build_replay_repository(temp_dir, replay_events)
            incident = repository.get_incident_projection(incident_id)
            if incident is None:
                return _failed_result(
                    resume_request,
                    reason_code="incident_resume_incident_missing",
                    message="Incident resume source incident is missing after replay.",
                    details={"incident_id": incident_id},
                )
            workflow_id = str(incident["workflow_id"])
            projection_summary = _base_projection_summary(repository, workflow_id)
            projection_summary["incident_context"] = _incident_context(
                repository,
                replay_events,
                incident_id,
                str(request.ticket_id).strip() if request.ticket_id else None,
            )
    except KeyError as exc:
        reason_code = str(exc.args[0])
        return _failed_result(
            resume_request,
            reason_code=reason_code,
            message="Incident resume context is incomplete.",
            details={"incident_id": incident_id, "ticket_id": request.ticket_id},
        )
    except Exception as exc:
        return _failed_result(
            resume_request,
            reason_code="projection_rebuild_failed",
            message="Replay resume projection rebuild failed.",
            details={
                "error_type": type(exc).__name__,
                "error_message": str(exc),
            },
        )
    return ReplayResumeResult(
        status="READY",
        resume_request=resume_request,
        replay_watermark=watermark,
        event_cursor=resume_request.event_cursor,
        projection_version=resume_request.projection_version,
        event_range=event_range,
        schema_version=resume_request.schema_version,
        contract_version=resume_request.contract_version,
        projection_summary=projection_summary,
        diagnostic={
            "reason_code": "resume_ready",
            "message": "Replay incident resume point is ready.",
            "incident_id": incident_id,
        },
    )
