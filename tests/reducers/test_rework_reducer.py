from datetime import UTC, datetime

from boardroom_os.agents.categories import RoleCategory
from boardroom_os.agents.seat import SeatDemand
from boardroom_os.agents.skills import CapabilityTag
from boardroom_os.contracts.evidence_obligation import RequiredArtifactType
from boardroom_os.contracts.types import AcceptanceRef, ContractId, EvidenceObligationRef, SourceSurfaceRef
from boardroom_os.events.record import EventRecord
from boardroom_os.events.types import ActorRef, EventId, EventPayloadRef, EventType, ProjectRef
from boardroom_os.execution.context_index import ProviderAttemptRef
from boardroom_os.execution.package import ExecutionPackageRef
from boardroom_os.graph.ticket import TicketCreatedPayload, TicketId
from boardroom_os.reducers.rework import (
    GraphPatchApprovalPayload,
    ReworkAttemptPayload,
    ReworkPlanPayload,
    ReworkReducer,
    ReworkReducerPayloadResolver,
    ReworkRequestPayload,
    ReworkReviewPayload,
    ReworkTerminalPayload,
    ReworkTerminalStatus,
    rework_ticket_payload_to_ticket_created_payload,
)
from boardroom_os.rework.model import (
    BlockerRef,
    GraphPatchApprovalSet,
    GraphPatchApprovalSetId,
    GraphPatchApprovalStatus,
    GraphPatchOperationKind,
    GraphPatchReview,
    GraphPatchReviewDomain,
    GraphPatchReviewId,
    GraphPatchReviewStatus,
    ReworkActorKind,
    ReworkAttempt,
    ReworkAttemptId,
    ReworkCycleId,
    ReworkCycleStatus,
    ReworkDecision,
    ReworkDecisionId,
    ReworkDecisionKind,
    ReworkIssue,
    ReworkIssueCode,
    ReworkIssueId,
    ReworkIssueSeverity,
    ReworkOutcome,
    ReworkOutcomeId,
    ReworkOutcomeStatus,
    ReworkPlan,
    ReworkPlanId,
    ReworkRequest,
    ReworkRequestId,
    ReworkSuspectedDomain,
    RunId,
    TicketGraphPatch,
    TicketGraphPatchId,
    TicketGraphPatchOperation,
    TicketGraphPatchOperationId,
)

NOW = datetime(2026, 6, 14, 11, 0, tzinfo=UTC)
PROJECT = ProjectRef(value="project.v2-100b")
ACCEPTANCE = AcceptanceRef(value="acceptance.book.add")
SURFACE = SourceSurfaceRef(value="surface.backend.api")
OBLIGATION = EvidenceObligationRef(value="evidence.add.api")
CYCLE = ReworkCycleId(value="rework-cycle.v2-100b")
REQUEST_ID = ReworkRequestId(value="rework-request.v2-100b")
PLAN_ID = ReworkPlanId(value="rework-plan.v2-100b")
PATCH_ID = TicketGraphPatchId(value="ticket-graph-patch.v2-100b")
REWORK_TICKET = TicketId(value="ticket.rework.backend-api-shape")
ATTEMPT_ID = ReworkAttemptId(value="rework-attempt.backend-api-shape.1")
OUTCOME_ID = ReworkOutcomeId(value="rework-outcome.backend-api-shape.1")
BLOCKER = BlockerRef(value="blocker.probe-response-shape")


def _issue() -> ReworkIssue:
    return ReworkIssue(
        issue_id=ReworkIssueId(value="rework-issue.probe-response-shape"),
        blocker_refs=(BLOCKER,),
        issue_code=ReworkIssueCode.PROBE_RESPONSE_SHAPE_MISMATCH,
        severity=ReworkIssueSeverity.BLOCKING,
        acceptance_refs=(ACCEPTANCE,),
        source_surface_refs=(SURFACE,),
        run_manifest_refs=("run-manifest.v2-090f",),
        evidence_obligation_refs=(OBLIGATION,),
        suspected_domains=(ReworkSuspectedDomain.IMPLEMENTATION, ReworkSuspectedDomain.PROBE),
        required_artifact_types=(RequiredArtifactType(value="live_blackbox_integration"),),
        description="Probe expects $.title but backend returns $.book.title.",
    )


