# Integration Test 013 审计整理

## 结论

第 13 轮 `library_management_autopilot_live_013` 的业务 workflow 最终进入 `COMPLETED / closeout`，但这不能等价为“图书馆管理系统已完成并可交付”。

本轮真实状态应拆开看：

- 架构与实施方案：较完整，已形成 PRD 级架构简报、技术决策、里程碑计划、详细设计和 backlog fanout。
- runtime workflow：已跑到 closeout。
- 原始 runner：最后失败在 live assertion profile。
- 修补 harness 后的 DB 重放：通过。
- 交付物实际质量：未通过最终交付检查。`BR-CHECK-001` 产出 `FAIL_CLOSED`，指出实现物化、启动、QA、文档和 scope manifest 证据不足。
- runtime 缺陷：CEO/autopilot 把 `FAIL_CLOSED` 的检查报告继续包装成 closeout，最终将半成品标成 `COMPLETED / closeout`。

因此，本轮主要价值是暴露了架构治理、实施 fanout、checker closeout 和 assertion profile 的问题；不能把本轮产物视为正式完成的网站系统。

## 基本信息

- 日期：2026-04-26 至 2026-04-27
- 场景 slug：`library_management_autopilot_live_013`
- workflow：`wf_3514435f5e6d`
- north star：完整《图书馆管理系统 PRD v1.0》，PRD 正文嵌入 live TOML
- 测试配置：`backend/data/live-tests/library_management_autopilot_live_013.toml`
- 后端留档副本：`backend/library_management_autopilot_live_013.toml`
- 审计场景目录：`backend/data/scenarios/library_management_autopilot_live_013`
- assertion profile：`library_management_prd`

## 模型与运行参数

- 默认模型：`gpt-5.4` / `high`
- CEO：`gpt-5.5` / `high`
- 架构/分析：`architect_primary`、`cto_primary`、`checker_primary` 使用 `gpt-5.5` / `xhigh`
- 开发：`frontend_engineer_primary`、`backend_engineer_primary`、`database_engineer_primary`、`platform_sre_primary` 使用 `gpt-5.3-codex` / `high`
- UI 设计：`ui_designer_primary` 使用 `gpt-5.4` / `high`
- `budget_cap = 5000000`
- `runtime.max_ticks = 900`
- `runtime.timeout_sec = 43200`

## 已验证结果

- `python -m pytest tests/test_live_configured_runner.py -q`：`11 passed`
- `python -m pytest tests/test_live_library_management_runner.py -q`：最终 `54 passed`
- `python -m pytest tests/test_runtime_provider_center.py -q`：`14 passed`
- 已完成 DB 重放：`collect_common_outcome()` + `scenario.assert_outcome()` 通过
- 原始自然执行的 runner 最后一次退出仍为失败，失败点是最终 assertion profile 与实际 PRD follow-up 结构不匹配

## 架构与实施方案摘要

本轮架构治理产物包括：

- `architecture_brief.json`
- `technology_decision.json`
- `milestone_plan.json`
- `detailed_design.json`
- `backlog_recommendation.json`

核心架构合同：

- API-first / contract-first。
- 前端使用 Vue 3、Vite、Element Plus、Vue Router、Pinia、ECharts。
- 后端默认 Node.js + TypeScript REST API。
- SQLite 为单一事务事实源。
- JWT + 服务端 RBAC；前端菜单只做展示过滤。
- 不引入 Redis、强制 Docker、强制外部 ISBN/邮件服务或生产 HA。
- ISBN 与邮件必须支持本地 fallback 或 mock。
- 图书可见性、可用性解析、标题歧义、Remove、借还续约预约罚款事务、预约保留、报表、审计均有明确合同。

backlog fanout 被拆成 14 个稳定 handoff：

- `BR-GOV-001` 治理与 AC 可追溯
- `BR-SET-001` 项目目录和启动骨架
- `BR-QA-PLAN-001` QA 计划
- `BR-BE-FOUND-001` 后端基础、认证、RBAC、health
- `BR-DB-DOMAIN-001` SQLite schema、migration、seed
- `BR-BE-CATALOG-001` 目录、ISBN、可用性、Remove
- `BR-BE-CIRC-001` 借还续约预约罚款事务流
- `BR-BE-OPS-001` 库存、通知、报表、CSV、审计
- `BR-FE-FOUND-001` 前端基础、认证、路由、动态菜单
- `BR-FE-CRITICAL-001` 目录、读者、馆员、流通、Remove UI
- `BR-FE-OPS-001` 库存、Admin、报表、通知、响应式
- `BR-QA-FINAL-001` 最终 QA
- `BR-DOC-001` README、API、seed 账号、证据包
- `BR-CHECK-001` 最终 checker closeout

