from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from boardroom_os.contracts.evidence_obligation import RequiredArtifactType
from boardroom_os.contracts.types import (
    AcceptanceRef,
    ContractId,
    EvidenceObligationRef,
    SourceSurfaceRef,
)
from boardroom_os.execution.context_index import ProviderAttemptRef
from boardroom_os.execution.package import ExecutionPackageRef
from boardroom_os.graph.ticket import TicketId
from boardroom_os.rework.model import (
    BlockerRef,
    BlockerReport,
    BlockerReportId,
    BlockerSourceKind,
    ExpectedFactRef,
    GraphPatchOperationKind,
    GraphPatchReview,
    GraphPatchReviewDomain,
    GraphPatchReviewId,
    GraphPatchReviewStatus,
    ObservedFactRef,
    ReworkActorKind,
    ReworkAttempt,
    ReworkAttemptId,
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
    TicketGraphPatchId,
    TicketGraphPatchOperationId,
    validate_issue_contract_scope,
    validate_request_verified_sources,
)

NOW = datetime(2026, 6, 13, 10, 0, tzinfo=UTC)
ACTIVE_ACCEPTANCE = (AcceptanceRef(value="acceptance.book.add"),)
ACTIVE_SURFACES = (SourceSurfaceRef(value="surface.backend.api"),)
ACTIVE_OBLIGATIONS = (EvidenceObligationRef(value="evidence.add.api"),)


def _blocker_report() -> BlockerReport:
    return BlockerReport(
        blocker_report_id=BlockerReportId(value="blocker-report.final-evidence.add"),
        run_id=RunId(value="run-v2-100a"),
        source_kind=BlockerSourceKind.FINAL_EVIDENCE_TABLE,
        source_ref="final-evidence-table.acceptance.v2-090f",
        contract_refs=(ContractId(value="acceptance.v2-090f"),),
        acceptance_refs=ACTIVE_ACCEPTANCE,
        package_contract_ref=ContractId(value="package.v2-090f"),
        run_manifest_ref="run-manifest.v2-090f",
        blockers=(BlockerRef(value="final-evidence-blocker.failed.acceptance.book.add.probe"),),
        created_at=NOW,
    )


def _issue() -> ReworkIssue:
    return ReworkIssue(
        issue_id=ReworkIssueId(value="rework-issue.probe-response-shape-mismatch"),
        blocker_refs=(BlockerRef(value="final-evidence-blocker.failed.acceptance.book.add.probe"),),
        issue_code=ReworkIssueCode.PROBE_RESPONSE_SHAPE_MISMATCH,
        severity=ReworkIssueSeverity.BLOCKING,
        acceptance_refs=ACTIVE_ACCEPTANCE,
        source_surface_refs=ACTIVE_SURFACES,
        run_manifest_refs=("run-manifest.v2-090f",),
        evidence_obligation_refs=ACTIVE_OBLIGATIONS,
        observed_fact_refs=(ObservedFactRef(value="fact.response.body.book.title"),),
        expected_fact_refs=(ExpectedFactRef(value="fact.probe.path.title"),),
        suspected_domains=(
            ReworkSuspectedDomain.IMPLEMENTATION,
            ReworkSuspectedDomain.PROBE,
        ),
        required_artifact_types=(RequiredArtifactType(value="live_blackbox_integration"),),
        description="Behavioral probe expected $.title while backend returned $.book.title.",
    )


def test_rework_request_without_issues_fails() -> None:
    with pytest.raises(ValidationError, match="issues must not be empty"):
        ReworkRequest(
            rework_request_id=ReworkRequestId(value="rework-request.empty"),
            cycle_id="rework-cycle.v2-100a",
            run_id=RunId(value="run-v2-100a"),
            request_source_refs=("blocker-report.final-evidence.add",),
            issues=(),
            requested_by_actor=ReworkActorKind.CHECKER,
            requested_at=NOW,
            active_contract_refs=(
                ContractId(value="acceptance.v2-090f"),
                ContractId(value="package.v2-090f"),
            ),
            active_graph_version=41,
        )


