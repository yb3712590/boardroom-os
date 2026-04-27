from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
import tests.live._autopilot_live_harness as live_harness
import tests.live._scenario_profiles as scenario_profiles
from fastapi.testclient import TestClient

from app.main import create_app
from app.core.runtime_liveness import build_runtime_liveness_report
from app.core.workflow_completion import (
    evaluate_workflow_closeout_gate_issue,
    resolve_workflow_closeout_completion,
)
from app.core.workspace_path_contracts import DEFAULT_WORKSPACE_PATH_TEMPLATES

from tests.live.architecture_governance_autopilot_live import SCENARIO as ARCHITECTURE_SCENARIO
from tests.live.architecture_governance_autopilot_smoke import (
    SCENARIO as ARCHITECTURE_SMOKE_SCENARIO,
    _assert_architecture_governance_smoke_checkpoint,
)
from tests.live.library_management_autopilot_smoke import (
    SCENARIO as LIBRARY_SMOKE_SCENARIO,
    _assert_library_check_stage_checkpoint,
    build_scenario_paths as build_library_smoke_paths,
)
from tests.live._autopilot_live_harness import (
    _collect_source_delivery_payload_audit,
    _assert_source_delivery_payload_quality,
    _assert_unique_source_delivery_evidence_paths,
    _build_success_report,
    _write_json,
    _should_count_stall,
    build_scenario_paths as _build_scenario_paths,
    integration_test_provider_template_path,
    load_integration_test_provider_payload,
    reset_scenario_root,
    write_audit_summary,
)
from tests.live._configured_runner import build_live_scenario
from tests.live._config import (
    LiveAssertionConfig,
    LiveProviderConfig,
    LiveRuntimeConfig,
    LiveScenarioConfig,
    LiveScenarioSection,
)
from tests.live._scenario_profiles import (
    MINIMALIST_BOOK_TRACKER_CONSTRAINTS,
    MINIMALIST_BOOK_TRACKER_GOAL,
    build_assert_outcome,
)
from tests.live.requirement_elicitation_autopilot_live import SCENARIO as REQUIREMENT_SCENARIO
from tests.test_api import _employee_hire_request_payload, _ensure_scoped_workflow, _persist_workflow_profile


def build_scenario_paths(scenario_root: Path | None = None):
    return _build_scenario_paths("library_management_autopilot_live", scenario_root)


def _library_live_config() -> LiveScenarioConfig:
    return LiveScenarioConfig(
        config_path=Path("/tmp/library_management_autopilot_live.toml"),
        scenario=LiveScenarioSection(
            slug="library_management_autopilot_live",
            description="Run the library management autopilot live scenario.",
            goal=MINIMALIST_BOOK_TRACKER_GOAL,
            workflow_profile="CEO_AUTOPILOT_FINE_GRAINED",
            force_requirement_elicitation=False,
            budget_cap=1_500_000,
            constraints=MINIMALIST_BOOK_TRACKER_CONSTRAINTS,
        ),
        runtime=LiveRuntimeConfig(seed=17, max_ticks=180, timeout_sec=7200),
        provider=LiveProviderConfig(
            provider_id="prov_openai_compat_truerealbill",
            base_url="http://codex.truerealbill.com:11234/v1",
            api_key="sk-test",
            api_key_env=None,
            preferred_model="gpt-5.4",
            max_context_window=270000,
            reasoning_effort="high",
            connect_timeout_sec=10,
            write_timeout_sec=20,
            first_token_timeout_sec=300,
            stream_idle_timeout_sec=300,
            fallback_provider_ids=(),
        ),
        assertions=LiveAssertionConfig(
            profile="minimalist_book_tracker",
            expected_provider_id="prov_openai_compat_truerealbill",
            expected_model="gpt-5.4",
            architect_reasoning_effort="xhigh",
            default_reasoning_effort="high",
        ),
        workspace_paths=DEFAULT_WORKSPACE_PATH_TEMPLATES,
    )


LIBRARY_SCENARIO = build_live_scenario(_library_live_config())
_assert_library_outcome = build_assert_outcome(_library_live_config().assertions)


def _library_backlog_payload(sequence: list[str] | None = None) -> dict:
    recommended_sequence = sequence or [f"BR00{index}" for index in range(1, 8)]
    return {
        "document_kind_ref": "backlog_recommendation",
        "title": "Library backlog recommendation",
        "summary": "Split the terminal library tracker into auditable follow-up tickets.",
        "implementation_handoff": {
            "tickets": [
                {
                    "ticket_id": ticket_key,
                    "name": f"{ticket_key} library delivery",
                    "summary": f"{ticket_key} library delivery",
                    "scope": ["books add check out return remove terminal console"],
                    "target_role": "frontend_engineer",
                }
                for ticket_key in recommended_sequence
            ],
            "dependency_graph": [
                {
                    "ticket_id": ticket_key,
                    "depends_on": [] if index == 0 else [recommended_sequence[index - 1]],
                }
                for index, ticket_key in enumerate(recommended_sequence)
            ],
            "recommended_sequence": recommended_sequence,
        },
    }


