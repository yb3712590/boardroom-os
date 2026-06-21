# V2-100F Native Rework Orchestration For Manifest Verification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development（子智能体驱动开发，推荐）or superpowers:executing-plans（按计划执行）to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 重写 V2-100F，把 RunManifest tolerant ingestion（运行清单宽容摄取）、verify-blackbox ticket（黑盒验证工单）、BlackboxVerificationPlan（黑盒验证计划）、runner facts（运行事实）和 ReworkCycle（返工循环）接入原生 TicketGraph / SeatAssignmentGraph / ExecutionPackage / ProviderAttempt / reducer（工单图 / 席位派工图 / 执行包 / 模型调用尝试记录 / 归约器）编排链路。

**Architecture:** V2-100F 不再以 helper hook（辅助钩子）作为主路径。unknown assertion（未知断言）只变成 raw manifest context（原始运行清单上下文）；CEO（项目经理）通过治理命令创建 first-class `verify-blackbox` ticket（黑盒验证一等工单），TicketGraphProjector（工单图投影器）和 SeatAssignmentProjector（席位派工投影器）决定 ready queue（就绪队列）与被派工 AgentSeat（智能体席位），ExecutionPackageCompiler（执行包编译器）编译上下文，provider-backed AgentSeat 产出 BlackboxVerificationPlan，runner 只执行 approved plan（已批准计划）并记录事实，EvidenceVerifier / Checker / CloseoutGate（证据验证器 / 检查者 / 收尾门禁）决定 `passed` / `rework_required` / `blocked_or_escalated`，需要返工时进入既有 REWORK_* reducer（返工归约）事件链。

**Tech Stack:** Python 3.11+、Pydantic v2、pytest、现有 Boardroom OS V2 EventRecord（事件记录）、TicketGraph（工单图）、SeatAssignmentGraph（席位派工图）、ExecutionPackage（执行包）、ProviderAttempt（模型调用尝试记录）、CommandRunner / ServiceRunner（命令 / 服务运行器）、EvidenceVerifier（证据验证器）、CheckerVerdict（检查结论）、CloseoutGate（收尾门禁）和 ReworkReducer（返工归约器）。

---

## Supersession

本文件取代此前 V2-100F implementation plan（实施计划）。

旧计划的根本问题不是缺少 P0 guardrail（架构护栏），而是主线仍像“RunManifest 摄取后调用 verification hook helper（验证钩子辅助器）”。这会让测试通过倾向于证明一个外接路径可用，而不是证明返工能力已被原生编排吸收。

新计划把 V2-100F 拆成 V2-100F-A ~ V2-100F-F 六个明确边界的子批次。顺序不可倒置：必须先推进 native orchestration（原生编排）接入，再验证 provider-backed rework capability（模型供应商支撑返工能力）。

## Non-negotiable Native Orchestration Gates

- `verify-blackbox` 必须是 TicketGraph（工单图）中的 `TicketNode`（工单节点），由真实 `TICKET_CREATED` / `SEAT_ASSIGNED` events（事件）投影进入 ready queue；不得由 helper 直接返回“已派工”。
- `verify-blackbox` 的 owner（执行者）必须来自 SeatAssignmentGraph（席位派工图）和 active AgentTeamProjection（智能体团队投影）；不得在 verification helper（验证辅助器）里硬编码 Tester（测试者）或 seat ref（席位引用）。
- BlackboxVerificationPlan（黑盒验证计划）必须来自 graph-assigned AgentSeat（图派工席位）的 ExecutionPackage（执行包）和 ProviderAttempt（模型调用尝试记录）；缺任一来源链都 fail closed（失败关闭）。
- Runner（运行器）只执行 approved plan actions（已批准计划动作），不得从 RunManifest（运行清单）、domain strings（领域字符串）或 default endpoints（默认端点）生成业务验证动作。
- HTTP / browser / tool facts（HTTP / 浏览器 / 工具事实）必须是一等事实模型。缺 executor（执行器）或 policy（策略）时返回 `blocked_or_escalated`，不得改写成 `rework_required`。
- EvidenceVerifier / Checker / CloseoutGate 是唯一证据和收尾权威；V2-100F 不新增第二套 verifier/checker/closeout（验证器 / 检查者 / 收尾）。
- `RUN_MANIFEST_ERROR` 是 coarse routing code（粗粒度路由码）。advisory labels（参考标签）、agent interpretation summary（智能体解释摘要）或 prose（散文）不得直接通过门禁。
- V2-100F active path（活跃路径）不得 import / call `run_v2_100_rework_loop_for_request()`、`build_v2_100_resettable_fixture()`、`build_current_run_provider_recheck_input()`、`_write_minimal_package()`，不得读取 `examples/generated-workspaces/tiny-fullstack/30-audit/v2-090k-failure-snapshot/`。
- Completion proof（完成证明）必须包含真实 provider opt-in（显式启用模型供应商）通过；本地 unit tests（单元测试）通过不构成 V2-100F 完成。

## Real Provider Configuration Paths

