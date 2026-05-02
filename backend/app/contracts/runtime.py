from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import Field

from app.contracts.common import StrictModel
from app.contracts.scope import TenantWorkspaceScope
from app.contracts.commands import TicketEscalationPolicy
from app.contracts.governance import GovernanceModeSlice
from app.contracts.process_assets import ProcessAssetKind


class ExecutionAttemptState(StrEnum):
    CREATED = "CREATED"
    LEASED = "LEASED"
    PROVIDER_CONNECTING = "PROVIDER_CONNECTING"
    STREAMING = "STREAMING"
    COMPLETED = "COMPLETED"
    FAILED_RETRYABLE = "FAILED_RETRYABLE"
    FAILED_TERMINAL = "FAILED_TERMINAL"
    TIMED_OUT = "TIMED_OUT"
    CANCELLED = "CANCELLED"


class ExecutionAttempt(StrictModel):
    attempt_id: str = Field(min_length=1)
    workflow_id: str = Field(min_length=1)
    ticket_id: str = Field(min_length=1)
    node_id: str = Field(min_length=1)
    attempt_no: int = Field(ge=1)
    idempotency_key: str = Field(min_length=1)
    provider_policy_ref: str = Field(min_length=1)
    deadline_at: datetime
    last_heartbeat_at: datetime | None = None
    state: ExecutionAttemptState
    failure_kind: str | None = None
    failure_fingerprint: str | None = None


class CompileRequestMeta(TenantWorkspaceScope):
    compile_request_id: str = Field(min_length=1)
    ticket_id: str = Field(min_length=1)
    workflow_id: str = Field(min_length=1)
    node_id: str = Field(min_length=1)
    attempt_no: int = Field(ge=1)
    governance_profile_ref: str = Field(min_length=1)
    graph_version: str = Field(min_length=1)
    asset_digest: str = Field(min_length=1)
    idempotency_key: str = Field(min_length=1)
    ticket_projection_version: int | None = Field(default=None, ge=1)
    node_projection_version: int | None = Field(default=None, ge=1)
    runtime_node_projection_version: int | None = Field(default=None, ge=1)
    source_projection_version: int | None = Field(default=None, ge=1)


class CompileRequestControlRefs(StrictModel):
    role_profile_ref: str = Field(min_length=1)
    constraints_ref: str = Field(min_length=1)
    output_schema_ref: str = Field(min_length=1)
    output_schema_version: int = Field(ge=1)


class CompileRequestWorkerBinding(TenantWorkspaceScope):
    actor_id: str = Field(min_length=1)
    assignment_id: str = Field(min_length=1)
    lease_id: str = Field(min_length=1)
    lease_owner: str = Field(min_length=1)
    employee_id: str = Field(min_length=1)
    employee_role_type: str = Field(min_length=1)
    skill_profile: dict[str, Any] = Field(default_factory=dict)
    personality_profile: dict[str, Any] = Field(default_factory=dict)
    aesthetic_profile: dict[str, Any] = Field(default_factory=dict)


class CompileRequestBudgetPolicy(StrictModel):
    max_input_tokens: int = Field(ge=1)
    overflow_policy: Literal["FAIL_CLOSED"]


class CompileRequestRetrievalPlan(StrictModel):
    scope_tenant_id: str = Field(min_length=1)
    scope_workspace_id: str = Field(min_length=1)
    exclude_workflow_id: str = Field(min_length=1)
    normalized_terms: list[str] = Field(default_factory=list)
    max_hits_by_channel: dict[str, int] = Field(default_factory=dict)


class CompileRequestRetrievedSummary(StrictModel):
    channel: Literal["review_summaries", "incident_summaries", "artifact_summaries"]
    source_ref: str = Field(min_length=1)
    source_workflow_id: str = Field(min_length=1)
    source_ticket_id: str | None = None
    headline: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    matched_terms: list[str] = Field(default_factory=list)
    why_it_matched: str = Field(min_length=1)
    review_pack_id: str | None = None
    incident_id: str | None = None
    artifact_ref: str | None = None
    preview_url: str | None = None


