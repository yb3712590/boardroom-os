# Boardroom OS 任务库入口

> 最后更新：2026-04-06
> 目的：保留 `doc/task-backlog.md` 这个高频入口，但把默认阅读层压缩到索引级别。

## 怎么读

1. 先看本页，确认当前任务总量、活跃区域和应该打开哪一层
2. 只需要当前未完成任务时，打开 [task-backlog/active.md](task-backlog/active.md)
3. 需要追溯已完成任务卡片、工时、依赖、验收标准、完成补记时，打开 [task-backlog/done.md](task-backlog/done.md)

## 总览

| 指标 | 数值 | 说明 |
|------|------|------|
| 总任务数 | 121 | 原始编号与任务名称保持不变 |
| 已完成 / 已收口 | 99 | 详细卡片与完成补记保存在 `task-backlog/done.md` |
| 当前仍未关闭 | 22 | 当前工作集保存在 `task-backlog/active.md` |
| 总预估工时 | 464h | 来自拆分前任务库原表 |

## 当前活跃区域

| 区域 | 任务范围 | 当前状态 | 默认看哪里 |
|------|----------|----------|------------|
| 代码清理 | `P1-CLN-001` 到 `P1-CLN-006` | 进行中 | [task-backlog/active.md](task-backlog/active.md) |
| 检索层 | `P2-RET-001` 到 `P2-RET-005` | 未开始 | [task-backlog/active.md](task-backlog/active.md) |
| Provider 增强 | `P2-PRV-001` 到 `P2-PRV-008` | 未开始 | [task-backlog/active.md](task-backlog/active.md) |
| 治理模板 | `P2-GOV-001` 到 `P2-GOV-006` | 未开始 | [task-backlog/active.md](task-backlog/active.md) |

当前补记：代码清理区仍维持“其余切片保守收口、只在条件满足时再评估无壳迁移”的状态；这轮已把 `P1-CLN-001` 真正推进到 shim 物理迁移完成，`worker-admin` 的真实实现现在位于 `backend/app/_frozen/worker_admin/`，旧 API / auth / projection / core / CLI 入口只保留兼容壳。`P1-CLN-002` 继续停在主线 command 侧已解耦、共享 contracts shape 未拆；`P1-CLN-003` 继续停在 upload 导入入口和 session 存储仍保留；`P1-CLN-004` 继续停在 handoff schema 仍成组保留。未关闭任务总数更新为 `22`，新增关闭任务为 `P1-CLN-001`。

## 读写约定

- 新任务如果进入当前主线，先更新 [TODO.md](TODO.md)，再把任务 ID 和状态同步到 [task-backlog/active.md](task-backlog/active.md)
- 任务关闭后，把详细补记放进 [task-backlog/done.md](task-backlog/done.md)，本页只更新状态统计和区域索引
- 需要按 ID 回查时，优先在 `task-backlog/active.md` 或 `task-backlog/done.md` 里搜索，不再默认整篇读取原始大文件
