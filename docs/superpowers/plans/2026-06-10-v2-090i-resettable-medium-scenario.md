# V2-090I Resettable Medium Scenario Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build V2-090I（可重置中等复杂实施场景） so a real provider-backed atomic-agent executor（模型供应商支撑原子智能体执行器） proves multi-file Python package/CLI delivery with non-trivial algorithms, real command evidence, reset safety, and source lineage.

**Architecture:** Add one focused proving runner under `scripts/` that owns the resettable workspace, constructs a single medium-complexity `ExecutionPackage`（执行包）, invokes `AtomicAgentExecutor`（原子智能体执行器） with `provider_transport_kind="real"`, and emits a JSON report from the event stream. Keep provider/runtime/role configuration delegated to existing `.env` + `config/boardroom-*.example.yaml`; tests cover reset safety and package construction without provider, while the real provider proving test is explicit opt-in.

**Tech Stack:** Python 3.12 standard library, pytest, existing Boardroom OS config/execution/contracts modules, external `atomic-agent`（原子智能体） package, OpenAI-compatible provider config via existing YAML.

---

## File Structure

### Files to create

- `scripts/run_v2_090i_medium_scenario.py` — resettable V2-090I runner, medium scenario `ExecutionPackage` builder, validation command source, real atomic-agent invocation, event stream summarizer, JSON report writer.
- `tests/proving/test_v2_090i_medium_scenario_script.py` — non-provider unit/proving tests for reset guardrails, run ID format, validator command behavior, and config-derived execution package construction.
- `tests/proving/test_v2_090i_medium_scenario.py` — explicit opt-in real provider proving test that resets the scenario, runs the runner, and verifies evidence summary fields.

### Files to modify

- `scripts/README.md` — document V2-090I runner purpose, reset behavior, and opt-in command.
- `doc/04-implementation/backlog.md` — add V2-090I work package, update Phase 9 count from `7 / 8` to `7 / 9`, and set current unfinished work to V2-090I while V2-090F remains blocked after it.
- `doc/04-implementation/acceptance-criteria.md` — add Phase 9 checkbox for V2-090I medium scenario evidence.
- `doc/05-project-log/2026-06.md` — append a V2-090I planning/implementation entry after implementation verification succeeds.

### Files already created before this plan

- `docs/superpowers/specs/2026-06-10-v2-090i-resettable-medium-scenario-design.md` — reviewed design spec（规格） for this implementation plan.

---

## Preconditions and guardrails

- Do not edit `.env`; it is ignored local configuration and remains the source of secrets/config paths only.
- Do not add new provider configuration files. Use `BOARDROOM_RUNTIME_CONFIG`, `BOARDROOM_PROVIDERS_CONFIG`, and `BOARDROOM_ROLES_CONFIG` with existing defaults.
- Do not hardcode model, base URL, timeout, or reasoning effort in the runner. Derive these from `load_boardroom_settings`（加载董事会配置）.
- Do not use fake provider transport in the V2-090I happy path.
- Do not make retry rate（重试率） a pass/fail threshold. Report it only.
- Do not claim V2-090F is unblocked. V2-090I is prerequisite evidence, not golden sample completion.

---

## Task 1: Reset workspace guardrails and run ID tests

**Files:**
- Create: `tests/proving/test_v2_090i_medium_scenario_script.py`
- Create later: `scripts/run_v2_090i_medium_scenario.py`

- [ ] **Step 1: Write failing reset and run ID tests**

Create `tests/proving/test_v2_090i_medium_scenario_script.py` with this content:

```python
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.run_v2_090i_medium_scenario import (
    MEDIUM_SCENARIO_MARKER_FILENAME,
    MediumScenarioResetError,
    _new_run_id,
    initialize_medium_scenario_workspace,
)


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
```

- [ ] **Step 2: Run tests to verify they fail because the runner does not exist**

Run:

```bash
PYTHONPATH=src:. python -m pytest tests/proving/test_v2_090i_medium_scenario_script.py -q --tb=short
```

Expected: FAIL with `ModuleNotFoundError: No module named 'scripts.run_v2_090i_medium_scenario'`.

- [ ] **Step 3: Implement reset guardrails and run ID helpers**

Create `scripts/run_v2_090i_medium_scenario.py` with this initial content:

```python
from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
import shutil
from uuid import uuid4

MEDIUM_SCENARIO_MARKER_FILENAME = ".boardroom-v2-090i-workspace.json"
MEDIUM_SCENARIO_MARKER = {"scenario": "v2-090i-medium", "version": 1}


class MediumScenarioResetError(ValueError):
    pass


def initialize_medium_scenario_workspace(workspace_root: Path, *, reset: bool) -> Path:
    workspace_root = workspace_root.resolve()
    marker_path = workspace_root / MEDIUM_SCENARIO_MARKER_FILENAME
    if workspace_root.exists() and not marker_path.exists():
        raise MediumScenarioResetError(f"refusing to reset workspace missing V2-090I marker: {workspace_root}")
    if workspace_root.exists() and reset:
        shutil.rmtree(workspace_root)
    workspace_root.mkdir(parents=True, exist_ok=True)
    marker_path.write_text(json.dumps(MEDIUM_SCENARIO_MARKER, sort_keys=True), encoding="utf-8")
    (workspace_root / "work").mkdir(parents=True, exist_ok=True)
    return workspace_root


def _new_run_id(prefix: str) -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"{prefix}.v2-090i.medium.{stamp}.{uuid4().hex[:8]}"


if __name__ == "__main__":
    raise SystemExit("V2-090I runner execution is added in a later task")
```

- [ ] **Step 4: Run reset tests and verify they pass**

Run:

```bash
PYTHONPATH=src:. python -m pytest tests/proving/test_v2_090i_medium_scenario_script.py -q --tb=short
```

Expected: PASS, 4 passed.

---

## Task 2: External medium scenario validator command

**Files:**
- Modify: `tests/proving/test_v2_090i_medium_scenario_script.py`
- Modify: `scripts/run_v2_090i_medium_scenario.py`

- [ ] **Step 1: Add a failing test for the validator command against a valid generated package**

Append this code to `tests/proving/test_v2_090i_medium_scenario_script.py`:

```python
import subprocess
import sys
import textwrap

from scripts.run_v2_090i_medium_scenario import _medium_scenario_check_code


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
```

- [ ] **Step 2: Run the validator test to verify it fails because `_medium_scenario_check_code` is missing**

Run:

```bash
PYTHONPATH=src:. python -m pytest tests/proving/test_v2_090i_medium_scenario_script.py::test_medium_scenario_check_code_accepts_valid_package -q --tb=short
```

Expected: FAIL with `ImportError` or `AttributeError` naming `_medium_scenario_check_code`.

