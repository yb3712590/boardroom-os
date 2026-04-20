# Backend 运行与运维指南

这份文档承接根目录 `README.md` 里不适合放在首页的运行细节，主要面向继续开发、排障和验证后端的人。

如果你只是想先判断“现在什么是真的”，先看 [mainline-truth.md](mainline-truth.md)。如果你需要逐条查接口，再看 [api-reference.md](api-reference.md)。

## 1. 当前后端定位

当前后端位于 `backend/`，技术栈是 FastAPI + Pydantic v2 + SQLite。它仍然是整个系统的执行中心：

- durable truth 在事件日志和确定性投影里
- React 只读投影、提交治理命令，不持有工作流真相
- runtime 默认走本地 deterministic；当前 registry 首版可选走 `OpenAI Compat` 或 `Claude Code CLI`
- maker-checker、incident、review room、closeout 都已经进入主链；但 `runtime ticket / legacy compat` 硬切还在收尾，手工 scope review 历史测试链和部分 scheduler recovery 还没完全收口

## 2. 当前主线与冻结边界

当前主线已经真实落地的能力：

- 命令入口、投影视图和 SSE 事件流
- `project-init -> scope review -> BUILD -> CHECK -> final REVIEW -> closeout` 这条 canonical 主线这轮已补齐到 closeout：scope review 不再依赖 legacy `followup_tickets` contract，closeout / provider-backed / timeout / repeated-failure recovery 的当前历史测试桶也已跑通
- 当前剩余风险集中在 workflow completion truth，而不是主链断裂：minimal recovery seed 下，timeout / repeated-failure 两条历史桶现在确认的是“closeout 票完成”，workflow 级 dashboard completion 仍可能被额外 `GRAPH_HEALTH_CRITICAL` incident 挂住
- `project-init` 先物化 `board-brief`，再由 CEO 发起首个 kickoff scope 共识票
- `project-init` 现在还会创建受管项目工作区，固定三分区 `00-boardroom / 10-project / 20-evidence`；第一版支持 `AGILE / HYBRID / COMPLIANCE`
- ticket 创建、lease、start、heartbeat、结构化结果提交、取消、人工恢复
- workspace-managed 代码票现在会走最小文档 hook：编译前写 `worker-preflight` 回执，结果提交时硬校验文档更新、测试证据和 git commit，并写 `worker-postrun / evidence-capture / git-closeout` 回执
- `delivery_closeout_package` 现在也走 `structured_document_delivery` 主线：默认写到 `20-evidence/closeout/<ticket>/`，并额外校验 `payload.final_artifact_refs` 必须对齐已知 delivery evidence
- 员工治理最小闭环：`employee-hire-request / employee-replace-request / employee-freeze / employee-restore`
- meeting room 最小版：既可手动发起，也支持 CEO 在窄触发条件下自动发起 `TECHNICAL_DECISION`
- artifact upload/import、artifact cleanup、dashboard cleanup 状态读面

仓库里仍保留、但默认冻结的能力：

- `worker-admin` HTTP 管理面与操作人令牌链
- 多租户 `tenant/workspace` scope binding
- 可选对象存储
- 外部 worker handoff、bootstrap、session、delivery grant

这些冻结面不是“坏掉不能用”，而是“默认不作为当前 MVP 的继续建设方向”。

## 3. 本地启动

运行前提：

- 后端命令默认都假设你已经在 `backend/` 目录下
- 如果当前机器还没有虚拟环境，先把依赖装进 `backend/.venv`

POSIX shell：

```bash
cd backend
source .venv/bin/activate
uvicorn app.main:app --reload
```

当前 Windows PowerShell：

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
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

启动图书馆管理系统 live 集成场景：

```bash
cd backend
source .venv/bin/activate
export BOARDROOM_OS_PROVIDER_OPENAI_COMPAT_BASE_URL="https://<your-openai-compatible-base-url>/v1"
export BOARDROOM_OS_PROVIDER_OPENAI_COMPAT_API_KEY="<your-api-key>"
python -m tests.live.library_management_autopilot_live
```

