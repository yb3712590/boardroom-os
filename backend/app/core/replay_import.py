from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from app.contracts.replay import ReplayImportManifest
from app.core.artifact_store import ArtifactStore, STORAGE_BACKEND_LOCAL_FILE
from app.core.constants import SCHEMA_VERSION
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

REPLAY_IMPORT_MANIFEST_VERSION = "replay-import-manifest.v1"
REPLAY_IMPORT_ISSUE_CLASSIFICATION = "replay/import issue"

_REQUIRED_TABLE_COLUMNS = {
    "events": {
        "sequence_no",
        "event_id",
        "workflow_id",
        "event_type",
        "actor_type",
        "actor_id",
        "occurred_at",
        "idempotency_key",
        "causation_id",
        "correlation_id",
        "payload_json",
    },
    "artifact_index": {
        "artifact_ref",
        "workflow_id",
        "ticket_id",
        "node_id",
        "logical_path",
        "kind",
        "media_type",
        "materialization_status",
        "lifecycle_status",
        "storage_relpath",
        "content_hash",
        "size_bytes",
        "retention_class",
        "storage_backend",
        "storage_object_key",
        "created_at",
    },
    "process_asset_index": {
        "process_asset_ref",
        "canonical_ref",
        "process_asset_kind",
        "workflow_id",
        "producer_ticket_id",
        "producer_node_id",
        "version",
    },
}

_PROJECTION_TABLES = (
    "workflow_projection",
    "ticket_projection",
    "assignment_projection",
    "lease_projection",
    "node_projection",
    "runtime_node_projection",
    "execution_attempt_projection",
    "actor_projection",
    "employee_projection",
    "incident_projection",
    "process_asset_index",
    "planned_placeholder_projection",
)


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


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


def _diagnostic(reason_code: str, message: str, **details: Any) -> dict[str, Any]:
    return {
        "reason_code": reason_code,
        "classification": REPLAY_IMPORT_ISSUE_CLASSIFICATION,
        "message": message,
        **_json_safe(details),
    }


def _empty_manifest(
    *,
    source_db_path: Path,
    artifact_root: Path,
    log_refs: list[Path],
    diagnostics: list[dict[str, Any]],
    input_hashes: dict[str, Any] | None = None,
    schema: dict[str, Any] | None = None,
    event_range: dict[str, int] | None = None,
    event_count: int = 0,
    workflow_ids: list[str] | None = None,
    artifact_count: int = 0,
    local_file_artifact_count: int = 0,
    inline_db_artifact_count: int = 0,
) -> ReplayImportManifest:
    manifest_payload = {
        "status": "FAILED",
        "manifest_version": REPLAY_IMPORT_MANIFEST_VERSION,
        "input_db_path": str(source_db_path),
        "artifact_root": str(artifact_root),
        "log_refs": [str(path) for path in log_refs],
        "input_hashes": input_hashes or {},
        "schema": schema or {"app_schema_version": SCHEMA_VERSION},
        "event_range": event_range,
        "event_count": event_count,
        "workflow_ids": workflow_ids or [],
        "artifact_count": artifact_count,
        "local_file_artifact_count": local_file_artifact_count,
        "inline_db_artifact_count": inline_db_artifact_count,
        "import_diagnostics": diagnostics,
        "idempotency_key": "",
        "manifest_hash": "",
    }
    manifest_payload["idempotency_key"] = _build_idempotency_key(manifest_payload)
    manifest_payload["manifest_hash"] = _manifest_hash(manifest_payload)
    return ReplayImportManifest.model_validate(manifest_payload)


def _manifest_hash_payload(manifest: ReplayImportManifest | dict[str, Any]) -> dict[str, Any]:
    payload = manifest.model_dump(mode="json") if isinstance(manifest, ReplayImportManifest) else dict(manifest)
    payload.pop("manifest_hash", None)
    return payload


def _manifest_hash(manifest: ReplayImportManifest | dict[str, Any]) -> str:
    return _sha256(_manifest_hash_payload(manifest))


