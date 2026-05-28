from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from boardroom_os.audit.git_version_audit import GitCommandEvidenceBinding, git_version_audit_readiness, source_inventory_hash
from boardroom_os.audit.process_audit import build_process_audit_bundle, process_audit_readiness
from boardroom_os.closeout.closure import (
    assert_checked_refs_cover,
    assert_source_inventory_evidence_refs_resolve,
    assert_workspace_evidence_bundle_matches_runs,
)
from boardroom_os.closeout.gate import CloseoutGate
from boardroom_os.closeout.package import CloseoutPackage, build_closeout_package
from boardroom_os.events.record import EventRecord
from boardroom_os.events.types import ActorRef, EventId, EventPayloadRef, EventType
from boardroom_os.reducers.closeout_reducer import (
    CloseoutCommitPayload,
    CloseoutCommitVerdict,
    CloseoutProjection,
    CloseoutReducer,
    CloseoutReducerPayloadResolver,
    CloseoutTerminalStatus,
)
from tests.closeout.test_closeout_package import _GENERATED_AT, _closeout_package_builder_input
from tests.closeout.test_git_version_audit import _builder_input as _git_version_audit_builder_input
from tests.closeout.test_git_version_audit import _build_bundle as _build_git_version_audit_bundle
from tests.closeout.test_process_audit_artifacts import _process_audit_builder_input
from tests.closeout.test_closeout_gate import _ready_input as _closeout_gate_ready_input


_CLOSEOUT_PAYLOAD_REF = EventPayloadRef(value="payload.closeout.commit.v2-071f")


@dataclass(frozen=True)
class V2070FactChainFixture:
    events_before_closeout: tuple[EventRecord, ...]
    closeout_committed_event: EventRecord
    events_after_closeout: tuple[EventRecord, ...]
    closeout_package: CloseoutPackage
    closeout_commit_payload: CloseoutCommitPayload
    closeout_projection: CloseoutProjection
    process_audit_bundle: Any
    process_audit_readiness: Any
    git_version_audit_bundle: Any
    git_audit_readiness: Any
    replay_bundle: Any
    replay_readiness: Any
    source_inventory: Any
    final_evidence_table: Any
    workspace_evidence_bundle: Any
    verification_runs: tuple[Any, ...]
    verified_evidence: tuple[Any, ...]
    closeout_gate_result: Any


class InMemoryCloseoutResolver(CloseoutReducerPayloadResolver):
    def __init__(self, fixture: V2070FactChainFixture) -> None:
        self._commit_payloads = {
            _CLOSEOUT_PAYLOAD_REF.value: fixture.closeout_commit_payload,
        }
        self._packages = {
            fixture.closeout_package.closeout_package_id.value: fixture.closeout_package,
        }

    def resolve_closeout_commit(self, payload_ref: EventPayloadRef) -> CloseoutCommitPayload:
        return self._commit_payloads[payload_ref.value]

    def resolve_closeout_package(self, closeout_package_ref):
        return self._packages[closeout_package_ref.value]


