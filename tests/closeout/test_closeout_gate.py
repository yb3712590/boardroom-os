from __future__ import annotations

from datetime import UTC, datetime

from boardroom_os.checker.verdict import CheckerNote, CheckerVerdict, CheckerVerdictStatus, SourceDiffRef
from boardroom_os.closeout.gate import (
    CloseoutCommandEvidenceBinding,
    CloseoutGate,
    CloseoutGateBlockerCode,
    CloseoutGateInput,
    CloseoutGateVerdict,
    GitAuditReadiness,
    ProcessAuditReadiness,
    ReplayBundleReadiness,
)
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
from boardroom_os.evidence.fallback_registry import FallbackDecisionRecordRef
from boardroom_os.evidence.table import FinalEvidenceRow, FinalEvidenceStatus, FinalEvidenceTable
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
from boardroom_os.execution.work_product import WorkProductRef
from boardroom_os.graph.ticket import TicketId
from boardroom_os.workspace.assembler import PackageArtifact, PackageArtifactKind, PackageArtifactPath, assemble_package
from boardroom_os.workspace.evidence_export import build_workspace_evidence_bundle
from boardroom_os.workspace.manifest import WorkflowRef, WorkspacePath, build_workspace_manifest
from boardroom_os.workspace.run_manifest import build_run_manifest, validate_run_manifest_binding
from boardroom_os.workspace.source_inventory import (
    PackageCommitRef,
    SourceFilePath,
    SourceFileRecord,
    SourceLineageRecord,
    build_source_inventory,
)

_NOW = datetime(2026, 5, 24, 10, 30, tzinfo=UTC)
_FINAL_COMMIT_SHA = "0123456789abcdef0123456789abcdef01234567"
_SOURCE_INVENTORY_HASH = "123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef0"
_SUMMARY_HASH = "23456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef01"
_FALLBACK_DECISION_REF = "fallback-decision-record.closeout-gate"
_PROCESS_AUDIT_ARTIFACT_PATHS = (
    "30-audit/process-audit.md",
    "30-audit/timeline.json",
    "30-audit/decision-log.md",
    "30-audit/agent-context-index.json",
    "30-audit/ticket-graph.md",
    "30-audit/artifact-lineage.json",
    "30-audit/evidence-map.json",
    "30-audit/git-version-audit.md",
    "30-audit/closeout-summary.md",
    "30-audit/replay-bundle-report.json",
)


def _profile() -> MethodologyProfile:
    template_kind = MethodologyTemplateKind.HYBRID
    return MethodologyProfile(
        methodology_profile_id=ContractId(value="methodology-profile.closeout-gate-happy"),
        project_charter_ref=ContractId(value="project-charter.closeout-gate-happy"),
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
        owned_by=OwnerSeatRef(value="worker.closeout-gate-happy"),
        acceptance_refs=tuple(AcceptanceRef(value=ref) for ref in acceptance_refs),
        required_tests=(RequiredTestRef(value="pytest.closeout-gate-happy"),),
    )


def _command(command_id: str, command: tuple[str, ...]) -> PackageCommand:
    return PackageCommand(
        command_id=ContractId(value=command_id),
        label=command_id.replace("-", " ").title(),
        command=command,
        cwd=".",
    )


def _package_contract():
    profile = _profile()
    return create_package_contract(
        methodology_registry=MethodologyProfileRegistry.from_profiles(profile),
        package_contract_id=ContractId(value="package-contract.closeout-gate-happy"),
        project_charter_ref=ContractId(value="project-charter.closeout-gate-happy"),
        package_root="10-project",
        project_type=PackageProjectType.SOFTWARE,
        source_surfaces=(
            _surface("app-source", ("app.py",), ("AC-APP",)),
            _surface("app-tests", ("test_app.py",), ("AC-TEST",)),
            _surface("run-manifest", ("run-manifest.json",), ("AC-RUN",)),
            _surface("package-contract", ("package-contract.json",), ("AC-CONTRACT",)),
        ),
        run_commands=(_command("run-app", ("python", "app.py")),),
        test_commands=(_command("test-app", ("python", "-m", "pytest")),),
        integration_boundaries=(IntegrationBoundary(value="local-process"),),
        docs_required=True,
        closeout_required=True,
        methodology_profile_ref=profile.methodology_profile_id,
        docs_template_key=profile.docs_template_key,
        documentation_obligations=profile.documentation_obligations,
    )