def _complete_library_common(*, materialized_count: int = 7, include_checker: bool = True) -> dict:
    scope_corpus = " ".join(
        [
            "books title author IN_LIBRARY CHECKED_OUT",
            "add check out return remove",
            "terminal console monochrome dense dark",
        ]
    )
    created_specs = {
        "tkt_arch": {
            "output_schema_ref": "architecture_brief",
            "summary": scope_corpus,
        },
        "tkt_backlog": {
            "output_schema_ref": "backlog_recommendation",
            "summary": scope_corpus,
        },
    }
    terminals = {
        "tkt_backlog": {
            "event_type": "TICKET_COMPLETED",
            "payload": _library_backlog_payload(),
        },
    }
    tickets = [
        {"ticket_id": "tkt_arch", "status": "COMPLETED", "node_id": "node_arch"},
        {"ticket_id": "tkt_backlog", "status": "COMPLETED", "node_id": "node_backlog"},
    ]
    audits = [
        {
            "ticket_id": "tkt_arch",
            "role_profile_ref": "architect_primary",
            "assumptions": {
                "actual_provider_id": "prov_openai_compat_truerealbill",
                "actual_model": "gpt-5.4",
                "effective_reasoning_effort": "xhigh",
            },
        }
    ]
    source_delivery_ticket_ids: list[str] = []
    for index in range(1, materialized_count + 1):
        ticket_key = f"BR00{index}"
        ticket_id = f"tkt_{ticket_key.lower()}"
        created_specs[ticket_id] = {
            "ticket_id": ticket_id,
            "output_schema_ref": "source_code_delivery",
            "delivery_stage": "BUILD",
            "node_id": f"node_backlog_followup_{ticket_key.lower()}",
            "parent_ticket_id": "tkt_backlog",
            "summary": f"{ticket_key} {scope_corpus}",
        }
        terminals[ticket_id] = {
            "event_type": "TICKET_COMPLETED",
            "payload": {
                "summary": f"{ticket_key} {scope_corpus}",
                "source_files": [{"path": f"src/{ticket_key.lower()}.py", "content": scope_corpus}],
                "verification_runs": [{"command": "pytest -q", "stdout": "1 passed\n"}],
            },
        }
        tickets.append(
            {
                "ticket_id": ticket_id,
                "status": "COMPLETED",
                "node_id": f"node_backlog_followup_{ticket_key.lower()}",
            }
        )
        audits.append(
            {
                "ticket_id": ticket_id,
                "role_profile_ref": "frontend_engineer_primary",
                "assumptions": {
                    "actual_provider_id": "prov_openai_compat_truerealbill",
                    "actual_model": "gpt-5.4",
                    "effective_reasoning_effort": "high",
                },
            }
        )
        source_delivery_ticket_ids.append(ticket_id)
    if include_checker:
        created_specs["tkt_br007_checker"] = {
            "ticket_id": "tkt_br007_checker",
            "output_schema_ref": "maker_checker_verdict",
            "delivery_stage": "REVIEW",
            "maker_checker_context": {
                "maker_ticket_id": "tkt_br007",
                "maker_ticket_spec": created_specs.get("tkt_br007", {}),
            },
        }
        terminals["tkt_br007_checker"] = {
            "event_type": "TICKET_COMPLETED",
            "payload": {
                "review_status": "APPROVED",
                "maker_checker_summary": {"review_status": "APPROVED"},
            },
        }
        tickets.append(
            {
                "ticket_id": "tkt_br007_checker",
                "status": "COMPLETED",
                "node_id": "node_backlog_followup_br007",
            }
        )
        audits.append(
            {
                "ticket_id": "tkt_br007_checker",
                "role_profile_ref": "checker_primary",
                "assumptions": {
                    "actual_provider_id": "prov_openai_compat_truerealbill",
                    "actual_model": "gpt-5.4",
                    "effective_reasoning_effort": "high",
                },
            }
        )
    return {
        "tickets": tickets,
        "employees": [{"role_type": "governance_architect"}],
        "audits": audits,
        "architect_ticket_ids": ["tkt_arch"],
        "created_specs": created_specs,
        "terminals": terminals,
        "source_delivery_ticket_ids": source_delivery_ticket_ids,
    }


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


def test_library_scenario_scope_no_longer_uses_ticket_count_as_size_limit() -> None:
    constraints = "\n".join(LIBRARY_SCENARIO.constraints)

    assert "books" in constraints
    assert "IN_LIBRARY" in constraints
    assert "CHECKED_OUT" in constraints
    assert "Check Out" in constraints
    assert "Return" in constraints
    assert "匿名" in LIBRARY_SCENARIO.goal
    assert "单机" in LIBRARY_SCENARIO.goal
    assert "terminal/console" in constraints
    assert "权限系统" in constraints
    assert "时间轴" in constraints
    assert "借阅历史" in constraints
    assert "分类表" in constraints or "复杂分类" in constraints


def test_library_outcome_accepts_completed_followup_fanout_and_checker_handoff() -> None:
    common = _complete_library_common()

    result = _assert_library_outcome(None, object(), "wf_library", common)

    assert result["scope_capabilities"] == [
        "books",
        "title",
        "author",
        "IN_LIBRARY",
        "CHECKED_OUT",
        "add",
        "check out",
        "return",
        "remove",
        "terminal",
        "console",
    ]
    assert result["required_followup_ticket_keys"] == [f"BR00{index}" for index in range(1, 8)]
    assert result["checker_handoff_ticket_ids"] == ["tkt_br007_checker"]


def test_library_outcome_rejects_missing_followup_fanout_even_if_capability_terms_present() -> None:
    common = _complete_library_common(materialized_count=3, include_checker=False)

    with pytest.raises(AssertionError, match="missing followup materialization"):
        _assert_library_outcome(None, object(), "wf_library", common)


def test_library_outcome_requires_checker_handoff_before_full_success() -> None:
    common = _complete_library_common(include_checker=False)

    with pytest.raises(AssertionError, match="checker handoff"):
        _assert_library_outcome(None, object(), "wf_library", common)


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


def test_write_audit_summary_renders_staffing_gap_and_hire_action(tmp_path: Path) -> None:
    paths = build_scenario_paths(tmp_path / "library_management_autopilot_live")
    reset_scenario_root(paths, clean=True)

    target_path = write_audit_summary(
        paths,
        report={
            "success": False,
            "scenario_slug": "library_management_autopilot_live",
            "workflow_id": "wf_library_live",
            "completion_mode": "timeout",
        },
        snapshot={
            "workflow": {
                "workflow_id": "wf_library_live",
                "status": "EXECUTING",
                "current_stage": "build",
            },
            "staffing_gap_audit": {
                "gaps": [
                    {
                        "ticket_id": "tkt_br004_rework",
                        "node_id": "node_br004",
                        "required_role_profile_ref": "backend_engineer_primary",
                        "reason_code": "NO_ELIGIBLE_WORKER",
                    }
                ],
                "hire_actions": [
                    {
                        "run_id": "ceo_run_001",
                        "role_type": "backend_engineer",
                        "role_profile_refs": ["backend_engineer_primary"],
                        "employee_id": "emp_backend_backup",
                        "execution_status": "EXECUTED",
                    }
                ],
            },
        },
    )

    body = target_path.read_text(encoding="utf-8")
    assert "## Staffing Gap Audit" in body
    assert "tkt_br004_rework" in body
    assert "backend_engineer_primary" in body
    assert "emp_backend_backup" in body


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


