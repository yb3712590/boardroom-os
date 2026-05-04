from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from app.contracts.replay import ReplayCaseResult, ReplayImportManifest
from app.core.workspace_path_contracts import ArtifactRefKind, resolve_artifact_ref_contract
from app.core.workflow_completion import (
    _closeout_contract_payload_issue,
    _compile_closeout_contract_inputs,
)

CLOSEOUT_CASE_ID = "closeout-015-manual-m103-contract-gate"
CLOSEOUT_REPLAY_EVIDENCE_CLASSIFICATION = "closeout replay evidence"
REPLAY_IMPORT_ISSUE_CLASSIFICATION = "replay/import issue"

_CASE_CONFIGS: dict[str, dict[str, Any]] = {
    CLOSEOUT_CASE_ID: {
        "workflow_id": "wf_7f2902f3c8c6",
        "event_range": {"start_sequence_no": 15778, "end_sequence_no": 15801},
        "closeout_ticket_ids": [
            "tkt_4624a870959f",
            "tkt_737cd07e76e5",
            "tkt_7a888035b4ff",
        ],
        "final_closeout_ticket_id": "tkt_7a888035b4ff",
        "graph_version": "gv_731",
    }
}

_REQUIRED_CLOSEOUT_FIELDS = [
    "deliverable_contract_version",
    "deliverable_contract_id",
    "evaluation_fingerprint",
    "final_evidence_table",
]
_FORBIDDEN_FINAL_TABLE_STATUSES = {
    "SUPERSEDED",
    "PLACEHOLDER",
    "ARCHIVE",
    "UNKNOWN_REF",
    "STALE_CURRENT_POINTER",
    "ILLEGAL_KIND",
}
_FORBIDDEN_REF_KINDS = {
    ArtifactRefKind.GOVERNANCE_DOCUMENT.value,
    ArtifactRefKind.ARCHIVE.value,
    ArtifactRefKind.UNKNOWN.value,
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
            "guard_passed": True,
            "current_pointer_source": "not_provider_replay",
        },
        diagnostics=diagnostics,
        issue_classification=REPLAY_IMPORT_ISSUE_CLASSIFICATION,
    )


def failed_closeout_case_result(
    *,
    case_id: str,
    diagnostics: list[dict[str, Any]],
    manifest: ReplayImportManifest | None = None,
) -> ReplayCaseResult:
    config = _CASE_CONFIGS.get(case_id)
    return _empty_result(
        case_id=case_id,
        manifest=manifest,
        diagnostics=diagnostics,
        event_range=dict(config["event_range"]) if config is not None else None,
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
    ticket_id: str,
) -> dict[str, Any] | None:
    matches = [
        event
        for event in events
        if event["event_type"] == event_type
        and str((event["payload"] or {}).get("ticket_id") or "") == ticket_id
    ]
    return matches[-1] if matches else None


def _closeout_payload_from_terminal(terminal_event: dict[str, Any] | None) -> dict[str, Any]:
    if terminal_event is None:
        return {}
    payload = terminal_event.get("payload") or {}
    nested = payload.get("payload")
    return dict(nested) if isinstance(nested, dict) else {}


def _extract_rejected_ref(failure_message: str) -> str | None:
    marker = "got "
    if marker not in failure_message:
        return None
    rejected = failure_message.split(marker, 1)[1].strip()
    if rejected.endswith("."):
        rejected = rejected[:-1]
    return rejected.strip() or None


def _known_final_refs_from_payload(payload: dict[str, Any]) -> set[str]:
    known_refs: set[str] = set()
    for ref in list(payload.get("final_artifact_refs") or []):
        normalized = str(ref).strip()
        if not normalized:
            continue
        contract = resolve_artifact_ref_contract(normalized)
        if contract.kind in {
            ArtifactRefKind.WORKSPACE_SOURCE,
            ArtifactRefKind.TEST_EVIDENCE,
            ArtifactRefKind.VERIFICATION_EVIDENCE,
            ArtifactRefKind.DELIVERY_REPORT,
            ArtifactRefKind.DELIVERY_CHECK_REPORT,
            ArtifactRefKind.GIT_EVIDENCE,
        }:
            known_refs.add(normalized)
    return known_refs


def _source_and_check_ticket_ids(refs: set[str]) -> tuple[set[str], set[str]]:
    source_ticket_ids: set[str] = set()
    check_ticket_ids: set[str] = set()
    for ref in refs:
        contract = resolve_artifact_ref_contract(ref)
        if contract.kind == ArtifactRefKind.WORKSPACE_SOURCE and contract.ticket_id:
            source_ticket_ids.add(contract.ticket_id)
        if contract.kind in {ArtifactRefKind.DELIVERY_CHECK_REPORT, ArtifactRefKind.DELIVERY_REPORT} and contract.ticket_id:
            check_ticket_ids.add(contract.ticket_id)
    return source_ticket_ids, check_ticket_ids


