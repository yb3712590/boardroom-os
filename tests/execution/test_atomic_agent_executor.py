from __future__ import annotations

from pathlib import Path
import sys

from atomic_agent.models import AgentRunResult

from boardroom_os.agents.seat import AgentSeatRef
from boardroom_os.config.boardroom import load_boardroom_settings
from boardroom_os.execution.atomic_executor import AtomicAgentExecutor, AtomicExecutionRequest
from tests.config.test_boardroom_config import _write_config_files
from tests.execution.test_atomic_agent_invocation_compiler import _execution_package
from tests.execution.test_atomic_agent_result_projection import _completed_result, _write_event_stream


class ScriptedRuntimePort:
    def __init__(self, result: AgentRunResult):
        self.result = result
        self.invocations = []

    def invoke(self, invocation):
        self.invocations.append(invocation)
        return self.result


def _settings(tmp_path: Path, monkeypatch):
    paths = _write_config_files(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-secret")
    return load_boardroom_settings(paths, env_values={})


def _execution_package_for_config():
    package = _execution_package()
    return package.model_copy(
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


def _execution_package_for_factory():
    package = _execution_package_for_config()
    command = package.commands[0].model_copy(
        update={"command": (sys.executable, "-c", "print('ok')"), "cwd": "."}
    )
    return package.model_copy(update={"commands": (command,)})


def test_atomic_agent_executor_invokes_runtime_and_projects_result(tmp_path, monkeypatch):
    event_stream = tmp_path / "events.jsonl"
    events_hash = _write_event_stream(event_stream, command_id="cmd.test", include_provider_turn=True)
    result = _completed_result(event_stream, events_hash)
    runtime_port = ScriptedRuntimePort(result)
    executor = AtomicAgentExecutor(runtime_port=runtime_port)
    request = AtomicExecutionRequest(
        execution_package=_execution_package_for_config(),
        settings=_settings(tmp_path, monkeypatch),
        seat_ref="seat.worker.implementation",
        workspace_root=tmp_path,
        event_stream_root=tmp_path,
    )

    execution_result = executor.execute(request)

    assert runtime_port.invocations
    assert execution_result.atomic_run_id == "run.atomic.1"
    assert execution_result.provider_attempt.provider_attempt_id.value.startswith("provider-attempt.atomic.")
    assert execution_result.provider_attempt.status == "succeeded"
    assert execution_result.projection.work_product_submission.work_product.ticket_ref.value == "ticket.backend"
    assert execution_result.projection.source_lineage_inputs[0]["path"] == "backend/app.py"


def test_atomic_agent_executor_projected_provider_attempt_binds_execution_package(tmp_path, monkeypatch):
    event_stream = tmp_path / "events.jsonl"
    events_hash = _write_event_stream(event_stream, command_id="cmd.test", include_provider_turn=True)
    executor = AtomicAgentExecutor(runtime_port=ScriptedRuntimePort(_completed_result(event_stream, events_hash)))
    package = _execution_package_for_config()

    execution_result = executor.execute(
        AtomicExecutionRequest(
            execution_package=package,
            settings=_settings(tmp_path, monkeypatch),
            seat_ref="seat.worker.implementation",
            workspace_root=tmp_path,
            event_stream_root=tmp_path,
        )
    )

    attempt = execution_result.provider_attempt
    assert attempt.input_package_ref.value == package.execution_package_id.value
    assert attempt.seat_ref == package.seat_ref
    assert attempt.provider == "openai-compatible"
    assert attempt.model == "gpt-5.5"
    assert attempt.reasoning_effort == "high"
    assert attempt.raw_output_ref is not None
    assert attempt.parsed_output_ref is not None


def test_atomic_runtime_factory_builds_port_with_openai_compatible_provider(tmp_path, monkeypatch):
    from boardroom_os.execution.atomic_executor import AtomicAgentRuntimeFactory

    settings = _settings(tmp_path, monkeypatch)
    factory = AtomicAgentRuntimeFactory(settings=settings)

    runtime_port = factory.build_runtime_port(
        execution_package=_execution_package_for_factory(),
        seat_ref="seat.worker.implementation",
        workspace_root=tmp_path,
        run_id="run.atomic.factory.1",
    )

    assert callable(getattr(runtime_port, "invoke", None))
