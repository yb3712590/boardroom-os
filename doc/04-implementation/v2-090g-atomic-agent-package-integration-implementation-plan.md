# V2-090G Atomic-agent Package Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Integrate atomic-agent（原子智能体） as an external Python package through a Boardroom anti-corruption adapter so Boardroom `ExecutionPackage`（执行包） can be executed by `AgentRuntimePort`（智能体运行端口） and projected back into Boardroom evidence（证据） without copying source code or service-wrapping atomic-agent.

**Architecture:** Boardroom OS（董事会操作系统） owns governance, contracts, reducers, evidence verification, and closeout; atomic-agent owns the controlled agent loop（受控智能体循环）. V2-090G adds `boardroom_os.execution.atomic_agent`（原子智能体执行适配模块） with a typed port, package adapter, invocation compiler, result validator, and result projector. The adapter calls only atomic-agent's public `AgentRuntimePort.invoke(AgentInvocation) -> AgentRunResult` contract and treats returned JSONL event streams, tool attempts, workspace mutations, and artifacts as auditable execution facts, not governance decisions.

**Tech Stack:** Python 3.11+, Pydantic v2 models（Pydantic 模型）, pytest, existing Boardroom `ExecutionPackage` / `ProviderAttempt` / `WorkProduct` / `EvidenceClaim` / `SourceInventory` models, external `atomic-agent` package installed with `python -m pip install -e ../atomic-agent` during development.

---

## File Structure

- Create `src/boardroom_os/execution/atomic_agent.py`
  - Owns Boardroom-facing `AtomicAgentPort`（原子智能体端口）, `AtomicAgentPackageAdapter`（原子智能体包适配器）, `AtomicAgentDependencyInfo`（原子智能体依赖信息）, `AtomicInvocationCompiler`（原子调用编译器）, `AtomicResultValidator`（原子结果校验器）, and `AtomicResultProjector`（原子结果投影器）.
  - Imports atomic-agent only inside adapter/factory functions so normal Boardroom import does not crash until the atomic path is used.
- Modify `src/boardroom_os/execution/__init__.py`
  - Export the new public adapter types after tests prove stable names.
- Create `tests/execution/test_atomic_agent_invocation_compiler.py`
  - Tests deterministic compilation from `ExecutionPackage` to atomic-agent-shaped invocation payloads.
- Create `tests/execution/test_atomic_agent_result_projection.py`
  - Tests completed `AgentRunResult` validation, event hash verification, workspace mutation projection, and WorkProduct draft generation.
- Create `tests/negative/test_atomic_agent_integration_fail_closed.py`
  - Tests missing package, type mismatch, failed status, missing event stream/hash, governance field injection, path/command escape, and missing workspace mutation.
- Modify `tests/proving/fixtures/tiny_package_assembly.py`
  - Add a narrow fixture hook for atomic-agent execution result projection only after unit tests pass. Do not rebuild golden sample in V2-090G.
- Modify `README.md`
  - Add sibling checkout + editable install instructions for atomic-agent and clarify Boardroom/atomic-agent responsibility split.
- Modify `doc/04-implementation/backlog.md`
  - Add V2-090G as a new work package after V2-090F; update Phase 9 counts from `5 / 6` to `5 / 7`; mark V2-090F blocked on V2-090G instead of generic self-built AgentWorkExecutor.
- Modify `doc/04-implementation/acceptance-criteria.md`
  - Add Phase 9 checkbox for V2-090G proving AC-V2-EXECUTION-001/002/003 and AC-V2-EVIDENCE-002 lineage via atomic-agent returned facts; keep V2-090F golden sample checkbox unchecked.
- Modify `doc/04-implementation/INDEX.md`
  - Register the V2-090G spec and this implementation plan.
- Modify `doc/05-project-log/decisions.md`
  - Add decision that Boardroom integrates atomic-agent as an external package via public runtime port, not source copy or service wrapper.
- Modify `doc/05-project-log/2026-06.md`
  - Add completion log only after implementation verification passes, not during spec/plan drafting.

---

## Pre-flight before implementation

- [ ] Confirm atomic-agent is available as a sibling checkout.

Run:

```bash
python -c "from pathlib import Path; p = Path('../atomic-agent').resolve(); print(p); print('exists=' + str(p.is_dir()))"
```

Expected: prints `/Users/bill/projects/atomic-agent` or another sibling checkout path and `exists=True`. If the sibling path does not exist, stop and ask the user to provide it; do not fall back to `.worktrees/atomic-agent` for implementation.

- [ ] Install atomic-agent in the active Boardroom environment.

Run:

```bash
python -m pip install -e ../atomic-agent
```

Expected: pip reports an editable install for `atomic-agent` from `../atomic-agent`. Installing from `.worktrees/atomic-agent` is not allowed for V2-090G implementation.

- [ ] Verify public import only.

Run:

```bash
python -c "from atomic_agent import AgentRuntimePort; from atomic_agent.models import AgentInvocation, AgentRunResult; print('atomic-agent import ok')"
```

Expected: `atomic-agent import ok`.

- [ ] Verify atomic-agent public model contract before writing Boardroom adapter code.

Run:

```bash
python -c "from atomic_agent.models import AgentInvocation, AgentRunResult, AgentRunStatus; print('AgentInvocation fields:', tuple(AgentInvocation.model_fields.keys())); print('AgentRunResult fields:', tuple(AgentRunResult.model_fields.keys())); print('AgentRunStatus values:', tuple(s.value for s in AgentRunStatus))"
```

Expected:

```text
AgentInvocation fields: ('invocation_id', 'task', 'workspace_root', 'allowed_write_set', 'tools', 'permission_policy', 'provider_profile', 'budgets', 'output_requirements', 'role_context', 'skill_context', 'initial_files', 'metadata')
AgentRunResult fields: ('run_id', 'status', 'event_stream_ref', 'events_hash', 'tool_attempts', 'workspace_mutations', 'artifacts', 'summary', 'failure_kind', 'failure_message', 'failed_action_ref')
AgentRunStatus values: ('completed', 'failed', 'interrupted', 'requires_approval')
```

If any field differs, stop and update this plan/spec before implementation; do not guess schema aliases.

- [ ] Do not use `.worktrees/atomic-agent/` during V2-090G implementation. It is a historical exploration copy only; all installation, import verification, and contract checks must use sibling `../atomic-agent`.

---

### Task 1: Add fail-closed tests for missing or malformed atomic-agent dependency

**Files:**
- Create: `tests/negative/test_atomic_agent_integration_fail_closed.py`
- Create later: `src/boardroom_os/execution/atomic_agent.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/negative/test_atomic_agent_integration_fail_closed.py` with this initial content:

```python
from __future__ import annotations

import pytest


def test_atomic_agent_adapter_fails_closed_when_package_missing(monkeypatch):
    from boardroom_os.execution.atomic_agent import (
        AtomicAgentAdapterError,
        AtomicAgentPackageAdapter,
    )

    def reject_import(name: str):
        raise ImportError(f"blocked import: {name}")

    adapter = AtomicAgentPackageAdapter(import_atomic_agent=reject_import)

    with pytest.raises(AtomicAgentAdapterError, match="atomic-agent package is not importable"):
        adapter.dependency_info()


def test_atomic_agent_adapter_rejects_non_agent_run_result():
    from boardroom_os.execution.atomic_agent import (
        AtomicAgentAdapterError,
        AtomicAgentDependencyInfo,
        AtomicAgentPackageAdapter,
    )

    class BadRuntimePort:
        def invoke(self, invocation):
            return {"status": "completed"}

    adapter = AtomicAgentPackageAdapter(
        runtime_port=BadRuntimePort(),
        dependency_info=AtomicAgentDependencyInfo(
            package_name="atomic-agent",
            package_version="0.0.0",
            source_path="/tmp/atomic-agent",
            runtime_port_contract_ref="atomic-agent.docs.agent-runtime-port",
        ),
    )

    with pytest.raises(AtomicAgentAdapterError, match="AgentRuntimePort returned non-AgentRunResult"):
        adapter.invoke({"invocation_id": "invocation.atomic.test"})
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
PYTHONPATH=src:. python -m pytest tests/negative/test_atomic_agent_integration_fail_closed.py -q --tb=short --basetemp .pytest-tmp-v2090g-adapter-red
```