def _build_idempotency_key(payload: dict[str, Any]) -> str:
    input_hashes = dict(payload.get("input_hashes") or {})
    schema = dict(payload.get("schema") or {})
    log_hashes = dict(input_hashes.get("log_sha256s") or {})
    idempotency_payload = {
        "manifest_version": payload.get("manifest_version"),
        "db_sha256": input_hashes.get("db_sha256"),
        "artifact_tree_sha256": input_hashes.get("artifact_tree_sha256"),
        "registered_artifact_tree_sha256": input_hashes.get("registered_artifact_tree_sha256"),
        "log_sha256s": sorted(log_hashes.values()),
        "event_log_hash": input_hashes.get("event_log_hash"),
        "artifact_index_hash": input_hashes.get("artifact_index_hash"),
        "schema_hash": schema.get("required_table_column_hash"),
        "sqlite_schema_version": schema.get("sqlite_schema_version"),
        "event_count": payload.get("event_count"),
        "event_range": payload.get("event_range"),
        "artifact_count": payload.get("artifact_count"),
        "local_file_artifact_count": payload.get("local_file_artifact_count"),
        "inline_db_artifact_count": payload.get("inline_db_artifact_count"),
    }
    return f"replay-import:{_sha256(idempotency_payload)}"


def _connect_source_db(source_db_path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(f"file:{source_db_path.as_posix()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def _table_columns(connection: sqlite3.Connection, table_name: str) -> list[str]:
    return [str(row["name"]) for row in connection.execute(f"PRAGMA table_info({table_name})").fetchall()]


def _schema_facts(connection: sqlite3.Connection) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    diagnostics: list[dict[str, Any]] = []
    rows = connection.execute("SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name").fetchall()
    tables = [str(row["name"]) for row in rows]
    columns_by_table: dict[str, list[str]] = {}
    for table_name, required_columns in _REQUIRED_TABLE_COLUMNS.items():
        if table_name not in tables:
            diagnostics.append(
                _diagnostic(
                    "required_table_missing",
                    "Replay source DB is missing a required table.",
                    table_name=table_name,
                )
            )
            columns_by_table[table_name] = []
            continue
        columns = _table_columns(connection, table_name)
        columns_by_table[table_name] = columns
        missing_columns = sorted(required_columns - set(columns))
        if missing_columns:
            diagnostics.append(
                _diagnostic(
                    "required_schema_columns_missing",
                    "Replay source DB is missing required table columns.",
                    table_name=table_name,
                    missing_columns=missing_columns,
                )
            )
    schema = {
        "app_schema_version": SCHEMA_VERSION,
        "sqlite_user_version": int(connection.execute("PRAGMA user_version").fetchone()[0]),
        "sqlite_schema_version": int(connection.execute("PRAGMA schema_version").fetchone()[0]),
        "required_tables": sorted(_REQUIRED_TABLE_COLUMNS),
        "required_table_columns": columns_by_table,
        "required_table_column_hash": _sha256(columns_by_table),
    }
    return schema, diagnostics


def _normalize_occurred_at(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _event_payload(event: dict[str, Any]) -> dict[str, Any]:
    payload = event.get("payload")
    if isinstance(payload, dict):
        return payload
    payload_json = event.get("payload_json")
    if isinstance(payload_json, str):
        return json.loads(payload_json)
    return {}


def _normalize_event_for_hash(event: dict[str, Any]) -> dict[str, Any]:
    return {
        "sequence_no": int(event["sequence_no"]),
        "event_id": str(event["event_id"]),
        "event_type": str(event["event_type"]),
        "workflow_id": event.get("workflow_id"),
        "occurred_at": _normalize_occurred_at(event.get("occurred_at")),
        "payload": _event_payload(event),
    }


def _event_log_hash(events: list[dict[str, Any]]) -> str:
    return _sha256([_normalize_event_for_hash(event) for event in events])


def _convert_event_row(row: sqlite3.Row) -> dict[str, Any]:
    converted = dict(row)
    converted["sequence_no"] = int(converted["sequence_no"])
    return converted


def _list_source_events(connection: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = connection.execute("SELECT * FROM events ORDER BY sequence_no ASC").fetchall()
    return [_convert_event_row(row) for row in rows]


def _first_missing_sequence_no(events: list[dict[str, Any]]) -> int | None:
    expected = 1
    for event in sorted(events, key=lambda item: int(item["sequence_no"])):
        sequence_no = int(event["sequence_no"])
        if sequence_no != expected:
            return expected
        expected += 1
    return None


def _event_range(events: list[dict[str, Any]]) -> dict[str, int] | None:
    if not events:
        return None
    sequence_numbers = [int(event["sequence_no"]) for event in events]
    return {
        "start_sequence_no": min(sequence_numbers),
        "end_sequence_no": max(sequence_numbers),
    }


def _workflow_ids(events: list[dict[str, Any]]) -> list[str]:
    return sorted({str(event.get("workflow_id") or "").strip() for event in events if str(event.get("workflow_id") or "").strip()})


def _convert_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))


def _convert_artifact_row(row: sqlite3.Row) -> dict[str, Any]:
    converted = dict(row)
    if converted.get("created_at"):
        converted["created_at"] = _convert_datetime(converted["created_at"])
    for field in ("expires_at", "deleted_at", "storage_deleted_at"):
        if converted.get(field):
            converted[field] = _convert_datetime(converted[field])
    if converted.get("size_bytes") is not None:
        converted["size_bytes"] = int(converted["size_bytes"])
    if converted.get("retention_ttl_sec") is not None:
        converted["retention_ttl_sec"] = int(converted["retention_ttl_sec"])
    return converted


def _list_source_artifacts(connection: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = connection.execute("SELECT * FROM artifact_index ORDER BY artifact_ref ASC").fetchall()
    return [_convert_artifact_row(row) for row in rows]


def _artifact_index_hash(artifacts: list[dict[str, Any]]) -> str:
    payload = []
    for artifact in sorted(artifacts, key=lambda item: str(item.get("artifact_ref") or "")):
        payload.append(
            {
                "artifact_ref": artifact.get("artifact_ref"),
                "workflow_id": artifact.get("workflow_id"),
                "ticket_id": artifact.get("ticket_id"),
                "node_id": artifact.get("node_id"),
                "logical_path": artifact.get("logical_path"),
                "kind": artifact.get("kind"),
                "media_type": artifact.get("media_type"),
                "materialization_status": artifact.get("materialization_status"),
                "lifecycle_status": artifact.get("lifecycle_status"),
                "storage_backend": artifact.get("storage_backend"),
                "storage_relpath": artifact.get("storage_relpath"),
                "storage_object_key": artifact.get("storage_object_key"),
                "content_hash": artifact.get("content_hash"),
                "size_bytes": artifact.get("size_bytes"),
            }
        )
    return _sha256(payload)


def _artifact_tree_hash(artifact_root: Path) -> tuple[str, int, int, list[str], list[str], dict[str, str]]:
    files = sorted(path for path in artifact_root.rglob("*") if path.is_file())
    entries: list[dict[str, Any]] = []
    full_hashes: dict[str, str] = {}
    noise_samples: list[str] = []
    for path in files:
        relpath = path.relative_to(artifact_root).as_posix()
        digest = _sha256_file(path)
        full_hashes[relpath] = digest
        entries.append({"path": relpath, "sha256": digest, "size_bytes": path.stat().st_size})
        if path.name.startswith("._") or "PaxHeader" in path.parts:
            noise_samples.append(relpath)
    tree_hash = _sha256(entries)
    return tree_hash, len(files), sum(path.stat().st_size for path in files), noise_samples[:20], noise_samples, full_hashes


def _registered_artifact_tree_hash(
    artifact_root: Path,
    artifacts: list[dict[str, Any]],
) -> tuple[str, list[dict[str, Any]], list[str]]:
    entries: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []
    registered_relpaths: list[str] = []
    local_artifacts_by_relpath: dict[str, list[dict[str, Any]]] = {}
    for artifact in artifacts:
        storage_backend = str(artifact.get("storage_backend") or STORAGE_BACKEND_LOCAL_FILE)
        storage_relpath = str(artifact.get("storage_relpath") or "").strip()
        if storage_backend == STORAGE_BACKEND_LOCAL_FILE and storage_relpath:
            local_artifacts_by_relpath.setdefault(Path(storage_relpath).as_posix(), []).append(artifact)
    duplicate_relpaths = {
        relpath: sorted(
            rows,
            key=lambda item: (str(item.get("created_at") or ""), str(item.get("artifact_ref") or "")),
        )
        for relpath, rows in local_artifacts_by_relpath.items()
        if len(rows) > 1
    }
    duplicate_relpath_diagnostics: dict[str, dict[str, Any]] = {}
    for relpath, rows in duplicate_relpaths.items():
        latest = rows[-1]
        duplicate_relpath_diagnostics[relpath] = _diagnostic(
            "mutable_storage_relpath_detected",
            "Multiple artifact_index rows reference the same storage_relpath; artifact root contains the latest file bytes.",
            storage_relpath=relpath,
            registered_artifact_count=len(rows),
            artifact_refs=[str(row.get("artifact_ref")) for row in rows],
            latest_artifact_ref=str(latest.get("artifact_ref")),
            latest_content_hash=latest.get("content_hash"),
        )
    for artifact in artifacts:
        storage_backend = str(artifact.get("storage_backend") or STORAGE_BACKEND_LOCAL_FILE)
        storage_relpath = str(artifact.get("storage_relpath") or "").strip()
        expected_hash = str(artifact.get("content_hash") or "").strip()
        if storage_backend != STORAGE_BACKEND_LOCAL_FILE:
            continue
        if not storage_relpath:
            diagnostics.append(
                _diagnostic(
                    "unregistered_storage_ref",
                    "Registered local artifact has no storage_relpath.",
                    artifact_ref=artifact.get("artifact_ref"),
                )
            )
            continue
        normalized_relpath = Path(storage_relpath).as_posix()
        registered_relpaths.append(normalized_relpath)
        artifact_path = artifact_root / storage_relpath
        if not artifact_path.is_file():
            diagnostics.append(
                _diagnostic(
                    "missing_registered_artifact",
                    "Registered local artifact file is missing from artifact root.",
                    artifact_ref=artifact.get("artifact_ref"),
                    storage_relpath=storage_relpath,
                )
            )
            continue
        actual_hash = _sha256_file(artifact_path)
        if expected_hash and actual_hash != expected_hash:
            duplicate_rows = duplicate_relpaths.get(normalized_relpath, [])
            duplicate_hashes = {str(row.get("content_hash") or "") for row in duplicate_rows}
            latest_hash = str(duplicate_rows[-1].get("content_hash") or "") if duplicate_rows else ""
            if duplicate_rows and actual_hash in duplicate_hashes and actual_hash == latest_hash:
                duplicate_relpath_diagnostics[normalized_relpath]["actual_content_hash"] = actual_hash
            else:
                diagnostics.append(
                    _diagnostic(
                        "registered_artifact_hash_mismatch",
                        "Registered local artifact content hash does not match artifact_index.",
                        artifact_ref=artifact.get("artifact_ref"),
                        storage_relpath=storage_relpath,
                        expected_content_hash=expected_hash,
                        actual_content_hash=actual_hash,
                    )
                )
        entries.append(
            {
                "artifact_ref": artifact.get("artifact_ref"),
                "storage_relpath": normalized_relpath,
                "content_hash": actual_hash,
                "size_bytes": artifact_path.stat().st_size,
            }
        )
    diagnostics.extend(duplicate_relpath_diagnostics.values())
    return _sha256(sorted(entries, key=lambda item: str(item["artifact_ref"]))), diagnostics, sorted(set(registered_relpaths))


def _unregistered_files(
    all_file_hashes: dict[str, str],
    registered_relpaths: Iterable[str],
) -> list[str]:
    registered = {Path(relpath).as_posix() for relpath in registered_relpaths}
    ignored = {relpath for relpath in all_file_hashes if Path(relpath).name.startswith("._") or "PaxHeader" in Path(relpath).parts}
    return sorted(set(all_file_hashes) - registered - ignored)


def _log_hashes(log_refs: list[Path]) -> dict[str, str]:
    return {str(path): _sha256_file(path) for path in log_refs}


def _source_projection_hashes(connection: sqlite3.Connection) -> dict[str, str]:
    hashes: dict[str, str] = {}
    rows = connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    existing_tables = {str(row["name"]) for row in rows}
    for table_name in _PROJECTION_TABLES:
        if table_name not in existing_tables:
            continue
        table_rows = [dict(row) for row in connection.execute(f"SELECT * FROM {table_name} ORDER BY 1").fetchall()]
        hashes[table_name] = _sha256(table_rows)
    return hashes


def _repository_with_rebuilt_projections(events: list[dict[str, Any]]) -> ControlPlaneRepository:
    temp_dir = TemporaryDirectory(prefix="boardroom-replay-import-projection-")
    repository = ControlPlaneRepository(Path(temp_dir.name) / "replay.db", 1000)
    repository._replay_import_temp_dir = temp_dir  # keep temp dir alive with repository
    repository.initialize()
    with repository.transaction() as connection:
        connection.execute("DELETE FROM events")
        _insert_import_events(connection, events)
        replay_events = repository.list_all_events(connection)
        _replace_rebuilt_projections(repository, connection, replay_events)
    return repository


def _rebuilt_projection_hashes(events: list[dict[str, Any]]) -> dict[str, str]:
    repository = _repository_with_rebuilt_projections(events)
    hashes: dict[str, str] = {}
    with repository.connection() as connection:
        for table_name in _PROJECTION_TABLES:
            rows = [dict(row) for row in connection.execute(f"SELECT * FROM {table_name} ORDER BY 1").fetchall()]
            hashes[table_name] = _sha256(rows)
    return hashes


def _projection_mismatch_diagnostics(
    source_hashes: dict[str, str],
    rebuilt_hashes: dict[str, str],
) -> list[dict[str, Any]]:
    diagnostics: list[dict[str, Any]] = []
    for table_name, source_hash in sorted(source_hashes.items()):
        rebuilt_hash = rebuilt_hashes.get(table_name)
        if rebuilt_hash is None or rebuilt_hash == source_hash:
            continue
        diagnostics.append(
            _diagnostic(
                "source_projection_mismatch",
                "Source projection table does not match reducer-rebuilt projection; import will use rebuilt projection.",
                table_name=table_name,
                source_projection_hash=source_hash,
                rebuilt_projection_hash=rebuilt_hash,
            )
        )
    return diagnostics


def _insert_import_events(connection: sqlite3.Connection, events: list[dict[str, Any]]) -> None:
    for event in sorted(events, key=lambda item: int(item["sequence_no"])):
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
                str(event.get("actor_type") or "replay-import"),
                str(event.get("actor_id") or "replay-import"),
                str(event["occurred_at"]),
                str(event.get("idempotency_key") or f"replay-import:{event['event_id']}"),
                event.get("causation_id"),
                event.get("correlation_id") or event.get("workflow_id"),
                json.dumps(_event_payload(event), sort_keys=True),
            ),
        )


def _replace_rebuilt_projections(
    repository: ControlPlaneRepository,
    connection: sqlite3.Connection,
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


def _copy_artifact_rows(
    connection: sqlite3.Connection,
    artifacts: list[dict[str, Any]],
) -> None:
    connection.execute("DELETE FROM artifact_index")
    for artifact in artifacts:
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
                retention_class_source,
                retention_ttl_sec,
                retention_policy_source,
                storage_backend,
                storage_object_key,
                storage_delete_status,
                storage_delete_error,
                expires_at,
                deleted_at,
                deleted_by,
                delete_reason,
                storage_deleted_at,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                artifact["artifact_ref"],
                artifact["workflow_id"],
                artifact["ticket_id"],
                artifact["node_id"],
                artifact["logical_path"],
                artifact["kind"],
                artifact.get("media_type"),
                artifact["materialization_status"],
                artifact["lifecycle_status"],
                artifact.get("storage_relpath"),
                artifact.get("content_hash"),
                artifact.get("size_bytes"),
                artifact["retention_class"],
                artifact.get("retention_class_source"),
                artifact.get("retention_ttl_sec"),
                artifact.get("retention_policy_source"),
                artifact.get("storage_backend") or STORAGE_BACKEND_LOCAL_FILE,
                artifact.get("storage_object_key"),
                artifact.get("storage_delete_status") or "PRESENT",
                artifact.get("storage_delete_error"),
                artifact["expires_at"].isoformat() if artifact.get("expires_at") else None,
                artifact["deleted_at"].isoformat() if artifact.get("deleted_at") else None,
                artifact.get("deleted_by"),
                artifact.get("delete_reason"),
                artifact["storage_deleted_at"].isoformat() if artifact.get("storage_deleted_at") else None,
                artifact["created_at"].isoformat() if artifact.get("created_at") else datetime.now().astimezone().isoformat(),
            ),
        )