def test_runtime_ticket_audit_uses_reasoning_effort_from_provider_audit_events(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        live_harness,
        "workflow_ticket_rows",
        lambda _repository, _workflow_id: [
            {
                "ticket_id": "tkt_checker_001",
                "node_id": "node_check",
                "status": "COMPLETED",
            }
        ],
    )
    monkeypatch.setattr(
        live_harness,
        "workflow_created_specs",
        lambda _repository, _workflow_id: {
            "tkt_checker_001": {
                "role_profile_ref": "checker_primary",
                "output_schema_ref": "maker_checker_verdict",
            }
        },
    )
    monkeypatch.setattr(
        live_harness,
        "workflow_terminal_events",
        lambda _repository, _workflow_id: {
            "tkt_checker_001": {
                "payload": {
                    "review_status": "APPROVED",
                }
            }
        },
    )
    monkeypatch.setattr(
        live_harness,
        "workflow_provider_audit_events",
        lambda _repository, _workflow_id: {
            "tkt_checker_001": [
                {
                    "event_type": "PROVIDER_ATTEMPT_FINISHED",
                    "payload": {
                        "provider_id": "prov_primary",
                        "actual_model": "gpt-5.5",
                        "attempt_no": 1,
                        "status": "COMPLETED",
                        "effective_reasoning_effort": "xhigh",
                    },
                }
            ]
        },
    )

    audits = live_harness.build_runtime_ticket_audit(object(), "wf_live")

    assert audits[0]["assumptions"]["effective_reasoning_effort"] == "xhigh"


def test_runtime_ticket_audit_infers_reasoning_effort_from_runtime_binding_when_audit_is_legacy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        live_harness,
        "workflow_ticket_rows",
        lambda _repository, _workflow_id: [
            {
                "ticket_id": "tkt_checker_legacy",
                "node_id": "node_check",
                "status": "COMPLETED",
            }
        ],
    )
    monkeypatch.setattr(
        live_harness,
        "workflow_created_specs",
        lambda _repository, _workflow_id: {
            "tkt_checker_legacy": {
                "role_profile_ref": "checker_primary",
                "output_schema_ref": "maker_checker_verdict",
            }
        },
    )
    monkeypatch.setattr(
        live_harness,
        "workflow_terminal_events",
        lambda _repository, _workflow_id: {
            "tkt_checker_legacy": {
                "payload": {
                    "review_status": "APPROVED",
                }
            }
        },
    )
    monkeypatch.setattr(
        live_harness,
        "workflow_provider_audit_events",
        lambda _repository, _workflow_id: {
            "tkt_checker_legacy": [
                {
                    "event_type": "PROVIDER_ATTEMPT_FINISHED",
                    "payload": {
                        "provider_id": "prov_primary",
                        "actual_model": "gpt-5.5",
                        "attempt_no": 1,
                        "status": "COMPLETED",
                    },
                }
            ]
        },
    )
    monkeypatch.setattr(live_harness, "resolve_runtime_provider_config", lambda: object(), raising=False)
    monkeypatch.setattr(
        live_harness,
        "resolve_provider_selection",
        lambda _config, **_kwargs: SimpleNamespace(effective_reasoning_effort="xhigh"),
        raising=False,
    )

    audits = live_harness.build_runtime_ticket_audit(object(), "wf_live")

    assert audits[0]["assumptions"]["effective_reasoning_effort"] == "xhigh"


def test_find_backlog_handoff_reads_written_artifact_content_json() -> None:
    ticket_id, handoff = scenario_profiles._find_backlog_handoff(
        {
            "created_specs": {
                "tkt_backlog": {
                    "output_schema_ref": "backlog_recommendation",
                }
            },
            "terminals": {
                "tkt_backlog": {
                    "payload": {
                        "written_artifacts": [
                            {
                                "content_json": {
                                    "implementation_handoff": {
                                        "recommended_sequence": ["BR-001"],
                                        "tickets": [{"ticket_id": "BR-001"}],
                                    }
                                }
                            }
                        ]
                    }
                }
            },
        }
    )

    assert ticket_id == "tkt_backlog"
    assert handoff["recommended_sequence"] == ["BR-001"]


def test_materialized_followups_can_accept_non_source_delivery_tickets_for_prd_profiles() -> None:
    materialized = scenario_profiles._materialized_followup_ticket_ids(
        {
            "tickets": [
                {
                    "ticket_id": "tkt_gov",
                    "status": "COMPLETED",
                }
            ],
            "created_specs": {
                "tkt_gov": {
                    "node_id": "node_backlog_followup_br_gov_001",
                    "output_schema_ref": "backlog_recommendation",
                }
            },
        },
        backlog_ticket_id="tkt_backlog",
        required_followup_keys=["BR-GOV-001"],
        required_output_schema_ref=None,
    )

    assert materialized == {"BR-GOV-001": "tkt_gov"}


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

    with pytest.raises(AssertionError, match="raw verification output"):
        _assert_source_delivery_payload_quality(created_specs, terminals)


def test_snapshot_source_delivery_payload_audit_records_quality_error_without_raising() -> None:
    created_specs = {
        "tkt_build_001": {
            "output_schema_ref": "source_code_delivery",
        }
    }
    terminals = {
        "tkt_build_001": {
            "event_type": "TICKET_COMPLETED",
            "payload": {
                "written_artifacts": [{"artifact_ref": "art://workspace/tkt_build_001/source.ts"}],
                "verification_evidence_refs": ["art://workspace/tkt_build_001/test-report.json"],
                "verification_runs": [],
            },
        }
    }

    audit = live_harness._collect_source_delivery_payload_audit_for_snapshot(created_specs, terminals)

    assert audit["completed_ticket_ids"] == []
    assert audit["failed_retry_count"] == 0
    assert "non-materialized artifact_ref" in audit["audit_error"]


