from datetime import UTC, datetime
from typing import Any

import pytest

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
    GraphPatchReviewGate,
    ReworkAttemptPayload,
    ReworkPlanPayload,
    ReworkReducer,
    ReworkReducerError,
    ReworkReducerPayloadResolver,
    ReworkRequestPayload,
    ReworkReviewPayload,
    ReworkTerminalPayload,
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
    ReworkTerminationDecision,
    RunId,
    TicketGraphPatch,
    TicketGraphPatchId,
    TicketGraphPatchOperation,
    TicketGraphPatchOperationId,
)

NOW = datetime(2026, 6, 14, 10, 0, tzinfo=UTC)
PROJECT = ProjectRef(value="project.v2-100b")
ACCEPTANCE = AcceptanceRef(value="acceptance.book.add")
SURFACE = SourceSurfaceRef(value="surface.backend.api")
OBLIGATION = EvidenceObligationRef(value="evidence.add.api")
CYCLE = ReworkCycleId(value="rework-cycle.v2-100b")
REQUEST_ID = ReworkRequestId(value="rework-request.v2-100b")
PLAN_ID = ReworkPlanId(value="rework-plan.v2-100b")
PATCH_ID = TicketGraphPatchId(value="ticket-graph-patch.v2-100b")
REWORK_TICKET = TicketId(value="ticket.rework.backend-api-shape")
BLOCKER = BlockerRef(value="blocker.probe-response-shape")
ATTEMPT_ID = ReworkAttemptId(value="rework-attempt.backend-api-shape.1")
OUTCOME_ID = ReworkOutcomeId(value="rework-outcome.backend-api-shape.1")


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


def _review(
    domain: GraphPatchReviewDomain,
    role: ReworkActorKind,
    *,
    status: GraphPatchReviewStatus = GraphPatchReviewStatus.APPROVED,
    suffix: str | None = None,
) -> GraphPatchReview:
    name = suffix or domain.value
    return GraphPatchReview(
        graph_patch_review_id=GraphPatchReviewId(value=f"graph-patch-review.{name}"),
        ticket_graph_patch_ref=PATCH_ID,
        review_domain=domain,
        reviewer_actor=role,
        reviewer_role_kind=role,
        reviewer_attempt_ref=ProviderAttemptRef(value=f"provider-attempt.{role.value}.{domain.value}"),
        status=status,
        checked_invariants=(f"{domain.value} invariant checked.",),
        blockers=() if status is GraphPatchReviewStatus.APPROVED else (BLOCKER,),
        non_blocking_notes=(),
        created_at=NOW,
    )


def _approval_set(
    status: GraphPatchApprovalStatus = GraphPatchApprovalStatus.READY_TO_COMMIT,
) -> GraphPatchApprovalSet:
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
        status=status,
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


def _outcome(status: ReworkOutcomeStatus = ReworkOutcomeStatus.ACCEPTED) -> ReworkOutcome:
    return ReworkOutcome(
        rework_outcome_id=OUTCOME_ID,
        rework_attempt_ref=ATTEMPT_ID,
        final_evidence_table_ref="final-evidence-table.rework.1" if status is ReworkOutcomeStatus.ACCEPTED else None,
        source_inventory_ref="source-inventory.rework.1" if status is ReworkOutcomeStatus.ACCEPTED else None,
        checker_verdict_ref="checker-verdict.rework.1" if status is ReworkOutcomeStatus.ACCEPTED else None,
        closeout_gate_ref=None,
        status=status,
        remaining_blocker_refs=(),
        accepted_blocker_refs=(BLOCKER,) if status is ReworkOutcomeStatus.ACCEPTED else (),
        created_at=NOW,
    )


def _event(
    event_type: EventType,
    *,
    graph_version: int,
    actor_ref: str,
    payload_ref: str | None = None,
) -> EventRecord:
    payload = payload_ref or f"payload:{event_type.value}"
    return EventRecord(
        event_id=EventId(value=f"evt:{event_type.value}:{graph_version}"),
        event_type=event_type,
        project_ref=PROJECT,
        actor_ref=ActorRef(value=actor_ref),
        timestamp=NOW,
        graph_version=graph_version,
        payload_refs=(EventPayloadRef(value=payload),),
    )


