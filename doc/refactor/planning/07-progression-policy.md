# 推进策略

## 目标

当前 workflow progression 由 controller、runtime、ticket handlers、approval handlers、autopilot、projection 和 live harness 共同拼出。重构目标是把推进判断收成显式 policy：同一份 snapshot 输入，输出可审计的 action proposals。

核心函数：

```text
decide_next_actions(snapshot, policy) -> ActionProposal[]
```

## Round 8A 实现状态

8A 已在 `backend/app/core/workflow_progression.py` 落地最小 policy contract：

- `ProgressionSnapshot` 是结构化只读输入，覆盖 workflow、graph version、node/ticket refs、ready/blocked/in-flight indexes、incidents、approvals、actor availability 和 provider availability。
- `ProgressionPolicy` 是显式策略输入，覆盖 governance、fanout、closeout、recovery policy input，并允许外层传入结构化 `create_ticket_candidates`、wait reason 和 no-action reason。
- `ActionProposal` 是 policy 输出，当前承载 `CREATE_TICKET`、`WAIT`、`REWORK`、`CLOSEOUT`、`INCIDENT`、`NO_ACTION` 六类 action contract。
- `build_action_metadata()` 为六类 action 生成统一 metadata：reason code、idempotency key、source graph version、affected node refs、expected state transition、policy ref。
- `decide_next_actions(snapshot, policy)` 目前只覆盖最小骨架：open approvals/incidents/in-flight 输出 `WAIT`，结构化 create-ticket candidate 输出 `CREATE_TICKET`，无合法动作输出 `NO_ACTION`。

8A 没有迁移 controller、scheduler、CEO proposer、backlog fanout、meeting/architect gate、closeout、rework 或 restore 主路径。后续批次必须继承 8A 的 contract，不得重新定义不兼容的 snapshot/policy/action proposal 语义。

## Round 8B 实现状态

8B 已把 effective graph pointer 与 ready/blocked/in-flight/complete 索引收进 progression policy：

- `ProgressionSnapshot` 增加结构化 graph nodes、graph edges、runtime nodes、ticket lineage、replacement/supersession/cancellation、graph reduction issue、blocked reason、completed index 和 stale/orphan pending refs。
- `evaluate_progression_graph(snapshot)` 是纯函数，只消费 snapshot，不读取 repository、provider raw transcript、artifact 正文或外部文件。
- `REPLACES` 指向的新 ticket/node 是 current；`SUPERSEDED` / `CANCELLED` 仍保留 lineage 可见性，但不进入 effective readiness、effective edges 或 complete。
- orphan pending / stale snapshot node 作为 diagnostic 处理，不阻断 effective graph complete。
- `decide_next_actions()` 为 open approval、open incident、in-flight runtime、graph reduction issue、stale/orphan pending、blocked node 无恢复动作、graph complete 输出稳定 `WAIT` / `INCIDENT` / `NO_ACTION` reason code。
- `ticket_graph.py` 仍是 DB snapshot facade，但 index summary 通过 policy evaluation 回填；controller 只保留 8E 前的兼容壳，fanout、meeting/architect、closeout/rework/restore 主判断尚未迁移。

## Round 8C 实现状态

8C 已把 governance chain、architect gate、meeting gate 和 backlog fanout 的推进输入迁到结构化 policy：

