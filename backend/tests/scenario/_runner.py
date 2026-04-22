from __future__ import annotations

import json
import os
import time
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol
from uuid import uuid4

from fastapi.testclient import TestClient

from app.core.ticket_graph import build_ticket_graph_snapshot
from app.core.workflow_auto_advance import auto_advance_workflow_to_next_stop
from app.main import create_app
from app.scheduler_runner import run_scheduler_once
from tests.scenario._config import (
    ScenarioStageSpec,
    ScenarioTestConfig,
    load_scenario_test_config,
)
from tests.scenario._seed_copy import (
    SEED_MANIFEST_FILENAME,
    ensure_layout_directories,
    load_seed_manifest,
    prepare_seeded_scenario,
)


BACKEND_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_ENV = "BOARDROOM_OS_SCENARIO_TEST_CONFIG_PATH"


@dataclass(frozen=True)
class ScenarioCheckpointTicket:
    ticket_id: str
    node_id: str
    status: str
    output_schema_ref: str | None = None
    git_branch_ref: str | None = None
    git_merge_status: str | None = None
    summary: str = ""


@dataclass(frozen=True)
class ScenarioEmployeeRecord:
    employee_id: str
    role_type: str
    board_approved: bool = False


@dataclass(frozen=True)
class ScenarioApprovalRecord:
    approval_id: str
    approval_type: str
    status: str


@dataclass(frozen=True)
class ScenarioIncidentRecord:
    incident_id: str
    incident_type: str
    status: str


@dataclass(frozen=True)
class ScenarioGraphNodeRecord:
    graph_node_id: str
    node_id: str
    output_schema_ref: str | None = None
    ticket_id: str | None = None


@dataclass(frozen=True)
class ScenarioGraphEdgeRecord:
    source_graph_node_id: str
    target_graph_node_id: str
    edge_type: str


@dataclass(frozen=True)
class ScenarioWorkflowSnapshot:
    workflow_id: str
    workflow_status: str
    current_stage: str
    workflow_profile: str
    tickets: list[ScenarioCheckpointTicket] = field(default_factory=list)
    employees: list[ScenarioEmployeeRecord] = field(default_factory=list)
    approvals: list[ScenarioApprovalRecord] = field(default_factory=list)
    open_incidents: list[ScenarioIncidentRecord] = field(default_factory=list)
    graph_nodes: list[ScenarioGraphNodeRecord] = field(default_factory=list)
    graph_edges: list[ScenarioGraphEdgeRecord] = field(default_factory=list)


@dataclass(frozen=True)
class ScenarioCheckpointResult:
    matched: bool
    reason: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ScenarioStageRunResult:
    success: bool
    stage_id: str
    workflow_id: str
    scenario_root: Path
    manifest_path: Path
    summary_path: Path
    dag_path: Path
    timeline_dir: Path


@dataclass(frozen=True)
class ScenarioRuntimePaths:
    scenario_root: Path
    db_path: Path
    events_log_path: Path
    runtime_provider_config_path: Path
    runtime_blobs_root: Path
    artifact_uploads_root: Path
    audit_records_root: Path
    audit_timeline_root: Path
    audit_nodes_root: Path
    audit_incidents_root: Path
    audit_views_root: Path
    audit_stage_views_root: Path
    debug_compile_root: Path
    debug_logs_root: Path
    ticket_context_archive_root: Path
    project_workspace_root: Path


class ScenarioDriver(Protocol):
    def upsert_runtime_provider(self, payload: dict[str, Any]) -> None: ...

    def ensure_workflow(
        self,
        input_payload: dict[str, Any],
        *,
        seed_workflow_id: str | None,
        resume_enabled: bool,
    ) -> str: ...

    def tick(self, workflow_id: str, tick_index: int, *, max_dispatches: int) -> None: ...

    def auto_advance(self, workflow_id: str, tick_index: int) -> None: ...

    def snapshot(self, workflow_id: str) -> ScenarioWorkflowSnapshot: ...

    def close(self) -> None: ...


