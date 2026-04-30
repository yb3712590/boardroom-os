# intergration-test-014 整改方案

> **For agentic workers:** 后续独立会话实施本方案时，建议使用 `executing-plans`。步骤使用 checkbox (`- [ ]`) 追踪。每轮只收一个架构问题族。不要把本方案降级成 P02 / P05 / P09 的局部补丁清单。

**目标：** 把 014 暴露的三个高优先级问题，整改为符合新架构的顶层 contract：Worker 无状态、Checker 输入可重编译、交付证据一等化、provider 执行可中断、恢复动作可幂等重放。

**架构：** 先把 source delivery 从“某张票的附带产物”提升为 versioned `ProcessAsset`，再让检查票只消费 `Context Compiler` 编译出的最小证据闭包；最后把 provider streaming 调用收进 `ExecutionAttempt` 边界，确保任何外部调用都不能把 scheduler / recovery 主链卡在内存态。不要用“取最新 ticket”“临时注入 refs”“加长 timeout”修补这个问题族。

**Tech Stack:** Python, pytest, SQLite-backed control-plane repository, boardroom-os runtime, live harness, workflow autopilot, provider OpenAI compat.

---

## 0. 真相源与当前结论

本方案只服务 014：

- 测试报告：`doc/tests/intergration-test-014-20260427.md`
- 参照方案：`doc/tests/intergration-test-012-remediation-plan-20260426.md`
- 参照架构：
  - `doc/new-architecture/00-autonomous-machine-overview.md`
  - `doc/new-architecture/02-ticket-graph-engine.md`
  - `doc/new-architecture/03-worker-context-and-execution-package.md`
  - `doc/new-architecture/05-incident-idempotency-and-recovery.md`
  - `doc/new-architecture/09-process-assets-and-project-map.md`
  - `doc/new-architecture/13-cross-cutting-concerns.md`

必须先接受这个结论：

- 014 没有完成自然收口。用户要求终止 live run，并回退本轮临时修补。
- P02、P05、P09 的临时修补方向能推进测试，但不是最终架构答案。
- P02 和 P05 是同一个上层问题：检查上下文不是由稳定资产合同编译出来，而是由运行链路临场拼引用。
- P09 是另一个上层问题：provider streaming 调用没有被收进可中断、可审计、可重放的执行尝试边界。
- P01、P03、P04、P06、P07、P08 主要是 provider 波动。它们需要审计，但不是本方案的主整改面。

本方案重点对照这些新架构底线：

- `00-autonomous-machine-overview`：节点完成不等于下游可见，必要证据必须落地。
- `02-ticket-graph-engine`：ticket 关系应是 versioned DAG，不能靠“最新票”表达依赖语义。
- `03-worker-context-and-execution-package`：Worker / Checker 无状态，每次只拿封闭执行包。
- `05-incident-idempotency-and-recovery`：错误必须显式变成 incident，恢复动作必须可重放。
- `09-process-assets-and-project-map`：交付证据应是一等 `ProcessAsset`，后续节点消费资产引用和地图切片。
- `13-cross-cutting-concerns`：幂等键、版本、资产引用格式必须统一。

---

## 1. 014 暴露的顶层架构问题

### 1.1 交付证据没有一等化

对应问题：P02、P05。

现象不是“少传了一个 `input_process_asset_refs`”。真正问题是：

- 检查票需要 source delivery 证据，但证据选择规则散落在 controller / CEO payload / latest ticket 查询里。
- “依赖是否完成”和“下游应该读哪份证据”被混在一起。
- checker 票也可能成为某个节点的最新票，但它不是 source delivery 产出方。
- 缺少稳定资产血缘后，系统只能靠票据时间顺序猜上下文。

架构判断：

- source delivery 必须成为 versioned `ProcessAsset`。
- 检查票不能直接消费“某张最新 ticket”。
- 检查票只能消费 `Context Compiler` 基于 graph version、asset version、ProjectMap 切片编译出的证据闭包。
- 资产不存在或版本不匹配时，应打开 `EVIDENCE_GAP` 或 `COMPILER_FAILURE` incident，而不是继续刷失败票。

### 1.2 检查上下文不是可重编译合同

对应问题：P02、P05。

P02 是 checker 没拿到实现票 source delivery。  
P05 是 checker 拿到了 checker 票的伪 source delivery。

两者共同说明：

- 检查输入不是可重复编译的执行包。
- 输入构造过度依赖当前运行链路的局部状态。
- 同一 workflow clean 重启后能推进，不代表 contract 正确。
- 污染场景目录后需要 clean 重启，说明恢复没有做到局部幂等。

架构判断：

