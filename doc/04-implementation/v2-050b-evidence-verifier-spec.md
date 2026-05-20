# V2-050B EvidenceVerifier 设计 Spec

## 1. 现实场景

本轮对应的现实场景是：worker（实施智能体）、provider（模型供应商）或 runner（命令运行器）已经交出 EvidenceClaim（证据声明），声称某些 artifact（产物）可以证明某条 acceptance criterion（验收项）。但在真实项目里，声明本身不等于证据；报销单上写了“我买了设备”不等于发票真实、金额正确、付款可追踪。

通俗地说，V2-050B 要加的是“证据验货员”：逐条核验 EvidenceClaim（证据声明）背后的 artifact/hash/provider/command/fallback lineage（产物 / 哈希 / 模型调用 / 命令 / 降级来源链），把可信声明转换为 VerifiedEvidence（已验证证据），把任何缺口转换为 blocker（阻断项）。它不负责统计整份验收合同是否全部满足；那是 V2-050C FinalEvidenceTable（最终证据表）的职责。

## 2. 目标

实现 EvidenceVerifier（证据验证器）的最小边界：

1. 验证 EvidenceClaim（证据声明）引用的 artifacts（产物）在 ArtifactManifest（产物清单）中存在。
2. 验证每个 artifact 都有稳定 sha256 hash（哈希）。
3. 验证 claim.producer_attempt_ref（声明产出尝试引用）能追踪到 succeeded ProviderAttempt（成功模型调用尝试记录）。
4. 验证 command evidence（命令证据）必须来自 VerificationRun（验证运行），且 run 已通过并有 stdout/stderr artifact hashes（标准输出/错误输出产物哈希）。
5. 验证 claim.acceptance_refs（验收引用）属于 active AcceptanceContract（活跃验收合同）。
6. 验证 claim 与 EvidenceObligation（证据义务）的 acceptance refs、source surface refs 和 artifact type（产物类型）一致，同时保留 required_verifier（必需验证器）作为合同派生的业务策略名。
7. 验证 EvidencePurpose（证据用途）与 RequiredArtifactType（必需产物类型）匹配。
8. 对 fallback claim（降级声明）强制经过 FallbackPolicyRegistry（降级策略注册表）和 FallbackDecisionRecord（降级判定记录）。
9. 拒绝 synthetic verification（合成验证）、provider zero-attempt（零模型调用）、claim-only success（仅靠声明成功）和 fallback allowed=False（降级判定不允许）。
10. 输出逐条 VerifiedEvidence（已验证证据）或 EvidenceVerificationBlocker（证据验证阻断项）。

## 3. 非目标

V2-050B 不做以下事情：

1. 不生成 EvidenceClaim（证据声明）；claim builder（声明构建函数）属于 V2-050A。
2. 不定义 fallback policy（降级策略）或 decision record（判定记录）；registry/evaluator（注册表 / 判定器）属于 V2-050A1。
3. 不实现 FinalEvidenceTable（最终证据表）；多条 evidence 对 active AcceptanceContract（活跃验收合同）的覆盖汇总属于 V2-050C。
4. 不实现 CheckerVerdict（检查结论）、checker（检查者）或 rework ticket（返工任务）；这些属于 V2-050D/E。
5. 不接入 TicketReducer（任务状态归约器）completion gate（完成门禁）；formal evidence/checker model（正式证据 / 检查模型）适配属于 V2-050F。
6. 不构建 SourceInventory（源码清单）；最终源码文件与 package root/git hash（包根 / Git 哈希）来源链属于 V2-060C。
7. 不运行 command（命令），不调用 provider（模型供应商），不补 artifact（产物）。Verifier（验证器）只消费已有事实。
8. 不读取旧 runtime（旧运行时）或旧 contracts（旧合同）作为实现依据。

## 4. 选型结论

采用“逐条 EvidenceClaim 验真”的方案。

### 4.1 被采用方案：单条 claim verifier

EvidenceVerifier（证据验证器）一次只验证一条 EvidenceClaim（证据声明），输出一条 VerifiedEvidence（已验证证据）或一组 EvidenceVerificationBlocker（证据验证阻断项）。

优点：

