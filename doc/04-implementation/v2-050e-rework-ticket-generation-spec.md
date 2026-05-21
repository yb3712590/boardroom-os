# V2-050E Rework Ticket Generation 设计 Spec

## 1. 现实场景

本轮对应的现实场景是：worker（实施智能体）提交了 WorkProduct（工作产物），EvidenceVerifier（证据验证器）和 FinalEvidenceTable（最终证据表）已经发现某些 blocking acceptance criteria（阻塞验收项）缺证据或证据失败，CheckerVerdict（检查结论）也输出了 `rework_required`（需要返工）。此时系统不能只在检查报告里写一句“有问题”，也不能等到 closeout（收尾）阶段才第一次暴露缺口，而必须在 ticket graph（任务图）里创建可派发、可审计、可重放的 rework ticket（返工任务），并同时阻塞原 ticket（任务）。

通俗地说，V2-050D CheckerVerdict（检查结论）像“质检报告”，指出哪里不合格；V2-050E ReworkTicketGenerator（返工任务生成器）像“维修工单系统”，把质检报告里的每个阻断问题转换成工程团队能执行的返工任务，并把原来的工单标记为“返工中，不能结案”。这样后续 CEO / Architect / Worker / Checker（治理者 / 架构师 / 实施者 / 检查者）看到的是 graph（任务图）里的明确待办，而不是散落在备注里的问题。

## 2. 目标

实现 rework ticket（返工任务）触发的最小边界：

1. 定义 ReworkTicketPlan（返工任务计划）作为 checker/rework 阶段的 typed planning artifact（类型化规划产物）。
2. 从 `CheckerVerdict(status=rework_required)`（检查结论：需要返工）派生一个新的 `TicketCreatedPayload`（任务创建载荷），表示 graph（任务图）中的 rework ticket（返工任务）。
3. 同时派生原 ticket（原任务）的 `TicketCheckSnapshot`（检查快照）和 `TicketRefPayload`（任务引用载荷），使调用方可写入 `TICKET_CHECKED`（任务已检查）和 `TICKET_REWORKED`（任务已返工）事件后由 TicketReducer（任务状态归约器）阻塞原 ticket。
4. 确保任何 blocking gap（阻塞缺口）都必须生成 rework output（返工输出）；不能只返回 notes（备注）或空 plan（空计划）。
5. 确保 rework ticket（返工任务）继承必要的 `acceptance_refs`（验收引用）、`source_surface_refs`（源码实现面引用）、`evidence_obligations`（证据义务）和 `allowed_write_set`（允许写入集合）。
6. 确保 rework ticket 明确绑定 original ticket（原任务）、checker verdict（检查结论）和 blocker refs（阻断引用）。
7. 保持 V2-050E 只做 rework planning（返工规划）与 reducer payload preparation（归约器载荷准备），不直接 append EventLog（事件日志）、不修改 TicketGraph（任务图）、不决定 ticket completed（任务完成）。

## 3. 非目标

V2-050E 不做以下事情：

1. 不重新验证 EvidenceClaim（证据声明）、VerifiedEvidence（已验证证据）、artifact hash（产物哈希）、provider attempt（模型调用尝试记录）或 VerificationRun（验证运行）；这些属于 V2-050B EvidenceVerifier（证据验证器）。
2. 不构建 FinalEvidenceTable（最终证据表）；这些属于 V2-050C。
3. 不产出 CheckerVerdict（检查结论）；这些属于 V2-050D。
4. 不直接写 EventLog（事件日志），不负责 graph_version sequencing（图版本排序），不生成 EventRecord（事件记录）。事件创建和 append 由调用方或后续 orchestration（编排）负责。
5. 不直接调用 TicketReducer（任务状态归约器）修改 TicketGraph（任务图）；它只产出 reducer 可消费的 typed payload（类型化载荷）。
6. 不完成原 ticket 或 rework ticket；completion gate（完成门禁）属于 V2-050F。
7. 不决定 rework ticket 的具体 AgentSeat assignment（智能体席位派工）；seat assignment（席位分配）仍由既有 graph / assignment 流程处理。
8. 不生成新的 AcceptanceContract（验收合同）或 PackageContract（包合同）。返工必须在当前 active contract（活跃合同）边界内进行。
9. 不构建 SourceInventory（源码清单）；source lineage（源码来源链）由 V2-060C 证明。
10. 不读取旧 runtime（旧运行时）、旧 contracts（旧合同）或旧测试作为实现依据。

## 4. 选型结论

采用“三件套闭环”方案：ReworkTicketGenerator（返工任务生成器）输出 ReworkTicketPlan（返工任务计划）、新 rework ticket 的 TicketCreatedPayload（任务创建载荷）、原 ticket 的 TicketCheckSnapshot（检查快照）和 TicketRefPayload（任务引用载荷）。调用方可把这些 payload（载荷）分别落成 `TICKET_CREATED`、`TICKET_CHECKED`、`TICKET_REWORKED` 事件，交由 TicketReducer（任务状态归约器）生成可审计状态。

### 4.1 被采用方案：新建返工单并阻塞原单

输入：

