# V2 总验收标准

## 文档职责

本文件定义 Boardroom OS V2 自身的验收标准。它不是某个 generated project 的 acceptance contract。

本文件由两层组成：

1. **抽象原则层（AC-V2-XXX）**：principle-level 验收标准，对应架构主线。`backlog.md` 的工作包必须显式映射到这里的某条 AC。
2. **分批验收层（Phase 0 ~ Phase 8）**：每个 phase 完成时人类用以验收的 checkbox 清单、产出清单和"进入下一 Phase 前置"。这层是人类视角的 quality gate。

使用方式：

- 实施工作包时，先读相应 phase 的"分批验收"段，确认要勾选哪些 checkbox、要产出哪些文件。
- 工作包完成后按 `backlog.md` 的"工作包完成更新协议"勾选 checkbox 并更新日志。
- Phase 全部 checkbox 勾选 + 前置全部满足后，才可进入下一 Phase。

## AC-V2-FOUNDATION

### AC-V2-FOUNDATION-001: clean branch foundation

V2 必须能在干净分支中独立表达目标、架构、约束和路线，不依赖旧实现主链。

### AC-V2-FOUNDATION-002: legacy boundary

旧实现默认 abandoned by default。除 forensic lookup 外，AI 不应读取旧实现作为 V2 实施依据。

## AC-V2-CONTRACT

### AC-V2-CONTRACT-001: dynamic acceptance contract

Acceptance criteria 必须从当前用户需求、PRD 和治理产物动态派生。

### AC-V2-CONTRACT-002: package contract required

任何 implementation ticket 创建前，必须存在 package contract，定义 source surfaces、run/test commands、integration boundary 和 evidence obligations。

### AC-V2-CONTRACT-003: no static universal AC

禁止使用固定 AC 列表覆盖所有项目类型。

## AC-V2-GRAPH

### AC-V2-GRAPH-001: ticket graph as state source

Ticket graph 是流程状态源。runtime 不得直接推进 project completed。

### AC-V2-GRAPH-002: reducer-protected transitions

所有关键状态变更必须通过 reducer 或 validator。

## AC-V2-EXECUTION

### AC-V2-EXECUTION-001: execution package required

Worker 执行前必须收到结构化 execution package。

### AC-V2-EXECUTION-002: provider attempt required

Provider-required implementation ticket 必须有 provider attempt。attempt count 为 0 必须失败。

### AC-V2-EXECUTION-003: fallback cannot satisfy implementation evidence

Fallback 默认不能满足 source、integration、acceptance 或 closeout evidence。

## AC-V2-EVIDENCE

### AC-V2-EVIDENCE-001: command evidence from runner

Verification run 必须来自 command runner 的真实执行记录。

### AC-V2-EVIDENCE-002: source inventory proves implementation lineage

Source inventory 必须证明文件路径、hash、producer ticket、provider attempt、source surface、acceptance refs 和 evidence refs。

### AC-V2-EVIDENCE-003: evidence map complete

Final evidence table 必须覆盖 active acceptance contract 的所有 blocking criteria。

## AC-V2-CHECKER

### AC-V2-CHECKER-001: checker blocks evidence gaps

Checker 必须对缺失 source、test、integration、acceptance 或 closeout evidence 发起 rework。

### AC-V2-CHECKER-002: notes do not clear blockers

Checker notes 不能覆盖 blocker。

## AC-V2-PACKAGE

### AC-V2-PACKAGE-001: generated project package is final output

最终输出必须是 generated project package，而不是离散 source artifact。

### AC-V2-PACKAGE-002: package must be runnable when required

对于声明为可运行的软件项目，必须验证 run/test commands。

## AC-V2-CLOSEOUT

### AC-V2-CLOSEOUT-001: closeout only after verified evidence

Closeout 只能在 evidence、source inventory、git audit、replay bundle 全部 ready 后通过。

### AC-V2-CLOSEOUT-002: replay bundle required

缺 replay bundle 不允许 terminal success。

### AC-V2-CLOSEOUT-003: human-readable process audit required

必须产出人类可读 process audit。

## Negative acceptance

以下情况必须失败：

