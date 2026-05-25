# V2-070G Closeout Closure Hardening（收尾闭包硬化）spec

## 1. 背景与现实场景

V2-070A~F 已经把 closeout pipeline（收尾流水线）一路从 CloseoutGate（收尾门禁）、ReplayBundle（重放包）、ProcessAuditBundle（流程审计包）、GitVersionAuditBundle（Git 版本审计包）、CloseoutPackage（收尾包）直到 CloseoutReducer（收尾归约器）物化为 typed object + readiness projection（类型化对象 + 就绪投影）。但在 V2-070 大阶段的同行评审中发现：

链路虽然搭通，"证据闭包（evidence closure）"在多处由 self-validating derivations（自洽派生）、placeholder sentinels（占位哨兵）、weak field constraints（弱字段约束）和 early returns（提前返回）补齐。具体表现为：

1. ProcessAudit（流程审计）在 EventLog（事件日志）缺关键事件时，会自动从 typed input 合成 `process_audit_projection` 来源的 timeline 条目，让 `timeline_key_events_present` 仍然返回 True。
2. ArtifactLineage（产物来源链）允许 `verifier_ref="verifier.unresolved"` 这种 sentinel 通过非空校验，等价于"找不到 verifier（验证器）也算来源闭合"。
3. GitVersionAudit readiness（Git 版本审计就绪投影）只重算 hash manifest（哈希清单），report 中 `source_inventory_hash_matches` / `final_command_evidence_at_final_commit` 等关键 booleans 被当作 trusted input（可信输入），未基于 fact_set（事实集）+ command_evidence_bindings（命令证据绑定）重新推导。
4. CloseoutReducer（收尾归约器）命中 `CLOSEOUT_COMMITTED`（收尾已提交）即 `return`，**同一 batch（批次）后续事件的 `project_ref` / `graph_version` 不再校验**。
5. ProcessAudit 与 CloseoutPackage 在跨对象绑定上只校验 `project_ref` 与 readiness 自一致，**未要求 GitVersionAuditBundle 的 source inventory ref/hash、package commit、checked_refs 覆盖当前 closure**。
6. CloseoutGate 校验了 `verified_evidence_refs`，但未校验 `WorkspaceEvidenceBundle.verification_run_refs` 与 gate input 一致。
7. EvidenceMap（证据映射）的 `expected_evidence_map_rows` 与 evidence map artifact 共用同一份 `_evidence_map_payload(builder_input)` 派生，readiness 等同于自我验证。
8. ReplayBundleReadiness（重放包就绪摘要）仅以 `summary_hash` 绑定，`event_range` / `projection_versions` 等不二次比对。
9. `_validate_events` 只检查非空，输入乱序或 graph_version 缺口会被后续 `sort` 掩盖。
10. 多处 hash 类型只是 `NonEmptyTextValue`（`ReplaySummaryHash` / `GitCommitSha` / `SourceInventoryHash`），不强制 SHA 格式与 placeholder 拒绝；`_is_placeholder_sha256` 仅硬编码白名单 `{a*64, 0*64, 1*64, f*64}`。
11. `AgentContextIndexEntry` 真实 schema 字段 `execution_package_ref` / `model_execution_profile` 位于 `entry.snapshot.*` 下，而 ProcessAudit 直接 `getattr(entry, ...)` 永远拿到 None，靠测试 fixture 把字段平铺到顶层绕过——这是 second source of truth（第二事实源）。
12. `AgentContextIndexEntry.provider_attempt_refs` 只校验非空，不要求是 ProcessAuditBuilderInput.provider_attempt_refs 子集。
13. `GitAuditAdapter._require_read_only_command` 仅对 `diff` 拦截 `--output`；`git show --output=...` / `git log --output-indicator-new=...` 仍可写文件。

通俗地说：审计员在 closeout 时拿到的不再是"独立可重算的证据闭包"，而是"自洽的派生材料"。

