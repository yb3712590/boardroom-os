from __future__ import annotations

import hashlib
import json
from datetime import timedelta
from typing import Any

import pytest
from pydantic import BaseModel, ConfigDict, ValidationError

from boardroom_os.agents.profiles import ModelExecutionProfile, ModelExecutionProfileId
from boardroom_os.audit.git_version_audit import (
    GitVersionAuditBundle,
    git_version_audit_readiness,
)
from boardroom_os.audit.process_audit import (
    REQUIRED_PROCESS_AUDIT_ARTIFACT_PATHS,
    ProcessAuditArtifact,
    ProcessAuditArtifactFormat,
    ProcessAuditArtifactKind,
    ProcessAuditBuilderInput,
    ProcessAuditBundle,
    ProcessAuditError,
    build_process_audit_bundle,
    process_audit_readiness,
)
from boardroom_os.audit.replay_bundle import (
    ReplayContentHash,
    ReplayContentRef,
    ReplayManifestEntry,
    ReplayManifestKind,
    _payload_bytes_for_hash,
    build_replay_bundle,
    replay_bundle_readiness,
)
from boardroom_os.closeout.gate import GitAuditReadiness, ReplayBundleReadiness
from boardroom_os.contracts.acceptance import (
    AcceptanceContract,
    AcceptanceCriterion,
    EvidenceRequirement,
    VerificationStrategy,
    create_acceptance_contract,
)
from boardroom_os.contracts.evidence_obligation import EvidenceObligation, RequiredArtifactType, RequiredVerifier
from boardroom_os.contracts.directive import (
    BoardDirective,
    BoardDirectiveSourceType,
    DirectiveRegistry,
)
from boardroom_os.contracts.package import PackageCommand, PackageContract
from boardroom_os.contracts.project import (
    DeliveryType,
    ProjectCharterRegistry,
    create_project_charter,
)
from boardroom_os.contracts.types import (
    AcceptanceRef,
    ContractId,
    ContractStatus,
    EvidenceObligationRef,
    SourceSurfaceRef,
)
from boardroom_os.evidence.fallback_registry import FallbackDecisionRecordRef
from boardroom_os.evidence.table import FinalEvidenceStatus
from boardroom_os.evidence.verifier import FallbackDecisionRecordedRef, VerifiedEvidence, VerifiedEvidenceRef
from boardroom_os.events.record import EventRecord
from boardroom_os.events.types import ActorRef, EventId, EventPayloadRef, EventType, ProjectRef
from boardroom_os.execution.context_index import (
    AgentContextIndex,
    AgentContextIndexEntry,
    AgentContextIndexEntryId,
    ProviderAttemptRef,
    build_agent_context_snapshot,
)
from boardroom_os.execution.package import (
    AllowedReadRef,
    AllowedWritePath,
    AuditRequirement,
    ContextRef,
    ExecutionPackage,
    ExecutionPackageId,
    FallbackPolicyRef,
    RequiredOutput,
)
from boardroom_os.graph.seat_assignment import SeatAssignmentProjector
from boardroom_os.graph.ticket import TicketGraph, TicketId, TicketStatus
from tests.closeout.test_git_version_audit import _build_bundle as _build_git_version_audit_bundle
from tests.closeout.test_replay_bundle import _builder_input as _replay_builder_input
from tests.closeout.test_replay_bundle import _artifact_manifest_entries as _replay_artifact_manifest_entries
from tests.closeout.test_replay_bundle import _payload_manifest_entries as _replay_payload_manifest_entries
from tests.closeout.test_replay_bundle import _projector as _replay_projector
from tests.closeout.test_replay_bundle import PROJECTION_VERSION as _REPLAY_PROJECTION_VERSION
from tests.closeout.test_closeout_gate import _NOW, _ready_input as _closeout_gate_ready_input