- runtime 生成 placeholder source；
- runtime 合成 verification success；
- provider attempt count 为 0；
- acceptance map 为空；
- source inventory 只证明 ref 存在；
- checker notes 覆盖 blocker；
- generated project package 缺 run manifest；
- final package 不可运行却 closeout passed；
- replay bundle 缺失；
- closeout 阶段才首次发现 implementation 缺口。

---

## 分批验收

下面 9 段对应 `backlog.md` 的 Phase 0 ~ Phase 8。每段固定结构：

- **AC 检查清单**：本 phase 需要勾选的项；每项标注由哪个工作包的 negative / happy test 提供证据，并显式绑定到 AC-V2-XXX。
- **本批产出**：本 phase 完成时仓库内应存在的文件、模块或文档同步项。
- **进入下一 Phase 前置**：在所有 AC checkbox 已勾选基础上，还需满足的额外门槛（用户确认、状态字段、日志条目等）。

### Phase 0 验收 — V2-000 + V2-001

#### AC 检查清单

- [x] AC-V2-FOUNDATION-001（clean branch foundation）— 由 V2-000 产物证明：根 README / AGENTS / doc 全目录 / src·tests·scripts·examples 占位存在
- [x] AC-V2-FOUNDATION-002（legacy boundary）— 由 V2-000 产物证明：`AGENTS.md`、`doc/06-reference/legacy-boundary.md` 和 `decisions.md` DEC-0001/DEC-0002 均声明 abandoned by default
- [x] V2-001A 完成（Phase 0 完整性审计）—— 独立审计已完成，识别 4 项阻塞缺口 + 1 项幂等性缺口
- [x] V2-001B 完成（工作包计划审计）—— 51 个工作包均具备九项要素；BoardDirective / MethodologyProfile 已补；V2-070C 已拆 10 项；分批验收 + 幂等更新协议已上线
- [x] V2-001C 完成（Phase 0 用户确认与冻结）—— 2026-05-14 用户在 commit `578c7a8` 后确认推进，Phase 0 冻结

#### 本批产出

- 根 `README.md`、`AGENTS.md`、`SESSION_PROMPT.md`、`.gitignore`
- `doc/` 全目录（01-product ~ 06-reference + 通用 conventions）
- `src/`、`tests/`、`scripts/`、`examples/` 占位
- `doc/05-project-log/decisions.md` 含 DEC-0001 ~ DEC-0008
- 本文件含分批验收段
- `doc/04-implementation/backlog.md` 含幂等更新协议 + 51 个工作包

#### 进入 Phase 1 前置

- [x] 上述 AC checkbox 全部勾选
- [x] V2-001A / V2-001B / V2-001C 状态翻 DONE
- [x] `doc/05-project-log/2026-05.md` 记录 Phase 0 完成
- [x] 用户显式确认（V2-001C 验收口径）

### Phase 1 验收 — V2-010 Contract Kernel

#### AC 检查清单

- [x] AC-V2-CONTRACT-001（动态 acceptance）— 由 V2-010C `test_acceptance_contract_fail_closed.py` 证明：空 criteria / 非 blocking 全覆盖 / charter 缺 board_directive_ref 必须失败
- [x] AC-V2-CONTRACT-002（package contract 必需）— 由 V2-010D `test_package_contract_fail_closed.py` 证明：缺 package_root / run·test commands / source_surfaces 必须失败
- [x] AC-V2-CONTRACT-003（无 static universal AC）— 由 V2-010E `test_contract_gate.py` 证明：acceptance_ref 不属于 active contract 必须失败
- [x] BoardDirective intake 闭合 — 由 V2-010B negative test 证明：不存在 directive 不得创建 ProjectCharter
- [x] MethodologyProfile 闭合 — 由 V2-010F negative test 证明：PackageContract 缺 methodology_profile_ref 必须失败；四种 template_kind 影响 workspace docs template 选择
- [x] V2-010G fixture 与 AC-V2 绑定闭合 — 由 V2-010G `test_tiny_fullstack_contract_fixture_fail_closed.py` 证明：fixture 缺 AC-V2 显式绑定、未知 AC-V2 绑定或 fallback implementation evidence 必须失败
- [x] V2-010A ~ V2-010G 七个工作包全部 DONE
- [x] `backlog.md` 进度总览 Phase 1 显示 7/7

#### 本批产出

