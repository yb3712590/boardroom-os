# V2-050C FinalEvidenceTable 设计 Spec

## 1. 现实场景

本轮对应的现实场景是：worker（实施智能体）、provider（模型供应商）和 runner（命令运行器）已经产出多条 VerifiedEvidence（已验证证据），但项目经理或 checker（检查者）不能靠“某条证据验证通过”就判断项目可以收尾。收尾前必须有一张总表，逐项回答 active AcceptanceContract（活跃验收合同）里每个 blocking criterion（阻塞验收项）是否已被真实证据覆盖。

通俗地说，V2-050B EvidenceVerifier（证据验证器）像“发票验真员”：它证明单张发票是真的。V2-050C FinalEvidenceTable（最终证据表）像“报销汇总表”：它必须按报销清单逐项确认该有的发票是否都有、是否失败。只要 acceptance map（验收映射，即最终 rows）为空、任一 blocking criterion（阻塞验收项）缺证据，或任一 acceptance_ref（验收引用）存在 failed blocker（失败阻断项），整张表都不能 complete（完成）。checker notes（检查者备注）不属于 V2-050C；V2-050C 通过“不提供 notes 逃生口”防止备注遮蔽失败。

## 2. 目标

实现 FinalEvidenceTable（最终证据表）的最小边界：

1. 按 active AcceptanceContract（活跃验收合同）的 blocking criteria（阻塞验收项）生成每个 acceptance_ref（验收引用）的 evidence row（证据行）。
2. 汇总 VerifiedEvidence（已验证证据）对 acceptance_ref 的覆盖关系。
3. 显式表达 `satisfied`、`missing`、`failed` 三种 FinalEvidenceStatus（最终证据状态）。
4. 拒绝空 acceptance map（验收映射，即 rows 为空）。
5. 拒绝 blocking criterion（阻塞验收项）缺 evidence row（证据行）或缺 verified_evidence_refs（已验证证据引用）。
6. 拒绝 notes（备注）字段进入 FinalEvidenceTable（最终证据表）或 FinalEvidenceRow（最终证据行），避免 V2-050C 出现备注覆盖失败的语义。
7. 产出 closeout（收尾）和 checker（检查者）可消费的 complete/incomplete 判定。
8. 保持 V2-050C 只做 evidence aggregation（证据聚合），不替代 EvidenceVerifier（证据验证器）、CheckerVerdict（检查结论）或 CloseoutGate（收尾门禁）。

## 3. 非目标

V2-050C 不做以下事情：

1. 不验证 artifact/hash/provider/command/fallback facts（产物 / 哈希 / 模型调用 / 命令 / 降级事实）；这些属于 V2-050B EvidenceVerifier（证据验证器）。
2. 不把 EvidenceClaim（证据声明）直接变成 evidence row（证据行）；输入必须是 VerifiedEvidence（已验证证据）或显式 failed blocker（失败阻断项）。
3. 不消费 EvidenceVerificationResult（证据验证结果）；调用方必须先把其中的 blockers（阻断项）转换成 FinalEvidenceBlocker（最终证据阻断项）。
4. 不消费、存储或解释 checker notes（检查者备注）；notes 属于 V2-050D CheckerVerdict（检查结论）。
5. 不运行 command（命令）、不调用 provider（模型供应商）、不写 artifact（产物）。
6. 不实现 CheckerVerdict（检查结论）或 checker（检查者）策略；这些属于 V2-050D。
7. 不生成 rework ticket（返工任务）；这些属于 V2-050E。
8. 不接入 TicketReducer（任务状态归约器）completion gate（完成门禁）；这些属于 V2-050F。
9. 不构建 SourceInventory（源码清单）；最终 source lineage（源码来源链）仍由 V2-060C 证明。
10. 不决定 project closeout（项目收尾）；closeout 只消费 complete FinalEvidenceTable（最终证据表）作为输入之一。
11. 不读取旧 runtime（旧运行时）或旧 contracts（旧合同）作为实现依据。

## 4. 选型结论

