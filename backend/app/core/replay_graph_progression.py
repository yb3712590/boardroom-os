from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from app.contracts.replay import ReplayCaseResult, ReplayImportManifest
from app.core.workflow_progression import (
    ProgressionPolicy,
    ProgressionSnapshot,
    decide_next_actions,
    evaluate_progression_graph,
)


ORPHAN_PENDING_CASE_ID = "graph-progression-015-orphan-pending-br060"
CANCELLED_SUPERSEDED_CASE_ID = "graph-progression-015-superseded-cancelled-br032"
LATE_PROVIDER_POINTER_CASE_ID = "graph-progression-015-late-provider-current-pointer-br041"
MISSING_EXPLICIT_POINTER_CASE_ID = "graph-progression-015-missing-explicit-pointer"
GRAPH_PROGRESSION_REPLAY_EVIDENCE_CLASSIFICATION = "graph progression replay evidence"
REPLAY_IMPORT_ISSUE_CLASSIFICATION = "replay/import issue"

WORKFLOW_ID = "wf_7f2902f3c8c6"
BR031_NODE_ID = "node_backlog_followup_br_031_m3_frontend_auth_nav"
BR032_NODE_ID = "node_backlog_followup_br_032_m3_checker_gate"
BR041_NODE_ID = "node_backlog_followup_br_041_m4_isbn_remove_inventory"
BR060_NODE_ID = "node_backlog_followup_br_060_m6_circulation_transactions"

_CASE_CONFIGS: dict[str, dict[str, Any]] = {
    ORPHAN_PENDING_CASE_ID: {
        "workflow_id": WORKFLOW_ID,
        "event_range": {"start_sequence_no": 11791, "end_sequence_no": 11903},
        "graph_version": "gv_11903",
        "node_id": BR060_NODE_ID,
        "current_ticket_id": "tkt_5d8e536a14c2",
        "review_ticket_id": "tkt_665d647e556a",
        "orphan_pending_ticket_id": "tkt_262f159fc931",
        "cancelled_ticket_ids": ["tkt_f5c2cd110a2f", "tkt_37d97847a282"],
    },
    CANCELLED_SUPERSEDED_CASE_ID: {
        "workflow_id": WORKFLOW_ID,
        "event_range": {"start_sequence_no": 5960, "end_sequence_no": 6299},
        "graph_version": "gv_6299",
        "cancelled_ticket_ids": [
            "tkt_ade5951f10ec",
            "tkt_2262491ff9ae",
            "tkt_e2b36aef19e9",
        ],
        "completed_tickets": {
            BR031_NODE_ID: "tkt_c247833b2c60",
            f"{BR031_NODE_ID}::review": "tkt_f00a95436db3",
            BR032_NODE_ID: "tkt_2e4ac9dd357e",
            f"{BR032_NODE_ID}::review": "tkt_1b2b27220047",
        },
    },
    LATE_PROVIDER_POINTER_CASE_ID: {
        "workflow_id": WORKFLOW_ID,
        "event_range": {"start_sequence_no": 9969, "end_sequence_no": 10016},
        "graph_version": "gv_10016",
        "node_id": BR041_NODE_ID,
        "old_ticket_id": "tkt_30c7a10979ae",
        "failure_ticket_id": "tkt_0c616378c9ac",
        "recovery_ticket_id": "tkt_2b58304dccb9",
    },
    MISSING_EXPLICIT_POINTER_CASE_ID: {
        "workflow_id": WORKFLOW_ID,
        "event_range": {"start_sequence_no": 11791, "end_sequence_no": 11903},
        "graph_version": "gv_11903",
        "node_id": BR060_NODE_ID,
        "candidate_ticket_ids": ["tkt_262f159fc931", "tkt_5d8e536a14c2"],
    },
}


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    return value


def _diagnostic(reason_code: str, message: str, **details: Any) -> dict[str, Any]:
    return {
        "reason_code": reason_code,
        "classification": details.pop("classification", GRAPH_PROGRESSION_REPLAY_EVIDENCE_CLASSIFICATION),
        "message": message,
        **_json_safe(details),
    }


