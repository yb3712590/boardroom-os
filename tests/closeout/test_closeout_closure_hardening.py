from __future__ import annotations

from datetime import UTC, datetime

import pytest

from boardroom_os.closeout.closure import (
    CloseoutClosureError,
    assert_checked_refs_cover,
    assert_source_inventory_evidence_refs_resolve,
    assert_workspace_evidence_bundle_matches_runs,
    normalize_ref_tuple,
)
from boardroom_os.contracts.evidence_obligation import RequiredArtifactType
from boardroom_os.contracts.types import AcceptanceRef, ContractId, EvidenceObligationRef, NonEmptyTextValue, SourceSurfaceRef
from boardroom_os.evidence.claim import EvidenceArtifactRef, EvidenceClaimRef, EvidenceClaimSourceKind
from boardroom_os.evidence.table import FinalEvidenceTableRef
from boardroom_os.evidence.verifier import ArtifactSha256, VerifiedArtifact, VerifiedEvidence, VerifiedEvidenceRef
from boardroom_os.execution.context_index import ProviderAttemptRef
from boardroom_os.execution.fallback import EvidencePurpose
from boardroom_os.execution.package import ExecutionPackageRef
from boardroom_os.execution.verification_run import (
    CommandOutputRef,
    EnvironmentProfileRef,
    RunnerRef,
    VerificationRun,
    VerificationRunRef,
    VerificationRunStatus,
    WorkspaceSnapshotRef,
)
from boardroom_os.graph.ticket import TicketId
from boardroom_os.workspace.assembler import PackageAssemblyRef
from boardroom_os.workspace.evidence_export import (
    EvidenceBundleArtifact,
    EvidenceBundleArtifactKind,
    EvidenceBundleArtifactPath,
    WorkspaceEvidenceBundle,
    WorkspaceEvidenceBundleRef,
)
from boardroom_os.workspace.manifest import WorkspaceManifestRef, WorkspacePath
from boardroom_os.workspace.run_manifest import RunManifestRef
from boardroom_os.workspace.source_inventory import (
    PackageCommitRef,
    SourceFilePath,
    SourceInventory,
    SourceInventoryEntry,
    SourceInventoryRef,
)

_NOW = datetime(2026, 5, 25, 9, 0, tzinfo=UTC)


def _verification_run(ref: str) -> VerificationRun:
    return VerificationRun(
        verification_run_id=VerificationRunRef(value=ref),
        execution_package_ref=ExecutionPackageRef(value="execution-package.closeout-closure"),
        ticket_ref=TicketId(value="ticket.closeout-closure"),
        command_id=ContractId(value="test-closeout-closure"),
        command=("python", "-m", "pytest"),
        cwd=".",
        exit_code=0,
        status=VerificationRunStatus.PASSED,
        stdout_ref=CommandOutputRef(value=f"command-output.{ref}.stdout"),
        stderr_ref=CommandOutputRef(value=f"command-output.{ref}.stderr"),
        duration_ms=0,
        started_at=_NOW,
        finished_at=_NOW,
        runner_ref=RunnerRef(value="runner.local"),
        environment_profile_ref=EnvironmentProfileRef(value="environment.local"),
        workspace_snapshot_ref=WorkspaceSnapshotRef(value="workspace-snapshot.closeout-closure"),
    )


def _verified_evidence(ref: str, run_refs: tuple[VerificationRunRef, ...] = ()) -> VerifiedEvidence:
    return VerifiedEvidence(
        verified_evidence_id=VerifiedEvidenceRef(value=ref),
        evidence_claim_ref=EvidenceClaimRef(value=f"evidence-claim.{ref}"),
        evidence_obligation_ref=EvidenceObligationRef(value="evidence-obligation.closeout-closure"),
        producer_attempt_ref=ProviderAttemptRef(value="provider-attempt.closeout-closure"),
        source_kind=EvidenceClaimSourceKind.VERIFICATION_RUN,
        source_ref=run_refs[0].value if run_refs else "verification-run.closeout-closure",
        expected_purpose=EvidencePurpose.IMPLEMENTATION,
        required_artifact_type=RequiredArtifactType(value="source"),
        acceptance_refs=(AcceptanceRef(value="AC-CLOSURE"),),
        source_surface_refs=(SourceSurfaceRef(value="source-surface.closeout-closure"),),
        verified_artifacts=(
            VerifiedArtifact(
                artifact_ref=EvidenceArtifactRef(value=f"artifact.{ref}"),
                sha256=ArtifactSha256(value="a" * 64),
                producer_attempt_ref=ProviderAttemptRef(value="provider-attempt.closeout-closure"),
                source_ref=run_refs[0].value if run_refs else "verification-run.closeout-closure",
                artifact_kind="source",
            ),
        ),
        verification_run_refs=run_refs,
        verified_at=_NOW,
    )