class InMemoryReworkResolver(ReworkReducerPayloadResolver):
    def __init__(self, **payloads: dict[str, Any]) -> None:
        self.request_payloads = payloads.get("request_payloads", {})
        self.plan_payloads = payloads.get("plan_payloads", {})
        self.review_payloads = payloads.get("review_payloads", {})
        self.approval_payloads = payloads.get("approval_payloads", {})
        self.ticket_payloads = payloads.get("ticket_payloads", {})
        self.attempt_payloads = payloads.get("attempt_payloads", {})
        self.review_outcome_payloads = payloads.get("review_outcome_payloads", {})
        self.terminal_payloads = payloads.get("terminal_payloads", {})

    def resolve_rework_request(self, payload_ref: EventPayloadRef) -> ReworkRequestPayload:
        return self.request_payloads[payload_ref.value]

    def resolve_rework_plan(self, payload_ref: EventPayloadRef) -> ReworkPlanPayload:
        return self.plan_payloads[payload_ref.value]

    def resolve_graph_patch_review(self, payload_ref: EventPayloadRef):
        return self.review_payloads[payload_ref.value]

    def resolve_graph_patch_approval(self, payload_ref: EventPayloadRef) -> GraphPatchApprovalPayload:
        return self.approval_payloads[payload_ref.value]

    def resolve_rework_ticket_created(self, payload_ref: EventPayloadRef) -> TicketCreatedPayload:
        return self.ticket_payloads[payload_ref.value]

    def resolve_rework_attempt(self, payload_ref: EventPayloadRef) -> ReworkAttemptPayload:
        return self.attempt_payloads[payload_ref.value]

    def resolve_rework_review(self, payload_ref: EventPayloadRef) -> ReworkReviewPayload:
        return self.review_outcome_payloads[payload_ref.value]

    def resolve_rework_terminal(self, payload_ref: EventPayloadRef) -> ReworkTerminalPayload:
        return self.terminal_payloads[payload_ref.value]


def test_runtime_actor_cannot_accept_escalate_or_exhaust_rework() -> None:
    resolver = InMemoryReworkResolver(
        terminal_payloads={
            "payload:rework_accepted": ReworkTerminalPayload(
                cycle_id=CYCLE,
                outcome_ref=ReworkOutcomeId(value="rework-outcome.accepted"),
                termination_decision_ref=None,
                accepted_blocker_refs=(BLOCKER,),
                remaining_blocker_refs=(),
            )
        }
    )

    with pytest.raises(ReworkReducerError, match="runtime/executor/atomic-agent cannot emit governance"):
        ReworkReducer(resolver).reduce(
            (
                _event(
                    EventType.REWORK_ACCEPTED,
                    graph_version=50,
                    actor_ref="runtime:executor",
                    payload_ref="payload:rework_accepted",
                ),
            )
        )


def test_rework_planned_without_requested_fails() -> None:
    resolver = InMemoryReworkResolver(
        plan_payloads={
            "payload:rework_planned": ReworkPlanPayload(
                request_ref=REQUEST_ID,
                plan=_plan(),
                patch=_patch(),
            )
        }
    )

    with pytest.raises(ReworkReducerError, match="request must exist before rework_planned"):
        ReworkReducer(resolver).reduce(
            (
                _event(
                    EventType.REWORK_PLANNED,
                    graph_version=41,
                    actor_ref="seat-ceo",
                    payload_ref="payload:rework_planned",
                ),
            )
        )


