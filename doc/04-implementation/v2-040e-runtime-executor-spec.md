# V2-040E RuntimeExecutor 设计 Spec

## 1. 现实场景

本轮对应的现实场景是：当 Boardroom OS V2 把一个 ready ExecutionPackage（就绪执行包）交给 runtime（运行时）时，runtime 只能像受控流水线执行员一样记录“开始执行、调用 provider（模型供应商）、提交 WorkProduct（工作产物）、运行 declared command（已声明命令）”这些事实，不能替 CEO、Architect（架构师）、Checker（检查者）或 Closeout（收尾）链路做治理判断。

通俗地说，V2-040E 要给 runtime 装一条“权限护栏”：它可以把执行过程留下可审计脚印，但不能盖章说 ticket（任务）完成、project（项目）完成或 closeout（收尾）通过。

## 2. 目标

实现 RuntimeExecutor（运行时执行器）的最小事实事件边界：

1. 接收一个已编译的 ExecutionPackage（执行包）作为核心执行原语。
2. 通过 ProviderExecutor（模型供应商执行器）调用 provider，并记录 ProviderAttempt（模型调用尝试记录）。
3. 将成功 ProviderAttempt 转成 WorkProduct（工作产物）并提交 `WORK_PRODUCT_SUBMITTED`（工作产物已提交）事实事件。
4. 通过 CommandRunner（命令执行器）运行 ExecutionPackage 与 PackageContract（包合同）共同声明的 commands（命令），并记录 VerificationRun（验证运行）。
5. 只允许 runtime emit execution/provider/tool/command/work product fact events（执行/模型/工具/命令/工作产物事实事件）。
6. 拒绝 runtime emit `TICKET_COMPLETED`、`PROJECT_COMPLETED`、`CLOSEOUT_COMMITTED` 这类 governance events（治理事件）。
7. 越权判断基于 AgentTeamProjection（智能体团队投影）中的 AgentSeat（智能体席位）与 RoleCategory（角色类别），不基于 `actor_ref` 字符串前缀。
8. 在设计上保留多 ticket runtime loop（多任务运行循环）的 independent wave（独立波次）语义，但本工作包不实现动态图推进 loop。

## 3. 非目标

V2-040E 不做以下事情：

1. 不实现 EvidenceClaim（证据声明）、EvidenceVerifier（证据验证器）、VerifiedEvidenceTable（已验证证据表）或 CheckerVerdict（检查结论），这些属于 V2-050。
2. 不实现 SourceInventory（源码清单）、RunManifest（运行清单）或 PackageAssembler（项目包装配器），这些属于 V2-060。
3. 不实现 CloseoutGate（收尾门禁）、ReplayBundle（重放包）或 ProcessAudit（流程审计），这些属于 V2-070。
4. 不把 command exit code（命令退出码）或 provider success（模型调用成功）解释为 acceptance satisfied（验收满足）。
5. 不根据 WorkProduct 或 VerificationRun 自动 emit `TICKET_COMPLETED`。
6. 不在 runtime 内重新计算 ready queue（就绪队列）、编译后续 ExecutionPackage，或沿依赖链级联执行下一批 ticket。
7. 不新增完整 `PROJECT_COMPLETED` / `CLOSEOUT_COMMITTED` EventType（事件类型）枚举；若这些未来治理事件尚未进入 EventType，runtime boundary（运行时边界）仍应按保留治理事件名拒绝 raw request（原始请求）。
8. 不持久化 stdout/stderr 内容到 `20-evidence/`；CommandRunnerResult（命令执行器结果）仍按 V2-040D 返回内容，后续 evidence export（证据导出）负责物化。

## 4. 选型结论

采用“单包执行原语 + 独立波次设计边界”方案。

### 4.1 被采用方案：单包执行原语 + 独立波次边界

V2-040E 实现 `RuntimeExecutor.execute_package`（运行时单包执行）作为真实代码入口。该入口消费一个 ExecutionPackage、PackageContract、ProviderAdapter（模型供应商适配器）、CommandRunner 输入所需环境引用，以及 AgentTeamProjection，用于校验执行席位和 runtime actor（运行时参与者）边界。

