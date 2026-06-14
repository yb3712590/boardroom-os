from datetime import UTC, datetime
from pathlib import Path

from boardroom_os.agents.categories import RoleCategory
from boardroom_os.agents.seat import SeatDemand
from boardroom_os.agents.skills import CapabilityTag
from boardroom_os.contracts.types import AcceptanceRef, ContractId, EvidenceObligationRef, SourceSurfaceRef
from boardroom_os.events.record import EventRecord
from boardroom_os.events.types import ActorRef, EventId, EventPayloadRef, EventType, ProjectRef
from boardroom_os.execution.context_index import ProviderAttemptRef
from boardroom_os.graph.ticket import TicketCreatedPayload, TicketId
from boardroom_os.providers.attempt import ProviderArtifactRef
from boardroom_os.reducers.rework import (
    GraphPatchApprovalPayload,
    GraphPatchReviewPayload,
    ReworkPlanPayload,
    ReworkReducer,
    ReworkReducerPayloadResolver,
    ReworkRequestPayload,
)
from boardroom_os.rework.blocker_projection import (
    BlockerProjectionContext,
    project_v2_090k_failure_summary,
)
from boardroom_os.rework.model import (
    BlockerRef,
    GraphPatchApprovalSet,
    GraphPatchApprovalStatus,
    GraphPatchOperationKind,
    GraphPatchReview,
    GraphPatchReviewDomain,
    GraphPatchReviewId,
    GraphPatchReviewStatus,
    ReworkActorKind,
    ReworkCycleId,
    ReworkCycleStatus,
    ReworkDecision,
    ReworkDecisionId,
    ReworkDecisionKind,
    ReworkIssue,
    ReworkIssueCode,
    ReworkPlan,
    ReworkPlanId,
    ReworkRequest,
    RunId,
    TicketGraphPatch,
    TicketGraphPatchId,
    TicketGraphPatchOperation,
    TicketGraphPatchOperationId,
)
from boardroom_os.rework.planner import (
    CeoReworkPlannerInput,
    CeoReworkPlannerOutput,
    validate_ceo_rework_plan,
)
from boardroom_os.rework.ticket_graph_patch import (
    RequiredReviewDomainInput,
    build_graph_patch_approval_set,
    infer_required_review_domains,
)
from tests.negative.test_ceo_rework_planner_fail_closed import (
    CEO_ATTEMPT_REF,
    CEO_HOOK_REF,
    PLANNER_PACKAGE,
    _provider_attempt,
)

SNAPSHOT = Path(
    "examples/generated-workspaces/tiny-fullstack/30-audit/"
    "v2-090k-failure-snapshot/failure-summary.json"
)
NOW = datetime(2026, 6, 14, 14, 0, tzinfo=UTC)
PROJECT = ProjectRef(value="project.v2-100c")

ACTIVE_ACCEPTANCE_REFS = (
    AcceptanceRef(value="acceptance.book.add"),
    AcceptanceRef(value="acceptance.book.list"),
    AcceptanceRef(value="acceptance.book.checkout"),
    AcceptanceRef(value="acceptance.book.return"),
    AcceptanceRef(value="acceptance.book.delete"),
    AcceptanceRef(value="acceptance.ui.backend_updates"),
    AcceptanceRef(value="acceptance.persistence.sqlite"),
    AcceptanceRef(value="acceptance.instructions.tests"),
)
ACTIVE_SOURCE_SURFACE_REFS = (
    SourceSurfaceRef(value="surface.backend.api"),
    SourceSurfaceRef(value="surface.frontend.ui"),
    SourceSurfaceRef(value="surface.persistence.sqlite"),
    SourceSurfaceRef(value="surface.run_manifest"),
    SourceSurfaceRef(value="surface.behavioral_probe"),
    SourceSurfaceRef(value="surface.closeout_audit"),
)
ACTIVE_EVIDENCE_OBLIGATION_REFS = (
    EvidenceObligationRef(value="evidence.add.api"),
    EvidenceObligationRef(value="evidence.list.api"),
    EvidenceObligationRef(value="evidence.checkout.api"),
    EvidenceObligationRef(value="evidence.return.api"),
    EvidenceObligationRef(value="evidence.delete.api"),
    EvidenceObligationRef(value="evidence.ui.real_backend"),
    EvidenceObligationRef(value="evidence.sqlite.persistence"),
    EvidenceObligationRef(value="evidence.tests.instructions"),
)
ACTIVE_CONTRACT_REFS = (
    ContractId(value="package.v2-090f.tiny-library-checkout"),
)
PACKAGE_CONTRACT_REF = ContractId(value="package.v2-090f.tiny-library-checkout")
RUN_MANIFEST_REF = "run-manifest.v2-090f.tiny-library-checkout"


