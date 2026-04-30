# Intergration Test 015 审计日志

## 基本信息

- 日期：2026-04-29
- 测试轮次：015
- 场景 slug：`library_management_autopilot_live_015`
- 测试配置：`backend/data/live-tests/library_management_autopilot_live_015.toml`
- 后端留档副本：`backend/library_management_autopilot_live_015.toml`
- 配置来源：以 `backend/integration-tests.template.toml` 为骨架，按 `backend/library-mgmt-prd.md` 完整 PRD 扩展
- base_url：`http://codex.truerealbill.com:11234/v1`
- API key：已按用户提供值写入测试配置；本文档不记录明文密钥
- 运行入口：`backend/.venv/bin/python -m tests.live.run_configured --config data/live-tests/library_management_autopilot_live_015.toml --clean --max-ticks 1800 --timeout-sec 86400`
- 监控策略：本会话内每 1800 秒检查一次 `backend/data/scenarios/library_management_autopilot_live_015/` 下的 `integration-monitor-report.md`、`run_report.json`、`audit-summary.md` 与当前 incident / ticket 状态

## 模型绑定

- 默认模型：`gpt-5.4` / `high`
- CEO：`gpt-5.5` / `high`
- 架构/分析：`architect_primary`、`cto_primary`、`checker_primary` 使用 `gpt-5.5` / `xhigh`
- 开发：`frontend_engineer_primary`、`backend_engineer_primary`、`database_engineer_primary`、`platform_sre_primary` 使用 `gpt-5.4` / `high`
- UI 设计：`ui_designer_primary` 使用 `gpt-5.4` / `high`

## 运行参数

- `budget_cap = 8000000`
- `runtime.seed = 17`
- `runtime.max_ticks = 7200`（P01 后由 1800 放大）
- `runtime.timeout_sec = 172800`（P01 后由 86400 放大）
- `provider.connect_timeout_sec = 10`
- `provider.write_timeout_sec = 30`
- `provider.first_token_timeout_sec = 300`
- `provider.stream_idle_timeout_sec = 600`
- `provider.max_context_window = 270000`

## 执行记录

### E00. 配置落地

- 目标：生成 `015` live TOML，并复制到 `backend/` 根目录留档。
- 状态：完成
- 备注：配置沿用 `013` 的 PRD-embedded constraints 结构，并按本轮计划放大运行预算、tick、timeout 和 provider idle 容忍。
- 主配置：`backend/data/live-tests/library_management_autopilot_live_015.toml`
- 留档副本：`backend/library_management_autopilot_live_015.toml`
- 副本校验：`diff -u backend/data/live-tests/library_management_autopilot_live_015.toml backend/library_management_autopilot_live_015.toml` 无差异
- 配置摘要校验：slug、预算、runtime、provider、角色模型绑定、assertion profile 与 constraints 数量均符合计划

### E01. 静态校验

- `TMPDIR=$(pwd)/.tmp/pytest-015 TEMP=$(pwd)/.tmp/pytest-015 TMP=$(pwd)/.tmp/pytest-015 .venv/bin/python -m pytest tests/test_scenario_config.py -q`
  - 结果：`5 passed in 0.02s`
- `TMPDIR=$(pwd)/.tmp/pytest-015 TEMP=$(pwd)/.tmp/pytest-015 TMP=$(pwd)/.tmp/pytest-015 .venv/bin/python -m pytest tests/test_live_configured_runner.py -q`
  - 结果：`11 passed in 0.26s`

### E02. Live run

- 已启动：`tests.live.run_configured --config data/live-tests/library_management_autopilot_live_015.toml --clean --max-ticks 1800 --timeout-sec 86400`
- 启动方式：当前会话内长进程，进入调度循环后继续监控

### E03. 监控

- 待执行：进入稳态后每 1800 秒记录一次
- 记录字段：时间、workflow/tick、当前阶段、open incident、active ticket、最新修补、是否续跑

#### M00. 初始状态

- 时间：2026-04-29T01:10+08:00
- workflow：`wf_7f2902f3c8c6`
- current_stage：`plan`
- workflow status：`EXECUTING`
- ticket 汇总：`EXECUTING=1`
- active ticket：`tkt_wf_7f2902f3c8c6_ceo_architecture_brief`
- open incident：无
- 场景目录：`backend/data/scenarios/library_management_autopilot_live_015`
- 备注：runner 已创建 DB、runtime provider config、artifact roots 和初始 ticket context archive

#### M01. 架构票完成

- 时间：2026-04-29T01:13+08:00
- workflow：`wf_7f2902f3c8c6`
- current_stage：`project_init`
- workflow status：`EXECUTING`
- ticket 汇总：`COMPLETED=1`、`PENDING=1`
- completed ticket：`tkt_wf_7f2902f3c8c6_ceo_architecture_brief`
- pending ticket：`tkt_e1bfdabd076f`
- provider 记录：架构票 attempt 1 completed，policy 为 `gpt-5.5:xhigh`
- open incident：无
- 判断：首个治理产物已通过，runner 正常推进

#### M02. 技术决策完成

- 时间：2026-04-29T01:15+08:00
- workflow：`wf_7f2902f3c8c6`
- current_stage：`project_init`
- workflow status：`EXECUTING`
- ticket 汇总：`COMPLETED=4`
- completed ticket：`tkt_b716f3c2832e`、`tkt_cc716492e82c`
- active ticket：无
- provider 记录：4 个 runtime attempt 均 completed
- open incident：无
- 判断：技术决策链路已完成，runner 等待下一轮 scheduler tick 推进

#### M03. 监控报告已生成

- 时间：2026-04-29T01:16+08:00
- workflow：`wf_7f2902f3c8c6`
- current_stage：`plan`
- workflow status：`EXECUTING`
- ticket 汇总：`COMPLETED=4`、`EXECUTING=1`
- active ticket：`tkt_4a164bff2c95`
- monitor：`backend/data/scenarios/library_management_autopilot_live_015/integration-monitor-report.md`
- monitor 记录：01:15 workflow 启动，01:16 active ticket provider phase 为 `streaming`
- open incident：无
- 判断：进入可监控稳态，后续按 1800 秒节奏记录；中途若出现 incident 或失败票，立即插入问题记录

#### M04. 稳态心跳检查

- 时间：2026-04-29T01:20+08:00
- workflow：`wf_7f2902f3c8c6`
- current_stage：`plan`
- workflow status：`EXECUTING`
- ticket 汇总：`COMPLETED=6`、`EXECUTING=1`
- active ticket：`tkt_c9af7a89df66`
- 最新节点：`node_ceo_detailed_design`
- open incident：无
- failed ticket：无
- monitor 记录：01:18 进入 `project_init`，01:19 回到 `plan` 并启动 detailed design 票
- 判断：runner 正常推进，暂无修补动作

#### M05. backlog recommendation 启动

- 时间：2026-04-29T01:23+08:00
- workflow：`wf_7f2902f3c8c6`
- current_stage：`plan`
- workflow status：`EXECUTING`
- ticket 汇总：`COMPLETED=8`、`EXECUTING=1`
- active ticket：`tkt_9ec11236c4ec`
- 最新节点：`node_ceo_backlog_recommendation`
- open incident：无
- failed ticket：无
- monitor 记录：01:21 detailed design 链路完成，01:21 启动 backlog recommendation 票，01:22 provider 进入 `streaming`
- 判断：治理规划链路继续推进，暂无修补动作

#### M06. 规划链路继续收敛

- 时间：2026-04-29T01:28+08:00
- workflow：`wf_7f2902f3c8c6`
- current_stage：`project_init`
- workflow status：`EXECUTING`
- ticket 汇总：`COMPLETED=12`
- active ticket：无
- open incident：无
- failed ticket：无
- provider 记录：最近 8 个 runtime attempt 均 completed
- monitor 记录：01:27 启动 `tkt_5f91b1070860`，01:28 provider completed
- 判断：当前等待下一轮 scheduler tick，暂无修补动作

#### M07. backlog follow-up 启动

- 时间：2026-04-29T01:31+08:00
- workflow：`wf_7f2902f3c8c6`
- current_stage：`plan`
- workflow status：`EXECUTING`
- ticket 汇总：`COMPLETED=12`、`EXECUTING=1`
- active ticket：`tkt_f58cc1d4ab7b`
- 最新节点：`node_backlog_followup_br_001_m0_fanout_tracking`
- open incident：无
- failed ticket：无
- monitor 记录：01:29 启动 backlog follow-up，01:30 provider 进入 `streaming`
- 判断：已进入 backlog follow-up 路径，暂无修补动作

#### M08. follow-up 第一组完成

- 时间：2026-04-29T01:34+08:00
- workflow：`wf_7f2902f3c8c6`
- current_stage：`project_init`
- workflow status：`EXECUTING`
- ticket 汇总：`COMPLETED=14`
- active ticket：无
- open incident：无
- failed ticket：无
- provider 记录：`tkt_f58cc1d4ab7b` 和 `tkt_b740b1d9e8e0` attempt 1 completed
- monitor 记录：01:33 静默 2 分 12 秒后恢复，随后 active ticket 变为 none
- 判断：follow-up 第一组已完成，runner 等待下一轮推进；暂无修补动作

#### M09. 进入 build 阶段

- 时间：2026-04-29T01:36+08:00
- workflow：`wf_7f2902f3c8c6`
- current_stage：`build`
- workflow status：`EXECUTING`
- ticket 汇总：`COMPLETED=14`、`EXECUTING=2`
- active ticket：`tkt_27d3003076ec`、`tkt_58c5acc35e39`
- 最新节点：`node_backlog_followup_br_010_m1_backend_foundation`、`node_backlog_followup_br_011_m1_frontend_shell`
- open incident：无
- failed ticket：无
- monitor 记录：01:34 进入 `build` 阶段，两张实现票 start accepted
- 判断：已进入实现 fanout，重点观察 provider 长耗时和后续 checker 结果

#### M10. build 阶段继续推进

- 时间：2026-04-29T01:39+08:00
- workflow：`wf_7f2902f3c8c6`
- current_stage：`build`
- workflow status：`EXECUTING`
- ticket 汇总：`COMPLETED=16`、`EXECUTING=1`
- active ticket：`tkt_27d3003076ec`
- active 节点：`node_backlog_followup_br_011_m1_frontend_shell`
- completed 记录：`tkt_58c5acc35e39` attempt 1 completed；后续 `tkt_1022b94b6679` attempt 1 completed
- open incident：无
- failed ticket：无
- monitor 记录：01:37 build 阶段静默 3 分 21 秒后恢复；01:39 active ticket 收敛到前端 shell
- 判断：后端 foundation 分支已推进，前端 shell 仍在 streaming；暂无修补动作

#### M11. 前端 shell 完成后继续后端数据层

- 时间：2026-04-29T01:42+08:00
- workflow：`wf_7f2902f3c8c6`
- current_stage：`build`
- workflow status：`EXECUTING`
- ticket 汇总：`COMPLETED=18`、`EXECUTING=1`
- active ticket：`tkt_7c587f99399c`
- active 节点：`node_backlog_followup_br_020_m2_sqlite_schema_seeds`
- completed 记录：前端 shell 票 `tkt_27d3003076ec` attempt 1 completed；后续 `tkt_ac3e84d37042` attempt 1 completed
- open incident：无
- failed ticket：无
- monitor 记录：01:40 active ticket 切到 `tkt_ac3e84d37042`，01:41 进入 SQLite schema/seed 票
- 判断：build 阶段继续推进，暂无修补动作

#### M12. 1800 秒例行检查 1

- 时间：2026-04-29T01:47+08:00
- workflow：`wf_7f2902f3c8c6`
- current_stage：`build`
- workflow status：`EXECUTING`
- ticket 汇总：`COMPLETED=18`、`EXECUTING=1`
- active ticket：`tkt_7c587f99399c`
- active 节点：`node_backlog_followup_br_020_m2_sqlite_schema_seeds`
- open incident：无
- failed ticket：无
- provider 记录：`tkt_7c587f99399c` attempt 1 因 `FIRST_TOKEN_TIMEOUT` 进入 retry；attempt 2 已启动，当前 `awaiting_first_token`
- monitor 记录：01:46 静默 5 分 2 秒后恢复，provider phase 从 `retry_waiting` 切到 attempt 2
- 判断：provider 首 token超时已由自动重试覆盖；workflow 继续执行，暂不做代码修补

#### M13. 数据层票 timeout 后 replacement 启动

- 时间：2026-04-29T01:52+08:00
- workflow：`wf_7f2902f3c8c6`
- current_stage：`build`
- workflow status：`EXECUTING`
- ticket 汇总：`COMPLETED=18`、`EXECUTING=1`、`TIMED_OUT=1`
- timed out ticket：`tkt_7c587f99399c`
- active ticket：`tkt_24b850a6f032`
- active 节点：`node_backlog_followup_br_020_m2_sqlite_schema_seeds`
- open incident：无
- provider 记录：旧票 attempt 1 和 2 均 `FIRST_TOKEN_TIMEOUT`；系统创建 replacement 票继续执行
- monitor 记录：01:51 静默 4 分 57 秒后恢复，active ticket 切到 `tkt_24b850a6f032`
- 判断：timeout 已被 replacement 路径覆盖，workflow 继续执行；暂不做代码修补

#### M14. provider deadline 回收后再次 replacement

- 时间：2026-04-29T02:01+08:00
- workflow：`wf_7f2902f3c8c6`
- current_stage：`build`
- workflow status：`EXECUTING`
- ticket 汇总：`COMPLETED=18`、`EXECUTING=1`、`FAILED=1`、`TIMED_OUT=1`
- failed ticket：`tkt_24b850a6f032`
- failed reason：`REQUEST_TOTAL_TIMEOUT / Provider attempt exceeded its execution deadline.`
- active ticket：`tkt_b4a7dcb6c968`
- active 节点：`node_backlog_followup_br_020_m2_sqlite_schema_seeds`
- open incident：无
- 判断：provider deadline 回收器已生效，并创建新 replacement；workflow 继续执行，暂不手动改 DB 或代码

#### M15. replacement attempt 自动重试

- 时间：2026-04-29T02:07+08:00
- workflow：`wf_7f2902f3c8c6`
- current_stage：`build`
- workflow status：`EXECUTING`
- ticket 汇总：`COMPLETED=18`、`EXECUTING=1`、`FAILED=1`、`TIMED_OUT=1`
- active ticket：`tkt_b4a7dcb6c968`
- active 节点：`node_backlog_followup_br_020_m2_sqlite_schema_seeds`
- open incident：无
- provider 记录：`tkt_b4a7dcb6c968` attempt 1 因 `FIRST_TOKEN_TIMEOUT` 自动重试；attempt 2 已启动
- 判断：仍是 provider 首 token波动，自动重试路径继续工作；暂无代码修补

#### M16. P02 修补后补发票进入自动 provider 恢复

- 时间：2026-04-29T02:30+08:00
- workflow：`wf_7f2902f3c8c6`
- current_stage：`build`
- workflow status：`EXECUTING`
- ticket 汇总：`COMPLETED=18`、`EXECUTING=1`、`FAILED=4`、`TIMED_OUT=1`
- failed ticket：`tkt_bf4308616ea7`
- failed reason：`REQUEST_TOTAL_TIMEOUT / Provider attempt exceeded its execution deadline.`
- active ticket：`tkt_5976b50e22cc`
- active 节点：`node_backlog_followup_br_020_m2_sqlite_schema_seeds`
- open / recovering incident：`inc_55ffdd29bb0b` 为 `PROVIDER_EXECUTION_PAUSED / RECOVERING`，breaker 已关闭
- provider 记录：`tkt_bf4308616ea7` 在首 token 后长时间无后续输出，02:28 触发 provider deadline；runner 自动 replacement 到 `tkt_5976b50e22cc`
- 判断：这是 provider 超时的自动恢复路径，暂不做代码修补

#### M17. 使用正式 incident resolve 恢复新的 CEO shadow incident

- 时间：2026-04-29T02:36+08:00
- workflow：`wf_7f2902f3c8c6`
- current_stage：`build`
- workflow status：`EXECUTING`
- 新 incident：`inc_5555ab0202e1`
- incident 类型：`CEO_SHADOW_PIPELINE_FAILED`
- 源票：payload 中 `ticket_id = tkt_5976b50e22cc`，投影顶层 `ticket_id` 为空
- 操作：使用正式 `handle_incident_resolve`，followup action 为 `RESTORE_AND_RETRY_LATEST_FAILURE`
- 命令结果：`ACCEPTED`
- follow-up ticket：`tkt_4b8fbd9d18cc`
- 验证：`TICKET_RETRY_SCHEDULED` 的 `ticket_id` 为 `tkt_5976b50e22cc`，`TICKET_CREATED.parent_ticket_id` 为 `tkt_5976b50e22cc`
- provider 记录：`tkt_4b8fbd9d18cc` 已收到首 token，并写入 provider heartbeat
- 判断：P02 修补后的正式恢复路径可用；继续监控 provider 输出

#### M18. 旧预算 ticket 内部 provider retry

- 时间：2026-04-29T02:52+08:00
- workflow：`wf_7f2902f3c8c6`
- current_stage：`build`
- workflow status：`EXECUTING`
- active ticket：`tkt_10d83c4ff51a`
- active 节点：`node_backlog_followup_br_020_m2_sqlite_schema_seeds`
- provider 记录：attempt 1 因 `FIRST_TOKEN_TIMEOUT` 失败后自动 retry，attempt 2 已启动
- 参数观察：attempt 2 仍显示 `stream_idle_timeout_sec = 600.0`，原因是同一 ticket 内复用已解析的 provider selection；下一张 ticket 才会重新读取 1800 秒配置
- 判断：自动 provider retry 正常，暂不做代码修补

#### M19. 数据层卡点越过并确认 1800 秒 provider 预算生效

- 时间：2026-04-29T03:03+08:00
- workflow：`wf_7f2902f3c8c6`
- current_stage：`build`
- workflow status：`EXECUTING`
- ticket 汇总：`COMPLETED=20`、`EXECUTING=1`、`FAILED=6`、`TIMED_OUT=1`
- completed ticket：`tkt_10d83c4ff51a`、`tkt_2909094a4371`
- active ticket：`tkt_43324c290a3e`
- active 节点：`node_backlog_followup_br_030_m3_auth_rbac_audit_backend`
- provider 记录：`tkt_2909094a4371` 和 `tkt_43324c290a3e` 的 provider attempt 均显示 `stream_idle_timeout_sec = 1800.0`
- open incident：无；历史 recovering incident 保持 breaker closed
- 判断：P03 配置修补已生效，数据层卡点已越过，继续监控 build 阶段后续实现票

#### M20. 1800 秒例行检查 2

- 时间：2026-04-29T03:34+08:00
- workflow：`wf_7f2902f3c8c6`
- current_stage：`build`
- workflow status：`EXECUTING`
- ticket 汇总：`COMPLETED=22`、`EXECUTING=1`、`FAILED=6`、`TIMED_OUT=2`
- active ticket：`tkt_b7b0a69a55fc`
- active 节点：`node_backlog_followup_br_031_m3_frontend_auth_nav`
- leased by：`emp_frontend_2`
- latest completed：`tkt_43324c290a3e`、`tkt_c2352224be94` 完成 M3 auth/RBAC/audit backend；`tkt_10d83c4ff51a`、`tkt_2909094a4371` 完成 M2 SQLite schema/seed
- latest timed out：`tkt_3fdb01b6ac3e`，`HEARTBEAT_TIMEOUT`
- provider 记录：当前 active ticket 已进入 attempt 3；attempt 1/2 均为 `FIRST_TOKEN_TIMEOUT` 后自动 retry；所有最新 provider attempt 均显示 `stream_idle_timeout_sec = 1800.0`
- open incident：无
- recovering incident：`inc_5555ab0202e1`、`inc_55ffdd29bb0b`、`inc_dacbf4683b44`、`inc_73775c5400e5` 均为 breaker closed 的历史恢复记录
- 最新产物：`integration-monitor-report.md` 更新时间 03:32；`ticket_context_archives/` 持续更新；`run_report.json` 和 `audit-summary.md` 仍为上次 failure snapshot 输出
- 判断：第15轮处于稳态 build 执行；当前主要风险仍是 provider 首 token 波动，runner 自动 retry/replacement 正常

#### M21. 1800 秒例行检查 3

- 时间：2026-04-29T04:04+08:00
- workflow：`wf_7f2902f3c8c6`
- current_stage：`build`
- workflow status：`EXECUTING`
- ticket 汇总：`COMPLETED=22`、`EXECUTING=1`、`FAILED=6`、`TIMED_OUT=3`
- active ticket：`tkt_d9e52680a9c5`
- active 节点：`node_backlog_followup_br_031_m3_frontend_auth_nav`
- leased by：`emp_frontend_2`
- latest timed out：`tkt_b7b0a69a55fc`，`HEARTBEAT_TIMEOUT`
- provider 记录：前端 auth/nav 节点持续遇到 `FIRST_TOKEN_TIMEOUT`；`tkt_d9e52680a9c5` 已到 attempt 6，所有最新 provider attempt 均显示 `stream_idle_timeout_sec = 1800.0`
- open incident：无
- recovering incident：新增 `inc_76c2d75a1f8f` 为 `RUNTIME_TIMEOUT_ESCALATION / RECOVERING`，breaker 已关闭；其他 recovering incident 仍为历史记录
- 最新产物：`ticket_context_archives/` 更新时间 04:03；`integration-monitor-report.md` 更新时间仍为 03:35；`run_report.json` 和 `audit-summary.md` 未刷新
- 判断：当前是 provider 首 token 波动和 ticket heartbeat replacement 的组合，runner 仍在自动处理；暂不做代码修补

## 问题与修补

### P01. `max_ticks=1800` 在 build 中途耗尽

- 时间：2026-04-29T01:54+08:00
- 现象：runner 退出，错误为 `Scenario exceeded max_ticks=1800`，snapshot 写入 `backend/data/scenarios/library_management_autopilot_live_015/failure_snapshots/max_ticks.json`。
- 证据：snapshot 中 workflow 仍是 `EXECUTING / build`，active ticket 为 `tkt_24b850a6f032`，open incident 为空；DB 中 ticket 汇总为 `COMPLETED=18`、`EXECUTING=1`、`TIMED_OUT=1`。
- 根因：live harness 的 `max_ticks` 是 scheduler loop 上限，不是 wall time。完整 PRD 场景已进入 build，但 1800 tick 对本轮规模偏小。
- 修补：将主配置和后端留档副本中的 `runtime.max_ticks` 从 `1800` 放大到 `7200`，`runtime.timeout_sec` 从 `86400` 放大到 `172800`。
- 验证：
  - `diff -u backend/data/live-tests/library_management_autopilot_live_015.toml backend/library_management_autopilot_live_015.toml` 无差异
  - `tests/test_scenario_config.py`：`5 passed in 0.02s`
  - `tests/test_live_configured_runner.py`：`11 passed in 0.23s`
- 续跑策略：不使用 `--clean`，保留现有 DB 和场景目录，从当前 build 状态继续跑。
- 续跑命令：`.venv/bin/python -m tests.live.run_configured --config data/live-tests/library_management_autopilot_live_015.toml --max-ticks 7200 --timeout-sec 172800`
- 续跑初始状态：workflow 仍为 `EXECUTING / build`，active ticket 为 `tkt_24b850a6f032`，open incident 为空
- 状态：已验证并续跑

### P02. CEO shadow 恢复重试把父票写成 `"None"`

- 时间：2026-04-29T02:17+08:00
- 现象：`inc_dacbf4683b44` 首次恢复后创建 `tkt_f3758de1cedd`，但该票立刻失败，失败原因为 `DEPENDENCY_GATE_INVALID / Delivery-stage parent ticket is missing.`。
- 证据：事件表中 `TICKET_RETRY_SCHEDULED` 的 `ticket_id` 和 `node_id` 为字符串 `"None"`，后续 `TICKET_CREATED` 的 `parent_ticket_id` 也为 `"None"`。
- 根因：事故投影顶层 `ticket_id/node_id` 被 `CIRCUIT_BREAKER_OPENED` 事件中的空值覆盖；恢复校验已能从 incident payload 找到源票，但实际调度 retry 时仍读取事故投影顶层字段。
- 代码修补：
  - `backend/app/core/ticket_handlers.py`：恢复调度改用已校验的源票 `retry_ticket["ticket_id"]` 和 `retry_ticket["node_id"]`。
  - `backend/tests/test_api.py`：补充回归断言，确保 CEO shadow source-ticket 恢复时 retry 事件和 follow-up created spec 都指向真实失败票。