## 问题与修补

### P00. Pytest 临时目录权限问题

现象：初次运行 `tests/test_live_configured_runner.py` 时受系统 Temp 权限影响。

处理：将 `TMP/TEMP` 临时切到 `backend/.tmp/pytest-013` 后运行。

验证：`tests/test_live_configured_runner.py` 通过，结果 `11 passed`。

状态：环境级 workaround，不涉及业务代码。

### P01. provider `stream_read_error` 自动恢复

现象：初始推进中出现 `CEO_SHADOW_PIPELINE_FAILED`，错误为 `OpenAICompatProviderBadResponseError / stream_read_error`。

根因：证据指向 provider stream 读取中断，未发现本地配置或 harness contract 错误。

处理：系统通过 `RERUN_CEO_SHADOW` 自动恢复，无需代码修补。

验证：incident 关闭，workflow 继续推进。

状态：无需保留代码变更；继续作为 provider 稳定性风险记录。

### P02. CTO staffing gap 与 duplicate hire 死循环

现象：workflow 在 backlog recommendation 后卡住。controller 认为缺 `cto_primary`，不断建议 `HIRE_EMPLOYEE`，但 roster 中已有 active board-approved `emp_cto_governance`，validator 又拒绝重复招聘。CEO 尝试 `NO_ACTION` 也被拒绝，因为 controller 仍要求 `HIRE_EMPLOYEE`。

根因：

- `BR-GOV-001` 的 `target_role=cto` 映射到 `cto_primary`。
- backlog follow-up 默认 `output_schema_ref` 落成 `source_code_delivery`。
- CTO 治理角色不支持该执行合同，导致 controller 误判 staffing gap。
- 派单路径未强制 assignee 具备对应 `role_profile_ref`，容易把治理票派给错误 planning 角色。

修补：

- 在 `backend/app/core/workflow_controller.py` 中，将 backlog follow-up 的 `cto_primary` 输出 schema 改为 `backlog_recommendation`。
- backlog follow-up 默认派单要求 assignee 包含对应 `role_profile_ref`。
- 保持治理初始化路径的既有宽松派单行为不变。
- 增加回归测试 `test_ceo_shadow_snapshot_uses_existing_cto_for_backlog_governance_followup`。

验证：

- RED 阶段复现 `STAFFING_REQUIRED`。
- 修补后单测 `1 passed`。
- 定向回归 `3 passed`。

状态：建议保留。该修补解决 stale staffing gap 与 duplicate hire 死循环。

### P03. provider audit 未记录 `effective_reasoning_effort`

现象：最终 assertion 报 `checker_primary` runtime audit reasoning 偏离期望。TOML 与 runtime config 是 `xhigh`，但 harness 旧逻辑推断成 `high`。

根因：

- provider audit payload 未记录 `effective_reasoning_effort`。
- 部分 checker terminal payload 缺少顶层 `assumptions`。
- harness fallback 只能按角色硬编码推断。

修补：

- 修改 `backend/app/core/runtime.py`，provider audit payload 增加 `effective_reasoning_effort`。
- 修改 `backend/tests/live/_autopilot_live_harness.py`，优先从 provider audit 读取 reasoning。
- 旧审计事件缺失时，从 runtime provider binding 推断；最后才回退旧默认值。
- 增加回归覆盖 provider audit reasoning 与 legacy fallback。

验证：

- `tests/test_live_library_management_runner.py`：`54 passed`
- `tests/test_runtime_provider_center.py`：`14 passed`

状态：建议保留。该修补提高审计证据准确性，不改变实际 runtime selection。

### P04. PRD profile 不能沿用极简源码单类 follow-up 断言

现象：修复 reasoning 后，最终 assertion 继续失败，报缺少 `BR-GOV-001`、`BR-QA-PLAN-001`、`BR-QA-FINAL-001`、`BR-DOC-001`、`BR-CHECK-001` follow-up materialization。

根因：

- 这些 follow-up 已物化并完成，但不是 `source_code_delivery`。
- `library_management_prd` 复用了 minimalist profile 的 materialization 检查。
- minimalist profile 只允许源码交付 follow-up。
- backlog `implementation_handoff` 存在于 `written_artifacts[*].content_json`，不是 terminal payload 顶层字段。

修补：

- 修改 `backend/tests/live/_scenario_profiles.py`。
- `_find_backlog_handoff()` 支持从 `written_artifacts[*].content_json` 读取 handoff。
- materialization 检查增加可选 `required_output_schema_ref`。
- `minimalist_book_tracker` 仍要求 `source_code_delivery`。
- `library_management_prd` 允许 PRD 合理包含 governance、QA、doc、check 等非源码 follow-up。