- `ProgressionPolicy.governance` 现在消费 `chain_order`、`completed_outputs`、`chain_ticket_plans`、`required_gates`、`meeting_requirements` 和 `approved_meeting_evidence`。
- `ProgressionPolicy.fanout` 现在消费 `backlog_implementation_handoff`、`fanout_graph_patch_plan` 和 `existing_ticket_ids_by_node_ref`。
- `decide_next_actions(snapshot, policy)` 会为治理链下一文档、结构化 architect governance gate、结构化 meeting requirement、backlog handoff fanout 和 graph patch fanout 输出 `CREATE_TICKET` / `WAIT` / `NO_ACTION` proposal。
- 8C 新增稳定 reason code：`progression.governance.followup_required`、`progression.governance.architect_gate_required`、`progression.wait.meeting_requirement`、`progression.fanout.backlog_handoff_ticket`、`progression.fanout.graph_patch_ticket`。
- `CREATE_TICKET` proposal metadata 保留 8A contract：reason code、idempotency key、source graph version、affected node refs、expected state transition 和 policy ref；fanout payload 额外携带 source graph version、source ticket 和具体 plan。
- `workflow_controller.py` 只读取 DB/artifact 来编译 structured policy input，不把 backlog recommendation artifact 正文交给 `decide_next_actions()`。`hard_constraints` 只保留为 snapshot/display 字段，不再驱动 `requires_architect`、`requires_meeting` 或 fanout。
- controller 可透传 workflow/directive 中已编译的 `progression_policy_input.governance` / `progression_policy_input.fanout.fanout_graph_patch_plan`；8C 不从 graph patch placeholder node 或 freeform 文本硬造 create-ticket payload。
- CEO proposer 优先消费 `progression_policy_proposals` 中的 `CREATE_TICKET` payload；validator 接受与 policy proposal 匹配的 create-ticket action，并在 accepted details 中保留 policy metadata。

8C 未迁移 closeout、retry/restore、BR-100 loop 或 incident followup 主判断；失败票 recovery meeting 也仍保留 8D 前兼容路径。controller 中 graph wait/ready/blocked、closeout gate 和 recovery orchestration 仍是 8E 前兼容壳。

## Round 8D 实现状态

8D 已把 closeout、rework、retry/restore、incident followup 和 BR-100 loop 的推进裁决迁入结构化 policy：

- `ProgressionPolicy.closeout.readiness` 现在消费 `effective_graph_complete`、`open_blocking_incident_refs`、`open_approval_refs`、`delivery_checker_gate_issue`、`existing_closeout_ticket_id`、`closeout_parent_ticket_id`、`final_evidence_legality_summary` 和可执行 `ticket_payload`。
- `CLOSEOUT` proposal 只在 effective graph complete、无 blocker、无 duplicate closeout、存在 parent ticket、final evidence 合法且存在 closeout ticket payload 时输出；duplicate closeout 输出 `NO_ACTION`，reason code 为 `progression.closeout.duplicate_existing_closeout`。
- `ProgressionPolicy.recovery.actions` 现在消费 failed/timed-out terminal state、retry budget/count、failure kind、recommended followup action、failure lineage、completed-ticket reuse gate、superseded/invalidated lineage 和 restore-needed action。
- `ProgressionPolicy.recovery.loop_signals` 现在消费 maker-checker/rework loop threshold；BR-100 在本批用结构化 `loop_ref=BR-100` + threshold input 覆盖，完整 015 replay 仍归 Phase 7。
- Policy 为 checker blocking finding、deliverable/evidence gap、retryable failed/timed-out terminal target 和 completed-ticket reuse lineage blocker 输出 `REWORK`；为 retry budget exhausted、restore-needed missing ticket id、unrecoverable failure kind 和 loop threshold reached 输出 `INCIDENT`。
- `REWORK`、`CLOSEOUT`、`INCIDENT` proposal 都有稳定 reason code、idempotency key、source graph version、affected node refs 和 expected state transition 单测。
- `workflow_controller.py` 不再调用 `resolve_workflow_closeout_completion()` 做 closeout 推进裁决；它只读取 DB/artifact index 编译 closeout/recovery policy input，final evidence 只传 legality summary，不把 artifact 正文交给 policy。
- Closeout graph complete 来自 `evaluate_progression_graph(progression_snapshot).graph_complete`，不得用 stale snapshot nodes 覆盖 effective graph pointer。
- CEO proposer / validator 已接受 `CLOSEOUT` policy proposal，并把其中 `ticket_payload` 当 create-ticket execution shell；旧 `_build_autopilot_closeout_batch()` 只保留为 Round 8E 兼容壳。
- `workflow_auto_advance.py` 和 incident detail projection 的 recommended followup action 改为复用 `recommended_incident_followup_action_from_policy_input()`；需要 DB 查询的 source-ticket/provider context 只作为结构化 input compiler。

