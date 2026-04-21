# intergration-test-006 分会话修补路线

这份文档只服务 `intergration-test-006-20260420.md`。

用途很简单：

- 把 006 剩余问题拆成多轮独立会话
- 每一轮只解决一类问题
- 每一轮都写清楚开工前必须知道的背景
- 每一轮都给出可以直接勾掉的清单

这份路线图**不是本轮实现记录**。
它的目标是让你后续每开一个新会话，都能只盯一件事，不被 006 的长链路问题重新带偏。

---

## 先看全局结论

006 当前剩余问题，真实上只剩四类：

1. `CEO_SHADOW_PIPELINE_FAILED` 的恢复语义不对  
   现在更像 `RERUN_CEO_SHADOW`，不是 incident-driven restore / retry。

2. 根票失败后，retry budget 很快打空  
   后面即使判断“应该恢复”，执行层也会拒掉。

3. follow-up 依赖门会连锁拖死下游  
   根票一挂，`BR-002 / 020 / 021 / 022 / 023` 一串直接 `DEPENDENCY_GATE_UNHEALTHY`。

4. backlog follow-up fallback 没有恢复出口  
   遇到“已有 `existing_ticket_id` + 依赖链已坏”时，只会掉进 `no_actions_built`。

所以后续不要按“模块”切会话。
要按“问题闭环”切会话。

推荐固定顺序：

1. 先修恢复语义
2. 再修 retry budget
3. 再收依赖门
4. 再补 fallback 恢复出口
5. 最后补 006 专项回归和一次最小回放

---

## 每轮开工前都要知道的背景

### 1. 006 真相源

先看这几份：

- `doc/tests/intergration-test-006-20260420.md`
- `backend/data/scenarios/library_management_autopilot_live/run_report.json`
- `backend/data/scenarios/library_management_autopilot_live/integration-monitor-report.md`
- `backend/data/scenarios/library_management_autopilot_live/audit-summary.md`

如果你这一轮需要查数据库现场，再看：

- `backend/data/scenarios/library_management_autopilot_live/boardroom_os.db`

### 2. 006 最后稳定现场

必须记住这几个点：

- workflow：`wf_e8e809fe5970`
- workflow status：`EXECUTING`
- current stage：`check`
- 没有 active ticket
- open approval：`0`
- incident 里还挂着 `RECOVERING`
  - `PROVIDER_EXECUTION_PAUSED`
  - `RUNTIME_LIVENESS_UNAVAILABLE`

### 3. 006 的根失败链

根票是：

- `tkt_162554078b19`
- `node_backlog_followup_br_001`
- `architecture_brief`

它反复 timeout / failure 后耗尽 retry budget。

之后下游一串 follow-up 被它连坐：

- `tkt_135316963abb` `BR-002`
- `tkt_1aa760cdda9a` `BR-020`
- `tkt_f3322bfdab15` `BR-021`
- `tkt_93d456c03bd4` `BR-022`
- `tkt_c31a0eab3270` `BR-023`

共同失败形态：

- `DEPENDENCY_GATE_UNHEALTHY`

### 4. 本路线明确不做什么

006 里提过的这些 live patch，当前**不作为默认修复方向**：

- `source_code_delivery` 请求形态修补
- streaming timeout 语义修补
- `RETRY_TICKET.node_id` 反填兼容补丁

原因很直接：

- 这些是 live 临场止血
- 不是这轮剩余主问题的根修复

如果后面某轮又碰到它们，单独立题，不要混到 006 主线修补里。

---

## 会话 1：先把 CEO shadow 恢复语义改对

### 这一轮只解决什么

只解决这一句：

- `CEO_SHADOW_PIPELINE_FAILED` 遇到“根票真实失败/超时”时，不要先走 `RERUN_CEO_SHADOW`

这轮不要顺手修 retry budget。
不要顺手修 dependency gate。
不要顺手修 fallback。

### 开工前必须知道的背景

- 006 里已经明确：当前自动恢复更像 rerun proposer
- 这会让系统再次去问 proposer
- provider proposal 再次不合法时，就会继续掉 fallback / incident
- 它没有先恢复最上游失败票

