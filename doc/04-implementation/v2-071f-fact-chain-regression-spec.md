# V2-071F V2-070 fact-chain end-to-end regression（事实链端到端回归）同行评审 spec

## 1. 背景与现实场景

V2-071F 处理的是 Phase 7（收尾能力）重新上锁前的“整链防伪复核”场景：V2-071A ~ V2-071E 已分别收紧 ReplayBundle（重放包）、ProcessAuditBundle（流程审计包）、GitVersionAuditBundle（Git 版本审计包）和 CloseoutPackage（收尾包）的事实边界，但还需要证明这些边界串成一条链后仍然 fail closed（封闭失败），且好交付可以稳定 closeout（收尾）。

通俗地说：ReplayBundle 像录像，ProcessAuditBundle 像审计报告，GitVersionAuditBundle 像 Git 封条，CloseoutPackage 像最终结案袋，CLOSEOUT_COMMITTED event（收尾提交治理事件）像正式签字。V2-071F 要做的是把这些材料按真实顺序串起来，确认伪造录像、串包审计、缺 Git 封条、payload hash（载荷哈希）篡改、graph_version（图版本）越界、fallback（兜底值）污染等坏交付都不能通过；同时确认一份完整、真实、有证据的交付能得到 CloseoutReducer（收尾归约器）的 terminal succeeded（终态成功）投影，并通过 CloseoutClosure（收尾闭包）校验。

本工作包闭合 V2-070 batch review（批量评审）提出的 P0/P1/P2 audit report regressions（审计报告回归缺口），并用一个共享端到端 fact-chain fixture（事实链夹具）降低测试漂移风险。

V2-071F 的测试定位是 integration-level confirmatory regression（集成层确认性回归），不是替代 V2-071A ~ V2-071E 已有 isolated unit tests（隔离单元测试）。已有测试证明单个边界各自 fail closed（封闭失败）；本轮证明这些边界在同一条 fact-chain（事实链）中组合后仍然 fail closed，且完整好交付能端到端 closeout（收尾）。

Pre-flight（一致性预检）：`backlog.md` 当前未完成工作包为 V2-071F；V2-071A ~ V2-071E 依赖已 DONE；本文件、`tests/closeout/test_v2_070_fact_chain_end_to_end.py`、`tests/negative/test_v2_070_audit_report_p0_regressions.py`、`tests/negative/test_v2_070_audit_report_p1_regressions.py`、`tests/negative/test_v2_070_audit_report_p2_regressions.py` 创建前不存在；Phase 7.5 进度为 5/6，V2-071F、18 项缺口闭合和 Phase 7.5 总闭合 checkbox（复选框）仍未勾选；未发现阻断 V2-071F 的 drift（状态漂移）。

## 2. 范围与边界

### 2.1 In Scope

- 新建本 spec，并在实现完成时同步 `doc/04-implementation/INDEX.md`。
- 新增 `tests/closeout/test_v2_070_fact_chain_end_to_end.py`：
  - 定义共享 end-to-end fact-chain fixture（端到端事实链夹具）。
  - 覆盖 happy path（正向路径）：EventLog（事件日志）到 CloseoutReducer（收尾归约器）和 CloseoutClosure（收尾闭包校验）的完整链路。
  - 覆盖多次构造稳定性：readiness summaries（就绪摘要）和关键 hash（哈希）在相同输入下字节稳定。
- 新增 P0/P1/P2 negative tests（反例测试）：
  - `tests/negative/test_v2_070_audit_report_p0_regressions.py`
  - `tests/negative/test_v2_070_audit_report_p1_regressions.py`
  - `tests/negative/test_v2_070_audit_report_p2_regressions.py`