- 职责清晰：V2-050B 负责“这条证据可信吗”，V2-050C 负责“所有 blocking criteria（阻塞验收项）是否齐全”。
- 与 backlog（待办）依赖一致，避免提前吞掉 FinalEvidenceTable（最终证据表）。
- negative tests（负例测试）可以精确证明 synthetic/fallback/zero-attempt/hash 缺口无法通过。
- 后续 CheckerVerdict（检查结论）和 CompletionGate（完成门禁）可以消费稳定的 VerifiedEvidence（已验证证据）结构。

代价：

- V2-050B 完成后仍不能证明整体 acceptance map complete（验收映射完整）。
- V2-050C 仍需实现聚合与 missing/failed/satisfied（缺失 / 失败 / 满足）状态计算。

### 4.2 未采用方案：claim verifier + 局部覆盖预检

在 verifier 中同时检查当前 claim 对 blocking acceptance refs（阻塞验收引用）的局部覆盖。

不采用原因：coverage（覆盖率）判断需要全量 claims 和 active contract（活跃合同），放在 V2-050B 会与 V2-050C 重叠。

### 4.3 未采用方案：verifier 直接产出 evidence map

V2-050B 接收多条 claims 并直接产出接近 FinalEvidenceTable（最终证据表）的 evidence map（证据映射）。

不采用原因：这会模糊 Phase 5（阶段 5）分包边界，也会让 CheckerVerdict（检查结论）和 closeout（收尾）过早依赖未冻结的聚合语义。

## 5. 已决实施决定

1. EvidenceClaim（证据声明）不是 VerifiedEvidence（已验证证据）。任何 closeout（收尾）或 checker approval（检查者批准）不得直接消费 claim。
2. VerifiedEvidence（已验证证据）只表示单条 claim 被验证可信，不表示 active AcceptanceContract（活跃验收合同）已全部满足。
3. EvidenceVerifier（证据验证器）必须 fail closed（失败关闭）：缺 artifact、缺 hash、缺 provider attempt、缺 command run、缺 active acceptance ref、缺 fallback decision 都失败。
4. ArtifactManifest（产物清单）是 V2-050B 对 artifact existence/hash（产物存在性 / 哈希）的最小事实输入；它不是 SourceInventory（源码清单），不证明最终源码来源链。
5. EvidenceVerifier（证据验证器）首版消费 per-claim ArtifactManifest（单条声明产物清单）：manifest 只应包含本次 claim.artifact_refs 对应条目，避免把全局 artifact catalog（全局产物目录）误当 source inventory（源码清单）。
6. ArtifactManifestEntry（产物清单条目）必须至少包含 artifact_ref（产物引用）、sha256、producer_attempt_ref（产出尝试引用）和 source_ref（来源引用）。
7. ProviderAttempt（模型调用尝试记录）必须存在且 status=succeeded；failed attempt（失败尝试）只能作为审计事实，不能满足 verified evidence（已验证证据）。
8. Primary claim（主路径声明）必须绑定 PRIMARY_PROVIDER_OUTPUT（主模型输出）attempt；fallback claim（降级声明）必须绑定 FALLBACK_ARTIFACT（降级产物）attempt 且 fallback_kind（降级类型）一致。
9. VerificationRun claim（验证运行声明）必须绑定 passed VerificationRun（通过的验证运行）；failed command（失败命令）产生 blocker，不产生 VerifiedEvidence。
10. VerificationRun claim 的 artifact_refs 必须等于该 run 的 stdout_ref/stderr_ref（标准输出/错误引用）对应 EvidenceArtifactRef（证据产物引用），且二者都必须出现在 ArtifactManifest 中并携带 sha256。
11. Active AcceptanceContract（活跃验收合同）必须为 status=active；claim.acceptance_refs 必须全部属于 active contract criteria（验收合同条目）。
12. Claim 与 EvidenceObligation（证据义务）必须完全对齐：evidence_obligation_ref、acceptance_refs、source_surface_refs 和 required_artifact_type 必须一致。
13. evidence_obligation.required_verifier（证据义务必需验证器）保持 `verification_strategy -> required_verifier`（验证策略到必需验证器）的合同派生语义；V2-050B 不把它收窄为实现引擎白名单，也不要求单一固定值。
14. EvidencePurposePolicy（证据用途策略）用于声明 RequiredArtifactType（必需产物类型）允许哪些 EvidencePurpose（证据用途）；mismatch 必须失败。该策略是 verifier input（验证器输入），不是静态 universal AC（通用验收标准）。V2-050B 只消费该策略；策略如何从合同层或 V2-050C 汇总上下文派生，留给后续工作包。
15. Fallback claim 必须同时携带 FallbackPolicyRegistry（降级策略注册表）、FallbackDecisionRecord（降级判定记录）和 FallbackDecisionRecordedRef（降级判定记录事实引用）。
16. Verifier 对 fallback claim 必须通过 V2-050A1 的 evaluate_fallback_claim（判定降级声明函数）重新计算 expected decision（预期判定），再与传入的 FallbackDecisionRecord 做完全一致性校验；不得重新实现 fallback evaluator（降级判定器）。
17. Verifier 调用 evaluate_fallback_claim 时必须使用 EvidenceVerificationInput.verified_at 作为 evaluated_at，保证 fallback decision（降级判定）与 VerifiedEvidence（已验证证据）的时间线一致。
18. FallbackDecisionRecord.decision.allowed=False 必须产生 blocker，即使其它 artifact/hash/provider 校验都通过。
19. Primary claim 不得携带 fallback decision record；否则失败。
20. VerifiedEvidence（已验证证据）必须携带 artifact hash refs（产物哈希引用）和可审计 lineage（来源链），包含 claim ref、producer attempt ref、verification run refs 和 fallback decision refs（如适用）。
21. EvidenceVerificationBlocker（证据验证阻断项）必须可审计，至少记录 blocker code（阻断代码）、message（说明）和相关 ref。
22. Verifier 不 append event（追加事件）、不写 projection（投影）、不更新 ticket status（任务状态）。事件接线留给后续 reducer/closeout（状态归约器 / 收尾）工作包。

