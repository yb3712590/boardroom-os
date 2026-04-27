# intergration-test-013 整改方案

> **For agentic workers:** 后续独立会话实施本方案时，建议使用 `executing-plans` 或按本文件每轮独立执行。步骤使用 checkbox (`- [ ]`) 追踪。每轮只收一个问题族，完成前必须运行本轮列出的定向验证，并在最终回复里如实报告无法执行的验证。

**目标：** 把 013 从“workflow 进入 `COMPLETED / closeout`，但控制面把合同错配、重复招聘、检查失败都包装成可继续推进”整改为“角色合同、员工复用、招聘幂等、checker gate、closeout gate 都按通用 agent team 状态机 contract 明确收口”。

**架构：** 先收 `target_role -> role_profile_ref -> output_schema_ref -> execution_contract` 的单一真相源，再把 staffing gap 从合同错误里拆出来；随后让 CEO 招聘具备复用护栏和重复拒绝熔断，最后收紧 `FAIL_CLOSED` 到 closeout 的硬 gate。不要把 live harness replay 成功当作 runtime contract 已满足，也不要用某次图书馆产物装配来掩盖状态机问题。

**Tech Stack:** Python, pytest, SQLite-backed control-plane repository, CEO shadow, workflow controller, execution target matrix, staffing catalog, live harness, workflow autopilot.

---

## 0. 真相源与当前结论

本方案只服务 013：

- 测试报告：`doc/tests/intergration-test-013-20260426.md`
- 参照方案：`doc/tests/intergration-test-012-remediation-plan-20260426.md`
- live config：`backend/data/live-tests/library_management_autopilot_live_013.toml`
- workflow：`wf_3514435f5e6d`
- 最终状态：`COMPLETED / closeout`
- 原始 runner：最后失败在 live assertion profile
- 修补后 DB replay：`collect_common_outcome()` + `scenario.assert_outcome()` 通过
- 真实交付质量：`BR-CHECK-001` 输出 `FAIL_CLOSED`

必须先接受这个结论：

- 013 的产物没有真正装配完成。
- 不应该整改某次生成出来的 Vue、SQLite、README、API skeleton。
- 013 的价值是暴露通用 agent team 状态机缺陷。
- CTO 招聘卡点不是“缺 `cto_primary` 员工”，而是执行合同错配被误报成 staffing gap。
- `FAIL_CLOSED` 被 closeout 吞掉，是状态机完成门禁问题，不是测试断言太严格。

本方案重点对照这些主线事实：

- `doc/mainline-truth.md`：`cto_primary` 支持治理文档，不支持 `source_code_delivery`。
- `backend/app/core/execution_targets.py`：执行目标由 `role_profile_ref + output_schema_ref` 推出。
- `backend/app/core/workflow_controller.py`：controller 当前负责 follow-up 计划、staffing gap 与 recommended action。
- `backend/app/core/ceo_validator.py` / `backend/app/core/employee_handlers.py`：重复招聘会被 high-overlap / existing employee 拒绝。
- `backend/app/core/workflow_completion.py`：closeout 必须尊重 checker verdict。

关于 CTO 招聘循环，当前判断如下：

- `BR-GOV-001` 的 `target_role=cto` 映射到 `cto_primary` 是合理的。
- 错在后续默认 `output_schema_ref` 曾落成 `source_code_delivery`。
- `cto_primary + source_code_delivery` 不是合法执行合同。
- controller 因合同不成立，误判为缺 `cto_primary` staffing。
- CEO 继续发 `HIRE_EMPLOYEE`。
- validator 看到已有 active board-approved 同类 CTO，拒绝重复招聘。
- controller 没吸收拒绝事实，下一轮继续同样推荐，形成死循环。

“按需实时组装员工角色”没有挡住这个问题，原因也很明确：

- 它解决的是“如何从模板组装员工画像和 role profile”。
- 它不负责修正错误的 `role_profile_ref + output_schema_ref` 组合。
- 如果执行合同本身不存在，员工再怎么组装也不能承接这张票。
- 重复招聘 validator 是防线，不是调度恢复机制。