- 原 TicketNode（任务节点）
- CheckerVerdict（检查结论）
- 可选 rework_overrides（返工覆盖项），仅允许收窄 purpose（目的）、allowed_read_refs（允许读取引用）和 allowed_write_set（允许写入集合）
- generated_at（生成时间）

输出：

- ReworkTicketPlan（返工任务计划）
- `TicketCreatedPayload`（新 rework ticket 创建载荷）
- `TicketCheckSnapshot(checker_approved=False, blocking_issue_refs=...)`（原任务检查快照）
- `TicketRefPayload(ticket_id=<original_ticket_id>)`（原任务返工引用）

优点：

- 精确符合用户确认的语义：“新建返工单并阻塞原单”。
- 复用现有 `TicketReducer` 的 `TICKET_CHECKED -> TICKET_REWORKED -> BLOCKED` 语义，不另造 parallel graph state（平行任务图状态）。
- rework ticket（返工任务）是 graph（任务图）中的正式 ticket，可被后续 seat assignment（席位分配）、ExecutionPackage compiler（执行包编译器）、EvidenceVerifier（证据验证器）和 Checker（检查者）继续消费。
- 缺口在 checker/rework 阶段显式暴露，不留到 closeout（收尾）首次发现。

代价：

- V2-050E 要定义更严格的 fail-closed 输入边界，防止 rework ticket 丢失 acceptance/evidence/source lineage（验收 / 证据 / 源码来源链）。
- 调用方仍需负责 EventRecord（事件记录）创建、graph_version（图版本）排序和 event log append（事件日志追加）。

### 4.2 未采用方案：只新建返工单

只输出 ReworkTicketPlan（返工任务计划）和 TicketCreatedPayload（任务创建载荷），不产出原 ticket 的 `TICKET_CHECKED` / `TICKET_REWORKED` payload（载荷）。

不采用原因：原 ticket（原任务）可能仍保持 ready（就绪）或可被误判为可完成；这会削弱 “reducer-protected transitions（受归约器保护的状态转换）” 约束。

### 4.3 未采用方案：只阻塞原单

只复用 `TICKET_REWORKED`（任务已返工）阻塞原 ticket，不生成独立 rework ticket（返工任务）。

不采用原因：不满足 backlog（待办）中“转换成 graph 中的 rework ticket”的要求，也不利于后续派工、审计和 process audit（流程审计）。

### 4.4 未采用方案：事件工厂式

V2-050E 直接输出 `EventRecord`（事件记录），包括 `TICKET_CREATED`、`TICKET_CHECKED`、`TICKET_REWORKED`。

不采用原因：会让 V2-050E 提前承担 event sequencing（事件排序）、project_ref（项目引用）、actor_ref（参与者引用）和 causation/correlation（因果 / 关联引用）职责。当前更稳妥的边界是只产出 typed payload（类型化载荷），事件工厂留给 orchestrator（编排器）或后续工作包。

## 5. 已决实施决定

