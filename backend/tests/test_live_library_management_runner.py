from __future__ import annotations

from datetime import datetime
from pathlib import Path

from tests.live.architecture_governance_autopilot_live import SCENARIO as ARCHITECTURE_SCENARIO
from tests.live.architecture_governance_autopilot_smoke import (
    SCENARIO as ARCHITECTURE_SMOKE_SCENARIO,
    _assert_architecture_governance_smoke_checkpoint,
)
from tests.live._autopilot_live_harness import (
    _build_success_report,
    integration_test_provider_template_path,
    load_integration_test_provider_payload,
    write_audit_summary,
)
from tests.live.library_management_autopilot_live import (
    SCENARIO as LIBRARY_SCENARIO,
    _write_json,
    build_scenario_paths,
    reset_scenario_root,
)
from tests.live.requirement_elicitation_autopilot_live import SCENARIO as REQUIREMENT_SCENARIO


def test_reset_scenario_root_recreates_expected_layout(tmp_path: Path):
    paths = build_scenario_paths(tmp_path / "library_management_autopilot_live")
    paths.ticket_context_archive_root.mkdir(parents=True, exist_ok=True)
    stale_file = paths.ticket_context_archive_root / "stale.md"
    stale_file.write_text("stale", encoding="utf-8")

    reset_scenario_root(paths, clean=True)

    assert paths.root.exists()
    assert paths.artifact_store_root.exists()
    assert paths.artifact_upload_root.exists()
    assert paths.developer_inspector_root.exists()
    assert paths.ticket_context_archive_root.exists()
    assert not stale_file.exists()


def test_write_json_serializes_datetime_payloads(tmp_path: Path):
    target_path = tmp_path / "report.json"

    _write_json(
        target_path,
        {
            "generated_at": datetime.fromisoformat("2026-04-10T03:36:00+08:00"),
            "status": "FAILED",
        },
    )

    body = target_path.read_text(encoding="utf-8")
    assert '"generated_at": "2026-04-10 03:36:00+08:00"' in body
    assert '"status": "FAILED"' in body


def test_requirement_scenario_forces_requirement_elicitation() -> None:
    assert REQUIREMENT_SCENARIO.force_requirement_elicitation is True
    assert any("REQUIREMENT_ELICITATION" in item for item in REQUIREMENT_SCENARIO.constraints)


def test_architecture_scenario_keeps_architect_and_meeting_gate_constraints() -> None:
    assert ARCHITECTURE_SCENARIO.force_requirement_elicitation is False
    assert any("architect_primary" in item for item in ARCHITECTURE_SCENARIO.constraints)
    assert any("技术决策会议" in item or "meeting gate" in item for item in ARCHITECTURE_SCENARIO.constraints)
    assert LIBRARY_SCENARIO.slug == "library_management_autopilot_live"


def test_build_success_report_marks_checkpoint_mode() -> None:
    report = _build_success_report(
        workflow_id="wf_smoke_demo",
        scenario_root="D:/tmp/architecture_governance_autopilot_smoke",
        seed=17,
        ticks_used=9,
        elapsed_sec=12.5,
        base_report={"workflow_status": "EXECUTING", "workflow_stage": "plan"},
        assertions={"approved_architect_governance_ticket_ids": ["tkt_architect_001"]},
        completion_mode="checkpoint_smoke",
        checkpoint_label="architecture_governance_gate",
    )

    assert report["success"] is True
    assert report["completion_mode"] == "checkpoint_smoke"
    assert report["checkpoint_label"] == "architecture_governance_gate"
    assert report["assertions"]["workflow_status"] == "EXECUTING"
    assert report["assertions"]["approved_architect_governance_ticket_ids"] == ["tkt_architect_001"]


def test_write_audit_summary_renders_provider_attempts_and_terminal_failure(tmp_path: Path) -> None:
    paths = build_scenario_paths(tmp_path / "library_management_autopilot_live")
    reset_scenario_root(paths, clean=True)

    target_path = write_audit_summary(
        paths,
        report={
            "success": False,
            "workflow_id": "wf_library_live",
            "completion_mode": "full",
        },
        snapshot={
            "workflow": {
                "workflow_id": "wf_library_live",
                "status": "EXECUTING",
                "current_stage": "build",
            },
            "tickets": [
                {
                    "ticket_id": "tkt_build_001",
                    "status": "FAILED",
                    "node_id": "node_build_001",
                }
            ],
            "provider_candidate_chain": ["prov_primary", "prov_backup"],
            "provider_attempt_log": [
                {
                    "provider_id": "prov_primary",
                    "attempt_no": 1,
                    "failure_kind": "FIRST_TOKEN_TIMEOUT",
                    "status": "FAILED",
                },
                {
                    "provider_id": "prov_backup",
                    "attempt_no": 1,
                    "failure_kind": "PROVIDER_AUTH_FAILED",
                    "status": "FAILED",
                },
            ],
            "fallback_blocked": True,
            "final_failure_kind": "PROVIDER_REQUIRED_UNAVAILABLE",
        },
    )

    body = target_path.read_text(encoding="utf-8")
    assert target_path.name == "audit-summary.md"
    assert "wf_library_live" in body
    assert "prov_primary -> prov_backup" in body
    assert "FIRST_TOKEN_TIMEOUT" in body
    assert "PROVIDER_REQUIRED_UNAVAILABLE" in body
    assert "fallback blocked" in body.lower()