- 代码：`src/boardroom_os/contracts/{types,directive,project,acceptance,package,source_surface,evidence_obligation,gates,methodology}.py`
- 正例测试：`tests/contracts/` 至少 7 个测试文件
- 负例测试：`tests/negative/` 至少 5 个 fail-closed 测试
- Fixture：`tests/fixtures/contracts/tiny_fullstack_contract.py`
- 文档同步：本文件 Phase 1 checkbox 全勾选；`backlog.md` 工作包状态翻 DONE

#### 进入 Phase 2 前置

- [x] 上述 AC checkbox 全部勾选
- [x] V2-010A ~ V2-010G 状态全部 DONE
- [x] `doc/05-project-log/2026-05.md` 记录每个工作包完成日期
- [x] fixture 与本文件 AC-V2 抽象 AC 形成显式绑定（V2-010G 验收口径）

### Phase 2 验收 — V2-020 Event + Reducer Kernel

#### AC 检查清单

- [x] AC-V2-GRAPH-001（ticket graph 是状态源）— 由 V2-020C `test_ticket_graph_projection.py` 证明：ticket 缺 acceptance_refs / source_surface_refs / evidence_obligations / allowed_write_set 必须无效
- [x] AC-V2-GRAPH-002（reducer-protected transitions）— 由 V2-020D `test_ticket_reducer_transitions.py` + `test_executor_cannot_complete_ticket.py` 证明：executor 提交 `TICKET_COMPLETED`、provider_attempt_count 为 0、checker blocker 未清除时完成 ticket 必须失败；completion boundary（完成边界）由 V2-050F 适配正式 evidence/checker 模型
- [x] typed event record 完整性 — 由 V2-020A `test_event_record.py` 证明：事件缺 actor / timestamp / graph_version / payload refs、无时区 timestamp、未知 event_type 必须失败；stable dump 可回放为 EventRecord
- [x] event log append 完整性 — 由 V2-020B `test_event_log.py` 证明：graph_version 回退 / 重复 event_id / 未知 event_type 必须失败；按 project_ref 隔离 graph_version 序列并可按版本范围读取事件
- [x] seat assignment 投影 — 由 V2-020E `test_seat_assignment_projection.py` 证明：ticket 无 owner_seat_ref / 缺 SEAT_ASSIGNED 事件 / SEAT_ASSIGNED 早于 TICKET_CREATED / 多 payload_refs / assignment 引用未知 ticket / seat 缺 model_execution_profile_ref / 未知 seat / inactive seat / seat 声明 capability 与 assignment required_capability_tags 不一致必须 fail closed 或 blocked
- [x] projection replay 可重建 — 由 V2-020F `test_projection_replay.py` 证明：audit replay（审计重放）仅重放 `seat_assignment_graph` projection summary（席位分配图投影摘要）；事件缺失 / 乱序 / project mismatch（项目不匹配）/ non-positive expected_graph_version（非正预期图版本）/ from_graph_version 中段重放缺 snapshot/base projection contract（快照/基准投影合同）/ projection version mismatch（投影版本不匹配）必须 fail closed；相同事件序列产生 deterministic `summary_hash`
- [x] V2-020A ~ V2-020F 六个工作包全部 DONE
- [x] `backlog.md` 进度总览 Phase 2 显示 6/6

#### 本批产出

- 代码：`src/boardroom_os/events/`、`src/boardroom_os/reducers/`、`src/boardroom_os/graph/`
- 测试：`tests/reducers/` 至少 6 个测试文件 + `tests/negative/test_executor_cannot_complete_ticket.py`
- 文档同步：本文件 Phase 2 checkbox 全勾选；`backlog.md` 工作包状态翻 DONE

#### 进入 Phase 3 前置

- [x] 上述 AC checkbox 全部勾选
- [x] V2-020A ~ V2-020F 状态全部 DONE
- [x] 项目日志记录完成
- [x] reducer 公开接口稳定（后续 V2-050F 完成度门禁会复用）

### Phase 3 验收 — V2-030 Agent Seat + Execution Package Compiler

#### AC 检查清单

