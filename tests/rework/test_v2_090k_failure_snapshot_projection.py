from datetime import UTC, datetime
from pathlib import Path

from boardroom_os.contracts.types import (
    AcceptanceRef,
    ContractId,
    EvidenceObligationRef,
    SourceSurfaceRef,
)
from boardroom_os.rework.blocker_projection import (
    BlockerProjectionContext,
    project_v2_090k_failure_summary,
)
from boardroom_os.rework.model import (
    ReworkActorKind,
    ReworkCycleId,
    ReworkIssueCode,
    ReworkSuspectedDomain,
    RunId,
)

SNAPSHOT = Path(
    "examples/generated-workspaces/tiny-fullstack/30-audit/"
    "v2-090k-failure-snapshot/failure-summary.json"
)


def _context() -> BlockerProjectionContext:
    return BlockerProjectionContext(
        cycle_id=ReworkCycleId(value="rework-cycle.v2-100a.snapshot"),
        run_id=RunId(value="run-v2-090k-full-provider"),
        package_contract_ref=ContractId(value="package.v2-090f.tiny-library-checkout"),
        run_manifest_ref="run-manifest.v2-090f.tiny-library-checkout",
        active_acceptance_refs=(
            AcceptanceRef(value="acceptance.book.add"),
            AcceptanceRef(value="acceptance.book.list"),
            AcceptanceRef(value="acceptance.book.checkout"),
            AcceptanceRef(value="acceptance.book.return"),
            AcceptanceRef(value="acceptance.book.delete"),
            AcceptanceRef(value="acceptance.ui.backend_updates"),
            AcceptanceRef(value="acceptance.persistence.sqlite"),
            AcceptanceRef(value="acceptance.instructions.tests"),
        ),
        active_source_surface_refs=(
            SourceSurfaceRef(value="surface.backend.api"),
            SourceSurfaceRef(value="surface.frontend.ui"),
            SourceSurfaceRef(value="surface.persistence.sqlite"),
            SourceSurfaceRef(value="surface.run_manifest"),
            SourceSurfaceRef(value="surface.behavioral_probe"),
            SourceSurfaceRef(value="surface.closeout_audit"),
        ),
        active_evidence_obligation_refs=(
            EvidenceObligationRef(value="evidence.add.api"),
            EvidenceObligationRef(value="evidence.list.api"),
            EvidenceObligationRef(value="evidence.checkout.api"),
            EvidenceObligationRef(value="evidence.return.api"),
            EvidenceObligationRef(value="evidence.delete.api"),
            EvidenceObligationRef(value="evidence.ui.real_backend"),
            EvidenceObligationRef(value="evidence.sqlite.persistence"),
            EvidenceObligationRef(value="evidence.tests.instructions"),
        ),
        active_graph_version=90,
        requested_by_actor=ReworkActorKind.GOVERNANCE_ADAPTER,
        requested_at=datetime(2026, 6, 13, 12, 0, tzinfo=UTC),
    )


def test_v2_090k_failure_snapshot_projects_four_issues() -> None:
    request = project_v2_090k_failure_summary(SNAPSHOT, _context())

    assert request.request_source_refs == (
        "blocker-report.v2-090k.v2-090k-failure-snapshot.tiny-fullstack.2026-06-13",
    )
    assert len(request.issues) == 4
    assert {issue.issue_code for issue in request.issues} == {
        ReworkIssueCode.PROBE_RESPONSE_SHAPE_MISMATCH,
        ReworkIssueCode.ENV_BINDING_NOT_CONVERGED,
        ReworkIssueCode.FINAL_EVIDENCE_OLD_ACCEPTANCE_REFS,
        ReworkIssueCode.CLOSEOUT_AUDIT_OLD_RUN_REFS,
    }


def test_v2_090k_snapshot_projection_uses_active_acceptance_refs_not_ac_tiny_refs() -> None:
    request = project_v2_090k_failure_summary(SNAPSHOT, _context())

    for issue in request.issues:
        assert all(not ref.value.startswith("AC-TINY-") for ref in issue.acceptance_refs)
        assert issue.source_surface_refs
        assert issue.evidence_obligation_refs
        assert issue.required_artifact_types


def test_v2_090k_snapshot_projection_routes_domains() -> None:
    request = project_v2_090k_failure_summary(SNAPSHOT, _context())
    by_code = {issue.issue_code: issue for issue in request.issues}

    assert (
        ReworkSuspectedDomain.PROBE
        in by_code[ReworkIssueCode.PROBE_RESPONSE_SHAPE_MISMATCH].suspected_domains
    )
    assert (
        ReworkSuspectedDomain.IMPLEMENTATION
        in by_code[ReworkIssueCode.PROBE_RESPONSE_SHAPE_MISMATCH].suspected_domains
    )
    assert (
        ReworkSuspectedDomain.RUN_ENV
        in by_code[ReworkIssueCode.ENV_BINDING_NOT_CONVERGED].suspected_domains
    )
    assert (
        ReworkSuspectedDomain.EVIDENCE_PROJECTION
        in by_code[ReworkIssueCode.FINAL_EVIDENCE_OLD_ACCEPTANCE_REFS].suspected_domains
    )
    assert (
        ReworkSuspectedDomain.CLOSEOUT_AUDIT
        in by_code[ReworkIssueCode.CLOSEOUT_AUDIT_OLD_RUN_REFS].suspected_domains
    )