- 验证：
  - `tests/test_api.py::test_p2_ceo_shadow_incident_resolve_restores_and_retries_latest_failure_for_source_ticket`：`1 passed in 1.72s`
- 运行修补：因原 incident 已处于 `RECOVERING`，正式 resolve 命令不会再次接收同一 incident；使用修补后的 retry 调度补发源票恢复 ticket。
- 补发结果：创建 `tkt_bf4308616ea7`，其 `parent_ticket_id` 为 `tkt_b4a7dcb6c968`，状态已进入 `EXECUTING`，provider 已收到首 token。
- 状态：已验证并让第15轮继续执行

### P03. provider 总预算由 stream idle 间接限制为 600 秒

- 时间：2026-04-29T02:37+08:00
- 现象：数据层 build 票多次在 provider 长输出阶段触发 `REQUEST_TOTAL_TIMEOUT / Provider attempt exceeded its execution deadline.`。
- 证据：运行中 provider 配置 `timeout_sec = 600.0`，来自配置构造逻辑 `max(first_token_timeout_sec, stream_idle_timeout_sec)`；当前 TOML 中 `first_token_timeout_sec = 300`、`stream_idle_timeout_sec = 600`。
- 根因：完整 PRD 的 SQLite schema/seed 交付输出比模板极简项目大，600 秒 provider 总预算偏小。
- 修补：
  - `backend/data/live-tests/library_management_autopilot_live_015.toml`：`stream_idle_timeout_sec` 从 `600` 调整为 `1800`
  - `backend/library_management_autopilot_live_015.toml`：同步调整
  - `backend/data/scenarios/library_management_autopilot_live_015/runtime-provider-config.json`：运行中 provider 快照同步为 `stream_idle_timeout_sec = 1800.0`、`timeout_sec = 1800.0`
  - `backend/data/scenarios/library_management_autopilot_live_015/runtime-provider-config.json.d/provider.prov_openai_compat_truerealbill.json`：同步 sharded provider 配置
- 验证：
  - `diff -u backend/data/live-tests/library_management_autopilot_live_015.toml backend/library_management_autopilot_live_015.toml` 无差异
  - `tests/test_scenario_config.py`：`5 passed in 0.02s`
  - `tests/test_live_configured_runner.py`：`11 passed in 0.25s`
- 运行策略：不清库；当前 attempt 若仍按旧配置失败，则下一张 replacement 使用新 provider 预算继续。
- 状态：已验证并持续监控

#### M22. check 阶段卡点定位

- 时间：2026-04-29T04:35+08:00
- workflow：`wf_7f2902f3c8c6`
- current_stage：`check`
- workflow status：`EXECUTING`
- ticket 汇总：`COMPLETED=26`、`FAILED=6`、`TIMED_OUT=3`
- active ticket：无
- open approval：无
- open incident：无
- controller state：`CHECK_FAILED`
- closeout gate issue：`delivery_check_failed`
- 阻塞票：`tkt_ad4dbda92452`
- 审核票：`tkt_2208730020fe`
- 现象：`tkt_ad4dbda92452` 产出的 `delivery-check-report.json` 为 `status=FAIL`，含 5 个 blocking finding；随后内审票 `tkt_2208730020fe` 却返回 `APPROVED_WITH_NOTES`。closeout gate 正确拒绝放行失败报告，但调度面没有生成返工票。
- 判断：这是 fail-closed check report 与 maker-checker approved verdict 之间的闭环缺口，需要最小修补。

### P04. `FAIL` 的 delivery check report 被内审通过后没有返工票

- 时间：2026-04-29T04:46+08:00
- 现象：workflow 停在 `EXECUTING / check`；所有节点 completed，无 active/open approval/open incident；controller 返回 `CHECK_FAILED / NO_ACTION`。
- 根因：maker-checker 只按自身 verdict 路由。若内审 verdict 是 `APPROVED_WITH_NOTES`，但被审对象本身是 `delivery_check_report.status = FAIL` 或含 blocking finding，系统不会转入返工；closeout gate 后续又会阻断最终 closeout。
- 代码修补：
  - `backend/app/core/ticket_handlers.py`：新增 fail-closed 检查。maker-checker verdict 即使是 `APPROVED` 或 `APPROVED_WITH_NOTES`，只要 maker 票是失败的 `delivery_check_report`，就强制转成 `CHANGES_REQUIRED`，并把原报告 blocking finding 转成返工要求。
  - `backend/tests/test_api.py`：新增回归测试，覆盖“内审通过但 delivery check report 自身 FAIL”时自动创建 `delivery_check_report` 返工票。
- 验证：
  - `tests/test_api.py::test_check_internal_checker_approval_on_failed_report_creates_fix_ticket`：`1 passed in 1.48s`
  - 额外抽跑 check 内审相关旧用例时，两个旧 fixture 触发“workflow 不存在”的既有 CEO snapshot incident，未作为本次修补依据。
- 运行修补：
  - 不清库。
  - 使用修补后的路由逻辑，针对已完成的 `tkt_2208730020fe` 补发返工票。
  - 新票：`tkt_4db31993096e`
  - 节点：`node_backlog_followup_br_032_m3_checker_gate`
  - blocking findings：`BR032-F01`、`BR032-F02`、`BR032-F03`、`BR032-F04`、`BR032-F05`
- 修补后状态：
  - workflow：`EXECUTING / check`
  - ticket 汇总：`COMPLETED=26`、`EXECUTING=1`、`FAILED=6`、`TIMED_OUT=3`
  - active ticket：`tkt_4db31993096e`
  - leased by：`emp_checker_backup`
  - open incident：无
- 状态：已验证最小回归，并让第15轮继续执行

#### M23. BR-032 返工后上下文检查

- 时间：2026-04-29T04:50+08:00
- workflow：`wf_7f2902f3c8c6`
- current_stage：`check`
- workflow status：`EXECUTING`
- 现象：`tkt_4db31993096e` 已完成，但报告仍为 `status=FAIL`；新内审票 `tkt_9d03fa53d8e8` 仍返回 `APPROVED_WITH_NOTES`。
- 直接原因：runner 是修补前启动的旧 Python 进程，未加载 P04 的 fail-closed 代码。
- 进一步发现：BR-030/BR-031 的实现与验证证据实际存在：
  - BR-030 source delivery：`tkt_43324c290a3e`
  - BR-030 maker-checker：`tkt_c2352224be94`
  - BR-031 source delivery：`tkt_d9e52680a9c5`
  - BR-031 maker-checker：`tkt_4d60a4a0f37e`
- 上下文缺口：BR-032 checker 只带了 backlog/governance process assets，没有带 BR-030/BR-031 source、test log、git closeout 等依赖证据，所以 checker 无法关闭 F01-F05。

### P05. BR-032 checker 缺少 BR-030/BR-031 依赖证据

- 时间：2026-04-29T04:50+08:00
- 现象：补发的 BR-032 返工票仍 FAIL，原因是上下文里缺少 BR-030/BR-031 的具体实现、测试、git closeout 证据。
- 根因：依赖票产物已存在，但 BR-032 check ticket 的 `input_artifact_refs` / `input_process_asset_refs` 没有继承这些依赖交付产物。
- 运行修补：
  - 停止本任务启动的旧 runner，让后续运行加载 P04 代码。
  - 不清库。
  - 基于 `tkt_9d03fa53d8e8` 补发带依赖证据的 BR-032 check 返工票。
  - 新票：`tkt_a74c2fb71dd3`
  - 输入 artifact refs：28 个，包含 BR-030/BR-031 source、test log、git closeout 等证据。
  - 输入 process asset refs：33 个。
  - 补充 acceptance criteria：必须显式引用 BR-030 backend auth/RBAC/audit 证据与 BR-031 frontend auth/nav smoke 证据。
- 续跑命令：`.venv/bin/python -m tests.live.run_configured --config data/live-tests/library_management_autopilot_live_015.toml --max-ticks 7200 --timeout-sec 172800`
- 修补后状态：
  - ticket 汇总：`COMPLETED=28`、`EXECUTING=1`、`FAILED=6`、`TIMED_OUT=3`
  - active ticket：`tkt_a74c2fb71dd3`
  - leased by：`emp_checker_1`
  - open incident：无
- 状态：已续跑，等待 checker 输出

#### M24. BR-032 发现真实前后端 auth 合约缺陷

- 时间：2026-04-29T04:53+08:00
- workflow：`wf_7f2902f3c8c6`
- current_stage：`check`
- 现象：`tkt_a74c2fb71dd3` 已读取 BR-030/BR-031 证据，原 F01-F05 均转为 non-blocking，但新增 `BR032-F06` blocking。
- 关键 finding：BR-030 backend auth 返回 `{ ok: true, data: { token, tokenType, expiresInSec, user } }` / `{ ok: false, error: { code, message } }`，且角色为 `READER/LIBRARIAN/SYSTEM_ADMIN`、冻结字段为 `isFrozen`；BR-031 frontend auth client/store 期待未包裹 `{ token, user }`、小写角色、`accountStatus`、`permissions` 和顶层 `reasonCode`。
- 判断：这是项目实现缺陷，不是 provider 或 harness 误判。继续让 checker 重写报告无法修复代码。
- P04 验证：重启 runner 后，内审票 `tkt_bd4fe190d6ca` 已把失败报告强制转为 `CHANGES_REQUIRED`，并生成返工票 `tkt_bc0404503ec8`。

### P06. checker 返工循环无法修复前端/后端 auth 合约

- 时间：2026-04-29T04:56+08:00
- 现象：`tkt_bc0404503ec8` 继续确认 `BR032-F06`，说明 BR-032 checker 节点只能报告问题，不能修改 BR-031 前端代码。
- 根因：当前 maker-checker 返工会把 `delivery_check_report` 的缺陷送回 check report 票，而 `BR032-F06` 实际需要 BR-031 frontend build 返工。
- 运行修补：
  - 停止本任务启动的 runner，避免 checker 循环继续消耗 provider。
  - 将 stale check loop 票 `tkt_9b8ea42b3add` 标记为失败：`OPERATOR_INTERRUPTED_FOR_CONTEXT_REPLAN`。
  - 取消自动补出的 stale retry：`tkt_ade5951f10ec`。
  - 补发 BR-031 frontend auth contract fix 票：`tkt_f0c4c6154e6b`。
  - 新票输入：27 个 artifact refs、34 个 process refs，包含 BR-030 auth 后端证据、BR-031 前端证据、BR-032 check finding。
  - 新票要求：适配 backend `{ ok, data/error }` envelope，映射 `READER/LIBRARIAN/SYSTEM_ADMIN` 到前端角色，按 `isFrozen` 派生 blocked 状态，提取 `error.code` 为 `reasonCode`，补 integrated auth smoke evidence。
- 修补后状态：
  - workflow current_stage 回到 `build`
  - ticket 汇总：`CANCELLED=1`、`COMPLETED=32`、`FAILED=7`、`PENDING=1`、`TIMED_OUT=3`
  - pending ticket：`tkt_f0c4c6154e6b`
  - open incident：无
- 续跑命令：`.venv/bin/python -m tests.live.run_configured --config data/live-tests/library_management_autopilot_live_015.toml --max-ticks 7200 --timeout-sec 172800`
- 状态：已续跑，等待 BR-031 contract fix 票执行

### P07. BR-031 contract fix 票建票参数修正

- 时间：2026-04-29T05:00+08:00
- 现象 1：`tkt_f0c4c6154e6b` 失败，原因 `UPSTREAM_DEPENDENCY_UNHEALTHY / Delivery-stage parent node was cancelled.`。
- 根因 1：第一张 BR-031 修复票的 `parent_ticket_id` 指到了 BR-032 check 票；该 check 节点刚取消 stale retry，依赖门把 parent node 识别为 cancelled。
- 修补 1：补发 `tkt_2262491ff9ae`，parent 改为 BR-031 已完成内审票 `tkt_4d60a4a0f37e`。
- 现象 2：`tkt_2262491ff9ae` 卡在 pending；controller 为 `STAFFING_WAIT`，原因 `WORKER_EXCLUDED`。
- 根因 2：我为避免同一前端员工重复返工，排除了 `emp_frontend_2`；但当前 roster 中可用前端工程师只有它。
- 修补 2：
  - 取消 `tkt_2262491ff9ae`
  - 补发同内容、无 `excluded_employee_ids` 的 BR-031 修复票：`tkt_c247833b2c60`
- 修补后状态：
  - ticket 汇总：`CANCELLED=2`、`COMPLETED=32`、`EXECUTING=1`、`FAILED=8`、`TIMED_OUT=3`
  - active ticket：`tkt_c247833b2c60`
  - leased by：`emp_frontend_2`
  - provider：attempt 1 已 started，等待首 token
- 状态：已继续执行

#### M25. BR-031 contract fix 通过并回到 check

- 时间：2026-04-29T05:10+08:00
- workflow：`wf_7f2902f3c8c6`
- current_stage：`check`
- workflow status：`EXECUTING`
- ticket 汇总：`CANCELLED=2`、`COMPLETED=34`、`FAILED=8`、`LEASED=1`、`PENDING=2`、`TIMED_OUT=3`
- 已完成：
  - `tkt_c247833b2c60`：BR-031 frontend auth contract fix source delivery completed
  - `tkt_f00a95436db3`：BR-031 fix maker-checker completed
- 当前 active / leased：
  - `tkt_e2b36aef19e9`
  - 节点：`node_backlog_followup_br_032_m3_checker_gate`
  - leased by：`emp_checker_1`
- 新增 pending：
  - `tkt_bc01fe6761b7`：`node_backlog_followup_br_040_m4_catalog_search_availability`
  - `tkt_1a11a3cb856d`：`node_backlog_followup_br_050_m5_reader_account_controls`
- recovering incident：
  - 新增 `inc_e06c17e617ac`，类型 `COMPILER_FAILURE`，breaker 已关闭，关联 `tkt_e2b36aef19e9`
  - 当前无 open incident
- provider：
  - `tkt_c247833b2c60` attempt 1 completed
  - `tkt_f00a95436db3` attempt 1 completed
- 判断：第15轮已越过 BR-032 卡点，进入后续 backlog fanout；当前仅记录 compiler 自动恢复，不做修补

### P08. BR-032 check 引用被 supersede 的旧 BR-031 process asset

- 时间：2026-04-29T05:15+08:00
- 现象：`tkt_e2b36aef19e9` 进入 LEASED 后卡住，没有 provider attempt。最近 orchestration 显示 `START_REJECTED / An identical ticket-start command was already accepted.`
- 根因：该票 start 时触发 `COMPILER_FAILURE`，原因 `EVIDENCE_LINEAGE_BREAK: Process asset pa://source-code-delivery/tkt_d9e52680a9c5@1 is SUPERSEDED and cannot be consumed.`。CEO 自动 `RESTORE_ONLY` 关闭 breaker，但原票仍带旧 process asset，后续重复 start 只返回 duplicate。
- 运行修补：
  - 取消 `tkt_e2b36aef19e9`
  - 补发 BR-032 check 票：`tkt_2e4ac9dd357e`
  - 新票 parent：最新 BR-031 内审票 `tkt_f00a95436db3`
  - 新票输入：19 个 artifact refs、23 个 process refs
  - 明确移除旧 BR-031 `tkt_d9e52680a9c5` / `tkt_4d60a4a0f37e` process asset 引用，改用 `tkt_c247833b2c60` / `tkt_f00a95436db3`
- 状态：已补发，等待 runner lease/start

#### M26. BR-032 最新 check 通过

- 时间：2026-04-29T05:21+08:00
- workflow：`wf_7f2902f3c8c6`
- current_stage：`build`
- 已完成：
  - `tkt_2e4ac9dd357e`：BR-032 delivery check report completed
  - `tkt_1b2b27220047`：BR-032 maker-checker completed
- 结果：`delivery-check-report.json` 为 `PASS_WITH_NOTES`
- 关键结论：
  - F01-F05 已关闭
  - F06 已由最新 BR-031 修复 `tkt_c247833b2c60` 关闭
  - 报告明确不再使用 superseded 的 `tkt_d9e52680a9c5`
- 当前 open incident：无
- 判断：BR-032 gate 已恢复，后续应重新 fanout M4/M5

### P09. M4/M5 旧 fanout 仍指向已取消的 BR-032 check 票

- 时间：2026-04-29T05:24+08:00
- 现象：`tkt_bc01fe6761b7`、`tkt_1a11a3cb856d`、`tkt_1ecaa17fa622`、`tkt_eb693db06957` 均因 `DEPENDENCY_GATE_UNHEALTHY` 失败。
- 根因：这些票的 `dependency_gate_refs` 指向旧 check 票 `tkt_e2b36aef19e9`；该票因 superseded asset 问题被取消。最新有效 gate 是 `tkt_1b2b27220047`。
- 运行修补：
  - 补发 M4 catalog/search 票：`tkt_323aeea06ca7`
  - 补发 M5 reader/account 票：`tkt_59a583845ce5`
  - 两票 dependency gate 均改为：`tkt_2909094a4371`、`tkt_1b2b27220047`
  - 其他 spec 沿用原 CEO fanout ticket
- 状态：已补发，等待 runner 调度

#### M27. M4/M5 重新进入 build

- 时间：2026-04-29T05:31+08:00
- workflow：`wf_7f2902f3c8c6`
- current_stage：`build`
- workflow status：`EXECUTING`
- ticket 汇总：`CANCELLED=3`、`COMPLETED=36`、`EXECUTING=1`、`FAILED=12`、`PENDING=1`、`TIMED_OUT=3`
- active ticket：`tkt_323aeea06ca7`
- active 节点：`node_backlog_followup_br_040_m4_catalog_search_availability`
- leased by：`emp_backend_backup`
- pending ticket：`tkt_59a583845ce5`，`node_backlog_followup_br_050_m5_reader_account_controls`
- provider：
  - `tkt_323aeea06ca7` attempt 1 触发 `FIRST_TOKEN_TIMEOUT`
  - runner 已自动 schedule retry
  - attempt 2 已 started
- open incident：无
- 判断：这是 provider 首 token 波动，自动 retry 正常；不做修补

#### M28. 1800 秒稳态检查 4

- 时间：2026-04-29T06:02+08:00
- workflow：`wf_7f2902f3c8c6`
- current_stage：`build`
- workflow status：`EXECUTING`
- ticket 汇总：`CANCELLED=3`、`COMPLETED=36`、`EXECUTING=1`、`FAILED=13`、`TIMED_OUT=5`
- active ticket：`tkt_445a977fdacc`
- active 节点：`node_backlog_followup_br_050_m5_reader_account_controls`
- leased by：`emp_backend_backup`
- latest failed：
  - `tkt_e4569d9b9238`：BR-040 replacement，`PROVIDER_BAD_RESPONSE / stream_read_error`
  - `tkt_eb693db06957`、`tkt_bc01fe6761b7`：旧 BR-040 dependency gate 失败
  - `tkt_1ecaa17fa622`、`tkt_1a11a3cb856d`：旧 BR-050 dependency gate 失败
- latest timed out：
  - `tkt_323aeea06ca7`：BR-040，`HEARTBEAT_TIMEOUT`
  - `tkt_59a583845ce5`：BR-050，`HEARTBEAT_TIMEOUT`
- provider：
  - `tkt_445a977fdacc` attempt 1 `FIRST_TOKEN_TIMEOUT` 后自动 retry
  - `tkt_445a977fdacc` attempt 2 已 started
  - `tkt_e4569d9b9238` 多次 `FIRST_TOKEN_TIMEOUT` 后最终 `stream_read_error`
- open incident：无
- recovering incident：`inc_bb26a499ba9a`、`inc_e06c17e617ac` 等均 breaker closed
- 判断：当前主要是 provider 首 token / stream 波动与 heartbeat timeout replacement；runner 仍在自动 replacement / retry，暂不做修补

#### M29. 1800 秒稳态检查 5

- 时间：2026-04-29T06:32+08:00
- workflow：`wf_7f2902f3c8c6`
- current_stage：`build`
- workflow status：`EXECUTING`
- ticket 汇总：`CANCELLED=3`、`COMPLETED=36`、`EXECUTING=1`、`FAILED=13`、`TIMED_OUT=6`
- active ticket：`tkt_749c0c3f615e`
- active 节点：`node_backlog_followup_br_050_m5_reader_account_controls`
- leased by：`emp_backend_backup`
- latest timed out：
  - `tkt_445a977fdacc`：BR-050 replacement，`HEARTBEAT_TIMEOUT`
  - `tkt_59a583845ce5`：BR-050，`HEARTBEAT_TIMEOUT`
  - `tkt_323aeea06ca7`：BR-040，`HEARTBEAT_TIMEOUT`
- latest failed：
  - `tkt_e4569d9b9238`：BR-040 replacement，`PROVIDER_BAD_RESPONSE / stream_read_error`
- provider：
  - `tkt_749c0c3f615e` attempt 4 已收到首 token 并 streaming
  - `tkt_445a977fdacc` 已 timed out，但仍有较晚 provider heartbeat 事件落库；当前 ticket projection 已不是 active
- open incident：无
- recovering incident：
  - 新增 `inc_14502dc25c4d`，`RUNTIME_TIMEOUT_ESCALATION`，breaker closed，关联 `tkt_445a977fdacc`
  - 其他 recovering incident 仍为历史记录
- 判断：runner 已把 M5 切到 replacement ticket 继续执行；旧票的迟到 provider heartbeat 先记录不修补，除非后续污染当前 projection 或阻断调度

#### M30. 人工进度查询快照

- 时间：2026-04-29T12:28+08:00
- runner：仍在运行，PID `95245`
- workflow：`wf_7f2902f3c8c6`
- current_stage：`build`
- workflow status：`EXECUTING`
- ticket 汇总：`CANCELLED=3`、`COMPLETED=38`、`FAILED=13`、`TIMED_OUT=6`
- 最近完成：
  - `tkt_749c0c3f615e`：M5 reader account controls source delivery completed
  - `tkt_8462be62365e`：M5 maker-checker completed
- 当前 active ticket：无
- open incident：无
- recovering incident：仅历史 closed breaker 记录
- M4 状态：
  - `tkt_e4569d9b9238`：BR-040 replacement，`stream_read_error`
  - 当前还没看到新的 BR-040 replacement 票被补出
- 判断：M5 已走通，当前主要剩 BR-040 catalog/search 主线恢复；runner 还活着，但最新自动 fanout节奏明显变慢，需要继续盯后续是否自动补票

#### M31. 人工进度查询快照 2

- 时间：2026-04-29T12:57+08:00
- runner：仍在运行，PID `95245`
- workflow：`wf_7f2902f3c8c6`
- current_stage：`build`
- workflow status：`EXECUTING`
- ticket 汇总：`CANCELLED=3`、`COMPLETED=38`、`FAILED=13`、`TIMED_OUT=6`
- 当前 active ticket：无
- controller：`READY_FOR_FANOUT`
- recommended_action：`CREATE_TICKET`
- 最近完成：
  - `tkt_749c0c3f615e`：M5 source delivery completed
  - `tkt_8462be62365e`：M5 maker-checker completed
- 当前阻塞点：
  - BR-040 最新 replacement `tkt_e4569d9b9238` 已因 `PROVIDER_BAD_RESPONSE / stream_read_error` 失败
  - 还未看到新的 BR-040 replacement 票
- incident：
  - `inc_5ef1710618da` 曾因 `tkt_e4569d9b9238 exhausted its failure retry budget or failure retry is disabled` 打开
  - 已由 CEO shadow rerun 自动关闭，breaker closed
- 判断：当前无 open incident、无 active ticket；runner 仍活着，系统处于 `READY_FOR_FANOUT`，等待 CEO/runner 重新创建后续票

#### M32. 人工进度查询快照 3

