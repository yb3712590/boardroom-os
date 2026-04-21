# intergration-test-006-20260420

这份记录只保留第六轮长测真正有价值的内容：

- 现场真实出现过什么问题
- 当时做了什么改动
- 这些改动验证到哪一步
- 最后还留下了什么问题

不再保留逐针脉冲式 probe。

---

## 0. 测试目标

本轮场景固定为：

- 场景：`library_management_autopilot_live`
- workflow：`wf_e8e809fe5970`
- live 命令：
  - `./backend/.venv/bin/python -m tests.live.library_management_autopilot_live --max-ticks 180 --timeout-sec 7200`

本轮想验证的是：

- 新 live provider 能不能把 `library_management_autopilot_live` 真正跑进主线
- CEO fine-grained graph runtime 能不能从治理链推进到实现、检查、收口
- 现场出现小卡点时，是否能通过最小修补把主线继续推下去

本轮真相源以这些为准：

- `backend/data/scenarios/library_management_autopilot_live/boardroom_os.db`
- `backend/data/scenarios/library_management_autopilot_live/integration-monitor-report.md`
- `backend/data/scenarios/library_management_autopilot_live/audit-summary.md`
- `backend/data/scenarios/library_management_autopilot_live/run_report.json`
- `backend/data/scenarios/library_management_autopilot_live/failure_snapshots/`
- 最新 `ceo_shadow_run` / `workflow_projection` / `ticket_projection` / `approval_projection` / `incident_projection`

---

## 1. 最终持久现场

截至这轮收口时，最后一个真正写进数据库并能稳定复现的现场是：

- workflow：`wf_e8e809fe5970`
- status：`EXECUTING`
- current stage：`check`
- 最新持久事件时间：`2026-04-21 02:50:12 +08:00`
- 没有 active ticket
- open approval：`0`
- `incident_projection` 里仍有两条 `RECOVERING`
  - `PROVIDER_EXECUTION_PAUSED`
  - `RUNTIME_LIVENESS_UNAVAILABLE`

`run_report.json` 的最后稳定结果是：

- `completion_mode=timeout`
- `failure_mode=timeout`
- `provider_attempt_count=8`

后面又做过几次不 `clean` 的恢复拉起，但这些新进程没有把主线事件继续往前写出来，最后都没有形成新的持久现场结论。

---

## 2. 已确认问题与当时改动

### 问题 A：默认 live provider 模板文件缺失

场景：

- `library_management_autopilot_live` 入口已经切到 `backend/data/integration-test-provider-config.json`
- 仓库里最开始没有这份模板

影响：

- 场景起不来
- 也没法保证“本轮只用新 live provider”这个口径

当时改动：

- 新增 `backend/data/integration-test-provider-config.json`
- 全部 role binding 只指向 `prov_openai_compat_truerealbill::gpt-5.4`
- timeout 和 retry backoff 固定到 live 口径

验证：

- 默认 live provider 模板已能落盘到场景目录
- provider chain 确实命中新 live provider

状态：

- 当时问题已解决
- 后续 `006` 前置会话 A 已继续收口：
  - 自动主线 `HIRE_EMPLOYEE` 不再经过 `CORE_HIRE_APPROVAL`
  - CEO 自动招聘现在直接把 active employee 写进 roster
  - 手工 `employee-hire-request` 仍保留审批链

### 问题 B：OpenAI Python SDK 未安装

场景：

- 首轮 workflow 在 `project_init` 直接开 incident
- incident payload 明确给出：
  - `error_class=OpenAICompatProviderUnavailableError`
  - `error_message=OpenAI Python SDK is not installed.`

影响：

- workflow 连 kickoff 都过不去

当时改动：

- 在 `backend/.venv` 安装 `openai>=2.0,<3.0`

验证：

- clean rerun 后，不再在 `project_init` 立刻因为 SDK 缺失失败

状态：

- 当时问题已解决

### 问题 C：live provider 偶发回流旧 `CREATE_TICKET` 协议

场景：

- live provider 偶尔返回旧形态的 `CREATE_TICKET`
- 典型表现是：
  - `dispatch_intent.selection_reason` 缺失
  - 或 `execution_contract` 不完整

影响：

- provider proposal 会在 contract 校验阶段直接炸
- CEO shadow 后续只能走 fallback 或开 incident

当时改动：

- 收紧 `CREATE_TICKET` 的 payload 归一化
- 对 `selection_reason` 和 `execution_contract` 做最小补齐

验证：

- 当时相关回归都能过

状态：

- 这条问题当时被压住
- 但后来发现硬切只补到了 `CREATE_TICKET`，没补齐 `RETRY_TICKET`

### 问题 D：`CORE_HIRE_APPROVAL` 批准链不顺

场景：