当前主线 full live 入口有 3 条：

- `python -m tests.live.library_management_autopilot_live`
- `python -m tests.live.requirement_elicitation_autopilot_live`
- `python -m tests.live.architecture_governance_autopilot_live`

当前还额外补了一条更轻的 governance smoke：

- `python -m tests.live.architecture_governance_autopilot_smoke`

每条场景默认都会先清空再重建自己的目录：

- `backend/data/scenarios/library_management_autopilot_live/`
- `backend/data/scenarios/requirement_elicitation_autopilot_live/`
- `backend/data/scenarios/architecture_governance_autopilot_live/`
- `backend/data/scenarios/architecture_governance_autopilot_smoke/`

里面会单独保存：

- `boardroom_os.db`
- `runtime-provider-config.json`
- `artifacts/`
- `artifact_uploads/`
- `developer_inspector/`
- `ticket_context_archives/`
- `run_report.json`
- `failure_snapshots/`

## 4. 验证与当前 shell 现实

后端目标验证命令仍是：

```bash
cd backend
pytest tests/ -q
```

但当前 Windows PowerShell 实测里，裸 `pytest` 仍可能报 `CommandNotFoundException`。这时按真实环境改用：

```powershell
cd backend
py -m pytest tests/ -q
```

本轮整体验证口径：

```bash
cd backend
pytest tests/ -q

cd ../frontend
npm run build
npm run test:run
```

当前后端全量回归基线：

- `./.venv/bin/pytest tests/ -q -> 555 passed`

当前这轮补记：

- 如果仓库本身跑在 Git linked worktree 里，`backend/tests/conftest.py` 现在会自动把测试用 `BOARDROOM_OS_PROJECT_WORKSPACE_ROOT` 放到系统临时目录，避免测试中的项目 worktree 再嵌 Git worktree 时触发 Git 的 `$GIT_DIR too big`
- `backend/app/core/project_workspaces.py` 的 Git 子进程现在会统一带 `stdin=DEVNULL`；这台 Windows + Python 3.14 机器上，`project-init / ticket-start / ticket-result-submit` 相关的 `git init / worktree / rev-parse` 已不再因为句柄继承报 `WinError 6`
- Windows 下 `pytest` 的临时目录权限仍可能有系统级噪声；这时继续建议显式带 repo 内 `--basetemp`，例如：

```powershell
cd backend
py -m pytest tests/test_ceo_scheduler.py -q --basetemp D:\Projects\boardroom-os\.tmp\pytest-ceo
```

如果你要跑这条新的真实长测，单独用：

```bash
cd backend
python -m tests.live.library_management_autopilot_live
python -m tests.live.requirement_elicitation_autopilot_live
python -m tests.live.architecture_governance_autopilot_live
python -m tests.live.architecture_governance_autopilot_smoke
```

它不进入默认 `pytest tests/ -q`。

默认数据库和产物路径：

- `backend/data/boardroom_os.db`
- `backend/data/artifacts/`
- `backend/data/artifact_uploads/`
- `backend/data/project_workspaces/`
- `backend/data/runtime-provider-config.json`
- `backend/data/developer_inspector/`

live 集成场景会把这些路径整体重定向到各自场景目录：

- `backend/data/scenarios/<scenario-slug>/`

项目工作区相关补记：

- 默认项目工作区根目录由 `BOARDROOM_OS_PROJECT_WORKSPACE_ROOT` 控制；未显式覆盖时落到 `backend/data/project_workspaces/`
- 当前只有带 workspace manifest 的 workflow 会启用新的 workspace-managed 文档 / git gate
- 旧的 artifact-path 代码票仍保持兼容，不会被这条新 gate 误伤
- 测试环境下如果仓库位于 linked worktree，fixture 会临时把 `BOARDROOM_OS_PROJECT_WORKSPACE_ROOT` 切到系统临时目录；这只是测试防噪，不改变线上默认路径

