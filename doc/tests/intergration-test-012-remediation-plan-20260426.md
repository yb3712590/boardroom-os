# intergration-test-012 整改方案

> **For agentic workers:** 后续独立会话实施本方案时，建议使用 `executing-plans` 或按本文件每轮独立执行。步骤使用 checkbox (`- [ ]`) 追踪。每轮只收一个问题族，完成前必须运行本轮列出的定向验证，并在最终回复里如实报告无法执行的验证。

**目标：** 把 012 从“业务 workflow 已完成但 runner / harness / recovery contract 仍有灰区”整改为“依赖 gate、source delivery、closeout、chain report、provider failure 都符合 `doc/new-architecture/*.md` 的显式 contract 与幂等恢复原则”。

**架构：** 先收 dependency gate 的 completed-ticket 可用性定义，再把 chain report 前移到 production completion path；随后统一 source delivery compact/full 证据合同，收紧 closeout final evidence 白名单，最后把 provider / hook / schema failure 从“被 retry 覆盖”提升为可审计的 recovery 链。不要把 harness replay 成功当作 production contract 已满足，也不要让旧 completed ticket 遮蔽后续 replacement / supersession / evidence invalidation。

**Tech Stack:** Python, pytest, SQLite-backed control-plane repository, boardroom-os runtime, live harness, workflow autopilot, workspace hooks.

---

## 0. 真相源与当前结论

本方案只服务 012：

- 测试报告：`doc/tests/intergration-test-012-20260426.md`
- 参照方案：`doc/tests/intergration-test-011-remediation-plan-20260425.md`
- live config：`backend/data/live-tests/library_management_autopilot_live_012.toml`
- 最终 workflow：`wf_6695c18ddb6f`
- 最终状态：`COMPLETED / closeout`
- ticket 汇总：`COMPLETED=28 / FAILED=6`
- 原始 runner 退出：失败，失败于 final collection 缺少 workflow chain report artifact
- 修补后 DB replay：`collect_common_outcome()` 通过，compiled / archived tickets 为 `34 / 34`

必须先接受这个结论：

- 012 的业务 workflow 和人工产物查看结论是成功的。
- 原始 runner 自然退出仍是失败，不能把 replay 成功改写成“原 runner 成功”。
- 本轮多数修补方向符合新架构，但有几个 contract 需要继续收口。
- provider bad JSON、invalid content、closeout artifact refs 不合规并没有被根治，只是被 retry / replacement / 后续 closeout 覆盖。
- `.tmp/library_preview_server.py` 是临时预览 harness，不是产品架构修复。

本方案重点对照这些新架构底线：

- `doc/new-architecture/00-autonomous-machine-overview.md`：节点完成不等于下游可见，必要 hook 和证据必须落地。
- `doc/new-architecture/02-ticket-graph-engine.md`：Ticket 真相应是 versioned DAG，替换必须显式 `REPLACES`，旧节点进入 `SUPERSEDED`。
- `doc/new-architecture/03-worker-context-and-execution-package.md`：source code delivery 必须有源码、测试证据、文档更新、git 证据。
- `doc/new-architecture/05-incident-idempotency-and-recovery.md`：禁止静默 fallback 掩盖真实失败；恢复动作必须显式、可重放。
- `doc/new-architecture/06-role-hook-system.md`：required hooks 失败不能默默放行下游。
- `doc/new-architecture/11-governance-profile-and-audit-modes.md`：`MINIMAL` 不能关闭事件、图状态变化和最低交付证据。
- `doc/new-architecture/13-cross-cutting-concerns.md`：幂等键、版本号、资产引用应统一并可追溯。
- `doc/new-architecture/14-graph-health-monitor.md`：失败热区、ready stale、persistent failure 需要进入 CEO 读面或 incident。

## 1. 本方案明确纳入审计的 012 修改

### 1.1 建议保留的修改

- [ ] 保留 `backend/app/core/workflow_controller.py` 中 `_build_followup_ticket_plans()` 显式接收并写入当前 `workflow_id` 的方向。
  - 架构判断：这是 controller contract 构造错误修复，符合“workflow id 是 controller view 上下文事实，不从派生 payload 反推”的原则。
  - 后续要求：审计是否还有从 created payload 反推顶层 workflow context 的模式。

- [ ] 保留 `backend/app/core/ceo_proposer.py` 中 backlog 无可构造动作时返回 `None`，并允许 closeout / `NO_ACTION` 的方向。
  - 架构判断：这是状态机稳态处理修复，符合“可创建、可 closeout、可等待”三态表达。
  - 后续要求：provider validator 与 deterministic fallback 必须共享同一 controller action expectation。