- architect / backend 的核心招聘变更需要董事会批准
- 当时 CEO 代董事会批准链没有完整收口

影响：

- staffing change 会停在 approval 上
- 后面的治理 / 实现链都起不来

当时改动：

- 修 `CORE_HIRE_APPROVAL` 的批准链

验证：

- 现场后续能看到：
  - `apr_2d10ca6fedf5`
  - `apr_a5b96680cdef`
  - 两条审批都进入 `APPROVED`
- `emp_architect_governance`
- `emp_backend_backup`
  - 都被真正雇入 roster

状态：

- 当时问题已解决

### 问题 E：runtime liveness 误判 workflow 级 board review

场景：

- workflow 级 `CORE_HIRE_APPROVAL`
- 会被 runtime liveness 当成 runtime blocker

影响：

- 主线被错误打成 liveness 不可用
- 出现与真实运行态不一致的 incident

当时改动：

- 修 runtime liveness 对 workflow 级 board review 的误判

验证：

- 相关 live runner 回归通过

状态：

- 当时问题已解决

### 问题 F：live harness 的恢复能力不完整

场景：

- live harness 恢复 delegate blocker 不稳定
- `clean=False` resume 也不够可靠

影响：

- 现场已经有场景目录时，续跑经常恢复不到正确 workflow

当时改动：

- 修 live harness 的 delegate blocker 恢复
- 修 `clean=False` resume

验证：

- 当时相关 runner 回归通过

状态：

- 当时问题已解决

### 问题 G：follow-up plan 把治理 / checker 条目错误映射成 `source_code_delivery`

场景：

- `capability_plan.followup_ticket_plans` 里
- 一批治理 / checker 条目被误落成 `source_code_delivery`
- 还伴随 `assignee_employee_id=null`

影响：

- controller 会误判为缺 `architect_primary` / `checker_primary`
- 然后反复要求 `HIRE_EMPLOYEE`
- 又被“画像太相似”的保护拦掉
- workflow 困在错误 staffing gap 闭环里

当时改动：

- `workflow_controller` 把 follow-up schema 最小收正为：
  - `architect_primary -> architecture_brief`
  - `checker_primary -> delivery_check_report`
  - 实现角色才继续用 `source_code_delivery`

验证：

- 当时相关 `test_ceo_scheduler.py`
- `test_live_library_management_runner.py`
  - 都通过

状态：

- 这条根因当时被明确并修过

### 问题 H：`BR-003 source_code_delivery` 的 live provider 请求形态不兼容 upstream

场景：

- workflow 进入 `build` 后，`tkt_cfdfccdd5432 / node_backlog_followup_br_003`
- 不再是“没 active ticket”
- 而是已经起跑
- 但 provider 连续返回：
  - `UPSTREAM_UNAVAILABLE`
  - `502 upstream_error`

请求级复现结论：

- 最小 `/responses` 请求正常
- 直接回放 `tkt_cfdfccdd5432` 的真实请求会稳定 `502`
- 问题不在 provider 全挂，而在请求形态

当时做过的修补：

- 对 `source_code_delivery` 禁掉 strict `json_schema`
- 压缩 system instructions
- 避免把完整 schema body 和重复 contract 大包再塞给 upstream

验证到的结果：

- 新请求不再像旧请求那样在 `0.xs` 内直接 `502`
- provider 回放能进入正常生成时长
- 相关 provider / live runner 回归通过

状态：

- 这是 live 过程中做过的修补
- 本次收口按你的要求，**代码层面已丢弃**
- 只在这里保留问题和当时尝试的记录

### 问题 I：流式 timeout 语义被错误实现成墙钟总时长

场景：

- 你明确要求的是：
  - 流式请求里看“最后一次收到返回”后的超时
- 但当时实现实际写成了：
  - 从请求发起开始，整次墙钟超过 `request_total_timeout_sec` 就超时

影响：

- `BR-001 / node_backlog_followup_br_001 / tkt_162554078b19`
- 这种治理票首 token 本来就慢
- 经常在 `240s~260s` 才开始流
- 然后在 `300s` 左右被错误打成 `REQUEST_TOTAL_TIMEOUT`

当时做过的修补：

- 把流式阶段改成只看：
  - `FIRST_TOKEN_TIMEOUT`
  - `STREAM_IDLE_TIMEOUT`

验证到的结果：

- provider 回归通过

状态：

- 这是 live 过程中做过的修补
- 本次修补已把这条语义正式补回代码
- 当前 streaming timeout 口径是：
  - `FIRST_TOKEN_TIMEOUT` 只看首 token 前等待
  - `STREAM_IDLE_TIMEOUT` 只看最后一次输出后的静默等待
  - 不再把 `request_total_timeout_sec=300` 当成流式墙钟总时长
