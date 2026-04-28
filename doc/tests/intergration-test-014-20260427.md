# Intergration Test 014 审计日志

## 基本信息

- 日期：2026-04-27
- 测试轮次：014
- 场景 slug：`library_management_autopilot_live_014`
- 测试配置：`backend/data/live-tests/library_management_autopilot_live_014.toml`
- 后端留档副本：`backend/library_management_autopilot_live_014.toml`
- 配置来源：以 `backend/integration-tests.template.toml` 为骨架，按 `backend/library-mgmt-prd.md` 完整 PRD 扩展
- base_url：`http://codex.truerealbill.com:11234/v1`
- API key：已按用户提供值写入测试配置；本文档不记录明文密钥
- 运行入口：`backend/.venv/bin/python -m tests.live.run_configured --config data/live-tests/library_management_autopilot_live_014.toml --clean --max-ticks 1200 --timeout-sec 64800`
- 监控策略：本会话内每 1800 秒检查一次 `backend/data/scenarios/library_management_autopilot_live_014/` 下的 `integration-monitor-report.md`、`run_report.json`、`audit-summary.md` 与当前 incident / ticket 状态

## 模型绑定

- 默认模型：`gpt-5.4` / `high`
- CEO：`gpt-5.5` / `high`
- 架构/分析：`architect_primary`、`cto_primary`、`checker_primary` 使用 `gpt-5.5` / `xhigh`
- 开发：`frontend_engineer_primary`、`backend_engineer_primary`、`database_engineer_primary`、`platform_sre_primary` 使用 `gpt-5.4` / `high`
- UI 设计：`ui_designer_primary` 使用 `gpt-5.4` / `high`

## 运行参数

- `budget_cap = 6000000`
- `runtime.seed = 17`
- `runtime.max_ticks = 1200`
- `runtime.timeout_sec = 64800`
- `provider.connect_timeout_sec = 10`
- `provider.write_timeout_sec = 30`
- `provider.first_token_timeout_sec = 300`
- `provider.stream_idle_timeout_sec = 600`
- `provider.max_context_window = 270000`

## 执行记录

### E00. 配置落地

- 目标：生成 `014` live TOML，并复制到 `backend/` 根目录留档。
- 状态：完成
- 备注：配置沿用 `013` 的 PRD-embedded constraints 结构，但把运行预算、角色模型绑定和 timeout 放大到本轮方案要求。
- 主配置：`backend/data/live-tests/library_management_autopilot_live_014.toml`
- 留档副本：`backend/library_management_autopilot_live_014.toml`
- 副本校验：`diff -u backend/data/live-tests/library_management_autopilot_live_014.toml backend/library_management_autopilot_live_014.toml` 无差异

### E01. 静态校验

- `TMPDIR=$(pwd)/.tmp/pytest-014 TEMP=$(pwd)/.tmp/pytest-014 TMP=$(pwd)/.tmp/pytest-014 .venv/bin/python -m pytest tests/test_scenario_config.py -q`
  - 结果：`5 passed in 0.02s`
- `TMPDIR=$(pwd)/.tmp/pytest-014 TEMP=$(pwd)/.tmp/pytest-014 TMP=$(pwd)/.tmp/pytest-014 .venv/bin/python -m pytest tests/test_live_configured_runner.py -q`
  - 结果：`11 passed in 0.24s`

### E02. Live run

- 已启动：`tests.live.run_configured --config data/live-tests/library_management_autopilot_live_014.toml --clean --max-ticks 1200 --timeout-sec 64800`
- 启动方式：当前会话内长进程，进入调度循环后继续监控
- 2026-04-28T01:18+08:00：P02 修补后，已用同一命令 `--clean` 重启；旧场景目录已备份

### E03. 监控

- 待执行：进入稳态后每 1800 秒记录一次
- 记录字段：时间、workflow/tick、当前阶段、open incident、active ticket、最新修补、是否续跑

#### M00. 初始状态

- 时间：2026-04-27T23:44+08:00
- workflow：`wf_80100a48d705`
- current_stage：`plan`
- workflow status：`EXECUTING`
- ticket 汇总：`EXECUTING=1`
- active ticket：`tkt_wf_80100a48d705_ceo_architecture_brief`
- open incident：无
- 场景目录：`backend/data/scenarios/library_management_autopilot_live_014`

#### M01. 初始推进

- 时间：2026-04-27T23:49+08:00
- workflow：`wf_80100a48d705`
- current_stage：`project_init`
- workflow status：`EXECUTING`
- ticket 汇总：`COMPLETED=3`、`PENDING=1`
- 已产出：`architecture_brief.json`、`technology_decision.json`
- open incident：无
- 失败 ticket：无
- 判断：runner 正在推进，暂不修补

#### M02. 首份监控报告

- 时间：2026-04-27T23:52+08:00
- workflow：`wf_80100a48d705`
- monitor：`backend/data/scenarios/library_management_autopilot_live_014/integration-monitor-report.md`
- monitor 记录：`EXECUTING / project_init`
- tickets：`6`
- active ticket：`tkt_c87921fc913c`
- open incident：无
- provider：`prov_openai_compat_truerealbill`，attempt `1`，phase `completed`，elapsed `95.39`
- 已产出：`milestone_plan.json`
- 判断：进入可监控稳态，后续按 1800 秒节奏记录；中途若出现 incident 或失败票，立即插入问题记录

#### M03. 1800 秒例行检查 1

- 时间：2026-04-28T00:22+08:00
- workflow：`wf_80100a48d705`
- current_stage：`build`
- workflow status：`EXECUTING`
- ticket 汇总：`COMPLETED=12`、`EXECUTING=1`、`LEASED=1`
- active / leased ticket：`tkt_23d92cfbc59d`、`tkt_d25c7f86ea0a`
- 最新节点：`node_backlog_followup_impl_m1_sqlite_schema_seed`、`node_backlog_followup_impl_m1_project_runtime_foundation`
- open incident：无
- 失败 ticket：无
- monitor 记录：00:06 进入 `build` 阶段，active tickets 为 `tkt_d25c7f86ea0a, tkt_23d92cfbc59d`
- 判断：已进入实现 fanout，暂无修补动作

#### M04. 1800 秒例行检查 2

