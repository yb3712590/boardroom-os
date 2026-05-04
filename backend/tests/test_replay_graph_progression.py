from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from app.contracts.replay import ReplayImportManifest
from app.core.replay_graph_progression import (
    CANCELLED_SUPERSEDED_CASE_ID,
    LATE_PROVIDER_POINTER_CASE_ID,
    MISSING_EXPLICIT_POINTER_CASE_ID,
    ORPHAN_PENDING_CASE_ID,
    replay_graph_progression_case,
)
from app.replay_graph_progression_cli import main as replay_graph_progression_cli_main


WORKFLOW_ID = "wf_7f2902f3c8c6"
BR031_NODE_ID = "node_backlog_followup_br_031_m3_frontend_auth_nav"
BR032_NODE_ID = "node_backlog_followup_br_032_m3_checker_gate"
BR041_NODE_ID = "node_backlog_followup_br_041_m4_isbn_remove_inventory"
BR060_NODE_ID = "node_backlog_followup_br_060_m6_circulation_transactions"


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
            json.dumps({"workflow_id": WORKFLOW_ID, **payload}, sort_keys=True),
        ),
    )


def _seed_cancelled_superseded(connection: sqlite3.Connection) -> None:
    _insert_event(
        connection,
        5960,
        "TICKET_COMPLETED",
        {"ticket_id": "tkt_9be6344dedde", "node_id": BR032_NODE_ID},
    )
    _insert_event(
        connection,
        5961,
        "TICKET_CREATED",
        {"ticket_id": "tkt_9b8ea42b3add", "node_id": BR032_NODE_ID},
    )
    _insert_event(
        connection,
        5964,
        "TICKET_FAILED",
        {"ticket_id": "tkt_9b8ea42b3add", "node_id": BR032_NODE_ID},
    )
    _insert_event(
        connection,
        5966,
        "TICKET_CREATED",
        {"ticket_id": "tkt_ade5951f10ec", "node_id": BR032_NODE_ID},
    )
    _insert_event(
        connection,
        5967,
        "TICKET_CANCELLED",
        {
            "ticket_id": "tkt_ade5951f10ec",
            "node_id": BR032_NODE_ID,
            "reason": "Superseded by BR-031 auth contract implementation repair.",
        },
    )
    _insert_event(
        connection,
        5971,
        "TICKET_CREATED",
        {"ticket_id": "tkt_2262491ff9ae", "node_id": BR031_NODE_ID},
    )
    _insert_event(
        connection,
        5975,
        "TICKET_CANCELLED",
        {
            "ticket_id": "tkt_2262491ff9ae",
            "node_id": BR031_NODE_ID,
            "reason": "Superseded by same BR-031 contract fix without worker exclusion.",
        },
    )
    _insert_event(
        connection,
        5977,
        "TICKET_CREATED",
        {"ticket_id": "tkt_c247833b2c60", "node_id": BR031_NODE_ID},
    )
    _insert_event(
        connection,
        6134,
        "TICKET_COMPLETED",
        {"ticket_id": "tkt_c247833b2c60", "node_id": BR031_NODE_ID},
    )
    _insert_event(
        connection,
        6135,
        "TICKET_CREATED",
        {"ticket_id": "tkt_f00a95436db3", "node_id": f"{BR031_NODE_ID}::review"},
    )
    _insert_event(
        connection,
        6174,
        "TICKET_COMPLETED",
        {"ticket_id": "tkt_f00a95436db3", "node_id": f"{BR031_NODE_ID}::review"},
    )
    _insert_event(
        connection,
        6177,
        "TICKET_CREATED",
        {"ticket_id": "tkt_e2b36aef19e9", "node_id": BR032_NODE_ID},
    )
    _insert_event(
        connection,
        6273,
        "TICKET_CANCELLED",
        {
            "ticket_id": "tkt_e2b36aef19e9",
            "node_id": BR032_NODE_ID,
            "reason": "Superseded by BR-032 check ticket rebuilt with latest BR-031 process assets.",
        },
    )
    _insert_event(
        connection,
        6276,
        "TICKET_CREATED",
        {"ticket_id": "tkt_2e4ac9dd357e", "node_id": BR032_NODE_ID},
    )
    _insert_event(
        connection,
        6291,
        "TICKET_COMPLETED",
        {"ticket_id": "tkt_2e4ac9dd357e", "node_id": BR032_NODE_ID},
    )
    _insert_event(
        connection,
        6292,
        "TICKET_CREATED",
        {"ticket_id": "tkt_1b2b27220047", "node_id": f"{BR032_NODE_ID}::review"},
    )
    _insert_event(
        connection,
        6299,
        "TICKET_COMPLETED",
        {"ticket_id": "tkt_1b2b27220047", "node_id": f"{BR032_NODE_ID}::review"},
    )


