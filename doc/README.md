# 文档索引

`doc/` 现在按“当前真相 -> 工作参考 -> 历史归档”三层收口。默认只读当前真相层，不把旧计划、旧分析、已完成流水和长历史日志塞进上下文。

## 默认首读

1. [mainline-truth.md](mainline-truth.md)：当前代码真相、runtime 支持矩阵和冻结边界
2. [roadmap-reset.md](roadmap-reset.md)：当前阶段边界和开发判断规则
3. [TODO.md](TODO.md)：当前批次、条件批次和当前阶段目标

## 工作参考

- [milestone-timeline.md](milestone-timeline.md)：后续顺序、条件批次、远期储备，以及未来可支持的交付类型方向
- [task-backlog.md](task-backlog.md)：任务库入口，只放统计、状态索引和阅读说明
- [task-backlog/active.md](task-backlog/active.md)：当前未关闭任务
- [backend-runtime-guide.md](backend-runtime-guide.md)：当前后端运行、运维和排障指南
- [api-reference.md](api-reference.md)：当前 HTTP 接口参考
- [history/context-baseline.md](history/context-baseline.md)：稳定不常变的规则和架构基线，只在需要时打开
- [history/memory-log.md](history/memory-log.md)：最近仍影响实现判断的事实，只在需要近期原因时打开

## 设计文档

默认只按需打开相关设计文档，且先读开头 `TL;DR`：

- `design/message-bus-design.md`
- `design/context-compiler-design.md`
- `design/meeting-room-protocol.md`
- `design/boardroom-data-contracts.md`
- `design/boardroom-ui-*.md`

## 历史归档

- [archive/README.md](archive/README.md)：旧 spec、旧计划、旧分析和历史评估的入口
- [task-backlog/done.md](task-backlog/done.md)：已完成任务卡片和完成补记
- [todo/completed-capabilities.md](todo/completed-capabilities.md)：已落地主线能力清单
- [history/archive/](history/archive/)：详细 memory log 和旧验证流水
- [roadmap-reset/rationale.md](roadmap-reset/rationale.md)：路线纠偏长版背景，按需看

## 阅读规则

- 默认固定顺序：`README.md -> doc/README.md -> mainline-truth.md -> roadmap-reset.md -> TODO.md`
- 需要当前任务时再进 `task-backlog/active.md`
- 需要排后续顺序时再进 `milestone-timeline.md`
- 需要稳定规则时再进 `history/context-baseline.md`
- 需要最近几天的具体变化原因时再进 `history/memory-log.md`
- 需要旧计划、旧评估或旧 spec 时，统一从 `archive/README.md` 进入