- 复用 V2-071A ~ V2-071E 已有 builder/readiness/reducer/validator（构建器/就绪校验/归约器/校验器），不为测试绕过生产契约。
- 如果 mandatory regression（强制回归用例）暴露现有生产校验缺口，只做与该 fail-closed（封闭失败）断言直接相关的最小修复。
- 实现完成后按 backlog（任务积压文档）工作包完成协议更新：backlog 状态、acceptance criteria（验收标准）、月度项目日志、必要时 decisions（决策记录）、INDEX（索引）。

### 2.2 Out of Scope

- 不读取、迁移、复制或修补 legacy runtime（旧运行时）与旧 backend（后端）路径。
- 不新增 CEO（首席执行官角色）、Architect（架构师角色）、Checker（检查者角色）或 Closeout（收尾）决策主路径。
- 不把 generated project workspace（生成项目工作区）的 `00-boardroom` / `10-project` / `20-evidence` / `30-audit` 目录结构引入框架仓库。
- 不新增 optional validation（可选校验）、compatibility shim（兼容垫片）或 fallback mode（兜底模式）。
- 不把 provider attempt count（模型调用尝试次数）、source inventory hash（源码清单哈希）、evidence verifier verdict（证据验证器结论）或 closeout gate result（收尾门禁结果）mock（模拟）掉。

### 2.4 Confirmatory regression（确认性回归）边界

V2-071F 的 P0/P1/P2 tests（回归测试）必须复用已有单元级 hardening（加固）结论，但不能只复制既有断言。每个用例都应说明它在共享 fact-chain fixture（事实链夹具）中的集成价值：

- 单元级 fail-closed（封闭失败）测试证明某个 builder/readiness/adapter（构建器/就绪校验/适配器）单独拒绝坏输入。
- V2-071F 集成级 regression（回归）测试证明同一坏输入在端到端链条中不会被相邻环节重新包装、吞掉或绕过。
- 若某项回归已经由 V2-071A ~ V2-071E 单元测试完全覆盖，V2-071F 只保留最小 confirmatory assertion（确认性断言），并在表格中标明已有测试文件和本轮增量价值。

## 3. 目标事实链契约

V2-071F 固定并测试以下事实链顺序：

```text
EventLog（事件日志）
   ↓
ReplayBundle（重放包：从 events 重新投影）
   ↓
ReplayBundleReadiness（重放包就绪摘要：用 resolver 重算 payload sha256）
   ↓
ProcessAuditBundle（流程审计包：复用 replay_bundle.events）
   ↓
ProcessAuditReadiness（流程审计就绪摘要）
   ↓
GitVersionAuditBundle（Git 版本审计包）
   ↓
GitAuditReadiness（Git 审计就绪摘要）
   ↓
CloseoutGateResult（收尾门禁结果）
   ↓
CloseoutPackage（收尾包：绑定同一 proof boundary）
   ↓
CLOSEOUT_COMMITTED event（收尾提交治理事件）
   ↓
CloseoutReducer（收尾归约器：terminal_status = SUCCEEDED）
   ↓
CloseoutClosure helpers（收尾闭包辅助校验）
```

关键约束：

1. EventLog（事件日志）是事件事实的唯一权威源。
2. ReplayBundle（重放包）不得接受外部 `ProjectionReplaySummary`（投影重放摘要）。
3. ProcessAuditBundle（流程审计包）必须复用 `replay_bundle.events`，不得另收一份 events。
4. ProcessAuditBundle 可以在没有 `CLOSEOUT_COMMITTED` 的情况下构造；`CLOSEOUT_COMMITTED` 只能在 CloseoutPackage（收尾包）完成后作为 governance event（治理事件）追加。
5. GitVersionAuditBundle（Git 版本审计包）必须绑定显式 `base_commit_sha`（基准提交哈希）、`worktree_ref`（工作树引用）和 SourceInventory hash（源码清单哈希）。
6. CloseoutPackage.graph_version（收尾包图版本）必须等于 ReplayBundle proof boundary（重放证明边界），不得小于或大于。
7. CloseoutReducer（收尾归约器）只能消费 `CLOSEOUT_COMMITTED` 事件和已解析 CloseoutPackage（收尾包）完成终态投影。
8. CloseoutClosure（收尾闭包）以 helper functions（辅助函数）表达：`assert_checked_refs_cover(...)`、`assert_source_inventory_evidence_refs_resolve(...)`、`assert_workspace_evidence_bundle_matches_runs(...)`。

