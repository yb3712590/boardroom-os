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

DEFAULT_SCENARIO_SEED = 17
DEFAULT_MAX_TICKS = 180
DEFAULT_TIMEOUT_SEC = 7200
DEFAULT_LIVE_PROVIDER_TIMEOUT_SEC = 180
MAX_STALL_TICKS = 25
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


def write_audit_summary(paths: ScenarioPaths, *, report: dict[str, Any], snapshot: dict[str, Any]) -> Path:
    workflow = snapshot.get("workflow") or {}
    tickets = list(snapshot.get("tickets") or [])
    provider_candidate_chain = list(snapshot.get("provider_candidate_chain") or [])
    provider_attempt_log = list(snapshot.get("provider_attempt_log") or [])
    fallback_blocked = bool(snapshot.get("fallback_blocked"))
    final_failure_kind = snapshot.get("final_failure_kind")
    lines = [
        "# Audit Summary",
        f"- Workflow: `{workflow.get('workflow_id') or report.get('workflow_id') or 'unknown'}`",
        f"- Status: `{workflow.get('status') or ('COMPLETED' if report.get('success') else 'FAILED')}`",
        f"- Stage: `{workflow.get('current_stage') or 'unknown'}`",
        f"- Completion mode: `{report.get('completion_mode') or 'unknown'}`",
        f"- Candidate chain: `{(' -> '.join(provider_candidate_chain) if provider_candidate_chain else 'none')}`",
        f"- Fallback blocked: `{str(fallback_blocked).lower()}`",
        f"- Final failure kind: `{final_failure_kind or 'none'}`",
        "",
        "## Provider Attempts",
    ]
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
    paths.audit_summary_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return paths.audit_summary_path


def write_failure_snapshot(paths: ScenarioPaths, repository, workflow_id: str, *, label: str) -> Path:
    provider_snapshot = _latest_provider_runtime_snapshot(repository, workflow_id)
    snapshot = {
        "workflow": repository.get_workflow_projection(workflow_id),
        "open_approvals": [item for item in repository.list_open_approvals() if item["workflow_id"] == workflow_id],
        "open_incidents": [item for item in repository.list_open_incidents() if item["workflow_id"] == workflow_id],
        "tickets": workflow_ticket_rows(repository, workflow_id)[-20:],
        "ceo_shadow_runs": repository.list_ceo_shadow_runs(workflow_id, limit=10),
        "orchestration_trace": recent_orchestration_trace(repository),
        **provider_snapshot,
    }
    target_path = paths.failure_snapshot_root / f"{label}.json"
    _write_json(target_path, snapshot)
    write_audit_summary(
        paths,
        report={
            "success": False,
            "workflow_id": workflow_id,
            "completion_mode": label,
        },
        snapshot=snapshot,
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
                    _write_json(paths.run_report_path, report)
                    write_audit_summary(
                        paths,
                        report=report,
                        snapshot={
                            "workflow": common["workflow"],
                            "tickets": common["tickets"][-20:],
                            **_latest_provider_runtime_snapshot(repository, workflow_id),
                        },
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
                        _write_json(paths.run_report_path, report)
                        write_audit_summary(
                            paths,
                            report=report,
                            snapshot={
                                "workflow": snapshot["workflow"],
                                "tickets": snapshot["tickets"][-20:],
                                **_latest_provider_runtime_snapshot(repository, workflow_id),
                            },
                        )
                        return report

                if time.monotonic() - started_at > timeout_sec:
                    snapshot_path = write_failure_snapshot(paths, repository, workflow_id, label="timeout")
                    raise RuntimeError(f"Scenario timed out. Snapshot: {snapshot_path}")

                if consecutive_stalls >= MAX_STALL_TICKS:
                    snapshot_path = write_failure_snapshot(paths, repository, workflow_id, label="stall")
                    raise RuntimeError(f"Scenario stalled for {consecutive_stalls} ticks. Snapshot: {snapshot_path}")

                time.sleep(1.05)

            snapshot_path = write_failure_snapshot(paths, repository, workflow_id, label="max_ticks")
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
