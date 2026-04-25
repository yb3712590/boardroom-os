# intergration-test-010-20260425

## 最终状态

- 结论：第 10 轮 full live 长测已手动停止，未通过。
- 停止动作：已停止 full live 进程 PID `44672`。
- 主入口：`py -3 -m tests.live.run_configured --config data/live-tests/library_management_autopilot_live_010.toml --clean --max-ticks 180 --timeout-sec 7200`。
- 主配置：`backend/data/live-tests/library_management_autopilot_live_010.toml`。
- scenario root：`backend/data/scenarios/library_management_autopilot_live_010`。
- runner 输出：`backend/.tmp/integration-010-full-live.log`，长度为 0；主要运行证据在 scenario root 和 DB 中。

## 配置摘要

- Provider base_url：保持模板/既有 Truerealbill OpenAI-compatible endpoint：`http://codex.truerealbill.com:11234/v1`。
- API key：已写入本地 live 配置；报告仅记录 masked key `sk-***eb03`。
- 默认模型：未明确角色使用 `gpt-5.4@high`。
- CEO：`gpt-5.5@high`。
- 架构师与 CTO：`gpt-5.5@xhigh`。
- 编码实现类人员：frontend/backend/database/platform SRE 使用 `gpt-5.3-codex-spark@high`。
- checker / UI designer：`gpt-5.4@high`。

## 本轮修补

- 修补 `tests.live._config`：支持 `[provider].role_bindings`，并把 role bindings 引用的 `gpt-5.5`、`gpt-5.4`、`gpt-5.3-codex-spark` 补入 `provider_model_entries`。
- 修补 `tests.scenario._config`：同样支持 role bindings 引用的多模型 entry；这是早期误跑 `tests/scenario` 时为配置验证做的兼容修补。
- 新增定向测试：`tests/test_live_configured_runner.py` 覆盖 live 多模型 role binding payload；`tests/test_scenario_config.py` 覆盖 scenario 多模型 entry。
- 验证结果：`py -3 -m pytest tests/test_live_configured_runner.py -q` 通过，`6 passed in 0.38s`；`py -3 -m pytest tests/test_scenario_config.py -q` 在仓库临时目录下通过，`5 passed in 0.04s`。

## 误跑与纠偏

- 误跑：先前误把 `scenario-tests.template.toml` 当作 `tests/scenario` stage 测试入口，启动过 Stage 01。
- Stage 01 误跑结果：`1 failed in 5259.27s (1:27:39)`，最终停在 `project_init`，同样暴露 `WRITE_SET_VIOLATION`。
- 纠偏：用户指出目标是整个 live 长测后，已切换到 `tests.live.run_configured`，并创建 `backend/data/live-tests/library_management_autopilot_live_010.toml`。

## full live 运行证据

- full live PID：`44672`，已停止。
- workflow：`wf_d5df1a0d67b3`。
- 停止时 workflow 状态：`EXECUTING`。
- 停止时 current stage：`project_init`。
- 停止时 ticket 状态分布：`EXECUTING=1`、`FAILED=39`、`PENDING=3`。
- 失败类型分布：`WRITE_SET_VIOLATION=38`、`DEPENDENCY_GATE_UNHEALTHY=1`。
- incident 分布：`REPEATED_FAILURE_ESCALATION` recovering `34`，`GRAPH_HEALTH_CRITICAL` closed `6`。
- employees：`checker` 1 名、`frontend_engineer` 1 名，均 board approved。
- provider 证据：monitor report 多次记录 `prov_openai_compat_truerealbill` attempt `1` phase `completed`，elapsed 约 12–30 秒；因此主阻塞不是 provider 完全不可用。

## 根因分析