## 4. 共享 fact-chain fixture（事实链夹具）设计

### 4.1 夹具输出对象

测试局部定义一个不可变 fixture result（夹具结果）对象，例如 `V2070FactChainFixture`（V2-070 事实链夹具），包含：

- `project_ref`（项目引用）
- `run_id`（运行标识）
- `generated_at`（生成时间）
- `events_before_closeout`（收尾前事件）
- `closeout_committed_event`（收尾提交事件）
- `events_after_closeout`（收尾后事件）
- `source_inventory`（源码清单）
- `package_contract`（包合同）
- `acceptance_contract`（验收合同）
- `workspace_evidence_bundle`（工作区证据包）
- `verification_runs`（验证运行记录）
- `verified_evidence`（已验证证据）
- `final_evidence_table`（最终证据表）
- `checker_verdict`（检查者结论）
- `replay_bundle`（重放包）
- `replay_readiness`（重放就绪摘要）
- `process_audit_bundle`（流程审计包）
- `process_audit_readiness`（流程审计就绪摘要）
- `git_version_audit_bundle`（Git 版本审计包）
- `git_audit_readiness`（Git 审计就绪摘要）
- `closeout_gate_result`（收尾门禁结果）
- `closeout_package`（收尾包）
- `closeout_projection`（收尾投影）

该对象只放在测试代码中，不进入生产模块。

### 4.2 夹具构造流程

共享 fixture（夹具）按以下顺序构造：

1. 使用固定 `project_ref`、`run_id` 和 `generated_at`，避免时间漂移影响 hash（哈希）。
2. 构造包含 work product（工作产物）、provider attempt（模型调用尝试记录）、command run（命令运行）、verification（验证）和 evidence（证据）事实的 EventRecord（事件记录）序列，但不包含 `CLOSEOUT_COMMITTED`。
3. 调用 ReplayBundleBuilderInput（重放包构建输入）和 `build_replay_bundle(...)`，由 events 重新投影 summary（摘要）。
4. 调用 `replay_bundle_readiness(...)`，传入显式 ReplayPayloadResolver（重放载荷解析器），用真实 payload 内容重算 sha256。
5. 构造 ProcessAuditBuilderInput（流程审计构建输入），只传入 ReplayBundle（重放包），不传入外部 events。
6. 构造 GitVersionAuditBundle（Git 版本审计包）和 GitAuditReadiness（Git 审计就绪摘要），显式提供 Git 边界字段。
7. 构造 CloseoutGateResult（收尾门禁结果），输入 readiness summaries（就绪摘要）和 evidence verdicts（证据结论）。
8. 构造 CloseoutPackage（收尾包），`graph_version` 使用 ReplayBundle proof boundary（重放证明边界）。
9. 构造并追加 `CLOSEOUT_COMMITTED` governance event（收尾提交治理事件）。
10. 调用 CloseoutReducer（收尾归约器）得到 `terminal_status = SUCCEEDED`。
11. 调用 CloseoutClosure helpers（收尾闭包辅助校验）确认 checked refs（已检查引用）、SourceInventory evidence refs（源码清单证据引用）和 WorkspaceEvidenceBundle runs（工作区证据包运行记录）闭合。

### 4.3 Fixture construction complexity note（夹具构造复杂度说明）

共享 fixture（夹具）允许使用 fixed/fake-but-valid values（固定的、假的但符合契约的值），但不允许 mock（模拟）掉事实链核心校验。

必须经过真实 builder/readiness/reducer/validator（构建器/就绪校验/归约器/校验器）的对象：

