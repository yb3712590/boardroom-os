# TODO

> 最后更新：2026-04-06
> 本文件仍是项目唯一的待办真相源，但正文只保留当前批次与条件批次。已完成能力改看 `todo/completed-capabilities.md`，远期储备改看 `todo/postponed.md` 与 `milestone-timeline.md`。

## 当前阶段目标

把项目继续收敛成一个本地单机可运行、可验证、可演示的 Agent Delivery OS MVP：

- 事件溯源状态总线是真相源
- Ticket 驱动无状态执行器推进工作
- Maker-Checker 和 Review 闭环真实可用
- React 只做最薄治理壳，不接管工作流真相

## 当前基线（2026-04-06）

- backend：`./backend/.venv/bin/pytest tests/ -q` -> `426 passed`
- frontend：`npm run build` -> passed，`npm run test:run` -> `64 passed`
- CEO 当前真实执行集：`CREATE_TICKET / RETRY_TICKET / HIRE_EMPLOYEE / REQUEST_MEETING`；`ESCALATE_TO_BOARD` 仍是 `DEFERRED_SHADOW_ONLY`

## 当前批次

### `P2-B`：代码瘦身与冻结能力隔离

状态：`阻塞已确认，等待前置条件改变`

- `P1-CLN-002`：主线 command 侧已解耦，但 runtime、`worker-admin / worker-runtime` contracts 和共享读面仍保留 `tenant_id/workspace_id` shape
- `P1-CLN-003`：`ticket-result-submit` 已与 upload session 解耦，但 upload 导入入口和 upload session 存储仍保留

详细任务与 blocker 统一看 [task-backlog/active.md](task-backlog/active.md)。

### `P2-C`：检索、Provider 路由与发布准备

状态：`未开始`

- 只有在证明当前主链不够用后，才打开 `P2-RET-*` 与 `P2-PRV-*`
- 发布准备仍是后续顺序的一部分，但当前不单独开活跃任务面

后续顺序统一看 [milestone-timeline.md](milestone-timeline.md)。

## `C1` 条件批次

只有在触发条件成立时，下面这些任务才进入真实执行：

| 任务 | 状态 | 触发条件 | 说明 |
|---|---|---|---|
| `P2-CEO-001` | 条件纳入 | 初始化输入反复低于最小可执行阈值 | 建立初始化需求澄清板审协议，不依赖 live `ESCALATE_TO_BOARD` |
| `P2-RET-006` | 条件纳入 | Worker 输出反复暴露缺少最小组织上下文，或执行包需要进一步收紧 | 只收口执行包最小组织上下文与 `L1` 纪律 |
| `P2-MTG-011` | 条件纳入 | 会议共识文档反复过长，默认消费面不清 | 把会议共识压成 ADR 化决策视图，不改当前 artifact 类型 |
| `P2-GOV-007` | 条件纳入 | closeout / review 反复出现“代码已改但证据或文档没同步” | 只加 soft review / checker rule，不加硬状态机门禁 |

## 当前入口

- 当前任务索引：[task-backlog.md](task-backlog.md)
- 当前活跃任务明细：[task-backlog/active.md](task-backlog/active.md)
- 已完成能力与收口批次：[todo/completed-capabilities.md](todo/completed-capabilities.md)
- 冻结范围与远期储备：[todo/postponed.md](todo/postponed.md)
- 后续顺序与条件批次：[milestone-timeline.md](milestone-timeline.md)