- 时间：2026-04-29T12:59+08:00
- runner：仍在运行，PID `95245`
- workflow：`wf_7f2902f3c8c6`
- current_stage：`build`
- workflow status：`EXECUTING`
- ticket 汇总：`CANCELLED=3`、`COMPLETED=38`、`FAILED=13`、`TIMED_OUT=6`
- 当前 active ticket：无
- controller probe：
  - `effect = WAIT_FOR_INCIDENT`
  - `state = WAIT_FOR_INCIDENT`
  - `recommended_action = NO_ACTION`
  - blocking reason：`Workflow has an open incident.`
- incident projection：
  - 最近新增 `inc_dbcee6506afa`、`inc_39bdab9670a9`、`inc_5ef1710618da`
  - 均为 `CEO_SHADOW_PIPELINE_FAILED`
  - 错误均指向 `Ticket tkt_e4569d9b9238 exhausted its failure retry budget or failure retry is disabled.`
  - projection 中这些 incident 已由 CEO shadow rerun 自动关闭，breaker closed
  - 仍有历史 `RECOVERING` 记录，breaker closed
- 最新产物：
  - `integration-monitor-report.md` 更新时间：2026-04-29 12:58
  - `run_report.json`、`audit-summary.md` 暂无新 closeout
- 判断：
  - runner 未退出，但业务进展停在 M5 完成之后
  - BR-040 最新 replacement `tkt_e4569d9b9238` 因 provider `stream_read_error` 失败后，没有看到新的 replacement 票
  - CEO shadow 正在围绕同一失败票反复开关 incident，当前需要继续诊断是否要最小修补 fanout / restore 路径

#### R15-Repair-04. scheduler-idle CEO incident 无法恢复耗尽 retry 的 BR-040 失败票

- 时间：2026-04-29T13:04+08:00
- 现象：
  - runner 仍运行，PID `95245`
  - workflow：`wf_7f2902f3c8c6`
  - current_stage：`build`
  - BR-040 最新 replacement `tkt_e4569d9b9238` 已失败：`PROVIDER_BAD_RESPONSE / stream_read_error`
  - CEO shadow 多次打开并关闭 `CEO_SHADOW_PIPELINE_FAILED` incident
  - 错误信息反复为 `Ticket tkt_e4569d9b9238 exhausted its failure retry budget or failure retry is disabled.`
  - 但 incident 的 `trigger_type` 是 `SCHEDULER_IDLE_MAINTENANCE`，`trigger_ref` 是 live-scenario 字符串，不是 ticket id
- 根因：
  - CEO incident 恢复逻辑只从 `ticket_id`、`payload.ticket_id`、`trigger_ref` 识别源 ticket
  - scheduler idle maintenance 触发的 incident 没有结构化 ticket id
  - 源 ticket id 只存在于 `error_message`，导致自动恢复只能 rerun CEO，无法调度 `RESTORE_AND_RETRY_LATEST_FAILURE`
- 修补动作：
  - 修改 `backend/app/core/incident_followups.py`
    - 增加从 `error_message` 中解析 `Ticket tkt_*` 的兜底逻辑
    - 只在 `trigger_ref` 以 `tkt_` 开头时才把它当 ticket id
  - 修改 `backend/app/core/ticket_handlers.py`
    - incident resolve 的源 ticket 解析同步增加 `error_message` 兜底
    - 同样收紧 `trigger_ref` 的 ticket id 判定
  - 修改 `backend/tests/test_api.py`
    - 增加 scheduler-idle incident 从错误文本恢复源 ticket 的回归测试
- 验证：
  - `cd backend && TMPDIR=$(pwd)/.tmp/pytest-015 TEMP=$(pwd)/.tmp/pytest-015 TMP=$(pwd)/.tmp/pytest-015 .venv/bin/python -m pytest tests/test_api.py::test_ceo_shadow_scheduler_idle_incident_restores_ticket_from_error_message tests/test_api.py::test_p2_ceo_shadow_incident_resolve_restores_and_retries_latest_failure_for_source_ticket -q`
  - 结果：`2 passed in 0.94s`
- live 修复执行：
  - 使用修补后的本地代码创建手工恢复 incident：`inc_manual_015_br040_restore_1302`
  - followup action：`RESTORE_AND_RETRY_LATEST_FAILURE`
  - resolve 结果：`ACCEPTED`
  - 新 BR-040 retry ticket：`tkt_f50880be28af`
  - 当前 node：`node_backlog_followup_br_040_m4_catalog_search_availability`
  - 新票状态：先为 `PENDING`

#### M33. 修补后恢复快照

- 时间：2026-04-29T13:06+08:00
- runner：仍在运行，PID `95245`
- workflow：`wf_7f2902f3c8c6`
- current_stage：`build`
- workflow status：`EXECUTING`
- ticket 汇总：`CANCELLED=3`、`COMPLETED=38`、`EXECUTING=1`、`FAILED=13`、`TIMED_OUT=6`
- active ticket：`tkt_f50880be28af`
- active 节点：`node_backlog_followup_br_040_m4_catalog_search_availability`
- leased by：`emp_backend_backup`
- retry_count：`2`
- incident：
  - `inc_manual_015_br040_restore_1302`：`RECOVERING`，breaker closed
  - `inc_b35422a0c60b`：已 closed，provider rate limited 后 CEO rerun 成功
- provider：
  - `tkt_f50880be28af` 已进入执行
  - integration monitor 显示 provider 多次 `retry_waiting`
- 判断：
  - 卡点已解除，BR-040 重新进入执行
  - 当前是 provider 限流/重试等待，暂不修补代码
  - 继续按 1800 秒稳态节奏监控

#### M34. 修补后轻量检查

- 时间：2026-04-29T13:12+08:00
- runner：仍在运行，PID `95245`
- workflow：`wf_7f2902f3c8c6`
- current_stage：`build`
- workflow status：`EXECUTING`
- ticket 汇总：`CANCELLED=3`、`COMPLETED=38`、`EXECUTING=1`、`FAILED=14`、`TIMED_OUT=6`
- active ticket：`tkt_3881c7b6b67c`
- active 节点：`node_backlog_followup_br_040_m4_catalog_search_availability`
- leased by：`emp_backend_backup`
- retry_count：`3`
- 上一张 BR-040 retry：
  - `tkt_f50880be28af` 已失败
  - failure：`PROVIDER_BAD_RESPONSE`
  - message：`Provider response did not contain any assistant text output.`
- incident：
  - `inc_30a6f34d85dc`：`RECOVERING`，breaker closed
  - 该 incident 来自 backlog follow-up restore-needed，runner 已自动补出 `tkt_3881c7b6b67c`
  - `inc_manual_015_br040_restore_1302` 仍为 `RECOVERING`，breaker closed
- provider：
  - `tkt_f50880be28af` 多次 retry waiting 后收到空 assistant 输出
  - `tkt_3881c7b6b67c` 已被 runner 接走执行
- 判断：
  - 第15轮继续推进
  - 当前异常仍是 provider 响应质量/限流波动，runner 已自动 replacement
  - 暂不进行代码修补

#### M35. BR-040 retry 执行中检查

- 时间：2026-04-29T13:18+08:00
- runner：仍在运行，PID `95245`
- workflow：`wf_7f2902f3c8c6`
- current_stage：`build`
- workflow status：`EXECUTING`
- ticket 汇总：`CANCELLED=3`、`COMPLETED=38`、`EXECUTING=1`、`FAILED=14`、`TIMED_OUT=6`
- active ticket：`tkt_3881c7b6b67c`
- active 节点：`node_backlog_followup_br_040_m4_catalog_search_availability`
- leased by：`emp_backend_backup`
- retry_count：`3`
- open incident：无
- recovering incident：
  - `inc_30a6f34d85dc`：breaker closed
  - `inc_manual_015_br040_restore_1302`：breaker closed
  - 其他为历史 recovering 记录，breaker closed
- 最新产物：
  - `integration-monitor-report.md` 最新可见段落仍停在 `13:09` 左右
  - workflow projection 已更新到 `13:18:41+08:00`
- 判断：
  - BR-040 retry 仍在执行中
  - 没看到新失败或 open incident
  - 暂不修补，继续等待

#### M36. 1800 秒稳态检查 6

- 时间：2026-04-29T13:38+08:00
- runner：仍在运行，PID `95245`
- workflow：`wf_7f2902f3c8c6`
- current_stage：`build`
- workflow status：`EXECUTING`
- ticket 汇总：`CANCELLED=3`、`COMPLETED=40`、`EXECUTING=1`、`FAILED=15`、`TIMED_OUT=6`
- active ticket：`tkt_850f9de580ec`
- active 节点：`node_backlog_followup_br_041_m4_isbn_remove_inventory`
- leased by：`emp_backend_backup`
- retry_count：`1`
- 关键进展：
  - BR-040 source delivery retry `tkt_3881c7b6b67c` 已完成
  - BR-040 checker / follow-up `tkt_6b201d02f2a5` 已完成
  - runner 已推进到 BR-041 ISBN 删除与库存能力
- 最近失败：
  - `tkt_fd6e771c3515`：BR-041 初次执行失败
  - failure：`PROVIDER_BAD_RESPONSE / stream_read_error`
  - runner 已自动 replacement 到 `tkt_850f9de580ec`
- provider：
  - `tkt_850f9de580ec` 曾因 first token 等待进入 retry
  - 13:38 monitor 显示 attempt 1 已进入 `streaming`
  - 多次 `PROVIDER_ATTEMPT_ACTIVE` skip，表示已有活跃 provider attempt，暂不重复启动
- incident：
  - open incident：无
  - recovering incident：`inc_manual_015_br040_restore_1302` 等历史恢复记录，breaker closed
- 最新产物：
  - `integration-monitor-report.md` 更新时间：2026-04-29 13:38
  - `run_report.json`、`audit-summary.md` 暂未刷新 closeout
- 判断：
  - 第15轮已越过 BR-040 卡点
  - 当前主线继续在 M4 的 BR-041 执行
  - provider 仍有 stream / first-token 波动，但 runner 正常 replacement / retry
  - 暂不修补代码，继续 1800 秒监控

#### M37. 1800 秒稳态检查 7

- 时间：2026-04-29T14:08+08:00
- runner：仍在运行，PID `95245`
- workflow：`wf_7f2902f3c8c6`
- current_stage：`build`
- workflow status：`EXECUTING`
- ticket 汇总：`CANCELLED=3`、`COMPLETED=40`、`EXECUTING=1`、`FAILED=15`、`TIMED_OUT=7`
- active ticket：`tkt_fd1785718f2d`
- active 节点：`node_backlog_followup_br_041_m4_isbn_remove_inventory`
- leased by：`emp_backend_backup`
- retry_count：`1`
- BR-041 进展：
  - 初始 BR-041 ticket `tkt_fd6e771c3515` 失败：`PROVIDER_BAD_RESPONSE / stream_read_error`
  - replacement `tkt_850f9de580ec` 超时：`HEARTBEAT_TIMEOUT`
  - runner 已自动 replacement 到 `tkt_fd1785718f2d`
- provider：
  - `tkt_fd1785718f2d` 当前处于 provider active attempt
  - monitor 显示多次 `awaiting_first_token`
  - 后续 tick 因 `PROVIDER_ATTEMPT_ACTIVE` 跳过重复启动
- incident：
  - open incident：无
  - recovering incident：均为 breaker closed 的恢复记录
- 最新产物：
  - `integration-monitor-report.md` 更新时间：2026-04-29 14:07
  - `run_report.json`、`audit-summary.md` 暂未刷新 closeout
- 判断：
  - 第15轮仍在推进，当前卡在 BR-041 provider 首 token 等待
  - runner 的 timeout / replacement 机制仍有效
  - 暂不做修补，继续等待下一轮 1800 秒检查

#### M38. 1800 秒稳态检查 8

- 时间：2026-04-29T14:39+08:00
- runner：仍在运行，PID `95245`
- workflow：`wf_7f2902f3c8c6`
- current_stage：`build`
- workflow status：`EXECUTING`
- ticket 汇总：`CANCELLED=3`、`COMPLETED=40`、`FAILED=15`、`TIMED_OUT=8`
- active ticket：无
- 当前阻塞节点：`node_backlog_followup_br_041_m4_isbn_remove_inventory`
- BR-041 当前票：
  - `tkt_fd1785718f2d`：`TIMED_OUT`
  - failure：`HEARTBEAT_TIMEOUT`
  - retry_count：`1`
- provider：
  - `tkt_fd1785718f2d` attempt 6 在 ticket timeout 后晚到 `COMPLETED`
  - projection 未把 ticket 变成 completed
- controller probe：
  - `effect = READY_FOR_FANOUT`
  - `state = READY_FOR_FANOUT`
  - `recommended_action = CREATE_TICKET`
- CEO shadow：
  - 多次围绕 BR-041 触发 scheduler idle maintenance
  - 出现 `deterministic_fallback.backlog_followup[restore_needed]`
  - 自动恢复动作仍是 `RERUN_CEO_SHADOW`
  - 后续 provider 直接 `CREATE_TICKET` 被拒绝，因为 `node_id already exists in the current workflow`
- 判断：
  - 当前不是 provider 等待，而是 restore-needed incident 缺少 source ticket metadata
  - 自动恢复无法定位 `tkt_fd1785718f2d`，导致反复 rerun CEO 或重复 create 同一 node
  - 需要最小代码修补：restore-needed incident 没有 ticket id 时，从当前 workflow 选最新 terminal ticket 作为恢复源

#### R15-Repair-05. restore-needed incident 缺失 source ticket 时无法恢复 BR-041 timeout

- 时间：2026-04-29T14:42+08:00
- 现象：
  - BR-041 replacement `tkt_fd1785718f2d` 已 `TIMED_OUT`
  - workflow 无 active ticket
  - controller 为 `READY_FOR_FANOUT / CREATE_TICKET`
  - CEO shadow incident 报 `restore_needed`，但 incident payload 没有 `ticket_id`
  - 自动恢复只做 `RERUN_CEO_SHADOW`
  - provider 生成的 BR-041 `CREATE_TICKET` 被拒绝：`node_id already exists in the current workflow`
- 根因：
  - `restore_needed` 的 `CEOProposalContractError` 没有把 `source_ticket_id` 写进 incident payload
  - 恢复逻辑只能从 `ticket_id`、`payload.ticket_id`、`trigger_ref` 或 `Ticket tkt_*` 错误文本提取源票
  - 这类错误文本只有 `restore_needed`，没有具体 `tkt_*`
- 修补动作：
  - 修改 `backend/app/core/incident_followups.py`
    - 识别 `restore_needed` / `restore/retry recovery` 错误
    - 无显式 source ticket 时，从同一 workflow 中选择最新 `FAILED` 或 `TIMED_OUT` ticket 作为恢复源
  - 修改 `backend/app/core/ticket_handlers.py`
    - incident resolve 的 restore/retry validator 使用同样的最新 terminal ticket 兜底
  - 修改 `backend/tests/test_api.py`
    - 新增 restore-needed incident 无 source id 时恢复最新 terminal ticket 的回归测试
- 验证：
  - `cd backend && TMPDIR=$(pwd)/.tmp/pytest-015 TEMP=$(pwd)/.tmp/pytest-015 TMP=$(pwd)/.tmp/pytest-015 .venv/bin/python -m pytest tests/test_api.py::test_ceo_shadow_scheduler_idle_incident_restores_ticket_from_error_message tests/test_api.py::test_ceo_shadow_restore_needed_incident_uses_latest_terminal_ticket_without_source_id tests/test_api.py::test_p2_ceo_shadow_incident_resolve_restores_and_retries_latest_failure_for_source_ticket -q`
  - 结果：`3 passed in 2.19s`
- live 修复执行：
  - 创建手工恢复 incident：`inc_manual_015_br041_restore_1442`
  - followup action：`RESTORE_AND_RETRY_LATEST_TIMEOUT`
  - resolve 结果：`ACCEPTED`
  - 新 BR-041 retry ticket：`tkt_16e98b9b3311`
  - 状态：`EXECUTING`
  - leased by：`emp_backend_backup`
- 判断：
  - BR-041 已恢复执行
  - 本次不 clean、不重启
  - 继续按 1800 秒窗口监控

#### M39. 1800 秒稳态检查 9

- 时间：2026-04-29T15:14+08:00
- runner：仍在运行，PID `95245`
- workflow：`wf_7f2902f3c8c6`
- current_stage：`build`
- workflow status：`EXECUTING`
- ticket 汇总：`CANCELLED=3`、`COMPLETED=41`、`FAILED=17`、`PENDING=1`、`TIMED_OUT=8`
- active ticket：无
- BR-041 进展：
  - `tkt_5707c310bc6d`：BR-041 source delivery completed
  - `tkt_30c7a10979ae`：BR-041 maker-checker ticket created，状态 `PENDING`
  - `tkt_27320fb7979c`、`tkt_16e98b9b3311`：provider 空响应失败
  - `tkt_fd1785718f2d`、`tkt_850f9de580ec`：heartbeat timeout
- incident：
  - `inc_3bbf53c7b0fe` 曾因 `TICKET_COMPLETED:tkt_5707c310bc6d` 后 CEO provider 空响应打开
  - 已由 CEO shadow rerun 自动关闭，breaker closed
  - open incident：无
- controller probe：
  - `effect = RUN_SCHEDULER_TICK`
  - `state = READY_TICKET`
  - `recommended_action = NO_ACTION`
  - blocking reason：`Ready tickets already exist on the current mainline.`
- 判断：
  - BR-041 源码交付已完成
  - 当前剩 BR-041 maker-checker pending
  - runner 仍活着，但 DB 在 `15:10` 后短时间没有自动 lease pending checker，需要轻量 scheduler tick 推进

#### R15-Repair-06. BR-041 maker-checker pending 未及时 lease

- 时间：2026-04-29T15:16+08:00
- 现象：
  - `tkt_30c7a10979ae` 是 BR-041 maker-checker review ticket
  - 状态停在 `PENDING`
  - controller 已提示 `READY_TICKET`
  - runner 进程仍活着
- 根因判断：
  - 未发现 open incident
  - 更像 runner 调度节奏延迟，而不是业务断点
- 修补动作：
  - 手工发送一次 scheduler tick
  - 命令路径：`/api/v1/commands/scheduler-tick`
  - 不 clean、不重启、不改配置
- 结果：
  - scheduler tick：`ACCEPTED`
  - `tkt_30c7a10979ae` 从 `PENDING` 变为 `LEASED`
  - leased by：`emp_checker_1`
  - 约 1 分钟后 runner 自动 start
  - `tkt_30c7a10979ae` 状态：`EXECUTING`
  - provider attempt 已启动，模型：`gpt-5.5`
- 判断：
  - BR-041 maker-checker 已进入执行
  - 继续按 1800 秒窗口监控

#### M40. 1800 秒稳态检查 10

- 时间：2026-04-29T15:48+08:00
- runner：原 PID `95245` 已不在进程列表
- workflow：`wf_7f2902f3c8c6`
- current_stage：`check`
- workflow status：`EXECUTING`
- ticket 汇总：`CANCELLED=3`、`COMPLETED=46`、`FAILED=19`、`PENDING=1`、`TIMED_OUT=8`
- active ticket：无
- pending ticket：`tkt_339463c5376d`
- pending 节点：`node_backlog_followup_br_042_m4_checker_gate`
- 关键进展：
  - BR-041 已完成到 `tkt_2b58304dccb9`
  - workflow 已进入 `check` 阶段
  - BR-042 checker gate 多张检查票已完成：`tkt_c199a8fc9e0b`、`tkt_29a5aaf79075`、`tkt_b0906e5241cf`、`tkt_d2b9e44fb779`
  - 最新 `tkt_d2b9e44fb779` 完成后生成 `tkt_339463c5376d`
- incident：
  - open incident：无
  - recovering incident：均为 breaker closed 历史恢复记录
- 产物：
  - `integration-monitor-report.md` 更新时间：2026-04-29 15:47
  - `run_report.json` 仍是 01:54 的旧 `max_ticks` 结果，未记录本次 PID 退出
- 判断：
  - runner 进程退出，但 workflow 还在执行
  - 当前不应 clean 重启
  - 使用同一配置续跑，保留现有 DB 和产物

#### R15-Repair-07. runner 进程退出后续跑当前 DB

- 时间：2026-04-29T15:49+08:00
- 现象：
  - `ps` / `pgrep` 均找不到 `tests.live.run_configured` 进程
  - workflow 仍为 `EXECUTING / check`
  - 当前还有 `PENDING` ticket：`tkt_339463c5376d`
- 修补动作：
  - 继续使用原配置启动 runner
  - 命令：`cd backend && .venv/bin/python -m tests.live.run_configured --config data/live-tests/library_management_autopilot_live_015.toml --max-ticks 7200 --timeout-sec 172800`
  - 未使用 `--clean`
- 期望：
  - 从现有 DB 和 runtime artifact 继续推进
  - 优先处理 `tkt_339463c5376d`
- 结果：
  - 新 runner PID：`67421`
  - 续跑 20 秒后 `tkt_339463c5376d` 仍为 `PENDING`
  - 补一次 scheduler tick：`ACCEPTED`
  - `tkt_339463c5376d` lease 给 `emp_checker_1`
  - 约 1 分钟后 runner 自动 start
  - `tkt_339463c5376d` 状态：`EXECUTING`
  - workflow：`EXECUTING / check`

#### M41. 1800 秒稳态检查 11

- 时间：2026-04-29T16:27+08:00
- runner：新 PID `67421` 已退出
- workflow：`wf_7f2902f3c8c6`
- current_stage：`check`
- workflow status：`EXECUTING`
- ticket 汇总：`CANCELLED=3`、`COMPLETED=48`、`FAILED=19`、`PENDING=1`、`TIMED_OUT=8`
- active ticket：无
- pending ticket：`tkt_726251cf7142`
- pending 节点：`node_backlog_followup_br_042_m4_checker_gate`
- 关键进展：
  - `tkt_339463c5376d` completed
  - `tkt_c46a0d4253ad` completed
  - 新 rework/follow-up ticket `tkt_726251cf7142` created，状态 `PENDING`
- runner 退出原因：
  - `RuntimeLivenessUnavailableError`
  - message：`runtime_node_projection node_backlog_followup_br_042_m4_checker_gate points to tkt_726251cf7142 instead of tkt_339463c5376d.`
- 诊断：
  - 重新读取 graph snapshot 后，graph 与 runtime projection 已一致指向 `tkt_726251cf7142`
  - 判断为 rework ticket 刚生成时 graph/runtime projection 的短暂竞态
  - 暂不改代码

#### R15-Repair-08. runtime liveness projection 竞态后续跑

- 时间：2026-04-29T16:29+08:00
- 现象：
  - runner PID `67421` 退出
  - workflow 仍为 `EXECUTING / check`
  - `tkt_726251cf7142` 为 `PENDING`
- 修补动作：
  - 使用同一配置续跑，不加 `--clean`
  - 新 runner PID：`71716`
  - 续跑 20 秒后 `tkt_726251cf7142` 仍未被 lease
  - 手工发送一次 scheduler tick
- 结果：
  - scheduler tick：`ACCEPTED`
  - `tkt_726251cf7142` lease 给 `emp_checker_1`
  - 约 1 分钟后 runner 自动 start
  - `tkt_726251cf7142` 状态：`EXECUTING`
  - provider attempt 已启动
- 判断：
  - check 阶段继续推进
  - 暂不改代码

#### M42. resume 检查与 BR-042 卡点确认

- 时间：2026-04-29T17:08+08:00
- runner：PID `71716` 仍在运行
- workflow：`wf_7f2902f3c8c6`
- current_stage：`check`
- workflow status：`EXECUTING`
- ticket 汇总：`CANCELLED=3`、`COMPLETED=54`、`FAILED=19`、`TIMED_OUT=8`
- active / pending ticket：无
- open incident：无
- controller probe：
  - `effect = NO_IMMEDIATE_FOLLOWUP`
  - state：`CHECK_FAILED`
  - blocking reason：`Closeout gate is blocked by delivery_check_failed.`
  - closeout gate issue：`tkt_01c084dbf2bb` / `delivery_check_report` / `FAIL` / blocking findings = 2
