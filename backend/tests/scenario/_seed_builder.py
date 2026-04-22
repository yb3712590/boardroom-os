from __future__ import annotations

import argparse
import os
import re
import tempfile
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from app.main import create_app
from app.core.project_workspaces import (
    finalize_workspace_ticket_git_status,
    merge_ticket_branch_into_main,
    update_git_closeout_status,
)
from tests.scenario._config import ScenarioTestConfig, load_scenario_test_config
from tests.scenario._runner import (
    AppScenarioDriver,
    _build_runtime_paths,
    run_configured_stage,
)
from tests.scenario._seed_copy import freeze_scenario_as_seed

import tests.test_api as api_test_helpers


DEFAULT_STAGE06_SEED_ID = "stage_06_parallel_git_fanout_merge"
CAPTURE_STAGE_TO_SEED = {
    "stage_01_requirement_to_architecture": "stage_02_outline_to_detailed_design",
    "stage_02_outline_to_detailed_design": "stage_03_detailed_design_to_backlog",
    "stage_03_detailed_design_to_backlog": "stage_04_book_module_build_review",
    "stage_04_book_module_build_review": "stage_05_closeout_mainline_merge",
}


def update_seed_workflow_id_in_config(
    config_path: Path,
    *,
    seed_id: str,
    workflow_id: str,
) -> None:
    body = config_path.read_text(encoding="utf-8")
    section_pattern = re.compile(
        rf"(?ms)(^\[seeds\.{re.escape(seed_id)}\]\n)(.*?)(?=^\[seeds\.|^\[\[stages\]\]|\Z)"
    )
    match = section_pattern.search(body)
    if match is None:
        raise ValueError(f"Seed section `seeds.{seed_id}` is missing from {config_path}.")

    section_header = match.group(1)
    section_body = match.group(2)
    workflow_line = f'workflow_id = "{workflow_id}"\n'
    if re.search(r"(?m)^workflow_id\s*=", section_body):
        updated_body = re.sub(
            r'(?m)^workflow_id\s*=\s*".*?"\s*$',
            workflow_line.rstrip(),
            section_body,
        )
        if not updated_body.endswith("\n"):
            updated_body += "\n"
    else:
        updated_body = section_body
        if updated_body and not updated_body.endswith("\n"):
            updated_body += "\n"
        updated_body += workflow_line

    config_path.write_text(
        body[: match.start()] + section_header + updated_body + body[match.end() :],
        encoding="utf-8",
    )


def _latest_workflow_id(repository) -> str:
    workflows = repository.list_workflow_projections()
    if not workflows:
        raise RuntimeError("Scenario runtime does not contain any workflow projections to freeze.")
    ordered = sorted(
        workflows,
        key=lambda item: (
            str(item.get("updated_at") or ""),
            str(item.get("workflow_id") or ""),
        ),
    )
    return str(ordered[-1]["workflow_id"])


def _collect_seed_snapshot_metadata(
    config: ScenarioTestConfig,
    *,
    scenario_root: Path,
    workflow_id: str | None = None,
) -> dict[str, Any]:
    runtime_paths = _build_runtime_paths(config, scenario_root)
    if not runtime_paths.db_path.exists():
        return {
            "workflow_id": workflow_id,
            "workflow_status": "BOOTSTRAP",
            "current_stage": "bootstrap",
            "output_schema_refs": (),
            "graph_node_ids": (),
            "source_delivery_git": (),
        }

    with AppScenarioDriver(runtime_paths, config) as driver:
        resolved_workflow_id = workflow_id or _latest_workflow_id(driver.repository)
        snapshot = driver.snapshot(resolved_workflow_id)
    output_schema_refs = tuple(
        sorted(
            {
                str(ticket.output_schema_ref or "").strip()
                for ticket in snapshot.tickets
                if str(ticket.output_schema_ref or "").strip()
            }
        )
    )
    graph_node_ids = tuple(
        sorted(
            {
                str(node.graph_node_id or "").strip()
                for node in snapshot.graph_nodes
                if str(node.graph_node_id or "").strip()
            }
            | {
                str(node.node_id or "").strip()
                for node in snapshot.graph_nodes
                if str(node.node_id or "").strip()
            }
        )
    )
    source_delivery_git = tuple(
        {
            "ticket_id": ticket.ticket_id,
            "node_id": ticket.node_id,
            "branch_ref": ticket.git_branch_ref,
            "merge_status": ticket.git_merge_status,
        }
        for ticket in snapshot.tickets
        if ticket.output_schema_ref == "source_code_delivery"
    )
    return {
        "workflow_id": snapshot.workflow_id,
        "workflow_status": snapshot.workflow_status,
        "current_stage": snapshot.current_stage,
        "output_schema_refs": output_schema_refs,
        "graph_node_ids": graph_node_ids,
        "source_delivery_git": source_delivery_git,
    }


