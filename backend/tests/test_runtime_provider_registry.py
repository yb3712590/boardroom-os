from __future__ import annotations

import json
import subprocess
from datetime import datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.contracts.commands import RuntimeProviderUpsertCommand
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
from app.core.runtime import _resolve_ticket_target_ref
from app.core.runtime_provider_config import (
    CLAUDE_CODE_PROVIDER_ID,
    OPENAI_COMPAT_PROVIDER_ID,
    RuntimeProviderConfigEntry,
    RuntimeProviderConfigStore,
    RuntimeProviderRoleBinding,
    RuntimeProviderStoredConfig,
    provider_meets_target_capability_floor,
    runtime_provider_health_details,
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
    assert [tag.value for tag in openai_provider.capability_tags] == [
        "structured_output",
        "planning",
        "implementation",
        "review",
    ]
    assert openai_provider.fallback_provider_ids == []
    assert [tag.value for tag in claude_provider.capability_tags] == [
        "structured_output",
        "planning",
        "implementation",
        "review",
    ]
    assert claude_provider.fallback_provider_ids == []


def test_runtime_provider_store_round_trips_capabilities_and_fallback_ids(tmp_path: Path) -> None:
    config_path = tmp_path / "runtime-provider-config.json"
    store = RuntimeProviderConfigStore(config_path)
    store.save_config(
        RuntimeProviderStoredConfig(
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
                    reasoning_effort="high",
                    capability_tags=["structured_output", "planning", "implementation"],
                    fallback_provider_ids=[CLAUDE_CODE_PROVIDER_ID],
                ),
                RuntimeProviderConfigEntry(
                    provider_id=CLAUDE_CODE_PROVIDER_ID,
                    adapter_kind="claude_code_cli",
                    label="Claude Code CLI",
                    enabled=True,
                    command_path="/Users/bill/.local/bin/claude",
                    model="claude-sonnet-4-6",
                    timeout_sec=45.0,
                    capability_tags=["structured_output", "planning", "review"],
                    fallback_provider_ids=[],
                ),
            ],
            role_bindings=[],
        )
    )

    loaded = store.load_saved_config()

    assert loaded is not None
    openai_provider = next(provider for provider in loaded.providers if provider.provider_id == OPENAI_COMPAT_PROVIDER_ID)
    claude_provider = next(provider for provider in loaded.providers if provider.provider_id == CLAUDE_CODE_PROVIDER_ID)
    assert openai_provider.capability_tags == ["structured_output", "planning", "implementation"]
    assert openai_provider.fallback_provider_ids == [CLAUDE_CODE_PROVIDER_ID]
    assert claude_provider.capability_tags == ["structured_output", "planning", "review"]
    assert claude_provider.fallback_provider_ids == []