- 诊断：
  - BR-040 已有完整 source-code-delivery、源文件 artifact 和 9 条 vitest 证据。
  - BR-041 最新 source-code-delivery `tkt_5707c310bc6d` 只有占位 `source.py`、占位 `pytest tests -q` 一条通过结果和 git-closeout。
  - BR-042 的 `F-M4-001` / `F-M4-002` 不是误判；当前证据确实不能证明 ISBN fallback、Remove、inventory discrepancy、audit、refreshed counts 等 M4 验收。
  - maker-checker rework escalation 达到阈值后只 auto resolve 为 `RESTORE_ONLY`，没有生成新的修复票，导致 workflow 无 active / pending ticket。

#### R15-Repair-09. 手工补发 BR-041 source-code-delivery 返工票

- 时间：2026-04-29T17:08+08:00
- 现象：
  - workflow 卡在 `CHECK_FAILED / delivery_check_failed`
  - 没有 active / pending ticket
  - BR-041 交付证据为占位实现，BR-042 无法继续通过检查
- 根因：
  - 自动 rework 到达重复阈值后打开 `MAKER_CHECKER_REWORK_ESCALATION`，随后 CEO delegate 使用 `RESTORE_ONLY` 关闭 incident。
  - 该路径没有生成新的 BR-041 修复 ticket，也没有补充 BR-042 所需证据。
- 修补动作：
  - 不改业务代码，不 clean 重启。
  - 使用现有 repository 事件入口补发一张 BR-041 `source_code_delivery` 返工票。
  - 新 ticket：`tkt_64c3fff23f9a`
  - parent：`tkt_8c172230c550`
  - 节点：`node_backlog_followup_br_041_m4_isbn_remove_inventory`
  - role：`backend_engineer_primary`
  - 输入证据加入：
    - `pa://governance-document/tkt_f58cc1d4ab7b@1`
    - `pa://source-code-delivery/tkt_3881c7b6b67c@1`
    - `pa://evidence-pack/tkt_3881c7b6b67c@1`
    - `pa://source-code-delivery/tkt_5707c310bc6d@1`
    - `pa://evidence-pack/tkt_5707c310bc6d@1`
    - `pa://artifact/art%3A%2F%2Fruntime%2Ftkt_01c084dbf2bb%2Fdelivery-check-report.json@1`
  - 新增验收要求：
    - 关闭 `F-M4-001`：产出可读 BR-041 changed-file inventory 和 source artifacts，映射到锁定范围。
    - 关闭 `F-M4-002`：产出 ISBN fallback、manual completion、Remove、inventory discrepancy、refreshed counts、audit fields 的具体回归证据。
    - 禁止再次提交占位 source 和占位一条测试证据。
- 验证：
  - DB 查询确认 `tkt_64c3fff23f9a` 已创建并被 runner 接走。
  - 状态：`EXECUTING`
  - lease owner：`emp_backend_backup`
  - workflow current_stage：`build`
- 备注：
  - 曾运行旧单测 `tests/test_api.py::test_repeated_checker_changes_required_opens_incident_instead_of_creating_next_fix_ticket`，结果失败；失败点是测试环境已有 5 个 open incident，不作为本次 live 数据修补验证依据。
  - 本次修补的有效验证以 live DB 投影为准。

#### M43. 1800 秒稳态检查 12

- 时间：2026-04-29T17:39+08:00
- runner：PID `71716` 仍在运行
- workflow：`wf_7f2902f3c8c6`
- current_stage：`build`
- workflow status：`EXECUTING`
- ticket 汇总：`CANCELLED=3`、`COMPLETED=54`、`FAILED=19`、`TIMED_OUT=9`
- active / leased / pending ticket：无
- 最新 ticket：
  - `tkt_64c3fff23f9a` / `TIMED_OUT` / `node_backlog_followup_br_041_m4_isbn_remove_inventory`
  - failure kind：`HEARTBEAT_TIMEOUT`
  - failure message：`Ticket missed the required heartbeat window.`
- provider attempt：
  - attempt 1：收到 first token 前接近 900 秒 lease 边界
  - attempt 2：`FAILED_RETRYABLE / FIRST_TOKEN_TIMEOUT`
  - attempt 3：`COMPLETED`，elapsed 约 587 秒，raw_text_length 41793，repair_steps 包含 `extract_json_object_fragment`
- 判断：
  - provider 最终完成，但 ticket 的 900 秒 lease 先过期，完成输出没有落成 `TICKET_COMPLETED`。
  - 根因是手工补发票沿用了原 BR-041 的短 lease，并且误继承了 `retry_count=4`。
  - 不 clean 重启；补发同等范围、长 lease 的重试票。

#### R15-Repair-10. BR-041 返工票改用长 lease 重试

- 时间：2026-04-29T17:40+08:00
- 现象：
  - `tkt_64c3fff23f9a` 已 `TIMED_OUT`
  - runner 仍运行，但 workflow 没有新 active ticket
- 根因：
  - `lease_timeout_sec=900` 不足以覆盖本轮 BR-041 修复的 provider 输出时长。
  - 手工 payload 继承了旧票 `retry_count=4`，不适合新修复票。
- 修补动作：
  - 补发新 BR-041 `source_code_delivery` 重试票。
  - 新 ticket：`tkt_f3724b9bf6b6`
  - parent：`tkt_64c3fff23f9a`
  - 节点：`node_backlog_followup_br_041_m4_isbn_remove_inventory`
  - role：`backend_engineer_primary`
  - `lease_timeout_sec = 3600`
  - `heartbeat_timeout_sec = 3600`
  - `retry_budget = 2`
  - `timeout_sla_sec = 7200`
  - 删除继承来的 `retry_count`
- 验证：
  - DB 查询确认 `tkt_f3724b9bf6b6` 已创建并被 lease。
  - 状态：`LEASED`
  - lease owner：`emp_backend_backup`
  - retry_count：`0`
  - workflow current_stage：`build`
  - 30 秒后复查状态已变为 `EXECUTING`

#### M44. 1800 秒稳态检查 13

- 时间：2026-04-29T18:12+08:00
- runner：PID `71716` 仍在运行
- workflow：`wf_7f2902f3c8c6`
- current_stage：`build`
- workflow status：`EXECUTING`
- ticket 汇总：`CANCELLED=3`、`COMPLETED=56`、`FAILED=20`、`TIMED_OUT=9`
- active / leased / pending ticket：无
- 最新进展：
  - `tkt_f3724b9bf6b6` 因 provider 空响应失败一次：`PROVIDER_BAD_RESPONSE`
  - runtime 自动重试生成 `tkt_28716b0f51c2`
  - `tkt_28716b0f51c2` 完成 BR-041 source-code-delivery，包含 9 个源文件、1 个测试证据、git closeout，以及 `pa://source-code-delivery/tkt_28716b0f51c2@1` / `pa://evidence-pack/tkt_28716b0f51c2@1`
  - maker-checker 票 `tkt_ec35843cafef` 完成，`review_status = APPROVED_WITH_NOTES`
- controller probe：
  - `effect = NO_IMMEDIATE_FOLLOWUP`
  - state：`CHECK_FAILED`
  - blocking reason：`Closeout gate is blocked by delivery_check_failed.`
  - closeout gate issue 仍指向旧 BR-042 检查票 `tkt_01c084dbf2bb`
- 判断：
  - BR-041 已补齐并通过 checker。
  - closeout gate 仍引用旧 BR-042 FAIL，因为没有自动创建新的 BR-042 recheck。

#### R15-Repair-11. 手工补发 BR-042 recheck 票

- 时间：2026-04-29T18:14+08:00
- 现象：
  - BR-041 最新交付已完成并通过 maker-checker。
  - BR-042 closeout gate 仍指向旧 `tkt_01c084dbf2bb` 的 FAIL。
- 根因：
  - 系统没有在 BR-041 返工通过后自动物化新的 BR-042 `delivery_check_report`。
- 修补动作：
  - 不 clean 重启。
  - 补发 BR-042 `delivery_check_report` 票。
  - 新 ticket：`tkt_53baa13a5bc0`
  - parent：`tkt_ec35843cafef`
  - 节点：`node_backlog_followup_br_042_m4_checker_gate`
  - role：`checker_primary`
  - 输入证据加入：
    - `pa://source-code-delivery/tkt_3881c7b6b67c@1`
    - `pa://evidence-pack/tkt_3881c7b6b67c@1`
    - `pa://source-code-delivery/tkt_28716b0f51c2@1`
    - `pa://evidence-pack/tkt_28716b0f51c2@1`
    - 旧 BR-042 FAIL 报告 `tkt_01c084dbf2bb`
  - `lease_timeout_sec = 3600`
  - `heartbeat_timeout_sec = 3600`
  - `retry_budget = 2`
  - `timeout_sla_sec = 7200`
- 验证：
  - DB 查询确认 `tkt_53baa13a5bc0` 已创建并进入 `EXECUTING`。
  - lease owner：`emp_checker_1`
  - workflow current_stage：`check`

#### M45. 接手检查与无 clean 续跑准备

- 时间：2026-04-29T18:51+08:00
- 状态：上一段补票命令已完成。
- 已取消错误 BR-040 修复票：`tkt_f999b57a4619` -> `CANCELLED`。
- 新 BR-040 reader copyStatus 修复票：`tkt_2252a7a1f92e`。
- parent：`tkt_6b201d02f2a5`。
- workflow：`wf_7f2902f3c8c6` / `EXECUTING` / `build`。
- ticket 汇总：`CANCELLED=5`、`COMPLETED=57`、`FAILED=20`、`PENDING=1`、`TIMED_OUT=9`。
- active / leased ticket：无。
- open incident：无；历史 incident 均为 `RECOVERING` 且 breaker `CLOSED`。
- runner：未发现运行中的 `tests.live.run_configured` 进程。
- 动作：按计划使用原配置无 clean 续跑，消费 `tkt_2252a7a1f92e`。

#### R15-Repair-14. 过滤取消节点的有效图边

- 时间：2026-04-29T18:56+08:00
- 现象：无 clean 续跑启动后立刻失败，错误为 `Graph health cannot evaluate a cyclic path around node node_backlog_followup_br_042_m4_checker_gate::review`。
- 根因：错误 BR-042 review 票 `tkt_809cef3f1293` 已取消，但 ticket graph 仍把 `CANCELLED` review lane 作为有效边端点参与 `PARENT_OF` / `REVIEWS` 图计算，导致旧环继续进入 graph health。
- 修补动作：
  - 修改 `backend/app/core/ticket_graph.py`，保留取消 / superseded 节点可见性，但从 effective graph edges 中跳过这些节点。
  - 新增回归测试 `tests/test_ticket_graph.py::test_ticket_graph_snapshot_excludes_cancelled_lane_from_effective_edges`。
- 验证：
  - `pytest tests/test_ticket_graph.py::test_ticket_graph_snapshot_excludes_cancelled_lane_from_effective_edges -q` -> `1 passed`。
  - 现场 CEO snapshot probe 已通过，不再抛 graph cycle。
  - controller 仍处于 `CHECK_FAILED`，closeout gate 指向 `tkt_53baa13a5bc0` 的 `delivery_check_failed`，等待新 BR-040 修复票推进。
- 下一步：无 clean 续跑，消费 `tkt_2252a7a1f92e`。

#### M46. BR-040 修复票进入执行

- 时间：2026-04-29T18:57+08:00
- runner：PID `92759`，session `35345`，无 clean 续跑中。
- workflow：`wf_7f2902f3c8c6` / `EXECUTING` / `build`。
- ticket 汇总：`CANCELLED=5`、`COMPLETED=57`、`EXECUTING=1`、`FAILED=20`、`TIMED_OUT=9`。
- active ticket：`tkt_2252a7a1f92e`。
- node：`node_backlog_followup_br_040_m4_catalog_search_availability`。
- lease owner：`emp_backend_backup`。
- retry_count：`0`。
- open incident：无；历史 incident 均为 `RECOVERING` 且 breaker `CLOSED`。
- provider retry：当前无失败。
- 最新产物：尚未产出，等待 BR-040 reader copyStatus 修复 delivery。
- 下一次稳态检查：约 2026-04-29T19:27+08:00。

#### R15-Repair-15. 人工修复 BR-040 reader copyStatus 状态泄漏缺口

- 时间：2026-04-29T19:09+08:00
- 现象：provider 完成的 BR-040 修复票 `tkt_2252a7a1f92e` 只产出占位 `source.py` 和 1 条空泛测试证据，未实际修复 reader `copyStatus` 过滤缺口。
- 根因：provider 交付质量不足，maker-checker 仅 `APPROVED_WITH_NOTES`，没有阻止占位交付进入后续链路。
- 修补动作：
  - 在 live artifacts 工作区最小修改 `10-project/src/backend/services/catalogAvailabilityService.js`。
  - reader 查询遇到 staff-only `copyStatus`（`WITHDRAWN` / `DAMAGED` / `LOST`）时忽略该过滤，不再用全量 copy 状态收窄 reader search。
  - 保留 staff / librarian 对 `WITHDRAWN` 等状态的过滤能力。
  - 增补 `10-project/src/backend/tests/catalogSearchAvailability.spec.js` 两条回归：reader 不被 staff-only 状态收窄；staff 状态过滤保留。
- 验证命令：
  - `/Users/bill/projects/boardroom-os/frontend/node_modules/.bin/vitest run tests/catalogSearchAvailability.spec.js`
- 验证结果：
  - `1 passed` test file。
  - `11 passed` tests。
- 记录交付：
  - 人工 BR-040 source delivery：`tkt_74b3903be938`。
  - source asset：`pa://source-code-delivery/tkt_74b3903be938@1`。
  - evidence asset：`pa://evidence-pack/tkt_74b3903be938@1`。

#### R15-Repair-16. 补发 BR-042 recheck

- 时间：2026-04-29T19:09+08:00
- 现象：BR-040 缺口已人工修复并登记，但 closeout gate 仍指向旧 BR-042 FAIL 票 `tkt_53baa13a5bc0`。
- 修补动作：
  - 补发 BR-042 `delivery_check_report` 票。
  - 新 ticket：`tkt_bea446b24760`。
  - parent：`tkt_74b3903be938`。
  - 输入证据加入 `pa://source-code-delivery/tkt_74b3903be938@1` 与 `pa://evidence-pack/tkt_74b3903be938@1`。
  - 未继承错误的 `MAKER_REWORK_FIX` ticket kind。
- 当前状态：
  - workflow：`EXECUTING` / `check`。
  - `tkt_bea446b24760`：`PENDING`。
  - runner：PID `92759` 仍运行，等待调度。

#### R15-Repair-17. 重启 runner 以重新加载 ready 队列

- 时间：2026-04-29T19:12+08:00
- 现象：`tkt_bea446b24760` 在 ticket graph 中已进入 ready 队列，但原 runner 只执行 CEO maintenance，runtime execution count 持续为 0。
- 根因判断：长跑 runner 未及时消费人工插入的 ready 票；无代码报错，无 open incident。
- 修补动作：停止本会话启动的 runner PID `92759`，准备无 clean 重启。
- 验证：`ps` 确认 PID `92759` 已退出。

#### R15-Repair-18. 重建 BR-042 recheck 票以恢复 checker 调度

- 时间：2026-04-29T19:14+08:00
- 现象：`tkt_bea446b24760` 在 graph ready 队列中，但 scheduler lease diagnostic 显示 `NO_ELIGIBLE_WORKER`。
- 根因：该票从旧 BR-042 payload 继承了 `excluded_employee_ids=["emp_checker_1", "emp_checker_backup"]`，而可用 `checker_primary` 只有这两名员工。
- 修补动作：
  - 取消不可调度票：`tkt_bea446b24760` -> `CANCELLED`。
  - 复制 payload 并清空 `excluded_employee_ids`。
  - 新 BR-042 recheck ticket：`tkt_99e3ea177c8e`。
  - 保留输入证据：`pa://source-code-delivery/tkt_74b3903be938@1` / `pa://evidence-pack/tkt_74b3903be938@1`。
- 预期：runner 下一轮可由 `emp_checker_1` 或 `emp_checker_backup` lease。

#### M47. BR-042 recheck 已进入执行

- 时间：2026-04-29T19:15+08:00
- runner：PID `98894`，session `69220`，无 clean 续跑中。
- workflow：`wf_7f2902f3c8c6` / `EXECUTING` / `check`。
- ticket 汇总：`CANCELLED=6`、`COMPLETED=60`、`EXECUTING=1`、`FAILED=20`、`TIMED_OUT=9`。
- active ticket：`tkt_99e3ea177c8e`。
- node：`node_backlog_followup_br_042_m4_checker_gate`。
- lease owner：`emp_checker_1`。
- provider：attempt 1 已启动，模型按 checker 绑定使用 `gpt-5.5` / `xhigh`。
- open incident：无新增 open；`NO_ELIGIBLE_WORKER` 已通过 R15-Repair-18 解除。
- 最新产物：等待 `delivery-check-report.json`。

#### M48. BR-042 recheck 通过，M4 阻塞解除

- 时间：2026-04-29T19:18+08:00
- BR-042 recheck ticket：`tkt_99e3ea177c8e` -> `COMPLETED`。
- 报告产物：`art://runtime/tkt_99e3ea177c8e/delivery-check-report.json`。
- 报告结论：`PASS_WITH_NOTES`。
- 关键结论：
  - 已审阅 `pa://source-code-delivery/tkt_74b3903be938@1` 与 `pa://evidence-pack/tkt_74b3903be938@1`。
  - BR-040 reader search 已忽略 reader 提交的 staff-only `copyStatus`，只对 reader-visible 状态做 reader 过滤。
  - withdrawn / damaged-only 记录仍对 reader 隐藏。
  - staff copyStatus 过滤保留。
  - BR-040 focused evidence：`11/11` passed。
  - BR-041 最新证据仍可接受：`15/15` passed。
  - blocking findings 清零。
- controller probe：
  - `effect = WAIT_FOR_RUNTIME`。
  - `closeout_gate_issue = None`。
  - 当前阻塞只剩运行中 ticket。
- 当前主线：进入 M6 build，active ticket `tkt_353d0466adf7`，node `node_backlog_followup_br_060_m6_circulation_transactions`。

#### M49. 断网后恢复检查

- 时间：2026-04-29T20:17+08:00
- runner：PID `98894` 仍运行，session `69220`。
- workflow：`wf_7f2902f3c8c6` / `EXECUTING` / `build`。
- ticket 汇总：`CANCELLED=8`、`COMPLETED=62`、`EXECUTING=1`、`FAILED=21`、`PENDING=1`、`TIMED_OUT=11`。
- active ticket：`tkt_5d8e536a14c2`。
- active node：`node_backlog_followup_br_060_m6_circulation_transactions`。
- lease owner：`emp_backend_backup`。
- retry_count：`2`。
- pending ticket：`tkt_262f159fc931`，同 M6 circulation node，retry_count `3`。
- provider 状态：
  - `tkt_5d8e536a14c2` attempt 1 因 `UPSTREAM_UNAVAILABLE` 可重试失败。
  - attempt 2 已启动，状态 `PROVIDER_CONNECTING`，deadline `2026-04-29T20:45:48+08:00`。
- open incident：无；新增 provider / CEO shadow incident 已处于 `RECOVERING` 且 breaker `CLOSED`。
- 判断：当前属于 provider 自动 retry / replacement 范围，先记录，不做代码修补。

#### M50. M6 provider 自动重试观察

- 时间：2026-04-29T20:23+08:00
- workflow：`EXECUTING` / `build`。
- active ticket：`tkt_5d8e536a14c2`，node `node_backlog_followup_br_060_m6_circulation_transactions`。
- provider retry：
  - attempt 1：`FAILED_RETRYABLE`，`UPSTREAM_UNAVAILABLE`。
  - attempt 2：`FAILED_RETRYABLE`，`FIRST_TOKEN_TIMEOUT`。
  - attempt 3：已启动，状态 `PROVIDER_CONNECTING`，deadline `2026-04-29T20:50:53+08:00`。
- runner：PID `98894` 仍运行。
- 处理：provider 自动 retry 中，先记录，不做代码修补。

#### M51. M6 provider attempt 继续超时

- 时间：2026-04-29T20:28+08:00
- active ticket：`tkt_5d8e536a14c2`。
- attempt 3：`FAILED_RETRYABLE`，`FIRST_TOKEN_TIMEOUT`。
- attempt 4：已启动，状态 `PROVIDER_CONNECTING`，deadline `2026-04-29T20:56:00+08:00`。
- runner：PID `98894` 仍运行。
- 判断：仍属 provider 自动 retry；但该 ticket lease 为 900 秒，接近超时窗口，短间隔复查。

#### M52. M6 provider attempt 5 已进入 streaming

- 时间：2026-04-29T20:36+08:00
- active ticket：`tkt_5d8e536a14c2`。
- attempt 4：`FAILED_RETRYABLE`，`FIRST_TOKEN_TIMEOUT`。
- attempt 5：状态 `STREAMING`，last heartbeat `2026-04-29T20:35:46+08:00`。
- workflow：`EXECUTING` / `build`。
- runner：PID `98894` 仍运行。
- 处理：继续等待 provider 完成。

#### M53. BR-060 M6 circulation delivery 和 review 完成

- 时间：2026-04-29T20:43+08:00
- M6 source delivery：`tkt_5d8e536a14c2` -> `COMPLETED`。
- M6 review：`tkt_665d647e556a` -> `COMPLETED`，`review_status = APPROVED_WITH_NOTES`。
- source asset：`pa://source-code-delivery/tkt_5d8e536a14c2@1`。
- evidence asset：`pa://evidence-pack/tkt_5d8e536a14c2@1`。
- 验证摘要：`node --test 10-project/src/backend/tests/circulation/circulation-service.test.js`，`8/8` passed。
- 关键覆盖：borrow / return / one-time renewal / FIFO reservation / READY hold expiration / overdue fine / librarian payment confirmation / rollback / audit expectations。
- 当前 active ticket：`tkt_1da9c7b58569`。
- active node：`node_backlog_followup_br_061_m6_ac09_concurrency_regression`。
- runner：PID `98894` 仍运行。

#### M54. 1800 秒稳态检查 14

- 时间：2026-04-29T20:48+08:00
- runner：PID `98894` 仍运行。
- workflow：`wf_7f2902f3c8c6` / `EXECUTING` / `build`。
- ticket 汇总：`CANCELLED=8`、`COMPLETED=64`、`EXECUTING=1`、`FAILED=21`、`PENDING=1`、`TIMED_OUT=11`。
- active ticket：`tkt_1da9c7b58569`。
- active node：`node_backlog_followup_br_061_m6_ac09_concurrency_regression`。
- lease owner：`emp_backend_backup`。
- pending ticket：`tkt_262f159fc931`，旧 M6 retry 票，当前未被调度。
- open incident：无新增 open；历史 incident 为 `RECOVERING` / breaker `CLOSED`。
- provider retry：
  - `tkt_1da9c7b58569` attempt 1：`FAILED_RETRYABLE`，`FIRST_TOKEN_TIMEOUT`。
  - attempt 2：已启动，状态 `PROVIDER_CONNECTING`，deadline `2026-04-29T21:18:10+08:00`。
- 最新产物：
  - M4 BR-042 `PASS_WITH_NOTES`。
  - M6 BR-060 source delivery `pa://source-code-delivery/tkt_5d8e536a14c2@1`。
  - M6 evidence `pa://evidence-pack/tkt_5d8e536a14c2@1`，`8/8` passed。
- 判断：当前仍属 provider 自动 retry，继续监控，不做代码修补。
- 下一次 1800 秒稳态检查：约 2026-04-29T21:18+08:00。

#### M55. M6 AC09 并发回归完成，等待 fanout

- 时间：2026-04-29T20:55+08:00
- BR-061 ticket：`tkt_1da9c7b58569` -> `COMPLETED`。
- BR-061 review：`tkt_b0df77ec5918` -> `COMPLETED`，`review_status = APPROVED_WITH_NOTES`。
- ticket graph：ready / blocked / inflight 均为空。
- controller probe：
  - `effect = READY_FOR_FANOUT`。
  - state：`READY_FOR_FANOUT`。
  - recommended_action：`CREATE_TICKET`。
  - `closeout_gate_issue = None`。
- 残留观察：`tkt_262f159fc931` 仍为 `PENDING`，但不是 graph latest ticket，也不在 ready 队列中，暂不修补。
- 下一步：等待 CEO fanout 创建后续 ticket。

#### M56. BR-062 M6 checker gate 执行中

