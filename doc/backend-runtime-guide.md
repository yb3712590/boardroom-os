# Backend 运行与 Worker 运维

这份文档承接根目录 `README.md` 里不适合放在首页的运行细节，主要面向当前在仓库里继续开发或排查 Runtime / Backend 的人。

## 当前可运行切片

当前后端位于 `backend/`，技术栈是 FastAPI + Pydantic v2 + SQLite。

已经真实落地的能力包括：

- 命令入口、投影视图和 SSE 事件流
- ticket 创建、lease、start、heartbeat、结构化结果提交、取消和人工恢复
- 最小 incident / circuit-breaker / retry 治理链
- review room 与 board approve / reject / modify constraints
- artifact store / artifact index / ticket artifacts projection
- 外部 worker handoff：bootstrap token、refreshable session、signed delivery grants、artifact 访问、worker 命令 URL
- 多租户 worker 运维面：binding 生命周期、`worker-runtime` 投影读面、bootstrap issue 签发记录，以及可直接撤 session / delivery grant 的 `worker-admin` HTTP 管理面

## 本地运行

启动后端：

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

启动独立 runner：

```bash
cd backend
source .venv/bin/activate
python -m app.scheduler_runner
```

## 运行模式

- `BOARDROOM_OS_RUNTIME_EXECUTION_MODE=INPROCESS` 是默认值，runner / in-process scheduler 会在 `LEASED` 后直接执行当前最小 runtime
- `BOARDROOM_OS_RUNTIME_EXECUTION_MODE=EXTERNAL` 时，runner / in-process scheduler 只负责 dispatch / lease，不再自动 `start / execute / result-submit`

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

## Worker bootstrap 与运维命令

给某个 worker 签发 bootstrap token：

```bash
cd backend
source .venv/bin/activate
python -m app.worker_auth_cli issue-bootstrap --worker-id emp_frontend_2
```

显式创建某个 scope binding：

```bash
cd backend
source .venv/bin/activate
python -m app.worker_auth_cli create-binding \
  --worker-id emp_frontend_2 \
  --tenant-id tenant_blue \
  --workspace-id ws_design
```

常用本地运维命令：

```bash
cd backend
source .venv/bin/activate
python -m app.worker_auth_cli list-bindings --worker-id emp_frontend_2
python -m app.worker_auth_cli cleanup-bindings --worker-id emp_frontend_2 --dry-run
python -m app.worker_auth_cli list-delivery-grants --worker-id emp_frontend_2
python -m app.worker_auth_cli list-sessions --worker-id emp_frontend_2
python -m app.worker_auth_cli list-auth-rejections --worker-id emp_frontend_2
python -m app.worker_auth_cli revoke-session --session-id <session_id> --revoked-by ops@example.com
python -m app.worker_auth_cli revoke-delivery-grant --grant-id <grant_id>
```

说明：

- `list-bindings` 会返回每个 binding 的活跃 session / grant / ticket 数、最近一次 bootstrap 签发时间 / 来源，以及是否可清理
- `cleanup-bindings` 只会清掉没有活跃 session、没有活跃 grant、没有活跃 ticket，且已 revoke 或从未签发过 bootstrap 的 binding
- 当一个 worker 已经有多组 binding 时，`issue-bootstrap`、`rotate-bootstrap`、`revoke-bootstrap` 必须显式传 `--tenant-id` 和 `--workspace-id`
- `revoke-session` 现在支持传 `--session-id`，或者传 `--worker-id` 并同时显式带 `--tenant-id` / `--workspace-id`
- `revoke-session` 和 `revoke-delivery-grant` 都会回显 `revoked_via`、`revoked_by`、`revoke_reason`，并把这些字段写进持久化读面

## Worker admin HTTP 管理面

现在也可以直接走后端控制面，而不是只能回本地 CLI：

```bash
curl 'http://127.0.0.1:8000/api/v1/worker-admin/bindings?worker_id=emp_frontend_2'

curl 'http://127.0.0.1:8000/api/v1/worker-admin/bootstrap-issues?worker_id=emp_frontend_2&active_only=true'

curl -X POST 'http://127.0.0.1:8000/api/v1/worker-admin/create-binding' \
  -H 'Content-Type: application/json' \
  -d '{"worker_id":"emp_frontend_2","tenant_id":"tenant_blue","workspace_id":"ws_design"}'

curl -X POST 'http://127.0.0.1:8000/api/v1/worker-admin/issue-bootstrap' \
  -H 'Content-Type: application/json' \
  -d '{"worker_id":"emp_frontend_2","tenant_id":"tenant_blue","workspace_id":"ws_design","ttl_sec":120,"issued_by":"ops@example.com","reason":"tenant admin bootstrap"}'

curl -X POST 'http://127.0.0.1:8000/api/v1/worker-admin/revoke-session' \
  -H 'Content-Type: application/json' \
  -d '{"session_id":"wsess_123","revoked_by":"ops@example.com","reason":"tenant incident session revoke"}'

curl -X POST 'http://127.0.0.1:8000/api/v1/worker-admin/revoke-delivery-grant' \
  -H 'Content-Type: application/json' \
  -d '{"grant_id":"wgrant_123","revoked_by":"ops@example.com","reason":"single URL revoke"}'
```

