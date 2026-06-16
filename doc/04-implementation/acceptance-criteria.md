# V2 总验收标准

## 文档职责

本文件定义 Boardroom OS V2 自身的验收标准。它不是某个 generated project 的 acceptance contract。

本文件由两层组成：

1. **抽象原则层（AC-V2-XXX）**：principle-level 验收标准，对应架构主线。`backlog.md` 的工作包必须显式映射到这里的某条 AC。
2. **分批验收层（Phase 0 ~ Phase 10）**：每个 phase 完成时人类用以验收的 checkbox 清单、产出清单和"进入下一 Phase 前置"。这层是人类视角的 quality gate。

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

## AC-V2-REWORK

### AC-V2-REWORK-001: rework cycle is graph-governed

ReworkCycle（返工循环）必须由 TicketGraph（工单图）和 reducer（归约器）表达。runtime（运行时）、executor（执行器）或 atomic-agent（原子智能体）不得直接关闭返工、完成 ticket（工单）或推进 closeout（收尾）。

### AC-V2-REWORK-002: rework request requires verified blocker

没有 FinalEvidenceTable missing/failed row（最终证据表缺失/失败行）、CheckerVerdict blocker（检查结论阻塞项）或 CloseoutGate failure（收尾门禁失败）等 verified blocker（已验证阻塞项）时，不得创建 ReworkRequest（返工请求）。

### AC-V2-REWORK-003: rework scope is contract-bound

ReworkTicket（返工工单）必须绑定 active AcceptanceContract（活跃验收合同）、PackageContract（包合同）、SourceSurface（源码面）和 EvidenceObligation（证据义务）。返工不得引入静态 acceptance refs（验收引用）、路径前缀源码面推断或第二事实源。

### AC-V2-REWORK-004: each rework attempt re-enters evidence and checker gates

每次 ReworkAttempt（返工尝试）产物必须重新经过 EvidenceVerifier（证据验证器）、FinalEvidenceTableBuilder（最终证据表构建器）、SourceInventory（源码清单）和 Checker（检查者）。旧的 satisfied evidence row（已满足证据行）、Checker approved verdict（检查通过结论）或 CloseoutPackage passed（通过收尾包）不得跨轮次复用。

### AC-V2-REWORK-005: rework termination is explicit and auditable

达到预算、重复失败、合同冲突或需要人工澄清时，必须生成可审计 escalation/termination decision（升级/终止决策）。禁止静默失败、无限循环或由 runtime 自动放行。

### AC-V2-REWORK-006: manifest ingestion converts ambiguity to rework context

RunManifest（运行清单）摄取不得把 LLM（大模型）输出的 behavior assertion type（行为断言类型）词汇当作封闭成功协议。未知、变体或不可解释断言不得 raw crash（原始崩溃）、不得静默跳过、不得算作通过证据；必须保留 raw payload（原始载荷）并交给 CEO（项目经理）通过 TicketGraph / SeatDemand（工单图 / 席位需求）派给 verify-blackbox ticket（黑盒验证工单）的 AgentSeat（智能体席位）生成 BlackboxVerificationPlan（黑盒验证计划）。Runner（运行器）只能执行该计划并记录 observed facts（观察事实）；Checker / Closeout（检查 / 收尾）再把失败投影为 verified blocker（已验证阻塞项）或显式升级上下文。

## AC-V2-AGENT

### AC-V2-AGENT-001: role prompt hooks versioned and auditable

CEO / Architect / Worker / Tester / Checker / Closeout 的基础 RolePromptHook（角色提示词钩子）必须是 governed asset（治理资产），具备版本、hash、role category（角色类别）和 policy refs（策略引用），并进入 RoleProfile（角色模板）、ExecutionPackage（执行包）和 ProviderAttempt（模型调用尝试记录）审计链。

所有 agent role（智能体角色）都必须通过 ExecutionPackage（执行包）接收上下文并接入 LLM（大模型）；Tester（测试者）、Checker（检查者）等非 implementation category（非实施类别）角色也必须接收自身 RolePromptHook（角色提示词钩子）并在 ProviderAttempt（模型调用尝试记录）中留痕。EvidenceVerifier（证据验证器）校验 ProviderAttempt 与对应 ExecutionPackage hook snapshot（执行包钩子快照）一致，不按 RoleCategory（角色类别）推断证据权限。

### AC-V2-AGENT-002: prompt constraints do not replace gates

RolePromptHook（角色提示词钩子）只能约束 agent behavior（智能体行为）和派生提示词边界，不能替代 AcceptanceContract（验收合同）、PackageContract（包合同）、reducer（归约器）、EvidenceVerifier（证据验证器）或 CloseoutGate（收尾门禁）的程序化校验。

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

### AC-V2-EVIDENCE-004: live integration proves behavior

当 AcceptanceContract（验收合同）声明 frontend/backend integration（前后端集成）、HTTP API（HTTP 接口）、service startup（服务启动）或 persistence（持久化）时，最终证据必须来自真实 command evidence（命令证据）、service readiness probe（服务就绪探针）或 live blackbox integration（真实黑盒集成）。fakeFetch（模拟 fetch）、源码字符串检查或函数级单测不能单独满足 full-stack acceptance（全栈验收）。

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

### AC-V2-PACKAGE-003: all declared commands require evidence

RunManifest（运行清单）中的每个 declared run/test command（声明运行/测试命令）都必须有对应 final evidence（最终证据）。已有 VerificationRun（验证运行）不能代表未执行、未 probe（探测）或未绑定的 command。

## AC-V2-CLOSEOUT

### AC-V2-CLOSEOUT-001: closeout only after verified evidence

Closeout 只能在 evidence、source inventory、git audit、replay bundle 全部 ready 后通过。

### AC-V2-CLOSEOUT-002: replay bundle required

缺 replay bundle 不允许 terminal success。

