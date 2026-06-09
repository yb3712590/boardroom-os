from __future__ import annotations

from typing import Any
from types import ModuleType

import pytest


def test_atomic_agent_adapter_fails_closed_when_package_missing(monkeypatch):
    from boardroom_os.execution.atomic_agent import (
        AtomicAgentAdapterError,
        AtomicAgentPackageAdapter,
    )

    def reject_import(name: str) -> Any:
        raise ImportError(f"blocked import: {name}")

    adapter = AtomicAgentPackageAdapter(import_atomic_agent=reject_import)

    with pytest.raises(
        AtomicAgentAdapterError,
        match="atomic-agent package is not importable",
    ):
        adapter.dependency_info()


def test_atomic_agent_adapter_rejects_unauditable_package_version(monkeypatch):
    import boardroom_os.execution.atomic_agent as atomic_agent
    from boardroom_os.execution.atomic_agent import (
        AtomicAgentAdapterError,
        AtomicAgentPackageAdapter,
    )

    monkeypatch.setattr(
        atomic_agent,
        "version",
        lambda package_name: (_ for _ in ()).throw(atomic_agent.PackageNotFoundError(package_name)),
    )

    adapter = AtomicAgentPackageAdapter(
        import_atomic_agent=lambda name: ModuleType(name),
    )

    with pytest.raises(
        AtomicAgentAdapterError,
        match="atomic-agent package version is not auditable",
    ):
        adapter.dependency_info()


def test_atomic_agent_adapter_rejects_unknown_module_version(monkeypatch):
    import boardroom_os.execution.atomic_agent as atomic_agent
    from boardroom_os.execution.atomic_agent import (
        AtomicAgentAdapterError,
        AtomicAgentPackageAdapter,
    )

    monkeypatch.setattr(
        atomic_agent,
        "version",
        lambda package_name: (_ for _ in ()).throw(atomic_agent.PackageNotFoundError(package_name)),
    )
    module = ModuleType("atomic_agent")
    module.__version__ = "unknown"

    adapter = AtomicAgentPackageAdapter(
        import_atomic_agent=lambda name: module,
    )

    with pytest.raises(
        AtomicAgentAdapterError,
        match="atomic-agent package version is not auditable",
    ):
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
            runtime_port_contract_ref="atomic-agent.docs.agent-runtime-port.v1",
        ),
    )

    with pytest.raises(
        AtomicAgentAdapterError,
        match="AgentRuntimePort returned non-AgentRunResult",
    ):
        adapter.invoke({"invocation_id": "invocation.atomic.test"})


def test_atomic_agent_adapter_rejects_fake_agent_run_result_class():
    from boardroom_os.execution.atomic_agent import (
        AtomicAgentAdapterError,
        AtomicAgentDependencyInfo,
        AtomicAgentPackageAdapter,
    )

    FakeAgentRunResult = type("AgentRunResult", (), {})

    class BadRuntimePort:
        def invoke(self, invocation):
            return FakeAgentRunResult()

    adapter = AtomicAgentPackageAdapter(
        runtime_port=BadRuntimePort(),
        dependency_info=AtomicAgentDependencyInfo(
            package_name="atomic-agent",
            package_version="0.0.0",
            source_path="/tmp/atomic-agent",
            runtime_port_contract_ref="atomic-agent.docs.agent-runtime-port.v1",
        ),
    )

    with pytest.raises(
        AtomicAgentAdapterError,
        match="AgentRuntimePort returned non-AgentRunResult",
    ):
        adapter.invoke({"invocation_id": "invocation.atomic.test"})


def _result(**overrides):
    from atomic_agent.models import AgentRunResult, AgentRunStatus

    payload = {
        "run_id": "run.atomic.1",
        "status": AgentRunStatus.COMPLETED,
        "event_stream_ref": "events.jsonl",
        "events_hash": "sha256:abc",
        "tool_attempts": [{"tool_attempt_id": "tool.1", "action": "write_file"}],
        "workspace_mutations": [
            {
                "path": "backend/app.py",
                "tool_attempt_id": "tool.1",
                "sha256": "sha256:" + "0" * 64,
            }
        ],
        "artifacts": [
            {
                "artifact_ref": "artifact://run.atomic.1/result.json",
                "path": "backend/app.py",
                "sha256": "sha256:" + "1" * 64,
            }
        ],
        "summary": "Updated backend/app.py",
    }
    payload.update(overrides)
    return AgentRunResult(**payload)


def test_atomic_result_validator_rejects_failed_status():
    from atomic_agent.models import AgentRunStatus
    from boardroom_os.execution.atomic_agent import AtomicAgentResultValidator

    result = _result(
        status=AgentRunStatus.FAILED,
        failure_kind="provider_failed",
        failure_message="boom",
    )
    validator = AtomicAgentResultValidator(
        allowed_write_set=("backend",),
        declared_command_ids=("test-backend",),
        event_stream_root="/tmp/events",
    )

    with pytest.raises(ValueError, match="atomic-agent result must be completed"):
        validator.validate(result)


