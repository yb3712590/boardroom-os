from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import Field, model_validator

from app.contracts.common import JsonValue, StrictModel
from app.contracts.process_assets import ProcessAssetReference
from app.core.developer_inspector import parse_developer_inspector_ref
from app.core.constants import (
    DEFAULT_LEASE_TIMEOUT_SEC,
    DEFAULT_REPEAT_FAILURE_THRESHOLD,
    DEFAULT_TIMEOUT_BACKOFF_CAP_MULTIPLIER,
    DEFAULT_TIMEOUT_BACKOFF_MULTIPLIER,
    DEFAULT_TIMEOUT_REPEAT_THRESHOLD,
)


class CommandAckStatus(StrEnum):
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    DUPLICATE = "DUPLICATE"


class ReviewAction(StrEnum):
    APPROVE = "APPROVE"
    REJECT = "REJECT"
    MODIFY_CONSTRAINTS = "MODIFY_CONSTRAINTS"


class ReviewType(StrEnum):
    REQUIREMENT_ELICITATION = "REQUIREMENT_ELICITATION"
    VISUAL_MILESTONE = "VISUAL_MILESTONE"
    BUDGET_EXCEPTION = "BUDGET_EXCEPTION"
    MEETING_ESCALATION = "MEETING_ESCALATION"
    INTERNAL_GOVERNANCE_REVIEW = "INTERNAL_GOVERNANCE_REVIEW"
    INTERNAL_DELIVERY_REVIEW = "INTERNAL_DELIVERY_REVIEW"
    INTERNAL_CHECK_REVIEW = "INTERNAL_CHECK_REVIEW"
    INTERNAL_CLOSEOUT_REVIEW = "INTERNAL_CLOSEOUT_REVIEW"
    CORE_HIRE_APPROVAL = "CORE_HIRE_APPROVAL"
    SCOPE_PIVOT = "SCOPE_PIVOT"