采用“显式 failed 的 active-contract coverage table（活跃合同覆盖表）”方案，并把 notes（备注）完全留给 V2-050D CheckerVerdict（检查结论）。

### 4.1 被采用方案：显式 `satisfied / missing / failed`

FinalEvidenceTableBuilder（最终证据表构建器）消费 active AcceptanceContract（活跃验收合同）、VerifiedEvidence（已验证证据）集合和显式 FinalEvidenceBlocker（最终证据阻断项），按 blocking criterion（阻塞验收项）生成 coverage rows（覆盖行）：

- 有足够 VerifiedEvidence（已验证证据）且无 failed blocker（失败阻断项）时为 `satisfied`。
- 没有任何可用 VerifiedEvidence（已验证证据）时为 `missing`。
- 存在 failed blocker（失败阻断项）时为 `failed`，即使同一 acceptance_ref 也有 VerifiedEvidence（已验证证据）。

优点：

- 精确覆盖 backlog（待办）要求的“acceptance map 为空、blocking criterion missing、failed evidence 被 notes 覆盖必须失败”。其中 notes 覆盖失败通过“V2-050C 无 notes 字段、额外字段 fail closed（失败关闭）”证明。
- 与 `doc/03-architecture/contract-and-evidence-model.md` 中 FinalEvidenceTable（最终证据表）的官方字段保持一致：`acceptance_ref / status / verified_evidence_refs / blockers`。
- 与 fail closed（失败关闭）原则一致。
- 为 V2-050D CheckerVerdict（检查结论）提供明确输入：checker 只能消费 failed/missing row（失败 / 缺失行），不能在 V2-050C 层写备注清除它们。
- 为 V2-070 CloseoutGate（收尾门禁）提供稳定 `complete` 判定。

代价：

- 相比只表达 missing（缺失）的模型，多一个 FinalEvidenceBlocker（最终证据阻断项）输入类型。
- Checker notes（检查者备注）的完整负例需要 V2-050D 再闭合；V2-050C 只证明 evidence table（证据表）层没有 notes 逃生口。

### 4.2 未采用方案：只认 `missing`

FinalEvidenceTable（最终证据表）只检查 blocking acceptance_ref（阻塞验收引用）是否存在 VerifiedEvidenceRef（已验证证据引用），失败细节留给 EvidenceVerifier（证据验证器）。

不采用原因：无法在 V2-050C 直接表达 failed evidence（失败证据）一等状态，也会让 V2-050D CheckerVerdict（检查结论）承担过多聚合职责。

### 4.3 未采用方案：直接消费 EvidenceVerificationResult（证据验证结果）

FinalEvidenceTable（最终证据表）同时接收成功和失败的 EvidenceVerificationResult（证据验证结果），由表格内部判断 verified/failed/missing。

不采用原因：会把 V2-050B EvidenceVerifier（证据验证器）的 per-claim verification（单条声明验证）过程泄漏到 V2-050C，导致表格构建器既像 verifier（验证器）又像 aggregator（聚合器）。V2-050C 应消费 verifier 已产出的稳定事实，而不是重新参与验证过程。

## 5. 已决实施决定

