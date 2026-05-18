# V2-040C WorkProduct（工作产物）设计

## 背景

V2-040C 位于 Phase 4 Runtime + Provider + Runner（运行时、模型调用与命令证据）阶段。V2-040A 已定义 ProviderAttempt（模型调用尝试记录），V2-040B 已证明 ProviderExecutor（模型供应商执行器）只能通过 ExecutionPackage（执行包）调用 provider（模型供应商）并返回可审计 attempt fact（尝试事实）。本工作包补齐下一段链路：把 provider raw output（模型原始输出）解析为 WorkProduct（工作产物），并提交 `WORK_PRODUCT_SUBMITTED`（工作产物已提交）事实事件。

现实类比：这一步不是验收交付，也不是宣布任务完成，而是把模型产出的内容登记成一张可追溯的“交货单”。这张交货单说明它来自哪个执行包、哪个 ticket（任务）、哪个 provider attempt（模型调用尝试记录）、包含哪些 artifact refs（产物引用）和 claim drafts（证据声明草稿）。后续 EvidenceVerifier（证据验证器）、Checker（检查者）和 reducer（状态归约器）会再判断它是否足够、真实、可用于完成任务。

## 范围

本工作包新增：

- `src/boardroom_os/execution/work_product.py`
- `tests/execution/test_work_product_submission.py`

本工作包可扩展或消费既有：

- `src/boardroom_os/providers/attempt.py`
- `src/boardroom_os/providers/adapter.py`
- `src/boardroom_os/execution/provider_executor.py`
- `src/boardroom_os/events/record.py`
- `src/boardroom_os/events/types.py`
- `src/boardroom_os/reducers/ticket_reducer.py`

本工作包不实现：

- EvidenceClaim（证据声明）的最终模型；
- EvidenceVerifier（证据验证器）；
- VerifiedEvidenceTable（已验证证据表）；
- CommandRunner（命令执行器）或 VerificationRun（验证运行）；
- RuntimeExecutor（运行时执行器）的完整编排；
- `TICKET_COMPLETED`（任务完成）或任何治理结论。

## 设计目标

1. WorkProduct（工作产物）必须绑定 producer attempt（生产者尝试），不能出现 provider zero-attempt（零模型尝试）的工作产物。
2. WorkProduct（工作产物）必须携带 artifact refs（产物引用）和 claim refs（声明引用），否则不得用于后续 evidence（证据）链路。
3. WorkProductClaimDraft（工作产物证据声明草稿）可以表达 producer 对 artifact（产物）的声明意图，但不能替代 EvidenceClaim（证据声明）或 verified evidence（已验证证据）。
4. 从 provider attempt（模型调用尝试记录）到 WorkProduct（工作产物）的解析必须 fail closed（失败关闭）：失败 attempt、缺 parsed output、错绑 execution package、错绑 ticket 或 fallback marker（降级标记）不一致时不能静默通过。
5. 事件工厂只能生成 `WORK_PRODUCT_SUBMITTED`（工作产物已提交）事实事件，不得生成 completion（完成）或 closeout（收尾）事件。

## Typed models（类型化模型）

### WorkProductRef（工作产物引用）

`WorkProductRef` 是非空值对象，用于 event payload ref（事件载荷引用）、audit（审计）和后续 evidence/checker 链路引用 WorkProduct（工作产物）。

### WorkProductArtifactRef（工作产物产物引用）

`WorkProductArtifactRef` 表达 WorkProduct（工作产物）包含的产物引用。它可以由 ProviderAttempt.raw_output_ref（模型原始输出引用）与 ProviderAttempt.parsed_output_ref（模型解析输出引用）派生，也可以在未来由 tool attempt（工具尝试）或 workspace artifact（工作区产物）派生。

V2-040C 不读取文件系统、不计算 artifact hash（产物哈希）。hash validation（哈希校验）属于 V2-050 EvidenceVerifier（证据验证器）与 V2-060 SourceInventory（源码清单）。

### WorkProductClaimDraftRef（工作产物证据声明草稿引用）

