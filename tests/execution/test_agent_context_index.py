import pytest
from pydantic import ValidationError

from boardroom_os.agents.profiles import ModelExecutionProfile
from boardroom_os.agents.seat import AgentSeatRef
from boardroom_os.contracts.evidence_obligation import (
    EvidenceObligation,
    RequiredArtifactType,
    RequiredVerifier,
)
from boardroom_os.contracts.package import PackageCommand
from boardroom_os.contracts.types import (
    AcceptanceRef,
    ContractId,
    EvidenceObligationRef,
    SourceSurfaceRef,
)
from boardroom_os.execution.context_index import (
    AgentContextIndex,
    AgentContextIndexEntry,
    AgentContextIndexEntryId,
    AgentContextSnapshot,
    AgentContextSnapshotId,
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
    ExecutionPackageRef,
    FallbackPolicyRef,
    RequiredOutput,
)
from boardroom_os.graph.ticket import TicketId
from tests.fixtures.execution.role_prompt_hooks import baseline_role_prompt_hook


def _model_execution_profile() -> ModelExecutionProfile:
    return ModelExecutionProfile(
        model_execution_profile_id="model-profile.worker.default",
        provider="anthropic",
        model="claude-opus-4-7",
        reasoning_effort="medium",
        context_window=200000,
        temperature=0.2,
        tool_permissions=("filesystem.write",),
        fallback_policy_ref="fallback.default",
    )


def _evidence_obligation() -> EvidenceObligation:
    return EvidenceObligation(
        evidence_obligation_id=EvidenceObligationRef(value="evidence.source.backend"),
        acceptance_refs=(AcceptanceRef(value="AC-BACKEND"),),
        source_surface_refs=(SourceSurfaceRef(value="surface.backend"),),
        required_artifact_type=RequiredArtifactType(value="source_patch"),
        required_verifier=RequiredVerifier(value="checker"),
        blocking=True,
    )


def _command() -> PackageCommand:
    return PackageCommand(
        command_id=ContractId(value="cmd.test"),
        label="Run tests",
        command=("pytest", "tests"),
        cwd="10-project",
    )


def _execution_package() -> ExecutionPackage:
    return ExecutionPackage(
        execution_package_id=ExecutionPackageId(value="exec.ticket.backend.1"),
        ticket_ref=TicketId(value="ticket.backend"),
        graph_version=7,
        seat_ref=AgentSeatRef(value="seat.worker.backend"),
        model_execution_profile=_model_execution_profile(),
        role_prompt_hook=baseline_role_prompt_hook(),
        objective="Implement backend API",
        context_refs=(
            ContextRef(value="contract.acceptance.active"),
            ContextRef(value="contract.package.active"),
        ),
        constraints=(
            "Only write paths listed in allowed_write_set.",
            "Do not modify active contracts or governance state.",
        ),
        acceptance_refs=(AcceptanceRef(value="AC-BACKEND"),),
        source_surface_refs=(SourceSurfaceRef(value="surface.backend"),),
        allowed_read_refs=(AllowedReadRef(value="README.md"),),
        allowed_write_set=(AllowedWritePath(value="backend/app.py"),),
        required_outputs=(RequiredOutput(value="source:surface.backend"),),
        commands=(_command(),),
        evidence_obligations=(_evidence_obligation(),),
        fallback_policy_ref=FallbackPolicyRef(value="fallback.default"),
        audit_requirements=(AuditRequirement(value="record.received_execution_package"),),
    )


def _snapshot() -> AgentContextSnapshot:
    return build_agent_context_snapshot(_execution_package())


def _snapshot_fields() -> dict[str, object]:
    return _snapshot().model_dump(mode="python")


def _entry(
    *,
    entry_id: str = "agent-context-entry.backend",
    provider_attempt_refs: tuple[ProviderAttemptRef, ...] = (
        ProviderAttemptRef(value="provider-attempt.1"),
    ),
) -> AgentContextIndexEntry:
    return AgentContextIndexEntry(
        entry_id=AgentContextIndexEntryId(value=entry_id),
        snapshot=_snapshot(),
        provider_attempt_refs=provider_attempt_refs,
    )


@pytest.mark.parametrize(
    "field_name",
    (
        "execution_package_ref",
        "ticket_ref",
        "graph_version",
        "seat_ref",
        "objective",
        "model_execution_profile",
        "role_prompt_hook",
        "context_refs",
        "constraints",
        "acceptance_refs",
        "source_surface_refs",
        "allowed_read_refs",
        "allowed_write_set",
        "required_outputs",
        "commands",
        "evidence_obligations",
        "fallback_policy_ref",
        "audit_requirements",
        "snapshot_fingerprint",
    ),
)
def test_agent_context_snapshot_rejects_missing_required_fields(field_name: str) -> None:
    fields = _snapshot_fields()
    fields.pop(field_name)

    with pytest.raises(ValidationError):
        AgentContextSnapshot(**fields)


