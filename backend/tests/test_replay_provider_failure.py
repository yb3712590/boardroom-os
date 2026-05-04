from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from app.contracts.replay import ReplayImportManifest
from app.core.replay_provider_failure import replay_provider_failure_case


WORKFLOW_ID = "wf_7f2902f3c8c6"
NODE_ID = "node_backlog_followup_br_041_m4_isbn_remove_inventory"
OLD_TICKET_ID = "tkt_30c7a10979ae"
FAILURE_TICKET_ID = "tkt_0c616378c9ac"
RECOVERY_TICKET_ID = "tkt_2b58304dccb9"
CASE_ID = "provider-failure-015-malformed-sse"


def _manifest(db_path: Path, *, status: str = "READY") -> ReplayImportManifest:
    return ReplayImportManifest(
        status=status,
        manifest_version="replay-import-manifest.v1",
        input_db_path=str(db_path),
        artifact_root=str(db_path.parent / "artifacts"),
        log_refs=[],
        input_hashes={"event_log_hash": "fixture-event-log"},
        schema={"app_schema_version": "fixture"},
        event_range={"start_sequence_no": 1, "end_sequence_no": 20},
        event_count=20,
        workflow_ids=[WORKFLOW_ID],
        artifact_count=1,
        local_file_artifact_count=1,
        inline_db_artifact_count=0,
        import_diagnostics=[],
        idempotency_key="replay-import:fixture",
        manifest_hash="manifest-fixture",
    )


def _insert_event(
    connection: sqlite3.Connection,
    sequence_no: int,
    event_type: str,
    payload: dict[str, Any],
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
            sequence_no,
            f"evt_{sequence_no:04d}",
            WORKFLOW_ID,
            event_type,
            "fixture",
            "fixture",
            f"2026-04-29T15:{sequence_no % 60:02d}:00+08:00",
            f"fixture:{sequence_no}",
            None,
            WORKFLOW_ID,
            json.dumps(payload, sort_keys=True),
        ),
    )


