from __future__ import annotations

from pathlib import Path

from tests.live._autopilot_live_harness import (
    LiveScenarioDefinition,
    run_live_scenario_with_provider_payload,
)
from tests.live._config import LiveScenarioConfig, load_live_scenario_config
from tests.live._scenario_profiles import build_assert_outcome


def build_live_scenario(config: LiveScenarioConfig) -> LiveScenarioDefinition:
    return LiveScenarioDefinition(
        slug=config.scenario.slug,
        description=config.scenario.description,
        goal=config.scenario.goal,
        constraints=list(config.scenario.constraints),
        force_requirement_elicitation=config.scenario.force_requirement_elicitation,
        budget_cap=config.scenario.budget_cap,
        workflow_profile=config.scenario.workflow_profile,
        assert_outcome=build_assert_outcome(config.assertions),
    )


def run_configured_live_scenario(
    config_path: Path,
    *,
    clean: bool = True,
    max_ticks: int | None = None,
    timeout_sec: int | None = None,
    seed: int | None = None,
    scenario_root: Path | None = None,
) -> dict[str, object]:
    config = load_live_scenario_config(config_path)
    scenario = build_live_scenario(config)
    return run_live_scenario_with_provider_payload(
        scenario,
        config.build_runtime_provider_payload(),
        clean=clean,
        max_ticks=max_ticks if max_ticks is not None else config.runtime.max_ticks,
        timeout_sec=timeout_sec if timeout_sec is not None else config.runtime.timeout_sec,
        seed=seed if seed is not None else config.runtime.seed,
        scenario_root=scenario_root,
    )