1. V2-050E 新增 `src/boardroom_os/checker/rework.py`。
2. ReworkTicketGenerator（返工任务生成器）只接受 `CheckerVerdict.status == rework_required` 的 CheckerVerdict（检查结论）。`approved`、`approved_with_non_blocking_notes` 和 `escalate` 都不得生成 implementation rework ticket（实施返工任务）。
3. ReworkTicketGenerator（返工任务生成器）只接受 existing original TicketNode（既有原任务节点），不接受裸 dict（字典）或只传 ticket_id 的 shortcut（捷径）。
4. 原 ticket 必须不是 `completed`（已完成）。已完成 ticket 的返工需要后续 governance reopen（治理重开）语义，V2-050E 不实现。
5. 原 ticket 必须具备非空 `acceptance_refs`、`source_surface_refs`、`evidence_obligations`、`allowed_write_set`，即使 TicketNode（任务节点）已有校验，V2-050E 边界仍需 fail closed（失败关闭）拒绝畸形对象。
6. CheckerVerdict.ticket_ref（检查结论任务引用）必须等于 original TicketNode.ticket_id（原任务 ID）。
7. CheckerVerdict.blockers（检查结论阻断项）必须非空，并且每个 blocker 必须有 `blocker_id`、`code`、`message`、`related_ref`、`source`。
8. `final_evidence_missing` / `final_evidence_failed` 来源的 blocker 必须携带 acceptance_ref（验收引用）；work-product-level checker blocker（工作产物级检查阻断项）允许 acceptance_ref 为空，但不能单独生成无验收范围的 rework ticket。
9. 只要 CheckerVerdict（检查结论）中的任一 blocker 绑定了 acceptance_ref，该 acceptance_ref 必须属于 original ticket.acceptance_refs（原任务验收引用）。未知 acceptance_ref 必须 fail closed。
10. Rework ticket（返工任务）的 `acceptance_refs` 必须等于相关 blocker acceptance refs 与原 ticket acceptance refs 的交集；如果所有 blockers 都无 acceptance_ref，则 rework ticket 继承原 ticket 全部 acceptance_refs。
11. Rework ticket（返工任务）的 `source_surface_refs` 必须继承原 ticket.source_surface_refs，不允许生成空 source surface（源码实现面）。
12. Rework ticket（返工任务）的 `evidence_obligations` 必须至少保留原 ticket.evidence_obligations 中与 rework acceptance_refs 相关的 obligation（证据义务）。首版若无法可靠解析 obligation -> acceptance_ref 映射，则继承原 ticket 全部 evidence_obligations；不得输出空 evidence_obligations。
13. Rework ticket（返工任务）的 `allowed_write_set` 默认继承原 ticket.allowed_write_set；可通过 overrides（覆盖项）收窄，但不得扩展到原 write set（写入集合）之外。
14. Rework ticket（返工任务）的 `allowed_read_refs` 默认包括原 ticket.allowed_read_refs、CheckerVerdictRef（检查结论引用）、FinalEvidenceTableRef（最终证据表引用）、WorkProductRef（工作产物引用）和所有 CheckerBlockerRef（检查阻断引用）。
15. Rework ticket（返工任务）默认不设置 `depends_on`（依赖），即 `depends_on=()`。现有 TicketGraph（任务图）只把 completed dependency（已完成依赖）视为满足；若 rework ticket 依赖被 `TICKET_REWORKED` 阻塞的原 ticket，会造成 rework ticket 永远进不了 ready_queue（就绪队列）。Lineage（来源链）由 ReworkTicketPlan.original_ticket_ref（返工任务计划原任务引用）和 allowed_read_refs（允许读取引用）表达；首版不引入专用 rework edge（返工边）。
16. Rework ticket（返工任务）的 `seat_demand` 默认继承原 ticket.seat_demand，表示返工通常由同类 implementation capability（实施能力）处理。V2-050E 不切换到 checker/architect seat（检查 / 架构席位）。这是首版保守选择；未来如需把“补测试”等窄场景派给更细 capability（能力），应另行扩展 seat demand narrowing（席位需求收窄）规则。
17. Rework ticket id（返工任务 ID）必须 deterministic（确定性）：`rework.<original_ticket_id>.<checker_verdict_id>`。若该 ID 过长或含不适合字符，implementation（实施）可使用稳定 sha256 digest（稳定 SHA-256 摘要）派生，但 spec 层仍要求相同输入产出相同 ID。
18. ReworkTicketPlan（返工任务计划）必须记录 original_ticket_ref（原任务引用）、rework_ticket_ref（返工任务引用）、checker_verdict_ref（检查结论引用）、final_evidence_table_ref（最终证据表引用）、work_product_ref（工作产物引用）、blocker_refs（阻断引用）、acceptance_refs（验收引用）、source_surface_refs（源码实现面引用）、evidence_obligations（证据义务引用）、generated_at（生成时间）。
19. ReworkTicketPlan（返工任务计划）不包含 notes（备注）作为放行依据；notes 仅可作为 allowed_read_refs（允许读取引用）或 audit refs（审计引用）间接存在。
20. ReworkTicketGenerator（返工任务生成器）必须生成 `TicketCheckSnapshot(checker_approved=False, blocking_issue_refs=<checker blocker ids>)`，供 `TICKET_CHECKED` 事件 payload（载荷）使用。
21. ReworkTicketGenerator（返工任务生成器）必须生成 `TicketRefPayload(ticket_id=<original_ticket_id>)`，供 `TICKET_REWORKED` 事件 payload（载荷）使用。
22. V2-050E 不引入新的 EventType（事件类型）。现有 `TICKET_CREATED`、`TICKET_CHECKED`、`TICKET_REWORKED` 已足够表达本包边界。
23. V2-050E 不修改 TicketReducer（任务状态归约器）；测试中可以用现有 TicketReducer 验证 payload（载荷）落成事件后的原 ticket blocked（阻塞）行为。
24. V2-050E 不修改 CheckerService（检查服务）或 CheckerVerdict（检查结论）结构，除非同行评审发现 blocker refs 无法可靠消费。
25. Rework generation（返工生成）必须是 deterministic（确定性）的：相同 original ticket、checker verdict、overrides 和 generated_at 之外的稳定输入，应生成相同 rework_ticket_id、purpose、refs 和 payload shape（载荷形状）。

## 6. 模块设计

### 6.1 `src/boardroom_os/checker/rework.py`

新增 value objects（值对象）、schema（结构）和 service（服务）：

- `ReworkTicketGenerationError`（返工任务生成错误）
- `ReworkTicketPlanRef`（返工任务计划引用）
- `ReworkTicketPlan`（返工任务计划）
- `ReworkTicketGenerationInput`（返工任务生成输入）
- `ReworkTicketGenerationResult`（返工任务生成结果）
- `ReworkTicketOverrides`（返工任务覆盖项，可选）
- `ReworkTicketGenerator`（返工任务生成器）

### 6.2 ReworkTicketPlan

建议 schema：

```yaml
version: 1
rework_plan_id:
original_ticket_ref:
rework_ticket_ref:
checker_verdict_ref:
final_evidence_table_ref:
work_product_ref:
blocker_refs:
acceptance_refs:
source_surface_refs:
evidence_obligations:
allowed_write_set:
generated_at:
```

字段说明：