- [ ] 保留 `backend/tests/live/_autopilot_live_harness.py` 中 failure snapshot 审计容错。
  - 架构判断：失败快照应 best-effort 保存现场，不能用二次质量审计覆盖原始失败。
  - 后续要求：最终 `collect_common_outcome()` 仍必须严格，不因 snapshot 容错放宽成功门槛。

- [ ] 保留 `backend/tests/live/_autopilot_live_harness.py` 中 compact source delivery evidence 审计读取。
  - 架构判断：harness 理解 compact payload 不等于降低证据要求。
  - 后续要求：compact/full 两种 source delivery payload 需要正式 contract 化。

- [ ] 保留 `backend/app/core/runtime.py` 中 source delivery verification path attempt normalization 方向。
  - 架构判断：provider 输出是不稳定输入，runtime 在 workspace hook 前 canonicalize 是正确边界防御。
  - 后续要求：覆盖所有 source delivery 入口，并确认 attempt no 使用当前 execution package。

### 1.2 建议保留但必须继续整改的修改

- [ ] `backend/app/core/ceo_proposer.py`：latest existing ticket 失败时使用同 node completed ticket 满足依赖 gate。
  - 风险：当前 node-only 兜底可能让旧 completed ticket 掩盖后续失败证明出的失效、replacement 或 superseded 状态。
  - 整改方向：引入 completed ticket 可用性判断，至少检查 schema、terminal evidence、lineage、replacement / supersession、artifact validity。

- [ ] `backend/tests/live/_autopilot_live_harness.py`：`collect_common_outcome()` 检查 chain report 前调用 `ensure_workflow_atomic_chain_report()`。
  - 风险：如果 chain report 是 completion contract 的一部分，只在 harness 收集阶段补齐会让 production completion path contract 变弱。
  - 整改方向：production closeout / auto-advance 在标记 workflow completed 前应保证 chain report 物化；harness ensure 只作为幂等补救。

### 1.3 未修复，仅被恢复机制覆盖的问题

- [ ] provider bad JSON / invalid content。
- [ ] closeout package 曾把非 delivery evidence artifact 放入 `payload.final_artifact_refs`。
- [ ] provider schema compliance 不稳定。
- [ ] 最终历史里仍保留 failed tickets，必须进入 audit summary，而不是从成功结论中消失。

### 1.4 临时动作，不纳入产品架构

- [ ] 多次停止旧 live runner 并 clean 重启：属于测试推进操作，不是 runtime 修复。
- [ ] `.tmp/library_preview_server.py`：仅用于本地查看产物的临时预览服务，不作为业务代码修复。

---

## 2. 六轮执行顺序

### Round 1：收紧 completed ticket 兜底的依赖 gate

**目标：** 保留“同节点已有有效 completed ticket 可满足下游依赖”的能力，但不能让旧完成票据掩盖后续明确 supersede / replacement / evidence invalidation。

**优先级：** P1，必须第一轮做。P03 是本轮最大架构偏移风险。

**主要文件：**

- Modify: `backend/app/core/ceo_proposer.py`
- Modify: `backend/app/core/workflow_completion.py`
- Test: `backend/tests/test_ceo_scheduler.py`

**需要理解的现有代码：**

- `backend/app/core/ceo_proposer.py`
  - `_latest_completed_ticket_id_for_node()`
  - `_prefer_completed_ticket_when_existing_terminal_failed()`
  - `_build_backlog_followup_batch()`
  - `_build_existing_backlog_followup_retry_action()`
- `backend/app/core/workflow_completion.py`
  - `_ticket_lineage_ticket_ids()`
  - `delivery_mainline_stage_for_ticket()`
  - `_is_redundant_active_delivery_ticket()`
- `backend/tests/test_ceo_scheduler.py`
  - `test_backlog_followup_batch_uses_completed_attempt_when_latest_existing_ticket_failed`
  - `test_backlog_followup_batch_raises_structured_restore_needed_for_existing_ticket_without_direct_retry`

**实施清单：**

- [ ] 新增 helper：`_completed_ticket_satisfies_followup_dependency_gate()`
  - 位置：`backend/app/core/ceo_proposer.py`
  - 输入：`repository`, `connection`, `workflow_id`, `node_id`, `completed_ticket_id`, `planned_output_schema_ref`, `terminal_failed_ticket_id`
  - 返回：`bool`
  - 判定必须同时满足：
    - completed ticket 存在且 `status == "COMPLETED"`
    - completed ticket 的 `workflow_id` 与当前 workflow 一致
    - completed ticket 的 `node_id` 与 planned node 一致
    - completed ticket created spec 的 `output_schema_ref` 与 planned `output_schema_ref` 一致
    - completed ticket 有 terminal event，且 terminal payload 至少包含 `artifact_refs`、`verification_evidence_refs` 或可识别的 delivery evidence
    - terminal failed ticket 没有通过 parent lineage、replacement、graph patch 或 created spec 明确声明该 completed ticket 已被替代

