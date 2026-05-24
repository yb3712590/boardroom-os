# V2-070F CloseoutReducer（收尾归约器）同行评审 spec

## 1. 背景与现实场景

V2-070F 要处理的现实场景是：generated project package（生成项目包）已经完成 implementation（实施）、verification（验证）、evidence export（证据导出）、ReplayBundle（重放包）、ProcessAuditBundle（流程审计包）、GitVersionAuditBundle（Git 版本审计包）和 CloseoutPackage（收尾包）绑定；CloseoutGate（收尾门禁）也已经 passed（通过）。但系统还不能只因为 workflow completed（流程跑完）、runtime（运行时）返回了某个成功状态，或某个包文件存在，就把项目标记为 terminal success（终态成功）。

通俗地说，V2-070F 是“结案登记员”：它不重新审计证据、不重新运行测试、不重新生成收尾包；它只在看到正式治理事件 `CLOSEOUT_COMMITTED`（收尾已提交）且该事件携带的 CloseoutPackage（收尾包）确实 passed 后，把项目投影为 terminal success（终态成功）。如果只有 workflow completed（流程完成）、缺 closeout gate（收尾门禁）、缺 replay bundle（重放包），或增量 replay（增量重放）没有显式保留历史 `WORK_PRODUCT_SUBMITTED`（工作产物已提交）事实，都必须 fail closed（失败关闭）。

本轮 Pre-flight（一致性预检）结论：`backlog.md`（待办）当前未完成工作包为 V2-070F；`acceptance-criteria.md`（验收标准）Phase 7 中 “Closeout reducer 接入” 和 “V2-070A ~ V2-070F 六个工作包全部 DONE” 仍未勾选；`src/boardroom_os/reducers/closeout_reducer.py` 与 `tests/closeout/test_closeout_reducer.py` 尚不存在；V2-070E 已提供 CloseoutPackage（收尾包）typed boundary（类型化边界）。当前状态与输出文件、验收 checkbox（一致性勾选项）一致，无 drift（漂移）。

## 2. 选项背景

### 2.1 方案 A：新增 `CLOSEOUT_COMMITTED` 治理事件 + CloseoutReducer（推荐）

扩展 `EventType`（事件类型）新增 `CLOSEOUT_COMMITTED`（收尾已提交）事件；该事件不是 runtime fact（运行时事实），而是治理/收尾链路产生的 governance event（治理事件）。新增 `CloseoutReducer`（收尾归约器）消费 EventRecord（事件记录）和 typed closeout payload（类型化收尾载荷），在 gate/package/history 条件满足后产生 terminal success projection（终态成功投影）。

优点：

- 与 `TICKET_COMPLETED`（任务已完成）类似，最终状态变化通过 reducer（状态归约器）保护。
- EventLog（事件日志）中有可审计、可重放的收尾事实入口。
- 可以继续保持 `RuntimeEventBoundary`（运行时事件边界）拒绝 runtime emit（运行时发出）治理事件。
- 能直接覆盖 V2-070F 对 reducer/replay（归约器/重放）和增量历史事实保留的要求。

代价：需要扩展 `EventType`（事件类型）、新增 payload resolver（载荷解析器）协议和测试 fixture（测试夹具）。

### 2.2 方案 B：只消费 CloseoutPackage 对象，不新增事件

调用方直接把 CloseoutPackage（收尾包）交给一个函数，函数返回 terminal success projection（终态成功投影）。

优点：实现最小。

不采用原因：缺少 EventLog（事件日志）中的治理事实入口，process audit/replay（流程审计/重放）无法回答“谁在第几个 graph version（图版本）提交了收尾”。这会把 V2-070F 变成对象校验函数，而不是 reducer integration（归约器集成）。

### 2.3 方案 C：把 terminal success 放进 TicketReducer（任务归约器）

在 `TicketReducer`（任务归约器）中处理项目级 closeout（收尾）。

优点：复用已有 reducer。

