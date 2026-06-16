from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
from typing import TYPE_CHECKING

from boardroom_os.agents.profiles import ModelExecutionProfile
from boardroom_os.agents.categories import RoleCategory
from boardroom_os.agents.role_prompt_hooks import RolePromptHookRef, build_baseline_role_prompt_hook_registry
from boardroom_os.agents.seat import AgentSeatRef
from boardroom_os.agents.skills import CapabilityTag
from boardroom_os.agents.seat import SeatDemand
from boardroom_os.adapters.process_runner import CommandRunner, CommandRunnerInput
from boardroom_os.checker.verdict import SourceDiffRef
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
from boardroom_os.contracts.evidence_obligation import EvidenceObligation, RequiredArtifactType, RequiredVerifier
from boardroom_os.contracts.hashes import Sha256Hex
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
from boardroom_os.contracts.project import ProjectCharterRegistry, create_project_charter
from boardroom_os.contracts.source_surface import OwnerSeatRef, RequiredTestRef, SourceSurface
from boardroom_os.contracts.types import (
    AcceptanceRef,
    ContractId,
    ContractStatus,
    EvidenceObligationRef,
    SourceSurfaceRef,
)
from boardroom_os.evidence.claim import (
    EvidenceArtifactRef,
    EvidenceClaimRef,
    EvidenceClaimSourceKind,
    build_evidence_claim_from_live_blackbox,
    build_evidence_claim_from_verification_run,
)
from boardroom_os.evidence.fallback_registry import FallbackDecisionRecordRef
from boardroom_os.evidence.live_blackbox import (
    LiveBlackboxIntegrationEvidence,
    LiveBlackboxIntegrationEvidenceRef,
    LiveBlackboxProbeResult,
)
from boardroom_os.evidence.service_run import ServiceReadinessUrl, ServiceRunEvidence, ServiceRunEvidenceRef
from boardroom_os.evidence.table import FinalEvidenceBlocker, FinalEvidenceBlockerCode
from boardroom_os.evidence.verifier import (
    ArtifactManifest,
    ArtifactManifestEntry,
    ArtifactSha256,
    EvidencePurposePolicy,
    EvidencePurposeRule,
    EvidenceVerificationInput,
    EvidenceVerificationResult,
    EvidenceVerifier,
    VerifiedArtifact,
    VerifiedEvidence,
)
from boardroom_os.execution.context_index import ProviderAttemptRef
from boardroom_os.execution.fallback import EvidencePurpose
from boardroom_os.execution.package import ExecutionPackage, ExecutionPackageRef
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
from boardroom_os.graph.ticket import TicketCreatedPayload
from boardroom_os.reducers.rework import (
    GraphPatchApprovalPayload,
    GraphPatchReviewPayload,
    ReworkAttemptPayload,
    ReworkPlanPayload,
    ReworkRequestPayload,
    ReworkReviewPayload,
    ReworkTerminalPayload,
)
from boardroom_os.providers.attempt import (
    ProviderArtifactRef,
    ProviderAttempt,
    ProviderAttemptOutcome,
    ProviderAttemptStatus,
)
from boardroom_os.providers.openai_adapter import FileProviderOutputStore
from boardroom_os.rework.evidence import (
    ReworkCloseoutRecheckContext,
    ReworkEnvironmentUsage,
    ReworkEvidenceNamespace,
    ReworkEvidenceRecheckInput,
    recheck_rework_attempt,
    rework_evidence_namespace_ref,
)
from boardroom_os.rework.model import (
    BlockerRef,
    ReworkAttempt,
    ReworkAttemptId,
    ReworkCycleId,
    ReworkDecision,
    ReworkDecisionId,
    ReworkDecisionKind,
    GraphPatchApprovalSet,
    GraphPatchApprovalSetId,
    GraphPatchApprovalStatus,
    GraphPatchOperationKind,
    GraphPatchReview,
    GraphPatchReviewDomain,
    GraphPatchReviewId,
    GraphPatchReviewStatus,
    ReworkActorKind,
    ReworkPlanId,
    ReworkPlan,
    ReworkRequest,
    ReworkTerminationDecision,
    ReworkTerminationDecisionId,
    ReworkTerminationReason,
    RunId,
    TicketGraphPatch,
    TicketGraphPatchId,
    TicketGraphPatchOperation,
    TicketGraphPatchOperationId,
)
from boardroom_os.rework.planner import CeoReworkPlannerInput, CeoReworkPlannerOutput
from boardroom_os.rework.reviewer import GraphPatchReviewerInput, GraphPatchReviewerOutput
from boardroom_os.workspace.assembler import (
    PackageArtifact,
    PackageArtifactKind,
    PackageArtifactPath,
    assemble_package,
)
from boardroom_os.workspace.manifest import WorkflowRef, WorkspacePath, build_workspace_manifest
from boardroom_os.workspace.evidence_export import build_workspace_evidence_bundle
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
from boardroom_os.workspace.source_inventory import (
    PackageCommitRef,
    SourceFilePath,
    SourceFileRecord,
    SourceLineageRecord,
)

if TYPE_CHECKING:
    from boardroom_os.proving.v2_100_rework_loop import (
        ScenarioRoundBuild,
        ScenarioRoundProvider,
        V2_100ScenarioInput,
    )


DEFAULT_FAILURE_SUMMARY_PATH = Path(
    "examples/generated-workspaces/tiny-fullstack/30-audit/v2-090k-failure-snapshot/failure-summary.json"
)

NOW = datetime(2026, 6, 15, 9, 0, tzinfo=UTC)
RUN_ID = RunId(value="run-v2-100e")
CYCLE_ID = ReworkCycleId(value="rework-cycle.v2-100e")
TICKET_REF = TicketId(value="ticket.v2-100e.backend")
EXECUTION_PACKAGE_REF = ExecutionPackageRef(value="execution-package.v2-100e.backend")
REWORK_PLAN_REF = ReworkPlanId(value="rework-plan.v2-100e.1")
ACCEPTANCE_REF = AcceptanceRef(value="acceptance.book.add")
LIST_ACCEPTANCE_REF = AcceptanceRef(value="acceptance.book.list")
PERSISTENCE_ACCEPTANCE_REF = AcceptanceRef(value="acceptance.persistence.sqlite")
TEST_INSTRUCTIONS_ACCEPTANCE_REF = AcceptanceRef(value="acceptance.instructions.tests")
SOURCE_SURFACE_REF = SourceSurfaceRef(value="surface.backend.api")
TEST_SURFACE_REF = SourceSurfaceRef(value="surface.backend.tests")
BEHAVIORAL_PROBE_SURFACE_REF = SourceSurfaceRef(value="surface.behavioral_probe")
RUN_MANIFEST_SURFACE_REF = SourceSurfaceRef(value="surface.run-manifest")
PACKAGE_CONTRACT_SURFACE_REF = SourceSurfaceRef(value="surface.package-contract")
ENV_RUN_MANIFEST_SURFACE_REF = SourceSurfaceRef(value="surface.run_manifest")
CLOSEOUT_AUDIT_SURFACE_REF = SourceSurfaceRef(value="surface.closeout_audit")
EVIDENCE_OBLIGATION_REF = EvidenceObligationRef(value="evidence.book.add.live")
ADD_API_EVIDENCE_OBLIGATION_REF = EvidenceObligationRef(value="evidence.add.api")
LIST_API_EVIDENCE_OBLIGATION_REF = EvidenceObligationRef(value="evidence.list.api")
TEST_INSTRUCTIONS_EVIDENCE_OBLIGATION_REF = EvidenceObligationRef(value="evidence.tests.instructions")
SQLITE_EVIDENCE_OBLIGATION_REF = EvidenceObligationRef(value="evidence.sqlite.persistence")
PACKAGE_CONTRACT_REF = ContractId(value="package.v2-100e")
ACCEPTANCE_CONTRACT_REF = ContractId(value="acceptance.v2-100e")
PROVIDER_ATTEMPT_REF = ProviderAttemptRef(value="provider-attempt.worker.rework.v2-100e.1")
TARGET_BLOCKER_REF = BlockerRef(value="v2-090k-failure.probe-response-shape-mismatch")
FINAL_COMMIT_SHA = "1234567890abcdef1234567890abcdef12345678"


@dataclass(frozen=True)
class V2_100ResettableFixture:
    package_root: Path
    request: ReworkRequest
    failing_recheck_input: ReworkEvidenceRecheckInput
    accepted_recheck_input: ReworkEvidenceRecheckInput

    def without_provider_attempt(self) -> "V2_100ResettableFixture":
        return replace_attempt(self, provider_attempt_refs=())

    def with_stale_final_evidence(self) -> "V2_100ResettableFixture":
        return replace_with_previous_namespace_evidence(self)

    def with_command_success_wrong_claim(self) -> "V2_100ResettableFixture":
        return replace_with_failed_behavioral_blocker_despite_passed_command(self)

    def with_old_closeout_run_ref(self) -> "V2_100ResettableFixture":
        return replace_with_old_closeout_readiness_refs(self)


def replace_attempt(
    base: V2_100ResettableFixture,
    *,
    provider_attempt_refs: tuple[ProviderAttemptRef, ...],
) -> V2_100ResettableFixture:
    invalid_attempt = base.accepted_recheck_input.attempt.model_copy(
        update={"provider_attempt_refs": provider_attempt_refs}
    )
    invalid_recheck = base.accepted_recheck_input.model_copy(update={"attempt": invalid_attempt})
    return _copy_fixture(base, accepted_recheck_input=invalid_recheck)


def replace_with_previous_namespace_evidence(
    base: V2_100ResettableFixture,
) -> V2_100ResettableFixture:
    invalid_recheck = base.accepted_recheck_input.model_copy(
        update={"namespace": base.failing_recheck_input.namespace}
    )
    return _copy_fixture(base, accepted_recheck_input=invalid_recheck)


def replace_with_failed_behavioral_blocker_despite_passed_command(
    base: V2_100ResettableFixture,
) -> V2_100ResettableFixture:
    invalid_recheck = base.accepted_recheck_input.model_copy(
        update={
            "failed_final_evidence_blockers": (
                _failed_behavioral_probe_blocker(base.accepted_recheck_input.namespace),
            )
        }
    )
    return _copy_fixture(base, accepted_recheck_input=invalid_recheck)


