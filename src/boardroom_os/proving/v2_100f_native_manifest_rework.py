from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Mapping, Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from dataclasses import dataclass
from boardroom_os.agents.categories import RoleCategory
from boardroom_os.agents.policy import RoleProfileProjection
from boardroom_os.agents.profiles import (
    ModelExecutionProfile,
    ModelExecutionProfileId,
    ModelExecutionProfileRegistry,
    RoleProfile,
)
from boardroom_os.agents.role_prompt_hooks import build_baseline_role_prompt_hook_registry
from boardroom_os.agents.seat import (
    AgentSeat,
    AgentSeatRef,
    SeatLifecycleProjection,
    SeatLifecycleStatus,
)
from boardroom_os.agents.skills import CapabilityTag, RoleProfileId, SkillRef
from boardroom_os.agents.team import AgentTeamProjection
from boardroom_os.config.boardroom import BoardroomConfigPaths, load_boardroom_settings
from boardroom_os.contracts.acceptance import (
    AcceptanceContract,
    AcceptanceCriterion,
    EvidenceRequirement,
    VerificationStrategy,
)
from boardroom_os.contracts.evidence_obligation import (
    EvidenceObligation,
    RequiredArtifactType,
    RequiredVerifier,
)
from boardroom_os.contracts.hashes import Sha256Hex
from boardroom_os.contracts.package import (
    IntegrationBoundary,
    PackageCommand,
    PackageContract,
    PackageProjectType,
)
from boardroom_os.contracts.source_surface import OwnerSeatRef, RequiredTestRef, SourceSurface
from boardroom_os.contracts.types import (
    AcceptanceRef,
    ContractId,
    ContractStatus,
    EvidenceObligationRef,
    SourceSurfaceRef,
)
from boardroom_os.events.record import EventRecord
from boardroom_os.events.types import (
    ActorRef,
    EventId,
    EventPayloadRef,
    EventType,
    ProjectRef,
)
from boardroom_os.evidence.blackbox_plan import (
    BlackboxPlanAction,
    BlackboxPlanActionKind,
    BlackboxPlanApproval,
    BlackboxPlanApprovalRef,
    BlackboxVerificationPlan,
    BlackboxVerificationPlanRef,
    validate_blackbox_plan_lineage,
)
from boardroom_os.execution.blackbox_plan_runner import (
    BlackboxActionExecutorResult,
    BlackboxActionInputRefHash,
    BlackboxPlanRunner,
    BlackboxPlanRunnerInput,
    BlackboxPlanRunnerStatus,
    HttpActionExecutor,
)
from boardroom_os.execution.compiler import (
    ExecutionPackageCompiler,
    ExecutionPackageCompilerInput,
    ExecutionWorkspaceContext,
    VerificationExecutionContext,
)
from boardroom_os.execution.context_index import ProviderAttemptRef
from boardroom_os.execution.package import ContextRef, ExecutionPackage, ExecutionPackageRef
from boardroom_os.execution.provider_executor import ProviderExecutor, ProviderExecutorInput
from boardroom_os.execution.verification_run import (
    EnvironmentProfileRef,
    RunnerRef,
    WorkspaceSnapshotRef,
)
from boardroom_os.graph.projection import TicketGraphProjector
from boardroom_os.graph.seat_assignment import (
    SeatAssignmentPayload,
    SeatAssignmentProjector,
)
from boardroom_os.graph.ticket import TicketCreatedPayload, TicketId
from boardroom_os.orchestration.verification import (
    VerificationMilestoneRequest,
    VerifyBlackboxTicketIntent,
)
from boardroom_os.providers.attempt import (
    ProviderArtifactRef,
    ProviderAttempt,
    ProviderAttemptOutcome,
    ProviderAttemptStatus,
)
from boardroom_os.providers.adapter import ProviderRequest
from boardroom_os.providers.openai_adapter import FileProviderOutputStore, OpenAIProviderSettings, OpenAIProviderTransport
from boardroom_os.reducers.rework import (
    ReworkReducer,
    ReworkReducerPayloadResolver,
    ReworkRequestPayload,
)
from boardroom_os.rework.blocker_projection import (
    BlockerProjectionContext,
    ManifestReworkRoutingStatus,
    route_manifest_blackbox_facts,
)
from boardroom_os.rework.model import (
    ReworkActorKind,
    ReworkCycleId,
    RunId,
)
from boardroom_os.workspace.run_manifest_ingestion import ingest_run_manifest_artifact


EXPECTED_RUNTIME_CONFIG = "config/boardroom-runtime.v2-090f.yaml"
EXPECTED_PROVIDERS_CONFIG = "config/boardroom-providers.v2-090f.yaml"
EXPECTED_ROLES_CONFIG = "config/boardroom-roles.v2-090f.yaml"

PROJECT_REF = ProjectRef(value="project.v2-100f")
VERIFY_TICKET_ID = TicketId(value="ticket.verify-blackbox.generated")
ACCEPTANCE_REF = AcceptanceRef(value="AC-LIVE-BLACKBOX")
SOURCE_SURFACE_REF = SourceSurfaceRef(value="surface.backend-api")
EVIDENCE_OBLIGATION_REF = EvidenceObligationRef(value="evidence.live-blackbox")
PACKAGE_CONTRACT_REF = ContractId(value="contract.package.tiny-fullstack")
ACCEPTANCE_CONTRACT_REF = ContractId(value="contract.acceptance.tiny-fullstack")
RAW_MANIFEST_CONTEXT_REF = ContextRef(value="context.run-manifest.generated.raw")
SKELETON_SUMMARY_REF = ContextRef(value="context.run-manifest.generated.skeleton")
WORKSPACE_CONTEXT_REF = ContextRef(value="context.workspace.v2-100f")
SHARED_WORKSPACE_CONTEXT_REF = ContextRef(value="context.workspace.shared")
README_REF = ContextRef(value="docs/README.md")
RUNBOOK_REF = ContextRef(value="docs/RUNBOOK.md")
FAILURE_REF = ContextRef(value="failure.raw-run-error")
PLAN_REF = BlackboxVerificationPlanRef(value="blackbox-plan.v2-100f.verify")
SEAT_REF = AgentSeatRef(value="seat.tester.integration")
BASE_TIMESTAMP = datetime(2026, 6, 22, 12, 0, tzinfo=UTC)


