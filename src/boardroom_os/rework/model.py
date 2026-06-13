from __future__ import annotations

import hashlib
import json
from datetime import datetime
from enum import Enum, StrEnum
from typing import Any, Mapping, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from boardroom_os.contracts.evidence_obligation import RequiredArtifactType
from boardroom_os.contracts.types import (
    AcceptanceRef,
    ContractId,
    EvidenceObligationRef,
    NonEmptyTextValue,
    SourceSurfaceRef,
)
from boardroom_os.execution.context_index import ProviderAttemptRef
from boardroom_os.execution.package import ExecutionPackageRef
from boardroom_os.graph.ticket import TicketId


class BlockerReportId(NonEmptyTextValue):
    pass


class BlockerRef(NonEmptyTextValue):
    pass


class ObservedFactRef(NonEmptyTextValue):
    pass


class ExpectedFactRef(NonEmptyTextValue):
    pass


class RunId(NonEmptyTextValue):
    pass


class ReworkCycleId(NonEmptyTextValue):
    pass


class ReworkRequestId(NonEmptyTextValue):
    pass


class ReworkIssueId(NonEmptyTextValue):
    pass


class ReworkPlanId(NonEmptyTextValue):
    pass


class ReworkDecisionId(NonEmptyTextValue):
    pass


class TicketGraphPatchId(NonEmptyTextValue):
    pass


class TicketGraphPatchOperationId(NonEmptyTextValue):
    pass


class GraphPatchReviewId(NonEmptyTextValue):
    pass


class GraphPatchApprovalSetId(NonEmptyTextValue):
    pass


class ReworkAttemptId(NonEmptyTextValue):
    pass


class ReworkOutcomeId(NonEmptyTextValue):
    pass


class ReworkTerminationDecisionId(NonEmptyTextValue):
    pass


class BlockerSourceKind(StrEnum):
    FINAL_EVIDENCE_TABLE = "final_evidence_table"
    CHECKER_VERDICT = "checker_verdict"
    CLOSEOUT_GATE = "closeout_gate"
    RUN_MANIFEST = "run_manifest"
    BEHAVIORAL_PROBE = "behavioral_probe"
    PROCESS_AUDIT = "process_audit"
    REPLAY_BUNDLE = "replay_bundle"


class ReworkActorKind(StrEnum):
    CEO = "ceo"
    ARCHITECT = "architect"
    WORKER = "worker"
    TESTER = "tester"
    RELEASE_DEVOPS = "release_devops"
    CHECKER = "checker"
    CLOSEOUT = "closeout"
    CLOSEOUT_GATE = "closeout_gate"
    EVIDENCE_VERIFIER = "evidence_verifier"
    GRAPH_PATCH_REVIEW_GATE = "graph_patch_review_gate"
    GOVERNANCE_ADAPTER = "governance_adapter"
    GOVERNANCE_COMMAND_HANDLER = "governance_command_handler"
    RUNTIME = "runtime"
    EXECUTOR = "executor"
    ATOMIC_AGENT = "atomic_agent"


class ReworkCycleStatus(StrEnum):
    REQUESTED = "requested"
    PLANNED = "planned"
    EXECUTING = "executing"
    REVIEWING = "reviewing"
    ACCEPTED = "accepted"
    ESCALATED = "escalated"
    EXHAUSTED = "exhausted"


class ReworkIssueCode(StrEnum):
    FINAL_EVIDENCE_MISSING = "final_evidence_missing"
    FINAL_EVIDENCE_FAILED = "final_evidence_failed"
    CHECKER_BLOCKER = "checker_blocker"
    CONTRACT_MISMATCH = "contract_mismatch"
    WORK_PRODUCT_MISMATCH = "work_product_mismatch"
    INVALID_CHECKER_INPUT = "invalid_checker_input"
    CLOSEOUT_GATE_FAILURE = "closeout_gate_failure"
    RUN_MANIFEST_MISMATCH = "run_manifest_mismatch"
    PROBE_RESPONSE_SHAPE_MISMATCH = "probe_response_shape_mismatch"
    ENV_BINDING_NOT_CONVERGED = "env_binding_not_converged"
    FINAL_EVIDENCE_OLD_ACCEPTANCE_REFS = "final_evidence_old_acceptance_refs"
    CLOSEOUT_AUDIT_OLD_RUN_REFS = "closeout_audit_old_run_refs"


