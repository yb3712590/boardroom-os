# intergration-test-007-20260422

这份记录只保留这轮长测真正有价值的内容：

- 本轮测试想验证什么
- 实际怎么跑的
- 运行中遇到了什么问题
- 每个问题怎么修、验证到哪一步
- 最后为什么没进实现链

不再保留按分钟刷屏的探针记录。

---

## 0. 测试目标

本轮场景固定为：

- 场景：`library_management_autopilot_live`
- 目标：极简图书流转终端
- live 命令：
  - `/Users/bill/projects/boardroom-os/backend/.venv/bin/python -m tests.live.library_management_autopilot_live --clean --max-ticks 180 --timeout-sec 7200`

本轮要验证的是：

- live 场景是否已经从“大而全图书馆系统”收口到匿名、单机、单表 `books` 的极简终端
- runtime 默认 backlog 是否不再把 Agent 拉回 Auth / RBAC、预约、罚金、报表、运维这些旧模块
- 新 provider `prov_openai_compat_truerealbill` 是否能作为唯一 provider 把主线推进到实现链
- 运行中如果遇到小卡点，最小修补后主线能不能继续向前

本轮 provider 口径：

- provider id：`prov_openai_compat_truerealbill`
- base url：`http://codex.truerealbill.com:11234/v1`
- model：`gpt-5.4`
- fallback：`[]`

本轮真相源以这些为准：

- `backend/data/scenarios/library_management_autopilot_live/boardroom_os.db`
- `backend/data/scenarios/library_management_autopilot_live/runtime-provider-config.json`
- `backend/data/scenarios/library_management_autopilot_live/integration-monitor-report.md`
- `backend/data/scenarios/library_management_autopilot_live/audit-summary.md`
- `backend/data/scenarios/library_management_autopilot_live/run_report.json`
- `backend/data/scenarios/library_management_autopilot_live/failure_snapshots/timeout.json`

---

## 1. 开始前做了什么

这轮不是直接开跑。

开跑前先把测试入口和默认行为一起收口：

- `library_management_autopilot_live` 的 goal / constraints / outcome 断言改成“极简图书流转终端”
- `library_management_autopilot_smoke` 同步改成同一套场景常量
- `runtime.py` 里的默认 backlog 改成最小实现链：
  - 终端风 UI
  - `books` 单表
  - `Add / Check Out / Return / Remove`
  - 列表展示
  - 最小验证
  - closeout 证据
- 默认 live provider 模板固定为这次的新 provider，所有 binding 只指向 `prov_openai_compat_truerealbill::gpt-5.4`

开跑前的定向验证结果：

- `backend/tests/test_live_library_management_runner.py`
- `backend/tests/test_runtime_fallback_payload.py`
- `backend/tests/test_persona_profiles.py`
- `backend/tests/test_ceo_scheduler.py -k backfills_missing_dispatch_selection_reason`

最终相关定向回归收口为：

- `46 passed, 105 deselected`

---

## 2. 实际运行经过

### 第一段：场景成功切到新 provider 和新约束

clean rerun 后，场景目录正常重建，`runtime-provider-config.json` 也按预期落盘：

- `default_provider_id=prov_openai_compat_truerealbill`
- 所有 `role_bindings` 都指向 `prov_openai_compat_truerealbill::gpt-5.4`
- `fallback_provider_ids=[]`

首张治理票的上下文归档也已经明确写入新的极简约束，说明输入流确实切到了：

- 匿名 / 单机
- `books` 单表
- `IN_LIBRARY / CHECKED_OUT`
- `Add / Check Out / Return / Remove`
- 终端风 UI

### 第二段：治理链本身能往前走

修补早期兼容问题后，主线一度能连续推进治理链。

这轮实际完成过的治理输出包括：

- `architecture_brief`
- `technology_decision`
- `milestone_plan`
- `detailed_design`
- `backlog_recommendation`
- 一轮 `architect_governance_gate` 补充治理票

provider 侧也比之前健康很多：

- 最近多张治理票都只有单次 attempt
- 每次都有
  - `PROVIDER_ATTEMPT_STARTED`
  - `PROVIDER_FIRST_TOKEN_RECEIVED`
  - `PROVIDER_ATTEMPT_FINISHED`
- 这轮没有再出现早期那种“attempt 起了但不收口”的问题

### 第三段：治理链结束后没有进入实现链

问题出在这里。

虽然治理票都完成了，但 workflow 没有进入 `build` 或 `check`，而是长期停在：

- `workflow_id=wf_0823f6909bb5`
- `status=EXECUTING`
- `current_stage=project_init`

后半段现场的典型形态是：

- 没有 active ticket
- 没有 open approval
- 主线不生成实现票
- 事件数持续增长
- 定时触发 `CEO_SHADOW_PIPELINE_FAILED`
- incident 会自动恢复、自动关闭，然后下一轮 maintenance 再次打开

也就是说，系统不是“彻底死掉”，而是进入了“治理已完成，但 CEO shadow proposal 校验不停打回”的循环。

---

## 3. 运行中遇到的问题和修法

### 问题 A：默认 roster seed 仍写旧 provider id

场景：

- 第一轮 clean live 启动后
- 场景配置已经是 `prov_openai_compat_truerealbill`
- 但 bootstrap `EMPLOYEE_HIRED` 事件仍写 `provider_id=prov_openai_compat`

影响：

- “本轮只用新 provider” 这个真相被污染
- 虽然不一定立刻阻塞执行，但现场口径不一致

