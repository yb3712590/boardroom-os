from __future__ import annotations

import os
import subprocess
import sys

import pytest


@pytest.mark.skipif(
    not os.environ.get("OPENAI_API_KEY"),
    reason="real provider proving requires OPENAI_API_KEY",
)
def test_tiny_atomic_agent_executor_real_provider_produces_command_evidence():
    completed = subprocess.run(
        [sys.executable, "scripts/run_tiny_atomic_agent_executor.py"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=1500,
    )

    assert completed.returncode == 0, completed.stderr
    assert "atomic_run_id" in completed.stdout
    assert "provider_attempt_ref" in completed.stdout
    assert "source_lineage_inputs" in completed.stdout
