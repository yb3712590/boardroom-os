from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest
import tests.live._autopilot_live_harness as live_harness

from tests.live.architecture_governance_autopilot_live import SCENARIO as ARCHITECTURE_SCENARIO
from tests.live.architecture_governance_autopilot_smoke import (
    SCENARIO as ARCHITECTURE_SMOKE_SCENARIO,
    _assert_architecture_governance_smoke_checkpoint,
)
from tests.live._autopilot_live_harness import (
    _assert_source_delivery_payload_quality,
    _assert_unique_source_delivery_evidence_paths,
    _build_success_report,
    _should_count_stall,
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


def test_build_scenario_paths_exposes_integration_monitor_report_path(tmp_path: Path) -> None:
    paths = build_scenario_paths(tmp_path / "library_management_autopilot_live")

    assert getattr(paths, "integration_monitor_report_path", None) == (
        paths.root / "integration-monitor-report.md"
    )


def test_write_audit_summary_renders_formal_sections(tmp_path: Path) -> None:
    paths = build_scenario_paths(tmp_path / "library_management_autopilot_live")
    reset_scenario_root(paths, clean=True)

    target_path = write_audit_summary(
        paths,
        report={
            "success": False,
            "scenario_slug": "library_management_autopilot_live",
            "workflow_id": "wf_library_live",
            "completion_mode": "timeout",
            "elapsed_sec": 4260.0,
            "started_at": "2026-04-13T01:37:37+08:00",
            "finished_at": "2026-04-13T02:48:37+08:00",
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
                    "status": "IN_PROGRESS",
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
                }
            ],
            "fallback_blocked": True,
            "final_failure_kind": "PROVIDER_REQUIRED_UNAVAILABLE",
            "provider_summary": {
                "actual_provider_id": "prov_primary",
                "actual_model": "gpt-5.4",
                "provider_base_url": "https://api.example.test/v1",
            },
            "timeline": [
                {
                    "entered_at": "2026-04-13T01:37:37+08:00",
                    "stage": "project_init",
                    "workflow_status": "EXECUTING",
                },
                {
                    "entered_at": "2026-04-13T01:41:37+08:00",
                    "stage": "plan",
                    "workflow_status": "EXECUTING",
                },
                {
                    "entered_at": "2026-04-13T02:00:37+08:00",
                    "stage": "build",
                    "workflow_status": "EXECUTING",
                },
            ],
            "ticket_summary": {
                "total": 7,
                "completed": 4,
                "failed": 1,
                "pending": 2,
                "active_ticket_ids": ["tkt_build_001"],
            },
            "governance_documents": [
                {
                    "ticket_id": "tkt_gov_001",
                    "document_kind_ref": "architecture_brief",
                    "status": "COMPLETED",
                    "summary": "MVP scope is locked to library management.",
                }
            ],
            "artifact_summary": {
                "has_project_code": True,
                "has_test_evidence": True,
                "has_git_evidence": True,
            },
            "approval_summary": {
                "open_count": 1,
                "resolved_count": 2,
            },
            "incident_summary": {
                "open_count": 0,
                "resolved_count": 1,
            },
            "longest_silence": {
                "start_at": "2026-04-13T02:10:00+08:00",
                "end_at": "2026-04-13T02:23:00+08:00",
                "duration_sec": 780,
            },
        },
    )

    body = target_path.read_text(encoding="utf-8")
    assert "library_management_autopilot_live" in body
    assert "## Workflow Progress" in body
    assert "## Governance Output Chain" in body
    assert "## Code And Evidence" in body
    assert "## Incidents And Approvals" in body
    assert "## Longest Silence" in body
    assert "https://api.example.test/v1" in body
    assert "MVP scope is locked to library management." in body