def _seed_late_provider(connection: sqlite3.Connection) -> None:
    _insert_event(
        connection,
        9969,
        "TICKET_CREATED",
        {"ticket_id": "tkt_0c616378c9ac", "node_id": BR041_NODE_ID},
    )
    _insert_event(
        connection,
        9974,
        "PROVIDER_ATTEMPT_HEARTBEAT_RECORDED",
        {
            "ticket_id": "tkt_30c7a10979ae",
            "node_id": BR041_NODE_ID,
            "attempt_id": f"attempt:{WORKFLOW_ID}:tkt_30c7a10979ae:prov:1",
        },
    )
    _insert_event(
        connection,
        9995,
        "PROVIDER_ATTEMPT_FINISHED",
        {
            "ticket_id": "tkt_0c616378c9ac",
            "node_id": BR041_NODE_ID,
            "attempt_id": f"attempt:{WORKFLOW_ID}:tkt_0c616378c9ac:prov:1",
            "status": "FAILED",
            "failure_kind": "PROVIDER_BAD_RESPONSE",
        },
    )
    _insert_event(
        connection,
        9996,
        "TICKET_FAILED",
        {
            "ticket_id": "tkt_0c616378c9ac",
            "node_id": BR041_NODE_ID,
            "failure_kind": "PROVIDER_BAD_RESPONSE",
        },
    )
    _insert_event(
        connection,
        10008,
        "TICKET_CREATED",
        {"ticket_id": "tkt_2b58304dccb9", "node_id": BR041_NODE_ID},
    )
    _insert_event(
        connection,
        10016,
        "TICKET_COMPLETED",
        {"ticket_id": "tkt_2b58304dccb9", "node_id": BR041_NODE_ID},
    )


def _seed_orphan_pending(connection: sqlite3.Connection) -> None:
    _insert_event(
        connection,
        11792,
        "TICKET_CREATED",
        {"ticket_id": "tkt_f5c2cd110a2f", "node_id": BR060_NODE_ID},
    )
    _insert_event(
        connection,
        11796,
        "TICKET_CREATED",
        {"ticket_id": "tkt_37d97847a282", "node_id": BR060_NODE_ID},
    )
    _insert_event(
        connection,
        11797,
        "TICKET_CANCELLED",
        {
            "ticket_id": "tkt_f5c2cd110a2f",
            "node_id": BR060_NODE_ID,
            "reason": "Superseded by retry follow-up ticket tkt_f51adeb1beb7.",
        },
    )
    _insert_event(
        connection,
        11798,
        "TICKET_CREATED",
        {"ticket_id": "tkt_f51adeb1beb7", "node_id": BR060_NODE_ID},
    )
    _insert_event(
        connection,
        11834,
        "TICKET_TIMED_OUT",
        {"ticket_id": "tkt_f51adeb1beb7", "node_id": BR060_NODE_ID},
    )
    _insert_event(
        connection,
        11863,
        "TICKET_CREATED",
        {"ticket_id": "tkt_262f159fc931", "node_id": BR060_NODE_ID},
    )
    _insert_event(
        connection,
        11864,
        "TICKET_CANCELLED",
        {
            "ticket_id": "tkt_37d97847a282",
            "node_id": BR060_NODE_ID,
            "reason": "Superseded by retry follow-up ticket tkt_5d8e536a14c2.",
        },
    )
    _insert_event(
        connection,
        11865,
        "TICKET_CREATED",
        {"ticket_id": "tkt_5d8e536a14c2", "node_id": BR060_NODE_ID},
    )
    _insert_event(
        connection,
        11895,
        "TICKET_COMPLETED",
        {"ticket_id": "tkt_5d8e536a14c2", "node_id": BR060_NODE_ID},
    )
    _insert_event(
        connection,
        11896,
        "TICKET_CREATED",
        {"ticket_id": "tkt_665d647e556a", "node_id": f"{BR060_NODE_ID}::review"},
    )
    _insert_event(
        connection,
        11903,
        "TICKET_COMPLETED",
        {"ticket_id": "tkt_665d647e556a", "node_id": f"{BR060_NODE_ID}::review"},
    )


def _create_graph_progression_db(tmp_path: Path) -> Path:
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
        _seed_cancelled_superseded(connection)
        _seed_late_provider(connection)
        _seed_orphan_pending(connection)
    return db_path


def _reason_codes(result) -> set[str]:
    return {str(item["reason_code"]) for item in result.diagnostics}