本次硬化的目标，是按 CLAUDE.md `Engineering Standards`（工程标准）中的 hard rules（硬规则）——**no silent fallbacks（无静默 fallback）、no mocked success paths（无伪造成功路径）、no second source of truth（无第二事实源）、no broad error swallowing（无大范围错误吞掉）、no hardcoded configurable options（无硬编码可配置项）**——把 V2-070A~F 全部接受 boundary（边界）改造为 fail-closed evidence closure（失败封闭式证据闭包），并对外冻结 V2-070 大阶段的输入输出契约。

Pre-flight（一致性预检）：`backlog.md` 中 V2-070A~F 全部标记完成；本次新增 V2-070G 工作包，文件位于 `doc/04-implementation/v2-070g-closeout-closure-hardening-spec.md`；当前 `src/boardroom_os/audit/process_audit.py`、`src/boardroom_os/audit/git_version_audit.py`、`src/boardroom_os/closeout/gate.py`、`src/boardroom_os/closeout/package.py`、`src/boardroom_os/reducers/closeout_reducer.py`、`src/boardroom_os/adapters/git_audit.py` 均已存在且测试通过，但本 spec 列出的缺口未被现有 negative tests 覆盖。

## 2. 范围与边界

### 2.1 In Scope（覆盖范围）

- ProcessAuditBundle / ProcessAuditBuilderInput / process_audit_readiness（流程审计包及其投影）
- GitVersionAuditBundle / GitVersionAuditBuilderInput / git_version_audit_readiness（Git 版本审计包及其投影）
- CloseoutGate / CloseoutGateInput / CloseoutGateResult（收尾门禁）
- CloseoutPackage / CloseoutPackageBuilderInput（收尾包）
- CloseoutReducer（收尾归约器）
- GitAuditAdapter `_require_read_only_command`（Git 审计采集只读边界）
- 共享 value object（值对象）：`ReplaySummaryHash` / `GitCommitSha` / `SourceInventoryHash` / `ProcessAuditContentHash` 等 SHA 类
- placeholder digest detector（占位摘要识别器）`_is_placeholder_sha256` 抽出为公共纯函数

### 2.2 Out of Scope（边界外）

- 不重新设计 ReplayBundle / ProcessAuditBundle / GitVersionAuditBundle / CloseoutPackage 的 schema 版本（仍是 `version: 1`），仅收紧 invariant（不变量）。
- 不引入 branchable governance replay（可分叉治理重放），按 memory `project_replay_scope` 留到独立工作包。
- 不修改 `30-audit/` 十项 artifact 的逻辑路径与文件名。
- 不变动 CloseoutGate 的 verdict 公式与 result_id 派生公式（`closeout-gate-result.{source_inventory_id}.{final_evidence_table_id}`），由 V2-070A 维护。

### 2.3 兼容性策略

按 hard rule **no second source of truth**：V2-070A~F 任何与本 spec 冲突的旧 boundary 一律改造为新 boundary，**不保留 backwards-compat shim（向后兼容兜底）**。删除时同步删除所有引用与"removed for X"注释。下游测试 fixture 必须迁移到真实 schema。

## 3. V2-070 阶段输入/输出契约（对外冻结）

V2-070G 完成后，V2-070 大阶段对外提供以下契约。任何调用方都按此契约消费，不允许从内部字段二次推导。

### 3.1 输入：CloseoutDomainInputs（收尾域输入）

V2-070 接受的全部 typed inputs 必须从 V2-010~V2-060 通过 typed boundary 传入，**不接受 plain dict（裸字典）或 partial mock（半成品 mock）**：

