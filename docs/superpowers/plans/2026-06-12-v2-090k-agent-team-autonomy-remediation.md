# V2-090K Agent Team Autonomy Remediation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the V2-090F command-line integration run prove real agent team autonomy（智能体团队自治） by removing runner-owned startup, business-probe, acceptance, and source-surface knowledge.

**Architecture:** Keep the existing V2-090F runner（运行器） as the command-line orchestration entrypoint, but strip it down to contract execution and fail-closed verification. CEO/Architect/Tester/Release-DevOps/Worker/Checker/Closeout roles（角色） must generate AcceptanceContract（验收合同）、PackageContract（包合同）、TicketGraph（任务图）、RunManifest（运行清单）、BehavioralProbePlan（行为探针计划）、implementation artifacts（实施产物）、checker verdict（检查结论） and closeout draft（收尾草案） with ProviderAttempt（模型调用尝试记录） evidence; the runner only validates and executes those declared artifacts.

**Tech Stack:** Python 3.12, pytest, pydantic, Boardroom OS contracts/workspace/evidence/closeout modules, external `atomic-agent`（原子智能体）, existing V2-090F dedicated runtime/providers/roles config baseline（运行时/供应商/角色配置基线）.

---

## File Structure

### Create

- `src/boardroom_os/agents/prompt_templates/baseline/v1/release_devops.md` — Release/DevOps role prompt（发布/运维角色提示词） for startability, env mapping, readiness, behavioral probes, topology, and sample promotion.
- `tests/negative/test_v2_090k_autonomy_regression_fail_closed.py` — negative tests（负例测试） proving hardcoded runner knowledge cannot remain.
- `tests/workspace/test_run_manifest_service_contract.py` — RunManifest service/env/readiness/frontend topology（运行清单服务/环境/就绪/前端拓扑） tests.
- `tests/workspace/test_run_manifest_behavioral_probe.py` — RunManifest behavioral probe（运行清单行为探针） schema tests.
- `tests/proving/fixtures/v2_090k_contract_authority.py` — shared typed AcceptanceContract / PackageContract fixture（共享强类型验收合同 / 包合同夹具） for V2-090K contract authority tests.
- `tests/proving/test_v2_090k_dynamic_closeout_contract.py` — closeout runner（收尾运行器） tests using non-090F command/env names and agent-declared behavior probes.
- `tests/proving/test_v2_090k_evidence_authority.py` — tests proving FinalEvidenceTable（最终证据表） and SourceInventory（源码清单） consume agent-generated contracts, not runner constants.
- `tests/proving/test_v2_090k_checker_closeout_roles.py` — Checker/Closeout ProviderAttempt（检查/收尾模型调用尝试记录） tests.

### Modify

- `src/boardroom_os/agents/role_prompt_hooks.py` — add `release_devops` role kind and strengthen Architect/Tester/Checker/Closeout responsibilities.
- `src/boardroom_os/agents/prompt_templates/baseline/v1/architect.md` — require contract/run/evidence authority outputs without naming fixed files/env vars.
- `src/boardroom_os/agents/prompt_templates/baseline/v1/tester.md` — require declarative behavioral probes tied to acceptance refs.
- `src/boardroom_os/agents/prompt_templates/baseline/v1/checker.md` — require contract/evidence/run-manifest/behavioral-probe gap review.
- `src/boardroom_os/agents/prompt_templates/baseline/v1/closeout.md` — require provider-backed closeout draft and audit summary without self-approving gates.
- `config/boardroom-roles.v2-090f.yaml` — add `seat.release.devops` with high-budget provider profile.
- `src/boardroom_os/workspace/run_manifest.py` — extend RunManifest（运行清单） with service contracts, env bindings, readiness probes, frontend topology, and behavioral probes.
- `src/boardroom_os/proving/v2_090f_prd_agent_team.py` — remove hardcoded startup/env/domain/acceptance/source-surface knowledge, consume agent-generated contracts, invoke Checker/Closeout roles, and publish default sample.
- `scripts/build_tiny_closeout_sample.py` — ensure `--check` validates the default published sample without provider calls or writes.
- `scripts/run_v2_090f_prd_agent_team.py` — keep explicit real provider opt-in path using 090K-remediated runner behavior.
- `doc/04-implementation/backlog.md`, `doc/04-implementation/acceptance-criteria.md`, `doc/05-project-log/2026-06.md` — update only after implementation evidence exists.

### Inspect Only

- `src/boardroom_os/adapters/process_runner.py` — reuse ServiceRunner（服务运行器） and `environment_overrides`（环境变量覆盖）.
- `src/boardroom_os/evidence/live_blackbox.py` — keep live blackbox verification（真实黑盒验证） as behavioral evidence gate.
- `src/boardroom_os/evidence/verifier.py` — keep provider attempt and evidence verification fail-closed.
- `doc/05-project-log/v2-090f-implementation-intervention-log.md` — first-run intervention evidence（介入证据）.

---

## Task 0: Baseline and Drift Check

**Files:**
- Inspect: `src/boardroom_os/proving/v2_090f_prd_agent_team.py`
- Inspect: `src/boardroom_os/agents/role_prompt_hooks.py`
- Inspect: `config/boardroom-roles.v2-090f.yaml`
- Inspect: `doc/04-implementation/acceptance-criteria.md`

- [ ] **Step 1: Record worktree state**

Run:

```bash
git status --short --branch --untracked-files=all
```

Expected: record existing changes. Do not revert unrelated user changes.

- [ ] **Step 2: Confirm current hardcoded intervention points exist before remediation**

Run:

```bash
rg -n "app/server.py|python -m app.server|LIBRARY_API_HOST|LIBRARY_API_PORT|LIBRARY_DB_PATH|_probe_v2_090f_crud_workflow|AC-V2-090F|_source_surface_for_project_path|_acceptance_refs_for_project_path|_v2_090f_acceptance_refs" src/boardroom_os/proving/v2_090f_prd_agent_team.py tests scripts config
```

Expected before implementation: matches exist in the V2-090F runner or tests. After remediation, active source/tests/config must not enforce these as success paths.

- [ ] **Step 3: Confirm V2-090F remains unchecked**

Run:

```bash
rg -n "\\[ \\].*V2-090F|V2-090F.*REVIEW_REQUIRED|V2-090F.*BLOCKED" doc/04-implementation/acceptance-criteria.md doc/04-implementation/backlog.md doc/05-project-log/2026-06.md
```

Expected: V2-090F is not DONE before V2-090K evidence exists.

---

## Task 1: Negative Tests for Runner-Owned Knowledge

**Files:**
- Create: `tests/negative/test_v2_090k_autonomy_regression_fail_closed.py`
- Modify: `src/boardroom_os/proving/v2_090f_prd_agent_team.py`

- [ ] **Step 1: Write failing tests that reject fixed startup and env knowledge**

Create `tests/negative/test_v2_090k_autonomy_regression_fail_closed.py`:

```python
from __future__ import annotations

import inspect


def _runner_source() -> str:
    from boardroom_os.proving import v2_090f_prd_agent_team as runner

    return inspect.getsource(runner)


def test_planning_prompt_does_not_hardcode_backend_layout_or_env() -> None:
    from boardroom_os.proving import v2_090f_prd_agent_team as runner

    prompt = runner._direct_planning_prompt("Objective mentions ticket-graph")

    forbidden = (
        "app/server.py",
        "python -m app.server",
        "LIBRARY_API_HOST",
        "LIBRARY_API_PORT",
        "LIBRARY_DB_PATH",
        "backend API, SQLite persistence, static frontend",
    )
    for value in forbidden:
        assert value not in prompt


def test_runner_source_does_not_contain_hard_backend_validator() -> None:
    source = _runner_source()

    assert "_validate_v2_090f_hard_backend_entrypoint" not in source
    assert "hard backend runtime environment" not in source
```

- [ ] **Step 2: Add failing tests that reject business-domain probe knowledge**

Append:

```python
def test_runner_source_does_not_contain_library_domain_probe() -> None:
    source = _runner_source()

    forbidden = (
        "_probe_v2_090f_crud_workflow",
        "\"/books\"",
        "\"Dune\"",
        "\"Frank Herbert\"",
        "\"checked_out\"",
        "{\"books\": []}",
    )
    for value in forbidden:
        assert value not in source
```

- [ ] **Step 3: Add failing tests that reject acceptance/source-surface second source of truth**

Append:

```python
def test_runner_source_does_not_contain_static_acceptance_or_path_surface_mapping() -> None:
    source = _runner_source()

    forbidden = (
        "_v2_090f_acceptance_refs",
        "_statement_for_acceptance_ref",
        "_acceptance_refs_for_project_path",
        "_source_surface_for_project_path",
        "AC-V2-090F-BACKEND-CRUD",
        "relative.startswith(\"app/\")",
        "relative.startswith(\"static/\")",
    )
    for value in forbidden:
        assert value not in source
```

- [ ] **Step 4: Run tests and verify failure**

Run:

```bash
PYTHONPATH=src:. python -m pytest tests/negative/test_v2_090k_autonomy_regression_fail_closed.py -q --tb=short
```

Expected before implementation: FAIL because the runner still contains hardcoded startup/env/domain/acceptance/source-surface knowledge.

- [ ] **Step 5: Remove hardcoded planning prompt and validator**

Edit `src/boardroom_os/proving/v2_090f_prd_agent_team.py`:

- Delete `_validate_v2_090f_hard_backend_entrypoint`.
- Remove its call site from ticket graph validation.
- In `_direct_planning_prompt`, replace fixed backend layout/env text with:

```python
"For ticket-graph, include implementation tickets only as needed to satisfy the PRD and active contracts; do not rely on runner-provided ticket categories.",
"The agent team must produce AcceptanceContract, PackageContract, RunManifest, and verification-plan artifacts. The runner will validate and execute these artifacts without assuming filenames, module names, environment variable names, endpoints, seeded data, or source-surface path prefixes.",
"Worker implementation commands must be bounded finite verification commands that exit.",
"Service startup, readiness, live behavior probes, source-surface mappings, and acceptance evidence mapping must be declared by agent-generated contracts and verification artifacts.",
```

- [ ] **Step 6: Keep tests red until Tasks 3 and 4 remove domain/acceptance/source fallback**

Run:

```bash
PYTHONPATH=src:. python -m pytest tests/negative/test_v2_090k_autonomy_regression_fail_closed.py -q --tb=short
```

Expected after Step 5 only: startup/env tests may pass, but domain/acceptance/source tests still FAIL. They are resolved by Tasks 3 and 4.

---

## Task 2: Role Prompt and Release/DevOps Responsibility

**Files:**
- Create: `src/boardroom_os/agents/prompt_templates/baseline/v1/release_devops.md`
- Modify: `src/boardroom_os/agents/role_prompt_hooks.py`
- Modify: `src/boardroom_os/agents/prompt_templates/baseline/v1/architect.md`
- Modify: `src/boardroom_os/agents/prompt_templates/baseline/v1/tester.md`
- Modify: `src/boardroom_os/agents/prompt_templates/baseline/v1/checker.md`
- Modify: `src/boardroom_os/agents/prompt_templates/baseline/v1/closeout.md`
- Modify: `config/boardroom-roles.v2-090f.yaml`
- Test: `tests/execution/test_role_prompt_hooks.py`
- Test: `tests/config/test_boardroom_config.py`
- Test: `tests/negative/test_v2_090f_agent_team_fail_closed.py`

- [ ] **Step 1: Add failing role prompt test**

Append to `tests/execution/test_role_prompt_hooks.py`:

```python
def test_baseline_hooks_include_release_devops_responsibility() -> None:
    from boardroom_os.agents.role_prompt_hooks import build_baseline_role_prompt_hook_registry

    registry = build_baseline_role_prompt_hook_registry()
    hook = registry.require_by_role_kind("release_devops")

    responsibilities = " ".join(hook.required_responsibilities).lower()
    assert "runmanifest" in responsibilities or "run manifest" in responsibilities
    assert "service startup" in responsibilities
    assert "environment mapping" in responsibilities
    assert "readiness" in responsibilities
    assert "behavioral probe" in responsibilities
    assert "frontend" in responsibilities and "backend" in responsibilities
```