`WorkProductClaimDraftRef` 是 WorkProductClaimDraft（工作产物证据声明草稿）的引用。WorkProduct（工作产物）必须至少携带一个 claim draft ref（声明草稿引用），但 claim draft 仍只是草稿，不是 verified evidence（已验证证据）。

### WorkProductClaimDraft（工作产物证据声明草稿）

最小字段：

- `claim_draft_ref`
- `producer_attempt_ref`
- `execution_package_ref`
- `ticket_ref`
- `acceptance_refs`
- `source_surface_refs`
- `artifact_refs`
- `summary`

校验规则：

- `producer_attempt_ref` 必须非空；
- `execution_package_ref` 必须非空；
- `ticket_ref` 必须非空；
- `acceptance_refs` 必须非空；
- `source_surface_refs` 必须非空；
- `artifact_refs` 必须非空；
- `summary` 必须非空；
- unknown extra fields（未知额外字段）必须 fail closed（失败关闭）。

边界声明：WorkProductClaimDraft（工作产物证据声明草稿）只说明“producer 声称这些产物可能支撑这些 acceptance refs（验收引用）和 source surfaces（源码实现面）”。它不检查 artifact existence（产物存在性）、hash（哈希）、command evidence（命令证据）、fallback eligibility（降级证据资格）或 active contract membership（活跃合同归属）。这些由 V2-050 完成。

### WorkProduct（工作产物）

最小字段：

- `work_product_id`
- `execution_package_ref`
- `ticket_ref`
- `producer_attempt_ref`
- `artifact_refs`
- `claim_refs`
- `summary`
- `fallback_kind`（可选）

校验规则：

- `execution_package_ref` 必须非空；
- `ticket_ref` 必须非空；
- `producer_attempt_ref` 必须非空；
- `artifact_refs` 必须非空；
- `claim_refs` 必须非空；
- `summary` 必须非空；
- `fallback_kind` 只能在 producer attempt outcome（生产者尝试结果）为 `FALLBACK_ARTIFACT`（降级产物）时出现；
- unknown extra fields（未知额外字段）必须 fail closed（失败关闭）。

## Provider output parsing（模型输出解析）

新增纯函数 `build_work_product_from_provider_attempt`（从模型尝试构建工作产物）。输入建议为：

- `execution_package: ExecutionPackage`
- `provider_attempt: ProviderAttempt`
- `summary: str | None = None`

输出建议为 `WorkProductSubmission`（工作产物提交包），包含：

- `work_product`
- `claim_drafts`

解析规则：

1. `provider_attempt.status` 必须为 `SUCCEEDED`（成功），失败 attempt 只能作为 provider fact（模型调用事实）记录，不能生成 WorkProduct（工作产物）。
2. `provider_attempt.input_package_ref` 必须等于 `execution_package.execution_package_id` 派生出的 ExecutionPackageRef（执行包引用）。
3. `provider_attempt.seat_ref` 必须等于 `execution_package.seat_ref`。
4. `provider_attempt.raw_output_ref` 和 `provider_attempt.parsed_output_ref` 必须存在。
5. WorkProduct.artifact_refs（工作产物产物引用）至少包含 parsed output ref（解析输出引用）；raw output ref（原始输出引用）也应纳入 artifact refs（产物引用），以保留 audit lineage（审计来源链）。
6. WorkProductClaimDraft（工作产物证据声明草稿）的 acceptance_refs（验收引用）来自 ExecutionPackage.acceptance_refs（执行包验收引用）。
7. WorkProductClaimDraft（工作产物证据声明草稿）的 source_surface_refs（源码实现面引用）来自 ExecutionPackage.source_surface_refs（执行包源码实现面引用）。
8. 每个 WorkProduct（工作产物）至少生成一个 claim draft（证据声明草稿），并把其 ref 写入 WorkProduct.claim_refs（工作产物声明引用）。
9. 若 provider_attempt.outcome 为 `FALLBACK_ARTIFACT`（降级产物），WorkProduct.fallback_kind（工作产物降级类型）必须等于 provider_attempt.fallback_kind；若 provider_attempt.outcome 为 `PRIMARY_PROVIDER_OUTPUT`（主模型输出），WorkProduct 不得携带 fallback_kind。

