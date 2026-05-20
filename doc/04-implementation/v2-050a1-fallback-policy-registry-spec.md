# V2-050A1 FallbackPolicyRegistry 设计 Spec

## 1. 现实场景

本轮对应的现实场景是：worker（实施智能体）或 runtime（运行时）交出了一个 fallback artifact（降级产物），并声称它可以作为某些 evidence（证据）的一部分。Boardroom OS V2 不能只看 artifact（产物）上写了一个 `fallback_policy_ref`（降级策略引用）就相信它，也不能让 verifier（证据验证器）临时解释这个 ref。

通俗地说，V2-050A1 要加的是一座“降级证据闸门”：任何 fallback claim（降级声明）都必须先去唯一注册表查策略，再按完整 claim scope（声明作用域）一次性判定，并产出可审计的 decision record（判定记录）。如果查不到、类型对不上、策略本身不允许、或有人试图拆分 acceptance refs（验收引用）绕过 scope（作用域）校验，就必须 fail closed（失败关闭）。

## 2. 目标

实现 FallbackPolicyRegistry（降级策略注册表）与 fallback decision record（降级判定记录）的最小接口，并统一 V2-050A1 与 V2-050B 的 fallback 口径：

1. 提供唯一权威入口，将 `fallback_policy_ref` 解析为 FallbackPolicy（降级策略）。
2. 拒绝缺 registry（注册表）、未知 ref、重复 ref、空 registry 和 malformed input（格式错误输入）。
3. 拒绝 registry 中声明可用于证据满足的危险 fallback kind（降级类型），尤其是 `TEST_ONLY_SIMULATION`（测试模拟）、`PROVIDER_UNAVAILABLE`（模型供应商不可用）和 `DETERMINISTIC_GOVERNANCE_DRAFT`（确定性治理草案）。
4. 将 EvidenceClaim（证据声明）中的 FallbackLineageMarker（降级来源链标记）解析为 typed decision record（类型化判定记录）。
5. 强制 `FallbackLineageMarker.fallback_kind`（降级标记类型）与 registry 中 FallbackPolicy.kind（策略类型）一致。
6. 强制每个 fallback work product（降级工作产物）以完整 `EvidenceClaim.acceptance_refs` 一次性调用 `evaluate_fallback_evidence`（降级证据判定函数）。
7. 产出 FallbackDecisionRecord（降级判定记录），供 V2-050B EvidenceVerifier（证据验证器）唯一消费。
8. 将 V2-050B 的接口合同写清楚：verifier 不得重新解析 fallback policy（降级策略），不得按单个 acceptance ref 拆分判定，不得绕过 decision record。

## 3. 非目标

V2-050A1 不做以下事情：

1. 不实现完整 EvidenceVerifier（证据验证器），artifact existence（产物存在性）、artifact hash（产物哈希）、provider attempt existence（模型调用尝试存在性）、active contract refs（活跃合同引用）校验属于 V2-050B。
2. 不把 FallbackDecisionRecord（降级判定记录）转换为 verified evidence（已验证证据）。
3. 不实现 FinalEvidenceTable（最终证据表），acceptance map（验收映射）汇总属于 V2-050C。
4. 不实现 CheckerVerdict（检查结论）、rework ticket（返工任务）或 reducer completion gate（状态归约完成门禁），这些属于 V2-050D/E/F。
5. 不新增 event log（事件日志）持久化要求；`FALLBACK_DECISION_RECORDED`（降级判定已记录）事件名和 event wiring（事件接线）由 V2-050B/F 在实际消费时补齐。
6. 不读取 generated project workspace（生成项目工作区）或 package root（包根）。
7. 不修改 V2-030E `evaluate_fallback_evidence` 的现有真值表语义，除非同行评审明确要求。

## 4. 选型结论

采用“统一 fallback gate（降级门禁）口径，分工作包实施”的方案。

### 4.1 被采用方案：A1 定义唯一 fallback gate，B 只能消费它