def _empty_result(
    *,
    case_id: str,
    manifest: ReplayImportManifest | None,
    diagnostics: list[dict[str, Any]],
    event_range: dict[str, int] | None = None,
) -> ReplayCaseResult:
    return ReplayCaseResult(
        case_id=case_id,
        status="FAILED",
        source_manifest_hash=manifest.manifest_hash if manifest is not None else "",
        event_range=event_range,
        provider_failure_kind=None,
        attempt_refs=[],
        raw_archive_refs=[],
        source_ticket_context={},
        provider_provenance={},
        retry_recovery_outcome={
            "recovery_outcome": "not_evaluated",
            "raw_transcript_used": False,
            "late_output_body_used": False,
            "timestamp_pointer_guess_used": False,
        },
        late_event_guard={
            "guard_passed": True,
            "current_pointer_source": "not_provider_replay",
            "timestamp_pointer_guess_used": False,
        },
        diagnostics=diagnostics,
        issue_classification=REPLAY_IMPORT_ISSUE_CLASSIFICATION,
    )


def failed_graph_progression_case_result(
    *,
    case_id: str,
    diagnostics: list[dict[str, Any]],
    manifest: ReplayImportManifest | None = None,
) -> ReplayCaseResult:
    config = _CASE_CONFIGS.get(case_id)
    event_range = dict(config["event_range"]) if config is not None else None
    return _empty_result(
        case_id=case_id,
        manifest=manifest,
        diagnostics=diagnostics,
        event_range=event_range,
    )


def _connect_replay_db(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def _payload(row: sqlite3.Row | dict[str, Any] | None) -> dict[str, Any]:
    if row is None:
        return {}
    raw = row["payload_json"] if isinstance(row, sqlite3.Row) else row.get("payload_json")
    if not raw:
        return {}
    return json.loads(str(raw))


def _event_from_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "sequence_no": int(row["sequence_no"]),
        "event_id": str(row["event_id"]),
        "workflow_id": row["workflow_id"],
        "event_type": str(row["event_type"]),
        "occurred_at": str(row["occurred_at"]),
        "payload": _payload(row),
    }


