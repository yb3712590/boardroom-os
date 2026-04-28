from __future__ import annotations

import json
from pathlib import Path

from app.contracts.commands import RuntimeProviderUpsertCommand
from app.core.runtime_provider_config import (
    RuntimeProviderConfigEntry,
    RuntimeProviderModelEntry,
    RuntimeProviderRoleBinding,
    RuntimeProviderConfigStore,
    RuntimeProviderStoredConfig,
    build_provider_model_entry_ref,
    resolve_runtime_provider_config,
    resolve_provider_failover_selections,
    resolve_provider_selection,
    save_runtime_provider_command,
)


def _shard_dir(config_path: Path) -> Path:
    return Path(f"{config_path}.d")


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _provider_config(
    *,
    default_provider_id: str | None = "prov_default",
    include_ceo_binding: bool = True,
    include_target_binding: bool = False,
) -> RuntimeProviderStoredConfig:
    providers = [
        RuntimeProviderConfigEntry(
            provider_id="prov_default",
            adapter_kind="openai_compat",
            label="Default",
            enabled=True,
            base_url="https://api.default.test/v1",
            api_key="sk-default",
            preferred_model="gpt-5.4",
        ),
        RuntimeProviderConfigEntry(
            provider_id="prov_employee",
            adapter_kind="openai_compat",
            label="Employee",
            enabled=True,
            base_url="https://api.employee.test/v1",
            api_key="sk-employee",
            preferred_model="gpt-5.4",
        ),
        RuntimeProviderConfigEntry(
            provider_id="prov_role",
            adapter_kind="openai_compat",
            label="Role",
            enabled=True,
            base_url="https://api.role.test/v1",
            api_key="sk-role",
            preferred_model="gpt-5.4",
        ),
    ]
    entries = [
        RuntimeProviderModelEntry(
            entry_ref=build_provider_model_entry_ref(provider.provider_id, "gpt-5.4"),
            provider_id=provider.provider_id,
            model_name="gpt-5.4",
        )
        for provider in providers
    ]
    bindings = []
    if include_ceo_binding:
        bindings.append(
            RuntimeProviderRoleBinding(
                target_ref="ceo_shadow",
                provider_model_entry_refs=[build_provider_model_entry_ref("prov_default", "gpt-5.4")],
            )
        )
    if include_target_binding:
        bindings.append(
            RuntimeProviderRoleBinding(
                target_ref="role_profile:architect_primary",
                provider_model_entry_refs=[build_provider_model_entry_ref("prov_role", "gpt-5.4")],
            )
        )
    return RuntimeProviderStoredConfig(
        default_provider_id=default_provider_id,
        providers=providers,
        provider_model_entries=entries,
        role_bindings=bindings,
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


def test_runtime_provider_store_loads_sharded_config_without_snapshot(tmp_path: Path) -> None:
    config_path = tmp_path / "runtime-provider-config.json"
    shard_dir = _shard_dir(config_path)
    _write_json(
        shard_dir / "provider.prov_secondary.json",
        {
            "provider_id": "prov_secondary",
            "type": "openai_responses_non_stream",
            "base_url": "https://api.secondary.test/v1",
            "api_key": "sk-secondary-secret",
            "alias": "secondary",
            "preferred_model": "gpt-4.1",
            "max_context_window": 270000,
            "enabled": True,
            "reasoning_effort": "medium",
        },
    )
    _write_json(
        shard_dir / "provider.prov_primary.json",
        {
            "provider_id": "prov_primary",
            "type": "openai_responses_stream",
            "base_url": "https://api.primary.test/v1",
            "api_key": "sk-primary-secret",
            "alias": "primary",
            "preferred_model": "gpt-5.3-codex",
            "max_context_window": 1000000,
            "enabled": True,
            "fallback_provider_ids": ["prov_secondary"],
        },
    )
    _write_json(
        shard_dir / "routing.json",
        {
            "default_provider_id": "prov_primary",
            "provider_model_entries": [
                {
                    "provider_id": "prov_primary",
                    "model_name": "gpt-5.3-codex",
                },
                {
                    "provider_id": "prov_secondary",
                    "model_name": "gpt-4.1",
                },
            ],
            "role_bindings": [
                {
                    "target_ref": "ceo_shadow",
                    "provider_model_entry_refs": ["prov_primary::gpt-5.3-codex"],
                    "max_context_window_override": None,
                    "reasoning_effort_override": None,
                }
            ],
        },
    )
    store = RuntimeProviderConfigStore(config_path)

    loaded = store.load_saved_config()

    assert loaded is not None
    assert loaded.default_provider_id == "prov_primary"
    assert [provider.provider_id for provider in loaded.providers] == ["prov_primary", "prov_secondary"]
    assert loaded.providers[0].fallback_provider_ids == ["prov_secondary"]
    assert [entry.entry_ref for entry in loaded.provider_model_entries] == [
        "prov_primary::gpt-5.3-codex",
        "prov_secondary::gpt-4.1",
    ]
    assert loaded.role_bindings[0].target_ref == "ceo_shadow"


def test_runtime_provider_store_prefers_shards_over_legacy_snapshot(tmp_path: Path) -> None:
    config_path = tmp_path / "runtime-provider-config.json"
    _write_json(
        config_path,
        {
            "default_provider_id": "prov_legacy",
            "providers": [
                {
                    "provider_id": "prov_legacy",
                    "type": "openai_responses_stream",
                    "base_url": "https://api.legacy.test/v1",
                    "api_key": "sk-legacy-secret",
                    "alias": "legacy",
                    "preferred_model": "gpt-4.1",
                    "enabled": True,
                }
            ],
            "provider_model_entries": [
                {
                    "provider_id": "prov_legacy",
                    "model_name": "gpt-4.1",
                }
            ],
            "role_bindings": [],
        },
    )
    shard_dir = _shard_dir(config_path)
    _write_json(
        shard_dir / "provider.prov_sharded.json",
        {
            "provider_id": "prov_sharded",
            "type": "openai_responses_stream",
            "base_url": "https://api.sharded.test/v1",
            "api_key": "sk-sharded-secret",
            "alias": "sharded",
            "preferred_model": "gpt-5.3-codex",
            "enabled": True,
        },
    )
    _write_json(
        shard_dir / "routing.json",
        {
            "default_provider_id": "prov_sharded",
            "provider_model_entries": [
                {
                    "provider_id": "prov_sharded",
                    "model_name": "gpt-5.3-codex",
                }
            ],
            "role_bindings": [],
        },
    )
    store = RuntimeProviderConfigStore(config_path)

    loaded = store.load_saved_config()

    assert loaded is not None
    assert loaded.default_provider_id == "prov_sharded"
    assert [provider.provider_id for provider in loaded.providers] == ["prov_sharded"]


def test_save_runtime_provider_command_writes_shards_and_compat_snapshot(tmp_path: Path) -> None:
    config_path = tmp_path / "runtime-provider-config.json"
    store = RuntimeProviderConfigStore(config_path)

    save_runtime_provider_command(store, _build_upsert_command())

    shard_dir = _shard_dir(config_path)
    provider_payload = _read_json(shard_dir / "provider.prov_primary.json")
    routing_payload = _read_json(shard_dir / "routing.json")
    snapshot_payload = _read_json(config_path)

    assert provider_payload["provider_id"] == "prov_primary"
    assert provider_payload["preferred_model"] == "gpt-5.3-codex"
    assert provider_payload["fallback_provider_ids"] == []
    assert "providers" not in provider_payload
    assert "provider_model_entries" not in provider_payload
    assert "role_bindings" not in provider_payload
    assert routing_payload["default_provider_id"] == "prov_primary"
    assert routing_payload["provider_model_entries"] == [
        {
            "model_name": "gpt-5.3-codex",
            "provider_id": "prov_primary",
        }
    ]
    assert routing_payload["role_bindings"][0]["target_ref"] == "ceo_shadow"
    assert snapshot_payload["providers"][0]["provider_id"] == "prov_primary"
    assert snapshot_payload["provider_model_entries"][0]["entry_ref"] == "prov_primary::gpt-5.3-codex"


def test_save_runtime_provider_command_replaces_shard_directory_and_removes_stale_provider_file(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "runtime-provider-config.json"
    store = RuntimeProviderConfigStore(config_path)
    save_runtime_provider_command(store, _build_upsert_command())
    stale_provider_path = _shard_dir(config_path) / "provider.prov_deleted.json"
    _write_json(
        stale_provider_path,
        {
            "provider_id": "prov_deleted",
            "type": "openai_responses_stream",
            "base_url": "https://api.deleted.test/v1",
            "api_key": "sk-deleted-secret",
            "alias": "deleted",
            "preferred_model": "gpt-4.1",
            "enabled": True,
        },
    )

    save_runtime_provider_command(store, _build_upsert_command())

    assert not stale_provider_path.exists()
    assert (_shard_dir(config_path) / "provider.prov_primary.json").exists()


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


def test_env_backed_provider_config_defaults_legacy_timeout_to_large_value(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("BOARDROOM_OS_PROVIDER_OPENAI_COMPAT_BASE_URL", "https://api.env.test/v1/")
    monkeypatch.setenv("BOARDROOM_OS_PROVIDER_OPENAI_COMPAT_API_KEY", "sk-env-secret")
    monkeypatch.setenv("BOARDROOM_OS_PROVIDER_OPENAI_COMPAT_MODEL", "gpt-5.4")
    monkeypatch.delenv("BOARDROOM_OS_PROVIDER_OPENAI_COMPAT_TIMEOUT_SEC", raising=False)
    store = RuntimeProviderConfigStore(tmp_path / "runtime-provider-config.json")

    loaded = resolve_runtime_provider_config(store)

    assert loaded.providers[0].timeout_sec == 7200.0
    assert loaded.providers[0].first_token_timeout_sec == 300.0
    assert loaded.providers[0].stream_idle_timeout_sec == 300.0
    assert loaded.providers[0].request_total_timeout_sec is None


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
    assert loaded.providers[0].request_total_timeout_sec is None
    assert loaded.providers[0].retry_backoff_schedule_sec == [1.0, 2.0, 4.0, 8.0, 16.0, 32.0, 60.0, 60.0, 60.0]
    assert loaded.provider_model_entries[0].entry_ref == build_provider_model_entry_ref(
        "prov_primary",
        "gpt-5.3-codex",
    )


def test_save_runtime_provider_command_preserves_explicit_request_total_timeout(tmp_path: Path) -> None:
    store = RuntimeProviderConfigStore(tmp_path / "runtime-provider-config.json")
    command = _build_upsert_command()
    command.providers[0].timeout_sec = 30.0
    command.providers[0].request_total_timeout_sec = 45.0

    save_runtime_provider_command(store, command)
    loaded = store.load_saved_config()

    assert loaded is not None
    assert loaded.providers[0].timeout_sec == 45.0
    assert loaded.providers[0].request_total_timeout_sec == 45.0


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


def test_strict_provider_selection_requires_explicit_target_binding() -> None:
    config = _provider_config(include_ceo_binding=True, include_target_binding=False)

    selection = resolve_provider_selection(
        config,
        target_ref="role_profile:architect_primary",
        employee_provider_id="prov_employee",
        strict_explicit_binding=True,
    )

    assert selection is None


def test_strict_provider_selection_uses_explicit_target_binding() -> None:
    config = _provider_config(include_ceo_binding=True, include_target_binding=True)

    selection = resolve_provider_selection(
        config,
        target_ref="role_profile:architect_primary",
        employee_provider_id="prov_employee",
        strict_explicit_binding=True,
    )

    assert selection is not None
    assert selection.provider.provider_id == "prov_role"
    assert selection.selection_reason == "role_binding"


def test_non_strict_provider_selection_keeps_existing_fallback_order() -> None:
    config = _provider_config(include_ceo_binding=True, include_target_binding=False)

    selection = resolve_provider_selection(
        config,
        target_ref="role_profile:architect_primary",
        employee_provider_id="prov_employee",
    )

    assert selection is not None
    assert selection.provider.provider_id == "prov_default"
    assert selection.selection_reason == "ceo_binding_inheritance"


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