未来多 ticket runtime loop（多任务运行循环）只能作为 `execute_package` 的组合层：它接收同一 graph_version（图版本）下已经由外部 graph/compiler/reducer（任务图/编译器/状态归约器）证明 ready 的 ExecutionPackage 集合，并以 independent wave（独立波次）方式执行。

优点：

- V2-040E 可直接证明 runtime bounded（运行时受限）。
- 单包入口是未来多 ticket loop 的真子集，不是一次性孤岛实现。
- 保持 Runtime bounded：runtime 只执行事实，不推进治理状态。
- 避免把 V2-080 proving scenario（证明场景）的 orchestration（编排）提前塞进 V2-040E。

代价：

- 本期不会完成多 ticket 调度器。
- wave independence（波次独立性）的完整图论校验需要后续 orchestrator（编排器）接入 TicketGraph（任务图）后完成。

### 4.2 未采用方案：只做事件发射门禁

只实现 `RuntimeEventBoundary`（运行时事件边界）校验允许/禁止的 EventType，不串接 ProviderExecutor、WorkProduct 和 CommandRunner。

不采用原因：无法证明 backlog 要求的 happy path —— “runtime 对 ready execution package 可记录 provider attempt、work product 和 command run”。

### 4.3 未采用方案：完整多 ticket runtime loop

本期直接实现从 ready queue 中批量取 ticket、编译包、执行、追加事件、重新投影并继续执行依赖后继节点的 loop。

不采用原因：这会让 runtime 动态推进 graph progression（任务图推进），容易把 reducer/projection/compiler 的治理职责转移到 runtime，违反 V2 runtime bounded 原则。

## 5. 已决实施决定

1. `execute_package` 是 V2-040E 的最小执行原语；后续 `execute_wave` 只能组合它。
2. runtime fact events（运行时事实事件）允许集合为：`EXECUTION_STARTED`、`PROVIDER_ATTEMPT_RECORDED`、`TOOL_ATTEMPT_RECORDED`、`WORK_PRODUCT_SUBMITTED`、`COMMAND_RUN_RECORDED`。
3. governance events（治理事件）拒绝集合至少包含：`TICKET_COMPLETED`、保留名 `PROJECT_COMPLETED`、保留名 `CLOSEOUT_COMMITTED`。
4. EventType（事件类型）采用 DEC-0010 的阶段性收窄原则：V2-040E 不为未来 project/closeout 事件提前扩枚举；runtime boundary 必须能拒绝保留治理事件名。
5. runtime actor_ref（运行时参与者引用）必须是 runtime service actor（运行时服务参与者），不得等于任何 active AgentSeat.actor_ref（活跃智能体席位参与者引用）。这可防止 runtime 使用普通 seat actor_ref 冒充 CEO、Checker 或 Worker。
6. ExecutionPackage.seat_ref（执行包席位引用）必须解析到 AgentTeamProjection.active_seats（活跃席位）中的 AgentSeat。
7. 可执行席位的 RoleCategory（角色类别）首版限定为 `IMPLEMENTATION`（实施）、`VERIFICATION`（验证）和 `INTEGRATION`（集成）；`GOVERNANCE`（治理）、`ARCHITECTURE`（架构）和 `AUDIT`（审计）席位不得被 runtime 当作 work execution seat（工作执行席位）运行。
8. ProviderAttempt 失败时 runtime 只记录 `PROVIDER_ATTEMPT_RECORDED`，不构造 WorkProduct。
9. ProviderAttempt 成功时 runtime 必须通过 `build_work_product_from_provider_attempt`（从模型尝试构建工作产物）构造 WorkProductSubmission（工作产物提交包），再通过既有 factory 构造 `WORK_PRODUCT_SUBMITTED` 事件。
10. CommandRunner 返回 failed VerificationRun（失败验证运行）时 runtime 仍记录 `COMMAND_RUN_RECORDED` 事实事件；是否阻断验收由 V2-050 决定。
11. RuntimeExecutor 不直接调用 TicketReducer（任务状态归约器）完成 ticket；事件 append（追加）后的 projection（投影）由调用方或后续编排层处理。
12. 事件 graph_version 分配必须显式、确定且单调递增；单包执行可从 `first_fact_graph_version` 开始分配，future wave（未来波次）在同一 wave 内按 deterministic package order（确定性执行包顺序）分配连续事件版本。

