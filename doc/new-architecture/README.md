# 新架构规格索引

这套文稿只回答一个问题：**如果要把 Boardroom OS 重构成健壮、无状态、幂等、可恢复的自治状态机，它下一代应该长成什么样。**

这里不是当前代码真相层。当前真相还是看：

- [../mainline-truth.md](../mainline-truth.md)
- [../roadmap-reset.md](../roadmap-reset.md)
- [../TODO.md](../TODO.md)

这套新文稿的作用是定目标架构，后面拆重构任务、画迁移边界、审查实现偏差，都以这里为准。

## 阅读顺序

1. [00-autonomous-machine-overview.md](00-autonomous-machine-overview.md)
2. [01-document-constitution.md](01-document-constitution.md)
3. [11-governance-profile-and-audit-modes.md](11-governance-profile-and-audit-modes.md)
4. [02-ticket-graph-engine.md](02-ticket-graph-engine.md)
5. [03-worker-context-and-execution-package.md](03-worker-context-and-execution-package.md)
6. [04-ceo-memory-model.md](04-ceo-memory-model.md)
7. [05-incident-idempotency-and-recovery.md](05-incident-idempotency-and-recovery.md)
8. [06-role-hook-system.md](06-role-hook-system.md)
9. [07-skill-runtime.md](07-skill-runtime.md)
10. [08-board-advisor-and-replanning.md](08-board-advisor-and-replanning.md)
11. [09-process-assets-and-project-map.md](09-process-assets-and-project-map.md)
12. [10-migration-map.md](10-migration-map.md)
13. [12-architecture-audit-report.md](12-architecture-audit-report.md)
14. [13-cross-cutting-concerns.md](13-cross-cutting-concerns.md)
15. [14-graph-health-monitor.md](14-graph-health-monitor.md)

如果你只想先抓主线，读 `00 -> 01 -> 11 -> 02 -> 03 -> 05 -> 10` 就够了。
如果你想看审计结论和重构建议，读 `12 -> 13 -> 14`。

## 这套文稿固定保留的判断

- 文档不是真相存储。文档是 `event + graph + process asset` 的物化视图。
- 任务真相不是树，是 `versioned DAG`。
- CEO 不保存长对话记忆，只读受控快照和资产切片。
- Worker 无状态，但不是无约束。每次都拿 `CompiledExecutionPackage`。
- 技能不是人格的一部分。技能是按场景取出的武器。
- 错误必须升级成 `IncidentRecord`，恢复靠 `RecoveryAction` 和幂等重放。
- Hook 跟 `role + lifecycle event + deliverable kind` 绑定，不跟 runtime 阶段绑定。
- Board 不只是审批点，也是随时可唤醒的重规划顾问环。
- `小白 / 专家` 和 `审计强度` 不是 UI 开关，是 workflow 级治理协议。
- `audit_mode` 只能控制留痕物化强度，不能关闭系统真相底座。

## 统一术语总表

| 术语 | 含义 | 谁消费 |
|---|---|---|
| `EventRecord` | 只追加的事件包络。记录真实发生过的动作。 | Reducer、Projection、审计 |
| `ProjectionSnapshot` | 面向某个角色的当前状态切片。 | CEO、Board、Scheduler |
| `TicketNode` | 图里的原子任务节点。 | CEO、Scheduler、Compiler |
| `TicketEdge` | 节点之间的关系边。 | Graph Engine |
| `CompiledExecutionPackage` | 发给 Worker 的封闭执行包。 | Worker、Checker |
| `ProcessAsset` | 可追溯、可复用、可编译的过程资产。 | Compiler、CEO、Hook |
| `ProjectMap` | 项目边界、责任、热点、冲突区的结构化地图。 | CEO、Compiler、Checker |
| `IncidentRecord` | 显式故障记录。 | CEO、Board、Recovery Engine |
| `RecoveryAction` | 受控恢复动作。 | Reducer、Scheduler、CEO |
| `RoleHook` | 和角色绑定的标准化后置动作。 | Hook Runner |
| `SkillBinding` | 当前票解析出来的技能装配结果。 | Compiler、Worker |
| `BoardAdvisorySession` | 董事会顾问会话。用于约束变更和图重排。 | CEO、Board |

| `GraphHealthReport` | 图健康检查报告。瓶颈、深度、扇出、孤立、震荡的检测结果。 | CEO、Scheduler |

## 和现有文档栈的关系

- [../mainline-truth.md](../mainline-truth.md) 讲的是“当前代码已经是什么”。
- [../roadmap-reset.md](../roadmap-reset.md) 讲的是“当前阶段先做什么，不做什么”。
- `doc/design/*` 讲的是“当前主线某个子系统的设计细节”。
- `doc/new-architech/*` 讲的是“自治状态机的目标架构和迁移落点”。

说白了，旧文档偏现状，新文档偏目标。两边都保留，但职责不同。

## 固定示例 workflow

全套文稿统一用 `library_management_autopilot` 当示例。

原因只有两个：

- 仓库里已经有真实审计材料和失败轨迹。
- 它正好暴露了“治理文档很多、票很多、流程在跑、但没有真正收口成可验收交付”这个核心问题。

示例里固定采用这条主链：

`project-init -> governance -> backlog fanout -> build -> check -> board review -> closeout`

示例里常见节点名统一写成：

- `node_architecture_brief`
- `node_technology_decision`
- `node_milestone_plan`
- `node_detailed_design`
- `node_backlog_recommendation`
- `node_backend_catalog_build`
- `node_frontend_library_build`
- `node_delivery_check`
- `node_board_review`
- `node_closeout`

## 文稿约束

- 每份规格都固定有：`TL;DR`、`设计目标`、`非目标`、`核心 Contract`、`状态机 / 流程`、`失败与恢复`、`统一示例`、`和现有主线的关系`。
- 每份规格都必须能独立读懂，不靠读者自己翻旧文档补上下文。
- 每份规格都不能留 `TODO / TBD / 后续再定`。
- 图一律用 Mermaid。
- 这套文稿不顺手重写现有设计稿，也不把自己伪装成当前代码现实。

## 你该怎么用这套文稿

- 要判断一个实现是不是跑偏：先看 `00` 和 `10`。
- 要拆后续重构任务：先看 `02`、`05`、`06`、`10`。
- 要查某个角色该看什么上下文：看 `03` 和 `04`。
- 要查文档、证据、项目地图为什么总在漂：看 `01` 和 `09`。

这套文稿的目标很单纯：把“文档地狱式 agent 系统”重新立法成“能自我恢复的交付机器”。
