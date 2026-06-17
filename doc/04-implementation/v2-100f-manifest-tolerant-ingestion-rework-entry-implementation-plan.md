# V2-100F Manifest Tolerant Ingestion Rework Entry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development（子智能体驱动开发，推荐）or superpowers:executing-plans（按计划执行）to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现 V2-100F RunManifest tolerant ingestion and agent-owned blackbox verification（运行清单宽容摄取与智能体拥有的黑盒验证），让 LLM（大模型）产生的新 assertion vocabulary（断言词汇）不再 raw crash（原始崩溃）、不被忽略、不被当作通过证据，而是进入 CEO-governed（项目经理治理）的 verification/rework hook（验证/返工钩子）。

**Architecture:** RunManifest（运行清单）摄取只保留 raw semantic payload（原始语义载荷）和 skeleton summary（骨架摘要），不把自然语言式 assertion type（断言类型）当作封闭成功协议。BlackboxVerificationPlan（黑盒验证计划）替代 `RunManifest.behavioral_probes`（运行清单行为探针）的直接执行路径；`behavioral_probes` 保留为 Release DevOps（发布运维）声明的上下文和运行承诺。`verify-blackbox` ticket（黑盒验证工单）由 CEO/TicketGraph（项目经理/工单图）治理创建和派工，plan owner（计划拥有者）是被派工 AgentSeat（智能体席位），不是固定 Tester（测试者）。

**Tech Stack:** Python 3.11+、Pydantic v2、pytest；复用现有 RunManifest（运行清单）、ExecutionPackage（执行包）、ProviderAttempt（模型调用尝试记录）、TicketGraph（工单图）、LiveBlackboxProbeResult（真实黑盒探针结果）、EvidenceVerifier（证据验证器）、Checker（检查者）、CloseoutGate（收尾门禁）和 ReworkIssue（返工问题）模型。

---

## Confirmed Decisions

- [x] `BlackboxVerificationPlan`（黑盒验证计划）替代 `RunManifest.behavioral_probes`（运行清单行为探针）的直接执行路径；`behavioral_probes` 保留为上下文，不删除。
- [x] `BlackboxVerificationPlan` 的 owner（拥有者）是 CEO（项目经理）通过 TicketGraph（工单图）派给 `verify-blackbox` ticket 的 AgentSeat（智能体席位），不硬编码 Tester（测试者）。
- [x] 当前版本在 RunManifest tolerant ingestion（运行清单宽容摄取）后插入 `verify-blackbox` hook（黑盒验证钩子）；该 hook 抽象为 milestone gate（里程碑门禁）通过前的 verification/rework hook，未来 roadmap（路线图）多个里程碑可复用。
- [x] 新增 `RUN_MANIFEST_ERROR`（运行清单错误）作为 active routing code（活跃路由代码），保留 `RUN_MANIFEST_MISMATCH`（运行清单不匹配）作为 deprecated legacy code（弃用旧代码）只用于兼容读取。
- [x] 新增 `ReworkSuspectedDomain.MANIFEST`（运行清单疑似域），但 framework（框架）不得根据 raw text（原始文本）、异常消息或 manifest fragment（清单片段）自动判定域归属；域归属必须来自 typed verifier/checker/gate（类型化验证/检查/门禁）或 provider-backed governance output（模型支撑治理输出）。

## Scope And Non-Goals

V2-100F 负责：

- 让 provider-produced RunManifest（模型产出运行清单）中的未知 assertion type 不再在 ingestion/normalization（摄取/归一化）阶段 raw crash。
- 保留每个 assertion 的 raw payload（原始载荷）、raw type（原始类型）、probe/step/index（探针/步骤/索引）和 source ref（来源引用）。
- 引入 `BlackboxVerificationPlan` formal model（正式模型），并要求它绑定 ExecutionPackage（执行包）、ProviderAttempt（模型调用尝试记录）、producer seat（产出席位）和 active acceptance refs（活跃验收引用）。
- 让 runner（运行器）只执行 approved plan actions（已批准计划动作），不能从 RunManifest 直接生成业务探针、默认端点或隐藏断言。
- 将 manifest/plan/execution facts（运行清单/计划/执行事实）接入现有 EvidenceVerifier / Checker / CloseoutGate / ReworkIssue（证据验证器/检查/收尾门禁/返工问题）链路。
- 把 V2-090F 当前 `blocked_by_missing_rework_entry`（缺返工入口阻断）复判为 `rework_required`（需要返工）或 typed `blocked_or_escalated`（类型化阻断/升级），而不是 raw exception。

V2-100F 不负责：

- 不新增 standalone ManifestInterpreter（独立运行清单解释器）或框架拥有的模型解释阶段。
- 不把未知 assertion 转为“通过”或“已验证”。
- 不用硬编码 alias list（别名列表）作为主要设计；允许迁移现有小范围 normalizer（归一化器），但未知词汇必须走 raw context（原始上下文）。
- 不复制 EvidenceVerifier（证据验证器）、FinalEvidenceTableBuilder（最终证据表构建器）、Checker（检查者）或 CloseoutGate（收尾门禁）。
- 不让 runtime/runner（运行时/运行器）创建 ReworkPlan（返工计划）、修改 TicketGraph（工单图）或决定返工已接受。
- 不提前实现完整 roadmap orchestrator（路线图编排器）；只实现当前 RunManifest 后的 hook，并让接口可被未来 milestone gate 复用。

## P0 Architectural Boundary

V2-100F must implement a new governed orchestration（治理编排） path. It may reuse V2-100 domain models, reducers, validators, evidence primitives and typed contracts（领域模型、归约器、校验器、证据基础类型和强类型合同）, but it must not reuse V2-100E proving scenario orchestration（证明场景编排） as a shortcut to accepted-looking state（看似接受状态）.

Hard constraints:

- V2-100F rework-entry（返工入口） code must not import or call `run_v2_100_rework_loop_for_request()`（V2-100E 返工循环入口）.
- V2-100F must not depend on `v2_100_resettable_fixture.py`（V2-100E 可重置夹具）、`build_current_run_provider_recheck_input()`（当前运行夹具重验输入构造器）、`build_v2_100_resettable_fixture()`（V2-100E 夹具构造器） or `_write_minimal_package()`（最小占位包写入器）.
- `examples/generated-workspaces/tiny-fullstack/30-audit/v2-090k-failure-snapshot/`（V2-090K 历史失败快照） may remain in the repository only for V2-100A~E historical regression tests（历史回归测试）. V2-100F active path（活跃路径）, V2-100F fixtures（夹具） and V2-100F real-provider opt-in（真实模型显式启用） must not read, copy, adapt or route through that snapshot.
- V2-100F must not use `REWORK_ACCEPTED_CANDIDATE`（返工接受候选） as a success state. A V2-100F terminal result can only be `passed`（通过）、`rework_required`（需要返工） or `blocked_or_escalated`（阻断/升级）, and `passed` requires fresh plan/fact/evidence/checker/closeout lineage.
- `create_rework_ticket`（创建返工工单） must be consumed by the real TicketGraph reducer/projection（工单图归约器/投影） and must result in a new graph node visible in the ready queue（就绪队列）. If the governance decision repairs an existing blocked ticket, use an explicit update/repair operation kind instead of `create_rework_ticket`.
- Accepted blocker refs（已接受阻塞引用） must exactly match the current `ReworkRequest.issues[*].blocker_refs`（当前返工请求问题阻塞引用）. Old V2-090K/V2-100E blocker refs cannot satisfy a V2-100F request.
- Provider-backed worker evidence（模型支撑 worker 证据） must not be satisfied by deterministic stub（确定性占位）、fixture package（夹具包）、`assert True` tests、`changed_files: []` provider outputs（空变更模型输出） or ack-only provider outputs（仅确认模型输出）.
- V2-100F audit exports（审计导出） must be derived from actual graph projection, provider attempts, runner facts, EvidenceVerifier, Checker and CloseoutGate objects. They must not be copied or adapted from V2-100E accepted audit exports.

