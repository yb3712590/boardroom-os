# V2-090G Atomic-agent package/import integration spec（atomic-agent 包导入集成规范）

## 状态

Draft for human review（待人工评审）。本文只定义 V2-090G 的实施边界、合同、验收与计划输入；在用户评审通过前不得写生产实现代码。

## 背景

V2-090F Golden sample rebuild（黄金样例重建）已被阻塞。阻塞根因不是 provider timeout（模型供应商超时），而是当前 Boardroom OS（董事会操作系统）只有 `ProviderAttempt`（模型调用尝试记录）事实：它证明发起过一次 LLM request（大模型请求），但不能证明 autonomous agent work（自主智能体工作）已经在受控 workspace（工作区）中读写文件、运行命令、观察失败、多轮修复并归档真实 evidence（证据）。

外部项目 `atomic-agent`（原子智能体）已经完成，V2-090G 实施必须使用 Boardroom OS 同级目录中的项目：

```text
/Users/bill/projects/atomic-agent/
```

只读探索确认该项目已有稳定的 Python package（Python 包）入口和 active contract（活跃契约）：

- `../atomic-agent/pyproject.toml`：`project.name = "atomic-agent"`，`requires-python = ">=3.11"`。
- `../atomic-agent/src/atomic_agent/__init__.py`：导出 `AgentRuntimePort`（智能体运行端口）、`AgentRuntimeRunner`（智能体运行器协议）、`BoardroomAgentRuntimePortAdapter`（Boardroom 适配器）。
- `../atomic-agent/src/atomic_agent/runtime_port.py`：定义 `AgentRuntimePort.invoke(invocation: AgentInvocation) -> AgentRunResult`。
- `../atomic-agent/docs/03-contracts/agent-runtime-port.md`：声明该端口是 Boardroom OS 等上层系统调用 atomic-agent runtime（原子智能体运行时）的稳定边界。
- `../atomic-agent/docs/00-overview/boardroom-os-integration-summary.md`：声明 Boardroom OS 保留 governance/evidence/closeout（治理/证据/收尾）权威，atomic-agent 只负责受控执行实际工作并返回可审计事实。

## 决策

V2-090G 采用 **external Python package import（外部 Python 包导入）+ Boardroom anti-corruption adapter（Boardroom 防腐适配层）** 的路线。

明确不采用以下路线：

1. **不复制源码**：不得把 `atomic_agent` 源码复制进 `src/boardroom_os/`。`../atomic-agent/` 是唯一允许的实施安装来源；`.worktrees/atomic-agent/` 只保留为本轮历史探索副本，不得作为实施安装或验证路径。
2. **不服务化**：V2-090G 不把 atomic-agent 封装成 HTTP/gRPC service（服务）。源码中未发现稳定 service API（服务接口），当前服务化会发明协议并扩大范围。
3. **不把 examples CLI 当作稳定协议**：atomic-agent 的 `examples/minimal_*_loop.py` 可作为测试/门禁参考，但不是正式 CLI contract（命令行契约）。
4. **不让 atomic-agent 做治理决定**：`AgentRunResult.status == completed`（智能体运行完成）只表示 atomic-agent runtime 提交结果，不代表 Boardroom `TICKET_COMPLETED`（任务完成）、`CloseoutPackage.passed`（收尾包通过）或 `CLOSEOUT_COMMITTED`（收尾已提交）。

开发安装方式以 README（项目说明）记录为准：

```bash
cd /Users/bill/projects/boardroom-os
python -m pip install -e ../atomic-agent
python -c "from atomic_agent import AgentRuntimePort; print('atomic-agent import ok')"
```

正式文档必须优先推荐 sibling checkout（同级目录检出）方式：

```text
/Users/bill/projects/boardroom-os
/Users/bill/projects/atomic-agent
```

## 目标

V2-090G 要建立 Boardroom OS 到 atomic-agent 的最小可信执行桥，使 implementation ticket（实施任务）能按以下路径闭合：

```text
ExecutionPackage（执行包）
  -> AtomicAgentInvocation（原子智能体调用）/ atomic_agent.AgentInvocation
  -> atomic_agent.AgentRuntimePort.invoke(...)
  -> atomic_agent.AgentRunResult
  -> AtomicAgentResultProjection（原子智能体结果投影）
  -> Boardroom WorkProduct / EvidenceClaim / SourceInventory lineage / runtime facts
  -> EvidenceVerifier / Checker / Reducer / CloseoutGate
```

