from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import shutil
import sys
import traceback
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
from boardroom_os.execution.atomic_executor import (
    AtomicAgentExecutor,
    AtomicAgentRuntimeFactory,
    AtomicExecutionRequest,
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
        reasoning_effort=provider_config.reasoning_effort,
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
            "Every provider response must be exactly one valid JSON object representing one action. "
            "Do not output Markdown, code fences, explanations, arrays, multiple JSON objects, or action_envelope. "
            "Use top-level action_id, action, reason_summary, and input fields for every action. "
            "The final submit_result action must be exactly one JSON object with those same top-level fields. "
            "The final input field must contain summary, produced_paths, and evidence_refs. "
            f"produced_paths must be exactly {produced_paths_json}; evidence_refs must be [\"{MEDIUM_SCENARIO_COMMAND_ID}\"]."
        ),
        context_refs=(ContextRef(value="context.v2-090i.medium-scenario"),),
        constraints=(
            "Only write under work/.",
            "Use only the Python standard library; do not install dependencies.",
            "Do not implement placeholder arithmetic; each public function must perform the specified multi-step calculation.",
            "risk.py must import statistics.py rather than duplicating all statistics functions.",
            "Return only one JSON action object per turn; never concatenate multiple action objects in one response.",
            "Do not use action_envelope for any action.",
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


def run_medium_scenario(*, reset: bool) -> dict[str, Any]:
    settings = _settings_with_medium_scenario_budget(load_boardroom_settings(
        BoardroomConfigPaths(
            runtime_config=Path(os.environ.get("BOARDROOM_RUNTIME_CONFIG", "config/boardroom-runtime.example.yaml")),
            providers_config=Path(os.environ.get("BOARDROOM_PROVIDERS_CONFIG", "config/boardroom-providers.example.yaml")),
            roles_config=Path(os.environ.get("BOARDROOM_ROLES_CONFIG", "config/boardroom-roles.example.yaml")),
        ),
        env_values=dict(os.environ),
    ))
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


def _settings_with_medium_scenario_budget(settings: Any) -> Any:
    role_slots = []
    for slot in settings.roles.role_slots:
        if slot.seat_ref == "seat.worker.implementation":
            default_tools = tuple(tool for tool in slot.default_tools if tool != "apply_patch")
            role_slots.append(
                slot.model_copy(
                    update={
                        "default_tools": default_tools,
                        "skill_refs": tuple(ref for ref in slot.skill_refs if ref != "skill.filesystem.patch"),
                        "budgets_override": {
                            **slot.budgets_override,
                            "max_steps": settings.runtime.atomic_agent.budget_caps.max_steps,
                            "max_parse_failures": settings.runtime.atomic_agent.budget_caps.max_parse_failures,
                        }
                    }
                )
            )
        else:
            role_slots.append(slot)
    return settings.model_copy(
        update={
            "roles": settings.roles.model_copy(update={"role_slots": tuple(role_slots)})
        }
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
    source_lineage_inputs: tuple[dict[str, Any], ...] | tuple[str, ...],
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


if __name__ == "__main__":
    raise SystemExit(main())
