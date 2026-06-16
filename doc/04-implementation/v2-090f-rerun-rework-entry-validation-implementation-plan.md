# V2-090F Rerun Rework-Entry Validation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development（子智能体驱动开发，推荐）or superpowers:executing-plans（按计划执行）to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 按已通过的 V2-090F rerun rework-entry validation spec（重跑返工入口验证规格）执行真实 V2-090F full rerun（完整重跑），在无阻断时产出 closeout candidate（收尾候选），在有阻断时投影为 ReworkRequest（返工请求）、调用 V2-100 rework loop（返工循环）并导出 TicketGraph（工单图）更新前后证据。

**Architecture:** 先做 observation run（观察重跑），不提前改写 V2-090F 编排；新增的 `v2_090f_rework_entry.py`（V2-090F 返工入口验证模块）只读取现有 V2-090F artifacts（产物）、导出 graph snapshot（图快照）、把结构化 gate blocker（门禁阻断项）投影到既有 Rework model（返工模型），再调用 V2-100 API（接口）。若真实输出只剩 raw exception（原始异常）或 free text（自由文本），结果必须是 `blocked_by_missing_rework_entry`，只有拿到该观察证据后才补最小 gate-failure adapter（门禁失败适配器），不得复制 EvidenceVerifier（证据验证器）、Checker（检查者）或 CloseoutGate（收尾门禁）。

**Tech Stack:** Python 3.11+、Pydantic v2、pytest、现有 `boardroom_os.proving.v2_090f_prd_agent_team`（V2-090F PRD 到智能体团队证明模块）、`boardroom_os.rework.*`（返工模型/投影/归约器）、`boardroom_os.proving.v2_100_rework_loop`（V2-100 返工循环证明模块）、Mermaid graph（Mermaid 图）、真实 provider opt-in（模型供应商显式启用）。

---

## Scope And Review Boundary

本计划只写入实施步骤，实施前必须再次评审。执行本计划时：

- 不修改 `backend/app/core/*` 旧 runtime（旧运行时）。
- 不把 `AgentRunResult.status == completed`（原子智能体运行完成）映射为 `TICKET_COMPLETED`（任务完成）。
- 不把 V2-100E resettable fixture（可重置夹具）伪装成 V2-090F golden sample（黄金样例）。
- 不在真实 observation run（观察重跑）前新增大规模 orchestration glue（编排胶水）。
- 不自动修改 `backlog.md` 中 V2-090F 状态，不勾选 Phase 9 V2-090F checkbox。

## File Structure

Create:

- `src/boardroom_os/proving/v2_090f_rework_entry.py` — V2-090F rework-entry validation（返工入口验证）薄层：result models（结果模型）、TicketGraph snapshot（工单图快照）、Mermaid export（Mermaid 导出）、structured blocker projection（结构化阻断投影）、V2-100 continuation（继续返工）调用和 audit report（审计报告）导出。
- `tests/proving/test_v2_090f_rework_entry_validation.py` — 正向路径：无阻断 closeout candidate、结构化 blocker 进入 V2-100、before/after graph 导出。
- `tests/negative/test_v2_090f_rework_entry_fail_closed.py` — 负例：无 verified blocker（已验证阻断项）不得创建 ReworkRequest、raw exception 不得伪装为返工请求、after graph 版本不增加失败、缺 TicketGraphPatch ref（工单图补丁引用）失败。

Modify:

- `src/boardroom_os/proving/v2_100_rework_loop.py` — 只允许最小暴露 `run_v2_100_rework_loop_for_request()`（从已验证 ReworkRequest 启动返工循环的包装函数），通过复用现有 round provider（轮次供应器）、reducer（归约器）、evidence recheck（证据重验）和 audit export（审计导出）实现；不得新增第二套 V2-100 返工逻辑。
- `scripts/run_v2_090f_prd_agent_team.py` — 增加 `--stage rework-entry`，先执行现有 full stage（完整阶段），再调用 `run_v2_090f_rework_entry_validation()`（返工入口验证函数）；真实 provider opt-in 仍由 `BOARDROOM_RUN_REAL_PROVIDER_PROVING=1` 控制。
- `src/boardroom_os/proving/__init__.py` — 导出 V2-090F rework-entry validation public API（公开接口）。
- `tests/proving/test_v2_090f_prd_agent_team_script.py` — CLI（命令行入口）非 provider 单元测试，覆盖 `rework-entry` stage 的调用顺序和 exit code（退出码）。
- `tests/proving/test_v2_090f_prd_agent_team_real.py` — 真实 provider opt-in 测试，单独验证 rerun rework-entry validation（重跑返工入口验证）产物存在。
- `tests/proving/test_v2_100_rework_loop.py` — 增加 V2-100 request-start wrapper（从请求启动包装函数）测试，证明已验证 ReworkRequest 可绕过 090K snapshot loader（失败快照装载器）进入同一 V2-100 循环。
- `doc/04-implementation/INDEX.md` — 登记本实施计划和后续计划文件。
- `doc/04-implementation/backlog.md` — 将本实施计划加入 V2-090F 输入文档与当前阻塞说明，状态保持 `BLOCKED`。
- `doc/05-project-log/2026-06.md` — 记录“计划写入，等待评审”，不记录实现完成。

Completion-only modify after implementation and real verification:

- `doc/04-implementation/backlog.md` — 只有复判通过并经评审确认后，才可改 V2-090F 状态。
- `doc/04-implementation/acceptance-criteria.md` — 只有复判通过并经评审确认后，才可勾选 Phase 9 V2-090F。
- `doc/05-project-log/2026-06.md` — 只有真实 rerun 完成后，才追加 run id（运行编号）、audit export path（审计导出路径）和验证命令。

## Target Public API

`src/boardroom_os/proving/v2_090f_rework_entry.py` must expose:

```python
from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class V2_090FReworkEntryStatus(StrEnum):
    PASSED_WITHOUT_REWORK_CANDIDATE = "passed_without_rework_candidate"
    REWORK_ACCEPTED_CANDIDATE = "rework_accepted_candidate"
    REWORK_ESCALATED_OR_EXHAUSTED = "rework_escalated_or_exhausted"
    BLOCKED_BY_MISSING_REWORK_ENTRY = "blocked_by_missing_rework_entry"


class V2_090FTicketGraphNodeSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    ticket_id: str
    owner_seat_ref: str
    status: str
    acceptance_ref_count: int = Field(ge=0)
    evidence_obligation_count: int = Field(ge=0)


class V2_090FTicketGraphSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    graph_version: int = Field(gt=0)
    source_ref: str
    nodes: tuple[V2_090FTicketGraphNodeSnapshot, ...]
    edges: tuple[tuple[str, str], ...] = ()
    ticket_graph_patch_ref: str | None = None


class V2_090FReworkEntryValidationInput(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    output_root: Path
    workspace_root: Path
    run_id: str
    cycle_id: str
    max_rounds: int = Field(gt=0)
    require_real_provider: bool = True


class V2_090FReworkEntryValidationResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: V2_090FReworkEntryStatus
    before_graph_json_path: Path
    before_graph_mermaid_path: Path
    after_graph_json_path: Path | None = None
    after_graph_mermaid_path: Path | None = None
    blocker_report_path: Path
    rework_request_path: Path | None = None
    rework_plan_path: Path | None = None
    ticket_graph_patch_path: Path | None = None
    terminal_path: Path
    report_path: Path
    checked_refs: tuple[str, ...]
```

Required functions:

```python
def load_v2_090f_ticket_graph_snapshot(output_root: Path) -> V2_090FTicketGraphSnapshot:
    """Read 00-boardroom/generated-ticket-graph.json and return a normalized before-rework snapshot."""


def render_v2_090f_ticket_graph_mermaid(snapshot: V2_090FTicketGraphSnapshot) -> str:
    """Render graph TD with ticket id, owner seat, status, acceptance count, and evidence count."""


def run_v2_090f_rework_entry_validation(
    validation_input: V2_090FReworkEntryValidationInput,
) -> V2_090FReworkEntryValidationResult:
    """Validate closeout or structured blocker output, call V2-100 when a ReworkRequest exists, and export audit files."""
```

## Task 0: Pre-Implementation Drift And Observation Checkpoint

**Files:**

- Read: `doc/04-implementation/v2-090f-rerun-rework-entry-validation-spec.md`
- Read: `src/boardroom_os/proving/v2_090f_prd_agent_team.py`
- Read: `src/boardroom_os/proving/v2_100_rework_loop.py`
- Read: `src/boardroom_os/rework/blocker_projection.py`
- No code edit in this task

- [ ] **Step 1: Confirm worktree state before implementation**

Run:

```bash
git status --short --branch
```

Expected: existing dirty files may exist, but no implementation file for `v2_090f_rework_entry.py` should be present unless a previous reviewed attempt exists.

- [ ] **Step 2: Run the current V2-090F full stage as observation only**

Run only after reviewer confirms provider cost and secrets are available:

```bash
BOARDROOM_RUN_REAL_PROVIDER_PROVING=1 PYTHONPATH=src:. \
python scripts/run_v2_090f_prd_agent_team.py \
  --prd examples/directives/tiny-fullstack-prd.md \
  --reset \
  --stage full
```

Expected classification:

- exit 0 with `closeout_gate_passed` means the next implementation must preserve that as `passed_without_rework_candidate`;
- non-zero with structured `20-evidence/closeout/closeout-gate-result.json`, `20-evidence/closeout/final-evidence-table.json`, or `30-audit/checker-verdict.json` means the next implementation must project the existing blocker to ReworkRequest;
- non-zero with only raw exception/free text means the result is `blocked_by_missing_rework_entry` until a minimal adapter is reviewed.

- [ ] **Step 3: Record observation without changing V2-090F status**

Create a local review note under ignored evidence root, not committed unless reviewer asks:

```bash
mkdir -p .tmp/v2-090f-rework-entry-observation
```

Expected: no `backlog.md` status change, no Phase 9 checkbox change.

## Task 1: TicketGraph Snapshot And Mermaid Export

**Files:**

- Create: `src/boardroom_os/proving/v2_090f_rework_entry.py`
- Create: `tests/proving/test_v2_090f_rework_entry_validation.py`
- Test: `tests/proving/test_v2_090f_rework_entry_validation.py::test_ticket_graph_snapshot_exports_required_labels`

- [ ] **Step 1: Write the failing graph snapshot test**

Add this test:

```python
import json

from boardroom_os.proving.v2_090f_rework_entry import (
    load_v2_090f_ticket_graph_snapshot,
    render_v2_090f_ticket_graph_mermaid,
)


def test_ticket_graph_snapshot_exports_required_labels(tmp_path):
    output_root = tmp_path / "tiny-fullstack"
    boardroom_root = output_root / "00-boardroom"
    boardroom_root.mkdir(parents=True)
    (boardroom_root / "generated-ticket-graph.json").write_text(
        json.dumps(
            {
                "provider_output": {
                    "artifact_name": "ticket-graph",
                    "ticket_graph": {
                        "graph_version": 7,
                        "nodes": [
                            {
                                "node_ref": "ticket.worker.implementation",
                                "owner_seat_ref": "seat.worker.implementation",
                                "status": "blocked",
                                "acceptance_refs": ["AC-1", "AC-2"],
                                "evidence_obligations": ["evidence.source"],
                                "depends_on": ["ticket.architect.plan"],
                            }
                        ],
                    },
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    snapshot = load_v2_090f_ticket_graph_snapshot(output_root)
    mermaid = render_v2_090f_ticket_graph_mermaid(snapshot)

    assert snapshot.graph_version == 7
    assert snapshot.nodes[0].ticket_id == "ticket.worker.implementation"
    assert snapshot.nodes[0].acceptance_ref_count == 2
    assert snapshot.nodes[0].evidence_obligation_count == 1
    assert '"ticket.worker.implementation\\nseat.worker.implementation\\nblocked\\nAC:2 EV:1"' in mermaid
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
PYTHONPATH=src:. python -m pytest \
  tests/proving/test_v2_090f_rework_entry_validation.py::test_ticket_graph_snapshot_exports_required_labels \
  -q
```

Expected: FAIL with `ModuleNotFoundError` or missing function.

- [ ] **Step 3: Implement minimal graph snapshot helpers**

Create `src/boardroom_os/proving/v2_090f_rework_entry.py` with the public models from the API section and these helper behaviors:

```python
def _node_ref(node: dict[str, Any]) -> str:
    value = node.get("node_ref") or node.get("ticket_id")
    if not isinstance(value, str) or not value.strip():
        raise ValueError("ticket graph node requires node_ref or ticket_id")
    return value.strip()


def _node_status(node: dict[str, Any]) -> str:
    value = node.get("status", "unknown")
    if not isinstance(value, str) or not value.strip():
        raise ValueError("ticket graph node status must be text")
    return value.strip()


def _count_list_field(node: dict[str, Any], field_name: str) -> int:
    value = node.get(field_name)
    if value is None:
        return 0
    if not isinstance(value, list):
        raise ValueError(f"ticket graph {field_name} must be a list")
    return len(value)
```

The implementation must reject empty graph nodes and must not infer acceptance refs or evidence obligations from hardcoded ticket names.

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
PYTHONPATH=src:. python -m pytest \
  tests/proving/test_v2_090f_rework_entry_validation.py::test_ticket_graph_snapshot_exports_required_labels \
  -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/boardroom_os/proving/v2_090f_rework_entry.py tests/proving/test_v2_090f_rework_entry_validation.py
git commit -m "feat(v2-090f): 增加工单图快照导出"
```

## Task 2: Rework-Entry Result Model And Fail-Closed Validation

**Files:**

- Modify: `src/boardroom_os/proving/v2_090f_rework_entry.py`
- Create: `tests/negative/test_v2_090f_rework_entry_fail_closed.py`
- Test: `tests/negative/test_v2_090f_rework_entry_fail_closed.py::test_rework_entry_rejects_after_graph_without_patch_ref`

- [ ] **Step 1: Write failing validation tests**

Add:

```python
import pytest

from boardroom_os.proving.v2_090f_rework_entry import V2_090FTicketGraphSnapshot


