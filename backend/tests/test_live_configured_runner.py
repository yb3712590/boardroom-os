from __future__ import annotations

from pathlib import Path

import pytest


def _write_live_config(tmp_path: Path, *, extra_body: str = "") -> Path:
    config_path = tmp_path / "library_management_autopilot_live.toml"
    config_path.write_text(
        f"""
[scenario]
slug = "library_management_autopilot_live"
description = "Run the library management autopilot live scenario."
goal = "实现一个完全匿名的、纯粹用于记录实体书本当前是否在馆的单机版终端系统。"
workflow_profile = "CEO_AUTOPILOT_FINE_GRAINED"
force_requirement_elicitation = false
budget_cap = 1500000
constraints = [
  "绝对禁止权限系统。",
  "绝对禁止时间轴计算。",
  "绝对禁止复杂分类。",
  "绝对禁止用户借阅历史。",
  "唯一数据模型只允许 books 一张表。",
  "前端 UI 必须采用终端风格。"
]

[runtime]
seed = 17
max_ticks = 180
timeout_sec = 7200

[provider]
provider_id = "prov_openai_compat_truerealbill"
base_url = "http://codex.truerealbill.com:11234/v1"
api_key = "sk-test"
preferred_model = "gpt-5.4"
max_context_window = 270000
reasoning_effort = "high"
connect_timeout_sec = 10
write_timeout_sec = 20
first_token_timeout_sec = 300
stream_idle_timeout_sec = 300
fallback_provider_ids = []

[assertions]
profile = "minimalist_book_tracker"

{extra_body}
""".strip()
        + "\n",
        encoding="utf-8",
    )
    return config_path


def test_load_live_scenario_config_builds_single_provider_payload_and_derives_compat_timeouts(
    tmp_path: Path,
) -> None:
    from tests.live._config import load_live_scenario_config

    config = load_live_scenario_config(_write_live_config(tmp_path))
    payload = config.build_runtime_provider_payload()

    provider = payload["providers"][0]
    assert config.scenario.slug == "library_management_autopilot_live"
    assert provider["provider_id"] == "prov_openai_compat_truerealbill"
    assert provider["base_url"] == "http://codex.truerealbill.com:11234/v1"
    assert provider["api_key"] == "sk-test"
    assert provider["preferred_model"] == "gpt-5.4"
    assert provider["timeout_sec"] == 300
    assert "request_total_timeout_sec" not in provider
    assert provider["connect_timeout_sec"] == 10
    assert provider["write_timeout_sec"] == 20
    assert provider["first_token_timeout_sec"] == 300
    assert provider["stream_idle_timeout_sec"] == 300
    assert provider["fallback_provider_ids"] == []
    assert payload["provider_model_entries"] == [
        {
            "provider_id": "prov_openai_compat_truerealbill",
            "model_name": "gpt-5.4",
        }
    ]
    assert {
        tuple(binding["provider_model_entry_refs"])
        for binding in payload["role_bindings"]
    } == {
        ("prov_openai_compat_truerealbill::gpt-5.4",)
    }
    assert {
        "ceo_shadow",
        "role_profile:architect_primary",
        "role_profile:frontend_engineer_primary",
        "role_profile:checker_primary",
        "role_profile:backend_engineer_primary",
        "role_profile:database_engineer_primary",
        "role_profile:platform_sre_primary",
        "role_profile:cto_primary",
    }.issubset({binding["target_ref"] for binding in payload["role_bindings"]})


def test_load_live_scenario_config_rejects_stage_fields(tmp_path: Path) -> None:
    from tests.live._config import load_live_scenario_config

    config_path = _write_live_config(
        tmp_path,
        extra_body="""
[[stages]]
stage_id = "legacy_stage"

[seeds.stage_01]
path = "legacy"
""",
    )

    with pytest.raises(ValueError, match="seeds|stages"):
        load_live_scenario_config(config_path)


def test_load_live_scenario_config_rejects_workflow_id_fields(tmp_path: Path) -> None:
    from tests.live._config import load_live_scenario_config

    config_path = _write_live_config(
        tmp_path,
        extra_body="""
[legacy]
workflow_id = "wf_legacy"
""",
    )

    with pytest.raises(ValueError, match="workflow_id"):
        load_live_scenario_config(config_path)