Expected: FAIL with `ModuleNotFoundError: No module named 'boardroom_os.execution.atomic_agent'`.

- [ ] **Step 3: Implement minimal adapter dependency boundary**

Create `src/boardroom_os/execution/atomic_agent.py` with this content:

```python
from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from types import ModuleType
from typing import Any, Callable, Protocol


class AtomicAgentAdapterError(RuntimeError):
    pass


@dataclass(frozen=True)
class AtomicAgentDependencyInfo:
    package_name: str
    package_version: str
    source_path: str | None
    runtime_port_contract_ref: str


class AtomicAgentPort(Protocol):
    def invoke(self, invocation: Any) -> Any:
        ...


def _default_import_atomic_agent(name: str) -> ModuleType:
    return import_module(name)


class AtomicAgentPackageAdapter:
    def __init__(
        self,
        *,
        runtime_port: AtomicAgentPort | None = None,
        dependency_info: AtomicAgentDependencyInfo | None = None,
        import_atomic_agent: Callable[[str], ModuleType] = _default_import_atomic_agent,
    ) -> None:
        self._runtime_port = runtime_port
        self._dependency_info = dependency_info
        self._import_atomic_agent = import_atomic_agent

    def dependency_info(self) -> AtomicAgentDependencyInfo:
        if self._dependency_info is not None:
            return self._dependency_info
        try:
            module = self._import_atomic_agent("atomic_agent")
        except ImportError as exc:
            raise AtomicAgentAdapterError("atomic-agent package is not importable") from exc
        try:
            package_version = version("atomic-agent")
        except PackageNotFoundError:
            package_version = getattr(module, "__version__", "unknown")
        module_file = getattr(module, "__file__", None)
        source_path = str(Path(module_file).resolve().parents[1]) if module_file else None
        return AtomicAgentDependencyInfo(
            package_name="atomic-agent",
            package_version=package_version,
            source_path=source_path,
            runtime_port_contract_ref="atomic-agent.docs.agent-runtime-port.v1",
        )

    def invoke(self, invocation: Any) -> Any:
        runtime_port = self._runtime_port
        if runtime_port is None:
            raise AtomicAgentAdapterError("atomic-agent runtime_port is required")
        result = runtime_port.invoke(invocation)
        result_class_name = type(result).__name__
        if result_class_name != "AgentRunResult":
            raise AtomicAgentAdapterError("AgentRuntimePort returned non-AgentRunResult")
        return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
PYTHONPATH=src:. python -m pytest tests/negative/test_atomic_agent_integration_fail_closed.py -q --tb=short --basetemp .pytest-tmp-v2090g-adapter-green
```

Expected: PASS (`2 passed`).

- [ ] **Step 5: Commit**

```bash
git add src/boardroom_os/execution/atomic_agent.py tests/negative/test_atomic_agent_integration_fail_closed.py
git commit -m "feat: 增加原子智能体适配边界"
```

---

### Task 2: Compile ExecutionPackage into atomic-agent AgentInvocation

**Files:**
- Modify: `src/boardroom_os/execution/atomic_agent.py`
- Create: `tests/execution/test_atomic_agent_invocation_compiler.py`
- Inline local execution package helper in this test file, copying the construction shape from `tests/execution/test_execution_package_schema.py::test_execution_package_captures_complete_worker_input_snapshot`; do not import helper names that are not defined in the current codebase.

- [ ] **Step 1: Write failing compiler tests**

Create `tests/execution/test_atomic_agent_invocation_compiler.py`:

```python
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
        enabled_tools=("list_files", "read_file", "write_file", "apply_patch", "run_command", "submit_result"),
        max_steps=12,
        wall_time_seconds=300,
    )

    invocation = compiler.compile(execution_package)

    assert isinstance(invocation, AgentInvocation)
    assert invocation.invocation_id == f"atomic-invocation.{execution_package.execution_package_id.value}"
    assert invocation.workspace_root == str(tmp_path)
    assert invocation.allowed_write_set == [path.value for path in execution_package.allowed_write_set]
    assert invocation.tools == ["list_files", "read_file", "write_file", "apply_patch", "run_command", "submit_result"]
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
    assert invocation.permission_policy["commands"][0]["command_id"] == execution_package.commands[0].command_id
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
PYTHONPATH=src:. python -m pytest tests/execution/test_atomic_agent_invocation_compiler.py -q --tb=short --basetemp .pytest-tmp-v2090g-compiler-red
```

Expected: FAIL with `ImportError` or `AttributeError` for `AtomicInvocationCompiler`.

- [ ] **Step 3: Implement `AtomicInvocationCompiler`**

Append to `src/boardroom_os/execution/atomic_agent.py`:

```python
from pathlib import PurePosixPath

from boardroom_os.execution.package import ExecutionPackage


class AtomicInvocationCompiler:
    def __init__(
        self,
        *,
        workspace_root: str | Path,
        enabled_tools: tuple[str, ...] = (
            "list_files",
            "read_file",
            "search_files",
            "write_file",
            "apply_patch",
            "run_command",
            "submit_result",
        ),
        max_steps: int = 20,
        wall_time_seconds: int = 600,
    ) -> None:
        self.workspace_root = Path(workspace_root)
        self.enabled_tools = enabled_tools
        self.max_steps = max_steps
        self.wall_time_seconds = wall_time_seconds

    def compile(self, execution_package: ExecutionPackage) -> Any:
        try:
            agent_models = import_module("atomic_agent.models")
        except ImportError as exc:
            raise AtomicAgentAdapterError("atomic-agent package is not importable") from exc
        AgentInvocation = getattr(agent_models, "AgentInvocation")
        allowed_write_set = [path.value for path in execution_package.allowed_write_set]
        for path in allowed_write_set:
            parsed = PurePosixPath(path)
            if parsed.is_absolute() or ".." in parsed.parts:
                raise ValueError("allowed_write_set must contain relative paths")
        role_context = "\n".join(
            (
                f"RolePromptHook ref: {execution_package.role_prompt_hook.hook_ref.value}",
                f"RolePromptHook version: {execution_package.role_prompt_hook.hook_version}",
                f"RolePromptHook sha256: {execution_package.role_prompt_hook.content_sha256.value}",
                execution_package.role_prompt_hook.prompt_text,
            )
        )
        permission_commands = [
            {
                "command_id": command.command_id,
                "kind": command.kind.value,
                "argv": list(command.argv),
                "cwd": command.cwd,
                "timeout_seconds": command.timeout_seconds,
            }
            for command in execution_package.commands
        ]
        evidence_obligations = [
            obligation.model_dump(mode="json") for obligation in execution_package.evidence_obligations
        ]
        task = "\n".join(
            (
                execution_package.objective,
                "",
                "Constraints:",
                *[f"- {constraint}" for constraint in execution_package.constraints],
                "",
                "Evidence obligations:",
                *[f"- {item}" for item in evidence_obligations],
            )
        )
        return AgentInvocation(
            invocation_id=f"atomic-invocation.{execution_package.execution_package_id.value}",
            task=task,
            workspace_root=str(self.workspace_root),
            allowed_write_set=allowed_write_set,
            tools=list(self.enabled_tools),
            permission_policy={
                "commands": permission_commands,
                "network": {"default": "deny"},
                "filesystem": {"allowed_write_set": allowed_write_set},
            },
            provider_profile={
                "provider": execution_package.model_execution_profile.provider,
                "model": execution_package.model_execution_profile.model,
                "reasoning_effort": execution_package.model_execution_profile.reasoning_effort,
                "temperature": execution_package.model_execution_profile.temperature,
                "context_window": execution_package.model_execution_profile.context_window,
            },
            budgets={"max_steps": self.max_steps, "wall_time_seconds": self.wall_time_seconds},
            output_requirements={
                "require_event_stream": True,
                "require_tool_attempts": True,
                "require_workspace_mutations": True,
                "require_artifacts": True,
                "evidence_obligations": evidence_obligations,
            },
            role_context=role_context,
            skill_context={"audit_requirements": [item.value for item in execution_package.audit_requirements]},
            initial_files=[ref.value for ref in execution_package.context_refs],
            metadata={
                "execution_package_ref": execution_package.execution_package_id.value,
                "ticket_ref": execution_package.ticket_ref.value,
                "seat_ref": execution_package.seat_ref.value,
                "graph_version": execution_package.graph_version,
                "acceptance_refs": [ref.value for ref in execution_package.acceptance_refs],
                "source_surface_refs": [ref.value for ref in execution_package.source_surface_refs],
            },
        )
```

