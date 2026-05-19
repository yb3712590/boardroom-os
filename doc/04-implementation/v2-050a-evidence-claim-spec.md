# V2-050A EvidenceClaim 设计 Spec

## 1. 现实场景

本轮对应的现实场景是：worker（实施智能体）或 runner（运行器）交出了“我产出了这些源码 / 我跑了这些命令”的材料清单，但这些材料还没有被验收员核验。

通俗地说，V2-050A 要做的是给 Boardroom OS V2 加一张“证据申报单”：producer（产出者）可以声明某个 WorkProduct（工作产物）或 VerificationRun（验证运行）与哪些 acceptance refs（验收引用）、source surfaces（源码实现面）和 artifacts（产物引用）有关，但这张申报单本身不等于 verified evidence（已验证证据），更不能直接让 ticket（任务）完成或 closeout（收尾）通过。

## 2. 目标

实现 EvidenceClaim（证据声明）的最小 typed schema（类型化结构）和 claim builder（声明构建函数）：

1. 表达 producer 对 source / test / run / integration / closeout evidence（源码 / 测试 / 运行 / 集成 / 收尾证据）的声明。
2. 强制 claim（声明）携带 `producer_attempt_ref`、`acceptance_refs`、`source_surface_refs`、`artifact_refs` 和 `expected_purpose`。
3. 让 `expected_purpose`（证据预期用途）由 EvidenceObligation（证据义务）派生，verifier（证据验证器）不得在后续自由选择 purpose（用途）。
4. 支持从 WorkProduct（工作产物）生成 implementation claim（实施声明）。
5. 支持从 VerificationRun（验证运行）生成 command/test/run claim（命令 / 测试 / 运行声明）。
6. 对 fallback artifact（降级产物）保留 typed fallback marker（类型化降级标记），让 V2-050A1/V2-050B 能 fail closed（失败关闭）地解析 fallback lineage（降级来源链）。

## 3. 非目标

V2-050A 不做以下事情：

1. 不实现 EvidenceVerifier（证据验证器）；claim 不能直接变成 verified evidence（已验证证据）。
2. 不实现 FallbackPolicyRegistry（降级策略注册表）；registry 解析属于 V2-050A1。
3. 不调用 `evaluate_fallback_evidence`（降级证据判定函数）；fallback 判定属于 V2-050A1/V2-050B。
4. 不实现 FinalEvidenceTable（最终证据表）；汇总 acceptance coverage（验收覆盖）属于 V2-050C。
5. 不实现 CheckerVerdict（检查结论）或 rework ticket（返工任务）；这些属于 V2-050D/E。
6. 不计算 artifact hash（产物哈希）、不检查 artifact 是否存在、不读取 package root（包根）；这些属于 V2-050B/V2-060。
7. 不从 claim 推导 ticket completed（任务完成）；completion gate（完成门禁）属于 reducer（状态归约器）和 V2-050F。

## 4. 选型结论

采用“严格最小 claim schema + obligation-derived purpose（证据义务派生用途）”方案。

### 4.1 被采用方案：严格最小 EvidenceClaim

V2-050A 只新增 EvidenceClaim（证据声明）及其 builder（构建函数）。claim 记录 producer 声称满足什么 obligation（义务）、引用了哪些 artifacts（产物）、对应哪些 acceptance/source surface（验收/源码实现面），并携带由 obligation 派生的 `expected_purpose`。

优点：

- 阶段边界清晰，避免把 verifier/table/checker（验证器 / 证据表 / 检查者）提前塞入 V2-050A。
- 明确 claim 只是声明，不是 proof（证明）。
- `expected_purpose` 在 claim 阶段固定，为后续 fallback gate（降级门禁）和 EvidenceVerifier（证据验证器）提供不可篡改输入。
- 可直接衔接现有 WorkProductClaimDraft（工作产物证据声明草稿）、WorkProduct（工作产物）、VerificationRun（验证运行）和 EvidenceObligation（证据义务）。

