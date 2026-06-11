from __future__ import annotations

from pathlib import Path

from atomic_agent.providers.openai_compatible import OpenAICompatibleProviderOptions

from boardroom_os.config.boardroom import (
    BoardroomConfigPaths,
    BoardroomRuntimeConfig,
    BoardroomSettings,
    load_boardroom_settings,
)


def _write_config_files(tmp_path: Path) -> BoardroomConfigPaths:
    runtime = tmp_path / "runtime.yaml"
    providers = tmp_path / "providers.yaml"
    roles = tmp_path / "roles.yaml"
    runtime.write_text(
        """
version: 1
runtime_id: boardroom-runtime.test
execution:
  implementation_executor: atomic_agent
  reject_provider_executor_for_implementation: true
atomic_agent:
  package_name: atomic-agent
  import_name: atomic_agent
  runtime_port_contract_ref: atomic-agent.docs.agent-runtime-port.v1
  event_stream_root: .evidence/atomic-agent/events
  artifact_root: .evidence/atomic-agent/artifacts
  run_id_prefix: boardroom-atomic
  dependency:
    atomic_agent_path_env: BOARDROOM_ATOMIC_AGENT_PATH
    default_atomic_agent_path: ../atomic-agent
    contract_lock_ref: doc/06-reference/atomic-agent-contract-lock.md
    require_contract_hash_match: true
  execution_policy:
    wall_time_seconds: 900
    retry_on_provider_timeout: false
    retry_on_runtime_crash: true
    max_retries: 1
    interrupt_grace_period_seconds: 30
    retry_requires_no_workspace_mutation: true
  concurrency:
    mode: serial_per_workspace
    workspace_lock_root: .evidence/atomic-agent/locks
    require_run_scoped_event_artifact_roots: true
  default_tools: [list_files, read_file, search_files, write_file, run_command, submit_result]
  required_tools: [submit_result]
  tool_permission_map:
    filesystem.read: [list_files, read_file, search_files]
    filesystem.write: [write_file, apply_patch]
    command.execute: [run_command]
    network.fetch: [web_fetch]
  budget_profiles:
    atomic.proving.minimal:
      max_steps: 32
      max_parse_failures: 2
      max_observation_chars: 16000
      max_wall_seconds: 1200
      max_actions_per_turn: 4
    worker.implementation.default:
      max_steps: 96
      max_parse_failures: 3
      max_observation_chars: 24000
      max_wall_seconds: 3600
      max_actions_per_turn: 8
  budget_caps:
    max_steps: 240
    max_parse_failures: 6
    max_observation_chars: 64000
    max_wall_seconds: 10800
    max_actions_per_turn: 8
  checkpoints:
    required_output:
      max_auto_runs: 3
  filesystem:
    default_read_limit: 12000
    max_read_limit: 50000
    default_max_entries: 200
    max_entries_limit: 1000
    default_max_matches: 50
    max_matches_limit: 500
    allow_apply_patch: false
  commands:
    default_timeout_seconds: 60
    max_timeout_seconds: 300
    max_output_bytes: 200000
  network:
    default: deny
    allow_rules: []
""".strip()
        + "\n",
        encoding="utf-8",
    )
    providers.write_text(
        """
version: 1
providers:
  - provider_profile_id: provider.openai-compatible.primary
    provider_type: openai_compatible
    provider_label: test-openai-compatible
    base_url: https://api.example.invalid/v1
    api_key_env: OPENAI_API_KEY
    model: gpt-5.5
    context_window_tokens: 400000
    max_output_tokens: 128000
    stream_idle_timeout_seconds: 120
    total_timeout_seconds: 600
    reasoning_effort: high
    temperature: null
    top_p: null
    presence_penalty: null
    frequency_penalty: null
    seed: null
    stop: null
    response_format: null
    stream_options: null
    service_tier: null
    user: boardroom-os
""".strip()
        + "\n",
        encoding="utf-8",
    )
    roles.write_text(
        """
version: 1
role_slots:
  - seat_ref: seat.worker.implementation
    role_profile_ref: role.worker.implementation
    role_category: worker
    model_execution_profile_id: model-profile.worker.implementation.primary
    provider_profile_ref: provider.openai-compatible.primary
    skill_refs: [skill.command.test]
    default_tools: [list_files, read_file, search_files, write_file, run_command, submit_result]
    budget_profile_ref: worker.implementation.default
    budgets_override:
      max_steps: 128
      max_wall_seconds: 5400
""".strip()
        + "\n",
        encoding="utf-8",
    )
    return BoardroomConfigPaths(runtime_config=runtime, providers_config=providers, roles_config=roles)


def test_load_boardroom_settings_cross_links_runtime_provider_and_role(tmp_path, monkeypatch):
    paths = _write_config_files(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-secret")

    settings = load_boardroom_settings(paths, env_values={})

    assert isinstance(settings, BoardroomSettings)
    assert isinstance(settings.runtime, BoardroomRuntimeConfig)
    assert settings.runtime.execution.implementation_executor == "atomic_agent"
    assert settings.runtime.execution.reject_provider_executor_for_implementation is True
    assert settings.provider_by_id("provider.openai-compatible.primary").model == "gpt-5.5"
    role = settings.role_slot_by_seat("seat.worker.implementation")
    assert role.provider_profile_ref == "provider.openai-compatible.primary"
    assert settings.config_hashes.runtime_config_hash.startswith("sha256:")
    assert settings.config_hashes.providers_config_hash.startswith("sha256:")
    assert settings.config_hashes.roles_config_hash.startswith("sha256:")


def test_provider_profile_compiles_to_openai_compatible_options(tmp_path, monkeypatch):
    paths = _write_config_files(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-secret")
    settings = load_boardroom_settings(paths, env_values={})

    options = settings.openai_compatible_options("provider.openai-compatible.primary")

    assert isinstance(options, OpenAICompatibleProviderOptions)
    assert options.base_url == "https://api.example.invalid/v1"
    assert options.api_key == "sk-test-secret"
    assert options.model == "gpt-5.5"
    assert options.reasoning_effort == "high"
    assert options.to_provider_profile()["provider"] == "openai-compatible"
    assert "api_key" not in options.to_provider_profile()


def test_role_budget_profile_and_override_resolve_to_auditable_budget(tmp_path, monkeypatch):
    paths = _write_config_files(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-secret")
    settings = load_boardroom_settings(paths, env_values={})

    budget = settings.budgets_for_seat("seat.worker.implementation")

    assert budget["budget_profile_ref"] == "worker.implementation.default"
    assert budget["max_steps"] == 128
    assert budget["max_wall_seconds"] == 5400
    assert budget["max_parse_failures"] == 3


def test_role_budget_override_merges_with_runtime_defaults(tmp_path, monkeypatch):
    paths = _write_config_files(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-secret")
    settings = load_boardroom_settings(paths, env_values={})

    budgets = settings.budgets_for_seat("seat.worker.implementation")

    assert budgets == {
        "max_steps": 128,
        "max_parse_failures": 3,
        "max_observation_chars": 24000,
        "max_wall_seconds": 5400,
        "max_actions_per_turn": 8,
        "budget_profile_ref": "worker.implementation.default",
    }
