# V2-090J Atomic Action Protocol Repair Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Repair the V2-090I medium-scenario blocker by making atomic-agent action execution stable for medium-complexity tasks without weakening Boardroom OS evidence gates.

**Architecture:** Implement the protocol fix first in sibling `atomic-agent`（原子智能体）: explicit `AgentActionBatch`（智能体动作批次）, audited batch execution, and optional required-output command checkpoint（必需产物命令检查点）. Then update Boardroom OS（董事会系统） integration to compile protocol/checkpoint metadata, align tool policy around `apply_patch`（补丁写入工具）, and add a V2-090J real-provider proving runner（真实供应商证明运行器） that revalidates the medium package/CLI path.

**Tech Stack:** Python 3.12, pydantic, pytest, existing `atomic-agent` package, Boardroom OS config/execution modules, OpenAI-compatible provider config through existing YAML and `.env` paths.

---

## File Structure

### atomic-agent files to modify

- `/Users/bill/projects/atomic-agent/src/atomic_agent/models.py` — add `AgentActionBatch` model（动作批次模型） and optional batch/checkpoint event payload helpers if needed.
- `/Users/bill/projects/atomic-agent/src/atomic_agent/action_parser.py` — add parser that returns a parsed turn containing one or more ordered `AgentAction`（动作） objects.
- `/Users/bill/projects/atomic-agent/src/atomic_agent/agent_loop.py` — execute parsed actions in order, enforce batch limits, and add required-output checkpoint scheduling.
- `/Users/bill/projects/atomic-agent/src/atomic_agent/event_recorder.py` — add event recording for batch parsed/executed or reuse existing per-action events with batch metadata.
- `/Users/bill/projects/atomic-agent/src/atomic_agent/evidence.py` — ensure batch/checkpoint event stream remains verifiable.
- `/Users/bill/projects/atomic-agent/docs/03-contracts/agent-action-protocol.md` — document `agent-action-batch-v1`.
- `/Users/bill/projects/atomic-agent/docs/03-contracts/event-stream-protocol.md` — document batch/checkpoint event semantics.
- `/Users/bill/projects/atomic-agent/tests/test_action_parser.py` — parser negative/happy coverage.
- `/Users/bill/projects/atomic-agent/tests/test_agent_loop.py` — batch execution and checkpoint loop coverage.
- `/Users/bill/projects/atomic-agent/tests/test_evidence.py` — event stream verification coverage.

### Boardroom OS files to modify

- `src/boardroom_os/execution/atomic_agent.py` — compile protocol/checkpoint metadata; validate batch/checkpoint event streams; align tool resolver behavior.
- `src/boardroom_os/execution/atomic_executor.py` — pass metadata through unchanged and keep evidence gates intact.
- `scripts/run_v2_090i_medium_scenario.py` — remove scenario-local `apply_patch` workaround once formal tool policy exists, or make it consume formal config.
- `scripts/run_v2_090j_medium_scenario.py` — new proving runner for repaired medium scenario.
- `tests/execution/test_atomic_agent_invocation_compiler.py` — metadata/tool policy tests.
- `tests/execution/test_atomic_agent_executor.py` — validator acceptance for batch/checkpoint events.
- `tests/negative/test_atomic_agent_executor_fail_closed.py` — fail-closed tests for missing command evidence and unsupported tool policy.
- `tests/proving/test_v2_090j_medium_scenario_script.py` — non-provider tests for runner/report/metadata.
- `tests/proving/test_v2_090j_medium_scenario.py` — default-skipped real-provider proving test.
- `doc/04-implementation/backlog.md`, `doc/04-implementation/acceptance-criteria.md`, `doc/05-project-log/2026-06.md`, `scripts/README.md` — status and usage documentation.

---

## Task 0: atomic-agent baseline and shape verification

**Files:**
- Inspect only: `/Users/bill/projects/atomic-agent/src/atomic_agent/models.py`
- Inspect only: `/Users/bill/projects/atomic-agent/src/atomic_agent/action_parser.py`
- Inspect only: `/Users/bill/projects/atomic-agent/src/atomic_agent/agent_loop.py`
- Inspect only: `/Users/bill/projects/atomic-agent/tests/`

- [ ] **Step 1: Verify sibling repository is present**

```bash
cd /Users/bill/projects/atomic-agent
test -f src/atomic_agent/models.py
test -f src/atomic_agent/action_parser.py
test -f src/atomic_agent/agent_loop.py
grep -R "class AgentAction" -n src/atomic_agent
```

Expected: all commands exit 0. If any file is missing, stop and update this plan before implementing.

- [ ] **Step 2: Record baseline working tree state**

```bash
cd /Users/bill/projects/atomic-agent
git status --short --branch
```

Expected: implementation owner records any pre-existing dirty files. Do not overwrite unrelated user changes.

- [ ] **Step 3: Run atomic-agent baseline tests**

```bash
cd /Users/bill/projects/atomic-agent
python -m pytest tests/ -q --tb=short
```

Expected: existing suite passes or known unrelated failures are recorded before Task 1 begins. Boardroom Task 4 must not start until Task 1-3 atomic-agent targeted tests pass.

---

## Task 1: atomic-agent parser supports explicit action batches

**Files:**
- Modify: `/Users/bill/projects/atomic-agent/src/atomic_agent/models.py`
- Modify: `/Users/bill/projects/atomic-agent/src/atomic_agent/action_parser.py`
- Modify: `/Users/bill/projects/atomic-agent/tests/test_action_parser.py`
- Modify docs: `/Users/bill/projects/atomic-agent/docs/03-contracts/agent-action-protocol.md`

- [ ] **Step 1: Add failing parser tests**

Append tests to `/Users/bill/projects/atomic-agent/tests/test_action_parser.py`:

```python
import json

import pytest

from atomic_agent.action_parser import ActionParseError, parse_agent_turn


def test_parse_agent_turn_accepts_single_action() -> None:
    parsed = parse_agent_turn(json.dumps({
        "action_id": "step-0001",
        "action": "write_file",
        "reason_summary": "Create file.",
        "input": {"path": "work/a.txt", "content": "hello"},
    }))

    assert parsed.protocol == "agent-action-v1"
    assert [action.action_id for action in parsed.actions] == ["step-0001"]


def test_parse_agent_turn_accepts_explicit_batch_v1() -> None:
    parsed = parse_agent_turn(json.dumps({
        "batch_id": "batch-0001",
        "protocol": "agent-action-batch-v1",
        "reason_summary": "Create and check package.",
        "actions": [
            {
                "action_id": "step-0001",
                "action": "write_file",
                "reason_summary": "Create file.",
                "input": {"path": "work/a.txt", "content": "hello"},
            },
            {
                "action_id": "step-0002",
                "action": "run_command",
                "reason_summary": "Run declared check.",
                "input": {"command_id": "check"},
            },
        ],
    }))

    assert parsed.protocol == "agent-action-batch-v1"
    assert parsed.batch_id == "batch-0001"
    assert [action.action_id for action in parsed.actions] == ["step-0001", "step-0002"]


def test_parse_agent_turn_rejects_bare_json_array() -> None:
    with pytest.raises(ActionParseError, match="explicit batch object"):
        parse_agent_turn(json.dumps([
            {
                "action_id": "step-0001",
                "action": "write_file",
                "reason_summary": "Create file.",
                "input": {"path": "work/a.txt", "content": "hello"},
            }
        ]))


def test_parse_agent_turn_rejects_concatenated_json_objects() -> None:
    first = json.dumps({
        "action_id": "step-0001",
        "action": "write_file",
        "reason_summary": "Create file.",
        "input": {"path": "work/a.txt", "content": "hello"},
    })
    second = json.dumps({
        "action_id": "step-0002",
        "action": "run_command",
        "reason_summary": "Run declared check.",
        "input": {"command_id": "check"},
    })

    with pytest.raises(ActionParseError, match="valid JSON"):
        parse_agent_turn(first + second)


def test_parse_agent_turn_rejects_batch_without_protocol() -> None:
    with pytest.raises(ActionParseError, match="batch_like_without_protocol"):
        parse_agent_turn(json.dumps({
            "batch_id": "batch-0001",
            "reason_summary": "Missing protocol.",
            "actions": [],
        }))
```

- [ ] **Step 2: Run parser tests and verify they fail**

```bash
cd /Users/bill/projects/atomic-agent
python -m pytest tests/test_action_parser.py -q --tb=short
```

Expected: failures because `parse_agent_turn` and batch models do not exist.

- [ ] **Step 3: Implement parser models**

In `/Users/bill/projects/atomic-agent/src/atomic_agent/models.py`, add:

```python
class AgentActionBatch(StrictModel):
    batch_id: str
    protocol: str
    reason_summary: str
    actions: list[AgentAction]

    @model_validator(mode="after")
    def validate_batch(self):
        if self.protocol != "agent-action-batch-v1":
            raise ValueError("batch protocol must be agent-action-batch-v1")
        if not self.actions:
            raise ValueError("batch actions must not be empty")
        seen: set[str] = set()
        for action in self.actions:
            if action.action_id in seen:
                raise ValueError("batch action_id values must be unique")
            seen.add(action.action_id)
        submit_indexes = [
            index for index, action in enumerate(self.actions)
            if action.action == AgentActionType.SUBMIT_RESULT
        ]
        if submit_indexes and submit_indexes[-1] != len(self.actions) - 1:
            raise ValueError("submit_result must be the final batch action")
        return self


class ParsedAgentTurn(StrictModel):
    protocol: str
    actions: list[AgentAction]
    batch_id: str | None = None
    reason_summary: str | None = None
```

- [ ] **Step 4: Implement parser function**

In `/Users/bill/projects/atomic-agent/src/atomic_agent/action_parser.py`, keep `parse_agent_action` for compatibility and add:

```python
from atomic_agent.models import AgentAction, AgentActionBatch, ParsedAgentTurn


def parse_agent_turn(provider_output: str) -> ParsedAgentTurn:
    try:
        parsed: Any = json.loads(provider_output)
    except json.JSONDecodeError as error:
        raise ActionParseError("invalid_json", "Provider output must be valid JSON.") from error

    if isinstance(parsed, list):
        raise ActionParseError(
            "invalid_action_batch",
            "Provider output must use an explicit batch object with protocol agent-action-batch-v1.",
        )
    if not isinstance(parsed, dict):
        raise ActionParseError("invalid_action", "Provider output JSON must be an object.")

    if parsed.get("protocol") == "agent-action-batch-v1":
        try:
            batch = AgentActionBatch.model_validate(parsed)
        except ValidationError as error:
            raise ActionParseError("schema_validation_failed", str(error)) from error
        return ParsedAgentTurn(
            protocol=batch.protocol,
            batch_id=batch.batch_id,
            reason_summary=batch.reason_summary,
            actions=batch.actions,
        )
    if "actions" in parsed or "batch_id" in parsed:
        raise ActionParseError(
            "batch_like_without_protocol",
            "Batch-shaped provider output must include protocol agent-action-batch-v1.",
        )

    try:
        action = AgentAction.model_validate(parsed)
    except ValidationError as error:
        raise ActionParseError("schema_validation_failed", str(error)) from error
    return ParsedAgentTurn(protocol="agent-action-v1", actions=[action])
```

- [ ] **Step 5: Re-run parser tests**

```bash
cd /Users/bill/projects/atomic-agent
python -m pytest tests/test_action_parser.py -q --tb=short
```

Expected: parser tests pass.

- [ ] **Step 6: Update action protocol docs**

Add an `AgentActionBatch` section to `/Users/bill/projects/atomic-agent/docs/03-contracts/agent-action-protocol.md` with the exact JSON shape from the spec. State that bare arrays, concatenated JSON objects, Markdown-wrapped JSON, and `action_envelope` remain invalid.

