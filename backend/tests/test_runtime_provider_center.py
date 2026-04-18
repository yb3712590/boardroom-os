from __future__ import annotations

from pathlib import Path

from app.contracts.commands import RuntimeProviderUpsertCommand
from app.core.runtime_provider_config import (
    RuntimeProviderConfigStore,
    RuntimeProviderStoredConfig,
    build_provider_model_entry_ref,
    resolve_provider_failover_selections,
    resolve_provider_selection,
    save_runtime_provider_command,
)


def _build_upsert_command() -> RuntimeProviderUpsertCommand:
    return RuntimeProviderUpsertCommand.model_validate(
        {
            "providers": [
                {
                    "provider_id": "prov_primary",
                    "type": "openai_responses_stream",
                    "base_url": "https://api.example.test/v1",
                    "api_key": "sk-test-secret",
                    "alias": "",
                    "preferred_model": "gpt-5.3-codex",
                    "max_context_window": None,
                    "enabled": True,
                }
            ],
            "provider_model_entries": [
                {
                    "provider_id": "prov_primary",
                    "model_name": "gpt-5.3-codex",
                }
            ],
            "role_bindings": [
                {
                    "target_ref": "ceo_shadow",
                    "provider_model_entry_refs": [
                        build_provider_model_entry_ref("prov_primary", "gpt-5.3-codex")
                    ],
                    "max_context_window_override": None,
                },
                {
                    "target_ref": "role_profile:frontend_engineer_primary",
                    "provider_model_entry_refs": [],
                    "max_context_window_override": None,
                },
            ],
            "idempotency_key": "runtime-provider-upsert:center-test",
        }
    )


def test_runtime_provider_store_discards_legacy_fixed_registry_and_starts_empty(tmp_path: Path) -> None:
    config_path = tmp_path / "runtime-provider-config.json"
    config_path.write_text(
        """
        {
          "default_provider_id": "prov_openai_compat",
          "providers": [
            {
              "provider_id": "prov_openai_compat",
              "adapter_kind": "openai_compat",
              "label": "OpenAI Compat",
              "enabled": true,
              "base_url": "https://api.example.test/v1",
              "api_key": "sk-test-secret",
              "model": "gpt-5.3-codex",
              "timeout_sec": 30.0
            }
          ],
          "role_bindings": []
        }
        """,
        encoding="utf-8",
    )
    store = RuntimeProviderConfigStore(config_path)

    loaded = store.load_saved_config()

    assert loaded == RuntimeProviderStoredConfig(
        providers=[],
        provider_model_entries=[],
        role_bindings=[],
    )


def test_save_runtime_provider_command_normalizes_alias_window_and_model_entry_ref(tmp_path: Path) -> None:
    store = RuntimeProviderConfigStore(tmp_path / "runtime-provider-config.json")

    ack = save_runtime_provider_command(store, _build_upsert_command())
    loaded = store.load_saved_config()

    assert ack.status == "ACCEPTED"
    assert loaded is not None
    assert loaded.providers[0].alias == "example"
    assert loaded.providers[0].max_context_window == 1000000
    assert loaded.providers[0].reasoning_effort == "high"
    assert loaded.providers[0].timeout_sec == 300.0
    assert loaded.providers[0].connect_timeout_sec == 10.0
    assert loaded.providers[0].write_timeout_sec == 20.0
    assert loaded.providers[0].first_token_timeout_sec == 300.0
    assert loaded.providers[0].stream_idle_timeout_sec == 300.0
    assert loaded.providers[0].request_total_timeout_sec == 300.0
    assert loaded.providers[0].retry_backoff_schedule_sec == [1.0, 2.0, 4.0, 8.0, 16.0, 32.0, 60.0, 60.0, 60.0]
    assert loaded.provider_model_entries[0].entry_ref == build_provider_model_entry_ref(
        "prov_primary",
        "gpt-5.3-codex",
    )