Failure to satisfy any hard constraint must fail closed before marking V2-100F `DONE`.

## File Structure

Create:

- `src/boardroom_os/workspace/run_manifest_ingestion.py`
  - `RunManifestRawAssertion`（运行清单原始断言）、`RunManifestSkeletonSummary`（运行清单骨架摘要）、`RunManifestIngestionContext`（运行清单摄取上下文）。
  - `ingest_run_manifest_artifact()`（摄取运行清单产物）和 `extract_run_manifest_raw_assertions()`（提取原始断言）。
- `src/boardroom_os/evidence/blackbox_plan.py`
  - `BlackboxVerificationPlan`（黑盒验证计划）、`BlackboxPlanAction`（计划动作）、`BlackboxPlanApproval`（计划批准）、`BlackboxPlanValidationResult`（计划校验结果）。
- `src/boardroom_os/execution/blackbox_plan_runner.py`
  - `BlackboxPlanRunnerInput`（黑盒计划运行输入）、`BlackboxActionExecutionFact`（黑盒动作执行事实）、`BlackboxPlanRunResult`（黑盒计划运行结果）和 plan/action gate（计划/动作门禁）。
- `src/boardroom_os/rework/verification_hook.py`
  - `VerificationHookRequest`（验证钩子请求）、`VerifyBlackboxTicketDecision`（黑盒验证工单决策）和 `build_verify_blackbox_ticket_payload()`（构建黑盒验证工单 payload）。

Modify:

- `src/boardroom_os/workspace/run_manifest.py`
  - 保留现有 typed behavior assertion（类型化行为断言）模型；不要继续扩大 enum 作为未知词汇解决方案。
- `src/boardroom_os/proving/v2_090f_prd_agent_team.py`
  - 将 `_load_v2_090k_run_manifest_artifact()` 和 `_normalize_v2_090k_behavior_assertion()` 迁移到 tolerant ingestion（宽容摄取）路径；未知 assertion 不抛 raw exception，必须进入 `RunManifestIngestionContext.raw_assertions`。
  - 停止从 `RunManifest.behavioral_probes` 直接执行行为探针作为唯一黑盒验证路径；改为产生/消费 `BlackboxVerificationPlan`。
- `src/boardroom_os/evidence/live_blackbox.py`
  - 给 `LiveBlackboxProbeResult`（真实黑盒探针结果）增加 plan lineage（计划来源链）字段，或通过 `BlackboxActionExecutionFact` 建立等价绑定。
- `src/boardroom_os/evidence/verifier.py`
  - 校验 live blackbox evidence（真实黑盒证据）必须绑定 approved `BlackboxVerificationPlan` 和真实 execution facts（执行事实）。
- `src/boardroom_os/rework/model.py`
  - 新增 `ReworkIssueCode.RUN_MANIFEST_ERROR = "run_manifest_error"`。
  - 保留 `RUN_MANIFEST_MISMATCH = "run_manifest_mismatch"`，标记为 deprecated legacy code。
  - 新增 `ReworkSuspectedDomain.MANIFEST = "manifest"`，但不让框架自动判域。
- `src/boardroom_os/rework/blocker_projection.py`
  - 新投影使用 `RUN_MANIFEST_ERROR`；旧 code 只兼容读取。
  - 不通过 message/source 字符串自动生成 `MANIFEST` suspected domain。
- `src/boardroom_os/rework/ticket_graph_patch.py`
  - `RUN_MANIFEST_ERROR` 或已声明 `MANIFEST` domain 触发 `RUN_ENV_READINESS` review（运行环境就绪审查）。
  - 不根据文本猜测 domain。
- `src/boardroom_os/agents/prompt_templates/baseline/v1/tester.md`
- `src/boardroom_os/agents/prompt_templates/baseline/v1/worker.md`
- `src/boardroom_os/agents/prompt_templates/baseline/v1/release_devops.md`
  - 将 `BehavioralProbePlan`（行为探针计划）表述迁移为 `BlackboxVerificationPlan`（黑盒验证计划）或 RunManifest context（运行清单上下文）。
- `src/boardroom_os/workspace/__init__.py`、`src/boardroom_os/evidence/__init__.py`、`src/boardroom_os/execution/__init__.py`、`src/boardroom_os/rework/__init__.py`
  - 导出新增公共 API。

Tests:

- Create `tests/workspace/test_run_manifest_tolerant_ingestion.py`
- Create `tests/evidence/test_blackbox_verification_plan.py`
- Create `tests/execution/test_blackbox_plan_runner.py`
- Create `tests/rework/test_verification_hook_ticket.py`
- Create `tests/negative/test_manifest_tolerant_ingestion_fail_closed.py`
- Create `tests/negative/test_blackbox_plan_fail_closed.py`
- Create `tests/negative/test_manifest_rework_routing_fail_closed.py`
- Create `tests/negative/test_v2_100f_forbidden_dependency_fail_closed.py`
- Create `tests/proving/test_v2_100f_governed_orchestration.py`
- Modify `tests/proving/test_v2_090k_dynamic_closeout_contract.py`
- Modify `tests/proving/test_v2_090f_rework_entry_validation.py`
- Modify `tests/negative/test_v2_090f_rework_entry_fail_closed.py`

Docs:

- Modify `doc/04-implementation/INDEX.md`
- Modify `doc/04-implementation/backlog.md`
- Modify `doc/05-project-log/decisions.md`
- Modify `doc/05-project-log/2026-06.md`

Completion-only docs after implementation:

- `doc/04-implementation/backlog.md` 状态只有在代码和真实/opt-in 验证通过后才可从 `REVIEW_REQUIRED` 改为 `DONE`。
- `doc/04-implementation/acceptance-criteria.md` 的 AC-V2-REWORK-006 和 Phase 10 checkbox 只有实现完成后才可勾选。

## Public API Targets

`src/boardroom_os/workspace/run_manifest_ingestion.py`:

```python
class RunManifestRawAssertion(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    probe_id: str
    step_id: str
    assertion_index: int = Field(ge=0)
    raw_type: str
    raw_payload: dict[str, Any]
    source_ref: str


class RunManifestSkeletonSummary(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    run_manifest_ref: RunManifestRef
    package_contract_ref: ContractId
    command_ids: tuple[ContractId, ...]
    service_command_ids: tuple[ContractId, ...]
    behavioral_probe_ids: tuple[ContractId, ...]
    acceptance_refs: tuple[AcceptanceRef, ...]


class RunManifestIngestionContext(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    source_ref: str
    raw_manifest_ref: str
    raw_manifest_sha256: str
    run_manifest: RunManifest
    skeleton_summary: RunManifestSkeletonSummary
    raw_assertions: tuple[RunManifestRawAssertion, ...]
```

`src/boardroom_os/evidence/blackbox_plan.py`:

```python
class BlackboxVerificationPlanRef(NonEmptyTextValue):
    pass


class BlackboxPlanActionKind(StrEnum):
    COMMAND = "command"
    HTTP = "http"
    BROWSER = "browser"
    TOOL = "tool"
    FILE_READ = "file_read"


class BlackboxPlanAction(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    action_id: NonEmptyTextValue
    kind: BlackboxPlanActionKind
    description: str
    input_refs: tuple[str, ...]
    parameters: dict[str, Any]
    acceptance_refs: tuple[AcceptanceRef, ...]
    expected_observations: tuple[str, ...]
    required_permissions: tuple[str, ...]


class BlackboxVerificationPlan(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    plan_id: BlackboxVerificationPlanRef
    execution_package_ref: ExecutionPackageRef
    producer_attempt_ref: ProviderAttemptRef
    producer_seat_ref: AgentSeatRef
    objective: str
    input_context_refs: tuple[str, ...]
    run_manifest_context_ref: str
    acceptance_refs: tuple[AcceptanceRef, ...]
    package_contract_ref: ContractId
    actions: tuple[BlackboxPlanAction, ...]
    evidence_obligation_refs: tuple[EvidenceObligationRef, ...]
    created_at: datetime
```

`src/boardroom_os/rework/verification_hook.py`:

```python
class VerificationHookKind(StrEnum):
    BLACKBOX_BEFORE_GATE = "blackbox_before_gate"


class VerificationHookRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    hook_request_id: NonEmptyTextValue
    hook_kind: VerificationHookKind
    milestone_ref: str
    trigger_ref: str
    run_manifest_context_ref: str
    acceptance_refs: tuple[AcceptanceRef, ...]
    package_contract_ref: ContractId
    requested_by_actor: ReworkActorKind
    active_graph_version: int = Field(gt=0)
    created_at: datetime


class VerifyBlackboxTicketDecision(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    hook_request_ref: NonEmptyTextValue
    decided_by_actor: ReworkActorKind
    provider_attempt_ref: ProviderAttemptRef
    ticket_payload: TicketCreatedPayload
    rationale: str
```

Key rules:

- `VerificationHookRequest`（验证钩子请求）不是 TicketNode（工单节点），不能直接进入 ready queue（就绪队列）。
- `build_verify_blackbox_ticket_payload()` 必须要求 `decided_by_actor == ReworkActorKind.CEO`，并校验 `ticket_payload.purpose`、`required_outputs`、`acceptance_refs`、`allowed_read_refs` 和 `evidence_obligations` 覆盖 hook request。
- Seat assignment（席位派工）继续走现有 SeatAssignmentGraph（席位派工图），不在该 helper 内指定固定 seat。

---

## Task 0: Pre-Flight And Drift Check

**Files:**

- Read: `doc/04-implementation/v2-100f-manifest-tolerant-ingestion-rework-entry-spec.md`
- Read: `src/boardroom_os/proving/v2_090f_prd_agent_team.py`
- Read: `src/boardroom_os/workspace/run_manifest.py`
- Read: `src/boardroom_os/evidence/live_blackbox.py`
- Read: `src/boardroom_os/rework/model.py`
- Read: `src/boardroom_os/rework/ticket_graph_patch.py`

- [ ] **Step 1: Confirm worktree state**

Run:

```bash
git status --short --branch
```

Expected: No unrelated staged changes. If dirty files exist, read them before editing and preserve user changes.

- [ ] **Step 2: Confirm current raw-crash reproduction point**

Run:

```bash
PYTHONPATH=src:. python -m pytest \
  tests/proving/test_v2_090f_rework_entry_validation.py \
  tests/negative/test_v2_090f_rework_entry_fail_closed.py \
  -q
```

Expected: Existing rework-entry tests pass and still classify raw exception as `blocked_by_missing_rework_entry`.

- [ ] **Step 3: Confirm no active implementation plan has already been applied**

Run:

```bash
test ! -e src/boardroom_os/workspace/run_manifest_ingestion.py
test ! -e src/boardroom_os/evidence/blackbox_plan.py
test ! -e src/boardroom_os/execution/blackbox_plan_runner.py
```

Expected: files do not exist. If any file exists, inspect and continue from existing work instead of overwriting.

## Task 1: Tolerant RunManifest Ingestion Context

**Files:**

- Create: `src/boardroom_os/workspace/run_manifest_ingestion.py`
- Modify: `src/boardroom_os/workspace/run_manifest.py`
- Modify: `src/boardroom_os/proving/v2_090f_prd_agent_team.py`
- Create: `tests/workspace/test_run_manifest_tolerant_ingestion.py`
- Create: `tests/negative/test_manifest_tolerant_ingestion_fail_closed.py`

- [ ] **Step 1: Write failing negative test for unknown assertion no raw crash**

Add to `tests/workspace/test_run_manifest_tolerant_ingestion.py`:

```python
from boardroom_os.workspace.run_manifest_ingestion import ingest_run_manifest_artifact


def test_unknown_assertion_is_preserved_without_raw_crash():
    context = ingest_run_manifest_artifact(
        artifact=_manifest_with_assertion(
            {"type": "json_array_contains_field", "path": "$", "field": "title"}
        ),
        source_ref="00-boardroom/generated-run-manifest.json",
        raw_manifest_ref="artifact.run_manifest.generated",
    )

    assert context.run_manifest.behavioral_probes
    assert context.raw_assertions[0].raw_type == "json_array_contains_field"
    assert context.raw_assertions[0].raw_payload["field"] == "title"
```

The helper `_manifest_with_assertion()` must build a minimal RunManifest-like artifact with one command, one service contract, one readiness probe and one behavioral probe. Do not import old generated workspace files.

- [ ] **Step 2: Implement raw assertion extraction**

In `run_manifest_ingestion.py`, implement:

```python
def extract_run_manifest_raw_assertions(
    artifact: Mapping[str, Any],
    *,
    source_ref: str,
) -> tuple[RunManifestRawAssertion, ...]:
    raw_assertions: list[RunManifestRawAssertion] = []
    for probe in artifact.get("behavioral_probes") or ():
        if not isinstance(probe, Mapping):
            continue
        probe_id = str(probe.get("probe_id") or "").strip()
        for step in probe.get("steps") or probe.get("http_steps") or ():
            if not isinstance(step, Mapping):
                continue
            step_id = str(step.get("step_id") or "").strip()
            for index, assertion in enumerate(step.get("assertions") or ()):
                if not isinstance(assertion, Mapping):
                    continue
                raw_type = str(
                    assertion.get("kind")
                    or assertion.get("type")
                    or assertion.get("operator")
                    or "unknown"
                ).strip()
                raw_assertions.append(
                    RunManifestRawAssertion(
                        probe_id=probe_id or "unknown-probe",
                        step_id=step_id or "unknown-step",
                        assertion_index=index,
                        raw_type=raw_type,
                        raw_payload=dict(assertion),
                        source_ref=source_ref,
                    )
                )
    return tuple(raw_assertions)
```

