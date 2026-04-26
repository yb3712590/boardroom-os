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
from app.core.execution_targets import resolve_execution_target_ref_from_ticket_spec
from app.core.runtime_provider_config import resolve_provider_selection, resolve_runtime_provider_config
from app.core.time import now_local
from app.core.workflow_auto_advance import auto_advance_workflow_to_next_stop
from app.core.workflow_autopilot import ensure_workflow_atomic_chain_report, workflow_uses_ceo_board_delegate

DEFAULT_SCENARIO_SEED = 17
DEFAULT_MAX_TICKS = 180
DEFAULT_TIMEOUT_SEC = 7200
DEFAULT_LIVE_PROVIDER_TIMEOUT_SEC = 300
MAX_STALL_TICKS = 25
TERMINAL_TICKET_STATUSES = {"COMPLETED", "FAILED", "TIMED_OUT", "CANCELLED"}
PROVIDER_AUDIT_EVENT_TYPES = {
    "PROVIDER_ATTEMPT_STARTED",
    "PROVIDER_FIRST_TOKEN_RECEIVED",
    "PROVIDER_RETRY_SCHEDULED",
    "PROVIDER_ATTEMPT_FINISHED",
    "PROVIDER_FAILOVER_SELECTED",
}
RECOVERED_FAILURE_FAMILY_ORDER = (
    "Provider JSON / Bad Response",
    "Workspace Hook Validation",
    "Closeout Contract Violation",
    "Runtime Schema Validation",
    "Other",
)
PROVIDER_JSON_FAILURE_KINDS = {
    "PROVIDER_MALFORMED_JSON",
    "NO_JSON_OBJECT",
    "PROVIDER_BAD_RESPONSE",
    "PROVIDER_RATE_LIMITED",
    "PROVIDER_AUTH_FAILED",
    "UPSTREAM_UNAVAILABLE",
    "FIRST_TOKEN_TIMEOUT",
    "STREAM_IDLE_TIMEOUT",
    "REQUEST_TOTAL_TIMEOUT",
}
WORKSPACE_HOOK_FAILURE_KINDS = {
    "WORKSPACE_HOOK_VALIDATION_ERROR",
    "REQUIRED_HOOK_GATE_BLOCKED",
}
CLOSEOUT_CONTRACT_FAILURE_KINDS = {
    "ARTIFACT_VALIDATION_ERROR",
    "ARTIFACT_PERSIST_ERROR",
    "WRITE_SET_VIOLATION",
    "WORKFLOW_CHAIN_REPORT_UNAVAILABLE",
    "CLOSEOUT_CONTRACT_VIOLATION",
    "FINAL_ARTIFACT_REF_INVALID",
}
RUNTIME_SCHEMA_FAILURE_KINDS = {
    "SCHEMA_VALIDATION_FAILED",
    "SCHEMA_ERROR",
    "RUNTIME_SCHEMA_VALIDATION_FAILED",
}
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
    provider_id: str | None,
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
        "BOARDROOM_OS_RUNTIME_STRICT_PROVIDER_SELECTION": "1",
        "BOARDROOM_OS_CEO_MAINTENANCE_INTERVAL_SEC": "1",
        "BOARDROOM_OS_PROVIDER_OPENAI_COMPAT_BASE_URL": base_url,
        "BOARDROOM_OS_PROVIDER_OPENAI_COMPAT_API_KEY": api_key,
        "BOARDROOM_OS_PROVIDER_OPENAI_COMPAT_MODEL": "gpt-5.4",
        "BOARDROOM_OS_PROVIDER_OPENAI_COMPAT_REASONING_EFFORT": "high",
        "BOARDROOM_OS_PROVIDER_OPENAI_COMPAT_TIMEOUT_SEC": str(DEFAULT_LIVE_PROVIDER_TIMEOUT_SEC),
        "BOARDROOM_OS_CEO_STAFFING_VARIANT_SEED": str(seed),
        "BOARDROOM_OS_DEFAULT_EMPLOYEE_PROVIDER_ID": str(provider_id or "prov_openai_compat").strip(),
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
    normalized.pop("default_provider_id", None)
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


def _reasoning_effort_from_role_profile_ref(role_profile_ref: str) -> str:
    if role_profile_ref in {"architect_primary", "cto_primary"}:
        return "xhigh"
    return "high"


def _reasoning_effort_from_runtime_provider_binding(created_spec: dict[str, Any]) -> str | None:
    target_ref = resolve_execution_target_ref_from_ticket_spec(created_spec)
    if target_ref is None:
        return None
    try:
        config = resolve_runtime_provider_config()
        selection = resolve_provider_selection(
            config,
            target_ref=target_ref,
            employee_provider_id=None,
        )
    except Exception:
        return None
    if selection is None:
        return None
    return str(selection.effective_reasoning_effort or "").strip() or None


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


def workflow_provider_audit_events(repository, workflow_id: str) -> dict[str, list[dict[str, Any]]]:
    with repository.connection() as connection:
        rows = connection.execute(
            f"""
            SELECT *
            FROM events
            WHERE workflow_id = ?
              AND event_type IN ({",".join("?" for _ in PROVIDER_AUDIT_EVENT_TYPES)})
            ORDER BY sequence_no ASC
            """,
            (workflow_id, *sorted(PROVIDER_AUDIT_EVENT_TYPES)),
        ).fetchall()
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        event = repository._convert_event_row(row)
        ticket_id = str(event.get("ticket_id") or "").strip()
        if not ticket_id:
            continue
        grouped.setdefault(ticket_id, []).append(event)
    return grouped


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


