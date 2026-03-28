from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import Field, model_validator

from app.contracts.common import StrictModel
from app.core.developer_inspector import parse_developer_inspector_ref


class CommandAckStatus(StrEnum):
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    DUPLICATE = "DUPLICATE"


class ReviewAction(StrEnum):
    APPROVE = "APPROVE"
    REJECT = "REJECT"
    MODIFY_CONSTRAINTS = "MODIFY_CONSTRAINTS"


class ReviewType(StrEnum):
    VISUAL_MILESTONE = "VISUAL_MILESTONE"
    BUDGET_EXCEPTION = "BUDGET_EXCEPTION"
    MEETING_ESCALATION = "MEETING_ESCALATION"
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


class ProjectInitCommand(StrictModel):
    north_star_goal: str = Field(min_length=1)
    hard_constraints: list[str]
    budget_cap: int = Field(ge=0)
    deadline_at: datetime | None = None


class ContextQueryPlan(StrictModel):
    keywords: list[str]
    semantic_queries: list[str]
    max_context_tokens: int = Field(ge=1)


class TicketEscalationPolicy(StrictModel):
    on_timeout: str = Field(min_length=1)
    on_schema_error: str = Field(min_length=1)
    on_repeat_failure: str = Field(min_length=1)


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
    retry_budget: int = Field(ge=0)
    priority: str = Field(min_length=1)
    timeout_sla_sec: int = Field(ge=1)
    deadline_at: datetime | None = None
    escalation_policy: TicketEscalationPolicy
    idempotency_key: str = Field(min_length=1)


class TicketStartCommand(StrictModel):
    workflow_id: str = Field(min_length=1)
    ticket_id: str = Field(min_length=1)
    node_id: str = Field(min_length=1)
    started_by: str = Field(min_length=1)
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


class SchedulerWorkerCandidate(StrictModel):
    employee_id: str = Field(min_length=1)
    role_profile_refs: list[str] = Field(min_length=1)


class SchedulerTickCommand(StrictModel):
    workers: list[SchedulerWorkerCandidate] | None = None
    max_dispatches: int = Field(default=10, ge=1)
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
        return self


class DeveloperInspectorPayloads(StrictModel):
    compiled_context_bundle: dict | None = None
    compile_manifest: dict | None = None


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
    developer_inspector_payloads: DeveloperInspectorPayloads | None = None
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
        refs = self.developer_inspector_refs
        payloads = self.developer_inspector_payloads
        if payloads is not None:
            if payloads.compiled_context_bundle is not None and (
                refs is None or refs.compiled_context_bundle_ref is None
            ):
                raise ValueError(
                    "developer_inspector_payloads.compiled_context_bundle requires compiled_context_bundle_ref."
                )
            if payloads.compile_manifest is not None and (
                refs is None or refs.compile_manifest_ref is None
            ):
                raise ValueError(
                    "developer_inspector_payloads.compile_manifest requires compile_manifest_ref."
                )
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
    idempotency_key: str = Field(min_length=1)


class CommandAckEnvelope(StrictModel):
    command_id: str
    idempotency_key: str
    status: CommandAckStatus
    received_at: datetime
    reason: str | None = None
    causation_hint: str | None = None
