from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest


def _write_runner_config(tmp_path: Path, *, checkpoint_kind: str) -> Path:
    seed_path = tmp_path / "seeds" / checkpoint_kind / "scenario"
    seed_path.mkdir(parents=True, exist_ok=True)
    config_path = tmp_path / "library-management.toml"
    config_path.write_text(
        f"""
[scenario]
scenario_id = "library-management"
display_name = "Library Management Scenario Tests"

[input]
north_star_goal = "实现一个完全匿名、单机运行的极简图书流转终端。"
hard_constraints = ["匿名", "单机", "books 单表"]
read_only_context_refs = []
workflow_profile = "CEO_AUTOPILOT_FINE_GRAINED"
force_requirement_elicitation = false

[runtime]
seed = 17
max_ticks = 4
timeout_sec = 30
maintenance_interval_sec = 1
scheduler_max_dispatches = 20
resume_enabled = true

[layout]
runtime_db = "runtime/state.db"
events_log = "runtime/events.log"
runtime_blobs_dir = "runtime/blobs"
audit_records_dir = "audit/records"
audit_views_dir = "audit/views"
audit_stage_views_dir = "audit/views/stage-views"
workspace_dir_pattern = "workspace/wf_{{workflow_id}}"
workspace_metadata_dir = "workspace/wf_{{workflow_id}}/.metadata"
debug_compile_dir = "debug/compile"
debug_logs_dir = "debug/logs"
runtime_provider_config = "runtime/runtime-provider-config.json"
artifact_uploads_dir = "runtime/blobs/uploads"
ticket_context_archive_dir = "audit/records/nodes/ticket-context-archives"

[provider.default]
provider_id = "prov_default"
base_url = "https://api.example.test/v1"
api_key = "inline-secret"
preferred_model = "gpt-5.4"
max_context_window = 200000
reasoning_effort = "high"
timeout_sec = 480
connect_timeout_sec = 10
write_timeout_sec = 20
first_token_timeout_sec = 300
stream_idle_timeout_sec = 300
request_total_timeout_sec = 480
retry_backoff_schedule_sec = [1, 2, 4]
fallback_provider_ids = []

[[provider.role_bindings]]
target_ref = "ceo_shadow"
provider_model_entry_refs = ["prov_default::gpt-5.4"]
max_context_window_override = 180000
reasoning_effort_override = "xhigh"

[seeds.{checkpoint_kind}]
path = "seeds/{checkpoint_kind}/scenario"
description = "Seed for {checkpoint_kind}"
requires_prepared_state = false

[[stages]]
stage_id = "{checkpoint_kind}"
test_file = "backend/tests/scenario/test_{checkpoint_kind}.py"
seed_ref = "{checkpoint_kind}"
start_mode = "copy_seed"
checkpoint_kind = "{checkpoint_kind}"
expected_stage = "plan"
expected_outputs = ["audit/records/manifest.json", "audit/views/workflow-summary.md", "audit/views/dag-visualization.dot"]
required_schema_refs = ["architecture_brief"]
required_role_types = ["governance_architect"]
""".strip(),
        encoding="utf-8",
    )
    return config_path


