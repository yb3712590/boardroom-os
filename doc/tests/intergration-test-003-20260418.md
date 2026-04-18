# intergration-test-003-20260418

这份记录只追第三轮长测。

目标很简单：

- 继续跑 `library_management_autopilot_live`
- 场景范围沿用第二轮
- Provider 沿用 `https://api-hk.codex-for.me/v1`
- 每 60 秒探查一次 workflow 执行情况
- 只记录新问题、新卡点和关键收口证据

---

## 0. 测试背景

本轮开始前，`intergration-test-002-20260418.md` 里提到的问题已经过两轮修复。

这轮要验证：

- in-process runtime 是否能接回 `EXECUTING` 票
- review lane package guard 是否不再查错 graph node
- provider 卡死时是否能留下足够审计证据
- `integration-monitor-report.md`、`run_report.json`、`failure_snapshots/` 是否按预期落盘

本轮仍使用：

- 场景：`library_management_autopilot_live`
- Provider：`prov_openai_compat_vip`
- Base URL：`https://api-hk.codex-for.me/v1`
- 模型：`gpt-5.4`
- 角色策略：`architect_primary` / `cto_primary` 用 `xhigh`，其他执行角色用 `high`

---

## 1. 启动记录

### [2026-04-18 22:25 +08:00]

准备启动第三轮长测。

启动口径：

- 工作目录：`backend`
- 命令：`py -3.12 -m tests.live.library_management_autopilot_live --max-ticks 180 --timeout-sec 7200`
- 输出日志：`.tmp/integration-monitor/live-003-20260418/`
- 场景目录：`backend/data/scenarios/library_management_autopilot_live/`

本轮记录规则：

- 正常心跳不刷屏
- workflow 推进、票状态变化、关键产物落盘时记录
- 如果卡住，记录卡住的 workflow、stage、ticket、role、schema、provider attempt 和已有审计证据
- 如果系统自己写出 failure snapshot / run report，优先引用系统证据

---

## 2. 问题记录

### 问题 A：provider attempt 超过 300s 后仍没有 terminal event

---

## 3. 现场追加

### [2026-04-18 22:28 +08:00]

第三轮长测已启动。

当前现场：

- workflow：`wf_ce3f80a4b50c`
- status：`EXECUTING`
- stage：`plan`
- 首张 active ticket：`tkt_wf_ce3f80a4b50c_ceo_architecture_brief`
- node：`node_ceo_architecture_brief`
- lease owner：`emp_frontend_2`
- ticket status：`EXECUTING`
- ticket start time：`2026-04-18T22:28:32.628717+08:00`

当前已确认的启动证据：

- `WORKFLOW_CREATED`
- `TICKET_CREATED`
- `TICKET_LEASED`
- `TICKET_STARTED`
- `PROVIDER_ATTEMPT_STARTED`

这条 `PROVIDER_ATTEMPT_STARTED` 很关键。

它说明第三轮起步时，provider 审计链已经至少写下了：

- `attempt_no=1`
- `provider_id=prov_openai_compat_vip`
- `actual_model=gpt-5.4`
- `current_phase=awaiting_first_token`
- `request_total_timeout_sec=300`
- `retry_backoff_schedule_sec=[1,2,4,8,16,32,60,60,60]`

当前还没看到：

- `integration-monitor-report.md`
- `audit-summary.md`
- `run_report.json`
- `failure_snapshots/*.json`

这在启动早期是正常现象。

下一步继续按 60 秒节奏探查。

### [2026-04-18 22:35 +08:00]

第三轮开始出现新的卡点。

当前现场：

- workflow：`wf_ce3f80a4b50c`
- status：`EXECUTING`
- stage：`plan`
- active ticket：`tkt_wf_ce3f80a4b50c_ceo_architecture_brief`
- ticket status：`EXECUTING`
- ticket started_at：`2026-04-18T22:28:32.628717+08:00`
- 最近事件：`PROVIDER_FIRST_TOKEN_RECEIVED`
- 最近事件时间：`2026-04-18T22:31:33.802889+08:00`

关键问题：

- `PROVIDER_ATTEMPT_STARTED` 写明 `request_total_timeout_sec=300`
- attempt started at `2026-04-18T22:28:32.690628+08:00`
- 探查时间是 `2026-04-18T22:35:50 +08:00`
- 单次 provider attempt 已持续约 `438s`
- 但事件流里还没有 provider terminal event

当前缺少：

- `PROVIDER_ATTEMPT_SUCCEEDED`
- `PROVIDER_ATTEMPT_FAILED`
- `PROVIDER_ATTEMPT_TIMEOUT`
- `TICKET_RESULT_SUBMITTED`
- `integration-monitor-report.md`
- `run_report.json`
- `failure_snapshots/*.json`

这说明第三轮虽然补上了：

- attempt start 审计
- first token 审计

但目前还没证明：

- `request_total_timeout_sec=300` 能强制收口
- provider stream 卡住时会写 terminal attempt event
- 卡住时会即时落 failure snapshot 或 monitor report

下一步继续观察。

如果后续在 `stream_idle_timeout_sec=300` 后仍不收口，就可以把问题范围进一步收敛为：

- stream idle timeout 没有生效
- 或 timeout 触发了但没有写 provider terminal audit

### [2026-04-18 22:38 +08:00]

按新要求，第三轮已切换 provider 并重启。