- 检查票的输入必须来自 `CompiledExecutionPackage`。
- `CompiledExecutionPackage` 必须能从事件、图和资产索引重建。
- 恢复优先级应是 `RECOMPILE_CONTEXT`，而不是重复创建相同坏输入的 ticket。
- context 编译失败时，应冻结受影响检查节点，不污染全 workflow。

### 1.3 provider streaming 没有执行边界

对应问题：P09。

现象不是“某个 socket read 没 timeout”。真正问题是：

- 外部 provider 调用仍可能把 runner 主线程卡在内存态。
- recovery ticket 已存在，但 scheduler 不能继续 lease。
- incident 进入 `RECOVERING` 后，恢复动作没有获得可执行时间片。
- CEO shadow 与 runtime provider 调用策略没有共享同一执行尝试合同。

架构判断：

- provider 调用必须被建模为 `ExecutionAttempt`。
- 每次 attempt 都要有幂等键、deadline、heartbeat、attempt state、failure fingerprint。
- streaming read 只能是 attempt 内部实现细节，不能成为 scheduler 的阻塞点。
- provider 超时应写事件、开 incident、释放恢复路径，而不是靠进程外人工停止。

---

## 2. 本方案明确不做的事

- [ ] 不写 P02 / P05 / P09 的局部代码修复步骤。
- [ ] 不把 `input_process_asset_refs` 字段继续扩散成通用补丁口。
- [ ] 不靠“节点内倒序查找最近真实 source delivery”作为长期 contract。
- [ ] 不靠加长 provider timeout 换取 live run 通过。
- [ ] 不把 clean 重启当作恢复能力。
- [ ] 不把 provider 波动直接归咎为业务产物失败。
- [ ] 不把 live harness replay 成功当作 production contract 满足。

---

## 3. 三轮整改顺序

### Round 1：把交付证据提升为一等 ProcessAsset

**目标：** source delivery、verification evidence、git evidence 不再是 ticket payload 里的附属字段，而是有版本、有血缘、有消费者的一等 `ProcessAsset`。

**优先级：** P1。必须先做。没有资产真相源，后续 checker context 仍然只能猜。

**架构边界：**

- `TicketGraph` 表达节点完成、review、replacement、supersession。
- `ProcessAsset` 表达交付证据本体。
- `ProjectMap / AssetLineageMap` 表达资产消费链。
- `Context Compiler` 只消费资产和地图，不解析“最新 ticket”语义。

**实施清单：**

- [ ] 定义 `SOURCE_CODE_DELIVERY` 资产的最低合同。
  - 必须包含 source refs、verification refs、git refs、producer ticket、producer node、graph version、content hash。
  - 必须带版本，不允许隐式引用最新版。
  - 必须能从 producer ticket terminal event 重建。

- [ ] 定义 `EVIDENCE_PACK` 资产的最低合同。
  - 必须包含测试命令、原始输出、执行结果、attempt id。
  - 必须能关联到 source delivery 资产。
  - compact / full payload 只是物化格式差异，不改变证据要求。

- [ ] 定义资产可见性状态。
  - `MATERIALIZED`：资产已写入索引。
  - `VALIDATED`：schema、hash、source refs、evidence refs 通过校验。
  - `CONSUMABLE`：可被下游执行包消费。
  - `SUPERSEDED`：被新版本替代，不再作为默认输入。

- [ ] 拆开 dependency gate 和 evidence binding。
  - dependency gate 判断节点是否可进入下一阶段。
  - evidence binding 判断下游执行包应读取哪些资产版本。
  - 两者可以引用同一上游节点，但不能复用同一“最新票”查询。

- [ ] 定义资产选择规则。
  - 选择条件必须基于 asset type、producer node、graph version、consumer node、lineage。
  - 禁止按 ticket 更新时间直接推断 source delivery。
  - checker / review 票不能伪装成 source delivery producer。

- [ ] 定义资产缺失的失败语义。
  - 缺少 source delivery：`EVIDENCE_GAP`。
  - 资产引用不存在：`COMPILER_FAILURE` 或 `EVIDENCE_LINEAGE_BREAK`。
  - 资产版本被替代：触发 `RECOMPILE_CONTEXT`，不继续使用旧包。

**验收标准：**

- 下游检查节点不再需要知道“哪张 ticket 最新”。
- 同一上游节点有 implementation、checker、follow-up 多张票时，资产选择仍稳定。
- 资产索引可重建，重建后得到同一组 consumable assets。
- 被替代的 source delivery 不会被新检查票默认消费。

**建议验证：**

