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
from typing import Any

from fastapi.testclient import TestClient

BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.main import create_app
from app.scheduler_runner import run_scheduler_once


DEFAULT_SCENARIO_SLUG = "library_management_autopilot_live"
DEFAULT_SCENARIO_SEED = 17
DEFAULT_MAX_TICKS = 180
DEFAULT_TIMEOUT_SEC = 7200
DEFAULT_LIVE_PROVIDER_TIMEOUT_SEC = 180
MAX_STALL_TICKS = 25
SCENARIO_GOAL = "全自动开发一个计算机系毕业设计-有精美设计的图书馆管理系统"
SCENARIO_CONSTRAINTS = [
    (
        "该项目全权授予CEO自由裁量的权利，进度完全由CEO自主推进无需经过董事会审议，包括招聘，"
        "召集架构师、系统分析师选型和详细梳理系统，分配开发工作，审阅测试结果，审阅里程碑，"
        "交给运维人员发布，向董事会交付报告。"
    ),
    "CEO 必须真实招聘并真实使用 architect_primary，系统分析职责并入架构治理链。",
    (
        "需求拆解必须足够原子，workflow 最终 ticket 总数不得少于 30，"
        "并覆盖架构、详细设计、前端、后端、数据、测试、评审、发布、closeout。"
    ),
    "开发、测试、平台岗位允许继续扩招，且同岗人员画像必须明显拉开风险偏好、质疑方式、节奏和审美。",
    (
        "图书馆管理系统至少覆盖：认证与 RBAC、读者档案、馆藏目录、检索、借阅归还、预约、罚金、"
        "库存与盘点、公告、统计报表、审计日志、部署发布、运维监控与交付报告。"
    ),
]


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
    failure_snapshot_root: Path


def build_scenario_paths(scenario_root: Path | None = None) -> ScenarioPaths:
    root = Path(scenario_root) if scenario_root is not None else (
        BACKEND_ROOT / "data" / "scenarios" / DEFAULT_SCENARIO_SLUG
    )
    return ScenarioPaths(
        root=root,
        db_path=root / "boardroom_os.db",
        runtime_provider_config_path=root / "runtime-provider-config.json",
        artifact_store_root=root / "artifacts",
        artifact_upload_root=root / "artifact_uploads",
        developer_inspector_root=root / "developer_inspector",
        ticket_context_archive_root=root / "ticket_context_archives",
        run_report_path=root / "run_report.json",
        failure_snapshot_root=root / "failure_snapshots",
    )


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
):
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


def _require_live_provider_credentials() -> tuple[str, str]:
    base_url = str(os.environ.get("BOARDROOM_OS_PROVIDER_OPENAI_COMPAT_BASE_URL") or "").strip()
    api_key = str(os.environ.get("BOARDROOM_OS_PROVIDER_OPENAI_COMPAT_API_KEY") or "").strip()
    if not base_url or not api_key:
        raise RuntimeError(
            "Live scenario requires BOARDROOM_OS_PROVIDER_OPENAI_COMPAT_BASE_URL and "
            "BOARDROOM_OS_PROVIDER_OPENAI_COMPAT_API_KEY."
        )
    return base_url, api_key


def _runtime_provider_payload(base_url: str, api_key: str) -> dict[str, Any]:
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
                "alias": "library-live",
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
        "idempotency_key": "runtime-provider-upsert:library-management-live",
    }


def _project_init_payload() -> dict[str, Any]:
    return {
        "north_star_goal": SCENARIO_GOAL,
        "hard_constraints": list(SCENARIO_CONSTRAINTS),
        "budget_cap": 1_500_000,
        "deadline_at": None,
        "workflow_profile": "CEO_AUTOPILOT_FINE_GRAINED",
        "force_requirement_elicitation": False,
    }


def _parse_assumptions(assumptions: list[str] | None) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for item in assumptions or []:
        if "=" not in str(item):
            continue
        key, value = str(item).split("=", 1)
        parsed[key] = value
    return parsed


def _workflow_ticket_rows(repository, workflow_id: str) -> list[dict[str, Any]]:
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


def _compiled_ticket_ids(repository, workflow_id: str) -> list[str]:
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