- [ ] 将 `_prefer_completed_ticket_when_existing_terminal_failed()` 改成只返回满足 helper 的 completed ticket。
  - 不满足时保留原 failed ticket id，让后续 retry / restore-needed 路径处理。
  - 不允许只靠 `workflow_id + node_id + latest COMPLETED` 判定可用。

- [ ] 新增 failing test：`test_backlog_followup_completed_attempt_superseded_by_failed_replacement_does_not_open_downstream`
  - 位置：`backend/tests/test_ceo_scheduler.py`
  - 场景：
    - 同一 workflow / node 先有 `tkt_followup_completed_attempt` completed。
    - 后续有 `tkt_followup_failed_replacement` failed，created spec parent 或 replacement 关系指向 completed attempt，并表达这是替代尝试。
    - 下游 `BR-NEXT` blocked by 该 plan。
  - 断言：
    - `_build_backlog_followup_batch()` 不创建 `BR-NEXT`。
    - 结果应是 retry action 或 structured restore-needed error。
    - `dependency_gate_refs` 不得指向被 superseded 的 completed attempt。

- [ ] 新增 passing regression：`test_backlog_followup_completed_attempt_still_satisfies_gate_when_failed_retry_is_unrelated`
  - 位置：`backend/tests/test_ceo_scheduler.py`
  - 场景：
    - completed ticket 有有效 source delivery evidence。
    - 同 node 后续 failed ticket 没有 replacement / supersession 语义，只是 retry 噪声或 provider malformed JSON。
  - 断言：
    - 下游 ticket 可创建。
    - `dependency_gate_refs == ["tkt_followup_completed_attempt"]`。

- [ ] 把 helper 的失效原因记录到 deterministic fallback error details。
  - 当 helper 拒绝 completed ticket 时，details 至少包含：
    - `completed_ticket_id`
    - `terminal_failed_ticket_id`
    - `node_id`
    - `reason_code`
  - reason code 使用稳定字符串，例如：
    - `completed_ticket_schema_mismatch`
    - `completed_ticket_missing_delivery_evidence`
    - `completed_ticket_superseded`
    - `completed_ticket_lineage_invalidated`

**建议测试命令：**

```powershell
cd D:\Projects\boardroom-os\backend
py -3 -m pytest tests/test_ceo_scheduler.py::test_backlog_followup_batch_uses_completed_attempt_when_latest_existing_ticket_failed -q
py -3 -m pytest tests/test_ceo_scheduler.py::test_backlog_followup_completed_attempt_superseded_by_failed_replacement_does_not_open_downstream -q
py -3 -m pytest tests/test_ceo_scheduler.py::test_backlog_followup_completed_attempt_still_satisfies_gate_when_failed_retry_is_unrelated -q
py -3 -m pytest tests/test_ceo_scheduler.py -k "backlog_followup and completed" -q
```

**验收标准：**

- 同节点 completed attempt 仍能解决 012 的“最新失败遮蔽已有完成产物”问题。
- 被 replacement / supersession / lineage invalidation 证明失效的 completed attempt 不能开放下游。
- dependency gate ref 永远指向被判定有效的 ticket，而不是单纯最新 completed row。

**不要在本轮做：**

- 不引入完整 graph version migration。
- 不改 closeout chain report。
- 不把所有 failed ticket 都视为 completed ticket 失效。

---

### Round 2：把 chain report 提升为 production completion contract

**目标：** 完成态 workflow 自身保证 chain report artifact 已物化；live harness 只做幂等补救和断言，不成为唯一生成点。

**优先级：** P1。P07 是 012 原 runner 最终失败点。

**主要文件：**

- Modify: `backend/app/core/workflow_auto_advance.py`
- Modify: `backend/app/core/workflow_autopilot.py`
- Test: `backend/tests/test_workflow_autopilot.py`
- Test: `backend/tests/test_scheduler_runner.py` only if scheduler completion path also marks workflow completed
- Keep: `backend/tests/live/_autopilot_live_harness.py`

**需要理解的现有代码：**

- `backend/app/core/workflow_autopilot.py`
  - `workflow_chain_report_artifact_ref()`
  - `workflow_chain_report_logical_path()`
  - `build_human_readable_workflow_report()`
  - `ensure_workflow_atomic_chain_report()`
- `backend/app/core/workflow_auto_advance.py`
  - `_maybe_write_autopilot_chain_report()`
  - `auto_advance_workflow_to_next_stop()`
- `backend/tests/live/_autopilot_live_harness.py`
  - `collect_common_outcome()`

**实施清单：**