验证：

- RED 测试先失败，修补后通过。
- 已完成 DB 重放 assertion 通过。
- materialized ticket 映射覆盖 `BR-GOV-001` 到 `BR-CHECK-001`。

状态：建议保留。PRD 级集成测试不应继承极简源码单类交付约束。

### P05. 产物启动链路仍是 skeleton

现象：正式启动 `web` 后页面只有：

```text
Library Management System
BR-SET-001 frontend startup skeleton is ready for downstream feature tickets.
```

根因：

- `src/web/src/App.vue` 本身就是 BR-SET-001 skeleton。
- 完整业务前端代码生成在 `src/App.vue`、`src/main.ts`、`src/router`、`src/views` 等上层目录，以及 `src/web/src/features` 下。
- 这些业务页面没有接入正式 `src/web/src/main.ts`。

会话内临时处理：

- 创建临时 Vite preview 壳，将已生成业务页面挂出，供人工审核。
- 这不是正式产品修补，不应计入原产物完成。

状态：未正式修复。需要把业务前端入口、路由、权限、API client 统一接入 `web` 正式启动链路。

### P06. 正式 seed 未接入 `npm run db:seed`

现象：按 README 执行 `npm run db:migrate` 和 `npm run db:seed` 后，SQLite 只有 `schema_migrations`，没有书籍、用户、读者等业务表和数据。

根因：

- 正式图书馆业务 schema/seed 存在于：
  - `src/api/db/migrations/002_library_domain_schema.sql`
  - `src/api/db/seeds/002_library_domain_seed.sql`
- 当前脚本只执行：
  - `src/data/sqlite/migrations/0001_init.sql`
  - `src/data/sqlite/seeds/0001_seed.sql`
- `0001_seed.sql` 只是 BR-SET-001 placeholder，只插入 `schema_migrations`。

会话内临时处理：

- 手动将 `002_library_domain_schema.sql` 和 `002_library_domain_seed.sql` 执行到当前 `library.db`。
- 验证后数据为：`book_records=6`、`book_copies=8`、`users=4`、`reader_profiles=3`、`loans=3`、`reservations=3`、`fines=3`、`inventory_sheets=2`。

状态：未正式修复。需要把 domain migration/seed 接入正式 migrate/seed runner。

### P07. 正式后端仍是 health skeleton

现象：4000 后端只实现 `/health`，访问 `/catalog` 返回 404。即使手动导入业务 seed，前端也无法通过正式 API 读取图书。

根因：

- `src/api/src/dev-server.js` 是 BR-SET-001 health skeleton。
- 业务后端模块、catalog module、ops module 等生成在其他目录，但未接入正式启动服务。

会话内临时处理：

- 创建临时 preview API 直接读取 SQLite，为人工审核提供 `/catalog`、`/catalog/books/:id`、`/reader/workbench`、`/api/admin/users`、`/api/admin/roles`、`/api/admin/permissions` 等预览接口。
- 修复临时 CORS 和 Vite `/api` 代理。

状态：未正式修复。需要将业务 API 路由、DB 访问、认证/RBAC、错误 envelope 接入正式 backend runtime。

### P08. README 只说明 skeleton，不说明完整系统启动

现象：`src/README.md` 标题和内容均为 `Startup Skeleton (BR-SET-001)`，说明 `api`、`web`、`data/sqlite` 是 skeleton/placeholder。

根因：README 是 BR-SET-001 产物，没有随着后续业务实施更新。

影响：

- 没有说明完整系统如何安装依赖。
- 没有说明业务 schema/seed 如何执行。
- 没有说明真实后端 API 如何启动。
- 没有说明 seed 账号、API overview、测试命令、已知限制。

状态：未正式修复。需要由 `BR-DOC-001` 更新 README 和 checker evidence pack。

### P09. Admin 页面无法进入

现象：临时预览中 admin 页面显示无权限或接口失败。

根因：

- Admin 页面从 `localStorage.permissions` 读取 `admin.users.manage` / `admin.roles.manage`。
- 临时 preview 壳没有注入权限。
- Admin 页面请求同源 `/api/admin/*`，临时 Vite 原先没有代理，preview API 也未实现对应接口。

会话内临时处理：

- 在 preview 壳写入 `localStorage.permissions`。
- Vite 临时配置代理 `/api -> http://127.0.0.1:4000`。
- preview API 增加 admin users、roles、permissions 的读写模拟接口。

状态：仅为人工审核临时修补，不是正式产物修复。

### P10. Runtime 把 `FAIL_CLOSED` 包装成 closeout 并标记 workflow 完成

现象：