class ReworkIssueSeverity(StrEnum):
    BLOCKING = "blocking"
    ESCALATION_REQUIRED = "escalation_required"


class ReworkSuspectedDomain(StrEnum):
    CONTRACT = "contract"
    IMPLEMENTATION = "implementation"
    PROBE = "probe"
    RUN_ENV = "run_env"
    EVIDENCE_PROJECTION = "evidence_projection"
    CLOSEOUT_AUDIT = "closeout_audit"
    GRAPH = "graph"


class ReworkDecisionKind(StrEnum):
    FIX_IMPLEMENTATION = "fix_implementation"
    FIX_CONTRACT_OR_PROBE = "fix_contract_or_probe"
    SPLIT_TICKET = "split_ticket"
    REORDER_DEPENDENCIES = "reorder_dependencies"
    NARROW_SCOPE = "narrow_scope"
    ESCALATE_HUMAN_REVIEW = "escalate_human_review"


class GraphPatchOperationKind(StrEnum):
    CREATE_REWORK_TICKET = "create_rework_ticket"
    SPLIT_TICKET = "split_ticket"
    UPDATE_DEPENDENCIES = "update_dependencies"
    NARROW_ALLOWED_WRITE_SET = "narrow_allowed_write_set"
    APPEND_EVIDENCE_OBLIGATION = "append_evidence_obligation"
    MARK_TICKET_BLOCKED_BY_REWORK = "mark_ticket_blocked_by_rework"
    REQUEST_CONTRACT_OR_PROBE_REVISION = "request_contract_or_probe_revision"
    ESCALATE_WITHOUT_GRAPH_CHANGE = "escalate_without_graph_change"


class GraphPatchReviewDomain(StrEnum):
    PLANNING = "planning"
    STRUCTURAL = "structural"
    BLOCKER_COVERAGE = "blocker_coverage"
    BEHAVIORAL_PROBE = "behavioral_probe"
    RUN_ENV_READINESS = "run_env_readiness"
    CLOSEOUT_FACT_CHAIN = "closeout_fact_chain"


class GraphPatchReviewStatus(StrEnum):
    APPROVED = "approved"
    REJECTED = "rejected"
    NEEDS_CHANGES = "needs_changes"
    ABSTAINED_NOT_APPLICABLE = "abstained_not_applicable"


class GraphPatchApprovalStatus(StrEnum):
    READY_TO_COMMIT = "ready_to_commit"
    REJECTED = "rejected"
    INCOMPLETE = "incomplete"


class ReworkOutcomeStatus(StrEnum):
    ACCEPTED = "accepted"
    REWORK_REQUIRED = "rework_required"
    ESCALATED = "escalated"
    EXHAUSTED = "exhausted"


class ReworkTerminationReason(StrEnum):
    ACCEPTED = "accepted"
    ESCALATED_HUMAN_REVIEW = "escalated_human_review"
    EXHAUSTED_BUDGET = "exhausted_budget"
    BLOCKED_BY_MISSING_CONTRACT = "blocked_by_missing_contract"
    BLOCKED_BY_PROVIDER_CAPABILITY = "blocked_by_provider_capability"
    BLOCKED_BY_UNTRUSTED_EVIDENCE = "blocked_by_untrusted_evidence"


_REQUESTER_ACTORS = frozenset(
    {
        ReworkActorKind.CHECKER,
        ReworkActorKind.CLOSEOUT_GATE,
        ReworkActorKind.GRAPH_PATCH_REVIEW_GATE,
        ReworkActorKind.GOVERNANCE_ADAPTER,
        ReworkActorKind.EVIDENCE_VERIFIER,
        ReworkActorKind.CLOSEOUT,
    }
)

