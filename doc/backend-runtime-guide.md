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
- artifact cleanup 闭环：物理删除记账、scheduler 自动 cleanup，以及 `dashboard` 上可直接看的 cleanup 状态
- 外部 worker handoff：bootstrap token、refreshable session、signed delivery grants、artifact 访问、worker 命令 URL
- 多租户 worker 运维面：binding 生命周期、`worker-runtime` 投影读面、bootstrap issue 签发记录，以及带签名操作人令牌入口、独立动作审计读面的 `worker-admin` HTTP 管理面

## 本地运行

启动后端：

```bash
cd backend
source .venv/bin/activate
uvicorn app.main:app --reload
```

如果你这轮要直接调用 `worker-admin` HTTP 管理面，再额外带上：

```bash
BOARDROOM_OS_WORKER_ADMIN_SIGNING_SECRET=operator-signing-secret
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

artifact cleanup 默认会跟着 runner / in-process scheduler 一起跑：

- 默认每 300 秒检查一次过期 artifact
- `BOARDROOM_OS_ARTIFACT_CLEANUP_INTERVAL_SEC <= 0` 时关闭自动 cleanup，只保留手动命令兜底
- 自动 cleanup 的操作人默认记成 `system:artifact-cleanup`，可用 `BOARDROOM_OS_ARTIFACT_CLEANUP_OPERATOR_ID` 覆盖

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

现在也可以直接走后端控制面，而不是只能回本地 CLI。和上一轮不同的是，`worker-admin` 不再单独信裸请求头，必须先拿到短时效签名令牌，再用它调用接口。新的操作人令牌还会持久化 `token_id`，所以值守同学现在不只会“签一张短票”，还可以列出活动令牌、按 `token_id` 撤销，并从拒绝读面里确认它是否已经失效。

当前默认约束是：

- `python -m app.worker_admin_auth_cli issue-token` 不显式传 `--ttl-sec` 时，会使用 `BOARDROOM_OS_WORKER_ADMIN_DEFAULT_TTL_SEC`，默认 900 秒
- 显式传入的 `--ttl-sec` 不能超过 `BOARDROOM_OS_WORKER_ADMIN_MAX_TTL_SEC`，默认 3600 秒
- 令牌里的 `issued_at` / `expires_at` 必须带时区；后端只接受带时区的签名 claim，避免把无时区时间误当成可信身份
- 新签发令牌现在会带 `token_id`，并持久化到 `worker_admin_token_issue`；后端在 `worker-admin` / `worker-admin-audit` / `worker-admin-auth-rejections` 入口上会对这类新令牌做“验签 + 验状态”

先在本地签发一个平台管理员令牌：

```bash
cd backend
source .venv/bin/activate
python -m app.worker_admin_auth_cli issue-token \
  --operator-id ops@example.com \
  --role platform_admin \
  --ttl-sec 900
```

如果你要签发 scoped 角色令牌，就显式带上 scope：

```bash
cd backend
source .venv/bin/activate
python -m app.worker_admin_auth_cli issue-token \
  --operator-id tenant-admin@example.com \
  --role scope_admin \
  --tenant-id tenant_blue \
  --workspace-id ws_design \
  --ttl-sec 900
```

上面命令会回显 `operator_token` 和 `token_id`。后面的 HTTP 调用都把它放到 `X-Boardroom-Operator-Token`：

```bash
OPERATOR_TOKEN='<把 issue-token 输出里的 operator_token 粘进来>'

curl 'http://127.0.0.1:8000/api/v1/worker-admin/bindings?worker_id=emp_frontend_2&tenant_id=tenant_blue&workspace_id=ws_design' \
  -H "X-Boardroom-Operator-Token: ${OPERATOR_TOKEN}"

curl -X POST 'http://127.0.0.1:8000/api/v1/worker-admin/issue-bootstrap' \
  -H 'Content-Type: application/json' \
  -H "X-Boardroom-Operator-Token: ${OPERATOR_TOKEN}" \
  -d '{"worker_id":"emp_frontend_2","tenant_id":"tenant_blue","workspace_id":"ws_design","ttl_sec":120,"reason":"tenant admin bootstrap"}'

curl -X POST 'http://127.0.0.1:8000/api/v1/worker-admin/contain-scope' \
  -H 'Content-Type: application/json' \
  -H "X-Boardroom-Operator-Token: ${OPERATOR_TOKEN}" \
  -d '{"tenant_id":"tenant_blue","workspace_id":"ws_design","dry_run":true,"revoke_bootstrap_issues":true,"revoke_sessions":true,"reason":"tenant incident containment"}'

