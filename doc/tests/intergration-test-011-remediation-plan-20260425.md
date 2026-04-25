# intergration-test-011 整改方案

> **For agentic workers:** 后续独立会话实施本方案时，建议使用 `executing-plans` 或按本文件每轮独立执行。每轮只收一个问题族，完成前必须运行本轮列出的定向验证，并在最终回复里如实报告无法执行的验证。

**目标：** 把 011 的 `success=true` 从“harness/workflow 假绿”整改为“控制面不能早收尾、live harness 能拦截不完整交付、产品行为能真实查询和修改图书状态”。

**架构：** 先修控制面 closeout/fanout 的判定，再修 graph health 与 controller 的等待语义，然后收紧 live harness 的成功门槛，补齐 011 产物本身缺失的 BR004-BR007 行为，最后修复 ready ticket 无可用员工时不能触发 CEO 按需雇佣的问题。不要先改产品代码来掩盖控制面早收尾；否则下一次 live run 仍可能把不完整工作流标为完成。

**Tech Stack:** Python, FastAPI/TestClient, SQLite, pytest, boardroom-os control-plane repository/event projection, live harness.

---

## 0. 真相源与当前结论

本方案只服务 011：

- 测试报告：`doc/tests/intergration-test-011-20260425.md`
- live config：`backend/data/live-tests/library_management_autopilot_live_011.toml`
- scenario root：`backend/data/scenarios/library_management_autopilot_live_011`
- final report：`backend/data/scenarios/library_management_autopilot_live_011/run_report.json`
- workflow：`wf_01c3733dd2a0`
- closeout ticket：`tkt_19950c0e6ba0`

必须先接受这个结论：

- 011 的 `success=true` 是 harness/workflow 层成功，不是产品完成。
- 实际交付只完成 BR001-BR003。
- BR004-BR007 未 materialize。
- `node_ceo_delivery_closeout` 被创建在 BR004 之前。
- 产物只是 parser + SQLite repository 切片，不是完整 terminal 图书管理应用。

报告中的关键证据：

- `doc/tests/intergration-test-011-20260425.md` 中 `Final State` 记录 `success=true`。
- 同文件 `Confirmed Defects` 明确 P1：fallback 在 backlog fanout 前 closeout。
- 同文件 `Backlog Fanout Reality` 明确 BR004-BR007 没有 ticket。
- 同文件 `Root Cause Summary` 明确最终完成没有功能性 end-to-end application。

## 1. 本方案明确纳入审计的 011 最小修改

011 期间的最小修改已经有一部分落入主线提交 `7cd932f Strengthen CEO fallback and runtime artifact normalization`。后续不能只看报告缺陷，还要审计这些修改是否和主线意图一致。

### 1.1 应保留，但要补回归的修改

1. `backend/app/core/runtime.py`
   - 目的：source/test output artifacts 使用唯一 `art://workspace/<ticket>/...` refs，避免 rework 写同一 logical path 时 artifact index 冲突。
   - 当前关键函数：`_source_code_delivery_artifact_ref()`
   - 整改要求：保留方向，补“同一 ticket 多次 rework、同一 logical path 不撞 artifact_ref”的回归。

2. `backend/tests/live/_config.py` 与 `backend/tests/live/_scenario_profiles.py`
   - 目的：live role bindings 支持按 role profile 派生 expected model/reasoning。
   - 整改要求：保留方向，避免把多模型路由退回一个全局 preferred model。

3. `backend/tests/live/_autopilot_live_harness.py`
   - 目的：非 clean resume 使用 per-run idempotency token，避免 resume key 复用。
   - 整改要求：保留方向，但不能把已 `COMPLETED` workflow 当成新一轮成功证明。

### 1.2 必须整改覆盖的修改

1. `backend/app/core/ceo_scheduler.py`
   - 当前行为：live CEO 的 `NO_ACTION` 被 validator 拒绝后，如果 controller 要求 `CREATE_TICKET/HIRE_EMPLOYEE/REQUEST_MEETING`，scheduler 直接用 deterministic fallback 执行。
   - 风险：当 graph health `CRITICAL` 时，CEO 的等待可能是正确行为；fallback 可能绕过健康门槛。
   - 整改方向：只有 controller 和 graph health 都允许 mutating action 时，才允许 validation fallback。

2. `backend/app/core/ceo_proposer.py`
   - 当前行为：`build_deterministic_fallback_batch()` 在处理 `recommended_action == CREATE_TICKET` 之前先调用 `_build_autopilot_closeout_batch()`。
   - 风险：BR004-BR007 未 materialize 时先 closeout。
   - 整改方向：`CREATE_TICKET` backlog fanout 优先于 closeout，且 closeout 本身要显式检查没有未 materialize 的 followup plans。

3. `backend/tests/live/_autopilot_live_harness.py`
   - 当前行为：source delivery payload audit 跳过 failed retry history；full success 可以接受 compact payload；non-clean resume 能 attach 到 latest `COMPLETED` workflow。
   - 风险：历史失败、证据缺口、已完成 workflow 被新 run 继承，都会让 `success=true` 变弱。
   - 整改方向：failed retry 可不阻断“最终成功”，但必须进入 audit summary；full success 必须要求完整 fanout/checker/e2e 证据；non-clean attach 到 completed 只能用于读取报告，不能作为新运行成功。

