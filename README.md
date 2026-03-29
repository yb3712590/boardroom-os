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
- `GET /api/v1/projections/incidents/{incident_id}` 最小 incident 详情投影
- `GET /api/v1/projections/review-room/{review_pack_id}` 真实投影（针对已持久化审批包）
- `GET /api/v1/projections/review-room/{review_pack_id}/developer-inspector` 可读取已持久化的 developer inspector JSON 产物
- `GET /api/v1/events/stream?after={cursor}` SSE 增量事件流
- `CommandAckEnvelope` 首轮真实契约
- `events` / `workflow_projection` / `ticket_projection` / `node_projection` / `approval_projection` / `employee_projection` / `incident_projection` 最小 schema
- `compiled_context_bundle` / `compile_manifest` 最小持久化审计表
- `POST /api/v1/commands/ticket-create` 真实落地 ticket 创建，并显式携带 lease 超时、重复超时升级阈值与轻量退让策略
- `POST /api/v1/commands/ticket-lease` 真实落地 ticket lease 获取与续租
- `POST /api/v1/commands/ticket-start` 把最新 ticket / node 推进到执行态
- `POST /api/v1/commands/ticket-heartbeat` 为 `EXECUTING` ticket 提供显式活跃心跳，不再复用 lease 续命语义
- `POST /api/v1/commands/ticket-fail` 真实落地主动失败上报与最小 retry create
- `POST /api/v1/commands/ticket-complete` 用结构化 ticket 结果触发上游审批生产
- `ticket-complete -> review_request` 现在只负责声明 `developer_inspector_refs`；review-room 下的 inspector 文件来自该 ticket 已持久化的真实最小 compile 产物，若真实产物尚未存在则 companion projection 会诚实返回 `partial`
- 最小持久化 worker roster / executor pool
- `POST /api/v1/commands/scheduler-tick` 真实落地显式 scheduler tick，默认从持久化 roster 读取 workers，用于总执行超时、heartbeat 超时、timeout retry 轻量退让、重复超时 incident / circuit-breaker 升级与 expired lease dispatch
- dashboard / inbox 的 incident 与 circuit-breaker 计数已接入真实投影，不再写死为 0
- repeated runtime timeout 现在会在同一 node 的重试链路上打开最小 incident 与 circuit-breaker，并阻断该 node 的后续自动 dispatch
- `POST /api/v1/commands/incident-resolve` 已打通最小人工恢复链：一次性关闭 circuit breaker 并关闭 incident；关闭后同 node 的新 ticket 可再次进入调度，但不会自动补发 retry
- dashboard `workforce_summary` 已接入最小真实投影
- 独立 scheduler runner：`python -m app.scheduler_runner`
- runner 已打通最小自动执行链：`TICKET_LEASED` 会在独立 runner 中继续推进到 `TICKET_STARTED`，并先经过最小 `CompileRequest -> CompiledContextBundle / CompileManifest -> CompiledExecutionPackage` 编译与持久化边界，再进入 `TICKET_COMPLETED` 或 `TICKET_FAILED`
- FastAPI 进程现在也可按环境变量显式开启进程内后台 scheduler loop；默认关闭，不改变现有启动语义；开启后会复用同一条最小调度与运行时链路
- 最小 `CompiledContextBundle` / `CompileManifest` 已落地持久化与审计，可按 ticket 回看；当前 provenance 仍是 reference-only，不包含 artifact 正文 hydration
- `POST /api/v1/commands/board-approve`
- `POST /api/v1/commands/board-reject`
- `POST /api/v1/commands/modify-constraints`
- API、ticket 生命周期、审批链与 reducer 最小测试

## 本轮未实现

以下能力仍未落地，当前仍是 stub 或未开始：

- 完整 compiled execution package 交付 / 外部 worker runtime 实际交付（当前仅落地进程内最小编译边界）
- employee hire / replace / freeze 生命周期
- 超出当前最小闭环的 cancel / richer retry policy / incident 自动恢复与自动关闭状态
- 外部 AI 提供方配额不足 / 服务波动后的暂停恢复治理
- Maker-Checker Review Loop
- Review Room 仍只支持已持久化审批包，不含更完整的证据拼装
- 非 reference-only 的完整 Context Compiler 编译、artifact hydration、缓存复用与更丰富 provenance
- artifact store / artifact index 与严格结果校验器
- FTS / 向量检索
- React Boardroom UI

## 已落地后端契约

首轮对外路由和契约名已经锁定，不再用临时命名替代：

- `POST /api/v1/commands/project-init`
- `GET /api/v1/projections/dashboard`
- `GET /api/v1/projections/inbox`
- `GET /api/v1/projections/incidents/{incident_id}`
- `GET /api/v1/projections/review-room/{review_pack_id}`
- `GET /api/v1/projections/review-room/{review_pack_id}/developer-inspector`
- `GET /api/v1/events/stream?after={cursor}`
- `POST /api/v1/commands/ticket-create`
- `POST /api/v1/commands/ticket-lease`
- `POST /api/v1/commands/ticket-start`
- `POST /api/v1/commands/ticket-heartbeat`
- `POST /api/v1/commands/ticket-fail`
- `POST /api/v1/commands/ticket-complete`
- `POST /api/v1/commands/scheduler-tick`
- `POST /api/v1/commands/incident-resolve`
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

如需启用 FastAPI 进程内后台调度，可显式打开：

```bash
cd backend
BOARDROOM_OS_ENABLE_INPROCESS_SCHEDULER=true uvicorn app.main:app --reload
```

独立 runner 仍保留，适合与 API 进程分离部署：

```bash
cd backend
python -m app.scheduler_runner
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
- `BOARDROOM_OS_BUSY_TIMEOUT_MS`
- `BOARDROOM_OS_RECENT_EVENT_LIMIT`
- `BOARDROOM_OS_ENABLE_INPROCESS_SCHEDULER`
- `BOARDROOM_OS_SCHEDULER_POLL_INTERVAL_SEC`
- `BOARDROOM_OS_SCHEDULER_MAX_DISPATCHES`
- `BOARDROOM_OS_DEVELOPER_INSPECTOR_ROOT`

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
- ticket 的 cancel / richer retry / incident 恢复状态机
- 扩展当前 reference-only Context Compiler 到带 artifact hydration、检索与缓存复用的完整编译链
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