def test_orphan_pending_replay_does_not_block_graph_complete(tmp_path: Path) -> None:
    db_path = _create_graph_progression_db(tmp_path)

    result = replay_graph_progression_case(
        manifest=_manifest(db_path),
        replay_db_path=db_path,
        case_id=ORPHAN_PENDING_CASE_ID,
    )

    assert result.status == "READY"
    assert result.issue_classification == "graph progression replay evidence"
    assert result.event_range == {"start_sequence_no": 11791, "end_sequence_no": 11903}
    assert result.graph_pointer_summary["source_graph_version"] == "gv_11903"
    assert result.graph_pointer_summary["graph_complete"] is True
    assert result.graph_pointer_summary["stale_orphan_pending_refs"] == ["tkt_262f159fc931"]
    assert "tkt_262f159fc931" not in result.graph_pointer_summary["ready_ticket_ids"]
    assert "tkt_262f159fc931" not in result.graph_pointer_summary["current_ticket_ids_by_node_ref"].values()
    assert result.policy_proposal["metadata"]["reason_code"] == "progression.stale_orphan_pending_ignored"
    assert result.policy_proposal["metadata"]["source_graph_version"] == "gv_11903"
    assert result.policy_proposal["metadata"]["idempotency_key"].startswith(
        "progression:NO_ACTION:gv_11903:replay-graph-progression:"
    )
    assert result.policy_proposal["metadata"]["affected_node_refs"] == ["tkt_262f159fc931"]
    assert "orphan_pending_ignored" in _reason_codes(result)


def test_cancelled_superseded_replay_excludes_inactive_edges_and_readiness(tmp_path: Path) -> None:
    db_path = _create_graph_progression_db(tmp_path)

    result = replay_graph_progression_case(
        manifest=_manifest(db_path),
        replay_db_path=db_path,
        case_id=CANCELLED_SUPERSEDED_CASE_ID,
    )

    inactive_refs = {"tkt_ade5951f10ec", "tkt_2262491ff9ae", "tkt_e2b36aef19e9"}
    assert result.status == "READY"
    assert result.graph_pointer_summary["graph_complete"] is True
    assert result.graph_pointer_summary["source_graph_version"] == "gv_6299"
    assert result.graph_pointer_summary["current_ticket_ids_by_node_ref"] == {
        BR031_NODE_ID: "tkt_c247833b2c60",
        f"{BR031_NODE_ID}::review": "tkt_f00a95436db3",
        BR032_NODE_ID: "tkt_2e4ac9dd357e",
        f"{BR032_NODE_ID}::review": "tkt_1b2b27220047",
    }
    assert set(result.graph_pointer_summary["completed_ticket_ids"]) == {
        "tkt_c247833b2c60",
        "tkt_f00a95436db3",
        "tkt_2e4ac9dd357e",
        "tkt_1b2b27220047",
    }
    assert inactive_refs.isdisjoint(result.graph_pointer_summary["ready_ticket_ids"])
    assert inactive_refs.isdisjoint(result.graph_pointer_summary["completed_ticket_ids"])
    assert inactive_refs.isdisjoint(result.graph_pointer_summary["current_ticket_ids_by_node_ref"].values())
    assert inactive_refs.isdisjoint(
        {
            str(edge.get("source_ticket_id") or "")
            for edge in result.effective_edge_summary["effective_edges"]
        }
    )
    assert inactive_refs.isdisjoint(
        {
            str(edge.get("target_ticket_id") or "")
            for edge in result.effective_edge_summary["effective_edges"]
        }
    )
    assert result.effective_edge_summary["excluded_inactive_ticket_refs"] == sorted(inactive_refs)
    assert result.policy_proposal["metadata"]["reason_code"] == "progression.graph_complete_no_closeout_in_8b"
    assert "cancelled_superseded_edges_excluded" in _reason_codes(result)


def test_late_provider_replay_keeps_current_pointer_on_recovery_ticket(tmp_path: Path) -> None:
    db_path = _create_graph_progression_db(tmp_path)

    result = replay_graph_progression_case(
        manifest=_manifest(db_path),
        replay_db_path=db_path,
        case_id=LATE_PROVIDER_POINTER_CASE_ID,
    )

    assert result.status == "READY"
    assert result.graph_pointer_summary["current_ticket_ids_by_node_ref"] == {
        BR041_NODE_ID: "tkt_2b58304dccb9"
    }
    assert result.graph_pointer_summary["late_event_guard"]["guard_passed"] is True
    assert result.graph_pointer_summary["late_event_guard"]["current_pointer_ticket_id"] == "tkt_2b58304dccb9"
    assert result.graph_pointer_summary["late_event_guard"]["current_pointer_source"] == "case_range_terminal_events"
    assert result.graph_pointer_summary["timestamp_pointer_guess_used"] is False
    assert result.retry_recovery_outcome["timestamp_pointer_guess_used"] is False
    assert result.policy_proposal["metadata"]["source_graph_version"] == "gv_10016"
    assert "late_provider_output_ignored_for_current_pointer" in _reason_codes(result)


