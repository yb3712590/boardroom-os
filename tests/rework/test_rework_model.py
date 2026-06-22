from datetime import UTC, datetime

from boardroom_os.checker.verdict import (
    CheckerBlockerCode,
    CheckerVerdict,
    CheckerVerdictBlocker,
    CheckerVerdictStatus,
    SourceDiffRef,
)
from boardroom_os.closeout.gate import (
    CloseoutGateBlocker,
    CloseoutGateBlockerCode,
    CloseoutGateResult,
    CloseoutGateResultRef,
    CloseoutGateVerdict,
)
from boardroom_os.contracts.evidence_obligation import RequiredArtifactType
from boardroom_os.contracts.types import (
    AcceptanceRef,
    ContractId,
    EvidenceObligationRef,
    SourceSurfaceRef,
)
from boardroom_os.evidence.table import (
    FinalEvidenceBlocker,
    FinalEvidenceBlockerCode,
    FinalEvidenceRow,
    FinalEvidenceStatus,
    FinalEvidenceTable,
    FinalEvidenceTableRef,
)
from boardroom_os.execution.context_index import ProviderAttemptRef
from boardroom_os.execution.package import ExecutionPackageRef
from boardroom_os.execution.work_product import WorkProductRef
from boardroom_os.graph.ticket import TicketId
from boardroom_os.rework.blocker_projection import (
    BlockerProjectionContext,
    project_checker_verdict_blockers,
    project_closeout_gate_blockers,
    project_final_evidence_table_blockers,
)
from boardroom_os.rework.model import (
    BlockerRef,
    BlockerReport,
    BlockerReportId,
    BlockerSourceKind,
    ExpectedFactRef,
    GraphPatchOperationKind,
    GraphPatchReviewDomain,
    ObservedFactRef,
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
    RunId,
    TicketGraphPatch,
    TicketGraphPatchId,
    TicketGraphPatchOperation,
    TicketGraphPatchOperationId,
    canonical_rework_hash,
)

NOW = datetime(2026, 6, 13, 11, 0, tzinfo=UTC)
ACCEPTANCE = AcceptanceRef(value="acceptance.book.add")
SURFACE = SourceSurfaceRef(value="surface.backend.api")
OBLIGATION = EvidenceObligationRef(value="evidence.add.api")


def _issue() -> ReworkIssue:
    return ReworkIssue(
        issue_id=ReworkIssueId(value="rework-issue.probe-response-shape-mismatch"),
        blocker_refs=(BlockerRef(value="final-evidence-blocker.failed.acceptance.book.add.probe"),),
        issue_code=ReworkIssueCode.PROBE_RESPONSE_SHAPE_MISMATCH,
        severity=ReworkIssueSeverity.BLOCKING,
        acceptance_refs=(ACCEPTANCE,),
        source_surface_refs=(SURFACE,),
        run_manifest_refs=("run-manifest.v2-090f",),
        evidence_obligation_refs=(OBLIGATION,),
        observed_fact_refs=(ObservedFactRef(value="fact.response.body.book.title"),),
        expected_fact_refs=(ExpectedFactRef(value="fact.probe.path.title"),),
        suspected_domains=(
            ReworkSuspectedDomain.IMPLEMENTATION,
            ReworkSuspectedDomain.PROBE,
        ),
        required_artifact_types=(RequiredArtifactType(value="live_blackbox_integration"),),
        description="Behavioral probe expected $.title while backend returned $.book.title.",
    )