- 时间：2026-04-28T00:52+08:00
- workflow：`wf_80100a48d705`
- current_stage：`build`
- workflow status：`EXECUTING`
- ticket 汇总：`COMPLETED=16`、`EXECUTING=1`、`FAILED=1`
- active ticket：`tkt_02c0b79be605`
- failed ticket：`tkt_d25c7f86ea0a`
- failed reason：`PROVIDER_BAD_RESPONSE / stream_read_error`
- open incident：无
- monitor 记录：00:39 出现 33 分 32 秒静默后恢复；provider attempt `6` completed；后续 replacement 票继续推进
- 判断：provider 流中断已被 replacement / retry 路径覆盖，workflow 继续执行；暂不做代码修补

#### M05. P02 修补后重启

- 时间：2026-04-28T01:19+08:00
- workflow：`wf_1228997413c5`
- current_stage：`plan`
- workflow status：`EXECUTING`
- ticket 汇总：`EXECUTING=1`
- active ticket：`tkt_wf_1228997413c5_ceo_architecture_brief`
- open incident：无
- 判断：第 14 轮已用修补后的代码重启，继续观察到稳态后恢复 1800 秒节奏

#### M06. 重启后稳态确认

- 时间：2026-04-28T01:27+08:00
- workflow：`wf_1228997413c5`
- current_stage：`plan`
- workflow status：`EXECUTING`
- ticket 汇总：`COMPLETED=4`、`EXECUTING=1`
- active ticket：`tkt_6d7459c3890f`
- open incident：无
- failed ticket：无
- monitor 记录：暂未生成 `integration-monitor-report.md`
- 判断：重启后已稳定进入计划阶段；继续等待 runner 推进

#### M07. monitor report 已生成

- 时间：2026-04-28T01:28+08:00
- workflow：`wf_1228997413c5`
- current_stage：`project_init`
- workflow status：`EXECUTING`
- ticket 汇总：`COMPLETED=5`、`EXECUTING=1`
- active ticket：`tkt_f82b10036df2`
- open incident：无
- failed ticket：无
- monitor 记录：01:27 workflow 启动，active ticket 为 `tkt_f82b10036df2`，provider attempt `1` completed
- 判断：runner 正常推进；继续等待进入后续阶段

#### M08. 重启后进入 build 阶段

- 时间：2026-04-28T01:35+08:00
- workflow：`wf_1228997413c5`
- current_stage：`build`
- workflow status：`EXECUTING`
- ticket 汇总：`COMPLETED=10`、`EXECUTING=1`、`LEASED=1`
- active / leased ticket：`tkt_38dad7783185`、`tkt_6741b0ef0ac9`
- open incident：无
- failed ticket：无
- monitor 记录：已完成 architecture、milestone、detailed design、backlog recommendation；开始 backlog follow-up 实现 fanout
- 判断：重启后已进入实现阶段；继续重点观察 provider 波动和后续 check 阶段

#### M09. build 阶段静默恢复

- 时间：2026-04-28T01:54+08:00
- workflow：`wf_1228997413c5`
- current_stage：`build`
- workflow status：`EXECUTING`
- ticket 汇总：`COMPLETED=11`、`EXECUTING=1`、`LEASED=1`
- active / leased ticket：`tkt_48f70ec17b7c`、`tkt_6741b0ef0ac9`
- open incident：无
- failed ticket：无
- provider 记录：`tkt_38dad7783185` attempt 1 因 `SCHEMA_VALIDATION_FAILED` 自动重试，attempt 2 因 `FIRST_TOKEN_TIMEOUT` 自动重试，attempt 3 completed
- monitor 记录：静默 18 分 22 秒后恢复；`tkt_38dad7783185` 已完成并生成 checker 票；`tkt_6741b0ef0ac9` 曾因旧 lease 过期被 start reject，随后重新 lease
- 判断：provider/retry 路径已自动恢复；暂无代码修补

#### M10. build 阶段继续推进

- 时间：2026-04-28T02:15+08:00
- workflow：`wf_1228997413c5`
- current_stage：`build`
- workflow status：`EXECUTING`
- ticket 汇总：`COMPLETED=13`、`EXECUTING=1`、`LEASED=1`
- active / leased ticket：`tkt_320d9143b7dc`、`tkt_f440477af914`
- open incident：无
- failed ticket：无
- provider 记录：`tkt_6741b0ef0ac9` attempt 1 和 2 因 `FIRST_TOKEN_TIMEOUT` 自动重试，attempt 3 completed，耗时约 573 秒
- monitor 记录：前端 foundation source delivery 已完成；对应 checker 票已启动；后端修正 follow-up 已重新 lease
- 判断：长耗时由 provider 重试覆盖，workflow 仍在推进；暂无代码修补

#### M11. follow-up 修正票启动

- 时间：2026-04-28T02:21+08:00
- workflow：`wf_1228997413c5`
- current_stage：`build`
- workflow status：`EXECUTING`
- ticket 汇总：`COMPLETED=15`、`EXECUTING=1`、`LEASED=1`
- active / leased ticket：`tkt_7aa3b6696516`、`tkt_3e7b6036da87`
- open incident：无
- failed ticket：无
- monitor 记录：02:20 静默 5 分 34 秒后恢复；后端和前端 checker 均已完成并派生修正 follow-up
- 判断：实现阶段继续推进；暂无代码修补

#### M12. 1800 秒例行检查 3

- 时间：2026-04-28T02:48+08:00
- workflow：`wf_1228997413c5`
- current_stage：`build`
- workflow status：`EXECUTING`
- ticket 汇总：`COMPLETED=20`、`PENDING=1`
- pending ticket：`tkt_1cf48af91061`
- open incident：无
- failed ticket：无
- provider 记录：BR-003 后端实现票 `tkt_02ab9efad21d` attempt 1 和 2 因 `FIRST_TOKEN_TIMEOUT` 自动重试，attempt 3 completed
- monitor 记录：BR-003 后端实现和 checker 已完成；checker 生成 follow-up
- 判断：仍在 build 阶段；provider 波动由自动重试覆盖，暂无代码修补

#### M13. BR-004 已启动

- 时间：2026-04-28T02:56+08:00
- workflow：`wf_1228997413c5`
- current_stage：`build`
- workflow status：`EXECUTING`
- ticket 汇总：`COMPLETED=22`、`EXECUTING=1`
- active ticket：`tkt_040af73d370a`
- open incident：无
- failed ticket：无
- monitor 记录：BR-003 follow-up 与 checker 已通过；CEO 已创建 BR-004 catalog / inventory 后端实现票
- 判断：build 阶段继续推进；暂无代码修补