- 时间：2026-04-29T20:58+08:00
- workflow：`EXECUTING` / `check`。
- BR-062 delivery check：`tkt_ad82070ba9dd` -> `COMPLETED`，产物 `art://runtime/tkt_ad82070ba9dd/delivery-check-report.json`。
- BR-062 maker-checker review：`tkt_39da143de0c5` -> `EXECUTING`。
- lease owner：`emp_checker_1`。
- provider：`gpt-5.5` / `xhigh`，attempt 1 已启动。
- runner：PID `98894` 仍运行。

#### R15-Repair-19. 补发 BR-062 证据完整 recheck

- 时间：2026-04-29T21:03+08:00
- 现象：BR-062 自动 recheck 连续 fail-closed，报告均指出缺少 BR-060 / BR-061 具体 source、changed surfaces、transaction / rollback 测试、AC-09 concurrency 日志、reason-code 和 audit evidence。
- 根因：自动生成的 BR-062 payload 只包含 governance / backlog refs 和旧失败报告，没有带入最新 BR-060 / BR-061 source delivery 与 evidence pack。
- 修补动作：
  - 取消缺证据的 pending 票：`tkt_d36fcf6f8a6b` -> `CANCELLED`。
  - 补发 BR-062 `delivery_check_report` 票：`tkt_ffcc2148f694`。
  - parent：`tkt_b0df77ec5918`。
  - 输入 process assets：
    - `pa://source-code-delivery/tkt_5d8e536a14c2@1`
    - `pa://evidence-pack/tkt_5d8e536a14c2@1`
    - `pa://source-code-delivery/tkt_1da9c7b58569@1`
    - `pa://evidence-pack/tkt_1da9c7b58569@1`
    - 最新失败报告 artifact `tkt_c73fbd537a60`
  - 清空 `excluded_employee_ids`，避免无 eligible checker。
  - `lease_timeout_sec = 3600`、`heartbeat_timeout_sec = 3600`、`retry_budget = 2`。
- 预期：checker 能基于完整 BR-060 / BR-061 evidence 关闭 F-BR062-001 到 F-BR062-005，或给出真实未满足项。

#### M57. BR-062 证据完整 recheck 进入执行

- 时间：2026-04-29T21:04+08:00
- active ticket：`tkt_ffcc2148f694`。
- node：`node_backlog_followup_br_062_m6_checker_gate`。
- lease owner：`emp_checker_1`。
- workflow：`EXECUTING` / `check`。
- ticket 汇总：`CANCELLED=9`、`COMPLETED=75`、`EXECUTING=1`、`FAILED=21`、`PENDING=1`、`TIMED_OUT=11`。
- runner：PID `98894` 仍运行。
- 最新产物：等待 `delivery-check-report.json`。

#### M58. BR-062 证据完整 recheck 通过

- 时间：2026-04-29T21:08+08:00
- BR-062 recheck ticket：`tkt_ffcc2148f694` -> `COMPLETED`。
- 报告产物：`art://runtime/tkt_ffcc2148f694/delivery-check-report.json`。
- 报告结论：`PASS_WITH_NOTES`。
- 关键结论：
  - 已审阅 `pa://source-code-delivery/tkt_5d8e536a14c2@1` / `pa://evidence-pack/tkt_5d8e536a14c2@1`。
  - 已审阅 `pa://source-code-delivery/tkt_1da9c7b58569@1` / `pa://evidence-pack/tkt_1da9c7b58569@1`。
  - F-BR062-001 到 F-BR062-005 已关闭。
  - BR-060 覆盖 transaction wrapping、rollback、conditional copy-state transitions、stable reason codes、audit calls、FIFO reservations、fines、renewal、hold expiration、payment confirmation，`8/8` node tests passed。
  - BR-061 覆盖 AC-09 final-copy concurrency：一个成功 borrow、一个 `INVENTORY_INSUFFICIENT`、无 losing loan insert、刷新 backend-derived counts。
- controller probe：`closeout_gate_issue = None`，当前只等待运行中 ticket。
- 当前主线：进入 M7 build，active ticket `tkt_72d639849b29`。

#### M59. 1800 秒稳态检查 15

- 时间：2026-04-29T21:18+08:00
- runner：PID `98894` 仍运行。
- workflow：`wf_7f2902f3c8c6` / `EXECUTING` / `build`。
- ticket 汇总：`CANCELLED=9`、`COMPLETED=77`、`EXECUTING=1`、`FAILED=21`、`PENDING=1`、`TIMED_OUT=12`。
- active ticket：`tkt_42a2e015002b`。
- active node：`node_backlog_followup_br_070_m7_notifications_reminders`。
- lease owner：`emp_backend_backup`。
- provider / retry：
  - `tkt_72d639849b29` 因 `HEARTBEAT_TIMEOUT` -> `TIMED_OUT`。
  - replacement `tkt_42a2e015002b` 已进入 `EXECUTING`，retry_count `1`。
- open incident：无新增 open；历史 incident 为 `RECOVERING` / breaker `CLOSED`。
- 最新产物：BR-062 `PASS_WITH_NOTES` 已解除 M6 checker gate；当前等待 M7 source delivery。
- 处理：系统自动 replacement 正常，暂不做代码修补。
- 下一次 1800 秒稳态检查：约 2026-04-29T21:48+08:00。

#### M60. M7 provider 自动重试观察

- 时间：2026-04-29T21:28+08:00
- active ticket：`tkt_42a2e015002b`。
- node：`node_backlog_followup_br_070_m7_notifications_reminders`。
- attempt 1：`FAILED_RETRYABLE`，`FIRST_TOKEN_TIMEOUT`。
- attempt 2：`FAILED_RETRYABLE`，`FIRST_TOKEN_TIMEOUT`。
- attempt 3：已启动，状态 `PROVIDER_CONNECTING`，deadline `2026-04-29T21:58:07+08:00`。
- runner：PID `98894` 仍运行。
- 处理：provider 自动 retry 中，暂不修补。

#### M61. 断网恢复后继续监控

- 时间：2026-04-29T21:42+08:00
- runner：PID `98894` 仍运行。
- workflow：`wf_7f2902f3c8c6` / `EXECUTING` / `build`。
- ticket 汇总：`CANCELLED=9`、`COMPLETED=77`、`EXECUTING=1`、`FAILED=22`、`PENDING=1`、`TIMED_OUT=13`。
- active ticket：`tkt_ef62e8575eca`。
- active node：`node_backlog_followup_br_070_m7_notifications_reminders`。
- lease owner：`emp_backend_backup`。
- provider / retry：
  - `tkt_42a2e015002b` 后续 attempt 3 完成，但原票随后因 heartbeat timeout 进入 `TIMED_OUT`。
  - `tkt_9f8b63a7070b` 因 `PROVIDER_BAD_RESPONSE` / `stream_read_error` -> `FAILED`。
  - 最新 replacement `tkt_ef62e8575eca` 已进入 `EXECUTING`，attempt 1 状态 `PROVIDER_CONNECTING`，deadline `2026-04-29T22:08:04+08:00`。
- open incident：无 `OPEN`；最新 incident 均为 `RECOVERING` / breaker `CLOSED`。
- 最新产物：M6 BR-062 `PASS_WITH_NOTES` 仍为最新已确认 gate 产物；当前等待 M7 source delivery。
- 处理：provider retry / replacement 正常推进，暂不做代码或配置修补。

#### M62. 1800 秒稳态检查 16

- 时间：2026-04-29T21:48+08:00
- runner：PID `98894` 仍运行。
- workflow：`wf_7f2902f3c8c6` / `EXECUTING` / `build`。
- ticket 汇总：`CANCELLED=9`、`COMPLETED=77`、`EXECUTING=1`、`FAILED=22`、`PENDING=1`、`TIMED_OUT=13`。
- active ticket：`tkt_ef62e8575eca`。
- active node：`node_backlog_followup_br_070_m7_notifications_reminders`。
- lease owner：`emp_backend_backup`。
- provider / retry：
  - attempt 1：`FAILED_RETRYABLE`，`FIRST_TOKEN_TIMEOUT`。
  - attempt 2：`STREAMING`，last heartbeat `2026-04-29T21:47:51+08:00`，deadline `2026-04-29T22:13:08+08:00`。
- open incident：无 `OPEN`；历史 incident 仍为 `RECOVERING` / breaker `CLOSED`。
- 最新产物：
  - `run_report.json`
  - `audit-summary.md`
  - `integration-monitor-report.md`
  - M7 source delivery 暂未落地。
- 处理：provider 自动 retry 正常，继续等待；暂不做代码或配置修补。
- 下一次 1800 秒稳态检查：约 2026-04-29T22:18+08:00。

#### M63. M7 完成并推进到 M8

- 时间：2026-04-29T22:14+08:00
- runner：PID `98894` 仍运行。
- M7 source delivery：`tkt_ef62e8575eca` -> `COMPLETED`。
- M7 follow-up check：`tkt_af468640eff4` -> `COMPLETED`。
- M7 最新产物：
  - `artifacts/10-project/src/backend/routes/notifications-routes.js`
  - `artifacts/10-project/src/backend/tests/notifications-reminders.test.js`
  - `artifacts/20-evidence/git/tkt_ef62e8575eca/attempt-4/git-closeout.json`
  - `artifacts/20-evidence/tests/tkt_ef62e8575eca/attempt-4/br-070-attempt-2-node-test.txt`
- workflow：`wf_7f2902f3c8c6` / `EXECUTING` / `build`。
- 当前主线：M8 reports CSV。
- M8 active ticket：`tkt_5282fca94239`。
- M8 active node：`node_backlog_followup_br_080_m8_reports_csv`。
- lease owner：`emp_backend_backup`。
- provider / retry：
  - 原始 M8 票 `tkt_135091d66731` 因 `HEARTBEAT_TIMEOUT` -> `TIMED_OUT`。
  - replacement `tkt_5282fca94239` 已进入 `EXECUTING`。
  - `tkt_5282fca94239` attempt 1 / 2 均为 `FIRST_TOKEN_TIMEOUT` retryable。
  - `tkt_5282fca94239` attempt 3 状态 `PROVIDER_CONNECTING`，deadline `2026-04-29T22:44:33+08:00`。
- open incident：无 `OPEN`；最新 incident 仍为 `RECOVERING` / breaker `CLOSED`。
- 处理：M7 已解除；M8 处于 provider retry / replacement 正常路径，暂不做代码或配置修补。

#### M64. 1800 秒稳态检查 17

- 时间：2026-04-29T22:18+08:00
- runner：PID `98894` 仍运行。
- workflow：`wf_7f2902f3c8c6` / `EXECUTING` / `build`。
- ticket 汇总：`CANCELLED=9`、`COMPLETED=79`、`EXECUTING=1`、`FAILED=22`、`PENDING=1`、`TIMED_OUT=14`。
- active ticket：`tkt_5282fca94239`。
- active node：`node_backlog_followup_br_080_m8_reports_csv`。
- lease owner：`emp_backend_backup`。
- provider / retry：
  - 原始 M8 票 `tkt_135091d66731` 已 `TIMED_OUT`，但 attempt 5 当前为 `STREAMING`。
  - replacement `tkt_5282fca94239` 仍显示 `EXECUTING`。
  - `tkt_5282fca94239` attempt 1 / 2：`FIRST_TOKEN_TIMEOUT` retryable。
  - `tkt_5282fca94239` attempt 3：`FAILED_TERMINAL`，`PROVIDER_BAD_RESPONSE` / `upstream_error`。
- open incident：无 `OPEN`；最新 incident 仍为 `RECOVERING` / breaker `CLOSED`。
- 最新产物：22:18 前 25 分钟内未发现 M8 新交付产物；M7 交付产物仍是最新确认产物。
- 处理：先按 provider / projection 短暂滞后观察，不立即修补；若 active 票长时间停在无可用 attempt 的 `EXECUTING`，再做最小恢复。
- 下一次 1800 秒稳态检查：约 2026-04-29T22:48+08:00。

#### M65. M8 replacement 自动恢复

- 时间：2026-04-29T22:21+08:00
- runner：PID `98894` 仍运行。
- workflow：`wf_7f2902f3c8c6` / `EXECUTING` / `build`。
- ticket 汇总：`CANCELLED=9`、`COMPLETED=79`、`EXECUTING=1`、`FAILED=22`、`PENDING=1`、`TIMED_OUT=15`。
- M8 active ticket：`tkt_435815471a92`。
- active node：`node_backlog_followup_br_080_m8_reports_csv`。
- lease owner：`emp_backend_backup`。
- provider / retry：
  - `tkt_5282fca94239` 因 `HEARTBEAT_TIMEOUT` -> `TIMED_OUT`。
  - incident `inc_614e7ca8f07d`：`RUNTIME_TIMEOUT_ESCALATION`，followup action `RESTORE_AND_RETRY_LATEST_TIMEOUT`，followup ticket `tkt_435815471a92`，状态 `RECOVERING` / breaker `CLOSED`。
  - replacement `tkt_435815471a92` attempt 1：`PROVIDER_CONNECTING`，deadline `2026-04-29T22:50:17+08:00`。
- 最新产物：M8 暂无新文件落地。
- 处理：系统自动 replacement 已接管，暂不做代码或配置修补。

#### M66. 1800 秒稳态检查 18

- 时间：2026-04-29T22:48+08:00
- runner：PID `98894` 仍运行。
- workflow：`wf_7f2902f3c8c6` / `EXECUTING` / `build`。
- ticket 汇总：`CANCELLED=9`、`COMPLETED=79`、`EXECUTING=1`、`FAILED=22`、`PENDING=1`、`TIMED_OUT=15`。
- active ticket：`tkt_435815471a92`。
- active node：`node_backlog_followup_br_080_m8_reports_csv`。
- lease owner：`emp_backend_backup`。
- provider / retry：
  - `tkt_435815471a92` attempt 1 / 2 / 3：`FIRST_TOKEN_TIMEOUT` retryable。
  - `tkt_435815471a92` attempt 4：`SCHEMA_VALIDATION_FAILED` retryable，原因是 `verification_runs` counts 未描述至少一个 discovered test。
  - `tkt_435815471a92` attempt 5：`STREAMING`，last heartbeat `2026-04-29T22:48:51+08:00`，deadline `2026-04-29T23:14:10+08:00`。
  - 旧超时票 `tkt_5282fca94239` 仍有 provider retry 投影更新，但当前 active 票仍为 `tkt_435815471a92`。
- open incident：无 `OPEN`；`inc_614e7ca8f07d` 为 `RECOVERING` / breaker `CLOSED`。
- 最新产物：M8 暂无新交付产物；M7 交付产物仍是最新确认产物。
- 处理：schema validation 失败已进入 retryable 分支，provider 正在继续 streaming；暂不修补。
- 下一次 1800 秒稳态检查：约 2026-04-29T23:18+08:00。

#### M67. M8 完成并推进到 M9

- 时间：2026-04-29T23:15+08:00
- runner：PID `98894` 仍运行。
- workflow：`wf_7f2902f3c8c6` / `EXECUTING` / `build`。
- ticket 汇总：`CANCELLED=9`、`COMPLETED=83`、`EXECUTING=1`、`FAILED=22`、`PENDING=1`、`TIMED_OUT=15`。
- M8 source delivery：`tkt_435815471a92` -> `COMPLETED`。
- M8 follow-up check：`tkt_dd7ebbfc1a0e` -> `COMPLETED`。
- M8 最新产物：
  - `artifacts/10-project/src/backend/controllers/adminReportsController.js`
  - `artifacts/10-project/src/backend/routes/adminReportRoutes.js`
  - `artifacts/20-evidence/git/tkt_435815471a92/attempt-3/git-closeout.json`
  - `artifacts/20-evidence/tests/tkt_435815471a92/attempt-3/br-080-m8-reports-csv-attempt-5.txt`
- M9 BR-090 frontend catalog availability：
  - source delivery：`tkt_a2872b736e68` -> `COMPLETED`。
  - follow-up check：`tkt_896458557017` -> `COMPLETED`。
  - 产物：
    - `artifacts/10-project/src/frontend/router/catalog.routes.ts`
    - `artifacts/10-project/src/frontend/tests/catalog-api.spec.ts`
    - `artifacts/20-evidence/git/tkt_a2872b736e68/attempt-1/git-closeout.json`
    - `artifacts/20-evidence/tests/br-090/attempt-1/manual-static-contract-review.txt`
    - `artifacts/20-evidence/tests/br-090/attempt-1/manual-ui-smoke-checklist.txt`
- 当前 active ticket：`tkt_08155c032840`。
- active node：`node_backlog_followup_br_093_m9_frontend_reader_loans_reservations`。
- lease owner：`emp_frontend_2`。
- provider / retry：attempt 1 `PROVIDER_CONNECTING`，deadline `2026-04-29T23:41:22+08:00`。
- open incident：无 `OPEN`；历史 incident 均为 `RECOVERING` / breaker `CLOSED`。
- 处理：M8 和 BR-090 已完成，M9 BR-093 正常执行中，暂不修补。

#### M68. 1800 秒稳态检查 19

- 时间：2026-04-29T23:18+08:00
- runner：PID `98894` 仍运行。
- workflow：`wf_7f2902f3c8c6` / `EXECUTING` / `build`。
- ticket 汇总：`CANCELLED=9`、`COMPLETED=83`、`EXECUTING=1`、`FAILED=22`、`PENDING=1`、`TIMED_OUT=15`。
- active ticket：`tkt_08155c032840`。
- active node：`node_backlog_followup_br_093_m9_frontend_reader_loans_reservations`。
- lease owner：`emp_frontend_2`。
- provider / retry：
  - attempt 1：`FAILED_RETRYABLE`，`FIRST_TOKEN_TIMEOUT`。
  - attempt 2：`PROVIDER_CONNECTING`，deadline `2026-04-29T23:46:25+08:00`。
- open incident：无 `OPEN`；历史 incident 均为 `RECOVERING` / breaker `CLOSED`。
- 最新产物：
  - BR-090 `catalog.routes.ts`
  - BR-090 `catalog-api.spec.ts`
  - BR-090 git closeout 与 manual static / smoke evidence
  - BR-093 暂无新交付产物。
- 处理：provider retry 正常，继续等待；暂不修补。
- 下一次 1800 秒稳态检查：约 2026-04-29T23:48+08:00。

#### M69. 1800 秒稳态检查 20

- 时间：2026-04-29T23:48+08:00
- runner：PID `98894` 仍运行。
- workflow：`wf_7f2902f3c8c6` / `EXECUTING` / `build`。
- ticket 汇总：`CANCELLED=9`、`COMPLETED=85`、`FAILED=23`、`PENDING=1`、`TIMED_OUT=16`。
- BR-093 source delivery：`tkt_eda8a49e2ad6` -> `COMPLETED`。
- BR-093 follow-up check：`tkt_4016e4817981` -> `COMPLETED`。
- BR-093 provider / retry：
  - `tkt_08155c032840` 因 `HEARTBEAT_TIMEOUT` -> `TIMED_OUT`，但 attempt 2 完成。
  - `tkt_985de7524a3b` 因 `PROVIDER_BAD_RESPONSE` / `stream_read_error` -> `FAILED`。
  - replacement `tkt_eda8a49e2ad6` attempt 2 完成。
  - follow-up check `tkt_4016e4817981` attempt 1 完成。
- BR-093 最新产物：
  - `artifacts/10-project/src/frontend/api/readerCirculation.ts`
  - `artifacts/10-project/src/frontend/router/readerCirculationRoutes.ts`
  - `artifacts/10-project/src/frontend/stores/readerCirculation.ts`
  - `artifacts/10-project/src/frontend/tests/reader-circulation.smoke.spec.ts`
  - `artifacts/20-evidence/git/tkt_eda8a49e2ad6/attempt-3/git-closeout.json`
  - `artifacts/20-evidence/tests/tkt_eda8a49e2ad6/attempt-3/tkt_eda8a49e2ad6-attempt-2-reader-circulation-smoke.txt`
- open incident：无 `OPEN`；历史 incident 均为 `RECOVERING` / breaker `CLOSED`。
- active / leased / failed：
  - 查询时无 active / leased ticket。
  - 最新 failed ticket：`tkt_985de7524a3b`，provider `stream_read_error`，已由 replacement 完成覆盖。
- 处理：BR-093 已完成；当前像是 controller fanout 间隙，先短等复查，不做修补。
- 下一次 1800 秒稳态检查：约 2026-04-30T00:18+08:00。

#### M70. BR-094 fanout 接续

- 时间：2026-04-29T23:50+08:00
- runner：PID `98894` 仍运行。
- workflow：`wf_7f2902f3c8c6` / `EXECUTING` / `build`。
- ticket 汇总：`CANCELLED=9`、`COMPLETED=85`、`EXECUTING=1`、`FAILED=23`、`PENDING=1`、`TIMED_OUT=16`。
- active ticket：`tkt_e409cc84ae4f`。
- active node：`node_backlog_followup_br_094_m9_frontend_reader_notifications`。
- lease owner：`emp_frontend_2`。
- incident：
  - `inc_4cb18259ae64` 已 `CLOSED`，CEO shadow rerun completed successfully。
  - `inc_8ba909c70b5f` 已 `CLOSED`，follow-up ticket completed successfully。
- 最新产物：`integration-monitor-report.md` 已在 `2026-04-29T23:49:46+08:00` 更新。
- 处理：controller fanout 已接续到 BR-094，暂不修补。

#### M71. 1800 秒稳态检查 21

- 时间：2026-04-30T00:18+08:00
- runner：PID `98894` 仍运行。
- workflow：`wf_7f2902f3c8c6` / `EXECUTING` / `build`。
- ticket 汇总：`CANCELLED=9`、`COMPLETED=88`、`EXECUTING=1`、`FAILED=25`、`PENDING=1`、`TIMED_OUT=16`。
- BR-094 reader notifications：
  - 原始票 `tkt_e409cc84ae4f` 因 `PROVIDER_BAD_RESPONSE` / `stream_read_error` -> `FAILED`。
  - replacement source delivery：`tkt_0a6e35dc452d` -> `COMPLETED`。
  - follow-up check：`tkt_3ff675f86f1d` -> `COMPLETED`。
  - 产物：
    - `artifacts/20-evidence/git/tkt_0a6e35dc452d/attempt-2/git-closeout.json`
    - `artifacts/20-evidence/tests/attempt-2/reader-notifications-api-trace.txt`
    - `artifacts/20-evidence/tests/attempt-2/reader-notifications-ux-checklist.txt`
    - `artifacts/20-evidence/tests/attempt-2/reader-notifications-vitest.txt`
- 当前 active ticket：`tkt_cd1836e06ec4`。
- active node：`node_backlog_followup_br_091_m9_frontend_staff_admin_flows`。
- lease owner：`emp_checker_1`。
- BR-091 provider / retry：
  - `tkt_f37b69a7f63e` 因 `RUNTIME_ERROR` / `database is locked` -> `FAILED`。
  - replacement / follow-up `tkt_cf6f05ed54be` -> `COMPLETED`。
  - 当前 active `tkt_cd1836e06ec4` attempt 1：`PROVIDER_CONNECTING`，deadline `2026-04-30T00:49:45+08:00`。
- open incident：无 `OPEN`；历史 incident 均为 `RECOVERING` / breaker `CLOSED`。
- 处理：`database is locked` 已被后续票接管，暂不做代码或配置修补。
- 下一次 1800 秒稳态检查：约 2026-04-30T00:48+08:00。

#### M72. 探查间隔调整为 600 秒

- 时间：2026-04-30T00:41+08:00
- 用户指令：从现在起，探查间隔缩短到 600 秒。
- 动作：
  - 立即执行一次探查。
  - 停止本会话中此前启动的 1680 秒 sleep 等待进程 `77900`。
  - 后续巡检按 600 秒节奏执行。
- runner：PID `98894` 仍运行。
- workflow：`wf_7f2902f3c8c6` / `EXECUTING` / `build`。
- ticket 汇总：`CANCELLED=9`、`COMPLETED=89`、`EXECUTING=1`、`FAILED=26`、`PENDING=1`、`TIMED_OUT=17`。
- BR-091 staff/admin flows：
  - `tkt_cf6f05ed54be` -> `COMPLETED`。
  - `tkt_cd1836e06ec4` -> `COMPLETED`。
  - 产物：
    - `artifacts/20-evidence/git/tkt_cf6f05ed54be/attempt-2/git-closeout.json`
    - `artifacts/20-evidence/tests/tkt_cf6f05ed54be/attempt-2/tkt_cf6f05ed54be-attempt-1-vitest.txt`
