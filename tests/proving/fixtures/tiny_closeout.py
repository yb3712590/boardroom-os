from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Mapping

from pydantic import BaseModel, ConfigDict

from boardroom_os.adapters.git_audit import GitAuditAdapter, GitCommandTransport
from boardroom_os.audit.git_version_audit import (
    GitCommandEvidenceBinding,
    GitVersionAuditBuilderInput,
    build_git_version_audit_bundle,
    git_version_audit_readiness,
    source_inventory_hash,
)
from boardroom_os.audit.process_audit import (
    ProcessAuditArtifactKind,
    ProcessAuditBuilderInput,
    ProcessAuditBundle,
    build_process_audit_bundle,
    process_audit_readiness,
)
from boardroom_os.audit.replay_bundle import (
    ReplayArtifactManifestEntry,
    ReplayBundle,
    ReplayBundleBuilderInput,
    ReplayContentHash,
    ReplayContentRef,
    ReplayManifestEntry,
    ReplayManifestKind,
    ReplayManifestRef,
    ReplayPayloadResolver,
    ReplayReportRef,
    build_replay_bundle,
    replay_bundle_readiness,
    _payload_bytes_for_hash,
)
from boardroom_os.checker.verdict import (
    CheckerVerdict,
    CheckerVerdictStatus,
    SourceDiffRef,
)
from boardroom_os.closeout.gate import (
    CloseoutCommandEvidenceBinding,
    CloseoutGate,
    CloseoutGateInput,
    CloseoutGateResult,
)
from boardroom_os.closeout.package import (
    CloseoutPackage,
    CloseoutPackageBuilderInput,
    build_closeout_package,
)
from boardroom_os.contracts.types import ContractId
from boardroom_os.events.record import EventRecord
from boardroom_os.events.types import ActorRef, EventId, EventPayloadRef, EventType
from boardroom_os.execution.context_index import (
    AgentContextIndex,
    AgentContextIndexEntry,
    AgentContextIndexEntryId,
    ProviderAttemptRef,
    build_agent_context_snapshot,
)
from boardroom_os.execution.verification_run import VerificationRun
from boardroom_os.execution.work_product import WorkProductRef
from boardroom_os.graph.projection import TicketGraphProjector
from boardroom_os.graph.seat_assignment import SeatAssignmentProjector
from boardroom_os.graph.ticket import TicketId, TicketStatus
from boardroom_os.providers.adapter import ProviderRequest
from boardroom_os.providers.attempt import ProviderAttempt
from boardroom_os.reducers.closeout_reducer import (
    CloseoutCommitPayload,
    CloseoutCommitVerdict,
    CloseoutProjection,
    CloseoutReducer,
    CloseoutReducerPayloadResolver,
)
from boardroom_os.reducers.ticket_reducer import TicketRefPayload
from boardroom_os.workspace.run_manifest import validate_run_manifest_binding
from boardroom_os.workspace.source_inventory import (
    PackageCommitRef,
    SourceInventory,
    SourceFileRecord,
    SourceLineageRecord,
    build_source_inventory,
)
from tests.proving.fixtures.tiny_package_assembly import (
    TinyPackageAssemblyFixture,
    build_tiny_package_assembly_fixture,
)
from tests.fixtures.execution.role_prompt_hooks import baseline_role_prompt_hook_registry
from tests.proving.fixtures.tiny_provider_attempts import (
    TinyProviderAttemptFixture,
    build_tiny_provider_attempt_fixture,
    compile_tiny_implementation_execution_packages,
)
from tests.proving.fixtures.tiny_ticket_graph import (
    PROJECT_REF,
    TICKET_CHECKER_ID,
    TinyTicketGraphPayloadResolver,
)
from boardroom_os.workspace.assembler import PackageArtifactKind


GENERATED_AT = datetime(2026, 5, 30, 10, 0, tzinfo=UTC)
RUN_ID = "run-v2-080f"
_CLOSEOUT_PAYLOAD_REF = EventPayloadRef(value="payload.closeout.commit.v2-080f")
_DEFAULT_SAMPLE_ROOT = Path("examples/generated-workspaces/tiny-fullstack")
_CLEANABLE_SAMPLE_PATHS = (
    "10-project",
    "20-evidence",
    "30-audit",
    "closeout-package.json",
    "replay-bundle.json",
    "git-version-audit-bundle.json",
    "sample-manifest.json",
)
_PROVIDER_ATTEMPTS_SAMPLE_PATH = Path(
    "20-evidence/provider-attempts/provider-attempts.json"
)
_PROVIDER_ARTIFACTS_SAMPLE_DIR = Path("20-evidence/provider-artifacts")


@dataclass(frozen=True)
class TinyCloseoutAuditAnswers:
    timeline_event_count: int
    agent_decision_count: int
    agent_context_entry_count: int
    artifact_paths: tuple[str, ...]
    git_final_commit_sha: str
    evidence_map_acceptance_refs: tuple[str, ...]


@dataclass(frozen=True)
class TinyCloseoutFixture:
    package_fixture: TinyPackageAssemblyFixture
    source_inventory: SourceInventory
    verification_runs: tuple[VerificationRun, ...]
    provider_attempt_refs: tuple[ProviderAttemptRef, ...]
    agent_context_index: AgentContextIndex
    ticket_graph_summary: BaseModel
    replay_payload_resolver: ReplayPayloadResolver
    events_before_closeout: tuple[EventRecord, ...]
    replay_bundle: ReplayBundle
    replay_readiness: Any
    git_version_audit_bundle: Any
    git_audit_readiness: Any
    process_audit_bundle: ProcessAuditBundle
    process_audit_readiness: Any
    closeout_gate_input: CloseoutGateInput
    closeout_gate_result: CloseoutGateResult
    closeout_package_input: CloseoutPackageBuilderInput
    closeout_package: CloseoutPackage
    closeout_commit_payload: CloseoutCommitPayload
    closeout_committed_event: EventRecord
    closeout_payload_resolver: CloseoutReducerPayloadResolver
    closeout_projection: CloseoutProjection
    audit_answers: TinyCloseoutAuditAnswers


@dataclass(frozen=True)
class TinyCloseoutSampleManifest:
    sample_root: str
    generated_at: str
    run_id: str
    file_count: int
    total_bytes: int
    sha256: str
    files: tuple[str, ...]


class TinyCloseoutPayloadResolver(CloseoutReducerPayloadResolver):
    def __init__(
        self,
        *,
        closeout_commit_payload: CloseoutCommitPayload,
        closeout_package: CloseoutPackage,
    ) -> None:
        self._commit_payloads = {
            _CLOSEOUT_PAYLOAD_REF.value: closeout_commit_payload,
        }
        self._packages = {
            closeout_package.closeout_package_id.value: closeout_package,
        }

    def resolve_closeout_commit(
        self,
        payload_ref: EventPayloadRef,
    ) -> CloseoutCommitPayload:
        return self._commit_payloads[payload_ref.value]

    def resolve_closeout_package(self, closeout_package_ref) -> CloseoutPackage:
        return self._packages[closeout_package_ref.value]


