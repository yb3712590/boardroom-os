# V2-050F CompletionGate（完成门禁）同行评审 spec

## 1. 背景与现实场景

V2-050F 要处理的现实场景是：Worker（执行者）已经提交 WorkProduct（工作产物），EvidenceVerifier（证据验证器）已经产出 VerifiedEvidence（已验证证据），FinalEvidenceTable（最终证据表）显示 blocking criteria（阻塞验收项）已满足，CheckerVerdict（检查结论）也批准；但 ticket（任务）在进入 completed（完成）状态前，仍必须由 reducer（状态归约器）保护完成边界。

这个门禁的作用不是重新验证证据，也不是替 checker（检查者）做判断，而是把正式 evidence/checker 模型适配到 V2-020D 已固化的 TicketCompletionSnapshot（任务完成快照）边界，并证明以下任一情况都不能完成 ticket：

- checker approved（检查者批准）但 FinalEvidenceTable（最终证据表）缺失或 incomplete（不完整）；
- evidence complete（证据完整）但 checker verdict（检查结论）仍有 blocker（阻断项）；
- ProviderAttempt（模型调用尝试记录）数量为 0；
- 缺 WORK_PRODUCT_SUBMITTED（工作产物已提交）历史事实；
- 任一关联 fallback（降级）的 VerifiedEvidence（已验证证据）缺 FALLBACK_DECISION_RECORDED（降级判定已记录）来源链，或其 FallbackDecisionRecord（降级判定记录）为 allowed=False（不允许）。

## 2. 目标

1. 新增 `CompletionGate`（完成门禁）模块，将 `FinalEvidenceTable`（最终证据表）、`CheckerVerdict`（检查结论）、`VerifiedEvidence`（已验证证据）、`FallbackDecisionRecord`（降级判定记录）、ProviderAttempt refs（模型调用尝试引用）和 WorkProduct submitted refs（工作产物已提交引用）汇总为 `TicketCompletionSnapshot`（任务完成快照）。
2. 保持 `TicketReducer`（任务状态归约器）作为唯一完成状态写入边界：`CompletionGate`（完成门禁）只能生成 payload（载荷），不能直接修改 `TicketGraph`（任务图）。
3. 同时在 gate（门禁）和 reducer（状态归约器）层证明缺 WORK_PRODUCT_SUBMITTED（工作产物已提交）历史事实会阻断 completion（完成）。
4. 明确 fallback lineage（降级来源链）在 completion（完成）前的最终检查规则，闭合 DEC-0014 中对 V2-050F 的要求。

## 3. 非目标

- 不重写 `TicketReducer`（任务状态归约器）的核心状态机。
- 不重新实现 `EvidenceVerifier`（证据验证器）或 `FinalEvidenceTableBuilder`（最终证据表构建器）。
- 不实现 SourceInventory（源码清单）、CloseoutPackage（收尾包）或 process audit（流程审计）。
- 不让 runtime（运行时）或 checker（检查者）单独决定 ticket completed（任务完成）。
- 不接受 synthetic verification（合成验证）、占位源码或 fallback success（降级成功）作为新的完成路径。

## 4. 设计方案

### 4.1 新增模块

新增文件：

```text
src/boardroom_os/reducers/completion_gate.py
```

建议公开对象：

```python
class CompletionGateError(ValueError): ...

class CompletionGateInput(BaseModel): ...

class CompletionGateResult(BaseModel): ...

class CompletionGate:
    def build_completion_snapshot(
        self,
        gate_input: CompletionGateInput,
    ) -> CompletionGateResult: ...
```

`CompletionGateInput`（完成门禁输入）建议字段：

- `ticket_ref: TicketId`（任务引用）；
- `final_evidence_table: FinalEvidenceTable`（最终证据表）；
- `checker_verdict: CheckerVerdict`（检查结论）；
- `verified_evidence: tuple[VerifiedEvidence, ...]`（已验证证据集合）；
- `provider_attempt_refs: tuple[ProviderAttemptRef, ...]`（模型调用尝试引用集合）；
- `work_product_submitted_refs: tuple[WorkProductRef, ...]`（已提交工作产物引用集合）；
- `fallback_decision_records: tuple[FallbackDecisionRecord, ...] = ()`（降级判定记录集合）。

