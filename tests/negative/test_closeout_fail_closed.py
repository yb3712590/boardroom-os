from __future__ import annotations

import importlib
from datetime import UTC, datetime

import pytest

from boardroom_os.checker.verdict import (
    CheckerBlockerCode,
    CheckerVerdict,
    CheckerVerdictBlocker,
    CheckerVerdictStatus,
    SourceDiffRef,
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
from boardroom_os.contracts.package import (
    IntegrationBoundary,
    PackageCommand,
    PackageProjectType,
    create_package_contract,
)
from boardroom_os.contracts.source_surface import OwnerSeatRef, RequiredTestRef, SourceSurface
from boardroom_os.contracts.types import AcceptanceRef, ContractId, EvidenceObligationRef, SourceSurfaceRef
from boardroom_os.evidence.claim import EvidenceArtifactRef, EvidenceClaimRef, EvidenceClaimSourceKind
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
    SourceInventory,
    SourceLineageRecord,
    build_source_inventory,
)

_NOW = datetime(2026, 5, 24, 10, 0, tzinfo=UTC)
_VALID_SHA256 = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
_FINAL_COMMIT_SHA = "123456789abcdef0123456789abcdef012345678"
_SOURCE_INVENTORY_HASH = "23456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef01"

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


def _gate_module():
    return importlib.import_module("boardroom_os.closeout.gate")