代价：

- V2-050A 完成后还不能勾选 AC-V2-EVIDENCE-002/003（源码清单来源链 / evidence map complete），必须等 V2-050B/C 与 V2-060C。
- fallback claim（降级声明）只能被标记，不能在本工作包内判定 allowed/blocked（允许/阻断）。

### 4.2 未采用方案：EvidenceClaim 内置 verifier 结果

让 EvidenceClaim 直接包含 `status: verified | failed` 或 `verified_evidence_ref`。

不采用原因：会混淆 claim（声明）与 verified evidence（已验证证据），破坏“claim 只是 producer 声明，必须经 verifier 才能 closeout”的架构边界。

### 4.3 未采用方案：从 artifact type 自动推断 purpose

根据 `required_artifact_type`（必需产物类型）或 artifact ref（产物引用）自动推断 `expected_purpose`。

不采用原因：purpose（用途）必须来自 EvidenceObligation（证据义务）和 active contract（活跃合同）的约束。自动推断会让 verifier 在后续自由选择 purpose，容易把 implementation artifact（实施产物）误判成 deterministic evidence（确定性证据）。

## 5. 已决实施决定

1. EvidenceClaim（证据声明）是 producer claim（产出者声明），不是 verified evidence（已验证证据）。
2. EvidenceClaim 必须携带 `expected_purpose`，类型复用 `from boardroom_os.execution.fallback import EvidencePurpose`（证据用途）：`implementation | diagnostic | deterministic`。
3. EvidenceClaim 必须携带 `required_artifact_type`，类型复用 RequiredArtifactType（必需产物类型）。
4. EvidenceClaim 必须携带 `evidence_obligation_ref`，并由 builder 校验 claim 的 acceptance/source surface/artifact type 与 EvidenceObligation 一致。
5. WorkProduct（工作产物）来源的 claim 必须同时消费 WorkProduct 与 WorkProductClaimDraft（工作产物证据声明草稿）；WorkProduct 提供 producer/artifact/fallback lineage（产出者 / 产物 / 降级来源链），WorkProductClaimDraft 提供 acceptance_refs 与 source_surface_refs。
6. WorkProduct claim 的 `producer_attempt_ref`、`execution_package_ref`、`ticket_ref`、`artifact_refs` 必须在 WorkProduct 与 WorkProductClaimDraft 之间一致，且 claim_draft_ref 必须属于 WorkProduct.claim_refs。
7. VerificationRun（验证运行）来源的 claim 也必须携带 `producer_attempt_ref`；该 ref 由调用方传入，用于保持 command evidence（命令证据）与 provider attempt（模型调用尝试记录）的 producer lineage（产出来源链）相连。V2-050A 不验证 attempt 是否存在。
8. fallback claim 必须显式携带 typed fallback marker（类型化降级标记）：至少包括 `fallback_policy_ref` 与 `fallback_kind`。
9. 非 fallback claim 不得携带 fallback marker。
10. fallback marker 只表示“这是降级来源链的一部分”，不表示 fallback evidence 被允许满足任何 acceptance（验收）。
11. claim builder 不读取 active AcceptanceContract（活跃验收合同）或 PackageContract（包合同）；active contract ref 校验属于 EvidenceVerifier（证据验证器）。
12. claim builder 可校验 EvidenceObligation（证据义务）本身与输入对象之间的局部一致性，不能越权做全局 evidence verification（证据验证）。
13. 未显式传入 `evidence_claim_id` 时，builder 使用确定性默认模板：`evidence-claim.<source_kind>.<source_ref_value>.<evidence_obligation_id_value>`。
14. 测试应先写 negative tests（负例测试），证明缺字段、fallback marker 缺失或 purpose 越权都无法构造 claim。

## 6. 模块设计

### 6.1 `src/boardroom_os/evidence/claim.py`

