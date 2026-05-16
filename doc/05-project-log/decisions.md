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

