# Backend 运行与 Worker 运维

这份文档承接根目录 `README.md` 里不适合放在首页的运行细节，主要面向当前在仓库里继续开发或排查 Runtime / Backend 的人。

如果你只是想先判断"现在什么是真的"，先看 [mainline-truth.md](mainline-truth.md)。这份文档更偏运行和排障，不再把冻结能力写成当前主线。

## 当前可运行切片

当前后端位于 `backend/`，技术栈是 FastAPI + Pydantic v2 + SQLite。

当前主线里已经真实落地的能力包括：

- 命令入口、投影视图和 SSE 事件流
- `project-init` 现在会先物化 `board-brief`，再由 CEO 发起首个 kickoff scope 共识票，继续复用现有 `consensus_document@1 + MEETING_ESCALATION`
- ticket 创建、lease、start、heartbeat、结构化结果提交、取消和人工恢复
- 最小 incident / circuit-breaker / retry 治理链
- 视觉里程碑最小 Maker-Checker 闭环：maker 完成后自动生成 checker ticket，checker 通过后再进入 review room，要求返工则自动生成带 required fixes 的 fix ticket；相同 blocking finding 指纹重复达到阈值时会直接升级为 incident / breaker
- 员工治理最小闭环：默认 roster 现在由 employee 事件 bootstrap，`employee-hire-request / employee-replace-request` 会走 `CORE_HIRE_APPROVAL -> Inbox -> Review Room -> board approve`，`employee-freeze` 会立即阻止新 dispatch / lease / start / worker-runtime bootstrap，`employee-restore` 会把 `FROZEN` 员工直接恢复回 `ACTIVE`
- 最小 workforce 读面：`GET /api/v1/projections/workforce` 会按角色泳道返回当前员工状态、活动态、当前 ticket/node 和 provider 绑定
- review room 与 board approve / reject / modify constraints
- artifact store / artifact index / ticket artifacts projection
- Context Compiler 最小内联链：`TEXT / MARKDOWN / JSON` 且当前可读的 input artifact 会直接进 compiled execution package；超预算的文本和 JSON 现在会先退到确定性的相关片段编译，片段仍放不下时再退到头部预览 / 顶层预览，并在 bundle / manifest 里写明结构化降级原因和 selector；图片 / PDF 会作为结构化媒体引用保留；其他二进制、未落盘、已删除材料仍保留 descriptor + URL 兜底
- 最小真实 provider 适配层：当 in-process runtime 遇到 `provider_id=prov_openai_compat`，并且本地配置了兼容 OpenAI `responses` 的 `base_url / api_key / model` 后，会直接打 `POST {base_url}/responses`；未配置时继续走本地 deterministic runtime
- artifact cleanup 闭环：场景留存分级、物理删除记账、scheduler 自动 cleanup，以及 `dashboard` 上可直接看的 cleanup 状态

## 仓库保留但冻结

下面这些能力还在仓库里，部分入口也还挂着，但**默认不继续扩张**。除非直接解堵本地 MVP，否则这轮不要把它们当当前主线：

- `worker-admin` HTTP 管理面与操作人令牌链
- 多租户 `tenant/workspace` scope binding
- 控制面分段上传与可选对象存储
- 外部 worker handoff、bootstrap、session、delivery grant

## 本地运行

运行前提：

- 后端命令默认都假设你已经在 `backend/` 目录下，并且先执行了 `source .venv/bin/activate`
- 如果当前机器还没有这个虚拟环境，先按项目依赖把 `fastapi / httpx / pydantic / uvicorn / pytest` 装进 `backend/.venv`

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

如果你希望这层入口只能经过受信反向代理，再额外配置：

```bash
BOARDROOM_OS_WORKER_ADMIN_TRUSTED_PROXY_IDS=corp-edge-a,corp-edge-b
```

启用 FastAPI 进程内 scheduler：

```bash
cd backend
source .venv/bin/activate
BOARDROOM_OS_ENABLE_INPROCESS_SCHEDULER=true uvicorn app.main:app --reload
```

如果你这轮要开 artifact 对象存储，再额外带上：