class CompiledArtifactAccessDescriptor(StrictModel):
    artifact_ref: str = Field(min_length=1)
    logical_path: str | None = None
    kind: str | None = None
    media_type: str | None = None
    preview_kind: Literal["TEXT", "JSON", "INLINE_MEDIA", "DOWNLOAD_ONLY"] | None = None
    display_hint: Literal[
        "INLINE_BODY",
        "OPEN_PREVIEW_URL",
        "DOWNLOAD_ATTACHMENT",
        "OPEN_CONTENT_URL",
    ] | None = None
    materialization_status: str = Field(min_length=1)
    lifecycle_status: str = Field(min_length=1)
    size_bytes: int | None = Field(default=None, ge=0)
    content_hash: str | None = None
    content_url: str | None = None
    preview_url: str | None = None
    download_url: str | None = None


class CompileRequestExplicitSource(StrictModel):
    source_ref: str = Field(min_length=1)
    source_kind: Literal["PROCESS_ASSET"]
    process_asset_kind: ProcessAssetKind
    producer_ticket_id: str | None = None
    source_summary: str | None = None
    consumable_by: list[str] = Field(default_factory=list)
    source_metadata: dict[str, Any] = Field(default_factory=dict)
    is_mandatory: bool = True
    artifact_access: CompiledArtifactAccessDescriptor | None = None
    inline_content_type: Literal["TEXT", "JSON"] | None = None
    inline_content_text: str | None = None
    inline_content_json: dict[str, Any] | None = None
    inline_fallback_reason: str | None = None
    inline_fallback_reason_code: str | None = None
    inline_content_truncated: bool = False
    inline_preview_strategy: str | None = None
    fragment_selector_type: Literal["MARKDOWN_SECTION", "TEXT_WINDOW", "JSON_PATH"] | None = None
    fragment_selector_value: str | None = None
    fragment_content_type: Literal["TEXT", "JSON"] | None = None
    fragment_content_text: str | None = None
    fragment_content_json: dict[str, Any] | None = None
    fragment_metadata: dict[str, Any] = Field(default_factory=dict)


class CompileRequestOrgRelation(StrictModel):
    ticket_id: str = Field(min_length=1)
    node_id: str = Field(min_length=1)
    role_profile_ref: str = Field(min_length=1)
    role_type: str = Field(min_length=1)
    employee_id: str | None = None
    status: str | None = None
    relation_reason: str = Field(min_length=1)


class CompileRequestEscalationPath(StrictModel):
    current_blocking_reason: str | None = None
    open_review_pack_id: str | None = None
    open_incident_id: str | None = None
    path: list[str] = Field(default_factory=list)


class CompileRequestResponsibilityBoundary(StrictModel):
    delivery_stage: str | None = None
    output_schema_ref: str = Field(min_length=1)
    allowed_write_set: list[str] = Field(default_factory=list)
    board_review_possible: bool = False
    incident_path_possible: bool = False


class CompileRequestOrgContext(StrictModel):
    upstream_provider: CompileRequestOrgRelation | None = None
    downstream_reviewer: CompileRequestOrgRelation | None = None
    collaborators: list[CompileRequestOrgRelation] = Field(default_factory=list)
    escalation_path: CompileRequestEscalationPath
    responsibility_boundary: CompileRequestResponsibilityBoundary


class CompileRequestExecution(StrictModel):
    acceptance_criteria: list[str] = Field(default_factory=list)
    allowed_tools: list[str] = Field(default_factory=list)
    allowed_write_set: list[str] = Field(default_factory=list)
    forced_skill_ids: list[str] = Field(default_factory=list)
    input_artifact_refs: list[str] = Field(default_factory=list)
    input_process_asset_refs: list[str] = Field(default_factory=list)
    required_read_refs: list[str] = Field(default_factory=list)
    doc_update_requirements: list[str] = Field(default_factory=list)
    project_workspace_ref: str | None = None
    project_checkout_ref: str | None = None
    project_checkout_path: str | None = None
    git_branch_ref: str | None = None
    deliverable_kind: str | None = None
    git_policy: str | None = None


