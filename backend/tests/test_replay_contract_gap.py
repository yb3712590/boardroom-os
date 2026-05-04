from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from app.contracts.replay import ReplayImportManifest
from app.core.replay_contract_gap import (
    BR032_AUTH_MISMATCH_CASE_ID,
    BR040_PLACEHOLDER_DELIVERY_CASE_ID,
    BR041_PLACEHOLDER_DELIVERY_CASE_ID,
    replay_contract_gap_case,
)
from app.replay_contract_gap_cli import main as replay_contract_gap_cli_main


WORKFLOW_ID = "wf_7f2902f3c8c6"
BR032_CHECKER_NODE_ID = "node_backlog_followup_br_032_m3_checker_gate"
BR031_NODE_ID = "node_backlog_followup_br_031_m3_frontend_auth_nav"
BR040_NODE_ID = "node_backlog_followup_br_040_m4_catalog_search_availability"
BR041_NODE_ID = "node_backlog_followup_br_041_m4_isbn_remove_inventory"


def _manifest(db_path: Path, *, status: str = "READY") -> ReplayImportManifest:
    return ReplayImportManifest(
        status=status,
        manifest_version="replay-import-manifest.v1",
        input_db_path=str(db_path),
        artifact_root=str(db_path.parent / "artifacts"),
        log_refs=[],
        input_hashes={"event_log_hash": "fixture-event-log"},
        schema={"app_schema_version": "fixture"},
        event_range={"start_sequence_no": 1, "end_sequence_no": 20000},
        event_count=20000,
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
            f"evt_{sequence_no:05d}",
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


def _insert_artifact(
    connection: sqlite3.Connection,
    *,
    artifact_ref: str,
    ticket_id: str,
    node_id: str,
    logical_path: str,
    kind: str = "JSON",
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
            logical_path,
            kind,
            "application/json",
            "MATERIALIZED",
            "ACTIVE",
            logical_path,
            f"hash-{artifact_ref}",
            42,
            "DELIVERABLE_EVIDENCE",
            "LOCAL_FILE",
            None,
            "2026-04-29T15:00:00+08:00",
        ),
    )


def _insert_process_asset(
    connection: sqlite3.Connection,
    *,
    process_asset_ref: str,
    producer_ticket_id: str,
    producer_node_id: str,
    process_asset_kind: str,
    summary: str,
    metadata: dict[str, Any] | None = None,
) -> None:
    connection.execute(
        """
        INSERT INTO process_asset_index (
            process_asset_ref,
            canonical_ref,
            version_int,
            supersedes_ref,
            process_asset_kind,
            workflow_id,
            producer_ticket_id,
            producer_node_id,
            graph_version,
            content_hash,
            visibility_status,
            linked_process_asset_refs_json,
            summary,
            consumable_by_json,
            source_metadata_json,
            updated_at,
            version
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            process_asset_ref,
            process_asset_ref,
            1,
            None,
            process_asset_kind,
            WORKFLOW_ID,
            producer_ticket_id,
            producer_node_id,
            "gv_fixture",
            f"hash-{process_asset_ref}",
            "ACTIVE",
            "[]",
            summary,
            "[]",
            json.dumps(metadata or {}, sort_keys=True),
            "2026-04-29T15:00:00+08:00",
            1,
        ),
    )


def _create_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "replay.db"
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            CREATE TABLE events (
                sequence_no INTEGER PRIMARY KEY,
                event_id TEXT NOT NULL,
                workflow_id TEXT,
                event_type TEXT NOT NULL,
                actor_type TEXT NOT NULL,
                actor_id TEXT NOT NULL,
                occurred_at TEXT NOT NULL,
                idempotency_key TEXT NOT NULL,
                causation_id TEXT,
                correlation_id TEXT,
                payload_json TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE artifact_index (
                artifact_ref TEXT PRIMARY KEY,
                workflow_id TEXT NOT NULL,
                ticket_id TEXT NOT NULL,
                node_id TEXT NOT NULL,
                logical_path TEXT NOT NULL,
                kind TEXT NOT NULL,
                media_type TEXT,
                materialization_status TEXT NOT NULL,
                lifecycle_status TEXT NOT NULL,
                storage_relpath TEXT,
                content_hash TEXT,
                size_bytes INTEGER,
                retention_class TEXT NOT NULL,
                storage_backend TEXT,
                storage_object_key TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE process_asset_index (
                process_asset_ref TEXT PRIMARY KEY,
                canonical_ref TEXT NOT NULL,
                version_int INTEGER,
                supersedes_ref TEXT,
                process_asset_kind TEXT NOT NULL,
                workflow_id TEXT,
                producer_ticket_id TEXT,
                producer_node_id TEXT,
                graph_version TEXT,
                content_hash TEXT,
                visibility_status TEXT NOT NULL,
                linked_process_asset_refs_json TEXT NOT NULL,
                summary TEXT,
                consumable_by_json TEXT NOT NULL,
                source_metadata_json TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                version INTEGER NOT NULL
            )
            """
        )
    return db_path