def _recent_orchestration_trace(repository, *, limit: int = 5) -> list[dict[str, Any]]:
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


def _build_runtime_ticket_audit(repository, workflow_id: str) -> list[dict[str, Any]]:
    audits: list[dict[str, Any]] = []
    for ticket in _workflow_ticket_rows(repository, workflow_id):
        ticket_id = str(ticket["ticket_id"])
        created_spec = repository.get_latest_ticket_created_payload(ticket_id) or {}
        terminal_event = repository.get_latest_ticket_terminal_event(ticket_id)
        assumptions = _parse_assumptions((terminal_event or {}).get("payload", {}).get("assumptions") or [])
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


def _artifact_exists(repository, artifact_ref: str) -> bool:
    return repository.get_artifact_by_ref(artifact_ref) is not None


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )


def _write_failure_snapshot(paths: ScenarioPaths, repository, workflow_id: str, *, label: str) -> Path:
    snapshot = {
        "workflow": repository.get_workflow_projection(workflow_id),
        "open_approvals": [item for item in repository.list_open_approvals() if item["workflow_id"] == workflow_id],
        "open_incidents": [item for item in repository.list_open_incidents() if item["workflow_id"] == workflow_id],
        "tickets": _workflow_ticket_rows(repository, workflow_id)[-20:],
        "ceo_shadow_runs": repository.list_ceo_shadow_runs(workflow_id, limit=10),
        "orchestration_trace": _recent_orchestration_trace(repository),
    }
    target_path = paths.failure_snapshot_root / f"{label}.json"
    _write_json(target_path, snapshot)
    return target_path


def _assert_scenario_outcome(paths: ScenarioPaths, repository, workflow_id: str) -> dict[str, Any]:
    workflow = repository.get_workflow_projection(workflow_id)
    if workflow is None:
        raise AssertionError("Workflow projection is missing.")
    if workflow["status"] != "COMPLETED":
        raise AssertionError(f"Workflow did not complete. Current status: {workflow['status']}")
    if workflow["current_stage"] != "closeout":
        raise AssertionError(f"Workflow current_stage is {workflow['current_stage']}, expected closeout.")

    tickets = _workflow_ticket_rows(repository, workflow_id)
    if len(tickets) < 30:
        raise AssertionError(f"Workflow produced {len(tickets)} tickets, expected at least 30.")

    if not _artifact_exists(repository, f"art://workflow-chain/{workflow_id}/workflow-chain-report.json"):
        raise AssertionError("Workflow chain report artifact is missing.")

    if not any(
        (repository.get_latest_ticket_created_payload(str(ticket["ticket_id"])) or {}).get("output_schema_ref")
        == "delivery_closeout_package"
        for ticket in tickets
    ):
        raise AssertionError("No delivery_closeout_package ticket was recorded.")

    compiled_ticket_ids = _compiled_ticket_ids(repository, workflow_id)
    archived_ticket_ids = sorted(path.stem for path in paths.ticket_context_archive_root.glob("*.md"))
    if sorted(compiled_ticket_ids) != archived_ticket_ids:
        raise AssertionError(
            "Ticket context archives do not match compiled runtime tickets: "
            f"compiled={compiled_ticket_ids} archived={archived_ticket_ids}"
        )

    employees = [
        employee
        for employee in repository.list_employee_projections(states=["ACTIVE"])
        if bool(employee.get("board_approved"))
    ]
    if not any(str(employee.get("role_type") or "") == "governance_architect" for employee in employees):
        raise AssertionError("No approved governance_architect employee was hired.")

    audits = _build_runtime_ticket_audit(repository, workflow_id)
    architect_audits = [item for item in audits if item["role_profile_ref"] == "architect_primary"]
    if not architect_audits:
        raise AssertionError("No architect_primary runtime ticket completed with recorded assumptions.")
    if not any(
        audit["assumptions"].get("actual_model") == "gpt-5.4"
        and audit["assumptions"].get("effective_reasoning_effort") == "xhigh"
        for audit in architect_audits
    ):
        raise AssertionError("Architect runtime audit did not record gpt-5.4 @ xhigh.")

    non_architect_audits = [item for item in audits if item["role_profile_ref"] != "architect_primary"]
    if not non_architect_audits:
        raise AssertionError("No non-architect runtime tickets completed.")
    invalid_non_architect = [
        item
        for item in non_architect_audits
        if item["assumptions"].get("actual_model") != "gpt-5.4"
        or item["assumptions"].get("effective_reasoning_effort") != "high"
    ]
    if invalid_non_architect:
        raise AssertionError(f"Non-architect runtime audits deviated from gpt-5.4 @ high: {invalid_non_architect}")

    return {
        "workflow_id": workflow_id,
        "workflow_status": workflow["status"],
        "workflow_stage": workflow["current_stage"],
        "ticket_count": len(tickets),
        "compiled_ticket_ids": compiled_ticket_ids,
        "archived_ticket_ids": archived_ticket_ids,
        "architect_ticket_ids": [item["ticket_id"] for item in architect_audits],
        "employee_ids": [str(employee["employee_id"]) for employee in employees],
    }


