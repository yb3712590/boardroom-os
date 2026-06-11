# V2-090F PRD-to-Delivery Agent Team Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a V2-090F entrypoint that accepts a short PRD（简短产品需求） and proves the agent team（智能体团队） can autonomously plan, implement, test, check, and close out a tiny fullstack delivery without pre-split implementation tickets from the runner.

**Architecture:** Add a PRD-driven agent-team runner（智能体团队运行器） with a frozen config/role-context baseline（配置/角色上下文基线）. The runner starts CEO/Architect/Worker/Tester/Checker/Closeout seats（席位）, records each role's `RolePromptHook`（角色提示词钩子） and `skill_context`（技能上下文）, lets the team generate contracts and a ticket graph, then uses Boardroom gates to verify atomic execution, command/service/live evidence, source lineage, and closeout. `scripts/build_tiny_closeout_sample.py` remains a public wrapper, but it must not predefine the ticket graph or call provider during `--check`.

**Tech Stack:** Python 3.12, pytest, pydantic, Boardroom OS config/execution/evidence/closeout modules, external `atomic-agent`, existing RolePromptHook/RoleProfile/ExecutionPackage models, standard-library tiny fullstack acceptance probes.

---

## File Structure

### Create

- `examples/directives/tiny-fullstack-prd.md` — short PRD input（短需求输入） for V2-090F proving.
- `examples/directives/v2-090f-reference-examples.md` — bounded reference examples（受限参考示例） for contracts and ticket graph shape; no fixed ticket graph.
- `config/boardroom-runtime.v2-090f.yaml` — V2-090F high-budget runtime baseline（高预算运行时基线）.
- `config/boardroom-providers.v2-090f.yaml` — V2-090F high-timeout provider baseline（高超时供应商基线）.
- `config/boardroom-roles.v2-090f.yaml` — V2-090F required agent team seats（必需智能体团队席位）.
- `src/boardroom_os/proving/v2_090f_prd_agent_team.py` — PRD runner domain helpers: baseline lock, required seat validation, role-context capture, autonomy gate, sample manifest checks.
- `scripts/run_v2_090f_prd_agent_team.py` — explicit V2-090F real-provider runner.
- `tests/negative/test_v2_090f_agent_team_fail_closed.py` — fail-closed tests for missing roles, worker-seat reuse, hook/skill mismatch, pre-split ticket graph, ProviderExecutor reuse, and missing evidence.
- `tests/proving/test_v2_090f_prd_agent_team_script.py` — non-provider tests for PRD loading, reset guard, baseline lock, `--check` no-write, and sample tree checks.
- `tests/proving/test_v2_090f_prd_agent_team_real.py` — default-skipped real provider proving test.

### Modify

- `config/boardroom-roles.example.yaml` — do not use as the V2-090F baseline; keep example docs pointing to the dedicated config if needed.
- `config/boardroom-runtime.example.yaml` — do not raise generic budgets for V2-090F; dedicated runtime config owns the high-budget baseline.
- `src/boardroom_os/execution/atomic_agent.py` — support role-specific invocation requirements（按角色区分的调用要求） so non-worker roles are not forced to produce implementation workspace mutations.
- `scripts/build_tiny_closeout_sample.py` — delegate build/check to the PRD agent-team runner and check helpers.
- `examples/README.md`, `scripts/README.md`, `doc/04-implementation/backlog.md`, `doc/04-implementation/acceptance-criteria.md`, `doc/05-project-log/2026-06.md` — update status and usage after implementation.

### Inspect Only

- `src/boardroom_os/agents/role_prompt_hooks.py` — baseline role prompt hook registry.
- `src/boardroom_os/agents/profiles.py` — role profile and hook category matching.
- `src/boardroom_os/config/boardroom.py` — role slot config and resolved budget behavior.
- `src/boardroom_os/execution/package.py` — `ExecutionPackage.role_prompt_hook` and seat fields.
- `src/boardroom_os/execution/atomic_executor.py` — worker implementation execution boundary.
- `src/boardroom_os/evidence/verifier.py` — provider attempt hook verification.

---

## Task 0: Baseline and Drift Check

**Files:**
- Inspect only: `config/boardroom-runtime.example.yaml`
- Inspect only: `config/boardroom-providers.example.yaml`
- Inspect only: `config/boardroom-roles.example.yaml`
- Inspect only: `src/boardroom_os/execution/atomic_agent.py`
- Inspect only: `doc/04-implementation/acceptance-criteria.md`

- [ ] **Step 1: Record working tree state**

```bash
git status --short --branch
```

Expected: record pre-existing dirty files. Do not revert unrelated user changes.

- [ ] **Step 2: Verify V2-090F remains blocked**

```bash
rg -n "\\[ \\].*V2-090F|V2-090F.*BLOCKED|AC-V2-PACKAGE-001 / AC-V2-CLOSEOUT" doc/04-implementation/acceptance-criteria.md doc/04-implementation/backlog.md
```

Expected: V2-090F is still unchecked or blocked before implementation.

- [ ] **Step 3: Inspect current role slots**

```bash
python - <<'PY'
from pathlib import Path
import yaml
data = yaml.safe_load(Path("config/boardroom-roles.example.yaml").read_text())
for slot in data["role_slots"]:
    print(slot["seat_ref"], slot["role_profile_ref"], slot["role_category"], slot["skill_refs"], slot["default_tools"])
PY
```

Expected before Task 2: likely only worker seats exist. Record this as the reason V2-090F needs dedicated config files rather than mutating the generic example config.

---

## Task 1: Short PRD Input, Reference Examples, and Reset Guard

**Files:**
- Create: `examples/directives/tiny-fullstack-prd.md`
- Create: `examples/directives/v2-090f-reference-examples.md`
- Create: `src/boardroom_os/proving/v2_090f_prd_agent_team.py`
- Create: `tests/proving/test_v2_090f_prd_agent_team_script.py`