class AppScenarioDriver(AbstractContextManager["AppScenarioDriver"]):
    def __init__(self, runtime_paths: ScenarioRuntimePaths, config: ScenarioTestConfig) -> None:
        self._runtime_paths = runtime_paths
        self._config = config
        self._previous_env: dict[str, str | None] = {}
        self._client: TestClient | None = None
        self._repository = None

    def __enter__(self) -> "AppScenarioDriver":
        overrides = {
            "BOARDROOM_OS_DB_PATH": str(self._runtime_paths.db_path),
            "BOARDROOM_OS_RUNTIME_PROVIDER_CONFIG_PATH": str(
                self._runtime_paths.runtime_provider_config_path
            ),
            "BOARDROOM_OS_ARTIFACT_STORE_ROOT": str(self._runtime_paths.runtime_blobs_root),
            "BOARDROOM_OS_ARTIFACT_UPLOAD_STAGING_ROOT": str(self._runtime_paths.artifact_uploads_root),
            "BOARDROOM_OS_DEVELOPER_INSPECTOR_ROOT": str(self._runtime_paths.debug_compile_root),
            "BOARDROOM_OS_TICKET_CONTEXT_ARCHIVE_ROOT": str(
                self._runtime_paths.ticket_context_archive_root
            ),
            "BOARDROOM_OS_PROJECT_WORKSPACE_ROOT": str(self._runtime_paths.project_workspace_root),
            "BOARDROOM_OS_RUNTIME_EXECUTION_MODE": "INPROCESS",
            "BOARDROOM_OS_CEO_MAINTENANCE_INTERVAL_SEC": str(
                self._config.runtime.maintenance_interval_sec
            ),
            "BOARDROOM_OS_PROVIDER_OPENAI_COMPAT_BASE_URL": self._config.provider.base_url,
            "BOARDROOM_OS_PROVIDER_OPENAI_COMPAT_API_KEY": str(self._config.provider.api_key or ""),
            "BOARDROOM_OS_PROVIDER_OPENAI_COMPAT_MODEL": self._config.provider.preferred_model,
            "BOARDROOM_OS_PROVIDER_OPENAI_COMPAT_REASONING_EFFORT": str(
                self._config.provider.reasoning_effort or "high"
            ),
            "BOARDROOM_OS_PROVIDER_OPENAI_COMPAT_TIMEOUT_SEC": str(
                self._config.provider.timeout_sec or 30
            ),
            "BOARDROOM_OS_CEO_STAFFING_VARIANT_SEED": str(self._config.runtime.seed),
        }
        self._previous_env = {key: os.environ.get(key) for key in overrides}
        os.environ.update(overrides)
        self._client = TestClient(create_app())
        self._client.__enter__()
        self._repository = self._client.app.state.repository
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()
        return None

    def close(self) -> None:
        if self._client is not None:
            self._client.__exit__(None, None, None)
            self._client = None
        for key, value in self._previous_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    @property
    def repository(self):
        if self._repository is None:
            raise RuntimeError("Scenario driver is not initialized.")
        return self._repository

    @property
    def client(self) -> TestClient:
        if self._client is None:
            raise RuntimeError("Scenario driver is not initialized.")
        return self._client

    def upsert_runtime_provider(self, payload: dict[str, Any]) -> None:
        for provider in list(payload.get("providers") or []):
            if str(provider.get("api_key") or "").strip():
                continue
            config_hint = (
                f"Set `{self._config.provider.api_key_env}` or `provider.default.api_key` in `{self._config.config_path}`."
                if self._config.provider.api_key_env
                else f"Set `provider.default.api_key` in `{self._config.config_path}`."
            )
            raise RuntimeError(f"Scenario runtime provider api_key is empty. {config_hint}")
        response = self.client.post("/api/v1/commands/runtime-provider-upsert", json=payload)
        if response.status_code != 200 or response.json().get("status") != "ACCEPTED":
            raise RuntimeError(f"runtime-provider-upsert failed: {response.text}")

    def ensure_workflow(
        self,
        input_payload: dict[str, Any],
        *,
        seed_workflow_id: str | None,
        resume_enabled: bool,
    ) -> str:
        if seed_workflow_id and self.repository.get_workflow_projection(seed_workflow_id) is not None:
            return seed_workflow_id
        if resume_enabled:
            with self.repository.connection() as connection:
                row = connection.execute(
                    """
                    SELECT workflow_id
                    FROM workflow_projection
                    WHERE status = 'EXECUTING'
                    ORDER BY updated_at DESC, workflow_id DESC
                    LIMIT 1
                    """
                ).fetchone()
            if row is not None:
                return str(row["workflow_id"])
        response = self.client.post("/api/v1/commands/project-init", json=input_payload)
        if response.status_code != 200 or response.json().get("status") != "ACCEPTED":
            raise RuntimeError(f"project-init failed: {response.text}")
        return str(response.json()["causation_hint"]).split(":", 1)[1]

    def tick(self, workflow_id: str, tick_index: int, *, max_dispatches: int) -> None:
        run_scheduler_once(
            self.repository,
            idempotency_key=f"scenario-stage:{workflow_id}:{tick_index}",
            tick_index=tick_index,
            max_dispatches=max_dispatches,
        )

    def auto_advance(self, workflow_id: str, tick_index: int) -> None:
        auto_advance_workflow_to_next_stop(
            self.repository,
            workflow_id=workflow_id,
            idempotency_key_prefix=f"scenario-stage:auto-advance:{workflow_id}:{tick_index}",
            max_steps=4,
            max_dispatches=self._config.runtime.scheduler_max_dispatches,
        )

    def snapshot(self, workflow_id: str) -> ScenarioWorkflowSnapshot:
        workflow = self.repository.get_workflow_projection(workflow_id)
        if workflow is None:
            raise RuntimeError(f"Workflow `{workflow_id}` is missing from the copied scenario state.")

        with self.repository.connection() as connection:
            ticket_rows = connection.execute(
                """
                SELECT * FROM ticket_projection
                WHERE workflow_id = ?
                ORDER BY updated_at ASC, ticket_id ASC
                """,
                (workflow_id,),
            ).fetchall()
            approval_rows = connection.execute(
                """
                SELECT * FROM approval_projection
                WHERE workflow_id = ?
                ORDER BY created_at ASC, approval_id ASC
                """,
                (workflow_id,),
            ).fetchall()

            tickets: list[ScenarioCheckpointTicket] = []
            for row in ticket_rows:
                ticket = self.repository._convert_ticket_projection_row(row)
                ticket_id = str(ticket["ticket_id"])
                created_spec = self.repository.get_latest_ticket_created_payload(connection, ticket_id) or {}
                terminal_event = self.repository.get_latest_ticket_terminal_event(connection, ticket_id) or {}
                payload = dict(terminal_event.get("payload") or {})
                git_branch_ref = None
                git_merge_status = None
                try:
                    from app.core.project_workspaces import load_git_closeout_receipt

                    git_receipt = load_git_closeout_receipt(workflow_id, ticket_id)
                    git_branch_ref = str(git_receipt.get("branch_ref") or "").strip() or None
                    git_merge_status = str(git_receipt.get("merge_status") or "").strip() or None
                except Exception:
                    git_branch_ref = None
                    git_merge_status = None
                tickets.append(
                    ScenarioCheckpointTicket(
                        ticket_id=ticket_id,
                        node_id=str(ticket.get("node_id") or ""),
                        status=str(ticket.get("status") or ""),
                        output_schema_ref=str(created_spec.get("output_schema_ref") or "").strip() or None,
                        git_branch_ref=git_branch_ref,
                        git_merge_status=git_merge_status,
                        summary=str(payload.get("summary") or created_spec.get("summary") or "").strip(),
                    )
                )

        employees = [
            ScenarioEmployeeRecord(
                employee_id=str(item.get("employee_id") or ""),
                role_type=str(item.get("role_type") or ""),
                board_approved=bool(item.get("board_approved")),
            )
            for item in self.repository.list_employee_projections(states=["ACTIVE"])
        ]
        approvals = [
            ScenarioApprovalRecord(
                approval_id=str(item["approval_id"]),
                approval_type=str(item["approval_type"]),
                status=str(item["status"]),
            )
            for item in (self.repository._convert_approval_row(row) for row in approval_rows)
        ]
        open_incidents = [
            ScenarioIncidentRecord(
                incident_id=str(item.get("incident_id") or ""),
                incident_type=str(item.get("incident_type") or ""),
                status=str(item.get("status") or ""),
            )
            for item in self.repository.list_open_incidents()
            if str(item.get("workflow_id") or "") == workflow_id
        ]

        graph_snapshot = build_ticket_graph_snapshot(self.repository, workflow_id)
        graph_nodes = [
            ScenarioGraphNodeRecord(
                graph_node_id=str(node.graph_node_id),
                node_id=str(node.node_id),
                output_schema_ref=node.output_schema_ref,
                ticket_id=node.ticket_id,
            )
            for node in graph_snapshot.nodes
        ]
        graph_edges = [
            ScenarioGraphEdgeRecord(
                source_graph_node_id=str(edge.source_graph_node_id),
                target_graph_node_id=str(edge.target_graph_node_id),
                edge_type=str(edge.edge_type),
            )
            for edge in graph_snapshot.edges
        ]

        return ScenarioWorkflowSnapshot(
            workflow_id=workflow_id,
            workflow_status=str(workflow.get("status") or ""),
            current_stage=str(workflow.get("current_stage") or ""),
            workflow_profile=str(workflow.get("workflow_profile") or ""),
            tickets=tickets,
            employees=employees,
            approvals=approvals,
            open_incidents=open_incidents,
            graph_nodes=graph_nodes,
            graph_edges=graph_edges,
        )


