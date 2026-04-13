# Boardroom OS 任务库入口

> 最后更新：2026-04-13
> 目的：保留 `doc/task-backlog.md` 这个高频入口，但把默认阅读层压缩到索引级别。

## 怎么读

1. 先看本页，确认当前任务总量、活跃区域和应该打开哪一层
2. 只需要当前未关闭任务时，打开 [task-backlog/active.md](task-backlog/active.md)
3. 需要追溯已完成任务卡片、依赖、验收标准和详细补记时，打开 [task-backlog/done.md](task-backlog/done.md)

## 总览

| 指标 | 数值 | 说明 |
|------|------|------|
| 总任务数 | 153 | 原始编号保留，新增编号继续用于路线重排、角色纳入、provider 收口，以及 2026-04-10 新增的 `P0-COR` 主线纠偏批次 |
| 已完成 / 已收口 | 145 | 详细卡片与完成补记保存在 `task-backlog/done.md` |
| 当前仍未关闭 | 8 | 当前工作集保存在 `task-backlog/active.md` |

## 当前活跃区域

| 区域 | 任务范围 | 当前状态 | 默认看哪里 |
|------|----------|----------|------------|
| 当前主线 | `P0-COR-001` 到 `P0-COR-006` | 进行中：本轮已按审计总计划连续落两批，先把真实交付门禁收紧，再把场景摘要、巡检报告、治理 `.audit.md` 和 ticket 执行卡片收成固定审计入口 | [task-backlog/active.md](task-backlog/active.md) |
| 冻结后置 | `P1-CLN-002` 到 `P1-CLN-003` | 冻结后置 | [task-backlog/active.md](task-backlog/active.md) |
| 条件批次 | `C1` | 当前无新增开启项；只在触发条件成立时回到主线 | [TODO.md](TODO.md) |
| 已完成历史 | `P2-*`、旧 `M7` 相关批次 | 已收口 | [task-backlog/done.md](task-backlog/done.md) |

## 读写约定

- 新任务如果进入当前主线，先更新 [TODO.md](TODO.md)，再把任务 ID 和状态同步到 [task-backlog/active.md](task-backlog/active.md)
- 任务关闭后，把详细补记放进 [task-backlog/done.md](task-backlog/done.md)，本页只更新统计和区域索引
- `TODO.md` 只保留当前批次与条件批次；远期储备统一写到 `milestone-timeline.md` 与 `todo/postponed.md`