def test_rework_entry_rejects_after_graph_without_patch_ref():
    with pytest.raises(ValueError, match="ticket_graph_patch_ref"):
        V2_090FTicketGraphSnapshot(
            graph_version=9,
            source_ref="00-boardroom/ticket-graph.after-rework.json",
            nodes=(
                {
                    "ticket_id": "ticket.rework.response-shape",
                    "owner_seat_ref": "seat.worker.implementation",
                    "status": "ready",
                    "acceptance_ref_count": 1,
                    "evidence_obligation_count": 1,
                },
            ),
            ticket_graph_patch_ref=None,
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
PYTHONPATH=src:. python -m pytest \
  tests/negative/test_v2_090f_rework_entry_fail_closed.py::test_rework_entry_rejects_after_graph_without_patch_ref \
  -q
```

Expected: FAIL because the model does not yet enforce after graph patch binding.

- [ ] **Step 3: Implement model validation**

Add a `model_validator` to `V2_090FTicketGraphSnapshot`:

```python
from pydantic import model_validator


@model_validator(mode="after")
def _validate_patch_binding(self):
    if "after-rework" in self.source_ref and not self.ticket_graph_patch_ref:
        raise ValueError("after-rework graph requires ticket_graph_patch_ref")
    if not self.nodes:
        raise ValueError("ticket graph snapshot nodes must not be empty")
    return self
```

Also add validation that `V2_090FReworkEntryValidationResult.status == REWORK_ACCEPTED_CANDIDATE` requires `after_graph_json_path`, `after_graph_mermaid_path`, `rework_request_path`, `rework_plan_path`, and `ticket_graph_patch_path`.

- [ ] **Step 4: Run negative tests**

Run:

```bash
PYTHONPATH=src:. python -m pytest \
  tests/negative/test_v2_090f_rework_entry_fail_closed.py \
  -q
```

Expected: PASS for the new negative model tests.

- [ ] **Step 5: Commit**

```bash
git add src/boardroom_os/proving/v2_090f_rework_entry.py tests/negative/test_v2_090f_rework_entry_fail_closed.py
git commit -m "test(v2-090f): 锁定返工入口失败关闭"
```

## Task 3: No-Blocker Closeout Candidate Path

**Files:**

- Modify: `src/boardroom_os/proving/v2_090f_rework_entry.py`
- Modify: `tests/proving/test_v2_090f_rework_entry_validation.py`
- Test: `tests/proving/test_v2_090f_rework_entry_validation.py::test_passed_closeout_writes_no_blocker_candidate_report`

- [ ] **Step 1: Write failing no-blocker test**

Add:

```python
import json

from boardroom_os.proving.v2_090f_rework_entry import (
    V2_090FReworkEntryStatus,
    V2_090FReworkEntryValidationInput,
    run_v2_090f_rework_entry_validation,
)


def test_passed_closeout_writes_no_blocker_candidate_report(tmp_path):
    output_root = tmp_path / "tiny-fullstack"
    workspace_root = tmp_path / "workspace"
    (output_root / "00-boardroom").mkdir(parents=True)
    (output_root / "20-evidence/closeout").mkdir(parents=True)
    (output_root / "00-boardroom/generated-ticket-graph.json").write_text(
        json.dumps(
            {
                "provider_output": {
                    "artifact_name": "ticket-graph",
                    "ticket_graph": {
                        "graph_version": 3,
                        "nodes": [
                            {
                                "node_ref": "ticket.worker.implementation",
                                "owner_seat_ref": "seat.worker.implementation",
                                "status": "completed",
                                "acceptance_refs": ["AC-1"],
                                "evidence_obligations": ["evidence.source"],
                            }
                        ],
                    },
                }
            }
        ),
        encoding="utf-8",
    )
    (output_root / "20-evidence/closeout/closeout-gate-result.json").write_text(
        json.dumps(
            {
                "closeout_gate_result_id": "closeout-gate-result.v2-090f.generated",
                "verdict": "passed",
                "blockers": [],
                "checked_refs": ["source-inventory.v2-090f.generated"],
            }
        ),
        encoding="utf-8",
    )
    (output_root / "closeout-package.json").write_text(
        json.dumps({"closeout_package_id": "closeout-package.v2-090f.generated", "verdict": "passed"}),
        encoding="utf-8",
    )

    result = run_v2_090f_rework_entry_validation(
        V2_090FReworkEntryValidationInput(
            output_root=output_root,
            workspace_root=workspace_root,
            run_id="run.v2-090f.test",
            cycle_id="rework-cycle.v2-090f.test",
            max_rounds=1,
            require_real_provider=False,
        )
    )

    assert result.status is V2_090FReworkEntryStatus.PASSED_WITHOUT_REWORK_CANDIDATE
    assert result.before_graph_json_path.is_file()
    assert result.before_graph_mermaid_path.is_file()
    assert result.after_graph_json_path is None
    assert result.rework_request_path is None
    assert "passed_without_rework_candidate" in result.report_path.read_text(encoding="utf-8")
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
PYTHONPATH=src:. python -m pytest \
  tests/proving/test_v2_090f_rework_entry_validation.py::test_passed_closeout_writes_no_blocker_candidate_report \
  -q
```

Expected: FAIL because `run_v2_090f_rework_entry_validation` has not exported candidate artifacts.

- [ ] **Step 3: Implement no-blocker export**

Implement:

- write `00-boardroom/ticket-graph.before-rework.json`;
- write `00-boardroom/ticket-graph.before-rework.md`;
- write `20-evidence/rework-entry/blocker-report.json` with `{"blockers": [], "status": "no_verified_blocker"}`;
- write `20-evidence/rework-entry/rework-terminal.json` with `terminal_status="passed_without_rework_candidate"`;
- write `30-audit/rework-entry-validation.md` explaining no ReworkRequest was created because CloseoutGate passed.

The implementation must require `closeout-package.json` and closeout gate verdict `passed` for this path.

- [ ] **Step 4: Run focused test**

Run:

```bash
PYTHONPATH=src:. python -m pytest \
  tests/proving/test_v2_090f_rework_entry_validation.py::test_passed_closeout_writes_no_blocker_candidate_report \
  -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/boardroom_os/proving/v2_090f_rework_entry.py tests/proving/test_v2_090f_rework_entry_validation.py
git commit -m "feat(v2-090f): 导出无阻断收尾候选"
```

## Task 4: Structured Blocker Projection Or Missing-Entry Terminal

**Files:**

- Modify: `src/boardroom_os/proving/v2_090f_rework_entry.py`
- Modify: `tests/proving/test_v2_090f_rework_entry_validation.py`
- Modify: `tests/negative/test_v2_090f_rework_entry_fail_closed.py`
- Test: `tests/proving/test_v2_090f_rework_entry_validation.py::test_closeout_gate_blocker_projects_to_rework_request`

- [ ] **Step 1: Write failing structured blocker test**

Add these local helpers and a test that writes a structured closeout blocker and asserts a ReworkRequest is exported:

```python
def _write_generated_graph(tmp_path, *, graph_version: int, status: str):
    output_root = tmp_path / "tiny-fullstack"
    boardroom_root = output_root / "00-boardroom"
    boardroom_root.mkdir(parents=True, exist_ok=True)
    (boardroom_root / "generated-ticket-graph.json").write_text(
        json.dumps(
            {
                "provider_output": {
                    "artifact_name": "ticket-graph",
                    "ticket_graph": {
                        "graph_version": graph_version,
                        "nodes": [
                            {
                                "node_ref": "ticket.worker.implementation",
                                "owner_seat_ref": "seat.worker.implementation",
                                "status": status,
                                "acceptance_refs": ["AC-AGENT-DECLARED-LIBRARY"],
                                "source_surface_refs": ["surface.agent-service"],
                                "evidence_obligations": ["evidence.live-blackbox"],
                                "depends_on": ["ticket.architect.plan"],
                            }
                        ],
                    },
                }
            }
        ),
        encoding="utf-8",
    )
    (boardroom_root / "generated-contracts.json").write_text(
        json.dumps(
            {
                "acceptance_contract": {
                    "criteria": [
                        {
                            "acceptance_ref": "AC-AGENT-DECLARED-LIBRARY",
                            "blocking": True,
                            "evidence_required": ["live_blackbox"],
                            "source_surface_refs": ["surface.agent-service"],
                        }
                    ]
                },
                "package_contract": {
                    "package_contract_id": "package-contract.agent",
                    "source_surfaces": [
                        {
                            "source_surface_ref": "surface.agent-service",
                            "acceptance_refs": ["AC-AGENT-DECLARED-LIBRARY"],
                        }
                    ],
                },
                "evidence_obligations": [
                    {
                        "evidence_obligation_id": "evidence.live-blackbox",
                        "acceptance_refs": ["AC-AGENT-DECLARED-LIBRARY"],
                        "required_artifact_type": "live_blackbox",
                        "blocking": True,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return output_root


def _write_closeout_gate_result(output_root, *, verdict: str, blockers: list[dict[str, str]]):
    closeout_root = output_root / "20-evidence/closeout"
    closeout_root.mkdir(parents=True, exist_ok=True)
    (closeout_root / "closeout-gate-result.json").write_text(
        json.dumps(
            {
                "version": 1,
                "closeout_gate_result_id": {"value": "closeout-gate-result.v2-090f.generated"},
                "verdict": verdict,
                "blockers": blockers,
                "checked_refs": ["source-inventory.v2-090f.generated"],
            }
        ),
        encoding="utf-8",
    )


def test_closeout_gate_blocker_projects_to_rework_request(tmp_path):
    output_root = _write_generated_graph(tmp_path, graph_version=4, status="blocked")
    workspace_root = tmp_path / "workspace"
    _write_closeout_gate_result(
        output_root,
        verdict="blocked",
        blockers=[
            {
                "code": "command_evidence_not_final",
                "message": "service/live evidence missing",
                "related_ref": "cmd.agent-service",
            }
        ],
    )

    result = run_v2_090f_rework_entry_validation(
        V2_090FReworkEntryValidationInput(
            output_root=output_root,
            workspace_root=workspace_root,
            run_id="run.v2-090f.blocked",
            cycle_id="rework-cycle.v2-090f.blocked",
            max_rounds=1,
            require_real_provider=False,
        )
    )

    request = json.loads(result.rework_request_path.read_text(encoding="utf-8"))
    assert result.rework_request_path.is_file()
    assert request["rework_request_id"]["value"].startswith("rework-request.closeout.")
    assert request["issues"][0]["blocker_refs"]
```

- [ ] **Step 2: Write failing raw-exception negative test**

Add:

```python
def test_raw_exception_does_not_create_rework_request(tmp_path):
    output_root = _write_generated_graph(tmp_path, graph_version=4, status="blocked")
    workspace_root = tmp_path / "workspace"
    (output_root / "30-audit").mkdir(parents=True)
    (output_root / "30-audit/raw-closeout-error.txt").write_text(
        "ValueError: live blackbox evidence is required before closeout",
        encoding="utf-8",
    )

    result = run_v2_090f_rework_entry_validation(
        V2_090FReworkEntryValidationInput(
            output_root=output_root,
            workspace_root=workspace_root,
            run_id="run.v2-090f.raw-error",
            cycle_id="rework-cycle.v2-090f.raw-error",
            max_rounds=1,
            require_real_provider=False,
        )
    )

    assert result.status is V2_090FReworkEntryStatus.BLOCKED_BY_MISSING_REWORK_ENTRY
    assert result.rework_request_path is None
    assert "blocked_by_missing_rework_entry" in result.terminal_path.read_text(encoding="utf-8")
```

- [ ] **Step 3: Run tests to verify they fail**

Run:

```bash
PYTHONPATH=src:. python -m pytest \
  tests/proving/test_v2_090f_rework_entry_validation.py::test_closeout_gate_blocker_projects_to_rework_request \
  tests/negative/test_v2_090f_rework_entry_fail_closed.py::test_raw_exception_does_not_create_rework_request \
  -q
```

Expected: FAIL until projection and missing-entry terminal are implemented.

- [ ] **Step 4: Implement projection using existing rework APIs**

Use existing `project_closeout_gate_blockers()`（收尾门禁阻断投影函数） from `boardroom_os.rework.blocker_projection` and typed `BlockerProjectionContext`（阻断投影上下文）. Do not create a second ReworkRequest schema.

Required context values for V2-090F:

```python
active_acceptance_refs = tuple(AcceptanceRef(value=value) for value in _load_active_acceptance_refs(output_root))
active_source_surface_refs = tuple(SourceSurfaceRef(value=value) for value in _load_active_source_surface_refs(output_root))
active_evidence_obligation_refs = tuple(EvidenceObligationRef(value=value) for value in _load_active_evidence_obligation_refs(output_root))
```

If these refs cannot be loaded from generated contracts or evidence obligations, fail with `blocked_by_missing_rework_entry` rather than inventing static refs.

- [ ] **Step 5: Run projection tests**

Run:

```bash
PYTHONPATH=src:. python -m pytest \
  tests/proving/test_v2_090f_rework_entry_validation.py::test_closeout_gate_blocker_projects_to_rework_request \
  tests/negative/test_v2_090f_rework_entry_fail_closed.py::test_raw_exception_does_not_create_rework_request \
  -q
```

Expected: PASS.

- [ ] **Step 6: Observation review gate**

If Task 0 produced only raw exception/free text, stop after this task and ask for review before adding any adapter that changes V2-090F closeout failure emission. The reviewed adapter must only convert existing gate failure facts into typed `CloseoutGateResult` / `CheckerVerdict` / `FinalEvidenceTable` input; it must not decide closeout or synthesize evidence.

- [ ] **Step 7: Commit**

```bash
git add src/boardroom_os/proving/v2_090f_rework_entry.py tests/proving/test_v2_090f_rework_entry_validation.py tests/negative/test_v2_090f_rework_entry_fail_closed.py
git commit -m "feat(v2-090f): 投影结构化返工请求"
```

## Task 5: V2-100 Request-Start Continuation And After-Graph Export

**Files:**

- Modify: `src/boardroom_os/proving/v2_100_rework_loop.py`
- Modify: `src/boardroom_os/proving/v2_090f_rework_entry.py`
- Modify: `tests/proving/test_v2_100_rework_loop.py`
- Modify: `tests/proving/test_v2_090f_rework_entry_validation.py`
- Modify: `tests/negative/test_v2_090f_rework_entry_fail_closed.py`
- Test: `tests/proving/test_v2_100_rework_loop.py::test_v2_100_loop_can_start_from_verified_rework_request`
- Test: `tests/proving/test_v2_090f_rework_entry_validation.py::test_rework_continuation_exports_before_and_after_graph`

- [ ] **Step 1: Write failing V2-100 request-start wrapper test**

Add to `tests/proving/test_v2_100_rework_loop.py`:

```python
def test_v2_100_loop_can_start_from_verified_rework_request(tmp_path: Path) -> None:
    from boardroom_os.proving.v2_100_resettable_fixture import (
        build_two_round_provider,
        build_v2_100_scenario_input,
    )
    from boardroom_os.proving.v2_100_rework_loop import (
        project_snapshot_request,
        run_v2_100_rework_loop_for_request,
    )

    scenario_input = build_v2_100_scenario_input(
        package_root=tmp_path / "package",
        export_root=tmp_path / "audit-artifacts",
        require_real_provider=False,
        max_rounds=2,
    )
    request = project_snapshot_request(scenario_input)

    result = run_v2_100_rework_loop_for_request(
        scenario_input,
        request=request,
        round_provider=build_two_round_provider(tmp_path),
    )

    assert result.request == request
    assert result.rounds[-1].remaining_blocker_refs == ()
    assert result.final_projection.graph_version > scenario_input.initial_graph_version
```

- [ ] **Step 2: Run wrapper test to verify it fails**

Run:

```bash
PYTHONPATH=src:. python -m pytest \
  tests/proving/test_v2_100_rework_loop.py::test_v2_100_loop_can_start_from_verified_rework_request \
  -q
```

Expected: FAIL because `run_v2_100_rework_loop_for_request` is not exposed yet.

- [ ] **Step 3: Implement minimal V2-100 request-start wrapper**

In `src/boardroom_os/proving/v2_100_rework_loop.py`, factor the body of `run_v2_100_rework_loop_scenario()` after its current `request = project_snapshot_request(scenario_input)` line into:

```python
def run_v2_100_rework_loop_for_request(
    scenario_input: V2_100ScenarioInput,
    *,
    request: ReworkRequest,
    round_provider: ScenarioRoundProvider | None = None,
) -> V2_100ScenarioResult:
    scenario_input = V2_100ScenarioInput.model_validate(scenario_input)
    request = validate_scenario_request(request, scenario_input)
    return _run_v2_100_rework_loop_with_request(
        scenario_input,
        request=request,
        round_provider=round_provider,
    )
```

Then make `run_v2_100_rework_loop_scenario()` call the same private `_run_v2_100_rework_loop_with_request()` after projecting the snapshot. This is a factoring-only API extension; it must not change existing V2-100 tests or create another reducer/evidence path.

- [ ] **Step 4: Run wrapper regression**

Run:

```bash
PYTHONPATH=src:. python -m pytest \
  tests/proving/test_v2_100_rework_loop.py::test_v2_100_loop_can_start_from_verified_rework_request \
  tests/proving/test_v2_100_rework_loop.py \
  tests/negative/test_v2_100_rework_loop_fail_closed.py \
  -q
```

Expected: PASS.

- [ ] **Step 5: Write failing before/after graph test**

Add this result-double helper and a test with an injected V2-100 result that exposes the exact attributes consumed by the rework-entry adapter:

```python
from types import SimpleNamespace


def _closeout_blocker():
    return {
        "code": "command_evidence_not_final",
        "message": "service/live evidence missing",
        "related_ref": "cmd.agent-service",
    }


def _accepted_v2_100_result_with_patch(*, after_graph_version: int, patch_ref: str):
    patch = SimpleNamespace(
        ticket_graph_patch_id=SimpleNamespace(value=patch_ref),
        affected_ticket_refs=(SimpleNamespace(value="ticket.rework.response-shape"),),
        operations=(
            SimpleNamespace(
                operation_id=SimpleNamespace(value="patch-op.v2-090f.response-shape"),
                target_ticket_refs=(SimpleNamespace(value="ticket.rework.response-shape"),),
            ),
        ),
    )
    round_result = SimpleNamespace(
        patch=patch,
        plan_output=SimpleNamespace(
            plan=SimpleNamespace(
                model_dump=lambda mode="json": {"rework_plan_id": "rework-plan.v2-090f.test"}
            )
        ),
        remaining_blocker_refs=(),
        accepted_blocker_refs=(
            SimpleNamespace(value="closeout-gate-blocker.command_evidence_not_final.cmd.agent-service"),
        ),
    )
    return SimpleNamespace(
        terminal_status=SimpleNamespace(value="accepted"),
        rounds=(round_result,),
        final_projection=SimpleNamespace(graph_version=after_graph_version),
    )


def test_rework_continuation_exports_before_and_after_graph(tmp_path, monkeypatch):
    output_root = _write_generated_graph(tmp_path, graph_version=4, status="blocked")
    _write_closeout_gate_result(
        output_root,
        verdict="blocked",
        blockers=[
            {
                "code": "command_evidence_not_final",
                "message": "service/live evidence missing",
                "related_ref": "cmd.agent-service",
            }
        ],
    )
    captured = {}

    def fake_run_v2_100_rework_loop_scenario(scenario_input, round_provider=None):
        captured["scenario_input"] = scenario_input
        return _accepted_v2_100_result_with_patch(
            after_graph_version=12,
            patch_ref="ticket-graph-patch.v2-090f.response-shape",
        )

    monkeypatch.setattr(
        "boardroom_os.proving.v2_090f_rework_entry.run_v2_100_rework_loop_scenario",
        fake_run_v2_100_rework_loop_scenario,
    )

    result = run_v2_090f_rework_entry_validation(
        V2_090FReworkEntryValidationInput(
            output_root=output_root,
            workspace_root=tmp_path / "workspace",
            run_id="run.v2-090f.rework",
            cycle_id="rework-cycle.v2-090f.rework",
            max_rounds=2,
            require_real_provider=False,
        )
    )

    before_graph = json.loads(result.before_graph_json_path.read_text(encoding="utf-8"))
    after_graph = json.loads(result.after_graph_json_path.read_text(encoding="utf-8"))

    assert result.status is V2_090FReworkEntryStatus.REWORK_ACCEPTED_CANDIDATE
    assert after_graph["graph_version"] > before_graph["graph_version"]
    assert after_graph["ticket_graph_patch_ref"] == "ticket-graph-patch.v2-090f.response-shape"
    assert "ticket.rework." in result.after_graph_mermaid_path.read_text(encoding="utf-8")
```

- [ ] **Step 6: Write failing after-graph negative test**

Add:

```python
def test_rework_entry_rejects_after_graph_without_version_increase(tmp_path, monkeypatch):
    output_root = _write_generated_graph(tmp_path, graph_version=4, status="blocked")
    _write_closeout_gate_result(output_root, verdict="blocked", blockers=[_closeout_blocker()])

    monkeypatch.setattr(
        "boardroom_os.proving.v2_090f_rework_entry.run_v2_100_rework_loop_scenario",
        lambda scenario_input, round_provider=None: _accepted_v2_100_result_with_patch(
            after_graph_version=4,
            patch_ref="ticket-graph-patch.v2-090f.bad",
        ),
    )

    with pytest.raises(ValueError, match="after graph_version must be greater"):
        run_v2_090f_rework_entry_validation(
            V2_090FReworkEntryValidationInput(
                output_root=output_root,
                workspace_root=tmp_path / "workspace",
                run_id="run.v2-090f.bad-graph",
                cycle_id="rework-cycle.v2-090f.bad-graph",
                max_rounds=2,
                require_real_provider=False,
            )
        )
```

- [ ] **Step 7: Run tests to verify they fail**

Run:

```bash
PYTHONPATH=src:. python -m pytest \
  tests/proving/test_v2_090f_rework_entry_validation.py::test_rework_continuation_exports_before_and_after_graph \
  tests/negative/test_v2_090f_rework_entry_fail_closed.py::test_rework_entry_rejects_after_graph_without_version_increase \
  -q
```

Expected: FAIL until V2-100 continuation and after graph export are implemented.

- [ ] **Step 8: Implement V2-100 continuation**

Call the minimal request-start V2-100 API:

```python
from boardroom_os.proving.v2_100_rework_loop import (
    V2_100ScenarioInput,
    export_v2_100_rework_audit,
    run_v2_100_rework_loop_for_request,
)
```

The implementation must:

- pass the projected ReworkRequest directly to `run_v2_100_rework_loop_for_request()`; do not write a temporary 090K-style `failure-summary.json`;
- set `max_rounds` from `V2_090FReworkEntryValidationInput.max_rounds`;
- reject `require_real_provider=True` with any injected fake `round_provider`;
- export V2-100 audit under `20-evidence/rework-entry/v2-100-audit/`;
- write `20-evidence/rework-entry/rework-plan.json`;
- write `20-evidence/rework-entry/ticket-graph-patch.json`;
- write `00-boardroom/ticket-graph.after-rework.json`;
- write `00-boardroom/ticket-graph.after-rework.md`;
- write `20-evidence/rework-entry/rework-terminal.json`.

- [ ] **Step 9: Run before/after tests**

Run:

```bash
PYTHONPATH=src:. python -m pytest \
  tests/proving/test_v2_090f_rework_entry_validation.py::test_rework_continuation_exports_before_and_after_graph \
  tests/negative/test_v2_090f_rework_entry_fail_closed.py::test_rework_entry_rejects_after_graph_without_version_increase \
  -q
```

Expected: PASS.

- [ ] **Step 10: Commit**

```bash
git add src/boardroom_os/proving/v2_100_rework_loop.py src/boardroom_os/proving/v2_090f_rework_entry.py tests/proving/test_v2_100_rework_loop.py tests/proving/test_v2_090f_rework_entry_validation.py tests/negative/test_v2_090f_rework_entry_fail_closed.py
git commit -m "feat(v2-090f): 接入返工续跑图证据"
```

## Task 6: CLI Stage For Rework-Entry Validation

**Files:**

- Modify: `scripts/run_v2_090f_prd_agent_team.py`
- Modify: `src/boardroom_os/proving/__init__.py`
- Modify: `tests/proving/test_v2_090f_prd_agent_team_script.py`
- Test: `tests/proving/test_v2_090f_prd_agent_team_script.py::test_v2_090f_runner_rework_entry_stage_runs_full_then_validation`

- [ ] **Step 1: Write failing CLI test**

Add:

```python
from types import SimpleNamespace


def _passed_rework_entry_result(tmp_path):
    report_path = tmp_path / "rework-entry-validation.md"
    report_path.write_text("passed_without_rework_candidate", encoding="utf-8")
    return SimpleNamespace(
        status=SimpleNamespace(value="passed_without_rework_candidate"),
        report_path=report_path,
    )


def test_v2_090f_runner_rework_entry_stage_runs_full_then_validation(tmp_path, monkeypatch):
    from scripts import run_v2_090f_prd_agent_team as runner

    calls = []
    prd = tmp_path / "prd.md"
    prd.write_text("Build the tiny fullstack app.", encoding="utf-8")

    monkeypatch.setenv("BOARDROOM_RUN_REAL_PROVIDER_PROVING", "1")
    monkeypatch.setattr(runner, "load_boardroom_settings", lambda paths, env_values: object())
    monkeypatch.setattr(runner, "resolve_v2_090f_config_paths_from_env", lambda env_values: object())
    monkeypatch.setattr(runner, "run_v2_090f_planning_preflight", lambda **kwargs: calls.append("preflight") or {"status": "preflight"})
    monkeypatch.setattr(runner, "run_v2_090f_provider_planning_stage", lambda **kwargs: calls.append("planning") or {"status": "planning"})
    monkeypatch.setattr(runner, "run_v2_090f_worker_execution_stage", lambda **kwargs: calls.append("worker") or {"status": "worker"})
    monkeypatch.setattr(runner, "run_v2_090f_closeout_stage", lambda **kwargs: calls.append("closeout") or {"status": "closeout_gate_passed"})
    monkeypatch.setattr(
        runner,
        "run_v2_090f_rework_entry_validation",
        lambda validation_input: calls.append("rework-entry") or _passed_rework_entry_result(tmp_path),
    )

    exit_code = runner.main(
        [
            "--prd",
            str(prd),
            "--reset",
            "--workspace-root",
            str(tmp_path / "workspace"),
            "--output-root",
            str(tmp_path / "tiny-fullstack"),
            "--stage",
            "rework-entry",
        ]
    )

    assert exit_code == 0
    assert calls == ["preflight", "planning", "worker", "closeout", "rework-entry"]
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
PYTHONPATH=src:. python -m pytest \
  tests/proving/test_v2_090f_prd_agent_team_script.py::test_v2_090f_runner_rework_entry_stage_runs_full_then_validation \
  -q
```

Expected: FAIL because parser choices do not include `rework-entry`.

- [ ] **Step 3: Implement CLI stage**

Modify parser choices to:

```python
choices=("planning", "worker", "full", "rework-entry")
```

Then after `run_v2_090f_closeout_stage`, call `run_v2_090f_rework_entry_validation` when `args.stage == "rework-entry"`. Exit codes:

- `0` for `passed_without_rework_candidate` or `rework_accepted_candidate`;
- `4` for `rework_escalated_or_exhausted`;
- `5` for `blocked_by_missing_rework_entry`.

- [ ] **Step 4: Run CLI tests**

Run:

```bash
PYTHONPATH=src:. python -m pytest \
  tests/proving/test_v2_090f_prd_agent_team_script.py::test_v2_090f_runner_rework_entry_stage_runs_full_then_validation \
  tests/proving/test_v2_090f_prd_agent_team_real.py::test_v2_090f_real_opt_in_records_preflight_before_blocking \
  -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/run_v2_090f_prd_agent_team.py src/boardroom_os/proving/__init__.py tests/proving/test_v2_090f_prd_agent_team_script.py
git commit -m "feat(v2-090f): 增加返工入口运行阶段"
```

## Task 7: Real Provider Verification And Documentation Closeout

**Files:**

- Modify: `tests/proving/test_v2_090f_prd_agent_team_real.py`
- Modify after real verification only: `doc/04-implementation/backlog.md`
- Modify after real verification only: `doc/04-implementation/acceptance-criteria.md`
- Modify after real verification only: `doc/05-project-log/2026-06.md`

- [ ] **Step 1: Add explicit opt-in real provider test**

Add:

```python
@pytest.mark.skipif(
    os.environ.get("BOARDROOM_RUN_REAL_PROVIDER_PROVING") != "1"
    or not os.environ.get("OPENAI_API_KEY"),
    reason="V2-090F rework-entry validation requires explicit opt-in and provider secret",
)
def test_v2_090f_prd_agent_team_rework_entry_validation_real_provider(tmp_path: Path) -> None:
    from scripts.run_v2_090f_prd_agent_team import main

    prd = tmp_path / "prd.md"
    prd.write_text(
        "Build a tiny library checkout web app with a standard-library Python backend, "
        "static frontend, SQLite persistence, tests, and run instructions. "
        "Users can add books, list books, checkout and return a book, delete a book, "
        "and see the UI update from a real backend.",
        encoding="utf-8",
    )
    output = tmp_path / "tiny-fullstack"

    exit_code = main(
        [
            "--prd",
            str(prd),
            "--reset",
            "--workspace-root",
            str(tmp_path / "workspace"),
            "--output-root",
            str(output),
            "--stage",
            "rework-entry",
        ]
    )

    assert exit_code in {0, 4, 5}
    assert (output / "00-boardroom/ticket-graph.before-rework.json").is_file()
    assert (output / "00-boardroom/ticket-graph.before-rework.md").is_file()
    assert (output / "20-evidence/rework-entry/rework-terminal.json").is_file()
    assert (output / "30-audit/rework-entry-validation.md").is_file()
```

- [ ] **Step 2: Run local non-provider regression**

Run:

```bash
PYTHONPATH=src:. python -m pytest \
  tests/proving/test_v2_090f_rework_entry_validation.py \
  tests/negative/test_v2_090f_rework_entry_fail_closed.py \
  tests/proving/test_v2_090f_prd_agent_team_script.py \
  tests/proving/test_v2_100_rework_loop.py \
  tests/negative/test_v2_100_rework_loop_fail_closed.py \
  -q
```

Expected: PASS.

- [ ] **Step 3: Run real provider rerun validation**

Run:

```bash
BOARDROOM_RUN_REAL_PROVIDER_PROVING=1 PYTHONPATH=src:. \
python scripts/run_v2_090f_prd_agent_team.py \
  --prd examples/directives/tiny-fullstack-prd.md \
  --reset \
  --stage rework-entry
```

Expected: one of the four spec-defined statuses is printed and `30-audit/rework-entry-validation.md` records run id, terminal status, checked refs, graph paths, and V2-100 audit path when applicable.

- [ ] **Step 4: Verify graph evidence when rework occurs**

Run:

```bash
PYTHONPATH=src:. python - <<'PY'
import json
from pathlib import Path
root = Path("examples/generated-workspaces/tiny-fullstack")
before = json.loads((root / "00-boardroom/ticket-graph.before-rework.json").read_text(encoding="utf-8"))
after_path = root / "00-boardroom/ticket-graph.after-rework.json"
if after_path.exists():
    after = json.loads(after_path.read_text(encoding="utf-8"))
    assert after["graph_version"] > before["graph_version"]
    assert after["ticket_graph_patch_ref"]
    assert any(node["ticket_id"].startswith("ticket.rework.") for node in after["nodes"])
print("graph evidence verified")
PY
```

Expected: `graph evidence verified`.

- [ ] **Step 5: Documentation update only after verification**

If status is `passed_without_rework_candidate` or `rework_accepted_candidate` and reviewer accepts evidence, update:

- `doc/04-implementation/backlog.md` V2-090F status and completion evidence;
- `doc/04-implementation/acceptance-criteria.md` Phase 9 V2-090F checkbox;
- `doc/05-project-log/2026-06.md` with run id, command, terminal status, graph before/after paths, and audit export path.

If status is `blocked_by_missing_rework_entry`, keep V2-090F `BLOCKED` and write a new reviewed follow-up spec for the minimal gate-failure adapter before implementing it.

- [ ] **Step 6: Final verification**

Run:

```bash
PYTHONPATH=src:. python -m pytest \
  tests/proving/test_v2_090f_prd_agent_team_script.py \
  tests/proving/test_v2_090f_rework_entry_validation.py \
  tests/negative/test_v2_090f_rework_entry_fail_closed.py \
  tests/proving/test_v2_100_rework_loop.py \
  tests/negative/test_v2_100_rework_loop_fail_closed.py \
  -q

git diff --check
```

Expected: pytest PASS and `git diff --check` has no output.

- [ ] **Step 7: Commit**

Use the status-specific commit message:

```bash
git add src/boardroom_os/proving/v2_090f_rework_entry.py scripts/run_v2_090f_prd_agent_team.py tests/proving/test_v2_090f_rework_entry_validation.py tests/negative/test_v2_090f_rework_entry_fail_closed.py tests/proving/test_v2_090f_prd_agent_team_script.py tests/proving/test_v2_090f_prd_agent_team_real.py doc/04-implementation/backlog.md doc/04-implementation/acceptance-criteria.md doc/05-project-log/2026-06.md
git commit -m "feat(v2-090f): 验证返工入口重跑"
```

If the real result is `blocked_by_missing_rework_entry`, use:

```bash
git add src/boardroom_os/proving/v2_090f_rework_entry.py scripts/run_v2_090f_prd_agent_team.py tests/proving/test_v2_090f_rework_entry_validation.py tests/negative/test_v2_090f_rework_entry_fail_closed.py tests/proving/test_v2_090f_prd_agent_team_script.py tests/proving/test_v2_090f_prd_agent_team_real.py doc/05-project-log/2026-06.md
git commit -m "feat(v2-090f): 记录返工入口缺口"
```

## Self-Review Checklist

- Spec coverage:
  - Observation run covered by Task 0.
  - No-blocker closeout candidate covered by Task 3.
  - Structured blocker projection covered by Task 4.
  - V2-100 continuation and TicketGraph before/after evidence covered by Task 5.
  - CLI and real provider opt-in covered by Tasks 6 and 7.
  - Missing rework-entry gap classification covered by Task 4.

- Fail-closed rules:
  - no verified blocker -> no ReworkRequest;
  - raw exception/free text -> `blocked_by_missing_rework_entry`;
  - after graph without patch ref -> failure;
  - after graph version not greater than before -> failure;
  - fake provider cannot satisfy real provider validation.

- State boundary:
  - Plan does not mark V2-090F DONE.
  - Plan does not check Phase 9 completion boxes.
  - Plan requires reviewer acceptance before completion-only docs change.