def build_rework_chain() -> tuple[ReworkRequest, ReworkPlan, ReworkOutcome]:
    issue = _issue()
    blocker_report = BlockerReport(
        blocker_report_id=BlockerReportId(value="blocker-report.final-evidence.add"),
        run_id=RunId(value="run-v2-100a"),
        source_kind=BlockerSourceKind.FINAL_EVIDENCE_TABLE,
        source_ref="final-evidence-table.acceptance.v2-090f",
        contract_refs=(ContractId(value="acceptance.v2-090f"),),
        acceptance_refs=(ACCEPTANCE,),
        package_contract_ref=ContractId(value="package.v2-090f"),
        run_manifest_ref="run-manifest.v2-090f",
        blockers=issue.blocker_refs,
        created_at=NOW,
    )
    request = ReworkRequest(
        rework_request_id=ReworkRequestId(value="rework-request.final-evidence"),
        cycle_id="rework-cycle.v2-100a",
        run_id=RunId(value="run-v2-100a"),
        request_source_refs=(blocker_report.blocker_report_id.value,),
        issues=(issue,),
        requested_by_actor=ReworkActorKind.CHECKER,
        requested_at=NOW,
        active_contract_refs=(
            ContractId(value="acceptance.v2-090f"),
            ContractId(value="package.v2-090f"),
        ),
        active_graph_version=41,
    )
    create_op = TicketGraphPatchOperation(
        operation_id=TicketGraphPatchOperationId(value="ticket-graph-op.create-fix-ticket"),
        operation_kind=GraphPatchOperationKind.CREATE_REWORK_TICKET,
        target_ticket_refs=(TicketId(value="ticket.fix-backend-create-response"),),
        acceptance_refs=(ACCEPTANCE,),
        source_surface_refs=(SURFACE,),
        evidence_obligation_refs=(OBLIGATION,),
        rationale="Create a bounded rework ticket for the response shape mismatch.",
    )
    block_op = TicketGraphPatchOperation(
        operation_id=TicketGraphPatchOperationId(value="ticket-graph-op.block-original-ticket"),
        operation_kind=GraphPatchOperationKind.MARK_TICKET_BLOCKED_BY_REWORK,
        target_ticket_refs=(TicketId(value="ticket.backend-create-book"),),
        acceptance_refs=(ACCEPTANCE,),
        source_surface_refs=(SURFACE,),
        evidence_obligation_refs=(OBLIGATION,),
        rationale="Keep the original ticket blocked until fresh evidence passes.",
    )
    patch = TicketGraphPatch(
        ticket_graph_patch_id=TicketGraphPatchId(value="ticket-graph-patch.fix-api-shape"),
        base_graph_version=41,
        proposed_by_plan_ref=ReworkPlanId(value="rework-plan.fix-api-shape"),
        operations=(create_op, block_op),
        affected_ticket_refs=(
            TicketId(value="ticket.fix-backend-create-response"),
            TicketId(value="ticket.backend-create-book"),
        ),
        affected_contract_refs=(ContractId(value="acceptance.v2-090f"),),
        affected_source_surface_refs=(SURFACE,),
        required_review_domains=(
            GraphPatchReviewDomain.PLANNING,
            GraphPatchReviewDomain.STRUCTURAL,
            GraphPatchReviewDomain.BLOCKER_COVERAGE,
            GraphPatchReviewDomain.BEHAVIORAL_PROBE,
        ),
        patch_hash="sha256:ticket-graph-patch.fix-api-shape",
    )
    decision = ReworkDecision(
        decision_id=ReworkDecisionId(value="rework-decision.fix-api-shape"),
        decision_kind=ReworkDecisionKind.FIX_IMPLEMENTATION,
        blocker_refs=issue.blocker_refs,
        issue_ids=(issue.issue_id,),
        target_ticket_refs=(TicketId(value="ticket.fix-backend-create-response"),),
        target_graph_operation_refs=(create_op.operation_id,),
        rationale="Fix backend response shape to match active behavioral probe.",
    )
    plan = ReworkPlan(
        rework_plan_id=patch.proposed_by_plan_ref,
        cycle_id="rework-cycle.v2-100a",
        rework_request_id=request.rework_request_id,
        planner_actor=ReworkActorKind.CEO,
        planner_attempt_ref=ProviderAttemptRef(value="provider-attempt.ceo.rework-plan"),
        decisions=(decision,),
        ticket_graph_patch_ref=patch.ticket_graph_patch_id,
        risk_notes=("Keep probe and implementation aligned with active contract.",),
        stop_or_escalation_conditions=("Escalate after two identical probe mismatches.",),
    )
    attempt = ReworkAttempt(
        rework_attempt_id=ReworkAttemptId(value="rework-attempt.fix-api-shape.1"),
        cycle_id="rework-cycle.v2-100a",
        rework_plan_ref=plan.rework_plan_id,
        ticket_ref=TicketId(value="ticket.fix-backend-create-response"),
        execution_package_ref=ExecutionPackageRef(value="execution-package.fix-api-shape"),
        actor_ref="agent-seat.worker.backend",
        provider_attempt_refs=(ProviderAttemptRef(value="provider-attempt.worker.fix-api-shape"),),
        workspace_mutation_refs=("workspace-mutation.fix-api-shape.server-py",),
        command_evidence_refs=("verification-run.backend-tests.after-rework",),
        source_lineage_refs=("source-lineage.backend.server-py.after-rework",),
        run_manifest_ref="run-manifest.v2-090f",
        submitted_at=NOW,
    )
    outcome = ReworkOutcome(
        rework_outcome_id=ReworkOutcomeId(value="rework-outcome.fix-api-shape"),
        rework_attempt_ref=attempt.rework_attempt_id,
        final_evidence_table_ref="final-evidence-table.acceptance.v2-090f.rework.1",
        source_inventory_ref="source-inventory.rework.1",
        checker_verdict_ref="checker-verdict.rework.1",
        closeout_gate_ref=None,
        status=ReworkOutcomeStatus.ACCEPTED,
        remaining_blocker_refs=(),
        accepted_blocker_refs=issue.blocker_refs,
        created_at=NOW,
    )

    assert request.issues == (issue,)
    assert plan.planner_actor is ReworkActorKind.CEO
    assert attempt.provider_attempt_refs == (
        ProviderAttemptRef(value="provider-attempt.worker.fix-api-shape"),
    )
    assert outcome.status is ReworkOutcomeStatus.ACCEPTED
    return request, plan, outcome