#### M14. BR-004 provider 失败后自动重试

- 时间：2026-04-28T03:11+08:00
- workflow：`wf_1228997413c5`
- current_stage：`build`
- workflow status：`EXECUTING`
- ticket 汇总：`COMPLETED=22`、`EXECUTING=1`、`FAILED=1`
- failed ticket：`tkt_040af73d370a`
- active ticket：`tkt_3866bb84c746`
- open incident：无
- provider 记录：`tkt_040af73d370a` 多次 `FIRST_TOKEN_TIMEOUT` 后以 `PROVIDER_BAD_RESPONSE / stream_read_error` 失败；scheduler 已创建 replacement `tkt_3866bb84c746`
- 判断：失败由 replacement 覆盖，workflow 继续执行；暂不做代码修补

#### M15. BR-004 replacement 后继续修正

- 时间：2026-04-28T03:22+08:00
- workflow：`wf_1228997413c5`
- current_stage：`build`
- workflow status：`EXECUTING`
- ticket 汇总：`COMPLETED=24`、`EXECUTING=1`、`FAILED=1`
- failed ticket：`tkt_040af73d370a`
- active ticket：`tkt_ec0b88c536d2`
- open incident：无
- monitor 记录：replacement `tkt_3866bb84c746` completed；checker `tkt_b85ef87bc917` 返回 `CHANGES_REQUIRED`；已创建新 follow-up `tkt_ec0b88c536d2`
- 判断：BR-004 继续通过 follow-up 收敛；暂无代码修补

#### M16. BR-005 已启动

- 时间：2026-04-28T03:50+08:00
- workflow：`wf_1228997413c5`
- current_stage：`build`
- workflow status：`EXECUTING`
- ticket 汇总：`COMPLETED=26`、`EXECUTING=1`、`FAILED=1`
- failed ticket：`tkt_040af73d370a`
- active ticket：`tkt_cd30c8be5e9d`
- open incident：无
- monitor 记录：BR-004 follow-up `tkt_ec0b88c536d2` completed；checker `tkt_112db12581a7` completed；BR-005 backend 票已启动
- 判断：BR-004 已收敛，build 进入下一业务切片；暂无代码修补

#### M17. BR-005 follow-up 启动

- 时间：2026-04-28T04:11+08:00
- workflow：`wf_1228997413c5`
- current_stage：`build`
- workflow status：`EXECUTING`
- ticket 汇总：`COMPLETED=28`、`EXECUTING=1`、`FAILED=1`
- failed ticket：`tkt_040af73d370a`
- active ticket：`tkt_ae3e9525c4f7`
- open incident：无
- provider 记录：BR-005 初始实现票 `tkt_cd30c8be5e9d` attempt 1 和 2 first token timeout，attempt 3 completed
- monitor 记录：BR-005 checker 返回 follow-up；新 follow-up 已启动
- 判断：build 阶段继续推进；暂无代码修补

#### M18. BR-006 / BR-007 已启动

- 时间：2026-04-28T04:22+08:00
- workflow：`wf_1228997413c5`
- current_stage：`build`
- workflow status：`EXECUTING`
- ticket 汇总：`COMPLETED=30`、`EXECUTING=1`、`LEASED=1`、`FAILED=1`
- failed ticket：`tkt_040af73d370a`
- active / leased ticket：`tkt_3b29b226c012`、`tkt_f4dc2d1a0f78`
- open incident：无
- monitor 记录：BR-005 follow-up `tkt_ae3e9525c4f7` completed；checker `tkt_49c022c9d74f` completed；BR-006 后端票已 lease，BR-007 前端票已启动
- 判断：build 阶段进入后续业务切片；暂无代码修补

#### M19. BR-007 provider 失败后自动重试

- 时间：2026-04-28T04:38+08:00
- workflow：`wf_1228997413c5`
- current_stage：`build`
- workflow status：`EXECUTING`
- ticket 汇总：`COMPLETED=30`、`EXECUTING=1`、`LEASED=1`、`FAILED=2`
- failed tickets：`tkt_040af73d370a`、`tkt_3b29b226c012`
- active / leased ticket：`tkt_7019760d3e4e`、`tkt_f4dc2d1a0f78`
- open incident：无
- provider 记录：`tkt_3b29b226c012` 多次 `FIRST_TOKEN_TIMEOUT` 后以 `PROVIDER_BAD_RESPONSE / stream_read_error` 失败；scheduler 已创建 replacement `tkt_7019760d3e4e`
- 判断：失败由 replacement 覆盖，workflow 继续执行；暂不做代码修补

#### M20. BR-006 执行中，BR-007 进入 follow-up

- 时间：2026-04-28T04:54+08:00
- workflow：`wf_1228997413c5`
- current_stage：`build`
- workflow status：`EXECUTING`
- ticket 汇总：`COMPLETED=32`、`EXECUTING=1`、`PENDING=1`、`FAILED=2`
- failed tickets：`tkt_040af73d370a`、`tkt_3b29b226c012`
- active ticket：`tkt_f4dc2d1a0f78`
- pending ticket：`tkt_12ad4972dee4`
- open incident：无
- monitor 记录：BR-007 replacement `tkt_7019760d3e4e` completed；checker `tkt_406d00cd58d0` completed 并创建 follow-up；BR-006 后端票开始执行
- 判断：build 阶段继续推进；暂无代码修补

#### M21. BR-007 follow-up 完成，BR-006 checker 执行中

- 时间：2026-04-28T05:15+08:00
- workflow：`wf_1228997413c5`
- current_stage：`build`
- workflow status：`EXECUTING`
- ticket 汇总：`COMPLETED=34`、`EXECUTING=1`、`PENDING=1`、`FAILED=2`
- active ticket：`tkt_fe689da9eaa1`
- pending ticket：`tkt_4d2691fa9aff`
- open incident：无
- monitor 记录：BR-007 follow-up `tkt_12ad4972dee4` completed；其 checker `tkt_4d2691fa9aff` 已创建并等待调度；BR-006 checker `tkt_fe689da9eaa1` 正在执行
- 判断：workflow 持续推进；暂无代码修补