def test_source_delivery_payload_quality_accepts_compact_evidence_artifact_raw_output() -> None:
    created_specs = {
        "tkt_build_001": {
            "output_schema_ref": "source_code_delivery",
        }
    }
    terminals = {
        "tkt_build_001": {
            "event_type": "TICKET_COMPLETED",
            "payload": {
                "written_artifacts": [
                    {
                        "artifact_ref": "art://workspace/tkt_build_001/tests/report.json",
                        "path": "20-evidence/tests/attempt-1/report.json",
                        "content_json": {
                            "artifact_ref": "art://workspace/tkt_build_001/tests/report.json",
                            "path": "20-evidence/tests/attempt-1/report.json",
                            "runner": "pytest",
                            "command": "pytest -q",
                            "status": "passed",
                            "exit_code": 0,
                            "duration_sec": 0.3,
                            "stdout": "1 passed\n",
                            "stderr": "",
                            "discovered_count": 1,
                            "passed_count": 1,
                            "failed_count": 0,
                            "skipped_count": 0,
                            "failures": [],
                        },
                    }
                ],
                "verification_evidence_refs": ["art://workspace/tkt_build_001/tests/report.json"],
            },
        }
    }

    assert _assert_source_delivery_payload_quality(created_specs, terminals) == ["tkt_build_001"]


def test_source_delivery_compact_payload_requires_evidence_ref_content_json_raw_output() -> None:
    created_specs = {
        "tkt_build_001": {
            "output_schema_ref": "source_code_delivery",
        }
    }
    terminals = {
        "tkt_build_001": {
            "event_type": "TICKET_COMPLETED",
            "payload": {
                "written_artifacts": [
                    {
                        "artifact_ref": "art://workspace/tkt_build_001/tests/report.json",
                        "path": "20-evidence/tests/tkt_build_001/attempt-1/report.json",
                        "content_json": {
                            "artifact_ref": "art://workspace/tkt_build_001/tests/report.json",
                            "path": "20-evidence/tests/tkt_build_001/attempt-1/report.json",
                            "command": "pytest -q",
                            "stdout": "",
                            "stderr": "",
                        },
                    }
                ],
                "verification_evidence_refs": ["art://workspace/tkt_build_001/tests/report.json"],
            },
        }
    }

    with pytest.raises(AssertionError, match="raw verification output"):
        _assert_source_delivery_payload_quality(created_specs, terminals)


def test_source_delivery_payload_quality_accepts_compact_stderr_raw_output() -> None:
    created_specs = {
        "tkt_build_001": {
            "output_schema_ref": "source_code_delivery",
        }
    }
    terminals = {
        "tkt_build_001": {
            "event_type": "TICKET_COMPLETED",
            "payload": {
                "written_artifacts": [
                    {
                        "artifact_ref": "art://workspace/tkt_build_001/tests/report.json",
                        "path": "20-evidence/tests/tkt_build_001/attempt-1/report.json",
                        "content_json": {
                            "artifact_ref": "art://workspace/tkt_build_001/tests/report.json",
                            "path": "20-evidence/tests/tkt_build_001/attempt-1/report.json",
                            "runner": "pytest",
                            "command": "pytest -q",
                            "status": "failed",
                            "exit_code": 1,
                            "duration_sec": 0.3,
                            "stdout": "",
                            "stderr": "AssertionError: regression failed\n",
                            "discovered_count": 1,
                            "passed_count": 0,
                            "failed_count": 1,
                            "skipped_count": 0,
                            "failures": [],
                        },
                    }
                ],
                "verification_evidence_refs": ["art://workspace/tkt_build_001/tests/report.json"],
            },
        }
    }

    assert _assert_source_delivery_payload_quality(created_specs, terminals) == ["tkt_build_001"]


def test_failed_retry_history_is_reported_in_audit_summary_without_blocking_final_success(tmp_path: Path) -> None:
    created_specs = {
        "tkt_failed": {"output_schema_ref": "source_code_delivery"},
        "tkt_completed": {"output_schema_ref": "source_code_delivery"},
    }
    terminals = {
        "tkt_failed": {
            "event_type": "TICKET_FAILED",
            "payload": {
                "ticket_id": "tkt_failed",
                "failure_kind": "WORKSPACE_HOOK_VALIDATION_ERROR",
            },
        },
        "tkt_completed": {
            "event_type": "TICKET_COMPLETED",
            "payload": {
                "ticket_id": "tkt_completed",
                "written_artifacts": [{"artifact_ref": "art://workspace/tkt_completed/source.py"}],
                "verification_evidence_refs": ["art://workspace/tkt_completed/tests.json"],
                "verification_runs": [
                    {
                        "command": "pytest -q",
                        "stdout": "1 passed\n",
                    }
                ],
            },
        },
    }

    assert _assert_source_delivery_payload_quality(created_specs, terminals) == ["tkt_completed"]
    audit = _collect_source_delivery_payload_audit(created_specs, terminals)
    assert audit["completed_ticket_ids"] == ["tkt_completed"]
    assert audit["failed_retry_entries"] == [
        {
            "ticket_id": "tkt_failed",
            "failure_kind": "WORKSPACE_HOOK_VALIDATION_ERROR",
        }
    ]

    paths = build_scenario_paths(tmp_path / "library_management_autopilot_live")
    reset_scenario_root(paths, clean=True)
    target_path = write_audit_summary(
        paths,
        report={
            "success": True,
            "scenario_slug": "library_management_autopilot_live",
            "workflow_id": "wf_library_live",
            "completion_mode": "full",
        },
        snapshot={
            "workflow": {
                "workflow_id": "wf_library_live",
                "status": "COMPLETED",
                "current_stage": "closeout",
            },
            "source_delivery_payload_audit": audit,
        },
    )

    body = target_path.read_text(encoding="utf-8")
    assert "Source Delivery Retry Audit" in body
    assert "tkt_failed" in body
    assert "WORKSPACE_HOOK_VALIDATION_ERROR" in body