curl 'http://127.0.0.1:8000/api/v1/projections/worker-admin-audit?tenant_id=tenant_blue&workspace_id=ws_design&limit=20' \
  -H "X-Boardroom-Operator-Token: ${OPERATOR_TOKEN}"
```

查看当前还活着的操作人令牌：

```bash
cd backend
source .venv/bin/activate
python -m app.worker_admin_auth_cli list-tokens --tenant-id tenant_blue --workspace-id ws_design --active-only
```

撤销一张已经发出去的操作人令牌：

```bash
cd backend
source .venv/bin/activate
python -m app.worker_admin_auth_cli revoke-token \
  --token-id <token_id> \
  --revoked-by ops@example.com \
  --reason "tenant admin offboarded"
```

对应的 HTTP 管理面现在也能直接看和撤操作人令牌：

```bash
curl 'http://127.0.0.1:8000/api/v1/worker-admin/operator-tokens?tenant_id=tenant_blue&workspace_id=ws_design&active_only=true' \
  -H "X-Boardroom-Operator-Token: ${OPERATOR_TOKEN}"

curl -X POST 'http://127.0.0.1:8000/api/v1/worker-admin/revoke-operator-token' \
  -H 'Content-Type: application/json' \
  -H "X-Boardroom-Operator-Token: ${OPERATOR_TOKEN}" \
  -d '{"token_id":"<token_id>","reason":"tenant admin offboarded"}'

curl 'http://127.0.0.1:8000/api/v1/projections/worker-admin-auth-rejections?tenant_id=tenant_blue&workspace_id=ws_design&limit=20' \
  -H "X-Boardroom-Operator-Token: ${OPERATOR_TOKEN}"