4. 011 中手工插入员工
   - 报告记录插入 `emp_backend_integration_011`、`emp_database_integration_011`、`emp_platform_integration_011`。
   - 风险：这是 scenario 数据修补，不是通用 staffing 机制。
   - 整改方向：本方案不把手工员工插入当主线修复；如果 staffing gap 重现，应通过 controller/hiring/followup routing 回归覆盖。

---

## 2. 五轮执行顺序

### Round 1：阻断早收尾，恢复 backlog fanout 优先级

**目标：** 当 backlog followup plans 仍有未 materialize 项时，任何 deterministic fallback 或 autopilot closeout 都不能创建 closeout；如果 controller `recommended_action == CREATE_TICKET`，必须创建下一个可执行 backlog followup ticket，例如 011 的 BR004。

**优先级：** P1，必须第一轮做。

**主要文件：**

- Modify: `backend/app/core/ceo_proposer.py`
- Modify: `backend/app/core/workflow_completion.py`
- Test: `backend/tests/test_ceo_scheduler.py`

**需要理解的现有代码：**

- `backend/app/core/ceo_proposer.py`
  - `_build_backlog_followup_batch()`
  - `_build_autopilot_closeout_batch()`
  - `build_deterministic_fallback_batch()`
- `backend/app/core/workflow_completion.py`
  - `ticket_has_delivery_mainline_evidence()`
  - `workflow_has_delivery_mainline_evidence()`
- `backend/app/core/workflow_controller.py`
  - `_build_followup_ticket_plans()`
  - controller state `READY_FOR_FANOUT / CREATE_TICKET`

**实施清单：**

- [x] 新增 failing test：`test_deterministic_fallback_prefers_missing_backlog_followup_over_closeout`
  - 位置：`backend/tests/test_ceo_scheduler.py`
  - 场景：seed workflow，完成最小治理链，创建 backlog recommendation，推荐 BR001-BR007；把 BR001-BR003 设为已完成，BR004-BR007 的 `existing_ticket_id` 保持 `None`；snapshot controller state 为 `READY_FOR_FANOUT / CREATE_TICKET`。
  - 断言：`build_deterministic_fallback_batch()` 返回 `CREATE_TICKET`，payload `node_id` 指向 BR004 followup，不是 `node_ceo_delivery_closeout`。

- [x] 新增 failing test：`test_autopilot_closeout_blocked_by_unmaterialized_followup_plans`
  - 位置：`backend/tests/test_ceo_scheduler.py`
  - 场景：snapshot 中 `capability_plan.followup_ticket_plans` 存在至少一个 `existing_ticket_id is None`。
  - 断言：`_build_autopilot_closeout_batch()` 返回 `None`。

- [x] 修改 `build_deterministic_fallback_batch()`
  - 如果 `recommended_action == "CREATE_TICKET"`，先处理：
    - `required_governance_ticket_plan`
    - `followup_ticket_plans`
    - project init kickoff
  - 只有 controller 没有 mutating action 或所有 fanout/required governance 已经完成时，才考虑 closeout。

- [x] 修改 `_build_autopilot_closeout_batch()`
  - 增加 guard：
    - `capability_plan.followup_ticket_plans` 中任何 `existing_ticket_id is None` -> return `None`
    - 如果存在 planned followup tickets，但这些 tickets 未全部 terminal completed/reviewed -> return `None`
  - 不要只依赖 `ticket_summary.active_count == 0` 和 nodes 全 completed。

- [x] 强化 closeout parent 选择
  - `_resolve_autopilot_closeout_parent_ticket_id()` 不能把 BR002/BR003 的 command-contract 或 repository-contract 证据当成整个 workflow 的最终 parent。
  - 若存在 maker/checker handoff ticket，优先使用最终 checker/handoff 对应 maker ticket。

**Round 1 验证记录（2026-04-25）：**

- 已通过：`py -3 -m pytest tests/test_ceo_scheduler.py::test_deterministic_fallback_prefers_missing_backlog_followup_over_closeout -q`
- 已通过：`py -3 -m pytest tests/test_ceo_scheduler.py::test_autopilot_closeout_blocked_by_unmaterialized_followup_plans -q`
- 已通过：`py -3 -m pytest tests/test_ceo_scheduler.py::test_autopilot_closeout_parent_prefers_checker_handoff_maker_ticket -q`
- 已通过：`py -3 -m pytest tests/test_runtime_fallback_payload.py -q`
- 未全绿：`py -3 -m pytest tests/test_ceo_scheduler.py tests/test_runtime_fallback_payload.py -q` 当前失败 17 个 `tests/test_ceo_scheduler.py` 非本轮新增用例，集中在 governance / provider / project-init 相关路径；本轮未把该文件级套件标记为通过。

**建议测试命令：**

```powershell
cd D:\Projects\boardroom-os\backend
py -3 -m pytest tests/test_ceo_scheduler.py::test_deterministic_fallback_prefers_missing_backlog_followup_over_closeout -q
py -3 -m pytest tests/test_ceo_scheduler.py::test_autopilot_closeout_blocked_by_unmaterialized_followup_plans -q
py -3 -m pytest tests/test_ceo_scheduler.py tests/test_runtime_fallback_payload.py -q
```

**验收标准：**

- BR004-BR007 任一未 materialize 时，closeout 不可创建。
- 011 同类状态下 fallback 创建 BR004，而不是 `node_ceo_delivery_closeout`。
- 既有 closeout fallback 正常场景仍可在所有 implementation/checker 完成后创建 closeout。