1. FinalEvidenceTable（最终证据表）只覆盖 active AcceptanceContract（活跃验收合同）的 blocking criteria（阻塞验收项）。非 blocking criteria（非阻塞验收项）保留在 AcceptanceContract（验收合同）中供 audit（审计）读取，但不生成 V2-050C row（行），也不影响 `complete`。
2. AcceptanceContract.status（验收合同状态）必须为 active；inactive/draft contract（非活跃 / 草稿合同）不能构建 complete table（完成表）。
3. acceptance map（验收映射）在 V2-050C 中专指 FinalEvidenceTable.rows（最终证据表行集合）。rows 为空与 blocking_criteria() 为空属于同一失败路径：无法构建可收尾的验收映射。
4. VerifiedEvidence（已验证证据）是 satisfied（满足）的唯一正向来源；EvidenceClaim（证据声明）不能进入 FinalEvidenceTable（最终证据表）。
5. Failed evidence（失败证据）通过显式 FinalEvidenceBlocker（最终证据阻断项）表达。FinalEvidenceTableBuilder（最终证据表构建器）只接受 typed blocker（类型化阻断项），不接受 EvidenceVerificationResult（证据验证结果）。
6. 调用方负责把 EvidenceVerificationResult.blockers（证据验证结果阻断项）结合 claim/obligation context（声明 / 义务上下文）转换成 FinalEvidenceBlocker（最终证据阻断项）。转换时必须提供 acceptance_ref、related_ref 和 source；builder 不推断失败 blocker 来源。
7. 同一个 acceptance_ref（验收引用）只要存在 FinalEvidenceBlocker（最终证据阻断项），该 row（行）状态就是 `failed`，不能被 VerifiedEvidence（已验证证据）覆盖。
8. blocking criterion（阻塞验收项）没有 VerifiedEvidenceRef（已验证证据引用）且没有 failed blocker（失败阻断项）时，状态为 `missing`。
9. 只有所有 blocking rows（阻塞行）状态都是 `satisfied` 时，FinalEvidenceTable.complete（最终证据表完成标记）才为 true。
10. V2-050C 不定义 FinalEvidenceNote（最终证据备注）、row.notes（行备注）或 table.notes（表备注）。Pydantic extra fields（额外字段）必须 forbid（禁止）；任何 notes 字段尝试进入 table/input/row 都必须 fail closed（失败关闭）。
11. VerifiedEvidence（已验证证据）的 acceptance_refs（验收引用）可以覆盖多个 acceptance_ref；builder（构建器）按每个 acceptance_ref 拆分映射，但不拆分 VerifiedEvidence 本身。
12. VerifiedEvidence.acceptance_refs 中任一 ref 不属于 active contract（活跃合同）必须 fail closed（失败关闭），避免把外部证据混入当前合同。
13. VerifiedEvidence.acceptance_refs 只覆盖 non-blocking criteria（非阻塞验收项）时，不能满足任何 blocking row（阻塞行）。
14. VerifiedEvidence.required_artifact_type（已验证证据必需产物类型）不在该 criterion.evidence_required（验收项必需证据）派生范围内时，本工作包不重新解释文本语义；是否引入 evidence requirement mapping（证据需求映射）留给后续合同增强。V2-050C 首版只要求 evidence 与 acceptance_ref 显式绑定。
15. FinalEvidenceTable（最终证据表）不证明 SourceInventory lineage（源码清单来源链）；它只保留 VerifiedEvidenceRef（已验证证据引用）和 blocker refs（阻断引用）供后续 V2-060C/V2-070 消费。
16. FinalEvidenceTable（最终证据表）必须可 audit-friendly JSON（审计友好 JSON）序列化，便于 V2-070C process audit（流程审计）生成 evidence-map.json（证据映射 JSON）。
17. FinalEvidenceTableRef（最终证据表引用）必须使用 deterministic id（确定性 ID）：`final-evidence-table.<acceptance_contract_id>`。调用方传入不同 ID 或构造出不匹配 ID 必须 fail closed（失败关闭）。

## 6. 模块设计

### 6.1 `src/boardroom_os/evidence/table.py`

新增模块包含：

- `FinalEvidenceTableError`（最终证据表错误）
- `FinalEvidenceTableRef`（最终证据表引用）
- `FinalEvidenceStatus`（最终证据状态）
- `FinalEvidenceBlockerCode`（最终证据阻断代码）
- `FinalEvidenceBlocker`（最终证据阻断项）
- `FinalEvidenceRow`（最终证据行）
- `FinalEvidenceTable`（最终证据表）
- `FinalEvidenceTableInput`（最终证据表输入）
- `FinalEvidenceTableBuilder`（最终证据表构建器）

### 6.2 FinalEvidenceStatus

枚举值：

```text
satisfied
missing
failed
```

语义：

- `satisfied`：该 acceptance_ref（验收引用）有至少一条 VerifiedEvidenceRef（已验证证据引用），且无 blocker（阻断项）。
- `missing`：该 acceptance_ref 没有 VerifiedEvidenceRef，也没有 failed blocker；代表还缺 evidence（证据）。
- `failed`：该 acceptance_ref 有一个或多个 blocker；代表已有失败事实或失败证据，不能被 VerifiedEvidence 覆盖。