```bash
BOARDROOM_OS_ARTIFACT_OBJECT_STORE_ENABLED=true
BOARDROOM_OS_ARTIFACT_OBJECT_STORE_ENDPOINT=http://127.0.0.1:9000
BOARDROOM_OS_ARTIFACT_OBJECT_STORE_BUCKET=boardroom-artifacts
BOARDROOM_OS_ARTIFACT_OBJECT_STORE_ACCESS_KEY=minioadmin
BOARDROOM_OS_ARTIFACT_OBJECT_STORE_SECRET_KEY=minioadmin
```

如果你是在新环境里第一次启这个能力，还需要把后端按可选依赖装上对象存储 SDK：

```bash
cd backend
pip install -e .[objectstore]
```

如果你本地只做大文件链路验证、不想开对象存储，默认什么都不配即可；分段上传 staging 会继续落本机文件系统。

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
- CEO idle maintenance 默认也会跟着 runner / in-process scheduler 一起检查
- `BOARDROOM_OS_CEO_MAINTENANCE_INTERVAL_SEC` 默认是 `60`；当 workflow 没有 open approval / incident、没有 leased / executing 工单，但仍有 `无票待起步 / ready ticket / failed ticket` 这三类待推进信号时，scheduler 会补打一轮 `SCHEDULER_IDLE_MAINTENANCE`
- `BOARDROOM_OS_CEO_MAINTENANCE_INTERVAL_SEC <= 0` 时关闭这层 idle maintenance，只保留事件驱动 CEO 触发

## 运行模式

- `BOARDROOM_OS_RUNTIME_EXECUTION_MODE=INPROCESS` 是默认值，runner / in-process scheduler 会在 `LEASED` 后直接执行当前最小 runtime
- `BOARDROOM_OS_RUNTIME_EXECUTION_MODE=EXTERNAL` 时，runner / in-process scheduler 只负责 dispatch / lease，不再自动 `start / execute / result-submit`

兼容 OpenAI provider 的真实调用规则：

- 只在 `provider_id == prov_openai_compat` 且 `BOARDROOM_OS_PROVIDER_OPENAI_COMPAT_BASE_URL / API_KEY / MODEL` 三个配置都存在时启用
- `base_url` 可以直接带 `/v1`，运行时会调用 `POST {base_url}/responses`
- 如果配置了 `BOARDROOM_OS_PROVIDER_OPENAI_COMPAT_REASONING_EFFORT`，运行时会把它透传成 `reasoning.effort`；当前支持 `low / medium / high / xhigh`
- 请求输入直接来自编译后的 `rendered_execution_payload.messages`；后端不会依赖 provider 端 JSON schema 强约束，而是拿回文本后在本地做 JSON 解析和现有 output schema 校验
- 当前代码现实里，这条 live path 已覆盖主线需要的 6 组 role/schema 组合：
  - `ui_designer_primary -> consensus_document`
  - `frontend_engineer_primary -> implementation_bundle`
  - `checker_primary -> delivery_check_report`
  - `frontend_engineer_primary -> ui_milestone_review`
  - `frontend_engineer_primary -> delivery_closeout_package`
  - `checker_primary -> maker_checker_verdict`
- `frontend_engineer` 现在已经有独立的 `frontend_engineer_primary` worker profile
- 只有 `project-init -> scope review` 这条旧共识链仍保留 `ui_designer_primary`；调度层会把 `frontend_engineer_primary` 兼容匹配到这类旧票，避免 scope 主链中断
- 失败映射固定为：`429 -> PROVIDER_RATE_LIMITED`、超时 / 连接失败 / `5xx -> UPSTREAM_UNAVAILABLE`、`401/403 -> PROVIDER_AUTH_FAILED`、其他 `4xx` / 空响应 / 非 JSON / 结构不匹配 -> `PROVIDER_BAD_RESPONSE`
- 只有 `PROVIDER_RATE_LIMITED` 和 `UPSTREAM_UNAVAILABLE` 会进入既有 provider incident / breaker 暂停链；鉴权失败和坏响应只让当前 ticket 失败，不自动扩大成 provider pause

当前执行包的编译边界：