def default_scenario_test_config_path() -> Path:
    override = str(os.environ.get(DEFAULT_CONFIG_ENV) or "").strip()
    if override:
        return Path(override)
    return BACKEND_ROOT / "data" / "scenario-tests" / "library-management.toml"


def is_scenario_test_enabled() -> bool:
    return str(os.environ.get("BOARDROOM_OS_SCENARIO_TEST_ENABLE") or "").strip() == "1"


def _build_runtime_paths(config: ScenarioTestConfig, scenario_root: Path) -> ScenarioRuntimePaths:
    return ScenarioRuntimePaths(
        scenario_root=scenario_root,
        db_path=scenario_root / config.layout.runtime_db,
        events_log_path=scenario_root / config.layout.events_log,
        runtime_provider_config_path=scenario_root / config.layout.runtime_provider_config,
        runtime_blobs_root=scenario_root / config.layout.runtime_blobs_dir,
        artifact_uploads_root=scenario_root / config.layout.artifact_uploads_dir,
        audit_records_root=scenario_root / config.layout.audit_records_dir,
        audit_timeline_root=scenario_root / config.layout.audit_records_dir / "timeline",
        audit_nodes_root=scenario_root / config.layout.audit_records_dir / "nodes",
        audit_incidents_root=scenario_root / config.layout.audit_records_dir / "incidents",
        audit_views_root=scenario_root / config.layout.audit_views_dir,
        audit_stage_views_root=scenario_root / config.layout.audit_stage_views_dir,
        debug_compile_root=scenario_root / config.layout.debug_compile_dir,
        debug_logs_root=scenario_root / config.layout.debug_logs_dir,
        ticket_context_archive_root=scenario_root / config.layout.ticket_context_archive_dir,
        project_workspace_root=config.layout.resolve_project_workspace_root(scenario_root),
    )


def _seed_workspace_manifest_path(runtime_paths: ScenarioRuntimePaths, workflow_id: str) -> Path:
    return runtime_paths.project_workspace_root / workflow_id / "00-boardroom" / "workflow" / "workspace-manifest.json"


def _seed_ticket_receipt_root(runtime_paths: ScenarioRuntimePaths, workflow_id: str, ticket_id: str) -> Path:
    return (
        runtime_paths.project_workspace_root
        / workflow_id
        / "00-boardroom"
        / "tickets"
        / ticket_id
        / "hook-receipts"
    )