`WorkProductSubmission` 不是 event（事件），也不是 evidence（证据）。它只是运行时内部用于“产物事实 + 声明草稿”一起传递的 typed bundle（类型化包）。

## Event factory（事件工厂）

新增函数 `build_work_product_submitted_event`（构建工作产物已提交事件）。输入建议为：

- `work_product: WorkProduct`
- `project_ref: ProjectRef`
- `actor_ref: ActorRef`
- `graph_version: int`
- `timestamp: datetime`
- `event_id: EventId | None = None`
- `causation_refs: tuple[EventRef, ...] = ()`
- `correlation_refs: tuple[EventRef, ...] = ()`

输出：

- `EventRecord`，`event_type` 固定为 `EventType.WORK_PRODUCT_SUBMITTED`（工作产物已提交）。

事件规则：

- payload_refs（事件载荷引用）只包含 WorkProductRef（工作产物引用）映射成 EventPayloadRef（事件载荷引用）；TicketReducer（任务状态归约器）不得把该 ref 当作 TicketId（任务 ID）直接消费，必须通过 `resolve_work_product_ticket_ref`（解析工作产物对应任务引用）从 WorkProduct（工作产物）载荷恢复 ticket_ref（任务引用）；
- `graph_version` 必须为正数；
- `timestamp` 必须带时区；
- actor_ref（参与者引用）可以是 runtime/executor actor（运行时/执行器参与者），因为提交工作产物事实是 runtime 允许动作；
- event factory 不接受 event_type 参数，避免调用方伪造 `TICKET_COMPLETED`（任务完成）或 `CLOSEOUT_COMMITTED`（收尾提交）。

V2-040C 不引入 payload repository（载荷仓库）或 event log append（事件日志追加）。V2-040E RuntimeExecutor（运行时执行器）会负责把 WorkProduct（工作产物）存入事实载荷存储并 append event（追加事件）。本轮只保证 event shape（事件形状）正确，并把 reducer 消费口径收窄到 WorkProductRef -> ticket_ref 的显式解析边界。

## Fail-closed rules（失败关闭规则）

构造期必须失败：

- WorkProduct（工作产物）缺 `producer_attempt_ref`；
- WorkProduct（工作产物）缺 `artifact_refs`；
- WorkProduct（工作产物）缺 `claim_refs`；
- WorkProduct（工作产物）缺 `execution_package_ref`；
- WorkProduct（工作产物）缺 `ticket_ref`；
- WorkProductClaimDraft（工作产物证据声明草稿）缺 `acceptance_refs`；
- WorkProductClaimDraft（工作产物证据声明草稿）缺 `source_surface_refs`；
- 任一模型携带 unknown extra fields（未知额外字段）。

解析期必须失败：

- provider attempt（模型调用尝试记录）状态为 failed（失败）；
- provider attempt（模型调用尝试记录）缺 raw_output_ref（原始输出引用）；
- provider attempt（模型调用尝试记录）缺 parsed_output_ref（解析输出引用）；
- provider attempt（模型调用尝试记录）错绑 execution_package_ref（执行包引用）；
- provider attempt（模型调用尝试记录）错绑 seat_ref（席位引用）；
- fallback outcome（降级结果）缺 fallback_kind（降级类型）；
- primary outcome（主模型输出）生成的 WorkProduct（工作产物）携带 fallback_kind（降级类型）。

事件期必须失败：

- graph_version 非正数；
- timestamp 无时区；
- 调用方试图传入非 `WORK_PRODUCT_SUBMITTED`（工作产物已提交）的 event_type；
- WorkProduct（工作产物）无有效 ref，导致 payload_refs（事件载荷引用）无法生成。

## Testing strategy（测试策略）

先写 negative tests（负例测试）到 `tests/execution/test_work_product_submission.py`：