## 6. 模块设计

### 6.1 `src/boardroom_os/evidence/verifier.py`

新增模块包含：

- `EvidenceVerificationError`（证据验证错误）
- `VerifiedEvidenceRef`（已验证证据引用）
- `ArtifactSha256`（产物 SHA-256 哈希）
- `ArtifactManifestEntry`（产物清单条目）
- `ArtifactManifest`（产物清单）
- `EvidencePurposeRule`（证据用途规则）
- `EvidencePurposePolicy`（证据用途策略）
- `FallbackDecisionRecordedRef`（降级判定记录事实引用）
- `VerifiedArtifact`（已验证产物）
- `VerifiedEvidence`（已验证证据）
- `EvidenceVerificationBlockerCode`（证据验证阻断代码）
- `EvidenceVerificationBlocker`（证据验证阻断项）
- `EvidenceVerificationInput`（证据验证输入）
- `EvidenceVerificationResult`（证据验证结果）
- `EvidenceVerifier`（证据验证器）

### 6.2 ArtifactManifestEntry

建议 schema：

```yaml
artifact_ref:
sha256:
producer_attempt_ref:
source_ref:
artifact_kind:
```

字段说明：

- `artifact_ref`：EvidenceArtifactRef（证据产物引用）。
- `sha256`：ArtifactSha256（产物哈希），必须是 64 位小写 hex digest（十六进制摘要）。
- `producer_attempt_ref`：ProviderAttemptRef（模型调用尝试引用），必须与 claim.producer_attempt_ref 一致。
- `source_ref`：来源对象引用，必须与 EvidenceClaim.source_ref（证据声明来源引用）一致，或在 VerificationRun claim（验证运行声明）中与 verification_run_id（验证运行 ID）一致。
- `artifact_kind`：短文本，供审计展示，例如 `provider_output`、`stdout`、`stderr`、`hash_manifest`。

ArtifactManifest（产物清单）是 per-claim manifest（单条声明清单），只包含本次 EvidenceClaim.artifact_refs（证据声明产物引用）需要验证的条目；它不是全局 artifact catalog（全局产物目录）。ArtifactManifest 必须拒绝空 entries、重复 artifact_ref、缺 hash、hash 格式错误、包含 claim.artifact_refs 之外的额外条目和 malformed ref（格式错误引用）。

### 6.3 EvidencePurposePolicy