新增 EvidenceClaim（证据声明）模块，包含：

- `EvidenceClaimRef`（证据声明引用）
- `EvidenceArtifactRef`（证据产物引用）
- `EvidenceClaimSourceKind`（证据声明来源类型）
- `FallbackLineageMarker`（降级来源链标记）
- `EvidenceClaim`（证据声明）
- `EvidenceClaimBuildError`（证据声明构建错误）
- `build_evidence_claim_from_work_product`（从工作产物构建证据声明）
- `build_evidence_claim_from_verification_run`（从验证运行构建证据声明）

### 6.2 EvidenceClaim 字段

建议 schema：

```yaml
version: 1
evidence_claim_id:
evidence_obligation_ref:
producer_attempt_ref:
source_kind: work_product | verification_run
source_ref:
expected_purpose: implementation | diagnostic | deterministic
required_artifact_type:
acceptance_refs:
source_surface_refs:
artifact_refs:
verification_run_refs:
fallback_marker:
summary:
```

字段说明：

- `evidence_claim_id`：EvidenceClaimRef（证据声明引用）。
- `evidence_obligation_ref`：EvidenceObligationRef（证据义务引用），绑定本 claim 声称满足的 obligation。
- `producer_attempt_ref`：ProviderAttemptRef（模型调用尝试引用），用于保持 producer lineage（产出来源链）。
- `source_kind`：EvidenceClaimSourceKind（证据声明来源类型），首版固定为 `work_product` 或 `verification_run`。
- `source_ref`：来源对象引用；WorkProductRef（工作产物引用）或 VerificationRunRef（验证运行引用）的字符串值。
- `expected_purpose`：EvidencePurpose（证据用途），由 EvidenceObligation 和 builder 输入固定。
- `required_artifact_type`：RequiredArtifactType（必需产物类型），来自 EvidenceObligation。
- `acceptance_refs`：claim 覆盖的 AcceptanceRef（验收引用）集合。
- `source_surface_refs`：claim 覆盖的 SourceSurfaceRef（源码实现面引用）集合。
- `artifact_refs`：EvidenceArtifactRef（证据产物引用）集合。
- `verification_run_refs`：类型为 `tuple[VerificationRunRef, ...]`；WorkProduct claim 必须使用空 tuple `()`，VerificationRun claim 必须包含当前 run。
- `fallback_marker`：FallbackLineageMarker（降级来源链标记），仅 fallback claim 可存在。
- `summary`：人类可读摘要，非空。

### 6.3 EvidenceClaimSourceKind

```python
class EvidenceClaimSourceKind(StrEnum):
    WORK_PRODUCT = "work_product"
    VERIFICATION_RUN = "verification_run"
```

首版只支持这两类来源。SourceInventory（源码清单）、CloseoutPackage（收尾包）或 ProcessAudit（流程审计）来源的 claim 如未来需要，应在对应工作包引入，不在 V2-050A 提前扩展。

### 6.4 FallbackLineageMarker

建议 schema：

```yaml
fallback_policy_ref:
fallback_kind:
producer_attempt_ref:
```

校验规则：

1. `fallback_policy_ref` 必填，类型为 FallbackPolicyRef（降级策略引用）。
2. `fallback_kind` 必填，类型为 FallbackKind（降级类型）。
3. `producer_attempt_ref` 必填，且必须等于 EvidenceClaim.producer_attempt_ref。
4. `producer_attempt_ref` 与 claim 顶层字段有意冗余：这样 FallbackLineageMarker（降级来源链标记）即使被单独审计或导出，也能独立证明它绑定的 producer attempt（产出尝试）。实现时不得为了“去重”删除该字段。
5. marker 不包含 `allowed` 字段，不包含 fallback decision（降级判定）；allowed/blocked 只能由 V2-050A1/V2-050B 记录。

### 6.5 `build_evidence_claim_from_work_product`

