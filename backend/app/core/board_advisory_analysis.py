from __future__ import annotations

import json
from contextlib import nullcontext
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping

from app.config import get_settings
from app.contracts.advisory import (
    BoardAdvisoryAnalysisRun,
    BoardAdvisoryDecision,
    GraphPatchProposal,
)
from app.contracts.commands import TicketEscalationPolicy
from app.contracts.governance import GovernanceModeSlice, GovernanceProfile
from app.contracts.runtime import (
    CompileRequest,
    CompileRequestBudgetPolicy,
    CompileRequestControlRefs,
    CompileRequestExecution,
    CompileRequestExplicitSource,
    CompileRequestGovernance,
    CompileRequestMeta,
    CompileRequestOrgContext,
    CompileRequestRetrievalPlan,
    CompileRequestWorkerBinding,
    CompiledArtifactAccessDescriptor,
)
from app.core.board_advisory import (
    BOARD_ADVISORY_STATUS_ANALYSIS_REJECTED,
    build_graph_patch_proposal,
)
from app.core.constants import (
    CIRCUIT_BREAKER_STATE_OPEN,
    DEFAULT_TENANT_ID,
    DEFAULT_WORKSPACE_ID,
    EVENT_BOARD_ADVISORY_ANALYSIS_COMPLETED,
    EVENT_BOARD_ADVISORY_ANALYSIS_REJECTED,
    EVENT_CIRCUIT_BREAKER_OPENED,
    EVENT_INCIDENT_OPENED,
    INCIDENT_STATUS_OPEN,
    INCIDENT_TYPE_BOARD_ADVISORY_ANALYSIS_FAILED,
)
from app.core.context_compiler import _build_fragment_candidate, _build_org_context, compile_audit_artifacts
from app.core.execution_targets import (
    EXECUTION_TARGET_BOARD_ADVISORY_ANALYSIS,
    build_execution_contract_payload_for_target,
    employee_supports_execution_contract,
    pick_employee_role_profile_for_execution_contract,
)
from app.core.graph_identity import GraphIdentityResolutionError, ensure_patch_targets_are_execution_node_ids
from app.core.ids import new_prefixed_id
from app.core.output_schemas import (
    GRAPH_PATCH_PROPOSAL_SCHEMA_REF,
    GRAPH_PATCH_PROPOSAL_SCHEMA_VERSION,
    validate_output_payload,
)
from app.core.persona_profiles import normalize_persona_profiles
from app.core.process_assets import (
    build_compile_manifest_process_asset_ref,
    build_compiled_context_bundle_process_asset_ref,
    build_compiled_execution_package_process_asset_ref,
    build_decision_summary_process_asset_ref,
    build_failure_fingerprint_process_asset_ref,
    build_project_map_slice_process_asset_ref,
    dedupe_process_asset_refs,
    resolve_process_asset,
)
from app.core.provider_claude_code import invoke_claude_code_response
from app.core.provider_openai_compat import invoke_openai_compat_response, load_openai_compat_result_payload
from app.core.review_subjects import resolve_graph_only_review_subject_execution_identity
from app.core.runtime_provider_config import (
    RuntimeProviderAdapterKind,
    RuntimeProviderSelection,
    resolve_provider_selection,
    resolve_runtime_provider_config,
)
from app.core.ticket_graph import build_ticket_graph_snapshot
from app.core.time import now_local
from app.db.repository import ControlPlaneRepository

BOARD_ADVISORY_ANALYSIS_ROLE_TYPE = "governance_architect"
BOARD_ADVISORY_ANALYSIS_CONSTRAINTS_REF = "board_advisory_analysis_constraints_v1"
BOARD_ADVISORY_ANALYSIS_OVERFLOW_POLICY = "FAIL_CLOSED"
BOARD_ADVISORY_ANALYSIS_FAILURE_PHASE_EXECUTOR_SELECTION = "executor_selection"
BOARD_ADVISORY_ANALYSIS_FAILURE_PHASE_PROVIDER_SELECTION = "provider_selection"
BOARD_ADVISORY_ANALYSIS_FAILURE_PHASE_PROVIDER_EXECUTION = "provider_execution"
BOARD_ADVISORY_ANALYSIS_FAILURE_PHASE_OUTPUT_VALIDATION = "output_validation"
BOARD_ADVISORY_ANALYSIS_FAILURE_PHASE_NODE_VALIDATION = "node_validation"
BOARD_ADVISORY_ANALYSIS_FAILURE_PHASE_TRACE_MATERIALIZATION = "trace_materialization"
BOARD_ADVISORY_ANALYSIS_FAILURE_PHASE_ARCHIVE_MATERIALIZATION = "archive_materialization"
BOARD_ADVISORY_ANALYSIS_FAILURE_PHASE_GRAPH_VERSION_STALE = "graph_version_stale"


@dataclass(frozen=True)
class _AdvisoryAnalysisExecutor:
    employee_id: str
    role_type: str
    role_profile_ref: str
    skill_profile: dict[str, Any]
    personality_profile: dict[str, Any]
    aesthetic_profile: dict[str, Any]
    provider_id: str | None
    is_real_employee: bool


@dataclass(frozen=True)
class _ResolvedAnalysisExecutionPlan:
    execution_contract: dict[str, Any]
    executor: _AdvisoryAnalysisExecutor | None
    provider_selection: RuntimeProviderSelection | None
    executor_mode: str
    has_any_real_employee: bool
    failure_reason: str | None


@dataclass(frozen=True)
class _LiveExecutionResult:
    proposal_payload: dict[str, Any]
    selection_summary: dict[str, Any]
    provider_response_id: str | None


def _analysis_subject_ticket_id(session_id: str) -> str:
    return f"advisory-analysis:{session_id}"


def _analysis_subject_node_id(session_id: str) -> str:
    return f"advisory-analysis:{session_id}"


def _analysis_trace_artifact_ref(*, workflow_id: str, session_id: str, attempt_int: int) -> str:
    return f"art://board-advisory-analysis/{workflow_id}/{session_id}/analysis-run-{attempt_int}.json"


def _analysis_trace_logical_path(*, session_id: str, attempt_int: int) -> str:
    return f"20-evidence/board-advisory/{session_id}/analysis-run-{attempt_int}.json"


def _analysis_archive_artifact_ref(*, workflow_id: str, session_id: str, attempt_int: int) -> str:
    return f"art://board-advisory-analysis/{workflow_id}/{session_id}/archive-run-{attempt_int}.json"