def _verification_run() -> VerificationRun:
    return VerificationRun(
        verification_run_id=VerificationRunRef(value="verification-run.app"),
        execution_package_ref=ExecutionPackageRef(value="execution-package.app"),
        ticket_ref=TicketId(value="ticket.app"),
        command_id=ContractId(value="test-app"),
        command=("python", "-m", "pytest"),
        cwd=".",
        exit_code=0,
        status=VerificationRunStatus.PASSED,
        stdout_ref=CommandOutputRef(value="command-output.verification-run.app.stdout"),
        stderr_ref=CommandOutputRef(value="command-output.verification-run.app.stderr"),
        duration_ms=0,
        started_at=_NOW,
        finished_at=_NOW,
        runner_ref=RunnerRef(value="runner.local"),
        environment_profile_ref=EnvironmentProfileRef(value="environment.local"),
        workspace_snapshot_ref=WorkspaceSnapshotRef(value="workspace-snapshot.app"),
    )


def _verified_evidence(run_ref: VerificationRunRef) -> VerifiedEvidence:
    return VerifiedEvidence(
        verified_evidence_id=VerifiedEvidenceRef(value="verified-evidence.app"),
        evidence_claim_ref=EvidenceClaimRef(value="evidence-claim.verified-evidence.app"),
        evidence_obligation_ref=EvidenceObligationRef(value="evidence-obligation.app"),
        producer_attempt_ref=ProviderAttemptRef(value="provider-attempt.app"),
        source_kind=EvidenceClaimSourceKind.VERIFICATION_RUN,
        source_ref=run_ref.value,
        expected_purpose=EvidencePurpose.IMPLEMENTATION,
        required_artifact_type=RequiredArtifactType(value="source"),
        acceptance_refs=(AcceptanceRef(value="AC-APP"),),
        source_surface_refs=(SourceSurfaceRef(value="app-source"),),
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
        fallback_decision_record_ref=FallbackDecisionRecordRef(value=_FALLBACK_DECISION_REF),
        verified_at=_NOW,
    )


def _ready_input(*, checker_notes: bool = False) -> CloseoutGateInput:
    contract = _package_contract()
    workspace_manifest = build_workspace_manifest(
        workflow_ref=WorkflowRef(value="workflow.closeout-gate-happy"),
        workspace_root=WorkspacePath(value="workspaces/closeout-gate-happy"),
        package_contract=contract,
    )
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
                source_surface_refs=(contract.source_surfaces[0].source_surface_ref,),
                acceptance_refs=(AcceptanceRef(value="AC-APP"),),
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
                source_surface_refs=(contract.source_surfaces[0].source_surface_ref,),
                acceptance_refs=(AcceptanceRef(value="AC-APP"),),
            ),
        ),
    )
    run_manifest = build_run_manifest(workspace_manifest=workspace_manifest, package_contract=contract)
    verification_run = _verification_run()
    verified_evidence = _verified_evidence(verification_run.verification_run_id)
    final_evidence_table = FinalEvidenceTable(
        acceptance_contract_ref=ContractId(value="acceptance-contract.closeout-gate-happy"),
        generated_at=_NOW,
        rows=(
            FinalEvidenceRow(
                acceptance_ref=AcceptanceRef(value="AC-APP"),
                statement="App acceptance is satisfied by verified command evidence.",
                status=FinalEvidenceStatus.SATISFIED,
                verified_evidence_refs=(verified_evidence.verified_evidence_id,),
            ),
        ),
    )
    source_inventory = build_source_inventory(
        package_assembly=package_assembly,
        package_contract=contract,
        package_commit_ref=PackageCommitRef(value=f"package-commit.{_FINAL_COMMIT_SHA}"),
        source_files=(
            SourceFileRecord(path=SourceFilePath(value="app.py"), sha256=ArtifactSha256(value="e" * 64)),
            SourceFileRecord(path=SourceFilePath(value="test_app.py"), sha256=ArtifactSha256(value="f" * 64)),
            SourceFileRecord(path=SourceFilePath(value="docs/architecture.md"), sha256=ArtifactSha256(value="1" * 64)),
        ),
        lineage_records=(
            SourceLineageRecord(
                path=SourceFilePath(value="app.py"),
                source_surface_ref=contract.source_surfaces[0].source_surface_ref,
                producer_ticket_ref=TicketId(value="ticket.app"),
                producer_attempt_ref=ProviderAttemptRef(value="provider-attempt.app"),
                acceptance_refs=(AcceptanceRef(value="AC-APP"),),
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
                source_surface_ref=contract.source_surfaces[0].source_surface_ref,
                producer_ticket_ref=TicketId(value="ticket.app"),
                producer_attempt_ref=ProviderAttemptRef(value="provider-attempt.app"),
                acceptance_refs=(AcceptanceRef(value="AC-APP"),),
                evidence_refs=(verified_evidence.verified_evidence_id,),
            ),
        ),
    )
    workspace_evidence_bundle = build_workspace_evidence_bundle(
        workspace_manifest=workspace_manifest,
        package_assembly=package_assembly,
        source_inventory=source_inventory,
        run_manifest=run_manifest,
        verification_runs=(verification_run,),
        verified_evidence=(verified_evidence,),
        final_evidence_table=final_evidence_table,
    )
    checker_verdict = CheckerVerdict(
        ticket_ref=TicketId(value="ticket.app"),
        work_product_ref=WorkProductRef(value="work-product.app"),
        source_diff_ref=SourceDiffRef(value="source-diff.app"),
        acceptance_contract_ref=final_evidence_table.acceptance_contract_ref,
        final_evidence_table_ref=final_evidence_table.final_evidence_table_id,
        status=(
            CheckerVerdictStatus.APPROVED_WITH_NON_BLOCKING_NOTES
            if checker_notes
            else CheckerVerdictStatus.APPROVED
        ),
        notes=(CheckerNote(message="Non-blocking note.", related_ref="verified-evidence.app"),)
        if checker_notes
        else (),
        checked_at=_NOW,
    )
    run_manifest_binding = validate_run_manifest_binding(
        run_manifest=run_manifest,
        package_contract=contract,
        command_id=ContractId(value="test-app"),
    )
    return CloseoutGateInput(
        package_contract=contract,
        source_inventory=source_inventory,
        run_manifest=run_manifest,
        workspace_evidence_bundle=workspace_evidence_bundle,
        final_evidence_table=final_evidence_table,
        checker_verdict=checker_verdict,
        verification_runs=(verification_run,),
        verified_evidence=(verified_evidence,),
        provider_attempt_refs=(ProviderAttemptRef(value="provider-attempt.app"),),
        final_command_bindings=(
            CloseoutCommandEvidenceBinding(
                verification_run_ref=verification_run.verification_run_id,
                run_manifest_ref=run_manifest_binding.run_manifest_ref,
                package_contract_ref=run_manifest_binding.package_contract_ref,
                command_id=run_manifest_binding.command_id,
                binding_kind=run_manifest_binding.kind,
            ),
        ),
        replay_readiness=ReplayBundleReadiness(
            replay_passed=True,
            summary_hash=_SUMMARY_HASH,
            event_range="events.0001-0009",
            projection_versions=("completion-gate.v1", "closeout-gate.v1"),
            hash_chain_verified=True,
        ),
        git_audit_readiness=GitAuditReadiness(
            git_clean=True,
            final_commit_sha=_FINAL_COMMIT_SHA,
            source_inventory_hash=_SOURCE_INVENTORY_HASH,
            source_inventory_hash_matches=True,
            final_command_evidence_at_final_commit=True,
        ),
        process_audit_readiness=ProcessAuditReadiness(
            artifact_paths=_PROCESS_AUDIT_ARTIFACT_PATHS,
            all_artifacts_present=True,
            timeline_key_events_present=True,
            agent_context_index_complete=True,
            artifact_lineage_complete=True,
            evidence_map_consistent_with_final_table=True,
        ),
    )