V2-050A1 新增 FallbackPolicyRegistry（降级策略注册表）、FallbackDecisionRecord（降级判定记录）和 `evaluate_fallback_claim`（判定降级声明）入口。V2-050B 后续只能消费 A1 产出的 FallbackDecisionRecord，不得重新解释 policy（策略）或重新选择 EvidencePurpose（证据用途）。

优点：

- V2-050 整体口径更稳，降低 A1/B 间行为漂移风险。
- A1 可独立完成 registry/ref/kind/scope/evaluator（注册表 / 引用 / 类型 / 作用域 / 判定器）边界。
- B 后续只需校验 decision record 是否存在、是否与 claim 匹配、是否 allowed=True，而不再重写 fallback gate。
- 不越界吞掉 artifact/hash/provider/command verifier（产物 / 哈希 / 模型调用 / 命令验证器）职责。

代价：

- A1 比“纯 registry”略重，需要定义 FallbackDecisionRecord。
- B 的部分行为约束会提前写入本 spec，但代码仍按 backlog（待办）分包落地。

### 4.2 未采用方案：A1 只做 registry，B 自己接 verifier

只新增 `FallbackPolicyRegistry.resolve(ref)`，把 evaluator（判定器）调用和 decision record（判定记录）全部留给 V2-050B。

不采用原因：V2-050B 很容易重新选择 purpose（用途）、按 acceptance_ref 拆分调用 evaluator，或把 registry lookup（注册表查询）当作可选步骤，从而造成 V2-050 阶段口径不一致。

### 4.3 未采用方案：A1 直接实现完整 fallback verifier

A1 同时检查 artifact hash（产物哈希）、provider attempt（模型调用尝试）、command evidence（命令证据）、active contract refs（活跃合同引用）并生成 verified evidence（已验证证据）。

不采用原因：这会吞掉 V2-050B 的 EvidenceVerifier（证据验证器）职责，并提前接入 V2-050C/F 的表格和完成门禁语义，工作包边界过大。

## 5. 已决实施决定

1. `FallbackPolicyRegistry`（降级策略注册表）是唯一 `fallback_policy_ref -> FallbackPolicy`（降级策略）解析入口。
2. registry 必须 immutable（不可变）且 fail closed（失败关闭）：空 registry、重复 ref、未知 ref、非 FallbackPolicy 输入都失败。
3. registry 不允许把 `PROVIDER_UNAVAILABLE`、`TEST_ONLY_SIMULATION`、`DETERMINISTIC_GOVERNANCE_DRAFT` 注册成可满足 evidence 的 policy。它们可以作为历史事实的 fallback kind 出现在 ProviderAttempt（模型调用尝试记录）或 WorkProduct（工作产物）中，但不能通过 registry 进入 allowed evidence path（可允许证据路径）。
4. `TOOLING_PREFLIGHT`（工具预检）允许注册，但只能生成 diagnostic decision（诊断判定），不得被 V2-050C FinalEvidenceTable（最终证据表）计入 blocking criteria（阻塞验收项）。A1 只记录 decision，B/C/F 阶段负责阻止它进入 blocking evidence（阻塞证据）或 completion gate（完成门禁）。
5. `CONTRACT_ALLOWED_DETERMINISTIC_TRANSFORM`（合同允许确定性转换）是唯一可能 allowed=True 的 fallback evidence path，但仍只能满足 deterministic evidence（确定性证据），且必须受 artifact type（产物类型）与完整 acceptance refs（验收引用集合） scope 约束。
6. `evaluate_fallback_claim` 必须使用 EvidenceClaim.expected_purpose（证据声明预期用途）与 EvidenceClaim.required_artifact_type（证据声明必需产物类型），不得由调用方传入替代 purpose 或 artifact type。
7. `evaluate_fallback_claim` 必须将 EvidenceClaim.acceptance_refs 作为完整 tuple（元组）一次性传给 `FallbackEvidenceRequest`（降级证据请求）。实现中不提供“按单个 acceptance ref 判定”的 public API（公开接口）。
8. FallbackLineageMarker.fallback_policy_ref（降级来源链策略引用）必须解析到 registry 中的 policy。
9. FallbackLineageMarker.fallback_kind 必须与 FallbackPolicy.kind 一致。
10. FallbackDecisionRecord（降级判定记录）只表示判定事实，不表示 verified evidence（已验证证据）。
11. FallbackDecisionRecord 必须同时绑定 EvidenceClaimRef（证据声明引用）、FallbackPolicyRef（降级策略引用）、ProducerAttemptRef（产出尝试引用）、完整 acceptance refs、required artifact type、expected purpose 和 FallbackEvidenceDecision（降级证据判定）。
12. V2-050B 后续必须要求 fallback claim 携带与 claim 完全匹配的 FallbackDecisionRecord；没有 record、record mismatch（记录不匹配）或 `allowed=False` 均不能进入 verified evidence。
13. V2-050B 后续不得重新解析 fallback policy，不得重新调用 `evaluate_fallback_evidence`，除非明确以 A1 的 `evaluate_fallback_claim` 为唯一入口。

