from __future__ import annotations

import pytest
from pydantic import ValidationError

from boardroom_os.audit.process_audit import ProcessAuditArtifactKind, ProcessAuditError, build_process_audit_bundle, process_audit_readiness
from boardroom_os.audit.replay_bundle import ReplayBundleError, ReplayContentHash, replay_bundle_readiness
from boardroom_os.contracts.refs import namespaced_ref
from boardroom_os.graph.ticket import TicketId
from tests.closeout.test_closeout_package_boundary import ProcessAuditArtifactRef, ProcessAuditContentRef
from tests.closeout.test_process_audit_artifacts import _process_audit_builder_input
from tests.closeout.test_process_audit_artifacts import _artifact_by_kind
from tests.closeout.test_process_audit_fact_chain import _build_process_audit_with_source_inventory
from tests.closeout.test_v2_070_fact_chain_end_to_end import assert_v2_070_fact_chain_closure, build_v2_070_fact_chain_fixture
from tests.negative.test_process_audit_construction_loop_rejected import _replace_artifact_content
from tests.negative.test_process_audit_construction_loop_rejected import (
    _TicketWithoutOwnerSeatRef,
    _TicketWithoutTicketRef,
    _ticket_graph_summary_with,
)
from tests.negative.test_replay_payload_manifest_tampering_rejected import PayloadResolver, _canonical_sha256


def test_p1_1_payload_sha256_tampering_blocks_fact_chain_readiness() -> None:
    fixture = build_v2_070_fact_chain_fixture()
    tampered_entries = tuple(
        entry.model_copy(update={"sha256": ReplayContentHash(value=_canonical_sha256("tampered"))})
        if index == 0
        else entry
        for index, entry in enumerate(fixture.replay_bundle.payload_manifest.entries)
    )
    tampered_manifest = fixture.replay_bundle.payload_manifest.model_copy(update={"entries": tampered_entries})
    tampered_hash_manifest = fixture.replay_bundle.hash_manifest.model_copy(
        update={"payload_manifest_hash": type(fixture.replay_bundle.hash_manifest.payload_manifest_hash)(value=tampered_manifest.payload_manifest_hash)}
    )
    tampered_bundle = fixture.replay_bundle.model_copy(
        update={"payload_manifest": tampered_manifest, "hash_manifest": tampered_hash_manifest}
    )
    payloads = {entry.content_ref.value: f"payload.{entry.content_ref.value}" for entry in fixture.replay_bundle.payload_manifest.entries}

    with pytest.raises(ReplayBundleError, match="payload manifest sha256 mismatch"):
        replay_bundle_readiness(tampered_bundle, payload_resolver=PayloadResolver(payloads))


def test_p1_2a_missing_owner_seat_ref_fails_before_unknown_placeholder_can_be_emitted() -> None:
    fixture = build_v2_070_fact_chain_fixture()
    valid_ticket = _process_audit_builder_input().ticket_graph_summary.tickets[0]
    broken_ticket = _TicketWithoutOwnerSeatRef(
        ticket_ref=valid_ticket.ticket_ref,
        status=valid_ticket.status,
        acceptance_refs=valid_ticket.acceptance_refs,
        source_surface_refs=valid_ticket.source_surface_refs,
    )

    assert_v2_070_fact_chain_closure(fixture)

    with pytest.raises((ProcessAuditError, ValidationError), match="missing owner_seat_ref"):
        build_process_audit_bundle(
            _process_audit_builder_input(
                ticket_graph_summary=_ticket_graph_summary_with(broken_ticket)
            )
        )


def test_p1_2b_missing_ticket_ref_fails_before_generic_ticket_placeholder_can_be_emitted() -> None:
    fixture = build_v2_070_fact_chain_fixture()
    valid_ticket = _process_audit_builder_input().ticket_graph_summary.tickets[0]
    broken_ticket = _TicketWithoutTicketRef(
        status=valid_ticket.status,
        owner_seat_ref=valid_ticket.owner_seat_ref,
        acceptance_refs=valid_ticket.acceptance_refs,
        source_surface_refs=valid_ticket.source_surface_refs,
    )

    assert_v2_070_fact_chain_closure(fixture)

    with pytest.raises((ProcessAuditError, ValidationError), match="missing ticket_ref"):
        build_process_audit_bundle(
            _process_audit_builder_input(
                ticket_graph_summary=_ticket_graph_summary_with(broken_ticket)
            )
        )


def test_p1_3_artifact_lineage_keeps_producer_and_consumer_tickets_separate_in_fact_chain() -> None:
    fixture = build_v2_070_fact_chain_fixture()
    source_entry = fixture.source_inventory.entries[0]
    changed_entry = source_entry.model_copy(
        update={
            "producer_ticket_ref": TicketId(value="ticket-a"),
            "consumer_ticket_refs": (TicketId(value="ticket-b"),),
        }
    )
    changed_inventory = fixture.source_inventory.model_copy(
        update={"entries": (changed_entry, *fixture.source_inventory.entries[1:])}
    )
    base_ticket = __import__("tests.closeout.test_process_audit_artifacts", fromlist=["_process_audit_builder_input"])._process_audit_builder_input().ticket_graph_summary.tickets[0]
    ticket_graph_summary = __import__("tests.closeout.test_process_audit_artifacts", fromlist=["_process_audit_builder_input"])._process_audit_builder_input().ticket_graph_summary.model_copy(
        update={
            "tickets": (
                base_ticket,
                base_ticket.model_copy(update={"ticket_ref": "ticket-a", "acceptance_refs": tuple(source_entry.acceptance_refs), "source_surface_refs": (source_entry.source_surface_ref.value,)}),
                base_ticket.model_copy(update={"ticket_ref": "ticket-b", "acceptance_refs": tuple(source_entry.acceptance_refs), "source_surface_refs": (source_entry.source_surface_ref.value,)}),
            )
        }
    )

    bundle = _build_process_audit_with_source_inventory(changed_inventory, ticket_graph_summary=ticket_graph_summary)
    lineage = _artifact_by_kind(bundle, ProcessAuditArtifactKind.ARTIFACT_LINEAGE)
    row = next(item for item in lineage.content["lineages"] if item["path"] == source_entry.path.value)

    assert row["producer_ticket_ref"] == "ticket-a"
    assert row["consumer_ticket_refs"] == ["ticket-b"]
    assert row["consumer_ticket_refs"] != ["ticket-a"]