### AC-V2-CLOSEOUT-003: human-readable process audit required

必须产出人类可读 process audit。

### AC-V2-CLOSEOUT-004: fact-chain 单一权威源

V2-070 大阶段的事实链必须存在唯一权威源：EventLog 是事件事实的唯一权威源；ReplayBundle 必须从 events 重新投影出 ProjectionReplaySummary，不接受调用方传入的 summary 内容字段；ProcessAuditBundle 必须直接复用 ReplayBundle.events，不接受独立 events 输入；CloseoutPackage 不得二次提取 bundle 内部字段构造判定。

### AC-V2-CLOSEOUT-005: 构造无环

V2-070 阶段的对象构造顺序必须为 `EventLog → ReplayBundle → ProcessAuditBundle → GitVersionAuditBundle → CloseoutPackage → CLOSEOUT_COMMITTED 治理事件 → CloseoutReducer → CloseoutClosure`，不得形成构造环。ProcessAudit 不得要求 `CLOSEOUT_COMMITTED` 事件已经存在于事件流中；`CLOSEOUT_COMMITTED` 必须在 CloseoutPackage 构造完成后发出。

### AC-V2-CLOSEOUT-006: 无隐式 fallback

V2-070 阶段任何 adapter / builder / readiness 不得对缺失输入采用静默 fallback 或占位 sentinel 值。GitAuditAdapter 的 `base_commit_sha` / `worktree_ref`、ProcessAudit 的 `unknown` / `ticket` 占位、artifact-lineage 的 `verifier.unresolved` sentinel、`getattr(entry, ..., None)` 顶层平铺 fallback 均必须由 fail-closed 校验替代。

### AC-V2-CLOSEOUT-007: graph_version 边界严格

`CloseoutPackage.graph_version` 必须严格等于 `ReplayBundle.last_graph_version`（除非额外设计扩展证明窗口）。允许 closeout 包覆盖范围超过 replay 已证明的事件边界即视为越界。

### AC-V2-CLOSEOUT-008: payload 内容绑定

`ReplayPayloadManifest.entries[*].sha256` 必须能通过 `ReplayPayloadResolver` 在 readiness 阶段重新计算真实 payload 内容的 hash 并比对；只有 ref 覆盖检查不构成可信 payload 证明。

### AC-V2-CLOSEOUT-009: 跨包引用命名空间

V2-070 阶段所有持久化引用（`fact_set_id`、`artifact_ref`、`content_ref`、`closeout_package_id` 等）必须包含 `project_ref` 与 `content_hash`（或 `run_id`）命名空间段，禁止跨 run / 跨 project / 跨 bundle 串包。

### AC-V2-CLOSEOUT-010: 确定性哈希

V2-070 阶段所有 hash 输入若语义为集合（payload/artifact manifest entries、verification_runs、command_evidence_bindings、checked_refs 等），必须 canonical sort（规范排序）后参与 hash；若语义为序列（events、event_hash_chain），必须说明序列权威来源并保持稳定。同一事实重建必须产出字节相同的 hash。

### AC-V2-CLOSEOUT-011: closeout validates behavior claims

CloseoutGate（收尾门禁）不得只验证 refs（引用）、hashes（哈希）和 bundle readiness（包就绪摘要）结构一致；它必须确认 final evidence（最终证据）覆盖 active acceptance claims（活跃验收命题）的真实行为对象。真实证据若证明了错误命题，不能 closeout passed（收尾通过）。

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
- run manifest 中任一 declared command 缺最终证据；
- fakeFetch-only integration 被当作 full-stack acceptance；
- service command 缺 startup/readiness probe；
- 无 verified blocker 创建返工；
- runtime 或 atomic-agent 直接判定返工 accepted；
- 返工复用旧 FinalEvidenceTable / CheckerVerdict / CloseoutPackage 作为新轮次通过证据；
- 返工耗尽预算但缺 escalation/termination decision；
- replay bundle 缺失；
- closeout 阶段才首次发现 implementation 缺口。

---

## 分批验收

下面 11 段对应 `backlog.md` 的 Phase 0 ~ Phase 10。每段固定结构：

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
- [x] Closeout reducer 接入 — 由 V2-070F `test_closeout_reducer.py` 证明：增量 reducer/replay 不得丢失历史 `WORK_PRODUCT_SUBMITTED` 事实
- [x] V2-070A ~ V2-070F 六个工作包全部 DONE
- [x] `backlog.md` 进度总览 Phase 7 显示 6/6

#### 本批产出

- 代码：`src/boardroom_os/closeout/{gate,package}.py`、`src/boardroom_os/audit/{replay_bundle,process_audit,git_version_audit}.py`、`src/boardroom_os/adapters/git_audit.py`、`src/boardroom_os/reducers/closeout_reducer.py`
- 测试：`tests/closeout/` 至少 7 个测试文件 + `tests/negative/test_closeout_fail_closed.py`
- 文档同步：本文件 Phase 7 checkbox 全勾选

#### 进入 Phase 8 前置

- [x] 上述 AC checkbox 全部勾选
- [x] V2-070A ~ V2-070F 状态全部 DONE
- [x] 10 项 30-audit 产物的 schema 稳定

> **Phase 7 重审说明（2026-05-25）**：外部独立审计在 V2-070A~G 实施基础上识别出 18 项 P0/P1/P2 缺口（详见 `doc/04-implementation/v2-070-batch-review-report.md` 与 DEC-0016）。Phase 7 抽象 AC（AC-V2-CLOSEOUT-001/002/003）所要求的"可信收尾"在 fact chain（事实链）权威源、构造顺序、跨包绑定、确定性哈希、Git 审计 fallback、命名空间命名等 6 个维度仍存在结构性缺口。原 Phase 7 checkbox 保留勾选作为"070A~F 各自工作包已交付"的依据，但**整体 Phase 7 不视为关闭**；进入 Phase 8 还须先通过 Phase 7.5（V2-071）的 fact-chain 重构闭合验收。

