from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest


@pytest.mark.skipif(
    not os.environ.get("OPENAI_API_KEY"),
    reason="real provider retry-rate proving requires OPENAI_API_KEY",
)
def test_atomic_agent_retry_rate_probe_dispatches_three_distinct_tickets():
    completed = subprocess.run(
        [sys.executable, "scripts/run_atomic_agent_retry_rate_probe.py"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=4500,
    )

    assert completed.returncode == 0, completed.stderr
    report = json.loads(completed.stdout)

    assert report["metric"] == "action.rejected / provider.turn.completed"
    assert report["summary"]["ticket_count"] == 3
    assert report["summary"]["provider_turn_completed_count"] >= 3
    assert 0 <= report["summary"]["retry_rate"] <= 1

    results = report["tickets"]
    assert len(results) == 3
    assert {item["ticket_ref"] for item in results} == {
        "ticket.retry-rate.note",
        "ticket.retry-rate.json",
        "ticket.retry-rate.python",
    }

    for result in results:
        assert result["atomic_run_id"].startswith("boardroom-atomic.retry-rate.")
        assert result["event_stream_ref"].endswith(".jsonl")
        assert result["terminal_event_type"] == "run.completed"
        assert result["provider_turn_completed_count"] >= 1
        assert result["action_rejected_count"] >= 0
        assert result["retryable_action_rejected_count"] <= result["action_rejected_count"]
        assert 0 <= result["retry_rate"] <= 1
        assert result["command_exit_codes"]
        assert all(exit_code == 0 for exit_code in result["command_exit_codes"].values())
        assert result["workspace_mutation_paths"]
        assert result["source_lineage_inputs"]