---

## Task 2: atomic-agent loop executes batches with audit events and fail-closed semantics

**Files:**
- Modify: `/Users/bill/projects/atomic-agent/src/atomic_agent/agent_loop.py`
- Modify: `/Users/bill/projects/atomic-agent/src/atomic_agent/event_recorder.py`
- Modify: `/Users/bill/projects/atomic-agent/src/atomic_agent/evidence.py`
- Modify: `/Users/bill/projects/atomic-agent/tests/test_agent_loop.py`
- Modify: `/Users/bill/projects/atomic-agent/tests/test_evidence.py`

- [ ] **Step 1: Add failing loop tests for batch execution**

Append to `/Users/bill/projects/atomic-agent/tests/test_agent_loop.py`:

```python
def test_agent_loop_executes_batch_actions_in_order(tmp_path: Path) -> None:
    invocation = make_invocation(
        tmp_path,
        tools=["write_file", "run_command", "submit_result"],
        commands={"check": command_that_exits(0)},
        budgets={"max_steps": 5, "max_parse_failures": 0, "max_actions_per_turn": 4},
    )
    provider = FakeProvider([
        json.dumps({
            "batch_id": "batch-0001",
            "protocol": "agent-action-batch-v1",
            "reason_summary": "Create, check, and submit.",
            "actions": [
                {
                    "action_id": "step-0001",
                    "action": "write_file",
                    "reason_summary": "Create output.",
                    "input": {"path": "work/output.txt", "content": "ok"},
                },
                {
                    "action_id": "step-0002",
                    "action": "run_command",
                    "reason_summary": "Run declared check.",
                    "input": {"command_id": "check"},
                },
                {
                    "action_id": "step-0003",
                    "action": "submit_result",
                    "reason_summary": "Submit checked output.",
                    "input": {"summary": "done", "produced_paths": ["work/output.txt"], "evidence_refs": ["check"]},
                },
            ],
        })
    ])

    result = run_loop(invocation, provider)

    assert result.status == AgentRunStatus.COMPLETED
    events = read_events(result.event_stream_ref)
    assert [event["type"] for event in events].count("action.parsed") == 3
    assert any(event["type"] == "command.completed" and event["payload"]["command_id"] == "check" for event in events)
```

- [ ] **Step 2: Add failing negative tests**

Append:

```python
def test_agent_loop_rejects_batch_over_action_limit(tmp_path: Path) -> None:
    invocation = make_invocation(
        tmp_path,
        tools=["write_file", "submit_result"],
        budgets={"max_steps": 5, "max_parse_failures": 0, "max_actions_per_turn": 1},
    )
    provider = FakeProvider([
        json.dumps({
            "batch_id": "batch-0001",
            "protocol": "agent-action-batch-v1",
            "reason_summary": "Too many actions.",
            "actions": [
                {"action_id": "step-0001", "action": "write_file", "reason_summary": "A", "input": {"path": "work/a.txt", "content": "a"}},
                {"action_id": "step-0002", "action": "write_file", "reason_summary": "B", "input": {"path": "work/b.txt", "content": "b"}},
            ],
        })
    ])

    result = run_loop(invocation, provider)

    assert result.status == AgentRunStatus.FAILED
    assert result.failure_kind == "action_parse_failed"
    assert not (tmp_path / "workspace" / "work" / "a.txt").exists()


def test_agent_loop_stops_batch_on_policy_denied(tmp_path: Path) -> None:
    invocation = make_invocation(
        tmp_path,
        allowed_write_set=["work/allowed/"],
        tools=["write_file", "submit_result"],
        budgets={"max_steps": 5, "max_parse_failures": 0, "max_actions_per_turn": 3},
    )
    provider = FakeProvider([
        json.dumps({
            "batch_id": "batch-0001",
            "protocol": "agent-action-batch-v1",
            "reason_summary": "Second action escapes.",
            "actions": [
                {"action_id": "step-0001", "action": "write_file", "reason_summary": "Allowed.", "input": {"path": "work/allowed/a.txt", "content": "a"}},
                {"action_id": "step-0002", "action": "write_file", "reason_summary": "Denied.", "input": {"path": "work/denied/b.txt", "content": "b"}},
                {"action_id": "step-0003", "action": "submit_result", "reason_summary": "Should not run.", "input": {"summary": "bad", "produced_paths": ["work/denied/b.txt"], "evidence_refs": []}},
            ],
        })
    ])

    result = run_loop(invocation, provider)

    assert result.status == AgentRunStatus.FAILED
    assert result.failure_kind == "policy_denied"
    events = read_events(result.event_stream_ref)
    parsed_ids = [event["payload"]["action_id"] for event in events if event["type"] == "action.parsed"]
    assert parsed_ids == ["step-0001", "step-0002"]
```

- [ ] **Step 3: Run loop tests and verify failure**

```bash
cd /Users/bill/projects/atomic-agent
python -m pytest tests/test_agent_loop.py -q --tb=short
```

Expected: new tests fail until loop consumes parsed turns.

- [ ] **Step 4: Implement loop batch execution**

First read the existing `agent_loop.py` action path and identify the smallest existing block that already performs permission checks, tool execution, observation appending, result submission, and terminal failure handling. Extract only that block into one helper; do not restructure provider retry, budget accounting, or event stream ownership in this task.

Use this helper shape unless the existing code requires additional already-present context:

```python
def _execute_parsed_action(
    self,
    *,
    invocation: AgentInvocation,
    run_state: AgentRunState,
    action: AgentAction,
    turn: ParsedAgentTurn,
    action_index: int,
) -> ActionExecutionOutcome:
    existing_outcome = self._execute_existing_single_action_path(
        invocation=invocation,
        run_state=run_state,
        action=action,
    )
    return ActionExecutionOutcome.from_existing(existing_outcome)
```