- [ ] 审计 `workflow_auto_advance.py` 中所有 workflow closeout completion path。
  - 找到实际把 workflow projection 变成 `COMPLETED / closeout` 的位置。
  - 确认该路径是否已经调用 `_maybe_write_autopilot_chain_report()` 或 `ensure_workflow_atomic_chain_report()`。

- [ ] 在 production closeout path 增加 hard ensure。
  - workflow 标记 `COMPLETED / closeout` 前调用 `ensure_workflow_atomic_chain_report(repository, workflow_id=workflow_id)`。
  - 如果 artifact store 不可用或 report 无法生成，不应把 workflow 静默标成 full completed。
  - 若当前设计必须允许 closeout 完成但 chain report 延迟物化，则要写结构化 warning / incident，并让 final collection 明确显示 `completion_mode="completed_pending_chain_report"`。

- [ ] 保留 `collect_common_outcome()` 里的 ensure。
  - 它只作为 replay / harness 幂等补救。
  - 测试不能只证明 harness replay 可以补齐。

- [ ] 新增 failing test：`test_workflow_completion_materializes_chain_report_before_completed_projection`
  - 位置：`backend/tests/test_workflow_autopilot.py`
  - 场景：
    - seed autopilot workflow。
    - source delivery completed。
    - closeout ticket completed。
    - 调用 production auto-advance。
  - 断言：
    - workflow projection 为 `COMPLETED / closeout`。
    - `artifact_exists(repository, workflow_chain_report_artifact_ref(workflow_id))` 为 true。
    - artifact `ticket_id` 指向 closeout ticket。

- [ ] 新增 idempotency regression：`test_workflow_chain_report_ensure_is_idempotent_across_auto_advance_and_harness_replay`
  - 位置：`backend/tests/test_workflow_autopilot.py`
  - 场景：
    - production auto-advance 已生成 chain report。
    - 再次调用 `ensure_workflow_atomic_chain_report()`。
  - 断言：
    - artifact ref 不变。
    - artifact_index 中同一 `artifact_ref` 只有一条 active record。

**建议测试命令：**

```powershell
cd D:\Projects\boardroom-os\backend
py -3 -m pytest tests/test_workflow_autopilot.py -k "chain_report" -q
py -3 -m pytest tests/test_workflow_autopilot.py::test_workflow_completion_materializes_chain_report_before_completed_projection -q
py -3 -m pytest tests/test_workflow_autopilot.py::test_workflow_chain_report_ensure_is_idempotent_across_auto_advance_and_harness_replay -q
```

**验收标准：**

- production closeout 后立即存在 `art://workflow-chain/<workflow_id>/workflow-chain-report.json`。
- live harness replay 不再是 chain report 唯一生成点。
- 重复 ensure 不产生重复 artifact record。

**不要在本轮做：**

- 不改 chain report 内容结构，除非现有内容缺少 closeout / atomic task 基本字段。
- 不把失败隐藏成 runner success。
- 不改 source delivery payload 审计。

---

### Round 3：统一 source delivery compact / full payload contract

**目标：** source delivery 的 full payload 与 compact payload 都有正式审计规则，runtime、workspace hook、live harness 使用同一套证据解释口径。

**优先级：** P1/P2。P05、P06 都落在这个问题族。

**主要文件：**

- Modify: `backend/app/core/runtime.py`
- Modify: `backend/app/core/ticket_handlers.py`
- Modify: `backend/tests/live/_autopilot_live_harness.py`
- Test: `backend/tests/test_runtime_fallback_payload.py`
- Test: `backend/tests/test_project_workspace_hooks.py`
- Test: `backend/tests/test_live_library_management_runner.py`

**需要理解的现有代码：**

- `backend/app/core/runtime.py`
  - `_default_source_code_delivery_verification_runs()`
  - `_normalize_source_code_delivery_verification_path()`
  - `_normalize_source_code_delivery_payload()`
  - `_build_runtime_default_artifacts()`
  - `_build_source_code_delivery_submission_evidence()`
  - `_normalize_provider_payload_for_execution()`
- `backend/app/core/ticket_handlers.py`
  - `_validate_workspace_source_delivery_hooks()`
- `backend/tests/live/_autopilot_live_harness.py`
  - `_collect_source_delivery_payload_audit()`
  - `_collect_source_delivery_payload_audit_for_snapshot()`
  - `_assert_source_delivery_payload_quality()`

**实施清单：**

- [ ] 修改 `_default_source_code_delivery_verification_runs()`。
  - 当前默认 path 使用 `attempt-1`。
  - 改为使用 `execution_package.meta.attempt_no`。
  - artifact ref 如需区分 attempt，也应包含 attempt 或保持由后续 `_source_code_delivery_artifact_ref()` 生成唯一 ref。

