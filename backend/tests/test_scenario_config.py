from __future__ import annotations

from pathlib import Path

import pytest


def _write_config(tmp_path: Path, *, provider_body: str, stage_seed_ref: str = "stage_01_requirement_to_architecture") -> Path:
    config_path = tmp_path / "library-management.toml"
    seed_path = tmp_path / "seeds" / "stage_01_requirement_to_architecture" / "scenario"
    seed_path.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        f"""
[scenario]
scenario_id = "library-management"
display_name = "Library Management Scenario Tests"

[input]
north_star_goal = "实现一个完全匿名、单机运行的极简图书流转终端。"
hard_constraints = ["匿名", "单机", "books 单表"]
read_only_context_refs = ["doc/tests/intergration-test-007-20260422.md"]
workflow_profile = "CEO_AUTOPILOT_FINE_GRAINED"
force_requirement_elicitation = false

[runtime]
seed = 17
max_ticks = 12
timeout_sec = 120
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
workspace_dir_pattern = "workspace/wf_{{workflow_id}}"
workspace_metadata_dir = "workspace/wf_{{workflow_id}}/.metadata"
debug_compile_dir = "debug/compile"
debug_logs_dir = "debug/logs"
runtime_provider_config = "runtime/runtime-provider-config.json"
artifact_uploads_dir = "runtime/blobs/uploads"
ticket_context_archive_dir = "audit/records/nodes/ticket-context-archives"

[provider.default]
{provider_body}

[[provider.role_bindings]]
target_ref = "ceo_shadow"
provider_model_entry_refs = ["prov_default::gpt-5.4"]
max_context_window_override = 180000
reasoning_effort_override = "xhigh"

[seeds.stage_01_requirement_to_architecture]
path = "seeds/stage_01_requirement_to_architecture/scenario"
description = "Stage 01 seed"
requires_prepared_state = false

[[stages]]
stage_id = "stage_01_requirement_to_architecture"
test_file = "backend/tests/scenario/test_library_management_stage_01_requirement_to_architecture.py"
seed_ref = "{stage_seed_ref}"
start_mode = "copy_seed"
checkpoint_kind = "requirement_to_architecture"
expected_stage = "project_init"
expected_outputs = ["audit/records/manifest.json", "audit/views/workflow-summary.md", "audit/views/dag-visualization.dot"]
required_schema_refs = ["architecture_brief"]
forbidden_schema_refs = ["source_code_delivery"]
required_role_types = ["governance_architect"]
""".strip(),
        encoding="utf-8",
    )
    return config_path


def test_load_scenario_test_config_resolves_env_api_key_and_stage_refs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SCENARIO_TEST_KEY", "env-secret")
    config_path = _write_config(
        tmp_path,
        provider_body="""
provider_id = "prov_default"
base_url = "https://api.example.test/v1"
api_key_env = "SCENARIO_TEST_KEY"
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
""".strip(),
    )

    from tests.scenario._config import load_scenario_test_config

    config = load_scenario_test_config(config_path)

    assert config.provider.api_key == "env-secret"
    assert config.provider.provider_id == "prov_default"
    assert config.seeds["stage_01_requirement_to_architecture"].path == (
        tmp_path / "seeds" / "stage_01_requirement_to_architecture" / "scenario"
    )
    assert config.stages["stage_01_requirement_to_architecture"].seed_ref == (
        "stage_01_requirement_to_architecture"
    )
    assert config.layout.resolve_workspace_dir(tmp_path / "run" / "scenario", "wf_demo") == (
        tmp_path / "run" / "scenario" / "workspace" / "wf_demo"
    )
    assert config.layout.resolve_workspace_metadata_dir(tmp_path / "run" / "scenario", "wf_demo") == (
        tmp_path / "run" / "scenario" / "workspace" / "wf_demo" / ".metadata"
    )


def test_load_scenario_test_config_prefers_inline_api_key_over_env_reference(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SCENARIO_TEST_KEY", "env-secret")
    config_path = _write_config(
        tmp_path,
        provider_body="""
provider_id = "prov_default"
base_url = "https://api.example.test/v1"
api_key = "inline-secret"
api_key_env = "SCENARIO_TEST_KEY"
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
""".strip(),
    )

    from tests.scenario._config import load_scenario_test_config

    config = load_scenario_test_config(config_path)

    assert config.provider.api_key == "inline-secret"


def test_build_runtime_provider_payload_uses_empty_string_when_api_key_is_missing(
    tmp_path: Path,
) -> None:
    config_path = _write_config(
        tmp_path,
        provider_body="""
provider_id = "prov_default"
base_url = "https://api.example.test/v1"
api_key_env = "MISSING_SCENARIO_TEST_KEY"
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
""".strip(),
    )

    from tests.scenario._config import load_scenario_test_config

    config = load_scenario_test_config(config_path)
    payload = config.build_runtime_provider_payload()

    assert payload["providers"][0]["api_key"] == ""


def test_load_scenario_test_config_rejects_unknown_seed_ref(tmp_path: Path) -> None:
    config_path = _write_config(
        tmp_path,
        provider_body="""
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
""".strip(),
        stage_seed_ref="missing_seed",
    )

    from tests.scenario._config import load_scenario_test_config

    with pytest.raises(ValueError, match="missing_seed"):
        load_scenario_test_config(config_path)
