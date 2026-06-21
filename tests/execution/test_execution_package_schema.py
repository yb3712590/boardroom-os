import pytest
from pydantic import ValidationError

from boardroom_os.agents.categories import RoleCategory
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
from boardroom_os.graph.ticket import TicketId
from tests.fixtures.execution.role_prompt_hooks import baseline_role_prompt_hook


def test_execution_package_captures_complete_worker_input_snapshot() -> None:
    model_execution_profile = ModelExecutionProfile(
        model_execution_profile_id="model-profile.worker.default",
        provider="anthropic",
        model="claude-opus-4-7",
        reasoning_effort="medium",
        context_window=200000,
        temperature=0.2,
        tool_permissions=("filesystem.write",),
        fallback_policy_ref="fallback.default",
    )
    evidence_obligation = EvidenceObligation(
        evidence_obligation_id=EvidenceObligationRef(value="evidence.source.backend"),
        acceptance_refs=(AcceptanceRef(value="AC-BACKEND"),),
        source_surface_refs=(SourceSurfaceRef(value="surface.backend"),),
        required_artifact_type=RequiredArtifactType(value="source_patch"),
        required_verifier=RequiredVerifier(value="checker"),
        blocking=True,
    )
    command = PackageCommand(
        command_id=ContractId(value="cmd.test"),
        label="Run tests",
        command=("pytest", "tests"),
        cwd="10-project",
    )

    package = ExecutionPackage(
        execution_package_id=ExecutionPackageId(value="exec.ticket.backend.1"),
        ticket_ref=TicketId(value="ticket.backend"),
        graph_version=7,
        seat_ref=AgentSeatRef(value="seat.worker.backend"),
        model_execution_profile=model_execution_profile,
        role_prompt_hook=baseline_role_prompt_hook(),
        objective="Implement backend API",
        context_refs=(ContextRef(value="context.contracts.active"),),
        constraints=("Only write backend files",),
        acceptance_refs=(AcceptanceRef(value="AC-BACKEND"),),
        source_surface_refs=(SourceSurfaceRef(value="surface.backend"),),
        allowed_read_refs=(AllowedReadRef(value="README.md"),),
        allowed_write_set=(AllowedWritePath(value="backend/app.py"),),
        required_outputs=(RequiredOutput(value="backend source patch"),),
        commands=(command,),
        evidence_obligations=(evidence_obligation,),
        fallback_policy_ref=FallbackPolicyRef(value="fallback.default"),
        audit_requirements=(AuditRequirement(value="record received context"),),
    )

    assert package.version == 1
    assert package.ticket_ref == TicketId(value="ticket.backend")
    assert package.seat_ref == AgentSeatRef(value="seat.worker.backend")
    assert package.model_execution_profile == model_execution_profile
    assert package.role_prompt_hook == baseline_role_prompt_hook()
    assert package.commands == (command,)
    assert package.evidence_obligations == (evidence_obligation,)
    assert package.fallback_policy_ref == FallbackPolicyRef(value="fallback.default")


def test_execution_package_accepts_yaml_shaped_ref_strings() -> None:
    package = ExecutionPackage(
        execution_package_id="exec.ticket.backend.1",
        ticket_ref="ticket.backend",
        graph_version=7,
        seat_ref="seat.worker.backend",
        model_execution_profile={
            "model_execution_profile_id": "model-profile.worker.default",
            "provider": "anthropic",
            "model": "claude-opus-4-7",
            "reasoning_effort": "medium",
            "context_window": 200000,
            "temperature": 0.2,
            "tool_permissions": ("filesystem.write",),
            "fallback_policy_ref": "fallback.default",
        },
        role_prompt_hook=baseline_role_prompt_hook().model_dump(),
        objective="Implement backend API",
        context_refs=("context.contracts.active",),
        constraints=("Only write backend files",),
        acceptance_refs=("AC-BACKEND",),
        source_surface_refs=("surface.backend",),
        allowed_read_refs=("README.md",),
        allowed_write_set=("backend/app.py",),
        required_outputs=("backend source patch",),
        commands=(
            {
                "command_id": {"value": "cmd.test"},
                "label": "Run tests",
                "command": ("pytest", "tests"),
                "cwd": "10-project",
            },
        ),
        evidence_obligations=(
            {
                "evidence_obligation_id": {"value": "evidence.source.backend"},
                "acceptance_refs": ({"value": "AC-BACKEND"},),
                "source_surface_refs": ({"value": "surface.backend"},),
                "required_artifact_type": {"value": "source_patch"},
                "required_verifier": {"value": "checker"},
                "blocking": True,
            },
        ),
        fallback_policy_ref="fallback.default",
        audit_requirements=("record received context",),
    )

    assert package.execution_package_id == ExecutionPackageId(value="exec.ticket.backend.1")
    assert package.ticket_ref == TicketId(value="ticket.backend")
    assert package.allowed_write_set == (AllowedWritePath(value="backend/app.py"),)