def run_live_scenario(
    *,
    clean: bool = True,
    max_ticks: int = DEFAULT_MAX_TICKS,
    timeout_sec: int = DEFAULT_TIMEOUT_SEC,
    seed: int = DEFAULT_SCENARIO_SEED,
    scenario_root: Path | None = None,
) -> dict[str, Any]:
    paths = build_scenario_paths(scenario_root)
    base_url, api_key = _require_live_provider_credentials()
    reset_scenario_root(paths, clean=clean)

    started_at = time.monotonic()
    with scenario_environment(paths, base_url=base_url, api_key=api_key, seed=seed):
        with TestClient(create_app()) as client:
            runtime_response = client.post(
                "/api/v1/commands/runtime-provider-upsert",
                json=_runtime_provider_payload(base_url, api_key),
            )
            if runtime_response.status_code != 200 or runtime_response.json()["status"] != "ACCEPTED":
                raise RuntimeError(f"runtime-provider-upsert failed: {runtime_response.text}")

            project_response = client.post(
                "/api/v1/commands/project-init",
                json=_project_init_payload(),
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
                    idempotency_key=f"live-scenario:{workflow_id}:{tick_index}",
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
                    assertions = _assert_scenario_outcome(paths, repository, workflow_id)
                    report = {
                        "success": True,
                        "workflow_id": workflow_id,
                        "scenario_root": str(paths.root),
                        "seed": seed,
                        "ticks_used": tick_index + 1,
                        "elapsed_sec": round(time.monotonic() - started_at, 2),
                        "assertions": assertions,
                    }
                    _write_json(paths.run_report_path, report)
                    return report

                if time.monotonic() - started_at > timeout_sec:
                    snapshot_path = _write_failure_snapshot(paths, repository, workflow_id, label="timeout")
                    raise RuntimeError(f"Scenario timed out. Snapshot: {snapshot_path}")

                if consecutive_stalls >= MAX_STALL_TICKS:
                    snapshot_path = _write_failure_snapshot(paths, repository, workflow_id, label="stall")
                    raise RuntimeError(f"Scenario stalled for {consecutive_stalls} ticks. Snapshot: {snapshot_path}")

                time.sleep(1.05)

            snapshot_path = _write_failure_snapshot(paths, repository, workflow_id, label="max_ticks")
            raise RuntimeError(f"Scenario exceeded max_ticks={max_ticks}. Snapshot: {snapshot_path}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the library management autopilot live scenario.")
    parser.add_argument("--clean", action="store_true", help="Delete and recreate the scenario directory first.")
    parser.add_argument("--max-ticks", type=int, default=DEFAULT_MAX_TICKS)
    parser.add_argument("--timeout-sec", type=int, default=DEFAULT_TIMEOUT_SEC)
    parser.add_argument("--seed", type=int, default=DEFAULT_SCENARIO_SEED)
    parser.add_argument("--scenario-root", type=Path, default=None)
    args = parser.parse_args(argv)

    report = run_live_scenario(
        clean=True,
        max_ticks=args.max_ticks,
        timeout_sec=args.timeout_sec,
        seed=args.seed,
        scenario_root=args.scenario_root,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