---

## 1. 本方案明确纳入审计的 013 修改

### 1.1 建议保留的修改

- [ ] 保留 `backend/app/core/workflow_controller.py` 中 `cto_primary` backlog follow-up 输出 schema 改为 `backlog_recommendation` 的方向。
  - 架构判断：这是合同修复，不是 CTO 个例修补。
  - 后续要求：把它提升为统一 resolver 规则，不能散落在单个 if 分支里。

- [ ] 保留 backlog follow-up 默认派单要求 assignee 具备对应 `role_profile_ref`。
  - 架构判断：这是派单边界修复。
  - 后续要求：所有 ready ticket、governance progression、CEO fallback 都要共享同一套合同判定。

- [ ] 保留 `backend/tests/test_ceo_scheduler.py` 中 `test_ceo_shadow_snapshot_uses_existing_cto_for_backlog_governance_followup`。
  - 架构判断：这个测试覆盖了“员工 ID 不重要，role profile 和合同才重要”。
  - 后续要求：补充 contract mismatch、duplicate hire loop、validator reuse details 的回归。

### 1.2 建议保留但必须继续整改的修改

- [ ] `target_role=cto` 映射到 `cto_primary`。
  - 风险：映射本身正确，但下游默认 schema 一旦落成 `source_code_delivery`，仍会制造假 staffing gap。
  - 整改方向：`target_role` 解析必须一次性给出合法 `role_profile_ref + output_schema_ref + execution_contract`。

- [ ] CEO 自动招聘直接注册 active employee。
  - 风险：自动招聘能解真缺人，但不能用来修合同错配。
  - 整改方向：`HIRE_EMPLOYEE` 只能在“无 active board-approved 可复用员工”时出现。

- [ ] live assertion profile 支持 PRD 级非源码 follow-up。
  - 风险：profile 修正只能让断言理解治理、QA、doc、check 票，不能把失败产物变成功。
  - 整改方向：runtime closeout gate 必须读取 checker verdict。

### 1.3 未修复，仅被恢复机制覆盖的问题

- [ ] 合同错配仍可能被包装成 `STAFFING_REQUIRED`。
- [ ] validator 拒绝重复招聘后，状态机没有结构化吸收这个事实。
- [ ] CEO 可能继续按旧 snapshot 重复发出同类 hire。
- [ ] checker `FAIL_CLOSED` 仍可能被 closeout 包装成 `COMPLETED / closeout`。
- [ ] DB replay 通过不能改写原始 runner 失败事实。

### 1.4 临时动作，不纳入产品架构

- [ ] 临时装配 013 图书馆前端入口。
- [ ] 临时导入 013 SQLite schema / seed。
- [ ] 临时补 013 API 路由。
- [ ] 临时改 013 README。
- [ ] 用临时 preview server 证明产物可看。

---

## 2. 六轮执行顺序

### Round 1：收口 backlog follow-up 执行合同

**目标：** 所有 backlog follow-up 先生成合法执行合同，再进入派单、招聘和建票。

**优先级：** P0。CTO duplicate hire loop 的根因在本轮收口。

**主要文件：**

- Modify: `backend/app/core/workflow_controller.py`
- Modify: `backend/app/core/execution_targets.py`
- Test: `backend/tests/test_ceo_scheduler.py`

**需要理解的现有代码：**

- `backend/app/core/workflow_controller.py`
  - `_ROLE_PROFILE_BY_TARGET_ROLE`
  - `_resolve_target_role_profile()`
  - `_resolve_followup_output_schema_ref()`
  - `_select_default_assignee()`
  - `_build_followup_ticket_plans()`
- `backend/app/core/execution_targets.py`
  - `infer_execution_contract_payload()`
  - `get_execution_target_definition()`
  - `employee_supports_execution_contract()`

**实施清单：**