- [ ] **Step 2: Add `require_by_role_kind` helper**

In `src/boardroom_os/agents/role_prompt_hooks.py`, add to `RolePromptHookRegistry`:

```python
def require_by_role_kind(self, role_kind: str) -> RolePromptHook:
    normalized = role_kind.strip()
    if not normalized:
        raise ValueError("role_kind must not be empty")
    matches = tuple(hook for hook in self.hooks if hook.role_kind == normalized)
    if len(matches) != 1:
        raise ValueError(f"expected exactly one role prompt hook for role_kind: {normalized}")
    return matches[0]
```

- [ ] **Step 3: Add failing dedicated-role config test with real function name**

Append to `tests/negative/test_v2_090f_agent_team_fail_closed.py`:

```python
def test_v2_090f_roles_require_release_devops_seat() -> None:
    from boardroom_os.proving.v2_090f_prd_agent_team import validate_required_agent_team_slots

    slots = [
        {"seat_ref": "seat.ceo.delivery", "role_profile_ref": "role.ceo.delivery"},
        {"seat_ref": "seat.architect.delivery", "role_profile_ref": "role.architect.delivery"},
        {"seat_ref": "seat.worker.implementation", "role_profile_ref": "role.worker.implementation"},
        {"seat_ref": "seat.tester.integration", "role_profile_ref": "role.tester.integration"},
        {"seat_ref": "seat.checker.acceptance", "role_profile_ref": "role.checker.acceptance"},
        {"seat_ref": "seat.closeout.package", "role_profile_ref": "role.closeout.package"},
    ]

    with pytest.raises(ValueError, match="seat.release.devops"):
        validate_required_agent_team_slots(slots)
```

- [ ] **Step 4: Run tests and verify failure**

Run:

```bash
PYTHONPATH=src:. python -m pytest tests/execution/test_role_prompt_hooks.py tests/negative/test_v2_090f_agent_team_fail_closed.py -q --tb=short
```

Expected before implementation: FAIL because no `release_devops` hook/seat exists and `REQUIRED_AGENT_TEAM_SEATS` does not include `seat.release.devops`.

- [ ] **Step 5: Add release/devops hook and prompt**

Create `src/boardroom_os/agents/prompt_templates/baseline/v1/release_devops.md`:

```markdown
# Release DevOps Role Prompt

You are the Release/DevOps seat for Boardroom OS V2.

Your responsibility is to make the generated package startable, observable,
behaviorally probeable, and releasable without asking the runner to know
private implementation or business-domain details in advance.

You must produce or review a RunManifest that declares:
- service startup commands;
- required environment bindings;
- readiness probes;
- frontend/backend topology;
- behavioral probe steps and assertions;
- test commands;
- sample promotion and check expectations.

You must not hardcode Boardroom-owned filenames, module names, environment
variable names, ports, endpoints, seeded data, response shapes, acceptance
refs, or source-surface path prefixes unless they are declared by the
generated contracts and verification artifacts.

You do not approve closeout. CloseoutGate remains the final authority.
```

In `role_prompt_hooks.py`, add:

```python
_ROLE_KIND_CATEGORY["release_devops"] = RoleCategory.INTEGRATION
_ROLE_REQUIRED_RESPONSIBILITY_TERMS["release_devops"] = (
    ("runmanifest",),
    ("service startup",),
    ("environment mapping",),
    ("readiness",),
    ("behavioral probe",),
    ("frontend", "backend"),
)
```

Add `_BASELINE_HOOK_SPECS` entry:

```python
(
    "release_devops",
    "role-prompt-hook.baseline.release-devops.v1",
    RoleCategory.INTEGRATION,
    "release_devops.md",
    (
        "Define RunManifest service startup responsibilities.",
        "Define environment mapping for runtime-provided values.",
        "Define readiness probe requirements.",
        "Define behavioral probe steps and assertions.",
        "Define frontend/backend topology for live verification.",
    ),
),
```

- [ ] **Step 6: Update required seats and hook map**

In `src/boardroom_os/proving/v2_090f_prd_agent_team.py`, update:

```python
REQUIRED_AGENT_TEAM_SEATS = (
    "seat.ceo.delivery",
    "seat.architect.delivery",
    "seat.worker.implementation",
    "seat.tester.integration",
    "seat.release.devops",
    "seat.checker.acceptance",
    "seat.closeout.package",
)
```

Add `_HOOK_REF_BY_SEAT` mapping:

```python
"seat.release.devops": "role-prompt-hook.baseline.release-devops.v1",
```

- [ ] **Step 7: Strengthen existing prompts**

Update prompt templates:

- `architect.md`: require AcceptanceContract / PackageContract / source surfaces / run manifest references as authority sources.
- `tester.md`: require behavioral probe steps tied to acceptance refs.
- `checker.md`: require evidence gap review including behavioral probes, contract-derived final evidence, and source surface mapping.
- `closeout.md`: require provider-backed closeout draft and audit summary; state that CloseoutGate decides pass/fail.

- [ ] **Step 8: Update V2-090F dedicated roles config**

Add `seat.release.devops` to `config/boardroom-roles.v2-090f.yaml` using the exact existing YAML field names. The logical content must be:

```yaml
seat_ref: seat.release.devops
role_profile_ref: role.release.devops.v2-090f
role_category: integration
provider_profile_ref: provider.openai-compatible.v2-090f-primary
budget_profile_ref: agent_team.v2_090f.fullstack
skill_refs:
  - skill.release.run-manifest
default_tools:
  - submit_result
```

Do not add `.env` overrides for model, timeout, or budget.

- [ ] **Step 9: Add config loader preflight for the new seat**

Append to `tests/config/test_boardroom_config.py`:

```python
def test_v2_090f_roles_config_loads_release_devops_seat(monkeypatch) -> None:
    from pathlib import Path

    from boardroom_os.config.boardroom import BoardroomConfigPaths, load_boardroom_settings

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-secret")

    settings = load_boardroom_settings(
        BoardroomConfigPaths(
            runtime_config=Path("config/boardroom-runtime.v2-090f.yaml"),
            providers_config=Path("config/boardroom-providers.v2-090f.yaml"),
            roles_config=Path("config/boardroom-roles.v2-090f.yaml"),
        ),
        env_values={},
    )

    slot = settings.role_slot_by_seat("seat.release.devops")
    assert slot.role_category == "integration"
    assert slot.role_profile_ref == "role.release.devops.v2-090f"
    assert slot.provider_profile_ref == "provider.openai-compatible.v2-090f-primary"
    assert slot.budget_profile_ref == "agent_team.v2_090f.fullstack"
    assert "skill.release.run-manifest" in slot.skill_refs
    assert "submit_result" in slot.default_tools
    assert settings.budgets_for_seat("seat.release.devops")["budget_profile_ref"] == "agent_team.v2_090f.fullstack"
```

This test proves the existing `load_boardroom_settings` config loader（配置加载器） accepts `role_category: integration`, the new role profile ref（角色模板引用）, skill ref（技能引用）, provider ref（供应商引用）, and budget ref（预算引用） without a provider call.

- [ ] **Step 10: Re-run tests**

Run:

```bash
PYTHONPATH=src:. python -m pytest tests/execution/test_role_prompt_hooks.py tests/config/test_boardroom_config.py tests/negative/test_role_prompt_hooks_fail_closed.py tests/negative/test_v2_090f_agent_team_fail_closed.py -q --tb=short
```

Expected: PASS.

---

## Task 3: RunManifest Service and Behavioral Probe Protocol

**Files:**
- Modify: `src/boardroom_os/workspace/run_manifest.py`
- Create: `tests/workspace/test_run_manifest_service_contract.py`
- Create: `tests/workspace/test_run_manifest_behavioral_probe.py`
- Modify: `tests/proving/test_run_manifest.py`

- [ ] **Step 1: Write failing tests for service/env/readiness/topology**

Create `tests/workspace/test_run_manifest_service_contract.py`:

```python
from __future__ import annotations

import pytest


def test_service_contract_allows_agent_declared_env_names() -> None:
    from boardroom_os.contracts.types import ContractId
    from boardroom_os.workspace.run_manifest import (
        RunManifestEnvironmentBinding,
        RunManifestEnvironmentValueSource,
        RunManifestReadinessProbe,
        RunManifestServiceContract,
    )

    service = RunManifestServiceContract(
        command_id=ContractId(value="serve-library"),
        role="backend",
        env_bindings=(
            RunManifestEnvironmentBinding(
                name="BOOK_APP_HOST",
                value_source=RunManifestEnvironmentValueSource.RUNTIME_HOST,
            ),
            RunManifestEnvironmentBinding(
                name="BOOK_APP_PORT",
                value_source=RunManifestEnvironmentValueSource.RUNTIME_PORT,
            ),
            RunManifestEnvironmentBinding(
                name="BOOK_DB_FILE",
                value_source=RunManifestEnvironmentValueSource.TEMP_SQLITE_PATH,
            ),
        ),
        readiness_probe=RunManifestReadinessProbe(
            method="GET",
            path="/healthz",
            expect_status=200,
        ),
    )

    assert {binding.name for binding in service.env_bindings} == {
        "BOOK_APP_HOST",
        "BOOK_APP_PORT",
        "BOOK_DB_FILE",
    }


def test_service_contract_rejects_missing_readiness_probe() -> None:
    from boardroom_os.contracts.types import ContractId
    from boardroom_os.workspace.run_manifest import RunManifestServiceContract

    with pytest.raises(ValueError, match="readiness_probe is required"):
        RunManifestServiceContract(
            command_id=ContractId(value="serve-library"),
            role="backend",
            env_bindings=(),
            readiness_probe=None,
        )
```

- [ ] **Step 2: Write failing tests for behavioral probe schema**

Create `tests/workspace/test_run_manifest_behavioral_probe.py`:

```python
from __future__ import annotations

import pytest


def test_behavioral_probe_declares_http_steps_without_books_domain_requirement() -> None:
    from boardroom_os.contracts.types import AcceptanceRef, ContractId
    from boardroom_os.workspace.run_manifest import (
        RunManifestBehaviorAssertion,
        RunManifestBehaviorAssertionKind,
        RunManifestBehaviorProbe,
        RunManifestBehaviorStep,
    )

    probe = RunManifestBehaviorProbe(
        probe_id=ContractId(value="probe.prd-behavior"),
        service_command_id=ContractId(value="serve-api"),
        acceptance_refs=(AcceptanceRef(value="AC-AGENT-DECLARED-CREATE-LIST"),),
        steps=(
            RunManifestBehaviorStep(
                step_id="create-item",
                method="POST",
                path="/agent-declared-items",
                json_body={"name": "agent chosen"},
                expect_status=201,
                capture={"item_id": "$.item.id"},
                assertions=(),
            ),
            RunManifestBehaviorStep(
                step_id="list-items",
                method="GET",
                path="/agent-declared-items",
                json_body=None,
                expect_status=200,
                capture={},
                assertions=(
                    RunManifestBehaviorAssertion(
                        kind=RunManifestBehaviorAssertionKind.JSON_CONTAINS,
                        target="$.items[*].id",
                        expected="${item_id}",
                    ),
                ),
            ),
        ),
    )

    assert probe.steps[0].path == "/agent-declared-items"
    assert probe.acceptance_refs[0].value == "AC-AGENT-DECLARED-CREATE-LIST"


def test_behavioral_probe_rejects_step_without_acceptance_refs() -> None:
    from boardroom_os.workspace.run_manifest import RunManifestBehaviorProbe, RunManifestBehaviorStep
    from boardroom_os.contracts.types import ContractId

    with pytest.raises(ValueError, match="acceptance_refs must not be empty"):
        RunManifestBehaviorProbe(
            probe_id=ContractId(value="probe.invalid"),
            service_command_id=ContractId(value="serve-api"),
            acceptance_refs=(),
            steps=(
                RunManifestBehaviorStep(
                    step_id="list",
                    method="GET",
                    path="/items",
                    json_body=None,
                    expect_status=200,
                    capture={},
                    assertions=(),
                ),
            ),
        )
```

- [ ] **Step 3: Run tests and verify failure**

Run:

```bash
PYTHONPATH=src:. python -m pytest tests/workspace/test_run_manifest_service_contract.py tests/workspace/test_run_manifest_behavioral_probe.py -q --tb=short
```

Expected before implementation: FAIL because the service contract and behavioral probe models do not exist.

- [ ] **Step 4: Extend RunManifest service models**

In `src/boardroom_os/workspace/run_manifest.py`, add:

```python
class RunManifestEnvironmentValueSource(StrEnum):
    RUNTIME_HOST = "runtime_host"
    RUNTIME_PORT = "runtime_port"
    TEMP_SQLITE_PATH = "temp_sqlite_path"
    LITERAL = "literal"
```

Add:

```python
class RunManifestEnvironmentBinding(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    value_source: RunManifestEnvironmentValueSource
    literal_value: str | None = None
```

Validators:

- `name` must match `^[A-Z_][A-Z0-9_]*$`;
- `literal_value` is required only when `value_source == LITERAL`;
- dynamic sources must not carry `literal_value`.

Add:

```python
class RunManifestReadinessProbe(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    method: Literal["GET"]
    path: str
    expect_status: int
```

Validators:

- `path` must start with `/`;
- `100 <= expect_status <= 599`.

Add:

```python
class RunManifestServiceContract(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    command_id: ContractId
    role: str
    env_bindings: tuple[RunManifestEnvironmentBinding, ...]
    readiness_probe: RunManifestReadinessProbe
```

- [ ] **Step 5: Extend RunManifest frontend topology models**

Add:

```python
class RunManifestFrontendMode(StrEnum):
    SERVED_BY_BACKEND = "served-by-backend"
    STATIC_SERVER = "static-server"
    PROXY_REQUIRED = "proxy-required"
    CONFIGURABLE_API_BASE = "configurable-api-base"


class RunManifestFrontendTopology(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    mode: RunManifestFrontendMode
    service_command_id: ContractId | None = None
    api_base_binding: str | None = None
```

Validation:

- `service_command_id` is required for `STATIC_SERVER` and `PROXY_REQUIRED`;
- `api_base_binding` is required for `CONFIGURABLE_API_BASE`;
- empty `api_base_binding` fails.

- [ ] **Step 6: Extend RunManifest behavioral probe models**

Add `AcceptanceRef` to the `src/boardroom_os/workspace/run_manifest.py` imports:

```python
from boardroom_os.contracts.types import AcceptanceRef, ContractId, NonEmptyTextValue
```

Add:

```python
class RunManifestBehaviorAssertionKind(StrEnum):
    JSON_EQUALS = "json_equals"
    JSON_CONTAINS = "json_contains"
    FIELD_EQUALS = "field_equals"
    FIELD_ABSENT = "field_absent"


class RunManifestBehaviorAssertion(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: RunManifestBehaviorAssertionKind
    target: str
    expected: Any = None
```

Add:

```python
class RunManifestBehaviorStep(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    step_id: str
    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE"]
    path: str
    json_body: Any = None
    expect_status: int
    capture: dict[str, str] = {}
    assertions: tuple[RunManifestBehaviorAssertion, ...] = ()
```

Validators:

- `step_id` must be non-empty;
- `path` must start with `/`;
- `100 <= expect_status <= 599`;
- `capture` keys/values must be non-empty strings.

Add:

```python
class RunManifestBehaviorProbe(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    probe_id: ContractId
    service_command_id: ContractId
    acceptance_refs: tuple[AcceptanceRef, ...]
    steps: tuple[RunManifestBehaviorStep, ...]
```

Validators:

- `acceptance_refs` must not be empty;
- `steps` must not be empty;
- step IDs must be unique.

- [ ] **Step 7: Add fields to RunManifest and validation**

Add fields:

```python
service_contracts: tuple[RunManifestServiceContract, ...] = ()
frontend_topology: RunManifestFrontendTopology | None = None
behavioral_probes: tuple[RunManifestBehaviorProbe, ...] = ()
```

Validation:

- each `service_contract.command_id` exists in `commands` with kind `RUN`;
- each `behavioral_probe.service_command_id` exists in `service_contracts`;
- software/mixed packages require at least one service contract and at least one behavioral probe;
- duplicate service contract command IDs and behavioral probe IDs fail;
- `frontend_topology.service_command_id`, if present, points to a run command;
- no field requires `LIBRARY_API_*`; agent-declared names are valid.

- [ ] **Step 8: Update `build_run_manifest`**

Change signature:

```python
def build_run_manifest(
    *,
    workspace_manifest: WorkspaceManifest,
    package_contract: PackageContract,
    service_contracts: tuple[RunManifestServiceContract, ...] = (),
    frontend_topology: RunManifestFrontendTopology | None = None,
    behavioral_probes: tuple[RunManifestBehaviorProbe, ...] = (),
) -> RunManifest:
```

Existing call sites can pass defaults. V2-090K runner must pass service contracts and behavioral probes parsed from agent artifacts.

- [ ] **Step 9: Run run-manifest regression tests**

Run:

```bash
PYTHONPATH=src:. python -m pytest tests/proving/test_run_manifest.py tests/workspace/test_run_manifest_service_contract.py tests/workspace/test_run_manifest_behavioral_probe.py -q --tb=short
```

Expected: PASS.

---

## Task 4: Acceptance and Source Surface Authority

**Files:**
- Modify: `src/boardroom_os/proving/v2_090f_prd_agent_team.py`
- Create: `tests/proving/fixtures/v2_090k_contract_authority.py`
- Create: `tests/proving/test_v2_090k_evidence_authority.py`
- Test: `tests/negative/test_v2_090k_autonomy_regression_fail_closed.py`

- [ ] **Step 1: Create shared typed contract fixture**

Create `tests/proving/fixtures/v2_090k_contract_authority.py`:

```python
from __future__ import annotations

from datetime import UTC, datetime

from boardroom_os.contracts.acceptance import create_acceptance_contract
from boardroom_os.contracts.directive import BoardDirective, DirectiveRegistry
from boardroom_os.contracts.evidence_obligation import RequiredArtifactType
from boardroom_os.contracts.methodology import (
    DocumentationDensity,
    MethodologyProfile,
    MethodologyProfileRegistry,
    MethodologyTemplateKind,
    default_documentation_obligations_for,
    docs_template_key_for,
)
from boardroom_os.contracts.package import (
    IntegrationBoundary,
    PackageCommand,
    PackageContract,
    PackageProjectType,
    create_package_contract,
)
from boardroom_os.contracts.project import ProjectCharterRegistry, create_project_charter
from boardroom_os.contracts.source_surface import OwnerSeatRef, RequiredTestRef, SourceSurface
from boardroom_os.contracts.types import AcceptanceRef, ContractId, EvidenceObligationRef, SourceSurfaceRef
from boardroom_os.evidence.claim import EvidenceArtifactRef, EvidenceClaimRef, EvidenceClaimSourceKind
from boardroom_os.evidence.verifier import ArtifactSha256, VerifiedArtifact, VerifiedEvidence, VerifiedEvidenceRef
from boardroom_os.execution.context_index import ProviderAttemptRef
from boardroom_os.execution.fallback import EvidencePurpose
from boardroom_os.graph.ticket import TicketId
from boardroom_os.proving.v2_090f_prd_agent_team import V2_090KContractAuthority
from boardroom_os.workspace.assembler import (
    PackageArtifact,
    PackageArtifactKind,
    PackageArtifactPath,
    assemble_package,
)
from boardroom_os.workspace.manifest import WorkflowRef, WorkspacePath, build_workspace_manifest
from boardroom_os.workspace.source_inventory import (
    PackageCommitRef,
    SourceFilePath,
    SourceFileRecord,
    SourceLineageRecord,
)


def _charter_registry() -> ProjectCharterRegistry:
    directive = BoardDirective(
        board_directive_id=ContractId(value="directive.v2-090k-authority"),
        source_type="natural_language",
        content_ref=ContractId(value="content.v2-090k-authority"),
        received_at=datetime(2026, 6, 12, 9, 0, tzinfo=UTC),
        requester_ref=ContractId(value="human-board"),
    )
    charter = create_project_charter(
        registry=DirectiveRegistry.from_directives(directive),
        project_charter_id=ContractId(value="project.charter.v2-090k-authority"),
        board_directive_ref=ContractId(value="directive.v2-090k-authority"),
        project_goal="Prove agent generated contract authority.",
        delivery_type="generated_project_package",
        non_goals=("No runner-owned acceptance refs.",),
        constraints=("Use existing strong contracts.",),
        risks=("Dict-only helpers can create a second source of truth.",),
        success_summary="Typed contracts drive evidence.",
    )
    return ProjectCharterRegistry.from_charters(charter)


def _methodology_registry() -> MethodologyProfileRegistry:
    template_kind = MethodologyTemplateKind.HYBRID
    profile = MethodologyProfile(
        methodology_profile_id=ContractId(value="methodology-profile.v2-090k-authority"),
        project_charter_ref=ContractId(value="project.charter.v2-090k-authority"),
        template_kind=template_kind,
        documentation_density=DocumentationDensity.STANDARD,
        docs_template_key=docs_template_key_for(template_kind),
        documentation_obligations=default_documentation_obligations_for(template_kind),
    )
    return MethodologyProfileRegistry.from_profiles(profile)


def _source_surface() -> SourceSurface:
    return SourceSurface(
        source_surface_ref=SourceSurfaceRef(value="surface.agent.backend"),
        name="Agent Backend",
        paths=("server_pkg/",),
        owned_by=OwnerSeatRef(value="seat.worker.implementation"),
        acceptance_refs=(AcceptanceRef(value="AC-AGENT-CREATE-LIST"),),
        required_tests=(RequiredTestRef(value="pytest-agent-backend"),),
    )


def _package_command(command_id: str) -> PackageCommand:
    return PackageCommand(
        command_id=ContractId(value=command_id),
        label=command_id,
        command=("python", "-m", "agent_declared.server"),
        cwd="10-project",
    )


def _valid_contract_authority() -> V2_090KContractAuthority:
    from boardroom_os.contracts.gates import validate_contract_gate

    acceptance_contract = create_acceptance_contract(
        registry=_charter_registry(),
        acceptance_contract_id=ContractId(value="acceptance-contract.agent.generated"),
        project_charter_ref=ContractId(value="project.charter.v2-090k-authority"),
        status={"value": "active"},
        criteria=(
            {
                "acceptance_ref": {"value": "AC-AGENT-CREATE-LIST"},
                "statement": "Agent declared create/list behavior works.",
                "evidence_required": [{"value": "source_patch"}],
                "blocking": True,
                "source_surface_refs": [{"value": "surface.agent.backend"}],
                "verification_strategy": {"value": "aggregate verified evidence"},
            },
        ),
    )
    methodology_registry = _methodology_registry()
    profile = methodology_registry.profiles[0]
    package_contract = create_package_contract(
        methodology_registry=methodology_registry,
        package_contract_id=ContractId(value="package-contract.agent.generated"),
        project_charter_ref=ContractId(value="project.charter.v2-090k-authority"),
        package_root="10-project",
        project_type=PackageProjectType.SOFTWARE,
        source_surfaces=(_source_surface(),),
        run_commands=(_package_command("serve-agent-api"),),
        test_commands=(_package_command("test-agent-api"),),
        integration_boundaries=(IntegrationBoundary(value="agent-declared-http"),),
        docs_required=True,
        closeout_required=True,
        methodology_profile_ref=profile.methodology_profile_id,
        docs_template_key=profile.docs_template_key,
        documentation_obligations=profile.documentation_obligations,
    )
    return V2_090KContractAuthority(
        acceptance_contract=acceptance_contract,
        package_contract=package_contract,
        contract_gate=validate_contract_gate(
            acceptance_contract=acceptance_contract,
            package_contract=package_contract,
        ),
    )


def _verified_evidence() -> VerifiedEvidence:
    return VerifiedEvidence(
        verified_evidence_id=VerifiedEvidenceRef(value="verified-evidence.agent.fullstack"),
        evidence_claim_ref=EvidenceClaimRef(value="claim.agent.fullstack"),
        evidence_obligation_ref=EvidenceObligationRef(value="obl-AC-AGENT-CREATE-LIST-source_patch"),
        producer_attempt_ref=ProviderAttemptRef(value="provider-attempt.worker.agent"),
        source_kind=EvidenceClaimSourceKind.WORK_PRODUCT,
        source_ref="work-product.agent.fullstack",
        expected_purpose=EvidencePurpose.IMPLEMENTATION,
        required_artifact_type=RequiredArtifactType(value="source_patch"),
        acceptance_refs=(AcceptanceRef(value="AC-AGENT-CREATE-LIST"),),
        source_surface_refs=(SourceSurfaceRef(value="surface.agent.backend"),),
        verified_artifacts=(
            VerifiedArtifact(
                artifact_ref=EvidenceArtifactRef(value="artifact.server-pkg-main"),
                sha256=ArtifactSha256(value="a" * 64),
                producer_attempt_ref=ProviderAttemptRef(value="provider-attempt.worker.agent"),
                source_ref="work-product.agent.fullstack",
                artifact_kind="source_patch",
            ),
        ),
        verified_at=datetime(2026, 6, 12, 11, 0, tzinfo=UTC),
    )


def _agent_contract_json_artifacts() -> dict[str, dict[str, object]]:
    authority = _valid_contract_authority()
    return {
        "acceptance-contract": authority.acceptance_contract.model_dump(mode="json"),
        "package-contract": authority.package_contract.model_dump(mode="json"),
    }


__all__ = [
    "_agent_contract_json_artifacts",
    "_charter_registry",
    "_methodology_registry",
    "_valid_contract_authority",
    "_verified_evidence",
    "AcceptanceRef",
    "ArtifactSha256",
    "ContractId",
    "PackageArtifact",
    "PackageArtifactKind",
    "PackageArtifactPath",
    "PackageCommitRef",
    "PackageContract",
    "ProviderAttemptRef",
    "SourceFilePath",
    "SourceFileRecord",
    "SourceLineageRecord",
    "SourceSurfaceRef",
    "TicketId",
    "VerifiedEvidenceRef",
    "WorkflowRef",
    "WorkspacePath",
    "assemble_package",
    "build_workspace_manifest",
]
```