`ActionExecutionOutcome` may be an existing result/terminal signal type if one already exists. If no such type exists, define a narrow dataclass with `terminal: bool`, `failed: bool`, and `observation: str | None`. Keep single action and batch execution on this one helper path.

Then change `agent_loop.py` so provider output is parsed with `parse_agent_turn`. For each parsed action:

```python
turn = parse_agent_turn(provider_output)
max_actions = requirements.max_actions_per_turn
if len(turn.actions) > max_actions:
    raise ActionParseError("too_many_actions", f"batch contains {len(turn.actions)} actions, limit is {max_actions}")
for action in turn.actions:
    self.dependencies.event_recorder.record_action_parsed({
        **action.model_dump(mode="json"),
        "batch_id": turn.batch_id,
        "protocol": turn.protocol,
    })
    # Reuse existing permission, submit_result, tool execution, and failure logic.
```

- [ ] **Step 5: Add `max_actions_per_turn` validation**

In the invocation requirements loader, accept `budgets.max_actions_per_turn`. If absent, default to `1` for backward compatibility. Reject non-integer, bool, zero, or negative values.

- [ ] **Step 6: Re-run loop and evidence tests**

```bash
cd /Users/bill/projects/atomic-agent
python -m pytest tests/test_action_parser.py tests/test_agent_loop.py tests/test_evidence.py -q --tb=short
```

Expected: all pass.

---

## Task 3: atomic-agent required-output validator checkpoint

**Files:**
- Modify: `/Users/bill/projects/atomic-agent/src/atomic_agent/agent_loop.py`
- Modify: `/Users/bill/projects/atomic-agent/src/atomic_agent/models.py` if a checkpoint model is needed
- Modify: `/Users/bill/projects/atomic-agent/tests/test_agent_loop.py`
- Modify docs: `/Users/bill/projects/atomic-agent/docs/03-contracts/agent-runtime-port.md`

- [ ] **Step 1: Add failing checkpoint test**

Append to `/Users/bill/projects/atomic-agent/tests/test_agent_loop.py`:

```python
def test_agent_loop_runs_required_output_checkpoint_when_paths_exist(tmp_path: Path) -> None:
    invocation = make_invocation(
        tmp_path,
        tools=["write_file", "submit_result"],
        commands={"check": command_that_exits(0)},
        output_requirements={
            "required_output_checkpoint": {
                "when_all_paths_exist": ["work/a.txt", "work/b.txt"],
                "run_command_id": "check",
                "max_auto_runs": 1,
            }
        },
        budgets={"max_steps": 5, "max_parse_failures": 0, "max_actions_per_turn": 2},
    )
    provider = FakeProvider([
        json.dumps({
            "batch_id": "batch-0001",
            "protocol": "agent-action-batch-v1",
            "reason_summary": "Create required outputs.",
            "actions": [
                {"action_id": "step-0001", "action": "write_file", "reason_summary": "A.", "input": {"path": "work/a.txt", "content": "a"}},
                {"action_id": "step-0002", "action": "write_file", "reason_summary": "B.", "input": {"path": "work/b.txt", "content": "b"}},
            ],
        }),
        json.dumps({
            "action_id": "step-0003",
            "action": "submit_result",
            "reason_summary": "Submit after checkpoint.",
            "input": {"summary": "done", "produced_paths": ["work/a.txt", "work/b.txt"], "evidence_refs": ["check"]},
        }),
    ])

    result = run_loop(invocation, provider)

    assert result.status == AgentRunStatus.COMPLETED
    events = read_events(result.event_stream_ref)
    assert any(event["type"] == "command.completed" and event["payload"]["command_id"] == "check" for event in events)
```

- [ ] **Step 2: Run test and verify failure**

```bash
cd /Users/bill/projects/atomic-agent
python -m pytest tests/test_agent_loop.py::test_agent_loop_runs_required_output_checkpoint_when_paths_exist -q --tb=short
```

Expected: fails because checkpoint is not implemented.

- [ ] **Step 3: Implement checkpoint requirements parsing**

Add to requirements loading:

```python
checkpoint = invocation.output_requirements.get("required_output_checkpoint")
if checkpoint is not None:
    paths = checkpoint.get("when_all_paths_exist")
    command_id = checkpoint.get("run_command_id")
    max_auto_runs = checkpoint.get("max_auto_runs")
    if not isinstance(paths, list) or not all(isinstance(path, str) and path for path in paths):
        return "required_output_checkpoint.when_all_paths_exist must be non-empty string paths"
    if not isinstance(command_id, str) or not command_id:
        return "required_output_checkpoint.run_command_id must be a non-empty string"
    if not isinstance(max_auto_runs, int) or isinstance(max_auto_runs, bool) or max_auto_runs < 1:
        return "required_output_checkpoint.max_auto_runs must be a positive integer"
```

- [ ] **Step 4: Implement checkpoint scheduler**

After each successful workspace mutation, check whether all paths exist under workspace root. If yes and checkpoint run count is below `max_auto_runs`, run the declared command via the same command tool path used for `run_command`. Record normal `tool.attempt.*` and `command.completed` events with action id such as `checkpoint:<command_id>:<count>`. Append observation to state so provider can see command output.

`max_auto_runs` semantics:

- It is the maximum number of automatic checkpoint triggers for one invocation.
- The first failed checkpoint observation is shown to the provider for repair.
- After the configured limit is reached, the loop stops auto-triggering the checkpoint.
- Passing checkpoint output never auto-submits; provider must still emit `submit_result`.

- [ ] **Step 5: Add negative tests**

Add tests proving:

```python
def test_agent_loop_rejects_checkpoint_for_undeclared_command(tmp_path: Path) -> None:
    invocation = make_invocation(
        tmp_path,
        commands={},
        output_requirements={
            "required_output_checkpoint": {
                "when_all_paths_exist": ["work/a.txt"],
                "run_command_id": "missing",
                "max_auto_runs": 1,
            }
        },
    )

    result = run_loop(invocation, FakeProvider([]))

    assert result.status == AgentRunStatus.FAILED
    assert result.failure_kind == "invalid_invocation"
```