- [ ] **Step 3: Add the validator command source**

Append this function to `scripts/run_v2_090i_medium_scenario.py` before the `if __name__ == "__main__"` block:

```python
def _medium_scenario_check_code() -> str:
    return r'''
from __future__ import annotations

import json
import math
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path.cwd()
WORK = ROOT / "work"
REQUIRED = [
    WORK / "forecast_engine" / "__init__.py",
    WORK / "forecast_engine" / "statistics.py",
    WORK / "forecast_engine" / "risk.py",
    WORK / "forecast_engine" / "cli.py",
    WORK / "tests" / "test_forecast_engine.py",
]


def fail(message: str) -> None:
    print(message, file=sys.stderr)
    raise SystemExit(3)


for path in REQUIRED:
    if not path.exists():
        fail(f"missing required file: {path.relative_to(ROOT)}")

risk_source = (WORK / "forecast_engine" / "risk.py").read_text(encoding="utf-8")
if "from .statistics import" not in risk_source and "import forecast_engine.statistics" not in risk_source:
    fail("risk.py must import statistics.py")

sys.path.insert(0, str(WORK))
try:
    import forecast_engine
    from forecast_engine.statistics import linear_regression_forecast, max_drawdown, weighted_moving_average
    from forecast_engine.risk import analyze_series
except Exception as exc:
    fail(f"package import failed: {exc}")

for name in ["weighted_moving_average", "linear_regression_forecast", "max_drawdown", "analyze_series"]:
    if not hasattr(forecast_engine, name):
        fail(f"forecast_engine missing public API: {name}")


def assert_close(actual: float, expected: float, name: str, tolerance: float = 1e-4) -> None:
    if abs(actual - expected) > tolerance:
        fail(f"{name} expected {expected}, got {actual}")


assert_close(weighted_moving_average([10, 20, 40, 80], 3), (20 * 1 + 40 * 2 + 80 * 3) / 6, "weighted_moving_average")
assert_close(linear_regression_forecast([3, 7, 11, 15]), 19.0, "linear_regression_forecast")
assert_close(max_drawdown([100, 120, 90, 130, 65]), 0.5, "max_drawdown")

SERIES = [100, 106, 103, 111, 97, 92, 95]


def expected_report(values: list[float]) -> dict[str, float | str]:
    mean = sum(values) / len(values)
    stddev = math.sqrt(sum((value - mean) ** 2 for value in values) / len(values))
    xs = list(range(len(values)))
    mean_x = sum(xs) / len(xs)
    denominator = sum((x - mean_x) ** 2 for x in xs)
    slope = sum((x - mean_x) * (y - mean) for x, y in zip(xs, values)) / denominator
    intercept = mean - slope * mean_x
    forecast = intercept + slope * len(values)
    peak = values[0]
    drawdown = 0.0
    for value in values:
        if value > peak:
            peak = value
        drawdown = max(drawdown, (peak - value) / abs(peak))
    tail = values[-3:]
    wma = sum(value * weight for value, weight in zip(tail, [1, 2, 3])) / 6
    mean_abs = abs(mean) or 1.0
    volatility = stddev / mean_abs
    trend_ratio = slope / mean_abs
    risk_score = round(min(100.0, volatility * 45.0 + drawdown * 35.0 + max(0.0, -trend_ratio) * 20.0), 4)
    if risk_score < 8.0:
        risk_level = "low"
    elif risk_score < 20.0:
        risk_level = "medium"
    else:
        risk_level = "high"
    return {
        "mean": round(mean, 4),
        "weighted_moving_average": round(wma, 4),
        "linear_regression_forecast": round(forecast, 4),
        "max_drawdown": round(drawdown, 4),
        "risk_score": risk_score,
        "risk_level": risk_level,
    }


actual = analyze_series(SERIES)
expected = expected_report(SERIES)
for key, expected_value in expected.items():
    if key not in actual:
        fail(f"analyze_series missing key: {key}")
    actual_value = actual[key]
    if isinstance(expected_value, float):
        assert_close(float(actual_value), expected_value, f"analyze_series.{key}")
    elif actual_value != expected_value:
        fail(f"analyze_series.{key} expected {expected_value}, got {actual_value}")

unit_env = os.environ.copy()
unit_env["PYTHONPATH"] = str(WORK) + os.pathsep + unit_env.get("PYTHONPATH", "")
unit_result = subprocess.run(
    [sys.executable, "-m", "unittest", "discover", "-s", "work/tests", "-p", "test_*.py"],
    cwd=ROOT,
    text=True,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    env=unit_env,
    check=False,
)
if unit_result.returncode != 0:
    fail("unittest failed:\n" + unit_result.stdout + unit_result.stderr)

input_path = WORK / "v2_090i_input_series.json"
input_path.write_text(json.dumps({"series": SERIES}), encoding="utf-8")
cli_result = subprocess.run(
    [sys.executable, "-m", "forecast_engine.cli", str(input_path)],
    cwd=ROOT,
    text=True,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    env=unit_env,
    check=False,
)
if cli_result.returncode != 0:
    fail("CLI failed:\n" + cli_result.stdout + cli_result.stderr)
try:
    cli_report = json.loads(cli_result.stdout)
except json.JSONDecodeError as exc:
    fail(f"CLI output is not JSON: {exc}")
for key, expected_value in expected.items():
    if key not in cli_report:
        fail(f"CLI report missing key: {key}")
    actual_value = cli_report[key]
    if isinstance(expected_value, float):
        assert_close(float(actual_value), expected_value, f"cli.{key}")
    elif actual_value != expected_value:
        fail(f"cli.{key} expected {expected_value}, got {actual_value}")

raise SystemExit(0)
'''.strip()
```

- [ ] **Step 4: Run the validator test and verify it passes**

Run:

```bash
PYTHONPATH=src:. python -m pytest tests/proving/test_v2_090i_medium_scenario_script.py::test_medium_scenario_check_code_accepts_valid_package -q --tb=short
```

Expected: PASS.

- [ ] **Step 5: Run all non-provider script tests**

Run:

```bash
PYTHONPATH=src:. python -m pytest tests/proving/test_v2_090i_medium_scenario_script.py -q --tb=short
```

Expected: PASS.

---

## Task 3: ExecutionPackage builder for V2-090I

**Files:**
- Modify: `tests/proving/test_v2_090i_medium_scenario_script.py`
- Modify: `scripts/run_v2_090i_medium_scenario.py`

- [ ] **Step 1: Add failing tests for config-derived package construction**

Append this code to `tests/proving/test_v2_090i_medium_scenario_script.py`:

```python
from boardroom_os.config.boardroom import load_boardroom_settings
from tests.config.test_boardroom_config import _write_config_files
from scripts.run_v2_090i_medium_scenario import _execution_package


def test_medium_scenario_execution_package_uses_boardroom_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
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
```

