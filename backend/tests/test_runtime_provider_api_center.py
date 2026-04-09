from __future__ import annotations

from fastapi.testclient import TestClient


def _upsert_payload() -> dict:
    return {
        "providers": [
            {
                "provider_id": "prov_primary",
                "type": "openai_responses_stream",
                "base_url": "https://api.example.test/v1",
                "api_key": "sk-test-secret",
                "alias": "",
                "preferred_model": "gpt-5.3-codex",
                "max_context_window": None,
                "reasoning_effort": "high",
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
                "provider_model_entry_refs": ["prov_primary::gpt-5.3-codex"],
                "max_context_window_override": None,
                "reasoning_effort_override": None,
            },
            {
                "target_ref": "role_profile:frontend_engineer_primary",
                "provider_model_entry_refs": [],
                "max_context_window_override": 180000,
                "reasoning_effort_override": "medium",
            },
        ],
        "idempotency_key": "runtime-provider-upsert:api-center",
    }


def test_runtime_provider_projection_returns_provider_model_entries_and_role_binding_windows(
    db_path,
    monkeypatch,
) -> None:
    config_path = db_path.parent / "runtime-provider-config-center.json"
    monkeypatch.setenv("BOARDROOM_OS_RUNTIME_PROVIDER_CONFIG_PATH", str(config_path))

    from app.main import create_app

    with TestClient(create_app()) as client:
        save_response = client.post("/api/v1/commands/runtime-provider-upsert", json=_upsert_payload())
        projection_response = client.get("/api/v1/projections/runtime-provider")

        assert save_response.status_code == 200
        assert projection_response.status_code == 200

        data = projection_response.json()["data"]
        assert data["providers"][0]["provider_id"] == "prov_primary"
        assert data["providers"][0]["alias"] == "example"
        assert data["providers"][0]["max_context_window"] == 1000000
        assert data["providers"][0]["reasoning_effort"] == "high"
        assert data["provider_model_entries"] == [
            {
                "entry_ref": "prov_primary::gpt-5.3-codex",
                "provider_id": "prov_primary",
                "provider_label": "example",
                "model_name": "gpt-5.3-codex",
                "max_context_window": 1000000,
            }
        ]
        assert data["role_bindings"][0]["target_ref"] == "ceo_shadow"
        assert data["role_bindings"][0]["provider_model_entry_refs"] == ["prov_primary::gpt-5.3-codex"]
        assert data["role_bindings"][0]["reasoning_effort_override"] is None
        assert data["role_bindings"][1]["target_ref"] == "role_profile:frontend_engineer_primary"
        assert data["role_bindings"][1]["max_context_window_override"] == 180000
        assert data["role_bindings"][1]["reasoning_effort_override"] == "medium"


def test_runtime_provider_connectivity_test_returns_resolved_provider_shape(
    db_path,
    monkeypatch,
) -> None:
    config_path = db_path.parent / "runtime-provider-config-connectivity.json"
    monkeypatch.setenv("BOARDROOM_OS_RUNTIME_PROVIDER_CONFIG_PATH", str(config_path))

    from app.main import create_app
    from app.core.provider_openai_compat import OpenAICompatConnectivityResult, OpenAICompatProviderType
    import app.api.commands as command_routes

    def _probe(config, transport=None):
        assert config.reasoning_effort == "high"
        return OpenAICompatConnectivityResult(
            ok=True,
            provider_type=OpenAICompatProviderType.RESPONSES_NON_STREAM,
            response_id="resp_connectivity_test",
        )

    monkeypatch.setattr(command_routes, "probe_openai_compat_connectivity", _probe)

    with TestClient(create_app()) as client:
        response = client.post(
            "/api/v1/commands/runtime-provider-connectivity-test",
            json={
                "provider_id": "prov_probe",
                "type": "openai_responses_stream",
                "base_url": "https://api.example.test/v1",
                "api_key": "sk-test-secret",
                "alias": "",
                "preferred_model": "gpt-5.3-codex",
                "max_context_window": None,
                "reasoning_effort": "high",
                "enabled": True,
            },
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["ok"] is True
        assert payload["resolved_provider"]["type"] == "openai_responses_non_stream"
        assert payload["resolved_provider"]["alias"] == "example"
        assert payload["resolved_provider"]["max_context_window"] == 1000000
        assert payload["resolved_provider"]["reasoning_effort"] == "high"


def test_runtime_provider_models_refresh_returns_latest_models_for_saved_provider(
    db_path,
    monkeypatch,
) -> None:
    config_path = db_path.parent / "runtime-provider-config-models.json"
    monkeypatch.setenv("BOARDROOM_OS_RUNTIME_PROVIDER_CONFIG_PATH", str(config_path))

    from app.main import create_app
    import app.api.commands as command_routes

    monkeypatch.setattr(
        command_routes,
        "list_openai_compat_models",
        lambda config, transport=None: ["gpt-4.1", "gpt-5.3-codex"],
    )

    with TestClient(create_app()) as client:
        client.post("/api/v1/commands/runtime-provider-upsert", json=_upsert_payload())
        response = client.post(
            "/api/v1/commands/runtime-provider-models-refresh",
            json={"provider_id": "prov_primary"},
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["provider_id"] == "prov_primary"
        assert payload["models"] == ["gpt-4.1", "gpt-5.3-codex"]