and:

```python
def test_agent_loop_does_not_auto_submit_after_checkpoint_passes(tmp_path: Path) -> None:
    invocation = make_invocation(
        tmp_path,
        tools=["write_file"],
        commands={"check": command_that_exits(0)},
        output_requirements={
            "required_output_checkpoint": {
                "when_all_paths_exist": ["work/a.txt"],
                "run_command_id": "check",
                "max_auto_runs": 1,
            }
        },
        budgets={"max_steps": 1, "max_parse_failures": 0, "max_actions_per_turn": 1},
    )
    provider = FakeProvider([
        json.dumps({"action_id": "step-0001", "action": "write_file", "reason_summary": "A.", "input": {"path": "work/a.txt", "content": "a"}})
    ])

    result = run_loop(invocation, provider)

    assert result.status == AgentRunStatus.FAILED
    assert result.failure_kind == "max_steps_exceeded"
```

- [ ] **Step 6: Run targeted atomic-agent tests**

```bash
cd /Users/bill/projects/atomic-agent
python -m pytest tests/test_action_parser.py tests/test_agent_loop.py tests/test_evidence.py tests/test_runtime_port.py -q --tb=short
```

Expected: all pass.

---

## Task 4: Boardroom compiler emits protocol, batch, and checkpoint metadata

**Files:**
- Modify: `src/boardroom_os/execution/atomic_agent.py`
- Modify: `tests/execution/test_atomic_agent_invocation_compiler.py`

- [ ] **Step 1: Add failing compiler test**

Append to `tests/execution/test_atomic_agent_invocation_compiler.py`:

```python
def test_atomic_invocation_compiler_emits_action_protocol_and_checkpoint_metadata(tmp_path: Path) -> None:
    settings = _settings_with_atomic_agent_defaults(tmp_path)
    package = _execution_package_with_required_outputs_and_command()

    invocation = AtomicInvocationCompiler(workspace_root=tmp_path).compile_with_settings(
        execution_package=package,
        settings=settings,
        seat_ref="seat.worker.implementation",
    )

    assert invocation.metadata["action_protocol"] == "agent-action-batch-v1"
    assert invocation.budgets["max_actions_per_turn"] == settings.runtime.atomic_agent.budget_caps.max_actions_per_turn
    assert invocation.output_requirements["required_output_checkpoint"] == {
        "when_all_paths_exist": [output.value for output in package.required_outputs],
        "run_command_id": package.commands[0].command_id.value,
        "max_auto_runs": settings.runtime.atomic_agent.checkpoints.required_output.max_auto_runs,
    }
```

If helper names differ, create local helpers in the test file using existing fixture style. Do not import V2-090I script helpers into execution unit tests.

- [ ] **Step 2: Run test and verify failure**

```bash
PYTHONPATH=src:. python -m pytest tests/execution/test_atomic_agent_invocation_compiler.py::test_atomic_invocation_compiler_emits_action_protocol_and_checkpoint_metadata -q --tb=short
```

Expected: fails because metadata/budget/checkpoint fields are absent.

- [ ] **Step 3: Add config fields**

In Boardroom config models, add runtime atomic-agent fields:

```python
class AgentExecutionBudgetConfig(BaseModel):
    max_actions_per_turn: int = Field(gt=0, default=1)
```

Also add:

```python
class BudgetCapsConfig(BaseModel):
    max_actions_per_turn: int = Field(gt=0)


class AtomicRequiredOutputCheckpointConfig(BaseModel):
    max_auto_runs: int = Field(gt=0)


class AtomicCheckpointConfig(BaseModel):
    required_output: AtomicRequiredOutputCheckpointConfig
```

Wire `AtomicCheckpointConfig` into `AtomicAgentRuntimeConfig.checkpoints`.

Ensure every `config/boardroom-runtime.example.yaml` budget profile and cap includes:

```yaml
budget_profiles:
  atomic.proving.minimal:
    max_actions_per_turn: 4
  worker.implementation.default:
    max_actions_per_turn: 8
  worker.implementation.large:
    max_actions_per_turn: 8
budget_caps:
  max_actions_per_turn: 8
checkpoints:
  required_output:
    max_auto_runs: 3
```

Do not hardcode provider model/base URL/timeout/reasoning effort/checkpoint retry count.

- [ ] **Step 4: Emit metadata and checkpoint**

In `AtomicInvocationCompiler.compile_with_settings`, include:

```python
budget_payload = {
    key: resolved_budget[key]
    for key in ("max_steps", "max_parse_failures", "max_observation_chars", "max_wall_seconds", "max_actions_per_turn")
}
checkpoint = None
if execution_package.required_outputs:
    if len(execution_package.commands) != 1:
        raise ValueError("required output checkpoint requires exactly one declared command")
    checkpoint = {
        "when_all_paths_exist": [output.value for output in execution_package.required_outputs],
        "run_command_id": execution_package.commands[0].command_id.value,
        "max_auto_runs": settings.runtime.atomic_agent.checkpoints.required_output.max_auto_runs,
    }
output_requirements = {
    **base_invocation.output_requirements,
    "require_command_evidence": True,
    "require_source_lineage": True,
    "declared_command_ids": list(declared_command_ids_from_execution_package(execution_package)),
    "required_output_checkpoint": checkpoint,
}
metadata = {
    **base_invocation.metadata,
    "action_protocol": "agent-action-batch-v1",
    "action_protocol_version": "agent-action-batch-v1",
    "checkpoint_policy": "required-output-single-command-v1",
}
```

V2-090J only supports a single declared command for automatic required-output checkpoint generation. `PackageCommand` currently has no metadata or validator marker field, so packages with multiple commands must fail closed until a command role marker protocol is designed.

- [ ] **Step 5: Run compiler tests**