- [ ] **Step 1: Add short PRD file**

Create `examples/directives/tiny-fullstack-prd.md`:

```markdown
# Tiny Library Checkout PRD

Build a tiny library checkout web app. Users can add books, list books,
checkout and return a book, delete a book, and see the UI update from a
real backend. Persist data in SQLite. Use a standard-library Python backend
and a static frontend. Provide tests and run instructions.
```

- [ ] **Step 2: Add bounded reference examples**

Create `examples/directives/v2-090f-reference-examples.md`:

```markdown
# V2-090F Reference Examples

These examples describe acceptance and evidence shape only. They must not
predefine implementation ticket IDs, execution order, or source file names.

Acceptance examples:
- The backend service must expose real HTTP behavior for create, list,
  checkout, return, and delete.
- The frontend must call the real backend during live blackbox verification.
- SQLite persistence must be proven through HTTP behavior, not function-only tests.

Ticket graph shape examples:
- Tickets should declare owner seat, dependencies, acceptance refs,
  evidence obligations, source surfaces, and allowed write sets.
- Implementation tickets must be generated by the agent team from the PRD.
```

- [ ] **Step 3: Add PRD/reset tests**

Create `tests/proving/test_v2_090f_prd_agent_team_script.py`:

```python
from __future__ import annotations

from pathlib import Path

import pytest


def test_v2_090f_loads_non_empty_short_prd(tmp_path: Path) -> None:
    from boardroom_os.proving.v2_090f_prd_agent_team import load_v2_090f_prd

    prd = tmp_path / "prd.md"
    prd.write_text("Build a tiny checkout app.", encoding="utf-8")

    loaded = load_v2_090f_prd(prd)

    assert loaded.text == "Build a tiny checkout app."
    assert loaded.sha256.startswith("sha256:")


def test_v2_090f_rejects_empty_prd(tmp_path: Path) -> None:
    from boardroom_os.proving.v2_090f_prd_agent_team import load_v2_090f_prd

    prd = tmp_path / "empty.md"
    prd.write_text("   \n", encoding="utf-8")

    with pytest.raises(ValueError, match="PRD must not be empty"):
        load_v2_090f_prd(prd)


def test_v2_090f_reset_rejects_unmarked_workspace(tmp_path: Path) -> None:
    from boardroom_os.proving.v2_090f_prd_agent_team import reset_v2_090f_workspace

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "user.txt").write_text("keep", encoding="utf-8")

    with pytest.raises(ValueError, match="missing V2-090F marker"):
        reset_v2_090f_workspace(workspace)


def test_v2_090f_reference_examples_do_not_define_ticket_refs() -> None:
    text = Path("examples/directives/v2-090f-reference-examples.md").read_text(encoding="utf-8")

    assert "ticket.tiny.backend-api" not in text
    assert "ticket.tiny.frontend-ui" not in text
    assert "ticket.tiny.integration-evidence" not in text
```

- [ ] **Step 4: Run tests and verify they fail**

```bash
PYTHONPATH=src:. python -m pytest tests/proving/test_v2_090f_prd_agent_team_script.py -q --tb=short
```

Expected: FAIL because `boardroom_os.proving.v2_090f_prd_agent_team` is missing.

- [ ] **Step 5: Implement PRD and reset helpers**

Create `src/boardroom_os/proving/v2_090f_prd_agent_team.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import shutil


V2_090F_MARKER = ".boardroom-v2-090f-workspace.json"


@dataclass(frozen=True)
class LoadedPrd:
    path: str
    text: str
    sha256: str


def load_v2_090f_prd(path: Path) -> LoadedPrd:
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        raise ValueError("PRD must not be empty")
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return LoadedPrd(path=path.as_posix(), text=text, sha256=f"sha256:{digest}")


def reset_v2_090f_workspace(workspace: Path) -> None:
    workspace = workspace.resolve()
    marker = workspace / V2_090F_MARKER
    if workspace.exists():
        if not marker.is_file():
            raise ValueError("missing V2-090F marker; refusing to reset workspace")
        shutil.rmtree(workspace)
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "00-boardroom").mkdir()
    (workspace / "work").mkdir()
    marker.write_text(
        json.dumps({"scenario": "V2-090F", "runner": "prd-agent-team"}, sort_keys=True),
        encoding="utf-8",
    )
```

- [ ] **Step 6: Run tests**

```bash
PYTHONPATH=src:. python -m pytest tests/proving/test_v2_090f_prd_agent_team_script.py -q --tb=short --basetemp .pytest-tmp-v2090f-prd-reset
```

Expected: PASS.

---

## Task 2: Dedicated High-Budget Config and Required Agent Team Role Slots

**Files:**
- Create: `config/boardroom-runtime.v2-090f.yaml`
- Create: `config/boardroom-providers.v2-090f.yaml`
- Create: `config/boardroom-roles.v2-090f.yaml`
- Modify: `src/boardroom_os/proving/v2_090f_prd_agent_team.py`
- Create: `tests/negative/test_v2_090f_agent_team_fail_closed.py`

- [ ] **Step 1: Add required-seat fail-closed tests**

Create `tests/negative/test_v2_090f_agent_team_fail_closed.py`:

```python
from __future__ import annotations

import pytest


def _slot(
    seat_ref: str,
    role_profile_ref: str,
    role_category: str,
    skill_refs: tuple[str, ...] = ("skill.command.test",),
    default_tools: tuple[str, ...] = ("read_file", "submit_result"),
    provider_profile_ref: str = "provider.openai-compatible.v2-090f-primary",
    budget_profile_ref: str = "agent_team.v2_090f.fullstack",
) -> dict[str, object]:
    return {
        "seat_ref": seat_ref,
        "role_profile_ref": role_profile_ref,
        "role_category": role_category,
        "provider_profile_ref": provider_profile_ref,
        "skill_refs": skill_refs,
        "default_tools": default_tools,
        "budget_profile_ref": budget_profile_ref,
    }


def test_v2_090f_rejects_missing_required_agent_team_seat() -> None:
    from boardroom_os.proving.v2_090f_prd_agent_team import validate_required_agent_team_slots

    with pytest.raises(ValueError, match="missing required agent team seats"):
        validate_required_agent_team_slots([_slot("seat.worker.implementation", "role.worker.implementation", "worker")])


def test_v2_090f_rejects_all_roles_reusing_worker_seat() -> None:
    from boardroom_os.proving.v2_090f_prd_agent_team import validate_required_agent_team_slots

    slots = [
        _slot(required, "role.worker.implementation", "worker", default_tools=("read_file", "write_file", "run_command", "submit_result"))
        for required in (
            "seat.ceo.delivery",
            "seat.architect.delivery",
            "seat.worker.implementation",
            "seat.tester.integration",
            "seat.checker.acceptance",
            "seat.closeout.package",
        )
    ]

    with pytest.raises(ValueError, match="required seats must not all reuse worker role profile"):
        validate_required_agent_team_slots(slots)


def test_v2_090f_rejects_non_worker_reusing_worker_role_profile() -> None:
    from boardroom_os.proving.v2_090f_prd_agent_team import validate_required_agent_team_slots

    slots = [
        _slot("seat.ceo.delivery", "role.worker.implementation", "governance"),
        _slot("seat.architect.delivery", "role.architecture.lead", "architecture"),
        _slot("seat.worker.implementation", "role.worker.implementation", "worker", default_tools=("read_file", "write_file", "run_command", "submit_result")),
        _slot("seat.tester.integration", "role.verification.tester", "verification"),
        _slot("seat.checker.acceptance", "role.verification.checker", "verification"),
        _slot("seat.closeout.package", "role.audit.closeout", "audit"),
    ]

    with pytest.raises(ValueError, match="non-worker seat must not reuse worker role profile"):
        validate_required_agent_team_slots(slots)


def test_v2_090f_rejects_non_high_budget_or_provider_profile() -> None:
    from boardroom_os.proving.v2_090f_prd_agent_team import validate_required_agent_team_slots

    slots = [
        _slot("seat.ceo.delivery", "role.governance.ceo", "governance", provider_profile_ref="provider.openai-compatible.primary"),
        _slot("seat.architect.delivery", "role.architecture.lead", "architecture"),
        _slot("seat.worker.implementation", "role.worker.implementation", "worker", default_tools=("read_file", "write_file", "run_command", "submit_result")),
        _slot("seat.tester.integration", "role.verification.tester", "verification"),
        _slot("seat.checker.acceptance", "role.verification.checker", "verification"),
        _slot("seat.closeout.package", "role.audit.closeout", "audit", budget_profile_ref="worker.implementation.default"),
    ]

    with pytest.raises(ValueError, match="required seats must use V2-090F high-budget provider baseline"):
        validate_required_agent_team_slots(slots)


def test_v2_090f_rejects_non_worker_source_write_tools() -> None:
    from boardroom_os.proving.v2_090f_prd_agent_team import validate_required_agent_team_slots

    slots = [
        _slot("seat.ceo.delivery", "role.governance.ceo", "governance"),
        _slot("seat.architect.delivery", "role.architecture.lead", "architecture"),
        _slot("seat.worker.implementation", "role.worker.implementation", "worker", default_tools=("read_file", "write_file", "run_command", "submit_result")),
        _slot("seat.tester.integration", "role.verification.tester", "verification"),
        _slot("seat.checker.acceptance", "role.verification.checker", "verification", default_tools=("read_file", "write_file", "submit_result")),
        _slot("seat.closeout.package", "role.audit.closeout", "audit"),
    ]

    with pytest.raises(ValueError, match="non-worker role must not have implementation write tools"):
        validate_required_agent_team_slots(slots)
```

- [ ] **Step 2: Run tests and verify they fail**

```bash
PYTHONPATH=src:. python -m pytest tests/negative/test_v2_090f_agent_team_fail_closed.py -q --tb=short
```

Expected: FAIL because `validate_required_agent_team_slots` is missing.

- [ ] **Step 3: Implement required-seat validator**

Add to `src/boardroom_os/proving/v2_090f_prd_agent_team.py`:

```python
REQUIRED_AGENT_TEAM_SEATS = (
    "seat.ceo.delivery",
    "seat.architect.delivery",
    "seat.worker.implementation",
    "seat.tester.integration",
    "seat.checker.acceptance",
    "seat.closeout.package",
)


def validate_required_agent_team_slots(slots: list[dict[str, object]] | tuple[dict[str, object], ...]) -> None:
    by_seat = {str(slot["seat_ref"]): slot for slot in slots}
    missing = [seat for seat in REQUIRED_AGENT_TEAM_SEATS if seat not in by_seat]
    if missing:
        raise ValueError("missing required agent team seats: " + ", ".join(missing))
    role_profile_refs = {str(by_seat[seat]["role_profile_ref"]) for seat in REQUIRED_AGENT_TEAM_SEATS}
    if role_profile_refs == {"role.worker.implementation"}:
        raise ValueError("required seats must not all reuse worker role profile")
    for seat in REQUIRED_AGENT_TEAM_SEATS:
        slot = by_seat[seat]
        if seat != "seat.worker.implementation" and slot["role_profile_ref"] == "role.worker.implementation":
            raise ValueError("non-worker seat must not reuse worker role profile")
        if (
            slot["provider_profile_ref"] != "provider.openai-compatible.v2-090f-primary"
            or slot["budget_profile_ref"] != "agent_team.v2_090f.fullstack"
        ):
            raise ValueError("required seats must use V2-090F high-budget provider baseline")
    for seat, slot in by_seat.items():
        if seat == "seat.worker.implementation":
            continue
        tools = set(slot.get("default_tools", ()))
        if {"write_file", "apply_patch"}.intersection(tools):
            raise ValueError("non-worker role must not have implementation write tools")
```