- [ ] **Step 2: Write failing tests that enforce existing typed builders**

Create `tests/proving/test_v2_090k_evidence_authority.py`:

```python
from __future__ import annotations

from datetime import UTC, datetime

import pytest

from tests.proving.fixtures.v2_090k_contract_authority import (
    _agent_contract_json_artifacts,
    _charter_registry,
    _methodology_registry,
    _valid_contract_authority,
    _verified_evidence,
)


def test_final_evidence_builder_requires_typed_acceptance_contract(monkeypatch) -> None:
    from boardroom_os.contracts.acceptance import AcceptanceContract
    from boardroom_os.evidence import table as evidence_table
    from boardroom_os.evidence.table import FinalEvidenceTable
    from boardroom_os.proving.v2_090f_prd_agent_team import build_v2_090k_final_evidence_table

    calls: list[object] = []
    original_build = evidence_table.FinalEvidenceTableBuilder.build

    def spy_build(self, table_input):
        assert isinstance(table_input.active_acceptance_contract, AcceptanceContract)
        calls.append(table_input.active_acceptance_contract)
        return original_build(self, table_input)

    monkeypatch.setattr(evidence_table.FinalEvidenceTableBuilder, "build", spy_build)

    authority = _valid_contract_authority()
    table = build_v2_090k_final_evidence_table(
        acceptance_contract=authority.acceptance_contract,
        verified_evidence=(_verified_evidence(),),
        failed_blockers=(),
        generated_at=datetime(2026, 6, 12, 12, 0, tzinfo=UTC),
    )

    assert isinstance(table, FinalEvidenceTable)
    assert calls == [authority.acceptance_contract]
    assert table.acceptance_contract_ref == authority.acceptance_contract.acceptance_contract_id
    assert tuple(row.acceptance_ref.value for row in table.rows) == ("AC-AGENT-CREATE-LIST",)


def test_final_evidence_rejects_dict_acceptance_contract() -> None:
    from boardroom_os.proving.v2_090f_prd_agent_team import build_v2_090k_final_evidence_table

    with pytest.raises(ValueError, match="AcceptanceContract"):
        build_v2_090k_final_evidence_table(
            acceptance_contract={"criteria": []},
            verified_evidence=(),
            failed_blockers=(),
            generated_at=datetime(2026, 6, 12, 12, 0, tzinfo=UTC),
        )
```

- [ ] **Step 3: Write failing tests for SourceInventory authority**

Append:

```python
from tests.proving.fixtures.v2_090k_contract_authority import (
    AcceptanceRef,
    ArtifactSha256,
    PackageArtifact,
    PackageArtifactKind,
    PackageArtifactPath,
    PackageCommitRef,
    PackageContract,
    ProviderAttemptRef,
    SourceFilePath,
    SourceFileRecord,
    SourceLineageRecord,
    SourceSurfaceRef,
    TicketId,
    WorkflowRef,
    WorkspacePath,
    assemble_package,
    build_workspace_manifest,
)


def test_source_inventory_uses_typed_package_contract_and_lineage_records(monkeypatch) -> None:
    from boardroom_os.proving.v2_090f_prd_agent_team import build_v2_090k_source_inventory
    from boardroom_os.workspace import source_inventory as source_inventory_module
    from boardroom_os.workspace.source_inventory import SourceInventory

    calls: list[PackageContract] = []
    original_build = source_inventory_module.build_source_inventory

    def spy_build_source_inventory(**kwargs):
        assert isinstance(kwargs["package_contract"], PackageContract)
        assert all(isinstance(record, SourceLineageRecord) for record in kwargs["lineage_records"])
        calls.append(kwargs["package_contract"])
        return original_build(**kwargs)

    monkeypatch.setattr(source_inventory_module, "build_source_inventory", spy_build_source_inventory)

    authority = _valid_contract_authority()
    workspace_manifest = build_workspace_manifest(
        workflow_ref=WorkflowRef(value="workflow.v2-090k-authority"),
        workspace_root=WorkspacePath(value="workspace/v2-090k-authority"),
        package_contract=authority.package_contract,
    )
    package_assembly = assemble_package(
        workspace_manifest=workspace_manifest,
        package_contract=authority.package_contract,
        artifacts=(
            PackageArtifact(relative_path=PackageArtifactPath(value="README.md"), artifact_kind=PackageArtifactKind.README),
            PackageArtifact(relative_path=PackageArtifactPath(value="AGENTS.md"), artifact_kind=PackageArtifactKind.AGENTS),
            PackageArtifact(
                relative_path=PackageArtifactPath(value="package-contract.json"),
                artifact_kind=PackageArtifactKind.PACKAGE_CONTRACT,
                source_surface_refs=(SourceSurfaceRef(value="surface.agent.backend"),),
                acceptance_refs=(AcceptanceRef(value="AC-AGENT-CREATE-LIST"),),
            ),
            PackageArtifact(
                relative_path=PackageArtifactPath(value="run-manifest.json"),
                artifact_kind=PackageArtifactKind.RUN_MANIFEST,
                source_surface_refs=(SourceSurfaceRef(value="surface.agent.backend"),),
                acceptance_refs=(AcceptanceRef(value="AC-AGENT-CREATE-LIST"),),
            ),
            PackageArtifact(
                relative_path=PackageArtifactPath(value="server_pkg/main.py"),
                artifact_kind=PackageArtifactKind.SOURCE,
                source_surface_refs=(SourceSurfaceRef(value="surface.agent.backend"),),
                acceptance_refs=(AcceptanceRef(value="AC-AGENT-CREATE-LIST"),),
            ),
            PackageArtifact(
                relative_path=PackageArtifactPath(value="server_pkg/test_main.py"),
                artifact_kind=PackageArtifactKind.TEST,
                source_surface_refs=(SourceSurfaceRef(value="surface.agent.backend"),),
                acceptance_refs=(AcceptanceRef(value="AC-AGENT-CREATE-LIST"),),
            ),
            PackageArtifact(
                relative_path=PackageArtifactPath(value="server_pkg/usage.md"),
                artifact_kind=PackageArtifactKind.DOC,
                source_surface_refs=(SourceSurfaceRef(value="surface.agent.backend"),),
                acceptance_refs=(AcceptanceRef(value="AC-AGENT-CREATE-LIST"),),
            ),
        ),
    )
    source_inventory = build_v2_090k_source_inventory(
        package_assembly=package_assembly,
        package_contract=authority.package_contract,
        package_commit_ref=PackageCommitRef(value="commit.v2-090k-authority"),
        source_files=(
            SourceFileRecord(path=SourceFilePath(value="server_pkg/main.py"), sha256=ArtifactSha256(value="b" * 64)),
            SourceFileRecord(path=SourceFilePath(value="server_pkg/test_main.py"), sha256=ArtifactSha256(value="c" * 64)),
            SourceFileRecord(path=SourceFilePath(value="server_pkg/usage.md"), sha256=ArtifactSha256(value="d" * 64)),
        ),
        lineage_records=(
            SourceLineageRecord(
                path=SourceFilePath(value="server_pkg/main.py"),
                source_surface_ref=SourceSurfaceRef(value="surface.agent.backend"),
                producer_ticket_ref=TicketId(value="ticket.agent.backend"),
                producer_attempt_ref=ProviderAttemptRef(value="provider-attempt.worker.agent"),
                consumer_ticket_refs=(TicketId(value="ticket.agent.backend"),),
                acceptance_refs=(AcceptanceRef(value="AC-AGENT-CREATE-LIST"),),
                evidence_refs=(VerifiedEvidenceRef(value="verified-evidence.agent.fullstack"),),
            ),
            SourceLineageRecord(
                path=SourceFilePath(value="server_pkg/test_main.py"),
                source_surface_ref=SourceSurfaceRef(value="surface.agent.backend"),
                producer_ticket_ref=TicketId(value="ticket.agent.tests"),
                producer_attempt_ref=ProviderAttemptRef(value="provider-attempt.worker.tests"),
                consumer_ticket_refs=(TicketId(value="ticket.agent.tests"),),
                acceptance_refs=(AcceptanceRef(value="AC-AGENT-CREATE-LIST"),),
                evidence_refs=(VerifiedEvidenceRef(value="verified-evidence.agent.fullstack"),),
            ),
            SourceLineageRecord(
                path=SourceFilePath(value="server_pkg/usage.md"),
                source_surface_ref=SourceSurfaceRef(value="surface.agent.backend"),
                producer_ticket_ref=TicketId(value="ticket.agent.docs"),
                producer_attempt_ref=ProviderAttemptRef(value="provider-attempt.worker.docs"),
                consumer_ticket_refs=(TicketId(value="ticket.agent.docs"),),
                acceptance_refs=(AcceptanceRef(value="AC-AGENT-CREATE-LIST"),),
                evidence_refs=(VerifiedEvidenceRef(value="verified-evidence.agent.fullstack"),),
            ),
        ),
    )

    assert isinstance(source_inventory, SourceInventory)
    assert calls == [authority.package_contract]
    assert source_inventory.entries[0].source_surface_ref.value == "surface.agent.backend"


def test_contract_authority_rejects_package_surface_ref_outside_acceptance_contract() -> None:
    from boardroom_os.proving.v2_090f_prd_agent_team import load_v2_090k_contract_authority

    artifacts = _agent_contract_json_artifacts()
    artifacts["package-contract"]["source_surfaces"][0]["acceptance_refs"] = [{"value": "AC-NOT-ACTIVE"}]

    with pytest.raises(ValueError, match="active contract"):
        load_v2_090k_contract_authority(
            artifacts=artifacts,
            project_charter_registry=_charter_registry(),
            methodology_registry=_methodology_registry(),
        )
```

- [ ] **Step 4: Run tests and verify failure**

Run:

```bash
PYTHONPATH=src:. python -m pytest tests/proving/test_v2_090k_evidence_authority.py -q --tb=short
```

Expected before implementation: FAIL because the typed authority helpers do not exist.

- [ ] **Step 5: Implement typed contract authority loader**

Add imports in `src/boardroom_os/proving/v2_090f_prd_agent_team.py`:

```python
from dataclasses import dataclass
from typing import Mapping

from boardroom_os.contracts.acceptance import AcceptanceContract, create_acceptance_contract
from boardroom_os.contracts.gates import ContractGateResult, validate_contract_gate
from boardroom_os.contracts.methodology import MethodologyProfileRegistry
from boardroom_os.contracts.package import PackageContract, create_package_contract
from boardroom_os.contracts.project import ProjectCharterRegistry
from boardroom_os.evidence.table import (
    FinalEvidenceBlocker,
    FinalEvidenceTable,
    FinalEvidenceTableBuilder,
    FinalEvidenceTableInput,
)
from boardroom_os.evidence.verifier import VerifiedEvidence
from boardroom_os.workspace.assembler import PackageAssembly
from boardroom_os.workspace import source_inventory as source_inventory_module
from boardroom_os.workspace.source_inventory import (
    PackageCommitRef,
    SourceFileRecord,
    SourceInventory,
    SourceLineageRecord,
)
```

Add:

```python
@dataclass(frozen=True)
class V2_090KContractAuthority:
    acceptance_contract: AcceptanceContract
    package_contract: PackageContract
    contract_gate: ContractGateResult
```

```python
def load_v2_090k_contract_authority(
    *,
    artifacts: Mapping[str, Any],
    project_charter_registry: ProjectCharterRegistry,
    methodology_registry: MethodologyProfileRegistry,
) -> V2_090KContractAuthority:
    acceptance_payload = artifacts.get("acceptance-contract")
    package_payload = artifacts.get("package-contract")
    if not isinstance(acceptance_payload, Mapping):
        raise ValueError("AcceptanceContract artifact is required")
    if not isinstance(package_payload, Mapping):
        raise ValueError("PackageContract artifact is required")

    acceptance_contract = create_acceptance_contract(
        registry=project_charter_registry,
        **dict(acceptance_payload),
    )
    package_contract = create_package_contract(
        methodology_registry=methodology_registry,
        **dict(package_payload),
    )
    contract_gate = validate_contract_gate(
        acceptance_contract=acceptance_contract,
        package_contract=package_contract,
    )
    return V2_090KContractAuthority(
        acceptance_contract=acceptance_contract,
        package_contract=package_contract,
        contract_gate=contract_gate,
    )
```

This loader is the only place where agent JSON artifacts（产物） are admitted. It immediately converts them into existing strong types and calls `validate_contract_gate`（合同门禁校验）. Do not add a dict-only AcceptanceContract / PackageContract / SourceSurface implementation.

- [ ] **Step 6: Implement typed evidence wrappers over existing builders**

Add:

```python
def build_v2_090k_final_evidence_table(
    *,
    acceptance_contract: AcceptanceContract,
    verified_evidence: tuple[VerifiedEvidence, ...],
    failed_blockers: tuple[FinalEvidenceBlocker, ...],
    generated_at: datetime,
) -> FinalEvidenceTable:
    if not isinstance(acceptance_contract, AcceptanceContract):
        raise ValueError("AcceptanceContract instance is required")
    return FinalEvidenceTableBuilder().build(
        FinalEvidenceTableInput(
            active_acceptance_contract=acceptance_contract,
            verified_evidence=verified_evidence,
            failed_blockers=failed_blockers,
            generated_at=generated_at,
        )
    )
```

Add:

```python
def build_v2_090k_source_inventory(
    *,
    package_assembly: PackageAssembly,
    package_contract: PackageContract,
    package_commit_ref: PackageCommitRef,
    source_files: tuple[SourceFileRecord, ...],
    lineage_records: tuple[SourceLineageRecord, ...],
) -> SourceInventory:
    if not isinstance(package_contract, PackageContract):
        raise ValueError("PackageContract instance is required")
    return source_inventory_module.build_source_inventory(
        package_assembly=package_assembly,
        package_contract=package_contract,
        package_commit_ref=package_commit_ref,
        source_files=source_files,
        lineage_records=lineage_records,
    )
```

These wrappers are allowed only to enforce type boundaries and call existing builders. They must not derive row IDs, acceptance refs, source surfaces, path mappings, or status values by hand.

- [ ] **Step 7: Replace source inventory and final evidence table builders**

In `_build_v2_090f_source_inventory_payload`, replace calls to:

- `_source_surface_for_project_path`;
- `_acceptance_refs_for_project_path`;
- `_ticket_marker_for_path` if it relies on `app`/`static` domain markers.

The builder must consume typed `PackageContract`, `PackageAssembly`, `SourceFileRecord`, and agent-generated `SourceLineageRecord` values, then call `build_v2_090k_source_inventory`. It must fail closed if any materialized source file lacks lineage or is absent from the package assembly.

In `_build_v2_090f_final_evidence_table_payload`, replace `_v2_090f_acceptance_refs()` and `_statement_for_acceptance_ref()` with `build_v2_090k_final_evidence_table`. Persist `FinalEvidenceTable.model_dump(mode="json")`; do not hand-assemble a dict.

- [ ] **Step 8: Delete static and dict-only authority helpers**

Delete:

- `_source_surface_for_project_path`;
- `_acceptance_refs_for_project_path`;
- `_v2_090f_acceptance_refs`;
- `_statement_for_acceptance_ref`.

Do not add:

- `build_v2_090k_final_evidence_table_from_contracts`;
- `map_v2_090k_source_file_to_surface`;
- helpers that accept `acceptance_contract: dict[str, Any]` or `package_contract: dict[str, Any]` as authority.

Keep historical mentions only in docs/logs, not active `src`, `tests`, `scripts`, or `config`.

- [ ] **Step 9: Re-run authority and negative tests**

Run:

```bash
PYTHONPATH=src:. python -m pytest tests/proving/test_v2_090k_evidence_authority.py tests/negative/test_v2_090k_autonomy_regression_fail_closed.py -q --tb=short
```

Expected after implementation: PASS for authority tests and for the static acceptance/source-surface checks in the negative suite.

---

## Task 5: Planning Artifact Extraction and Contract Validation

**Files:**
- Modify: `src/boardroom_os/proving/v2_090f_prd_agent_team.py`
- Test: `tests/negative/test_v2_090k_autonomy_regression_fail_closed.py`
- Test: `tests/proving/test_v2_090f_prd_agent_team_script.py`

- [ ] **Step 1: Add failing tests for typed planning contract validation**

Append to `tests/negative/test_v2_090k_autonomy_regression_fail_closed.py`:

```python
import pytest

from tests.proving.fixtures.v2_090k_contract_authority import (
    _charter_registry,
    _methodology_registry,
    _valid_contract_authority,
)


def test_v2_090k_rejects_planning_without_run_manifest_and_behavioral_probes() -> None:
    from boardroom_os.proving.v2_090f_prd_agent_team import validate_v2_090k_planning_contracts

    artifacts = _valid_planning_artifacts()
    artifacts.pop("run-manifest")

    with pytest.raises(ValueError, match="RunManifest"):
        validate_v2_090k_planning_contracts(
            artifacts=artifacts,
            project_charter_registry=_charter_registry(),
            methodology_registry=_methodology_registry(),
        )
```

Add:

```python
def test_v2_090k_rejects_run_manifest_without_behavioral_probes() -> None:
    from boardroom_os.proving.v2_090f_prd_agent_team import validate_v2_090k_planning_contracts

    artifacts = _valid_planning_artifacts()
    artifacts["run-manifest"]["behavioral_probes"] = []

    with pytest.raises(ValueError, match="behavioral probes"):
        validate_v2_090k_planning_contracts(
            artifacts=artifacts,
            project_charter_registry=_charter_registry(),
            methodology_registry=_methodology_registry(),
        )
```

Add:

```python
def test_v2_090k_planning_contracts_return_typed_authority() -> None:
    from boardroom_os.contracts.acceptance import AcceptanceContract
    from boardroom_os.contracts.package import PackageContract
    from boardroom_os.proving.v2_090f_prd_agent_team import validate_v2_090k_planning_contracts
    from boardroom_os.workspace.run_manifest import RunManifest

    validated = validate_v2_090k_planning_contracts(
        artifacts=_valid_planning_artifacts(),
        project_charter_registry=_charter_registry(),
        methodology_registry=_methodology_registry(),
    )

    assert isinstance(validated.contract_authority.acceptance_contract, AcceptanceContract)
    assert isinstance(validated.contract_authority.package_contract, PackageContract)
    assert isinstance(validated.run_manifest, RunManifest)
    assert validated.contract_authority.contract_gate.acceptance_refs[0].value == "AC-AGENT-CREATE-LIST"
```

Add helpers:

```python
def _valid_planning_artifacts() -> dict[str, object]:
    authority = _valid_contract_authority()
    return {
        "acceptance-contract": authority.acceptance_contract.model_dump(mode="json"),
        "package-contract": authority.package_contract.model_dump(mode="json"),
        "ticket-graph": {"nodes": [{"node_type": "implementation"}]},
        "verification-plan": {
            "behavioral_probe_plan_ref": "20-evidence/tests/run-manifest.json#behavioral_probes",
        },
        "run-manifest": _valid_run_manifest_payload(authority),
    }

def _valid_run_manifest_payload(authority) -> dict[str, object]:
    from boardroom_os.contracts.types import AcceptanceRef, ContractId
    from boardroom_os.workspace.manifest import WorkflowRef, WorkspacePath, build_workspace_manifest
    from boardroom_os.workspace.run_manifest import (
        RunManifestBehaviorAssertion,
        RunManifestBehaviorAssertionKind,
        RunManifestBehaviorProbe,
        RunManifestBehaviorStep,
        RunManifestEnvironmentBinding,
        RunManifestEnvironmentValueSource,
        RunManifestFrontendMode,
        RunManifestFrontendTopology,
        RunManifestReadinessProbe,
        RunManifestServiceContract,
        build_run_manifest,
    )

    workspace_manifest = build_workspace_manifest(
        workflow_ref=WorkflowRef(value="workflow.v2-090k-planning"),
        workspace_root=WorkspacePath(value="workspace/v2-090k-planning"),
        package_contract=authority.package_contract,
    )
    manifest = build_run_manifest(
        workspace_manifest=workspace_manifest,
        package_contract=authority.package_contract,
        service_contracts=(
            RunManifestServiceContract(
                command_id=ContractId(value="serve-agent-api"),
                role="backend",
                env_bindings=(
                    RunManifestEnvironmentBinding(
                        name="AGENT_HOST",
                        value_source=RunManifestEnvironmentValueSource.RUNTIME_HOST,
                    ),
                    RunManifestEnvironmentBinding(
                        name="AGENT_PORT",
                        value_source=RunManifestEnvironmentValueSource.RUNTIME_PORT,
                    ),
                ),
                readiness_probe=RunManifestReadinessProbe(method="GET", path="/ready", expect_status=200),
            ),
        ),
        frontend_topology=RunManifestFrontendTopology(mode=RunManifestFrontendMode.SERVED_BY_BACKEND),
        behavioral_probes=(
            RunManifestBehaviorProbe(
                probe_id=ContractId(value="probe.agent-create-list"),
                service_command_id=ContractId(value="serve-agent-api"),
                acceptance_refs=(AcceptanceRef(value="AC-AGENT-CREATE-LIST"),),
                steps=(
                    RunManifestBehaviorStep(
                        step_id="create",
                        method="POST",
                        path="/agent-items",
                        json_body={"title": "agent declared"},
                        expect_status=201,
                        capture={"item_id": "$.item.id"},
                        assertions=(),
                    ),
                    RunManifestBehaviorStep(
                        step_id="list",
                        method="GET",
                        path="/agent-items",
                        json_body=None,
                        expect_status=200,
                        capture={},
                        assertions=(
                            RunManifestBehaviorAssertion(
                                kind=RunManifestBehaviorAssertionKind.JSON_CONTAINS,
                                target="$.items[*].id",
                                expected="${item_id}",
                            ),
                        ),
                    ),
                ),
            ),
        ),
    )
    return manifest.model_dump(mode="json")
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
PYTHONPATH=src:. python -m pytest tests/negative/test_v2_090k_autonomy_regression_fail_closed.py::test_v2_090k_rejects_planning_without_run_manifest_and_behavioral_probes tests/negative/test_v2_090k_autonomy_regression_fail_closed.py::test_v2_090k_rejects_run_manifest_without_behavioral_probes -q --tb=short
```