**不要在本轮做：**

- 不改 graph health recovery。
- 不改 011 产物业务代码。
- 不扩大到所有 workflow stage 重构。

---

### Round 2：让 graph health/controller 支持合理等待与恢复

**目标：** `PERSISTENT_FAILURE_ZONE / CRITICAL` 不能永久卡住，也不能在健康门槛未恢复时强迫 CEO mutating action。成功 retry + review 后应降级或清除对应 critical finding；健康仍 critical 且建议 pause 时，controller 应允许 `NO_ACTION` 或 wait state。

**优先级：** P1，必须在 Round 1 后做。

**主要文件：**

- Modify: `backend/app/core/graph_health.py`
- Modify: `backend/app/core/workflow_controller.py`
- Modify: `backend/app/core/ceo_scheduler.py`
- Test: `backend/tests/test_ticket_graph.py`
- Test: `backend/tests/test_ceo_scheduler.py`
- Test: `backend/tests/test_scheduler_runner.py`

**需要理解的现有代码：**

- `backend/app/core/graph_health.py`
  - `PERSISTENT_FAILURE_ZONE` finding 生成逻辑
- `backend/app/core/graph_health_policy.py`
  - finding severity policy
- `backend/app/core/workflow_controller.py`
  - controller state 构建与 `workflow_controller_effect()`
- `backend/app/core/ceo_scheduler.py`
  - `_needs_deterministic_fallback_after_validation()`
  - `list_due_ceo_maintenance_workflows()`

**实施清单：**

- [x] 新增 failing test：`test_graph_health_clears_persistent_failure_zone_after_latest_retry_and_review_complete`
  - 位置：`backend/tests/test_ticket_graph.py`
  - 场景：同一 runtime node 先出现多次 failed tickets，随后 latest retry ticket completed，且 checker/review ticket completed。
  - 断言：graph health report 不再对该 node 输出 `PERSISTENT_FAILURE_ZONE` `CRITICAL`；或者 severity 降到非阻塞级别。

- [x] 新增 failing test：`test_controller_waits_when_graph_health_critical_recommends_pause`
  - 位置：`backend/tests/test_ceo_scheduler.py`
  - 场景：snapshot 有 unmaterialized followup plans，但 graph health summary 显示 `CRITICAL` 且 pause recommendation。
  - 断言：controller state 不应是 `READY_FOR_FANOUT / CREATE_TICKET`；应是明确 wait state，例如 `GRAPH_HEALTH_WAIT` 或已有可复用 wait state，`recommended_action == "NO_ACTION"`。

- [x] 新增 failing test：`test_scheduler_does_not_fallback_over_health_gate_no_action`
  - 位置：`backend/tests/test_ceo_scheduler.py`
  - 场景：live CEO 提 `NO_ACTION`，validator 因 controller action 拒绝，但 snapshot graph health critical。
  - 断言：scheduler 不执行 deterministic mutating fallback；记录 no-op 或 wait run。

- [x] 修改 graph health recovery
  - 查找 affected node 的最新 ticket。
  - 如果最新 implementation ticket `COMPLETED` 且相关 maker/checker verdict 或 review `COMPLETED/APPROVED`，不要只因历史失败继续输出 critical `PERSISTENT_FAILURE_ZONE`。
  - 如果仍有 active incident，保留 warning 或 recovering 状态，但不要让它等同于未恢复 critical。

- [x] 修改 controller
  - 把 graph health severity/pause recommendation 纳入 controller state。
  - 建议新增或复用 wait state：
    - `GRAPH_HEALTH_WAIT`
    - `recommended_action: "NO_ACTION"`
    - `blocking_reason` 写明 critical graph health 尚未恢复。
  - `workflow_controller_effect()` 应把该状态映射到等待效果，例如 `WAIT_FOR_GRAPH_HEALTH`。

- [x] 修改 scheduler fallback 条件
  - `_needs_deterministic_fallback_after_validation()` 不能只看 expected action。
  - 如果 snapshot graph health critical 且 controller/wait signal 表示 pause，不能从 rejected `NO_ACTION` 转成 deterministic mutating action。

**建议测试命令：**

```powershell
cd D:\Projects\boardroom-os\backend
py -3 -m pytest tests/test_ticket_graph.py::test_graph_health_clears_persistent_failure_zone_after_latest_retry_and_review_complete -q
py -3 -m pytest tests/test_ceo_scheduler.py::test_controller_waits_when_graph_health_critical_recommends_pause -q
py -3 -m pytest tests/test_ceo_scheduler.py::test_scheduler_does_not_fallback_over_health_gate_no_action -q
py -3 -m pytest tests/test_ticket_graph.py tests/test_ceo_scheduler.py tests/test_scheduler_runner.py -q
```

**Round 2 验证记录（2026-04-25）：**

- 已通过：`py -3 -m pytest tests/test_ticket_graph.py::test_graph_health_clears_persistent_failure_zone_after_latest_retry_and_review_complete -q`
- 已通过：`py -3 -m pytest tests/test_ceo_scheduler.py::test_controller_waits_when_graph_health_critical_recommends_pause -q`
- 已通过：`py -3 -m pytest tests/test_ceo_scheduler.py::test_scheduler_does_not_fallback_over_health_gate_no_action -q`
- 已通过：`py -3 -m pytest tests/test_ticket_graph.py::test_graph_health_report_detects_persistent_failure_zone -q`
- 已通过：`py -3 -m pytest tests/test_ceo_scheduler.py::test_ceo_shadow_run_rejects_live_no_action_when_controller_requires_backlog_fanout -q`
- 未全绿：`py -3 -m pytest tests/test_ticket_graph.py tests/test_ceo_scheduler.py tests/test_scheduler_runner.py -q` 当前结果 51 failed / 172 passed；失败集中在非本轮新增定向用例覆盖的 graph contract、CEO provider payload、scheduler runtime/worker routing 路径，本轮只将 Round 2 定向回归标记为通过。