### 6.3 FinalEvidenceBlocker

建议 schema：

```yaml
blocker_id:
code:
message:
acceptance_ref:
related_ref:
source:
```

字段说明：

- `blocker_id`：NonEmptyTextValue（非空文本值），可由 code + acceptance_ref + related_ref 派生。
- `code`：FinalEvidenceBlockerCode（最终证据阻断代码）。
- `message`：人类可读说明。
- `acceptance_ref`：被阻断的 AcceptanceRef（验收引用）。
- `related_ref`：关联 EvidenceVerificationBlocker（证据验证阻断项）、EvidenceClaimRef（证据声明引用）、VerifiedEvidenceRef（已验证证据引用）或审计事实引用。
- `source`：短文本来源，例如 `evidence_verifier`、`checker_preflight`、`manual_review_import`。

建议 code：

```text
failed_evidence
unknown_acceptance_ref
invalid_acceptance_map
inactive_acceptance_contract
```

`invalid_acceptance_map` 覆盖 rows 为空、blocking_criteria() 为空、缺 blocking row（阻塞行）等无法构建有效验收映射的情况。

### 6.4 Blocker 输入来源协议

V2-050C 明确不消费 EvidenceVerificationResult（证据验证结果）。如果调用方要把 EvidenceVerifier（证据验证器）的失败结果纳入 FinalEvidenceTable（最终证据表），必须在调用 builder 前完成转换：

```text
EvidenceVerificationResult.blockers
  + EvidenceClaim.acceptance_refs 或 EvidenceObligation.acceptance_refs
  + source label（来源标签）
  -> FinalEvidenceBlocker
```

转换要求：

1. 每个 FinalEvidenceBlocker.acceptance_ref 必须来自同一失败 claim/obligation 的 acceptance_refs，并且属于 active blocking criteria（活跃阻塞验收项）。
2. related_ref 必须指向可审计来源，例如 EvidenceVerificationBlocker.related_ref、EvidenceClaimRef（证据声明引用）或 EvidenceObligationRef（证据义务引用）。
3. source 必须声明转换来源，例如 `evidence_verifier`。
4. 若一个 EvidenceVerificationBlocker 影响多个 acceptance_ref，调用方必须拆成多条 FinalEvidenceBlocker，每条绑定一个 acceptance_ref。
5. Builder 只校验 FinalEvidenceBlocker 的类型、acceptance_ref 归属和 row 状态，不反向读取 EvidenceVerificationResult。

### 6.5 FinalEvidenceRow

建议 schema：

```yaml
acceptance_ref:
statement:
status:
verified_evidence_refs:
blockers:
```

字段说明：

- `acceptance_ref`：AcceptanceRef（验收引用）。
- `statement`：AcceptanceCriterion.statement（验收项陈述）的快照，用于 audit（审计）。
- `status`：FinalEvidenceStatus（最终证据状态）。
- `verified_evidence_refs`：tuple[VerifiedEvidenceRef, ...]。
- `blockers`：tuple[FinalEvidenceBlocker, ...]。

不变量：

1. `status == satisfied` 时，verified_evidence_refs 非空且 blockers 为空。
2. `status == missing` 时，verified_evidence_refs 为空且 blockers 为空。
3. `status == failed` 时，blockers 非空；verified_evidence_refs 可以为空或非空，但不能改变 failed 状态。
4. Row 不含 notes 字段；任何 extra notes 字段必须被 Pydantic extra forbid 拒绝。

### 6.6 FinalEvidenceTable

建议 schema：

```yaml
version: 1
final_evidence_table_id:
acceptance_contract_ref:
generated_at:
rows:
complete:
```

字段说明：