def test_missing_explicit_pointer_replay_opens_graph_reduction_incident(tmp_path: Path) -> None:
    db_path = _create_graph_progression_db(tmp_path)

    result = replay_graph_progression_case(
        manifest=_manifest(db_path),
        replay_db_path=db_path,
        case_id=MISSING_EXPLICIT_POINTER_CASE_ID,
    )

    assert result.status == "READY"
    assert result.graph_pointer_summary["graph_complete"] is False
    assert result.graph_pointer_summary["timestamp_pointer_guess_used"] is False
    assert result.graph_diagnostics[0]["issue_code"] == "graph.current_pointer.missing_explicit"
    assert result.policy_proposal["action_type"] == "INCIDENT"
    assert result.policy_proposal["metadata"]["reason_code"] == "progression.incident.graph_reduction_issue"
    assert result.policy_proposal["metadata"]["source_graph_version"] == "gv_11903"
    assert result.policy_proposal["metadata"]["affected_node_refs"] == [BR060_NODE_ID]
    assert "missing_explicit_pointer_incident" in _reason_codes(result)


def test_graph_progression_replay_fails_closed_for_manifest_and_db_errors(tmp_path: Path) -> None:
    db_path = _create_graph_progression_db(tmp_path)
    missing_db = tmp_path / "missing.db"

    not_ready = replay_graph_progression_case(
        manifest=_manifest(db_path, status="FAILED"),
        replay_db_path=db_path,
        case_id=ORPHAN_PENDING_CASE_ID,
    )
    missing = replay_graph_progression_case(
        manifest=_manifest(missing_db),
        replay_db_path=missing_db,
        case_id=ORPHAN_PENDING_CASE_ID,
    )
    unknown = replay_graph_progression_case(
        manifest=_manifest(db_path),
        replay_db_path=db_path,
        case_id="graph-progression-unknown",
    )

    assert not_ready.status == "FAILED"
    assert missing.status == "FAILED"
    assert unknown.status == "FAILED"
    assert not_ready.issue_classification == "replay/import issue"
    assert missing.issue_classification == "replay/import issue"
    assert unknown.issue_classification == "replay/import issue"
    assert "manifest_not_ready" in _reason_codes(not_ready)
    assert "replay_db_missing" in _reason_codes(missing)
    assert "replay_case_unknown" in _reason_codes(unknown)


def test_graph_progression_cli_fails_closed_when_manifest_is_missing(tmp_path: Path) -> None:
    db_path = _create_graph_progression_db(tmp_path)
    out_path = tmp_path / "case-out" / "orphan.json"

    exit_code = replay_graph_progression_cli_main(
        [
            "--manifest",
            str(tmp_path / "missing-manifest.json"),
            "--replay-db",
            str(db_path),
            "--case-id",
            ORPHAN_PENDING_CASE_ID,
            "--case-out",
            str(out_path),
        ]
    )

    result = json.loads(out_path.read_text(encoding="utf-8"))
    assert exit_code == 2
    assert result["status"] == "FAILED"
    assert result["issue_classification"] == "replay/import issue"
    assert "manifest_missing" in {item["reason_code"] for item in result["diagnostics"]}


def test_graph_progression_cli_fails_closed_when_replay_db_is_missing(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"
    missing_db = tmp_path / "missing.db"
    out_path = tmp_path / "case-out" / "missing-db.json"
    manifest_path.write_text(
        _manifest(missing_db).model_dump_json(indent=2),
        encoding="utf-8",
    )

    exit_code = replay_graph_progression_cli_main(
        [
            "--manifest",
            str(manifest_path),
            "--replay-db",
            str(missing_db),
            "--case-id",
            ORPHAN_PENDING_CASE_ID,
            "--case-out",
            str(out_path),
        ]
    )

    result = json.loads(out_path.read_text(encoding="utf-8"))
    assert exit_code == 2
    assert result["status"] == "FAILED"
    assert result["issue_classification"] == "replay/import issue"
    assert "replay_db_missing" in {item["reason_code"] for item in result["diagnostics"]}


def test_graph_progression_cli_fails_closed_for_unknown_case(tmp_path: Path) -> None:
    db_path = _create_graph_progression_db(tmp_path)
    manifest_path = tmp_path / "manifest.json"
    out_path = tmp_path / "case-out" / "unknown.json"
    manifest_path.write_text(
        _manifest(db_path).model_dump_json(indent=2),
        encoding="utf-8",
    )

    exit_code = replay_graph_progression_cli_main(
        [
            "--manifest",
            str(manifest_path),
            "--replay-db",
            str(db_path),
            "--case-id",
            "graph-progression-unknown",
            "--case-out",
            str(out_path),
        ]
    )

    result = json.loads(out_path.read_text(encoding="utf-8"))
    assert exit_code == 2
    assert result["status"] == "FAILED"
    assert result["issue_classification"] == "replay/import issue"
    assert "replay_case_unknown" in {item["reason_code"] for item in result["diagnostics"]}