- 定向验证已覆盖：
  - 长流持续输出不误触发总时长 timeout
  - 首 token timeout
  - stream idle timeout

### 问题 J：`RETRY_TICKET` 协议硬切不完整

场景：

- 前几轮硬切了 action 协议
- 但只把 `CREATE_TICKET` 的兼容修补做完整
- `RETRY_TICKET` 还会出现 provider 返回：
  - `ticket_id` 正确
  - `node_id` 缺失

影响：

- `CEOActionBatch.model_validate(...)` 在 proposer 阶段直接炸
- 后续掉进 deterministic fallback

当时做过的修补：

- 在 proposer 里加了最小归一化：
  - `RETRY_TICKET` 缺 `node_id`
  - 但 `ticket_id` 可在 projection 查到
  - 就反填 `node_id`

验证到的结果：

- 新增回归能通过

状态：

- 这是 live 过程中做过的修补
- 本次收口按你的要求，**代码层面已丢弃**
- 这里只保留问题和当时尝试记录

### 问题 K：当前自动恢复语义更像 rerun proposer，不像 incident-driven restore/retry

场景：

- `CEO_SHADOW_PIPELINE_FAILED`
- 当前默认恢复路径更偏向：
  - `RERUN_CEO_SHADOW`
- 而不是优先：
  - `RESTORE_AND_RETRY_*`

影响：

- 上游根票失败后
- 系统会先重问一次 proposer
- provider proposal 一旦再次不合法
- 就会继续掉进 deterministic fallback
- 而不是直接幂等恢复最上游失败票

这轮没有正式改它，只把建议方向收口如下：

- `CEO_SHADOW_PIPELINE_FAILED` 不要先 rerun proposer
- 优先按 incident 类型走 `RESTORE_AND_RETRY_*`
- 至少对上游根票失败这类场景
  - 先恢复 ticket
  - 再决定要不要重问 CEO shadow

状态：

- 这是当前仍然保留的设计问题
- 只记录建议，不在本轮做代码修补

---

## 3. 最后稳定失败链

最后真正稳定写入数据库的失败链是：

- 上游根票：
  - `tkt_162554078b19`
  - `node_backlog_followup_br_001`
  - `architecture_brief`
- 这张票反复超时 / 失败后，耗尽 retry budget
- 然后下游一串 follow-up 票因为 `dependency_gate_refs` 指向它而连锁失败：
  - `tkt_135316963abb` `BR-002`
  - `tkt_1aa760cdda9a` `BR-020`
  - `tkt_f3322bfdab15` `BR-021`
  - `tkt_93d456c03bd4` `BR-022`
  - `tkt_c31a0eab3270` `BR-023`

这些下游票的共同失败形态是：

- `DEPENDENCY_GATE_UNHEALTHY`

同时，CEO shadow 还会反复出现两类高层故障：

- `ExecutionFailed`
  - 根因是上游 retry budget 已耗尽
- `CEOProposalContractError`
  - 根因是
    - `deterministic_fallback.backlog_followup[no_actions_built]`

---

## 4. 本轮仍然留下的问题

当前真正还没解决的，不再是“单一 provider 502”。

留下的问题主要有四类：

1. 上游根票恢复语义不对

- `CEO_SHADOW_PIPELINE_FAILED`
- 现在更偏 rerun proposer
- 不是 incident-driven restore/retry

2. 上游根票失败后，retry budget 很快耗尽

- 一旦根票失败预算打空
- 后面 CEO shadow 即使判断“应该 retry”
- 执行也会被拒掉

3. 下游 follow-up 会被依赖门连锁拖死

- 依赖的是失败根票
- 所以下游大量票直接 `DEPENDENCY_GATE_UNHEALTHY`

4. fallback 在“已有 existing_ticket_id + 依赖链已坏”时没有恢复出口

- `_build_backlog_followup_batch()` 会发现没有任何新 action 可构
- 然后抛：
  - `no_actions_built`

补记：

- `006` 前置会话 A 已完成
- 自动主线里的 staffing blocker 不再表现为 `CORE_HIRE_APPROVAL` 挂起
- 后续会话 1 到 5 可以按“恢复语义 / retry budget / dependency gate / fallback”继续拆开处理

---

## 5. 这次收口时的处理原则

按本次要求，这里明确记录最终处理动作：

- `006` 日志已重写
  - 只保留问题、改动、验证、剩余问题
  - 删除了脉冲式 probe 信息
- live 过程中做的代码修补，已决定全部丢弃
  - 包括：
    - `source_code_delivery` 请求形态修补
    - streaming timeout 语义修补
    - `RETRY_TICKET.node_id` 反填修补

也就是说：

- 这份日志保留了问题和当时做过什么
- 但不主张把这些 live 补丁继续留在当前工作树里