- 直接失败：governance tickets 提交 structured result 后触发 `WRITE_SET_VIOLATION`。
- 失败消息：`Structured result attempted to write outside the allowed write set.`
- 自动 `.audit.md` 来源：`a9044c50 fix: improve integration audit readability outputs`（2026-04-13 18:16:22 +0800）引入 `_build_governance_audit_written_artifact()`，会为 governance document 主 JSON 自动派生同路径 `.audit.md`。
- 精确 JSON write set 来源：`ef233e9c feat: 拆分架构简报初始化票据`（2026-04-24 17:12:06 +0800）引入 `reports/governance/<ticket_id>/architecture_brief_segment.json` 精确路径，并设置为 project-init architecture segment tickets 的 `allowed_write_set`。
- 主路径接入：`b7767e31 Add CEO-driven decomposition planning`（2026-04-25 03:03:26 +0800）让 full live 在 project-init 阶段实际走这套 segment + aggregator governance tickets。
- 冲突机制：主 JSON 路径被允许，但自动派生的 `architecture_brief_segment.audit.md` 不匹配精确 JSON 路径，于是所有相关 governance tickets 反复失败并触发 recovery/escalation。

## 为什么“通用大请求拆分”没有覆盖旧路径

- project-init 当前仍无条件调用 `insert_project_init_architecture_tickets()`，它继续调用 `build_project_init_architecture_brief_ticket_specs()` 并生成 project-init architecture segment + aggregator tickets。
- 通用 decomposition recovery 当前是 failure recovery 入口，只在 `REQUEST_TOO_LARGE`、`CONTEXT_TOO_LARGE`、`OUTPUT_TOO_LARGE`、`NEEDS_DECOMPOSITION` 这些 failure kind 出现时触发。
- 本轮失败类型是 `WRITE_SET_VIOLATION`，不属于 decomposition recovery failure kinds。
- 因此旧 project-init 架构简报拆分没有被替换或禁用，仍在 workflow 初始化路径中先于任何大请求探测运行。

## 建议后续修补

1. 先修 write-set 与自动 audit 的契约冲突：允许 governance audit markdown 作为主 JSON 的派生审计工件通过校验，或在生成 governance ticket 时把同目录 `*.audit.md` 纳入 allowed write set。
2. 再处理 project-init 旧拆分与通用大请求拆分的职责重叠：如果通用机制应覆盖旧机制，需要从 `command_handlers.py` / `project_init_architecture_tickets.py` 移除或改造无条件预置插票逻辑。
3. 修补后重启第 10 轮 full live，而不是续用当前 DB；当前 DB 已积累大量 `WRITE_SET_VIOLATION` 与 recovery incident，建议 clean run。
4. Codex app 自动化：当前会话未暴露 `automation_update` 工具，未能创建 app 级 1800s wakeup；不能把本地 PowerShell 循环冒充为 app 自动化。

## 附：原始流水
# intergration-test-010-20260425

## 初始化

- 配置文件：`backend/data/scenario-tests/library-management-010.toml`
- 模板来源：`backend/scenario-tests.template.toml`
- Provider base_url：保持模板不变。
- API key：`sk-***eb03`（日志不记录明文）。
- 角色路由：CEO `gpt-5.5@high`；架构师/CTO `gpt-5.5@xhigh`；编码实现类人员 `gpt-5.3-codex-spark@high`；其他明确绑定角色 `gpt-5.4@high`。

## 执行记录

### 卡点：pytest 默认临时目录无权限

- 命令：`py -3 -m pytest tests/test_scenario_config.py -q`
- 现象：pytest setup 阶段访问 `C:\Users\yb371\AppData\Local\Temp\pytest-of-yb371` 触发 `PermissionError: [WinError 5] 拒绝访问`。
- 修补动作：不改业务代码，后续测试命令统一设置 `TMP` / `TEMP` / `PYTEST_DEBUG_TEMPROOT` 到 `backend/.tmp/pytest-temp`。
### 卡点：TOML 文件 BOM 导致解析失败

- 命令：加载 `data/scenario-tests/library-management-010.toml` 并生成 runtime provider payload。
- 现象：`tomllib.TOMLDecodeError: Invalid statement (at line 1, column 1)`。
- 根因：PowerShell `Set-Content -Encoding UTF8` 写入 BOM，`tomllib` 不能按当前方式解析。
- 修补动作：将 `library-management-010.toml` 重写为 UTF-8 no BOM，不改变配置语义。
### 配置与路由验证