| 输入对象 | 来源 | 关键约束 |
|---|---|---|
| `ProjectCharter`（项目章程） | V2-010A | `project_ref` 唯一 |
| `AcceptanceContract`（验收合同） | V2-010C | 引用同一 `project_charter_ref` |
| `PackageContract`（包合同） | V2-010E | 引用同一 `acceptance_contract_id` |
| `TicketGraphSummary`（任务图摘要） | V2-030A | 每 ticket 引用 `acceptance_refs` |
| `AgentContextIndex`（智能体上下文索引） | V2-040E | entries[*].snapshot.* 真实字段；不允许平铺 |
| `EventRecord[]`（事件日志切片） | V2-020 | 严格按 `graph_version` 递增；本 batch 覆盖关键事件 |
| `ProviderAttemptRef[]`（模型调用尝试引用） | V2-040E | 去重；可被 AgentContextIndex 解析 |
| `VerificationRun[]`（验证运行） | V2-040D | `status=PASSED`、`exit_code=0` |
| `VerifiedEvidence[]`（已验证证据） | V2-050B | 引用真实 `VerificationRun` |
| `FinalEvidenceTable`（最终证据表） | V2-050C | 每 row 引用 `VerifiedEvidence` |
| `CheckerVerdict`（检查者结论） | V2-050D | `final_evidence_table_ref` 一致 |
| `SourceInventory`（源码清单） | V2-060C | entries[*].evidence_refs 在 `VerifiedEvidence` 集合中可解析 |
| `RunManifest`（运行清单） | V2-060D | `package_contract_ref` 一致 |
| `WorkspaceEvidenceBundle`（工作区证据包） | V2-060E | `closeout_ready=True`、`verified_evidence_refs` 与 `verification_run_refs` 与输入完全一致 |
| `GitFacts`（Git 事实集） | V2-070D adapter | `git_clean=True`、`source_inventory_hash` 与 SourceInventory 等价 |

### 3.2 输出：CloseoutDomainOutputs（收尾域输出）

V2-070 大阶段成功时仅对外发布以下三件 durable artifact（持久产物）：

1. `CloseoutPackage`（收尾包，`verdict=PASSED`），其 `checked_refs` 覆盖下述全部 ref 与 hash。
2. `CloseoutProjection`（收尾投影，`terminal_status=SUCCEEDED`），唯一持有 closeout terminal truth（收尾终态事实）。
3. 三件 readiness summaries（就绪摘要）：`ReplayBundleReadiness` / `ProcessAuditReadiness` / `GitAuditReadiness`，分别由 `replay_bundle_readiness(...)` / `process_audit_readiness(...)` / `git_version_audit_readiness(...)` 三个 pure projection function（纯投影函数）独立重算得到。

下游（V2-080 及之后）只能消费 `CloseoutProjection` 与三件 readiness summaries，不允许直接读 `CloseoutPackage` 内部字段绕过门禁。

### 3.3 幂等与稳定性

- 三个 readiness projection 必须 deterministic & pure（确定性 + 纯函数）：相同 typed input 产出 byte-for-byte（逐字节）相同的 readiness 与 hash。
- CloseoutReducer 对同一 EventRecord batch 重复执行必须产出等同 `CloseoutProjection`；duplicate `CLOSEOUT_COMMITTED` 直接 fail，**不靠"已经 succeeded 就跳过"**。
- 任何 bundle 重新构建必须复算所有 hash chain（哈希链），并与持久化的 hash 完全相等；不允许"hash 是旧的就保留旧 hash"。
- 全部 SHA 字段使用同一 value object（值对象）家族，序列化/反序列化必须保持 lowercase hex 与长度约束。

## 4. 设计方案（逐缺口硬化）

### 4.1 P0-1 移除 timeline projection 合成路径

- 删除 `_timeline_milestone_items` 中"对缺失关键事件自动合成 process_audit_projection 条目"的逻辑。
- 新增 `_validate_timeline_event_kinds(builder_input)`：在 `_validate_input` 阶段断言 `builder_input.events` 真实覆盖 `_REQUIRED_TIMELINE_EVENT_KINDS`；任何缺失直接 `raise ProcessAuditError("missing timeline event kind: ...")`。
- timeline artifact 只允许 `source="event_log"` 条目；从 builder/readiness 中删除 `process_audit_projection` 字面量。
- 命名上保留 `_REQUIRED_TIMELINE_EVENT_KINDS` 为唯一权威，删除散落在 milestone_specs 中的 ref 取值逻辑（合并为单一 typed lookup table）。

### 4.2 P0-2 删除 verifier.unresolved sentinel