- 已完整内联：当前可读且已物化、并且能放进预算内的 `TEXT / MARKDOWN / JSON` input artifact
- 已片段编译：超预算但还能压进预算的 `TEXT / MARKDOWN / JSON` 会优先保留确定性的相关片段，当前文本会走 `MARKDOWN_SECTION` / `TEXT_WINDOW`，JSON 会走 `JSON_PATH`
- 已保底预览：片段仍放不下预算时，`TEXT / MARKDOWN / JSON` 会退到确定性的头部摘录或顶层 JSON 预览，并标明 `INLINE_BUDGET_EXCEEDED`
- 已结构化引用：`IMAGE / PDF` 不内联原始二进制正文，但会在 `artifact_access` 里显式带上 `kind`、`preview_kind=INLINE_MEDIA`、`display_hint=OPEN_PREVIEW_URL` 和 worker 可直接消费的 URL
- 仍走结构化下载引用：其他二进制 artifact 不内联原始正文，但会在 `artifact_access` 里显式带上 `kind`、`preview_kind=DOWNLOAD_ONLY`、`display_hint=DOWNLOAD_ATTACHMENT` 和 worker 可直接消费的 URL
- 仍走 descriptor：`REGISTERED_ONLY`、已删除 / 已过期材料、读取失败材料，以及当前不能安全解码的正文
- 即使已经内联，执行包里仍保留 `artifact_access`，并把 `display_hint` 同步到 context block 顶层；文本类正文会显式标成 `INLINE_BODY`，所以 worker 不需要靠字段名猜“这是正文、预览还是下载”
- worker execution package 在 signed URL 重写之后，仍会保留 `artifact_access.kind / preview_kind / display_hint` 这些展示语义；不会因为 URL 被改写就退回成一条模糊附件

排障时如果走 `GET /api/v1/projections/review-room/{review_pack_id}/developer-inspector`：

- 除了原始 `compiled_context_bundle` 和 `compile_manifest`，现在还会附带一层 `compile_summary`
- 这层摘要会直接告诉你本次编译共有多少 source、多少完整内联、多少片段内联、多少部分预览、多少纯引用，以及各类降级原因码的计数
- 现在还会单独汇总媒体引用数量、下载型附件数量、各片段策略计数、各预览策略计数，以及 `preview_kind` 计数；排障时不再需要手翻 context blocks 才知道 worker 看到的是正文、预览还是下载引用
- 当前常见原因码包括：`ARTIFACT_NOT_INDEXED`、`ARTIFACT_NOT_READABLE`、`MEDIA_REFERENCE_ONLY`、`BINARY_REFERENCE_ONLY`、`INLINE_BUDGET_EXCEEDED`

## 员工治理命令

当前与员工生命周期直接相关的最小命令面是：

- `POST /api/v1/commands/employee-hire-request`
  - 为一个新员工发起 `CORE_HIRE_APPROVAL`，进入现有 `Inbox -> Review Room`
- `POST /api/v1/commands/employee-replace-request`
  - 为已有员工发起换人审批；board approve 后会写入“replacement hire + old employee replaced”两条事件
- `POST /api/v1/commands/employee-freeze`
  - 立即把员工从新 dispatch / lease / start / worker-runtime bootstrap 入口上摘掉，不等待 board gate
- `POST /api/v1/commands/employee-restore`
  - 立即把已经 `FROZEN` 的员工恢复回 `ACTIVE`，重新放开 scheduler dispatch、手动 `ticket-lease` 和 `worker-runtime` bootstrap；这也是即时治理命令，不走 `Inbox -> Review Room`
- `GET /api/v1/projections/workforce`
  - 按角色泳道返回当前 active / frozen / replaced 员工，以及他们当前是否在执行 ticket

如果你只是为了兼容旧链路，才需要切到外部 worker handoff 模式：

```bash
cd backend
source .venv/bin/activate
BOARDROOM_OS_RUNTIME_EXECUTION_MODE=EXTERNAL \
BOARDROOM_OS_WORKER_BOOTSTRAP_SIGNING_SECRET=bootstrap-signing-secret \
BOARDROOM_OS_WORKER_DELIVERY_SIGNING_SECRET=delivery-signing-secret \
BOARDROOM_OS_PUBLIC_BASE_URL=http://127.0.0.1:8000 \
uvicorn app.main:app --reload
```

## 冻结能力：Worker bootstrap 与运维命令

下面这组命令仍然可用，但属于保留兼容面，不是当前主线默认操作路径。

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

## 冻结能力：Worker admin HTTP 管理面

这部分仍保留在仓库里，方便排查或兼容旧链路，但默认不作为当前 MVP 的继续建设方向。

