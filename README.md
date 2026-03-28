# Boardroom OS

> Event-sourced Agent Governance.

中文版首页说明。English version: [README.en.md](README.en.md)

Boardroom OS 是一个基于事件溯源的 Agent 治理框架。

它不是聊天机器人外壳，不是“AI 办公室动画”产品，也不是把一堆 Agent 扔进群聊后听天由命的自动化脚本。它的目标是把 Agent 开发流程做成一个可审计、可治理、可审批、可持续推进的控制面系统：

- 用户扮演董事会
- CEO Agent 负责调度与推进
- Worker 以工单方式无状态执行
- Checker 负责内部审查
- 关键里程碑通过 Board Gate 审批
- 全流程通过事件日志和状态投影保留可追溯性

## 当前代码状态

当前仓库已经从“纯设计文档仓库”进入 **设计文档 + 后端首个可运行切片** 阶段。

已落地代码位于 [backend/](backend/)，当前实现范围：

- FastAPI 后端入口
- SQLite 控制面数据库与 `WAL`
- `SYSTEM_INITIALIZED` 首次初始化幂等规则
- `POST /api/v1/commands/project-init`
- `GET /api/v1/projections/dashboard`
- `GET /api/v1/projections/inbox`
- `GET /api/v1/projections/review-room/{review_pack_id}` 真实投影（针对已持久化审批包）
- `GET /api/v1/events/stream?after={cursor}` SSE 增量事件流
- `CommandAckEnvelope` 首轮真实契约
- `events` / `workflow_projection` / `ticket_projection` / `node_projection` / `approval_projection` 最小 schema
- `POST /api/v1/commands/ticket-create` 真实落地 ticket 创建
- `POST /api/v1/commands/ticket-lease` 真实落地 ticket lease 获取与续租
- `POST /api/v1/commands/ticket-start` 把最新 ticket / node 推进到执行态
- `POST /api/v1/commands/ticket-complete` 用结构化 ticket 结果触发上游审批生产
- `POST /api/v1/commands/board-approve`
- `POST /api/v1/commands/board-reject`
- `POST /api/v1/commands/modify-constraints`
- API、ticket 生命周期、审批链与 reducer 最小测试

## 本轮未实现

以下能力仍未落地，当前仍是 stub 或未开始：

- CEO Tick Scheduler
- Scheduler 驱动的 lease 回收 / Ticket Pool 派发
- Worker 派发 / compiled execution package 实际交付
- 超出 `CREATED -> LEASED -> STARTED -> COMPLETED` 的 timeout / retry / failure 状态
- Maker-Checker Review Loop
- Review Room 仍只支持已持久化审批包，不含更完整的证据拼装
- Context Compiler 实际编译
- FTS / 向量检索
- React Boardroom UI

## 已落地后端契约

首轮对外路由和契约名已经锁定，不再用临时命名替代：

- `POST /api/v1/commands/project-init`
- `GET /api/v1/projections/dashboard`
- `GET /api/v1/projections/inbox`
- `GET /api/v1/projections/review-room/{review_pack_id}`
- `GET /api/v1/events/stream?after={cursor}`
- `POST /api/v1/commands/ticket-create`
- `POST /api/v1/commands/ticket-lease`
- `POST /api/v1/commands/ticket-start`
- `POST /api/v1/commands/ticket-complete`
- `POST /api/v1/commands/board-approve`
- `POST /api/v1/commands/board-reject`
- `POST /api/v1/commands/modify-constraints`

首轮命令回执已真实返回：

- `command_id`
- `idempotency_key`
- `status`
- `received_at`
- `reason`
- `causation_hint`

## 运行方式

在本地安装 Python 3.12 后：

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -e .[dev]
uvicorn app.main:app --reload
```

测试命令：

```bash
cd backend
python -m pytest
```

默认数据库路径：

- `backend/data/boardroom_os.db`

也可以通过环境变量覆盖：

- `BOARDROOM_OS_DB_PATH`

## 文档导航

- [feature.txt](feature.txt)
  - 全局 feature 规则与设计约束总表
- [message-bus-design.md](message-bus-design.md)
  - 事件总线、Ticket、Projection、Board Gate 的总体机制
- [context-compiler-design.md](context-compiler-design.md)
  - Context Compiler、CompileRequest、CompiledContextBundle、压缩策略
- [meeting-room-protocol.md](meeting-room-protocol.md)
  - 受控会议室协作协议
- [boardroom-ui-design.md](boardroom-ui-design.md)
  - Boardroom 控制面的产品与交互边界
- [boardroom-data-contracts.md](boardroom-data-contracts.md)
  - Dashboard / Inbox / Review Room 等 UI 数据契约
- [memory.txt](memory.txt)
  - 会话连续性记录，非正式规范源

## 计划技术栈

- 后端：Python 3.12 + FastAPI + Pydantic v2
- 数据层：SQLite + WAL + 手写 SQL / 拼装 SQL
- 前端：React + Vite + TypeScript + TailwindCSS
- 同步：REST + SSE
- 存储：控制面元数据进 SQLite，产物与预览走文件系统引用

## MVP 仍然方向

当前后端切片只打通最小控制面闭环。后续仍按既定顺序推进：

- 投影 reducer 继续扩展
- ticket 的 timeout / retry / failure 状态机
- Context Compiler 骨架接入
- Worker / Checker 执行链
- Board Review Pack 与审批命令
- 最小 Boardroom UI

## 项目哲学

Boardroom OS 默认相信：

- 治理比热闹重要
- 审计比想象重要
- 幂等比炫技重要
- 结构化协作比自由群聊可靠
- 用户应只在关键节点介入，而不是为系统兜底日常执行

最终目标不是做一个“会聊天的 Agent 项目”，而是做一个：

**可推进、可治理、可交付的 Agent Operating System。**