def _source_delivery_verification_runs_from_terminal_payload(
    ticket_id: str,
    payload: dict[str, Any],
) -> list[Any]:
    source_files = list(payload.get("source_files") or [])
    verification_runs = list(payload.get("verification_runs") or [])
    written_artifacts = list(payload.get("written_artifacts") or [])
    verification_evidence_refs = list(payload.get("verification_evidence_refs") or [])
    if verification_runs:
        return list(verification_runs)
    if source_files:
        raise AssertionError(f"{ticket_id} is missing verification_runs in terminal payload.")
    if not written_artifacts:
        raise AssertionError(f"{ticket_id} is missing written_artifacts in terminal payload.")
    if not verification_evidence_refs:
        raise AssertionError(f"{ticket_id} is missing verification_evidence_refs in terminal payload.")

    evidence_refs = [str(item).strip() for item in verification_evidence_refs if str(item).strip()]
    written_artifacts_by_ref = {
        str(item.get("artifact_ref") or "").strip(): item
        for item in written_artifacts
        if isinstance(item, dict) and str(item.get("artifact_ref") or "").strip()
    }
    verification_runs = []
    for evidence_ref in evidence_refs:
        written_artifact = written_artifacts_by_ref.get(evidence_ref)
        if written_artifact is None:
            raise AssertionError(
                f"{ticket_id} verification_evidence_refs includes non-materialized artifact_ref {evidence_ref}."
            )
        content_json = written_artifact.get("content_json")
        if not isinstance(content_json, dict):
            raise AssertionError(
                f"{ticket_id} compact source delivery payload is missing content_json raw verification output."
            )
        verification_runs.append(dict(content_json))
    if not verification_runs:
        raise AssertionError(f"{ticket_id} compact source delivery payload is missing raw verification output.")
    return verification_runs


def _validate_source_delivery_payload(ticket_id: str, payload: dict[str, Any]) -> None:
    verification_runs = _source_delivery_verification_runs_from_terminal_payload(ticket_id, payload)
    for run in verification_runs:
        if not isinstance(run, dict):
            raise AssertionError(f"{ticket_id} contains invalid verification_runs payload.")
        if not str(run.get("command") or "").strip():
            raise AssertionError(f"{ticket_id} is missing verification command.")
        if not str(run.get("stdout") or "").strip() and not str(run.get("stderr") or "").strip():
            raise AssertionError(f"{ticket_id} is missing raw verification output.")


def _collect_source_delivery_payload_audit(
    created_specs: dict[str, dict[str, Any]],
    terminals: dict[str, dict[str, Any] | None],
) -> dict[str, Any]:
    source_delivery_ticket_ids = _source_delivery_ticket_ids(created_specs)
    completed_source_delivery_ticket_ids: list[str] = []
    failed_retry_entries: list[dict[str, str]] = []
    for ticket_id in source_delivery_ticket_ids:
        terminal_event = terminals.get(ticket_id) or {}
        terminal_event_type = str(terminal_event.get("event_type") or "TICKET_COMPLETED")
        payload = terminal_event.get("payload") or {}
        if terminal_event_type != "TICKET_COMPLETED":
            if terminal_event_type == "TICKET_FAILED":
                failure_detail = payload.get("failure_detail") if isinstance(payload, dict) else None
                failure_detail_kind = (
                    failure_detail.get("kind")
                    if isinstance(failure_detail, dict)
                    else None
                )
                payload_failure_kind = (
                    payload.get("failure_kind")
                    if isinstance(payload, dict)
                    else None
                )
                failure_kind = str(payload_failure_kind or failure_detail_kind or "")
                failed_retry_entries.append(
                    {
                        "ticket_id": ticket_id,
                        "failure_kind": failure_kind or "UNKNOWN",
                    }
                )
            continue
        completed_source_delivery_ticket_ids.append(ticket_id)
        if not isinstance(payload, dict):
            raise AssertionError(f"{ticket_id} is missing source delivery payload.")
        _validate_source_delivery_payload(ticket_id, payload)
    return {
        "completed_ticket_ids": completed_source_delivery_ticket_ids,
        "failed_retry_entries": failed_retry_entries,
        "failed_retry_count": len(failed_retry_entries),
    }


def _collect_source_delivery_payload_audit_for_snapshot(
    created_specs: dict[str, dict[str, Any]],
    terminals: dict[str, dict[str, Any] | None],
) -> dict[str, Any]:
    try:
        return _collect_source_delivery_payload_audit(created_specs, terminals)
    except AssertionError as exc:
        return {
            "completed_ticket_ids": [],
            "failed_retry_entries": [],
            "failed_retry_count": 0,
            "audit_error": str(exc),
        }


def _empty_recovered_failure_audit() -> dict[str, Any]:
    return {
        "total_count": 0,
        "groups": {
            family: {
                "count": 0,
                "entries": [],
            }
            for family in RECOVERED_FAILURE_FAMILY_ORDER
        },
        "repeated_fingerprints": [],
    }


def _failure_family(failure_kind: str) -> str:
    normalized = str(failure_kind or "").strip().upper()
    if normalized in PROVIDER_JSON_FAILURE_KINDS:
        return "Provider JSON / Bad Response"
    if normalized in WORKSPACE_HOOK_FAILURE_KINDS:
        return "Workspace Hook Validation"
    if normalized in CLOSEOUT_CONTRACT_FAILURE_KINDS:
        return "Closeout Contract Violation"
    if normalized in RUNTIME_SCHEMA_FAILURE_KINDS:
        return "Runtime Schema Validation"
    return "Other"


def _is_completed_ticket(ticket: dict[str, Any], terminal_event: dict[str, Any] | None) -> bool:
    if str(ticket.get("status") or "").upper() == "COMPLETED":
        return True
    return str((terminal_event or {}).get("event_type") or "").upper() == "TICKET_COMPLETED"


def _failure_payload_detail(payload: dict[str, Any]) -> dict[str, Any]:
    detail = payload.get("failure_detail")
    return dict(detail) if isinstance(detail, dict) else {}


def _stable_failure_fingerprint(
    *,
    family: str,
    failure_kind: str,
    payload: dict[str, Any],
    detail: dict[str, Any],
) -> str:
    explicit = (
        detail.get("fingerprint")
        or payload.get("fingerprint")
        or detail.get("failure_fingerprint")
        or payload.get("failure_fingerprint")
    )
    if explicit:
        return str(explicit)
    if family == "Provider JSON / Bad Response":
        provider_id = str(
            detail.get("provider_id")
            or payload.get("provider_id")
            or detail.get("actual_provider_id")
            or payload.get("actual_provider_id")
            or "unknown-provider"
        )
        model = str(
            detail.get("actual_model")
            or payload.get("actual_model")
            or detail.get("preferred_model")
            or payload.get("preferred_model")
            or "unknown-model"
        )
        discriminator = str(
            detail.get("parse_stage")
            or payload.get("parse_stage")
            or detail.get("response_error_type")
            or payload.get("response_error_type")
            or detail.get("timeout_phase")
            or payload.get("timeout_phase")
            or detail.get("schema_validation_error")
            or payload.get("schema_validation_error")
            or "provider_failure"
        )
        return f"provider:{provider_id}:{model}:{failure_kind}:{discriminator}"
    if family == "Workspace Hook Validation":
        hook_id = str(detail.get("hook_id") or payload.get("hook_id") or "unknown-hook")
        return f"hook:{hook_id}:{failure_kind}"
    return f"{family}:{failure_kind}"


