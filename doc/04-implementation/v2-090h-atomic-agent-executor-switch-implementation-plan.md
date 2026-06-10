# V2-090H Atomic-agent Executor Switch Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Switch Boardroom OS（董事会操作系统） implementation tickets（实施任务） from single-shot `ProviderExecutor`（模型供应商执行器） source delivery to a real provider-backed atomic-agent executor（模型供应商支撑的原子智能体执行器）, with three-file configuration and fail-closed evidence projection.

**Architecture:** V2-090H adds an explicit configuration layer and an `AtomicAgentExecutor`（原子智能体执行器） boundary. Config files define runtime defaults, OpenAI-compatible provider profiles（OpenAI 兼容供应商配置档）, and role slot bindings（角色席位绑定）; the executor compiles `ExecutionPackage`（执行包） plus selected configs into `AgentInvocation`（智能体调用） and `OpenAICompatibleProviderOptions`（OpenAI 兼容供应商选项）, invokes atomic-agent through `AgentRuntimePort`（智能体运行端口）, then validates/projects returned facts through the existing V2-090G validator/projector. Governance remains in Boardroom reducers, EvidenceVerifier（证据验证器）, Checker（检查者）, and CloseoutGate（收尾门禁）.

**Tech Stack:** Python 3.11+, Pydantic v2 models（Pydantic 模型）, PyYAML, pytest, external `atomic-agent` package from `BOARDROOM_ATOMIC_AGENT_PATH`（默认 `../atomic-agent`）, atomic-agent `OpenAICompatibleProviderAdapter` / `AgentLoop` / `BoardroomAgentRuntimePortAdapter`, existing Boardroom execution/evidence models.

---

## File Structure

- Create `config/boardroom-runtime.example.yaml`
  - Example runtime config（运行时配置） for atomic-agent executor: execution mode, event/artifact roots, default tools, runtime budgets, filesystem/command/network tool limits.
- Create `config/boardroom-providers.example.yaml`
  - Example OpenAI-compatible providers config（供应商配置）. First version supports only `provider_type: openai_compatible`.
- Create `config/boardroom-roles.example.yaml`
  - Example role slot config（角色席位配置） binding Boardroom seats to provider profile refs, model execution profile ids, skill refs, tool sets, and budget overrides.
- Create `doc/06-reference/atomic-agent-contract-lock.md`
  - Auditable contract lock（契约锁定清单） for external atomic-agent docs/source hashes, active model fields, and canonical event stream format. This is not a second source of truth; it is the reviewed compatibility lock.
- Modify `.env.template`
  - Keep only config paths, secret env names, and bootstrap/local paths.
- Modify `.env.example`
  - Same shape as `.env.template`; remove old `BOARDROOM_OPENAI_*` model parameters.
- Create `src/boardroom_os/config/__init__.py`
  - Public exports for Boardroom config models and loader.
- Create `src/boardroom_os/config/boardroom.py`
  - Pydantic config schemas, YAML loading, config hash calculation, `.env` parsing, stale env detection, cross-file validation, provider options compilation.
- Modify `src/boardroom_os/execution/atomic_agent.py`
  - Extend `AtomicInvocationCompiler`（原子调用编译器） so it consumes runtime/provider/role config instead of constructor-only defaults; keep V2-090G behavior behind explicit test fixtures only if needed.
- Create `src/boardroom_os/execution/atomic_executor.py`
  - `AtomicExecutionRequest`（原子执行请求）, `AtomicExecutionResult`（原子执行结果）, `AtomicAgentRuntimeFactory`（原子智能体运行时工厂）, `AtomicAgentExecutor`（原子智能体执行器）, and provider-attempt projection from atomic event stream.
- Modify `src/boardroom_os/execution/__init__.py`
  - Export the new executor/config-facing execution types after tests prove stable names.
- Create `tests/config/test_boardroom_config.py`
  - Happy-path config loading, config hashing, provider options compilation, and role/provider cross-reference tests.
- Create `tests/negative/test_boardroom_config_fail_closed.py`
  - Missing config, stale `.env`, unsupported provider type, unknown references, raw secret leakage, and bad budgets fail-closed tests.
- Modify `tests/execution/test_atomic_agent_invocation_compiler.py`
  - Update compiler expectations to include `permission_policy.policy_ref`, full budgets, config hashes, role slot metadata, and provider profile from `OpenAICompatibleProviderOptions.to_provider_profile()`.
- Create `tests/execution/test_atomic_agent_executor.py`
  - Unit tests for executor wiring with scripted/fake `AgentRuntimePort` that is allowed only for unit tests, plus provider attempt projection from event stream.
- Create `tests/negative/test_atomic_agent_executor_fail_closed.py`
  - Implementation ticket routed to `ProviderExecutor`, missing runtime port, missing provider turn facts, missing command evidence, fake provider transport in real proving path, and direct governance completion fail-closed tests.
- Create `tests/proving/test_tiny_atomic_agent_executor.py`
  - Real provider-backed minimal atomic implementation ticket proving path. This test may be marked/skipped unless explicit real-provider env is present, but when enabled it must use real OpenAI-compatible transport and cannot use fake provider transport.
- Create `scripts/run_tiny_atomic_agent_executor.py`
  - Manual proving helper that loads the three config files, runs the minimal atomic ticket, writes evidence, and prints result refs. It is not a stable execution API.
- Modify `README.md`
  - Document three-file config, `.env` scope, OpenAI-compatible-only first provider protocol, and V2-090H executor boundary.
- Modify `doc/04-implementation/INDEX.md`
  - Register this spec and plan.
- Modify `doc/04-implementation/backlog.md`, `doc/04-implementation/acceptance-criteria.md`, and `doc/05-project-log/2026-06.md` only during actual implementation closeout, not in this spec/plan drafting pass.

---

## Expert-review hardening requirements（专家评审加固要求）

The following requirements amend all tasks below and must be implemented before V2-090H can be marked DONE:

1. **Dependency lock** — add `doc/06-reference/atomic-agent-contract-lock.md` and validate atomic-agent contract hashes / active model fields. Do not rely on version alone while `atomic-agent.__version__` remains `0.0.0`.
2. **Configurable atomic-agent path** — use `BOARDROOM_ATOMIC_AGENT_PATH`, default `../atomic-agent`; no task may hardcode `../atomic-agent` except as that documented default.
3. **Execution policy** — add explicit timeout/retry/interruption semantics. Provider timeout does not retry by default; runtime crash can retry at most once only if no workspace mutation occurred.
4. **Canonical event stream** — validate `jsonl-utf8-lf-canonical-json-v1`; reject CRLF, non-UTF-8, empty lines, non-canonical JSON, and hash mismatches.
5. **Serial workspace execution** — V2-090H first version is `serial_per_workspace`; no concurrent atomic execution in the same generated package workspace.
6. **Human-readable safe errors** — include path / command_id / policy refs in errors, but never leak API keys or full raw provider output.
7. **Budget/tool/command parameterization** — budget profiles and role overrides live in YAML, resolved budget snapshots are audited, tools are resolved from runtime/role/tool_permissions/skills/evidence requirements, and declared command ids come only from `ExecutionPackage.commands`.

---

## Pre-flight before implementation

- [ ] **Step 0: Confirm Python 3.11+**

Run:

```bash
python -c "import sys; assert sys.version_info >= (3, 11), 'Python 3.11+ required'; print(sys.version)"
```

Expected: prints Python 3.11 or newer. If this fails, stop; atomic-agent and Boardroom V2 are Python 3.11+ codebases.

- [ ] **Step 1: Confirm branch and worktree state**

Run:

```bash
git status --short --branch
```

Expected:

```text
## rebuild/v2-clean-foundation...origin/rebuild/v2-clean-foundation [ahead 2]
```

Additional uncommitted files may be present only if they are the approved V2-090H spec/plan documents. If unrelated changes appear, stop and ask the user how to handle them.

- [ ] **Step 2: Confirm configurable atomic-agent checkout and install**

Run:

```bash
python - <<'PY'
import os
from pathlib import Path
path = Path(os.environ.get("BOARDROOM_ATOMIC_AGENT_PATH", "../atomic-agent")).expanduser().resolve()
print(path)
print("exists=" + str(path.is_dir()))
if ".worktrees" in path.parts:
    raise SystemExit("BOARDROOM_ATOMIC_AGENT_PATH must not point at .worktrees/atomic-agent")
PY
python -m pip install -e "${BOARDROOM_ATOMIC_AGENT_PATH:-../atomic-agent}"
python -c "from atomic_agent import AgentRuntimePort; from atomic_agent.models import AgentInvocation, AgentRunResult; print('atomic-agent import ok')"
```

Expected: path exists, is not `.worktrees/atomic-agent`, editable install succeeds from `BOARDROOM_ATOMIC_AGENT_PATH` or its default `../atomic-agent`, and the final command prints `atomic-agent import ok`.

- [ ] **Step 3: Confirm atomic-agent active contract**

Run:

```bash
python - <<'PY'
from atomic_agent.models import AgentInvocation, AgentRunResult, AgentRunStatus
print(tuple(AgentInvocation.model_fields.keys()))
print(tuple(AgentRunResult.model_fields.keys()))
print(tuple(status.value for status in AgentRunStatus))
PY
```

Expected:

```text
('invocation_id', 'task', 'workspace_root', 'allowed_write_set', 'tools', 'permission_policy', 'provider_profile', 'budgets', 'output_requirements', 'role_context', 'skill_context', 'initial_files', 'metadata')
('run_id', 'status', 'event_stream_ref', 'events_hash', 'tool_attempts', 'workspace_mutations', 'artifacts', 'summary', 'failure_kind', 'failure_message', 'failed_action_ref')
('completed', 'failed', 'interrupted', 'requires_approval')
```

If this differs, update the spec and plan before implementation.

- [ ] **Step 3.5: Generate or verify atomic-agent contract lock inputs**

Run:

```bash
python - <<'PY'
import hashlib
import os
from pathlib import Path
root = Path(os.environ.get("BOARDROOM_ATOMIC_AGENT_PATH", "../atomic-agent")).expanduser().resolve()
for rel in [
    "docs/03-contracts/agent-runtime-port.md",
    "docs/03-contracts/agent-action-protocol.md",
    "docs/03-contracts/event-stream-protocol.md",
    "src/atomic_agent/models.py",
    "src/atomic_agent/event_recorder.py",
]:
    path = root / rel
    if not path.exists():
        raise SystemExit(f"missing atomic-agent contract input: {path}")
    print(rel, "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest())
PY
```

Expected: prints sha256 for every contract input. These hashes must be recorded in `doc/06-reference/atomic-agent-contract-lock.md` during implementation.

- [ ] **Step 4: Confirm PyYAML is available**

Run:

```bash
python - <<'PY'
import yaml
print(yaml.__version__)
PY
```

Expected: prints a PyYAML version such as `6.0.1`. If missing, add an explicit project dependency decision before implementing config loading.

---

### Task 1: Add example config files and slim `.env` templates

**Files:**
- Create: `config/boardroom-runtime.example.yaml`
- Create: `config/boardroom-providers.example.yaml`
- Create: `config/boardroom-roles.example.yaml`
- Modify: `.env.template`
- Modify: `.env.example`

- [ ] **Step 1: Create `config/boardroom-runtime.example.yaml`**

Write this exact file:

```yaml
version: 1
runtime_id: boardroom-runtime.local
execution:
  implementation_executor: atomic_agent
  reject_provider_executor_for_implementation: true
atomic_agent:
  package_name: atomic-agent
  import_name: atomic_agent
  runtime_port_contract_ref: atomic-agent.docs.agent-runtime-port.v1
  event_stream_root: .evidence/atomic-agent/events
  artifact_root: .evidence/atomic-agent/artifacts
  run_id_prefix: boardroom-atomic
  dependency:
    atomic_agent_path_env: BOARDROOM_ATOMIC_AGENT_PATH
    default_atomic_agent_path: ../atomic-agent
    contract_lock_ref: doc/06-reference/atomic-agent-contract-lock.md
    require_contract_hash_match: true
  execution_policy:
    wall_time_seconds: 900
    retry_on_provider_timeout: false
    retry_on_runtime_crash: true
    max_retries: 1
    interrupt_grace_period_seconds: 30
    retry_requires_no_workspace_mutation: true
  concurrency:
    mode: serial_per_workspace
    workspace_lock_root: .evidence/atomic-agent/locks
    require_run_scoped_event_artifact_roots: true
  default_tools:
    - list_files
    - read_file
    - search_files
    - write_file
    - apply_patch
    - run_command
    - submit_result
  required_tools:
    - submit_result
  tool_permission_map:
    filesystem.read:
      - list_files
      - read_file
      - search_files
    filesystem.write:
      - write_file
      - apply_patch
    command.execute:
      - run_command
    network.fetch:
      - web_fetch
  budget_profiles:
    atomic.proving.minimal:
      max_steps: 32
      max_parse_failures: 2
      max_observation_chars: 16000
      max_wall_seconds: 1200
    worker.implementation.default:
      max_steps: 96
      max_parse_failures: 3
      max_observation_chars: 24000
      max_wall_seconds: 3600
    worker.implementation.large:
      max_steps: 160
      max_parse_failures: 4
      max_observation_chars: 32000
      max_wall_seconds: 7200
  budget_caps:
    max_steps: 240
    max_parse_failures: 6
    max_observation_chars: 64000
    max_wall_seconds: 10800
  filesystem:
    default_read_limit: 12000
    max_read_limit: 50000
    default_max_entries: 200
    max_entries_limit: 1000
    default_max_matches: 50
    max_matches_limit: 500
  commands:
    default_timeout_seconds: 60
    max_timeout_seconds: 300
    max_output_bytes: 200000
  network:
    default: deny
    allow_rules: []
```

- [ ] **Step 2: Create `config/boardroom-providers.example.yaml`**

Write this exact file:

```yaml
version: 1
providers:
  - provider_profile_id: provider.openai-compatible.primary
    provider_type: openai_compatible
    provider_label: truerealbill-openai-compatible
    base_url: https://api.truerealbill.com/v1
    api_key_env: OPENAI_API_KEY
    model: gpt-5.5
    context_window_tokens: 400000
    max_output_tokens: 128000
    stream_idle_timeout_seconds: 120
    total_timeout_seconds: 600
    reasoning_effort: high
    temperature: null
    top_p: null
    presence_penalty: null
    frequency_penalty: null
    seed: null
    stop: null
    response_format: null
    stream_options: null
    service_tier: null
    user: boardroom-os
  - provider_profile_id: provider.openai-compatible.fast-worker
    provider_type: openai_compatible
    provider_label: fast-worker-openai-compatible
    base_url: https://api.truerealbill.com/v1
    api_key_env: OPENAI_API_KEY
    model: gpt-5.5-fast
    context_window_tokens: 400000
    max_output_tokens: 64000
    stream_idle_timeout_seconds: 90
    total_timeout_seconds: 420
    reasoning_effort: medium
    temperature: null
    top_p: null
    presence_penalty: null
    frequency_penalty: null
    seed: null
    stop: null
    response_format: null
    stream_options: null
    service_tier: null
    user: boardroom-os-fast-worker
```

- [ ] **Step 3: Create `config/boardroom-roles.example.yaml`**

Write this exact file:

```yaml
version: 1
role_slots:
  - seat_ref: seat.worker.implementation
    role_profile_ref: role.worker.implementation
    role_category: worker
    model_execution_profile_id: model-profile.worker.implementation.primary
    provider_profile_ref: provider.openai-compatible.primary
    skill_refs:
      - skill.filesystem.patch
      - skill.command.test
    default_tools:
      - list_files
      - read_file
      - search_files
      - write_file
      - apply_patch
      - run_command
      - submit_result
    budget_profile_ref: worker.implementation.default
    budgets_override:
      max_steps: 128
      max_wall_seconds: 5400
  - seat_ref: seat.worker.fast-fix
    role_profile_ref: role.worker.implementation
    role_category: worker
    model_execution_profile_id: model-profile.worker.fast-fix
    provider_profile_ref: provider.openai-compatible.fast-worker
    skill_refs:
      - skill.filesystem.patch
      - skill.command.test
    default_tools:
      - read_file
      - apply_patch
      - run_command
      - submit_result
    budget_profile_ref: atomic.proving.minimal
    budgets_override:
      max_steps: 48
      max_wall_seconds: 1800
    budgets_override:
      max_steps: 16
      max_parse_failures: 1
      max_observation_chars: 12000
      max_wall_seconds: 600
```

- [ ] **Step 4: Create `doc/06-reference/atomic-agent-contract-lock.md`**

Create a Markdown lock file with this structure, filling actual hashes from pre-flight Step 3.5:

```markdown
# Atomic-agent contract lock

## Purpose

This file records the reviewed external atomic-agent（原子智能体） contract inputs for Boardroom OS V2-090H. It is an audit lock, not a second source of truth. If any hash changes, V2-090H implementation must stop for contract review.

## Source

- atomic_agent_path_env: `BOARDROOM_ATOMIC_AGENT_PATH`
- default_atomic_agent_path: `../atomic-agent`
- package_name: `atomic-agent`
- import_name: `atomic_agent`

## Contract hashes

| Path | sha256 |
|---|---|
| `docs/03-contracts/agent-runtime-port.md` | `sha256:edc8c617f0cf35c2f8f257d39b8757de81c4e489d8c25872996037bcf2c1a50b` |
| `docs/03-contracts/agent-action-protocol.md` | `sha256:e9a8319b4d9a99d82bfeb08decd5eafb44e879293eb4bd3721ed3e6ce0fa03c5` |
| `docs/03-contracts/event-stream-protocol.md` | `sha256:2f67d46cf7bb73ed274a72b30a1e57f04adf19dca09a4770b6ef9e03bbff2b83` |
| `src/atomic_agent/models.py` | `sha256:0eaeb41dcfe643c68b3d3c632a19baa2bbca2b7a87fc7e6904e4febac6bd2c18` |
| `src/atomic_agent/event_recorder.py` | `sha256:685946430066b3dc6537c5f05b5777a35231e41b3fae3d624b3e8e553a993bf8` |

## Active model fields

- AgentInvocation: `invocation_id`, `task`, `workspace_root`, `allowed_write_set`, `tools`, `permission_policy`, `provider_profile`, `budgets`, `output_requirements`, `role_context`, `skill_context`, `initial_files`, `metadata`
- AgentRunResult: `run_id`, `status`, `event_stream_ref`, `events_hash`, `tool_attempts`, `workspace_mutations`, `artifacts`, `summary`, `failure_kind`, `failure_message`, `failed_action_ref`

## Event stream format

`jsonl-utf8-lf-canonical-json-v1`: one canonical JSON object per LF-terminated line, UTF-8, `sort_keys=True`, `separators=(",", ":")`, `ensure_ascii=False`; `events_hash` is sha256 of raw bytes.
```

- [ ] **Step 5: Replace `.env.template`**

Replace `.env.template` with:

```text
BOARDROOM_RUNTIME_CONFIG=config/boardroom-runtime.example.yaml
BOARDROOM_PROVIDERS_CONFIG=config/boardroom-providers.example.yaml
BOARDROOM_ROLES_CONFIG=config/boardroom-roles.example.yaml
OPENAI_API_KEY=
BOARDROOM_ATOMIC_AGENT_PATH=../atomic-agent
BOARDROOM_EVIDENCE_ROOT=.evidence
```

- [ ] **Step 6: Replace `.env.example`**

Replace `.env.example` with:

```text
BOARDROOM_RUNTIME_CONFIG=config/boardroom-runtime.example.yaml
BOARDROOM_PROVIDERS_CONFIG=config/boardroom-providers.example.yaml
BOARDROOM_ROLES_CONFIG=config/boardroom-roles.example.yaml
OPENAI_API_KEY=
BOARDROOM_ATOMIC_AGENT_PATH=../atomic-agent
BOARDROOM_EVIDENCE_ROOT=.evidence
```

- [ ] **Step 7: Verify removed stale env keys**

Run:

```bash
python - <<'PY'
from pathlib import Path
for path in [Path('.env.template'), Path('.env.example')]:
    text = path.read_text(encoding='utf-8')
    banned = [line for line in text.splitlines() if line.startswith('BOARDROOM_OPENAI_')]
    if banned:
        raise SystemExit(f'{path} still contains stale model config keys: {banned}')
print('env templates slimmed')
PY
```

Expected: `env templates slimmed`.

---

### Task 2: Add config model happy-path tests

**Files:**
- Create: `tests/config/test_boardroom_config.py`
- Create later: `src/boardroom_os/config/__init__.py`
- Create later: `src/boardroom_os/config/boardroom.py`

- [ ] **Step 1: Write happy-path config tests**

Create `tests/config/test_boardroom_config.py` with:

```python
from __future__ import annotations

from pathlib import Path

from atomic_agent.providers.openai_compatible import OpenAICompatibleProviderOptions

from boardroom_os.config.boardroom import (
    BoardroomConfigPaths,
    BoardroomRuntimeConfig,
    BoardroomSettings,
    load_boardroom_settings,
)


def _write_config_files(tmp_path: Path) -> BoardroomConfigPaths:
    runtime = tmp_path / "runtime.yaml"
    providers = tmp_path / "providers.yaml"
    roles = tmp_path / "roles.yaml"
    runtime.write_text(
        """
version: 1
runtime_id: boardroom-runtime.test
execution:
  implementation_executor: atomic_agent
  reject_provider_executor_for_implementation: true
atomic_agent:
  package_name: atomic-agent
  import_name: atomic_agent
  runtime_port_contract_ref: atomic-agent.docs.agent-runtime-port.v1
  event_stream_root: .evidence/atomic-agent/events
  artifact_root: .evidence/atomic-agent/artifacts
  run_id_prefix: boardroom-atomic
  default_tools: [list_files, read_file, search_files, write_file, apply_patch, run_command, submit_result]
  required_tools: [submit_result]
  tool_permission_map:
    filesystem.read: [list_files, read_file, search_files]
    filesystem.write: [write_file, apply_patch]
    command.execute: [run_command]
    network.fetch: [web_fetch]
  budget_profiles:
    atomic.proving.minimal:
      max_steps: 32
      max_parse_failures: 2
      max_observation_chars: 16000
      max_wall_seconds: 1200
    worker.implementation.default:
      max_steps: 96
      max_parse_failures: 3
      max_observation_chars: 24000
      max_wall_seconds: 3600
  budget_caps:
    max_steps: 240
    max_parse_failures: 6
    max_observation_chars: 64000
    max_wall_seconds: 10800
  filesystem:
    default_read_limit: 12000
    max_read_limit: 50000
    default_max_entries: 200
    max_entries_limit: 1000
    default_max_matches: 50
    max_matches_limit: 500
  commands:
    default_timeout_seconds: 60
    max_timeout_seconds: 300
    max_output_bytes: 200000
  network:
    default: deny
    allow_rules: []
""".strip()
        + "\n",
        encoding="utf-8",
    )
    providers.write_text(
        """
version: 1
providers:
  - provider_profile_id: provider.openai-compatible.primary
    provider_type: openai_compatible
    provider_label: test-openai-compatible
    base_url: https://api.example.invalid/v1
    api_key_env: OPENAI_API_KEY
    model: gpt-5.5
    context_window_tokens: 400000
    max_output_tokens: 128000
    stream_idle_timeout_seconds: 120
    total_timeout_seconds: 600
    reasoning_effort: high
    temperature: null
    top_p: null
    presence_penalty: null
    frequency_penalty: null
    seed: null
    stop: null
    response_format: null
    stream_options: null
    service_tier: null
    user: boardroom-os
""".strip()
        + "\n",
        encoding="utf-8",
    )
    roles.write_text(
        """
version: 1
role_slots:
  - seat_ref: seat.worker.implementation
    role_profile_ref: role.worker.implementation
    role_category: worker
    model_execution_profile_id: model-profile.worker.implementation.primary
    provider_profile_ref: provider.openai-compatible.primary
    skill_refs: [skill.filesystem.patch, skill.command.test]
    default_tools: [list_files, read_file, search_files, write_file, apply_patch, run_command, submit_result]
    budget_profile_ref: worker.implementation.default
    budgets_override:
      max_steps: 128
      max_wall_seconds: 5400
""".strip()
        + "\n",
        encoding="utf-8",
    )
    return BoardroomConfigPaths(runtime_config=runtime, providers_config=providers, roles_config=roles)


def test_load_boardroom_settings_cross_links_runtime_provider_and_role(tmp_path, monkeypatch):
    paths = _write_config_files(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-secret")

    settings = load_boardroom_settings(paths, env_values={})

    assert isinstance(settings, BoardroomSettings)
    assert isinstance(settings.runtime, BoardroomRuntimeConfig)
    assert settings.runtime.execution.implementation_executor == "atomic_agent"
    assert settings.runtime.execution.reject_provider_executor_for_implementation is True
    assert settings.provider_by_id("provider.openai-compatible.primary").model == "gpt-5.5"
    role = settings.role_slot_by_seat("seat.worker.implementation")
    assert role.provider_profile_ref == "provider.openai-compatible.primary"
    assert settings.config_hashes.runtime_config_hash.startswith("sha256:")
    assert settings.config_hashes.providers_config_hash.startswith("sha256:")
    assert settings.config_hashes.roles_config_hash.startswith("sha256:")


def test_provider_profile_compiles_to_openai_compatible_options(tmp_path, monkeypatch):
    paths = _write_config_files(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-secret")
    settings = load_boardroom_settings(paths, env_values={})

    options = settings.openai_compatible_options("provider.openai-compatible.primary")

    assert isinstance(options, OpenAICompatibleProviderOptions)
    assert options.base_url == "https://api.example.invalid/v1"
    assert options.api_key == "sk-test-secret"
    assert options.model == "gpt-5.5"
    assert options.reasoning_effort == "high"
    assert options.to_provider_profile()["provider"] == "openai-compatible"
    assert "api_key" not in options.to_provider_profile()


def test_role_budget_profile_and_override_resolve_to_auditable_budget(tmp_path, monkeypatch):
    paths = _write_config_files(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-secret")
    settings = load_boardroom_settings(paths, env_values={})

    budget = settings.budgets_for_seat("seat.worker.implementation")

    assert budget["budget_profile_ref"] == "worker.implementation.default"
    assert budget["max_steps"] == 128
    assert budget["max_wall_seconds"] == 5400
    assert budget["max_parse_failures"] == 3


def test_role_budget_override_merges_with_runtime_defaults(tmp_path, monkeypatch):
    paths = _write_config_files(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-secret")
    settings = load_boardroom_settings(paths, env_values={})

    budgets = settings.budgets_for_seat("seat.worker.implementation")

    assert budgets == {
        "max_steps": 128,
        "max_parse_failures": 3,
        "max_observation_chars": 24000,
        "max_wall_seconds": 5400,
        "budget_profile_ref": "worker.implementation.default",
    }
```

