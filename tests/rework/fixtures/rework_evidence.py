from __future__ import annotations

from datetime import UTC, datetime
from typing import NamedTuple

from boardroom_os.checker.verdict import CheckerVerdict, SourceDiffRef
from boardroom_os.closeout.gate import (
    CloseoutCommandEvidenceBinding,
    CloseoutGateInput,
    GitAuditReadiness,
    ProcessAuditReadiness,
    ReplayBundleReadiness,
)
from boardroom_os.contracts.acceptance import (
    AcceptanceCriterion,
    EvidenceRequirement,
    VerificationStrategy,
    create_acceptance_contract,
)
from boardroom_os.contracts.directive import BoardDirective, DirectiveRegistry
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
    PackageContract,
    PackageProjectType,
    create_package_contract,
)
from boardroom_os.contracts.project import ProjectCharterRegistry, create_project_charter
from boardroom_os.contracts.source_surface import OwnerSeatRef, RequiredTestRef, SourceSurface
from boardroom_os.contracts.types import (
    AcceptanceRef,
    ContractId,
    ContractStatus,
    EvidenceObligationRef,
    SourceSurfaceRef,
)
from boardroom_os.evidence.claim import EvidenceArtifactRef, EvidenceClaimRef, EvidenceClaimSourceKind
from boardroom_os.evidence.fallback_registry import FallbackDecisionRecordRef
from boardroom_os.evidence.service_run import ServiceReadinessUrl, ServiceRunEvidence
from boardroom_os.evidence.table import (
    EvidenceNamespaceRef,
    FinalEvidenceBlocker,
    FinalEvidenceBlockerCode,
    FinalEvidenceTable,
    FinalEvidenceTableRef,
)
from boardroom_os.evidence.verifier import (
    ArtifactSha256,
    VerifiedArtifact,
    VerifiedEvidence,
    VerifiedEvidenceRef,
    EvidenceVerificationResult,
)
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
from boardroom_os.execution.work_product import WorkProduct, WorkProductRef
from boardroom_os.graph.ticket import TicketId
from boardroom_os.rework.evidence import (
    ReworkCloseoutRecheckContext,
    ReworkEnvironmentUsage,
    ReworkEvidenceNamespace,
    ReworkEvidenceRecheckInput,
    build_rework_checker_verdict,
    build_rework_final_evidence_table,
    build_rework_source_inventory,
    rework_evidence_namespace_ref,
)
from boardroom_os.rework.model import (
    BlockerRef,
    ReworkAttempt,
    ReworkAttemptId,
    ReworkCycleId,
    ReworkPlanId,
    RunId,
)
from boardroom_os.workspace.assembler import (
    PackageArtifact,
    PackageArtifactKind,
    PackageArtifactPath,
    PackageAssembly,
    assemble_package,
)
from boardroom_os.workspace.manifest import WorkflowRef, WorkspacePath, build_workspace_manifest
from boardroom_os.workspace.run_manifest import (
    RunManifest,
    RunManifestBehaviorAssertion,
    RunManifestBehaviorAssertionKind,
    RunManifestBehaviorProbe,
    RunManifestBehaviorStep,
    RunManifestCommandKind,
    RunManifestEnvironmentBinding,
    RunManifestEnvironmentValueSource,
    RunManifestReadinessProbe,
    RunManifestServiceContract,
    build_run_manifest,
    validate_run_manifest_binding,
)
from boardroom_os.workspace.evidence_export import build_workspace_evidence_bundle
from boardroom_os.workspace.source_inventory import (
    PackageCommitRef,
    SourceFilePath,
    SourceFileRecord,
    SourceInventory,
    SourceInventoryRef,
    SourceLineageRecord,
)

