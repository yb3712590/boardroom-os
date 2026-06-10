from __future__ import annotations

from scripts.run_tiny_atomic_agent_executor import _new_run_id


def test_tiny_atomic_agent_executor_script_generates_run_scoped_ids():
    first = _new_run_id("boardroom-atomic")
    second = _new_run_id("boardroom-atomic")

    assert first.startswith("boardroom-atomic.tiny-proving.")
    assert second.startswith("boardroom-atomic.tiny-proving.")
    assert first != second