- `rework_plan_id`：ReworkTicketPlanRef（返工任务计划引用），建议 deterministic id：`rework-plan.<rework_ticket_ref>`。
- `original_ticket_ref`：TicketId（原任务 ID）。
- `rework_ticket_ref`：TicketId（返工任务 ID）。
- `checker_verdict_ref`：CheckerVerdictRef（检查结论引用）。
- `final_evidence_table_ref`：FinalEvidenceTableRef（最终证据表引用）。
- `work_product_ref`：WorkProductRef（工作产物引用）。
- `blocker_refs`：tuple[CheckerBlockerRef, ...]（检查阻断引用集合）。
- `acceptance_refs`：tuple[str, ...]，与 TicketCreatedPayload（任务创建载荷）保持当前 graph 层字符串字段一致。
- `source_surface_refs`：tuple[str, ...]。
- `evidence_obligations`：tuple[str, ...]。
- `allowed_write_set`：tuple[str, ...]。
- `generated_at`：timezone-aware datetime（带时区时间）。

不变量：

1. original_ticket_ref、rework_ticket_ref、checker_verdict_ref、final_evidence_table_ref、work_product_ref 必须非空。
2. rework_ticket_ref 不得等于 original_ticket_ref。
3. blocker_refs、acceptance_refs、source_surface_refs、evidence_obligations、allowed_write_set 均不得为空。
4. generated_at 必须带时区。
5. rework_plan_id 必须由 rework_ticket_ref 派生。
6. 任意 extra fields（额外字段）必须 fail closed（失败关闭）。

### 6.3 ReworkTicketOverrides

建议 schema：

```yaml
purpose:
allowed_read_refs:
allowed_write_set:
```

字段说明：

- `purpose`：可选非空文本，用于替换默认 purpose（目的）。
- `allowed_read_refs`：可选 tuple[str, ...]，用于追加 rework ticket（返工任务）允许读取上下文。不得为空字符串；所有 CheckerVerdictRef（检查结论引用）、FinalEvidenceTableRef（最终证据表引用）、WorkProductRef（工作产物引用）和 CheckerBlockerRef（检查阻断引用）都必须用 `.value` 字符串写入，不能把 value object（值对象）直接放进 graph payload（任务图载荷）。
- `allowed_write_set`：可选 tuple[str, ...]，用于收窄原 ticket allowed_write_set（允许写入集合）。不得包含原 ticket write set 外的新路径。

首版不允许 overrides 修改 `acceptance_refs`、`source_surface_refs`、`evidence_obligations` 或 `seat_demand`，避免调用方绕过 evidence obligations（证据义务）。

### 6.4 ReworkTicketGenerationInput

建议 schema：

```yaml
original_ticket:
checker_verdict:
overrides:
generated_at:
```

字段说明：

- `original_ticket`：TicketNode（任务节点），必须是 typed model（类型化模型）。
- `checker_verdict`：CheckerVerdict（检查结论），必须 status=`rework_required`。
- `overrides`：ReworkTicketOverrides（返工覆盖项），可为空。
- `generated_at`：timezone-aware datetime（带时区时间）。

Input 不接受 `final_evidence_table`、`verified_evidence`、`evidence_claims`、`force_rework`、`force_ready`、`completion_snapshot` 等额外字段。

### 6.5 ReworkTicketGenerationResult

建议 schema：

```yaml
plan:
rework_ticket_payload:
original_ticket_check_snapshot:
original_ticket_reworked_payload:
```

字段说明：

- `plan`：ReworkTicketPlan（返工任务计划）。
- `rework_ticket_payload`：TicketCreatedPayload（返工任务创建载荷），供 `TICKET_CREATED` 使用。
- `original_ticket_check_snapshot`：TicketCheckSnapshot（原任务检查快照），供 `TICKET_CHECKED` 使用。
- `original_ticket_reworked_payload`：TicketRefPayload（原任务引用载荷），供 `TICKET_REWORKED` 使用。

不变量：

1. `rework_ticket_payload.ticket_id == plan.rework_ticket_ref`。
2. `original_ticket_check_snapshot.ticket_id == plan.original_ticket_ref`。
3. `original_ticket_reworked_payload.ticket_id == plan.original_ticket_ref`。
4. `original_ticket_check_snapshot.checker_approved is False`。
5. `original_ticket_check_snapshot.blocking_issue_refs == tuple(ref.value for ref in plan.blocker_refs)`。
6. `rework_ticket_payload.acceptance_refs == plan.acceptance_refs`。
7. `rework_ticket_payload.source_surface_refs == plan.source_surface_refs`。
8. `rework_ticket_payload.evidence_obligations == plan.evidence_obligations`。
9. `rework_ticket_payload.allowed_write_set == plan.allowed_write_set`。

## 7. Generator 行为

ReworkTicketGenerator.generate(input)（返工任务生成函数）执行以下步骤：

