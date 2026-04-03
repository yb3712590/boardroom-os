# 文档索引

`doc/` 目录集中放项目文档、设计规范、路线决议和历史记录。

## 优先阅读

1. [mainline-truth.md](mainline-truth.md)：当前代码真相表，先看主链现实、runtime 支持矩阵和冻结边界
2. [roadmap-reset.md](roadmap-reset.md)：当前阶段的路线纠偏决议与范围边界
3. [TODO.md](TODO.md)：当前主线待办（唯一待办真相源）
4. [backend-runtime-guide.md](backend-runtime-guide.md)：后端运行方式与现有 runtime / worker 面
5. [feature-spec.md](feature-spec.md)：产品边界、治理规则与长期设计原则

## 评审与规划

- [cto-assessment-report.md](cto-assessment-report.md)：CTO 技术评审报告（诊断、差距分析、优先级建议）
- [milestone-timeline.md](milestone-timeline.md)：13 周 9 里程碑时间线
- [task-backlog.md](task-backlog.md)：112 项任务清单（含工时估算、依赖图、验收标准）

## 设计文档

- [design/message-bus-design.md](design/message-bus-design.md)：事件溯源控制面、Ticket 生命周期、审批门、恢复与熔断治理
- [design/context-compiler-design.md](design/context-compiler-design.md)：CompileRequest、预算策略、压缩与审计产物
- [design/meeting-room-protocol.md](design/meeting-room-protocol.md)：受控多角色协作协议
- [design/boardroom-data-contracts.md](design/boardroom-data-contracts.md)：Dashboard、Inbox、Review Room 和命令契约
- [design/boardroom-ui-design.md](design/boardroom-ui-design.md)：Boardroom UI 的信息架构与产品边界
- [design/boardroom-ui-visual-concept.md](design/boardroom-ui-visual-concept.md)：当前确认的首页视觉方向与设计稿
- [design/boardroom-ui-visual-spec.md](design/boardroom-ui-visual-spec.md)：前端实现时应参照的详细视觉规范
- [design/frontend-architecture-guide.md](design/frontend-architecture-guide.md)：前端架构蓝图（目录结构、类型系统、状态管理、迁移计划）
- [design/frontend-component-spec.md](design/frontend-component-spec.md)：前端组件规格（Props、HTML 结构、视觉规则、行数目标）

## 历史记录

- [history/memory-log.md](history/memory-log.md)：精简后的长期记忆与近期进展
- `history/archive/`：按需查阅的详细历史归档

说明：
`memory-log.md` 和归档文件保留了最近几轮基础设施推进的真实记录；当前主线请以 `roadmap-reset.md` 和 `TODO.md` 为准。