## 6. 模块设计

### 6.1 `src/boardroom_os/evidence/fallback_registry.py`

新增模块包含：

- `FallbackRegistryError`（降级注册表错误）
- `FallbackPolicyRegistry`（降级策略注册表）
- `FallbackDecisionRecordRef`（降级判定记录引用）
- `FallbackDecisionRecord`（降级判定记录）
- `evaluate_fallback_claim`（判定降级声明）

### 6.2 FallbackPolicyRegistry

建议 schema：

```yaml
policies:
  - fallback_policy_ref:
    kind:
    allowed_artifact_types:
    allowed_acceptance_refs:
```

建议行为：

```python
class FallbackPolicyRegistry(BaseModel):
    policies: tuple[FallbackPolicy, ...]

    def resolve(self, fallback_policy_ref: FallbackPolicyRef) -> FallbackPolicy:
        ...
```

校验规则：

1. `policies` 不得为空。
2. 每个 item 必须是 FallbackPolicy（降级策略）。
3. `fallback_policy_ref` 不得重复。
4. `resolve` 收到非 FallbackPolicyRef（降级策略引用）必须失败。
5. `resolve` 未找到 ref 必须失败。
6. 若 policy.kind 为 `CONTRACT_ALLOWED_DETERMINISTIC_TRANSFORM`，allowed_artifact_types 和 allowed_acceptance_refs 的非空约束由 FallbackPolicy（降级策略）自身保证；registry 不重复实现 allow list（允许列表）校验，只消费已通过模型校验的 policy。
7. 若 policy.kind 为 `PROVIDER_UNAVAILABLE`、`TEST_ONLY_SIMULATION` 或 `DETERMINISTIC_GOVERNANCE_DRAFT`，registry 构造必须失败。
8. 若 policy.kind 为 `TOOLING_PREFLIGHT`，registry 必须允许注册为 diagnostic preflight（诊断预检）事实来源，但该 policy 不属于 evidence satisfaction path（证据满足路径）；V2-050B/C/F 必须阻止它进入 blocking evidence（阻塞证据）或 completion（完成）门禁。

说明：第 8 条锁定为“允许注册但限制用途”，用于兼容 V2-030E 已允许 diagnostic eligibility（诊断资格）的真值表；它不是 implementation evidence（实施证据）、deterministic closeout evidence（确定性收尾证据）或 generated project acceptance evidence（生成项目验收证据）。

### 6.3 FallbackDecisionRecord

`FallbackDecisionRecordRef`（降级判定记录引用）必须继承 NonEmptyTextValue（非空文本值），与 EvidenceClaimRef（证据声明引用）和 FallbackPolicyRef（降级策略引用）保持同一种 value object（值对象）风格；不要为 ref 新建 BaseModel-shaped（BaseModel 形状）对象。