def test_write_audit_summary_groups_recovered_provider_failures(tmp_path: Path) -> None:
    tickets = [
        {
            "ticket_id": "tkt_provider_json_failed",
            "node_id": "node_build_001",
            "status": "FAILED",
        },
        {
            "ticket_id": "tkt_provider_json_completed",
            "node_id": "node_build_001",
            "status": "COMPLETED",
        },
    ]
    terminals = {
        "tkt_provider_json_failed": {
            "event_type": "TICKET_FAILED",
            "payload": {
                "ticket_id": "tkt_provider_json_failed",
                "failure_kind": "PROVIDER_MALFORMED_JSON",
                "failure_detail": {
                    "provider_id": "prov_primary",
                    "actual_model": "gpt-5.4",
                    "fingerprint": "provider:prov_primary:gpt-5.4:PROVIDER_MALFORMED_JSON:repair_parse",
                },
            },
        },
        "tkt_provider_json_completed": {
            "event_type": "TICKET_COMPLETED",
            "payload": {"ticket_id": "tkt_provider_json_completed"},
        },
    }

    recovered_audit = live_harness._collect_recovered_failure_audit(
        tickets=tickets,
        terminals=terminals,
        provider_audit_by_ticket={},
        incidents=[],
    )

    assert recovered_audit["total_count"] == 1
    provider_group = recovered_audit["groups"]["Provider JSON / Bad Response"]
    assert provider_group["count"] == 1
    assert provider_group["entries"][0]["ticket_id"] == "tkt_provider_json_failed"
    assert provider_group["entries"][0]["node_id"] == "node_build_001"
    assert provider_group["entries"][0]["failure_kind"] == "PROVIDER_MALFORMED_JSON"
    assert provider_group["entries"][0]["recovered_by_ticket_id"] == "tkt_provider_json_completed"

    paths = build_scenario_paths(tmp_path / "library_management_autopilot_live")
    reset_scenario_root(paths, clean=True)
    target_path = write_audit_summary(
        paths,
        report={
            "success": True,
            "scenario_slug": "library_management_autopilot_live",
            "workflow_id": "wf_library_live",
            "completion_mode": "full",
        },
        snapshot={
            "workflow": {
                "workflow_id": "wf_library_live",
                "status": "COMPLETED",
                "current_stage": "closeout",
            },
            "tickets": tickets,
            "recovered_failure_audit": recovered_audit,
        },
    )

    body = target_path.read_text(encoding="utf-8")
    assert "## Recovered Failure Audit" in body
    assert "Provider JSON / Bad Response" in body
    assert "tkt_provider_json_failed" in body
    assert "PROVIDER_MALFORMED_JSON" in body
    assert "recovered by `tkt_provider_json_completed`" in body


def test_failed_retry_history_distinguishes_provider_and_hook_failures(tmp_path: Path) -> None:
    tickets = [
        {
            "ticket_id": "tkt_provider_no_json",
            "node_id": "node_build_001",
            "status": "FAILED",
        },
        {
            "ticket_id": "tkt_hook_validation",
            "node_id": "node_build_001",
            "status": "FAILED",
        },
        {
            "ticket_id": "tkt_build_completed",
            "node_id": "node_build_001",
            "status": "COMPLETED",
        },
    ]
    terminals = {
        "tkt_provider_no_json": {
            "event_type": "TICKET_FAILED",
            "payload": {
                "ticket_id": "tkt_provider_no_json",
                "failure_kind": "NO_JSON_OBJECT",
                "failure_detail": {
                    "provider_id": "prov_primary",
                    "actual_model": "gpt-5.4",
                    "fingerprint": "provider:prov_primary:gpt-5.4:NO_JSON_OBJECT:missing_json",
                },
            },
        },
        "tkt_hook_validation": {
            "event_type": "TICKET_FAILED",
            "payload": {
                "ticket_id": "tkt_hook_validation",
                "failure_kind": "WORKSPACE_HOOK_VALIDATION_ERROR",
                "failure_detail": {
                    "hook_id": "source_code_delivery.required_evidence",
                    "fingerprint": "hook:source_code_delivery.required_evidence",
                },
            },
        },
        "tkt_build_completed": {
            "event_type": "TICKET_COMPLETED",
            "payload": {"ticket_id": "tkt_build_completed"},
        },
    }

    recovered_audit = live_harness._collect_recovered_failure_audit(
        tickets=tickets,
        terminals=terminals,
        provider_audit_by_ticket={},
        incidents=[],
    )

    assert recovered_audit["groups"]["Provider JSON / Bad Response"]["count"] == 1
    assert recovered_audit["groups"]["Workspace Hook Validation"]["count"] == 1
    assert recovered_audit["groups"]["Provider JSON / Bad Response"]["entries"][0]["failure_kind"] == "NO_JSON_OBJECT"
    assert (
        recovered_audit["groups"]["Workspace Hook Validation"]["entries"][0]["failure_kind"]
        == "WORKSPACE_HOOK_VALIDATION_ERROR"
    )

    paths = build_scenario_paths(tmp_path / "library_management_autopilot_live")
    reset_scenario_root(paths, clean=True)
    target_path = write_audit_summary(
        paths,
        report={
            "success": True,
            "scenario_slug": "library_management_autopilot_live",
            "workflow_id": "wf_library_live",
            "completion_mode": "full",
        },
        snapshot={
            "workflow": {
                "workflow_id": "wf_library_live",
                "status": "COMPLETED",
                "current_stage": "closeout",
            },
            "tickets": tickets,
            "recovered_failure_audit": recovered_audit,
        },
    )

    body = target_path.read_text(encoding="utf-8")
    assert "Provider JSON / Bad Response" in body
    assert "Workspace Hook Validation" in body
    assert "tkt_provider_no_json" in body
    assert "tkt_hook_validation" in body
    assert "NO_JSON_OBJECT" in body
    assert "WORKSPACE_HOOK_VALIDATION_ERROR" in body


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