不采用原因：会混淆 ticket completed（任务完成）和 project terminal success（项目终态成功）两个层级。TicketReducer（任务归约器）负责 ticket graph（任务图），CloseoutReducer（收尾归约器）负责 project closeout projection（项目收尾投影），边界应保持分离。

## 3. 选型结论

采用方案 A：新增 `CLOSEOUT_COMMITTED`（收尾已提交）治理事件 + `CloseoutReducer`（收尾归约器）。

核心边界：

1. `CloseoutReducer`（收尾归约器）是 terminal success projection（终态成功投影）的唯一写入边界。
2. `CLOSEOUT_COMMITTED`（收尾已提交）是 governance event（治理事件），不是 runtime fact（运行时事实）。
3. `RuntimeEventBoundary`（运行时事件边界）必须继续拒绝 runtime emit `CLOSEOUT_COMMITTED`。
4. `CloseoutReducer`（收尾归约器）只消费 passed CloseoutPackage（通过的收尾包）和显式历史 projection/replay input（历史投影/重放输入），不重新运行 CloseoutGate（收尾门禁）。
5. 增量模式必须显式携带历史 `WORK_PRODUCT_SUBMITTED`（工作产物已提交）事实摘要，不能依赖 `TicketReducer.reduce()` 调用内局部集合。

## 4. 目标

1. 新增 `src/boardroom_os/reducers/closeout_reducer.py`，定义 CloseoutReducer（收尾归约器）、CloseoutCommitPayload（收尾提交载荷）、CloseoutProjection（收尾投影）、CloseoutHistoryProjection（收尾历史投影）、CloseoutReducerPayloadResolver（收尾归约器载荷解析器）和 CloseoutReducerError（收尾归约器错误）。
2. 扩展 `src/boardroom_os/events/types.py` 的 `EventType`（事件类型），新增 `CLOSEOUT_COMMITTED = "closeout_committed"`。
3. 保持 `RuntimeEventBoundary.require_runtime_fact_event(...)`（运行时事实事件检查）拒绝 `CLOSEOUT_COMMITTED`。
4. 新增 `tests/closeout/test_closeout_reducer.py`，先写 negative tests（负例测试），再写 happy path（正向路径）。
5. 证明 workflow completed（流程完成）或 runtime actor（运行时参与者）不能产生 terminal success（终态成功）。
6. 证明增量 reducer/replay（增量归约/重放）输入必须显式保留历史 `WORK_PRODUCT_SUBMITTED` 事实。

## 5. 非目标

V2-070F 不做以下事情：

1. 不重新实现 CloseoutGate（收尾门禁）或 CloseoutPackage（收尾包）。
2. 不重新验证 FinalEvidenceTable（最终证据表）、SourceInventory（源码清单）、ReplayBundle（重放包）、ProcessAuditBundle（流程审计包）或 GitVersionAuditBundle（Git 版本审计包）的内部内容。
3. 不生成或修改 generated project workspace（生成项目工作区）。
4. 不读取旧 runtime（旧运行时）、旧 workflow completion（旧流程完成）或旧 closeout state machine（旧收尾状态机）。
5. 不实现 branchable governance replay（可分叉治理重放）的完整恢复/分叉流程；本轮只为后续分叉能力提供明确的 terminal closeout projection（终态收尾投影）边界。
6. 不把 `PROJECT_COMPLETED`（项目已完成）作为正式事件；首版只引入 `CLOSEOUT_COMMITTED`，terminal success 由 CloseoutProjection（收尾投影）表达。

## 6. 模块设计

### 6.1 新增/修改文件

```text
src/boardroom_os/reducers/closeout_reducer.py
tests/closeout/test_closeout_reducer.py
src/boardroom_os/events/types.py
src/boardroom_os/execution/runtime_executor.py
```

必要时同步 public API（公开接口）导出：

```text
src/boardroom_os/reducers/__init__.py
src/boardroom_os/closeout/__init__.py
```

如果 `src/boardroom_os/reducers/__init__.py` 当前不存在，可不强制新增；测试可直接从模块路径 import（导入）。

### 6.2 建议公开对象