def _freeze_seed(
    config: ScenarioTestConfig,
    *,
    source_root: Path,
    seed_id: str,
    captured_from_stage_id: str | None,
    workflow_id: str | None = None,
    update_config: bool = True,
) -> Path:
    if seed_id not in config.seeds:
        raise ValueError(f"Unknown seed `{seed_id}`.")
    seed = config.seeds[seed_id]
    metadata = _collect_seed_snapshot_metadata(config, scenario_root=source_root, workflow_id=workflow_id)
    manifest_path = freeze_scenario_as_seed(
        source_root=source_root,
        destination_root=seed.path,
        layout=config.layout,
        seed_id=seed_id,
        captured_from_stage_id=captured_from_stage_id,
        workflow_id=metadata["workflow_id"],
        workflow_status=metadata["workflow_status"],
        current_stage=metadata["current_stage"],
        output_schema_refs=metadata["output_schema_refs"],
        graph_node_ids=metadata["graph_node_ids"],
        source_delivery_git=metadata["source_delivery_git"],
    )
    if update_config and metadata["workflow_id"]:
        update_seed_workflow_id_in_config(
            config.config_path,
            seed_id=seed_id,
            workflow_id=str(metadata["workflow_id"]),
        )
    return manifest_path


def _workspace_source_create_payload(
    *,
    workflow_id: str,
    ticket_id: str,
    node_id: str,
    parent_ticket_id: str | None,
    summary: str,
) -> dict[str, Any]:
    return api_test_helpers._ticket_create_payload(
        workflow_id=workflow_id,
        ticket_id=ticket_id,
        node_id=node_id,
        parent_ticket_id=parent_ticket_id,
        role_profile_ref="frontend_engineer_primary",
        output_schema_ref="source_code_delivery",
        delivery_stage="BUILD",
        allowed_tools=["read_artifact", "write_artifact"],
        allowed_write_set=[
            "10-project/src/*",
            "10-project/docs/*",
            "20-evidence/tests/*",
            "20-evidence/git/*",
        ],
        input_artifact_refs=["art://inputs/brief.md"],
        acceptance_criteria=[summary],
    )


def _workspace_source_result_payload(
    *,
    workflow_id: str,
    ticket_id: str,
    node_id: str,
    summary: str,
) -> dict[str, Any]:
    source_file_ref = f"art://workspace/{ticket_id}/source.ts"
    verification_ref = f"art://workspace/{ticket_id}/test-report.json"
    verification_path = f"20-evidence/tests/{ticket_id}/attempt-1/test-report.json"
    payload = {
        "summary": summary,
        "source_file_refs": [source_file_ref],
        "source_files": [
            {
                "artifact_ref": source_file_ref,
                "path": f"10-project/src/{ticket_id}.ts",
                "content": f"export const {ticket_id} = true;\n",
            }
        ],
        "verification_runs": [
            {
                "artifact_ref": verification_ref,
                "path": verification_path,
                "runner": "pytest",
                "command": "pytest backend/tests/test_scenario_runner.py -q",
                "status": "passed",
                "exit_code": 0,
                "duration_sec": 0.8,
                "stdout": "collected 1 item\\n\\n1 passed in 0.08s\\n",
                "stderr": "",
                "discovered_count": 1,
                "passed_count": 1,
                "failed_count": 0,
                "skipped_count": 0,
                "failures": [],
            }
        ],
        "implementation_notes": [summary],
        "documentation_updates": [
            {
                "doc_ref": "10-project/docs/tracking/active-tasks.md",
                "status": "UPDATED",
                "summary": f"Recorded implementation status for {ticket_id}.",
            }
        ],
    }
    return {
        "workflow_id": workflow_id,
        "ticket_id": ticket_id,
        "node_id": node_id,
        "submitted_by": "emp_frontend_2",
        "result_status": "completed",
        "schema_version": "source_code_delivery_v1",
        "payload": payload,
        "artifact_refs": [],
        "written_artifacts": [
            {
                "path": f"10-project/src/{ticket_id}.ts",
                "artifact_ref": source_file_ref,
                "kind": "TEXT",
                "content_text": f"export const {ticket_id} = true;\n",
            },
            {
                "path": f"10-project/docs/tracking/{ticket_id}-active.md",
                "artifact_ref": f"art://workspace/{ticket_id}/active-task.md",
                "kind": "TEXT",
                "content_text": "Updated active task summary.\n",
            },
            {
                "path": verification_path,
                "artifact_ref": verification_ref,
                "kind": "JSON",
                "content_json": payload["verification_runs"][0],
            },
            {
                "path": f"20-evidence/git/{ticket_id}/attempt-1/git-closeout.json",
                "artifact_ref": f"art://workspace/{ticket_id}/git-closeout.json",
                "kind": "JSON",
                "content_json": {"commit_sha": "abc1234", "branch_ref": f"codex/{ticket_id}"},
            },
        ],
        "verification_evidence_refs": [verification_ref],
        "git_commit_record": {
            "commit_sha": "abc1234",
            "branch_ref": f"codex/{ticket_id}",
            "merge_status": "PENDING_REVIEW_GATE",
        },
        "assumptions": ["Parallel git fanout seed uses workspace-managed source delivery tickets."],
        "issues": [],
        "confidence": 0.9,
        "needs_escalation": False,
        "summary": summary,
        "failure_kind": None,
        "failure_message": None,
        "failure_detail": None,
        "idempotency_key": f"ticket-result-submit:{workflow_id}:{ticket_id}:source-code-delivery",
    }