- ReplayBundle（重放包）与 ReplayBundleReadiness（重放包就绪摘要）
- ProcessAuditBundle（流程审计包）与 ProcessAuditReadiness（流程审计就绪摘要）
- GitVersionAuditBundle（Git 版本审计包）与 GitAuditReadiness（Git 审计就绪摘要）
- CloseoutGateResult（收尾门禁结果）
- CloseoutPackage（收尾包）
- CLOSEOUT_COMMITTED event（收尾提交治理事件）
- CloseoutReducer projection（收尾归约器投影）
- CloseoutClosure helpers（收尾闭包辅助校验）

可以使用确定性测试值构造、但必须保持 schema（结构）和 binding（绑定）有效的对象：

- VerificationRun（验证运行记录）：可使用固定 `exit_code=0`、stdout/stderr refs（标准输出/标准错误引用）和 command evidence refs（命令证据引用）。
- VerifiedEvidence（已验证证据）：可使用固定 verifier verdict（验证器结论），但必须绑定真实 evidence refs（证据引用）和 producer attempt refs（生产者尝试引用）。
- WorkspaceEvidenceBundle（工作区证据包）：可使用测试内固定 artifacts（产物）和 refs（引用），但必须与 VerificationRun（验证运行记录）和 VerifiedEvidence（已验证证据）互相闭合。
- SourceInventory（源码清单）：可使用测试内固定 entries（条目），但必须包含 sha256、producer_attempt_ref（生产者尝试引用）、acceptance_refs（验收引用）、evidence_refs（证据引用）和 consumer_ticket_refs（消费者任务引用）。
- PackageContract（包合同）、AcceptanceContract（验收合同）、CheckerVerdict（检查者结论）可使用现有测试 helper（辅助函数）或最小有效对象，但不得删除必填 acceptance map（验收映射）或 verdict evidence（结论证据）。

允许复用现有 tests（测试）中的 helper（辅助函数）作为构造参考，例如 closeout package、process audit、git audit 和 closure hardening tests（加固测试）里的 `_build_*` / `_fixture` 模式；若 helper 只存在于测试文件内部，V2-071F 可在本轮目标测试文件中复制最小必要构造逻辑，不把测试 helper 提升到生产模块。

### 4.4 稳定性策略

- 所有输入使用固定顺序和固定时间。
- 需要证明 canonical sort（规范排序）的对象由 P2 tests（P2 回归测试）显式乱序输入。
- 同一 fixture（夹具）重复构造至少两次，比较关键 refs（引用）、readiness summaries（就绪摘要）和 hash（哈希）完全一致。
- 不使用文件系统临时目录作为事实源；如需 payload 内容，使用显式 resolver（解析器）映射。

## 5. Regression mapping（回归映射）

V2-070 batch review（批量评审）在 backlog（任务积压文档）中以 15 个 grouped findings（分组发现）列出；V2-071F 将其中含多字段边界的条目拆成 18 个 executable checks（可执行检查）。