class CompileRequestGovernance(StrictModel):
    retry_budget: int = Field(ge=0)
    timeout_sla_sec: int = Field(ge=1)
    escalation_policy: TicketEscalationPolicy


class CompileRequest(StrictModel):
    meta: CompileRequestMeta
    control_refs: CompileRequestControlRefs
    worker_binding: CompileRequestWorkerBinding
    budget_policy: CompileRequestBudgetPolicy
    governance_mode_slice: GovernanceModeSlice
    org_context: CompileRequestOrgContext
    retrieval_plan: CompileRequestRetrievalPlan
    explicit_sources: list[CompileRequestExplicitSource]
    retrieved_summaries: list[CompileRequestRetrievedSummary] = Field(default_factory=list)
    execution: CompileRequestExecution
    governance: CompileRequestGovernance


class CompiledContextBundleMeta(StrictModel):
    bundle_id: str = Field(min_length=1)
    compile_request_id: str = Field(min_length=1)
    ticket_id: str = Field(min_length=1)
    workflow_id: str = Field(min_length=1)
    node_id: str = Field(min_length=1)
    attempt_no: int = Field(ge=1)
    version_ref: str | None = None
    version_int: int | None = Field(default=None, ge=1)
    supersedes_ref: str | None = None
    compiler_version: str = Field(min_length=1)
    compiled_at: datetime
    model_profile: str = Field(min_length=1)
    render_target: str = Field(min_length=1)
    is_degraded: bool


class CompiledOutputContract(StrictModel):
    schema_ref: str = Field(min_length=1)
    schema_version: int = Field(ge=1)
    schema_body: dict[str, Any] = Field(default_factory=dict)


class CompiledSystemControls(StrictModel):
    role_profile: dict[str, Any] = Field(default_factory=dict)
    organization_context: CompileRequestOrgContext
    governance_mode_slice: GovernanceModeSlice | None = None
    required_doc_surfaces: list[str] = Field(default_factory=list)
    skill_binding: dict[str, Any] = Field(default_factory=dict)
    hard_rules: list[str] = Field(default_factory=list)
    board_constraints: list[str] = Field(default_factory=list)
    output_contract: CompiledOutputContract
    allowed_write_set: list[str] = Field(default_factory=list)


class CompiledTaskDefinition(StrictModel):
    task_type: str | None = None
    atomic_task: str = Field(min_length=1)
    acceptance_criteria: list[str] = Field(default_factory=list)
    risk_class: Literal["low", "medium", "high", "critical"] | None = None
    budget_profile: str | None = None


class CompiledContextSelector(StrictModel):
    selector_type: str = Field(min_length=1)
    selector_value: str = Field(min_length=1)


class CompiledContextBlock(StrictModel):
    block_id: str = Field(min_length=1)
    source_ref: str = Field(min_length=1)
    source_kind: Literal["PROCESS_ASSET", "RETRIEVAL_SUMMARY"]
    trust_level: Literal[1, 2, 3]
    instruction_authority: Literal["DATA_ONLY"]
    priority_class: Literal["P1", "P2", "P3"]
    selector: CompiledContextSelector
    transform_chain: list[str] = Field(default_factory=list)
    content_type: Literal["JSON", "TEXT", "SOURCE_DESCRIPTOR"]
    content_mode: Literal["INLINE_FULL", "INLINE_FRAGMENT", "INLINE_PARTIAL", "REFERENCE_ONLY"]
    content_payload: dict[str, Any] = Field(default_factory=dict)
    degradation_reason_code: str | None = None
    token_estimate: int = Field(ge=1)
    relevance_score: float = Field(ge=0.0)
    source_hash: str = Field(min_length=1)
    trust_note: str = Field(min_length=1)


class CompiledRenderHints(StrictModel):
    preferred_section_order: list[str] = Field(default_factory=list)
    sandbox_untrusted_data: bool = True
    preferred_markup: Literal["json_messages", "markdown", "xml", "provider_native"]


class CompiledContextBundle(StrictModel):
    meta: CompiledContextBundleMeta
    system_controls: CompiledSystemControls
    task_definition: CompiledTaskDefinition
    context_blocks: list[CompiledContextBlock] = Field(default_factory=list)
    render_hints: CompiledRenderHints


