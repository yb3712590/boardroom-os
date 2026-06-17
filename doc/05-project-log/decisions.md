# Decisions

## DEC-0001: V2 采用 clean foundation 路线

- 状态：Accepted
- 日期：2026-05-13

### 决策

V2 不在旧实现主链上做瘦身重构。采用干净分支和新文档基座，旧 git 历史只作为归档教训。

### 理由

旧主链失败来自架构权力倒挂：runtime 可制造伪 source /伪 verification / workflow completion，治理、证据和 closeout 在事后才暴露问题。继续整理旧代码会污染上下文并降低性价比。

## DEC-0002: 旧实现 abandoned by default

- 状态：Accepted
- 日期：2026-05-13

### 决策

旧实现默认废弃。除用户明确要求 forensic lookup 外，不读取、不迁移、不整理旧实现。

### 理由

V2 需要避免从旧 runtime、旧 tests、旧 docs 中继承伪成功语义。

## DEC-0003: 新代码进入 `src/boardroom_os/`

- 状态：Accepted
- 日期：2026-05-13

### 决策

V2 后续实现进入新命名空间 `src/boardroom_os/`。

### 理由

需要从路径上切断与旧 `backend/app/core` 主链的耦合。

## DEC-0004: Contract-first and reducer-first

- 状态：Accepted
- 日期：2026-05-13

### 决策

没有 active contract 不写 implementation 主路径；关键状态变更必须通过 reducer。

### 理由

防止 runtime 或 executor 再次越权决定项目完成。

## DEC-0005: Negative tests first

- 状态：Accepted
- 日期：2026-05-13

### 决策

先写防伪成功负例测试，再写 happy path。

### 理由

旧系统的失败之一是测试保护了 fallback success。V2 必须反向设计测试激励。

## DEC-0006: Provider-backed implementation evidence is mandatory

- 状态：Accepted
- 日期：2026-05-13

### 决策

Provider-required implementation ticket 必须有 provider attempt。attempt count 为 0 必须失败。

### 理由

没有 provider attempt 的 implementation success 无法证明 agent team 真实实施。

## DEC-0007: Generated project package is final output

- 状态：Accepted
- 日期：2026-05-13

### 决策

最终交付物是 generated project package，而不是离散 source artifact。

### 理由

用户期望的是一个一致、可运行、可审计的目标项目包。

## DEC-0008: Backlog 工作包化 + 分批验收 + 幂等更新协议

- 状态：Accepted
- 日期：2026-05-14

### 决策

1. `doc/04-implementation/backlog.md` 从 8 个阶段索引扩展为 51 个可执行工作包（V2-000 ~ V2-080F）。每个工作包必须具备 ID / 状态 / 目标 / 输入 / 依赖 / 输出 / negative tests / happy path / 验收口径。
2. 在 backlog.md 顶部新增"实施幂等性 / 工作包完成更新协议"段，强制规定工作包完成后必须按序更新的文档清单（backlog 状态、acceptance-criteria checkbox、月度日志、必要时 decisions.md、必要时 INDEX.md），并定义 Pre-flight 一致性检查和幂等保证。
3. 在 `doc/04-implementation/acceptance-criteria.md` 新增"分批验收"层：每个 phase 列出 AC checkbox（绑定到 AC-V2-XXX 抽象 AC 和具体 negative / happy test）、产出清单和进入下一 Phase 前置。原有 AC-V2-XXX 抽象原则段保留为 source of truth。
4. 显式补齐 `BoardDirective`（V2-010B）和 `MethodologyProfile`（V2-010F）两个工作包，闭合合同链入口和方法论选择。
5. 显式扩展 V2-070C，把 `30-audit/` 的 10 项产物拆为逐项 negative test。

### 理由

- **幂等性**：每次会话的启动提示词都接近，模型必须能从文档自身推导出"完成后改哪些文件"。原 backlog 仅在启动顺序中模糊提到"完成后更新本文件、相关 INDEX、必要验收文件和项目日志"，不具备可重复执行的协议性。补齐协议后，跨会话项目状态可保持全局一致。
- **可验收性**：原 acceptance-criteria.md 全是抽象原则，人类无法用它做批次验收。分批验收 + checkbox + 产出清单让人能逐 phase 审查。
- **架构完整性**：BoardDirective 是 domain-model.md 合同链的第一环，MethodologyProfile 是 agent-team-model.md / generated-project-workspace.md 显式声明的核心对象，原 backlog 漏掉这两项会在 V2-080 fixture 阶段补丁式补回，破坏 contract-first 的纯度。
- **process audit 可验证性**：30-audit 10 项产物分别承担不同审计能力，单一测试无法覆盖。逐项负例让缺失不可被静默吞掉。

### 影响

- 工作包总数 49 → 51；Phase 1 工作包数 5 → 7。
- 后续所有工作包完成时必须遵循 Pre-flight + 完成更新协议；不遵循即视为 drift。
- 后续 phase gate 由 acceptance-criteria.md 中的 checkbox 决定，不由 backlog 状态字段独立决定。

## DEC-0009: Contract value objects 采用 Pydantic-first

- 状态：Accepted
- 日期：2026-05-14

### 决策

V2 的合同、schema、领域边界值对象从 V2-010A 开始直接采用 Pydantic model（Pydantic 模型）和 fail-closed 校验，不先引入 dataclass / 裸 dict 过渡版本，也不保留兼容 shim 或 fallback 路径。

### 理由

项目已经经历多次重构，继续保留临时兼容层会积累新的坑。如果最终目标是 Pydantic model，就应从合同内核起步阶段按最终标准实现。

### 影响

- 后续 V2-010B ~ V2-010G 的合同对象应复用 V2-010A 的 Pydantic 值对象。
- 后续 schema 不应为了兼容旧表达而接受裸 dict 作为核心字段语义来源。
- 需要新增依赖配置时，应显式声明 Pydantic 作为项目标准依赖，而不是测试环境偶然依赖。

## DEC-0010: EventType 采用阶段性收窄定义

- 状态：Accepted
- 日期：2026-05-15

### 决策

V2-020A 只定义 Phase 2 和 runtime boundary（运行时边界）已经明确需要的 ticket / execution 事实事件类型，不一次性枚举 Phase 3 ~ Phase 8 的完整 event taxonomy（事件分类）。后续工作包在实际引入 provider、evidence、workspace、closeout、replay 等事实时，必须同步扩展 `EventType`（事件类型）枚举和对应 fail-closed 测试。

### 理由

EventRecord（事件记录）的职责是先稳定 event log（事件日志）可审计、可回放的 envelope（外壳字段）和序列化语义；提前替后续阶段定义所有事件会把尚未实现的业务边界固化为猜测，增加后续调整成本。

### 影响

- V2-020B 的 event log append（事件追加）仍必须拒绝 unknown event_type（未知事件类型）。
- 后续阶段扩展 EventType 时必须同时补测试和项目日志，不能依赖任意字符串绕过 fail closed。
- stable dump（稳定转储）保持 Pydantic value object（Pydantic 值对象）形态，确保可直接回放为 EventRecord。

## DEC-0011: Phase 2 审计延期项绑定到后续工作包

- 状态：Accepted
- 日期：2026-05-16

### 决策