### 本轮目标

把 `CEO_SHADOW_PIPELINE_FAILED` 拆成两类：

1. 有真实源票的 incident  
   例如 `trigger_type` 指向 `TICKET_FAILED / TICKET_TIMED_OUT`

2. 没有真实源票的 incident  
   例如纯 proposer / contract / snapshot 类错误

只有第 2 类，才继续优先 `RERUN_CEO_SHADOW`。

第 1 类，要优先推荐对应的 `RESTORE_AND_RETRY_*`。

### 本轮建议先看的代码入口

- `backend/app/core/workflow_auto_advance.py`
- `backend/app/core/projections.py`
- `backend/app/core/ticket_handlers.py`

### 这一轮做完后要勾掉的清单

- [ ] `GET /api/v1/projections/incidents/:id` 能区分“有源票”还是“无源票”
- [ ] `CEO_SHADOW_PIPELINE_FAILED` 由 `TICKET_FAILED` 触发时，推荐动作不再是 `RERUN_CEO_SHADOW`
- [ ] `CEO_SHADOW_PIPELINE_FAILED` 由 `TICKET_TIMED_OUT` 触发时，推荐动作不再是 `RERUN_CEO_SHADOW`
- [ ] 纯 proposer / contract 错误仍然可以继续推荐 `RERUN_CEO_SHADOW`
- [ ] incident detail 至少能稳定看见：
  - `source_ticket_id`
  - `source_ticket_status`
  - `recommended_restore_action`

### 本轮验收口径

至少补两条定向回归：

- `TICKET_FAILED -> CEO_SHADOW_PIPELINE_FAILED -> RESTORE_AND_RETRY_LATEST_FAILURE`
- `TICKET_TIMED_OUT -> CEO_SHADOW_PIPELINE_FAILED -> RESTORE_AND_RETRY_LATEST_TIMEOUT`

---

## 会话 2：把 restore 接到 retry budget 语义上

### 这一轮只解决什么

只解决这一句：

- 根票 budget 打空后，incident-driven restore 仍然要有一次明确恢复出口

这轮默认不改 dependency gate。
也不碰 backlog fallback。

### 开工前必须知道的背景

- 006 的根票失败链已经证明：budget 会很快打空
- 一旦打空，后面即使系统判断“应该 retry”
- 执行层也会拒绝
- 所以“推荐动作为 restore”还不够
- 必须让 incident resolve 真能落成一次 follow-up ticket

### 本轮目标

复用现有 `RESTORE_AND_RETRY_*` 的 override 语义。

重点不是新增一套新命令。
而是让 `CEO_SHADOW_PIPELINE_FAILED` 这类 incident 也能：

- 找到源票
- 绕过已经耗尽的普通 retry budget 校验
- 生成一次受控的 follow-up ticket

### 本轮建议先看的代码入口

- `backend/app/core/ticket_handlers.py`
- 重点看：
  - `handle_incident_resolve(...)`
  - `_validate_restore_and_retry_*`
  - `_schedule_retry(...)`

### 这一轮做完后要勾掉的清单

- [ ] `CEO_SHADOW_PIPELINE_FAILED` 的 resolve 可以复用现有 `RESTORE_AND_RETRY_*`
- [ ] 源票 budget 已耗尽时，incident resolve 仍能接受一次恢复
- [ ] 恢复后会真正产出新的 follow-up ticket
- [ ] incident 状态能进入 `RECOVERING`
- [ ] 同一 failure fingerprint 已有 `OPEN/RECOVERING` incident 时，不再继续用 rerun 叠无效重试

### 本轮验收口径

至少补一条回归：

- `CEO_SHADOW_PIPELINE_FAILED + TICKET_TIMED_OUT + retry budget exhausted -> incident resolve accepted -> follow-up ticket created`

---

## 会话 3：把 dependency gate 从“连坐失败”改成“阻塞等待恢复”

### 这一轮只解决什么

只解决这一句：

- 依赖根票已失败但正在恢复时，下游不要直接进 `DEPENDENCY_GATE_UNHEALTHY`