Expected before implementation: FAIL because `validate_v2_090k_planning_contracts` does not exist or does not enforce behavioral probes.

- [ ] **Step 3: Implement typed planning artifact container**

Add:

```python
@dataclass(frozen=True)
class V2_090KPlanningContracts:
    contract_authority: V2_090KContractAuthority
    run_manifest: RunManifest
    ticket_graph: Mapping[str, Any]
    verification_plan: Mapping[str, Any]
```

- [ ] **Step 4: Implement planning artifact validator**

Add imports:

```python
from boardroom_os.workspace.run_manifest import RunManifest
```

Add:

```python
def validate_v2_090k_planning_contracts(
    *,
    artifacts: Mapping[str, Any],
    project_charter_registry: ProjectCharterRegistry,
    methodology_registry: MethodologyProfileRegistry,
) -> V2_090KPlanningContracts:
    required = ("acceptance-contract", "package-contract", "ticket-graph", "verification-plan", "run-manifest")
    missing = [name for name in required if name not in artifacts]
    if missing:
        raise ValueError("missing planning artifacts: " + ", ".join(missing))

    contract_authority = load_v2_090k_contract_authority(
        artifacts=artifacts,
        project_charter_registry=project_charter_registry,
        methodology_registry=methodology_registry,
    )

    run_manifest_payload = artifacts["run-manifest"]
    if not isinstance(run_manifest_payload, Mapping):
        raise ValueError("RunManifest artifact is required")
    run_manifest = RunManifest.model_validate(run_manifest_payload)
    if run_manifest.package_contract_ref != contract_authority.package_contract.package_contract_id:
        raise ValueError("RunManifest package_contract_ref must match PackageContract")
    if not run_manifest.service_contracts:
        raise ValueError("RunManifest service contracts are required")
    if not run_manifest.behavioral_probes:
        raise ValueError("RunManifest behavioral probes are required")

    active_acceptance_refs = {
        criterion.acceptance_ref.value
        for criterion in contract_authority.acceptance_contract.criteria
    }
    for probe in run_manifest.behavioral_probes:
        for acceptance_ref in probe.acceptance_refs:
            if acceptance_ref.value not in active_acceptance_refs:
                raise ValueError("RunManifest behavioral probe acceptance_ref must belong to active contract")

    ticket_graph = artifacts["ticket-graph"]
    if not isinstance(ticket_graph, Mapping):
        raise ValueError("TicketGraph artifact is required")
    nodes = ticket_graph.get("nodes")
    if not isinstance(nodes, list) or not any(node.get("node_type") == "implementation" for node in nodes if isinstance(node, dict)):
        raise ValueError("ticket graph requires agent-generated implementation nodes")

    verification_plan = artifacts["verification-plan"]
    if not isinstance(verification_plan, Mapping):
        raise ValueError("VerificationPlan artifact is required")

    return V2_090KPlanningContracts(
        contract_authority=contract_authority,
        run_manifest=run_manifest,
        ticket_graph=ticket_graph,
        verification_plan=verification_plan,
    )
```

- [ ] **Step 5: Invoke validation after planning**

In `run_v2_090f_provider_planning_stage`, use planning steps:

```python
planning_steps = (
    ("seat.ceo.delivery", "board-directive"),
    ("seat.architect.delivery", "acceptance-contract"),
    ("seat.architect.delivery", "package-contract"),
    ("seat.architect.delivery", "ticket-graph"),
    ("seat.tester.integration", "verification-plan"),
    ("seat.release.devops", "run-manifest"),
)
```

Call `validate_v2_090k_planning_contracts(...)` before `_mark_planning_role_context_succeeded`. Pass the project charter registry（项目章程注册表） and methodology registry（方法论注册表） already used by the current run. Do not let the validator accept naked dict contracts as authoritative outputs.

- [ ] **Step 6: Persist normalized planning contracts**

Write normalized artifacts to:

- `00-boardroom/generated-acceptance-contract.json`;
- `00-boardroom/generated-package-contract.json`;
- `00-boardroom/generated-ticket-graph.json`;
- `00-boardroom/generated-verification-plan.json`;
- `20-evidence/tests/run-manifest.json`.

Persist typed `.model_dump(mode="json")` output from `V2_090KPlanningContracts`. The persisted RunManifest must be the validated agent artifact, not a runner-generated replacement.

- [ ] **Step 7: Re-run planning tests**

Run:

```bash
PYTHONPATH=src:. python -m pytest tests/negative/test_v2_090k_autonomy_regression_fail_closed.py tests/proving/test_v2_090f_prd_agent_team_script.py -q --tb=short
```

Expected: PASS except tests that require later closeout behavior may still be skipped or separately targeted.

---

## Task 6: Dynamic Closeout Runner From Agent Contracts

**Files:**
- Modify: `src/boardroom_os/proving/v2_090f_prd_agent_team.py`
- Create: `tests/proving/test_v2_090k_dynamic_closeout_contract.py`
- Reuse: `src/boardroom_os/adapters/process_runner.py`

- [ ] **Step 1: Write failing test for dynamic env binding**

Create `tests/proving/test_v2_090k_dynamic_closeout_contract.py`:

```python
from __future__ import annotations

from pathlib import Path

import pytest


def test_dynamic_env_binding_does_not_require_library_api_names(tmp_path: Path) -> None:
    from boardroom_os.proving.v2_090f_prd_agent_team import resolve_v2_090k_service_environment
    from boardroom_os.workspace.run_manifest import (
        RunManifestEnvironmentBinding,
        RunManifestEnvironmentValueSource,
    )

    env = resolve_v2_090k_service_environment(
        bindings=(
            RunManifestEnvironmentBinding(
                name="BOOK_APP_HOST",
                value_source=RunManifestEnvironmentValueSource.RUNTIME_HOST,
            ),
            RunManifestEnvironmentBinding(
                name="BOOK_APP_PORT",
                value_source=RunManifestEnvironmentValueSource.RUNTIME_PORT,
            ),
            RunManifestEnvironmentBinding(
                name="BOOK_DB_FILE",
                value_source=RunManifestEnvironmentValueSource.TEMP_SQLITE_PATH,
            ),
        ),
        host="127.0.0.1",
        port=8123,
        temp_sqlite_path=tmp_path / "library.sqlite3",
    )

    assert env == {
        "BOOK_APP_HOST": "127.0.0.1",
        "BOOK_APP_PORT": "8123",
        "BOOK_DB_FILE": str(tmp_path / "library.sqlite3"),
    }
```

- [ ] **Step 2: Write failing tests for behavior probe capture and interpolation**

Append:

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class _FakeResponse:
    status_code: int
    payload: object

    def json(self) -> object:
        return self.payload


class _FakeHttpClient:
    def __init__(self, responses: list[_FakeResponse]) -> None:
        self._responses = responses
        self.requests: list[dict[str, object]] = []

    def request(self, method: str, url: str, *, json: object | None = None, timeout: float = 10.0):
        self.requests.append({"method": method, "url": url, "json": json, "timeout": timeout})
        if not self._responses:
            raise AssertionError("unexpected extra HTTP request")
        return self._responses.pop(0)


def test_behavior_probe_executor_captures_and_interpolates_values() -> None:
    from boardroom_os.contracts.types import AcceptanceRef, ContractId
    from boardroom_os.proving.v2_090f_prd_agent_team import execute_v2_090k_behavior_probe
    from boardroom_os.workspace.run_manifest import (
        RunManifestBehaviorAssertion,
        RunManifestBehaviorAssertionKind,
        RunManifestBehaviorProbe,
        RunManifestBehaviorStep,
    )

    client = _FakeHttpClient(
        [
            _FakeResponse(201, {"item": {"id": "agent-123", "name": "Agent Item"}}),
            _FakeResponse(200, {"items": [{"id": "agent-123", "name": "Agent Item"}]}),
        ]
    )
    probe = RunManifestBehaviorProbe(
        probe_id=ContractId(value="probe.agent-custom"),
        service_command_id=ContractId(value="serve-agent-api"),
        acceptance_refs=(AcceptanceRef(value="AC-AGENT-CUSTOM"),),
        steps=(
            RunManifestBehaviorStep(
                step_id="create",
                method="POST",
                path="/custom-items",
                json_body={"name": "Agent Item"},
                expect_status=201,
                capture={"item_id": "$.item.id"},
                assertions=(),
            ),
            RunManifestBehaviorStep(
                step_id="list",
                method="GET",
                path="/custom-items/${item_id}",
                json_body=None,
                expect_status=200,
                capture={},
                assertions=(
                    RunManifestBehaviorAssertion(
                        kind=RunManifestBehaviorAssertionKind.JSON_CONTAINS,
                        target="$.items[*].id",
                        expected="${item_id}",
                    ),
                ),
            ),
        ),
    )

    result = execute_v2_090k_behavior_probe(
        probe=probe,
        base_url="http://127.0.0.1:8123",
        http_client=client,
    )

    assert result["probe_id"] == "probe.agent-custom"
    assert result["passed"] is True
    assert result["captures"] == {"item_id": "agent-123"}
    assert client.requests[1]["url"] == "http://127.0.0.1:8123/custom-items/agent-123"
```

- [ ] **Step 3: Write failing tests for assertion semantics and fail-closed cases**

Append:

```python
def test_behavior_probe_executor_supports_all_declared_assertions() -> None:
    from boardroom_os.contracts.types import AcceptanceRef, ContractId
    from boardroom_os.proving.v2_090f_prd_agent_team import execute_v2_090k_behavior_probe
    from boardroom_os.workspace.run_manifest import (
        RunManifestBehaviorAssertion,
        RunManifestBehaviorAssertionKind,
        RunManifestBehaviorProbe,
        RunManifestBehaviorStep,
    )

    client = _FakeHttpClient(
        [
            _FakeResponse(
                200,
                {
                    "status": "ok",
                    "item": {"id": "agent-123", "state": "active"},
                    "items": [{"id": "agent-123"}, {"id": "agent-456"}],
                },
            )
        ]
    )
    probe = RunManifestBehaviorProbe(
        probe_id=ContractId(value="probe.assertions"),
        service_command_id=ContractId(value="serve-agent-api"),
        acceptance_refs=(AcceptanceRef(value="AC-AGENT-CUSTOM"),),
        steps=(
            RunManifestBehaviorStep(
                step_id="assert",
                method="GET",
                path="/custom-items",
                json_body=None,
                expect_status=200,
                capture={},
                assertions=(
                    RunManifestBehaviorAssertion(
                        kind=RunManifestBehaviorAssertionKind.JSON_EQUALS,
                        target="$.status",
                        expected="ok",
                    ),
                    RunManifestBehaviorAssertion(
                        kind=RunManifestBehaviorAssertionKind.JSON_CONTAINS,
                        target="$.items[*].id",
                        expected="agent-123",
                    ),
                    RunManifestBehaviorAssertion(
                        kind=RunManifestBehaviorAssertionKind.FIELD_EQUALS,
                        target="$.item.state",
                        expected="active",
                    ),
                    RunManifestBehaviorAssertion(
                        kind=RunManifestBehaviorAssertionKind.FIELD_ABSENT,
                        target="$.item.deleted_at",
                    ),
                ),
            ),
        ),
    )

    result = execute_v2_090k_behavior_probe(
        probe=probe,
        base_url="http://127.0.0.1:8123",
        http_client=client,
    )

    assert result["passed"] is True


def test_behavior_probe_executor_fails_closed_on_missing_capture() -> None:
    from boardroom_os.contracts.types import AcceptanceRef, ContractId
    from boardroom_os.proving.v2_090f_prd_agent_team import execute_v2_090k_behavior_probe
    from boardroom_os.workspace.run_manifest import RunManifestBehaviorProbe, RunManifestBehaviorStep

    client = _FakeHttpClient([_FakeResponse(201, {"item": {}})])
    probe = RunManifestBehaviorProbe(
        probe_id=ContractId(value="probe.missing-capture"),
        service_command_id=ContractId(value="serve-agent-api"),
        acceptance_refs=(AcceptanceRef(value="AC-AGENT-CUSTOM"),),
        steps=(
            RunManifestBehaviorStep(
                step_id="create",
                method="POST",
                path="/custom-items",
                json_body={},
                expect_status=201,
                capture={"item_id": "$.item.id"},
                assertions=(),
            ),
        ),
    )

    with pytest.raises(ValueError, match="capture item_id"):
        execute_v2_090k_behavior_probe(
            probe=probe,
            base_url="http://127.0.0.1:8123",
            http_client=client,
        )