def _build_manifest(
    *,
    status: str,
    source_db_path: Path,
    artifact_root: Path,
    log_refs: list[Path],
    input_hashes: dict[str, Any],
    schema: dict[str, Any],
    event_range: dict[str, int] | None,
    event_count: int,
    workflow_ids: list[str],
    artifacts: list[dict[str, Any]],
    diagnostics: list[dict[str, Any]],
) -> ReplayImportManifest:
    local_file_artifact_count = sum(
        1 for artifact in artifacts if str(artifact.get("storage_backend") or STORAGE_BACKEND_LOCAL_FILE) == STORAGE_BACKEND_LOCAL_FILE
    )
    inline_db_artifact_count = sum(1 for artifact in artifacts if str(artifact.get("storage_backend") or "") == "INLINE_DB")
    manifest_payload = {
        "status": status,
        "manifest_version": REPLAY_IMPORT_MANIFEST_VERSION,
        "input_db_path": str(source_db_path),
        "artifact_root": str(artifact_root),
        "log_refs": [str(path) for path in log_refs],
        "input_hashes": input_hashes,
        "schema": schema,
        "event_range": event_range,
        "event_count": event_count,
        "workflow_ids": workflow_ids,
        "artifact_count": len(artifacts),
        "local_file_artifact_count": local_file_artifact_count,
        "inline_db_artifact_count": inline_db_artifact_count,
        "import_diagnostics": diagnostics,
        "idempotency_key": "",
        "manifest_hash": "",
    }
    manifest_payload["idempotency_key"] = _build_idempotency_key(manifest_payload)
    manifest_payload["manifest_hash"] = _manifest_hash(manifest_payload)
    return ReplayImportManifest.model_validate(manifest_payload)