- [ ] 新增统一 resolver：`_resolve_backlog_followup_execution_plan(raw_ticket)`。
  - 输入：backlog handoff ticket。
  - 输出：`role_profile_ref / output_schema_ref / execution_contract / deliverable_kind`。
  - 不返回合法 `execution_contract` 时，返回结构化错误，不继续建 follow-up plan。

- [ ] 将 `target_role=cto / governance_cto / cto_primary` 统一解析为：
  - `role_profile_ref = "cto_primary"`
  - `output_schema_ref = "backlog_recommendation"`
  - `execution_target_ref = "execution_target:cto_governance_document"`

- [ ] 将实现型角色继续解析为：
  - `frontend_engineer_primary -> source_code_delivery`
  - `backend_engineer_primary -> source_code_delivery`
  - `database_engineer_primary -> source_code_delivery`
  - `platform_sre_primary -> source_code_delivery`

- [ ] `checker_primary` 只允许生成检查类 schema，不默认走 `source_code_delivery`。

- [ ] `_build_followup_ticket_plans()` 只消费 resolver 输出，不再自己拼 role 和 schema。

- [ ] resolver 对无效组合写明 `reason_code`：
  - `unsupported_target_role`
  - `unsupported_role_schema_combo`
  - `execution_contract_missing`

**建议测试命令：**

```powershell
cd D:\projects\boardroom-os\backend
py -3 -m pytest tests/test_ceo_scheduler.py::test_ceo_shadow_snapshot_uses_existing_cto_for_backlog_governance_followup -q
py -3 -m pytest tests/test_ceo_scheduler.py -k "backlog and cto" -q
```

**验收标准：**

- `target_role=cto` 不再可能生成 `source_code_delivery`。
- 合同缺失时不会进入 staffing gap。
- 已有任意 employee id 的 `cto_primary` 员工都可被复用。
- 不硬编码 `emp_cto_governance`。

**不要在本轮做：**

- 不改招聘系统。
- 不改 closeout。
- 不修 013 图书馆产物。

---

### Round 2：拆开 staffing gap 与 contract mismatch

**目标：** controller 能分清“真缺员工”“员工暂不可用”“执行合同错误”。

**优先级：** P0。没有这个拆分，CEO 仍会把合同错误当招聘需求。

**主要文件：**

- Modify: `backend/app/core/workflow_controller.py`
- Test: `backend/tests/test_ceo_scheduler.py`

**需要理解的现有代码：**

- `_build_ready_ticket_staffing_gaps()`
- `build_workflow_controller_view()`
- `capability_plan["ready_ticket_staffing_gaps"]`
- `capability_plan["recommended_hire"]`

**实施清单：**

- [ ] 在 `_build_ready_ticket_staffing_gaps()` 里先校验 created spec 的执行合同。
  - `execution_contract is None` 时，不统计为 staffing gap。
  - 输出结构化 `contract_issues[]`。

- [ ] 给 ready ticket 问题分类：
  - `INVALID_EXECUTION_CONTRACT`
  - `ROLE_SCHEMA_UNSUPPORTED`
  - `NO_ACTIVE_ROLE_WORKER`
  - `WORKER_BUSY`
  - `WORKER_EXCLUDED`
  - `PROVIDER_PAUSED`

- [ ] 只有 `NO_ACTIVE_ROLE_WORKER` 允许进入 `STAFFING_REQUIRED -> HIRE_EMPLOYEE`。

- [ ] `WORKER_BUSY / PROVIDER_PAUSED` 应进入 wait / pause，不触发招聘。

- [ ] `INVALID_EXECUTION_CONTRACT / ROLE_SCHEMA_UNSUPPORTED` 应进入 `CONTRACT_REPLAN_REQUIRED` 或等价状态。
  - `recommended_action` 不得是 `HIRE_EMPLOYEE`。

- [ ] `capability_plan` 增加：
  - `contract_issues`
  - `reuse_candidate_employee_ids`
  - `staffing_wait_reasons`

**建议测试命令：**

```powershell
cd D:\projects\boardroom-os\backend
py -3 -m pytest tests/test_ceo_scheduler.py -k "ready_ticket_staffing or contract" -q
```