def replace_with_old_closeout_readiness_refs(
    base: V2_100ResettableFixture,
) -> V2_100ResettableFixture:
    invalid_recheck = base.accepted_recheck_input.model_copy(
        update={"namespace": base.failing_recheck_input.namespace}
    )
    return _copy_fixture(base, accepted_recheck_input=invalid_recheck)


def build_v2_100_resettable_fixture(*, package_root: Path) -> V2_100ResettableFixture:
    package_root.mkdir(parents=True, exist_ok=True)
    _write_minimal_package(package_root)

    from boardroom_os.proving.v2_100_rework_loop import project_snapshot_request

    scenario_input = build_v2_100_scenario_input(
        package_root=package_root,
        require_real_provider=False,
    )
    request = project_snapshot_request(scenario_input)
    failing_recheck_input = _recheck_input(
        attempt_id=ReworkAttemptId(value="rework-attempt.v2-100e.1"),
        graph_version=scenario_input.initial_graph_version + 8,
        include_live_evidence=False,
        failed_blocker=True,
        package_root=package_root,
    )
    accepted_recheck_input = _recheck_input(
        attempt_id=ReworkAttemptId(value="rework-attempt.v2-100e.2"),
        graph_version=scenario_input.initial_graph_version + 16,
        include_live_evidence=True,
        failed_blocker=False,
        package_root=package_root,
    )
    accepted_recheck_input = _with_closeout_context(accepted_recheck_input)
    return V2_100ResettableFixture(
        package_root=package_root,
        request=request,
        failing_recheck_input=failing_recheck_input,
        accepted_recheck_input=accepted_recheck_input,
    )


def build_real_provider_recheck_input(
    *,
    package_root: Path,
    attempt_id: ReworkAttemptId,
    graph_version: int,
    provider_attempt_ref: ProviderAttemptRef,
    rework_plan_ref: ReworkPlanId,
) -> ReworkEvidenceRecheckInput:
    return _with_closeout_context(_recheck_input(
        attempt_id=attempt_id,
        graph_version=graph_version,
        include_live_evidence=True,
        failed_blocker=False,
        provider_attempt_ref=provider_attempt_ref,
        rework_plan_ref=rework_plan_ref,
        source_prefix="real-provider-evidence",
        package_root=package_root,
    ))


def build_v2_100_scenario_input(
    *,
    snapshot_summary_path: Path = DEFAULT_FAILURE_SUMMARY_PATH,
    export_root: Path | None = None,
    provider_env_path: Path = Path(".env"),
    require_real_provider: bool = True,
    max_rounds: int = 2,
    package_root: Path | None = None,
) -> "V2_100ScenarioInput":
    from boardroom_os.proving.v2_100_rework_loop import V2_100ScenarioInput

    return V2_100ScenarioInput(
        project_ref="project-tiny-fullstack",
        snapshot_summary_path=snapshot_summary_path,
        run_id=RUN_ID,
        cycle_id=CYCLE_ID,
        package_contract_ref=PACKAGE_CONTRACT_REF.value,
        run_manifest_ref=_run_manifest().run_manifest_id.value,
        active_acceptance_refs=(
            ACCEPTANCE_REF.value,
            LIST_ACCEPTANCE_REF.value,
            PERSISTENCE_ACCEPTANCE_REF.value,
            TEST_INSTRUCTIONS_ACCEPTANCE_REF.value,
        ),
        active_source_surface_refs=(
            SOURCE_SURFACE_REF.value,
            TEST_SURFACE_REF.value,
            BEHAVIORAL_PROBE_SURFACE_REF.value,
            RUN_MANIFEST_SURFACE_REF.value,
            PACKAGE_CONTRACT_SURFACE_REF.value,
            ENV_RUN_MANIFEST_SURFACE_REF.value,
            CLOSEOUT_AUDIT_SURFACE_REF.value,
        ),
        active_evidence_obligation_refs=(
            EVIDENCE_OBLIGATION_REF.value,
            ADD_API_EVIDENCE_OBLIGATION_REF.value,
            LIST_API_EVIDENCE_OBLIGATION_REF.value,
            TEST_INSTRUCTIONS_EVIDENCE_OBLIGATION_REF.value,
            SQLITE_EVIDENCE_OBLIGATION_REF.value,
        ),
        active_contract_refs=(ACCEPTANCE_CONTRACT_REF.value, PACKAGE_CONTRACT_REF.value),
        initial_graph_version=40,
        max_rounds=max_rounds,
        provider_env_path=provider_env_path,
        export_root=export_root or (package_root / "30-audit" if package_root else None),
        require_real_provider=require_real_provider,
    )


def build_accepted_round_input(tmp_path: Path) -> "ScenarioRoundBuild":
    scenario_input = build_v2_100_scenario_input(
        package_root=tmp_path / "package",
        require_real_provider=False,
    )
    fixture = build_v2_100_resettable_fixture(package_root=tmp_path / "package")
    return _round_build(
        scenario_input=scenario_input,
        request=fixture.request,
        recheck_input=fixture.accepted_recheck_input,
        round_index=1,
        started_at_graph_version=scenario_input.initial_graph_version,
    )


def build_two_round_provider(tmp_path: Path) -> "ScenarioRoundProvider":
    return _DeterministicRoundProvider(
        package_root=tmp_path / "package-two-round",
        modes=("failing", "accepted"),
    )


def build_exhausted_round_provider(tmp_path: Path) -> "ScenarioRoundProvider":
    return _DeterministicRoundProvider(
        package_root=tmp_path / "package-exhausted",
        modes=("exhausted",),
    )


class _DeterministicRoundProvider:
    def __init__(self, *, package_root: Path, modes: tuple[str, ...]) -> None:
        self._package_root = package_root
        self._modes = modes

    def build_round(
        self,
        scenario_input: "V2_100ScenarioInput",
        request: ReworkRequest,
        *,
        round_index: int,
        started_at_graph_version: int,
    ) -> "ScenarioRoundBuild":
        fixture = build_v2_100_resettable_fixture(package_root=self._package_root)
        mode = self._modes[min(round_index - 1, len(self._modes) - 1)]
        if mode == "accepted":
            recheck_input = fixture.accepted_recheck_input
            terminal_decision = None
        elif mode == "exhausted":
            recheck_input = fixture.failing_recheck_input
            outcome = recheck_rework_attempt(recheck_input).to_rework_outcome()
            terminal_decision = ReworkTerminationDecision(
                termination_decision_id=ReworkTerminationDecisionId(
                    value=f"rework-termination.v2-100e.round-{round_index}"
                ),
                cycle_id=scenario_input.cycle_id,
                reason=ReworkTerminationReason.EXHAUSTED_BUDGET,
                blocker_refs=outcome.remaining_blocker_refs,
                evidence_refs=tuple(recheck_input.attempt.command_evidence_refs),
                decided_by_actor=ReworkActorKind.GOVERNANCE_COMMAND_HANDLER,
                decided_at=NOW,
                rationale="Round budget exhausted with verified blockers remaining.",
            )
        else:
            recheck_input = fixture.failing_recheck_input
            terminal_decision = None
        return _round_build(
            scenario_input=scenario_input,
            request=request,
            recheck_input=recheck_input,
            round_index=round_index,
            started_at_graph_version=started_at_graph_version,
            terminal_decision=terminal_decision,
        )


def _round_build(
    *,
    scenario_input: "V2_100ScenarioInput",
    request: ReworkRequest,
    recheck_input: ReworkEvidenceRecheckInput,
    round_index: int,
    started_at_graph_version: int,
    terminal_decision: ReworkTerminationDecision | None = None,
) -> "ScenarioRoundBuild":
    from boardroom_os.proving.v2_100_rework_loop import (
        ScenarioRoundBuild,
        V2_100ScenarioRoundInput,
        _ScenarioPayloadResolver,
        provider_attempt_manifest_entry,
    )

    plan_output = _planner_output(scenario_input, request)
    review_outputs = _review_outputs(plan_output.patch)
    approval_set = GraphPatchApprovalSet(
        approval_set_id=GraphPatchApprovalSetId(value=f"graph-patch-approval.v2-100e.round-{round_index}"),
        ticket_graph_patch_ref=plan_output.patch.ticket_graph_patch_id,
        required_domains=plan_output.patch.required_review_domains,
        reviews=tuple(output.review for output in review_outputs),
        status=GraphPatchApprovalStatus.READY_TO_COMMIT,
        computed_at=NOW,
    )
    ticket_payload = _ticket_payload()
    round_input = V2_100ScenarioRoundInput(
        round_index=round_index,
        project_ref=scenario_input.project_ref,
        request=request,
        planner_output=plan_output,
        reviewer_outputs=review_outputs,
        approval_set=approval_set,
        rework_ticket_payload=ticket_payload,
        attempt=recheck_input.attempt,
        recheck_input=recheck_input,
        terminal_decision=terminal_decision,
        started_at_graph_version=started_at_graph_version,
    )
    payloads = {
        f"payload:v2-100e:round-{round_index}:request": ReworkRequestPayload(request=request),
        f"payload:v2-100e:round-{round_index}:plan": ReworkPlanPayload(
            request_ref=request.rework_request_id,
            plan=plan_output.plan,
            patch=plan_output.patch,
        ),
        f"payload:v2-100e:round-{round_index}:approval": GraphPatchApprovalPayload(
            patch_ref=plan_output.patch.ticket_graph_patch_id,
            approval_set=approval_set,
        ),
        f"payload:v2-100e:round-{round_index}:ticket": ticket_payload,
        f"payload:v2-100e:round-{round_index}:attempt": ReworkAttemptPayload(attempt=recheck_input.attempt),
    }
    for index, output in enumerate(review_outputs, start=1):
        payloads[f"payload:v2-100e:round-{round_index}:review-{index}"] = GraphPatchReviewPayload(
            patch_ref=plan_output.patch.ticket_graph_patch_id,
            review=output.review,
        )
    manifest_store = FileProviderOutputStore(
        root=(
            scenario_input.export_root / "provider-artifacts"
            if scenario_input.export_root is not None
            else scenario_input.snapshot_summary_path.parent / "v2-100e-provider-artifacts"
        )
    )
    provider_attempt_manifest_entries = _provider_attempt_manifest_entries(
        manifest_store,
        planner_output=plan_output,
        review_outputs=review_outputs,
        worker_attempt=_provider_attempt(),
    )
    return ScenarioRoundBuild(
        round_input=round_input,
        payload_resolver=_ScenarioPayloadResolver(payloads),
        provider_attempt_manifest_entries=provider_attempt_manifest_entries,
    )


