from __future__ import annotations

import json
import subprocess
from datetime import datetime
from pathlib import Path

import pytest

from app.contracts.runtime import (
    RenderedExecutionMessage,
    RenderedExecutionPayload,
    RenderedExecutionPayloadMeta,
    RenderedExecutionPayloadSummary,
)
from app.core.provider_claude_code import (
    ClaudeCodeProviderConfig,
    ClaudeCodeProviderError,
    invoke_claude_code_response,
)
from app.core.runtime_provider_config import (
    CLAUDE_CODE_PROVIDER_ID,
    OPENAI_COMPAT_PROVIDER_ID,
    RuntimeProviderConfigEntry,
    RuntimeProviderConfigStore,
    RuntimeProviderRoleBinding,
    RuntimeProviderStoredConfig,
    resolve_provider_selection,
)


def _rendered_payload() -> RenderedExecutionPayload:
    return RenderedExecutionPayload(
        meta=RenderedExecutionPayloadMeta(
            bundle_id="ctx_001",
            compile_id="cmp_001",
            compile_request_id="creq_001",
            ticket_id="tkt_001",
            workflow_id="wf_001",
            node_id="node_001",
            compiler_version="context-compiler.min.v1",
            model_profile="boardroom_os.runtime.min",
            render_target="json_messages_v1",
            rendered_at=datetime.fromisoformat("2026-04-07T12:00:00+08:00"),
        ),
        messages=[
            RenderedExecutionMessage(
                role="system",
                channel="SYSTEM_CONTROLS",
                content_type="JSON",
                content_payload={"rules": ["return JSON only"]},
            ),
            RenderedExecutionMessage(
                role="user",
                channel="TASK_DEFINITION",
                content_type="JSON",
                content_payload={"task": "Produce a structured payload."},
            ),
        ],
        summary=RenderedExecutionPayloadSummary(
            total_message_count=2,
            control_message_count=1,
            data_message_count=1,
            retrieval_message_count=0,
            degraded_data_message_count=0,
            reference_message_count=0,
        ),
    )


def test_runtime_provider_store_migrates_legacy_openai_config_to_registry_shape(tmp_path: Path) -> None:
    config_path = tmp_path / "runtime-provider-config.json"
    config_path.write_text(
        json.dumps(
            {
                "mode": "OPENAI_COMPAT",
                "base_url": "https://api.example.test/v1",
                "api_key": "sk-test-secret",
                "model": "gpt-5.3-codex",
                "timeout_sec": 30.0,
                "reasoning_effort": "high",
            }
        ),
        encoding="utf-8",
    )
    store = RuntimeProviderConfigStore(config_path)

    loaded = store.load_saved_config()

    assert loaded is not None
    assert loaded.default_provider_id == OPENAI_COMPAT_PROVIDER_ID
    assert loaded.role_bindings == []
    assert [provider.provider_id for provider in loaded.providers] == [
        OPENAI_COMPAT_PROVIDER_ID,
        CLAUDE_CODE_PROVIDER_ID,
    ]
    openai_provider = next(provider for provider in loaded.providers if provider.provider_id == OPENAI_COMPAT_PROVIDER_ID)
    assert openai_provider.adapter_kind == "openai_compat"
    assert openai_provider.enabled is True
    assert openai_provider.base_url == "https://api.example.test/v1"
    assert openai_provider.api_key == "sk-test-secret"
    assert openai_provider.model == "gpt-5.3-codex"
    claude_provider = next(provider for provider in loaded.providers if provider.provider_id == CLAUDE_CODE_PROVIDER_ID)
    assert claude_provider.adapter_kind == "claude_code_cli"
    assert claude_provider.enabled is False


def test_resolve_provider_selection_prefers_role_binding_over_employee_provider() -> None:
    config = RuntimeProviderStoredConfig(
        default_provider_id=OPENAI_COMPAT_PROVIDER_ID,
        providers=[
            RuntimeProviderConfigEntry(
                provider_id=OPENAI_COMPAT_PROVIDER_ID,
                adapter_kind="openai_compat",
                label="OpenAI Compat",
                enabled=True,
                base_url="https://api.example.test/v1",
                api_key="sk-test-secret",
                model="gpt-5.3-codex",
                timeout_sec=30.0,
                reasoning_effort="medium",
            ),
            RuntimeProviderConfigEntry(
                provider_id=CLAUDE_CODE_PROVIDER_ID,
                adapter_kind="claude_code_cli",
                label="Claude Code",
                enabled=True,
                command_path="/Users/bill/.local/bin/claude",
                model="claude-sonnet-4-6",
                timeout_sec=45.0,
            ),
        ],
        role_bindings=[
            RuntimeProviderRoleBinding(
                target_ref="role_profile:frontend_engineer_primary",
                provider_id=CLAUDE_CODE_PROVIDER_ID,
                model="claude-opus-4-1",
            )
        ],
    )

    selection = resolve_provider_selection(
        config,
        target_ref="role_profile:frontend_engineer_primary",
        employee_provider_id=OPENAI_COMPAT_PROVIDER_ID,
    )

    assert selection is not None
    assert selection.provider.provider_id == CLAUDE_CODE_PROVIDER_ID
    assert selection.preferred_provider_id == CLAUDE_CODE_PROVIDER_ID
    assert selection.preferred_model == "claude-opus-4-1"
    assert selection.binding_target_ref == "role_profile:frontend_engineer_primary"


