from __future__ import annotations

from typing import Any

import pytest
from pydantic import BaseModel, ConfigDict, ValidationError

from boardroom_os.audit.git_version_audit import (
    _bundle_payload_for_hash,
    _hash_jsonable,
    git_version_audit_readiness,
    source_inventory_hash,
)
from boardroom_os.audit.process_audit import (
    ProcessAuditArtifactKind,
    ProcessAuditBuilderInput,
    ProcessAuditError,
    _hash_bundle_payload,
    _hash_model,
    build_process_audit_bundle,
    process_audit_readiness,
)
from boardroom_os.evidence.fallback_registry import FallbackDecisionRecordRef
from boardroom_os.evidence.verifier import FallbackDecisionRecordedRef, VerifiedEvidenceRef
from boardroom_os.events.types import EventType
from boardroom_os.execution.context_index import ProviderAttemptRef
from boardroom_os.execution.verification_run import VerificationRunStatus
from boardroom_os.graph.ticket import TicketId

from tests.closeout.test_git_version_audit import (
    _build_bundle as _build_git_version_audit_bundle,
    _command_binding,
    _git_facts,
)
from tests.closeout.test_process_audit_artifacts import (
    _artifact_by_kind,
    _artifact_content_hash,
    _build_bundle,
    _process_audit_builder_input,
    _process_audit_events,
)




def _rehashed_process_audit_bundle(bundle, *, artifacts=None, report=None, checked_refs=None):
    resolved_artifacts = tuple(artifacts if artifacts is not None else bundle.artifacts)
    resolved_report = report or bundle.process_audit_report
    resolved_checked_refs = tuple(checked_refs if checked_refs is not None else bundle.checked_refs)
    artifact_hashes = {
        artifact.path.value: artifact.sha256 for artifact in resolved_artifacts
    }
    artifact_manifest = bundle.artifact_manifest.model_copy(
        update={
            "entries": tuple(
                entry.model_copy(
                    update={
                        "sha256": artifact_hashes[entry.path.value],
                    }
                )
                for entry in bundle.artifact_manifest.entries
            )
        }
    )
    partial_hash_manifest = bundle.hash_manifest.model_copy(
        update={
            "artifact_hashes": artifact_hashes,
            "artifact_manifest_hash": type(bundle.hash_manifest.artifact_manifest_hash)(
                value=_hash_model(artifact_manifest)
            ),
            "process_audit_report_hash": type(bundle.hash_manifest.process_audit_report_hash)(
                value=_hash_model(resolved_report)
            ),
        }
    )
    hash_manifest_without_bundle_hash = {
        "hash_manifest_id": partial_hash_manifest.hash_manifest_id,
        "project_ref": partial_hash_manifest.project_ref,
        "artifact_hashes": partial_hash_manifest.artifact_hashes,
        "artifact_manifest_hash": partial_hash_manifest.artifact_manifest_hash,
        "process_audit_report_hash": partial_hash_manifest.process_audit_report_hash,
    }
    hash_manifest = partial_hash_manifest.model_copy(
        update={
            "bundle_payload_hash": type(bundle.hash_manifest.bundle_payload_hash)(
                value=_hash_bundle_payload(
                    process_audit_bundle_id=bundle.process_audit_bundle_id,
                    project_ref=bundle.project_ref,
                    generated_at=bundle.generated_at,
                    artifacts=resolved_artifacts,
                    artifact_manifest=artifact_manifest,
                    hash_manifest_without_bundle_hash=hash_manifest_without_bundle_hash,
                    process_audit_report=resolved_report,
                    checked_refs=resolved_checked_refs,
                )
            )
        }
    )
    return bundle.model_copy(
        update={
            "artifacts": resolved_artifacts,
            "artifact_manifest": artifact_manifest,
            "hash_manifest": hash_manifest,
            "process_audit_report": resolved_report,
            "checked_refs": resolved_checked_refs,
        }
    )


def _replace_artifact_content(bundle, *, kind: ProcessAuditArtifactKind, content: Any):
    artifacts = []
    for artifact in bundle.artifacts:
        if artifact.kind is kind:
            artifacts.append(
                artifact.model_copy(
                    update={
                        "content": content,
                        "sha256": type(artifact.sha256)(
                            value=_artifact_content_hash(content, artifact.format)
                        ),
                    }
                )
            )
            continue
        artifacts.append(artifact)
    return _rehashed_process_audit_bundle(bundle, artifacts=tuple(artifacts))


def _build_process_audit_with_source_inventory(source_inventory, *, ticket_graph_summary=None):
    facts = _git_facts(source_inventory_hash=source_inventory_hash(source_inventory))
    binding = _command_binding(source_inventory_hash=source_inventory_hash(source_inventory))
    git_bundle = _build_git_version_audit_bundle(
        source_inventory=source_inventory,
        git_facts=facts,
        command_evidence_bindings=(binding,),
    )
    return _build_bundle(
        source_inventory=source_inventory,
        ticket_graph_summary=ticket_graph_summary,
        git_version_audit_bundle=git_bundle,
    )


def _git_bundle_for_source_inventory(source_inventory, *, verification_runs=None):
    resolved_verification_runs = verification_runs or _process_audit_builder_input().verification_runs
    inventory_hash = source_inventory_hash(source_inventory)
    bindings = tuple(
        _command_binding(
            binding_id=f"git-command-evidence-binding.{run.verification_run_id.value}",
            verification_run_ref=run.verification_run_id,
            workspace_snapshot_ref=run.workspace_snapshot_ref,
            source_inventory_hash=inventory_hash,
        )
        for run in resolved_verification_runs
    )
    facts = _git_facts(source_inventory_hash=inventory_hash)
    return _build_git_version_audit_bundle(
        source_inventory=source_inventory,
        verification_runs=resolved_verification_runs,
        git_facts=facts,
        command_evidence_bindings=bindings,
    )


def _process_audit_input_with_raw_source_inventory(source_inventory):
    base_input = _process_audit_builder_input()
    return base_input.model_copy(
        update={
            "source_inventory": source_inventory,
        }
    )