def _analysis_archive_logical_path(*, session_id: str, attempt_int: int) -> str:
    return f"90-archive/transcripts/board-advisory-analysis/{session_id}/run-{attempt_int}.json"


def _stable_json_hash(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=True,
        separators=(",", ":"),
        default=str,
    )


def _resolve_board_decision_hash(session: Mapping[str, Any]) -> str:
    return _stable_json_hash(dict(session.get("board_decision") or {}))


def _resolve_source_subject(
    repository: ControlPlaneRepository,
    connection,
    *,
    session: Mapping[str, Any],
) -> tuple[str, str]:
    approval = repository.get_approval_by_id(connection, str(session.get("approval_id") or "")) or {}
    review_pack = ((approval.get("payload") or {}).get("review_pack") or {}) if isinstance(approval, dict) else {}
    subject = review_pack.get("subject") or {}
    source_ticket_id, _source_graph_node_id, source_node_id = resolve_graph_only_review_subject_execution_identity(
        repository,
        workflow_id=str(session.get("workflow_id") or ""),
        subject=subject,
        connection=connection,
    )
    normalized_ticket_id = (
        str(source_ticket_id or "").strip()
        or str(session.get("approval_id") or "").strip()
        or str(session.get("session_id") or "").strip()
    )
    return normalized_ticket_id, source_node_id


def _workflow_failure_fingerprint_refs(
    repository: ControlPlaneRepository,
    *,
    workflow_id: str,
    connection,
) -> list[str]:
    rows = connection.execute(
        """
        SELECT incident_id
        FROM incident_projection
        WHERE workflow_id = ?
        ORDER BY opened_at DESC, incident_id DESC
        LIMIT 5
        """,
        (workflow_id,),
    ).fetchall()
    return dedupe_process_asset_refs(
        [
            build_failure_fingerprint_process_asset_ref(str(row["incident_id"]).strip())
            for row in rows
            if str(row["incident_id"]).strip()
        ]
    )[:3]


def _resolve_advisory_execution_contract() -> dict[str, Any]:
    execution_contract = build_execution_contract_payload_for_target(
        EXECUTION_TARGET_BOARD_ADVISORY_ANALYSIS
    )
    if execution_contract is None:
        raise RuntimeError("Board advisory analysis execution contract is not configured.")
    return execution_contract


def _resolve_analysis_executor(
    repository: ControlPlaneRepository,
    *,
    execution_contract: dict[str, Any],
) -> tuple[_AdvisoryAnalysisExecutor | None, bool]:
    employees = repository.list_employee_projections(states=["ACTIVE"], board_approved_only=True)
    has_any_real_employee = any(isinstance(employee, dict) for employee in employees)
    for employee in employees:
        if not employee_supports_execution_contract(
            employee=employee,
            execution_contract=execution_contract,
        ):
            continue
        role_profile_ref = (
            pick_employee_role_profile_for_execution_contract(
                employee=employee,
                execution_contract=execution_contract,
            )
            or _SYNTHETIC_BOARD_ADVISORY_ANALYSIS_ROLE_PROFILE_REF
        )
        normalized = normalize_persona_profiles(
            str(employee.get("role_type") or BOARD_ADVISORY_ANALYSIS_ROLE_TYPE),
            skill_profile=employee.get("skill_profile_json"),
            personality_profile=employee.get("personality_profile_json"),
            aesthetic_profile=employee.get("aesthetic_profile_json"),
        )
        return _AdvisoryAnalysisExecutor(
            employee_id=str(employee.get("employee_id") or ""),
            role_type=str(employee.get("role_type") or BOARD_ADVISORY_ANALYSIS_ROLE_TYPE),
            role_profile_ref=role_profile_ref,
            skill_profile=dict(normalized["skill_profile"]),
            personality_profile=dict(normalized["personality_profile"]),
            aesthetic_profile=dict(normalized["aesthetic_profile"]),
            provider_id=str(employee.get("provider_id") or "").strip() or None,
            is_real_employee=True,
        ), has_any_real_employee
    return None, has_any_real_employee


def _resolve_analysis_execution_plan(
    repository: ControlPlaneRepository,
) -> _ResolvedAnalysisExecutionPlan:
    execution_contract = _resolve_advisory_execution_contract()
    executor, has_any_real_employee = _resolve_analysis_executor(
        repository,
        execution_contract=execution_contract,
    )
    provider_selection: RuntimeProviderSelection | None = None
    failure_reason: str | None = None
    if executor is not None:
        provider_selection = resolve_provider_selection(
            resolve_runtime_provider_config(),
            target_ref=str(execution_contract.get("execution_target_ref") or ""),
            employee_provider_id=executor.provider_id,
            runtime_preference=None,
        )
        if provider_selection is None:
            failure_reason = "missing_provider_selection"
    elif has_any_real_employee:
        failure_reason = "no_contract_matching_executor"
    else:
        failure_reason = "no_real_executor"
    return _ResolvedAnalysisExecutionPlan(
        execution_contract=execution_contract,
        executor=executor,
        provider_selection=provider_selection,
        executor_mode="LIVE_PROVIDER",
        has_any_real_employee=has_any_real_employee,
        failure_reason=failure_reason,
    )


def create_board_advisory_analysis_run(
    repository: ControlPlaneRepository,
    connection,
    *,
    session: Mapping[str, Any],
    idempotency_key: str,
    occurred_at: datetime,
) -> dict[str, Any]:
    latest_run = repository.get_latest_board_advisory_analysis_run(
        str(session.get("session_id") or ""),
        connection=connection,
    )
    attempt_int = int((latest_run or {}).get("attempt_int") or 0) + 1
    execution_plan = _resolve_analysis_execution_plan(repository)
    run = BoardAdvisoryAnalysisRun(
        run_id=new_prefixed_id("adrun"),
        session_id=str(session.get("session_id") or ""),
        workflow_id=str(session.get("workflow_id") or ""),
        source_graph_version=str(session.get("source_version") or ""),
        status="PENDING",
        idempotency_key=idempotency_key,
        attempt_int=attempt_int,
        executor_mode=execution_plan.executor_mode,
        created_at=occurred_at,
    )
    created = repository.create_board_advisory_analysis_run(connection, run)
    repository.queue_board_advisory_analysis_run(
        connection,
        session_id=str(session.get("session_id") or ""),
        run_id=run.run_id,
        updated_at=occurred_at,
    )
    return created