```bash
PYTHONPATH=src:. python -m pytest tests/config/test_boardroom_config.py tests/negative/test_boardroom_config_fail_closed.py tests/execution/test_atomic_agent_invocation_compiler.py -q --tb=short
```

Expected: pass.

---

## Task 5: Boardroom tool policy makes apply_patch consistency fail closed

**Files:**
- Modify: `src/boardroom_os/execution/atomic_agent.py`
- Modify: `tests/negative/test_atomic_agent_executor_fail_closed.py`
- Modify: `tests/execution/test_atomic_agent_invocation_compiler.py`
- Modify: `scripts/run_v2_090i_medium_scenario.py`

- [ ] **Step 1: Add negative test for inconsistent apply_patch exposure**

Add to `tests/negative/test_atomic_agent_executor_fail_closed.py`:

```python
def test_atomic_invocation_compiler_rejects_apply_patch_when_runtime_policy_does_not_support_it(tmp_path: Path) -> None:
    settings = _settings_with_apply_patch_role_tool_but_disabled_runtime_patch(tmp_path)
    package = _execution_package_with_write_permission()

    with pytest.raises(ValueError, match="apply_patch tool is visible but not supported by runtime policy"):
        AtomicInvocationCompiler(workspace_root=tmp_path).compile_with_settings(
            execution_package=package,
            settings=settings,
            seat_ref="seat.worker.implementation",
        )
```

- [ ] **Step 2: Run test and verify failure**

```bash
PYTHONPATH=src:. python -m pytest tests/negative/test_atomic_agent_executor_fail_closed.py::test_atomic_invocation_compiler_rejects_apply_patch_when_runtime_policy_does_not_support_it -q --tb=short
```

Expected: fails because compiler currently lets resolved tools include `apply_patch`.

- [ ] **Step 3: Add explicit runtime patch support flag**

Add runtime config:

```yaml
filesystem:
  allow_apply_patch: false
```

Model field:

```python
allow_apply_patch: bool = False
```

In `AtomicToolPolicyResolver.resolve_tools`, if `apply_patch` is in resolved tools and runtime filesystem does not support it, raise `ValueError`.

- [ ] **Step 4: Remove V2-090I script-local workaround**

In `scripts/run_v2_090i_medium_scenario.py`, remove the manual filtering:

```python
default_tools = tuple(tool for tool in slot.default_tools if tool != "apply_patch")
"skill_refs": tuple(ref for ref in slot.skill_refs if ref != "skill.filesystem.patch"),
```

Replace it with formal config use:

- In `config/boardroom-runtime.example.yaml`, set `atomic_agent.filesystem.allow_apply_patch: false`.
- In `config/boardroom-runtime.example.yaml` and `config/boardroom-roles.example.yaml`, remove `apply_patch` from default tools and remove `skill.filesystem.patch` from role skill refs unless a later task formally supports patch execution.
- Add one fail-closed test proving that if either config still exposes `apply_patch` while `allow_apply_patch` is false, compilation fails before provider invocation.

- [ ] **Step 5: Run Boardroom tool policy tests**

```bash
PYTHONPATH=src:. python -m pytest tests/execution/test_atomic_agent_invocation_compiler.py tests/negative/test_atomic_agent_executor_fail_closed.py tests/proving/test_v2_090i_medium_scenario_script.py -q --tb=short
```

Expected: pass.

---

## Task 6: Boardroom accepts audited batch/checkpoint event streams without relaxing evidence gates

**Files:**
- Modify: `src/boardroom_os/execution/atomic_agent.py`
- Modify: `tests/execution/test_atomic_agent_executor.py`
- Modify: `tests/negative/test_atomic_agent_executor_fail_closed.py`

- [ ] **Step 1: Add happy test with batch/checkpoint events**

Create or extend an existing fake `AgentRunResult` fixture so event stream contains:

```json
{"type":"provider.turn.completed","payload":{"provider_turn_id":"turn-1","artifact_ref":"artifact://run/provider/turn_000001.txt"}}
{"type":"action.parsed","payload":{"action_id":"step-0001","action":"write_file","batch_id":"batch-0001","protocol":"agent-action-batch-v1"}}
{"type":"workspace.mutation.recorded","payload":{"path":"work/output.txt","after_hash":"sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}}
{"type":"command.completed","payload":{"command_id":"check","exit_code":0}}
{"type":"result.submitted","payload":{"produced_paths":["work/output.txt"],"evidence_refs":["check"]}}
{"type":"run.completed","payload":{}}
```

Assert:

```python
validated = AtomicAgentResultValidator(
    allowed_write_set=("work/",),
    declared_command_ids=("check",),
    event_stream_root=event_root,
).validate(result)

assert validated.evidence_summary["command_results"]["check"]["exit_code"] == 0
```

- [ ] **Step 2: Add negative tests**

Add tests proving:

```python
def test_atomic_result_validator_rejects_batch_without_command_evidence(tmp_path: Path) -> None:
    event_root = tmp_path / "events"
    result = _agent_result_with_events(
        event_root,
        [
            {"type": "provider.turn.completed", "payload": {"provider_turn_id": "turn-1"}},
            {"type": "action.parsed", "payload": {"action_id": "step-0001", "action": "write_file", "batch_id": "batch-0001", "protocol": "agent-action-batch-v1"}},
            {"type": "workspace.mutation.recorded", "payload": {"path": "work/output.txt", "after_hash": "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}},
            {"type": "result.submitted", "payload": {"produced_paths": ["work/output.txt"], "evidence_refs": []}},
            {"type": "run.completed", "payload": {}},
        ],
    )

    with pytest.raises(ValueError, match="command evidence is required"):
        AtomicAgentResultValidator(
            allowed_write_set=("work/",),
            declared_command_ids=("check",),
            event_stream_root=event_root,
        ).validate(result)
```

and:

```python
def test_atomic_result_validator_rejects_checkpoint_command_not_declared(tmp_path: Path) -> None:
    event_root = tmp_path / "events"
    result = _agent_result_with_events(
        event_root,
        [
            {"type": "provider.turn.completed", "payload": {"provider_turn_id": "turn-1"}},
            {"type": "workspace.mutation.recorded", "payload": {"path": "work/output.txt", "after_hash": "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}},
            {"type": "command.completed", "payload": {"command_id": "undeclared-check", "exit_code": 0}},
            {"type": "result.submitted", "payload": {"produced_paths": ["work/output.txt"], "evidence_refs": ["undeclared-check"]}},
            {"type": "run.completed", "payload": {}},
        ],
    )

    with pytest.raises(ValueError, match="undeclared command"):
        AtomicAgentResultValidator(
            allowed_write_set=("work/",),
            declared_command_ids=("check",),
            event_stream_root=event_root,
        ).validate(result)
```

- [ ] **Step 3: Implement validator changes**

Ensure `AtomicAgentResultValidator` does not reject `action.parsed` payloads with `batch_id` and `protocol` as long as canonical event verification passes. Keep existing checks:

- event stream hash matches;
- workspace mutation path stays under allowed write set;
- command id is declared;
- result-side summary matches event stream summary;
- source lineage input remains required by projector/executor.

- [ ] **Step 4: Run targeted tests**

```bash
PYTHONPATH=src:. python -m pytest tests/execution/test_atomic_agent_executor.py tests/negative/test_atomic_agent_executor_fail_closed.py -q --tb=short
```

Expected: pass.

---

## Task 7: V2-090J medium proving runner and tests

**Files:**
- Create: `scripts/run_v2_090j_medium_scenario.py`
- Create: `tests/proving/test_v2_090j_medium_scenario_script.py`
- Create: `tests/proving/test_v2_090j_medium_scenario.py`
- Modify: `scripts/README.md`

- [ ] **Step 1: Copy V2-090I runner as baseline**

Create `scripts/run_v2_090j_medium_scenario.py` from `scripts/run_v2_090i_medium_scenario.py`, then update constants:

```python
MEDIUM_SCENARIO_MARKER = {"scenario": "v2-090j-medium", "version": 1}
MEDIUM_SCENARIO_TICKET_REF = "ticket.medium.forecast-engine.protocol-repair"
MEDIUM_SCENARIO_COMMAND_ID = "cmd.check-medium-scenario"
```

Use workspace:

```text
.evidence/atomic-agent/v2-090j-medium-scenario-workspace/
```

- [ ] **Step 2: Update objective to allow explicit batch protocol**

In the V2-090J objective/constraints, replace “Every provider response must be exactly one valid JSON object representing one action” with:

```text
Provider responses may be either one AgentAction JSON object or one AgentActionBatch JSON object with protocol "agent-action-batch-v1". Do not output Markdown, code fences, concatenated JSON objects, bare arrays, or action_envelope.
```

Keep command evidence and produced paths requirements unchanged.

- [ ] **Step 3: Add non-provider tests**

Create `tests/proving/test_v2_090j_medium_scenario_script.py` mirroring V2-090I tests and add assertions:

```python
def test_v2_090j_execution_package_requests_batch_protocol_and_checkpoint(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    settings = load_boardroom_settings(_write_config_files(tmp_path), env_values={})
    package = _execution_package(settings)

    assert "agent-action-batch-v1" in package.objective
    assert package.commands[0].command_id.value == "cmd.check-medium-scenario"
    assert {output.value for output in package.required_outputs} == set(REQUIRED_OUTPUT_PATHS)
```

Add a separate assertion that the V2-090J runner refuses to proceed if batch budget is not enabled:

```python
def test_v2_090j_settings_require_batch_budget(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    settings = load_boardroom_settings(_write_config_files(tmp_path, max_actions_per_turn=1), env_values={})

    with pytest.raises(ValueError, match="max_actions_per_turn must be greater than 1"):
        _settings_with_v2_090j_budget(settings)
```

Also assert checkpoint retry count is read from settings:

```python
def test_v2_090j_checkpoint_max_auto_runs_comes_from_settings(tmp_path: Path) -> None:
    settings = load_boardroom_settings(_write_config_files(tmp_path, checkpoint_max_auto_runs=3), env_values={})
    invocation = _compile_invocation(settings)

    assert invocation.output_requirements["required_output_checkpoint"]["max_auto_runs"] == 3
```

and:

```python
def test_v2_090j_report_success_requires_checkpoint_command_evidence() -> None:
    report = _build_report(
        run_id="boardroom-atomic.v2-090j.medium.test",
        provider_transport_kind="real",
        event_summary={
            "terminal_event_type": "run.completed",
            "command_exit_codes": {},
            "workspace_mutation_paths": ["work/forecast_engine/statistics.py"],
            "source_lineage_inputs": ["work/forecast_engine/statistics.py"],
        },
    )
    assert report["success"] is False
```

- [ ] **Step 4: Add real provider proving test**

Create `tests/proving/test_v2_090j_medium_scenario.py`:

```python
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
    assert report["provider_transport_kind"] == "real"
    assert report["terminal_event_type"] == "run.completed"
    assert report["command_exit_codes"]["cmd.check-medium-scenario"] == 0
    assert report["workspace_mutation_paths"]
    assert report["source_lineage_inputs"]
    assert report["success"] is True
```

- [ ] **Step 5: Run non-provider V2-090J tests**

```bash
PYTHONPATH=src:. python -m pytest tests/proving/test_v2_090j_medium_scenario_script.py tests/proving/test_v2_090j_medium_scenario.py -q --tb=short --basetemp .pytest-tmp-v2090j-non-provider
```

Expected: non-provider tests pass, real provider test skipped without opt-in.

---

## Task 8: Documentation and status updates

**Files:**
- Modify: `doc/04-implementation/backlog.md`
- Modify: `doc/04-implementation/acceptance-criteria.md`
- Modify: `doc/05-project-log/2026-06.md`
- Modify: `scripts/README.md`
- Modify: `doc/05-project-log/v2-090i-implementation-run-record.md`

