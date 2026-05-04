from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from app.contracts.replay import ReplayImportManifest
from app.core.replay_closeout import CLOSEOUT_CASE_ID, replay_closeout_case
from app.replay_closeout_cli import main as replay_closeout_cli_main


WORKFLOW_ID = "wf_7f2902f3c8c6"
CHECK_REPORT_REF = "art://runtime/tkt_3b7e09a86505/delivery-check-report.json"
SOURCE_REF = (
    "art://workspace/tkt_b502981640f5/source/"
    "1-10-project%2Fsrc%2Fbackend%2Ftests%2Fbr-102%2Fapi-regression-fixtures.mjs"
)
CLOSEOUT_REF = "art://runtime/tkt_7a888035b4ff/delivery-closeout-package.json"


def _manifest(db_path: Path, *, status: str = "READY") -> ReplayImportManifest:
    return ReplayImportManifest(
        status=status,
        manifest_version="replay-import-manifest.v1",
        input_db_path=str(db_path),
        artifact_root=str(db_path.parent / "artifacts"),
        log_refs=[],
        input_hashes={
            "event_log_hash": "fixture-event-log",
            "db_sha256": "fixture-db",
        },
        schema={"app_schema_version": "fixture"},
        event_range={"start_sequence_no": 1, "end_sequence_no": 15801},
        event_count=15801,
        workflow_ids=[WORKFLOW_ID],
        artifact_count=3,
        local_file_artifact_count=2,
        inline_db_artifact_count=1,
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
            f"evt_{sequence_no:05d}",
            WORKFLOW_ID,
            event_type,
            "fixture",
            "fixture",
            f"2026-04-29T15:{sequence_no % 60:02d}:00+08:00",
            f"fixture:{sequence_no}",
            None,
            WORKFLOW_ID,
            json.dumps({"workflow_id": WORKFLOW_ID, **payload}, sort_keys=True),
        ),
    )


def _insert_artifact(
    connection: sqlite3.Connection,
    *,
    artifact_ref: str,
    ticket_id: str,
    node_id: str,
    kind: str = "JSON",
    storage_backend: str = "LOCAL_FILE",
) -> None:
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
            artifact_ref,
            WORKFLOW_ID,
            ticket_id,
            node_id,
            artifact_ref.rsplit("/", 1)[-1],
            kind,
            "application/json",
            "MATERIALIZED",
            "ACTIVE",
            None if storage_backend == "INLINE_DB" else artifact_ref.rsplit("/", 1)[-1],
            f"hash-{artifact_ref}",
            42,
            "DELIVERABLE_EVIDENCE",
            storage_backend,
            None,
            "2026-04-29T15:00:00+08:00",
        ),
    )


def _create_closeout_db(tmp_path: Path) -> Path:
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
        _insert_artifact(
            connection,
            artifact_ref=CHECK_REPORT_REF,
            ticket_id="tkt_3b7e09a86505",
            node_id="node_final_check",
        )
        _insert_artifact(
            connection,
            artifact_ref=SOURCE_REF,
            ticket_id="tkt_b502981640f5",
            node_id="node_br_102",
            kind="TEXT",
        )
        _insert_artifact(
            connection,
            artifact_ref=CLOSEOUT_REF,
            ticket_id="tkt_7a888035b4ff",
            node_id="node_ceo_delivery_closeout",
            storage_backend="INLINE_DB",
        )
        _insert_event(
            connection,
            15778,
            "TICKET_CREATED",
            {
                "ticket_id": "tkt_4624a870959f",
                "node_id": "node_ceo_delivery_closeout",
                "output_schema_ref": "delivery_closeout_package",
                "parent_ticket_id": "tkt_3b7e09a86505",
                "input_artifact_refs": [CHECK_REPORT_REF],
            },
        )
        _insert_event(
            connection,
            15786,
            "TICKET_FAILED",
            {
                "ticket_id": "tkt_4624a870959f",
                "node_id": "node_ceo_delivery_closeout",
                "failure_kind": "WORKSPACE_HOOK_VALIDATION_ERROR",
                "failure_message": (
                    "Closeout tickets must keep payload.final_artifact_refs aligned with "
                    "known delivery evidence; got "
                    "art://project-workspace/wf_7f2902f3c8c6/10-project/ARCHITECTURE.md."
                ),
            },
        )
        _insert_event(
            connection,
            15788,
            "TICKET_CREATED",
            {
                "ticket_id": "tkt_737cd07e76e5",
                "node_id": "node_ceo_delivery_closeout",
                "output_schema_ref": "delivery_closeout_package",
                "parent_ticket_id": "tkt_4624a870959f",
                "input_artifact_refs": [CHECK_REPORT_REF],
            },
        )
        _insert_event(
            connection,
            15796,
            "TICKET_FAILED",
            {
                "ticket_id": "tkt_737cd07e76e5",
                "node_id": "node_ceo_delivery_closeout",
                "failure_kind": "WORKSPACE_HOOK_VALIDATION_ERROR",
                "failure_message": (
                    "Closeout tickets must keep payload.final_artifact_refs aligned with "
                    "known delivery evidence; got "
                    "art://runtime/tkt_f58cc1d4ab7b/backlog_recommendation.json."
                ),
            },
        )
        _insert_event(
            connection,
            15798,
            "TICKET_CREATED",
            {
                "ticket_id": "tkt_7a888035b4ff",
                "node_id": "node_ceo_delivery_closeout",
                "output_schema_ref": "delivery_closeout_package",
                "parent_ticket_id": "tkt_4624a870959f",
                "input_artifact_refs": [CHECK_REPORT_REF],
            },
        )
        _insert_event(
            connection,
            15801,
            "TICKET_COMPLETED",
            {
                "ticket_id": "tkt_7a888035b4ff",
                "node_id": "node_ceo_delivery_closeout",
                "artifact_refs": [CLOSEOUT_REF],
                "completion_summary": "Manual M103 closeout package.",
                "payload": {
                    "summary": "Manual M103 closeout package.",
                    "final_artifact_refs": [SOURCE_REF, CHECK_REPORT_REF],
                    "documentation_updates": [
                        {
                            "doc_ref": "doc/tests/intergration-test-015-20260429.md",
                            "status": "UPDATED",
                            "summary": "Recorded M103 closeout recovery.",
                        }
                    ],
                },
                "written_artifacts": [
                    {
                        "artifact_ref": CLOSEOUT_REF,
                        "path": "20-evidence/closeout/tkt_7a888035b4ff/delivery-closeout-package.json",
                        "kind": "JSON",
                        "content_json": {
                            "summary": "Manual M103 closeout package.",
                            "final_artifact_refs": [SOURCE_REF, CHECK_REPORT_REF],
                            "documentation_updates": [
                                {
                                    "doc_ref": "doc/tests/intergration-test-015-20260429.md",
                                    "status": "UPDATED",
                                    "summary": "Recorded M103 closeout recovery.",
                                }
                            ],
                        },
                    }
                ],
            },
        )
    return db_path


