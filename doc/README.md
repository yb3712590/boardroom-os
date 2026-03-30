# 文档索引

`doc/` 目录集中放置项目文档、设计规范、历史记录和当前待办。根目录只保留面向 GitHub 首页阅读的 `README.md`。

## 先看这些

- [TODO.md](TODO.md)：当前仍未完成的事项，已从 README、设计文档和最近历史记录里归纳去重
- [README.en.md](README.en.md)：英文版概览
- [feature-spec.md](feature-spec.md)：项目治理规则、组织规则和产品边界总表

## 设计文档

- [design/message-bus-design.md](design/message-bus-design.md)：事件溯源控制面、ticket 生命周期、审批门、恢复与熔断治理
- [design/context-compiler-design.md](design/context-compiler-design.md)：CompileRequest、预算策略、压缩矩阵和审计产物
- [design/meeting-room-protocol.md](design/meeting-room-protocol.md)：受控多角色协作协议
- [design/boardroom-ui-design.md](design/boardroom-ui-design.md)：Boardroom UI 的信息架构和产品边界
- [design/boardroom-data-contracts.md](design/boardroom-data-contracts.md)：Dashboard、Inbox、Review Room 和命令契约

## 历史记录

- [history/memory-log.md](history/memory-log.md)：精简后的长期记忆 + 近期记忆，适合作为会话入口
- `history/archive/`：按需查阅的详细历史归档，不应作为每次会话的默认入口

说明：
`memory-log.md` 和归档文件中保留了部分旧路径和旧文件名，用于忠实记录当时的工作上下文，不代表当前仓库布局。