def test_latest_provider_runtime_snapshot_uses_in_progress_provider_audit_events(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        live_harness,
        "workflow_terminal_events",
        lambda _repository, _workflow_id: {},
    )
    monkeypatch.setattr(
        live_harness,
        "workflow_ticket_rows",
        lambda _repository, _workflow_id: [
            {
                "ticket_id": "tkt_build_001",
                "status": "EXECUTING",
            }
        ],
    )
    monkeypatch.setattr(
        live_harness,
        "workflow_provider_audit_events",
        lambda _repository, _workflow_id: {
            "tkt_build_001": [
                {
                    "event_type": "PROVIDER_ATTEMPT_STARTED",
                    "payload": {
                        "provider_id": "prov_primary",
                        "actual_model": "gpt-5.4",
                        "attempt_no": 3,
                        "retry_backoff_schedule_sec": [1, 2, 4],
                    },
                },
                {
                    "event_type": "PROVIDER_FIRST_TOKEN_RECEIVED",
                    "payload": {
                        "provider_id": "prov_primary",
                        "actual_model": "gpt-5.4",
                        "attempt_no": 3,
                        "elapsed_sec": 91.5,
                        "retry_backoff_schedule_sec": [1, 2, 4],
                    },
                },
            ]
        },
    )

    snapshot = live_harness._latest_provider_runtime_snapshot(object(), "wf_live")

    assert snapshot["actual_provider_id"] == "prov_primary"
    assert snapshot["actual_model"] == "gpt-5.4"
    assert snapshot["provider_attempt_count"] == 3
    assert snapshot["current_attempt_no"] == 3
    assert snapshot["current_phase"] == "streaming"
    assert snapshot["elapsed_sec"] == 91.5
    assert snapshot["retry_backoff_schedule_sec"] == [1, 2, 4]
    assert snapshot["provider_attempt_log"] == [
        {
            "provider_id": "prov_primary",
            "attempt_no": 3,
            "status": "IN_PROGRESS",
            "failure_kind": None,
        }
    ]


def test_write_audit_summary_renders_in_progress_provider_status(tmp_path: Path) -> None:
    paths = build_scenario_paths(tmp_path / "library_management_autopilot_live")
    reset_scenario_root(paths, clean=True)

    target_path = write_audit_summary(
        paths,
        report={
            "success": False,
            "scenario_slug": "library_management_autopilot_live",
            "workflow_id": "wf_library_live",
            "completion_mode": "stall",
            "elapsed_sec": 901.0,
            "started_at": "2026-04-18T13:54:10+08:00",
            "finished_at": "2026-04-18T14:09:11+08:00",
        },
        snapshot={
            "workflow": {
                "workflow_id": "wf_library_live",
                "status": "EXECUTING",
                "current_stage": "plan",
            },
            "tickets": [
                {
                    "ticket_id": "tkt_build_001",
                    "status": "EXECUTING",
                    "node_id": "node_build_001",
                }
            ],
            "provider_summary": {
                "actual_provider_id": "prov_primary",
                "actual_model": "gpt-5.4",
                "provider_base_url": "https://api.example.test/v1",
            },
            "provider_attempt_count": 3,
            "current_attempt_no": 3,
            "current_phase": "streaming",
            "elapsed_sec": 91.5,
            "provider_attempt_log": [
                {
                    "provider_id": "prov_primary",
                    "attempt_no": 3,
                    "status": "IN_PROGRESS",
                    "failure_kind": None,
                }
            ],
        },
    )

    body = target_path.read_text(encoding="utf-8")
    assert "Current attempt" in body
    assert "Current phase" in body
    assert "streaming" in body
    assert "91.5" in body


def test_write_integration_monitor_report_only_keeps_changes(tmp_path: Path) -> None:
    paths = build_scenario_paths(tmp_path / "library_management_autopilot_live")
    reset_scenario_root(paths, clean=True)

    writer = getattr(live_harness, "write_integration_monitor_report", None)
    assert callable(writer)

    target_path = writer(
        paths,
        entries=[
            {
                "recorded_at": "2026-04-13T01:38:41+08:00",
                "workflow_status": "EXECUTING",
                "stage": "project_init",
                "ticket_count": 0,
                "event_count": 5,
                "active_ticket_ids": [],
                "approval_count": 0,
                "incident_count": 0,
                "change_type": "state_change",
                "summary": "workflow 启动",
            },
            {
                "recorded_at": "2026-04-13T01:39:41+08:00",
                "workflow_status": "EXECUTING",
                "stage": "plan",
                "ticket_count": 1,
                "event_count": 8,
                "active_ticket_ids": ["tkt_plan_001"],
                "approval_count": 0,
                "incident_count": 0,
                "change_type": "state_change",
                "summary": "进入 plan 阶段",
            },
            {
                "recorded_at": "2026-04-13T01:54:41+08:00",
                "workflow_status": "EXECUTING",
                "stage": "plan",
                "ticket_count": 1,
                "event_count": 8,
                "active_ticket_ids": ["tkt_plan_001"],
                "approval_count": 0,
                "incident_count": 0,
                "change_type": "silence_recovered",
                "summary": "静默 14 分钟后恢复",
                "silent_for_sec": 840,
            },
        ],
    )

    body = target_path.read_text(encoding="utf-8")
    assert target_path.name == "integration-monitor-report.md"
    assert body.count("### ") == 3
    assert "静默 14 分钟后恢复" in body
    assert "tkt_plan_001" in body


