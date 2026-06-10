from __future__ import annotations

import pytest

from tests.config.test_boardroom_config import _write_config_files


STALE_ENV_KEYS = {
    "BOARDROOM_OPENAI_MODEL": "gpt-5.5",
    "BOARDROOM_OPENAI_TIMEOUT_SECONDS": "600",
}


def test_config_loader_rejects_stale_openai_env_keys(tmp_path, monkeypatch):
    from boardroom_os.config.boardroom import load_boardroom_settings

    paths = _write_config_files(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-secret")

    with pytest.raises(ValueError, match="stale env execution config keys are not allowed"):
        load_boardroom_settings(paths, env_values=STALE_ENV_KEYS)


def test_config_loader_rejects_atomic_budget_env_keys(tmp_path, monkeypatch):
    from boardroom_os.config.boardroom import load_boardroom_settings

    paths = _write_config_files(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-secret")

    with pytest.raises(ValueError, match="stale env execution config keys are not allowed"):
        load_boardroom_settings(paths, env_values={"BOARDROOM_ATOMIC_MAX_STEPS": "20"})


def test_config_loader_rejects_unknown_provider_type(tmp_path, monkeypatch):
    from boardroom_os.config.boardroom import load_boardroom_settings

    paths = _write_config_files(tmp_path)
    providers_text = paths.providers_config.read_text(encoding="utf-8")
    paths.providers_config.write_text(
        providers_text.replace("provider_type: openai_compatible", "provider_type: anthropic_native"),
        encoding="utf-8",
    )
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-secret")

    with pytest.raises(ValueError, match="provider_type must be openai_compatible"):
        load_boardroom_settings(paths, env_values={})


def test_config_loader_rejects_role_unknown_provider_ref(tmp_path, monkeypatch):
    from boardroom_os.config.boardroom import load_boardroom_settings

    paths = _write_config_files(tmp_path)
    roles_text = paths.roles_config.read_text(encoding="utf-8")
    paths.roles_config.write_text(
        roles_text.replace("provider.openai-compatible.primary", "provider.missing"),
        encoding="utf-8",
    )
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-secret")

    with pytest.raises(ValueError, match="unknown provider_profile_ref"):
        load_boardroom_settings(paths, env_values={})


def test_config_loader_rejects_role_inline_provider_transport_param(tmp_path, monkeypatch):
    from boardroom_os.config.boardroom import load_boardroom_settings

    paths = _write_config_files(tmp_path)
    roles_text = paths.roles_config.read_text(encoding="utf-8")
    paths.roles_config.write_text(
        roles_text + "    base_url: https://api.example.invalid/v1\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-secret")

    with pytest.raises(ValueError, match="extra inputs are not permitted"):
        load_boardroom_settings(paths, env_values={})


def test_config_loader_rejects_missing_api_key_env(tmp_path):
    from boardroom_os.config.boardroom import load_boardroom_settings

    paths = _write_config_files(tmp_path)

    with pytest.raises(ValueError, match="provider api key env is required"):
        load_boardroom_settings(paths, env_values={})


def test_config_loader_rejects_runtime_without_submit_result(tmp_path, monkeypatch):
    from boardroom_os.config.boardroom import load_boardroom_settings

    paths = _write_config_files(tmp_path)
    runtime_text = paths.runtime_config.read_text(encoding="utf-8")
    paths.runtime_config.write_text(runtime_text.replace("submit_result", "submit_missing"), encoding="utf-8")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-secret")

    with pytest.raises(ValueError, match="atomic_agent.default_tools must include submit_result"):
        load_boardroom_settings(paths, env_values={})


def test_config_loader_rejects_provider_executor_for_implementation(tmp_path, monkeypatch):
    from boardroom_os.config.boardroom import load_boardroom_settings

    paths = _write_config_files(tmp_path)
    runtime_text = paths.runtime_config.read_text(encoding="utf-8")
    paths.runtime_config.write_text(
        runtime_text.replace("implementation_executor: atomic_agent", "implementation_executor: provider_executor"),
        encoding="utf-8",
    )
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-secret")

    with pytest.raises(ValueError, match="implementation_executor must be atomic_agent"):
        load_boardroom_settings(paths, env_values={})


def test_config_loader_rejects_unsupported_provider_request_param(tmp_path, monkeypatch):
    from boardroom_os.config.boardroom import load_boardroom_settings

    paths = _write_config_files(tmp_path)
    providers_text = paths.providers_config.read_text(encoding="utf-8")
    paths.providers_config.write_text(providers_text + "    tool_choice: auto\n", encoding="utf-8")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-secret")

    with pytest.raises(ValueError, match="extra inputs are not permitted"):
        load_boardroom_settings(paths, env_values={})


def test_config_loader_rejects_missing_contract_lock(tmp_path, monkeypatch):
    from boardroom_os.config.boardroom import load_boardroom_settings

    paths = _write_config_files(tmp_path)
    runtime_text = paths.runtime_config.read_text(encoding="utf-8")
    paths.runtime_config.write_text(
        runtime_text.replace("contract_lock_ref: doc/06-reference/atomic-agent-contract-lock.md", "contract_lock_ref: missing-lock.md"),
        encoding="utf-8",
    )
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-secret")

    with pytest.raises(ValueError, match="atomic-agent contract lock is required"):
        load_boardroom_settings(paths, env_values={})


def test_config_loader_rejects_worktree_atomic_agent_path(tmp_path, monkeypatch):
    from boardroom_os.config.boardroom import resolve_atomic_agent_path

    path = tmp_path / ".worktrees" / "atomic-agent"
    path.mkdir(parents=True)
    monkeypatch.setenv("BOARDROOM_ATOMIC_AGENT_PATH", str(path))

    with pytest.raises(ValueError, match="must not point at .worktrees"):
        resolve_atomic_agent_path(default_path="../atomic-agent")