- [ ] **Step 2: Run tests to verify red**

Run:

```bash
PYTHONPATH=src:. python -m pytest tests/config/test_boardroom_config.py -q --tb=short --basetemp .pytest-tmp-v2090h-config-red
```

Expected: FAIL with `ModuleNotFoundError: No module named 'boardroom_os.config'`.

---

### Task 3: Add config fail-closed tests

**Files:**
- Create: `tests/negative/test_boardroom_config_fail_closed.py`
- Modify later: `src/boardroom_os/config/boardroom.py`

- [ ] **Step 1: Write config negative tests**

Create `tests/negative/test_boardroom_config_fail_closed.py` with:

```python
from __future__ import annotations

from pathlib import Path

import pytest

from tests.config.test_boardroom_config import _write_config_files


STALE_ENV_KEYS = {
    "BOARDROOM_OPENAI_MODEL": "gpt-5.5",
    "BOARDROOM_OPENAI_TIMEOUT_SECONDS": "600",
}


def test_config_loader_rejects_stale_openai_env_keys(tmp_path, monkeypatch):
    from boardroom_os.config.boardroom import load_boardroom_settings

    paths = _write_config_files(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-secret")

    with pytest.raises(ValueError, match="stale env execution config keys are not allowed"):
        load_boardroom_settings(paths, env_values=STALE_ENV_KEYS)


def test_config_loader_rejects_atomic_budget_env_keys(tmp_path, monkeypatch):
    from boardroom_os.config.boardroom import load_boardroom_settings

    paths = _write_config_files(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-secret")

    with pytest.raises(ValueError, match="stale env execution config keys are not allowed"):
        load_boardroom_settings(paths, env_values={"BOARDROOM_ATOMIC_MAX_STEPS": "20"})


def test_config_loader_rejects_unknown_provider_type(tmp_path, monkeypatch):
    from boardroom_os.config.boardroom import load_boardroom_settings

    paths = _write_config_files(tmp_path)
    providers_text = paths.providers_config.read_text(encoding="utf-8")
    paths.providers_config.write_text(
        providers_text.replace("provider_type: openai_compatible", "provider_type: anthropic_native"),
        encoding="utf-8",
    )
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-secret")

    with pytest.raises(ValueError, match="provider_type must be openai_compatible"):
        load_boardroom_settings(paths, env_values={})


def test_config_loader_rejects_role_unknown_provider_ref(tmp_path, monkeypatch):
    from boardroom_os.config.boardroom import load_boardroom_settings

    paths = _write_config_files(tmp_path)
    roles_text = paths.roles_config.read_text(encoding="utf-8")
    paths.roles_config.write_text(
        roles_text.replace("provider.openai-compatible.primary", "provider.missing"),
        encoding="utf-8",
    )
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-secret")

    with pytest.raises(ValueError, match="unknown provider_profile_ref"):
        load_boardroom_settings(paths, env_values={})


def test_config_loader_rejects_role_inline_provider_transport_param(tmp_path, monkeypatch):
    from boardroom_os.config.boardroom import load_boardroom_settings

    paths = _write_config_files(tmp_path)
    roles_text = paths.roles_config.read_text(encoding="utf-8")
    paths.roles_config.write_text(
        roles_text + "    base_url: https://api.example.invalid/v1\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-secret")

    with pytest.raises(ValueError, match="extra inputs are not permitted"):
        load_boardroom_settings(paths, env_values={})


def test_config_loader_rejects_missing_api_key_env(tmp_path):
    from boardroom_os.config.boardroom import load_boardroom_settings

    paths = _write_config_files(tmp_path)

    with pytest.raises(ValueError, match="provider api key env is required"):
        load_boardroom_settings(paths, env_values={})


def test_config_loader_rejects_runtime_without_submit_result(tmp_path, monkeypatch):
    from boardroom_os.config.boardroom import load_boardroom_settings

    paths = _write_config_files(tmp_path)
    runtime_text = paths.runtime_config.read_text(encoding="utf-8")
    paths.runtime_config.write_text(runtime_text.replace("    - submit_result\n", ""), encoding="utf-8")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-secret")

    with pytest.raises(ValueError, match="atomic_agent.default_tools must include submit_result"):
        load_boardroom_settings(paths, env_values={})


def test_config_loader_rejects_provider_executor_for_implementation(tmp_path, monkeypatch):
    from boardroom_os.config.boardroom import load_boardroom_settings

    paths = _write_config_files(tmp_path)
    runtime_text = paths.runtime_config.read_text(encoding="utf-8")
    paths.runtime_config.write_text(
        runtime_text.replace("implementation_executor: atomic_agent", "implementation_executor: provider_executor"),
        encoding="utf-8",
    )
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-secret")

    with pytest.raises(ValueError, match="implementation_executor must be atomic_agent"):
        load_boardroom_settings(paths, env_values={})


def test_config_loader_rejects_unsupported_provider_request_param(tmp_path, monkeypatch):
    from boardroom_os.config.boardroom import load_boardroom_settings

    paths = _write_config_files(tmp_path)
    providers_text = paths.providers_config.read_text(encoding="utf-8")
    paths.providers_config.write_text(providers_text + "    tool_choice: auto\n", encoding="utf-8")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-secret")

    with pytest.raises(ValueError, match="extra inputs are not permitted"):
        load_boardroom_settings(paths, env_values={})
```

- [ ] **Step 2: Add contract lock and path negative tests**

Append tests that prove:

```python

def test_config_loader_rejects_missing_contract_lock(tmp_path, monkeypatch):
    from boardroom_os.config.boardroom import load_boardroom_settings

    paths = _write_config_files(tmp_path)
    runtime_text = paths.runtime_config.read_text(encoding="utf-8")
    paths.runtime_config.write_text(
        runtime_text.replace("contract_lock_ref: doc/06-reference/atomic-agent-contract-lock.md", "contract_lock_ref: missing-lock.md"),
        encoding="utf-8",
    )
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-secret")

    with pytest.raises(ValueError, match="atomic-agent contract lock is required"):
        load_boardroom_settings(paths, env_values={})


def test_config_loader_rejects_worktree_atomic_agent_path(tmp_path, monkeypatch):
    from boardroom_os.config.boardroom import resolve_atomic_agent_path

    monkeypatch.setenv("BOARDROOM_ATOMIC_AGENT_PATH", str(tmp_path / ".worktrees" / "atomic-agent"))

    with pytest.raises(ValueError, match="must not point at .worktrees"):
        resolve_atomic_agent_path(default_path="../atomic-agent")
```

- [ ] **Step 3: Run tests to verify red**

Run:

```bash
PYTHONPATH=src:. python -m pytest tests/negative/test_boardroom_config_fail_closed.py -q --tb=short --basetemp .pytest-tmp-v2090h-config-negative-red
```

Expected: FAIL with missing `boardroom_os.config` import.

---

### Task 4: Implement config schemas and loader

**Files:**
- Create: `src/boardroom_os/config/__init__.py`
- Create: `src/boardroom_os/config/boardroom.py`
- Test: `tests/config/test_boardroom_config.py`
- Test: `tests/negative/test_boardroom_config_fail_closed.py`

- [ ] **Step 1: Create `src/boardroom_os/config/boardroom.py`**

Implement the module with these key definitions and behavior. In addition to the base models below, include:

- `AtomicDependencyConfig` with `atomic_agent_path_env`, `default_atomic_agent_path`, `contract_lock_ref`, and `require_contract_hash_match`.
- `AtomicExecutionPolicyConfig` with `wall_time_seconds`, `retry_on_provider_timeout`, `retry_on_runtime_crash`, `max_retries`, `interrupt_grace_period_seconds`, and `retry_requires_no_workspace_mutation`. Reject `retry_on_provider_timeout=True` in V2-090H unless an explicit idempotency policy is added.
- `AtomicConcurrencyConfig` with `mode: Literal["serial_per_workspace"]`, `workspace_lock_root`, and `require_run_scoped_event_artifact_roots`.
- `AgentExecutionBudgetConfig`, `BudgetCapsConfig`, and `ResolvedAgentExecutionBudget` models. Runtime config must define `budget_profiles` and `budget_caps`; role slots must choose `budget_profile_ref`; `budgets_override` merges over the profile and must stay within caps.
- `AtomicToolPolicyResolver` and `declared_command_ids_from_execution_package`. Tool resolution must derive tools from runtime defaults, role tools, `ModelExecutionProfile.tool_permissions`, skill refs, and evidence requirements; command ids must be extracted only from `ExecutionPackage.commands`.
- `resolve_atomic_agent_path()` that reads `BOARDROOM_ATOMIC_AGENT_PATH`, defaults to `../atomic-agent`, rejects missing paths and `.worktrees` paths, and returns a resolved `Path`.
- `load_atomic_agent_contract_lock()` that reads `doc/06-reference/atomic-agent-contract-lock.md`, extracts expected contract paths/hashes, and fails closed when the file is missing.

Implement the module with these key definitions and behavior:

```python
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
import yaml

from atomic_agent.providers.openai_compatible import OpenAICompatibleProviderOptions


class BoardroomConfigError(ValueError):
    pass


_STALE_OPENAI_PREFIX = "BOARDROOM_OPENAI_"
_STALE_ATOMIC_BUDGET_PREFIX = "BOARDROOM_ATOMIC_"
_ALLOWED_ATOMIC_ENV_KEYS = {"BOARDROOM_ATOMIC_AGENT_PATH"}
_PROVIDER_REQUEST_FIELDS = {
    "temperature",
    "reasoning_effort",
    "top_p",
    "presence_penalty",
    "frequency_penalty",
    "seed",
    "stop",
    "response_format",
    "stream_options",
    "service_tier",
    "user",
}


@dataclass(frozen=True)
class BoardroomConfigPaths:
    runtime_config: Path
    providers_config: Path
    roles_config: Path


@dataclass(frozen=True)
class BoardroomConfigHashes:
    runtime_config_hash: str
    providers_config_hash: str
    roles_config_hash: str


class AtomicExecutionModeConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    implementation_executor: Literal["atomic_agent"]
    reject_provider_executor_for_implementation: bool

    @model_validator(mode="after")
    def _require_atomic_executor(self) -> Self:
        if self.implementation_executor != "atomic_agent":
            raise ValueError("implementation_executor must be atomic_agent")
        if self.reject_provider_executor_for_implementation is not True:
            raise ValueError("reject_provider_executor_for_implementation must be true")
        return self


class AgentExecutionBudgetConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    max_steps: int = Field(gt=0)
    max_parse_failures: int = Field(ge=0)
    max_observation_chars: int = Field(gt=0)
    max_wall_seconds: float = Field(gt=0)


class BudgetCapsConfig(AgentExecutionBudgetConfig):
    pass


class AtomicFilesystemConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    default_read_limit: int = Field(gt=0)
    max_read_limit: int = Field(gt=0)
    default_max_entries: int = Field(gt=0)
    max_entries_limit: int = Field(gt=0)
    default_max_matches: int = Field(gt=0)
    max_matches_limit: int = Field(gt=0)


class AtomicCommandConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    default_timeout_seconds: float = Field(gt=0)
    max_timeout_seconds: float = Field(gt=0)
    max_output_bytes: int = Field(gt=0)

    @model_validator(mode="after")
    def _validate_timeouts(self) -> Self:
        if self.default_timeout_seconds > self.max_timeout_seconds:
            raise ValueError("default_timeout_seconds must not exceed max_timeout_seconds")
        return self


class NetworkAllowRuleConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    rule_id: str
    scheme: Literal["http", "https"]
    host: str
    port: int | None = Field(default=None, ge=1, le=65535)
    path_prefix: str

    @field_validator("rule_id", "host", "path_prefix")
    @classmethod
    def _reject_empty_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("network allow rule text fields must not be empty")
        return normalized


class AtomicNetworkConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    default: Literal["deny"]
    allow_rules: tuple[NetworkAllowRuleConfig, ...] = ()


class AtomicAgentRuntimeConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    package_name: str
    import_name: str
    runtime_port_contract_ref: str
    event_stream_root: str
    artifact_root: str
    run_id_prefix: str
    default_tools: tuple[str, ...]
    required_tools: tuple[str, ...]
    tool_permission_map: dict[str, tuple[str, ...]]
    budget_profiles: dict[str, AgentExecutionBudgetConfig]
    budget_caps: BudgetCapsConfig
    filesystem: AtomicFilesystemConfig
    commands: AtomicCommandConfig
    network: AtomicNetworkConfig

    @field_validator("package_name", "import_name", "runtime_port_contract_ref", "event_stream_root", "artifact_root", "run_id_prefix")
    @classmethod
    def _reject_empty_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("atomic_agent text fields must not be empty")
        return normalized

    @field_validator("default_tools", "required_tools")
    @classmethod
    def _reject_empty_tools(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if not values:
            raise ValueError("atomic_agent tools must not be empty")
        normalized = tuple(value.strip() for value in values)
        if any(not value for value in normalized):
            raise ValueError("atomic_agent tools must not contain empty values")
        return normalized

    @model_validator(mode="after")
    def _validate_tools(self) -> Self:
        if "submit_result" not in self.default_tools:
            raise ValueError("atomic_agent.default_tools must include submit_result")
        for tool in self.required_tools:
            if tool not in self.default_tools:
                raise ValueError("atomic_agent.required_tools must be present in default_tools")
        return self


class BoardroomRuntimeConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    version: Literal[1]
    runtime_id: str
    execution: AtomicExecutionModeConfig
    atomic_agent: AtomicAgentRuntimeConfig


class ProviderProfileConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    provider_profile_id: str
    provider_type: Literal["openai_compatible"]
    provider_label: str | None = None
    base_url: str
    api_key_env: str
    model: str
    context_window_tokens: int = Field(gt=0)
    max_output_tokens: int = Field(gt=0)
    stream_idle_timeout_seconds: float = Field(gt=0)
    total_timeout_seconds: float = Field(gt=0)
    reasoning_effort: Literal["none", "minimal", "low", "medium", "high", "xhigh"] | None = None
    temperature: float | None = None
    top_p: float | None = None
    presence_penalty: float | None = None
    frequency_penalty: float | None = None
    seed: int | None = None
    stop: tuple[str, ...] | None = None
    response_format: dict[str, Any] | None = None
    stream_options: dict[str, Any] | None = None
    service_tier: str | None = None
    user: str | None = None

    @field_validator("provider_profile_id", "base_url", "api_key_env", "model")
    @classmethod
    def _reject_empty_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("provider text fields must not be empty")
        return normalized

    @model_validator(mode="after")
    def _validate_provider(self) -> Self:
        if self.provider_type != "openai_compatible":
            raise ValueError("provider_type must be openai_compatible")
        if self.stream_idle_timeout_seconds > self.total_timeout_seconds:
            raise ValueError("stream_idle_timeout_seconds must not exceed total_timeout_seconds")
        return self

    def to_openai_options(self, *, api_key: str) -> OpenAICompatibleProviderOptions:
        if not api_key.strip():
            raise ValueError("provider api key env is required")
        return OpenAICompatibleProviderOptions(
            base_url=self.base_url,
            api_key=api_key,
            model=self.model,
            context_window_tokens=self.context_window_tokens,
            max_output_tokens=self.max_output_tokens,
            stream_idle_timeout_seconds=self.stream_idle_timeout_seconds,
            total_timeout_seconds=self.total_timeout_seconds,
            temperature=self.temperature,
            provider_label=self.provider_label,
            reasoning_effort=self.reasoning_effort,
            top_p=self.top_p,
            presence_penalty=self.presence_penalty,
            frequency_penalty=self.frequency_penalty,
            seed=self.seed,
            stop=self.stop,
            response_format=self.response_format,
            stream_options=self.stream_options,
            service_tier=self.service_tier,
            user=self.user,
        )


class BoardroomProvidersConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    version: Literal[1]
    providers: tuple[ProviderProfileConfig, ...]

    @model_validator(mode="after")
    def _require_unique_providers(self) -> Self:
        if not self.providers:
            raise ValueError("providers must not be empty")
        seen: set[str] = set()
        for provider in self.providers:
            if provider.provider_profile_id in seen:
                raise ValueError("provider_profile_id values must be unique")
            seen.add(provider.provider_profile_id)
        return self


class RoleSlotConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    seat_ref: str
    role_profile_ref: str
    role_category: str
    model_execution_profile_id: str
    provider_profile_ref: str
    budget_profile_ref: str
    skill_refs: tuple[str, ...]
    default_tools: tuple[str, ...]
    budgets_override: dict[str, int | float] = {}

    @field_validator("seat_ref", "role_profile_ref", "role_category", "model_execution_profile_id", "provider_profile_ref", "budget_profile_ref")
    @classmethod
    def _reject_empty_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("role slot text fields must not be empty")
        return normalized

    @field_validator("skill_refs", "default_tools")
    @classmethod
    def _reject_empty_tuple(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if not values:
            raise ValueError("role slot tuples must not be empty")
        normalized = tuple(value.strip() for value in values)
        if any(not value for value in normalized):
            raise ValueError("role slot tuples must not contain empty values")
        return normalized


class BoardroomRolesConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    version: Literal[1]
    role_slots: tuple[RoleSlotConfig, ...]

    @model_validator(mode="after")
    def _require_unique_seats(self) -> Self:
        if not self.role_slots:
            raise ValueError("role_slots must not be empty")
        seen: set[str] = set()
        for slot in self.role_slots:
            if slot.seat_ref in seen:
                raise ValueError("seat_ref values must be unique")
            seen.add(slot.seat_ref)
        return self


class BoardroomSettings(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    runtime: BoardroomRuntimeConfig
    providers: BoardroomProvidersConfig
    roles: BoardroomRolesConfig
    config_hashes: BoardroomConfigHashes

    @model_validator(mode="after")
    def _validate_cross_refs(self) -> Self:
        provider_ids = {provider.provider_profile_id for provider in self.providers.providers}
        allowed_budget_keys = set(AgentExecutionBudgetConfig.model_fields)
        for slot in self.roles.role_slots:
            if slot.provider_profile_ref not in provider_ids:
                raise ValueError("unknown provider_profile_ref")
            unknown_budget_keys = set(slot.budgets_override) - allowed_budget_keys
            if unknown_budget_keys:
                raise ValueError("unknown budget override keys: " + ", ".join(sorted(unknown_budget_keys)))
            if slot.role_category == "worker" and "submit_result" not in slot.default_tools:
                raise ValueError("worker role slot tools must include submit_result")
            if slot.role_category == "worker" and "run_command" not in slot.default_tools:
                raise ValueError("worker role slot tools must include run_command")
            if slot.role_category == "worker" and not {"write_file", "apply_patch"}.intersection(slot.default_tools):
                raise ValueError("worker role slot tools must include write_file or apply_patch")
        return self

    def provider_by_id(self, provider_profile_id: str) -> ProviderProfileConfig:
        for provider in self.providers.providers:
            if provider.provider_profile_id == provider_profile_id:
                return provider
        raise ValueError("unknown provider_profile_id")

    def role_slot_by_seat(self, seat_ref: str) -> RoleSlotConfig:
        for slot in self.roles.role_slots:
            if slot.seat_ref == seat_ref:
                return slot
        raise ValueError("unknown seat_ref")

    def budgets_for_seat(self, seat_ref: str) -> dict[str, int | float | str]:
        slot = self.role_slot_by_seat(seat_ref)
        profile = self.runtime.atomic_agent.budget_profiles.get(slot.budget_profile_ref)
        if profile is None:
            raise ValueError("unknown budget_profile_ref")
        merged = profile.model_dump()
        merged.update(slot.budgets_override)
        for key, value in merged.items():
            cap = getattr(self.runtime.atomic_agent.budget_caps, key)
            if value > cap:
                raise ValueError(f"resolved budget {key} exceeds budget_caps")
        merged["budget_profile_ref"] = slot.budget_profile_ref
        return merged

    def openai_compatible_options(self, provider_profile_id: str) -> OpenAICompatibleProviderOptions:
        provider = self.provider_by_id(provider_profile_id)
        api_key = os.environ.get(provider.api_key_env, "")
        if not api_key:
            raise ValueError("provider api key env is required")
        return provider.to_openai_options(api_key=api_key)


def load_boardroom_settings(paths: BoardroomConfigPaths, *, env_values: dict[str, str] | None = None) -> BoardroomSettings:
    env_values = env_values or {}
    stale = sorted(key for key, value in env_values.items() if key.startswith(_STALE_OPENAI_PREFIX) and value.strip())
    stale.extend(
        sorted(
            key
            for key, value in env_values.items()
            if key.startswith(_STALE_ATOMIC_BUDGET_PREFIX)
            and key not in _ALLOWED_ATOMIC_ENV_KEYS
            and value.strip()
        )
    )
    if stale:
        raise ValueError("stale env execution config keys are not allowed: " + ", ".join(stale))
    runtime = BoardroomRuntimeConfig.model_validate(_load_yaml_mapping(paths.runtime_config))
    providers = BoardroomProvidersConfig.model_validate(_load_yaml_mapping(paths.providers_config))
    roles = BoardroomRolesConfig.model_validate(_load_yaml_mapping(paths.roles_config))
    return BoardroomSettings(
        runtime=runtime,
        providers=providers,
        roles=roles,
        config_hashes=BoardroomConfigHashes(
            runtime_config_hash=_sha256_file(paths.runtime_config),
            providers_config_hash=_sha256_file(paths.providers_config),
            roles_config_hash=_sha256_file(paths.roles_config),
        ),
    )


def _load_yaml_mapping(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise ValueError(f"config file is required: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"config file must contain a YAML mapping: {path}")
    return data


def _sha256_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
```