def test_run_configured_stage_writes_manifest_timeline_and_views(tmp_path: Path) -> None:
    from tests.scenario._runner import (
        ScenarioApprovalRecord,
        ScenarioCheckpointTicket,
        ScenarioEmployeeRecord,
        ScenarioGraphEdgeRecord,
        ScenarioGraphNodeRecord,
        ScenarioWorkflowSnapshot,
        run_configured_stage,
    )

    config_path = _write_runner_config(tmp_path, checkpoint_kind="requirement_to_architecture")

    class FakeDriver:
        def __init__(self) -> None:
            self.tick_count = 0

        def upsert_runtime_provider(self, payload: dict[str, object]) -> None:
            assert payload["providers"][0]["provider_id"] == "prov_default"

        def ensure_workflow(
            self,
            input_payload: dict[str, object],
            *,
            seed_workflow_id: str | None,
            resume_enabled: bool,
        ) -> str:
            assert input_payload["workflow_profile"] == "CEO_AUTOPILOT_FINE_GRAINED"
            assert resume_enabled is True
            assert seed_workflow_id is None
            return "wf_library_demo"

        def tick(self, workflow_id: str, tick_index: int, *, max_dispatches: int) -> None:
            assert workflow_id == "wf_library_demo"
            assert max_dispatches == 20
            self.tick_count = tick_index + 1

        def auto_advance(self, workflow_id: str, tick_index: int) -> None:
            assert workflow_id == "wf_library_demo"

        def snapshot(self, workflow_id: str) -> ScenarioWorkflowSnapshot:
            tickets = []
            employees = []
            approvals = []
            if self.tick_count >= 1:
                tickets = [
                    ScenarioCheckpointTicket(
                        ticket_id="tkt_architecture_001",
                        node_id="node_ceo_architecture_brief",
                        status="COMPLETED",
                        output_schema_ref="architecture_brief",
                        summary="Locked architecture for the anonymous single-machine books terminal.",
                    )
                ]
                employees = [
                    ScenarioEmployeeRecord(
                        employee_id="emp_architect_001",
                        role_type="governance_architect",
                        board_approved=True,
                    )
                ]
                approvals = [
                    ScenarioApprovalRecord(
                        approval_id="apr_architecture_gate",
                        approval_type="MEETING_ESCALATION",
                        status="APPROVED",
                    )
                ]
            return ScenarioWorkflowSnapshot(
                workflow_id=workflow_id,
                workflow_status="EXECUTING",
                current_stage="plan",
                workflow_profile="CEO_AUTOPILOT_FINE_GRAINED",
                tickets=tickets,
                employees=employees,
                approvals=approvals,
                open_incidents=[],
                graph_nodes=[
                    ScenarioGraphNodeRecord(
                        graph_node_id="graph_architecture",
                        node_id="node_ceo_architecture_brief",
                        output_schema_ref="architecture_brief",
                    )
                ],
                graph_edges=[
                    ScenarioGraphEdgeRecord(
                        source_graph_node_id="graph_architecture",
                        target_graph_node_id="graph_architecture",
                        edge_type="SELF",
                    )
                ],
            )

        def close(self) -> None:
            return None

    result = run_configured_stage(
        config_path,
        "requirement_to_architecture",
        run_root=tmp_path / "runs",
        driver_factory=lambda _runtime: FakeDriver(),
    )

    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert result.success is True
    assert manifest["stage_id"] == "requirement_to_architecture"
    assert manifest["workflow_id"] == "wf_library_demo"
    assert result.summary_path.exists()
    assert result.dag_path.exists()
    assert any(result.timeline_dir.iterdir())
    assert (result.scenario_root / "runtime" / "events.log").exists()