class TinyReplayPayloadResolver:
    def __init__(
        self,
        *,
        ticket_payload_resolver: TinyTicketGraphPayloadResolver,
        extra_payloads: Mapping[str, Any],
    ) -> None:
        self._ticket_payload_resolver = ticket_payload_resolver
        self._extra_payloads = dict(extra_payloads)

    def resolve_payload(self, content_ref: ReplayContentRef) -> Any:
        payload_ref = EventPayloadRef(value=content_ref.value)
        if content_ref.value in self._extra_payloads:
            return self._extra_payloads[content_ref.value]
        try:
            return self._ticket_payload_resolver.resolve_ticket_created(payload_ref)
        except KeyError:
            pass
        try:
            return self._ticket_payload_resolver.resolve_seat_assignment(payload_ref)
        except KeyError:
            pass
        return self._ticket_payload_resolver.resolve_ticket_blocked(payload_ref)


class TinyCloseoutReplayTicketProjector:
    def __init__(self, delegate: TicketGraphProjector) -> None:
        self._delegate = delegate

    def project(self, events: tuple[EventRecord, ...]):
        ticket_events = tuple(
            event
            for event in events
            if event.event_type in {EventType.TICKET_CREATED, EventType.TICKET_BLOCKED}
        )
        ticket_graph = self._delegate.project(ticket_events)
        if events and ticket_graph.graph_version != events[-1].graph_version:
            return ticket_graph.model_copy(update={"graph_version": events[-1].graph_version})
        return ticket_graph


class TinyCloseoutReplaySeatProjector(SeatAssignmentProjector):
    pass