- `BR-CHECK-001` 的 `delivery-check-report.json` 明确是 `FAIL` / `FAIL_CLOSED`。
- 报告列出 F01-F04 blocking findings：源码可追溯缺失、实现物化缺失、启动/QA/文档缺失、scope manifest 缺失。
- 但随后 CEO/autopilot 创建 `node_ceo_delivery_closeout`。
- closeout 包自己也写明 `FAIL_CLOSED` 且 “not approved for completion”。
- maker-checker 对 closeout 包返回 `APPROVED_WITH_NOTES`。
- workflow projection 最终变为 `COMPLETED / closeout`。

根因：

- `workflow_controller.py` 中，只要 followup plans 存在且没有 active ticket/staffing/meeting 阻塞，就可能进入 `READY_FOR_FANOUT / CREATE_TICKET`，没有识别“最新 checker 明确失败”这一终止/返工状态。
- `ceo_proposer.py::_build_autopilot_closeout_batch()` 只检查没有 active ticket、nodes 完成、followup plans 都已有、没有已有 closeout、能找到 parent ticket；没有检查 parent checker 报告是否 PASS、是否存在 blocking findings。
- `workflow_completion.py::resolve_workflow_closeout_completion()` 只要存在已完成的 `delivery_closeout_package`，且没有 active tickets/open approval/open incident，就认为 closeout complete；不读取 closeout 包语义。
- `ticket_handlers.py` 对 CEO autopilot internal maker-checker review 有 rework cap convergence：达到阈值后可把结果改成 `APPROVED_WITH_NOTES` 并将 blocking findings 降级。这不应适用于最终硬验收 closeout。

状态：未修复。该问题是本轮最重要的 runtime 缺陷。

建议修补：

- 如果最新 `delivery-check-report.status == FAIL` 或存在 blocking findings，不允许创建 `delivery_closeout_package`。
- closeout 包包含 `FAIL_CLOSED`、`not approved` 或 open blocking findings 时，不允许 workflow 进入 `COMPLETED / closeout`。
- final closeout 的 maker-checker 不应应用 autopilot rework cap convergence。
- controller 需要新增 `CHECK_FAILED` / `REWORK_REQUIRED` 状态，而不是继续 `READY_FOR_FANOUT / CREATE_TICKET`。
- `_build_autopilot_closeout_batch()` 必须要求最新 checker 报告显式 PASS。

## 本轮代码修改汇总

已做并建议保留：

- `backend/app/core/workflow_controller.py`
  - 修复 `cto_primary` backlog follow-up schema 与派单约束。
- `backend/app/core/runtime.py`
  - provider audit 增加 `effective_reasoning_effort`。
- `backend/tests/live/_autopilot_live_harness.py`
  - runtime reasoning audit 读取和 fallback 修正。
- `backend/tests/live/_scenario_profiles.py`
  - PRD profile 的 handoff 与 materialization 检查修正。
- 相关测试文件
  - 增加 CTO staffing、provider reasoning、PRD materialization 的回归覆盖。

仅用于人工预览，不应视为正式产物修补：

- 手动执行业务 SQL 到 `library.db`。
- 创建临时 Vite preview 壳。
- 创建临时 Python preview API。
- 临时补 `/catalog`、`/reader/workbench`、`/api/admin/*` 预览接口。
- 临时写入前端 `localStorage.permissions`。

## 当前风险

- workflow 完成状态不可信：`COMPLETED / closeout` 可能只是 closeout 包完成，不代表交付通过。
- checker failure 未阻断 closeout：`FAIL_CLOSED` 被 runtime 继续推进。
- 实施物化不足：后端、数据库、前端各自生成了部分模块，但正式启动链路没有装配。
- 文档滞后：README 仍是 setup skeleton，不是完整系统启动说明。
- QA 证据不足：缺少真实启动日志、health/migration/seed 输出、API/并发/前端权限测试证据。
- assertion profile 修补后能让 DB 重放通过，但这验证的是 runtime 物化结构，不代表产品功能完成。

## 后续建议

优先级从高到低：

1. 修 runtime closeout gate：禁止 `FAIL_CLOSED` 进入 completed closeout。
2. 给 `delivery_check_report` 和 `delivery_closeout_package` 增加强语义校验：必须显式 PASS 且无 blocking findings。
3. 禁止 final closeout maker-checker 套用 autopilot rework cap convergence。
4. 将正式业务 schema/seed 接入 migrate/seed runner。
5. 将业务后端路由接入正式 API 服务。
6. 将业务前端入口接入正式 `web/src/main.ts`。
7. 更新 README：完整启动、seed 账号、API overview、测试命令、fallback 模式、已知限制。
8. 重新运行 `BR-QA-FINAL-001` 和 `BR-CHECK-001`，要求真实启动和测试证据齐全后才允许 closeout。
