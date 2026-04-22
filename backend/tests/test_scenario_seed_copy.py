from __future__ import annotations

import json
import stat
from pathlib import Path


def test_prepare_seeded_scenario_copies_seed_and_makes_destination_writable(tmp_path: Path) -> None:
    from tests.scenario._config import ScenarioLayoutConfig
    from tests.scenario._seed_copy import prepare_seeded_scenario

    seed_root = tmp_path / "seed" / "scenario"
    source_file = seed_root / "runtime" / "state.db"
    source_file.parent.mkdir(parents=True, exist_ok=True)
    source_file.write_text("seed-db", encoding="utf-8")
    source_file.chmod(stat.S_IREAD)

    destination_root = tmp_path / "run" / "scenario"
    layout = ScenarioLayoutConfig(
        runtime_db=Path("runtime/state.db"),
        events_log=Path("runtime/events.log"),
        runtime_blobs_dir=Path("runtime/blobs"),
        audit_records_dir=Path("audit/records"),
        audit_views_dir=Path("audit/views"),
        audit_stage_views_dir=Path("audit/views/stage-views"),
        workspace_dir_pattern=Path("workspace/wf_{workflow_id}"),
        workspace_metadata_dir=Path("workspace/wf_{workflow_id}/.metadata"),
        debug_compile_dir=Path("debug/compile"),
        debug_logs_dir=Path("debug/logs"),
        runtime_provider_config=Path("runtime/runtime-provider-config.json"),
        artifact_uploads_dir=Path("runtime/blobs/uploads"),
        ticket_context_archive_dir=Path("audit/records/nodes/ticket-context-archives"),
    )

    prepare_seeded_scenario(
        seed_root=seed_root,
        destination_root=destination_root,
        layout=layout,
        workflow_id="wf_seed_demo",
    )

    copied_file = destination_root / "runtime" / "state.db"
    assert copied_file.read_text(encoding="utf-8") == "seed-db"

    copied_file.write_text("mutated", encoding="utf-8")
    assert copied_file.read_text(encoding="utf-8") == "mutated"
    assert source_file.read_text(encoding="utf-8") == "seed-db"


def test_prepare_seeded_scenario_creates_workspace_metadata_and_audit_dirs(tmp_path: Path) -> None:
    from tests.scenario._config import ScenarioLayoutConfig
    from tests.scenario._seed_copy import prepare_seeded_scenario

    seed_root = tmp_path / "seed" / "scenario"
    seed_root.mkdir(parents=True, exist_ok=True)
    destination_root = tmp_path / "run" / "scenario"
    layout = ScenarioLayoutConfig(
        runtime_db=Path("runtime/state.db"),
        events_log=Path("runtime/events.log"),
        runtime_blobs_dir=Path("runtime/blobs"),
        audit_records_dir=Path("audit/records"),
        audit_views_dir=Path("audit/views"),
        audit_stage_views_dir=Path("audit/views/stage-views"),
        workspace_dir_pattern=Path("workspace/wf_{workflow_id}"),
        workspace_metadata_dir=Path("workspace/wf_{workflow_id}/.metadata"),
        debug_compile_dir=Path("debug/compile"),
        debug_logs_dir=Path("debug/logs"),
        runtime_provider_config=Path("runtime/runtime-provider-config.json"),
        artifact_uploads_dir=Path("runtime/blobs/uploads"),
        ticket_context_archive_dir=Path("audit/records/nodes/ticket-context-archives"),
    )

    prepare_seeded_scenario(
        seed_root=seed_root,
        destination_root=destination_root,
        layout=layout,
        workflow_id="wf_stage_demo",
    )

    assert (destination_root / "workspace" / "wf_stage_demo" / ".metadata").exists()
    assert (destination_root / "audit" / "records" / "timeline").exists()
    assert (destination_root / "audit" / "records" / "nodes").exists()
    assert (destination_root / "audit" / "records" / "incidents").exists()
    assert (destination_root / "audit" / "views" / "stage-views").exists()
    assert (destination_root / "debug" / "compile").exists()
    assert (destination_root / "debug" / "logs").exists()