```python
class CloseoutReducerError(ValueError): ...

class CloseoutCommitPayload(BaseModel): ...
class CloseoutHistoryProjection(BaseModel): ...
class CloseoutProjection(BaseModel): ...

class CloseoutReducerPayloadResolver(Protocol):
    def resolve_closeout_commit(
        self,
        payload_ref: EventPayloadRef,
    ) -> CloseoutCommitPayload: ...

    def resolve_closeout_package(
        self,
        closeout_package_ref: CloseoutPackageRef,
    ) -> CloseoutPackage: ...

class CloseoutReducer:
    def __init__(self, payload_resolver: CloseoutReducerPayloadResolver) -> None: ...

    def reduce(
        self,
        events: tuple[EventRecord, ...],
        *,
        base_history: CloseoutHistoryProjection | None = None,
    ) -> CloseoutProjection: ...
```

## 7. Schema（结构）设计

### 7.1 CloseoutCommitPayload（收尾提交载荷）

建议 schema：

```yaml
closeout_package_ref:
closeout_gate_result_ref:
source_inventory_ref:
final_evidence_table_ref:
replay_bundle_ref:
process_audit_bundle_ref:
git_version_audit_bundle_ref:
package_commit_ref:
terminal_verdict: passed
```

字段语义：

- `closeout_package_ref` 必须等于 CloseoutPackage.closeout_package_id（收尾包 ID）。
- `closeout_gate_result_ref` 必须等于 CloseoutPackage.closeout_gate_result_ref（收尾门禁结果引用）。
- source/evidence/replay/process/git refs（源码/证据/重放/流程/Git 引用）必须分别等于 CloseoutPackage（收尾包）中对应字段。
- `package_commit_ref` 必须等于 CloseoutPackage.package_commit_ref（项目包提交引用）。
- `terminal_verdict` 首版固定为 `passed`；任何 failed/blocked/unknown value（失败/阻断/未知值）必须 fail closed（失败关闭）。

`CloseoutCommitPayload`（收尾提交载荷）是 event payload（事件载荷），用于把 EventRecord（事件记录）与 CloseoutPackage（收尾包）建立稳定绑定。它不复制完整 CloseoutPackage（收尾包），避免形成第二份事实源。

### 7.2 CloseoutHistoryProjection（收尾历史投影）

建议 schema：

```yaml
project_ref:
graph_version:
work_product_submitted_refs:
ticket_completed_refs:
closeout_package_refs:
```

字段语义：

- `project_ref` 是历史投影所属项目。
- `graph_version` 是该历史投影覆盖到的最后 graph version（图版本）。
- `work_product_submitted_refs` 是从历史 `WORK_PRODUCT_SUBMITTED`（工作产物已提交）事件显式投影出的 payload refs（载荷引用）或 WorkProduct refs（工作产物引用），必须非空才能允许 terminal success（终态成功）。
- `ticket_completed_refs` 首版用于可审计地说明已有 ticket completion（任务完成）历史；不强制要求全部 ticket complete，因为 V2-070F 不重新解释 TicketGraph（任务图）。
- `closeout_package_refs` 用于增量模式下检测重复 closeout（重复收尾）。

### 7.3 CloseoutProjection（收尾投影）

建议 schema：

```yaml
project_ref:
graph_version:
terminal_status: open | succeeded
closeout_package_ref:
closeout_gate_result_ref:
package_commit_ref:
committed_event_ref:
work_product_history_refs:
checked_refs:
```

字段语义：

- `terminal_status` 初始为 `open`（开放），只有合法 `CLOSEOUT_COMMITTED`（收尾已提交）事件可变为 `succeeded`（成功）。
- `graph_version` 为 reduce（归约）处理后的最后 event graph_version（事件图版本）；若提供 base_history（基准历史），不得回退。
- `committed_event_ref` 记录触发 terminal success（终态成功）的 EventRecord.event_id（事件 ID）。
- `work_product_history_refs` 来自 events（事件）和/或 base_history（基准历史），必须非空。
- `checked_refs` 至少包含 CloseoutPackage（收尾包）自身关键 refs 与 `work_product_history_refs`，用于 audit-friendly dump（审计友好转储）。