现在也可以直接走后端控制面，而不是只能回本地 CLI。和上一轮不同的是，`worker-admin` 不再单独信裸请求头，必须先拿到短时效签名令牌，再用它调用接口。新的操作人令牌还会持久化 `token_id`，所以值守同学现在不只会“签一张短票”，还可以列出活动令牌、按 `token_id` 撤销，并从拒绝读面里确认它是否已经失效。对于挂在反向代理后的部署，现在还可以额外开启可信代理断言，把入口进一步收口到预期代理。

当前默认约束是：

- `python -m app.worker_admin_auth_cli issue-token` 不显式传 `--ttl-sec` 时，会使用 `BOARDROOM_OS_WORKER_ADMIN_DEFAULT_TTL_SEC`，默认 900 秒
- 显式传入的 `--ttl-sec` 不能超过 `BOARDROOM_OS_WORKER_ADMIN_MAX_TTL_SEC`，默认 3600 秒
- 令牌里的 `issued_at` / `expires_at` 必须带时区；后端只接受带时区的签名 claim，避免把无时区时间误当成可信身份
- 新签发令牌现在会带 `token_id`，并持久化到 `worker_admin_token_issue`；后端在 `worker-admin` / `worker-admin-audit` / `worker-admin-auth-rejections` 入口上会对这类新令牌做“验签 + 验状态”
- 如果配置了 `BOARDROOM_OS_WORKER_ADMIN_TRUSTED_PROXY_IDS`，上述三个入口还必须带 `X-Boardroom-Trusted-Proxy-Id`，并且值必须命中白名单

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
  -H "X-Boardroom-Operator-Token: ${OPERATOR_TOKEN}" \
  -H 'X-Boardroom-Trusted-Proxy-Id: corp-edge-a'

curl -X POST 'http://127.0.0.1:8000/api/v1/worker-admin/issue-bootstrap' \
  -H 'Content-Type: application/json' \
  -H "X-Boardroom-Operator-Token: ${OPERATOR_TOKEN}" \
  -H 'X-Boardroom-Trusted-Proxy-Id: corp-edge-a' \
  -d '{"worker_id":"emp_frontend_2","tenant_id":"tenant_blue","workspace_id":"ws_design","ttl_sec":120,"reason":"tenant admin bootstrap"}'

curl -X POST 'http://127.0.0.1:8000/api/v1/worker-admin/contain-scope' \
  -H 'Content-Type: application/json' \
  -H "X-Boardroom-Operator-Token: ${OPERATOR_TOKEN}" \
  -H 'X-Boardroom-Trusted-Proxy-Id: corp-edge-a' \
  -d '{"tenant_id":"tenant_blue","workspace_id":"ws_design","dry_run":true,"revoke_bootstrap_issues":true,"revoke_sessions":true,"reason":"tenant incident containment"}'

curl 'http://127.0.0.1:8000/api/v1/projections/worker-admin-audit?tenant_id=tenant_blue&workspace_id=ws_design&limit=20' \
  -H "X-Boardroom-Operator-Token: ${OPERATOR_TOKEN}" \
  -H 'X-Boardroom-Trusted-Proxy-Id: corp-edge-a'
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
  -H "X-Boardroom-Operator-Token: ${OPERATOR_TOKEN}" \
  -H 'X-Boardroom-Trusted-Proxy-Id: corp-edge-a'

curl -X POST 'http://127.0.0.1:8000/api/v1/worker-admin/revoke-operator-token' \
  -H 'Content-Type: application/json' \
  -H "X-Boardroom-Operator-Token: ${OPERATOR_TOKEN}" \
  -H 'X-Boardroom-Trusted-Proxy-Id: corp-edge-a' \
  -d '{"token_id":"<token_id>","reason":"tenant admin offboarded"}'

curl 'http://127.0.0.1:8000/api/v1/projections/worker-admin-auth-rejections?tenant_id=tenant_blue&workspace_id=ws_design&limit=20' \
  -H "X-Boardroom-Operator-Token: ${OPERATOR_TOKEN}" \
  -H 'X-Boardroom-Trusted-Proxy-Id: corp-edge-a'
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
- 一旦配置了 `BOARDROOM_OS_WORKER_ADMIN_TRUSTED_PROXY_IDS`，上述入口还必须带 `X-Boardroom-Trusted-Proxy-Id`，缺失会返回 `403 missing_trusted_proxy_assertion`，不在白名单会返回 `403 untrusted_proxy_assertion`
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
- `worker-admin-audit` 里的每条动作现在还会回显 `trusted_proxy_id` 和 `source_ip`，值守同学可以直接确认这次操作是从哪条受信入口打进来的
- `worker-admin-auth-rejections` 会记录缺票、坏票、过期、已撤销、兼容断言不一致、可信代理断言缺失 / 不可信和 scope 越权这些拒绝；summary 里也会直接回显当前是否强制可信代理以及白名单内容
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

