# Contract 与 Evidence 模型

## 文档职责

本文件定义 acceptance、package、source surface、evidence obligation、evidence claim、source inventory、checker、closeout 的关系。

## 基本原则

1. Acceptance contract 来自当前需求，不来自静态测试常量。
2. Package contract 定义最终项目包，而不只是 source artifact。
3. Evidence claim 只是声明，必须被 verifier 验证后才可用于 closeout。
4. Source inventory 证明最终源码及其来源、hash、producer、acceptance refs。
5. Closeout 只能消费 verified evidence。

## 合同链

```text
BoardDirective
  -> ProjectCharter
  -> AcceptanceContract
  -> PackageContract
  -> TicketGraph obligations
  -> ExecutionPackage obligations
  -> EvidenceClaims
  -> VerifiedEvidenceTable
  -> CloseoutPackage
```

## AcceptanceContract

验收合同必须动态派生。

每条 criterion 至少包含：

```yaml
acceptance_ref:
statement:
blocking:
evidence_required:
source_surface_refs:
verification_strategy:
```

示例：

```yaml
acceptance_ref: AC-BOOK-API-STATE-001
statement: Books can transition between IN_LIBRARY and CHECKED_OUT through backend API.
blocking: true
evidence_required:
  - api_test_run
  - backend_source_inventory
  - persistence_evidence
```

## PackageContract

Package contract 至少包含：

```yaml
package_root:
project_type:
source_surfaces:
run_commands:
test_commands:
integration_boundaries:
docs_required:
closeout_required:
```

## SourceSurface

Source surface 是可以被 ticket 和 evidence 引用的实现面。

```yaml
source_surface_ref:
name:
paths:
owned_by:
acceptance_refs:
required_tests:
```

常见 surfaces：

- backend API；
- frontend UI；
- persistence layer；
- integration tests；
- docs；
- run manifest。

## EvidenceObligation

Evidence obligation 是 execution package 中必须完成的证据义务。

```yaml
evidence_obligation_id:
acceptance_refs:
required_artifact_type:
required_verifier:
blocking:
```

## EvidenceClaim

Claim 是 producer 对证据的声明，不是最终证明。

```yaml
evidence_claim_id:
producer_attempt_ref:
claim_type:
artifact_refs:
acceptance_refs:
source_surface_refs:
```

## EvidenceVerifier

Verifier 将 claim 转为 verified evidence 或 blocker。

Verifier 必须检查：

- artifact 是否存在；
- artifact hash 是否稳定；
- producer 是否可追踪；
- provider attempt 是否存在；
- command evidence 是否真实；
- acceptance refs 是否属于 active contract；
- source files 是否在 package root 和 git tree 内；
- 是否存在 placeholder / fallback / synthetic marker。

## VerificationRun

Command evidence 必须来自 runner。

```yaml
verification_run:
  command:
  cwd:
  exit_code:
  stdout_ref:
  stderr_ref:
  duration_ms:
  started_at:
  finished_at:
  runner_ref:
```

## SourceInventory

Source inventory 不能只证明引用存在。它必须绑定：

- package commit；
- file path；
- sha256；
- producer ticket；
- producer attempt；
- source surface；
- acceptance refs；
- evidence refs。

## FinalEvidenceTable

Final evidence table 必须覆盖 active acceptance contract 的所有 blocking criteria。

```yaml
acceptance_ref:
status: satisfied | failed | missing
verified_evidence_refs:
blockers:
```

任何 missing / failed blocking criterion 都阻断 closeout。

## Checker 与 Evidence 的关系

Checker 不能替 evidence verifier 放行。

```text
verified evidence incomplete -> checker REWORK_REQUIRED
verified evidence complete + non-blocking notes -> APPROVED_WITH_NON_BLOCKING_NOTES
verified evidence complete + no notes -> APPROVED
```

## Rework 与 Evidence 的关系

Rework（返工）不能由 runtime（运行时）或 atomic-agent（原子智能体）内部完成状态直接触发。返工请求必须由已验证阻塞项驱动：

- FinalEvidenceTable（最终证据表）存在 missing/failed blocking row（缺失/失败阻塞行）；
- CheckerVerdict（检查结论）存在 blocking issue（阻塞问题）；
- CloseoutGate（收尾门禁）发现 package/evidence/audit（包/证据/审计）不满足 active contract（活跃合同）。

ReworkRequest（返工请求）至少绑定：

```yaml
blocker_refs:
acceptance_refs:
source_surface_refs:
required_artifact_types:
failed_or_missing_evidence_refs:
```

CEO（项目经理/治理角色）或 Architect（架构师）生成 ReworkPlan（返工计划）时，必须把每个 ReworkTicket（返工工单）重新绑定到 active AcceptanceContract（验收合同）、PackageContract（包合同）、SourceSurface（源码面）和 EvidenceObligation（证据义务）。返工不能引入静态 acceptance refs（验收引用）、第二套 source surface mapping（源码面映射）或 dict-only（仅字典）证据链。

每次 ReworkAttempt（返工尝试）产物都必须重新经过：

1. EvidenceVerifier（证据验证器）；
2. SourceInventory（源码清单）或对应 source lineage（源码来源链）校验；
3. FinalEvidenceTableBuilder（最终证据表构建器）；
4. Checker（检查者）；
5. 必要时 CloseoutGate（收尾门禁）。

旧的 satisfied evidence row（已满足证据行）、Checker approved verdict（检查通过结论）或 CloseoutPackage passed（通过收尾包）不得跨返工轮次复用为新轮次通过证据。

## Closeout Gate

Closeout 必须检查：

1. ticket graph 无 open blocker；
2. source inventory valid；
3. final evidence table complete；
4. package contract satisfied；
5. declared commands passed；
6. provider attempts recorded；
7. git audit clean；
8. replay bundle ready；
9. process audit generated。

Closeout 失败不应是首次发现 implementation 缺口；缺口应在 checker/rework 阶段处理。