RequiredArtifactType（必需产物类型）是 contract-derived text value（合同派生文本值），不能硬编码成 universal enum（通用枚举）。因此 V2-050B 使用显式 EvidencePurposePolicy（证据用途策略）表达允许关系。V2-050B 只消费该策略并执行校验；策略如何从 AcceptanceContract（验收合同）、EvidenceObligation（证据义务）或后续 FinalEvidenceTable（最终证据表）上下文派生，不在本工作包实现。

建议 schema：

```yaml
rules:
  - required_artifact_type:
    allowed_purposes:
```

校验规则：

1. rules 不得为空。
2. 每个 required_artifact_type 只能出现一次。
3. allowed_purposes 不得为空。
4. claim.required_artifact_type 必须存在对应 rule。
5. claim.expected_purpose 必须在 allowed_purposes 中。

示例：

```yaml
rules:
  - required_artifact_type: source_patch
    allowed_purposes: [implementation]
  - required_artifact_type: command_output
    allowed_purposes: [implementation, diagnostic]
  - required_artifact_type: hash_manifest
    allowed_purposes: [deterministic]
```

### 6.4 EvidenceVerificationInput

建议 schema：

```yaml
claim:
evidence_obligation:
active_acceptance_contract:
artifact_manifest:
purpose_policy:
provider_attempts:
verification_runs:
fallback_policy_registry:
fallback_decision_record:
fallback_decision_recorded_ref:
verified_at:
```

说明：

- `claim`：EvidenceClaim（证据声明）。
- `evidence_obligation`：EvidenceObligation（证据义务），必须匹配 claim.evidence_obligation_ref。
- `active_acceptance_contract`：AcceptanceContract（验收合同），必须为 active。
- `artifact_manifest`：ArtifactManifest（产物清单）。
- `purpose_policy`：EvidencePurposePolicy（证据用途策略）。
- `provider_attempts`：tuple[ProviderAttempt, ...]，用于按 claim.producer_attempt_ref 查找 attempt。
- `verification_runs`：tuple[VerificationRun, ...]，用于 VerificationRun claim（验证运行声明）。
- `fallback_policy_registry`：FallbackPolicyRegistry | None（降级策略注册表）。fallback claim 必须存在。
- `fallback_decision_record`：FallbackDecisionRecord | None（降级判定记录）。fallback claim 必须存在。
- `fallback_decision_recorded_ref`：FallbackDecisionRecordedRef | None（降级判定记录事实引用）。fallback claim 必须存在。
- `verified_at`：timezone-aware datetime（带时区时间）。

### 6.5 VerifiedEvidence

建议 schema：

```yaml
version: 1
verified_evidence_id:
evidence_claim_ref:
evidence_obligation_ref:
producer_attempt_ref:
source_kind:
source_ref:
expected_purpose:
required_artifact_type:
acceptance_refs:
source_surface_refs:
verified_artifacts:
verification_run_refs:
fallback_decision_record_ref:
fallback_decision_recorded_ref:
verified_at:
```

字段说明：

- `verified_evidence_id`：默认确定性 ID，建议模板 `verified-evidence.<evidence_claim_id>`。
- `verified_artifacts`：tuple[VerifiedArtifact, ...]，每项绑定 artifact_ref 和 sha256。
- `fallback_decision_record_ref`：仅 fallback claim 存在。
- `fallback_decision_recorded_ref`：仅 fallback claim 存在，用于后续 V2-050F completion gate（完成门禁）验证 fallback lineage（降级来源链）。

VerifiedEvidence（已验证证据）不得包含 `status=satisfied` 之类聚合状态；satisfied/failed/missing（满足 / 失败 / 缺失）属于 FinalEvidenceTable（最终证据表）。

### 6.6 EvidenceVerificationResult

建议行为：

```python
result = EvidenceVerifier().verify(input)
if result.verified_evidence is not None:
    ...
else:
    ... result.blockers ...
```

规则：

1. 成功时 `verified_evidence` 非空，`blockers == ()`。
2. 失败时 `verified_evidence is None`，`blockers` 至少一项。
3. 实现可以累积多个 blocker（阻断项），但不得在存在 blocker 时返回部分 verified evidence（部分已验证证据）。

## 7. 数据流