```

当前已实现的管理接口：

- `GET /api/v1/worker-admin/bindings`
- `GET /api/v1/worker-admin/operator-tokens`
- `GET /api/v1/worker-admin/bootstrap-issues`
- `GET /api/v1/worker-admin/sessions`
- `GET /api/v1/worker-admin/delivery-grants`
- `GET /api/v1/worker-admin/auth-rejections`
- `GET /api/v1/worker-admin/scope-summary`
- `POST /api/v1/worker-admin/create-binding`
- `POST /api/v1/worker-admin/issue-bootstrap`
- `POST /api/v1/worker-admin/revoke-bootstrap`
- `POST /api/v1/worker-admin/revoke-session`
- `POST /api/v1/worker-admin/revoke-delivery-grant`
- `POST /api/v1/worker-admin/revoke-operator-token`
- `POST /api/v1/worker-admin/cleanup-bindings`
- `POST /api/v1/worker-admin/contain-scope`

当前已实现的独立审计读面：

- `GET /api/v1/projections/worker-admin-audit`
- `GET /api/v1/projections/worker-admin-auth-rejections`

说明：

- `/api/v1/worker-admin/*`、`GET /api/v1/projections/worker-admin-audit` 和 `GET /api/v1/projections/worker-admin-auth-rejections` 现在都必须带 `X-Boardroom-Operator-Token`
- 旧的 `X-Boardroom-Operator-Id`、`X-Boardroom-Operator-Role`、`X-Boardroom-Operator-Tenant-Id`、`X-Boardroom-Operator-Workspace-Id` 现在只剩兼容断言作用；如果带了且和令牌 claim 不一致，接口会直接返回 `400`
- 当前最小角色模型是：
  - `platform_admin`：可全局读写
  - `scope_admin`：只能读写自己 `tenant_id + workspace_id` 下的 worker 运维数据
  - `scope_viewer`：只能读取自己 `tenant_id + workspace_id` 下的 worker 运维数据，不能做任何止血或签发动作
- `operator-tokens` 读面会把平台级令牌和 scoped 令牌放在同一套契约里；但 scoped 角色只能显式查询自己 scope 下的 scoped 令牌，看不到平台级令牌
- `revoke-operator-token` 会直接撤销指定 `token_id`；只要这张票是新签发的持久化令牌，后续请求会立即被拒绝，不再只能等 TTL 到点
- scoped 角色现在必须显式查询或写入自己的 `tenant_id + workspace_id` scope，不能再只带 `worker_id` 做跨 scope 浏览
- `tenant_id` 和 `workspace_id` 必须成对出现；多 binding worker 在 `issue-bootstrap` / `revoke-bootstrap` 上也仍然要显式带 scope
- `issue-bootstrap`、`revoke-session`、`revoke-delivery-grant`、`contain-scope` 响应里的 `issued_by` / `revoked_by` 现在统一来自签名令牌里的操作人；请求体里如果还带这些字段，只会被当成兼容断言
- `sessions`、`delivery-grants`、`auth-rejections` 和 `scope-summary` 现在可以直接按 `tenant_id + workspace_id` 看整组租户 scope，而不必先知道具体 `worker_id`
- `worker-admin-audit` 会独立记录 `create-binding`、`issue-bootstrap`、`revoke-bootstrap`、`revoke-session`、`revoke-delivery-grant`、`cleanup-bindings`、`contain-scope` 这些动作，并保留 dry-run / 真执行差异
- `worker-admin-auth-rejections` 会记录缺票、坏票、过期、已撤销、兼容断言不一致和 scope 越权这些拒绝，值守同学现在可以直接确认某张票是不是还在撞入口
- `revoke-session` 必须二选一：要么按 `session_id` 撤一条会话，要么按 `worker_id + tenant_id + workspace_id` 撤一个明确 scope 下的会话
- `revoke-delivery-grant` 只按 `grant_id` 撤一条具体 delivery grant，不会把同 session 的兄弟 URL 一起撤掉
- `revoke-session` 会同步回显并落盘级联撤掉的 delivery grant 数，以及 `revoked_via` / `revoked_by` / `revoke_reason`
- `contain-scope` 用的是“先预演、再执行”的同一接口：`dry_run=true` 时只回显当前会命中的 bootstrap issue / session / delivery grant，不改 worker 运行态，但会写一条独立动作审计；`dry_run=false` 时必须同时带 `reason` 和 `expected_active_*` 计数
- `contain-scope` 真执行时会先撤活跃 bootstrap issue，再撤活跃 session，并让 session 继续沿现有级联逻辑撤活跃 delivery grant；它不会自动删 binding，也不会自动 cleanup binding
- 如果 `expected_active_bootstrap_issue_count`、`expected_active_session_count`、`expected_active_delivery_grant_count` 任一和执行瞬间的真实值不一致，接口会直接返回 `409`，避免拿着过期预演结果误伤现场
- scope containment 的批量止血会单独写 `revoked_via = worker_admin_scope_containment`，后续排障时可以和普通单条 revoke 区分开
- 这是一层“受信控制面”入口，不代表项目已经补齐公网身份层、反向代理断言或租户自助权限模型

## Worker handoff 现状

- 推荐路径是：先用 `issue-bootstrap` 生成 bootstrap token，再携带 `X-Boardroom-Worker-Bootstrap` 调 `GET /api/v1/worker-runtime/assignments`
- assignments 响应会返回 `tenant_id`、`workspace_id`、`session_id`、`session_token`、`session_expires_at` 和 assignment 列表
- worker 拿到 `session_token` 后，可以继续用 `X-Boardroom-Worker-Session` 轮询 `GET /api/v1/worker-runtime/assignments`
- execution package URL、artifact URL 和 command URL 都使用短时 `access_token`
- `/api/v1/worker-runtime/tickets/*`、`/api/v1/worker-runtime/artifacts/*` 和 `/api/v1/worker-runtime/commands/*` 只接受 signed URL，不再接受旧的共享密钥请求 fallback
- 现在也可以用 `GET /api/v1/projections/worker-runtime` 按同一组 filter 一次看到 binding、session、delivery grant 和最近拒绝日志，再用 `worker-admin` HTTP 或本地 CLI 做最小 scope 级处理
- `worker-runtime` 投影里的 session / delivery grant 现在会回显 `revoked_via`、`revoked_by`、`revoke_reason`，方便值守同学直接确认是谁、从哪、因为什么做了撤销

## Artifact cleanup

手动触发 cleanup 仍然保留，适合本地验证或值守兜底：

```bash
cd backend
source .venv/bin/activate
curl -X POST 'http://127.0.0.1:8000/api/v1/commands/artifact-cleanup' \
  -H 'Content-Type: application/json' \
  -d '{
    "cleaned_by": "emp_ops_1",
    "idempotency_key": "artifact-cleanup:manual-001"
  }'
```

当前真实行为：

- `EPHEMERAL + retention_ttl_sec` 的 artifact 会按显式 TTL 到期
- `EPHEMERAL` 如果没显式写 `retention_ttl_sec`，会自动落 `BOARDROOM_OS_ARTIFACT_EPHEMERAL_DEFAULT_TTL_SEC`；默认 7 天
- 旧库里 `EPHEMERAL` 但没有 `expires_at` 的 artifact，会在仓库初始化时按同一默认 TTL 回填，避免历史临时件永久滞留
- 如果 artifact 有本地落盘文件，cleanup 会把文件删掉，并在 `artifact_index` 里写 `storage_deleted_at`
- 已经写过 `storage_deleted_at` 的 artifact 不会在后续 cleanup 里被重复统计成 residual cleanup
- `GET /api/v1/projections/dashboard` 现在会返回 `artifact_maintenance`，可以直接看：
  - 自动 cleanup 是否开启
  - 当前默认 `EPHEMERAL` TTL
  - cleanup 间隔
  - 当前待过期 / 待物理删除积压
  - 历史遗留里还有多少 artifact 只能保守标成 `LEGACY_UNKNOWN`
  - 最近一次 cleanup 的时间、触发来源、操作者和删除数量
- `GET /api/v1/projections/tickets/{ticket_id}/artifacts` 现在会回显 `retention_ttl_sec`、`retention_policy_source`、`deleted_by`、`delete_reason` 和 `storage_deleted_at`
- `GET /api/v1/projections/artifact-cleanup-candidates` 可以直接列出当前 cleanup 候选，并区分：
  - `EXPIRED_DUE`：已经到过期时间，还没跑到真正 cleanup
  - `STORAGE_DELETE_PENDING`：逻辑上已删或已过期，但本地文件还没记账成 `storage_deleted_at`

## 关键环境变量

- `BOARDROOM_OS_WORKER_BOOTSTRAP_SIGNING_SECRET`
  bootstrap token 的签名密钥；未设置时会回退到 `BOARDROOM_OS_WORKER_SHARED_SECRET`
- `BOARDROOM_OS_WORKER_BOOTSTRAP_DEFAULT_TTL_SEC`
  CLI 没显式传 `--ttl-sec` 时使用的默认 bootstrap TTL
- `BOARDROOM_OS_WORKER_BOOTSTRAP_MAX_TTL_SEC`
  CLI 显式传入的 bootstrap TTL 上限
- `BOARDROOM_OS_WORKER_BOOTSTRAP_ALLOWED_TENANT_IDS`
  可选，逗号分隔；一旦设置，只允许对名单内租户通过 CLI 或 `worker-admin` HTTP 签发 bootstrap
- `BOARDROOM_OS_WORKER_ADMIN_SIGNING_SECRET`
  `worker-admin` 操作人令牌的签名密钥；未设置时，`worker-admin`、`worker-admin-audit` 和 `worker-admin-auth-rejections` 入口会 fail-closed，直接拒绝请求
- `BOARDROOM_OS_WORKER_ADMIN_DEFAULT_TTL_SEC`
  `worker-admin` 操作人令牌 CLI 在没显式传 `--ttl-sec` 时使用的默认 TTL，默认 900 秒
- `BOARDROOM_OS_WORKER_ADMIN_MAX_TTL_SEC`
  `worker-admin` 操作人令牌 CLI 允许签发的最大 TTL，默认 3600 秒
- `BOARDROOM_OS_WORKER_SESSION_TTL_SEC`
  `session_token` 的刷新窗口
- `BOARDROOM_OS_PUBLIC_BASE_URL`
  把 worker 交付 URL 改写成外部真正可达的公开基座
- `BOARDROOM_OS_WORKER_DELIVERY_TOKEN_TTL_SEC`
  delivery URL 的默认过期时间
- `BOARDROOM_OS_WORKER_DELIVERY_SIGNING_SECRET`
  delivery URL 的签名密钥；未设置时会回退到 `BOARDROOM_OS_WORKER_SHARED_SECRET`
- `BOARDROOM_OS_ARTIFACT_CLEANUP_INTERVAL_SEC`
  自动 artifact cleanup 的检查间隔，默认 300 秒；设成 `0` 或负数可关闭自动 cleanup
- `BOARDROOM_OS_ARTIFACT_CLEANUP_OPERATOR_ID`
  自动 cleanup 写入事件和 artifact 审计时使用的操作人，默认 `system:artifact-cleanup`
- `BOARDROOM_OS_ARTIFACT_EPHEMERAL_DEFAULT_TTL_SEC`
  `EPHEMERAL` artifact 没显式写 `retention_ttl_sec` 时使用的默认 TTL，默认 604800 秒（7 天）

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