建议 schema：

```yaml
version: 1
fallback_decision_record_id:
evidence_claim_ref:
producer_attempt_ref:
fallback_policy_ref:
fallback_kind:
evaluated_purpose:
required_artifact_type:
acceptance_refs:
decision:
evaluated_at:
```

字段说明：

- `fallback_decision_record_id`：FallbackDecisionRecordRef（降级判定记录引用），可由 claim ref 和 policy ref 确定性派生。
- `evidence_claim_ref`：EvidenceClaimRef（证据声明引用），绑定被判定的 claim。
- `producer_attempt_ref`：ProviderAttemptRef（模型调用尝试引用），必须等于 EvidenceClaim.producer_attempt_ref。
- `fallback_policy_ref`：FallbackPolicyRef（降级策略引用），必须等于 claim.fallback_marker.fallback_policy_ref。
- `fallback_kind`：FallbackKind（降级类型），必须等于 claim.fallback_marker.fallback_kind 与 policy.kind。
- `evaluated_purpose`：EvidencePurpose（证据用途），必须等于 EvidenceClaim.expected_purpose。
- `required_artifact_type`：RequiredArtifactType（必需产物类型），必须等于 EvidenceClaim.required_artifact_type。
- `acceptance_refs`：完整 AcceptanceRef（验收引用）tuple，必须等于 EvidenceClaim.acceptance_refs，不能是拆分子集。
- `decision`：FallbackEvidenceDecision（降级证据判定），由 `evaluate_fallback_evidence` 返回。
- `evaluated_at`：timezone-aware datetime（带时区时间），用于 audit（审计）。

校验规则：

1. `decision.fallback_policy_ref` 必须等于 `fallback_policy_ref`。
2. `decision.applied_kind` 必须等于 `fallback_kind`。
3. `decision.evaluated_purpose` 必须等于 `evaluated_purpose`。
4. `acceptance_refs` 不得为空。
5. `evaluated_at` 必须带时区。
6. `allowed=True` 的 decision 不能有 blocking reasons（阻塞原因），该规则已由 FallbackEvidenceDecision 自身校验；record 仍应通过 nested model（嵌套模型）保留该约束。

### 6.4 `evaluate_fallback_claim`

建议函数签名：

```python
def evaluate_fallback_claim(
    *,
    claim: EvidenceClaim,
    registry: FallbackPolicyRegistry,
    evaluated_at: datetime,
    decision_record_id: FallbackDecisionRecordRef | None = None,
) -> FallbackDecisionRecord:
    ...
```

职责：

1. 要求 `registry` 是 FallbackPolicyRegistry（降级策略注册表），不得为 None。
2. 要求 claim.fallback_marker 存在；primary claim（主路径声明）调用该函数必须失败。
3. 从 claim.fallback_marker.fallback_policy_ref 解析 FallbackPolicy。
4. 校验 policy.kind 与 claim.fallback_marker.fallback_kind 一致。
5. 构造 FallbackEvidenceRequest：
   - `purpose = claim.expected_purpose`
   - `artifact_type = claim.required_artifact_type`
   - `acceptance_refs = claim.acceptance_refs`
6. 一次性调用 `evaluate_fallback_evidence(policy=policy, request=request)`。
7. 生成 FallbackDecisionRecord，完整复制 claim scope。
8. 若调用方显式传入 decision_record_id，则使用它；否则使用确定性 ID：`fallback-decision.<evidence_claim_id>.<fallback_policy_ref>`。

该函数是 V2-050B 后续可调用的唯一 fallback gate（降级门禁）入口。

## 7. V2-050B 接口合同

为了降低 Phase 5（阶段 5）整体口径不一致风险，V2-050B EvidenceVerifier（证据验证器）必须遵守以下接口合同：

