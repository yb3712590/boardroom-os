# V2-050D CheckerVerdict 设计 Spec

## 1. 现实场景

本轮对应的现实场景是：worker（实施智能体）已经提交 WorkProduct（工作产物），EvidenceVerifier（证据验证器）已经把 EvidenceClaim（证据声明）验证成 VerifiedEvidence（已验证证据），FinalEvidenceTable（最终证据表）已经按 active AcceptanceContract（活跃验收合同）汇总 blocking criteria（阻塞验收项）的 satisfied / missing / failed 状态。

接下来需要一个独立 Checker（检查者）做“质量审查员”：它查看 worker 提交的内容、source diff（源码差异）引用、最终证据表和合同，决定是否可以放行当前 ticket（任务）。Checker 不能替 verifier（验证器）补证据，不能把 notes（备注）当 evidence（证据），也不能用“我觉得可以”覆盖 missing / failed row（缺失 / 失败行）。

通俗地说：EvidenceVerifier 像“发票验真员”，FinalEvidenceTable 像“报销汇总表”，CheckerVerdict（检查结论）像“独立审批意见”。审批人可以写非阻断备注，但如果报销汇总表里有缺票或假票，审批人不能靠备注把它签成通过。

## 2. 目标

实现 CheckerVerdict（检查结论）的最小边界：

1. 定义 checker（检查者）可审计输出模型，支持 `APPROVED`、`APPROVED_WITH_NON_BLOCKING_NOTES`、`REWORK_REQUIRED`、`ESCALATE` 四种结论。
2. 让 Checker（检查者）独立消费 WorkProduct（工作产物）、source diff ref（源码差异引用）、FinalEvidenceTable（最终证据表）和 AcceptanceContract（验收合同）。
3. 证明 FinalEvidenceTable（最终证据表） incomplete（未完成）时，checker 不得输出 approved（批准）类结论。
4. 证明 notes（备注）不能覆盖 blocker（阻断项）。
5. 证明 checker service（检查服务）不能自行补 EvidenceClaim（证据声明）、VerifiedEvidence（已验证证据）或 EvidenceVerificationResult（证据验证结果）。
6. 产出 V2-050E rework ticket（返工任务）可消费的 blocker refs（阻断引用），但不生成 rework ticket。
7. 保持 V2-050D 只做 checker verdict（检查结论），不替代 EvidenceVerifier（证据验证器）、FinalEvidenceTableBuilder（最终证据表构建器）、ReworkGenerator（返工生成器）、CompletionGate（完成门禁）或 CloseoutGate（收尾门禁）。

## 3. 非目标

V2-050D 不做以下事情：

1. 不重新验证 artifact/hash/provider/command/fallback facts（产物 / 哈希 / 模型调用 / 命令 / 降级事实）；这些属于 V2-050B EvidenceVerifier（证据验证器）。
2. 不构建 FinalEvidenceTable（最终证据表）；这些属于 V2-050C。
3. 不把 EvidenceClaim（证据声明）转成 VerifiedEvidence（已验证证据）。
4. 不把 EvidenceVerificationResult（证据验证结果）转换成 FinalEvidenceBlocker（最终证据阻断项）。
5. 不生成 rework ticket（返工任务）；这些属于 V2-050E。
6. 不接入 TicketReducer（任务状态归约器）completion gate（完成门禁）；这些属于 V2-050F。
7. 不构建 SourceInventory（源码清单）；source lineage（源码来源链）由 V2-060C 证明。
8. 不决定 project closeout（项目收尾）；closeout 只消费后续 gate（门禁）结果。
9. 不读取旧 runtime（旧运行时）、旧 contracts（旧合同）或旧测试作为实现依据。
10. 不提前设计完整 human review workflow（人工评审流程）；`ESCALATE` 只作为 typed verdict status（类型化结论状态）存在，后续治理流再决定如何消费。

## 4. 选型结论

采用“最小守门 checker verdict（检查结论）”方案：CheckerInput（检查输入）只接受已形成的工作产物、源码差异引用、最终证据表和合同；CheckerService（检查服务）只根据这些事实产出 CheckerVerdict（检查结论）。

### 4.1 被采用方案：最小守门版本