## 6. 模块设计

### 6.1 `src/boardroom_os/execution/runtime_executor.py`

新增 RuntimeExecutor（运行时执行器）模块，包含：

- `RuntimeExecutor`（运行时执行器）
- `RuntimeExecutorError`（运行时执行器错误）
- `RuntimeExecutionInput`（运行时执行输入）
- `RuntimeExecutionResult`（运行时执行结果）
- `RuntimeEventBoundary`（运行时事件边界）
- `RuntimeEventSequencer`（运行时事件序列器）

`RuntimeExecutionInput` 固定字段：

```yaml
execution_package:
package_contract:
agent_team_projection:
provider_adapter:
project_ref:
runtime_actor_ref:
first_fact_graph_version:
package_root:
runner_ref:
environment_profile_ref:
workspace_snapshot_ref:
command_ids:
timestamp:
```

字段说明：

- `execution_package`：已由 ExecutionPackageCompiler（执行包编译器）编译出的执行包。
- `package_contract`：CommandRunner 校验 declared command 时需要的 active PackageContract。
- `agent_team_projection`：用于解析 execution seat（执行席位）与 active seats（活跃席位），实现 role-aware boundary（按角色边界）。
- `provider_adapter`：ProviderExecutor 使用的 ProviderAdapter；测试可用 FakeProviderTransport（模拟模型传输）。
- `project_ref`：事件所属 ProjectRef（项目引用）。
- `runtime_actor_ref`：事件 actor_ref；必须不是任何 active AgentSeat.actor_ref。
- `first_fact_graph_version`：本次执行第一个事实事件使用的 graph_version，必须大于 `execution_package.graph_version`。
- `package_root`、`runner_ref`、`environment_profile_ref`、`workspace_snapshot_ref`：转交 CommandRunner。
- `command_ids`：本次要运行的 declared command IDs（声明命令 ID 集合）；空集合表示本包不运行命令，但 provider/work product 事实仍可记录。
- `timestamp`：用于首版事件时间；若需要每个事件独立时间，后续可替换为 clock protocol（时钟协议），但本期不要求。

`RuntimeExecutionResult` 固定字段：

```yaml
provider_attempt:
work_product_submission:
verification_runs:
events:
stdout_by_verification_run:
stderr_by_verification_run:
```

说明：

- `provider_attempt` 总是返回；失败 attempt 是可审计事实。
- `work_product_submission` 仅在 provider attempt succeeded（模型调用成功）时存在。
- `verification_runs` 包含每个 command run 的 VerificationRun。
- `events` 是 runtime 允许发出的事实事件，供 caller append 到 InMemoryEventLog（内存事件日志）或未来持久化 event log。
- stdout/stderr 内容按 VerificationRunRef（验证运行引用）索引返回。

### 6.2 RuntimeEventBoundary（运行时事件边界）

RuntimeEventBoundary 负责两个维度校验：

1. event_type boundary（事件类型边界）
2. actor/seat boundary（参与者/席位边界）

允许事件类型：

```text
execution_started
provider_attempt_recorded
tool_attempt_recorded
work_product_submitted
command_run_recorded
```

拒绝事件类型：

```text
ticket_completed
project_completed
closeout_committed
```

实现上应支持传入 EventType 或 raw event name（原始事件名）进行校验：

- 对当前 EventType 中已有的 `TICKET_COMPLETED`，必须拒绝。
- 对当前 EventType 中尚未存在的 `PROJECT_COMPLETED`、`CLOSEOUT_COMMITTED`，若调用方以 raw name 请求，也必须拒绝。
- unknown non-governance raw event name（未知非治理原始事件名）也应失败，不能靠字符串绕过 EventType。