- [ ] 构造同一节点多票历史，确认 source delivery 资产选择不受 checker 票更新时间影响。
- [ ] 删除或隐藏某个 source delivery 资产，确认 compiler fail-closed 并打开结构化 incident。
- [ ] 重放事件生成资产索引，确认 asset refs 和版本不变。

---

### Round 2：让检查输入成为可重编译执行包

**目标：** checker / delivery check 每次启动都拿 `CompiledExecutionPackage`。这个包只由 graph version、ticket node、asset versions、ProjectMap 切片和治理档位编译出来，不继承隐式上下文。

**优先级：** P1。Round 1 后立即做。

**架构边界：**

- CEO 负责发受控动作，不负责手工拼 checker 输入。
- Controller 负责推进状态机，不负责猜证据来源。
- Context Compiler 负责组包，并对缺失资产 fail-closed。
- Checker 只执行包内任务，不自行回查全局历史补上下文。

**实施清单：**

- [ ] 定义 delivery check 的执行包合同。
  - `ticket_ref`：当前 ticket、node、graph version。
  - `task_frame`：检查目标、通过条件、失败条件。
  - `atomic_context_bundle`：source delivery、evidence pack、上游 review verdict。
  - `org_boundary`：上游 producer、下游 consumer、review owner。
  - `output_contract`：checker verdict 或 delivery check report。
  - `idempotency_key`：`exec:{workflow_id}:{ticket_id}:{attempt_no}`。

- [ ] 定义 context 编译幂等键。
  - 建议格式：`compile:{workflow_id}:{ticket_id}:{graph_version}:{asset_digest}`。
  - 同一输入重复编译必须返回同一 package ref。
  - asset digest 变化时必须生成新 package ref。

- [ ] 定义 context stale 检测。
  - package graph version 落后：`PACKAGE_STALE`。
  - asset version 被替代：`PACKAGE_STALE`。
  - required asset 缺失：`EVIDENCE_GAP`。
  - required map slice 缺失：`COMPILER_FAILURE`。

- [ ] 定义检查节点恢复优先级。
  - 第一恢复动作：`RECOMPILE_CONTEXT`。
  - 第二恢复动作：`RETRY_SAME_INPUT`。
  - 第三恢复动作：`REASSIGN_EXECUTOR`。
  - 只有图结构真的错误时才 `PATCH_GRAPH`。

- [ ] 定义失败隔离边界。
  - context 编译失败只冻结当前检查节点及直接依赖它的下游。
  - 不允许同一坏输入反复创建 replacement ticket。
  - 同一 fingerprint 超阈值后进入 incident recovery，不继续刷普通失败票。

- [ ] 定义 live harness 的角色。
  - harness 可以验证执行包可重建。
  - harness 不能成为唯一补齐输入的地方。
  - harness replay 成功不能覆盖原 runner 失败事实。

**验收标准：**

- delivery check 输入可从事件、图、资产索引重建。
- 重建出的 package ref、asset refs、output contract 一致。
- 缺失资产时不创建 checker 垃圾票，不污染 scenario root。
- clean 重启不是必要恢复动作。

**建议验证：**

- [ ] 从同一 workflow snapshot 编译两次 checker package，确认 package digest 一致。
- [ ] 将上游 source delivery 标记 `SUPERSEDED`，确认 checker package 失效并触发重编译。
- [ ] 构造缺失 evidence pack，确认打开 `EVIDENCE_GAP`，且没有重复刷失败 ticket。

---

### Round 3：把 provider 调用收进可中断 ExecutionAttempt

**目标：** provider streaming 是外部不可信调用。它必须被包在有 deadline、heartbeat、幂等键和事件边界的 `ExecutionAttempt` 里，不能阻塞 scheduler 和 recovery 主链。

**优先级：** P1。它解决 P09 暴露的 runner 卡死问题。

**架构边界：**

- Scheduler 管 lease，不直接等待 provider socket。
- Runtime 管 execution attempt，不让 provider 调用逃出 attempt 边界。
- Incident system 管 provider outage 和恢复动作。
- CEO shadow 与普通 Worker provider 调用共享同一 provider policy。

**实施清单：**

- [ ] 定义 `ExecutionAttempt` 合同。
  - `attempt_id`
  - `workflow_id`
  - `ticket_id`
  - `node_id`
  - `attempt_no`
  - `idempotency_key`
  - `provider_policy_ref`
  - `deadline_at`
  - `last_heartbeat_at`
  - `state`
  - `failure_kind`
  - `failure_fingerprint`

- [ ] 定义 attempt 状态机。
  - `CREATED`
  - `LEASED`
  - `PROVIDER_CONNECTING`
  - `STREAMING`
  - `COMPLETED`
  - `FAILED_RETRYABLE`
  - `FAILED_TERMINAL`
  - `TIMED_OUT`
  - `CANCELLED`

