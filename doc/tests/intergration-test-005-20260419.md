# intergration-test-005-20260419

这份记录承接 `intergration-test-004-20260419.md`。

本轮目标只有三件事：

- 把 live provider 切到新 key
- 优先判断 004 现场能不能续跑
- 续跑不成立就立刻切 005 重跑，并按 120 秒节奏做 probe

---

## 0. 当前结论

截至 `2026-04-19 16:56:12 +08:00`，本轮结论先收成三句：

- 新 key 已经接成当前唯一 live provider
- 004 现场不能直接续跑，原因不是旧版 `HIRE_EMPLOYEE`，而是旧 backlog artifact 不兼容当前严格 contract
- 005 已经稳定推进到 `backlog_recommendation` 之后，虽然实现扇出前继续暴露 CEO action batch 结构问题，但 staffing gate 已经从 open approval 往前推进到 architect governance gate 真实票据执行

本轮新 provider 口径：

- base url：`http://new.xem8k5.top:3000/v1`
- provider id：`prov_openai_compat_new_key`
- model：`gpt-5.4`
- 旧 key 不参与本轮 live role 绑定，也没有作为 fallback 保留

---

## 1. 004 为什么不能续跑

### 004 preflight 结果

先做了两步最小判定：

1. provider connectivity test
2. 对 004 现场直接跑一次 CEO shadow preflight

结果：

- connectivity 是通的
- 但 preflight 直接失败

失败原因不是旧版 `HIRE_EMPLOYEE`。

这次真正打断 004 续跑的是：

- 旧现场里 `tkt_dfbbd286b444/backlog_recommendation.json`
- 没有 `implementation_handoff`
- 当前 controller 读取 canonical backlog artifact 时会直接按严格 contract 拒绝

现场证据：

- `backend/data/scenarios/library_management_autopilot_live/artifacts/reports/governance/tkt_dfbbd286b444/backlog_recommendation.json`
- payload 顶层没有 `implementation_handoff`
- sections 里也没有足够的 machine-readable handoff 结构可以直接接回当前主线

所以这轮对 004 的判断是：

- 不是 provider 不可用
- 也不是新 key 继续复现旧版 `HIRE_EMPLOYEE`
- 而是 **004 的旧 backlog 产物本身已经不满足当前 runtime contract**

这意味着：

- 004 不适合继续拿来验证当前主线
- 直接切 005 clean rerun 更合理

---

## 2. 005 重跑里遇到的问题和修复

### 问题 A：live harness 直接把 `default_provider_id` 发给了 `runtime-provider-upsert`

首轮 005 runner 一启动就退出。

报错：

- `runtime-provider-upsert failed`
- `default_provider_id` 被命令合同判成 `extra_forbidden`

根因：

- `backend/data/integration-test-provider-config.json` 现在包含 `default_provider_id`
- 但 `RuntimeProviderUpsertCommand` 不接受这个字段
- live harness 的 `load_integration_test_provider_payload()` 之前会把整份模板原样拿去 upsert

实施改动：

- `backend/tests/live/_autopilot_live_harness.py`
  - 在 `load_integration_test_provider_payload()` 里显式 `pop("default_provider_id", None)`
- `backend/tests/live/library_management_resume_or_rerun.py`
  - 新增 `build_runtime_provider_upsert_payload()`，把配置态字段和命令态字段分开
- `backend/tests/test_live_library_management_runner.py`
  - 补了 `default_provider_id` 剥离回归测试

这次修完后：

- CLI runner 和 004 preflight 走的是同一条正确 upsert 口径

### 问题 B：CEO kickoff prompt 仍在诱导 provider 产出旧版 `CREATE_TICKET` payload

第二轮 005 能启动，但很快打开了：

- `CEO_SHADOW_PIPELINE_FAILED`

第一次具体报错是：

- `CREATE_TICKET.payload.workflow_id` 缺失
- 同时还带了旧散字段：
  - `dependency_gate_refs`
  - `source_ticket_id`
  - `source_node_id`
  - `required_capability_tags`
  - `assignee_employee_id`

这说明：

- 旧版 kickoff `CREATE_TICKET` 结构没有完全从 prompt 里清干净

第一次修复：

- `backend/app/core/ceo_prompts.py`
  - 把 `CREATE_TICKET` 的禁止字段写进 system prompt
  - 明确要求：
    - `assignee_employee_id / dependency_gate_refs` 只能放进 `dispatch_intent`
    - `required_capability_tags` 只能放进 `execution_contract`