- [ ] 修改 `_build_runtime_default_artifacts()`。
  - verification evidence fallback path 不能硬编码 `attempt-1`。
  - git evidence fallback path 不能硬编码 `attempt-1`。
  - 默认文件名分别保持：
    - `test-report.json`
    - `git-closeout.json`

- [ ] 强化 `_normalize_source_code_delivery_verification_path()`。
  - 如果 provider path 不含 `/attempt-`，改写到当前 attempt。
  - 如果 provider path 含 `/attempt-<n>/` 且 `<n>` 不等于当前 `execution_package.meta.attempt_no`，改写到当前 attempt 或 fail-closed。
  - 本轮建议选择“改写到当前 attempt”，因为这是 runtime normalization；同时在 audit assumptions 中记录 normalization。

- [ ] 抽出可复用审计 helper。
  - 建议位置：`backend/tests/live/_autopilot_live_harness.py` 内部 helper，后续可迁移到 production audit module。
  - helper 名：`_source_delivery_verification_runs_from_terminal_payload()`
  - 输入：`ticket_id`, `payload`
  - 输出：标准化 verification run list
  - full 规则：
    - 顶层 `verification_runs` 是非空 list。
    - 每个 run 至少有 `command` 和 raw `stdout` 或 raw `stderr`。
  - compact 规则：
    - 顶层无 `verification_runs` 时，读取 `verification_evidence_refs`。
    - refs 必须指向 `written_artifacts[*].artifact_ref`。
    - 对应 `written_artifacts[*].content_json` 必须包含 raw output。

- [ ] 保持 failure snapshot best-effort。
  - `_collect_source_delivery_payload_audit_for_snapshot()` 捕获 audit error 并写入 `audit_error`。
  - `_collect_source_delivery_payload_audit()` 和 `collect_common_outcome()` 仍严格抛错。

- [ ] 新增 failing test：`test_source_code_delivery_default_evidence_paths_use_current_attempt`
  - 位置：`backend/tests/test_runtime_fallback_payload.py`
  - 场景：fake execution package `attempt_no = 4`，调用 `_build_runtime_success_payload()` 或 `_normalize_source_code_delivery_payload()`。
  - 断言：
    - verification path 为 `20-evidence/tests/<ticket_id>/attempt-4/test-report.json`。
    - git written artifact path 为 `20-evidence/git/<ticket_id>/attempt-4/git-closeout.json`，如果测试覆盖 default artifacts。

- [ ] 新增 failing test：`test_source_code_delivery_normalization_rewrites_wrong_attempt_path_to_current_attempt`
  - 位置：`backend/tests/test_runtime_fallback_payload.py`
  - 场景：provider payload path 为 `20-evidence/tests/tkt_x/attempt-1/report.json`，execution package attempt 为 4。
  - 断言：normalized path 为 `20-evidence/tests/tkt_x/attempt-4/report.json`。

- [ ] 新增 hook regression：`test_workspace_source_delivery_accepts_current_attempt_normalized_paths`
  - 位置：`backend/tests/test_project_workspace_hooks.py`
  - 场景：runtime normalized payload 进入 ticket-result-submit。
  - 断言：hook accepted；`verification_evidence_refs` 与 `payload.verification_runs[*].artifact_ref` 对齐。

- [ ] 新增 harness regression：`test_source_delivery_compact_payload_requires_evidence_ref_content_json_raw_output`
  - 位置：`backend/tests/test_live_library_management_runner.py`
  - 场景：
    - compact payload 有 `verification_evidence_refs`。
    - `written_artifacts` 中对应 artifact 没有 `content_json.stdout/stderr`。
  - 断言：`_assert_source_delivery_payload_quality()` 抛出 raw output 缺失错误。

**建议测试命令：**

```powershell
cd D:\Projects\boardroom-os\backend
py -3 -m pytest tests/test_runtime_fallback_payload.py -q
py -3 -m pytest tests/test_project_workspace_hooks.py -k "source_code_delivery or verification" -q
py -3 -m pytest tests/test_live_library_management_runner.py -k "source_delivery_payload" -q
```

**验收标准：**

- source delivery 默认证据 path 与当前 attempt 一致。
- provider 给错 attempt path 时 runtime normalization 产出当前 attempt path。
- compact/full payload 的 raw output 要求一致。
- failure snapshot 容错不影响 final collection 严格性。

**不要在本轮做：**

- 不放宽 workspace hook。
- 不接受没有 raw verification output 的 compact payload。
- 不把所有 source delivery audit helper 立即抽成 production module，除非已有 production 消费方需要。

---

### Round 4：收紧 closeout `final_artifact_refs` 白名单

**目标：** closeout 只能引用真实交付证据，不允许把 `10-project/ARCHITECTURE.md` 等普通项目文档当 final delivery evidence。

**优先级：** P2。P08 中 closeout artifact refs 不合规属于 contract 压力点。

**主要文件：**