def _provider_attempt_manifest_entries(
    manifest_store: FileProviderOutputStore,
    *,
    planner_output: CeoReworkPlannerOutput,
    review_outputs: tuple[GraphPatchReviewerOutput, ...],
    worker_attempt: ProviderAttempt,
) -> tuple["V2_100ProviderAttemptManifestEntry", ...]:
    from boardroom_os.proving.v2_100_rework_loop import (
        V2_100ProviderAttemptManifestEntry,
        provider_attempt_manifest_entry,
    )

    bindings: list[tuple[ProviderAttempt | None, str, str]] = [
        (
            planner_output.provider_attempt,
            planner_output.planner_input.planner_execution_package_ref.value,
            planner_output.planner_input.planner_role_prompt_hook_ref.value,
        ),
    ]
    bindings.extend(
        (
            output.provider_attempt,
            output.reviewer_input.reviewer_execution_package_ref.value,
            output.reviewer_input.reviewer_role_prompt_hook_ref.value,
        )
        for output in review_outputs
    )
    bindings.append(
        (
            worker_attempt,
            EXECUTION_PACKAGE_REF.value,
            "role-prompt-hook.baseline.worker.v1",
        )
    )
    materialized = _materialized_provider_attempts(
        manifest_store,
        tuple(attempt for attempt, _expected_package, _expected_hook in bindings),
    )
    entries: list[V2_100ProviderAttemptManifestEntry] = []
    for attempt, (_original_attempt, expected_package, expected_hook) in zip(
        materialized,
        bindings,
        strict=True,
    ):
        entries.append(
            provider_attempt_manifest_entry(
                attempt,
                artifact_store=manifest_store,
                expected_input_package_ref=expected_package,
                expected_hook_ref=expected_hook,
            )
        )
    return tuple(entries)


def _materialized_provider_attempts(
    store: FileProviderOutputStore,
    attempts: tuple[ProviderAttempt | None, ...],
) -> tuple[ProviderAttempt, ...]:
    materialized: list[ProviderAttempt] = []
    for attempt in attempts:
        if attempt is None:
            continue
        raw_artifact = store.write_text(
            response_id=_provider_response_id(attempt.provider_attempt_id.value),
            artifact_kind="raw",
            text=f'{{"provider_attempt_ref":"{attempt.provider_attempt_id.value}","kind":"raw"}}',
        )
        parsed_artifact = store.write_text(
            response_id=_provider_response_id(attempt.provider_attempt_id.value),
            artifact_kind="parsed",
            text=f'{{"provider_attempt_ref":"{attempt.provider_attempt_id.value}","kind":"parsed"}}',
        )
        materialized.append(
            attempt.model_copy(
                update={
                    "raw_output_ref": raw_artifact.artifact_ref,
                    "parsed_output_ref": parsed_artifact.artifact_ref,
                }
            )
        )
    return tuple(materialized)


def _provider_response_id(provider_attempt_ref: str) -> str:
    return provider_attempt_ref.replace(":", ".").replace("/", ".")


def _planner_output(
    scenario_input: "V2_100ScenarioInput",
    request: ReworkRequest,
) -> CeoReworkPlannerOutput:
    attempt = _role_provider_attempt(
        attempt_ref="provider-attempt.v2-100e.ceo",
        input_package_ref="execution-package.v2-100e.ceo",
        seat_ref="seat.ceo.delivery",
        hook_ref="role-prompt-hook.baseline.ceo.v1",
    )
    plan_id = ReworkPlanId(value="rework-plan.v2-100e.1")
    patch_id = TicketGraphPatchId(value="ticket-graph-patch.v2-100e.1")
    operation_id = TicketGraphPatchOperationId(value="ticket-graph-patch-operation.v2-100e.1")
    decision = ReworkDecision(
        decision_id=ReworkDecisionId(value="rework-decision.v2-100e.fix-implementation"),
        decision_kind=ReworkDecisionKind.FIX_IMPLEMENTATION,
        blocker_refs=tuple(blocker for issue in request.issues for blocker in issue.blocker_refs),
        issue_ids=tuple(issue.issue_id for issue in request.issues),
        target_ticket_refs=(TICKET_REF,),
        target_graph_operation_refs=(operation_id,),
        rationale="Create a contract-bound rework ticket for the verified blocker set.",
    )
    plan = ReworkPlan(
        rework_plan_id=plan_id,
        cycle_id=request.cycle_id,
        rework_request_id=request.rework_request_id,
        planner_actor=ReworkActorKind.CEO,
        planner_attempt_ref=attempt.provider_attempt_id,
        decisions=(decision,),
        ticket_graph_patch_ref=patch_id,
        risk_notes=("Evidence must be regenerated in the current round.",),
        stop_or_escalation_conditions=("Escalate or exhaust when budget is reached with blockers.",),
    )
    patch = TicketGraphPatch(
        ticket_graph_patch_id=patch_id,
        base_graph_version=request.active_graph_version,
        proposed_by_plan_ref=plan_id,
        operations=(
            TicketGraphPatchOperation(
                operation_id=operation_id,
                operation_kind=GraphPatchOperationKind.CREATE_REWORK_TICKET,
                target_ticket_refs=(TICKET_REF,),
                acceptance_refs=(ACCEPTANCE_REF,),
                source_surface_refs=(SOURCE_SURFACE_REF, TEST_SURFACE_REF),
                evidence_obligation_refs=(EVIDENCE_OBLIGATION_REF,),
                rationale="Bind the rework ticket to active acceptance and evidence obligations.",
            ),
        ),
        affected_ticket_refs=(TICKET_REF,),
        affected_contract_refs=request.active_contract_refs,
        affected_source_surface_refs=(SOURCE_SURFACE_REF, TEST_SURFACE_REF),
        required_review_domains=(
            GraphPatchReviewDomain.PLANNING,
            GraphPatchReviewDomain.STRUCTURAL,
            GraphPatchReviewDomain.BLOCKER_COVERAGE,
        ),
        patch_hash="sha256:" + "8" * 64,
    )
    planner_input = CeoReworkPlannerInput(
        rework_request=request,
        current_graph_version=request.active_graph_version,
        active_contract_refs=request.active_contract_refs,
        active_acceptance_refs=tuple(AcceptanceRef(value=value) for value in scenario_input.active_acceptance_refs),
        active_source_surface_refs=tuple(SourceSurfaceRef(value=value) for value in scenario_input.active_source_surface_refs),
        active_evidence_obligation_refs=tuple(
            EvidenceObligationRef(value=value) for value in scenario_input.active_evidence_obligation_refs
        ),
        package_contract_ref=ContractId(value=scenario_input.package_contract_ref),
        run_manifest_ref=scenario_input.run_manifest_ref,
        planner_execution_package_ref=attempt.input_package_ref,
        planner_role_prompt_hook_ref=attempt.role_prompt_hook_ref,
    )
    return CeoReworkPlannerOutput(
        planner_input=planner_input,
        provider_attempt=attempt,
        plan=plan,
        patch=patch,
        parsed_payload_ref=attempt.parsed_output_ref,
        validated_at=NOW,
    )


def _review_outputs(patch: TicketGraphPatch) -> tuple[GraphPatchReviewerOutput, ...]:
    specs = (
        (GraphPatchReviewDomain.PLANNING, ReworkActorKind.CEO, "role-prompt-hook.baseline.ceo.v1"),
        (GraphPatchReviewDomain.STRUCTURAL, ReworkActorKind.ARCHITECT, "role-prompt-hook.baseline.architect.v1"),
        (GraphPatchReviewDomain.BLOCKER_COVERAGE, ReworkActorKind.CHECKER, "role-prompt-hook.baseline.checker.v1"),
    )
    outputs: list[GraphPatchReviewerOutput] = []
    for domain, actor, hook_ref in specs:
        attempt = _role_provider_attempt(
            attempt_ref=f"provider-attempt.v2-100e.review.{domain.value}",
            input_package_ref=f"execution-package.v2-100e.review.{domain.value}",
            seat_ref=f"seat.{actor.value}",
            hook_ref=hook_ref,
        )
        review = GraphPatchReview(
            graph_patch_review_id=GraphPatchReviewId(value=f"graph-patch-review.v2-100e.{domain.value}"),
            ticket_graph_patch_ref=patch.ticket_graph_patch_id,
            review_domain=domain,
            reviewer_actor=actor,
            reviewer_role_kind=actor,
            reviewer_attempt_ref=attempt.provider_attempt_id,
            status=GraphPatchReviewStatus.APPROVED,
            checked_invariants=(f"{domain.value}.contract-bound",),
            created_at=NOW,
        )
        outputs.append(
            GraphPatchReviewerOutput(
                reviewer_input=GraphPatchReviewerInput(
                    patch=patch,
                    review_domain=domain,
                    reviewer_role_kind=actor,
                    expected_provider_attempt_ref=attempt.provider_attempt_id,
                    reviewer_execution_package_ref=attempt.input_package_ref,
                    reviewer_role_prompt_hook_ref=attempt.role_prompt_hook_ref,
                ),
                provider_attempt=attempt,
                review=review,
                parsed_payload_ref=attempt.parsed_output_ref,
                validated_at=NOW,
            )
        )
    return tuple(outputs)