| ID | 可执行检查 | 已有测试文件 | V2-071F 增量价值 | V2-071F 测试函数 |
|---|---|---|---|---|
| P0-1 | ProcessAuditBundle（流程审计包）可在无 `CLOSEOUT_COMMITTED` 时构造；CloseoutPackage（收尾包）完成后追加 `CLOSEOUT_COMMITTED`，CloseoutReducer（收尾归约器）投影 succeeded | `test_closeout_reducer.py`、`test_process_audit_fact_chain.py` | 从 EventLog（事件日志）到 CloseoutReducer（收尾归约器）的整链衔接，不重复单测 reducer（归约器） | `test_p0_1_fact_chain_commits_closeout_only_after_process_audit_and_package` |
| P0-2 | 外部伪造 `ProjectionReplaySummary`（投影重放摘要）必须被拒绝 | `test_replay_bundle_external_summary_rejected.py` | 在共享 fixture（夹具）入口确认外部摘要不能进入整链 | `test_p0_2_external_projection_summary_cannot_enter_fact_chain` |
| P0-3 | ProcessAudit events（流程审计事件）与 ReplayBundle.events（重放包事件）中间事件不一致必须失败 | `test_process_audit_timeline_matches_replay_bundle_events_exactly` in `test_process_audit_fact_chain.py` | 在共享 fixture（夹具）上下文中篡改中间事件，确认集成链拒绝事件漂移 | `test_p0_3_tampered_process_audit_timeline_is_rejected_in_shared_fixture_context` |
| P0-4a | GitAuditAdapter（Git 审计适配器）缺 `base_commit_sha`（基准提交哈希）必须失败 | `test_git_audit_fallback_rejected.py` | 确认 Git 边界缺失不会被 CloseoutPackage（收尾包）或 readiness（就绪摘要）吞掉 | `test_p0_4a_missing_base_commit_sha_stops_git_boundary_before_closeout` |
| P0-4b | GitAuditAdapter（Git 审计适配器）缺 `worktree_ref`（工作树引用）必须失败 | `test_git_audit_fallback_rejected.py` | 确认 Git 边界缺失不会被整链兜底为 unknown（未知） | `test_p0_4b_missing_worktree_ref_stops_git_boundary_before_closeout` |
| P0-5 | CloseoutPackage.graph_version（收尾包图版本）大于 ReplayBundle.last_graph_version（重放包最后图版本）必须失败 | `test_closeout_package_graph_version_overflow_rejected.py` | 在已构造完整 replay/process/git/gate（重放/流程/Git/门禁）上下文中确认 proof boundary（证明边界）不可越界 | `test_p0_5_closeout_package_cannot_extend_beyond_replay_boundary_in_full_context` |
| P1-1 | ReplayPayloadManifest（重放载荷清单）sha256 篡改必须失败 | `test_replay_payload_manifest_tampering_rejected.py` | 确认 payload hash（载荷哈希）篡改会阻断后续 closeout（收尾）链路 | `test_p1_1_payload_sha256_tampering_blocks_fact_chain_readiness` |
| P1-2a | ProcessAudit（流程审计）缺 `owner_seat_ref` 字段不得输出 `unknown`（未知占位） | `test_process_audit_construction_loop_rejected.py` | 从 `ProcessAuditBuilderInput`（流程审计构造输入）缺字段直接失败，确认占位 artifact（产物）没有生成机会 | `test_p1_2a_missing_owner_seat_ref_fails_before_unknown_placeholder_can_be_emitted` |
| P1-2b | ProcessAudit（流程审计）缺 `ticket_ref` 字段不得输出 generic `ticket`（通用任务占位） | `test_process_audit_construction_loop_rejected.py` | 从 `ProcessAuditBuilderInput`（流程审计构造输入）缺字段直接失败，确认 generic ticket（通用任务）不会污染 artifact lineage（产物来源链） | `test_p1_2b_missing_ticket_ref_fails_before_generic_ticket_placeholder_can_be_emitted` |
| P1-3 | producer ticket（生产者任务）与 consumer ticket（消费者任务）不同时 artifact-lineage.json（产物来源文件）必须分离 | `test_process_audit_fact_chain.py` | 在整链 fixture（夹具）中确认 lineage separation（来源链分离）被 CloseoutClosure（收尾闭包）继续使用 | `test_p1_3_artifact_lineage_keeps_producer_and_consumer_tickets_separate_in_fact_chain` |
| P1-4 | expected fallback（预期兜底）为空但 actual fallback lineages（实际兜底来源链）非空必须失败 | `test_process_audit_construction_loop_rejected.py` | 确认额外 fallback lineage（兜底来源链）不会被 process audit/readiness（流程审计/就绪摘要）吸收 | `test_p1_4_unexpected_fallback_lineage_is_rejected_in_fact_chain_bundle` |
| P1-5a | 跨 project（项目）的 `fact_set_id`（事实集标识）串包必须失败 | `test_namespaced_refs_fail_closed.py` | 确认跨 project（项目）事实集不能绑定进同一 Git/process/closeout 链 | `test_p1_5a_cross_project_fact_set_id_cannot_bind_into_fact_chain` |
| P1-5b | 跨 run（运行）的 `artifact_ref` / `content_ref`（产物引用/内容引用）串包必须失败 | `test_namespaced_refs_fail_closed.py` | 确认跨 run（运行）产物/内容引用不能进入同一 ProcessAuditBundle（流程审计包） | `test_p1_5b_cross_run_process_audit_artifact_ref_is_rejected_in_fact_chain` |
| P2-1 | GitVersionAudit（Git 版本审计）`verification_runs`（验证运行记录）乱序 hash 稳定 | `test_git_audit_hardening.py` | 确认 Git readiness（Git 就绪摘要）在整链输入顺序变化时仍稳定 | `test_p2_1_git_version_audit_verification_run_order_is_stable_for_fact_chain_readiness` |
| P2-2 | Replay manifest entries（重放清单条目）乱序 hash 稳定 | `test_replay_bundle_rereplay.py` | 确认 ReplayBundle（重放包）稳定性可被后续 audit/closeout（审计/收尾）复用 | `test_p2_2_replay_manifest_entry_order_is_stable_before_audit_and_closeout` |
| P2-3 | ProcessAudit `checked_refs`（流程审计已检查引用）乱序 hash 稳定 | `test_process_audit_fact_chain.py` | 确认 ProcessAudit readiness（流程审计就绪摘要）不因 checked_refs（已检查引用）顺序影响 closeout（收尾） | `test_p2_3_process_audit_checked_refs_order_is_stable_before_closeout` |
| P2-4 | 特殊字符文件名可通过 `git status --porcelain=v1 -z`（Git 状态零分隔输出）正确解析 | `test_git_audit_hardening.py` | 确认特殊文件名解析正确，且 dirty facts（脏 Git 事实）不能构造 GitVersionAuditBundle（Git 版本审计包）进入整链 | `test_p2_4_git_status_z_parses_special_filenames_before_git_readiness` |
| P2-5 | 含 `insertions` 字样的文件名不污染 `git diff --shortstat`（Git 差异短统计）解析 | `test_git_audit_hardening.py` | 确认 diff 统计解析正确，且 dirty facts（脏 Git 事实）不能构造 GitVersionAuditBundle（Git 版本审计包）进入整链 | `test_p2_5_git_diff_shortstat_ignores_filename_containing_insertions_before_git_readiness` |