CheckerService（检查服务）消费：

- WorkProduct（工作产物）
- SourceDiffRef（源码差异引用）
- FinalEvidenceTable（最终证据表）
- AcceptanceContract（验收合同）
- optional non-blocking notes（可选非阻断备注）
- optional checker blockers（可选检查者阻断项）

输出 CheckerVerdict（检查结论）。规则：

- final evidence table complete 且无 notes / blockers -> `APPROVED`
- final evidence table complete 且有 notes、无 blockers -> `APPROVED_WITH_NON_BLOCKING_NOTES`
- final evidence table incomplete 或有 blockers -> `REWORK_REQUIRED`
- 输入 contract/table 不一致等治理输入异常 -> fail closed（失败关闭），必要时调用方可构造 `ESCALATE`，但 service 首版不自动把结构错误吞成通过

优点：

- 精确覆盖 backlog（待办）V2-050D：verified evidence incomplete 但 checker approved 必须失败；notes 覆盖 blocker 必须失败；checker 自行补 evidence 必须失败。
- 与 `doc/03-architecture/contract-and-evidence-model.md` 中 Checker（检查者）不能替 verifier 放行的约束一致。
- 为 V2-050E 提供清晰的 blocker refs（阻断引用）输入，不提前固化 rework ticket schema（返工任务结构）。
- 保持 V2-050F 的 reducer completion gate（归约器完成门禁）可以只消费 formal evidence/checker model（正式证据 / 检查模型），不依赖散文备注。

代价：

- V2-050D 不处理真实 diff 内容，只保存 source diff ref（源码差异引用）；后续若需要 deep diff semantics（深度差异语义）需另开工作包或扩展。
- `ESCALATE` 的治理流暂不闭合，只定义为合法 verdict status（结论状态）。

### 4.2 未采用方案：提前生成 rework payload

在 CheckerVerdictBlocker（检查结论阻断项）里直接携带 rework ticket 所需字段，如 new ticket id、dependency refs、evidence obligations。

不采用原因：会把 V2-050E 的职责前移，提前固化 rework ticket（返工任务）结构，破坏工作包边界。

### 4.3 未采用方案：Checker 直接消费 EvidenceClaim / VerifiedEvidence

CheckerService（检查服务）直接接收 EvidenceClaim（证据声明）、VerifiedEvidence（已验证证据）或 EvidenceVerificationResult（证据验证结果），由 checker 判断 evidence completeness（证据完整性）。

不采用原因：会让 checker 替代 EvidenceVerifier（证据验证器）和 FinalEvidenceTableBuilder（最终证据表构建器），重新打开“checker 备注覆盖证据缺口”的风险。

## 5. 已决实施决定