def test_parallel_git_fanout_merge_checkpoint_requires_merged_branches_and_closeout(tmp_path: Path) -> None:
    from tests.scenario._runner import (
        ScenarioCheckpointTicket,
        ScenarioGraphNodeRecord,
        ScenarioWorkflowSnapshot,
        evaluate_stage_checkpoint,
    )

    config_path = _write_runner_config(tmp_path, checkpoint_kind="parallel_git_fanout_merge")

    from tests.scenario._config import load_scenario_test_config

    config = load_scenario_test_config(config_path)
    stage = config.stages["parallel_git_fanout_merge"]
    stage = stage.with_updates(
        expected_stage="closeout",
        required_node_ids=("books_query", "books_commands", "terminal_shell"),
        required_schema_refs=("delivery_closeout_package",),
        required_role_types=(),
    )

    snapshot = ScenarioWorkflowSnapshot(
        workflow_id="wf_parallel",
        workflow_status="COMPLETED",
        current_stage="closeout",
        workflow_profile="CEO_AUTOPILOT_FINE_GRAINED",
        tickets=[
            ScenarioCheckpointTicket(
                ticket_id="tkt_books_query",
                node_id="books_query",
                status="COMPLETED",
                output_schema_ref="source_code_delivery",
                git_branch_ref="codex/books-query",
                git_merge_status="MERGED",
                summary="books query delivery",
            ),
            ScenarioCheckpointTicket(
                ticket_id="tkt_books_commands",
                node_id="books_commands",
                status="COMPLETED",
                output_schema_ref="source_code_delivery",
                git_branch_ref="codex/books-commands",
                git_merge_status="MERGED",
                summary="books commands delivery",
            ),
            ScenarioCheckpointTicket(
                ticket_id="tkt_terminal_shell",
                node_id="terminal_shell",
                status="COMPLETED",
                output_schema_ref="source_code_delivery",
                git_branch_ref="codex/terminal-shell",
                git_merge_status="MERGED",
                summary="terminal shell delivery",
            ),
            ScenarioCheckpointTicket(
                ticket_id="tkt_closeout",
                node_id="node_ceo_delivery_closeout",
                status="COMPLETED",
                output_schema_ref="delivery_closeout_package",
                summary="closeout package",
            ),
        ],
        employees=[],
        approvals=[],
        open_incidents=[],
        graph_nodes=[
            ScenarioGraphNodeRecord(graph_node_id="books_query", node_id="books_query"),
            ScenarioGraphNodeRecord(graph_node_id="books_commands", node_id="books_commands"),
            ScenarioGraphNodeRecord(graph_node_id="terminal_shell", node_id="terminal_shell"),
        ],
        graph_edges=[],
    )

    checkpoint = evaluate_stage_checkpoint(stage, snapshot)

    assert checkpoint.matched is True
    assert checkpoint.reason == "parallel_git_fanout_merge_ready"
    assert checkpoint.details["merged_branch_count"] == 3


def test_run_configured_stage_requires_timeline_manifest_and_dag_outputs(tmp_path: Path) -> None:
    from tests.scenario._runner import verify_expected_outputs

    scenario_root = tmp_path / "scenario"
    (scenario_root / "audit" / "records").mkdir(parents=True, exist_ok=True)
    (scenario_root / "audit" / "views").mkdir(parents=True, exist_ok=True)

    missing = verify_expected_outputs(
        scenario_root=scenario_root,
        expected_outputs=(
            "audit/records/manifest.json",
            "audit/views/workflow-summary.md",
            "audit/views/dag-visualization.dot",
        ),
    )

    assert missing == [
        "audit/records/manifest.json",
        "audit/views/workflow-summary.md",
        "audit/views/dag-visualization.dot",
    ]


def test_book_module_build_review_checkpoint_requires_git_gate_and_branch_ref(tmp_path: Path) -> None:
    from tests.scenario._runner import (
        ScenarioCheckpointTicket,
        ScenarioWorkflowSnapshot,
        evaluate_stage_checkpoint,
    )

    config_path = _write_runner_config(tmp_path, checkpoint_kind="book_module_build_review")

    from tests.scenario._config import load_scenario_test_config

    config = load_scenario_test_config(config_path)
    stage = config.stages["book_module_build_review"].with_updates(
        expected_stage="review",
        required_schema_refs=(),
        required_summary_terms=("books",),
        required_role_types=(),
    )
    snapshot = ScenarioWorkflowSnapshot(
        workflow_id="wf_review_gate",
        workflow_status="EXECUTING",
        current_stage="review",
        workflow_profile="CEO_AUTOPILOT_FINE_GRAINED",
        tickets=[
            ScenarioCheckpointTicket(
                ticket_id="tkt_build_001",
                node_id="books_query",
                status="COMPLETED",
                output_schema_ref="source_code_delivery",
                git_branch_ref=None,
                git_merge_status="PENDING_REVIEW_GATE",
                summary="books query delivery",
            )
        ],
        employees=[],
        approvals=[],
        open_incidents=[],
        graph_nodes=[],
        graph_edges=[],
    )

    checkpoint = evaluate_stage_checkpoint(stage, snapshot)

    assert checkpoint.matched is False
    assert checkpoint.reason == "book_module_build_review_missing_git_gate"