## 8. Validation（校验）规则

### 8.1 Event ordering（事件顺序）

`CloseoutReducer.reduce(...)`（收尾归约）必须 fail closed：

1. `events` 不能为空，除非调用方只想 materialize base_history（物化基准历史）；本工作包测试主路径使用非空 events。
2. 事件必须属于同一 `project_ref`（项目引用）。
3. 事件 graph_version（图版本）必须严格递增；不得通过排序悄悄修正乱序输入。
4. 若提供 `base_history`（基准历史），第一条增量事件 graph_version 必须大于 `base_history.graph_version`。
5. `CLOSEOUT_COMMITTED`（收尾已提交）只能出现一次；重复 closeout 必须失败。

### 8.2 Runtime/governance boundary（运行时/治理边界）

1. `CLOSEOUT_COMMITTED`（收尾已提交）事件的 actor_ref（参与者引用）不得以 `runtime:` 或 `executor:` 开头。
2. `RuntimeEventBoundary.require_runtime_fact_event(EventType.CLOSEOUT_COMMITTED)` 必须失败，错误应指向 runtime cannot emit governance event（运行时不能发出治理事件）。
3. 任意字符串 `"workflow_completed"`、`"project_completed"` 或其他非 EventType（事件类型）都不能产生 terminal success（终态成功）。
4. 如果 EventRecord（事件记录）使用未知 event_type（未知事件类型），应由 EventRecord/EventLog（事件记录/事件日志）已有 fail-closed 机制阻断；CloseoutReducer（收尾归约器）不接受裸字符串事件绕过。

### 8.3 CloseoutPackage binding（收尾包绑定）

对 `CLOSEOUT_COMMITTED`（收尾已提交）事件：

1. 必须只有一个 payload_ref（载荷引用）。
2. payload resolver（载荷解析器）必须返回 typed `CloseoutCommitPayload`（类型化收尾提交载荷），raw dict（原始字典）必须失败。
3. payload resolver（载荷解析器）必须同时通过 `resolve_closeout_package(payload.closeout_package_ref)` 解析出 typed `CloseoutPackage`（类型化收尾包）；raw dict（原始字典）或只凭 ref string（引用字符串）通过都必须失败。
4. CloseoutPackage.verdict（收尾包结论）必须为 `passed`。
5. CloseoutPackage.closeout_gate_result_ref（收尾门禁结果引用）必须等于 payload.closeout_gate_result_ref。
6. payload 中 source inventory / final evidence / replay / process audit / git audit / package commit refs 必须与 CloseoutPackage（收尾包）一致。
7. CloseoutPackage.checked_refs（收尾包检查引用）必须覆盖 payload 中 gate/source/evidence/replay/process/git/package commit 等外部关键 refs；`closeout_package_ref`（收尾包自身引用）通过等于 `CloseoutPackage.closeout_package_id` 单独校验，不要求出现在 checked_refs 中。
8. CloseoutPackage.graph_version 不得大于 commit event.graph_version；否则表示事件在尚未到达收尾包所声明的图版本前就提交了 closeout。

### 8.4 Historical work product requirement（历史工作产物要求）

1. `CloseoutReducer`（收尾归约器）必须从当前 events（当前事件）收集 `WORK_PRODUCT_SUBMITTED`（工作产物已提交）payload refs，并与 `base_history.work_product_submitted_refs` 合并。
2. terminal success（终态成功）前 `work_product_history_refs` 必须非空。
3. 增量模式中，如果当前 events（当前事件）只包含 `CLOSEOUT_COMMITTED`，则必须提供 base_history（基准历史）且其 `work_product_submitted_refs` 非空。
4. 不能调用 `TicketReducer.reduce()` 后从其局部状态猜测历史 work product（工作产物）；历史事实必须作为 `CloseoutHistoryProjection`（收尾历史投影）或当前 EventRecord（事件记录）显式输入。