def test_agent_context_snapshot_rejects_execution_package_id_alias() -> None:
    fields = _snapshot_fields()
    fields.pop("execution_package_ref")
    fields["execution_package_id"] = ExecutionPackageId(value="exec.ticket.backend.1")

    with pytest.raises(ValidationError):
        AgentContextSnapshot(**fields)


@pytest.mark.parametrize(
    "field_name",
    (
        "context_refs",
        "constraints",
        "acceptance_refs",
        "source_surface_refs",
        "allowed_write_set",
        "required_outputs",
        "commands",
        "evidence_obligations",
        "audit_requirements",
    ),
)
def test_agent_context_snapshot_rejects_empty_required_tuples(field_name: str) -> None:
    fields = _snapshot_fields()
    fields[field_name] = ()

    with pytest.raises(ValidationError):
        AgentContextSnapshot(**fields)


def test_build_agent_context_snapshot_allows_empty_allowed_read_refs() -> None:
    package_fields = _execution_package().model_dump(mode="python")
    package_fields["allowed_read_refs"] = ()
    package = ExecutionPackage(**package_fields)

    snapshot = build_agent_context_snapshot(package)

    assert snapshot.allowed_read_refs == ()


def test_build_agent_context_snapshot_derives_execution_package_ref_and_snapshot_id() -> None:
    package = _execution_package()

    snapshot = build_agent_context_snapshot(package)

    assert snapshot.execution_package_ref == ExecutionPackageRef(
        value=package.execution_package_id.value
    )
    assert snapshot.context_snapshot_id == AgentContextSnapshotId(
        value=f"context-snapshot.{snapshot.snapshot_fingerprint[:16]}"
    )
    assert not hasattr(snapshot, "provider_attempt_refs")


def test_build_agent_context_snapshot_preserves_complete_input_boundary() -> None:
    package = _execution_package()

    snapshot = build_agent_context_snapshot(package)

    assert snapshot.ticket_ref == package.ticket_ref
    assert snapshot.graph_version == package.graph_version
    assert snapshot.seat_ref == package.seat_ref
    assert snapshot.objective == package.objective
    assert snapshot.model_execution_profile == package.model_execution_profile
    assert snapshot.role_prompt_hook == package.role_prompt_hook
    assert snapshot.context_refs == package.context_refs
    assert snapshot.constraints == package.constraints
    assert snapshot.acceptance_refs == package.acceptance_refs
    assert snapshot.source_surface_refs == package.source_surface_refs
    assert snapshot.allowed_read_refs == package.allowed_read_refs
    assert snapshot.allowed_write_set == package.allowed_write_set
    assert snapshot.required_outputs == package.required_outputs
    assert snapshot.commands == package.commands
    assert snapshot.evidence_obligations == package.evidence_obligations
    assert snapshot.fallback_policy_ref == package.fallback_policy_ref
    assert snapshot.audit_requirements == package.audit_requirements


def test_build_agent_context_snapshot_is_deterministic_for_same_execution_package() -> None:
    first = build_agent_context_snapshot(_execution_package())
    second = build_agent_context_snapshot(_execution_package())

    assert first.context_snapshot_id == second.context_snapshot_id
    assert first.snapshot_fingerprint == second.snapshot_fingerprint
    assert len(first.snapshot_fingerprint) == 64


def test_agent_context_snapshot_rejects_tampered_fingerprint() -> None:
    fields = _snapshot_fields()
    fields["objective"] = "Tampered objective"

    with pytest.raises(ValidationError, match="snapshot_fingerprint does not match input facts"):
        AgentContextSnapshot(**fields)


def test_agent_context_snapshot_rejects_malformed_fingerprint() -> None:
    fields = _snapshot_fields()
    fields["snapshot_fingerprint"] = "not-a-sha-256-digest"

    with pytest.raises(ValidationError, match="snapshot_fingerprint must be a SHA-256 hex digest"):
        AgentContextSnapshot(**fields)


def test_agent_context_snapshot_fingerprint_includes_allowed_read_refs() -> None:
    fields = _snapshot_fields()
    fields["allowed_read_refs"] = (AllowedReadRef(value="CONTRIBUTING.md"),)

    with pytest.raises(ValidationError, match="snapshot_fingerprint does not match input facts"):
        AgentContextSnapshot(**fields)


def test_agent_context_snapshot_rejects_tampered_snapshot_id() -> None:
    fields = _snapshot_fields()
    fields["context_snapshot_id"] = AgentContextSnapshotId(value="context-snapshot.bad")

    with pytest.raises(ValidationError, match="context_snapshot_id must be derived from snapshot_fingerprint"):
        AgentContextSnapshot(**fields)


