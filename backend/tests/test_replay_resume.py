from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from datetime import datetime

from app.core.constants import (
    EVENT_INCIDENT_OPENED,
    EVENT_INCIDENT_RECOVERY_STARTED,
    EVENT_GRAPH_PATCH_APPLIED,
    EVENT_TICKET_ASSIGNED,
    EVENT_TICKET_CANCELLED,
    EVENT_TICKET_COMPLETED,
    EVENT_TICKET_CREATED,
    EVENT_TICKET_FAILED,
    EVENT_TICKET_LEASE_GRANTED,
    EVENT_TICKET_STARTED,
    EVENT_WORKFLOW_CREATED,
    SCHEMA_VERSION,
)
from app.core.planned_placeholder_projection import rebuild_planned_placeholder_projections
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
from app.core.replay_resume import (
    REPLAY_RESUME_CONTRACT_VERSION,
    build_replay_resume_request,
    resume_replay_from_event_id,
    resume_replay_from_graph_version,
    resume_replay_from_incident_id,
    resume_replay_from_ticket_id,
)
from app.core.ticket_graph import build_ticket_graph_snapshot
from app.core.workflow_progression import ProgressionSnapshot, evaluate_progression_graph
from app.db.repository import ControlPlaneRepository


def _event(
    sequence_no: int,
    event_id: str,
    event_type: str,
    payload: dict,
    *,
    workflow_id: str | None = "wf_replay",
) -> dict:
    return {
        "sequence_no": sequence_no,
        "event_id": event_id,
        "event_type": event_type,
        "workflow_id": workflow_id,
        "occurred_at": datetime.fromisoformat(f"2026-05-04T10:{sequence_no:02d}:00+08:00"),
        "payload_json": json.dumps(payload, sort_keys=True),
    }


def _event_payload(event: dict[str, Any]) -> dict[str, Any]:
    payload = event.get("payload")
    if isinstance(payload, dict):
        return payload
    return json.loads(str(event["payload_json"]))


def _insert_full_replay_event(connection, event: dict[str, Any]) -> None:
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
            str(event.get("actor_type") or "full-replay"),
            str(event.get("actor_id") or "full-replay"),
            event["occurred_at"].isoformat(),
            str(event.get("idempotency_key") or f"full-replay:{event['event_id']}"),
            event.get("causation_id"),
            event.get("correlation_id") or event.get("workflow_id"),
            json.dumps(_event_payload(event), sort_keys=True),
        ),
    )