改动：

- `backend/app/core/persona_profiles.py`
  - `build_default_employee_roster()` 增加 `BOARDROOM_OS_DEFAULT_EMPLOYEE_PROVIDER_ID`
- `backend/app/db/repository.py`
  - 初始化 bootstrap roster 时不再吃导入时静态常量，改成运行时调用
- `backend/tests/live/_autopilot_live_harness.py`
  - live 环境里把当前 provider id 注入 `BOARDROOM_OS_DEFAULT_EMPLOYEE_PROVIDER_ID`

验证：

- 新增 `backend/tests/test_persona_profiles.py` 定向回归
- rerun 后，bootstrap `EMPLOYEE_HIRED` 已稳定写成：
  - `provider_id=prov_openai_compat_truerealbill`
  - `bootstrap_source=default_roster_seed`

状态：

- 这条问题已解决

### 问题 B：CEO shadow proposal 回流旧 `dispatch_intent` 形态

场景：

- 第一轮 clean live 跑完 `architecture_brief` 后
- 自动维护阶段打开 `CEO_SHADOW_PIPELINE_FAILED`

现场证据：

- `error_class=ValidationError`
- 报错点是：
  - `actions.0.CREATE_TICKET.payload.dispatch_intent.selection_reason`
  - `Field required`

影响：

- incident 会自动恢复并关闭
- 但 workflow 会被打回 `project_init`

改动：

- `backend/app/core/ceo_proposer.py`
  - 在 `_normalize_provider_action_batch_payload()` 里补旧协议兼容
  - 如果 `CREATE_TICKET.dispatch_intent` 里有 `assignee_employee_id`，但缺 `selection_reason`
  - 自动补默认 `selection_reason`

验证：

- 新增 `backend/tests/test_ceo_scheduler.py::test_provider_action_batch_backfills_missing_dispatch_selection_reason`
- rerun 后，这条 `selection_reason` 缺失问题没有再复现

状态：

- 这条问题已解决

### 问题 C：CEO shadow proposal 又回流旧 `execution_contract` 形态

这是本轮最后真正卡死主线的根因。

场景：

- 治理链跑完后
- workflow 没进入实现链
- 后台 maintenance 持续触发 CEO shadow proposal
- proposal 里的 `CREATE_TICKET.execution_contract` 又回流了一套旧结构

现场证据：

重复出现的 `CEO_SHADOW_PIPELINE_FAILED` 里，常见报错包括：

- 缺字段：
  - `execution_target_ref`
  - `runtime_contract_version`
- 多余旧字段：
  - `task_name`
  - `scope`
  - `objective`
  - `hard_constraints`
  - `acceptance_criteria`

有些轮次还会把旧字段带到 `dispatch_intent`：

- `dependency_ticket_keys`
- `source_ticket_id`
- `source_node_id`
- `ticket_key`

影响：

- provider proposal 每分钟左右都会在 contract 校验阶段被拒
- incident 打开后会自动 `RERUN_CEO_SHADOW`
- 但 rerun 仍回流同一类旧 payload
- 所以系统形成“打开 incident -> 自动恢复 -> 再次打开”的死循环
- workflow 始终停在 `project_init`
- 从头到尾没有进入 `build` 或 `check`

状态：

- 这条问题在本轮**没有修**
- 它是这轮 timeout 的直接根因

---

## 4. 最终结果

这轮长测最后已经形成正式终态文件，不再是中途观察。

`run_report.json` 的结论：

- `success=false`
- `completion_mode=timeout`
- `failure_mode=timeout`
- `workflow_id=wf_0823f6909bb5`
- `elapsed_sec=6553.9`
- `finished_at=2026-04-22T03:43:07.744516+08:00`

`audit-summary.md` 的结论：

- workflow 最终仍是 `EXECUTING / project_init`
- 候选 provider 链始终只有：
  - `prov_openai_compat_truerealbill`
- 观测到的 provider attempt 是健康收口的
- 但主线没有任何代码和测试证据产出：
  - `Project code written: no`
  - `Test evidence written: no`
  - `Git evidence written: no`

本轮最终可以下这个判断：

- 场景约束已经收口成功
- 单 provider 口径已经收口成功
- provider attempt 审计链和收口能力比早期明显更健康
- 治理链可以推进
- 但治理之后的 CEO shadow proposal 仍会回流旧 `execution_contract` 结构
- 这让系统无法把 backlog recommendation 转成实现票
- 所以主线最终停在“治理完成，但实现链起不来”的循环里

---

## 5. 最后的卡点

最后真正卡死这轮长测的，不是 provider 超时，也不是 provider 坏响应。

最后卡点是：

- `CEO_SHADOW_PIPELINE_FAILED`
- `trigger_type=SCHEDULER_IDLE_MAINTENANCE`
- provider proposal 回流旧版 `CREATE_TICKET.execution_contract`
- contract 校验持续失败
- 系统自动 `RERUN_CEO_SHADOW`
- rerun 后继续回流同类旧 payload

所以这轮的结论很明确：

1. “极简图书流转终端”场景收口本身已经到位。
2. live provider 主路径也能稳定完成治理文档生成。
3. 真正没收完的，是 **治理结果落实现票时的 provider proposal 兼容层**。
4. 下一轮如果继续跑，不该再盯 provider stream timeout，而应该直接收 `CREATE_TICKET.execution_contract` 的旧协议兼容口。