def build_replay_import_manifest(
    *,
    source_db_path: str | Path,
    artifact_root: str | Path,
    log_refs: list[str | Path] | None = None,
    expected_manifest: ReplayImportManifest | None = None,
    expected_manifest_hash: str | None = None,
    expected_sqlite_schema_version: int | None = None,
) -> ReplayImportManifest:
    db_path = Path(source_db_path)
    artifacts_path = Path(artifact_root)
    logs = [Path(path) for path in list(log_refs or [])]
    diagnostics: list[dict[str, Any]] = []

    if not db_path.is_file():
        return _empty_manifest(
            source_db_path=db_path,
            artifact_root=artifacts_path,
            log_refs=logs,
            diagnostics=[
                _diagnostic(
                    "missing_replay_db",
                    "Replay import requires an existing source DB.",
                    source_db_path=str(db_path),
                )
            ],
        )
    if not artifacts_path.is_dir():
        return _empty_manifest(
            source_db_path=db_path,
            artifact_root=artifacts_path,
            log_refs=logs,
            diagnostics=[
                _diagnostic(
                    "missing_artifact_root",
                    "Replay import requires an existing artifact root.",
                    artifact_root=str(artifacts_path),
                )
            ],
        )
    for log_ref in logs:
        if not log_ref.is_file():
            return _empty_manifest(
                source_db_path=db_path,
                artifact_root=artifacts_path,
                log_refs=logs,
                diagnostics=[
                    _diagnostic(
                        "missing_log_ref",
                        "Replay import requires every declared log ref to exist.",
                        log_ref=str(log_ref),
                    )
                ],
            )

    try:
        with _connect_source_db(db_path) as connection:
            schema, schema_diagnostics = _schema_facts(connection)
            diagnostics.extend(schema_diagnostics)
            if expected_sqlite_schema_version is not None and schema["sqlite_schema_version"] != expected_sqlite_schema_version:
                diagnostics.insert(
                    0,
                    _diagnostic(
                        "sqlite_schema_version_mismatch",
                        "Replay source DB schema version does not match the expected version.",
                        expected_sqlite_schema_version=expected_sqlite_schema_version,
                        actual_sqlite_schema_version=schema["sqlite_schema_version"],
                    ),
                )
            if schema_diagnostics:
                return _empty_manifest(
                    source_db_path=db_path,
                    artifact_root=artifacts_path,
                    log_refs=logs,
                    diagnostics=diagnostics,
                    schema=schema,
                )
            events = _list_source_events(connection)
            artifacts = _list_source_artifacts(connection)
            source_projection_hashes = _source_projection_hashes(connection)
    except sqlite3.Error as exc:
        return _empty_manifest(
            source_db_path=db_path,
            artifact_root=artifacts_path,
            log_refs=logs,
            diagnostics=[
                _diagnostic(
                    "invalid_replay_db",
                    "Replay source DB cannot be opened read-only.",
                    error_type=type(exc).__name__,
                    error_message=str(exc),
                )
            ],
        )

    range_payload = _event_range(events)
    if not events:
        diagnostics.append(_diagnostic("event_log_empty", "Replay import requires at least one event."))
    missing_sequence_no = _first_missing_sequence_no(events)
    if missing_sequence_no is not None:
        diagnostics.append(
            _diagnostic(
                "event_range_not_contiguous",
                "Replay import event range is not contiguous.",
                missing_sequence_no=missing_sequence_no,
            )
        )

    artifact_tree_sha256, artifact_file_count, artifact_total_bytes, noise_samples, all_noise, full_file_hashes = _artifact_tree_hash(artifacts_path)
    registered_tree_sha256, artifact_diagnostics, registered_relpaths = _registered_artifact_tree_hash(artifacts_path, artifacts)
    diagnostics.extend(artifact_diagnostics)
    unregistered = _unregistered_files(full_file_hashes, registered_relpaths)
    if all_noise:
        diagnostics.append(
            _diagnostic(
                "artifact_tree_noise_detected",
                "Artifact root contains archive metadata files; import records but ignores them.",
                noise_file_count=len(all_noise),
                sample_paths=noise_samples,
            )
        )
    if unregistered:
        diagnostics.append(
            _diagnostic(
                "unregistered_artifact_files_detected",
                "Artifact root contains files not registered by artifact_index; import records but ignores them.",
                unregistered_file_count=len(unregistered),
                sample_paths=unregistered[:20],
            )
        )
    if any(str(artifact.get("storage_backend") or "") == "INLINE_DB" for artifact in artifacts):
        diagnostics.append(
            _diagnostic(
                "inline_db_artifact_recorded",
                "INLINE_DB artifact rows are covered by source DB hash and have no artifact root storage.",
                artifact_refs=[
                    str(artifact.get("artifact_ref"))
                    for artifact in artifacts
                    if str(artifact.get("storage_backend") or "") == "INLINE_DB"
                ],
            )
        )

    rebuilt_hashes = _rebuilt_projection_hashes(events) if events else {}
    diagnostics.extend(_projection_mismatch_diagnostics(source_projection_hashes, rebuilt_hashes))

    input_hashes = {
        "db_sha256": _sha256_file(db_path),
        "artifact_tree_sha256": artifact_tree_sha256,
        "registered_artifact_tree_sha256": registered_tree_sha256,
        "artifact_file_count": artifact_file_count,
        "artifact_total_bytes": artifact_total_bytes,
        "log_sha256s": _log_hashes(logs),
        "event_log_hash": _event_log_hash(events),
        "artifact_index_hash": _artifact_index_hash(artifacts),
    }
    fail_reason_codes = {
        "sqlite_schema_version_mismatch",
        "event_log_empty",
        "event_range_not_contiguous",
        "missing_registered_artifact",
        "registered_artifact_hash_mismatch",
        "unregistered_storage_ref",
    }
    status = "FAILED" if any(item["reason_code"] in fail_reason_codes for item in diagnostics) else "READY"
    manifest = _build_manifest(
        status=status,
        source_db_path=db_path,
        artifact_root=artifacts_path,
        log_refs=logs,
        input_hashes=input_hashes,
        schema=schema,
        event_range=range_payload,
        event_count=len(events),
        workflow_ids=_workflow_ids(events),
        artifacts=artifacts,
        diagnostics=diagnostics,
    )
    expected_hash = expected_manifest_hash or (expected_manifest.manifest_hash if expected_manifest is not None else None)
    if expected_hash and manifest.manifest_hash != expected_hash:
        return _build_manifest(
            status="FAILED",
            source_db_path=db_path,
            artifact_root=artifacts_path,
            log_refs=logs,
            input_hashes=input_hashes,
            schema=schema,
            event_range=range_payload,
            event_count=len(events),
            workflow_ids=_workflow_ids(events),
            artifacts=artifacts,
            diagnostics=[
                _diagnostic(
                    "expected_manifest_hash_mismatch",
                    "Replay import manifest hash does not match expected manifest.",
                    expected_manifest_hash=expected_hash,
                    actual_manifest_hash=manifest.manifest_hash,
                ),
                *diagnostics,
            ],
        )
    return manifest


