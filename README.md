# Boardroom OS

> Event-sourced agent governance for autonomous software delivery.

中文首页。English overview: [doc/README.en.md](doc/README.en.md)

Boardroom OS 想做的不是“多 Agent 群聊外壳”，而是一个可审计、可治理、可审批的 Agent 交付控制面：

- 用户扮演董事会，只给目标、约束和验收标准
- CEO Agent 负责持续拆解、委派、推进，而不是频繁停下来等反馈
- Worker 通过结构化 ticket 无状态执行
- 关键节点通过 Board Gate 审批
- 全流程通过 event log 和 projection 保留可追溯性

## 当前状态

当前仓库已经不是纯设计稿，而是“设计文档 + 首个可运行后端切片”：

- 后端位于 `backend/`，技术栈是 FastAPI + Pydantic v2 + SQLite
- 已具备命令入口、投影视图和 SSE 事件流
- 已跑通 ticket 创建、lease、start、heartbeat、结构化结果提交、取消和人工恢复
- 已具备最小 incident / circuit-breaker / retry 治理链
- 已支持 review room、board approve/reject/modify constraints
- 已有独立 `scheduler_runner` 和可选的进程内 scheduler loop
- 已有最小 artifact store / artifact index，`JSON` / `TEXT` / `MARKDOWN` 与图片 / PDF / 其它中等体量二进制都可通过 `ticket-result-submit` 真实落盘
- 已有外部 worker handoff 面：worker 先用 per-worker bootstrap token 领取 assignment，拿到可刷新的 session 后，再通过 per-ticket 短时签名 URL 拉取 persisted execution package、读取 artifact、回写 start / heartbeat / result-submit；这些 URL 现在都落成可单独撤销的 delivery grant，并且 worker 侧已经补上可并存多组的 `tenant_id/workspace_id` 绑定

当前更像一个最小控制面原型，而不是完整产品。

## 已实现能力

- 命令面：`project-init`、ticket 生命周期命令、`ticket-result-submit`、`artifact-delete`、`artifact-cleanup`、board 审批命令、`incident-resolve`
- 投影面：`dashboard`、`inbox`、`incident detail`、`review room`、developer inspector companion、ticket artifacts
- artifact 读取面：按 `artifact_ref` 的 metadata / content / preview 接口，可供 review、incident 和外部调用复用
- worker handoff：`BOARDROOM_OS_RUNTIME_EXECUTION_MODE=EXTERNAL` 下由 scheduler 只负责 dispatch / lease；外部 worker 先用 `python -m app.worker_auth_cli` 签发的 bootstrap token 调 `GET /api/v1/worker-runtime/assignments`，拿到 `session_token` 后继续轮询 assignment，再沿 execution package 中的短时签名 URL 完成 artifact 读取和结构化回写；delivery URL 现在都有持久化 grant，可按单条 URL 撤销
- 运行时治理：重复失败升级、provider 级暂停恢复、协作式取消、`ticket-result-submit` 统一结果入口、artifact 物化 / 索引 / 生命周期治理
- 输出 schema：已真实注册并严格校验 `ui_milestone_review@1`、`consensus_document@1`
- 审计能力：事件流、SQLite WAL、最小 compile manifest / context bundle / compiled execution package 持久化
- 测试覆盖：API、reducer、scheduler runner、in-process scheduler

详细契约、状态机和设计边界已经迁移到 [doc/README.md](doc/README.md)。

## 快速开始

当前仓库里已验证的本地运行方式：

```bash
cd backend
source .venv/bin/activate
uvicorn app.main:app --reload
```

启用 FastAPI 进程内 scheduler：

```bash
cd backend
source .venv/bin/activate
BOARDROOM_OS_ENABLE_INPROCESS_SCHEDULER=true uvicorn app.main:app --reload
```

切到外部 worker handoff 模式：

```bash
cd backend
source .venv/bin/activate
BOARDROOM_OS_RUNTIME_EXECUTION_MODE=EXTERNAL \
BOARDROOM_OS_WORKER_BOOTSTRAP_SIGNING_SECRET=bootstrap-signing-secret \
BOARDROOM_OS_WORKER_DELIVERY_SIGNING_SECRET=delivery-signing-secret \
BOARDROOM_OS_PUBLIC_BASE_URL=http://127.0.0.1:8000 \
uvicorn app.main:app --reload
```

给某个 worker 签发 bootstrap token：

```bash
cd backend
source .venv/bin/activate
python -m app.worker_auth_cli issue-bootstrap --worker-id emp_frontend_2
python -m app.worker_auth_cli list-bindings --worker-id emp_frontend_2
python -m app.worker_auth_cli list-delivery-grants --worker-id emp_frontend_2
python -m app.worker_auth_cli list-sessions --worker-id emp_frontend_2
python -m app.worker_auth_cli list-auth-rejections --worker-id emp_frontend_2
python -m app.worker_auth_cli revoke-delivery-grant --grant-id <grant_id>
```

启动独立 runner：

```bash
cd backend
source .venv/bin/activate
python -m app.scheduler_runner
```

说明：