输入：

```yaml
work_product:
claim_draft:
evidence_obligation:
expected_purpose:
summary:
claim_id: optional
```

职责：

1. 从 WorkProduct（工作产物）读取 `producer_attempt_ref`、`artifact_refs`、`fallback_kind` 和 source_ref（来源引用）。
2. 从 WorkProductClaimDraft（工作产物证据声明草稿）读取 `acceptance_refs` 与 `source_surface_refs`；WorkProduct 本身不携带这两个字段。
3. 要求 claim_draft.claim_draft_ref 属于 WorkProduct.claim_refs。
4. 要求 WorkProduct 与 WorkProductClaimDraft 的 `producer_attempt_ref`、`execution_package_ref`、`ticket_ref` 和 `artifact_refs` 完全一致。
5. 要求 WorkProductClaimDraft 的 acceptance/source surface 覆盖 EvidenceObligation 的 acceptance/source surface。
6. 将 WorkProductArtifactRef（工作产物产物引用）转换为 EvidenceArtifactRef（证据产物引用）。
7. 复制 EvidenceObligation 的 `required_artifact_type` 和 `evidence_obligation_id`。
8. 如果 WorkProduct.fallback_kind 存在，则要求调用方传入 fallback_policy_ref，并生成 FallbackLineageMarker。
9. 如果 WorkProduct.fallback_kind 不存在，则不得传入 fallback_policy_ref，也不得生成 fallback marker。
10. 返回 EvidenceClaim，source_kind 为 `work_product`，source_ref 为 WorkProductRef（工作产物引用）。

建议函数签名：

```python
def build_evidence_claim_from_work_product(
    *,
    work_product: WorkProduct,
    claim_draft: WorkProductClaimDraft,
    evidence_obligation: EvidenceObligation,
    expected_purpose: EvidencePurpose,
    summary: str,
    fallback_policy_ref: FallbackPolicyRef | None = None,
    claim_id: EvidenceClaimRef | None = None,
) -> EvidenceClaim:
    ...
```

### 6.6 `build_evidence_claim_from_verification_run`

输入：

```yaml
verification_run:
evidence_obligation:
producer_attempt_ref:
acceptance_refs:
source_surface_refs:
expected_purpose:
summary:
claim_id: optional
```

职责：

1. 从 VerificationRun（验证运行）读取 `verification_run_id`、stdout/stderr refs（输出引用）和 ticket_ref（任务引用）。
2. V2-050A 的 EvidenceClaim schema 不复制 `command_id`：后续 verifier（证据验证器）可通过 `verification_run_refs` join（关联）完整 VerificationRun（验证运行）取得 command_id、command、cwd、exit_code 等命令事实，避免 claim 重复缓存 runner fact（运行器事实）。
3. 要求调用方显式传入 `producer_attempt_ref`，避免 command evidence 断开 provider attempt lineage（模型调用尝试来源链）。
4. 要求传入的 acceptance/source surface 与 EvidenceObligation 一致。
5. 将 stdout/stderr refs 转换为 EvidenceArtifactRef；VerificationRun 本身也进入 `verification_run_refs`。
6. 返回 EvidenceClaim，source_kind 为 `verification_run`，source_ref 为 VerificationRunRef（验证运行引用）。

建议函数签名：

```python
def build_evidence_claim_from_verification_run(
    *,
    verification_run: VerificationRun,
    evidence_obligation: EvidenceObligation,
    producer_attempt_ref: ProviderAttemptRef,
    acceptance_refs: tuple[AcceptanceRef, ...],
    source_surface_refs: tuple[SourceSurfaceRef, ...],
    expected_purpose: EvidencePurpose,
    summary: str,
    claim_id: EvidenceClaimRef | None = None,
) -> EvidenceClaim:
    ...
```

### 6.7 purpose 派生口径