def _source_inventory(evidence_refs: tuple[VerifiedEvidenceRef, ...]) -> SourceInventory:
    return SourceInventory(
        source_inventory_id=SourceInventoryRef(value="source-inventory.closeout-closure"),
        package_assembly_ref=PackageAssemblyRef(value="package-assembly.closeout-closure"),
        package_contract_ref=ContractId(value="package-contract.closeout-closure"),
        package_root=WorkspacePath(value="10-project"),
        package_commit_ref=PackageCommitRef(value="package-commit.closeout-closure"),
        entries=(
            SourceInventoryEntry(
                path=SourceFilePath(value="app.py"),
                sha256=ArtifactSha256(value="b" * 64),
                source_surface_ref=SourceSurfaceRef(value="source-surface.closeout-closure"),
                producer_ticket_ref=TicketId(value="ticket.closeout-closure"),
                producer_attempt_ref=ProviderAttemptRef(value="provider-attempt.closeout-closure"),
                consumer_ticket_refs=(TicketId(value="ticket.closeout-closure"),),
                acceptance_refs=(AcceptanceRef(value="AC-CLOSURE"),),
                evidence_refs=evidence_refs,
            ),
        ),
    )


def _bundle(run_refs: tuple[VerificationRunRef, ...]) -> WorkspaceEvidenceBundle:
    related_refs = (
        NonEmptyTextValue(value="workspace-manifest.closeout-closure"),
        NonEmptyTextValue(value="source-inventory.closeout-closure"),
        *(NonEmptyTextValue(value=run_ref.value) for run_ref in run_refs),
    )
    artifacts = tuple(
        sorted(
            (
                EvidenceBundleArtifact(
                    relative_path=EvidenceBundleArtifactPath(value="20-evidence/source-inventory/source-inventory.json"),
                    artifact_kind=EvidenceBundleArtifactKind.SOURCE_INVENTORY,
                    source_ref=NonEmptyTextValue(value="source-inventory.closeout-closure"),
                    related_refs=related_refs,
                ),
                EvidenceBundleArtifact(
                    relative_path=EvidenceBundleArtifactPath(value="20-evidence/tests/verification-runs.json"),
                    artifact_kind=EvidenceBundleArtifactKind.VERIFICATION_RUNS,
                    source_ref=NonEmptyTextValue(value="verification-runs"),
                    related_refs=related_refs,
                ),
                EvidenceBundleArtifact(
                    relative_path=EvidenceBundleArtifactPath(value="20-evidence/tests/run-manifest.json"),
                    artifact_kind=EvidenceBundleArtifactKind.RUN_MANIFEST,
                    source_ref=NonEmptyTextValue(value="run-manifest.closeout-closure"),
                    related_refs=related_refs,
                ),
                EvidenceBundleArtifact(
                    relative_path=EvidenceBundleArtifactPath(value="20-evidence/closeout/final-evidence-table.json"),
                    artifact_kind=EvidenceBundleArtifactKind.FINAL_EVIDENCE_TABLE,
                    source_ref=NonEmptyTextValue(value="final-evidence-table.closeout-closure"),
                    related_refs=related_refs,
                ),
                EvidenceBundleArtifact(
                    relative_path=EvidenceBundleArtifactPath(value="20-evidence/closeout/evidence-bundle-manifest.json"),
                    artifact_kind=EvidenceBundleArtifactKind.BUNDLE_MANIFEST,
                    source_ref=NonEmptyTextValue(value="workspace-evidence-bundle.closeout-closure"),
                    related_refs=related_refs,
                ),
            ),
            key=lambda artifact: artifact.relative_path.value,
        )
    )
    return WorkspaceEvidenceBundle(
        workspace_evidence_bundle_id=WorkspaceEvidenceBundleRef(value="workspace-evidence-bundle.closeout-closure"),
        workspace_manifest_ref=WorkspaceManifestRef(value="workspace-manifest.closeout-closure"),
        package_assembly_ref=PackageAssemblyRef(value="package-assembly.closeout-closure"),
        package_contract_ref=ContractId(value="package-contract.closeout-closure"),
        source_inventory_ref=SourceInventoryRef(value="source-inventory.closeout-closure"),
        run_manifest_ref=RunManifestRef(value="run-manifest.closeout-closure"),
        final_evidence_table_ref=FinalEvidenceTableRef(value="final-evidence-table.closeout-closure"),
        verification_run_refs=tuple(sorted(run_refs, key=lambda ref: ref.value)),
        verified_evidence_refs=(VerifiedEvidenceRef(value="verified-evidence.closeout-closure"),),
        artifacts=artifacts,
        closeout_ready=True,
    )