def test_graph_patch_review_gate_rejects_missing_required_domain() -> None:
    incomplete = GraphPatchApprovalSet(
        approval_set_id=GraphPatchApprovalSetId(value="graph-patch-approval.incomplete"),
        ticket_graph_patch_ref=PATCH_ID,
        required_domains=_patch().required_review_domains,
        reviews=(
            _review(GraphPatchReviewDomain.PLANNING, ReworkActorKind.CEO),
            _review(GraphPatchReviewDomain.STRUCTURAL, ReworkActorKind.ARCHITECT),
            _review(GraphPatchReviewDomain.BLOCKER_COVERAGE, ReworkActorKind.CHECKER),
        ),
        status=GraphPatchApprovalStatus.INCOMPLETE,
        computed_at=NOW,
    )

    with pytest.raises(ReworkReducerError, match="missing required review domain"):
        GraphPatchReviewGate.evaluate(_patch(), incomplete)


def test_graph_patch_review_gate_rejects_rejected_review() -> None:
    rejected = GraphPatchApprovalSet(
        approval_set_id=GraphPatchApprovalSetId(value="graph-patch-approval.rejected"),
        ticket_graph_patch_ref=PATCH_ID,
        required_domains=_patch().required_review_domains,
        reviews=(
            _review(GraphPatchReviewDomain.PLANNING, ReworkActorKind.CEO),
            _review(GraphPatchReviewDomain.STRUCTURAL, ReworkActorKind.ARCHITECT),
            _review(GraphPatchReviewDomain.BLOCKER_COVERAGE, ReworkActorKind.CHECKER),
            _review(
                GraphPatchReviewDomain.BEHAVIORAL_PROBE,
                ReworkActorKind.TESTER,
                status=GraphPatchReviewStatus.REJECTED,
            ),
        ),
        status=GraphPatchApprovalStatus.REJECTED,
        computed_at=NOW,
    )

    with pytest.raises(ReworkReducerError, match="graph patch approval is not ready"):
        GraphPatchReviewGate.evaluate(_patch(), rejected)


def test_rework_ticket_created_rejects_allowed_write_set_expansion_outside_patch_surface() -> None:
    ticket_payload = TicketCreatedPayload(
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
        allowed_write_set=("10-project/**",),
        attempt_count=0,
    )
    resolver = InMemoryReworkResolver(
        request_payloads={"payload:request": ReworkRequestPayload(request=_request())},
        plan_payloads={"payload:plan": ReworkPlanPayload(request_ref=REQUEST_ID, plan=_plan(), patch=_patch())},
        approval_payloads={
            "payload:approval": GraphPatchApprovalPayload(
                patch_ref=PATCH_ID,
                approval_set=_approval_set(),
            )
        },
        ticket_payloads={"payload:ticket": ticket_payload},
    )

    with pytest.raises(ReworkReducerError, match="allowed_write_set"):
        ReworkReducer(resolver).reduce(
            (
                _event(EventType.REWORK_REQUESTED, graph_version=41, actor_ref="seat-checker", payload_ref="payload:request"),
                _event(EventType.REWORK_PLANNED, graph_version=42, actor_ref="seat-ceo", payload_ref="payload:plan"),
                _event(
                    EventType.REWORK_GRAPH_PATCH_APPROVED,
                    graph_version=43,
                    actor_ref="governance:graph-patch-review-gate",
                    payload_ref="payload:approval",
                ),
                _event(
                    EventType.REWORK_TICKET_CREATED,
                    graph_version=44,
                    actor_ref="governance:command-handler",
                    payload_ref="payload:ticket",
                ),
            )
        )