- [ ] **Step 1: Add V2-090J backlog entry**

Add a new work package after V2-090I:

```markdown
### V2-090J: Atomic action protocol repair（原子动作协议修复）

- 状态：TODO（计划已形成，尚未实施）
- 目标：修复 V2-090I 暴露的 action protocol（动作协议）、tool policy（工具策略）和 validator checkpoint（验证命令检查点）问题，并用中等复杂真实 provider proving test 复验。
- 输入文档：`docs/superpowers/specs/2026-06-11-v2-090j-atomic-action-protocol-repair-design.md`、`docs/superpowers/plans/2026-06-11-v2-090j-atomic-action-protocol-repair.md`、`doc/05-project-log/v2-090i-implementation-run-record.md`、atomic-agent action protocol docs。
- 依赖：V2-090H、V2-090I 阻塞证据、atomic-agent batch/checkpoint 修复。
- 输出文件：`scripts/run_v2_090j_medium_scenario.py`、`tests/proving/test_v2_090j_medium_scenario_script.py`、`tests/proving/test_v2_090j_medium_scenario.py`、相关 atomic-agent 改动。
- 验收口径：真实 provider-backed executor 完成 medium package/CLI，产生 command evidence、workspace mutation、source lineage input；V2-090F 仍不自动解阻。
```

Update Phase 9 counts from `7 / 9` to `7 / 10` until V2-090J is done.

- [ ] **Step 2: Add acceptance checkbox**

In `acceptance-criteria.md`, add:

```markdown
- [ ] V2-090J：atomic-agent action protocol repair（原子动作协议修复）后，真实 provider-backed executor 可通过 batch/structured action（批量/结构化动作）或等价结构化协议完成中等复杂多文件任务，并保留 command evidence / workspace mutation / source lineage 硬门禁
```

- [ ] **Step 3: Update scripts README**

Document the V2-090J runner and opt-in command:

```bash
set -a; source .env; set +a; BOARDROOM_RUN_REAL_PROVIDER_PROVING=1 PYTHONPATH=src:. python -m pytest tests/proving/test_v2_090j_medium_scenario.py -q --tb=short --basetemp .pytest-tmp-v2090j-medium-real
```

- [ ] **Step 4: Update project log**

Add a `2026-06-11 — V2-090J Atomic action protocol repair 立项` entry summarizing root cause and the plan.

- [ ] **Step 5: Run doc checks**

```bash
git diff --check
rg -n "V2-090J|090J" doc scripts tests docs/superpowers
```

Expected: `git diff --check` passes; `rg` shows the spec/plan/docs/tests references.

---

## Task 9: Final verification and real provider gate

**Files:** all touched files

- [ ] **Step 1: Run atomic-agent targeted verification**

```bash
cd /Users/bill/projects/atomic-agent
python -m pytest tests/test_action_parser.py tests/test_agent_loop.py tests/test_evidence.py tests/test_runtime_port.py -q --tb=short
```

Expected: all pass.

- [ ] **Step 2: Run Boardroom targeted verification**

```bash
cd /Users/bill/projects/boardroom-os/.worktrees/v2-090i-medium-scenario
PYTHONPATH=src:. python -m pytest tests/config/test_boardroom_config.py tests/negative/test_boardroom_config_fail_closed.py tests/execution/test_atomic_agent_invocation_compiler.py tests/execution/test_atomic_agent_executor.py tests/negative/test_atomic_agent_executor_fail_closed.py tests/proving/test_v2_090j_medium_scenario_script.py tests/proving/test_v2_090j_medium_scenario.py -q --tb=short --basetemp .pytest-tmp-v2090j-targeted
```

Expected: non-provider tests pass; real provider test skipped unless opt-in env is set.

- [ ] **Step 3: Run real provider V2-090J gate**

```bash
cd /Users/bill/projects/boardroom-os/.worktrees/v2-090i-medium-scenario
set -a; source /Users/bill/projects/boardroom-os/.env; set +a; BOARDROOM_RUN_REAL_PROVIDER_PROVING=1 PYTHONPATH=src:. python -m pytest tests/proving/test_v2_090j_medium_scenario.py -q --tb=short --basetemp .pytest-tmp-v2090j-medium-real
```

Expected: `1 passed`, JSON report shows `success=true`, `terminal_event_type=run.completed`, `cmd.check-medium-scenario=0`, workspace mutation paths non-empty, and source lineage inputs non-empty.

- [ ] **Step 4: Run diff checks**

```bash
cd /Users/bill/projects/boardroom-os/.worktrees/v2-090i-medium-scenario
git diff --check
cd /Users/bill/projects/atomic-agent
git diff --check
```

Expected: both pass.

- [ ] **Step 5: Status decision**

If Step 3 passes, update Boardroom docs to mark V2-090J `DONE` and record that V2-090I root cause is covered by the repair evidence. Keep V2-090I and V2-090F status changes pending explicit human review. If Step 3 fails, keep V2-090J `BLOCKED` and record event stream evidence without weakening gates.

---

## Self-Review

Spec coverage:

- Root cause summary maps to Tasks 1-3 and Task 5.
- Evidence gate preservation maps to Tasks 6, 7, and 9.
- Documentation/status requirements map to Task 8.
- Real provider proving maps to Task 9.

Placeholder scan:

- No TODO/TBD placeholders remain.
- Every task has exact files, commands, and expected outcomes.

Type consistency:

- `AgentActionBatch`、`ParsedAgentTurn`、`max_actions_per_turn`、`required_output_checkpoint` are introduced before use in later tasks.
- Boardroom metadata names match the spec: `action_protocol`, `required_output_checkpoint`, `max_actions_per_turn`.

Execution choice after plan approval:

1. Subagent-Driven（推荐）：按任务拆分 atomic-agent 与 Boardroom 改动，每个任务单独 review。
2. Inline Execution：本会话按 executing-plans（执行计划）逐项实现。
