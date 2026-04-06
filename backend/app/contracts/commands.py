from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import Field, model_validator

from app.contracts.common import JsonValue, StrictModel
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


class RuntimeProviderConfigInput(StrictModel):
    provider_id: str = Field(min_length=1)
    adapter_kind: str = Field(min_length=1)
    label: str = Field(min_length=1)
    enabled: bool = False
    base_url: str | None = None
    api_key: str | None = None
    model: str | None = None
    timeout_sec: float = Field(default=30.0, gt=0)
    reasoning_effort: str | None = None
    command_path: str | None = None
    capability_tags: list[RuntimeProviderCapabilityTag] = Field(default_factory=list)
    fallback_provider_ids: list[str] = Field(default_factory=list)


class RuntimeProviderRoleBindingInput(StrictModel):
    target_ref: str = Field(min_length=1)
    provider_id: str = Field(min_length=1)
    model: str | None = None


class RuntimeProviderUpsertCommand(StrictModel):
    default_provider_id: str | None = None
    providers: list[RuntimeProviderConfigInput] = Field(default_factory=list)
    role_bindings: list[RuntimeProviderRoleBindingInput] = Field(default_factory=list)
    idempotency_key: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_provider_registry_shape(self) -> "RuntimeProviderUpsertCommand":
        provider_ids = [provider.provider_id for provider in self.providers]
        if len(provider_ids) != len(set(provider_ids)):
            raise ValueError("providers must not contain duplicate provider_id values.")

        valid_provider_ids = set(provider_ids)
        for provider in self.providers:
            capability_values = [tag.value for tag in provider.capability_tags]
            if len(capability_values) != len(set(capability_values)):
                raise ValueError(f"{provider.provider_id} capability_tags must not contain duplicates.")

            fallback_ids = list(provider.fallback_provider_ids)
            if len(fallback_ids) != len(set(fallback_ids)):
                raise ValueError(f"{provider.provider_id} fallback_provider_ids must not contain duplicates.")
            if provider.provider_id in fallback_ids:
                raise ValueError(f"{provider.provider_id} cannot list itself as a fallback provider.")

            unknown_fallback_ids = [provider_id for provider_id in fallback_ids if provider_id not in valid_provider_ids]
            if unknown_fallback_ids:
                raise ValueError(
                    f"{provider.provider_id} references unknown fallback providers: {', '.join(unknown_fallback_ids)}."
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


class TicketCreateCommand(StrictModel):
    ticket_id: str = Field(min_length=1)
    workflow_id: str = Field(min_length=1)
    node_id: str = Field(min_length=1)
    parent_ticket_id: str | None = None
    attempt_no: int = Field(ge=1)
    role_profile_ref: str = Field(min_length=1)
    constraints_ref: str = Field(min_length=1)
    input_artifact_refs: list[str]
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
    escalation_policy: TicketEscalationPolicy
    idempotency_key: str = Field(min_length=1)


class TicketStartCommand(StrictModel):
    workflow_id: str = Field(min_length=1)
    ticket_id: str = Field(min_length=1)
    node_id: str = Field(min_length=1)
    started_by: str = Field(min_length=1)
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


class TicketResultSubmitCommand(StrictModel):
    workflow_id: str = Field(min_length=1)
    ticket_id: str = Field(min_length=1)
    node_id: str = Field(min_length=1)
    submitted_by: str = Field(min_length=1)
    result_status: TicketResultStatus
    schema_version: str = Field(min_length=1)
    payload: dict
    artifact_refs: list[str] = Field(default_factory=list)
    written_artifacts: list[TicketWrittenArtifact] = Field(default_factory=list)
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
