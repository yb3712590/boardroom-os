from __future__ import annotations

from pathlib import Path


def _write_builder_config(tmp_path: Path) -> Path:
    config_path = tmp_path / "library-management.toml"
    config_path.write_text(
        """
[scenario]
scenario_id = "library-management"
display_name = "Library Management Scenario Tests"

[input]
north_star_goal = "实现一个完全匿名、单机运行的极简图书流转终端。"
hard_constraints = ["匿名", "单机", "books 单表"]
read_only_context_refs = []
workflow_profile = "CEO_AUTOPILOT_FINE_GRAINED"
force_requirement_elicitation = false

[runtime]
seed = 17
max_ticks = 4
timeout_sec = 30
maintenance_interval_sec = 1
scheduler_max_dispatches = 20
resume_enabled = true

[layout]
runtime_db = "runtime/state.db"
events_log = "runtime/events.log"
runtime_blobs_dir = "runtime/blobs"
audit_records_dir = "audit/records"
audit_views_dir = "audit/views"
audit_stage_views_dir = "audit/views/stage-views"
workspace_dir_pattern = "workspace/wf_{workflow_id}"
workspace_metadata_dir = "workspace/wf_{workflow_id}/.metadata"
debug_compile_dir = "debug/compile"
debug_logs_dir = "debug/logs"
runtime_provider_config = "runtime/runtime-provider-config.json"
artifact_uploads_dir = "runtime/blobs/uploads"
ticket_context_archive_dir = "audit/records/nodes/ticket-context-archives"

[provider.default]
provider_id = "prov_default"
base_url = "https://api.example.test/v1"
api_key = "inline-secret"
preferred_model = "gpt-5.4"
max_context_window = 200000
reasoning_effort = "high"
timeout_sec = 480
connect_timeout_sec = 10
write_timeout_sec = 20
first_token_timeout_sec = 300
stream_idle_timeout_sec = 300
request_total_timeout_sec = 480
retry_backoff_schedule_sec = [1, 2, 4]
fallback_provider_ids = []

[[provider.role_bindings]]
target_ref = "ceo_shadow"
provider_model_entry_refs = ["prov_default::gpt-5.4"]

[seeds.stage_02_outline_to_detailed_design]
path = "seeds/stage_02_outline_to_detailed_design/scenario"
description = "Stage 02 seed"
requires_prepared_state = true

[seeds.stage_06_parallel_git_fanout_merge]
path = "seeds/stage_06_parallel_git_fanout_merge/scenario"
description = "Stage 06 seed"
requires_prepared_state = true
""".strip(),
        encoding="utf-8",
    )
    return config_path


def test_update_seed_workflow_id_in_config_inserts_and_replaces_value(tmp_path: Path) -> None:
    from tests.scenario._seed_builder import update_seed_workflow_id_in_config

    config_path = _write_builder_config(tmp_path)

    update_seed_workflow_id_in_config(
        config_path,
        seed_id="stage_02_outline_to_detailed_design",
        workflow_id="wf_stage02_seed",
    )
    update_seed_workflow_id_in_config(
        config_path,
        seed_id="stage_02_outline_to_detailed_design",
        workflow_id="wf_stage02_seed_replaced",
    )

    body = config_path.read_text(encoding="utf-8")

    assert 'workflow_id = "wf_stage02_seed_replaced"' in body
    assert 'workflow_id = "wf_stage02_seed"' not in body


def test_seed_builder_main_dispatches_capture_stage(monkeypatch, tmp_path: Path) -> None:
    from tests.scenario import _seed_builder

    config_path = _write_builder_config(tmp_path)
    captured: dict[str, object] = {}

    def _fake_capture(args) -> int:
        captured["config_path"] = args.config_path
        captured["stage_id"] = args.stage_id
        return 0

    monkeypatch.setattr(_seed_builder, "_handle_capture_stage", _fake_capture)

    exit_code = _seed_builder.main(
        [
            "capture-stage",
            "--config-path",
            str(config_path),
            "--stage-id",
            "stage_02_outline_to_detailed_design",
        ]
    )

    assert exit_code == 0
    assert captured["config_path"] == config_path
    assert captured["stage_id"] == "stage_02_outline_to_detailed_design"


def test_seed_builder_main_dispatches_build_stage06(monkeypatch, tmp_path: Path) -> None:
    from tests.scenario import _seed_builder

    config_path = _write_builder_config(tmp_path)
    captured: dict[str, object] = {}

    def _fake_build_stage06(args) -> int:
        captured["config_path"] = args.config_path
        captured["seed_id"] = args.seed_id
        return 0

    monkeypatch.setattr(_seed_builder, "_handle_build_stage06", _fake_build_stage06)

    exit_code = _seed_builder.main(
        [
            "build-stage06",
            "--config-path",
            str(config_path),
            "--seed-id",
            "stage_06_parallel_git_fanout_merge",
        ]
    )

    assert exit_code == 0
    assert captured["config_path"] == config_path
    assert captured["seed_id"] == "stage_06_parallel_git_fanout_merge"