本次调整：

- 停掉了卡住的旧 runner
- 保留第三轮记录文件不变
- 把 `backend/data/integration-test-provider-config.json` 的全部 `role_bindings` 从 `prov_openai_compat_vip::gpt-5.4` 切到 `prov_openai_compat::gpt-5.4`
- 重启命令不变，仍是：
  - `py -3.12 -m tests.live.library_management_autopilot_live --max-ticks 180 --timeout-sec 7200`

切换后的 provider 口径：

- provider id：`prov_openai_compat`
- base url：`http://new.xem8k5.top:3000/v1`

重启后的新 workflow：

- workflow：`wf_8a2d2aff32a1`
- status：`EXECUTING`
- stage：`project_init`

当前已确认的新现场证据：

- 场景目录新的 `runtime-provider-config.json` 已落盘
- 全部 `role_bindings` 已指向 `prov_openai_compat::gpt-5.4`
- 新一轮 `EMPLOYEE_HIRED` 事件里的 `provider_id` 已经是 `prov_openai_compat`

说明：

- `wf_ce3f80a4b50c` 那次卡在 `api-hk.codex-for.me` 的现场，作为上一段失败留档保留
- 从这一刻起，第三轮后续探查默认跟踪 `wf_8a2d2aff32a1`

### [2026-04-18 22:46 +08:00]

切到 `new.xem8k5.top` 后，首票没有复现“超时不收口”。

这次 provider attempt 已经正式收口，但暴露了新的问题。

当前现场：

- workflow：`wf_8a2d2aff32a1`
- status：`EXECUTING`
- stage：`plan`
- 当前票数：`2`
- 原首票：`tkt_wf_8a2d2aff32a1_ceo_architecture_brief`
- 重试票：`tkt_9c22c49fd143`

这次关键事件链：

- `22:40:20 +08:00` `PROVIDER_ATTEMPT_STARTED`
- `22:42:34 +08:00` `PROVIDER_FIRST_TOKEN_RECEIVED`
- `22:45:22 +08:00` `PROVIDER_ATTEMPT_FINISHED`
- `22:45:22 +08:00` `TICKET_FAILED`
- `22:45:22 +08:00` `TICKET_RETRY_SCHEDULED`
- `22:45:22 +08:00` 新重试票创建、lease、start

provider 失败细节已经写进事件流：

- `provider_id=prov_openai_compat`
- `status=FAILED`
- `failure_kind=PROVIDER_BAD_RESPONSE`
- `elapsed_sec=301.19`
- `failure_message=Provider output was not valid JSON: Unterminated string starting at: line 1106 column 31 (char 46108)`

这说明：

- `request_total_timeout_sec=300` 这次是生效的
- provider terminal audit 这次也写出来了
- 但 `new.xem8k5.top` 返回了损坏的 JSON

同时又引出了新的系统级问题：

- `INCIDENT_OPENED`
- `CIRCUIT_BREAKER_OPENED`

incident 里的错误是：

- `Meeting candidate source ticket tkt_wf_8a2d2aff32a1_ceo_architecture_brief is missing graph/runtime truth for node_ceo_architecture_brief.`

这说明首票失败后，CEO shadow / meeting candidate 这条恢复链又撞到了新的快照一致性问题。

当前判断：

- 旧 provider 的问题更像“attempt 不收口”
- 新 provider 的问题更像“attempt 能收口，但返回内容不合法，而且失败后的 incident 恢复链还有二次故障”

当前仍缺少：

- `integration-monitor-report.md`
- `run_report.json`
- `audit-summary.md`
- `failure_snapshots/*.json`

### [2026-04-18 22:53 +08:00]

`new.xem8k5.top` 这轮又往前走了一步，但结论更差了。

不是只有首票失败。

重试票也失败了。

当前现场：

- workflow：`wf_8a2d2aff32a1`
- status：`EXECUTING`
- stage：`plan`
- ticket 总数：`2`
- `tkt_wf_8a2d2aff32a1_ceo_architecture_brief`：`FAILED`
- `tkt_9c22c49fd143`：`FAILED`
- active ticket：`none`
- open incident：`1`

新增关键事件：

- `22:47:38 +08:00` 重试票 `PROVIDER_FIRST_TOKEN_RECEIVED`
- `22:51:59 +08:00` 重试票 `PROVIDER_ATTEMPT_FINISHED`
- `22:51:59 +08:00` 重试票 `TICKET_FAILED`

这说明：

- 第二次 provider 调用也已经收口
- 不是卡死
- 但还是没产出可用结果

这轮新的好消息：

- `integration-monitor-report.md` 终于落盘了
- monitor 里已经能直接看到：
  - workflow 还在 `EXECUTING / plan`
  - active tickets 是 `none`
  - incidents 是 `1`
  - provider `prov_openai_compat` 当前 phase 是 `failed`

这轮新的坏消息：

- workflow 现在不是“继续推进中”
- 而是“没有 active ticket，但 incident 还开着，scheduler 只在持续写 orchestration 记录”

当前判断：

- `new.xem8k5.top` 这轮已经证明 provider attempt audit 和 integration monitor 能落盘
- 但业务上仍然跑不通
- 现在现场更像卡在“失败后的恢复链没有真正把 workflow 拉回可执行状态”

当前仍缺少：

- `run_report.json`
- `audit-summary.md`
- `failure_snapshots/*.json`