This extraction preserves raw data. It must not classify domain, mark success, or infer acceptance satisfaction.

- [ ] **Step 3: Replace unsupported assertion failure with raw preservation**

Modify `_normalize_v2_090k_behavior_assertion()` in `src/boardroom_os/proving/v2_090f_prd_agent_team.py` so unsupported assertion types return `None` and are preserved by `RunManifestIngestionContext.raw_assertions`, instead of raising:

```python
return None
```

Do not add `json_array_contains_field` as a new successful alias. The unknown assertion remains context, not executable evidence.

- [ ] **Step 4: Add fail-closed tests for missing raw artifact and empty skeleton**

Add to `tests/negative/test_manifest_tolerant_ingestion_fail_closed.py`:

```python
import pytest

from boardroom_os.workspace.run_manifest_ingestion import ingest_run_manifest_artifact


def test_missing_raw_manifest_ref_fails_closed():
    with pytest.raises(ValueError, match="raw_manifest_ref"):
        ingest_run_manifest_artifact(
            artifact=_manifest_with_assertion({"type": "json_array_contains_field"}),
            source_ref="00-boardroom/generated-run-manifest.json",
            raw_manifest_ref="",
        )


def test_manifest_without_commands_fails_closed():
    payload = _manifest_with_assertion({"type": "json_array_contains_field"})
    payload["commands"] = []
    with pytest.raises(ValueError, match="commands"):
        ingest_run_manifest_artifact(
            artifact=payload,
            source_ref="00-boardroom/generated-run-manifest.json",
            raw_manifest_ref="artifact.run_manifest.generated",
        )
```

- [ ] **Step 5: Run focused tests**

Run:

```bash
PYTHONPATH=src:. python -m pytest \
  tests/workspace/test_run_manifest_tolerant_ingestion.py \
  tests/negative/test_manifest_tolerant_ingestion_fail_closed.py \
  tests/proving/test_v2_090k_dynamic_closeout_contract.py \
  -q
```

Expected: new tolerant ingestion tests pass; existing supported assertion normalization still passes.

## Task 2: BlackboxVerificationPlan Formal Model

**Files:**

- Create: `src/boardroom_os/evidence/blackbox_plan.py`
- Modify: `src/boardroom_os/evidence/__init__.py`
- Create: `tests/evidence/test_blackbox_verification_plan.py`
- Create: `tests/negative/test_blackbox_plan_fail_closed.py`

- [ ] **Step 1: Write failing tests for provider-backed plan lineage**

Add to `tests/evidence/test_blackbox_verification_plan.py`:

```python
def test_blackbox_plan_requires_provider_attempt_lineage():
    plan = blackbox_plan_fixture()

    assert plan.producer_attempt_ref.value.startswith("provider-attempt.")
    assert plan.execution_package_ref.value.startswith("exec.")
    assert plan.actions[0].acceptance_refs == plan.acceptance_refs
```

Add to `tests/negative/test_blackbox_plan_fail_closed.py`:

```python
import pytest

from boardroom_os.evidence.blackbox_plan import BlackboxVerificationPlan


def test_blackbox_plan_without_actions_fails_closed():
    payload = blackbox_plan_payload()
    payload["actions"] = []
    with pytest.raises(ValueError, match="actions"):
        BlackboxVerificationPlan.model_validate(payload)


def test_blackbox_plan_action_acceptance_outside_plan_fails_closed():
    payload = blackbox_plan_payload()
    payload["actions"][0]["acceptance_refs"] = [{"value": "AC-OUTSIDE"}]
    with pytest.raises(ValueError, match="acceptance"):
        BlackboxVerificationPlan.model_validate(payload)
```

- [ ] **Step 2: Implement BlackboxVerificationPlan models**

Implement the API in `blackbox_plan.py` as specified in Public API Targets. Validators must enforce:

- non-empty objective, context refs, actions and expected observations;
- unique action IDs;
- every action acceptance ref is inside plan acceptance refs;
- `producer_attempt_ref`, `execution_package_ref` and `producer_seat_ref` are required;
- `parameters` may be open structured data, but must be a dict and must not include `passed`, `success`, `closeout_passed` or `verified` keys.

- [ ] **Step 3: Add explicit anti-prose-pass test**

Add:

```python
def test_plan_parameters_cannot_mark_passed():
    payload = blackbox_plan_payload()
    payload["actions"][0]["parameters"]["passed"] = True
    with pytest.raises(ValueError, match="passed|success|verified"):
        BlackboxVerificationPlan.model_validate(payload)
```

- [ ] **Step 4: Run focused tests**

Run:

```bash
PYTHONPATH=src:. python -m pytest \
  tests/evidence/test_blackbox_verification_plan.py \
  tests/negative/test_blackbox_plan_fail_closed.py \
  -q
```

Expected: BlackboxVerificationPlan model rejects missing lineage, empty actions, out-of-contract acceptance refs and prose-success markers.

## Task 3: CEO-Governed Verification Hook And Ticket Creation

**Files:**

- Create: `src/boardroom_os/rework/verification_hook.py`
- Modify: `src/boardroom_os/rework/__init__.py`
- Create: `tests/rework/test_verification_hook_ticket.py`
- Create: `tests/negative/test_manifest_rework_routing_fail_closed.py`

- [ ] **Step 1: Add module docstring with trigger convention**

At the top of `src/boardroom_os/rework/verification_hook.py`, add:

```python
"""Verification hook boundary for milestone-gated blackbox verification.

RunManifest ingestion returns RunManifestIngestionContext only. It does not
create tickets, assign seats, decide rework, or trigger runner execution.

A milestone/gate caller inspects the ingestion context together with the active
AcceptanceContract, PackageContract, evidence obligations, and milestone policy.
When the milestone requires blackbox verification, the caller may create a
VerificationHookRequest and submit it to the governance path.

raw_assertions being non-empty is a V2-100F trigger signal, not proof of failure
and not a runner instruction. Runner code must not create this request, create a
ticket, assign a seat, or infer business verification actions from RunManifest
content.
"""
```

This docstring is part of the boundary contract. `ingest_run_manifest_artifact()`（运行清单产物摄取函数） returns `RunManifestIngestionContext`（运行清单摄取上下文） only; the current V2-090F caller or future milestone gate adapter（里程碑门禁适配器） decides whether to create `VerificationHookRequest`（验证钩子请求） and submit it to governance.

- [ ] **Step 2: Write failing test for hook request not being a ticket**

Add:

```python
from boardroom_os.rework.verification_hook import VerificationHookRequest


def test_verification_hook_request_is_not_ticket_node():
    request = verification_hook_request_fixture()

    assert request.hook_kind.value == "blackbox_before_gate"
    assert not hasattr(request, "seat_demand")
    assert not hasattr(request, "status")
```

- [ ] **Step 3: Write failing tests for CEO-only ticket decision**

Add:

```python
import pytest

from boardroom_os.rework.model import ReworkActorKind
from boardroom_os.rework.verification_hook import build_verify_blackbox_ticket_payload


def test_non_ceo_cannot_create_verify_blackbox_ticket_payload():
    with pytest.raises(ValueError, match="CEO"):
        build_verify_blackbox_ticket_payload(
            hook_request=verification_hook_request_fixture(),
            decided_by_actor=ReworkActorKind.RUNTIME,
            provider_attempt_ref=provider_attempt_ref_fixture(),
            ticket_payload=ticket_payload_fixture(),
        )
```

- [ ] **Step 4: Implement hook and ticket decision validator**

`build_verify_blackbox_ticket_payload()` must:

- require `decided_by_actor is ReworkActorKind.CEO`;
- require non-empty `provider_attempt_ref`;
- require ticket purpose contains `blackbox` or `verification` and required output includes `BlackboxVerificationPlan`;
- require ticket acceptance refs exactly cover or explicitly subset hook acceptance refs;
- require ticket `allowed_read_refs` include run manifest context ref, active contract refs and previous failure context refs;
- never assign a concrete seat ref.

- [ ] **Step 5: Add milestone-compatible hook field test**

Add:

```python
def test_hook_request_carries_milestone_ref_for_future_roadmap_gates():
    request = verification_hook_request_fixture(milestone_ref="milestone.phase-10.v2-100f")

    assert request.milestone_ref == "milestone.phase-10.v2-100f"
```

- [ ] **Step 6: Run focused tests**

Run:

```bash
PYTHONPATH=src:. python -m pytest \
  tests/rework/test_verification_hook_ticket.py \
  tests/negative/test_manifest_rework_routing_fail_closed.py \
  -q
```

Expected: framework can record hook requests, but only CEO-backed governance output can become a ticket payload.

## Task 4: Runner Executes Only Approved Blackbox Plans

**Files:**

- Create: `src/boardroom_os/execution/blackbox_plan_runner.py`
- Modify: `src/boardroom_os/execution/__init__.py`
- Create: `tests/execution/test_blackbox_plan_runner.py`
- Modify: `tests/negative/test_blackbox_plan_fail_closed.py`

- [ ] **Step 1: Write failing test for absent plan**

Add:

```python
import pytest

from boardroom_os.execution.blackbox_plan_runner import (
    BlackboxPlanRunnerInput,
    BlackboxPlanRunner,
)


def test_runner_rejects_missing_blackbox_plan():
    with pytest.raises(ValueError, match="BlackboxVerificationPlan"):
        BlackboxPlanRunner().run(
            BlackboxPlanRunnerInput(
                plan=None,
                approved_action_ids=("action.http.list-books",),
                execution_policy=execution_policy_fixture(),
            )
        )
```

- [ ] **Step 2: Write failing test for plan-outside action**

Add:

```python
def test_runner_rejects_action_outside_approved_plan():
    plan = blackbox_plan_fixture(action_ids=("action.http.list-books",))
    with pytest.raises(ValueError, match="approved plan"):
        BlackboxPlanRunner().record_action_fact(
            plan=plan,
            action_fact=action_fact_fixture(action_id="action.http.delete-book"),
        )
```

- [ ] **Step 3: Implement runner gate**

The first implementation may execute only command and HTTP actions if those delegates already exist. Browser/tool actions must fail closed with `blocked_or_escalated` until a real executor is wired; they must not be simulated.

Required validators:

- action id must exist in `plan.actions`;
- action id must be explicitly approved;
- required permissions must be subset of execution policy;
- produced fact must include started/finished timestamps, status/exit code, output refs and plan ref;
- fact acceptance refs must match the plan action acceptance refs.

- [ ] **Step 4: Add no-invented-action regression**

Add:

```python
def test_runner_cannot_invent_default_http_probe():
    plan = blackbox_plan_fixture(actions=())
    with pytest.raises(ValueError, match="actions"):
        BlackboxPlanRunner().run(
            BlackboxPlanRunnerInput(
                plan=plan,
                approved_action_ids=("action.http.default-health",),
                execution_policy=execution_policy_fixture(),
            )
        )
```

- [ ] **Step 5: Run focused tests**

Run:

```bash
PYTHONPATH=src:. python -m pytest \
  tests/execution/test_blackbox_plan_runner.py \
  tests/negative/test_blackbox_plan_fail_closed.py \
  -q
```

Expected: runner accepts only plan-declared and policy-approved actions; unsupported real execution types fail closed rather than succeed.

## Task 5: Live Blackbox Evidence Plan Lineage

**Files:**

- Modify: `src/boardroom_os/evidence/live_blackbox.py`
- Modify: `src/boardroom_os/evidence/verifier.py`
- Modify: `tests/evidence/test_live_blackbox_evidence.py`
- Modify: `tests/negative/test_live_blackbox_integration_fail_closed.py`

- [ ] **Step 1: Write failing test for missing plan lineage**

Add:

```python
def test_live_blackbox_probe_requires_blackbox_plan_ref_for_v2_100f():
    evidence = live_blackbox_evidence_fixture(probe_plan_ref=None)
    result = LiveBlackboxIntegrationVerifier().verify(
        LiveBlackboxVerifierInput(
            evidence=evidence,
            package_contract=package_contract_fixture(),
            service_runs=service_run_fixtures(),
        )
    )

    assert not result.success
    assert any("plan" in blocker.message.lower() for blocker in result.blockers)
```

- [ ] **Step 2: Add plan lineage field**

Either add `blackbox_plan_ref: BlackboxVerificationPlanRef | None = None` to `LiveBlackboxProbeResult`, or require a `BlackboxActionExecutionFact` manifest that maps each probe to `plan_ref`.

Compatibility rule:

- Existing historical fixtures may omit the field.
- V2-100F verifier path must require it when the claim source type is live blackbox integration.

- [ ] **Step 3: Ensure real execution facts are required**

Extend verifier tests so `BlackboxVerificationPlan` alone cannot become verified evidence:

```python
def test_blackbox_plan_without_execution_facts_does_not_verify():
    result = verify_live_blackbox_with_plan(plan=blackbox_plan_fixture(), facts=())

    assert not result.success
    assert any(blocker.code.value in {"probe_evidence_missing", "command_evidence_missing"} for blocker in result.blockers)
```

- [ ] **Step 4: Run focused tests**

Run:

```bash
PYTHONPATH=src:. python -m pytest \
  tests/evidence/test_live_blackbox_evidence.py \
  tests/negative/test_live_blackbox_integration_fail_closed.py \
  -q
```

Expected: plan prose cannot verify behavior; only real command/HTTP/browser/tool facts can feed evidence.

## Task 6: Rework Routing Codes And Suspected Domain Boundary

**Files:**