def _request() -> ReworkRequest:
    return ReworkRequest(
        rework_request_id=REQUEST_ID,
        cycle_id=CYCLE,
        run_id=RunId(value="run.v2-100b"),
        request_source_refs=("blocker-report.final-evidence",),
        issues=(_issue(),),
        requested_by_actor=ReworkActorKind.CHECKER,
        requested_at=NOW,
        active_contract_refs=(ContractId(value="acceptance.v2-090f"), ContractId(value="package.v2-090f")),
        active_graph_version=40,
    )


def _patch() -> TicketGraphPatch:
    operation = TicketGraphPatchOperation(
        operation_id=TicketGraphPatchOperationId(value="op.create-rework-ticket"),
        operation_kind=GraphPatchOperationKind.CREATE_REWORK_TICKET,
        target_ticket_refs=(REWORK_TICKET,),
        acceptance_refs=(ACCEPTANCE,),
        source_surface_refs=(SURFACE,),
        evidence_obligation_refs=(OBLIGATION,),
        rationale="Create bounded rework ticket for API response shape.",
    )
    return TicketGraphPatch(
        ticket_graph_patch_id=PATCH_ID,
        base_graph_version=40,
        proposed_by_plan_ref=PLAN_ID,
        operations=(operation,),
        affected_ticket_refs=(REWORK_TICKET,),
        affected_contract_refs=(ContractId(value="acceptance.v2-090f"),),
        affected_source_surface_refs=(SURFACE,),
        required_review_domains=(
            GraphPatchReviewDomain.PLANNING,
            GraphPatchReviewDomain.STRUCTURAL,
            GraphPatchReviewDomain.BLOCKER_COVERAGE,
            GraphPatchReviewDomain.BEHAVIORAL_PROBE,
        ),
        patch_hash="sha256:ticket-graph-patch.v2-100b",
    )


def _plan() -> ReworkPlan:
    decision = ReworkDecision(
        decision_id=ReworkDecisionId(value="decision.fix-api-shape"),
        decision_kind=ReworkDecisionKind.FIX_IMPLEMENTATION,
        blocker_refs=(BLOCKER,),
        issue_ids=(_issue().issue_id,),
        target_ticket_refs=(REWORK_TICKET,),
        target_graph_operation_refs=(_patch().operations[0].operation_id,),
        rationale="Fix backend implementation to satisfy active probe.",
    )
    return ReworkPlan(
        rework_plan_id=PLAN_ID,
        cycle_id=CYCLE,
        rework_request_id=REQUEST_ID,
        planner_actor=ReworkActorKind.CEO,
        planner_attempt_ref=ProviderAttemptRef(value="provider-attempt.ceo.rework-plan"),
        decisions=(decision,),
        ticket_graph_patch_ref=PATCH_ID,
        risk_notes=("Do not change acceptance refs without contract revision.",),
        stop_or_escalation_conditions=("Escalate after two identical blocker rounds.",),
    )