```text
EvidenceClaim（证据声明）
  + EvidenceObligation（证据义务）
  + active AcceptanceContract（活跃验收合同）
  + ArtifactManifest（产物清单）
  + ProviderAttempt（模型调用尝试记录）
  + VerificationRun（验证运行，可选）
  + FallbackDecisionRecord（降级判定记录，可选）
      -> EvidenceVerifier（证据验证器）
          -> VerifiedEvidence（已验证证据）
          -> V2-050C FinalEvidenceTable（最终证据表）
```

fallback path（降级路径）：

```text
EvidenceClaim.fallback_marker（降级标记）
  + FallbackPolicyRegistry（降级策略注册表）
  + evaluate_fallback_claim（判定降级声明）
  + supplied FallbackDecisionRecord（传入降级判定记录）
  + FallbackDecisionRecordedRef（降级判定记录事实引用）
      -> EvidenceVerifier（证据验证器）
          -> allowed=True 才能生成 VerifiedEvidence（已验证证据）
          -> allowed=False 生成 blocker（阻断项）
```

关键不变量：fallback implementation evidence（降级实施证据）必须失败，因为 evaluate_fallback_claim（判定降级声明函数）会基于 claim.expected_purpose（声明预期用途）返回 allowed=False。

## 8. Fail-closed 规则

以下情况必须失败：

1. EvidenceVerificationInput 缺 claim。
2. EvidenceVerificationInput 缺 evidence_obligation。
3. EvidenceVerificationInput 缺 active_acceptance_contract。
4. EvidenceVerificationInput 缺 artifact_manifest。
5. EvidenceVerificationInput 缺 purpose_policy。
6. `verified_at` 无时区。
7. active_acceptance_contract.status 不是 active。
8. claim.evidence_obligation_ref 与 evidence_obligation.evidence_obligation_id 不一致。
9. claim.acceptance_refs 与 evidence_obligation.acceptance_refs 不一致。
10. claim.source_surface_refs 与 evidence_obligation.source_surface_refs 不一致。
11. claim.required_artifact_type 与 evidence_obligation.required_artifact_type 不一致。
12. claim.acceptance_refs 中任一 ref 不属于 active_acceptance_contract.criteria。
13. purpose_policy 缺 claim.required_artifact_type 的 rule。
14. claim.expected_purpose 不在对应 rule.allowed_purposes 中。
15. claim.artifact_refs 中任一 artifact_ref 不在 ArtifactManifest 中。
16. ArtifactManifest 包含 claim.artifact_refs 之外的额外 artifact_ref。
17. ArtifactManifestEntry 缺 sha256。
18. ArtifactManifestEntry.sha256 不是 64 位小写 hex digest。
19. ArtifactManifestEntry.producer_attempt_ref 与 claim.producer_attempt_ref 不一致。
20. provider_attempts 为空或找不到 claim.producer_attempt_ref。
21. 找到的 ProviderAttempt.status 不是 succeeded。
22. primary claim 绑定 FALLBACK_ARTIFACT ProviderAttempt。
23. fallback claim 绑定 PRIMARY_PROVIDER_OUTPUT ProviderAttempt。
24. fallback claim 的 claim.fallback_marker.fallback_kind 与 ProviderAttempt.fallback_kind 不一致。
25. claim.source_kind == verification_run 但找不到 VerificationRun。
26. VerificationRun.status 不是 passed。
27. VerificationRun.verification_run_id 与 claim.source_ref 不一致。
28. VerificationRun claim 的 artifact_refs 不等于 stdout_ref/stderr_ref 对应 EvidenceArtifactRef。
29. VerificationRun stdout/stderr artifact 缺 ArtifactManifestEntry 或缺 sha256。
30. claim.source_kind == work_product 但 verification_run_refs 非空。
31. primary claim 携带 fallback decision record。
32. fallback claim 缺 FallbackPolicyRegistry。
33. fallback claim 的 fallback_policy_ref 无法通过 registry 解析。
34. fallback claim 缺 FallbackDecisionRecord。
35. fallback claim 缺 FallbackDecisionRecordedRef。
36. Verifier 未通过 evaluate_fallback_claim（判定降级声明函数）重新计算 expected decision。
37. Verifier 调用 evaluate_fallback_claim 时未使用 EvidenceVerificationInput.verified_at 作为 evaluated_at。
38. FallbackDecisionRecord 与 evaluate_fallback_claim 结果不一致。
39. FallbackDecisionRecord 与 claim 的 claim ref、producer attempt、policy ref、kind、purpose、artifact type 或 acceptance refs 任一不一致。
40. FallbackDecisionRecord.decision.allowed is False。
41. synthetic verification（合成验证）只提供 claim 或 claim-level “passed” 标记，没有真实 VerificationRun + artifact hashes。
42. EvidenceClaim 试图绕过 artifact/hash/provider/command 任一事实 join（关联）。