## 5. 运行模式与 provider

运行模式：

- `BOARDROOM_OS_RUNTIME_EXECUTION_MODE=INPROCESS` 是默认值，runner / in-process scheduler 会在 `LEASED` 后直接执行当前最小 runtime
- `BOARDROOM_OS_RUNTIME_EXECUTION_MODE=EXTERNAL` 时，runner / in-process scheduler 只负责 dispatch / lease，不再自动 `start / execute / result-submit`

当前 `runtime-provider-config.json` 已经切到 registry 结构：

- `default_provider_id`
- `providers[]`
- `role_bindings[]`

当前 `providers[]` 里最小还会带：

- `capability_tags[]`
- `fallback_provider_ids[]`

当前 provider 选择顺序：

- 先看 `ceo_shadow` 或 ticket `role_profile` 的角色绑定
- 再回退员工投影里的 `provider_id` 兼容字段
- 最后才回退 `default_provider_id`
- 没有命中或配置不完整时，回退本地 deterministic
- 命中 live provider 后，只有在 `PROVIDER_RATE_LIMITED / UPSTREAM_UNAVAILABLE` 时，才会按当前 provider 的 `fallback_provider_ids[]` 顺序尝试满足目标能力底线的备选 provider

`OpenAI Compat` live path 的真实规则：

- 只在 registry 里启用 `prov_openai_compat`，且 `BASE_URL / API_KEY / MODEL` 三项都存在时启用
- `base_url` 可以直接带 `/v1`，运行时会调用 `POST {base_url}/responses`
- 如果配置了 `reasoning_effort`，运行时会透传 `reasoning.effort`
- 请求输入直接来自编译后的 `rendered_execution_payload.messages`
- 返回结果会在本地做 JSON 解析和现有 output schema 校验，不把 provider 端 schema 当唯一真相

`Claude Code CLI` live path 的真实规则：

- 只在 registry 里启用 `prov_claude_code`，且显式配置 `command_path / model` 时启用
- provider 健康明细不会做主动探活；当前只看启停、配置完整度、provider incident pause 和 Claude 命令可解析性
- 当前通过 `claude --print --output-format text --permission-mode bypassPermissions --json-schema '{"type":"object"}'` 走非交互调用
- 请求输入当前按编译后的 `rendered_execution_payload.messages` 逐条转成结构化文本 prompt
- CLI 返回结果同样会在本地做 JSON 解析和现有 output schema 校验，不把 CLI 输出当唯一真相

当前 live path 已覆盖主线需要的 6 组 role / schema 组合：

- `ui_designer_primary -> consensus_document`
- `frontend_engineer_primary -> source_code_delivery`
- `checker_primary -> delivery_check_report`
- `frontend_engineer_primary -> ui_milestone_review`
- `frontend_engineer_primary -> delivery_closeout_package`
- `checker_primary -> maker_checker_verdict`

当前 live runner 已收成共享 harness，3 条 full 入口和 1 条 checkpoint smoke 共用同一套 provider 配置与目录骨架：

- `tests.live.library_management_autopilot_live`
- `tests.live.requirement_elicitation_autopilot_live`
- `tests.live.architecture_governance_autopilot_live`
- `tests.live.architecture_governance_autopilot_smoke`
- provider 模板固定从 `backend/data/integration-test-provider-config.json` 读取；后续要追加 provider，直接改这一个文件里的 `providers[] / provider_model_entries[] / role_bindings[]`
- 会先把所有角色统一绑定到 `prov_openai_compat::gpt-5.4`
- `architect_primary` 固定走 `xhigh`
- 其他 live 角色固定走 `high`
- runtime 结果现在会把 `effective_reasoning_effort` 一并写进 assumptions，方便长测验收
- 每条场景都会产出 `run_report.json`、`ticket_context_archives/` 和 `failure_snapshots/`
- `run_report.json` 现在会带 `completion_mode`：full 长测写 `full`，checkpoint smoke 写 `checkpoint_smoke`