1. V2-050D 新增 `src/boardroom_os/checker/` 包，首批模块为 `verdict.py` 和 `checker.py`。
2. CheckerVerdict（检查结论）是 Pydantic model（Pydantic 模型），`extra="forbid"`，所有关键字段 fail closed（失败关闭）。
3. CheckerVerdictStatus（检查结论状态）枚举固定为：`approved`、`approved_with_non_blocking_notes`、`rework_required`、`escalate`。
4. `APPROVED` 不允许 notes（备注）或 blockers（阻断项）。
5. `APPROVED_WITH_NON_BLOCKING_NOTES` 必须有 notes，且 blockers 为空。
6. `REWORK_REQUIRED` 必须有至少一个 blocker；notes 可存在，但不能消除 blocker。
7. `ESCALATE` 必须有至少一个 blocker（阻断项）；首版不引入 escalation_reason（升级原因）字段，也不由 CheckerService（检查服务）自动生成。
8. FinalEvidenceTable.complete（最终证据表完成标记）为 false 时，CheckerService 不允许产出 approved 类 verdict（结论），必须产出 `REWORK_REQUIRED` 并携带 evidence-table-derived blockers（由证据表派生的阻断项）。
9. FinalEvidenceTable.rows 中任一 `missing` 或 `failed` row 必须映射为 CheckerVerdictBlocker（检查结论阻断项）。
10. Checker notes（检查者备注）只表达非阻断质量建议，不具备证据资格。
11. CheckerServiceInput（检查服务输入）不接受 EvidenceClaim（证据声明）、VerifiedEvidence（已验证证据）、EvidenceVerificationResult（证据验证结果）或 raw evidence dict（原始证据字典）。出现这些字段必须 fail closed。
12. CheckerServiceInput 必须校验 FinalEvidenceTable.acceptance_contract_ref 与 AcceptanceContract.acceptance_contract_id 一致。
13. CheckerServiceInput 必须校验 AcceptanceContract.status 为 active。
14. CheckerServiceInput 必须校验 WorkProduct.ticket_ref 与 checker_input.ticket_ref 一致。
15. CheckerServiceInput 必须校验 source_diff_ref 非空；本包只记录 diff 引用，不读取真实 diff 内容。
16. CheckerServiceInput 必须校验 WorkProduct.artifact_refs 非空、claim_refs 非空；即使 WorkProduct 模型已有校验，checker 边界仍以 typed input（类型化输入）拒绝伪对象或 dict。
17. CheckerVerdict.checker_verdict_id 使用 deterministic id（确定性 ID）：`checker-verdict.<ticket_ref>.<final_evidence_table_ref>`。
18. CheckerVerdict 必须保留 work_product_ref、ticket_ref、acceptance_contract_ref、final_evidence_table_ref、source_diff_ref、checked_at，供 V2-070C process audit（流程审计）回答 checker 看了什么。
19. CheckerVerdict 不直接进入 EventLog（事件日志）；V2-050F 或后续 event taxonomy（事件分类）扩展时再定义 `CHECKER_VERDICT_RECORDED` 之类事件。
20. CheckerService（检查服务）遇到结构性输入异常时必须 raise CheckerVerdictError（检查结论错误），不得返回 `ESCALATE` 或 approved 类 verdict（批准类结论）。
21. `ESCALATE` 首版只作为 CheckerVerdictStatus（检查结论状态）的 schema status（结构状态）存在，由调用方或后续治理流显式构造；CheckerService.review（检查服务审查函数）不自动生成 `ESCALATE`。
22. SourceDiffRef（源码差异引用）首版只实现为 NonEmptyTextValue（非空文本值）子类；不引入 SourceDiffSummary（源码差异摘要），避免提前实现 SourceInventory（源码清单）或深度 diff 语义。
23. CheckerNote.related_ref（检查备注关联引用）必填，保证 V2-070C ProcessAudit（流程审计）可追踪备注对象。
24. CheckerVerdictBlocker.acceptance_ref（检查结论阻断项验收引用）在 schema（结构）上允许为空，以支持 work-product-level blocker（工作产物级阻断）；但由 FinalEvidenceTable row（最终证据表行）派生的 `final_evidence_missing` / `final_evidence_failed` blocker 必须携带 acceptance_ref。
25. V2-050D 不引入 `CHECKER_VERDICT_RECORDED` 事件；等 V2-050F / V2-070 实际消费 checker verdict（检查结论）时再扩展 EventType（事件类型）。

## 6. 模块设计

### 6.1 `src/boardroom_os/checker/verdict.py`

新增 value objects（值对象）与 schema（结构）：

- `CheckerVerdictError`（检查结论错误）
- `CheckerVerdictRef`（检查结论引用）
- `SourceDiffRef`（源码差异引用）
- `CheckerNoteRef`（检查备注引用）
- `CheckerBlockerRef`（检查阻断引用）
- `CheckerVerdictStatus`（检查结论状态）
- `CheckerBlockerCode`（检查阻断代码）
- `CheckerNote`（检查备注）
- `CheckerVerdictBlocker`（检查结论阻断项）
- `CheckerVerdict`（检查结论）

### 6.2 CheckerVerdictStatus

枚举值：

```text
approved
approved_with_non_blocking_notes
rework_required
escalate
```

语义：

- `approved`：证据完整，无 checker notes（检查备注），无 blockers（阻断项）。
- `approved_with_non_blocking_notes`：证据完整，无 blockers，但有非阻断备注。
- `rework_required`：证据表未完成，或 checker 发现阻断项。
- `escalate`：输入事实需要人工/CEO/架构治理判断，不是 implementation approved（实施批准）。

