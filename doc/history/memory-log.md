# Memory Log

> This file is intentionally compact. Stable baseline context now lives in `doc/history/context-baseline.md`.
> Detailed older round logs still live in:
>
> - `doc/history/archive/memory-log-detailed-2026-03-27_to_2026-03-30.md`
> - `doc/history/archive/memory-log-detailed-2026-03-31_to_2026-04-02.md`

## How To Use This File

- Read `doc/history/context-baseline.md` first for stable rules and architecture.
- Read `doc/TODO.md` next for the current action list.
- Use this file only for recent changes that still affect implementation decisions.
- Open the archive only when exact historical rationale, raw verification commands, or old compatibility details are required.

## Current Mainline Truth

- Current executable truth now lives in `doc/mainline-truth.md`.
- This file no longer duplicates the stable product model, governance rules, or frozen-boundary notes.
- Treat this file as compressed recent memory, not as a second truth source.

## Recent Memory

### 2026-04-03

- `delivery_check_report@1` gained its own internal checker gate before final board review.
- Final board approval now auto-creates a `delivery_closeout_package@1` ticket, and workflow completion depends on that closeout loop finishing.
- Thin staffing deblocking became available in the React shell through `freeze / restore / hire request / replace request` controls.
- Added `doc/mainline-truth.md` as the dedicated entrypoint for current code truth and runtime support.
- OpenAI Compat live execution now retries `timeout / 429 / 5xx`, classifies non-retry failures cleanly, and falls back to deterministic execution without breaking the workflow.
- Provider health is now surfaced through stable labels: `LOCAL_ONLY / HEALTHY / INCOMPLETE / PAUSED`.
- `frontend_engineer` now has an independent runtime profile, while scope kickoff keeps a narrow compatibility alias to the legacy scope-only lane.

### 2026-04-04

- Successful live-path structured outputs now materialize the same default audit artifacts as deterministic execution, so scope approval, review evidence, and closeout read from one consistent shape.
- CEO shadow mode became real through `ceo_actions.py`, `ceo_snapshot.py`, `ceo_prompts.py`, `ceo_proposer.py`, `ceo_validator.py`, and `ceo_scheduler.py`.
- CEO then moved into a limited-execution first slice: accepted `CREATE_TICKET / RETRY_TICKET / HIRE_EMPLOYEE` actions now execute through the existing command handlers, while `ESCALATE_TO_BOARD` stays `DEFERRED_SHADOW_ONLY`.
- `project-init` now lets CEO create the first stable kickoff scope ticket instead of hardcoding that ticket in `command_handlers.py`.
- `scheduler_runner.py` now runs idle CEO maintenance when a workflow has no active approval or incident, no leased/executing ticket, and still has a clear actionable signal.
- Frontend data-layer split is now real: the live types, clients, SSE manager, hook, and Zustand stores moved under `frontend/src/types/`, `frontend/src/api/`, `frontend/src/hooks/`, and `frontend/src/stores/`.
- `App.tsx` is back to a pure router entry, while layout, dashboard, workforce, events, overlays, shared UI primitives, styles, and utilities all moved into dedicated folders.
- Persona data now has one source of truth in `backend/app/core/persona_profiles.py`; runtime execution packages carry `persona_summary`, and both Workforce and staffing review views expose that normalized persona shape.
- Full verification by the end of this day had reached `py -m pytest tests/ -q` -> `394 passed`, `npm run build` -> passed, and `npm run test:run` -> `49 passed`.

### 2026-04-05

