from __future__ import annotations

from typing import Any

import pytest
from pydantic import BaseModel, ConfigDict

from boardroom_os.agents.seat import AgentSeatRef
from boardroom_os.audit.git_version_audit import (
    git_version_audit_readiness,
    source_inventory_hash,
)
from boardroom_os.audit.process_audit import (
    ProcessAuditArtifactKind,
    ProcessAuditBuilderInput,
    ProcessAuditError,
    build_process_audit_bundle,
    process_audit_readiness,
)
from boardroom_os.evidence.fallback_registry import FallbackDecisionRecordRef
from boardroom_os.evidence.verifier import FallbackDecisionRecordedRef, VerifiedEvidenceRef
from boardroom_os.events.types import EventType
from boardroom_os.execution.context_index import (
    AgentContextIndex,
    AgentContextIndexEntry,
    AgentContextIndexEntryId,
    ProviderAttemptRef,
    build_agent_context_snapshot,
)
from boardroom_os.graph.ticket import TicketId
from tests.closeout.test_git_version_audit import (
    _build_bundle as _build_git_version_audit_bundle,
)
from tests.closeout.test_git_version_audit import _command_binding, _command_bindings, _git_facts
from tests.closeout.test_process_audit_artifacts import (
    _agent_context_execution_package,
    _artifact_by_kind,
    _build_bundle,
    _process_audit_builder_input,
    _process_audit_events,
)