def _find_recovered_by_ticket_id(
    *,
    tickets: list[dict[str, Any]],
    terminals: dict[str, dict[str, Any] | None],
    ticket_id: str,
    node_id: str,
    ticket_index: int,
) -> str | None:
    current_ticket = tickets[ticket_index] if 0 <= ticket_index < len(tickets) else {}
    if _is_completed_ticket(current_ticket, terminals.get(ticket_id)):
        return ticket_id
    if not node_id:
        return None
    for candidate in tickets[max(ticket_index + 1, 0):]:
        candidate_id = str(candidate.get("ticket_id") or "").strip()
        if not candidate_id:
            continue
        if str(candidate.get("node_id") or "").strip() != node_id:
            continue
        if _is_completed_ticket(candidate, terminals.get(candidate_id)):
            return candidate_id
    return None


def _collect_recovered_failure_audit(
    *,
    tickets: list[dict[str, Any]],
    terminals: dict[str, dict[str, Any] | None],
    provider_audit_by_ticket: dict[str, list[dict[str, Any]]],
    incidents: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    audit = _empty_recovered_failure_audit()
    ticket_index_by_id = {
        str(ticket.get("ticket_id") or "").strip(): index
        for index, ticket in enumerate(tickets)
        if str(ticket.get("ticket_id") or "").strip()
    }
    tickets_by_id = {
        str(ticket.get("ticket_id") or "").strip(): ticket
        for ticket in tickets
        if str(ticket.get("ticket_id") or "").strip()
    }
    seen_entries: set[tuple[str, str, str, str, int]] = set()

    def _add_entry(
        *,
        ticket_id: str,
        node_id: str,
        failure_kind: str,
        payload: dict[str, Any],
        source: str,
        attempt_no: int = 0,
    ) -> None:
        if not ticket_id or not failure_kind:
            return
        detail = _failure_payload_detail(payload)
        family = _failure_family(failure_kind)
        fingerprint = _stable_failure_fingerprint(
            family=family,
            failure_kind=failure_kind,
            payload=payload,
            detail=detail,
        )
        entry_key = (ticket_id, failure_kind, fingerprint, source, attempt_no)
        if entry_key in seen_entries:
            return
        seen_entries.add(entry_key)
        ticket_index = ticket_index_by_id.get(ticket_id, -1)
        recovered_by_ticket_id = _find_recovered_by_ticket_id(
            tickets=tickets,
            terminals=terminals,
            ticket_id=ticket_id,
            node_id=node_id,
            ticket_index=ticket_index,
        )
        entry = {
            "ticket_id": ticket_id,
            "node_id": node_id or str(payload.get("node_id") or ""),
            "failure_kind": failure_kind,
            "family": family,
            "fingerprint": fingerprint,
            "recovered_by_ticket_id": recovered_by_ticket_id,
            "source": source,
            "attempt_no": attempt_no,
        }
        group = audit["groups"][family]
        group["entries"].append(entry)
        group["count"] = len(group["entries"])
        audit["total_count"] = int(audit["total_count"]) + 1

    for ticket in tickets:
        ticket_id = str(ticket.get("ticket_id") or "").strip()
        if not ticket_id:
            continue
        terminal_event = terminals.get(ticket_id) or {}
        if str(terminal_event.get("event_type") or "").upper() != "TICKET_FAILED":
            continue
        payload = dict(terminal_event.get("payload") or {})
        failure_kind = str(payload.get("failure_kind") or "").strip()
        if not failure_kind:
            detail = _failure_payload_detail(payload)
            failure_kind = str(detail.get("kind") or "").strip()
        _add_entry(
            ticket_id=ticket_id,
            node_id=str(ticket.get("node_id") or payload.get("node_id") or "").strip(),
            failure_kind=failure_kind,
            payload=payload,
            source="terminal_event",
        )

    for ticket_id, events in provider_audit_by_ticket.items():
        ticket = tickets_by_id.get(str(ticket_id) or "", {})
        for event in events:
            if str(event.get("event_type") or "") != "PROVIDER_ATTEMPT_FINISHED":
                continue
            payload = dict(event.get("payload") or {})
            if str(payload.get("status") or "").upper() != "FAILED":
                continue
            failure_kind = str(payload.get("failure_kind") or "").strip()
            if not failure_kind:
                continue
            _add_entry(
                ticket_id=str(ticket_id),
                node_id=str(ticket.get("node_id") or payload.get("node_id") or "").strip(),
                failure_kind=failure_kind,
                payload=payload,
                source="provider_attempt",
                attempt_no=int(payload.get("attempt_no") or 0),
            )

    fingerprint_counts: dict[str, int] = {}
    for group in audit["groups"].values():
        for entry in group["entries"]:
            fingerprint = str(entry.get("fingerprint") or "").strip()
            if fingerprint:
                fingerprint_counts[fingerprint] = fingerprint_counts.get(fingerprint, 0) + 1

    incident_refs_by_fingerprint: dict[str, list[str]] = {}
    for incident in incidents or []:
        payload = dict(incident.get("payload") or {})
        incident_fingerprint = str(
            payload.get("fingerprint")
            or payload.get("latest_failure_fingerprint")
            or incident.get("fingerprint")
            or ""
        ).strip()
        if not incident_fingerprint:
            continue
        incident_id = str(payload.get("incident_id") or incident.get("incident_id") or "").strip()
        if incident_id:
            incident_refs_by_fingerprint.setdefault(incident_fingerprint, []).append(incident_id)

    audit["repeated_fingerprints"] = [
        {
            "fingerprint": fingerprint,
            "count": count,
            "incident_ids": incident_refs_by_fingerprint.get(fingerprint, []),
            "residual_risk": not bool(incident_refs_by_fingerprint.get(fingerprint)),
        }
        for fingerprint, count in sorted(fingerprint_counts.items())
        if count >= 3
    ]
    return audit


def _assert_source_delivery_payload_quality(
    created_specs: dict[str, dict[str, Any]],
    terminals: dict[str, dict[str, Any] | None],
) -> list[str]:
    audit = _collect_source_delivery_payload_audit(created_specs, terminals)
    return list(audit.get("completed_ticket_ids") or [])


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


def _runtime_execution_summary_from_trace(
    traces: list[dict[str, Any]],
    workflow_id: str,
) -> dict[str, Any]:
    outcomes: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for trace in traces:
        runtime_execution = dict(trace.get("runtime_execution") or {})
        for item in list(runtime_execution.get("outcomes") or []):
            if str(item.get("workflow_id") or "") == workflow_id:
                outcomes.append(dict(item))
        for item in list(runtime_execution.get("skipped") or []):
            if str(item.get("workflow_id") or "") == workflow_id:
                skipped.append(dict(item))
    return {
        "outcomes": outcomes,
        "skipped": skipped,
    }


def _latest_runtime_execution_summary(repository, workflow_id: str) -> dict[str, Any]:
    return _runtime_execution_summary_from_trace(
        recent_orchestration_trace(repository),
        workflow_id,
    )


def build_runtime_ticket_audit(repository, workflow_id: str) -> list[dict[str, Any]]:
    audits: list[dict[str, Any]] = []
    created_specs = workflow_created_specs(repository, workflow_id)
    terminals = workflow_terminal_events(repository, workflow_id)
    provider_audit_by_ticket = workflow_provider_audit_events(repository, workflow_id)
    for ticket in workflow_ticket_rows(repository, workflow_id):
        ticket_id = str(ticket["ticket_id"])
        created_spec = created_specs.get(ticket_id) or {}
        terminal_event = terminals.get(ticket_id) or {}
        assumptions = _parse_assumptions((terminal_event.get("payload") or {}).get("assumptions") or [])
        role_profile_ref = str(created_spec.get("role_profile_ref") or "")
        if not assumptions:
            provider_snapshot = _provider_snapshot_from_audit_events(provider_audit_by_ticket.get(ticket_id, []))
            if not provider_snapshot["provider_attempt_log"]:
                continue
            assumptions = {
                "actual_provider_id": str(provider_snapshot.get("actual_provider_id") or ""),
                "actual_model": str(provider_snapshot.get("actual_model") or ""),
                "effective_reasoning_effort": str(
                    provider_snapshot.get("effective_reasoning_effort")
                    or _reasoning_effort_from_runtime_provider_binding(created_spec)
                    or _reasoning_effort_from_role_profile_ref(role_profile_ref)
                ),
            }
            if not assumptions["actual_provider_id"] or not assumptions["actual_model"]:
                continue
        audits.append(
            {
                "ticket_id": ticket_id,
                "node_id": str(ticket.get("node_id") or ""),
                "role_profile_ref": role_profile_ref,
                "output_schema_ref": str(created_spec.get("output_schema_ref") or ""),
                "delivery_stage": str(created_spec.get("delivery_stage") or ""),
                "assumptions": assumptions,
            }
        )
    return audits


def _collect_staffing_gap_audit(repository, workflow_id: str) -> dict[str, Any]:
    gaps: list[dict[str, Any]] = []
    hire_actions: list[dict[str, Any]] = []
    with repository.connection() as connection:
        rows = connection.execute(
            """
            SELECT *
            FROM events
            WHERE workflow_id = ?
              AND event_type = 'SCHEDULER_LEASE_DIAGNOSTIC_RECORDED'
            ORDER BY sequence_no ASC
            """,
            (workflow_id,),
        ).fetchall()
    for row in rows:
        event = repository._convert_event_row(row)
        payload = dict(event.get("payload") or {})
        if str(payload.get("reason_code") or "").strip() != "NO_ELIGIBLE_WORKER":
            continue
        gaps.append(
            {
                "ticket_id": str(payload.get("ticket_id") or ""),
                "node_id": str(payload.get("node_id") or ""),
                "required_role_profile_ref": str(payload.get("required_role_profile_ref") or ""),
                "reason_code": "NO_ELIGIBLE_WORKER",
            }
        )
    for run in repository.list_ceo_shadow_runs(workflow_id):
        for action in list(run.get("executed_actions") or []):
            if str(action.get("action_type") or "").strip() != "HIRE_EMPLOYEE":
                continue
            payload = dict(action.get("payload") or {})
            hire_actions.append(
                {
                    "run_id": str(run.get("run_id") or ""),
                    "role_type": str(payload.get("role_type") or ""),
                    "role_profile_refs": list(payload.get("role_profile_refs") or []),
                    "employee_id": str(payload.get("employee_id") or ""),
                    "execution_status": str(action.get("execution_status") or ""),
                }
            )
    return {
        "gaps": gaps,
        "hire_actions": hire_actions,
    }


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


def _empty_provider_runtime_snapshot() -> dict[str, Any]:
    return {
        "provider_candidate_chain": [],
        "provider_attempt_log": [],
        "fallback_blocked": False,
        "final_failure_kind": None,
        "retry_backoff_schedule_sec": [],
        "preferred_provider_id": None,
        "actual_provider_id": None,
        "actual_model": None,
        "provider_failover_to": None,
        "provider_attempt_count": 0,
        "current_attempt_no": 0,
        "current_phase": None,
        "elapsed_sec": 0.0,
    }


def _phase_from_provider_audit_event(event: dict[str, Any]) -> str | None:
    payload = dict(event.get("payload") or {})
    explicit_phase = str(payload.get("current_phase") or "").strip()
    if explicit_phase:
        return explicit_phase
    event_type = str(event.get("event_type") or "")
    if event_type == "PROVIDER_ATTEMPT_STARTED":
        return "awaiting_first_token"
    if event_type == "PROVIDER_FIRST_TOKEN_RECEIVED":
        return "streaming"
    if event_type == "PROVIDER_RETRY_SCHEDULED":
        return "retry_waiting"
    if event_type == "PROVIDER_ATTEMPT_FINISHED":
        return "completed" if str(payload.get("status") or "").upper() == "COMPLETED" else "failed"
    return None


def _provider_snapshot_from_audit_events(events: list[dict[str, Any]]) -> dict[str, Any]:
    if not events:
        return _empty_provider_runtime_snapshot()

    attempt_log_by_key: dict[tuple[str, int], dict[str, Any]] = {}
    retry_backoff_schedule_sec: list[Any] = []
    provider_candidate_chain: list[str] = []
    provider_failover_to: str | None = None
    latest_payload = dict(events[-1].get("payload") or {})

    for event in events:
        payload = dict(event.get("payload") or {})
        if payload.get("retry_backoff_schedule_sec"):
            retry_backoff_schedule_sec = list(payload.get("retry_backoff_schedule_sec") or [])
        if payload.get("provider_candidate_chain"):
            provider_candidate_chain = list(payload.get("provider_candidate_chain") or [])
        if payload.get("to_provider_id"):
            provider_failover_to = str(payload.get("to_provider_id") or "")

        provider_id = str(payload.get("provider_id") or "").strip()
        attempt_no = int(payload.get("attempt_no") or 0)
        if not provider_id or attempt_no <= 0:
            continue
        key = (provider_id, attempt_no)
        current = attempt_log_by_key.setdefault(
            key,
            {
                "provider_id": provider_id,
                "attempt_no": attempt_no,
                "status": "IN_PROGRESS",
                "failure_kind": None,
            },
        )
        event_type = str(event.get("event_type") or "")
        if event_type == "PROVIDER_ATTEMPT_FINISHED":
            current["status"] = str(payload.get("status") or "UNKNOWN")
            current["failure_kind"] = payload.get("failure_kind")
            if payload.get("fingerprint"):
                current["fingerprint"] = payload.get("fingerprint")
        elif event_type == "PROVIDER_RETRY_SCHEDULED":
            current["status"] = "RETRY_WAITING"
            current["failure_kind"] = payload.get("failure_kind")
            if payload.get("fingerprint"):
                current["fingerprint"] = payload.get("fingerprint")
        else:
            current["status"] = "IN_PROGRESS"

    if not provider_candidate_chain:
        latest_provider_id = str(latest_payload.get("provider_id") or "").strip()
        provider_candidate_chain = [latest_provider_id] if latest_provider_id else []

    current_attempt_no = int(latest_payload.get("attempt_no") or 0)
    return {
        "provider_candidate_chain": provider_candidate_chain,
        "provider_attempt_log": list(attempt_log_by_key.values()),
        "fallback_blocked": False,
        "final_failure_kind": latest_payload.get("failure_kind"),
        "retry_backoff_schedule_sec": retry_backoff_schedule_sec,
        "preferred_provider_id": latest_payload.get("preferred_provider_id"),
        "actual_provider_id": latest_payload.get("actual_provider_id") or latest_payload.get("provider_id"),
        "actual_model": latest_payload.get("actual_model"),
        "effective_reasoning_effort": latest_payload.get("effective_reasoning_effort"),
        "provider_failover_to": provider_failover_to,
        "provider_attempt_count": max(
            [int((event.get("payload") or {}).get("attempt_no") or 0) for event in events],
            default=current_attempt_no,
        ),
        "current_attempt_no": current_attempt_no,
        "current_phase": _phase_from_provider_audit_event(events[-1]),
        "elapsed_sec": float(latest_payload.get("elapsed_sec") or 0.0),
    }


def _latest_provider_runtime_snapshot(repository, workflow_id: str) -> dict[str, Any]:
    terminals = workflow_terminal_events(repository, workflow_id)
    provider_audit_by_ticket = workflow_provider_audit_events(repository, workflow_id)
    for ticket in reversed(workflow_ticket_rows(repository, workflow_id)):
        ticket_id = str(ticket["ticket_id"])
        audit_snapshot = _provider_snapshot_from_audit_events(provider_audit_by_ticket.get(ticket_id, []))
        if audit_snapshot["provider_attempt_log"]:
            terminal_event = terminals.get(ticket_id)
            if terminal_event:
                payload = terminal_event.get("payload") or {}
                failure_detail = payload.get("failure_detail") or {}
                if failure_detail.get("provider_candidate_chain"):
                    audit_snapshot["provider_candidate_chain"] = list(
                        failure_detail.get("provider_candidate_chain") or []
                    )
                if failure_detail.get("retry_backoff_schedule_sec"):
                    audit_snapshot["retry_backoff_schedule_sec"] = list(
                        failure_detail.get("retry_backoff_schedule_sec") or []
                    )
                audit_snapshot["fallback_blocked"] = bool(failure_detail.get("fallback_blocked"))
                audit_snapshot["final_failure_kind"] = payload.get("failure_kind")
            return audit_snapshot

        terminal_event = terminals.get(ticket_id)
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
            "retry_backoff_schedule_sec": list(failure_detail.get("retry_backoff_schedule_sec") or []),
            "preferred_provider_id": assumptions.get("preferred_provider_id"),
            "actual_provider_id": assumptions.get("actual_provider_id"),
            "actual_model": assumptions.get("actual_model"),
            "provider_failover_to": assumptions.get("provider_failover_to"),
            "provider_attempt_count": int(failure_detail.get("attempt_count") or 0),
            "current_attempt_no": int(failure_detail.get("attempt_count") or 0),
            "current_phase": ("failed" if payload.get("failure_kind") else "completed"),
            "elapsed_sec": 0.0,
        }
    return _empty_provider_runtime_snapshot()


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
    provider_snapshot = _latest_provider_runtime_snapshot(repository, workflow_id)
    runtime_execution_summary = _latest_runtime_execution_summary(repository, workflow_id)
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
        "open_incidents": [
            {
                "incident_id": str(item.get("incident_id") or ""),
                "incident_type": str(item.get("incident_type") or ""),
                "status": str(item.get("status") or ""),
                "provider_id": str(item.get("provider_id") or ""),
                "circuit_breaker_state": str(item.get("circuit_breaker_state") or ""),
            }
            for item in incidents
            if str(item.get("status") or "").upper() in {"OPEN", "RECOVERING"}
        ],
        "provider_id": provider_snapshot.get("actual_provider_id"),
        "current_attempt_no": provider_snapshot.get("current_attempt_no"),
        "current_phase": provider_snapshot.get("current_phase"),
        "elapsed_sec": provider_snapshot.get("elapsed_sec"),
        "runtime_execution_summary": runtime_execution_summary,
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
        write_integration_monitor_report(
            paths,
            entries=entries,
            runtime_execution_summary=snapshot.get("runtime_execution_summary"),
        )
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
        write_integration_monitor_report(
            paths,
            entries=entries,
            runtime_execution_summary=snapshot.get("runtime_execution_summary"),
        )

    state["previous_snapshot"] = snapshot
    state["previous_signature"] = current_signature
    return state