def _ticket_payload() -> TicketCreatedPayload:
    return TicketCreatedPayload(
        ticket_id=TICKET_REF,
        purpose="Fix the V2-090K response shape blocker under active contract refs.",
        seat_demand=SeatDemand(
            required_role_category=RoleCategory.IMPLEMENTATION,
            required_capability_tags=(CapabilityTag(value="task.implementation"),),
        ),
        depends_on=(),
        acceptance_refs=(ACCEPTANCE_REF.value,),
        source_surface_refs=(SOURCE_SURFACE_REF.value, TEST_SURFACE_REF.value),
        evidence_obligations=(EVIDENCE_OBLIGATION_REF.value,),
        allowed_read_refs=("contract:acceptance.v2-100e",),
        allowed_write_set=("app/main.py", "tests/test_books.py"),
        attempt_count=0,
    )


def _role_provider_attempt(
    *,
    attempt_ref: str,
    input_package_ref: str,
    seat_ref: str,
    hook_ref: str,
) -> ProviderAttempt:
    hook = build_baseline_role_prompt_hook_registry().require(RolePromptHookRef(value=hook_ref))
    return ProviderAttempt(
        provider_attempt_id=ProviderAttemptRef(value=attempt_ref),
        provider="openai-compatible",
        model="gpt-5.5",
        reasoning_effort="high",
        input_package_ref=ExecutionPackageRef(value=input_package_ref),
        seat_ref=AgentSeatRef(value=seat_ref),
        role_prompt_hook_ref=hook.hook_ref,
        role_prompt_hook_version=hook.hook_version,
        role_prompt_hook_sha256=hook.content_sha256,
        status=ProviderAttemptStatus.SUCCEEDED,
        outcome=ProviderAttemptOutcome.PRIMARY_PROVIDER_OUTPUT,
        started_at=NOW,
        finished_at=NOW,
        raw_output_ref=ProviderArtifactRef(value=f"provider-artifact.{attempt_ref}.raw"),
        parsed_output_ref=ProviderArtifactRef(value=f"provider-artifact.{attempt_ref}.parsed"),
    )


def _copy_fixture(
    base: V2_100ResettableFixture,
    *,
    accepted_recheck_input: ReworkEvidenceRecheckInput,
) -> V2_100ResettableFixture:
    return V2_100ResettableFixture(
        package_root=base.package_root,
        request=base.request,
        failing_recheck_input=base.failing_recheck_input,
        accepted_recheck_input=accepted_recheck_input,
    )


def _methodology_profile() -> MethodologyProfile:
    template_kind = MethodologyTemplateKind.HYBRID
    return MethodologyProfile(
        methodology_profile_id=ContractId(value="methodology.v2-100e"),
        project_charter_ref=ContractId(value="project-charter.v2-100e"),
        template_kind=template_kind,
        documentation_density=DocumentationDensity.STANDARD,
        docs_template_key=docs_template_key_for(template_kind),
        documentation_obligations=default_documentation_obligations_for(template_kind),
    )


def _acceptance_contract():
    directive = BoardDirective(
        board_directive_id=ContractId(value="directive.v2-100e"),
        source_type="natural_language",
        content_ref=ContractId(value="content.v2-100e"),
        received_at=NOW,
        requester_ref=ContractId(value="human-board"),
    )
    charter = create_project_charter(
        registry=DirectiveRegistry.from_directives(directive),
        project_charter_id=ContractId(value="project-charter.v2-100e"),
        board_directive_ref=directive.board_directive_id,
        project_goal="Prove a multi-round CEO-governed rework loop.",
        delivery_type="generated_project_package",
        non_goals=("Do not treat runtime completion as accepted rework.",),
        constraints=("Every round must re-enter evidence and checker gates.",),
        risks=("Old evidence may be reused if namespace checks are bypassed.",),
        success_summary="Current evidence accepts the projected blocker or terminates explicitly.",
    )
    return create_acceptance_contract(
        registry=ProjectCharterRegistry.from_charters(charter),
        acceptance_contract_id=ACCEPTANCE_CONTRACT_REF,
        project_charter_ref=charter.project_charter_id,
        status=ContractStatus(value="active"),
        criteria=(
            AcceptanceCriterion(
                acceptance_ref=ACCEPTANCE_REF,
                statement="Book creation API returns a response shape matching the active probe.",
                evidence_required=(
                    EvidenceRequirement(value="source"),
                    EvidenceRequirement(value="test"),
                    EvidenceRequirement(value="live_blackbox"),
                ),
                blocking=True,
                source_surface_refs=(SOURCE_SURFACE_REF, TEST_SURFACE_REF),
                verification_strategy=VerificationStrategy(value="pytest plus live blackbox probe"),
            ),
            AcceptanceCriterion(
                acceptance_ref=LIST_ACCEPTANCE_REF,
                statement="Book listing API returns active package data.",
                evidence_required=(EvidenceRequirement(value="live_blackbox"),),
                blocking=True,
                source_surface_refs=(SOURCE_SURFACE_REF, BEHAVIORAL_PROBE_SURFACE_REF),
                verification_strategy=VerificationStrategy(value="live blackbox probe"),
            ),
            AcceptanceCriterion(
                acceptance_ref=PERSISTENCE_ACCEPTANCE_REF,
                statement="SQLite persistence is bound by the active run manifest.",
                evidence_required=(EvidenceRequirement(value="run_manifest"),),
                blocking=True,
                source_surface_refs=(SOURCE_SURFACE_REF, ENV_RUN_MANIFEST_SURFACE_REF),
                verification_strategy=VerificationStrategy(value="run manifest env binding check"),
            ),
            AcceptanceCriterion(
                acceptance_ref=TEST_INSTRUCTIONS_ACCEPTANCE_REF,
                statement="Test instructions use the active package command contract.",
                evidence_required=(EvidenceRequirement(value="test"),),
                blocking=True,
                source_surface_refs=(TEST_SURFACE_REF, ENV_RUN_MANIFEST_SURFACE_REF),
                verification_strategy=VerificationStrategy(value="pytest command evidence"),
            ),
        ),
    )


def _package_contract():
    profile = _methodology_profile()
    return create_package_contract(
        methodology_registry=MethodologyProfileRegistry.from_profiles(profile),
        package_contract_id=PACKAGE_CONTRACT_REF,
        project_charter_ref=ContractId(value="project-charter.v2-100e"),
        package_root="10-project",
        project_type=PackageProjectType.SOFTWARE,
        source_surfaces=(
            _surface(
                SOURCE_SURFACE_REF,
                ("app/main.py",),
                (ACCEPTANCE_REF, LIST_ACCEPTANCE_REF, PERSISTENCE_ACCEPTANCE_REF),
            ),
            _surface(
                TEST_SURFACE_REF,
                ("tests/test_books.py",),
                (ACCEPTANCE_REF, TEST_INSTRUCTIONS_ACCEPTANCE_REF),
            ),
            _surface(BEHAVIORAL_PROBE_SURFACE_REF, ("tests/probes/books.json",), (ACCEPTANCE_REF, LIST_ACCEPTANCE_REF)),
            _surface(
                RUN_MANIFEST_SURFACE_REF,
                ("run-manifest.json",),
                (ACCEPTANCE_REF, PERSISTENCE_ACCEPTANCE_REF, TEST_INSTRUCTIONS_ACCEPTANCE_REF),
            ),
            _surface(PACKAGE_CONTRACT_SURFACE_REF, ("package-contract.json",), (ACCEPTANCE_REF,)),
            _surface(
                ENV_RUN_MANIFEST_SURFACE_REF,
                ("run-manifest.json",),
                (ACCEPTANCE_REF, PERSISTENCE_ACCEPTANCE_REF, TEST_INSTRUCTIONS_ACCEPTANCE_REF),
            ),
            _surface(
                CLOSEOUT_AUDIT_SURFACE_REF,
                ("audit/process-timeline.md",),
                (
                    ACCEPTANCE_REF,
                    LIST_ACCEPTANCE_REF,
                    PERSISTENCE_ACCEPTANCE_REF,
                    TEST_INSTRUCTIONS_ACCEPTANCE_REF,
                ),
            ),
        ),
        run_commands=(
            _command("run-api", ("python", "-m", "app.main")),
            _command("run-frontend", ("python", "-c", "print('frontend ready')")),
        ),
        test_commands=(_command("test-api", ("python", "-c", "print('v2-100e fixture ok')")),),
        integration_boundaries=(IntegrationBoundary(value="local-http"),),
        docs_required=True,
        closeout_required=True,
        methodology_profile_ref=profile.methodology_profile_id,
        docs_template_key=profile.docs_template_key,
        documentation_obligations=profile.documentation_obligations,
    )


def _surface(
    ref: SourceSurfaceRef,
    paths: tuple[str, ...],
    acceptance_refs: tuple[AcceptanceRef, ...],
) -> SourceSurface:
    return SourceSurface(
        source_surface_ref=ref,
        name=ref.value,
        paths=paths,
        owned_by=OwnerSeatRef(value="seat.worker.implementation"),
        acceptance_refs=acceptance_refs,
        required_tests=(RequiredTestRef(value="pytest.v2-100e"),),
    )


def _command(command_id: str, command: tuple[str, ...]) -> PackageCommand:
    return PackageCommand(
        command_id=ContractId(value=command_id),
        label=command_id,
        command=command,
        cwd=".",
    )


def _workspace_manifest():
    return build_workspace_manifest(
        workflow_ref=WorkflowRef(value="workflow.v2-100e"),
        workspace_root=WorkspacePath(value="workspaces/v2-100e"),
        package_contract=_package_contract(),
    )