def _resolve_seed_workflow_id(seed_manifest: dict[str, Any], seed_workflow_id: str | None) -> str | None:
    if seed_workflow_id:
        return seed_workflow_id
    resolved = str(seed_manifest.get("workflow_id") or "").strip()
    return resolved or None


def _validate_seed_file_requirements(
    stage: ScenarioStageSpec,
    runtime_paths: ScenarioRuntimePaths,
    *,
    requires_prepared_state: bool,
    workflow_id: str | None,
) -> dict[str, Any]:
    if not requires_prepared_state:
        return {}

    if not runtime_paths.db_path.exists():
        raise RuntimeError(
            f"Prepared seed for `{stage.stage_id}` is missing `{runtime_paths.db_path.relative_to(runtime_paths.scenario_root)}`."
        )

    manifest_path = runtime_paths.scenario_root / SEED_MANIFEST_FILENAME
    if not manifest_path.exists():
        raise RuntimeError(
            f"Prepared seed for `{stage.stage_id}` is missing `{SEED_MANIFEST_FILENAME}`."
        )
    seed_manifest = load_seed_manifest(runtime_paths.scenario_root)
    resolved_workflow_id = _resolve_seed_workflow_id(seed_manifest, workflow_id)
    if not resolved_workflow_id:
        raise RuntimeError(
            f"Prepared seed for `{stage.stage_id}` must declare a workflow_id in TOML or `{SEED_MANIFEST_FILENAME}`."
        )

    workspace_manifest_path = _seed_workspace_manifest_path(runtime_paths, resolved_workflow_id)
    if not workspace_manifest_path.exists():
        raise RuntimeError(
            f"Prepared seed for `{stage.stage_id}` is missing workspace manifest: {workspace_manifest_path.relative_to(runtime_paths.scenario_root)}."
        )

    if not runtime_paths.ticket_context_archive_root.exists():
        raise RuntimeError(
            f"Prepared seed for `{stage.stage_id}` is missing ticket context archive root: {runtime_paths.ticket_context_archive_root.relative_to(runtime_paths.scenario_root)}."
        )
    return seed_manifest


def _stage_source_delivery_tickets(
    snapshot: ScenarioWorkflowSnapshot,
    *,
    node_ids: tuple[str, ...] | None = None,
) -> list[ScenarioCheckpointTicket]:
    tickets = [
        ticket
        for ticket in snapshot.tickets
        if ticket.output_schema_ref == "source_code_delivery"
    ]
    if not node_ids:
        return tickets
    required = set(node_ids)
    return [ticket for ticket in tickets if ticket.node_id in required]


def _require_ticket_context_archives(
    runtime_paths: ScenarioRuntimePaths,
    *,
    ticket_ids: list[str],
) -> None:
    for ticket_id in ticket_ids:
        archive_path = runtime_paths.ticket_context_archive_root / f"{ticket_id}.md"
        if not archive_path.exists():
            raise RuntimeError(
                f"Prepared seed is missing ticket context archive: {archive_path.relative_to(runtime_paths.scenario_root)}."
            )


def _require_git_receipts(
    runtime_paths: ScenarioRuntimePaths,
    *,
    workflow_id: str,
    ticket_ids: list[str],
) -> None:
    for ticket_id in ticket_ids:
        receipt_root = _seed_ticket_receipt_root(runtime_paths, workflow_id, ticket_id)
        worktree_receipt = receipt_root / "worktree-checkout.json"
        git_receipt = receipt_root / "git-closeout.json"
        if not worktree_receipt.exists():
            raise RuntimeError(
                f"Prepared seed is missing worktree checkout receipt: {worktree_receipt.relative_to(runtime_paths.scenario_root)}."
            )
        if not git_receipt.exists():
            raise RuntimeError(
                f"Prepared seed is missing git closeout receipt: {git_receipt.relative_to(runtime_paths.scenario_root)}."
            )