1. 校验 input 是 ReworkTicketGenerationInput（返工任务生成输入）。
2. 校验 generated_at（生成时间）带时区。
3. 校验 original_ticket 是 TicketNode（任务节点）。
4. 校验 original_ticket.status 不是 `completed`。
5. 校验 original_ticket.acceptance_refs、source_surface_refs、evidence_obligations、allowed_write_set 非空。
6. 校验 checker_verdict 是 CheckerVerdict（检查结论）。
7. 校验 checker_verdict.status 是 `rework_required`。
8. 校验 checker_verdict.ticket_ref 等于 original_ticket.ticket_id。
9. 校验 checker_verdict.blockers 非空。
10. 提取 blocker_refs（阻断引用）。任何 blocker 缺 blocker_id 必须 fail closed（失败关闭）。
11. 对携带 acceptance_ref 的 blockers，校验其 acceptance_ref 属于 original_ticket.acceptance_refs。
12. 对 `final_evidence_missing` / `final_evidence_failed` blocker，要求 acceptance_ref 非空。
13. 计算 rework_acceptance_refs：若 blockers 中存在 acceptance_ref，则取这些 acceptance_ref 的稳定去重序列；否则继承 original_ticket.acceptance_refs。
14. 计算 rework_source_surface_refs：继承 original_ticket.source_surface_refs。
15. 计算 rework_evidence_obligations：首版继承 original_ticket.evidence_obligations，除非后续 implementation 能从 typed EvidenceObligation（证据义务）建立可靠 acceptance_ref 映射并保持非空。
16. 计算 rework_allowed_write_set：默认继承 original_ticket.allowed_write_set；若 overrides.allowed_write_set 存在，则必须是原 allowed_write_set 的子集或精确路径收窄，不得扩展。
17. 计算 allowed_read_refs：合并 original_ticket.allowed_read_refs、checker_verdict_id.value、final_evidence_table_ref.value、work_product_ref.value、blocker_refs 的 `.value` 字符串；若 overrides.allowed_read_refs 存在，只允许追加非空审计引用，不得删除 checker verdict / table / work product / blocker refs。
18. 构造 deterministic rework_ticket_id：`rework.<original_ticket_id>.<checker_verdict_id>` 或等价稳定 digest 形式。
19. 构造默认 purpose（目的）：`Rework <original purpose> for checker blockers: <codes>`。若 overrides.purpose 存在，使用 override，但仍应包含或可追踪 original ticket 与 blocker refs。
20. 构造 ReworkTicketPlan（返工任务计划）。
21. 构造 TicketCreatedPayload（任务创建载荷）：
    - ticket_id = rework_ticket_ref
    - purpose = computed purpose
    - seat_demand = original_ticket.seat_demand
    - depends_on = ()
    - acceptance_refs = rework_acceptance_refs
    - source_surface_refs = rework_source_surface_refs
    - evidence_obligations = rework_evidence_obligations
    - allowed_read_refs = computed allowed_read_refs
    - allowed_write_set = rework_allowed_write_set
    - attempt_count = 0
22. 构造 TicketCheckSnapshot（检查快照）：
    - ticket_id = original_ticket.ticket_id
    - checker_approved = False
    - blocking_issue_refs = blocker_refs string values
23. 构造 TicketRefPayload（任务引用载荷）：
    - ticket_id = original_ticket.ticket_id
24. 返回 ReworkTicketGenerationResult（返工任务生成结果）。

关键点：Generator（生成器）不 append events（追加事件），也不排序 graph_version（图版本）。它只保证 payload（载荷）足够让调用方生成 `TICKET_CREATED`、`TICKET_CHECKED`、`TICKET_REWORKED` 事件后交给 reducer（状态归约器）。

## 8. 数据流

```text
CheckerVerdict（检查结论）
  status = rework_required
  blockers -> blocker_refs / acceptance_refs

TicketNode（原任务节点）
  -> seat_demand（席位需求）
  -> source_surface_refs（源码实现面引用）
  -> evidence_obligations（证据义务）
  -> allowed_write_set（允许写入集合）

ReworkTicketGenerator（返工任务生成器）
  -> ReworkTicketPlan（返工任务计划）
  -> TicketCreatedPayload（新返工任务）
  -> TicketCheckSnapshot（原任务检查失败快照）
  -> TicketRefPayload（原任务返工引用）

Caller / orchestrator（调用方 / 编排器）
  -> EventRecord: TICKET_CREATED(rework ticket)
  -> EventRecord: TICKET_CHECKED(original ticket)
  -> EventRecord: TICKET_REWORKED(original ticket)
  -> TicketReducer（任务状态归约器）
  -> original ticket BLOCKED（原任务阻塞） + rework ticket in graph（返工任务进入任务图）
```

## 9. Fail-closed 规则

以下情况必须失败，不得生成 rework ticket（返工任务）或原 ticket reworked payload（原任务返工载荷）：