- `test_work_product_requires_producer_attempt_ref`
- `test_work_product_requires_artifact_refs`
- `test_work_product_requires_claim_refs`
- `test_claim_draft_requires_acceptance_refs`
- `test_claim_draft_requires_source_surface_refs`
- `test_failed_provider_attempt_cannot_build_work_product`
- `test_provider_attempt_package_mismatch_is_rejected`
- `test_provider_attempt_seat_mismatch_is_rejected`
- `test_work_product_event_factory_cannot_emit_completion_event`
- `test_work_product_claim_draft_is_not_verified_evidence`

再写 happy path（正向路径）到同一测试文件：

- fake provider transport（模拟模型传输）返回 succeeded ProviderAttempt（成功模型调用尝试记录）；
- `build_work_product_from_provider_attempt` 生成 WorkProduct（工作产物）；
- WorkProduct（工作产物）绑定 ExecutionPackageRef（执行包引用）、TicketId（任务 ID）、ProviderAttemptRef（模型调用尝试引用）、raw/parsed artifact refs（原始/解析产物引用）和 claim draft refs（声明草稿引用）；
- WorkProductClaimDraft（工作产物证据声明草稿）继承 ExecutionPackage（执行包）的 acceptance_refs（验收引用）和 source_surface_refs（源码实现面引用）；
- `build_work_product_submitted_event` 生成 `WORK_PRODUCT_SUBMITTED`（工作产物已提交）事件；
- 将该事件与 TicketReducer（任务状态归约器）现有 completion gate（完成门禁）组合时，使用真实 `TicketReducer.reduce`（任务归约器归约函数）证明 WorkProductRef payload（工作产物引用载荷）会登记“已提交工作产物”，但不会单独完成 ticket（任务）；只有追加独立 `TICKET_COMPLETED`（任务完成）事件且 completion snapshot（完成快照）满足门禁后才会完成。

## 与验收标准的绑定

本设计覆盖 V2-040C 的工作包验收口径：runtime（运行时）只提交 work product fact（工作产物事实），不完成 ticket（任务）。

完成后按 backlog（工作包清单）更新：

- `doc/04-implementation/backlog.md`：V2-040C 状态改为 DONE，顶部当前未完成工作包指向 V2-040D，Phase 4 进度从 2/5 改为 3/5；
- `doc/05-project-log/2026-05.md`：追加 V2-040C 完成记录，包含输出文件、negative/happy tests（负例/正向测试）和验证命令；
- `doc/04-implementation/acceptance-criteria.md`：V2-040C 本身不勾选 Phase 4 抽象 AC；AC-V2-EVIDENCE-001（命令证据来自 runner）等到 V2-040D，Runtime bounded（运行时有界）等到 V2-040E。

## 非目标

- 不把 WorkProductClaimDraft（工作产物证据声明草稿）升级为 EvidenceClaim（证据声明）；
- 不验证 artifact hash（产物哈希）；
- 不读取 package root（包根目录）或写 source files（源码文件）；
- 不运行 command（命令）；
- 不让 fallback artifact（降级产物）满足 implementation evidence（实施证据）；
- 不追加 event log（事件日志）；
- 不产生 `TICKET_COMPLETED`（任务完成）、`PROJECT_COMPLETED`（项目完成）或 `CLOSEOUT_COMMITTED`（收尾提交）。

## 同行评审重点

请重点审查以下问题：

1. WorkProductClaimDraft（工作产物证据声明草稿）是否已经足够帮助 V2-050A 落地 EvidenceClaim（证据声明），同时没有越界成 verified evidence（已验证证据）。
2. `build_work_product_from_provider_attempt`（从模型尝试构建工作产物）是否应该把 raw output ref（原始输出引用）和 parsed output ref（解析输出引用）都纳入 artifact_refs（产物引用）。
3. event factory（事件工厂）只生成 `WORK_PRODUCT_SUBMITTED`（工作产物已提交）是否足以支撑 V2-040E RuntimeExecutor（运行时执行器）。
4. fallback marker（降级标记）是否应只从 ProviderAttempt（模型调用尝试记录）继承，还是需要 WorkProduct（工作产物）再持有独立 marker；本设计选择继承并冗余记录，便于 V2-050A1/FallbackPolicyRegistry（降级策略注册表）校验一致性。