def test_write_integration_monitor_report_renders_provider_status_when_present(tmp_path: Path) -> None:
    paths = build_scenario_paths(tmp_path / "library_management_autopilot_live")
    reset_scenario_root(paths, clean=True)

    target_path = live_harness.write_integration_monitor_report(
        paths,
        entries=[
            {
                "recorded_at": "2026-04-18T13:59:41+08:00",
                "workflow_status": "EXECUTING",
                "stage": "plan",
                "ticket_count": 1,
                "event_count": 8,
                "active_ticket_ids": ["tkt_build_001"],
                "approval_count": 0,
                "incident_count": 0,
                "change_type": "state_change",
                "summary": "provider 进入流式输出",
                "provider_id": "prov_primary",
                "current_attempt_no": 3,
                "current_phase": "streaming",
                "elapsed_sec": 91.5,
            }
        ],
    )

    body = target_path.read_text(encoding="utf-8")
    assert "prov_primary" in body
    assert "attempt `3`" in body
    assert "streaming" in body


def test_write_integration_monitor_report_renders_runtime_execution_summary(tmp_path: Path) -> None:
    paths = build_scenario_paths(tmp_path / "library_management_autopilot_live")
    reset_scenario_root(paths, clean=True)

    target_path = live_harness.write_integration_monitor_report(
        paths,
        entries=[
            {
                "recorded_at": "2026-04-18T13:59:41+08:00",
                "workflow_status": "EXECUTING",
                "stage": "plan",
                "ticket_count": 1,
                "event_count": 8,
                "active_ticket_ids": ["tkt_build_001"],
                "approval_count": 0,
                "incident_count": 0,
                "change_type": "state_change",
                "summary": "活跃 ticket 变化",
            }
        ],
        runtime_execution_summary={
            "outcomes": [],
            "skipped": [
                {
                    "workflow_id": "wf_library_live",
                    "ticket_id": "tkt_build_001",
                    "node_id": "node_build_001",
                    "graph_node_id": "node_build_001",
                    "ticket_status": "LEASED",
                    "runtime_node_status": None,
                    "reason_code": "GRAPH_CONTRACT_MISSING",
                    "reason": "Ticket tkt_build_001 is missing graph_contract.lane_kind.",
                }
            ],
        },
    )

    body = target_path.read_text(encoding="utf-8")
    assert "Runtime Execution" in body
    assert "GRAPH_CONTRACT_MISSING" in body
    assert "tkt_build_001" in body


def test_write_failure_report_persists_run_report_for_failed_snapshot(tmp_path: Path) -> None:
    paths = build_scenario_paths(tmp_path / "library_management_autopilot_live")
    reset_scenario_root(paths, clean=True)

    writer = getattr(live_harness, "_write_failure_report", None)
    assert callable(writer)

    report = writer(
        paths,
        scenario_slug="library_management_autopilot_live",
        workflow_id="wf_library_live",
        failure_mode="stall",
        completion_mode="stall",
        elapsed_sec=901.0,
        started_at="2026-04-18T13:54:10+08:00",
        finished_at="2026-04-18T14:09:11+08:00",
        snapshot_path=paths.failure_snapshot_root / "stall.json",
        provider_snapshot={
            "provider_attempt_count": 3,
            "current_attempt_no": 3,
            "current_phase": "streaming",
            "elapsed_sec": 91.5,
            "provider_attempt_log": [],
            "runtime_execution_summary": {
                "outcomes": [],
                "skipped": [
                    {
                        "workflow_id": "wf_library_live",
                        "ticket_id": "tkt_build_001",
                        "node_id": "node_build_001",
                        "graph_node_id": "node_build_001",
                        "ticket_status": "LEASED",
                        "runtime_node_status": None,
                        "reason_code": "GRAPH_CONTRACT_MISSING",
                        "reason": "Ticket tkt_build_001 is missing graph_contract.lane_kind.",
                    }
                ],
            },
        },
    )

    persisted = json.loads(paths.run_report_path.read_text(encoding="utf-8"))
    assert report["success"] is False
    assert persisted["failure_mode"] == "stall"
    assert persisted["snapshot_path"].endswith("stall.json")
    assert persisted["current_phase"] == "streaming"
    assert persisted["runtime_execution_summary"] == {
        "outcomes": [],
        "skipped": [
            {
                "workflow_id": "wf_library_live",
                "ticket_id": "tkt_build_001",
                "node_id": "node_build_001",
                "graph_node_id": "node_build_001",
                "ticket_status": "LEASED",
                "runtime_node_status": None,
                "reason_code": "GRAPH_CONTRACT_MISSING",
                "reason": "Ticket tkt_build_001 is missing graph_contract.lane_kind.",
            }
        ],
    }