def test_architecture_smoke_scenario_stops_before_source_code_fanout() -> None:
    assertions = _assert_architecture_governance_smoke_checkpoint(
        None,
        None,
        "wf_architecture_smoke",
        {
            "architect_ticket_ids": ["tkt_architect_approved_001"],
            "approvals": [
                {"approval_type": "MEETING_ESCALATION", "status": "APPROVED"},
            ],
            "employees": [
                {"employee_id": "emp_architect_1", "role_type": "governance_architect"},
            ],
            "tickets": [
                {"ticket_id": "tkt_architect_approved_001"},
            ],
            "created_specs": {
                "tkt_architect_approved_001": {"output_schema_ref": "architecture_brief"},
            },
        },
    )

    assert ARCHITECTURE_SMOKE_SCENARIO.checkpoint_label == "architecture_governance_gate"
    assert assertions is not None
    assert assertions["approved_architect_governance_ticket_ids"] == ["tkt_architect_approved_001"]
    assert assertions["approved_meeting_escalation_count"] == 1
    assert assertions["governance_architect_employee_ids"] == ["emp_architect_1"]


def test_integration_test_provider_template_path_uses_backend_data() -> None:
    path = integration_test_provider_template_path()
    assert path.name == "integration-test-provider-config.json"
    assert path.parent.name == "data"


def test_load_integration_test_provider_payload_reads_template_and_sets_idempotency_key(tmp_path: Path) -> None:
    config_path = tmp_path / "integration-test-provider-config.json"
    config_path.write_text(
        (
            '{'
            '"providers":[{"provider_id":"prov_openai_compat","type":"openai_responses_stream","enabled":true,'
            '"base_url":"https://api.example.test/v1","api_key":"sk-test","alias":"integration-live",'
            '"preferred_model":"gpt-5.4","max_context_window":null,"reasoning_effort":"high"}],'
            '"provider_model_entries":[{"provider_id":"prov_openai_compat","model_name":"gpt-5.4"}],'
            '"role_bindings":[{"target_ref":"ceo_shadow","provider_model_entry_refs":["prov_openai_compat::gpt-5.4"],'
            '"max_context_window_override":null,"reasoning_effort_override":"high"}]'
            '}'
        ),
        encoding="utf-8",
    )

    payload = load_integration_test_provider_payload(
        scenario_slug="library_management_autopilot_live",
        config_path=config_path,
    )

    assert payload["providers"][0]["base_url"] == "https://api.example.test/v1"
    assert payload["provider_model_entries"][0]["model_name"] == "gpt-5.4"
    assert payload["role_bindings"][0]["target_ref"] == "ceo_shadow"
    assert payload["idempotency_key"] == "runtime-provider-upsert:library_management_autopilot_live"


def test_load_integration_test_provider_payload_prefers_env_override(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config_path = tmp_path / "integration-test-provider-config.json"
    config_path.write_text(
        (
            '{'
            '"providers":[{"provider_id":"prov_openai_compat","type":"openai_responses_stream","enabled":true,'
            '"base_url":"https://api.override.test/v1","api_key":"sk-override","alias":"integration-live",'
            '"preferred_model":"gpt-5.4","max_context_window":null,"reasoning_effort":"high"}],'
            '"provider_model_entries":[{"provider_id":"prov_openai_compat","model_name":"gpt-5.4"}],'
            '"role_bindings":[{"target_ref":"ceo_shadow","provider_model_entry_refs":["prov_openai_compat::gpt-5.4"],'
            '"max_context_window_override":null,"reasoning_effort_override":"high"}]'
            '}'
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("BOARDROOM_OS_INTEGRATION_TEST_PROVIDER_CONFIG_PATH", str(config_path))

    payload = load_integration_test_provider_payload(scenario_slug="architecture_governance_autopilot_smoke")

    assert payload["providers"][0]["base_url"] == "https://api.override.test/v1"
    assert payload["providers"][0]["api_key"] == "sk-override"
    assert payload["idempotency_key"] == "runtime-provider-upsert:architecture_governance_autopilot_smoke"