When implementing, keep the module smaller if possible, but preserve the exact public names used by tests.

- [ ] **Step 2: Create `src/boardroom_os/config/__init__.py`**

Write:

```python
"""Boardroom OS configuration models and loaders."""

from boardroom_os.config.boardroom import (
    BoardroomConfigError,
    BoardroomConfigHashes,
    BoardroomConfigPaths,
    BoardroomRuntimeConfig,
    BoardroomSettings,
    ProviderProfileConfig,
    RoleSlotConfig,
    load_boardroom_settings,
)

__all__ = [
    "BoardroomConfigError",
    "BoardroomConfigHashes",
    "BoardroomConfigPaths",
    "BoardroomRuntimeConfig",
    "BoardroomSettings",
    "ProviderProfileConfig",
    "RoleSlotConfig",
    "load_boardroom_settings",
]
```

- [ ] **Step 3: Run config tests**

Run:

```bash
PYTHONPATH=src:. python -m pytest tests/config/test_boardroom_config.py tests/negative/test_boardroom_config_fail_closed.py -q --tb=short --basetemp .pytest-tmp-v2090h-config-green
```

Expected: all tests pass.

- [ ] **Step 4: Commit Task 1-4**

Run:

```bash
git add config/boardroom-runtime.example.yaml config/boardroom-providers.example.yaml config/boardroom-roles.example.yaml doc/06-reference/atomic-agent-contract-lock.md .env.template .env.example src/boardroom_os/config tests/config/test_boardroom_config.py tests/negative/test_boardroom_config_fail_closed.py
git commit -m "feat(config): 增加原子执行器配置"
```

Expected: commit created. If the user has not authorized commits in this session, skip commit and record that it was skipped.

---

### Task 5: Extend invocation compiler tests for config-aware requests

**Files:**
- Modify: `tests/execution/test_atomic_agent_invocation_compiler.py`
- Modify later: `src/boardroom_os/execution/atomic_agent.py`

- [ ] **Step 1: Add config-aware compiler test**

Append this test to `tests/execution/test_atomic_agent_invocation_compiler.py`:

```python

def test_atomic_invocation_compiler_consumes_runtime_provider_and_role_config(tmp_path, monkeypatch):
    from boardroom_os.config.boardroom import load_boardroom_settings
    from tests.config.test_boardroom_config import _write_config_files

    paths = _write_config_files(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-secret")
    settings = load_boardroom_settings(paths, env_values={})
    execution_package = _execution_package().model_copy(
        update={
            "seat_ref": AgentSeatRef(value="seat.worker.implementation"),
            "model_execution_profile": _execution_package().model_execution_profile.model_copy(
                update={
                    "provider": "openai-compatible",
                    "model": "gpt-5.5",
                    "reasoning_effort": "high",
                    "context_window": 400000,
                    "temperature": 0.0,
                    "model_execution_profile_id": "model-profile.worker.implementation.primary",
                }
            ),
        }
    )

    invocation = AtomicInvocationCompiler(workspace_root=tmp_path).compile_with_settings(
        execution_package=execution_package,
        settings=settings,
        seat_ref="seat.worker.implementation",
    )

    assert invocation.permission_policy["policy_ref"] == "policy://boardroom/atomic-agent/exec.ticket.backend.1"
    assert invocation.provider_profile["provider"] == "openai-compatible"
    assert invocation.provider_profile["model"] == "gpt-5.5"
    assert "api_key" not in invocation.provider_profile
    assert invocation.budgets == {
        "max_steps": 128,
        "max_parse_failures": 3,
        "max_observation_chars": 24000,
        "max_wall_seconds": 5400,
    }
    assert invocation.metadata["budget_profile_ref"] == "worker.implementation.default"
    assert invocation.metadata["resolved_budget_hash"].startswith("sha256:")
    assert invocation.metadata["resolved_tool_policy_hash"].startswith("sha256:")
    assert "submit_result" in invocation.tools
    assert "run_command" in invocation.tools
    assert invocation.output_requirements["require_command_evidence"] is True
    assert invocation.output_requirements["require_source_lineage"] is True
    assert invocation.metadata["runtime_config_hash"].startswith("sha256:")
    assert invocation.metadata["providers_config_hash"].startswith("sha256:")
    assert invocation.metadata["roles_config_hash"].startswith("sha256:")
    assert invocation.metadata["provider_profile_ref"] == "provider.openai-compatible.primary"
```

- [ ] **Step 1.5: Add tool policy and command id tests**

Append tests equivalent to:

```python
def test_atomic_tool_policy_resolver_derives_tools_from_permissions(tmp_path, monkeypatch):
    from boardroom_os.execution.atomic_agent import AtomicToolPolicyResolver

    tools = AtomicToolPolicyResolver().resolve_tools(
        runtime_tools=("list_files", "read_file", "search_files", "write_file", "apply_patch", "run_command", "submit_result"),
        role_tools=("read_file", "apply_patch", "run_command", "submit_result"),
        tool_permissions=("filesystem.read", "filesystem.write", "command.execute"),
        skill_refs=("skill.filesystem.patch", "skill.command.test"),
        requires_command_evidence=True,
        requires_workspace_mutation=True,
    )

    assert tools == ("read_file", "apply_patch", "run_command", "submit_result")


def test_declared_command_ids_are_extracted_from_execution_package_only():
    from boardroom_os.execution.atomic_agent import declared_command_ids_from_execution_package

    assert declared_command_ids_from_execution_package(_execution_package()) == ("cmd.test",)
```

- [ ] **Step 2: Add compiler negative tests**

Append:

```python

def test_atomic_invocation_compiler_rejects_provider_profile_mismatch(tmp_path, monkeypatch):
    from boardroom_os.config.boardroom import load_boardroom_settings
    from tests.config.test_boardroom_config import _write_config_files

    paths = _write_config_files(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-secret")
    settings = load_boardroom_settings(paths, env_values={})
    execution_package = _execution_package().model_copy(
        update={"seat_ref": AgentSeatRef(value="seat.worker.implementation")}
    )

    try:
        AtomicInvocationCompiler(workspace_root=tmp_path).compile_with_settings(
            execution_package=execution_package,
            settings=settings,
            seat_ref="seat.worker.implementation",
        )
    except ValueError as exc:
        assert "provider profile does not match execution package" in str(exc)
    else:
        raise AssertionError("expected provider mismatch failure")


def test_atomic_invocation_compiler_rejects_role_slot_seat_mismatch(tmp_path, monkeypatch):
    from boardroom_os.config.boardroom import load_boardroom_settings
    from tests.config.test_boardroom_config import _write_config_files

    paths = _write_config_files(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-secret")
    settings = load_boardroom_settings(paths, env_values={})

    try:
        AtomicInvocationCompiler(workspace_root=tmp_path).compile_with_settings(
            execution_package=_execution_package(),
            settings=settings,
            seat_ref="seat.worker.implementation",
        )
    except ValueError as exc:
        assert "role slot seat_ref must match execution_package.seat_ref" in str(exc)
    else:
        raise AssertionError("expected seat mismatch failure")
```

- [ ] **Step 3: Run compiler tests to verify red**

Run:

```bash
PYTHONPATH=src:. python -m pytest tests/execution/test_atomic_agent_invocation_compiler.py -q --tb=short --basetemp .pytest-tmp-v2090h-compiler-red
```

Expected: FAIL with `AttributeError: 'AtomicInvocationCompiler' object has no attribute 'compile_with_settings'`.

---

### Task 6: Implement config-aware invocation compiler

Compiler implementation must not use constructor defaults for budget or tools on the V2-090H main path. It must call `settings.resolve_budget_for_execution_package(...)` or equivalent and `AtomicToolPolicyResolver.resolve_tools(...)`. Compiler implementation must also:

- Include `execution_policy` in invocation metadata and ensure `budgets.max_wall_seconds` equals the selected policy wall time unless a role override explicitly changes it.
- Include `event_stream_format: jsonl-utf8-lf-canonical-json-v1` in metadata.
- Reject role/provider mismatch with path/seat/provider refs in the error message, while never including API keys.

**Files:**
- Modify: `src/boardroom_os/execution/atomic_agent.py`
- Test: `tests/execution/test_atomic_agent_invocation_compiler.py`

- [ ] **Step 1: Add `compile_with_settings` to `AtomicInvocationCompiler`**

Add a method with this behavior:

```python
def compile_with_settings(
    self,
    *,
    execution_package: ExecutionPackage,
    settings: Any,
    seat_ref: str,
) -> Any:
    role_slot = settings.role_slot_by_seat(seat_ref)
    if role_slot.seat_ref != execution_package.seat_ref.value:
        raise ValueError("role slot seat_ref must match execution_package.seat_ref")
    provider_config = settings.provider_by_id(role_slot.provider_profile_ref)
    profile = execution_package.model_execution_profile
    if (
        profile.provider != "openai-compatible"
        or profile.model != provider_config.model
        or profile.reasoning_effort != (provider_config.reasoning_effort or profile.reasoning_effort)
        or profile.context_window != provider_config.context_window_tokens
    ):
        raise ValueError("provider profile does not match execution package")
    provider_options = settings.openai_compatible_options(provider_config.provider_profile_id)
    allowed_write_set = _validate_relative_paths(
        tuple(_ref_value(path) for path in execution_package.allowed_write_set),
        error_message="allowed_write_set must contain relative paths",
    )
    tools = AtomicToolPolicyResolver().resolve_tools(
        runtime_tools=tuple(settings.runtime.atomic_agent.default_tools),
        role_tools=tuple(role_slot.default_tools),
        tool_permissions=tuple(execution_package.model_execution_profile.tool_permissions),
        skill_refs=tuple(role_slot.skill_refs),
        requires_command_evidence=True,
        requires_workspace_mutation=True,
    )
    resolved_budget = settings.budgets_for_seat(role_slot.seat_ref)
    invocation = self.compile(execution_package).model_copy(
        update={
            "tools": list(tools),
            "permission_policy": {
                "policy_ref": f"policy://boardroom/atomic-agent/{execution_package.execution_package_id.value}",
                "commands": [
                    {
                        "command_id": command.command_id.value,
                        "label": command.label,
                        "argv": list(command.command),
                        "cwd": _validate_relative_paths(
                            (command.cwd,),
                            error_message="command cwd must contain relative paths",
                        )[0],
                    }
                    for command in execution_package.commands
                ],
                "network": settings.runtime.atomic_agent.network.model_dump(mode="json"),
                "filesystem": {"allowed_write_set": list(allowed_write_set)},
            },
            "provider_profile": provider_options.to_provider_profile(),
            "budgets": {key: resolved_budget[key] for key in ("max_steps", "max_parse_failures", "max_observation_chars", "max_wall_seconds")},
            "output_requirements": {
                **self.compile(execution_package).output_requirements,
                "require_command_evidence": True,
                "require_source_lineage": True,
            },
            "skill_context": {
                "skill_refs": list(role_slot.skill_refs),
                "audit_requirements": [item.value for item in execution_package.audit_requirements],
            },
            "metadata": {
                **self.compile(execution_package).metadata,
                "provider_profile_ref": provider_config.provider_profile_id,
                "role_slot_ref": role_slot.seat_ref,
                "budget_profile_ref": resolved_budget["budget_profile_ref"],
                "resolved_budget_hash": stable_hash(resolved_budget),
                "resolved_tool_policy_hash": stable_hash({"tools": tools}),
                "runtime_config_hash": settings.config_hashes.runtime_config_hash,
                "providers_config_hash": settings.config_hashes.providers_config_hash,
                "roles_config_hash": settings.config_hashes.roles_config_hash,
            },
        }
    )
    return invocation
```