def test_build_audit_snapshot_uses_current_workflow_runtime_execution_summary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        live_harness,
        "workflow_ticket_rows",
        lambda _repository, _workflow_id: [
            {
                "ticket_id": "tkt_build_001",
                "status": "LEASED",
                "node_id": "node_build_001",
            }
        ],
    )
    monkeypatch.setattr(
        live_harness,
        "workflow_approvals",
        lambda _repository, _workflow_id: [],
    )
    monkeypatch.setattr(
        live_harness,
        "_workflow_incidents",
        lambda _repository, _workflow_id: [],
    )
    monkeypatch.setattr(
        live_harness,
        "_latest_provider_runtime_snapshot",
        lambda _repository, _workflow_id: live_harness._empty_provider_runtime_snapshot(),
    )
    monkeypatch.setattr(
        live_harness,
        "_governance_documents",
        lambda _repository, _workflow_id: [],
    )
    monkeypatch.setattr(
        live_harness,
        "_artifact_summary",
        lambda _repository, _workflow_id: {
            "has_project_code": False,
            "has_test_evidence": False,
            "has_git_evidence": False,
        },
    )
    monkeypatch.setattr(
        live_harness,
        "recent_orchestration_trace",
        lambda _repository, limit=5: [
            {
                "runtime_execution": {
                    "outcomes": [],
                    "skipped": [
                        {
                            "workflow_id": "wf_other",
                            "ticket_id": "tkt_other",
                            "node_id": "node_other",
                            "graph_node_id": "node_other",
                            "ticket_status": "LEASED",
                            "runtime_node_status": None,
                            "reason_code": "GRAPH_CONTRACT_MISSING",
                            "reason": "Should not leak from a different workflow.",
                        }
                    ],
                }
            },
            {
                "runtime_execution": {
                    "outcomes": [],
                    "skipped": [
                        {
                            "workflow_id": "wf_target",
                            "ticket_id": "tkt_build_001",
                            "node_id": "node_build_001",
                            "graph_node_id": "node_build_001",
                            "ticket_status": "LEASED",
                            "runtime_node_status": None,
                            "reason_code": "GRAPH_CONTRACT_MISSING",
                            "reason": "Ticket tkt_build_001 is missing graph_contract.lane_kind.",
                        }
                    ],
                }
            },
        ],
    )

    class _Repository:
        def get_workflow_projection(self, workflow_id: str) -> dict:
            return {
                "workflow_id": workflow_id,
                "status": "EXECUTING",
                "current_stage": "plan",
            }

    snapshot = live_harness._build_audit_snapshot(
        _Repository(),
        "wf_target",
        monitor_state={"entries": []},
        provider_id=None,
        model_name=None,
        provider_base_url=None,
    )

    assert snapshot["runtime_execution_summary"] == {
        "outcomes": [],
        "skipped": [
            {
                "workflow_id": "wf_target",
                "ticket_id": "tkt_build_001",
                "node_id": "node_build_001",
                "graph_node_id": "node_build_001",
                "ticket_status": "LEASED",
                "runtime_node_status": None,
                "reason_code": "GRAPH_CONTRACT_MISSING",
                "reason": "Ticket tkt_build_001 is missing graph_contract.lane_kind.",
            }
        ],
    }


def test_write_audit_summary_renders_runtime_execution_summary(tmp_path: Path) -> None:
    paths = build_scenario_paths(tmp_path / "library_management_autopilot_live")
    reset_scenario_root(paths, clean=True)

    target_path = write_audit_summary(
        paths,
        report={
            "success": False,
            "scenario_slug": "library_management_autopilot_live",
            "workflow_id": "wf_library_live",
            "completion_mode": "stall",
            "elapsed_sec": 901.0,
            "started_at": "2026-04-18T13:54:10+08:00",
            "finished_at": "2026-04-18T14:09:11+08:00",
        },
        snapshot={
            "workflow": {
                "workflow_id": "wf_library_live",
                "status": "EXECUTING",
                "current_stage": "plan",
            },
            "tickets": [
                {
                    "ticket_id": "tkt_build_001",
                    "status": "LEASED",
                    "node_id": "node_build_001",
                }
            ],
            "runtime_execution_summary": {
                "outcomes": [],
                "skipped": [
                    {
                        "workflow_id": "wf_library_live",
                        "ticket_id": "tkt_build_001",
                        "node_id": "node_build_001",
                        "graph_node_id": "node_build_001",
                        "ticket_status": "LEASED",
                        "runtime_node_status": None,
                        "reason_code": "GRAPH_CONTRACT_MISSING",
                        "reason": "Ticket tkt_build_001 is missing graph_contract.lane_kind.",
                    }
                ],
            },
        },
    )

    body = target_path.read_text(encoding="utf-8")
    assert "Runtime Execution" in body
    assert "GRAPH_CONTRACT_MISSING" in body
    assert "tkt_build_001" in body


