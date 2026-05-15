# Process Audit 与 Replay

## 文档职责

本文件定义 V2 的人类可读流程审计资料和 replay/resume 机制。

## Process Audit 是产品能力

Process audit 不是 raw event dump。它是最终交付的一部分，用来让人类理解并审计：

- 需求如何被解释；
- CEO 如何组织团队；
- architect 如何形成合同；
- ticket graph 如何演进；
- worker 接收了什么上下文；
- provider 和工具实际执行了什么；
- checker 如何验证；
- evidence 如何满足 acceptance；
- closeout 为什么可以通过。

## 必需输出

```text
30-audit/process-audit.md
30-audit/timeline.json
30-audit/decision-log.md
30-audit/agent-context-index.json
30-audit/ticket-graph.md
30-audit/artifact-lineage.json
30-audit/evidence-map.json
30-audit/git-version-audit.md
30-audit/closeout-summary.md
30-audit/replay-bundle-report.json
```

## Timeline

Timeline 记录关键事件，不应包含所有低价值 runtime 噪音。

关键事件包括：

- directive received；
- charter created；
- acceptance contract created；
- package contract created；
- seat assigned；
- ticket created / leased / blocked / reworked / completed；
- provider attempt；
- command run；
- evidence verified；
- checker verdict；
- closeout prepared / committed；
- replay materialized。

## Decision Log

CEO 和 human board 的关键决策必须记录：

```yaml
decision_id:
actor:
graph_version:
input_state_refs:
decision:
rationale:
created_events:
```

## Agent Context Index

每次 agent attempt 都应可追踪：

- execution package ref；
- context refs；
- constraints；
- allowed write set；
- required outputs；
- model execution profile；
- provider attempt ref。

## Artifact Lineage

Artifact lineage 必须表达：

```text
producer attempt -> artifact -> consumer ticket -> evidence claim -> verifier -> closeout
```

## Git Version Audit

每个 source ticket 必须记录：

- branch / worktree；
- base commit；
- changed files；
- commit hash；
- dirty status；
- diff summary；
- associated evidence。

Closeout 必须记录：

- final package commit；
- optional tag；
- git clean proof；
- source inventory hash；
- run/test evidence at final commit。

## Replay

Replay 分为两层：

1. **Audit replay（审计重放）**：从有序 `EventLog`（事件日志）和必要 payload/artifact manifest（载荷/产物清单）重建 typed summaries（类型化摘要），证明 runtime（运行时）内存状态不是事实源。
2. **Branchable governance replay（可分叉治理重放）**：从历史图上的某个 graph version（图版本）或 event cursor（事件游标）重新 materialize（物化）状态，由 CEO（首席治理者）记录 replay decision（重放决策），再对 graph（图）或 work packages（工作包）施加新影响，形成新的后继历史。

V2-020F 只实现 audit replay（审计重放）：它必须证明 projection summary（投影摘要）可由从 graph version（图版本）1 开始的事件历史确定性重建，并在事件缺失、乱序、中段 replay 缺 snapshot/base projection contract（快照/基准投影合同）或 projection version（投影版本）不匹配时 fail closed（失败关闭）。

V2-070 应从 audit replay（审计重放）继续扩展，逐步走向 branchable governance replay（可分叉治理重放）能力；当 closeout（收尾）产出不合格时，尤其应支持从选定历史点开展大规模返工，而不是把不合格 closeout 当作 terminal success（终态成功）。

本文件只声明 replay（重放）的边界和演进方向，不在当前阶段锁定最终 materialization flow（物化流程）、rework strategy（返工策略）或 replay bundle contract（重放包合同）。

如果未来引入 replay bundle（重放包），可参考的非绑定示例字段包括：

```yaml
replay_bundle_id:
event_range:
projection_versions:
payload_manifest_ref:
artifact_manifest_ref:
hash_manifest_ref:
expected_summary_refs:
replay_report_ref:
```

## Resume

Resume 必须从明确 boundary 恢复：

- graph version；
- event cursor；
- workspace commit；
- artifact manifest；
- active contract refs。

禁止从不完整 raw runtime state 猜恢复点。