V2-050A 不新增 EvidenceObligation 字段，因此 `expected_purpose` 由 builder 调用方显式传入，但 builder 必须做局部约束：

1. `expected_purpose` 必须是 EvidencePurpose（证据用途）枚举。
2. WorkProduct fallback claim 如果 `expected_purpose == implementation`，仍可构造 claim，但必须带 fallback marker；后续 verifier 必须拒绝 fallback satisfying implementation evidence（降级满足实施证据）。
3. deterministic purpose（确定性用途）不得由普通 primary WorkProduct（主路径工作产物）自动推断；只有调用方显式传入并经 EvidenceObligation 绑定后才可声明。
4. 未显式传入 `claim_id` 时，builder 使用确定性默认模板：`evidence-claim.<source_kind>.<source_ref_value>.<evidence_obligation_id_value>`。该模板不包含 timestamp（时间戳）或随机数，保证同一输入可稳定派生同一 claim ref（声明引用）。
5. V2-050B 必须基于 claim.expected_purpose 调用 fallback evaluator（降级判定器），不能重新选择 purpose。

## 7. 数据流

```text
WorkProduct（工作产物）
  + EvidenceObligation（证据义务）
  + EvidencePurpose（证据用途）
      -> EvidenceClaim（证据声明）
          -> V2-050A1 FallbackPolicyRegistry（降级策略注册表）
          -> V2-050B EvidenceVerifier（证据验证器）
          -> V2-050C FinalEvidenceTable（最终证据表）
```

```text
VerificationRun（验证运行）
  + producer_attempt_ref（模型调用尝试引用）
  + EvidenceObligation（证据义务）
  + acceptance/source refs（验收/源码实现面引用）
      -> EvidenceClaim（证据声明）
          -> V2-050B EvidenceVerifier（证据验证器）
```

EvidenceClaim 不 append event（追加事件）、不更新 projection（投影）、不完成 ticket（任务）。它只是把 producer 声明变成可验证输入。

## 8. Fail-closed 规则

以下情况必须失败：

1. EvidenceClaim 缺 `producer_attempt_ref`。
2. EvidenceClaim 缺 `evidence_obligation_ref`。
3. EvidenceClaim 缺 `acceptance_refs`。
4. EvidenceClaim 缺 `source_surface_refs`。
5. EvidenceClaim 缺 `artifact_refs`。
6. EvidenceClaim 缺 `expected_purpose`。
7. EvidenceClaim 缺 `required_artifact_type`。
8. EvidenceClaim `source_kind=verification_run` 但缺 `verification_run_refs`。
9. EvidenceClaim `source_kind=work_product` 但 `verification_run_refs` 非空。
10. EvidenceClaim 携带 fallback marker 但 marker.producer_attempt_ref 与 claim.producer_attempt_ref 不一致。
11. fallback WorkProduct 生成 claim 时缺 fallback_policy_ref。
12. fallback WorkProduct 生成 claim 时缺 typed fallback marker。
13. primary WorkProduct 生成 claim 时携带 fallback_policy_ref。
14. WorkProductClaimDraft acceptance_refs 不能覆盖 EvidenceObligation acceptance_refs。
15. WorkProductClaimDraft source_surface_refs 不能覆盖 EvidenceObligation source_surface_refs。
16. VerificationRun claim 传入的 acceptance_refs 不能覆盖 EvidenceObligation acceptance_refs。
17. VerificationRun claim 传入的 source_surface_refs 不能覆盖 EvidenceObligation source_surface_refs。
18. summary 为空。
19. `extra="forbid"`，未知字段必须失败。

## 9. Happy path

### 9.1 WorkProduct claim

最小正例：