1. original_ticket 不是 TicketNode（任务节点）实例。
2. checker_verdict 不是 CheckerVerdict（检查结论）实例。
3. checker_verdict.status 不是 `rework_required`。
4. checker_verdict.status 是 `approved` 或 `approved_with_non_blocking_notes` 却试图生成 rework。
5. checker_verdict.status 是 `escalate` 却试图生成 implementation rework ticket（实施返工任务）。
6. checker_verdict.ticket_ref 与 original_ticket.ticket_id 不一致。
7. checker_verdict.blockers 为空。
8. 任一 blocker 缺 blocker_id。
9. 任一 `final_evidence_missing` / `final_evidence_failed` blocker 缺 acceptance_ref。
10. 任一 blocker.acceptance_ref 不属于 original_ticket.acceptance_refs。
11. original_ticket.status 是 `completed`。
12. original_ticket.acceptance_refs 为空。
13. original_ticket.source_surface_refs 为空。
14. original_ticket.evidence_obligations 为空。
15. original_ticket.allowed_write_set 为空。
16. 生成的 rework ticket 缺 acceptance_refs。
17. 生成的 rework ticket 缺 source_surface_refs。
18. 生成的 rework ticket 缺 evidence_obligations。
19. 生成的 rework ticket 缺 allowed_write_set。
20. overrides.allowed_write_set 扩展到 original_ticket.allowed_write_set 之外。
21. overrides.allowed_read_refs 删除 checker_verdict_ref、final_evidence_table_ref、work_product_ref 或 blocker_refs 等必要审计引用。
22. generated_at 无时区。
23. ReworkTicketPlan（返工任务计划）字段与 TicketCreatedPayload（任务创建载荷）不一致。
24. TicketCheckSnapshot（检查快照）没有把 checker_approved 设为 False。
25. TicketCheckSnapshot.blocking_issue_refs 与 checker blocker refs 不一致。
26. TicketRefPayload.ticket_id 不是 original_ticket.ticket_id。
27. rework_ticket_id 与 original_ticket_id 相同。
28. rework_ticket_id 非 deterministic（非确定性）。
29. 输入中出现 `force_ready`、`force_rework`、`completion_snapshot` 或 evidence override（证据覆盖）字段。
30. 生成器试图直接创建 EventRecord（事件记录）或修改 TicketGraph（任务图）。

## 10. Happy path

### 10.1 Missing test evidence 生成返工任务并阻塞原任务

1. 原 TicketNode（任务节点）代表 backend API implementation ticket（后端 API 实施任务）。
2. CheckerVerdict（检查结论）状态为 `rework_required`，包含一个 `final_evidence_missing` blocker（最终证据缺失阻断项），acceptance_ref 指向缺失的 test evidence（测试证据）。
3. ReworkTicketGenerator（返工任务生成器）生成 ReworkTicketPlan（返工任务计划）。
4. 生成的新 TicketCreatedPayload（任务创建载荷）继承原 ticket 的 source_surface_refs、evidence_obligations 和 allowed_write_set，并把 acceptance_refs 收窄到缺失证据相关 refs。
5. 生成的 TicketCheckSnapshot（检查快照）把原 ticket 标记为 checker_approved=False，blocking_issue_refs 指向 blocker_id。
6. 生成的 TicketRefPayload（任务引用载荷）指向原 ticket。
7. 调用方若把三者落成 `TICKET_CREATED`、`TICKET_CHECKED`、`TICKET_REWORKED` 事件，TicketReducer（任务状态归约器）应把原 ticket 置为 `BLOCKED`，并且 rework ticket 因 `depends_on=()` 保持可进入 ready_queue（就绪队列）。

### 10.2 Failed evidence 生成返工任务

1. FinalEvidenceTable（最终证据表）中某 acceptance_ref 对应 failed evidence（失败证据）。
2. CheckerService（检查服务）生成 `final_evidence_failed` blocker。
3. ReworkTicketGenerator（返工任务生成器）生成 rework ticket（返工任务），purpose 中可读地说明 blocker code（阻断代码）和 related_ref（关联引用）。
4. rework ticket 保留 blocker_refs 和 final_evidence_table_ref 作为 allowed_read_refs（允许读取引用）。

### 10.3 Checker manual blocker 生成返工任务

1. FinalEvidenceTable.complete（最终证据表完成标记）为 true。
2. Checker（检查者）发现 source diff（源码差异）与 WorkProduct summary（工作产物摘要）不一致，传入 `checker_blocker`。
3. CheckerVerdict（检查结论）为 `rework_required`。
4. 若 blocker 没有 acceptance_ref，ReworkTicketGenerator（返工任务生成器）继承原 ticket 全部 acceptance_refs，避免生成无验收范围的返工任务。

### 10.4 Overrides 只允许收窄写入范围

1. 原 ticket.allowed_write_set 包含 `10-project/backend/**` 和 `10-project/tests/**`。
2. overrides.allowed_write_set 指定 `10-project/tests/**`。
3. Rework ticket allowed_write_set 收窄为 `10-project/tests/**`。
4. 若 overrides 指定 `10-project/frontend/**`，生成器必须失败。

## 11. 测试计划

新增测试：

- `tests/evidence/test_rework_ticket_generation.py`

由于 backlog（待办）只声明一个测试文件，V2-050E 的 negative tests（负例测试）和 happy path tests（正向测试）都放在该文件内；文件内必须用清晰 section comments（章节注释）分隔 negative section（负例段）和 happy path section（正例段），避免单文件过长后难以审阅。

### 11.1 Negative tests（先写）

`tests/evidence/test_rework_ticket_generation.py`：