- [ ] **Step 4: Run compiler tests**

Run:

```bash
PYTHONPATH=src:. python -m pytest tests/execution/test_atomic_agent_invocation_compiler.py -q --tb=short --basetemp .pytest-tmp-v2090g-compiler-green
```

Expected: PASS (`2 passed`).

- [ ] **Step 5: Run existing execution package regression**

Run:

```bash
PYTHONPATH=src:. python -m pytest tests/execution/test_execution_package_schema.py tests/execution/test_execution_package_compiler.py tests/execution/test_atomic_agent_invocation_compiler.py -q --tb=short --basetemp .pytest-tmp-v2090g-compiler-regression
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/boardroom_os/execution/atomic_agent.py tests/execution/test_atomic_agent_invocation_compiler.py
git commit -m "feat: 编译原子智能体调用"
```

---

### Task 3: Validate AgentRunResult and event stream hash

**Files:**
- Modify: `src/boardroom_os/execution/atomic_agent.py`
- Extend: `tests/negative/test_atomic_agent_integration_fail_closed.py`
- Create: `tests/execution/test_atomic_agent_result_projection.py`

- [ ] **Step 1: Write failing validator tests**

Append to `tests/negative/test_atomic_agent_integration_fail_closed.py`:

```python
from pathlib import Path

from atomic_agent.models import AgentRunResult, AgentRunStatus


def _result(**overrides):
    payload = {
        "run_id": "run.atomic.1",
        "status": AgentRunStatus.COMPLETED,
        "event_stream_ref": "events.jsonl",
        "events_hash": "sha256:abc",
        "tool_attempts": [{"tool_attempt_id": "tool.1", "action": "write_file"}],
        "workspace_mutations": [{"path": "backend/app.py", "tool_attempt_id": "tool.1", "sha256": "0" * 64}],
        "artifacts": [{"artifact_ref": "artifact://run.atomic.1/result.json", "sha256": "1" * 64}],
        "summary": "Updated backend/app.py",
    }
    payload.update(overrides)
    return AgentRunResult(**payload)


def test_atomic_result_validator_rejects_failed_status():
    from boardroom_os.execution.atomic_agent import AtomicAgentResultValidator

    result = _result(status=AgentRunStatus.FAILED, failure_kind="provider_failed", failure_message="boom")
    validator = AtomicAgentResultValidator(allowed_write_set=("backend",), declared_command_ids=("test-backend",))

    with pytest.raises(ValueError, match="atomic-agent result must be completed"):
        validator.validate(result)


def test_atomic_result_validator_rejects_missing_workspace_mutation_for_implementation():
    from boardroom_os.execution.atomic_agent import AtomicAgentResultValidator

    result = _result(workspace_mutations=[])
    validator = AtomicAgentResultValidator(allowed_write_set=("backend",), declared_command_ids=("test-backend",))

    with pytest.raises(ValueError, match="workspace mutation is required"):
        validator.validate(result)


def test_atomic_result_validator_rejects_governance_fields():
    from boardroom_os.execution.atomic_agent import AtomicAgentResultValidator

    result = _result(artifacts=[{"artifact_ref": "artifact://x", "sha256": "1" * 64, "ticket_completed": True}])
    validator = AtomicAgentResultValidator(allowed_write_set=("backend",), declared_command_ids=("test-backend",))

    with pytest.raises(ValueError, match="atomic-agent result must not contain governance field"):
        validator.validate(result)


def test_atomic_result_validator_rejects_write_path_outside_allowed_set():
    from boardroom_os.execution.atomic_agent import AtomicAgentResultValidator

    result = _result(workspace_mutations=[{"path": "frontend/app.js", "tool_attempt_id": "tool.1", "sha256": "0" * 64}])
    validator = AtomicAgentResultValidator(allowed_write_set=("backend",), declared_command_ids=("test-backend",))

    with pytest.raises(ValueError, match="workspace mutation path is outside allowed_write_set"):
        validator.validate(result)


def test_atomic_result_validator_rejects_undeclared_command_id():
    from boardroom_os.execution.atomic_agent import AtomicAgentResultValidator

    result = _result(tool_attempts=[{"tool_attempt_id": "tool.2", "action": "run_command", "command_id": "rm-all"}])
    validator = AtomicAgentResultValidator(allowed_write_set=("backend",), declared_command_ids=("test-backend",))

    with pytest.raises(ValueError, match="command_id is not declared"):
        validator.validate(result)
```

Create `tests/execution/test_atomic_agent_result_projection.py` with hash test skeleton:

```python
from __future__ import annotations

import hashlib
import json

from atomic_agent.models import AgentRunResult, AgentRunStatus

from boardroom_os.execution.atomic_agent import AtomicAgentResultValidator


def _write_event_stream(path):
    events = [
        {"event_id": "evt-1", "run_id": "run.atomic.1", "sequence": 1, "type": "run.started", "payload": {}, "previous_event_hash": None, "event_hash": "hash-1"},
        {"event_id": "evt-2", "run_id": "run.atomic.1", "sequence": 2, "type": "workspace.mutation.recorded", "payload": {"path": "backend/app.py"}, "previous_event_hash": "hash-1", "event_hash": "hash-2"},
        {"event_id": "evt-3", "run_id": "run.atomic.1", "sequence": 3, "type": "run.completed", "payload": {}, "previous_event_hash": "hash-2", "event_hash": "hash-3"},
    ]
    content = "".join(json.dumps(event, sort_keys=True, separators=(",", ":")) + "\n" for event in events).encode("utf-8")
    path.write_bytes(content)
    return "sha256:" + hashlib.sha256(content).hexdigest()


def test_atomic_result_validator_recomputes_event_stream_hash(tmp_path):
    event_stream = tmp_path / "events.jsonl"
    events_hash = _write_event_stream(event_stream)
    result = AgentRunResult(
        run_id="run.atomic.1",
        status=AgentRunStatus.COMPLETED,
        event_stream_ref=str(event_stream),
        events_hash=events_hash,
        tool_attempts=[{"tool_attempt_id": "tool.1", "action": "write_file"}],
        workspace_mutations=[{"path": "backend/app.py", "tool_attempt_id": "tool.1", "sha256": "0" * 64}],
        artifacts=[{"artifact_ref": "artifact://run.atomic.1/result.json", "sha256": "1" * 64}],
        summary="Updated backend/app.py",
    )

    validator = AtomicAgentResultValidator(allowed_write_set=("backend",), declared_command_ids=("test-backend",))

    validated = validator.validate(result)

    assert validated.events_hash == events_hash
    assert len(validated.events) == 3


def test_atomic_result_validator_rejects_event_stream_hash_mismatch(tmp_path):
    event_stream = tmp_path / "events.jsonl"
    _write_event_stream(event_stream)
    result = AgentRunResult(
        run_id="run.atomic.1",
        status=AgentRunStatus.COMPLETED,
        event_stream_ref=str(event_stream),
        events_hash="sha256:" + "f" * 64,
        tool_attempts=[{"tool_attempt_id": "tool.1", "action": "write_file"}],
        workspace_mutations=[{"path": "backend/app.py", "tool_attempt_id": "tool.1", "sha256": "0" * 64}],
        artifacts=[{"artifact_ref": "artifact://run.atomic.1/result.json", "sha256": "1" * 64}],
        summary="Updated backend/app.py",
    )
    validator = AtomicAgentResultValidator(allowed_write_set=("backend",), declared_command_ids=("test-backend",))

    try:
        validator.validate(result)
    except ValueError as exc:
        assert "events_hash does not match event stream content" in str(exc)
    else:
        raise AssertionError("expected event stream hash mismatch")
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
PYTHONPATH=src:. python -m pytest tests/negative/test_atomic_agent_integration_fail_closed.py tests/execution/test_atomic_agent_result_projection.py -q --tb=short --basetemp .pytest-tmp-v2090g-validator-red
```