def _seed_br032(connection: sqlite3.Connection) -> None:
    backend_refs = [
        "art://workspace/tkt_43324c290a3e/source/5-10-project%2Fsrc%2Fbackend%2Fauth%2FauthModule.js",
        "art://workspace/tkt_43324c290a3e/tests/1-20-evidence%2Ftests%2Ftkt_43324c290a3e%2Fattempt-1%2Fbr-030-m3-auth-rbac-audit-attempt-1.log",
    ]
    old_frontend_refs = [
        "art://workspace/tkt_d9e52680a9c5/source/4-10-project%2Fsrc%2Ffrontend%2Fsrc%2Fapi%2Fauth.ts",
    ]
    fixed_frontend_refs = [
        "art://workspace/tkt_c247833b2c60/source/2-10-project%2Fsrc%2Ffrontend%2Fsrc%2Fapi%2Fauth.ts",
        "art://workspace/tkt_c247833b2c60/tests/1-20-evidence%2Ftests%2Ftkt_c247833b2c60%2Fattempt-1%2Fbr-031-auth-contract-smoke-attempt-1.log",
    ]
    for ref in [*backend_refs, *old_frontend_refs, *fixed_frontend_refs]:
        ticket_id = "tkt_43324c290a3e"
        node_id = "node_backlog_followup_br_030_m3_auth_rbac_audit_backend"
        if "tkt_d9e52680a9c5" in ref:
            ticket_id = "tkt_d9e52680a9c5"
            node_id = BR031_NODE_ID
        if "tkt_c247833b2c60" in ref:
            ticket_id = "tkt_c247833b2c60"
            node_id = BR031_NODE_ID
        _insert_artifact(
            connection,
            artifact_ref=ref,
            ticket_id=ticket_id,
            node_id=node_id,
            logical_path=ref.rsplit("/", 1)[-1],
            kind="TEXT",
        )
    report_ref = "art://runtime/tkt_bc0404503ec8/delivery-check-report.json"
    _insert_artifact(
        connection,
        artifact_ref=report_ref,
        ticket_id="tkt_bc0404503ec8",
        node_id=BR032_CHECKER_NODE_ID,
        logical_path="reports/check/tkt_bc0404503ec8/delivery-check-report.json",
    )
    _insert_process_asset(
        connection,
        process_asset_ref="pa://artifact/art%3A%2F%2Fruntime%2Ftkt_bc0404503ec8%2Fdelivery-check-report.json@1",
        producer_ticket_id="tkt_bc0404503ec8",
        producer_node_id=BR032_CHECKER_NODE_ID,
        process_asset_kind="ARTIFACT",
        summary=(
            "FAIL: BR032-F06 remains blocking. Backend returns wrapped auth payloads "
            "while frontend consumes unwrapped token/user fields."
        ),
        metadata={"artifact_ref": report_ref},
    )
    _insert_event(
        connection,
        5913,
        "TICKET_CREATED",
        {
            "workflow_id": WORKFLOW_ID,
            "ticket_id": "tkt_bc0404503ec8",
            "node_id": BR032_CHECKER_NODE_ID,
            "input_artifact_refs": [*backend_refs, *old_frontend_refs],
        },
    )
    _insert_event(
        connection,
        5934,
        "TICKET_COMPLETED",
        {
            "workflow_id": WORKFLOW_ID,
            "ticket_id": "tkt_bc0404503ec8",
            "node_id": BR032_CHECKER_NODE_ID,
            "artifact_refs": [report_ref],
        },
    )
    _insert_event(
        connection,
        5960,
        "TICKET_COMPLETED",
        {
            "workflow_id": WORKFLOW_ID,
            "ticket_id": "tkt_9be6344dedde",
            "node_id": BR032_CHECKER_NODE_ID,
            "review_status": "APPROVED_WITH_NOTES",
        },
    )
    _insert_event(
        connection,
        6134,
        "TICKET_COMPLETED",
        {
            "workflow_id": WORKFLOW_ID,
            "ticket_id": "tkt_c247833b2c60",
            "node_id": BR031_NODE_ID,
            "artifact_refs": fixed_frontend_refs,
        },
    )
    _insert_event(
        connection,
        6299,
        "TICKET_COMPLETED",
        {
            "workflow_id": WORKFLOW_ID,
            "ticket_id": "tkt_1b2b27220047",
            "node_id": BR032_CHECKER_NODE_ID,
            "review_status": "APPROVED_WITH_NOTES",
        },
    )