### 6.3 CheckerBlockerCode

建议枚举：

```text
final_evidence_failed
final_evidence_missing
checker_blocker
contract_mismatch
work_product_mismatch
invalid_checker_input
```

语义：

- `final_evidence_failed`：FinalEvidenceRow.status 为 failed。
- `final_evidence_missing`：FinalEvidenceRow.status 为 missing。
- `checker_blocker`：checker 独立发现的阻断问题。
- `contract_mismatch`：FinalEvidenceTable（最终证据表）与 AcceptanceContract（验收合同）不一致。
- `work_product_mismatch`：WorkProduct（工作产物）与 checker input（检查输入）不一致。
- `invalid_checker_input`：输入不满足 checker 边界。

### 6.4 CheckerNote

建议 schema：

```yaml
note_id:
message:
related_ref:
```

字段说明：

- `note_id`：CheckerNoteRef（检查备注引用），可由 related_ref 派生。
- `message`：非空人类可读备注。
- `related_ref`：关联 work product / source diff / acceptance row / artifact ref（工作产物 / 源码差异 / 验收行 / 产物引用）。

不变量：

1. notes 只能进入 `approved_with_non_blocking_notes` 或 `rework_required` / `escalate` 的审计上下文。
2. notes 不能作为 blocker 清除依据。
3. notes 不能包含 `blocking=False` 之类绕过字段；阻断与否由 verdict status 和 blockers 决定。

### 6.5 CheckerVerdictBlocker

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

- `blocker_id`：CheckerBlockerRef（检查阻断引用），可由 code + acceptance_ref + related_ref 派生。
- `code`：CheckerBlockerCode（检查阻断代码）。
- `message`：非空人类可读说明。
- `acceptance_ref`：可选 AcceptanceRef（验收引用）；对 source diff 或 work product 级 blocker 可为空。
- `related_ref`：FinalEvidenceRow / FinalEvidenceBlocker / WorkProduct / SourceDiffRef 等审计引用。
- `source`：短文本来源，例如 `final_evidence_table`、`checker_manual_review`、`checker_input_validator`。

不变量：

1. message / related_ref / source 必须非空。
2. final evidence row 派生 blocker 必须保留 acceptance_ref。
3. blocker 一旦存在，approved 类 status 不合法。

### 6.6 CheckerVerdict

建议 schema：

```yaml
version: 1
checker_verdict_id:
ticket_ref:
work_product_ref:
source_diff_ref:
acceptance_contract_ref:
final_evidence_table_ref:
status:
notes:
blockers:
checked_at:
```

字段说明：

- `checker_verdict_id`：CheckerVerdictRef（检查结论引用），必须等于 `checker-verdict.<ticket_ref>.<final_evidence_table_ref>`。
- `ticket_ref`：TicketId（任务 ID）。
- `work_product_ref`：WorkProductRef（工作产物引用）。
- `source_diff_ref`：SourceDiffRef（源码差异引用）。
- `acceptance_contract_ref`：ContractId（合同 ID）。
- `final_evidence_table_ref`：FinalEvidenceTableRef（最终证据表引用）。
- `status`：CheckerVerdictStatus（检查结论状态）。
- `notes`：tuple[CheckerNote, ...]。
- `blockers`：tuple[CheckerVerdictBlocker, ...]。
- `checked_at`：timezone-aware datetime（带时区时间）。

不变量：

1. checked_at 必须带时区。
2. `approved`：notes 为空，blockers 为空。
3. `approved_with_non_blocking_notes`：notes 非空，blockers 为空。
4. `rework_required`：blockers 非空。
5. `escalate`：blockers 非空；首版不引入 escalation_reason 字段，由调用方或后续治理流显式构造。
6. checker_verdict_id 必须 deterministic（确定性）。
7. 任意 extra fields（额外字段）必须 fail closed。

### 6.7 `src/boardroom_os/checker/checker.py`

新增 service input（服务输入）与 service（服务）：

- `CheckerServiceInput`（检查服务输入）
- `CheckerService`（检查服务）

CheckerServiceInput schema：

```yaml
ticket_ref:
work_product:
source_diff_ref:
active_acceptance_contract:
final_evidence_table:
notes:
checker_blockers:
checked_at:
```