这轮不要去修 CEO shadow fallback。

### 开工前必须知道的背景

006 当前最伤的不是“根票失败”本身。
而是根票一挂，下游一串 follow-up 全被拖死。

现在的坏处有两个：

1. 现场噪音变大  
   看起来像很多票都坏了，其实根因只有一张根票。

2. 恢复路径更难  
   根票一恢复，还得处理一串被连坐打死的下游票。

### 本轮目标

把 dependency gate 的语义收成两段：

1. 依赖票彻底不可恢复  
   下游才允许进入 `DEPENDENCY_GATE_UNHEALTHY`

2. 依赖票已有明确恢复路径  
   下游保持阻塞，不要终态失败

这里的“已有明确恢复路径”，至少包括：

- 关联 incident 仍是 `OPEN`
- 或已经 `RECOVERING`
- 且 follow-up action 已明确指向 restore / retry

### 本轮建议先看的代码入口

- `backend/app/core/ticket_handlers.py`
- 必要时看：
  - `backend/app/core/workflow_controller.py`
  - `backend/app/core/ticket_graph.py`

### 这一轮做完后要勾掉的清单

- [ ] 依赖票失败但处于恢复链时，下游 ticket 保持阻塞，不进 `DEPENDENCY_GATE_UNHEALTHY`
- [ ] scheduler 不再把这类下游票直接打成 `FAILED`
- [ ] 这类下游票不会额外触发新的 CEO shadow 噪音 incident
- [ ] 依赖票恢复后，下游还能继续被正常调度
- [ ] 已因 `DEPENDENCY_GATE_UNHEALTHY` 终态失败的历史票，后续恢复策略有明确口径

### 本轮验收口径

至少补一条回归：

- “上游失败 + incident 已进入 `OPEN/RECOVERING` + 下游依赖该票” 时，下游保持 `PENDING/BLOCKED`，而不是 `FAILED`

---

## 会话 4：给 backlog follow-up fallback 补恢复出口

### 这一轮只解决什么

只解决这一句：

- `_build_backlog_followup_batch()` 遇到“已有 `existing_ticket_id` + 依赖链已坏”时，不能再只抛 `no_actions_built`

### 开工前必须知道的背景

006 的另一条高频高层故障是：

- `CEOProposalContractError`
- 根因是 `deterministic_fallback.backlog_followup[no_actions_built]`

说白了：

- controller 已经给了 follow-up plan
- 但这些 plan 对应的票其实已经存在
- fallback 又不会恢复旧票
- 也不会明确抛出“该怎么恢复”
- 最后只会报“一个 action 都没构出来”

### 本轮目标

把 existing ticket 的处理分成两档：

1. 旧票还能直接 retry  
   生成合法 `RETRY_TICKET`

2. 旧票不能直接 retry，只能走 incident restore  
   抛结构化恢复信息，不再抛裸 `no_actions_built`

结构化恢复信息至少要能看见：

- `source_ticket_id`
- `node_id`
- `failure_kind`
- `recommended_followup_action`

### 本轮建议先看的代码入口

- `backend/app/core/ceo_proposer.py`
- 对照看：
  - `backend/app/core/workflow_controller.py`
  - `backend/tests/test_ceo_scheduler.py`

### 这一轮做完后要勾掉的清单

- [ ] follow-up plan 全部已有 `existing_ticket_id` 时，不再直接掉 `no_actions_built`
- [ ] 可直接恢复的 existing ticket 能生成合法 `RETRY_TICKET`
- [ ] 不能直接恢复时，会抛结构化 restore-needed 错误
- [ ] 这类错误里能直接看见源票、节点、失败类型、推荐恢复动作
- [ ] fallback 不再伪造新的 `CREATE_TICKET` 去污染现场

### 本轮验收口径

至少补两条回归：

- existing root ticket 可 retry -> 生成 `RETRY_TICKET`
- existing root ticket 不可直接 retry -> 抛结构化 restore-needed 错误，不是 `no_actions_built`

---

## 会话 5：收 006 专项回归，再做一次最小回放