`CompletionGateResult`（完成门禁结果）建议字段：

- `completion_snapshot: TicketCompletionSnapshot`（任务完成快照）；
- `provider_attempt_count: int`（模型调用尝试数量）；
- `final_evidence_table_ref: FinalEvidenceTableRef`（最终证据表引用）；
- `checker_verdict_ref: CheckerVerdictRef`（检查结论引用）；
- `verified_evidence_refs: tuple[VerifiedEvidenceRef, ...]`（已验证证据引用集合）；
- `fallback_decision_record_refs: tuple[FallbackDecisionRecordRef, ...]`（降级判定记录引用集合）。

### 4.2 完成门禁规则

`CompletionGate`（完成门禁）必须 fail closed（失败关闭）检查以下规则。

#### 4.2.1 Evidence table（证据表）完整性

- `final_evidence_table.complete` 必须为 `True`。
- 所有 `FinalEvidenceRow`（最终证据行）状态必须为 `SATISFIED`（已满足）。
- `FinalEvidenceTable`（最终证据表）中引用的所有 `verified_evidence_refs` 必须能在 `verified_evidence` 输入集合中解析。
- `verified_evidence` 输入集合必须与 table rows（证据表行）引用集合严格一致，避免隐藏的未映射证据影响完成判断。

#### 4.2.2 Checker verdict（检查结论）一致性

- `checker_verdict.ticket_ref` 必须等于 `ticket_ref`。
- `checker_verdict.final_evidence_table_ref` 必须等于 `final_evidence_table.final_evidence_table_id`。
- `checker_verdict.acceptance_contract_ref` 必须等于 `final_evidence_table.acceptance_contract_ref`。
- `checker_verdict.status` 只能是 `APPROVED`（批准）或 `APPROVED_WITH_NON_BLOCKING_NOTES`（带非阻断备注批准）。
- `checker_verdict.blockers` 必须为空。
- `REWORK_REQUIRED`（需要返工）或 `ESCALATE`（升级处理）永远不能生成 completion snapshot（完成快照）。

#### 4.2.3 Provider attempt（模型调用尝试）门禁

- `provider_attempt_refs` 必须非空且唯一。
- 每个 `VerifiedEvidence.producer_attempt_ref`（已验证证据的生产尝试引用）必须出现在 `provider_attempt_refs` 中。
- `TicketCompletionSnapshot.provider_attempt_count` 必须由 gate 内部通过 `len({ref.value for ref in provider_attempt_refs})` 从唯一 `provider_attempt_refs` 派生，不能由调用方自由传入裸数字，也不能接受“伪造高 count + 空 attempt refs”的组合。

#### 4.2.4 Work product submitted（工作产物已提交）门禁

- `work_product_submitted_refs` 必须包含 `checker_verdict.work_product_ref`；该集合由调用方从 `WORK_PRODUCT_SUBMITTED`（工作产物已提交）事件历史投影提供，`CompletionGate`（完成门禁）不查询事件日志。
- gate（门禁）缺失该 ref 时不得生成 `TicketCompletionSnapshot`（任务完成快照）。
- reducer（状态归约器）仍必须在事件历史中看到真实 `WORK_PRODUCT_SUBMITTED`（工作产物已提交）事件；即使调用方伪造 gate input（门禁输入），`TicketReducer`（任务状态归约器）也必须拒绝缺历史事实的 `TICKET_COMPLETED`（任务已完成）事件。

#### 4.2.5 Fallback lineage（降级来源链）门禁

对每个 `VerifiedEvidence`（已验证证据）：