#### M22. 1800 秒检查，BR-008 follow-up 执行中

- 时间：2026-04-28T05:46+08:00
- workflow：`wf_1228997413c5`
- current_stage：`build`
- workflow status：`EXECUTING`
- ticket 汇总：`COMPLETED=38`、`EXECUTING=1`、`FAILED=2`
- active ticket：`tkt_46b6b9c769c5`
- open incident：无
- monitor 记录：BR-006 checker `tkt_fe689da9eaa1` completed；BR-007 checker `tkt_4d2691fa9aff` completed；BR-008 initial implementation `tkt_76fb5010c9df` completed；BR-008 checker `tkt_9fd328afe25f` completed 并创建 follow-up `tkt_46b6b9c769c5`
- provider 记录：`tkt_46b6b9c769c5` attempt 1 触发 `FIRST_TOKEN_TIMEOUT`，attempt 2 触发 `UPSTREAM_UNAVAILABLE / Connection reset by peer`，attempt 3 已收到 first token 并继续 streaming
- 判断：provider 波动已由 runtime 自动重试覆盖，workflow 仍在推进；暂无代码修补

#### M23. 1800 秒检查发现 BR-009 check 重复失败

- 时间：2026-04-28T06:17+08:00
- workflow：`wf_1228997413c5`
- current_stage：`check`
- workflow status：`EXECUTING`
- ticket 汇总：`COMPLETED=40`、`FAILED=40`、`PENDING=1`
- open incident：`37`
- 卡点现象：BR-009 check 票持续以 `RUNTIME_INPUT_ERROR` 失败，错误为 `Process asset pa://source-code-delivery/tkt_cc5ee0ee37b5 is missing.`
- 处置：停止当前 live runner，避免继续刷失败票；转入 P05 runtime/harness 修补
- 判断：scenario root 已被重复失败和 open incident 污染，修补后需要备份并 `--clean` 重启

#### M24. P05 修补后 clean 重启

- 时间：2026-04-28T06:24+08:00
- workflow：`wf_7ed3499c2cae`
- current_stage：`plan`
- workflow status：`EXECUTING`
- ticket 汇总：`EXECUTING=1`
- open incident：无
- runner：新会话 `82792`
- 重启命令：`.venv/bin/python -m tests.live.run_configured --config data/live-tests/library_management_autopilot_live_014.toml --clean --max-ticks 1200 --timeout-sec 64800`
- 判断：live run 已恢复启动；进入稳态监控

#### M25. 重启后短间隔健康检查

- 时间：2026-04-28T06:30+08:00
- workflow：`wf_7ed3499c2cae`
- current_stage：`project_init`
- workflow status：`EXECUTING`
- ticket 汇总：`COMPLETED=5`、`EXECUTING=1`
- active ticket：`tkt_db0fff837044`
- open incident：无
- monitor 记录：architecture brief 与 technology decision 已完成；milestone plan checker 正在执行
- 判断：P05 修补后新 run 正常推进；暂无代码修补

#### M26. 1800 秒检查，新 workflow 进入 build

- 时间：2026-04-28T07:01+08:00
- workflow：`wf_7ed3499c2cae`
- current_stage：`build`
- workflow status：`EXECUTING`
- ticket 汇总：`COMPLETED=11`、`EXECUTING=1`
- active ticket：`tkt_33ece41fef47`
- open incident：无
- monitor 记录：M1 foundation implementation `tkt_dd91caf09019` completed；checker `tkt_33ece41fef47` 正在执行
- provider 记录：`tkt_dd91caf09019` 前 3 次 attempt 触发 `FIRST_TOKEN_TIMEOUT`，attempt 4 完成；未打开 incident
- 判断：重启后已进入 build 稳态；暂无代码修补

#### M27. 1800 秒检查，M2 SQLite 票 provider 重试中

- 时间：2026-04-28T07:32+08:00
- workflow：`wf_7ed3499c2cae`
- current_stage：`build`
- workflow status：`EXECUTING`
- ticket 汇总：`COMPLETED=13`、`EXECUTING=1`、`PENDING=1`
- active ticket：`tkt_eb8ec29d0350`
- pending ticket：`tkt_774e12969636`
- open incident：无
- monitor 记录：M1 checker `tkt_33ece41fef47` completed；M3 auth/RBAC implementation `tkt_bfdbee5b8156` completed 并创建 checker；M2 SQLite implementation `tkt_eb8ec29d0350` 执行中
- provider 记录：`tkt_eb8ec29d0350` attempt 1-4 均触发 `FIRST_TOKEN_TIMEOUT`，attempt 5 已启动并等待 first token
- 判断：仍在 provider 自动重试预算内，未形成 runtime/harness 卡点；暂无代码修补

#### M28. 1800 秒检查，M2 provider 重试耗尽后 replacement 启动

- 时间：2026-04-28T08:03+08:00
- workflow：`wf_7ed3499c2cae`
- current_stage：`build`
- workflow status：`EXECUTING`
- ticket 汇总：`COMPLETED=13`、`EXECUTING=1`、`LEASED=1`、`FAILED=1`
- failed ticket：`tkt_eb8ec29d0350`
- replacement ticket：`tkt_2bd1013aa3af`
- leased ticket：`tkt_774e12969636`
- open incident：`1`，状态 `RECOVERING`
- monitor 记录：M2 SQLite implementation `tkt_eb8ec29d0350` 10 次 provider attempt 均以 `FIRST_TOKEN_TIMEOUT` 失败；CEO recovery 创建 replacement `tkt_2bd1013aa3af`，并已启动；M3 checker `tkt_774e12969636` 已 lease
- 判断：provider 层连续超时，已被 runtime / CEO recovery 覆盖；暂无代码修补

#### M29. M2 replacement 完成，provider incident 自动关闭

- 时间：2026-04-28T08:10+08:00
- workflow：`wf_7ed3499c2cae`
- current_stage：`build`
- workflow status：`EXECUTING`
- ticket 汇总：`COMPLETED=14`、`EXECUTING=1`、`PENDING=1`、`FAILED=1`
- completed replacement：`tkt_2bd1013aa3af`
- active ticket：`tkt_774e12969636`
- pending ticket：`tkt_62d1ba70fe79`
- open incident：无
- monitor 记录：M2 replacement `tkt_2bd1013aa3af` attempt 1 在 293 秒收到 first token 并完成；provider incident `inc_6b58dada58c0` 自动关闭；M2 checker `tkt_62d1ba70fe79` 已创建
- 判断：P06 已自动恢复；暂无代码修补