def test_blocker_report_without_blockers_fails() -> None:
    with pytest.raises(ValidationError, match="blockers must not be empty"):
        BlockerReport(
            blocker_report_id=BlockerReportId(value="blocker-report.notes-only"),
            run_id=RunId(value="run-v2-100a"),
            source_kind=BlockerSourceKind.CHECKER_VERDICT,
            source_ref="checker-note.non-blocking",
            contract_refs=(ContractId(value="acceptance.v2-090f"),),
            acceptance_refs=ACTIVE_ACCEPTANCE,
            package_contract_ref=ContractId(value="package.v2-090f"),
            run_manifest_ref="run-manifest.v2-090f",
            blockers=(),
            created_at=NOW,
        )


def test_rework_issue_without_blocker_ref_fails() -> None:
    data = _issue().model_dump()
    data["blocker_refs"] = ()
    with pytest.raises(ValidationError, match="blocker_refs must not be empty"):
        ReworkIssue(**data)


def test_rework_issue_without_acceptance_source_surface_or_artifact_fails() -> None:
    for field_name in ("acceptance_refs", "source_surface_refs", "required_artifact_types"):
        data = _issue().model_dump()
        data[field_name] = ()
        with pytest.raises(ValidationError, match=f"{field_name} must not be empty"):
            ReworkIssue(**data)


def test_rework_issue_stale_ac_tiny_ref_fails_against_active_contract_scope() -> None:
    stale_issue = _issue().model_copy(
        update={"acceptance_refs": (AcceptanceRef(value="AC-TINY-API-BOOK-CREATE"),)}
    )

    with pytest.raises(ValueError, match="unknown acceptance_ref in rework issue"):
        validate_issue_contract_scope(
            stale_issue,
            active_acceptance_refs=ACTIVE_ACCEPTANCE,
            active_source_surface_refs=ACTIVE_SURFACES,
            active_evidence_obligation_refs=ACTIVE_OBLIGATIONS,
        )


def test_rework_plan_requires_planner_attempt_ref_and_graph_patch_ref() -> None:
    decision = ReworkDecision(
        decision_id=ReworkDecisionId(value="rework-decision.fix-api-shape"),
        decision_kind=ReworkDecisionKind.FIX_IMPLEMENTATION,
        blocker_refs=_issue().blocker_refs,
        issue_ids=(_issue().issue_id,),
        target_ticket_refs=(TicketId(value="ticket.fix-backend-create-response"),),
        target_graph_operation_refs=(
            TicketGraphPatchOperationId(value="ticket-graph-op.create-fix-ticket"),
        ),
        rationale="Fix backend response shape to match active behavioral probe.",
    )

    with pytest.raises(ValidationError, match="planner_attempt_ref"):
        ReworkPlan(
            rework_plan_id=ReworkPlanId(value="rework-plan.missing-attempt"),
            cycle_id="rework-cycle.v2-100a",
            rework_request_id=ReworkRequestId(value="rework-request.final-evidence"),
            planner_actor=ReworkActorKind.CEO,
            planner_attempt_ref=None,
            decisions=(decision,),
            ticket_graph_patch_ref=TicketGraphPatchId(value="ticket-graph-patch.fix-api-shape"),
            risk_notes=("Keep probe and implementation aligned with active contract.",),
            stop_or_escalation_conditions=("Escalate after two identical probe mismatches.",),
        )

    with pytest.raises(ValidationError, match="ticket_graph_patch_ref"):
        ReworkPlan(
            rework_plan_id=ReworkPlanId(value="rework-plan.missing-patch"),
            cycle_id="rework-cycle.v2-100a",
            rework_request_id=ReworkRequestId(value="rework-request.final-evidence"),
            planner_actor=ReworkActorKind.CEO,
            planner_attempt_ref=ProviderAttemptRef(value="provider-attempt.ceo.rework-plan"),
            decisions=(decision,),
            ticket_graph_patch_ref=None,
            risk_notes=("Keep probe and implementation aligned with active contract.",),
            stop_or_escalation_conditions=("Escalate after two identical probe mismatches.",),
        )


def test_rework_decision_rejects_unknown_operation_kind() -> None:
    with pytest.raises(ValueError):
        GraphPatchOperationKind("direct_ticket_completion")


