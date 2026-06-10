from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import textwrap

import pytest

from boardroom_os.config.boardroom import load_boardroom_settings
from scripts.run_v2_090i_medium_scenario import (
    MEDIUM_SCENARIO_MARKER_FILENAME,
    MediumScenarioResetError,
    _build_report,
    _execution_package,
    _medium_scenario_check_code,
    _new_run_id,
    _settings_with_medium_scenario_budget,
    _summarize_event_stream,
    initialize_medium_scenario_workspace,
)
from tests.config.test_boardroom_config import _write_config_files


def test_medium_scenario_reset_refuses_unmarked_existing_directory(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "unrelated.txt").write_text("do not delete", encoding="utf-8")

    with pytest.raises(MediumScenarioResetError, match="missing V2-090I marker"):
        initialize_medium_scenario_workspace(workspace, reset=True)

    assert (workspace / "unrelated.txt").read_text(encoding="utf-8") == "do not delete"


def test_medium_scenario_reset_deletes_only_marked_workspace(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    work = workspace / "work"
    work.mkdir(parents=True)
    (workspace / MEDIUM_SCENARIO_MARKER_FILENAME).write_text(
        json.dumps({"scenario": "v2-090i-medium", "version": 1}),
        encoding="utf-8",
    )
    (work / "stale.py").write_text("print('stale')", encoding="utf-8")

    initialized = initialize_medium_scenario_workspace(workspace, reset=True)

    assert initialized == workspace
    assert workspace.exists()
    assert (workspace / MEDIUM_SCENARIO_MARKER_FILENAME).exists()
    assert (workspace / "work").is_dir()
    assert not (workspace / "work" / "stale.py").exists()


def test_medium_scenario_initializes_new_workspace_with_marker(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"

    initialized = initialize_medium_scenario_workspace(workspace, reset=False)

    marker = json.loads((initialized / MEDIUM_SCENARIO_MARKER_FILENAME).read_text(encoding="utf-8"))
    assert marker == {"scenario": "v2-090i-medium", "version": 1}
    assert (initialized / "work").is_dir()


def test_v2_090i_run_id_is_run_scoped() -> None:
    first = _new_run_id("boardroom-atomic")
    second = _new_run_id("boardroom-atomic")

    assert first.startswith("boardroom-atomic.v2-090i.medium.")
    assert second.startswith("boardroom-atomic.v2-090i.medium.")
    assert first != second


def _write_valid_forecast_engine_package(root: Path) -> None:
    package = root / "work" / "forecast_engine"
    tests = root / "work" / "tests"
    package.mkdir(parents=True)
    tests.mkdir(parents=True)
    (package / "__init__.py").write_text(
        textwrap.dedent(
            '''
            from .statistics import linear_regression_forecast, max_drawdown, weighted_moving_average
            from .risk import analyze_series

            __all__ = [
                "analyze_series",
                "linear_regression_forecast",
                "max_drawdown",
                "weighted_moving_average",
            ]
            '''
        ).strip()
        + "\n",
        encoding="utf-8",
    )
    (package / "statistics.py").write_text(
        textwrap.dedent(
            '''
            from __future__ import annotations

            import math


            def weighted_moving_average(values: list[float], window: int) -> float:
                if window <= 0:
                    raise ValueError("window must be positive")
                if len(values) < window:
                    raise ValueError("not enough values")
                tail = values[-window:]
                weights = list(range(1, window + 1))
                return sum(value * weight for value, weight in zip(tail, weights)) / sum(weights)


            def linear_regression_forecast(values: list[float]) -> float:
                if len(values) < 2:
                    raise ValueError("at least two values are required")
                n = len(values)
                xs = list(range(n))
                mean_x = sum(xs) / n
                mean_y = sum(values) / n
                denominator = sum((x - mean_x) ** 2 for x in xs)
                if denominator == 0:
                    return values[-1]
                slope = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, values)) / denominator
                intercept = mean_y - slope * mean_x
                return intercept + slope * n


            def regression_slope(values: list[float]) -> float:
                if len(values) < 2:
                    raise ValueError("at least two values are required")
                n = len(values)
                xs = list(range(n))
                mean_x = sum(xs) / n
                mean_y = sum(values) / n
                denominator = sum((x - mean_x) ** 2 for x in xs)
                if denominator == 0:
                    return 0.0
                return sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, values)) / denominator


            def population_stddev(values: list[float]) -> float:
                if not values:
                    raise ValueError("values must not be empty")
                mean = sum(values) / len(values)
                return math.sqrt(sum((value - mean) ** 2 for value in values) / len(values))


            def max_drawdown(values: list[float]) -> float:
                if not values:
                    raise ValueError("values must not be empty")
                peak = values[0]
                worst = 0.0
                for value in values:
                    if value > peak:
                        peak = value
                    if peak != 0:
                        worst = max(worst, (peak - value) / abs(peak))
                return worst
            '''
        ).strip()
        + "\n",
        encoding="utf-8",
    )
    (package / "risk.py").write_text(
        textwrap.dedent(
            '''
            from __future__ import annotations

            from .statistics import (
                linear_regression_forecast,
                max_drawdown,
                population_stddev,
                regression_slope,
                weighted_moving_average,
            )


            def analyze_series(values: list[float]) -> dict[str, float | str]:
                if len(values) < 4:
                    raise ValueError("at least four values are required")
                mean = sum(values) / len(values)
                mean_abs = abs(mean) or 1.0
                volatility = population_stddev(values) / mean_abs
                trend_ratio = regression_slope(values) / mean_abs
                negative_trend = max(0.0, -trend_ratio)
                drawdown = max_drawdown(values)
                risk_score = round(min(100.0, volatility * 45.0 + drawdown * 35.0 + negative_trend * 20.0), 4)
                if risk_score < 8.0:
                    risk_level = "low"
                elif risk_score < 20.0:
                    risk_level = "medium"
                else:
                    risk_level = "high"
                return {
                    "mean": round(mean, 4),
                    "weighted_moving_average": round(weighted_moving_average(values, min(3, len(values))), 4),
                    "linear_regression_forecast": round(linear_regression_forecast(values), 4),
                    "max_drawdown": round(drawdown, 4),
                    "risk_score": risk_score,
                    "risk_level": risk_level,
                }
            '''
        ).strip()
        + "\n",
        encoding="utf-8",
    )
    (package / "cli.py").write_text(
        textwrap.dedent(
            '''
            from __future__ import annotations

            import json
            from pathlib import Path
            import sys

            from .risk import analyze_series


            def main(argv: list[str] | None = None) -> int:
                argv = list(sys.argv[1:] if argv is None else argv)
                if len(argv) != 1:
                    print("usage: python -m forecast_engine.cli INPUT_JSON", file=sys.stderr)
                    return 2
                data = json.loads(Path(argv[0]).read_text(encoding="utf-8"))
                values = [float(value) for value in data["series"]]
                print(json.dumps(analyze_series(values), sort_keys=True))
                return 0


            if __name__ == "__main__":
                raise SystemExit(main())
            '''
        ).strip()
        + "\n",
        encoding="utf-8",
    )
    (tests / "test_forecast_engine.py").write_text(
        textwrap.dedent(
            '''
            from __future__ import annotations

            import unittest

            from forecast_engine import analyze_series, linear_regression_forecast, max_drawdown, weighted_moving_average


            class ForecastEngineTests(unittest.TestCase):
                def test_weighted_moving_average(self) -> None:
                    self.assertAlmostEqual(weighted_moving_average([10, 20, 40, 80], 3), 56.6666667, places=5)

                def test_linear_regression_forecast(self) -> None:
                    self.assertAlmostEqual(linear_regression_forecast([3, 7, 11, 15]), 19.0, places=5)

                def test_max_drawdown(self) -> None:
                    self.assertAlmostEqual(max_drawdown([100, 120, 90, 130, 65]), 0.5, places=5)

                def test_analyze_series(self) -> None:
                    report = analyze_series([100, 106, 103, 111, 97, 92, 95])
                    self.assertIn(report["risk_level"], {"low", "medium", "high"})
                    self.assertGreater(report["risk_score"], 0)


            if __name__ == "__main__":
                unittest.main()
            '''
        ).strip()
        + "\n",
        encoding="utf-8",
    )


def test_medium_scenario_check_code_accepts_valid_package(tmp_path: Path) -> None:
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


def test_medium_scenario_execution_package_uses_boardroom_settings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = _write_config_files(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-secret")
    settings = load_boardroom_settings(paths, env_values={})

    package = _execution_package(settings)

    assert package.execution_package_id.value == "exec.ticket.v2-090i.medium-scenario.1"
    assert package.ticket_ref.value == "ticket.medium.forecast-engine"
    assert package.seat_ref.value == "seat.worker.implementation"
    assert package.model_execution_profile.model == "gpt-5.5"
    assert package.model_execution_profile.context_window == 400000
    assert package.model_execution_profile.reasoning_effort == "high"
    assert package.allowed_write_set[0].value == "work/"
    assert {output.value for output in package.required_outputs} == {
        "work/forecast_engine/__init__.py",
        "work/forecast_engine/statistics.py",
        "work/forecast_engine/risk.py",
        "work/forecast_engine/cli.py",
        "work/tests/test_forecast_engine.py",
    }
    assert len(package.commands) == 1
    assert package.commands[0].command_id.value == "cmd.check-medium-scenario"
    assert package.commands[0].command[:2] == (sys.executable, "-c")
    assert "weighted_moving_average" in package.objective
    assert "linear_regression_forecast" in package.objective
    assert "max_drawdown" in package.objective
    assert "submit_result" in "\n".join(package.constraints)


def test_medium_scenario_settings_adds_run_scoped_budget_without_provider_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = _write_config_files(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-secret")
    settings = load_boardroom_settings(paths, env_values={})

    medium_settings = _settings_with_medium_scenario_budget(settings)

    assert settings.provider_by_id("provider.openai-compatible.primary").model == "gpt-5.5"
    assert medium_settings.provider_by_id("provider.openai-compatible.primary").model == "gpt-5.5"
    assert settings.budgets_for_seat("seat.worker.implementation")["max_parse_failures"] == 3
    assert medium_settings.budgets_for_seat("seat.worker.implementation")["max_parse_failures"] == 6
    assert medium_settings.budgets_for_seat("seat.worker.implementation")["max_steps"] == 240
    role_slot = medium_settings.role_slot_by_seat("seat.worker.implementation")
    assert "write_file" in role_slot.default_tools
    assert "run_command" in role_slot.default_tools
    assert "submit_result" in role_slot.default_tools
    assert "apply_patch" not in role_slot.default_tools


def test_medium_scenario_event_summary_counts_provider_turns_and_rejections(tmp_path: Path) -> None:
    event_stream = tmp_path / "events.jsonl"
    events = [
        {"type": "provider.turn.completed", "payload": {"provider_turn_id": "turn-1"}},
        {"type": "action.rejected", "payload": {"error": {"retryable": True}}},
        {"type": "workspace.mutation.recorded", "payload": {"path": "work/forecast_engine/statistics.py"}},
        {"type": "command.completed", "payload": {"command_id": "cmd.check-medium-scenario", "exit_code": 0}},
        {"type": "run.completed", "payload": {}},
    ]
    event_stream.write_text("".join(json.dumps(event) + "\n" for event in events), encoding="utf-8")

    summary = _summarize_event_stream(event_stream)

    assert summary["terminal_event_type"] == "run.completed"
    assert summary["provider_turn_completed_count"] == 1
    assert summary["action_rejected_count"] == 1
    assert summary["retryable_action_rejected_count"] == 1
    assert summary["retry_rate"] == 1.0
    assert summary["command_exit_codes"] == {"cmd.check-medium-scenario": 0}
    assert summary["workspace_mutation_paths"] == ("work/forecast_engine/statistics.py",)


def test_medium_scenario_report_marks_success_only_with_required_evidence() -> None:
    report = _build_report(
        ticket_ref="ticket.medium.forecast-engine",
        execution_package_id="exec.ticket.v2-090i.medium-scenario.1",
        atomic_run_id="boardroom-atomic.v2-090i.medium.20260610T000000Z.abcdef12",
        workspace_root=Path(".evidence/atomic-agent/v2-090i-medium-scenario-workspace"),
        event_stream_ref="boardroom-atomic.v2-090i.medium.20260610T000000Z.abcdef12.jsonl",
        events_hash="sha256:abc",
        provider_attempt_ref="provider-attempt.atomic.run.turn",
        work_product_ref="work-product.medium",
        source_lineage_inputs=("source-lineage.medium",),
        event_summary={
            "terminal_event_type": "run.completed",
            "provider_turn_completed_count": 2,
            "action_rejected_count": 1,
            "retryable_action_rejected_count": 1,
            "retry_rate": 0.5,
            "command_exit_codes": {"cmd.check-medium-scenario": 0},
            "workspace_mutation_paths": ("work/forecast_engine/risk.py",),
        },
    )

    assert report["success"] is True
    assert report["provider_transport_kind"] == "real"
    assert report["command_exit_codes"] == {"cmd.check-medium-scenario": 0}
    assert report["source_lineage_inputs"] == ("source-lineage.medium",)