def _seed_placeholder_case(
    connection: sqlite3.Connection,
    *,
    ticket_id: str,
    node_id: str,
    sequence_start: int,
) -> None:
    source_ref = f"art://workspace/{ticket_id}/source.py"
    test_ref = f"art://workspace/{ticket_id}/test-report.json"
    source_pa = f"pa://source-code-delivery/{ticket_id}@1"
    evidence_pa = f"pa://evidence-pack/{ticket_id}@1"
    _insert_artifact(
        connection,
        artifact_ref=source_ref,
        ticket_id=ticket_id,
        node_id=node_id,
        logical_path=f"10-project/src/{ticket_id}.py",
        kind="TEXT",
    )
    _insert_artifact(
        connection,
        artifact_ref=test_ref,
        ticket_id=ticket_id,
        node_id=node_id,
        logical_path=f"20-evidence/tests/{ticket_id}/attempt-1/test-report.json",
    )
    _insert_process_asset(
        connection,
        process_asset_ref=source_pa,
        producer_ticket_id=ticket_id,
        producer_node_id=node_id,
        process_asset_kind="SOURCE_CODE_DELIVERY",
        summary=f"Source code delivery prepared for ticket {ticket_id}.",
        metadata={"verification_evidence_refs": [test_ref]},
    )
    _insert_process_asset(
        connection,
        process_asset_ref=evidence_pa,
        producer_ticket_id=ticket_id,
        producer_node_id=node_id,
        process_asset_kind="EVIDENCE_PACK",
        summary=f"Evidence pack for {ticket_id}",
        metadata={
            "source_delivery_ref": source_pa,
            "ticket_id": ticket_id,
            "verification_evidence_refs": [test_ref],
            "verification_runs": [
                {
                    "artifact_ref": test_ref,
                    "command": "pytest tests -q",
                    "discovered_count": 1,
                    "exit_code": 0,
                    "passed_count": 1,
                    "status": "passed",
                    "stdout": "collected 1 item\n\n1 passed in 0.12s\n",
                }
            ],
        },
    )
    _insert_event(
        connection,
        sequence_start,
        "TICKET_CREATED",
        {
            "workflow_id": WORKFLOW_ID,
            "ticket_id": ticket_id,
            "node_id": node_id,
            "input_artifact_refs": [],
        },
    )
    _insert_event(
        connection,
        sequence_start + 54,
        "TICKET_COMPLETED",
        {
            "workflow_id": WORKFLOW_ID,
            "ticket_id": ticket_id,
            "node_id": node_id,
            "artifact_refs": [
                source_ref,
                test_ref,
                f"art://workspace/{ticket_id}/git-commit.json",
            ],
        },
    )
    _insert_event(
        connection,
        sequence_start + 64,
        "TICKET_COMPLETED",
        {
            "workflow_id": WORKFLOW_ID,
            "ticket_id": f"checker_{ticket_id}",
            "node_id": node_id,
            "review_status": "APPROVED_WITH_NOTES",
        },
    )