_REQUIRED_APPROVAL_DOMAINS = frozenset(
    {
        GraphPatchReviewDomain.PLANNING,
        GraphPatchReviewDomain.STRUCTURAL,
        GraphPatchReviewDomain.BLOCKER_COVERAGE,
    }
)

_REVIEW_DOMAIN_ALLOWED_ROLES = {
    GraphPatchReviewDomain.PLANNING: frozenset({ReworkActorKind.CEO}),
    GraphPatchReviewDomain.STRUCTURAL: frozenset({ReworkActorKind.ARCHITECT}),
    GraphPatchReviewDomain.BLOCKER_COVERAGE: frozenset({ReworkActorKind.CHECKER}),
    GraphPatchReviewDomain.BEHAVIORAL_PROBE: frozenset({ReworkActorKind.TESTER}),
    GraphPatchReviewDomain.RUN_ENV_READINESS: frozenset({ReworkActorKind.RELEASE_DEVOPS}),
    GraphPatchReviewDomain.CLOSEOUT_FACT_CHAIN: frozenset(
        {ReworkActorKind.CLOSEOUT, ReworkActorKind.CHECKER}
    ),
}


def _reject_empty_tuple(values: tuple[Any, ...], field_name: str) -> tuple[Any, ...]:
    if not values:
        raise ValueError(f"{field_name} must not be empty")
    return values


def _reject_empty_string_tuple(values: tuple[str, ...], field_name: str) -> tuple[str, ...]:
    normalized = tuple(value.strip() for value in values)
    if not normalized:
        raise ValueError(f"{field_name} must not be empty")
    if any(not value for value in normalized):
        raise ValueError(f"{field_name} must not contain empty values")
    return normalized


def _reject_duplicate_value_refs(values: tuple[Any, ...], field_name: str) -> tuple[Any, ...]:
    seen: set[str] = set()
    for value in values:
        ref_value = getattr(value, "value", str(value))
        if ref_value in seen:
            raise ValueError(f"{field_name} must be unique")
        seen.add(ref_value)
    return values