- 如果 `fallback_decision_record_ref` 为空，则 `fallback_decision_recorded_ref` 也必须为空。
- 如果 `fallback_decision_record_ref` 非空：
  - `fallback_decision_recorded_ref` 必须非空；
  - `fallback_decision_records` 中必须存在同 ID 的 `FallbackDecisionRecord`（降级判定记录）；
  - `FallbackDecisionRecord.decision.allowed` 必须为 `True`；
  - `FallbackDecisionRecord.evidence_claim_ref` 必须等于 `VerifiedEvidence.evidence_claim_ref`；
  - `FallbackDecisionRecord.producer_attempt_ref` 必须等于 `VerifiedEvidence.producer_attempt_ref`；
  - `FallbackDecisionRecord.required_artifact_type` 必须等于 `VerifiedEvidence.required_artifact_type`；
  - `FallbackDecisionRecord.evaluated_purpose` 必须等于 `VerifiedEvidence.expected_purpose`；
  - `FallbackDecisionRecord.acceptance_refs` 必须等于 `VerifiedEvidence.acceptance_refs`。
- 传入但未被任何 `VerifiedEvidence`（已验证证据）引用的 `FallbackDecisionRecord`（降级判定记录）必须失败，避免审计集合含义不清。

## 5. 数据流

```text
RuntimeExecutor（运行时执行器）
  -> PROVIDER_ATTEMPT_RECORDED（模型调用尝试已记录）
  -> WORK_PRODUCT_SUBMITTED（工作产物已提交）
  -> EvidenceClaim（证据声明）
  -> EvidenceVerifier（证据验证器）
  -> VerifiedEvidence（已验证证据）
  -> FinalEvidenceTableBuilder（最终证据表构建器）
  -> FinalEvidenceTable（最终证据表）
  -> CheckerService / CheckerVerdict（检查服务 / 检查结论）
  -> CompletionGate（完成门禁）
  -> TicketCompletionSnapshot（任务完成快照）
  -> TICKET_COMPLETED event payload（任务完成事件载荷）
  -> TicketReducer（任务状态归约器）
  -> TicketGraph.completed_nodes（任务图完成节点）
```

关键边界：

- `CompletionGate`（完成门禁）不 append event（追加事件）。
- `CompletionGate`（完成门禁）不接收 runtime actor（运行时参与者）授权，也不判断 actor 权限。
- actor 越权、缺 `WORK_PRODUCT_SUBMITTED` 历史事实、provider attempt count 为 0 等 reducer-level invariant（状态归约层不变量）仍由 `TicketReducer`（任务状态归约器）执行最终保护。

## 6. 错误处理

- 所有输入模型使用 Pydantic（Pydantic 模型）`frozen=True` 与 `extra="forbid"`，拒绝未知字段和运行时篡改。
- 对外统一抛出 `CompletionGateError`（完成门禁错误），错误信息应指向被拒绝的 gate rule（门禁规则），但不替调用方生成 fallback（降级）或补齐缺失字段。
- `CompletionGateResult`（完成门禁结果）必须是纯派生结果；调用方不能覆写 `provider_attempt_count`、`evidence_complete` 或 `checker_approved`。

## 7. 测试方案

新增测试文件：

```text
tests/reducers/test_completion_gate_with_evidence.py
```

### 7.1 必须先写的 negative tests（负例测试）