def _package_assembly():
    return assemble_package(
        workspace_manifest=_workspace_manifest(),
        package_contract=_package_contract(),
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
                source_surface_refs=(RUN_MANIFEST_SURFACE_REF, ENV_RUN_MANIFEST_SURFACE_REF),
                acceptance_refs=(ACCEPTANCE_REF, PERSISTENCE_ACCEPTANCE_REF, TEST_INSTRUCTIONS_ACCEPTANCE_REF),
            ),
            PackageArtifact(
                relative_path=PackageArtifactPath(value="app/main.py"),
                artifact_kind=PackageArtifactKind.SOURCE,
                source_surface_refs=(SOURCE_SURFACE_REF,),
                acceptance_refs=(ACCEPTANCE_REF, LIST_ACCEPTANCE_REF, PERSISTENCE_ACCEPTANCE_REF),
            ),
            PackageArtifact(
                relative_path=PackageArtifactPath(value="tests/test_books.py"),
                artifact_kind=PackageArtifactKind.TEST,
                source_surface_refs=(TEST_SURFACE_REF,),
                acceptance_refs=(ACCEPTANCE_REF, TEST_INSTRUCTIONS_ACCEPTANCE_REF),
            ),
            PackageArtifact(
                relative_path=PackageArtifactPath(value="tests/probes/books.json"),
                artifact_kind=PackageArtifactKind.TEST,
                source_surface_refs=(BEHAVIORAL_PROBE_SURFACE_REF,),
                acceptance_refs=(ACCEPTANCE_REF, LIST_ACCEPTANCE_REF),
            ),
            PackageArtifact(
                relative_path=PackageArtifactPath(value="docs/api.md"),
                artifact_kind=PackageArtifactKind.DOC,
                source_surface_refs=(SOURCE_SURFACE_REF,),
                acceptance_refs=(ACCEPTANCE_REF, LIST_ACCEPTANCE_REF),
            ),
            PackageArtifact(
                relative_path=PackageArtifactPath(value="audit/process-timeline.md"),
                artifact_kind=PackageArtifactKind.DOC,
                source_surface_refs=(CLOSEOUT_AUDIT_SURFACE_REF,),
                acceptance_refs=(
                    ACCEPTANCE_REF,
                    LIST_ACCEPTANCE_REF,
                    PERSISTENCE_ACCEPTANCE_REF,
                    TEST_INSTRUCTIONS_ACCEPTANCE_REF,
                ),
            ),
        ),
    )


