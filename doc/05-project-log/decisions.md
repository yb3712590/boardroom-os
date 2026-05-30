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
