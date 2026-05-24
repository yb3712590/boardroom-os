from __future__ import annotations

import hashlib
import json
from typing import Any

import pytest
from pydantic import BaseModel, ConfigDict, ValidationError

from boardroom_os.agents.profiles import ModelExecutionProfile, ModelExecutionProfileId
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
from boardroom_os.audit.replay_bundle import build_replay_bundle, replay_bundle_readiness
from boardroom_os.closeout.gate import GitAuditReadiness
from boardroom_os.contracts.acceptance import (
    AcceptanceContract,
    AcceptanceCriterion,
    EvidenceRequirement,
    VerificationStrategy,
    create_acceptance_contract,
)
from boardroom_os.contracts.directive import (
    BoardDirective,
    BoardDirectiveSourceType,
    DirectiveRegistry,
)
from boardroom_os.contracts.package import PackageContract
from boardroom_os.contracts.project import (
    DeliveryType,
    ProjectCharterRegistry,
    create_project_charter,
)
from boardroom_os.contracts.types import AcceptanceRef, ContractId, ContractStatus
from boardroom_os.evidence.fallback_registry import FallbackDecisionRecordRef
from boardroom_os.evidence.verifier import FallbackDecisionRecordedRef, VerifiedEvidence
from boardroom_os.execution.context_index import ProviderAttemptRef
from boardroom_os.execution.package import ExecutionPackageRef
from tests.closeout.test_replay_bundle import _builder_input as _replay_builder_input
from tests.negative.test_closeout_fail_closed import _NOW, _ready_input as _closeout_gate_ready_input


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


class MinimalAgentContextIndexEntry(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    entry_id: str
    execution_package_ref: ExecutionPackageRef | None
    model_execution_profile: ModelExecutionProfile | None
    provider_attempt_refs: tuple[ProviderAttemptRef, ...]


class MinimalAgentContextIndex(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    entries: tuple[MinimalAgentContextIndexEntry, ...]


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


def _agent_context_index(
    provider_attempt_refs: tuple[ProviderAttemptRef, ...],
) -> MinimalAgentContextIndex:
    return MinimalAgentContextIndex(
        entries=(
            MinimalAgentContextIndexEntry(
                entry_id="agent-context-entry.worker.app",
                execution_package_ref=ExecutionPackageRef(
                    value="execution-package.worker.app"
                ),
                model_execution_profile=_model_execution_profile(),
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
                acceptance_refs=(AcceptanceRef(value="AC-APP"),),
                source_surface_refs=("app-source",),
                evidence_obligation_refs=("evidence-obligation.app",),
                owner_seat_ref="seat-worker-backend",
            ),
        )
    )


def _process_audit_builder_input(
    *,
    agent_context_index: MinimalAgentContextIndex | None = None,
    git_audit_readiness: GitAuditReadiness | None = None,
    verified_evidence: tuple[VerifiedEvidence, ...] | None = None,
) -> ProcessAuditBuilderInput:
    gate_input = _closeout_gate_ready_input()
    replay_bundle = build_replay_bundle(_replay_builder_input())
    replay_readiness = replay_bundle_readiness(replay_bundle)
    return ProcessAuditBuilderInput(
        project_ref=replay_bundle.project_ref,
        generated_at=_NOW,
        events=replay_bundle.events,
        package_contract=gate_input.package_contract,
        acceptance_contract=_acceptance_contract(gate_input.package_contract),
        agent_context_index=agent_context_index
        or _agent_context_index(gate_input.provider_attempt_refs),
        ticket_graph_summary=_ticket_graph_summary(),
        source_inventory=gate_input.source_inventory,
        workspace_evidence_bundle=gate_input.workspace_evidence_bundle,
        final_evidence_table=gate_input.final_evidence_table,
        checker_verdict=gate_input.checker_verdict,
        verification_runs=gate_input.verification_runs,
        verified_evidence=verified_evidence or gate_input.verified_evidence,
        provider_attempt_refs=gate_input.provider_attempt_refs,
        replay_bundle=replay_bundle,
        replay_readiness=replay_readiness,
        git_audit_readiness=git_audit_readiness or gate_input.git_audit_readiness,
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


@pytest.mark.parametrize(
    ("field_name", "replacement", "expected_match"),
    (
        ("execution_package_ref", None, "execution_package_ref|agent context|hash manifest"),
        ("model_execution_profile", None, "model_execution_profile|agent context|hash manifest"),
        ("provider_attempt_refs", (), "provider_attempt_refs|agent context|hash manifest"),
    ),
)
def test_process_audit_rejects_incomplete_agent_context_index(
    field_name: str,
    replacement: object,
    expected_match: str,
) -> None:
    gate_input = _closeout_gate_ready_input()
    broken_entry = _agent_context_index(gate_input.provider_attempt_refs).entries[0].model_copy(
        update={field_name: replacement}
    )
    broken_index = MinimalAgentContextIndex(entries=(broken_entry,))

    with pytest.raises((ProcessAuditError, ValidationError), match=expected_match):
        build_process_audit_bundle(
            _process_audit_builder_input(agent_context_index=broken_index)
        )


def test_process_audit_rejects_incomplete_artifact_lineage() -> None:
    bundle = _build_bundle()
    lineage = _artifact_by_kind(bundle, ProcessAuditArtifactKind.ARTIFACT_LINEAGE)
    content = dict(lineage.content)
    primary_lineages = [dict(item) for item in content["lineages"]]
    primary_lineages[0].pop("closeout_related_ref", None)
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
    ] = "a" * 64

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
