from __future__ import annotations

import json
import os
import shutil
import stat
from pathlib import Path
from typing import Any

from tests.scenario._config import ScenarioLayoutConfig

SEED_MANIFEST_FILENAME = "seed-manifest.json"

DEFAULT_EXCLUDED_PATHS = (
    "runtime/events.log",
    "runtime/runtime-provider-config.json",
    "audit/records/timeline",
    "audit/records/nodes",
    "audit/records/incidents",
    "audit/views",
    "debug",
)


def _make_tree_writable(root: Path) -> None:
    if not root.exists():
        return
    for path in sorted(root.rglob("*")):
        try:
            if path.is_dir():
                path.chmod(stat.S_IWRITE | stat.S_IREAD | stat.S_IEXEC)
            else:
                path.chmod(stat.S_IWRITE | stat.S_IREAD)
        except OSError:
            continue


def _remove_tree(target: Path) -> None:
    def _onerror(func, path, _exc_info) -> None:
        os.chmod(path, stat.S_IWRITE)
        func(path)

    if target.exists():
        shutil.rmtree(target, onerror=_onerror)


def _is_relative_to(path: Path, other: Path) -> bool:
    try:
        path.relative_to(other)
        return True
    except ValueError:
        return False


def _copy_file(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def _copy_tree_filtered(
    *,
    source_root: Path,
    destination_root: Path,
    relative_path: Path,
    skip_relative_paths: tuple[Path, ...] = (),
) -> list[str]:
    source_path = source_root / relative_path
    if not source_path.exists():
        return []

    copied_paths: list[str] = [relative_path.as_posix()]
    destination_path = destination_root / relative_path
    destination_path.mkdir(parents=True, exist_ok=True)
    for path in sorted(source_path.rglob("*")):
        relative = path.relative_to(source_root)
        if any(_is_relative_to(relative, skip_path) for skip_path in skip_relative_paths):
            continue
        target = destination_root / relative
        if path.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        _copy_file(path, target)
        copied_paths.append(relative.as_posix())
    return copied_paths


def load_seed_manifest(seed_root: Path) -> dict[str, Any]:
    manifest_path = seed_root / SEED_MANIFEST_FILENAME
    if not manifest_path.exists():
        raise FileNotFoundError(f"Seed manifest is missing: {manifest_path}")
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Seed manifest is invalid JSON: {manifest_path}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"Seed manifest must decode to a JSON object: {manifest_path}")
    return payload


def freeze_scenario_as_seed(
    *,
    source_root: Path,
    destination_root: Path,
    layout: ScenarioLayoutConfig,
    seed_id: str,
    captured_from_stage_id: str | None,
    workflow_id: str | None,
    workflow_status: str,
    current_stage: str,
    output_schema_refs: tuple[str, ...],
    graph_node_ids: tuple[str, ...],
    source_delivery_git: tuple[dict[str, Any], ...],
) -> Path:
    _remove_tree(destination_root)
    destination_root.mkdir(parents=True, exist_ok=True)

    copied_paths: list[str] = []
    state_db = source_root / layout.runtime_db
    if state_db.exists():
        _copy_file(state_db, destination_root / layout.runtime_db)
        copied_paths.append(layout.runtime_db.as_posix())

    copied_paths.extend(
        _copy_tree_filtered(
            source_root=source_root,
            destination_root=destination_root,
            relative_path=layout.runtime_blobs_dir,
            skip_relative_paths=(layout.artifact_uploads_dir,),
        )
    )
    if workflow_id:
        copied_paths.extend(
            _copy_tree_filtered(
                source_root=source_root,
                destination_root=destination_root,
                relative_path=layout.resolve_workspace_dir(Path("."), workflow_id),
            )
        )
    copied_paths.extend(
        _copy_tree_filtered(
            source_root=source_root,
            destination_root=destination_root,
            relative_path=layout.ticket_context_archive_dir,
        )
    )

    ensure_layout_directories(
        scenario_root=destination_root,
        layout=layout,
        workflow_id=workflow_id,
    )

    manifest_path = destination_root / SEED_MANIFEST_FILENAME
    manifest_path.write_text(
        json.dumps(
            {
                "seed_id": seed_id,
                "captured_from_stage_id": captured_from_stage_id,
                "workflow_id": workflow_id,
                "workflow_status": workflow_status,
                "current_stage": current_stage,
                "output_schema_refs": sorted(set(output_schema_refs)),
                "graph_node_ids": sorted(set(graph_node_ids)),
                "source_delivery_git": list(source_delivery_git),
                "copied_paths": sorted(dict.fromkeys(copied_paths)),
                "excluded_paths": list(DEFAULT_EXCLUDED_PATHS),
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return manifest_path


def ensure_layout_directories(
    *,
    scenario_root: Path,
    layout: ScenarioLayoutConfig,
    workflow_id: str | None,
) -> None:
    required_dirs = [
        (scenario_root / layout.runtime_db).parent,
        (scenario_root / layout.events_log).parent,
        scenario_root / layout.runtime_blobs_dir,
        scenario_root / layout.audit_records_dir,
        scenario_root / layout.audit_records_dir / "timeline",
        scenario_root / layout.audit_records_dir / "nodes",
        scenario_root / layout.audit_records_dir / "incidents",
        scenario_root / layout.audit_views_dir,
        scenario_root / layout.audit_stage_views_dir,
        scenario_root / layout.debug_compile_dir,
        scenario_root / layout.debug_logs_dir,
        (scenario_root / layout.runtime_provider_config).parent,
        scenario_root / layout.artifact_uploads_dir,
        scenario_root / layout.ticket_context_archive_dir,
        layout.resolve_project_workspace_root(scenario_root),
    ]
    if workflow_id:
        required_dirs.extend(
            [
                layout.resolve_workspace_dir(scenario_root, workflow_id),
                layout.resolve_workspace_metadata_dir(scenario_root, workflow_id),
            ]
        )

    for directory in required_dirs:
        directory.mkdir(parents=True, exist_ok=True)

    (scenario_root / layout.events_log).touch(exist_ok=True)


def prepare_seeded_scenario(
    *,
    seed_root: Path,
    destination_root: Path,
    layout: ScenarioLayoutConfig,
    workflow_id: str | None,
) -> None:
    if not seed_root.exists():
        raise FileNotFoundError(f"Seed root does not exist: {seed_root}")

    _remove_tree(destination_root)
    shutil.copytree(seed_root, destination_root)
    _make_tree_writable(destination_root)
    ensure_layout_directories(
        scenario_root=destination_root,
        layout=layout,
        workflow_id=workflow_id,
    )