class MinimalTicketGraphNode(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    ticket_ref: str
    status: str
    acceptance_refs: tuple[AcceptanceRef, ...]
    source_surface_refs: tuple[str, ...]
    evidence_obligation_refs: tuple[str, ...]
    owner_seat_ref: str
    blocker_refs: tuple[str, ...] = ()


class MinimalTicketGraphSummary(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    graph_ref: str
    tickets: tuple[MinimalTicketGraphNode, ...]


class LegacyAgentContextIndexEntry(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    entry_id: str
    execution_package_ref: str | None = None
    model_execution_profile: ModelExecutionProfile | None = None
    provider_attempt_refs: tuple[ProviderAttemptRef, ...]


class LegacyAgentContextIndex(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    entries: tuple[LegacyAgentContextIndexEntry, ...]


_REQUIRED_PATH_SET = set(REQUIRED_PROCESS_AUDIT_ARTIFACT_PATHS)


def _directive_registry() -> DirectiveRegistry:
    directive = BoardDirective(
        board_directive_id=ContractId(value="board-directive.process-audit"),
        source_type=BoardDirectiveSourceType.NATURAL_LANGUAGE,
        content_ref=ContractId(value="content-ref.process-audit"),
        received_at=_NOW,
        requester_ref=ContractId(value="requester.board"),
    )
    return DirectiveRegistry.from_directives(directive)


def _acceptance_contract(package_contract: PackageContract) -> AcceptanceContract:
    directive_registry = _directive_registry()
    charter = create_project_charter(
        registry=directive_registry,
        project_charter_id=ContractId(value="project-charter.process-audit"),
        board_directive_ref=ContractId(value="board-directive.process-audit"),
        project_goal="Produce an auditable closeout package.",
        delivery_type=DeliveryType.GENERATED_PROJECT_PACKAGE,
        non_goals=("Do not bypass evidence verification.",),
        constraints=("Process audit must stay typed and fail closed.",),
        risks=("Human-readable audit could drift from typed facts.",),
        success_summary="Closeout ships a readable audit trail with replay and evidence closure.",
    )
    charter_registry = ProjectCharterRegistry.from_charters(charter)
    return create_acceptance_contract(
        registry=charter_registry,
        acceptance_contract_id=ContractId(value="acceptance-contract.process-audit"),
        project_charter_ref=charter.project_charter_id,
        status=ContractStatus.active(),
        criteria=(
            AcceptanceCriterion(
                acceptance_ref=AcceptanceRef(value="AC-APP"),
                statement="App acceptance is satisfied by verified command evidence.",
                evidence_required=(EvidenceRequirement(value="verified-command-evidence"),),
                blocking=True,
                source_surface_refs=(package_contract.source_surfaces[0].source_surface_ref,),
                verification_strategy=VerificationStrategy(value="pytest"),
            ),
        ),
    )


def _model_execution_profile() -> ModelExecutionProfile:
    return ModelExecutionProfile(
        model_execution_profile_id=ModelExecutionProfileId(
            value="model.process-audit.worker"
        ),
        provider="anthropic",
        model="claude-sonnet-4-6",
        reasoning_effort="high",
        context_window=200000,
        temperature=0.2,
        tool_permissions=("read", "write"),
        fallback_policy_ref=ContractId(value="fallback-policy.contract.allowed"),
    )


def _agent_context_execution_package() -> ExecutionPackage:
    return ExecutionPackage(
        execution_package_id=ExecutionPackageId(value="execution-package.worker.app"),
        ticket_ref=TicketId(value="ticket.app"),
        graph_version=7,
        seat_ref="seat-worker-backend",
        model_execution_profile=_model_execution_profile(),
        objective="Implement app acceptance evidence.",
        context_refs=(ContextRef(value="context.package-contract.closeout-gate"),),
        constraints=("Use only the declared package contract and evidence refs.",),
        acceptance_refs=(AcceptanceRef(value="AC-APP"),),
        source_surface_refs=(SourceSurfaceRef(value="app-source"),),
        allowed_read_refs=(AllowedReadRef(value="package-contract.closeout-gate"),),
        allowed_write_set=(AllowedWritePath(value="app.py"),),
        required_outputs=(RequiredOutput(value="source.app"),),
        commands=(
            PackageCommand(
                command_id=ContractId(value="test-app"),
                label="Run app tests",
                command=("python", "-m", "pytest"),
                cwd=".",
            ),
        ),
        evidence_obligations=(
            EvidenceObligation(
                evidence_obligation_id=EvidenceObligationRef(value="evidence-obligation.app"),
                acceptance_refs=(AcceptanceRef(value="AC-APP"),),
                source_surface_refs=(SourceSurfaceRef(value="app-source"),),
                required_artifact_type=RequiredArtifactType(value="source"),
                required_verifier=RequiredVerifier(value="checker"),
                blocking=True,
            ),
        ),
        fallback_policy_ref=FallbackPolicyRef(value="fallback-policy.contract.allowed"),
        audit_requirements=(AuditRequirement(value="record.agent-context.snapshot"),),
    )


def _agent_context_index(
    provider_attempt_refs: tuple[ProviderAttemptRef, ...],
) -> AgentContextIndex:
    return AgentContextIndex(
        entries=(
            AgentContextIndexEntry(
                entry_id=AgentContextIndexEntryId(value="agent-context-entry.worker.app"),
                snapshot=build_agent_context_snapshot(_agent_context_execution_package()),
                provider_attempt_refs=provider_attempt_refs,
            ),
        )
    )


def _ticket_graph_summary() -> MinimalTicketGraphSummary:
    return MinimalTicketGraphSummary(
        graph_ref="ticket-graph.process-audit",
        tickets=(
            MinimalTicketGraphNode(
                ticket_ref="ticket.app",
                status="completed",
                acceptance_refs=(AcceptanceRef(value="AC-APP"), AcceptanceRef(value="AC-TEST")),
                source_surface_refs=("app-source", "app-tests"),
                evidence_obligation_refs=("evidence-obligation.app",),
                owner_seat_ref="seat-worker-backend",
            ),
        )
    )


class ProcessAuditReplayProjector(SeatAssignmentProjector):
    pass


class ProcessAuditReplayPayloadResolver:
    def __init__(
        self,
        delegate: Any,
        extra_payload_refs: tuple[str, ...],
    ) -> None:
        self._delegate = delegate
        self._extra_payload_refs = set(extra_payload_refs)

    def resolve_payload(self, content_ref):
        payload_ref = EventPayloadRef(value=content_ref.value)
        if content_ref.value in self._extra_payload_refs:
            return f"payload.{content_ref.value}"
        try:
            return self._delegate.resolve_payload(content_ref)
        except AttributeError:
            if content_ref.value == "payload:ticket-backend-api-created":
                return self.resolve_ticket_created(payload_ref)
            if content_ref.value == "payload:ticket-backend-api-seat-assigned":
                return self.resolve_seat_assignment(payload_ref)
            raise

    def resolve_ticket_created(self, payload_ref: EventPayloadRef):
        return self._delegate.resolve_ticket_created(payload_ref)

    def resolve_ticket_blocked(self, payload_ref: EventPayloadRef):
        return self._delegate.resolve_ticket_blocked(payload_ref)

    def resolve_seat_assignment(self, payload_ref: EventPayloadRef):
        return self._delegate.resolve_seat_assignment(payload_ref)

    def resolve_process_audit_event(self, payload_ref: EventPayloadRef) -> dict[str, str]:
        if payload_ref.value not in self._extra_payload_refs:
            raise KeyError(payload_ref.value)
        return {"payload_ref": payload_ref.value}


class ProcessAuditReplayTicketProjector:
    def __init__(self, delegate: Any) -> None:
        self._delegate = delegate

    def project(self, events: tuple[EventRecord, ...]):
        ticket_events = tuple(
            event
            for event in events
            if event.event_type is EventType.TICKET_CREATED
            or event.event_type is EventType.TICKET_BLOCKED
        )
        ticket_graph = self._delegate.project(ticket_events)
        if events and ticket_graph.graph_version != events[-1].graph_version:
            nodes = tuple(
                node.model_copy(update={"status": TicketStatus.COMPLETED})
                for node in ticket_graph.nodes.values()
            )
            return TicketGraph.from_nodes(
                graph_version=events[-1].graph_version,
                nodes=nodes,
            )
        return ticket_graph


def _replay_payload_resolver() -> ProcessAuditReplayPayloadResolver:
    base_projector = _replay_projector()
    return ProcessAuditReplayPayloadResolver(
        base_projector._payload_resolver,
        (
            "payload:ticket-started",
            "provider-attempt.app",
            "source-inventory",
            "verification-run.app",
        ),
    )


def _process_audit_payload_manifest_entries(
    events: tuple[EventRecord, ...],
    payload_resolver: ProcessAuditReplayPayloadResolver,
) -> tuple[ReplayManifestEntry, ...]:
    return tuple(
        ReplayManifestEntry(
            manifest_ref=entry.manifest_ref,
            kind=entry.kind,
            content_ref=entry.content_ref,
            sha256=ReplayContentHash(
                value=hashlib.sha256(
                    _payload_bytes_for_hash(payload_resolver.resolve_payload(entry.content_ref))
                ).hexdigest()
            ),
        )
        for entry in _replay_payload_manifest_entries(events)
    )


class ProcessAuditReplaySeatAssignmentProjector(ProcessAuditReplayProjector):
    def __init__(self) -> None:
        base_projector = _replay_projector()
        super().__init__(
            ticket_projector=ProcessAuditReplayTicketProjector(base_projector._ticket_projector),
            payload_resolver=ProcessAuditReplayPayloadResolver(
                base_projector._payload_resolver,
                (
                    "payload:ticket-started",
                    "provider-attempt.app",
                    "source-inventory",
                    "verification-run.app",
                ),
            ),
            seat_projection=base_projector._seat_projection,
        )


def _audit_event(
    *,
    event_type: EventType,
    graph_version: int,
    payload_ref: str,
    event_ref: str | None = None,
    actor_ref: str = "boardroom-os",
) -> EventRecord:
    return EventRecord(
        event_id=EventId(value=event_ref or f"event.process-audit.{graph_version}.{event_type.value}"),
        event_type=event_type,
        project_ref=ProjectRef(value="project-tiny-fullstack"),
        actor_ref=ActorRef(value=actor_ref),
        timestamp=_NOW + timedelta(seconds=graph_version),
        graph_version=graph_version,
        payload_refs=(EventPayloadRef(value=payload_ref),),
    )


def _process_audit_events() -> tuple[EventRecord, ...]:
    return (
        _audit_event(event_type=EventType.TICKET_CREATED, graph_version=1, payload_ref="payload:ticket-backend-api-created", event_ref="evt-ticket-created-1", actor_ref="seat-architect"),
        _audit_event(event_type=EventType.SEAT_ASSIGNED, graph_version=2, payload_ref="payload:ticket-backend-api-seat-assigned", event_ref="evt-seat-assigned-2", actor_ref="seat-ceo"),
        _audit_event(event_type=EventType.TICKET_LEASED, graph_version=3, payload_ref="payload:ticket-started"),
        _audit_event(event_type=EventType.PROVIDER_ATTEMPT_RECORDED, graph_version=4, payload_ref="provider-attempt.app"),
        _audit_event(event_type=EventType.WORK_PRODUCT_SUBMITTED, graph_version=5, payload_ref="source-inventory"),
        _audit_event(event_type=EventType.COMMAND_RUN_RECORDED, graph_version=6, payload_ref="verification-run.app"),
    )


def _build_replay_bundle_for_process_audit(events: tuple[EventRecord, ...]):
    replay_events = events
    payload_resolver = _replay_payload_resolver()
    event_window_ref = (
        "event-range."
        f"{replay_events[0].project_ref.value}."
        f"{replay_events[0].graph_version}-{replay_events[-1].graph_version}"
    )
    artifact_manifest_entries = tuple(
        entry.model_copy(update={"content_ref": ReplayContentRef(value=event_window_ref)})
        if entry.kind is ReplayManifestKind.EVENT_WINDOW
        else entry
        for entry in _replay_artifact_manifest_entries()
    )
    return build_replay_bundle(
        _replay_builder_input(
            events=replay_events,
            payload_manifest_entries=_process_audit_payload_manifest_entries(
                replay_events,
                payload_resolver,
            ),
            artifact_manifest_entries=artifact_manifest_entries,
            projection_version=_REPLAY_PROJECTION_VERSION,
            seat_assignment_projector=ProcessAuditReplaySeatAssignmentProjector(),
        )
    )


def _process_audit_builder_input(
    *,
    agent_context_index: BaseModel | None = None,
    git_version_audit_bundle: GitVersionAuditBundle | None = None,
    git_audit_readiness: GitAuditReadiness | None = None,
    verified_evidence: tuple[VerifiedEvidence, ...] | None = None,
    replay_events: tuple[EventRecord, ...] | None = None,
    replay_bundle: Any | None = None,
    replay_readiness: ReplayBundleReadiness | None = None,
    source_inventory: Any | None = None,
    final_evidence_table: Any | None = None,
    ticket_graph_summary: BaseModel | None = None,
    run_id: str | None = "run-v2-071e",
) -> ProcessAuditBuilderInput:
    gate_input = _closeout_gate_ready_input()
    resolved_replay_events = replay_events or _process_audit_events()
    replay_bundle = replay_bundle or _build_replay_bundle_for_process_audit(resolved_replay_events)
    resolved_replay_readiness = replay_readiness or replay_bundle_readiness(
        replay_bundle,
        payload_resolver=_replay_payload_resolver(),
    )
    resolved_git_version_audit_bundle = (
        git_version_audit_bundle or _build_git_version_audit_bundle()
    )
    resolved_git_audit_readiness = (
        git_audit_readiness
        or git_version_audit_readiness(resolved_git_version_audit_bundle)
    )
    return ProcessAuditBuilderInput(
        project_ref=replay_bundle.project_ref,
        generated_at=_NOW,
        package_contract=gate_input.package_contract,
        acceptance_contract=_acceptance_contract(gate_input.package_contract),
        agent_context_index=agent_context_index
        or _agent_context_index(gate_input.provider_attempt_refs),
        ticket_graph_summary=ticket_graph_summary or _ticket_graph_summary(),
        source_inventory=source_inventory if source_inventory is not None else gate_input.source_inventory,
        run_manifest=gate_input.run_manifest,
        workspace_evidence_bundle=gate_input.workspace_evidence_bundle,
        final_evidence_table=final_evidence_table if final_evidence_table is not None else gate_input.final_evidence_table,
        checker_verdict=gate_input.checker_verdict,
        verification_runs=gate_input.verification_runs,
        verified_evidence=verified_evidence if verified_evidence is not None else gate_input.verified_evidence,
        provider_attempt_refs=gate_input.provider_attempt_refs,
        replay_bundle=replay_bundle,
        replay_readiness=resolved_replay_readiness,
        git_version_audit_bundle=resolved_git_version_audit_bundle,
        git_audit_readiness=resolved_git_audit_readiness,
        run_id=run_id,
    )


def _build_bundle(**overrides: Any) -> ProcessAuditBundle:
    return build_process_audit_bundle(_process_audit_builder_input(**overrides))


def _artifact_by_path(bundle: ProcessAuditBundle, path: str) -> ProcessAuditArtifact:
    for artifact in bundle.artifacts:
        if artifact.path.value == path:
            return artifact
    raise AssertionError(f"artifact path not found: {path}")


def _artifact_by_kind(
    bundle: ProcessAuditBundle, kind: ProcessAuditArtifactKind
) -> ProcessAuditArtifact:
    for artifact in bundle.artifacts:
        if artifact.kind is kind:
            return artifact
    raise AssertionError(f"artifact kind not found: {kind.value}")


def _canonical_jsonable(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, tuple | list):
        return [_canonical_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {key: _canonical_jsonable(item) for key, item in value.items()}
    return value


def _hash_jsonable(value: Any) -> str:
    encoded = json.dumps(
        _canonical_jsonable(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _artifact_content_hash(
    content: Any, artifact_format: ProcessAuditArtifactFormat
) -> str:
    if artifact_format is ProcessAuditArtifactFormat.MARKDOWN:
        return hashlib.sha256(str(content).encode("utf-8")).hexdigest()
    return _hash_jsonable(content)


def _replace_artifact(
    bundle: ProcessAuditBundle,
    *,
    kind: ProcessAuditArtifactKind,
    content: Any | None = None,
    path: str | None = None,
) -> ProcessAuditBundle:
    replaced: list[ProcessAuditArtifact] = []
    for artifact in bundle.artifacts:
        if artifact.kind is kind:
            next_content = artifact.content if content is None else content
            next_path = artifact.path if path is None else type(artifact.path)(value=path)
            replaced.append(
                artifact.model_copy(
                    update={
                        "path": next_path,
                        "content": next_content,
                        "sha256": type(artifact.sha256)(
                            value=_artifact_content_hash(next_content, artifact.format)
                        ),
                    }
                )
            )
            continue
        replaced.append(artifact)
    return bundle.model_copy(update={"artifacts": tuple(replaced)})


@pytest.mark.parametrize("missing_path", sorted(_REQUIRED_PATH_SET))
def test_process_audit_rejects_missing_required_artifact(
    missing_path: str,
) -> None:
    bundle = _build_bundle()
    kept_artifacts = tuple(
        artifact
        for artifact in bundle.artifacts
        if artifact.path.value != missing_path
    )

    with pytest.raises(
        (ProcessAuditError, ValidationError),
        match="artifact|required|process audit",
    ):
        process_audit_readiness(bundle.model_copy(update={"artifacts": kept_artifacts}))


def test_process_audit_rejects_extra_audit_artifact_path() -> None:
    bundle = _build_bundle()
    template = bundle.artifacts[0]
    extra_artifact = template.model_copy(
        update={
            "artifact_id": type(template.artifact_id)(
                value="process-audit-artifact.extra-audit-artifact"
            ),
            "path": type(template.path)(value="30-audit/extra-audit-artifact.json"),
            "content_ref": type(template.content_ref)(
                value="process-audit-content.extra-audit-artifact"
            ),
            "sha256": type(template.sha256)(
                value=_artifact_content_hash(template.content, template.format)
            ),
        }
    )

    with pytest.raises(
        (ProcessAuditError, ValidationError),
        match="artifact|path|required|extra",
    ):
        process_audit_readiness(
            bundle.model_copy(update={"artifacts": (*bundle.artifacts, extra_artifact)})
        )


def test_process_audit_rejects_duplicate_audit_artifact_path() -> None:
    bundle = _build_bundle()
    template = _artifact_by_kind(bundle, ProcessAuditArtifactKind.TIMELINE)
    duplicate_artifact = template.model_copy(
        update={
            "artifact_id": type(template.artifact_id)(
                value="process-audit-artifact.timeline-duplicate"
            ),
            "content_ref": type(template.content_ref)(
                value="process-audit-content.timeline-duplicate"
            ),
        }
    )

    with pytest.raises(
        (ProcessAuditError, ValidationError),
        match="artifact|path|duplicate|unique",
    ):
        process_audit_readiness(
            bundle.model_copy(
                update={"artifacts": (*bundle.artifacts, duplicate_artifact)}
            )
        )


@pytest.mark.parametrize(
    "unsafe_path",
    ("30-audit/../timeline.json", "C:/audit/timeline.json", "30-audit\\timeline.json"),
)
def test_process_audit_rejects_unsafe_audit_artifact_path(unsafe_path: str) -> None:
    bundle = _build_bundle()
    broken_bundle = _replace_artifact(
        bundle,
        kind=ProcessAuditArtifactKind.TIMELINE,
        path=unsafe_path,
    )

    with pytest.raises(
        (ProcessAuditError, ValidationError),
        match="path|audit|relative|unsafe",
    ):
        process_audit_readiness(broken_bundle)


def test_process_audit_rejects_timeline_missing_key_event() -> None:
    bundle = _build_bundle()
    timeline = _artifact_by_kind(bundle, ProcessAuditArtifactKind.TIMELINE)
    content = dict(timeline.content)
    content["events"] = [
        event
        for event in content["events"]
        if event["kind"] != "provider_attempt_recorded"
    ]
    broken_bundle = _replace_artifact(
        bundle,
        kind=ProcessAuditArtifactKind.TIMELINE,
        content=content,
    )

    with pytest.raises(
        (ProcessAuditError, ValidationError),
        match="timeline|key event|provider_attempt_recorded|hash manifest",
    ):
        process_audit_readiness(broken_bundle)


def test_process_audit_rejects_decision_log_without_ceo_or_human_board_decision() -> None:
    bundle = _build_bundle()
    decision_log = _artifact_by_kind(bundle, ProcessAuditArtifactKind.DECISION_LOG)
    broken_bundle = _replace_artifact(
        bundle,
        kind=ProcessAuditArtifactKind.DECISION_LOG,
        content=str(decision_log.content)
        .replace("## CEO / Human Board Decision", "## Governance Decision")
        .replace("CEO / human board", "governance"),
    )

    with pytest.raises(
        (ProcessAuditError, ValidationError),
        match="decision|CEO|human board|hash manifest",
    ):
        process_audit_readiness(broken_bundle)


def test_process_audit_rejects_agent_context_entry_without_real_snapshot() -> None:
    gate_input = _closeout_gate_ready_input()
    legacy_index = LegacyAgentContextIndex(
        entries=(
            LegacyAgentContextIndexEntry(
                entry_id="agent-context-entry.legacy",
                execution_package_ref="execution-package.legacy",
                model_execution_profile=_model_execution_profile(),
                provider_attempt_refs=gate_input.provider_attempt_refs,
            ),
        )
    )

    with pytest.raises((ProcessAuditError, ValidationError), match="agent context|snapshot|AgentContextIndex"):
        build_process_audit_bundle(
            _process_audit_builder_input(agent_context_index=legacy_index)
        )


def test_process_audit_rejects_agent_context_provider_attempt_mismatch() -> None:
    extra_ref = ProviderAttemptRef(value="provider-attempt.extra")
    broken_index = _agent_context_index((extra_ref,))

    with pytest.raises(
        (ProcessAuditError, ValidationError),
        match="agent context|provider_attempt_refs|missing|extra",
    ):
        build_process_audit_bundle(
            _process_audit_builder_input(agent_context_index=broken_index)
        )


def test_process_audit_rejects_verified_evidence_without_verification_run_refs() -> None:
    gate_input = _closeout_gate_ready_input()
    broken_evidence = gate_input.verified_evidence[0].model_copy(
        update={"verification_run_refs": ()}
    )

    with pytest.raises(
        (ProcessAuditError, ValidationError),
        match="verified evidence|verification_run_refs",
    ):
        build_process_audit_bundle(
            _process_audit_builder_input(verified_evidence=(broken_evidence,))
        )


def test_process_audit_rejects_source_inventory_evidence_ref_missing_from_verified_evidence() -> None:
    gate_input = _closeout_gate_ready_input()

    with pytest.raises(
        (ProcessAuditError, ValidationError),
        match="source inventory|evidence_refs|verified evidence|verified_evidence must not be empty",
    ):
        build_process_audit_bundle(
            _process_audit_builder_input(
                verified_evidence=(),
                source_inventory=gate_input.source_inventory,
            )
        )


def test_process_audit_rejects_final_evidence_table_ref_missing_from_verified_evidence() -> None:
    gate_input = _closeout_gate_ready_input()
    missing_ref_row = gate_input.final_evidence_table.rows[0].model_copy(
        update={
            "verified_evidence_refs": (
                VerifiedEvidenceRef(value="verified-evidence.missing"),
            )
        }
    )
    broken_table = gate_input.final_evidence_table.model_copy(update={"rows": (missing_ref_row,)})

    with pytest.raises(
        (ProcessAuditError, ValidationError),
        match="final evidence table|verified evidence",
    ):
        build_process_audit_bundle(
            _process_audit_builder_input(final_evidence_table=broken_table)
        )


def test_process_audit_rejects_source_inventory_evidence_ref_missing_from_final_table() -> None:
    gate_input = _closeout_gate_ready_input()
    extra_ref = VerifiedEvidenceRef(value="verified-evidence.extra")
    extra_evidence = gate_input.verified_evidence[0].model_copy(
        update={"verified_evidence_id": extra_ref}
    )
    broken_entry = gate_input.source_inventory.entries[0].model_copy(
        update={"evidence_refs": (extra_ref,)}
    )
    broken_inventory = gate_input.source_inventory.model_copy(update={"entries": (broken_entry,)})

    with pytest.raises(
        (ProcessAuditError, ValidationError),
        match="source inventory|final evidence table",
    ):
        build_process_audit_bundle(
            _process_audit_builder_input(
                source_inventory=broken_inventory,
                verified_evidence=(gate_input.verified_evidence[0], extra_evidence),
            )
        )


def test_process_audit_rejects_replay_readiness_event_range_mismatch() -> None:
    base_input = _process_audit_builder_input()
    mismatched_readiness = base_input.replay_readiness.model_copy(
        update={"event_range": type(base_input.replay_readiness.event_range)(value="event-range.project-tiny-fullstack.9-10")}
    )

    with pytest.raises(
        (ProcessAuditError, ValidationError),
        match="replay readiness mismatch",
    ):
        build_process_audit_bundle(
            _process_audit_builder_input(replay_readiness=mismatched_readiness)
        )


def test_process_audit_rejects_git_source_inventory_binding_mismatch() -> None:
    gate_input = _closeout_gate_ready_input()
    changed_inventory = gate_input.source_inventory.model_copy(
        update={"package_commit_ref": type(gate_input.source_inventory.package_commit_ref)(value="package-commit.fedcba9876543210fedcba9876543210fedcba98")}
    )

    with pytest.raises(
        (ProcessAuditError, ValidationError),
        match="git version audit|source inventory|hash|package_commit_ref",
    ):
        build_process_audit_bundle(
            _process_audit_builder_input(source_inventory=changed_inventory)
        )


def test_process_audit_rejects_incomplete_artifact_lineage() -> None:
    bundle = _build_bundle()
    lineage = _artifact_by_kind(bundle, ProcessAuditArtifactKind.ARTIFACT_LINEAGE)
    content = dict(lineage.content)
    primary_lineages = [dict(item) for item in content["lineages"]]
    primary_lineages[0].pop("producer_attempt_ref", None)
    content["lineages"] = primary_lineages
    broken_bundle = _replace_artifact(
        bundle,
        kind=ProcessAuditArtifactKind.ARTIFACT_LINEAGE,
        content=content,
    )

    with pytest.raises(
        (ProcessAuditError, ValidationError),
        match="lineage|closeout|producer attempt|hash manifest",
    ):
        process_audit_readiness(broken_bundle)


def test_process_audit_rejects_missing_fallback_lineage() -> None:
    gate_input = _closeout_gate_ready_input()
    fallback_evidence = gate_input.verified_evidence[0].model_copy(
        update={
            "fallback_decision_record_ref": FallbackDecisionRecordRef(
                value="fallback-decision.verified-evidence.app"
            ),
            "fallback_decision_recorded_ref": FallbackDecisionRecordedRef(
                value="fallback-decision-recorded.verified-evidence.app"
            ),
        }
    )
    bundle = _build_bundle(verified_evidence=(fallback_evidence,))
    lineage = _artifact_by_kind(bundle, ProcessAuditArtifactKind.ARTIFACT_LINEAGE)
    content = dict(lineage.content)
    content["fallback_lineages"] = ()
    broken_bundle = _replace_artifact(
        bundle,
        kind=ProcessAuditArtifactKind.ARTIFACT_LINEAGE,
        content=content,
    )

    with pytest.raises(
        (ProcessAuditError, ValidationError),
        match="fallback|lineage|decision record|hash manifest",
    ):
        process_audit_readiness(broken_bundle)


def test_process_audit_rejects_evidence_map_inconsistent_with_final_table() -> None:
    bundle = _build_bundle()
    evidence_map = _artifact_by_kind(bundle, ProcessAuditArtifactKind.EVIDENCE_MAP)
    content = dict(evidence_map.content)
    rows = [dict(row) for row in content["rows"]]
    rows[0]["verified_evidence_refs"] = ()
    content["rows"] = rows
    broken_bundle = _replace_artifact(
        bundle,
        kind=ProcessAuditArtifactKind.EVIDENCE_MAP,
        content=content,
    )

    with pytest.raises(
        (ProcessAuditError, ValidationError),
        match="evidence map|final evidence table|verified_evidence_refs|hash manifest",
    ):
        process_audit_readiness(broken_bundle)


@pytest.mark.parametrize(
    ("needle", "expected_match"),
    (
        ("Final commit SHA", "final commit|git audit|hash manifest"),
        ("Git clean status", "git clean|dirty status|git audit|hash manifest"),
        ("Source inventory hash", "source inventory hash|git audit|hash manifest"),
    ),
)
def test_process_audit_rejects_incomplete_git_version_audit(
    needle: str,
    expected_match: str,
) -> None:
    bundle = _build_bundle()
    git_audit = _artifact_by_kind(bundle, ProcessAuditArtifactKind.GIT_VERSION_AUDIT)
    broken_bundle = _replace_artifact(
        bundle,
        kind=ProcessAuditArtifactKind.GIT_VERSION_AUDIT,
        content="\n".join(
            line for line in str(git_audit.content).splitlines() if needle not in line
        ),
    )

    with pytest.raises((ProcessAuditError, ValidationError), match=expected_match):
        process_audit_readiness(broken_bundle)


def test_process_audit_rejects_replay_bundle_report_mismatch() -> None:
    bundle = _build_bundle()
    replay_report = _artifact_by_kind(
        bundle, ProcessAuditArtifactKind.REPLAY_BUNDLE_REPORT
    )
    content = dict(replay_report.content)
    content["summary_hash"] = "deadbeef" * 8
    broken_bundle = _replace_artifact(
        bundle,
        kind=ProcessAuditArtifactKind.REPLAY_BUNDLE_REPORT,
        content=content,
    )

    with pytest.raises(
        (ProcessAuditError, ValidationError),
        match="replay|summary_hash|projection version|hash manifest",
    ):
        process_audit_readiness(broken_bundle)


def test_process_audit_rejects_hash_manifest_mismatch() -> None:
    bundle = _build_bundle()
    broken_payload = bundle.model_dump(mode="python", exclude={"bundle_hash"})
    broken_payload["hash_manifest"]["artifact_hashes"][
        "30-audit/process-audit.md"
    ] = "abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789"

    with pytest.raises(
        (ProcessAuditError, ValidationError),
        match="hash manifest|artifact hash|bundle payload hash",
    ):
        process_audit_readiness(type(bundle).model_validate(broken_payload))


__all__ = [
    "_artifact_by_kind",
    "_artifact_by_path",
    "_artifact_content_hash",
    "_build_bundle",
]