失败映射：

- `429 -> PROVIDER_RATE_LIMITED`
- 超时 / 连接失败 / `5xx -> UPSTREAM_UNAVAILABLE`
- `401/403 -> PROVIDER_AUTH_FAILED`
- 其他 `4xx` / 空响应 / 非 JSON / 结构不匹配 -> `PROVIDER_BAD_RESPONSE`

只有 `PROVIDER_RATE_LIMITED` 和 `UPSTREAM_UNAVAILABLE` 会进入既有 provider incident / breaker 暂停链；`Claude Code CLI` 首版不会走额外重试策略，失败后直接回退现有 deterministic 路径。

## 6. 主线运维面

当前主线最常用的读写面是：

- `GET /api/v1/projections/dashboard`
- `GET /api/v1/projections/inbox`
- `GET /api/v1/projections/workforce`
- `GET /api/v1/projections/review-room/{review_pack_id}`
- `GET /api/v1/projections/workflows/{workflow_id}/dependency-inspector`
- `GET /api/v1/projections/incidents/{incident_id}`
- `GET /api/v1/projections/meetings/{meeting_id}`
- `GET /api/v1/projections/runtime-provider`
- `POST /api/v1/commands/project-init`
- `POST /api/v1/commands/board-approve`
- `POST /api/v1/commands/board-reject`
- `POST /api/v1/commands/modify-constraints`
- `POST /api/v1/commands/incident-resolve`
- `POST /api/v1/commands/runtime-provider-upsert`

员工治理最小命令面：

- `POST /api/v1/commands/employee-hire-request`
- `POST /api/v1/commands/employee-replace-request`
- `POST /api/v1/commands/employee-freeze`
- `POST /api/v1/commands/employee-restore`

开发排障最常用的附加读面：

- `GET /api/v1/projections/review-room/{review_pack_id}/developer-inspector`
- `GET /api/v1/projections/workflows/{workflow_id}/ceo-shadow`
- `GET /api/v1/projections/tickets/{ticket_id}/artifacts`
- `GET /api/v1/projections/artifact-cleanup-candidates`

这两个点现在要先记住：

- `ceo-shadow.reuse_candidates.recent_completed_tickets` 不会再提前暴露未过 `MEETING_ESCALATION` 的 `consensus_document`
- 五类治理文档仍然只会在 internal governance gate 通过后进入复用候选

如果你在查 live 场景为什么卡住，优先看当前场景目录下这两个位置：

- `backend/data/scenarios/<scenario-slug>/ticket_context_archives/`
- `backend/data/scenarios/<scenario-slug>/failure_snapshots/`

完整接口说明见 [api-reference.md](api-reference.md)。

## 7. Artifact 上传、导入与清理

当前中大文件链路不是浏览器直传，也不是外部 worker 直传，而是：

`artifact-uploads session -> complete -> ticket-artifact-import-upload -> ticket-result-submit 引用 artifact_ref`

上传会话接口：

- `POST /api/v1/artifact-uploads/sessions`
- `PUT /api/v1/artifact-uploads/sessions/{session_id}/parts/{part_number}`
- `POST /api/v1/artifact-uploads/sessions/{session_id}/complete`
- `POST /api/v1/artifact-uploads/sessions/{session_id}/abort`

当前写回规则：

- 小文件继续在 `ticket-result-submit.written_artifacts[*]` 里走 inline 内容
- 中大文件先走 upload session，再调用 `ticket-artifact-import-upload`
- `ticket-result-submit` 现在只接 inline 内容或已有 `artifact_ref`
- `deliverable_kind=structured_document_delivery` 的票现在必须声明至少一条 `artifact_ref`、落至少一条 `written_artifact`，而且 declared `artifact_ref` 至少有一条要和本次写盘对上
- 五类治理文档在上面这层统一 gate 之外，还要继续满足 `payload.document_kind_ref == output_schema_ref`