本工作包的目标不是重建 V2-090F golden sample（黄金样例），而是解除 V2-090F 的执行器边界阻塞。V2-090G 完成后不得自动恢复或实施 V2-090F；必须先由人工评审 V2-090G 证据，再明确确认是否将 V2-090F 从 BLOCKED（阻塞）恢复为 TODO / IN_PROGRESS（待办 / 进行中）。

## 非目标

- 不发布 atomic-agent 到公共包仓库。
- 不修改 atomic-agent 源码作为 V2-090G 的必要条件。
- 不实现 atomic-agent HTTP service（HTTP 服务）。
- 不新增 Boardroom 自研通用 agent loop（智能体循环）；执行循环由 atomic-agent 提供。
- 不把 atomic-agent 的 event stream（事件流）直接并入 Boardroom EventLog（事件日志）作为治理事件；它应先作为外部 execution evidence（执行证据）被投影和验证。
- 不允许 import 失败时 fallback 到 fake provider（模拟模型供应商）或单次 JSON source delivery（JSON 源码交付）。

## 设计单元

### 1. `AtomicAgentPort`（原子智能体端口）

Boardroom OS 自己定义的最小 Protocol（协议），避免主链直接依赖 atomic-agent 内部实现。

语义：

```text
AtomicAgentPort.invoke(invocation: AtomicAgentInvocation) -> AtomicAgentRunResult
```

第一版可以将 `AtomicAgentInvocation` / `AtomicAgentRunResult` 包装真实 `atomic_agent.models.AgentInvocation` / `AgentRunResult`，但 Boardroom 代码不得直接调用 `AgentLoop`（智能体循环）或内部 tool modules（工具模块）。

### 2. `AtomicAgentPackageAdapter`（原子智能体包适配器）

默认实现，通过 package import（包导入）调用 atomic-agent 公开端口。

职责：

- fail closed 检查 `atomic_agent` 可 import；
- 记录 package provenance（包来源）：version（版本）、source path（源码路径，如可得）、pyproject hash（打包配置哈希，如可得）、runtime port contract ref（运行端口契约引用）；
- 调用 `AgentRuntimePort.invoke(...)`；
- 校验返回值是 `AgentRunResult`；
- 不吞掉 import/runtime/type errors（导入/运行/类型错误）。

### 3. `AtomicInvocationCompiler`（原子调用编译器）

把 Boardroom `ExecutionPackage`（执行包）编译为 atomic-agent `AgentInvocation`（智能体调用）。

字段映射：

| Boardroom 字段 | atomic-agent 字段 | 说明 |
|---|---|---|
| `execution_package_id` | `invocation_id` | 保留可追踪性，可加 `atomic-invocation.` 前缀。 |
| `objective` + constraints + evidence obligations | `task` | 形成 agent-facing task（面向智能体任务），不得包含思维链。 |
| package workspace root（项目工作区根） | `workspace_root` | 必须是 generated package workspace（生成项目工作区）中受控路径。 |
| `allowed_write_set` | `allowed_write_set` | 只传相对路径；禁止绝对路径和 `..`。 |
| `commands` | `permission_policy.commands` | 转成 command id allow-list（命令标识允许列表），禁止自由 shell。 |
| `model_execution_profile` | `provider_profile` | 只传 provider/model/reasoning/temperature 等已审计字段。 |
| `role_prompt_hook` | `role_context` | 包含 hook ref/version/hash 与 prompt text snapshot（提示词快照）。 |
| `context_refs` / skill refs | `skill_context` / `initial_files` / `metadata` | 只传可审计引用，不读取旧实现。 |
| `audit_requirements` / required outputs | `output_requirements` | 要求 event stream、tool attempts、workspace mutations、artifacts。 |

### 4. `AtomicResultProjector`（原子结果投影器）

把 `AgentRunResult` 投影为 Boardroom 可消费的事实和草稿证据。

必须投影：

- `ProviderAttempt` lineage（模型调用来源链）：来自 atomic-agent event stream 中的 provider turn facts（模型轮次事实）或 result summary（结果摘要），不得将 provider text 单独视为 implementation evidence（实施证据）。
- `ToolAttempt` draft（工具尝试草稿）：来自 `tool_attempts` 和 `tool.attempt.*` events（工具尝试事件）。
- `WorkspaceMutation` draft（工作区变更草稿）：来自 `workspace_mutations` 和 `workspace.mutation.recorded` events。
- `WorkProduct` draft（工作产物草稿）：只在 status completed、存在 result submitted（结果提交）、存在 workspace mutation 或明确 no-file-change evidence（无文件变更证据）时生成。
- `EvidenceClaim` draft（证据声明草稿）：绑定 acceptance refs（验收引用）、source surface refs（源码实现面引用）、produced artifacts（产物）和 command evidence refs（命令证据引用）。
- Source inventory lineage input（源码清单来源链输入）：每个变更文件必须能绑定 producer ticket、atomic run id、tool attempt ref、content sha256、acceptance refs 和 evidence refs。