def test_agent_context_index_entry_has_version() -> None:
    entry = _entry()

    assert entry.version == 1


def test_agent_context_index_has_version() -> None:
    index = AgentContextIndex(entries=(_entry(),))

    assert index.version == 1


def test_agent_context_index_entry_requires_provider_attempt_refs() -> None:
    with pytest.raises(ValidationError, match="provider_attempt_refs must not be empty"):
        AgentContextIndexEntry(
            entry_id=AgentContextIndexEntryId(value="agent-context-entry.backend"),
            snapshot=_snapshot(),
            provider_attempt_refs=(),
        )


def test_agent_context_index_entry_preserves_provider_attempt_order() -> None:
    entry = AgentContextIndexEntry(
        entry_id=AgentContextIndexEntryId(value="agent-context-entry.backend"),
        snapshot=_snapshot(),
        provider_attempt_refs=(
            ProviderAttemptRef(value="provider-attempt.1"),
            ProviderAttemptRef(value="provider-attempt.2"),
        ),
    )

    assert entry.provider_attempt_refs == (
        ProviderAttemptRef(value="provider-attempt.1"),
        ProviderAttemptRef(value="provider-attempt.2"),
    )


def test_agent_context_index_entry_rejects_duplicate_provider_attempt_refs() -> None:
    with pytest.raises(ValidationError, match="provider_attempt_refs must be unique"):
        AgentContextIndexEntry(
            entry_id=AgentContextIndexEntryId(value="agent-context-entry.backend"),
            snapshot=_snapshot(),
            provider_attempt_refs=(
                ProviderAttemptRef(value="provider-attempt.1"),
                ProviderAttemptRef(value="provider-attempt.1"),
            ),
        )


def test_agent_context_index_rejects_empty_entries() -> None:
    with pytest.raises(ValidationError, match="entries must not be empty"):
        AgentContextIndex(entries=())


def test_agent_context_index_rejects_duplicate_entry_ids() -> None:
    with pytest.raises(ValidationError, match="entry_id values must be unique"):
        AgentContextIndex(
            entries=(
                _entry(
                    entry_id="agent-context-entry.backend",
                    provider_attempt_refs=(ProviderAttemptRef(value="provider-attempt.1"),),
                ),
                _entry(
                    entry_id="agent-context-entry.backend",
                    provider_attempt_refs=(ProviderAttemptRef(value="provider-attempt.2"),),
                ),
            )
        )


def test_agent_context_index_rejects_provider_attempt_claimed_by_multiple_entries() -> None:
    with pytest.raises(ValidationError, match="provider_attempt_ref values must belong to one entry"):
        AgentContextIndex(
            entries=(
                _entry(
                    entry_id="agent-context-entry.backend.1",
                    provider_attempt_refs=(ProviderAttemptRef(value="provider-attempt.1"),),
                ),
                _entry(
                    entry_id="agent-context-entry.backend.2",
                    provider_attempt_refs=(ProviderAttemptRef(value="provider-attempt.1"),),
                ),
            )
        )


def test_agent_context_index_allows_same_snapshot_with_distinct_provider_attempt_refs() -> None:
    snapshot = _snapshot()

    index = AgentContextIndex(
        entries=(
            AgentContextIndexEntry(
                entry_id=AgentContextIndexEntryId(value="agent-context-entry.backend.1"),
                snapshot=snapshot,
                provider_attempt_refs=(ProviderAttemptRef(value="provider-attempt.1"),),
            ),
            AgentContextIndexEntry(
                entry_id=AgentContextIndexEntryId(value="agent-context-entry.backend.2"),
                snapshot=snapshot,
                provider_attempt_refs=(ProviderAttemptRef(value="provider-attempt.2"),),
            ),
        )
    )

    assert len(index.entries) == 2


def test_agent_context_index_models_reject_unknown_extra_fields() -> None:
    snapshot_fields = _snapshot_fields()
    snapshot_fields["provider_attempt_refs"] = (ProviderAttemptRef(value="provider-attempt.1"),)
    with pytest.raises(ValidationError):
        AgentContextSnapshot(**snapshot_fields)

    with pytest.raises(ValidationError):
        AgentContextIndexEntry(
            entry_id=AgentContextIndexEntryId(value="agent-context-entry.backend"),
            snapshot=_snapshot(),
            provider_attempt_refs=(ProviderAttemptRef(value="provider-attempt.1"),),
            unexpected="not allowed",
        )

    with pytest.raises(ValidationError):
        AgentContextIndex(
            entries=(_entry(),),
            unexpected="not allowed",
        )