- Expanded the old aggregated `P0-INT-*` placeholder into eight explicit integration-closure tasks in `doc/task-backlog.md`.
- Added explicit deterministic, provider fallback, staffing containment recovery, timeout recovery, repeated failure recovery, provider recovery, frontend smoke, and incident drawer regression proofs for the current mainline.
- Full verification for the integration-closure round reached `py -m pytest tests/ -q` -> `399 passed`, `npm run build` -> passed, and `npm run test:run` -> `50 passed`.
- Split long-term requirements into two tracks and kept them out of `doc/TODO.md`: framework capability and company governance.
- `doc/feature-spec.md`, `doc/milestone-timeline.md`, and `doc/task-backlog.md` now explicitly cover multi-model coexistence, role-to-model binding, task-level override, preferred/actual model tracking, and high-cost low-frequency routing.
- `DashboardPage.tsx` was further slimmed from 629 lines to 298 through page-level helper files, and `StaffingActions` now shows hire-template persona summary through `ProfileSummary`.
- Added the first ticket-backed meeting room slice without creating a second chat system: backend now supports `meeting-request`, four auditable meeting event types, a persisted meeting projection, and a `TECHNICAL_DECISION` meeting state machine that runs `POSITION -> CHALLENGE -> PROPOSAL -> CONVERGENCE` over a `consensus_document` ticket.
- The React shell now has a read-only meeting path at `/meeting/:meetingId`, and inbox meeting items open `MeetingRoomDrawer` with topic, participants, round summaries, consensus state, and jump-through to review room.
- CEO now has a limited `REQUEST_MEETING` execution path: `ceo_shadow_snapshot` exposes auditable `meeting_candidates`, deterministic mode only opens a meeting when exactly one candidate is eligible, and live provider proposals are constrained to those snapshot candidates.
- Automatic meetings stay narrow: they only cover decision-oriented ticket failure recovery or board `REJECT / MODIFY_CONSTRAINTS` realignment, they do not run in idle maintenance, and they do not recursively reopen `MEETING_ESCALATION`.
- Full verification for the CEO auto-meeting round finished at `py -m pytest tests/ -q` -> `408 passed`, `npm run build` -> passed, and `npm run test:run` -> `53 passed`.
- `P2-B` 的第一段保守收口已经落地：`FrozenCapabilityBoundary` 现在不只记路由和代码引用，还显式记录真实入口、主线依赖、测试归属和迁移前置条件。
- 这轮把 `P1-CLN-005`、`P1-CLN-006` 真实关闭了，但没有启动 `_frozen/` 物理迁移；当前确认的原因有两个：多租户 scope 仍是共享数据结构，`artifact_uploads` 仍被主线 `ticket-result-submit` 桥接使用。
- 这轮完整验证结果是：`py -m pytest tests/ -q` -> `409 passed`，`npm run build` -> passed，`npm run test:run` -> `53 passed`。
- `P1-CLN-001` 这轮已从“未开始”推进到“进行中”：`worker-admin` 共用的 scope / bootstrap / session / grant helper 已抽到 `worker_scope_ops.py`，`worker-admin` 专属 projection 入口已从通用 `projections.py` 中拆出到独立文件。
- 这次拆分没有启动 `_frozen/` 物理迁移；当前仍保持 worker-admin API、auth、projection、CLI 一起移动的前置条件，不提前碰 `P1-CLN-002` 到 `P1-CLN-004`。
- 这轮完整验证结果更新为：`py -m pytest tests/ -q` -> `411 passed`，`npm run build` -> passed，`npm run test:run` -> `53 passed`。
- `P1-CLN-002` 到 `P1-CLN-004` 这轮没有转入物理迁移，只做了阻塞评估收口：`FrozenCapabilityBoundary` 现在额外保存 `migration_blocker_refs` 和 `migration_blocker_summary`，把“为什么现在还不能迁”写成结构化真相。
- `backend/tests/test_mainline_truth.py` 现在会直接扫描共享 contracts、`ticket-result-submit` 上传桥接点，以及 `worker-runtime` API / 投影 / CLI / repository schema 的源码锚点，避免后续把阻塞原因又写回口头判断。
- 这轮最终验证结果是：`py -m pytest tests/ -q` -> `414 passed`，`npm run build` -> passed，`npm run test:run` -> `53 passed`；其中后端仍需用 `py -m pytest`，因为当前 shell 下裸 `pytest` 不在 PATH。
- 首页 UI 真实缺口第一轮已经收口：`InboxWell`、`Workflow River`、`WorkforcePanel`、`EventTicker` 在初次加载时都改成真实骨架屏，不再只靠一条全局 loading 文案占位。
- `Workflow River` 这轮没有重做视觉语言，只在现有粒子和 Board Gate 提醒上补了两件事：窄屏保留横向河道表达，`prefers-reduced-motion` 下关闭漂移动画和呼吸动画。
- 新增前端回归测试覆盖首页 loading / board gate 语义：`BoardGateIndicator`、`InboxWell`、`WorkflowRiver`、`WorkforcePanel`、`EventTicker` 现在都有对应断言。
- 本轮完整验证结果更新为：后端先确认 `pytest tests/ -q` 在当前 shell 下仍报 `CommandNotFoundException`，再用 `py -m pytest tests/ -q` 实测 `414 passed`；前端 `npm run build` -> passed，`npm run test:run` -> `59 passed`。
- 前端当前全部可达路由这轮已补齐键盘可访问性基础：`AppShell` 新增 skip link，主布局改成 `main` landmark，`Drawer` 会处理初始焦点、焦点循环、`Escape` 关闭、关闭后回到触发元素，并在打开时锁住背景滚动。
- 这轮暗色主题没有扩成 light theme；只把 surface / divider / focus / disabled / board / incident 语义收口到统一 token，并把首页、按钮、输入框和 overlay 的对比度补稳。
- 当前性能收口只做了两件真实变更：`ReviewRoomDrawer`、`MeetingRoomDrawer`、`IncidentDrawer`、`DependencyInspectorDrawer`、`ProviderSettingsDrawer` 改成按需懒加载；`useSSE` 对 `boardroom-event` 失效通知默认做 `500ms` debounce。
- 新增前端回归测试覆盖抽屉焦点管理、直接路由落到 review 抽屉时的初始焦点，以及 `useSSE` 的 clustered invalidation debounce；本轮前端验证结果更新为 `npm run build` -> passed，`npm run test:run` -> `64 passed`。
- `P1-CLN-002` 这轮已把主线 command 侧的 `tenant_id/workspace_id` 收口掉：`ProjectInitCommand`、`TicketCreateCommand` 已不再暴露这两个字段，`project-init`、`ticket-create`、CEO 建票、审批 follow-up、closeout 和会议室建票都统一改成从 workflow/default 解析 scope。
- `/api/v1/commands/project-init` 和 `/api/v1/commands/ticket-create` 当前仍保留弃用兼容输入，旧字段还能传，但不会再影响主线行为；冻结多租户链路相关测试改成显式 seed 带 scope 的 workflow，再让 ticket-create 继承 workflow scope。
- `backend/app/core/mainline_truth.py` 与 `backend/tests/test_mainline_truth.py` 这轮已改成新的阻塞口径：主线 command 已解耦，但 runtime、`worker-admin / worker-runtime` contracts 和共享读面仍保留多租户 shape，所以 `P1-CLN-002` 还不能收口成 `_frozen/` 物理迁移。
- 这轮完整验证结果是：后端先确认 `pytest tests/ -q` 仍报 `CommandNotFoundException`，再用 `py -m pytest tests/ -q` 实测 `415 passed`；前端 `npm run build` -> passed，`npm run test:run` -> `64 passed`。