def _profile() -> MethodologyProfile:
    template_kind = MethodologyTemplateKind.HYBRID
    return MethodologyProfile(
        methodology_profile_id=ContractId(value="methodology-profile.closeout-gate"),
        project_charter_ref=ContractId(value="project-charter.closeout-gate"),
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
        owned_by=OwnerSeatRef(value="worker.closeout-gate"),
        acceptance_refs=tuple(AcceptanceRef(value=ref) for ref in acceptance_refs),
        required_tests=(RequiredTestRef(value="pytest.closeout-gate"),),
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
        package_contract_id=ContractId(value="package-contract.closeout-gate"),
        project_charter_ref=ContractId(value="project-charter.closeout-gate"),
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


def _verification_run(
    ref: str = "verification-run.app",
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
    ref: str = "verified-evidence.app",
    *,
    run_ref: VerificationRunRef,
    producer_attempt_ref: str = "provider-attempt.app",
) -> VerifiedEvidence:
    return VerifiedEvidence(
        verified_evidence_id=VerifiedEvidenceRef(value=ref),
        evidence_claim_ref=EvidenceClaimRef(value=f"evidence-claim.{ref}"),
        evidence_obligation_ref=EvidenceObligationRef(value="evidence-obligation.app"),
        producer_attempt_ref=ProviderAttemptRef(value=producer_attempt_ref),
        source_kind=EvidenceClaimSourceKind.VERIFICATION_RUN,
        source_ref=run_ref.value,
        expected_purpose=EvidencePurpose.IMPLEMENTATION,
        required_artifact_type=RequiredArtifactType(value="source"),
        acceptance_refs=(AcceptanceRef(value="AC-APP"),),
        source_surface_refs=(SourceSurfaceRef(value="app-source"),),
        verified_artifacts=(
            VerifiedArtifact(
                artifact_ref=EvidenceArtifactRef(value=f"artifact.{ref}"),
                sha256=ArtifactSha256(value=_VALID_SHA256),
                producer_attempt_ref=ProviderAttemptRef(value=producer_attempt_ref),
                source_ref=run_ref.value,
                artifact_kind="source",
            ),
        ),
        verification_run_refs=(run_ref,),
        verified_at=_NOW,
    )


def _final_table(*, evidence_ref: VerifiedEvidenceRef) -> FinalEvidenceTable:
    return FinalEvidenceTable(
        acceptance_contract_ref=ContractId(value="acceptance-contract.closeout-gate"),
        generated_at=_NOW,
        rows=(
            FinalEvidenceRow(
                acceptance_ref=AcceptanceRef(value="AC-APP"),
                statement="App acceptance is satisfied by verified command evidence.",
                status=FinalEvidenceStatus.SATISFIED,
                verified_evidence_refs=(evidence_ref,),
            ),
        ),
    )


def _checker_blocker() -> CheckerVerdictBlocker:
    return CheckerVerdictBlocker(
        code=CheckerBlockerCode.CHECKER_BLOCKER,
        message="Checker found an unresolved blocker.",
        acceptance_ref=AcceptanceRef(value="AC-APP"),
        related_ref="source-diff.app",
        source="checker",
    )


def _ready_input():
    gate = _gate_module()
    contract = _package_contract()
    workspace_manifest = build_workspace_manifest(
        workflow_ref=WorkflowRef(value="workflow.closeout-gate"),
        workspace_root=WorkspacePath(value="workspaces/closeout-gate"),
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
    verified_evidence = _verified_evidence(run_ref=verification_run.verification_run_id)
    final_evidence_table = _final_table(evidence_ref=verified_evidence.verified_evidence_id)
    source_inventory = build_source_inventory(
        package_assembly=package_assembly,
        package_contract=contract,
        package_commit_ref=PackageCommitRef(value=f"package-commit.{_FINAL_COMMIT_SHA}"),
        source_files=(
            SourceFileRecord(path=SourceFilePath(value="app.py"), sha256=ArtifactSha256(value="d" * 64)),
            SourceFileRecord(path=SourceFilePath(value="test_app.py"), sha256=ArtifactSha256(value="e" * 64)),
            SourceFileRecord(path=SourceFilePath(value="docs/architecture.md"), sha256=ArtifactSha256(value="f" * 64)),
        ),
        lineage_records=(
            SourceLineageRecord(
                path=SourceFilePath(value="app.py"),
                source_surface_ref=contract.source_surfaces[0].source_surface_ref,
                producer_ticket_ref=TicketId(value="ticket.app"),
                producer_attempt_ref=ProviderAttemptRef(value="provider-attempt.app"),
                consumer_ticket_refs=(TicketId(value="ticket.app"),),
                acceptance_refs=(AcceptanceRef(value="AC-APP"),),
                evidence_refs=(verified_evidence.verified_evidence_id,),
            ),
            SourceLineageRecord(
                path=SourceFilePath(value="test_app.py"),
                source_surface_ref=contract.source_surfaces[1].source_surface_ref,
                producer_ticket_ref=TicketId(value="ticket.app"),
                producer_attempt_ref=ProviderAttemptRef(value="provider-attempt.app"),
                consumer_ticket_refs=(TicketId(value="ticket.app"),),
                acceptance_refs=(AcceptanceRef(value="AC-TEST"),),
                evidence_refs=(verified_evidence.verified_evidence_id,),
            ),
            SourceLineageRecord(
                path=SourceFilePath(value="docs/architecture.md"),
                source_surface_ref=contract.source_surfaces[0].source_surface_ref,
                producer_ticket_ref=TicketId(value="ticket.app"),
                producer_attempt_ref=ProviderAttemptRef(value="provider-attempt.app"),
                consumer_ticket_refs=(TicketId(value="ticket.app"),),
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
        status=CheckerVerdictStatus.APPROVED,
        checked_at=_NOW,
    )
    run_manifest_binding = validate_run_manifest_binding(
        run_manifest=run_manifest,
        package_contract=contract,
        command_id=ContractId(value="test-app"),
    )
    command_binding = gate.CloseoutCommandEvidenceBinding(
        verification_run_ref=verification_run.verification_run_id,
        run_manifest_ref=run_manifest_binding.run_manifest_ref,
        package_contract_ref=run_manifest_binding.package_contract_ref,
        command_id=run_manifest_binding.command_id,
        binding_kind=run_manifest_binding.kind,
    )
    return gate.CloseoutGateInput(
        package_contract=contract,
        source_inventory=source_inventory,
        run_manifest=run_manifest,
        workspace_evidence_bundle=workspace_evidence_bundle,
        final_evidence_table=final_evidence_table,
        checker_verdict=checker_verdict,
        verification_runs=(verification_run,),
        verified_evidence=(verified_evidence,),
        provider_attempt_refs=(ProviderAttemptRef(value="provider-attempt.app"),),
        final_command_bindings=(command_binding,),
        replay_readiness=gate.ReplayBundleReadiness(
            replay_passed=True,
            summary_hash=_VALID_SHA256,
            event_range="events.0001-0009",
            projection_versions=("completion-gate.v1", "closeout-gate.v1"),
            hash_chain_verified=True,
            payload_sha256_verified=True,
            payload_manifest_ref="manifest.payload.closeout-gate",
            payload_manifest_hash="3456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef012",
        ),
        git_audit_readiness=gate.GitAuditReadiness(
            git_clean=True,
            final_commit_sha=_FINAL_COMMIT_SHA,
            source_inventory_hash=_SOURCE_INVENTORY_HASH,
            source_inventory_hash_matches=True,
            final_command_evidence_at_final_commit=True,
        ),
        process_audit_readiness=gate.ProcessAuditReadiness(
            artifact_paths=_PROCESS_AUDIT_ARTIFACT_PATHS,
            all_artifacts_present=True,
            timeline_key_events_present=True,
            agent_context_index_complete=True,
            artifact_lineage_complete=True,
            evidence_map_consistent_with_final_table=True,
        ),
    )


def _evaluate(gate_input):
    return _gate_module().CloseoutGate().evaluate(gate_input)


def _assert_blocked(result, *expected_codes) -> None:
    gate = _gate_module()
    assert result.verdict == gate.CloseoutGateVerdict.BLOCKED
    assert result.blockers
    assert {blocker.code for blocker in result.blockers} & set(expected_codes)


def test_closeout_gate_blocks_when_replay_readiness_is_missing() -> None:
    gate_input = _ready_input().model_copy(update={"replay_readiness": None})

    result = _evaluate(gate_input)

    _assert_blocked(result, _gate_module().CloseoutGateBlockerCode.REPLAY_NOT_READY)


@pytest.mark.parametrize(
    ("field_name", "value"),
    (
        ("replay_passed", False),
        ("hash_chain_verified", False),
    ),
)
def test_closeout_gate_blocks_when_replay_readiness_fails_core_checks(field_name: str, value: object) -> None:
    gate_input = _ready_input()
    replay_readiness = gate_input.replay_readiness.model_copy(update={field_name: value})

    result = _evaluate(gate_input.model_copy(update={"replay_readiness": replay_readiness}))

    _assert_blocked(result, _gate_module().CloseoutGateBlockerCode.REPLAY_NOT_READY)


@pytest.mark.parametrize(
    "final_evidence_table",
    (
        lambda ready: FinalEvidenceTable(
            acceptance_contract_ref=ready.final_evidence_table.acceptance_contract_ref,
            generated_at=_NOW,
            rows=(
                FinalEvidenceRow(
                    acceptance_ref=AcceptanceRef(value="AC-APP"),
                    statement="App acceptance is still missing verified evidence.",
                    status=FinalEvidenceStatus.MISSING,
                    verified_evidence_refs=(),
                    missing_required_artifact_types=(RequiredArtifactType(value="source"),),
                ),
            ),
        ),
        lambda ready: ready.final_evidence_table.model_copy(update={"rows": (), "complete": False}),
    ),
)
def test_closeout_gate_blocks_when_final_evidence_table_is_incomplete_or_missing_acceptance_map(final_evidence_table) -> None:
    gate_input = _ready_input()
    mutated_table = final_evidence_table(gate_input)
    checker_verdict = gate_input.checker_verdict.model_copy(
        update={"final_evidence_table_ref": mutated_table.final_evidence_table_id}
    )

    result = _evaluate(
        gate_input.model_copy(
            update={
                "final_evidence_table": mutated_table,
                "checker_verdict": checker_verdict,
            }
        )
    )

    _assert_blocked(result, _gate_module().CloseoutGateBlockerCode.FINAL_EVIDENCE_INCOMPLETE)


def test_closeout_gate_blocks_when_checker_verdict_has_open_blocker() -> None:
    gate_input = _ready_input()
    checker_verdict = gate_input.checker_verdict.model_copy(
        update={
            "status": CheckerVerdictStatus.REWORK_REQUIRED,
            "blockers": (_checker_blocker(),),
        }
    )

    result = _evaluate(gate_input.model_copy(update={"checker_verdict": checker_verdict}))

    _assert_blocked(result, _gate_module().CloseoutGateBlockerCode.CHECKER_NOT_APPROVED)


@pytest.mark.parametrize(
    "gate_input",
    (
        lambda ready: ready.model_copy(update={"provider_attempt_refs": ()}),
        lambda ready: ready.model_copy(
            update={
                "verified_evidence": (
                    _verified_evidence(
                        ref=ready.verified_evidence[0].verified_evidence_id.value,
                        run_ref=ready.verification_runs[0].verification_run_id,
                        producer_attempt_ref="provider-attempt.other",
                    ),
                )
            }
        ),
    ),
)
def test_closeout_gate_blocks_when_provider_attempt_refs_are_missing_or_unclosed(gate_input) -> None:
    ready = _ready_input()

    result = _evaluate(gate_input(ready))

    _assert_blocked(result, _gate_module().CloseoutGateBlockerCode.PROVIDER_ATTEMPTS_MISSING)


@pytest.mark.parametrize(
    ("field_name", "value", "expected_code"),
    (
        ("git_clean", False, "GIT_AUDIT_NOT_READY"),
        ("source_inventory_hash_matches", False, "GIT_AUDIT_NOT_READY"),
        ("final_command_evidence_at_final_commit", False, "COMMAND_EVIDENCE_NOT_FINAL"),
    ),
)
def test_closeout_gate_blocks_when_git_audit_readiness_is_not_closed(
    field_name: str,
    value: object,
    expected_code: str,
) -> None:
    gate = _gate_module()
    gate_input = _ready_input()
    git_audit_readiness = gate_input.git_audit_readiness.model_copy(update={field_name: value})

    result = _evaluate(gate_input.model_copy(update={"git_audit_readiness": git_audit_readiness}))

    _assert_blocked(result, getattr(gate.CloseoutGateBlockerCode, expected_code))


@pytest.mark.parametrize(
    "mutator",
    (
        lambda ready: ready.model_copy(update={"final_command_bindings": ()}),
        lambda ready: ready.model_copy(
            update={
                "verification_runs": (
                    _verification_run(status=VerificationRunStatus.FAILED, exit_code=1),
                )
            }
        ),
        lambda ready: ready.model_copy(
            update={
                "verification_runs": (ready.verification_runs[0], ready.verification_runs[0]),
                "workspace_evidence_bundle": ready.workspace_evidence_bundle.model_copy(
                    update={
                        "verification_run_refs": (
                            ready.verification_runs[0].verification_run_id,
                            ready.verification_runs[0].verification_run_id,
                        )
                    }
                ),
            }
        ),
        lambda ready: ready.model_copy(
            update={
                "verification_runs": (),
                "workspace_evidence_bundle": ready.workspace_evidence_bundle.model_copy(
                    update={"verification_run_refs": ()}
                ),
            }
        ),
    ),
)
def test_closeout_gate_blocks_when_final_command_evidence_is_not_proven_by_run_manifest_binding(mutator) -> None:
    ready = _ready_input()

    result = _evaluate(mutator(ready))

    _assert_blocked(result, _gate_module().CloseoutGateBlockerCode.COMMAND_EVIDENCE_NOT_FINAL)


def test_closeout_gate_blocks_when_source_inventory_commit_does_not_match_git_audit() -> None:
    gate_input = _ready_input()
    source_inventory = gate_input.source_inventory.model_copy(
        update={"package_commit_ref": PackageCommitRef(value="package-commit.deadbeefdeadbeefdeadbeefdeadbeefdeadbeef")}
    )

    result = _evaluate(gate_input.model_copy(update={"source_inventory": source_inventory}))

    _assert_blocked(result, _gate_module().CloseoutGateBlockerCode.PACKAGE_COMMIT_MISMATCH)


def test_closeout_gate_blocks_when_verified_evidence_contains_orphan_not_in_final_table() -> None:
    gate_input = _ready_input()
    orphan = _verified_evidence(
        ref="verified-evidence.orphan",
        run_ref=gate_input.verification_runs[0].verification_run_id,
    )

    result = _evaluate(
        gate_input.model_copy(update={"verified_evidence": (*gate_input.verified_evidence, orphan)})
    )

    _assert_blocked(result, _gate_module().CloseoutGateBlockerCode.FINAL_EVIDENCE_INCOMPLETE)


@pytest.mark.parametrize(
    "workspace_evidence_bundle",
    (
        lambda ready: ready.workspace_evidence_bundle.model_copy(update={"closeout_ready": False}),
        lambda ready: ready.workspace_evidence_bundle.model_copy(
            update={"artifacts": ready.workspace_evidence_bundle.artifacts[:-1]}
        ),
    ),
)
def test_closeout_gate_blocks_when_workspace_evidence_bundle_is_not_closeout_ready(workspace_evidence_bundle) -> None:
    gate_input = _ready_input()

    result = _evaluate(
        gate_input.model_copy(update={"workspace_evidence_bundle": workspace_evidence_bundle(gate_input)})
    )

    _assert_blocked(result, _gate_module().CloseoutGateBlockerCode.WORKSPACE_EVIDENCE_BUNDLE_NOT_READY)


@pytest.mark.parametrize(
    "process_audit_readiness",
    (
        lambda ready: ready.process_audit_readiness.model_copy(
            update={
                "artifact_paths": ready.process_audit_readiness.artifact_paths[:-1],
                "all_artifacts_present": False,
            }
        ),
        lambda ready: ready.process_audit_readiness.model_copy(update={"timeline_key_events_present": False}),
        lambda ready: ready.process_audit_readiness.model_copy(update={"agent_context_index_complete": False}),
        lambda ready: ready.process_audit_readiness.model_copy(update={"artifact_lineage_complete": False}),
        lambda ready: ready.process_audit_readiness.model_copy(update={"evidence_map_consistent_with_final_table": False}),
    ),
)
def test_closeout_gate_blocks_when_process_audit_readiness_is_incomplete(process_audit_readiness) -> None:
    gate_input = _ready_input()

    result = _evaluate(
        gate_input.model_copy(update={"process_audit_readiness": process_audit_readiness(gate_input)})
    )

    _assert_blocked(result, _gate_module().CloseoutGateBlockerCode.PROCESS_AUDIT_NOT_READY)