真实 provider proof（模型供应商证明）必须直接使用以下路径，不允许由 example config（示例配置）或隐式环境覆盖替代：

- Runtime config（运行时配置）：`config/boardroom-runtime.v2-090f.yaml`
- Provider config（供应商配置）：`config/boardroom-providers.v2-090f.yaml`
- Role config（角色配置）：`config/boardroom-roles.v2-090f.yaml`
- Local secret env（本机密钥环境文件）：`.env`
- V2-100F proof env（本批次证明环境文件，gitignored）：`.tmp/v2-100f-real-provider.env`

`.tmp/v2-100f-real-provider.env` 必须声明：

```bash
BOARDROOM_RUNTIME_CONFIG=config/boardroom-runtime.v2-090f.yaml
BOARDROOM_PROVIDERS_CONFIG=config/boardroom-providers.v2-090f.yaml
BOARDROOM_ROLES_CONFIG=config/boardroom-roles.v2-090f.yaml
BOARDROOM_ATOMIC_AGENT_PATH=../atomic-agent
BOARDROOM_EVIDENCE_ROOT=.evidence
BOARDROOM_RUN_REAL_PROVIDER_PROVING=1
BOARDROOM_RUN_REAL_PROVIDER_TESTS=1
```

`OPENAI_API_KEY` 或兼容 provider secret（供应商密钥）只能来自 `.env`、shell secret store（本机密钥存储）或 `.tmp/v2-100f-real-provider.env` 的本机未提交值；不得写入 tracked docs（受版本控制文档）或 committed config（提交配置）。

---

## File Structure

Create:

- `src/boardroom_os/workspace/run_manifest_ingestion.py` — RunManifestRawAssertion（运行清单原始断言）、RunManifestSkeletonSummary（运行清单骨架摘要）、RunManifestIngestionContext（运行清单摄取上下文）。
- `src/boardroom_os/orchestration/verification.py` — VerificationMilestoneRequest（验证里程碑请求）、VerifyBlackboxTicketIntent（黑盒验证工单意图）、VerificationOutcomeProjection（验证结果投影）；只封装原生事件输入输出，不绕过 projector（投影器）。
- `src/boardroom_os/evidence/blackbox_plan.py` — BlackboxVerificationPlan（黑盒验证计划）、BlackboxPlanAction（黑盒计划动作）、BlackboxPlanApproval（黑盒计划批准）和 lineage validator（来源链校验器）。
- `src/boardroom_os/execution/blackbox_plan_runner.py` — approved action runner（已批准动作运行器）和 BlackboxActionExecutionFact（黑盒动作执行事实），内部调用现有 CommandRunner / ServiceRunner（命令 / 服务运行器）或显式阻断缺失 executor。
- `src/boardroom_os/proving/v2_100f_native_manifest_rework.py` — V2-100F proving harness（证明薄层），只驱动原生组件，不创建替代状态。
- `scripts/run_v2_100f_native_manifest_rework.py` — 真实 provider opt-in CLI（显式启用命令行）。

Modify:

- `src/boardroom_os/events/types.py` — 仅在现有事件不足以表达一等验证事实时扩展 event taxonomy（事件分类）；优先复用 `TICKET_CREATED`、`SEAT_ASSIGNED`、`EXECUTION_STARTED`、`PROVIDER_ATTEMPT_RECORDED`、`WORK_PRODUCT_SUBMITTED`、`COMMAND_RUN_RECORDED`、`REWORK_REQUESTED`。
- `src/boardroom_os/graph/projection.py` — 确保 `verify-blackbox` 作为普通 ticket 通过 TicketGraphProjector（工单图投影器）进入 graph。
- `src/boardroom_os/graph/seat_assignment.py` — 确保 verification seat demand（验证席位需求）按 capability tags（能力标签）匹配 active AgentSeat。
- `src/boardroom_os/execution/compiler.py` — 将 raw manifest context refs（原始运行清单上下文引用）、PackageContract、AcceptanceContract、project docs（项目文档）、source refs（源码引用）和 observed failures（已观察失败）编入 `verify-blackbox` ExecutionPackage。
- `src/boardroom_os/evidence/live_blackbox.py` — 给真实黑盒事实增加 plan/action lineage（计划 / 动作来源链）或改为消费 `BlackboxActionExecutionFact`。
- `src/boardroom_os/evidence/verifier.py` — live blackbox evidence（真实黑盒证据）必须绑定 approved BlackboxVerificationPlan 和 execution facts。
- `src/boardroom_os/checker/checker.py`、`src/boardroom_os/checker/verdict.py`、`src/boardroom_os/closeout/gate.py` — 只消费 verified evidence（已验证证据）和 typed blockers（类型化阻断项），不消费 plan prose。
- `src/boardroom_os/rework/model.py` — 新增 active `ReworkIssueCode.RUN_MANIFEST_ERROR = "run_manifest_error"`；保留 `RUN_MANIFEST_MISMATCH` 为 deprecated read-only legacy code（只读遗留代码）。
- `src/boardroom_os/rework/blocker_projection.py`、`src/boardroom_os/rework/ticket_graph_patch.py`、`src/boardroom_os/reducers/rework.py` — 将 manifest / plan / fact failure（运行清单 / 计划 / 事实失败）接入现有 ReworkRequest / ReworkPlan / TicketGraphPatch / ReworkProjection 链。
- `src/boardroom_os/proving/v2_090f_prd_agent_team.py`、`src/boardroom_os/proving/v2_090f_rework_entry.py`、`scripts/run_v2_090f_prd_agent_team.py` — 移除 raw assertion crash（原始断言崩溃）作为控制流；改为调用原生 V2-100F verification/rework 编排。
- `src/boardroom_os/agents/prompt_templates/baseline/v1/tester.md`、`worker.md`、`release_devops.md`、`checker.md`、`closeout.md` — 明确 RunManifest 是 context / commitment（上下文 / 承诺），BlackboxVerificationPlan 和 evidence gates（证据门禁）才是可执行/可判定边界。
- `src/boardroom_os/workspace/__init__.py`、`src/boardroom_os/evidence/__init__.py`、`src/boardroom_os/execution/__init__.py`、`src/boardroom_os/rework/__init__.py` — 导出新增 public API（公开接口）。