### Phase 7.5 验收 — V2-071 Closeout fact-chain hardening（事实链强化重构）

> 本批验收负责消除 V2-070-batch-review-report.md 列出的 18 项 P0/P1/P2 缺口；Phase 7 的抽象 AC（AC-V2-CLOSEOUT-001/002/003）必须在 Phase 7.5 完成后才能视为完整闭合。Phase 7.5 完成后，Phase 8 的"进入前置"中"V2-071F 闭合"checkbox 自动满足。

#### AC 检查清单

- [x] AC-V2-CLOSEOUT-004（事实链单一权威源；新增抽象原则，见本文件第 1 部分）— 分项闭合进度：
  - [x] V2-071B ReplayBundle（重放包）部分已由 `test_replay_bundle_rereplay.py` / `test_replay_bundle_external_summary_rejected.py` 证明：ReplayBundle 从 events 重新投影，调用方无法通过 builder 输入伪造 ProjectionReplaySummary 内容字段
  - [x] V2-071C ProcessAudit（流程审计）部分已由 `test_process_audit_fact_chain.py` / `test_process_audit_construction_loop_rejected.py` 证明：ProcessAudit 直接复用 ReplayBundle.events，不接受独立 events
- [x] AC-V2-CLOSEOUT-005（无构造环；新增抽象原则）— 由 V2-071C `test_process_audit_construction_loop_rejected.py` 证明：事件流不含 `CLOSEOUT_COMMITTED` 时 ProcessAuditBundle 必须可成功构造；CloseoutPackage 构造完成后才发出 `CLOSEOUT_COMMITTED` 治理事件
- [x] AC-V2-CLOSEOUT-006（无隐式 fallback；映射到 No silent fallbacks 硬规则）— 由 V2-071D `test_git_audit_fallback_rejected.py` 证明：GitAuditAdapter 缺 `base_commit_sha` / `worktree_ref` 必须 raise，不再 fallback 到 `final_commit_sha` 或 `worktree.{package_root}`
- [x] AC-V2-CLOSEOUT-007（graph_version 边界严格）— 由 V2-071E `test_closeout_package_graph_version_overflow_rejected.py` 证明：`CloseoutPackage.graph_version > ReplayBundle.last_graph_version` 必须 fail closed
- [x] AC-V2-CLOSEOUT-008（payload 内容绑定）— 由 V2-071E `test_replay_payload_manifest_tampering_rejected.py` 证明：`ReplayPayloadManifest.entries[*].sha256` 与 resolver 重算结果不一致必须 raise
- [x] AC-V2-CLOSEOUT-009（跨包引用命名空间）— V2-071A 已交付 `boardroom_os.contracts.refs`（引用命名空间 helper）基础设施与 `test_namespaced_refs.py` / `test_namespaced_refs_fail_closed.py`；最终由 V2-071E `test_closeout_package_boundary.py` 证明 `fact_set_id` / `artifact_ref` / `content_ref` / `closeout_package_id` 全面采用 `project_ref` + `content_hash` + 必要时 `run_id` 命名空间，禁止跨 run / 跨 project / 跨 bundle 串包
- [x] AC-V2-CLOSEOUT-010（确定性哈希）— 分项闭合进度：
  - [x] V2-071A 已交付 `canonical_sort_for_hash` 与 `hash_namespaced_payload` helper
  - [x] V2-071B 已由 `test_replay_bundle_rereplay.py` 证明 payload manifest entries / artifact manifest entries 乱序后仍产生稳定 hash
  - [x] V2-071C 已由 `test_process_audit_fact_chain.py` 证明 `checked_refs` 等 ProcessAudit 集合语义输入乱序后仍产生稳定 hash；V2-071D 已由 `test_git_audit_hardening.py` 证明 GitVersionAudit 的 verification_runs / command_evidence_bindings 稳定性
- [x] artifact-lineage producer/consumer 正确分离 — 由 V2-071C 证明：当 ticket A 产出源码、ticket B 消费时，artifact-lineage.json 必须分别记录 producer_ticket_ref 与 consumer_ticket_ref
- [x] ProcessAudit `unknown` / `ticket` 占位 fallback 消除 — 由 V2-071C 证明：`ticket_graph_summary` / `agent_context_index` 缺字段时直接 raise，不输出占位字符串
- [x] expected_fallback_decision_refs 排他校验 — 由 V2-071C 证明：`expected_fallback_decision_refs` 为空但 actual fallback lineages 非空必须 fail closed
- [x] AgentContextIndex 字段路径正确 — 由 V2-071C 证明：从 `entry.snapshot.execution_package_ref` / `entry.snapshot.model_execution_profile` 读取，不再 `getattr(entry, ..., None)` 取顶层平铺字段
- [x] Git status `--porcelain -z` 解析鲁棒 — 由 V2-071D 证明：含换行 / 引号 / 反斜杠 / 制表符的文件名可被正确解析
- [x] Git diff stat 锚定 summary footer — 由 V2-071D 证明：含 `12 insertions.md` 等特殊文件名不污染 `GitDiffSummary.insertions`
- [x] V2-070-batch-review-report.md 18 项 P0/P1/P2 缺口逐项闭合 — 由 V2-071F `test_v2_070_audit_report_p0_regressions.py` / `test_v2_070_audit_report_p1_regressions.py` / `test_v2_070_audit_report_p2_regressions.py` 证明
- [x] V2-071A ~ V2-071F 六个工作包全部 DONE
- [x] `backlog.md` 进度总览 Phase 7.5 显示 6/6

#### 本批产出