### 8.5 Terminal projection invariant（终态投影不变量）

1. 没有 `CLOSEOUT_COMMITTED`（收尾已提交）事件时，projection（投影）保持 `terminal_status="open"`。
2. 有合法 `CLOSEOUT_COMMITTED` 事件时，projection（投影）为 `terminal_status="succeeded"`。
3. succeeded projection（成功投影）必须包含 `closeout_package_ref`、`closeout_gate_result_ref`、`package_commit_ref`、`committed_event_ref` 和非空 `work_product_history_refs`。
4. 已经 succeeded（成功）的 base_history（基准历史）不得再接受新的 closeout commit（收尾提交）。

## 9. 数据流

```text
RuntimeExecutor（运行时执行器）
  -> WORK_PRODUCT_SUBMITTED（工作产物已提交）facts（事实）
  -> TicketReducer / CompletionGate（任务归约器 / 完成门禁）
  -> TICKET_COMPLETED（任务已完成）facts（事实）
  -> Evidence / SourceInventory / Replay / ProcessAudit / GitAudit（证据 / 源码清单 / 重放 / 流程审计 / Git 审计）
  -> CloseoutGate（收尾门禁）
  -> CloseoutPackage（收尾包）
  -> CLOSEOUT_COMMITTED（收尾已提交治理事件）
  -> CloseoutReducer（收尾归约器）
  -> CloseoutProjection.terminal_status = succeeded（收尾投影终态成功）
```

关键边界：

- runtime（运行时）只能 emit（发出）execution/provider/tool/command/work product facts（执行/模型/工具/命令/工作产物事实）。
- closeout commit（收尾提交）必须来自治理/收尾链路 actor（参与者），不是 runtime actor（运行时参与者）。
- CloseoutReducer（收尾归约器）不重新证明 evidence（证据），只检查 CloseoutPackage（收尾包）和历史事实引用闭合。

## 10. 错误处理

1. 所有输入模型使用 Pydantic（Pydantic 模型）`frozen=True` 与 `extra="forbid"`。
2. 对外统一抛出 `CloseoutReducerError`（收尾归约器错误），错误信息应指向 event order（事件顺序）、actor boundary（参与者边界）、package binding（收尾包绑定）或 history gap（历史缺口）。
3. reducer（归约器）不得自动补齐 missing history（缺失历史）、默认生成 closeout package（收尾包）或把 workflow completed（流程完成）转换成成功。
4. `model_dump(mode="json")` 不得包含宿主绝对路径、Windows drive（Windows 盘符）、反斜杠路径、`.pytest` 临时目录或旧实现路径。

## 11. 测试计划

### 11.1 必须先写的 negative tests（负例测试）

新增 `tests/closeout/test_closeout_reducer.py`，建议 test names（测试名）：

1. `test_closeout_reducer_rejects_runtime_closeout_event`
   - `CLOSEOUT_COMMITTED`（收尾已提交）事件 actor_ref 以 `runtime:` 或 `executor:` 开头时失败。
   - `RuntimeEventBoundary.require_runtime_fact_event(EventType.CLOSEOUT_COMMITTED)` 必须失败。

2. `test_closeout_reducer_rejects_workflow_completed_without_closeout_package`
   - workflow completed（流程完成）或 project_completed（项目完成）不能产生 terminal success（终态成功）。
   - 没有 `CLOSEOUT_COMMITTED` 事件时 projection（投影）保持 open（开放）。

3. `test_closeout_reducer_rejects_missing_closeout_gate_or_blocked_package`
   - CloseoutPackage.verdict 不是 passed（通过）或 payload 缺 closeout_gate_result_ref（收尾门禁结果引用）必须失败。

4. `test_closeout_reducer_rejects_missing_replay_bundle_binding`
   - payload 或 package 缺 replay_bundle_ref（重放包引用），或 payload 与 package 的 replay_bundle_ref 不一致时失败。