Actor/seat boundary：

1. 从 `agent_team_projection.active_seats` 中解析 `execution_package.seat_ref`。
2. 若 seat 不存在或 inactive（非活跃），失败。
3. 若 seat.role_category 不在 `IMPLEMENTATION | VERIFICATION | INTEGRATION`，失败。
4. 若 `runtime_actor_ref` 等于任一 active seat 的 `actor_ref`，失败。
5. 该校验不使用 `actor_ref` 字符串前缀，例如不判断是否以 `runtime:` 开头。

### 6.3 RuntimeEventSequencer（运行时事件序列器）

RuntimeEventSequencer 负责 deterministic graph_version（确定性图版本）分配。

单包规则：

```text
base package graph_version = N
first_fact_graph_version must be > N
runtime facts use first_fact_graph_version, first_fact_graph_version + 1, ...
```

推荐事件顺序：

1. `EXECUTION_STARTED`
2. `PROVIDER_ATTEMPT_RECORDED`
3. `WORK_PRODUCT_SUBMITTED`（仅 provider succeeded）
4. `COMMAND_RUN_RECORDED`（每个 command 一条，按 command_ids 输入顺序）

如果 provider failed（模型调用失败），仍生成：

1. `EXECUTION_STARTED`
2. `PROVIDER_ATTEMPT_RECORDED`

但不生成 WorkProduct，也不运行 commands。原因是没有可提交的 implementation artifact（实施产物），后续 verifier/checker 应看到失败 attempt 事实。

### 6.4 ProviderAttempt recorded event（模型调用尝试已记录事件）

V2-040E 新增 factory（事件工厂）：

```python
build_provider_attempt_recorded_event(...)
```

事件字段：

```yaml
event_type: provider_attempt_recorded
payload_refs:
  - <provider_attempt_id>
actor_ref: runtime_actor_ref
graph_version: sequencer.next()
```

factory 不验证 provider attempt 是否成功，只记录事实。

### 6.5 Command run recorded event（命令运行已记录事件）

V2-040E 新增 factory：

```python
build_command_run_recorded_event(...)
```

事件字段：

```yaml
event_type: command_run_recorded
payload_refs:
  - <verification_run_id>
actor_ref: runtime_actor_ref
graph_version: sequencer.next()
```

factory 不把 `status=passed` 解释为验收成功，也不把 `status=failed` 抛成治理异常。

### 6.6 Execution started event（执行已开始事件）

V2-040E 新增最小 `EXECUTION_STARTED` 事件 factory：

```python
build_execution_started_event(...)
```

事件 payload_ref 建议使用 `execution_package.execution_package_id`，表示“runtime 开始执行这个执行包”。本期不新增复杂 ExecutionStartedPayload（执行开始载荷），避免在 V2-040E 引入新的持久 payload store（载荷存储）。

## 7. 多 ticket runtime loop 的保留语义

未来多 ticket runtime loop（多任务运行循环）应采用 independent wave（独立波次）模型。

### 7.1 Independent wave 定义

一个 wave 是在同一 TicketGraph graph_version=N 下，由外部 graph/projection/compiler 已经证明 ready 的 ExecutionPackage 集合。wave 内 ticket 必须满足：

1. 同一 `execution_package.graph_version == N`。
2. ticket 节点之间没有直接依赖。
3. ticket 节点之间没有间接依赖或级联依赖。
4. ticket 节点之间没有 allowed_write_set（允许写入集合）冲突。
5. 每个 ticket 的 seat assignment（席位分配）已经在 graph_version=N 前稳定。
6. 每个 ExecutionPackage 已由 compiler 基于 graph_version=N 编译完成。

这组 ticket 在图论上应形成 antichain（反链）：wave 内任意两个 ticket 不存在 path（路径）可达关系。

### 7.2 Runtime loop 不能做什么

即使实现 `execute_wave`，runtime 也不能：