def _build_governance_mode_slice(profile: Mapping[str, Any]) -> GovernanceModeSlice:
    return GovernanceModeSlice(
        governance_profile_ref=str(profile.get("profile_id") or ""),
        approval_mode=str(profile.get("approval_mode") or ""),
        audit_mode=str(profile.get("audit_mode") or ""),
        auto_approval_scope=list(profile.get("auto_approval_scope") or []),
        expert_review_targets=list(profile.get("expert_review_targets") or []),
        audit_materialization_policy=dict(profile.get("audit_materialization_policy") or {}),
    )


def _build_explicit_sources(
    repository: ControlPlaneRepository,
    *,
    process_asset_refs: list[str],
    fragment_terms: list[str],
    connection,
) -> list[CompileRequestExplicitSource]:
    explicit_sources: list[CompileRequestExplicitSource] = []
    for source_ref in process_asset_refs:
        resolved_asset = resolve_process_asset(repository, str(source_ref), connection=connection)
        explicit_source = CompileRequestExplicitSource(
            source_ref=str(resolved_asset.process_asset_ref),
            source_kind="PROCESS_ASSET",
            process_asset_kind=resolved_asset.process_asset_kind,
            producer_ticket_id=resolved_asset.producer_ticket_id,
            source_summary=resolved_asset.summary,
            consumable_by=list(resolved_asset.consumable_by),
            source_metadata=(
                dict(resolved_asset.source_metadata)
                | {
                    "canonical_ref": resolved_asset.canonical_ref,
                    "version_int": resolved_asset.version_int,
                    "supersedes_ref": resolved_asset.supersedes_ref,
                }
            ),
            is_mandatory=True,
            artifact_access=(
                CompiledArtifactAccessDescriptor.model_validate(resolved_asset.artifact_access)
                if resolved_asset.artifact_access is not None
                else None
            ),
            inline_content_type=resolved_asset.content_type,
            inline_content_text=resolved_asset.text_content,
            inline_content_json=resolved_asset.json_content,
            inline_fallback_reason=resolved_asset.fallback_reason,
            inline_fallback_reason_code=resolved_asset.fallback_reason_code,
            inline_content_truncated=False,
            inline_preview_strategy=None,
        )
        explicit_sources.append(
            _build_fragment_candidate(
                explicit_source,
                fragment_terms=fragment_terms,
            )
        )
    return explicit_sources


def _build_board_advisory_analysis_compile_request(
    repository: ControlPlaneRepository,
    *,
    session: Mapping[str, Any],
    run: Mapping[str, Any],
    execution_plan: _ResolvedAnalysisExecutionPlan,
    connection,
) -> CompileRequest:
    workflow_id = str(session.get("workflow_id") or "")
    workflow = repository.get_workflow_projection(workflow_id)
    current_profile = repository.get_latest_governance_profile(workflow_id, connection=connection)
    if workflow is None:
        raise ValueError(f"Workflow {workflow_id} does not exist.")
    if current_profile is None:
        raise ValueError("Governance profile is required before advisory analysis can run.")
    board_decision = dict(session.get("board_decision") or {})
    if not board_decision:
        raise ValueError("Board advisory session is missing its drafting decision summary.")

    session_id = str(session.get("session_id") or "")
    ticket_id = _analysis_subject_ticket_id(session_id)
    node_id = _analysis_subject_node_id(session_id)
    source_ticket_id, source_node_id = _resolve_source_subject(repository, connection, session=session)
    process_asset_refs = dedupe_process_asset_refs(
        [
            build_decision_summary_process_asset_ref(session_id),
            build_project_map_slice_process_asset_ref(workflow_id),
            *(
                [str(session.get("latest_timeline_index_ref") or "").strip()]
                if str(session.get("latest_timeline_index_ref") or "").strip()
                else []
            ),
            *_workflow_failure_fingerprint_refs(
                repository,
                workflow_id=workflow_id,
                connection=connection,
            ),
        ]
    )
    affected_nodes = [
        str(node_id_value).strip()
        for node_id_value in list(session.get("affected_nodes") or [])
        if str(node_id_value).strip()
    ]
    fragment_terms = [
        "advisory",
        "graph",
        "patch",
        "governance",
        "constraint",
        "risk",
        "focus",
        *affected_nodes,
    ]
    executor = execution_plan.executor
    if executor is None:
        raise RuntimeError(
            "Board advisory analysis compile request requires a board-approved contract-matching executor."
        )
    ticket_stub = {
        "workflow_id": workflow_id,
        "ticket_id": source_ticket_id,
        "node_id": source_node_id,
        "blocking_reason_code": None,
    }
    created_spec = {
        "parent_ticket_id": source_ticket_id,
        "graph_contract": {"lane_kind": "execution"},
        "role_profile_ref": executor.role_profile_ref,
        "output_schema_ref": GRAPH_PATCH_PROPOSAL_SCHEMA_REF,
        "output_schema_version": GRAPH_PATCH_PROPOSAL_SCHEMA_VERSION,
        "execution_contract": dict(execution_plan.execution_contract),
        "delivery_stage": "REVIEW",
        "allowed_write_set": [
            f"20-evidence/board-advisory/{session_id}/*",
            f"90-archive/transcripts/board-advisory-analysis/{session_id}/*",
        ],
        "acceptance_criteria": [
            "Return a valid graph_patch_proposal payload.",
            "Only reference existing execution node ids in freeze_node_ids, unfreeze_node_ids, replacements, remove_node_ids, edge_additions, and edge_removals.",
            "If you use add_nodes, every new node must declare node_id, node_kind, deliverable_kind, role_hint, parent_node_id, and dependency_node_ids.",
            "Do not target synthetic review lanes, and do not use edge_additions or edge_removals to wire placeholder nodes in the same patch.",
            "Keep the proposal scoped to the current board advisory session.",
        ],
        "forced_skill_ids": ["planning_governance"],
        "input_process_asset_refs": process_asset_refs,
        "required_read_refs": [],
        "doc_update_requirements": [],
        "deliverable_kind": "structured_document_delivery",
        "git_policy": "no_git_required",
        "escalation_policy": {
            "on_timeout": "REQUEST_BOARD_ADVICE",
            "on_schema_error": "REQUEST_BOARD_ADVICE",
            "on_repeat_failure": "REQUEST_BOARD_ADVICE",
        },
    }
    explicit_sources = _build_explicit_sources(
        repository,
        process_asset_refs=process_asset_refs,
        fragment_terms=fragment_terms,
        connection=connection,
    )
    cursor_version = repository.get_cursor_and_version(connection)[1]
    org_context = _build_org_context(
        repository,
        ticket=ticket_stub,
        created_spec=created_spec,
        employee_role_type=executor.role_type,
        connection=connection,
    )
    return CompileRequest(
        meta=CompileRequestMeta(
            compile_request_id=new_prefixed_id("creq"),
            ticket_id=ticket_id,
            workflow_id=workflow_id,
            node_id=node_id,
            attempt_no=1,
            governance_profile_ref=str(current_profile.get("profile_id") or ""),
            tenant_id=str(workflow.get("tenant_id") or DEFAULT_TENANT_ID),
            workspace_id=str(workflow.get("workspace_id") or DEFAULT_WORKSPACE_ID),
            ticket_projection_version=1,
            node_projection_version=1,
            source_projection_version=max(cursor_version, 1),
        ),
        control_refs=CompileRequestControlRefs(
            role_profile_ref=executor.role_profile_ref,
            constraints_ref=BOARD_ADVISORY_ANALYSIS_CONSTRAINTS_REF,
            output_schema_ref=GRAPH_PATCH_PROPOSAL_SCHEMA_REF,
            output_schema_version=GRAPH_PATCH_PROPOSAL_SCHEMA_VERSION,
        ),
        worker_binding=CompileRequestWorkerBinding(
            lease_owner=executor.employee_id,
            employee_id=executor.employee_id,
            employee_role_type=executor.role_type,
            tenant_id=str(workflow.get("tenant_id") or DEFAULT_TENANT_ID),
            workspace_id=str(workflow.get("workspace_id") or DEFAULT_WORKSPACE_ID),
            skill_profile=dict(executor.skill_profile),
            personality_profile=dict(executor.personality_profile),
            aesthetic_profile=dict(executor.aesthetic_profile),
        ),
        budget_policy=CompileRequestBudgetPolicy(
            max_input_tokens=3000,
            overflow_policy=BOARD_ADVISORY_ANALYSIS_OVERFLOW_POLICY,
        ),
        governance_mode_slice=_build_governance_mode_slice(current_profile),
        org_context=CompileRequestOrgContext.model_validate(org_context),
        retrieval_plan=CompileRequestRetrievalPlan(
            scope_tenant_id=str(workflow.get("tenant_id") or DEFAULT_TENANT_ID),
            scope_workspace_id=str(workflow.get("workspace_id") or DEFAULT_WORKSPACE_ID),
            exclude_workflow_id=workflow_id,
            normalized_terms=[],
            max_hits_by_channel={},
        ),
        explicit_sources=explicit_sources,
        retrieved_summaries=[],
        execution=CompileRequestExecution(
            acceptance_criteria=list(created_spec["acceptance_criteria"]),
            allowed_tools=[],
            allowed_write_set=list(created_spec["allowed_write_set"]),
            forced_skill_ids=list(created_spec["forced_skill_ids"]),
            input_artifact_refs=[],
            input_process_asset_refs=list(process_asset_refs),
            required_read_refs=[],
            doc_update_requirements=[],
            project_workspace_ref=None,
            project_checkout_ref=None,
            project_checkout_path=None,
            git_branch_ref=None,
            deliverable_kind="structured_document_delivery",
            git_policy="no_git_required",
        ),
        governance=CompileRequestGovernance(
            retry_budget=0,
            timeout_sla_sec=900,
            escalation_policy=TicketEscalationPolicy.model_validate(created_spec["escalation_policy"]),
        ),
    )