- `backend/tests/test_ceo_scheduler.py`
  - 新增 kickoff prompt contract 回归测试

第三轮 005 再跑时，又暴露出一个更窄的漏口：

- 旧散字段不再乱塞了
- 但 provider 仍然会漏：
  - `workflow_id`
  - `dispatch_intent.selection_reason`

第二次修复：

- `backend/app/core/ceo_prompts.py`
  - 进一步加硬约束：
    - `CREATE_TICKET` 不得缺 `workflow_id / node_id / role_profile_ref / output_schema_ref / execution_contract / dispatch_intent / summary / parent_ticket_id`
    - `dispatch_intent.selection_reason` 不能省
- `backend/tests/test_ceo_scheduler.py`
  - 同一条 prompt contract 测试加了这两个断言

修完之后，第三轮 005 才真正跨过 kickoff。

### 问题 C：`NO_ACTION` 仍会回流成旧版顶层 `reason`

第三轮 005 跑起来后，第一张 `architecture_brief` maker 票已经完成。

但在它完成后的下一次 CEO shadow，又出现了新的旧格式回流：

- `provider_action_batch[payload_missing]: NO_ACTION must include payload.`

这说明：

- `CREATE_TICKET` 合同已经明显收紧成功
- 但 `NO_ACTION` 仍然会偶发回到旧版顶层 `reason`

实施改动：

- `backend/app/core/ceo_prompts.py`
  - 新增明确约束：
    - `NO_ACTION` 必须带 `payload.reason`
    - 不能再用顶层 `reason`
- `backend/tests/test_ceo_scheduler.py`
  - 把同一条 kickoff prompt contract 测试继续扩成 `NO_ACTION` 约束回归

修完后，第四轮 005 才重新回到无 incident 的执行态。

---

## 3. Probe 时间线

原始 probe 落盘目录：

- `.tmp/integration-monitor/live-005-20260419/`

本轮关键 probe：

### [2026-04-19 14:58:55 +08:00]

- workflow：`wf_472156ae6ee1`
- stage：`project_init`
- 005 第一次真正起跑

### [2026-04-19 15:01:15 +08:00]

- 打开 `CEO_SHADOW_PIPELINE_FAILED`
- 原因是 kickoff `CREATE_TICKET` 仍然带旧散字段

### [2026-04-19 15:04:43 +08:00]

- workflow：`wf_1222421be0c2`
- 第二次重启 005

### [2026-04-19 15:07:10 +08:00]

- 又一次 `CEO_SHADOW_PIPELINE_FAILED`
- 这次旧散字段已经收掉
- 但 `workflow_id` 和 `dispatch_intent.selection_reason` 仍然会漏

### [2026-04-19 15:12:21 +08:00]

- workflow：`wf_5dd07a50a4a4`
- 第三次重启 005
- 进入 `project_init`

### [2026-04-19 15:14:37 +08:00]

- workflow：`wf_5dd07a50a4a4`
- stage：`plan`
- 首张票 `tkt_wf_5dd07a50a4a4_ceo_architecture_brief` 进入 `EXECUTING`

### [2026-04-19 15:16:59 +08:00]

- workflow：`wf_5dd07a50a4a4`
- 当前 stage 显示为 `project_init`
- 但第一张 `architecture_brief` maker 票已经 `COMPLETED`
- 同节点的后继票 `tkt_97b240a9863c` 已经 `PENDING`
- provider 事件链已确认：
  - `PROVIDER_ATTEMPT_STARTED`
  - `PROVIDER_FIRST_TOKEN_RECEIVED`
  - `PROVIDER_ATTEMPT_FINISHED`
  - `TICKET_COMPLETED`

这说明：

- provider 现在已经真正工作
- kickoff 票已经不再被旧 payload 合同打爆
- 005 主线已经开始产出治理链票据

### [2026-04-19 15:19:13 +08:00]

- workflow 仍是 `wf_5dd07a50a4a4`
- 第一张 `architecture_brief` maker 票保持 `COMPLETED`
- 但又新开一条 `CEO_SHADOW_PIPELINE_FAILED`
- 这次具体原因是旧版 `NO_ACTION.reason` 回流，没有包进 `payload`