- [ ] **Step 4: Create dedicated runtime config**

Create `config/boardroom-runtime.v2-090f.yaml` by copying `config/boardroom-runtime.example.yaml` and adding a high-budget profile:

```yaml
budget_profiles:
  agent_team.v2_090f.fullstack:
    max_steps: 240
    max_parse_failures: 6
    max_observation_chars: 64000
    max_wall_seconds: 10800
    max_actions_per_turn: 8
```

Keep `retry_requires_no_workspace_mutation: true`. Do not enable retry after workspace mutation.

- [ ] **Step 5: Create dedicated providers config**

Create `config/boardroom-providers.v2-090f.yaml` by copying the primary provider and raising timeout only in this dedicated file:

```yaml
provider_profile_id: provider.openai-compatible.v2-090f-primary
model: gpt-5.5
reasoning_effort: high
context_window_tokens: 400000
max_output_tokens: 128000
stream_idle_timeout_seconds: 180
total_timeout_seconds: 900
```

The exact timeout values may be higher if reviewed, but they must live in this YAML and be recorded in the baseline hash.

- [ ] **Step 6: Create dedicated roles config**

Create `config/boardroom-roles.v2-090f.yaml` with required seats. All seats must use `provider.openai-compatible.v2-090f-primary` and `agent_team.v2_090f.fullstack`; each seat must have distinct role profile and skill refs. Worker keeps `write_file/run_command/submit_result`; non-worker seats start read-only plus `submit_result`, except Closeout can write audit/closeout artifacts only after role-specific tool policy exists.

- [ ] **Step 7: Add config test for dedicated YAML**

Append to `tests/proving/test_v2_090f_prd_agent_team_script.py`:

```python
def test_v2_090f_roles_baseline_defines_required_agent_team_seats() -> None:
    import yaml
    from boardroom_os.proving.v2_090f_prd_agent_team import validate_required_agent_team_slots

    data = yaml.safe_load(open("config/boardroom-roles.v2-090f.yaml", encoding="utf-8"))

    validate_required_agent_team_slots(data["role_slots"])
```

- [ ] **Step 8: Add budget baseline test**

Append:

```python
def test_v2_090f_runtime_baseline_uses_high_budget_profile() -> None:
    import yaml

    runtime = yaml.safe_load(open("config/boardroom-runtime.v2-090f.yaml", encoding="utf-8"))
    budget = runtime["atomic_agent"]["budget_profiles"]["agent_team.v2_090f.fullstack"]

    assert budget["max_steps"] == 240
    assert budget["max_parse_failures"] == 6
    assert budget["max_observation_chars"] == 64000
    assert budget["max_wall_seconds"] == 10800
    assert budget["max_actions_per_turn"] == 8
    assert runtime["atomic_agent"]["execution_policy"]["retry_requires_no_workspace_mutation"] is True
```

- [ ] **Step 9: Run tests**

```bash
PYTHONPATH=src:. python -m pytest tests/negative/test_v2_090f_agent_team_fail_closed.py tests/proving/test_v2_090f_prd_agent_team_script.py -q --tb=short --basetemp .pytest-tmp-v2090f-role-slots
```

Expected: PASS.

---

## Task 3: Role Context and Skill Context Baseline

**Files:**
- Modify: `src/boardroom_os/proving/v2_090f_prd_agent_team.py`
- Modify: `tests/negative/test_v2_090f_agent_team_fail_closed.py`
- Modify: `tests/proving/test_v2_090f_prd_agent_team_script.py`

- [ ] **Step 1: Add role-context mismatch tests**

Append:

```python
def test_v2_090f_rejects_role_context_missing_hook_snapshot() -> None:
    from boardroom_os.proving.v2_090f_prd_agent_team import validate_role_invocation_context

    with pytest.raises(ValueError, match="role_context must include RolePromptHook"):
        validate_role_invocation_context(
            seat_ref="seat.ceo.delivery",
            expected_skill_refs=("skill.governance.ceo",),
            invocation_role_context="CEO prompt without audit fields",
            invocation_skill_context={"skill_refs": ["skill.governance.ceo"]},
        )


def test_v2_090f_rejects_skill_context_mismatch() -> None:
    from boardroom_os.proving.v2_090f_prd_agent_team import validate_role_invocation_context

    role_context = "\n".join(
        (
            "RolePromptHook ref: role-prompt-hook.baseline.ceo.v1",
            "RolePromptHook version: v1",
            "RolePromptHook sha256: sha256:abc",
            "CEO prompt text",
        )
    )

    with pytest.raises(ValueError, match="skill_context.skill_refs mismatch"):
        validate_role_invocation_context(
            seat_ref="seat.ceo.delivery",
            expected_skill_refs=("skill.governance.ceo",),
            invocation_role_context=role_context,
            invocation_skill_context={"skill_refs": ["skill.command.test"]},
        )
```

- [ ] **Step 2: Run tests and verify they fail**

```bash
PYTHONPATH=src:. python -m pytest tests/negative/test_v2_090f_agent_team_fail_closed.py -q --tb=short
```

Expected: FAIL because `validate_role_invocation_context` is missing.

- [ ] **Step 3: Implement context validator**

Add:

```python
def validate_role_invocation_context(
    *,
    seat_ref: str,
    expected_skill_refs: tuple[str, ...],
    invocation_role_context: str,
    invocation_skill_context: dict[str, object],
) -> None:
    required_fragments = (
        "RolePromptHook ref:",
        "RolePromptHook version:",
        "RolePromptHook sha256:",
    )
    if any(fragment not in invocation_role_context for fragment in required_fragments):
        raise ValueError(f"role_context must include RolePromptHook snapshot for {seat_ref}")
    actual = tuple(invocation_skill_context.get("skill_refs", ()))
    if actual != expected_skill_refs:
        raise ValueError("skill_context.skill_refs mismatch")
```

- [ ] **Step 4: Add baseline report test**

Append to `tests/proving/test_v2_090f_prd_agent_team_script.py`:

```python
def test_v2_090f_baseline_report_records_required_seats(tmp_path: Path) -> None:
    from boardroom_os.proving.v2_090f_prd_agent_team import write_v2_090f_baseline_report

    report = write_v2_090f_baseline_report(
        output_path=tmp_path / "baseline.json",
        prd_sha256="sha256:prd",
        runtime_config_hash="sha256:runtime",
        providers_config_hash="sha256:providers",
        roles_config_hash="sha256:roles",
        seats={
            "seat.ceo.delivery": {"role_profile_ref": "role.governance.ceo", "skill_refs": ["skill.governance.ceo"]},
            "seat.architect.delivery": {"role_profile_ref": "role.architecture.lead", "skill_refs": ["skill.architecture.lead"]},
            "seat.worker.implementation": {"role_profile_ref": "role.worker.implementation", "skill_refs": ["skill.command.test"]},
            "seat.tester.integration": {"role_profile_ref": "role.verification.tester", "skill_refs": ["skill.verification.tester"]},
            "seat.checker.acceptance": {"role_profile_ref": "role.verification.checker", "skill_refs": ["skill.verification.checker"]},
            "seat.closeout.package": {"role_profile_ref": "role.audit.closeout", "skill_refs": ["skill.audit.closeout"]},
        },
    )

    assert report["prd_sha256"] == "sha256:prd"
    assert set(report["seats"]) == {
        "seat.ceo.delivery",
        "seat.architect.delivery",
        "seat.worker.implementation",
        "seat.tester.integration",
        "seat.checker.acceptance",
        "seat.closeout.package",
    }
```

- [ ] **Step 5: Implement baseline report writer**

Add deterministic JSON writer that sorts keys and returns the payload.

- [ ] **Step 6: Run tests**

```bash
PYTHONPATH=src:. python -m pytest tests/negative/test_v2_090f_agent_team_fail_closed.py tests/proving/test_v2_090f_prd_agent_team_script.py -q --tb=short --basetemp .pytest-tmp-v2090f-role-context
```

Expected: PASS.

---

## Task 4: Role-Specific Invocation Requirements

**Files:**
- Modify: `src/boardroom_os/execution/atomic_agent.py`
- Modify: `tests/execution/test_atomic_agent_invocation_compiler.py`
- Modify: `tests/negative/test_v2_090f_agent_team_fail_closed.py`

- [ ] **Step 1: Add non-worker compiler tests**

Add tests proving:

- `seat.worker.implementation` still requires `run_command`, write tool, command evidence, source lineage, and workspace mutation.
- `seat.ceo.delivery`, `seat.architect.delivery`, `seat.checker.acceptance`, and `seat.closeout.package` can compile read-only or audit-only invocations without required implementation workspace mutation.
- non-worker invocation metadata records `role_execution_kind` such as `governance`, `architecture`, `verification`, or `audit`.

- [ ] **Step 2: Verify tests fail**

```bash
PYTHONPATH=src:. python -m pytest tests/execution/test_atomic_agent_invocation_compiler.py tests/negative/test_v2_090f_agent_team_fail_closed.py -q --tb=short
```

Expected: FAIL because `AtomicInvocationCompiler.compile_with_settings` currently always requires command evidence and workspace mutation.

- [ ] **Step 3: Implement role-specific requirements**

Extend `compile_with_settings` or add a new helper such as `compile_role_invocation_with_settings`. Requirements:

- worker role category: keep current hard requirements.
- governance/architecture/verification/audit categories: require event stream and provider turn facts; require command evidence only when declared commands exist; require workspace mutation only when allowed write set includes implementation source paths; write permissions must match role policy.
- metadata must include `role_slot_ref`, `role_profile_ref`, `role_category`, `role_execution_kind`, config hashes, tool policy hash, and budget hash.

- [ ] **Step 4: Run targeted compiler tests**

```bash
PYTHONPATH=src:. python -m pytest tests/execution/test_atomic_agent_invocation_compiler.py tests/negative/test_v2_090f_agent_team_fail_closed.py -q --tb=short --basetemp .pytest-tmp-v2090f-role-compiler
```

Expected: PASS.

---

## Task 5: Autonomy Gate Against Pre-Split Ticket Graphs

**Files:**
- Modify: `src/boardroom_os/proving/v2_090f_prd_agent_team.py`
- Modify: `tests/negative/test_v2_090f_agent_team_fail_closed.py`

- [ ] **Step 1: Add autonomy gate tests**

Append:

```python
def test_v2_090f_rejects_runner_predefined_ticket_graph() -> None:
    from boardroom_os.proving.v2_090f_prd_agent_team import validate_agent_team_autonomy_inputs

    with pytest.raises(ValueError, match="runner must not predefine implementation ticket graph"):
        validate_agent_team_autonomy_inputs(
            prd_text="Build a tiny checkout app.",
            predefined_ticket_refs=("ticket.tiny.backend-api", "ticket.tiny.frontend-ui"),
        )


def test_v2_090f_allows_prd_only_autonomy_input() -> None:
    from boardroom_os.proving.v2_090f_prd_agent_team import validate_agent_team_autonomy_inputs

    validate_agent_team_autonomy_inputs(
        prd_text="Build a tiny checkout app.",
        predefined_ticket_refs=(),
    )
```