Tests:

- `tests/workspace/test_run_manifest_tolerant_ingestion.py`
- `tests/negative/test_manifest_tolerant_ingestion_fail_closed.py`
- `tests/orchestration/test_verify_blackbox_native_ticket.py`
- `tests/negative/test_verify_blackbox_orchestration_fail_closed.py`
- `tests/evidence/test_blackbox_verification_plan.py`
- `tests/negative/test_blackbox_plan_fail_closed.py`
- `tests/execution/test_blackbox_plan_runner.py`
- `tests/negative/test_blackbox_plan_runner_fail_closed.py`
- `tests/rework/test_manifest_rework_routing.py`
- `tests/negative/test_manifest_rework_routing_fail_closed.py`
- `tests/proving/test_v2_100f_native_orchestration.py`
- `tests/proving/test_v2_100f_real_provider_orchestration.py`
- Update `tests/proving/test_v2_090f_rework_entry_validation.py`
- Update `tests/negative/test_v2_090f_rework_entry_fail_closed.py`
- Update `tests/negative/test_v2_100_rework_loop_fail_closed.py`

Docs:

- Modify `doc/04-implementation/INDEX.md`
- Modify `doc/04-implementation/backlog.md`
- Modify `doc/05-project-log/decisions.md`
- Modify `doc/05-project-log/2026-06.md`

---

## V2-100F-A: Tolerant Manifest Context, Not Evidence

**Goal:** unknown RunManifest assertion vocabulary（未知运行清单断言词汇）不 raw crash、不通过、不消失，只形成 raw context（原始上下文）。

**Files:**

- Create: `src/boardroom_os/workspace/run_manifest_ingestion.py`
- Modify: `src/boardroom_os/workspace/run_manifest.py`
- Modify: `src/boardroom_os/proving/v2_090f_prd_agent_team.py`
- Test: `tests/workspace/test_run_manifest_tolerant_ingestion.py`
- Test: `tests/negative/test_manifest_tolerant_ingestion_fail_closed.py`

- [ ] **Step A1: Write negative tests for raw assertion behavior**

Add tests proving:

```python
def test_unknown_assertion_is_preserved_without_raw_crash():
    context = ingest_run_manifest_artifact(
        artifact=manifest_with_assertion(
            {"type": "json_array_contains_field", "path": "$", "field": "title"}
        ),
        source_ref="00-boardroom/generated-run-manifest.json",
        raw_manifest_ref="artifact.run_manifest.generated",
    )

    assert context.raw_assertions[0].raw_type == "json_array_contains_field"
    assert context.raw_assertions[0].raw_payload["field"] == "title"
    assert context.skeleton_summary.behavioral_probe_ids
```

```python
def test_unknown_assertion_context_is_not_evidence():
    context = ingest_run_manifest_artifact(
        artifact=manifest_with_assertion({"type": "json_array_contains_field"}),
        source_ref="00-boardroom/generated-run-manifest.json",
        raw_manifest_ref="artifact.run_manifest.generated",
    )

    with pytest.raises(ValueError, match="raw manifest context is not verified evidence"):
        build_live_blackbox_evidence_from_manifest_context(context)
```

The fixture must be generated in the test, not read from `examples/generated-workspaces/tiny-fullstack/30-audit/v2-090k-failure-snapshot/`.

- [ ] **Step A2: Implement ingestion models**

Implement frozen Pydantic models with `extra="forbid"`:

- `RunManifestRawAssertion`
- `RunManifestSkeletonSummary`
- `RunManifestIngestionContext`

`RunManifestIngestionContext` must include:

- `source_ref`
- `raw_manifest_ref`
- `raw_manifest_sha256`
- `skeleton_summary`
- `raw_assertions`
- `ingestion_status = "context_only"`