- `final_evidence_table_id`：FinalEvidenceTableRef（最终证据表引用），必须等于 `final-evidence-table.<acceptance_contract_ref.value>`。
- `acceptance_contract_ref`：ContractId（合同 ID），指向 active AcceptanceContract（活跃验收合同）。
- `generated_at`：timezone-aware datetime（带时区时间）。
- `rows`：tuple[FinalEvidenceRow, ...]，每个 blocking acceptance_ref 一行。
- `complete`：bool（布尔值），仅当所有 rows.status 都为 satisfied 时为 true。

不变量：

1. rows 不得为空。
2. row.acceptance_ref 必须唯一。
3. complete 必须由 rows 派生，不允许调用方自由设置。
4. 任何 `missing` 或 `failed` row 都使 complete 为 false。
5. Table 不含 notes 字段；任何 extra notes 字段必须被 Pydantic extra forbid 拒绝。

### 6.7 FinalEvidenceTableInput

建议 schema：

```yaml
active_acceptance_contract:
verified_evidence:
failed_blockers:
generated_at:
```

字段说明：

- `active_acceptance_contract`：AcceptanceContract（验收合同），必须 status=active。
- `verified_evidence`：tuple[VerifiedEvidence, ...]。
- `failed_blockers`：tuple[FinalEvidenceBlocker, ...]，可为空。
- `generated_at`：timezone-aware datetime（带时区时间）。

Input 不含 notes 字段；任何 extra notes 字段必须 fail closed（失败关闭）。

## 7. Builder 行为

FinalEvidenceTableBuilder.build(input)（最终证据表构建函数）执行以下步骤：

1. 校验 active_acceptance_contract.status == active。
2. 读取 active_acceptance_contract.blocking_criteria()（阻塞验收项）。若为空，失败；这是 acceptance map（验收映射）为空的源头失败。
3. 建立 blocking_acceptance_refs（阻塞验收引用集合）。
4. 校验每条 VerifiedEvidence.acceptance_refs 全部属于 active contract criteria（活跃合同条目）。若出现未知 ref，失败。
5. 校验每条 failed blocker.acceptance_ref 属于 blocking_acceptance_refs。若出现未知 ref，失败。
6. 按 acceptance_ref 聚合 verified_evidence_refs，只聚合属于 blocking_acceptance_refs 的 refs。
7. 按 acceptance_ref 聚合 failed_blockers。
8. 为每个 blocking criterion 生成 FinalEvidenceRow。
9. 若某 acceptance_ref 有 blockers，则 row.status = failed。
10. 否则若某 acceptance_ref 有 verified_evidence_refs，则 row.status = satisfied。
11. 否则 row.status = missing。
12. 若任何 row.status != satisfied，则 complete = false。
13. 若所有 row.status == satisfied，则 complete = true。
14. 生成 final_evidence_table_id，必须为 `final-evidence-table.<acceptance_contract_id>`。
15. 返回 FinalEvidenceTable（最终证据表）。

关键点：builder（构建器）不读取 notes（备注），也不接受 EvidenceVerificationResult（证据验证结果）。

## 8. 数据流

```text
AcceptanceContract（验收合同）
  -> blocking_criteria（阻塞验收项）

VerifiedEvidence（已验证证据）
  -> acceptance_refs（验收引用）
  -> verified_evidence_refs（已验证证据引用）

FinalEvidenceBlocker（最终证据阻断项）
  <- caller converts from verifier/checker/preflight context（调用方转换）
  -> failed evidence / verifier blocker（失败证据 / 验证器阻断项）

FinalEvidenceTableBuilder（最终证据表构建器）
  -> FinalEvidenceTable（最终证据表）
  -> CheckerVerdict（检查结论，V2-050D）
  -> CompletionGate（完成门禁，V2-050F）
  -> CloseoutGate（收尾门禁，V2-070A）
```

## 9. Fail-closed 规则

以下情况必须失败或生成 incomplete table（未完成表），不得 closeout-ready（可收尾）：