def _request() -> ReworkRequest:
    return project_v2_090k_failure_summary(
        SNAPSHOT,
        BlockerProjectionContext(
            cycle_id=ReworkCycleId(value="rework-cycle.v2-100c.snapshot"),
            run_id=RunId(value="run-v2-090k-full-provider"),
            package_contract_ref=PACKAGE_CONTRACT_REF,
            run_manifest_ref=RUN_MANIFEST_REF,
            active_acceptance_refs=ACTIVE_ACCEPTANCE_REFS,
            active_source_surface_refs=ACTIVE_SOURCE_SURFACE_REFS,
            active_evidence_obligation_refs=ACTIVE_EVIDENCE_OBLIGATION_REFS,
            active_graph_version=90,
            requested_by_actor=ReworkActorKind.GOVERNANCE_ADAPTER,
            requested_at=datetime(2026, 6, 13, 12, 0, tzinfo=UTC),
        ),
    )


def _issue(code: ReworkIssueCode) -> ReworkIssue:
    return next(issue for issue in _request().issues if issue.issue_code is code)


def _planner_input(request: ReworkRequest) -> CeoReworkPlannerInput:
    return CeoReworkPlannerInput(
        rework_request=request,
        blocker_reports=(),
        current_graph_version=request.active_graph_version,
        active_contract_refs=ACTIVE_CONTRACT_REFS,
        active_acceptance_refs=ACTIVE_ACCEPTANCE_REFS,
        active_source_surface_refs=ACTIVE_SOURCE_SURFACE_REFS,
        active_evidence_obligation_refs=ACTIVE_EVIDENCE_OBLIGATION_REFS,
        package_contract_ref=PACKAGE_CONTRACT_REF,
        run_manifest_ref=RUN_MANIFEST_REF,
        planner_execution_package_ref=PLANNER_PACKAGE,
        planner_role_prompt_hook_ref=CEO_HOOK_REF,
    )


def _plan_patch(
    *,
    request: ReworkRequest,
    issue: ReworkIssue,
    ticket_id: str,
    decision_kind: ReworkDecisionKind = ReworkDecisionKind.FIX_IMPLEMENTATION,
) -> tuple[ReworkPlan, TicketGraphPatch]:
    plan_id = ReworkPlanId(value=f"rework-plan.v2-100c.{ticket_id}")
    patch_id = TicketGraphPatchId(value=f"ticket-graph-patch.v2-100c.{ticket_id}")
    ticket_ref = TicketId(value=ticket_id)
    operation = TicketGraphPatchOperation(
        operation_id=TicketGraphPatchOperationId(value=f"op.{ticket_id}"),
        operation_kind=GraphPatchOperationKind.CREATE_REWORK_TICKET,
        target_ticket_refs=(ticket_ref,),
        acceptance_refs=issue.acceptance_refs,
        source_surface_refs=issue.source_surface_refs,
        evidence_obligation_refs=issue.evidence_obligation_refs,
        rationale=f"Create bounded rework ticket for {issue.issue_code.value}.",
    )
    domains = infer_required_review_domains(
        RequiredReviewDomainInput(issues=(issue,), operations=(operation,))
    )
    patch = TicketGraphPatch(
        ticket_graph_patch_id=patch_id,
        base_graph_version=request.active_graph_version,
        proposed_by_plan_ref=plan_id,
        operations=(operation,),
        affected_ticket_refs=(ticket_ref,),
        affected_contract_refs=ACTIVE_CONTRACT_REFS,
        affected_source_surface_refs=issue.source_surface_refs,
        required_review_domains=domains,
        patch_hash="sha256:pending",
    )
    decision = ReworkDecision(
        decision_id=ReworkDecisionId(value=f"decision.{ticket_id}"),
        decision_kind=decision_kind,
        blocker_refs=tuple(blocker for blocker in issue.blocker_refs),
        issue_ids=(issue.issue_id,),
        target_ticket_refs=(ticket_ref,),
        target_graph_operation_refs=(operation.operation_id,),
        rationale=f"Resolve {issue.issue_code.value} through governed graph patch.",
    )
    plan = ReworkPlan(
        rework_plan_id=plan_id,
        cycle_id=request.cycle_id,
        rework_request_id=request.rework_request_id,
        planner_actor=ReworkActorKind.CEO,
        planner_attempt_ref=CEO_ATTEMPT_REF,
        decisions=(decision,),
        ticket_graph_patch_ref=patch_id,
        risk_notes=("Do not reuse stale evidence or old run ids.",),
        stop_or_escalation_conditions=("Escalate if the same blocker remains after rework.",),
    )
    return plan, patch