- `PERSISTENT` artifact 默认不过期
- `REVIEW_EVIDENCE + retention_ttl_sec` 的 artifact 会按显式 TTL 到期
- `REVIEW_EVIDENCE` 如果没显式写 `retention_ttl_sec`，会自动落 `BOARDROOM_OS_ARTIFACT_REVIEW_EVIDENCE_DEFAULT_TTL_SEC`；默认 30 天
- `OPERATIONAL_EVIDENCE + retention_ttl_sec` 的 artifact 会按显式 TTL 到期
- `OPERATIONAL_EVIDENCE` 如果没显式写 `retention_ttl_sec`，会自动落 `BOARDROOM_OS_ARTIFACT_OPERATIONAL_EVIDENCE_DEFAULT_TTL_SEC`；默认 14 天
- `EPHEMERAL + retention_ttl_sec` 的 artifact 会按显式 TTL 到期
- `EPHEMERAL` 如果没显式写 `retention_ttl_sec`，会自动落 `BOARDROOM_OS_ARTIFACT_EPHEMERAL_DEFAULT_TTL_SEC`；默认 7 天
- 调用方如果没显式写 `retention_class`，后端会按保守路径规则补默认值：
  - `reports/review/*` -> `REVIEW_EVIDENCE`
  - `reports/ops/*` -> `OPERATIONAL_EVIDENCE`
  - `reports/diagnostics/*` -> `OPERATIONAL_EVIDENCE`
  - 其他路径 -> `PERSISTENT`
- 旧库里 `REVIEW_EVIDENCE` / `OPERATIONAL_EVIDENCE` / `EPHEMERAL` 但没有 `expires_at` 的 artifact，会在仓库初始化时按各自默认 TTL 回填，避免历史评审材料或临时件永久滞留
- 如果 artifact 有本地落盘文件或远端对象，cleanup 都会尝试删掉底层存储，并在 `artifact_index` 里回写 `storage_backend`、`storage_delete_status`、`storage_delete_error` 和 `storage_deleted_at`
- 已经写过 `storage_deleted_at` 的 artifact 不会在后续 cleanup 里被重复统计成 residual cleanup
- `GET /api/v1/projections/dashboard` 现在会返回 `artifact_maintenance`，可以直接看：
  - 自动 cleanup 是否开启
  - 当前默认 `EPHEMERAL` TTL
  - 当前默认 `REVIEW_EVIDENCE` TTL
  - 四类留存语义的默认规则映射
  - cleanup 间隔
  - 当前待过期 / 待物理删除积压
  - 当前仍删不掉、处于 `DELETE_FAILED` 的 artifact 数量
  - 历史遗留里还有多少 artifact 只能保守标成 `LEGACY_UNKNOWN`
  - 最近一次 cleanup 的时间、触发来源、操作者和删除数量
- `GET /api/v1/projections/tickets/{ticket_id}/artifacts` 现在会回显 `retention_class_source`、`retention_ttl_sec`、`retention_policy_source`、`deleted_by`、`delete_reason`、`storage_backend`、`storage_delete_status` 和 `storage_deleted_at`
- `GET /api/v1/projections/artifact-cleanup-candidates` 可以直接列出当前 cleanup 候选，并区分：
  - `EXPIRED_DUE`：已经到过期时间，还没跑到真正 cleanup
  - `STORAGE_DELETE_PENDING`：逻辑上已删或已过期，但本地文件或远端对象还没记账成 `storage_deleted_at`

## 大文件上传会话

这轮新增的是“控制面 multipart”，不是浏览器直传，也不是外部 worker signed URL 直传。

- `POST /api/v1/artifact-uploads/sessions`
  - 创建上传会话，返回 `session_id`
- `PUT /api/v1/artifact-uploads/sessions/{session_id}/parts/{part_number}`
  - 按 part number 上传二进制分片
- `POST /api/v1/artifact-uploads/sessions/{session_id}/complete`
  - 校验 part 连续性并合并 staging 内容，状态流转到 `COMPLETED`