**验收标准：**

- `cto_primary + source_code_delivery` 不建议招聘。
- `backend_engineer_primary + source_code_delivery` 且无 backend 员工时，仍建议招聘。
- 同角色员工 busy 时，不创建重复招聘。
- snapshot 能看出是合同错，还是人手缺。

**不要在本轮做：**

- 不调整 persona overlap 阈值。
- 不把所有无法 lease 的票都归为缺人。
- 不让 `NO_ACTION` 掩盖 contract issue。

---

### Round 3：CEO 招聘增加复用护栏

**目标：** CEO 在发出 `HIRE_EMPLOYEE` 前，先确认当前 roster 没有可复用员工。

**优先级：** P1。

**主要文件：**

- Modify: `backend/app/core/ceo_proposer.py`
- Modify: `backend/app/core/ceo_validator.py`
- Modify: `backend/app/core/employee_handlers.py`
- Test: `backend/tests/test_ceo_scheduler.py`
- Test: `backend/tests/test_api.py`

**需要理解的现有代码：**

- `backend/app/core/ceo_proposer.py`
  - `_build_capability_hire_batch()`
  - `build_deterministic_fallback_batch()`
- `backend/app/core/ceo_validator.py`
  - `validate_ceo_action_batch()`
- `backend/app/core/employee_handlers.py`
  - `_resolve_employee_hire_request()`
  - `handle_ceo_direct_employee_hire()`
- `backend/app/core/persona_profiles.py`
  - `find_same_role_high_overlap_conflict()`

**实施清单：**

- [ ] 在 `_build_capability_hire_batch()` 前检查 active board-approved roster。
  - role profile 已覆盖时，不生成 hire batch。
  - 返回结构化 proposal error，要求 controller 重新评估或复用员工。

- [ ] `ceo_validator` 拒绝高重叠招聘时，reason details 增加：
  - `reason_code = "ROLE_ALREADY_COVERED"`
  - `reuse_candidate_employee_id`
  - `role_type`
  - `role_profile_refs`

- [ ] `employee_handlers` 对 direct hire 的 high-overlap rejection 也返回同类结构化信息。

- [ ] controller 读取上一轮 rejected action 后，不再重复输出同一 `recommended_hire`。

- [ ] 保留 high-overlap 校验。
  - 它是防重复员工的正确 guard。
  - 问题是上层没有消费拒绝结果。

**建议测试命令：**

```powershell
cd D:\projects\boardroom-os\backend
py -3 -m pytest tests/test_ceo_scheduler.py -k "hire and overlap" -q
py -3 -m pytest tests/test_api.py -k "employee_hire and overlap" -q
```

**验收标准：**

- 已有 `cto_primary` active worker 时，CEO 不发第二次 CTO hire。
- employee id 和 template hint 不一致时仍可复用。
- validator 拒绝重复招聘后，下一轮不再同样重试。
- 真缺员工路径仍能招聘 backend / database / platform / checker 等角色。

**不要在本轮做：**

- 不删除 duplicate / high-overlap 校验。
- 不把 duplicate rejection 当成功。
- 不用随机变体绕过重复员工校验。

---

### Round 4：审计按需组装员工角色的适用边界

**目标：** 明确“按需实时组装员工角色”只负责员工模板和画像，不负责修正错误执行合同。

**优先级：** P1。

**主要文件：**

- Modify: `backend/app/core/staffing_catalog.py`
- Modify: `backend/app/core/governance_templates.py`
- Modify: `backend/app/core/projections.py`
- Modify: `backend/app/core/workflow_progression.py`
- Test: `backend/tests/test_governance_templates.py`
- Test: `backend/tests/test_api.py`

**需要理解的现有代码：**

- `backend/app/core/staffing_catalog.py`
  - `_BOARD_WORKFORCE_STAFFING_HIRE_TEMPLATES`
  - `resolve_limited_ceo_staffing_combo()`
- `backend/app/core/governance_templates.py`
  - `role_template_source_for_worker()`
  - `list_role_template_catalog_entries()`