#### M30. 1800 秒检查，进入 M5 circulation 实现

- 时间：2026-04-28T08:41+08:00
- workflow：`wf_7ed3499c2cae`
- current_stage：`build`
- workflow status：`EXECUTING`
- ticket 汇总：`COMPLETED=20`、`EXECUTING=1`、`PENDING=1`、`FAILED=1`
- active ticket：`tkt_e2949d442904`
- pending ticket：`tkt_bb8135cdf2be`
- open incident：无
- monitor 记录：M2 checker `tkt_62d1ba70fe79` completed；M3 checker `tkt_774e12969636` completed；M4 catalog 先由 checker `tkt_522907daf2f0` 要求修改，follow-up `tkt_2bf2ef613f1c` completed，checker `tkt_0b70b2471abb` completed；M5 circulation implementation `tkt_e2949d442904` 正在执行
- provider 记录：`tkt_e2949d442904` attempt 1 已收到 first token 并 streaming
- 判断：build 阶段稳态推进；暂无代码修补

#### M31. 1800 秒检查，M5 replacement 执行中

- 时间：2026-04-28T09:13+08:00
- workflow：`wf_7ed3499c2cae`
- current_stage：`build`
- workflow status：`EXECUTING`
- ticket 汇总：`COMPLETED=21`、`EXECUTING=1`、`LEASED=1`、`FAILED=2`
- active ticket：`tkt_745fcab4b232`
- leased ticket：`tkt_c55d2b5064ce`
- failed tickets：`tkt_eb8ec29d0350`、`tkt_e2949d442904`
- open incident：无
- monitor 记录：M6 reader/staff implementation `tkt_bb8135cdf2be` completed，并创建 checker `tkt_c55d2b5064ce`；M5 original `tkt_e2949d442904` 因 provider `stream_read_error` 失败，replacement `tkt_745fcab4b232` 已启动
- provider 记录：`tkt_745fcab4b232` attempt 1 触发 `FIRST_TOKEN_TIMEOUT`，attempt 2 已启动并等待 first token
- 判断：provider 波动已由 replacement 覆盖，workflow 继续推进；暂无代码修补

#### M32. 1800 秒检查，M6 follow-up 执行中

- 时间：2026-04-28T09:45+08:00
- workflow：`wf_7ed3499c2cae`
- current_stage：`build`
- workflow status：`EXECUTING`
- ticket 汇总：`COMPLETED=24`、`EXECUTING=1`、`PENDING=1`、`FAILED=2`
- active ticket：`tkt_0da8b342cbb3`
- pending ticket：`tkt_fba5b63050d2`
- failed tickets：`tkt_eb8ec29d0350`、`tkt_e2949d442904`
- open incident：无
- monitor 记录：M5 replacement `tkt_745fcab4b232` completed；M5 checker `tkt_09be59d6c019` completed with `CHANGES_REQUIRED`，创建 follow-up `tkt_fba5b63050d2`；M6 checker `tkt_c55d2b5064ce` completed with `CHANGES_REQUIRED`，M6 follow-up `tkt_0da8b342cbb3` 正在执行
- provider 记录：`tkt_0da8b342cbb3` attempt 1 触发 `FIRST_TOKEN_TIMEOUT`，attempt 2 已启动并等待 first token
- 判断：build 阶段仍在推进；暂无代码修补

#### M33. 1800 秒检查，进入 M7 Remove / Inventory / Audit

- 时间：2026-04-28T10:16+08:00
- workflow：`wf_7ed3499c2cae`
- current_stage：`build`
- workflow status：`EXECUTING`
- ticket 汇总：`COMPLETED=28`、`EXECUTING=1`、`FAILED=2`
- active ticket：`tkt_59e7a4e8c8b6`
- failed tickets：`tkt_eb8ec29d0350`、`tkt_e2949d442904`
- open incident：无
- monitor 记录：M6 follow-up `tkt_0da8b342cbb3` completed；M6 checker `tkt_9a27dc40eeeb` completed；M5 follow-up `tkt_fba5b63050d2` completed；M5 checker `tkt_06d16643175f` completed；M7 Remove / Inventory / Audit `tkt_59e7a4e8c8b6` 正在执行
- incident 记录：10:05 出现一次 `CEO_SHADOW_PIPELINE_FAILED`，错误为 provider 返回的 `NO_ACTION payload` 不匹配 CEO shadow contract；10:09 自动 rerun 后关闭，未阻塞 workflow
- provider 记录：`tkt_59e7a4e8c8b6` attempt 1 已收到 first token 并 streaming
- 判断：build 阶段持续推进；暂无代码修补

#### M34. resume 后检查，M7 checker provider 恢复中

- 时间：2026-04-28T11:00+08:00
- workflow：`wf_7ed3499c2cae`
- current_stage：`build`
- workflow status：`EXECUTING`
- workflow version：`369`
- ticket 汇总：`COMPLETED=29`、`FAILED=3`、`PENDING=1`
- pending ticket：`tkt_6dc3c82f6c4d`
- failed tickets：`tkt_eb8ec29d0350`、`tkt_e2949d442904`、`tkt_e0a99bae9d1f`
- open incident：`inc_df97ee50cdf6`，状态 `RECOVERING`，类型 `PROVIDER_EXECUTION_PAUSED`
- incident 节点：`node_backlog_followup_impl_m7_remove_inventory_audit`
- 根因判断：M7 checker 票 `tkt_e0a99bae9d1f` 先经历多次 `UPSTREAM_UNAVAILABLE`，随后第 10 次等待 first token 超时，失败类型为 `FIRST_TOKEN_TIMEOUT`
- 恢复动作：runtime / CEO recovery 已创建 retry ticket `tkt_6dc3c82f6c4d`
- runner 状态：当前会话 runner 仍在运行
- 处置：不修代码；等待恢复票被调度并继续观察
- 稳态判断：workflow 未退出，处于 provider 自动恢复路径，暂未发现 harness / controller 新卡点

#### M35. 1800 秒检查，runner 卡在 provider socket 读取