## 9. Happy path

### 9.1 primary WorkProduct evidence

最小正例：

1. 构造 succeeded ProviderAttempt（成功模型调用尝试记录），outcome 为 PRIMARY_PROVIDER_OUTPUT。
2. 构造 WorkProduct-derived EvidenceClaim（工作产物派生证据声明），expected_purpose 为 implementation。
3. ArtifactManifest（产物清单）包含 claim.artifact_refs 全部条目，每项有 sha256 且 producer_attempt_ref 匹配。
4. active AcceptanceContract（活跃验收合同）包含 claim.acceptance_refs。
5. EvidenceObligation（证据义务）与 claim 完全一致。
6. EvidencePurposePolicy（证据用途策略）允许当前 required_artifact_type 用于 implementation。
7. EvidenceVerifier 返回 VerifiedEvidence，且 verified_artifacts 保留 artifact_ref + sha256。

### 9.2 command VerificationRun evidence

最小正例：

1. 使用 CommandRunner（命令运行器）产生 passed VerificationRun（通过验证运行）。
2. 构造 VerificationRun-derived EvidenceClaim（验证运行派生证据声明）。
3. ArtifactManifest 包含 stdout/stderr refs 对应条目和 sha256。
4. ProviderAttempt 存在且 succeeded，用于保持 producer lineage（产出来源链）。
5. EvidenceVerifier 返回 VerifiedEvidence，verification_run_refs 包含该 VerificationRunRef（验证运行引用）。

### 9.3 deterministic fallback evidence

最小正例：

1. 构造 fallback EvidenceClaim，expected_purpose 为 deterministic，fallback_kind 为 CONTRACT_ALLOWED_DETERMINISTIC_TRANSFORM。
2. 构造 FallbackPolicyRegistry，能解析 claim.fallback_marker.fallback_policy_ref。
3. 通过 evaluate_fallback_claim 生成 allowed=True 的 FallbackDecisionRecord。
4. 输入携带 FallbackDecisionRecordedRef。
5. ArtifactManifest 与 ProviderAttempt 均匹配。
6. EvidenceVerifier 返回 VerifiedEvidence，并携带 fallback_decision_record_ref 与 fallback_decision_recorded_ref。

### 9.4 blocked fallback decision is auditable

最小正例：

1. 构造 fallback EvidenceClaim，expected_purpose 为 implementation。
2. 通过 evaluate_fallback_claim 生成 allowed=False 的 FallbackDecisionRecord。
3. EvidenceVerifier 不抛出不可审计异常，而是返回 EvidenceVerificationBlocker。
4. blocker 指向 FallbackDecisionRecordRef，并保留 blocking reason（阻断原因）。

## 10. 测试计划

新增测试：

- `tests/evidence/test_evidence_verifier.py`
- `tests/negative/test_synthetic_evidence_rejected.py`

### 10.1 Negative tests（先写）

`tests/negative/test_synthetic_evidence_rejected.py`：