def test_ref_normalization_returns_stable_deduped_tuple_for_value_objects_and_strings() -> None:
    assert normalize_ref_tuple(
        field_name="checked_refs",
        refs=(NonEmptyTextValue(value="b-ref"), "a-ref", "b-ref"),
    ) == ("b-ref", "a-ref")


def test_checked_refs_cover_accepts_value_objects_and_strings() -> None:
    assert_checked_refs_cover(
        domain_object_id="closeout-gate.closeout-closure",
        required_refs=(NonEmptyTextValue(value="source-inventory.closeout-closure"), "verified-evidence.closeout-closure"),
        observed_refs=("verified-evidence.closeout-closure", NonEmptyTextValue(value="source-inventory.closeout-closure")),
    )


def test_checked_refs_cover_fails_closed_with_diagnostics_for_missing_ref() -> None:
    with pytest.raises(CloseoutClosureError) as error:
        assert_checked_refs_cover(
            domain_object_id="closeout-gate.closeout-closure",
            required_refs=("source-inventory.closeout-closure", "verified-evidence.closeout-closure"),
            observed_refs=("source-inventory.closeout-closure",),
        )

    message = str(error.value)
    assert "domain_object_id=closeout-gate.closeout-closure" in message
    assert "source-inventory.closeout-closure" in message
    assert "verified-evidence.closeout-closure" in message
    assert "required_refs" in message
    assert "observed_refs" in message


def test_checked_refs_cover_rejects_empty_refs_instead_of_ignoring_them() -> None:
    with pytest.raises(CloseoutClosureError, match="required_refs must not contain empty refs"):
        assert_checked_refs_cover(
            domain_object_id="closeout-gate.closeout-closure",
            required_refs=("source-inventory.closeout-closure", ""),
            observed_refs=("source-inventory.closeout-closure",),
        )


def test_checked_refs_cover_rejects_whitespace_refs_instead_of_trimming_them() -> None:
    with pytest.raises(CloseoutClosureError, match="required_refs must not contain surrounding whitespace"):
        assert_checked_refs_cover(
            domain_object_id="closeout-gate.closeout-closure",
            required_refs=("source-inventory.closeout-closure", " verified-evidence.closeout-closure "),
            observed_refs=("source-inventory.closeout-closure",),
        )


def test_source_inventory_evidence_refs_resolve_when_all_refs_are_verified() -> None:
    verified = _verified_evidence("verified-evidence.closeout-closure")
    inventory = _source_inventory((verified.verified_evidence_id,))

    assert_source_inventory_evidence_refs_resolve(
        domain_object_id="source-inventory.closeout-closure",
        source_inventory=inventory,
        verified_evidence=(verified,),
    )


def test_source_inventory_evidence_refs_resolve_fails_closed_for_missing_verified_evidence() -> None:
    inventory = _source_inventory((VerifiedEvidenceRef(value="verified-evidence.missing"),))
    verified = _verified_evidence("verified-evidence.closeout-closure")

    with pytest.raises(CloseoutClosureError) as error:
        assert_source_inventory_evidence_refs_resolve(
            domain_object_id="source-inventory.closeout-closure",
            source_inventory=inventory,
            verified_evidence=(verified,),
        )

    message = str(error.value)
    assert "domain_object_id=source-inventory.closeout-closure" in message
    assert "verified-evidence.missing" in message
    assert "verified-evidence.closeout-closure" in message


def test_workspace_evidence_bundle_matches_runs_when_sets_are_equal() -> None:
    run = _verification_run("verification-run.closeout-closure")
    bundle = _bundle((run.verification_run_id,))

    assert_workspace_evidence_bundle_matches_runs(
        domain_object_id="workspace-evidence-bundle.closeout-closure",
        workspace_evidence_bundle=bundle,
        verification_runs=(run,),
    )


def test_workspace_evidence_bundle_matches_runs_fails_closed_for_set_mismatch() -> None:
    run = _verification_run("verification-run.closeout-closure")
    bundle = _bundle((VerificationRunRef(value="verification-run.other"),))

    with pytest.raises(CloseoutClosureError) as error:
        assert_workspace_evidence_bundle_matches_runs(
            domain_object_id="workspace-evidence-bundle.closeout-closure",
            workspace_evidence_bundle=bundle,
            verification_runs=(run,),
        )

    message = str(error.value)
    assert "domain_object_id=workspace-evidence-bundle.closeout-closure" in message
    assert "verification-run.other" in message
    assert "verification-run.closeout-closure" in message
    assert "expected_refs" in message
    assert "actual_refs" in message