- [x] AC-V2-EXECUTION-001（execution package required）— 由 V2-030C `test_execution_package_fail_closed.py` 证明：缺 ticket_ref / graph_version / seat_ref / model_execution_profile / acceptance_refs / allowed_write_set / evidence_obligations / fallback_policy_ref 必须失败；只传 ticket_id alias 或 model_execution_profile_ref 也必须失败
- [x] AC-V2-EXECUTION-003（fallback 不能满足 implementation evidence）— V2-030E `test_fallback_cannot_satisfy_implementation.py` 已提供 typed evaluator（类型化判定器）与真值表负例；V2-050A1 已补齐 FallbackPolicyRegistry（降级策略注册表）与 FallbackDecisionRecord（降级判定记录）；V2-050B `test_synthetic_evidence_rejected.py` 已证明 EvidenceVerifier（证据验证器）实际通过 registry 解析 fallback_policy_ref、消费 decision record 并拒绝未解析 registry、缺 decision 或 allowed=False 的 fallback artifact

> Phase-gating 说明：`backlog.md` 的 Phase 3 `完成` 表示 V2-030A ~ V2-030F 工作包 6/6 已完成；AC-V2-EXECUTION-003 的最终 verifier wiring（验证器接线）证据已由 V2-050A1 / V2-050B 闭合。

- [x] Role / Seat / Provider 接入链闭合 — V2-030A 已证明 RoleProfile / SkillBinding / ModelExecutionProfile 边界；V2-030B 已证明 AgentSeat 生命周期与派工投影；V2-030D 已证明 AgentTeamProjector 单一治理投影入口与 ExecutionPackage compiler 严格消费已派工 ready ticket，闭合 AgentSeat -> ExecutionPackage 链路（见 DEC-0011 / DEC-0013）
- [x] Agent context index 可审计 — 由 V2-030F `test_agent_context_index.py` 证明：缺 execution_package_ref / model_execution_profile / allowed_write_set / provider_attempt_refs 必须失败；ExecutionPackage（执行包）可生成确定性 AgentContextSnapshot（智能体上下文快照）；最终 AgentContextIndexEntry（智能体上下文索引条目）必须绑定有序 ProviderAttemptRef（模型调用尝试引用）
- [x] V2-030A ~ V2-030F 六个工作包全部 DONE
- [x] `backlog.md` 进度总览 Phase 3 显示 6/6

#### 本批产出

- 代码：`src/boardroom_os/agents/`、`src/boardroom_os/execution/{package,compiler,fallback,context_index}.py`
- 测试：`tests/execution/` 至少 6 个测试文件 + `tests/negative/` fail-closed 测试
- 文档同步：本文件 Phase 3 checkbox 全勾选；`backlog.md` 工作包状态翻 DONE

#### 进入 Phase 4 前置

- [x] 上述 AC checkbox 全部勾选
- [x] V2-030A ~ V2-030F 状态全部 DONE
- [x] ExecutionPackage schema 稳定（V2-040 / V2-080 都会消费）
- [x] 项目日志记录完成

### Phase 4 验收 — V2-040 Runtime Executor + Provider + Command Runner

#### AC 检查清单

- [x] AC-V2-EXECUTION-002（provider attempt required）— 由 V2-040A `test_provider_attempt.py` 证明：attempt 缺 provider / model / input_package_ref / seat_ref / status / outcome 必须失败；fallback outcome 缺 typed fallback_kind 或 primary outcome 携带 fallback_kind 必须失败；FakeProviderTransport 可产生绑定 ExecutionPackageRef / AgentSeatRef 的 ProviderAttempt
- [x] Provider executor boundary — 由 V2-040B `test_provider_executor_fail_closed.py` + `test_provider_executor.py` 证明：缺 execution package 不得调用 provider；RoleProfile / TicketNode shortcut 不能绕过 ExecutionPackage；adapter 回填错绑 ProviderAttempt 必须 fail closed；合法 ExecutionPackage 可调用 fake provider 并记录 attempt；failed attempt 作为可审计事实返回
- [x] AC-V2-EVIDENCE-001（command evidence from runner）— 由 V2-040D `test_command_runner.py` 证明：合成 verification success / 缺 stdout/stderr refs / 缺 exit_code / 命令不在 package contract 中 / cwd 越界或 absolute cwd / 时钟异常必须失败；合法 runner 记录真实 exit code/stdout/stderr/duration 并生成 VerificationRun
- [x] Runtime bounded — 由 V2-040E `test_runtime_cannot_govern.py` 证明：runtime emit `TICKET_COMPLETED` / 保留治理事件名 `project_completed` / `closeout_committed` 必须失败；runtime/executor 不能靠普通 seat actor_ref 绕过 role-aware 边界（见 DEC-0011）
- [x] V2-040A ~ V2-040E 五个工作包全部 DONE
- [x] `backlog.md` 进度总览 Phase 4 显示 5/5

