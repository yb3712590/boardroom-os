# 文档索引

`doc/` 目录集中放项目文档、设计规范、路线决议和历史记录。

## 优先阅读

- [roadmap-reset.md](roadmap-reset.md)：当前阶段的路线纠偏决议与范围边界
- [TODO.md](TODO.md)：当前主线待办
- [backend-runtime-guide.md](backend-runtime-guide.md)：后端运行方式与现有 runtime / worker 面
- [feature-spec.md](feature-spec.md)：产品边界、治理规则与长期设计原则

## 设计文档

- [design/message-bus-design.md](design/message-bus-design.md)：事件溯源控制面、Ticket 生命周期、审批门、恢复与熔断治理
- [design/context-compiler-design.md](design/context-compiler-design.md)：CompileRequest、预算策略、压缩与审计产物
- [design/meeting-room-protocol.md](design/meeting-room-protocol.md)：受控多角色协作协议
- [design/boardroom-ui-design.md](design/boardroom-ui-design.md)：Boardroom UI 的信息架构与产品边界
- [design/boardroom-data-contracts.md](design/boardroom-data-contracts.md)：Dashboard、Inbox、Review Room 和命令契约

## 历史记录

- [history/memory-log.md](history/memory-log.md)：精简后的长期记忆与近期进展
- `history/archive/`：按需查阅的详细历史归档

说明：
`memory-log.md` 和归档文件保留了最近几轮基础设施推进的真实记录；当前主线请以 `roadmap-reset.md` 和 `TODO.md` 为准。