- 命令：加载 `data/scenario-tests/library-management-010.toml` 并打印 runtime provider payload 摘要。
- 结果：配置加载成功；`base_url` 保持 `http://codex.truerealbill.com:11234/v1`；API key masked 为 `sk-***eb03`。
- Provider model entries：`gpt-5.4`、`gpt-5.5`、`gpt-5.3-codex-spark` 均已写入 payload。
- 角色路由确认：CEO `gpt-5.5@high`；架构师/CTO `gpt-5.5@xhigh`；frontend/backend/database/platform SRE `gpt-5.3-codex-spark@high`；checker/UI designer `gpt-5.4@high`。
- 定向回归：`py -3 -m pytest tests/test_scenario_config.py -q` 在仓库临时目录下通过，结果 `5 passed in 0.04s`。

### 启动集成测试

- 命令：`py -3 -m pytest tests/scenario -q`（已设置 `BOARDROOM_OS_SCENARIO_TEST_ENABLE=1` 和第 10 轮配置路径）。
- 进程 PID：`40544`
- 输出日志：`backend/.tmp/integration-010-pytest.log`

### 卡点：prepared seed 目录缺失

- 命令：`py -3 -m pytest tests/scenario -q`
- 现象：6 个 stage 快速失败，均为 `FileNotFoundError: Seed root does not exist`；路径被解析到 `backend/data/scenario-tests/data/scenario-tests/...`，且当前仓库没有已落盘的 `library-management/seeds`。
- 依据：`backend/docs/library-management-scenario-next-session-prompt.md` 记录 Stage 02 seed 仍不存在，需要先跑 Stage 01 并 freeze。
- 修补动作：不改 runner；改为按链路先运行 Stage 01，待 Stage 01 checkpoint 成功后用 `_seed_builder.py capture-stage` 冻结 Stage 02 seed，再继续后续阶段。
### 配置修补：seed path 相对目录

- 问题：第 10 轮配置位于 `backend/data/scenario-tests`，模板 seed path 仍以 `data/scenario-tests/...` 开头，loader 会按配置目录再次拼接。
- 修补动作：将本轮配置中的 seed path 改为 `library-management/seeds/...`，使其解析到 `backend/data/scenario-tests/library-management/seeds/...`。

### 启动 Stage 01

- 命令：`py -3 -m pytest tests/scenario/test_library_management_stage_01_requirement_to_architecture.py -q`。
- 进程 PID：`40984`
- 输出日志：`backend/.tmp/integration-010-stage01.log`

### 修补：创建 Stage 01 bootstrap seed

- 问题：Stage 01 `requires_prepared_state = false`，但 runner 仍要求 seed root 目录存在以复制并初始化 layout。
- 修补动作：创建空目录 `backend/data/scenario-tests/library-management/seeds/stage_01_requirement_to_architecture/scenario`，让 Stage 01 能从 bootstrap 空场景启动。

### 重启 Stage 01

- 命令：`py -3 -m pytest tests/scenario/test_library_management_stage_01_requirement_to_architecture.py -q`。
- 进程 PID：`42068`
- 输出日志：`backend/.tmp/integration-010-stage01.log`


### 稳态与 1800s 监控

- 稳态判断：Stage 01 进程已运行超过 60s，未出现快速失败输出，进入 provider/runtime 长耗时推进态。
- 自动化工具：当前会话未暴露 automation update MCP/tool，已按计划记录降级。
- 降级方案：启动本地 PowerShell 监控进程，每 1800s 检查 Stage 01 PID、pytest 输出尾部和 runtime events 尾部，并追加本日志。
- 监控 PID：`15184`
- 下一次唤醒时间：`2026-04-25 04:31:06 +08:00`
- 监控脚本：`backend/.tmp/integration-010-monitor.ps1`

### 即时状态快照

- Stage 01 测试进程：运行中。
- 1800s 监控进程：运行中。
- pytest 输出：当前为空，未见快速失败栈。
- runtime events：已创建 `runtime/events.log`，当前长度为 0，后续由监控唤醒记录尾部。
### 进度检查：Stage 01 结束但未通过