**验收标准：**

- 成功 retry + review 后，graph health 不再把同一 node 永久标为 critical persistent failure zone。
- graph health critical 时，controller 不强迫 `CREATE_TICKET`。
- scheduler 不再把合理 `NO_ACTION` 硬转成 mutating fallback。

**不要在本轮做：**

- 不改 closeout/fanout 顺序，除非 Round 1 未完成。
- 不改 live harness full success 断言。
- 不改 011 产物业务代码。

---

### Round 3：收紧 live harness 成功门槛与测试中修改审计

**目标：** full live 的 `success=true` 必须代表本场景要求的 fanout、实现、证据、checker handoff 已经完成；failed retry history 可以不直接判失败，但必须进入审计。非 clean resume 不能把旧 completed workflow 当作新运行成功。

**优先级：** P1/P2，Round 1-2 后做。

**主要文件：**

- Modify: `backend/tests/live/_autopilot_live_harness.py`
- Modify: `backend/tests/live/_scenario_profiles.py`
- Modify: `backend/tests/live/_config.py` only if assertions config needs explicit gate fields
- Test: `backend/tests/test_live_library_management_runner.py`
- Test: `backend/tests/test_live_configured_runner.py`

**需要理解的现有代码：**

- `backend/tests/live/_autopilot_live_harness.py`
  - `_assert_source_delivery_payload_quality()`
  - `_assert_unique_source_delivery_evidence_paths()`
  - `_latest_resumable_workflow_id()`
  - `run_live_scenario_with_provider_payload()`
  - `collect_common_outcome()`
  - `write_audit_summary()`
- `backend/tests/live/_scenario_profiles.py`
  - `_assert_minimalist_book_tracker()`
  - `_missing_required_capabilities()`

**实施清单：**

- [x] 新增 failing test：`test_library_outcome_rejects_missing_followup_fanout_even_if_capability_terms_present`
  - 位置：`backend/tests/test_live_library_management_runner.py`
  - 场景：`created_specs` 和 terminal payload 文本包含 books/add/check out/remove 等关键词，但 BR004-BR007 对应 followup ticket 不存在。
  - 断言：`_assert_minimalist_book_tracker()` 抛出 `AssertionError`，错误指向 missing followup materialization。

- [x] 新增 failing test：`test_library_outcome_requires_checker_handoff_before_full_success`
  - 位置：`backend/tests/test_live_library_management_runner.py`
  - 场景：source delivery tickets 完成，但没有 checker handoff / maker_checker verdict / delivery check evidence。
  - 断言：full success assertion 失败。

- [x] 新增 failing test：`test_failed_retry_history_is_reported_in_audit_summary_without_blocking_final_success`
  - 位置：`backend/tests/test_live_library_management_runner.py`
  - 场景：一个 source delivery retry failed，后续 retry completed。
  - 断言：`_assert_source_delivery_payload_quality()` 返回 completed ticket；同时 `write_audit_summary()` 或新增 audit collector 输出 failed retry count/detail。

- [x] 新增 failing test：`test_non_clean_resume_does_not_report_existing_completed_workflow_as_new_success`
  - 位置：`backend/tests/test_live_library_management_runner.py`
  - 场景：repository 最新 workflow 已 `COMPLETED`，以 `clean=False` 启动。
  - 断言：runner 要么创建新 workflow，要么以 explicit resumed-completed mode 返回，不得标为本次 `completion_mode="full"`。

- [x] 修改 `_assert_minimalist_book_tracker()`
  - 不再只用关键词 corpus 判断 scope capabilities。
  - 增加结构化断言：
    - backlog recommendation 存在 BR001-BR007 或等价 capability plan。
    - BR004-equivalent service behavior ticket completed。
    - BR005-equivalent terminal/e2e ticket completed。
    - BR006-equivalent tests/evidence ticket completed。
    - BR007-equivalent checker handoff completed。
  - 如果无法依赖固定 BR id，按 `implementation_handoff.recommended_sequence` 和 `capability_plan.followup_ticket_plans` 推导 required followups。

- [x] 修改 `_assert_source_delivery_payload_quality()`
  - failed retry tickets 不阻断最终 completed retry，但要返回或记录 failed retry audit entries。
  - compact payload 只在明确 schema 支持且包含 written artifacts、verification evidence、raw command/output 时可接受。

- [x] 修改 resume 语义
  - `_latest_resumable_workflow_id()` 默认只返回 `EXECUTING`。
  - 如果确实需要 attach completed workflow，应通过显式 `--attach-completed` 或报告 `completion_mode="attached_completed_report_only"`，不能当作新 full run 成功。

**建议测试命令：**