NOW = datetime(2026, 6, 14, 9, 0, tzinfo=UTC)
RUN_ID = RunId(value="run-v2-100d")
CYCLE_ID = ReworkCycleId(value="rework-cycle.v2-100d")
ATTEMPT_ID = ReworkAttemptId(value="rework-attempt.v2-100d.1")
TICKET_REF = TicketId(value="ticket.v2-100d.backend")
EXECUTION_PACKAGE_REF = ExecutionPackageRef(value="execution-package.v2-100d.backend")
ACCEPTANCE_REF = AcceptanceRef(value="acceptance.book.add")
SOURCE_SURFACE_REF = SourceSurfaceRef(value="surface.backend.api")
TEST_SURFACE_REF = SourceSurfaceRef(value="surface.backend.tests")
RUN_MANIFEST_SURFACE_REF = SourceSurfaceRef(value="surface.run-manifest")
PACKAGE_CONTRACT_SURFACE_REF = SourceSurfaceRef(value="surface.package-contract")
EVIDENCE_OBLIGATION_REF = EvidenceObligationRef(value="evidence.book.add.api")
PACKAGE_CONTRACT_REF = ContractId(value="package.v2-100d")
ACCEPTANCE_CONTRACT_REF = ContractId(value="acceptance.v2-100d")
PROVIDER_ATTEMPT_REF = ProviderAttemptRef(value="provider-attempt.worker.rework.v2-100d.1")
TARGET_BLOCKER_REF = BlockerRef(value="final-evidence-blocker.failed.acceptance.book.add.probe")
FINAL_COMMIT_SHA = "0123456789abcdef0123456789abcdef01234567"
SOURCE_SHA = "a" * 64
TEST_SHA = "b" * 64
DOC_SHA = "d" * 64
SERVICE_BODY_SHA = "456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123"
SOURCE_INVENTORY_HASH = "56789abcdef0123456789abcdef0123456789abcdef0123456789abcdef01234"
SUMMARY_HASH = "6789abcdef0123456789abcdef0123456789abcdef0123456789abcdef012345"
PAYLOAD_HASH = "789abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456"
PROCESS_AUDIT_ARTIFACT_PATHS = (
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


def namespace() -> ReworkEvidenceNamespace:
    return ReworkEvidenceNamespace(
        run_id=RUN_ID,
        cycle_id=CYCLE_ID,
        rework_attempt_id=ATTEMPT_ID,
        graph_version=42,
        config_hash_refs=("config-hash.roles.v2-100d", "config-hash.runtime.v2-100d"),
    )


class FreshRecheckParts(NamedTuple):
    source_inventory: SourceInventory
    final_evidence_table: FinalEvidenceTable
    checker_verdict: CheckerVerdict
    old_source_inventory: SourceInventory
    old_final_evidence_table: FinalEvidenceTable
    old_checker_verdict: CheckerVerdict


def _methodology_profile() -> MethodologyProfile:
    template_kind = MethodologyTemplateKind.HYBRID
    return MethodologyProfile(
        methodology_profile_id=ContractId(value="methodology.v2-100d"),
        project_charter_ref=ContractId(value="project-charter.v2-100d"),
        template_kind=template_kind,
        documentation_density=DocumentationDensity.STANDARD,
        docs_template_key=docs_template_key_for(template_kind),
        documentation_obligations=default_documentation_obligations_for(template_kind),
    )


def active_acceptance_contract():
    directive = BoardDirective(
        board_directive_id=ContractId(value="directive.v2-100d"),
        source_type="natural_language",
        content_ref=ContractId(value="content.v2-100d"),
        received_at=NOW,
        requester_ref=ContractId(value="human-board"),
    )
    charter = create_project_charter(
        registry=DirectiveRegistry.from_directives(directive),
        project_charter_id=ContractId(value="project-charter.v2-100d"),
        board_directive_ref=directive.board_directive_id,
        project_goal="Recheck rework evidence with current facts only.",
        delivery_type="generated_project_package",
        non_goals=("Do not reuse stale closeout facts.",),
        constraints=("Every rework attempt must re-enter evidence gates.",),
        risks=("Old evidence could be reused across cycles.",),
        success_summary="Current rework attempt satisfies active acceptance.",
    )
    return create_acceptance_contract(
        registry=ProjectCharterRegistry.from_charters(charter),
        acceptance_contract_id=ACCEPTANCE_CONTRACT_REF,
        project_charter_ref=charter.project_charter_id,
        status=ContractStatus(value="active"),
        criteria=(
            AcceptanceCriterion(
                acceptance_ref=ACCEPTANCE_REF,
                statement="Book creation API accepts and returns a created book.",
                evidence_required=(
                    EvidenceRequirement(value="source"),
                    EvidenceRequirement(value="test"),
                    EvidenceRequirement(value="live_blackbox"),
                ),
                blocking=True,
                source_surface_refs=(SOURCE_SURFACE_REF, TEST_SURFACE_REF),
                verification_strategy=VerificationStrategy(value="pytest plus live API probe"),
            ),
        ),
    )


def _surface(ref: SourceSurfaceRef, paths: tuple[str, ...], acceptance_refs: tuple[AcceptanceRef, ...]) -> SourceSurface:
    return SourceSurface(
        source_surface_ref=ref,
        name=ref.value,
        paths=paths,
        owned_by=OwnerSeatRef(value="worker.v2-100d"),
        acceptance_refs=acceptance_refs,
        required_tests=(RequiredTestRef(value="pytest.v2-100d"),),
    )


def _command(command_id: str, command: tuple[str, ...]) -> PackageCommand:
    return PackageCommand(
        command_id=ContractId(value=command_id),
        label=command_id,
        command=command,
        cwd=".",
    )


def active_package_contract() -> PackageContract:
    profile = _methodology_profile()
    return create_package_contract(
        methodology_registry=MethodologyProfileRegistry.from_profiles(profile),
        package_contract_id=PACKAGE_CONTRACT_REF,
        project_charter_ref=ContractId(value="project-charter.v2-100d"),
        package_root="10-project",
        project_type=PackageProjectType.SOFTWARE,
        source_surfaces=(
            _surface(SOURCE_SURFACE_REF, ("app/main.py",), (ACCEPTANCE_REF,)),
            _surface(TEST_SURFACE_REF, ("tests/test_books.py",), (ACCEPTANCE_REF,)),
            _surface(RUN_MANIFEST_SURFACE_REF, ("run-manifest.json",), (ACCEPTANCE_REF,)),
            _surface(PACKAGE_CONTRACT_SURFACE_REF, ("package-contract.json",), (ACCEPTANCE_REF,)),
        ),
        run_commands=(_command("run-api", ("python", "-m", "app.main")),),
        test_commands=(_command("test-api", ("python", "-m", "pytest")),),
        integration_boundaries=(IntegrationBoundary(value="local-http"),),
        docs_required=True,
        closeout_required=True,
        methodology_profile_ref=profile.methodology_profile_id,
        docs_template_key=profile.docs_template_key,
        documentation_obligations=profile.documentation_obligations,
    )


def workspace_manifest():
    return build_workspace_manifest(
        workflow_ref=WorkflowRef(value=f"workflow.{RUN_ID.value}.{ATTEMPT_ID.value}"),
        workspace_root=WorkspacePath(value=f"workspaces/{RUN_ID.value}/{ATTEMPT_ID.value}"),
        package_contract=active_package_contract(),
    )


def package_assembly() -> PackageAssembly:
    contract = active_package_contract()
    manifest = workspace_manifest()
    return assemble_package(
        workspace_manifest=manifest,
        package_contract=contract,
        artifacts=(
            PackageArtifact(relative_path=PackageArtifactPath(value="README.md"), artifact_kind=PackageArtifactKind.README),
            PackageArtifact(relative_path=PackageArtifactPath(value="AGENTS.md"), artifact_kind=PackageArtifactKind.AGENTS),
            PackageArtifact(
                relative_path=PackageArtifactPath(value="package-contract.json"),
                artifact_kind=PackageArtifactKind.PACKAGE_CONTRACT,
                source_surface_refs=(PACKAGE_CONTRACT_SURFACE_REF,),
                acceptance_refs=(ACCEPTANCE_REF,),
            ),
            PackageArtifact(
                relative_path=PackageArtifactPath(value="run-manifest.json"),
                artifact_kind=PackageArtifactKind.RUN_MANIFEST,
                source_surface_refs=(RUN_MANIFEST_SURFACE_REF,),
                acceptance_refs=(ACCEPTANCE_REF,),
            ),
            PackageArtifact(
                relative_path=PackageArtifactPath(value="app/main.py"),
                artifact_kind=PackageArtifactKind.SOURCE,
                source_surface_refs=(SOURCE_SURFACE_REF,),
                acceptance_refs=(ACCEPTANCE_REF,),
            ),
            PackageArtifact(
                relative_path=PackageArtifactPath(value="tests/test_books.py"),
                artifact_kind=PackageArtifactKind.TEST,
                source_surface_refs=(TEST_SURFACE_REF,),
                acceptance_refs=(ACCEPTANCE_REF,),
            ),
            PackageArtifact(
                relative_path=PackageArtifactPath(value="docs/api.md"),
                artifact_kind=PackageArtifactKind.DOC,
                source_surface_refs=(SOURCE_SURFACE_REF,),
                acceptance_refs=(ACCEPTANCE_REF,),
            ),
        ),
    )


def source_files() -> tuple[SourceFileRecord, ...]:
    return (
        SourceFileRecord(path=SourceFilePath(value="app/main.py"), sha256=ArtifactSha256(value=SOURCE_SHA)),
        SourceFileRecord(path=SourceFilePath(value="tests/test_books.py"), sha256=ArtifactSha256(value=TEST_SHA)),
        SourceFileRecord(path=SourceFilePath(value="docs/api.md"), sha256=ArtifactSha256(value=DOC_SHA)),
    )


def verified_evidence(
    namespace_ref,
    *,
    suffix: str = "book.add.live",
    source_kind: EvidenceClaimSourceKind = EvidenceClaimSourceKind.LIVE_BLACKBOX,
    required_artifact_type: str = "live_blackbox",
) -> VerifiedEvidence:
    verified_id = f"verified-evidence.{namespace_ref.value}.{suffix}"
    return VerifiedEvidence(
        verified_evidence_id=VerifiedEvidenceRef(value=verified_id),
        evidence_claim_ref=EvidenceClaimRef(value=f"claim.{verified_id}"),
        evidence_obligation_ref=EVIDENCE_OBLIGATION_REF,
        producer_attempt_ref=PROVIDER_ATTEMPT_REF,
        source_kind=source_kind,
        source_ref=f"{source_kind.value}.{namespace_ref.value}.{suffix}",
        expected_purpose=EvidencePurpose.IMPLEMENTATION,
        required_artifact_type=RequiredArtifactType(value=required_artifact_type),
        acceptance_refs=(ACCEPTANCE_REF,),
        source_surface_refs=(SOURCE_SURFACE_REF, TEST_SURFACE_REF),
        verified_artifacts=(
            VerifiedArtifact(
                artifact_ref=EvidenceArtifactRef(value=f"artifact.{namespace_ref.value}.source"),
                sha256=ArtifactSha256(value=SOURCE_SHA),
                producer_attempt_ref=PROVIDER_ATTEMPT_REF,
                source_ref="app/main.py",
                artifact_kind="source",
            ),
            VerifiedArtifact(
                artifact_ref=EvidenceArtifactRef(value=f"artifact.{namespace_ref.value}.test"),
                sha256=ArtifactSha256(value=TEST_SHA),
                producer_attempt_ref=PROVIDER_ATTEMPT_REF,
                source_ref="tests/test_books.py",
                artifact_kind="test",
            ),
            VerifiedArtifact(
                artifact_ref=EvidenceArtifactRef(value=f"artifact.{namespace_ref.value}.live"),
                sha256=ArtifactSha256(value="c" * 64),
                producer_attempt_ref=PROVIDER_ATTEMPT_REF,
                source_ref=f"live-blackbox.{namespace_ref.value}.book.add",
                artifact_kind="live_blackbox",
            ),
        ),
        verification_run_refs=(VerificationRunRef(value=f"verification-run.{namespace_ref.value}.pytest"),),
        fallback_decision_record_ref=FallbackDecisionRecordRef(value=f"fallback-decision.{namespace_ref.value}.none"),
        verified_at=NOW,
    )


def evidence_results(namespace_ref=None) -> tuple[EvidenceVerificationResult, ...]:
    namespace_ref = namespace_ref or rework_evidence_namespace_ref(namespace())
    return (
        EvidenceVerificationResult(
            verified_evidence=verified_evidence(
                namespace_ref,
                suffix="book.add.source",
                source_kind=EvidenceClaimSourceKind.WORK_PRODUCT,
                required_artifact_type="source",
            )
        ),
        EvidenceVerificationResult(
            verified_evidence=verified_evidence(
                namespace_ref,
                suffix="book.add.test",
                source_kind=EvidenceClaimSourceKind.VERIFICATION_RUN,
                required_artifact_type="test",
            )
        ),
        EvidenceVerificationResult(
            verified_evidence=verified_evidence(
                namespace_ref,
                suffix="book.add.live",
                source_kind=EvidenceClaimSourceKind.LIVE_BLACKBOX,
                required_artifact_type="live_blackbox",
            )
        ),
    )


def evidence_results_without_live_probe(namespace_ref=None) -> tuple[EvidenceVerificationResult, ...]:
    namespace_ref = namespace_ref or rework_evidence_namespace_ref(namespace())
    return evidence_results(namespace_ref)[:2]


def source_lineage_records(namespace_ref=None) -> tuple[SourceLineageRecord, ...]:
    return source_lineage_records_for_results(
        evidence_results(namespace_ref or rework_evidence_namespace_ref(namespace()))
    )


def source_lineage_records_for_results(
    results: tuple[EvidenceVerificationResult, ...],
) -> tuple[SourceLineageRecord, ...]:
    evidence_refs = tuple(
        result.verified_evidence.verified_evidence_id
        for result in results
        if result.verified_evidence is not None
    )
    return (
        SourceLineageRecord(
            path=SourceFilePath(value="app/main.py"),
            source_surface_ref=SOURCE_SURFACE_REF,
            producer_ticket_ref=TICKET_REF,
            producer_attempt_ref=PROVIDER_ATTEMPT_REF,
            consumer_ticket_refs=(TICKET_REF,),
            acceptance_refs=(ACCEPTANCE_REF,),
            evidence_refs=evidence_refs,
        ),
        SourceLineageRecord(
            path=SourceFilePath(value="tests/test_books.py"),
            source_surface_ref=TEST_SURFACE_REF,
            producer_ticket_ref=TICKET_REF,
            producer_attempt_ref=PROVIDER_ATTEMPT_REF,
            consumer_ticket_refs=(TICKET_REF,),
            acceptance_refs=(ACCEPTANCE_REF,),
            evidence_refs=evidence_refs,
        ),
        SourceLineageRecord(
            path=SourceFilePath(value="docs/api.md"),
            source_surface_ref=SOURCE_SURFACE_REF,
            producer_ticket_ref=TICKET_REF,
            producer_attempt_ref=PROVIDER_ATTEMPT_REF,
            consumer_ticket_refs=(TICKET_REF,),
            acceptance_refs=(ACCEPTANCE_REF,),
            evidence_refs=evidence_refs,
        ),
    )


def rework_attempt() -> ReworkAttempt:
    return ReworkAttempt(
        rework_attempt_id=ATTEMPT_ID,
        cycle_id=CYCLE_ID,
        rework_plan_ref=ReworkPlanId(value="rework-plan.v2-100d"),
        ticket_ref=TICKET_REF,
        execution_package_ref=EXECUTION_PACKAGE_REF,
        actor_ref="worker.v2-100d",
        provider_attempt_refs=(PROVIDER_ATTEMPT_REF,),
        workspace_mutation_refs=("workspace-mutation.v2-100d.source",),
        command_evidence_refs=("verification-run.v2-100d.pytest", "service-run.v2-100d.api"),
        source_lineage_refs=("source-lineage.v2-100d.app", "source-lineage.v2-100d.tests"),
        run_manifest_ref=run_manifest_with_service_and_probe().run_manifest_id.value,
        submitted_at=NOW,
    )


def work_product() -> WorkProduct:
    return WorkProduct(
        work_product_id=WorkProductRef(value=f"work-product.{ATTEMPT_ID.value}"),
        execution_package_ref=EXECUTION_PACKAGE_REF,
        ticket_ref=TICKET_REF,
        producer_attempt_ref=PROVIDER_ATTEMPT_REF,
        artifact_refs=("artifact.app.main", "artifact.tests.books"),
        summary="Implemented the current rework attempt.",
        claim_refs=("claim.book.add",),
    )


def source_diff_ref() -> SourceDiffRef:
    return SourceDiffRef(value=f"source-diff.{ATTEMPT_ID.value}")


def run_manifest_with_service_and_probe() -> RunManifest:
    return build_run_manifest(
        workspace_manifest=workspace_manifest(),
        package_contract=active_package_contract(),
        service_contracts=(
            RunManifestServiceContract(
                command_id=ContractId(value="run-api"),
                role="backend-api",
                env_bindings=(
                    RunManifestEnvironmentBinding(name="HOST", value_source=RunManifestEnvironmentValueSource.RUNTIME_HOST),
                    RunManifestEnvironmentBinding(name="PORT", value_source=RunManifestEnvironmentValueSource.RUNTIME_PORT),
                    RunManifestEnvironmentBinding(name="LIBRARY_DB_PATH", value_source=RunManifestEnvironmentValueSource.TEMP_SQLITE_PATH),
                ),
                readiness_probe=RunManifestReadinessProbe(method="GET", path="/health", expect_status=200),
            ),
        ),
        behavioral_probes=(
            RunManifestBehaviorProbe(
                probe_id=ContractId(value="probe.book.add"),
                service_command_id=ContractId(value="run-api"),
                acceptance_refs=(ACCEPTANCE_REF,),
                steps=(
                    RunManifestBehaviorStep(
                        step_id="create-book",
                        method="POST",
                        path="/books",
                        json_body={"title": "Dune"},
                        expect_status=201,
                        assertions=(
                            RunManifestBehaviorAssertion(
                                kind=RunManifestBehaviorAssertionKind.FIELD_PRESENT,
                                target="$.book.id",
                            ),
                        ),
                    ),
                ),
            ),
        ),
    )


def old_run_manifest_with_service_and_probe() -> RunManifest:
    current = run_manifest_with_service_and_probe()
    return current.model_copy(
        update={"run_manifest_id": current.run_manifest_id.model_copy(update={"value": "run-manifest.old-run"})}
    )


def run_manifest_with_run_command_and_no_service_contracts() -> RunManifest:
    return run_manifest_with_service_and_probe().model_copy(update={"service_contracts": None})


def run_manifest_with_host_port_only() -> RunManifest:
    service = RunManifestServiceContract(
        command_id=ContractId(value="run-api"),
        role="backend-api",
        env_bindings=(
            RunManifestEnvironmentBinding(name="HOST", value_source=RunManifestEnvironmentValueSource.RUNTIME_HOST),
            RunManifestEnvironmentBinding(name="PORT", value_source=RunManifestEnvironmentValueSource.RUNTIME_PORT),
        ),
        readiness_probe=RunManifestReadinessProbe(method="GET", path="/health", expect_status=200),
    )
    return run_manifest_with_service_and_probe().model_copy(update={"service_contracts": (service,)})


def environment_usage_declared() -> tuple[ReworkEnvironmentUsage, ...]:
    return (ReworkEnvironmentUsage(source_ref="source-file.backend.app", env_names=("HOST", "PORT", "LIBRARY_DB_PATH")),)


def environment_usage_undeclared() -> tuple[ReworkEnvironmentUsage, ...]:
    return (ReworkEnvironmentUsage(source_ref="source-file.backend.app", env_names=("LIBRARY_DB_PATH",)),)


def failed_behavioral_probe_blocker() -> FinalEvidenceBlocker:
    return FinalEvidenceBlocker(
        blocker_id=TARGET_BLOCKER_REF,
        code=FinalEvidenceBlockerCode.FAILED_EVIDENCE,
        message="Behavioral probe failed.",
        acceptance_ref=ACCEPTANCE_REF,
        related_ref="probe.book.add",
        source="behavioral_probe",
    )


def rework_input_with_verified_evidence() -> ReworkEvidenceRecheckInput:
    ns = namespace()
    namespace_ref = rework_evidence_namespace_ref(ns)
    return ReworkEvidenceRecheckInput(
        attempt=rework_attempt(),
        namespace=ns,
        active_acceptance_contract=active_acceptance_contract(),
        active_package_contract=active_package_contract(),
        package_assembly=package_assembly(),
        package_commit_ref=PackageCommitRef(value=f"package-commit.{FINAL_COMMIT_SHA}"),
        source_files=source_files(),
        source_lineage_records=source_lineage_records(namespace_ref),
        evidence_verification_results=evidence_results(namespace_ref),
        failed_final_evidence_blockers=(),
        target_blocker_refs=(TARGET_BLOCKER_REF,),
        work_product=work_product(),
        source_diff_ref=source_diff_ref(),
        run_manifest=run_manifest_with_service_and_probe(),
        environment_usage=environment_usage_declared(),
        checked_at=NOW,
        closeout_context=None,
    )


def rework_input_with_behavioral_probe_failure() -> ReworkEvidenceRecheckInput:
    ns = namespace()
    namespace_ref = rework_evidence_namespace_ref(ns)
    results = evidence_results_without_live_probe(namespace_ref)
    return rework_input_with_verified_evidence().model_copy(
        update={
            "evidence_verification_results": results,
            "source_lineage_records": source_lineage_records_for_results(results),
            "failed_final_evidence_blockers": (failed_behavioral_probe_blocker(),),
        }
    )


def _verified_tuple(recheck_input: ReworkEvidenceRecheckInput) -> tuple[VerifiedEvidence, ...]:
    return tuple(
        result.verified_evidence
        for result in recheck_input.evidence_verification_results
        if result.verified_evidence is not None
    )


def _verification_run(recheck_input: ReworkEvidenceRecheckInput) -> VerificationRun:
    namespace_ref = rework_evidence_namespace_ref(recheck_input.namespace).value
    command = next(command for command in recheck_input.run_manifest.commands if command.kind is RunManifestCommandKind.TEST)
    return VerificationRun(
        verification_run_id=VerificationRunRef(value=f"verification-run.{namespace_ref}.{command.command_id.value}"),
        execution_package_ref=EXECUTION_PACKAGE_REF,
        ticket_ref=TICKET_REF,
        command_id=command.command_id,
        command=command.command,
        cwd=command.cwd,
        exit_code=0,
        status=VerificationRunStatus.PASSED,
        stdout_ref=CommandOutputRef(value=f"command-output.{namespace_ref}.{command.command_id.value}.stdout"),
        stderr_ref=CommandOutputRef(value=f"command-output.{namespace_ref}.{command.command_id.value}.stderr"),
        duration_ms=0,
        started_at=NOW,
        finished_at=NOW,
        runner_ref=RunnerRef(value="runner.v2-100d"),
        environment_profile_ref=EnvironmentProfileRef(value="environment.v2-100d"),
        workspace_snapshot_ref=WorkspaceSnapshotRef(value=f"workspace-snapshot.{namespace_ref}"),
    )


def _service_run(recheck_input: ReworkEvidenceRecheckInput) -> ServiceRunEvidence:
    namespace_ref = rework_evidence_namespace_ref(recheck_input.namespace).value
    command = next(command for command in recheck_input.run_manifest.commands if command.kind is RunManifestCommandKind.RUN)
    return ServiceRunEvidence(
        service_run_evidence_id=f"service-run.{namespace_ref}.{command.command_id.value}",
        execution_package_ref=EXECUTION_PACKAGE_REF,
        ticket_ref=TICKET_REF,
        command_id=command.command_id,
        command=command.command,
        cwd=command.cwd,
        process_id=4321,
        readiness_url=ServiceReadinessUrl(value="http://127.0.0.1:8000/health"),
        probe_status_code=200,
        probe_body_sha256=SERVICE_BODY_SHA,
        stdout_ref=CommandOutputRef(value=f"command-output.service-run.{namespace_ref}.{command.command_id.value}.stdout"),
        stderr_ref=CommandOutputRef(value=f"command-output.service-run.{namespace_ref}.{command.command_id.value}.stderr"),
        started_at=NOW,
        ready_at=NOW,
        runner_ref=RunnerRef(value="runner.v2-100d.service"),
        environment_profile_ref=EnvironmentProfileRef(value="environment.v2-100d"),
        workspace_snapshot_ref=WorkspaceSnapshotRef(value=f"workspace-snapshot.{namespace_ref}"),
    )


def closeout_gate_input(
    *,
    recheck_input: ReworkEvidenceRecheckInput,
    source_inventory: SourceInventory,
    final_evidence_table: FinalEvidenceTable,
    checker_verdict: CheckerVerdict,
    run_manifest: RunManifest,
) -> CloseoutGateInput:
    verification_run = _verification_run(recheck_input)
    service_run = _service_run(recheck_input)
    verified = tuple(
        evidence.model_copy(
            update={
                "verification_run_refs": (verification_run.verification_run_id,)
                if evidence.source_kind is EvidenceClaimSourceKind.VERIFICATION_RUN
                else (),
                "service_run_refs": (service_run.service_run_evidence_id,)
                if evidence.source_kind is EvidenceClaimSourceKind.LIVE_BLACKBOX
                else (),
            }
        )
        for evidence in _verified_tuple(recheck_input)
    )
    workspace_evidence_bundle = build_workspace_evidence_bundle(
        workspace_manifest=workspace_manifest(),
        package_assembly=recheck_input.package_assembly,
        source_inventory=source_inventory,
        run_manifest=run_manifest,
        verification_runs=(verification_run,),
        service_runs=(service_run,),
        verified_evidence=verified,
        final_evidence_table=final_evidence_table,
    )
    run_manifest_bindings = tuple(
        validate_run_manifest_binding(
            run_manifest=run_manifest,
            package_contract=recheck_input.active_package_contract,
            command_id=command.command_id,
        )
        for command in run_manifest.commands
    )
    bindings_by_id = {binding.command_id.value: binding for binding in run_manifest_bindings}
    final_command_bindings = (
        CloseoutCommandEvidenceBinding(
            verification_run_ref=VerificationRunRef(value=service_run.service_run_evidence_id.value),
            run_manifest_ref=bindings_by_id[service_run.command_id.value].run_manifest_ref,
            package_contract_ref=bindings_by_id[service_run.command_id.value].package_contract_ref,
            command_id=bindings_by_id[service_run.command_id.value].command_id,
            binding_kind=bindings_by_id[service_run.command_id.value].kind,
        ),
        CloseoutCommandEvidenceBinding(
            verification_run_ref=verification_run.verification_run_id,
            run_manifest_ref=bindings_by_id[verification_run.command_id.value].run_manifest_ref,
            package_contract_ref=bindings_by_id[verification_run.command_id.value].package_contract_ref,
            command_id=bindings_by_id[verification_run.command_id.value].command_id,
            binding_kind=bindings_by_id[verification_run.command_id.value].kind,
        ),
    )
    return CloseoutGateInput(
        package_contract=recheck_input.active_package_contract,
        source_inventory=source_inventory,
        run_manifest=run_manifest,
        workspace_evidence_bundle=workspace_evidence_bundle,
        final_evidence_table=final_evidence_table,
        checker_verdict=checker_verdict,
        verification_runs=(verification_run,),
        service_run_evidence=(service_run,),
        verified_evidence=verified,
        provider_attempt_refs=(PROVIDER_ATTEMPT_REF,),
        final_command_bindings=final_command_bindings,
        replay_readiness=ReplayBundleReadiness(
            replay_passed=True,
            summary_hash=SUMMARY_HASH,
            event_range=f"events.{RUN_ID.value}.0001-0009",
            projection_versions=("rework-evidence.v1", "closeout-gate.v1"),
            hash_chain_verified=True,
            payload_sha256_verified=True,
            payload_manifest_ref=f"manifest.payload.{RUN_ID.value}.{ATTEMPT_ID.value}",
            payload_manifest_hash=PAYLOAD_HASH,
        ),
        git_audit_readiness=GitAuditReadiness(
            git_clean=True,
            final_commit_sha=FINAL_COMMIT_SHA,
            source_inventory_hash=SOURCE_INVENTORY_HASH,
            source_inventory_hash_matches=True,
            final_command_evidence_at_final_commit=True,
        ),
        process_audit_readiness=ProcessAuditReadiness(
            artifact_paths=PROCESS_AUDIT_ARTIFACT_PATHS,
            all_artifacts_present=True,
            timeline_key_events_present=True,
            agent_context_index_complete=True,
            artifact_lineage_complete=True,
            evidence_map_consistent_with_final_table=True,
        ),
    )


def fresh_recheck_parts() -> FreshRecheckParts:
    recheck_input = rework_input_with_verified_evidence()
    source_inventory = build_rework_source_inventory(recheck_input)
    final_evidence_table = build_rework_final_evidence_table(recheck_input)
    checker_verdict = build_rework_checker_verdict(recheck_input, final_evidence_table)
    old_source_inventory = source_inventory.model_copy(
        update={"source_inventory_id": SourceInventoryRef(value="source-inventory.old-run")}
    )
    old_namespace = EvidenceNamespaceRef(value="rework-evidence.run-old.cycle-old.attempt-old.g1")
    old_final_evidence_table = final_evidence_table.model_copy(
        update={
            "evidence_namespace_ref": old_namespace,
            "final_evidence_table_id": FinalEvidenceTableRef(
                value=f"final-evidence-table.{ACCEPTANCE_CONTRACT_REF.value}.{old_namespace.value}"
            ),
        }
    )
    old_checker_verdict = checker_verdict.model_copy(
        update={"final_evidence_table_ref": old_final_evidence_table.final_evidence_table_id}
    )
    return FreshRecheckParts(
        source_inventory=source_inventory,
        final_evidence_table=final_evidence_table,
        checker_verdict=checker_verdict,
        old_source_inventory=old_source_inventory,
        old_final_evidence_table=old_final_evidence_table,
        old_checker_verdict=old_checker_verdict,
    )


def rework_input_with_closeout_context(*, old_run_manifest: bool = False) -> ReworkEvidenceRecheckInput:
    recheck_input = rework_input_with_verified_evidence()
    parts = fresh_recheck_parts()
    closeout_input = closeout_gate_input(
        recheck_input=recheck_input,
        source_inventory=parts.source_inventory,
        final_evidence_table=parts.final_evidence_table,
        checker_verdict=parts.checker_verdict,
        run_manifest=recheck_input.run_manifest,
    )
    if old_run_manifest:
        closeout_input = closeout_input.model_copy(
            update={"run_manifest": old_run_manifest_with_service_and_probe()}
        )
    return recheck_input.model_copy(
        update={
            "closeout_context": ReworkCloseoutRecheckContext(closeout_input=closeout_input),
        }
    )