def test_resolve_provider_selection_falls_back_to_employee_provider_and_default_provider() -> None:
    config = RuntimeProviderStoredConfig(
        default_provider_id=OPENAI_COMPAT_PROVIDER_ID,
        providers=[
            RuntimeProviderConfigEntry(
                provider_id=OPENAI_COMPAT_PROVIDER_ID,
                adapter_kind="openai_compat",
                label="OpenAI Compat",
                enabled=True,
                base_url="https://api.example.test/v1",
                api_key="sk-test-secret",
                model="gpt-5.3-codex",
                timeout_sec=30.0,
                reasoning_effort="medium",
            ),
            RuntimeProviderConfigEntry(
                provider_id=CLAUDE_CODE_PROVIDER_ID,
                adapter_kind="claude_code_cli",
                label="Claude Code",
                enabled=False,
                command_path="/Users/bill/.local/bin/claude",
                model="claude-sonnet-4-6",
                timeout_sec=45.0,
            ),
        ],
        role_bindings=[],
    )

    employee_selection = resolve_provider_selection(
        config,
        target_ref="role_profile:checker_primary",
        employee_provider_id=OPENAI_COMPAT_PROVIDER_ID,
    )
    default_selection = resolve_provider_selection(
        config,
        target_ref="ceo_shadow",
        employee_provider_id=None,
    )

    assert employee_selection is not None
    assert employee_selection.provider.provider_id == OPENAI_COMPAT_PROVIDER_ID
    assert employee_selection.binding_target_ref is None
    assert default_selection is not None
    assert default_selection.provider.provider_id == OPENAI_COMPAT_PROVIDER_ID
    assert default_selection.preferred_model == "gpt-5.3-codex"


def test_invoke_claude_code_response_uses_print_mode_and_json_schema(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def _fake_run(cmd: list[str], *, check: bool, capture_output: bool, text: bool, timeout: float) -> subprocess.CompletedProcess[str]:
        captured["cmd"] = cmd
        captured["check"] = check
        captured["capture_output"] = capture_output
        captured["text"] = text
        captured["timeout"] = timeout
        return subprocess.CompletedProcess(
            args=cmd,
            returncode=0,
            stdout='{"summary":"Claude completed.","options":[],"recommended_option_id":"option_a"}',
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", _fake_run)

    result = invoke_claude_code_response(
        ClaudeCodeProviderConfig(
            command_path="/Users/bill/.local/bin/claude",
            model="claude-sonnet-4-6",
            timeout_sec=45.0,
        ),
        _rendered_payload(),
    )

    assert result.output_text.startswith('{"summary":"Claude completed."')
    assert result.response_id is None
    assert captured["check"] is False
    assert captured["capture_output"] is True
    assert captured["text"] is True
    assert captured["timeout"] == 45.0
    command = captured["cmd"]
    assert isinstance(command, list)
    assert command[:10] == [
        "/Users/bill/.local/bin/claude",
        "--print",
        "--output-format",
        "text",
        "--permission-mode",
        "bypassPermissions",
        "--model",
        "claude-sonnet-4-6",
        "--json-schema",
        '{"type":"object"}',
    ]
    assert "SYSTEM_CONTROLS" in command[-1]
    assert "TASK_DEFINITION" in command[-1]


def test_invoke_claude_code_response_maps_process_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fake_run(cmd: list[str], *, check: bool, capture_output: bool, text: bool, timeout: float) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args=cmd,
            returncode=2,
            stdout="",
            stderr="auth missing",
        )

    monkeypatch.setattr(subprocess, "run", _fake_run)

    with pytest.raises(ClaudeCodeProviderError) as exc_info:
        invoke_claude_code_response(
            ClaudeCodeProviderConfig(
                command_path="/Users/bill/.local/bin/claude",
                model="claude-sonnet-4-6",
                timeout_sec=45.0,
            ),
            _rendered_payload(),
        )

    assert exc_info.value.failure_kind == "PROVIDER_BAD_RESPONSE"
    assert exc_info.value.failure_detail["provider_exit_code"] == 2