artifact cleanup 当前真实行为：

- `PERSISTENT` 默认不过期
- `REVIEW_EVIDENCE` 默认 30 天
- `OPERATIONAL_EVIDENCE` 默认 14 天
- `EPHEMERAL` 默认 7 天
- cleanup 会同时处理逻辑过期和底层存储删除记账
- `dashboard.artifact_maintenance` 可直接查看最近一次 cleanup、待处理积压和失败数量

手动触发 cleanup：

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

## 8. 冻结兼容面

### 8.1 Worker runtime / external handoff

如果你只是为了兼容旧链路，才需要切到外部 worker handoff：

```bash
cd backend
source .venv/bin/activate
BOARDROOM_OS_RUNTIME_EXECUTION_MODE=EXTERNAL \
BOARDROOM_OS_WORKER_BOOTSTRAP_SIGNING_SECRET=bootstrap-signing-secret \
BOARDROOM_OS_WORKER_DELIVERY_SIGNING_SECRET=delivery-signing-secret \
BOARDROOM_OS_PUBLIC_BASE_URL=http://127.0.0.1:8000 \
uvicorn app.main:app --reload
```

当前兼容链路规则：

- 先用 bootstrap token 调 `GET /api/v1/worker-runtime/assignments`
- assignments 会返回 `tenant_id / workspace_id / session_id / session_token / session_expires_at`
- 后续用 `X-Boardroom-Worker-Session` 继续轮询 assignments
- execution package URL、artifact URL 和 command URL 都使用短时 `access_token`
- `/api/v1/worker-runtime/tickets/*`、`/api/v1/worker-runtime/artifacts/*` 和 `/api/v1/worker-runtime/commands/*` 只接受 signed URL
- `GET /api/v1/projections/worker-runtime` 可按同一组 filter 看 binding、session、delivery grant 和最近拒绝日志

### 8.2 Worker admin

`worker-admin` 现在必须先拿短时效签名令牌，再走 HTTP 管理面。它仍可用，但默认只是保留兼容面。

令牌签发示例：

```bash
cd backend
source .venv/bin/activate
python -m app.worker_admin_auth_cli issue-token \
  --operator-id ops@example.com \
  --role platform_admin \
  --ttl-sec 900
```

一旦配置了 `BOARDROOM_OS_WORKER_ADMIN_TRUSTED_PROXY_IDS`，`worker-admin`、`worker-admin-audit` 和 `worker-admin-auth-rejections` 都必须带 `X-Boardroom-Trusted-Proxy-Id`。

当前最小角色模型：

- `platform_admin`：全局读写
- `scope_admin`：只能读写一个 `tenant_id + workspace_id`
- `scope_viewer`：只能读一个 `tenant_id + workspace_id`

### 8.3 可选对象存储

对象存储仍保留，但默认关闭，不作为当前主线继续扩张。

如果你要开它：

```bash
BOARDROOM_OS_ARTIFACT_OBJECT_STORE_ENABLED=true
BOARDROOM_OS_ARTIFACT_OBJECT_STORE_ENDPOINT=http://127.0.0.1:9000
BOARDROOM_OS_ARTIFACT_OBJECT_STORE_BUCKET=boardroom-artifacts
BOARDROOM_OS_ARTIFACT_OBJECT_STORE_ACCESS_KEY=minioadmin
BOARDROOM_OS_ARTIFACT_OBJECT_STORE_SECRET_KEY=minioadmin
```

新环境第一次启用时还需要：

```bash
cd backend
pip install -e .[objectstore]
```

## 9. 关键环境变量

runtime / provider：