#### 本批产出

- 代码：`src/boardroom_os/providers/`、`src/boardroom_os/adapters/process_runner.py`、`src/boardroom_os/execution/{provider_executor,work_product,verification_run,runtime_executor}.py`
- 测试：`tests/execution/` 至少 5 个测试文件 + `tests/negative/test_runtime_cannot_govern.py`
- 文档同步：本文件 Phase 4 checkbox 全勾选

#### 进入 Phase 5 前置

- [x] 上述 AC checkbox 全部勾选
- [x] V2-040A ~ V2-040E 状态全部 DONE
- [x] Fake provider transport 与 ProviderAttempt schema 稳定（V2-080 会复用）

### Phase 5 验收 — V2-050 Evidence Verifier + Checker + Rework

#### AC 检查清单

- [ ] AC-V2-EVIDENCE-002（source inventory proves lineage）— 明确延后至 V2-060C 提供；V2-050B 中 verifier 端的 `test_synthetic_evidence_rejected.py` 只覆盖 synthetic / fallback evidence（合成/降级证据）不能替代 source inventory lineage（源码清单来源链）
- [x] AC-V2-EVIDENCE-003（evidence map complete）— 由 V2-050C `test_missing_acceptance_map_blocks_closeout.py` 证明
- [x] AC-V2-CHECKER-001（checker blocks gaps）— 由 V2-050D `test_checker_verdict.py` 证明：FinalEvidenceTable（最终证据表）missing / failed rows 必须转为 `REWORK_REQUIRED` blocker，malformed typed input（畸形类型化输入）必须 fail closed
- [x] AC-V2-CHECKER-002（notes 不能覆盖 blocker）— 由 V2-050D `test_checker_verdict.py` 证明：notes（备注）不会清除 evidence blocker（证据阻断项）或 manual checker blocker（手动检查阻断项）
- [x] Rework 闭环 — 由 V2-050E `test_rework_ticket_generation.py` 证明
- [x] Completion gate 接入 reducer — 由 V2-050F `test_completion_gate_with_evidence.py` 证明：正式 evidence/checker 模型不得绕过 `WORK_PRODUCT_SUBMITTED` 与 provider attempt 门禁
- [x] V2-050A ~ V2-050F 七个工作包全部 DONE（含 V2-050A1；当前 7/7）
- [x] `backlog.md` 进度总览 Phase 5 显示 7/7

#### 本批产出

- 代码：`src/boardroom_os/evidence/{claim,fallback_registry,verifier,table}.py`、`src/boardroom_os/checker/{verdict,checker,rework}.py`、`src/boardroom_os/reducers/completion_gate.py`
- 测试：`tests/evidence/`、`tests/reducers/test_completion_gate_with_evidence.py`、相应 negative 测试
- 文档同步：V2-050-owned checkbox（V2-050 负责的验收项）已勾选；AC-V2-EVIDENCE-002 明确延后至 V2-060C

#### 进入 Phase 6 前置

- [x] V2-050-owned checkbox（V2-050 负责的验收项）全部勾选；AC-V2-EVIDENCE-002 明确延后至 V2-060C
- [x] V2-050A ~ V2-050F 状态全部 DONE（含 V2-050A1）
- [x] FinalEvidenceTable schema 稳定（V2-060 / V2-070 会消费）

### Phase 6 验收 — V2-060 Workspace + Package Assembler

#### AC 检查清单