- Modify: `src/boardroom_os/rework/model.py`
- Modify: `src/boardroom_os/rework/blocker_projection.py`
- Modify: `src/boardroom_os/rework/ticket_graph_patch.py`
- Modify: `tests/rework/test_rework_model.py`
- Modify: `tests/rework/test_v2_090k_failure_snapshot_projection.py`
- Modify: `tests/rework/test_multi_role_graph_patch_reviews.py`
- Modify: `tests/negative/test_rework_model_fail_closed.py`
- Modify: `tests/negative/test_manifest_rework_routing_fail_closed.py`

- [ ] **Step 1: Write failing test for new active code**

Add:

```python
from boardroom_os.rework.model import ReworkIssueCode


def test_run_manifest_error_is_active_issue_code():
    assert ReworkIssueCode.RUN_MANIFEST_ERROR.value == "run_manifest_error"
    assert ReworkIssueCode.RUN_MANIFEST_MISMATCH.value == "run_manifest_mismatch"
```

- [ ] **Step 2: Write failing test that new projections avoid old code**

Add:

```python
def test_manifest_projection_uses_run_manifest_error_not_mismatch():
    request = project_manifest_blackbox_failure_fixture()

    assert request.issues[0].issue_code is ReworkIssueCode.RUN_MANIFEST_ERROR
    assert request.issues[0].issue_code is not ReworkIssueCode.RUN_MANIFEST_MISMATCH
```

- [ ] **Step 3: Add MANIFEST domain without framework auto-classification**

Add enum value:

```python
class ReworkSuspectedDomain(StrEnum):
    ...
    MANIFEST = "manifest"
```

Add negative test:

```python
def test_raw_exception_alone_does_not_create_manifest_domain():
    issue = project_raw_run_manifest_error_without_typed_source()

    assert ReworkSuspectedDomain.MANIFEST not in issue.suspected_domains
```

- [ ] **Step 4: Update graph patch review inference**

Modify `infer_required_review_domains()` so:

```python
if issue_codes & {
    ReworkIssueCode.ENV_BINDING_NOT_CONVERGED,
    ReworkIssueCode.RUN_MANIFEST_ERROR,
    ReworkIssueCode.RUN_MANIFEST_MISMATCH,
} or {
    ReworkSuspectedDomain.RUN_ENV,
    ReworkSuspectedDomain.MANIFEST,
} & suspected_domains:
    domains.append(GraphPatchReviewDomain.RUN_ENV_READINESS)
```

Do not infer `MANIFEST` domain in `_domains_for_issue_code()` from text. If no typed source declares it, leave domains coarse, such as `EVIDENCE_PROJECTION`, and let CEO/reviewer classify.

- [ ] **Step 5: Run focused tests**

Run:

```bash
PYTHONPATH=src:. python -m pytest \
  tests/rework/test_rework_model.py \
  tests/rework/test_v2_090k_failure_snapshot_projection.py \
  tests/rework/test_multi_role_graph_patch_reviews.py \
  tests/negative/test_rework_model_fail_closed.py \
  tests/negative/test_manifest_rework_routing_fail_closed.py \
  -q
```

Expected: new active routing code is used; old code remains readable; MANIFEST domain exists but is not framework-guessed.

## Task 7: Prompt And ExecutionPackage Context Wiring

**Files:**

- Modify: `src/boardroom_os/agents/prompt_templates/baseline/v1/tester.md`
- Modify: `src/boardroom_os/agents/prompt_templates/baseline/v1/worker.md`
- Modify: `src/boardroom_os/agents/prompt_templates/baseline/v1/release_devops.md`
- Modify: `src/boardroom_os/execution/compiler.py`
- Modify: `tests/execution/test_execution_package_compiler.py`
- Modify: `tests/execution/test_role_prompt_hooks.py`
- Modify: `tests/execution/test_role_prompt_hooks_rework_governance.py`

- [ ] **Step 1: Replace BehavioralProbePlan prompt wording**

Update prompts:

- Tester prompt should request `BlackboxVerificationPlan` when assigned a blackbox verification ticket.
- Release DevOps prompt should frame RunManifest `behavioral_probes` as behavior intent/context, not a framework-executed success script.
- Worker prompt should not claim behavior passed from `behavioral_probes`; it may reference plan/facts only.

- [ ] **Step 2: Add ExecutionPackage context test**

Add:

```python
def test_verify_blackbox_execution_package_contains_manifest_raw_context():
    package = compile_verify_blackbox_execution_package_fixture()

    context_values = {ref.value for ref in package.context_refs}
    assert "context.run_manifest.raw" in context_values
    assert "context.run_manifest.skeleton" in context_values
    assert "context.previous_failures" in context_values
    assert any(output.value == "BlackboxVerificationPlan" for output in package.required_outputs)
```

- [ ] **Step 3: Ensure compiler still follows graph assignment**

Add negative test:

```python
def test_verify_blackbox_compiler_requires_seat_assignment():
    with pytest.raises(ExecutionPackageCompilerError, match="missing seat assignment"):
        compile_verify_blackbox_execution_package_fixture(with_assignment=False)
```

- [ ] **Step 4: Run focused tests**

Run:

```bash
PYTHONPATH=src:. python -m pytest \
  tests/execution/test_execution_package_compiler.py \
  tests/execution/test_role_prompt_hooks.py \
  tests/execution/test_role_prompt_hooks_rework_governance.py \
  -q
```

Expected: plan production context is present only through graph-assigned ExecutionPackage.

## Task 8: V2-100F Governed Orchestration And V2-090F Rework-Entry Integration

**Files:**

- Modify: `src/boardroom_os/proving/v2_090f_prd_agent_team.py`
- Modify: `src/boardroom_os/proving/v2_090f_rework_entry.py`
- Modify: `tests/proving/test_v2_090f_rework_entry_validation.py`
- Modify: `tests/negative/test_v2_090f_rework_entry_fail_closed.py`
- Modify: `tests/proving/test_v2_090f_prd_agent_team_script.py`
- Create: `tests/negative/test_v2_100f_forbidden_dependency_fail_closed.py`
- Create: `tests/proving/test_v2_100f_governed_orchestration.py`

- [ ] **Step 1: Add forbidden dependency tests**

Add to `tests/negative/test_v2_100f_forbidden_dependency_fail_closed.py`:

```python
import inspect

import boardroom_os.proving.v2_090f_rework_entry as rework_entry


def test_v2_100f_rework_entry_does_not_call_v2_100e_rework_loop():
    source = inspect.getsource(rework_entry)

    assert "run_v2_100_rework_loop_for_request" not in source


def test_v2_100f_rework_entry_does_not_depend_on_v2_100e_fixtures():
    source = inspect.getsource(rework_entry)

    forbidden = (
        "v2_100_resettable_fixture",
        "build_current_run_provider_recheck_input",
        "build_v2_100_resettable_fixture",
        "_write_minimal_package",
        "v2-090k-failure-snapshot",
    )
    assert not any(marker in source for marker in forbidden)


def test_v2_100f_rework_entry_does_not_emit_rework_accepted_candidate():
    source = inspect.getsource(rework_entry)

    assert "REWORK_ACCEPTED_CANDIDATE" not in source
```