def _review(domain: GraphPatchReviewDomain, patch: TicketGraphPatch) -> GraphPatchReview:
    roles = {
        GraphPatchReviewDomain.PLANNING: ReworkActorKind.CEO,
        GraphPatchReviewDomain.STRUCTURAL: ReworkActorKind.ARCHITECT,
        GraphPatchReviewDomain.BLOCKER_COVERAGE: ReworkActorKind.CHECKER,
        GraphPatchReviewDomain.BEHAVIORAL_PROBE: ReworkActorKind.TESTER,
        GraphPatchReviewDomain.RUN_ENV_READINESS: ReworkActorKind.RELEASE_DEVOPS,
        GraphPatchReviewDomain.CLOSEOUT_FACT_CHAIN: ReworkActorKind.CLOSEOUT,
    }
    role = roles[domain]
    return GraphPatchReview(
        graph_patch_review_id=GraphPatchReviewId(value=f"graph-patch-review.{domain.value}.{patch.ticket_graph_patch_id.value}"),
        ticket_graph_patch_ref=patch.ticket_graph_patch_id,
        review_domain=domain,
        reviewer_actor=role,
        reviewer_role_kind=role,
        reviewer_attempt_ref=ProviderAttemptRef(value=f"provider-attempt.{role.value}.{domain.value}"),
        status=GraphPatchReviewStatus.APPROVED,
        checked_invariants=(f"{domain.value} invariant checked.",),
        blockers=(),
        non_blocking_notes=(),
        created_at=NOW,
    )


class _Resolver(ReworkReducerPayloadResolver):
    def __init__(
        self,
        *,
        request: ReworkRequest,
        plan: ReworkPlan,
        patch: TicketGraphPatch,
        reviews: tuple[GraphPatchReview, ...],
        approval_set: GraphPatchApprovalSet,
        ticket: TicketCreatedPayload,
    ) -> None:
        self.request = request
        self.plan = plan
        self.patch = patch
        self.reviews = {f"payload:review:{review.review_domain.value}": review for review in reviews}
        self.approval_set = approval_set
        self.ticket = ticket

    def resolve_rework_request(self, payload_ref: EventPayloadRef) -> ReworkRequestPayload:
        return ReworkRequestPayload(request=self.request)

    def resolve_rework_plan(self, payload_ref: EventPayloadRef) -> ReworkPlanPayload:
        return ReworkPlanPayload(request_ref=self.request.rework_request_id, plan=self.plan, patch=self.patch)

    def resolve_graph_patch_review(self, payload_ref: EventPayloadRef) -> GraphPatchReviewPayload:
        return GraphPatchReviewPayload(patch_ref=self.patch.ticket_graph_patch_id, review=self.reviews[payload_ref.value])

    def resolve_graph_patch_approval(self, payload_ref: EventPayloadRef) -> GraphPatchApprovalPayload:
        return GraphPatchApprovalPayload(patch_ref=self.patch.ticket_graph_patch_id, approval_set=self.approval_set)

    def resolve_rework_ticket_created(self, payload_ref: EventPayloadRef) -> TicketCreatedPayload:
        return self.ticket


def _event(event_type: EventType, graph_version: int, actor_ref: str, payload_ref: str) -> EventRecord:
    return EventRecord(
        event_id=EventId(value=f"evt:{event_type.value}:{graph_version}"),
        event_type=event_type,
        project_ref=PROJECT,
        actor_ref=ActorRef(value=actor_ref),
        timestamp=NOW,
        graph_version=graph_version,
        payload_refs=(EventPayloadRef(value=payload_ref),),
    )


def _ticket_payload(ticket_id: TicketId, issue: ReworkIssue) -> TicketCreatedPayload:
    write_set_by_surface = {
        "surface.backend.api": "10-project/backend/**",
        "surface.frontend.ui": "10-project/frontend/**",
        "surface.persistence.sqlite": "10-project/backend/db/**",
        "surface.run_manifest": "00-boardroom/run-manifest.json",
        "surface.behavioral_probe": "20-evidence/behavioral-probes/**",
        "surface.closeout_audit": "30-audit/closeout/**",
    }
    allowed_write_set = tuple(
        write_set_by_surface[ref.value]
        for ref in issue.source_surface_refs
    )
    return TicketCreatedPayload(
        ticket_id=ticket_id,
        purpose=f"Rework {issue.issue_code.value}",
        seat_demand=SeatDemand(
            required_role_category=RoleCategory.IMPLEMENTATION,
            required_capability_tags=(CapabilityTag(value="task.rework"),),
        ),
        depends_on=(),
        acceptance_refs=tuple(ref.value for ref in issue.acceptance_refs),
        source_surface_refs=tuple(ref.value for ref in issue.source_surface_refs),
        evidence_obligations=tuple(ref.value for ref in issue.evidence_obligation_refs),
        allowed_read_refs=("contract:acceptance.v2-090f.tiny-library-checkout",),
        allowed_write_set=allowed_write_set,
        attempt_count=0,
    )