def test_runtime_provider_upsert_rejects_invalid_capability_and_fallback_config() -> None:
    with pytest.raises(ValidationError):
        RuntimeProviderUpsertCommand.model_validate(
            {
                "default_provider_id": OPENAI_COMPAT_PROVIDER_ID,
                "providers": [
                    {
                        "provider_id": OPENAI_COMPAT_PROVIDER_ID,
                        "adapter_kind": "openai_compat",
                        "label": "OpenAI Compat",
                        "enabled": True,
                        "base_url": "https://api.example.test/v1",
                        "api_key": "sk-test-secret",
                        "model": "gpt-5.3-codex",
                        "timeout_sec": 30.0,
                        "reasoning_effort": "high",
                        "command_path": None,
                        "capability_tags": ["structured_output", "structured_output", "unknown_capability"],
                        "fallback_provider_ids": [OPENAI_COMPAT_PROVIDER_ID, "prov_missing", OPENAI_COMPAT_PROVIDER_ID],
                    }
                ],
                "role_bindings": [],
                "idempotency_key": "runtime-provider-upsert:invalid",
            }
        )


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
                capability_tags=["structured_output", "planning"],
            ),
            RuntimeProviderConfigEntry(
                provider_id=CLAUDE_CODE_PROVIDER_ID,
                adapter_kind="claude_code_cli",
                label="Claude Code",
                enabled=True,
                command_path="/Users/bill/.local/bin/claude",
                model="claude-sonnet-4-6",
                timeout_sec=45.0,
                capability_tags=["structured_output", "planning", "implementation"],
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


def test_resolve_provider_selection_prefers_ticket_runtime_preference_when_allowed() -> None:
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
                capability_tags=["structured_output", "implementation"],
                cost_tier="standard",
                participation_policy="always_allowed",
            ),
            RuntimeProviderConfigEntry(
                provider_id=CLAUDE_CODE_PROVIDER_ID,
                adapter_kind="claude_code_cli",
                label="Claude Code",
                enabled=True,
                command_path="/Users/bill/.local/bin/claude",
                model="claude-sonnet-4-6",
                timeout_sec=45.0,
                capability_tags=["structured_output", "planning", "implementation"],
                cost_tier="premium",
                participation_policy="always_allowed",
            ),
        ],
        role_bindings=[
            RuntimeProviderRoleBinding(
                target_ref="execution_target:frontend_build",
                provider_id=OPENAI_COMPAT_PROVIDER_ID,
                model="gpt-5.3-codex",
            )
        ],
    )

    selection = resolve_provider_selection(
        config,
        target_ref="execution_target:frontend_build",
        employee_provider_id=OPENAI_COMPAT_PROVIDER_ID,
        runtime_preference={
            "preferred_provider_id": CLAUDE_CODE_PROVIDER_ID,
            "preferred_model": "claude-opus-4-1",
        },
    )

    assert selection is not None
    assert selection.provider.provider_id == CLAUDE_CODE_PROVIDER_ID
    assert selection.preferred_provider_id == CLAUDE_CODE_PROVIDER_ID
    assert selection.preferred_model == "claude-opus-4-1"
    assert selection.actual_model == "claude-opus-4-1"
    assert selection.selection_reason == "ticket_runtime_preference"
    assert selection.policy_reason is None


def test_resolve_provider_selection_downgrades_low_frequency_only_ticket_preference_for_high_frequency_target() -> None:
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
                capability_tags=["structured_output", "implementation"],
                cost_tier="standard",
                participation_policy="always_allowed",
            ),
            RuntimeProviderConfigEntry(
                provider_id=CLAUDE_CODE_PROVIDER_ID,
                adapter_kind="claude_code_cli",
                label="Claude Code",
                enabled=True,
                command_path="/Users/bill/.local/bin/claude",
                model="claude-sonnet-4-6",
                timeout_sec=45.0,
                capability_tags=["structured_output", "planning", "implementation"],
                cost_tier="premium",
                participation_policy="low_frequency_only",
            ),
        ],
        role_bindings=[
            RuntimeProviderRoleBinding(
                target_ref="execution_target:frontend_build",
                provider_id=OPENAI_COMPAT_PROVIDER_ID,
                model="gpt-5.3-codex",
            )
        ],
    )

    selection = resolve_provider_selection(
        config,
        target_ref="execution_target:frontend_build",
        employee_provider_id=OPENAI_COMPAT_PROVIDER_ID,
        runtime_preference={
            "preferred_provider_id": CLAUDE_CODE_PROVIDER_ID,
            "preferred_model": "claude-opus-4-1",
        },
    )

    assert selection is not None
    assert selection.provider.provider_id == OPENAI_COMPAT_PROVIDER_ID
    assert selection.preferred_provider_id == CLAUDE_CODE_PROVIDER_ID
    assert selection.preferred_model == "claude-opus-4-1"
    assert selection.actual_model == "gpt-5.3-codex"
    assert selection.selection_reason == "role_binding_fallback_after_ticket_runtime_preference"
    assert selection.policy_reason == "preferred_provider_low_frequency_only_for_high_frequency_target"


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
                capability_tags=["structured_output", "planning", "review"],
            ),
            RuntimeProviderConfigEntry(
                provider_id=CLAUDE_CODE_PROVIDER_ID,
                adapter_kind="claude_code_cli",
                label="Claude Code",
                enabled=False,
                command_path="/Users/bill/.local/bin/claude",
                model="claude-sonnet-4-6",
                timeout_sec=45.0,
                capability_tags=["structured_output", "planning", "review"],
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


def test_resolve_provider_selection_skips_provider_that_misses_target_capability_floor() -> None:
    config = RuntimeProviderStoredConfig(
        default_provider_id=CLAUDE_CODE_PROVIDER_ID,
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
                capability_tags=["structured_output", "implementation"],
            ),
            RuntimeProviderConfigEntry(
                provider_id=CLAUDE_CODE_PROVIDER_ID,
                adapter_kind="claude_code_cli",
                label="Claude Code",
                enabled=True,
                command_path="/Users/bill/.local/bin/claude",
                model="claude-sonnet-4-6",
                timeout_sec=45.0,
                capability_tags=["structured_output", "planning"],
            ),
        ],
        role_bindings=[
            RuntimeProviderRoleBinding(
                target_ref="ceo_shadow",
                provider_id=OPENAI_COMPAT_PROVIDER_ID,
                model="gpt-5.3-codex",
            )
        ],
    )

    selection = resolve_provider_selection(config, target_ref="ceo_shadow", employee_provider_id=None)

    assert selection is not None
    assert selection.provider.provider_id == CLAUDE_CODE_PROVIDER_ID
    assert selection.preferred_provider_id == CLAUDE_CODE_PROVIDER_ID
    assert selection.preferred_model == "claude-sonnet-4-6"
    assert provider_meets_target_capability_floor(selection.provider, "ceo_shadow") is True