def _validate_seed_snapshot_requirements(
    stage: ScenarioStageSpec,
    runtime_paths: ScenarioRuntimePaths,
    *,
    workflow_id: str,
    snapshot: ScenarioWorkflowSnapshot,
) -> None:
    available_schema_refs = _ticket_output_schema_refs(snapshot)
    available_node_ids = {
        str(node.graph_node_id or "").strip()
        for node in snapshot.graph_nodes
        if str(node.graph_node_id or "").strip()
    } | {
        str(node.node_id or "").strip()
        for node in snapshot.graph_nodes
        if str(node.node_id or "").strip()
    }

    match stage.stage_id:
        case "stage_02_outline_to_detailed_design":
            if snapshot.current_stage != "plan" or "architecture_brief" not in available_schema_refs:
                raise RuntimeError(
                    "Prepared seed for `stage_02_outline_to_detailed_design` must pause at `plan` with `architecture_brief` already completed."
                )
        case "stage_03_detailed_design_to_backlog":
            required = {"technology_decision", "milestone_plan", "detailed_design"}
            if snapshot.current_stage != "plan" or not required.issubset(available_schema_refs):
                raise RuntimeError(
                    "Prepared seed for `stage_03_detailed_design_to_backlog` must pause at `plan` with technology_decision, milestone_plan, and detailed_design completed."
                )
        case "stage_04_book_module_build_review":
            if snapshot.current_stage != "plan" or "backlog_recommendation" not in available_schema_refs:
                raise RuntimeError(
                    "Prepared seed for `stage_04_book_module_build_review` must pause at `plan` with `backlog_recommendation` completed."
                )
            if not any(node_id.startswith("node_backlog_followup") for node_id in available_node_ids):
                raise RuntimeError(
                    "Prepared seed for `stage_04_book_module_build_review` must already contain backlog fanout nodes."
                )
        case "stage_05_closeout_mainline_merge":
            source_tickets = _stage_source_delivery_tickets(snapshot)
            if snapshot.current_stage != "review" or not source_tickets:
                raise RuntimeError(
                    "Prepared seed for `stage_05_closeout_mainline_merge` must pause at `review` with at least one source_code_delivery ticket."
                )
            ticket_ids = [ticket.ticket_id for ticket in source_tickets]
            _require_git_receipts(runtime_paths, workflow_id=workflow_id, ticket_ids=ticket_ids)
            _require_ticket_context_archives(runtime_paths, ticket_ids=ticket_ids)
            if not any(
                str(ticket.git_merge_status or "").strip().upper() in {"PENDING_REVIEW_GATE", "MERGED"}
                for ticket in source_tickets
            ):
                raise RuntimeError(
                    "Prepared seed for `stage_05_closeout_mainline_merge` must include a source delivery ticket at PENDING_REVIEW_GATE or MERGED."
                )
        case "stage_06_parallel_git_fanout_merge":
            required_nodes = stage.required_node_ids or ("books_query", "books_commands", "terminal_shell")
            source_tickets = _stage_source_delivery_tickets(snapshot, node_ids=required_nodes)
            if snapshot.current_stage != "review":
                raise RuntimeError(
                    "Prepared seed for `stage_06_parallel_git_fanout_merge` must pause at `review`."
                )
            if set(required_nodes) - {ticket.node_id for ticket in source_tickets}:
                raise RuntimeError(
                    "Prepared seed for `stage_06_parallel_git_fanout_merge` is missing one or more required parallel source delivery nodes."
                )
            ticket_ids = [ticket.ticket_id for ticket in source_tickets]
            _require_git_receipts(runtime_paths, workflow_id=workflow_id, ticket_ids=ticket_ids)
            _require_ticket_context_archives(runtime_paths, ticket_ids=ticket_ids)
            if any(str(ticket.git_merge_status or "").strip().upper() != "MERGED" for ticket in source_tickets):
                raise RuntimeError(
                    "Prepared seed for `stage_06_parallel_git_fanout_merge` must mark all required parallel source delivery branches as MERGED."
                )
        case _:
            return


def validate_seed_for_stage(
    config: ScenarioTestConfig,
    stage: ScenarioStageSpec,
    seed,
    runtime_paths: ScenarioRuntimePaths,
    *,
    driver: ScenarioDriver | None = None,
    snapshot: ScenarioWorkflowSnapshot | None = None,
) -> str | None:
    seed_manifest = _validate_seed_file_requirements(
        stage,
        runtime_paths,
        requires_prepared_state=seed.requires_prepared_state,
        workflow_id=seed.workflow_id,
    )
    workflow_id = _resolve_seed_workflow_id(seed_manifest, seed.workflow_id)
    if not seed.requires_prepared_state:
        return workflow_id

    if snapshot is None:
        if driver is None:
            raise RuntimeError(
                f"Prepared seed for `{stage.stage_id}` requires a snapshot-capable driver for validation."
            )
        if workflow_id is None:
            raise RuntimeError(
                f"Prepared seed for `{stage.stage_id}` must resolve a workflow_id before snapshot validation."
            )
        snapshot = driver.snapshot(workflow_id)

    if workflow_id is None:
        workflow_id = snapshot.workflow_id
    if snapshot.workflow_id != workflow_id:
        raise RuntimeError(
            f"Prepared seed workflow mismatch: expected `{workflow_id}`, got snapshot `{snapshot.workflow_id}`."
        )
    _validate_seed_snapshot_requirements(
        stage,
        runtime_paths,
        workflow_id=workflow_id,
        snapshot=snapshot,
    )
    return workflow_id


def _stage_run_root(base_run_root: Path, stage_id: str) -> Path:
    return base_run_root / stage_id / f"run_{uuid4().hex[:10]}" / "scenario"


def verify_expected_outputs(*, scenario_root: Path, expected_outputs: tuple[str, ...]) -> list[str]:
    return [output for output in expected_outputs if not (scenario_root / output).exists()]


def _ticket_output_schema_refs(snapshot: ScenarioWorkflowSnapshot) -> set[str]:
    return {
        str(ticket.output_schema_ref or "").strip()
        for ticket in snapshot.tickets
        if str(ticket.output_schema_ref or "").strip()
    }


def _has_required_role_types(stage: ScenarioStageSpec, snapshot: ScenarioWorkflowSnapshot) -> bool:
    if not stage.required_role_types:
        return True
    role_types = {
        employee.role_type
        for employee in snapshot.employees
        if employee.board_approved
    }
    return set(stage.required_role_types).issubset(role_types)


def _has_required_node_ids(stage: ScenarioStageSpec, snapshot: ScenarioWorkflowSnapshot) -> bool:
    if not stage.required_node_ids:
        return True
    available = {
        str(node.graph_node_id or "").strip()
        for node in snapshot.graph_nodes
        if str(node.graph_node_id or "").strip()
    } | {
        str(node.node_id or "").strip()
        for node in snapshot.graph_nodes
        if str(node.node_id or "").strip()
    }
    return set(stage.required_node_ids).issubset(available)