def _projection_context(actor: ReworkActorKind = ReworkActorKind.CHECKER) -> BlockerProjectionContext:
    return BlockerProjectionContext(
        cycle_id=ReworkCycleId(value="rework-cycle.v2-100a"),
        run_id=RunId(value="run-v2-100a"),
        package_contract_ref=ContractId(value="package.v2-090f"),
        run_manifest_ref="run-manifest.v2-090f",
        active_acceptance_refs=(ACCEPTANCE,),
        active_source_surface_refs=(SURFACE,),
        active_evidence_obligation_refs=(OBLIGATION,),
        active_graph_version=41,
        requested_by_actor=actor,
        requested_at=NOW,
    )


def test_builds_full_rework_chain_from_blocker_to_accepted_outcome() -> None:
    request, plan, outcome = build_rework_chain()

    assert request.requested_by_actor is ReworkActorKind.CHECKER
    assert plan.ticket_graph_patch_ref == TicketGraphPatchId(value="ticket-graph-patch.fix-api-shape")
    assert outcome.accepted_blocker_refs == _issue().blocker_refs


def test_rework_chain_serializes_and_hashes_deterministically() -> None:
    request, plan, outcome = build_rework_chain()

    first = (
        canonical_rework_hash(request),
        canonical_rework_hash(plan),
        canonical_rework_hash(outcome),
    )
    second = (
        canonical_rework_hash(request.model_validate(request.model_dump())),
        canonical_rework_hash(plan.model_validate(plan.model_dump())),
        canonical_rework_hash(outcome.model_validate(outcome.model_dump())),
    )

    assert first == second
    assert all(len(value) == 64 for value in first)


def test_rework_package_exports_v2_100b_reducer_api() -> None:
    from boardroom_os.reducers import rework as rework_reducer

    for name in (
        "GraphPatchReviewGate",
        "ReworkProjection",
        "ReworkReducer",
        "ReworkReducerError",
        "ReworkTerminalStatus",
    ):
        assert hasattr(rework_reducer, name)


def test_build_rework_request_from_final_evidence_missing_row() -> None:
    table = FinalEvidenceTable(
        final_evidence_table_id=FinalEvidenceTableRef(value="final-evidence-table.acceptance.v2-090f"),
        acceptance_contract_ref=ContractId(value="acceptance.v2-090f"),
        generated_at=NOW,
        rows=(
            FinalEvidenceRow(
                acceptance_ref=ACCEPTANCE,
                statement="Book add API must return the created title.",
                status=FinalEvidenceStatus.MISSING,
                verified_evidence_refs=(),
                missing_required_artifact_types=(
                    RequiredArtifactType(value="live_blackbox_integration"),
                ),
                blockers=(),
            ),
        ),
    )

    request = project_final_evidence_table_blockers(table, _projection_context())

    assert len(request.issues) == 1
    assert request.request_source_refs == (
        "blocker-report.final-evidence.final-evidence-table.acceptance.v2-090f",
    )
    assert request.issues[0].issue_code is ReworkIssueCode.FINAL_EVIDENCE_MISSING
    assert request.issues[0].blocker_refs == (
        BlockerRef(value="final-evidence-missing.acceptance.book.add"),
    )