Phase 2 审计中发现的非 P2 修补项不在 V2-020 继续扩张实现，而是绑定到后续工作包：seat lifecycle（席位生命周期）事件流与 capability registry（能力标签注册表）进入 V2-030A/B；role-aware completion boundary（按角色感知的完成边界）进入 V2-040E；governance/human/evidence/checker/closeout event taxonomy（治理/人审/证据/检查/收尾事件分类）按 V2-030/V2-050/V2-070 实际消费时扩展；TicketStatus（任务状态）中间态细化或 raw event timeline（原始事件时间线）设计选择从 V2-030 起显式化；event log hash chain（事件日志哈希链）与 replay bundle（重放包）进入 V2-070B。

### 理由

这些能力需要 RoleProfile（角色模板）、AgentSeat（智能体席位）、ModelExecutionProfile（模型执行配置）、EvidenceVerifier（证据验证器）、CheckerVerdict（检查结论）或 CloseoutPackage（收尾包）成为可信输入后才能正确建模。若在 Phase 2 提前补齐，会把尚未实现的业务边界固化为猜测，并违反 DEC-0010 的阶段性收窄原则。Phase 2 只立即修补 reducer/kernel 层已可独立证明的 P2 缺口：依赖环 fail closed，以及 completion 前必须存在 `WORK_PRODUCT_SUBMITTED`（工作产物提交）事实。

### 影响

- V2-030A/B 必须让 active seats（活跃席位）可由事件或策略投影审计，不能长期依赖构造器注入的 `SeatDefinition` 快照。
- V2-040E 必须用 RoleProfile / AgentSeat 信息替代 `actor_ref` 字符串前缀作为 runtime/executor 越权判断依据。
- V2-050F 必须把正式 FinalEvidenceTable / CheckerVerdict 接入现有 completion boundary，不绕过 `WORK_PRODUCT_SUBMITTED` 和 provider attempt 门禁。
- V2-070B/F 若引入增量 reducer 或 replay bundle，必须把 work product 历史事实纳入显式 projection/replay 输入，不能依赖 `TicketReducer.reduce()` 调用内局部集合。

## DEC-0012: Agent asset 导入放在 workspace/package 阶段

- 状态：Accepted
- 日期：2026-05-16

### 决策

外部提供的 role config（角色配置）、skill file（技能文件）、prompt file（提示词文件）和 MCP interface manifest（MCP 接口清单）不作为 ExecutionPackage compiler（执行包编译器）的运行时外部输入。V2-030D 必须保持 0 外部文件输入能力，只消费已编译 registry / contract / graph / seat assignment。外部 agent assets（智能体资产）导入追加为 V2-060F，在 generated project workspace（生成项目工作区）阶段物化为 `00-boardroom/agents/` 快照，并写入 `asset-import-manifest.yaml` 来源链。

### 理由

执行包编译器是 runtime 前的治理编译边界，若在此阶段同步外部文件，会让执行包可重复性依赖项目外状态。把导入放到 workspace/package 阶段，可以让最终 generated project package 自包含、可审计、可 hash，并避免外部资产静默变化影响已编译执行包。

### 影响

- V2-030D 不读取外部 skill/prompt/MCP 文件；缺外部资产时仍应可用内存 registry fixture 编译 ExecutionPackage。
- V2-060F 负责将外部 agent asset bundle 导入 `00-boardroom/agents/`，并记录 source_ref/source_kind/imported_at/source_path/target_path/sha256。
- 既有项目更新 agent assets 必须产生新 ref 或显式 import manifest 记录，不能静默覆盖。

## DEC-0013: Agent team governance projection must be orchestrated before compilation

- 状态：Accepted
- 日期：2026-05-17

### 决策

V2-030D 在实现 ExecutionPackage compiler（执行包编译器）前，必须引入 AgentTeamProjector（智能体团队投影器）或等价单一编排入口。该入口按 graph_version（图版本）交织消费 RoleProfile change facts（角色模板变更事实）与 Seat lifecycle facts（席位生命周期事实），产出当前 RoleProfileProjection（角色模板投影）、SeatLifecycleProjection（席位生命周期投影）和 active seats（活跃席位）供 assignment（派工）与 compiler 消费。

ExecutionPackage compiler 不得直接分别调用 `RoleProfileProjection.apply_changes` 与 `SeatLifecycleProjector.project` 后自行拼接治理状态。

### 理由

V2-030B 已证明 RoleProfile（角色模板）与 AgentSeat（智能体席位）彼此校验：seat lifecycle 需要 role profile，非 bootstrap role registration 又需要 active governance seat。若调用者自行组合两个 projector，会在 CEO 替换、席位停用、后续 role 注册等交织事件中使用错误时间点的 active seat 快照。

### 影响

- V2-030D 的输入应是编排后的 agent team projection（智能体团队投影），不是多个半成品 projector 的松散组合。
- V2-070 branchable governance replay（可分叉治理重放）可以复用同一编排入口，避免 replay 与 compiler 形成两套治理解释。
- `SeatPolicy.match`（席位策略匹配）保留为 demand-first seat discovery（需求优先席位发现）API，但新增逻辑应等到 V2-030D 有真实消费者后再扩展。

## DEC-0014: TEST_ONLY_SIMULATION 不能作为 fallback evidence 例外

- 状态：Accepted
- 日期：2026-05-17

### 决策

V2-030E 不保留 `TEST_ONLY_SIMULATION`（测试环境模拟）可在“测试明确验证失败路径”时满足 evidence（证据）的例外。`TEST_ONLY_SIMULATION` 与 `PROVIDER_UNAVAILABLE`（模型供应商不可用）、`DETERMINISTIC_GOVERNANCE_DRAFT`（确定性治理草案）一样，不能满足 implementation evidence（实施证据）、diagnostic evidence（诊断证据）或 deterministic evidence（确定性证据）。

### 理由

上一版系统失败的核心风险之一是 fallback kind（降级类型）本身隐式承载了成功语义。failure-path validation（失败路径验证）必须通过 contract-declared deterministic transform（合同声明的确定性转换）显式表达，并受 `RequiredArtifactType`（必需产物类型）与 `AcceptanceRef`（验收引用）scope（作用域）约束。

### 影响

- `TEST_ONLY_SIMULATION` 只能作为测试环境中的场景标签，不具备证据资格。
- V2-050 `EvidenceVerifier`（证据验证器）处理 fallback artifact（降级产物）时，必须先解析 `fallback_policy_ref`（降级策略引用）得到 `FallbackPolicy`（降级策略）并调用 `evaluate_fallback_evidence`（降级证据判定函数）；若 registry（注册表）尚未提供可解析 policy，必须 fail closed（失败关闭）。
- V2-040A ProviderAttempt（模型调用尝试记录）与 V2-040C WorkProduct（工作产物）必须携带 typed fallback marker（类型化降级标记）或等价 outcome（结果）字段；缺 marker 时，V2-050 不得把任何 fallback artifact 转为 verified evidence（已验证证据）。
- V2-050A EvidenceClaim（证据声明）或 EvidenceObligation（证据义务）必须携带 expected_purpose（预期证据用途），verifier 不得自由选择 EvidencePurpose（证据用途）。
- 每个 fallback work product 必须以其完整 acceptance_refs（验收引用）一次性调用 `evaluate_fallback_evidence`，禁止按单个 acceptance_ref 拆分调用规避 scope（作用域）校验。
- `TOOLING_PREFLIGHT`（工具预检）即使满足 diagnostic evidence（诊断证据），也不得计入 FinalEvidenceTable（最终证据表）的 blocking criteria（阻塞验收项）。
- V2-050F completion gate（完成门禁）必须阻断任何关联 allowed=False fallback decision 的 evidence；V2-070C process audit（流程审计）必须能追踪 fallback decision lineage（降级判定来源链）。