def _closeout_ticket_summary(ticket_id: str, events: list[dict[str, Any]], final_ticket_id: str) -> dict[str, Any]:
    created = _last_event(events, event_type="TICKET_CREATED", ticket_id=ticket_id)
    failed = _last_event(events, event_type="TICKET_FAILED", ticket_id=ticket_id)
    completed = _last_event(events, event_type="TICKET_COMPLETED", ticket_id=ticket_id)
    rejected_ref = None
    if failed is not None:
        rejected_ref = _extract_rejected_ref(str((failed["payload"] or {}).get("failure_message") or ""))
    terminal = completed or failed
    return {
        "ticket_id": ticket_id,
        "node_id": str(((created or terminal or {}).get("payload") or {}).get("node_id") or ""),
        "created_sequence_no": created.get("sequence_no") if created else None,
        "terminal_sequence_no": terminal.get("sequence_no") if terminal else None,
        "terminal_event_type": terminal.get("event_type") if terminal else None,
        "failure_kind": ((failed or {}).get("payload") or {}).get("failure_kind") if failed else None,
        "rejected_final_artifact_refs": [rejected_ref] if rejected_ref else [],
        "manual_recovery": ticket_id == final_ticket_id and completed is not None,
        "artifact_refs": list(((completed or {}).get("payload") or {}).get("artifact_refs") or []),
    }