class ReviewPriority(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class BlockingScope(StrEnum):
    NODE_ONLY = "NODE_ONLY"
    DEPENDENT_SUBGRAPH = "DEPENDENT_SUBGRAPH"
    WORKFLOW = "WORKFLOW"


class IncidentFollowupAction(StrEnum):
    REBUILD_TICKET_GRAPH = "REBUILD_TICKET_GRAPH"
    REPLAY_REQUIRED_HOOKS = "REPLAY_REQUIRED_HOOKS"
    RESTORE_ONLY = "RESTORE_ONLY"
    RESTORE_AND_RETRY_LATEST_FAILURE = "RESTORE_AND_RETRY_LATEST_FAILURE"
    RESTORE_AND_RETRY_LATEST_TIMEOUT = "RESTORE_AND_RETRY_LATEST_TIMEOUT"
    RESTORE_AND_RETRY_LATEST_PROVIDER_FAILURE = "RESTORE_AND_RETRY_LATEST_PROVIDER_FAILURE"
    RESTORE_AND_RETRY_LATEST_STAFFING_CONTAINMENT = "RESTORE_AND_RETRY_LATEST_STAFFING_CONTAINMENT"


class TicketResultStatus(StrEnum):
    COMPLETED = "completed"
    FAILED = "failed"


class ArtifactRetentionClass(StrEnum):
    PERSISTENT = "PERSISTENT"
    REVIEW_EVIDENCE = "REVIEW_EVIDENCE"
    OPERATIONAL_EVIDENCE = "OPERATIONAL_EVIDENCE"
    EPHEMERAL = "EPHEMERAL"


class DeliveryStage(StrEnum):
    BUILD = "BUILD"
    CHECK = "CHECK"
    REVIEW = "REVIEW"
    CLOSEOUT = "CLOSEOUT"


class RuntimeProviderMode(StrEnum):
    DETERMINISTIC = "DETERMINISTIC"
    OPENAI_COMPAT = "OPENAI_COMPAT"
    CLAUDE_CODE_CLI = "CLAUDE_CODE_CLI"


class RuntimeProviderCapabilityTag(StrEnum):
    STRUCTURED_OUTPUT = "structured_output"
    PLANNING = "planning"
    IMPLEMENTATION = "implementation"
    REVIEW = "review"


class RuntimeProviderCostTier(StrEnum):
    STANDARD = "standard"
    PREMIUM = "premium"


class RuntimeProviderParticipationPolicy(StrEnum):
    ALWAYS_ALLOWED = "always_allowed"
    LOW_FREQUENCY_ONLY = "low_frequency_only"


class RuntimeProviderType(StrEnum):
    OPENAI_RESPONSES_STREAM = "openai_responses_stream"
    OPENAI_RESPONSES_NON_STREAM = "openai_responses_non_stream"
    CLAUDE_STREAM = "claude_stream"
    GEMINI_STREAM = "gemini_stream"


RuntimeProviderReasoningEffort = Literal["low", "medium", "high", "xhigh"]


class MeetingType(StrEnum):
    TECHNICAL_DECISION = "TECHNICAL_DECISION"


class MeetingStatus(StrEnum):
    REQUESTED = "REQUESTED"
    OPEN = "OPEN"
    IN_ROUND = "IN_ROUND"
    CONSENSUS_SUBMITTED = "CONSENSUS_SUBMITTED"
    NO_CONSENSUS = "NO_CONSENSUS"
    CLOSED = "CLOSED"


class MeetingRound(StrEnum):
    POSITION = "POSITION"
    CHALLENGE = "CHALLENGE"
    PROPOSAL = "PROPOSAL"
    CONVERGENCE = "CONVERGENCE"


class ProjectMethodologyProfile(StrEnum):
    AGILE = "AGILE"
    HYBRID = "HYBRID"
    COMPLIANCE = "COMPLIANCE"


class DeliverableKind(StrEnum):
    SOURCE_CODE_DELIVERY = "source_code_delivery"
    STRUCTURED_DOCUMENT_DELIVERY = "structured_document_delivery"
    REVIEW_EVIDENCE = "review_evidence"
    CLOSEOUT_EVIDENCE = "closeout_evidence"


class GitPolicy(StrEnum):
    NO_GIT_REQUIRED = "no_git_required"
    PER_TICKET_COMMIT_REQUIRED = "per_ticket_commit_required"


class ElicitationResponseKind(StrEnum):
    SINGLE_SELECT = "SINGLE_SELECT"
    MULTI_SELECT = "MULTI_SELECT"
    TEXT = "TEXT"


class ElicitationQuestionOption(StrictModel):
    option_id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    summary: str | None = None


class ElicitationQuestion(StrictModel):
    question_id: str = Field(min_length=1)
    prompt: str = Field(min_length=1)
    response_kind: ElicitationResponseKind
    required: bool = True
    options: list[ElicitationQuestionOption] = Field(default_factory=list)


class ElicitationAnswer(StrictModel):
    question_id: str = Field(min_length=1)
    selected_option_ids: list[str] = Field(default_factory=list)
    text: str = ""


class ProjectInitCommand(StrictModel):
    north_star_goal: str = Field(min_length=1)
    hard_constraints: list[str]
    budget_cap: int = Field(ge=0)
    deadline_at: datetime | None = None
    force_requirement_elicitation: bool = False
    workflow_profile: str = Field(default="STANDARD", min_length=1)
    project_methodology_profile: ProjectMethodologyProfile = ProjectMethodologyProfile.AGILE


class RuntimeProviderConfigInput(StrictModel):
    provider_id: str = Field(min_length=1)
    type: RuntimeProviderType
    base_url: str = Field(min_length=1)
    api_key: str = Field(min_length=1)
    alias: str | None = None
    preferred_model: str | None = None
    max_context_window: int | None = Field(default=None, ge=1)
    timeout_sec: float | None = Field(default=None, gt=0)
    connect_timeout_sec: float | None = Field(default=None, gt=0)
    write_timeout_sec: float | None = Field(default=None, gt=0)
    first_token_timeout_sec: float | None = Field(default=None, gt=0)
    stream_idle_timeout_sec: float | None = Field(default=None, gt=0)
    request_total_timeout_sec: float | None = Field(default=None, gt=0)
    retry_backoff_schedule_sec: list[float] = Field(default_factory=list)
    reasoning_effort: RuntimeProviderReasoningEffort | None = "high"
    enabled: bool = False
    fallback_provider_ids: list[str] = Field(default_factory=list)


class RuntimeProviderModelEntryInput(StrictModel):
    provider_id: str = Field(min_length=1)
    model_name: str = Field(min_length=1)


class RuntimeProviderRoleBindingInput(StrictModel):
    target_ref: str = Field(min_length=1)
    provider_model_entry_refs: list[str] = Field(default_factory=list)
    max_context_window_override: int | None = Field(default=None, ge=1)
    reasoning_effort_override: RuntimeProviderReasoningEffort | None = None


class RuntimeSelectionPreference(StrictModel):
    preferred_provider_id: str = Field(min_length=1)
    preferred_model: str | None = None


class RuntimeProviderUpsertCommand(StrictModel):
    providers: list[RuntimeProviderConfigInput] = Field(default_factory=list)
    provider_model_entries: list[RuntimeProviderModelEntryInput] = Field(default_factory=list)
    role_bindings: list[RuntimeProviderRoleBindingInput] = Field(default_factory=list)
    idempotency_key: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_provider_registry_shape(self) -> "RuntimeProviderUpsertCommand":
        provider_ids = [provider.provider_id for provider in self.providers]
        if len(provider_ids) != len(set(provider_ids)):
            raise ValueError("providers must not contain duplicate provider_id values.")
        valid_provider_ids = set(provider_ids)
        seen_provider_model_pairs: set[tuple[str, str]] = set()
        provider_model_entry_refs: set[str] = set()
        for entry in self.provider_model_entries:
            if entry.provider_id not in valid_provider_ids:
                raise ValueError(f"{entry.provider_id} is not a known provider_id.")
            pair = (entry.provider_id, entry.model_name)
            if pair in seen_provider_model_pairs:
                raise ValueError("provider_model_entries must not contain duplicate provider_id + model_name pairs.")
            seen_provider_model_pairs.add(pair)
            provider_model_entry_refs.add(f"{entry.provider_id}::{entry.model_name}")

        for provider in self.providers:
            if provider.retry_backoff_schedule_sec and any(delay <= 0 for delay in provider.retry_backoff_schedule_sec):
                raise ValueError(
                    f"{provider.provider_id} retry_backoff_schedule_sec must contain only positive values."
                )
            fallback_ids = list(provider.fallback_provider_ids)
            if len(fallback_ids) != len(set(fallback_ids)):
                raise ValueError(f"{provider.provider_id} fallback_provider_ids must not contain duplicates.")
            if provider.provider_id in fallback_ids:
                raise ValueError(f"{provider.provider_id} must not include itself in fallback_provider_ids.")
            unknown_fallback_ids = [provider_id for provider_id in fallback_ids if provider_id not in valid_provider_ids]
            if unknown_fallback_ids:
                raise ValueError(
                    f"{provider.provider_id} references unknown fallback providers: {', '.join(unknown_fallback_ids)}."
                )

        seen_target_refs: set[str] = set()
        for binding in self.role_bindings:
            if binding.target_ref in seen_target_refs:
                raise ValueError("role_bindings must not contain duplicate target_ref values.")
            seen_target_refs.add(binding.target_ref)
            if len(binding.provider_model_entry_refs) != len(set(binding.provider_model_entry_refs)):
                raise ValueError(
                    f"{binding.target_ref} provider_model_entry_refs must not contain duplicates."
                )
            unknown_refs = [
                ref for ref in binding.provider_model_entry_refs if ref not in provider_model_entry_refs
            ]
            if unknown_refs:
                raise ValueError(
                    f"{binding.target_ref} references unknown provider_model_entry_refs: {', '.join(unknown_refs)}."
                )
        return self


class ContextQueryPlan(StrictModel):
    keywords: list[str]
    semantic_queries: list[str]
    max_context_tokens: int = Field(ge=1)


class TicketEscalationPolicy(StrictModel):
    on_timeout: str = Field(min_length=1)
    on_schema_error: str = Field(min_length=1)
    on_repeat_failure: str = Field(min_length=1)
    repeat_failure_threshold: int = Field(default=DEFAULT_REPEAT_FAILURE_THRESHOLD, ge=1)
    timeout_repeat_threshold: int = Field(default=DEFAULT_TIMEOUT_REPEAT_THRESHOLD, ge=1)
    timeout_backoff_multiplier: float = Field(default=DEFAULT_TIMEOUT_BACKOFF_MULTIPLIER, ge=1.0)
    timeout_backoff_cap_multiplier: float = Field(
        default=DEFAULT_TIMEOUT_BACKOFF_CAP_MULTIPLIER,
        ge=1.0,
    )


class MeetingRequestCommand(StrictModel):
    workflow_id: str = Field(min_length=1)
    meeting_type: MeetingType
    topic: str = Field(min_length=1)
    participant_employee_ids: list[str] = Field(min_length=2)
    recorder_employee_id: str = Field(min_length=1)
    input_artifact_refs: list[str] = Field(default_factory=list)
    max_rounds: int = Field(default=4, ge=1, le=4)
    idempotency_key: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_meeting_request(self) -> "MeetingRequestCommand":
        deduped = {item for item in self.participant_employee_ids if item}
        if len(deduped) != len(self.participant_employee_ids):
            raise ValueError("participant_employee_ids must not contain duplicates.")
        if self.recorder_employee_id not in deduped:
            raise ValueError("recorder_employee_id must be included in participant_employee_ids.")
        return self


class ExecutionContract(StrictModel):
    execution_target_ref: str = Field(min_length=1)
    required_capability_tags: list[RuntimeProviderCapabilityTag] = Field(min_length=1)
    runtime_contract_version: str = Field(min_length=1)


class DispatchIntent(StrictModel):
    assignee_employee_id: str = Field(min_length=1)
    selection_reason: str = Field(min_length=1)
    dependency_gate_refs: list[str] = Field(default_factory=list)
    selected_by: str = Field(default="ceo", min_length=1)
    wakeup_policy: str = Field(default="default", min_length=1)

    @model_validator(mode="after")
    def validate_dependency_gate_refs(self) -> "DispatchIntent":
        normalized_refs: list[str] = []
        seen_refs: set[str] = set()
        for ref in self.dependency_gate_refs:
            normalized_ref = str(ref).strip()
            if not normalized_ref:
                raise ValueError("dependency_gate_refs must not contain empty values.")
            if normalized_ref in seen_refs:
                raise ValueError("dependency_gate_refs must not contain duplicates.")
            seen_refs.add(normalized_ref)
            normalized_refs.append(normalized_ref)
        object.__setattr__(self, "dependency_gate_refs", normalized_refs)
        return self


class TicketCreateCommand(StrictModel):
    ticket_id: str = Field(min_length=1)
    workflow_id: str = Field(min_length=1)
    node_id: str = Field(min_length=1)
    parent_ticket_id: str | None = None
    attempt_no: int = Field(ge=1)
    role_profile_ref: str = Field(min_length=1)
    constraints_ref: str = Field(min_length=1)
    input_artifact_refs: list[str]
    input_process_asset_refs: list[str] = Field(default_factory=list)
    context_query_plan: ContextQueryPlan
    acceptance_criteria: list[str]
    output_schema_ref: str = Field(min_length=1)
    output_schema_version: int = Field(ge=1)
    allowed_tools: list[str]
    allowed_write_set: list[str]
    lease_timeout_sec: int = Field(default=DEFAULT_LEASE_TIMEOUT_SEC, ge=1)
    retry_budget: int = Field(ge=0)
    priority: str = Field(min_length=1)
    timeout_sla_sec: int = Field(ge=1)
    deadline_at: datetime | None = None
    delivery_stage: DeliveryStage | None = None
    excluded_employee_ids: list[str] = Field(default_factory=list)
    auto_review_request: TicketBoardReviewRequest | None = None
    meeting_context: dict | None = None
    execution_contract: ExecutionContract | None = None
    dispatch_intent: DispatchIntent | None = None
    runtime_preference: RuntimeSelectionPreference | None = None
    project_workspace_ref: str | None = None
    project_methodology_profile: ProjectMethodologyProfile | None = None
    deliverable_kind: DeliverableKind | None = None
    canonical_doc_refs: list[str] = Field(default_factory=list)
    required_read_refs: list[str] = Field(default_factory=list)
    doc_update_requirements: list[str] = Field(default_factory=list)
    git_policy: GitPolicy | None = None
    escalation_policy: TicketEscalationPolicy
    idempotency_key: str = Field(min_length=1)


class TicketStartCommand(StrictModel):
    workflow_id: str = Field(min_length=1)
    ticket_id: str = Field(min_length=1)
    node_id: str = Field(min_length=1)
    started_by: str = Field(min_length=1)
    expected_ticket_version: int | None = Field(default=None, ge=1)
    expected_node_version: int | None = Field(default=None, ge=1)
    idempotency_key: str = Field(min_length=1)


class TicketHeartbeatCommand(StrictModel):
    workflow_id: str = Field(min_length=1)
    ticket_id: str = Field(min_length=1)
    node_id: str = Field(min_length=1)
    reported_by: str = Field(min_length=1)
    idempotency_key: str = Field(min_length=1)


class TicketLeaseCommand(StrictModel):
    workflow_id: str = Field(min_length=1)
    ticket_id: str = Field(min_length=1)
    node_id: str = Field(min_length=1)
    leased_by: str = Field(min_length=1)
    lease_timeout_sec: int = Field(ge=1)
    idempotency_key: str = Field(min_length=1)


class TicketFailCommand(StrictModel):
    workflow_id: str = Field(min_length=1)
    ticket_id: str = Field(min_length=1)
    node_id: str = Field(min_length=1)
    failed_by: str = Field(min_length=1)
    failure_kind: str = Field(min_length=1)
    failure_message: str = Field(min_length=1)
    failure_detail: dict | None = None
    idempotency_key: str = Field(min_length=1)


class TicketCancelCommand(StrictModel):
    workflow_id: str = Field(min_length=1)
    ticket_id: str = Field(min_length=1)
    node_id: str = Field(min_length=1)
    cancelled_by: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    idempotency_key: str = Field(min_length=1)


class TicketWrittenArtifact(StrictModel):
    path: str = Field(min_length=1)
    artifact_ref: str = Field(min_length=1)
    kind: str = Field(min_length=1)
    media_type: str | None = None
    content_json: JsonValue | None = None
    content_text: str | None = None
    content_base64: str | None = None
    retention_class: ArtifactRetentionClass | None = None
    retention_ttl_sec: int | None = Field(default=None, ge=1)


class GitMergeStatus(StrEnum):
    PENDING_REVIEW_GATE = "PENDING_REVIEW_GATE"
    MERGED = "MERGED"
    NOT_REQUESTED = "NOT_REQUESTED"


class TicketGitCommitRecord(StrictModel):
    commit_sha: str = Field(min_length=1)
    branch_ref: str = Field(min_length=1)
    merge_status: GitMergeStatus = GitMergeStatus.PENDING_REVIEW_GATE


class TicketResultSubmitCommand(StrictModel):
    workflow_id: str = Field(min_length=1)
    ticket_id: str = Field(min_length=1)
    node_id: str = Field(min_length=1)
    submitted_by: str = Field(min_length=1)
    compile_request_id: str | None = None
    compiled_execution_package_version_ref: str | None = None
    result_status: TicketResultStatus
    schema_version: str = Field(min_length=1)
    payload: dict
    artifact_refs: list[str] = Field(default_factory=list)
    written_artifacts: list[TicketWrittenArtifact] = Field(default_factory=list)
    verification_evidence_refs: list[str] = Field(default_factory=list)
    git_commit_record: TicketGitCommitRecord | None = None
    assumptions: list[str] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    needs_escalation: bool = False
    summary: str = Field(min_length=1)
    review_request: TicketBoardReviewRequest | None = None
    failure_kind: str | None = None
    failure_message: str | None = None
    failure_detail: dict | None = None
    idempotency_key: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_status_specific_fields(self) -> "TicketResultSubmitCommand":
        if self.result_status == TicketResultStatus.COMPLETED:
            if self.review_request is not None and self.needs_escalation:
                raise ValueError("review_request and needs_escalation cannot conflict.")
            return self
        if not self.failure_kind or not self.failure_message:
            raise ValueError("failed result submissions require failure_kind and failure_message.")
        return self


class SchedulerWorkerCandidate(StrictModel):
    employee_id: str = Field(min_length=1)
    role_profile_refs: list[str] = Field(min_length=1)


class SchedulerTickCommand(StrictModel):
    workers: list[SchedulerWorkerCandidate] | None = None
    max_dispatches: int = Field(default=10, ge=1)
    idempotency_key: str = Field(min_length=1)


class IncidentResolveCommand(StrictModel):
    incident_id: str = Field(min_length=1)
    resolved_by: str = Field(min_length=1)
    resolution_summary: str = Field(min_length=1)
    followup_action: IncidentFollowupAction = IncidentFollowupAction.RESTORE_ONLY
    idempotency_key: str = Field(min_length=1)


class ArtifactDeleteCommand(StrictModel):
    artifact_ref: str = Field(min_length=1)
    deleted_by: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    idempotency_key: str = Field(min_length=1)


class ArtifactCleanupCommand(StrictModel):
    cleaned_by: str = Field(min_length=1)
    idempotency_key: str = Field(min_length=1)


class TicketArtifactImportUploadCommand(StrictModel):
    workflow_id: str = Field(min_length=1)
    ticket_id: str = Field(min_length=1)
    node_id: str = Field(min_length=1)
    artifact_ref: str = Field(min_length=1)
    path: str = Field(min_length=1)
    kind: str = Field(min_length=1)
    media_type: str | None = None
    upload_session_id: str = Field(min_length=1)
    retention_class: ArtifactRetentionClass | None = None
    retention_ttl_sec: int | None = Field(default=None, ge=1)
    idempotency_key: str = Field(min_length=1)


class EmployeeHireRequestCommand(StrictModel):
    workflow_id: str = Field(min_length=1)
    employee_id: str = Field(min_length=1)
    role_type: str = Field(min_length=1)
    role_profile_refs: list[str] = Field(min_length=1)
    skill_profile: dict = Field(default_factory=dict)
    personality_profile: dict = Field(default_factory=dict)
    aesthetic_profile: dict = Field(default_factory=dict)
    provider_id: str | None = Field(default=None, min_length=1)
    request_summary: str = Field(min_length=1)
    idempotency_key: str = Field(min_length=1)


class EmployeeReplaceRequestCommand(StrictModel):
    workflow_id: str = Field(min_length=1)
    replaced_employee_id: str = Field(min_length=1)
    replacement_employee_id: str = Field(min_length=1)
    replacement_role_type: str = Field(min_length=1)
    replacement_role_profile_refs: list[str] = Field(min_length=1)
    replacement_skill_profile: dict = Field(default_factory=dict)
    replacement_personality_profile: dict = Field(default_factory=dict)
    replacement_aesthetic_profile: dict = Field(default_factory=dict)
    replacement_provider_id: str | None = Field(default=None, min_length=1)
    request_summary: str = Field(min_length=1)
    idempotency_key: str = Field(min_length=1)


class EmployeeFreezeCommand(StrictModel):
    workflow_id: str = Field(min_length=1)
    employee_id: str = Field(min_length=1)
    frozen_by: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    idempotency_key: str = Field(min_length=1)


class EmployeeRestoreCommand(StrictModel):
    workflow_id: str = Field(min_length=1)
    employee_id: str = Field(min_length=1)
    restored_by: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    idempotency_key: str = Field(min_length=1)


class TicketReviewOption(StrictModel):
    option_id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    artifact_refs: list[str] = Field(default_factory=list)
    preview_assets: list[dict] = Field(default_factory=list)
    pros: list[str] = Field(default_factory=list)
    cons: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    estimated_budget_impact_range: dict | None = None


class TicketReviewEvidence(StrictModel):
    evidence_id: str = Field(min_length=1)
    source_type: str = Field(min_length=1)
    headline: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    source_ref: str | None = None


class DeveloperInspectorRefs(StrictModel):
    compiled_context_bundle_ref: str | None = None
    compile_manifest_ref: str | None = None
    rendered_execution_payload_ref: str | None = None
    incident_ref: str | None = None
    meeting_consensus_ref: str | None = None

    @model_validator(mode="after")
    def validate_supported_refs(self) -> "DeveloperInspectorRefs":
        if self.compiled_context_bundle_ref is not None:
            parsed = parse_developer_inspector_ref(self.compiled_context_bundle_ref)
            if parsed.scheme != "ctx":
                raise ValueError("compiled_context_bundle_ref must use ctx://.")
        if self.compile_manifest_ref is not None:
            parsed = parse_developer_inspector_ref(self.compile_manifest_ref)
            if parsed.scheme != "manifest":
                raise ValueError("compile_manifest_ref must use manifest://.")
        if self.rendered_execution_payload_ref is not None:
            parsed = parse_developer_inspector_ref(self.rendered_execution_payload_ref)
            if parsed.scheme != "render":
                raise ValueError("rendered_execution_payload_ref must use render://.")
        return self



class TicketBoardReviewRequest(StrictModel):
    review_type: ReviewType
    priority: ReviewPriority = ReviewPriority.MEDIUM
    title: str = Field(min_length=1)
    subtitle: str | None = None
    blocking_scope: BlockingScope = BlockingScope.NODE_ONLY
    trigger_reason: str = Field(min_length=1)
    why_now: str = Field(min_length=1)
    recommended_action: ReviewAction
    recommended_option_id: str | None = None
    recommendation_summary: str = Field(min_length=1)
    options: list[TicketReviewOption] = Field(min_length=1)
    evidence_summary: list[TicketReviewEvidence] = Field(default_factory=list)
    delta_summary: dict | None = None
    maker_checker_summary: dict | None = None
    risk_summary: dict | None = None
    budget_impact: dict | None = None
    developer_inspector_refs: DeveloperInspectorRefs | None = None
    elicitation_questionnaire: list[ElicitationQuestion] | None = None
    available_actions: list[ReviewAction] = Field(
        default_factory=lambda: [
            ReviewAction.APPROVE,
            ReviewAction.REJECT,
            ReviewAction.MODIFY_CONSTRAINTS,
        ]
    )
    draft_selected_option_id: str | None = None
    comment_template: str = ""
    inbox_title: str | None = None
    inbox_summary: str | None = None
    badges: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_option_refs(self) -> "TicketBoardReviewRequest":
        option_ids = {option.option_id for option in self.options}
        if self.recommended_option_id is not None and self.recommended_option_id not in option_ids:
            raise ValueError("recommended_option_id must match one of the review options.")
        if self.draft_selected_option_id is not None and self.draft_selected_option_id not in option_ids:
            raise ValueError("draft_selected_option_id must match one of the review options.")
        if len({action.value for action in self.available_actions}) != len(self.available_actions):
            raise ValueError("available_actions must not contain duplicates.")
        return self


class TicketCompletedCommand(StrictModel):
    workflow_id: str = Field(min_length=1)
    ticket_id: str = Field(min_length=1)
    node_id: str = Field(min_length=1)
    completed_by: str = Field(min_length=1)
    completion_summary: str = Field(min_length=1)
    artifact_refs: list[str] = Field(default_factory=list)
    written_artifacts: list[TicketWrittenArtifact] = Field(default_factory=list)
    produced_process_assets: list[ProcessAssetReference] = Field(default_factory=list)
    verification_evidence_refs: list[str] = Field(default_factory=list)
    git_commit_record: TicketGitCommitRecord | None = None
    review_request: TicketBoardReviewRequest | None = None
    idempotency_key: str = Field(min_length=1)


class BoardApproveCommand(StrictModel):
    review_pack_id: str = Field(min_length=1)
    review_pack_version: int = Field(ge=1)
    command_target_version: int = Field(ge=0)
    approval_id: str = Field(min_length=1)
    selected_option_id: str = Field(min_length=1)
    board_comment: str = Field(min_length=1)
    elicitation_answers: list[ElicitationAnswer] = Field(default_factory=list)
    idempotency_key: str = Field(min_length=1)


class BoardRejectCommand(StrictModel):
    review_pack_id: str = Field(min_length=1)
    review_pack_version: int = Field(ge=1)
    command_target_version: int = Field(ge=0)
    approval_id: str = Field(min_length=1)
    board_comment: str = Field(min_length=1)
    rejection_reasons: list[str] = Field(min_length=1)
    idempotency_key: str = Field(min_length=1)


class ConstraintPatch(StrictModel):
    add_rules: list[str]
    remove_rules: list[str]
    replace_rules: list[str]


class ModifyConstraintsCommand(StrictModel):
    review_pack_id: str = Field(min_length=1)
    review_pack_version: int = Field(ge=1)
    command_target_version: int = Field(ge=0)
    approval_id: str = Field(min_length=1)
    constraint_patch: ConstraintPatch
    board_comment: str = Field(min_length=1)
    elicitation_answers: list[ElicitationAnswer] = Field(default_factory=list)
    idempotency_key: str = Field(min_length=1)


class CommandAckEnvelope(StrictModel):
    command_id: str
    idempotency_key: str
    status: CommandAckStatus
    received_at: datetime
    reason: str | None = None
    causation_hint: str | None = None