- [ ] **Step 2: Implement autonomy validator**

```python
def validate_agent_team_autonomy_inputs(*, prd_text: str, predefined_ticket_refs: tuple[str, ...]) -> None:
    if not prd_text.strip():
        raise ValueError("PRD must not be empty")
    if predefined_ticket_refs:
        raise ValueError("runner must not predefine implementation ticket graph")
```

- [ ] **Step 3: Run tests**

```bash
PYTHONPATH=src:. python -m pytest tests/negative/test_v2_090f_agent_team_fail_closed.py -q --tb=short --basetemp .pytest-tmp-v2090f-autonomy
```

Expected: PASS.

---

## Task 6: PRD Agent Team Runner Skeleton

**Files:**
- Create: `scripts/run_v2_090f_prd_agent_team.py`
- Modify: `scripts/build_tiny_closeout_sample.py`
- Modify: `tests/proving/test_v2_090f_prd_agent_team_script.py`

- [ ] **Step 1: Add CLI tests**

Append:

```python
def test_v2_090f_runner_requires_real_provider_opt_in(tmp_path: Path, monkeypatch) -> None:
    from scripts.run_v2_090f_prd_agent_team import main

    prd = tmp_path / "prd.md"
    prd.write_text("Build a tiny checkout app.", encoding="utf-8")
    monkeypatch.delenv("BOARDROOM_RUN_REAL_PROVIDER_PROVING", raising=False)

    assert main(["--prd", str(prd), "--reset"]) == 2


def test_tiny_closeout_wrapper_check_does_not_write_output_root(tmp_path: Path, monkeypatch) -> None:
    from scripts import build_tiny_closeout_sample

    output_root = tmp_path / "tiny-fullstack"
    output_root.mkdir()
    sentinel = output_root / "sentinel.txt"
    sentinel.write_text("keep", encoding="utf-8")

    monkeypatch.setattr(build_tiny_closeout_sample, "check_v2_090f_agent_team_sample", lambda root: 0)

    assert build_tiny_closeout_sample.main(["--output-root", str(output_root), "--check"]) == 0
    assert sentinel.read_text(encoding="utf-8") == "keep"
```

- [ ] **Step 2: Run tests and verify they fail**

```bash
PYTHONPATH=src:. python -m pytest tests/proving/test_v2_090f_prd_agent_team_script.py -q --tb=short
```

Expected: FAIL because runner and wrapper hook are missing.

- [ ] **Step 3: Implement runner skeleton**

Create `scripts/run_v2_090f_prd_agent_team.py`:

```python
from __future__ import annotations

import argparse
import os
from pathlib import Path

from boardroom_os.proving.v2_090f_prd_agent_team import (
    load_v2_090f_prd,
    reset_v2_090f_workspace,
    validate_agent_team_autonomy_inputs,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run V2-090F PRD-to-delivery agent team proving.")
    parser.add_argument("--prd", required=True)
    parser.add_argument("--reset", action="store_true")
    parser.add_argument("--workspace-root", default=".evidence/atomic-agent/v2-090f-prd-agent-team-workspace")
    parser.add_argument("--output-root", default="examples/generated-workspaces/tiny-fullstack")
    args = parser.parse_args(argv)
    prd = load_v2_090f_prd(Path(args.prd))
    validate_agent_team_autonomy_inputs(prd_text=prd.text, predefined_ticket_refs=())
    if os.environ.get("BOARDROOM_RUN_REAL_PROVIDER_PROVING") != "1":
        print("BOARDROOM_RUN_REAL_PROVIDER_PROVING=1 is required for V2-090F")
        return 2
    if args.reset:
        reset_v2_090f_workspace(Path(args.workspace_root))
    raise NotImplementedError("V2-090F real agent-team orchestration is implemented across Task 7A-7C")


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Update wrapper**

Refactor `scripts/build_tiny_closeout_sample.py` so:

```python
if args.check:
    return check_v2_090f_agent_team_sample(args.output_root)
return run_v2_090f_agent_team_build(args.output_root)
```

Do not call provider or write output root in `check_v2_090f_agent_team_sample`.

- [ ] **Step 5: Run tests**

```bash
PYTHONPATH=src:. python -m pytest tests/proving/test_v2_090f_prd_agent_team_script.py -q --tb=short --basetemp .pytest-tmp-v2090f-runner-skeleton
```

Expected: PASS.

---

## Task 7A: Real Agent Team Planning Orchestration

**Files:**
- Modify: `src/boardroom_os/proving/v2_090f_prd_agent_team.py`
- Modify: `scripts/run_v2_090f_prd_agent_team.py`
- Create: `tests/proving/test_v2_090f_prd_agent_team_real.py`

- [ ] **Step 1: Add default-skipped real provider test**

Create:

```python
from __future__ import annotations

import os
from pathlib import Path

import pytest


@pytest.mark.skipif(
    os.environ.get("BOARDROOM_RUN_REAL_PROVIDER_PROVING") != "1" or not os.environ.get("OPENAI_API_KEY"),
    reason="V2-090F real provider proving requires explicit opt-in and provider secret",
)
def test_v2_090f_prd_agent_team_real_provider(tmp_path: Path) -> None:
    from scripts.run_v2_090f_prd_agent_team import main

    prd = tmp_path / "prd.md"
    prd.write_text(
        "Build a tiny library checkout web app with a standard-library Python backend, static frontend, SQLite persistence, tests, and run instructions.",
        encoding="utf-8",
    )
    workspace = tmp_path / "workspace"
    output = tmp_path / "tiny-fullstack"

    assert main(["--prd", str(prd), "--reset", "--workspace-root", str(workspace), "--output-root", str(output)]) == 0
    assert (output / "00-boardroom/v2-090f-baseline.json").is_file()
    assert (output / "00-boardroom/generated-contracts.json").is_file()
    assert (output / "00-boardroom/generated-ticket-graph.json").is_file()
    assert (output / "closeout-package.json").is_file()
    assert (output / "sample-manifest.json").is_file()
