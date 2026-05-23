from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from boardroom_os.contracts.evidence_obligation import RequiredArtifactType
from boardroom_os.contracts.methodology import (
    DocumentationDensity,
    MethodologyProfile,
    MethodologyProfileRegistry,
    MethodologyTemplateKind,
    default_documentation_obligations_for,
    docs_template_key_for,
)
from boardroom_os.contracts.package import IntegrationBoundary, PackageCommand, PackageProjectType, create_package_contract
from boardroom_os.contracts.source_surface import OwnerSeatRef, RequiredTestRef, SourceSurface
from boardroom_os.contracts.types import AcceptanceRef, ContractId, EvidenceObligationRef, SourceSurfaceRef
from boardroom_os.evidence.claim import EvidenceArtifactRef, EvidenceClaimRef, EvidenceClaimSourceKind
from boardroom_os.evidence.table import (
    FinalEvidenceBlocker,
    FinalEvidenceBlockerCode,
    FinalEvidenceRow,
    FinalEvidenceStatus,
    FinalEvidenceTable,
)
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
from boardroom_os.workspace.assembler import PackageArtifact, PackageArtifactKind, PackageArtifactPath, assemble_package
from boardroom_os.workspace.manifest import WorkflowRef, WorkspacePath, build_workspace_manifest
from boardroom_os.workspace.run_manifest import build_run_manifest
from boardroom_os.workspace.source_inventory import (
    PackageCommitRef,
    SourceFilePath,
    SourceFileRecord,
    SourceInventory,
    SourceLineageRecord,
    build_source_inventory,
)

_VERIFY_ERRORS = (ValueError, ValidationError)
_NOW = datetime(2026, 5, 23, tzinfo=UTC)


def _profile() -> MethodologyProfile:
    template_kind = MethodologyTemplateKind.HYBRID
    return MethodologyProfile(
        methodology_profile_id=ContractId(value="methodology-profile.workspace-evidence-export"),
        project_charter_ref=ContractId(value="project-charter.workspace-evidence-export"),
        template_kind=template_kind,
        documentation_density=DocumentationDensity.STANDARD,
        docs_template_key=docs_template_key_for(template_kind),
        documentation_obligations=default_documentation_obligations_for(template_kind),
    )


def _surface(surface_ref: str, paths: tuple[str, ...], acceptance_refs: tuple[str, ...]) -> SourceSurface:
    return SourceSurface(
        source_surface_ref=SourceSurfaceRef(value=surface_ref),
        name=surface_ref.replace("-", " ").title(),
        paths=paths,
        owned_by=OwnerSeatRef(value="worker.workspace-evidence-export"),
        acceptance_refs=tuple(AcceptanceRef(value=ref) for ref in acceptance_refs),
        required_tests=(RequiredTestRef(value="pytest.workspace-evidence-export"),),
    )


def _command(command_id: str) -> PackageCommand:
    return PackageCommand(
        command_id=ContractId(value=command_id),
        label=command_id.replace("-", " ").title(),
        command=("python", "-m", "pytest"),
        cwd=".",
    )


def _package_contract():
    profile = _profile()
    return create_package_contract(
        methodology_registry=MethodologyProfileRegistry.from_profiles(profile),
        package_contract_id=ContractId(value="package-contract.workspace-evidence-export"),
        project_charter_ref=ContractId(value="project-charter.workspace-evidence-export"),
        package_root="10-project",
        project_type=PackageProjectType.SOFTWARE,
        source_surfaces=(
            _surface("app-source", ("app.py",), ("AC-APP",)),
            _surface("app-tests", ("test_app.py",), ("AC-TEST",)),
            _surface("run-manifest", ("run-manifest.json",), ("AC-RUN",)),
            _surface("package-contract", ("package-contract.json",), ("AC-CONTRACT",)),
        ),
        run_commands=(_command("run-app"),),
        test_commands=(_command("test-app"),),
        integration_boundaries=(IntegrationBoundary(value="local-process"),),
        docs_required=True,
        closeout_required=True,
        methodology_profile_ref=profile.methodology_profile_id,
        docs_template_key=profile.docs_template_key,
        documentation_obligations=profile.documentation_obligations,
    )