### [2026-04-19 15:23:50 +08:00]

- workflow：`wf_db5a68bd7ffa`
- stage：`plan`
- 当前没有 open incident
- 首张票 `tkt_wf_db5a68bd7ffa_ceo_architecture_brief` 正在 `EXECUTING`
- provider 事件已经重新开始：
  - `PROVIDER_ATTEMPT_STARTED`

这说明第四轮 005 至少已经满足两点：

- 不再在 kickoff 后立刻掉回旧版 `NO_ACTION` 结构
- 主线重新回到可继续观测的 live provider 执行态

### [2026-04-19 15:32:41 +08:00]

- workflow：`wf_db5a68bd7ffa`
- stage：`plan`
- 当前没有 open incident
- 当前票据状态：
  - `tkt_wf_db5a68bd7ffa_ceo_architecture_brief` `COMPLETED`
  - `tkt_94fb6dd8ba4b` `COMPLETED`
  - `tkt_30aec15c9aad` `EXECUTING`
- 最新 provider 现场：
  - `15:29:30 +08:00` `PROVIDER_ATTEMPT_STARTED`
  - `15:32:41 +08:00` `PROVIDER_FIRST_TOKEN_RECEIVED`
- 当前最新 CEO shadow run 仍是 `OPENAI_RESPONSES_STREAM_LIVE / HEALTHY`

这说明：

- 之前那几轮 prompt 合同修复已经起效
- 主线没有再掉回 `CEO_SHADOW_PIPELINE_FAILED`
- 现在已经进入连续治理文档执行，而不是“起步即炸”的状态

### [2026-04-19 15:58:52 +08:00]

- workflow：`wf_db5a68bd7ffa`
- stage：`project_init`
- 当前没有 open incident
- 当前票据状态：
  - `tkt_275c603dc216` `COMPLETED`
  - `tkt_592cb998b065` `EXECUTING`
- 节点推进：
  - `node_ceo_milestone_plan` 已完成
  - `node_ceo_detailed_design` 已进入执行
- 最新 provider 现场：
  - `15:53:35 +08:00` `PROVIDER_ATTEMPT_STARTED`
  - `15:54:38 +08:00` `PROVIDER_FIRST_TOKEN_RECEIVED`
  - `15:56:33 +08:00` `PROVIDER_ATTEMPT_FINISHED`
  - `15:58:52 +08:00` 新一轮 `PROVIDER_ATTEMPT_STARTED`
- 当前仍没有 provider failover、run_report 或 failure snapshot

这说明：

- 治理链已经越过 `milestone_plan`
- 当前已经正式推进到 `detailed_design`
- 主线依然保持“连续完成 + 无 incident”的稳定状态

### [2026-04-19 16:05:03 +08:00]

- workflow：`wf_db5a68bd7ffa`
- stage：`project_init`
- 当前没有 open incident
- 当前票据状态：
  - `tkt_592cb998b065` `COMPLETED`
  - `tkt_cce741c4aba3` `COMPLETED`
  - `tkt_f9b48faf4f22` `PENDING`
- 节点推进：
  - `node_ceo_detailed_design` 已完成
  - `node_ceo_backlog_recommendation` 已完成并已挂出后继 pending 票
- 最新 provider 现场：
  - `16:02:31 +08:00` `PROVIDER_ATTEMPT_STARTED`
  - `16:03:58 +08:00` `PROVIDER_FIRST_TOKEN_RECEIVED`
  - `16:05:03 +08:00` `PROVIDER_ATTEMPT_FINISHED`
- 当前仍没有 provider failover、run_report 或 failure snapshot

这说明：

- 治理链已经正式推进到 `backlog_recommendation`
- 这条 live 长测已经越过前面几轮一直卡住的治理主线阶段
- 接下来最关键的是看 `backlog_recommendation` 产物能不能在当前严格 contract 下稳定驱动 implementation fanout

### [2026-04-19 16:10:19 +08:00]

- workflow：`wf_db5a68bd7ffa`
- 当前没有 open incident
- 但这 5 分钟里出现过一轮新的：
  - `INCIDENT_OPENED`
  - `CIRCUIT_BREAKER_OPENED`
  - `INCIDENT_RECOVERY_STARTED`
  - `CIRCUIT_BREAKER_CLOSED`
  - `INCIDENT_CLOSED`