- 移除 `_verification_ref_for_evidence` 中"未解析回退到 `verifier.unresolved`"分支。
- `_artifact_lineage_payload` 在 `verified_by_ref.get(evidence_ref.value)` 返回 None 时直接 raise，并指明 `(source_inventory_entry, evidence_ref)`。
- 在 `ProcessAuditBuilderInput._validate_input` 中新增：所有 `SourceInventory.entries[*].evidence_refs` 必须在 `verified_evidence` 集合中可解析；不可解析直接 raise（fail-closed），并把这个不变量同步到 `CloseoutGate` 与 `CloseoutPackage`，三处共用同一 helper 而不是各自复制条件。
- 删除 `_LINEAGE_REQUIRED_FIELDS` 中对 `verifier_ref` 字段"只检查非空"的隐式契约，改为校验值出现在 `verification_runs` 的 ref 集合中。

### 4.3 P0-3 GitVersionAudit readiness 重新推导报告 booleans

- `git_version_audit_readiness(bundle)` 不再信任 `report.source_inventory_hash_matches` / `final_command_evidence_at_final_commit`：
  - `source_inventory_hash_matches` 由 `bundle.fact_set.source_inventory_hash == bundle.report.source_inventory_hash_in_report` 重新比较得到（必要时为 report 增加显式 source_inventory_hash 字段，作为唯一事实源）。
  - `final_command_evidence_at_final_commit` 由 `command_evidence_bindings` 中每条 binding 的 `commit_sha == fact_set.final_commit_sha` 与 `command_kind` 是否覆盖 `RunManifest` 必需命令重新派生。
- readiness 返回前与持久化的 report booleans 比较，**不一致直接 raise**。这样既保留 report 作为 human-readable artifact，又消除 boolean 二次事实源。
- 若 V2-070D report schema 缺少必要字段，本次同步扩展，禁止用 placeholder 补齐。

### 4.4 P0-4 CloseoutReducer 全量预扫描

- `CloseoutReducer.reduce(events, base_history=None)` 改为 two-pass（两遍）：
  - Pass 1：遍历全部 events，校验 `project_ref` 一致、`graph_version` 相对 `base_history` 严格递增、`CLOSEOUT_COMMITTED` 至多 1 次、closeout 后不能再出现任何 ticket/work_product/closeout 事件。
  - Pass 2：按事件顺序构造 projection，命中 `CLOSEOUT_COMMITTED` 时收尾 binding 校验，并在循环结束后才 return。
- 取消"循环中遇到 closeout 就 return"导致的 early-exit；遇到 closeout 之后还有事件时直接 raise `CloseoutReducerError("events after closeout commit are not allowed")`。

### 4.5 P0-5 ProcessAudit 绑定 GitVersionAuditBundle 到当前闭包

- 在 `ProcessAuditBuilderInput._validate_input` 中新增：
  - `git_version_audit_bundle.report.source_inventory_ref == source_inventory.source_inventory_id`
  - `git_version_audit_bundle.report.source_inventory_hash == source_inventory_hash(source_inventory)`（hash 推导走唯一函数 `source_inventory_hash`）
  - `git_version_audit_bundle.report.package_commit_ref == source_inventory.package_commit_ref`
  - `git_version_audit_bundle.fact_set.final_commit_sha == source_inventory.package_commit_ref` 中嵌入的 SHA 部分（同 V2-070D `_validate_package_commit_ref`）
- 校验函数从 `closeout/package.py`、`audit/process_audit.py`、`audit/git_version_audit.py` 三处复用同一 `assert_git_bundle_binds_to_source_inventory(...)` helper。

### 4.6 P0-6 CloseoutPackage 绑定 ProcessAuditBundle.checked_refs

- 在 `_validate_builder_input` 中新增：`process_audit_bundle.checked_refs` 必须覆盖
  - `source_inventory.source_inventory_id`
  - `final_evidence_table.final_evidence_table_id`
  - `replay_bundle.replay_bundle_id`
  - `git_version_audit_bundle.git_version_audit_bundle_id`
  - `git_version_audit_bundle.report.source_inventory_hash`
  - `git_audit_readiness.final_commit_sha`
  - `replay_readiness.summary_hash` 与 `replay_readiness.event_range`
- 缺任一 ref 直接 raise；与 `_validate_gate_checked_refs` 复用同一 `assert_checked_refs_cover(required, observed, code=...)` 工具函数，避免两份相似列表漂移。

### 4.7 P0-7 CloseoutGate 校验 workspace verification_run_refs