5. `test_closeout_reducer_rejects_package_payload_ref_mismatch`
   - source inventory / final evidence table / process audit / git audit / package commit 任一 ref mismatch（引用不一致）必须失败。

6. `test_closeout_reducer_rejects_closeout_before_package_graph_version`
   - commit event.graph_version 小于 CloseoutPackage.graph_version 时失败。

7. `test_closeout_reducer_rejects_incremental_closeout_without_work_product_history`
   - 增量 events 只有 `CLOSEOUT_COMMITTED` 且 base_history 缺 `WORK_PRODUCT_SUBMITTED` 历史时失败。

8. `test_closeout_reducer_rejects_missing_work_product_history_even_if_ticket_completed_exists`
   - base_history 只含 ticket completed refs（任务完成引用）但没有 work product submitted refs（工作产物提交引用）时失败。

9. `test_closeout_reducer_rejects_duplicate_closeout_commit`
   - 同一 reduce 输入中出现两个 `CLOSEOUT_COMMITTED` 事件时失败。
   - 已 succeeded base_history（已成功基准历史）再收到 closeout commit 时失败。

10. `test_closeout_reducer_rejects_out_of_order_or_cross_project_events`
    - graph_version 乱序或 project_ref 不一致时失败。

11. `test_closeout_reducer_rejects_raw_dict_payloads`
    - resolver 返回 raw dict（原始字典）而不是 typed CloseoutCommitPayload（类型化收尾提交载荷）时失败。

12. `test_closeout_reducer_rejects_checked_refs_gap`
    - CloseoutPackage.checked_refs（收尾包检查引用）缺 payload 中任一关键 ref 时失败。

### 11.2 Happy path（正向路径）

1. `test_closeout_reducer_projects_terminal_success_from_passed_closeout_package`
   - 当前 events 包含 `WORK_PRODUCT_SUBMITTED` 和合法 `CLOSEOUT_COMMITTED` 时，projection.terminal_status 为 succeeded。

2. `test_closeout_reducer_supports_incremental_base_history_with_explicit_work_product_refs`
   - base_history 显式携带 work product submitted refs，增量 events 只包含合法 `CLOSEOUT_COMMITTED` 时可成功。

3. `test_closeout_projection_dump_is_audit_friendly_json`
   - CloseoutProjection（收尾投影）JSON 不含宿主绝对路径、Windows drive（Windows 盘符）、反斜杠路径、临时目录或旧实现路径。

4. `test_closeout_committed_event_is_accepted_by_event_record_but_not_runtime_boundary`
   - EventRecord（事件记录）可表达 `EventType.CLOSEOUT_COMMITTED`，但 runtime boundary（运行时边界）拒绝它。

## 12. 验证命令

实施完成后建议运行：

```bash
PYTHONPATH="src;." python -m pytest tests/closeout/test_closeout_reducer.py -q
PYTHONPATH="src;." python -m pytest tests/closeout/test_closeout_reducer.py tests/closeout/test_closeout_package.py tests/closeout/test_closeout_gate.py tests/negative/test_closeout_fail_closed.py -q
PYTHONPATH="src;." python -m pytest tests/reducers/test_completion_gate_with_evidence.py tests/reducers/test_ticket_reducer_transitions.py tests/closeout/test_closeout_reducer.py -q
PYTHONPATH="src;." python -m pytest tests/contracts tests/reducers tests/execution tests/evidence tests/proving tests/closeout tests/negative -q --basetemp=.pytest-tmp-v2070f-all
```

其中第一条证明 V2-070F 自身；第二条证明 V2-070A/E/F gate-package-reducer chain（门禁-收尾包-归约器链）一致；第三条证明 ticket completion（任务完成）和 closeout terminal success（收尾终态成功）边界不混淆；第四条作为全量回归。

## 13. 完成后文档同步

实现完成并通过验证后，必须按 `backlog.md` 的工作包完成更新协议同步：

1. `doc/04-implementation/backlog.md`
   - V2-070F 状态改为 DONE。
   - 顶部“当前未完成工作包”指向 V2-080A。
   - Phase 7 进度从 5 / 6 改为 6 / 6；总计数字以实施当时 backlog 为准。
