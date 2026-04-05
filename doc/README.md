# 文档索引

`doc/` 现在按“入口摘要 -> 详细页 / 归档页”分层。默认先读短入口，不再把大文件整篇塞进上下文。

## 默认首读

1. [mainline-truth.md](mainline-truth.md)：当前代码真相表，先确认主链现实、runtime 支持矩阵和冻结边界
2. [roadmap-reset.md](roadmap-reset.md)：当前阶段规则清单；长版背景看 `roadmap-reset/`
3. [TODO.md](TODO.md)：唯一待办真相源，只保留当前要推进的批次
4. [history/context-baseline.md](history/context-baseline.md)：稳定不常变的产品模型、治理规则、架构基线
5. [history/memory-log.md](history/memory-log.md)：最近几天的关键进展和当前工作集

## 任务与规划

- [task-backlog.md](task-backlog.md)：任务库入口，只放统计、状态索引和阅读说明
- [task-backlog/active.md](task-backlog/active.md)：仍未关闭、仍可能被反复读取的任务明细
- [task-backlog/done.md](task-backlog/done.md)：拆分前的完整任务库快照，保留已完成任务卡片、工时、依赖、验收标准和完成补记
- [milestone-timeline.md](milestone-timeline.md)：中长期里程碑时间线；当前真相仍以 `TODO.md` 为准
- [cto-assessment-report.md](cto-assessment-report.md)：CTO 技术评审报告（诊断、差距分析、优先级建议）

## 设计文档

- [design/message-bus-design.md](design/message-bus-design.md)：事件溯源控制面、Ticket 生命周期、审批门、恢复与熔断治理
- [design/context-compiler-design.md](design/context-compiler-design.md)：CompileRequest、预算策略、压缩与审计产物
- [design/meeting-room-protocol.md](design/meeting-room-protocol.md)：受控多角色协作协议
- [design/boardroom-data-contracts.md](design/boardroom-data-contracts.md)：Dashboard、Inbox、Review Room 和命令契约
- [design/boardroom-ui-design.md](design/boardroom-ui-design.md)：Boardroom UI 的信息架构与产品边界
- [design/boardroom-ui-visual-concept.md](design/boardroom-ui-visual-concept.md)：首页视觉方向与设计稿
- [design/boardroom-ui-visual-spec.md](design/boardroom-ui-visual-spec.md)：详细视觉规范
- [design/frontend-architecture-guide.md](design/frontend-architecture-guide.md)：前端架构蓝图（目录结构、类型系统、状态管理、迁移计划）
- [design/frontend-component-spec.md](design/frontend-component-spec.md)：前端组件规格（Props、HTML 结构、视觉规则、行数目标）

这些设计文档现在都先给 `TL;DR`。默认先读开头摘要，需要改对应模块时再往下翻全文。

## 历史与附录

- [todo/completed-capabilities.md](todo/completed-capabilities.md)：已完成主线能力和已收口批次
- [todo/postponed.md](todo/postponed.md)：冻结能力、明确后置方向和不主动扩张的范围
- [roadmap-reset/rationale.md](roadmap-reset/rationale.md)：路线纠偏的长版背景和推导
- [roadmap-reset/agent-reset-prompt.md](roadmap-reset/agent-reset-prompt.md)：给开发代理整段复制的长提示词
- `history/archive/`：按需查阅的详细历史归档

## 阅读规则

- 默认先读短入口：`mainline-truth.md`、`roadmap-reset.md`、`TODO.md`、`history/context-baseline.md`、`history/memory-log.md`
- 只有在需要任务工时、依赖、验收细节时，再进 `task-backlog/active.md` 或 `task-backlog/done.md`
- 只有在要做多周规划、发布日期排程或远期能力排序时，再读 `milestone-timeline.md`
- `TODO.md` 只记录当前主线待办；远期框架能力和公司治理能力，统一看 `feature-spec.md`、`milestone-timeline.md`、`task-backlog/active.md`