def _should_count_stall(
    *,
    workflow: dict[str, Any],
    active_ticket_ids: list[str],
    open_incidents: list[dict[str, Any]],
) -> bool:
    if active_ticket_ids:
        return False
    workflow_status = str(workflow.get("status") or "").upper()
    if workflow_status in {"COMPLETED", "FAILED", "TIMED_OUT", "CANCELLED"}:
        return False
    recoverable_incident_types = {
        "PROVIDER_EXECUTION_PAUSED",
        "RUNTIME_TIMEOUT_ESCALATION",
        "REPEATED_FAILURE_ESCALATION",
        "STAFFING_CONTAINMENT",
    }
    for incident in open_incidents:
        incident_status = str(incident.get("status") or "").upper()
        incident_type = str(incident.get("incident_type") or "").upper()
        if incident_status in {"OPEN", "RECOVERING"} and incident_type in recoverable_incident_types:
            return False
    return True


def _should_increment_stall(
    *,
    previous_signature: tuple[Any, ...] | None,
    current_signature: tuple[Any, ...] | None,
    workflow: dict[str, Any],
    active_ticket_ids: list[str],
    open_incidents: list[dict[str, Any]],
) -> bool:
    if previous_signature is None or current_signature is None:
        return False
    if current_signature != previous_signature:
        return False
    return _should_count_stall(
        workflow=workflow,
        active_ticket_ids=active_ticket_ids,
        open_incidents=open_incidents,
    )


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
    runtime_execution_summary = _latest_runtime_execution_summary(repository, workflow_id)
    if hasattr(repository, "connection"):
        created_specs = workflow_created_specs(repository, workflow_id)
        terminals = workflow_terminal_events(repository, workflow_id)
        provider_audit_by_ticket = workflow_provider_audit_events(repository, workflow_id)
        source_delivery_payload_audit = _collect_source_delivery_payload_audit_for_snapshot(created_specs, terminals)
        staffing_gap_audit = _collect_staffing_gap_audit(repository, workflow_id)
        recovered_failure_audit = _collect_recovered_failure_audit(
            tickets=tickets,
            terminals=terminals,
            provider_audit_by_ticket=provider_audit_by_ticket,
            incidents=incidents,
        )
    else:
        source_delivery_payload_audit = {
            "completed_ticket_ids": [],
            "failed_retry_entries": [],
            "failed_retry_count": 0,
        }
        staffing_gap_audit = {
            "gaps": [],
            "hire_actions": [],
        }
        recovered_failure_audit = _empty_recovered_failure_audit()
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
        "runtime_execution_summary": runtime_execution_summary,
        "source_delivery_payload_audit": source_delivery_payload_audit,
        "staffing_gap_audit": staffing_gap_audit,
        "recovered_failure_audit": recovered_failure_audit,
        **provider_snapshot,
    }