```

- [ ] **Step 2: Implement CEO + Architect + Tester planning stage**

Implement the first stage of `run_v2_090f_prd_agent_team(...)` to:

- load Boardroom settings from `.env` config paths;
- require the paths point at `config/boardroom-runtime.v2-090f.yaml`, `config/boardroom-providers.v2-090f.yaml`, and `config/boardroom-roles.v2-090f.yaml`;
- validate required agent team role slots;
- write baseline report with config hashes and required seats;
- invoke CEO role to produce directive;
- invoke Architect role to produce contracts and ticket graph;
- invoke Tester role to produce verification plan;
- write `00-boardroom/generated-contracts.json`, `00-boardroom/generated-ticket-graph.json`, and `00-boardroom/generated-verification-plan.json`.

Important: implementation ticket refs must come from the agent-team-generated ticket graph, not from runner constants.

- [ ] **Step 3: Provide bounded reference examples as context**

The CEO/Architect/Tester invocations may read `examples/directives/v2-090f-reference-examples.md`. The runner must not parse that file into predefined ticket refs or commands.

- [ ] **Step 4: Record planning role context evidence**

For CEO, Architect and Tester invocations, persist:

- seat_ref;
- role_profile_ref;
- role_prompt_hook_ref/version/sha256;
- skill_refs;
- tools;
- provider profile ref/model/reasoning;
- invocation metadata hash;
- provider attempt ref or atomic run id.

Write this to `00-boardroom/agent-team-role-context.json`.

- [ ] **Step 5: Run non-provider tests**

```bash
PYTHONPATH=src:. python -m pytest tests/negative/test_v2_090f_agent_team_fail_closed.py tests/proving/test_v2_090f_prd_agent_team_script.py tests/proving/test_v2_090f_prd_agent_team_real.py -q --tb=short --basetemp .pytest-tmp-v2090f-non-provider
```

Expected: PASS with the real provider test skipped.

- [ ] **Step 6: Run real provider planning gate**

```bash
set -a; source .env; set +a; BOARDROOM_RUNTIME_CONFIG=config/boardroom-runtime.v2-090f.yaml BOARDROOM_PROVIDERS_CONFIG=config/boardroom-providers.v2-090f.yaml BOARDROOM_ROLES_CONFIG=config/boardroom-roles.v2-090f.yaml BOARDROOM_RUN_REAL_PROVIDER_PROVING=1 PYTHONPATH=src:. python -m pytest tests/proving/test_v2_090f_prd_agent_team_real.py -q --tb=short --basetemp .pytest-tmp-v2090f-real-planning
```

Expected after Task 7A implementation: planning artifacts exist. If implementation/closeout are still stubbed, the full real test may remain xfail until Task 7C; record planning run ids and failures without weakening gates.

---

## Task 7B: Worker Implementation Execution

**Files:**
- Modify: `src/boardroom_os/proving/v2_090f_prd_agent_team.py`
- Modify: `tests/proving/test_v2_090f_prd_agent_team_real.py`

- [ ] **Step 1: Execute generated implementation tickets**

Implement worker execution so every implementation ticket from `generated-ticket-graph.json` is compiled into an active `ExecutionPackage` and executed through `AtomicAgentExecutor`.

- [ ] **Step 2: Validate implementation evidence**

For each worker ticket require:

- provider turn facts;
- workspace mutation;
- command evidence for declared commands;
- source lineage input;
- no governance completion fields.

- [ ] **Step 3: Run real provider worker gate**

```bash
set -a; source .env; set +a; BOARDROOM_RUNTIME_CONFIG=config/boardroom-runtime.v2-090f.yaml BOARDROOM_PROVIDERS_CONFIG=config/boardroom-providers.v2-090f.yaml BOARDROOM_ROLES_CONFIG=config/boardroom-roles.v2-090f.yaml BOARDROOM_RUN_REAL_PROVIDER_PROVING=1 PYTHONPATH=src:. python -m pytest tests/proving/test_v2_090f_prd_agent_team_real.py -q --tb=short --basetemp .pytest-tmp-v2090f-real-worker
```

Expected after Task 7B: generated source and command evidence exist. If checker/closeout are not complete yet, keep the closeout verdict blocked and record evidence.

---

## Task 7C: Tester, Checker, Closeout, and Gates

**Files:**
- Modify: `src/boardroom_os/proving/v2_090f_prd_agent_team.py`
- Modify: `tests/proving/test_v2_090f_prd_agent_team_real.py`

- [ ] **Step 1: Invoke Tester, Checker, and Closeout roles**

Tester must execute or review the generated verification plan against the package evidence, including command/service/live probes. Checker must read contracts, ticket graph, package, command/service/live evidence and produce checker verdict. Closeout must assemble audit/closeout artifacts without setting passed directly.

- [ ] **Step 2: Run Boardroom gates**

Run existing evidence verifier, live blackbox verifier, final evidence table, workspace evidence bundle, replay/process/git audit and `CloseoutGate`.

- [ ] **Step 3: Run real provider full gate**

```bash
set -a; source .env; set +a; BOARDROOM_RUNTIME_CONFIG=config/boardroom-runtime.v2-090f.yaml BOARDROOM_PROVIDERS_CONFIG=config/boardroom-providers.v2-090f.yaml BOARDROOM_ROLES_CONFIG=config/boardroom-roles.v2-090f.yaml BOARDROOM_RUN_REAL_PROVIDER_PROVING=1 PYTHONPATH=src:. python -m pytest tests/proving/test_v2_090f_prd_agent_team_real.py -q --tb=short --basetemp .pytest-tmp-v2090f-real-full
```

Expected: PASS. Record PRD sha256, baseline hash, role invocation refs, generated ticket graph refs, atomic run ids, command exit codes, service/live evidence refs, closeout verdict, and sample manifest hash.

---

## Task 8: Check Mode and Sample Manifest

**Files:**
- Modify: `src/boardroom_os/proving/v2_090f_prd_agent_team.py`
- Modify: `scripts/build_tiny_closeout_sample.py`
- Modify: `tests/proving/test_v2_090f_prd_agent_team_script.py`

- [ ] **Step 1: Add check-mode tests**

Append:

```python
def test_v2_090f_check_rejects_forbidden_runtime_files(tmp_path: Path) -> None:
    from boardroom_os.proving.v2_090f_prd_agent_team import check_v2_090f_sample_tree

    sample = tmp_path / "tiny-fullstack"
    (sample / "10-project/backend/__pycache__").mkdir(parents=True)
    (sample / "10-project/backend/__pycache__/app.pyc").write_bytes(b"bad")

    with pytest.raises(ValueError, match="unregistered runtime file"):
        check_v2_090f_sample_tree(sample)