It must not include `passed`, `verified`, `satisfied`, `evidence_ref`, or `closeout_ready` fields.

- [ ] **Step A3: Replace closed enum crash with context extraction**

Update the V2-090F RunManifest loading path so novel assertion strings are retained in `raw_assertions`. Existing typed assertion parsing can still work for known assertions, but unknown strings must not raise raw exceptions before verification orchestration.

- [ ] **Step A4: Run focused tests**

Run:

```bash
PYTHONPATH=src:. python -m pytest \
  tests/workspace/test_run_manifest_tolerant_ingestion.py \
  tests/negative/test_manifest_tolerant_ingestion_fail_closed.py \
  -q
```

Expected: all tests pass; tests prove raw context cannot satisfy evidence.

**Completion gate:** A novel assertion such as `json_array_contains_field` reaches typed `RunManifestIngestionContext` and cannot be used as evidence or a closeout success claim.

---

## V2-100F-B: Verify-blackbox As First-class Ticket

**Goal:** `verify-blackbox` 进入 native TicketGraph / SeatAssignmentGraph（原生工单图 / 席位派工图），不是外接 hook。

**Files:**

- Create: `src/boardroom_os/orchestration/verification.py`
- Modify: `src/boardroom_os/events/types.py`
- Modify: `src/boardroom_os/graph/projection.py`
- Modify: `src/boardroom_os/graph/seat_assignment.py`
- Modify: `src/boardroom_os/execution/compiler.py`
- Test: `tests/orchestration/test_verify_blackbox_native_ticket.py`
- Test: `tests/negative/test_verify_blackbox_orchestration_fail_closed.py`

- [x] **Step B1: Write native graph tests**

Add tests proving:

```python
def test_verify_blackbox_ticket_enters_ready_queue_through_ticket_graph():
    events, resolver = build_events_with_verify_blackbox_ticket()

    ticket_graph = TicketGraphProjector(payload_resolver=resolver).project(events)

    assert TicketId(value="ticket.verify-blackbox.generated") in ticket_graph.ready_queue
    assert ticket_graph.nodes[TicketId(value="ticket.verify-blackbox.generated")].purpose == "verify-blackbox"
```

```python
def test_verify_blackbox_requires_real_seat_assignment():
    events, resolver, seat_projection = build_events_without_matching_verification_seat()

    assignment_graph = SeatAssignmentProjector(
        ticket_projector=TicketGraphProjector(payload_resolver=resolver),
        payload_resolver=resolver,
        seat_projection=seat_projection,
    ).project(events)

    assert TicketId(value="ticket.verify-blackbox.generated") not in assignment_graph.ready_queue
    assert "missing seat assignment" in assignment_graph.seat_blockers[
        TicketId(value="ticket.verify-blackbox.generated")
    ][0]
```

- [x] **Step B2: Implement verification orchestration payloads**

`VerifyBlackboxTicketIntent` must require:

- raw manifest context ref;
- active AcceptanceContract refs;
- PackageContract ref;
- source surface refs;
- evidence obligation refs;
- allowed read refs for project docs, RunManifest, PackageContract, AcceptanceContract and observed failures;
- empty allowed write set unless a later rework ticket explicitly grants writes.

The intent builder must return a `TicketCreatedPayload`, not a custom ready queue item.

- [x] **Step B3: Compile ExecutionPackage from graph assignment**

Extend `ExecutionPackageCompiler` so a ready `verify-blackbox` ticket receives:

- raw RunManifest context ref;
- skeleton summary ref;
- PackageContract and AcceptanceContract refs;
- generated docs refs such as README / RUNBOOK / API docs when present;
- relevant source surface refs;
- observed failure refs, including raw run errors.

The compiler must reject `verify-blackbox` if the ticket was not present in `SeatAssignmentGraph.ready_queue`.
It must also reject any verification context ref that is not already declared by the ticket `allowed_read_refs`, and must enforce `RoleCategory.VERIFICATION` plus `task.verify-blackbox` capability rather than trusting the purpose string alone.

- [x] **Step B4: Run graph and compiler tests**

Run:

```bash
PYTHONPATH=src:. python -m pytest \
  tests/orchestration/test_verify_blackbox_native_ticket.py \
  tests/negative/test_verify_blackbox_orchestration_fail_closed.py \
  tests/execution/test_execution_package_compiler.py \
  tests/negative/test_execution_package_compiler_fail_closed.py \
  -q
```

Expected: `verify-blackbox` is a normal graph node; missing graph, seat, contract, context or queue membership fails.

**Completion gate:** The only path from raw manifest context to `verify-blackbox` execution is `TICKET_CREATED -> SEAT_ASSIGNED -> SeatAssignmentGraph.ready_queue -> ExecutionPackageCompiler -> AgentContextSnapshot -> ProviderExecutor`, with no verification context expansion outside ticket `allowed_read_refs`, no non-verification SeatDemand accepted for `verify-blackbox`, and no empty `allowed_write_set` package accepted unless the package is a read-only verification package whose `context_refs` are covered by `allowed_read_refs`.