字段说明：

- `ticket_ref`：TicketId（任务 ID）。
- `work_product`：WorkProduct（工作产物），必须是 typed model（类型化模型）。
- `source_diff_ref`：SourceDiffRef（源码差异引用）。
- `active_acceptance_contract`：AcceptanceContract（验收合同），必须 active。
- `final_evidence_table`：FinalEvidenceTable（最终证据表）。
- `notes`：tuple[CheckerNote, ...]，可为空。
- `checker_blockers`：tuple[CheckerVerdictBlocker, ...]，可为空。
- `checked_at`：timezone-aware datetime（带时区时间）。

Input 不接受以下字段：

```text
evidence_claims
verified_evidence
evidence_verification_results
final_evidence_blockers
acceptance_override
force_approved
```

这些字段出现即 extra forbid（禁止额外字段）失败。

## 7. CheckerService 行为

CheckerService.review(input)（检查服务审查函数）执行以下步骤：

1. 校验 input.active_acceptance_contract.status == active。
2. 校验 input.final_evidence_table.acceptance_contract_ref == input.active_acceptance_contract.acceptance_contract_id。
3. 校验 input.work_product.ticket_ref == input.ticket_ref。
4. 校验 input.source_diff_ref 非空。
5. 从 FinalEvidenceTable.rows 中读取 missing / failed rows。
6. 对每个 missing row 生成 CheckerVerdictBlocker：code=`final_evidence_missing`，source=`final_evidence_table`。
7. 对每个 failed row 生成 CheckerVerdictBlocker：code=`final_evidence_failed`，source=`final_evidence_table`，related_ref 优先指向 row.blockers 的 blocker_id；若 row 只有 failed status 却缺 blockers，应由 FinalEvidenceRow 自身 fail closed。
8. 合并 caller 提供的 checker_blockers。
9. 如果 blockers 非空，返回 `REWORK_REQUIRED`。
10. 如果 blockers 为空且 notes 非空，返回 `APPROVED_WITH_NON_BLOCKING_NOTES`。
11. 如果 blockers 为空且 notes 为空，返回 `APPROVED`。
12. 构造 CheckerVerdict（检查结论）时自动填 deterministic checker_verdict_id。
13. 不修改任何输入对象。

关键点：CheckerService（检查服务）从 FinalEvidenceTable（最终证据表）派生 blocker，不从 notes 派生 evidence，也不读取 raw evidence（原始证据）。

## 8. 数据流

```text
WorkProduct（工作产物）
  -> CheckerServiceInput（检查服务输入）

SourceDiffRef（源码差异引用）
  -> CheckerServiceInput

AcceptanceContract（验收合同）
  -> active contract consistency check（活跃合同一致性校验）

FinalEvidenceTable（最终证据表）
  -> missing / failed rows（缺失 / 失败行）
  -> CheckerVerdictBlocker（检查结论阻断项）

CheckerNote（检查备注）
  -> non-blocking audit context（非阻断审计上下文）

CheckerService（检查服务）
  -> CheckerVerdict（检查结论）
  -> V2-050E ReworkGenerator（返工生成器）
  -> V2-050F CompletionGate（完成门禁）
  -> V2-070C ProcessAudit（流程审计）
```

## 9. Fail-closed 规则

以下情况必须失败或输出 `REWORK_REQUIRED`，不得 approved（批准）：