8D 仍未完成 Round 8E 的 scheduler/controller/proposer 总收口：旧 closeout fallback、backlog followup retry execution shell、projection display 分支和 runtime incident execution 分支仍需在 8E 统一 grep、删减或标注为纯 input compiler / execution shell。

## 输入

Policy engine 输入必须是结构化对象：

- graph version；
- current nodes and edges；
- current ready/blocked/completed indexes；
- ticket terminal states；
- process asset index；
- artifact index；
- incident records；
- actor registry；
- provider health；
- governance profile；
- deliverable contract status。

Policy 纯函数不得读取：

- freeform hard_constraints 文本进行 substring 判断；
- markdown 当前正文作为真实状态；
- provider raw transcript 作为推进依据；
- DB、artifact 文件正文或外部文件正文；
- stale snapshot 中的 orphan pending 作为 active truth。

## 输出 Action

允许输出：

| Action | 含义 |
|---|---|
| `CREATE_TICKET` | 创建新执行票 |
| `PATCH_GRAPH` | 修改 graph version |
| `RETRY_TICKET` | 在原输入上重试 |
| `RECOMPILE_CONTEXT` | 重编译执行包 |
| `REASSIGN_EXECUTOR` | 更换执行者 |
| `FREEZE_SUBGRAPH` | 冻结受影响子图 |
| `RESUME_SUBGRAPH` | 解冻子图 |
| `CREATE_INCIDENT` | 打开 incident |
| `REQUEST_HUMAN_DECISION` | 请求人类裁量 |
| `CREATE_CLOSEOUT` | 生成 closeout 票 |
| `NO_ACTION` | 无合法动作，必须给 reason |
| `WAIT` | 等待 provider/worker/approval，必须给 wake condition |

每个 action 必须带：

- source graph version；
- idempotency key；
- reason code；
- affected node refs；
- expected state transition；
- policy ref。

## Graph latest ticket 规则

一个 graph node 的 current ticket 由 graph edge 和 version 决定，不由 ticket 表中最新 updated_at 决定。

规则：

- `REPLACES` 指向的新 ticket 是 current。
- `SUPERSEDED` ticket 不参与 readiness。
- `CANCELLED` ticket 不参与 effective edges。
- `FAILED` / `TIMED_OUT` ticket 只有被 recovery action 引用时参与恢复。
- orphan pending 不能阻断 graph complete。
- late completed/output 的 old provider attempt 只保留 lineage，不参与 current ticket、graph pointer、artifact/evidence 推进。

8B 实现边界：

- `updated_at` 只能作为历史/展示字段；没有 runtime current pointer 或 `REPLACES` lineage 时，policy/facade 记录 `graph.current_pointer.missing_explicit`，不再用最新更新时间猜 current。
- `REPLACES` edge 可在 graph facade 中作为 lineage edge 展示，但不进入 policy effective edges。
- 015 stale gate 的完整 replay 仍归 Phase 7；8B 覆盖结构化等价 stale/orphan snapshot 场景。

## Ready 判断

节点 ready 必须满足：

1. all dependency edges satisfied；
2. required process assets present；
3. required evidence present；
4. actor capability available or create-actor action planned；
5. no blocking incident on node/subgraph；
6. write-surface policy satisfiable；
7. provider health acceptable for selected purpose。

## Rework 判断

Rework 必须由结构化 finding 驱动：

- failed schema；
- write-set violation；
- evidence gap；
- deliverable contract gap；
- checker blocking finding；
- provider terminal failure requiring recompile/reassign；
- repeated review loop threshold。

Rework target 必须指向能修复问题的 upstream node，而不是默认把 failed check report 再送回 checker。

