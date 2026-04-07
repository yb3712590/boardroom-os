# Boardroom OS 任务库入口

> 最后更新：2026-04-07
> 目的：保留 `doc/task-backlog.md` 这个高频入口，但把默认阅读层压缩到索引级别。

## 怎么读

1. 先看本页，确认当前任务总量、活跃区域和应该打开哪一层
2. 只需要当前未关闭任务时，打开 [task-backlog/active.md](task-backlog/active.md)
3. 需要追溯已完成任务卡片、依赖、验收标准和详细补记时，打开 [task-backlog/done.md](task-backlog/done.md)

## 总览

| 指标 | 数值 | 说明 |
|------|------|------|
| 总任务数 | 143 | 原始编号保留，新增编号继续用于路线重排、M7 首批、条件批次、角色纳入链和本轮前置解耦批次 |
| 已完成 / 已收口 | 130 | 详细卡片与完成补记保存在 `task-backlog/done.md` |
| 当前仍未关闭 | 13 | 当前工作集保存在 `task-backlog/active.md` |
| 总预估工时 | 531h | 在原表基础上补入本轮新增前置解耦任务 |

## 当前活跃区域

| 区域 | 任务范围 | 当前状态 | 默认看哪里 |
|------|----------|----------|------------|
| 当前主线 | `P2-DEC-003` 到 `P2-DEC-004` | 当前主线；`P2-DEC-001 / P2-DEC-002` 已完成，下一步继续收正过程资产闭环与 CEO 防停滞边界 | [task-backlog/active.md](task-backlog/active.md) |
| 冻结后置 | `P1-CLN-002` 到 `P1-CLN-003` | 冻结后置 | [task-backlog/active.md](task-backlog/active.md) |
| Provider 增强 | `P2-PRV-007` 到 `P2-PRV-008` | 后置增强 | [task-backlog/active.md](task-backlog/active.md) |
| 治理模板与文档链 | `P2-GOV-003` 到 `P2-GOV-006` | 后置增强 / 条件纳入；顺序排在 `P2-DEC-*` 之后 | [task-backlog/active.md](task-backlog/active.md) |
| 角色纳入链 | `P2-RLS-001` 到 `P2-RLS-003` | 后续工作链纳入；等待 `P2-DEC-*` 与 `P2-GOV-003/004` | [task-backlog/active.md](task-backlog/active.md) |

## 读写约定

- 新任务如果进入当前主线，先更新 [TODO.md](TODO.md)，再把任务 ID 和状态同步到 [task-backlog/active.md](task-backlog/active.md)
- 任务关闭后，把详细补记放进 [task-backlog/done.md](task-backlog/done.md)，本页只更新统计和区域索引
- `TODO.md` 只保留当前批次与条件批次；远期储备统一写到 `milestone-timeline.md` 与 `todo/postponed.md`
