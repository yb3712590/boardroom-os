from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.constants import INCIDENT_TYPE_CEO_SHADOW_PIPELINE_FAILED
from tests.live._autopilot_live_harness import (
    LiveScenarioDefinition,
    ScenarioPaths,
    build_scenario_paths as _build_scenario_paths,
    run_cli,
    run_live_scenario as _run_live_scenario,
)
from tests.live._scenario_profiles import (
    MINIMALIST_BOOK_TRACKER_CONSTRAINTS as SCENARIO_CONSTRAINTS,
    MINIMALIST_BOOK_TRACKER_GOAL as SCENARIO_GOAL,
)

DEFAULT_SCENARIO_SLUG = "library_management_autopilot_smoke"


def build_scenario_paths(scenario_root: Path | None = None) -> ScenarioPaths:
    return _build_scenario_paths(DEFAULT_SCENARIO_SLUG, scenario_root)


def _json_corpus(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).lower()
    except TypeError:
        return str(value).lower()


def _checkpoint_has_no_actions_built_signal(
    *,
    snapshot: dict[str, Any],
    open_incidents: list[dict[str, Any]],
) -> bool:
    terminal_corpus = _json_corpus(snapshot.get("terminals") or {})
    if "no_actions_built" in terminal_corpus:
        return True
    incident_corpus = _json_corpus(open_incidents)
    return "no_actions_built" in incident_corpus


def _checkpoint_has_dependency_gate_failure(snapshot: dict[str, Any]) -> bool:
    for ticket in list(snapshot.get("tickets") or []):
        if str(ticket.get("last_failure_kind") or "").strip() == "DEPENDENCY_GATE_UNHEALTHY":
            return True
    return False


def _open_ceo_shadow_recovery_incidents(repository, workflow_id: str) -> list[dict[str, Any]]:
    if repository is None:
        return []
    incidents = [
        incident
        for incident in repository.list_open_incidents()
        if str(incident.get("workflow_id") or "").strip() == workflow_id
    ]
    return [
        incident
        for incident in incidents
        if str(incident.get("incident_type") or "").strip() == INCIDENT_TYPE_CEO_SHADOW_PIPELINE_FAILED
        and str(incident.get("status") or "").strip().upper() in {"OPEN", "RECOVERING"}
    ]


def _assert_library_check_stage_checkpoint(
    paths: ScenarioPaths | None,
    repository,
    workflow_id: str,
    snapshot: dict[str, Any],
) -> dict[str, Any] | None:
    workflow = snapshot.get("workflow") or {}
    if str(workflow.get("status") or "").strip().upper() != "EXECUTING":
        return None
    if str(workflow.get("current_stage") or "").strip() != "check":
        return None

    open_ceo_shadow_incidents = _open_ceo_shadow_recovery_incidents(repository, workflow_id)
    if open_ceo_shadow_incidents:
        return None
    if _checkpoint_has_dependency_gate_failure(snapshot):
        return None
    if _checkpoint_has_no_actions_built_signal(
        snapshot=snapshot,
        open_incidents=open_ceo_shadow_incidents,
    ):
        return None

    return {
        "workflow_stage": "check",
        "checkpoint_reason": "entered_check_without_it006_failure_signals",
        "open_ceo_shadow_recovery_incident_count": 0,
        "dependency_gate_unhealthy_ticket_count": 0,
        "ticket_count": len(list(snapshot.get("tickets") or [])),
    }


def _assert_smoke_outcome(
    paths: ScenarioPaths,
    repository,
    workflow_id: str,
    common: dict[str, Any],
) -> dict[str, Any]:
    raise AssertionError("Library smoke should exit through checkpoint mode before full completion.")


SCENARIO = LiveScenarioDefinition(
    slug=DEFAULT_SCENARIO_SLUG,
    description="Run the library management 006 checkpoint smoke scenario.",
    goal=SCENARIO_GOAL,
    constraints=list(SCENARIO_CONSTRAINTS),
    assert_outcome=_assert_smoke_outcome,
    checkpoint_assertion=_assert_library_check_stage_checkpoint,
    checkpoint_label="library_check_stage_gate",
)


def run_live_scenario(
    *,
    clean: bool = True,
    max_ticks: int = 180,
    timeout_sec: int = 7200,
    seed: int = 17,
    scenario_root: Path | None = None,
) -> dict[str, Any]:
    return _run_live_scenario(
        SCENARIO,
        clean=clean,
        max_ticks=max_ticks,
        timeout_sec=timeout_sec,
        seed=seed,
        scenario_root=scenario_root,
    )


def main(argv: list[str] | None = None) -> int:
    return run_cli(SCENARIO, argv)


if __name__ == "__main__":
    raise SystemExit(main())