def test_rework_accepted_requires_reviewed_accepted_outcome() -> None:
    resolver = InMemoryReworkResolver(
        request_payloads={"payload:request": ReworkRequestPayload(request=_request())},
        plan_payloads={"payload:plan": ReworkPlanPayload(request_ref=REQUEST_ID, plan=_plan(), patch=_patch())},
        approval_payloads={
            "payload:approval": GraphPatchApprovalPayload(
                patch_ref=PATCH_ID,
                approval_set=_approval_set(),
            )
        },
        ticket_payloads={"payload:ticket": _ticket_payload()},
        attempt_payloads={"payload:attempt": ReworkAttemptPayload(attempt=_attempt())},
        review_outcome_payloads={
            "payload:review": ReworkReviewPayload(
                outcome=_outcome(status=ReworkOutcomeStatus.ESCALATED),
            )
        },
        terminal_payloads={
            "payload:accepted": ReworkTerminalPayload(
                cycle_id=CYCLE,
                outcome_ref=OUTCOME_ID,
                accepted_blocker_refs=(BLOCKER,),
                remaining_blocker_refs=(),
            )
        },
    )

    with pytest.raises(ReworkReducerError, match="accepted rework requires accepted outcome"):
        ReworkReducer(resolver).reduce(
            (
                _event(EventType.REWORK_REQUESTED, graph_version=41, actor_ref="seat-checker", payload_ref="payload:request"),
                _event(EventType.REWORK_PLANNED, graph_version=42, actor_ref="seat-ceo", payload_ref="payload:plan"),
                _event(
                    EventType.REWORK_GRAPH_PATCH_APPROVED,
                    graph_version=43,
                    actor_ref="governance:graph-patch-review-gate",
                    payload_ref="payload:approval",
                ),
                _event(
                    EventType.REWORK_TICKET_CREATED,
                    graph_version=44,
                    actor_ref="governance:command-handler",
                    payload_ref="payload:ticket",
                ),
                _event(EventType.REWORK_ATTEMPT_SUBMITTED, graph_version=45, actor_ref="runtime:executor", payload_ref="payload:attempt"),
                _event(EventType.REWORK_REVIEWED, graph_version=46, actor_ref="seat-checker", payload_ref="payload:review"),
                _event(
                    EventType.REWORK_ACCEPTED,
                    graph_version=47,
                    actor_ref="governance:command-handler",
                    payload_ref="payload:accepted",
                ),
            )
        )


def test_rework_accepted_requires_terminal_outcome_ref_to_match_review() -> None:
    resolver = InMemoryReworkResolver(
        request_payloads={"payload:request": ReworkRequestPayload(request=_request())},
        plan_payloads={"payload:plan": ReworkPlanPayload(request_ref=REQUEST_ID, plan=_plan(), patch=_patch())},
        approval_payloads={
            "payload:approval": GraphPatchApprovalPayload(
                patch_ref=PATCH_ID,
                approval_set=_approval_set(),
            )
        },
        ticket_payloads={"payload:ticket": _ticket_payload()},
        attempt_payloads={"payload:attempt": ReworkAttemptPayload(attempt=_attempt())},
        review_outcome_payloads={"payload:review": ReworkReviewPayload(outcome=_outcome())},
        terminal_payloads={
            "payload:accepted": ReworkTerminalPayload(
                cycle_id=CYCLE,
                outcome_ref=ReworkOutcomeId(value="rework-outcome.other"),
                accepted_blocker_refs=(BLOCKER,),
                remaining_blocker_refs=(),
            )
        },
    )

    with pytest.raises(ReworkReducerError, match="terminal outcome_ref does not match reviewed outcome"):
        ReworkReducer(resolver).reduce(
            (
                _event(EventType.REWORK_REQUESTED, graph_version=41, actor_ref="seat-checker", payload_ref="payload:request"),
                _event(EventType.REWORK_PLANNED, graph_version=42, actor_ref="seat-ceo", payload_ref="payload:plan"),
                _event(
                    EventType.REWORK_GRAPH_PATCH_APPROVED,
                    graph_version=43,
                    actor_ref="governance:graph-patch-review-gate",
                    payload_ref="payload:approval",
                ),
                _event(
                    EventType.REWORK_TICKET_CREATED,
                    graph_version=44,
                    actor_ref="governance:command-handler",
                    payload_ref="payload:ticket",
                ),
                _event(EventType.REWORK_ATTEMPT_SUBMITTED, graph_version=45, actor_ref="runtime:executor", payload_ref="payload:attempt"),
                _event(EventType.REWORK_REVIEWED, graph_version=46, actor_ref="seat-checker", payload_ref="payload:review"),
                _event(
                    EventType.REWORK_ACCEPTED,
                    graph_version=47,
                    actor_ref="governance:command-handler",
                    payload_ref="payload:accepted",
                ),
            )
        )