Expected before implementation: these tests fail against the current shortcut path. They must pass before any V2-100F completion claim.

- [ ] **Step 2: Add regression for current novel assertion**

Add:

```python
def test_v2_090f_rework_entry_preserves_json_array_contains_field(tmp_path):
    output_root = write_v2_090f_artifacts_with_manifest_assertion(
        tmp_path,
        {"type": "json_array_contains_field", "path": "$", "field": "title"},
    )

    result = run_v2_090f_rework_entry_validation(
        V2_090FReworkEntryValidationInput(
            output_root=output_root,
            workspace_root=tmp_path / "workspace",
            run_id="run.v2-090f.novel-assertion",
            cycle_id="rework-cycle.v2-090f.novel-assertion",
            max_rounds=1,
            require_real_provider=False,
        )
    )

    assert result.status is not V2_090FReworkEntryStatus.BLOCKED_BY_MISSING_REWORK_ENTRY
```

If no provider-backed plan exists in the fixture, expected status should be typed `blocked_or_escalated` with missing plan/provider context, not raw exception.

- [ ] **Step 3: Add governed orchestration happy-path test**

Add to `tests/proving/test_v2_100f_governed_orchestration.py`:

```python
def test_v2_100f_verify_blackbox_ticket_is_graph_projected_before_plan_execution(tmp_path):
    result = run_v2_100f_governed_orchestration_fixture(
        tmp_path,
        assertion={"type": "json_array_contains_field", "path": "$", "field": "title"},
        provider_plan=True,
        runner_facts=True,
    )

    assert result.ingestion_context.raw_assertions[0].raw_type == "json_array_contains_field"
    assert result.verify_blackbox_ticket_ref.value.startswith("ticket.verify-blackbox.")
    assert result.ticket_graph_after.has_node(result.verify_blackbox_ticket_ref)
    assert result.ticket_graph_after.ready_queue_contains(result.verify_blackbox_ticket_ref)
    assert result.blackbox_plan.producer_attempt_ref.value.startswith("provider-attempt.")
    assert result.action_facts
    assert {fact.plan_ref for fact in result.action_facts} == {result.blackbox_plan.plan_id}
    assert result.terminal_status in {"passed", "rework_required", "blocked_or_escalated"}
```

The fixture may use a deterministic local fake provider only for unit tests, but the fake must produce a real `ProviderAttempt` object and must not generate implementation source, stub tests or accepted audit evidence.

- [ ] **Step 4: Route missing provider/config to blocked_or_escalated**

Add a new V2-100F status enum in the rework-entry layer if needed:

```python
class V2_100FBlackboxRoutingStatus(StrEnum):
    PASSED = "passed"
    REWORK_REQUIRED = "rework_required"
    BLOCKED_OR_ESCALATED = "blocked_or_escalated"
```

Do not overload `V2_090FReworkEntryStatus.BLOCKED_BY_MISSING_REWORK_ENTRY` for cases where trustworthy raw manifest context exists but required provider/config/plan is missing.

- [ ] **Step 5: Replace direct V2-100E continuation with V2-100F orchestration**

Remove the V2-090F rework-entry shortcut that converts any structured `ReworkRequest` directly into `run_v2_100_rework_loop_for_request(...)`.

Implement the V2-100F orchestration in this order:

1. `ingest_run_manifest_artifact()` returns `RunManifestIngestionContext` only.
2. A governance adapter creates `VerificationHookRequest` only when active AcceptanceContract / PackageContract / RunManifest context is trustworthy.
3. CEO provider output creates a `TicketGraphPatch` containing a `verify-blackbox` ticket operation.
4. TicketGraph reducer/projection consumes the patch and produces an after graph with a visible `verify-blackbox` node in ready queue.
5. Seat assignment chooses an AgentSeat from the graph demand; the framework must not hardcode Tester.
6. ExecutionPackage compiler creates a provider-backed package requiring `BlackboxVerificationPlan`.
7. The assigned AgentSeat produces `BlackboxVerificationPlan`.
8. Runner executes only approved plan actions and records `BlackboxActionExecutionFact`.
9. EvidenceVerifier / Checker / CloseoutGate consume facts and produce exactly one terminal status: `passed`, `rework_required` or `blocked_or_escalated`.

Do not call V2-100E scenario runners, resettable fixtures or audit exporters from this path.

- [ ] **Step 6: Integrate hook request and fact exports**

When RunManifest ingestion succeeds and live blackbox evidence is required, export:

- `20-evidence/blackbox/run-manifest-ingestion-context.json`
- `20-evidence/blackbox/verification-hook-request.json`
- `20-evidence/blackbox/ticket-graph.before-blackbox.json`
- `20-evidence/blackbox/ticket-graph.after-blackbox.json`
- `20-evidence/blackbox/blackbox-verification-plan.json` when produced
- `20-evidence/blackbox/blackbox-action-facts.json` when executed
- `20-evidence/blackbox/blackbox-run-result.json`

Each export must include content hash or stable JSON hash in the audit report.

- [ ] **Step 7: Add blocker alignment and graph mutation tests**

Add negative tests:

```python
def test_v2_100f_rejects_accepted_blockers_outside_current_request(tmp_path):
    result = run_v2_100f_governed_orchestration_fixture(
        tmp_path,
        accepted_blockers=("v2-090k-failure.probe-response-shape-mismatch",),
        request_blockers=("run-manifest.validator.service-entrypoint-not-required-output",),
    )

    assert result.terminal_status == "blocked_or_escalated"
    assert "accepted_blockers" in result.reason


def test_create_rework_ticket_must_add_graph_node(tmp_path):
    result = run_v2_100f_graph_patch_fixture(
        tmp_path,
        operation_kind="create_rework_ticket",
        after_graph_adds_node=False,
    )

    assert result.terminal_status == "blocked_or_escalated"
    assert "create_rework_ticket" in result.reason
```

- [ ] **Step 8: Ensure no direct behavioral probe execution path remains active**

Add negative test:

```python
def test_runner_does_not_execute_run_manifest_behavioral_probes_without_plan(tmp_path):
    output_root = write_v2_090f_artifacts_with_manifest_assertion(
        tmp_path,
        {"type": "json_equals", "path": "$.status", "value": "ok"},
    )

    terminal = run_blackbox_without_plan(output_root)

    assert terminal["status"] == "blocked_or_escalated"
    assert "BlackboxVerificationPlan" in terminal["reason"]
```

- [ ] **Step 9: Ensure worker evidence cannot be stubbed**

Add negative test:

```python
def test_v2_100f_worker_stub_or_empty_provider_changes_cannot_satisfy_evidence(tmp_path):
    result = run_v2_100f_worker_evidence_fixture(
        tmp_path,
        changed_files=[],
        source_text="def create_book():\n    return {'book': {'id': 1}}\n",
        test_text="def test_create_book():\n    assert True\n",
    )

    assert result.terminal_status == "blocked_or_escalated"
    assert "stub" in result.reason or "changed_files" in result.reason
```