class _AgentContextEntryWithTopLevelFallbacks(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    entry_id: object
    snapshot: object
    provider_attempt_refs: tuple[object, ...]
    execution_package_ref: str
    model_execution_profile: dict[str, str]


class _AgentContextIndexWithTopLevelFallbacks(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    entries: tuple[_AgentContextEntryWithTopLevelFallbacks, ...]


def _expected_timeline_kind(event_type: EventType) -> str:
    if event_type is EventType.TICKET_LEASED:
        return "ticket_started"
    return event_type.value


def _git_bundle_for_source_inventory(source_inventory: Any):
    inventory_hash = source_inventory_hash(source_inventory)
    return _build_git_version_audit_bundle(
        source_inventory=source_inventory,
        git_facts=_git_facts(source_inventory_hash=inventory_hash),
        command_evidence_bindings=tuple(
            binding.model_copy(update={"source_inventory_hash": inventory_hash})
            for binding in _command_bindings()
        ),
    )


def _build_process_audit_with_source_inventory(
    source_inventory: Any,
    *,
    ticket_graph_summary: Any | None = None,
):
    git_bundle = _git_bundle_for_source_inventory(source_inventory)
    return build_process_audit_bundle(
        _process_audit_builder_input(
            source_inventory=source_inventory,
            ticket_graph_summary=ticket_graph_summary,
            git_version_audit_bundle=git_bundle,
            git_audit_readiness=git_version_audit_readiness(git_bundle),
        )
    )


def test_process_audit_uses_replay_bundle_events_before_closeout_package() -> None:
    builder_input = _process_audit_builder_input()

    bundle = build_process_audit_bundle(builder_input)
    timeline = _artifact_by_kind(bundle, ProcessAuditArtifactKind.TIMELINE)

    assert "closeout_package" not in ProcessAuditBuilderInput.model_fields
    assert all(
        event.event_type is not EventType.CLOSEOUT_COMMITTED
        for event in builder_input.replay_bundle.events
    )
    assert [event["event_ref"] for event in timeline.content["events"]] == [
        event.event_id.value for event in builder_input.replay_bundle.events
    ]
    assert "closeout_committed" not in {
        event["kind"] for event in timeline.content["events"]
    }
    assert process_audit_readiness(bundle).timeline_key_events_present is True


def test_process_audit_timeline_matches_replay_bundle_events_exactly() -> None:
    builder_input = _process_audit_builder_input()
    bundle = build_process_audit_bundle(builder_input)

    timeline = _artifact_by_kind(bundle, ProcessAuditArtifactKind.TIMELINE)
    actual_events = timeline.content["events"]

    assert [
        {
            "event_ref": event["event_ref"],
            "kind": event["kind"],
            "graph_version": event["graph_version"],
            "actor_ref": event["actor_ref"],
            "payload_refs": event["payload_refs"],
        }
        for event in actual_events
    ] == [
        {
            "event_ref": event.event_id.value,
            "kind": _expected_timeline_kind(event.event_type),
            "graph_version": event.graph_version,
            "actor_ref": event.actor_ref.value,
            "payload_refs": [payload_ref.value for payload_ref in event.payload_refs],
        }
        for event in builder_input.replay_bundle.events
    ]


def test_artifact_lineage_separates_producer_and_consumer_tickets() -> None:
    base_input = _process_audit_builder_input()
    source_entry = base_input.source_inventory.entries[0]
    changed_entry = source_entry.model_copy(
        update={
            "producer_ticket_ref": TicketId(value="ticket-a"),
            "consumer_ticket_refs": (TicketId(value="ticket-b"),),
        }
    )
    changed_inventory = base_input.source_inventory.model_copy(
        update={"entries": (changed_entry, *base_input.source_inventory.entries[1:])}
    )
    ticket = base_input.ticket_graph_summary.tickets[0]
    consumer_ticket = ticket.model_copy(update={"ticket_ref": "ticket-b"})
    ticket_graph_summary = base_input.ticket_graph_summary.model_copy(
        update={"tickets": (*base_input.ticket_graph_summary.tickets, consumer_ticket)}
    )

    bundle = _build_process_audit_with_source_inventory(
        changed_inventory,
        ticket_graph_summary=ticket_graph_summary,
    )
    lineage = _artifact_by_kind(bundle, ProcessAuditArtifactKind.ARTIFACT_LINEAGE)
    lineage_for_entry = next(
        item
        for item in lineage.content["lineages"]
        if item["path"] == source_entry.path.value
    )

    assert lineage_for_entry["producer_ticket_ref"] == "ticket-a"
    assert lineage_for_entry["consumer_ticket_refs"] == ["ticket-b"]
    assert lineage_for_entry["consumer_ticket_refs"] != ["ticket-a"]


def test_artifact_lineage_hash_stable_under_source_inventory_entry_reordering() -> None:
    base_input = _process_audit_builder_input()
    reversed_inventory = base_input.source_inventory.model_copy(
        update={"entries": tuple(reversed(base_input.source_inventory.entries))}
    )
    git_bundle = _git_bundle_for_source_inventory(reversed_inventory)

    first_bundle = build_process_audit_bundle(base_input)
    second_bundle = build_process_audit_bundle(
        _process_audit_builder_input(
            source_inventory=reversed_inventory,
            git_version_audit_bundle=git_bundle,
            git_audit_readiness=git_version_audit_readiness(git_bundle),
        )
    )
    first_lineage = _artifact_by_kind(
        first_bundle,
        ProcessAuditArtifactKind.ARTIFACT_LINEAGE,
    )
    second_lineage = _artifact_by_kind(
        second_bundle,
        ProcessAuditArtifactKind.ARTIFACT_LINEAGE,
    )

    assert first_lineage.content["lineages"] == second_lineage.content["lineages"]
    assert first_lineage.sha256 == second_lineage.sha256


def test_primary_artifact_lineage_closes_source_to_evidence_and_manifest() -> None:
    builder_input = _process_audit_builder_input()
    bundle = build_process_audit_bundle(builder_input)
    lineage = _artifact_by_kind(bundle, ProcessAuditArtifactKind.ARTIFACT_LINEAGE)
    evidence_map = _artifact_by_kind(bundle, ProcessAuditArtifactKind.EVIDENCE_MAP)
    row = lineage.content["lineages"][0]

    assert lineage.content["checker_verdict_ref"] == builder_input.checker_verdict.checker_verdict_id.value
    assert "closeout_related_ref" not in row
    assert row["evidence_map_ref"] == evidence_map.artifact_id.value
    assert row["evidence_map_ref"] != builder_input.final_evidence_table.final_evidence_table_id.value
    assert row["final_evidence_table_ref"] == builder_input.final_evidence_table.final_evidence_table_id.value
    runs_by_ref = {
        run.verification_run_id: run for run in builder_input.verification_runs
    }
    assert row["evidence_bindings"] == [
        {
            "evidence_claim_ref": evidence.evidence_claim_ref.value,
            "verified_evidence_ref": evidence.verified_evidence_id.value,
            "verifier_ref": runs_by_ref[evidence.verification_run_refs[0]].runner_ref.value,
            "verification_run_ref": evidence.verification_run_refs[0].value,
            "run_manifest_ref": builder_input.run_manifest.run_manifest_id.value,
        }
        for evidence in builder_input.verified_evidence
    ]
    for binding in row["evidence_bindings"]:
        assert binding["verifier_ref"] != binding["verification_run_ref"]



def test_fallback_artifact_lineage_uses_verifier_runner_ref() -> None:
    base_input = _process_audit_builder_input()
    fallback_evidence = base_input.verified_evidence[0].model_copy(
        update={
            "fallback_decision_record_ref": FallbackDecisionRecordRef(
                value="fallback-decision.verified-evidence.app"
            ),
            "fallback_decision_recorded_ref": FallbackDecisionRecordedRef(
                value="fallback-decision-recorded.verified-evidence.app"
            ),
        }
    )

    bundle = build_process_audit_bundle(
        _process_audit_builder_input(
            verified_evidence=(fallback_evidence, *base_input.verified_evidence[1:])
        )
    )
    lineage = _artifact_by_kind(bundle, ProcessAuditArtifactKind.ARTIFACT_LINEAGE)
    evidence_map = _artifact_by_kind(bundle, ProcessAuditArtifactKind.EVIDENCE_MAP)
    fallback_lineage = lineage.content["fallback_lineages"][0]

    assert fallback_lineage["verifier_ref"] == base_input.verification_runs[0].runner_ref.value
    assert fallback_lineage["verifier_ref"] != base_input.verification_runs[0].verification_run_id.value
    assert fallback_lineage["evidence_map_ref"] == evidence_map.artifact_id.value
    assert "closeout_related_ref" not in fallback_lineage



def test_ticket_graph_markdown_uses_real_ticket_fields() -> None:
    builder_input = _process_audit_builder_input()
    ticket = builder_input.ticket_graph_summary.tickets[0]

    bundle = build_process_audit_bundle(builder_input)
    ticket_graph = _artifact_by_kind(bundle, ProcessAuditArtifactKind.TICKET_GRAPH)
    markdown = str(ticket_graph.content)

    assert f"## {ticket.ticket_ref}" in markdown
    assert f"Status: {ticket.status}" in markdown
    assert f"Owner seat: {ticket.owner_seat_ref}" in markdown
    assert "unknown" not in markdown
    assert "## ticket" not in markdown.splitlines()


def test_agent_context_index_rejects_legacy_top_level_fallbacks() -> None:
    base_input = _process_audit_builder_input()
    base_entry = base_input.agent_context_index.entries[0]
    agent_context_index = _AgentContextIndexWithTopLevelFallbacks(
        entries=(
            _AgentContextEntryWithTopLevelFallbacks(
                entry_id=base_entry.entry_id,
                snapshot=base_entry.snapshot,
                provider_attempt_refs=base_entry.provider_attempt_refs,
                execution_package_ref="execution-package.legacy-top-level",
                model_execution_profile={"model": "legacy-top-level"},
            ),
        )
    )

    with pytest.raises(
        (ProcessAuditError, ValueError),
        match="agent_context_index must be AgentContextIndex|AgentContextIndex",
    ):
        _process_audit_builder_input(agent_context_index=agent_context_index)


def _stable_hash_input_with_order(
    *,
    provider_attempt_refs: tuple[ProviderAttemptRef, ProviderAttemptRef],
    verification_run_order: tuple[int, int],
    evidence_order: tuple[int, int],
    agent_context_entry_order: tuple[int, int],
):
    base_input = _process_audit_builder_input()
    provider_alpha = ProviderAttemptRef(value="provider-attempt.alpha")
    provider_beta = ProviderAttemptRef(value="provider-attempt.beta")
    first_run, second_run = base_input.verification_runs
    first_run_ref = first_run.verification_run_id
    verification_runs = (first_run, second_run)

    first_evidence = base_input.verified_evidence[0].model_copy(
        update={
            "producer_attempt_ref": provider_alpha,
            "verification_run_refs": (first_run_ref,),
            "fallback_decision_record_ref": FallbackDecisionRecordRef(
                value="fallback-decision.alpha"
            ),
            "fallback_decision_recorded_ref": FallbackDecisionRecordedRef(
                value="fallback-decision-recorded.alpha"
            ),
        }
    )
    second_evidence = base_input.verified_evidence[1].model_copy(
        update={
            "producer_attempt_ref": provider_beta,
            "verification_run_refs": (second_run.verification_run_id,),
            "fallback_decision_record_ref": FallbackDecisionRecordRef(
                value="fallback-decision.beta"
            ),
            "fallback_decision_recorded_ref": FallbackDecisionRecordedRef(
                value="fallback-decision-recorded.beta"
            ),
        }
    )
    verified_evidence = (first_evidence, second_evidence)
    source_inventory = base_input.source_inventory.model_copy(
        update={
            "entries": tuple(
                entry.model_copy(update={"producer_attempt_ref": provider_alpha})
                for entry in base_input.source_inventory.entries
            )
        }
    )

    final_evidence_table = base_input.final_evidence_table.model_copy(
        update={
            "rows": (
                base_input.final_evidence_table.rows[0].model_copy(
                    update={
                        "verified_evidence_refs": (
                            first_evidence.verified_evidence_id,
                            second_evidence.verified_evidence_id,
                        )
                    }
                ),
            )
        }
    )
    workspace_evidence_bundle = base_input.workspace_evidence_bundle.model_copy(
        update={
            "verification_run_refs": tuple(
                sorted(
                    (run.verification_run_id for run in verification_runs),
                    key=lambda ref: ref.value,
                )
            ),
            "verified_evidence_refs": tuple(
                sorted(
                    (evidence.verified_evidence_id for evidence in verified_evidence),
                    key=lambda ref: ref.value,
                )
            ),
        }
    )

    second_execution_package = _agent_context_execution_package().model_copy(
        update={
            "execution_package_id": type(_agent_context_execution_package().execution_package_id)(
                value="execution-package.worker.extra"
            ),
            "ticket_ref": TicketId(value="ticket.extra"),
            "graph_version": 8,
            "seat_ref": AgentSeatRef(value="seat-worker-extra"),
            "objective": "Implement extra acceptance evidence.",
        }
    )
    first_entry = base_input.agent_context_index.entries[0].model_copy(
        update={
            "provider_attempt_refs": (provider_alpha,),
        }
    )
    second_entry = AgentContextIndexEntry(
        entry_id=AgentContextIndexEntryId(value="agent-context-entry.worker.extra"),
        snapshot=build_agent_context_snapshot(second_execution_package),
        provider_attempt_refs=(provider_beta,),
    )
    agent_context_entries = (first_entry, second_entry)
    agent_context_index = AgentContextIndex(
        entries=tuple(agent_context_entries[index] for index in agent_context_entry_order)
    )

    ordered_verification_runs = tuple(
        verification_runs[index] for index in verification_run_order
    )
    git_verification_runs = tuple(
        sorted(verification_runs, key=lambda run: run.verification_run_id.value)
    )
    run_index_by_ref = {
        run.verification_run_id: index
        for index, run in enumerate(base_input.verification_runs)
    }
    inventory_hash = source_inventory_hash(source_inventory)
    git_bundle = _build_git_version_audit_bundle(
        source_inventory=source_inventory,
        git_facts=_git_facts(source_inventory_hash=inventory_hash),
        verification_runs=git_verification_runs,
        command_evidence_bindings=tuple(
            _command_binding(
                run_index=run_index_by_ref[run.verification_run_id],
                binding_id=f"git-command-evidence-binding.{run.verification_run_id.value}",
                verification_run_ref=run.verification_run_id,
                command_id=run.command_id,
                command=run.command,
                cwd=run.cwd,
                workspace_snapshot_ref=run.workspace_snapshot_ref,
                source_inventory_hash=inventory_hash,
            )
            for run in git_verification_runs
        ),
    )
    return ProcessAuditBuilderInput(
        project_ref=base_input.project_ref,
        generated_at=base_input.generated_at,
        package_contract=base_input.package_contract,
        acceptance_contract=base_input.acceptance_contract,
        agent_context_index=agent_context_index,
        ticket_graph_summary=base_input.ticket_graph_summary,
        source_inventory=source_inventory,
        run_manifest=base_input.run_manifest,
        workspace_evidence_bundle=workspace_evidence_bundle,
        final_evidence_table=final_evidence_table,
        checker_verdict=base_input.checker_verdict,
        verification_runs=ordered_verification_runs,
        verified_evidence=tuple(verified_evidence[index] for index in evidence_order),
        provider_attempt_refs=provider_attempt_refs,
        replay_bundle=base_input.replay_bundle,
        replay_readiness=base_input.replay_readiness,
        git_version_audit_bundle=git_bundle,
        git_audit_readiness=git_version_audit_readiness(git_bundle),
        run_id=base_input.run_id,
    )


def test_checked_refs_hash_stable_under_reordering() -> None:
    ascending_provider_refs = (
        ProviderAttemptRef(value="provider-attempt.alpha"),
        ProviderAttemptRef(value="provider-attempt.beta"),
    )
    descending_provider_refs = tuple(reversed(ascending_provider_refs))

    first_bundle = build_process_audit_bundle(
        _stable_hash_input_with_order(
            provider_attempt_refs=ascending_provider_refs,
            verification_run_order=(0, 1),
            evidence_order=(0, 1),
            agent_context_entry_order=(0, 1),
        )
    )
    second_bundle = build_process_audit_bundle(
        _stable_hash_input_with_order(
            provider_attempt_refs=descending_provider_refs,
            verification_run_order=(1, 0),
            evidence_order=(1, 0),
            agent_context_entry_order=(1, 0),
        )
    )
    first_lineage = _artifact_by_kind(
        first_bundle,
        ProcessAuditArtifactKind.ARTIFACT_LINEAGE,
    )
    second_lineage = _artifact_by_kind(
        second_bundle,
        ProcessAuditArtifactKind.ARTIFACT_LINEAGE,
    )

    assert [
        lineage["fallback_decision_record_ref"]
        for lineage in first_lineage.content["fallback_lineages"]
    ] == [
        "fallback-decision.alpha",
        "fallback-decision.beta",
    ]
    assert first_lineage.content["fallback_lineages"] == second_lineage.content[
        "fallback_lineages"
    ]
    assert first_bundle.checked_refs == second_bundle.checked_refs
    assert (
        first_bundle.hash_manifest.process_audit_report_hash.value
        == second_bundle.hash_manifest.process_audit_report_hash.value
    )
    assert first_bundle.hash_manifest.bundle_payload_hash.value == (
        second_bundle.hash_manifest.bundle_payload_hash.value
    )
    assert first_bundle.bundle_hash == second_bundle.bundle_hash