1. checker approved（检查者批准）但 `FinalEvidenceTable`（最终证据表）缺失或类型错误时失败。
2. `FinalEvidenceTable.complete=False`（最终证据表不完整）时失败。
3. table row（证据表行）存在 missing/failed（缺失/失败）状态时失败。
4. checker verdict（检查结论）为 `REWORK_REQUIRED`（需要返工）/ `ESCALATE`（升级处理）或含 blocker（阻断项）时失败。
5. `provider_attempt_refs=()`（模型调用尝试引用为空）时失败，并证明“伪造高 count + 空 attempt refs”的组合无法绕过 gate（门禁）。
6. `VerifiedEvidence.producer_attempt_ref`（已验证证据生产尝试引用）不在 `provider_attempt_refs` 中时失败。
7. `work_product_submitted_refs` 不包含 `checker_verdict.work_product_ref` 时失败。
8. 即使 gate（门禁）生成了 snapshot（快照），`TicketReducer`（任务状态归约器）在缺 `WORK_PRODUCT_SUBMITTED` 历史事件时仍失败。
9. fallback evidence（降级证据）缺 `fallback_decision_recorded_ref` 时失败。
10. fallback evidence（降级证据）缺对应 `FallbackDecisionRecord`（降级判定记录）时失败。
11. fallback decision（降级判定）`allowed=False` 时失败。
12. fallback decision record（降级判定记录）与 VerifiedEvidence（已验证证据）的 claim / attempt / artifact type / purpose / acceptance refs 任一不一致时失败。
13. table（证据表）、checker verdict（检查结论）和 ticket_ref（任务引用）之间任一 contract/ticket/ref 不一致时失败。

### 7.2 Happy path（正向路径）

1. primary evidence（主路径证据）完整、checker approved（检查者批准）、provider attempt refs（模型调用尝试引用）非空、work product submitted refs（工作产物已提交引用）匹配时，`CompletionGate`（完成门禁）生成 `TicketCompletionSnapshot`（任务完成快照）。
2. `APPROVED_WITH_NON_BLOCKING_NOTES`（带非阻断备注批准）可生成 completion snapshot（完成快照），但 blocker（阻断项）仍必须为空。
3. 合同允许的 deterministic fallback evidence（确定性降级证据）在 `FallbackDecisionRecord.decision.allowed=True` 且 `fallback_decision_recorded_ref` 存在时可通过 gate（门禁）。
4. `TicketReducer`（任务状态归约器）在事件历史包含 `TICKET_CREATED`（任务创建）、`WORK_PRODUCT_SUBMITTED`（工作产物已提交）和治理/检查链路提交的 `TICKET_COMPLETED`（任务已完成）时，将 ticket 投影为 `COMPLETED`（已完成）。

## 8. 验收口径

V2-050F 完成后必须满足：

- `src/boardroom_os/reducers/completion_gate.py` 存在，并且只承担正式 evidence/checker 模型到 `TicketCompletionSnapshot`（任务完成快照）的适配职责。
- `tests/reducers/test_completion_gate_with_evidence.py` 覆盖 backlog 中列出的全部 negative tests（负例测试）和 happy path（正向路径）。
- 现有 `TicketReducer`（任务状态归约器）仍是 ticket completed（任务完成）的唯一状态写入边界。
- runtime（运行时）不能通过任何新接口 emit（发出）或伪造 `TICKET_COMPLETED`（任务已完成）。
- Phase 5 的 completion gate checkbox（完成门禁勾选项）可由测试证据闭合。

## 9. 同行评审关注点

请重点审查：

1. `CompletionGate`（完成门禁）是否过度承担了 verifier（验证器）或 checker（检查者）的职责。
2. WorkProduct submitted（工作产物已提交）历史事实是否同时在 gate input（门禁输入）和 reducer event history（状态归约器事件历史）两层被保护。
3. fallback lineage（降级来源链）规则是否足以闭合 DEC-0014 对 allowed=False（不允许）和缺 FALLBACK_DECISION_RECORDED（降级判定已记录）的风险。
4. `provider_attempt_count`（模型调用尝试数量）是否应仅由 `provider_attempt_refs` 派生，而不是由调用方传入。
5. 是否应拒绝未被 FinalEvidenceTable（最终证据表）引用的额外 VerifiedEvidence（已验证证据）；本 spec 选择拒绝，以保持 completion evidence set（完成证据集合）含义明确。
6. 多次 rework（返工）后，`checker_verdict.work_product_ref`（检查结论工作产物引用）目前只要求出现在 `work_product_submitted_refs`（已提交工作产物引用集合）中，不判断“最新一次”语义；该 lineage（来源链）收束留给 V2-070C process audit（流程审计）验证。