### 5. `AtomicAgentResultValidator`（原子结果校验器）

任何缺失或越权都必须 fail closed：

- `status != completed` 时不得生成 successful `WorkProduct`。
- 缺 `event_stream_ref`、`events_hash`、`tool_attempts`、`artifacts` 时失败。
- implementation ticket（实施任务）缺 workspace mutation 且未声明 deterministic no-file-change output（确定性无文件变更输出）时失败。
- event stream hash（事件流哈希）无法重算或与 `events_hash` 不一致时失败。
- event stream 含 `ticket_completed`、`closeout_committed`、`governance_status`、`evidence_verified`、`source_inventory_accepted` 等治理字段时失败。
- workspace mutation 路径越过 `allowed_write_set` 时失败。
- command result 引用未在 `ExecutionPackage.commands` 中声明的 command id 时失败。
- artifact ref（产物引用）无法解析、sha256 缺失或路径越界时失败。
- import atomic-agent 失败、版本来源不可记录、返回对象类型不匹配时失败。

## Atomic-agent 权威引用

V2-090G spec/plan 和实现必须引用这些实际文件，不得凭记忆或猜测扩展协议：

- `../atomic-agent/docs/03-contracts/agent-runtime-port.md`
- `../atomic-agent/docs/03-contracts/agent-action-protocol.md`
- `../atomic-agent/docs/03-contracts/event-stream-protocol.md`
- `../atomic-agent/docs/00-overview/boardroom-os-integration-summary.md`
- `../atomic-agent/src/atomic_agent/runtime_port.py`
- `../atomic-agent/src/atomic_agent/models.py`
- `../atomic-agent/src/atomic_agent/agent_loop.py`
- `../atomic-agent/src/atomic_agent/evidence.py`
- `../atomic-agent/tests/test_runtime_port.py`
- `../atomic-agent/tests/test_agent_loop.py`

`docs/04-implementation-spec/P2-003-external-coding-agent-bridge-design-spec.md` 只能作为 archived design reference（归档设计参考），不得写成当前已实现能力。

## README 更新要求

V2-090G 实施计划必须包含 README 更新。README 至少需要新增：

1. atomic-agent 是独立项目，不复制到 boardroom-os。
2. 推荐目录布局：`~/projects/boardroom-os` 与 `~/projects/atomic-agent` 同级。
3. 安装命令：`python -m pip install -e ../atomic-agent`。
4. 验证命令：`python -c "from atomic_agent import AgentRuntimePort; print('atomic-agent import ok')"`。
5. 说明 atomic-agent completed（运行完成）不等于 Boardroom closeout passed（收尾通过）。
6. 说明缺 atomic-agent package、缺 event stream、缺 workspace mutation 或缺 command evidence 时 fail closed。

## 验收标准

V2-090G 完成时必须证明：

- Boardroom OS 可以在不复制源码、不调用 service、不依赖示例 CLI 的情况下，通过 package import 调用 atomic-agent public port（公开端口）。
- `ExecutionPackage` 能被确定性编译为 `AgentInvocation`，并保留 role prompt hook、allowed write set、command policy、provider profile、evidence obligations。
- `AgentRunResult` 能被投影为 Boardroom evidence chain（证据链）输入，但不能直接完成 ticket 或 closeout。
- 缺 atomic-agent package、返回类型错误、非 completed 状态、缺 event stream/hash、缺 tool attempts、缺 workspace mutations、命令越权、路径越权、治理字段越权均 fail closed。
- README、backlog、acceptance criteria、INDEX 和 decisions 文档同步。
- V2-090F 的解阻条件从“实现自研 AgentWorkExecutor”更新为“V2-090G atomic-agent package/import integration 通过，且人工评审确认恢复 V2-090F”。

## 自审结果

- Placeholder scan（占位符扫描）：未保留占位符或待补字段；所有未知项均转化为非目标或 fail-closed 要求。
- Consistency check（一致性检查）：与 atomic-agent 当前 active docs 和源码一致；没有把 examples CLI、service API、external coding agent bridge 写成当前能力。
- Scope check（范围检查）：V2-090G 只做 package/import 防腐层、调用编译、结果投影和文档；V2-090F golden sample rebuild 留在后续工作包。
- Constraint check（约束检查）：不复制源码、不新增静默 fallback、不让 atomic-agent 替代 Boardroom reducer/evidence/closeout 权威。