- [ ] **Step 2: Run the package construction test to verify it fails because `_execution_package` is missing**

Run:

```bash
PYTHONPATH=src:. python -m pytest tests/proving/test_v2_090i_medium_scenario_script.py::test_medium_scenario_execution_package_uses_boardroom_settings -q --tb=short
```

Expected: FAIL with `ImportError` or `AttributeError` naming `_execution_package`.

- [ ] **Step 3: Replace the runner with package construction support**

Replace the full content of `scripts/run_v2_090i_medium_scenario.py` with this version:

```python
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import shutil
import sys
from typing import Any
from uuid import uuid4

from boardroom_os.agents.profiles import ModelExecutionProfile
from boardroom_os.agents.role_prompt_hooks import (
    RolePromptHookRef,
    build_baseline_role_prompt_hook_registry,
)
from boardroom_os.agents.seat import AgentSeatRef
from boardroom_os.config.boardroom import BoardroomConfigPaths, load_boardroom_settings
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

MEDIUM_SCENARIO_MARKER_FILENAME = ".boardroom-v2-090i-workspace.json"
MEDIUM_SCENARIO_MARKER = {"scenario": "v2-090i-medium", "version": 1}
MEDIUM_SCENARIO_TICKET_REF = "ticket.medium.forecast-engine"
MEDIUM_SCENARIO_COMMAND_ID = "cmd.check-medium-scenario"
REQUIRED_OUTPUT_PATHS = (
    "work/forecast_engine/__init__.py",
    "work/forecast_engine/statistics.py",
    "work/forecast_engine/risk.py",
    "work/forecast_engine/cli.py",
    "work/tests/test_forecast_engine.py",
)


class MediumScenarioResetError(ValueError):
    pass


@dataclass(frozen=True)
class MediumScenarioPaths:
    workspace_root: Path
    event_stream_root: Path


def initialize_medium_scenario_workspace(workspace_root: Path, *, reset: bool) -> Path:
    workspace_root = workspace_root.resolve()
    marker_path = workspace_root / MEDIUM_SCENARIO_MARKER_FILENAME
    if workspace_root.exists() and not marker_path.exists():
        raise MediumScenarioResetError(f"refusing to reset workspace missing V2-090I marker: {workspace_root}")
    if workspace_root.exists() and reset:
        shutil.rmtree(workspace_root)
    workspace_root.mkdir(parents=True, exist_ok=True)
    marker_path.write_text(json.dumps(MEDIUM_SCENARIO_MARKER, sort_keys=True), encoding="utf-8")
    (workspace_root / "work").mkdir(parents=True, exist_ok=True)
    return workspace_root


def _execution_package(settings: Any) -> ExecutionPackage:
    role_slot = settings.role_slot_by_seat("seat.worker.implementation")
    provider_config = settings.provider_by_id(role_slot.provider_profile_ref)
    model_execution_profile = ModelExecutionProfile(
        model_execution_profile_id=role_slot.model_execution_profile_id,
        provider="openai-compatible",
        model=provider_config.model,
        reasoning_effort=provider_config.reasoning_effort or "high",
        context_window=provider_config.context_window_tokens,
        temperature=0.0 if provider_config.temperature is None else provider_config.temperature,
        tool_permissions=("filesystem.read", "filesystem.write", "command.execute"),
        fallback_policy_ref="fallback.default",
    )
    evidence_obligation = EvidenceObligation(
        evidence_obligation_id=EvidenceObligationRef(value="evidence.v2-090i.medium-scenario.source"),
        acceptance_refs=(AcceptanceRef(value="AC-V2-090I-MEDIUM-SCENARIO"),),
        source_surface_refs=(SourceSurfaceRef(value="surface.v2-090i.forecast-engine"),),
        required_artifact_type=RequiredArtifactType(value="source_patch"),
        required_verifier=RequiredVerifier(value="checker"),
        blocking=True,
    )
    command = PackageCommand(
        command_id=ContractId(value=MEDIUM_SCENARIO_COMMAND_ID),
        label="Check V2-090I medium forecast engine package",
        command=(sys.executable, "-c", _medium_scenario_check_code()),
        cwd=".",
    )
    produced_paths_json = json.dumps(list(REQUIRED_OUTPUT_PATHS), ensure_ascii=False)
    return ExecutionPackage(
        execution_package_id=ExecutionPackageId(value="exec.ticket.v2-090i.medium-scenario.1"),
        ticket_ref=TicketId(value=MEDIUM_SCENARIO_TICKET_REF),
        graph_version=1,
        seat_ref=AgentSeatRef(value="seat.worker.implementation"),
        model_execution_profile=model_execution_profile,
        role_prompt_hook=_baseline_worker_role_prompt_hook(),
        objective=(
            "Create a Python standard-library package and CLI under work/ named forecast_engine. "
            "The package must include work/forecast_engine/__init__.py, statistics.py, risk.py, cli.py, "
            "and work/tests/test_forecast_engine.py. Implement non-trivial multi-step algorithms: "
            "weighted_moving_average(values, window), linear_regression_forecast(values), max_drawdown(values), "
            "and analyze_series(values). risk.py must import and reuse statistics.py. cli.py must read a JSON file "
            "containing a series array and print a JSON risk report. Add unittest tests under work/tests. "
            f"Run {MEDIUM_SCENARIO_COMMAND_ID}, fix any failures, then submit the result. "
            "The final submit_result action must be exactly one JSON object with top-level action_id, action, "
            "reason_summary, and input fields. The input field must contain summary, produced_paths, and evidence_refs. "
            f"produced_paths must be exactly {produced_paths_json}; evidence_refs must be [\"{MEDIUM_SCENARIO_COMMAND_ID}\"]."
        ),
        context_refs=(ContextRef(value="context.v2-090i.medium-scenario"),),
        constraints=(
            "Only write under work/.",
            "Use only the Python standard library; do not install dependencies.",
            "Do not implement placeholder arithmetic; each public function must perform the specified multi-step calculation.",
            "risk.py must import statistics.py rather than duplicating all statistics functions.",
            f"Use run_command with {MEDIUM_SCENARIO_COMMAND_ID} before submit_result.",
            (
                "For submit_result, do not use action_envelope. Use this shape: "
                '{"action_id":"act.submit-result","action":"submit_result","reason_summary":"done",'
                f'"input":{{"summary":"Created and verified V2-090I forecast_engine package",'
                f'"produced_paths":{produced_paths_json},"evidence_refs":["{MEDIUM_SCENARIO_COMMAND_ID}"]}}}}'
            ),
        ),
        acceptance_refs=(AcceptanceRef(value="AC-V2-090I-MEDIUM-SCENARIO"),),
        source_surface_refs=(SourceSurfaceRef(value="surface.v2-090i.forecast-engine"),),
        allowed_read_refs=(AllowedReadRef(value="README.md"),),
        allowed_write_set=(AllowedWritePath(value="work/"),),
        required_outputs=tuple(RequiredOutput(value=path) for path in REQUIRED_OUTPUT_PATHS),
        commands=(command,),
        evidence_obligations=(evidence_obligation,),
        fallback_policy_ref=FallbackPolicyRef(value="fallback.default"),
        audit_requirements=(AuditRequirement(value="record V2-090I medium scenario provider, mutation, command, and lineage evidence"),),
    )


def _medium_scenario_check_code() -> str:
    return r'''
from __future__ import annotations

import json
import math
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path.cwd()
WORK = ROOT / "work"
REQUIRED = [
    WORK / "forecast_engine" / "__init__.py",
    WORK / "forecast_engine" / "statistics.py",
    WORK / "forecast_engine" / "risk.py",
    WORK / "forecast_engine" / "cli.py",
    WORK / "tests" / "test_forecast_engine.py",
]


def fail(message: str) -> None:
    print(message, file=sys.stderr)
    raise SystemExit(3)


for path in REQUIRED:
    if not path.exists():
        fail(f"missing required file: {path.relative_to(ROOT)}")

risk_source = (WORK / "forecast_engine" / "risk.py").read_text(encoding="utf-8")
if "from .statistics import" not in risk_source and "import forecast_engine.statistics" not in risk_source:
    fail("risk.py must import statistics.py")

sys.path.insert(0, str(WORK))
try:
    import forecast_engine
    from forecast_engine.statistics import linear_regression_forecast, max_drawdown, weighted_moving_average
    from forecast_engine.risk import analyze_series
except Exception as exc:
    fail(f"package import failed: {exc}")

for name in ["weighted_moving_average", "linear_regression_forecast", "max_drawdown", "analyze_series"]:
    if not hasattr(forecast_engine, name):
        fail(f"forecast_engine missing public API: {name}")


def assert_close(actual: float, expected: float, name: str, tolerance: float = 1e-4) -> None:
    if abs(actual - expected) > tolerance:
        fail(f"{name} expected {expected}, got {actual}")


assert_close(weighted_moving_average([10, 20, 40, 80], 3), (20 * 1 + 40 * 2 + 80 * 3) / 6, "weighted_moving_average")
assert_close(linear_regression_forecast([3, 7, 11, 15]), 19.0, "linear_regression_forecast")
assert_close(max_drawdown([100, 120, 90, 130, 65]), 0.5, "max_drawdown")

SERIES = [100, 106, 103, 111, 97, 92, 95]


def expected_report(values: list[float]) -> dict[str, float | str]:
    mean = sum(values) / len(values)
    stddev = math.sqrt(sum((value - mean) ** 2 for value in values) / len(values))
    xs = list(range(len(values)))
    mean_x = sum(xs) / len(xs)
    denominator = sum((x - mean_x) ** 2 for x in xs)
    slope = sum((x - mean_x) * (y - mean) for x, y in zip(xs, values)) / denominator
    intercept = mean - slope * mean_x
    forecast = intercept + slope * len(values)
    peak = values[0]
    drawdown = 0.0
    for value in values:
        if value > peak:
            peak = value
        drawdown = max(drawdown, (peak - value) / abs(peak))
    tail = values[-3:]
    wma = sum(value * weight for value, weight in zip(tail, [1, 2, 3])) / 6
    mean_abs = abs(mean) or 1.0
    volatility = stddev / mean_abs
    trend_ratio = slope / mean_abs
    risk_score = round(min(100.0, volatility * 45.0 + drawdown * 35.0 + max(0.0, -trend_ratio) * 20.0), 4)
    if risk_score < 8.0:
        risk_level = "low"
    elif risk_score < 20.0:
        risk_level = "medium"
    else:
        risk_level = "high"
    return {
        "mean": round(mean, 4),
        "weighted_moving_average": round(wma, 4),
        "linear_regression_forecast": round(forecast, 4),
        "max_drawdown": round(drawdown, 4),
        "risk_score": risk_score,
        "risk_level": risk_level,
    }


actual = analyze_series(SERIES)
expected = expected_report(SERIES)
for key, expected_value in expected.items():
    if key not in actual:
        fail(f"analyze_series missing key: {key}")
    actual_value = actual[key]
    if isinstance(expected_value, float):
        assert_close(float(actual_value), expected_value, f"analyze_series.{key}")
    elif actual_value != expected_value:
        fail(f"analyze_series.{key} expected {expected_value}, got {actual_value}")

unit_env = os.environ.copy()
unit_env["PYTHONPATH"] = str(WORK) + os.pathsep + unit_env.get("PYTHONPATH", "")
unit_result = subprocess.run(
    [sys.executable, "-m", "unittest", "discover", "-s", "work/tests", "-p", "test_*.py"],
    cwd=ROOT,
    text=True,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    env=unit_env,
    check=False,
)
if unit_result.returncode != 0:
    fail("unittest failed:\n" + unit_result.stdout + unit_result.stderr)

input_path = WORK / "v2_090i_input_series.json"
input_path.write_text(json.dumps({"series": SERIES}), encoding="utf-8")
cli_result = subprocess.run(
    [sys.executable, "-m", "forecast_engine.cli", str(input_path)],
    cwd=ROOT,
    text=True,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    env=unit_env,
    check=False,
)
if cli_result.returncode != 0:
    fail("CLI failed:\n" + cli_result.stdout + cli_result.stderr)
try:
    cli_report = json.loads(cli_result.stdout)
except json.JSONDecodeError as exc:
    fail(f"CLI output is not JSON: {exc}")
for key, expected_value in expected.items():
    if key not in cli_report:
        fail(f"CLI report missing key: {key}")
    actual_value = cli_report[key]
    if isinstance(expected_value, float):
        assert_close(float(actual_value), expected_value, f"cli.{key}")
    elif actual_value != expected_value:
        fail(f"cli.{key} expected {expected_value}, got {actual_value}")

raise SystemExit(0)
'''.strip()


def _new_run_id(prefix: str) -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"{prefix}.v2-090i.medium.{stamp}.{uuid4().hex[:8]}"


def _baseline_worker_role_prompt_hook():
    return build_baseline_role_prompt_hook_registry().require(
        RolePromptHookRef(value="role-prompt-hook.baseline.worker.v1")
    )


if __name__ == "__main__":
    raise SystemExit("V2-090I runner execution is added in a later task")
```