def _contract_summaries(
    *,
    workflow_id: str,
    graph_version: str,
    closeout_ticket_id: str,
    closeout_payload: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    final_refs = [str(ref).strip() for ref in list(closeout_payload.get("final_artifact_refs") or []) if str(ref).strip()]
    known_refs = _known_final_refs_from_payload(closeout_payload)
    source_ticket_ids, check_ticket_ids = _source_and_check_ticket_ids(known_refs)
    contract, _evidence_pack, evaluation, final_table = _compile_closeout_contract_inputs(
        workflow_id=workflow_id,
        graph_version=graph_version,
        final_artifact_refs=final_refs,
        known_final_refs=known_refs or set(final_refs),
        placeholder_final_refs={ref for ref in set(final_refs) | known_refs if ref.endswith("/source.py")},
        source_delivery_ticket_ids=source_ticket_ids,
        delivery_check_ticket_ids=check_ticket_ids,
        closeout_ticket_id=closeout_ticket_id,
    )
    contract_issue = _closeout_contract_payload_issue(
        closeout_ticket_id=closeout_ticket_id,
        closeout_payloads=[closeout_payload],
        contract=contract,
        evaluation=evaluation,
        final_table=final_table,
    )
    submitted_table = closeout_payload.get("final_evidence_table")
    submitted_rows = submitted_table if isinstance(submitted_table, list) else []
    compiled_rows = [row.model_dump(mode="json") for row in final_table.rows]
    missing_payload_fields = [
        field
        for field in _REQUIRED_CLOSEOUT_FIELDS
        if field not in closeout_payload or (field == "final_evidence_table" and not submitted_rows)
    ]
    illegal_statuses_present = sorted(
        {
            str(row.get("legality_status") or "")
            for row in compiled_rows
            if str(row.get("legality_status") or "") in _FORBIDDEN_FINAL_TABLE_STATUSES
        }
        | {
            str(row.get("current_status") or "")
            for row in compiled_rows
            if str(row.get("current_status") or "") in _FORBIDDEN_FINAL_TABLE_STATUSES
        }
    )
    forbidden_ref_kinds_present = sorted(
        {
            str(row.get("artifact_kind") or "")
            for row in compiled_rows
            if str(row.get("artifact_kind") or "") in _FORBIDDEN_REF_KINDS
        }
    )
    contract_summary = {
        "status": "BLOCKED" if contract_issue is not None else "ACCEPTED",
        "contract_id": contract.contract_id,
        "contract_version": contract.contract_version,
        "evaluation_fingerprint": evaluation.evaluation_fingerprint,
        "blocking_finding_count": evaluation.blocking_finding_count,
        "contract_issue_reason_code": (contract_issue or {}).get("reason_code"),
        "missing_payload_fields": missing_payload_fields,
    }
    table_summary = {
        "compiled_row_count": len(compiled_rows),
        "submitted_row_count": len(submitted_rows),
        "compiled_evidence_refs": [str(row.get("evidence_ref")) for row in compiled_rows],
        "illegal_statuses_present": illegal_statuses_present,
        "forbidden_ref_kinds_present": forbidden_ref_kinds_present,
    }
    diagnostics: list[dict[str, Any]] = []
    if contract_issue is not None:
        diagnostics.append(
            _diagnostic(
                str(contract_issue.get("reason_code") or "closeout_contract_blocked"),
                "Legacy closeout package cannot satisfy the deliverable contract payload gate.",
                classification=REPLAY_IMPORT_ISSUE_CLASSIFICATION,
                details=contract_issue.get("details") or {},
            )
        )
    return contract_summary, table_summary, diagnostics


def replay_closeout_case(
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
                    "Replay closeout case id is not registered.",
                    case_id=case_id,
                )
            ],
        )
    diagnostics: list[dict[str, Any]] = []
    if manifest.status != "READY":
        diagnostics.append(
            _diagnostic(
                "manifest_not_ready",
                "Replay closeout requires a READY ReplayImportManifest.",
                manifest_status=manifest.status,
            )
        )

    db_path = Path(replay_db_path)
    if not db_path.is_file():
        diagnostics.append(
            _diagnostic(
                "replay_db_missing",
                "Replay closeout requires an imported replay DB.",
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
                "Replay closeout DB cannot be opened read-only.",
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
                "Replay closeout case range has no events.",
                event_range=config["event_range"],
            )
        )
        return _empty_result(case_id=case_id, manifest=manifest, diagnostics=diagnostics, event_range=config["event_range"])

    final_ticket_id = str(config["final_closeout_ticket_id"])
    final_terminal = _last_event(events, event_type="TICKET_COMPLETED", ticket_id=final_ticket_id)
    closeout_payload = _closeout_payload_from_terminal(final_terminal)
    closeout_tickets = [
        _closeout_ticket_summary(str(ticket_id), events, final_ticket_id)
        for ticket_id in list(config["closeout_ticket_ids"])
    ]
    contract_summary, final_table_summary, contract_diagnostics = _contract_summaries(
        workflow_id=str(config["workflow_id"]),
        graph_version=str(config["graph_version"]),
        closeout_ticket_id=final_ticket_id,
        closeout_payload=closeout_payload,
    )
    diagnostics.extend(contract_diagnostics)
    for ticket in closeout_tickets:
        for ref in list(ticket.get("rejected_final_artifact_refs") or []):
            diagnostics.append(
                _diagnostic(
                    "closeout_illegal_ref_rejected",
                    "Legacy closeout attempt rejected a non-delivery final artifact ref.",
                    classification=CLOSEOUT_REPLAY_EVIDENCE_CLASSIFICATION,
                    ticket_id=ticket["ticket_id"],
                    artifact_ref=ref,
                )
            )
    manual_bypassed = contract_summary["status"] == "ACCEPTED" and not contract_summary["missing_payload_fields"]
    status = "FAILED" if contract_summary["status"] != "ACCEPTED" else "READY"
    classification = (
        REPLAY_IMPORT_ISSUE_CLASSIFICATION
        if status == "FAILED"
        else CLOSEOUT_REPLAY_EVIDENCE_CLASSIFICATION
    )
    return ReplayCaseResult(
        case_id=case_id,
        status=status,  # type: ignore[arg-type]
        source_manifest_hash=manifest.manifest_hash,
        event_range=_event_range(events),
        provider_failure_kind=None,
        attempt_refs=[],
        raw_archive_refs=[],
        source_ticket_context={
            "workflow_id": config["workflow_id"],
            "final_closeout_ticket_id": final_ticket_id,
            "manual_recovery_source": "M103",
        },
        provider_provenance={},
        retry_recovery_outcome={
            "recovery_outcome": "manual_closeout_recovery",
            "raw_transcript_used": False,
            "late_output_body_used": False,
            "timestamp_pointer_guess_used": False,
        },
        late_event_guard={
            "guard_passed": True,
            "current_pointer_source": "structured_closeout_events",
            "timestamp_pointer_guess_used": False,
        },
        diagnostics=diagnostics,
        issue_classification=classification,
        evidence_refs={
            "final_artifact_refs": list(closeout_payload.get("final_artifact_refs") or []),
            "closeout_artifact_refs": list(((final_terminal or {}).get("payload") or {}).get("artifact_refs") or []),
            "rejected_final_artifact_refs": [
                ref
                for ticket in closeout_tickets
                for ref in list(ticket.get("rejected_final_artifact_refs") or [])
            ],
        },
        graph_terminal_override_used=False,
        closeout_tickets=closeout_tickets,
        closeout_contract_summary=contract_summary,
        final_evidence_table_summary=final_table_summary,
        bypass_guard={
            "manual_closeout_recovery_bypassed_contract": manual_bypassed,
            "graph_terminal_override_used": False,
            "checker_verdict_only_allowed": False,
            "failed_delivery_report_only_allowed": False,
            "governance_docs_only_allowed": False,
        },
        audit_disposition={
            "disposition": (
                "legacy_manual_closeout_rejected"
                if status == "FAILED"
                else "closeout_contract_replay_evidence"
            ),
            "issue_type": "replay/import issue" if status == "FAILED" else "contract gap",
            "next_round": "Round 12 backend-only live scenario clean run",
        },
    )