2. `doc/04-implementation/acceptance-criteria.md`
   - 勾选 Phase 7 的 “Closeout reducer 接入”。
   - 勾选 “V2-070A ~ V2-070F 六个工作包全部 DONE”。
   - 勾选 “backlog.md 进度总览 Phase 7 显示 6/6”。
   - 若本工作包是 Phase 7 最后一项，同步勾选 “进入 Phase 8 前置”全部项。
3. `doc/05-project-log/2026-05.md`
   - 追加 V2-070F 完成记录，包含关键产出文件、negative/happy tests（负例/正例测试）和真实验证命令证据。
4. `doc/05-project-log/decisions.md`
   - 若实现坚持本 spec 的方案 A，只新增 `CLOSEOUT_COMMITTED` 作为治理事件并保持 runtime 拒绝，不需要新增 DEC；如改变 CloseoutGate/CloseoutPackage 权威边界或引入 `PROJECT_COMPLETED` 正式事件，则必须新增决策。
5. `doc/04-implementation/INDEX.md`
   - 本 spec 文件已加入索引；若新增 implementation plan（实施计划）文档，应同步追加。
6. `doc/04-implementation/acceptance-criteria.md` 抽象 AC 段
   - 仅当本轮改变 AC-V2-CLOSEOUT-001/002/003 语义时同步。按本 spec 实施只闭合 Phase 7 checkbox，不改变抽象 AC 语义。

## 14. 评审关注点

请重点审查：

1. 是否同意 `CLOSEOUT_COMMITTED`（收尾已提交）作为正式治理事件，而不是 runtime fact（运行时事实）。
2. 是否同意 terminal success projection（终态成功投影）由 CloseoutReducer（收尾归约器）表达，而不是 CloseoutPackage（收尾包）对象本身直接表达。
3. 是否同意首版不引入 `PROJECT_COMPLETED`（项目已完成）正式事件，避免 workflow completed（流程完成）语义复活。
4. 是否同意增量 reducer/replay（增量归约/重放）必须通过 CloseoutHistoryProjection（收尾历史投影）显式携带 `WORK_PRODUCT_SUBMITTED`（工作产物已提交）历史事实。
5. 是否同意 CloseoutReducer（收尾归约器）不重新运行 CloseoutGate（收尾门禁），只校验 passed CloseoutPackage（通过收尾包）和 payload refs（载荷引用）一致。
6. 是否同意 `CloseoutCommitPayload`（收尾提交载荷）不复制完整 CloseoutPackage（收尾包），并由 resolver/package registry（解析器/包注册表）通过 `closeout_package_ref` 解析 typed CloseoutPackage（类型化收尾包），不能只凭 ref string（引用字符串）通过。
7. 是否同意 Event ordering（事件顺序）采用严格输入顺序校验，而不是内部排序修复。
8. 是否同意重复 closeout commit（重复收尾提交）永远 fail closed（失败关闭）。

## 15. 完成判定

V2-070F 完成时：

1. `src/boardroom_os/reducers/closeout_reducer.py` 存在，并只承担收尾事件到 terminal success projection（终态成功投影）的归约职责。
2. `EventType.CLOSEOUT_COMMITTED`（收尾已提交事件）存在，且 RuntimeEventBoundary（运行时事件边界）拒绝 runtime emit（运行时发出）。
3. 缺 closeout package（收尾包）、缺 closeout gate ref（收尾门禁引用）、缺 replay bundle ref（重放包引用）、workflow completed 替代 closeout、runtime closeout、增量历史缺 `WORK_PRODUCT_SUBMITTED` 均由 negative tests（负例测试）证明失败。
4. passed CloseoutPackage（通过的收尾包）经 `CLOSEOUT_COMMITTED`（收尾已提交）事件可投影为 project terminal success（项目终态成功）。
5. Phase 7 全部工作包可按 acceptance-criteria（验收标准）勾选，V2-080A 可作为下一个未完成工作包。
