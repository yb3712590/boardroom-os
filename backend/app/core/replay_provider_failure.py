from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from app.contracts.replay import ReplayCaseResult, ReplayImportManifest

PROVIDER_FAILURE_CASE_ID = "provider-failure-015-malformed-sse"
PROVIDER_REPLAY_EVIDENCE_CLASSIFICATION = "provider replay evidence"
REPLAY_IMPORT_ISSUE_CLASSIFICATION = "replay/import issue"

_CASE_CONFIGS: dict[str, dict[str, Any]] = {
    PROVIDER_FAILURE_CASE_ID: {
        "workflow_id": "wf_7f2902f3c8c6",
        "node_id": "node_backlog_followup_br_041_m4_isbn_remove_inventory",
        "old_ticket_id": "tkt_30c7a10979ae",
        "failure_ticket_id": "tkt_0c616378c9ac",
        "recovery_ticket_id": "tkt_2b58304dccb9",
        "event_range": {"start_sequence_no": 9969, "end_sequence_no": 10016},
        "failure_sequence_no": 9996,
        "finished_sequence_no": 9995,
        "recovery_completed_sequence_no": 10016,
    }
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
        "classification": details.pop("classification", REPLAY_IMPORT_ISSUE_CLASSIFICATION),
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
            "guard_passed": False,
            "current_pointer_ticket_id": None,
        },
        diagnostics=diagnostics,
        issue_classification=REPLAY_IMPORT_ISSUE_CLASSIFICATION,
    )