- Modify: `backend/app/core/ticket_handlers.py`
- Modify: `backend/app/core/runtime.py`
- Test: `backend/tests/test_project_workspace_hooks.py`
- Test: `backend/tests/test_runtime_fallback_payload.py`

**需要理解的现有代码：**

- `backend/app/core/ticket_handlers.py`
  - `_closeout_known_final_artifact_refs()`
  - `_validate_closeout_delivery_hooks()`
- `backend/app/core/runtime.py`
  - `_build_runtime_success_payload()` closeout branch
  - `_build_runtime_default_artifacts()`

**实施清单：**

- [ ] 新增 helper：`_is_delivery_evidence_artifact_ref()`
  - 位置：`backend/app/core/ticket_handlers.py`
  - 允许的 artifact ref 来源：
    - source delivery `payload.source_file_refs`
    - source delivery `payload.verification_evidence_refs`
    - maker-checker verdict `payload.artifact_refs`
    - delivery check report `payload.artifact_refs`
    - closeout package 自身 artifact ref
  - 不允许的来源：
    - 普通 `10-project/docs/*`
    - `10-project/ARCHITECTURE.md`
    - project notes、README、非 ticket terminal payload 的裸文档 ref

- [ ] 修改 `_closeout_known_final_artifact_refs()`。
  - 当前从 `created_spec.input_artifact_refs`、parent terminal payload、source-code-delivery process asset terminal payload 里收集 known refs。
  - 改为先收集候选，再按 `_is_delivery_evidence_artifact_ref()` 或 terminal payload 上下文过滤。
  - source delivery 的 `artifact_refs` 和 `verification_evidence_refs` 可进入。
  - 普通 input artifact refs 不因“被 closeout ticket 读取过”而自动成为 final evidence。

- [ ] 修改 runtime closeout fallback。
  - `_build_runtime_success_payload()` closeout branch 不能直接把 `execution_package.execution.input_artifact_refs` 全量作为 `final_artifact_refs`。
  - 应优先使用当前 delivery chain 中的 source/evidence refs。
  - 如果没有可用 delivery evidence，生成的 payload 应让 validator fail-closed，而不是塞普通文档 ref。

- [ ] 新增 failing test：`test_closeout_ticket_rejects_project_document_as_final_artifact_ref`
  - 位置：`backend/tests/test_project_workspace_hooks.py`
  - 场景：closeout created spec `input_artifact_refs` 包含 `art://workspace/.../10-project/ARCHITECTURE.md` 或等价普通文档 ref。
  - payload `final_artifact_refs` 只包含该普通文档 ref。
  - 断言：ticket-result-submit 被拒绝，错误包含 `known delivery evidence` 或 `final_artifact_refs`。

- [ ] 新增 passing test：`test_closeout_ticket_accepts_source_delivery_and_verification_evidence_refs`
  - 位置：`backend/tests/test_project_workspace_hooks.py`
  - 场景：上游 source delivery completed，terminal payload 有 source ref 与 verification ref。
  - closeout `final_artifact_refs` 引用这些 refs。
  - 断言：ticket-result-submit accepted。

- [ ] 新增 runtime regression：`test_delivery_closeout_runtime_payload_filters_non_delivery_input_artifact_refs`
  - 位置：`backend/tests/test_runtime_fallback_payload.py`
  - 场景：execution package closeout input refs 同时包含普通 docs ref 与 source/evidence ref。
  - 断言：runtime fallback payload 的 `final_artifact_refs` 只包含 source/evidence ref。

**建议测试命令：**

```powershell
cd D:\Projects\boardroom-os\backend
py -3 -m pytest tests/test_project_workspace_hooks.py -k "closeout or final_artifact_refs" -q
py -3 -m pytest tests/test_runtime_fallback_payload.py -k "closeout" -q
```

**验收标准：**

- 非 delivery evidence ref 出现在 `payload.final_artifact_refs` 时 closeout 被拒绝。
- source delivery 和 verification evidence refs 可以通过。
- runtime fallback 不再把普通项目文档塞进 final evidence。

**不要在本轮做：**

- 不把所有文档 ref 禁掉；只禁止它们伪装成 final delivery evidence。
- 不改 output schema 字段名。
- 不靠 provider prompt 提醒替代 validator。

---

### Round 5：provider failure 与恢复审计收口

**目标：** provider bad JSON、invalid content、schema drift 被结构化记录和汇总；最终完成可以允许 recovered failures，但不能让问题从审计面消失。

**优先级：** P2。P08 当前仍主要靠 retry 覆盖。

**主要文件：**

- Modify: `backend/app/core/runtime.py`
- Modify: `backend/tests/live/_autopilot_live_harness.py`
- Test: `backend/tests/test_live_library_management_runner.py`
- Test: `backend/tests/test_runtime_fallback_payload.py` if provider failure detail formatting changes

