# 推进策略

## 目标

当前 workflow progression 由 controller、runtime、ticket handlers、approval handlers、autopilot、projection 和 live harness 共同拼出。重构目标是把推进判断收成显式 policy：同一份 snapshot 输入，输出可审计的 action proposals。

核心函数：

```text
decide_next_actions(graph, assets, incidents, policy) -> ActionProposal[]
```

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

不得读取：

- freeform hard_constraints 文本进行 substring 判断；
- markdown 当前正文作为真实状态；
- provider raw transcript 作为推进依据；
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

- 每种 action 有独立单测。
- 相同 snapshot + policy 输出稳定 action proposals。
- 015 中出现的 stale gate、orphan pending、restore-needed missing ticket id、BR-100 loop 都能由 policy 测试覆盖。
- Scheduler 不再承担业务推进判断。