- 时间：2026-04-28T11:33+08:00
- workflow：`wf_7ed3499c2cae`
- current_stage：`build`
- workflow status：`EXECUTING`
- workflow version：`369`
- ticket 汇总：`COMPLETED=29`、`FAILED=3`、`PENDING=1`
- pending ticket：`tkt_6dc3c82f6c4d`
- open incident：`inc_df97ee50cdf6`，状态 `RECOVERING`
- 现象：事件流停在 sequence `369`，恢复票超过 30 分钟未被 lease；runner 进程仍存活，但没有写入新的 scheduler orchestration 事件
- 诊断：`sample 3545 2` 显示主线程阻塞在 socket `recv`；`lsof -p 3545` 显示 runner 与 provider `:11234` 仍保持 ESTABLISHED 连接
- 根因判断：CEO / provider streaming 调用进入无界 socket read；当前进程使用旧代码，无法从本次代码修补中自动恢复
- 稳态判断：已从 provider 波动升级为 runtime/provider timeout 基建卡点，需要最小修补并续跑

#### M36. P09 修补后不带 clean 续跑恢复推进

- 时间：2026-04-28T11:59+08:00
- workflow：`wf_7ed3499c2cae`
- current_stage：`build`
- workflow status：`EXECUTING`
- workflow version：`371`
- ticket 汇总：`COMPLETED=29`、`EXECUTING=1`、`FAILED=3`
- active ticket：`tkt_6dc3c82f6c4d`
- runner 处置：旧 runner 进程 `3545` 已停止；用修补后的代码不带 `--clean` 续跑
- 续跑命令：`.venv/bin/python -m tests.live.run_configured --config data/live-tests/library_management_autopilot_live_014.toml --max-ticks 1200 --timeout-sec 64800`
- 事件验证：`tkt_6dc3c82f6c4d` 已在 11:59:17 lease/start，11:59:37 收到 first token
- 稳态判断：P09 修补有效，恢复票已进入 streaming；继续按 1800 秒节奏监控

## 问题与修补

本节用于追加记录本轮运行过程中遇到的卡点、根因、最小修补、验证命令与续跑结果。

### P01. provider `stream_read_error` 被自动恢复覆盖

- 时间：2026-04-28T00:44+08:00
- 现象：`tkt_d25c7f86ea0a` 失败，`last_failure_kind=PROVIDER_BAD_RESPONSE`，`last_failure_message=stream_read_error`
- 影响：该票失败，但 workflow 未打开 incident，后续 replacement ticket 继续推进
- 处理：不修代码；记录为 provider 波动
- 验证：第二轮 1800 秒检查时，workflow 仍为 `EXECUTING / build`，open incident 为 0，replacement 票已完成并继续执行下一张票

### P02. CHECK_FAILED 后 stall，checker 没拿到依赖实现证据

- 时间：2026-04-28T01:08+08:00
- 现象：runner 退出，错误为 `Scenario stalled for 25 ticks`
- failure snapshot：`backend/data/scenarios/library_management_autopilot_live_014/failure_snapshots/stall.json`
- workflow：`wf_80100a48d705`
- 当前阶段：`check`
- 票据状态：`COMPLETED=22`、`FAILED=1`
- 直接阻塞：`delivery_check_failed` on `tkt_315c071a73ed`
- 根因：M1 检查票的 `input_process_asset_refs` 没包含依赖实现票的 `pa://source-code-delivery/...`，checker 只拿到 project map 中的引用、旧失败报告和治理文档，无法读取 runtime foundation / SQLite schema seed 的 source、test、git evidence。
- 修补：
  - `backend/app/core/workflow_controller.py`：创建 `delivery_check_report` follow-up 时，把依赖实现票的 source-code-delivery process asset refs 注入 `input_process_asset_refs`
  - `backend/app/contracts/ceo_actions.py`：允许 CEO `CREATE_TICKET` payload 携带 `input_process_asset_refs`
  - `backend/app/core/ceo_execution_presets.py`：把 CEO payload 中的 `input_process_asset_refs` 传入实际 `TicketCreateCommand`
  - `backend/tests/test_ceo_scheduler.py`：新增回归，验证 M1 smoke check 票会读取依赖 source delivery assets
- 验证：
  - `tests/test_ceo_scheduler.py::test_backlog_delivery_check_followup_reads_dependency_source_delivery_assets`：`1 passed`
  - `tests/test_ceo_scheduler.py -k "backlog_followup or delivery_check_followup or cto_governance_contract"`：`21 passed, 124 deselected`
  - `tests/test_live_configured_runner.py`：`11 passed`
- 续跑策略：当前 scenario root 已包含旧的 fail-closed check report 和 stall 状态；先备份旧目录，再 `--clean` 重启 `014`
- 已备份旧目录：`backend/data/scenarios/library_management_autopilot_live_014_stalled_20260428-0108`

### P03. BR-004 provider `stream_read_error` 被 replacement 覆盖

- 时间：2026-04-28T03:09+08:00
- 现象：`tkt_040af73d370a` 失败，`last_failure_kind=PROVIDER_BAD_RESPONSE`，`last_failure_message=stream_read_error`
- 影响：该票失败，但 workflow 未打开 incident；scheduler 创建 replacement ticket `tkt_3866bb84c746`
- 处理：不修代码；记录为 provider 波动
- 验证：03:11 检查时，workflow 仍为 `EXECUTING / build`，open incident 为 0，replacement 票已执行并拿到 first token

### P04. BR-007 provider `stream_read_error` 被 replacement 覆盖

- 时间：2026-04-28T04:36+08:00
- 现象：`tkt_3b29b226c012` 失败，`last_failure_kind=PROVIDER_BAD_RESPONSE`，`last_failure_message=stream_read_error`
- 影响：该票失败，但 workflow 未打开 incident；scheduler 创建 replacement ticket `tkt_7019760d3e4e`
- 处理：不修代码；记录为 provider 波动
- 验证：04:38 检查时，workflow 仍为 `EXECUTING / build`，open incident 为 0，replacement 票已启动

### P05. BR-009 check 读取了 checker 票的伪 source delivery 引用