## DEC-0015: WorkspaceManifest 采用严格固定四区

- 状态：Accepted
- 日期：2026-05-22

### 决策

WorkspaceManifest（工作区清单）第一版只接受 durable/auditable（可持久/可审计）四区：`00-boardroom` / `10-project` / `20-evidence` / `30-audit`。排除 build cache（构建缓存）、secrets/credentials（密钥/凭据）和 runtime scratch（运行时临时区）；PackageContract.package_root（包合同项目根）必须固定绑定 `10-project`。

### 理由

固定四区可保证 generated project workspace（生成项目工作区）边界清晰、可审计、可重放，并避免把 workspace layout（工作区布局）误作 Boardroom OS V2 框架 repo layout（仓库布局）。

### 影响

- V2-060B/C/E/F 通过 manifest（清单）读取 canonical roots（规范根路径）。
- 临时缓存和密钥只能作为外部引用或显式排除，不进入 WorkspaceManifest contract（工作区清单合同）。

## DEC-0016: V2-070G 不视为 V2-070 阶段闭合；启动 V2-071 fact-chain hardening

- 状态：Accepted
- 日期：2026-05-25

### 决策

V2-070A~G 已实施完毕，但 2026-05-25 外部独立审计（详见 `doc/04-implementation/v2-070-batch-review-report.md`）在代码层验证后识别出 18 项 P0/P1/P2 缺口，主要集中在事实链结构（ProcessAudit 与 CloseoutPackage 构造环、ReplayBundle 接受外部 ProjectionReplaySummary 形成第二事实源、ProcessAudit events 与 ReplayBundle.events 缺少内容级一致性校验）、隐式 fallback（GitAuditAdapter `base_commit_sha` / `worktree_ref` 隐式 fallback、ProcessAudit `getattr(..., "unknown")` 占位）、边界越界（CloseoutPackage.graph_version 允许超过 ReplayBundle 已证明范围）、命名空间不足（`fact_set_id` / `artifact_ref` / `content_ref` 缺 project/run/hash 命名空间）和确定性哈希（多处 set 语义输入未 canonical sort）。

V2-070G 已补强 Closeout Closure 阶段失败封闭校验，但未覆盖上述结构性缺口。本次决策：

1. V2-070A~G 各工作包**保持 DONE 状态**，作为"各阶段独立交付"的依据；
2. V2-070 大阶段整体**不视为闭合**，Phase 7 整体进入"待重构"状态；
3. 在 V2-080 之前**新增 Phase 7.5 / V2-071 里程碑**（6 个工作包 V2-071A~F），专门负责 fact-chain hardening 重构与 18 项缺口闭合；
4. 不采用"逐项串行打补丁"，也不"推倒重写 V2-070"，而是按"事实链权威源 → ReplayBundle re-replay → ProcessAudit 解构构造环 → Git 审计强化 → CloseoutPackage 边界严格化 → 端到端 fail-closed 回归"分包推进；
5. V2-080A 的依赖追加 V2-071F；Phase 8 在 V2-071 闭合前不得启动。

### 理由

- **结构性问题不能用补丁解决**：ProcessAudit 与 CloseoutPackage 之间的构造环（ProcessAudit 要求 `CLOSEOUT_COMMITTED` 事件，而 CloseoutPackage 又要求 ProcessAuditBundle）需要重新设计构造顺序，单点修改会留下"测试可构造，真实流程不可构造"的隐患。
- **第二事实源是系统性风险**：ReplayBundle 接受外部 ProjectionReplaySummary 而不重新投影、ProcessAudit 接受独立 events 而不直接复用 ReplayBundle.events，会让伪造 projection 字段在不被检测的情况下进入持久审计产物。
- **CLAUDE.md hard rules 不可妥协**：GitAuditAdapter 的 `base_commit_sha or final_commit_sha` 直接违反 "No silent fallbacks"，必须删除而非保留兼容路径。
- **不全推倒重写的理由**：V2-070A~G 在 event_hash_chain、artifact manifest sha256、checked_refs 闭包、artifact format 校验等维度提供了大量正确资产，全部重做会浪费。
- **不纯补丁的理由**：补丁修完单点 fallback 后，原本依赖 fallback 通过的合成测试会大面积暴露上游流程不成立，最终仍需结构性重构，只是会被推迟到更糟的时间点。

### 影响

- `doc/04-implementation/backlog.md`：新增 Phase 7.5 / V2-071A~F 共 6 个工作包；TL;DR 当前未完成工作包改为 V2-071A；V2-080A 依赖追加 V2-071F；进度总览总数 53 → 59。
- `doc/04-implementation/acceptance-criteria.md`：Phase 7 验收段追加"重审说明"，明确 070A~F checkbox 保留勾选但 Phase 7 整体不闭合；新增 Phase 7.5 验收段；抽象 AC 层新增 AC-V2-CLOSEOUT-004 ~ 010。
- `doc/04-implementation/INDEX.md`：登记 6 份新 spec。
- 后续 V2-071A~F 实施完成后，本决策结合 V2-071F 的全量回归证据共同关闭 Phase 7。

## DEC-0017: V2-070 事实链单一权威源原则

- 状态：Accepted
- 日期：2026-05-25

### 决策

V2-070 大阶段的事实链必须遵循以下权威源原则，由 V2-071 阶段落地：

1. **EventLog 是事件事实的唯一权威源**。任何 audit / replay / closeout 产物对事件的引用必须通过 EventRecord 切片，不得通过其他对象重新声明事件内容。
2. **ReplayBundle 是 projection 事实的唯一权威源**。ReplayBundleBuilderInput 不再接受 `projection_summary` 字段；builder 内部必须调用 `ProjectionReplay.replay_events(...)` 从 events 重新投影 `ProjectionReplaySummary`，并以此为唯一 `summary_hash` 来源。
3. **ProcessAuditBundle 必须直接复用 `ReplayBundle.events`**，不接受独立 events 输入；ProcessAudit.events 与 ReplayBundle.events 在内容层（event_type / payload_refs / actor_ref 等）必须逐条一致。
4. **GitVersionAuditBundle 是 git facts 的唯一权威源**。GitAuditAdapter 的 base_commit_sha / worktree_ref / source_inventory_hash 必须显式传入；任何 fallback 必须 fail closed。
5. **CloseoutPackage 不重新提取 bundle 内部字段**。CloseoutPackage 通过 readiness summaries 与 bundle refs 形成绑定，但绑定校验必须经过 `assert_namespaced_ref_binding(...)` 与 `assert_checked_refs_cover(...)` 共享 helper，而不是各模块内部独立比较。
6. **构造顺序固定**：`EventLog → ReplayBundle → ProcessAuditBundle → GitVersionAuditBundle → CloseoutPackage → CLOSEOUT_COMMITTED 治理事件 → CloseoutReducer → CloseoutClosure`，不存在构造环。`CLOSEOUT_COMMITTED` 在 CloseoutPackage 构造完成后才能出现，ProcessAudit 不得要求该事件存在。

### 理由

外部审计报告显示，V2-070A~G 的实施在每个单点工作包上都满足"输入→输出"语义闭合，但在跨包视角下出现"测试可构造，真实流程不可构造"的合成路径。根因是缺少统一的事实链权威源原则——builder 输入接口允许调用方注入"看似与边界一致"的派生字段（projection_summary、独立 events、`base_commit_sha or final_commit_sha`），让伪事实可以在不修改 hash 链的前提下进入持久产物。一次性写明权威源原则比逐个工作包修补更稳健。

