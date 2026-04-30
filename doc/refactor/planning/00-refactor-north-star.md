# 自治 Runtime 重构北极星

## 这次重构要解决什么

`boardroom-os` 当前已经具备事件日志、投影、ticket、artifact、process asset、incident 和 compiled execution package 等重要基础，但第 15 轮 live 集成测试表明：系统还不能被视为一个稳定自治、可审计、可重放的执行机器。

015 最终通过人工介入打出了 closeout，但它暴露了这些根本问题：

- runtime 过度纠结 delivery 合法性，且规则散落在 reducer、projection、runtime、ticket handler、approval 和 closeout gate 中。
- workflow progression 存在 hardcoded chain、字符串启发和默认 fanout，而不是显式 policy。
- provider 失败率异常高，且当前证据不能区分上游不稳和本项目 streaming/parser/timeout 实现问题。
- 旧前端、后端、证据目录、runtime 目录和 archive 边界不够硬。
- actor/role/employee/capability 混在一起，角色模板仍在很多地方承担 runtime 执行键职责。
- replay/resume 仍依赖人工理解和投影修补，未成为可验证的一等能力。

本轮重构的目的不是继续往现 runtime 上补 delivery 特例，而是重建更小、更硬、更可验证的自治内核。

## 项目最小身份

`boardroom-os` 是一个事件源、无状态、可审计、可重放的 AI 自治推进机器。

它接收 PRD、约束和验收标准，将其变成 versioned ticket graph，通过受控执行包驱动 worker/checker 产生源码、证据和过程资产，并在任意失败、返工、替换和恢复后，最终收敛为一个可验证的交付物。

## 本轮必须承载的愿景

### 1. 全自动推进

用户只提供目标、约束和验收标准。系统默认继续推进，只有明确阻塞、权限缺失、预算冲突、不可恢复 incident 或需要人类裁量时才升级。

### 2. 事件源真相

正式协作必须落成事件、图边、资产、审批或 incident。文档、dashboard、review room 都是物化视图，不是真相本体。

### 3. 无状态执行

CEO/policy actor 不保存长对话记忆。Worker/checker 不继承隐式历史。每次执行都只读 snapshot、process asset 和 compiled execution package。

### 4. 受控动作

LLM 只能提出 action。Reducer/guard 校验 action 合法性。没有 idempotency key、allowed write set 或 output contract 的动作不能进入执行链路。

### 5. 可审计

每个关键产物必须有 evidence pack、source lineage、review verdict、test/verification evidence 和 closeout 引用。审计文档必须能从事件和资产重新物化。

### 6. 可重放

replay/resume 是正式能力，不依赖人工补写 DB、projection 或 artifact index。恢复动作必须幂等，且可从 event/version/ticket/incident 重新执行。

### 7. 最终交付物契约

closeout 不能只证明 graph 完成。closeout 必须证明 `DeliverableContract` 满足 PRD acceptance criteria，且无 placeholder source/evidence 进入最终证据链。

## 本轮不承载的愿景

以下能力不进入本轮 runtime kernel 重构：

1. 员工人格画像、审美画像和同岗异质性招聘。
2. 董事会审批核心员工人格组合。
3. Boardroom UI 的具体交互和视觉布局。
4. 会议室完整多轮协议。
5. 组织学习自动转化为招聘、派工或审查规则。
6. LanceDB、复杂 RAG 层和长期语义记忆系统。
7. 高级模型成本治理和复杂 provider 路由策略。
8. 通用视觉董事会审核门。
9. 浏览器前端源码和 Boardroom UI 交互壳。

这些能力未来可以作为 policy pack、UI layer 或 plugin 恢复。本轮只保留它们背后的必要抽象：actor、capability、policy、incident、evidence、replay。

## 核心不变量

1. `EventRecord` 是唯一历史真相。
2. `TicketGraph` 是唯一任务结构真相。
3. `ProcessAsset / Artifact` 是唯一产物和证据真相。
4. Projection 和 Markdown 都是物化视图；未来 UI 也只能是物化视图。
5. Runtime kernel 不认识 CEO、员工、具体业务 milestone 或角色名称。
6. Runtime kernel 只认识 actor、capability、ticket、action、policy、asset、incident。
7. Scheduler 不做业务判断，只做 ready、lease、timeout、retry wakeup。
8. Worker 只执行 compiled execution package。
9. Provider adapter 只产出标准 provider event stream，不把厂商协议泄漏进 runtime。
10. Closeout 必须证明 deliverable contract，而不是只证明 ticket 都 terminal。

## 成功定义

重构成功必须同时满足：

- 无人工 DB/projection/event 注入完成 replay/resume。
- 无 placeholder source/evidence 能通过 deliverable closeout。
- provider streaming smoke 在同一 API 配置下达到外部 AI 编程框架同级稳定性。
- runtime kernel 不硬编码 CEO、员工、角色模板或业务 milestone。
- 任意 ticket 的输入、输出、证据、写入面和恢复历史都可追溯。
- 任意当前文档视图都能说明自己的事件/资产来源。

## 非目标

- 不做 AI 公司模拟器。
- 不继续扩大治理拟人化细节。
- 不把 closeout 当作人工投影修补的同义词。
- 不用更多 fallback 掩盖 provider、context、write-set 或 evidence 问题。
- 不在本轮直接重写 backend runtime 行为。