---

## V2-100F-C: Provider-backed BlackboxVerificationPlan

**Goal:** BlackboxVerificationPlan（黑盒验证计划）由被派工 AgentSeat 通过真实 ProviderAttempt 产出，并绑定 ExecutionPackage / role hook / active contract lineage（执行包 / 角色提示词钩子 / 活跃合同来源链）。

**Files:**

- Create: `src/boardroom_os/evidence/blackbox_plan.py`
- Modify: `src/boardroom_os/providers/attempt.py`
- Modify: `src/boardroom_os/execution/work_product.py`
- Modify: `src/boardroom_os/evidence/verifier.py`
- Test: `tests/evidence/test_blackbox_verification_plan.py`
- Test: `tests/negative/test_blackbox_plan_fail_closed.py`

- [ ] **Step C1: Write lineage negative tests**

Add tests proving:

```python
def test_blackbox_plan_requires_provider_attempt_for_assigned_execution_package():
    package = build_verify_blackbox_execution_package(seat_ref="seat.tester.integration")
    plan = build_blackbox_plan(
        execution_package_ref=package.execution_package_id,
        producer_attempt_ref="provider-attempt.missing",
        producer_seat_ref=package.seat_ref,
    )

    with pytest.raises(ValueError, match="provider attempt could not be resolved"):
        validate_blackbox_plan_lineage(plan, execution_package=package, provider_attempts=())
```

```python
def test_blackbox_plan_wrong_seat_fails():
    package = build_verify_blackbox_execution_package(seat_ref="seat.tester.integration")
    attempt = build_provider_attempt(input_package_ref=package.execution_package_id)
    plan = build_blackbox_plan(
        execution_package_ref=package.execution_package_id,
        producer_attempt_ref=attempt.provider_attempt_id,
        producer_seat_ref="seat.worker.implementation",
    )

    with pytest.raises(ValueError, match="producer seat must match execution package"):
        validate_blackbox_plan_lineage(plan, execution_package=package, provider_attempts=(attempt,))
```

- [ ] **Step C2: Implement plan schema**

`BlackboxVerificationPlan` must include:

- `plan_id`
- `execution_package_ref`
- `producer_attempt_ref`
- `producer_seat_ref`
- `role_prompt_hook_ref`
- `objective`
- `input_context_refs`
- `run_manifest_context_ref`
- `acceptance_refs`
- `package_contract_ref`
- `actions`
- `evidence_obligation_refs`
- `created_at`

`BlackboxPlanAction` must support `command`, `http`, `browser`, `tool`, and `file_read` kinds, but execution is allowed only when a matching executor exists.

- [ ] **Step C3: Implement lineage validator**

Validation must check:

- ProviderAttempt exists and is not fallback evidence;
- ProviderAttempt.input_package_ref equals plan.execution_package_ref;
- ProviderAttempt.role hook snapshot matches ExecutionPackage.role_prompt_hook;
- plan.producer_seat_ref equals ExecutionPackage.seat_ref;
- plan.acceptance_refs are active acceptance refs from the package;
- every action has acceptance refs, expected observations and required permissions;
- plan cannot contain `passed`, `approved`, `closeout_ready` or equivalent success claims.

- [ ] **Step C4: Run plan tests**

Run:

```bash
PYTHONPATH=src:. python -m pytest \
  tests/evidence/test_blackbox_verification_plan.py \
  tests/negative/test_blackbox_plan_fail_closed.py \
  tests/evidence/test_evidence_verifier.py \
  tests/negative/test_synthetic_evidence_rejected.py \
  -q
```

Expected: provider-backed assigned AgentSeat plan is valid; missing attempt, wrong seat, fallback attempt, stale package, stale hook or prose-only output fails.

**Completion gate:** A BlackboxVerificationPlan can only enter execution when it is a provider-backed work product of the graph-assigned AgentSeat for the `verify-blackbox` ExecutionPackage.

---

## V2-100F-D: Plan Runner Through Authoritative Facts

**Goal:** approved plan actions（已批准计划动作）通过权威 runner（运行器）记录 facts（事实）；缺 executor 时显式 `blocked_or_escalated`。

**Files:**

- Create: `src/boardroom_os/execution/blackbox_plan_runner.py`
- Modify: `src/boardroom_os/execution/verification_run.py`
- Modify: `src/boardroom_os/evidence/live_blackbox.py`
- Modify: `src/boardroom_os/evidence/claim.py`
- Modify: `src/boardroom_os/evidence/verifier.py`
- Test: `tests/execution/test_blackbox_plan_runner.py`
- Test: `tests/negative/test_blackbox_plan_runner_fail_closed.py`

- [ ] **Step D1: Write runner fail-closed tests**

Add tests proving:

```python
def test_runner_rejects_missing_approved_plan():
    with pytest.raises(ValueError, match="approved BlackboxVerificationPlan is required"):
        BlackboxPlanRunner().run(build_runner_input(plan=None))
```