def _facts() -> dict[str, object]:
    contract = _package_contract()
    workspace_manifest = build_workspace_manifest(
        workflow_ref=WorkflowRef(value="workflow.workspace-evidence-export"),
        workspace_root=WorkspacePath(value="workspaces/workspace-evidence-export"),
        package_contract=contract,
    )
    app_surface = contract.source_surfaces[0].source_surface_ref
    acceptance_ref = AcceptanceRef(value="AC-APP")
    package_assembly = assemble_package(
        workspace_manifest=workspace_manifest,
        package_contract=contract,
        artifacts=(
            PackageArtifact(relative_path=PackageArtifactPath(value="README.md"), artifact_kind=PackageArtifactKind.README),
            PackageArtifact(relative_path=PackageArtifactPath(value="AGENTS.md"), artifact_kind=PackageArtifactKind.AGENTS),
            PackageArtifact(
                relative_path=PackageArtifactPath(value="package-contract.json"),
                artifact_kind=PackageArtifactKind.PACKAGE_CONTRACT,
                source_surface_refs=(contract.source_surfaces[3].source_surface_ref,),
                acceptance_refs=(AcceptanceRef(value="AC-CONTRACT"),),
            ),
            PackageArtifact(
                relative_path=PackageArtifactPath(value="run-manifest.json"),
                artifact_kind=PackageArtifactKind.RUN_MANIFEST,
                source_surface_refs=(contract.source_surfaces[2].source_surface_ref,),
                acceptance_refs=(AcceptanceRef(value="AC-RUN"),),
            ),
            PackageArtifact(
                relative_path=PackageArtifactPath(value="app.py"),
                artifact_kind=PackageArtifactKind.SOURCE,
                source_surface_refs=(app_surface,),
                acceptance_refs=(acceptance_ref,),
            ),
            PackageArtifact(
                relative_path=PackageArtifactPath(value="test_app.py"),
                artifact_kind=PackageArtifactKind.TEST,
                source_surface_refs=(contract.source_surfaces[1].source_surface_ref,),
                acceptance_refs=(AcceptanceRef(value="AC-TEST"),),
            ),
            PackageArtifact(
                relative_path=PackageArtifactPath(value="docs/architecture.md"),
                artifact_kind=PackageArtifactKind.DOC,
                source_surface_refs=(app_surface,),
                acceptance_refs=(acceptance_ref,),
            ),
        ),
    )
    run_manifest = build_run_manifest(workspace_manifest=workspace_manifest, package_contract=contract)
    verification_run = _verification_run("verification-run.app")
    verified_evidence = _verified_evidence("verified-evidence.app", verification_run.verification_run_id, acceptance_ref, app_surface)
    source_inventory = build_source_inventory(
        package_assembly=package_assembly,
        package_contract=contract,
        package_commit_ref=PackageCommitRef(value="package-commit.workspace-evidence-export"),
        source_files=(
            SourceFileRecord(path=SourceFilePath(value="app.py"), sha256=ArtifactSha256(value="a" * 64)),
            SourceFileRecord(path=SourceFilePath(value="test_app.py"), sha256=ArtifactSha256(value="b" * 64)),
            SourceFileRecord(path=SourceFilePath(value="docs/architecture.md"), sha256=ArtifactSha256(value="c" * 64)),
        ),
        lineage_records=(
            SourceLineageRecord(
                path=SourceFilePath(value="app.py"),
                source_surface_ref=app_surface,
                producer_ticket_ref=TicketId(value="ticket.app"),
                producer_attempt_ref=ProviderAttemptRef(value="provider-attempt.app"),
                acceptance_refs=(acceptance_ref,),
                evidence_refs=(verified_evidence.verified_evidence_id,),
            ),
            SourceLineageRecord(
                path=SourceFilePath(value="test_app.py"),
                source_surface_ref=contract.source_surfaces[1].source_surface_ref,
                producer_ticket_ref=TicketId(value="ticket.app"),
                producer_attempt_ref=ProviderAttemptRef(value="provider-attempt.app"),
                acceptance_refs=(AcceptanceRef(value="AC-TEST"),),
                evidence_refs=(verified_evidence.verified_evidence_id,),
            ),
            SourceLineageRecord(
                path=SourceFilePath(value="docs/architecture.md"),
                source_surface_ref=app_surface,
                producer_ticket_ref=TicketId(value="ticket.app"),
                producer_attempt_ref=ProviderAttemptRef(value="provider-attempt.app"),
                acceptance_refs=(acceptance_ref,),
                evidence_refs=(verified_evidence.verified_evidence_id,),
            ),
        ),
    )
    final_evidence_table = _final_table(
        rows=(
            FinalEvidenceRow(
                acceptance_ref=acceptance_ref,
                statement="App acceptance is satisfied by verified command evidence.",
                status=FinalEvidenceStatus.SATISFIED,
                verified_evidence_refs=(verified_evidence.verified_evidence_id,),
            ),
        ),
    )
    return {
        "workspace_manifest": workspace_manifest,
        "package_assembly": package_assembly,
        "source_inventory": source_inventory,
        "run_manifest": run_manifest,
        "verification_runs": (verification_run,),
        "verified_evidence": (verified_evidence,),
        "final_evidence_table": final_evidence_table,
    }