### 这一轮只解决什么

这一轮不再改设计。
只做两件事：

1. 把 006 的 4 类问题固化成专项回归
2. 做一次 006 现场的最小回放验证

### 开工前必须知道的背景

前 4 轮每轮都应该已经各自收口。

如果前 4 轮里还有任一条没有稳定回归，这一轮不要硬上 live。
先回去补齐前面那轮。

### 本轮目标

形成一组以后每次都能直接跑的 006 回归包。

最低覆盖：

- CEO shadow incident 推荐动作切换
- exhausted budget 下的 incident-driven restore
- dependency gate 不再链式终态
- backlog existing ticket 的 retry / restore 出口

然后再做一次最小回放，确认主线不再停在：

- `check` 阶段
- rerun proposer loop
- `no_actions_built`
- 批量 `DEPENDENCY_GATE_UNHEALTHY`

### 本轮建议先看的代码入口

- `backend/tests/test_api.py`
- `backend/tests/test_ceo_scheduler.py`
- `backend/tests/test_live_library_management_runner.py`

### 这一轮做完后要勾掉的清单

- [ ] 006 四类问题都有专项回归
- [ ] 回归命名能一眼看出对应 006 哪条问题
- [ ] 最小回放能验证根票恢复后主线继续推进
- [ ] 不再先掉进 rerun proposer loop
- [ ] 不再出现“根票一挂，下游整串直接 unhealthy”

### 本轮验收口径

最少要给出两层证据：

1. 定向自动化回归通过
2. 一次最小回放的现场摘要

---

## 追加需求补记（2026-04-21）

这两条是 006 路线的新前置要求。

它们不是“顺手优化”。
要视为会直接影响后面会话 1 到 5 的主线约束。

### 追加要求 A：不要再让自动主线反复卡在招聘审批

你追加的目标是：

- 自动主线里，不再走 `CEO -> HIRE_EMPLOYEE -> CORE_HIRE_APPROVAL -> 批准后入岗`
- 改成 `CEO` 直接按要求拼装员工定义，并注册进 roster

我读代码后，当前真实路径是：

- `backend/app/core/ceo_executor.py`
  - `HIRE_EMPLOYEE` 会转到 `handle_employee_hire_request(...)`
- `backend/app/core/employee_handlers.py`
  - `handle_employee_hire_request(...)` 当前不会直接注册员工
  - 它会创建一条 `CORE_HIRE_APPROVAL`
- `doc/mainline-truth.md`
  - 现在主线也明确写着：缺 architect 时，controller 会先建议 `HIRE_EMPLOYEE`
- `doc/TODO.md`
  - 当前 CEO 真实执行集里也还保留 `HIRE_EMPLOYEE`

也就是说：

- 现在自动主线并没有“直接注册员工”
- 它的真实语义还是“发起招聘审批”
- 这正是 006 反复卡在 staffing gate 的一个核心原因

### 追加要求 B：把隐式 fallback 改成显式 failed，再由 CEO 决定幂等重试

你追加的目标是：

- ticket 多次失败后，不要再靠隐式 fallback 继续往下混
- 要显式暴露成 `FAILED`
- 然后由 scheduler 调起 CEO 来决定下一步怎么幂等恢复

我读代码和文档后，当前至少有这层相关语义：

- `backend/app/core/ceo_proposer.py`
  - 还保留 `build_deterministic_fallback_batch(...)`
  - `propose_ceo_action_batch(...)` 在选不到 live path 时，会回到 deterministic fallback
- `backend/app/core/ceo_scheduler.py`
  - 还会记录 `deterministic_fallback_used / deterministic_fallback_reason`
- `doc/history/memory-log.md`
  - 现有口径还是 `CEO_SHADOW_PIPELINE_FAILED -> RERUN_CEO_SHADOW`
- `doc/TODO.md`
  - 也明确写过当前 incident detail / resolve 还在沿用 rerun 这条恢复链

所以你这条新增要求，本质不是“小修 fallback”。
而是在补一套更明确的失败决策面：

