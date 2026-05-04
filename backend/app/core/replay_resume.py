from __future__ import annotations

import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from datetime import datetime
from typing import Any

from app.contracts.replay import ReplayResumeRequest, ReplayResumeResult, ReplayWatermark
from app.core.constants import (
    EVENT_BOARD_REVIEW_APPROVED,
    EVENT_BOARD_REVIEW_REJECTED,
    EVENT_BOARD_REVIEW_REQUIRED,
    EVENT_GRAPH_PATCH_APPLIED,
    EVENT_INCIDENT_CLOSED,
    EVENT_INCIDENT_OPENED,
    EVENT_INCIDENT_RECOVERY_STARTED,
    EVENT_MEETING_CONCLUDED,
    EVENT_MEETING_REQUESTED,
    EVENT_MEETING_STARTED,
    EVENT_TICKET_CANCELLED,
    EVENT_TICKET_COMPLETED,
    EVENT_TICKET_CREATED,
    EVENT_TICKET_FAILED,
    EVENT_TICKET_TIMED_OUT,
    EVENT_WORKFLOW_CREATED,
    SCHEMA_VERSION,
)
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

REPLAY_RESUME_CONTRACT_VERSION = "replay-resume.v1"
RESUME_KIND_EVENT_ID = "event_id"
RESUME_KIND_GRAPH_VERSION = "graph_version"
RESUME_KIND_TICKET_ID = "ticket_id"
RESUME_KIND_INCIDENT_ID = "incident_id"
_TERMINAL_TICKET_STATUSES = {"CANCELLED", "COMPLETED", "FAILED", "TIMED_OUT"}
_IN_FLIGHT_TICKET_STATUSES = {"LEASED", "EXECUTING"}

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


def _build_replay_repository(
    temp_dir: str,
    events: list[dict[str, Any]],
) -> ControlPlaneRepository:
    repository = ControlPlaneRepository(Path(temp_dir) / "replay.db", 1000)
    repository.initialize()
    with repository.transaction() as connection:
        connection.execute("DELETE FROM events")
        for event in sorted(events, key=lambda item: int(item["sequence_no"])):
            _insert_replay_event(repository, connection, event)
        replay_events = repository.list_all_events(connection)
        _rebuild_replay_projections(repository, connection, replay_events)
    return repository


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