- 新增代码：`src/boardroom_os/contracts/refs.py`（跨包命名空间 helper + canonical sort helper）
- 修改代码：`src/boardroom_os/audit/replay_bundle.py`、`src/boardroom_os/audit/process_audit.py`、`src/boardroom_os/audit/git_version_audit.py`、`src/boardroom_os/adapters/git_audit.py`、`src/boardroom_os/closeout/package.py`、必要时 `src/boardroom_os/workspace/source_inventory.py`
- 新增 spec：`doc/04-implementation/v2-071a-fact-chain-design-spec.md` ~ `v2-071f-fact-chain-regression-spec.md` 共 6 份
- 新增测试：`tests/closeout/test_replay_bundle_rereplay.py`、`tests/closeout/test_process_audit_fact_chain.py`、`tests/closeout/test_git_audit_hardening.py`、`tests/closeout/test_closeout_package_boundary.py`、`tests/closeout/test_v2_070_fact_chain_end_to_end.py`、`tests/contracts/test_namespaced_refs.py` 及对应 `tests/negative/` 负例
- 文档同步：本文件 Phase 7.5 checkbox 全勾选；`backlog.md` 工作包状态翻 DONE；`decisions.md` 新增 DEC-0016 / DEC-0017；`INDEX.md` 增加 6 份 spec 条目；`2026-05.md` 追加 V2-071A~F 完成日志

#### 进入 Phase 8 前置（更新版）

- [x] 上述 Phase 7.5 AC checkbox 全部勾选
- [x] V2-071A ~ V2-071F 状态全部 DONE
- [x] `v2-070-batch-review-report.md` 列出的 18 项缺口全部有独立 negative test 证明已闭合
- [x] CloseoutPackage / CloseoutClosure 端到端集成测试通过（不再依赖合成事件）
- [x] 全量套件（`tests/contracts tests/reducers tests/execution tests/evidence tests/proving tests/closeout tests/negative`）通过

### Phase 8 验收 — V2-080 Tiny Full-stack Proving Scenario

> **失败复审说明（2026-05-31）**：两份 tiny-fullstack 复审报告（`boardroom-os-tiny-fullstack-audit-20260531.md`、`boardroom-os-tiny-fullstack-gptpro-review.md`）撤回 Phase 8 “V2 最小端到端能力成立”结论。下列 V2-080A~F checkbox 保留为“历史工作包产物存在并曾执行”的记录，不再表示 generated package（生成包）通过端到端验收。具体失败点包括：`run-backend` / `run-frontend` 缺最终证据，backend package（后端包）不能按 `uvicorn backend.app:app` 启动，frontend integration（前端集成）为 fakeFetch（模拟 fetch）路径捕获而非 live HTTP integration（真实 HTTP 集成），SQLite persistence（SQLite 持久化）未通过 HTTP 工作流证明。整改转入 Phase 9 / V2-090。

#### AC 检查清单

- [x] tiny scenario active contracts 完整 — 由 V2-080A `test_tiny_contracts.py` 证明：覆盖 API / UI / persistence / run / test acceptance refs
- [x] tiny ticket graph + seat assignment — 由 V2-080B `test_tiny_ticket_graph.py` 证明：ticket graph ready queue 可按依赖推进，seat assignment 明确绑定 CEO / Architect / Worker / Checker
- [x] tiny provider attempts — 由 V2-080C `test_tiny_provider_attempts.py` 证明：每个 implementation ticket ≥ 1 真实 ProviderAttempt（模型调用尝试记录），provider 配置缺失 fail closed（失败关闭），raw/parsed provider output（模型输出）已物化为带 content hash（内容哈希）的 artifact（产物）
- [x] tiny evidence verification — 由 V2-080D `test_tiny_evidence_verification.py` 证明：真实 CommandRunner（命令运行器）command evidence（命令证据）可被 EvidenceVerifier（证据验证器）验证；缺 source inventory（源码清单）/ run manifest（运行清单）/ SQLite persistence evidence（SQLite 持久化证据）/ package assembly（项目包装配）时 FinalEvidenceTable（最终证据表）保持 incomplete（未完成），CompletionGate（完成门禁）继续阻断
- [x] tiny package assembly — 由 V2-080E `test_tiny_package_assembly.py` 证明：package root + run manifest + source inventory + evidence
- [x] tiny closeout / replay / process audit — 由 V2-080F `test_tiny_closeout.py` 证明：closeout passed + 10 项 30-audit 产物齐全 + replay 可重建；GitVersionAudit（Git 版本审计）消费真实 GitAuditAdapter（Git 审计适配器）事实，dirty facts（脏事实）/ 缺 base commit（基准提交）/ fake ProviderAttempt（模拟模型调用尝试记录）均 fail closed
- [ ] `proving-scenario-tiny-fullstack.md` 的 Functional / Package / Evidence / Negative checks 全部满足 — **失败复审后撤回**：V2-080 没有证明 declared run commands（声明运行命令）可启动、前后端真实串联或 SQLite 经 HTTP 持久化
- [x] V2-080A ~ V2-080F 六个工作包全部 DONE
- [x] `backlog.md` 进度总览 Phase 8 显示 6/6

#### 本批产出

- Generated project package：完整 tiny book availability tracker（backend + frontend + tests + docs + run manifest + package contract）
- Evidence bundle：`20-evidence/` 完整目录（tests / integration / git / source-inventory / closeout）
- Audit bundle：`30-audit/` 10 项产物
- 测试：`tests/proving/` 至少 6 个测试文件
- 文档同步：本文件 Phase 8 历史工作包 checkbox 保留；端到端成立 checkbox 撤回并转入 Phase 9

#### V2 端到端能力成立的判定（已撤回）

- [ ] 所有 AC checkbox 全部勾选 — Phase 8 失败复审后不满足
- [x] V2-080A ~ V2-080F 状态全部 DONE
- [ ] tiny package 可以本地运行 declared run commands — 失败复审证明 `run-backend` 无 ASGI `app` 对象，且缺 `run-backend` / `run-frontend` evidence
- [ ] tiny closeout 产生可信 CloseoutPackage（verdict: passed）— V2-080F 的 closeout passed 证明对象错误，结论撤回
- [x] process audit 可被人类读懂并完成审计

