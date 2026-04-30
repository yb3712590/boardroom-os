# 目标架构

## 总览

目标架构把系统压缩成一个小内核和若干 policy/template 层。核心原则是：kernel 只维护真相和执行协议，不硬编码 CEO、员工、业务 milestone、delivery 特例或 provider 厂商细节。

```text
Layer 0  Event Log
Layer 1  Ticket Graph
Layer 2  ProcessAsset / Artifact
Layer 3  Policy Engine
Layer 4  Execution Engine
Layer 5  Workspace / Audit Materializer
Layer 6  Governance Templates
```

## Layer 0: Event Log

职责：

- 只追加记录所有正式动作。
- 提供 replay 的历史输入。
- 记录 idempotency key、actor、action、source version 和 resulting refs。

不负责：

- 当前状态查询。
- 保存大对象正文。
- 业务判断。

关键要求：

- Event schema versioned。
- Event payload 可增量 replay。
- 高频 projection 不得每次全量解析 1GB JSON。
- 人工修补 event/projection 不得作为正常恢复路径。

## Layer 1: Ticket Graph

职责：

- 表达任务、依赖、替换、冻结、review、context lineage 和 closeout 关系。
- 维护 `graph_version`。
- 产生 ready / blocked / critical path / failure heat 等索引。

不负责：

- 自行做业务判断。
- 直接派工。
- 保存长文档正文。

核心对象：

```text
TicketNode
TicketEdge
GraphPatch
GraphVersion
ReadyIndex
FailureHeatIndex
```

## Layer 2: ProcessAsset / Artifact

职责：

- 保存决策、证据、源码交付、测试结果、review verdict、closeout package、project map slice。
- 通过 content hash 和 lineage 维护 supersede 关系。
- 为 Context Compiler 和 Audit Materializer 提供输入。

不负责：

- 直接驱动调度。
- 充当 mutable global memory。

## Layer 3: Policy Engine

职责：

- 根据 graph、assets、incidents、governance profile 计算合法下一步。
- 输出 controlled action list。
- 封装 progression、delivery、checker、closeout、incident recovery 等策略。

核心函数：

```text
decide_next_actions(snapshot, policy) -> ActionProposal[]
validate_action(action, snapshot, policy) -> GuardResult
```

Policy Engine 是从当前 runtime 中拆出的主要目标。它替代散落在 controller、runtime、ticket handler、approval、projection 中的隐式推进规则。

## Layer 4: Execution Engine

职责：

- Scheduler 只处理 ready、lease、timeout、retry wakeup。
- Context Compiler 组装 `CompiledExecutionPackage`。
- Provider adapter 产出标准 event stream。
- Worker/checker 执行 package 并提交结构化结果。
- Validator 做 schema、write-set、evidence 校验。

不负责：

- 判断业务下一步。
- 生成 hardcoded backlog。
- 用 fallback 伪造业务证据。

## Layer 5: Workspace / Audit Materializer

职责：

- 执行目录 contract。
- 维护 workspace refs 与 artifact refs 映射。
- 从 event、projection、asset materialize 人类可读审计文档。
- 生成 closeout package 和 replay bundle。

不负责：

- 让 markdown 反向驱动状态机。
- 让 worker 自由选择写入目录。

## Layer 6: Governance Templates

职责：

- 定义 Board/CEO/Architect/Checker/Engineer 等产品层模板。
- 定义 role template 到 capability 的映射。
- 定义 approval/audit mode。
- 定义可选 visual review、meeting room、board advisory 等高级策略。

不负责：

- 作为 runtime kernel 的硬编码执行键。
- 绕过 graph、policy、write-set、evidence 契约。

## 核心数据流

```text
Trigger
  -> Snapshot
  -> Policy Engine proposes Action[]
  -> Reducer/Guard accepts EventRecord
  -> Projection + TicketGraph update
  -> Scheduler leases READY node
  -> Context Compiler builds package
  -> Worker/Checker executes
  -> Schema/WriteSet/Evidence validation
  -> ProcessAsset/Artifact indexed
  -> Audit docs materialized
  -> Policy Engine evaluates next step
```

## Runtime Kernel 最小认识范围

Kernel 可以认识：

- `EventRecord`
- `TicketNode`
- `TicketEdge`
- `GraphVersion`
- `ProcessAsset`
- `ArtifactRef`
- `ActorId`
- `Capability`
- `Action`
- `PolicyRef`
- `IncidentRecord`
- `RecoveryAction`

Kernel 不应认识：

- `frontend_engineer_primary`
- `backend_engineer_primary`
- `checker_primary`
- `CEO` 作为代码分支条件
- library-management 特定 milestone
- provider 厂商流式协议细节
- closeout provider 输出里的任意 artifact refs

## 与现有代码的关系

现有实现中以下基础应保留：

- 事件日志；
- ticket projection；
- runtime node projection；
- process asset index；
- compiled execution package；
- incident projection；
- live harness 的审计记录能力；
- `00-boardroom / 10-project / 20-evidence` 目录雏形。

以下内容应拆分或降级：

- workflow controller 中的 hardcoded role/schema/fanout 映射；
- runtime 中的 default source/test delivery fallback；
- ticket handler 中的 dispatch、incident、retry、completion 混合逻辑；
- projection 中混合 dashboard、dependency、incident、worker admin 的大模块；
- closeout gate 的重复判断；
- maker-checker verdict 对 failed delivery report 的单点放行。

## 目标架构验收

架构重构不是以文件重排为完成标准，而是以行为边界为准：

- policy 可独立测试。
- provider adapter 可独立 soak test。
- actor lifecycle 可独立测试。
- directory/write-surface 可独立验证。
- deliverable contract 可阻断 placeholder closeout。
- replay/resume 可在无人工 DB/projection 注入下完成。