Refactor to avoid calling `self.compile(execution_package)` three times in final code. Keep the exact error messages from tests.

- [ ] **Step 2: Preserve V2-090G tests**

Run:

```bash
PYTHONPATH=src:. python -m pytest tests/execution/test_atomic_agent_invocation_compiler.py tests/proving/test_tiny_atomic_agent_bridge.py -q --tb=short --basetemp .pytest-tmp-v2090h-compiler-green
```

Expected: all tests pass; V2-090G bridge test remains valid.

- [ ] **Step 3: Commit compiler work**

Run:

```bash
git add src/boardroom_os/execution/atomic_agent.py tests/execution/test_atomic_agent_invocation_compiler.py
git commit -m "feat(execution): 扩展原子调用配置编译"
```

Expected: commit created, unless commits are not authorized.

---

### Task 7: Add executor unit and fail-closed tests

**Files:**
- Create: `tests/execution/test_atomic_agent_executor.py`
- Create: `tests/negative/test_atomic_agent_executor_fail_closed.py`
- Create later: `src/boardroom_os/execution/atomic_executor.py`

- [ ] **Step 1: Write executor unit tests**

Create `tests/execution/test_atomic_agent_executor.py` with:

```python
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from atomic_agent.models import AgentRunResult, AgentRunStatus

from boardroom_os.config.boardroom import load_boardroom_settings
from boardroom_os.execution.atomic_executor import AtomicAgentExecutor, AtomicExecutionRequest
from boardroom_os.execution.context_index import ProviderAttemptRef
from boardroom_os.providers.attempt import ProviderArtifactRef
from tests.config.test_boardroom_config import _write_config_files
from tests.execution.test_atomic_agent_invocation_compiler import _execution_package
from tests.execution.test_atomic_agent_result_projection import _completed_result, _write_event_stream


class ScriptedRuntimePort:
    def __init__(self, result: AgentRunResult):
        self.result = result
        self.invocations = []

    def invoke(self, invocation):
        self.invocations.append(invocation)
        return self.result


def _settings(tmp_path: Path, monkeypatch):
    paths = _write_config_files(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-secret")
    return load_boardroom_settings(paths, env_values={})


def _execution_package_for_config():
    package = _execution_package()
    return package.model_copy(
        update={
            "seat_ref": {"value": "seat.worker.implementation"},
            "model_execution_profile": package.model_execution_profile.model_copy(
                update={
                    "provider": "openai-compatible",
                    "model": "gpt-5.5",
                    "reasoning_effort": "high",
                    "context_window": 400000,
                    "temperature": 0.0,
                    "model_execution_profile_id": "model-profile.worker.implementation.primary",
                }
            ),
        }
    )


def test_atomic_agent_executor_invokes_runtime_and_projects_result(tmp_path, monkeypatch):
    event_stream = tmp_path / "events.jsonl"
    events_hash = _write_event_stream(event_stream, command_id="cmd.test")
    result = _completed_result(event_stream, events_hash)
    runtime_port = ScriptedRuntimePort(result)
    executor = AtomicAgentExecutor(runtime_port=runtime_port)
    request = AtomicExecutionRequest(
        execution_package=_execution_package_for_config(),
        settings=_settings(tmp_path, monkeypatch),
        seat_ref="seat.worker.implementation",
        workspace_root=tmp_path,
        event_stream_root=tmp_path,
    )

    execution_result = executor.execute(request)

    assert runtime_port.invocations
    assert execution_result.atomic_run_id == "run.atomic.1"
    assert execution_result.provider_attempt.provider_attempt_id.value.startswith("provider-attempt.atomic.")
    assert execution_result.provider_attempt.status == "succeeded"
    assert execution_result.projection.work_product_submission.work_product.ticket_ref.value == "ticket.backend"
    assert execution_result.projection.source_lineage_inputs[0]["path"] == "backend/app.py"


def test_atomic_agent_executor_projected_provider_attempt_binds_execution_package(tmp_path, monkeypatch):
    event_stream = tmp_path / "events.jsonl"
    events_hash = _write_event_stream(event_stream, command_id="cmd.test")
    executor = AtomicAgentExecutor(runtime_port=ScriptedRuntimePort(_completed_result(event_stream, events_hash)))
    package = _execution_package_for_config()

    execution_result = executor.execute(
        AtomicExecutionRequest(
            execution_package=package,
            settings=_settings(tmp_path, monkeypatch),
            seat_ref="seat.worker.implementation",
            workspace_root=tmp_path,
            event_stream_root=tmp_path,
        )
    )

    attempt = execution_result.provider_attempt
    assert attempt.input_package_ref.value == package.execution_package_id.value
    assert attempt.seat_ref == package.seat_ref
    assert attempt.provider == "openai-compatible"
    assert attempt.model == "gpt-5.5"
    assert attempt.reasoning_effort == "high"
    assert attempt.raw_output_ref is not None
    assert attempt.parsed_output_ref is not None
```

- [ ] **Step 2: Write executor negative tests**

Negative tests must include CRLF/noncanonical event stream rejection and retry-after-mutation rejection in addition to the base tests below. Create `tests/negative/test_atomic_agent_executor_fail_closed.py` with:

```python
from __future__ import annotations

from pathlib import Path

import pytest
from atomic_agent.models import AgentRunResult, AgentRunStatus

from boardroom_os.config.boardroom import load_boardroom_settings
from boardroom_os.execution.atomic_executor import (
    AtomicAgentExecutor,
    AtomicExecutionRequest,
    reject_provider_executor_for_implementation,
)
from boardroom_os.execution.provider_executor import ProviderExecutor
from tests.config.test_boardroom_config import _write_config_files
from tests.execution.test_atomic_agent_executor import ScriptedRuntimePort, _execution_package_for_config
from tests.execution.test_atomic_agent_result_projection import _completed_result, _write_event_stream


def _settings(tmp_path: Path, monkeypatch):
    paths = _write_config_files(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-secret")
    return load_boardroom_settings(paths, env_values={})


def _request(tmp_path, monkeypatch, runtime_result):
    return AtomicExecutionRequest(
        execution_package=_execution_package_for_config(),
        settings=_settings(tmp_path, monkeypatch),
        seat_ref="seat.worker.implementation",
        workspace_root=tmp_path,
        event_stream_root=tmp_path,
    )


def test_provider_executor_is_rejected_for_implementation_ticket():
    with pytest.raises(ValueError, match="ProviderExecutor cannot satisfy implementation ticket evidence"):
        reject_provider_executor_for_implementation(ProviderExecutor(), ticket_category="implementation")


def test_atomic_agent_executor_requires_runtime_port(tmp_path, monkeypatch):
    executor = AtomicAgentExecutor(runtime_port=None)
    event_stream = tmp_path / "events.jsonl"
    events_hash = _write_event_stream(event_stream, command_id="cmd.test")

    with pytest.raises(ValueError, match="AgentRuntimePort is required"):
        executor.execute(_request(tmp_path, monkeypatch, _completed_result(event_stream, events_hash)))


def test_atomic_agent_executor_rejects_missing_provider_turn_facts(tmp_path, monkeypatch):
    event_stream = tmp_path / "events.jsonl"
    events_hash = _write_event_stream(event_stream, command_id="cmd.test")
    result = _completed_result(event_stream, events_hash)
    executor = AtomicAgentExecutor(runtime_port=ScriptedRuntimePort(result))

    with pytest.raises(ValueError, match="provider turn facts are required"):
        executor.execute(_request(tmp_path, monkeypatch, result))


def test_atomic_agent_executor_rejects_missing_command_evidence(tmp_path, monkeypatch):
    event_stream = tmp_path / "events.jsonl"
    events_hash = _write_event_stream(event_stream, command_id=None)
    result = _completed_result(event_stream, events_hash)
    executor = AtomicAgentExecutor(runtime_port=ScriptedRuntimePort(result))

    with pytest.raises(ValueError, match="command evidence is required"):
        executor.execute(_request(tmp_path, monkeypatch, result))


def test_atomic_agent_executor_rejects_direct_governance_completion(tmp_path, monkeypatch):
    event_stream = tmp_path / "events.jsonl"
    events_hash = _write_event_stream(event_stream, command_id="cmd.test")
    result = _completed_result(event_stream, events_hash).model_copy(
        update={"summary": "ticket_completed=true"}
    )
    executor = AtomicAgentExecutor(runtime_port=ScriptedRuntimePort(result))

    with pytest.raises(ValueError, match="atomic-agent result must not contain governance field"):
        executor.execute(_request(tmp_path, monkeypatch, result))


def test_real_proving_path_rejects_fake_provider_marker(tmp_path, monkeypatch):
    event_stream = tmp_path / "events.jsonl"
    events_hash = _write_event_stream(event_stream, command_id="cmd.test")
    result = _completed_result(event_stream, events_hash)
    executor = AtomicAgentExecutor(runtime_port=ScriptedRuntimePort(result), allow_fake_provider_for_unit_tests=False)

    with pytest.raises(ValueError, match="fake provider transport cannot satisfy V2-090H"):
        executor.execute(_request(tmp_path, monkeypatch, result), provider_transport_kind="fake")
```

- [ ] **Step 2.5: Add canonical event stream and retry policy negative tests**

Append tests equivalent to:

```python

def test_atomic_agent_executor_rejects_crlf_event_stream(tmp_path, monkeypatch):
    event_stream = tmp_path / "events.jsonl"
    events_hash = _write_event_stream(event_stream, command_id="cmd.test")
    event_stream.write_bytes(event_stream.read_bytes().replace(b"\n", b"\r\n"))
    result = _completed_result(event_stream, "sha256:" + __import__("hashlib").sha256(event_stream.read_bytes()).hexdigest())
    executor = AtomicAgentExecutor(runtime_port=ScriptedRuntimePort(result))

    with pytest.raises(ValueError, match="event stream must use LF line endings"):
        executor.execute(_request(tmp_path, monkeypatch, result))


def test_atomic_agent_executor_rejects_retry_after_workspace_mutation(tmp_path, monkeypatch):
    from boardroom_os.execution.atomic_executor import AtomicRetryDecision

    decision = AtomicRetryDecision.can_retry(
        failure_kind="runtime_crash",
        attempt_index=0,
        max_retries=1,
        workspace_mutations=[{"path": "backend/app.py"}],
    )

    assert decision.allowed is False
    assert "workspace mutation" in decision.reason
```

- [ ] **Step 3: Run executor tests to verify red**

Run:

```bash
PYTHONPATH=src:. python -m pytest tests/execution/test_atomic_agent_executor.py tests/negative/test_atomic_agent_executor_fail_closed.py -q --tb=short --basetemp .pytest-tmp-v2090h-executor-red
```

Expected: FAIL with `ModuleNotFoundError: No module named 'boardroom_os.execution.atomic_executor'`.

---

### Task 8: Implement `AtomicAgentExecutor` unit boundary

**Files:**
- Create: `src/boardroom_os/execution/atomic_executor.py`
- Modify: `src/boardroom_os/execution/__init__.py`
- Test: `tests/execution/test_atomic_agent_executor.py`
- Test: `tests/negative/test_atomic_agent_executor_fail_closed.py`

- [ ] **Step 1: Implement dataclasses, retry decision, and executor skeleton**

Create `src/boardroom_os/execution/atomic_executor.py` with these public names. Include a per-workspace lock helper for `serial_per_workspace`; if the lock exists, fail closed with the workspace path and lock path. Include `AtomicRetryDecision` so retry rules can be unit-tested without invoking a provider.

Create `src/boardroom_os/execution/atomic_executor.py` with these public names:

```python
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from boardroom_os.execution.atomic_agent import (
    AtomicAgentPackageAdapter,
    AtomicAgentResultValidator,
    AtomicInvocationCompiler,
    AtomicResultProjection,
    AtomicResultProjector,
)
from boardroom_os.execution.package import ExecutionPackage, ExecutionPackageRef
from boardroom_os.execution.context_index import ProviderAttemptRef
from boardroom_os.providers.attempt import (
    ProviderArtifactRef,
    ProviderAttempt,
    ProviderAttemptOutcome,
    ProviderAttemptStatus,
)


@dataclass(frozen=True)
class AtomicExecutionRequest:
    execution_package: ExecutionPackage
    settings: Any
    seat_ref: str
    workspace_root: Path
    event_stream_root: Path


@dataclass(frozen=True)
class AtomicExecutionResult:
    atomic_run_id: str
    provider_attempt: ProviderAttempt
    projection: AtomicResultProjection
    raw_result: Any


class AtomicAgentExecutor:
    def __init__(self, *, runtime_port: Any | None, allow_fake_provider_for_unit_tests: bool = True) -> None:
        self.runtime_port = runtime_port
        self.allow_fake_provider_for_unit_tests = allow_fake_provider_for_unit_tests

    def execute(self, request: AtomicExecutionRequest, *, provider_transport_kind: str = "real") -> AtomicExecutionResult:
        if self.runtime_port is None:
            raise ValueError("AgentRuntimePort is required")
        if provider_transport_kind == "fake" and not self.allow_fake_provider_for_unit_tests:
            raise ValueError("fake provider transport cannot satisfy V2-090H")
        compiler = AtomicInvocationCompiler(workspace_root=request.workspace_root)
        invocation = compiler.compile_with_settings(
            execution_package=request.execution_package,
            settings=request.settings,
            seat_ref=request.seat_ref,
        )
        result = AtomicAgentPackageAdapter(runtime_port=self.runtime_port).invoke(invocation)
        validator = AtomicAgentResultValidator(
            allowed_write_set=tuple(path.value for path in request.execution_package.allowed_write_set),
            declared_command_ids=declared_command_ids_from_execution_package(request.execution_package),
            event_stream_root=request.event_stream_root,
        )
        validated = validator.validate(result)
        _require_provider_turn_facts(validated.evidence_summary)
        _require_command_evidence(validated.evidence_summary)
        provider_attempt = _provider_attempt_from_atomic_summary(request.execution_package, validated.evidence_summary)
        projection = AtomicResultProjector().project(
            execution_package=request.execution_package,
            provider_attempt=provider_attempt,
            validated_result=validated,
        )
        return AtomicExecutionResult(
            atomic_run_id=result.run_id,
            provider_attempt=provider_attempt,
            projection=projection,
            raw_result=result,
        )


def reject_provider_executor_for_implementation(provider_executor: Any, *, ticket_category: str) -> None:
    if ticket_category == "implementation" and provider_executor is not None:
        raise ValueError("ProviderExecutor cannot satisfy implementation ticket evidence")


def _require_provider_turn_facts(evidence_summary: dict[str, Any]) -> None:
    if not evidence_summary.get("provider_attempts"):
        raise ValueError("provider turn facts are required")


def _require_command_evidence(evidence_summary: dict[str, Any]) -> None:
    if not evidence_summary.get("command_results"):
        raise ValueError("command evidence is required")


def _provider_attempt_from_atomic_summary(execution_package: ExecutionPackage, evidence_summary: dict[str, Any]) -> ProviderAttempt:
    provider_turns = evidence_summary.get("provider_attempts") or []
    provider_turn = provider_turns[0]
    output = provider_turn.get("output", {})
    artifact_ref = output.get("artifact_ref")
    if not isinstance(artifact_ref, str) or not artifact_ref:
        raise ValueError("provider turn output artifact_ref is required")
    now = datetime.now(UTC)
    profile = execution_package.model_execution_profile
    safe_ref = artifact_ref.replace("artifact://", "artifact.atomic.").replace("/", ".")
    return ProviderAttempt(
        provider_attempt_id=ProviderAttemptRef(value=f"provider-attempt.atomic.{evidence_summary['run_id']}.{provider_turn['provider_turn_id']}"),
        provider=profile.provider,
        model=profile.model,
        reasoning_effort=profile.reasoning_effort,
        input_package_ref=ExecutionPackageRef(value=execution_package.execution_package_id.value),
        seat_ref=execution_package.seat_ref,
        role_prompt_hook_ref=execution_package.role_prompt_hook.hook_ref,
        role_prompt_hook_version=execution_package.role_prompt_hook.hook_version,
        role_prompt_hook_sha256=execution_package.role_prompt_hook.content_sha256,
        status=ProviderAttemptStatus.SUCCEEDED,
        outcome=ProviderAttemptOutcome.PRIMARY_PROVIDER_OUTPUT,
        started_at=now,
        finished_at=now,
        raw_output_ref=ProviderArtifactRef(value=f"provider-artifact.atomic.raw.{safe_ref}"),
        parsed_output_ref=ProviderArtifactRef(value=f"provider-artifact.atomic.parsed.{safe_ref}"),
    )
```

This is the minimal unit boundary. Later tasks replace test-only runtime port construction with real atomic-agent `AgentLoop` factory.

- [ ] **Step 2: Update `src/boardroom_os/execution/__init__.py` exports**

Add imports and `__all__` entries for:

```python
AtomicAgentExecutor
AtomicExecutionRequest
AtomicExecutionResult
reject_provider_executor_for_implementation
```

- [ ] **Step 3: Adjust event stream fixtures to include provider turn facts**

The existing `_write_event_stream` helper in `tests/execution/test_atomic_agent_result_projection.py` lacks provider turn events. For V2-090H, add optional provider turn events in the helper when `include_provider_turn=True`, defaulting to true only in executor tests if preserving V2-090G tests is easier. The provider turn event payload must use a valid artifact reference:

```python
{
    "event_id": "evt-provider-start",
    "run_id": "run.atomic.1",
    "sequence": 2,
    "type": "provider.turn.started",
    "timestamp": "2026-06-10T00:00:00Z",
    "payload": {"provider_turn_id": "provider_turn_000001"},
    "previous_event_hash": None,
}
```

and:

```python
{
    "event_id": "evt-provider-completed",
    "run_id": "run.atomic.1",
    "sequence": 3,
    "type": "provider.turn.completed",
    "timestamp": "2026-06-10T00:00:01Z",
    "payload": {
        "provider_turn_id": "provider_turn_000001",
        "output": {
            "artifact_ref": "artifact://run.atomic.1/provider/turn_000001.txt",
            "sha256": "sha256:" + "5" * 64,
            "size_bytes": 80,
            "truncated_in_observation": False,
        },
    },
    "previous_event_hash": None,
}
```

Recompute sequence and hashes exactly as the helper already does.

- [ ] **Step 4: Run executor tests**

Run:

```bash
PYTHONPATH=src:. python -m pytest tests/execution/test_atomic_agent_executor.py tests/negative/test_atomic_agent_executor_fail_closed.py -q --tb=short --basetemp .pytest-tmp-v2090h-executor-green
```

Expected: all tests pass.

- [ ] **Step 5: Run V2-090G regression tests**

Run:

```bash
PYTHONPATH=src:. python -m pytest tests/execution/test_atomic_agent_result_projection.py tests/negative/test_atomic_agent_integration_fail_closed.py tests/proving/test_tiny_atomic_agent_bridge.py -q --tb=short --basetemp .pytest-tmp-v2090h-v2090g-regression
```

Expected: all tests pass.

- [ ] **Step 6: Commit executor unit boundary**

Run:

```bash
git add src/boardroom_os/execution/atomic_executor.py src/boardroom_os/execution/__init__.py tests/execution/test_atomic_agent_executor.py tests/negative/test_atomic_agent_executor_fail_closed.py tests/execution/test_atomic_agent_result_projection.py
git commit -m "feat(execution): 增加原子执行器边界"
```

Expected: commit created, unless commits are not authorized.

---

### Task 9: Add real atomic-agent runtime factory

The factory must resolve `BOARDROOM_ATOMIC_AGENT_PATH`, verify the contract lock, create run-scoped event/artifact directories, and enforce `serial_per_workspace` before invoking atomic-agent. It must not start a second run in the same workspace while a lock exists.

**Files:**
- Modify: `src/boardroom_os/execution/atomic_executor.py`
- Create or modify: `tests/execution/test_atomic_agent_executor.py`
- Test: `tests/negative/test_atomic_agent_executor_fail_closed.py`

- [ ] **Step 1: Add runtime factory tests with mocked real provider adapter boundary**

Append to `tests/execution/test_atomic_agent_executor.py`:

```python

def test_atomic_runtime_factory_builds_port_with_openai_compatible_provider(tmp_path, monkeypatch):
    from boardroom_os.execution.atomic_executor import AtomicAgentRuntimeFactory

    settings = _settings(tmp_path, monkeypatch)
    factory = AtomicAgentRuntimeFactory(settings=settings)

    runtime_port = factory.build_runtime_port(
        execution_package=_execution_package_for_config(),
        seat_ref="seat.worker.implementation",
        workspace_root=tmp_path,
        run_id="run.atomic.factory.1",
    )

    assert callable(getattr(runtime_port, "invoke", None))
```

This test does not call the provider. It only proves the factory can build a public runtime port from config.

- [ ] **Step 2: Implement `AtomicAgentRuntimeFactory`**

In `src/boardroom_os/execution/atomic_executor.py`, import atomic-agent public/runtime pieces lazily inside the factory method and construct:

```python
class AtomicAgentRuntimeFactory:
    def __init__(self, *, settings: Any) -> None:
        self.settings = settings

    def build_runtime_port(self, *, execution_package: ExecutionPackage, seat_ref: str, workspace_root: Path, run_id: str) -> Any:
        from atomic_agent.agent_loop import AgentLoop, AgentLoopConfig, AgentLoopDependencies
        from atomic_agent.artifacts import ArtifactWriter, ArtifactWriterConfig
        from atomic_agent.command_tools import CommandPolicy, CommandSpec, CommandToolConfig, CommandTools
        from atomic_agent.event_recorder import EventRecorder, EventRecorderConfig
        from atomic_agent.filesystem_tools import FilesystemToolConfig, FilesystemTools
        from atomic_agent.path_guard import WorkspacePathGuard
        from atomic_agent.providers.openai_compatible import OpenAICompatibleProviderAdapter
        from atomic_agent.runtime_port import BoardroomAgentRuntimePortAdapter
        from atomic_agent.web_fetch_tools import NetworkAllowRule, NetworkPolicy, WebFetchToolConfig, WebFetchTools

        role_slot = self.settings.role_slot_by_seat(seat_ref)
        provider_options = self.settings.openai_compatible_options(role_slot.provider_profile_ref)
        runtime = self.settings.runtime.atomic_agent
        workspace_root = workspace_root.resolve()
        workspace_root.mkdir(parents=True, exist_ok=True)
        event_root = Path(runtime.event_stream_root)
        artifact_root = Path(runtime.artifact_root)
        event_root.mkdir(parents=True, exist_ok=True)
        artifact_root.mkdir(parents=True, exist_ok=True)
        guard = WorkspacePathGuard(workspace_root, [path.value for path in execution_package.allowed_write_set])
        filesystem_tools = FilesystemTools(
            guard,
            FilesystemToolConfig(**runtime.filesystem.model_dump()),
        )
        command_policy = CommandPolicy(
            {
                command.command_id.value: CommandSpec(
                    argv=tuple(command.command),
                    cwd=command.cwd,
                    timeout_seconds=None,
                    env=None,
                    allow_network=False,
                )
                for command in execution_package.commands
            }
        )
        command_tools = CommandTools(
            guard,
            command_policy,
            CommandToolConfig(**runtime.commands.model_dump()),
        )
        network_policy = NetworkPolicy(
            tuple(
                NetworkAllowRule(
                    rule.rule_id,
                    rule.scheme,
                    rule.host,
                    rule.port,
                    rule.path_prefix,
                )
                for rule in runtime.network.allow_rules
            )
        )
        web_fetch_tools = WebFetchTools(network_policy, WebFetchToolConfig(timeout_seconds=30, max_response_bytes=200000))
        recorder = EventRecorder(
            run_id=run_id,
            config=EventRecorderConfig(
                event_stream_path=event_root / f"{run_id}.jsonl",
                event_stream_ref=f"{run_id}.jsonl",
            ),
            clock=lambda: datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        )
        artifact_writer = ArtifactWriter(
            ArtifactWriterConfig(
                artifact_root=artifact_root,
                artifact_ref_prefix=f"artifact://{run_id}",
            )
        )
        loop = AgentLoop(
            AgentLoopConfig(run_id=run_id),
            AgentLoopDependencies(
                provider=OpenAICompatibleProviderAdapter(provider_options),
                filesystem_tools=filesystem_tools,
                command_tools=command_tools,
                event_recorder=recorder,
                artifact_writer=artifact_writer,
                runtime_clock=__import__("time").monotonic,
                web_fetch_tools=web_fetch_tools,
            ),
        )
        return BoardroomAgentRuntimePortAdapter(loop)
```