### 影响

- V2-071B：删除 `ReplayBundleBuilderInput.projection_summary` 字段，builder 内部重新投影。
- V2-071C：删除 `ProcessAuditBuilderInput.events` 字段，强制复用 `replay_bundle.events`；删除 ProcessAudit `_REQUIRED_TIMELINE_EVENT_KINDS` 中的 `closeout_committed`。
- V2-071D：删除 GitAuditAdapter 所有 `or fallback` 表达式。
- V2-071E：CloseoutPackage 引用绑定经过 V2-071A 命名空间 helper。
- 测试 fixture：所有依赖 V2-070 旧 builder input 形态的 fixture（包括 V2-070B/C/E/F 已提交的测试）必须同步迁移；本决策接受这部分回归成本。
- 后续阶段（V2-080 及之后）的 audit / closeout 消费者只能从 readiness summaries 与 CloseoutProjection 读取事实，不得直接读 CloseoutPackage / ReplayBundle 内部字段绕过权威源。

## DEC-0018: FinalEvidenceTable 按 evidence_required 完整覆盖判定完成

- 状态：Accepted
- 日期：2026-05-30

### 决策

FinalEvidenceTableBuilder（最终证据表构建器）判定 FinalEvidenceRow（最终证据行）为 `satisfied` 时，必须同时满足：

1. VerifiedEvidence（已验证证据）显式绑定该 blocking criterion（阻断性验收项）的 acceptance_ref（验收引用）；
2. 该 criterion 的每个 `evidence_required`（证据需求）都有对应 VerifiedEvidence.required_artifact_type（已验证证据必需产物类型）覆盖；
3. 同一 acceptance_ref 没有 FinalEvidenceBlocker（最终证据阻断项）。

若同一 acceptance_ref 只有部分 evidence（证据）覆盖，row 必须保持 `missing`，保留 `verified_evidence_refs`（已验证证据引用）用于 audit（审计），并通过 `missing_required_artifact_types`（缺失必需产物类型）列出尚未满足的 requirements（需求）。`CompletionGate`（完成门禁）和 closeout（收尾）只能消费所有 blocking rows 均 `satisfied` 的 FinalEvidenceTable（最终证据表）。

### 理由

V2-080D 首轮实现把 command evidence（命令证据）和 provider-backed work product claims（模型支持的工作产物声明）合并后提前构造出 complete FinalEvidenceTable，掩盖了 SourceInventory（源码清单）、run manifest（运行清单）、SQLite persistence evidence（SQLite 持久化证据）和 package assembly（项目包装配）仍未完成的事实。只检查 `acceptance_ref` 是否绑定会把“部分证据存在”误判为“阻断性验收项完成”，违反 evidence first（证据优先）和 fail closed（失败关闭）。

### 影响

- `doc/04-implementation/v2-050c-final-evidence-table-spec.md` 修订旧的 satisfied/missing 语义。
- `src/boardroom_os/evidence/table.py` 新增 `missing_required_artifact_types` 并按 required artifact coverage（必需产物覆盖率）判定 status。
- `src/boardroom_os/checker/checker.py` 接受 missing row 带有已验证 evidence refs，但要求明确列出缺失 artifact types。
- V2-080D 的验收口径改为“command evidence 可验证，但 FinalEvidenceTable incomplete 且 CompletionGate blocked”；V2-080E 才负责补齐 package/source/run/persistence evidence。

## DEC-0019: 撤回 V2-080 tiny-fullstack 端到端成立结论并启动 V2-090

- 状态：Accepted
- 日期：2026-05-31

### 决策

撤回 V2-080F “V2 最小端到端能力成立”的验收结论。V2-080A~F 保留 `DONE` 作为历史工作包执行记录，但 Phase 8 不再作为 minimal end-to-end（最小端到端）成立依据；当前 `examples/generated-workspaces/tiny-fullstack/` golden sample（黄金样例）降级为 V2-090 的 regression negative material（回归负例素材），直到黑盒证据重新闭合。

新增 Phase 9 / V2-090 Tiny Fullstack Blackbox Recovery（微型全栈黑盒整改），工作包顺序固定为：

1. V2-090A RolePromptHook（角色提示词钩子）；
2. V2-090B Closeout all-command coverage（收尾全命令覆盖）；
3. V2-090C ServiceRunEvidence（服务运行证据）；
4. V2-090D Tiny contract recovery（微型合同修复）；
5. V2-090E Live blackbox integration（真实黑盒集成）；
6. V2-090F Golden sample rebuild（黄金样例重建）。

RolePromptHook（角色提示词钩子）作为第一批整改进入 RoleProfile（角色模板）、ExecutionPackage（执行包）和 ProviderAttempt（模型调用尝试记录）审计链。它约束 CEO / Architect / Worker / Tester / Checker / Closeout 的基础行为边界，但不能替代 AcceptanceContract（验收合同）、PackageContract（包合同）、reducer（归约器）、EvidenceVerifier（证据验证器）或 CloseoutGate（收尾门禁）的程序化 fail-closed（失败关闭）校验。

### 理由

2026-05-31 两份 tiny-fullstack 失败复审报告显示，V2-080 的失败不是旧 runtime（运行时）直接合成 source / verification（源码 / 验证）的同类问题，而是“真实证据证明了错误命题”：

- `run-manifest.json` 声明 `run-backend` / `run-frontend`，但 `verification-runs.json` 只覆盖 `test-backend` / `test-integration`；
- backend package（后端包）声明 `python -m uvicorn backend.app:app`，但生成的 `backend/app.py` 没有 ASGI `app` 对象；
- frontend integration（前端集成）使用 fakeFetch（模拟 fetch）捕获 URL，不是 live HTTP integration（真实 HTTP 集成）；
- SQLite persistence（SQLite 持久化）仅由函数级测试证明，没有通过 HTTP 工作流证明；
- ProcessAuditBundle（流程审计包）、SourceInventory（源码清单）和 FinalEvidenceTable（最终证据表）证明 refs/hashes/artifacts（引用/哈希/产物）结构一致，但没有证明 generated package（生成包）按声明可启动、可运行、可集成。

同时，自治服务运行期间各角色只能从简短 PRD（产品需求文档）和上游产物派生后续提示词。V2-080 暴露出 Architect（架构师）缺少基础提示词约束：没有被明确要求检查 run command（运行命令）与 service boundary（服务边界）、provider prompt（模型提示词）与 package contract（包合同）、integration boundary（集成边界）与 evidence obligation（证据义务）的一致性。因此 V2-090A 必须先引入角色基础提示词 hook，再推进程序化门禁收紧。

### 影响

- `doc/04-implementation/backlog.md`：当前未完成工作包改为 V2-090A；Phase 8 标记为失败复审后结束；新增 Phase 9 / V2-090A~F；进度变为 59 / 65。
- `doc/04-implementation/acceptance-criteria.md`：Phase 8 端到端成立判定撤回；新增 Phase 9 验收段；新增 AC-V2-AGENT、AC-V2-EVIDENCE-004、AC-V2-PACKAGE-003、AC-V2-CLOSEOUT-011。
- `doc/04-implementation/INDEX.md`：登记两份复审报告和 V2-090 整改计划。
- V2-090 完成前，不得恢复“V2 最小端到端能力成立”结论。

## DEC-0020: Active RolePromptHook 必须哈希绑定并进入执行审计链

- 状态：Accepted
- 日期：2026-05-31

