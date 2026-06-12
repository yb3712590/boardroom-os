from __future__ import annotations

from pathlib import Path

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


def _governance_execution_package() -> ExecutionPackage:
    package = _execution_package()
    return package.model_copy(
        update={
            "execution_package_id": ExecutionPackageId(value="exec.ticket.ceo.1"),
            "ticket_ref": TicketId(value="ticket.prd-intake"),
            "seat_ref": AgentSeatRef(value="seat.ceo.delivery"),
            "objective": "Summarize PRD and authorize delivery planning",
            "source_surface_refs": (),
            "allowed_write_set": (),
            "required_outputs": (),
            "commands": (),
            "evidence_obligations": (),
            "model_execution_profile": package.model_execution_profile.model_copy(
                update={
                    "provider": "openai-compatible",
                    "model": "gpt-5.5",
                    "reasoning_effort": "high",
                    "context_window": 400000,
                    "temperature": 0.0,
                    "model_execution_profile_id": "model-profile.ceo.delivery.v2-090f",
                    "tool_permissions": ("filesystem.read",),
                }
            ),
        }
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


def test_atomic_invocation_compiler_consumes_runtime_provider_and_role_config(tmp_path, monkeypatch):
    from boardroom_os.config.boardroom import load_boardroom_settings
    from tests.config.test_boardroom_config import _write_config_files

    paths = _write_config_files(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-secret")
    settings = load_boardroom_settings(paths, env_values={})
    package = _execution_package()
    execution_package = package.model_copy(
        update={
            "seat_ref": AgentSeatRef(value="seat.worker.implementation"),
            "model_execution_profile": package.model_execution_profile.model_copy(
                update={
                    "provider": "openai-compatible",
                    "model": "gpt-5.5",
                    "reasoning_effort": "high",
                    "context_window": 400000,
                    "temperature": 0.0,
                    "model_execution_profile_id": "model-profile.worker.implementation.primary",
                    "tool_permissions": ("filesystem.read", "filesystem.write", "command.execute"),
                }
            ),
        }
    )

    invocation = AtomicInvocationCompiler(workspace_root=tmp_path).compile_with_settings(
        execution_package=execution_package,
        settings=settings,
        seat_ref="seat.worker.implementation",
    )

    assert invocation.permission_policy["policy_ref"] == "policy://boardroom/atomic-agent/exec.ticket.backend.1"
    assert invocation.provider_profile["provider"] == "openai-compatible"
    assert invocation.provider_profile["model"] == "gpt-5.5"
    assert "api_key" not in invocation.provider_profile
    assert invocation.budgets == {
        "max_steps": 128,
        "max_parse_failures": 3,
        "max_observation_chars": 24000,
        "max_wall_seconds": 5400,
        "max_actions_per_turn": 8,
    }
    assert invocation.metadata["budget_profile_ref"] == "worker.implementation.default"
    assert invocation.metadata["resolved_budget_hash"].startswith("sha256:")
    assert invocation.metadata["resolved_tool_policy_hash"].startswith("sha256:")
    assert "submit_result" in invocation.tools
    assert "run_command" in invocation.tools
    assert invocation.output_requirements["require_command_evidence"] is True
    assert invocation.output_requirements["require_source_lineage"] is True
    assert invocation.metadata["runtime_config_hash"].startswith("sha256:")
    assert invocation.metadata["providers_config_hash"].startswith("sha256:")
    assert invocation.metadata["roles_config_hash"].startswith("sha256:")
    assert invocation.metadata["provider_profile_ref"] == "provider.openai-compatible.primary"
    assert invocation.metadata["event_stream_format"] == "jsonl-utf8-lf-canonical-json-v1"


def test_atomic_invocation_compiler_allows_governance_role_without_worker_evidence(
    tmp_path,
    monkeypatch,
):
    from boardroom_os.config.boardroom import BoardroomConfigPaths, load_boardroom_settings

    runtime = tmp_path / "runtime.yaml"
    providers = tmp_path / "providers.yaml"
    roles = tmp_path / "roles.yaml"
    runtime.write_text(
        Path("config/boardroom-runtime.v2-090f.yaml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    providers.write_text(
        Path("config/boardroom-providers.v2-090f.yaml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    roles.write_text(
        Path("config/boardroom-roles.v2-090f.yaml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-secret")
    settings = load_boardroom_settings(
        BoardroomConfigPaths(
            runtime_config=runtime,
            providers_config=providers,
            roles_config=roles,
        ),
        env_values={},
    )

    invocation = AtomicInvocationCompiler(workspace_root=tmp_path).compile_with_settings(
        execution_package=_governance_execution_package(),
        settings=settings,
        seat_ref="seat.ceo.delivery",
    )

    assert invocation.tools == ["read_file", "submit_result"]
    assert invocation.output_requirements["require_event_stream"] is True
    assert invocation.output_requirements["require_command_evidence"] is False
    assert invocation.output_requirements["require_workspace_mutations"] is False
    assert invocation.output_requirements["require_source_lineage"] is False
    assert invocation.metadata["role_slot_ref"] == "seat.ceo.delivery"
    assert invocation.metadata["role_profile_ref"] == "role.governance.ceo"
    assert invocation.metadata["role_category"] == "governance"
    assert invocation.metadata["role_execution_kind"] == "governance"


def test_atomic_invocation_compiler_keeps_worker_evidence_requirements(
    tmp_path,
    monkeypatch,
):
    from boardroom_os.config.boardroom import BoardroomConfigPaths, load_boardroom_settings

    runtime = tmp_path / "runtime.yaml"
    providers = tmp_path / "providers.yaml"
    roles = tmp_path / "roles.yaml"
    runtime.write_text(
        Path("config/boardroom-runtime.v2-090f.yaml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    providers.write_text(
        Path("config/boardroom-providers.v2-090f.yaml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    roles.write_text(
        Path("config/boardroom-roles.v2-090f.yaml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-secret")
    settings = load_boardroom_settings(
        BoardroomConfigPaths(
            runtime_config=runtime,
            providers_config=providers,
            roles_config=roles,
        ),
        env_values={},
    )
    package = _execution_package()
    execution_package = package.model_copy(
        update={
            "seat_ref": AgentSeatRef(value="seat.worker.implementation"),
            "model_execution_profile": package.model_execution_profile.model_copy(
                update={
                    "provider": "openai-compatible",
                    "model": "gpt-5.5",
                    "reasoning_effort": "high",
                    "context_window": 400000,
                    "temperature": 0.0,
                    "model_execution_profile_id": "model-profile.worker.implementation.v2-090f",
                    "tool_permissions": (
                        "filesystem.read",
                        "filesystem.write",
                        "command.execute",
                    ),
                }
            ),
        }
    )

    invocation = AtomicInvocationCompiler(workspace_root=tmp_path).compile_with_settings(
        execution_package=execution_package,
        settings=settings,
        seat_ref="seat.worker.implementation",
    )

    assert "write_file" in invocation.tools
    assert "run_command" in invocation.tools
    assert invocation.output_requirements["require_command_evidence"] is True
    assert invocation.output_requirements["require_workspace_mutations"] is True
    assert invocation.output_requirements["require_source_lineage"] is True
    assert invocation.metadata["role_execution_kind"] == "implementation"


def test_atomic_invocation_compiler_emits_action_protocol_and_checkpoint_metadata(tmp_path, monkeypatch):
    from boardroom_os.config.boardroom import load_boardroom_settings
    from tests.config.test_boardroom_config import _write_config_files

    paths = _write_config_files(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-secret")
    settings = load_boardroom_settings(paths, env_values={})
    package = _execution_package()
    execution_package = package.model_copy(
        update={
            "seat_ref": AgentSeatRef(value="seat.worker.implementation"),
            "model_execution_profile": package.model_execution_profile.model_copy(
                update={
                    "provider": "openai-compatible",
                    "model": "gpt-5.5",
                    "reasoning_effort": "high",
                    "context_window": 400000,
                    "temperature": 0.0,
                    "model_execution_profile_id": "model-profile.worker.implementation.primary",
                    "tool_permissions": ("filesystem.read", "filesystem.write", "command.execute"),
                }
            ),
        }
    )

    invocation = AtomicInvocationCompiler(workspace_root=tmp_path).compile_with_settings(
        execution_package=execution_package,
        settings=settings,
        seat_ref="seat.worker.implementation",
    )

    assert invocation.metadata["action_protocol"] == "agent-action-batch-v1"
    assert invocation.metadata["action_protocol_version"] == "agent-action-batch-v1"
    assert invocation.metadata["checkpoint_policy"] == "required-output-single-command-v1"
    assert invocation.budgets["max_actions_per_turn"] == 8
    assert invocation.output_requirements["required_output_checkpoint"] == {
        "when_all_paths_exist": [output.value for output in execution_package.required_outputs],
        "run_command_id": execution_package.commands[0].command_id.value,
        "max_auto_runs": settings.runtime.atomic_agent.checkpoints.required_output.max_auto_runs,
    }


def test_atomic_invocation_compiler_allows_multiple_declared_commands_without_checkpoint(
    tmp_path,
    monkeypatch,
):
    from boardroom_os.config.boardroom import load_boardroom_settings
    from tests.config.test_boardroom_config import _write_config_files

    paths = _write_config_files(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-secret")
    settings = load_boardroom_settings(paths, env_values={})
    package = _execution_package()
    second_command = package.commands[0].model_copy(update={"command_id": ContractId(value="cmd.second")})
    execution_package = package.model_copy(
        update={
            "seat_ref": AgentSeatRef(value="seat.worker.implementation"),
            "commands": (package.commands[0], second_command),
            "model_execution_profile": package.model_execution_profile.model_copy(
                update={
                    "provider": "openai-compatible",
                    "model": "gpt-5.5",
                    "reasoning_effort": "high",
                    "context_window": 400000,
                    "temperature": 0.0,
                    "model_execution_profile_id": "model-profile.worker.implementation.primary",
                    "tool_permissions": ("filesystem.read", "filesystem.write", "command.execute"),
                }
            ),
        }
    )

    invocation = AtomicInvocationCompiler(workspace_root=tmp_path).compile_with_settings(
        execution_package=execution_package,
        settings=settings,
        seat_ref="seat.worker.implementation",
    )

    assert invocation.output_requirements["required_output_checkpoint"] is None
    assert invocation.output_requirements["declared_command_ids"] == [
        "cmd.test",
        "cmd.second",
    ]
    assert invocation.metadata["checkpoint_policy"] == "manual-declared-commands-v1"


def test_atomic_tool_policy_resolver_derives_tools_from_permissions():
    from boardroom_os.execution.atomic_agent import AtomicToolPolicyResolver

    tools = AtomicToolPolicyResolver().resolve_tools(
        runtime_tools=("list_files", "read_file", "search_files", "write_file", "apply_patch", "run_command", "submit_result"),
        role_tools=("read_file", "apply_patch", "run_command", "submit_result"),
        tool_permissions=("filesystem.read", "filesystem.write", "command.execute"),
        skill_refs=("skill.filesystem.patch", "skill.command.test"),
        requires_command_evidence=True,
        requires_workspace_mutation=True,
    )

    assert tools == ("read_file", "apply_patch", "run_command", "submit_result")


def test_declared_command_ids_are_extracted_from_execution_package_only():
    from boardroom_os.execution.atomic_agent import declared_command_ids_from_execution_package

    assert declared_command_ids_from_execution_package(_execution_package()) == ("cmd.test",)


def test_atomic_invocation_compiler_rejects_provider_profile_mismatch(tmp_path, monkeypatch):
    from boardroom_os.config.boardroom import load_boardroom_settings
    from tests.config.test_boardroom_config import _write_config_files

    paths = _write_config_files(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-secret")
    settings = load_boardroom_settings(paths, env_values={})
    execution_package = _execution_package().model_copy(
        update={"seat_ref": AgentSeatRef(value="seat.worker.implementation")}
    )

    try:
        AtomicInvocationCompiler(workspace_root=tmp_path).compile_with_settings(
            execution_package=execution_package,
            settings=settings,
            seat_ref="seat.worker.implementation",
        )
    except ValueError as exc:
        assert "provider profile does not match execution package" in str(exc)
    else:
        raise AssertionError("expected provider mismatch failure")


def test_atomic_invocation_compiler_rejects_role_slot_seat_mismatch(tmp_path, monkeypatch):
    from boardroom_os.config.boardroom import load_boardroom_settings
    from tests.config.test_boardroom_config import _write_config_files

    paths = _write_config_files(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-secret")
    settings = load_boardroom_settings(paths, env_values={})

    try:
        AtomicInvocationCompiler(workspace_root=tmp_path).compile_with_settings(
            execution_package=_execution_package(),
            settings=settings,
            seat_ref="seat.worker.implementation",
        )
    except ValueError as exc:
        assert "role slot seat_ref must match execution_package.seat_ref" in str(exc)
    else:
        raise AssertionError("expected seat mismatch failure")