def test_closeout_mainline_merge_checkpoint_requires_merged_branch_ref(tmp_path: Path) -> None:
    from tests.scenario._runner import (
        ScenarioCheckpointTicket,
        ScenarioWorkflowSnapshot,
        evaluate_stage_checkpoint,
    )

    config_path = _write_runner_config(tmp_path, checkpoint_kind="closeout_mainline_merge")

    from tests.scenario._config import load_scenario_test_config

    config = load_scenario_test_config(config_path)
    stage = config.stages["closeout_mainline_merge"].with_updates(
        expected_stage="closeout",
        required_schema_refs=("delivery_closeout_package",),
        required_role_types=(),
    )
    snapshot = ScenarioWorkflowSnapshot(
        workflow_id="wf_closeout_missing_branch",
        workflow_status="COMPLETED",
        current_stage="closeout",
        workflow_profile="CEO_AUTOPILOT_FINE_GRAINED",
        tickets=[
            ScenarioCheckpointTicket(
                ticket_id="tkt_build_001",
                node_id="books_query",
                status="COMPLETED",
                output_schema_ref="source_code_delivery",
                git_branch_ref=None,
                git_merge_status="MERGED",
                summary="books query delivery",
            ),
            ScenarioCheckpointTicket(
                ticket_id="tkt_closeout_001",
                node_id="node_closeout_001",
                status="COMPLETED",
                output_schema_ref="delivery_closeout_package",
                summary="closeout package",
            ),
        ],
        employees=[],
        approvals=[],
        open_incidents=[],
        graph_nodes=[],
        graph_edges=[],
    )

    checkpoint = evaluate_stage_checkpoint(stage, snapshot)

    assert checkpoint.matched is False
    assert checkpoint.reason == "closeout_mainline_merge_missing_branch_ref"


def test_validate_seed_for_stage_rejects_prepared_seed_without_manifest(tmp_path: Path) -> None:
    from tests.scenario._config import load_scenario_test_config
    from tests.scenario._runner import _build_runtime_paths, validate_seed_for_stage

    config_path = _write_runner_config(tmp_path, checkpoint_kind="closeout_mainline_merge")
    config = load_scenario_test_config(config_path)
    seed = replace(config.seeds["closeout_mainline_merge"], requires_prepared_state=True)
    seed_root = seed.path
    (seed_root / "runtime").mkdir(parents=True, exist_ok=True)
    (seed_root / "runtime" / "state.db").write_text("db", encoding="utf-8")
    (
        seed_root
        / "workspace"
        / "wf_seed_demo"
        / "00-boardroom"
        / "workflow"
        / "workspace-manifest.json"
    ).parent.mkdir(parents=True, exist_ok=True)
    (
        seed_root
        / "workspace"
        / "wf_seed_demo"
        / "00-boardroom"
        / "workflow"
        / "workspace-manifest.json"
    ).write_text("{}", encoding="utf-8")

    runtime_paths = _build_runtime_paths(config, seed_root)

    with pytest.raises(RuntimeError, match="seed-manifest.json"):
        validate_seed_for_stage(
            config,
            config.stages["closeout_mainline_merge"],
            seed.with_updates(workflow_id="wf_seed_demo") if hasattr(seed, "with_updates") else seed,
            runtime_paths,
        )