1. active_acceptance_contract 不是 AcceptanceContract（验收合同）实例。
2. active_acceptance_contract.status 不是 active。
3. active_acceptance_contract.blocking_criteria() 为空，即无法生成非空 acceptance map（验收映射）。
4. generated_at 无时区。
5. rows 为空。
6. row.acceptance_ref 重复。
7. blocking criterion（阻塞验收项）没有对应 row。
8. VerifiedEvidence.acceptance_refs 为空或包含未知 acceptance_ref。
9. VerifiedEvidence.acceptance_refs 只覆盖 non-blocking criterion（非阻塞验收项），却被用来满足 blocking row。
10. failed blocker.acceptance_ref 不属于 active blocking criteria。
11. row.status == satisfied 但 verified_evidence_refs 为空。
12. row.status == satisfied 但 blockers 非空。
13. row.status == missing 但 verified_evidence_refs 非空或 blockers 非空。
14. row.status == failed 但 blockers 为空。
15. complete == true 但存在 missing row。
16. complete == true 但存在 failed row。
17. complete == true 但 acceptance_ref 覆盖不等于 active blocking criteria 覆盖。
18. final_evidence_table_id 不等于 `final-evidence-table.<acceptance_contract_ref.value>`。
19. 传入 EvidenceClaim（证据声明）、EvidenceVerificationResult（证据验证结果）或原始 dict（字典）试图绕过 VerifiedEvidence（已验证证据）与 FinalEvidenceBlocker（最终证据阻断项）类型边界。
20. table/input/row 出现 notes 字段或其它 extra fields（额外字段）。
21. failed evidence（失败证据）试图通过 VerifiedEvidence（已验证证据）或 notes（备注）覆盖为 satisfied（满足）。

## 10. Happy path

### 10.1 单个 blocking criterion satisfied

1. active AcceptanceContract（活跃验收合同）包含一个 blocking criterion（阻塞验收项）。
2. 输入一条 VerifiedEvidence（已验证证据），其 acceptance_refs 包含该 acceptance_ref。
3. failed_blockers 为空。
4. FinalEvidenceTableBuilder 返回一行 `satisfied`。
5. complete 为 true。
6. final_evidence_table_id 等于 `final-evidence-table.<acceptance_contract_id>`。

### 10.2 多个 blocking criteria 全部 satisfied

1. active AcceptanceContract 包含 backend、frontend、command 三个 blocking acceptance_ref。
2. 输入多条 VerifiedEvidence，分别覆盖这些 acceptance_ref。
3. builder 为每个 blocking criterion 生成一行。
4. 每行都有 verified_evidence_refs。
5. complete 为 true。

### 10.3 missing criterion blocks closeout

1. active AcceptanceContract 包含两个 blocking criteria。
2. VerifiedEvidence 只覆盖其中一个。
3. 未覆盖的 row 状态为 `missing`。
4. complete 为 false。
5. table 可被 checker（检查者）用于生成 rework（返工）输入。

### 10.4 failed evidence blocks closeout

1. active AcceptanceContract 包含一个 blocking criterion。
2. 输入该 criterion 的 FinalEvidenceBlocker（最终证据阻断项）。
3. row.status 为 `failed`。
4. complete 为 false。

### 10.5 verified evidence can coexist with blocker but cannot clear it

1. 输入某 acceptance_ref 的 VerifiedEvidence。
2. 同时输入同一 acceptance_ref 的 FinalEvidenceBlocker。
3. row 保留 verified_evidence_refs 用于 audit。
4. row.status 为 `failed`。
5. complete 为 false。

## 11. 测试计划

新增测试：

- `tests/evidence/test_final_evidence_table.py`
- `tests/negative/test_missing_acceptance_map_blocks_closeout.py`

### 11.1 Negative tests（先写）

`tests/negative/test_missing_acceptance_map_blocks_closeout.py`：