1. active_acceptance_contract 不是 AcceptanceContract（验收合同）实例。
2. active_acceptance_contract.status 不是 active。
3. final_evidence_table 不是 FinalEvidenceTable（最终证据表）实例。
4. final_evidence_table.acceptance_contract_ref 与 active_acceptance_contract.acceptance_contract_id 不一致。
5. work_product 不是 WorkProduct（工作产物）实例。
6. work_product.ticket_ref 与 input.ticket_ref 不一致。
7. source_diff_ref 缺失或空白。
8. checked_at 无时区。
9. FinalEvidenceTable.complete 为 false 时，CheckerService 输出 approved 类状态。
10. FinalEvidenceTable 中存在 missing row，却输出 approved 类状态。
11. FinalEvidenceTable 中存在 failed row，却输出 approved 类状态。
12. CheckerVerdict.status 为 `approved` 但 notes 非空。
13. CheckerVerdict.status 为 `approved` 但 blockers 非空。
14. CheckerVerdict.status 为 `approved_with_non_blocking_notes` 但 notes 为空。
15. CheckerVerdict.status 为 `approved_with_non_blocking_notes` 但 blockers 非空。
16. CheckerVerdict.status 为 `rework_required` 但 blockers 为空。
17. CheckerVerdict.status 为 `escalate` 但 blockers 为空。
18. notes 字段试图携带 blocking / evidence / override 语义。
19. checker service input 出现 EvidenceClaim（证据声明）相关字段。
20. checker service input 出现 VerifiedEvidence（已验证证据）相关字段。
21. checker service input 出现 EvidenceVerificationResult（证据验证结果）相关字段。
22. checker service input 出现 `force_approved`、`acceptance_override` 或类似 override 字段。
23. checker 自行补 evidence refs（证据引用）到 verdict。
24. checker_verdict_id 不符合 `checker-verdict.<ticket_ref>.<final_evidence_table_ref>`。
25. verdict / note / blocker / input 任意 extra fields（额外字段）出现。

## 10. Happy path

### 10.1 Evidence complete -> APPROVED

1. 输入 WorkProduct（工作产物）和 source_diff_ref（源码差异引用）。
2. 输入 active AcceptanceContract（活跃验收合同）。
3. 输入 complete FinalEvidenceTable（完成的最终证据表）。
4. notes 为空，checker_blockers 为空。
5. CheckerService 返回 `APPROVED`。
6. verdict 保留 work_product_ref、ticket_ref、source_diff_ref、acceptance_contract_ref、final_evidence_table_ref。

### 10.2 Evidence complete + notes -> APPROVED_WITH_NON_BLOCKING_NOTES

1. FinalEvidenceTable.complete 为 true。
2. checker 添加一条非阻断 note（备注）。
3. checker_blockers 为空。
4. CheckerService 返回 `APPROVED_WITH_NON_BLOCKING_NOTES`。
5. note 进入 verdict audit shape（审计形状），但不生成 blocker，也不生成 evidence。

### 10.3 Evidence missing -> REWORK_REQUIRED

1. FinalEvidenceTable.complete 为 false。
2. 至少一行 status 为 `missing`。
3. CheckerService 返回 `REWORK_REQUIRED`。
4. verdict.blockers 包含 `final_evidence_missing`，绑定对应 acceptance_ref。

### 10.4 Evidence failed -> REWORK_REQUIRED

1. FinalEvidenceTable.complete 为 false。
2. 至少一行 status 为 `failed`。
3. CheckerService 返回 `REWORK_REQUIRED`。
4. verdict.blockers 包含 `final_evidence_failed`，保留 FinalEvidenceBlocker（最终证据阻断项）的 related ref。

### 10.5 Evidence complete + checker blocker -> REWORK_REQUIRED

1. FinalEvidenceTable.complete 为 true。
2. checker 独立发现 blocking issue（阻断问题），例如 source diff 与 work product summary 不一致。
3. caller 传入 CheckerVerdictBlocker（检查结论阻断项）。
4. CheckerService 返回 `REWORK_REQUIRED`。
5. notes 即使存在也不能改变 status。

## 11. 测试计划

新增测试：

- `tests/evidence/test_checker_verdict.py`

由于 backlog（待办）只声明一个测试文件，V2-050D 的 negative tests（负例测试）和 happy path tests（正向测试）都放在该文件内；文件内先写 negative section（负例段），再写 happy path section（正例段）。

### 11.1 Negative tests（先写）

`tests/evidence/test_checker_verdict.py`：