def _validate_and_reduce(
    *,
    issue_code: ReworkIssueCode,
    ticket_id: str,
    decision_kind: ReworkDecisionKind = ReworkDecisionKind.FIX_IMPLEMENTATION,
) -> tuple[ReworkPlan, TicketGraphPatch, GraphPatchApprovalSet]:
    request = _request().model_copy(update={"issues": (_issue(issue_code),)})
    issue = request.issues[0]
    plan, patch = _plan_patch(
        request=request,
        issue=issue,
        ticket_id=ticket_id,
        decision_kind=decision_kind,
    )
    output = CeoReworkPlannerOutput(
        planner_input=_planner_input(request),
        provider_attempt=_provider_attempt(),
        plan=plan,
        patch=patch,
        parsed_payload_ref=ProviderArtifactRef(value="provider-artifact.parsed.ceo-rework-plan"),
        validated_at=NOW,
    )
    assert validate_ceo_rework_plan(output) == output
    reviews = tuple(_review(domain, patch) for domain in patch.required_review_domains)
    approval_set = build_graph_patch_approval_set(patch, reviews, computed_at=NOW)
    assert approval_set.status is GraphPatchApprovalStatus.READY_TO_COMMIT
    ticket = _ticket_payload(patch.affected_ticket_refs[0], issue)
    resolver = _Resolver(
        request=request,
        plan=plan,
        patch=patch,
        reviews=reviews,
        approval_set=approval_set,
        ticket=ticket,
    )
    events = (
        _event(EventType.REWORK_REQUESTED, 91, "seat-checker", "payload:request"),
        _event(EventType.REWORK_PLANNED, 92, "seat-ceo", "payload:plan"),
        *(
            _event(
                EventType.REWORK_GRAPH_PATCH_REVIEWED,
                93 + index,
                f"seat-{review.reviewer_role_kind.value}",
                f"payload:review:{review.review_domain.value}",
            )
            for index, review in enumerate(reviews)
        ),
        _event(EventType.REWORK_GRAPH_PATCH_APPROVED, 100, "governance:graph-patch-review-gate", "payload:approval"),
        _event(EventType.REWORK_TICKET_CREATED, 101, "governance:command-handler", "payload:ticket"),
    )
    projection = ReworkReducer(resolver).reduce(events)
    assert projection.status is ReworkCycleStatus.EXECUTING
    assert projection.rework_ticket_refs == (TicketId(value=ticket_id),)
    return plan, patch, approval_set


def test_probe_mismatch_plan_requires_behavioral_probe_review_and_commits_ticket() -> None:
    _plan, patch, _approval_set = _validate_and_reduce(
        issue_code=ReworkIssueCode.PROBE_RESPONSE_SHAPE_MISMATCH,
        ticket_id="ticket.rework.backend-api-shape",
        decision_kind=ReworkDecisionKind.FIX_CONTRACT_OR_PROBE,
    )

    assert GraphPatchReviewDomain.BEHAVIORAL_PROBE in patch.required_review_domains


def test_env_binding_plan_requires_release_devops_review() -> None:
    _plan, patch, _approval_set = _validate_and_reduce(
        issue_code=ReworkIssueCode.ENV_BINDING_NOT_CONVERGED,
        ticket_id="ticket.rework.run-manifest-env-binding",
        decision_kind=ReworkDecisionKind.FIX_CONTRACT_OR_PROBE,
    )

    assert GraphPatchReviewDomain.RUN_ENV_READINESS in patch.required_review_domains


def test_stale_acceptance_refs_plan_uses_active_refs_only() -> None:
    plan, patch, _approval_set = _validate_and_reduce(
        issue_code=ReworkIssueCode.FINAL_EVIDENCE_OLD_ACCEPTANCE_REFS,
        ticket_id="ticket.rework.final-evidence-active-refs",
    )

    payload = plan.model_dump(mode="json") | patch.model_dump(mode="json")
    assert "AC-TINY-" not in str(payload)


def test_closeout_old_run_plan_requires_closeout_fact_chain_review() -> None:
    _plan, patch, _approval_set = _validate_and_reduce(
        issue_code=ReworkIssueCode.CLOSEOUT_AUDIT_OLD_RUN_REFS,
        ticket_id="ticket.rework.closeout-same-run-fact-chain",
        decision_kind=ReworkDecisionKind.SPLIT_TICKET,
    )

    assert GraphPatchReviewDomain.CLOSEOUT_FACT_CHAIN in patch.required_review_domains