class CompileManifestMeta(StrictModel):
    compile_id: str = Field(min_length=1)
    bundle_id: str = Field(min_length=1)
    compile_request_id: str = Field(min_length=1)
    ticket_id: str = Field(min_length=1)
    workflow_id: str = Field(min_length=1)
    node_id: str = Field(min_length=1)
    attempt_no: int = Field(ge=1)
    version_ref: str | None = None
    version_int: int | None = Field(default=None, ge=1)
    supersedes_ref: str | None = None
    compiler_version: str = Field(min_length=1)
    compiled_at: datetime
    duration_ms: int = Field(ge=0)
    model_profile: str = Field(min_length=1)
    cache_key: str = Field(min_length=1)


class CompileManifestArtifactHash(StrictModel):
    artifact_id: str = Field(min_length=1)
    hash: str = Field(min_length=1)


class CompileManifestInputFingerprint(StrictModel):
    ticket_hash: str = Field(min_length=1)
    role_profile_version: str = Field(min_length=1)
    constraints_version: str = Field(min_length=1)
    output_schema_version: str = Field(min_length=1)
    artifact_hashes: list[CompileManifestArtifactHash] = Field(default_factory=list)


class CompileManifestBudgetPlan(StrictModel):
    total_budget_tokens: int = Field(ge=0)
    reserved_p0: int = Field(ge=0)
    reserved_p1: int = Field(ge=0)
    reserved_p2: int = Field(ge=0)
    reserved_p3: int = Field(ge=0)
    soft_limit_tokens: int = Field(ge=0)
    hard_limit_tokens: int = Field(ge=0)


class CompileManifestBudgetActual(StrictModel):
    used_p0: int = Field(ge=0)
    used_p1: int = Field(ge=0)
    used_p2: int = Field(ge=0)
    used_p3: int = Field(ge=0)
    final_bundle_tokens: int = Field(ge=0)
    truncated_tokens: int = Field(ge=0)


class CompileManifestSourceLogEntry(StrictModel):
    source_ref: str = Field(min_length=1)
    source_kind: str = Field(min_length=1)
    priority_class: str | None = None
    trust_level: int | None = Field(default=None, ge=0)
    selector_used: str | None = None
    content_mode: str | None = None
    critical: bool = False
    status: Literal["USED", "CACHE_HIT", "SUMMARIZED", "TRUNCATED", "DROPPED", "MISSING"]
    tokens_before: int | None = Field(default=None, ge=0)
    tokens_after: int | None = Field(default=None, ge=0)
    reason: str | None = None
    reason_code: str | None = None


class CompileManifestTransformLogEntry(StrictModel):
    stage: str = Field(min_length=1)
    operation_type: Literal[
        "HYDRATE",
        "RETRIEVE",
        "AST_SKELETON",
        "SUMMARIZE",
        "TRUNCATE",
        "DROP",
        "NORMALIZE",
        "RENDER_PREP",
    ]
    target_ref: str | None = None
    output_block_id: str | None = None
    reason: str | None = None


class CompileManifestDegradation(StrictModel):
    is_degraded: bool
    fail_mode: Literal["FAIL_CLOSED", "BEST_EFFORT"]
    missing_critical_sources: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class CompileManifestCacheReport(StrictModel):
    cache_hit: bool
    reused_from_compile_id: str | None = None
    invalidated_by: list[str] = Field(default_factory=list)


class CompileManifestFinalBundleStats(StrictModel):
    context_block_count: int = Field(ge=0)
    trusted_block_count: int = Field(ge=0)
    reference_block_count: int = Field(ge=0)
    hydrated_block_count: int = Field(ge=0)
    fragment_block_count: int = Field(ge=0)
    partially_hydrated_block_count: int = Field(ge=0)
    negative_pattern_count: int = Field(ge=0)
    retrieved_block_count: int = Field(default=0, ge=0)
    dropped_retrieval_count: int = Field(default=0, ge=0)
    dropped_explicit_source_count: int = Field(default=0, ge=0)