1. `test_rework_generator_rejects_approved_verdict`
2. `test_rework_generator_rejects_approved_with_notes_verdict`
3. `test_rework_generator_rejects_escalate_verdict`
4. `test_rework_generator_rejects_ticket_verdict_mismatch`
5. `test_rework_generator_rejects_verdict_without_blockers`
6. `test_rework_generator_rejects_blocker_without_id`
7. `test_final_evidence_missing_blocker_requires_acceptance_ref`
8. `test_final_evidence_failed_blocker_requires_acceptance_ref`
9. `test_rework_generator_rejects_unknown_blocker_acceptance_ref`
10. `test_rework_generator_rejects_completed_original_ticket`
11. `test_rework_generator_rejects_malformed_ticket_without_acceptance_refs`
12. `test_rework_generator_rejects_malformed_ticket_without_source_surfaces`
13. `test_rework_generator_rejects_malformed_ticket_without_evidence_obligations`
14. `test_rework_generator_rejects_malformed_ticket_without_allowed_write_set`
15. `test_rework_ticket_payload_requires_acceptance_refs`
16. `test_rework_ticket_payload_requires_evidence_obligations`
17. `test_rework_ticket_payload_requires_source_surface_refs`
18. `test_rework_ticket_payload_requires_allowed_write_set`
19. `test_rework_overrides_cannot_expand_allowed_write_set`
20. `test_rework_overrides_cannot_drop_required_audit_refs`
21. `test_rework_generator_rejects_naive_generated_at`
22. `test_rework_result_rejects_plan_payload_mismatch`
23. `test_rework_check_snapshot_must_mark_checker_not_approved`
24. `test_rework_check_snapshot_must_preserve_blocking_issue_refs`
25. `test_rework_ref_payload_must_point_to_original_ticket`
26. `test_rework_ticket_id_must_be_deterministic`
27. `test_rework_input_rejects_force_ready_override`
28. `test_rework_input_rejects_completion_snapshot_override`
29. `test_rework_generator_does_not_emit_event_records`

RED 预期：首次运行应因缺 `boardroom_os.checker.rework` 模块或缺 ReworkTicketGenerator（返工任务生成器）失败。

### 11.2 Happy path tests

`tests/evidence/test_rework_ticket_generation.py`：

1. `test_missing_test_evidence_generates_rework_ticket_and_original_rework_payloads`
2. `test_failed_evidence_generates_rework_ticket_with_failed_blocker_refs`
3. `test_checker_manual_blocker_inherits_original_acceptance_scope`
4. `test_rework_ticket_inherits_original_source_surfaces_and_evidence_obligations`
5. `test_rework_ticket_inherits_seat_demand`
6. `test_rework_ticket_allowed_read_refs_include_verdict_table_work_product_and_blockers`
7. `test_rework_overrides_can_narrow_allowed_write_set`
8. `test_rework_ticket_generation_is_deterministic`
9. `test_rework_generation_serializes_as_audit_friendly_json`
10. `test_rework_payloads_make_original_ticket_blocked_and_rework_ticket_ready_through_ticket_reducer`

### 11.3 Regression scope

实现完成后至少运行：

```bash
PYTHONPATH="src:." python -m pytest tests/evidence/test_rework_ticket_generation.py -q
PYTHONPATH="src:." python -m pytest tests/evidence/test_checker_verdict.py tests/evidence/test_rework_ticket_generation.py -q
PYTHONPATH="src:." python -m pytest tests/reducers/test_ticket_reducer_transitions.py tests/evidence/test_rework_ticket_generation.py -q
PYTHONPATH="src:." python -m pytest tests/contracts tests/reducers tests/execution tests/evidence tests/negative -q
```

## 12. 与现有模块的关系

1. 复用 `boardroom_os.checker.verdict.CheckerVerdict`（检查结论）、CheckerVerdictStatus（检查结论状态）、CheckerVerdictBlocker（检查结论阻断项）、CheckerBlockerRef（检查阻断引用）和 CheckerBlockerCode（检查阻断代码）。
2. 复用 `boardroom_os.graph.ticket.TicketNode`（任务节点）、TicketCreatedPayload（任务创建载荷）、TicketId（任务 ID）和 TicketStatus（任务状态）。
3. 复用 `boardroom_os.reducers.ticket_reducer.TicketCheckSnapshot`（任务检查快照）和 TicketRefPayload（任务引用载荷）。
4. 复用 `boardroom_os.events.types.EventType`（事件类型）中既有的 `TICKET_CREATED`、`TICKET_CHECKED`、`TICKET_REWORKED` 语义；不新增事件类型。
5. 不修改 `boardroom_os.reducers.ticket_reducer.TicketReducer`（任务状态归约器）；只用测试证明 payload（载荷）落成事件后可驱动原 ticket blocked（原任务阻塞）。
6. 不修改 `boardroom_os.checker.checker.CheckerService`（检查服务）；V2-050D 已经负责产出 CheckerVerdict（检查结论）。
7. 不修改 `boardroom_os.evidence.table.FinalEvidenceTable`（最终证据表）；V2-050E 通过 CheckerVerdict（检查结论）间接消费证据缺口。
8. 不修改 RuntimeExecutor（运行时执行器）、CommandRunner（命令运行器）或 ProviderExecutor（模型供应商执行器）。
9. 不修改 ExecutionPackageCompiler（执行包编译器）；rework ticket 进入 graph（任务图）后，后续编译流程应按普通 ready ticket（就绪任务）处理。

## 13. 验收映射

本 spec 对应 backlog 工作包：V2-050E。

覆盖 `backlog.md` 中 V2-050E 的验收口径：