## Closeout 判断

`CREATE_CLOSEOUT` 必须满足：

- runtime graph effective nodes 全部 completed；
- no open blocking incident；
- no deliverable contract blocker；
- no unresolved evidence gap；
- no placeholder source/evidence in final evidence set；
- final artifact refs 全部来自合法 delivery evidence；
- approved failed report 必须有明确 convergence policy 支撑。

## Incident 判断

以下情况必须 incident 化：

- no eligible actor；
- repeated provider failure beyond retry budget；
- repeated maker-checker loop；
- graph patch rejected；
- write-set violation；
- placeholder delivery attempt；
- replay/resume inconsistency；
- projection/hash mismatch；
- scheduler cannot make progress beyond stall threshold。

## 禁止事项

1. 禁止用字符串 hint 判断会议/架构门。
2. 禁止 runtime 内硬编码 backlog milestone fanout。
3. 禁止 adapter 两个分支都返回同一个固定 chain。
4. 禁止 closeout fallback 读 stale snapshot nodes 而忽略 runtime graph pointer。
5. 禁止 maker-checker `APPROVED_WITH_NOTES` 自动覆盖 failed delivery report。
6. 禁止 provider failure 直接触发重复 create 同 node。

## 验收标准

- Round 8A：六类 action metadata helper 有独立单测，覆盖 reason code、idempotency key、source graph version、affected node refs、expected state transition 和 policy ref。
- Round 8A：相同 snapshot + policy 输出稳定 action proposals。
- Round 8B：policy 单测覆盖 `REPLACES` current pointer、`CANCELLED` / `SUPERSEDED` effective edge 排除、orphan pending 不阻断 graph complete，以及 approval/incident/in-flight/blocked/graph reduction/stale-orphan reason code。
- Round 8B：ticket graph facade 测试覆盖 runtime pointer 优先于 newer stale `updated_at`，以及缺 explicit pointer 时产生 graph reduction issue。
- Round 8C：policy 单测覆盖无结构化 requirement 时 legacy hint text 不触发 architect/meeting gate，结构化 architect gate 产生稳定 `CREATE_TICKET` metadata，meeting requirement 缺 evidence 时 `WAIT`，backlog handoff / graph patch 产生 fanout ticket，只有 completed `milestone_plan` 时不 fanout。
- 015 中出现的 stale gate、orphan pending、restore-needed missing ticket id、BR-100 loop 都能由 policy 测试覆盖。
- Scheduler 不再承担业务推进判断。

8D 验收补充：

- closeout readiness 的 policy 单测覆盖 `CLOSEOUT` stable metadata、duplicate closeout `NO_ACTION`、open incident/approval/gate issue/illegal evidence blocker。
- recovery policy 单测覆盖 checker blocking finding `REWORK`、retry budget exhausted `INCIDENT`、restore-needed missing ticket id `INCIDENT`、completed-ticket reuse gate `NO_ACTION`、superseded/invalidated lineage `REWORK`、retryable terminal target `REWORK` 和 unrecoverable failure kind `INCIDENT`。
- BR-100 loop 本批覆盖结构化 loop threshold 等价输入；没有 replay DB 时，完整 015/BR-100 replay 仍归 Phase 7。

## 后续批次依赖

- Round 8B：已把 effective graph pointer、ready/blocked/complete 判断迁入 policy。
- Round 8C：已把 governance gate、architect/meeting gate 和 backlog fanout 迁入结构化 policy input / graph patch，并删除 substring hint / hardcoded milestone fanout 作为推进依据。
- Round 8D：已把 closeout、rework、retry/restore、BR-100 loop 和 incident follow-up 推进判断迁入 policy；旧入口只作为 input compiler、execution shell 或 8E 兼容壳。
- Round 8E：收口 controller/runtime/scheduler/proposer 旧业务判断和兼容展示壳，并补齐 Phase 4 全部验收证据。