```powershell
cd D:\Projects\boardroom-os\backend
py -3 -m pytest tests/test_live_library_management_runner.py::test_library_outcome_rejects_missing_followup_fanout_even_if_capability_terms_present -q
py -3 -m pytest tests/test_live_library_management_runner.py::test_library_outcome_requires_checker_handoff_before_full_success -q
py -3 -m pytest tests/test_live_library_management_runner.py::test_failed_retry_history_is_reported_in_audit_summary_without_blocking_final_success -q
py -3 -m pytest tests/test_live_library_management_runner.py::test_non_clean_resume_does_not_report_existing_completed_workflow_as_new_success -q
py -3 -m pytest tests/test_live_library_management_runner.py tests/test_live_configured_runner.py -q
```

**Round 3 验证记录（2026-04-25）：**

- 已通过：`py -3 -m pytest --basetemp .tmp\pytest-round3 tests/test_live_library_management_runner.py::test_library_outcome_rejects_missing_followup_fanout_even_if_capability_terms_present -q`
- 已通过：`py -3 -m pytest --basetemp .tmp\pytest-round3b tests/test_live_library_management_runner.py::test_library_outcome_requires_checker_handoff_before_full_success -q`
- 已通过：`py -3 -m pytest --basetemp .tmp\pytest-round3c tests/test_live_library_management_runner.py::test_failed_retry_history_is_reported_in_audit_summary_without_blocking_final_success -q`
- 已通过：`py -3 -m pytest --basetemp .tmp\pytest-round3d tests/test_live_library_management_runner.py::test_non_clean_resume_does_not_report_existing_completed_workflow_as_new_success -q`
- 已通过：`py -3 -m pytest --basetemp .tmp\pytest-round3-suite tests/test_live_library_management_runner.py tests/test_live_configured_runner.py -q`，结果 52 passed。
- 说明：本机默认 pytest temp root `C:\Users\yb371\AppData\Local\Temp\pytest-of-yb371` 当前会触发 `PermissionError`，本轮验证显式使用仓库内 `.tmp` basetemp。

**验收标准：**

- 011 这种 BR004-BR007 missing 不能再得到 `success=true/full`。
- failed retry history 被审计记录，不再被静默跳过。
- compact completed payload 不能绕过 source/test/e2e/checker 证据要求。
- 非 clean resume 不再把已有 completed workflow 当本次成功。

**不要在本轮做：**

- 不修 graph health。
- 不修产品服务层。
- 不运行长 live 作为唯一验证；本轮以定向 harness tests 为主。

---

### Round 4：补齐 011 产品行为与 BR004-BR007 等价交付

**目标：** 011 产物从 parser/repository 切片变成可验证的 terminal/console 单机图书状态系统：Add、Check Out、Return、Remove 会真实修改 SQLite；availability 会真实查询库存；terminal rendering/e2e 和 checker evidence 可证明核心路径。

**优先级：** P1/P2，必须在控制面和 harness 不再假绿后做。

**主要文件：**

- Modify/Create under scenario artifact if continuing 011 artifact:
  - `backend/data/scenarios/library_management_autopilot_live_011/artifacts/10-project/src/terminal_command_contract.py`
  - `backend/data/scenarios/library_management_autopilot_live_011/artifacts/10-project/src/books_db.py`
  - `backend/data/scenarios/library_management_autopilot_live_011/artifacts/10-project/src/books_db_contract_probe.py`
  - Create: `backend/data/scenarios/library_management_autopilot_live_011/artifacts/10-project/src/library_service.py`
  - Create: `backend/data/scenarios/library_management_autopilot_live_011/artifacts/10-project/src/terminal_renderer.py`
  - Create: `backend/data/scenarios/library_management_autopilot_live_011/artifacts/10-project/tests/test_library_service.py`
  - Create: `backend/data/scenarios/library_management_autopilot_live_011/artifacts/10-project/tests/test_terminal_e2e.py`

如果目标是修主线生成能力，而不是只修 011 artifact，则不要直接改 scenario artifact；应把相同行为要求转成 control-plane prompt/schema/harness 约束，并用 live/smoke 生成新 artifact 验证。

**需要理解的现有代码：**

- `terminal_command_contract.py`
  - `parse_command()` 目前只解析并返回 success，不调用 repository。
  - `_book_snapshot()` 目前伪造 `Book {id}` / `Unknown Author` / `AVAILABLE`。
- `books_db.py`
  - `BooksRepository.insert_book()`
  - `get_book_by_id()`
  - `list_books()`
  - `list_title_candidates()`
  - `update_status_by_id()`
  - `delete_in_library_by_id()`
  - `close()`
- `books_db_contract_probe.py`
  - 目前没有 `finally: repo.close()`，Windows 下可能锁 SQLite 文件。

**实施清单：**

- [x] 新增 `library_service.py`
  - 定义 service result 类型。
  - `add_book(title, author)` 调用 `BooksRepository.insert_book()`。
  - `check_out(book_id)`：
    - missing id -> fail closed
    - `CHECKED_OUT` -> no state change
    - `IN_LIBRARY` -> update to `CHECKED_OUT`
  - `return_book(book_id)`：
    - missing id -> fail closed
    - `IN_LIBRARY` -> no state change
    - `CHECKED_OUT` -> update to `IN_LIBRARY`
  - `remove_book(book_id, confirm)`：
    - no confirm -> return confirmation with real id/title/author/status
    - missing id -> fail closed
    - checked out -> deny
    - confirm yes and in library -> delete exact row
  - `availability_by_title(title)`：
    - no match -> `NOT_FOUND`
    - one normalized author group -> aggregate total/in_library and can-take-now
    - multiple normalized author groups -> `AMBIGUOUS_TITLE`