**需要理解的现有代码：**

- `backend/app/core/runtime.py`
  - `PROVIDER_RETRYABLE_FAILURE_KINDS`
  - `_normalize_provider_failure_detail()`
  - `_record_provider_attempt_finished()` or provider attempt event call sites
  - provider retry loop in runtime execution path
- `backend/tests/live/_autopilot_live_harness.py`
  - `build_runtime_ticket_audit()`
  - `_collect_source_delivery_payload_audit()`
  - `write_audit_summary()`

**实施清单：**

- [ ] 确认 provider malformed JSON / no JSON / schema validation failed 都有稳定 failure kind。
  - 必须覆盖：
    - `PROVIDER_MALFORMED_JSON`
    - `NO_JSON_OBJECT`
    - `SCHEMA_VALIDATION_FAILED`
    - provider bad response / invalid content 对应现有 failure kind

- [ ] 强化 provider failure detail。
  - `_normalize_provider_failure_detail()` 输出中至少包含：
    - `provider_id`
    - `preferred_provider_id`
    - `actual_provider_id`
    - `preferred_model`
    - `actual_model`
    - `attempt_count`
    - `fallback_applied`
    - `failure_kind`
    - `fingerprint` 或可稳定派生 fingerprint 的字段

- [ ] 在 live audit summary 中增加 `Recovered Failure Audit` 段。
  - 列出最终 workflow 中 historical failed tickets。
  - 按 failure family 分类：
    - provider JSON / bad response
    - workspace hook validation
    - closeout contract violation
    - runtime schema validation
  - 每项至少显示：
    - ticket id
    - node id
    - failure kind
    - 是否有后续 completed replacement / retry

- [ ] 对同 fingerprint 超阈值的 provider failure 给出显式审计。
  - 如果 runtime 已有 circuit breaker / provider pause，则 audit summary 引用相关事件。
  - 如果没有触发 circuit，本轮不强行新增 circuit breaker，只在 audit 中显示 retry count 和 residual risk。

- [ ] 新增 failing test：`test_write_audit_summary_groups_recovered_provider_failures`
  - 位置：`backend/tests/test_live_library_management_runner.py`
  - 场景：snapshot 中 tickets 有 failed provider malformed JSON，后续同 node completed。
  - 断言：audit summary 包含 `Recovered Failure Audit`、failure kind、ticket id、recovered by completed ticket。

- [ ] 新增 regression：`test_failed_retry_history_distinguishes_provider_and_hook_failures`
  - 位置：`backend/tests/test_live_library_management_runner.py`
  - 场景：一个 provider failure，一个 workspace hook validation failure，一个 completed retry。
  - 断言：summary 按 failure family 分组，不只输出总数。

**建议测试命令：**

```powershell
cd D:\Projects\boardroom-os\backend
py -3 -m pytest tests/test_live_library_management_runner.py -k "failed_retry or recovered or audit_summary" -q
py -3 -m pytest tests/test_runtime_fallback_payload.py -q
```

**验收标准：**

- 012 类“最终 completed 但历史 failed=6”会在 audit summary 中列出失败族和恢复结果。
- recovered failure 不阻断最终成功，但不能从报告中消失。
- provider retry / fallback 相关 failure detail 可追溯到 provider、model、attempt 和 fingerprint。

**不要在本轮做：**

- 不把 provider 不稳定归咎为业务产物失败。
- 不因历史 failed ticket 直接否定最终 recovered workflow。
- 不新增复杂 provider 策略引擎。

---

### Round 6：处理临时 preview harness 的去留

**目标：** 明确 `.tmp/library_preview_server.py` 不是产品修复，避免后续把临时查看工具误认为架构能力。

**优先级：** P3。P09 是临时验证工具问题，不是 production artifact 问题。

**主要文件：**

- Inspect: `.tmp/library_preview_server.py`
- Optional Modify: `.gitignore` only if `.tmp/` 当前未被忽略且会误入提交
- Optional Docs: `doc/tests/intergration-test-012-20260426.md` only if需要补充审计说明

**实施清单：**

- [ ] 检查 `.tmp/library_preview_server.py` 是否仍存在。
  - 命令：

```powershell
cd D:\Projects\boardroom-os
Test-Path .tmp\library_preview_server.py
```

- [ ] 检查 `.tmp/` 是否被 git ignore。
  - 命令：

```powershell
cd D:\Projects\boardroom-os
git status --short .tmp
git check-ignore -v .tmp/library_preview_server.py
```

- [ ] 若 `.tmp/library_preview_server.py` 未被跟踪且 `.tmp/` 已被 ignore，保持现状，不做代码修改。