def _review(domain: GraphPatchReviewDomain, role: ReworkActorKind) -> GraphPatchReview:
    return GraphPatchReview(
        graph_patch_review_id=GraphPatchReviewId(value=f"graph-patch-review.{domain.value}"),
        ticket_graph_patch_ref=PATCH_ID,
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


def _approval_set() -> GraphPatchApprovalSet:
    return GraphPatchApprovalSet(
        approval_set_id=GraphPatchApprovalSetId(value="graph-patch-approval.v2-100b"),
        ticket_graph_patch_ref=PATCH_ID,
        required_domains=_patch().required_review_domains,
        reviews=(
            _review(GraphPatchReviewDomain.PLANNING, ReworkActorKind.CEO),
            _review(GraphPatchReviewDomain.STRUCTURAL, ReworkActorKind.ARCHITECT),
            _review(GraphPatchReviewDomain.BLOCKER_COVERAGE, ReworkActorKind.CHECKER),
            _review(GraphPatchReviewDomain.BEHAVIORAL_PROBE, ReworkActorKind.TESTER),
        ),
        status=GraphPatchApprovalStatus.READY_TO_COMMIT,
        computed_at=NOW,
    )


def _ticket_payload() -> TicketCreatedPayload:
    return TicketCreatedPayload(
        ticket_id=REWORK_TICKET,
        purpose="Fix backend API response shape",
        seat_demand=SeatDemand(
            required_role_category=RoleCategory.IMPLEMENTATION,
            required_capability_tags=(
                CapabilityTag(value="task.implementation"),
                CapabilityTag(value="surface.backend"),
            ),
        ),
        depends_on=(),
        acceptance_refs=(ACCEPTANCE.value,),
        source_surface_refs=(SURFACE.value,),
        evidence_obligations=(OBLIGATION.value,),
        allowed_read_refs=("contract:acceptance.v2-090f",),
        allowed_write_set=("10-project/backend/**",),
        attempt_count=0,
    )


def _attempt() -> ReworkAttempt:
    return ReworkAttempt(
        rework_attempt_id=ATTEMPT_ID,
        cycle_id=CYCLE,
        rework_plan_ref=PLAN_ID,
        ticket_ref=REWORK_TICKET,
        execution_package_ref=ExecutionPackageRef(value="execution-package.rework.backend-api-shape"),
        actor_ref="seat-worker-backend",
        provider_attempt_refs=(ProviderAttemptRef(value="provider-attempt.worker.rework"),),
        workspace_mutation_refs=("workspace-mutation.backend.server-py",),
        command_evidence_refs=("verification-run.backend-tests.rework",),
        source_lineage_refs=("source-lineage.backend.server-py.rework",),
        run_manifest_ref="run-manifest.v2-090f",
        submitted_at=NOW,
    )


def _accepted_outcome() -> ReworkOutcome:
    return ReworkOutcome(
        rework_outcome_id=OUTCOME_ID,
        rework_attempt_ref=ATTEMPT_ID,
        final_evidence_table_ref="final-evidence-table.rework.1",
        source_inventory_ref="source-inventory.rework.1",
        checker_verdict_ref="checker-verdict.rework.1",
        closeout_gate_ref=None,
        status=ReworkOutcomeStatus.ACCEPTED,
        remaining_blocker_refs=(),
        accepted_blocker_refs=(BLOCKER,),
        created_at=NOW,
    )


class InMemoryReworkResolver(ReworkReducerPayloadResolver):
    def __init__(self) -> None:
        self.request_payloads = {"payload:request": ReworkRequestPayload(request=_request())}
        self.plan_payloads = {"payload:plan": ReworkPlanPayload(request_ref=REQUEST_ID, plan=_plan(), patch=_patch())}
        self.approval_payloads = {
            "payload:approval": GraphPatchApprovalPayload(patch_ref=PATCH_ID, approval_set=_approval_set())
        }
        self.ticket_payloads = {"payload:ticket": _ticket_payload()}
        self.attempt_payloads = {"payload:attempt": ReworkAttemptPayload(attempt=_attempt())}
        self.review_payloads = {"payload:review": ReworkReviewPayload(outcome=_accepted_outcome())}
        self.terminal_payloads = {
            "payload:accepted": ReworkTerminalPayload(
                cycle_id=CYCLE,
                outcome_ref=OUTCOME_ID,
                termination_decision_ref=None,
                accepted_blocker_refs=(BLOCKER,),
                remaining_blocker_refs=(),
            )
        }

    def resolve_rework_request(self, payload_ref: EventPayloadRef) -> ReworkRequestPayload:
        return self.request_payloads[payload_ref.value]

    def resolve_rework_plan(self, payload_ref: EventPayloadRef) -> ReworkPlanPayload:
        return self.plan_payloads[payload_ref.value]

    def resolve_graph_patch_review(self, payload_ref: EventPayloadRef):
        raise AssertionError("review events are not used by this happy path")

    def resolve_graph_patch_approval(self, payload_ref: EventPayloadRef) -> GraphPatchApprovalPayload:
        return self.approval_payloads[payload_ref.value]

    def resolve_rework_ticket_created(self, payload_ref: EventPayloadRef) -> TicketCreatedPayload:
        return self.ticket_payloads[payload_ref.value]

    def resolve_rework_attempt(self, payload_ref: EventPayloadRef) -> ReworkAttemptPayload:
        return self.attempt_payloads[payload_ref.value]

    def resolve_rework_review(self, payload_ref: EventPayloadRef) -> ReworkReviewPayload:
        return self.review_payloads[payload_ref.value]

    def resolve_rework_terminal(self, payload_ref: EventPayloadRef) -> ReworkTerminalPayload:
        return self.terminal_payloads[payload_ref.value]


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


def test_rework_reducer_projects_full_governed_rework_cycle() -> None:
    projection = ReworkReducer(InMemoryReworkResolver()).reduce(
        (
            _event(EventType.REWORK_REQUESTED, 41, "seat-checker", "payload:request"),
            _event(EventType.REWORK_PLANNED, 42, "seat-ceo", "payload:plan"),
            _event(EventType.REWORK_GRAPH_PATCH_APPROVED, 43, "governance:graph-patch-review-gate", "payload:approval"),
            _event(EventType.REWORK_TICKET_CREATED, 44, "governance:command-handler", "payload:ticket"),
            _event(EventType.REWORK_ATTEMPT_STARTED, 45, "runtime:executor", "payload:attempt"),
            _event(EventType.REWORK_ATTEMPT_SUBMITTED, 46, "runtime:executor", "payload:attempt"),
            _event(EventType.REWORK_REVIEWED, 47, "seat-checker", "payload:review"),
            _event(EventType.REWORK_ACCEPTED, 48, "governance:command-handler", "payload:accepted"),
        )
    )

    assert projection.project_ref == PROJECT
    assert projection.graph_version == 48
    assert projection.cycle_id == CYCLE
    assert projection.status is ReworkCycleStatus.ACCEPTED
    assert projection.terminal_status is ReworkTerminalStatus.ACCEPTED
    assert projection.request_ref == REQUEST_ID
    assert projection.plan_ref == PLAN_ID
    assert projection.patch_ref == PATCH_ID
    assert projection.rework_ticket_refs == (REWORK_TICKET,)
    assert projection.attempt_refs == (ATTEMPT_ID,)
    assert projection.outcome_refs == (OUTCOME_ID,)
    assert projection.accepted_blocker_refs == (BLOCKER,)
    assert projection.remaining_blocker_refs == ()


def test_rework_reducer_replay_is_deterministic() -> None:
    events = (
        _event(EventType.REWORK_REQUESTED, 41, "seat-checker", "payload:request"),
        _event(EventType.REWORK_PLANNED, 42, "seat-ceo", "payload:plan"),
        _event(EventType.REWORK_GRAPH_PATCH_APPROVED, 43, "governance:graph-patch-review-gate", "payload:approval"),
        _event(EventType.REWORK_TICKET_CREATED, 44, "governance:command-handler", "payload:ticket"),
        _event(EventType.REWORK_ATTEMPT_SUBMITTED, 45, "runtime:executor", "payload:attempt"),
        _event(EventType.REWORK_REVIEWED, 46, "seat-checker", "payload:review"),
        _event(EventType.REWORK_ACCEPTED, 47, "governance:command-handler", "payload:accepted"),
    )

    first = ReworkReducer(InMemoryReworkResolver()).reduce(events)
    replayed_events = tuple(EventRecord(**event.stable_dump()) for event in events)
    second = ReworkReducer(InMemoryReworkResolver()).reduce(replayed_events)

    assert first == second
    assert first.checked_refs == second.checked_refs


def test_rework_ticket_creation_projection_remains_patch_bound() -> None:
    projection = ReworkReducer(InMemoryReworkResolver()).reduce(
        (
            _event(EventType.REWORK_REQUESTED, 41, "seat-checker", "payload:request"),
            _event(EventType.REWORK_PLANNED, 42, "seat-ceo", "payload:plan"),
            _event(EventType.REWORK_GRAPH_PATCH_APPROVED, 43, "governance:graph-patch-review-gate", "payload:approval"),
            _event(EventType.REWORK_TICKET_CREATED, 44, "governance:command-handler", "payload:ticket"),
        )
    )

    assert projection.status is ReworkCycleStatus.EXECUTING
    assert projection.rework_ticket_refs == (REWORK_TICKET,)
    assert REWORK_TICKET.value in projection.checked_refs


def test_rework_ticket_payload_adapter_returns_valid_ticket_created_payload() -> None:
    payload = rework_ticket_payload_to_ticket_created_payload(_ticket_payload(), patch=_patch())

    assert payload.ticket_id == REWORK_TICKET