def _rebuild_full_replay_projections(
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


def _progression_snapshot_from_ticket_graph_snapshot(snapshot) -> ProgressionSnapshot:
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


def _projection_summary_from_full_replay(events: list[dict[str, Any]], *, workflow_id: str) -> dict[str, Any]:
    with TemporaryDirectory(prefix="boardroom-full-replay-") as temp_dir:
        repository = ControlPlaneRepository(Path(temp_dir) / "full-replay.db", 1000)
        repository.initialize()
        with repository.transaction() as connection:
            connection.execute("DELETE FROM events")
            for event in sorted(events, key=lambda item: int(item["sequence_no"])):
                _insert_full_replay_event(connection, event)
            replay_events = repository.list_all_events(connection)
            _rebuild_full_replay_projections(repository, connection, replay_events)
        snapshot = build_ticket_graph_snapshot(repository, workflow_id)
        evaluation = evaluate_progression_graph(_progression_snapshot_from_ticket_graph_snapshot(snapshot))
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


def _events() -> list[dict]:
    return [
        _event(
            1,
            "evt_replay_001",
            EVENT_WORKFLOW_CREATED,
            {
                "north_star_goal": "Replay contract",
                "budget_cap": 500000,
                "deadline_at": None,
                "title": "Replay contract",
            },
        ),
        _event(
            2,
            "evt_replay_002",
            EVENT_TICKET_CREATED,
            {
                "ticket_id": "tkt_replay",
                "node_id": "node_replay",
                "retry_budget": 1,
                "timeout_sla_sec": 1800,
                "priority": "high",
            },
        ),
        _event(
            3,
            "evt_replay_003",
            EVENT_TICKET_CREATED,
            {
                "ticket_id": "tkt_replay_check",
                "node_id": "node_replay_check",
                "retry_budget": 1,
                "timeout_sla_sec": 1800,
                "priority": "normal",
            },
        ),
    ]


def _workflow_event_payload(title: str = "Replay contract") -> dict:
    return {
        "north_star_goal": title,
        "budget_cap": 500000,
        "deadline_at": None,
        "title": title,
    }


def _ticket_event_payload(
    ticket_id: str,
    node_id: str,
    *,
    status_detail: dict | None = None,
    parent_ticket_id: str | None = None,
) -> dict:
    payload = {
        "ticket_id": ticket_id,
        "node_id": node_id,
        "retry_budget": 1,
        "timeout_sla_sec": 1800,
        "priority": "normal",
        "graph_contract": {
            "lane_kind": "execution",
        },
    }
    if parent_ticket_id is not None:
        payload["parent_ticket_id"] = parent_ticket_id
    if status_detail:
        payload.update(status_detail)
    return payload


def _graph_equivalence_events() -> list[dict]:
    return [
        _event(
            1,
            "evt_graph_wf",
            EVENT_WORKFLOW_CREATED,
            _workflow_event_payload("Graph version resume"),
        ),
        _event(
            2,
            "evt_graph_parent",
            EVENT_TICKET_CREATED,
            _ticket_event_payload("tkt_graph_parent", "node_graph_parent"),
        ),
        _event(
            3,
            "evt_graph_old",
            EVENT_TICKET_CREATED,
            _ticket_event_payload(
                "tkt_graph_old",
                "node_graph_old",
                parent_ticket_id="tkt_graph_parent",
            ),
        ),
        _event(
            4,
            "evt_graph_new",
            EVENT_TICKET_CREATED,
            _ticket_event_payload("tkt_graph_new", "node_graph_new"),
        ),
        _event(
            5,
            "evt_graph_patch",
            EVENT_GRAPH_PATCH_APPLIED,
            {
                "patch_ref": "pa://graph-patch/graph-version-resume@1",
                "workflow_id": "wf_replay",
                "session_id": "adv_graph_version_resume",
                "proposal_ref": "pa://graph-patch-proposal/graph-version-resume@1",
                "base_graph_version": "gv_4",
                "freeze_node_ids": [],
                "unfreeze_node_ids": [],
                "focus_node_ids": ["node_graph_new"],
                "replacements": [
                    {
                        "old_node_id": "node_graph_old",
                        "new_node_id": "node_graph_new",
                    }
                ],
                "remove_node_ids": [],
                "add_nodes": [],
                "edge_additions": [
                    {
                        "edge_type": "PARENT_OF",
                        "source_node_id": "node_graph_parent",
                        "target_node_id": "node_graph_new",
                    }
                ],
                "edge_removals": [
                    {
                        "edge_type": "PARENT_OF",
                        "source_node_id": "node_graph_parent",
                        "target_node_id": "node_graph_old",
                    }
                ],
                "reason_summary": "Replace old graph branch with current branch.",
                "patch_hash": "hash-graph-version-resume",
            },
        ),
    ]


def _graph_equivalence_events_with_late_old_complete() -> list[dict]:
    return [
        *_graph_equivalence_events(),
        _event(
            6,
            "evt_graph_old_late_complete",
            EVENT_TICKET_COMPLETED,
            _ticket_event_payload("tkt_graph_old", "node_graph_old"),
        ),
    ]


def _graph_equivalence_events_with_late_old_cancelled() -> list[dict]:
    return [
        *_graph_equivalence_events(),
        _event(
            6,
            "evt_graph_old_late_cancelled",
            EVENT_TICKET_CANCELLED,
            _ticket_event_payload("tkt_graph_old", "node_graph_old"),
        ),
    ]


def _orphan_pending_events() -> list[dict]:
    return [
        _event(
            1,
            "evt_orphan_wf",
            EVENT_WORKFLOW_CREATED,
            _workflow_event_payload("Orphan pending replay"),
        ),
        _event(
            2,
            "evt_orphan_delivery",
            EVENT_TICKET_CREATED,
            _ticket_event_payload("tkt_orphan_delivery", "node_orphan_delivery"),
        ),
        _event(
            3,
            "evt_orphan_delivery_done",
            EVENT_TICKET_COMPLETED,
            _ticket_event_payload("tkt_orphan_delivery", "node_orphan_delivery"),
        ),
        _event(
            4,
            "evt_orphan_stale",
            EVENT_TICKET_CREATED,
            _ticket_event_payload("tkt_orphan_stale", "node_orphan_stale"),
        ),
        _event(
            5,
            "evt_orphan_patch",
            EVENT_GRAPH_PATCH_APPLIED,
            {
                "patch_ref": "pa://graph-patch/orphan-pending@1",
                "workflow_id": "wf_replay",
                "session_id": "adv_orphan_pending",
                "proposal_ref": "pa://graph-patch-proposal/orphan-pending@1",
                "base_graph_version": "gv_4",
                "freeze_node_ids": [],
                "unfreeze_node_ids": [],
                "focus_node_ids": [],
                "replacements": [],
                "remove_node_ids": ["node_orphan_stale"],
                "add_nodes": [],
                "edge_additions": [],
                "edge_removals": [],
                "reason_summary": "Remove stale orphan branch from effective graph.",
                "patch_hash": "hash-orphan-pending",
            },
        ),
    ]


def _ticket_resume_terminal_events() -> list[dict]:
    return [
        _event(
            1,
            "evt_ticket_resume_wf",
            EVENT_WORKFLOW_CREATED,
            _workflow_event_payload("Ticket resume"),
        ),
        _event(
            2,
            "evt_ticket_resume_created",
            EVENT_TICKET_CREATED,
            _ticket_event_payload(
                "tkt_ticket_resume_done",
                "node_ticket_resume_done",
                status_detail={
                    "input_artifact_refs": ["art://input/spec.md"],
                    "input_process_asset_refs": ["prd://resume-ticket@1"],
                    "retry_budget": 2,
                },
            ),
        ),
        _event(
            3,
            "evt_ticket_resume_completed",
            EVENT_TICKET_COMPLETED,
            _ticket_event_payload(
                "tkt_ticket_resume_done",
                "node_ticket_resume_done",
                status_detail={
                    "artifact_refs": ["art://runtime/tkt_ticket_resume_done/source-code.tsx"],
                    "verification_evidence_refs": ["evidence://pytest/ticket-resume"],
                    "produced_process_assets": [
                        {
                            "process_asset_ref": "SOURCE_CODE_DELIVERY:scd_tkt_ticket_resume_done@1",
                            "canonical_ref": "SOURCE_CODE_DELIVERY:scd_tkt_ticket_resume_done@1",
                            "process_asset_kind": "SOURCE_CODE_DELIVERY",
                            "workflow_id": "wf_replay",
                            "producer_ticket_id": "tkt_ticket_resume_done",
                            "producer_node_id": "node_ticket_resume_done",
                            "graph_version": "gv_3",
                            "content_hash": "sha256:ticket-resume-source",
                            "visibility_status": "CONSUMABLE",
                            "summary": "Ticket resume source delivery",
                        }
                    ],
                },
            ),
        ),
    ]


def _ticket_resume_in_flight_events() -> list[dict]:
    return [
        _event(
            1,
            "evt_ticket_inflight_wf",
            EVENT_WORKFLOW_CREATED,
            _workflow_event_payload("Ticket resume in flight"),
        ),
        _event(
            2,
            "evt_ticket_inflight_created",
            EVENT_TICKET_CREATED,
            _ticket_event_payload(
                "tkt_ticket_resume_inflight",
                "node_ticket_resume_inflight",
                status_detail={"retry_budget": 2},
            ),
        ),
        _event(
            3,
            "evt_ticket_inflight_assigned",
            EVENT_TICKET_ASSIGNED,
            {
                "workflow_id": "wf_replay",
                "ticket_id": "tkt_ticket_resume_inflight",
                "node_id": "node_ticket_resume_inflight",
                "assignment_id": "asg_ticket_resume_inflight",
                "actor_id": "emp_resume_worker",
                "required_capabilities": ["frontend_engineering"],
                "assignment_reason": "resume fixture assignment",
                "provider_selection": {"provider_id": "prov_openai_compat"},
            },
        ),
        _event(
            4,
            "evt_ticket_inflight_lease",
            EVENT_TICKET_LEASE_GRANTED,
            {
                "workflow_id": "wf_replay",
                "ticket_id": "tkt_ticket_resume_inflight",
                "node_id": "node_ticket_resume_inflight",
                "assignment_id": "asg_ticket_resume_inflight",
                "lease_id": "lease_ticket_resume_inflight",
                "actor_id": "emp_resume_worker",
                "lease_timeout_sec": 600,
                "lease_expires_at": "2026-05-04T10:24:00+08:00",
            },
        ),
        _event(
            5,
            "evt_ticket_inflight_started",
            EVENT_TICKET_STARTED,
            {
                "workflow_id": "wf_replay",
                "ticket_id": "tkt_ticket_resume_inflight",
                "node_id": "node_ticket_resume_inflight",
                "started_by": "emp_resume_worker",
                "actor_id": "emp_resume_worker",
                "assignment_id": "asg_ticket_resume_inflight",
                "lease_id": "lease_ticket_resume_inflight",
            },
        ),
    ]


def _incident_resume_events() -> list[dict]:
    return [
        _event(
            1,
            "evt_incident_resume_wf",
            EVENT_WORKFLOW_CREATED,
            _workflow_event_payload("Incident resume"),
        ),
        _event(
            2,
            "evt_incident_source_created",
            EVENT_TICKET_CREATED,
            _ticket_event_payload(
                "tkt_incident_resume_source",
                "node_incident_resume_source",
                status_detail={"retry_budget": 2},
            ),
        ),
        _event(
            3,
            "evt_incident_source_failed",
            EVENT_TICKET_FAILED,
            _ticket_event_payload(
                "tkt_incident_resume_source",
                "node_incident_resume_source",
                status_detail={
                    "failure_kind": "RUNTIME_ERROR",
                    "failure_message": "resume fixture failure",
                    "failure_fingerprint": "fp:incident-resume-source",
                },
            ),
        ),
        _event(
            4,
            "evt_incident_opened",
            EVENT_INCIDENT_OPENED,
            {
                "incident_id": "inc_resume_failure",
                "ticket_id": "tkt_incident_resume_source",
                "node_id": "node_incident_resume_source",
                "incident_type": "REPEATED_FAILURE_ESCALATION",
                "status": "OPEN",
                "severity": "HIGH",
                "fingerprint": "incident:resume-failure",
                "latest_failure_kind": "RUNTIME_ERROR",
            },
        ),
        _event(
            5,
            "evt_incident_recovery_started",
            EVENT_INCIDENT_RECOVERY_STARTED,
            {
                "incident_id": "inc_resume_failure",
                "ticket_id": "tkt_incident_resume_source",
                "node_id": "node_incident_resume_source",
                "status": "RECOVERING",
                "followup_action": "RESTORE_AND_RETRY_LATEST_FAILURE",
                "followup_ticket_id": "tkt_incident_resume_followup",
                "recovery_action": {
                    "action_ref": "recovery:inc_resume_failure:retry-source",
                    "ticket_id": "tkt_incident_resume_source",
                    "target_ticket_id": "tkt_incident_resume_source",
                    "node_ref": "node_incident_resume_source",
                    "terminal_state": "FAILED",
                    "failure_kind": "RUNTIME_ERROR",
                    "retry_count": 0,
                    "retry_budget": 2,
                    "recommended_followup_action": "RESTORE_AND_RETRY_LATEST_FAILURE",
                },
            },
        ),
    ]


def test_resume_from_event_id_returns_explicit_watermark_boundary():
    request = build_replay_resume_request(
        resume_kind="event_id",
        event_cursor="evt_replay_002",
        projection_version=2,
    )

    result = resume_replay_from_event_id(_events(), request)

    assert result.status == "READY"
    assert result.event_cursor == "evt_replay_002"
    assert result.projection_version == 2
    assert result.event_range == {
        "start_sequence_no": 1,
        "end_sequence_no": 2,
    }
    assert result.schema_version == SCHEMA_VERSION
    assert result.contract_version == REPLAY_RESUME_CONTRACT_VERSION
    assert result.replay_watermark is not None
    assert result.replay_watermark.event_cursor == "evt_replay_002"
    assert result.replay_watermark.projection_version == 2
    assert result.replay_watermark.event_range == result.event_range
    assert result.replay_watermark.watermark_hash
    assert result.diagnostic == {
        "reason_code": "resume_ready",
        "message": "Replay resume point is ready.",
    }


def test_replay_watermark_is_stable_for_same_event_log_and_request():
    request = build_replay_resume_request(
        resume_kind="event_id",
        event_cursor="evt_replay_003",
        projection_version=3,
    )

    first = resume_replay_from_event_id(_events(), request)
    second = resume_replay_from_event_id(_events(), request)

    assert first.status == "READY"
    assert second.status == "READY"
    assert first.replay_watermark == second.replay_watermark
    assert first.replay_watermark is not None
    assert first.replay_watermark.watermark_hash == second.replay_watermark.watermark_hash


def test_resume_fails_closed_when_event_cursor_is_missing():
    request = build_replay_resume_request(
        resume_kind="event_id",
        event_cursor=None,
        projection_version=2,
    )

    result = resume_replay_from_event_id(_events(), request)

    assert result.status == "FAILED"
    assert result.replay_watermark is None
    assert result.diagnostic["reason_code"] == "missing_event_cursor"


def test_resume_fails_closed_when_event_cursor_is_out_of_range():
    request = build_replay_resume_request(
        resume_kind="event_id",
        event_cursor="evt_missing",
        projection_version=2,
    )

    result = resume_replay_from_event_id(_events(), request)

    assert result.status == "FAILED"
    assert result.replay_watermark is None
    assert result.diagnostic["reason_code"] == "event_cursor_out_of_range"


def test_resume_fails_closed_when_projection_version_mismatches_event_cursor():
    request = build_replay_resume_request(
        resume_kind="event_id",
        event_cursor="evt_replay_002",
        projection_version=3,
    )

    result = resume_replay_from_event_id(_events(), request)

    assert result.status == "FAILED"
    assert result.replay_watermark is None
    assert result.diagnostic["reason_code"] == "projection_version_mismatch"
    assert result.diagnostic["expected_projection_version"] == 2
    assert result.diagnostic["actual_projection_version"] == 3


def test_resume_fails_closed_when_event_range_is_not_contiguous():
    request = build_replay_resume_request(
        resume_kind="event_id",
        event_cursor="evt_replay_003",
        projection_version=3,
    )
    events = [
        _events()[0],
        _event(
            3,
            "evt_replay_003",
            EVENT_TICKET_CREATED,
            {
                "ticket_id": "tkt_replay_check",
                "node_id": "node_replay_check",
                "retry_budget": 1,
                "timeout_sla_sec": 1800,
                "priority": "normal",
            },
        ),
    ]

    result = resume_replay_from_event_id(events, request)

    assert result.status == "FAILED"
    assert result.replay_watermark is None
    assert result.diagnostic["reason_code"] == "event_range_not_contiguous"
    assert result.diagnostic["missing_sequence_no"] == 2


def test_resume_fails_closed_when_event_range_does_not_start_at_first_event():
    request = build_replay_resume_request(
        resume_kind="event_id",
        event_cursor="evt_replay_003",
        projection_version=3,
    )
    events = [
        _event(
            2,
            "evt_replay_002",
            EVENT_TICKET_CREATED,
            {
                "ticket_id": "tkt_replay",
                "node_id": "node_replay",
                "retry_budget": 1,
                "timeout_sla_sec": 1800,
                "priority": "high",
            },
        ),
        _events()[2],
    ]

    result = resume_replay_from_event_id(events, request)

    assert result.status == "FAILED"
    assert result.replay_watermark is None
    assert result.diagnostic["reason_code"] == "event_range_not_contiguous"
    assert result.diagnostic["missing_sequence_no"] == 1


def test_resume_from_graph_version_returns_watermark_and_projection_summary():
    request = build_replay_resume_request(
        resume_kind="graph_version",
        event_cursor=None,
        projection_version=5,
        graph_version="gv_5",
        expected_graph_patch_hash="hash-graph-version-resume",
    )

    result = resume_replay_from_graph_version(_graph_equivalence_events(), request)
    expected_request = build_replay_resume_request(
        resume_kind="graph_version",
        event_cursor="evt_graph_patch",
        projection_version=5,
        graph_version="gv_5",
        expected_graph_patch_hash="hash-graph-version-resume",
        event_range={
            "start_sequence_no": 1,
            "end_sequence_no": 5,
        },
    )

    assert result.status == "READY"
    assert result.resume_request == expected_request
    assert result.event_cursor == "evt_graph_patch"
    assert result.projection_version == 5
    assert result.event_range == {
        "start_sequence_no": 1,
        "end_sequence_no": 5,
    }
    assert result.replay_watermark is not None
    assert result.replay_watermark.resume_kind == "graph_version"
    assert result.replay_watermark.event_cursor == "evt_graph_patch"
    assert result.replay_watermark.event_range == result.event_range
    assert result.replay_watermark.request_hash == expected_request.request_hash
    assert result.projection_summary is not None
    assert result.projection_summary["graph_version"] == "gv_5"
    assert result.projection_summary["current_ticket_ids_by_node_ref"]["node_graph_new"] == "tkt_graph_new"
    assert "tkt_graph_old" not in result.projection_summary["ready_ticket_ids"]
    assert "node_graph_old" not in result.projection_summary["effective_node_refs"]
    assert all(
        edge["target_node_ref"] != "node_graph_old"
        for edge in result.projection_summary["effective_edges"]
    )
    assert result.diagnostic["reason_code"] == "resume_ready"


def test_resume_from_ticket_id_returns_watermark_runtime_assignment_lease_and_refs():
    request = build_replay_resume_request(
        resume_kind="ticket_id",
        event_cursor=None,
        projection_version=5,
        ticket_id="tkt_ticket_resume_inflight",
    )

    result = resume_replay_from_ticket_id(_ticket_resume_in_flight_events(), request)

    assert result.status == "READY"
    assert result.event_cursor == "evt_ticket_inflight_started"
    assert result.projection_version == 5
    assert result.replay_watermark is not None
    assert result.replay_watermark.resume_kind == "ticket_id"
    assert result.replay_watermark.event_range == {
        "start_sequence_no": 1,
        "end_sequence_no": 5,
    }
    assert result.projection_summary is not None
    ticket_context = result.projection_summary["ticket_context"]
    assert ticket_context["ticket_id"] == "tkt_ticket_resume_inflight"
    assert ticket_context["status"] == "EXECUTING"
    assert ticket_context["is_in_flight"] is True
    assert ticket_context["is_terminal"] is False
    assert ticket_context["runtime_node_view"] == {
        "node_id": "node_ticket_resume_inflight",
        "graph_node_id": "node_ticket_resume_inflight",
        "runtime_node_id": "node_ticket_resume_inflight",
        "ticket_id": "tkt_ticket_resume_inflight",
        "is_placeholder": False,
        "materialization_state": "materialized",
        "placeholder_status": None,
        "reason_code": None,
        "open_incident_id": None,
        "materialization_hint": None,
    }
    assert ticket_context["assignment"]["assignment_id"] == "asg_ticket_resume_inflight"
    assert ticket_context["assignment"]["actor_id"] == "emp_resume_worker"
    assert ticket_context["lease"]["lease_id"] == "lease_ticket_resume_inflight"
    assert ticket_context["lease"]["status"] == "EXECUTING"
    assert result.projection_summary["current_ticket_ids_by_node_ref"] == {
        "node_ticket_resume_inflight": "tkt_ticket_resume_inflight",
    }


def test_resume_from_ticket_id_preserves_terminal_state_and_related_refs():
    request = build_replay_resume_request(
        resume_kind="ticket_id",
        event_cursor=None,
        projection_version=3,
        ticket_id="tkt_ticket_resume_done",
    )

    result = resume_replay_from_ticket_id(_ticket_resume_terminal_events(), request)

    assert result.status == "READY"
    assert result.projection_summary is not None
    ticket_context = result.projection_summary["ticket_context"]
    assert ticket_context["status"] == "COMPLETED"
    assert ticket_context["terminal_state"] == "COMPLETED"
    assert ticket_context["is_terminal"] is True
    assert ticket_context["is_in_flight"] is False
    assert ticket_context["related_artifact_refs"] == [
        "art://input/spec.md",
        "art://runtime/tkt_ticket_resume_done/source-code.tsx",
    ]
    assert ticket_context["related_evidence_refs"] == ["evidence://pytest/ticket-resume"]
    assert ticket_context["related_process_asset_refs"] == [
        "SOURCE_CODE_DELIVERY:scd_tkt_ticket_resume_done@1",
        "prd://resume-ticket@1",
    ]


def test_resume_from_incident_id_preserves_source_ticket_followup_and_recovery_lineage():
    request = build_replay_resume_request(
        resume_kind="incident_id",
        event_cursor=None,
        projection_version=5,
        incident_id="inc_resume_failure",
        ticket_id="tkt_incident_resume_source",
    )

    result = resume_replay_from_incident_id(_incident_resume_events(), request)

    assert result.status == "READY"
    assert result.event_cursor == "evt_incident_recovery_started"
    assert result.replay_watermark is not None
    assert result.replay_watermark.resume_kind == "incident_id"
    assert result.projection_summary is not None
    incident_context = result.projection_summary["incident_context"]
    assert incident_context["incident_id"] == "inc_resume_failure"
    assert incident_context["status"] == "RECOVERING"
    assert incident_context["source_ticket_context"]["ticket_id"] == "tkt_incident_resume_source"
    assert incident_context["source_ticket_context"]["status"] == "FAILED"
    assert incident_context["followup_action"] == "RESTORE_AND_RETRY_LATEST_FAILURE"
    assert incident_context["recommended_followup_action"] == "RESTORE_AND_RETRY_LATEST_FAILURE"
    assert incident_context["recovery_action_lineage"] == [
        {
            "action_ref": "recovery:inc_resume_failure:retry-source",
            "ticket_id": "tkt_incident_resume_source",
            "target_ticket_id": "tkt_incident_resume_source",
            "node_ref": "node_incident_resume_source",
            "terminal_state": "FAILED",
            "failure_kind": "RUNTIME_ERROR",
            "retry_count": 0,
            "retry_budget": 2,
            "recommended_followup_action": "RESTORE_AND_RETRY_LATEST_FAILURE",
        }
    ]
    assert incident_context["rework_restore_policy_input"] == {
        "actions": incident_context["recovery_action_lineage"],
    }
    assert [event["event_type"] for event in incident_context["incident_event_lineage"]] == [
        "INCIDENT_OPENED",
        "INCIDENT_RECOVERY_STARTED",
    ]
    assert result.projection_summary["current_ticket_ids_by_node_ref"] == {
        "node_incident_resume_source": "tkt_incident_resume_source",
    }


def test_ticket_id_resume_fails_closed_when_ticket_is_missing():
    request = build_replay_resume_request(
        resume_kind="ticket_id",
        event_cursor=None,
        projection_version=3,
        ticket_id="tkt_missing_resume",
    )

    result = resume_replay_from_ticket_id(_ticket_resume_terminal_events(), request)

    assert result.status == "FAILED"
    assert result.replay_watermark is None
    assert result.projection_summary is None
    assert result.diagnostic["reason_code"] == "ticket_resume_ticket_missing"


def test_incident_id_resume_fails_closed_when_incident_is_missing():
    request = build_replay_resume_request(
        resume_kind="incident_id",
        event_cursor=None,
        projection_version=5,
        incident_id="inc_missing_resume",
    )

    result = resume_replay_from_incident_id(_incident_resume_events(), request)

    assert result.status == "FAILED"
    assert result.replay_watermark is None
    assert result.projection_summary is None
    assert result.diagnostic["reason_code"] == "incident_resume_incident_missing"


def test_incident_id_resume_fails_closed_when_pinned_source_ticket_mismatches():
    request = build_replay_resume_request(
        resume_kind="incident_id",
        event_cursor=None,
        projection_version=5,
        incident_id="inc_resume_failure",
        ticket_id="tkt_wrong_source",
    )

    result = resume_replay_from_incident_id(_incident_resume_events(), request)

    assert result.status == "FAILED"
    assert result.replay_watermark is None
    assert result.projection_summary is None
    assert result.diagnostic["reason_code"] == "incident_source_ticket_mismatch"


def test_incident_id_resume_fails_closed_when_source_ticket_context_is_missing():
    events = [
        _event(
            1,
            "evt_incident_missing_source_wf",
            EVENT_WORKFLOW_CREATED,
            _workflow_event_payload("Incident missing source"),
        ),
        _event(
            2,
            "evt_incident_missing_source_opened",
            EVENT_INCIDENT_OPENED,
            {
                "incident_id": "inc_missing_source",
                "ticket_id": "tkt_missing_source",
                "node_id": "node_missing_source",
                "incident_type": "REPEATED_FAILURE_ESCALATION",
                "status": "OPEN",
                "severity": "HIGH",
                "fingerprint": "incident:missing-source",
            },
        ),
    ]
    request = build_replay_resume_request(
        resume_kind="incident_id",
        event_cursor=None,
        projection_version=2,
        incident_id="inc_missing_source",
    )

    result = resume_replay_from_incident_id(events, request)

    assert result.status == "FAILED"
    assert result.replay_watermark is None
    assert result.projection_summary is None
    assert result.diagnostic["reason_code"] == "incident_source_ticket_missing"


def test_ticket_id_resume_fails_closed_when_runtime_node_view_is_broken(monkeypatch):
    import app.core.replay_resume as replay_resume_module
    from app.core.runtime_node_views import RuntimeNodeViewResolutionError

    def _raise_broken_runtime_node_view(*args, **kwargs):
        raise RuntimeNodeViewResolutionError("runtime node view fixture break")

    monkeypatch.setattr(
        replay_resume_module,
        "build_runtime_graph_node_views",
        _raise_broken_runtime_node_view,
    )
    request = build_replay_resume_request(
        resume_kind="ticket_id",
        event_cursor=None,
        projection_version=5,
        ticket_id="tkt_ticket_resume_inflight",
    )

    result = resume_replay_from_ticket_id(_ticket_resume_in_flight_events(), request)

    assert result.status == "FAILED"
    assert result.replay_watermark is None
    assert result.projection_summary is None
    assert result.diagnostic["reason_code"] == "runtime_node_view_broken"


def test_graph_version_resume_matches_full_replay_projection_summary():
    events = _graph_equivalence_events()
    resumed_request = build_replay_resume_request(
        resume_kind="graph_version",
        event_cursor=None,
        projection_version=5,
        graph_version="gv_5",
    )

    full_summary = _projection_summary_from_full_replay(events, workflow_id="wf_replay")
    resumed = resume_replay_from_graph_version(events, resumed_request)

    assert resumed.status == "READY"
    assert resumed.projection_summary == full_summary


def test_graph_version_resume_keeps_late_old_attempt_out_of_current_pointer():
    request = build_replay_resume_request(
        resume_kind="graph_version",
        event_cursor=None,
        projection_version=6,
        graph_version="gv_6",
    )

    result = resume_replay_from_graph_version(_graph_equivalence_events_with_late_old_complete(), request)

    assert result.status == "READY"
    assert result.projection_summary is not None
    assert result.projection_summary["graph_version"] == "gv_6"
    assert result.projection_summary["current_ticket_ids_by_node_ref"] == {
        "node_graph_new": "tkt_graph_new",
        "node_graph_parent": "tkt_graph_parent",
    }
    assert "tkt_graph_old" not in result.projection_summary["completed_ticket_ids"]
    assert "node_graph_old" not in result.projection_summary["effective_node_refs"]


def test_graph_version_resume_keeps_late_old_cancelled_out_of_patch_legality():
    request = build_replay_resume_request(
        resume_kind="graph_version",
        event_cursor=None,
        projection_version=6,
        graph_version="gv_6",
    )

    result = resume_replay_from_graph_version(_graph_equivalence_events_with_late_old_cancelled(), request)

    assert result.status == "READY"
    assert result.projection_summary is not None
    assert result.projection_summary["current_ticket_ids_by_node_ref"]["node_graph_new"] == "tkt_graph_new"
    assert "node_graph_old" not in result.projection_summary["effective_node_refs"]


def test_graph_version_resume_preserves_orphan_pending_and_effective_edge_semantics():
    request = build_replay_resume_request(
        resume_kind="graph_version",
        event_cursor=None,
        projection_version=5,
        graph_version="gv_5",
    )

    result = resume_replay_from_graph_version(_orphan_pending_events(), request)

    assert result.status == "READY"
    assert result.projection_summary is not None
    assert result.projection_summary["graph_complete"] is True
    assert result.projection_summary["completed_ticket_ids"] == ["tkt_orphan_delivery"]
    assert "tkt_orphan_stale" not in result.projection_summary["ready_ticket_ids"]
    assert "node_orphan_stale" not in result.projection_summary["effective_node_refs"]
    assert result.projection_summary["effective_edges"] == []


def test_graph_version_resume_fails_closed_when_graph_version_missing():
    request = build_replay_resume_request(
        resume_kind="graph_version",
        event_cursor=None,
        projection_version=2,
        graph_version=None,
    )

    result = resume_replay_from_graph_version(_events(), request)

    assert result.status == "FAILED"
    assert result.replay_watermark is None
    assert result.projection_summary is None
    assert result.diagnostic["reason_code"] == "missing_graph_version"


def test_graph_version_resume_fails_closed_when_graph_version_is_gap():
    request = build_replay_resume_request(
        resume_kind="graph_version",
        event_cursor=None,
        projection_version=3,
        graph_version="gv_3",
    )
    events = [_events()[0], _events()[2]]

    result = resume_replay_from_graph_version(events, request)

    assert result.status == "FAILED"
    assert result.replay_watermark is None
    assert result.projection_summary is None
    assert result.diagnostic["reason_code"] == "event_range_not_contiguous"
    assert result.diagnostic["missing_sequence_no"] == 2


def test_graph_version_resume_fails_closed_when_request_event_range_mismatches():
    request = build_replay_resume_request(
        resume_kind="graph_version",
        event_cursor=None,
        projection_version=5,
        graph_version="gv_5",
        event_range={
            "start_sequence_no": 1,
            "end_sequence_no": 4,
        },
    )

    result = resume_replay_from_graph_version(_graph_equivalence_events(), request)

    assert result.status == "FAILED"
    assert result.replay_watermark is None
    assert result.projection_summary is None
    assert result.diagnostic["reason_code"] == "event_range_mismatch"
    assert result.diagnostic["expected_event_range"] == {
        "start_sequence_no": 1,
        "end_sequence_no": 5,
    }
    assert result.diagnostic["actual_event_range"] == {
        "start_sequence_no": 1,
        "end_sequence_no": 4,
    }


def test_graph_version_resume_fails_closed_when_graph_patch_hash_is_missing():
    events = _graph_equivalence_events()
    patch_event = dict(events[-1])
    patch_payload = _event_payload(patch_event)
    patch_payload.pop("patch_hash")
    patch_event["payload_json"] = json.dumps(patch_payload, sort_keys=True)
    events[-1] = patch_event
    request = build_replay_resume_request(
        resume_kind="graph_version",
        event_cursor=None,
        projection_version=5,
        graph_version="gv_5",
    )

    result = resume_replay_from_graph_version(events, request)

    assert result.status == "FAILED"
    assert result.replay_watermark is None
    assert result.projection_summary is None
    assert result.diagnostic["reason_code"] == "graph_patch_hash_missing"


def test_graph_version_resume_fails_closed_when_graph_patch_hash_mismatches():
    request = build_replay_resume_request(
        resume_kind="graph_version",
        event_cursor=None,
        projection_version=5,
        graph_version="gv_5",
        expected_graph_patch_hash="wrong-hash",
    )

    result = resume_replay_from_graph_version(_graph_equivalence_events(), request)

    assert result.status == "FAILED"
    assert result.replay_watermark is None
    assert result.projection_summary is None
    assert result.diagnostic["reason_code"] == "graph_patch_hash_mismatch"
    assert result.diagnostic["expected_graph_patch_hash"] == "wrong-hash"
    assert result.diagnostic["actual_graph_patch_hash"] == "hash-graph-version-resume"


def test_graph_version_resume_fails_closed_when_projection_rebuild_rejects_patch():
    events = _graph_equivalence_events()
    patch_event = dict(events[-1])
    patch_payload = _event_payload(patch_event)
    patch_payload["edge_additions"] = [
        {
            "edge_type": "PARENT_OF",
            "source_node_id": "node_graph_missing",
            "target_node_id": "node_graph_new",
        }
    ]
    patch_event["payload_json"] = json.dumps(patch_payload, sort_keys=True)
    events[-1] = patch_event
    request = build_replay_resume_request(
        resume_kind="graph_version",
        event_cursor=None,
        projection_version=5,
        graph_version="gv_5",
    )

    result = resume_replay_from_graph_version(events, request)

    assert result.status == "FAILED"
    assert result.replay_watermark is None
    assert result.projection_summary is None
    assert result.diagnostic["reason_code"] == "projection_rebuild_failed"
    assert result.diagnostic["error_type"]


def test_resume_normal_path_does_not_touch_projection_repair(monkeypatch, client):
    repository = client.app.state.repository
    called = {"refresh_projections": False}

    def _forbid_refresh_projections(*args, **kwargs):
        called["refresh_projections"] = True
        raise AssertionError("resume must not repair projection rows")

    monkeypatch.setattr(repository, "refresh_projections", _forbid_refresh_projections)
    request = build_replay_resume_request(
        resume_kind="event_id",
        event_cursor="evt_replay_002",
        projection_version=2,
    )

    result = resume_replay_from_event_id(_events(), request)

    assert result.status == "READY"
    assert called["refresh_projections"] is False