### 决策

CEO / Architect / Worker / Tester / Checker / Closeout 的 active RolePromptHook（角色提示词钩子）必须作为 governed asset（治理资产）管理。每个 active hook 必须具备唯一 `hook_ref`（钩子引用）、非空 `prompt_text`（提示词文本）、`hook_version`（钩子版本）、真实 `content_sha256`（内容哈希）、`policy_refs`（策略引用）和对应角色的 `required_responsibilities`（必备职责）。

RoleProfile（角色模板）必须显式引用 RolePromptHook 的 ref/version/hash；ExecutionPackage（执行包）必须携带 RolePromptHook snapshot（钩子快照）；ProviderRequest（模型请求）和 ProviderAttempt（模型调用尝试记录）必须携带同一组 hook 审计字段。ExecutionPackageCompiler（执行包编译器）只能消费已构造的 RolePromptHookRegistry（角色提示词钩子注册表），不得在编译时临时读取外部提示词文件。

CEO / Architect / Worker / Tester / Checker / Closeout 都是 provider-backed agent role（模型支撑的智能体角色）。任何 agent role 参与工作流时都应经 ExecutionPackage 接收上下文、接入 LLM（大模型）、记录 ProviderAttempt，并让返回结果进入后续治理或证据链。工具、validator（校验器）、reducer（归约器）和 gate（门禁）不代表 agent role。

RolePromptHook 不能替代 AcceptanceContract（验收合同）、PackageContract（包合同）、reducer（归约器）、EvidenceVerifier（证据验证器）或 CloseoutGate（收尾门禁）。任何声称绕过、替代或取代这些程序化门禁的 active hook 必须 fail closed（失败关闭）。

### 理由

V2-080 失败复审显示，系统虽然记录了真实证据，但 agent 角色缺少可审计的基础提示词职责边界，尤其是 Architect（架构师）未被明确要求检查 run command（运行命令）、service boundary（服务边界）、integration boundary（集成边界）和 evidence obligations（证据义务）的一致性。把基础提示词做成哈希绑定资产，可以让治理约束随 RoleProfile、ExecutionPackage 和 ProviderAttempt 进入审计链，同时仍保持程序化门禁为最终权威。

### 影响

- `src/boardroom_os/agents/role_prompt_hooks.py` 成为 active baseline hook registry（基准钩子注册表）的权威实现。
- `RoleProfileRegistry.from_profiles(...)` 必须接收 hook registry 并校验 ref/version/hash/category。
- `ExecutionPackageCompiler` 继续保持 0 外部文件输入，只消费 typed registry（类型化注册表）。
- `EvidenceVerifier` 对 provider-backed evidence（模型支撑证据）必须拒绝缺 hook 审计字段、hook ref/version/hash 无法由 RolePromptHookRegistry（角色提示词钩子注册表）验真，或 ProviderAttempt（模型调用尝试记录）与其 `input_package_ref` 对应 ExecutionPackage（执行包）RolePromptHook snapshot（角色提示词快照）不一致的记录。Verifier 不得按 RoleCategory（角色类别）推断 evidence（证据）权限。

## DEC-0021: ProviderAttempt 不是自主 agent work

- 状态：Accepted
- 日期：2026-06-03

### 决策

ProviderAttempt（模型调用尝试记录）只记录一次 provider request / response（模型供应商请求 / 响应）事实；它不能被当作 autonomous agent work（自主智能体工作）、agent loop completion（智能体循环完成）或 generated project package（生成项目包）已经被智能体实施完成的证明。

V2 必须引入显式 AgentWorkExecutor（智能体工作执行器）或等价 agent loop executor（智能体循环执行器）边界，才能宣称 agent team framework（智能体团队框架）完成实施闭环。该执行器至少必须：

1. 接收 ExecutionPackage（执行包）和 RolePromptHook snapshot（角色提示词快照）；
2. 在受控 workspace（工作区）内按 allowed read/write set（允许读写集合）读取和写入文件；
3. 调用 provider（模型供应商）并记录 ProviderAttempt（模型调用尝试记录）；
4. 调用受控 tool / command runner（工具 / 命令执行器）并记录 ToolAttempt / CommandEvidence（工具尝试 / 命令证据）；
5. 根据真实 command output（命令输出）多轮修复，直到产物提交或明确失败；
6. 把 WorkProduct（工作产物）、EvidenceClaim（证据声明）和失败事实交给 reducer（归约器）、validator（校验器）、EvidenceVerifier（证据验证器）和 CloseoutGate（收尾门禁），不得自行决定 ticket completed（任务完成）或 project completed（项目完成）。

LLM request timeout（大模型请求超时）必须与 agent task deadline（智能体任务期限）分离配置。`BOARDROOM_OPENAI_TIMEOUT_SECONDS` 只表示 provider request timeout（模型请求超时）；它不得被解释为 agent loop deadline（智能体循环期限）或任务完成门槛。后续 agent loop executor 应拥有独立配置项和审计字段来表达 task deadline / step deadline（任务期限 / 步骤期限）。

### 理由

V2-090F Golden sample rebuild（黄金样例重建）期间，真实 provider-backed source delivery（模型供应商支撑的源码交付）暴露当前系统只会对每个 implementation ticket（实施任务）发起一次 LLM request（大模型请求）并要求返回 JSON 文件内容。该路径不会自主读取 workspace（工作区）、写文件、运行 declared commands（声明命令）、观察失败、循环修复或归档 command evidence（命令证据）。把这类单次请求包装为“agent team 自治实施”会重复 V2-080 的错误：证据链看似完整，但证明的命题错误。

同一轮排查还显示，600 秒 timeout（超时）和 400000 context window（上下文窗口）是模型请求层配置问题，不是 agent 工作边界。单纯放大 timeout 不能补齐 agent loop executor（智能体循环执行器）缺口。

### 影响

- V2-090F 状态改为 BLOCKED（阻塞），Phase 9 保持 5 / 6；不得标记为 DONE（完成）。
- `examples/generated-workspaces/tiny-fullstack/` 在 V2-090F 解阻前不得被宣称为 passed golden sample（通过黄金样例）。
- `scripts/build_tiny_closeout_sample.py`（构建微型收尾样例脚本）的 provider-backed generation subprocess deadline（模型供应商生成子进程期限）只能作为临时执行保护，不是 agent task deadline（智能体任务期限）。
- `.env.example` / `.env.template` 记录 provider request timeout（模型请求超时）和 context window（上下文窗口）默认值，但后续必须新增独立 agent loop deadline（智能体循环期限）配置后才能实施 autonomous agent execution（自主智能体执行）。
- 后续工作包必须先补 AgentWorkExecutor（智能体工作执行器）/ agent loop executor（智能体循环执行器）等价边界；当前立项为 V2-090G，通过外部 atomic-agent（原子智能体）package/import 集成来提供受控 agent loop（智能体循环），再恢复 V2-090F golden sample rebuild（黄金样例重建）验收。

## DEC-0022: atomic-agent 以外部 Python package 接入 Boardroom OS

- 状态：Accepted
- 日期：2026-06-09

### 决策

V2-090G 采用外部 Python package import（Python 包导入）方式接入 `atomic-agent`（原子智能体）。Boardroom OS 不复制 atomic-agent 源码，不把 atomic-agent 封装为 HTTP/gRPC service（服务），也不把 atomic-agent examples CLI（示例命令行）当作稳定集成协议。