1. `test_verifier_rejects_claim_without_artifact_manifest_entry`
2. `test_verifier_rejects_artifact_without_sha256`
3. `test_verifier_rejects_malformed_sha256`
4. `test_verifier_rejects_provider_zero_attempt`
5. `test_verifier_rejects_failed_provider_attempt`
6. `test_verifier_rejects_acceptance_ref_outside_active_contract`
7. `test_verifier_rejects_inactive_acceptance_contract`
8. `test_verifier_rejects_evidence_obligation_ref_mismatch`
9. `test_verifier_rejects_acceptance_refs_mismatch`
10. `test_verifier_rejects_source_surface_refs_mismatch`
11. `test_verifier_rejects_required_artifact_type_mismatch`
12. `test_verifier_rejects_purpose_artifact_type_mismatch`
13. `test_verifier_rejects_manifest_with_extra_artifact_ref`
14. `test_verifier_rejects_synthetic_verification_without_run_record`
15. `test_verifier_rejects_failed_verification_run`
16. `test_verifier_rejects_verification_run_without_stdout_stderr_hashes`
17. `test_verifier_rejects_verification_run_artifact_ref_mismatch`
18. `test_verifier_rejects_primary_claim_with_fallback_attempt`
19. `test_verifier_rejects_primary_claim_with_fallback_decision_record`
20. `test_verifier_rejects_fallback_claim_with_primary_attempt`
21. `test_verifier_rejects_fallback_claim_without_registry`
22. `test_verifier_rejects_fallback_claim_with_unresolved_policy`
23. `test_verifier_rejects_fallback_claim_without_decision_record`
24. `test_verifier_rejects_fallback_claim_without_decision_recorded_ref`
25. `test_verifier_rejects_fallback_decision_record_scope_mismatch`
26. `test_verifier_rejects_fallback_decision_allowed_false`
27. `test_verifier_uses_verified_at_for_fallback_decision_evaluation`
28. `test_verifier_uses_evaluate_fallback_claim_once_with_full_scope`

### 10.2 Happy path tests

`tests/evidence/test_evidence_verifier.py`：

1. `test_primary_work_product_claim_becomes_verified_evidence`
2. `test_command_verification_run_claim_becomes_verified_evidence`
3. `test_allowed_deterministic_fallback_claim_becomes_verified_evidence`
4. `test_blocked_fallback_decision_returns_auditable_blocker`
5. `test_verified_evidence_uses_deterministic_default_id`
6. `test_verified_evidence_serializes_as_audit_friendly_json`
7. `test_verifier_result_is_success_or_blockers_not_both`

### 10.3 Regression scope

实现完成后至少运行：

```bash
PYTHONPATH="src:." python -m pytest tests/negative/test_synthetic_evidence_rejected.py -q
PYTHONPATH="src:." python -m pytest tests/evidence/test_evidence_verifier.py -q
PYTHONPATH="src:." python -m pytest tests/evidence/test_evidence_claim.py tests/evidence/test_fallback_policy_registry.py tests/evidence/test_evidence_verifier.py tests/negative/test_synthetic_evidence_rejected.py tests/negative/test_fallback_registry_fail_closed.py -q
PYTHONPATH="src:." python -m pytest tests/contracts tests/reducers tests/execution tests/evidence tests/negative -q
```

## 11. 与现有模块的关系

1. 复用 `boardroom_os.evidence.claim.EvidenceClaim`（证据声明）、EvidenceArtifactRef（证据产物引用）、EvidenceClaimSourceKind（证据声明来源类型）和 FallbackLineageMarker（降级来源链标记）。
2. 复用 `boardroom_os.evidence.fallback_registry.FallbackPolicyRegistry`（降级策略注册表）、FallbackDecisionRecord（降级判定记录）和 evaluate_fallback_claim（判定降级声明函数）。
3. 复用 `boardroom_os.providers.attempt.ProviderAttempt`（模型调用尝试记录）。
4. 复用 `boardroom_os.execution.verification_run.VerificationRun`（验证运行）。
5. 复用 `boardroom_os.contracts.acceptance.AcceptanceContract`（验收合同）和 AcceptanceCriterion（验收项）。
6. 复用 `boardroom_os.contracts.evidence_obligation.EvidenceObligation`（证据义务）、RequiredArtifactType（必需产物类型）和 RequiredVerifier（必需验证器）。
7. 不修改 RuntimeExecutor（运行时执行器）；runtime 仍只记录 provider/work product/command facts（模型调用 / 工作产物 / 命令事实）。
8. 不修改 CommandRunner（命令运行器）；verifier 只消费 VerificationRun（验证运行）结果。
9. 不修改 TicketReducer（任务状态归约器）；V2-050F 再接入 formal completion gate（正式完成门禁）。
10. 不修改 SourceInventory（源码清单）相关设计；V2-050B 的 ArtifactManifest（产物清单）只证明 claim artifact hashes（声明产物哈希），不证明 package source lineage（包源码来源链）。

## 12. 验收映射

本 spec 对应 backlog 工作包：V2-050B。

覆盖 `backlog.md` 中 V2-050B 的验收口径：