def test_behavior_probe_executor_fails_closed_on_bad_status_or_assertion() -> None:
    from boardroom_os.contracts.types import AcceptanceRef, ContractId
    from boardroom_os.proving.v2_090f_prd_agent_team import execute_v2_090k_behavior_probe
    from boardroom_os.workspace.run_manifest import (
        RunManifestBehaviorAssertion,
        RunManifestBehaviorAssertionKind,
        RunManifestBehaviorProbe,
        RunManifestBehaviorStep,
    )

    status_probe = RunManifestBehaviorProbe(
        probe_id=ContractId(value="probe.bad-status"),
        service_command_id=ContractId(value="serve-agent-api"),
        acceptance_refs=(AcceptanceRef(value="AC-AGENT-CUSTOM"),),
        steps=(
            RunManifestBehaviorStep(
                step_id="list",
                method="GET",
                path="/custom-items",
                json_body=None,
                expect_status=200,
                capture={},
                assertions=(),
            ),
        ),
    )
    with pytest.raises(ValueError, match="expected status 200"):
        execute_v2_090k_behavior_probe(
            probe=status_probe,
            base_url="http://127.0.0.1:8123",
            http_client=_FakeHttpClient([_FakeResponse(500, {"error": "boom"})]),
        )

    assertion_probe = status_probe.model_copy(
        update={
            "probe_id": ContractId(value="probe.bad-assertion"),
            "steps": (
                status_probe.steps[0].model_copy(
                    update={
                        "assertions": (
                            RunManifestBehaviorAssertion(
                                kind=RunManifestBehaviorAssertionKind.FIELD_EQUALS,
                                target="$.status",
                                expected="ok",
                            ),
                        )
                    }
                ),
            ),
        }
    )
    with pytest.raises(ValueError, match="assertion failed"):
        execute_v2_090k_behavior_probe(
            probe=assertion_probe,
            base_url="http://127.0.0.1:8123",
            http_client=_FakeHttpClient([_FakeResponse(200, {"status": "wrong"})]),
        )
```

- [ ] **Step 4: Run tests and verify failure**

Run:

```bash
PYTHONPATH=src:. python -m pytest tests/proving/test_v2_090k_dynamic_closeout_contract.py -q --tb=short
```

Expected before implementation: FAIL because the helpers do not exist.

- [ ] **Step 5: Implement dynamic env resolver**

Add:

```python
def resolve_v2_090k_service_environment(
    *,
    bindings: tuple[RunManifestEnvironmentBinding, ...],
    host: str,
    port: int,
    temp_sqlite_path: Path,
) -> dict[str, str]:
    values = {
        RunManifestEnvironmentValueSource.RUNTIME_HOST: host,
        RunManifestEnvironmentValueSource.RUNTIME_PORT: str(port),
        RunManifestEnvironmentValueSource.TEMP_SQLITE_PATH: str(temp_sqlite_path),
    }
    resolved: dict[str, str] = {}
    for binding in bindings:
        if binding.value_source is RunManifestEnvironmentValueSource.LITERAL:
            if binding.literal_value is None:
                raise ValueError("literal env binding requires literal_value")
            resolved[binding.name] = binding.literal_value
        else:
            resolved[binding.name] = values[binding.value_source]
    return resolved
```

- [ ] **Step 6: Implement JSON path extraction and interpolation helpers**

Add imports:

```python
import re
from typing import Mapping

from boardroom_os.workspace.run_manifest import (
    RunManifestBehaviorAssertion,
    RunManifestBehaviorAssertionKind,
    RunManifestBehaviorProbe,
)
```

Add:

```python
def extract_v2_090k_json_path(payload: Any, path: str) -> Any:
    if not path.startswith("$."):
        raise ValueError(f"unsupported JSON path: {path}")
    current: Any = payload
    for token in path[2:].split("."):
        if token.endswith("[*]"):
            key = token[:-3]
            if not isinstance(current, dict) or key not in current or not isinstance(current[key], list):
                raise ValueError(f"JSON path not found: {path}")
            current = current[key]
            continue
        if "[*]" in token:
            key, child = token.split("[*]", 1)
            child = child.lstrip(".")
            if not isinstance(current, dict) or key not in current or not isinstance(current[key], list):
                raise ValueError(f"JSON path not found: {path}")
            if child:
                values = []
                for item in current[key]:
                    if not isinstance(item, dict) or child not in item:
                        raise ValueError(f"JSON path not found: {path}")
                    values.append(item[child])
                current = values
            else:
                current = current[key]
            continue
        if isinstance(current, list):
            values = []
            for item in current:
                if not isinstance(item, dict) or token not in item:
                    raise ValueError(f"JSON path not found: {path}")
                values.append(item[token])
            current = values
            continue
        if not isinstance(current, dict) or token not in current:
            raise ValueError(f"JSON path not found: {path}")
        current = current[token]
    return current
```

Add:

```python
_CAPTURE_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


def interpolate_v2_090k_value(value: Any, captures: Mapping[str, Any]) -> Any:
    if isinstance(value, str):
        exact = _CAPTURE_PATTERN.fullmatch(value)
        if exact:
            key = exact.group(1)
            if key not in captures:
                raise ValueError(f"capture {key} is required")
            return captures[key]
        def replace(match: re.Match[str]) -> str:
            key = match.group(1)
            if key not in captures:
                raise ValueError(f"capture {key} is required")
            return str(captures[key])
        return _CAPTURE_PATTERN.sub(replace, value)
    if isinstance(value, list):
        return [interpolate_v2_090k_value(item, captures) for item in value]
    if isinstance(value, dict):
        return {
            key: interpolate_v2_090k_value(item, captures)
            for key, item in value.items()
        }
    return value
```

Supported JSON path syntax is intentionally small and fail-closed: `$.field`, `$.field.child`, `$.items[*]`, and `$.items[*].field`. Do not silently return `None` for missing paths.

- [ ] **Step 7: Implement assertion evaluator and probe executor**

Add:

```python
def evaluate_v2_090k_behavior_assertion(
    *,
    payload: Any,
    assertion: RunManifestBehaviorAssertion,
    captures: Mapping[str, Any],
) -> None:
    expected = interpolate_v2_090k_value(assertion.expected, captures)

    if assertion.kind is RunManifestBehaviorAssertionKind.FIELD_ABSENT:
        try:
            extract_v2_090k_json_path(payload, assertion.target)
        except ValueError:
            return
        raise ValueError(f"assertion failed: field must be absent at {assertion.target}")

    actual = extract_v2_090k_json_path(payload, assertion.target)
    if assertion.kind is RunManifestBehaviorAssertionKind.JSON_EQUALS:
        if actual != expected:
            raise ValueError(f"assertion failed: {assertion.target} expected {expected!r} got {actual!r}")
        return
    if assertion.kind is RunManifestBehaviorAssertionKind.FIELD_EQUALS:
        if actual != expected:
            raise ValueError(f"assertion failed: {assertion.target} expected {expected!r} got {actual!r}")
        return
    if assertion.kind is RunManifestBehaviorAssertionKind.JSON_CONTAINS:
        if isinstance(actual, list) and expected in actual:
            return
        if isinstance(actual, dict) and isinstance(expected, dict) and all(actual.get(key) == value for key, value in expected.items()):
            return
        if isinstance(actual, str) and isinstance(expected, str) and expected in actual:
            return
        raise ValueError(f"assertion failed: {assertion.target} does not contain {expected!r}")

    raise ValueError(f"unsupported behavior assertion kind: {assertion.kind}")
```

Add:

```python
def execute_v2_090k_behavior_probe(
    *,
    probe: RunManifestBehaviorProbe,
    base_url: str,
    http_client: Any,
    timeout_seconds: float = 10.0,
) -> dict[str, Any]:
    captures: dict[str, Any] = {}
    step_results: list[dict[str, Any]] = []
    base = base_url.rstrip("/")
    for step in probe.steps:
        path = interpolate_v2_090k_value(step.path, captures)
        if not isinstance(path, str) or not path.startswith("/"):
            raise ValueError(f"behavioral probe step path must start with /: {step.step_id}")
        body = interpolate_v2_090k_value(step.json_body, captures)
        response = http_client.request(
            step.method,
            f"{base}{path}",
            json=body,
            timeout=timeout_seconds,
        )
        if response.status_code != step.expect_status:
            raise ValueError(
                f"behavioral probe step {step.step_id} expected status {step.expect_status} got {response.status_code}"
            )
        payload = response.json()
        for capture_name, capture_path in step.capture.items():
            captured = extract_v2_090k_json_path(payload, capture_path)
            if captured is None:
                raise ValueError(f"capture {capture_name} is empty")
            captures[capture_name] = captured
        for assertion in step.assertions:
            evaluate_v2_090k_behavior_assertion(
                payload=payload,
                assertion=assertion,
                captures=captures,
            )
        step_results.append(
            {
                "step_id": step.step_id,
                "method": step.method,
                "path": path,
                "status_code": response.status_code,
                "captures_after_step": dict(captures),
            }
        )
    return {
        "probe_id": probe.probe_id.value,
        "service_command_id": probe.service_command_id.value,
        "acceptance_refs": [acceptance_ref.value for acceptance_ref in probe.acceptance_refs],
        "passed": True,
        "captures": captures,
        "steps": step_results,
    }
```

- [ ] **Step 8: Replace fixed closeout startup and `_probe_v2_090f_crud_workflow`**

In `run_v2_090f_closeout_stage`:

- Load `00-boardroom/generated-package-contract.json`;
- Load `20-evidence/tests/run-manifest.json`;
- Select service contracts from run manifest, not command text;
- Bind dynamic env with `resolve_v2_090k_service_environment`;
- Start service with `ServiceRunner`;
- Execute typed `RunManifestBehaviorProbe` values with `execute_v2_090k_behavior_probe`;
- Write `20-evidence/tests/live-blackbox.json` from declared behavior probe results.

Delete `_probe_v2_090f_crud_workflow`. Do not replace it with another domain-specific function.

- [ ] **Step 9: Assert no fixed interface or business domain remains in active code**

Run:

```bash
rg -n "python -m app.server|LIBRARY_API_HOST|LIBRARY_API_PORT|LIBRARY_DB_PATH|app/server.py|_probe_v2_090f_crud_workflow|\"/books\"|\"Dune\"|\"Frank Herbert\"|\"checked_out\"|AC-V2-090F|_source_surface_for_project_path|_acceptance_refs_for_project_path|_v2_090f_acceptance_refs" \
  src tests scripts config \
  --glob '!tests/negative/test_v2_090k_autonomy_regression_fail_closed.py'
```

Expected: no active source/test/script/config match enforcing old V2-090F startup, domain, acceptance, or source-surface assumptions. The V2-090K negative regression test may still contain forbidden literals as test data.

- [ ] **Step 10: Re-run dynamic closeout tests**

Run:

```bash
PYTHONPATH=src:. python -m pytest tests/proving/test_v2_090k_dynamic_closeout_contract.py tests/execution/test_service_runner.py tests/execution/test_service_runner_environment.py -q --tb=short
```

Expected: PASS.

---

## Task 7: Checker and Closeout Provider Attempts

**Files:**
- Modify: `src/boardroom_os/proving/v2_090f_prd_agent_team.py`
- Create: `tests/proving/test_v2_090k_checker_closeout_roles.py`
- Modify: `tests/negative/test_v2_090f_agent_team_fail_closed.py`

- [ ] **Step 1: Write failing tests for missing role attempts**

Create `tests/proving/test_v2_090k_checker_closeout_roles.py`:

```python
from __future__ import annotations

import pytest