Boardroom OS 新增 `AtomicAgentPort`（原子智能体端口）/ `AtomicAgentPackageAdapter`（原子智能体包适配器）防腐层，只调用 atomic-agent 公开 `AgentRuntimePort.invoke(AgentInvocation) -> AgentRunResult`（智能体运行端口）边界。开发安装采用同级目录 checkout（检出）后执行 `python -m pip install -e ../atomic-agent`；运行和审计必须记录 atomic-agent package version（包版本）、source path（源码路径）或等价 provenance（来源）。

### 理由

V2-090F 证明 ProviderAttempt（模型调用尝试记录）不是自主 agent work（智能体工作）。atomic-agent 已经在独立项目中提供受控 agent loop（智能体循环）、tool dispatch（工具调度）、permission policy（权限策略）、event stream（事件流）和 workspace mutation（工作区变更）能力；直接复用其公开端口比在 Boardroom OS 内复制或重写执行循环更符合 no duplicate implementations（禁止重复实现）和 contract-first/evidence-first（合同优先/证据优先）原则。

### 影响

- V2-090G 成为 V2-090F 解阻前置。
- Boardroom OS 的 README 必须说明 atomic-agent 同级目录安装和 import 验证方式。
- `AgentRunResult.status == completed`（智能体运行完成）不得直接映射为 `TICKET_COMPLETED`（任务完成）或 `CloseoutPackage.passed`（收尾通过）。
- 缺 atomic-agent package、缺 event stream、缺 workspace mutation、越权 command/path 或返回治理字段时必须 fail closed（失败关闭）。

## DEC-0023: Agent-generated contracts 是 closeout 运行与证据权威源

- 状态：Accepted
- 日期：2026-06-12

### 决策

V2-090K 起，generated package（生成项目包）的可启动性、运行环境映射、readiness probe（就绪探针）和 frontend/backend topology（前后端拓扑）必须由 agent team（智能体团队）生成的 PackageContract（包合同）/ RunManifest（运行清单）声明。Runner（运行器）和 Closeout helper（收尾辅助器）不得把固定源码布局、固定模块名、固定启动命令或固定环境变量名作为 planning prompt（规划提示词）或 ticket graph validator（任务图校验器）的隐含成功条件。

Closeout runner（收尾运行器）只能消费 agent-generated RunManifest（智能体生成运行清单）来启动服务、绑定动态端口/临时 SQLite path（SQLite 路径）和执行 readiness/live probes（就绪/真实探针）。业务行为探针必须由 Tester / Release DevOps（测试 / 发布运维）生成的 BehavioralProbePlan（行为探针计划）或 RunManifest.behavioral_probes（运行清单行为探针）声明；runner 不得内置 `/books`、seed data（种子数据）、响应形状或 CRUD workflow（增删改查工作流）。缺 RunManifest service contract（运行清单服务合同）、缺 env binding（环境绑定）、缺 readiness probe（就绪探针）、缺 frontend/backend topology（前后端拓扑）、缺 behavioral probes（行为探针）或 RunManifest 与 PackageContract（包合同）不一致时必须 fail closed（失败关闭）。

FinalEvidenceTable（最终证据表）和 SourceInventory（源码清单）也必须消费 agent-generated AcceptanceContract（智能体生成验收合同）和 PackageContract.source_surfaces（包合同源码面）作为唯一权威源。Agent JSON artifact（智能体 JSON 产物）只允许作为输入格式，进入 gate（门禁）前必须解析为现有强类型 AcceptanceContract（验收合同）、PackageContract（包合同）、SourceSurface（源码面）、RunManifest（运行清单）和 SourceLineageRecord（源码来源链记录），并通过 validate_contract_gate（合同门禁校验）。Runner 不得维护 `AC-V2-090F-*` 静态验收列表、`_statement_for_acceptance_ref` 类平行声明，或 `app/` / `static/` / `tests/` 路径前缀源码面映射；也不得新增 dict-only（仅字典）FinalEvidenceTable / SourceInventory helper（最终证据表 / 源码清单辅助器）复制现有 FinalEvidenceTableBuilder（最终证据表构建器）、build_source_inventory（源码清单构建器）或 ID/path matching（ID/路径匹配）规则。未被 active PackageContract.source_surfaces 覆盖的 materialized source file（物化源码文件）必须 fail closed，不能默认归入 docs（文档）或 integration（集成）面。

Behavioral probe runner（行为探针运行器）必须有明确执行语义：capture（捕获）从 HTTP JSON response（响应）按受限 JSON path（JSON 路径）提取；`${name}` interpolation（占位符替换）可用于后续 path/body/expected（路径/请求体/期望值）；`json_equals`、`json_contains`、`field_equals`、`field_absent` 断言必须 fail closed。缺 capture、JSON path 不存在、状态码不符、断言失败或 unsupported assertion（不支持断言）不得写成成功 live evidence（真实证据）。

Checker（检查者）和 Closeout（收尾者）仍是 provider-backed agent roles（模型支撑智能体角色）。程序化 helper 可以验证结构、引用和证据完整性，但不能直接生成 approved checker verdict（通过检查结论）或 passed closeout package（通过收尾包）来替代角色 ProviderAttempt（模型调用尝试记录）。

### 理由

V2-090F first run（首次运行）证明真实 provider-backed worker implementation chain（模型供应商支撑工人实施链路）可以完成 tiny fullstack package（微型全栈包）并通过一次 live closeout probe（真实收尾探针）。但专家评审指出，runner/prompt/validator（运行器/提示词/校验器）把 `app/server.py`、`python -m app.server`、`LIBRARY_API_HOST`、`LIBRARY_API_PORT` 和 `LIBRARY_DB_PATH` 前置为 planning requirement（规划要求），Checker/Closeout（检查/收尾）也没有各自 provider attempt（模型调用尝试记录）。这证明的是 worker implementation（工人实施）和程序化探针链路，而不是 agent team autonomy（智能体团队自治）。

“必须能启动”是 DevOps/Release（运维/发布）职责和 PackageContract/RunManifest 协议职责；“必须用某个文件名、模块名或环境变量名启动”除非来自用户需求或 agent-generated contract（智能体生成合同），否则属于 runner 介入。

后续评审又确认，090F first run 的介入不仅限于启动接口。`_probe_v2_090f_crud_workflow`（硬编码增删改查探针）、`_v2_090f_acceptance_refs`（静态验收引用）、`_acceptance_refs_for_project_path`（路径到验收引用映射）和 `_source_surface_for_project_path`（路径到源码面映射）让 runner 继续知道这是 library/books（图书馆/图书）域，并让 runner 成为 AcceptanceContract / PackageContract 之外的第二权威源。这违反 dynamic acceptance contract（动态验收合同）、runtime bounded（运行时有界）和 no second source of truth（无第二权威源）原则。

### 影响

- V2-090K 必须新增或强化 Release/DevOps role responsibility（发布/运维角色职责），推荐使用 `seat.release.devops`（发布运维席位）。
- `src/boardroom_os/workspace/run_manifest.py` 应扩展 service contract（服务合同）、env binding（环境绑定）、readiness probe（就绪探针）、frontend topology（前端拓扑）和 behavioral probes（行为探针）语义。
- V2-090F runner（运行器）必须移除固定 backend entrypoint（后端入口）、固定 env names（环境变量名）、业务域 HTTP workflow（HTTP 工作流）、静态 acceptance refs（验收引用）和路径前缀 source surface（源码面）校验，改为验证 agent-generated AcceptanceContract / PackageContract / RunManifest / BehavioralProbePlan（智能体生成验收合同 / 包合同 / 运行清单 / 行为探针计划），并复用现有强类型 Contract/Evidence（契约/证据）构建器。
- V2-090F 不得因为 first run passed（首次运行通过）而标记 DONE；必须等待 V2-090K 消除 runner/helper 外力介入并完成真实 provider full run（完整真实模型运行）复判。若该 full run fail closed（失败关闭）地暴露 agent-generated contract / implementation / probe / closeout projection（智能体生成合同 / 实现 / 探针 / 收尾投影）不一致，且失败现场可审计保留，则该失败进入 V2-100 返工循环，不再要求 090K 自身 single-pass passed（单轮通过）。

