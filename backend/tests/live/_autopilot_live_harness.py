from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from fastapi.testclient import TestClient

BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.main import create_app
from app.scheduler_runner import run_scheduler_once
from app.core.time import now_local

DEFAULT_SCENARIO_SEED = 17
DEFAULT_MAX_TICKS = 180
DEFAULT_TIMEOUT_SEC = 7200
DEFAULT_LIVE_PROVIDER_TIMEOUT_SEC = 180
MAX_STALL_TICKS = 25
TERMINAL_TICKET_STATUSES = {"COMPLETED", "FAILED", "TIMED_OUT", "CANCELLED"}
GOVERNANCE_DOCUMENT_SCHEMA_REFS = {
    "architecture_brief",
    "technology_decision",
    "milestone_plan",
    "detailed_design",
    "backlog_recommendation",
}
APPROVED_ARCHITECT_GOVERNANCE_SCHEMA_REFS = {
    "architecture_brief",
    "technology_decision",
    "detailed_design",
}


@dataclass(frozen=True)
class ScenarioPaths:
    root: Path
    db_path: Path
    runtime_provider_config_path: Path
    artifact_store_root: Path
    artifact_upload_root: Path
    developer_inspector_root: Path
    ticket_context_archive_root: Path
    run_report_path: Path
    audit_summary_path: Path
    integration_monitor_report_path: Path
    failure_snapshot_root: Path


@dataclass(frozen=True)
class LiveScenarioDefinition:
    slug: str
    description: str
    goal: str
    constraints: list[str]
    assert_outcome: Callable[[ScenarioPaths, Any, str, dict[str, Any]], dict[str, Any]]
    checkpoint_assertion: Callable[[ScenarioPaths | None, Any, str, dict[str, Any]], dict[str, Any] | None] | None = None
    checkpoint_label: str | None = None
    force_requirement_elicitation: bool = False
    budget_cap: int = 1_500_000
    workflow_profile: str = "CEO_AUTOPILOT_FINE_GRAINED"


def build_scenario_paths(slug: str, scenario_root: Path | None = None) -> ScenarioPaths:
    root = Path(scenario_root) if scenario_root is not None else (BACKEND_ROOT / "data" / "scenarios" / slug)
    return ScenarioPaths(
        root=root,
        db_path=root / "boardroom_os.db",
        runtime_provider_config_path=root / "runtime-provider-config.json",
        artifact_store_root=root / "artifacts",
        artifact_upload_root=root / "artifact_uploads",
        developer_inspector_root=root / "developer_inspector",
        ticket_context_archive_root=root / "ticket_context_archives",
        run_report_path=root / "run_report.json",
        audit_summary_path=root / "audit-summary.md",
        integration_monitor_report_path=root / "integration-monitor-report.md",
        failure_snapshot_root=root / "failure_snapshots",
    )


def integration_test_provider_template_path() -> Path:
    return BACKEND_ROOT / "data" / "integration-test-provider-config.json"


def reset_scenario_root(paths: ScenarioPaths, *, clean: bool) -> None:
    if clean and paths.root.exists():
        shutil.rmtree(paths.root)
    paths.root.mkdir(parents=True, exist_ok=True)
    paths.artifact_store_root.mkdir(parents=True, exist_ok=True)
    paths.artifact_upload_root.mkdir(parents=True, exist_ok=True)
    paths.developer_inspector_root.mkdir(parents=True, exist_ok=True)
    paths.ticket_context_archive_root.mkdir(parents=True, exist_ok=True)
    paths.failure_snapshot_root.mkdir(parents=True, exist_ok=True)


@contextmanager
def scenario_environment(
    paths: ScenarioPaths,
    *,
    base_url: str,
    api_key: str,
    seed: int,
) -> Any:
    overrides = {
        "BOARDROOM_OS_DB_PATH": str(paths.db_path),
        "BOARDROOM_OS_RUNTIME_PROVIDER_CONFIG_PATH": str(paths.runtime_provider_config_path),
        "BOARDROOM_OS_ARTIFACT_STORE_ROOT": str(paths.artifact_store_root),
        "BOARDROOM_OS_ARTIFACT_UPLOAD_STAGING_ROOT": str(paths.artifact_upload_root),
        "BOARDROOM_OS_DEVELOPER_INSPECTOR_ROOT": str(paths.developer_inspector_root),
        "BOARDROOM_OS_TICKET_CONTEXT_ARCHIVE_ROOT": str(paths.ticket_context_archive_root),
        "BOARDROOM_OS_RUNTIME_EXECUTION_MODE": "INPROCESS",
        "BOARDROOM_OS_CEO_MAINTENANCE_INTERVAL_SEC": "1",
        "BOARDROOM_OS_PROVIDER_OPENAI_COMPAT_BASE_URL": base_url,
        "BOARDROOM_OS_PROVIDER_OPENAI_COMPAT_API_KEY": api_key,
        "BOARDROOM_OS_PROVIDER_OPENAI_COMPAT_MODEL": "gpt-5.4",
        "BOARDROOM_OS_PROVIDER_OPENAI_COMPAT_REASONING_EFFORT": "high",
        "BOARDROOM_OS_PROVIDER_OPENAI_COMPAT_TIMEOUT_SEC": str(DEFAULT_LIVE_PROVIDER_TIMEOUT_SEC),
        "BOARDROOM_OS_CEO_STAFFING_VARIANT_SEED": str(seed),
    }
    previous = {key: os.environ.get(key) for key in overrides}
    try:
        os.environ.update(overrides)
        yield
    finally:
        for key, previous_value in previous.items():
            if previous_value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = previous_value


def require_live_provider_credentials() -> tuple[str, str]:
    base_url = str(os.environ.get("BOARDROOM_OS_PROVIDER_OPENAI_COMPAT_BASE_URL") or "").strip()
    api_key = str(os.environ.get("BOARDROOM_OS_PROVIDER_OPENAI_COMPAT_API_KEY") or "").strip()
    if not base_url or not api_key:
        raise RuntimeError(
            "Live scenario requires BOARDROOM_OS_PROVIDER_OPENAI_COMPAT_BASE_URL and "
            "BOARDROOM_OS_PROVIDER_OPENAI_COMPAT_API_KEY."
        )
    return base_url, api_key