def test_graph_patch_review_rejects_wrong_reviewer_role_for_domain() -> None:
    with pytest.raises(ValidationError, match="reviewer_role_kind does not match"):
        GraphPatchReview(
            graph_patch_review_id=GraphPatchReviewId(value="graph-patch-review.wrong-role"),
            ticket_graph_patch_ref=TicketGraphPatchId(value="ticket-graph-patch.fix-api-shape"),
            review_domain=GraphPatchReviewDomain.STRUCTURAL,
            reviewer_actor=ReworkActorKind.CHECKER,
            reviewer_role_kind=ReworkActorKind.CHECKER,
            reviewer_attempt_ref=ProviderAttemptRef(value="provider-attempt.checker.review"),
            status=GraphPatchReviewStatus.APPROVED,
            checked_invariants=("Graph patch preserves contract and dependency invariants.",),
            blockers=(),
            non_blocking_notes=(),
            created_at=NOW,
        )


def test_rework_attempt_requires_execution_provider_command_and_source_lineage() -> None:
    base = {
        "rework_attempt_id": ReworkAttemptId(value="rework-attempt.fix-api-shape.1"),
        "cycle_id": "rework-cycle.v2-100a",
        "rework_plan_ref": ReworkPlanId(value="rework-plan.fix-api-shape"),
        "ticket_ref": TicketId(value="ticket.fix-backend-create-response"),
        "execution_package_ref": ExecutionPackageRef(value="execution-package.fix-api-shape"),
        "actor_ref": "agent-seat.worker.backend",
        "provider_attempt_refs": (ProviderAttemptRef(value="provider-attempt.worker.fix-api-shape"),),
        "workspace_mutation_refs": ("workspace-mutation.fix-api-shape.server-py",),
        "command_evidence_refs": ("verification-run.backend-tests.after-rework",),
        "source_lineage_refs": ("source-lineage.backend.server-py.after-rework",),
        "run_manifest_ref": "run-manifest.v2-090f",
        "submitted_at": NOW,
    }
    for field_name in (
        "execution_package_ref",
        "provider_attempt_refs",
        "command_evidence_refs",
        "source_lineage_refs",
    ):
        data = dict(base)
        data[field_name] = None if field_name == "execution_package_ref" else ()
        with pytest.raises(ValidationError, match=field_name):
            ReworkAttempt(**data)


def test_rework_outcome_accepted_with_remaining_blockers_fails() -> None:
    with pytest.raises(ValidationError, match="accepted outcome must not include remaining blockers"):
        ReworkOutcome(
            rework_outcome_id=ReworkOutcomeId(value="rework-outcome.fix-api-shape"),
            rework_attempt_ref="rework-attempt.fix-api-shape.1",
            final_evidence_table_ref="final-evidence-table.acceptance.v2-090f.rework.1",
            source_inventory_ref="source-inventory.rework.1",
            checker_verdict_ref="checker-verdict.rework.1",
            closeout_gate_ref=None,
            status=ReworkOutcomeStatus.ACCEPTED,
            remaining_blocker_refs=(BlockerRef(value="checker-blocker.still-failing"),),
            accepted_blocker_refs=(
                BlockerRef(value="final-evidence-blocker.failed.acceptance.book.add.probe"),
            ),
            created_at=NOW,
        )


def test_rework_request_rejects_issue_without_verified_blocker_report_source() -> None:
    request = ReworkRequest(
        rework_request_id=ReworkRequestId(value="rework-request.final-evidence"),
        cycle_id="rework-cycle.v2-100a",
        run_id=RunId(value="run-v2-100a"),
        request_source_refs=("blocker-report.final-evidence.add",),
        issues=(
            _issue().model_copy(
                update={"blocker_refs": (BlockerRef(value="final-evidence-blocker.unknown"),)}
            ),
        ),
        requested_by_actor=ReworkActorKind.CHECKER,
        requested_at=NOW,
        active_contract_refs=(ContractId(value="acceptance.v2-090f"),),
        active_graph_version=41,
    )

    with pytest.raises(ValueError, match="unknown verified blocker ref"):
        validate_request_verified_sources(request, (_blocker_report(),))