def _create_case_db(
    tmp_path: Path,
    *,
    failure_kind: str,
    raw_archive_ref: str | None,
    current_pointer_ticket_id: str = RECOVERY_TICKET_ID,
    include_failure_attempt: bool = True,
    include_recovery_completed: bool = True,
) -> Path:
    db_path = tmp_path / "replay.db"
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            CREATE TABLE events (
                sequence_no INTEGER,
                event_id TEXT,
                workflow_id TEXT,
                event_type TEXT,
                actor_type TEXT,
                actor_id TEXT,
                occurred_at TEXT,
                idempotency_key TEXT,
                causation_id TEXT,
                correlation_id TEXT,
                payload_json TEXT
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE runtime_node_projection (
                workflow_id TEXT,
                graph_node_id TEXT,
                node_id TEXT,
                runtime_node_id TEXT,
                latest_ticket_id TEXT,
                status TEXT,
                blocking_reason_code TEXT,
                graph_version TEXT,
                updated_at TEXT,
                version INTEGER
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE artifact_index (
                artifact_ref TEXT,
                workflow_id TEXT,
                ticket_id TEXT,
                node_id TEXT,
                logical_path TEXT,
                kind TEXT,
                media_type TEXT,
                materialization_status TEXT,
                lifecycle_status TEXT,
                storage_relpath TEXT,
                content_hash TEXT,
                size_bytes INTEGER,
                retention_class TEXT,
                storage_backend TEXT,
                storage_object_key TEXT,
                created_at TEXT
            )
            """
        )

        _insert_event(
            connection,
            9942,
            "TICKET_CREATED",
            {"workflow_id": WORKFLOW_ID, "ticket_id": OLD_TICKET_ID, "node_id": NODE_ID, "attempt_no": 6},
        )
        _insert_event(
            connection,
            9952,
            "PROVIDER_ATTEMPT_STARTED",
            {
                "workflow_id": WORKFLOW_ID,
                "ticket_id": OLD_TICKET_ID,
                "node_id": NODE_ID,
                "attempt_id": f"attempt:{WORKFLOW_ID}:{OLD_TICKET_ID}:prov:1",
                "attempt_no": 1,
                "provider_id": "prov_openai_compat_truerealbill",
                "actual_model": "gpt-5.5",
            },
        )
        _insert_event(
            connection,
            9965,
            "PROVIDER_ATTEMPT_FINISHED",
            {
                "workflow_id": WORKFLOW_ID,
                "ticket_id": OLD_TICKET_ID,
                "node_id": NODE_ID,
                "attempt_id": f"attempt:{WORKFLOW_ID}:{OLD_TICKET_ID}:prov:1",
                "attempt_no": 1,
                "status": "FAILED",
                "state": "FAILED_TERMINAL",
                "failure_kind": "PROVIDER_BAD_RESPONSE",
                "failure_message": "empty assistant",
                "provider_id": "prov_openai_compat_truerealbill",
                "actual_model": "gpt-5.5",
            },
        )
        _insert_event(
            connection,
            9967,
            "TICKET_FAILED",
            {
                "workflow_id": WORKFLOW_ID,
                "ticket_id": OLD_TICKET_ID,
                "node_id": NODE_ID,
                "failure_kind": "PROVIDER_BAD_RESPONSE",
                "failure_message": "empty assistant",
                "failure_detail": {"failure_kind": "PROVIDER_BAD_RESPONSE"},
            },
        )
        _insert_event(
            connection,
            9974,
            "PROVIDER_ATTEMPT_HEARTBEAT_RECORDED",
            {
                "workflow_id": WORKFLOW_ID,
                "ticket_id": OLD_TICKET_ID,
                "node_id": NODE_ID,
                "attempt_id": f"attempt:{WORKFLOW_ID}:{OLD_TICKET_ID}:prov:1",
                "attempt_no": 1,
                "state": "STREAMING",
            },
        )
        _insert_event(
            connection,
            9968,
            "TICKET_RETRY_SCHEDULED",
            {
                "workflow_id": WORKFLOW_ID,
                "ticket_id": OLD_TICKET_ID,
                "node_id": NODE_ID,
                "next_ticket_id": FAILURE_TICKET_ID,
                "retry_source_event_type": "TICKET_FAILED",
            },
        )
        _insert_event(
            connection,
            9969,
            "TICKET_CREATED",
            {"workflow_id": WORKFLOW_ID, "ticket_id": FAILURE_TICKET_ID, "node_id": NODE_ID, "attempt_no": 7},
        )
        if include_failure_attempt:
            _insert_event(
                connection,
                9973,
                "PROVIDER_ATTEMPT_STARTED",
                {
                    "workflow_id": WORKFLOW_ID,
                    "ticket_id": FAILURE_TICKET_ID,
                    "node_id": NODE_ID,
                    "attempt_id": f"attempt:{WORKFLOW_ID}:{FAILURE_TICKET_ID}:prov:1",
                    "attempt_no": 1,
                    "provider_id": "prov_openai_compat_truerealbill",
                    "actual_model": "gpt-5.5",
                    "provider_policy_ref": "provider-policy:prov_openai_compat_truerealbill:gpt-5.5:xhigh:openai_compat",
                },
            )
            finished_payload = {
                "workflow_id": WORKFLOW_ID,
                "ticket_id": FAILURE_TICKET_ID,
                "node_id": NODE_ID,
                "attempt_id": f"attempt:{WORKFLOW_ID}:{FAILURE_TICKET_ID}:prov:1",
                "attempt_no": 1,
                "status": "FAILED",
                "state": "FAILED_TERMINAL",
                "failure_kind": failure_kind,
                "failure_message": "Provider stream emitted malformed SSE JSON.",
                "provider_id": "prov_openai_compat_truerealbill",
                "actual_model": "gpt-5.5",
            }
            if raw_archive_ref:
                finished_payload["raw_archive_ref"] = raw_archive_ref
            _insert_event(connection, 9995, "PROVIDER_ATTEMPT_FINISHED", finished_payload)
        failure_detail = {
            "actual_model": "gpt-5.5",
            "actual_provider_id": "prov_openai_compat_truerealbill",
            "adapter_kind": "openai_compat",
            "attempt_count": 1,
            "failure_kind": failure_kind,
            "fallback_applied": False,
            "fallback_blocked": True,
            "fingerprint": f"provider:prov_openai_compat_truerealbill:gpt-5.5:{failure_kind}:provider_failure",
            "preferred_model": "gpt-5.5",
            "preferred_provider_id": "prov_openai_compat_truerealbill",
            "provider_id": "prov_openai_compat_truerealbill",
            "provider_attempt_log": [
                {
                    "actual_model": "gpt-5.5",
                    "failure_kind": failure_kind,
                    "failure_message": "Provider stream emitted malformed SSE JSON.",
                    "provider_id": "prov_openai_compat_truerealbill",
                    "status": "FAILED",
                }
            ],
        }
        if raw_archive_ref:
            failure_detail["raw_archive_ref"] = raw_archive_ref
            failure_detail["provider_attempt_log"][0]["raw_archive_ref"] = raw_archive_ref
        _insert_event(
            connection,
            9996,
            "TICKET_FAILED",
            {
                "workflow_id": WORKFLOW_ID,
                "ticket_id": FAILURE_TICKET_ID,
                "node_id": NODE_ID,
                "failure_kind": failure_kind,
                "failure_message": "Provider stream emitted malformed SSE JSON.",
                "failure_detail": failure_detail,
            },
        )
        _insert_event(
            connection,
            9998,
            "INCIDENT_OPENED",
            {
                "workflow_id": WORKFLOW_ID,
                "ticket_id": FAILURE_TICKET_ID,
                "node_id": NODE_ID,
                "incident_id": "inc_provider_failure",
                "incident_type": "CEO_SHADOW_PIPELINE_FAILED",
                "status": "OPEN",
            },
        )
        _insert_event(
            connection,
            10007,
            "TICKET_RETRY_SCHEDULED",
            {
                "workflow_id": WORKFLOW_ID,
                "ticket_id": FAILURE_TICKET_ID,
                "node_id": NODE_ID,
                "next_ticket_id": RECOVERY_TICKET_ID,
                "retry_source_event_type": "TICKET_FAILED",
            },
        )
        _insert_event(
            connection,
            10009,
            "INCIDENT_RECOVERY_STARTED",
            {
                "workflow_id": WORKFLOW_ID,
                "incident_id": "inc_provider_failure",
                "incident_type": "CEO_SHADOW_PIPELINE_FAILED",
                "followup_action": "RESTORE_AND_RETRY_LATEST_FAILURE",
                "followup_ticket_id": RECOVERY_TICKET_ID,
                "status": "RECOVERING",
            },
        )
        _insert_event(
            connection,
            10008,
            "TICKET_CREATED",
            {"workflow_id": WORKFLOW_ID, "ticket_id": RECOVERY_TICKET_ID, "node_id": NODE_ID, "attempt_no": 8},
        )
        _insert_event(
            connection,
            10012,
            "PROVIDER_ATTEMPT_STARTED",
            {
                "workflow_id": WORKFLOW_ID,
                "ticket_id": RECOVERY_TICKET_ID,
                "node_id": NODE_ID,
                "attempt_id": f"attempt:{WORKFLOW_ID}:{RECOVERY_TICKET_ID}:prov:1",
                "attempt_no": 1,
            },
        )
        _insert_event(
            connection,
            10015,
            "PROVIDER_ATTEMPT_FINISHED",
            {
                "workflow_id": WORKFLOW_ID,
                "ticket_id": RECOVERY_TICKET_ID,
                "node_id": NODE_ID,
                "attempt_id": f"attempt:{WORKFLOW_ID}:{RECOVERY_TICKET_ID}:prov:1",
                "attempt_no": 1,
                "status": "COMPLETED",
                "state": "COMPLETED",
            },
        )
        if include_recovery_completed:
            _insert_event(
                connection,
                10016,
                "TICKET_COMPLETED",
                {
                    "workflow_id": WORKFLOW_ID,
                    "ticket_id": RECOVERY_TICKET_ID,
                    "node_id": NODE_ID,
                    "artifact_refs": [],
                    "completion_summary": "Provider-backed runtime executed retry ticket.",
                },
            )
        if raw_archive_ref:
            connection.execute(
                """
                INSERT INTO artifact_index (
                    artifact_ref,
                    workflow_id,
                    ticket_id,
                    node_id,
                    logical_path,
                    kind,
                    media_type,
                    materialization_status,
                    lifecycle_status,
                    storage_relpath,
                    content_hash,
                    size_bytes,
                    retention_class,
                    storage_backend,
                    storage_object_key,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    raw_archive_ref,
                    WORKFLOW_ID,
                    FAILURE_TICKET_ID,
                    NODE_ID,
                    "reports/ops/provider-stream-archives/provider-attempt-1.json",
                    "JSON",
                    "application/json",
                    "MATERIALIZED",
                    "ACTIVE",
                    "reports/ops/provider-stream-archives/provider-attempt-1.json",
                    "hash",
                    42,
                    "OPERATIONAL_EVIDENCE",
                    "LOCAL_FILE",
                    None,
                    "2026-04-29T15:09:00+08:00",
                ),
            )
        connection.execute(
            """
            INSERT INTO runtime_node_projection (
                workflow_id,
                graph_node_id,
                node_id,
                runtime_node_id,
                latest_ticket_id,
                status,
                blocking_reason_code,
                graph_version,
                updated_at,
                version
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                WORKFLOW_ID,
                NODE_ID,
                NODE_ID,
                NODE_ID,
                current_pointer_ticket_id,
                "COMPLETED",
                None,
                "gv_fixture",
                "2026-04-29T15:17:00+08:00",
                10016,
            ),
        )
    return db_path


def _reason_codes(result) -> set[str]:
    return {str(item["reason_code"]) for item in result.diagnostics}


def test_provider_failure_replay_classifies_malformed_with_raw_archive_as_provider_evidence(tmp_path: Path) -> None:
    raw_archive_ref = "art://ops/provider-raw-stream/provider-attempt-1"
    db_path = _create_case_db(
        tmp_path,
        failure_kind="MALFORMED_STREAM_EVENT",
        raw_archive_ref=raw_archive_ref,
    )

    result = replay_provider_failure_case(
        manifest=_manifest(db_path),
        replay_db_path=db_path,
        case_id=CASE_ID,
    )

    assert result.status == "READY"
    assert result.issue_classification == "provider replay evidence"
    assert result.provider_failure_kind == "MALFORMED_STREAM_EVENT"
    assert result.raw_archive_refs == [raw_archive_ref]
    assert result.provider_provenance["actual_provider_id"] == "prov_openai_compat_truerealbill"
    assert result.provider_provenance["preferred_provider_id"] == "prov_openai_compat_truerealbill"
    assert result.retry_recovery_outcome["recovery_outcome"] == "retried_and_completed"
    assert result.retry_recovery_outcome["raw_transcript_used"] is False
    assert result.late_event_guard["guard_passed"] is True


def test_provider_failure_replay_classifies_missing_raw_archive_as_replay_import_issue(tmp_path: Path) -> None:
    db_path = _create_case_db(
        tmp_path,
        failure_kind="PROVIDER_BAD_RESPONSE",
        raw_archive_ref=None,
    )

    result = replay_provider_failure_case(
        manifest=_manifest(db_path),
        replay_db_path=db_path,
        case_id=CASE_ID,
    )

    assert result.status == "FAILED"
    assert result.issue_classification == "replay/import issue"
    assert result.provider_failure_kind == "PROVIDER_BAD_RESPONSE"
    assert result.raw_archive_refs == []
    assert "provider_raw_archive_ref_missing" in _reason_codes(result)
    assert "provider_failure_taxonomy_legacy_bad_response" in _reason_codes(result)


def test_provider_failure_replay_flags_late_event_current_pointer_violation(tmp_path: Path) -> None:
    raw_archive_ref = "art://ops/provider-raw-stream/provider-attempt-1"
    db_path = _create_case_db(
        tmp_path,
        failure_kind="MALFORMED_STREAM_EVENT",
        raw_archive_ref=raw_archive_ref,
        include_recovery_completed=False,
    )

    result = replay_provider_failure_case(
        manifest=_manifest(db_path),
        replay_db_path=db_path,
        case_id=CASE_ID,
    )

    assert result.status == "FAILED"
    assert result.late_event_guard["guard_passed"] is False
    assert result.late_event_guard["current_pointer_ticket_id"] is None
    assert result.late_event_guard["current_pointer_source"] == "missing_case_terminal_event"
    assert "late_event_guard_violation" in _reason_codes(result)


def test_provider_failure_replay_uses_case_range_current_pointer_not_final_projection(tmp_path: Path) -> None:
    raw_archive_ref = "art://ops/provider-raw-stream/provider-attempt-1"
    db_path = _create_case_db(
        tmp_path,
        failure_kind="MALFORMED_STREAM_EVENT",
        raw_archive_ref=raw_archive_ref,
        current_pointer_ticket_id="tkt_later_unrelated_ticket",
    )

    result = replay_provider_failure_case(
        manifest=_manifest(db_path),
        replay_db_path=db_path,
        case_id=CASE_ID,
    )

    assert result.status == "READY"
    assert result.late_event_guard["guard_passed"] is True
    assert result.late_event_guard["current_pointer_source"] == "case_range_terminal_events"
    assert result.late_event_guard["current_pointer_ticket_id"] == RECOVERY_TICKET_ID
    assert "late_event_guard_violation" not in _reason_codes(result)


def test_provider_failure_replay_fails_closed_when_attempt_refs_are_missing(tmp_path: Path) -> None:
    db_path = _create_case_db(
        tmp_path,
        failure_kind="MALFORMED_STREAM_EVENT",
        raw_archive_ref="art://ops/provider-raw-stream/provider-attempt-1",
        include_failure_attempt=False,
    )

    result = replay_provider_failure_case(
        manifest=_manifest(db_path),
        replay_db_path=db_path,
        case_id=CASE_ID,
    )

    assert result.status == "FAILED"
    assert result.issue_classification == "replay/import issue"
    assert "provider_attempt_refs_missing" in _reason_codes(result)


def test_provider_failure_replay_fails_closed_when_manifest_is_not_ready(tmp_path: Path) -> None:
    db_path = _create_case_db(
        tmp_path,
        failure_kind="MALFORMED_STREAM_EVENT",
        raw_archive_ref="art://ops/provider-raw-stream/provider-attempt-1",
    )

    result = replay_provider_failure_case(
        manifest=_manifest(db_path, status="FAILED"),
        replay_db_path=db_path,
        case_id=CASE_ID,
    )

    assert result.status == "FAILED"
    assert result.issue_classification == "replay/import issue"
    assert "manifest_not_ready" in _reason_codes(result)