1. 若 EvidenceClaim.fallback_marker is None（没有降级标记），verifier 走 primary evidence path（主路径证据路径），不得要求 fallback decision record。
2. 若 EvidenceClaim.fallback_marker 存在，verifier 必须要求存在 FallbackDecisionRecord（降级判定记录）。
3. verifier 必须校验 record 与 claim 完全一致：
   - `record.evidence_claim_ref == claim.evidence_claim_id`
   - `record.producer_attempt_ref == claim.producer_attempt_ref`
   - `record.fallback_policy_ref == claim.fallback_marker.fallback_policy_ref`
   - `record.fallback_kind == claim.fallback_marker.fallback_kind`
   - `record.evaluated_purpose == claim.expected_purpose`
   - `record.required_artifact_type == claim.required_artifact_type`
   - `record.acceptance_refs == claim.acceptance_refs`
4. 若 `record.decision.allowed is False`，verifier 必须产生 blocker（阻塞项），不能转为 verified evidence。
5. 若 record 缺失、错绑、scope 子集化、purpose 不一致、artifact type 不一致，verifier 必须 fail closed。
6. verifier 不得按单个 acceptance_ref 重新构造 FallbackEvidenceRequest。
7. verifier 不得重新选择 EvidencePurpose（证据用途）。
8. verifier 不得重新解析 `fallback_policy_ref`，除非调用 A1 的 `evaluate_fallback_claim` 并把结果作为 record 消费。
9. `TOOLING_PREFLIGHT` 即使得到 allowed diagnostic decision，也不得被 FinalEvidenceTable（最终证据表）计入 blocking acceptance satisfied（阻塞验收满足）。该规则在 V2-050C/F 消费 evidence table 时继续保持。
10. V2-050F completion gate（完成门禁）必须阻断任何关联 `allowed=False` fallback decision 的 evidence，且必须要求 fallback lineage（降级来源链）可追踪到 decision record。

## 8. 数据流

```text
EvidenceClaim（证据声明，含 fallback_marker）
  -> FallbackPolicyRegistry.resolve（降级策略解析）
  -> FallbackKind match（降级类型一致性校验）
  -> FallbackEvidenceRequest（完整 claim scope 请求）
  -> evaluate_fallback_evidence（降级证据判定）
  -> FallbackDecisionRecord（降级判定记录）
      -> V2-050B EvidenceVerifier（证据验证器）
      -> V2-050C FinalEvidenceTable（最终证据表）
      -> V2-050F CompletionGate（完成门禁）
```

关键不变量：`EvidenceClaim.acceptance_refs` 必须作为完整 tuple 进入 evaluator（判定器），不能由 verifier 或调用方拆成多个单 ref request（单验收引用请求）。

## 9. Fail-closed 规则

以下情况必须失败：

1. FallbackPolicyRegistry 缺位。
2. FallbackPolicyRegistry.policies 为空。
3. FallbackPolicyRegistry 中有重复 fallback_policy_ref。
4. FallbackPolicyRegistry 中包含非 FallbackPolicy item。
5. `resolve` 收到非 FallbackPolicyRef。
6. `resolve` 找不到 fallback_policy_ref。
7. registry 尝试注册 `PROVIDER_UNAVAILABLE` 为可满足 evidence 的 policy。
8. registry 尝试注册 `TEST_ONLY_SIMULATION` 为可满足 evidence 的 policy。
9. registry 尝试注册 `DETERMINISTIC_GOVERNANCE_DRAFT` 为可满足 evidence 的 policy。
10. EvidenceClaim 缺 fallback_marker 却调用 `evaluate_fallback_claim`。
11. FallbackLineageMarker.fallback_policy_ref 无法解析。
12. FallbackLineageMarker.fallback_kind 与 FallbackPolicy.kind 不一致。
13. FallbackDecisionRecord 的 decision policy/kind/purpose 与 record 顶层字段不一致。
14. FallbackDecisionRecord.acceptance_refs 为空。
15. FallbackDecisionRecord.acceptance_refs 不是完整 EvidenceClaim.acceptance_refs。
16. `evaluated_at` 无时区。
17. 试图通过按 acceptance_ref 拆分 evaluator 调用来获得多个局部 decision；A1 不提供该 API，测试应通过 monkeypatch（猴子补丁）或 spy（调用监控）证明 evaluator 只被调用一次且参数包含完整 refs。补丁点必须是 `boardroom_os.evidence.fallback_registry.evaluate_fallback_evidence`（模块本地引用），而不是 `boardroom_os.execution.fallback.evaluate_fallback_evidence`（上游定义）。
18. `expected_purpose == implementation` 的 fallback claim 即使 policy 是 deterministic transform，也必须返回 allowed=False。
19. `TEST_ONLY_SIMULATION`、`PROVIDER_UNAVAILABLE`、`DETERMINISTIC_GOVERNANCE_DRAFT` 不存在第二条 claim-level allowed path；由 registry 构造拒绝（规则 7-9）和 marker/policy kind mismatch（规则 12）共同保证。