class V2_100FTerminalStatus(StrEnum):
    PASSED = "passed"
    REWORK_REQUIRED = "rework_required"
    BLOCKED_OR_ESCALATED = "blocked_or_escalated"


class V2_100FNativeManifestReworkInput(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    output_root: Path
    workspace_root: Path
    run_manifest_artifact: dict[str, Any] | None = None
    run_manifest_path: Path | None = None
    require_real_provider: bool = True
    deterministic_provider_fixture: bool = False
    http_status: int = Field(default=404, gt=0)
    runtime_config_path: str | None = None
    providers_config_path: str | None = None
    roles_config_path: str | None = None

    @model_validator(mode="after")
    def _validate_manifest_source(self) -> "V2_100FNativeManifestReworkInput":
        if self.run_manifest_artifact is None and self.run_manifest_path is None:
            raise ValueError("run_manifest_artifact or run_manifest_path is required")
        if self.run_manifest_artifact is not None and self.run_manifest_path is not None:
            raise ValueError("only one run manifest source is allowed")
        return self


class V2_100FNativeManifestReworkResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    terminal_status: V2_100FTerminalStatus
    verify_blackbox_ticket_ref: str
    before_graph_ref: str | None = None
    seat_assignment_ref: str | None = None
    execution_package_ref: str | None = None
    provider_attempt_ref: str | None = None
    blackbox_plan_ref: str | None = None
    fact_refs: tuple[str, ...] = ()
    rework_request_ref: str | None = None
    blocked_reason_code: str | None = None
    raw_assertion_types: tuple[str, ...] = ()
    verify_blackbox_ready_before_execution: bool = False
    assigned_seat_ref: str | None = None
    execution_context_refs: tuple[str, ...] = ()
    rework_issue_codes: tuple[str, ...] = ()
    raw_error: str | None = None

    @field_validator("blocked_reason_code", "raw_error")
    @classmethod
    def _normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("optional text fields must not be empty")
        return normalized


class V2_100FProviderAdapter(Protocol):
    def invoke(self, request: Any) -> ProviderAttempt: ...

    def blackbox_plan_for_attempt(
        self,
        *,
        attempt: ProviderAttempt,
        execution_package: ExecutionPackage,
    ) -> BlackboxVerificationPlan: ...


def run_v2_100f_native_manifest_rework(
    input: V2_100FNativeManifestReworkInput,
    require_real_provider: bool | None = None,
    provider_adapter: V2_100FProviderAdapter | None = None,
    http_executor: HttpActionExecutor | None = None,
) -> V2_100FNativeManifestReworkResult:
    input = V2_100FNativeManifestReworkInput.model_validate(input)
    require_real_provider = input.require_real_provider if require_real_provider is None else require_real_provider
    artifact = _load_manifest_artifact(input)
    output_root = input.output_root
    proof_root = output_root / "20-evidence" / "v2-100f-native"
    proof_root.mkdir(parents=True, exist_ok=True)

    try:
        context = ingest_run_manifest_artifact(
            artifact=artifact,
            source_ref="00-boardroom/generated-run-manifest.json",
            raw_manifest_ref="artifact.run_manifest.generated",
        )
    except Exception as error:
        return _blocked_result("manifest_ingestion_failed", error)

    _write_json(proof_root / "run-manifest-ingestion-context.json", context.model_dump(mode="json"))
    raw_assertion_types = tuple(assertion.raw_type for assertion in context.raw_assertions)

    if require_real_provider and provider_adapter is None and input.deterministic_provider_fixture:
        return V2_100FNativeManifestReworkResult(
            terminal_status=V2_100FTerminalStatus.BLOCKED_OR_ESCALATED,
            verify_blackbox_ticket_ref=VERIFY_TICKET_ID.value,
            blocked_reason_code="real_provider_required",
            raw_assertion_types=raw_assertion_types,
        )
    if require_real_provider:
        config_blocker = _config_blocker(input)
        if config_blocker is not None:
            return V2_100FNativeManifestReworkResult(
                terminal_status=V2_100FTerminalStatus.BLOCKED_OR_ESCALATED,
                verify_blackbox_ticket_ref=VERIFY_TICKET_ID.value,
                blocked_reason_code=config_blocker,
            raw_assertion_types=raw_assertion_types,
        )

    try:
        model_execution_profile = _resolved_model_execution_profile(input, require_real_provider)
    except Exception as error:
        return V2_100FNativeManifestReworkResult(
            terminal_status=V2_100FTerminalStatus.BLOCKED_OR_ESCALATED,
            verify_blackbox_ticket_ref=VERIFY_TICKET_ID.value,
            blocked_reason_code=f"provider_config_failed.{type(error).__name__}",
            raw_assertion_types=raw_assertion_types,
            raw_error=f"{type(error).__name__}: {error}",
        )
    model_profiles = _model_profiles(model_execution_profile)
    contracts = _contracts()
    intent = VerifyBlackboxTicketIntent.from_request(_verification_request())
    ticket_payload = intent.to_ticket_created_payload()
    resolver = _NativePayloadResolver(ticket_payload=ticket_payload)
    events = (_ticket_created_event(), _seat_assigned_event())
    ticket_graph = TicketGraphProjector(payload_resolver=resolver).project(events)
    _write_json(proof_root / "ticket-graph.before.json", ticket_graph.model_dump(mode="json"))
    verify_ready = VERIFY_TICKET_ID in ticket_graph.ready_queue

    seat_assignment_graph = SeatAssignmentProjector(
        ticket_projector=TicketGraphProjector(resolver),
        payload_resolver=resolver,
        seat_projection=_seat_projection(model_execution_profile),
    ).project(events)
    _write_json(
        proof_root / "seat-assignment-graph.json",
        seat_assignment_graph.model_dump(mode="json"),
    )

    execution_package = ExecutionPackageCompiler().compile(
        ExecutionPackageCompilerInput.model_construct(
            ticket_ref=VERIFY_TICKET_ID,
            seat_assignment_graph=seat_assignment_graph,
            agent_team_projection=_agent_team_projection(model_execution_profile),
            acceptance_contract=contracts.acceptance_contract,
            package_contract=contracts.package_contract,
            evidence_obligations=(contracts.evidence_obligation,),
            model_execution_profiles=model_profiles,
            role_prompt_hook_registry=build_baseline_role_prompt_hook_registry(),
            workspace_context=ExecutionWorkspaceContext(
                workspace_ref=WORKSPACE_CONTEXT_REF,
                package_root="10-project",
                context_refs=(SHARED_WORKSPACE_CONTEXT_REF,),
            ),
            verification_context=VerificationExecutionContext(
                raw_manifest_context_ref=RAW_MANIFEST_CONTEXT_REF,
                skeleton_summary_ref=SKELETON_SUMMARY_REF,
                package_contract_ref=ContextRef(value=PACKAGE_CONTRACT_REF.value),
                acceptance_contract_ref=ContextRef(value=ACCEPTANCE_CONTRACT_REF.value),
                project_doc_refs=(README_REF, RUNBOOK_REF),
                source_surface_refs=(ContextRef(value=SOURCE_SURFACE_REF.value),),
                observed_failure_refs=(FAILURE_REF,),
            ),
        )
    )
    _write_json(
        proof_root / "execution-package.json",
        execution_package.model_dump(mode="json"),
        )

    if (
        not require_real_provider
        and provider_adapter is None
        and not input.deterministic_provider_fixture
    ):
        return V2_100FNativeManifestReworkResult(
            terminal_status=V2_100FTerminalStatus.BLOCKED_OR_ESCALATED,
            verify_blackbox_ticket_ref=VERIFY_TICKET_ID.value,
            before_graph_ref="ticket-graph.v2-100f.before",
            seat_assignment_ref="seat-assignment.v2-100f.graph-2",
            execution_package_ref=execution_package.execution_package_id.value,
            blocked_reason_code="deterministic_provider_fixture_required",
            raw_assertion_types=raw_assertion_types,
            verify_blackbox_ready_before_execution=verify_ready,
            assigned_seat_ref=seat_assignment_graph.seat_assignments[VERIFY_TICKET_ID].value,
            execution_context_refs=_context_ref_values(execution_package.context_refs),
        )

    try:
        adapter = _provider_adapter_for_input(
            input=input,
            require_real_provider=require_real_provider,
            provider_adapter=provider_adapter,
        )
    except Exception as error:
        return _provider_blocked_result(
            error,
            execution_package=execution_package,
            raw_assertion_types=raw_assertion_types,
            verify_ready=verify_ready,
            seat_assignment_graph=seat_assignment_graph,
        )
    try:
        provider_result = ProviderExecutor().execute(
            ProviderExecutorInput(
                execution_package=execution_package,
                provider_adapter=adapter,
            )
        )
        provider_attempt = provider_result.provider_attempt
        _write_json(proof_root / "provider-attempt.json", provider_attempt.model_dump(mode="json"))
        plan = adapter.blackbox_plan_for_attempt(
            attempt=provider_attempt,
            execution_package=execution_package,
        )
        validate_blackbox_plan_lineage(
            plan,
            execution_package=execution_package,
            provider_attempts=(provider_attempt,),
        )
    except Exception as error:
        return V2_100FNativeManifestReworkResult(
            terminal_status=V2_100FTerminalStatus.BLOCKED_OR_ESCALATED,
            verify_blackbox_ticket_ref=VERIFY_TICKET_ID.value,
            before_graph_ref="ticket-graph.v2-100f.before",
            seat_assignment_ref="seat-assignment.v2-100f.graph-2",
            execution_package_ref=execution_package.execution_package_id.value,
            provider_attempt_ref=(
                provider_result.provider_attempt.provider_attempt_id.value
                if "provider_result" in locals()
                else None
            ),
            blocked_reason_code=f"provider_plan_failed.{type(error).__name__}",
            raw_assertion_types=raw_assertion_types,
            verify_blackbox_ready_before_execution=verify_ready,
            assigned_seat_ref=seat_assignment_graph.seat_assignments[VERIFY_TICKET_ID].value,
            execution_context_refs=_context_ref_values(execution_package.context_refs),
            raw_error=f"{type(error).__name__}: {error}",
        )

    _write_json(proof_root / "blackbox-plan.json", plan.model_dump(mode="json"))

    approval = BlackboxPlanApproval(
        approval_id=BlackboxPlanApprovalRef(value="blackbox-plan-approval.v2-100f.verify"),
        plan_ref=plan.plan_id,
        approved_action_ids=tuple(action.action_id for action in plan.actions),
        approval_scope="execute_plan_actions_only",
        approved_at=datetime.now(UTC),
    )
    runner_result = BlackboxPlanRunner(
        http_executor=http_executor or _StaticHttpActionExecutor(input.http_status)
    ).run(
        BlackboxPlanRunnerInput(
            plan=plan,
            approval=approval,
            execution_package=execution_package,
            package_contract=contracts.package_contract,
            package_root=input.workspace_root,
            input_ref_hashes=_input_hashes(plan.input_context_refs),
            runner_ref=RunnerRef(value="runner.v2-100f.blackbox"),
            environment_profile_ref=EnvironmentProfileRef(value="environment.v2-100f.local"),
            workspace_snapshot_ref=WorkspaceSnapshotRef(value="workspace-snapshot.v2-100f"),
        )
    )
    _write_json(proof_root / "blackbox-runner-result.json", runner_result.model_dump(mode="json"))

    if runner_result.status is BlackboxPlanRunnerStatus.BLOCKED_OR_ESCALATED:
        return V2_100FNativeManifestReworkResult(
            terminal_status=V2_100FTerminalStatus.BLOCKED_OR_ESCALATED,
            verify_blackbox_ticket_ref=VERIFY_TICKET_ID.value,
            before_graph_ref="ticket-graph.v2-100f.before",
            seat_assignment_ref="seat-assignment.v2-100f.graph-2",
            execution_package_ref=execution_package.execution_package_id.value,
            provider_attempt_ref=provider_attempt.provider_attempt_id.value,
            blackbox_plan_ref=plan.plan_id.value,
            blocked_reason_code=runner_result.blocked_reason_code,
            raw_assertion_types=raw_assertion_types,
            verify_blackbox_ready_before_execution=verify_ready,
            assigned_seat_ref=seat_assignment_graph.seat_assignments[VERIFY_TICKET_ID].value,
            execution_context_refs=_context_ref_values(execution_package.context_refs),
        )

    routing = route_manifest_blackbox_facts(
        facts=runner_result.facts,
        context=_blocker_context(),
        advisory_context={
            "raw_manifest_context_ref": RAW_MANIFEST_CONTEXT_REF.value,
            "raw_assertion_types": raw_assertion_types,
            "skeleton_summary_ref": SKELETON_SUMMARY_REF.value,
        },
    )
    if routing.rework_request is not None:
        _write_json(
            proof_root / "rework-request.json",
            routing.rework_request.model_dump(mode="json"),
        )
        projection = ReworkReducer(_ReworkRequestOnlyResolver(routing.rework_request)).reduce(
            (
                EventRecord(
                    event_id=EventId(value="evt.v2-100f.rework-requested"),
                    event_type=EventType.REWORK_REQUESTED,
                    project_ref=PROJECT_REF,
                    actor_ref=ActorRef(value="seat.evidence-verifier"),
                    timestamp=datetime.now(UTC),
                    graph_version=13,
                    payload_refs=(EventPayloadRef(value="payload.v2-100f.rework-request"),),
                ),
            )
        )
        _write_json(proof_root / "rework-projection.json", projection.model_dump(mode="json"))

    return V2_100FNativeManifestReworkResult(
        terminal_status=_terminal_from_routing(routing.status),
        verify_blackbox_ticket_ref=VERIFY_TICKET_ID.value,
        before_graph_ref="ticket-graph.v2-100f.before",
        seat_assignment_ref="seat-assignment.v2-100f.graph-2",
        execution_package_ref=execution_package.execution_package_id.value,
        provider_attempt_ref=provider_attempt.provider_attempt_id.value,
        blackbox_plan_ref=plan.plan_id.value,
        fact_refs=tuple(fact.fact_id.value for fact in runner_result.facts),
        rework_request_ref=(
            routing.rework_request.rework_request_id.value
            if routing.rework_request is not None
            else None
        ),
        blocked_reason_code=routing.blocked_reason_code,
        raw_assertion_types=raw_assertion_types,
        verify_blackbox_ready_before_execution=verify_ready,
        assigned_seat_ref=seat_assignment_graph.seat_assignments[VERIFY_TICKET_ID].value,
        execution_context_refs=_context_ref_values(execution_package.context_refs),
        rework_issue_codes=tuple(
            issue.issue_code.value
            for issue in (routing.rework_request.issues if routing.rework_request else ())
        ),
    )


@dataclass(frozen=True)
class _NativeContracts:
    acceptance_contract: AcceptanceContract
    package_contract: PackageContract
    evidence_obligation: EvidenceObligation


class _NativePayloadResolver:
    def __init__(self, *, ticket_payload: TicketCreatedPayload) -> None:
        self._ticket_payload = ticket_payload

    def resolve_ticket_created(self, payload_ref: EventPayloadRef) -> TicketCreatedPayload:
        return self._ticket_payload

    def resolve_ticket_blocked(self, payload_ref: EventPayloadRef) -> Any:
        raise KeyError(payload_ref.value)

    def resolve_seat_assignment(self, payload_ref: EventPayloadRef) -> SeatAssignmentPayload:
        return SeatAssignmentPayload(ticket_id=VERIFY_TICKET_ID, seat_ref=SEAT_REF)


class _StaticHttpActionExecutor:
    def __init__(self, status_code: int) -> None:
        self._status_code = status_code

    def execute_http(self, *, method: str, url: str) -> BlackboxActionExecutorResult:
        return BlackboxActionExecutorResult(
            status_code=self._status_code,
            body_ref="artifact.v2-100f.http.body",
            observed_ref="artifact.v2-100f.http.observed",
            status_text="run manifest/API observation recorded",
        )


class _DeterministicBlackboxPlanProviderAdapter:
    def __init__(self, *, output_root: Path, plan_id: BlackboxVerificationPlanRef) -> None:
        self._output_root = output_root
        self._plan_id = plan_id
        self._plans: dict[str, BlackboxVerificationPlan] = {}

    def invoke(self, request: Any) -> ProviderAttempt:
        started_at = datetime.now(UTC)
        attempt = ProviderAttempt(
            provider_attempt_id=ProviderAttemptRef(
                value=f"provider-attempt.v2-100f.blackbox.{int(started_at.timestamp() * 1000000)}"
            ),
            provider=request.model_execution_profile.provider,
            model=request.model_execution_profile.model,
            reasoning_effort=request.model_execution_profile.reasoning_effort,
            input_package_ref=request.execution_package_ref,
            seat_ref=request.seat_ref,
            role_prompt_hook_ref=request.role_prompt_hook_ref,
            role_prompt_hook_version=request.role_prompt_hook_version,
            role_prompt_hook_sha256=request.role_prompt_hook_sha256,
            status=ProviderAttemptStatus.SUCCEEDED,
            outcome=ProviderAttemptOutcome.PRIMARY_PROVIDER_OUTPUT,
            started_at=started_at,
            finished_at=datetime.now(UTC),
            raw_output_ref=ProviderArtifactRef(value="artifact.v2-100f.provider.raw"),
            parsed_output_ref=ProviderArtifactRef(value="artifact.v2-100f.provider.parsed"),
        )
        self._plans[attempt.provider_attempt_id.value] = _blackbox_plan(
            plan_id=self._plan_id,
            execution_package_ref=request.execution_package_ref,
            producer_attempt_ref=attempt.provider_attempt_id,
            producer_seat_ref=request.seat_ref,
            role_prompt_hook_ref=request.role_prompt_hook_ref,
        )
        return attempt

    def blackbox_plan_for_attempt(
        self,
        *,
        attempt: ProviderAttempt,
        execution_package: ExecutionPackage,
    ) -> BlackboxVerificationPlan:
        return self._plans[attempt.provider_attempt_id.value]


class _OpenAIBlackboxPlanProviderAdapter:
    def __init__(self, *, input: V2_100FNativeManifestReworkInput) -> None:
        settings = _openai_provider_settings(input)
        artifact_store = FileProviderOutputStore(
            root=input.output_root / "20-evidence" / "provider-artifacts"
        )
        self._transport = OpenAIProviderTransport(
            settings=settings,
            artifact_store=artifact_store,
        )
        self._artifact_store = artifact_store

    def invoke(self, request: Any) -> ProviderAttempt:
        return self._transport.invoke(
            ProviderRequest(
                execution_package_ref=request.execution_package_ref,
                seat_ref=request.seat_ref,
                model_execution_profile=request.model_execution_profile,
                role_prompt_hook_ref=request.role_prompt_hook_ref,
                role_prompt_hook_version=request.role_prompt_hook_version,
                role_prompt_hook_sha256=request.role_prompt_hook_sha256,
                prompt=_blackbox_provider_prompt(request.prompt),
            )
        )

    def blackbox_plan_for_attempt(
        self,
        *,
        attempt: ProviderAttempt,
        execution_package: ExecutionPackage,
    ) -> BlackboxVerificationPlan:
        if attempt.parsed_output_ref is None:
            raise ValueError("provider parsed_output_ref is required for blackbox plan")
        payload = json.loads(self._artifact_store.read_text(attempt.parsed_output_ref))
        if not isinstance(payload, dict):
            raise ValueError("provider blackbox plan output must be a JSON object")
        # Lineage belongs to observed execution facts, not provider prose.
        payload["plan_id"] = PLAN_REF.value
        payload["execution_package_ref"] = execution_package.execution_package_id.value
        payload["producer_attempt_ref"] = attempt.provider_attempt_id.value
        payload["producer_seat_ref"] = execution_package.seat_ref.value
        payload["role_prompt_hook_ref"] = execution_package.role_prompt_hook.hook_ref.value
        return BlackboxVerificationPlan.model_validate(payload)


class _ReworkRequestOnlyResolver(ReworkReducerPayloadResolver):
    def __init__(self, request: Any) -> None:
        self._request = request

    def resolve_rework_request(self, payload_ref: EventPayloadRef) -> ReworkRequestPayload:
        return ReworkRequestPayload(request=self._request)

    def resolve_rework_plan(self, payload_ref: EventPayloadRef) -> Any:
        raise AssertionError("plan is not used by V2-100F request-only projection")

    def resolve_graph_patch_review(self, payload_ref: EventPayloadRef) -> Any:
        raise AssertionError("review is not used by V2-100F request-only projection")

    def resolve_graph_patch_approval(self, payload_ref: EventPayloadRef) -> Any:
        raise AssertionError("approval is not used by V2-100F request-only projection")

    def resolve_rework_ticket_created(self, payload_ref: EventPayloadRef) -> Any:
        raise AssertionError("ticket is not used by V2-100F request-only projection")

    def resolve_rework_attempt(self, payload_ref: EventPayloadRef) -> Any:
        raise AssertionError("attempt is not used by V2-100F request-only projection")

    def resolve_rework_review(self, payload_ref: EventPayloadRef) -> Any:
        raise AssertionError("outcome is not used by V2-100F request-only projection")

    def resolve_rework_terminal(self, payload_ref: EventPayloadRef) -> Any:
        raise AssertionError("terminal is not used by V2-100F request-only projection")


def _load_manifest_artifact(input: V2_100FNativeManifestReworkInput) -> dict[str, Any]:
    if input.run_manifest_artifact is not None:
        return dict(input.run_manifest_artifact)
    assert input.run_manifest_path is not None
    data = json.loads(input.run_manifest_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("run manifest file must contain a JSON object")
    return data


def _config_blocker(input: V2_100FNativeManifestReworkInput) -> str | None:
    values = {
        "runtime_config_path": input.runtime_config_path or os.environ.get("BOARDROOM_RUNTIME_CONFIG"),
        "providers_config_path": input.providers_config_path or os.environ.get("BOARDROOM_PROVIDERS_CONFIG"),
        "roles_config_path": input.roles_config_path or os.environ.get("BOARDROOM_ROLES_CONFIG"),
    }
    expected = {
        "runtime_config_path": EXPECTED_RUNTIME_CONFIG,
        "providers_config_path": EXPECTED_PROVIDERS_CONFIG,
        "roles_config_path": EXPECTED_ROLES_CONFIG,
    }
    for key, expected_value in expected.items():
        if values[key] != expected_value:
            return f"{key}_mismatch"
    if os.environ.get("BOARDROOM_RUN_REAL_PROVIDER_PROVING") != "1":
        return "real_provider_proving_not_enabled"
    if os.environ.get("BOARDROOM_RUN_REAL_PROVIDER_TESTS") != "1":
        return "real_provider_tests_not_enabled"
    if not os.environ.get("OPENAI_API_KEY"):
        return "provider_secret_missing"
    return None


def _resolved_model_execution_profile(
    input: V2_100FNativeManifestReworkInput,
    require_real_provider: bool,
) -> ModelExecutionProfile:
    if not require_real_provider:
        return _local_fixture_model_execution_profile()
    settings = load_boardroom_settings(
        BoardroomConfigPaths(
            runtime_config=Path(input.runtime_config_path or EXPECTED_RUNTIME_CONFIG),
            providers_config=Path(input.providers_config_path or EXPECTED_PROVIDERS_CONFIG),
            roles_config=Path(input.roles_config_path or EXPECTED_ROLES_CONFIG),
        ),
        env_values=dict(os.environ),
    )
    role_slot = settings.role_slot_by_seat(SEAT_REF.value)
    provider_config = settings.provider_by_id(role_slot.provider_profile_ref)
    return ModelExecutionProfile(
        model_execution_profile_id=ModelExecutionProfileId(
            value=role_slot.model_execution_profile_id
        ),
        provider="openai-compatible",
        model=provider_config.model,
        reasoning_effort=provider_config.reasoning_effort or "high",
        context_window=provider_config.context_window_tokens,
        temperature=0.0 if provider_config.temperature is None else provider_config.temperature,
        tool_permissions=("http.request", "command.run", "filesystem.read"),
        fallback_policy_ref=ContractId(value="fallback.verification.record_failure"),
    )


def _openai_provider_settings(input: V2_100FNativeManifestReworkInput) -> OpenAIProviderSettings:
    settings = load_boardroom_settings(
        BoardroomConfigPaths(
            runtime_config=Path(input.runtime_config_path or EXPECTED_RUNTIME_CONFIG),
            providers_config=Path(input.providers_config_path or EXPECTED_PROVIDERS_CONFIG),
            roles_config=Path(input.roles_config_path or EXPECTED_ROLES_CONFIG),
        ),
        env_values=dict(os.environ),
    )
    role_slot = settings.role_slot_by_seat(SEAT_REF.value)
    provider_config = settings.provider_by_id(role_slot.provider_profile_ref)
    response_format = provider_config.response_format or {}
    if response_format.get("type") != "json_object":
        raise ValueError("blackbox provider profile must request json_object response_format")
    return OpenAIProviderSettings(
        api_key=os.environ[provider_config.api_key_env],
        base_url=provider_config.base_url,
        model=provider_config.model,
        api_protocol="chat_completions",
        reasoning_effort=provider_config.reasoning_effort or "high",
        text_verbosity="low",
        response_format="json_object",
        max_output_tokens=provider_config.max_output_tokens,
        context_window=provider_config.context_window_tokens,
        timeout_seconds=provider_config.total_timeout_seconds,
        max_retries=0,
        system_instructions=_blackbox_provider_system_instructions(),
    )


def _provider_adapter_for_input(
    *,
    input: V2_100FNativeManifestReworkInput,
    require_real_provider: bool,
    provider_adapter: V2_100FProviderAdapter | None,
) -> V2_100FProviderAdapter:
    if provider_adapter is not None:
        return provider_adapter
    if require_real_provider:
        return _OpenAIBlackboxPlanProviderAdapter(input=input)
    return _DeterministicBlackboxPlanProviderAdapter(
        output_root=input.output_root,
        plan_id=PLAN_REF,
    )


def _blackbox_provider_system_instructions() -> str:
    return (
        "Return only one JSON object matching BlackboxVerificationPlan. "
        "Do not include success claims such as passed, approved, verified, or closeout_ready. "
        "Use only context_refs, acceptance_refs, evidence_obligation_refs, and permissions from the execution package facts. "
        "Plan executable blackbox actions; do not claim that any action has already succeeded."
    )


def _blackbox_provider_prompt(execution_prompt: str) -> str:
    return "\n".join(
        (
            "# Task",
            "Return exactly one JSON object matching this schema:",
            "{",
            '  "plan_id": "blackbox-plan.v2-100f.verify",',
            '  "execution_package_ref": "<ExecutionPackageRef from facts>",',
            '  "producer_attempt_ref": "<omit or use provider attempt ref only if known>",',
            '  "producer_seat_ref": "seat.tester.integration",',
            '  "role_prompt_hook_ref": "<role prompt hook ref from facts>",',
            '  "objective": "<non-empty objective>",',
            '  "input_context_refs": ["<refs from ExecutionPackageFacts.context_refs>"],',
            '  "run_manifest_context_ref": "context.run-manifest.generated.raw",',
            '  "acceptance_refs": ["AC-LIVE-BLACKBOX"],',
            '  "package_contract_ref": "contract.package.tiny-fullstack",',
            '  "actions": [',
            "    {",
            '      "action_id": "action.http.books",',
            '      "action_kind": "http",',
            '      "description": "<non-empty description>",',
            '      "acceptance_refs": ["AC-LIVE-BLACKBOX"],',
            '      "input_refs": ["context.run-manifest.generated.raw"],',
            '      "method": "GET",',
            '      "url": "http://127.0.0.1:8000/api/books",',
            '      "required_permissions": ["http.request"],',
            '      "expected_observations": ["HTTP status and response body shape."]',
            "    }",
            "  ],",
            '  "evidence_obligation_refs": ["evidence.live-blackbox"],',
            '  "created_at": "<timezone-aware ISO-8601 timestamp>"',
            "}",
            "",
            "Rules:",
            "- Output JSON only; no markdown, no commentary.",
            "- Do not include negative_tests, verification_commands, service_probes, behavioral_probes, acceptance_ref_map, expected_failure_modes, rework_targets, permissions, or context_refs.",
            "- Do not include success claims such as passed, approved, verified, satisfied, success, evidence_passed, or closeout_ready.",
            "- Use only refs present in ExecutionPackageFacts.",
            "- If producer_attempt_ref is unknown, omit it; the harness will bind it to the actual ProviderAttempt.",
            "",
            "# ExecutionPackagePrompt",
            execution_prompt,
        )
    )


def _verification_request() -> VerificationMilestoneRequest:
    return VerificationMilestoneRequest(
        ticket_id=VERIFY_TICKET_ID,
        raw_manifest_context_ref=RAW_MANIFEST_CONTEXT_REF,
        skeleton_summary_ref=SKELETON_SUMMARY_REF,
        acceptance_refs=(ACCEPTANCE_REF,),
        acceptance_contract_ref=ContextRef(value=ACCEPTANCE_CONTRACT_REF.value),
        package_contract_ref=ContextRef(value=PACKAGE_CONTRACT_REF.value),
        source_surface_refs=(SOURCE_SURFACE_REF,),
        evidence_obligation_refs=(EVIDENCE_OBLIGATION_REF,),
        workspace_context_refs=(WORKSPACE_CONTEXT_REF, SHARED_WORKSPACE_CONTEXT_REF),
        project_doc_refs=(README_REF, RUNBOOK_REF),
        observed_failure_refs=(FAILURE_REF,),
    )


def _ticket_created_event() -> EventRecord:
    return EventRecord(
        event_id=EventId(value="evt.v2-100f.verify-blackbox.created"),
        event_type=EventType.TICKET_CREATED,
        project_ref=PROJECT_REF,
        actor_ref=ActorRef(value="seat.ceo.delivery"),
        timestamp=BASE_TIMESTAMP,
        graph_version=1,
        payload_refs=(EventPayloadRef(value="payload.v2-100f.verify-blackbox.created"),),
    )


def _seat_assigned_event() -> EventRecord:
    return EventRecord(
        event_id=EventId(value="evt.v2-100f.verify-blackbox.assigned"),
        event_type=EventType.SEAT_ASSIGNED,
        project_ref=PROJECT_REF,
        actor_ref=ActorRef(value="seat.ceo.delivery"),
        timestamp=BASE_TIMESTAMP,
        graph_version=2,
        payload_refs=(EventPayloadRef(value="payload.v2-100f.verify-blackbox.assigned"),),
    )


def _contracts() -> _NativeContracts:
    acceptance_contract = AcceptanceContract.model_construct(
        acceptance_contract_id=ACCEPTANCE_CONTRACT_REF,
        project_charter_ref=ContractId(value="charter.v2-100f"),
        status=ContractStatus.active(),
        criteria=(
            AcceptanceCriterion(
                acceptance_ref=ACCEPTANCE_REF,
                statement="Generated package behavior is verified through native blackbox facts.",
                evidence_required=(EvidenceRequirement(value="live_blackbox_integration"),),
                blocking=True,
                source_surface_refs=(SOURCE_SURFACE_REF,),
                verification_strategy=VerificationStrategy(value="live_blackbox"),
            ),
        ),
    )
    package_contract = PackageContract(
        package_contract_id=PACKAGE_CONTRACT_REF,
        project_charter_ref=ContractId(value="charter.v2-100f"),
        package_root="10-project",
        project_type=PackageProjectType.SOFTWARE,
        source_surfaces=(
            SourceSurface(
                source_surface_ref=SOURCE_SURFACE_REF,
                name="Backend API",
                paths=("backend", "00-boardroom/generated-run-manifest.json"),
                owned_by=OwnerSeatRef(value="seat.worker.implementation"),
                acceptance_refs=(ACCEPTANCE_REF,),
                required_tests=(RequiredTestRef(value="test.live-blackbox"),),
            ),
        ),
        run_commands=(
            PackageCommand(
                command_id=ContractId(value="run.backend"),
                label="Run backend",
                command=("python", "-m", "app"),
                cwd=".",
            ),
        ),
        test_commands=(
            PackageCommand(
                command_id=ContractId(value="test.live-blackbox"),
                label="Run live blackbox checks",
                command=("python", "-m", "pytest"),
                cwd=".",
            ),
        ),
        integration_boundaries=(IntegrationBoundary(value="backend-http-api"),),
        docs_required=False,
        closeout_required=True,
    )
    evidence_obligation = EvidenceObligation(
        evidence_obligation_id=EVIDENCE_OBLIGATION_REF,
        acceptance_refs=(ACCEPTANCE_REF,),
        source_surface_refs=(SOURCE_SURFACE_REF,),
        required_artifact_type=RequiredArtifactType(value="live_blackbox_integration"),
        required_verifier=RequiredVerifier(value="live_blackbox"),
        blocking=True,
    )
    return _NativeContracts(
        acceptance_contract=acceptance_contract,
        package_contract=package_contract,
        evidence_obligation=evidence_obligation,
    )


def _seat_projection(model_execution_profile: ModelExecutionProfile) -> SeatLifecycleProjection:
    seat = _tester_seat(model_execution_profile)
    return SeatLifecycleProjection(
        graph_version=2,
        seats={seat.seat_ref: seat},
        active_seats={seat.seat_ref: seat},
        replacement_refs={},
    )


def _agent_team_projection(model_execution_profile: ModelExecutionProfile) -> AgentTeamProjection:
    seat = _tester_seat(model_execution_profile)
    hook = build_baseline_role_prompt_hook_registry().require_by_role_kind("tester")
    profile = RoleProfile(
        role_profile_id=RoleProfileId(value="role.verification.tester"),
        role_category=RoleCategory.VERIFICATION,
        role_name="Verification Tester",
        responsibilities=("Plan blackbox verification from contracts.",),
        capability_tags=(CapabilityTag(value="task.verify-blackbox"),),
        input_contracts=(ContractId(value="contract.execution.package"),),
        output_contracts=(ContractId(value="contract.blackbox.plan"),),
        forbidden_actions=("Do not write implementation files.",),
        role_prompt_hook_ref=hook.hook_ref,
        role_prompt_hook_version=hook.hook_version,
        role_prompt_hook_sha256=hook.content_sha256,
    )
    return AgentTeamProjection(
        graph_version=2,
        role_profiles=RoleProfileProjection(profiles=(profile,)),
        seat_lifecycle=SeatLifecycleProjection(
            graph_version=2,
            seats={seat.seat_ref: seat},
            active_seats={seat.seat_ref: seat},
            replacement_refs={},
        ),
    )


def _tester_seat(model_execution_profile: ModelExecutionProfile) -> AgentSeat:
    return AgentSeat(
        seat_ref=SEAT_REF,
        actor_ref=ActorRef(value="actor.tester.integration"),
        project_ref=PROJECT_REF,
        role_profile_ref=RoleProfileId(value="role.verification.tester"),
        role_category=RoleCategory.VERIFICATION,
        capability_tags=(CapabilityTag(value="task.verify-blackbox"),),
        model_execution_profile_ref=model_execution_profile.model_execution_profile_id,
        skill_refs=(SkillRef(value="skill.verification.tester"),),
        context_budget_tokens=8192,
        lifecycle_status=SeatLifecycleStatus.ACTIVE,
    )


def _model_profiles(profile: ModelExecutionProfile) -> ModelExecutionProfileRegistry:
    return ModelExecutionProfileRegistry.from_profiles(profile)


def _local_fixture_model_execution_profile() -> ModelExecutionProfile:
    return ModelExecutionProfile(
        model_execution_profile_id=ModelExecutionProfileId(value="model.tester.integration"),
        provider="openai-compatible",
        model="gpt-verifier",
        reasoning_effort="high",
        context_window=200000,
        temperature=0.2,
        tool_permissions=("http.request", "command.run", "filesystem.read"),
        fallback_policy_ref=ContractId(value="fallback.verification.record_failure"),
    )


def _blackbox_plan(
    *,
    plan_id: BlackboxVerificationPlanRef,
    execution_package_ref: ExecutionPackageRef,
    producer_attempt_ref: ProviderAttemptRef,
    producer_seat_ref: AgentSeatRef,
    role_prompt_hook_ref: Any,
) -> BlackboxVerificationPlan:
    return BlackboxVerificationPlan(
        plan_id=plan_id,
        execution_package_ref=execution_package_ref,
        producer_attempt_ref=producer_attempt_ref,
        producer_seat_ref=producer_seat_ref,
        role_prompt_hook_ref=role_prompt_hook_ref,
        objective="Verify generated package behavior from manifest context and active contracts.",
        input_context_refs=(
            RAW_MANIFEST_CONTEXT_REF,
            SKELETON_SUMMARY_REF,
            ContextRef(value=PACKAGE_CONTRACT_REF.value),
            ContextRef(value=ACCEPTANCE_CONTRACT_REF.value),
            README_REF,
            RUNBOOK_REF,
            ContextRef(value=SOURCE_SURFACE_REF.value),
            FAILURE_REF,
        ),
        run_manifest_context_ref=RAW_MANIFEST_CONTEXT_REF,
        acceptance_refs=(ACCEPTANCE_REF,),
        package_contract_ref=ContextRef(value=PACKAGE_CONTRACT_REF.value),
        actions=(
            BlackboxPlanAction(
                action_id="action.http.books",
                action_kind=BlackboxPlanActionKind.HTTP,
                description="Probe the documented books API from approved blackbox plan.",
                acceptance_refs=(ACCEPTANCE_REF,),
                input_refs=(RAW_MANIFEST_CONTEXT_REF,),
                method="GET",
                url="http://127.0.0.1:8000/api/books",
                required_permissions=("http.request",),
                expected_observations=("HTTP status and response body shape.",),
            ),
        ),
        evidence_obligation_refs=(EVIDENCE_OBLIGATION_REF,),
        created_at=datetime.now(UTC),
    )


def _input_hashes(context_refs: tuple[ContextRef, ...]) -> tuple[BlackboxActionInputRefHash, ...]:
    return tuple(
        BlackboxActionInputRefHash(
            input_ref=context_ref,
            sha256=Sha256Hex(value=f"{index + 1:064x}"),
        )
        for index, context_ref in enumerate(context_refs)
    )


def _blocker_context() -> BlockerProjectionContext:
    return BlockerProjectionContext(
        cycle_id=ReworkCycleId(value="rework-cycle.v2-100f"),
        run_id=RunId(value="run.v2-100f"),
        package_contract_ref=PACKAGE_CONTRACT_REF,
        run_manifest_ref="run-manifest.v2-100f.generated",
        active_acceptance_refs=(ACCEPTANCE_REF,),
        active_source_surface_refs=(SOURCE_SURFACE_REF,),
        active_evidence_obligation_refs=(EVIDENCE_OBLIGATION_REF,),
        active_graph_version=12,
        requested_by_actor=ReworkActorKind.EVIDENCE_VERIFIER,
        requested_at=datetime.now(UTC),
    )


def _terminal_from_routing(status: ManifestReworkRoutingStatus) -> V2_100FTerminalStatus:
    return {
        ManifestReworkRoutingStatus.PASSED: V2_100FTerminalStatus.PASSED,
        ManifestReworkRoutingStatus.REWORK_REQUIRED: V2_100FTerminalStatus.REWORK_REQUIRED,
        ManifestReworkRoutingStatus.BLOCKED_OR_ESCALATED: V2_100FTerminalStatus.BLOCKED_OR_ESCALATED,
    }[status]


def _context_ref_values(context_refs: tuple[ContextRef, ...]) -> tuple[str, ...]:
    return tuple(context_ref.value for context_ref in context_refs)


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _blocked_result(reason_code: str, error: Exception) -> V2_100FNativeManifestReworkResult:
    return V2_100FNativeManifestReworkResult(
        terminal_status=V2_100FTerminalStatus.BLOCKED_OR_ESCALATED,
        verify_blackbox_ticket_ref=VERIFY_TICKET_ID.value,
        blocked_reason_code=reason_code,
        raw_error=f"{type(error).__name__}: {error}",
    )


__all__ = [
    "EXPECTED_PROVIDERS_CONFIG",
    "EXPECTED_ROLES_CONFIG",
    "EXPECTED_RUNTIME_CONFIG",
    "V2_100FNativeManifestReworkInput",
    "V2_100FNativeManifestReworkResult",
    "V2_100FProviderAdapter",
    "V2_100FTerminalStatus",
    "run_v2_100f_native_manifest_rework",
]