def test_build_rework_request_from_checker_verdict_blocker() -> None:
    verdict = CheckerVerdict(
        ticket_ref=TicketId(value="ticket.backend"),
        work_product_ref=WorkProductRef(value="work-product.backend"),
        source_diff_ref=SourceDiffRef(value="source-diff.backend"),
        acceptance_contract_ref=ContractId(value="acceptance.v2-090f"),
        final_evidence_table_ref=FinalEvidenceTableRef(value="final-evidence-table.acceptance.v2-090f"),
        status=CheckerVerdictStatus.REWORK_REQUIRED,
        blockers=(
            CheckerVerdictBlocker(
                code=CheckerBlockerCode.FINAL_EVIDENCE_FAILED,
                message="Final evidence row failed for add API.",
                acceptance_ref=ACCEPTANCE,
                related_ref="final-evidence-table.acceptance.v2-090f",
                source="checker",
            ),
        ),
        checked_at=NOW,
    )

    request = project_checker_verdict_blockers(verdict, _projection_context())

    assert len(request.issues) == 1
    assert request.request_source_refs == (
        "blocker-report.checker.checker-verdict.ticket.backend.final-evidence-table.acceptance.v2-090f",
    )
    assert request.issues[0].issue_code is ReworkIssueCode.FINAL_EVIDENCE_FAILED
    assert request.requested_by_actor is ReworkActorKind.CHECKER


def test_build_rework_request_from_closeout_old_run_audit_failure() -> None:
    result = CloseoutGateResult(
        closeout_gate_result_id=CloseoutGateResultRef(value="closeout-gate-result.rework"),
        verdict=CloseoutGateVerdict.BLOCKED,
        blockers=(
            CloseoutGateBlocker(
                code=CloseoutGateBlockerCode.PROCESS_AUDIT_NOT_READY,
                message="Process audit references an old run.",
                related_ref="30-audit/process-audit.md",
            ),
        ),
        checked_refs=("final-evidence-table.acceptance.v2-090f",),
    )

    request = project_closeout_gate_blockers(
        result,
        _projection_context(ReworkActorKind.CLOSEOUT_GATE),
    )

    assert len(request.issues) == 1
    assert request.request_source_refs == ("blocker-report.closeout.closeout-gate-result.rework",)
    assert request.issues[0].issue_code is ReworkIssueCode.CLOSEOUT_AUDIT_OLD_RUN_REFS
    assert ReworkSuspectedDomain.CLOSEOUT_AUDIT in request.issues[0].suspected_domains


def test_build_rework_request_from_generic_closeout_gate_failure() -> None:
    result = CloseoutGateResult(
        closeout_gate_result_id=CloseoutGateResultRef(value="closeout-gate-result.generic"),
        verdict=CloseoutGateVerdict.BLOCKED,
        blockers=(
            CloseoutGateBlocker(
                code=CloseoutGateBlockerCode.REF_MISMATCH,
                message="Final evidence table ref differs from closeout gate input.",
                related_ref="final-evidence-table.acceptance.v2-090f",
            ),
        ),
        checked_refs=("final-evidence-table.acceptance.v2-090f",),
    )

    request = project_closeout_gate_blockers(
        result,
        _projection_context(ReworkActorKind.CLOSEOUT_GATE),
    )

    assert len(request.issues) == 1
    assert request.request_source_refs == ("blocker-report.closeout.closeout-gate-result.generic",)
    assert request.issues[0].issue_code is ReworkIssueCode.CLOSEOUT_GATE_FAILURE


def test_rework_package_exports_v2_100a_public_api() -> None:
    import boardroom_os.rework as rework

    for name in (
        "BlockerReport",
        "ReworkIssue",
        "ReworkRequest",
        "ReworkPlan",
        "TicketGraphPatch",
        "GraphPatchReview",
        "ReworkAttempt",
        "ReworkOutcome",
        "project_v2_090k_failure_summary",
    ):
        assert hasattr(rework, name)