## 10. Happy path

### 10.1 deterministic fallback decision

最小正例：

1. 构造一个 fallback EvidenceClaim，包含：
   - fallback_marker.fallback_policy_ref = `fallback.hash-manifest`
   - fallback_marker.fallback_kind = `CONTRACT_ALLOWED_DETERMINISTIC_TRANSFORM`
   - expected_purpose = `deterministic`
   - required_artifact_type = `hash_manifest`
   - acceptance_refs = `(AC-HASH-MANIFEST, AC-REPLAY-HASH)`
2. 构造 FallbackPolicyRegistry，包含同 ref、同 kind 的 FallbackPolicy，allowed_artifact_types 含 `hash_manifest`，allowed_acceptance_refs 覆盖上述两个 acceptance refs。
3. 调用 `evaluate_fallback_claim`。
4. 返回 FallbackDecisionRecord：
   - record 绑定 claim、producer_attempt_ref、policy ref 和 full acceptance refs。
   - decision.allowed == True。
   - decision.applied_kind == `CONTRACT_ALLOWED_DETERMINISTIC_TRANSFORM`。
   - decision.evaluated_purpose == `deterministic`。

### 10.2 blocked fallback decision is auditable

最小正例：

1. 构造一个 fallback EvidenceClaim，expected_purpose = `implementation`。
2. 使用合法 deterministic transform policy。
3. 调用 `evaluate_fallback_claim`。
4. 返回 FallbackDecisionRecord，而不是抛出治理异常。
5. record.decision.allowed == False，blocking_reasons 包含 “implementation evidence cannot be satisfied by fallback”。

说明：blocked decision（阻断判定）本身也是 audit fact（审计事实），后续 V2-050B/F 用它阻断 verified evidence 和 completion。

### 10.3 tooling preflight diagnostic decision

最小正例：

1. 构造 `TOOLING_PREFLIGHT` policy。
2. 构造 expected_purpose = `diagnostic` 的 fallback claim。
3. 调用 `evaluate_fallback_claim`。
4. 返回 allowed diagnostic decision。
5. 文档明确：该 decision 不得进入 FinalEvidenceTable 的 blocking acceptance satisfied 计算。

## 11. 测试计划

新增测试：

- `tests/evidence/test_fallback_policy_registry.py`
- `tests/negative/test_fallback_registry_fail_closed.py`

### 11.1 Negative tests（先写）

`tests/negative/test_fallback_registry_fail_closed.py`：