Expected: FAIL with missing `AtomicAgentResultValidator`.

- [ ] **Step 3: Implement validator**

Append to `src/boardroom_os/execution/atomic_agent.py`:

```python
import hashlib
import json
from dataclasses import field


_GOVERNANCE_FORBIDDEN_KEYS = {
    "ticket_completed",
    "closeout_committed",
    "governance_status",
    "evidence_verified",
    "source_inventory_accepted",
}


@dataclass(frozen=True)
class AtomicAgentValidatedResult:
    result: Any
    events: tuple[dict[str, Any], ...]
    events_hash: str


class AtomicAgentResultValidator:
    def __init__(
        self,
        *,
        allowed_write_set: tuple[str, ...],
        declared_command_ids: tuple[str, ...],
        require_workspace_mutation: bool = True,
    ) -> None:
        self.allowed_write_set = allowed_write_set
        self.declared_command_ids = set(declared_command_ids)
        self.require_workspace_mutation = require_workspace_mutation

    def validate(self, result: Any) -> AtomicAgentValidatedResult:
        if getattr(result, "status", None).value != "completed":
            raise ValueError("atomic-agent result must be completed")
        self._reject_governance_fields(result)
        if not getattr(result, "event_stream_ref", None):
            raise ValueError("event_stream_ref is required")
        if not getattr(result, "events_hash", None):
            raise ValueError("events_hash is required")
        if not getattr(result, "tool_attempts", None):
            raise ValueError("tool_attempts are required")
        if not getattr(result, "artifacts", None):
            raise ValueError("artifacts are required")
        if self.require_workspace_mutation and not getattr(result, "workspace_mutations", None):
            raise ValueError("workspace mutation is required")
        self._validate_workspace_mutations(result.workspace_mutations)
        self._validate_tool_attempt_commands(result.tool_attempts)
        events = self._read_events(Path(result.event_stream_ref), result.events_hash)
        return AtomicAgentValidatedResult(result=result, events=events, events_hash=result.events_hash)

    def _reject_governance_fields(self, value: Any) -> None:
        if isinstance(value, dict):
            forbidden = _GOVERNANCE_FORBIDDEN_KEYS.intersection(value)
            if forbidden:
                raise ValueError("atomic-agent result must not contain governance field")
            for nested in value.values():
                self._reject_governance_fields(nested)
            return
        if isinstance(value, (list, tuple)):
            for nested in value:
                self._reject_governance_fields(nested)
            return
        if hasattr(value, "model_dump"):
            self._reject_governance_fields(value.model_dump(mode="json"))

    def _validate_workspace_mutations(self, mutations: list[dict[str, Any]]) -> None:
        for mutation in mutations:
            path = mutation.get("path")
            if not isinstance(path, str) or not path:
                raise ValueError("workspace mutation path is required")
            parsed = PurePosixPath(path)
            if parsed.is_absolute() or ".." in parsed.parts:
                raise ValueError("workspace mutation path is outside allowed_write_set")
            if not any(path == prefix or path.startswith(prefix.rstrip("/") + "/") for prefix in self.allowed_write_set):
                raise ValueError("workspace mutation path is outside allowed_write_set")
            if not mutation.get("sha256"):
                raise ValueError("workspace mutation sha256 is required")

    def _validate_tool_attempt_commands(self, tool_attempts: list[dict[str, Any]]) -> None:
        for attempt in tool_attempts:
            if attempt.get("action") != "run_command":
                continue
            command_id = attempt.get("command_id")
            if command_id not in self.declared_command_ids:
                raise ValueError("command_id is not declared")

    def _read_events(self, event_stream_path: Path, expected_hash: str) -> tuple[dict[str, Any], ...]:
        if not event_stream_path.exists() or not event_stream_path.is_file():
            raise ValueError("event stream file is required")
        content = event_stream_path.read_bytes()
        actual_hash = "sha256:" + hashlib.sha256(content).hexdigest()
        if actual_hash != expected_hash:
            raise ValueError("events_hash does not match event stream content")
        events: list[dict[str, Any]] = []
        for line in content.decode("utf-8").splitlines():
            if line.strip():
                events.append(json.loads(line))
        if not events:
            raise ValueError("event stream must not be empty")
        if events[0].get("type") != "run.started":
            raise ValueError("event stream must start with run.started")
        if events[-1].get("type") not in {"run.completed", "run.failed"}:
            raise ValueError("event stream must end with terminal run event")
        return tuple(events)
```

- [ ] **Step 4: Run validator tests**

Run:

```bash
PYTHONPATH=src:. python -m pytest tests/negative/test_atomic_agent_integration_fail_closed.py tests/execution/test_atomic_agent_result_projection.py -q --tb=short --basetemp .pytest-tmp-v2090g-validator-green
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/boardroom_os/execution/atomic_agent.py tests/negative/test_atomic_agent_integration_fail_closed.py tests/execution/test_atomic_agent_result_projection.py
git commit -m "feat: 校验原子智能体结果"
```

---

### Task 4: Project completed atomic-agent result into Boardroom WorkProduct drafts

**Files:**
- Modify: `src/boardroom_os/execution/atomic_agent.py`
- Extend: `tests/execution/test_atomic_agent_result_projection.py`

- [ ] **Step 1: Write failing projector test**

Append to `tests/execution/test_atomic_agent_result_projection.py`:

```python
from tests.execution.test_atomic_agent_invocation_compiler import _execution_package
from boardroom_os.providers.attempt import ProviderAttempt


def test_atomic_result_projector_builds_work_product_submission(tmp_path):
    from boardroom_os.execution.atomic_agent import AtomicResultProjector

    event_stream = tmp_path / "events.jsonl"
    events_hash = _write_event_stream(event_stream)
    result = AgentRunResult(
        run_id="run.atomic.1",
        status=AgentRunStatus.COMPLETED,
        event_stream_ref=str(event_stream),
        events_hash=events_hash,
        tool_attempts=[{"tool_attempt_id": "tool.1", "action": "write_file"}],
        workspace_mutations=[{"path": "backend/app.py", "tool_attempt_id": "tool.1", "sha256": "0" * 64}],
        artifacts=[{"artifact_ref": "artifact://run.atomic.1/backend/app.py", "sha256": "0" * 64}],
        summary="Updated backend/app.py",
    )
    execution_package = _execution_package()
    provider_attempt = ProviderAttempt.model_validate(
        {
            "provider_attempt_id": "provider-attempt.atomic.run.atomic.1",
            "provider": execution_package.model_execution_profile.provider,
            "model": execution_package.model_execution_profile.model,
            "reasoning_effort": execution_package.model_execution_profile.reasoning_effort,
            "input_package_ref": execution_package.execution_package_id.value,
            "seat_ref": execution_package.seat_ref.value,
            "role_prompt_hook_ref": execution_package.role_prompt_hook.hook_ref.value,
            "role_prompt_hook_version": execution_package.role_prompt_hook.hook_version,
            "role_prompt_hook_sha256": execution_package.role_prompt_hook.content_sha256.value,
            "status": "succeeded",
            "outcome": "primary_provider_output",
            "started_at": "2026-06-09T00:00:00Z",
            "finished_at": "2026-06-09T00:00:01Z",
            "raw_output_ref": "artifact://run.atomic.1/provider/raw.json",
            "parsed_output_ref": "artifact://run.atomic.1/provider/parsed.json",
        }
    )
    validator = AtomicAgentResultValidator(allowed_write_set=("backend",), declared_command_ids=("test-backend",))
    validated = validator.validate(result)

    projection = AtomicResultProjector().project(
        execution_package=execution_package,
        provider_attempt=provider_attempt,
        validated_result=validated,
    )

    assert projection.atomic_run_id == "run.atomic.1"
    assert projection.work_product_submission.work_product.execution_package_ref.value == execution_package.execution_package_id.value
    assert projection.work_product_submission.work_product.producer_attempt_ref == provider_attempt.provider_attempt_id
    assert "artifact://run.atomic.1/backend/app.py" in [ref.value for ref in projection.work_product_submission.work_product.artifact_refs]
    assert projection.source_lineage_inputs[0]["path"] == "backend/app.py"
    assert projection.source_lineage_inputs[0]["producer_ticket_ref"] == execution_package.ticket_ref.value
    assert projection.source_lineage_inputs[0]["producer_attempt_ref"] == provider_attempt.provider_attempt_id.value
```

- [ ] **Step 2: Run projector test to verify it fails**

Run:

```bash
PYTHONPATH=src:. python -m pytest tests/execution/test_atomic_agent_result_projection.py::test_atomic_result_projector_builds_work_product_submission -q --tb=short --basetemp .pytest-tmp-v2090g-projector-red
```

Expected: FAIL with missing `AtomicResultProjector`.

- [ ] **Step 3: Implement projector**

Append to `src/boardroom_os/execution/atomic_agent.py`:

```python
from boardroom_os.execution.work_product import (
    WorkProduct,
    WorkProductArtifactRef,
    WorkProductClaimDraft,
    WorkProductClaimDraftRef,
    WorkProductRef,
    WorkProductSubmission,
)
from boardroom_os.providers.attempt import ProviderAttempt


@dataclass(frozen=True)
class AtomicResultProjection:
    atomic_run_id: str
    work_product_submission: WorkProductSubmission
    source_lineage_inputs: tuple[dict[str, Any], ...]
    event_stream_ref: str
    events_hash: str


class AtomicResultProjector:
    def project(
        self,
        *,
        execution_package: ExecutionPackage,
        provider_attempt: ProviderAttempt,
        validated_result: AtomicAgentValidatedResult,
    ) -> AtomicResultProjection:
        result = validated_result.result
        artifact_refs = tuple(
            WorkProductArtifactRef(value=artifact["artifact_ref"])
            for artifact in result.artifacts
            if isinstance(artifact, dict) and artifact.get("artifact_ref")
        )
        if not artifact_refs:
            raise ValueError("atomic-agent artifacts are required for work product")
        claim_draft_ref = WorkProductClaimDraftRef(
            value=f"claim-draft.atomic.{provider_attempt.provider_attempt_id.value}"
        )
        execution_package_ref = execution_package.execution_package_id.value
        claim_draft = WorkProductClaimDraft(
            claim_draft_ref=claim_draft_ref,
            producer_attempt_ref=provider_attempt.provider_attempt_id,
            execution_package_ref=execution_package_ref,
            ticket_ref=execution_package.ticket_ref,
            acceptance_refs=execution_package.acceptance_refs,
            source_surface_refs=execution_package.source_surface_refs,
            artifact_refs=artifact_refs,
            summary=result.summary,
        )
        work_product = WorkProduct(
            work_product_id=WorkProductRef(value=f"work-product.atomic.{provider_attempt.provider_attempt_id.value}"),
            execution_package_ref=execution_package_ref,
            ticket_ref=execution_package.ticket_ref,
            producer_attempt_ref=provider_attempt.provider_attempt_id,
            artifact_refs=artifact_refs,
            claim_refs=(claim_draft_ref,),
            summary=result.summary,
        )
        source_lineage_inputs = tuple(
            {
                "path": mutation["path"],
                "sha256": mutation["sha256"],
                "producer_ticket_ref": execution_package.ticket_ref.value,
                "producer_attempt_ref": provider_attempt.provider_attempt_id.value,
                "atomic_run_id": result.run_id,
                "tool_attempt_id": mutation.get("tool_attempt_id"),
                "acceptance_refs": [ref.value for ref in execution_package.acceptance_refs],
                "source_surface_refs": [ref.value for ref in execution_package.source_surface_refs],
                "evidence_refs": [ref.value for ref in artifact_refs],
            }
            for mutation in result.workspace_mutations
        )
        return AtomicResultProjection(
            atomic_run_id=result.run_id,
            work_product_submission=WorkProductSubmission(work_product=work_product, claim_drafts=(claim_draft,)),
            source_lineage_inputs=source_lineage_inputs,
            event_stream_ref=result.event_stream_ref,
            events_hash=result.events_hash,
        )
```

- [ ] **Step 4: Run projection tests**

Run:

```bash
PYTHONPATH=src:. python -m pytest tests/execution/test_atomic_agent_result_projection.py -q --tb=short --basetemp .pytest-tmp-v2090g-projector-green
```

Expected: PASS.

- [ ] **Step 5: Run work product regression**

Run:

```bash
PYTHONPATH=src:. python -m pytest tests/execution/test_work_product_submission.py tests/execution/test_atomic_agent_result_projection.py -q --tb=short --basetemp .pytest-tmp-v2090g-work-product-regression
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/boardroom_os/execution/atomic_agent.py tests/execution/test_atomic_agent_result_projection.py
git commit -m "feat: 投影原子智能体工作产物"
```

---

### Task 5: Add a deterministic fake atomic-agent port integration test

**Files:**
- Modify: `tests/execution/test_atomic_agent_result_projection.py`
- Modify: `src/boardroom_os/execution/atomic_agent.py`

- [ ] **Step 1: Write failing end-to-end adapter test**

Append to `tests/execution/test_atomic_agent_result_projection.py`:

```python

def test_atomic_package_adapter_invokes_runtime_port_and_projector(tmp_path):
    from boardroom_os.execution.atomic_agent import (
        AtomicAgentDependencyInfo,
        AtomicAgentPackageAdapter,
        AtomicInvocationCompiler,
        AtomicResultProjector,
    )

    event_stream = tmp_path / "events.jsonl"
    events_hash = _write_event_stream(event_stream)

    class FakeRuntimePort:
        def __init__(self):
            self.invocations = []

        def invoke(self, invocation):
            self.invocations.append(invocation)
            return AgentRunResult(
                run_id="run.atomic.fake",
                status=AgentRunStatus.COMPLETED,
                event_stream_ref=str(event_stream),
                events_hash=events_hash,
                tool_attempts=[{"tool_attempt_id": "tool.1", "action": "write_file"}],
                workspace_mutations=[{"path": "backend/app.py", "tool_attempt_id": "tool.1", "sha256": "0" * 64}],
                artifacts=[{"artifact_ref": "artifact://run.atomic.fake/backend/app.py", "sha256": "0" * 64}],
                summary="Updated backend/app.py",
            )

    execution_package = _execution_package()
    runtime_port = FakeRuntimePort()
    adapter = AtomicAgentPackageAdapter(
        runtime_port=runtime_port,
        dependency_info=AtomicAgentDependencyInfo(
            package_name="atomic-agent",
            package_version="0.0.0",
            source_path=str(tmp_path),
            runtime_port_contract_ref="atomic-agent.docs.agent-runtime-port.v1",
        ),
    )
    invocation = AtomicInvocationCompiler(workspace_root=tmp_path).compile(execution_package)

    result = adapter.invoke(invocation)

    assert runtime_port.invocations == [invocation]
    assert result.run_id == "run.atomic.fake"
    assert adapter.dependency_info().package_name == "atomic-agent"
```

- [ ] **Step 2: Run test**

Run:

```bash
PYTHONPATH=src:. python -m pytest tests/execution/test_atomic_agent_result_projection.py::test_atomic_package_adapter_invokes_runtime_port_and_projector -q --tb=short --basetemp .pytest-tmp-v2090g-fake-port
```

Expected: PASS. If it fails because adapter type-check is too brittle, update `AtomicAgentPackageAdapter.invoke` to accept imported `atomic_agent.models.AgentRunResult` as well as same-shape instances by checking required attributes and class name.

- [ ] **Step 3: Run all atomic-agent integration tests**

Run:

```bash
PYTHONPATH=src:. python -m pytest tests/execution/test_atomic_agent_invocation_compiler.py tests/execution/test_atomic_agent_result_projection.py tests/negative/test_atomic_agent_integration_fail_closed.py -q --tb=short --basetemp .pytest-tmp-v2090g-all-atomic
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add src/boardroom_os/execution/atomic_agent.py tests/execution/test_atomic_agent_result_projection.py
git commit -m "test: 增加原子智能体端口集成"
```

---

### Task 6: Export public names and add proving fixture hook without golden sample rebuild

**Files:**
- Modify: `src/boardroom_os/execution/__init__.py`
- Modify: `tests/proving/fixtures/tiny_package_assembly.py`
- Create or modify: `tests/proving/test_tiny_atomic_agent_bridge.py`

- [ ] **Step 1: Write failing proving-level bridge test**

Create `tests/proving/test_tiny_atomic_agent_bridge.py`:

```python
from __future__ import annotations

from boardroom_os.execution.atomic_agent import AtomicInvocationCompiler
from tests.proving.fixtures.tiny_ticket_graph import build_tiny_ticket_graph_fixture


def test_tiny_worker_execution_package_can_compile_to_atomic_invocation(tmp_path):
    fixture = build_tiny_ticket_graph_fixture()
    backend_package = fixture.execution_packages["ticket-tiny-backend-api"]

    invocation = AtomicInvocationCompiler(workspace_root=tmp_path).compile(backend_package)

    assert invocation.metadata["ticket_ref"] == "ticket-tiny-backend-api"
    assert "run_command" in invocation.tools
    assert invocation.output_requirements["require_event_stream"] is True
    assert invocation.output_requirements["require_workspace_mutations"] is True
    assert invocation.permission_policy["commands"]
```

- [ ] **Step 2: Run proving bridge test to verify failure or pass**

Run:

```bash
PYTHONPATH=src:. python -m pytest tests/proving/test_tiny_atomic_agent_bridge.py -q --tb=short --basetemp .pytest-tmp-v2090g-proving-bridge
```

Expected: PASS if fixture exposes `execution_packages`; if fixture shape differs, update the test to use the existing fixture builder that returns compiled tiny execution packages. Do not change production code solely to fit a guessed fixture name.

- [ ] **Step 3: Export atomic adapter public names**

Modify `src/boardroom_os/execution/__init__.py` to include:

```python
from boardroom_os.execution.atomic_agent import (
    AtomicAgentAdapterError,
    AtomicAgentDependencyInfo,
    AtomicAgentPackageAdapter,
    AtomicAgentPort,
    AtomicAgentResultValidator,
    AtomicInvocationCompiler,
    AtomicResultProjection,
    AtomicResultProjector,
)

__all__ = [
    "AtomicAgentAdapterError",
    "AtomicAgentDependencyInfo",
    "AtomicAgentPackageAdapter",
    "AtomicAgentPort",
    "AtomicAgentResultValidator",
    "AtomicInvocationCompiler",
    "AtomicResultProjection",
    "AtomicResultProjector",
]
```

If `__init__.py` already exports existing names, merge these names rather than replacing existing exports.

- [ ] **Step 4: Run execution/proving regression**

Run:

```bash
PYTHONPATH=src:. python -m pytest tests/execution/test_atomic_agent_invocation_compiler.py tests/execution/test_atomic_agent_result_projection.py tests/proving/test_tiny_atomic_agent_bridge.py -q --tb=short --basetemp .pytest-tmp-v2090g-proving-regression
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/boardroom_os/execution/__init__.py tests/proving/test_tiny_atomic_agent_bridge.py tests/proving/fixtures/tiny_package_assembly.py
git commit -m "feat: 接入微型原子智能体桥接"
```

---

### Task 7: Update README with sibling checkout import setup

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Add atomic-agent setup section**

Append this section after `目录概览` in `README.md`:

```markdown
## atomic-agent 本地集成

V2-090G 起，Boardroom OS 通过外部 `atomic-agent`（原子智能体）Python package（Python 包）执行 implementation ticket（实施任务）的受控 agent loop（智能体循环）。Boardroom OS 不复制 `atomic-agent` 源码，也不要求 `atomic-agent` 作为 HTTP/gRPC service（服务）运行。

推荐本地目录布局：

```text
~/projects/boardroom-os
~/projects/atomic-agent
```

在 Boardroom OS 的 Python 环境中安装 atomic-agent：

```bash
cd ~/projects/boardroom-os
python -m pip install -e ../atomic-agent
python -c "from atomic_agent import AgentRuntimePort; print('atomic-agent import ok')"
```

不得从本仓库内的探索副本安装 atomic-agent：

```text
.worktrees/atomic-agent/ 仅是历史探索副本，不得用于 V2-090G 实施安装、import 验证或契约检查。
```

职责边界：

- `atomic-agent` 负责 agent loop（智能体循环）、tool dispatch（工具调度）、permission policy（权限策略）、event stream（事件流）和 workspace mutation（工作区变更）。
- Boardroom OS 继续负责 AcceptanceContract（验收合同）、PackageContract（包合同）、reducer（归约器）、EvidenceVerifier（证据验证器）、Checker（检查者）和 CloseoutGate（收尾门禁）。
- `AgentRunResult.status == completed`（原子智能体运行完成）不等于 `TICKET_COMPLETED`（任务完成）或 `CloseoutPackage.passed`（收尾包通过）。缺 event stream、workspace mutation、command evidence 或 source inventory lineage 时必须 fail closed（失败关闭）。
```

- [ ] **Step 2: Run markdown grep checks**

Run:

```bash
python - <<'PY'
from pathlib import Path
text = Path('README.md').read_text(encoding='utf-8')
required = [
    'python -m pip install -e ../atomic-agent',
    'AgentRunResult.status == completed',
    '不复制 `atomic-agent` 源码',
]
missing = [item for item in required if item not in text]
if missing:
    raise SystemExit(f'missing README text: {missing}')
print('README atomic-agent section ok')
PY
```