- `_workspace_evidence_bundle_blockers` 增加：
  - `bundle.verification_run_refs` 与 `gate_input.verification_runs` 的 `verification_run_id` 集合完全相等。
  - 任何 reference 不在集合中或缺失时返回新增 blocker code `WORKSPACE_EVIDENCE_BUNDLE_NOT_READY` 子类（或保留同一 code，但 detail 字段带具体差集）。
- 同步在 `CloseoutGateInput` 层加 model-level invariant：`workspace_evidence_bundle.verification_run_refs == verification_runs` 集合。

### 4.8 P1-8 EvidenceMap readiness 独立重推

- 拆分 `_evidence_map_payload(builder_input)` 为两个职责：
  - `_build_evidence_map_artifact(builder_input)`：构建 artifact 的视图。
  - `_derive_expected_evidence_map_rows(final_evidence_table, verified_evidence, source_inventory, verification_runs, checker_verdict)`：从原始 typed input 独立重算 expected rows，**不读 artifact**。
- `_validate_evidence_map(bundle)` 改为：
  - 用 `bundle.process_audit_report.expected_evidence_map_rows` 与 `_derive_expected_evidence_map_rows(...)` 比较；
  - 用 `actual rows`（artifact 内容）与 `_derive_expected_evidence_map_rows(...)` 比较；
  - 三方必须等价。
- `process_audit_report.expected_evidence_map_rows` 字段仍保留作为 hash chain 一部分，但其值来自 `_derive_expected_evidence_map_rows(...)`，不再来自 artifact 派生快照。

### 4.9 P1-9 ReplayBundleReadiness 全字段重算

- `ProcessAuditBuilderInput._validate_input` 把 `replay_readiness == replay_bundle_readiness(replay_bundle)` 整体比较；删除只比较 `summary_hash` 的旧逻辑。
- 调用 `replay_bundle_readiness` 必须可在不引入循环依赖的前提下重用 V2-070B 的 projection；如有循环风险，把 readiness projection 抽到 `boardroom_os.audit.replay_readiness`（或 V2-070B 已经提供的现有模块）作为唯一来源。

### 4.10 P1-10 EventRecord 严格递增校验

- `ProcessAuditBuilderInput._validate_events` 改为：
  - events 非空；
  - 按输入顺序 `graph_version` 严格递增；
  - `project_ref` 全部等于 `builder_input.project_ref`；
  - 若 spec 要求连续 graph_version（与 V2-020F EventLog reducer 对齐），缺口直接 raise，不接受 gap explanation（缺口说明）。
- timeline projection 在 sort 之前断言"输入顺序与 graph_version 排序一致"，否则 raise。

### 4.11 P2-11 AgentContextIndex 字段路径修正

- `_agent_context_index_payload` 改为读取 `entry.snapshot.execution_package_ref` / `entry.snapshot.model_execution_profile.model_dump(mode="json")`，删除 `getattr(entry, "execution_package_ref", None)` 这种 fallback。
- 同步删除任何用顶层平铺字段 mock `AgentContextIndexEntry` 的测试 fixture，全部迁移到真实 schema。
- `_validate_agent_context_index_payload` 不再以 `entry.get(...)` 非空作为唯一判据，而是把"required field path"集中在常量 `_REQUIRED_AGENT_CONTEXT_FIELDS`，并显式校验 `entry["snapshot"]` 的子字段。

### 4.12 P2-12 provider_attempt_refs 子集校验

- `AgentContextIndex` 每个 entry 的 `provider_attempt_refs` 必须是 `builder_input.provider_attempt_refs` 的子集；缺失或不可解析直接 raise。
- 校验在 `ProcessAuditBuilderInput._validate_input` 完成，避免分散到 readiness 阶段。

### 4.13 P2-13 SHA value object 强化

- 在 `boardroom_os.contracts.types` 或新模块 `boardroom_os.contracts.hashes`（择一，按现有 import boundary 决定）新增：
  - `Sha1Hex`、`Sha256Hex`，强制 lowercase 40/64 hex 且拒绝 placeholder。