def _fetch_events(
    connection: sqlite3.Connection,
    *,
    start_sequence_no: int,
    end_sequence_no: int,
) -> list[dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT sequence_no, event_id, workflow_id, event_type, occurred_at, payload_json
        FROM events
        WHERE sequence_no BETWEEN ? AND ?
        ORDER BY sequence_no ASC
        """,
        (start_sequence_no, end_sequence_no),
    ).fetchall()
    return [_event_from_row(row) for row in rows]


def _event_range(events: list[dict[str, Any]]) -> dict[str, int] | None:
    if not events:
        return None
    sequence_numbers = [int(event["sequence_no"]) for event in events]
    return {"start_sequence_no": min(sequence_numbers), "end_sequence_no": max(sequence_numbers)}


def _events_for_ticket(events: list[dict[str, Any]], ticket_id: str) -> list[dict[str, Any]]:
    return [event for event in events if str((event["payload"] or {}).get("ticket_id") or "") == ticket_id]


def _last_event(
    events: list[dict[str, Any]],
    *,
    event_type: str,
    ticket_id: str | None = None,
) -> dict[str, Any] | None:
    matches = [
        event
        for event in events
        if event["event_type"] == event_type
        and (ticket_id is None or str((event["payload"] or {}).get("ticket_id") or "") == ticket_id)
    ]
    return matches[-1] if matches else None


def _latest_ticket_terminal_event(
    connection: sqlite3.Connection,
    *,
    ticket_id: str,
    max_sequence_no: int,
) -> dict[str, Any] | None:
    rows = connection.execute(
        """
        SELECT sequence_no, event_id, workflow_id, event_type, occurred_at, payload_json
        FROM events
        WHERE sequence_no <= ?
          AND event_type IN ('TICKET_FAILED', 'TICKET_COMPLETED', 'TICKET_CANCELLED', 'TICKET_TIMED_OUT')
          AND payload_json LIKE ?
        ORDER BY sequence_no DESC
        """,
        (max_sequence_no, f"%{ticket_id}%"),
    ).fetchall()
    for row in rows:
        event = _event_from_row(row)
        if str((event["payload"] or {}).get("ticket_id") or "") == ticket_id:
            return event
    return None


def _event_types_for_tickets(events: list[dict[str, Any]], ticket_ids: list[str]) -> dict[str, list[str]]:
    return {
        ticket_id: [str(event["event_type"]) for event in _events_for_ticket(events, ticket_id)]
        for ticket_id in ticket_ids
    }


def _graph_node(
    *,
    node_ref: str,
    ticket_id: str,
    status: str,
    node_id: str | None = None,
) -> dict[str, Any]:
    return {
        "node_ref": node_ref,
        "node_id": node_id or node_ref,
        "ticket_id": ticket_id,
        "ticket_status": status,
        "node_status": status,
    }


def _runtime_node(
    *,
    node_ref: str,
    ticket_id: str,
    status: str,
    node_id: str | None = None,
) -> dict[str, Any]:
    return {
        "node_ref": node_ref,
        "node_id": node_id or node_ref,
        "latest_ticket_id": ticket_id,
        "status": status,
    }


def _policy_ref(case_id: str) -> str:
    return f"replay-graph-progression:{case_id}:policy"


def _base_result_payload(config: dict[str, Any], events: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "case_id": config["case_id"],
        "event_range": dict(config["event_range"]),
        "provider_failure_kind": None,
        "attempt_refs": [],
        "raw_archive_refs": [],
        "source_ticket_context": {
            "workflow_id": config["workflow_id"],
            "case_id": config["case_id"],
        },
        "provider_provenance": {},
        "retry_recovery_outcome": {
            "recovery_outcome": "not_provider_failure",
            "raw_transcript_used": False,
            "late_output_body_used": False,
            "timestamp_pointer_guess_used": False,
        },
        "late_event_guard": {
            "guard_passed": True,
            "current_pointer_source": "structured_graph_replay",
            "timestamp_pointer_guess_used": False,
        },
    }


def _proposal_for_snapshot(
    *,
    snapshot: ProgressionSnapshot,
    case_id: str,
) -> dict[str, Any]:
    policy = ProgressionPolicy(policy_ref=_policy_ref(case_id))
    return decide_next_actions(snapshot, policy)[0].model_dump(mode="json")


def _summary_from_evaluation(
    *,
    graph_version: str,
    evaluation,
    late_event_guard: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "source_graph_version": graph_version,
        "current_ticket_ids_by_node_ref": evaluation.current_ticket_ids_by_node_ref,
        "effective_node_refs": evaluation.effective_node_refs,
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
        "graph_reduction_issue_count": len(evaluation.graph_reduction_issues),
        "timestamp_pointer_guess_used": False,
        **({"late_event_guard": late_event_guard} if late_event_guard is not None else {}),
    }


def _result_status_and_classification(
    diagnostics: list[dict[str, Any]],
) -> tuple[str, str]:
    import_issue_codes = {
        "manifest_not_ready",
        "replay_db_missing",
        "replay_db_invalid",
        "replay_case_unknown",
        "replay_case_events_missing",
        "case_expected_event_missing",
        "orphan_pending_not_ignored",
        "inactive_ticket_participated_in_effective_graph",
        "late_provider_pointer_violation",
        "missing_explicit_pointer_not_incident",
    }
    diagnostic_codes = {str(item.get("reason_code") or "") for item in diagnostics}
    if diagnostic_codes & import_issue_codes:
        return "FAILED", REPLAY_IMPORT_ISSUE_CLASSIFICATION
    return "READY", GRAPH_PROGRESSION_REPLAY_EVIDENCE_CLASSIFICATION


def _orphan_pending_result(
    *,
    manifest: ReplayImportManifest,
    config: dict[str, Any],
    events: list[dict[str, Any]],
    diagnostics: list[dict[str, Any]],
) -> ReplayCaseResult:
    node_id = str(config["node_id"])
    orphan_ticket_id = str(config["orphan_pending_ticket_id"])
    current_ticket_id = str(config["current_ticket_id"])
    review_ticket_id = str(config["review_ticket_id"])
    graph_version = str(config["graph_version"])
    snapshot = ProgressionSnapshot(
        workflow_id=str(config["workflow_id"]),
        graph_version=graph_version,
        graph_nodes=[
            _graph_node(node_ref=node_id, node_id=node_id, ticket_id=current_ticket_id, status="COMPLETED"),
            _graph_node(node_ref=node_id, node_id=node_id, ticket_id=orphan_ticket_id, status="PENDING"),
            _graph_node(
                node_ref=f"{node_id}::review",
                node_id=f"{node_id}::review",
                ticket_id=review_ticket_id,
                status="COMPLETED",
            ),
            *[
                _graph_node(node_ref=f"cancelled:{ticket_id}", ticket_id=ticket_id, status="CANCELLED")
                for ticket_id in list(config["cancelled_ticket_ids"])
            ],
        ],
        runtime_nodes=[
            _runtime_node(node_ref=node_id, node_id=node_id, ticket_id=current_ticket_id, status="COMPLETED"),
            _runtime_node(
                node_ref=f"{node_id}::review",
                node_id=f"{node_id}::review",
                ticket_id=review_ticket_id,
                status="COMPLETED",
            ),
        ],
        graph_edges=[
            {
                "edge_type": "REVIEWS",
                "source_node_ref": f"{node_id}::review",
                "target_node_ref": node_id,
                "source_ticket_id": review_ticket_id,
                "target_ticket_id": current_ticket_id,
            }
        ],
        cancelled_refs=list(config["cancelled_ticket_ids"]),
        stale_orphan_pending_refs=[orphan_ticket_id],
    )
    evaluation = evaluate_progression_graph(snapshot)
    proposal = _proposal_for_snapshot(snapshot=snapshot, case_id=str(config["case_id"]))
    if not evaluation.graph_complete or orphan_ticket_id in evaluation.ready_ticket_ids:
        diagnostics.append(
            _diagnostic(
                "orphan_pending_not_ignored",
                "Orphan pending ticket participated in effective graph readiness.",
                classification=REPLAY_IMPORT_ISSUE_CLASSIFICATION,
                orphan_ticket_id=orphan_ticket_id,
            )
        )
    else:
        diagnostics.append(
            _diagnostic(
                "orphan_pending_ignored",
                "Orphan pending ticket stayed outside the effective graph complete decision.",
                orphan_ticket_id=orphan_ticket_id,
            )
        )
    status, classification = _result_status_and_classification(diagnostics)
    payload = _base_result_payload(config, events)
    return ReplayCaseResult(
        **payload,
        status=status,  # type: ignore[arg-type]
        source_manifest_hash=manifest.manifest_hash,
        graph_pointer_summary=_summary_from_evaluation(graph_version=graph_version, evaluation=evaluation),
        policy_proposal=proposal,
        graph_diagnostics=list(evaluation.graph_reduction_issues),
        effective_edge_summary={
            "effective_edges": evaluation.effective_edges,
            "effective_edge_count": len(evaluation.effective_edges),
            "excluded_orphan_pending_refs": [orphan_ticket_id],
            "excluded_inactive_ticket_refs": list(config["cancelled_ticket_ids"]),
        },
        diagnostics=diagnostics,
        issue_classification=classification,
    )


def _cancelled_superseded_result(
    *,
    manifest: ReplayImportManifest,
    config: dict[str, Any],
    events: list[dict[str, Any]],
    diagnostics: list[dict[str, Any]],
) -> ReplayCaseResult:
    graph_version = str(config["graph_version"])
    completed_tickets = dict(config["completed_tickets"])
    inactive_ticket_ids = sorted(str(ticket_id) for ticket_id in config["cancelled_ticket_ids"])
    snapshot = ProgressionSnapshot(
        workflow_id=str(config["workflow_id"]),
        graph_version=graph_version,
        graph_nodes=[
            *[
                _graph_node(node_ref=node_ref, node_id=node_ref, ticket_id=ticket_id, status="COMPLETED")
                for node_ref, ticket_id in completed_tickets.items()
            ],
            *[
                _graph_node(
                    node_ref=f"inactive:{ticket_id}",
                    node_id=f"inactive:{ticket_id}",
                    ticket_id=ticket_id,
                    status="CANCELLED",
                )
                for ticket_id in inactive_ticket_ids
            ],
        ],
        runtime_nodes=[
            *[
                _runtime_node(node_ref=node_ref, node_id=node_ref, ticket_id=ticket_id, status="COMPLETED")
                for node_ref, ticket_id in completed_tickets.items()
            ],
        ],
        graph_edges=[
            {
                "edge_type": "REVIEWS",
                "source_node_ref": f"{BR031_NODE_ID}::review",
                "target_node_ref": BR031_NODE_ID,
                "source_ticket_id": "tkt_f00a95436db3",
                "target_ticket_id": "tkt_c247833b2c60",
            },
            {
                "edge_type": "REVIEWS",
                "source_node_ref": f"{BR032_NODE_ID}::review",
                "target_node_ref": BR032_NODE_ID,
                "source_ticket_id": "tkt_1b2b27220047",
                "target_ticket_id": "tkt_2e4ac9dd357e",
            },
            {
                "edge_type": "PARENT_OF",
                "source_node_ref": BR032_NODE_ID,
                "target_node_ref": BR032_NODE_ID,
                "source_ticket_id": "tkt_ade5951f10ec",
                "target_ticket_id": "tkt_e2b36aef19e9",
            },
        ],
        cancelled_refs=inactive_ticket_ids,
        superseded_refs=inactive_ticket_ids,
    )
    evaluation = evaluate_progression_graph(snapshot)
    proposal = _proposal_for_snapshot(snapshot=snapshot, case_id=str(config["case_id"]))
    effective_ticket_refs = {
        str(edge.get("source_ticket_id") or "")
        for edge in evaluation.effective_edges
    } | {
        str(edge.get("target_ticket_id") or "")
        for edge in evaluation.effective_edges
    } | set(evaluation.ready_ticket_ids) | set(evaluation.completed_ticket_ids)
    if set(inactive_ticket_ids) & effective_ticket_refs or not evaluation.graph_complete:
        diagnostics.append(
            _diagnostic(
                "inactive_ticket_participated_in_effective_graph",
                "Cancelled or superseded ticket participated in effective graph progression.",
                classification=REPLAY_IMPORT_ISSUE_CLASSIFICATION,
                inactive_ticket_ids=inactive_ticket_ids,
            )
        )
    else:
        diagnostics.append(
            _diagnostic(
                "cancelled_superseded_edges_excluded",
                "Cancelled and superseded ticket refs stayed outside effective edges and readiness.",
                inactive_ticket_ids=inactive_ticket_ids,
            )
        )
    status, classification = _result_status_and_classification(diagnostics)
    payload = _base_result_payload(config, events)
    return ReplayCaseResult(
        **payload,
        status=status,  # type: ignore[arg-type]
        source_manifest_hash=manifest.manifest_hash,
        graph_pointer_summary=_summary_from_evaluation(graph_version=graph_version, evaluation=evaluation),
        policy_proposal=proposal,
        graph_diagnostics=list(evaluation.graph_reduction_issues),
        effective_edge_summary={
            "effective_edges": evaluation.effective_edges,
            "effective_edge_count": len(evaluation.effective_edges),
            "excluded_inactive_ticket_refs": inactive_ticket_ids,
        },
        diagnostics=diagnostics,
        issue_classification=classification,
    )


def _late_event_guard(
    connection: sqlite3.Connection,
    events: list[dict[str, Any]],
    config: dict[str, Any],
) -> dict[str, Any]:
    old_ticket_id = str(config["old_ticket_id"])
    recovery_ticket_id = str(config["recovery_ticket_id"])
    old_terminal = _last_event(events, event_type="TICKET_FAILED", ticket_id=old_ticket_id)
    if old_terminal is None:
        old_terminal = _latest_ticket_terminal_event(
            connection,
            ticket_id=old_ticket_id,
            max_sequence_no=int(config["event_range"]["end_sequence_no"]),
        )
    old_terminal_sequence = old_terminal.get("sequence_no") if old_terminal else None
    late_provider_events = [
        {
            "sequence_no": event["sequence_no"],
            "event_type": event["event_type"],
            "attempt_id": event["payload"].get("attempt_id"),
        }
        for event in _events_for_ticket(events, old_ticket_id)
        if old_terminal_sequence is not None
        and event["sequence_no"] > old_terminal_sequence
        and str(event["event_type"]).startswith("PROVIDER_")
    ]
    recovery_completed = _last_event(events, event_type="TICKET_COMPLETED", ticket_id=recovery_ticket_id)
    current_pointer_ticket_id = recovery_ticket_id if recovery_completed is not None else None
    return {
        "guard_passed": current_pointer_ticket_id == recovery_ticket_id,
        "old_ticket_id": old_ticket_id,
        "old_terminal_sequence_no": old_terminal_sequence,
        "late_provider_events": late_provider_events,
        "current_pointer_ticket_id": current_pointer_ticket_id,
        "current_pointer_source": "case_range_terminal_events" if recovery_completed is not None else "missing_case_terminal_event",
        "expected_current_ticket_id": recovery_ticket_id,
        "recovery_completed_sequence_no": recovery_completed.get("sequence_no") if recovery_completed else None,
        "timestamp_pointer_guess_used": False,
    }


def _late_provider_result(
    *,
    manifest: ReplayImportManifest,
    connection: sqlite3.Connection,
    config: dict[str, Any],
    events: list[dict[str, Any]],
    diagnostics: list[dict[str, Any]],
) -> ReplayCaseResult:
    graph_version = str(config["graph_version"])
    node_id = str(config["node_id"])
    recovery_ticket_id = str(config["recovery_ticket_id"])
    late_guard = _late_event_guard(connection, events, config)
    snapshot = ProgressionSnapshot(
        workflow_id=str(config["workflow_id"]),
        graph_version=graph_version,
        graph_nodes=[
            _graph_node(node_ref=node_id, node_id=node_id, ticket_id=str(config["failure_ticket_id"]), status="FAILED"),
            _graph_node(node_ref=node_id, node_id=node_id, ticket_id=recovery_ticket_id, status="COMPLETED"),
        ],
        runtime_nodes=[
            _runtime_node(node_ref=node_id, node_id=node_id, ticket_id=recovery_ticket_id, status="COMPLETED"),
        ],
    )
    evaluation = evaluate_progression_graph(snapshot)
    proposal = _proposal_for_snapshot(snapshot=snapshot, case_id=str(config["case_id"]))
    if (
        late_guard.get("guard_passed") is not True
        or evaluation.current_ticket_ids_by_node_ref.get(node_id) != recovery_ticket_id
    ):
        diagnostics.append(
            _diagnostic(
                "late_provider_pointer_violation",
                "Late provider output appeared to change the current graph pointer.",
                classification=REPLAY_IMPORT_ISSUE_CLASSIFICATION,
                late_event_guard=late_guard,
            )
        )
    else:
        diagnostics.append(
            _diagnostic(
                "late_provider_output_ignored_for_current_pointer",
                "Late provider output stayed in old attempt lineage and did not change current pointer.",
                late_event_guard=late_guard,
            )
        )
    status, classification = _result_status_and_classification(diagnostics)
    payload = _base_result_payload(config, events)
    payload["retry_recovery_outcome"] = {
        "recovery_outcome": "retried_and_completed" if late_guard.get("guard_passed") else "not_recovered",
        "raw_transcript_used": False,
        "late_output_body_used": False,
        "timestamp_pointer_guess_used": False,
    }
    payload["late_event_guard"] = late_guard
    return ReplayCaseResult(
        **payload,
        status=status,  # type: ignore[arg-type]
        source_manifest_hash=manifest.manifest_hash,
        graph_pointer_summary=_summary_from_evaluation(
            graph_version=graph_version,
            evaluation=evaluation,
            late_event_guard=late_guard,
        ),
        policy_proposal=proposal,
        graph_diagnostics=list(evaluation.graph_reduction_issues),
        effective_edge_summary={
            "effective_edges": evaluation.effective_edges,
            "effective_edge_count": len(evaluation.effective_edges),
        },
        diagnostics=diagnostics,
        issue_classification=classification,
    )


def _missing_pointer_result(
    *,
    manifest: ReplayImportManifest,
    config: dict[str, Any],
    events: list[dict[str, Any]],
    diagnostics: list[dict[str, Any]],
) -> ReplayCaseResult:
    graph_version = str(config["graph_version"])
    node_id = str(config["node_id"])
    candidate_ticket_ids = [str(ticket_id) for ticket_id in config["candidate_ticket_ids"]]
    snapshot = ProgressionSnapshot(
        workflow_id=str(config["workflow_id"]),
        graph_version=graph_version,
        graph_nodes=[
            _graph_node(node_ref=node_id, node_id=node_id, ticket_id=ticket_id, status="PENDING")
            for ticket_id in candidate_ticket_ids
        ],
    )
    evaluation = evaluate_progression_graph(snapshot)
    proposal = _proposal_for_snapshot(snapshot=snapshot, case_id=str(config["case_id"]))
    issue_codes = {str(issue.get("issue_code") or "") for issue in evaluation.graph_reduction_issues}
    if (
        "graph.current_pointer.missing_explicit" not in issue_codes
        or proposal.get("action_type") != "INCIDENT"
    ):
        diagnostics.append(
            _diagnostic(
                "missing_explicit_pointer_not_incident",
                "Missing explicit current pointer did not produce a graph reduction incident.",
                classification=REPLAY_IMPORT_ISSUE_CLASSIFICATION,
                graph_reduction_issues=evaluation.graph_reduction_issues,
            )
        )
    else:
        diagnostics.append(
            _diagnostic(
                "missing_explicit_pointer_incident",
                "Missing explicit current pointer produced graph reduction incident without timestamp guessing.",
                candidate_ticket_ids=candidate_ticket_ids,
            )
        )
    status, classification = _result_status_and_classification(diagnostics)
    payload = _base_result_payload(config, events)
    return ReplayCaseResult(
        **payload,
        status=status,  # type: ignore[arg-type]
        source_manifest_hash=manifest.manifest_hash,
        graph_pointer_summary=_summary_from_evaluation(graph_version=graph_version, evaluation=evaluation),
        policy_proposal=proposal,
        graph_diagnostics=list(evaluation.graph_reduction_issues),
        effective_edge_summary={
            "effective_edges": evaluation.effective_edges,
            "effective_edge_count": len(evaluation.effective_edges),
        },
        diagnostics=diagnostics,
        issue_classification=classification,
    )


def _validate_expected_events(
    *,
    config: dict[str, Any],
    events: list[dict[str, Any]],
    diagnostics: list[dict[str, Any]],
) -> None:
    if config["case_id"] == ORPHAN_PENDING_CASE_ID:
        expected = [str(config["orphan_pending_ticket_id"]), str(config["current_ticket_id"]), str(config["review_ticket_id"])]
    elif config["case_id"] == CANCELLED_SUPERSEDED_CASE_ID:
        expected = list(config["cancelled_ticket_ids"]) + list(dict(config["completed_tickets"]).values())
    elif config["case_id"] == LATE_PROVIDER_POINTER_CASE_ID:
        expected = [str(config["failure_ticket_id"]), str(config["recovery_ticket_id"])]
    else:
        expected = list(config["candidate_ticket_ids"])
    event_types = _event_types_for_tickets(events, expected)
    missing = [ticket_id for ticket_id, types in event_types.items() if not types]
    if missing:
        diagnostics.append(
            _diagnostic(
                "case_expected_event_missing",
                "Replay graph progression case cannot find expected ticket events.",
                classification=REPLAY_IMPORT_ISSUE_CLASSIFICATION,
                missing_ticket_ids=missing,
            )
        )


def replay_graph_progression_case(
    *,
    manifest: ReplayImportManifest,
    replay_db_path: str | Path,
    case_id: str,
) -> ReplayCaseResult:
    config = _CASE_CONFIGS.get(case_id)
    if config is None:
        return _empty_result(
            case_id=case_id,
            manifest=manifest,
            diagnostics=[
                _diagnostic(
                    "replay_case_unknown",
                    "Replay graph progression case id is not registered.",
                    classification=REPLAY_IMPORT_ISSUE_CLASSIFICATION,
                    case_id=case_id,
                )
            ],
        )
    diagnostics: list[dict[str, Any]] = []
    if manifest.status != "READY":
        diagnostics.append(
            _diagnostic(
                "manifest_not_ready",
                "Replay graph progression requires a READY ReplayImportManifest.",
                classification=REPLAY_IMPORT_ISSUE_CLASSIFICATION,
                manifest_status=manifest.status,
            )
        )

    db_path = Path(replay_db_path)
    if not db_path.is_file():
        diagnostics.append(
            _diagnostic(
                "replay_db_missing",
                "Replay graph progression requires an imported replay DB.",
                classification=REPLAY_IMPORT_ISSUE_CLASSIFICATION,
                replay_db_path=str(db_path),
            )
        )
        return _empty_result(case_id=case_id, manifest=manifest, diagnostics=diagnostics, event_range=config["event_range"])

    try:
        connection = _connect_replay_db(db_path)
    except sqlite3.Error as exc:
        diagnostics.append(
            _diagnostic(
                "replay_db_invalid",
                "Replay graph progression DB cannot be opened read-only.",
                classification=REPLAY_IMPORT_ISSUE_CLASSIFICATION,
                error_type=type(exc).__name__,
                error_message=str(exc),
            )
        )
        return _empty_result(case_id=case_id, manifest=manifest, diagnostics=diagnostics, event_range=config["event_range"])

    with connection:
        events = _fetch_events(
            connection,
            start_sequence_no=int(config["event_range"]["start_sequence_no"]),
            end_sequence_no=int(config["event_range"]["end_sequence_no"]),
        )
        if not events:
            diagnostics.append(
                _diagnostic(
                    "replay_case_events_missing",
                    "Replay graph progression case range has no events.",
                    classification=REPLAY_IMPORT_ISSUE_CLASSIFICATION,
                    event_range=config["event_range"],
                )
            )
            return _empty_result(case_id=case_id, manifest=manifest, diagnostics=diagnostics, event_range=config["event_range"])

        config = {**config, "case_id": case_id}
        _validate_expected_events(config=config, events=events, diagnostics=diagnostics)
        if [item for item in diagnostics if item.get("classification") == REPLAY_IMPORT_ISSUE_CLASSIFICATION]:
            return _empty_result(case_id=case_id, manifest=manifest, diagnostics=diagnostics, event_range=config["event_range"])

        if case_id == ORPHAN_PENDING_CASE_ID:
            return _orphan_pending_result(
                manifest=manifest,
                config=config,
                events=events,
                diagnostics=diagnostics,
            )
        if case_id == CANCELLED_SUPERSEDED_CASE_ID:
            return _cancelled_superseded_result(
                manifest=manifest,
                config=config,
                events=events,
                diagnostics=diagnostics,
            )
        if case_id == LATE_PROVIDER_POINTER_CASE_ID:
            return _late_provider_result(
                manifest=manifest,
                connection=connection,
                config=config,
                events=events,
                diagnostics=diagnostics,
            )
        return _missing_pointer_result(
            manifest=manifest,
            config=config,
            events=events,
            diagnostics=diagnostics,
        )