def test_validate_seed_for_stage_uses_manifest_workflow_id_for_stage06_snapshot_checks(tmp_path: Path) -> None:
    from tests.scenario._config import load_scenario_test_config
    from tests.scenario._runner import (
        _build_runtime_paths,
        ScenarioCheckpointTicket,
        ScenarioGraphNodeRecord,
        ScenarioWorkflowSnapshot,
        validate_seed_for_stage,
    )

    config_path = _write_runner_config(tmp_path, checkpoint_kind="parallel_git_fanout_merge")
    config = load_scenario_test_config(config_path)
    seed = replace(config.seeds["parallel_git_fanout_merge"], requires_prepared_state=True)
    stage = config.stages["parallel_git_fanout_merge"].with_updates(
        expected_stage="review",
        required_node_ids=("books_query", "books_commands", "terminal_shell"),
        required_schema_refs=(),
        required_role_types=(),
    )
    seed_root = seed.path
    (seed_root / "runtime").mkdir(parents=True, exist_ok=True)
    (seed_root / "runtime" / "state.db").write_text("db", encoding="utf-8")
    (seed_root / "seed-manifest.json").write_text(
        json.dumps(
            {
                "seed_id": "parallel_git_fanout_merge",
                "workflow_id": "wf_stage06_seed",
                "workflow_status": "EXECUTING",
                "current_stage": "review",
            }
        ),
        encoding="utf-8",
    )
    (
        seed_root
        / "workspace"
        / "wf_stage06_seed"
        / "00-boardroom"
        / "workflow"
        / "workspace-manifest.json"
    ).parent.mkdir(parents=True, exist_ok=True)
    (
        seed_root
        / "workspace"
        / "wf_stage06_seed"
        / "00-boardroom"
        / "workflow"
        / "workspace-manifest.json"
    ).write_text("{}", encoding="utf-8")
    receipt_root = (
        seed_root
        / "workspace"
        / "wf_stage06_seed"
        / "00-boardroom"
        / "tickets"
    )
    context_root = seed_root / "audit" / "records" / "nodes" / "ticket-context-archives"
    for ticket_id in ("tkt_books_query", "tkt_books_commands", "tkt_terminal_shell"):
        dossier = receipt_root / ticket_id / "hook-receipts"
        dossier.mkdir(parents=True, exist_ok=True)
        (dossier / "worktree-checkout.json").write_text("{}", encoding="utf-8")
        (dossier / "git-closeout.json").write_text("{}", encoding="utf-8")
        context_root.mkdir(parents=True, exist_ok=True)
        (context_root / f"{ticket_id}.md").write_text("# context\n", encoding="utf-8")

    runtime_paths = _build_runtime_paths(config, seed_root)
    snapshot = ScenarioWorkflowSnapshot(
        workflow_id="wf_stage06_seed",
        workflow_status="EXECUTING",
        current_stage="review",
        workflow_profile="CEO_AUTOPILOT_FINE_GRAINED",
        tickets=[
            ScenarioCheckpointTicket(
                ticket_id="tkt_books_query",
                node_id="books_query",
                status="COMPLETED",
                output_schema_ref="source_code_delivery",
                git_branch_ref="codex/books-query",
                git_merge_status="MERGED",
                summary="books query delivery",
            ),
            ScenarioCheckpointTicket(
                ticket_id="tkt_books_commands",
                node_id="books_commands",
                status="COMPLETED",
                output_schema_ref="source_code_delivery",
                git_branch_ref="codex/books-commands",
                git_merge_status="MERGED",
                summary="books commands delivery",
            ),
            ScenarioCheckpointTicket(
                ticket_id="tkt_terminal_shell",
                node_id="terminal_shell",
                status="COMPLETED",
                output_schema_ref="source_code_delivery",
                git_branch_ref="codex/terminal-shell",
                git_merge_status="MERGED",
                summary="terminal shell delivery",
            ),
        ],
        employees=[],
        approvals=[],
        open_incidents=[],
        graph_nodes=[
            ScenarioGraphNodeRecord(graph_node_id="books_query", node_id="books_query"),
            ScenarioGraphNodeRecord(graph_node_id="books_commands", node_id="books_commands"),
            ScenarioGraphNodeRecord(graph_node_id="terminal_shell", node_id="terminal_shell"),
        ],
        graph_edges=[],
    )

    workflow_id = validate_seed_for_stage(
        config,
        stage,
        seed,
        runtime_paths,
        snapshot=snapshot,
    )

    assert workflow_id == "wf_stage06_seed"


def test_app_scenario_driver_rejects_empty_provider_api_key_before_request(tmp_path: Path) -> None:
    from tests.scenario._config import load_scenario_test_config
    from tests.scenario._runner import AppScenarioDriver, _build_runtime_paths

    config_path = _write_runner_config(tmp_path, checkpoint_kind="requirement_to_architecture")
    config = load_scenario_test_config(config_path)
    runtime_paths = _build_runtime_paths(config, tmp_path / "scenario")
    driver = AppScenarioDriver(runtime_paths, config)
    payload = config.build_runtime_provider_payload()
    payload["providers"][0]["api_key"] = ""

    with pytest.raises(RuntimeError, match="SCENARIO_TEST_KEY|api_key"):
        driver.upsert_runtime_provider(payload)