def test_resolve_provider_selection_allows_execution_target_to_use_legacy_role_binding() -> None:
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
                capability_tags=["structured_output", "implementation"],
            ),
            RuntimeProviderConfigEntry(
                provider_id=CLAUDE_CODE_PROVIDER_ID,
                adapter_kind="claude_code_cli",
                label="Claude Code",
                enabled=True,
                command_path="/Users/bill/.local/bin/claude",
                model="claude-sonnet-4-6",
                timeout_sec=45.0,
                capability_tags=["structured_output", "planning", "implementation"],
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
        target_ref="execution_target:frontend_build",
        employee_provider_id=OPENAI_COMPAT_PROVIDER_ID,
    )

    assert selection is not None
    assert selection.provider.provider_id == CLAUDE_CODE_PROVIDER_ID
    assert selection.preferred_provider_id == CLAUDE_CODE_PROVIDER_ID
    assert selection.preferred_model == "claude-opus-4-1"
    assert selection.binding_target_ref == "execution_target:frontend_build"


def test_resolve_ticket_target_ref_prefers_execution_contract_target() -> None:
    assert _resolve_ticket_target_ref(
        {
            "role_profile_ref": "frontend_engineer_primary",
            "output_schema_ref": "implementation_bundle",
            "execution_contract": {
                "execution_target_ref": "execution_target:frontend_closeout",
                "required_capability_tags": ["structured_output", "implementation"],
                "runtime_contract_version": "execution_contract_v1",
            },
        }
    ) == "execution_target:frontend_closeout"


def test_runtime_provider_health_details_reports_command_not_found_for_claude(client) -> None:
    repository = client.app.state.repository
    health_status, health_reason = runtime_provider_health_details(
        RuntimeProviderConfigEntry(
            provider_id=CLAUDE_CODE_PROVIDER_ID,
            adapter_kind="claude_code_cli",
            label="Claude Code",
            enabled=True,
            command_path="/path/that/does/not/exist/claude",
            model="claude-sonnet-4-6",
            timeout_sec=45.0,
            capability_tags=["structured_output", "planning", "implementation", "review"],
        ),
        repository,
    )

    assert health_status == "COMMAND_NOT_FOUND"
    assert "could not be resolved" in health_reason


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