- `BOARDROOM_OS_RUNTIME_EXECUTION_MODE=INPROCESS` 是默认值，runner / in-process scheduler 会在 `LEASED` 后直接执行当前最小 runtime。
- `BOARDROOM_OS_RUNTIME_EXECUTION_MODE=EXTERNAL` 时，runner / in-process scheduler 只负责 dispatch / lease，不再自动 `start / execute / result-submit`。
- 推荐的外部 worker bootstrap 路径是：先用 `python -m app.worker_auth_cli issue-bootstrap --worker-id <employee_id>` 生成 bootstrap token，再携带 `X-Boardroom-Worker-Bootstrap` 调 `GET /api/v1/worker-runtime/assignments`；响应会返回 `session_id`、`session_token`、`session_expires_at` 和 assignment 列表。
- worker 的 bootstrap state 现在按 `worker_id + tenant_id + workspace_id` 形成可并存多组 binding；session 和 delivery grant 仍然各自只绑定到其中一组 scope。
- 当一个 worker 已经有多组 binding 时，`issue-bootstrap`、`rotate-bootstrap`、`revoke-bootstrap` 必须显式传 `--tenant-id` 和 `--workspace-id`；单 binding worker 仍可省略，沿用现有绑定。
- `GET /api/v1/worker-runtime/assignments` 现在也会返回 `tenant_id`、`workspace_id`，交付给 worker 的 execution package 响应也会带上同样的 scope 字段，便于远端排障和审计。
- worker 拿到 `session_token` 后，可以继续用 `X-Boardroom-Worker-Session` 轮询 `GET /api/v1/worker-runtime/assignments`；同一个 session 会刷新过期时间，并重新返回一批新的 per-ticket 短时签名 URL。
- assignment 现在会按当前 session 的 scope 只返回匹配的 ticket；如果发现当前 worker 名下存在一个没有对应 binding 的脏 scope ticket，仍会拒绝并写入审计日志，而不是静默吞掉。
- execution package URL、artifact URL 和 command URL 都继续使用 `access_token` 短时签名参数；这些 token 现在同时绑定到 token claim、持久化 grant、session/bootstrap state，以及 ticket/workflow 的 `tenant_id/workspace_id` 真值，所以既能在 session 级联失效，也能按单条 URL 单独撤销，并且跨租户或跨工作区会直接拒绝。
- `/api/v1/worker-runtime/tickets/*`、`/api/v1/worker-runtime/artifacts/*` 和 `/api/v1/worker-runtime/commands/*` 现在只接受 signed URL，不再接受旧的共享密钥请求 fallback。
- 本地运维可通过 `python -m app.worker_auth_cli list-delivery-grants` 查看 grant，通过 `python -m app.worker_auth_cli list-sessions` 查看活跃 session，通过 `python -m app.worker_auth_cli list-auth-rejections` 查看最近被拒的 worker 请求，再用 `python -m app.worker_auth_cli revoke-delivery-grant --grant-id <grant_id>` 撤销某一条具体 URL。
- `BOARDROOM_OS_WORKER_BOOTSTRAP_SIGNING_SECRET` 用来签发 bootstrap token；未设置时会回退到 `BOARDROOM_OS_WORKER_SHARED_SECRET`。
- `BOARDROOM_OS_WORKER_SESSION_TTL_SEC` 默认是 `86400` 秒，用来控制 `session_token` 的刷新窗口。
- `BOARDROOM_OS_PUBLIC_BASE_URL` 用来把这些 worker 交付 URL 改写成外部 worker 真正可达的公开基座；未设置时回退到请求里的 `base_url`。
- `BOARDROOM_OS_WORKER_DELIVERY_TOKEN_TTL_SEC` 默认是 `3600` 秒，`BOARDROOM_OS_WORKER_DELIVERY_SIGNING_SECRET` 未设置时会回退到 `BOARDROOM_OS_WORKER_SHARED_SECRET`。

运行测试：

```bash
cd backend
source .venv/bin/activate
python -m pytest tests -q
```

默认数据库路径：

- `backend/data/boardroom_os.db`
- `backend/data/artifacts/`（可用 `BOARDROOM_OS_ARTIFACT_STORE_ROOT` 覆盖）

当前仍有两个已知现实：

- 全新环境下 `pip install -e .[dev]` 可能因为 `backend/` 的平铺布局触发 `setuptools` 打包识别问题，本轮没有修改这一点。
- 当前二进制上传仍走 `ticket-result-submit` 内联 `base64`，没有 multipart / 分片 / 对象存储链路，适合中等体量文件，不适合超大文件。
- 当前外部 worker handoff 已经支持 per-worker bootstrap token、可刷新 session、bootstrap rotate/revoke、按 session 失效的 signed delivery、独立 delivery grant / 单 URL 撤销，以及 worker 侧多组 `tenant_id/workspace_id` binding 与四层校验。
- 仍未完成的是更完整的多租户管理面：虽然一个 worker 现在可以并存多组 binding，但公开互联网场景下更细粒度的安全边界、租户管理面和更强签发治理还要继续收紧。

## 文档入口

- [doc/README.md](doc/README.md)：文档总索引
- [doc/TODO.md](doc/TODO.md)：从 README、设计文档和最近历史记录归纳出的当前待办
- [doc/feature-spec.md](doc/feature-spec.md)：项目治理与产品规则总表
- [doc/design/message-bus-design.md](doc/design/message-bus-design.md)：事件总线、ticket、审批与治理主线
- [doc/design/context-compiler-design.md](doc/design/context-compiler-design.md)：Context Compiler 设计
- [doc/design/meeting-room-protocol.md](doc/design/meeting-room-protocol.md)：会议室协议
- [doc/design/boardroom-ui-design.md](doc/design/boardroom-ui-design.md)：Boardroom UI 产品设计
- [doc/design/boardroom-data-contracts.md](doc/design/boardroom-data-contracts.md)：UI 投影与命令契约
- [doc/history/memory-log.md](doc/history/memory-log.md)：精简后的长期记忆与近期记忆；详细逐轮记录见 `doc/history/archive/`

## 项目哲学

- 治理比热闹重要
- 审计比想象重要
- 幂等比炫技重要
- 结构化协作比自由群聊可靠
- 用户只在关键审查门介入，而不是替系统兜底日常执行

最终目标不是做一个“很会聊天的 Agent 项目”，而是做一个：

**可推进、可治理、可交付的 Agent Operating System。**