def test_execution_package_allows_generic_read_only_verification_package() -> None:
    package = _read_only_verification_package(objective="plan-live-verification-from-contracts")

    assert package.allowed_write_set == ()
    assert package.role_prompt_hook.role_category is RoleCategory.VERIFICATION


def test_execution_package_rejects_empty_write_set_for_implementation_hook() -> None:
    with pytest.raises(ValidationError, match="read-only execution packages require verification role prompt hook"):
        _read_only_verification_package(
            objective="verify-blackbox",
            role_prompt_hook=baseline_role_prompt_hook("role-prompt-hook.baseline.worker.v1"),
        )


def test_execution_package_rejects_read_only_context_refs_outside_allowed_reads() -> None:
    with pytest.raises(ValidationError, match="context_refs must be covered by allowed_read_refs"):
        _read_only_verification_package(
            context_refs=(ContextRef(value="secrets/provider.env"),),
            allowed_read_refs=(AllowedReadRef(value="README.md"),),
        )


def _read_only_verification_package(
    *,
    objective: str = "verify-blackbox",
    role_prompt_hook=None,
    context_refs: tuple[ContextRef, ...] = (ContextRef(value="context.run-manifest.raw"),),
    allowed_read_refs: tuple[AllowedReadRef, ...] = (
        AllowedReadRef(value="context.run-manifest.raw"),
    ),
) -> ExecutionPackage:
    model_execution_profile = ModelExecutionProfile(
        model_execution_profile_id="model-profile.tester.default",
        provider="anthropic",
        model="claude-opus-4-7",
        reasoning_effort="medium",
        context_window=200000,
        temperature=0.2,
        tool_permissions=("filesystem.read",),
        fallback_policy_ref="fallback.default",
    )
    evidence_obligation = EvidenceObligation(
        evidence_obligation_id=EvidenceObligationRef(value="evidence.blackbox.plan"),
        acceptance_refs=(AcceptanceRef(value="AC-BLACKBOX"),),
        source_surface_refs=(SourceSurfaceRef(value="surface.run-manifest"),),
        required_artifact_type=RequiredArtifactType(value="blackbox_plan"),
        required_verifier=RequiredVerifier(value="tester"),
        blocking=True,
    )
    command = PackageCommand(
        command_id=ContractId(value="cmd.live-blackbox"),
        label="Run live blackbox checks",
        command=("pytest", "tests/live"),
        cwd="10-project",
    )

    return ExecutionPackage(
        execution_package_id=ExecutionPackageId(value="exec.ticket.verify.read-only.1"),
        ticket_ref=TicketId(value="ticket.verify.read-only"),
        graph_version=9,
        seat_ref=AgentSeatRef(value="seat.tester.blackbox"),
        model_execution_profile=model_execution_profile,
        role_prompt_hook=role_prompt_hook
        or baseline_role_prompt_hook("role-prompt-hook.baseline.tester.v1"),
        objective=objective,
        context_refs=context_refs,
        constraints=("Derive a verification plan without modifying workspace files.",),
        acceptance_refs=(AcceptanceRef(value="AC-BLACKBOX"),),
        source_surface_refs=(SourceSurfaceRef(value="surface.run-manifest"),),
        allowed_read_refs=allowed_read_refs,
        allowed_write_set=(),
        required_outputs=(RequiredOutput(value="blackbox verification plan"),),
        commands=(command,),
        evidence_obligations=(evidence_obligation,),
        fallback_policy_ref=FallbackPolicyRef(value="fallback.default"),
        audit_requirements=(AuditRequirement(value="record received verification context"),),
    )