def _require_timezone(value: datetime, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value


def _canonicalize(value: Any) -> Any:
    if isinstance(value, BaseModel):
        field_names = tuple(type(value).model_fields)
        if field_names == ("value",):
            return _canonicalize(value.value)
        return {field_name: _canonicalize(getattr(value, field_name)) for field_name in field_names}
    if isinstance(value, tuple | list):
        return [_canonicalize(item) for item in value]
    if isinstance(value, Mapping):
        return {str(key): _canonicalize(item) for key, item in value.items()}
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def canonical_rework_hash(model: BaseModel) -> str:
    payload = json.dumps(_canonicalize(model), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class BlockerReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    blocker_report_id: BlockerReportId
    run_id: RunId
    source_kind: BlockerSourceKind
    source_ref: str
    contract_refs: tuple[ContractId, ...]
    acceptance_refs: tuple[AcceptanceRef, ...]
    package_contract_ref: ContractId
    run_manifest_ref: str
    blockers: tuple[BlockerRef, ...]
    created_at: datetime

    @field_validator("source_ref", "run_manifest_ref")
    @classmethod
    def _reject_empty_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("text fields must not be empty")
        return normalized

    @field_validator("contract_refs", "acceptance_refs", "blockers")
    @classmethod
    def _reject_empty_or_duplicate_refs(cls, values: tuple[Any, ...], info: Any) -> tuple[Any, ...]:
        _reject_empty_tuple(values, info.field_name)
        return _reject_duplicate_value_refs(values, info.field_name)

    @field_validator("created_at")
    @classmethod
    def _require_created_at_timezone(cls, value: datetime) -> datetime:
        return _require_timezone(value, "created_at")


class ReworkIssue(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    issue_id: ReworkIssueId
    blocker_refs: tuple[BlockerRef, ...]
    issue_code: ReworkIssueCode
    severity: ReworkIssueSeverity
    acceptance_refs: tuple[AcceptanceRef, ...]
    source_surface_refs: tuple[SourceSurfaceRef, ...]
    run_manifest_refs: tuple[str, ...]
    evidence_obligation_refs: tuple[EvidenceObligationRef, ...]
    observed_fact_refs: tuple[ObservedFactRef, ...] = ()
    expected_fact_refs: tuple[ExpectedFactRef, ...] = ()
    suspected_domains: tuple[ReworkSuspectedDomain, ...]
    required_artifact_types: tuple[RequiredArtifactType, ...]
    description: str

    @field_validator(
        "blocker_refs",
        "acceptance_refs",
        "source_surface_refs",
        "evidence_obligation_refs",
        "suspected_domains",
        "required_artifact_types",
    )
    @classmethod
    def _reject_empty_or_duplicate_tuple(cls, values: tuple[Any, ...], info: Any) -> tuple[Any, ...]:
        _reject_empty_tuple(values, info.field_name)
        return _reject_duplicate_value_refs(values, info.field_name)

    @field_validator("observed_fact_refs", "expected_fact_refs")
    @classmethod
    def _reject_duplicate_optional_refs(cls, values: tuple[Any, ...], info: Any) -> tuple[Any, ...]:
        return _reject_duplicate_value_refs(values, info.field_name)

    @field_validator("run_manifest_refs")
    @classmethod
    def _reject_empty_run_manifest_refs(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized = _reject_empty_string_tuple(values, "run_manifest_refs")
        if len(set(normalized)) != len(normalized):
            raise ValueError("run_manifest_refs must be unique")
        return normalized

    @field_validator("description")
    @classmethod
    def _reject_empty_description(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("description must not be empty")
        return normalized


def validate_issue_contract_scope(
    issue: ReworkIssue,
    *,
    active_acceptance_refs: tuple[AcceptanceRef, ...],
    active_source_surface_refs: tuple[SourceSurfaceRef, ...],
    active_evidence_obligation_refs: tuple[EvidenceObligationRef, ...],
) -> None:
    active_acceptance = {ref.value for ref in active_acceptance_refs}
    active_surfaces = {ref.value for ref in active_source_surface_refs}
    active_obligations = {ref.value for ref in active_evidence_obligation_refs}
    for ref in issue.acceptance_refs:
        if ref.value not in active_acceptance:
            raise ValueError(f"unknown acceptance_ref in rework issue: {ref.value}")
    for ref in issue.source_surface_refs:
        if ref.value not in active_surfaces:
            raise ValueError(f"unknown source_surface_ref in rework issue: {ref.value}")
    for ref in issue.evidence_obligation_refs:
        if ref.value not in active_obligations:
            raise ValueError(f"unknown evidence_obligation_ref in rework issue: {ref.value}")


class ReworkRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    rework_request_id: ReworkRequestId
    cycle_id: ReworkCycleId | str
    run_id: RunId
    request_source_refs: tuple[str, ...]
    issues: tuple[ReworkIssue, ...]
    requested_by_actor: ReworkActorKind
    requested_at: datetime
    active_contract_refs: tuple[ContractId, ...]
    active_graph_version: int = Field(gt=0)

    @field_validator("request_source_refs")
    @classmethod
    def _reject_empty_request_source_refs(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized = _reject_empty_string_tuple(values, "request_source_refs")
        if len(set(normalized)) != len(normalized):
            raise ValueError("request_source_refs must be unique")
        return normalized

    @field_validator("issues", "active_contract_refs")
    @classmethod
    def _reject_empty_or_duplicate_refs(cls, values: tuple[Any, ...], info: Any) -> tuple[Any, ...]:
        _reject_empty_tuple(values, info.field_name)
        return _reject_duplicate_value_refs(values, info.field_name)

    @field_validator("requested_at")
    @classmethod
    def _require_requested_at_timezone(cls, value: datetime) -> datetime:
        return _require_timezone(value, "requested_at")

    @model_validator(mode="after")
    def _validate_request_actor_and_sources(self) -> Self:
        if self.requested_by_actor not in _REQUESTER_ACTORS:
            raise ValueError("requested_by_actor is not allowed to create rework requests")
        return self


class ReworkCycle(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    cycle_id: ReworkCycleId
    run_id: RunId
    status: ReworkCycleStatus
    request_ref: ReworkRequestId | None = None
    round_index: int = Field(ge=0)
    created_at: datetime

    @field_validator("created_at")
    @classmethod
    def _require_created_at_timezone(cls, value: datetime) -> datetime:
        return _require_timezone(value, "created_at")


class ReworkDecision(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    decision_id: ReworkDecisionId
    decision_kind: ReworkDecisionKind
    blocker_refs: tuple[BlockerRef, ...]
    issue_ids: tuple[ReworkIssueId, ...]
    target_ticket_refs: tuple[TicketId, ...] = ()
    target_graph_operation_refs: tuple[TicketGraphPatchOperationId, ...] = ()
    rationale: str

    @field_validator("blocker_refs", "issue_ids")
    @classmethod
    def _reject_empty_or_duplicate_refs(cls, values: tuple[Any, ...], info: Any) -> tuple[Any, ...]:
        _reject_empty_tuple(values, info.field_name)
        return _reject_duplicate_value_refs(values, info.field_name)

    @field_validator("target_ticket_refs", "target_graph_operation_refs")
    @classmethod
    def _reject_duplicate_optional_refs(cls, values: tuple[Any, ...], info: Any) -> tuple[Any, ...]:
        return _reject_duplicate_value_refs(values, info.field_name)

    @field_validator("rationale")
    @classmethod
    def _reject_empty_rationale(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("rationale must not be empty")
        return normalized

    @model_validator(mode="after")
    def _validate_targets(self) -> Self:
        if self.decision_kind is ReworkDecisionKind.ESCALATE_HUMAN_REVIEW:
            return self
        if not self.target_ticket_refs and not self.target_graph_operation_refs:
            raise ValueError("non-escalation rework decision requires target refs")
        return self


class ReworkPlan(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    rework_plan_id: ReworkPlanId
    cycle_id: ReworkCycleId | str
    rework_request_id: ReworkRequestId
    planner_actor: ReworkActorKind
    planner_attempt_ref: ProviderAttemptRef
    decisions: tuple[ReworkDecision, ...]
    ticket_graph_patch_ref: TicketGraphPatchId
    risk_notes: tuple[str, ...]
    stop_or_escalation_conditions: tuple[str, ...]

    @field_validator("decisions")
    @classmethod
    def _reject_empty_decisions(cls, values: tuple[ReworkDecision, ...]) -> tuple[ReworkDecision, ...]:
        _reject_empty_tuple(values, "decisions")
        return _reject_duplicate_value_refs(values, "decisions")

    @field_validator("risk_notes", "stop_or_escalation_conditions")
    @classmethod
    def _reject_empty_text_tuples(cls, values: tuple[str, ...], info: Any) -> tuple[str, ...]:
        normalized = _reject_empty_string_tuple(values, info.field_name)
        if len(set(normalized)) != len(normalized):
            raise ValueError(f"{info.field_name} must be unique")
        return normalized

    @model_validator(mode="after")
    def _validate_planner_actor(self) -> Self:
        if self.planner_actor is not ReworkActorKind.CEO:
            raise ValueError("planner_actor must be ceo")
        return self


class TicketGraphPatchOperation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    operation_id: TicketGraphPatchOperationId
    operation_kind: GraphPatchOperationKind
    target_ticket_refs: tuple[TicketId, ...]
    acceptance_refs: tuple[AcceptanceRef, ...]
    source_surface_refs: tuple[SourceSurfaceRef, ...]
    evidence_obligation_refs: tuple[EvidenceObligationRef, ...]
    rationale: str

    @field_validator(
        "target_ticket_refs",
        "acceptance_refs",
        "source_surface_refs",
        "evidence_obligation_refs",
    )
    @classmethod
    def _reject_empty_or_duplicate_refs(cls, values: tuple[Any, ...], info: Any) -> tuple[Any, ...]:
        _reject_empty_tuple(values, info.field_name)
        return _reject_duplicate_value_refs(values, info.field_name)

    @field_validator("rationale")
    @classmethod
    def _reject_empty_rationale(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("rationale must not be empty")
        return normalized


class TicketGraphPatch(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    ticket_graph_patch_id: TicketGraphPatchId
    base_graph_version: int = Field(gt=0)
    proposed_by_plan_ref: ReworkPlanId
    operations: tuple[TicketGraphPatchOperation, ...]
    affected_ticket_refs: tuple[TicketId, ...]
    affected_contract_refs: tuple[ContractId, ...]
    affected_source_surface_refs: tuple[SourceSurfaceRef, ...]
    required_review_domains: tuple[GraphPatchReviewDomain, ...]
    patch_hash: str

    @field_validator(
        "operations",
        "affected_ticket_refs",
        "affected_contract_refs",
        "affected_source_surface_refs",
        "required_review_domains",
    )
    @classmethod
    def _reject_empty_or_duplicate_refs(cls, values: tuple[Any, ...], info: Any) -> tuple[Any, ...]:
        _reject_empty_tuple(values, info.field_name)
        return _reject_duplicate_value_refs(values, info.field_name)

    @field_validator("patch_hash")
    @classmethod
    def _reject_empty_patch_hash(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("patch_hash must not be empty")
        return normalized


class GraphPatchReview(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    graph_patch_review_id: GraphPatchReviewId
    ticket_graph_patch_ref: TicketGraphPatchId
    review_domain: GraphPatchReviewDomain
    reviewer_actor: ReworkActorKind
    reviewer_role_kind: ReworkActorKind
    reviewer_attempt_ref: ProviderAttemptRef
    status: GraphPatchReviewStatus
    checked_invariants: tuple[str, ...] = ()
    blockers: tuple[BlockerRef, ...] = ()
    non_blocking_notes: tuple[str, ...] = ()
    created_at: datetime

    @field_validator("checked_invariants", "non_blocking_notes")
    @classmethod
    def _normalize_text_tuples(cls, values: tuple[str, ...], info: Any) -> tuple[str, ...]:
        if not values:
            return values
        normalized = tuple(value.strip() for value in values)
        if any(not value for value in normalized):
            raise ValueError(f"{info.field_name} must not contain empty values")
        if len(set(normalized)) != len(normalized):
            raise ValueError(f"{info.field_name} must be unique")
        return normalized

    @field_validator("blockers")
    @classmethod
    def _reject_duplicate_blockers(cls, values: tuple[BlockerRef, ...]) -> tuple[BlockerRef, ...]:
        return _reject_duplicate_value_refs(values, "blockers")

    @field_validator("created_at")
    @classmethod
    def _require_created_at_timezone(cls, value: datetime) -> datetime:
        return _require_timezone(value, "created_at")

    @model_validator(mode="after")
    def _validate_review_shape(self) -> Self:
        allowed_roles = _REVIEW_DOMAIN_ALLOWED_ROLES[self.review_domain]
        if self.reviewer_role_kind not in allowed_roles:
            raise ValueError("reviewer_role_kind does not match graph patch review domain")
        if self.status is GraphPatchReviewStatus.APPROVED and not self.checked_invariants:
            raise ValueError("approved graph patch review requires checked_invariants")
        if self.status in {GraphPatchReviewStatus.REJECTED, GraphPatchReviewStatus.NEEDS_CHANGES} and not self.blockers:
            raise ValueError("rejected or needs_changes graph patch review requires blockers")
        return self


class GraphPatchApprovalSet(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    approval_set_id: GraphPatchApprovalSetId
    ticket_graph_patch_ref: TicketGraphPatchId
    required_domains: tuple[GraphPatchReviewDomain, ...]
    reviews: tuple[GraphPatchReview, ...]
    status: GraphPatchApprovalStatus
    computed_at: datetime

    @field_validator("required_domains")
    @classmethod
    def _reject_empty_or_duplicate_domains(
        cls,
        values: tuple[GraphPatchReviewDomain, ...],
    ) -> tuple[GraphPatchReviewDomain, ...]:
        _reject_empty_tuple(values, "required_domains")
        return _reject_duplicate_value_refs(values, "required_domains")

    @field_validator("reviews")
    @classmethod
    def _reject_duplicate_reviews(cls, values: tuple[GraphPatchReview, ...]) -> tuple[GraphPatchReview, ...]:
        return _reject_duplicate_value_refs(values, "reviews")

    @field_validator("computed_at")
    @classmethod
    def _require_computed_at_timezone(cls, value: datetime) -> datetime:
        return _require_timezone(value, "computed_at")

    @model_validator(mode="after")
    def _validate_ready_domains(self) -> Self:
        if self.status is GraphPatchApprovalStatus.READY_TO_COMMIT:
            required = set(self.required_domains)
            if not _REQUIRED_APPROVAL_DOMAINS.issubset(required):
                raise ValueError("ready_to_commit approval set requires planning, structural, and blocker coverage domains")
        return self


class ReworkAttempt(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    rework_attempt_id: ReworkAttemptId
    cycle_id: ReworkCycleId | str
    rework_plan_ref: ReworkPlanId
    ticket_ref: TicketId
    execution_package_ref: ExecutionPackageRef
    actor_ref: str
    provider_attempt_refs: tuple[ProviderAttemptRef, ...]
    workspace_mutation_refs: tuple[str, ...]
    command_evidence_refs: tuple[str, ...]
    source_lineage_refs: tuple[str, ...]
    run_manifest_ref: str
    submitted_at: datetime

    @field_validator("actor_ref", "run_manifest_ref")
    @classmethod
    def _reject_empty_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("text fields must not be empty")
        return normalized

    @field_validator("provider_attempt_refs")
    @classmethod
    def _reject_empty_or_duplicate_provider_refs(
        cls,
        values: tuple[ProviderAttemptRef, ...],
    ) -> tuple[ProviderAttemptRef, ...]:
        _reject_empty_tuple(values, "provider_attempt_refs")
        return _reject_duplicate_value_refs(values, "provider_attempt_refs")

    @field_validator("workspace_mutation_refs", "command_evidence_refs", "source_lineage_refs")
    @classmethod
    def _reject_empty_or_duplicate_text_refs(cls, values: tuple[str, ...], info: Any) -> tuple[str, ...]:
        normalized = _reject_empty_string_tuple(values, info.field_name)
        if len(set(normalized)) != len(normalized):
            raise ValueError(f"{info.field_name} must be unique")
        return normalized

    @field_validator("submitted_at")
    @classmethod
    def _require_submitted_at_timezone(cls, value: datetime) -> datetime:
        return _require_timezone(value, "submitted_at")


class ReworkOutcome(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    rework_outcome_id: ReworkOutcomeId
    rework_attempt_ref: ReworkAttemptId | str
    final_evidence_table_ref: str | None
    source_inventory_ref: str | None
    checker_verdict_ref: str | None
    closeout_gate_ref: str | None = None
    status: ReworkOutcomeStatus
    remaining_blocker_refs: tuple[BlockerRef, ...] = ()
    accepted_blocker_refs: tuple[BlockerRef, ...] = ()
    termination_decision_ref: ReworkTerminationDecisionId | None = None
    created_at: datetime

    @field_validator("remaining_blocker_refs", "accepted_blocker_refs")
    @classmethod
    def _reject_duplicate_blocker_refs(cls, values: tuple[BlockerRef, ...], info: Any) -> tuple[BlockerRef, ...]:
        return _reject_duplicate_value_refs(values, info.field_name)

    @field_validator("created_at")
    @classmethod
    def _require_created_at_timezone(cls, value: datetime) -> datetime:
        return _require_timezone(value, "created_at")

    @model_validator(mode="after")
    def _validate_outcome_shape(self) -> Self:
        if self.status is ReworkOutcomeStatus.ACCEPTED:
            if self.remaining_blocker_refs:
                raise ValueError("accepted outcome must not include remaining blockers")
            if not self.accepted_blocker_refs:
                raise ValueError("accepted outcome requires accepted_blocker_refs")
            for field_name in ("final_evidence_table_ref", "source_inventory_ref", "checker_verdict_ref"):
                value = getattr(self, field_name)
                if value is None or not str(value).strip():
                    raise ValueError(f"accepted outcome requires {field_name}")
        if self.status is ReworkOutcomeStatus.REWORK_REQUIRED and not self.remaining_blocker_refs:
            raise ValueError("rework_required outcome requires remaining blockers")
        if self.status is ReworkOutcomeStatus.EXHAUSTED and self.termination_decision_ref is None:
            raise ValueError("exhausted outcome requires termination_decision_ref")
        return self


class ReworkTerminationDecision(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    termination_decision_id: ReworkTerminationDecisionId
    cycle_id: ReworkCycleId | str
    reason: ReworkTerminationReason
    blocker_refs: tuple[BlockerRef, ...]
    evidence_refs: tuple[str, ...]
    decided_by_actor: ReworkActorKind
    decided_at: datetime
    rationale: str

    @field_validator("blocker_refs")
    @classmethod
    def _reject_empty_or_duplicate_blockers(cls, values: tuple[BlockerRef, ...]) -> tuple[BlockerRef, ...]:
        _reject_empty_tuple(values, "blocker_refs")
        return _reject_duplicate_value_refs(values, "blocker_refs")

    @field_validator("evidence_refs")
    @classmethod
    def _reject_empty_or_duplicate_evidence_refs(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized = _reject_empty_string_tuple(values, "evidence_refs")
        if len(set(normalized)) != len(normalized):
            raise ValueError("evidence_refs must be unique")
        return normalized

    @field_validator("decided_at")
    @classmethod
    def _require_decided_at_timezone(cls, value: datetime) -> datetime:
        return _require_timezone(value, "decided_at")

    @field_validator("rationale")
    @classmethod
    def _reject_empty_rationale(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("rationale must not be empty")
        return normalized


def validate_request_verified_sources(
    request: ReworkRequest,
    blocker_reports: tuple[BlockerReport, ...],
) -> None:
    report_by_ref = {report.blocker_report_id.value: report for report in blocker_reports}
    for source_ref in request.request_source_refs:
        if source_ref not in report_by_ref:
            raise ValueError(f"unknown blocker report source for rework request: {source_ref}")
    verified_blocker_refs = {
        blocker.value
        for report in blocker_reports
        if report.blocker_report_id.value in request.request_source_refs
        for blocker in report.blockers
    }
    for issue in request.issues:
        for blocker_ref in issue.blocker_refs:
            if blocker_ref.value not in verified_blocker_refs:
                raise ValueError(f"unknown verified blocker ref in rework request: {blocker_ref.value}")


__all__ = [
    "BlockerRef",
    "BlockerReport",
    "BlockerReportId",
    "BlockerSourceKind",
    "ExpectedFactRef",
    "GraphPatchApprovalSet",
    "GraphPatchApprovalSetId",
    "GraphPatchApprovalStatus",
    "GraphPatchOperationKind",
    "GraphPatchReview",
    "GraphPatchReviewDomain",
    "GraphPatchReviewId",
    "GraphPatchReviewStatus",
    "ObservedFactRef",
    "ReworkActorKind",
    "ReworkAttempt",
    "ReworkAttemptId",
    "ReworkCycle",
    "ReworkCycleId",
    "ReworkCycleStatus",
    "ReworkDecision",
    "ReworkDecisionId",
    "ReworkDecisionKind",
    "ReworkIssue",
    "ReworkIssueCode",
    "ReworkIssueId",
    "ReworkIssueSeverity",
    "ReworkOutcome",
    "ReworkOutcomeId",
    "ReworkOutcomeStatus",
    "ReworkPlan",
    "ReworkPlanId",
    "ReworkRequest",
    "ReworkRequestId",
    "ReworkSuspectedDomain",
    "ReworkTerminationDecision",
    "ReworkTerminationDecisionId",
    "ReworkTerminationReason",
    "RunId",
    "TicketGraphPatch",
    "TicketGraphPatchId",
    "TicketGraphPatchOperation",
    "TicketGraphPatchOperationId",
    "canonical_rework_hash",
    "validate_issue_contract_scope",
    "validate_request_verified_sources",
]