def test_atomic_result_validator_rejects_interrupted_status():
    from atomic_agent.models import AgentRunStatus
    from boardroom_os.execution.atomic_agent import AtomicAgentResultValidator

    result = _result(status=AgentRunStatus.INTERRUPTED)
    validator = AtomicAgentResultValidator(
        allowed_write_set=("backend",),
        declared_command_ids=("test-backend",),
        event_stream_root="/tmp/events",
    )

    with pytest.raises(ValueError, match="atomic-agent result must be completed"):
        validator.validate(result)


def test_atomic_result_validator_rejects_missing_workspace_mutation_for_implementation():
    from boardroom_os.execution.atomic_agent import AtomicAgentResultValidator

    result = _result(workspace_mutations=[])
    validator = AtomicAgentResultValidator(
        allowed_write_set=("backend",),
        declared_command_ids=("test-backend",),
        event_stream_root="/tmp/events",
    )

    with pytest.raises(ValueError, match="workspace mutation is required"):
        validator.validate(result)


def test_atomic_result_validator_rejects_governance_fields():
    from boardroom_os.execution.atomic_agent import AtomicAgentResultValidator

    result = _result(
        artifacts=[
            {
                "artifact_ref": "artifact://x",
                "path": "backend/app.py",
                "sha256": "sha256:" + "1" * 64,
                "ticket_completed": True,
            }
        ]
    )
    validator = AtomicAgentResultValidator(
        allowed_write_set=("backend",),
        declared_command_ids=("test-backend",),
        event_stream_root="/tmp/events",
    )

    with pytest.raises(ValueError, match="atomic-agent result must not contain governance field"):
        validator.validate(result)


def test_atomic_result_validator_rejects_write_path_outside_allowed_set():
    from boardroom_os.execution.atomic_agent import AtomicAgentResultValidator

    result = _result(
        workspace_mutations=[
            {
                "path": "frontend/app.js",
                "tool_attempt_id": "tool.1",
                "sha256": "sha256:" + "0" * 64,
            }
        ]
    )
    validator = AtomicAgentResultValidator(
        allowed_write_set=("backend",),
        declared_command_ids=("test-backend",),
        event_stream_root="/tmp/events",
    )

    with pytest.raises(ValueError, match="workspace mutation path is outside allowed_write_set"):
        validator.validate(result)


def test_atomic_result_validator_rejects_write_path_parent_escape():
    from boardroom_os.execution.atomic_agent import AtomicAgentResultValidator

    result = _result(
        workspace_mutations=[
            {
                "path": "../backend/app.py",
                "tool_attempt_id": "tool.1",
                "sha256": "sha256:" + "0" * 64,
            }
        ]
    )
    validator = AtomicAgentResultValidator(
        allowed_write_set=("backend",),
        declared_command_ids=("test-backend",),
        event_stream_root="/tmp/events",
    )

    with pytest.raises(ValueError, match="workspace mutation path is outside allowed_write_set"):
        validator.validate(result)


def test_atomic_result_validator_rejects_undeclared_command_id():
    from boardroom_os.execution.atomic_agent import AtomicAgentResultValidator

    result = _result(
        tool_attempts=[{"tool_attempt_id": "tool.2", "action": "run_command", "command_id": "rm-all"}]
    )
    validator = AtomicAgentResultValidator(
        allowed_write_set=("backend",),
        declared_command_ids=("test-backend",),
        event_stream_root="/tmp/events",
    )

    with pytest.raises(ValueError, match="command_id is not declared"):
        validator.validate(result)


def test_atomic_result_validator_requires_event_stream_root():
    from boardroom_os.execution.atomic_agent import AtomicAgentResultValidator

    with pytest.raises(ValueError, match="event_stream_root is required"):
        AtomicAgentResultValidator(
            allowed_write_set=("backend",),
            declared_command_ids=("test-backend",),
        )


def test_atomic_result_validator_rejects_file_path_directory_expansion():
    from boardroom_os.execution.atomic_agent import AtomicAgentResultValidator

    result = _result(
        workspace_mutations=[
            {
                "path": "backend/app.py/evil.py",
                "tool_attempt_id": "tool.1",
                "sha256": "sha256:" + "0" * 64,
            }
        ]
    )
    validator = AtomicAgentResultValidator(
        allowed_write_set=("backend/app.py",),
        declared_command_ids=("test-backend",),
        event_stream_root="/tmp/events",
    )

    with pytest.raises(ValueError, match="workspace mutation path is outside allowed_write_set"):
        validator.validate(result)