Expected: `README atomic-agent section ok`.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: 说明原子智能体本地安装"
```

---

### Task 8: Update backlog, acceptance criteria, INDEX, and decisions

**Files:**
- Modify: `doc/04-implementation/backlog.md`
- Modify: `doc/04-implementation/acceptance-criteria.md`
- Modify: `doc/04-implementation/INDEX.md`
- Modify: `doc/05-project-log/decisions.md`

- [ ] **Step 1: Update backlog**

Apply these exact semantic edits to `doc/04-implementation/backlog.md`:

- Top TL;DR current unfinished package remains `V2-090F` if implementation is not yet started, but V2-090F blocker text must say it is blocked on V2-090G.
- Progress table Phase 9 changes from `5 / 6` to `5 / 7`.
- Total changes from `64 / 65` to `64 / 66`.
- Add a new work package after V2-090F:

```markdown
### V2-090G: Atomic-agent package/import integration

- 状态：TODO
- 目标：通过同级目录安装并 import 外部 `atomic-agent` Python package（Python 包），替代 Boardroom OS 中单次 provider JSON source delivery（模型供应商 JSON 源码交付）式 ticket 执行路径；Boardroom OS 只通过 `AgentRuntimePort`（智能体运行端口）调用 atomic-agent，并把 `AgentRunResult`（智能体运行结果）投影回 Boardroom evidence chain（证据链）。
- 输入文档：`doc/04-implementation/v2-090g-atomic-agent-package-integration-spec.md`、`doc/04-implementation/v2-090g-atomic-agent-package-integration-implementation-plan.md`、`../atomic-agent/docs/03-contracts/agent-runtime-port.md`、`../atomic-agent/docs/03-contracts/agent-action-protocol.md`、`../atomic-agent/docs/03-contracts/event-stream-protocol.md`、`../atomic-agent/docs/00-overview/boardroom-os-integration-summary.md`、`doc/03-architecture/execution-and-runtime-boundary.md`、`doc/03-architecture/contract-and-evidence-model.md`。
- 依赖：V2-090E、V2-090F 阻塞复盘、外部 `atomic-agent` 可通过 `python -m pip install -e ../atomic-agent` 安装。
- 输出文件：`src/boardroom_os/execution/atomic_agent.py`、`tests/execution/test_atomic_agent_invocation_compiler.py`、`tests/execution/test_atomic_agent_result_projection.py`、`tests/negative/test_atomic_agent_integration_fail_closed.py`、`tests/proving/test_tiny_atomic_agent_bridge.py`、`README.md`、必要时 `src/boardroom_os/execution/__init__.py`。
- 必须先写的 negative tests：缺 `atomic-agent` package 不得 fallback；`AgentRunResult.status != completed` 不得生成 successful WorkProduct（成功工作产物）；缺 event stream/hash/tool attempts/workspace mutations/artifacts 必须失败；event stream hash mismatch（事件流哈希不一致）必须失败；atomic-agent 返回 `ticket_completed` / `closeout_committed` / `evidence_verified` 等治理字段必须失败；workspace mutation path（工作区变更路径）超出 `allowed_write_set` 必须失败；command_id 未在 ExecutionPackage.commands 声明必须失败。
- 必须证明的 happy path：ExecutionPackage 可确定性编译为 atomic-agent `AgentInvocation`；fake `AgentRuntimePort` 返回 completed `AgentRunResult` 后，Boardroom 可验证 event stream hash，投影 workspace mutations/artifacts 为 WorkProductSubmission（工作产物提交）和 SourceInventory lineage input（源码清单来源链输入）；README 说明同级目录安装和 import 验证命令。
- 验收口径：atomic-agent 作为外部 package/import 执行边界接入，Boardroom 不复制源码、不调用不稳定示例 CLI、不服务化；atomic-agent completed 只作为 execution evidence（执行证据），后续仍由 EvidenceVerifier / Checker / Reducer / CloseoutGate 决定完成和收尾。V2-090G DONE 后不得自动恢复 V2-090F；必须先由人工评审 V2-090G 证据，再明确确认是否将 V2-090F 从 BLOCKED 恢复为 TODO/IN_PROGRESS 重新重建 golden sample。
```

- [ ] **Step 2: Update acceptance criteria**

In `doc/04-implementation/acceptance-criteria.md`, update Phase 9 checklist:

```markdown
- [ ] AC-V2-EXECUTION-001 / AC-V2-EXECUTION-002 / AC-V2-EVIDENCE-002（atomic-agent 执行边界与来源链）— 由 V2-090G 证明：ExecutionPackage（执行包）可编译为 atomic-agent AgentInvocation（智能体调用），AgentRunResult（智能体运行结果）的 event stream / tool attempts / workspace mutations / artifacts（事件流 / 工具尝试 / 工作区变更 / 产物）可投影为 Boardroom evidence chain（证据链）输入；缺包、缺事件流、缺工作区变更、越权路径、越权命令或治理字段注入均 fail closed（失败关闭）
```

Also update entry prerequisites from `V2-090A ~ V2-090F 全部 DONE` to `V2-090A ~ V2-090G 全部 DONE，且 V2-090F 在 V2-090G 后重新通过`.

- [ ] **Step 3: Update INDEX**

Add rows to `doc/04-implementation/INDEX.md`:

```markdown
| `v2-090g-atomic-agent-package-integration-spec.md` | V2-090G atomic-agent（原子智能体）package/import 集成规范 |
| `v2-090g-atomic-agent-package-integration-implementation-plan.md` | V2-090G atomic-agent（原子智能体）package/import 集成实施计划 |
```

- [ ] **Step 4: Update decisions**

Append to `doc/05-project-log/decisions.md`:

```markdown
## DEC-0022: atomic-agent 以外部 Python package 接入 Boardroom OS

- 状态：Accepted
- 日期：2026-06-09

### 决策

V2-090G 采用外部 Python package import（Python 包导入）方式接入 `atomic-agent`（原子智能体）。Boardroom OS 不复制 atomic-agent 源码，不把 atomic-agent 封装为 HTTP/gRPC service（服务），也不把 atomic-agent examples CLI（示例命令行）当作稳定集成协议。

Boardroom OS 新增 `AtomicAgentPort`（原子智能体端口）/ `AtomicAgentPackageAdapter`（原子智能体包适配器）防腐层，只调用 atomic-agent 公开 `AgentRuntimePort.invoke(AgentInvocation) -> AgentRunResult`（智能体运行端口）边界。开发安装采用同级目录 checkout（检出）后执行 `python -m pip install -e ../atomic-agent`；运行和审计必须记录 atomic-agent package version（包版本）、source path（源码路径）或等价 provenance（来源）。

### 理由

V2-090F 证明 ProviderAttempt（模型调用尝试记录）不是自主 agent work（智能体工作）。atomic-agent 已经在独立项目中提供受控 agent loop（智能体循环）、tool dispatch（工具调度）、permission policy（权限策略）、event stream（事件流）和 workspace mutation（工作区变更）能力；直接复用其公开端口比在 Boardroom OS 内复制或重写执行循环更符合 no duplicate implementations（禁止重复实现）和 contract-first/evidence-first（合同优先/证据优先）原则。

### 影响