def test_resolve_provider_selection_inherits_ceo_binding_and_provider_window(tmp_path: Path) -> None:
    store = RuntimeProviderConfigStore(tmp_path / "runtime-provider-config.json")
    save_runtime_provider_command(store, _build_upsert_command())
    loaded = store.load_saved_config()

    selection = resolve_provider_selection(
        loaded,
        target_ref="role_profile:frontend_engineer_primary",
        employee_provider_id=None,
    )

    assert selection is not None
    assert selection.provider.provider_id == "prov_primary"
    assert selection.provider_model_entry_ref == build_provider_model_entry_ref("prov_primary", "gpt-5.3-codex")
    assert selection.actual_model == "gpt-5.3-codex"
    assert selection.effective_max_context_window == 1000000
    assert selection.effective_reasoning_effort == "high"


def test_resolve_provider_selection_prefers_role_binding_and_window_override(tmp_path: Path) -> None:
    store = RuntimeProviderConfigStore(tmp_path / "runtime-provider-config.json")
    payload = {
        "providers": [
            {
                "provider_id": "prov_primary",
                "type": "openai_responses_stream",
                "base_url": "https://api.example.test/v1",
                "api_key": "sk-test-secret",
                "alias": "",
                "preferred_model": "gpt-5.3-codex",
                "max_context_window": None,
                "enabled": True,
            },
            {
                "provider_id": "prov_backup",
                "type": "openai_responses_non_stream",
                "base_url": "https://api.backup.test/v1",
                "api_key": "sk-backup-secret",
                "alias": "backup",
                "preferred_model": "gpt-4.1",
                "max_context_window": 270000,
                "enabled": True,
            },
        ],
        "provider_model_entries": [
            {
                "provider_id": "prov_primary",
                "model_name": "gpt-5.3-codex",
            },
            {
                "provider_id": "prov_backup",
                "model_name": "gpt-4.1",
            },
        ],
        "role_bindings": [
            {
                "target_ref": "ceo_shadow",
                "provider_model_entry_refs": [
                    build_provider_model_entry_ref("prov_primary", "gpt-5.3-codex")
                ],
                "max_context_window_override": None,
            },
            {
                "target_ref": "role_profile:frontend_engineer_primary",
                "provider_model_entry_refs": [
                    build_provider_model_entry_ref("prov_backup", "gpt-4.1")
                ],
                "max_context_window_override": 180000,
                "reasoning_effort_override": "xhigh",
            },
        ],
        "idempotency_key": "runtime-provider-upsert:center-role-override",
    }
    command = RuntimeProviderUpsertCommand.model_validate(payload)
    save_runtime_provider_command(store, command)
    loaded = store.load_saved_config()

    selection = resolve_provider_selection(
        loaded,
        target_ref="role_profile:frontend_engineer_primary",
        employee_provider_id=None,
    )

    assert selection is not None
    assert selection.provider.provider_id == "prov_backup"
    assert selection.actual_model == "gpt-4.1"
    assert selection.effective_max_context_window == 180000
    assert selection.effective_reasoning_effort == "xhigh"


