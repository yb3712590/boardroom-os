# Execution 与 Runtime 边界

## 文档职责

本文件定义 runtime / executor 的职责边界，防止 V2 再次出现 runtime 权力大于 CEO / architect / checker 的问题。

## 核心原则

```text
runtime executes facts; it does not govern the project.
```

runtime 只能执行事实、记录事实、投影事实。runtime 不得创造能满足 implementation contract 的事实。

## Runtime 可以做什么

- 读取 ready ticket；
- 编译或装载 execution package；
- 调用 provider；
- 调用本地工具；
- 运行 declared command；
- 捕获 stdout/stderr/exit code；
- 写 raw output；
- 计算 hash；
- 记录 provider attempt；
- 记录 tool attempt；
- emit typed event；
- 更新 projection。

## Runtime 禁止做什么

- 生成默认 source code delivery；
- 生成默认 verification runs；
- 自动补 acceptance evidence；
- 根据 ticket type 编造 source files；
- 让 provider zero-attempt 的 implementation ticket completed；
- 将 fallback 输出标记为 implementation evidence；
- 决定项目 completed；
- 代替 checker 放行；
- 代替 CEO 发起 closeout。

## ExecutionPackage 必备字段

```yaml
execution_package_id:
ticket_id:
graph_version:
seat_ref:
model_execution_profile:
objective:
acceptance_refs:
source_surface_refs:
context_refs:
constraints:
allowed_read_refs:
allowed_write_set:
required_outputs:
commands:
evidence_obligations:
fallback_policy:
audit_requirements:
```

缺少以上关键字段时，executor 必须 fail closed。

## Provider Attempt

每次 provider-backed ticket 必须有 attempt record：

```yaml
provider_attempt_id:
provider:
model:
reasoning_effort:
input_package_ref:
raw_output_ref:
parsed_output_ref:
status:
started_at:
finished_at:
failure_kind:
```

如果 implementation ticket 的 `required_provider_attempt` 为 true，则 attempt count 为 0 必须阻断 ticket completion。

## Fallback 分类

Fallback 必须显式分类。

| 类型 | 说明 | 可满足 implementation evidence |
|---|---|---|
| `DETERMINISTIC_GOVERNANCE_DRAFT` | 本地生成治理草案 | 否 |
| `TOOLING_PREFLIGHT` | 工具预检 | 否 |
| `PROVIDER_UNAVAILABLE` | provider 不可用时记录失败事实 | 否 |
| `TEST_ONLY_SIMULATION` | 测试环境模拟 | 否，除非测试明确验证失败路径 |
| `CONTRACT_ALLOWED_DETERMINISTIC_TRANSFORM` | 合同允许的 deterministic transform，例如 hash manifest | 仅限该 transform 的 evidence |

## Command Runner

Command runner 是 verification run 的唯一可信来源。

Runner 必须记录：

- command；
- cwd；
- environment profile；
- exit code；
- stdout/stderr refs；
- duration；
- started/finished timestamps；
- workspace snapshot or commit ref。

## 状态变更边界

Executor 可以提交事件：

```text
EXECUTION_STARTED
PROVIDER_ATTEMPT_RECORDED
TOOL_ATTEMPT_RECORDED
WORK_PRODUCT_SUBMITTED
COMMAND_RUN_RECORDED
```

Executor 不可以直接提交：

```text
TICKET_COMPLETED
PROJECT_COMPLETED
CLOSEOUT_COMMITTED
```

这些必须由 reducer 在验证 contract/evidence/checker 条件后产生。