- 时间：2026-04-28T06:18+08:00
- 现象：BR-009 check 从 `tkt_3077863f0e5d` 开始反复失败，最新失败链路已到 40+ 次；失败信息固定为 `Process asset pa://source-code-delivery/tkt_cc5ee0ee37b5 is missing.`
- 直接根因：依赖 source delivery 注入逻辑按依赖节点取最新 ticket；BR-003 节点最新票是 checker `tkt_cc5ee0ee37b5`，该票完成事件 `produced_process_assets=[]`，并没有 source delivery process asset。
- 修补：
  - `backend/app/core/workflow_controller.py`：为 backlog delivery check 注入依赖 process asset 时，改为在依赖节点内按更新时间倒序查找“实际产出 `SOURCE_CODE_DELIVERY` process asset”的最近实现票；dependency gate 仍保留最新票，用于等待 checker 完成。
  - `backend/tests/test_ceo_scheduler.py`：新增回归，覆盖“依赖节点最新票是 checker，但 check 输入必须读取最近真实 source delivery”的场景。
- 验证：
  - `backend/tests/test_ceo_scheduler.py::test_backlog_delivery_check_followup_uses_latest_real_source_delivery_not_checker_ticket`：先失败，随后修补后通过
  - `backend/tests/test_ceo_scheduler.py::test_backlog_delivery_check_followup_uses_latest_real_source_delivery_not_checker_ticket backend/tests/test_ceo_scheduler.py::test_backlog_delivery_check_followup_reads_dependency_source_delivery_assets`：`2 passed`
  - `backend/tests/test_ceo_scheduler.py -k "backlog_followup or delivery_check_followup or cto_governance_contract"`：`22 passed, 124 deselected`
  - `backend/tests/test_live_configured_runner.py`：`11 passed`
- 运行处置：当前 runner 已停止；污染目录已备份到 `backend/data/scenarios/library_management_autopilot_live_014_bad_source_asset_20260428-0623`
- 续跑策略：由于旧 scenario 已含大量坏 created payload、failed tickets 和 open incidents，本次按方案判定为 scenario root 污染，使用 `--clean` 重启 `014`

### P06. M2 SQLite provider 连续 `FIRST_TOKEN_TIMEOUT` 后自动 replacement

- 时间：2026-04-28T08:03+08:00
- 现象：`tkt_eb8ec29d0350` 连续 10 次 provider attempt 等待 first token 超时，最终以 `FIRST_TOKEN_TIMEOUT` 失败。
- 影响：runtime 打开 `PROVIDER_EXECUTION_PAUSED` incident；CEO recovery 创建 replacement ticket `tkt_2bd1013aa3af`。
- 处理：不修代码；记录为 provider 波动。当前 replacement 已启动，workflow 仍在 build 阶段推进。
- 验证：08:04 检查时，`tkt_2bd1013aa3af` 为 `EXECUTING`，M3 checker `tkt_774e12969636` 为 `LEASED`，runner 进程仍在运行。

### P07. M5 circulation provider `stream_read_error` 被 replacement 覆盖

- 时间：2026-04-28T08:53+08:00
- 现象：`tkt_e2949d442904` 失败，`last_failure_kind=PROVIDER_BAD_RESPONSE`，`last_failure_message=stream_read_error`
- 影响：该票失败，但 workflow 未打开 incident；scheduler 创建 replacement `tkt_745fcab4b232`
- 处理：不修代码；记录为 provider 波动
- 验证：09:13 检查时，workflow 仍为 `EXECUTING / build`，open incident 为 0，replacement `tkt_745fcab4b232` 正在执行

### P08. M7 checker provider 连续不可用后进入自动恢复

- 时间：2026-04-28T10:57+08:00
- 现象：M7 checker 票 `tkt_e0a99bae9d1f` 失败，`last_failure_kind=FIRST_TOKEN_TIMEOUT`，`last_failure_message=timed out`
- 直接证据：事件流显示该票多次出现 `UPSTREAM_UNAVAILABLE`，包括 `nodename nor servname provided, or not known`、`incomplete chunked read` 等 provider 侧错误；第 10 次 attempt 等待 first token 超时
- 影响：runtime 打开 `PROVIDER_EXECUTION_PAUSED` incident `inc_df97ee50cdf6`，状态随后进入 `RECOVERING`
- 处理：不修代码；记录为 provider 波动。CEO recovery 已创建 retry ticket `tkt_6dc3c82f6c4d`
- 验证：11:00 检查时，workflow 仍为 `EXECUTING / build`，runner 仍在运行，pending retry ticket 已存在
- 后续：继续等待 retry ticket 被调度；如恢复票再次失败并造成 stall，再按 runtime / harness 卡点处理

### P09. streaming provider socket read 无界导致 runner 卡住

- 时间：2026-04-28T11:58+08:00
- 现象：`inc_df97ee50cdf6` 进入 `RECOVERING` 后，事件流停在 `INCIDENT_RECOVERY_STARTED`；runner 进程存活但 30 分钟无新事件，恢复票 `tkt_6dc3c82f6c4d` 一直是 `PENDING`
- 根因：provider streaming 使用无界 socket read。`sample 3545 2` 显示主线程卡在 `_socket.recv`；代码检查发现 `_sdk_timeout(..., streaming=True)` 和 `_stream_timeout()` 都把 read timeout 设为 `None`。同时 CEO shadow 的 OpenAI compat 调用只传 `timeout_sec`，未继承 live config 中的 `connect/write/first_token/stream_idle/request_total/provider_type`
- 最小修补：
  - `backend/app/core/provider_openai_compat.py`：新增 streaming read timeout 解析，SDK streaming 与 httpx SSE streaming 都使用 `min(first_token_timeout_sec, stream_idle_timeout_sec)` 作为 socket read 上限，避免无限阻塞
  - `backend/app/core/ceo_proposer.py`：CEO shadow OpenAI compat 调用继承 provider entry 的分项 timeout、`request_total_timeout_sec`、`provider_type` 与 reasoning effort
  - `backend/tests/test_provider_openai_compat.py`：新增 streaming socket read timeout 回归
  - `backend/tests/test_ceo_scheduler.py`：新增 CEO provider timeout 继承回归