def test_closeout_gate_passes_when_all_closeout_inputs_are_ready() -> None:
    gate_input = _ready_input()

    result = CloseoutGate().evaluate(gate_input)

    assert result.verdict == CloseoutGateVerdict.PASSED
    assert result.blockers == ()
    assert gate_input.source_inventory.source_inventory_id.value in result.checked_refs
    assert gate_input.final_evidence_table.final_evidence_table_id.value in result.checked_refs
    assert gate_input.workspace_evidence_bundle.workspace_evidence_bundle_id.value in result.checked_refs
    assert gate_input.run_manifest.run_manifest_id.value in result.checked_refs
    assert gate_input.checker_verdict.checker_verdict_id.value in result.checked_refs
    assert _SUMMARY_HASH in result.checked_refs
    assert _FINAL_COMMIT_SHA in result.checked_refs
    assert _SOURCE_INVENTORY_HASH in result.checked_refs
    assert _FALLBACK_DECISION_REF in result.checked_refs
    for artifact_path in _PROCESS_AUDIT_ARTIFACT_PATHS:
        assert artifact_path in result.checked_refs


def test_closeout_gate_allows_checker_non_blocking_notes() -> None:
    gate_input = _ready_input(checker_notes=True)

    result = CloseoutGate().evaluate(gate_input)

    assert result.verdict == CloseoutGateVerdict.PASSED
    assert result.blockers == ()


def test_closeout_gate_blocked_result_remains_auditable() -> None:
    gate_input = _ready_input()
    blocked_input = gate_input.model_copy(
        update={
            "replay_readiness": gate_input.replay_readiness.model_copy(update={"replay_passed": False})
        }
    )

    result = CloseoutGate().evaluate(blocked_input)

    assert result.verdict == CloseoutGateVerdict.BLOCKED
    assert any(blocker.code is CloseoutGateBlockerCode.REPLAY_NOT_READY for blocker in result.blockers)
    assert _SUMMARY_HASH in result.checked_refs
    assert _FINAL_COMMIT_SHA in result.checked_refs
    assert _FALLBACK_DECISION_REF in result.checked_refs