1. `test_final_evidence_table_rejects_inactive_acceptance_contract`
2. `test_final_evidence_table_rejects_empty_acceptance_map`
3. `test_final_evidence_table_marks_blocking_criterion_missing`
4. `test_final_evidence_table_rejects_unknown_verified_evidence_acceptance_ref`
5. `test_final_evidence_table_rejects_unknown_failed_blocker_acceptance_ref`
6. `test_final_evidence_table_rejects_notes_input`
7. `test_verified_evidence_cannot_clear_failed_evidence_blocker`
8. `test_complete_table_cannot_contain_missing_rows`
9. `test_complete_table_cannot_contain_failed_rows`
10. `test_final_evidence_row_rejects_satisfied_without_verified_evidence_refs`
11. `test_final_evidence_row_rejects_satisfied_with_blockers`
12. `test_final_evidence_row_rejects_failed_without_blockers`
13. `test_final_evidence_table_rejects_duplicate_acceptance_rows`
14. `test_final_evidence_table_rejects_claim_dict_as_verified_evidence`
15. `test_final_evidence_table_rejects_verification_result_input`
16. `test_final_evidence_table_rejects_non_deterministic_table_id`

### 11.2 Happy path tests

`tests/evidence/test_final_evidence_table.py`：

1. `test_single_blocking_criterion_is_satisfied_by_verified_evidence`
2. `test_multiple_blocking_criteria_are_all_satisfied`
3. `test_verified_evidence_can_cover_multiple_acceptance_refs`
4. `test_missing_criterion_produces_incomplete_table`
5. `test_failed_evidence_produces_incomplete_table`
6. `test_verified_evidence_and_failed_blocker_preserve_audit_refs`
7. `test_final_evidence_table_serializes_as_audit_friendly_json`
8. `test_complete_is_derived_from_rows`
9. `test_final_evidence_table_uses_deterministic_contract_id`

### 11.3 Regression scope

实现完成后至少运行：

```bash
PYTHONPATH="src:." python -m pytest tests/negative/test_missing_acceptance_map_blocks_closeout.py -q
PYTHONPATH="src:." python -m pytest tests/evidence/test_final_evidence_table.py -q
PYTHONPATH="src:." python -m pytest tests/evidence/test_evidence_verifier.py tests/evidence/test_final_evidence_table.py tests/negative/test_synthetic_evidence_rejected.py tests/negative/test_missing_acceptance_map_blocks_closeout.py -q
PYTHONPATH="src:." python -m pytest tests/contracts tests/reducers tests/execution tests/evidence tests/negative -q
```

## 12. 与现有模块的关系

1. 复用 `boardroom_os.contracts.acceptance.AcceptanceContract`（验收合同）和 AcceptanceCriterion（验收项）。
2. 复用 `boardroom_os.contracts.types.AcceptanceRef`（验收引用）、ContractId（合同 ID）和 NonEmptyTextValue（非空文本值）。
3. 复用 `boardroom_os.evidence.verifier.VerifiedEvidence`（已验证证据）、VerifiedEvidenceRef（已验证证据引用）、EvidenceVerificationBlocker（证据验证阻断项）和 EvidenceVerificationBlockerCode（证据验证阻断代码），但不直接消费 EvidenceVerificationResult（证据验证结果）。
4. 不修改 `boardroom_os.evidence.verifier.EvidenceVerifier`（证据验证器）；V2-050C 只消费其成功产物 VerifiedEvidence（已验证证据），失败产物需由调用方转换为 FinalEvidenceBlocker（最终证据阻断项）。
5. 不修改 `boardroom_os.evidence.claim.EvidenceClaim`（证据声明）；claim 不进入 FinalEvidenceTable（最终证据表）。
6. 不修改 RuntimeExecutor（运行时执行器）、CommandRunner（命令运行器）或 ProviderExecutor（模型供应商执行器）。
7. 不修改 TicketReducer（任务状态归约器）；V2-050F 再接入 formal completion gate（正式完成门禁）。
8. 不修改 SourceInventory（源码清单）；V2-060C 再证明 implementation lineage（实现来源链）。

## 13. 验收映射

本 spec 对应 backlog 工作包：V2-050C。

覆盖 `backlog.md` 中 V2-050C 的验收口径：

- acceptance map（验收映射，即 rows）为空必须失败。
- blocking criterion missing（阻塞验收项缺证据）必须失败。
- failed evidence（失败证据）被 notes（备注）覆盖必须失败：V2-050C 通过拒绝 notes 字段和保持 failed row 优先级证明表格层无覆盖路径；V2-050D 再闭合 checker notes（检查者备注）语义。
- 所有 blocking criteria 都有 verified_evidence_refs（已验证证据引用）且无 blockers（阻断项）时 table complete（表完成）。
- closeout（收尾）只能消费 complete FinalEvidenceTable（最终证据表）。