def test_closeout_requires_checker_provider_attempt() -> None:
    from boardroom_os.proving.v2_090f_prd_agent_team import validate_v2_090k_checker_closeout_attempts

    with pytest.raises(ValueError, match="Checker ProviderAttempt"):
        validate_v2_090k_checker_closeout_attempts(
            checker_artifact={},
            closeout_artifact={"provider_attempt_ref": "provider-attempt.closeout"},
        )


def test_closeout_requires_closeout_provider_attempt() -> None:
    from boardroom_os.proving.v2_090f_prd_agent_team import validate_v2_090k_checker_closeout_attempts

    with pytest.raises(ValueError, match="Closeout ProviderAttempt"):
        validate_v2_090k_checker_closeout_attempts(
            checker_artifact={"provider_attempt_ref": "provider-attempt.checker"},
            closeout_artifact={},
        )


def test_helper_written_checker_verdict_does_not_satisfy_closeout() -> None:
    from boardroom_os.proving.v2_090f_prd_agent_team import validate_v2_090k_checker_closeout_attempts

    with pytest.raises(ValueError, match="Checker ProviderAttempt"):
        validate_v2_090k_checker_closeout_attempts(
            checker_artifact={"approved": True, "source": "helper"},
            closeout_artifact={"provider_attempt_ref": "provider-attempt.closeout"},
        )
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
PYTHONPATH=src:. python -m pytest tests/proving/test_v2_090k_checker_closeout_roles.py -q --tb=short
```

Expected before implementation: FAIL because helper does not exist.

- [ ] **Step 3: Implement checker/closeout validation**

Add:

```python
def validate_v2_090k_checker_closeout_attempts(
    *,
    checker_artifact: dict[str, Any],
    closeout_artifact: dict[str, Any],
) -> None:
    if not checker_artifact.get("provider_attempt_ref"):
        raise ValueError("Checker ProviderAttempt is required before closeout")
    if not closeout_artifact.get("provider_attempt_ref"):
        raise ValueError("Closeout ProviderAttempt is required before closeout")
```

- [ ] **Step 4: Add provider-backed role invocation**

In closeout stage:

- Build checker ExecutionPackage（检查执行包） from final evidence table, source inventory, RunManifest, worker evidence, and live probe evidence.
- Invoke checker provider adapter and write `30-audit/checker-verdict.json`.
- Build closeout ExecutionPackage（收尾执行包） from checker verdict, evidence map, and release manifest.
- Invoke closeout provider adapter and write `30-audit/closeout-draft.json`.
- Call `validate_v2_090k_checker_closeout_attempts`.
- Only then build programmatic CloseoutGate input（收尾门禁输入）.

The helper may normalize and verify returned JSON, but must not invent `approved=True` or `passed=True` without provider artifacts.

- [ ] **Step 5: Re-run tests**

Run:

```bash
PYTHONPATH=src:. python -m pytest tests/proving/test_v2_090k_checker_closeout_roles.py tests/negative/test_v2_090f_agent_team_fail_closed.py -q --tb=short
```

Expected: PASS.

---

## Task 8: Default Sample Promotion and `--check`

**Files:**
- Modify: `src/boardroom_os/proving/v2_090f_prd_agent_team.py`
- Modify: `scripts/build_tiny_closeout_sample.py`
- Test: `tests/proving/test_v2_090f_prd_agent_team_script.py`

- [ ] **Step 1: Add explicit marker helper**

Add:

```python
def require_v2_090f_marker(path: Path) -> None:
    marker = path / V2_090F_MARKER
    if not marker.is_file():
        raise ValueError("missing V2-090F marker")
```

Use it in `reset_v2_090f_workspace` and sample promotion code.

- [ ] **Step 2: Add real red test for default sample baseline mismatch**

Append to `tests/proving/test_v2_090f_prd_agent_team_script.py`:

```python
def test_sample_check_rejects_missing_sample_manifest(tmp_path: Path) -> None:
    from boardroom_os.proving.v2_090f_prd_agent_team import check_v2_090f_sample_tree

    sample_root = tmp_path / "tiny-fullstack"
    (sample_root / "00-boardroom").mkdir(parents=True)
    (sample_root / "00-boardroom" / "agent-team-role-context.json").write_text(
        '{"entries": {}}',
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="sample-manifest.json"):
        check_v2_090f_sample_tree(sample_root)
```

This is a real red test only if `check_v2_090f_sample_tree` does not already check `sample-manifest.json`; if it already does, replace with a baseline hash mismatch test using the actual sample manifest fields.

- [ ] **Step 3: Ensure `--check` default path is explicit**

`scripts/build_tiny_closeout_sample.py --check` must default to:

```text
examples/generated-workspaces/tiny-fullstack
```

It must:

- not call provider;
- not write output root;
- fail if `00-boardroom/agent-team-role-context.json` is missing;
- fail if `sample-manifest.json` is missing or its baseline hash does not match current baseline;
- fail if forbidden runtime files exist.

- [ ] **Step 4: Add promotion helper**

Add:

```python
def promote_v2_090f_sample(
    *,
    staging_output_root: Path,
    published_output_root: Path = Path("examples/generated-workspaces/tiny-fullstack"),
) -> None:
    check_v2_090f_sample_tree(staging_output_root)
    if published_output_root.exists():
        require_v2_090f_marker(published_output_root)
        shutil.rmtree(published_output_root)
    shutil.copytree(staging_output_root, published_output_root)
    check_v2_090f_sample_tree(published_output_root)
```

Do not copy provider secrets, runtime SQLite DB files, `.pytest*`, `__pycache__`, `.pyc`, or temp port files.

- [ ] **Step 5: Run script tests**

Run:

```bash
PYTHONPATH=src:. python -m pytest tests/proving/test_v2_090f_prd_agent_team_script.py -q --tb=short
```

Expected: PASS.

---

## Task 9: Real Provider Full Run and Failure Report

**Files:**
- Test: `tests/proving/test_v2_090f_prd_agent_team_real.py`
- Script: `scripts/run_v2_090f_prd_agent_team.py`

- [ ] **Step 1: Run non-provider targeted suite**

Run:

```bash
PYTHONPATH=src:. python -m pytest \
  tests/negative/test_v2_090k_autonomy_regression_fail_closed.py \
  tests/workspace/test_run_manifest_service_contract.py \
  tests/workspace/test_run_manifest_behavioral_probe.py \
  tests/proving/test_v2_090k_dynamic_closeout_contract.py \
  tests/proving/test_v2_090k_evidence_authority.py \
  tests/proving/test_v2_090k_checker_closeout_roles.py \
  tests/negative/test_v2_090f_agent_team_fail_closed.py \
  tests/proving/test_v2_090f_prd_agent_team_script.py \
  tests/proving/test_run_manifest.py \
  tests/execution/test_service_runner.py \
  tests/execution/test_service_runner_environment.py \
  -q --tb=short --basetemp .pytest-tmp-v2090k-targeted
```

Expected: PASS.

- [ ] **Step 2: Run real provider proving**

Run:

```bash
set -a; source /Users/bill/projects/boardroom-os/.env; set +a
BOARDROOM_RUNTIME_CONFIG=config/boardroom-runtime.v2-090f.yaml \
BOARDROOM_PROVIDERS_CONFIG=config/boardroom-providers.v2-090f.yaml \
BOARDROOM_ROLES_CONFIG=config/boardroom-roles.v2-090f.yaml \
BOARDROOM_RUN_REAL_PROVIDER_PROVING=1 \
PYTHONPATH=src:/Users/bill/projects/atomic-agent/src:. \
python -m pytest tests/proving/test_v2_090f_prd_agent_team_real.py::test_v2_090f_prd_agent_team_real_provider \
  -q --tb=short --basetemp .pytest-tmp-v2090k-real-full
```

Expected for success: PASS. Evidence must show:

- planning includes CEO, Architect, Tester, Release/DevOps provider attempts;
- AcceptanceContract, PackageContract, TicketGraph, RunManifest, and BehavioralProbePlan come from role artifacts;
- worker tickets are generated by agent artifacts, not runner fixed graph;
- Checker and Closeout provider attempts exist;
- RunManifest service contracts are consumed for startup/env/readiness;
- behavioral probes are executed from declared steps, not runner `/books` code;
- FinalEvidenceTable and SourceInventory consume agent-generated contracts;
- CloseoutGate passes.

Expected for failure: exit non-zero and write a run report classifying the failure as one of:

- `provider_failure`;
- `planning_contract_missing`;
- `run_manifest_invalid`;
- `behavioral_probe_failed`;
- `source_surface_unmapped`;
- `checker_rejected`;
- `closeout_gate_blocked`;
- `sample_publish_failed`.

- [ ] **Step 3: Promote default sample after success**

Run:

```bash
PYTHONPATH=src:. python scripts/run_v2_090f_prd_agent_team.py \
  --prd examples/directives/tiny-fullstack-prd.md \
  --output-root .evidence/v2-090k-real-worker-output \
  --publish examples/generated-workspaces/tiny-fullstack
```

Expected: exit 0 and publish `examples/generated-workspaces/tiny-fullstack`.

- [ ] **Step 4: Verify default sample check**

Run:

```bash
PYTHONPATH=src:. python scripts/build_tiny_closeout_sample.py --check
```

Expected: exit 0 and no file changes.

- [ ] **Step 5: Verify no active hardcoded knowledge remains**

Run:

```bash
rg -n "app/server.py|python -m app.server|LIBRARY_API_HOST|LIBRARY_API_PORT|LIBRARY_DB_PATH|backend API, SQLite persistence, static frontend|_probe_v2_090f_crud_workflow|\"/books\"|\"Dune\"|\"Frank Herbert\"|\"checked_out\"|AC-V2-090F|_source_surface_for_project_path|_acceptance_refs_for_project_path|_v2_090f_acceptance_refs" \
  src tests scripts config \
  --glob '!tests/negative/test_v2_090k_autonomy_regression_fail_closed.py'
```

Expected: no active implementation/test/config match that enforces old V2-090F startup, domain, acceptance, or source-surface assumptions. Historical docs and the dedicated V2-090K negative regression test may retain mentions.

---

## Task 10: Documentation and Status Update

**Files:**
- Modify: `doc/04-implementation/backlog.md`
- Modify: `doc/04-implementation/acceptance-criteria.md`
- Modify: `doc/05-project-log/2026-06.md`
- Modify: `doc/05-project-log/decisions.md`
- Modify: `doc/04-implementation/INDEX.md`
- Modify: `doc/05-project-log/INDEX.md`

- [ ] **Step 1: Update status only after Task 9 passes**

If real provider full run and default `--check` pass:

- Mark V2-090K `DONE`.
- Mark V2-090F `DONE` only if V2-090K evidence fully satisfies the original V2-090F acceptance row.
- Record run ID, event stream root, provider attempt refs, command evidence, service evidence, behavioral probe evidence, source inventory evidence, closeout gate result, and default sample path.

If Task 9 fails:

- Keep V2-090K `BLOCKED` or `IN_PROGRESS`.
- Keep V2-090F `REVIEW_REQUIRED` / `BLOCKED`.
- Record failure evidence and failure taxonomy without weakening gates.

- [ ] **Step 2: Run doc consistency checks**

Run:

```bash
rg -n "V2-090K|090K|agent team autonomy remediation|AcceptanceContract|PackageContract|RunManifest|BehavioralProbe|SourceInventory|seat.release.devops|DEC-0023" docs/superpowers doc/04-implementation doc/05-project-log
git diff --check
```

Expected: references exist in spec/plan/index/log/backlog/acceptance; no whitespace errors.

---

## Self-Review Checklist

- [ ] Spec coverage: every V2-090K spec requirement maps to a task above.
- [ ] No fixed source layout, env names, endpoints, seeded data, acceptance refs, or source-surface path prefixes are introduced as required success conditions.
- [ ] Behavioral probes are agent-declared and runner-executed.
- [ ] FinalEvidenceTable and SourceInventory consume AcceptanceContract and PackageContract as their authority sources.
- [ ] Checker and Closeout remain provider-backed roles, not helper-written verdicts.
- [ ] Existing ServiceRunner（服务运行器）、RunManifest（运行清单） and evidence gates（证据门禁） are extended instead of duplicated.
- [ ] Real provider proof and default sample `--check` are required before any DONE status change.