1. 在 ticket A 产出 WorkProduct 后，立刻判断依赖 A 的 ticket B 变 ready。
2. 在同一 loop 内重新调用 compiler 编译 B。
3. 在同一 loop 内根据 command result 或 provider result emit `TICKET_COMPLETED`。
4. 把 wave 内事实投影后的新 graph state（任务图状态）继续作为本 wave 的输入。

### 7.3 Wave 事件版本语义

event log（事件日志）仍是线性 append-only（只追加）事实序列。即使 wave 语义表示“可并行”，事件写入也必须有 deterministic serial order（确定性串行顺序）。推荐规则：

1. 按 `execution_package.execution_package_id.value` 排序。
2. 对每个 package 调用 `execute_package`。
3. 共享一个 RuntimeEventSequencer，从 `base_graph_version + 1` 开始分配连续 graph_version。
4. wave 完成后，调用方基于全部事实事件重新投影，再决定下一 wave。

该语义让 runtime 保持可回放、可审计，同时避免动态依赖级联。

## 8. 数据流

```text
AgentTeamProjection（智能体团队投影）
  + ExecutionPackage（执行包）
  + PackageContract（包合同）
  + ProviderAdapter（模型供应商适配器）
  + CommandRunner refs（命令运行引用）
      -> RuntimeExecutor（运行时执行器）
          -> RuntimeEventBoundary（运行时事件边界）
          -> EXECUTION_STARTED fact（执行开始事实）
          -> ProviderExecutor（模型供应商执行器）
              -> ProviderAttempt（模型调用尝试记录）
              -> PROVIDER_ATTEMPT_RECORDED fact（模型调用尝试事实）
          -> WorkProduct builder（工作产物构建）
              -> WorkProductSubmission（工作产物提交包）
              -> WORK_PRODUCT_SUBMITTED fact（工作产物提交事实）
          -> CommandRunner（命令执行器）
              -> VerificationRun（验证运行）
              -> COMMAND_RUN_RECORDED fact（命令运行事实）
                  -> V2-050 EvidenceClaim / EvidenceVerifier（证据声明/证据验证器）
```

RuntimeExecutor 只返回 facts（事实）和 typed records（类型化记录）。是否满足 acceptance、是否完成 ticket、是否进入 closeout，全部交给后续 reducer/evidence/checker/closeout 链路。

## 9. Fail-closed 规则

以下情况必须失败：

1. RuntimeEventBoundary 收到 `TICKET_COMPLETED`。
2. RuntimeEventBoundary 收到 raw name `project_completed`。
3. RuntimeEventBoundary 收到 raw name `closeout_committed`。
4. RuntimeEventBoundary 收到 unknown event name（未知事件名）。
5. `runtime_actor_ref` 等于任一 active AgentSeat.actor_ref。
6. `execution_package.seat_ref` 不在 AgentTeamProjection.active_seats 中。
7. execution seat 的 RoleCategory 是 `GOVERNANCE`、`ARCHITECTURE` 或 `AUDIT`。
8. `first_fact_graph_version <= execution_package.graph_version`。
9. RuntimeExecutor 尝试生成 governance event。
10. ProviderExecutor 返回 misbound ProviderAttempt（错绑模型调用尝试）时失败，复用 V2-040B 校验。
11. 成功 ProviderAttempt 缺 raw/parsed output ref 时 WorkProduct 构建失败，复用 V2-040C 校验。
12. CommandRunner 发现 command 不在 ExecutionPackage 或 PackageContract 中时失败，复用 V2-040D 校验。
13. command_ids 中任一 command 失败执行本身不让 RuntimeExecutor 失败；它应记录 failed VerificationRun 事实。
14. provider failed 不让 RuntimeExecutor 抛治理错误；它应记录 failed ProviderAttempt，但不得生成 WorkProduct 或 command run。

## 10. Happy path

最小正例：