1. 失败先显式暴露
2. scheduler 再拉 CEO
3. CEO 再决定：
   - 重调上游
   - 带失败原因追加信息后重试
   - 直接把当前图退出主线，重新设计 / 重规划

这条要求和原来文档里的：

- 会话 1：恢复语义
- 会话 2：retry budget
- 会话 3：dependency gate
- 会话 4：fallback 恢复出口

确实都有关系。

---

## 前置会话 A：把自动招聘改成 CEO 直接注册员工

### 这一轮只解决什么

只解决这一句：

- 自动主线里的 `HIRE_EMPLOYEE` 不再走 `CORE_HIRE_APPROVAL`，而是直接注册员工

这轮不要顺手把 replace / freeze / restore 一起改掉。
也不要删掉手工治理能力。

### 开工前必须知道的背景

当前自动招聘卡点来自这条链：

- `ceo_executor`
- `handle_employee_hire_request`
- `CORE_HIRE_APPROVAL`
- approval resolve 后才真正入岗

如果这条链不改，后面会话 1 到 5 里很多“恢复”都会继续被 staffing gate 打断。

### 本轮默认范围

只改**自动主线**。

建议默认口径：

- CEO 自动动作里的 `HIRE_EMPLOYEE`
  - 改成直接注册员工
- 手工入口 `employee-hire-request`
  - 先保留
- `CORE_HIRE_APPROVAL`
  - 先只从自动主线摘掉
  - 不在这一轮删除整套能力

### 本轮建议先看的代码入口

- `backend/app/core/ceo_executor.py`
- `backend/app/core/employee_handlers.py`
- `backend/app/core/workflow_controller.py`
- `doc/mainline-truth.md`
- `doc/TODO.md`

### 这一轮设计约束

自动注册不是“随便造个人”。
至少要保留这几类约束：

- role type / role profile 必须合法
- persona profile 仍要规范化
- 与现有 active 员工的高重合画像保护，不能悄悄丢
- idempotency 不能丢
- roster projection / worker lane /后续 dispatch 真相要保持一致

### 这一轮做完后要勾掉的清单

- [x] 自动主线里的 `HIRE_EMPLOYEE` 不再创建 `CORE_HIRE_APPROVAL`
- [x] CEO 能直接生成完整员工定义并注册入 roster
- [x] 现有 persona normalization 和高重合保护仍然保留
- [x] 自动招聘完成后，controller 能把这名员工立即视为可用员工
- [x] 手工 `employee-hire-request` 能力先不删
- [x] 文档里明确写清“自动招聘”和“手工审批招聘”的边界

实际落地：

- `ceo_executor` 的自动 `HIRE_EMPLOYEE` 已改成直写 `EMPLOYEE_HIRED`，`causation_hint` 固定落到 `employee:<employee_id>`
- 手工 `employee-hire-request` 仍继续创建 `CORE_HIRE_APPROVAL`
- `CORE_HIRE_APPROVAL -> EMPLOYEE_HIRED` 和自动直聘现在复用同一套 employee event payload 构造

### 本轮验收口径

至少补两条回归：

- `HIRE_EMPLOYEE` 自动路径执行后，直接出现 active employee，不出现 open approval
- architect / backend 这类 staffing gap 被填上后，主线能继续往后 materialize

---

## 前置会话 B：把隐式 fallback 收成显式 failed + CEO 决策面

### 这一轮只解决什么

只解决这一句：

- ticket / CEO 主线相关的隐式 fallback，不再偷偷兜底推进，而是显式失败后交给 CEO 决策

这轮不要扩大到：

- artifact inline fallback
- context compiler 的 reference-only fallback
- process asset 的 descriptor-only fallback

这些属于另一类“读面降级”，不是 006 现在要收的主线失败语义。

### 开工前必须知道的背景

当前至少有两层相关语义需要收紧：

1. `ceo_proposer` 的 deterministic fallback  
   现在在 provider 不可用、不是 live path、或 controller 推荐动作需要 deterministic route 时，会回落成 fallback batch。

2. `ceo_scheduler` 的 fallback 审计语义  
   现在还会记录 `deterministic_fallback_used / deterministic_fallback_reason`。