- [ ] **Step 10: Run focused tests**

Run:

```bash
PYTHONPATH=src:. python -m pytest \
  tests/negative/test_v2_100f_forbidden_dependency_fail_closed.py \
  tests/proving/test_v2_100f_governed_orchestration.py \
  tests/proving/test_v2_090f_rework_entry_validation.py \
  tests/negative/test_v2_090f_rework_entry_fail_closed.py \
  tests/proving/test_v2_090f_prd_agent_team_script.py \
  -q
```

Expected: current novel assertion no longer creates raw crash; missing plan/provider produces typed blocked/escalated context; direct behavioral probe execution without plan is rejected; V2-100F does not call V2-100E shortcut code; verify-blackbox ticket is graph-projected before plan execution.

## Task 9: End-To-End Regression And Real Provider Opt-In

**Files:**

- Modify: `tests/proving/test_v2_090f_prd_agent_team_real.py`
- Modify: `scripts/run_v2_090f_prd_agent_team.py` only if CLI needs to export new V2-100F artifacts
- No completion docs until verification passes

- [ ] **Step 1: Run focused local regression**

Run:

```bash
PYTHONPATH=src:. python -m pytest \
  tests/workspace/test_run_manifest_tolerant_ingestion.py \
  tests/evidence/test_blackbox_verification_plan.py \
  tests/execution/test_blackbox_plan_runner.py \
  tests/rework/test_verification_hook_ticket.py \
  tests/negative/test_v2_100f_forbidden_dependency_fail_closed.py \
  tests/proving/test_v2_100f_governed_orchestration.py \
  tests/proving/test_v2_090f_rework_entry_validation.py \
  tests/negative/test_manifest_tolerant_ingestion_fail_closed.py \
  tests/negative/test_blackbox_plan_fail_closed.py \
  tests/negative/test_manifest_rework_routing_fail_closed.py \
  tests/negative/test_v2_090f_rework_entry_fail_closed.py \
  -q
```

Expected: all focused V2-100F tests pass.

- [ ] **Step 2: Run broader affected regression**

Run:

```bash
PYTHONPATH=src:. python -m pytest \
  tests/workspace \
  tests/evidence \
  tests/execution \
  tests/rework \
  tests/reducers/test_rework_reducer.py \
  tests/proving/test_v2_090k_dynamic_closeout_contract.py \
  tests/proving/test_v2_090f_rework_entry_validation.py \
  tests/negative/test_run_manifest_command_coverage.py \
  tests/negative/test_live_blackbox_integration_fail_closed.py \
  tests/negative/test_rework_model_fail_closed.py \
  tests/negative/test_rework_reducer_fail_closed.py \
  -q
```

Expected: existing supported RunManifest, live blackbox, execution package and rework regressions pass.

- [ ] **Step 3: Run V2-090F real provider opt-in**

Run only with reviewer approval and provider secrets:

```bash
BOARDROOM_RUN_REAL_PROVIDER_PROVING=1 PYTHONPATH=src:. \
python scripts/run_v2_090f_prd_agent_team.py \
  --prd examples/directives/tiny-fullstack-prd.md \
  --reset \
  --stage rework-entry
```

Expected:

- no `unsupported RunManifest behavior assertion type` raw exception;
- `20-evidence/blackbox/run-manifest-ingestion-context.json` exists;
- `20-evidence/blackbox/verification-hook-request.json` exists when live blackbox verification is required;
- `20-evidence/blackbox/ticket-graph.after-blackbox.json` shows a graph-projected `verify-blackbox` ticket when a plan is required;
- provider-backed `BlackboxVerificationPlan` exists before runner action execution;
- runner executes only approved plan actions and records `BlackboxActionExecutionFact` entries;
- no V2-100E fixture package, `_write_minimal_package` output, `assert True` stub, `changed_files: []` worker evidence, or accepted-looking V2-100E audit export is used as success evidence;
- accepted blocker refs, when present, exactly match the current ReworkRequest blocker refs;
- terminal status is `rework_required`, `passed`, or `blocked_or_escalated` with typed reason, not `blocked_by_missing_rework_entry`.

- [ ] **Step 4: Run whitespace check**

Run:

```bash
git diff --check
```

Expected: no whitespace errors.

## Task 10: Completion Documentation After Implementation

**Files:**

- Modify: `doc/04-implementation/backlog.md`
- Modify: `doc/04-implementation/acceptance-criteria.md`
- Modify: `doc/05-project-log/2026-06.md`
- Modify: `doc/05-project-log/decisions.md` if implementation changes any confirmed architecture decision

- [ ] **Step 1: Update backlog only after tests pass**

Set V2-100F status to `DONE` only after Task 9 passes. Update Phase 10 count from `5 / 6` to `6 / 6`. Keep V2-090F golden sample state separate; it may remain REVIEW_REQUIRED / BLOCKED unless the real rerun produces a review-approved closeout candidate.

- [ ] **Step 2: Update acceptance criteria**

Check AC-V2-REWORK-006 and Phase 10 V2-100F checkbox only after evidence shows:

- unknown assertion does not raw crash;
- raw assertion is preserved;
- direct RunManifest behavioral probe execution is disabled;
- V2-100F rework-entry does not import/call `run_v2_100_rework_loop_for_request`;
- V2-100F does not depend on `v2_100_resettable_fixture.py`, `build_current_run_provider_recheck_input()` or `_write_minimal_package()`;
- verify-blackbox ticket creation is consumed by real TicketGraph reducer/projection and visible in ready queue;
- BlackboxVerificationPlan requires provider attempt and ExecutionPackage lineage;
- runner executes only approved plan actions;
- missing plan/provider/config routes to typed blocked/escalated context;
- accepted blocker refs equal the current ReworkRequest blocker refs;
- stub/empty-change worker output cannot satisfy evidence;
- rework issue uses `RUN_MANIFEST_ERROR`, not active `RUN_MANIFEST_MISMATCH`.

- [ ] **Step 3: Append project log entry**

Record:

- changed files;
- focused test commands and results;
- real provider opt-in command/result if executed;
- generated audit/export paths;
- whether V2-090F moved from raw exception to `rework_required` or `blocked_or_escalated`.

## Self-Review Checklist

- [ ] Spec coverage: V2-100F required negative and happy paths map to Tasks 1-9.
- [ ] No hidden second source of truth: framework preserves raw context and validates lineage; it does not interpret manifest domain or decide blackbox semantics.
- [ ] No hardcoded alias loop: unknown assertion types are preserved, not converted through expanding enum aliases.
- [ ] CEO governance preserved: `verify-blackbox` ticket creation and seat assignment are graph/governance-controlled.
- [ ] Runtime bounded: runner executes approved plan actions only and records facts.
- [ ] Evidence first: plan/prose cannot satisfy closeout without real execution facts.
- [ ] Rework routing coarse: new artifacts use `RUN_MANIFEST_ERROR`; `RUN_MANIFEST_MISMATCH` remains deprecated compatibility only.
- [ ] Future roadmap compatibility: hook request includes `milestone_ref` and does not assume a single global closeout stage.