def test_minimalist_book_tracker_profile_rejects_missing_scope_capabilities() -> None:
    from tests.live._config import LiveAssertionConfig
    from tests.live._scenario_profiles import build_assert_outcome

    assert_outcome = build_assert_outcome(
        LiveAssertionConfig(
            profile="minimalist_book_tracker",
            expected_provider_id="prov_openai_compat_truerealbill",
        )
    )

    common = {
        "employees": [{"role_type": "governance_architect"}],
        "audits": [
            {
                "ticket_id": "tkt_arch",
                "role_profile_ref": "architect_primary",
                "assumptions": {
                    "actual_provider_id": "prov_openai_compat_truerealbill",
                    "actual_model": "gpt-5.4",
                    "effective_reasoning_effort": "xhigh",
                },
            },
            {
                "ticket_id": "tkt_impl",
                "role_profile_ref": "frontend_engineer_primary",
                "assumptions": {
                    "actual_provider_id": "prov_openai_compat_truerealbill",
                    "actual_model": "gpt-5.4",
                    "effective_reasoning_effort": "high",
                },
            },
        ],
        "architect_ticket_ids": ["tkt_arch"],
        "created_specs": {
            "tkt_arch": {
                "output_schema_ref": "architecture_brief",
                "summary": "books title author IN_LIBRARY terminal",
            },
            "tkt_impl": {
                "output_schema_ref": "source_code_delivery",
                "summary": "books title author IN_LIBRARY terminal",
            },
        },
        "terminals": {
            "tkt_impl": {
                "payload": {
                    "summary": "books title author IN_LIBRARY terminal",
                    "source_files": [
                        {
                            "path": "src/library.tsx",
                            "content": "books title author IN_LIBRARY terminal",
                        }
                    ],
                }
            }
        },
        "source_delivery_ticket_ids": ["tkt_impl"],
    }

    with pytest.raises(AssertionError, match="CHECKED_OUT|remove|check out"):
        assert_outcome(None, object(), "wf_library", common)


def test_run_configured_live_scenario_loads_toml_and_passes_payload_to_harness(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tests.live import _configured_runner as configured_runner
    from tests.live._autopilot_live_harness import LiveScenarioDefinition

    config_path = _write_live_config(tmp_path)
    captured: dict[str, object] = {}

    def _fake_run_live_scenario_with_provider_payload(
        scenario: LiveScenarioDefinition,
        provider_payload: dict[str, object],
        *,
        clean: bool,
        max_ticks: int,
        timeout_sec: int,
        seed: int,
        scenario_root: Path | None,
    ) -> dict[str, object]:
        captured["scenario"] = scenario
        captured["provider_payload"] = provider_payload
        captured["clean"] = clean
        captured["max_ticks"] = max_ticks
        captured["timeout_sec"] = timeout_sec
        captured["seed"] = seed
        captured["scenario_root"] = scenario_root
        return {"success": True, "scenario_slug": scenario.slug}

    monkeypatch.setattr(
        configured_runner,
        "run_live_scenario_with_provider_payload",
        _fake_run_live_scenario_with_provider_payload,
    )

    report = configured_runner.run_configured_live_scenario(
        config_path,
        clean=False,
        max_ticks=9,
        timeout_sec=34,
        seed=23,
        scenario_root=tmp_path / "scenario-root",
    )

    assert report == {"success": True, "scenario_slug": "library_management_autopilot_live"}
    scenario = captured["scenario"]
    assert isinstance(scenario, LiveScenarioDefinition)
    assert scenario.slug == "library_management_autopilot_live"
    assert captured["clean"] is False
    assert captured["max_ticks"] == 9
    assert captured["timeout_sec"] == 34
    assert captured["seed"] == 23
    assert captured["scenario_root"] == tmp_path / "scenario-root"
    provider_payload = captured["provider_payload"]
    assert provider_payload["providers"][0]["provider_id"] == "prov_openai_compat_truerealbill"
    assert provider_payload["providers"][0]["api_key"] == "sk-test"