- `BOARDROOM_OS_RUNTIME_EXECUTION_MODE`
- `BOARDROOM_OS_PROVIDER_OPENAI_COMPAT_BASE_URL`
- `BOARDROOM_OS_PROVIDER_OPENAI_COMPAT_API_KEY`
- `BOARDROOM_OS_PROVIDER_OPENAI_COMPAT_MODEL`
- `BOARDROOM_OS_PROVIDER_OPENAI_COMPAT_REASONING_EFFORT`
- `BOARDROOM_OS_PROVIDER_OPENAI_COMPAT_TIMEOUT_SEC`

scheduler / cleanup：

- `BOARDROOM_OS_ENABLE_INPROCESS_SCHEDULER`
- `BOARDROOM_OS_CEO_MAINTENANCE_INTERVAL_SEC`
- `BOARDROOM_OS_ARTIFACT_CLEANUP_INTERVAL_SEC`
- `BOARDROOM_OS_ARTIFACT_CLEANUP_OPERATOR_ID`

artifact retention / upload：

- `BOARDROOM_OS_ARTIFACT_REVIEW_EVIDENCE_DEFAULT_TTL_SEC`
- `BOARDROOM_OS_ARTIFACT_OPERATIONAL_EVIDENCE_DEFAULT_TTL_SEC`
- `BOARDROOM_OS_ARTIFACT_EPHEMERAL_DEFAULT_TTL_SEC`
- `BOARDROOM_OS_ARTIFACT_UPLOAD_STAGING_ROOT`
- `BOARDROOM_OS_ARTIFACT_UPLOAD_PART_SIZE_LIMIT_BYTES`
- `BOARDROOM_OS_ARTIFACT_UPLOAD_MAX_SIZE_BYTES`
- `BOARDROOM_OS_ARTIFACT_UPLOAD_MAX_PART_COUNT`

worker-runtime / handoff：

- `BOARDROOM_OS_WORKER_BOOTSTRAP_SIGNING_SECRET`
- `BOARDROOM_OS_WORKER_BOOTSTRAP_DEFAULT_TTL_SEC`
- `BOARDROOM_OS_WORKER_BOOTSTRAP_MAX_TTL_SEC`
- `BOARDROOM_OS_WORKER_BOOTSTRAP_ALLOWED_TENANT_IDS`
- `BOARDROOM_OS_WORKER_SESSION_TTL_SEC`
- `BOARDROOM_OS_PUBLIC_BASE_URL`
- `BOARDROOM_OS_WORKER_DELIVERY_TOKEN_TTL_SEC`
- `BOARDROOM_OS_WORKER_DELIVERY_SIGNING_SECRET`

worker-admin：

- `BOARDROOM_OS_WORKER_ADMIN_SIGNING_SECRET`
- `BOARDROOM_OS_WORKER_ADMIN_TRUSTED_PROXY_IDS`
- `BOARDROOM_OS_WORKER_ADMIN_DEFAULT_TTL_SEC`
- `BOARDROOM_OS_WORKER_ADMIN_MAX_TTL_SEC`

object store：

- `BOARDROOM_OS_ARTIFACT_OBJECT_STORE_ENABLED`
- `BOARDROOM_OS_ARTIFACT_OBJECT_STORE_ENDPOINT`
- `BOARDROOM_OS_ARTIFACT_OBJECT_STORE_BUCKET`
- `BOARDROOM_OS_ARTIFACT_OBJECT_STORE_ACCESS_KEY`
- `BOARDROOM_OS_ARTIFACT_OBJECT_STORE_SECRET_KEY`
- `BOARDROOM_OS_ARTIFACT_OBJECT_STORE_REGION`

## 10. 当前限制

- `backend/pyproject.toml` 的 editable install 还没完全补平
- 当前真实 provider 只落了一个 `prov_openai_compat -> POST {base_url}/responses` 适配
- 当前大文件链路只补到控制面分段上传，还没有扩到 worker-runtime 上传面、浏览器直传或云厂商预签名 multipart
- 公开互联网场景下还没有完整身份层；`worker-admin` 即使加了可信代理断言，也仍只是受信控制面入口