## DEC-0024: V2-100 将 agent team 升级为 CEO-governed rework loop

- 状态：Accepted
- 日期：2026-06-13

### 决策

新增 Phase 10 / V2-100 Agent-team Rework Loop Hardening（智能体团队返工循环强化）。V2-100 的目标不是继续追求一次性 full run（完整运行）成功，而是把人类团队式的沟通、问题识别、返工规划、TicketGraph（工单图）更新、重新实施、重新验证和审计留痕固化为框架能力。

V2-100 引入 ReworkCycle（返工循环）、ReworkRequest（返工请求）、ReworkIssue（返工问题）、ReworkPlan（返工计划）、ReworkAttempt（返工尝试）和 ReworkOutcome（返工结果）作为一等领域对象。Checker（检查者）或 CloseoutGate（收尾门禁）发现 verified blocker（已验证阻塞项）后，不应只抛 Python exception（异常）或终止流程；系统必须生成结构化 blocker/rework request（阻塞/返工请求），由 CEO（项目经理/治理角色）读取后规划返工路线、生成 TicketGraphPatch（工单图补丁）提案，再交由 Architect / Checker / Tester / Release DevOps / Closeout（架构 / 检查 / 测试 / 发布运维 / 收尾）按领域审查。图变更只能由治理命令在 reducer / validator（归约器 / 校验器）通过后提交，CEO 不是 graph patch（图补丁）的唯一审查者或提交者。

RunManifest / service / behavioral probe failure（运行清单 / 服务 / 行为探针失败）只有在被 EvidenceVerifier、Checker、CloseoutGate 或等价 governance adapter（治理适配器）投影为 verified blocker（已验证阻塞项）后，才能打开 ReworkRequest（返工请求）；runtime output（运行时输出）本身不得直接触发返工治理。

Runtime（运行时）和 atomic-agent（原子智能体）只能执行 ReworkTicket（返工工单）并记录 provider/tool/command/workspace facts（模型/工具/命令/工作区事实）。它们不得创建 ReworkPlan、修改 AcceptanceContract（验收合同）或 PackageContract（包合同）、放大 allowed_write_set（允许写集合）、复用旧证据结论，或把 `AgentRunResult.status == completed`（智能体运行完成）解释为返工 accepted（已接受）。

Graph patch review policy（图补丁审查策略）属于治理配置，应进入 config bundle（配置包）或显式 governance policy（治理策略）并以 hash 进入 RunManifest / ProcessAudit（运行清单 / 流程审计）。Runtime YAML（运行时 YAML）可以引用该策略用于执行边界，但不能成为图变更治理的第二权威源。

V2-090K 的完成定义采用“理解 A”：090K 解决 runner/helper 外力介入和合同权威源问题，不要求 agent team 在 single-pass（单轮）内自然收敛。090K 真实 full run 若 fail closed 并保留结构化现场，可以标记 090K DONE；V2-090F golden sample（黄金样例）仍保持 BLOCKED / REVIEW_REQUIRED，等待 `V2-090K + V2-100` 后复判。

### 理由

V2-090K 的核心整改使 runner/helper（运行器/辅助器）不再硬编码业务域、启动接口、静态验收引用和源码面映射；真实 provider full run 也能 fail closed（失败关闭）地暴露 contract / implementation / probe（合同/实现/探针）不一致。但这仍是 single-pass fail-closed（单轮失败关闭）架构：系统能发现问题，却没有把问题交回 CEO 主导的返工闭环。

用户明确指出，agent team（智能体团队）的核心不在单 ticket（工单）一次执行能力，而在团队能否像人类团队一样默认局部产物可能不达标，并通过沟通、返工、重验收敛。此前人工频繁介入修代码、门禁和配置的过程，应被建设成 agent team 自身的框架能力。

2026-06-13 的 090K 真实失败现场已作为 curated failure snapshot（精选失败快照）保存在 `examples/generated-workspaces/tiny-fullstack/30-audit/v2-090k-failure-snapshot/`。该现场证明：PRD-derived（需求派生）的 library/books 业务词本身不是问题；问题是 BehavioralProbePlan（行为探针计划）与 backend response shape（后端响应形状）不一致、env binding（环境绑定）未收敛、FinalEvidenceTable（最终证据表）仍使用旧 `AC-TINY-*` 引用、closeout/audit（收尾/审计）仍引用旧 run。V2-100 必须把这类现场变成结构化 BlockerReport（阻塞报告）和可审计返工路线。

### 影响

- `doc/03-architecture/domain-model.md` 增加 ReworkCycle / ReworkRequest / ReworkPlan / ReworkAttempt / ReworkOutcome（返工循环/请求/计划/尝试/结果）对象。
- `doc/03-architecture/contract-and-evidence-model.md` 增加返工与 EvidenceVerifier / FinalEvidenceTableBuilder / Checker / CloseoutGate（证据验证器/最终证据表构建器/检查/收尾门禁）的重验关系。
- `doc/03-architecture/execution-and-runtime-boundary.md` 明确 runtime 不能规划或接受返工，atomic-agent 内部 repair loop（修复循环）不能替代 Boardroom OS 跨角色返工循环。
- `doc/04-implementation/backlog.md` 新增 Phase 10 / V2-100A~E，共 5 个工作包。
- `doc/04-implementation/acceptance-criteria.md` 新增 AC-V2-REWORK-001~005 和 Phase 10 验收段。
- `examples/generated-workspaces/tiny-fullstack/30-audit/v2-090k-failure-snapshot/` 成为 V2-100 的真实失败输入；V2-100E 还必须构造 resettable failing fixture（可重置失败夹具），避免端到端证明只依赖不可重置的真实 provider 现场。
- V2-100 不替代 V2-090K 的去硬编码整改；V2-090K 已可按 fail-closed 证据语义闭合。V2-100 的完成用于复判 V2-090F golden sample 是否可从 BLOCKED 转为 DONE。

## DEC-0025: V2-090F 先做真实返工入口验证再补编排

- 状态：Accepted
- 日期：2026-06-16

### 决策

V2-100E 完成后，V2-090F 的下一步是执行真实 rerun rework-entry validation（重跑返工入口验证），而不是先实施大规模 orchestration glue（编排胶水）或默认认为框架还缺一套新编排能力。

重跑必须仍以 single user PRD（单份用户需求文档）为业务输入，使用 V2-090F 专用 runtime/providers/roles config（运行时 / 供应商 / 角色配置），并经过现有 EvidenceVerifier / FinalEvidenceTableBuilder / Checker / CloseoutGate（证据验证器 / 最终证据表构建器 / 检查者 / 收尾门禁）。判定规则为：