def test_library_smoke_scenario_uses_it006_checkpoint_label() -> None:
    assert LIBRARY_SMOKE_SCENARIO.checkpoint_label == "library_check_stage_gate"
    assert LIBRARY_SMOKE_SCENARIO.slug == "library_management_autopilot_smoke"


def test_library_smoke_scenario_uses_dedicated_paths(tmp_path: Path) -> None:
    paths = build_library_smoke_paths(tmp_path / "library_management_autopilot_smoke")

    assert paths.root.name == "library_management_autopilot_smoke"
    assert paths.run_report_path.name == "run_report.json"
    assert paths.audit_summary_path.name == "audit-summary.md"


def test_library_smoke_checkpoint_requires_check_stage_without_006_failure_fingerprint() -> None:
    assertions = _assert_library_check_stage_checkpoint(
        None,
        None,
        "wf_library_smoke",
        {
            "workflow": {
                "workflow_id": "wf_library_smoke",
                "status": "EXECUTING",
                "current_stage": "check",
            },
            "tickets": [],
            "created_specs": {},
            "terminals": {},
            "approvals": [],
            "audits": [],
            "architect_ticket_ids": [],
            "employees": [],
            "base_report": {
                "workflow_id": "wf_library_smoke",
                "workflow_status": "EXECUTING",
                "workflow_stage": "check",
            },
        },
    )

    assert assertions is not None
    assert assertions["workflow_stage"] == "check"
    assert assertions["checkpoint_reason"] == "entered_check_without_it006_failure_signals"


def test_library_smoke_checkpoint_rejects_dependency_gate_unhealthy_signal() -> None:
    assertions = _assert_library_check_stage_checkpoint(
        None,
        None,
        "wf_library_smoke",
        {
            "workflow": {
                "workflow_id": "wf_library_smoke",
                "status": "EXECUTING",
                "current_stage": "check",
            },
            "tickets": [
                {
                    "ticket_id": "tkt_006_failed",
                    "last_failure_kind": "DEPENDENCY_GATE_UNHEALTHY",
                }
            ],
            "created_specs": {},
            "terminals": {},
            "approvals": [],
            "audits": [],
            "architect_ticket_ids": [],
            "employees": [],
            "base_report": {
                "workflow_id": "wf_library_smoke",
                "workflow_status": "EXECUTING",
                "workflow_stage": "check",
            },
        },
    )

    assert assertions is None


def test_integration_test_provider_template_path_uses_backend_data() -> None:
    path = integration_test_provider_template_path()
    assert path.name == "integration-test-provider-config.json"
    assert path.parent.name == "data"


def test_load_integration_test_provider_payload_requires_existing_template_path(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="Integration test provider config is missing"):
        load_integration_test_provider_payload(
            scenario_slug="library_management_autopilot_live",
            config_path=tmp_path / "missing-provider-config.json",
        )


def test_live_scenario_environment_sets_configured_default_employee_provider(tmp_path: Path) -> None:
    config = _library_live_config()
    paths = build_scenario_paths(tmp_path / "library_management_autopilot_live")
    provider_payload = config.build_runtime_provider_payload()
    provider = provider_payload["providers"][0]

    with live_harness.scenario_environment(
        paths,
        base_url=provider["base_url"],
        api_key=provider["api_key"],
        provider_id=provider["provider_id"],
        seed=config.runtime.seed,
    ):
        assert os.environ["BOARDROOM_OS_DEFAULT_EMPLOYEE_PROVIDER_ID"] == "prov_openai_compat_truerealbill"
        assert os.environ["BOARDROOM_OS_RUNTIME_STRICT_PROVIDER_SELECTION"] == "1"


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


def test_load_integration_test_provider_payload_strips_default_provider_id(tmp_path: Path) -> None:
    config_path = tmp_path / "integration-test-provider-config.json"
    config_path.write_text(
        (
            '{'
            '"default_provider_id":"prov_openai_compat_truerealbill",'
            '"providers":[{"provider_id":"prov_openai_compat_truerealbill","type":"openai_responses_stream","enabled":true,'
            '"base_url":"http://codex.truerealbill.com:11234/v1","api_key":"sk-test","alias":"integration-live",'
            '"preferred_model":"gpt-5.4","max_context_window":null,"reasoning_effort":"high"}],'
            '"provider_model_entries":[{"provider_id":"prov_openai_compat_truerealbill","model_name":"gpt-5.4"}],'
            '"role_bindings":[{"target_ref":"ceo_shadow",'
            '"provider_model_entry_refs":["prov_openai_compat_truerealbill::gpt-5.4"],'
            '"max_context_window_override":null,"reasoning_effort_override":"high"}]'
            '}'
        ),
        encoding="utf-8",
    )

    payload = load_integration_test_provider_payload(
        scenario_slug="library_management_autopilot_live",
        config_path=config_path,
    )

    assert "default_provider_id" not in payload
    assert payload["providers"][0]["provider_id"] == "prov_openai_compat_truerealbill"


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
            '"stream_idle_timeout_sec":300,'
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
    assert "request_total_timeout_sec" not in provider
    assert provider["retry_backoff_schedule_sec"] == [1, 2, 4, 8, 16, 32, 60, 60, 60]