def _persist_compile_artifacts(
    repository: ControlPlaneRepository,
    connection,
    compile_request: CompileRequest,
):
    artifacts = compile_audit_artifacts(compile_request)
    repository.save_compiled_context_bundle(connection, artifacts.compiled_context_bundle)
    repository.save_compile_manifest(connection, artifacts.compile_manifest)
    repository.save_compiled_execution_package(
        connection,
        artifacts.compiled_execution_package,
        compiled_at=artifacts.compile_manifest.compile_meta.compiled_at,
    )
    return artifacts


def _execute_live_provider_mode(
    repository: ControlPlaneRepository,
    *,
    execution_package,
    selection: RuntimeProviderSelection,
) -> _LiveExecutionResult:
    if repository.has_open_circuit_breaker_for_provider(selection.provider.provider_id):
        raise RuntimeError("Provider execution is currently paused by an open incident.")

    if selection.provider.adapter_kind == RuntimeProviderAdapterKind.OPENAI_COMPAT:
        from app.core.runtime import _build_openai_compat_provider_config

        if not all((selection.provider.base_url, selection.provider.api_key, selection.actual_model or selection.provider.model)):
            raise RuntimeError("Provider config is incomplete for OpenAI Compat execution.")
        provider_result = invoke_openai_compat_response(
            _build_openai_compat_provider_config(selection),
            execution_package.rendered_execution_payload,
        )
        provider_response_id = provider_result.response_id
    else:
        from app.core.runtime import _build_claude_code_provider_config

        if not all((selection.provider.command_path, selection.actual_model or selection.provider.model)):
            raise RuntimeError("Provider config is incomplete for Claude Code execution.")
        provider_result = invoke_claude_code_response(
            _build_claude_code_provider_config(selection),
            execution_package.rendered_execution_payload,
        )
        provider_response_id = None

    proposal_payload = load_openai_compat_result_payload(provider_result)
    validate_output_payload(
        schema_ref=GRAPH_PATCH_PROPOSAL_SCHEMA_REF,
        schema_version=GRAPH_PATCH_PROPOSAL_SCHEMA_VERSION,
        submitted_schema_version=f"{GRAPH_PATCH_PROPOSAL_SCHEMA_REF}_v{GRAPH_PATCH_PROPOSAL_SCHEMA_VERSION}",
        payload=proposal_payload,
    )
    return _LiveExecutionResult(
        proposal_payload=proposal_payload,
        selection_summary={
            "provider_model_entry_ref": selection.provider_model_entry_ref,
            "preferred_provider_id": selection.preferred_provider_id,
            "preferred_model": selection.preferred_model,
            "actual_provider_id": selection.provider.provider_id,
            "actual_model": selection.actual_model or selection.provider.model,
            "selection_reason": selection.selection_reason,
            "policy_reason": selection.policy_reason,
            "effective_max_context_window": selection.effective_max_context_window,
            "adapter_kind": selection.provider.adapter_kind,
        },
        provider_response_id=provider_response_id,
    )