def test_p1_4_unexpected_fallback_lineage_is_rejected_in_fact_chain_bundle() -> None:
    fixture = build_v2_070_fact_chain_fixture()
    lineage = _artifact_by_kind(fixture.process_audit_bundle, ProcessAuditArtifactKind.ARTIFACT_LINEAGE)
    evidence_map = _artifact_by_kind(fixture.process_audit_bundle, ProcessAuditArtifactKind.EVIDENCE_MAP)
    content = dict(lineage.content)
    content["fallback_lineages"] = (
        {
            "fallback_decision_record_ref": "fallback-decision.unexpected",
            "fallback_decision_recorded_ref": None,
            "verifier_ref": "runner.local",
            "evidence_map_ref": evidence_map.artifact_id.value,
        },
    )
    broken_bundle = _replace_artifact_content(
        fixture.process_audit_bundle,
        kind=ProcessAuditArtifactKind.ARTIFACT_LINEAGE,
        content=content,
    )

    with pytest.raises((ProcessAuditError, ValidationError), match="fallback lineage decision refs"):
        process_audit_readiness(broken_bundle)


def test_p1_5a_cross_project_fact_set_id_cannot_bind_into_fact_chain() -> None:
    fixture = build_v2_070_fact_chain_fixture()
    tampered_facts = fixture.git_version_audit_bundle.fact_set.model_copy(
        update={"fact_set_id": type(fixture.git_version_audit_bundle.fact_set.fact_set_id)(value="git-version-audit-facts.project-other.123456789abc")}
    )
    tampered_bundle = fixture.git_version_audit_bundle.model_copy(update={"fact_set": tampered_facts})

    with pytest.raises((ValueError, ValidationError), match="fact_set|hash manifest|namespace"):
        __import__("boardroom_os.audit.git_version_audit", fromlist=["git_version_audit_readiness"]).git_version_audit_readiness(tampered_bundle)


def test_p1_5b_cross_run_process_audit_artifact_ref_is_rejected_in_fact_chain() -> None:
    fixture = build_v2_070_fact_chain_fixture()
    timeline = _artifact_by_kind(fixture.process_audit_bundle, ProcessAuditArtifactKind.TIMELINE)
    cross_run_ref = ProcessAuditArtifactRef(
        value=namespaced_ref(
            kind="process-audit-artifact",
            project_ref=fixture.process_audit_bundle.project_ref.value,
            content_hash=timeline.sha256.value,
            run_id="run-other",
            extra_suffix=timeline.kind.value,
        )
    )
    cross_run_content_ref = ProcessAuditContentRef(
        value=namespaced_ref(
            kind="process-audit-content",
            project_ref=fixture.process_audit_bundle.project_ref.value,
            content_hash=timeline.sha256.value,
            run_id="run-other",
            extra_suffix=timeline.kind.value,
        )
    )
    broken_timeline = timeline.model_copy(update={"artifact_id": cross_run_ref, "content_ref": cross_run_content_ref})
    artifacts = tuple(broken_timeline if artifact is timeline else artifact for artifact in fixture.process_audit_bundle.artifacts)
    entries = tuple(
        entry.model_copy(update={"artifact_ref": cross_run_ref, "content_ref": cross_run_content_ref})
        if entry.path == timeline.path
        else entry
        for entry in fixture.process_audit_bundle.artifact_manifest.entries
    )
    artifact_manifest = fixture.process_audit_bundle.artifact_manifest.model_copy(update={"entries": entries})
    report = fixture.process_audit_bundle.process_audit_report.model_copy(update={"timeline_ref": cross_run_ref})
    hash_manifest = fixture.process_audit_bundle.hash_manifest.model_copy(
        update={
            "artifact_manifest_hash": type(fixture.process_audit_bundle.hash_manifest.artifact_manifest_hash)(
                value=__import__("boardroom_os.audit.process_audit", fromlist=["_hash_model"])._hash_model(artifact_manifest)
            ),
            "process_audit_report_hash": type(fixture.process_audit_bundle.hash_manifest.process_audit_report_hash)(
                value=__import__("boardroom_os.audit.process_audit", fromlist=["_hash_model"])._hash_model(report)
            ),
        }
    )
    broken_bundle = fixture.process_audit_bundle.model_copy(
        update={"artifacts": artifacts, "artifact_manifest": artifact_manifest, "process_audit_report": report, "hash_manifest": hash_manifest}
    )

    with pytest.raises((ProcessAuditError, ValidationError), match="namespace binding mismatch"):
        process_audit_readiness(broken_bundle)