```python
def test_runner_rejects_action_not_in_plan():
    plan = build_plan(actions=(command_action("action.test"),))

    with pytest.raises(ValueError, match="action is not approved by plan"):
        BlackboxPlanRunner().run_action(plan=plan, action_id="action.extra")
```

```python
def test_http_action_without_executor_routes_blocked_or_escalated():
    result = BlackboxPlanRunner(http_executor=None).run(
        build_runner_input(plan=build_plan(actions=(http_action("action.http"),)))
    )

    assert result.status == "blocked_or_escalated"
    assert result.blocked_reason_code == "executor_missing"
```

- [ ] **Step D2: Implement action facts**

`BlackboxActionExecutionFact` must record:

- `fact_id`
- `plan_ref`
- `action_id`
- `action_kind`
- input refs and hashes;
- command / URL / browser target / tool name;
- stdout/stderr/status/body/screenshot/artifact refs when applicable;
- exit code or HTTP status when applicable;
- started/finished timezone-aware timestamps;
- acceptance refs and package contract ref claimed by the plan.

- [ ] **Step D3: Route command actions through existing runner**

Command actions must use existing CommandRunner / VerificationRun（命令运行器 / 验证运行） path. A command action fact may wrap a VerificationRun ref, but must not duplicate command success semantics.

- [ ] **Step D4: Route non-command actions explicitly**

HTTP, browser and tool actions require explicit executors. When an executor is not configured, return `blocked_or_escalated` with a typed reason. Do not call that `rework_required`, because the framework lacks trustworthy execution facts.

- [ ] **Step D5: Run runner tests**

Run:

```bash
PYTHONPATH=src:. python -m pytest \
  tests/execution/test_blackbox_plan_runner.py \
  tests/negative/test_blackbox_plan_runner_fail_closed.py \
  tests/execution/test_command_runner.py \
  tests/evidence/test_live_blackbox_evidence.py \
  tests/negative/test_live_blackbox_integration_fail_closed.py \
  -q
```

Expected: approved command actions produce real VerificationRun-backed facts; plan-less, out-of-plan, unconfigured HTTP/browser/tool paths fail closed or block/escalate.

**Completion gate:** Runner output is facts only. It cannot create ReworkRequest, mark behavior passed, or produce closeout candidate.

---

## V2-100F-E: Rework Routing And Evidence Reintegration

**Goal:** plan/facts/evidence（计划 / 事实 / 证据）进入现有 EvidenceVerifier / Checker / CloseoutGate / ReworkReducer（证据验证器 / 检查者 / 收尾门禁 / 返工归约器），不复制第二套判断链。

**Files:**

- Modify: `src/boardroom_os/evidence/verifier.py`
- Modify: `src/boardroom_os/checker/checker.py`
- Modify: `src/boardroom_os/checker/verdict.py`
- Modify: `src/boardroom_os/closeout/gate.py`
- Modify: `src/boardroom_os/rework/model.py`
- Modify: `src/boardroom_os/rework/blocker_projection.py`
- Modify: `src/boardroom_os/rework/ticket_graph_patch.py`
- Modify: `src/boardroom_os/reducers/rework.py`
- Test: `tests/rework/test_manifest_rework_routing.py`
- Test: `tests/negative/test_manifest_rework_routing_fail_closed.py`

- [ ] **Step E1: Write routing tests**

Add tests proving:

```python
def test_manifest_drift_projects_to_run_manifest_error_rework_issue():
    facts = build_failed_blackbox_facts(
        observed={"path": "/ready", "status": 404},
        plan_labels=("readiness path differs from run manifest",),
    )

    request = project_blackbox_failure_to_rework_request(
        facts=facts,
        active_contract=active_contract(),
        package_contract=package_contract(),
    )

    assert request.issues[0].issue_code.value == "run_manifest_error"
    assert request.issues[0].advisory_context["observed"]["status"] == 404
```

```python
def test_advisory_label_cannot_mark_passed():
    facts = build_failed_blackbox_facts(
        observed={"status": 500},
        plan_labels=("probably acceptable",),
    )

    with pytest.raises(ValueError, match="advisory labels cannot satisfy evidence"):
        build_verified_evidence_from_advisory_labels(facts)
```

- [ ] **Step E2: Add RUN_MANIFEST_ERROR**

Add active `RUN_MANIFEST_ERROR` and migrate new code/tests to it. `RUN_MANIFEST_MISMATCH` can remain for reading existing historical artifacts only; new V2-100F artifacts must not emit it.

- [ ] **Step E3: Reuse existing verifier/checker/closeout**

EvidenceVerifier must validate plan/fact lineage before producing verified live blackbox evidence. Checker and CloseoutGate must consume verified evidence and typed blockers only. Plan prose, labels, summaries and raw assertion fragments are advisory context, not proof.

- [ ] **Step E4: Convert trustworthy failures to REWORK_REQUESTED**