- blocking gap（阻塞缺口）不生成 rework 必须失败。
- rework ticket（返工任务）缺 acceptance_refs（验收引用）必须失败。
- rework ticket 缺 evidence_obligations（证据义务）必须失败。
- missing test evidence（缺失测试证据）生成绑定原 ticket（原任务）的 rework ticket（返工任务）。
- 缺口在 checker/rework（检查 / 返工）阶段暴露，不留到 closeout（收尾）首次发现。

覆盖 `acceptance-criteria.md`：

- Phase 5 “Rework 闭环” checkbox（复选项）：由 V2-050E `tests/evidence/test_rework_ticket_generation.py` 证明。
- AC-V2-CHECKER-001（checker blocks evidence gaps，检查者阻断证据缺口）：V2-050D 已证明 checker 生成 blocker；V2-050E 进一步证明 blocker 会变成 graph（任务图）中的 rework ticket（返工任务）。
- AC-V2-GRAPH-002（reducer-protected transitions，受归约器保护的转换）：V2-050E 不直接改 graph，而是产出 reducer payload（归约器载荷），并通过 TicketReducer（任务状态归约器）证明原 ticket blocked（阻塞）。

完成 V2-050E implementation（实施）后应按 backlog 完成协议更新：

1. `doc/04-implementation/backlog.md`：V2-050E 状态改为 DONE，当前未完成工作包指向 V2-050F，Phase 5 进度改为 6/7，合计改为 34/53。
2. `doc/04-implementation/acceptance-criteria.md`：勾选 Phase 5 的 “Rework 闭环”；不要勾选 Completion gate（完成门禁）或 Phase 5 全部 DONE，除非 V2-050F 已完成。
3. `doc/05-project-log/2026-05.md`：追加 V2-050E 记录，包含关键产出文件、negative/happy tests 和验证命令。
4. `doc/04-implementation/INDEX.md`：本 spec 文档索引项应存在；若新增 implementation plan（实施计划）文档，再同步加入。
5. `doc/05-project-log/decisions.md`：若 implementation 阶段保持本 spec 边界，不需要新增 DEC；若决定引入新 EventType（事件类型）、rework edge（返工边）或改变 TicketReducer（任务状态归约器）语义，则新增 DEC。

## 14. 同行评审重点

请同行评审重点确认以下问题：

1. rework ticket（返工任务）不采用 `depends_on=(original_ticket_id,)`。现有 TicketGraph（任务图）依赖满足条件是 dependency ticket completed（依赖任务已完成）；原 ticket 在 rework path（返工路径）中会被置为 BLOCKED（阻塞），因此 depends_on 会造成死锁。Lineage（来源链）固定由 ReworkTicketPlan.original_ticket_ref（返工任务计划原任务引用）和 allowed_read_refs（允许读取引用）表达。
2. rework ticket（返工任务）的 evidence_obligations（证据义务）首版是否应全部继承原 ticket，还是必须按 acceptance_ref 精确收窄。当前 spec 推荐首版全部继承，避免丢失 obligation（义务）。
3. checker manual blocker（检查者手动阻断项）无 acceptance_ref 时，是否应继承原 ticket 全部 acceptance_refs。当前 spec 推荐继承全部，避免生成无验收范围的返工任务。
4. overrides.allowed_read_refs（允许读取引用覆盖项）只允许追加，不允许收窄；所有追加项与系统派生项都以字符串保存，系统派生项必须来自 `.value`。
5. V2-050E 是否应继续不生成 EventRecord（事件记录）。当前 spec 推荐只生成 typed payload（类型化载荷），避免提前承担 graph_version sequencing（图版本排序）。
6. deterministic rework_ticket_id（确定性返工任务 ID）是否采用可读拼接还是稳定 hash digest（哈希摘要）。当前 spec 允许 implementation 在保持确定性的前提下使用 digest。

## 15. 已收敛评审点

1. V2-050E 采用“新建返工单并阻塞原单”的语义。
2. V2-050E 不重新验证 evidence（证据），只消费 CheckerVerdict（检查结论）。
3. V2-050E 不直接 append EventLog（事件日志），只输出 typed payload（类型化载荷）。
4. V2-050E 不新增 EventType（事件类型），复用 `TICKET_CREATED`、`TICKET_CHECKED`、`TICKET_REWORKED`。
5. Rework ticket（返工任务）必须带 acceptance_refs、source_surface_refs、evidence_obligations 和 allowed_write_set。
6. 原 ticket（原任务）必须通过 TicketCheckSnapshot（任务检查快照）和 TicketRefPayload（任务引用载荷）进入既有 reducer rework path（归约器返工路径）。
7. Notes（备注）不能触发或清除 rework；只有 CheckerVerdictBlocker（检查结论阻断项）驱动返工。
8. CompletionGate（完成门禁）留给 V2-050F；V2-050E 不完成任何 ticket。
9. Rework ticket（返工任务）不依赖 original ticket（原任务），避免原任务 BLOCKED（阻塞）后造成 dependency deadlock（依赖死锁）；original_ticket_ref（原任务引用）只作为 lineage（来源链）写入 ReworkTicketPlan（返工任务计划）和 allowed_read_refs（允许读取引用）。