def _has_required_summary_terms(stage: ScenarioStageSpec, snapshot: ScenarioWorkflowSnapshot) -> bool:
    if not stage.required_summary_terms:
        return True
    summary_corpus = " ".join(ticket.summary for ticket in snapshot.tickets).lower()
    return all(term.lower() in summary_corpus for term in stage.required_summary_terms)


def _base_checkpoint_match(stage: ScenarioStageSpec, snapshot: ScenarioWorkflowSnapshot) -> ScenarioCheckpointResult:
    available_schema_refs = _ticket_output_schema_refs(snapshot)
    if stage.expected_stage and snapshot.current_stage != stage.expected_stage:
        return ScenarioCheckpointResult(False, "expected_stage_mismatch", {"current_stage": snapshot.current_stage})
    if not set(stage.required_schema_refs).issubset(available_schema_refs):
        return ScenarioCheckpointResult(False, "required_schema_refs_missing", {"available_schema_refs": sorted(available_schema_refs)})
    if set(stage.forbidden_schema_refs) & available_schema_refs:
        return ScenarioCheckpointResult(False, "forbidden_schema_refs_present", {"available_schema_refs": sorted(available_schema_refs)})
    if not _has_required_role_types(stage, snapshot):
        return ScenarioCheckpointResult(False, "required_role_types_missing")
    if not _has_required_node_ids(stage, snapshot):
        return ScenarioCheckpointResult(False, "required_node_ids_missing")
    if not _has_required_summary_terms(stage, snapshot):
        return ScenarioCheckpointResult(False, "required_summary_terms_missing")
    return ScenarioCheckpointResult(True, "base_conditions_met", {"available_schema_refs": sorted(available_schema_refs)})


def evaluate_stage_checkpoint(
    stage: ScenarioStageSpec,
    snapshot: ScenarioWorkflowSnapshot,
) -> ScenarioCheckpointResult:
    base = _base_checkpoint_match(stage, snapshot)
    if not base.matched:
        return base

    available_schema_refs = _ticket_output_schema_refs(snapshot)
    source_delivery_tickets = [
        ticket for ticket in snapshot.tickets if ticket.output_schema_ref == "source_code_delivery"
    ]
    merged_tickets = [
        ticket
        for ticket in source_delivery_tickets
        if str(ticket.git_merge_status or "").strip().upper() == "MERGED"
    ]

    match stage.checkpoint_kind:
        case "requirement_to_architecture":
            if "architecture_brief" not in available_schema_refs or source_delivery_tickets:
                return ScenarioCheckpointResult(False, "architecture_brief_not_ready")
            return ScenarioCheckpointResult(True, "requirement_to_architecture_ready", base.details)
        case "outline_to_detailed_design":
            required = {"technology_decision", "milestone_plan", "detailed_design"}
            if not required.issubset(available_schema_refs):
                return ScenarioCheckpointResult(False, "outline_to_detailed_design_missing_docs")
            return ScenarioCheckpointResult(True, "outline_to_detailed_design_ready", base.details)
        case "detailed_design_to_backlog":
            if "backlog_recommendation" not in available_schema_refs or not snapshot.graph_nodes:
                return ScenarioCheckpointResult(False, "detailed_design_to_backlog_missing_graph")
            return ScenarioCheckpointResult(
                True,
                "detailed_design_to_backlog_ready",
                {**base.details, "graph_node_count": len(snapshot.graph_nodes)},
            )
        case "book_module_build_review":
            qualified_git_gate_tickets = [
                ticket
                for ticket in source_delivery_tickets
                if str(ticket.git_branch_ref or "").strip()
                and str(ticket.git_merge_status or "").strip().upper() in {"PENDING_REVIEW_GATE", "MERGED"}
            ]
            if not qualified_git_gate_tickets:
                return ScenarioCheckpointResult(False, "book_module_build_review_missing_git_gate")
            return ScenarioCheckpointResult(
                True,
                "book_module_build_review_ready",
                {**base.details, "git_gate_ticket_count": len(qualified_git_gate_tickets)},
            )
        case "closeout_mainline_merge":
            if "delivery_closeout_package" not in available_schema_refs or not merged_tickets:
                return ScenarioCheckpointResult(False, "closeout_mainline_merge_incomplete")
            if any(not str(ticket.git_branch_ref or "").strip() for ticket in merged_tickets):
                return ScenarioCheckpointResult(False, "closeout_mainline_merge_missing_branch_ref")
            return ScenarioCheckpointResult(
                True,
                "closeout_mainline_merge_ready",
                {**base.details, "merged_branch_count": len(merged_tickets)},
            )
        case "parallel_git_fanout_merge":
            merged_source_tickets_by_node = {
                ticket.node_id: ticket
                for ticket in merged_tickets
                if str(ticket.node_id or "").strip()
            }
            merged_branches = {
                str(ticket.git_branch_ref or "").strip()
                for ticket in merged_source_tickets_by_node.values()
                if str(ticket.git_branch_ref or "").strip()
            }
            if "delivery_closeout_package" not in available_schema_refs:
                return ScenarioCheckpointResult(False, "parallel_git_fanout_merge_missing_closeout")
            if stage.required_node_ids and any(
                node_id not in merged_source_tickets_by_node
                or not str(merged_source_tickets_by_node[node_id].git_branch_ref or "").strip()
                for node_id in stage.required_node_ids
            ):
                return ScenarioCheckpointResult(False, "parallel_git_fanout_merge_missing_merged_branches")
            return ScenarioCheckpointResult(
                True,
                "parallel_git_fanout_merge_ready",
                {**base.details, "merged_branch_count": len(merged_branches)},
            )
        case _:
            return ScenarioCheckpointResult(True, "generic_checkpoint_ready", base.details)