### 2026-04-06

- `P2-B` 这轮继续停在保守收口，没有启动 `_frozen/` 物理迁移；新增的是“成组迁移清单”这层代码真相，而不是功能变更。
- `backend/app/core/mainline_truth.py` 里的 `FrozenCapabilityBoundary` 现在会显式记录每个冻结切片对应的 `api_surface_groups` 和 `storage_table_refs`，把 route family 与共享存储锚点收口成机器可读事实。
- `backend/tests/test_mainline_truth.py` 这轮新增回归：不仅检查入口文件和阻塞摘要，还会直接校验冻结边界引用的 API 分组名仍在 `api_surface.py` 中受支持、共享表名仍能在 `repository.py` 的建表语句里找到。
- `P1-CLN-003` 已从阻塞评估推进到真实进行中：`TicketWrittenArtifact` 不再接受 `upload_session_id`，`ticket-result-submit` 现在只处理 inline 内容或已有 `artifact_ref`。
- 新增了控制面 `POST /api/v1/commands/ticket-artifact-import-upload` 和 `worker-runtime` 同构命令；上传会话完成后先导入为普通 artifact，再进入结果提交。
- `worker-runtime` 执行包的 `command_endpoints` 现在多了 `ticket_artifact_import_upload_url`，worker delivery token 也补了同名命令范围，外部 handoff 保持兼容。
- `backend/app/core/mainline_truth.py` 与 `backend/tests/test_mainline_truth.py` 这轮同步成新口径：主线 result-submit 已与 upload session 解耦，但 upload 导入入口和 upload session 存储仍保留，所以 `P1-CLN-003` 还不能直接收口成 `_frozen/` 迁移。
- 本轮完整验证结果是：后端先确认 `pytest tests/ -q` 仍报 `CommandNotFoundException`，再用重定向方式执行 `py -m pytest tests/ -q` 实测 `416 passed`；前端 `npm run build` -> passed，`npm run test:run` -> `64 passed`。
- `P1-CLN-004` 这轮已从阻塞评估推进到真实进行中：`/api/v1/projections/worker-runtime` 已从通用 `projections.py` 拆到独立 `worker_runtime_projections.py`，`worker-runtime` 的投影入口边界先收清了。
- `build_worker_runtime_projection(...)` 这轮不再直接散读 repository 的 binding/session/grant/rejection 查询，当前统一改成复用 `worker_scope_ops.py` 里的现成 helper，避免 handoff 管理读面继续有两套活跃态判定。
- 本轮完整验证结果更新为：后端先确认 `pytest tests/ -q` 仍报 `CommandNotFoundException`，再用 `py -m pytest tests/ -q` 实测 `417 passed`；前端 `npm run build` -> passed，`npm run test:run` -> `64 passed`。
- `README.md`、`doc/backend-runtime-guide.md`、`doc/api-reference.md`、`doc/README.md` 这轮已同步到当前代码现实：文档现在会把主线和冻结兼容面分开写，并显式记录当前 Windows shell 下 `pytest` 不在 PATH 的事实。
- 为了防止接口文档再次和代码漂移，本轮新增了 `backend/app/core/api_surface.py` 与 `backend/tests/test_api_surface.py`，把当前 FastAPI 路由分组固定成最小回归测试。
- 这轮最终验证结果更新为：后端先确认 `pytest tests/ -q` 仍报 `CommandNotFoundException`，再用重定向方式执行 `py -m pytest tests/ -q` 实测 `418 passed`；前端 `npm run build` -> passed，`npm run test:run` -> `64 passed`。
- `P1-CLN-001`、`P1-CLN-003`、`P1-CLN-004` 这轮继续停在前置拆分，没有启动 `_frozen/` 物理迁移；新增的是 `backend/app/api/router_registry.py`，把 frozen 兼容路由的挂载边界收口成统一注册表。
- `backend/app/main.py` 现在只通过 `include_registered_routers(app)` 挂载路由；`backend/app/core/api_surface.py`、`backend/tests/test_api_surface.py`、`backend/tests/test_mainline_truth.py` 已改成直接复用这份组顺序并回归 frozen 组仍被注册。
- 这轮没有改任何 HTTP 路径、鉴权、命令契约或投影结构；变化只在内部挂载边界和对应测试。
- 本轮验证结果更新为：后端先确认 `pytest tests/ -q` 仍报 `CommandNotFoundException`，再用重定向方式执行 `py -m pytest tests/ -q` 实测 `420 passed`；前端 `npm run build` -> passed，`npm run test:run` -> `64 passed`。
- `P1-CLN-001` 这轮已真实完成 shim 迁移：`worker-admin` 的 API、auth、projection、core 和 CLI 实现都迁入了 `backend/app/_frozen/worker_admin/`，旧入口只保留薄转发。
- `backend/app/core/mainline_truth.py` 与 `backend/tests/test_mainline_truth.py` 这轮同步成新口径：`worker-admin` 的 `code_refs` 已切到 `_frozen/worker_admin`，但兼容壳仍保留，所以还不能把它写成“入口已删除”。
- `backend/tests/conftest.py` 这轮改成直接 monkeypatch `_frozen.worker_admin.core.worker_admin`，避免 shim 导出层吞掉测试里的时间注入。
- 本轮完整验证结果更新为：后端先确认 `pytest tests/ -q` 仍报 `CommandNotFoundException`，再用 `py -m pytest tests/ -q` 实测 `422 passed`；前端 `npm.cmd run build` -> passed，`npm.cmd run test:run` -> `64 passed`。
- `P1-CLN-004` 这轮已按 shim 迁移收口：`backend/app/_frozen/worker_runtime/` 现在承接 `worker-runtime` 的 API、projection、core 和 CLI 真实实现，旧 `app/api/worker_runtime*.py`、`app/core/worker_runtime.py`、`app/worker_auth_cli.py` 只保留薄转发。
- `backend/tests/conftest.py` 与 `backend/tests/test_mainline_truth.py` 这轮同步改成新口径：时间注入直接命中 `_frozen.worker_runtime`，`external_worker_handoff.code_refs` 也已切到 `_frozen/worker_runtime`，但 `worker_bootstrap/session/delivery-grant` schema 仍是保留阻塞点。
- 本轮完整验证结果是：后端先确认 `pytest tests/ -q` 在当前 shell 仍因未进入项目虚拟环境而失败，再用 `./.venv/bin/pytest tests/ -q` 实测 `422 passed`；前端在补装缺失依赖后 `npm run build` -> passed，`npm run test:run` -> `64 passed`。

## Current Working Set

- Prefer reading `README.md`, `doc/README.md`, `doc/mainline-truth.md`, `doc/roadmap-reset.md`, `doc/TODO.md`, `doc/history/context-baseline.md`, and then this file before touching the archive.
- Treat this file as semantic memory plus compressed recent progress, not as a full transcript.
- When adding new memory, keep only facts that still change implementation decisions; push raw logs and exhaustive verification into archive files.

## Archive Index

- `doc/history/archive/memory-log-detailed-2026-03-27_to_2026-03-30.md`: detailed early history before the roadmap reset was fully absorbed.
- `doc/history/archive/memory-log-detailed-2026-03-31_to_2026-04-02.md`: detailed recent implementation notes before this compaction pass.
