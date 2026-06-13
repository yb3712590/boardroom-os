from __future__ import annotations

from boardroom_os.agents.role_prompt_hooks import build_baseline_role_prompt_hook_registry


def _prompt(role_kind: str) -> str:
    return build_baseline_role_prompt_hook_registry().require_by_role_kind(role_kind).prompt_text.lower()


def test_ceo_prompt_requires_multi_role_graph_patch_review() -> None:
    prompt = _prompt("ceo")

    assert "reworkrequest" in prompt
    assert "reworkplan" in prompt
    assert "ticketgraphpatch" in prompt
    assert "architect structural review" in prompt
    assert "checker blocker/evidence review" in prompt
    assert "tester behavioral-probe review" in prompt
    assert "release devops run/env/readiness review" in prompt
    assert "reducer may commit" in prompt


def test_architect_prompt_covers_structural_graph_patch_invariants() -> None:
    prompt = _prompt("architect")

    assert "graph patch" in prompt
    assert "structural" in prompt
    assert "contract" in prompt
    assert "allowed_write_set" in prompt
    assert "source surfaces" in prompt
    assert "runmanifest" in prompt


def test_checker_prompt_covers_blocker_coverage_and_stale_refs() -> None:
    prompt = _prompt("checker")

    assert "blocker coverage" in prompt
    assert "graph patch" in prompt
    assert "stale evidence" in prompt
    assert "old run ids" in prompt
    assert "fresh verified evidence" in prompt


def test_tester_prompt_covers_behavioral_probe_mismatch() -> None:
    prompt = _prompt("tester")

    assert "behavioral probes" in prompt
    assert "response shape" in prompt
    assert "contract/probe/implementation mismatch" in prompt
    assert "fix implementation" in prompt
    assert "fix contract or probe" in prompt


def test_release_devops_prompt_covers_run_env_readiness_review() -> None:
    prompt = _prompt("release_devops")

    assert "runmanifest" in prompt
    assert "environment mapping" in prompt
    assert "readiness" in prompt
    assert "service startup" in prompt
    assert "sample promotion" in prompt
    assert "run/env/readiness" in prompt


def test_closeout_prompt_covers_same_run_fact_chain() -> None:
    prompt = _prompt("closeout")

    assert "same-run" in prompt
    assert "fact-chain" in prompt
    assert "old run refs" in prompt
    assert "old evidence" in prompt
    assert "closeoutgate" in prompt