- `backend/app/core/projections.py`
  - workforce projection 的 `source_template_id / source_fragment_refs`
- `backend/app/core/workflow_progression.py`
  - `select_governance_role_and_assignee()`

**实施清单：**

- [ ] 建立一张可测试矩阵：
  - `role_type`
  - `role_profile_ref`
  - `hire_template`
  - `role_template`
  - `supported_output_schema_refs`
  - `supported_execution_target_refs`

- [ ] `staffing_catalog` 只负责“能不能招聘这个角色”。
  - 不负责决定某张票应该输出什么 schema。

- [ ] `execution_targets` 负责“这个角色能不能执行这个 schema”。

- [ ] `workflow_controller` 负责“当前工作需要哪个合法执行合同”。

- [ ] workforce projection 继续展示模板来源。
  - 但 `source_template_id / source_fragment_refs` 只作为解释信息，不作为派单依据。

- [ ] governance progression、backlog follow-up、ready ticket staffing gap 使用同一 contract resolver。

**建议测试命令：**

```powershell
cd D:\projects\boardroom-os\backend
py -3 -m pytest tests/test_governance_templates.py -q
py -3 -m pytest tests/test_api.py -k "workforce or governance_cto" -q
```

**验收标准：**

- `cto_governance` 模板能组装 `cto_primary` 员工。
- `cto_primary` 可承接 `architecture_brief / technology_decision / milestone_plan / backlog_recommendation`。
- `cto_primary` 不能承接 `source_code_delivery`。
- workforce UI / projection 不再让人误以为模板默认文档就是 runtime contract。

**不要在本轮做：**

- 不把 role template catalog 当成 runtime 派单真相源。
- 不扩大未启用模板。
- 不引入新的自由角色系统。

---

### Round 5：招聘死循环检测与 incident 收口

**目标：** `STAFFING_REQUIRED -> HIRE_EMPLOYEE -> duplicate rejected` 不能无限循环。

**优先级：** P1。

**主要文件：**

- Modify: `backend/app/core/ceo_scheduler.py`
- Modify: `backend/app/core/workflow_auto_advance.py`
- Modify: `backend/app/core/workflow_controller.py`
- Test: `backend/tests/test_scheduler_runner.py`
- Test: `backend/tests/test_ceo_scheduler.py`

**需要理解的现有代码：**

- `backend/app/core/ceo_scheduler.py`
  - accepted / rejected / duplicate action summary
- `backend/app/core/workflow_auto_advance.py`
  - governance / staffing wait 状态推进
- `backend/app/core/workflow_controller.py`
  - `controller_state`
  - `capability_plan`

**实施清单：**

- [ ] 给 CEO shadow run 生成 loop fingerprint：
  - `workflow_id`
  - `controller_state.state`
  - `recommended_action`
  - `role_type`
  - `role_profile_refs`
  - `rejected_reason_code`

- [ ] 连续出现同一 fingerprint 时，打开 incident 或进入 graph health pause。

- [ ] incident payload 必须包含：
  - 原始 controller state
  - recommended hire
  - rejected action
  - validator reason
  - reuse candidate
  - suggested recovery action

- [ ] incident 未关闭前，不再重复发送同一 hire action。

- [ ] CEO snapshot 暴露 loop summary，便于人工或后续 recovery agent 处理。

**建议测试命令：**

```powershell
cd D:\projects\boardroom-os\backend
py -3 -m pytest tests/test_scheduler_runner.py -k "hire or duplicate or staffing" -q
py -3 -m pytest tests/test_ceo_scheduler.py -k "duplicate and hire" -q
```

**验收标准：**

- 同一 CTO duplicate hire 自动重试最多一次。
- 第二次同类拒绝后进入 incident / pause。
- controller 后续不继续建议相同 hire。
- incident 能指出已有哪个员工可复用，或指出合同错配。

**不要在本轮做：**

- 不靠 sleep / tick 上限掩盖循环。
- 不吞掉 validator rejection。
- 不把 incident 当 workflow completed。