- 将以下别名改为 `Sha256Hex` / `Sha1Hex` 的子类（保留命名以增强语义）：
  - `ReplaySummaryHash`、`SourceInventoryHash`、`GitVersionAuditContentHash`、`ProcessAuditContentHash`
  - `GitCommitSha`（`Sha1Hex` 子类）
- `EventRangeRef` / `ProjectionVersionRef` 若需要约束语义，按 V2-070B 已有定义沿用；本 spec 不扩散 SHA 校验到非 hash 字段。

### 4.14 P2-14 GitAuditAdapter 改为命令模板

- `GitAuditAdapter` 不再接受任意 git argv：
  - 新增 `_GIT_READ_ONLY_TEMPLATES`：每个采集动作对应一个固定 argv tuple + 可选 placeholder（如 `{commit_sha}`）。
  - 暴露 `git_status()` / `git_rev_parse(ref)` / `git_show_commit(commit)` 等 method，内部直接构造模板化 argv。
- 删除 `_require_read_only_command` 中"白名单子命令 + 个别 flag 拦截"逻辑；调用方不再能传入自定义命令。

### 4.15 P2-15 placeholder digest detector 重写

- 抽出 `is_placeholder_digest(value: str, *, length: int) -> bool` 为 `boardroom_os.contracts.hashes` 公共函数：
  - 拒绝 `len(set(value.lower())) == 1`（覆盖任意单字符重复）；
  - 拒绝长度不符；
  - 拒绝包含非 hex 字符；
  - 拒绝项目内置 dummy patterns（统一从一个 frozenset 引用，不再各自硬编码）。
- 所有调用方（`Sha256Hex`、`Sha1Hex`、`GitVersionAuditContentHash` 旧实现）改为依赖这个公共函数；删除 `audit/git_version_audit.py:_is_placeholder_sha256` 的局部实现。

## 5. 幂等与稳定性要求（must-have invariants）

- 三件 readiness projection（replay / process audit / git audit）必须是 pure function：相同 typed input → byte-for-byte 相同 readiness 与 hash。CI 中需有 test 反复调用 N 次断言结果稳定。
- CloseoutPackage build 必须使用确定性时间源（来自输入 `generated_at`），不取 `datetime.now()`。
- 所有 hash 与 `checked_refs` 集合在构建函数与 readiness 中**不重复实现**：构建函数生成、readiness 重算时**调用同一 helper**比较。
- 任何 fail-closed 抛错的错误信息必须包含定位三元组：`(domain_object_id, expected, actual)`，便于审计员定位；禁止只抛 "mismatch"。
- 删除全部"if X is None then …"形式的隐式 fallback；缺字段一律在 schema 层 raise。

## 6. 硬编码 / 兼容代码 / 隐式 fallback 治理清单

按 hard rule **no hardcoded configurable options** + **no silent fallbacks**，本次必须落地的清单：

| 现状 | 治理动作 |
|---|---|
| `audit/git_version_audit.py:35` `_is_placeholder_sha256` 字符白名单 | 改为 `contracts/hashes.py:is_placeholder_digest`，统一拒绝单字符重复 |
| `process_audit.py:1216` `"verifier.unresolved"` sentinel | 删除；改 fail-closed |
| `process_audit.py:1088-1100` `process_audit_projection` 合成 timeline | 删除；改 fail-closed |
| `process_audit.py:1189` `evidence_claim_ref` fallback 到 `evidence_ref.value` | 删除；要求 evidence 必须可解析 |
| `process_audit.py:1131` `getattr(entry, "execution_package_ref", None)` 平铺读取 | 改为 `entry.snapshot.execution_package_ref` |
| `gate.py:37-54` `ReplaySummaryHash` / `GitCommitSha` / `SourceInventoryHash` = `NonEmptyTextValue` | 改继承 `Sha256Hex` / `Sha1Hex` |
| `adapters/git_audit.py:128-149` argv 白名单 + 个别 flag 拦截 | 改为固定 argv 模板，调用方失去自由度 |
| `process_audit.py:819` 只比较 `summary_hash` | 改为 `replay_bundle_readiness(replay_bundle) == replay_readiness` 整体比较 |
| `process_audit.py:1005` `expected_evidence_map_rows = _evidence_map_payload(builder_input)["rows"]` | 改为独立 `_derive_expected_evidence_map_rows(...)` |
| `closeout_reducer.py:246` 命中 closeout 即 return | 改两遍扫描 |
| `closeout/gate.py:603-632` workspace bundle 不校验 `verification_run_refs` | 增加集合一致性校验 |
| `closeout/package.py:374-385` 仅校验 process audit `project_ref` + readiness | 增加 `checked_refs` 覆盖校验 |
| 测试 fixture 中把 `AgentContextIndexEntry` 平铺字段的写法 | 全部迁移到 `entry.snapshot.*`；删除旧 fixture |
| 任何含 `"verifier.unresolved"` / `"process_audit_projection"` 字面量的注释或残留 | 一并清除，不留 `// removed for ...` |