def test_v2_090f_check_requires_role_context_snapshot(tmp_path: Path) -> None:
    from boardroom_os.proving.v2_090f_prd_agent_team import check_v2_090f_sample_tree

    sample = tmp_path / "tiny-fullstack"
    sample.mkdir()
    (sample / "sample-manifest.json").write_text("{}", encoding="utf-8")

    with pytest.raises(ValueError, match="agent-team-role-context"):
        check_v2_090f_sample_tree(sample)
```

- [ ] **Step 2: Implement sample check**

`check_v2_090f_sample_tree` must:

- reject forbidden runtime files;
- require `00-boardroom/v2-090f-baseline.json`;
- require `00-boardroom/agent-team-role-context.json`;
- require `sample-manifest.json`, closeout, replay, git audit and process audit files;
- not call provider;
- not write output root.

- [ ] **Step 3: Run check-mode tests**

```bash
PYTHONPATH=src:. python -m pytest tests/proving/test_v2_090f_prd_agent_team_script.py -q --tb=short --basetemp .pytest-tmp-v2090f-check
```

Expected: PASS.

---

## Task 9: Documentation and Acceptance Update

**Files:**
- Modify: `examples/README.md`
- Modify: `scripts/README.md`
- Modify: `doc/04-implementation/backlog.md`
- Modify: `doc/04-implementation/acceptance-criteria.md`
- Modify: `doc/05-project-log/2026-06.md`

- [ ] **Step 1: Update documentation before completion claim**

Document that V2-090F is PRD-in / autonomous agent-team delivery out（PRD 输入 / 智能体团队自治交付输出）, not pre-split worker execution.

- [ ] **Step 2: Update acceptance only after real evidence**

Only after Task 7C and Task 8 pass:

- mark V2-090F `DONE`;
- check the V2-090F acceptance row;
- record role-context baseline evidence;
- record generated ticket graph refs;
- record closeout verdict and sample manifest hash.

---

## Task 10: Final Verification

**Files:**
- Inspect all modified files.

- [ ] **Step 1: Run targeted non-provider suite**

```bash
PYTHONPATH=src:. python -m pytest tests/negative/test_v2_090f_agent_team_fail_closed.py tests/proving/test_v2_090f_prd_agent_team_script.py tests/proving/test_v2_090f_prd_agent_team_real.py tests/execution/test_atomic_agent_invocation_compiler.py -q --tb=short --basetemp .pytest-tmp-v2090f-targeted-final
```

Expected: PASS with real provider test skipped.

- [ ] **Step 2: Run real provider proving gate**

```bash
set -a; source .env; set +a; BOARDROOM_RUNTIME_CONFIG=config/boardroom-runtime.v2-090f.yaml BOARDROOM_PROVIDERS_CONFIG=config/boardroom-providers.v2-090f.yaml BOARDROOM_ROLES_CONFIG=config/boardroom-roles.v2-090f.yaml BOARDROOM_RUN_REAL_PROVIDER_PROVING=1 PYTHONPATH=src:. python -m pytest tests/proving/test_v2_090f_prd_agent_team_real.py -q --tb=short --basetemp .pytest-tmp-v2090f-real-final
```

Expected: PASS.

- [ ] **Step 3: Run public check**

```bash
PYTHONPATH=src:. python scripts/build_tiny_closeout_sample.py --check
```

Expected: PASS and no file changes.

- [ ] **Step 4: Run diff hygiene**

```bash
git diff --check
```

Expected: exit 0.

- [ ] **Step 5: Scan for false autonomy claims**

```bash
rg -n "build_v2_090f_ticket_specs|ticket\\.tiny\\.backend-api|ticket\\.tiny\\.frontend-ui|all roles.*seat\\.worker|V2-090F.*DONE|\\[x\\].*V2-090F" docs doc scripts examples tests src
```

Expected: no pre-split ticket helper, no worker-seat reuse claim, and no V2-090F done claim before evidence.

---

## Self-Review

- Spec coverage: Tasks 1, 2, 3, 5, 7 and 8 cover PRD input, multi-role context, autonomy, real provider run, and sample verification.
- Negative-first: role-context, autonomy, provider-lock and check-mode failures are tested before happy path.
- No duplicate implementation: plan reuses RolePromptHook, RoleProfile, ExecutionPackage, AtomicAgentExecutor, evidence verifier and closeout gates.
- No second source of truth: config baseline records YAML hashes and resolved role settings; sample success comes from evidence and closeout gates.
- Runtime bounded: agent roles produce artifacts and facts; reducers/gates decide completion and closeout.
- Key correction from previous draft: runner must not predefine backend/frontend/integration tickets, and all roles must not share `seat.worker.implementation`.