class TinyTicketGraphNodeSummary(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    ticket_ref: str
    status: str
    acceptance_refs: tuple[str, ...]
    source_surface_refs: tuple[str, ...]
    evidence_obligation_refs: tuple[str, ...]
    owner_seat_ref: str
    blocker_refs: tuple[str, ...] = ()


class TinyTicketGraphSummary(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    graph_ref: str
    tickets: tuple[TinyTicketGraphNodeSummary, ...]


def build_tiny_closeout_fixture(
    package_root: Path | None = None,
    *,
    package_fixture: TinyPackageAssemblyFixture | None = None,
    git_transport: GitCommandTransport | None = None,
    base_commit_sha: str | None = None,
    allow_fake_provider_for_negative_tests: bool = False,
) -> TinyCloseoutFixture:
    root = package_root or Path(".pytest-tmp-tiny-closeout-package")
    verification_runs = tuple(
        result.verification_run
        for result in package_fixture.command_results_by_id.values()
    ) if package_fixture is not None else ()
    package_fixture = package_fixture or build_tiny_package_assembly_fixture(package_root=root)
    _reject_fake_provider_attempts(
        package_fixture,
        allow_fake_provider_for_negative_tests=allow_fake_provider_for_negative_tests,
    )
    git_cwd = _prepare_package_git_worktree(
        package_fixture=package_fixture,
        package_root=root,
        git_transport=git_transport,
    )
    if base_commit_sha is None:
        if git_transport is not None:
            raise ValueError("base_commit_sha is required for injected git audit")
        base_commit_sha = _git_base_commit_sha(package_root=git_cwd)
    final_commit_sha = _git_final_commit_sha(
        package_root=git_cwd,
        git_transport=git_transport,
    )
    source_inventory = _closeout_source_inventory(
        package_fixture,
        final_commit_sha=final_commit_sha,
    )
    verification_runs = verification_runs or tuple(
        result.verification_run
        for result in package_fixture.command_results_by_id.values()
    )
    provider_attempt_refs = tuple(
        ProviderAttemptRef(value=attempt.provider_attempt_id.value)
        for attempt in package_fixture.provider_attempts_by_ticket_id.values()
    )
    agent_context_index = _agent_context_index(package_fixture)
    ticket_graph_summary = _ticket_graph_summary(package_fixture)
    events_before_closeout = _events_before_closeout(package_fixture)
    replay_payload_resolver = _replay_payload_resolver(
        package_fixture=package_fixture,
        source_inventory=source_inventory,
        verification_runs=verification_runs,
    )
    replay_bundle = _replay_bundle(
        package_fixture=package_fixture,
        events=events_before_closeout,
        replay_payload_resolver=replay_payload_resolver,
    )
    replay_readiness = replay_bundle_readiness(
        replay_bundle,
        payload_resolver=replay_payload_resolver,
    )
    git_version_audit_bundle = _git_version_audit_bundle(
        package_fixture=package_fixture,
        source_inventory=source_inventory,
        verification_runs=verification_runs,
        package_root=git_cwd,
        git_transport=git_transport,
        base_commit_sha=base_commit_sha,
    )
    git_audit_readiness = git_version_audit_readiness(git_version_audit_bundle)
    checker_verdict = _checker_verdict(package_fixture)
    process_audit_bundle = build_process_audit_bundle(
        ProcessAuditBuilderInput(
            project_ref=PROJECT_REF,
            generated_at=GENERATED_AT,
            package_contract=package_fixture.package_contract,
            acceptance_contract=(
                package_fixture.provider_fixture.compiled.ticket_graph_fixture.contracts.acceptance_contract
            ),
            agent_context_index=agent_context_index,
            ticket_graph_summary=ticket_graph_summary,
            source_inventory=source_inventory,
            run_manifest=package_fixture.run_manifest,
            workspace_evidence_bundle=package_fixture.workspace_evidence_bundle.model_copy(
                update={"source_inventory_ref": source_inventory.source_inventory_id}
            ),
            final_evidence_table=package_fixture.final_evidence_table,
            checker_verdict=checker_verdict,
            verification_runs=verification_runs,
            verified_evidence=package_fixture.verified_evidence,
            provider_attempt_refs=provider_attempt_refs,
            replay_bundle=replay_bundle,
            replay_readiness=replay_readiness,
            git_version_audit_bundle=git_version_audit_bundle,
            git_audit_readiness=git_audit_readiness,
            run_id=RUN_ID,
        )
    )
    process_readiness = process_audit_readiness(process_audit_bundle)
    gate_input = _closeout_gate_input(
        package_fixture=package_fixture,
        source_inventory=source_inventory,
        verification_runs=verification_runs,
        provider_attempt_refs=provider_attempt_refs,
        checker_verdict=checker_verdict,
        replay_readiness=replay_readiness,
        git_audit_readiness=git_audit_readiness,
        process_readiness=process_readiness,
    )
    gate_result = CloseoutGate().evaluate(gate_input)
    if gate_result.verdict.value == "passed":
        _reject_fake_provider_passed_closeout(package_fixture)
    package_input = CloseoutPackageBuilderInput(
        closeout_gate_result=gate_result,
        source_inventory=source_inventory,
        final_evidence_table=package_fixture.final_evidence_table,
        replay_bundle=replay_bundle,
        replay_readiness=replay_readiness,
        process_audit_bundle=process_audit_bundle,
        process_audit_readiness=process_readiness,
        git_version_audit_bundle=git_version_audit_bundle,
        git_audit_readiness=git_audit_readiness,
        graph_version=replay_bundle.attestations[0].event_window.last_graph_version,
        generated_at=GENERATED_AT,
        run_id=RUN_ID,
    )
    closeout_package = build_closeout_package(package_input)
    closeout_payload = CloseoutCommitPayload(
        closeout_package_ref=closeout_package.closeout_package_id,
        closeout_gate_result_ref=closeout_package.closeout_gate_result_ref,
        source_inventory_ref=closeout_package.source_inventory_ref,
        final_evidence_table_ref=closeout_package.final_evidence_table_ref,
        replay_bundle_ref=closeout_package.replay_bundle_ref,
        process_audit_bundle_ref=closeout_package.process_audit_bundle_ref,
        git_version_audit_bundle_ref=closeout_package.git_version_audit_bundle_ref,
        package_commit_ref=closeout_package.package_commit_ref,
        terminal_verdict=CloseoutCommitVerdict.PASSED,
    )
    closeout_event = EventRecord(
        event_id=EventId(value="evt.closeout.committed.v2-080f"),
        event_type=EventType.CLOSEOUT_COMMITTED,
        project_ref=PROJECT_REF,
        actor_ref=ActorRef(value="seat-tiny-closeout"),
        timestamp=GENERATED_AT + timedelta(seconds=1),
        graph_version=closeout_package.graph_version + 1,
        payload_refs=(_CLOSEOUT_PAYLOAD_REF,),
    )
    closeout_resolver = TinyCloseoutPayloadResolver(
        closeout_commit_payload=closeout_payload,
        closeout_package=closeout_package,
    )
    projection = CloseoutReducer(closeout_resolver).reduce(
        (*events_before_closeout, closeout_event)
    )
    return TinyCloseoutFixture(
        package_fixture=package_fixture,
        source_inventory=source_inventory,
        verification_runs=verification_runs,
        provider_attempt_refs=provider_attempt_refs,
        agent_context_index=agent_context_index,
        ticket_graph_summary=ticket_graph_summary,
        replay_payload_resolver=replay_payload_resolver,
        events_before_closeout=events_before_closeout,
        replay_bundle=replay_bundle,
        replay_readiness=replay_readiness,
        git_version_audit_bundle=git_version_audit_bundle,
        git_audit_readiness=git_audit_readiness,
        process_audit_bundle=process_audit_bundle,
        process_audit_readiness=process_readiness,
        closeout_gate_input=gate_input,
        closeout_gate_result=gate_result,
        closeout_package_input=package_input,
        closeout_package=closeout_package,
        closeout_commit_payload=closeout_payload,
        closeout_committed_event=closeout_event,
        closeout_payload_resolver=closeout_resolver,
        closeout_projection=projection,
        audit_answers=_audit_answers(
            process_audit_bundle,
            final_commit_sha=git_audit_readiness.final_commit_sha.value,
        ),
    )


def materialize_tiny_closeout_sample(
    output_root: Path,
    *,
    clean: bool = True,
    allow_absolute_output_root: bool = False,
) -> TinyCloseoutSampleManifest:
    _validate_safe_output_root(
        output_root,
        allow_absolute_output_root=allow_absolute_output_root,
    )
    _reject_symlinked_output_root(output_root)
    logical_output_root = _logical_sample_root(output_root)
    resolved_root = output_root.resolve(strict=False)
    with tempfile.TemporaryDirectory(prefix="boardroom-os-v2080f-fixture-") as temp_dir:
        package_root = Path(temp_dir) / "physical-package-root"
        provider_fixture = _locked_provider_fixture_from_sample(resolved_root)
        had_provider_lock = provider_fixture is not None
        package_fixture = None
        if provider_fixture is not None:
            package_fixture = build_tiny_package_assembly_fixture(
                package_root=package_root,
                provider_fixture=provider_fixture,
            )
        fixture = build_tiny_closeout_fixture(
            package_root=package_root,
            package_fixture=package_fixture,
        )
        files = _tiny_closeout_sample_files(fixture)
    if clean:
        _clean_tiny_closeout_sample(resolved_root)
    for relative_path, content in files.items():
        _write_sample_file(resolved_root, relative_path, content)
    manifest = _sample_manifest(resolved_root, logical_output_root=logical_output_root)
    _write_sample_file(
        resolved_root,
        "sample-manifest.json",
        _stable_json(
            {
                "sample_root": manifest.sample_root,
                "generated_at": manifest.generated_at,
                "run_id": manifest.run_id,
                "file_count": manifest.file_count,
                "total_bytes": manifest.total_bytes,
                "sha256": manifest.sha256,
                "files": list(manifest.files),
            }
        ),
    )
    if not had_provider_lock:
        # 首次生成必须调用真实 provider；随后立即用写出的 provider artifact lock
        # 重放一次，使返回值与后续 --check / 重生成的字节树完全一致。
        return materialize_tiny_closeout_sample(
            output_root,
            clean=True,
            allow_absolute_output_root=allow_absolute_output_root,
        )
    return _sample_manifest(resolved_root, logical_output_root=logical_output_root)


def _tiny_closeout_sample_files(
    fixture: TinyCloseoutFixture,
) -> dict[str, str]:
    files: dict[str, str] = {}
    for artifact in fixture.package_fixture.package_assembly.artifacts:
        relative_path = artifact.relative_path.value
        files[f"10-project/{relative_path}"] = _project_file_content(
            fixture,
            relative_path,
        )

    files.update(
        {
            "20-evidence/source-inventory/source-inventory.json": _stable_json(
                fixture.source_inventory
            ),
            "20-evidence/tests/run-manifest.json": _stable_json(
                fixture.package_fixture.run_manifest
            ),
            "20-evidence/tests/verification-runs.json": _stable_json(
                [run.model_dump(mode="json") for run in fixture.verification_runs]
            ),
            _PROVIDER_ATTEMPTS_SAMPLE_PATH.as_posix(): _stable_json(
                [
                    attempt.model_dump(mode="json")
                    for _ticket_id, attempt in sorted(
                        fixture.package_fixture.provider_attempts_by_ticket_id.items(),
                        key=lambda item: item[0].value,
                    )
                ]
            ),
            "20-evidence/closeout/final-evidence-table.json": _stable_json(
                fixture.package_fixture.final_evidence_table
            ),
            "20-evidence/closeout/evidence-bundle-manifest.json": _stable_json(
                fixture.package_fixture.workspace_evidence_bundle.model_copy(
                    update={
                        "source_inventory_ref": fixture.source_inventory.source_inventory_id
                    }
                )
            ),
            "20-evidence/bundle-manifest.json": _stable_json(
                {
                    "source_inventory_ref": fixture.source_inventory.source_inventory_id.value,
                    "run_manifest_ref": fixture.package_fixture.run_manifest.run_manifest_id.value,
                    "final_evidence_table_ref": (
                        fixture.package_fixture.final_evidence_table.final_evidence_table_id.value
                    ),
                    "workspace_evidence_bundle_ref": (
                        fixture.package_fixture.workspace_evidence_bundle.workspace_evidence_bundle_id.value
                    ),
                }
            ),
            "closeout-package.json": _stable_json(fixture.closeout_package),
            "replay-bundle.json": _stable_json(fixture.replay_bundle),
            "git-version-audit-bundle.json": _stable_json(
                fixture.git_version_audit_bundle
            ),
        }
    )

    for artifact in fixture.process_audit_bundle.artifacts:
        content = artifact.content
        if isinstance(content, str):
            files[artifact.path.value] = _stable_text(content)
        else:
            files[artifact.path.value] = _stable_json(content)
    files.update(_provider_artifact_sample_files(fixture))
    return dict(sorted(files.items()))


def _project_file_content(fixture: TinyCloseoutFixture, relative_path: str) -> str:
    if relative_path == "run-manifest.json":
        return _stable_json(fixture.package_fixture.run_manifest)
    if relative_path == "package-contract.json":
        return _stable_json(fixture.package_fixture.package_contract)
    try:
        return _stable_text(fixture.package_fixture.source_contents[relative_path])
    except KeyError as error:
        artifact = next(
            item
            for item in fixture.package_fixture.package_assembly.artifacts
            if item.relative_path.value == relative_path
        )
        if artifact.artifact_kind in {
            PackageArtifactKind.README,
            PackageArtifactKind.AGENTS,
        }:
            raise ValueError(f"missing required project file content: {relative_path}") from error
        raise


def _provider_artifact_sample_files(
    fixture: TinyCloseoutFixture,
) -> dict[str, str]:
    files: dict[str, str] = {}
    artifact_root = fixture.package_fixture.provider_fixture.provider_artifact_root
    for attempt in fixture.package_fixture.provider_attempts_by_ticket_id.values():
        for artifact_ref in (attempt.raw_output_ref, attempt.parsed_output_ref):
            if artifact_ref is None:
                raise ValueError("provider artifact refs are required for sample lock")
            relative_path = _provider_artifact_sample_path(artifact_ref.value)
            files[relative_path.as_posix()] = _read_provider_artifact_text(
                artifact_root=artifact_root,
                artifact_ref=artifact_ref.value,
            )
    return files


def _locked_provider_fixture_from_sample(
    output_root: Path,
) -> TinyProviderAttemptFixture | None:
    attempts_path = output_root / _PROVIDER_ATTEMPTS_SAMPLE_PATH
    artifacts_root = output_root / _PROVIDER_ARTIFACTS_SAMPLE_DIR
    if not attempts_path.exists():
        if artifacts_root.exists() and any(artifacts_root.rglob("*")):
            raise ValueError("provider artifact lock is incomplete: attempts manifest missing")
        return None
    if not artifacts_root.is_dir():
        raise ValueError("provider artifact lock is incomplete: artifacts directory missing")
    data = json.loads(attempts_path.read_text(encoding="utf-8"))
    if not isinstance(data, list) or not data:
        raise ValueError("provider attempt lock must contain attempts")
    attempts = tuple(ProviderAttempt.model_validate(item) for item in data)
    hook_registry = baseline_role_prompt_hook_registry()
    for attempt in attempts:
        hook = hook_registry.require(attempt.role_prompt_hook_ref)
        if (
            attempt.role_prompt_hook_version != hook.hook_version
            or attempt.role_prompt_hook_sha256 != hook.content_sha256
        ):
            raise ValueError(
                "provider attempt lock role prompt hook lineage does not match registry"
            )
        _validate_locked_provider_attempt_artifacts(
            output_root=output_root,
            attempt=attempt,
        )
    return _provider_fixture_from_locked_attempts(
        attempts=attempts,
        artifact_root=artifacts_root,
    )


def _provider_fixture_from_locked_attempts(
    *,
    attempts: tuple[ProviderAttempt, ...],
    artifact_root: Path,
) -> TinyProviderAttemptFixture:
    compiled = compile_tiny_implementation_execution_packages(
        model=attempts[0].model,
    )
    attempts_by_input_ref = {
        attempt.input_package_ref.value: attempt
        for attempt in attempts
    }
    if len(attempts_by_input_ref) != len(attempts):
        raise ValueError("provider attempt lock contains duplicate execution packages")
    base_graph_version = compiled.ticket_graph_fixture.seat_assignment_graph.graph_version
    runtime_results = tuple(
        _execute_locked_provider_package(
            ticket_id=ticket_id,
            execution_package=execution_package,
            compiled=compiled,
            locked_attempt=attempts_by_input_ref.get(
                execution_package.execution_package_id.value
            ),
            first_fact_graph_version=base_graph_version + (index * 10) + 1,
        )
        for index, (ticket_id, execution_package) in enumerate(
            compiled.execution_packages.items()
        )
    )
    if any(result.provider_attempt is None for result in runtime_results):
        raise ValueError("provider attempt lock must cover every execution package")
    return TinyProviderAttemptFixture(
        compiled=compiled,
        execution_packages=compiled.execution_packages,
        runtime_results=runtime_results,
        provider_attempts_by_ticket_id={
            ticket_id: result.provider_attempt
            for ticket_id, result in zip(
                compiled.execution_packages,
                runtime_results,
                strict=True,
            )
        },
        provider_artifact_root=artifact_root,
    )


def _execute_locked_provider_package(
    *,
    ticket_id: TicketId,
    execution_package,
    compiled,
    locked_attempt: ProviderAttempt | None,
    first_fact_graph_version: int,
):
    if locked_attempt is None:
        raise ValueError(f"provider attempt lock missing ticket: {ticket_id.value}")
    return _runtime_execute_with_locked_provider(
        execution_package=execution_package,
        compiled=compiled,
        locked_provider=LockedProviderAttemptAdapter(locked_attempt),
        first_fact_graph_version=first_fact_graph_version,
    )


class LockedProviderAttemptAdapter:
    def __init__(self, attempt: ProviderAttempt) -> None:
        self._attempt = attempt

    def invoke(self, request: ProviderRequest) -> ProviderAttempt:
        if self._attempt.input_package_ref != request.execution_package_ref:
            raise ValueError("locked provider attempt input_package_ref mismatch")
        if self._attempt.seat_ref != request.seat_ref:
            raise ValueError("locked provider attempt seat_ref mismatch")
        if self._attempt.provider != request.model_execution_profile.provider:
            raise ValueError("locked provider attempt provider mismatch")
        if self._attempt.model != request.model_execution_profile.model:
            raise ValueError("locked provider attempt model mismatch")
        if self._attempt.reasoning_effort != request.model_execution_profile.reasoning_effort:
            raise ValueError("locked provider attempt reasoning_effort mismatch")
        return self._attempt


def _runtime_execute_with_locked_provider(
    *,
    execution_package,
    compiled,
    locked_provider: LockedProviderAttemptAdapter,
    first_fact_graph_version: int,
):
    from boardroom_os.execution.runtime_executor import RuntimeExecutionInput, RuntimeExecutor
    from boardroom_os.execution.verification_run import (
        EnvironmentProfileRef,
        RunnerRef,
        WorkspaceSnapshotRef,
    )
    from boardroom_os.contracts.methodology import MethodologyProfileRegistry
    from boardroom_os.events.types import ActorRef

    return RuntimeExecutor().execute_package(
        RuntimeExecutionInput.model_validate(
            {
                "execution_package": execution_package,
                "package_contract": compiled.ticket_graph_fixture.contracts.package_contract,
                "agent_team_projection": compiled.agent_team_projection,
                "provider_adapter": locked_provider,
                "project_ref": PROJECT_REF,
                "runtime_actor_ref": ActorRef(value="actor.runtime.tiny-provider-attempts"),
                "first_fact_graph_version": first_fact_graph_version,
                "package_root": Path("10-project"),
                "runner_ref": RunnerRef(value="runner.tiny-provider-attempts"),
                "environment_profile_ref": EnvironmentProfileRef(
                    value="env.tiny-provider-attempts"
                ),
                "workspace_snapshot_ref": WorkspaceSnapshotRef(
                    value="workspace.snapshot.tiny-provider-attempts"
                ),
                "command_ids": (),
                "timestamp": datetime(2026, 5, 29, 10, 0, tzinfo=UTC),
            },
            context={
                "methodology_registry": MethodologyProfileRegistry.from_profiles(
                    compiled.ticket_graph_fixture.contracts.methodology_profile,
                ),
            },
        )
    )


def _validate_locked_provider_attempt_artifacts(
    *,
    output_root: Path,
    attempt: ProviderAttempt,
) -> None:
    for artifact_ref in (attempt.raw_output_ref, attempt.parsed_output_ref):
        if artifact_ref is None:
            raise ValueError("locked provider attempt must include artifact refs")
        _read_provider_artifact_text(
            artifact_root=output_root / _PROVIDER_ARTIFACTS_SAMPLE_DIR,
            artifact_ref=artifact_ref.value,
        )


def _provider_artifact_sample_path(artifact_ref: str) -> Path:
    return _PROVIDER_ARTIFACTS_SAMPLE_DIR / f"{_safe_provider_artifact_name(artifact_ref)}.txt"


def _read_provider_artifact_text(*, artifact_root: Path, artifact_ref: str) -> str:
    path = artifact_root / f"{_safe_provider_artifact_name(artifact_ref)}.txt"
    if not path.is_file():
        raise ValueError(f"provider artifact lock file is required: {artifact_ref}")
    text = path.read_text(encoding="utf-8")
    expected_hash = artifact_ref.rsplit(".", 1)[-1]
    actual_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    if actual_hash != expected_hash:
        raise ValueError("provider artifact lock hash mismatch")
    return text


def _safe_provider_artifact_name(artifact_ref: str) -> str:
    if not artifact_ref.startswith("provider-artifact.openai."):
        raise ValueError("provider artifact lock ref must be provider-backed")
    safe_name = artifact_ref.replace("/", "_").replace("\\", "_").replace(":", "_")
    if safe_name != artifact_ref:
        raise ValueError("provider artifact lock ref must be repository-safe")
    return safe_name


def _validate_safe_output_root(
    output_root: Path,
    *,
    allow_absolute_output_root: bool = False,
) -> None:
    if output_root == Path("."):
        raise ValueError("sample output_root must not be repository root")
    raw = output_root.as_posix()
    if "\\" in raw or ".." in output_root.parts:
        raise ValueError("sample output_root must not contain unsafe path segments")
    if (output_root.is_absolute() or output_root.drive) and not allow_absolute_output_root:
        raise ValueError("sample output_root must be repository-relative")
    if raw in {"10-project", "20-evidence", "30-audit"} or raw.startswith(
        ("10-project/", "20-evidence/", "30-audit/")
    ):
        raise ValueError("sample output_root must not be a repository runtime directory")
    if raw != _DEFAULT_SAMPLE_ROOT.as_posix() and output_root.parts[:1] == ("examples",):
        raise ValueError("examples sample output_root must be tiny-fullstack")


def _logical_sample_root(output_root: Path) -> str:
    if output_root.is_absolute() or output_root.drive:
        return _DEFAULT_SAMPLE_ROOT.as_posix()
    return output_root.as_posix()


def _reject_symlinked_output_root(output_root: Path) -> None:
    candidates = [output_root]
    candidates.extend(output_root.parents)
    for candidate in candidates:
        if not candidate.exists():
            continue
        if candidate.is_symlink():
            raise ValueError("sample output_root must not be a symlink")
        if candidate == Path("."):
            break


def _clean_tiny_closeout_sample(output_root: Path) -> None:
    if output_root.exists() and not output_root.is_dir():
        raise ValueError("sample output_root must be a directory")
    output_root.mkdir(parents=True, exist_ok=True)
    for relative_path in _CLEANABLE_SAMPLE_PATHS:
        target = (output_root / relative_path).resolve(strict=False)
        _require_child_path(output_root, target)
        if target.is_dir():
            shutil.rmtree(target)
        elif target.exists():
            target.unlink()


def _write_sample_file(output_root: Path, relative_path: str, content: str) -> None:
    target = (output_root / _safe_relative_path(relative_path)).resolve(strict=False)
    _require_child_path(output_root, target)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8", newline="\n")


def _safe_relative_path(relative_path: str) -> Path:
    if not relative_path or relative_path.startswith("/") or "\\" in relative_path:
        raise ValueError("sample relative path must be safe")
    path = Path(relative_path)
    if path.drive or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError("sample relative path must be safe")
    if path.parts and path.parts[0] in {"00-boardroom"}:
        raise ValueError("sample must not write boardroom runtime inputs")
    return path


def _require_child_path(root: Path, target: Path) -> None:
    resolved_root = root.resolve(strict=False)
    try:
        target.relative_to(resolved_root)
    except ValueError as error:
        raise ValueError("sample path escapes output_root") from error


def _sample_manifest(
    output_root: Path,
    *,
    logical_output_root: str,
) -> TinyCloseoutSampleManifest:
    files = tuple(
        sorted(
            path.relative_to(output_root).as_posix()
            for path in output_root.rglob("*")
            if path.is_file() and path.name != "sample-manifest.json"
        )
    )
    hash_input: list[dict[str, str | int]] = []
    total_bytes = 0
    for relative_path in files:
        data = (output_root / relative_path).read_bytes()
        total_bytes += len(data)
        hash_input.append(
            {
                "path": relative_path,
                "size": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
            }
        )
    return TinyCloseoutSampleManifest(
        sample_root=logical_output_root,
        generated_at=GENERATED_AT.isoformat(),
        run_id=RUN_ID,
        file_count=len(files),
        total_bytes=total_bytes,
        sha256=hashlib.sha256(
            _stable_json(hash_input).encode("utf-8")
        ).hexdigest(),
        files=files,
    )


def _stable_json(value: Any) -> str:
    if isinstance(value, BaseModel):
        payload = value.model_dump(mode="json")
    else:
        payload = value
    return (
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
        )
        + "\n"
    )


def _stable_text(value: str) -> str:
    normalized = value.replace("\r\n", "\n").replace("\r", "\n")
    if not normalized.endswith("\n"):
        normalized += "\n"
    return normalized


def _reject_fake_provider_attempts(
    package_fixture: TinyPackageAssemblyFixture,
    *,
    allow_fake_provider_for_negative_tests: bool,
) -> None:
    fake_attempt_refs = _fake_provider_attempt_refs(package_fixture)
    if fake_attempt_refs and not allow_fake_provider_for_negative_tests:
        raise ValueError("fake provider attempts cannot satisfy tiny closeout")


def _reject_fake_provider_passed_closeout(
    package_fixture: TinyPackageAssemblyFixture,
) -> None:
    fake_attempt_refs = _fake_provider_attempt_refs(package_fixture)
    if fake_attempt_refs:
        raise ValueError(
            "fake provider attempts are only allowed for negative tests and "
            "cannot produce passed closeout"
        )


def _fake_provider_attempt_refs(
    package_fixture: TinyPackageAssemblyFixture,
) -> tuple[str, ...]:
    fake_attempt_refs = tuple(
        attempt.provider_attempt_id.value
        for attempt in package_fixture.provider_attempts_by_ticket_id.values()
        if ".fake." in attempt.provider_attempt_id.value
    )
    return fake_attempt_refs


def _prepare_package_git_worktree(
    *,
    package_fixture: TinyPackageAssemblyFixture,
    package_root: Path,
    git_transport: GitCommandTransport | None,
) -> Path:
    if git_transport is not None:
        return package_root
    _ensure_local_git_repo(package_root)
    return package_root


def _ensure_local_git_repo(package_root: Path) -> None:
    if not package_root.exists():
        raise ValueError("physical package root is required before git audit")
    if (package_root / ".git").exists():
        return
    baseline_root = _baseline_git_commit_root(package_root)
    baseline_root.mkdir(parents=True, exist_ok=True)
    (baseline_root / "README.md").write_text(
        "Tiny closeout package baseline.\n",
        encoding="utf-8",
        newline="\n",
    )
    _remove_runtime_cache_artifacts(package_root)
    _write_package_gitignore(package_root)
    _run_git(("git", "init"), cwd=package_root)
    _run_git(("git", "config", "user.name", "Boardroom OS Test"), cwd=package_root)
    _run_git(("git", "config", "user.email", "boardroom-os@example.invalid"), cwd=package_root)
    _run_git(("git", "add", ".closeout-baseline/README.md"), cwd=package_root)
    _run_git(
        ("git", "commit", "-m", "test fixture baseline"),
        cwd=package_root,
        env={
            "GIT_AUTHOR_DATE": (GENERATED_AT - timedelta(minutes=5)).isoformat(),
            "GIT_COMMITTER_DATE": (GENERATED_AT - timedelta(minutes=5)).isoformat(),
        },
    )
    shutil.rmtree(baseline_root)
    _run_git(("git", "add", "."), cwd=package_root)
    _run_git(
        ("git", "commit", "-m", "test fixture final package"),
        cwd=package_root,
        env={
            "GIT_AUTHOR_DATE": GENERATED_AT.isoformat(),
            "GIT_COMMITTER_DATE": GENERATED_AT.isoformat(),
        },
    )


def _baseline_git_commit_root(package_root: Path) -> Path:
    return package_root / ".closeout-baseline"


def _remove_runtime_cache_artifacts(package_root: Path) -> None:
    for target in package_root.rglob("*"):
        if target.name == "__pycache__" or target.name.startswith(".pytest"):
            resolved = target.resolve(strict=False)
            _require_child_path(package_root, resolved)
            if target.is_dir():
                shutil.rmtree(target)
            elif target.exists():
                target.unlink()


def _write_package_gitignore(package_root: Path) -> None:
    (package_root / ".gitignore").write_text(
        "\n".join(
            (
                ".pytest_cache/",
                ".pytest-tmp*/",
                "__pycache__/",
                "*.pyc",
                "*.sqlite3",
                "",
            )
        ),
        encoding="utf-8",
        newline="\n",
    )


def _run_git(
    command: tuple[str, ...],
    *,
    cwd: Path,
    env: Mapping[str, str] | None = None,
) -> str:
    process_env = None
    if env is not None:
        process_env = {**os.environ, **env}
    completed = subprocess.run(
        command,
        cwd=cwd,
        env=process_env,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise ValueError(f"git command failed: {' '.join(command)}: {completed.stderr}")
    return completed.stdout


def _git_final_commit_sha(
    *,
    package_root: Path,
    git_transport: GitCommandTransport | None,
) -> str:
    if git_transport is not None:
        result = git_transport.run(("git", "rev-parse", "HEAD"), cwd=str(package_root))
        if result.exit_code != 0:
            raise ValueError("git final commit lookup failed")
        return result.stdout.strip()
    return _run_git(("git", "rev-parse", "HEAD"), cwd=package_root).strip()


def _git_base_commit_sha(*, package_root: Path) -> str:
    return _run_git(("git", "rev-parse", "HEAD~1"), cwd=package_root).strip()


def _closeout_source_inventory(
    package_fixture: TinyPackageAssemblyFixture,
    *,
    final_commit_sha: str,
) -> SourceInventory:
    return build_source_inventory(
        package_assembly=package_fixture.package_assembly,
        package_contract=package_fixture.package_contract,
        package_commit_ref=PackageCommitRef(value=f"package-commit.{final_commit_sha}"),
        source_files=tuple(
            SourceFileRecord(path=entry.path, sha256=entry.sha256)
            for entry in package_fixture.source_inventory.entries
        ),
        lineage_records=tuple(
            SourceLineageRecord(
                path=entry.path,
                source_surface_ref=entry.source_surface_ref,
                producer_ticket_ref=entry.producer_ticket_ref,
                producer_attempt_ref=entry.producer_attempt_ref,
                consumer_ticket_refs=entry.consumer_ticket_refs,
                acceptance_refs=entry.acceptance_refs,
                evidence_refs=entry.evidence_refs,
            )
            for entry in package_fixture.source_inventory.entries
        ),
    )


def _events_before_closeout(
    package_fixture: TinyPackageAssemblyFixture,
) -> tuple[EventRecord, ...]:
    graph_fixture = package_fixture.provider_fixture.compiled.ticket_graph_fixture
    leased_events = tuple(
        _event(
            event_id=f"evt:{ticket_id.value}:ticket-leased",
            event_type=EventType.TICKET_LEASED,
            graph_version=21 + index,
            payload_ref=f"payload:{ticket_id.value}:ticket-leased",
            actor_ref=graph_fixture.seat_assignment_graph.seat_assignments[
                ticket_id
            ].value,
        )
        for index, ticket_id in enumerate(
            package_fixture.provider_fixture.execution_packages,
            start=1,
        )
    )
    runtime_events = tuple(
        event
        for result in package_fixture.provider_fixture.runtime_results
        for event in result.events
    )
    command_events = tuple(
        _event(
            event_id=f"evt.tiny.command-run-recorded.{index}",
            event_type=EventType.COMMAND_RUN_RECORDED,
            graph_version=47 + index,
            payload_ref=f"payload:command-run:{command_id}",
            actor_ref="runner.tiny-closeout",
        )
        for index, command_id in enumerate(
            sorted(package_fixture.command_results_by_id),
            start=1,
        )
    )
    ordered_events = tuple(
        sorted(
            (*graph_fixture.events, *leased_events, *runtime_events, *command_events),
            key=lambda event: (event.graph_version, event.event_id.value),
        )
    )
    return tuple(
        event.model_copy(update={"graph_version": index})
        for index, event in enumerate(ordered_events, start=1)
    )


def _event(
    *,
    event_id: str,
    event_type: EventType,
    graph_version: int,
    payload_ref: str,
    actor_ref: str,
) -> EventRecord:
    return EventRecord(
        event_id=EventId(value=event_id),
        event_type=event_type,
        project_ref=PROJECT_REF,
        actor_ref=ActorRef(value=actor_ref),
        timestamp=GENERATED_AT + timedelta(seconds=graph_version),
        graph_version=graph_version,
        payload_refs=(EventPayloadRef(value=payload_ref),),
    )


def _replay_payload_resolver(
    *,
    package_fixture: TinyPackageAssemblyFixture,
    source_inventory: SourceInventory,
    verification_runs: tuple[VerificationRun, ...],
) -> TinyReplayPayloadResolver:
    graph_fixture = package_fixture.provider_fixture.compiled.ticket_graph_fixture
    extra_payloads: dict[str, Any] = {
        **{
            f"payload:{ticket_id.value}:ticket-leased": TicketRefPayload(
                ticket_id=ticket_id
            )
            for ticket_id in package_fixture.provider_fixture.execution_packages
        },
        **{
            event.payload_refs[0].value: result.provider_attempt
            for result in package_fixture.provider_fixture.runtime_results
            for event in result.events
            if event.event_type is EventType.PROVIDER_ATTEMPT_RECORDED
        },
        **{
            event.payload_refs[0].value: result.work_product_submission.work_product
            for result in package_fixture.provider_fixture.runtime_results
            for event in result.events
            if event.event_type is EventType.WORK_PRODUCT_SUBMITTED
            and result.work_product_submission is not None
        },
        "payload:command-run:test-backend": verification_runs[0],
        "payload:command-run:test-integration": verification_runs[1],
        source_inventory.source_inventory_id.value: source_inventory,
    }
    for result in package_fixture.provider_fixture.runtime_results:
        for event in result.events:
            if event.event_type is EventType.EXECUTION_STARTED:
                extra_payloads[event.payload_refs[0].value] = {
                    "event_type": event.event_type.value,
                    "payload_ref": event.payload_refs[0].value,
                }
    return TinyReplayPayloadResolver(
        ticket_payload_resolver=graph_fixture.payload_resolver,
        extra_payloads=extra_payloads,
    )


def _replay_bundle(
    *,
    package_fixture: TinyPackageAssemblyFixture,
    events: tuple[EventRecord, ...],
    replay_payload_resolver: ReplayPayloadResolver,
) -> ReplayBundle:
    return build_replay_bundle(
        builder_input=_replay_builder_input(
            package_fixture=package_fixture,
            events=events,
            replay_payload_resolver=replay_payload_resolver,
        )
    )


def _replay_seat_assignment_projector(
    package_fixture: TinyPackageAssemblyFixture,
) -> SeatAssignmentProjector:
    graph_fixture = package_fixture.provider_fixture.compiled.ticket_graph_fixture
    return TinyCloseoutReplaySeatProjector(
        ticket_projector=TinyCloseoutReplayTicketProjector(
            TicketGraphProjector(graph_fixture.payload_resolver)
        ),
        payload_resolver=graph_fixture.payload_resolver,
        seat_projection=graph_fixture.seat_projection,
    )


def _replay_builder_input(
    *,
    package_fixture: TinyPackageAssemblyFixture,
    events: tuple[EventRecord, ...],
    replay_payload_resolver: ReplayPayloadResolver,
):
    project_ref = PROJECT_REF
    payload_manifest_ref = ReplayManifestRef(
        value="replay-payload-manifest.project-tiny-fullstack.v2-080f"
    )
    artifact_manifest_ref = ReplayManifestRef(
        value="replay-artifact-manifest.project-tiny-fullstack.v2-080f"
    )
    hash_manifest_ref = ReplayManifestRef(
        value="replay-hash-manifest.project-tiny-fullstack.v2-080f"
    )
    replay_report_ref = ReplayReportRef(
        value="replay-report.project-tiny-fullstack.v2-080f"
    )
    return ReplayBundleBuilderInput(
        project_ref=project_ref,
        events=events,
        seat_assignment_projector=_replay_seat_assignment_projector(package_fixture),
        projection_version="projection.seat_assignment_graph.v1",
        payload_manifest_ref=payload_manifest_ref,
        payload_manifest_entries=_payload_manifest_entries(
            events=events,
            replay_payload_resolver=replay_payload_resolver,
        ),
        event_window_ref=ReplayManifestRef(
            value="event-window.project-tiny-fullstack.v2-080f"
        ),
        artifact_manifest_ref=artifact_manifest_ref,
        artifact_manifest_entries=_artifact_manifest_entries(
            event_range_ref=(
                f"event-range.{project_ref.value}."
                f"{events[0].graph_version}-{events[-1].graph_version}"
            ),
            payload_manifest_ref=payload_manifest_ref.value,
            artifact_manifest_ref=artifact_manifest_ref.value,
            hash_manifest_ref=hash_manifest_ref.value,
            replay_report_ref=replay_report_ref.value,
        ),
        hash_manifest_ref=hash_manifest_ref,
        replay_report_ref=replay_report_ref,
        generated_at=GENERATED_AT,
        run_id=RUN_ID,
    )


def _payload_manifest_entries(
    *,
    events: tuple[EventRecord, ...],
    replay_payload_resolver: ReplayPayloadResolver,
) -> tuple[ReplayManifestEntry, ...]:
    payload_refs = sorted(
        {payload_ref.value for event in events for payload_ref in event.payload_refs}
    )
    return tuple(
        ReplayManifestEntry(
            manifest_ref=ReplayManifestRef(value=f"replay-payload-entry.{index}"),
            kind=ReplayManifestKind.PAYLOAD_MANIFEST,
            content_ref=ReplayContentRef(value=payload_ref),
            sha256=ReplayContentHash(
                value=hashlib.sha256(
                    _payload_bytes_for_hash(
                        replay_payload_resolver.resolve_payload(
                            ReplayContentRef(value=payload_ref)
                        )
                    )
                ).hexdigest()
            ),
        )
        for index, payload_ref in enumerate(payload_refs, start=1)
    )


def _artifact_manifest_entries(
    *,
    event_range_ref: str,
    payload_manifest_ref: str,
    artifact_manifest_ref: str,
    hash_manifest_ref: str,
    replay_report_ref: str,
) -> tuple[ReplayArtifactManifestEntry, ...]:
    return (
        _artifact_entry("event-window", ReplayManifestKind.EVENT_WINDOW, event_range_ref),
        _artifact_entry("payload-manifest", ReplayManifestKind.PAYLOAD_MANIFEST, payload_manifest_ref),
        _artifact_entry("artifact-manifest", ReplayManifestKind.ARTIFACT_MANIFEST, artifact_manifest_ref),
        _artifact_entry("hash-manifest", ReplayManifestKind.HASH_MANIFEST, hash_manifest_ref),
        _artifact_entry("replay-report", ReplayManifestKind.REPLAY_REPORT, replay_report_ref),
    )


def _artifact_entry(
    suffix: str,
    kind: ReplayManifestKind,
    content_ref: str,
) -> ReplayArtifactManifestEntry:
    return ReplayArtifactManifestEntry(
        manifest_ref=ReplayManifestRef(value=f"replay-artifact-entry.{suffix}.v2-080f"),
        kind=kind,
        content_ref=ReplayContentRef(value=content_ref),
        sha256=ReplayContentHash(
            value=hashlib.sha256(
                f"tiny-closeout-artifact-entry:{kind.value}:{content_ref}".encode(
                    "utf-8"
                )
            ).hexdigest()
        ),
    )


def _git_version_audit_bundle(
    *,
    package_fixture: TinyPackageAssemblyFixture,
    source_inventory: SourceInventory,
    verification_runs: tuple[VerificationRun, ...],
    package_root: Path,
    git_transport: GitCommandTransport | None,
    base_commit_sha: str,
):
    inventory_hash = source_inventory_hash(source_inventory)
    git_facts = GitAuditAdapter(transport=git_transport).collect(
        package_root=package_fixture.package_contract.package_root,
        project_ref=PROJECT_REF.value,
        cwd=str(package_root),
        source_inventory_hash=inventory_hash.value,
        base_commit_sha=base_commit_sha,
        worktree_ref=f"worktree.{RUN_ID}",
        generated_at=GENERATED_AT,
    )
    bindings = tuple(
        GitCommandEvidenceBinding(
            binding_id=f"git-command-evidence-binding.{run.verification_run_id.value}",
            verification_run_ref=run.verification_run_id,
            run_manifest_ref=package_fixture.run_manifest.run_manifest_id,
            package_contract_ref=package_fixture.package_contract.package_contract_id,
            command_id=run.command_id,
            command=run.command,
            cwd=run.cwd,
            workspace_snapshot_ref=run.workspace_snapshot_ref,
            commit_sha=git_facts.final_commit_sha,
            source_inventory_hash=inventory_hash,
        )
        for run in verification_runs
    )
    return build_git_version_audit_bundle(
        GitVersionAuditBuilderInput(
            project_ref=PROJECT_REF,
            generated_at=GENERATED_AT,
            package_contract=package_fixture.package_contract,
            source_inventory=source_inventory,
            run_manifest=package_fixture.run_manifest,
            verification_runs=verification_runs,
            command_evidence_bindings=bindings,
            git_facts=git_facts,
            run_id=RUN_ID,
        )
    )


def _checker_verdict(package_fixture: TinyPackageAssemblyFixture) -> CheckerVerdict:
    return CheckerVerdict(
        ticket_ref=TICKET_CHECKER_ID,
        work_product_ref=WorkProductRef(value="work-product.tiny-checker"),
        source_diff_ref=SourceDiffRef(value="source-diff.tiny-closeout"),
        acceptance_contract_ref=package_fixture.final_evidence_table.acceptance_contract_ref,
        final_evidence_table_ref=package_fixture.final_evidence_table.final_evidence_table_id,
        status=CheckerVerdictStatus.APPROVED,
        checked_at=GENERATED_AT,
    )


def _agent_context_index(
    package_fixture: TinyPackageAssemblyFixture,
) -> AgentContextIndex:
    return AgentContextIndex(
        entries=tuple(
            AgentContextIndexEntry(
                entry_id=AgentContextIndexEntryId(
                    value=f"agent-context-entry.{ticket_id.value}"
                ),
                snapshot=build_agent_context_snapshot(execution_package),
                provider_attempt_refs=(
                    ProviderAttemptRef(
                        value=package_fixture.provider_attempts_by_ticket_id[
                            ticket_id
                        ].provider_attempt_id.value
                    ),
                ),
            )
            for ticket_id, execution_package in package_fixture.provider_fixture.execution_packages.items()
        )
    )


def _ticket_graph_summary(
    package_fixture: TinyPackageAssemblyFixture,
) -> TinyTicketGraphSummary:
    graph = package_fixture.provider_fixture.compiled.ticket_graph_fixture.seat_assignment_graph
    return TinyTicketGraphSummary(
        graph_ref="ticket-graph.project-tiny-fullstack.v2-080f",
        tickets=tuple(
            TinyTicketGraphNodeSummary(
                ticket_ref=ticket_id.value,
                status=TicketStatus.COMPLETED.value,
                acceptance_refs=tuple(_ref_value(ref) for ref in node.acceptance_refs),
                source_surface_refs=tuple(_ref_value(ref) for ref in node.source_surface_refs),
                evidence_obligation_refs=tuple(
                    _ref_value(ref) for ref in node.evidence_obligations
                ),
                owner_seat_ref=graph.seat_assignments[ticket_id].value,
            )
            for ticket_id, node in graph.nodes.items()
        ),
    )


def _ref_value(value: Any) -> str:
    return str(getattr(value, "value", value))


def _closeout_gate_input(
    *,
    package_fixture: TinyPackageAssemblyFixture,
    source_inventory: SourceInventory,
    verification_runs: tuple[VerificationRun, ...],
    provider_attempt_refs: tuple[ProviderAttemptRef, ...],
    checker_verdict: CheckerVerdict,
    replay_readiness: Any,
    git_audit_readiness: Any,
    process_readiness: Any,
) -> CloseoutGateInput:
    command_bindings = tuple(
        _closeout_command_binding(package_fixture, run)
        for run in verification_runs
    )
    return CloseoutGateInput(
        package_contract=package_fixture.package_contract,
        source_inventory=source_inventory,
        run_manifest=package_fixture.run_manifest,
        workspace_evidence_bundle=package_fixture.workspace_evidence_bundle.model_copy(
            update={"source_inventory_ref": source_inventory.source_inventory_id}
        ),
        final_evidence_table=package_fixture.final_evidence_table,
        checker_verdict=checker_verdict,
        verification_runs=verification_runs,
        verified_evidence=package_fixture.verified_evidence,
        provider_attempt_refs=provider_attempt_refs,
        final_command_bindings=command_bindings,
        replay_readiness=replay_readiness,
        git_audit_readiness=git_audit_readiness,
        process_audit_readiness=process_readiness,
    )


def _closeout_command_binding(
    package_fixture: TinyPackageAssemblyFixture,
    run: VerificationRun,
) -> CloseoutCommandEvidenceBinding:
    binding = validate_run_manifest_binding(
        run_manifest=package_fixture.run_manifest,
        package_contract=package_fixture.package_contract,
        command_id=ContractId(value=run.command_id.value),
    )
    return CloseoutCommandEvidenceBinding(
        verification_run_ref=run.verification_run_id,
        run_manifest_ref=binding.run_manifest_ref,
        package_contract_ref=binding.package_contract_ref,
        command_id=binding.command_id,
        binding_kind=binding.kind,
    )


def _audit_answers(
    bundle: ProcessAuditBundle,
    *,
    final_commit_sha: str,
) -> TinyCloseoutAuditAnswers:
    artifacts_by_kind = {artifact.kind: artifact for artifact in bundle.artifacts}
    timeline = artifacts_by_kind[ProcessAuditArtifactKind.TIMELINE].content
    context = artifacts_by_kind[ProcessAuditArtifactKind.AGENT_CONTEXT_INDEX].content
    lineage = artifacts_by_kind[ProcessAuditArtifactKind.ARTIFACT_LINEAGE].content
    evidence_map = artifacts_by_kind[ProcessAuditArtifactKind.EVIDENCE_MAP].content
    git_audit = str(artifacts_by_kind[ProcessAuditArtifactKind.GIT_VERSION_AUDIT].content)
    decision_log = str(artifacts_by_kind[ProcessAuditArtifactKind.DECISION_LOG].content)
    return TinyCloseoutAuditAnswers(
        timeline_event_count=len(timeline["events"]),
        agent_decision_count=decision_log.count("CEO / human board"),
        agent_context_entry_count=len(context["entries"]),
        artifact_paths=tuple(lineage_item["path"] for lineage_item in lineage["lineages"]),
        git_final_commit_sha=final_commit_sha if final_commit_sha in git_audit else "",
        evidence_map_acceptance_refs=tuple(row["acceptance_ref"] for row in evidence_map["rows"]),
    )


__all__ = [
    "TinyCloseoutAuditAnswers",
    "TinyCloseoutFixture",
    "TinyCloseoutSampleManifest",
    "build_tiny_closeout_fixture",
    "materialize_tiny_closeout_sample",
]