> Phase 8 只能说明 V2-080A~F 工作包曾按当时计划执行；不能说明 V2 第一阶段（foundation + minimal end-to-end）成立。**workflow completed ≠ V2 完成**。恢复端到端成立结论必须等待 Phase 9 / V2-090 全部闭合。

### Phase 9 验收 — V2-090 Tiny Fullstack Blackbox Recovery

#### AC 检查清单

- [x] AC-V2-AGENT-001 / AC-V2-AGENT-002（RolePromptHook 版本化且不替代门禁）— 由 V2-090A 证明：CEO / Architect / Worker / Tester / Checker / Closeout 基础提示词职责边界进入 RoleProfile（角色模板）、ExecutionPackage（执行包）和 ProviderAttempt（模型调用尝试记录）审计链
- [x] AC-V2-PACKAGE-003 / AC-V2-CLOSEOUT-011（declared commands final evidence requirement，声明命令最终证据要求；closeout 验证行为命题）— 由 V2-090B 证明：RunManifest（运行清单）中每个 run/test command（运行/测试命令）缺 evidence 均阻断 CloseoutGate（收尾门禁）
- [x] AC-V2-EVIDENCE-001 / AC-V2-EVIDENCE-004（真实 runner 与 live integration 证据）— 由 V2-090C 证明：ServiceRunEvidence（服务运行证据）区分长运行 service startup/readiness（服务启动/就绪）与一次性 test command（测试命令）
- [x] AC-V2-CONTRACT-001 / AC-V2-CONTRACT-002（动态验收与包合同一致）— 由 V2-090D 证明：tiny-fullstack contract（微型全栈合同）不再同时声明 uvicorn ASGI（ASGI 服务器）和 standard-library-only（仅标准库）函数式后端
- [x] AC-V2-EVIDENCE-004（live blackbox integration）— 由 V2-090E 证明：真实启动 backend/frontend（后端/前端），通过 HTTP 验证 CRUD、SQLite persistence（SQLite 持久化）和前端调用后端
- [x] AC-V2-EXECUTION-001 / AC-V2-EXECUTION-002 / AC-V2-EVIDENCE-002（atomic-agent 执行边界与来源链）— 由 V2-090G 证明：ExecutionPackage（执行包）可编译为 atomic-agent AgentInvocation（智能体调用），AgentRunResult（智能体运行结果）的 event stream / tool attempts / workspace mutations / artifacts（事件流 / 工具尝试 / 工作区变更 / 产物）可投影为 Boardroom evidence chain（证据链）输入；缺包、缺事件流、缺工作区变更、越权路径、越权命令或治理字段注入均 fail closed（失败关闭）
- [x] AC-V2-EXECUTION-001 / AC-V2-EXECUTION-002 / AC-V2-EVIDENCE-001 / AC-V2-EVIDENCE-002（atomic-agent 主执行路径）— 由 V2-090H 证明：implementation ticket（实施任务）不再由 `ProviderExecutor`（模型供应商执行器）单次 LLM request（大模型请求）冒充 agent work（智能体工作），而是通过真实 provider-backed atomic-agent executor（模型供应商支撑的原子智能体执行器）产生 event stream（事件流）、workspace mutation（工作区变更）、command evidence（命令证据）和 source lineage input（源码来源链输入）
- [x] V2-090I：真实 provider-backed atomic-agent executor（模型供应商支撑原子智能体执行器）可在 reset workspace（重置工作区）中完成中等复杂多文件 Python package/CLI（Python 包/命令行工具），并产生 command evidence（命令证据）、workspace mutation（工作区变更）和 source lineage input（源码来源链输入）— 2026-06-11 在 V2-090J action protocol repair（原子动作协议修复）后复跑通过：pytest gate `1 passed in 222.99s`，独立 runner `boardroom-atomic.v2-090i.medium.20260611T160350Z.9f07d150` 包含 10 个 provider turns（模型轮次）、9 条 workspace mutations、`cmd.check-medium-scenario` command evidence 最终 exit 0、5 条 source lineage inputs 和 `run.completed`
- [x] V2-090J：atomic-agent action protocol repair（原子动作协议修复）后，真实 provider-backed executor 可通过显式 `AgentActionBatch`（智能体动作批次）或等价 provider-native structured output（供应商原生结构化输出）完成中等复杂多文件任务，并保留 command evidence / workspace mutation / source lineage / provider turn facts 硬门禁 — 初次由 `boardroom-atomic.v2-090j.medium.20260610T193727Z.f00e1709` 证明；2026-06-11 复跑由 `boardroom-atomic.v2-090j.medium.20260611T055454Z.016a2a2a`（pytest gate，`1 passed in 505.05s`）和 `boardroom-atomic.v2-090j.medium.20260611T060341Z.b564b20d`（runner report，8 个 provider turns、11 个 workspace mutations、6 次 `cmd.check-medium-scenario` command evidence，最终 exit 0，`run.completed`）再次证明
- [x] V2-090K：Agent team autonomy remediation（智能体团队自治整改）— 按 `docs/superpowers/specs/2026-06-12-v2-090k-agent-team-autonomy-remediation-design.md` 和 `docs/superpowers/plans/2026-06-12-v2-090k-agent-team-autonomy-remediation.md` 移除 V2-090F first run（首次运行）中的固定源码布局、固定启动命令、固定环境变量名、固定五票任务图、runner-owned `/books` 业务行为探针、`AC-V2-090F-*` 静态验收引用、`app/` / `static/` 路径前缀源码面映射和 helper-written checker/closeout verdict（辅助器写检查/收尾结论）；由角色提示词强化 DevOps/Release（运维/发布）职责，由 AcceptanceContract（验收合同）/PackageContract（包合同）/RunManifest（运行清单）/BehavioralProbePlan（行为探针计划）承载可启动、可验证、可审计合同，并要求 Checker/Closeout（检查/收尾）各自产生 ProviderAttempt（模型调用尝试记录）。090K 通过标准允许真实 provider full run fail closed（失败关闭）并输出结构化失败现场；它不要求 single-pass full run passed（单轮完整运行通过）
- [ ] AC-V2-PACKAGE-001 / AC-V2-CLOSEOUT-001~003 / AC-V2-CLOSEOUT-011（package + closeout + audit）— 由 V2-090F 证明：按 `docs/superpowers/specs/2026-06-12-v2-090f-atomic-golden-sample-rebuild-design.md` 和 `docs/superpowers/plans/2026-06-12-v2-090f-atomic-golden-sample-rebuild.md` 从 short PRD（简短产品需求）触发 agent team autonomous delivery（智能体团队自治交付），只有多角色上下文、implementation evidence（实施证据）、黑盒证据和 audit bundles（审计包）齐全时 CloseoutPackage（收尾包）passed

