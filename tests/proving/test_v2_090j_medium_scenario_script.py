from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import pytest

from boardroom_os.config.boardroom import load_boardroom_settings
from boardroom_os.execution.atomic_agent import AtomicInvocationCompiler
from scripts.run_v2_090j_medium_scenario import (
    MEDIUM_SCENARIO_MARKER_FILENAME,
    MEDIUM_SCENARIO_MARKER,
    MEDIUM_SCENARIO_COMMAND_ID,
    REQUIRED_OUTPUT_PATHS,
    MediumScenarioResetError,
    _build_report,
    _execution_package,
    _medium_scenario_check_code,
    _new_run_id,
    _settings_with_medium_scenario_budget,
    initialize_medium_scenario_workspace,
)
from tests.config.test_boardroom_config import _write_config_files
from tests.proving.test_v2_090i_medium_scenario_script import _write_valid_forecast_engine_package


def test_v2_090j_reset_refuses_unmarked_existing_directory(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "unrelated.txt").write_text("do not delete", encoding="utf-8")

    with pytest.raises(MediumScenarioResetError, match="missing V2-090J marker"):
        initialize_medium_scenario_workspace(workspace, reset=True)

    assert (workspace / "unrelated.txt").read_text(encoding="utf-8") == "do not delete"


def test_v2_090j_initializes_workspace_with_marker(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"

    initialized = initialize_medium_scenario_workspace(workspace, reset=False)

    marker = json.loads((initialized / MEDIUM_SCENARIO_MARKER_FILENAME).read_text(encoding="utf-8"))
    assert marker == MEDIUM_SCENARIO_MARKER
    assert marker["scenario"] == "v2-090j-medium"
    assert (initialized / "work").is_dir()


def test_v2_090j_run_id_is_run_scoped() -> None:
    first = _new_run_id("boardroom-atomic")
    second = _new_run_id("boardroom-atomic")

    assert first.startswith("boardroom-atomic.v2-090j.medium.")
    assert second.startswith("boardroom-atomic.v2-090j.medium.")
    assert first != second


def test_v2_090j_check_code_accepts_valid_package(tmp_path: Path) -> None:
    (tmp_path / "work").mkdir()
    _write_valid_forecast_engine_package(tmp_path)

    completed = subprocess.run(
        [sys.executable, "-c", _medium_scenario_check_code()],
        cwd=tmp_path,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr


def test_v2_090j_execution_package_requests_batch_protocol_and_checkpoint(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = _write_config_files(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-secret")
    settings = _settings_with_medium_scenario_budget(load_boardroom_settings(paths, env_values={}))
    package = _execution_package(settings)

    assert "agent-action-batch-v1" in package.objective
    assert package.ticket_ref.value == "ticket.medium.forecast-engine.protocol-repair"
    assert package.commands[0].command_id.value == MEDIUM_SCENARIO_COMMAND_ID
    assert {output.value for output in package.required_outputs} == set(REQUIRED_OUTPUT_PATHS)

    invocation = AtomicInvocationCompiler(workspace_root=tmp_path).compile_with_settings(
        execution_package=package,
        settings=settings,
        seat_ref="seat.worker.implementation",
    )
    checkpoint = invocation.output_requirements["required_output_checkpoint"]
    assert invocation.metadata["action_protocol"] == "agent-action-batch-v1"
    assert invocation.budgets["max_actions_per_turn"] == settings.runtime.atomic_agent.budget_caps.max_actions_per_turn
    assert checkpoint["run_command_id"] == MEDIUM_SCENARIO_COMMAND_ID
    assert checkpoint["when_all_paths_exist"] == list(REQUIRED_OUTPUT_PATHS)


def test_v2_090j_settings_require_batch_budget(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paths = _write_config_files(tmp_path)
    runtime_text = paths.runtime_config.read_text(encoding="utf-8")
    runtime_text = runtime_text.replace("max_actions_per_turn: 8", "max_actions_per_turn: 1")
    runtime_text = runtime_text.replace("max_actions_per_turn: 4", "max_actions_per_turn: 1")
    paths.runtime_config.write_text(runtime_text, encoding="utf-8")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-secret")
    settings = load_boardroom_settings(paths, env_values={})

    with pytest.raises(ValueError, match="max_actions_per_turn must be greater than 1"):
        _settings_with_medium_scenario_budget(settings)


def test_v2_090j_checkpoint_max_auto_runs_comes_from_settings(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = _write_config_files(tmp_path)
    runtime_text = paths.runtime_config.read_text(encoding="utf-8")
    runtime_text = runtime_text.replace("max_auto_runs: 3", "max_auto_runs: 2")
    paths.runtime_config.write_text(runtime_text, encoding="utf-8")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-secret")
    settings = _settings_with_medium_scenario_budget(load_boardroom_settings(paths, env_values={}))
    package = _execution_package(settings)

    invocation = AtomicInvocationCompiler(workspace_root=tmp_path).compile_with_settings(
        execution_package=package,
        settings=settings,
        seat_ref="seat.worker.implementation",
    )

    assert invocation.output_requirements["required_output_checkpoint"]["max_auto_runs"] == 2


def test_v2_090j_report_success_requires_checkpoint_command_evidence() -> None:
    report = _build_report(
        ticket_ref="ticket.medium.forecast-engine.protocol-repair",
        execution_package_id="exec.ticket.v2-090j.medium-scenario.1",
        atomic_run_id="boardroom-atomic.v2-090j.medium.test",
        workspace_root=Path(".evidence/atomic-agent/v2-090j-medium-scenario-workspace"),
        event_stream_ref="events.jsonl",
        events_hash="sha256:abc",
        provider_attempt_ref="provider-attempt.atomic.run.turn",
        work_product_ref="work-product.medium",
        source_lineage_inputs=("source-lineage.medium",),
        event_summary={
            "terminal_event_type": "run.completed",
            "provider_turn_completed_count": 1,
            "action_rejected_count": 0,
            "retryable_action_rejected_count": 0,
            "retry_rate": 0.0,
            "command_exit_codes": {},
            "workspace_mutation_paths": ("work/forecast_engine/risk.py",),
        },
        action_protocol="agent-action-batch-v1",
        max_actions_per_turn=8,
        checkpoint_max_auto_runs=3,
    )

    assert report["success"] is False
    assert report["action_protocol"] == "agent-action-batch-v1"
    assert report["max_actions_per_turn"] == 8
    assert report["checkpoint_max_auto_runs"] == 3