class CompileManifest(StrictModel):
    compile_meta: CompileManifestMeta
    input_fingerprint: CompileManifestInputFingerprint
    budget_plan: CompileManifestBudgetPlan
    budget_actual: CompileManifestBudgetActual
    source_log: list[CompileManifestSourceLogEntry] = Field(default_factory=list)
    transform_log: list[CompileManifestTransformLogEntry] = Field(default_factory=list)
    degradation: CompileManifestDegradation
    cache_report: CompileManifestCacheReport
    final_bundle_stats: CompileManifestFinalBundleStats


class CompiledExecutionPackageMeta(TenantWorkspaceScope):
    compile_request_id: str = Field(min_length=1)
    ticket_id: str = Field(min_length=1)
    workflow_id: str = Field(min_length=1)
    node_id: str = Field(min_length=1)
    attempt_no: int = Field(ge=1)
    governance_profile_ref: str = Field(min_length=1)
    graph_version: str = Field(min_length=1)
    asset_digest: str = Field(min_length=1)
    idempotency_key: str = Field(min_length=1)
    version_ref: str | None = None
    version_int: int | None = Field(default=None, ge=1)
    supersedes_ref: str | None = None
    actor_id: str = Field(min_length=1)
    assignment_id: str = Field(min_length=1)
    lease_id: str = Field(min_length=1)
    lease_owner: str = Field(min_length=1)
    compiler_version: str = Field(min_length=1)
    ticket_projection_version: int | None = Field(default=None, ge=1)
    node_projection_version: int | None = Field(default=None, ge=1)
    runtime_node_projection_version: int | None = Field(default=None, ge=1)
    source_projection_version: int | None = Field(default=None, ge=1)


class CompiledRole(StrictModel):
    role_profile_ref: str = Field(min_length=1)
    employee_id: str = Field(min_length=1)
    employee_role_type: str = Field(min_length=1)
    skill_profile: dict[str, Any] = Field(default_factory=dict)
    personality_profile: dict[str, Any] = Field(default_factory=dict)
    aesthetic_profile: dict[str, Any] = Field(default_factory=dict)
    persona_summary: str = Field(min_length=1)


class CompiledConstraints(StrictModel):
    constraints_ref: str = Field(min_length=1)
    global_rules: list[str] = Field(default_factory=list)
    board_constraints: list[str] = Field(default_factory=list)
    budget_constraints: dict[str, Any] = Field(default_factory=dict)


class AtomicContextBlock(StrictModel):
    block_id: str = Field(min_length=1)
    source_ref: str = Field(min_length=1)
    source_kind: Literal["PROCESS_ASSET", "RETRIEVAL"]
    selector: CompiledContextSelector
    content_type: Literal["TEXT", "JSON", "SOURCE_DESCRIPTOR"]
    content_mode: Literal["INLINE_FULL", "INLINE_FRAGMENT", "INLINE_PARTIAL", "REFERENCE_ONLY"]
    content_payload: dict[str, Any] = Field(default_factory=dict)
    degradation_reason_code: str | None = None


class AtomicContextBundle(StrictModel):
    context_blocks: list[AtomicContextBlock] = Field(default_factory=list)
    token_budget: int = Field(ge=1)


class RenderedExecutionPayloadMeta(StrictModel):
    bundle_id: str = Field(min_length=1)
    compile_id: str = Field(min_length=1)
    compile_request_id: str = Field(min_length=1)
    ticket_id: str = Field(min_length=1)
    workflow_id: str = Field(min_length=1)
    node_id: str = Field(min_length=1)
    compiler_version: str = Field(min_length=1)
    model_profile: str = Field(min_length=1)
    render_target: Literal["json_messages_v1"]
    rendered_at: datetime


class RenderedExecutionMessage(StrictModel):
    role: Literal["system", "user"]
    channel: Literal[
        "SYSTEM_CONTROLS",
        "TASK_DEFINITION",
        "CONTEXT_BLOCK",
        "OUTPUT_CONTRACT_REMINDER",
    ]
    content_type: Literal["TEXT", "JSON", "SOURCE_DESCRIPTOR"]
    content_payload: dict[str, Any] = Field(default_factory=dict)
    block_id: str | None = None
    source_ref: str | None = None