1. 构造一个 succeeded ProviderAttempt（成功模型调用尝试记录）。
2. 通过既有 builder 生成 WorkProductSubmission（工作产物提交包）。
3. 从 WorkProductSubmission 取 `work_product` 与对应的 `claim_draft`；acceptance/source surface 来自 WorkProductClaimDraft（工作产物证据声明草稿），不是 WorkProduct 本体。
4. 选取与 claim_draft acceptance/source surface 一致的 EvidenceObligation（证据义务）。
5. 调用 `build_evidence_claim_from_work_product`，expected_purpose 为 `implementation`。
6. 返回 EvidenceClaim：
   - `source_kind == work_product`
   - `producer_attempt_ref == work_product.producer_attempt_ref`
   - `artifact_refs` 来自 WorkProduct artifact refs
   - `acceptance_refs` 与 claim_draft / obligation 一致
   - `source_surface_refs` 与 claim_draft / obligation 一致
   - `fallback_marker is None`

### 9.2 VerificationRun claim

最小正例：

1. 构造一个真实 CommandRunner 返回的 VerificationRun（验证运行）。
2. 显式传入 producer_attempt_ref（模型调用尝试引用）。
3. 选取与 acceptance/source surface 一致的 EvidenceObligation（证据义务）。
4. 调用 `build_evidence_claim_from_verification_run`，expected_purpose 为 `implementation` 或 `diagnostic`，由当前 obligation 的语义决定。
5. 返回 EvidenceClaim：
   - `source_kind == verification_run`
   - `source_ref == verification_run.verification_run_id.value`
   - `verification_run_refs == (verification_run.verification_run_id,)`
   - `artifact_refs` 包含 stdout/stderr refs
   - `producer_attempt_ref` 为调用方传入值

### 9.3 fallback WorkProduct claim

最小正例：

1. WorkProduct.fallback_kind 存在。
2. 调用 builder 时显式传入 fallback_policy_ref。
3. builder 生成 FallbackLineageMarker（降级来源链标记）。
4. EvidenceClaim 可被构造，但不会标记 allowed。
5. V2-050A1/V2-050B 后续必须解析 registry、调用 evaluator 并记录 decision 后，才可能进入 verified evidence。

## 10. 测试计划

新增 `tests/evidence/test_evidence_claim.py`。

### 10.1 Negative tests（先写）

1. `test_evidence_claim_requires_producer_attempt_ref`
2. `test_evidence_claim_requires_acceptance_refs`
3. `test_evidence_claim_requires_source_surface_refs`
4. `test_evidence_claim_requires_artifact_refs`
5. `test_evidence_claim_requires_expected_purpose`
6. `test_evidence_claim_requires_required_artifact_type`
7. `test_evidence_claim_requires_evidence_obligation_ref`
8. `test_verification_run_claim_requires_verification_run_ref`
9. `test_work_product_claim_rejects_verification_run_refs`
10. `test_fallback_claim_requires_typed_fallback_marker`
11. `test_fallback_marker_must_match_claim_producer_attempt_ref`
12. `test_work_product_builder_requires_claim_draft_ref_to_belong_to_work_product`
13. `test_work_product_builder_rejects_claim_draft_attempt_mismatch`
14. `test_work_product_builder_rejects_claim_draft_execution_package_mismatch`
15. `test_work_product_builder_rejects_claim_draft_ticket_mismatch`
16. `test_work_product_builder_rejects_fallback_without_policy_ref`
17. `test_work_product_builder_rejects_primary_with_policy_ref`
18. `test_work_product_builder_rejects_acceptance_refs_outside_obligation`
19. `test_work_product_builder_rejects_source_surface_refs_outside_obligation`
20. `test_verification_run_builder_rejects_missing_producer_attempt_ref`
21. `test_verification_run_builder_rejects_acceptance_refs_outside_obligation`
22. `test_evidence_claim_rejects_unknown_fields`

### 10.2 Happy path tests

1. `test_work_product_builds_implementation_evidence_claim`
2. `test_verification_run_builds_command_evidence_claim`
3. `test_fallback_work_product_claim_records_lineage_without_allowing_evidence`
4. `test_claim_expected_purpose_is_fixed_from_builder_input`