- [x] V2-060A WorkspaceManifest（工作区清单）完成 — 由 `tests/proving/test_workspace_manifest.py` 证明：缺 `10-project` / `20-evidence`、package root 非 `10-project`、repo layout misuse（仓库布局误用）、cache/secrets/scratch section（缓存/密钥/临时区段）均 fail closed；happy path 可定位 boardroom/package/evidence/audit roots（四区根路径）
- [x] AC-V2-PACKAGE-001（package 是最终输出）— 由 V2-060B `test_package_assembler.py` 证明：缺 package-contract / run-manifest / source 写到 package root 外必须失败
- [x] AC-V2-PACKAGE-002（package 必须可运行）— 由 V2-060D `test_run_manifest.py` 证明：software/mixed package（软件/混合包）缺 run/test commands 必须失败；RunManifest（运行清单）与 PackageContract（包合同）命令不一致、未声明命令、非 canonical package root（非规范包根）均 fail closed；happy path 串联 `validate_run_manifest_binding(...)` → `CommandRunner.run(...)` 并生成 VerificationRun（验证运行）
- [x] AC-V2-EVIDENCE-002（source inventory lineage）— 由 V2-060C `test_source_inventory_ref_only_rejected.py` 与 `test_source_inventory.py` 证明：ref-only / 缺 sha256 / 缺 producer_ticket_ref / 缺 producer_attempt_ref / 缺 acceptance_refs / 缺 evidence_refs 必须失败；happy path 绑定 path、sha256、source_surface_ref、producer_ticket_ref、producer_attempt_ref、acceptance_refs 和 evidence_refs
- [x] Workspace / package / evidence 三者同步 — 由 V2-060E `test_workspace_evidence_export.py` 证明
- [x] Agent asset bundle 导入可审计 — 由 V2-060F `test_agent_asset_import.py` 证明：外部 role/skill/prompt/MCP 资产必须物化为 `00-boardroom/agents/` 快照并记录 `asset-import-manifest.yaml` 来源链；ExecutionPackage compiler 保持 0 外部文件输入
- [x] V2-060A ~ V2-060F 六个工作包全部 DONE
- [x] `backlog.md` 进度总览 Phase 6 显示 6/6

#### 本批产出

- 代码：`src/boardroom_os/workspace/{manifest,assembler,source_inventory,run_manifest,evidence_export,agent_asset_import}.py`（当前已存在 `src/boardroom_os/workspace/manifest.py`）
- 测试：`tests/proving/` 至少 6 个测试文件 + `tests/negative/test_source_inventory_ref_only_rejected.py`（当前已存在 `tests/proving/test_workspace_manifest.py`）
- 文档同步：本文件 Phase 6 随工作包逐项勾选；Phase 6 全部完成后再全勾选

#### 进入 Phase 7 前置

- [x] 上述 AC checkbox 全部勾选
- [x] V2-060A ~ V2-060F 状态全部 DONE
- [x] SourceInventory 与 RunManifest 与 FinalEvidenceTable 协同稳定

### Phase 7 验收 — V2-070 Closeout + Replay + Process Audit

#### AC 检查清单

- [x] AC-V2-CLOSEOUT-001（closeout 只能在 verified evidence 之后）— 由 V2-070A `test_closeout_fail_closed.py` 证明
- [x] AC-V2-CLOSEOUT-002（replay bundle required）— 由 V2-070A + V2-070B 证明：event log hash chain / hash manifest 缺失必须失败；ReplayBundle（重放包）归档 EventRecord（事件记录）切片并在 readiness（就绪投影）中重算 event hash chain（事件哈希链）与 artifact/hash manifests（产物/哈希清单），篡改后同步重算仍 fail closed
- [x] AC-V2-CLOSEOUT-003（人类可读 process audit）— 由 V2-070C `test_process_audit_artifacts.py` 与 `test_process_audit.py` 证明：ProcessAuditBundle（流程审计包）物化 10 项 30-audit 产物且缺一不可（process-audit.md / timeline.json / decision-log.md / agent-context-index.json / ticket-graph.md / artifact-lineage.json / evidence-map.json / git-version-audit.md / closeout-summary.md / replay-bundle-report.json），artifact manifest（产物清单）、hash manifest（哈希清单）、evidence map（证据映射）、readiness projection（就绪投影）、标准 Markdown 可读性和真实 EventRecord timeline projection（事件记录时间线投影）篡改均 fail closed
- [x] Git version audit 完整 — 由 V2-070D `test_git_version_audit.py` 证明：GitVersionAuditBundle（Git 版本审计包）记录 final package commit（最终项目包提交）、dirty status（脏工作区状态）、diff summary（差异摘要）、source inventory hash（源码清单哈希）和 final command evidence（最终命令证据），并在 readiness projection（就绪投影）中重算 hash manifest（哈希清单）后输出 CloseoutGate（收尾门禁）可消费的 GitAuditReadiness（Git 审计就绪摘要）
- [x] CloseoutPackage 绑定一致 — 由 V2-070E `test_closeout_package.py` 证明：CloseoutPackage（收尾包）稳定绑定 CloseoutGateResult（收尾门禁结果）、SourceInventory（源码清单）、FinalEvidenceTable（最终证据表）、ReplayBundle（重放包）、ProcessAuditBundle（流程审计包）和 GitVersionAuditBundle（Git 版本审计包），并对 readiness/bundle mismatch（就绪摘要/完整包不一致）、project_ref mismatch（项目引用不一致）、unsafe checked_refs（不安全检查引用）和 version/verdict 不变量 fail closed
- [ ] Closeout reducer 接入 — 由 V2-070F `test_closeout_reducer.py` 证明：增量 reducer/replay 不得丢失历史 `WORK_PRODUCT_SUBMITTED` 事实
- [ ] V2-070A ~ V2-070F 六个工作包全部 DONE
- [ ] `backlog.md` 进度总览 Phase 7 显示 6/6