- [ ] **Step 4: Run package construction tests and verify they pass**

Run:

```bash
PYTHONPATH=src:. python -m pytest tests/proving/test_v2_090i_medium_scenario_script.py -q --tb=short
```

Expected: PASS.

---

## Task 4: Runner execution and JSON report

**Files:**
- Modify: `scripts/run_v2_090i_medium_scenario.py`
- Modify: `tests/proving/test_v2_090i_medium_scenario_script.py`

- [ ] **Step 1: Add failing tests for report summary helpers**

Append this code to `tests/proving/test_v2_090i_medium_scenario_script.py`:

```python
from scripts.run_v2_090i_medium_scenario import _build_report, _summarize_event_stream


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
```

- [ ] **Step 2: Run helper tests to verify they fail because summary helpers are missing**

Run:

```bash
PYTHONPATH=src:. python -m pytest tests/proving/test_v2_090i_medium_scenario_script.py::test_medium_scenario_event_summary_counts_provider_turns_and_rejections tests/proving/test_v2_090i_medium_scenario_script.py::test_medium_scenario_report_marks_success_only_with_required_evidence -q --tb=short
```

Expected: FAIL with missing `_summarize_event_stream` / `_build_report`.

- [ ] **Step 3: Add execution, event summary, report, and CLI entrypoint**