## 6. 测试执行策略

实施阶段按 negative-tests-first（反例测试优先）执行：

1. 先写 P0/P1/P2 negative tests（反例测试），确认每个坏输入被现有或最小修复后的 fail-closed（封闭失败）边界拒绝。
2. 再写 happy path（正向路径）端到端测试，确认好输入可以完成 closeout（收尾）。
3. 最后运行相关历史 hardening tests（加固测试），确认 V2-071A ~ V2-071E 的边界未被 V2-071F fixture（夹具）削弱。

建议验证命令：

```bash
uv run pytest tests/negative/test_v2_070_audit_report_p0_regressions.py tests/negative/test_v2_070_audit_report_p1_regressions.py tests/negative/test_v2_070_audit_report_p2_regressions.py
uv run pytest tests/closeout/test_v2_070_fact_chain_end_to_end.py
uv run pytest tests/closeout/test_replay_bundle_rereplay.py tests/closeout/test_process_audit_fact_chain.py tests/closeout/test_git_audit_hardening.py tests/closeout/test_closeout_package_boundary.py tests/closeout/test_closeout_reducer.py tests/closeout/test_closeout_closure_hardening.py
```

若项目测试入口不是 `uv run pytest`，实施时以仓库现有测试约定为准，并在完成报告中真实记录命令和结果。实施前必须先核实测试入口：如果 `pip install -e .`、`python -m pytest` 或 `uv run pytest` 因缺少 packaging metadata（打包元数据）或 import path（导入路径）失败，先报告该验证环境缺口，不擅自重建 `pyproject.toml` / `setup.py` 或改变包管理结构。