1. `test_checker_service_rejects_inactive_acceptance_contract`
2. `test_checker_service_rejects_contract_mismatch`
3. `test_checker_service_rejects_work_product_ticket_mismatch`
4. `test_checker_service_rejects_missing_source_diff_ref`
5. `test_checker_service_rejects_evidence_claim_inputs`
6. `test_checker_service_rejects_verified_evidence_inputs`
7. `test_checker_service_rejects_verification_result_inputs`
8. `test_checker_service_rejects_force_approved_override`
9. `test_incomplete_final_evidence_table_cannot_be_approved`
10. `test_missing_evidence_row_becomes_rework_blocker`
11. `test_failed_evidence_row_becomes_rework_blocker`
12. `test_notes_cannot_clear_evidence_blocker`
13. `test_checker_blocker_forces_rework_even_when_evidence_complete`
14. `test_approved_verdict_rejects_notes`
15. `test_approved_verdict_rejects_blockers`
16. `test_approved_with_notes_requires_notes`
17. `test_approved_with_notes_rejects_blockers`
18. `test_rework_required_requires_blockers`
19. `test_escalate_requires_blockers`
20. `test_checker_verdict_rejects_non_deterministic_id`
21. `test_checker_verdict_rejects_naive_checked_at`
22. `test_checker_note_rejects_override_fields`
23. `test_checker_blocker_rejects_empty_related_ref`
24. `test_checker_verdict_rejects_extra_evidence_refs`

RED 预期：首次运行应因缺 `boardroom_os.checker` 模块失败。

### 11.2 Happy path tests

`tests/evidence/test_checker_verdict.py`：

1. `test_complete_evidence_without_notes_is_approved`
2. `test_complete_evidence_with_notes_is_approved_with_non_blocking_notes`
3. `test_missing_evidence_returns_rework_required`
4. `test_failed_evidence_returns_rework_required_and_preserves_related_refs`
5. `test_checker_blocker_returns_rework_required_with_complete_evidence`
6. `test_checker_verdict_serializes_as_audit_friendly_json`
7. `test_checker_verdict_uses_deterministic_id`
8. `test_checker_service_preserves_core_audit_refs`

### 11.3 Regression scope

实现完成后至少运行：

```bash
PYTHONPATH="src:." python -m pytest tests/evidence/test_checker_verdict.py -q
PYTHONPATH="src:." python -m pytest tests/evidence/test_final_evidence_table.py tests/evidence/test_checker_verdict.py tests/negative/test_missing_acceptance_map_blocks_closeout.py -q
PYTHONPATH="src:." python -m pytest tests/contracts tests/reducers tests/execution tests/evidence tests/negative -q
```

## 12. 与现有模块的关系

1. 复用 `boardroom_os.execution.work_product.WorkProduct`（工作产物）和 WorkProductRef（工作产物引用）。
2. 复用 `boardroom_os.graph.ticket.TicketId`（任务 ID）。
3. 复用 `boardroom_os.contracts.acceptance.AcceptanceContract`（验收合同）。
4. 复用 `boardroom_os.contracts.types.AcceptanceRef`（验收引用）、ContractId（合同 ID）和 NonEmptyTextValue（非空文本值）。
5. 复用 `boardroom_os.evidence.table.FinalEvidenceTable`（最终证据表）、FinalEvidenceTableRef（最终证据表引用）、FinalEvidenceStatus（最终证据状态）和 FinalEvidenceBlocker（最终证据阻断项）。
6. 不修改 `boardroom_os.evidence.verifier.EvidenceVerifier`（证据验证器）。
7. 不修改 `boardroom_os.evidence.table.FinalEvidenceTableBuilder`（最终证据表构建器）。
8. 不修改 `boardroom_os.execution.work_product.WorkProduct`（工作产物）。
9. 不修改 RuntimeExecutor（运行时执行器）、CommandRunner（命令运行器）或 ProviderExecutor（模型供应商执行器）。
10. 不修改 TicketReducer（任务状态归约器）；V2-050F 再接入 formal completion gate（正式完成门禁）。

## 13. 验收映射

本 spec 对应 backlog 工作包：V2-050D。

覆盖 `backlog.md` 中 V2-050D 的验收口径：

- verified evidence incomplete（已验证证据不完整）但 checker approved（检查者批准）必须失败。
- notes 覆盖 blocker（备注覆盖阻断项）必须失败。
- checker 自行补 evidence（检查者自行补证据）必须失败。
- evidence complete（证据完整）时 checker 可 `APPROVED` 或 `APPROVED_WITH_NON_BLOCKING_NOTES`。
- checker 不能替 verifier（验证器）放行。