def _create_contract_gap_db(tmp_path: Path) -> Path:
    db_path = _create_db(tmp_path)
    with sqlite3.connect(db_path) as connection:
        _seed_br032(connection)
        _seed_placeholder_case(
            connection,
            ticket_id="tkt_2252a7a1f92e",
            node_id=BR040_NODE_ID,
            sequence_start=11400,
        )
        _seed_placeholder_case(
            connection,
            ticket_id="tkt_5707c310bc6d",
            node_id=BR041_NODE_ID,
            sequence_start=9933,
        )
    return db_path


def _reason_codes(result) -> set[str]:
    return {str(item["reason_code"]) for item in result.diagnostics}


def test_br032_auth_mismatch_replay_routes_contract_gap_to_frontend_source(tmp_path: Path) -> None:
    db_path = _create_contract_gap_db(tmp_path)

    result = replay_contract_gap_case(
        manifest=_manifest(db_path),
        replay_db_path=db_path,
        case_id=BR032_AUTH_MISMATCH_CASE_ID,
    )

    assert result.status == "READY"
    assert result.br_id == "BR-032"
    assert result.issue_classification == "contract gap replay evidence"
    assert result.contract_gate["allowed"] is False
    assert result.contract_gate["review_status"] == "APPROVED_WITH_NOTES"
    assert result.contract_gate["failed_delivery_report"] is True
    assert result.contract_gate["requires_convergence_policy"] is True
    assert result.contract_gate["reason_code"] == "convergence_policy_required"
    assert result.graph_terminal_override_used is False
    assert result.rework_incident_outcome["outcome"] == "rework_requested"
    assert result.rework_target["producer_ticket_id"] == "tkt_c247833b2c60"
    assert result.rework_target["producer_node_ref"] == BR031_NODE_ID
    assert result.rework_target["source_surface_ref"] == "surface.br032.frontend_auth_contract"
    assert result.contract_findings[0]["finding_ref"] == "BR032-F06"
    assert result.contract_findings[0]["blocking"] is True
    assert result.evidence_refs["checker_report_refs"] == [
        "art://runtime/tkt_bc0404503ec8/delivery-check-report.json"
    ]
    assert "approved_with_notes_not_contract_satisfaction" in _reason_codes(result)


def test_br040_placeholder_delivery_replay_blocks_placeholder_and_targets_maker(tmp_path: Path) -> None:
    db_path = _create_contract_gap_db(tmp_path)

    result = replay_contract_gap_case(
        manifest=_manifest(db_path),
        replay_db_path=db_path,
        case_id=BR040_PLACEHOLDER_DELIVERY_CASE_ID,
    )

    assert result.status == "READY"
    assert result.br_id == "BR-040"
    assert result.contract_gate["allowed"] is False
    assert result.contract_gate["failed_delivery_report"] is True
    assert result.contract_gate["requires_convergence_policy"] is True
    assert result.contract_gate["reason_code"] == "convergence_policy_required"
    assert result.rework_target["producer_ticket_id"] == "tkt_2252a7a1f92e"
    assert result.rework_target["producer_node_ref"] == BR040_NODE_ID
    assert result.evidence_refs["placeholder_source_refs"] == [
        "art://workspace/tkt_2252a7a1f92e/source.py"
    ]
    assert result.evidence_refs["placeholder_test_refs"] == [
        "art://workspace/tkt_2252a7a1f92e/test-report.json"
    ]
    assert result.contract_findings[0]["reason_code"] == "invalid_evidence_for_contract"
    assert "PLACEHOLDER" in result.contract_findings[0]["metadata"]["invalid_statuses"]
    assert result.evidence_refs["generic_test_commands"] == ["pytest tests -q"]
    assert "placeholder_delivery_blocked" in _reason_codes(result)
    assert "APPROVED_WITH_NOTES" not in str(result.rework_target)