def load_integration_test_provider_payload(
    *,
    scenario_slug: str,
    config_path: Path | None = None,
) -> dict[str, Any]:
    env_override = str(os.environ.get("BOARDROOM_OS_INTEGRATION_TEST_PROVIDER_CONFIG_PATH") or "").strip()
    resolved_path = Path(config_path or env_override or integration_test_provider_template_path())
    if not resolved_path.exists():
        raise RuntimeError(
            "Integration test provider config is missing. "
            f"Expected: {resolved_path}"
        )
    payload = json.loads(resolved_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError("Integration test provider config must be a JSON object.")
    for key in ("providers", "provider_model_entries", "role_bindings"):
        value = payload.get(key)
        if not isinstance(value, list) or not value:
            raise RuntimeError(f"Integration test provider config must define non-empty `{key}`.")
    normalized = json.loads(json.dumps(payload))
    normalized["idempotency_key"] = str(
        normalized.get("idempotency_key") or f"runtime-provider-upsert:{scenario_slug}"
    )
    return normalized


def runtime_provider_payload(base_url: str, api_key: str, *, scenario_slug: str) -> dict[str, Any]:
    role_targets = [
        "ceo_shadow",
        "role_profile:ui_designer_primary",
        "role_profile:frontend_engineer_primary",
        "role_profile:checker_primary",
        "role_profile:backend_engineer_primary",
        "role_profile:database_engineer_primary",
        "role_profile:platform_sre_primary",
        "role_profile:cto_primary",
    ]
    role_bindings = [
        {
            "target_ref": target_ref,
            "provider_model_entry_refs": ["prov_openai_compat::gpt-5.4"],
            "max_context_window_override": None,
            "reasoning_effort_override": "high",
        }
        for target_ref in role_targets
    ]
    role_bindings.append(
        {
            "target_ref": "role_profile:architect_primary",
            "provider_model_entry_refs": ["prov_openai_compat::gpt-5.4"],
            "max_context_window_override": None,
            "reasoning_effort_override": "xhigh",
        }
    )
    return {
        "providers": [
            {
                "provider_id": "prov_openai_compat",
                "type": "openai_responses_stream",
                "enabled": True,
                "base_url": base_url,
                "api_key": api_key,
                "alias": scenario_slug,
                "preferred_model": "gpt-5.4",
                "max_context_window": None,
                "reasoning_effort": "high",
            }
        ],
        "provider_model_entries": [
            {
                "provider_id": "prov_openai_compat",
                "model_name": "gpt-5.4",
            }
        ],
        "role_bindings": role_bindings,
        "idempotency_key": f"runtime-provider-upsert:{scenario_slug}",
    }


def build_project_init_payload(scenario: LiveScenarioDefinition) -> dict[str, Any]:
    return {
        "north_star_goal": scenario.goal,
        "hard_constraints": list(scenario.constraints),
        "budget_cap": scenario.budget_cap,
        "deadline_at": None,
        "workflow_profile": scenario.workflow_profile,
        "force_requirement_elicitation": scenario.force_requirement_elicitation,
    }


def _parse_assumptions(assumptions: list[str] | None) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for item in assumptions or []:
        if "=" not in str(item):
            continue
        key, value = str(item).split("=", 1)
        parsed[key] = value
    return parsed


def workflow_ticket_rows(repository, workflow_id: str) -> list[dict[str, Any]]:
    with repository.connection() as connection:
        rows = connection.execute(
            """
            SELECT * FROM ticket_projection
            WHERE workflow_id = ?
            ORDER BY updated_at ASC, ticket_id ASC
            """,
            (workflow_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def workflow_created_specs(repository, workflow_id: str) -> dict[str, dict[str, Any]]:
    with repository.connection() as connection:
        ticket_ids = [
            str(row["ticket_id"])
            for row in connection.execute(
                "SELECT ticket_id FROM ticket_projection WHERE workflow_id = ?",
                (workflow_id,),
            ).fetchall()
        ]
        return {
            ticket_id: (repository.get_latest_ticket_created_payload(connection, ticket_id) or {})
            for ticket_id in ticket_ids
        }


def workflow_terminal_events(repository, workflow_id: str) -> dict[str, dict[str, Any] | None]:
    with repository.connection() as connection:
        ticket_ids = [
            str(row["ticket_id"])
            for row in connection.execute(
                "SELECT ticket_id FROM ticket_projection WHERE workflow_id = ?",
                (workflow_id,),
            ).fetchall()
        ]
        return {
            ticket_id: repository.get_latest_ticket_terminal_event(connection, ticket_id)
            for ticket_id in ticket_ids
        }


def workflow_approvals(repository, workflow_id: str) -> list[dict[str, Any]]:
    with repository.connection() as connection:
        rows = connection.execute(
            """
            SELECT * FROM approval_projection
            WHERE workflow_id = ?
            ORDER BY created_at ASC, approval_id ASC
            """,
            (workflow_id,),
        ).fetchall()
    return [repository._convert_approval_row(row) for row in rows]


def compiled_ticket_ids(repository, workflow_id: str) -> list[str]:
    with repository.connection() as connection:
        rows = connection.execute(
            """
            SELECT DISTINCT ticket_id
            FROM compiled_execution_package
            WHERE workflow_id = ?
            ORDER BY ticket_id ASC
            """,
            (workflow_id,),
        ).fetchall()
    return [str(row["ticket_id"]) for row in rows]


def _source_delivery_ticket_ids(created_specs: dict[str, dict[str, Any]]) -> list[str]:
    return [
        ticket_id
        for ticket_id, created_spec in created_specs.items()
        if str(created_spec.get("output_schema_ref") or "") == "source_code_delivery"
    ]


def _assert_source_delivery_payload_quality(
    created_specs: dict[str, dict[str, Any]],
    terminals: dict[str, dict[str, Any] | None],
) -> list[str]:
    source_delivery_ticket_ids = _source_delivery_ticket_ids(created_specs)
    for ticket_id in source_delivery_ticket_ids:
        terminal_event = terminals.get(ticket_id) or {}
        payload = terminal_event.get("payload") or {}
        if not isinstance(payload, dict):
            raise AssertionError(f"{ticket_id} is missing source delivery payload.")
        source_files = list(payload.get("source_files") or [])
        verification_runs = list(payload.get("verification_runs") or [])
        if not source_files:
            raise AssertionError(f"{ticket_id} is missing source_files in terminal payload.")
        if not verification_runs:
            raise AssertionError(f"{ticket_id} is missing verification_runs in terminal payload.")
        for run in verification_runs:
            if not isinstance(run, dict):
                raise AssertionError(f"{ticket_id} contains invalid verification_runs payload.")
            if not str(run.get("stdout") or "").strip():
                raise AssertionError(f"{ticket_id} is missing raw verification stdout.")
    return source_delivery_ticket_ids


def _assert_unique_source_delivery_evidence_paths(artifact_rows: list[dict[str, Any]]) -> None:
    seen_paths: dict[str, str] = {}
    duplicates: list[tuple[str, str, str]] = []
    for row in artifact_rows:
        logical_path = str(row.get("logical_path") or "").strip()
        ticket_id = str(row.get("ticket_id") or "").strip() or "unknown"
        if not logical_path.startswith(("20-evidence/tests/", "20-evidence/git/")):
            continue
        previous_ticket_id = seen_paths.get(logical_path)
        if previous_ticket_id is not None and previous_ticket_id != ticket_id:
            duplicates.append((logical_path, previous_ticket_id, ticket_id))
            continue
        seen_paths[logical_path] = ticket_id
    if duplicates:
        duplicate_lines = ", ".join(
            f"{logical_path} ({first_ticket_id}, {second_ticket_id})"
            for logical_path, first_ticket_id, second_ticket_id in duplicates
        )
        raise AssertionError(f"Found duplicate source delivery evidence paths: {duplicate_lines}")


def _workflow_artifact_rows(repository, workflow_id: str) -> list[dict[str, Any]]:
    with repository.connection() as connection:
        rows = connection.execute(
            """
            SELECT ticket_id, logical_path
            FROM artifact_index
            WHERE workflow_id = ?
            ORDER BY created_at ASC, artifact_ref ASC
            """,
            (workflow_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def recent_orchestration_trace(repository, *, limit: int = 5) -> list[dict[str, Any]]:
    with repository.connection() as connection:
        rows = connection.execute(
            """
            SELECT payload_json
            FROM events
            WHERE event_type = ?
            ORDER BY sequence_no DESC
            LIMIT ?
            """,
            ("SCHEDULER_ORCHESTRATION_RECORDED", limit),
        ).fetchall()
    return [json.loads(row["payload_json"]) for row in rows]


def build_runtime_ticket_audit(repository, workflow_id: str) -> list[dict[str, Any]]:
    audits: list[dict[str, Any]] = []
    created_specs = workflow_created_specs(repository, workflow_id)
    terminals = workflow_terminal_events(repository, workflow_id)
    for ticket in workflow_ticket_rows(repository, workflow_id):
        ticket_id = str(ticket["ticket_id"])
        created_spec = created_specs.get(ticket_id) or {}
        terminal_event = terminals.get(ticket_id) or {}
        assumptions = _parse_assumptions((terminal_event.get("payload") or {}).get("assumptions") or [])
        if not assumptions:
            continue
        audits.append(
            {
                "ticket_id": ticket_id,
                "node_id": str(ticket.get("node_id") or ""),
                "role_profile_ref": str(created_spec.get("role_profile_ref") or ""),
                "output_schema_ref": str(created_spec.get("output_schema_ref") or ""),
                "delivery_stage": str(created_spec.get("delivery_stage") or ""),
                "assumptions": assumptions,
            }
        )
    return audits


def approved_architect_governance_ticket_ids(repository, workflow_id: str) -> list[str]:
    approved_ticket_ids: list[str] = []
    seen_ticket_ids: set[str] = set()
    created_specs = workflow_created_specs(repository, workflow_id)
    terminals = workflow_terminal_events(repository, workflow_id)
    for ticket in workflow_ticket_rows(repository, workflow_id):
        ticket_id = str(ticket["ticket_id"])
        created_spec = created_specs.get(ticket_id) or {}
        if str(created_spec.get("output_schema_ref") or "") != "maker_checker_verdict":
            continue
        maker_checker_context = created_spec.get("maker_checker_context") or {}
        maker_ticket_id = str(maker_checker_context.get("maker_ticket_id") or "").strip()
        maker_ticket_spec = maker_checker_context.get("maker_ticket_spec")
        if not isinstance(maker_ticket_spec, dict) or not maker_ticket_spec:
            maker_ticket_spec = created_specs.get(maker_ticket_id) or {}
        if str(maker_ticket_spec.get("role_profile_ref") or "").strip() != "architect_primary":
            continue
        if str(maker_ticket_spec.get("output_schema_ref") or "").strip() not in APPROVED_ARCHITECT_GOVERNANCE_SCHEMA_REFS:
            continue
        completion_payload = (terminals.get(ticket_id) or {}).get("payload") or {}
        review_status = str(
            completion_payload.get("maker_checker_summary", {}).get("review_status")
            or completion_payload.get("review_status")
            or ""
        ).strip()
        if review_status not in {"APPROVED", "APPROVED_WITH_NOTES"}:
            continue
        approved_ticket_ref = maker_ticket_id or ticket_id
        if approved_ticket_ref in seen_ticket_ids:
            continue
        seen_ticket_ids.add(approved_ticket_ref)
        approved_ticket_ids.append(approved_ticket_ref)
    return approved_ticket_ids


def artifact_exists(repository, artifact_ref: str) -> bool:
    return repository.get_artifact_by_ref(artifact_ref) is not None


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )


def _build_success_report(
    *,
    workflow_id: str,
    scenario_root: str,
    seed: int,
    ticks_used: int,
    elapsed_sec: float,
    base_report: dict[str, Any],
    assertions: dict[str, Any],
    completion_mode: str,
    checkpoint_label: str | None = None,
) -> dict[str, Any]:
    report = {
        "success": True,
        "workflow_id": workflow_id,
        "scenario_root": scenario_root,
        "seed": seed,
        "ticks_used": ticks_used,
        "elapsed_sec": elapsed_sec,
        "completion_mode": completion_mode,
        "assertions": {
            **base_report,
            **assertions,
        },
    }
    if checkpoint_label is not None:
        report["checkpoint_label"] = checkpoint_label
    return report


def _latest_provider_runtime_snapshot(repository, workflow_id: str) -> dict[str, Any]:
    terminals = workflow_terminal_events(repository, workflow_id)
    for ticket in reversed(workflow_ticket_rows(repository, workflow_id)):
        terminal_event = terminals.get(str(ticket["ticket_id"]))
        if not terminal_event:
            continue
        payload = terminal_event.get("payload") or {}
        failure_detail = payload.get("failure_detail") or {}
        assumptions = _parse_assumptions(payload.get("assumptions") or [])
        provider_candidate_chain = list(failure_detail.get("provider_candidate_chain") or [])
        provider_attempt_log = list(failure_detail.get("provider_attempt_log") or [])
        provider_signals_present = bool(
            provider_candidate_chain
            or provider_attempt_log
            or assumptions.get("actual_provider_id")
            or assumptions.get("provider_failover_to")
        )
        if not provider_signals_present:
            continue
        return {
            "provider_candidate_chain": provider_candidate_chain,
            "provider_attempt_log": provider_attempt_log,
            "fallback_blocked": bool(failure_detail.get("fallback_blocked")),
            "final_failure_kind": payload.get("failure_kind"),
            "preferred_provider_id": assumptions.get("preferred_provider_id"),
            "actual_provider_id": assumptions.get("actual_provider_id"),
            "actual_model": assumptions.get("actual_model"),
            "provider_failover_to": assumptions.get("provider_failover_to"),
        }
    return {
        "provider_candidate_chain": [],
        "provider_attempt_log": [],
        "fallback_blocked": False,
        "final_failure_kind": None,
        "preferred_provider_id": None,
        "actual_provider_id": None,
        "actual_model": None,
        "provider_failover_to": None,
    }


def _workflow_event_count(repository, workflow_id: str) -> int:
    with repository.connection() as connection:
        row = connection.execute(
            """
            SELECT COUNT(*) AS total
            FROM events
            WHERE workflow_id = ?
            """,
            (workflow_id,),
        ).fetchone()
    return int(row["total"] or 0)


def _workflow_incidents(repository, workflow_id: str) -> list[dict[str, Any]]:
    with repository.connection() as connection:
        rows = connection.execute(
            """
            SELECT * FROM incident_projection
            WHERE workflow_id = ?
            ORDER BY opened_at ASC, incident_id ASC
            """,
            (workflow_id,),
        ).fetchall()
    return [repository._convert_incident_projection_row(row) for row in rows]


def _active_ticket_ids(tickets: list[dict[str, Any]]) -> list[str]:
    return [
        str(ticket.get("ticket_id") or "")
        for ticket in tickets
        if str(ticket.get("status") or "").upper() not in TERMINAL_TICKET_STATUSES
        and str(ticket.get("ticket_id") or "").strip()
    ]


def _ticket_summary(tickets: list[dict[str, Any]]) -> dict[str, Any]:
    completed = 0
    failed = 0
    for ticket in tickets:
        status = str(ticket.get("status") or "").upper()
        if status == "COMPLETED":
            completed += 1
        elif status in {"FAILED", "TIMED_OUT", "CANCELLED"}:
            failed += 1
    total = len(tickets)
    active_ticket_ids = _active_ticket_ids(tickets)
    pending = max(total - completed - failed, 0)
    return {
        "total": total,
        "completed": completed,
        "failed": failed,
        "pending": pending,
        "active_ticket_ids": active_ticket_ids,
    }


def _governance_documents(repository, workflow_id: str) -> list[dict[str, Any]]:
    documents: list[dict[str, Any]] = []
    created_specs = workflow_created_specs(repository, workflow_id)
    terminals = workflow_terminal_events(repository, workflow_id)
    for ticket in workflow_ticket_rows(repository, workflow_id):
        ticket_id = str(ticket.get("ticket_id") or "").strip()
        if not ticket_id:
            continue
        created_spec = created_specs.get(ticket_id) or {}
        output_schema_ref = str(created_spec.get("output_schema_ref") or "").strip()
        if output_schema_ref not in GOVERNANCE_DOCUMENT_SCHEMA_REFS:
            continue
        payload = (terminals.get(ticket_id) or {}).get("payload") or {}
        summary = (
            str(payload.get("summary") or "").strip()
            or str(payload.get("title") or "").strip()
            or f"{output_schema_ref} for {ticket_id}"
        )
        documents.append(
            {
                "ticket_id": ticket_id,
                "document_kind_ref": output_schema_ref,
                "status": str(ticket.get("status") or "UNKNOWN"),
                "summary": summary,
            }
        )
    return documents


def _artifact_summary(repository, workflow_id: str) -> dict[str, bool]:
    artifact_rows = _workflow_artifact_rows(repository, workflow_id)
    logical_paths = [str(row.get("logical_path") or "").strip() for row in artifact_rows]
    return {
        "has_project_code": any(
            path.startswith("10-project/src/") and not path.endswith(".gitkeep")
            for path in logical_paths
        ),
        "has_test_evidence": any(
            path.startswith("20-evidence/tests/") and not path.endswith(".gitkeep")
            for path in logical_paths
        ),
        "has_git_evidence": any(
            path.startswith("20-evidence/git/") and not path.endswith(".gitkeep")
            for path in logical_paths
        ),
    }


def _approval_summary(approvals: list[dict[str, Any]]) -> dict[str, int]:
    open_count = sum(1 for approval in approvals if str(approval.get("status") or "").upper() == "OPEN")
    return {
        "open_count": open_count,
        "resolved_count": max(len(approvals) - open_count, 0),
    }


def _incident_summary(incidents: list[dict[str, Any]]) -> dict[str, int]:
    open_count = sum(1 for incident in incidents if str(incident.get("status") or "").upper() == "OPEN")
    return {
        "open_count": open_count,
        "resolved_count": max(len(incidents) - open_count, 0),
    }


def _monitor_signature(snapshot: dict[str, Any]) -> tuple[Any, ...]:
    return (
        snapshot.get("workflow_status"),
        snapshot.get("stage"),
        tuple(snapshot.get("active_ticket_ids") or []),
        int(snapshot.get("approval_count") or 0),
        int(snapshot.get("incident_count") or 0),
        int(snapshot.get("ticket_count") or 0),
        int(snapshot.get("event_count") or 0),
    )


def _format_duration(duration_sec: int) -> str:
    if duration_sec < 60:
        return f"{duration_sec} 秒"
    minutes, seconds = divmod(duration_sec, 60)
    if minutes < 60:
        return f"{minutes} 分钟" if seconds == 0 else f"{minutes} 分 {seconds} 秒"
    hours, minutes = divmod(minutes, 60)
    return f"{hours} 小时 {minutes} 分钟" if minutes else f"{hours} 小时"


def _display_timestamp(value: str | None) -> str:
    if not value:
        return "unknown"
    return value.replace("T", " ")


def _collect_monitor_snapshot(repository, workflow_id: str, *, recorded_at: str) -> dict[str, Any]:
    workflow = repository.get_workflow_projection(workflow_id) or {}
    tickets = workflow_ticket_rows(repository, workflow_id)
    approvals = workflow_approvals(repository, workflow_id)
    incidents = _workflow_incidents(repository, workflow_id)
    return {
        "recorded_at": recorded_at,
        "workflow_id": workflow_id,
        "workflow_status": str(workflow.get("status") or "UNKNOWN"),
        "stage": str(workflow.get("current_stage") or "unknown"),
        "ticket_count": len(tickets),
        "event_count": _workflow_event_count(repository, workflow_id),
        "active_ticket_ids": _active_ticket_ids(tickets),
        "approval_count": len(approvals),
        "incident_count": len([item for item in incidents if str(item.get("status") or "").upper() == "OPEN"]),
    }


def _monitor_change_summary(previous: dict[str, Any] | None, current: dict[str, Any]) -> str:
    if previous is None:
        return "workflow 启动"
    if current.get("stage") != previous.get("stage"):
        return f"进入 {current.get('stage') or 'unknown'} 阶段"
    if current.get("workflow_status") != previous.get("workflow_status"):
        return f"状态变为 {current.get('workflow_status') or 'UNKNOWN'}"
    if current.get("active_ticket_ids") != previous.get("active_ticket_ids"):
        return "活跃 ticket 变化"
    if current.get("approval_count") != previous.get("approval_count"):
        return "approval 数量变化"
    if current.get("incident_count") != previous.get("incident_count"):
        return "incident 数量变化"
    return "ticket / event 计数变化"


def _update_monitor_entries(
    paths: ScenarioPaths,
    repository,
    workflow_id: str,
    *,
    state: dict[str, Any],
) -> dict[str, Any]:
    recorded_at = now_local().isoformat()
    snapshot = _collect_monitor_snapshot(repository, workflow_id, recorded_at=recorded_at)
    current_signature = _monitor_signature(snapshot)
    previous_snapshot = state.get("previous_snapshot")
    previous_signature = state.get("previous_signature")
    now_monotonic = time.monotonic()
    entries = state.setdefault("entries", [])

    if previous_signature is None:
        entries.append(
            {
                **snapshot,
                "change_type": "state_change",
                "summary": _monitor_change_summary(None, snapshot),
            }
        )
        state["last_change_monotonic"] = now_monotonic
        state["last_change_recorded_at"] = recorded_at
        write_integration_monitor_report(paths, entries=entries)
    elif current_signature != previous_signature:
        silence_sec = int(max(0, now_monotonic - float(state.get("last_change_monotonic") or now_monotonic)))
        if silence_sec >= 60:
            silence_entry = {
                **snapshot,
                "change_type": "silence_recovered",
                "summary": f"静默 {_format_duration(silence_sec)}后恢复",
                "silent_for_sec": silence_sec,
            }
            entries.append(silence_entry)
            longest = state.get("longest_silence")
            if longest is None or silence_sec > int(longest.get("duration_sec") or 0):
                state["longest_silence"] = {
                    "start_at": state.get("last_change_recorded_at"),
                    "end_at": recorded_at,
                    "duration_sec": silence_sec,
                }
        entries.append(
            {
                **snapshot,
                "change_type": "state_change",
                "summary": _monitor_change_summary(previous_snapshot, snapshot),
            }
        )
        state["last_change_monotonic"] = now_monotonic
        state["last_change_recorded_at"] = recorded_at
        write_integration_monitor_report(paths, entries=entries)

    state["previous_snapshot"] = snapshot
    state["previous_signature"] = current_signature
    return state


def _effective_longest_silence(state: dict[str, Any]) -> dict[str, Any] | None:
    longest = state.get("longest_silence")
    last_change_monotonic = state.get("last_change_monotonic")
    last_change_recorded_at = state.get("last_change_recorded_at")
    if last_change_monotonic is None or last_change_recorded_at is None:
        return longest
    current_duration_sec = int(max(0, time.monotonic() - float(last_change_monotonic)))
    if current_duration_sec < 60:
        return longest
    current_silence = {
        "start_at": str(last_change_recorded_at),
        "end_at": now_local().isoformat(),
        "duration_sec": current_duration_sec,
    }
    if longest is None or current_duration_sec > int(longest.get("duration_sec") or 0):
        return current_silence
    return longest


def _provider_summary(
    provider_snapshot: dict[str, Any],
    *,
    provider_id: str | None,
    model_name: str | None,
    provider_base_url: str | None,
) -> dict[str, Any]:
    return {
        "actual_provider_id": provider_snapshot.get("actual_provider_id") or provider_id,
        "actual_model": provider_snapshot.get("actual_model") or model_name,
        "provider_base_url": provider_base_url,
    }


def _build_audit_snapshot(
    repository,
    workflow_id: str,
    *,
    monitor_state: dict[str, Any],
    provider_id: str | None,
    model_name: str | None,
    provider_base_url: str | None,
) -> dict[str, Any]:
    workflow = repository.get_workflow_projection(workflow_id) or {}
    tickets = workflow_ticket_rows(repository, workflow_id)
    approvals = workflow_approvals(repository, workflow_id)
    incidents = _workflow_incidents(repository, workflow_id)
    provider_snapshot = _latest_provider_runtime_snapshot(repository, workflow_id)
    return {
        "workflow": workflow,
        "tickets": tickets[-20:],
        "timeline": [
            {
                "entered_at": item.get("recorded_at"),
                "stage": item.get("stage"),
                "workflow_status": item.get("workflow_status"),
                "summary": item.get("summary"),
            }
            for item in list(monitor_state.get("entries") or [])
            if item.get("change_type") == "state_change"
        ],
        "ticket_summary": _ticket_summary(tickets),
        "governance_documents": _governance_documents(repository, workflow_id),
        "artifact_summary": _artifact_summary(repository, workflow_id),
        "approval_summary": _approval_summary(approvals),
        "incident_summary": _incident_summary(incidents),
        "longest_silence": _effective_longest_silence(monitor_state),
        "provider_summary": _provider_summary(
            provider_snapshot,
            provider_id=provider_id,
            model_name=model_name,
            provider_base_url=provider_base_url,
        ),
        **provider_snapshot,
    }


def write_integration_monitor_report(paths: ScenarioPaths, *, entries: list[dict[str, Any]]) -> Path:
    lines = [
        "# Integration Monitor Report",
    ]
    if not entries:
        lines.extend(["", "- 暂无记录"])
    for entry in entries:
        lines.extend(
            [
                "",
                f"### {_display_timestamp(str(entry.get('recorded_at') or ''))} {entry.get('summary') or '状态变化'}",
                f"- workflow: `{entry.get('workflow_status') or 'UNKNOWN'}` / `{entry.get('stage') or 'unknown'}`",
                f"- tickets: `{entry.get('ticket_count') or 0}`, events: `{entry.get('event_count') or 0}`",
                f"- active tickets: `{', '.join(entry.get('active_ticket_ids') or []) or 'none'}`",
                f"- approvals: `{entry.get('approval_count') or 0}`, incidents: `{entry.get('incident_count') or 0}`",
            ]
        )
        if entry.get("change_type") == "silence_recovered":
            lines.append(f"- silent for: `{_format_duration(int(entry.get('silent_for_sec') or 0))}`")
    paths.integration_monitor_report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return paths.integration_monitor_report_path


def write_audit_summary(paths: ScenarioPaths, *, report: dict[str, Any], snapshot: dict[str, Any]) -> Path:
    workflow = snapshot.get("workflow") or {}
    tickets = list(snapshot.get("tickets") or [])
    timeline = list(snapshot.get("timeline") or [])
    ticket_summary = dict(snapshot.get("ticket_summary") or {})
    governance_documents = list(snapshot.get("governance_documents") or [])
    artifact_summary = dict(snapshot.get("artifact_summary") or {})
    approval_summary = dict(snapshot.get("approval_summary") or {})
    incident_summary = dict(snapshot.get("incident_summary") or {})
    longest_silence = snapshot.get("longest_silence") or {}
    provider_summary = dict(snapshot.get("provider_summary") or {})
    provider_candidate_chain = list(snapshot.get("provider_candidate_chain") or [])
    provider_attempt_log = list(snapshot.get("provider_attempt_log") or [])
    fallback_blocked = bool(snapshot.get("fallback_blocked"))
    final_failure_kind = snapshot.get("final_failure_kind")
    lines = [
        "# Audit Summary",
        f"- Scenario: `{report.get('scenario_slug') or 'unknown'}`",
        f"- Time Range: `{_display_timestamp(str(report.get('started_at') or ''))} -> {_display_timestamp(str(report.get('finished_at') or ''))}`",
        f"- Elapsed: `{_format_duration(int(float(report.get('elapsed_sec') or 0)))} `",
        f"- Workflow: `{workflow.get('workflow_id') or report.get('workflow_id') or 'unknown'}`",
        f"- Status: `{workflow.get('status') or ('COMPLETED' if report.get('success') else 'FAILED')}`",
        f"- Stage: `{workflow.get('current_stage') or 'unknown'}`",
        f"- Completion mode: `{report.get('completion_mode') or 'unknown'}`",
        f"- Provider: `{provider_summary.get('actual_provider_id') or 'unknown'}` / `{provider_summary.get('actual_model') or 'unknown'}`",
        f"- Provider Base URL: `{provider_summary.get('provider_base_url') or 'unknown'}`",
        f"- Candidate chain: `{(' -> '.join(provider_candidate_chain) if provider_candidate_chain else 'none')}`",
        f"- Fallback blocked: `{str(fallback_blocked).lower()}`",
        f"- Final failure kind: `{final_failure_kind or 'none'}`",
        "",
        "## Workflow Progress",
    ]
    if timeline:
        for item in timeline:
            lines.append(
                "- "
                f"`{_display_timestamp(str(item.get('entered_at') or ''))}` "
                f"`{item.get('workflow_status') or 'UNKNOWN'}` "
                f"`{item.get('stage') or 'unknown'}` "
                f"{item.get('summary') or ''}".rstrip()
            )
    else:
        lines.append("- `none`")
    lines.extend(
        [
            "",
            "## Ticket Summary",
            f"- Total: `{ticket_summary.get('total') or 0}`",
            f"- Completed: `{ticket_summary.get('completed') or 0}`",
            f"- Failed: `{ticket_summary.get('failed') or 0}`",
            f"- Pending: `{ticket_summary.get('pending') or 0}`",
            f"- Active Tickets: `{', '.join(ticket_summary.get('active_ticket_ids') or []) or 'none'}`",
            "",
            "## Governance Output Chain",
        ]
    )
    if governance_documents:
        for item in governance_documents:
            lines.append(
                "- "
                f"`{item.get('ticket_id')}` "
                f"`{item.get('document_kind_ref')}` "
                f"`{item.get('status')}` "
                f"{item.get('summary') or ''}".rstrip()
            )
    else:
        lines.append("- `none`")
    lines.extend(
        [
            "",
            "## Code And Evidence",
            f"- Project code written: `{'yes' if artifact_summary.get('has_project_code') else 'no'}`",
            f"- Test evidence written: `{'yes' if artifact_summary.get('has_test_evidence') else 'no'}`",
            f"- Git evidence written: `{'yes' if artifact_summary.get('has_git_evidence') else 'no'}`",
            "",
            "## Incidents And Approvals",
            f"- Open approvals: `{approval_summary.get('open_count') or 0}`",
            f"- Resolved approvals: `{approval_summary.get('resolved_count') or 0}`",
            f"- Open incidents: `{incident_summary.get('open_count') or 0}`",
            f"- Resolved incidents: `{incident_summary.get('resolved_count') or 0}`",
            "",
            "## Provider Attempts",
        ]
    )
    if provider_attempt_log:
        for item in provider_attempt_log:
            lines.append(
                "- "
                f"`{item.get('provider_id')}` "
                f"attempt `{item.get('attempt_no') or item.get('attempt_count') or 0}` "
                f"status `{item.get('status') or 'UNKNOWN'}` "
                f"failure `{item.get('failure_kind') or 'none'}`"
            )
    else:
        lines.append("- `none`")
    lines.extend(
        [
            "",
            "## Recent Tickets",
        ]
    )
    for ticket in tickets[:5]:
        lines.append(
            "- "
            f"`{ticket.get('ticket_id')}` "
            f"`{ticket.get('status') or 'UNKNOWN'}` "
            f"`{ticket.get('node_id') or 'unknown-node'}`"
        )
    lines.extend(
        [
            "",
            "## Longest Silence",
        ]
    )
    if longest_silence:
        lines.append(
            "- "
            f"`{_display_timestamp(str(longest_silence.get('start_at') or ''))}` -> "
            f"`{_display_timestamp(str(longest_silence.get('end_at') or ''))}` "
            f"({ _format_duration(int(longest_silence.get('duration_sec') or 0)) })"
        )
    else:
        lines.append("- `none`")
    paths.audit_summary_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return paths.audit_summary_path


def write_failure_snapshot(
    paths: ScenarioPaths,
    repository,
    workflow_id: str,
    *,
    label: str,
    monitor_state: dict[str, Any],
    provider_id: str | None,
    model_name: str | None,
    provider_base_url: str | None,
) -> Path:
    snapshot = {
        **_build_audit_snapshot(
            repository,
            workflow_id,
            monitor_state=monitor_state,
            provider_id=provider_id,
            model_name=model_name,
            provider_base_url=provider_base_url,
        ),
        "open_approvals": [item for item in repository.list_open_approvals() if item["workflow_id"] == workflow_id],
        "open_incidents": [item for item in repository.list_open_incidents() if item["workflow_id"] == workflow_id],
        "ceo_shadow_runs": repository.list_ceo_shadow_runs(workflow_id, limit=10),
        "orchestration_trace": recent_orchestration_trace(repository),
    }
    target_path = paths.failure_snapshot_root / f"{label}.json"
    _write_json(target_path, snapshot)
    write_audit_summary(
        paths,
        report={
            "success": False,
            "scenario_slug": paths.root.name,
            "workflow_id": workflow_id,
            "completion_mode": label,
            "started_at": monitor_state.get("started_at"),
            "finished_at": now_local().isoformat(),
            "elapsed_sec": round(time.monotonic() - float(monitor_state.get("started_monotonic") or time.monotonic()), 2),
        },
        snapshot={**snapshot, "tickets": list(snapshot.get("tickets") or [])[-20:]},
    )
    return target_path


def collect_common_outcome(paths: ScenarioPaths, repository, workflow_id: str) -> dict[str, Any]:
    workflow = repository.get_workflow_projection(workflow_id)
    if workflow is None:
        raise AssertionError("Workflow projection is missing.")
    if workflow["status"] != "COMPLETED":
        raise AssertionError(f"Workflow did not complete. Current status: {workflow['status']}")
    if workflow["current_stage"] != "closeout":
        raise AssertionError(f"Workflow current_stage is {workflow['current_stage']}, expected closeout.")

    tickets = workflow_ticket_rows(repository, workflow_id)
    created_specs = workflow_created_specs(repository, workflow_id)
    terminals = workflow_terminal_events(repository, workflow_id)
    approvals = workflow_approvals(repository, workflow_id)
    audits = build_runtime_ticket_audit(repository, workflow_id)
    architect_ticket_ids = approved_architect_governance_ticket_ids(repository, workflow_id)
    compiled_ids = compiled_ticket_ids(repository, workflow_id)
    archived_ids = sorted(path.stem for path in paths.ticket_context_archive_root.glob("*.md"))
    source_delivery_ticket_ids = _assert_source_delivery_payload_quality(created_specs, terminals)

    if not artifact_exists(repository, f"art://workflow-chain/{workflow_id}/workflow-chain-report.json"):
        raise AssertionError("Workflow chain report artifact is missing.")
    if sorted(compiled_ids) != archived_ids:
        raise AssertionError(
            "Ticket context archives do not match compiled runtime tickets: "
            f"compiled={compiled_ids} archived={archived_ids}"
        )
    if not any(
        str((created_specs.get(str(ticket["ticket_id"])) or {}).get("output_schema_ref") or "") == "delivery_closeout_package"
        for ticket in tickets
    ):
        raise AssertionError("No delivery_closeout_package ticket was recorded.")
    _assert_unique_source_delivery_evidence_paths(
        [
            artifact
            for artifact in _workflow_artifact_rows(repository, workflow_id)
            if str(artifact.get("ticket_id") or "").strip() in set(source_delivery_ticket_ids)
        ]
    )

    employees = [
        employee
        for employee in repository.list_employee_projections(states=["ACTIVE"])
        if bool(employee.get("board_approved"))
    ]

    return {
        "workflow": workflow,
        "tickets": tickets,
        "created_specs": created_specs,
        "terminals": terminals,
        "approvals": approvals,
        "audits": audits,
        "architect_ticket_ids": architect_ticket_ids,
        "employees": employees,
        "source_delivery_ticket_ids": source_delivery_ticket_ids,
        "compiled_ticket_ids": compiled_ids,
        "archived_ticket_ids": archived_ids,
        "base_report": {
            "workflow_id": workflow_id,
            "workflow_status": workflow["status"],
            "workflow_stage": workflow["current_stage"],
            "ticket_count": len(tickets),
            "compiled_ticket_ids": compiled_ids,
            "archived_ticket_ids": archived_ids,
            "employee_ids": [str(employee["employee_id"]) for employee in employees],
        },
    }


def collect_progress_snapshot(paths: ScenarioPaths, repository, workflow_id: str) -> dict[str, Any]:
    workflow = repository.get_workflow_projection(workflow_id)
    if workflow is None:
        raise AssertionError("Workflow projection is missing.")

    tickets = workflow_ticket_rows(repository, workflow_id)
    created_specs = workflow_created_specs(repository, workflow_id)
    terminals = workflow_terminal_events(repository, workflow_id)
    approvals = workflow_approvals(repository, workflow_id)
    audits = build_runtime_ticket_audit(repository, workflow_id)
    architect_ticket_ids = approved_architect_governance_ticket_ids(repository, workflow_id)
    compiled_ids = compiled_ticket_ids(repository, workflow_id)
    archived_ids = sorted(path.stem for path in paths.ticket_context_archive_root.glob("*.md"))
    employees = [
        employee
        for employee in repository.list_employee_projections(states=["ACTIVE"])
        if bool(employee.get("board_approved"))
    ]

    return {
        "workflow": workflow,
        "tickets": tickets,
        "created_specs": created_specs,
        "terminals": terminals,
        "approvals": approvals,
        "audits": audits,
        "architect_ticket_ids": architect_ticket_ids,
        "employees": employees,
        "compiled_ticket_ids": compiled_ids,
        "archived_ticket_ids": archived_ids,
        "base_report": {
            "workflow_id": workflow_id,
            "workflow_status": workflow["status"],
            "workflow_stage": workflow["current_stage"],
            "ticket_count": len(tickets),
            "compiled_ticket_ids": compiled_ids,
            "archived_ticket_ids": archived_ids,
            "employee_ids": [str(employee["employee_id"]) for employee in employees],
        },
    }


def run_live_scenario(
    scenario: LiveScenarioDefinition,
    *,
    clean: bool = True,
    max_ticks: int = DEFAULT_MAX_TICKS,
    timeout_sec: int = DEFAULT_TIMEOUT_SEC,
    seed: int = DEFAULT_SCENARIO_SEED,
    scenario_root: Path | None = None,
) -> dict[str, Any]:
    paths = build_scenario_paths(scenario.slug, scenario_root)
    provider_payload = load_integration_test_provider_payload(scenario_slug=scenario.slug)
    first_provider = next(
        (
            item
            for item in list(provider_payload.get("providers") or [])
            if isinstance(item, dict) and str(item.get("base_url") or "").strip() and str(item.get("api_key") or "").strip()
        ),
        None,
    )
    if first_provider is None:
        raise RuntimeError("Integration test provider config must contain at least one provider with base_url and api_key.")
    base_url = str(first_provider.get("base_url") or "").strip()
    api_key = str(first_provider.get("api_key") or "").strip()
    reset_scenario_root(paths, clean=clean)

    started_at = time.monotonic()
    with scenario_environment(paths, base_url=base_url, api_key=api_key, seed=seed):
        with TestClient(create_app()) as client:
            runtime_response = client.post(
                "/api/v1/commands/runtime-provider-upsert",
                json=provider_payload,
            )
            if runtime_response.status_code != 200 or runtime_response.json()["status"] != "ACCEPTED":
                raise RuntimeError(f"runtime-provider-upsert failed: {runtime_response.text}")

            project_response = client.post(
                "/api/v1/commands/project-init",
                json=build_project_init_payload(scenario),
            )
            if project_response.status_code != 200 or project_response.json()["status"] != "ACCEPTED":
                raise RuntimeError(f"project-init failed: {project_response.text}")

            workflow_id = project_response.json()["causation_hint"].split(":", 1)[1]
            repository = client.app.state.repository
            _, previous_version = repository.get_cursor_and_version()
            consecutive_stalls = 0
            monitor_state: dict[str, Any] = {
                "entries": [],
                "started_at": now_local().isoformat(),
                "started_monotonic": time.monotonic(),
            }
            provider_id = str(first_provider.get("provider_id") or "").strip() or None
            model_name = str(first_provider.get("preferred_model") or "").strip() or None

            for tick_index in range(max_ticks):
                run_scheduler_once(
                    repository,
                    idempotency_key=f"live-scenario:{scenario.slug}:{workflow_id}:{tick_index}",
                    max_dispatches=20,
                    tick_index=tick_index,
                )
                workflow = repository.get_workflow_projection(workflow_id)
                _, current_version = repository.get_cursor_and_version()
                if current_version == previous_version:
                    consecutive_stalls += 1
                else:
                    consecutive_stalls = 0
                previous_version = current_version
                monitor_state = _update_monitor_entries(
                    paths,
                    repository,
                    workflow_id,
                    state=monitor_state,
                )

                if workflow is not None and workflow["status"] == "COMPLETED":
                    common = collect_common_outcome(paths, repository, workflow_id)
                    assertions = scenario.assert_outcome(paths, repository, workflow_id, common)
                    report = _build_success_report(
                        workflow_id=workflow_id,
                        scenario_root=str(paths.root),
                        seed=seed,
                        ticks_used=tick_index + 1,
                        elapsed_sec=round(time.monotonic() - started_at, 2),
                        base_report=common["base_report"],
                        assertions=assertions,
                        completion_mode="full",
                    )
                    report["scenario_slug"] = scenario.slug
                    report["started_at"] = monitor_state.get("started_at")
                    report["finished_at"] = now_local().isoformat()
                    _write_json(paths.run_report_path, report)
                    write_audit_summary(
                        paths,
                        report=report,
                        snapshot=_build_audit_snapshot(
                            repository,
                            workflow_id,
                            monitor_state=monitor_state,
                            provider_id=provider_id,
                            model_name=model_name,
                            provider_base_url=base_url,
                        ),
                    )
                    return report

                if scenario.checkpoint_assertion is not None:
                    snapshot = collect_progress_snapshot(paths, repository, workflow_id)
                    checkpoint_assertions = scenario.checkpoint_assertion(paths, repository, workflow_id, snapshot)
                    if checkpoint_assertions is not None:
                        report = _build_success_report(
                            workflow_id=workflow_id,
                            scenario_root=str(paths.root),
                            seed=seed,
                            ticks_used=tick_index + 1,
                            elapsed_sec=round(time.monotonic() - started_at, 2),
                            base_report=snapshot["base_report"],
                            assertions=checkpoint_assertions,
                            completion_mode="checkpoint_smoke",
                            checkpoint_label=scenario.checkpoint_label,
                        )
                        report["scenario_slug"] = scenario.slug
                        report["started_at"] = monitor_state.get("started_at")
                        report["finished_at"] = now_local().isoformat()
                        _write_json(paths.run_report_path, report)
                        write_audit_summary(
                            paths,
                            report=report,
                            snapshot=_build_audit_snapshot(
                                repository,
                                workflow_id,
                                monitor_state=monitor_state,
                                provider_id=provider_id,
                                model_name=model_name,
                                provider_base_url=base_url,
                            ),
                        )
                        return report

                if time.monotonic() - started_at > timeout_sec:
                    snapshot_path = write_failure_snapshot(
                        paths,
                        repository,
                        workflow_id,
                        label="timeout",
                        monitor_state=monitor_state,
                        provider_id=provider_id,
                        model_name=model_name,
                        provider_base_url=base_url,
                    )
                    raise RuntimeError(f"Scenario timed out. Snapshot: {snapshot_path}")

                if consecutive_stalls >= MAX_STALL_TICKS:
                    snapshot_path = write_failure_snapshot(
                        paths,
                        repository,
                        workflow_id,
                        label="stall",
                        monitor_state=monitor_state,
                        provider_id=provider_id,
                        model_name=model_name,
                        provider_base_url=base_url,
                    )
                    raise RuntimeError(f"Scenario stalled for {consecutive_stalls} ticks. Snapshot: {snapshot_path}")

                time.sleep(1.05)

            snapshot_path = write_failure_snapshot(
                paths,
                repository,
                workflow_id,
                label="max_ticks",
                monitor_state=monitor_state,
                provider_id=provider_id,
                model_name=model_name,
                provider_base_url=base_url,
            )
            raise RuntimeError(f"Scenario exceeded max_ticks={max_ticks}. Snapshot: {snapshot_path}")


def run_cli(
    scenario: LiveScenarioDefinition,
    argv: list[str] | None = None,
) -> int:
    parser = argparse.ArgumentParser(description=scenario.description)
    parser.add_argument("--clean", action="store_true", help="Delete and recreate the scenario directory first.")
    parser.add_argument("--max-ticks", type=int, default=DEFAULT_MAX_TICKS)
    parser.add_argument("--timeout-sec", type=int, default=DEFAULT_TIMEOUT_SEC)
    parser.add_argument("--seed", type=int, default=DEFAULT_SCENARIO_SEED)
    parser.add_argument("--scenario-root", type=Path, default=None)
    args = parser.parse_args(argv)

    report = run_live_scenario(
        scenario,
        clean=True,
        max_ticks=args.max_ticks,
        timeout_sec=args.timeout_sec,
        seed=args.seed,
        scenario_root=args.scenario_root,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0