class _TicketWithoutTicketRef(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: str
    owner_seat_ref: str
    acceptance_refs: tuple[object, ...]
    source_surface_refs: tuple[object, ...]


class _TicketWithoutStatus(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    ticket_ref: str
    owner_seat_ref: str
    acceptance_refs: tuple[object, ...]
    source_surface_refs: tuple[object, ...]


class _TicketWithoutOwnerSeatRef(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    ticket_ref: str
    status: str
    acceptance_refs: tuple[object, ...]
    source_surface_refs: tuple[object, ...]


class _TicketWithoutAcceptanceRefs(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    ticket_ref: str
    status: str
    owner_seat_ref: str
    source_surface_refs: tuple[object, ...]


class _TicketWithScalarAcceptanceRefs(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    ticket_ref: str
    status: str
    owner_seat_ref: str
    acceptance_refs: object
    source_surface_refs: tuple[object, ...]


class _BrokenTicketGraphSummary(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    graph_ref: str = "ticket-graph.broken"
    tickets: tuple[BaseModel, ...]


class _TicketGraphSummaryWithoutTickets(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    graph_ref: str = "ticket-graph.broken"


class _TicketGraphSummaryWithOptionalTickets(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    graph_ref: str = "ticket-graph.broken"
    tickets: object


class _AgentSnapshotWithoutExecutionPackageRef(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    context_snapshot_id: str
    snapshot_fingerprint: str
    model_execution_profile: object


class _AgentSnapshotWithoutModelExecutionProfile(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    context_snapshot_id: str
    snapshot_fingerprint: str
    execution_package_ref: str


class _AgentSnapshotWithoutContextSnapshotId(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    snapshot_fingerprint: str
    execution_package_ref: str
    model_execution_profile: object


class _AgentSnapshotWithoutSnapshotFingerprint(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    context_snapshot_id: str
    execution_package_ref: str
    model_execution_profile: object


class _BrokenAgentContextEntry(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    entry_id: str
    snapshot: BaseModel
    provider_attempt_refs: tuple[ProviderAttemptRef, ...]


class _AgentContextEntryWithoutEntryId(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    snapshot: BaseModel
    provider_attempt_refs: tuple[ProviderAttemptRef, ...]


class _AgentContextEntryWithOptionalProviderRefs(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    entry_id: str
    snapshot: BaseModel
    provider_attempt_refs: object


class _BrokenAgentContextIndex(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    entries: tuple[BaseModel, ...]


class _AgentContextIndexWithOptionalEntries(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    entries: object


class _SourceInventoryEntryWithoutConsumerTicketRefs(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    path: object
    sha256: object
    source_surface_ref: object
    producer_ticket_ref: object
    producer_attempt_ref: object
    acceptance_refs: tuple[object, ...]
    evidence_refs: tuple[object, ...]


class _SourceInventoryEntryWithScalarLineageRefs(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    path: object
    sha256: object
    source_surface_ref: object
    producer_ticket_ref: object
    producer_attempt_ref: object
    consumer_ticket_refs: object
    acceptance_refs: object
    evidence_refs: object


class _BrokenSourceInventory(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    source_inventory_id: object
    package_assembly_ref: object
    package_contract_ref: object
    package_root: object
    package_commit_ref: object
    entries: tuple[BaseModel, ...]


def _payload_from_builder_input() -> dict[str, object]:
    base_input = _process_audit_builder_input()
    return base_input.model_dump(mode="python")


def _ticket_graph_summary_with(ticket: BaseModel) -> _BrokenTicketGraphSummary:
    return _BrokenTicketGraphSummary(tickets=(ticket,))


def _broken_agent_context_index(snapshot: BaseModel) -> _BrokenAgentContextIndex:
    provider_attempt_refs = _process_audit_builder_input().provider_attempt_refs
    return _BrokenAgentContextIndex(
        entries=(
            _BrokenAgentContextEntry(
                entry_id="agent-context-entry.broken",
                snapshot=snapshot,
                provider_attempt_refs=provider_attempt_refs,
            ),
        )
    )


def _build_process_audit_with_ticket_graph_summary(ticket_graph_summary: BaseModel):
    base_input = _process_audit_builder_input()
    return build_process_audit_bundle(
        base_input.model_copy(update={"ticket_graph_summary": ticket_graph_summary})
    )


def test_process_audit_builds_before_closeout_committed_event_exists() -> None:
    events = tuple(
        event
        for event in _process_audit_events()
        if event.event_type is not EventType.CLOSEOUT_COMMITTED
    )

    bundle = _build_bundle(replay_events=events)
    timeline = _artifact_by_kind(bundle, ProcessAuditArtifactKind.TIMELINE)
    event_kinds = {event["kind"] for event in timeline.content["events"]}

    assert "closeout_committed" not in event_kinds
    assert process_audit_readiness(bundle).timeline_key_events_present is True


def test_process_audit_builder_input_rejects_external_events_field() -> None:
    payload = _payload_from_builder_input()
    payload["events"] = _process_audit_events()

    with pytest.raises(ValidationError, match="events|extra"):
        ProcessAuditBuilderInput.model_validate(payload)


def test_process_audit_rejects_replay_bundle_event_window_gap() -> None:
    events = tuple(
        event
        for event in _process_audit_events()
        if event.graph_version != 4
    )

    with pytest.raises(
        (ProcessAuditError, ValidationError, ValueError),
        match="strictly ordered|contiguous|event window|cover|projection failed",
    ):
        _build_bundle(replay_events=events)


def test_process_audit_rejects_non_increasing_replay_bundle_events() -> None:
    events = tuple(reversed(_process_audit_events()))

    with pytest.raises(
        (ProcessAuditError, ValidationError, ValueError),
        match="strictly increasing|strictly ordered|contiguous|projection failed",
    ):
        _build_bundle(replay_events=events)


@pytest.mark.parametrize(
    ("ticket", "expected_message"),
    (
        (
            _TicketWithoutTicketRef(
                status="completed",
                owner_seat_ref="seat-worker-backend",
                acceptance_refs=("AC-APP",),
                source_surface_refs=("app-source",),
            ),
            "missing ticket_ref",
        ),
        (
            _TicketWithoutStatus(
                ticket_ref="ticket.app",
                owner_seat_ref="seat-worker-backend",
                acceptance_refs=("AC-APP", "AC-TEST"),
                source_surface_refs=("app-source", "app-tests"),
            ),
            "missing status",
        ),
        (
            _TicketWithoutOwnerSeatRef(
                ticket_ref="ticket.app",
                status="completed",
                acceptance_refs=("AC-APP", "AC-TEST"),
                source_surface_refs=("app-source", "app-tests"),
            ),
            "missing owner_seat_ref",
        ),
        (
            _TicketWithoutAcceptanceRefs(
                ticket_ref="ticket.app",
                status="completed",
                owner_seat_ref="seat-worker-backend",
                source_surface_refs=("app-source",),
            ),
            "missing acceptance_refs",
        ),
    ),
)
def test_process_audit_rejects_ticket_graph_summary_missing_required_fields(
    ticket: BaseModel,
    expected_message: str,
) -> None:
    with pytest.raises(
        (ProcessAuditError, ValidationError),
        match=expected_message,
    ):
        _build_process_audit_with_ticket_graph_summary(
            _ticket_graph_summary_with(ticket)
        )


@pytest.mark.parametrize(
    "ticket_graph_summary",
    (
        _TicketGraphSummaryWithoutTickets(),
        _TicketGraphSummaryWithOptionalTickets(tickets=None),
        _TicketGraphSummaryWithOptionalTickets(tickets=()),
        _TicketGraphSummaryWithOptionalTickets(tickets=123),
    ),
)
def test_process_audit_rejects_ticket_graph_summary_without_iterable_nonempty_tickets(
    ticket_graph_summary: BaseModel,
) -> None:
    with pytest.raises(
        (ProcessAuditError, ValidationError),
        match="ticket graph summary missing tickets",
    ):
        _build_process_audit_with_ticket_graph_summary(ticket_graph_summary)


@pytest.mark.parametrize(
    "acceptance_refs",
    ("AC-APP", b"AC-APP", {"value": "AC-APP"}, 123, ()),
)
def test_process_audit_rejects_ticket_graph_summary_invalid_acceptance_refs(
    acceptance_refs: object,
) -> None:
    ticket = _TicketWithScalarAcceptanceRefs(
        ticket_ref="ticket.app",
        status="completed",
        owner_seat_ref="seat-worker-backend",
        acceptance_refs=acceptance_refs,
        source_surface_refs=("app-source",),
    )

    with pytest.raises(
        (ProcessAuditError, ValidationError),
        match="ticket graph summary ticket missing acceptance_refs",
    ):
        _build_process_audit_with_ticket_graph_summary(
            _ticket_graph_summary_with(ticket)
        )


def test_process_audit_rejects_agent_context_without_entry_id() -> None:
    base_input = _process_audit_builder_input()
    entry = base_input.agent_context_index.entries[0]
    broken_index = _BrokenAgentContextIndex(
        entries=(
            _AgentContextEntryWithoutEntryId(
                snapshot=entry.snapshot,
                provider_attempt_refs=entry.provider_attempt_refs,
            ),
        )
    )

    with pytest.raises(
        (ProcessAuditError, ValidationError),
        match="agent context|AgentContextIndex",
    ):
        build_process_audit_bundle(
            _process_audit_builder_input(agent_context_index=broken_index)
        )


@pytest.mark.parametrize(
    ("entries", "expected_message"),
    (
        (None, "agent context|AgentContextIndex"),
        ((), "agent context|AgentContextIndex"),
        (123, "agent context|AgentContextIndex"),
    ),
)
def test_process_audit_rejects_agent_context_without_iterable_nonempty_entries(
    entries: object,
    expected_message: str,
) -> None:
    broken_index = _AgentContextIndexWithOptionalEntries(entries=entries)

    with pytest.raises(
        (ProcessAuditError, ValidationError),
        match=expected_message,
    ):
        build_process_audit_bundle(
            _process_audit_builder_input(agent_context_index=broken_index)
        )


@pytest.mark.parametrize(
    "provider_attempt_refs",
    (
        None,
        "provider-attempt.app",
        {"ref": "provider-attempt.app"},
        123,
    ),
)
def test_process_audit_rejects_agent_context_entry_without_iterable_provider_attempt_refs(
    provider_attempt_refs: object,
) -> None:
    base_input = _process_audit_builder_input()
    entry = base_input.agent_context_index.entries[0]
    broken_index = _BrokenAgentContextIndex(
        entries=(
            _AgentContextEntryWithOptionalProviderRefs(
                entry_id=entry.entry_id.value,
                snapshot=entry.snapshot,
                provider_attempt_refs=provider_attempt_refs,
            ),
        )
    )

    with pytest.raises(
        (ProcessAuditError, ValidationError),
        match="agent context|AgentContextIndex",
    ):
        build_process_audit_bundle(
            _process_audit_builder_input(agent_context_index=broken_index)
        )


@pytest.mark.parametrize(
    "provider_attempt_refs",
    (
        (),
        [],
    ),
)
def test_process_audit_rejects_agent_context_entry_with_empty_provider_attempt_refs(
    provider_attempt_refs: object,
) -> None:
    base_input = _process_audit_builder_input()
    entry = base_input.agent_context_index.entries[0]
    broken_index = _BrokenAgentContextIndex(
        entries=(
            _AgentContextEntryWithOptionalProviderRefs(
                entry_id=entry.entry_id.value,
                snapshot=entry.snapshot,
                provider_attempt_refs=provider_attempt_refs,
            ),
        )
    )

    with pytest.raises(
        (ProcessAuditError, ValidationError),
        match="agent context|AgentContextIndex",
    ):
        build_process_audit_bundle(
            _process_audit_builder_input(agent_context_index=broken_index)
        )


def test_process_audit_rejects_agent_context_without_snapshot_execution_package_ref() -> None:
    snapshot = _AgentSnapshotWithoutExecutionPackageRef(
        context_snapshot_id="context-snapshot.broken",
        snapshot_fingerprint="a" * 64,
        model_execution_profile={"provider": "anthropic"},
    )

    with pytest.raises(
        (ProcessAuditError, ValidationError),
        match="agent context|AgentContextIndex",
    ):
        build_process_audit_bundle(
            _process_audit_builder_input(
                agent_context_index=_broken_agent_context_index(snapshot)
            )
        )


def test_process_audit_rejects_agent_context_without_snapshot_model_execution_profile() -> None:
    snapshot = _AgentSnapshotWithoutModelExecutionProfile(
        context_snapshot_id="context-snapshot.broken",
        snapshot_fingerprint="a" * 64,
        execution_package_ref="execution-package.worker.app",
    )

    with pytest.raises(
        (ProcessAuditError, ValidationError),
        match="agent context|AgentContextIndex",
    ):
        build_process_audit_bundle(
            _process_audit_builder_input(
                agent_context_index=_broken_agent_context_index(snapshot)
            )
        )


def test_process_audit_rejects_agent_context_without_snapshot_context_snapshot_id() -> None:
    base_snapshot = _process_audit_builder_input().agent_context_index.entries[0].snapshot
    snapshot = _AgentSnapshotWithoutContextSnapshotId(
        snapshot_fingerprint="a" * 64,
        execution_package_ref="execution-package.worker.app",
        model_execution_profile=base_snapshot.model_execution_profile,
    )

    with pytest.raises(
        (ProcessAuditError, ValidationError),
        match="agent context|AgentContextIndex",
    ):
        build_process_audit_bundle(
            _process_audit_builder_input(
                agent_context_index=_broken_agent_context_index(snapshot)
            )
        )


def test_process_audit_rejects_agent_context_without_snapshot_fingerprint() -> None:
    base_snapshot = _process_audit_builder_input().agent_context_index.entries[0].snapshot
    snapshot = _AgentSnapshotWithoutSnapshotFingerprint(
        context_snapshot_id="context-snapshot.broken",
        execution_package_ref="execution-package.worker.app",
        model_execution_profile=base_snapshot.model_execution_profile,
    )

    with pytest.raises(
        (ProcessAuditError, ValidationError),
        match="agent context|AgentContextIndex",
    ):
        build_process_audit_bundle(
            _process_audit_builder_input(
                agent_context_index=_broken_agent_context_index(snapshot)
            )
        )


def test_artifact_lineage_rejects_missing_consumer_ticket_refs() -> None:
    bundle = _build_bundle()
    lineage = _artifact_by_kind(bundle, ProcessAuditArtifactKind.ARTIFACT_LINEAGE)
    content = dict(lineage.content)
    primary_lineages = [dict(item) for item in content["lineages"]]
    primary_lineages[0].pop("consumer_ticket_refs", None)
    content["lineages"] = primary_lineages
    broken_bundle = _replace_artifact_content(
        bundle,
        kind=ProcessAuditArtifactKind.ARTIFACT_LINEAGE,
        content=content,
    )

    with pytest.raises(
        (ProcessAuditError, ValidationError),
        match="artifact lineage missing producer attempt or closeout link",
    ):
        process_audit_readiness(broken_bundle)


def test_artifact_lineage_does_not_default_consumer_to_producer() -> None:
    base_input = _process_audit_builder_input()
    entry = base_input.source_inventory.entries[0]
    consumer_ticket_ref = TicketId(value="ticket.consumer.audit-reader")
    changed_entry = entry.model_copy(
        update={"consumer_ticket_refs": (consumer_ticket_ref,)}
    )
    changed_inventory = base_input.source_inventory.model_copy(
        update={"entries": (changed_entry, *base_input.source_inventory.entries[1:])}
    )
    ticket = base_input.ticket_graph_summary.tickets[0]
    consumer_ticket = ticket.model_copy(update={"ticket_ref": consumer_ticket_ref.value})
    ticket_graph_summary = base_input.ticket_graph_summary.model_copy(
        update={"tickets": (*base_input.ticket_graph_summary.tickets, consumer_ticket)}
    )

    bundle = _build_process_audit_with_source_inventory(
        changed_inventory,
        ticket_graph_summary=ticket_graph_summary,
    )
    lineage = _artifact_by_kind(bundle, ProcessAuditArtifactKind.ARTIFACT_LINEAGE)
    lineages_for_path = [
        item for item in lineage.content["lineages"] if item["path"] == entry.path.value
    ]

    assert lineages_for_path
    assert {item["producer_ticket_ref"] for item in lineages_for_path} == {
        entry.producer_ticket_ref.value
    }
    assert all(
        item["consumer_ticket_refs"] == [consumer_ticket_ref.value]
        for item in lineages_for_path
    )
    assert all(
        item["consumer_ticket_refs"] != [entry.producer_ticket_ref.value]
        for item in lineages_for_path
    )


def test_artifact_lineage_rejects_fallback_lineages_when_expected_empty() -> None:
    gate_input = _process_audit_builder_input()
    evidence = gate_input.verified_evidence[0].model_copy(
        update={
            "fallback_decision_record_ref": None,
            "fallback_decision_recorded_ref": None,
        }
    )
    bundle = _build_bundle(verified_evidence=(evidence,))
    lineage = _artifact_by_kind(bundle, ProcessAuditArtifactKind.ARTIFACT_LINEAGE)
    content = dict(lineage.content)
    content["fallback_lineages"] = (
        {
            "fallback_decision_record_ref": "fallback-decision.unexpected",
            "fallback_decision_recorded_ref": None,
            "verifier_ref": "runner.local",
            "evidence_map_ref": "process-audit-artifact.evidence_map",
        },
    )
    broken_bundle = _replace_artifact_content(
        bundle,
        kind=ProcessAuditArtifactKind.ARTIFACT_LINEAGE,
        content=content,
    )

    with pytest.raises(
        (ProcessAuditError, ValidationError),
        match="fallback lineage decision refs must match expected fallback decisions",
    ):
        process_audit_readiness(broken_bundle)


def test_artifact_lineage_rejects_missing_expected_fallback_lineage() -> None:
    gate_input = _process_audit_builder_input()
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
    broken_bundle = _replace_artifact_content(
        bundle,
        kind=ProcessAuditArtifactKind.ARTIFACT_LINEAGE,
        content=content,
    )

    with pytest.raises(
        (ProcessAuditError, ValidationError),
        match="fallback lineage decision refs must match expected fallback decisions",
    ):
        process_audit_readiness(broken_bundle)


def test_artifact_lineage_rejects_fallback_lineage_without_decision_ref_key() -> None:
    gate_input = _process_audit_builder_input()
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
    fallback_lineages = [dict(item) for item in content["fallback_lineages"]]
    fallback_lineages[0].pop("fallback_decision_record_ref", None)
    content["fallback_lineages"] = fallback_lineages
    broken_bundle = _replace_artifact_content(
        bundle,
        kind=ProcessAuditArtifactKind.ARTIFACT_LINEAGE,
        content=content,
    )

    with pytest.raises(
        (ProcessAuditError, ValidationError),
        match="fallback lineage missing decision record",
    ):
        process_audit_readiness(broken_bundle)


def test_artifact_lineage_rejects_tampered_fallback_recorded_ref() -> None:
    gate_input = _process_audit_builder_input()
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
    fallback_lineages = [dict(item) for item in content["fallback_lineages"]]
    fallback_lineages[0][
        "fallback_decision_recorded_ref"
    ] = "fallback-decision-recorded.tampered"
    content["fallback_lineages"] = fallback_lineages
    broken_bundle = _replace_artifact_content(
        bundle,
        kind=ProcessAuditArtifactKind.ARTIFACT_LINEAGE,
        content=content,
    )

    with pytest.raises(
        (ProcessAuditError, ValidationError),
        match="fallback lineage decision refs must match expected fallback decisions",
    ):
        process_audit_readiness(broken_bundle)


def test_artifact_lineage_rejects_missing_fallback_recorded_ref_key() -> None:
    gate_input = _process_audit_builder_input()
    fallback_evidence = gate_input.verified_evidence[0].model_copy(
        update={
            "fallback_decision_record_ref": FallbackDecisionRecordRef(
                value="fallback-decision.verified-evidence.app"
            ),
            "fallback_decision_recorded_ref": None,
        }
    )
    bundle = _build_bundle(verified_evidence=(fallback_evidence,))
    lineage = _artifact_by_kind(bundle, ProcessAuditArtifactKind.ARTIFACT_LINEAGE)
    content = dict(lineage.content)
    fallback_lineages = [dict(item) for item in content["fallback_lineages"]]
    fallback_lineages[0].pop("fallback_decision_recorded_ref", None)
    content["fallback_lineages"] = fallback_lineages
    broken_bundle = _replace_artifact_content(
        bundle,
        kind=ProcessAuditArtifactKind.ARTIFACT_LINEAGE,
        content=content,
    )

    with pytest.raises(
        (ProcessAuditError, ValidationError),
        match="fallback lineage missing decision record",
    ):
        process_audit_readiness(broken_bundle)


def test_artifact_lineage_rejects_duplicate_fallback_decision_refs() -> None:
    gate_input = _process_audit_builder_input()
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
    fallback_lineage = dict(content["fallback_lineages"][0])
    content["fallback_lineages"] = (fallback_lineage, fallback_lineage)
    broken_bundle = _replace_artifact_content(
        bundle,
        kind=ProcessAuditArtifactKind.ARTIFACT_LINEAGE,
        content=content,
    )

    with pytest.raises(
        (ProcessAuditError, ValidationError),
        match="fallback lineage decision refs must match expected fallback decisions",
    ):
        process_audit_readiness(broken_bundle)


def test_process_audit_rejects_source_inventory_entry_scalar_lineage_refs() -> None:
    base_input = _process_audit_builder_input()
    base_entry = base_input.source_inventory.entries[0]
    broken_entry = _SourceInventoryEntryWithScalarLineageRefs(
        path=base_entry.path,
        sha256=base_entry.sha256,
        source_surface_ref=base_entry.source_surface_ref,
        producer_ticket_ref=base_entry.producer_ticket_ref,
        producer_attempt_ref=base_entry.producer_attempt_ref,
        consumer_ticket_refs=base_entry.consumer_ticket_refs[0],
        acceptance_refs=base_entry.acceptance_refs[0],
        evidence_refs=base_entry.evidence_refs[0],
    )
    broken_inventory = _BrokenSourceInventory(
        source_inventory_id=base_input.source_inventory.source_inventory_id,
        package_assembly_ref=base_input.source_inventory.package_assembly_ref,
        package_contract_ref=base_input.source_inventory.package_contract_ref,
        package_root=base_input.source_inventory.package_root,
        package_commit_ref=base_input.source_inventory.package_commit_ref,
        entries=(broken_entry, *base_input.source_inventory.entries[1:]),
    )

    with pytest.raises(
        ProcessAuditError,
        match="source_inventory must be valid SourceInventory|source_inventory evidence_refs missing verified evidence",
    ):
        build_process_audit_bundle(
            _process_audit_input_with_raw_source_inventory(broken_inventory)
        )



def test_process_audit_rejects_agent_context_snapshot_with_invalid_fingerprint() -> None:
    base_input = _process_audit_builder_input()
    agent_entry = base_input.agent_context_index.entries[0]
    broken_snapshot = agent_entry.snapshot.model_copy(
        update={"snapshot_fingerprint": "not-a-sha-256-digest"}
    )
    broken_index = base_input.agent_context_index.model_copy(
        update={
            "entries": (
                agent_entry.model_copy(update={"snapshot": broken_snapshot}),
            )
        }
    )

    with pytest.raises(
        ProcessAuditError,
        match="agent_context_index must be valid AgentContextIndex|agent_context_index must be AgentContextIndex",
    ):
        build_process_audit_bundle(
            base_input.model_copy(update={"agent_context_index": broken_index})
        )



def test_artifact_lineage_builder_rejects_source_inventory_entry_missing_consumer_ticket_refs() -> None:
    base_input = _process_audit_builder_input()
    base_entry = base_input.source_inventory.entries[0]
    broken_entry = _SourceInventoryEntryWithoutConsumerTicketRefs(
        path=base_entry.path,
        sha256=base_entry.sha256,
        source_surface_ref=base_entry.source_surface_ref,
        producer_ticket_ref=base_entry.producer_ticket_ref,
        producer_attempt_ref=base_entry.producer_attempt_ref,
        acceptance_refs=base_entry.acceptance_refs,
        evidence_refs=base_entry.evidence_refs,
    )
    broken_inventory = _BrokenSourceInventory(
        source_inventory_id=base_input.source_inventory.source_inventory_id,
        package_assembly_ref=base_input.source_inventory.package_assembly_ref,
        package_contract_ref=base_input.source_inventory.package_contract_ref,
        package_root=base_input.source_inventory.package_root,
        package_commit_ref=base_input.source_inventory.package_commit_ref,
        entries=(broken_entry, *base_input.source_inventory.entries[1:]),
    )

    with pytest.raises(
        ProcessAuditError,
        match="source_inventory must be valid SourceInventory|source inventory entry missing consumer_ticket_refs",
    ):
        build_process_audit_bundle(
            _process_audit_input_with_raw_source_inventory(broken_inventory)
        )


def test_process_audit_rejects_verified_evidence_with_unknown_verification_run_ref() -> None:
    base_input = _process_audit_builder_input()
    ghost_evidence = base_input.verified_evidence[0].model_copy(
        update={
            "verification_run_refs": (
                type(base_input.verification_runs[0].verification_run_id)(
                    value="verification-run.ghost"
                ),
            ),
        }
    )

    with pytest.raises(
        (ProcessAuditError, ValidationError),
        match="verified evidence references missing verification runs",
    ):
        build_process_audit_bundle(
            _process_audit_builder_input(verified_evidence=(ghost_evidence,))
        )


def test_process_audit_rejects_consumer_ticket_outside_source_surface_scope() -> None:
    base_input = _process_audit_builder_input()
    ticket = base_input.ticket_graph_summary.tickets[0]
    source_entry = base_input.source_inventory.entries[0]
    foreign_ticket = ticket.model_copy(
        update={
            "ticket_ref": "ticket.foreign",
            "source_surface_refs": ("foreign-source",),
            "acceptance_refs": source_entry.acceptance_refs,
        }
    )
    changed_entry = source_entry.model_copy(
        update={"consumer_ticket_refs": (TicketId(value="ticket.foreign"),)}
    )
    source_inventory = base_input.source_inventory.model_copy(
        update={"entries": (changed_entry, *base_input.source_inventory.entries[1:])}
    )
    git_bundle = _git_bundle_for_source_inventory(source_inventory)

    with pytest.raises(
        (ProcessAuditError, ValidationError),
        match="source inventory consumer_ticket_refs outside ticket scope",
    ):
        build_process_audit_bundle(
            _process_audit_builder_input(
                source_inventory=source_inventory,
                ticket_graph_summary=base_input.ticket_graph_summary.model_copy(
                    update={"tickets": (*base_input.ticket_graph_summary.tickets, foreign_ticket)}
                ),
                git_version_audit_bundle=git_bundle,
                git_audit_readiness=git_version_audit_readiness(git_bundle),
            )
        )



def test_process_audit_rejects_source_inventory_unknown_producer_attempt_ref() -> None:
    base_input = _process_audit_builder_input()
    entry = base_input.source_inventory.entries[0]
    broken_entry = entry.model_copy(
        update={
            "producer_attempt_ref": ProviderAttemptRef(
                value="provider-attempt.unknown"
            )
        }
    )
    broken_inventory = base_input.source_inventory.model_copy(
        update={"entries": (broken_entry, *base_input.source_inventory.entries[1:])}
    )
    git_bundle = _git_bundle_for_source_inventory(broken_inventory)

    with pytest.raises(
        (ProcessAuditError, ValidationError),
        match="source inventory producer_attempt_refs mismatch",
    ):
        build_process_audit_bundle(
            _process_audit_builder_input(
                source_inventory=broken_inventory,
                git_version_audit_bundle=git_bundle,
                git_audit_readiness=git_version_audit_readiness(git_bundle),
            )
        )


def test_process_audit_rejects_git_audit_run_manifest_ref_mismatch() -> None:
    base_input = _process_audit_builder_input()
    binding = base_input.git_version_audit_bundle.command_evidence_bindings[0]
    other_manifest_ref = type(binding.run_manifest_ref)(value="run-manifest.unrelated")
    self_consistent_git_bundle = base_input.git_version_audit_bundle.model_copy(
        update={
            "command_evidence_bindings": (
                binding.model_copy(update={"run_manifest_ref": other_manifest_ref}),
            )
        }
    )
    command_binding_hashes = {
        item.verification_run_ref.value: type(self_consistent_git_bundle.hash_manifest.bundle_payload_hash)(
            value=_hash_model(item)
        )
        for item in self_consistent_git_bundle.command_evidence_bindings
    }
    hash_manifest_without_bundle_hash = {
        "hash_manifest_id": self_consistent_git_bundle.hash_manifest.hash_manifest_id.value,
        "project_ref": self_consistent_git_bundle.hash_manifest.project_ref.value,
        "fact_set_hash": self_consistent_git_bundle.hash_manifest.fact_set_hash.value,
        "report_hash": self_consistent_git_bundle.hash_manifest.report_hash.value,
        "command_binding_hashes": {
            key: value.value for key, value in command_binding_hashes.items()
        },
    }
    bundle_payload = _bundle_payload_for_hash(
        bundle_id=self_consistent_git_bundle.git_version_audit_bundle_id,
        project_ref=self_consistent_git_bundle.project_ref,
        generated_at=self_consistent_git_bundle.generated_at,
        fact_set=self_consistent_git_bundle.fact_set,
        command_evidence_bindings=self_consistent_git_bundle.command_evidence_bindings,
        report=self_consistent_git_bundle.report,
        checked_refs=self_consistent_git_bundle.checked_refs,
        hash_manifest_without_bundle_hash=hash_manifest_without_bundle_hash,
    )
    self_consistent_git_bundle = self_consistent_git_bundle.model_copy(
        update={
            "hash_manifest": self_consistent_git_bundle.hash_manifest.model_copy(
                update={
                    "command_binding_hashes": command_binding_hashes,
                    "bundle_payload_hash": type(self_consistent_git_bundle.hash_manifest.bundle_payload_hash)(
                        value=_hash_jsonable(bundle_payload)
                    ),
                }
            )
        }
    )
    self_consistent_evidence_bundle = base_input.workspace_evidence_bundle.model_copy(
        update={"run_manifest_ref": other_manifest_ref}
    )

    with pytest.raises(
        ProcessAuditError,
        match="git version audit run_manifest_ref mismatch",
    ):
        build_process_audit_bundle(
            base_input.model_copy(
                update={
                    "git_version_audit_bundle": self_consistent_git_bundle,
                    "workspace_evidence_bundle": self_consistent_evidence_bundle,
                }
            )
        )



def test_process_audit_rejects_git_audit_verification_run_fact_mismatch() -> None:
    base_input = _process_audit_builder_input()
    run = base_input.verification_runs[0]
    failed_run = run.model_copy(
        update={
            "exit_code": 1,
            "status": VerificationRunStatus.FAILED,
        }
    )

    with pytest.raises(
        (ProcessAuditError, ValidationError),
        match="git version audit verification run facts mismatch",
    ):
        build_process_audit_bundle(
            base_input.model_copy(update={"verification_runs": (failed_run,)})
        )


@pytest.mark.parametrize(
    ("field_name", "bad_value"),
    (
        ("consumer_ticket_refs", ()),
        ("consumer_ticket_refs", ("",)),
        ("consumer_ticket_refs", (None,)),
        ("consumer_ticket_refs", (123,)),
        ("acceptance_refs", ()),
        ("acceptance_refs", ("",)),
        ("acceptance_refs", (None,)),
        ("acceptance_refs", (123,)),
        ("evidence_refs", ()),
        ("evidence_refs", ("",)),
        ("evidence_refs", (None,)),
        ("evidence_refs", (123,)),
    ),
)
def test_artifact_lineage_rejects_empty_or_invalid_lineage_ref_containers(
    field_name: str,
    bad_value: tuple[object, ...],
) -> None:
    bundle = _build_bundle()
    lineage = _artifact_by_kind(bundle, ProcessAuditArtifactKind.ARTIFACT_LINEAGE)
    content = dict(lineage.content)
    primary_lineages = [dict(item) for item in content["lineages"]]
    primary_lineages[0][field_name] = bad_value
    content["lineages"] = primary_lineages
    broken_bundle = _replace_artifact_content(
        bundle,
        kind=ProcessAuditArtifactKind.ARTIFACT_LINEAGE,
        content=content,
    )

    with pytest.raises(
        (ProcessAuditError, ValidationError),
        match="artifact lineage missing producer attempt or closeout link",
    ):
        process_audit_readiness(broken_bundle)


def test_artifact_lineage_rejects_self_consistent_evidence_binding_mismatch() -> None:
    bundle = _build_bundle()
    lineage = _artifact_by_kind(bundle, ProcessAuditArtifactKind.ARTIFACT_LINEAGE)
    content = dict(lineage.content)
    primary_lineages = [dict(item) for item in content["lineages"]]
    bindings = [dict(item) for item in primary_lineages[0]["evidence_bindings"]]
    bindings[0]["verified_evidence_ref"] = "verified-evidence.ghost"
    primary_lineages[0]["evidence_bindings"] = bindings
    content["lineages"] = primary_lineages
    artifacts = tuple(
        artifact.model_copy(
            update={
                "content": content,
                "sha256": type(artifact.sha256)(
                    value=_artifact_content_hash(content, artifact.format)
                ),
            }
        )
        if artifact.kind is ProcessAuditArtifactKind.ARTIFACT_LINEAGE
        else artifact
        for artifact in bundle.artifacts
    )
    report = bundle.process_audit_report.model_copy(
        update={"expected_artifact_lineage_rows": tuple(primary_lineages)}
    )
    broken_bundle = _rehashed_process_audit_bundle(
        bundle,
        artifacts=artifacts,
        report=report,
    )

    with pytest.raises(
        (ProcessAuditError, ValidationError),
        match="artifact lineage evidence bindings must match evidence_refs",
    ):
        process_audit_readiness(broken_bundle)



def test_artifact_lineage_rejects_self_consistent_verifier_run_alias() -> None:
    bundle = _build_bundle()
    lineage = _artifact_by_kind(bundle, ProcessAuditArtifactKind.ARTIFACT_LINEAGE)
    content = dict(lineage.content)
    primary_lineages = [dict(item) for item in content["lineages"]]
    bindings = [dict(item) for item in primary_lineages[0]["evidence_bindings"]]
    bindings[0]["verifier_ref"] = bindings[0]["verification_run_ref"]
    primary_lineages[0]["evidence_bindings"] = bindings
    content["lineages"] = primary_lineages
    artifacts = tuple(
        artifact.model_copy(
            update={
                "content": content,
                "sha256": type(artifact.sha256)(
                    value=_artifact_content_hash(content, artifact.format)
                ),
            }
        )
        if artifact.kind is ProcessAuditArtifactKind.ARTIFACT_LINEAGE
        else artifact
        for artifact in bundle.artifacts
    )
    report = bundle.process_audit_report.model_copy(
        update={"expected_artifact_lineage_rows": tuple(primary_lineages)}
    )
    broken_bundle = _rehashed_process_audit_bundle(
        bundle,
        artifacts=artifacts,
        report=report,
    )

    with pytest.raises(
        (ProcessAuditError, ValidationError),
        match="artifact lineage evidence bindings must distinguish verifier and verification run",
    ):
        process_audit_readiness(broken_bundle)



def test_process_audit_readiness_rejects_tampered_artifact_lineage_primary_lineage() -> None:
    bundle = _build_bundle()
    lineage = _artifact_by_kind(bundle, ProcessAuditArtifactKind.ARTIFACT_LINEAGE)
    content = dict(lineage.content)
    primary_lineages = [dict(item) for item in content["lineages"]]
    primary_lineages[0] = {
        **primary_lineages[0],
        "path": "not-real.py",
        "sha256": "f" * 64,
        "producer_attempt_ref": "provider-attempt.fake",
    }
    content["lineages"] = primary_lineages
    broken_bundle = _replace_artifact_content(
        bundle,
        kind=ProcessAuditArtifactKind.ARTIFACT_LINEAGE,
        content=content,
    )

    with pytest.raises(
        (ProcessAuditError, ValidationError),
        match="artifact lineage inconsistent with expected source inventory lineage",
    ):
        process_audit_readiness(broken_bundle)


def test_artifact_lineage_rejects_self_consistent_duplicate_primary_rows() -> None:
    bundle = _build_bundle()
    lineage = _artifact_by_kind(bundle, ProcessAuditArtifactKind.ARTIFACT_LINEAGE)
    content = dict(lineage.content)
    primary_lineages = [dict(item) for item in content["lineages"]]
    primary_lineages.append(dict(primary_lineages[0]))
    content["lineages"] = primary_lineages
    artifacts = tuple(
        artifact.model_copy(
            update={
                "content": content,
                "sha256": type(artifact.sha256)(
                    value=_artifact_content_hash(content, artifact.format)
                ),
            }
        )
        if artifact.kind is ProcessAuditArtifactKind.ARTIFACT_LINEAGE
        else artifact
        for artifact in bundle.artifacts
    )
    report = bundle.process_audit_report.model_copy(
        update={"expected_artifact_lineage_rows": tuple(primary_lineages)}
    )
    broken_bundle = _rehashed_process_audit_bundle(
        bundle,
        artifacts=artifacts,
        report=report,
    )

    with pytest.raises(
        (ProcessAuditError, ValidationError),
        match="artifact lineage primary rows must be unique",
    ):
        process_audit_readiness(broken_bundle)



def test_process_audit_readiness_rejects_missing_artifact_lineage_primary_lineage() -> None:
    bundle = _build_bundle()
    lineage = _artifact_by_kind(bundle, ProcessAuditArtifactKind.ARTIFACT_LINEAGE)
    content = dict(lineage.content)
    content["lineages"] = tuple(content["lineages"][1:])
    broken_bundle = _replace_artifact_content(
        bundle,
        kind=ProcessAuditArtifactKind.ARTIFACT_LINEAGE,
        content=content,
    )

    with pytest.raises(
        (ProcessAuditError, ValidationError),
        match="artifact lineage inconsistent with expected source inventory lineage",
    ):
        process_audit_readiness(broken_bundle)


def test_checked_refs_stable_with_multiple_provider_runs_evidence_fallbacks_and_agent_context_refs() -> None:
    base_input = _process_audit_builder_input()
    provider_attempt_a = base_input.provider_attempt_refs[0]
    provider_attempt_b = ProviderAttemptRef(value="provider-attempt.zzz")
    run_a = base_input.verification_runs[0]
    run_b = run_a.model_copy(
        update={
            "verification_run_id": type(run_a.verification_run_id)(
                value="verification-run.zzz"
            ),
            "workspace_snapshot_ref": type(run_a.workspace_snapshot_ref)(
                value="workspace-snapshot.zzz"
            ),
        }
    )
    evidence_a = base_input.verified_evidence[0].model_copy(
        update={
            "fallback_decision_record_ref": FallbackDecisionRecordRef(
                value="fallback-decision.bbb"
            ),
            "fallback_decision_recorded_ref": FallbackDecisionRecordedRef(
                value="fallback-decision-recorded.bbb"
            ),
        }
    )
    evidence_b = base_input.verified_evidence[0].model_copy(
        update={
            "verified_evidence_id": VerifiedEvidenceRef(value="verified-evidence.zzz"),
            "fallback_decision_record_ref": FallbackDecisionRecordRef(
                value="fallback-decision.aaa"
            ),
            "fallback_decision_recorded_ref": FallbackDecisionRecordedRef(
                value="fallback-decision-recorded.aaa"
            ),
            "verification_run_refs": (run_b.verification_run_id,),
        }
    )
    row = base_input.final_evidence_table.rows[0].model_copy(
        update={
            "verified_evidence_refs": (
                evidence_a.verified_evidence_id,
                evidence_b.verified_evidence_id,
            )
        }
    )
    final_table = base_input.final_evidence_table.model_copy(update={"rows": (row,)})
    source_entry = base_input.source_inventory.entries[0].model_copy(
        update={
            "evidence_refs": (
                evidence_a.verified_evidence_id,
                evidence_b.verified_evidence_id,
            )
        }
    )
    source_inventory = base_input.source_inventory.model_copy(update={"entries": (source_entry,)})
    inventory_hash = source_inventory_hash(source_inventory)
    duplicate_binding_id = "git-command-evidence-binding.shared"
    git_bundle = _build_git_version_audit_bundle(
        source_inventory=source_inventory,
        verification_runs=(run_a, run_b),
        git_facts=_git_facts(source_inventory_hash=inventory_hash),
        command_evidence_bindings=(
            _command_binding(
                binding_id=duplicate_binding_id,
                verification_run_ref=run_b.verification_run_id,
                workspace_snapshot_ref=run_b.workspace_snapshot_ref,
                source_inventory_hash=inventory_hash,
            ),
            _command_binding(
                binding_id=duplicate_binding_id,
                verification_run_ref=run_a.verification_run_id,
                workspace_snapshot_ref=run_a.workspace_snapshot_ref,
                source_inventory_hash=inventory_hash,
            ),
        ),
    )
    base_agent_entry = base_input.agent_context_index.entries[0]
    agent_entry_a = base_agent_entry.model_copy(
        update={
            "entry_id": type(base_agent_entry.entry_id)(value="agent-context-entry.aaa"),
            "provider_attempt_refs": (provider_attempt_a,),
        }
    )
    agent_entry_b = base_agent_entry.model_copy(
        update={
            "entry_id": type(base_agent_entry.entry_id)(value="agent-context-entry.zzz"),
            "provider_attempt_refs": (provider_attempt_b,),
        }
    )
    agent_context_index = base_input.agent_context_index.model_copy(
        update={"entries": (agent_entry_a, agent_entry_b)}
    )
    reversed_agent_context_index = base_input.agent_context_index.model_copy(
        update={"entries": (agent_entry_b, agent_entry_a)}
    )
    sorted_input = base_input.model_copy(
        update={
            "source_inventory": source_inventory,
            "final_evidence_table": final_table,
            "verified_evidence": (evidence_a, evidence_b),
            "git_version_audit_bundle": git_bundle,
            "git_audit_readiness": git_version_audit_readiness(git_bundle),
            "agent_context_index": agent_context_index,
            "provider_attempt_refs": (provider_attempt_a, provider_attempt_b),
            "verification_runs": (run_a, run_b),
        }
    )
    reversed_input = sorted_input.model_copy(
        update={
            "agent_context_index": reversed_agent_context_index,
            "provider_attempt_refs": tuple(reversed(sorted_input.provider_attempt_refs)),
            "verification_runs": tuple(reversed(sorted_input.verification_runs)),
            "verified_evidence": tuple(reversed(sorted_input.verified_evidence)),
        }
    )

    first_bundle = build_process_audit_bundle(sorted_input)
    second_bundle = build_process_audit_bundle(reversed_input)
    expected_agent_refs = tuple(
        sorted(
            {
                "agent-context-entry.aaa",
                "agent-context-entry.zzz",
                base_agent_entry.snapshot.context_snapshot_id.value,
                base_agent_entry.snapshot.snapshot_fingerprint,
                base_agent_entry.snapshot.execution_package_ref.value,
            }
        )
    )

    assert first_bundle.checked_refs == second_bundle.checked_refs
    assert first_bundle.checked_refs.index(provider_attempt_a.value) < first_bundle.checked_refs.index(provider_attempt_b.value)
    assert first_bundle.checked_refs.index(run_a.verification_run_id.value) < first_bundle.checked_refs.index(run_b.verification_run_id.value)
    assert first_bundle.checked_refs.index(evidence_a.verified_evidence_id.value) < first_bundle.checked_refs.index(evidence_b.verified_evidence_id.value)
    assert first_bundle.checked_refs.index("fallback-decision.aaa") < first_bundle.checked_refs.index("fallback-decision.bbb")
    assert tuple(
        ref for ref in first_bundle.checked_refs if ref in expected_agent_refs
    ) == expected_agent_refs


def test_checked_refs_stable_under_collection_input_reordering() -> None:
    base_input = _process_audit_builder_input()
    reordered_inventory = base_input.source_inventory.model_copy(
        update={"entries": tuple(reversed(base_input.source_inventory.entries))}
    )
    reordered_git_bundle = _build_git_version_audit_bundle(
        source_inventory=reordered_inventory,
        git_facts=_git_facts(source_inventory_hash=source_inventory_hash(reordered_inventory)),
        command_evidence_bindings=(
            _command_binding(source_inventory_hash=source_inventory_hash(reordered_inventory)),
        ),
    )
    reordered_input = _process_audit_builder_input(
        source_inventory=reordered_inventory,
        git_version_audit_bundle=reordered_git_bundle,
        verified_evidence=tuple(reversed(base_input.verified_evidence)),
    ).model_copy(
        update={
            "verification_runs": tuple(reversed(base_input.verification_runs)),
            "provider_attempt_refs": tuple(reversed(base_input.provider_attempt_refs)),
        }
    )

    first_bundle = build_process_audit_bundle(base_input)
    second_bundle = build_process_audit_bundle(reordered_input)
    inventory_hashes = {
        source_inventory_hash(base_input.source_inventory).value,
        source_inventory_hash(reordered_inventory).value,
    }
    first_checked_refs = tuple(
        ref
        for ref in first_bundle.checked_refs
        if ref not in inventory_hashes
        and not ref.startswith("git-version-audit-bundle.")
        and not ref.startswith("git-version-audit-report.")
        and not ref.startswith("git-version-audit-hash-manifest.")
        and not ref.startswith("git-version-audit-facts.")
    )
    second_checked_refs = tuple(
        ref
        for ref in second_bundle.checked_refs
        if ref not in inventory_hashes
        and not ref.startswith("git-version-audit-bundle.")
        and not ref.startswith("git-version-audit-report.")
        and not ref.startswith("git-version-audit-hash-manifest.")
        and not ref.startswith("git-version-audit-facts.")
    )

    assert second_checked_refs == first_checked_refs