1. `test_fallback_registry_requires_non_empty_policies`
2. `test_fallback_registry_rejects_duplicate_policy_refs`
3. `test_fallback_registry_rejects_non_policy_items`
4. `test_fallback_registry_resolve_rejects_unknown_policy_ref`
5. `test_fallback_registry_resolve_rejects_non_ref_input`
6. `test_fallback_registry_rejects_provider_unavailable_as_evidence_policy`
7. `test_fallback_registry_rejects_test_only_simulation_as_evidence_policy`
8. `test_fallback_registry_rejects_deterministic_governance_draft_as_evidence_policy`
9. `test_evaluate_fallback_claim_requires_registry`
10. `test_evaluate_fallback_claim_requires_fallback_marker`
11. `test_evaluate_fallback_claim_rejects_unresolved_policy_ref`
12. `test_evaluate_fallback_claim_rejects_marker_kind_policy_kind_mismatch`
13. `test_evaluate_fallback_claim_uses_claim_expected_purpose_not_caller_override`
14. `test_evaluate_fallback_claim_uses_full_acceptance_refs_once`
15. `test_fallback_decision_record_rejects_decision_policy_mismatch`
16. `test_fallback_decision_record_rejects_decision_kind_mismatch`
17. `test_fallback_decision_record_rejects_decision_purpose_mismatch`
18. `test_fallback_decision_record_requires_full_acceptance_refs`
19. `test_fallback_decision_record_requires_timezone_aware_evaluated_at`
20. `test_implementation_purpose_fallback_decision_is_blocked`

### 11.2 Happy path tests

`tests/evidence/test_fallback_policy_registry.py`：

1. `test_registry_resolves_fallback_policy_by_ref`
2. `test_evaluate_fallback_claim_records_allowed_deterministic_decision`
3. `test_evaluate_fallback_claim_records_blocked_implementation_decision`
4. `test_evaluate_fallback_claim_records_tooling_preflight_diagnostic_decision`
5. `test_decision_record_uses_deterministic_default_id`
6. `test_decision_record_can_use_explicit_id`
7. `test_decision_record_serializes_as_audit_friendly_json`

### 11.3 V2-050B follow-up tests to preserve interface contract

V2-050B 进入实现时必须新增或包含以下测试：

1. fallback claim 缺 FallbackDecisionRecord 必须失败。
2. FallbackDecisionRecord 与 EvidenceClaim 的 acceptance_refs 不一致必须失败。
3. FallbackDecisionRecord 与 EvidenceClaim 的 expected_purpose 不一致必须失败。
4. FallbackDecisionRecord 与 EvidenceClaim 的 required_artifact_type 不一致必须失败。
5. FallbackDecisionRecord.decision.allowed=False 必须阻断 verified evidence。
6. verifier 不得直接消费 fallback_marker 当作 allowed evidence。
7. verifier 不得按单个 acceptance_ref 拆分调用 evaluator。
8. 缺 `FALLBACK_DECISION_RECORDED` lineage（降级判定记录来源链）必须阻断 completion，该项最终由 V2-050F 适配。

## 12. 验证命令

完成实现后至少运行：

```bash
PYTHONPATH="src:." python -m pytest tests/negative/test_fallback_registry_fail_closed.py -q
PYTHONPATH="src:." python -m pytest tests/evidence/test_fallback_policy_registry.py -q
PYTHONPATH="src:." python -m pytest tests/evidence/test_evidence_claim.py tests/evidence/test_fallback_policy_registry.py tests/negative/test_fallback_registry_fail_closed.py tests/negative/test_fallback_cannot_satisfy_implementation.py tests/execution/test_fallback_policy.py -q
PYTHONPATH="src:." python -m pytest tests/contracts tests/reducers tests/execution tests/evidence tests/negative -q
```

## 13. 与现有模块的关系

1. 复用 `boardroom_os.execution.fallback.FallbackPolicy`（降级策略）、FallbackKind（降级类型）、FallbackEvidenceRequest（降级证据请求）、FallbackEvidenceDecision（降级证据判定）和 `evaluate_fallback_evidence`（降级证据判定函数）。
2. 复用 `boardroom_os.evidence.claim.EvidenceClaim`（证据声明）和 FallbackLineageMarker（降级来源链标记）。
3. 复用 `boardroom_os.execution.package.FallbackPolicyRef`（降级策略引用）。
4. 不移动现有 FallbackPolicy（降级策略）定义；A1 的 registry 位于 evidence 层，因为它服务于 evidence verifier（证据验证器）链路。
5. 不修改 ProviderAttempt（模型调用尝试记录）或 WorkProduct（工作产物）schema；它们已携带 fallback_kind（降级类型）。
6. 不修改 EvidenceClaim builder（证据声明构建函数），除非实现中发现需要暴露更稳定的 fallback marker helper（降级标记辅助函数）。
7. 不修改 TicketReducer（任务状态归约器）；V2-050F 再接入 FallbackDecisionRecord（降级判定记录）和 completion gate（完成门禁）。