def _reason_codes(result) -> set[str]:
    return {str(item["reason_code"]) for item in result.diagnostics}


def test_closeout_replay_blocks_legacy_manual_closeout_without_contract_table(tmp_path: Path) -> None:
    db_path = _create_closeout_db(tmp_path)

    result = replay_closeout_case(
        manifest=_manifest(db_path),
        replay_db_path=db_path,
        case_id=CLOSEOUT_CASE_ID,
    )

    assert result.status == "FAILED"
    assert result.issue_classification == "replay/import issue"
    assert result.event_range == {"start_sequence_no": 15778, "end_sequence_no": 15801}
    assert result.closeout_tickets[-1]["ticket_id"] == "tkt_7a888035b4ff"
    assert result.closeout_tickets[-1]["manual_recovery"] is True
    assert result.closeout_contract_summary["status"] == "BLOCKED"
    assert result.closeout_contract_summary["missing_payload_fields"] == [
        "deliverable_contract_version",
        "deliverable_contract_id",
        "evaluation_fingerprint",
        "final_evidence_table",
    ]
    assert result.final_evidence_table_summary["compiled_row_count"] >= 2
    assert result.final_evidence_table_summary["submitted_row_count"] == 0
    assert result.bypass_guard["manual_closeout_recovery_bypassed_contract"] is False
    assert result.bypass_guard["graph_terminal_override_used"] is False
    assert result.bypass_guard["checker_verdict_only_allowed"] is False
    assert result.audit_disposition["disposition"] == "legacy_manual_closeout_rejected"
    assert "closeout_missing_final_evidence_table" in _reason_codes(result)


def test_closeout_replay_records_governance_and_backlog_refs_as_rejected(tmp_path: Path) -> None:
    db_path = _create_closeout_db(tmp_path)

    result = replay_closeout_case(
        manifest=_manifest(db_path),
        replay_db_path=db_path,
        case_id=CLOSEOUT_CASE_ID,
    )

    rejected_refs = {
        ref
        for ticket in result.closeout_tickets
        for ref in list(ticket.get("rejected_final_artifact_refs") or [])
    }
    assert "art://project-workspace/wf_7f2902f3c8c6/10-project/ARCHITECTURE.md" in rejected_refs
    assert "art://runtime/tkt_f58cc1d4ab7b/backlog_recommendation.json" in rejected_refs
    assert result.final_evidence_table_summary["illegal_statuses_present"] == []
    assert result.final_evidence_table_summary["forbidden_ref_kinds_present"] == []


def test_closeout_cli_writes_failed_case_result_for_legacy_manual_recovery(tmp_path: Path) -> None:
    db_path = _create_closeout_db(tmp_path)
    manifest_path = tmp_path / "manifest.json"
    out_path = tmp_path / "case-out" / "closeout.json"
    manifest_path.write_text(_manifest(db_path).model_dump_json(indent=2), encoding="utf-8")

    exit_code = replay_closeout_cli_main(
        [
            "--manifest",
            str(manifest_path),
            "--replay-db",
            str(db_path),
            "--case-id",
            CLOSEOUT_CASE_ID,
            "--case-out",
            str(out_path),
        ]
    )

    payload = json.loads(out_path.read_text(encoding="utf-8"))
    assert exit_code == 2
    assert payload["status"] == "FAILED"
    assert payload["issue_classification"] == "replay/import issue"
    assert payload["audit_disposition"]["disposition"] == "legacy_manual_closeout_rejected"