def test_assert_source_delivery_payload_quality_requires_raw_verification_output() -> None:
    created_specs = {
        "tkt_build_001": {
            "output_schema_ref": "source_code_delivery",
        }
    }
    terminals = {
        "tkt_build_001": {
            "payload": {
                "summary": "Source code delivery prepared for ticket tkt_build_001.",
                "source_file_refs": ["art://workspace/tkt_build_001/source.ts"],
                "source_files": [
                    {
                        "artifact_ref": "art://workspace/tkt_build_001/source.ts",
                        "path": "10-project/src/tkt_build_001.ts",
                        "content": "export const buildReady = true;\n",
                    }
                ],
                "verification_evidence_refs": ["art://workspace/tkt_build_001/test-report.json"],
                "verification_runs": [
                    {
                        "artifact_ref": "art://workspace/tkt_build_001/test-report.json",
                        "path": "20-evidence/tests/tkt_build_001/attempt-1/test-report.json",
                        "runner": "pytest",
                        "command": "pytest -q",
                        "status": "passed",
                        "exit_code": 0,
                        "duration_sec": 0.2,
                        "stdout": "",
                        "stderr": "",
                        "discovered_count": 0,
                        "passed_count": 0,
                        "failed_count": 0,
                        "skipped_count": 0,
                        "failures": [],
                    }
                ],
            }
        }
    }

    with pytest.raises(AssertionError, match="raw verification stdout"):
        _assert_source_delivery_payload_quality(created_specs, terminals)


def test_assert_unique_source_delivery_evidence_paths_rejects_duplicate_paths() -> None:
    with pytest.raises(AssertionError, match="duplicate source delivery evidence paths"):
        _assert_unique_source_delivery_evidence_paths(
            [
                {
                    "ticket_id": "tkt_build_001",
                    "logical_path": "20-evidence/tests/tkt_build_001/attempt-1/test-report.json",
                },
                {
                    "ticket_id": "tkt_build_002",
                    "logical_path": "20-evidence/tests/tkt_build_001/attempt-1/test-report.json",
                },
            ]
        )


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


def test_load_integration_test_provider_payload_preserves_long_test_timeout_and_retry_defaults(tmp_path: Path) -> None:
    config_path = tmp_path / "integration-test-provider-config.json"
    config_path.write_text(
        (
            '{'
            '"providers":[{"provider_id":"prov_openai_compat","type":"openai_responses_stream","enabled":true,'
            '"base_url":"https://api.example.test/v1","api_key":"sk-test","alias":"integration-live",'
            '"preferred_model":"gpt-5.4","max_context_window":null,"timeout_sec":300,'
            '"connect_timeout_sec":10,"write_timeout_sec":20,"first_token_timeout_sec":300,'
            '"stream_idle_timeout_sec":300,"request_total_timeout_sec":300,'
            '"retry_backoff_schedule_sec":[1,2,4,8,16,32,60,60,60],"reasoning_effort":"high"}],'
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

    provider = payload["providers"][0]
    assert provider["timeout_sec"] == 300
    assert provider["connect_timeout_sec"] == 10
    assert provider["write_timeout_sec"] == 20
    assert provider["first_token_timeout_sec"] == 300
    assert provider["stream_idle_timeout_sec"] == 300
    assert provider["request_total_timeout_sec"] == 300
    assert provider["retry_backoff_schedule_sec"] == [1, 2, 4, 8, 16, 32, 60, 60, 60]


def test_should_count_stall_ignores_active_execution_and_recoverable_provider_incident() -> None:
    assert _should_count_stall(
        workflow={"status": "EXECUTING"},
        active_ticket_ids=["tkt_build_001"],
        open_incidents=[],
    ) is False
    assert _should_count_stall(
        workflow={"status": "EXECUTING"},
        active_ticket_ids=[],
        open_incidents=[
            {
                "status": "OPEN",
                "incident_type": "PROVIDER_EXECUTION_PAUSED",
            }
        ],
    ) is False
    assert _should_count_stall(
        workflow={"status": "EXECUTING"},
        active_ticket_ids=[],
        open_incidents=[],
    ) is True