## 14. 验收映射

本 spec 对应 backlog 工作包：V2-050A1。

覆盖 `backlog.md` 中 V2-050A1 的验收口径：

- fallback ref -> policy 的解析只有 registry 一个权威入口。
- registry 落地前 V2-050 对任何 fallback artifact 必须 fail closed。
- registry 可把合法 fallback_policy_ref 解析为 FallbackPolicy。
- 每个 fallback work product 以完整 acceptance_refs 一次性调用 `evaluate_fallback_evidence` 并生成可审计 decision。

覆盖 `acceptance-criteria.md` Phase 3 延期项和 Phase 5 前置口径：

- AC-V2-EXECUTION-003（fallback 不能满足 implementation evidence）：V2-050A1 提供 registry/evaluator/decision record 接口，但最终 checkbox 仍需 V2-050B 证明 verifier 实际解析 registry、调用 evaluator、记录 fallback decision，并拒绝 allowed=False 或 registry 缺失的 fallback artifact 后才能勾选。
- Phase 5 Evidence + Checker（证据、检查与返工）：A1 是 V2-050A ~ V2-050F 七个工作包中的第二项；完成后 Phase 5 进度应从 1/7 改为 2/7。

完成 V2-050A1 implementation（实施）后应按 backlog 完成协议更新：

1. `doc/04-implementation/backlog.md`：V2-050A1 状态改为 DONE，当前未完成工作包指向 V2-050B，Phase 5 进度改为 2/7。
2. `doc/04-implementation/acceptance-criteria.md`：若仅完成 A1，不勾选 AC-V2-EXECUTION-003；等 V2-050B verifier wiring（验证器接线）完成后再勾选。
3. `doc/05-project-log/2026-05.md`：追加 V2-050A1 记录，包含 negative / happy tests 和验证命令。
4. `doc/04-implementation/INDEX.md`：新增本 spec 文档索引项。
5. `doc/05-project-log/decisions.md`：若 implementation 阶段保持本 spec 边界，不需要新增 DEC；若改变 A1/B fallback gate 分工，则新增 DEC。

## 15. 已收敛评审点

1. V2-050A1 不只是 registry lookup（注册表查询），还要定义 V2-050B 必须消费的 FallbackDecisionRecord（降级判定记录）。
2. V2-050A1 不实现完整 EvidenceVerifier（证据验证器），但会锁定 verifier 的 fallback 接口合同。
3. FallbackDecisionRecord 是 audit fact（审计事实），不是 verified evidence（已验证证据）。
4. `evaluate_fallback_claim` 是唯一 fallback gate（降级门禁）入口。
5. evaluator（判定器）必须以完整 EvidenceClaim.acceptance_refs 一次性调用。
6. `TEST_ONLY_SIMULATION`、`PROVIDER_UNAVAILABLE`、`DETERMINISTIC_GOVERNANCE_DRAFT` 不能通过 registry 成为 evidence satisfaction path（证据满足路径）。
7. `TOOLING_PREFLIGHT` 锁定为允许作为 diagnostic decision（诊断判定）记录，但不得计入 blocking FinalEvidenceTable（阻塞最终证据表）。
8. AC-V2-EXECUTION-003（fallback 不能满足 implementation evidence）最终勾选仍等待 V2-050B verifier wiring（验证器接线），A1 只提供必要接口和防漂移边界。