- 验证 artifact existence（产物存在性）与 hash stability（哈希稳定性）。
- 验证 producer attempt（产出模型调用尝试）、command run（命令运行）与 active contract refs（活跃合同引用）。
- 拒绝 synthetic verification（合成验证）、provider zero-attempt（零模型调用）和 artifact 缺 hash。
- 拒绝 acceptance_ref 不属于 active contract（活跃合同）的 claim。
- 通过 FallbackPolicyRegistry（降级策略注册表）解析 fallback_policy_ref（降级策略引用）。
- 消费 FallbackDecisionRecord（降级判定记录）并拒绝缺 decision、未记录 decision lineage、allowed=False 或 scope mismatch（作用域不匹配）。
- 证明 EvidencePurpose（证据用途）与 RequiredArtifactType（必需产物类型）不匹配必须失败。

覆盖 `acceptance-criteria.md`：

- AC-V2-EXECUTION-003（fallback 不能满足 implementation evidence）：V2-050B 完成后，若 negative/happy tests 证明 verifier 实际调用 registry/evaluator、消费 decision record，并拒绝 allowed=False / missing decision / implementation fallback，则该 checkbox 可勾选。
- AC-V2-EVIDENCE-001（command evidence from runner）：V2-040D 已提供 runner 事实；V2-050B 继续证明 claim-only synthetic command success 不能转成 VerifiedEvidence。
- AC-V2-EVIDENCE-002（source inventory proves lineage）：V2-050B 只同步证明 claim artifact/hash 不可伪造；最终 SourceInventory lineage（源码清单来源链）checkbox 仍等待 V2-060C。

完成 V2-050B implementation（实施）后应按 backlog 完成协议更新：

1. `doc/04-implementation/backlog.md`：V2-050B 状态改为 DONE，当前未完成工作包指向 V2-050C，Phase 5 进度改为 3/7，合计改为 31/53。
2. `doc/04-implementation/acceptance-criteria.md`：勾选 Phase 3 的 AC-V2-EXECUTION-003，并同步 Phase 3 “上述 AC checkbox 全部勾选”前置；Phase 5 的 AC-V2-EVIDENCE-002 仍保持未勾选，等待 V2-060C。
3. `doc/05-project-log/2026-05.md`：追加 V2-050B 记录，包含关键产出文件、negative/happy tests 和验证命令。
4. `doc/04-implementation/INDEX.md`：新增本 spec 文档索引项。
5. `doc/05-project-log/decisions.md`：若 implementation 阶段保持本 spec 的逐条 verifier 边界，不需要新增 DEC；若改变 V2-050B/V2-050C 分工或 fallback gate 分工，则新增 DEC。

## 13. 已收敛评审点

1. V2-050B 采用逐条 EvidenceClaim（证据声明）验真，不做 FinalEvidenceTable（最终证据表）聚合。
2. ArtifactManifest（产物清单）是 claim artifact/hash（声明产物 / 哈希）事实输入，不等同于 SourceInventory（源码清单）。
3. VerifiedEvidence（已验证证据）只代表单条 claim 可信，不代表 acceptance map complete（验收映射完整）。
4. EvidencePurposePolicy（证据用途策略）显式表达 artifact type 与 purpose 的允许关系，避免 verifier 自由重判 purpose；V2-050B 只消费该策略，不负责派生它。
5. VerificationRun claim（验证运行声明）必须有真实 VerificationRun（验证运行）和 stdout/stderr hashes（输出哈希），synthetic verification success（合成验证成功）不能通过。
6. ProviderAttempt（模型调用尝试记录）缺失或失败时，claim 不能变成 verified evidence。
7. Fallback claim（降级声明）必须经 FallbackPolicyRegistry（降级策略注册表）和 evaluate_fallback_claim（判定降级声明函数）路径重新计算并匹配 FallbackDecisionRecord（降级判定记录）；重新计算时使用 EvidenceVerificationInput.verified_at 作为 evaluated_at。
8. FallbackDecisionRecord.decision.allowed=False、缺 FallbackDecisionRecordedRef（降级判定记录事实引用）或 scope mismatch（作用域不匹配）都必须阻断 verified evidence。
9. V2-050B 完成后可闭合 AC-V2-EXECUTION-003（fallback 不能满足 implementation evidence），但不闭合 AC-V2-EVIDENCE-002（source inventory lineage）。