def test_maybe_recover_live_delegate_blockers_approves_core_hire_request(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("BOARDROOM_OS_DB_PATH", str(tmp_path / "boardroom_os.db"))

    with TestClient(create_app()) as client:
        workflow_id = "wf_live_resume"
        _ensure_scoped_workflow(
            client,
            workflow_id=workflow_id,
            tenant_id="tenant_default",
            workspace_id="ws_default",
            goal="Resume approval-blocked live workflow",
        )
        _persist_workflow_profile(
            client.app.state.repository,
            workflow_id,
            "CEO_AUTOPILOT_FINE_GRAINED",
        )
        hire_response = client.post(
            "/api/v1/commands/employee-hire-request",
            json=_employee_hire_request_payload(
                workflow_id,
                employee_id="emp_architect_governance",
                role_type="governance_architect",
                role_profile_refs=["architect_primary"],
                skill_profile={
                    "primary_domain": "architecture",
                    "system_scope": "design_review",
                    "validation_bias": "finish_first",
                },
                personality_profile={
                    "risk_posture": "guarded",
                    "challenge_style": "adversarial",
                    "execution_pace": "measured",
                    "detail_rigor": "sweeping",
                    "communication_style": "forensic",
                },
                aesthetic_profile={
                    "surface_preference": "polished",
                    "information_density": "dense",
                    "motion_tolerance": "restrained",
                },
                request_summary="Hire a board-approved architect_primary now so the workflow can continue.",
            ),
        )

        assert hire_response.status_code == 200
        assert hire_response.json()["status"] == "ACCEPTED"

        repository = client.app.state.repository
        approval = next(item for item in repository.list_open_approvals() if item["workflow_id"] == workflow_id)

        recovered = live_harness._maybe_recover_live_delegate_blockers(
            repository,
            workflow_id=workflow_id,
            idempotency_key_prefix="test-live-harness",
            tick_index=1,
        )

        updated = repository.get_approval_by_review_pack_id(approval["review_pack_id"])
        employee = repository.get_employee_projection("emp_architect_governance")

        assert recovered is True
        assert updated is not None
        assert updated["status"] == "APPROVED"
        assert updated["resolved_by"] == "ceo_delegate"
        assert employee is not None
        assert employee["board_approved"] is True


def test_run_cli_respects_clean_flag(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    recorded: dict[str, object] = {}

    def _fake_run_live_scenario(
        scenario,
        *,
        clean: bool = True,
        max_ticks: int = 180,
        timeout_sec: int = 7200,
        seed: int = 17,
        scenario_root: Path | None = None,
    ) -> dict[str, object]:
        recorded.update(
            {
                "scenario_slug": scenario.slug,
                "clean": clean,
                "max_ticks": max_ticks,
                "timeout_sec": timeout_sec,
                "seed": seed,
                "scenario_root": scenario_root,
            }
        )
        return {"success": True}

    monkeypatch.setattr(live_harness, "run_live_scenario", _fake_run_live_scenario)

    exit_code = live_harness.run_cli(
        LIBRARY_SCENARIO,
        [
            "--max-ticks",
            "12",
            "--timeout-sec",
            "34",
            "--seed",
            "56",
            "--scenario-root",
            str(tmp_path),
        ],
    )

    assert exit_code == 0
    assert recorded["scenario_slug"] == LIBRARY_SCENARIO.slug
    assert recorded["clean"] is False
    assert recorded["max_ticks"] == 12
    assert recorded["timeout_sec"] == 34
    assert recorded["seed"] == 56
    assert recorded["scenario_root"] == tmp_path


def test_latest_resumable_workflow_id_prefers_newest_executing_workflow(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("BOARDROOM_OS_DB_PATH", str(tmp_path / "boardroom_os.db"))

    with TestClient(create_app()) as client:
        _ensure_scoped_workflow(
            client,
            workflow_id="wf_completed",
            tenant_id="tenant_default",
            workspace_id="ws_default",
            goal="Completed workflow",
        )
        _ensure_scoped_workflow(
            client,
            workflow_id="wf_resumable",
            tenant_id="tenant_default",
            workspace_id="ws_default",
            goal="Resumable workflow",
        )

        repository = client.app.state.repository
        with repository.transaction() as connection:
            connection.execute(
                """
                UPDATE workflow_projection
                SET status = 'COMPLETED', current_stage = 'closeout', updated_at = '2026-04-20T22:00:00+08:00'
                WHERE workflow_id = 'wf_completed'
                """
            )
            connection.execute(
                """
                UPDATE workflow_projection
                SET status = 'EXECUTING', current_stage = 'project_init', updated_at = '2026-04-20T22:11:58+08:00'
                WHERE workflow_id = 'wf_resumable'
                """
            )

        assert live_harness._latest_resumable_workflow_id(repository) == "wf_resumable"


def test_non_clean_resume_does_not_report_existing_completed_workflow_as_new_success(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("BOARDROOM_OS_DB_PATH", str(tmp_path / "boardroom_os.db"))

    with TestClient(create_app()) as client:
        _ensure_scoped_workflow(
            client,
            workflow_id="wf_completed_only",
            tenant_id="tenant_default",
            workspace_id="ws_default",
            goal="Completed workflow must not be reused as a new live success.",
        )

        repository = client.app.state.repository
        with repository.transaction() as connection:
            connection.execute(
                """
                UPDATE workflow_projection
                SET status = 'COMPLETED', current_stage = 'closeout', updated_at = '2026-04-20T22:00:00+08:00'
                WHERE workflow_id = 'wf_completed_only'
                """
            )

        assert live_harness._latest_resumable_workflow_id(repository) is None


def test_library_replay_fail_closed_check_does_not_resolve_full_success() -> None:
    tickets = [
        {
            "ticket_id": "BR-BUILD-001",
            "status": "COMPLETED",
            "node_id": "node_br_build_001",
            "updated_at": datetime.fromisoformat("2026-04-20T21:00:00+08:00"),
        },
        {
            "ticket_id": "BR-CHECK-001",
            "status": "COMPLETED",
            "node_id": "node_br_check_001",
            "updated_at": datetime.fromisoformat("2026-04-20T21:10:00+08:00"),
        },
        {
            "ticket_id": "BR-CLOSEOUT-001",
            "status": "COMPLETED",
            "node_id": "node_br_closeout_001",
            "updated_at": datetime.fromisoformat("2026-04-20T21:20:00+08:00"),
        },
    ]
    nodes = [
        {"node_id": "node_br_build_001", "status": "COMPLETED"},
        {"node_id": "node_br_check_001", "status": "COMPLETED"},
        {"node_id": "node_br_closeout_001", "status": "COMPLETED"},
    ]
    created_specs = {
        "BR-BUILD-001": {
            "ticket_id": "BR-BUILD-001",
            "output_schema_ref": "source_code_delivery",
            "delivery_stage": "BUILD",
        },
        "BR-CHECK-001": {
            "ticket_id": "BR-CHECK-001",
            "output_schema_ref": "delivery_check_report",
            "delivery_stage": "CHECK",
            "parent_ticket_id": "BR-BUILD-001",
        },
        "BR-CLOSEOUT-001": {
            "ticket_id": "BR-CLOSEOUT-001",
            "output_schema_ref": "delivery_closeout_package",
            "delivery_stage": "CLOSEOUT",
            "parent_ticket_id": "BR-CHECK-001",
        },
    }
    terminals = {
        "BR-BUILD-001": {
            "event_type": "TICKET_COMPLETED",
            "occurred_at": datetime.fromisoformat("2026-04-20T21:00:00+08:00"),
            "payload": {
                "artifact_refs": ["art://runtime/BR-BUILD-001/source.py"],
                "written_artifacts": [
                    {"artifact_ref": "art://runtime/BR-BUILD-001/source.py"}
                ],
            },
        },
        "BR-CHECK-001": {
            "event_type": "TICKET_COMPLETED",
            "occurred_at": datetime.fromisoformat("2026-04-20T21:10:00+08:00"),
            "payload": {
                "artifact_refs": ["art://runtime/BR-CHECK-001/delivery-check-report.json"],
                "written_artifacts": [
                    {
                        "artifact_ref": "art://runtime/BR-CHECK-001/delivery-check-report.json",
                        "content_json": {
                            "status": "FAIL_CLOSED",
                            "summary": "BR-CHECK-001 FAIL_CLOSED: not approved for completion.",
                            "findings": [
                                {
                                    "finding_id": "missing_runtime_evidence",
                                    "summary": "Runtime and QA evidence are missing.",
                                    "blocking": True,
                                }
                            ],
                        },
                    }
                ],
            },
        },
        "BR-CLOSEOUT-001": {
            "event_type": "TICKET_COMPLETED",
            "occurred_at": datetime.fromisoformat("2026-04-20T21:20:00+08:00"),
            "payload": {
                "artifact_refs": ["art://runtime/BR-CLOSEOUT-001/delivery-closeout-package.json"],
                "written_artifacts": [
                    {
                        "artifact_ref": "art://runtime/BR-CLOSEOUT-001/delivery-closeout-package.json",
                        "content_json": {
                            "summary": "FAIL_CLOSED: not approved for completion.",
                            "final_artifact_refs": ["art://runtime/BR-BUILD-001/source.py"],
                            "handoff_notes": ["not approved for completion"],
                            "documentation_updates": [
                                {
                                    "doc_ref": "README.md",
                                    "status": "NO_CHANGE_REQUIRED",
                                    "summary": "No successful delivery evidence was produced.",
                                }
                            ],
                        },
                    }
                ],
            },
        },
    }

    issue = evaluate_workflow_closeout_gate_issue(
        tickets=tickets,
        created_specs_by_ticket=created_specs,
        ticket_terminal_events_by_ticket=terminals,
        closeout_ticket=tickets[-1],
        closeout_terminal_event=terminals["BR-CLOSEOUT-001"],
    )
    completion = resolve_workflow_closeout_completion(
        tickets=tickets,
        nodes=nodes,
        has_open_approval=False,
        has_open_incident=False,
        created_specs_by_ticket=created_specs,
        ticket_terminal_events_by_ticket=terminals,
    )

    assert issue is not None
    assert issue["reason_code"] == "delivery_check_failed"
    assert issue["ticket_id"] == "BR-CHECK-001"
    assert completion is None


def test_runtime_liveness_ignores_workflow_level_core_hire_board_review_blocker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("BOARDROOM_OS_DB_PATH", str(tmp_path / "boardroom_os.db"))

    with TestClient(create_app()) as client:
        workflow_id = "wf_core_hire_runtime_liveness"
        _ensure_scoped_workflow(
            client,
            workflow_id=workflow_id,
            tenant_id="tenant_default",
            workspace_id="ws_default",
            goal="Workflow-level core hire approval should not break runtime liveness.",
        )

        repository = client.app.state.repository
        with repository.transaction() as connection:
            repository.insert_event(
                connection,
                event_type="BOARD_REVIEW_REQUIRED",
                actor_type="staffing-router",
                actor_id="staffing-router",
                workflow_id=workflow_id,
                idempotency_key=f"test-core-hire-board-review-required:{workflow_id}",
                causation_id=None,
                correlation_id=workflow_id,
                payload={
                    "approval_id": "apr_core_hire_runtime_liveness",
                    "review_pack_id": "brp_core_hire_runtime_liveness",
                    "review_type": "CORE_HIRE_APPROVAL",
                    "ticket_id": None,
                    "node_id": None,
                    "title": "Approve hire: emp_architect_governance",
                },
                occurred_at=datetime.fromisoformat("2026-04-20T22:11:58+08:00"),
            )

        report = build_runtime_liveness_report(repository, workflow_id)

        assert isinstance(report.findings, list)


def test_should_increment_stall_when_monitor_signature_is_unchanged_despite_background_writes() -> None:
    assert live_harness._should_increment_stall(
        previous_signature=("EXECUTING", "project_init", (), 0, 0, 14, 178),
        current_signature=("EXECUTING", "project_init", (), 0, 0, 14, 178),
        workflow={"status": "EXECUTING"},
        active_ticket_ids=[],
        open_incidents=[],
    ) is True


def test_should_not_increment_stall_when_monitor_signature_changes() -> None:
    assert live_harness._should_increment_stall(
        previous_signature=("EXECUTING", "project_init", (), 0, 0, 14, 178),
        current_signature=("EXECUTING", "plan", (), 0, 0, 15, 179),
        workflow={"status": "EXECUTING"},
        active_ticket_ids=[],
        open_incidents=[],
    ) is False


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