- [x] 修改 `terminal_command_contract.py`
  - 保留 parser，但把 state-changing commands 交给 service。
  - `availability/title` 和 `availability/id` 查询 repository，不再返回 queued echo。
  - 删除或停止使用 `_book_snapshot()` 伪造结果。

- [x] 新增 `terminal_renderer.py`
  - 将 service result 渲染为高信息密度纯文本。
  - 不引入 web UI、权限系统、时间轴、分类、用户历史。

- [x] 修 `books_db_contract_probe.py`
  - 用 `with BooksRepository(db_path) as repo:` 或 `try/finally: repo.close()`。
  - Windows 下 `TemporaryDirectory` cleanup 不应因 SQLite handle 未关闭失败。

- [x] 新增 service tests
  - add 后 list 可见。
  - check out 后 repository status 变 `CHECKED_OUT`。
  - return 后 status 变 `IN_LIBRARY`。
  - checked-out book 不可 remove。
  - missing id 不改变状态。
  - title availability 覆盖 single match、multiple copies、checked-out-only、ambiguous title。

- [x] 新增 terminal e2e tests
  - canonical run：
    - add
    - catalog/list
    - availability/title
    - check out
    - availability/title
    - return
    - remove confirm=no
    - remove confirm=yes
    - catalog/list
  - 断言每一步输出和 repository 状态一致。

**建议测试命令：**

```powershell
cd D:\Projects\boardroom-os\backend\data\scenarios\library_management_autopilot_live_011\artifacts\10-project
py -3 -m pytest tests/test_library_service.py tests/test_terminal_e2e.py -q
py -3 src/books_db_contract_probe.py
```

若本轮改的是主线生成能力，而非 scenario artifact，再补：

```powershell
cd D:\Projects\boardroom-os\backend
py -3 -m pytest tests/test_live_library_management_runner.py tests/test_runtime_fallback_payload.py -q
```

**Round 4 验证记录（2026-04-25）：**

- 已确认红灯：新增 Round4 测试首次运行失败于 `ModuleNotFoundError: No module named 'library_service'`，对应缺失 service artifact。
- 已通过：`py -3 -m pytest --basetemp .tmp\pytest-round4-final tests/test_library_service.py tests/test_terminal_e2e.py -q`，结果 8 passed。
- 已通过：`py -3 src/books_db_contract_probe.py`，输出包含 `PASS_CONTRACT_CHECKS` 和 `FINAL_COUNT=3`。
- 已通过：`py -3 -m compileall -q src tests`。
- 说明：本机默认 pytest temp root `C:\Users\yb371\AppData\Local\Temp\pytest-of-yb371` 当前仍会触发 `PermissionError`，本轮验证显式使用 scenario artifact 内 `.tmp` basetemp。

**验收标准：**

- `check out 1` 后 SQLite 中 id=1 的 status 必须变为 `CHECKED_OUT`。
- `availability/title <title>` 必须读取 SQLite，并输出是否可拿走。
- `remove 999 confirm=yes` 不能成功。
- `remove <checked_out_id> confirm=yes` 不能删除。
- probe 在 Windows 下退出码为 0。
- checker/evidence 能证明 canonical run，而不是只证明 schema 合规。

**不要在本轮做：**

- 不把 terminal-only scope 改成 web UI。011 的 scenario 明确是单机 terminal/console。
- 不新增权限、用户、借阅历史、时间戳、分类表。
- 不把业务失败伪装成 parser success。

---

### Round 5：ready ticket 无可用员工时触发 CEO 按需雇佣

**目标：** 当图上已有 ready/pending ticket，但 scheduler 因 role profile 不匹配、worker 被 `excluded_employee_ids` 排除、或 roster 缺少对应员工而无法 lease 时，系统不能长期保持 `READY_TICKET / NO_ACTION`。该状态应反馈为 staffing gap，由 controller 产出 `HIRE_EMPLOYEE`，让 CEO 自动拼装合适员工接手图节点。

**优先级：** P1/P2。011 中这是人工修补过的真实卡点；若不修，后续 live run 仍可能靠人工插员工才能继续。

**011 证据：**

- 时间：2026-04-25 16:23-16:27 +08:00。
- 现象：BR002/BR003 rework tickets 已 ready，但 scheduler 反复空转，未能 lease。
- 原因：tickets 需要 `backend_engineer_primary` 和 `database_engineer_primary`，roster 当时缺少可用 backend/database 员工，原 frontend worker 又被 rework `excluded_employee_ids` 排除。
- 手工修补：通过 CEO direct hire handler 插入：
  - `emp_backend_integration_011`
  - `emp_database_integration_011`
  - `emp_platform_integration_011`
- DB 事件：三条 `EMPLOYEE_HIRED` 事件 actor 显示为 `ceo`，但这是测试过程中人工调用 handler 的最小修补，不是 live CEO 自行提出并执行的 `HIRE_EMPLOYEE`。
- 结果：插入 backend/database 员工后，scheduler 立即 lease BR002/BR003 rework tickets。

**主要文件：**