覆盖 `acceptance-criteria.md`：

- AC-V2-EVIDENCE-003（evidence map complete，证据映射完整）：由 V2-050C `test_missing_acceptance_map_blocks_closeout.py` 和 `test_final_evidence_table.py` 证明。
- AC-V2-CHECKER-002（notes do not clear blockers，备注不能清除阻断项）：V2-050C 只证明 evidence table（证据表）层没有 notes 逃生口；V2-050D CheckerVerdict（检查结论）负责 checker notes 的最终闭合。

完成 V2-050C implementation（实施）后应按 backlog 完成协议更新：

1. `doc/04-implementation/backlog.md`：V2-050C 状态改为 DONE，当前未完成工作包指向 V2-050D，Phase 5 进度改为 4/7，合计改为 32/53。
2. `doc/04-implementation/acceptance-criteria.md`：勾选 AC-V2-EVIDENCE-003；不要勾选 CheckerVerdict（检查结论）相关 checkbox，除非 V2-050D 已完成。
3. `doc/05-project-log/2026-05.md`：追加 V2-050C 记录，包含关键产出文件、negative/happy tests 和验证命令。
4. `doc/04-implementation/INDEX.md`：本 spec 文档索引项已存在；若新增 implementation plan（实施计划）文档，再同步加入。
5. `doc/05-project-log/decisions.md`：本次收口选择“notes 不进入 V2-050C”与架构契约一致，不需要新增 DEC；若 implementation 阶段改变 V2-050C/V2-050D 分工或 closeout 消费语义，则新增 DEC。

## 14. 同行评审后收口决策

1. Notes（备注）不属于 V2-050C。V2-050C 的官方字段保持 `acceptance_ref / status / verified_evidence_refs / blockers`；checker notes（检查者备注）留给 V2-050D。
2. Failed blockers（失败阻断项）通过 FinalEvidenceBlocker（最终证据阻断项）输入。EvidenceVerificationResult（证据验证结果）到 FinalEvidenceBlocker 的转换由调用方负责，builder 不消费 verifier result（验证器结果）。
3. acceptance map（验收映射）在 V2-050C 中专指 FinalEvidenceTable.rows（最终证据表行集合）。blocking_criteria() 为空会导致 rows 为空，因此属于同一失败路径。
4. FinalEvidenceTableRef（最终证据表引用）ID 模板 `final-evidence-table.<acceptance_contract_id>` 是强约束。
5. Non-blocking criteria（非阻塞验收项）不进入 V2-050C rows；它们保留在 AcceptanceContract（验收合同）中，V2-070C process audit（流程审计）可通过合同快照展示。

## 15. 已收敛评审点

1. V2-050C 不验证单条 evidence（证据）真假，只聚合 VerifiedEvidence（已验证证据）。
2. EvidenceClaim（证据声明）不得进入 FinalEvidenceTable（最终证据表）。
3. EvidenceVerificationResult（证据验证结果）不得进入 FinalEvidenceTableBuilder（最终证据表构建器）；调用方必须先转换失败阻断项。
4. `failed` 是一等状态，不能被 VerifiedEvidence（已验证证据）覆盖。
5. V2-050C 没有 notes 字段；任何 notes extra field（备注额外字段）都必须 fail closed（失败关闭）。
6. `missing` 表示 blocking criterion（阻塞验收项）还没有 verified evidence（已验证证据）或 failed blocker（失败阻断项）。
7. `complete=True` 只能在所有 blocking rows（阻塞行）均为 `satisfied` 时出现。
8. FinalEvidenceTable（最终证据表）是 V2-050D CheckerVerdict（检查结论）、V2-050F CompletionGate（完成门禁）和 V2-070A CloseoutGate（收尾门禁）的输入，不是最终收尾判定本身。