def _verification_run(
    ref: str,
    *,
    status: VerificationRunStatus = VerificationRunStatus.PASSED,
    exit_code: int = 0,
) -> VerificationRun:
    return VerificationRun(
        verification_run_id=VerificationRunRef(value=ref),
        execution_package_ref=ExecutionPackageRef(value="execution-package.app"),
        ticket_ref=TicketId(value="ticket.app"),
        command_id=ContractId(value="test-app"),
        command=("python", "-m", "pytest"),
        cwd=".",
        exit_code=exit_code,
        status=status,
        stdout_ref=CommandOutputRef(value=f"command-output.{ref}.stdout"),
        stderr_ref=CommandOutputRef(value=f"command-output.{ref}.stderr"),
        duration_ms=0,
        started_at=_NOW,
        finished_at=_NOW,
        runner_ref=RunnerRef(value="runner.local"),
        environment_profile_ref=EnvironmentProfileRef(value="environment.local"),
        workspace_snapshot_ref=WorkspaceSnapshotRef(value="workspace-snapshot.app"),
    )


def _verified_evidence(
    ref: str,
    run_ref: VerificationRunRef,
    acceptance_ref: AcceptanceRef,
    source_surface_ref: SourceSurfaceRef,
) -> VerifiedEvidence:
    return VerifiedEvidence(
        verified_evidence_id=VerifiedEvidenceRef(value=ref),
        evidence_claim_ref=EvidenceClaimRef(value=f"evidence-claim.{ref}"),
        evidence_obligation_ref=EvidenceObligationRef(value="evidence-obligation.app"),
        producer_attempt_ref=ProviderAttemptRef(value="provider-attempt.app"),
        source_kind=EvidenceClaimSourceKind.VERIFICATION_RUN,
        source_ref=run_ref.value,
        expected_purpose=EvidencePurpose.IMPLEMENTATION,
        required_artifact_type=RequiredArtifactType(value="source"),
        acceptance_refs=(acceptance_ref,),
        source_surface_refs=(source_surface_ref,),
        verified_artifacts=(
            VerifiedArtifact(
                artifact_ref=EvidenceArtifactRef(value="artifact.app"),
                sha256=ArtifactSha256(value="d" * 64),
                producer_attempt_ref=ProviderAttemptRef(value="provider-attempt.app"),
                source_ref=run_ref.value,
                artifact_kind="source",
            ),
        ),
        verification_run_refs=(run_ref,),
        verified_at=_NOW,
    )