### 10.3 Regression scope

完成实现后至少运行：

```bash
PYTHONPATH="src:." python -m pytest tests/evidence/test_evidence_claim.py -q
PYTHONPATH="src:." python -m pytest tests/execution/test_work_product_submission.py tests/execution/test_command_runner.py tests/evidence/test_evidence_claim.py -q
PYTHONPATH="src:." python -m pytest tests/contracts tests/reducers tests/execution tests/evidence tests/negative -q
```

## 11. 与现有模块的关系

1. 复用 `from boardroom_os.execution.fallback import EvidencePurpose, FallbackKind`（证据用途 / 降级类型），不新增第二套 purpose/fallback enum（用途 / 降级枚举）。
2. 复用 EvidenceObligation（证据义务）、RequiredArtifactType（必需产物类型）和 EvidenceObligationRef（证据义务引用）。
3. 复用 ProviderAttemptRef（模型调用尝试引用）作为 producer attempt identity（产出尝试身份）。
4. 复用 WorkProduct（工作产物）、WorkProductArtifactRef（工作产物产物引用）和 VerificationRun（验证运行）。
5. 不修改 RuntimeExecutor（运行时执行器）；runtime 仍只记录事实，claim 由后续 evidence 层构建。
6. 不修改 TicketReducer（任务状态归约器）；V2-050F 再把 formal evidence/checker model（正式证据 / 检查模型）接入 completion gate（完成门禁）。
7. 不修改 AcceptanceContract（验收合同）或 PackageContract（包合同）；active contract 校验留给 EvidenceVerifier（证据验证器）。

## 12. 验收映射

本 spec 对应 backlog 工作包：V2-050A。

覆盖 `backlog.md` 中 V2-050A 的验收口径：

- claim 不是 verified evidence（已验证证据）。
- EvidencePurpose（证据用途）必须在 claim/obligation（声明 / 义务）链路中被类型化表达。
- implementation artifact（实施产物）不得被 verifier 后续自由重判为 deterministic evidence（确定性证据）。
- fallback claim（降级声明）必须携带 typed fallback marker（类型化降级标记），但是否 allowed（允许）必须留给 V2-050A1/V2-050B。

V2-050A 完成后应按 backlog 完成协议更新：

1. `doc/04-implementation/backlog.md`：V2-050A 状态改为 DONE，当前未完成工作包指向 V2-050A1，Phase 5 进度改为 1/7。
2. `doc/04-implementation/acceptance-criteria.md`：V2-050A 本身不单独勾选 Phase 5 抽象 AC；Phase 5 checkbox 仍等待 V2-050B/C/D/E/F 与 V2-060C。
3. `doc/05-project-log/2026-05.md`：追加 V2-050A 记录，包含 negative / happy tests 和验证命令。
4. `doc/04-implementation/INDEX.md`：新增本 spec 文档索引项。
5. `doc/05-project-log/decisions.md`：若 implementation 阶段没有改变 claim/verifier 边界，不需要新增 DEC。

## 13. 已收敛评审点

1. EvidenceClaim 是 producer declaration（产出者声明），不是 verified evidence（已验证证据）。
2. V2-050A 只实现 claim schema（声明结构）与 builder（构建函数），不实现 verifier/table/checker（验证器 / 证据表 / 检查者）。
3. `expected_purpose` 必须在 claim 阶段固定，并由 EvidenceObligation（证据义务）语义驱动。
4. WorkProduct claim 与 VerificationRun claim 都必须保留 producer_attempt_ref（产出尝试引用）。
5. fallback artifact（降级产物）在 claim 阶段只能记录 typed fallback lineage（类型化降级来源链），不能记录 allowed decision（允许判定）。
6. active contract refs（活跃合同引用）和 artifact hash（产物哈希）验证属于 V2-050B，不在 V2-050A 越界实现。