## 7. 完成标准

V2-071F 只有在以下条件全部满足时才能标记 DONE：

- 本 spec 存在并已通过同行/专家评审要求。
- 四个目标测试文件存在，且 P0/P1/P2 regression mapping（回归映射）中的 18 个 executable checks（可执行检查）都有明确测试覆盖。
- End-to-end happy path（端到端正向路径）从 EventLog（事件日志）真实跑到 CloseoutReducer（收尾归约器）terminal succeeded（终态成功）。
- CloseoutClosure helpers（收尾闭包辅助校验）在 happy path（正向路径）中全部通过。
- 相同输入重复构造得到稳定 refs/readiness/hash（引用/就绪摘要/哈希）。
- 相关验证命令真实运行并通过。
- `doc/04-implementation/backlog.md` 更新 V2-071F 状态与 Phase 7.5 进度。
- `doc/04-implementation/acceptance-criteria.md` 勾选 V2-071F、18 项回归闭合、Phase 7.5 总闭合相关 checkbox（复选框）。
- `doc/05-project-log/2026-05.md` 记录本批实现与验证结果。
- `doc/04-implementation/INDEX.md` 登记本 spec。
- `doc/05-project-log/decisions.md` 仅在出现新方法、架构或范围决策时更新。

## 8. 风险与缓解

- 风险：共享 fixture（夹具）过大，导致单个测试文件难以维护。缓解：fixture 只表达事实链构造，P0/P1/P2 tests（回归测试）只在边界处做最小变体。
- 风险：为通过测试而弱化生产校验。缓解：所有坏输入必须经现有 builder/readiness/reducer/validator（构建器/就绪校验/归约器/校验器）失败，不新增宽松路径。
- 风险：P2 稳定性测试误把 fixture 顺序固定当成 canonical sort（规范排序）。缓解：P2 tests 必须显式输入乱序数据，并比较 canonical hash（规范哈希）。
- 风险：18 个 executable checks（可执行检查）与 backlog（任务积压文档）的 grouped findings（分组发现）数量表述不一致。缓解：本 spec 明确拆分规则：P0-4 拆为 base/worktree 两项，P1-2 拆为 unknown/generic ticket 两项，P1-5 拆为 fact_set 与 artifact/content namespace 两项。

## 9. 自审结论

- Placeholder scan（占位扫描）：未保留 TBD、TODO 或空白章节。
- Internal consistency（内部一致性）：事实链顺序与 V2-071A ~ V2-071E 一致；ProcessAuditBundle（流程审计包）允许无 `CLOSEOUT_COMMITTED`，CloseoutReducer（收尾归约器）只在追加治理事件后终态成功，两者不矛盾；V2-071F 明确是集成层确认性回归，不替代已有单元级 hardening tests（加固测试）。
- Scope check（范围检查）：本工作包聚焦 spec、端到端 regression tests（回归测试）和必要最小 fail-closed 修复，不引入新主路径或旧 runtime（旧运行时）迁移；fixture（夹具）允许 fixed/fake-but-valid values（固定的、假的但符合契约的值），但必须经过真实 builder/readiness/reducer/validator（构建器/就绪校验/归约器/校验器）。
- Ambiguity check（歧义检查）：18 个 executable checks（可执行检查）已从 grouped findings（分组发现）拆分到具体测试文件，并补充已有测试文件与 V2-071F 增量价值；P0-1/P0-3 已明确为共享 fixture（夹具）上下文的整链衔接与事件漂移测试；完成标准明确要求真实验证命令和文档更新。