- `POST /api/v1/artifact-uploads/sessions/{session_id}/abort`
  - 终止会话并删除 staging 文件

`ticket-result-submit` 里的二进制 `written_artifacts[*]` 现在支持：

- 小文件继续走 `content_base64`
- 中大文件改走 `upload_session_id`
- 两者不能同时提供

## 关键环境变量

- `BOARDROOM_OS_PROVIDER_OPENAI_COMPAT_BASE_URL`
  兼容 OpenAI `responses` 站点的基座地址；允许直接写成类似 `https://api-vip.codex-for.me/v1`
- `BOARDROOM_OS_PROVIDER_OPENAI_COMPAT_API_KEY`
  `prov_openai_compat` 路径使用的 bearer token
- `BOARDROOM_OS_PROVIDER_OPENAI_COMPAT_MODEL`
  `prov_openai_compat` 路径请求里带出的模型名
- `BOARDROOM_OS_PROVIDER_OPENAI_COMPAT_REASONING_EFFORT`
  可选；透传到 `responses` 请求体里的 `reasoning.effort`，支持 `low / medium / high / xhigh`
- `BOARDROOM_OS_PROVIDER_OPENAI_COMPAT_TIMEOUT_SEC`
  真实 provider 调用超时时间，默认 `30` 秒；必须大于 `0`
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
- `BOARDROOM_OS_WORKER_ADMIN_TRUSTED_PROXY_IDS`
  可选，逗号分隔；一旦设置，`worker-admin`、`worker-admin-audit` 和 `worker-admin-auth-rejections` 都必须带 `X-Boardroom-Trusted-Proxy-Id`，并且值必须命中白名单
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
- `BOARDROOM_OS_ARTIFACT_OPERATIONAL_EVIDENCE_DEFAULT_TTL_SEC`
  `OPERATIONAL_EVIDENCE` artifact 没显式写 `retention_ttl_sec` 时使用的默认 TTL，默认 1209600 秒（14 天）
- `BOARDROOM_OS_ARTIFACT_REVIEW_EVIDENCE_DEFAULT_TTL_SEC`
  `REVIEW_EVIDENCE` artifact 没显式写 `retention_ttl_sec` 时使用的默认 TTL，默认 2592000 秒（30 天）
- `BOARDROOM_OS_ARTIFACT_UPLOAD_STAGING_ROOT`
  分段上传 staging 目录；默认 `backend/data/artifact_uploads/`
- `BOARDROOM_OS_ARTIFACT_UPLOAD_PART_SIZE_LIMIT_BYTES`
  单个上传分片大小上限；默认 5 MiB
- `BOARDROOM_OS_ARTIFACT_UPLOAD_MAX_SIZE_BYTES`
  单次上传总大小上限；默认 100 MiB
- `BOARDROOM_OS_ARTIFACT_UPLOAD_MAX_PART_COUNT`
  单次上传允许的最大分片数；默认 10000
- `BOARDROOM_OS_ARTIFACT_OBJECT_STORE_ENABLED`
  是否启用可选对象存储后端；默认关闭
- `BOARDROOM_OS_ARTIFACT_OBJECT_STORE_ENDPOINT`
  S3 兼容对象存储 endpoint；启用对象存储时必填
- `BOARDROOM_OS_ARTIFACT_OBJECT_STORE_BUCKET`
  S3 兼容对象存储 bucket；启用对象存储时必填
- `BOARDROOM_OS_ARTIFACT_OBJECT_STORE_ACCESS_KEY`
  S3 兼容对象存储 access key；启用对象存储时必填
- `BOARDROOM_OS_ARTIFACT_OBJECT_STORE_SECRET_KEY`
  S3 兼容对象存储 secret key；启用对象存储时必填
- `BOARDROOM_OS_ARTIFACT_OBJECT_STORE_REGION`
  可选，对象存储 region；未填时走 SDK 默认

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
- 当前真实 provider 只落了一个 `prov_openai_compat -> POST {base_url}/responses` 适配；不支持 chat-completions 并行、不支持多 provider routing / fallback，也不做多模型矩阵
- 当前大文件链路只补到控制面分段上传；还没有扩到 worker-runtime 上传面、浏览器直传或云厂商预签名 multipart
- 公开互联网场景下还没有完整身份层；当前 `worker-admin` 即使加了可信代理断言，也仍只是受信控制面入口，不适合直接当公网租户自助面暴露