当前已实现的管理接口：

- `GET /api/v1/worker-admin/bindings`
- `GET /api/v1/worker-admin/bootstrap-issues`
- `POST /api/v1/worker-admin/create-binding`
- `POST /api/v1/worker-admin/issue-bootstrap`
- `POST /api/v1/worker-admin/revoke-bootstrap`
- `POST /api/v1/worker-admin/revoke-session`
- `POST /api/v1/worker-admin/revoke-delivery-grant`
- `POST /api/v1/worker-admin/cleanup-bindings`

说明：

- 这批接口复用和 CLI 完全同一套 scope 校验、TTL 上限、tenant allowlist 和 cleanup 规则
- `tenant_id` 和 `workspace_id` 必须成对出现；多 binding worker 在 `issue-bootstrap` / `revoke-bootstrap` 上也仍然要显式带 scope
- `revoke-session` 必须二选一：要么按 `session_id` 撤一条会话，要么按 `worker_id + tenant_id + workspace_id` 撤一个明确 scope 下的会话
- `revoke-delivery-grant` 只按 `grant_id` 撤一条具体 delivery grant，不会把同 session 的兄弟 URL 一起撤掉
- `revoke-session` 会同步回显并落盘级联撤掉的 delivery grant 数，以及 `revoked_via` / `revoked_by` / `revoke_reason`
- 这是一层“受信控制面”入口，不代表项目已经补齐公网身份层或租户自助权限模型

## Worker handoff 现状

- 推荐路径是：先用 `issue-bootstrap` 生成 bootstrap token，再携带 `X-Boardroom-Worker-Bootstrap` 调 `GET /api/v1/worker-runtime/assignments`
- assignments 响应会返回 `tenant_id`、`workspace_id`、`session_id`、`session_token`、`session_expires_at` 和 assignment 列表
- worker 拿到 `session_token` 后，可以继续用 `X-Boardroom-Worker-Session` 轮询 `GET /api/v1/worker-runtime/assignments`
- execution package URL、artifact URL 和 command URL 都使用短时 `access_token`
- `/api/v1/worker-runtime/tickets/*`、`/api/v1/worker-runtime/artifacts/*` 和 `/api/v1/worker-runtime/commands/*` 只接受 signed URL，不再接受旧的共享密钥请求 fallback
- 现在也可以用 `GET /api/v1/projections/worker-runtime` 按同一组 filter 一次看到 binding、session、delivery grant 和最近拒绝日志，再用 `worker-admin` HTTP 或本地 CLI 做最小 scope 级处理
- `worker-runtime` 投影里的 session / delivery grant 现在会回显 `revoked_via`、`revoked_by`、`revoke_reason`，方便值守同学直接确认是谁、从哪、因为什么做了撤销

## 关键环境变量

- `BOARDROOM_OS_WORKER_BOOTSTRAP_SIGNING_SECRET`
  bootstrap token 的签名密钥；未设置时会回退到 `BOARDROOM_OS_WORKER_SHARED_SECRET`
- `BOARDROOM_OS_WORKER_BOOTSTRAP_DEFAULT_TTL_SEC`
  CLI 没显式传 `--ttl-sec` 时使用的默认 bootstrap TTL
- `BOARDROOM_OS_WORKER_BOOTSTRAP_MAX_TTL_SEC`
  CLI 显式传入的 bootstrap TTL 上限
- `BOARDROOM_OS_WORKER_BOOTSTRAP_ALLOWED_TENANT_IDS`
  可选，逗号分隔；一旦设置，只允许对名单内租户通过 CLI 或 `worker-admin` HTTP 签发 bootstrap
- `BOARDROOM_OS_WORKER_SESSION_TTL_SEC`
  `session_token` 的刷新窗口
- `BOARDROOM_OS_PUBLIC_BASE_URL`
  把 worker 交付 URL 改写成外部真正可达的公开基座
- `BOARDROOM_OS_WORKER_DELIVERY_TOKEN_TTL_SEC`
  delivery URL 的默认过期时间
- `BOARDROOM_OS_WORKER_DELIVERY_SIGNING_SECRET`
  delivery URL 的签名密钥；未设置时会回退到 `BOARDROOM_OS_WORKER_SHARED_SECRET`

## 测试与默认存储

运行测试：

```bash
cd backend
source .venv/bin/activate
python -m pytest tests -q
```

默认数据库和产物路径：

- `backend/data/boardroom_os.db`
- `backend/data/artifacts/`，可用 `BOARDROOM_OS_ARTIFACT_STORE_ROOT` 覆盖

## 当前限制

- `backend/pyproject.toml` 的 editable install 还没完全补平
- 当前二进制上传仍走 `ticket-result-submit` 内联 `base64`
- 公开互联网场景下还没有完整身份层，当前 `worker-admin` 也只是受信控制面入口，不适合直接当公网租户自助面暴露