def _handle_freeze_run(args: argparse.Namespace) -> int:
    config = load_scenario_test_config(args.config_path)
    _freeze_seed(
        config,
        source_root=args.source_root,
        seed_id=args.seed_id,
        captured_from_stage_id=args.captured_from_stage_id,
        workflow_id=args.workflow_id,
        update_config=not args.skip_config_update,
    )
    return 0


def _handle_capture_stage(args: argparse.Namespace) -> int:
    config = load_scenario_test_config(args.config_path)
    target_seed_id = args.seed_id or CAPTURE_STAGE_TO_SEED.get(args.stage_id)
    if not target_seed_id:
        raise ValueError(f"Stage `{args.stage_id}` does not have a default capture target seed.")
    result = run_configured_stage(
        args.config_path,
        args.stage_id,
        run_root=args.run_root,
    )
    _freeze_seed(
        config,
        source_root=result.scenario_root,
        seed_id=target_seed_id,
        captured_from_stage_id=args.stage_id,
        workflow_id=result.workflow_id,
        update_config=not args.skip_config_update,
    )
    return 0


def _handle_build_stage06(args: argparse.Namespace) -> int:
    config = load_scenario_test_config(args.config_path)
    seed_id = args.seed_id or DEFAULT_STAGE06_SEED_ID
    with tempfile.TemporaryDirectory() as tmp_dir:
        scenario_root = Path(tmp_dir) / "scenario"
        runtime_paths = _build_runtime_paths(config, scenario_root)
        runtime_paths.db_path.parent.mkdir(parents=True, exist_ok=True)
        runtime_paths.runtime_blobs_root.mkdir(parents=True, exist_ok=True)
        runtime_paths.artifact_uploads_root.mkdir(parents=True, exist_ok=True)
        runtime_paths.ticket_context_archive_root.mkdir(parents=True, exist_ok=True)
        runtime_paths.debug_compile_root.mkdir(parents=True, exist_ok=True)

        env_overrides = {
            "BOARDROOM_OS_DB_PATH": str(runtime_paths.db_path),
            "BOARDROOM_OS_RUNTIME_PROVIDER_CONFIG_PATH": str(runtime_paths.runtime_provider_config_path),
            "BOARDROOM_OS_ARTIFACT_STORE_ROOT": str(runtime_paths.runtime_blobs_root),
            "BOARDROOM_OS_ARTIFACT_UPLOAD_STAGING_ROOT": str(runtime_paths.artifact_uploads_root),
            "BOARDROOM_OS_TICKET_CONTEXT_ARCHIVE_ROOT": str(runtime_paths.ticket_context_archive_root),
            "BOARDROOM_OS_PROJECT_WORKSPACE_ROOT": str(runtime_paths.project_workspace_root),
            "BOARDROOM_OS_DEVELOPER_INSPECTOR_ROOT": str(runtime_paths.debug_compile_root),
        }
        previous_env = {key: os.environ.get(key) for key in env_overrides}
        for key, value in env_overrides.items():
            os.environ[key] = value
        try:
            with TestClient(create_app()) as client:
                init_response = client.post(
                    "/api/v1/commands/project-init",
                    json=config.build_project_init_payload(),
                )
                if init_response.status_code != 200 or init_response.json().get("status") != "ACCEPTED":
                    raise RuntimeError(f"project-init failed while building stage06 seed: {init_response.text}")
                workflow_id = str(init_response.json()["causation_hint"]).split(":", 1)[1]

                repository = client.app.state.repository
                backlog_ticket_id = "tkt_stage06_parallel_parent"
                parallel_nodes = (
                    ("tkt_books_query", "books_query", "books query slice"),
                    ("tkt_books_commands", "books_commands", "books commands slice"),
                    ("tkt_terminal_shell", "terminal_shell", "terminal shell slice"),
                )
                for ticket_id, node_id, summary in parallel_nodes:
                    create_response = client.post(
                        "/api/v1/commands/ticket-create",
                        json=_workspace_source_create_payload(
                            workflow_id=workflow_id,
                            ticket_id=ticket_id,
                            node_id=node_id,
                            parent_ticket_id=backlog_ticket_id,
                            summary=summary,
                        ),
                    )
                    if create_response.status_code != 200 or create_response.json().get("status") != "ACCEPTED":
                        raise RuntimeError(f"ticket-create failed for {ticket_id}: {create_response.text}")
                    client.post(
                        "/api/v1/commands/ticket-lease",
                        json=api_test_helpers._ticket_lease_payload(
                            workflow_id=workflow_id,
                            ticket_id=ticket_id,
                            node_id=node_id,
                            leased_by="emp_frontend_2",
                        ),
                    )
                    client.post(
                        "/api/v1/commands/ticket-start",
                        json=api_test_helpers._ticket_start_payload(
                            workflow_id=workflow_id,
                            ticket_id=ticket_id,
                            node_id=node_id,
                            started_by="emp_frontend_2",
                        ),
                    )
                    submit_response = client.post(
                        "/api/v1/commands/ticket-result-submit",
                        json=_workspace_source_result_payload(
                            workflow_id=workflow_id,
                            ticket_id=ticket_id,
                            node_id=node_id,
                            summary=summary,
                        ),
                    )
                    if submit_response.status_code != 200 or submit_response.json().get("status") != "ACCEPTED":
                        raise RuntimeError(f"ticket-result-submit failed for {ticket_id}: {submit_response.text}")
                    with repository.connection() as connection:
                        created_spec = repository.get_latest_ticket_created_payload(connection, ticket_id) or {}
                    try:
                        merge_ticket_branch_into_main(
                            workflow_id=workflow_id,
                            ticket_id=ticket_id,
                            git_branch_ref=str(created_spec.get("git_branch_ref") or f"codex/{ticket_id}"),
                        )
                        finalize_workspace_ticket_git_status(
                            workflow_id=workflow_id,
                            ticket_id=ticket_id,
                            created_spec=created_spec,
                            merge_status="MERGED",
                        )
                    except Exception:
                        update_git_closeout_status(
                            workflow_id=workflow_id,
                            ticket_id=ticket_id,
                            git_branch_ref=str(created_spec.get("git_branch_ref") or f"codex/{ticket_id}"),
                            merge_status="MERGED",
                        )

                with repository.transaction() as connection:
                    connection.execute(
                        """
                        UPDATE workflow_projection
                        SET current_stage = 'review', status = 'EXECUTING'
                        WHERE workflow_id = ?
                        """,
                        (workflow_id,),
                    )

            _freeze_seed(
                config,
                source_root=scenario_root,
                seed_id=seed_id,
                captured_from_stage_id="build-stage06",
                workflow_id=workflow_id,
                update_config=not args.skip_config_update,
            )
        finally:
            for key, value in previous_env.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Scenario seed capture and freeze helpers.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    freeze_parser = subparsers.add_parser("freeze-run", help="Freeze an existing scenario run directory into a seed.")
    freeze_parser.add_argument("--config-path", type=Path, required=True)
    freeze_parser.add_argument("--source-root", type=Path, required=True)
    freeze_parser.add_argument("--seed-id", required=True)
    freeze_parser.add_argument("--captured-from-stage-id")
    freeze_parser.add_argument("--workflow-id")
    freeze_parser.add_argument("--skip-config-update", action="store_true")
    freeze_parser.set_defaults(handler=_handle_freeze_run)

    capture_parser = subparsers.add_parser("capture-stage", help="Run a stage and freeze its resulting scenario root.")
    capture_parser.add_argument("--config-path", type=Path, required=True)
    capture_parser.add_argument("--stage-id", required=True)
    capture_parser.add_argument("--seed-id")
    capture_parser.add_argument("--run-root", type=Path)
    capture_parser.add_argument("--skip-config-update", action="store_true")
    capture_parser.set_defaults(handler=_handle_capture_stage)

    stage06_parser = subparsers.add_parser(
        "build-stage06",
        help="Build the specialized stage06 parallel git fanout seed and freeze it.",
    )
    stage06_parser.add_argument("--config-path", type=Path, required=True)
    stage06_parser.add_argument("--seed-id", default=DEFAULT_STAGE06_SEED_ID)
    stage06_parser.add_argument("--skip-config-update", action="store_true")
    stage06_parser.set_defaults(handler=_handle_build_stage06)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.config_path = args.config_path.resolve()
    if hasattr(args, "source_root") and args.source_root is not None:
        args.source_root = args.source_root.resolve()
    if hasattr(args, "run_root") and args.run_root is not None:
        args.run_root = args.run_root.resolve()
    return int(args.handler(args))


if __name__ == "__main__":
    raise SystemExit(main())