- [ ] 定义 heartbeat 和 deadline 规则。
  - connect、first token、stream idle、request total 都必须进入 provider policy。
  - streaming 收到 token 或 chunk 时刷新 heartbeat。
  - 超过 deadline 必须写 attempt timeout event。
  - timeout 后释放 scheduler 主链，交给 incident recovery。

- [ ] 定义 provider failure 到 incident 的映射。
  - first token timeout：`PROVIDER_OUTAGE`。
  - stream idle timeout：`PROVIDER_OUTAGE`。
  - connection reset：`PROVIDER_OUTAGE`。
  - schema validation failed：`CONTRACT_VIOLATION` 或 provider output contract failure。
  - 同 fingerprint 超阈值：打开 circuit，不盲目重试。

- [ ] 定义恢复动作的幂等语义。
  - `RETRY_SAME_INPUT` 使用相同 package ref，新 attempt no。
  - `RECOMPILE_CONTEXT` 使用新 package ref，新 attempt no。
  - `REASSIGN_EXECUTOR` 保留 upstream assets，不复制脏状态。
  - 停止旧 runner 不是正式恢复动作，只能用于人工止血。

- [ ] 统一 CEO shadow provider policy。
  - CEO shadow 也必须使用同一 provider policy ref。
  - 不能只传一个宽泛 `timeout_sec`。
  - reasoning effort、model、provider type、分项 timeout 都应进入 attempt 审计。

**验收标准：**

- provider socket 无响应不会让 runner 进入无事件卡死。
- incident 进入 `RECOVERING` 后，恢复票能被 scheduler 正常 lease。
- 同一 ticket 多次 attempt 有清晰事件链和 failure fingerprint。
- 重启 runner 后能从 attempt / incident 状态恢复，不依赖内存变量。

**建议验证：**

- [ ] 模拟 streaming 卡住，确认 attempt 超时后写事件并释放恢复路径。
- [ ] 模拟 runner 在 streaming 中被终止，重启后确认不会重复提交同一 attempt 副作用。
- [ ] 模拟 CEO shadow provider timeout，确认 failure detail 与普通 worker attempt 走同一审计格式。

---

## 4. 整体架构验收

三轮都完成后，至少要有这些证据：

- [ ] source delivery 和 evidence pack 都是一等资产，并带版本、hash、producer、consumer。
- [ ] checker package 可从 graph + asset index + ProjectMap 重建。
- [ ] 缺失证据会打开 `EVIDENCE_GAP`，不会重复刷坏 ticket。
- [ ] context stale 会触发 `RECOMPILE_CONTEXT`，不会继续执行旧包。
- [ ] provider attempt 有 deadline、heartbeat、failure fingerprint。
- [ ] provider 卡死不会阻塞 scheduler / recovery 主链。
- [ ] live harness 只验证和重放，不承担 production contract 补洞。
- [ ] clean 重启不再是恢复路径的一部分。

可选 live 验证：

```powershell
cd D:\projects\boardroom-os\backend
py -3 -m tests.live.run_configured --config data/live-tests/library_management_autopilot_live_014.toml --clean --max-ticks 240 --timeout-sec 10800
```

live 验证成功时仍要人工核对：

- [ ] workflow 自然推进，没有靠人工 stop / clean / replay 改写结论。
- [ ] check 阶段消费的是 versioned process assets。
- [ ] checker execution package 有稳定 digest。
- [ ] provider timeout 以 attempt event 和 incident 表达。
- [ ] historical failed tickets 被 audit summary 捕获。

---

## 5. 常见误判

- [ ] 不要把“把 refs 传进去”当成架构修复。
- [ ] 不要把“查最近真实 source delivery ticket”当成资产合同。
- [ ] 不要把 dependency gate 和 evidence binding 合并。
- [ ] 不要让 Checker 回查全局历史补上下文。
- [ ] 不要让 CEO payload 携带一堆隐式执行包内容。
- [ ] 不要用 clean 重启证明恢复能力。
- [ ] 不要让 provider socket read 成为 scheduler 生命线。
- [ ] 不要把 provider 波动从 audit summary 里删掉。

---

## 6. 建议后续实施拆分

如果后续会话需要提交，建议按 contract 拆分，不按 P02 / P05 / P09 拆分：

- [ ] `feat(asset): 建立交付证据资产合同`
- [ ] `feat(compiler): 编译检查票执行包`
- [ ] `fix(recovery): 收敛缺证据恢复链`
- [ ] `fix(provider): 建立执行尝试边界`
- [ ] `test(live): 验证014恢复不依赖clean重启`

不要把三轮混成一个提交。