> V2-090I 的 2026-06-10 三次失败保留为 pre-repair failure evidence（修复前失败证据）：当时真实 provider run 未完成中等复杂多文件任务，暴露 action protocol（动作协议）、tool policy（工具策略）和 validator checkpoint（验证命令检查点）问题。V2-090J 已完成 action protocol repair（原子动作协议修复）和真实 provider proving（证明运行）；2026-06-11 V2-090I 原 runner 复跑通过，证明修复后 executor path（执行路径）可完成同一中等复杂任务。
> 2026-06-12：V2-090H、V2-090I 与 V2-090J 前置专家评审已通过，但旧 V2-090F 文档/代码因 provider lock（模型产物锁）、单次 JSON source delivery（源码交付）、固定三票监督实施和 atomic-agent（原子智能体）接口改造而腐化。当前只完成 V2-090F PRD-to-delivery agent team spec/plan（从 PRD 到交付的智能体团队规格/计划）修订与自审，尚未恢复实施，故本 checkbox 保持未勾选。
> 2026-06-12 补充：V2-090F first run（首次运行）真实 provider worker implementation chain（工人实施链路）已通过一次，且用户人工验证基础功能可用；但专家评审确认 planning prompt（规划提示词）、ticket graph validator（任务图校验器）和 closeout helper（收尾辅助器）存在外部介入，不能判定 agent team autonomy（智能体团队自治）成立。V2-090K 必须先完成整改并重跑真实 provider full test（完整真实模型测试）；若重跑 fail closed 并暴露 agent-generated contract / implementation / probe（智能体生成合同 / 实现 / 探针）不一致，则该失败进入 V2-100 返工循环，不再倒推 090K 未完成。
> 2026-06-12 修订：V2-090K 范围已扩展为同时消除 runtime（运行时）对业务域和证据权威源的硬编码认知。BehavioralProbePlan（行为探针计划）必须由 Tester/Release DevOps（测试/发布运维）声明，且执行器必须定义 capture（捕获）、`${}` interpolation（占位符替换）和 `json_equals` / `json_contains` / `field_equals` / `field_absent` 断言语义。Agent JSON artifact（智能体 JSON 产物）进入 closeout（收尾）前必须强类型解析为 AcceptanceContract（验收合同）、PackageContract（包合同）、RunManifest（运行清单）和 SourceLineageRecord（源码来源链记录），通过 validate_contract_gate（合同门禁校验），再由现有 FinalEvidenceTableBuilder（最终证据表构建器）和 build_source_inventory（源码清单构建器）生成证据；不得用 dict-only（仅字典）平行 helper（辅助器）替代。
> 2026-06-13 修订：V2-090K 已完成“去外力介入 + 合同权威源 + fail-closed 现场”目标。真实 provider full run 产生的失败现场已归档到 `examples/generated-workspaces/tiny-fullstack/30-audit/v2-090k-failure-snapshot/`，包含行为探针响应 shape（形状）错配、环境变量绑定未收敛、最终证据表旧 AC 引用和 closeout/audit 旧 run 引用。该现场是 V2-100 输入；V2-090F golden sample 仍保持未勾选。
> 2026-06-16 修订：V2-100E 已完成多轮返工 proving（证明）。V2-090F 下一步不先补大规模 orchestration glue（编排胶水），而是按 `doc/04-implementation/v2-090f-rerun-rework-entry-validation-spec.md` 执行真实 rerun rework-entry validation（重跑返工入口验证）：无阻断时按原样 closeout candidate（收尾候选）复判；有阻断时必须形成 verified blocker（已验证阻塞项）、ReworkRequest（返工请求）、TicketGraphPatch（工单图补丁），并导出 TicketGraph before/after（工单图更新前后）证据。该复判完成前，V2-090F checkbox 继续保持未勾选。

#### 本批产出

- RolePromptHook（角色提示词钩子）基础设施与角色职责基线
- Closeout all-command coverage（收尾全命令覆盖）门禁
- ServiceRunEvidence（服务运行证据）或等价服务探针模型
- 修正后的 tiny-fullstack AcceptanceContract（验收合同）与 PackageContract（包合同）
- live blackbox integration（真实黑盒集成）证明套件
- Atomic-agent package/import integration（原子智能体包导入集成）防腐层、调用编译器、结果校验器与投影器
- Atomic-agent executor switch（原子智能体执行器切换）主执行路径与最小 atomic implementation ticket（原子实施任务）证明
- Resettable medium implementation scenario（可重置中等复杂实施场景）runner（运行器）、非 provider 测试、三次历史阻塞证据与修复后真实 provider 通过证据
- Atomic action protocol repair（原子动作协议修复）spec/plan（规范/计划）、runner/proving 产物与真实 provider event stream（模型供应商事件流）证据
- Agent team autonomy remediation（智能体团队自治整改）spec/plan（规范/计划），用于消除 V2-090F first run 的 runner/prompt/validator/helper 介入、业务域行为探针硬编码和验收/源码面第二权威源
- V2-090K curated failure snapshot（精选失败快照）：`examples/generated-workspaces/tiny-fullstack/30-audit/v2-090k-failure-snapshot/`，用于后续 V2-100 返工循环 proving（证明）
- V2-090F rerun rework-entry validation spec（重跑返工入口验证规格）：`doc/04-implementation/v2-090f-rerun-rework-entry-validation-spec.md`
- V2-090F rerun rework-entry validation implementation plan（重跑返工入口验证实施计划）：`doc/04-implementation/v2-090f-rerun-rework-entry-validation-implementation-plan.md`，当前等待评审后再实施
- 待 V2-090F 实施生成的 `examples/generated-workspaces/tiny-fullstack/` PRD-to-delivery agent team golden sample（从 PRD 到交付的智能体团队黄金样例）