- 检查时间：2026-04-25 05:30+08:00 后。
- Stage 01 PID：`42068`，状态：已退出。
- pytest 结果：`1 failed in 5259.27s (1:27:39)`。
- 失败点：`Stage stage_01_requirement_to_architecture did not reach checkpoint requirement_to_architecture within 180 ticks`。
- 最终 workflow：`wf_950ca77c687c`，状态 `EXECUTING`，current stage `project_init`，checkpoint reason `expected_stage_mismatch`。
- 最终快照：ticket count `122`，全部为 `FAILED`；open incidents `8`。
- 根因证据：SQLite `ticket_projection.last_failure_kind = WRITE_SET_VIOLATION`，`last_failure_message = Structured result attempted to write outside the allowed write set.`；事件 payload 显示 governance ticket 允许写 `reports/governance/<ticket_id>/architecture_brief_segment.json`，但 runtime 会为 governance document 自动追加同路径派生的 `.audit.md`。
- 初步判断：不是 provider timeout；是自动生成 governance audit markdown 与精确 JSON allowed write set 不兼容，导致每次结构化结果提交后被判越界并循环重试。
- 建议最小修补：让 governance audit markdown 在 write-set 校验中被视为主 JSON 工件的派生审计工件，或在创建 governance tickets 时把同目录 `*.audit.md` 纳入 allowed write set；随后重跑 Stage 01。
### 纠偏：切换到 full live 长测入口

- 用户纠正：本轮目标是整个 live 长测，不是 `tests/scenario` 的 Stage 01 场景测试。
- 原 Stage 01 结果保留为误跑诊断记录，不再作为本轮主线推进依据。
- `.audit.md` 来源：`ticket-result-submit` 中 `_build_governance_audit_written_artifact()` 会对 governance document schema 自动生成同路径派生的人类可读 audit markdown，并追加到 `effective_written_artifacts`；随后 write-set 校验会检查这个派生文件。
- live loader 修补：`tests.live._config` 现在支持 `[provider].role_bindings`，并会把 role bindings 引用的多模型补入 `provider_model_entries`。
- 定向验证：`py -3 -m pytest tests/test_live_configured_runner.py -q` 通过，结果 `6 passed in 0.38s`。
- 新 live 配置：`backend/data/live-tests/library_management_autopilot_live_010.toml`。

### 启动 full live 长测

- 命令：`py -3 -m tests.live.run_configured --config data/live-tests/library_management_autopilot_live_010.toml --clean --max-ticks 180 --timeout-sec 7200`。
- 进程 PID：`44672`
- 输出日志：`backend/.tmp/integration-010-full-live.log`

### full live 即时状态

- full live PID：`44672`，启动 30s 后仍在运行。
- 输出日志：`backend/.tmp/integration-010-full-live.log`，当前未见快速失败输出。
- 说明：Codex app 自动化工具当前会话仍未暴露，因此尚不能创建 app 级 1800s wakeup；后续需在工具可用时补设，或由用户在 Codex app UI 中创建 thread wakeup。
### full live 进度检查

- 检查时间：2026-04-25 08:55+08:00。
- full live PID：`44672`，状态：运行中。
- runner stdout/stderr：`backend/.tmp/integration-010-full-live.log` 当前长度为 0；runner 主要进展写入 scenario 目录。
- scenario root：`backend/data/scenarios/library_management_autopilot_live_010`。
- workflow：`wf_d5df1a0d67b3`，状态 `EXECUTING`，current stage `project_init`。
- ticket 总数：`25`；状态分布：`EXECUTING=1`、`FAILED=21`、`PENDING=3`。
- employees：checker 1 名、frontend engineer 1 名。
- incidents：`REPEATED_FAILURE_ESCALATION` recovering `16`，`GRAPH_HEALTH_CRITICAL` closed `2`。
- monitor report 显示 provider attempt phase `completed`，最近有活跃 ticket 变化；但失败主因仍为 `WRITE_SET_VIOLATION`。
- 当前阻塞性质：full live 没有崩溃，但 governance tickets 因自动派生 `.audit.md` 不在精确 allowed write set 中反复失败，继续空跑会持续消耗 ticks。
- 建议下一步最小修补：允许 governance audit markdown 作为主 JSON 的派生审计工件通过 write-set 校验，然后重启/续跑 full live。
### 追溯：`.audit.md` 自动派生的引入时间