- 对应 CEO shadow run：
  - `ceo_d02b1278e047`
  - `effective_mode = SHADOW_ERROR`
  - `fallback_reason = provider_action_batch[action_type_missing]: Each provider action must include action_type or type.`
- 随后：
  - `ceo_3564b1201d61`
  - `effective_mode = OPENAI_RESPONSES_STREAM_LIVE`
  - `provider_health_summary = HEALTHY`

同时这轮主线也继续往前推进了：

- `tkt_f9b48faf4f22` `COMPLETED`
- 对应仍在 `node_ceo_backlog_recommendation`

这说明：

- `backlog_recommendation` 主线本身还在继续推进
- 但实现扇出前，provider 又吐出一版缺 `action_type` 的 action batch
- 这次没有把主线永久打停，`ceo_delegate` 已经自动恢复并关闭 incident
- 当前真正需要继续盯的是：恢复之后能不能稳定从 `backlog_recommendation` 走进 implementation fanout，而不是再反复开关 incident

### [2026-04-19 16:16:06 +08:00]

- workflow：`wf_db5a68bd7ffa`
- 当前没有 open incident
- 但这 5 分钟里又出现过两轮新的：
  - `INCIDENT_OPENED`
  - `CIRCUIT_BREAKER_OPENED`
  - `INCIDENT_RECOVERY_STARTED`
  - `CIRCUIT_BREAKER_CLOSED`
  - `INCIDENT_CLOSED`
- 两次对应的 CEO shadow run 分别是：
  - `ceo_b72b9cf8023d`
  - `ceo_5615238ad661`
- 两次 `fallback_reason` 都指向同一类问题：
  - `actions.0.HIRE_EMPLOYEE.payload.workflow_id`
  - `Field required`

也就是说：

- 现在 provider 在 implementation fanout 前，又开始回流旧版 `HIRE_EMPLOYEE` 结构
- 这次不是缺 `action_type`
- 而是 `HIRE_EMPLOYEE` payload 缺 `workflow_id`

现场特征：

- `backlog_recommendation` 主线票 `tkt_f9b48faf4f22` 已完成
- 之后没有出现新的 implementation fanout ticket
- `integration-monitor-report.md` 连续记录的是：
  - active tickets = `none`
  - incidents = `1`
  - 然后自动恢复
  - 再次进入同样循环

这说明：

- 当前最关键的新阻塞点，已经从治理链 contract 转移到 implementation fanout 前的 `HIRE_EMPLOYEE` action contract
- 自动恢复还在工作
- 但自动恢复现在更像“止血回路”，还没有真正把实现扇出打开

### [2026-04-19 16:23:07 +08:00]

- workflow：`wf_db5a68bd7ffa`
- 当前没有 open incident
- 当前出现了新的 open approval：
  - `apr_4268a4f23f7b`
  - `approval_type = CORE_HIRE_APPROVAL`
- 审批内容已经不是抽象建议，而是明确的人事动作：
  - `emp_architect_governance`
  - `role_type = governance_architect`
  - `role_profile_refs = ["architect_primary"]`
  - `inbox_summary = Hire an architect before implementation fanout continues.`

这说明：

- implementation fanout 前的 staffing path 已经开始 materialize
- 当前 system 不只是“想招人”，而是已经把 architect 招聘走到了正式审批态
- 这比前面纯 incident 开关更往前一步

但同时也说明：

- implementation fanout 还没有直接打开
- 当前主线更像是先进入 architect staffing gate，而不是马上生成 implementation tickets

### [2026-04-19 16:23:07 之后]

- `apr_4268a4f23f7b` 仍然保持 `OPEN`
- 但 system 没有安静停在 approval gate
- 在 approval 已经存在的情况下，后台又继续出现了同类循环：
  - `16:17:11 +08:00` `ceo_9e2f1931f82a`
  - `16:19:41 +08:00` `ceo_b7a1635233ca`
  - `16:20:40 +08:00` `ceo_5d93c863fe2b`
- 其中前两轮仍然是：
  - `HIRE_EMPLOYEE.payload.workflow_id` 缺失
  - 然后自动 `RERUN_CEO_SHADOW`
  - 再自动关闭 incident

这说明：

- 当前 system 已经知道自己要进 staffing approval gate
- 但在 approval 挂起期间，idle maintenance 还会继续触发旧版 `HIRE_EMPLOYEE` proposal
- 所以这不只是“提示词偶发漂移”，而是“approval gate 前后的控制流没有完全收住”