> 当前 `examples/generated-workspaces/tiny-fullstack/` 仍不得被当作 V2-090F passed golden sample（通过黄金样例）。已完成的 V2-090A~E、V2-090G~K 证明提示词钩子、命令覆盖、服务运行证据、合同整改、真实黑盒集成基础能力、atomic-agent 执行边界、中等复杂实施能力、action protocol repair（动作协议修复）和 agent team autonomy remediation（智能体团队自治整改）；尚未证明 tiny-fullstack golden sample 已经通过 CEO-governed rework loop（项目经理治理返工循环）收敛到完整 package/closeout/audit（包/收尾/审计）验收。

#### 进入下一阶段前置

- [x] V2-090A~E、V2-090G、V2-090H、V2-090I、V2-090J、V2-090K 已 DONE（专家评审已确认 agent team 基础能力和 090K 自治整改可进入 V2-100 返工循环证明；V2-090F golden sample 仍需 V2-100 后复判）
- [x] 当前 V2-080 failure package（失败包）作为 regression negative（回归负例）被 CloseoutGate 阻断
- [x] V2-090K 已移除固定运行接口、业务域探针、静态验收/源码面第二权威源、dict-only 契约/证据平行链路和 helper-written checker/closeout；真实 provider full run fail closed 现场已保留为 V2-100 输入
- [ ] V2-090F rerun rework-entry validation（重跑返工入口验证）已真实执行，并产出无阻断 closeout candidate 或 verified blocker -> ReworkRequest -> TicketGraphPatch -> before/after graph（已验证阻塞项 -> 返工请求 -> 工单图补丁 -> 更新前后图）证据
- [ ] V2-090F golden sample（黄金样例）中每个 declared run/test command 均有 final evidence
- [x] backend/frontend 均有 startup/readiness evidence
- [x] HTTP CRUD、delete book（删除图书）、SQLite persistence 和 frontend-to-backend live probe 均通过
- [ ] golden sample 可 clean rebuild（干净重建）且 `--check` 稳定通过

> V2-090B 勾选的是 CloseoutGate（收尾门禁）已强制 declared command evidence requirement（声明命令证据要求）；当前 V2-080 failure package（失败包）仍缺 `run-backend` / `run-frontend` final evidence（最终证据），因此 golden sample（黄金样例）证据齐全前置项必须保持未勾选。
> V2-090F 实施完成前不得把 `scripts/build_tiny_closeout_sample.py --check`（构建脚本检查模式）、provider artifact lock（模型产物锁）、ProviderAttempt（模型调用尝试记录）、`AgentRunResult.status == completed`（智能体运行完成）或 V2-090J 单元测试替身单独作为 agent team framework（智能体团队框架）端到端成立证据。
> V2-090F 也不得把 runner 预置的 backend/frontend/integration 固定 ticket graph（固定任务图）或所有角色共用 `seat.worker.implementation` 当作 agent team autonomy（智能体团队自治）证据。
> V2-090F 必须使用独立 high-budget config baseline（高预算配置基线），并将 runtime/providers/roles YAML hash、resolved budgets（解析后预算）、provider timeout（模型供应商超时）和 retry policy（重试策略）写入 `00-boardroom/v2-090f-baseline.json`；预算或超时不得通过 `.env` 临时调参绕过。
> V2-100 已完成后，V2-090F 的最终解阻条件是按 rerun rework-entry validation spec（重跑返工入口验证规格）重新证明 package + closeout + audit（包/收尾/审计）完整闭合；若出现阻断，必须证明阻断能进入 V2-100 返工循环并更新 TicketGraph（工单图），不能只停留在 raw exception（原始异常）或自由文本失败。

### Phase 10 验收 — V2-100 Agent-team Rework Loop Hardening

#### AC 检查清单