Modify `scripts/run_v2_090i_medium_scenario.py` as follows.

Add imports near the top:

```python
import argparse
import traceback

from boardroom_os.execution.atomic_executor import (
    AtomicAgentExecutor,
    AtomicAgentRuntimeFactory,
    AtomicExecutionRequest,
)
```

Append these functions before the `if __name__ == "__main__"` block:

```python
def run_medium_scenario(*, reset: bool) -> dict[str, Any]:
    settings = load_boardroom_settings(
        BoardroomConfigPaths(
            runtime_config=Path(os.environ.get("BOARDROOM_RUNTIME_CONFIG", "config/boardroom-runtime.example.yaml")),
            providers_config=Path(os.environ.get("BOARDROOM_PROVIDERS_CONFIG", "config/boardroom-providers.example.yaml")),
            roles_config=Path(os.environ.get("BOARDROOM_ROLES_CONFIG", "config/boardroom-roles.example.yaml")),
        ),
        env_values=dict(os.environ),
    )
    workspace_root = initialize_medium_scenario_workspace(
        Path(os.environ.get("BOARDROOM_EVIDENCE_ROOT", ".evidence"))
        / "atomic-agent"
        / "v2-090i-medium-scenario-workspace",
        reset=reset,
    )
    package = _execution_package(settings)
    run_id = _new_run_id(settings.runtime.atomic_agent.run_id_prefix)
    event_stream_root = Path(settings.runtime.atomic_agent.event_stream_root).resolve()
    runtime_port = AtomicAgentRuntimeFactory(settings=settings).build_runtime_port(
        execution_package=package,
        seat_ref="seat.worker.implementation",
        workspace_root=workspace_root,
        run_id=run_id,
    )
    result = AtomicAgentExecutor(
        runtime_port=runtime_port,
        allow_fake_provider_for_unit_tests=False,
    ).execute(
        AtomicExecutionRequest(
            execution_package=package,
            settings=settings,
            seat_ref="seat.worker.implementation",
            workspace_root=workspace_root,
            event_stream_root=event_stream_root,
        ),
        provider_transport_kind="real",
    )
    event_stream_path = event_stream_root / result.projection.event_stream_ref
    event_summary = _summarize_event_stream(event_stream_path)
    return _build_report(
        ticket_ref=package.ticket_ref.value,
        execution_package_id=package.execution_package_id.value,
        atomic_run_id=result.atomic_run_id,
        workspace_root=workspace_root,
        event_stream_ref=result.projection.event_stream_ref,
        events_hash=result.projection.events_hash,
        provider_attempt_ref=result.provider_attempt.provider_attempt_id.value,
        work_product_ref=result.projection.work_product_submission.work_product.work_product_id.value,
        source_lineage_inputs=result.projection.source_lineage_inputs,
        event_summary=event_summary,
    )


def _summarize_event_stream(event_stream_path: Path) -> dict[str, Any]:
    events = _read_events(event_stream_path)
    provider_turn_completed_count = _count_events(events, "provider.turn.completed")
    action_rejected_events = [event for event in events if event.get("type") == "action.rejected"]
    action_rejected_count = len(action_rejected_events)
    retryable_action_rejected_count = sum(
        1
        for event in action_rejected_events
        if bool(((event.get("payload") or {}).get("error") or {}).get("retryable"))
    )
    return {
        "terminal_event_type": _terminal_event_type(events),
        "provider_turn_completed_count": provider_turn_completed_count,
        "action_rejected_count": action_rejected_count,
        "retryable_action_rejected_count": retryable_action_rejected_count,
        "retry_rate": _retry_rate(action_rejected_count, provider_turn_completed_count),
        "command_exit_codes": _event_command_exit_codes(events),
        "workspace_mutation_paths": _event_workspace_mutation_paths(events),
    }


def _build_report(
    *,
    ticket_ref: str,
    execution_package_id: str,
    atomic_run_id: str,
    workspace_root: Path,
    event_stream_ref: str,
    events_hash: str,
    provider_attempt_ref: str,
    work_product_ref: str,
    source_lineage_inputs: tuple[str, ...],
    event_summary: dict[str, Any],
) -> dict[str, Any]:
    command_exit_codes = event_summary["command_exit_codes"]
    success = (
        event_summary["terminal_event_type"] == "run.completed"
        and event_summary["provider_turn_completed_count"] >= 1
        and command_exit_codes.get(MEDIUM_SCENARIO_COMMAND_ID) == 0
        and bool(event_summary["workspace_mutation_paths"])
        and bool(source_lineage_inputs)
    )
    return {
        "scenario": "v2-090i-resettable-medium-scenario",
        "ticket_ref": ticket_ref,
        "execution_package_id": execution_package_id,
        "atomic_run_id": atomic_run_id,
        "workspace_root": str(workspace_root),
        "event_stream_ref": event_stream_ref,
        "events_hash": events_hash,
        "provider_attempt_ref": provider_attempt_ref,
        "work_product_ref": work_product_ref,
        "provider_transport_kind": "real",
        "source_lineage_inputs": source_lineage_inputs,
        "terminal_event_type": event_summary["terminal_event_type"],
        "provider_turn_completed_count": event_summary["provider_turn_completed_count"],
        "action_rejected_count": event_summary["action_rejected_count"],
        "retryable_action_rejected_count": event_summary["retryable_action_rejected_count"],
        "retry_rate": event_summary["retry_rate"],
        "command_exit_codes": command_exit_codes,
        "workspace_mutation_paths": event_summary["workspace_mutation_paths"],
        "success": success,
    }


def _read_events(event_stream_path: Path) -> list[dict[str, Any]]:
    with event_stream_path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _count_events(events: list[dict[str, Any]], event_type: str) -> int:
    return sum(1 for event in events if event.get("type") == event_type)


def _terminal_event_type(events: list[dict[str, Any]]) -> str | None:
    for event in reversed(events):
        event_type = event.get("type")
        if event_type in {"run.completed", "run.failed"}:
            return event_type
    return None


def _retry_rate(action_rejected_count: int, provider_turn_completed_count: int) -> float:
    if provider_turn_completed_count == 0:
        return 0.0
    return action_rejected_count / provider_turn_completed_count


def _event_command_exit_codes(events: list[dict[str, Any]]) -> dict[str, int]:
    exit_codes: dict[str, int] = {}
    for event in events:
        if event.get("type") != "command.completed":
            continue
        payload = event.get("payload") or {}
        command_id = payload.get("command_id")
        exit_code = payload.get("exit_code")
        if isinstance(command_id, str) and isinstance(exit_code, int):
            exit_codes[command_id] = exit_code
    return exit_codes


def _event_workspace_mutation_paths(events: list[dict[str, Any]]) -> tuple[str, ...]:
    paths: list[str] = []
    for event in events:
        if event.get("type") != "workspace.mutation.recorded":
            continue
        payload = event.get("payload") or {}
        path = payload.get("path")
        if isinstance(path, str):
            paths.append(path)
    return tuple(paths)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run V2-090I resettable medium atomic-agent scenario.")
    parser.add_argument("--reset", action="store_true", help="Reset the marked V2-090I workspace before running.")
    args = parser.parse_args(argv)
    try:
        report = run_medium_scenario(reset=args.reset)
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
        return 0 if report["success"] else 1
    except Exception as exc:
        print(f"{exc.__class__.__name__}: {exc}", file=sys.stderr)
        if os.environ.get("BOARDROOM_DEBUG_TRACEBACK") == "1":
            traceback.print_exc(file=sys.stderr)
        return 1
```