- 验证：
  - `tests/test_provider_openai_compat.py::test_streaming_transports_use_bounded_socket_read_timeout tests/test_provider_openai_compat.py::test_invoke_openai_compat_response_ignores_request_total_timeout_for_streaming`：`2 passed`
  - `tests/test_ceo_scheduler.py::test_ceo_shadow_openai_provider_inherits_configured_timeouts`：`1 passed`
  - `tests/test_live_configured_runner.py`：`11 passed`
  - `tests/test_provider_openai_compat.py`：`30 passed`
  - `tests/test_ceo_scheduler.py -k "ceo_shadow_openai_provider_inherits_configured_timeouts or ceo_shadow_prefers_role_binding_over_default_provider or backlog_followup or delivery_check_followup or cto_governance_contract"`：`24 passed, 123 deselected`
- 续跑策略：当前 runner 进程仍卡在旧代码的 provider read；停止本轮卡住进程后，不带 `--clean` 续跑当前 workflow
- 续跑验证：11:59 检查时，恢复票 `tkt_6dc3c82f6c4d` 已从 `PENDING` 进入 `EXECUTING`，并收到 provider first token

## 终止与回退记录

- 时间：2026-04-28T12:29:18+08:00
- 用户指令：终止第 14 轮 live 集成测试，回退所有本轮测试改动，保留并整理本日志。
- 进程处置：live runner 进程 `48026` 已先前收到 `TERM`；复查进程表时，只剩本次 `ps | rg` 查询进程，没有 `tests.live.run_configured` 或 `library_management_autopilot_live_014` runner。
- 配置回退：删除本轮生成的 `backend/data/live-tests/library_management_autopilot_live_014.toml` 和 `backend/library_management_autopilot_live_014.toml`。
- 产物回退：删除本轮 scenario 产物目录 `backend/data/scenarios/library_management_autopilot_live_014`，以及两份污染场景备份目录 `backend/data/scenarios/library_management_autopilot_live_014_stalled_20260428-0108`、`backend/data/scenarios/library_management_autopilot_live_014_bad_source_asset_20260428-0623`。
- 代码回退：回退 P02/P05/P09 的临时运行时修补，包括 CEO create-ticket payload 注入、checker dependency source delivery 选择、streaming socket read timeout、CEO OpenAI compat timeout 继承，以及对应回归测试。
- 保留内容：保留本日志 `doc/tests/intergration-test-014-20260427.md`，作为本轮测试审计记录。
- 未处理范围：工作区存在其它未提交 staffing/mainline 改动，无法安全判定为本轮 live 测试补丁，未做回退。

## 问题汇总

| 编号 | 场景 / 节点 | 现象 | 根因判断 | 当时处理 | 最终状态 |
|---|---|---|---|---|---|
| P01 | 早期 build 票 `tkt_d25c7f86ea0a` | provider 返回 `stream_read_error`，票据失败 | provider streaming 波动 | 未改代码；等待 scheduler replacement | replacement 推进，workflow 继续执行 |
| P02 | M1 check，workflow `wf_80100a48d705`，检查票 `tkt_315c071a73ed` | runner 因 `Scenario stalled for 25 ticks` 退出 | checker 未拿到依赖实现票的 source delivery 证据，只能看到旧报告和治理文档 | 临时修补 follow-up 创建链路，把依赖实现票的 source delivery process asset refs 注入 checker 输入；定向测试通过后备份污染目录并 `--clean` 重启 | 后续按用户要求已回退该临时修补 |
| P03 | BR-004 implementation | provider 返回 `stream_read_error` | provider streaming 波动 | 未改代码；由 replacement 票继续 | replacement 启动并收到 first token |
| P04 | BR-007 implementation | provider 返回 `stream_read_error` | provider streaming 波动 | 未改代码；由 replacement 票继续 | replacement 启动，workflow 未停 |
| P05 | BR-009 closeout check | check 反复失败，提示 `pa://source-code-delivery/tkt_cc5ee0ee37b5 is missing` | 注入逻辑按节点取最新票，误把 checker 票当作 source delivery 来源；checker 票没有 source delivery asset | 临时修补为“依赖节点内倒序查找最近真实 source delivery 产出”；定向测试通过后备份污染目录并 `--clean` 重启 | 后续按用户要求已回退该临时修补 |
| P06 | M2 SQLite 票 `tkt_eb8ec29d0350` | 连续 10 次 `FIRST_TOKEN_TIMEOUT` 后失败 | provider first token 长时间不可用 | 未改代码；runtime 打开 provider paused incident，CEO recovery 创建 replacement | replacement `tkt_2bd1013aa3af` 启动，workflow 继续 |
| P07 | M5 circulation 票 `tkt_e2949d442904` | provider 返回 `stream_read_error` | provider streaming 波动 | 未改代码；scheduler 创建 replacement | replacement `tkt_745fcab4b232` 执行，workflow 继续 |
| P08 | M7 checker 票 `tkt_e0a99bae9d1f` | 多次 `UPSTREAM_UNAVAILABLE` 后第 10 次 `FIRST_TOKEN_TIMEOUT` | provider 侧不可用，包括 DNS / chunked read / first token timeout | 未改代码；runtime incident 进入 `RECOVERING`，CEO recovery 创建 retry ticket | retry ticket `tkt_6dc3c82f6c4d` pending，等待调度 |
| P09 | M7 retry 恢复阶段，runner 进程 `3545` | runner 存活但 30 分钟无新事件，恢复票不被 lease | streaming provider socket read 无界阻塞；旧 runner 卡在 `_socket.recv` | 临时修补 streaming read timeout 和 CEO provider timeout 继承；停止旧 runner 后不带 `--clean` 续跑 | 续跑后恢复票开始 streaming；随后用户要求终止，临时修补已回退 |

## 回退后校验记录

- 进程检查：`ps -axo pid,etime,stat,command | rg "tests.live.run_configured|library_management_autopilot_live_014"` 没有返回 live runner，只返回检查命令本身；`pgrep -af "[p]ython -m tests.live.run_configured"` 也无输出。
- 配置检查：`backend/data/live-tests/library_management_autopilot_live_014.toml` 和 `backend/library_management_autopilot_live_014.toml` 均已不存在。
- 产物检查：`backend/data/scenarios/` 下未再发现 `library_management_autopilot_live_014*` 目录。
- 残留检查：P02/P05/P09 的测试函数名、stream read helper、CEO timeout 继承调用、controller 中的本轮 process asset 注入代码均未在相关文件中命中。
- 说明：本次按用户要求终止测试并回退本轮临时补丁，没有继续跑 live 集成测试。