- [x] AC-V2-REWORK-001 / AC-V2-REWORK-002（返工循环由工单图治理，返工请求需要已验证阻塞项）— 由 V2-100A 证明：ReworkCycle（返工循环）、ReworkRequest（返工请求）、ReworkIssue（返工问题）、ReworkPlan（返工计划）、ReworkAttempt（返工尝试）和 ReworkOutcome（返工结果）均为强类型对象；缺 FinalEvidenceTable missing/failed row（最终证据表缺失/失败行）、CheckerVerdict blocker（检查结论阻塞项）或 CloseoutGate failure（收尾门禁失败）不得创建返工请求。
- [x] AC-V2-REWORK-001 / AC-V2-GRAPH-001 / AC-V2-GRAPH-002（返工状态由 TicketGraph 和 reducer 推进）— 由 V2-100B 证明：`REWORK_REQUESTED`、`REWORK_PLANNED`、`REWORK_TICKET_CREATED`、`REWORK_ATTEMPT_SUBMITTED`、`REWORK_REVIEWED`、`REWORK_ACCEPTED` 等事件只能按 reducer（归约器）规则推进；runtime/atomic-agent（运行时/原子智能体）不能直接提交 accepted/completed（接受/完成）。
- [x] AC-V2-REWORK-003 / AC-V2-AGENT-001（CEO 返工规划受合同和模型调用审计约束）— 由 V2-100C 证明：CEO（项目经理/治理角色）基于严格 schema（结构）的 BlockerReport（阻塞报告）/ ReworkRequest 生成 ReworkPlan 和 TicketGraphPatch（工单图补丁）；缺 CEO ProviderAttempt（模型调用尝试记录）、缺 blocker_refs（阻塞引用）映射、决策不在 `fix_implementation` / `fix_contract_or_probe` / `split_ticket` / `reorder_dependencies` / `escalate_human_review` 枚举内、绕过 active contract（活跃合同）或要求 runtime 自动修复均 fail closed。
- [x] AC-V2-REWORK-004 / AC-V2-EVIDENCE-002 / AC-V2-CHECKER-001（返工每轮重新进入证据和检查门禁）— 由 V2-100D 证明：ReworkAttempt 产物必须重新构造 SourceInventory（源码清单）、FinalEvidenceTable（最终证据表）、CheckerVerdict（检查结论）和必要 CloseoutGateResult（收尾门禁结果）；旧 FinalEvidenceTable（最终证据表）、旧 RunManifest（运行清单）、旧 SourceInventory（源码清单）、旧 CheckerVerdict（检查结论）或旧 CloseoutPackage passed（收尾通过包）不得跨轮次复用。
- [x] AC-V2-REWORK-005 / AC-V2-CLOSEOUT-001~003 / AC-V2-CLOSEOUT-011（多轮返工可审计收敛或升级）— 由 V2-100E 证明：090K 真实失败快照和一个可重置 failing fixture（失败夹具）都能被转化为结构化 blocker，CEO 自治规划返工，worker/tester/release-devops（实施/测试/发布运维）执行返工，checker/closeout（检查/收尾）重验；成功时 closeout passed（收尾通过），失败耗尽时生成 escalation/termination decision（升级/终止决策）。
- [ ] AC-V2-REWORK-006 / AC-V2-EVIDENCE-004 / AC-V2-CLOSEOUT-011（运行清单摄取把不确定性转成自治测试与返工上下文）— 待 V2-100F 证明：未知或变体 RunManifest assertion type（运行清单断言类型）不再 raw crash、不被忽略、不允许 closeout passed；CEO 通过 TicketGraph / SeatDemand（工单图 / 席位需求）派给 verify-blackbox ticket（黑盒验证工单）的 AgentSeat（智能体席位）读取 RunManifest、PackageContract、AcceptanceContract、项目文档和源码引用后生成 provider-backed BlackboxVerificationPlan（模型支撑黑盒验证计划）；runner 只执行该计划并记录真实 command / HTTP / browser / tool facts（命令 / HTTP / 浏览器 / 工具事实）；Checker / Closeout 把失败投影为结构化 ReworkIssue（返工问题）或升级。

> Phase 10 的核心负例是“命令通过但证明命题错误”：`AgentRunResult.status == completed`（智能体运行完成）、ProviderAttempt（模型调用尝试记录）、`--check`、一次 live probe（真实探针）或 CRUD 可用，都不能单独推出 CloseoutPackage.passed（收尾包通过）。系统必须拒绝 runner/helper（运行器/辅助器）代替 agent team（智能体团队）自治规划、检查和收尾的交付。
> PRD（产品需求文档）明确要求的业务行为不算硬编码；问题在于 runner 不得内置业务探针。BehavioralProbePlan（行为探针计划）和 RunManifest（运行清单）可以声明 `/api/books` 等路径，但声明必须来自 agent-generated contract（智能体生成合同）并通过强类型 gate（门禁）。

#### 本批产出

- ReworkCycle / ReworkRequest / ReworkIssue / ReworkPlan / ReworkAttempt / ReworkOutcome（返工循环/请求/问题/计划/尝试/结果）模型
  - V2-100A 已产出：`src/boardroom_os/rework/model.py`、`src/boardroom_os/rework/blocker_projection.py`、`tests/rework/test_rework_model.py`、`tests/rework/test_v2_090k_failure_snapshot_projection.py`、`tests/negative/test_rework_model_fail_closed.py`
- Rework event taxonomy（返工事件分类）与 reducer（归约器）门禁
- CEO rework planner boundary（项目经理返工规划边界）和 TicketGraphPatch（工单图补丁）模型
- Rework evidence/checker reintegration（返工证据/检查重接入）
- Multi-round rework proving scenario（多轮返工证明场景）和 process audit/replay（流程审计/重放）证据
- Resettable failing fixture（可重置失败夹具），从 090K failure taxonomy（失败分类）抽象而来，避免端到端证明只依赖不可重置的真实 provider 现场
- RunManifest tolerant ingestion（运行清单宽容摄取）与 agent-owned blackbox verification（智能体拥有的黑盒验证）spec：`doc/04-implementation/v2-100f-manifest-tolerant-ingestion-rework-entry-spec.md`

#### 进入下一阶段前置

- [ ] V2-100A ~ V2-100F 状态全部 DONE（当前 V2-100F REVIEW_REQUIRED，等待专家评审）
- [ ] `backlog.md` 进度总览 Phase 10 显示 6 / 6（当前 5 / 6）
- [x] 返工循环负例覆盖无 blocker 返工、runtime 直接关闭、旧 evidence 复用、越权写入、无限循环和 helper-written verdict（辅助器写结论）
- [x] 多轮返工 proving scenario（证明场景）同时消费 090K curated failure snapshot（精选失败快照）和 resettable failing fixture（可重置失败夹具），并在真实 provider opt-in（真实模型供应商显式启用）下产出完整 event/evidence/audit（事件/证据/审计）链
- [x] `doc/05-project-log/2026-06.md` 或对应月份日志记录 V2-100 完成证据