1. 构造 active AgentTeamProjection，包含一个 IMPLEMENTATION AgentSeat。
2. 构造 ExecutionPackage，seat_ref 指向该 active implementation seat。
3. runtime_actor_ref 使用独立 runtime service actor，不等于任何 active AgentSeat.actor_ref。
4. RuntimeExecutor 生成 `EXECUTION_STARTED` 事件。
5. ProviderExecutor 通过 FakeProviderTransport 生成 succeeded ProviderAttempt。
6. RuntimeExecutor 生成 `PROVIDER_ATTEMPT_RECORDED` 事件。
7. RuntimeExecutor 通过 WorkProduct builder 生成 WorkProductSubmission。
8. RuntimeExecutor 生成 `WORK_PRODUCT_SUBMITTED` 事件。
9. RuntimeExecutor 对 command_ids 中的 declared command 调用 CommandRunner。
10. RuntimeExecutor 生成 `COMMAND_RUN_RECORDED` 事件。
11. 返回结果包含 ProviderAttempt、WorkProductSubmission、VerificationRun、stdout/stderr 内容和事实事件列表。
12. 事件类型全部属于 runtime allowed fact events。
13. 事件 graph_version 从 `first_fact_graph_version` 开始连续递增。
14. 结果中没有 `TICKET_COMPLETED`、`PROJECT_COMPLETED` 或 `CLOSEOUT_COMMITTED`。

Provider failed 正例：

1. ProviderExecutor 返回 failed ProviderAttempt。
2. RuntimeExecutor 返回 failed ProviderAttempt。
3. RuntimeExecutor 只生成 `EXECUTION_STARTED` 与 `PROVIDER_ATTEMPT_RECORDED`。
4. RuntimeExecutor 不生成 WorkProductSubmission，不运行 command_ids，不声称 ticket 完成。

Command failed 正例：

1. ProviderAttempt succeeded，WorkProductSubmission 生成成功。
2. CommandRunner 真实运行 declared command 并返回非 0 exit code。
3. RuntimeExecutor 记录 failed VerificationRun 和 `COMMAND_RUN_RECORDED`。
4. RuntimeExecutor 不抛治理错误，不 emit completion event。

## 11. 测试计划

新增测试：

- `tests/execution/test_runtime_executor_boundary.py`
- `tests/negative/test_runtime_cannot_govern.py`

### 11.1 Negative tests（先写）

`tests/negative/test_runtime_cannot_govern.py`：

1. `test_runtime_event_boundary_rejects_ticket_completed`
2. `test_runtime_event_boundary_rejects_project_completed_reserved_name`
3. `test_runtime_event_boundary_rejects_closeout_committed_reserved_name`
4. `test_runtime_event_boundary_rejects_unknown_raw_event_name`
5. `test_runtime_rejects_runtime_actor_that_matches_active_governance_seat_actor`
6. `test_runtime_rejects_runtime_actor_that_matches_active_worker_seat_actor`
7. `test_runtime_rejects_execution_package_for_governance_seat`
8. `test_runtime_rejects_execution_package_for_architecture_seat`
9. `test_runtime_rejects_execution_package_for_audit_seat`
10. `test_runtime_rejects_missing_active_execution_seat`
11. `test_runtime_rejects_first_fact_graph_version_not_after_package_graph_version`
12. `test_runtime_never_emits_ticket_completed_after_successful_provider_and_command`

### 11.2 Happy path tests

`tests/execution/test_runtime_executor_boundary.py`：

1. `test_runtime_executor_records_provider_attempt_work_product_and_command_run_facts`
2. `test_runtime_executor_records_failed_provider_attempt_without_work_product_or_command_run`
3. `test_runtime_executor_records_failed_command_run_as_fact`
4. `test_runtime_executor_assigns_deterministic_monotonic_graph_versions`
5. `test_runtime_event_boundary_allows_only_runtime_fact_events`

### 11.3 Future wave tests（后续工作包或 V2-080 前补齐）

未来新增 `execute_wave` 时必须补：