- Modify: `backend/app/core/workflow_controller.py`
- Modify: `backend/app/core/scheduler.py` 或实际 lease/worker selection 所在模块
- Modify: `backend/app/core/ceo_scheduler.py`
- Modify: `backend/app/core/ceo_proposer.py` only if deterministic hire fallback shape needs adjustment
- Test: `backend/tests/test_ceo_scheduler.py`
- Test: `backend/tests/test_scheduler_runner.py`
- Test: worker routing / scheduler leasing 相关测试文件，按实际命名补充

**需要理解的现有代码：**

- `backend/app/core/workflow_controller.py`
  - `staffing_gaps`
  - `_recommended_hire_for_role_profile()`
  - controller state `HIRE_EMPLOYEE`
  - `capability_plan.recommended_hire`
- `backend/app/core/ceo_proposer.py`
  - `_build_capability_hire_batch()`
  - `build_deterministic_fallback_batch()`
- `backend/app/core/ceo_executor.py`
  - `HIRE_EMPLOYEE` execution path
  - `handle_ceo_direct_employee_hire()`
- scheduler lease selection path
  - ready ticket collection
  - eligible employee filtering
  - `excluded_employee_ids`
  - role profile matching

**实施清单：**

- [x] 新增 failing test：`test_ready_ticket_without_eligible_worker_surfaces_staffing_gap`
  - 位置：`backend/tests/test_scheduler_runner.py` 或 scheduler routing 测试文件。
  - 场景：创建 ready ticket，role profile 为 `backend_engineer_primary`；roster 无 backend worker，或唯一候选在 `excluded_employee_ids`。
  - 断言：scheduler/diagnostic 层输出明确的 `NO_ELIGIBLE_WORKER` 或等价 staffing signal，包含 ticket id、node id、required role profile、排除原因。

- [x] 新增 failing test：`test_controller_recommends_hire_when_ready_ticket_has_no_eligible_worker`
  - 位置：`backend/tests/test_ceo_scheduler.py`。
  - 场景：snapshot 中存在 ready ticket，但 lease diagnostics 表明无 eligible worker。
  - 断言：
    - controller state 不是 `READY_TICKET / NO_ACTION`
    - controller state 为 `STAFFING_REQUIRED` 或现有等价状态
    - `recommended_action == "HIRE_EMPLOYEE"`
    - `capability_plan.recommended_hire.role_profile_refs` 包含缺失角色，例如 `backend_engineer_primary`

- [x] 新增 failing test：`test_ceo_hire_fallback_uses_missing_ready_ticket_role_profile`
  - 位置：`backend/tests/test_ceo_scheduler.py`。
  - 场景：controller 推荐 `HIRE_EMPLOYEE`，capability plan 中有 `recommended_hire`。
  - 断言：`build_deterministic_fallback_batch()` 生成合法 `HIRE_EMPLOYEE` action，payload 包含 `workflow_id`、`role_type`、`role_profile_refs`、`request_summary`，不使用 legacy shape。

- [x] 新增 failing test：`test_scheduler_progresses_ready_ticket_after_ceo_hire`
  - 位置：`backend/tests/test_scheduler_runner.py`。
  - 场景：先运行一次 scheduler，发现 no eligible worker；CEO hire backend/database worker；再运行 scheduler。
  - 断言：原 ready ticket 被新员工 lease，而不是继续空转。

- [x] 修改 scheduler/lease diagnostics
  - ready ticket 如果无法 lease，不应只表现为 runtime execution count 0。
  - 需要记录结构化原因：
    - required role profile
    - 当前 roster 中缺失 role
    - 候选员工被排除的原因
    - 是否存在 inactive / unapproved / provider 不匹配候选
  - 该 signal 必须进入 controller snapshot 或 capability plan 输入。

- [x] 修改 controller
  - 如果存在 ready ticket 且 no eligible worker diagnostic，优先输出 staffing-required 状态，而不是 `READY_TICKET / NO_ACTION`。
  - 生成 `capability_plan.staffing_gaps` 和 `capability_plan.recommended_hire`。
  - 如果多个 ready tickets 缺不同角色，先选择最早 ready / critical path / highest priority 的角色；不要一次无界雇佣大量员工。

- [x] 修改 CEO scheduler/fallback
  - 当 controller 推荐 `HIRE_EMPLOYEE` 时，允许 live CEO 或 deterministic fallback 创建 hire action。
  - 如果 live CEO `NO_ACTION` 但 controller 推荐 hire，fallback 可执行 hire；但仍需尊重 graph health 的 hard wait gate。

- [x] 修改 live audit
  - 如果 live run 中发生 no eligible worker，audit summary 应记录 staffing gap 和后续 hire action。
  - 不再允许人工插员工成为唯一可见修复动作。

**建议测试命令：**

```powershell
cd D:\Projects\boardroom-os\backend
py -3 -m pytest tests/test_scheduler_runner.py::test_ready_ticket_without_eligible_worker_surfaces_staffing_gap -q
py -3 -m pytest tests/test_ceo_scheduler.py::test_controller_recommends_hire_when_ready_ticket_has_no_eligible_worker -q
py -3 -m pytest tests/test_ceo_scheduler.py::test_ceo_hire_fallback_uses_missing_ready_ticket_role_profile -q
py -3 -m pytest tests/test_scheduler_runner.py::test_scheduler_progresses_ready_ticket_after_ceo_hire -q
```

**Round 5 验证记录（2026-04-26）：**