#### 本批产出

- 代码：`src/boardroom_os/closeout/{gate,package}.py`、`src/boardroom_os/audit/{replay_bundle,process_audit,git_version_audit}.py`、`src/boardroom_os/adapters/git_audit.py`、`src/boardroom_os/reducers/closeout_reducer.py`
- 测试：`tests/closeout/` 至少 7 个测试文件 + `tests/negative/test_closeout_fail_closed.py`
- 文档同步：本文件 Phase 7 checkbox 全勾选

#### 进入 Phase 8 前置

- [ ] 上述 AC checkbox 全部勾选
- [ ] V2-070A ~ V2-070F 状态全部 DONE
- [ ] 10 项 30-audit 产物的 schema 稳定

### Phase 8 验收 — V2-080 Tiny Full-stack Proving Scenario

#### AC 检查清单

- [ ] tiny scenario active contracts 完整 — 由 V2-080A `test_tiny_contracts.py` 证明：覆盖 API / UI / persistence / run / test acceptance refs
- [ ] tiny ticket graph + seat assignment — 由 V2-080B 证明
- [ ] tiny provider attempts — 由 V2-080C `test_tiny_provider_attempts.py` 证明：每个 implementation ticket ≥ 1 ProviderAttempt
- [ ] tiny evidence verification — 由 V2-080D `test_tiny_evidence_verification.py` 证明：final evidence table complete
- [ ] tiny package assembly — 由 V2-080E `test_tiny_package_assembly.py` 证明：package root + run manifest + source inventory + evidence
- [ ] tiny closeout / replay / process audit — 由 V2-080F `test_tiny_closeout.py` 证明：closeout passed + 10 项 30-audit 产物齐全 + replay 可重建
- [ ] `proving-scenario-tiny-fullstack.md` 的 Functional / Package / Evidence / Negative checks 全部满足
- [ ] V2-080A ~ V2-080F 六个工作包全部 DONE
- [ ] `backlog.md` 进度总览 Phase 8 显示 6/6

#### 本批产出

- Generated project package：完整 tiny book availability tracker（backend + frontend + tests + docs + run manifest + package contract）
- Evidence bundle：`20-evidence/` 完整目录（tests / integration / git / source-inventory / closeout）
- Audit bundle：`30-audit/` 10 项产物
- 测试：`tests/proving/` 至少 6 个测试文件
- 文档同步：本文件 Phase 8 checkbox 全勾选

#### V2 端到端能力成立的判定

- [ ] 所有 AC checkbox 全部勾选
- [ ] V2-080A ~ V2-080F 状态全部 DONE
- [ ] tiny package 可以本地运行 declared run commands
- [ ] tiny closeout 产生 CloseoutPackage（verdict: passed）
- [ ] process audit 可被人类读懂并完成审计

> 仅当上述全部满足时，V2 第一阶段（foundation + minimal end-to-end）才算成立。**workflow completed ≠ V2 完成**。