1. 同一 wave 中 mixed graph_version 必须失败。
2. 同一 wave 中存在直接依赖必须失败。
3. 同一 wave 中存在间接依赖必须失败。
4. 同一 wave 中 allowed_write_set 冲突必须失败。
5. 同一 wave 事件 append 顺序必须 deterministic。
6. wave 内不得根据前一 package 产出级联编译/执行后继 ticket。

## 12. 验证命令

完成实现后至少运行：

```bash
PYTHONPATH="src;." pytest tests/negative/test_runtime_cannot_govern.py -q
PYTHONPATH="src;." pytest tests/execution/test_runtime_executor_boundary.py -q
PYTHONPATH="src;." pytest tests/execution/test_provider_executor.py tests/execution/test_work_product_submission.py tests/execution/test_command_runner.py tests/execution/test_runtime_executor_boundary.py tests/negative/test_provider_executor_fail_closed.py tests/negative/test_runtime_cannot_govern.py -q
PYTHONPATH="src;." pytest tests/contracts tests/reducers tests/execution tests/negative -q
```

## 13. 与现有模块的关系

1. 复用 `ProviderExecutor`（模型供应商执行器），不重新渲染 prompt（提示词）。
2. 复用 `build_work_product_from_provider_attempt` 与 `build_work_product_submitted_event`（工作产物构建与事件工厂）。
3. 复用 `CommandRunner`（命令执行器）和 `VerificationRun`（验证运行）。
4. 复用 `AgentTeamProjection.active_seats`（智能体团队活跃席位投影）做 role-aware boundary。
5. 复用 `EventRecord`（事件记录）和 `EventType`（事件类型），仅新增 runtime fact event factories（运行时事实事件工厂）。
6. 不改 TicketReducer（任务状态归约器）的 completion gate（完成门禁）；V2-050F 再接入正式 evidence/checker 模型。
7. 不改 InMemoryEventLog（内存事件日志）append 规则；RuntimeExecutor 返回事件，由调用方 append。

## 14. 验收映射

本 spec 对应 backlog 工作包：V2-040E。

覆盖 `acceptance-criteria.md` Phase 4：

- Runtime bounded（运行时受限）：由 `tests/negative/test_runtime_cannot_govern.py` 证明 runtime emit governance events 必须失败，且 runtime/executor 不能用普通 seat actor_ref 伪装治理 actor。
- V2-040A ~ V2-040E 五个工作包全部 DONE：V2-040E 完成后可勾选 Phase 4 最后一项并把 Phase 4 进度改为 5/5。
- `backlog.md` 进度总览 Phase 4 显示 5/5：完成协议中更新。

完成 V2-040E 后应按 backlog 完成协议更新：

1. `doc/04-implementation/backlog.md`：V2-040E 状态改为 DONE，当前未完成工作包指向 V2-050A，Phase 4 进度 5/5。
2. `doc/04-implementation/acceptance-criteria.md`：勾选 Runtime bounded、V2-040A ~ V2-040E 全部 DONE、Phase 4 进度 5/5，并勾选 Phase 4 进入下一 Phase 前置。
3. `doc/05-project-log/2026-05.md`：追加 V2-040E 记录，包含 negative / happy tests 和验证命令。
4. `doc/05-project-log/decisions.md`：若 implementation 阶段新增或改变 independent wave 语义，再追加 DEC；若只按本 spec 实现，不需要新增决策。
5. `doc/04-implementation/INDEX.md`：新增本 spec 文档索引项。

## 15. 已收敛评审点

1. 最终仍需要多 ticket runtime loop，但它应由 `execute_package` 组合而来。
2. 多 ticket loop 的语义是同一 graph_version 下 independent wave（独立波次），不是运行时级联推进依赖链。
3. wave 内 ticket 必须是 graph antichain（任务图反链），无直接/间接依赖，也无写集冲突。
4. RuntimeExecutor 只 emit fact events（事实事件），不 emit governance events（治理事件）。
5. runtime actor_ref 不能伪装任何 active AgentSeat.actor_ref，判断依据来自 AgentTeamProjection，而不是字符串前缀。
6. 单包执行入口是未来多 ticket loop 的真子集，不是隔离实现。