def test_resolve_provider_failover_selections_uses_remaining_binding_entries_before_provider_fallbacks(
    tmp_path: Path,
) -> None:
    class _HealthyRepository:
        @staticmethod
        def has_open_circuit_breaker_for_provider(_provider_id: str) -> bool:
            return False

    store = RuntimeProviderConfigStore(tmp_path / "runtime-provider-config.json")
    payload = {
        "providers": [
            {
                "provider_id": "prov_primary",
                "type": "openai_responses_stream",
                "base_url": "https://api.primary.test/v1",
                "api_key": "sk-primary-secret",
                "alias": "primary",
                "preferred_model": "gpt-5.3-codex",
                "max_context_window": None,
                "enabled": True,
                "fallback_provider_ids": ["prov_tail_backup"],
            },
            {
                "provider_id": "prov_binding_backup",
                "type": "openai_responses_non_stream",
                "base_url": "https://api.binding-backup.test/v1",
                "api_key": "sk-binding-backup",
                "alias": "binding-backup",
                "preferred_model": "gpt-4.1",
                "max_context_window": None,
                "enabled": True,
            },
            {
                "provider_id": "prov_tail_backup",
                "type": "openai_responses_non_stream",
                "base_url": "https://api.tail-backup.test/v1",
                "api_key": "sk-tail-backup",
                "alias": "tail-backup",
                "preferred_model": "gpt-4.1-mini",
                "max_context_window": None,
                "enabled": True,
            },
        ],
        "provider_model_entries": [
            {
                "provider_id": "prov_primary",
                "model_name": "gpt-5.3-codex",
            },
            {
                "provider_id": "prov_binding_backup",
                "model_name": "gpt-4.1",
            },
            {
                "provider_id": "prov_tail_backup",
                "model_name": "gpt-4.1-mini",
            },
        ],
        "role_bindings": [
            {
                "target_ref": "role_profile:frontend_engineer_primary",
                "provider_model_entry_refs": [
                    build_provider_model_entry_ref("prov_primary", "gpt-5.3-codex"),
                    build_provider_model_entry_ref("prov_binding_backup", "gpt-4.1"),
                ],
                "max_context_window_override": None,
                "reasoning_effort_override": "high",
            }
        ],
        "idempotency_key": "runtime-provider-upsert:binding-chain-failover",
    }
    command = RuntimeProviderUpsertCommand.model_validate(payload)
    save_runtime_provider_command(store, command)
    loaded = store.load_saved_config()

    primary_selection = resolve_provider_selection(
        loaded,
        target_ref="role_profile:frontend_engineer_primary",
        employee_provider_id=None,
    )
    assert primary_selection is not None

    failover_selections = resolve_provider_failover_selections(
        loaded,
        _HealthyRepository(),
        target_ref="role_profile:frontend_engineer_primary",
        primary_selection=primary_selection,
    )

    assert [item.provider.provider_id for item in failover_selections] == [
        "prov_binding_backup",
        "prov_tail_backup",
    ]


def test_runtime_provider_store_normalizes_legacy_null_reasoning_to_high(tmp_path: Path) -> None:
    config_path = tmp_path / "runtime-provider-config.json"
    config_path.write_text(
        """
        {
          "default_provider_id": "prov_primary",
          "providers": [
            {
              "provider_id": "prov_primary",
              "type": "openai_responses_stream",
              "adapter_kind": "openai_compat",
              "label": "example",
              "enabled": true,
              "base_url": "https://api.example.test/v1",
              "api_key": "sk-test-secret",
              "alias": "example",
              "preferred_model": "gpt-5.3-codex",
              "model": "gpt-5.3-codex",
              "max_context_window": 1000000,
              "timeout_sec": 30.0,
              "reasoning_effort": null
            }
          ],
          "provider_model_entries": [
            {
              "entry_ref": "prov_primary::gpt-5.3-codex",
              "provider_id": "prov_primary",
              "model_name": "gpt-5.3-codex"
            }
          ],
          "role_bindings": [
            {
              "target_ref": "ceo_shadow",
              "provider_model_entry_refs": ["prov_primary::gpt-5.3-codex"],
              "max_context_window_override": null,
              "reasoning_effort_override": null
            }
          ]
        }
        """,
        encoding="utf-8",
    )
    store = RuntimeProviderConfigStore(config_path)

    loaded = store.load_saved_config()
    selection = resolve_provider_selection(
        loaded,
        target_ref="ceo_shadow",
        employee_provider_id=None,
    )

    assert loaded is not None
    assert loaded.providers[0].reasoning_effort == "high"
    assert selection is not None
    assert selection.effective_reasoning_effort == "high"