def _validate_graph_patch_nodes(
    repository: ControlPlaneRepository,
    *,
    workflow_id: str,
    proposal_payload: dict[str, Any],
    connection,
) -> None:
    graph_snapshot = build_ticket_graph_snapshot(repository, workflow_id, connection=connection)
    proposal = GraphPatchProposal.model_validate(proposal_payload)
    add_node_ids = {
        str(item.node_id).strip()
        for item in proposal.add_nodes
        if str(item.node_id).strip()
    }
    referenced_existing_node_ids = {
        *proposal.freeze_node_ids,
        *proposal.unfreeze_node_ids,
        *proposal.remove_node_ids,
        *(item.old_node_id for item in proposal.replacements),
        *(item.new_node_id for item in proposal.replacements),
        *(item.source_node_id for item in proposal.edge_additions),
        *(item.target_node_id for item in proposal.edge_additions),
        *(item.source_node_id for item in proposal.edge_removals),
        *(item.target_node_id for item in proposal.edge_removals),
    }
    referenced_existing_node_ids.update(
        node_id
        for node_id in proposal.focus_node_ids
        if str(node_id).strip() and str(node_id).strip() not in add_node_ids
    )
    known_execution_node_ids = {
        str(node.runtime_node_id or node.node_id or "").strip()
        for node in graph_snapshot.nodes
        if str(node.graph_lane_kind or "") == "execution"
        and str(node.runtime_node_id or node.node_id or "").strip()
    }
    try:
        ensure_patch_targets_are_execution_node_ids(
            event_id=f"proposal:{proposal.proposal_ref}",
            referenced_node_ids=referenced_existing_node_ids,
            known_execution_node_ids=known_execution_node_ids,
        )
    except GraphIdentityResolutionError as exc:
        raise ValueError(str(exc)) from exc
    try:
        ensure_patch_targets_are_execution_node_ids(
            event_id=f"proposal:{proposal.proposal_ref}:add_nodes",
            referenced_node_ids=add_node_ids,
            known_execution_node_ids=known_execution_node_ids | add_node_ids,
        )
    except GraphIdentityResolutionError as exc:
        raise ValueError(str(exc)) from exc
    duplicate_add_node_ids = sorted(node_id for node_id in add_node_ids if node_id in known_execution_node_ids)
    if duplicate_add_node_ids:
        raise ValueError(
            "graph patch proposal add_nodes must use new node ids: "
            + ", ".join(duplicate_add_node_ids)
        )
    for added_node in proposal.add_nodes:
        try:
            ensure_patch_targets_are_execution_node_ids(
                event_id=f"proposal:{proposal.proposal_ref}:add_node:{added_node.node_id}",
                referenced_node_ids=[
                    added_node.parent_node_id,
                    *list(added_node.dependency_node_ids or []),
                ],
                known_execution_node_ids=known_execution_node_ids,
            )
        except GraphIdentityResolutionError as exc:
            raise ValueError(str(exc)) from exc


