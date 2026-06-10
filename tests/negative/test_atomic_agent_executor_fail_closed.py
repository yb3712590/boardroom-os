from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from boardroom_os.config.boardroom import load_boardroom_settings
from boardroom_os.execution.atomic_executor import (
    AtomicAgentExecutor,
    AtomicExecutionRequest,
    reject_provider_executor_for_implementation,
)
from boardroom_os.execution.provider_executor import ProviderExecutor
from tests.config.test_boardroom_config import _write_config_files
from tests.execution.test_atomic_agent_executor import ScriptedRuntimePort, _execution_package_for_config
from tests.execution.test_atomic_agent_result_projection import _completed_result, _write_event_stream


def _settings(tmp_path: Path, monkeypatch):
    paths = _write_config_files(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-secret")
    return load_boardroom_settings(paths, env_values={})


def _request(tmp_path, monkeypatch):
    return AtomicExecutionRequest(
        execution_package=_execution_package_for_config(),
        settings=_settings(tmp_path, monkeypatch),
        seat_ref="seat.worker.implementation",
        workspace_root=tmp_path,
        event_stream_root=tmp_path,
    )


def test_provider_executor_is_rejected_for_implementation_ticket():
    with pytest.raises(ValueError, match="ProviderExecutor cannot satisfy implementation ticket evidence"):
        reject_provider_executor_for_implementation(ProviderExecutor(), ticket_category="implementation")


def test_atomic_agent_executor_requires_runtime_port(tmp_path, monkeypatch):
    executor = AtomicAgentExecutor(runtime_port=None)

    with pytest.raises(ValueError, match="AgentRuntimePort is required"):
        executor.execute(_request(tmp_path, monkeypatch))


def test_atomic_agent_executor_rejects_missing_provider_turn_facts(tmp_path, monkeypatch):
    event_stream = tmp_path / "events.jsonl"
    events_hash = _write_event_stream(event_stream, command_id="cmd.test")
    result = _completed_result(event_stream, events_hash)
    executor = AtomicAgentExecutor(runtime_port=ScriptedRuntimePort(result))

    with pytest.raises(ValueError, match="provider turn facts are required"):
        executor.execute(_request(tmp_path, monkeypatch))


def test_atomic_agent_executor_rejects_missing_command_evidence(tmp_path, monkeypatch):
    event_stream = tmp_path / "events.jsonl"
    events_hash = _write_event_stream(event_stream, command_id=None, include_provider_turn=True)
    result = _completed_result(event_stream, events_hash)
    executor = AtomicAgentExecutor(runtime_port=ScriptedRuntimePort(result))

    with pytest.raises(ValueError, match="command evidence is required"):
        executor.execute(_request(tmp_path, monkeypatch))


def test_atomic_agent_executor_rejects_direct_governance_completion(tmp_path, monkeypatch):
    event_stream = tmp_path / "events.jsonl"
    events_hash = _write_event_stream(event_stream, command_id="cmd.test", include_provider_turn=True)
    result = _completed_result(event_stream, events_hash).model_copy(
        update={"summary": "ticket_completed=true"}
    )
    executor = AtomicAgentExecutor(runtime_port=ScriptedRuntimePort(result))

    with pytest.raises(ValueError, match="atomic-agent result must not contain governance field"):
        executor.execute(_request(tmp_path, monkeypatch))


def test_real_proving_path_rejects_fake_provider_marker(tmp_path, monkeypatch):
    event_stream = tmp_path / "events.jsonl"
    events_hash = _write_event_stream(event_stream, command_id="cmd.test", include_provider_turn=True)
    result = _completed_result(event_stream, events_hash)
    executor = AtomicAgentExecutor(runtime_port=ScriptedRuntimePort(result), allow_fake_provider_for_unit_tests=False)

    with pytest.raises(ValueError, match="fake provider transport cannot satisfy V2-090H"):
        executor.execute(_request(tmp_path, monkeypatch), provider_transport_kind="fake")


def test_atomic_agent_executor_rejects_crlf_event_stream(tmp_path, monkeypatch):
    event_stream = tmp_path / "events.jsonl"
    _write_event_stream(event_stream, command_id="cmd.test", include_provider_turn=True)
    event_stream.write_bytes(event_stream.read_bytes().replace(b"\n", b"\r\n"))
    result = _completed_result(
        event_stream,
        "sha256:" + hashlib.sha256(event_stream.read_bytes()).hexdigest(),
    )
    executor = AtomicAgentExecutor(runtime_port=ScriptedRuntimePort(result))

    with pytest.raises(ValueError, match="event stream must use LF line endings"):
        executor.execute(_request(tmp_path, monkeypatch))


def test_atomic_agent_executor_accepts_relative_event_stream_ref_under_root(tmp_path, monkeypatch):
    event_stream = tmp_path / "events.jsonl"
    events_hash = _write_event_stream(event_stream, command_id="cmd.test", include_provider_turn=True)
    result = _completed_result(event_stream, events_hash).model_copy(update={"event_stream_ref": "events.jsonl"})
    executor = AtomicAgentExecutor(runtime_port=ScriptedRuntimePort(result))

    execution_result = executor.execute(_request(tmp_path, monkeypatch))

    assert execution_result.atomic_run_id == "run.atomic.1"


def test_atomic_agent_executor_rejects_retry_after_workspace_mutation():
    from boardroom_os.execution.atomic_executor import AtomicRetryDecision

    decision = AtomicRetryDecision.can_retry(
        failure_kind="runtime_crash",
        attempt_index=0,
        max_retries=1,
        workspace_mutations=[{"path": "backend/app.py"}],
    )

    assert decision.allowed is False
    assert "workspace mutation" in decision.reason


def test_atomic_runtime_factory_rejects_command_executable_not_absolute(tmp_path, monkeypatch):
    from boardroom_os.execution.atomic_executor import AtomicAgentRuntimeFactory

    settings = _settings(tmp_path, monkeypatch)

    with pytest.raises(ValueError, match="command executable must be an absolute path"):
        AtomicAgentRuntimeFactory(settings=settings).build_runtime_port(
            execution_package=_execution_package_for_config(),
            seat_ref="seat.worker.implementation",
            workspace_root=tmp_path,
            run_id="run.atomic.factory.bad-command",
        )