## 7. 工作分解

按"单提交单主题"切分。下列顺序保证编译/测试可逐步增量通过：

1. `feat(contracts/hashes): 新增 Sha1Hex/Sha256Hex 与 is_placeholder_digest`
   - 新模块；将 `Sha256Hex` 等使用方迁移；删除局部 `_is_placeholder_sha256`。
2. `refactor(adapters/git_audit): 固定 git argv 模板`
3. `feat(audit/process_audit): 修正 agent context index 字段路径与子集校验`
4. `feat(audit/process_audit): 移除 timeline projection 合成 + EventRecord 严格递增`
5. `feat(audit/process_audit): 移除 verifier.unresolved sentinel + lineage fail-closed`
6. `feat(audit/process_audit): evidence map readiness 三方独立比对`
7. `feat(audit/process_audit): 与 GitVersionAuditBundle 强绑定 source inventory`
8. `feat(audit/process_audit): replay readiness 整体重算`
9. `feat(audit/git_version_audit): readiness 重新推导 report booleans`
10. `feat(closeout/gate): workspace verification_run_refs 一致性校验 + Sha 类型升级`
11. `feat(closeout/package): process_audit_bundle.checked_refs 覆盖校验`
12. `feat(reducers/closeout): CloseoutReducer 两遍扫描`
13. `test(closeout): 新增 V2-070G negative tests + idempotency tests`
14. `chore(closeout): 清除残留 sentinel/注释/旧 fixture`

每个 commit 必须自带对应单元测试；尾包 commit 11 之后所有相关 negative tests 必须可全绿。

## 8. 验收标准（acceptance）

### 8.1 Negative tests（fail-closed 必证）

文件位置：`tests/closeout/`、`tests/negative/`。每条用例需独立证明对应缺口被堵：

1. EventRecord 缺 `provider_attempt_recorded` → `build_process_audit_bundle` raise，错误消息含 `provider_attempt_recorded`。
2. EventRecord 缺 `work_product_submitted` → raise，错误消息含 `work_product_submitted`。
3. `SourceInventory.entries[*].evidence_refs` 含未在 `verified_evidence` 中的 ref → `build_process_audit_bundle` / `CloseoutGate` / `CloseoutPackage` 三处都 raise（任选一个执行点验证即可，但断言三个 helper 调用同一函数）。
4. GitVersionAuditBundle.report 中 booleans 被人为篡改为 True → `git_version_audit_readiness` raise（与 fact_set/bindings 重算不一致）。
5. CloseoutReducer 输入 `[CLOSEOUT_COMMITTED, WORK_PRODUCT_SUBMITTED]` → raise `"events after closeout commit are not allowed"`。
6. CloseoutReducer 输入 `[CLOSEOUT_COMMITTED(project=A), TICKET_BLOCKED(project=B)]` → raise（不再静默返回）。
7. ProcessAudit 输入中 GitVersionAuditBundle 的 `source_inventory_ref` 指向另一份 SourceInventory → raise。
8. CloseoutPackage 输入中 ProcessAuditBundle.checked_refs 不覆盖当前 ReplayBundle id → raise。
9. WorkspaceEvidenceBundle.verification_run_refs 与 gate_input.verification_runs 不等 → gate 返回 blocker。
10. EvidenceMap 中 `expected_evidence_map_rows` 与独立重算结果不等 → raise；artifact 自洽但偏离独立重算亦 raise。
11. ReplayReadiness 的 `event_range` 与 `replay_bundle_readiness(replay_bundle)` 不等 → raise。
12. EventRecord 顺序为 `(graph_version=2, graph_version=1)` → raise；`(1, 3)` 缺口同样 raise。
13. AgentContextIndexEntry 的 `provider_attempt_refs` 含 `builder_input.provider_attempt_refs` 之外的 ref → raise。
14. `Sha256Hex("a"*64)` / `Sha256Hex("b"*64)` / `Sha256Hex("0"*64)` / `Sha256Hex("z"*64)`（非 hex）全部 raise。
15. `GitAuditAdapter` 调用方尝试自定义 argv → 编译期不可调用（method 不暴露）；如保留 escape hatch，必须有 explicit boundary test。