- V2-090G 成为 V2-090F 解阻前置。
- Boardroom OS 的 README 必须说明 atomic-agent 同级目录安装和 import 验证方式。
- `AgentRunResult.status == completed`（智能体运行完成）不得直接映射为 `TICKET_COMPLETED`（任务完成）或 `CloseoutPackage.passed`（收尾通过）。
- 缺 atomic-agent package、缺 event stream、缺 workspace mutation、越权 command/path 或返回治理字段时必须 fail closed（失败关闭）。
```

- [ ] **Step 5: Commit docs state updates**

```bash
git add doc/04-implementation/backlog.md doc/04-implementation/acceptance-criteria.md doc/04-implementation/INDEX.md doc/05-project-log/decisions.md
git commit -m "docs: 登记原子智能体集成工作包"
```

---

### Task 9: Verification and completion log

**Files:**
- Modify: `doc/05-project-log/2026-06.md`
- Possibly modify: `doc/04-implementation/backlog.md`
- Possibly modify: `doc/04-implementation/acceptance-criteria.md`

- [ ] **Step 1: Run targeted V2-090G verification**

Run:

```bash
PYTHONPATH=src:. python -m pytest tests/execution/test_atomic_agent_invocation_compiler.py tests/execution/test_atomic_agent_result_projection.py tests/negative/test_atomic_agent_integration_fail_closed.py tests/proving/test_tiny_atomic_agent_bridge.py -q --tb=short --basetemp .pytest-tmp-v2090g-targeted-final
```

Expected: PASS.

- [ ] **Step 2: Run execution/evidence regression**

Run:

```bash
PYTHONPATH=src:. python -m pytest tests/execution/test_execution_package_schema.py tests/execution/test_execution_package_compiler.py tests/execution/test_work_product_submission.py tests/evidence/test_evidence_claim.py tests/evidence/test_evidence_verifier.py tests/reducers/test_completion_gate_with_evidence.py -q --tb=short --basetemp .pytest-tmp-v2090g-regression-final
```

Expected: PASS.

- [ ] **Step 3: Run Phase 9 relevant proving regression without real provider long path**

Run:

```bash
PYTHONPATH=src:. python -m pytest tests/proving/test_tiny_contracts.py tests/proving/test_tiny_ticket_graph.py tests/proving/test_tiny_live_blackbox_integration.py tests/proving/test_workspace_evidence_export.py tests/proving/test_tiny_atomic_agent_bridge.py -q --tb=short --basetemp .pytest-tmp-v2090g-phase9-final
```

Expected: PASS.

- [ ] **Step 4: Run docs/readme checks**

Run:

```bash
python - <<'PY'
from pathlib import Path
checks = {
    'README.md': ['python -m pip install -e ../atomic-agent', 'AgentRunResult.status == completed'],
    'doc/04-implementation/backlog.md': ['### V2-090G: Atomic-agent package/import integration', 'tests/negative/test_atomic_agent_integration_fail_closed.py'],
    'doc/04-implementation/acceptance-criteria.md': ['由 V2-090G 证明', 'atomic-agent 执行边界'],
    'doc/04-implementation/INDEX.md': ['v2-090g-atomic-agent-package-integration-spec.md', 'v2-090g-atomic-agent-package-integration-implementation-plan.md'],
    'doc/05-project-log/decisions.md': ['DEC-0022', 'AgentRuntimePort.invoke'],
}
for path, required in checks.items():
    text = Path(path).read_text(encoding='utf-8')
    missing = [item for item in required if item not in text]
    if missing:
        raise SystemExit(f'{path} missing {missing}')
print('V2-090G docs checks ok')
PY
```

Expected: `V2-090G docs checks ok`.

- [ ] **Step 5: Run whitespace check**

Run:

```bash
git diff --check
```

Expected: no output and exit code 0.

- [ ] **Step 6: Update completion log only after tests pass**

Append to `doc/05-project-log/2026-06.md`:

```markdown
## 2026-06-09 — V2-090G Atomic-agent package/import integration

- 工作包：V2-090G（Atomic-agent package/import integration，原子智能体包导入集成）
- 关键产出：`src/boardroom_os/execution/atomic_agent.py`、`tests/execution/test_atomic_agent_invocation_compiler.py`、`tests/execution/test_atomic_agent_result_projection.py`、`tests/negative/test_atomic_agent_integration_fail_closed.py`、`tests/proving/test_tiny_atomic_agent_bridge.py`、`README.md`、`doc/04-implementation/v2-090g-atomic-agent-package-integration-spec.md`、`doc/04-implementation/v2-090g-atomic-agent-package-integration-implementation-plan.md`。
- 关键实现：Boardroom OS 通过 `AtomicAgentPort` / `AtomicAgentPackageAdapter`（原子智能体端口 / 包适配器）调用外部 atomic-agent 的 `AgentRuntimePort.invoke(AgentInvocation)`（智能体运行端口）；`AtomicInvocationCompiler`（原子调用编译器）把 `ExecutionPackage`（执行包）映射为 `AgentInvocation`（智能体调用）；`AtomicAgentResultValidator`（原子结果校验器）重算 event stream hash（事件流哈希）并拒绝缺包、缺事件流、缺工作区变更、越权路径、越权命令和治理字段注入；`AtomicResultProjector`（原子结果投影器）把 completed `AgentRunResult`（智能体运行结果）投影为 Boardroom WorkProductSubmission（工作产物提交）和 SourceInventory lineage input（源码清单来源链输入）。
- Negative tests：覆盖 missing package fallback（缺包降级）、非 AgentRunResult 返回、failed/interrupted result、缺 workspace mutation、治理字段注入、allowed_write_set 越界、未声明 command_id、event stream hash mismatch（事件流哈希不一致）。
- Happy path：fake `AgentRuntimePort` 返回 completed `AgentRunResult` 后，Boardroom 能验证 event stream、生成 work product draft（工作产物草稿）和 source lineage input（源码来源链输入）；tiny backend worker execution package（微型后端实施执行包）可编译为 atomic-agent invocation（原子智能体调用）。
- 验证：记录本任务 Step 1~5 的实际命令和 passed 结果。
- 边界说明：V2-090G 不重建 golden sample（黄金样例），只解除 V2-090F 的 agent execution boundary（智能体执行边界）阻塞；atomic-agent completed 不等于 Boardroom ticket completed 或 closeout passed。
```

- [ ] **Step 7: Mark V2-090G done only after completion log**

In `doc/04-implementation/backlog.md`, set V2-090G status to `DONE`, update Phase 9 count to `6 / 7`, and update total to `65 / 66`. Keep V2-090F `BLOCKED` or move it to `TODO` only if the human reviewer explicitly asks to restart it in the same change.

In `doc/04-implementation/acceptance-criteria.md`, check the V2-090G checkbox, but keep V2-090F golden sample checkbox and Phase 9 final prerequisites unchecked.

- [ ] **Step 8: Commit completion state**

```bash
git add doc/05-project-log/2026-06.md doc/04-implementation/backlog.md doc/04-implementation/acceptance-criteria.md
git commit -m "docs: 记录原子智能体集成完成"
```

---

## Self-review Checklist

- [ ] Spec coverage: every requirement in `v2-090g-atomic-agent-package-integration-spec.md` maps to a task above.
- [ ] No source copy: no implementation step copies files from sibling `../atomic-agent/src/atomic_agent` or historical `.worktrees/atomic-agent/src/atomic_agent` into `src/boardroom_os`.
- [ ] No service wrapper: no implementation step starts HTTP/gRPC service for atomic-agent.
- [ ] No examples CLI dependency: tests may read atomic-agent public models but do not call `atomic_agent.examples.*` as production integration.
- [ ] Import failure fails closed: missing atomic-agent package raises explicit adapter error and never falls back to fake provider or JSON source delivery.
- [ ] Governance separation: no task maps `AgentRunResult.completed` to `TICKET_COMPLETED`, `CloseoutPackage.passed`, or `CLOSEOUT_COMMITTED`.
- [ ] Evidence first: result validation requires event stream, events hash, tool attempts, artifacts, and workspace mutation for implementation tickets.
- [ ] README updated: sibling checkout and `python -m pip install -e ../atomic-agent` are documented.
- [ ] V2-090F remains separate: this plan does not rebuild `examples/generated-workspaces/tiny-fullstack/`.
