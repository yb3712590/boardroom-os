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

Replay 的目标是证明 typed summaries 可由 event log + artifact manifest 重建。

Replay bundle 至少包含：

```yaml
replay_bundle_id:
event_range:
projection_versions:
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