- 已确认红灯：`test_ready_ticket_without_eligible_worker_surfaces_staffing_gap` 首次失败于缺少 `SCHEDULER_LEASE_DIAGNOSTIC_RECORDED / NO_ELIGIBLE_WORKER` 事件。
- 已确认红灯：`test_controller_recommends_hire_when_ready_ticket_has_no_eligible_worker` 首次失败为 controller 仍返回 `READY_TICKET`，未推荐 `HIRE_EMPLOYEE`。
- 已确认红灯：`test_ceo_hire_fallback_uses_missing_ready_ticket_role_profile` 首次失败为 deterministic fallback 返回 `NO_ACTION`，未生成 `HIRE_EMPLOYEE`。
- 已确认红灯：`test_write_audit_summary_renders_staffing_gap_and_hire_action` 首次失败于 audit summary 缺少 `Staffing Gap Audit`。
- 已通过：`py -3 -m pytest --basetemp .tmp\pytest-round5-final-reapply tests/test_scheduler_runner.py::test_ready_ticket_without_eligible_worker_surfaces_staffing_gap tests/test_ceo_scheduler.py::test_controller_recommends_hire_when_ready_ticket_has_no_eligible_worker tests/test_ceo_scheduler.py::test_ceo_hire_fallback_uses_missing_ready_ticket_role_profile tests/test_scheduler_runner.py::test_scheduler_progresses_ready_ticket_after_ceo_hire tests/test_live_library_management_runner.py::test_write_audit_summary_renders_staffing_gap_and_hire_action -q`，结果 5 passed。
- 说明：`test_scheduler_progresses_ready_ticket_after_ceo_hire` 验证 hire 后原 ready ticket 被新员工 lease；为避免单测触发真实 provider runtime，本用例断言最终状态为 `LEASED`，不要求 runtime 完成。

**验收标准：**

- ready ticket 无 eligible worker 时，系统产生结构化 staffing gap。
- controller 推荐 `HIRE_EMPLOYEE`，而不是继续 `READY_TICKET / NO_ACTION`。
- CEO hire action 自动创建所需角色员工。
- hire 后 scheduler 能 lease 原 ready ticket。
- 011 同类状态不再需要手工插入 `emp_backend_integration_011` / `emp_database_integration_011` / `emp_platform_integration_011` 才能推进。

**不要在本轮做：**

- 不把所有空转都解释成 staffing gap；只有 ready ticket 存在且 lease diagnostics 证明无 eligible worker 时才触发。
- 不绕过 board-approved / provider routing / role profile 约束。
- 不默认雇佣 platform SRE；011 实际需要的是 backend/database，platform 当时是保守人工补位。
- 不改 Round 1-4 的 closeout、graph health、harness、产品行为修复逻辑。

---

## 3. 推荐每轮开工前命令

每轮都先跑：

```powershell
cd D:\Projects\boardroom-os
git status --short
git log --oneline -n 8
```

如果工作区不干净：

- 不要 revert 用户改动。
- 只读理解相关 diff。
- 若相关文件已有未提交修改，先判断是否和本轮目标冲突。

每轮进入 backend 后再跑定向测试，不默认跑全仓大测试：

```powershell
cd D:\Projects\boardroom-os\backend
py -3 -m pytest <本轮测试> -q
```

## 4. 最终整体验收

五轮都完成后，至少要有这些证据：

1. Round 1 regression：missing BR004-BR007 时 fallback 创建 BR004，不 closeout。
2. Round 2 regression：critical graph health 下 controller/scheduler 允许 wait；成功 retry+review 后 critical 清除或降级。
3. Round 3 regression：011 缺 BR004-BR007 不能 full success；failed retry history 进入 audit。
4. Round 4 behavior：terminal commands 真实查询/修改 SQLite。
5. Round 5 regression：ready ticket 无 eligible worker 时 controller 推荐 hire，CEO 自动雇佣后 scheduler 能 lease 原 ticket。
6. 可选 live clean run：

```powershell
cd D:\Projects\boardroom-os\backend
py -3 -m tests.live.run_configured --config data/live-tests/library_management_autopilot_live_011.toml --clean --max-ticks 180 --timeout-sec 7200
```

live clean run 成功时仍要人工核对：

- BR004-BR007 或等价 followups 已 materialize。
- closeout 在 checker handoff 之后。
- staffing gap 如出现，应由 CEO `HIRE_EMPLOYEE` 自动修复，而不是人工插员工。
- `run_report.json` 的 `success=true` 对应完整产品行为证据。
- `audit-summary.md` 包含 failed retry history 与最终 completed evidence。

## 5. 常见误判

- 不要把 `success=true` 当产品完成。
- 不要把 BR002 command contract smoke evidence 当全链路 delivery evidence。
- 不要因为 `ticket_summary.active_count == 0` 就允许 closeout。
- 不要把 graph health historical failures 永久等同于当前 critical。
- 不要把 failed retry history 从 audit 中删除。
- 不要把 scenario artifact 的临时修补当成主线生成能力修复。
- 不要把 ready ticket 无法 lease 的人工员工插入当成主线 staffing 修复。
- 不要把 011 改成网站；本轮目标是 terminal/console。

## 6. 建议提交拆分

如果后续会话需要提交，建议每轮一个或多个小提交：

- `fix(ceo): 阻止扇出未完成时提前收尾`
- `fix(graph): 恢复成功后降级持久失败区`
- `test(live): 收紧011完整交付断言`
- `fix(library): 接通终端命令与库存状态`
- `fix(staffing): ready票据无可用员工时触发雇佣`

不要把五轮混成一个提交。