### [2026-04-19 16:56:12 +08:00]

- `apr_4268a4f23f7b` 已经不再是 `OPEN`
- 当前 approval projection 状态已经变成：
  - `approval_type = CORE_HIRE_APPROVAL`
  - `status = APPROVED`
- 这条 staffing gate 已经继续往前 materialize 成真实票据：
  - `tkt_543c164dcb94`
  - `node_id = node_architect_governance_gate_tkt_cce741c4aba3`
  - `role_profile_ref = architect_primary`
  - `output_schema_ref = architecture_brief`
  - `dispatch_intent.assignee_employee_id = emp_architect_governance`
  - 当前状态 `COMPLETED`
- 同节点后继 review 票也已经挂出：
  - `tkt_00082f181950`
  - `role_profile_ref = checker_primary`
  - `output_schema_ref = maker_checker_verdict`
  - 当前状态 `PENDING`

这说明：

- system 已经不只是“卡在招聘审批”
- architect staffing gate 已经继续执行到一张真实 governance maker 票完成
- 后续已经进入对应的 checker review 挂票阶段

当前仍要注意的一点：

- incident projection 里还出现过一条 `RUNTIME_LIVENESS_UNAVAILABLE / RECOVERING`
- 但它没有阻止 architect gate 继续 materialize
- 这更像恢复态残留，而不是当前主阻塞

---

## 4. 当前状态

截至最后一针，当前 live 长测状态是：

- 运行中的 workflow：`wf_db5a68bd7ffa`
- 当前已经越过最早的 kickoff 建票阻塞
- 治理链已经连续完成 `architecture_brief -> technology_decision -> milestone_plan -> detailed_design -> backlog_recommendation`
- `backlog_recommendation` 后已连续出现：
  - 一次 `action_type_missing`
  - 多次 `HIRE_EMPLOYEE.payload.workflow_id missing`
- 这些 incident 都被自动恢复关闭
- `CORE_HIRE_APPROVAL` 已经从 `OPEN` 推进到 `APPROVED`
- architect governance gate 对应的 maker 票已完成，checker 票已挂起
- implementation fanout 仍未真正打开

当前最值得继续盯的不是 provider 可用性，而是：

1. `architecture_brief` 完成后，review lane 是否正常 materialize
2. 主线是否会稳定推进到 `technology_decision / milestone_plan / detailed_design / backlog_recommendation`
3. 进入 `backlog_recommendation` 后，新的严格 `implementation_handoff` 是否能稳定产出

---

## 5. 本轮改动清单

本轮为长测直接做过的代码/配置改动：

- `backend/data/integration-test-provider-config.json`
  - 新增并切换到 `prov_openai_compat_new_key`
  - 所有 live role 只绑定新 key provider
- `backend/tests/live/_autopilot_live_harness.py`
  - live provider 模板加载时剥离 `default_provider_id`
- `backend/tests/live/library_management_resume_or_rerun.py`
  - 新增 004 preflight / resume probe / single-provider payload helper
- `backend/app/core/ceo_prompts.py`
  - 三轮收紧 CEO prompt contract
  - 先修 kickoff `CREATE_TICKET` 旧散字段
  - 再修 `workflow_id / dispatch_intent.selection_reason` 漏口
  - 再修 `NO_ACTION.payload.reason` 旧格式回流
  - prompt version 升到 `ceo_shadow_v3`
- `backend/tests/test_live_library_management_runner.py`
  - 补 provider payload / upsert shape / probe helper 回归测试
- `backend/tests/test_ceo_scheduler.py`
  - 补 kickoff prompt contract 回归测试

---

## 6. 现在最短结论

这轮 005 到目前为止，最短结论可以收成一句话：

- 004 不是新 key 下的可恢复现场，已经被旧 backlog artifact contract 卡死
- 005 前三次重跑先后被 kickoff `CREATE_TICKET` 和 `NO_ACTION` prompt 漂移打断
- 三轮小修后，第四次 005 已经重新跑起来，并稳定推进到 `backlog_recommendation` 完成态；当前新的主风险仍是 implementation fanout 前的 CEO `HIRE_EMPLOYEE` action contract 漂移，但 staffing gate 已经从 `CORE_HIRE_APPROVAL` 继续推进到 architect governance gate 真票执行