Replace the final `if __name__ == "__main__"` block with:

```python
if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run helper tests and verify they pass**

Run:

```bash
PYTHONPATH=src:. python -m pytest tests/proving/test_v2_090i_medium_scenario_script.py -q --tb=short
```

Expected: PASS.

- [ ] **Step 5: Run the script without provider credentials and verify it fails closed**

Run:

```bash
env -u OPENAI_API_KEY PYTHONPATH=src:. python scripts/run_v2_090i_medium_scenario.py --reset
```

Expected: exit code 1 and stderr contains `ValueError: provider api key env is required`.

---

## Task 5: Real provider opt-in proving test

**Files:**
- Create: `tests/proving/test_v2_090i_medium_scenario.py`

- [ ] **Step 1: Write the real provider test with explicit opt-in**

Create `tests/proving/test_v2_090i_medium_scenario.py` with this content:

```python
from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest


@pytest.mark.skipif(
    not os.environ.get("OPENAI_API_KEY") or os.environ.get("BOARDROOM_RUN_REAL_PROVIDER_PROVING") != "1",
    reason="V2-090I real provider proving requires OPENAI_API_KEY and BOARDROOM_RUN_REAL_PROVIDER_PROVING=1",
)
def test_v2_090i_medium_scenario_real_provider_resets_and_produces_trusted_delivery():
    completed = subprocess.run(
        [sys.executable, "scripts/run_v2_090i_medium_scenario.py", "--reset"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=7200,
    )

    assert completed.returncode == 0, completed.stderr
    report = json.loads(completed.stdout)

    assert report["scenario"] == "v2-090i-resettable-medium-scenario"
    assert report["ticket_ref"] == "ticket.medium.forecast-engine"
    assert report["execution_package_id"] == "exec.ticket.v2-090i.medium-scenario.1"
    assert report["atomic_run_id"].startswith("boardroom-atomic.v2-090i.medium.")
    assert report["provider_transport_kind"] == "real"
    assert report["terminal_event_type"] == "run.completed"
    assert report["provider_turn_completed_count"] >= 1
    assert report["command_exit_codes"]["cmd.check-medium-scenario"] == 0
    assert report["workspace_mutation_paths"]
    assert any(path.startswith("work/forecast_engine/") for path in report["workspace_mutation_paths"])
    assert report["source_lineage_inputs"]
    assert report["success"] is True
```

- [ ] **Step 2: Run the test without opt-in and verify it skips**

Run:

```bash
PYTHONPATH=src:. python -m pytest tests/proving/test_v2_090i_medium_scenario.py -q --tb=short
```

Expected: SKIPPED with reason containing `BOARDROOM_RUN_REAL_PROVIDER_PROVING=1` when the opt-in env var is absent.

- [ ] **Step 3: Run the non-provider V2-090I test set**

Run:

```bash
PYTHONPATH=src:. python -m pytest tests/proving/test_v2_090i_medium_scenario_script.py tests/proving/test_v2_090i_medium_scenario.py -q --tb=short
```

Expected: script tests PASS and real provider test SKIPPED unless the explicit opt-in env var is set.

- [ ] **Step 4: Run the real provider proving test explicitly**

Run:

```bash
set -a; source .env; set +a; BOARDROOM_RUN_REAL_PROVIDER_PROVING=1 PYTHONPATH=src:. python -m pytest tests/proving/test_v2_090i_medium_scenario.py -q --tb=short --basetemp .pytest-tmp-v2090i-medium-real
```

Expected: PASS. Runtime can be long because this uses the real provider and atomic-agent loop.

- [ ] **Step 5: Run the runner manually and inspect JSON output**

Run:

```bash
set -a; source .env; set +a; PYTHONPATH=src:. python scripts/run_v2_090i_medium_scenario.py --reset
```

Expected: exit code 0 and stdout is one JSON object with `success: true`, `provider_transport_kind: "real"`, `cmd.check-medium-scenario: 0`, non-empty `workspace_mutation_paths`, and non-empty `source_lineage_inputs`.

---

## Task 6: Documentation and phase tracking

**Files:**
- Modify: `scripts/README.md`
- Modify: `doc/04-implementation/backlog.md`
- Modify: `doc/04-implementation/acceptance-criteria.md`
- Modify: `doc/05-project-log/2026-06.md`

- [ ] **Step 1: Update `scripts/README.md` with V2-090I runner**

Append this section after the V2-090F script notes:

```markdown
## V2-090I medium scenario runner

`scripts/run_v2_090i_medium_scenario.py` runs the V2-090I Resettable Medium Scenario（可重置中等复杂场景）. It dispatches one real provider-backed atomic-agent implementation ticket（真实模型供应商支撑的原子智能体实施任务） that must create a multi-file `forecast_engine` Python package（Python 包） and CLI（命令行工具） under a marked workspace.

- Default workspace: `.evidence/atomic-agent/v2-090i-medium-scenario-workspace/`
- `--reset`: deletes and recreates only the marked V2-090I workspace; if the directory exists without `.boardroom-v2-090i-workspace.json`, the script fails closed instead of deleting it.
- Provider/runtime/role configuration still comes only from `.env` config paths and `config/boardroom-runtime.example.yaml`, `config/boardroom-providers.example.yaml`, `config/boardroom-roles.example.yaml`.
- Full pytest runs skip the real provider test unless `BOARDROOM_RUN_REAL_PROVIDER_PROVING=1` and `OPENAI_API_KEY` are both set.

PowerShell example:

```powershell
$env:PYTHONPATH='src;.'; $env:BOARDROOM_RUN_REAL_PROVIDER_PROVING='1'; python -m pytest tests/proving/test_v2_090i_medium_scenario.py -q --tb=short
```

POSIX shell example:

```bash
set -a; source .env; set +a; BOARDROOM_RUN_REAL_PROVIDER_PROVING=1 PYTHONPATH=src:. python -m pytest tests/proving/test_v2_090i_medium_scenario.py -q --tb=short --basetemp .pytest-tmp-v2090i-medium-real
```
```

- [ ] **Step 2: Update `doc/04-implementation/backlog.md` Phase 9 status**

Make these focused edits:

1. Change the top `当前未完成工作包` line from V2-090F to V2-090I:

```markdown
**当前未完成工作包**：`V2-090I`（Resettable medium implementation scenario，可重置中等复杂实施场景；完成后再人工评审是否恢复 V2-090F）
```

2. In the current focus paragraph, add V2-090I after V2-090H as the active next step and keep V2-090F blocked:

```markdown
当前处于 V2-090 Tiny Fullstack Blackbox Recovery（微型全栈黑盒整改）；`V2-090A RolePromptHook`（角色提示词钩子）、`V2-090B Closeout all-command coverage`（收尾全命令覆盖）、`V2-090C ServiceRunEvidence`（服务运行证据）、`V2-090D Tiny contract recovery`（微型合同整改）、`V2-090E Live blackbox integration`（真实黑盒集成）、`V2-090G Atomic-agent package/import integration`（原子智能体包导入集成）与 `V2-090H Atomic-agent executor switch`（原子智能体执行器切换）已完成。下一步为 `V2-090I Resettable medium implementation scenario`（可重置中等复杂实施场景），用真实 provider-backed atomic-agent executor（模型供应商支撑原子智能体执行器）证明多文件、文件间依赖、非平凡算法逻辑和真实命令验证。`V2-090F Golden sample rebuild`（黄金样例重建）仍为 BLOCKED：必须先经人工评审 V2-090H 与 V2-090I 真实执行证据后，才允许决定是否恢复 V2-090F 重建 golden sample。
```

3. Update progress table Phase 9 and total counts:

```markdown
| Phase 9：Tiny blackbox recovery | V2-090 | 7 / 9 | 阻塞；V2-090H 完成，V2-090I 为当前专项证明，V2-090F 待人工评审后决定是否恢复 |
| **合计** | **V2-000 ~ V2-090** | **66 / 68** | **V2-090A ~ V2-090E、V2-090G 与 V2-090H 完成，V2-090I TODO，V2-090F BLOCKED，Phase 9 未闭合** |
```

4. Add a new V2-090I work package section near the V2-090H/V2-090F Phase 9 entries:

```markdown
### V2-090I Resettable medium implementation scenario（可重置中等复杂实施场景）

- 状态：TODO
- 目标：构造一个可重置的中等复杂 implementation ticket（实施任务），由真实 provider-backed atomic-agent executor（模型供应商支撑原子智能体执行器）生成多文件 Python package/CLI（Python 包/命令行工具），包含文件间 import（导入依赖）、非平凡数学/算法逻辑、真实 unittest/CLI 验证和可审计 JSON report（报告）。
- 输入文档：`docs/superpowers/specs/2026-06-10-v2-090i-resettable-medium-scenario-design.md`、`config/boardroom-runtime.example.yaml`、`config/boardroom-providers.example.yaml`、`config/boardroom-roles.example.yaml`、`scripts/run_atomic_agent_retry_rate_probe.py`、`scripts/run_tiny_atomic_agent_executor.py`
- 依赖：V2-090G、V2-090H
- 输出文件：`scripts/run_v2_090i_medium_scenario.py`、`tests/proving/test_v2_090i_medium_scenario_script.py`、`tests/proving/test_v2_090i_medium_scenario.py`、`scripts/README.md`
- 必须先写的 negative tests（负例测试）：reset 拒绝删除缺 marker 的既有目录；真实 provider proving test 默认跳过；脚本缺 provider secret 时 fail closed；validator command 拒绝缺文件、缺 import、算法结果错误、unittest/CLI 失败。
- 必须证明的 happy path（正向路径）：显式 opt-in 后，专项测试先 `--reset` 初始化场景，再通过真实 provider-backed atomic-agent executor 生成 `forecast_engine` 多文件 package，运行 `cmd.check-medium-scenario` exit 0，event stream 包含 provider turn facts、workspace mutation、command evidence 和 source lineage input。
- 验收口径：V2-090I 只证明中等复杂单 ticket 可信交付能力；不解除 V2-090F BLOCKED，不生成 closeout passed golden sample。
```

- [ ] **Step 3: Update `doc/04-implementation/acceptance-criteria.md`**

In the Phase 9 checklist section, add this checkbox:

```markdown
- [ ] V2-090I：真实 provider-backed atomic-agent executor（模型供应商支撑原子智能体执行器）可在 reset workspace（重置工作区）中完成中等复杂多文件 Python package/CLI（Python 包/命令行工具），并产生 command evidence（命令证据）、workspace mutation（工作区变更）和 source lineage input（源码来源链输入）。
```

If Phase 9 count text exists near that section, update it from 8 work packages to 9 work packages.

- [ ] **Step 4: Add project log entry after verification**

Append this section to `doc/05-project-log/2026-06.md` after the V2-090H retry-rate entry, replacing the verification command result numbers with the actual results from Task 5:

```markdown
## 2026-06-10 — V2-090I Resettable medium implementation scenario

- 工作包：V2-090I（Resettable medium implementation scenario，可重置中等复杂实施场景）
- 关键产出：新增 `scripts/run_v2_090i_medium_scenario.py`、`tests/proving/test_v2_090i_medium_scenario_script.py`、`tests/proving/test_v2_090i_medium_scenario.py`；同步更新 `scripts/README.md`、`doc/04-implementation/backlog.md`、`doc/04-implementation/acceptance-criteria.md`。
- 关键实现：V2-090I runner（运行脚本）使用 marked workspace（标记工作区）`.evidence/atomic-agent/v2-090i-medium-scenario-workspace/`，`--reset` 只允许删除带 `.boardroom-v2-090i-workspace.json` 的场景目录。ExecutionPackage（执行包）要求真实 provider-backed atomic-agent executor 生成 `forecast_engine` 多文件 Python package/CLI（Python 包/命令行工具），包含 weighted moving average（加权移动平均）、linear regression forecast（线性回归预测）、max drawdown（最大回撤）和 risk score（风险评分）等多步算法逻辑，并通过 `cmd.check-medium-scenario` 外部验证。
- Negative / fail-closed：证明 reset 拒绝缺 marker 目录；缺 provider secret 时脚本 fail closed；真实 provider proving test（真实供应商证明测试）在未设置 `BOARDROOM_RUN_REAL_PROVIDER_PROVING=1` 时默认跳过；validator command（验证命令）独立检查 required files（必需文件）、跨文件 import（导入依赖）、API 算法结果、unittest 和 CLI JSON 输出。
- Happy path：显式 opt-in 后，真实 provider-backed atomic-agent executor 在 reset workspace 中生成多文件 package，运行 `cmd.check-medium-scenario` exit 0，并输出包含 provider turn facts（模型轮次事实）、workspace mutation（工作区变更）、command evidence（命令证据）、source lineage input（源码来源链输入）和 retry rate（重试率）的 JSON report。
- 验证：`PYTHONPATH=src:. python -m pytest tests/proving/test_v2_090i_medium_scenario_script.py tests/proving/test_v2_090i_medium_scenario.py -q --tb=short` 通过（填写实际结果）；`set -a; source .env; set +a; BOARDROOM_RUN_REAL_PROVIDER_PROVING=1 PYTHONPATH=src:. python -m pytest tests/proving/test_v2_090i_medium_scenario.py -q --tb=short --basetemp .pytest-tmp-v2090i-medium-real` 通过（填写实际结果）；`set -a; source .env; set +a; PYTHONPATH=src:. python scripts/run_v2_090i_medium_scenario.py --reset` 返回 exit 0 并生成 V2-090I JSON report。
- 边界说明：V2-090I 不生成 tiny-fullstack golden sample（微型全栈黄金样例），不证明 HTTP/SQLite/frontend integration（HTTP/SQLite/前端集成），也不解除 V2-090F BLOCKED。是否恢复 V2-090F 仍需人工评审 V2-090H 与 V2-090I 真实执行证据。
```

- [ ] **Step 5: Run docs-related sanity checks**

Run:

```bash
git diff --check
```

Expected: PASS with no whitespace errors.

---

## Task 7: Final verification bundle

**Files:**
- All files touched in Tasks 1-6

- [ ] **Step 1: Run focused non-provider tests**

Run:

```bash
PYTHONPATH=src:. python -m pytest tests/proving/test_v2_090i_medium_scenario_script.py tests/proving/test_v2_090i_medium_scenario.py -q --tb=short --basetemp .pytest-tmp-v2090i-non-provider
```

Expected: script tests PASS; real provider test SKIPPED unless opt-in env is set.

- [ ] **Step 2: Run config and atomic executor regression tests**

Run:

```bash
PYTHONPATH=src:. python -m pytest tests/config/test_boardroom_config.py tests/negative/test_boardroom_config_fail_closed.py tests/execution/test_atomic_agent_executor.py tests/negative/test_atomic_agent_executor_fail_closed.py tests/proving/test_tiny_atomic_agent_executor_script.py -q --tb=short --basetemp .pytest-tmp-v2090i-regression
```

Expected: PASS.

- [ ] **Step 3: Run explicit real provider V2-090I proving test**

Run:

```bash
set -a; source .env; set +a; BOARDROOM_RUN_REAL_PROVIDER_PROVING=1 PYTHONPATH=src:. python -m pytest tests/proving/test_v2_090i_medium_scenario.py -q --tb=short --basetemp .pytest-tmp-v2090i-medium-real-final
```

Expected: PASS and stdout/stderr show one passing test. If this fails because the provider cannot complete the medium scenario, keep V2-090I incomplete and preserve stderr/stdout as blocker evidence.

- [ ] **Step 4: Run manual runner command for auditable JSON report**

Run:

```bash
set -a; source .env; set +a; PYTHONPATH=src:. python scripts/run_v2_090i_medium_scenario.py --reset
```

Expected: exit code 0 and one JSON report with `success` true. Save the `atomic_run_id`, `event_stream_ref`, provider turns, action rejections, retry rate, and command exit code for the project log.

- [ ] **Step 5: Run whitespace check**

Run:

```bash
git diff --check
```

Expected: PASS.

- [ ] **Step 6: Review final diff**

Run:

```bash
git diff -- scripts/run_v2_090i_medium_scenario.py tests/proving/test_v2_090i_medium_scenario_script.py tests/proving/test_v2_090i_medium_scenario.py scripts/README.md doc/04-implementation/backlog.md doc/04-implementation/acceptance-criteria.md doc/05-project-log/2026-06.md
```

Expected: diff only contains V2-090I runner/tests/docs updates. No `.env` or provider YAML value changes.

---

## Self-review

### Spec coverage

- Resettable workspace with marker guard is covered by Tasks 1 and 4.
- Medium complexity package/CLI with non-trivial algorithms is covered by Tasks 2 and 3.
- Existing `.env` + runtime/providers/roles YAML as sole provider config source is covered by Task 3 package construction and Task 4 runner settings load.
- Full test skip and explicit real provider opt-in are covered by Task 5.
- Command evidence, workspace mutation, provider turn facts, source lineage, and retry rate report are covered by Tasks 4 and 5.
- Documentation and Phase 9 state tracking are covered by Task 6.
- Final verification commands are covered by Task 7.

### Placeholder scan

No placeholder implementation steps remain. The only “填写实际结果” text appears in the project-log template step because the implementer must replace it with real verification results after running commands; that is not runtime code and is explicitly tied to observed evidence.

### Type consistency

The plan consistently uses:

- `MEDIUM_SCENARIO_COMMAND_ID = "cmd.check-medium-scenario"`
- `ticket_ref = "ticket.medium.forecast-engine"`
- `execution_package_id = "exec.ticket.v2-090i.medium-scenario.1"`
- `scenario = "v2-090i-resettable-medium-scenario"`
- workspace marker `.boardroom-v2-090i-workspace.json`
- `BOARDROOM_RUN_REAL_PROVIDER_PROVING=1` as the real-provider opt-in gate.