- 引入提交：`a9044c50 fix: improve integration audit readability outputs`，提交时间 `2026-04-13 18:16:22 +0800`。
- 引入位置：`backend/app/core/ticket_handlers.py` 的 `_render_governance_audit_markdown()`、`_build_governance_audit_written_artifact()`，以及 ticket submit 中追加 `governance_audit_artifact` 到 `effective_written_artifacts`。
- write-set 校验本身更早已存在：`b4cd93b7`（2026-03-30）引入 `WRITE_SET_VIOLATION` 相关校验；`a9044c50` 把校验对象从原始 `payload.written_artifacts` 扩展到包含自动 audit 工件的 `effective_written_artifacts`。
- 为什么以前没遇到：新增测试 `test_governance_document_writes_human_readable_audit_markdown` 使用的 allowed write set 是 `10-project/docs/*` 这种目录通配，可以覆盖派生 `.audit.md`；而本轮 live 的 CEO governance tickets 使用精确路径 `reports/governance/<ticket_id>/architecture_brief_segment.json`，不能匹配同目录派生的 `.audit.md`，因此首次集中暴露。
### 追溯：精确 governance JSON allowed write set 的引入时间

- 精确路径 helper 引入提交：`ef233e9c feat: 拆分架构简报初始化票据`，提交时间 `2026-04-24 17:12:06 +0800`。
- 引入位置：`backend/app/core/ceo_execution_presets.py` 的 `build_project_init_architecture_segment_artifact_path()` 返回 `reports/governance/<ticket_id>/architecture_brief_segment.json`。
- 同一提交还在项目初始化架构分段票据里设置 `allowed_write_set=[build_project_init_architecture_segment_artifact_path(ticket_id)]`，即只允许精确 JSON 文件。
- 后续使用路径：`b7767e31 Add CEO-driven decomposition planning`（2026-04-25 03:03:26 +0800）把这套架构分段/聚合计划接入 CEO-driven decomposition planning，使 full live 实际走到这些精确 write set 的 governance tickets。
- 与 `.audit.md` 冲突的时间线：`.audit.md` 自动派生在 `a9044c50`（2026-04-13）已存在；精确 JSON write set 在 `ef233e9c`（2026-04-24）引入并在 `b7767e31` 后成为本轮 live 主路径，因此这轮才暴露冲突。
### 追溯：为什么旧 project-init 架构简报拆分仍在影响 live

- 当前 project-init 命令路径仍无条件调用 `insert_project_init_architecture_tickets()`：`backend/app/core/command_handlers.py` 在创建 workflow 和 board brief 后直接插入 project-init architecture tickets。
- `insert_project_init_architecture_tickets()` 调用 `build_project_init_architecture_brief_ticket_specs()`，后者在当前代码里继续调用 `build_ceo_project_init_architecture_decomposition_plan()` 并生成 segment + aggregator tickets。
- 所谓“通用大请求主动探测拆分”当前实际入口是 failure recovery：`ticket_handlers.py` 只在 ticket fail 的 `failure_kind` 属于 `REQUEST_TOO_LARGE` / `CONTEXT_TOO_LARGE` / `OUTPUT_TOO_LARGE` / `NEEDS_DECOMPOSITION` 时触发 `_open_decomposition_recovery_incident()`。
- 本轮失败是 `WRITE_SET_VIOLATION`，不属于 decomposition recovery failure kinds，所以不会切到通用大请求拆分恢复路径。
- 因此旧的 project-init 架构简报拆分没有被通用机制替换/禁用；它仍作为 workflow 初始化的硬编码预置路径先于任何大请求探测运行，并且产生精确 JSON write set。