def _final_table(*, rows: tuple[FinalEvidenceRow, ...], complete: bool | None = None) -> FinalEvidenceTable:
    return FinalEvidenceTable(
        acceptance_contract_ref=ContractId(value="acceptance-contract.workspace-evidence-export"),
        generated_at=_NOW,
        rows=rows,
        complete=complete,
    )


def _failed_blocker() -> FinalEvidenceBlocker:
    return FinalEvidenceBlocker(
        code=FinalEvidenceBlockerCode.FAILED_EVIDENCE,
        message="Evidence failed.",
        acceptance_ref=AcceptanceRef(value="AC-APP"),
        related_ref="verified-evidence.app",
        source="workspace-evidence-export-test",
    )


def _source_inventory_with_ref(facts: dict[str, object], evidence_ref: VerifiedEvidenceRef) -> SourceInventory:
    source_inventory = facts["source_inventory"]
    assert isinstance(source_inventory, SourceInventory)
    entries = tuple(
        entry.model_copy(update={"evidence_refs": (evidence_ref,)})
        for entry in source_inventory.entries
    )
    return source_inventory.model_copy(update={"entries": entries})


def test_missing_final_evidence_row_blocks_export() -> None:
    from boardroom_os.workspace.evidence_export import build_workspace_evidence_bundle

    facts = _facts()
    facts["final_evidence_table"] = _final_table(
        rows=(
            FinalEvidenceRow(
                acceptance_ref=AcceptanceRef(value="AC-APP"),
                statement="Missing evidence should block closeout.",
                status=FinalEvidenceStatus.MISSING,
                verified_evidence_refs=(),
            ),
        )
    )

    with pytest.raises(_VERIFY_ERRORS, match="complete|satisfied"):
        build_workspace_evidence_bundle(**facts)


def test_failed_final_evidence_row_blocks_export() -> None:
    from boardroom_os.workspace.evidence_export import build_workspace_evidence_bundle

    facts = _facts()
    facts["final_evidence_table"] = _final_table(
        rows=(
            FinalEvidenceRow(
                acceptance_ref=AcceptanceRef(value="AC-APP"),
                statement="Failed evidence should block closeout.",
                status=FinalEvidenceStatus.FAILED,
                verified_evidence_refs=(facts["verified_evidence"][0].verified_evidence_id,),
                blockers=(_failed_blocker(),),
            ),
        )
    )

    with pytest.raises(_VERIFY_ERRORS, match="complete|satisfied"):
        build_workspace_evidence_bundle(**facts)


def test_final_evidence_table_complete_must_be_derived_from_rows() -> None:
    facts = _facts()
    row = facts["final_evidence_table"].rows[0]

    with pytest.raises(_VERIFY_ERRORS, match="complete must be derived"):
        _final_table(rows=(row,), complete=False)


def test_empty_source_inventory_blocks_at_model_layer() -> None:
    facts = _facts()
    source_inventory = facts["source_inventory"]
    assert isinstance(source_inventory, SourceInventory)
    data = source_inventory.model_dump()
    data["entries"] = []

    with pytest.raises(_VERIFY_ERRORS, match="entries"):
        SourceInventory(**data)


def test_source_inventory_entry_missing_lineage_blocks_at_model_layer() -> None:
    facts = _facts()
    source_inventory = facts["source_inventory"]
    assert isinstance(source_inventory, SourceInventory)
    data = source_inventory.entries[0].model_dump()
    data.pop("producer_attempt_ref")

    with pytest.raises(_VERIFY_ERRORS, match="producer_attempt_ref"):
        source_inventory.entries[0].__class__(**data)