def build_v2_070_fact_chain_fixture() -> V2070FactChainFixture:
    process_input = _process_audit_builder_input()
    gate_seed = _closeout_gate_ready_input()
    inventory_hash = source_inventory_hash(process_input.source_inventory)
    git_seed = _git_version_audit_builder_input(
        package_contract=process_input.package_contract,
        source_inventory=process_input.source_inventory,
        run_manifest=gate_seed.run_manifest,
        verification_runs=process_input.verification_runs,
        git_facts=_git_version_audit_builder_input().git_facts.model_copy(
            update={"source_inventory_hash": inventory_hash}
        ),
        command_evidence_bindings=tuple(
            GitCommandEvidenceBinding(
                binding_id=f"git-command-evidence-binding.{run.verification_run_id.value}",
                verification_run_ref=run.verification_run_id,
                run_manifest_ref=gate_seed.run_manifest.run_manifest_id,
                package_contract_ref=process_input.package_contract.package_contract_id,
                command_id=run.command_id,
                command=run.command,
                cwd=run.cwd,
                workspace_snapshot_ref=run.workspace_snapshot_ref,
                commit_sha=_git_version_audit_builder_input().git_facts.final_commit_sha,
                source_inventory_hash=inventory_hash,
            )
            for run in process_input.verification_runs
        ),
    )
    git_bundle = _build_git_version_audit_bundle(
        package_contract=process_input.package_contract,
        source_inventory=process_input.source_inventory,
        run_manifest=gate_seed.run_manifest,
        verification_runs=process_input.verification_runs,
        git_facts=git_seed.git_facts,
        command_evidence_bindings=git_seed.command_evidence_bindings,
    )
    git_readiness = git_version_audit_readiness(git_bundle)
    process_input = _process_audit_builder_input(
        git_version_audit_bundle=git_bundle,
        git_audit_readiness=git_readiness,
        replay_bundle=process_input.replay_bundle,
        replay_readiness=process_input.replay_readiness,
    )
    process_bundle = build_process_audit_bundle(process_input)
    process_readiness = process_audit_readiness(process_bundle)
    gate_input = gate_seed.model_copy(
        update={
            "package_contract": process_input.package_contract,
            "source_inventory": process_input.source_inventory,
            "run_manifest": gate_seed.run_manifest,
            "workspace_evidence_bundle": process_input.workspace_evidence_bundle,
            "final_evidence_table": process_input.final_evidence_table,
            "checker_verdict": process_input.checker_verdict,
            "verification_runs": process_input.verification_runs,
            "verified_evidence": process_input.verified_evidence,
            "provider_attempt_refs": process_input.provider_attempt_refs,
            "replay_readiness": process_input.replay_readiness,
            "git_audit_readiness": git_readiness,
            "process_audit_readiness": process_readiness,
        }
    )
    gate_result = CloseoutGate().evaluate(gate_input)
    package_input = _closeout_package_builder_input(
        closeout_gate_result=gate_result,
        source_inventory=process_input.source_inventory,
        final_evidence_table=process_input.final_evidence_table,
        replay_bundle=process_input.replay_bundle,
        replay_readiness=process_input.replay_readiness,
        process_audit_bundle=process_bundle,
        process_audit_readiness=process_readiness,
        git_version_audit_bundle=git_bundle,
        git_audit_readiness=git_readiness,
        graph_version=process_input.replay_bundle.attestations[0].event_window.last_graph_version,
        generated_at=_GENERATED_AT,
        run_id=process_input.run_id,
    )
    package = build_closeout_package(package_input)
    closeout_payload = CloseoutCommitPayload(
        closeout_package_ref=package.closeout_package_id,
        closeout_gate_result_ref=package.closeout_gate_result_ref,
        source_inventory_ref=package.source_inventory_ref,
        final_evidence_table_ref=package.final_evidence_table_ref,
        replay_bundle_ref=package.replay_bundle_ref,
        process_audit_bundle_ref=package.process_audit_bundle_ref,
        git_version_audit_bundle_ref=package.git_version_audit_bundle_ref,
        package_commit_ref=package.package_commit_ref,
        terminal_verdict=CloseoutCommitVerdict.PASSED,
    )
    closeout_event = EventRecord(
        event_id=EventId(value="evt.closeout.committed.v2-071f"),
        event_type=EventType.CLOSEOUT_COMMITTED,
        project_ref=package.project_ref,
        actor_ref=ActorRef(value="seat-closeout"),
        timestamp=_GENERATED_AT,
        graph_version=package.graph_version + 1,
        payload_refs=(_CLOSEOUT_PAYLOAD_REF,),
    )
    partial_fixture = V2070FactChainFixture(
        events_before_closeout=process_input.replay_bundle.events,
        closeout_committed_event=closeout_event,
        events_after_closeout=(*process_input.replay_bundle.events, closeout_event),
        closeout_package=package,
        closeout_commit_payload=closeout_payload,
        closeout_projection=CloseoutProjection(
            project_ref=package.project_ref,
            graph_version=package.graph_version,
            terminal_status=CloseoutTerminalStatus.OPEN,
            work_product_history_refs=(EventPayloadRef(value="placeholder.work-product"),),
            checked_refs=("placeholder.work-product",),
        ),
        process_audit_bundle=process_bundle,
        process_audit_readiness=process_readiness,
        git_version_audit_bundle=git_bundle,
        git_audit_readiness=git_readiness,
        replay_bundle=process_input.replay_bundle,
        replay_readiness=process_input.replay_readiness,
        source_inventory=process_input.source_inventory,
        final_evidence_table=process_input.final_evidence_table,
        workspace_evidence_bundle=process_input.workspace_evidence_bundle,
        verification_runs=process_input.verification_runs,
        verified_evidence=process_input.verified_evidence,
        closeout_gate_result=gate_result,
    )
    projection = CloseoutReducer(InMemoryCloseoutResolver(partial_fixture)).reduce(
        partial_fixture.events_after_closeout
    )
    return V2070FactChainFixture(
        **{
            **partial_fixture.__dict__,
            "closeout_projection": projection,
        }
    )