def _run_manifest() -> RunManifest:
    return build_run_manifest(
        workspace_manifest=_workspace_manifest(),
        package_contract=_package_contract(),
        service_contracts=(
            RunManifestServiceContract(
                command_id=ContractId(value="run-api"),
                role="backend-api",
                env_bindings=(
                    RunManifestEnvironmentBinding(
                        name="HOST",
                        value_source=RunManifestEnvironmentValueSource.RUNTIME_HOST,
                    ),
                    RunManifestEnvironmentBinding(
                        name="PORT",
                        value_source=RunManifestEnvironmentValueSource.RUNTIME_PORT,
                    ),
                    RunManifestEnvironmentBinding(
                        name="LIBRARY_DB_PATH",
                        value_source=RunManifestEnvironmentValueSource.TEMP_SQLITE_PATH,
                    ),
                ),
                readiness_probe=RunManifestReadinessProbe(method="GET", path="/health", expect_status=200),
            ),
            RunManifestServiceContract(
                command_id=ContractId(value="run-frontend"),
                role="frontend-ui",
                env_bindings=(
                    RunManifestEnvironmentBinding(
                        name="FRONTEND_PORT",
                        value_source=RunManifestEnvironmentValueSource.RUNTIME_PORT,
                    ),
                ),
                readiness_probe=RunManifestReadinessProbe(method="GET", path="/", expect_status=200),
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
                        json_body={"title": "Dune", "author": "Frank Herbert"},
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


def _recheck_input(
    *,
    attempt_id: ReworkAttemptId,
    graph_version: int,
    include_live_evidence: bool,
    failed_blocker: bool,
    package_root: Path,
    provider_attempt_ref: ProviderAttemptRef = PROVIDER_ATTEMPT_REF,
    rework_plan_ref: ReworkPlanId = REWORK_PLAN_REF,
    source_prefix: str = "rework-evidence",
) -> ReworkEvidenceRecheckInput:
    namespace = ReworkEvidenceNamespace(
        run_id=RUN_ID,
        cycle_id=CYCLE_ID,
        rework_attempt_id=attempt_id,
        graph_version=graph_version,
        config_hash_refs=("config-hash.roles.v2-100e", "config-hash.runtime.v2-100e"),
    )
    namespace_ref = rework_evidence_namespace_ref(namespace)
    evidence_results = _evidence_results(
        namespace_ref.value,
        include_live=include_live_evidence,
        provider_attempt_ref=provider_attempt_ref,
        source_prefix=source_prefix,
    )
    return ReworkEvidenceRecheckInput(
        attempt=_rework_attempt(
            attempt_id,
            provider_attempt_ref=provider_attempt_ref,
            rework_plan_ref=rework_plan_ref,
        ),
        namespace=namespace,
        active_acceptance_contract=_acceptance_contract(),
        active_package_contract=_package_contract(),
        package_assembly=_package_assembly(),
        package_commit_ref=PackageCommitRef(value=f"package-commit.{FINAL_COMMIT_SHA}"),
        source_files=_source_files(package_root),
        source_lineage_records=_source_lineage_records(
            evidence_results,
            provider_attempt_ref=provider_attempt_ref,
        ),
        evidence_verification_results=evidence_results,
        failed_final_evidence_blockers=(
            (_failed_behavioral_probe_blocker(namespace) if failed_blocker else None),
        )
        if failed_blocker
        else (),
        target_blocker_refs=(TARGET_BLOCKER_REF,),
        work_product=_work_product(provider_attempt_ref=provider_attempt_ref),
        source_diff_ref=SourceDiffRef(value=f"source-diff.{attempt_id.value}"),
        run_manifest=_run_manifest(),
        environment_usage=(
            ReworkEnvironmentUsage(
                source_ref="source-file.backend.app",
                env_names=("HOST", "PORT", "LIBRARY_DB_PATH"),
            ),
        ),
        checked_at=NOW,
        closeout_context=None,
    )


def _with_closeout_context(recheck_input: ReworkEvidenceRecheckInput) -> ReworkEvidenceRecheckInput:
    from boardroom_os.rework.evidence import (
        build_rework_checker_verdict,
        build_rework_final_evidence_table,
        build_rework_source_inventory,
    )

    source_inventory = build_rework_source_inventory(recheck_input)
    final_evidence_table = build_rework_final_evidence_table(recheck_input)
    checker_verdict = build_rework_checker_verdict(recheck_input, final_evidence_table)
    closeout_input = _closeout_gate_input(
        recheck_input=recheck_input,
        source_inventory=source_inventory,
        final_evidence_table=final_evidence_table,
        checker_verdict=checker_verdict,
    )
    return recheck_input.model_copy(
        update={
            "closeout_context": ReworkCloseoutRecheckContext(closeout_input=closeout_input),
        }
    )


def _closeout_gate_input(
    *,
    recheck_input: ReworkEvidenceRecheckInput,
    source_inventory,
    final_evidence_table,
    checker_verdict,
) -> CloseoutGateInput:
    namespace_value = rework_evidence_namespace_ref(recheck_input.namespace).value
    verification_run = _closeout_verification_run(recheck_input)
    service_runs = _service_runs(namespace_value)
    verified_evidence = _verified_tuple(recheck_input)
    live_blackbox_evidence = _closeout_live_blackbox_evidence(recheck_input)
    workspace_evidence_bundle = build_workspace_evidence_bundle(
        workspace_manifest=_workspace_manifest(),
        package_assembly=recheck_input.package_assembly,
        source_inventory=source_inventory,
        run_manifest=recheck_input.run_manifest,
        verification_runs=(verification_run,),
        service_runs=service_runs,
        live_blackbox_evidence=live_blackbox_evidence,
        verified_evidence=verified_evidence,
        final_evidence_table=final_evidence_table,
    )
    command_bindings = _closeout_command_bindings(
        recheck_input=recheck_input,
        verification_run=verification_run,
        service_runs=service_runs,
    )
    return CloseoutGateInput(
        package_contract=recheck_input.active_package_contract,
        source_inventory=source_inventory,
        run_manifest=recheck_input.run_manifest,
        workspace_evidence_bundle=workspace_evidence_bundle,
        final_evidence_table=final_evidence_table,
        checker_verdict=checker_verdict,
        verification_runs=(verification_run,),
        service_run_evidence=service_runs,
        verified_evidence=verified_evidence,
        provider_attempt_refs=recheck_input.attempt.provider_attempt_refs,
        final_command_bindings=command_bindings,
        replay_readiness=ReplayBundleReadiness(
            replay_passed=True,
            summary_hash=_sha256_text(f"{namespace_value}:replay-summary"),
            event_range=f"events.{RUN_ID.value}.0041-0051",
            projection_versions=("rework-reducer.v2-100e", "closeout-gate.v2-100e"),
            hash_chain_verified=True,
            payload_sha256_verified=True,
            payload_manifest_ref=f"payload-manifest.{namespace_value}",
            payload_manifest_hash=_sha256_text(f"{namespace_value}:payload-manifest"),
        ),
        git_audit_readiness=GitAuditReadiness(
            git_clean=True,
            final_commit_sha=FINAL_COMMIT_SHA,
            source_inventory_hash=_sha256_text(source_inventory.model_dump_json()),
            source_inventory_hash_matches=True,
            final_command_evidence_at_final_commit=True,
        ),
        process_audit_readiness=ProcessAuditReadiness(
            artifact_paths=(
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
            ),
            all_artifacts_present=True,
            timeline_key_events_present=True,
            agent_context_index_complete=True,
            artifact_lineage_complete=True,
            evidence_map_consistent_with_final_table=True,
        ),
    )


def _verified_tuple(recheck_input: ReworkEvidenceRecheckInput) -> tuple[VerifiedEvidence, ...]:
    return tuple(
        result.verified_evidence
        for result in recheck_input.evidence_verification_results
        if result.verified_evidence is not None
    )


def _closeout_verification_run(recheck_input: ReworkEvidenceRecheckInput) -> VerificationRun:
    namespace_value = rework_evidence_namespace_ref(recheck_input.namespace).value
    command = next(command for command in recheck_input.run_manifest.commands if command.kind is RunManifestCommandKind.TEST)
    verification_run_ref = _verification_run_ref_from_evidence(recheck_input)
    return VerificationRun(
        verification_run_id=verification_run_ref,
        execution_package_ref=EXECUTION_PACKAGE_REF,
        ticket_ref=TICKET_REF,
        command_id=command.command_id,
        command=command.command,
        cwd=command.cwd,
        exit_code=0,
        status=VerificationRunStatus.PASSED,
        stdout_ref=CommandOutputRef(value=f"command-output.{namespace_value}.{command.command_id.value}.stdout"),
        stderr_ref=CommandOutputRef(value=f"command-output.{namespace_value}.{command.command_id.value}.stderr"),
        duration_ms=0,
        started_at=NOW,
        finished_at=NOW,
        runner_ref=RunnerRef(value="runner.v2-100e.closeout"),
        environment_profile_ref=EnvironmentProfileRef(value="environment.v2-100e.closeout"),
        workspace_snapshot_ref=WorkspaceSnapshotRef(value=f"workspace-snapshot.{namespace_value}.closeout"),
    )


def _verification_run_ref_from_evidence(recheck_input: ReworkEvidenceRecheckInput) -> VerificationRunRef:
    refs = tuple(
        run_ref
        for evidence in _verified_tuple(recheck_input)
        for run_ref in evidence.verification_run_refs
    )
    if not refs:
        raise ValueError("closeout context requires verification_run_refs in verified evidence")
    return sorted(refs, key=lambda ref: ref.value)[0]


def _closeout_live_blackbox_evidence(
    recheck_input: ReworkEvidenceRecheckInput,
) -> tuple[LiveBlackboxIntegrationEvidence, ...]:
    refs = tuple(
        ref.value
        for result in recheck_input.evidence_verification_results
        if result.verified_evidence is not None
        for ref in result.verified_evidence.live_blackbox_evidence_refs
    )
    if not refs:
        return ()
    namespace_value = rework_evidence_namespace_ref(recheck_input.namespace).value
    evidence = _live_blackbox_evidence(
        namespace_value,
        suffix="closeout.live",
        acceptance_refs=(ACCEPTANCE_REF, LIST_ACCEPTANCE_REF),
    )
    if evidence.live_blackbox_evidence_id.value in refs:
        return (evidence,)
    return tuple(
        _live_blackbox_evidence(
            namespace_value,
            suffix=_live_blackbox_suffix_from_ref(namespace_value, ref),
            acceptance_refs=(ACCEPTANCE_REF, LIST_ACCEPTANCE_REF),
        )
        for ref in refs
    )


def _live_blackbox_suffix_from_ref(namespace_value: str, ref_value: str) -> str:
    prefix = f"live-blackbox.{namespace_value}."
    if not ref_value.startswith(prefix):
        raise ValueError("live blackbox evidence ref namespace mismatch")
    return ref_value.removeprefix(prefix)


def _closeout_command_bindings(
    *,
    recheck_input: ReworkEvidenceRecheckInput,
    verification_run: VerificationRun,
    service_runs: tuple[ServiceRunEvidence, ...],
) -> tuple[CloseoutCommandEvidenceBinding, ...]:
    bindings_by_command = {
        binding.command_id.value: binding
        for command in recheck_input.run_manifest.commands
        for binding in (
            validate_run_manifest_binding(
                run_manifest=recheck_input.run_manifest,
                package_contract=recheck_input.active_package_contract,
                command_id=command.command_id,
            ),
        )
    }
    service_by_command = {service.command_id.value: service for service in service_runs}
    bindings: list[CloseoutCommandEvidenceBinding] = []
    for command in recheck_input.run_manifest.commands:
        binding = bindings_by_command[command.command_id.value]
        if command.kind is RunManifestCommandKind.TEST:
            verification_run_ref = verification_run.verification_run_id
        else:
            verification_run_ref = VerificationRunRef(value=service_by_command[command.command_id.value].service_run_evidence_id.value)
        bindings.append(
            CloseoutCommandEvidenceBinding(
                verification_run_ref=verification_run_ref,
                run_manifest_ref=binding.run_manifest_ref,
                package_contract_ref=binding.package_contract_ref,
                command_id=binding.command_id,
                binding_kind=binding.kind,
            )
        )
    return tuple(bindings)


def _rework_attempt(
    attempt_id: ReworkAttemptId,
    *,
    provider_attempt_ref: ProviderAttemptRef = PROVIDER_ATTEMPT_REF,
    rework_plan_ref: ReworkPlanId = REWORK_PLAN_REF,
) -> ReworkAttempt:
    return ReworkAttempt(
        rework_attempt_id=attempt_id,
        cycle_id=CYCLE_ID,
        rework_plan_ref=rework_plan_ref,
        ticket_ref=TICKET_REF,
        execution_package_ref=EXECUTION_PACKAGE_REF,
        actor_ref="seat.worker.implementation",
        provider_attempt_refs=(provider_attempt_ref,),
        workspace_mutation_refs=(f"workspace-mutation.{attempt_id.value}.source",),
        command_evidence_refs=(f"verification-run.{attempt_id.value}.pytest",),
        source_lineage_refs=(f"source-lineage.{attempt_id.value}.app",),
        run_manifest_ref=_run_manifest().run_manifest_id.value,
        submitted_at=NOW,
    )


def _work_product(*, provider_attempt_ref: ProviderAttemptRef = PROVIDER_ATTEMPT_REF) -> WorkProduct:
    return WorkProduct(
        work_product_id=WorkProductRef(value="work-product.v2-100e.backend"),
        execution_package_ref=EXECUTION_PACKAGE_REF,
        ticket_ref=TICKET_REF,
        producer_attempt_ref=provider_attempt_ref,
        artifact_refs=("artifact.v2-100e.app", "artifact.v2-100e.tests"),
        claim_refs=("claim.v2-100e.book.add",),
        summary="Current rework attempt updates implementation and verification evidence.",
    )


def _source_files(package_root: Path) -> tuple[SourceFileRecord, ...]:
    paths = (
        "app/main.py",
        "tests/test_books.py",
        "tests/probes/books.json",
        "docs/api.md",
        "audit/process-timeline.md",
    )
    return tuple(
        SourceFileRecord(
            path=SourceFilePath(value=relative_path),
            sha256=ArtifactSha256(value=_sha256_file(package_root / relative_path)),
        )
        for relative_path in paths
    )


def _sha256_file(path: Path) -> str:
    if not path.exists() or not path.is_file():
        raise ValueError(f"source file is required for V2-100E source inventory: {path}")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _evidence_results(
    namespace_value: str,
    *,
    include_live: bool,
    provider_attempt_ref: ProviderAttemptRef = PROVIDER_ATTEMPT_REF,
    source_prefix: str = "rework-evidence",
) -> tuple[EvidenceVerificationResult, ...]:
    results = [
        EvidenceVerificationResult(
            verified_evidence=_verified_evidence(
                namespace_value,
                suffix="source",
                source_kind=EvidenceClaimSourceKind.WORK_PRODUCT,
                required_artifact_type="source",
                provider_attempt_ref=provider_attempt_ref,
                source_prefix=source_prefix,
            )
        ),
        _verified_command_run_result(
            namespace_value,
            suffix="test",
            required_artifact_type="test",
            acceptance_refs=(ACCEPTANCE_REF,),
            source_surface_refs=(TEST_SURFACE_REF,),
            provider_attempt_ref=provider_attempt_ref,
            source_prefix=source_prefix,
        ),
    ]
    if include_live:
        results.append(
            _verified_live_blackbox_result(
                namespace_value,
                suffix="live",
                required_artifact_type="live_blackbox",
                acceptance_refs=(ACCEPTANCE_REF,),
                source_surface_refs=(SOURCE_SURFACE_REF, TEST_SURFACE_REF),
                provider_attempt_ref=provider_attempt_ref,
                source_prefix=source_prefix,
            )
        )
        results.append(
            _verified_live_blackbox_result(
                namespace_value,
                suffix="list.live",
                required_artifact_type="live_blackbox",
                acceptance_refs=(LIST_ACCEPTANCE_REF,),
                source_surface_refs=(SOURCE_SURFACE_REF, BEHAVIORAL_PROBE_SURFACE_REF),
                provider_attempt_ref=provider_attempt_ref,
                source_prefix=source_prefix,
            )
        )
        results.append(
            EvidenceVerificationResult(
                verified_evidence=_verified_evidence(
                    namespace_value,
                    suffix="persistence.run_manifest",
                    source_kind=EvidenceClaimSourceKind.WORK_PRODUCT,
                    required_artifact_type="run_manifest",
                    acceptance_refs=(PERSISTENCE_ACCEPTANCE_REF,),
                    source_surface_refs=(SOURCE_SURFACE_REF, ENV_RUN_MANIFEST_SURFACE_REF),
                    provider_attempt_ref=provider_attempt_ref,
                    source_prefix=source_prefix,
                )
            )
        )
        results.append(
            _verified_command_run_result(
                namespace_value,
                suffix="instructions.test",
                required_artifact_type="test",
                acceptance_refs=(TEST_INSTRUCTIONS_ACCEPTANCE_REF,),
                source_surface_refs=(TEST_SURFACE_REF, ENV_RUN_MANIFEST_SURFACE_REF),
                provider_attempt_ref=provider_attempt_ref,
                source_prefix=source_prefix,
            )
        )
    return tuple(results)


def _verified_command_run_result(
    namespace_value: str,
    *,
    suffix: str,
    required_artifact_type: str,
    acceptance_refs: tuple[AcceptanceRef, ...],
    source_surface_refs: tuple[SourceSurfaceRef, ...],
    provider_attempt_ref: ProviderAttemptRef = PROVIDER_ATTEMPT_REF,
    source_prefix: str = "rework-evidence",
) -> EvidenceVerificationResult:
    package_root = _command_fixture_package_root(namespace_value)
    _write_minimal_package(package_root)
    runner_result = CommandRunner().run(
        CommandRunnerInput(
            execution_package=_execution_package(),
            package_contract=_package_contract(),
            command_id=ContractId(value="test-api"),
            package_root=package_root,
            runner_ref=RunnerRef(value="runner.v2-100e.local"),
            environment_profile_ref=EnvironmentProfileRef(value="env.v2-100e.local"),
            workspace_snapshot_ref=WorkspaceSnapshotRef(value=f"workspace-snapshot.{namespace_value}.{suffix}"),
        )
    )
    run = runner_result.verification_run
    obligation = EvidenceObligation(
        evidence_obligation_id=EvidenceObligationRef(value=f"evidence-obligation.{namespace_value}.{suffix}"),
        acceptance_refs=acceptance_refs,
        source_surface_refs=source_surface_refs,
        required_artifact_type=RequiredArtifactType(value=required_artifact_type),
        required_verifier=RequiredVerifier(value="command_runner"),
        blocking=True,
    )
    claim = build_evidence_claim_from_verification_run(
        verification_run=run,
        evidence_obligation=obligation,
        producer_attempt_ref=provider_attempt_ref,
        acceptance_refs=acceptance_refs,
        source_surface_refs=source_surface_refs,
        expected_purpose=EvidencePurpose.IMPLEMENTATION,
        summary=f"Verified command evidence for {suffix}.",
    )
    result = EvidenceVerifier().verify(
        EvidenceVerificationInput(
            claim=claim,
            evidence_obligation=obligation,
            active_acceptance_contract=_acceptance_contract(),
            active_package_contract=_package_contract(),
            artifact_manifest=_verification_run_manifest(
                runner_result,
                provider_attempt_ref=provider_attempt_ref,
            ),
            purpose_policy=EvidencePurposePolicy(
                rules=(
                    EvidencePurposeRule(
                        required_artifact_type=RequiredArtifactType(value=required_artifact_type),
                        allowed_purposes=(EvidencePurpose.IMPLEMENTATION,),
                    ),
                )
            ),
            provider_attempts=(_provider_attempt(provider_attempt_ref=provider_attempt_ref),),
            execution_packages=(_execution_package(),),
            role_prompt_hook_registry=build_baseline_role_prompt_hook_registry(),
            verification_runs=(run,),
            verified_at=NOW,
        )
    )
    if not result.success:
        messages = "; ".join(blocker.message for blocker in result.blockers)
        raise ValueError(f"command evidence verification failed: {messages}")
    return result


def _verified_live_blackbox_result(
    namespace_value: str,
    *,
    suffix: str,
    required_artifact_type: str,
    acceptance_refs: tuple[AcceptanceRef, ...],
    source_surface_refs: tuple[SourceSurfaceRef, ...],
    provider_attempt_ref: ProviderAttemptRef = PROVIDER_ATTEMPT_REF,
    source_prefix: str = "rework-evidence",
) -> EvidenceVerificationResult:
    evidence = _live_blackbox_evidence(
        namespace_value,
        suffix=suffix,
        acceptance_refs=acceptance_refs,
    )
    obligation = EvidenceObligation(
        evidence_obligation_id=EvidenceObligationRef(value=f"evidence-obligation.{namespace_value}.{suffix}"),
        acceptance_refs=acceptance_refs,
        source_surface_refs=source_surface_refs,
        required_artifact_type=RequiredArtifactType(value=required_artifact_type),
        required_verifier=RequiredVerifier(value="live_blackbox"),
        blocking=True,
    )
    claim = build_evidence_claim_from_live_blackbox(
        evidence=evidence,
        evidence_obligation=obligation,
        producer_attempt_ref=provider_attempt_ref,
        expected_purpose=EvidencePurpose.IMPLEMENTATION,
        summary=f"Verified live blackbox evidence for {suffix}.",
    )
    result = EvidenceVerifier().verify(
        EvidenceVerificationInput(
            claim=claim,
            evidence_obligation=obligation,
            active_acceptance_contract=_acceptance_contract(),
            active_package_contract=_package_contract(),
                artifact_manifest=_live_blackbox_manifest(
                    claim=claim,
                    evidence=evidence,
                    artifact_type=required_artifact_type,
                    provider_attempt_ref=provider_attempt_ref,
                ),
            purpose_policy=EvidencePurposePolicy(
                rules=(
                    EvidencePurposeRule(
                        required_artifact_type=RequiredArtifactType(value=required_artifact_type),
                        allowed_purposes=(EvidencePurpose.IMPLEMENTATION,),
                    ),
                )
            ),
            provider_attempts=(_provider_attempt(provider_attempt_ref=provider_attempt_ref),),
            execution_packages=(_execution_package(),),
            role_prompt_hook_registry=build_baseline_role_prompt_hook_registry(),
            service_runs=_service_runs(namespace_value),
            live_blackbox_evidence=(evidence,),
            verified_at=NOW,
        )
    )
    if not result.success:
        messages = "; ".join(blocker.message for blocker in result.blockers)
        raise ValueError(f"live blackbox evidence verification failed: {messages}")
    return result


def _verification_run_manifest(
    runner_result,
    *,
    provider_attempt_ref: ProviderAttemptRef = PROVIDER_ATTEMPT_REF,
) -> ArtifactManifest:
    run = runner_result.verification_run
    return ArtifactManifest(
        entries=(
            ArtifactManifestEntry(
                artifact_ref=EvidenceArtifactRef(value=run.stdout_ref.value),
                sha256=ArtifactSha256(value=_sha256_text(runner_result.stdout)),
                producer_attempt_ref=provider_attempt_ref,
                source_ref=run.verification_run_id.value,
                artifact_kind="command_stdout",
            ),
            ArtifactManifestEntry(
                artifact_ref=EvidenceArtifactRef(value=run.stderr_ref.value),
                sha256=ArtifactSha256(value=_sha256_text(runner_result.stderr)),
                producer_attempt_ref=provider_attempt_ref,
                source_ref=run.verification_run_id.value,
                artifact_kind="command_stderr",
            ),
        )
    )


def _live_blackbox_evidence(
    namespace_value: str,
    *,
    suffix: str,
    acceptance_refs: tuple[AcceptanceRef, ...],
) -> LiveBlackboxIntegrationEvidence:
    evidence_ref = LiveBlackboxIntegrationEvidenceRef(value=f"live-blackbox.{namespace_value}.{suffix}")
    probe_ref = f"probe.{suffix}"
    service_runs = _service_runs(namespace_value)
    return LiveBlackboxIntegrationEvidence(
        live_blackbox_evidence_id=evidence_ref,
        package_contract_ref=PACKAGE_CONTRACT_REF,
        backend_command_id=ContractId(value="run-api"),
        frontend_command_id=ContractId(value="run-frontend"),
        backend_service_run_ref=service_runs[0].service_run_evidence_id,
        frontend_service_run_ref=service_runs[1].service_run_evidence_id,
        probes=(
            LiveBlackboxProbeResult(
                probe_ref=probe_ref,
                acceptance_refs=acceptance_refs,
                service_run_refs=(
                    service_runs[0].service_run_evidence_id,
                    service_runs[1].service_run_evidence_id,
                ),
                command_ids=(ContractId(value="run-api"), ContractId(value="run-frontend")),
                probe_url=ServiceReadinessUrl(value="http://127.0.0.1:5173/"),
                status_code=200,
                passed=True,
                observed_facts={"response_shape_matches_contract": True, "used_synthetic_fetch": False},
                body_sha256=Sha256Hex(value=_sha256_text(f"{namespace_value}:{suffix}:body")),
                probed_at=NOW,
            ),
        ),
        generated_at=NOW,
    )


def _service_runs(namespace_value: str) -> tuple[ServiceRunEvidence, ServiceRunEvidence]:
    return (
        _service_run(
            namespace_value,
            service_ref="backend",
            command_id="run-api",
            command=("python", "-m", "app.main"),
            readiness_url="http://127.0.0.1:8000/health",
        ),
        _service_run(
            namespace_value,
            service_ref="frontend",
            command_id="run-frontend",
            command=("python", "-c", "print('frontend ready')"),
            readiness_url="http://127.0.0.1:5173/",
        ),
    )


def _service_run(
    namespace_value: str,
    *,
    service_ref: str,
    command_id: str,
    command: tuple[str, ...],
    readiness_url: str,
) -> ServiceRunEvidence:
    service_run_ref = ServiceRunEvidenceRef(value=f"service-run.{namespace_value}.{service_ref}")
    return ServiceRunEvidence(
        service_run_evidence_id=service_run_ref,
        execution_package_ref=EXECUTION_PACKAGE_REF,
        ticket_ref=TICKET_REF,
        command_id=ContractId(value=command_id),
        command=command,
        cwd=".",
        process_id=4321 if service_ref == "backend" else 4322,
        readiness_url=ServiceReadinessUrl(value=readiness_url),
        probe_status_code=200,
        probe_body_sha256=Sha256Hex(value=_sha256_text(f"{namespace_value}:{service_ref}:ready")),
        stdout_ref=CommandOutputRef(value=f"command-output.{service_run_ref.value}.stdout"),
        stderr_ref=CommandOutputRef(value=f"command-output.{service_run_ref.value}.stderr"),
        started_at=NOW,
        ready_at=NOW,
        runner_ref=RunnerRef(value="runner.v2-100e.service"),
        environment_profile_ref=EnvironmentProfileRef(value="env.v2-100e.service"),
        workspace_snapshot_ref=WorkspaceSnapshotRef(value=f"workspace-snapshot.{namespace_value}.{service_ref}"),
    )


def _live_blackbox_manifest(
    *,
    claim,
    evidence: LiveBlackboxIntegrationEvidence,
    artifact_type: str,
    provider_attempt_ref: ProviderAttemptRef = PROVIDER_ATTEMPT_REF,
) -> ArtifactManifest:
    return ArtifactManifest(
        entries=tuple(
            ArtifactManifestEntry(
                artifact_ref=artifact_ref,
                sha256=ArtifactSha256(value=_sha256_text(f"{evidence.live_blackbox_evidence_id.value}:{artifact_ref.value}")),
                producer_attempt_ref=provider_attempt_ref,
                source_ref=evidence.live_blackbox_evidence_id.value,
                artifact_kind=f"{artifact_type}_{index}",
            )
            for index, artifact_ref in enumerate(claim.artifact_refs, start=1)
        )
    )


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _provider_attempt(
    *,
    provider_attempt_ref: ProviderAttemptRef = PROVIDER_ATTEMPT_REF,
) -> ProviderAttempt:
    hook = build_baseline_role_prompt_hook_registry().require(
        RolePromptHookRef(value="role-prompt-hook.baseline.worker.v1")
    )
    return ProviderAttempt(
        provider_attempt_id=provider_attempt_ref,
        provider="openai-compatible",
        model="gpt-5.5",
        reasoning_effort="high",
        input_package_ref=EXECUTION_PACKAGE_REF,
        seat_ref=AgentSeatRef(value="seat.worker.implementation"),
        role_prompt_hook_ref=hook.hook_ref,
        role_prompt_hook_version=hook.hook_version,
        role_prompt_hook_sha256=hook.content_sha256,
        status=ProviderAttemptStatus.SUCCEEDED,
        outcome=ProviderAttemptOutcome.PRIMARY_PROVIDER_OUTPUT,
        started_at=NOW,
        finished_at=NOW,
        raw_output_ref=ProviderArtifactRef(value="provider-artifact.v2-100e.worker.raw"),
        parsed_output_ref=ProviderArtifactRef(value="provider-artifact.v2-100e.worker.parsed"),
    )


def _execution_package() -> ExecutionPackage:
    hook = build_baseline_role_prompt_hook_registry().require(
        RolePromptHookRef(value="role-prompt-hook.baseline.worker.v1")
    )
    return ExecutionPackage(
        execution_package_id=EXECUTION_PACKAGE_REF.value,
        ticket_ref=TICKET_REF,
        graph_version=40,
        seat_ref="seat.worker.implementation",
        model_execution_profile=ModelExecutionProfile(
            model_execution_profile_id="model.v2-100e.worker",
            provider="openai-compatible",
            model="gpt-5.5",
            reasoning_effort="high",
            context_window=400000,
            temperature=0.2,
            tool_permissions=("filesystem.write",),
            fallback_policy_ref=ContractId(value="fallback.v2-100e.record_failure"),
        ),
        role_prompt_hook=hook,
        objective="Produce rework evidence for the V2-100E fixture.",
        context_refs=("context.v2-100e.rework",),
        constraints=("Do not use fallback evidence.",),
        acceptance_refs=(ACCEPTANCE_REF,),
        source_surface_refs=(SOURCE_SURFACE_REF, TEST_SURFACE_REF),
        allowed_write_set=("app/main.py", "tests/test_books.py"),
        required_outputs=("work-product.v2-100e.backend",),
        commands=(_command("test-api", ("python", "-c", "print('v2-100e fixture ok')")),),
        evidence_obligations=(
            EvidenceObligation(
                evidence_obligation_id=EVIDENCE_OBLIGATION_REF,
                acceptance_refs=(ACCEPTANCE_REF,),
                source_surface_refs=(SOURCE_SURFACE_REF, TEST_SURFACE_REF),
                required_artifact_type=RequiredArtifactType(value="test"),
                required_verifier=RequiredVerifier(value="command_runner"),
                blocking=True,
            ),
        ),
        fallback_policy_ref="fallback.v2-100e.record_failure",
        audit_requirements=("provider_attempt_hook_snapshot_binding",),
    )


def _command_fixture_package_root(namespace_value: str) -> Path:
    safe = namespace_value.replace("/", "_").replace(":", "_")
    return Path(".tmp/v2-100e-command-fixtures") / safe


def _verified_evidence(
    namespace_value: str,
    *,
    suffix: str,
    source_kind: EvidenceClaimSourceKind,
    required_artifact_type: str,
    acceptance_refs: tuple[AcceptanceRef, ...] = (ACCEPTANCE_REF,),
    source_surface_refs: tuple[SourceSurfaceRef, ...] = (SOURCE_SURFACE_REF, TEST_SURFACE_REF),
    provider_attempt_ref: ProviderAttemptRef = PROVIDER_ATTEMPT_REF,
    source_prefix: str = "rework-evidence",
) -> VerifiedEvidence:
    evidence_ref = f"verified-evidence.{source_prefix}.{namespace_value}.{suffix}"
    return VerifiedEvidence(
        verified_evidence_id=evidence_ref,
        evidence_claim_ref=EvidenceClaimRef(value=f"claim.{evidence_ref}"),
        evidence_obligation_ref=EVIDENCE_OBLIGATION_REF,
        producer_attempt_ref=provider_attempt_ref,
        source_kind=source_kind,
        source_ref=f"{source_prefix}.{source_kind.value}.{namespace_value}.{suffix}",
        expected_purpose=EvidencePurpose.IMPLEMENTATION,
        required_artifact_type=RequiredArtifactType(value=required_artifact_type),
        acceptance_refs=acceptance_refs,
        source_surface_refs=source_surface_refs,
        verified_artifacts=(
            VerifiedArtifact(
                artifact_ref=EvidenceArtifactRef(value=f"artifact.{namespace_value}.{suffix}"),
                sha256=ArtifactSha256(
                    value=_sha256_text(f"{namespace_value}:{suffix}:{required_artifact_type}")
                ),
                producer_attempt_ref=provider_attempt_ref,
                source_ref=f"artifact-source.{suffix}",
                artifact_kind=required_artifact_type,
            ),
        ),
        verification_run_refs=(),
        fallback_decision_record_ref=FallbackDecisionRecordRef(value=f"fallback-decision.{namespace_value}.none"),
        verified_at=NOW,
    )


def _source_lineage_records(
    evidence_results: tuple[EvidenceVerificationResult, ...],
    *,
    provider_attempt_ref: ProviderAttemptRef = PROVIDER_ATTEMPT_REF,
) -> tuple[SourceLineageRecord, ...]:
    evidence_refs = tuple(
        result.verified_evidence.verified_evidence_id
        for result in evidence_results
        if result.verified_evidence is not None
    )
    return (
        SourceLineageRecord(
            path=SourceFilePath(value="app/main.py"),
            source_surface_ref=SOURCE_SURFACE_REF,
            producer_ticket_ref=TICKET_REF,
            producer_attempt_ref=provider_attempt_ref,
            consumer_ticket_refs=(TICKET_REF,),
            acceptance_refs=(ACCEPTANCE_REF, LIST_ACCEPTANCE_REF, PERSISTENCE_ACCEPTANCE_REF),
            evidence_refs=evidence_refs,
        ),
        SourceLineageRecord(
            path=SourceFilePath(value="tests/test_books.py"),
            source_surface_ref=TEST_SURFACE_REF,
            producer_ticket_ref=TICKET_REF,
            producer_attempt_ref=provider_attempt_ref,
            consumer_ticket_refs=(TICKET_REF,),
            acceptance_refs=(ACCEPTANCE_REF, TEST_INSTRUCTIONS_ACCEPTANCE_REF),
            evidence_refs=evidence_refs,
        ),
        SourceLineageRecord(
            path=SourceFilePath(value="docs/api.md"),
            source_surface_ref=SOURCE_SURFACE_REF,
            producer_ticket_ref=TICKET_REF,
            producer_attempt_ref=provider_attempt_ref,
            consumer_ticket_refs=(TICKET_REF,),
            acceptance_refs=(ACCEPTANCE_REF, LIST_ACCEPTANCE_REF),
            evidence_refs=evidence_refs,
        ),
        SourceLineageRecord(
            path=SourceFilePath(value="tests/probes/books.json"),
            source_surface_ref=BEHAVIORAL_PROBE_SURFACE_REF,
            producer_ticket_ref=TICKET_REF,
            producer_attempt_ref=provider_attempt_ref,
            consumer_ticket_refs=(TICKET_REF,),
            acceptance_refs=(ACCEPTANCE_REF, LIST_ACCEPTANCE_REF),
            evidence_refs=evidence_refs,
        ),
        SourceLineageRecord(
            path=SourceFilePath(value="audit/process-timeline.md"),
            source_surface_ref=CLOSEOUT_AUDIT_SURFACE_REF,
            producer_ticket_ref=TICKET_REF,
            producer_attempt_ref=provider_attempt_ref,
            consumer_ticket_refs=(TICKET_REF,),
            acceptance_refs=(
                ACCEPTANCE_REF,
                LIST_ACCEPTANCE_REF,
                PERSISTENCE_ACCEPTANCE_REF,
                TEST_INSTRUCTIONS_ACCEPTANCE_REF,
            ),
            evidence_refs=evidence_refs,
        ),
    )


def _failed_behavioral_probe_blocker(namespace: ReworkEvidenceNamespace) -> FinalEvidenceBlocker:
    return FinalEvidenceBlocker(
        blocker_id=TARGET_BLOCKER_REF,
        code=FinalEvidenceBlockerCode.FAILED_EVIDENCE,
        message="Behavioral probe still observes the old response shape.",
        acceptance_ref=ACCEPTANCE_REF,
        related_ref=rework_evidence_namespace_ref(namespace).value,
        source="behavioral_probe",
    )


def _write_minimal_package(package_root: Path) -> None:
    files = {
        "app/main.py": "def create_book():\n    return {'book': {'id': 1}}\n",
        "tests/test_books.py": "def test_create_book():\n    assert True\n",
        "docs/api.md": "# API\n",
        "tests/probes/books.json": "{}\n",
        "audit/process-timeline.md": "# Timeline\n",
        "README.md": "# V2-100E fixture\n",
        "AGENTS.md": "# Fixture agent instructions\n",
        "package-contract.json": json.dumps(
            _package_contract().model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
        )
        + "\n",
        "run-manifest.json": json.dumps(
            _run_manifest().model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
        )
        + "\n",
    }
    for relative_path, content in files.items():
        path = package_root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


__all__ = [
    "DEFAULT_FAILURE_SUMMARY_PATH",
    "V2_100ResettableFixture",
    "build_accepted_round_input",
    "build_exhausted_round_provider",
    "build_two_round_provider",
    "build_v2_100_resettable_fixture",
    "build_v2_100_scenario_input",
    "replace_attempt",
    "replace_with_failed_behavioral_blocker_despite_passed_command",
    "replace_with_old_closeout_readiness_refs",
    "replace_with_previous_namespace_evidence",
]