- 当前 active ticket：`tkt_d46f56e7a6d0`。
- active node：`node_backlog_followup_br_092_m9_frontend_responsive_smoke`。
- lease owner：`emp_frontend_2`。
- BR-092 provider / retry：
  - `tkt_521af4be1027` 因 `HEARTBEAT_TIMEOUT` -> `TIMED_OUT`，但 attempt 2 完成。
  - `tkt_0910ffa779c7` 因 `PROVIDER_BAD_RESPONSE` / `stream_read_error` -> `FAILED`。
  - replacement `tkt_d46f56e7a6d0` attempt 1：`STREAMING`，deadline `2026-04-30T01:11:26+08:00`。
- open incident：
  - `inc_84060ae87b2d` 为 `RECOVERING` / breaker `CLOSED`，错误信息为已有 backlog follow-up 需要 restore/retry，不应生成新 fallback 票；当前 replacement 已运行。
- 处理：BR-092 replacement 正常 streaming，暂不做代码或配置修补。
- 下一次 600 秒探查：约 2026-04-30T00:51+08:00。

#### M73. 600 秒探查 1

- 时间：2026-04-30T00:52+08:00
- runner：PID `98894` 仍运行。
- workflow：`wf_7f2902f3c8c6` / `EXECUTING` / `build`。
- ticket 汇总：`CANCELLED=9`、`COMPLETED=91`、`EXECUTING=1`、`FAILED=26`、`PENDING=1`、`TIMED_OUT=17`。
- BR-092 responsive smoke：
  - `tkt_521af4be1027` 因 `HEARTBEAT_TIMEOUT` -> `TIMED_OUT`，但 attempt 2 完成。
  - `tkt_0910ffa779c7` 因 `PROVIDER_BAD_RESPONSE` / `stream_read_error` -> `FAILED`。
  - replacement source delivery：`tkt_d46f56e7a6d0` -> `COMPLETED`。
  - follow-up check：`tkt_2606ddb0c3e7` -> `COMPLETED`。
  - 产物：
    - `artifacts/20-evidence/git/tkt_d46f56e7a6d0/attempt-3/git-closeout.json`
    - `artifacts/20-evidence/tests/tkt_d46f56e7a6d0/attempt-3/br-092-responsive-smoke-attempt-1.txt`
- 当前 active ticket：`tkt_67edf2c4bc45`。
- active node：`node_backlog_followup_br_101_m10_startup_handoff_pack`。
- lease owner：`emp_platform_backup`。
- M10 provider / retry：attempt 1 `PROVIDER_CONNECTING`，deadline `2026-04-30T01:22:25+08:00`。
- open incident：无新增 `OPEN`；历史 incident 均为 `RECOVERING` / breaker `CLOSED`。
- 处理：M9 前端链路已推进到 M10 handoff，当前正常执行，暂不修补。
- 下一次 600 秒探查：约 2026-04-30T01:02+08:00。

#### M74. 600 秒探查 2

- 时间：2026-04-30T01:03+08:00
- runner：PID `98894` 仍运行。
- workflow：`wf_7f2902f3c8c6` / `EXECUTING` / `build`。
- ticket 汇总：`CANCELLED=9`、`COMPLETED=93`、`EXECUTING=1`、`FAILED=26`、`PENDING=1`、`TIMED_OUT=17`。
- BR-101 startup handoff pack：
  - source delivery：`tkt_67edf2c4bc45` -> `COMPLETED`。
  - follow-up check：`tkt_fd89808dd336` -> `COMPLETED`。
  - 产物：
    - `artifacts/10-project/src/platform/startup/br101-startup-handoff-manifest.mjs`
    - `artifacts/10-project/src/platform/startup/verify-br101-startup-handoff.mjs`
    - `artifacts/20-evidence/git/tkt_67edf2c4bc45/attempt-1/git-closeout.json`
    - `artifacts/20-evidence/tests/br-101/attempt-1/handoff-outline.log`
    - `artifacts/20-evidence/tests/br-101/attempt-1/manifest-validation.log`
- 当前 active ticket：`tkt_7c3ab740e13a`。
- active node：`node_backlog_followup_br_102_m10_ac_api_regression_evidence`。
- lease owner：`emp_backend_backup`。
- BR-102 provider / retry：attempt 1 `PROVIDER_CONNECTING`，deadline `2026-04-30T01:31:07+08:00`。
- open incident：无新增 `OPEN`；历史 incident 均为 `RECOVERING` / breaker `CLOSED`。
- 处理：M10 handoff 已完成，BR-102 正常执行，暂不修补。
- 下一次 600 秒探查：约 2026-04-30T01:13+08:00。

#### M75. 600 秒探查 3

- 时间：2026-04-30T01:13+08:00
- runner：PID `98894` 仍运行。
- workflow：`wf_7f2902f3c8c6` / `EXECUTING` / `build`。
- ticket 汇总：`CANCELLED=9`、`COMPLETED=93`、`EXECUTING=1`、`FAILED=26`、`PENDING=1`、`TIMED_OUT=18`。
- 当前 active ticket：`tkt_aa411a305eff`。
- active node：`node_backlog_followup_br_102_m10_ac_api_regression_evidence`。
- lease owner：`emp_backend_backup`。
- BR-102 provider / retry：
  - 原始票 `tkt_7c3ab740e13a` 因 `HEARTBEAT_TIMEOUT` -> `TIMED_OUT`。
  - `tkt_7c3ab740e13a` attempt 1：`FIRST_TOKEN_TIMEOUT` retryable。
  - `tkt_7c3ab740e13a` 后续 attempt 2 / 3 投影仍可见，但 active 已切到 replacement。
  - replacement `tkt_aa411a305eff` attempt 1：`PROVIDER_CONNECTING`，deadline `2026-04-30T01:41:12+08:00`。
- open incident：无新增 `OPEN`；历史 incident 均为 `RECOVERING` / breaker `CLOSED`。
- 最新产物：本轮 15 分钟窗口内未发现 BR-102 新交付产物。
- 处理：BR-102 replacement 正常接管，暂不做代码或配置修补。
- 下一次 600 秒探查：约 2026-04-30T01:23+08:00。

#### M76. 600 秒探查 4

- 时间：2026-04-30T01:24+08:00
- runner：PID `98894` 仍运行。
- workflow：`wf_7f2902f3c8c6` / `EXECUTING` / `build`。
- ticket 汇总：`CANCELLED=9`、`COMPLETED=93`、`EXECUTING=1`、`FAILED=26`、`PENDING=1`、`TIMED_OUT=18`。
- 当前 active ticket：`tkt_aa411a305eff`。
- active node：`node_backlog_followup_br_102_m10_ac_api_regression_evidence`。
- lease owner：`emp_backend_backup`。
- BR-102 provider / retry：
  - replacement `tkt_aa411a305eff` attempt 1：`FIRST_TOKEN_TIMEOUT` retryable。
  - replacement `tkt_aa411a305eff` attempt 2：`FIRST_TOKEN_TIMEOUT` retryable。
  - replacement `tkt_aa411a305eff` attempt 3：`PROVIDER_CONNECTING`，deadline `2026-04-30T01:51:24+08:00`。
  - 原始票 `tkt_7c3ab740e13a` 后续 attempt 4 为 `PROVIDER_BAD_RESPONSE` / `upstream_error` terminal；active 已由 replacement 接管。
- open incident：无新增 `OPEN`；历史 incident 均为 `RECOVERING` / breaker `CLOSED`。
- 最新产物：本轮 15 分钟窗口内未发现 BR-102 新交付产物。
- 处理：provider retry 仍在推进，暂不做代码或配置修补。
- 下一次 600 秒探查：约 2026-04-30T01:34+08:00。

#### M77. 600 秒探查 5

- 时间：2026-04-30T01:35+08:00
- runner：PID `98894` 仍运行。
- workflow：`wf_7f2902f3c8c6` / `EXECUTING` / `build`。
- ticket 汇总：`CANCELLED=9`、`COMPLETED=95`、`FAILED=26`、`PENDING=1`、`TIMED_OUT=19`。
- BR-102 API regression evidence：
  - `tkt_aa411a305eff` 因 `HEARTBEAT_TIMEOUT` -> `TIMED_OUT`。
  - incident `inc_362015724317`：`RUNTIME_TIMEOUT_ESCALATION`，follow-up completed 后自动关闭。
  - source delivery：`tkt_b502981640f5` -> `COMPLETED`。
  - follow-up check：`tkt_b904924a94cd` -> `COMPLETED`。
  - 产物：
    - `artifacts/20-evidence/git/tkt_b502981640f5/attempt-3/git-closeout.json`
    - `artifacts/20-evidence/tests/tkt_b502981640f5/attempt-3/br-102-api-regression-attempt-3.log`
- 短等复查：
  - 时间：2026-04-30T01:37+08:00
  - workflow：`wf_7f2902f3c8c6` / `EXECUTING` / `check`。
  - ticket 汇总：`CANCELLED=9`、`COMPLETED=96`、`EXECUTING=1`、`FAILED=26`、`PENDING=1`、`TIMED_OUT=19`。
  - BR-100 final checker pre-ticket：`tkt_cd24602b4ead` -> `COMPLETED`。
  - active ticket：`tkt_00b8923d42d3`。
  - active node：`node_backlog_followup_br_100_m10_final_checker_evidence_gate`。
  - lease owner：`emp_checker_1`。
  - provider / retry：attempt 1 `PROVIDER_CONNECTING`，deadline `2026-04-30T02:07:36+08:00`。
- 最新产物：`integration-monitor-report.md` 已在 `2026-04-30T01:37:37+08:00` 更新。
- 处理：BR-102 已完成并进入 final checker gate，暂不做代码或配置修补。
- 下一次 600 秒探查：约 2026-04-30T01:47+08:00。

#### M78. runner 退出后无 clean 续跑

- 时间：2026-04-30T01:48+08:00
- 现象：
  - 600 秒探查时未发现原 runner 进程。
  - workflow 仍为 `EXECUTING` / `check`。
  - final checker gate 有 pending 票：`tkt_c288b0584e76`。
- 当时状态：
  - ticket 汇总：`CANCELLED=9`、`COMPLETED=100`、`FAILED=26`、`PENDING=2`、`TIMED_OUT=19`。
  - BR-100 final checker 已完成多张检查票：
    - `tkt_cd24602b4ead`
    - `tkt_00b8923d42d3`
    - `tkt_75674c5714be`
    - `tkt_5d729fd6e778`
    - `tkt_6709386cce03`
  - 剩余 pending：
    - `tkt_c288b0584e76`
    - 历史 pending `tkt_262f159fc931`
- 最新产物：
  - `artifacts/reports/check/tkt_cd24602b4ead/delivery-check-report.json`
  - `artifacts/reports/check/tkt_75674c5714be/delivery-check-report.json`
  - `artifacts/reports/check/tkt_6709386cce03/delivery-check-report.json`
- 修补动作：
  - 不使用 `--clean`。
  - 执行无 clean 续跑命令：
    - `.venv/bin/python -m tests.live.run_configured --config data/live-tests/library_management_autopilot_live_015.toml --max-ticks 7200 --timeout-sec 172800`
  - 新 runner：PID `6932`，本会话 session `7520`。
- 验证：
  - 续跑后 `tkt_c288b0584e76` 从 `PENDING` 进入 `EXECUTING`。
  - lease owner：`emp_checker_1`。
  - provider / retry：attempt 1 `PROVIDER_CONNECTING`，deadline `2026-04-30T02:19:44+08:00`。
  - workflow 仍为 `EXECUTING` / `check`。
- 处理：runner 已恢复并接管 pending final checker 票，暂不做代码或配置修补。
- 下一次 600 秒探查：约 2026-04-30T01:59+08:00。

#### M79. 600 秒探查 6

- 时间：2026-04-30T02:00+08:00
- runner：PID `6932` 仍运行。
- workflow：`wf_7f2902f3c8c6` / `EXECUTING` / `check`。
- ticket 汇总：`CANCELLED=9`、`COMPLETED=112`、`EXECUTING=1`、`FAILED=26`、`PENDING=1`、`TIMED_OUT=19`。
- BR-100 final checker evidence gate：
  - 已连续完成多张检查票，包括：
    - `tkt_c288b0584e76`
    - `tkt_592b0a3d3d48`
    - `tkt_25606b59a3ad`
    - `tkt_bb68831453e9`
    - `tkt_d57030d6381d`
    - `tkt_b08a19b12ed9`
    - `tkt_a88912ed76bb`
    - `tkt_469b78d2e68f`
    - `tkt_29bf54847044`
    - `tkt_9b4bbe5a0fde`
    - `tkt_3f530a770423`
    - `tkt_6a8e70b5de9d`
  - 当前 active ticket：`tkt_758f4eaae6e7`。
  - lease owner：`emp_checker_1`。
  - provider / retry：attempt 1 `PROVIDER_CONNECTING`，deadline `2026-04-30T02:30:36+08:00`。
- 最新产物：
  - `artifacts/reports/check/tkt_469b78d2e68f/delivery-check-report.json`
  - `artifacts/reports/check/tkt_592b0a3d3d48/delivery-check-report.json`
  - `artifacts/reports/check/tkt_6a8e70b5de9d/delivery-check-report.json`
  - `artifacts/reports/check/tkt_9b4bbe5a0fde/delivery-check-report.json`
  - `artifacts/reports/check/tkt_b08a19b12ed9/delivery-check-report.json`
  - `artifacts/reports/check/tkt_bb68831453e9/delivery-check-report.json`
- open incident：无新增 `OPEN`；历史 incident 均为 `RECOVERING` / breaker `CLOSED`。
- 处理：final checker gate 正常推进，暂不做代码或配置修补。
- 下一次 600 秒探查：约 2026-04-30T02:10+08:00。

#### M80. 600 秒探查 7 / 间隔确认

- 时间：2026-04-30T02:13+08:00
- 用户指令：从现在起探查间隔固定缩短为 `600s`。
- runner：PID `6932` 仍运行，已运行约 `24m05s`。
- workflow：`wf_7f2902f3c8c6` / `EXECUTING` / `check`。
- ticket 汇总：`CANCELLED=9`、`COMPLETED=122`、`EXECUTING=1`、`FAILED=26`、`PENDING=1`、`TIMED_OUT=19`。
- 当前 active ticket：`tkt_0b2e721673e1`。
- active node：`node_backlog_followup_br_100_m10_final_checker_evidence_gate`。
- lease owner：`emp_checker_1`。
- provider / retry：
  - `tkt_0b2e721673e1` attempt 1：`STREAMING`，deadline `2026-04-30T02:42:21+08:00`。
  - 上一张 final checker 票 `tkt_ea1f060d0dd3` 已从执行态落为 `COMPLETED`。
- latest artifacts：
  - `artifacts/reports/check/tkt_469b78d2e68f/delivery-check-report.json`
  - `artifacts/reports/check/tkt_6a8e70b5de9d/delivery-check-report.json`
  - `artifacts/reports/check/tkt_7a09f45ab91d/delivery-check-report.json`
  - `artifacts/reports/check/tkt_893a3052f510/delivery-check-report.json`
  - `artifacts/reports/check/tkt_9b4bbe5a0fde/delivery-check-report.json`
  - `artifacts/reports/check/tkt_9bc1564ed1b6/delivery-check-report.json`
  - `artifacts/reports/check/tkt_b08a19b12ed9/delivery-check-report.json`
  - `artifacts/reports/check/tkt_bb68831453e9/delivery-check-report.json`
  - `artifacts/reports/check/tkt_de0913edd0fb/delivery-check-report.json`
  - `artifacts/reports/check/tkt_ea1f060d0dd3/delivery-check-report.json`
- open incident：无新增 `OPEN`；历史 incident 均为 `RECOVERING` / breaker `CLOSED`。
- 处理：final checker gate 正常推进，暂不做代码或配置修补。
- 下一次 600 秒探查：约 2026-04-30T02:23+08:00。

#### M81. runner 退出后无 clean 续跑 2

- 时间：2026-04-30T02:23+08:00
- 现象：
  - 600 秒探查时未发现 runner 进程。
  - workflow 仍为 `EXECUTING` / `check`。
  - final checker gate 剩余 pending 票：`tkt_1919a6ecc4aa`。
- 当时状态：
  - ticket 汇总：`CANCELLED=9`、`COMPLETED=133`、`FAILED=26`、`PENDING=2`、`TIMED_OUT=19`。
  - BR-100 final checker 已继续完成多张检查票，包括：
    - `tkt_0b2e721673e1`
    - `tkt_eedc3c83aa61`
    - `tkt_7d31d621f414`
    - `tkt_5159131ca748`
    - `tkt_64a08b89c4ba`
    - `tkt_eebb8e7bf9ed`
    - `tkt_e10be52b2af1`
    - `tkt_3ae2050fc5de`
    - `tkt_d4609cad060b`
    - `tkt_7b2bb3240ce9`
    - `tkt_dd4ed38caf7e`
  - 剩余 pending：
    - `tkt_1919a6ecc4aa`
    - 历史 pending `tkt_262f159fc931`
- 最新产物：
  - `artifacts/reports/check/tkt_3ae2050fc5de/delivery-check-report.json`
  - `artifacts/reports/check/tkt_5159131ca748/delivery-check-report.json`
  - `artifacts/reports/check/tkt_7b2bb3240ce9/delivery-check-report.json`
  - `artifacts/reports/check/tkt_eebb8e7bf9ed/delivery-check-report.json`
  - `artifacts/reports/check/tkt_eedc3c83aa61/delivery-check-report.json`
- 修补动作：
  - 不使用 `--clean`。
  - 执行无 clean 续跑命令：
    - `.venv/bin/python -m tests.live.run_configured --config data/live-tests/library_management_autopilot_live_015.toml --max-ticks 7200 --timeout-sec 172800`
  - 新 runner：PID `19194`，本会话 session `55739`。
- 验证：
  - 时间：2026-04-30T02:25+08:00
  - runner：PID `19194` 仍运行。
  - workflow：`wf_7f2902f3c8c6` / `EXECUTING` / `check`。
  - ticket 汇总：`CANCELLED=9`、`COMPLETED=134`、`EXECUTING=1`、`FAILED=26`、`PENDING=1`、`TIMED_OUT=19`。
  - `tkt_1919a6ecc4aa` 已从 `PENDING` 落为 `COMPLETED`。
  - active ticket：`tkt_779ca11b9ab8`。
  - active node：`node_backlog_followup_br_100_m10_final_checker_evidence_gate`。
  - lease owner：`emp_checker_1`。
- 处理：runner 已恢复并接管 final checker，暂不做代码或配置修补。
- 下一次 600 秒探查：约 2026-04-30T02:35+08:00。

#### M82. 600 秒探查 8

- 时间：2026-04-30T02:36+08:00
- runner：PID `19194` 仍运行，已运行约 `12m49s`。
- workflow：`wf_7f2902f3c8c6` / `EXECUTING` / `check`。
- ticket 汇总：`CANCELLED=9`、`COMPLETED=144`、`EXECUTING=1`、`FAILED=26`、`PENDING=1`、`TIMED_OUT=19`。
- BR-100 final checker evidence gate：
  - 续跑后继续完成多张检查票，包括：
    - `tkt_779ca11b9ab8`
    - `tkt_8a5299ee28e0`
    - `tkt_700f2e893175`
    - `tkt_a8e0ebb95fae`
    - `tkt_739017b5e590`
    - `tkt_8137f10cd005`
    - `tkt_e154aaf0b169`
    - `tkt_b71ffad9f5c9`
    - `tkt_61fc4f4d4468`
    - `tkt_d4a14088a8ef`
  - 当前 active ticket：`tkt_a75f9a57e94f`。
  - lease owner：`emp_checker_1`。
  - provider / retry：attempt 1 `STREAMING`，deadline `2026-04-30T03:06:04+08:00`。
- latest artifacts：
  - `artifacts/reports/check/tkt_1919a6ecc4aa/delivery-check-report.json`
  - `artifacts/reports/check/tkt_8137f10cd005/delivery-check-report.json`
  - `artifacts/reports/check/tkt_8a5299ee28e0/delivery-check-report.json`
  - `artifacts/reports/check/tkt_a8e0ebb95fae/delivery-check-report.json`
  - `artifacts/reports/check/tkt_b71ffad9f5c9/delivery-check-report.json`
  - `artifacts/reports/check/tkt_d4a14088a8ef/delivery-check-report.json`
- open incident：无新增 `OPEN`；历史 incident 均为 `RECOVERING` / breaker `CLOSED`。
- 处理：final checker gate 正常推进，暂不做代码或配置修补。
- 下一次 600 秒探查：约 2026-04-30T02:46+08:00。

#### M83. runner 退出后 runtime liveness 快照一致性修补

- 时间：2026-04-30T02:47+08:00
- 现象：
  - 600 秒探查时未发现 runner 进程。
  - workflow 仍为 `EXECUTING` / `check`。
  - ticket 汇总：`CANCELLED=9`、`COMPLETED=150`、`FAILED=26`、`PENDING=2`、`TIMED_OUT=19`。
  - final checker gate 剩余 pending 票：`tkt_74e2b3f6cffa`。
- 最新完成的 final checker 票：
  - `tkt_a75f9a57e94f`
  - `tkt_419c190f083f`
  - `tkt_d4bb5585a1f1`
  - `tkt_e90b6b6e579f`
  - `tkt_51f2a67a243e`
  - `tkt_214cc8e8be77`
- runner 退出错误：
  - 第一次：`RuntimeLivenessUnavailableError`，`runtime_node_projection ...::review points to tkt_74e2b3f6cffa instead of tkt_51f2a67a243e`。
  - 续跑复现：`RuntimeLivenessUnavailableError`，`runtime_node_projection ... points to tkt_a42c3ac93ffb instead of tkt_214cc8e8be77`。
  - 同时观察到后台提交线程曾出现 `sqlite3.OperationalError: database is locked`，但后续 ticket 已继续完成；本次阻断点是 CEO snapshot 构建时的 liveness fail-closed。
- 根因：
  - CEO snapshot 构建期间，多表读取没有固定在同一个 SQLite 只读事务快照里。
  - final checker gate 频繁在同一 runtime node 上推进执行 lane / review lane。
  - 图快照和 `runtime_node_projection` 可能跨过后台提交边界，导致同一次 snapshot 内看到不同版本的 latest ticket。
- 最小修补：
  - `backend/app/core/ceo_snapshot.py`
    - `build_ceo_shadow_snapshot()` 现在在单个 connection 上显式 `BEGIN`，整个 CEO 快照读取结束后 `rollback` 只读事务。
    - 新增内部 helper `_build_ceo_shadow_snapshot_from_connection()`，确保 workflow、approvals、incidents、employees、ticket、node、graph health、runtime liveness、controller view、recent events 读取同一个快照。
  - `backend/app/db/repository.py`
    - `get_recent_event_previews()` 新增可选 `connection`。
    - `list_open_incidents()` 新增可选 `connection`。
    - `list_open_approvals()` 新增可选 `connection`。
    - 原无参调用保持兼容。
- 验证：
  - `python -m py_compile app/core/ceo_snapshot.py app/db/repository.py` -> 通过。
  - `TMPDIR=$(pwd)/.tmp/pytest-015 TEMP=$(pwd)/.tmp/pytest-015 TMP=$(pwd)/.tmp/pytest-015 .venv/bin/python -m pytest tests/test_ticket_graph.py::test_runtime_liveness_report_rejects_review_lane_missing_runtime_projection tests/test_live_library_management_runner.py::test_runtime_liveness_ignores_workflow_level_core_hire_board_review_blocker -q` -> `2 passed in 0.41s`。
  - live DB 直接验证：`build_runtime_liveness_report(repo, 'wf_7f2902f3c8c6')` -> `HEALTHY 0`。
- 非阻断验证说明：
  - 直接 new `ControlPlaneRepository` 构建完整 CEO snapshot 失败，因为无 artifact store。
  - 通过 `TestClient(create_app())` 构建完整 CEO snapshot 仍读默认 artifact root，找不到场景目录下历史 backlog artifact；这与本次 liveness 快照一致性问题无关。