def assert_v2_070_fact_chain_closure(fixture: V2070FactChainFixture) -> None:
    assert_checked_refs_cover(
        fixture.closeout_package.closeout_package_id.value,
        (
            fixture.closeout_package.closeout_package_id,
            fixture.closeout_package.closeout_gate_result_ref,
            fixture.closeout_package.source_inventory_ref,
            fixture.closeout_package.final_evidence_table_ref,
            fixture.closeout_package.replay_bundle_ref,
            fixture.closeout_package.process_audit_bundle_ref,
            fixture.closeout_package.git_version_audit_bundle_ref,
            fixture.closeout_package.package_commit_ref,
        ),
        (*fixture.closeout_package.checked_refs, *fixture.closeout_projection.checked_refs),
    )
    assert_source_inventory_evidence_refs_resolve(
        fixture.closeout_package.closeout_package_id.value,
        fixture.source_inventory,
        fixture.verified_evidence,
    )
    assert_workspace_evidence_bundle_matches_runs(
        fixture.closeout_package.closeout_package_id.value,
        fixture.workspace_evidence_bundle,
        fixture.verification_runs,
    )


def test_v2_070_fact_chain_runs_from_event_log_to_closeout_closure() -> None:
    fixture = build_v2_070_fact_chain_fixture()

    assert all(event.event_type is not EventType.CLOSEOUT_COMMITTED for event in fixture.events_before_closeout)
    assert fixture.closeout_committed_event.event_type is EventType.CLOSEOUT_COMMITTED
    assert fixture.events_after_closeout[-1] == fixture.closeout_committed_event
    assert fixture.closeout_projection.terminal_status is CloseoutTerminalStatus.SUCCEEDED
    assert fixture.closeout_projection.closeout_package_ref == fixture.closeout_package.closeout_package_id
    assert fixture.replay_bundle.events == fixture.events_before_closeout
    assert fixture.closeout_package.graph_version == fixture.replay_bundle.attestations[0].event_window.last_graph_version
    assert_v2_070_fact_chain_closure(fixture)


def test_v2_070_fact_chain_refs_and_readiness_are_stable() -> None:
    first = build_v2_070_fact_chain_fixture()
    second = build_v2_070_fact_chain_fixture()

    assert first.replay_bundle.replay_bundle_id == second.replay_bundle.replay_bundle_id
    assert first.replay_readiness == second.replay_readiness
    assert first.process_audit_bundle.process_audit_bundle_id == second.process_audit_bundle.process_audit_bundle_id
    assert first.process_audit_readiness == second.process_audit_readiness
    assert first.git_version_audit_bundle.git_version_audit_bundle_id == second.git_version_audit_bundle.git_version_audit_bundle_id
    assert first.git_audit_readiness == second.git_audit_readiness
    assert first.closeout_package.closeout_package_id == second.closeout_package.closeout_package_id
    assert first.closeout_projection.checked_refs == second.closeout_projection.checked_refs