def test_source_inventory_package_assembly_mismatch_blocks_export() -> None:
    from boardroom_os.workspace.evidence_export import build_workspace_evidence_bundle

    facts = _facts()
    source_inventory = facts["source_inventory"]
    assert isinstance(source_inventory, SourceInventory)
    facts["source_inventory"] = source_inventory.model_copy(
        update={"package_assembly_ref": source_inventory.package_assembly_ref.__class__(value="package-assembly.other")}
    )

    with pytest.raises(_VERIFY_ERRORS, match="package_assembly_ref"):
        build_workspace_evidence_bundle(**facts)


def test_verification_run_missing_stdout_or_stderr_fails_at_model_layer() -> None:
    data = _verification_run("verification-run.malformed").model_dump()
    data.pop("stdout_ref")

    with pytest.raises(ValidationError, match="stdout_ref"):
        VerificationRun(**data)


def test_failed_verification_run_blocks_export() -> None:
    from boardroom_os.workspace.evidence_export import build_workspace_evidence_bundle

    facts = _facts()
    facts["verification_runs"] = (_verification_run("verification-run.app", status=VerificationRunStatus.FAILED, exit_code=1),)

    with pytest.raises(_VERIFY_ERRORS, match="verification run.*passed"):
        build_workspace_evidence_bundle(**facts)


def test_duplicate_verification_run_id_blocks_export() -> None:
    from boardroom_os.workspace.evidence_export import build_workspace_evidence_bundle

    facts = _facts()
    facts["verification_runs"] = (facts["verification_runs"][0], facts["verification_runs"][0])

    with pytest.raises(_VERIFY_ERRORS, match="verification run.*unique"):
        build_workspace_evidence_bundle(**facts)


def test_run_manifest_workspace_mismatch_blocks_export() -> None:
    from boardroom_os.workspace.evidence_export import build_workspace_evidence_bundle

    facts = _facts()
    run_manifest = facts["run_manifest"]
    facts["run_manifest"] = run_manifest.model_copy(
        update={"workspace_manifest_ref": run_manifest.workspace_manifest_ref.__class__(value="workspace-manifest.other")}
    )

    with pytest.raises(_VERIFY_ERRORS, match="run manifest.*workspace"):
        build_workspace_evidence_bundle(**facts)


def test_source_inventory_evidence_not_in_final_table_blocks_export() -> None:
    from boardroom_os.workspace.evidence_export import build_workspace_evidence_bundle

    facts = _facts()
    facts["source_inventory"] = _source_inventory_with_ref(
        facts,
        VerifiedEvidenceRef(value="verified-evidence.not-in-table"),
    )

    with pytest.raises(_VERIFY_ERRORS, match="source inventory evidence refs.*final evidence table"):
        build_workspace_evidence_bundle(**facts)


def test_final_table_unknown_verified_evidence_ref_blocks_export() -> None:
    from boardroom_os.workspace.evidence_export import build_workspace_evidence_bundle

    facts = _facts()
    facts["verified_evidence"] = (
        _verified_evidence(
            "verified-evidence.other",
            facts["verification_runs"][0].verification_run_id,
            AcceptanceRef(value="AC-APP"),
            SourceSurfaceRef(value="app-source"),
        ),
    )

    with pytest.raises(_VERIFY_ERRORS, match="verified evidence refs.*resolve"):
        build_workspace_evidence_bundle(**facts)


def test_orphan_verification_run_blocks_export() -> None:
    from boardroom_os.workspace.evidence_export import build_workspace_evidence_bundle

    facts = _facts()
    facts["verification_runs"] = (*facts["verification_runs"], _verification_run("verification-run.orphan"))

    with pytest.raises(_VERIFY_ERRORS, match="orphan verification run"):
        build_workspace_evidence_bundle(**facts)