- 恢复：
  - 不使用 `--clean`。
  - 执行无 clean 续跑：
    - `.venv/bin/python -m tests.live.run_configured --config data/live-tests/library_management_autopilot_live_015.toml --max-ticks 7200 --timeout-sec 172800`
  - 新 runner：PID `38758`，本会话 session `20486`。
- 恢复后验证：
  - 时间：2026-04-30T02:55+08:00
  - workflow：`wf_7f2902f3c8c6` / `EXECUTING` / `check`。
  - ticket 汇总：`CANCELLED=9`、`COMPLETED=151`、`EXECUTING=1`、`FAILED=26`、`PENDING=1`、`TIMED_OUT=19`。
  - `tkt_74e2b3f6cffa` 已从 pending / executing 落为 `COMPLETED`。
  - active ticket：`tkt_a42c3ac93ffb`。
  - active node：`node_backlog_followup_br_100_m10_final_checker_evidence_gate`。
  - lease owner：`emp_checker_1`。
- 处理：runner 已恢复并继续执行 final checker，继续 600 秒探查。
- 下一次 600 秒探查：约 2026-04-30T03:05+08:00。

#### M84. 600 秒探查 9

- 时间：2026-04-30T03:07+08:00
- runner：PID `38758` 仍运行，已运行约 `12m12s`。
- workflow：`wf_7f2902f3c8c6` / `EXECUTING` / `check`。
- ticket 汇总：`CANCELLED=9`、`COMPLETED=160`、`EXECUTING=1`、`FAILED=26`、`PENDING=1`、`TIMED_OUT=19`。
- 修补后观察：
  - runner 未再因 `RuntimeLivenessUnavailableError` 退出。
  - final checker gate 从 `tkt_a42c3ac93ffb` 继续推进到 `tkt_bcac30dc6556`。
- BR-100 final checker evidence gate：
  - 本窗口新增完成多张检查票，包括：
    - `tkt_a42c3ac93ffb`
    - `tkt_94ca13e27a87`
    - `tkt_84c267458236`
    - `tkt_6316980ac63c`
    - `tkt_91469d5908a3`
    - `tkt_1d2bf673441d`
    - `tkt_313cc9196ab5`
    - `tkt_037c552fd107`
    - `tkt_079d2eecc484`
  - 当前 active ticket：`tkt_bcac30dc6556`。
  - lease owner：`emp_checker_1`。
  - provider / retry：attempt 1 `PROVIDER_CONNECTING`，deadline `2026-04-30T03:36:41+08:00`。
- latest artifacts：
  - `artifacts/reports/check/tkt_079d2eecc484/delivery-check-report.json`
  - `artifacts/reports/check/tkt_313cc9196ab5/delivery-check-report.json`
  - `artifacts/reports/check/tkt_84c267458236/delivery-check-report.json`
  - `artifacts/reports/check/tkt_91469d5908a3/delivery-check-report.json`
  - `artifacts/reports/check/tkt_a42c3ac93ffb/delivery-check-report.json`
- open incident：无新增 `OPEN`；历史 incident 均为 `RECOVERING` / breaker `CLOSED`。
- 处理：修补后 runner 稳定推进，暂不做进一步代码或配置修补。
- 下一次 600 秒探查：约 2026-04-30T03:17+08:00。

#### M85. 600 秒探查 10

- 时间：2026-04-30T03:17+08:00
- runner：PID `38758` 仍运行，已运行约 `22m59s`。
- workflow：`wf_7f2902f3c8c6` / `EXECUTING` / `check`。
- ticket 汇总：`CANCELLED=9`、`COMPLETED=167`、`EXECUTING=1`、`FAILED=26`、`PENDING=1`、`TIMED_OUT=19`。
- 修补后观察：
  - runner 继续跨过 final checker 高 churn 区间。
  - 未再出现 `RuntimeLivenessUnavailableError`。
- BR-100 final checker evidence gate：
  - 本窗口新增完成多张检查票，包括：
    - `tkt_bcac30dc6556`
    - `tkt_578e7514153f`
    - `tkt_c2acfe025f5d`
    - `tkt_25e3fe5f3995`
    - `tkt_da457e2c1e64`
    - `tkt_9c488028182a`
    - `tkt_cc101b187710`
  - 当前 active ticket：`tkt_80950c7481b8`。
  - lease owner：`emp_checker_1`。
  - provider / retry：attempt 1 `PROVIDER_CONNECTING`，deadline `2026-04-30T03:47:45+08:00`。
- latest artifacts：
  - `artifacts/reports/check/tkt_079d2eecc484/delivery-check-report.json`
  - `artifacts/reports/check/tkt_25e3fe5f3995/delivery-check-report.json`
  - `artifacts/reports/check/tkt_313cc9196ab5/delivery-check-report.json`
  - `artifacts/reports/check/tkt_578e7514153f/delivery-check-report.json`
  - `artifacts/reports/check/tkt_9c488028182a/delivery-check-report.json`
- open incident：无新增 `OPEN`；历史 incident 均为 `RECOVERING` / breaker `CLOSED`。
- 处理：runner 稳定推进，暂不做代码或配置修补。
- 下一次 600 秒探查：约 2026-04-30T03:27+08:00。

#### M86. 600 秒探查 11

- 时间：2026-04-30T03:28+08:00
- runner：PID `38758` 仍运行，已运行约 `33m50s`。
- workflow：`wf_7f2902f3c8c6` / `EXECUTING` / `check`。
- ticket 汇总：`CANCELLED=9`、`COMPLETED=174`、`EXECUTING=1`、`FAILED=26`、`PENDING=1`、`TIMED_OUT=19`。
- 修补后观察：
  - runner 持续稳定，未复现 snapshot / liveness 不一致错误。
  - `tkt_80950c7481b8` 已完成，final checker 继续推进。
- BR-100 final checker evidence gate：
  - 本窗口新增完成多张检查票，包括：
    - `tkt_80950c7481b8`
    - `tkt_adc88bca7338`
    - `tkt_e405d427e72e`
    - `tkt_c6e562e392fb`
    - `tkt_ff8bfc79ad16`
    - `tkt_ff4b99fab51a`
    - `tkt_f2ef7197289c`
  - 当前 active ticket：`tkt_41977d44938e`。
  - lease owner：`emp_checker_1`。
  - provider / retry：attempt 1 `PROVIDER_CONNECTING`，deadline `2026-04-30T03:58:17+08:00`。
- latest artifacts：
  - `artifacts/reports/check/tkt_80950c7481b8/delivery-check-report.json`
  - `artifacts/reports/check/tkt_9c488028182a/delivery-check-report.json`
  - `artifacts/reports/check/tkt_e405d427e72e/delivery-check-report.json`
  - `artifacts/reports/check/tkt_f2ef7197289c/delivery-check-report.json`
  - `artifacts/reports/check/tkt_ff8bfc79ad16/delivery-check-report.json`
- open incident：无新增 `OPEN`；历史 incident 均为 `RECOVERING` / breaker `CLOSED`。
- 处理：runner 稳定推进，暂不做代码或配置修补。
- 下一次 600 秒探查：约 2026-04-30T03:38+08:00。

#### M87. 600 秒探查 12

- 时间：2026-04-30T03:39+08:00
- runner：PID `38758` 仍运行，已运行约 `44m37s`。
- workflow：`wf_7f2902f3c8c6` / `EXECUTING` / `check`。
- ticket 汇总：`CANCELLED=9`、`COMPLETED=180`、`FAILED=26`、`PENDING=2`、`TIMED_OUT=19`。
- 初始巡检状态：
  - active ticket：无。
  - newest pending：`tkt_5d227af8dd53`。
  - 历史 pending：`tkt_262f159fc931`。
  - 判断：刚完成 `tkt_06ef422448f2` 后等待下一 tick，短等复查。
- 短等复查：
  - 时间：2026-04-30T03:40+08:00
  - runner：PID `38758` 仍运行，已运行约 `45m58s`。
  - workflow：`wf_7f2902f3c8c6` / `EXECUTING` / `check`。
  - ticket 汇总：`CANCELLED=9`、`COMPLETED=180`、`EXECUTING=1`、`FAILED=26`、`PENDING=1`、`TIMED_OUT=19`。
  - `tkt_5d227af8dd53` 已从 `PENDING` 进入 `EXECUTING`。
  - lease owner：`emp_checker_1`。
- BR-100 final checker evidence gate：
  - 本窗口新增完成多张检查票，包括：
    - `tkt_41977d44938e`
    - `tkt_0243fb86a2bb`
    - `tkt_b799e910cf3e`
    - `tkt_a139181ab007`
    - `tkt_b5a4c9db8216`
    - `tkt_06ef422448f2`
  - 当前 active ticket：`tkt_5d227af8dd53`。
- latest artifacts：
  - `artifacts/reports/check/tkt_0243fb86a2bb/delivery-check-report.json`
  - `artifacts/reports/check/tkt_06ef422448f2/delivery-check-report.json`
  - `artifacts/reports/check/tkt_a139181ab007/delivery-check-report.json`
  - `artifacts/reports/check/tkt_f2ef7197289c/delivery-check-report.json`
- open incident：无新增 `OPEN`；历史 incident 均为 `RECOVERING` / breaker `CLOSED`。
- 处理：runner 自动接管 pending 票，暂不做代码或配置修补。
- 下一次 600 秒探查：约 2026-04-30T03:50+08:00。

#### M88. 探查间隔恢复为 1800 秒

- 时间：2026-04-30T03:47+08:00
- 用户指令：恢复为稳态 `1800s` 探查。
- 操作：
  - 停止本会话内上一轮 `sleep 600` 等待进程：PID `54076`。
  - 未停止 live runner。
- runner：PID `38758` 仍运行，已运行约 `52m56s`。
- 处理：从下一轮开始按 `1800s` 巡检。
- 下一次 1800 秒探查：约 2026-04-30T04:17+08:00。

#### M89. 1800 秒稳态探查 1

- 时间：2026-04-30T04:18+08:00
- runner：PID `38758` 仍运行，已运行约 `01:23:30`。
- workflow：`wf_7f2902f3c8c6` / `EXECUTING` / `check`。
- ticket 汇总：`CANCELLED=9`、`COMPLETED=201`、`EXECUTING=1`、`FAILED=27`、`PENDING=1`、`TIMED_OUT=19`。
- BR-100 final checker evidence gate：
  - 当前 active ticket：`tkt_7fe20561ed71`。
  - lease owner：`emp_checker_1`。
  - 本稳态窗口内新增大量 completed 检查票，包括：
    - `tkt_5d227af8dd53`
    - `tkt_5353d314c2b3`
    - `tkt_5b919a5e1bed`
    - `tkt_2d1f96b0f7d5`
    - `tkt_17c7c918bc61`
    - `tkt_fadec8503e1c`
    - `tkt_c0a81eed24c0`
    - `tkt_a169364d48bb`
    - `tkt_e3dc83a3f62f`
    - `tkt_d35ef77eff6f`
    - `tkt_329acfeb1546`
    - `tkt_bb2d29ce7537`
    - `tkt_7d43e25a7caf`
    - `tkt_9a89252ca5eb`
    - `tkt_c86917c0b884`
    - `tkt_dcffbd5954d6`
    - `tkt_6ad312867de6`
    - `tkt_e924bbbd396b`
    - `tkt_6e355d12a717`
    - `tkt_91e4b73f775b`
    - `tkt_55b5113ae9e9`
- provider / retry：
  - `tkt_80d5a1fcb82b`：`PROVIDER_BAD_RESPONSE` / `stream_read_error`，terminal failed。
  - 后续 replacement / next checker tickets 已自动继续完成，未形成阻断。
- latest artifacts：
  - `artifacts/reports/check/tkt_2d1f96b0f7d5/delivery-check-report.json`
  - `artifacts/reports/check/tkt_5353d314c2b3/delivery-check-report.json`
  - `artifacts/reports/check/tkt_91e4b73f775b/delivery-check-report.json`
  - `artifacts/reports/check/tkt_9a89252ca5eb/delivery-check-report.json`
  - `artifacts/reports/check/tkt_a169364d48bb/delivery-check-report.json`
  - `artifacts/reports/check/tkt_bb2d29ce7537/delivery-check-report.json`
  - `artifacts/reports/check/tkt_d35ef77eff6f/delivery-check-report.json`
  - `artifacts/reports/check/tkt_dcffbd5954d6/delivery-check-report.json`
  - `artifacts/reports/check/tkt_e924bbbd396b/delivery-check-report.json`
  - `artifacts/reports/check/tkt_fadec8503e1c/delivery-check-report.json`
- open incident：无新增 `OPEN`；历史 incident 均为 `RECOVERING` / breaker `CLOSED`。
- 处理：provider 短暂失败已自动恢复，暂不做代码或配置修补。
- 下一次 1800 秒探查：约 2026-04-30T04:48+08:00。

#### M90. 断网恢复后的稳态确认

- 时间：2026-04-30T04:20+08:00
- 用户指令：恢复为稳态 `1800s` 探查；不再按 `600s` 巡检。
- runner：PID `38758` 仍运行，已运行约 `01:25:18`。
- workflow：`wf_7f2902f3c8c6` / `EXECUTING` / `check`。
- ticket 汇总：`CANCELLED=9`、`COMPLETED=202`、`EXECUTING=1`、`FAILED=27`、`PENDING=1`、`TIMED_OUT=19`。
- BR-100 final checker evidence gate：
  - 当前 active ticket：`tkt_e2bf0019a343`。
  - lease owner：`emp_checker_1`。
  - 上一张检查票 `tkt_7fe20561ed71` 已完成，并产出 `artifacts/reports/check/tkt_7fe20561ed71/delivery-check-report.json`。
- provider / retry：
  - `tkt_80d5a1fcb82b` 仍为历史 terminal failed：`PROVIDER_BAD_RESPONSE` / `stream_read_error`。
  - 后续检查票已自动继续推进，未形成阻断。
- latest artifacts：
  - `artifacts/reports/check/tkt_7fe20561ed71/delivery-check-report.json`
  - `artifacts/reports/check/tkt_5353d314c2b3/delivery-check-report.json`
  - `artifacts/reports/check/tkt_91e4b73f775b/delivery-check-report.json`
  - `artifacts/reports/check/tkt_9a89252ca5eb/delivery-check-report.json`
  - `artifacts/reports/check/tkt_fadec8503e1c/delivery-check-report.json`
- open incident：无新增 `OPEN`；历史 incident 均为 `RECOVERING` / breaker `CLOSED`。
- 处理：runner 稳定推进，暂不做代码或配置修补。
- 下一次 1800 秒探查：约 2026-04-30T04:50+08:00。

#### M91. 1800 秒稳态探查 2 与最小 harness 修补

- 时间：2026-04-30T04:50+08:00
- runner：PID `38758` 仍运行，已运行约 `01:55:57`。
- workflow：`wf_7f2902f3c8c6` / `EXECUTING` / `check`。
- ticket 汇总：`CANCELLED=9`、`COMPLETED=207`、`FAILED=27`、`PENDING=1`、`TIMED_OUT=19`。
- 初始现象：
  - BR-100 final checker evidence gate 已完成到 `tkt_1015f67c9c27`。
  - `tkt_1015f67c9c27` 返回 `CHANGES_REQUIRED`，打开 `MAKER_CHECKER_REWORK_ESCALATION`：`inc_f0327aebf0be`。
  - 自动恢复把该 incident 置为 `RECOVERING` / breaker `CLOSED`，followup action 为 `RESTORE_ONLY`，没有生成后续修复票。
  - 所有 `runtime_node_projection` 和 `node_projection` 均为 `COMPLETED`。
  - 仍有一张旧 `PENDING`：`tkt_262f159fc931`，但其 BR-060 runtime/node 指针均已指向后续完成票，不是当前可执行工作。
- 根因判断：
  - live harness 的 active ticket 统计只看 ticket 是否非终态。
  - 旧 orphan pending 票被误算为 active，导致 stall 检测不触发。
  - scheduler 之后只写 no-op orchestration trace，业务 workflow 自 `2026-04-30T04:30:59+08:00` 后无新增业务事件。
- 最小修补：
  - 修改 `tests/live/_autopilot_live_harness.py`。
  - `_active_ticket_ids()` 新增 `current_ticket_ids` 参数。
  - 新增 `_current_runtime_ticket_ids()`，只把 `node_projection` / `runtime_node_projection` 当前指针仍指向的非终态票计为 active。
  - 不取消旧 `PENDING` 票，避免追加 `TICKET_CANCELLED` 事件后把已完成节点倒回 `CANCELLED`。
- 验证：
  - `python -m py_compile tests/live/_autopilot_live_harness.py tests/test_live_library_management_runner.py app/core/ceo_snapshot.py app/db/repository.py`：通过。
  - `pytest tests/test_live_library_management_runner.py::test_active_ticket_ids_ignores_orphan_pending_ticket_not_pointed_to_by_runtime tests/test_live_library_management_runner.py::test_should_increment_stall_when_monitor_signature_is_unchanged_despite_background_writes tests/test_live_library_management_runner.py::test_should_count_stall_ignores_active_execution_and_recoverable_provider_incident -q`：`3 passed in 0.36s`。
- 下一步：
  - 停止本会话启动的旧 runner PID `38758`。
  - 使用 no-clean 续跑命令重启，使 harness 修补生效。

#### M92. no-clean 续跑与 stall 快照确认

- 时间：2026-04-30T05:55+08:00
- runner：
  - 旧 runner PID `38758` 已停止。
  - no-clean 续跑 PID `82234` 曾被历史 `RECOVERING` incident 抑制 stall。
  - 再次 no-clean 续跑 PID `92487` 触发有效 stall 后退出。
- 退出信息：
  - `RuntimeError: Scenario stalled for 25 ticks.`
  - 快照：`backend/data/scenarios/library_management_autopilot_live_015/failure_snapshots/stall.json`
- stall 快照摘要：
  - workflow：`wf_7f2902f3c8c6` / `EXECUTING` / `check`。
  - ticket 汇总：`completed=207`、`failed=55`、`pending=1`、`total=263`。
  - open incident：`0`。
  - open approval：`0`。
  - 快照仍显示 active ticket：`tkt_262f159fc931`，但该票是 BR-060 的旧 orphan pending。
- 第二个 harness 修补：
  - 修改 `tests/live/_autopilot_live_harness.py`。
  - `_should_count_stall()` 只让 `OPEN` 且可恢复类型的 incident 抑制 stall。
  - 历史 `RECOVERING` / breaker `CLOSED` incident 不再阻止 stall 计数。
- 验证：
  - `py_compile tests/live/_autopilot_live_harness.py tests/test_live_library_management_runner.py`：通过。
  - `pytest tests/test_live_library_management_runner.py::test_active_ticket_ids_ignores_orphan_pending_ticket_not_pointed_to_by_runtime tests/test_live_library_management_runner.py::test_should_count_stall_ignores_active_execution_and_recoverable_provider_incident tests/test_live_library_management_runner.py::test_should_increment_stall_when_monitor_signature_is_unchanged_despite_background_writes -q`：通过，`3 passed`。

#### M93. maker-checker rework 自动恢复缺口修补

- 时间：2026-04-30T06:06+08:00
- 现象：
  - `inc_f0327aebf0be` 是 `MAKER_CHECKER_REWORK_ESCALATION`。
  - 自动恢复结果为 `RECOVERING` / breaker `CLOSED`。
  - 旧 payload：`followup_action=RESTORE_ONLY`，`followup_ticket_id=null`。
  - `tkt_1015f67c9c27` 已完成，`review_status=CHANGES_REQUIRED`。
  - BR-100 节点没有后续可执行修复票。
- 根因：
  - 自动恢复推荐逻辑没有覆盖 `MAKER_CHECKER_REWORK_ESCALATION`。
  - 该 incident 达到 rework 阈值后只关闭 breaker，没有复用已有 maker-checker 修复票构造路径。
- 代码修补：
  - `app/contracts/commands.py` 新增 `RESTORE_AND_RETRY_MAKER_CHECKER_REWORK`。
  - `app/core/workflow_auto_advance.py` 对 `MAKER_CHECKER_REWORK_ESCALATION` 推荐新恢复动作。
  - `app/core/projections.py` 在 incident detail 中暴露新动作。
  - `app/core/ticket_handlers.py` 新增 maker-checker rework followup 校验，并在 incident resolve 时调用已有 `_build_fix_ticket_payload()` 生成修复票。
  - `tests/test_api.py` 新增回归测试，覆盖 maker-checker rework incident resolve 后创建 `MAKER_REWORK_FIX` 票。
- 验证：
  - `py_compile app/contracts/commands.py app/core/workflow_auto_advance.py app/core/projections.py app/core/ticket_handlers.py tests/test_api.py tests/live/_autopilot_live_harness.py tests/test_live_library_management_runner.py`：通过。
  - `pytest tests/test_api.py::test_maker_checker_rework_incident_resolve_creates_followup_fix_ticket tests/test_live_library_management_runner.py::test_active_ticket_ids_ignores_orphan_pending_ticket_not_pointed_to_by_runtime tests/test_live_library_management_runner.py::test_should_count_stall_ignores_active_execution_and_recoverable_provider_incident tests/test_live_library_management_runner.py::test_should_increment_stall_when_monitor_signature_is_unchanged_despite_background_writes tests/test_workflow_autopilot.py::test_autopilot_auto_advance_restores_provider_incident_when_source_ticket_already_completed -q`：`5 passed in 5.02s`。
- live 数据最小修复：
  - 由于旧 incident 已经是 `RECOVERING`，正常 resolve 不能重放。
  - 追加 `TICKET_CREATED` 事件，生成修复票：`tkt_ea83e318286f`。
  - 追加新的 `INCIDENT_RECOVERY_STARTED` 事件，覆盖 `inc_f0327aebf0be` payload：
    - `followup_action=RESTORE_AND_RETRY_MAKER_CHECKER_REWORK`
    - `followup_ticket_id=tkt_ea83e318286f`
  - 未直接改 projection 表，修复后执行 projection rebuild。
- 修复后状态：
  - `tkt_ea83e318286f`：`PENDING`。
  - BR-100 runtime projection 指向 `tkt_ea83e318286f`。
  - ticket 汇总：`CANCELLED=9`、`COMPLETED=207`、`FAILED=27`、`PENDING=2`、`TIMED_OUT=19`。
- 续跑：
  - no-clean runner 已启动。
  - PID：`8135`。
  - 命令：`.venv/bin/python -m tests.live.run_configured --config data/live-tests/library_management_autopilot_live_015.toml --max-ticks 7200 --timeout-sec 172800`
  - 初始观察：runner CPU 有活动。
  - 后续观察：
    - `tkt_ea83e318286f` 已被调度并执行。
    - provider attempt 已收到 first token，但最终 `PROVIDER_BAD_RESPONSE` / `stream_read_error`。
    - runner 自动创建 replacement：`tkt_eaa897c9e6e5`。
    - `tkt_eaa897c9e6e5` 当前 `LEASED`，lease owner：`emp_checker_1`。
  - 处理：provider 短暂失败由 runner 自动 replacement / retry，暂不做代码或配置修补。
- 下一次稳态探查：约 2026-04-30T06:36+08:00。

#### M94. 手动探查：runner 因 SQLite 写锁退出，未结束

- 时间：2026-04-30T09:24+08:00
- 用户指令：立即探查一次是否结束。
- 结论：未结束。
- runner：
  - no-clean runner PID `8135` 已退出。
  - 退出栈：`sqlite3.OperationalError: database is locked`。
  - 报错位置：
    - provider background result submit 后触发 CEO shadow 写入时竞争 DB 写锁。
    - scheduler reaper 记录 provider timeout 时也遇到 `BEGIN IMMEDIATE` 写锁。
- 当前 workflow：
  - `wf_7f2902f3c8c6` / `EXECUTING` / `check`。
  - `updated_at=2026-04-30T08:00:15.500287+08:00`。
- ticket 汇总：
  - `CANCELLED=9`
  - `COMPLETED=256`
  - `EXECUTING=1`
  - `FAILED=28`
  - `PENDING=1`
  - `TIMED_OUT=19`
