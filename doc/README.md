# 文档索引

`doc/` 继续按“短入口 -> 详细页 -> 归档页”分层。默认先读短入口，不把大文件整篇塞进上下文。

当前文档组织采用“混合版分层”：

- `README / mainline-truth / roadmap-reset / TODO / task-backlog / history` 继续承担高频真相层
- `design/*` 继续承担详细设计与实现规格层
- 若后续新增 ADR / 决策记录，必须走独立目录并在索引里显式回链；不要把 ADR 混写进主线真相文件
- 文档之间的依赖关系必须通过索引或“相关文档”显式保留，不靠文件名猜关系

## 默认首读

1. [mainline-truth.md](mainline-truth.md)：当前代码真相表，先确认主链现实、runtime 支持矩阵和冻结边界
2. [roadmap-reset.md](roadmap-reset.md)：当前阶段边界和判断规则
3. [TODO.md](TODO.md)：当前批次与条件批次，不写远期愿景总表
4. [history/context-baseline.md](history/context-baseline.md)：稳定不常变的产品模型、治理规则、文档约束
5. [history/memory-log.md](history/memory-log.md)：最近几天仍影响判断的事实

## 任务与路线

- [task-backlog.md](task-backlog.md)：任务库入口，只放统计、状态索引和阅读说明
- [task-backlog/active.md](task-backlog/active.md)：当前未关闭任务与开启条件
- [task-backlog/done.md](task-backlog/done.md)：已完成任务卡片和详细补记
- [milestone-timeline.md](milestone-timeline.md)：后续顺序、条件批次和远期储备
- [todo/postponed.md](todo/postponed.md)：冻结范围与远期储备方向
- [新愿景文档更新与路线重整计划.md](新愿景文档更新与路线重整计划.md)：本轮一次性 handoff 计划，不是默认真相源

## 运行与接口

- [backend-runtime-guide.md](backend-runtime-guide.md)：当前后端运行、运维和排障指南
- [api-reference.md](api-reference.md)：当前全部 HTTP 接口参考，已标注主线 / 冻结边界

## 设计文档

默认只按需打开相关设计文档，且先读开头 `TL;DR`：

- `design/message-bus-design.md`
- `design/context-compiler-design.md`
- `design/meeting-room-protocol.md`
- `design/boardroom-data-contracts.md`
- `design/boardroom-ui-*.md`

## 历史与附录

- [todo/completed-capabilities.md](todo/completed-capabilities.md)：已完成主线能力和已收口批次
- [roadmap-reset/rationale.md](roadmap-reset/rationale.md)：路线纠偏的长版背景
- `history/archive/`：只有在需要精确历史原因、旧验证记录或兼容细节时才看

## 阅读规则

- 默认固定顺序：`README.md -> doc/README.md -> mainline-truth.md -> roadmap-reset.md -> TODO.md -> history/context-baseline.md -> history/memory-log.md`
- 需要任务细节时再进 `task-backlog/active.md` 或 `task-backlog/done.md`
- 需要排后续顺序时再进 `milestone-timeline.md`
- `TODO.md` 只保留当前批次与条件批次；远期储备统一看 `milestone-timeline.md` 与 `todo/postponed.md`
