# Boardroom OS 任务库入口

> 最后更新：2026-04-06
> 目的：保留 `doc/task-backlog.md` 这个高频入口，但把默认阅读层压缩到索引级别。

## 怎么读

1. 先看本页，确认当前任务总量、活跃区域和应该打开哪一层
2. 只需要当前未关闭任务时，打开 [task-backlog/active.md](task-backlog/active.md)
3. 需要追溯已完成任务卡片、依赖、验收标准和详细补记时，打开 [task-backlog/done.md](task-backlog/done.md)

## 总览

| 指标 | 数值 | 说明 |
|------|------|------|
| 总任务数 | 131 | 原始编号保留，新增编号只用于本轮文档重整与后续条件批次 |
| 已完成 / 已收口 | 105 | 详细卡片与完成补记保存在 `task-backlog/done.md` |
| 当前仍未关闭 | 26 | 当前工作集保存在 `task-backlog/active.md` |
| 总预估工时 | 490h | 在原表基础上补入本轮新增任务 |

## 当前活跃区域

| 区域 | 任务范围 | 当前状态 | 默认看哪里 |
|------|----------|----------|------------|
| 代码清理 | `P1-CLN-002` 到 `P1-CLN-003` | 进行中 | [task-backlog/active.md](task-backlog/active.md) |
| 检索层 | `P2-RET-001` 到 `P2-RET-006` | 后置增强 / 条件纳入 | [task-backlog/active.md](task-backlog/active.md) |
| Provider 增强 | `P2-PRV-001` 到 `P2-PRV-008` | 后置增强 | [task-backlog/active.md](task-backlog/active.md) |
| 治理模板与交付口径 | `P2-GOV-001` 到 `P2-GOV-007` | 后置增强 / 条件纳入 | [task-backlog/active.md](task-backlog/active.md) |
| CEO 策略增强 | `P2-CEO-001` 到 `P2-CEO-002` | 条件纳入 / 后置增强 | [task-backlog/active.md](task-backlog/active.md) |
| 会议增强 | `P2-MTG-011` | 条件纳入 | [task-backlog/active.md](task-backlog/active.md) |

## 读写约定

- 新任务如果进入当前主线，先更新 [TODO.md](TODO.md)，再把任务 ID 和状态同步到 [task-backlog/active.md](task-backlog/active.md)
- 任务关闭后，把详细补记放进 [task-backlog/done.md](task-backlog/done.md)，本页只更新统计和区域索引
- `TODO.md` 只保留当前批次与条件批次；远期储备统一写到 `milestone-timeline.md` 与 `todo/postponed.md`