覆盖 `acceptance-criteria.md`：

- AC-V2-CHECKER-001（checker blocks evidence gaps，检查者阻断证据缺口）：由 V2-050D `test_checker_verdict.py` 中 incomplete table / missing row / failed row -> `REWORK_REQUIRED` 证明。
- AC-V2-CHECKER-002（notes do not clear blockers，备注不能清除阻断项）：由 V2-050D `test_notes_cannot_clear_evidence_blocker`、approved status invariant tests（批准状态不变量测试）证明。

完成 V2-050D implementation（实施）后应按 backlog 完成协议更新：

1. `doc/04-implementation/backlog.md`：V2-050D 状态改为 DONE，当前未完成工作包指向 V2-050E，Phase 5 进度改为 5/7，合计改为 33/53。
2. `doc/04-implementation/acceptance-criteria.md`：勾选 AC-V2-CHECKER-001 和 AC-V2-CHECKER-002；更新 Phase 5 当前完成数为 5/7；不要勾选 Rework 闭环或 Completion gate。
3. `doc/05-project-log/2026-05.md`：追加 V2-050D 记录，包含关键产出文件、negative/happy tests 和验证命令。
4. `doc/04-implementation/INDEX.md`：本 spec 文档索引项已存在；若新增 implementation plan（实施计划）文档，再同步加入。
5. `doc/05-project-log/decisions.md`：若 implementation 阶段保持本 spec 边界，不需要新增 DEC；若改变 Checker（检查者）与 Rework（返工）或 CompletionGate（完成门禁）的职责边界，则新增 DEC。

## 14. 同行评审收口决策

同行评审后，以下 6 项作为 V2-050D implementation（实施）的固定边界：

1. 结构性输入异常必须 raise CheckerVerdictError（检查结论错误），不得返回 `ESCALATE`。这包括 inactive AcceptanceContract（非活跃验收合同）、contract/table mismatch（合同 / 表不一致）、work product ticket mismatch（工作产物任务不一致）、缺 source_diff_ref（源码差异引用）等输入边界错误。
2. `ESCALATE` 首版不由 CheckerService.review（检查服务审查函数）自动产出；它只作为 CheckerVerdictStatus（检查结论状态）保留给调用方或后续治理流显式构造。
3. SourceDiffRef（源码差异引用）首版只保留 NonEmptyTextValue（非空文本值）子类引用；不引入 SourceDiffSummary（源码差异摘要）。
4. CheckerNote.related_ref（检查备注关联引用）必填，且 CheckerNote（检查备注）不允许 blocking / evidence / override 额外字段。
5. CheckerVerdictBlocker.acceptance_ref（检查结论阻断项验收引用）schema 允许为空；但 CheckerService 从 FinalEvidenceTable row（最终证据表行）派生的 `final_evidence_missing` / `final_evidence_failed` blocker 必须携带 acceptance_ref。
6. V2-050D 不引入 `CHECKER_VERDICT_RECORDED` 事件，也不修改 EventType（事件类型）；事件 taxonomy（事件分类）等 V2-050F / V2-070 实际消费时再扩展。

## 15. 已收敛评审点

1. Checker（检查者）不能替 EvidenceVerifier（证据验证器）放行。
2. Checker（检查者）不能自行补 EvidenceClaim（证据声明）、VerifiedEvidence（已验证证据）或 EvidenceVerificationResult（证据验证结果）。
3. FinalEvidenceTable（最终证据表）是 checker 判断 evidence completeness（证据完整性）的唯一来源。
4. Notes（备注）只能是非阻断审计上下文，不能清除 blocker（阻断项）。
5. Incomplete FinalEvidenceTable（未完成最终证据表）必须导致 `REWORK_REQUIRED`。
6. Checker blocker（检查阻断项）即使在 evidence complete（证据完整）时也必须导致 `REWORK_REQUIRED`。
7. V2-050D 不生成 rework ticket（返工任务），只提供 V2-050E 可消费的 blocker refs（阻断引用）。
8. V2-050D 不接入 reducer completion gate（归约器完成门禁），V2-050F 再适配。