def failed_provider_failure_case_result(
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
        "payload_json": row["payload_json"],
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
          AND event_type IN ('TICKET_FAILED', 'TICKET_COMPLETED', 'TICKET_CANCELLED')
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


def _event_range(events: list[dict[str, Any]]) -> dict[str, int] | None:
    if not events:
        return None
    sequence_numbers = [int(event["sequence_no"]) for event in events]
    return {"start_sequence_no": min(sequence_numbers), "end_sequence_no": max(sequence_numbers)}


def _events_for_ticket(events: list[dict[str, Any]], ticket_id: str) -> list[dict[str, Any]]:
    return [event for event in events if str((event["payload"] or {}).get("ticket_id") or "") == ticket_id]


def _first_event(
    events: list[dict[str, Any]],
    *,
    event_type: str,
    ticket_id: str | None = None,
) -> dict[str, Any] | None:
    for event in events:
        if event["event_type"] != event_type:
            continue
        if ticket_id is not None and str((event["payload"] or {}).get("ticket_id") or "") != ticket_id:
            continue
        return event
    return None


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


def _raw_archive_refs_from_payload(payload: dict[str, Any]) -> list[str]:
    refs: list[str] = []

    def _append(value: Any) -> None:
        normalized = str(value or "").strip()
        if normalized and normalized not in refs:
            refs.append(normalized)

    _append(payload.get("raw_archive_ref"))
    failure_detail = payload.get("failure_detail")
    if isinstance(failure_detail, dict):
        _append(failure_detail.get("raw_archive_ref"))
        for attempt in failure_detail.get("provider_attempt_log") or []:
            if isinstance(attempt, dict):
                _append(attempt.get("raw_archive_ref"))
    return refs


def _raw_archive_refs(events: list[dict[str, Any]], ticket_id: str) -> list[str]:
    refs: list[str] = []
    for event in _events_for_ticket(events, ticket_id):
        for ref in _raw_archive_refs_from_payload(event["payload"]):
            if ref not in refs:
                refs.append(ref)
    return refs


def _artifact_ref_exists(connection: sqlite3.Connection, artifact_ref: str) -> bool:
    try:
        row = connection.execute(
            "SELECT 1 FROM artifact_index WHERE artifact_ref = ? LIMIT 1",
            (artifact_ref,),
        ).fetchone()
    except sqlite3.Error:
        return False
    return row is not None


def _attempt_refs(events: list[dict[str, Any]], ticket_id: str) -> list[dict[str, Any]]:
    attempts: dict[str, dict[str, Any]] = {}
    for event in _events_for_ticket(events, ticket_id):
        if not str(event["event_type"]).startswith("PROVIDER_ATTEMPT"):
            continue
        payload = event["payload"]
        attempt_id = str(payload.get("attempt_id") or "").strip()
        if not attempt_id:
            continue
        record = attempts.setdefault(
            attempt_id,
            {
                "attempt_id": attempt_id,
                "ticket_id": ticket_id,
                "attempt_no": payload.get("attempt_no"),
                "provider_id": payload.get("provider_id"),
                "provider_policy_ref": payload.get("provider_policy_ref"),
                "event_sequence_nos": [],
                "terminal_state": None,
                "failure_kind": None,
            },
        )
        record["event_sequence_nos"].append(event["sequence_no"])
        if event["event_type"] in {"PROVIDER_ATTEMPT_FINISHED", "PROVIDER_ATTEMPT_TIMED_OUT"}:
            record["terminal_state"] = payload.get("state") or payload.get("status")
            record["failure_kind"] = payload.get("failure_kind")
    return sorted(attempts.values(), key=lambda item: str(item["attempt_id"]))


def _provider_provenance(ticket_failed_payload: dict[str, Any], provider_event_payload: dict[str, Any]) -> dict[str, Any]:
    detail = ticket_failed_payload.get("failure_detail")
    if not isinstance(detail, dict):
        detail = {}
    provider_id = detail.get("provider_id") or provider_event_payload.get("provider_id")
    actual_provider_id = detail.get("actual_provider_id") or provider_id
    preferred_provider_id = detail.get("preferred_provider_id") or actual_provider_id
    actual_model = detail.get("actual_model") or provider_event_payload.get("actual_model")
    preferred_model = detail.get("preferred_model") or actual_model
    return {
        "provider_id": provider_id,
        "actual_provider_id": actual_provider_id,
        "preferred_provider_id": preferred_provider_id,
        "actual_model": actual_model,
        "preferred_model": preferred_model,
        "adapter_kind": detail.get("adapter_kind") or provider_event_payload.get("adapter_kind"),
        "provider_candidate_chain": detail.get("provider_candidate_chain")
        or provider_event_payload.get("provider_candidate_chain")
        or [],
        "selection_reason": detail.get("selection_reason"),
        "policy_reason": detail.get("policy_reason"),
    }


def _source_ticket_context(
    events: list[dict[str, Any]],
    config: dict[str, Any],
    *,
    old_terminal_sequence_no: int | None = None,
) -> dict[str, Any]:
    failure_ticket_id = str(config["failure_ticket_id"])
    old_ticket_id = str(config["old_ticket_id"])
    recovery_ticket_id = str(config["recovery_ticket_id"])
    failure_created = _first_event(events, event_type="TICKET_CREATED", ticket_id=failure_ticket_id)
    old_failed = _last_event(events, event_type="TICKET_FAILED", ticket_id=old_ticket_id)
    resolved_old_terminal_sequence_no = old_failed.get("sequence_no") if old_failed else old_terminal_sequence_no
    failure_failed = _last_event(events, event_type="TICKET_FAILED", ticket_id=failure_ticket_id)
    recovery_created = _first_event(events, event_type="TICKET_CREATED", ticket_id=recovery_ticket_id)
    return {
        "workflow_id": config["workflow_id"],
        "node_id": config["node_id"],
        "old_ticket_id": old_ticket_id,
        "failure_ticket_id": failure_ticket_id,
        "recovery_ticket_id": recovery_ticket_id,
        "failure_ticket_attempt_no": (failure_created or {}).get("payload", {}).get("attempt_no"),
        "old_ticket_terminal_sequence_no": resolved_old_terminal_sequence_no,
        "failure_ticket_terminal_sequence_no": failure_failed.get("sequence_no") if failure_failed else None,
        "recovery_ticket_created_sequence_no": recovery_created.get("sequence_no") if recovery_created else None,
    }


def _retry_recovery_outcome(events: list[dict[str, Any]], config: dict[str, Any]) -> dict[str, Any]:
    failure_ticket_id = str(config["failure_ticket_id"])
    recovery_ticket_id = str(config["recovery_ticket_id"])
    retry_event = next(
        (
            event
            for event in events
            if event["event_type"] == "TICKET_RETRY_SCHEDULED"
            and str((event["payload"] or {}).get("ticket_id") or "") == failure_ticket_id
            and str((event["payload"] or {}).get("next_ticket_id") or "") == recovery_ticket_id
        ),
        None,
    )
    recovery_event = next(
        (
            event
            for event in events
            if event["event_type"] == "INCIDENT_RECOVERY_STARTED"
            and str((event["payload"] or {}).get("followup_ticket_id") or "") == recovery_ticket_id
        ),
        None,
    )
    completed_event = _last_event(events, event_type="TICKET_COMPLETED", ticket_id=recovery_ticket_id)
    if completed_event is not None:
        recovery_outcome = "retried_and_completed"
    elif retry_event is not None or recovery_event is not None:
        recovery_outcome = "retry_scheduled"
    else:
        recovery_outcome = "not_recovered"
    return {
        "recovery_outcome": recovery_outcome,
        "retry_event_sequence_no": retry_event.get("sequence_no") if retry_event else None,
        "recovery_event_sequence_no": recovery_event.get("sequence_no") if recovery_event else None,
        "recovery_completed_sequence_no": completed_event.get("sequence_no") if completed_event else None,
        "followup_action": (recovery_event or {}).get("payload", {}).get("followup_action") if recovery_event else None,
        "followup_ticket_id": recovery_ticket_id if retry_event is not None or recovery_event is not None else None,
        "policy_input_fields": [
            "ticket_id",
            "node_id",
            "failure_kind",
            "failure_detail",
            "retry_source_event_type",
            "followup_action",
        ],
        "raw_transcript_used": False,
        "late_output_body_used": False,
        "timestamp_pointer_guess_used": False,
    }


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
    reopened_old_ticket_terminals = [
        {
            "sequence_no": event["sequence_no"],
            "event_type": event["event_type"],
        }
        for event in _events_for_ticket(events, old_ticket_id)
        if recovery_completed is not None
        and event["sequence_no"] > recovery_completed["sequence_no"]
        and event["event_type"] in {"TICKET_COMPLETED", "TICKET_FAILED", "TICKET_CANCELLED"}
    ]
    guard_passed = current_pointer_ticket_id == recovery_ticket_id and not reopened_old_ticket_terminals
    return {
        "guard_passed": guard_passed,
        "old_ticket_id": old_ticket_id,
        "old_terminal_sequence_no": old_terminal_sequence,
        "late_provider_events": late_provider_events,
        "current_pointer_ticket_id": current_pointer_ticket_id,
        "current_pointer_source": "case_range_terminal_events" if recovery_completed is not None else "missing_case_terminal_event",
        "expected_current_ticket_id": recovery_ticket_id,
        "recovery_completed_sequence_no": recovery_completed.get("sequence_no") if recovery_completed else None,
        "old_ticket_terminal_events_after_recovery": reopened_old_ticket_terminals,
    }


def _case_status_and_classification(
    *,
    diagnostics: list[dict[str, Any]],
    provider_failure_kind: str | None,
    raw_archive_refs: list[str],
    late_guard: dict[str, Any],
) -> tuple[str, str]:
    hard_failure_codes = {
        "manifest_not_ready",
        "replay_db_missing",
        "replay_db_invalid",
        "replay_case_unknown",
        "provider_failure_event_missing",
        "provider_attempt_refs_missing",
        "provider_raw_archive_ref_missing",
        "provider_raw_archive_ref_unregistered",
        "provider_failure_taxonomy_legacy_bad_response",
        "late_event_guard_violation",
    }
    diagnostic_codes = {str(item.get("reason_code") or "") for item in diagnostics}
    if diagnostic_codes & hard_failure_codes:
        return "FAILED", REPLAY_IMPORT_ISSUE_CLASSIFICATION
    if provider_failure_kind == "MALFORMED_STREAM_EVENT" and raw_archive_refs and late_guard.get("guard_passed") is True:
        return "READY", PROVIDER_REPLAY_EVIDENCE_CLASSIFICATION
    return "FAILED", REPLAY_IMPORT_ISSUE_CLASSIFICATION


def replay_provider_failure_case(
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
                    "Replay provider failure case id is not registered.",
                    case_id=case_id,
                )
            ],
        )
    diagnostics: list[dict[str, Any]] = []
    if manifest.status != "READY":
        diagnostics.append(
            _diagnostic(
                "manifest_not_ready",
                "Replay provider failure requires a READY ReplayImportManifest.",
                manifest_status=manifest.status,
            )
        )

    db_path = Path(replay_db_path)
    if not db_path.is_file():
        diagnostics.append(
            _diagnostic(
                "replay_db_missing",
                "Replay provider failure requires an imported replay DB.",
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
                "Replay provider failure DB cannot be opened read-only.",
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
        replayed_event_range = _event_range(events)
        failure_ticket_id = str(config["failure_ticket_id"])
        failure_event = _last_event(events, event_type="TICKET_FAILED", ticket_id=failure_ticket_id)
        finished_event = _last_event(events, event_type="PROVIDER_ATTEMPT_FINISHED", ticket_id=failure_ticket_id)
        if failure_event is None:
            diagnostics.append(
                _diagnostic(
                    "provider_failure_event_missing",
                    "Replay case cannot find the provider failure terminal ticket event.",
                    ticket_id=failure_ticket_id,
                )
            )
        failure_payload = failure_event["payload"] if failure_event else {}
        finished_payload = finished_event["payload"] if finished_event else {}
        provider_failure_kind = str(failure_payload.get("failure_kind") or finished_payload.get("failure_kind") or "").strip() or None
        attempts = _attempt_refs(events, failure_ticket_id)
        if not attempts:
            diagnostics.append(
                _diagnostic(
                    "provider_attempt_refs_missing",
                    "Replay case cannot find provider attempt events for the provider failure ticket.",
                    ticket_id=failure_ticket_id,
                )
            )
        raw_archive_refs = _raw_archive_refs(events, failure_ticket_id)
        malformed_message = "malformed" in str(
            failure_payload.get("failure_message") or finished_payload.get("failure_message") or ""
        ).lower()
        if malformed_message and not raw_archive_refs:
            diagnostics.append(
                _diagnostic(
                    "provider_raw_archive_ref_missing",
                    "Malformed provider failure has no raw archive ref in replay events.",
                    ticket_id=failure_ticket_id,
                    missing_refs=["raw_archive_ref"],
                )
            )
        for raw_archive_ref in raw_archive_refs:
            if not _artifact_ref_exists(connection, raw_archive_ref):
                diagnostics.append(
                    _diagnostic(
                        "provider_raw_archive_ref_unregistered",
                        "Replay raw archive ref is not registered in artifact_index.",
                        raw_archive_ref=raw_archive_ref,
                    )
                )
        if malformed_message and provider_failure_kind == "PROVIDER_BAD_RESPONSE":
            diagnostics.append(
                _diagnostic(
                    "provider_failure_taxonomy_legacy_bad_response",
                    "Replay malformed provider failure is recorded with the legacy PROVIDER_BAD_RESPONSE taxonomy.",
                    observed_failure_kind=provider_failure_kind,
                    expected_failure_kind="MALFORMED_STREAM_EVENT",
                )
            )
        late_guard = _late_event_guard(connection, events, config)
        if late_guard.get("guard_passed") is not True:
            diagnostics.append(
                _diagnostic(
                    "late_event_guard_violation",
                    "Late provider events appear to control the current runtime pointer.",
                    current_pointer_ticket_id=late_guard.get("current_pointer_ticket_id"),
                    expected_current_ticket_id=late_guard.get("expected_current_ticket_id"),
                )
            )
        provider_provenance = _provider_provenance(failure_payload, finished_payload)
        source_ticket_context = _source_ticket_context(
            events,
            config,
            old_terminal_sequence_no=late_guard.get("old_terminal_sequence_no")
            if isinstance(late_guard.get("old_terminal_sequence_no"), int)
            else None,
        )
        retry_recovery_outcome = _retry_recovery_outcome(events, config)
        status, classification = _case_status_and_classification(
            diagnostics=diagnostics,
            provider_failure_kind=provider_failure_kind,
            raw_archive_refs=raw_archive_refs,
            late_guard=late_guard,
        )
        return ReplayCaseResult(
            case_id=case_id,
            status=status,  # type: ignore[arg-type]
            source_manifest_hash=manifest.manifest_hash,
            event_range=replayed_event_range,
            provider_failure_kind=provider_failure_kind,
            attempt_refs=attempts,
            raw_archive_refs=raw_archive_refs,
            source_ticket_context=source_ticket_context,
            provider_provenance=provider_provenance,
            retry_recovery_outcome=retry_recovery_outcome,
            late_event_guard=late_guard,
            diagnostics=diagnostics,
            issue_classification=classification,
        )