def _append_event(runtime_paths: ScenarioRuntimePaths, event_type: str, payload: dict[str, Any]) -> None:
    entry = {
        "event_type": event_type,
        "recorded_at": time.time(),
        "payload": payload,
    }
    with runtime_paths.events_log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False, sort_keys=True))
        handle.write("\n")


def _snapshot_to_json(snapshot: ScenarioWorkflowSnapshot) -> dict[str, Any]:
    return {
        "workflow_id": snapshot.workflow_id,
        "workflow_status": snapshot.workflow_status,
        "current_stage": snapshot.current_stage,
        "workflow_profile": snapshot.workflow_profile,
        "tickets": [ticket.__dict__ for ticket in snapshot.tickets],
        "employees": [employee.__dict__ for employee in snapshot.employees],
        "approvals": [approval.__dict__ for approval in snapshot.approvals],
        "open_incidents": [incident.__dict__ for incident in snapshot.open_incidents],
        "graph_nodes": [node.__dict__ for node in snapshot.graph_nodes],
        "graph_edges": [edge.__dict__ for edge in snapshot.graph_edges],
    }


def _write_timeline_entry(
    runtime_paths: ScenarioRuntimePaths,
    *,
    tick_index: int,
    snapshot: ScenarioWorkflowSnapshot,
    checkpoint: ScenarioCheckpointResult,
) -> None:
    target_path = runtime_paths.audit_timeline_root / f"tick_{tick_index:04d}.json"
    target_path.write_text(
        json.dumps(
            {
                "tick_index": tick_index,
                "snapshot": _snapshot_to_json(snapshot),
                "checkpoint": checkpoint.__dict__,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def _write_nodes_view(runtime_paths: ScenarioRuntimePaths, snapshot: ScenarioWorkflowSnapshot) -> None:
    for node in snapshot.graph_nodes:
        target_path = runtime_paths.audit_nodes_root / f"{node.graph_node_id}.json"
        target_path.write_text(
            json.dumps(node.__dict__, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )


def _write_incident_views(runtime_paths: ScenarioRuntimePaths, snapshot: ScenarioWorkflowSnapshot) -> None:
    for incident in snapshot.open_incidents:
        target_path = runtime_paths.audit_incidents_root / f"{incident.incident_id}.json"
        target_path.write_text(
            json.dumps(incident.__dict__, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )


def _build_dag_dot(snapshot: ScenarioWorkflowSnapshot) -> str:
    lines = ["digraph workflow {"]
    for node in snapshot.graph_nodes:
        label = node.output_schema_ref or node.node_id or node.graph_node_id
        lines.append(f'  "{node.graph_node_id}" [label="{label}"];')
    for edge in snapshot.graph_edges:
        lines.append(
            f'  "{edge.source_graph_node_id}" -> "{edge.target_graph_node_id}" [label="{edge.edge_type}"];'
        )
    lines.append("}")
    return "\n".join(lines) + "\n"


def _write_summary_views(
    runtime_paths: ScenarioRuntimePaths,
    *,
    stage: ScenarioStageSpec,
    snapshot: ScenarioWorkflowSnapshot,
    checkpoint: ScenarioCheckpointResult,
) -> tuple[Path, Path, Path]:
    manifest_path = runtime_paths.audit_records_root / "manifest.json"
    summary_path = runtime_paths.audit_views_root / "workflow-summary.md"
    dag_path = runtime_paths.audit_views_root / "dag-visualization.dot"
    stage_view_path = runtime_paths.audit_stage_views_root / f"{stage.stage_id}.md"

    manifest_path.write_text(
        json.dumps(
            {
                "stage_id": stage.stage_id,
                "checkpoint_kind": stage.checkpoint_kind,
                "workflow_id": snapshot.workflow_id,
                "workflow_status": snapshot.workflow_status,
                "current_stage": snapshot.current_stage,
                "checkpoint": checkpoint.__dict__,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    summary_body = "\n".join(
        [
            f"# {stage.stage_id}",
            "",
            f"- Workflow: `{snapshot.workflow_id}`",
            f"- Status: `{snapshot.workflow_status}`",
            f"- Current stage: `{snapshot.current_stage}`",
            f"- Checkpoint: `{checkpoint.reason}`",
            f"- Ticket count: `{len(snapshot.tickets)}`",
            f"- Open incidents: `{len(snapshot.open_incidents)}`",
        ]
    )
    summary_path.write_text(summary_body + "\n", encoding="utf-8")
    dag_path.write_text(_build_dag_dot(snapshot), encoding="utf-8")
    stage_view_path.write_text(summary_body + "\n", encoding="utf-8")
    return manifest_path, summary_path, dag_path


def _write_audit_outputs(
    runtime_paths: ScenarioRuntimePaths,
    *,
    stage: ScenarioStageSpec,
    snapshot: ScenarioWorkflowSnapshot,
    checkpoint: ScenarioCheckpointResult,
    tick_index: int,
) -> tuple[Path, Path, Path]:
    _write_timeline_entry(runtime_paths, tick_index=tick_index, snapshot=snapshot, checkpoint=checkpoint)
    _write_nodes_view(runtime_paths, snapshot)
    _write_incident_views(runtime_paths, snapshot)
    return _write_summary_views(runtime_paths, stage=stage, snapshot=snapshot, checkpoint=checkpoint)


def run_configured_stage(
    config_path: Path | None,
    stage_id: str,
    *,
    run_root: Path | None = None,
    driver_factory: Any | None = None,
) -> ScenarioStageRunResult:
    config = load_scenario_test_config(config_path or default_scenario_test_config_path())
    stage = config.stages[stage_id]
    seed = config.seeds[stage.seed_ref]
    base_run_root = run_root or config.default_run_root()
    scenario_root = _stage_run_root(base_run_root, stage.stage_id)

    prepare_seeded_scenario(
        seed_root=seed.path,
        destination_root=scenario_root,
        layout=config.layout,
        workflow_id=seed.workflow_id,
    )
    runtime_paths = _build_runtime_paths(config, scenario_root)
    seed_manifest = _validate_seed_file_requirements(
        stage,
        runtime_paths,
        requires_prepared_state=seed.requires_prepared_state,
        workflow_id=seed.workflow_id,
    )
    seed_workflow_id = _resolve_seed_workflow_id(seed_manifest, seed.workflow_id)

    driver_builder = driver_factory or (lambda _runtime: AppScenarioDriver(_runtime, config))
    driver = driver_builder(runtime_paths)
    if hasattr(driver, "__enter__") and hasattr(driver, "__exit__"):
        context = driver
    else:
        context = _DriverContextAdapter(driver)

    started_at = time.monotonic()
    with context as active_driver:
        seed_workflow_id = validate_seed_for_stage(
            config,
            stage,
            seed,
            runtime_paths,
            driver=active_driver,
        )
        active_driver.upsert_runtime_provider(config.build_runtime_provider_payload())
        workflow_id = active_driver.ensure_workflow(
            config.build_project_init_payload(),
            seed_workflow_id=seed_workflow_id,
            resume_enabled=config.runtime.resume_enabled,
        )
        ensure_layout_directories(
            scenario_root=scenario_root,
            layout=config.layout,
            workflow_id=workflow_id,
        )
        _append_event(runtime_paths, "SCENARIO_STAGE_STARTED", {"stage_id": stage.stage_id, "workflow_id": workflow_id})

        last_snapshot: ScenarioWorkflowSnapshot | None = None
        last_checkpoint = ScenarioCheckpointResult(False, "not_evaluated")
        for tick_index in range(config.runtime.max_ticks + 1):
            if tick_index > 0:
                active_driver.tick(
                    workflow_id,
                    tick_index - 1,
                    max_dispatches=config.runtime.scheduler_max_dispatches,
                )
                active_driver.auto_advance(workflow_id, tick_index - 1)
            snapshot = active_driver.snapshot(workflow_id)
            checkpoint = evaluate_stage_checkpoint(stage, snapshot)
            manifest_path, summary_path, dag_path = _write_audit_outputs(
                runtime_paths,
                stage=stage,
                snapshot=snapshot,
                checkpoint=checkpoint,
                tick_index=tick_index,
            )
            _append_event(
                runtime_paths,
                "SCENARIO_STAGE_TICK",
                {
                    "stage_id": stage.stage_id,
                    "workflow_id": workflow_id,
                    "tick_index": tick_index,
                    "checkpoint_reason": checkpoint.reason,
                },
            )
            last_snapshot = snapshot
            last_checkpoint = checkpoint
            if checkpoint.matched:
                missing_outputs = verify_expected_outputs(
                    scenario_root=scenario_root,
                    expected_outputs=stage.expected_outputs,
                )
                if missing_outputs:
                    raise RuntimeError(
                        f"Stage `{stage.stage_id}` matched checkpoint but missed expected outputs: {missing_outputs}"
                    )
                _append_event(
                    runtime_paths,
                    "SCENARIO_STAGE_COMPLETED",
                    {
                        "stage_id": stage.stage_id,
                        "workflow_id": workflow_id,
                        "elapsed_sec": round(time.monotonic() - started_at, 2),
                    },
                )
                return ScenarioStageRunResult(
                    success=True,
                    stage_id=stage.stage_id,
                    workflow_id=workflow_id,
                    scenario_root=scenario_root,
                    manifest_path=manifest_path,
                    summary_path=summary_path,
                    dag_path=dag_path,
                    timeline_dir=runtime_paths.audit_timeline_root,
                )

        raise RuntimeError(
            f"Stage `{stage.stage_id}` did not reach checkpoint `{stage.checkpoint_kind}` within "
            f"{config.runtime.max_ticks} ticks. Last checkpoint: {last_checkpoint.reason}. "
            f"Workflow: {last_snapshot.workflow_id if last_snapshot else 'unknown'}."
        )


class _DriverContextAdapter(AbstractContextManager[ScenarioDriver]):
    def __init__(self, driver: ScenarioDriver) -> None:
        self._driver = driver

    def __enter__(self) -> ScenarioDriver:
        return self._driver

    def __exit__(self, exc_type, exc, tb) -> None:
        self._driver.close()
        return None