def test_freeze_scenario_as_seed_copies_stable_runtime_truth_and_writes_manifest(tmp_path: Path) -> None:
    from tests.scenario._config import ScenarioLayoutConfig
    from tests.scenario._seed_copy import freeze_scenario_as_seed

    source_root = tmp_path / "run" / "scenario"
    layout = ScenarioLayoutConfig(
        runtime_db=Path("runtime/state.db"),
        events_log=Path("runtime/events.log"),
        runtime_blobs_dir=Path("runtime/blobs"),
        audit_records_dir=Path("audit/records"),
        audit_views_dir=Path("audit/views"),
        audit_stage_views_dir=Path("audit/views/stage-views"),
        workspace_dir_pattern=Path("workspace/wf_{workflow_id}"),
        workspace_metadata_dir=Path("workspace/wf_{workflow_id}/.metadata"),
        debug_compile_dir=Path("debug/compile"),
        debug_logs_dir=Path("debug/logs"),
        runtime_provider_config=Path("runtime/runtime-provider-config.json"),
        artifact_uploads_dir=Path("runtime/blobs/uploads"),
        ticket_context_archive_dir=Path("audit/records/nodes/ticket-context-archives"),
    )

    (source_root / "runtime").mkdir(parents=True, exist_ok=True)
    (source_root / "runtime" / "state.db").write_text("seed-db", encoding="utf-8")
    (source_root / "runtime" / "events.log").write_text("event", encoding="utf-8")
    (source_root / "runtime" / "runtime-provider-config.json").write_text("{}", encoding="utf-8")
    (source_root / "runtime" / "blobs" / "keep.txt").parent.mkdir(parents=True, exist_ok=True)
    (source_root / "runtime" / "blobs" / "keep.txt").write_text("keep", encoding="utf-8")
    (source_root / "runtime" / "blobs" / "uploads" / "temp.txt").parent.mkdir(parents=True, exist_ok=True)
    (source_root / "runtime" / "blobs" / "uploads" / "temp.txt").write_text("skip", encoding="utf-8")
    (
        source_root
        / "workspace"
        / "wf_seed_demo"
        / "00-boardroom"
        / "workflow"
        / "workspace-manifest.json"
    ).parent.mkdir(parents=True, exist_ok=True)
    (
        source_root
        / "workspace"
        / "wf_seed_demo"
        / "00-boardroom"
        / "workflow"
        / "workspace-manifest.json"
    ).write_text('{"workflow_id":"wf_seed_demo"}', encoding="utf-8")
    (
        source_root
        / "audit"
        / "records"
        / "nodes"
        / "ticket-context-archives"
        / "tkt_build_001.md"
    ).parent.mkdir(parents=True, exist_ok=True)
    (
        source_root
        / "audit"
        / "records"
        / "nodes"
        / "ticket-context-archives"
        / "tkt_build_001.md"
    ).write_text("# context\n", encoding="utf-8")
    (source_root / "audit" / "records" / "timeline" / "tick_0001.json").parent.mkdir(
        parents=True, exist_ok=True
    )
    (source_root / "audit" / "records" / "timeline" / "tick_0001.json").write_text("{}", encoding="utf-8")
    (source_root / "audit" / "views" / "workflow-summary.md").parent.mkdir(parents=True, exist_ok=True)
    (source_root / "audit" / "views" / "workflow-summary.md").write_text("# summary\n", encoding="utf-8")
    (source_root / "debug" / "logs" / "debug.log").parent.mkdir(parents=True, exist_ok=True)
    (source_root / "debug" / "logs" / "debug.log").write_text("debug", encoding="utf-8")

    destination_root = tmp_path / "seed" / "scenario"
    manifest_path = freeze_scenario_as_seed(
        source_root=source_root,
        destination_root=destination_root,
        layout=layout,
        seed_id="stage_02_outline_to_detailed_design",
        captured_from_stage_id="stage_01_requirement_to_architecture",
        workflow_id="wf_seed_demo",
        workflow_status="EXECUTING",
        current_stage="plan",
        output_schema_refs=("architecture_brief",),
        graph_node_ids=("node_architecture_brief",),
        source_delivery_git=(),
    )

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert (destination_root / "runtime" / "state.db").read_text(encoding="utf-8") == "seed-db"
    assert (destination_root / "runtime" / "blobs" / "keep.txt").read_text(encoding="utf-8") == "keep"
    assert not (destination_root / "runtime" / "blobs" / "uploads" / "temp.txt").exists()
    assert (
        destination_root
        / "workspace"
        / "wf_seed_demo"
        / "00-boardroom"
        / "workflow"
        / "workspace-manifest.json"
    ).exists()
    assert (
        destination_root
        / "audit"
        / "records"
        / "nodes"
        / "ticket-context-archives"
        / "tkt_build_001.md"
    ).exists()
    assert not (destination_root / "audit" / "views" / "workflow-summary.md").exists()
    assert not (destination_root / "debug" / "logs" / "debug.log").exists()
    assert not (destination_root / "runtime" / "runtime-provider-config.json").exists()
    assert manifest["seed_id"] == "stage_02_outline_to_detailed_design"
    assert manifest["captured_from_stage_id"] == "stage_01_requirement_to_architecture"
    assert manifest["workflow_id"] == "wf_seed_demo"
    assert manifest["current_stage"] == "plan"
    assert manifest["output_schema_refs"] == ["architecture_brief"]
    assert manifest["graph_node_ids"] == ["node_architecture_brief"]
    assert "runtime/state.db" in manifest["copied_paths"]
    assert "runtime/runtime-provider-config.json" in manifest["excluded_paths"]