def _append_runtime_execution_summary(lines: list[str], runtime_execution_summary: dict[str, Any] | None) -> None:
    summary = dict(runtime_execution_summary or {})
    outcomes = list(summary.get("outcomes") or [])
    skipped = list(summary.get("skipped") or [])
    if not outcomes and not skipped:
        return
    lines.extend(
        [
            "",
            "## Runtime Execution",
        ]
    )
    if outcomes:
        for item in outcomes:
            lines.append(
                "- outcome: "
                f"`{item.get('ticket_id') or 'unknown-ticket'}` "
                f"`{item.get('action') or 'unknown'}` "
                f"start `{item.get('start_ack_status') or 'none'}` "
                f"final `{item.get('final_ack_status') or 'none'}`"
            )
    else:
        lines.append("- outcome: `none`")
    if skipped:
        for item in skipped:
            lines.append(
                "- skipped: "
                f"`{item.get('ticket_id') or 'unknown-ticket'}` "
                f"`{item.get('reason_code') or 'UNKNOWN'}` "
                f"{item.get('reason') or ''}".rstrip()
            )
    else:
        lines.append("- skipped: `none`")


def write_integration_monitor_report(
    paths: ScenarioPaths,
    *,
    entries: list[dict[str, Any]],
    runtime_execution_summary: dict[str, Any] | None = None,
) -> Path:
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
        if entry.get("provider_id") or entry.get("current_phase"):
            lines.append(
                "- provider: "
                f"`{entry.get('provider_id') or 'unknown'}` "
                f"attempt `{entry.get('current_attempt_no') or 0}` "
                f"phase `{entry.get('current_phase') or 'unknown'}` "
                f"elapsed `{entry.get('elapsed_sec') or 0}`"
            )
    _append_runtime_execution_summary(lines, runtime_execution_summary)
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
    retry_backoff_schedule_sec = list(snapshot.get("retry_backoff_schedule_sec") or [])
    fallback_blocked = bool(snapshot.get("fallback_blocked"))
    final_failure_kind = snapshot.get("final_failure_kind")
    provider_attempt_count = int(snapshot.get("provider_attempt_count") or 0)
    current_attempt_no = int(snapshot.get("current_attempt_no") or 0)
    current_phase = snapshot.get("current_phase")
    provider_elapsed_sec = snapshot.get("elapsed_sec")
    runtime_execution_summary = dict(snapshot.get("runtime_execution_summary") or {})
    source_delivery_payload_audit = dict(snapshot.get("source_delivery_payload_audit") or {})
    staffing_gap_audit = dict(snapshot.get("staffing_gap_audit") or {})
    staffing_gaps = list(staffing_gap_audit.get("gaps") or [])
    staffing_hire_actions = list(staffing_gap_audit.get("hire_actions") or [])
    failed_source_delivery_retries = list(source_delivery_payload_audit.get("failed_retry_entries") or [])
    recovered_failure_audit = dict(snapshot.get("recovered_failure_audit") or _empty_recovered_failure_audit())
    recovered_failure_groups = dict(recovered_failure_audit.get("groups") or {})
    repeated_failure_fingerprints = list(recovered_failure_audit.get("repeated_fingerprints") or [])
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
        f"- Retry schedule: `{(', '.join(str(item) for item in retry_backoff_schedule_sec) if retry_backoff_schedule_sec else 'none')}`",
        f"- Provider attempts observed: `{provider_attempt_count}`",
        f"- Current attempt: `{current_attempt_no or 'none'}`",
        f"- Current phase: `{current_phase or 'none'}`",
        f"- Provider elapsed sec: `{provider_elapsed_sec if provider_elapsed_sec is not None else 'none'}`",
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
            "## Source Delivery Retry Audit",
            f"- Failed retry count: `{len(failed_source_delivery_retries)}`",
            f"- Completed source delivery tickets: `{', '.join(source_delivery_payload_audit.get('completed_ticket_ids') or []) or 'none'}`",
        ]
    )
    if failed_source_delivery_retries:
        for item in failed_source_delivery_retries:
            lines.append(
                "- failed retry: "
                f"`{item.get('ticket_id') or 'unknown-ticket'}` "
                f"`{item.get('failure_kind') or 'UNKNOWN'}`"
            )
    else:
        lines.append("- failed retry: `none`")
    lines.extend(
        [
            "",
            "## Recovered Failure Audit",
            f"- Total recovered / historical failures: `{int(recovered_failure_audit.get('total_count') or 0)}`",
        ]
    )
    has_recovered_entries = False
    for family in RECOVERED_FAILURE_FAMILY_ORDER:
        group = dict(recovered_failure_groups.get(family) or {})
        entries = list(group.get("entries") or [])
        if not entries:
            continue
        has_recovered_entries = True
        lines.append(f"- family: `{family}` count `{len(entries)}`")
        for item in entries:
            recovered_by = item.get("recovered_by_ticket_id") or "none"
            lines.append(
                "- recovered failure: "
                f"`{item.get('ticket_id') or 'unknown-ticket'}` "
                f"`{item.get('node_id') or 'unknown-node'}` "
                f"`{item.get('failure_kind') or 'UNKNOWN'}` "
                f"fingerprint `{item.get('fingerprint') or 'unknown-fingerprint'}` "
                f"recovered by `{recovered_by}`"
            )
    if not has_recovered_entries:
        lines.append("- recovered failure: `none`")
    if repeated_failure_fingerprints:
        lines.append("- repeated fingerprints:")
        for item in repeated_failure_fingerprints:
            incident_ids = ", ".join(str(value) for value in list(item.get("incident_ids") or []))
            residual_risk = "yes" if item.get("residual_risk") else "no"
            lines.append(
                "- repeated fingerprint: "
                f"`{item.get('fingerprint') or 'unknown-fingerprint'}` "
                f"count `{item.get('count') or 0}` "
                f"incidents `{incident_ids or 'none'}` "
                f"residual risk `{residual_risk}`"
            )
    else:
        lines.append("- repeated fingerprint: `none`")
    lines.extend(
        [
            "",
            "## Staffing Gap Audit",
            f"- No eligible worker gaps: `{len(staffing_gaps)}`",
            f"- CEO hire actions: `{len(staffing_hire_actions)}`",
        ]
    )
    if staffing_gaps:
        for item in staffing_gaps:
            lines.append(
                "- staffing gap: "
                f"`{item.get('ticket_id') or 'unknown-ticket'}` "
                f"`{item.get('required_role_profile_ref') or 'unknown-role'}` "
                f"`{item.get('reason_code') or 'UNKNOWN'}`"
            )
    else:
        lines.append("- staffing gap: `none`")
    if staffing_hire_actions:
        for item in staffing_hire_actions:
            role_profile_refs = ", ".join(str(value) for value in list(item.get("role_profile_refs") or []))
            lines.append(
                "- hire action: "
                f"`{item.get('employee_id') or 'unknown-employee'}` "
                f"`{item.get('role_type') or 'unknown-role-type'}` "
                f"`{role_profile_refs or 'no-role-profile'}` "
                f"`{item.get('execution_status') or 'UNKNOWN'}`"
            )
    else:
        lines.append("- hire action: `none`")
    lines.extend(
        [
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
    _append_runtime_execution_summary(lines, runtime_execution_summary)
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


def _write_failure_report(
    paths: ScenarioPaths,
    *,
    scenario_slug: str,
    workflow_id: str,
    failure_mode: str,
    completion_mode: str,
    elapsed_sec: float,
    started_at: str | None,
    finished_at: str,
    snapshot_path: Path,
    provider_snapshot: dict[str, Any],
) -> dict[str, Any]:
    report = {
        "success": False,
        "scenario_slug": scenario_slug,
        "workflow_id": workflow_id,
        "completion_mode": completion_mode,
        "failure_mode": failure_mode,
        "elapsed_sec": elapsed_sec,
        "started_at": started_at,
        "finished_at": finished_at,
        "snapshot_path": str(snapshot_path),
        "provider_attempt_count": int(provider_snapshot.get("provider_attempt_count") or 0),
        "current_attempt_no": int(provider_snapshot.get("current_attempt_no") or 0),
        "current_phase": provider_snapshot.get("current_phase"),
        "elapsed_sec_provider": float(provider_snapshot.get("elapsed_sec") or 0.0),
        "provider_attempt_log": list(provider_snapshot.get("provider_attempt_log") or []),
        "runtime_execution_summary": dict(provider_snapshot.get("runtime_execution_summary") or {}),
    }
    _write_json(paths.run_report_path, report)
    return report


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
    report = _write_failure_report(
        paths,
        scenario_slug=paths.root.name,
        workflow_id=workflow_id,
        failure_mode=label,
        completion_mode=label,
        elapsed_sec=round(time.monotonic() - float(monitor_state.get("started_monotonic") or time.monotonic()), 2),
        started_at=monitor_state.get("started_at"),
        finished_at=now_local().isoformat(),
        snapshot_path=target_path,
        provider_snapshot=snapshot,
    )
    write_audit_summary(
        paths,
        report=report,
        snapshot={**snapshot, "tickets": list(snapshot.get("tickets") or [])[-20:]},
    )
    write_integration_monitor_report(
        paths,
        entries=list(monitor_state.get("entries") or []),
        runtime_execution_summary=snapshot.get("runtime_execution_summary"),
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
    source_delivery_payload_audit = _collect_source_delivery_payload_audit(created_specs, terminals)
    source_delivery_ticket_ids = list(source_delivery_payload_audit.get("completed_ticket_ids") or [])

    chain_report_artifact_ref = f"art://workflow-chain/{workflow_id}/workflow-chain-report.json"
    if not artifact_exists(repository, chain_report_artifact_ref):
        ensure_workflow_atomic_chain_report(repository, workflow_id=workflow_id)
        raise AssertionError("Workflow chain report was not materialized by production completion path.")
    ensure_workflow_atomic_chain_report(repository, workflow_id=workflow_id)
    if not artifact_exists(repository, chain_report_artifact_ref):
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
        "source_delivery_payload_audit": source_delivery_payload_audit,
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


def _maybe_recover_live_delegate_blockers(
    repository,
    *,
    workflow_id: str,
    idempotency_key_prefix: str,
    tick_index: int,
) -> bool:
    workflow = repository.get_workflow_projection(workflow_id)
    if not workflow_uses_ceo_board_delegate(workflow):
        return False

    open_approvals = [item for item in repository.list_open_approvals() if item["workflow_id"] == workflow_id]
    open_incidents = [item for item in repository.list_open_incidents() if item["workflow_id"] == workflow_id]
    if not open_approvals and not open_incidents:
        return False

    before = (len(open_approvals), len(open_incidents))
    auto_advance_workflow_to_next_stop(
        repository,
        workflow_id=workflow_id,
        idempotency_key_prefix=f"{idempotency_key_prefix}:{tick_index}",
        max_steps=4,
        max_dispatches=20,
    )
    after = (
        sum(1 for item in repository.list_open_approvals() if item["workflow_id"] == workflow_id),
        sum(1 for item in repository.list_open_incidents() if item["workflow_id"] == workflow_id),
    )
    return after != before


def _latest_resumable_workflow_id(repository) -> str | None:
    with repository.connection() as connection:
        row = connection.execute(
            """
            SELECT workflow_id
            FROM workflow_projection
            WHERE status = 'EXECUTING'
            ORDER BY updated_at DESC, workflow_id DESC
            LIMIT 1
            """
        ).fetchone()
    if row is None:
        return None
    return str(row["workflow_id"])


def run_live_scenario(
    scenario: LiveScenarioDefinition,
    *,
    clean: bool = True,
    max_ticks: int = DEFAULT_MAX_TICKS,
    timeout_sec: int = DEFAULT_TIMEOUT_SEC,
    seed: int = DEFAULT_SCENARIO_SEED,
    scenario_root: Path | None = None,
) -> dict[str, Any]:
    provider_payload = load_integration_test_provider_payload(scenario_slug=scenario.slug)
    return run_live_scenario_with_provider_payload(
        scenario,
        provider_payload,
        clean=clean,
        max_ticks=max_ticks,
        timeout_sec=timeout_sec,
        seed=seed,
        scenario_root=scenario_root,
    )


def run_live_scenario_with_provider_payload(
    scenario: LiveScenarioDefinition,
    provider_payload: dict[str, Any],
    *,
    clean: bool = True,
    max_ticks: int = DEFAULT_MAX_TICKS,
    timeout_sec: int = DEFAULT_TIMEOUT_SEC,
    seed: int = DEFAULT_SCENARIO_SEED,
    scenario_root: Path | None = None,
) -> dict[str, Any]:
    paths = build_scenario_paths(scenario.slug, scenario_root)
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
    with scenario_environment(
        paths,
        base_url=base_url,
        api_key=api_key,
        provider_id=str(first_provider.get("provider_id") or "").strip() or None,
        seed=seed,
    ):
        with TestClient(create_app()) as client:
            runtime_response = client.post(
                "/api/v1/commands/runtime-provider-upsert",
                json=provider_payload,
            )
            if runtime_response.status_code != 200 or runtime_response.json()["status"] != "ACCEPTED":
                raise RuntimeError(f"runtime-provider-upsert failed: {runtime_response.text}")

            repository = client.app.state.repository
            workflow_id = None if clean else _latest_resumable_workflow_id(repository)
            if workflow_id is None:
                project_response = client.post(
                    "/api/v1/commands/project-init",
                    json=build_project_init_payload(scenario),
                )
                if project_response.status_code != 200 or project_response.json()["status"] != "ACCEPTED":
                    raise RuntimeError(f"project-init failed: {project_response.text}")
                workflow_id = project_response.json()["causation_hint"].split(":", 1)[1]
            consecutive_stalls = 0
            monitor_state: dict[str, Any] = {
                "entries": [],
                "started_at": now_local().isoformat(),
                "started_monotonic": time.monotonic(),
            }
            run_idempotency_token = str(monitor_state["started_at"]).replace(":", "").replace(".", "")
            provider_id = str(first_provider.get("provider_id") or "").strip() or None
            model_name = str(first_provider.get("preferred_model") or "").strip() or None

            for tick_index in range(max_ticks):
                run_scheduler_once(
                    repository,
                    idempotency_key=(
                        f"live-scenario:{scenario.slug}:{workflow_id}:{run_idempotency_token}:{tick_index}"
                    ),
                    max_dispatches=20,
                    tick_index=tick_index,
                )
                _maybe_recover_live_delegate_blockers(
                    repository,
                    workflow_id=workflow_id,
                    idempotency_key_prefix=(
                        f"live-scenario-recover:{scenario.slug}:{workflow_id}:{run_idempotency_token}"
                    ),
                    tick_index=tick_index,
                )
                workflow = repository.get_workflow_projection(workflow_id)
                previous_signature = monitor_state.get("previous_signature")
                monitor_state = _update_monitor_entries(
                    paths,
                    repository,
                    workflow_id,
                    state=monitor_state,
                )
                current_snapshot = dict(monitor_state.get("previous_snapshot") or {})
                current_signature = monitor_state.get("previous_signature")
                if _should_increment_stall(
                    previous_signature=previous_signature,
                    current_signature=current_signature,
                    workflow=(workflow or {}),
                    active_ticket_ids=list(current_snapshot.get("active_ticket_ids") or []),
                    open_incidents=list(current_snapshot.get("open_incidents") or []),
                ):
                    consecutive_stalls += 1
                else:
                    consecutive_stalls = 0

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
                    report["runtime_execution_summary"] = _latest_runtime_execution_summary(
                        repository,
                        workflow_id,
                    )
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
                        report["runtime_execution_summary"] = _latest_runtime_execution_summary(
                            repository,
                            workflow_id,
                        )
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
        clean=args.clean,
        max_ticks=args.max_ticks,
        timeout_sec=args.timeout_sec,
        seed=args.seed,
        scenario_root=args.scenario_root,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0