- [ ] 若 `.tmp/library_preview_server.py` 出现在 `git status --short` 中，删除或忽略前先确认它不是用户需要保留的手工工具。
  - 本轮默认不删除文件，除非用户明确要求清理。
  - 如需正式产品化 preview harness，应另开设计，不并入 012 remediation。

- [ ] 在最终实施回复中明确：
  - P09 不属于业务产物缺陷。
  - preview API server 是本地人工查看补丁。
  - 后续 live harness 不应依赖 `.tmp` 预览脚本作为成功证据。

**建议验证命令：**

```powershell
cd D:\Projects\boardroom-os
git status --short .tmp
git check-ignore -v .tmp/library_preview_server.py
```

**验收标准：**

- `.tmp/library_preview_server.py` 不进入整改代码提交。
- 012 remediation 中不把临时预览服务当 production architecture fix。
- 如果后续要做正式 artifact preview harness，必须另列计划和验收。

**不要在本轮做：**

- 不把 terminal / web preview 问题混入 production delivery contract。
- 不在未确认的情况下删除用户可能还要查看的 `.tmp` 文件。
- 不把 preview server 接入 runtime。

---

## 3. 推荐每轮开工前命令

每轮都先跑：

```powershell
cd D:\Projects\boardroom-os
git status --short
git log --oneline -n 12
```

如果工作区不干净：

- [ ] 不要 revert 用户改动。
- [ ] 只读理解相关 diff。
- [ ] 若相关文件已有未提交修改，先判断是否和本轮目标冲突。
- [ ] 若冲突影响本轮判断，先在最终回复中报告冲突文件和建议顺序。

每轮进入 backend 后再跑定向测试，不默认跑全仓大测试：

```powershell
cd D:\Projects\boardroom-os\backend
py -3 -m pytest <本轮测试> -q
```

本机若默认 pytest temp root 触发 `PermissionError`，使用仓库内 `.tmp`：

```powershell
py -3 -m pytest --basetemp .tmp\pytest-012-roundN <本轮测试> -q
```

## 4. 最终整体验收

六轮都完成后，至少要有这些证据：

- [ ] Round 1 regression：completed ticket 兜底只有在 lineage / supersession / evidence 有效时开放下游。
- [ ] Round 2 regression：production closeout 完成前或完成同时物化 workflow chain report。
- [ ] Round 3 regression：source delivery compact/full payload 都要求 raw verification output，且 attempt path 与当前 attempt 一致。
- [ ] Round 4 regression：closeout `final_artifact_refs` 只能引用真实 delivery evidence。
- [ ] Round 5 regression：历史 provider / hook / schema failures 在 audit summary 中分组呈现，并显示 recovery 结果。
- [ ] Round 6 confirmation：`.tmp/library_preview_server.py` 未被误纳入产品架构或整改提交。

可选 live clean run：

```powershell
cd D:\Projects\boardroom-os\backend
py -3 -m tests.live.run_configured --config data/live-tests/library_management_autopilot_live_012.toml --clean --max-ticks 180 --timeout-sec 7200
```

live clean run 成功时仍要人工核对：

- [ ] 原始 runner 自然退出成功，而不是只靠 completed DB replay。
- [ ] workflow 为 `COMPLETED / closeout`。
- [ ] chain report artifact 在 completion path 中已经存在。
- [ ] compiled ticket ids 与 ticket context archives 一致。
- [ ] source delivery compact/full payload 都能追溯 raw verification output。
- [ ] failed ticket history 被 audit summary 捕获，不从成功结论中消失。
- [ ] closeout `final_artifact_refs` 不包含普通项目文档 ref。

## 5. 常见误判

- [ ] 不要把 `collect_common_outcome()` replay 成功改写成原始 runner 成功。
- [ ] 不要把同 node completed ticket 永远视为有效依赖；必须看 lineage、replacement、supersession、evidence。
- [ ] 不要只在 live harness ensure chain report，却让 production completion contract 缺口继续存在。
- [ ] 不要把 compact source delivery payload 当成可以省略 raw verification output。
- [ ] 不要把 provider bad JSON / invalid content 从 audit 中删掉。
- [ ] 不要把 closeout 读取过的普通项目文档当 final delivery evidence。
- [ ] 不要把 `.tmp/library_preview_server.py` 当业务产物修复。

## 6. 建议提交拆分

如果后续会话需要提交，建议每轮一个或多个小提交：

- [ ] `fix(ceo): 收紧完成票据依赖兜底`
- [ ] `fix(workflow): 完成前物化chain report`
- [ ] `fix(runtime): 统一交付证据attempt版本`
- [ ] `fix(closeout): 限定最终交付证据引用`
- [ ] `test(live): 汇总provider恢复失败审计`
- [ ] `docs(test): 标注012临时预览工具边界`

不要把六轮混成一个提交。