def _build_selection_summary_from_failure(
    selection,
    *,
    failure_detail: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if selection is None and not failure_detail:
        return None
    summary = dict(failure_detail or {})
    if selection is not None:
        summary.setdefault("provider_model_entry_ref", selection.provider_model_entry_ref)
        summary.setdefault("preferred_provider_id", selection.preferred_provider_id)
        summary.setdefault("preferred_model", selection.preferred_model)
        summary.setdefault("actual_provider_id", selection.provider.provider_id)
        summary.setdefault("actual_model", selection.actual_model or selection.provider.model)
        summary.setdefault("selection_reason", selection.selection_reason)
        summary.setdefault("policy_reason", selection.policy_reason)
        summary.setdefault("effective_max_context_window", selection.effective_max_context_window)
        summary.setdefault("adapter_kind", selection.provider.adapter_kind)
    return summary


def _open_board_advisory_analysis_failed_incident(
    repository: ControlPlaneRepository,
    connection,
    *,
    workflow_id: str,
    session: Mapping[str, Any],
    run: Mapping[str, Any],
    failure_phase: str,
    error_code: str,
    error_message: str,
    idempotency_key_base: str,
) -> str:
    command_id = new_prefixed_id("cmd")
    occurred_at = now_local()
    board_decision_hash = _resolve_board_decision_hash(session)
    source_graph_version = str(run.get("source_graph_version") or "")
    fingerprint = (
        f"{workflow_id}:{str(session.get('session_id') or '')}:{source_graph_version}:"
        f"{board_decision_hash}:{failure_phase}"
    )

    existing_row = connection.execute(
        """
        SELECT incident_id
        FROM incident_projection
        WHERE workflow_id = ? AND fingerprint = ? AND status = ?
        ORDER BY opened_at DESC, incident_id DESC
        LIMIT 1
        """,
        (workflow_id, fingerprint, INCIDENT_STATUS_OPEN),
    ).fetchone()
    if existing_row is not None:
        return str(existing_row["incident_id"])

    source_ticket_id, source_node_id = _resolve_source_subject(
        repository,
        connection,
        session=session,
    )
    incident_id = new_prefixed_id("inc")
    incident_payload = {
        "incident_id": incident_id,
        "ticket_id": source_ticket_id,
        "node_id": source_node_id,
        "incident_type": INCIDENT_TYPE_BOARD_ADVISORY_ANALYSIS_FAILED,
        "status": INCIDENT_STATUS_OPEN,
        "severity": "high",
        "fingerprint": fingerprint,
        "session_id": str(session.get("session_id") or ""),
        "run_id": str(run.get("run_id") or ""),
        "source_graph_version": source_graph_version,
        "board_decision_hash": board_decision_hash,
        "failure_phase": failure_phase,
        "error_code": error_code,
        "error_message": error_message,
    }
    incident_event = repository.insert_event(
        connection,
        event_type=EVENT_INCIDENT_OPENED,
        actor_type="system",
        actor_id="board-advisory-analysis",
        workflow_id=workflow_id,
        idempotency_key=f"{idempotency_key_base}:incident-opened:{failure_phase}",
        causation_id=command_id,
        correlation_id=workflow_id,
        payload=incident_payload,
        occurred_at=occurred_at,
    )
    if incident_event is None:
        raise RuntimeError("Board advisory analysis incident opening idempotency conflict.")
    breaker_event = repository.insert_event(
        connection,
        event_type=EVENT_CIRCUIT_BREAKER_OPENED,
        actor_type="system",
        actor_id="board-advisory-analysis",
        workflow_id=workflow_id,
        idempotency_key=f"{idempotency_key_base}:breaker-opened:{failure_phase}",
        causation_id=command_id,
        correlation_id=workflow_id,
        payload={
            "incident_id": incident_id,
            "ticket_id": source_ticket_id,
            "node_id": source_node_id,
            "circuit_breaker_state": CIRCUIT_BREAKER_STATE_OPEN,
            "fingerprint": fingerprint,
        },
        occurred_at=occurred_at,
    )
    if breaker_event is None:
        raise RuntimeError("Board advisory analysis breaker opening idempotency conflict.")
    return incident_id


def _persist_analysis_trace(
    repository: ControlPlaneRepository,
    connection,
    *,
    session: Mapping[str, Any],
    run: Mapping[str, Any],
    trace_payload: dict[str, Any],
    occurred_at: datetime,
) -> str:
    from app.core.approval_handlers import _save_json_artifact

    workflow_id = str(session.get("workflow_id") or "")
    session_id = str(session.get("session_id") or "")
    source_ticket_id, source_node_id = _resolve_source_subject(repository, connection, session=session)
    artifact_ref = _analysis_trace_artifact_ref(
        workflow_id=workflow_id,
        session_id=session_id,
        attempt_int=int(run.get("attempt_int") or 1),
    )
    _save_json_artifact(
        repository,
        connection,
        artifact_ref=artifact_ref,
        logical_path=_analysis_trace_logical_path(
            session_id=session_id,
            attempt_int=int(run.get("attempt_int") or 1),
        ),
        workflow_id=workflow_id,
        ticket_id=source_ticket_id,
        node_id=source_node_id,
        payload=trace_payload,
        kind="JSON",
        occurred_at=occurred_at,
    )
    return artifact_ref


def _persist_analysis_archive_if_needed(
    repository: ControlPlaneRepository,
    connection,
    *,
    session: Mapping[str, Any],
    current_profile: Mapping[str, Any],
    run: Mapping[str, Any],
    trace_payload: dict[str, Any],
    occurred_at: datetime,
) -> str | None:
    from app.core.approval_handlers import _save_json_artifact
    from app.core.board_advisory import board_advisory_requires_full_timeline_archive

    if not board_advisory_requires_full_timeline_archive(session, current_profile=current_profile):
        return None
    workflow_id = str(session.get("workflow_id") or "")
    session_id = str(session.get("session_id") or "")
    source_ticket_id, source_node_id = _resolve_source_subject(repository, connection, session=session)
    artifact_ref = _analysis_archive_artifact_ref(
        workflow_id=workflow_id,
        session_id=session_id,
        attempt_int=int(run.get("attempt_int") or 1),
    )
    _save_json_artifact(
        repository,
        connection,
        artifact_ref=artifact_ref,
        logical_path=_analysis_archive_logical_path(
            session_id=session_id,
            attempt_int=int(run.get("attempt_int") or 1),
        ),
        workflow_id=workflow_id,
        ticket_id=source_ticket_id,
        node_id=source_node_id,
        payload=trace_payload,
        kind="JSON",
        occurred_at=occurred_at,
    )
    return artifact_ref


def _refresh_full_timeline_archive_if_needed(
    repository: ControlPlaneRepository,
    connection,
    *,
    session: Mapping[str, Any],
    current_profile: Mapping[str, Any],
    occurred_at: datetime,
    latest_analysis_archive_artifact_ref: str | None = None,
) -> dict[str, Any]:
    from app.core.approval_handlers import _materialize_board_advisory_full_timeline_archive_checked

    return _materialize_board_advisory_full_timeline_archive_checked(
        repository,
        connection,
        session=dict(session),
        current_profile=dict(current_profile),
        occurred_at=occurred_at,
        latest_analysis_archive_artifact_ref=latest_analysis_archive_artifact_ref,
    )


def run_board_advisory_analysis(
    repository: ControlPlaneRepository,
    run_id: str,
) -> dict[str, Any]:
    repository.initialize()
    compile_request = None
    artifacts = None
    session = None
    run = None
    current_profile = None
    provider_selection = None
    provider_response_id = None
    proposal_payload: dict[str, Any] | None = None
    trace_payload: dict[str, Any] | None = None
    latest_analysis_archive_artifact_ref: str | None = None
    failure_phase = BOARD_ADVISORY_ANALYSIS_FAILURE_PHASE_PROVIDER_EXECUTION
    error_code = "BOARD_ADVISORY_ANALYSIS_FAILED"
    error_message = "Board advisory analysis failed."

    try:
        with repository.transaction() as connection:
            run = repository.get_board_advisory_analysis_run(run_id, connection=connection)
            if run is None:
                raise ValueError("Board advisory analysis run is missing.")
            session = repository.get_board_advisory_session(str(run.get("session_id") or ""), connection=connection)
            if session is None:
                raise ValueError("Board advisory session is missing.")
            current_profile = repository.get_latest_governance_profile(
                str(session.get("workflow_id") or ""),
                connection=connection,
            )
            if current_profile is None:
                raise ValueError("Governance profile is required before advisory analysis can run.")
            execution_plan = _resolve_analysis_execution_plan(repository)
            if execution_plan.executor is None:
                failure_phase = BOARD_ADVISORY_ANALYSIS_FAILURE_PHASE_EXECUTOR_SELECTION
                if execution_plan.failure_reason == "no_contract_matching_executor":
                    raise RuntimeError(
                        "No board-approved executor satisfies the advisory analysis execution contract."
                    )
                raise RuntimeError(
                    "Board advisory analysis requires a board-approved contract-matching executor."
                )
            if execution_plan.provider_selection is None:
                failure_phase = BOARD_ADVISORY_ANALYSIS_FAILURE_PHASE_PROVIDER_SELECTION
                raise RuntimeError(
                    "No live provider selection is available for the advisory analysis execution contract."
                )
            compile_request = _build_board_advisory_analysis_compile_request(
                repository,
                session=session,
                run=run,
                execution_plan=execution_plan,
                connection=connection,
            )
            artifacts = _persist_compile_artifacts(repository, connection, compile_request)
            repository.start_board_advisory_analysis_run(
                connection,
                run_id=run_id,
                compile_request_id=compile_request.meta.compile_request_id,
                compiled_execution_package_ref=(
                    artifacts.compiled_execution_package.meta.version_ref
                    or build_compiled_execution_package_process_asset_ref(
                        compile_request.meta.ticket_id,
                        version_int=artifacts.compiled_execution_package.meta.version_int,
                    )
                ),
                started_at=artifacts.compile_manifest.compile_meta.compiled_at,
            )
            repository.refresh_projections(connection)

        assert compile_request is not None
        assert artifacts is not None
        assert session is not None
        assert current_profile is not None
        execution_package = artifacts.compiled_execution_package
        run = repository.get_board_advisory_analysis_run(run_id)
        if run is None:
            raise ValueError("Board advisory analysis run vanished before execution.")

        execution_plan = _resolve_analysis_execution_plan(repository)
        if execution_plan.executor is None:
            failure_phase = BOARD_ADVISORY_ANALYSIS_FAILURE_PHASE_EXECUTOR_SELECTION
            if execution_plan.failure_reason == "no_contract_matching_executor":
                raise RuntimeError(
                    "No board-approved executor satisfies the advisory analysis execution contract."
                )
            raise RuntimeError(
                "Board advisory analysis requires a board-approved contract-matching executor."
            )
        provider_selection = execution_plan.provider_selection
        if provider_selection is None:
            failure_phase = BOARD_ADVISORY_ANALYSIS_FAILURE_PHASE_PROVIDER_SELECTION
            raise RuntimeError(
                "No live provider selection is available for the advisory analysis execution contract."
            )
        failure_phase = BOARD_ADVISORY_ANALYSIS_FAILURE_PHASE_PROVIDER_EXECUTION
        live_result = _execute_live_provider_mode(
            repository,
            execution_package=execution_package,
            selection=provider_selection,
        )
        proposal_payload = dict(live_result.proposal_payload)
        provider_response_id = live_result.provider_response_id

        with repository.transaction() as connection:
            run = repository.get_board_advisory_analysis_run(run_id, connection=connection)
            session = repository.get_board_advisory_session(str(run.get("session_id") or ""), connection=connection) if run else None
            current_profile = repository.get_latest_governance_profile(str(session.get("workflow_id") or ""), connection=connection) if session else None
            if run is None or session is None or current_profile is None:
                raise ValueError("Advisory analysis run context is missing.")
            if str(run.get("source_graph_version") or "") != str(session.get("source_version") or ""):
                failure_phase = BOARD_ADVISORY_ANALYSIS_FAILURE_PHASE_GRAPH_VERSION_STALE
                raise ValueError("Board advisory analysis run is stale against the latest graph version.")
            failure_phase = BOARD_ADVISORY_ANALYSIS_FAILURE_PHASE_NODE_VALIDATION
            _validate_graph_patch_nodes(
                repository,
                workflow_id=str(session.get("workflow_id") or ""),
                proposal_payload=dict(proposal_payload or {}),
                connection=connection,
            )

            failure_phase = BOARD_ADVISORY_ANALYSIS_FAILURE_PHASE_TRACE_MATERIALIZATION
            trace_payload = {
                "run_id": str(run.get("run_id") or ""),
                "session_id": str(session.get("session_id") or ""),
                "workflow_id": str(session.get("workflow_id") or ""),
                "source_graph_version": str(run.get("source_graph_version") or ""),
                "executor_mode": str(run.get("executor_mode") or ""),
                "input_process_asset_refs": list(compile_request.execution.input_process_asset_refs),
                "compile_request_id": compile_request.meta.compile_request_id,
                "compiled_context_bundle_ref": (
                    artifacts.compiled_context_bundle.meta.version_ref
                    or build_compiled_context_bundle_process_asset_ref(
                        compile_request.meta.ticket_id,
                        version_int=artifacts.compiled_context_bundle.meta.version_int,
                    )
                ),
                "compile_manifest_ref": (
                    artifacts.compile_manifest.compile_meta.version_ref
                    or build_compile_manifest_process_asset_ref(
                        compile_request.meta.ticket_id,
                        version_int=artifacts.compile_manifest.compile_meta.version_int,
                    )
                ),
                "compiled_execution_package_ref": (
                    artifacts.compiled_execution_package.meta.version_ref
                    or build_compiled_execution_package_process_asset_ref(
                        compile_request.meta.ticket_id,
                        version_int=artifacts.compiled_execution_package.meta.version_int,
                    )
                ),
                "provider_selection": _build_selection_summary_from_failure(
                    provider_selection,
                    failure_detail=None,
                ),
                "provider_response_id": provider_response_id,
                "result_status": "SUCCEEDED",
                "proposal_ref": str(proposal_payload.get("proposal_ref") or ""),
                "proposal_summary": str(proposal_payload.get("proposal_summary") or ""),
                "error_code": None,
                "error_message": None,
            }
            trace_artifact_ref = _persist_analysis_trace(
                repository,
                connection,
                session=session,
                run=run,
                trace_payload=trace_payload,
                occurred_at=now_local(),
            )

            proposal_ref = str(proposal_payload.get("proposal_ref") or "").strip()
            if not proposal_ref:
                raise ValueError("Advisory analysis result is missing proposal_ref.")

            from app.core.approval_handlers import _save_json_artifact
            from app.core.board_advisory import (
                advisory_patch_proposal_artifact_ref,
                advisory_patch_proposal_logical_path,
            )

            source_ticket_id, source_node_id = _resolve_source_subject(repository, connection, session=session)
            _save_json_artifact(
                repository,
                connection,
                artifact_ref=advisory_patch_proposal_artifact_ref(
                    workflow_id=str(session.get("workflow_id") or ""),
                    session_id=str(session.get("session_id") or ""),
                ),
                logical_path=advisory_patch_proposal_logical_path(
                    session_id=str(session.get("session_id") or ""),
                ),
                workflow_id=str(session.get("workflow_id") or ""),
                ticket_id=source_ticket_id,
                node_id=source_node_id,
                payload=proposal_payload,
                kind="JSON",
                occurred_at=now_local(),
            )

            decision_pack_refs = list(session.get("decision_pack_refs") or [])
            if proposal_ref not in decision_pack_refs:
                decision_pack_refs.append(proposal_ref)
            updated_session = repository.store_board_advisory_patch_proposal(
                connection,
                session_id=str(session.get("session_id") or ""),
                proposal_ref=proposal_ref,
                proposal=dict(proposal_payload),
                decision_pack_refs=decision_pack_refs,
                updated_at=now_local(),
            )
            repository.complete_board_advisory_analysis_run(
                connection,
                run_id=str(run.get("run_id") or ""),
                proposal_ref=proposal_ref,
                analysis_trace_artifact_ref=trace_artifact_ref,
                finished_at=now_local(),
            )
            updated_session = repository.get_board_advisory_session(
                str(session.get("session_id") or ""),
                connection=connection,
            )
            if updated_session is None:
                raise RuntimeError("Board advisory session row vanished after analysis completion.")
            failure_phase = BOARD_ADVISORY_ANALYSIS_FAILURE_PHASE_ARCHIVE_MATERIALIZATION
            latest_analysis_archive_artifact_ref = _persist_analysis_archive_if_needed(
                repository,
                connection,
                session=updated_session,
                current_profile=current_profile,
                run=run,
                trace_payload=trace_payload,
                occurred_at=now_local(),
            )
            updated_session = _refresh_full_timeline_archive_if_needed(
                repository,
                connection,
                session=updated_session,
                current_profile=current_profile,
                occurred_at=now_local(),
                latest_analysis_archive_artifact_ref=latest_analysis_archive_artifact_ref,
            )
            completion_event = repository.insert_event(
                connection,
                event_type=EVENT_BOARD_ADVISORY_ANALYSIS_COMPLETED,
                actor_type="system",
                actor_id="board-advisory-analysis",
                workflow_id=str(session.get("workflow_id") or ""),
                idempotency_key=f"board-advisory-analysis-run:{run_id}:completed",
                causation_id=None,
                correlation_id=str(session.get("workflow_id") or ""),
                payload={
                    "run_id": str(run.get("run_id") or ""),
                    "session_id": str(session.get("session_id") or ""),
                    "approval_id": str(session.get("approval_id") or ""),
                    "review_pack_id": str(session.get("review_pack_id") or ""),
                    "proposal_ref": proposal_ref,
                    "proposal_summary": str(proposal_payload.get("proposal_summary") or ""),
                    "status": "PENDING_BOARD_CONFIRMATION",
                },
                occurred_at=now_local(),
            )
            if completion_event is None:
                raise RuntimeError("Board advisory analysis completion idempotency conflict.")
            repository.refresh_projections(connection)
            return updated_session
    except Exception as exc:
        error_message = str(exc)
        error_code = (
            getattr(exc, "failure_kind", None)
            or getattr(exc, "__class__", type(exc)).__name__
            or "BOARD_ADVISORY_ANALYSIS_FAILED"
        )
        if session is None:
            raise
        normalize_provider_failure_detail = None
        if provider_selection is not None or hasattr(exc, "failure_detail"):
            from app.core.runtime import _normalize_provider_failure_detail as normalize_provider_failure_detail
        if trace_payload is None:
            trace_payload = {
                "run_id": str((run or {}).get("run_id") or ""),
                "session_id": str((session or {}).get("session_id") or ""),
                "workflow_id": str((session or {}).get("workflow_id") or ""),
                "source_graph_version": str((run or {}).get("source_graph_version") or ""),
                "executor_mode": str((run or {}).get("executor_mode") or ""),
                "input_process_asset_refs": list((compile_request.execution.input_process_asset_refs if compile_request else [])),
                "compile_request_id": (compile_request.meta.compile_request_id if compile_request else None),
                "compiled_execution_package_ref": (
                    artifacts.compiled_execution_package.meta.version_ref
                    if artifacts is not None
                    else None
                ),
                "provider_selection": _build_selection_summary_from_failure(
                    provider_selection,
                    failure_detail=(
                        normalize_provider_failure_detail(
                            getattr(exc, "failure_detail", {}) if hasattr(exc, "failure_detail") else {},
                            selection=provider_selection,
                            attempt_count=1,
                            fallback_applied=False,
                        )
                        if normalize_provider_failure_detail is not None
                        else None
                    ),
                ),
                "provider_response_id": provider_response_id,
                "result_status": "FAILED",
                "proposal_ref": None,
                "proposal_summary": None,
                "error_code": error_code,
                "error_message": error_message,
                "failure_phase": failure_phase,
            }
        with repository.transaction() as connection:
            run = repository.get_board_advisory_analysis_run(run_id, connection=connection)
            session = repository.get_board_advisory_session(str(run.get("session_id") or ""), connection=connection) if run else None
            current_profile = repository.get_latest_governance_profile(str(session.get("workflow_id") or ""), connection=connection) if session else None
            if run is None or session is None or current_profile is None:
                raise
            analysis_trace_artifact_ref = None
            try:
                analysis_trace_artifact_ref = _persist_analysis_trace(
                    repository,
                    connection,
                    session=session,
                    run=run,
                    trace_payload=trace_payload,
                    occurred_at=now_local(),
                )
            except Exception as trace_exc:
                failure_phase = BOARD_ADVISORY_ANALYSIS_FAILURE_PHASE_TRACE_MATERIALIZATION
                error_code = trace_exc.__class__.__name__
                error_message = str(trace_exc)
                analysis_trace_artifact_ref = None
            incident_id = _open_board_advisory_analysis_failed_incident(
                repository,
                connection,
                workflow_id=str(session.get("workflow_id") or ""),
                session=session,
                run=run,
                failure_phase=failure_phase,
                error_code=error_code,
                error_message=error_message,
                idempotency_key_base=f"board-advisory-analysis:{run_id}",
            )
            repository.fail_board_advisory_analysis_run(
                connection,
                run_id=str(run.get("run_id") or ""),
                incident_id=incident_id,
                error_code=error_code,
                error_message=error_message,
                analysis_trace_artifact_ref=analysis_trace_artifact_ref,
                finished_at=now_local(),
            )
            updated_session = repository.get_board_advisory_session(str(session.get("session_id") or ""), connection=connection)
            if updated_session is None:
                raise RuntimeError("Board advisory session row vanished after analysis failure.")
            updated_session = _refresh_full_timeline_archive_if_needed(
                repository,
                connection,
                session=updated_session,
                current_profile=current_profile,
                occurred_at=now_local(),
                latest_analysis_archive_artifact_ref=None,
            )
            rejection_event = repository.insert_event(
                connection,
                event_type=EVENT_BOARD_ADVISORY_ANALYSIS_REJECTED,
                actor_type="system",
                actor_id="board-advisory-analysis",
                workflow_id=str(session.get("workflow_id") or ""),
                idempotency_key=f"board-advisory-analysis-run:{run_id}:rejected",
                causation_id=None,
                correlation_id=str(session.get("workflow_id") or ""),
                payload={
                    "run_id": str(run.get("run_id") or ""),
                    "session_id": str(session.get("session_id") or ""),
                    "approval_id": str(session.get("approval_id") or ""),
                    "review_pack_id": str(session.get("review_pack_id") or ""),
                    "incident_id": incident_id,
                    "error_code": error_code,
                    "error_message": error_message,
                    "status": BOARD_ADVISORY_STATUS_ANALYSIS_REJECTED,
                },
                occurred_at=now_local(),
            )
            if rejection_event is None:
                raise RuntimeError("Board advisory analysis rejection idempotency conflict.")
            repository.refresh_projections(connection)
            return updated_session
