from __future__ import annotations

import json
import hashlib
import sqlite3
from datetime import datetime
from pathlib import Path

import pytest

from app.core.artifact_store import ArtifactStore
from app.core.constants import EVENT_TICKET_CREATED, EVENT_WORKFLOW_CREATED
from app.core.replay_import import (
    REPLAY_IMPORT_MANIFEST_VERSION,
    build_replay_import_manifest,
    import_replay_bundle,
)
from app.db.repository import ControlPlaneRepository


def _create_replay_source(
    tmp_path: Path,
    *,
    source_projection_status: str = "STALE_SOURCE",
    duplicate_storage_relpath: bool = False,
) -> tuple[Path, Path, Path]:
    source_root = tmp_path / "source"
    artifact_root = source_root / "artifacts"
    artifact_root.mkdir(parents=True)
    (artifact_root / "reports").mkdir()
    artifact_file = artifact_root / "reports" / "note.txt"
    artifact_content = "hello replay import"
    artifact_file.write_text(artifact_content, encoding="utf-8")
    artifact_hash = hashlib.sha256(artifact_content.encode("utf-8")).hexdigest()
    stale_artifact_hash = hashlib.sha256(b"old replay import").hexdigest()
    (artifact_root / "._reports").write_text("apple metadata", encoding="utf-8")
    (artifact_root / "PaxHeader").mkdir()
    (artifact_root / "PaxHeader" / "reports").write_text("pax metadata", encoding="utf-8")
    (artifact_root / "unregistered.txt").write_text("not registered", encoding="utf-8")

    log_ref = source_root / "run_report.json"
    log_ref.write_text('{"completion_mode":"fixture"}\n', encoding="utf-8")

    db_path = source_root / "boardroom_os.db"
    repository = ControlPlaneRepository(db_path, 1000, artifact_store=ArtifactStore(artifact_root))
    repository.initialize()
    with repository.transaction() as connection:
        connection.execute("DELETE FROM events")
        connection.execute("DELETE FROM artifact_index")
        connection.execute("DELETE FROM workflow_projection")
        rows = [
            (
                1,
                "evt_replay_import_wf",
                "wf_replay_import",
                EVENT_WORKFLOW_CREATED,
                "fixture",
                "fixture",
                "2026-05-04T10:00:00+08:00",
                "source:evt_replay_import_wf",
                None,
                "wf_replay_import",
                json.dumps(
                    {
                        "workflow_id": "wf_replay_import",
                        "title": "Replay import",
                        "north_star_goal": "Replay import",
                        "budget_cap": 100,
                        "deadline_at": None,
                    },
                    sort_keys=True,
                ),
            ),
            (
                2,
                "evt_replay_import_ticket",
                "wf_replay_import",
                EVENT_TICKET_CREATED,
                "fixture",
                "fixture",
                "2026-05-04T10:01:00+08:00",
                "source:evt_replay_import_ticket",
                None,
                "wf_replay_import",
                json.dumps(
                    {
                        "ticket_id": "tkt_replay_import",
                        "node_id": "node_replay_import",
                        "workflow_id": "wf_replay_import",
                        "priority": "normal",
                        "retry_budget": 1,
                        "timeout_sla_sec": 1800,
                        "graph_contract": {
                            "lane_kind": "execution",
                        },
                    },
                    sort_keys=True,
                ),
            ),
        ]
        connection.executemany(
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
            rows,
        )
        connection.execute(
            """
            INSERT INTO workflow_projection (
                workflow_id,
                title,
                north_star_goal,
                workflow_profile,
                tenant_id,
                workspace_id,
                current_stage,
                status,
                budget_total,
                budget_used,
                board_gate_state,
                deadline_at,
                started_at,
                updated_at,
                version
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "wf_replay_import",
                "Replay import",
                "Replay import",
                "STANDARD",
                "default",
                "default",
                "init",
                source_projection_status,
                100,
                0,
                "OPEN",
                None,
                "2026-05-04T10:00:00+08:00",
                "2026-05-04T10:00:00+08:00",
                999,
            ),
        )
        repository.save_artifact_record(
            connection,
            artifact_ref="art://runtime/tkt_replay_import/note.txt",
            workflow_id="wf_replay_import",
            ticket_id="tkt_replay_import",
            node_id="node_replay_import",
            logical_path="reports/note.txt",
            kind="TEXT",
            media_type="text/plain",
            materialization_status="MATERIALIZED",
            lifecycle_status="ACTIVE",
            storage_relpath="reports/note.txt",
            content_hash=artifact_hash,
            size_bytes=len(artifact_content.encode("utf-8")),
            retention_class="PERSISTENT",
            expires_at=None,
            deleted_at=None,
            deleted_by=None,
            delete_reason=None,
            created_at=datetime.fromisoformat("2026-05-04T10:02:00+08:00"),
        )
        if duplicate_storage_relpath:
            repository.save_artifact_record(
                connection,
                artifact_ref="art://runtime/tkt_replay_import/old-note.txt",
                workflow_id="wf_replay_import",
                ticket_id="tkt_replay_import",
                node_id="node_replay_import",
                logical_path="reports/note.txt",
                kind="TEXT",
                media_type="text/plain",
                materialization_status="MATERIALIZED",
                lifecycle_status="ACTIVE",
                storage_relpath="reports/note.txt",
                content_hash=stale_artifact_hash,
                size_bytes=len(b"old replay import"),
                retention_class="PERSISTENT",
                expires_at=None,
                deleted_at=None,
                deleted_by=None,
                delete_reason=None,
                created_at=datetime.fromisoformat("2026-05-04T10:01:30+08:00"),
            )
    return db_path, artifact_root, log_ref


def test_replay_import_manifest_is_stable_across_repeated_imports(tmp_path):
    db_path, artifact_root, log_ref = _create_replay_source(tmp_path)

    first = import_replay_bundle(
        source_db_path=db_path,
        artifact_root=artifact_root,
        log_refs=[log_ref],
        target_db_path=tmp_path / "target-a" / "replay.db",
    )
    second = import_replay_bundle(
        source_db_path=db_path,
        artifact_root=artifact_root,
        log_refs=[log_ref],
        target_db_path=tmp_path / "target-b" / "replay.db",
    )

    assert first.status == "READY"
    assert first.manifest_version == REPLAY_IMPORT_MANIFEST_VERSION
    assert first.event_range == {"start_sequence_no": 1, "end_sequence_no": 2}
    assert first.event_count == 2
    assert first.artifact_count == 1
    assert first.local_file_artifact_count == 1
    assert first.inline_db_artifact_count == 0
    assert first.workflow_ids == ["wf_replay_import"]
    assert first.idempotency_key == second.idempotency_key
    assert first.manifest_hash == second.manifest_hash
    assert first.model_dump(mode="json") == second.model_dump(mode="json")


def test_replay_import_idempotency_key_is_content_derived(tmp_path):
    db_path, artifact_root, log_ref = _create_replay_source(tmp_path)
    alternate_log = tmp_path / "renamed-run-report.json"
    alternate_log.write_bytes(log_ref.read_bytes())

    first = build_replay_import_manifest(
        source_db_path=db_path,
        artifact_root=artifact_root,
        log_refs=[log_ref],
    )
    second = build_replay_import_manifest(
        source_db_path=db_path,
        artifact_root=artifact_root,
        log_refs=[alternate_log],
    )

    assert first.status == "READY"
    assert second.status == "READY"
    assert first.idempotency_key == second.idempotency_key
    assert first.manifest_hash != second.manifest_hash


def test_replay_import_reports_external_noise_and_projection_mismatch(tmp_path):
    db_path, artifact_root, log_ref = _create_replay_source(tmp_path)

    manifest = import_replay_bundle(
        source_db_path=db_path,
        artifact_root=artifact_root,
        log_refs=[log_ref],
        target_db_path=tmp_path / "target" / "replay.db",
    )

    reason_codes = {item["reason_code"] for item in manifest.import_diagnostics}
    assert manifest.status == "READY"
    assert "artifact_tree_noise_detected" in reason_codes
    assert "unregistered_artifact_files_detected" in reason_codes
    assert "source_projection_mismatch" in reason_codes


def test_replay_import_allows_mutable_storage_relpath_when_latest_file_matches(tmp_path):
    db_path, artifact_root, log_ref = _create_replay_source(tmp_path, duplicate_storage_relpath=True)

    manifest = import_replay_bundle(
        source_db_path=db_path,
        artifact_root=artifact_root,
        log_refs=[log_ref],
        target_db_path=tmp_path / "target" / "replay.db",
    )

    reason_codes = {item["reason_code"] for item in manifest.import_diagnostics}
    assert manifest.status == "READY"
    assert manifest.artifact_count == 2
    assert "mutable_storage_relpath_detected" in reason_codes
    assert "registered_artifact_hash_mismatch" not in reason_codes


def test_replay_import_fails_closed_when_required_inputs_are_missing(tmp_path):
    db_path, artifact_root, log_ref = _create_replay_source(tmp_path)

    missing_db = build_replay_import_manifest(
        source_db_path=tmp_path / "missing.db",
        artifact_root=artifact_root,
        log_refs=[log_ref],
    )
    missing_artifacts = build_replay_import_manifest(
        source_db_path=db_path,
        artifact_root=tmp_path / "missing-artifacts",
        log_refs=[log_ref],
    )
    missing_log = build_replay_import_manifest(
        source_db_path=db_path,
        artifact_root=artifact_root,
        log_refs=[tmp_path / "missing-log.json"],
    )

    assert missing_db.status == "FAILED"
    assert missing_db.import_diagnostics[0]["reason_code"] == "missing_replay_db"
    assert missing_artifacts.status == "FAILED"
    assert missing_artifacts.import_diagnostics[0]["reason_code"] == "missing_artifact_root"
    assert missing_log.status == "FAILED"
    assert missing_log.import_diagnostics[0]["reason_code"] == "missing_log_ref"


def test_replay_import_fails_closed_on_hash_and_schema_mismatch(tmp_path):
    db_path, artifact_root, log_ref = _create_replay_source(tmp_path)
    expected = build_replay_import_manifest(
        source_db_path=db_path,
        artifact_root=artifact_root,
        log_refs=[log_ref],
    )

    tampered = artifact_root / "reports" / "note.txt"
    tampered.write_text("tampered", encoding="utf-8")
    hash_mismatch = build_replay_import_manifest(
        source_db_path=db_path,
        artifact_root=artifact_root,
        log_refs=[log_ref],
        expected_manifest=expected,
    )
    schema_mismatch = build_replay_import_manifest(
        source_db_path=db_path,
        artifact_root=artifact_root,
        log_refs=[log_ref],
        expected_sqlite_schema_version=999999,
    )

    assert hash_mismatch.status == "FAILED"
    assert hash_mismatch.import_diagnostics[0]["reason_code"] == "expected_manifest_hash_mismatch"
    assert {item["reason_code"] for item in hash_mismatch.import_diagnostics} >= {
        "expected_manifest_hash_mismatch",
        "registered_artifact_hash_mismatch",
    }
    assert schema_mismatch.status == "FAILED"
    assert schema_mismatch.import_diagnostics[0]["reason_code"] == "sqlite_schema_version_mismatch"


def test_replay_import_rebuilds_projection_from_events_without_repair(tmp_path, monkeypatch):
    db_path, artifact_root, log_ref = _create_replay_source(tmp_path)

    def _blocked_refresh(*_args, **_kwargs):  # pragma: no cover - should never run
        raise AssertionError("projection repair path must not run")

    monkeypatch.setattr(ControlPlaneRepository, "refresh_projections", _blocked_refresh)
    manifest = import_replay_bundle(
        source_db_path=db_path,
        artifact_root=artifact_root,
        log_refs=[log_ref],
        target_db_path=tmp_path / "target" / "replay.db",
    )

    with sqlite3.connect(tmp_path / "target" / "replay.db") as connection:
        connection.row_factory = sqlite3.Row
        event_count = connection.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        workflow = connection.execute(
            "SELECT * FROM workflow_projection WHERE workflow_id = ?",
            ("wf_replay_import",),
        ).fetchone()

    assert manifest.status == "READY"
    assert workflow is not None
    assert workflow["status"] != "STALE_SOURCE"
    assert workflow["version"] == 2
    assert event_count == 2