def import_replay_bundle(
    *,
    source_db_path: str | Path,
    artifact_root: str | Path,
    log_refs: list[str | Path] | None = None,
    target_db_path: str | Path,
    expected_manifest: ReplayImportManifest | None = None,
    expected_manifest_hash: str | None = None,
    expected_sqlite_schema_version: int | None = None,
) -> ReplayImportManifest:
    manifest = build_replay_import_manifest(
        source_db_path=source_db_path,
        artifact_root=artifact_root,
        log_refs=log_refs,
        expected_manifest=expected_manifest,
        expected_manifest_hash=expected_manifest_hash,
        expected_sqlite_schema_version=expected_sqlite_schema_version,
    )
    if manifest.status != "READY":
        return manifest

    db_path = Path(source_db_path)
    target_path = Path(target_db_path)
    with _connect_source_db(db_path) as source_connection:
        events = _list_source_events(source_connection)
        artifacts = _list_source_artifacts(source_connection)

    target_path.parent.mkdir(parents=True, exist_ok=True)
    if target_path.exists():
        target_path.unlink()
    artifact_store = ArtifactStore(Path(manifest.artifact_root))
    repository = ControlPlaneRepository(target_path, 1000, artifact_store=artifact_store)
    repository.initialize()
    with repository.transaction() as connection:
        connection.execute("DELETE FROM events")
        connection.execute("DELETE FROM artifact_index")
        _insert_import_events(connection, events)
        imported_events = repository.list_all_events(connection)
        _replace_rebuilt_projections(repository, connection, imported_events)
        _copy_artifact_rows(connection, artifacts)
    return manifest