Refine paths so event/artifact roots are resolved relative to the current project root or `BOARDROOM_EVIDENCE_ROOT` if that is implemented in config. Do not silently write outside the configured evidence root.

- [ ] **Step 3: Add factory fail-closed tests**

Add tests for:

```python

def test_atomic_runtime_factory_rejects_command_executable_not_absolute(tmp_path, monkeypatch):
    from boardroom_os.execution.atomic_executor import AtomicAgentRuntimeFactory

    settings = _settings(tmp_path, monkeypatch)
    package = _execution_package_for_config()

    with pytest.raises(ValueError, match="command executable must be an absolute path"):
        AtomicAgentRuntimeFactory(settings=settings).build_runtime_port(
            execution_package=package,
            seat_ref="seat.worker.implementation",
            workspace_root=tmp_path,
            run_id="run.atomic.factory.bad-command",
        )
```

Then adjust `_execution_package_for_config()` in executor tests or create a second fixture with absolute `sys.executable` command for factory happy path. Atomic-agent `CommandPolicy` requires command executable absolute.

- [ ] **Step 4: Run factory tests**

Run:

```bash
PYTHONPATH=src:. python -m pytest tests/execution/test_atomic_agent_executor.py tests/negative/test_atomic_agent_executor_fail_closed.py -q --tb=short --basetemp .pytest-tmp-v2090h-factory-green
```

Expected: all tests pass.

- [ ] **Step 5: Commit runtime factory**

Run:

```bash
git add src/boardroom_os/execution/atomic_executor.py tests/execution/test_atomic_agent_executor.py tests/negative/test_atomic_agent_executor_fail_closed.py
git commit -m "feat(execution): 构造真实原子运行时"
```

Expected: commit created, unless commits are not authorized.

---

### Task 10: Add real provider-backed proving helper and test

**Files:**
- Create: `scripts/run_tiny_atomic_agent_executor.py`
- Create: `tests/proving/test_tiny_atomic_agent_executor.py`
- Modify: `README.md`

- [ ] **Step 1: Create proving helper script**

Create `scripts/run_tiny_atomic_agent_executor.py` with a CLI that:

1. Loads `BOARDROOM_RUNTIME_CONFIG`, `BOARDROOM_PROVIDERS_CONFIG`, and `BOARDROOM_ROLES_CONFIG` from environment or defaults.
2. Builds a scratch workspace under `.evidence/atomic-agent/proving-workspace`.
3. Constructs a minimal `ExecutionPackage` with:
   - `seat_ref = seat.worker.implementation`
   - provider/model matching `provider.openai-compatible.primary`
   - `allowed_write_set = ("work/",)`
   - command id `cmd.check-output`
   - command argv `(sys.executable, "-c", "from pathlib import Path; p=Path('work/real-provider-output.txt'); raise SystemExit(0 if p.exists() and p.read_text(encoding='utf-8').strip() else 3)")`
4. Builds runtime port with `AtomicAgentRuntimeFactory`.
5. Executes `AtomicAgentExecutor` with `provider_transport_kind="real"`.
6. Prints JSON with `atomic_run_id`, `event_stream_ref`, `events_hash`, `provider_attempt_ref`, `work_product_ref`, and `source_lineage_inputs`.

The script must exit non-zero on any exception and must not catch errors broadly except to print the exception type/message to stderr.

- [ ] **Step 2: Create real-provider proving test**

Create `tests/proving/test_tiny_atomic_agent_executor.py`:

```python
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
```

This test is skipped without `OPENAI_API_KEY`; when the key is present, it must perform a real provider-backed atomic-agent run. Do not satisfy it with fake provider transport.

- [ ] **Step 3: Add README section**

Append or update README atomic-agent section with:

```markdown
### V2-090H atomic-agent executor config

Boardroom OS now separates runtime, provider, and role-slot configuration:

- `config/boardroom-runtime.example.yaml` — atomic executor mode, event/artifact roots, tool limits, budgets, and default-deny network policy.
- `config/boardroom-providers.example.yaml` — OpenAI-compatible provider profiles. This is the only place for model, base URL, timeout, stream, and request parameters.
- `config/boardroom-roles.example.yaml` — role slot bindings from Boardroom seats to provider profile refs, skills, tools, and budget overrides.

`.env` / `.env.template` only carry config paths, secrets, and local bootstrap paths. Old `BOARDROOM_OPENAI_*` model parameters are rejected when the new config paths are present.

To run the minimal real provider atomic executor proving helper:

```bash
OPENAI_API_KEY=... PYTHONPATH=src:. python scripts/run_tiny_atomic_agent_executor.py
```

A successful atomic-agent run is execution evidence only. It still does not directly mark a ticket completed or closeout passed.
```

- [ ] **Step 4: Run real proving test when key is available**

Run:

```bash
PYTHONPATH=src:. python -m pytest tests/proving/test_tiny_atomic_agent_executor.py -q --tb=short --basetemp .pytest-tmp-v2090h-real-provider
```

Expected with `OPENAI_API_KEY`: test passes and stdout contains atomic run refs. Expected without `OPENAI_API_KEY`: test is skipped; do not claim V2-090H complete until a real-provider run has passed in an authorized environment.

- [ ] **Step 5: Commit proving helper**

Run:

```bash
git add scripts/run_tiny_atomic_agent_executor.py tests/proving/test_tiny_atomic_agent_executor.py README.md
git commit -m "test(execution): 增加真实原子执行证明"
```

Expected: commit created, unless commits are not authorized.

---

### Task 11: Final regression, documentation closeout, and status updates

**Files:**
- Modify: `doc/04-implementation/backlog.md`
- Modify: `doc/04-implementation/acceptance-criteria.md`
- Modify: `doc/04-implementation/INDEX.md`
- Modify: `doc/05-project-log/2026-06.md`
- Modify if architectural decision is considered accepted: `doc/05-project-log/decisions.md`

- [ ] **Step 1: Run targeted V2-090H suite**

Run:

```bash
PYTHONPATH=src:. python -m pytest tests/config/test_boardroom_config.py tests/negative/test_boardroom_config_fail_closed.py tests/execution/test_atomic_agent_invocation_compiler.py tests/execution/test_atomic_agent_executor.py tests/negative/test_atomic_agent_executor_fail_closed.py tests/proving/test_tiny_atomic_agent_executor.py -q --tb=short --basetemp .pytest-tmp-v2090h-targeted-final
```

Expected: all non-real-provider tests pass; `test_tiny_atomic_agent_executor_real_provider_produces_command_evidence` passes if `OPENAI_API_KEY` is set, otherwise skips. If skipped, do not mark V2-090H DONE.

- [ ] **Step 2: Run V2-090G and evidence regressions**

Run:

```bash
PYTHONPATH=src:. python -m pytest tests/execution/test_atomic_agent_result_projection.py tests/negative/test_atomic_agent_integration_fail_closed.py tests/proving/test_tiny_atomic_agent_bridge.py tests/evidence/test_evidence_verifier.py tests/reducers/test_completion_gate_with_evidence.py -q --tb=short --basetemp .pytest-tmp-v2090h-regression-final
```

Expected: all pass.

- [ ] **Step 3: Run diff check**

Run:

```bash
git diff --check
```

Expected: no whitespace errors.

- [ ] **Step 4: Update `doc/04-implementation/backlog.md` only after real provider proof passes**

Change:

- V2-090H status from `TODO` to `DONE`.
- Add completion evidence line listing exact tests and real-provider proving run.
- Phase 9 progress from `6 / 8` to `7 / 8`.
- Top TL;DR current incomplete package remains V2-090F BLOCKED unless user explicitly unblocks it.

Do not change V2-090F to TODO/IN_PROGRESS without explicit human approval.

- [ ] **Step 5: Update `doc/04-implementation/acceptance-criteria.md` only after real provider proof passes**

Check the V2-090H checkbox:

```markdown
- [x] AC-V2-EXECUTION-001 / AC-V2-EXECUTION-002 / AC-V2-EVIDENCE-001 / AC-V2-EVIDENCE-002（atomic-agent 主执行路径）— 由 V2-090H 证明：...
```

Keep V2-090F package/closeout checkbox unchecked.

- [ ] **Step 6: Update `doc/05-project-log/2026-06.md`**

Append a single V2-090H log entry with:

- work package id and title;
- config files created;
- executor files created;
- negative tests run;
- real provider proving command and outcome;
- explicit boundary that V2-090F remains BLOCKED pending human review.

- [ ] **Step 7: Update `doc/04-implementation/INDEX.md`**

Ensure it includes:

```markdown
| `v2-090h-atomic-agent-executor-switch-spec.md` | V2-090H atomic-agent（原子智能体）executor switch（执行器切换）规范 |
| `v2-090h-atomic-agent-executor-switch-implementation-plan.md` | V2-090H atomic-agent（原子智能体）executor switch（执行器切换）实施计划 |
```

- [ ] **Step 8: Optional decision log**

If expert review accepts the three-file configuration as architecture policy, add a DEC entry to `doc/05-project-log/decisions.md`:

```markdown
## DEC-00XX: Boardroom provider configuration uses three-file config

- 状态：Accepted
- 日期：2026-06-10

### 决策

Boardroom OS 的 runtime/provider/role-slot 配置拆分为 runtime.yaml、providers.yaml、roles.yaml；`.env` 只保留路径和密钥。首版 provider protocol 只支持 OpenAI-compatible profiles。

### 理由

避免 `.env` 成为 provider/model 参数的第二事实源，并允许不同角色席位绑定不同 provider/model 以互补能力。
```

Do not add this DEC before human/expert review if the user wants the design reviewed first.

- [ ] **Step 9: Commit closeout docs**

Run:

```bash
git add doc/04-implementation/backlog.md doc/04-implementation/acceptance-criteria.md doc/04-implementation/INDEX.md doc/05-project-log/2026-06.md doc/05-project-log/decisions.md doc/06-reference/atomic-agent-contract-lock.md
git commit -m "docs(v2-090h): 记录原子执行器切换"
```

Expected: commit created, unless commits are not authorized.

---

## Self-Review

- Spec coverage（规范覆盖）：本计划覆盖 V2-090H spec 的三文件配置、`.env` 新定位、OpenAI-compatible-only provider、role slot provider binding、config-aware invocation compilation、runtime factory、executor fail-closed 矩阵、real provider proving、以及 V2-090F 不自动恢复边界。
- Placeholder scan（占位符扫描）：未使用 TBD / TODO / “类似上一步” 作为实施内容；每个任务都有具体文件、测试代码、命令和期望结果。
- Type consistency（类型一致性）：计划中的公共名保持一致：`BoardroomConfigPaths`、`BoardroomSettings`、`AtomicExecutionRequest`、`AtomicExecutionResult`、`AtomicAgentRuntimeFactory`、`AtomicAgentExecutor`、`compile_with_settings`。
- Test-first check（测试优先检查）：配置、编译器、executor、负例和 proving helper 均先写测试，再实现；V2-090H 不用 fake provider transport 满足真实 proving path。
- Parameterization check（参数化检查）：预算只来自 YAML budget profiles / role overrides / resolved snapshot，不进入 `.env`；工具集由 resolver 解析；declared command ids 只来自 `ExecutionPackage.commands`。
- Boundary check（边界检查）：计划没有让 atomic-agent completed 直接完成 ticket/closeout；完成后仍要求 EvidenceVerifier / Checker / Reducer / CloseoutGate 决策，且 V2-090F 仍等待人工评审。