### 8.2 Happy path（正例必证）

1. 真实 EventLog 覆盖全部 `_REQUIRED_TIMELINE_EVENT_KINDS` → `process_audit_readiness.timeline_key_events_present=True`，且 timeline artifact 中所有条目 `source="event_log"`。
2. 三件 readiness projection 各被独立调用 5 次，输出 hash 与字段完全相等（idempotency test）。
3. CloseoutReducer 对相同 EventRecord batch 重复调用产出等同 `CloseoutProjection`。
4. CloseoutPackage build → `CloseoutReducer` → `CloseoutProjection.terminal_status=SUCCEEDED`，且 `checked_refs` 覆盖 §3.2 三件 readiness 与全部 ref。
5. `AgentContextIndexEntry` 用真实 `entry.snapshot.*` schema 构造，readiness 通过。

### 8.3 验证命令

```powershell
$env:PYTHONPATH = "src;."
python -m pytest tests/contracts/test_hashes.py tests/closeout tests/negative tests/audit -q --basetemp=.pytest-tmp-v2070g
```

成功标准：全部测试通过，且：

- 新增 `tests/contracts/test_hashes.py`：覆盖 §8.1 第 14 条。
- 新增 `tests/closeout/test_closeout_closure_hardening.py`：覆盖 §8.1 其余 negative + §8.2 happy。
- `git grep -n "verifier.unresolved\|process_audit_projection"` 返回 0 行。
- `git grep -n "_is_placeholder_sha256"` 仅命中 `contracts/hashes.py` 内部定义。
- `git grep -n "getattr(entry, \"execution_package_ref\""` 返回 0 行。

## 9. 风险与回滚

- **风险**：删除 `verifier.unresolved` / `process_audit_projection` 等 sentinel 会让既有依赖这些行为的测试 fixture 失败。**处理**：本次必须迁移 fixture，不允许保留旧 sentinel；fixture 迁移作为 §7 步骤 13 的一部分。
- **风险**：`Sha256Hex` 强校验会拒绝既有 fixture 中"a"*64 这类常用 dummy hash。**处理**：fixture 改为真实 `hashlib.sha256(...)` 计算结果；不在产品代码里给 dummy 网开一面。
- **风险**：`GitAuditAdapter` 改为模板可能与外层调用方耦合面变化。**处理**：仅本项目内有一个调用点（V2-070D），同步改造，并补 boundary test 证明无法注入任意 argv。
- **回滚策略**：单提交可独立 revert；如果 step 4~12 中任何一步阻塞，回滚到 step 1（hashes 模块）保持 forward-compatible，不需要回滚到 V2-070F。

## 10. 同步更新

完成本工作包后：

- `doc/04-implementation/backlog.md`：在 V2-070 段尾新增 `V2-070G: closeout closure 硬化`，状态、输入、依赖、输出、negative tests、happy path、验收口径九项要素齐备；总数 47/53 → 48/54（或按当时实际口径修正）。
- `doc/04-implementation/acceptance-criteria.md`：在 Phase 7 / Phase 7.5（新增）下增加 "Closeout closure fail-closed coverage" checkbox 并指向本 spec。
- `doc/04-implementation/INDEX.md`：登记新文件。
- 不更新 `doc/05-project-log/`，留待 commit message + backlog 完成证据承载。