def test_br041_placeholder_delivery_replay_blocks_placeholder_and_targets_maker(tmp_path: Path) -> None:
    db_path = _create_contract_gap_db(tmp_path)

    result = replay_contract_gap_case(
        manifest=_manifest(db_path),
        replay_db_path=db_path,
        case_id=BR041_PLACEHOLDER_DELIVERY_CASE_ID,
    )

    assert result.status == "READY"
    assert result.br_id == "BR-041"
    assert result.contract_gate["allowed"] is False
    assert result.contract_gate["failed_delivery_report"] is True
    assert result.contract_gate["requires_convergence_policy"] is True
    assert result.contract_gate["reason_code"] == "convergence_policy_required"
    assert result.rework_target["producer_ticket_id"] == "tkt_5707c310bc6d"
    assert result.rework_target["producer_node_ref"] == BR041_NODE_ID
    assert result.evidence_refs["source_process_asset_refs"] == [
        "pa://source-code-delivery/tkt_5707c310bc6d@1"
    ]
    assert result.evidence_refs["evidence_pack_refs"] == [
        "pa://evidence-pack/tkt_5707c310bc6d@1"
    ]
    assert result.rework_incident_outcome["reason_code"] == "progression.rework.deliverable_contract_gap"
    assert result.evidence_refs["generic_test_commands"] == ["pytest tests -q"]
    assert "placeholder_delivery_blocked" in _reason_codes(result)


def test_contract_gap_replay_fails_closed_when_manifest_is_not_ready(tmp_path: Path) -> None:
    db_path = _create_contract_gap_db(tmp_path)

    result = replay_contract_gap_case(
        manifest=_manifest(db_path, status="FAILED"),
        replay_db_path=db_path,
        case_id=BR040_PLACEHOLDER_DELIVERY_CASE_ID,
    )

    assert result.status == "FAILED"
    assert result.issue_classification == "replay/import issue"
    assert "manifest_not_ready" in _reason_codes(result)


def test_contract_gap_replay_fails_closed_when_replay_db_is_missing(tmp_path: Path) -> None:
    missing_db = tmp_path / "missing.db"

    result = replay_contract_gap_case(
        manifest=_manifest(missing_db),
        replay_db_path=missing_db,
        case_id=BR041_PLACEHOLDER_DELIVERY_CASE_ID,
    )

    assert result.status == "FAILED"
    assert result.issue_classification == "replay/import issue"
    assert "replay_db_missing" in _reason_codes(result)


def test_contract_gap_cli_fails_closed_when_manifest_is_missing(tmp_path: Path) -> None:
    db_path = _create_contract_gap_db(tmp_path)
    out_path = tmp_path / "case-out" / "br040.json"

    exit_code = replay_contract_gap_cli_main(
        [
            "--manifest",
            str(tmp_path / "missing-manifest.json"),
            "--replay-db",
            str(db_path),
            "--case-id",
            BR040_PLACEHOLDER_DELIVERY_CASE_ID,
            "--case-out",
            str(out_path),
        ]
    )

    result = json.loads(out_path.read_text(encoding="utf-8"))
    assert exit_code == 2
    assert result["status"] == "FAILED"
    assert result["issue_classification"] == "replay/import issue"
    assert "manifest_missing" in {item["reason_code"] for item in result["diagnostics"]}
