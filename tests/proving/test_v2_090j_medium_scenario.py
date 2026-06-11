from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest


@pytest.mark.skipif(
    not os.environ.get("OPENAI_API_KEY") or os.environ.get("BOARDROOM_RUN_REAL_PROVIDER_PROVING") != "1",
    reason="V2-090J real provider proving requires OPENAI_API_KEY and BOARDROOM_RUN_REAL_PROVIDER_PROVING=1",
)
def test_v2_090j_medium_scenario_real_provider_completes_after_protocol_repair() -> None:
    completed = subprocess.run(
        [sys.executable, "scripts/run_v2_090j_medium_scenario.py", "--reset"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=7200,
    )

    assert completed.returncode == 0, completed.stderr
    report = json.loads(completed.stdout)

    assert report["scenario"] == "v2-090j-action-protocol-medium-scenario"
    assert report["ticket_ref"] == "ticket.medium.forecast-engine.protocol-repair"
    assert report["execution_package_id"] == "exec.ticket.v2-090j.medium-scenario.1"
    assert report["atomic_run_id"].startswith("boardroom-atomic.v2-090j.medium.")
    assert report["provider_transport_kind"] == "real"
    assert report["action_protocol"] == "agent-action-batch-v1"
    assert report["max_actions_per_turn"] > 1
    assert report["checkpoint_max_auto_runs"] >= 1
    assert report["terminal_event_type"] == "run.completed"
    assert report["provider_turn_completed_count"] >= 1
    assert report["command_exit_codes"]["cmd.check-medium-scenario"] == 0
    assert report["workspace_mutation_paths"]
    assert any(path.startswith("work/forecast_engine/") for path in report["workspace_mutation_paths"])
    assert report["source_lineage_inputs"]
    assert report["success"] is True