1. 若没有 verified blocker（已验证阻塞项），按原 closeout path（收尾路径）形成 V2-090F DONE candidate（完成候选），仍需专家评审。
2. 若存在 verified blocker，必须形成 BlockerReport（阻塞报告）和 ReworkRequest（返工请求），再进入 V2-100 ReworkCycle（返工循环）。
3. 进入返工后，必须导出 TicketGraph before/after（工单图更新前后）和 TicketGraphPatch（工单图补丁）证据，证明图确实被治理更新。
4. 只有真实重跑证明现有 gate failure（门禁失败）无法投影成 BlockerReport / ReworkRequest 时，才允许补最小 rework-entry adapter（返工入口适配器）。该 adapter 只能结构化既有 gate failure，不得复制或替代 FinalEvidenceTableBuilder、SourceInventory、Checker 或 CloseoutGate（最终证据表构建器 / 源码清单 / 检查者 / 收尾门禁）。

### 理由

V2-100E 已证明返工模型、图补丁、多角色审查、证据重验和终态决策链路可工作。此时继续先写编排框架会在没有真实 090F 失败形态前制造第二套接口和第二事实源，违反 no duplicate implementations（禁止重复实现）和 no second source of truth（无第二权威源）。

用户对 agent team autonomy（智能体团队自治）的理解是输入始终只有一份 PRD，框架应根据原有输入输出自适应；阻断才进入返工，不阻断则按原样 closeout。因此 090F 复判应先观察真实运行：如果阻断已经自然成为 verified blocker，就直接交给 V2-100；如果阻断停在 raw exception（原始异常）或自由文本错误，才证明原框架存在 rework-entry gap（返工入口缺口）。

### 影响

- 新增 `doc/04-implementation/v2-090f-rerun-rework-entry-validation-spec.md` 作为 V2-090F 下一步复判入口。
- `doc/04-implementation/backlog.md` 中 V2-090F 继续保持 `BLOCKED`，但阻塞说明从等待 V2-100E 评审更新为等待真实重跑返工入口验证。
- `doc/04-implementation/acceptance-criteria.md` 增加未勾选的 rerun rework-entry validation（重跑返工入口验证）前置项；完成前不得勾选 V2-090F package / closeout / audit 验收。
- 后续实施计划必须先做 observation run（观察重跑），再根据证据决定是否补最小 entry projection（入口投影），最后才执行 rework continuation（返工继续）。

## DEC-0026: RunManifest 摄取采用宽容语义边界

- 状态：Proposed
- 日期：2026-06-16

### 决策

新增 V2-100F RunManifest tolerant ingestion and rework entry（运行清单宽容摄取与返工入口）批次，等待计划评审与后续实施。

V2-100F 的核心决策是：RunManifest（运行清单）摄取层不得把 LLM（大模型）输出的 behavior assertion type（行为断言类型）字符串视作封闭协议枚举。模型输出可能自然产生 `json_array_contains_field`、`json_array_item_field_equals`、`json_array_lacks_field` 或其他未来变体；继续逐个补 alias（别名）会让框架陷入无穷适配循环。

框架应只约束系统可以宣称什么，而不应在摄取阶段限制 agent 只能使用哪些自然语义词汇。因此 RunManifest assertion（运行清单断言）应先作为 raw semantic payload（原始语义载荷）保留，连同 PackageContract（包合同）、AcceptanceContract（验收合同）、项目文档、源码引用和既有失败上下文进入 CEO-governed verify-blackbox hook（项目经理治理黑盒验证钩子）。BlackboxVerificationPlan（黑盒验证计划）的产出者不是固定 Tester（测试者）或 Release DevOps（发布运维），而是 CEO（项目经理）通过 TicketGraph / SeatDemand（工单图 / 席位需求）派给 `verify-blackbox` ticket（黑盒验证工单）的 AgentSeat（智能体席位）。未知断言不得 raw crash（原始崩溃）、不得静默跳过、不得算作通过证据。

黑盒验证动作由被派工 AgentSeat（智能体席位）在 provider-backed output（模型支撑输出）中决定；runner（运行器）只执行该计划并记录真实 command / HTTP / browser / tool facts（命令 / HTTP / 浏览器 / 工具事实）。框架不得根据 RunManifest 自行生成业务探针、默认端点或隐藏断言。无法通过证据证明的行为应投影为结构化 ReworkIssue（返工问题）/ ReworkRequest（返工请求）上下文，让 CEO / Architect / Tester / Release DevOps（项目经理 / 架构师 / 测试 / 发布运维）判断修 implementation（实现）、RunManifest（运行清单）、contract（合同）还是 TicketGraph（工单图）。若新增 `ReworkSuspectedDomain.MANIFEST`（运行清单疑似域），该域只能由 typed verifier/checker/gate（类型化验证/检查/门禁）或 provider-backed governance output（模型支撑治理输出）声明；framework（框架）不得根据 raw text（原始文本）、异常消息或 manifest fragment（清单片段）自动判定域归属。

### 理由

2026-06-16 V2-090F 真实 rerun 已证明当前 rework-entry（返工入口）卡死在 manifest assertion normalization（运行清单断言归一化）阶段，raw error 为：

```text
ValueError: unsupported RunManifest behavior assertion type: json_array_contains_field
```

该异常发生在形成 CloseoutGateResult（收尾门禁结果）、verified blocker（已验证阻塞项）或 ReworkRequest（返工请求）之前，导致 terminal status（终态）为 `blocked_by_missing_rework_entry`。这不是 V2-100A~E 返工循环能力本身失败，而是上游事实摄取和解释边界过紧，未能把模型输出不确定性转换为可返工事实。

同时，本地黑盒探索显示生成工程并非空壳：backend CRUD / checkout / return / delete（后端增删改查 / 借出 / 归还 / 删除）和单元测试可运行；但 RunManifest 与实现之间存在 readiness path（就绪路径）和 response shape（响应结构）等真实 drift（漂移）。这些 drift 应成为返工上下文，而不是被 assertion enum（断言枚举）错误提前截断。

### 影响

- 新增 `doc/04-implementation/v2-100f-manifest-tolerant-ingestion-rework-entry-spec.md`，作为专家评审入口；新增 `doc/04-implementation/v2-100f-manifest-tolerant-ingestion-rework-entry-implementation-plan.md`，作为后续代码实施入口。
- `doc/04-implementation/backlog.md` 将 V2-100 从 5 个工作包扩展为 V2-100A~F，当前 Phase 10 状态为 5 / 6，V2-100F REVIEW_REQUIRED。
- `doc/04-implementation/acceptance-criteria.md` 新增 AC-V2-REWORK-006，并保持未勾选，直到实现证明未知 assertion 不 raw crash、不被忽略、不通过 closeout，且能进入 CEO-governed assigned AgentSeat（项目经理治理派工的智能体席位）自主黑盒验证和返工上下文。
- V2-090F golden sample（黄金样例）继续 BLOCKED；不得通过直接 patch 当前样例工程或补固定 alias 列表来伪造完成。
- 2026-06-18 追加计划边界：V2-100F implementation plan（实施计划）必须强制新写 governed orchestration（治理编排）链路；可复用 V2-100 domain models / reducers / validators（领域模型 / 归约器 / 校验器），但不得复用 V2-100E proving scenario orchestration（证明场景编排）、resettable fixture（可重置夹具）、minimal package stub（最小占位包）或 accepted audit shortcut（接受审计捷径）作为 V2-100F 成功路径。`v2-090k-failure-snapshot`（V2-090K 历史失败快照）仅可供 V2-100A~E historical regression（历史回归）读取，V2-100F active path（活跃路径）不得读取、复制、改写或通过该 snapshot 路由。