---

### Round 6：收紧 checker closeout gate

**目标：** checker `FAIL_CLOSED` 不能被 closeout 包装成 workflow `COMPLETED / closeout`。

**优先级：** P0。013 最终“完成但不可交付”的核心问题在本轮收口。

**主要文件：**

- Modify: `backend/app/core/workflow_completion.py`
- Modify: `backend/app/core/ceo_proposer.py`
- Modify: `backend/app/core/workflow_autopilot.py`
- Test: `backend/tests/test_workflow_autopilot.py`
- Test: `backend/tests/test_live_library_management_runner.py`

**需要理解的现有代码：**

- `backend/app/core/workflow_completion.py`
  - `resolve_workflow_closeout_completion()`
- `backend/app/core/ceo_proposer.py`
  - `_build_autopilot_closeout_batch()`
- `backend/app/core/workflow_autopilot.py`
  - closeout summary / chain report 相关逻辑
- live profile：
  - `backend/tests/live/_scenario_profiles.py`

**实施清单：**

- [ ] closeout completion 前读取 checker ticket 的 terminal payload。

- [ ] 识别并阻断：
  - `FAIL_CLOSED`
  - 缺 source delivery evidence
  - 缺 QA evidence
  - 缺正式启动证据
  - 缺文档 evidence
  - checker report 指向 unresolved defects

- [ ] closeout fallback 只在存在有效 delivery mainline evidence 时触发。

- [ ] `FAIL_CLOSED` 时 controller 应进入 rework / incident / recovery 状态。

- [ ] live assertion profile 只做断言，不补 runtime 状态。

- [ ] DB replay 结果必须保留“原始 runner 失败”的事实。

**建议测试命令：**

```powershell
cd D:\projects\boardroom-os\backend
py -3 -m pytest tests/test_workflow_autopilot.py -k "closeout or checker" -q
py -3 -m pytest tests/test_live_library_management_runner.py -q
```

**验收标准：**

- checker `FAIL_CLOSED` 时 workflow 不进入 `COMPLETED / closeout`。
- checker `PASS` 且证据完整时才允许 closeout。
- closeout package 的 final evidence 不包含错误类型 artifact。
- 013 风格场景不会再把半成品标成完成。

**不要在本轮做：**

- 不降低 checker 严格度。
- 不让 closeout 忽略 checker verdict。
- 不把 replay 成功写成自然执行成功。

---

## 3. 总体验证

全部整改完成后运行：

```powershell
cd D:\projects\boardroom-os\backend
py -3 -m pytest tests/test_ceo_scheduler.py -k "cto or staffing or hire or backlog" -q
py -3 -m pytest tests/test_api.py -k "employee_hire or workforce or governance_cto" -q
py -3 -m pytest tests/test_governance_templates.py -q
py -3 -m pytest tests/test_workflow_autopilot.py -k "closeout or checker" -q
py -3 -m pytest tests/test_scheduler_runner.py -k "hire or duplicate or staffing" -q
py -3 -m pytest tests/test_live_library_management_runner.py -q
```

最终验收：

- `target_role=cto` 生成治理合同，不生成源码交付合同。
- 已有 `cto_primary` 员工时，CEO 复用员工，不重复招聘。
- 合同错配不会进入 `STAFFING_REQUIRED`。
- duplicate hire rejection 会进入结构化恢复，不会循环。
- `FAIL_CLOSED` 不会进入 workflow completed。
- live harness 不负责修补 runtime contract。
- 方案不依赖 013 产物目录。

---

## 4. 明确不要做

- 不修 013 那次生成出来的图书馆管理系统。
- 不补接那次产物的 Vue 入口、API 路由、SQLite seed、README。
- 不通过新增更多 CTO 员工解决卡点。
- 不硬编码 `emp_cto_governance`。
- 不删除 high-overlap / duplicate hire validator。
- 不让 governance role 默认输出 `source_code_delivery`。
- 不用 live replay 掩盖原始 runner 失败。
- 不把单次场景 workaround 写进通用状态机。