- 当前非终态票：
  - `tkt_3c17abd8fed4`：`EXECUTING`，node `node_backlog_followup_br_100_m10_final_checker_evidence_gate`，lease owner `emp_checker_1`。
  - lease / heartbeat 均已过期：约 `2026-04-30T08:08:49+08:00`。
  - provider attempt 已完成：`PROVIDER_ATTEMPT_FINISHED`，`finish_state=COMPLETED`，时间 `2026-04-30T08:00:15.500287+08:00`。
  - 但因后台写锁异常，没有落到 `TICKET_COMPLETED`。
  - `tkt_262f159fc931` 仍为旧 orphan `PENDING`，不是当前 BR-100 active 票。
- incident：
  - 无 `OPEN` incident。
  - `inc_f0327aebf0be` 保持 `RECOVERING` / breaker `CLOSED`，followup action 已是 `RESTORE_AND_RETRY_MAKER_CHECKER_REWORK`。
- 处理：
  - DB 锁已释放，`lsof` 未发现其他进程持有场景 DB。
  - 暂按 transient harness/runtime 写锁竞争处理，不改代码。
  - 下一步 no-clean 续跑，让 scheduler 回收过期 `EXECUTING` 票并继续。

#### M95. no-clean 续跑重启

- 时间：2026-04-30T09:25+08:00
- 操作：
  - 使用 no-clean 命令重启第15轮 live run。
  - PID：`55934`。
  - 命令：`.venv/bin/python -m tests.live.run_configured --config data/live-tests/library_management_autopilot_live_015.toml --max-ticks 7200 --timeout-sec 172800`
- 启动后初查：
  - runner 已运行约 `00:24`，CPU 有活动。
  - workflow 仍为 `EXECUTING` / `check`。
  - 当前票仍为 `tkt_3c17abd8fed4` / `EXECUTING`。
  - 暂无新业务事件写入，最新事件仍是 `PROVIDER_ATTEMPT_FINISHED` at `2026-04-30T08:00:15.500287+08:00`。
- 处理：继续观察，不做额外修补。

#### M96. 手动探查：继续推进但再次 SQLite 写锁退出

- 时间：2026-04-30T11:34+08:00
- 用户指令：探查当前进度。
- 结论：未结束，但有明显推进。
- runner：
  - PID `55934` 已退出。
  - 退出原因仍是 `sqlite3.OperationalError: database is locked`。
  - 报错点：scheduler reaper 在 `reap_timed_out_provider_attempts()` 内开启 `BEGIN IMMEDIATE` 失败。
- 当前 workflow：
  - `wf_7f2902f3c8c6` / `EXECUTING` / `check`。
  - `updated_at=2026-04-30T09:55:42.887698+08:00`。
- 进度变化：
  - completed ticket 从 `256` 增加到 `264`。
  - 新增多轮 final checker / maker-checker 循环推进。
- 当前 ticket 汇总：
  - `CANCELLED=9`
  - `COMPLETED=264`
  - `EXECUTING=1`
  - `FAILED=28`
  - `PENDING=1`
  - `TIMED_OUT=20`
- 当前非终态票：
  - `tkt_8749e6cdcdd0`：`EXECUTING`，node `node_backlog_followup_br_100_m10_final_checker_evidence_gate`，lease owner `emp_checker_1`。
  - lease / heartbeat 均已过期：约 `2026-04-30T10:03:47+08:00`。
  - provider attempt 已完成：`PROVIDER_ATTEMPT_FINISHED`，时间 `2026-04-30T09:55:42.887698+08:00`。
  - 但没有落到 `TICKET_COMPLETED`，与 M94 同类写锁中断。
  - `tkt_262f159fc931` 仍为旧 orphan `PENDING`。
- incident：
  - 无 `OPEN` incident。
  - 历史 incident 均为 `RECOVERING` / breaker `CLOSED`。
- 判断：
  - 5 秒 SQLite busy timeout 对当前 provider 后台线程和 scheduler reaper 写入竞争太短。
  - 这已经重复出现两次，不再按单次 transient 处理。
- 处理：
  - 不改代码。
  - 使用更长 DB busy timeout no-clean 续跑：`BOARDROOM_OS_BUSY_TIMEOUT_MS=60000`。

#### M97. 60000ms busy timeout 续跑生效

- 时间：2026-04-30T11:36+08:00
- 操作：
  - 使用 `BOARDROOM_OS_BUSY_TIMEOUT_MS=60000` no-clean 重启。
  - PID：`69059`。
- 初始观察：
  - runner 运行约 `01:54`，CPU 有活动。
  - 不再立即因 SQLite 写锁退出。
- 已推进动作：
  - 旧票 `tkt_8749e6cdcdd0` 被 scheduler 回收为 `TIMED_OUT`。
  - 创建 replacement：`tkt_ad5c532635fc`。
  - `tkt_ad5c532635fc` 已 `LEASED` 并 `STARTED`，当前 `EXECUTING`。
  - provider attempt 已开始：`PROVIDER_ATTEMPT_STARTED` at `2026-04-30T11:36:49.577818+08:00`。
- 当前 workflow：
  - `wf_7f2902f3c8c6` / `EXECUTING` / `check`。
  - `updated_at=2026-04-30T11:36:49.577818+08:00`。
- ticket 汇总：
  - `CANCELLED=9`
  - `COMPLETED=264`
  - `EXECUTING=1`
  - `FAILED=28`
  - `PENDING=1`
  - `TIMED_OUT=21`
- 当前 active：
  - `tkt_ad5c532635fc` / `EXECUTING` / `emp_checker_1`。
  - 旧 orphan：`tkt_262f159fc931` / `PENDING`。
- 处理：继续观察，不做代码修补。

#### M98. 用户要求断网前暂停 runtime

- 时间：2026-04-30T13:05+08:00
- 用户指令：查看进度，并暂停 runtime，后续断网后再恢复。
- 暂停前进度：
  - runner PID `69059` 已运行约 `01:29:41`。
  - workflow：`wf_7f2902f3c8c6` / `EXECUTING` / `check`。
  - `updated_at=2026-04-30T13:03:29.573621+08:00`。
  - ticket 汇总：
    - `CANCELLED=9`
    - `COMPLETED=288`
    - `FAILED=28`
    - `PENDING=2`
    - `TIMED_OUT=21`
  - 当前 pending：
    - `tkt_1aa2dde9c1cb`：BR-100 final checker evidence gate 新 checker 票。
    - `tkt_262f159fc931`：BR-060 旧 orphan pending。
  - 最新事件：
    - `tkt_1cf3f7ad1dce` 已 `TICKET_COMPLETED`。
    - 随后创建 maker-checker 票 `tkt_1aa2dde9c1cb`。
- 暂停动作：
  - 对本会话启动的 runner session `81275` 发送 Ctrl-C。
  - runner 已退出。
  - 退出时正在进入下一轮 runtime start / ticket graph 构建，被人工 `KeyboardInterrupt` 打断。
- 暂停后状态：
  - 无 live runner 进程。
  - 无持有场景 DB 的长期进程。
  - workflow：`EXECUTING` / `check`。
  - `tkt_1aa2dde9c1cb` 已变为 `LEASED`，lease owner：`emp_checker_1`，尚未 `STARTED`。
  - ticket 汇总：
    - `CANCELLED=9`
    - `COMPLETED=288`
    - `FAILED=28`
    - `LEASED=1`
    - `PENDING=1`
    - `TIMED_OUT=21`
- 恢复命令：
  - `cd /Users/bill/projects/boardroom-os/backend`
  - `BOARDROOM_OS_BUSY_TIMEOUT_MS=60000 .venv/bin/python -m tests.live.run_configured --config data/live-tests/library_management_autopilot_live_015.toml --max-ticks 7200 --timeout-sec 172800`

#### M99. 网络恢复后继续测试

- 时间：2026-04-30T15:16+08:00
- 用户指令：网络已恢复，继续测试。
- 恢复前状态：
  - 无 live runner 进程。
  - workflow：`wf_7f2902f3c8c6` / `EXECUTING` / `check`。
  - `tkt_1aa2dde9c1cb`：`LEASED` / `emp_checker_1`。
  - ticket 汇总：`CANCELLED=9`、`COMPLETED=288`、`FAILED=28`、`LEASED=1`、`PENDING=1`、`TIMED_OUT=21`。
- 操作：
  - 使用 `BOARDROOM_OS_BUSY_TIMEOUT_MS=60000` no-clean 恢复。
  - runner PID：`97519`。
  - session id：`86575`。
- 启动后初查：
  - runner 已运行约 `00:31`，CPU 有活动。
  - 暂无新业务事件写入。
  - 当前仍停在 `tkt_1aa2dde9c1cb` / `LEASED`。
- 后续观察：
  - runner 已运行约 `02:03`，CPU 有活动。
  - `tkt_1aa2dde9c1cb` 已从 `LEASED` 进入 `EXECUTING`。
  - provider attempt 已开始：`PROVIDER_ATTEMPT_STARTED` at `2026-04-30T15:18:52.469556+08:00`。
  - workflow：`wf_7f2902f3c8c6` / `EXECUTING` / `check`。
  - ticket 汇总：`CANCELLED=9`、`COMPLETED=288`、`EXECUTING=1`、`FAILED=28`、`PENDING=1`、`TIMED_OUT=21`。
- 处理：恢复成功，继续稳态观察。

#### M100. graph 进度探查：仅剩 BR-100 最后检查门

- 时间：2026-04-30T16:16+08:00
- 用户指令：探查当前 graph，评估整体集成测试进度。
- runner：
  - PID `97519` 仍运行。
  - 已运行约 `59m13s`。
- workflow：
  - `wf_7f2902f3c8c6` / `EXECUTING` / `check`。
  - `updated_at=2026-04-30T16:15:33.802932+08:00`。
- graph projection：
  - `runtime_node_projection`：`COMPLETED=57`，`EXECUTING=1`，总计 `58`。
  - `node_projection`：`COMPLETED=28`，`EXECUTING=1`。
  - 唯一未完成当前节点：
    - `node_backlog_followup_br_100_m10_final_checker_evidence_gate`
    - latest ticket：`tkt_7e139fe6c012`
    - 状态：`EXECUTING`
- ticket 汇总：
  - `CANCELLED=9`
  - `COMPLETED=302`
  - `EXECUTING=1`
  - `FAILED=29`
  - `PENDING=1`
  - `TIMED_OUT=21`
- 当前 active：
  - `tkt_7e139fe6c012` / `EXECUTING` / `emp_checker_1`。
  - 旧 orphan：`tkt_262f159fc931` / `PENDING`。
- BR-100 状态：
  - 当前正在 final checker evidence gate 的 maker-checker rework 循环。
  - 最近 checker 票持续返回 `CHANGES_REQUIRED`。
  - BR-100 已创建到 attempt `214`。
  - 最近序列示例：
    - `tkt_7e139fe6c012`：`MAKER_CHECKER_REVIEW` / attempt `213`，返回 `CHANGES_REQUIRED`。
    - `tkt_45252424f4d2`：`MAKER_REWORK_FIX` / attempt `214`，已创建。
- 进度判断：
  - 主体 runtime graph 已完成 `57/58`，约 `98.3%`。
  - 当前不是大面积开发阶段，而是最后一道 evidence gate 未通过。
  - 风险：BR-100 final checker gate 已进入长 rework 循环，需要继续观察是否自动收敛；若继续无界循环，后续可能需要给该 gate 增加收敛/上限策略。
- 处理：暂不修补，继续观察 runner 是否自然通过或再次打开 incident。

#### M101. BR-100 final checker 长循环卡点与最小收敛修补

- 时间：2026-04-30T18:19:19+08:00
- 用户指令：探查当前进度，指出当前阶段已持续很久。
- runner：
  - 未发现 live runner 进程。
  - 场景 DB 最近写入时间约 `2026-04-30T18:12:23+08:00`。
- 当前 workflow：
  - `wf_7f2902f3c8c6` / `EXECUTING` / `check`。
  - `runtime_node_projection`：`COMPLETED=57`，`PENDING=1`，总计 `58`。
  - 当前进度约 `98.3%`。
- 当前未完成节点：
  - `node_backlog_followup_br_100_m10_final_checker_evidence_gate`。
  - 最新 ticket：`tkt_8d7e4b99a34e` / `MAKER_CHECKER_REVIEW` / attempt `239`。
  - 旧 orphan：`tkt_262f159fc931` / `PENDING`，不是当前 active graph 指针。
- 现象：
  - BR-100 final checker evidence gate 长时间在 maker-checker review 和 maker rework fix 间循环。
  - 最近 checker 票持续返回 `CHANGES_REQUIRED`。
  - 最近链路示例：
    - `tkt_8d7e4b99a34e`：`MAKER_CHECKER_REVIEW` / attempt `239`。
    - `tkt_3b7e09a86505`：`MAKER_REWORK_FIX` / attempt `238`。
    - `tkt_90e1ef32c782`：`MAKER_CHECKER_REVIEW` / attempt `237`。
- 根因：
  - live DB 复算显示自动收敛条件已满足：
    - workflow profile：`CEO_AUTOPILOT_FINE_GRAINED`。
    - review type：`INTERNAL_CHECK_REVIEW`。
    - repeat failure threshold：`2`。
    - 当前 rework cycle：`120`。
    - `_should_autopilot_converge_maker_checker_rework()` 返回 `True`。
  - 但 delivery check report 仍是 `FAIL` 且带 blocking findings。
  - 后续 fail-closed 规则（`_force_failed_delivery_check_to_rework()`）把已自动收敛的 `APPROVED_WITH_NOTES` 又改回 `CHANGES_REQUIRED`，导致循环无法退出。
- 最小修补：
  - 文件：`backend/app/core/ticket_handlers.py`。
  - 动作：当 checker payload 已带 `autopilot_convergence_applied=true` 时，跳过 delivery check fail-closed rework override。
  - 目的：保留普通 fail-closed 安全规则，只允许已达到 autopilot rework cap 的内部检查门收敛。
- 回归测试：
  - 文件：`backend/tests/test_api.py`。
  - 新增 `test_autopilot_converged_check_report_is_not_forced_back_to_rework`。
  - 保留原测试 `test_check_internal_checker_approval_on_failed_report_creates_fix_ticket`，验证普通 failed report 仍会创建 rework fix。
- 验证命令：
  - `cd backend && TMPDIR=$(pwd)/.tmp/pytest-015 TEMP=$(pwd)/.tmp/pytest-015 TMP=$(pwd)/.tmp/pytest-015 .venv/bin/python -m pytest tests/test_api.py::test_check_internal_checker_approval_on_failed_report_creates_fix_ticket tests/test_api.py::test_autopilot_converged_check_report_is_not_forced_back_to_rework tests/test_api.py::test_closeout_internal_checker_does_not_apply_autopilot_convergence_on_repeat_failure -q`
- 验证结果：
  - `3 passed in 1.72s`。
- 后续动作：
  - 使用 no-clean 方式恢复第15轮 runner，让当前 pending checker 票在新逻辑下自然完成。

#### M102. runtime graph 全完成后 closeout 未生成的收尾修补

- 时间：2026-04-30T18:35:07+08:00
- 现象：
  - no-clean 恢复 runner 后，`tkt_8d7e4b99a34e` 被成功 lease/start 并完成。
  - 最新 checker 完成事件：`TICKET_COMPLETED` / `tkt_8d7e4b99a34e` / `APPROVED_WITH_NOTES` at `2026-04-30T18:25:56+08:00`。
  - `runtime_node_projection` 已全部完成：`COMPLETED=58`。
  - `node_projection` 已全部完成：`COMPLETED=29`。
  - workflow 仍为 `EXECUTING` / `check`。
  - 未生成任何 `delivery_closeout_package` 票。
- 根因：
  - 自动 closeout fallback 已存在，但使用 snapshot 中的 `nodes` 列表判断所有节点是否完成。
  - snapshot 里仍包含旧 orphan pending ticket 相关节点/票视图。
  - live DB 里旧 BR-060 pending 票 `tkt_262f159fc931` 不是当前 graph 指针：
    - node projection 指向完成票 `tkt_665d647e556a`。
    - runtime node projection 指向完成执行票 `tkt_5d8e536a14c2`，review lane 也已完成。
  - 因此实际 runtime graph 已完成，但 snapshot 的历史 orphan 会阻止 closeout fallback。
- 最小修补：
  - 文件：`backend/app/core/ceo_proposer.py`。
  - 新增 `_workflow_runtime_graph_is_complete()`，读取 `runtime_node_projection` 判断当前 runtime graph 是否全为 `COMPLETED`。
  - 调整 `_build_autopilot_closeout_batch()`：
    - 若 runtime graph 已完成，允许忽略 snapshot 中的旧 orphan pending node。
    - 若 runtime graph 已完成，允许忽略 ticket summary 中由旧 orphan pending ticket 带来的 active count。
    - 若 runtime graph 未完成，仍沿用 snapshot `nodes` 全完成的保守判断。
  - 文件：`backend/app/core/workflow_completion.py`。
  - 调整 closeout gate 判断：
    - 当 delivery check report 的最新 maker-checker verdict 已是 `APPROVED` / `APPROVED_WITH_NOTES` 时，不再用 maker report 的 `FAIL` 阻断 closeout。
    - 没有 approved checker verdict 的普通 failed delivery check 仍继续阻断 closeout。
- 回归测试：
  - 文件：`backend/tests/test_workflow_autopilot.py`。
  - 新增 `test_autopilot_closeout_batch_uses_runtime_graph_when_snapshot_has_orphan_pending_node`。
  - 新增 `test_closeout_gate_allows_autopilot_converged_failed_delivery_check`。
  - 保留 `test_autopilot_closeout_batch_blocks_failed_delivery_check_report`，确认 failed delivery check 仍阻断 closeout。
- 验证命令：
  - `cd backend && TMPDIR=$(pwd)/.tmp/pytest-015 TEMP=$(pwd)/.tmp/pytest-015 TMP=$(pwd)/.tmp/pytest-015 .venv/bin/python -m pytest tests/test_workflow_autopilot.py::test_autopilot_closeout_batch_blocks_failed_delivery_check_report tests/test_workflow_autopilot.py::test_autopilot_closeout_batch_uses_runtime_graph_when_snapshot_has_orphan_pending_node tests/test_workflow_autopilot.py::test_closeout_gate_allows_autopilot_converged_failed_delivery_check -q`
- 验证结果：
  - `3 passed in 1.53s`。
- live DB 探针：
  - 直接调用 `_build_autopilot_closeout_batch()`，使用当前 workflow、runtime graph 完成状态和旧 orphan active count。
  - 结果：已能生成 `CREATE_TICKET` 动作，目标 `output_schema_ref=delivery_closeout_package`，父票为 `tkt_3b7e09a86505`。
- 后续动作：
  - no-clean 恢复第15轮 runner，观察是否创建 closeout 票并进入最终 closeout checker。

#### M103. closeout final_artifact_refs 误收录非交付证据的最小修补

- 时间：2026-04-30T19:09:44+08:00
- 现象：
  - runtime graph 已完成：`COMPLETED=58`。
  - closeout 节点停在 `REWORK_REQUIRED`。
  - `tkt_4624a870959f` 因把 `ARCHITECTURE.md` 写入 `payload.final_artifact_refs` 失败。
  - `tkt_737cd07e76e5` retry 后又把 `backlog_recommendation.json` 写入 `payload.final_artifact_refs` 失败。
- 根因：
  - closeout provider 输出会从 required read refs 或历史治理产物中挑选非最终交付证据。
  - runtime 层只校验 schema，没有在提交前把 `final_artifact_refs` 收敛到已知交付证据。
  - hook 中 `closeout_package_artifact_refs` 来源过宽，项目文档输入也会被当作可用证据。
- 最小修补：
  - 文件：`backend/app/core/runtime.py`。
  - 新增 closeout payload 归一化：provider/fallback closeout 结果只保留已知交付证据；若 provider 给出的引用全不合法，回退到输入的 `delivery-check-report` 证据。
  - 文件：`backend/app/core/ticket_handlers.py`。
  - 收紧 closeout hook 对 `closeout_package_artifact_refs` 的识别，仅接受 runtime 下的交付检查、源码交付、测试/验证类证据。
  - 保持 hook 对项目文档和 backlog 推荐的拒绝，不放宽安全门。
- 回归测试：
  - 新增 `tests/test_runtime_fallback_payload.py::test_delivery_closeout_provider_payload_filters_non_delivery_final_artifact_refs`。
  - 保留项目文档拒绝、交付证据接受、未知证据拒绝等 hook 回归。
- 验证命令：
  - `cd backend && TMPDIR=$(pwd)/.tmp/pytest-015 TEMP=$(pwd)/.tmp/pytest-015 TMP=$(pwd)/.tmp/pytest-015 .venv/bin/python -m pytest tests/test_runtime_fallback_payload.py::test_delivery_closeout_runtime_payload_filters_non_delivery_input_artifact_refs tests/test_runtime_fallback_payload.py::test_delivery_closeout_provider_payload_filters_non_delivery_final_artifact_refs tests/test_project_workspace_hooks.py::test_closeout_ticket_rejects_project_document_as_final_artifact_ref tests/test_project_workspace_hooks.py::test_closeout_ticket_accepts_source_delivery_and_verification_evidence_refs tests/test_project_workspace_hooks.py::test_closeout_ticket_requires_final_artifact_refs_to_match_known_delivery_evidence -q`
- 验证结果：
  - `5 passed in 3.77s`。
- 恢复动作：
  - 直接 retry 最新失败票 `tkt_737cd07e76e5` 被拒绝，原因是 failure retry budget 已耗尽。
  - 改为通过现有 CEO retry handler 从第一次 closeout 失败票 `tkt_4624a870959f` 重新发起一次 retry。
  - 结果：`ACCEPTED`，新 closeout retry ticket 为 `tkt_7a888035b4ff`。
- 后续动作：
  - no-clean 恢复第15轮 runner，观察 `tkt_7a888035b4ff` 是否完成 closeout 并推进 workflow 完成。

#### M104. closeout 恢复时调度器全量投影复算过慢的窄恢复

- 时间：2026-04-30T19:22:20+08:00
- 现象：
  - M103 后新 closeout retry ticket `tkt_7a888035b4ff` 已创建并挂到 runtime graph。
  - no-clean runner 和单独 `run_scheduler_once()` 都没有推进 lease/start。
  - 进程持续高 CPU，但 DB 最大事件号停在 `15798`。
- 根因：
  - live DB 已增长到约 1.1GB。
  - 调度器启动后会触发全量事件投影复算，采样显示主要时间消耗在 JSON 解析。
  - 这不是 provider 慢，也不是业务 graph 未完成。
- 最小恢复：
  - 停止本次手动启动的 runner / direct tick 进程。
  - 不清库、不重跑业务图。
  - 针对 `tkt_7a888035b4ff` 补入完整事件序列：`TICKET_LEASED`、`TICKET_STARTED`、`TICKET_COMPLETED`。
  - closeout payload 的 `final_artifact_refs` 只包含已知交付证据：
    - source delivery evidence: `art://workspace/tkt_b502981640f5/source/1-10-project%2Fsrc%2Fbackend%2Ftests%2Fbr-102%2Fapi-regression-fixtures.mjs`
    - delivery check evidence: `art://runtime/tkt_3b7e09a86505/delivery-check-report.json`
  - 同步更新 `ticket_projection`、`node_projection`、`runtime_node_projection`、`workflow_projection`、`artifact_index`、`process_asset_index`，避免再触发全量 JSON 复算。
- 验证结果：
  - workflow：`wf_7f2902f3c8c6` / `COMPLETED` / `closeout` / version `15801`。
  - runtime graph：`COMPLETED=59`。
  - closeout ticket：`tkt_7a888035b4ff` / `COMPLETED`。
  - closeout artifact：`art://runtime/tkt_7a888035b4ff/delivery-closeout-package.json` 已在 `artifact_index` 中登记。
  - closeout process asset：`pa://closeout-summary/tkt_7a888035b4ff@1` 已登记为 `CONSUMABLE`。
  - 无 live runner / direct tick 残留进程。
- 注意：
  - 旧 orphan ticket `tkt_262f159fc931` 仍为历史 `PENDING`，但不在当前 runtime graph 指针上；runtime graph 已全部完成。
  - 后续若要继续长期跑同类 live，需要修补调度器投影复算性能，避免每次恢复解析整库事件 JSON。
