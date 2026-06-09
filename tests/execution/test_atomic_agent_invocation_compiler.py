from __future__ import annotations

from atomic_agent.models import AgentInvocation

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
from boardroom_os.execution.atomic_agent import AtomicInvocationCompiler
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


def _execution_package() -> ExecutionPackage:
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
    return ExecutionPackage(
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


def test_atomic_invocation_compiler_maps_execution_package_to_agent_invocation(tmp_path):
    execution_package = _execution_package()
    compiler = AtomicInvocationCompiler(
        workspace_root=tmp_path,
        enabled_tools=(
            "list_files",
            "read_file",
            "write_file",
            "apply_patch",
            "run_command",
            "submit_result",
        ),
        max_steps=12,
        wall_time_seconds=300,
    )

    invocation = compiler.compile(execution_package)

    assert isinstance(invocation, AgentInvocation)
    assert invocation.invocation_id == (
        f"atomic-invocation.{execution_package.execution_package_id.value}"
    )
    assert invocation.workspace_root == str(tmp_path)
    assert invocation.allowed_write_set == [path.value for path in execution_package.allowed_write_set]
    assert invocation.tools == [
        "list_files",
        "read_file",
        "write_file",
        "apply_patch",
        "run_command",
        "submit_result",
    ]
    assert invocation.provider_profile == {
        "provider": execution_package.model_execution_profile.provider,
        "model": execution_package.model_execution_profile.model,
        "reasoning_effort": execution_package.model_execution_profile.reasoning_effort,
        "temperature": execution_package.model_execution_profile.temperature,
        "context_window": execution_package.model_execution_profile.context_window,
    }
    assert invocation.budgets == {"max_steps": 12, "wall_time_seconds": 300}
    assert invocation.metadata["execution_package_ref"] == execution_package.execution_package_id.value
    assert invocation.metadata["ticket_ref"] == execution_package.ticket_ref.value
    assert invocation.metadata["seat_ref"] == execution_package.seat_ref.value
    assert invocation.metadata["graph_version"] == execution_package.graph_version
    assert invocation.role_context is not None
    assert execution_package.role_prompt_hook.hook_ref.value in invocation.role_context
    assert execution_package.role_prompt_hook.content_sha256.value in invocation.role_context
    assert invocation.permission_policy["commands"][0]["command_id"] == (
        execution_package.commands[0].command_id.value
    )
    assert invocation.permission_policy["commands"][0]["argv"] == list(
        execution_package.commands[0].command
    )
    assert invocation.output_requirements["require_event_stream"] is True
    assert invocation.output_requirements["require_workspace_mutations"] is True


def test_atomic_invocation_compiler_rejects_absolute_workspace_write_set(tmp_path):
    execution_package = _execution_package().model_copy(update={"allowed_write_set": ("/tmp/escape.py",)})
    compiler = AtomicInvocationCompiler(workspace_root=tmp_path)

    try:
        compiler.compile(execution_package)
    except ValueError as exc:
        assert "allowed_write_set must contain relative paths" in str(exc)
    else:
        raise AssertionError("expected relative path validation failure")


def test_atomic_invocation_compiler_rejects_windows_absolute_workspace_write_set(tmp_path):
    execution_package = _execution_package().model_copy(update={"allowed_write_set": ("C:/tmp/escape.py",)})
    compiler = AtomicInvocationCompiler(workspace_root=tmp_path)

    try:
        compiler.compile(execution_package)
    except ValueError as exc:
        assert "allowed_write_set must contain relative paths" in str(exc)
    else:
        raise AssertionError("expected relative path validation failure")


def test_atomic_invocation_compiler_rejects_parent_workspace_write_set(tmp_path):
    execution_package = _execution_package().model_copy(update={"allowed_write_set": ("../escape.py",)})
    compiler = AtomicInvocationCompiler(workspace_root=tmp_path)

    try:
        compiler.compile(execution_package)
    except ValueError as exc:
        assert "allowed_write_set must contain relative paths" in str(exc)
    else:
        raise AssertionError("expected relative path validation failure")


def test_atomic_invocation_compiler_rejects_absolute_command_cwd(tmp_path):
    command = _execution_package().commands[0].model_copy(update={"cwd": "/tmp"})
    execution_package = _execution_package().model_copy(update={"commands": (command,)})
    compiler = AtomicInvocationCompiler(workspace_root=tmp_path)

    try:
        compiler.compile(execution_package)
    except ValueError as exc:
        assert "command cwd must contain relative paths" in str(exc)
    else:
        raise AssertionError("expected command cwd relative path validation failure")


def test_atomic_invocation_compiler_rejects_windows_absolute_command_cwd(tmp_path):
    command = _execution_package().commands[0].model_copy(update={"cwd": "C:/tmp"})
    execution_package = _execution_package().model_copy(update={"commands": (command,)})
    compiler = AtomicInvocationCompiler(workspace_root=tmp_path)

    try:
        compiler.compile(execution_package)
    except ValueError as exc:
        assert "command cwd must contain relative paths" in str(exc)
    else:
        raise AssertionError("expected command cwd relative path validation failure")


def test_atomic_invocation_compiler_rejects_parent_command_cwd(tmp_path):
    command = _execution_package().commands[0].model_copy(update={"cwd": "../outside"})
    execution_package = _execution_package().model_copy(update={"commands": (command,)})
    compiler = AtomicInvocationCompiler(workspace_root=tmp_path)

    try:
        compiler.compile(execution_package)
    except ValueError as exc:
        assert "command cwd must contain relative paths" in str(exc)
    else:
        raise AssertionError("expected command cwd relative path validation failure")