def test_evidence_bundle_artifact_path_rejects_non_evidence_locations() -> None:
    from boardroom_os.workspace.evidence_export import EvidenceBundleArtifactPath

    for path in (
        "10-project/evidence.json",
        "00-boardroom/evidence.json",
        "30-audit/evidence.json",
        "src/boardroom_os/evidence.json",
        "doc/evidence.json",
        "/20-evidence/tests/run.json",
        "20-evidence/../run.json",
        "20-evidence/tests/",
    ):
        with pytest.raises(_VERIFY_ERRORS):
            EvidenceBundleArtifactPath(value=path)


def test_workspace_evidence_bundle_rejects_forged_closeout_ready_without_artifacts() -> None:
    from boardroom_os.workspace.evidence_export import WorkspaceEvidenceBundle, WorkspaceEvidenceBundleRef

    facts = _facts()
    with pytest.raises(_VERIFY_ERRORS, match="artifact"):
        WorkspaceEvidenceBundle(
            workspace_evidence_bundle_id=WorkspaceEvidenceBundleRef(value="workspace-evidence-bundle.forged"),
            workspace_manifest_ref=facts["workspace_manifest"].workspace_manifest_id,
            package_assembly_ref=facts["package_assembly"].package_assembly_id,
            package_contract_ref=facts["workspace_manifest"].package_contract_ref,
            source_inventory_ref=facts["source_inventory"].source_inventory_id,
            run_manifest_ref=facts["run_manifest"].run_manifest_id,
            final_evidence_table_ref=facts["final_evidence_table"].final_evidence_table_id,
            verification_run_refs=(),
            verified_evidence_refs=(),
            artifacts=(),
            closeout_ready=True,
        )


def test_build_workspace_evidence_bundle_returns_closeout_ready_plan() -> None:
    from boardroom_os.workspace.evidence_export import EvidenceBundleArtifactKind, build_workspace_evidence_bundle

    facts = _facts()
    bundle = build_workspace_evidence_bundle(**facts)

    assert bundle.closeout_ready is True
    assert bundle.workspace_manifest_ref == facts["workspace_manifest"].workspace_manifest_id
    assert bundle.package_assembly_ref == facts["package_assembly"].package_assembly_id
    assert bundle.package_contract_ref == facts["workspace_manifest"].package_contract_ref
    assert bundle.source_inventory_ref == facts["source_inventory"].source_inventory_id
    assert bundle.run_manifest_ref == facts["run_manifest"].run_manifest_id
    assert bundle.final_evidence_table_ref == facts["final_evidence_table"].final_evidence_table_id
    assert bundle.verification_run_refs == (facts["verification_runs"][0].verification_run_id,)
    assert bundle.verified_evidence_refs == (facts["verified_evidence"][0].verified_evidence_id,)
    assert {artifact.artifact_kind for artifact in bundle.artifacts} == set(EvidenceBundleArtifactKind)
    assert tuple(artifact.relative_path.value for artifact in bundle.artifacts) == tuple(
        sorted(artifact.relative_path.value for artifact in bundle.artifacts)
    )
    assert all(artifact.relative_path.value.startswith("20-evidence/") for artifact in bundle.artifacts)
    assert {
        "20-evidence/source-inventory/source-inventory.json",
        "20-evidence/tests/verification-runs.json",
        "20-evidence/tests/run-manifest.json",
        "20-evidence/closeout/final-evidence-table.json",
        "20-evidence/closeout/evidence-bundle-manifest.json",
    } == {artifact.relative_path.value for artifact in bundle.artifacts}


def test_build_workspace_evidence_bundle_is_deterministic() -> None:
    from boardroom_os.workspace.evidence_export import build_workspace_evidence_bundle

    facts = _facts()
    first = build_workspace_evidence_bundle(**facts)
    second = build_workspace_evidence_bundle(**facts)

    assert first.workspace_evidence_bundle_id == second.workspace_evidence_bundle_id
    assert first.model_dump() == second.model_dump()