When facts exist and evidence/checker/closeout produces a verified blocker, route to `rework_required` by emitting a real `REWORK_REQUESTED` event and consuming it through `ReworkReducer`. The reducer must project blocker refs, checked refs and graph version. Raw exception alone must route to `blocked_or_escalated`.

- [ ] **Step E5: Run routing tests**

Run:

```bash
PYTHONPATH=src:. python -m pytest \
  tests/rework/test_manifest_rework_routing.py \
  tests/negative/test_manifest_rework_routing_fail_closed.py \
  tests/reducers/test_rework_reducer.py \
  tests/negative/test_rework_reducer_fail_closed.py \
  tests/closeout/test_closeout_gate.py \
  tests/negative/test_closeout_fail_closed.py \
  -q
```

Expected: `RUN_MANIFEST_ERROR` routes to verified ReworkRequest only when trustworthy facts and active contract refs exist; missing graph, missing plan, missing facts, unsafe execution or missing provider/config routes to `blocked_or_escalated`.

**Completion gate:** V2-100F uses the same EvidenceVerifier / Checker / CloseoutGate / ReworkReducer chain as the rest of V2; no V2-100F-only closeout or acceptance shortcut exists.

---

## V2-100F-F: Native End-to-end Proof With Real Provider

**Goal:** prove（证明）真实 V2-090F rerun no longer stops at raw assertion crash; it reaches native `verify-blackbox` orchestration and then `passed` / `rework_required` / typed `blocked_or_escalated`.

**Files:**

- Create: `src/boardroom_os/proving/v2_100f_native_manifest_rework.py`
- Create: `scripts/run_v2_100f_native_manifest_rework.py`
- Test: `tests/proving/test_v2_100f_native_orchestration.py`
- Test: `tests/proving/test_v2_100f_real_provider_orchestration.py`
- Modify: `src/boardroom_os/proving/v2_090f_rework_entry.py`
- Modify: `scripts/run_v2_090f_prd_agent_team.py`

- [ ] **Step F1: Write local orchestration proof tests**

Add tests proving the full local projection chain:

```python
def test_v2_100f_native_orchestration_projects_graph_plan_facts_and_rework():
    result = run_v2_100f_native_manifest_rework(
        input=build_local_provider_backed_fixture_with_novel_assertion(),
        require_real_provider=False,
    )

    assert result.terminal_status in {"rework_required", "blocked_or_escalated", "passed"}
    assert result.verify_blackbox_ticket_ref == "ticket.verify-blackbox.generated"
    assert result.before_graph_ref
    assert result.execution_package_ref
    assert result.blackbox_plan_ref
    assert result.fact_refs
```

The local fixture may use deterministic provider records only when they are explicitly marked as test fixtures and cannot satisfy implementation evidence. Real completion still depends on Step F4.

- [ ] **Step F2: Add forbidden dependency tests**

Add tests or static guards proving V2-100F active path does not import or read forbidden V2-100E shortcuts:

```bash
rg -n "run_v2_100_rework_loop_for_request|build_v2_100_resettable_fixture|build_current_run_provider_recheck_input|_write_minimal_package|v2-090k-failure-snapshot" \
  src/boardroom_os/proving/v2_100f_native_manifest_rework.py \
  src/boardroom_os/orchestration \
  tests/proving/test_v2_100f_native_orchestration.py
```

Expected: no matches.

- [ ] **Step F3: Implement proving harness as a driver only**

`run_v2_100f_native_manifest_rework()` may:

- load generated V2-090F artifacts;
- call `ingest_run_manifest_artifact()`;
- append native ticket / seat / execution / provider / work product / command fact events;
- call existing projectors, compiler, provider adapter, runner, verifier, checker, closeout and rework reducer;
- export audit refs.

It must not:

- create ready queue entries directly;
- create ProviderAttempt without the configured provider adapter;
- synthesize accepted evidence;
- write ReworkPlan or TicketGraphPatch outside the existing governance path;
- convert `rework_required` to `passed`.

- [ ] **Step F4: Add real provider opt-in test**

Create `tests/proving/test_v2_100f_real_provider_orchestration.py` with `pytest.mark.skipif` requiring:

```python
os.environ.get("BOARDROOM_RUN_REAL_PROVIDER_TESTS") == "1"
os.environ.get("BOARDROOM_RUN_REAL_PROVIDER_PROVING") == "1"
os.environ.get("OPENAI_API_KEY")
os.environ.get("BOARDROOM_RUNTIME_CONFIG") == "config/boardroom-runtime.v2-090f.yaml"
os.environ.get("BOARDROOM_PROVIDERS_CONFIG") == "config/boardroom-providers.v2-090f.yaml"
os.environ.get("BOARDROOM_ROLES_CONFIG") == "config/boardroom-roles.v2-090f.yaml"
```

The test must assert:

- raw `json_array_contains_field` does not raw crash ingestion;
- `verify-blackbox` ticket appears in TicketGraph ready queue before execution;
- SeatAssignmentGraph assigns an active AgentSeat;
- ExecutionPackage includes raw manifest context, contracts, docs and source refs;
- ProviderAttempt exists for the assigned seat and plan;
- BlackboxVerificationPlan has approved actions;
- runner records at least one real command fact or a typed `blocked_or_escalated` reason for missing HTTP/browser executor;
- EvidenceVerifier / Checker / CloseoutGate or ReworkReducer produces terminal `passed`, `rework_required`, or typed `blocked_or_escalated`.

- [ ] **Step F5: Add CLI proof**

The CLI must require an explicit env file path:

```bash
python scripts/run_v2_100f_native_manifest_rework.py \
  --prd examples/directives/tiny-fullstack-prd.md \
  --workspace-root .tmp/v2-100f-workspace \
  --output-root .tmp/v2-100f-output \
  --env .tmp/v2-100f-real-provider.env \
  --reset
```

It must print resolved config paths and terminal status. It must refuse to run if resolved config paths differ from:

- `config/boardroom-runtime.v2-090f.yaml`
- `config/boardroom-providers.v2-090f.yaml`
- `config/boardroom-roles.v2-090f.yaml`

- [ ] **Step F6: Run local verification**

Run:

```bash
PYTHONPATH=src:. python -m pytest \
  tests/workspace/test_run_manifest_tolerant_ingestion.py \
  tests/orchestration/test_verify_blackbox_native_ticket.py \
  tests/evidence/test_blackbox_verification_plan.py \
  tests/execution/test_blackbox_plan_runner.py \
  tests/rework/test_manifest_rework_routing.py \
  tests/proving/test_v2_100f_native_orchestration.py \
  tests/negative/test_manifest_tolerant_ingestion_fail_closed.py \
  tests/negative/test_verify_blackbox_orchestration_fail_closed.py \
  tests/negative/test_blackbox_plan_fail_closed.py \
  tests/negative/test_blackbox_plan_runner_fail_closed.py \
  tests/negative/test_manifest_rework_routing_fail_closed.py \
  -q
```

Expected: all pass.

- [ ] **Step F7: Run real provider proof**

Run:

```bash
set -a
source .env
source .tmp/v2-100f-real-provider.env
set +a
PYTHONPATH=src:. python -m pytest \
  tests/proving/test_v2_100f_real_provider_orchestration.py \
  -q -s
```

Expected: test is not skipped; terminal status is `passed`, `rework_required`, or typed `blocked_or_escalated`; no raw `unsupported RunManifest behavior assertion type` exception appears.

- [ ] **Step F8: Run regression and static guards**

Run:

```bash
PYTHONPATH=src:. python -m pytest \
  tests/reducers \
  tests/execution \
  tests/evidence \
  tests/closeout \
  tests/rework \
  tests/negative \
  -q
```

Run:

```bash
rg -n "RUN_MANIFEST_MISMATCH|run_manifest_mismatch" \
  src/boardroom_os tests \
  --glob '!src/boardroom_os/rework/model.py' \
  --glob '!tests/rework/test_rework_model.py'
```

Expected: pytest passes; `rg` finds no new active routing usage outside legacy compatibility tests.

Run:

```bash
git diff --check
```

Expected: no whitespace errors.

**Completion gate:** V2-100F is complete only when local tests and real provider opt-in proof pass with the V2-090F config paths above, and the exported audit shows native graph projection, seat assignment, ExecutionPackage, ProviderAttempt, BlackboxVerificationPlan, runner facts and evidence/rework routing.

---

## Commit Sequence

Use small commits after each sub-batch passes focused verification:

```bash
git commit -m "feat(v2-100f): 接入运行清单宽容摄取"
git commit -m "feat(v2-100f): 原生编排黑盒验证工单"
git commit -m "feat(v2-100f): 绑定黑盒验证计划来源链"
git commit -m "feat(v2-100f): 记录黑盒计划执行事实"
git commit -m "feat(v2-100f): 接回运行清单返工路由"
git commit -m "test(v2-100f): 验证真实供应商端到端链路"
```

## Self-review Checklist

- [ ] Every V2-100F spec requirement maps to V2-100F-A ~ F.
- [ ] No task depends on V2-100E proving orchestration, resettable fixture, minimal package stub or historical accepted audit export.
- [ ] `verify-blackbox` is created, assigned and compiled through native graph/projection/compiler APIs.
- [ ] BlackboxVerificationPlan is provider-backed and graph-assigned.
- [ ] Runner cannot invent actions or convert facts into passed evidence.
- [ ] Missing provider/config/executor routes to `blocked_or_escalated`, not silent fallback.
- [ ] `RUN_MANIFEST_ERROR` is the only new active manifest routing code.
- [ ] Completion proof uses `config/boardroom-runtime.v2-090f.yaml`, `config/boardroom-providers.v2-090f.yaml`, `config/boardroom-roles.v2-090f.yaml`, `.env` and `.tmp/v2-100f-real-provider.env`.
- [ ] V2-100F remains REVIEW_REQUIRED until code implementation and real provider proof pass.