class RenderedExecutionPayloadSummary(StrictModel):
    total_message_count: int = Field(ge=0)
    control_message_count: int = Field(ge=0)
    data_message_count: int = Field(ge=0)
    retrieval_message_count: int = Field(ge=0)
    degraded_data_message_count: int = Field(ge=0)
    reference_message_count: int = Field(ge=0)


class RenderedExecutionPayload(StrictModel):
    meta: RenderedExecutionPayloadMeta
    messages: list[RenderedExecutionMessage] = Field(default_factory=list)
    summary: RenderedExecutionPayloadSummary


class CompiledExecution(StrictModel):
    acceptance_criteria: list[str] = Field(default_factory=list)
    allowed_tools: list[str] = Field(default_factory=list)
    allowed_write_set: list[str] = Field(default_factory=list)
    forced_skill_ids: list[str] = Field(default_factory=list)
    input_artifact_refs: list[str] = Field(default_factory=list)
    input_process_asset_refs: list[str] = Field(default_factory=list)
    required_read_refs: list[str] = Field(default_factory=list)
    doc_update_requirements: list[str] = Field(default_factory=list)
    project_workspace_ref: str | None = None
    project_checkout_ref: str | None = None
    project_checkout_path: str | None = None
    git_branch_ref: str | None = None
    deliverable_kind: str | None = None
    git_policy: str | None = None
    output_schema_ref: str = Field(min_length=1)
    output_schema_version: int = Field(ge=1)


class CompiledGovernance(StrictModel):
    retry_budget: int = Field(ge=0)
    timeout_sla_sec: int = Field(ge=1)
    escalation_policy: TicketEscalationPolicy


class CompiledTaskFrame(StrictModel):
    task_category: Literal["implementation", "review", "debugging", "planning"]
    goal: str = Field(min_length=1)
    completion_definition: list[str] = Field(default_factory=list)
    failure_definition: list[str] = Field(default_factory=list)
    deliverable_kind: str | None = None


class ContextLayerSectionSummary(StrictModel):
    label: str = Field(min_length=1)
    item_count: int = Field(ge=0)
    notes: list[str] = Field(default_factory=list)
    governance_profile_ref: str | None = None
    allowed_tool_count: int | None = Field(default=None, ge=0)
    allowed_write_set_count: int | None = Field(default=None, ge=0)


class CompiledContextLayerSummary(StrictModel):
    w0_constitution: ContextLayerSectionSummary
    w1_task_frame: ContextLayerSectionSummary
    w2_evidence: ContextLayerSectionSummary
    w3_runtime_guard: ContextLayerSectionSummary


class SkillBinding(StrictModel):
    binding_id: str = Field(min_length=1)
    binding_version: int = Field(ge=1)
    task_category: Literal["implementation", "review", "debugging", "planning"]
    audit_mode: str = Field(min_length=1)
    forced_skill_ids: list[str] = Field(default_factory=list)
    resolved_skill_ids: list[str] = Field(default_factory=list)
    binding_reason: str = Field(min_length=1)
    binding_scope: str = Field(min_length=1)
    conflict_resolution: str = Field(min_length=1)


class CompiledExecutionPackage(StrictModel):
    meta: CompiledExecutionPackageMeta
    compiled_role: CompiledRole
    compiled_constraints: CompiledConstraints
    governance_mode_slice: GovernanceModeSlice
    task_frame: CompiledTaskFrame
    required_doc_surfaces: list[str] = Field(default_factory=list)
    context_layer_summary: CompiledContextLayerSummary
    org_context: CompileRequestOrgContext
    atomic_context_bundle: AtomicContextBundle
    rendered_execution_payload: RenderedExecutionPayload
    execution: CompiledExecution
    governance: CompiledGovernance
    skill_binding: SkillBinding | None = None


class CompiledAuditArtifacts(StrictModel):
    compiled_context_bundle: CompiledContextBundle
    compile_manifest: CompileManifest
    compiled_execution_package: CompiledExecutionPackage