你的新增要求本质上是：

- 不要再把“失败后临时 fallback 继续跑”当主线
- 要让失败真失败
- 再由 scheduler 调起 CEO 去做下一步决策

### 这一轮建议的决策分层

建议把 CEO 决策收成三档：

1. **同源可恢复重试**
   - 上游 ticket 仍可恢复
   - CEO 选择 `RETRY_TICKET`
   - 或 `RESTORE_AND_RETRY_*`

2. **带失败原因的增强重试**
   - 同一 source ticket 已失败多次
   - 但根因明确、还有继续尝试价值
   - CEO 不直接 silent fallback
   - 而是在 snapshot / prompt 里显式带上前几轮失败原因，再做一次有上下文的重试决策

3. **退出当前图，重新设计**
   - 同类 failure fingerprint 重复出现
   - 或 dependency chain 已坏
   - 或当前 capability plan 已不可信
   - CEO 不再继续硬重试
   - 而是进入 replan / graph redesign

默认建议：

- 第一档优先
- 第二档只在 failure context 足够明确时启用
- 第三档作为重复失败后的升级出口

### 本轮建议先看的代码入口

- `backend/app/core/ceo_proposer.py`
- `backend/app/core/ceo_scheduler.py`
- `backend/app/core/ticket_handlers.py`
- `backend/app/core/workflow_auto_advance.py`
- `doc/history/memory-log.md`
- `doc/TODO.md`

### 这一轮做完后要勾掉的清单

- [ ] 006 主线相关的隐式 deterministic fallback 不再偷偷推进业务主线
- [ ] 失败会显式落成 `FAILED` 或明确 incident
- [ ] scheduler 会在合适时机重新调起 CEO，而不是直接 silent fallback
- [ ] CEO snapshot / prompt 能看到最近几轮失败原因摘要
- [ ] CEO 至少能在三类动作间做明确选择：
  - 原地恢复重试
  - 带失败原因增强重试
  - 退出当前图并重规划
- [ ] 文档里明确哪些 fallback 还保留为“读面降级”，哪些已经不允许再推进主线

### 本轮验收口径

至少补三类回归：

- 同类失败第一次出现：显式 failed / incident，不 silent fallback
- 同类失败重复出现但仍可恢复：CEO 能拿到历史失败原因并做增强重试
- 同类失败达到升级阈值：CEO 不再继续硬 retry，而是触发 replan / redesign 路线

---

## 顺序调整

因为这两条是新增前置要求，推荐顺序改成：

1. 前置会话 A：CEO 直接注册员工
2. 前置会话 B：隐式 fallback -> 显式 failed + CEO 决策面
3. 原会话 1：修 CEO shadow 恢复语义
4. 原会话 2：修 retry budget
5. 原会话 3：修 dependency gate
6. 原会话 4：补 backlog fallback 恢复出口
7. 原会话 5：收 006 专项回归和最小回放

这样排的原因很直接：

- 不先摘掉自动招聘审批，后面恢复链还是会被 staffing gate 卡住
- 不先收紧隐式 fallback，后面很多失败语义会继续混在一起，判断不干净

---

## 每轮收口时都要更新什么

每做完一轮，建议同步更新两处：

### 1. 这份路线文档

把对应会话下面的清单打勾。
必要时补一句：

- 实际改了什么
- 哪条验收还没过

### 2. 006 测试记录

如果那一轮真的改变了 006 的判断口径，再回写：

- `doc/tests/intergration-test-006-20260420.md`

只补这三类信息：

- 问题是否已解决
- 哪条验证已补齐
- 还剩什么尾巴

不要重新写成长过程流水账。

---

## 最后给一句执行建议

后续每个新会话，开场只要先说清三件事：

1. 现在做第几轮
2. 本轮只解决哪一类问题
3. 本轮明确不碰什么

这样最稳。

006 现在最忌讳的，不是修得慢。
是一次会话里同时改恢复语义、budget、dependency gate、fallback，最后又回到“问题到底是谁引起的”这种混战状态。
