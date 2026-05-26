# V2-071C ProcessAudit fact-chain hardening（同行评审 spec）

## 1. 背景与现实场景

V2-071C 处理的是项目收尾前的真实审计场景：系统已经有 `EventLog`（事件日志）、`ReplayBundle`（重放包）、`ProcessAudit`（流程审计）所需的合同、票据、证据和执行记录，但还没有生成 `CloseoutPackage`（收尾包），也还没有提交 `CLOSEOUT_COMMITTED`（收尾提交治理事件）。

审计产物必须能在最终签字前生成，用来回答：团队如何执行、哪些 ticket 被推进、哪些 evidence 被验证、哪些事件已经被 replay 证明。旧 V2-070C 实现把 `closeout_committed` 放进 ProcessAudit 必需时间线，导致“必须先完成收尾，才能生成收尾前审计”的构造环。

V2-071C 按 DEC-0017 的单一事实源原则修正这个问题：ProcessAudit 不再接收第二份外部 events（事件列表），而是直接复用 `ReplayBundle.events`；ProcessAudit 不再要求 `CLOSEOUT_COMMITTED` 已存在；同时清除 ProcessAudit 中的 placeholder fallback（占位降级）、artifact lineage（产物来源链）伪造和 checked_refs（已检查引用）输入顺序不稳定问题。

Pre-flight（一致性预检）：`backlog.md` 当前未完成工作包为 V2-071C；本 spec 在 V2-071C 输出文件清单中声明；本文件创建前不存在；V2-071C 相关 acceptance checkbox 仍未勾选，符合 TODO 状态；`doc/04-implementation/INDEX.md` 创建本文件后需要同步登记。

## 2. 范围与边界

### 2.1 In Scope

- 新建 `doc/04-implementation/v2-071c-process-audit-fact-chain-spec.md`（本文件）。
- 修改 `src/boardroom_os/audit/process_audit.py`：
  - 删除 `ProcessAuditBuilderInput.events` 外部输入。
  - ProcessAudit 只复用 `ReplayBundle.events`。
  - 删除 `closeout_committed` 必需时间线要求。
  - 确保 ProcessAudit 输出的 timeline（时间线）逐条由 `ReplayBundle.events` 派生，防止重新引入第二事件源。
  - 删除 ticket graph / agent context / artifact lineage 中的隐式 placeholder fallback。
  - 对集合语义输入进行 canonical sort（规范排序），稳定 `checked_refs`。
- 修改 `src/boardroom_os/workspace/source_inventory.py`：
  - 新增 consumer ticket（消费票据）字段，以区分 producer ticket（生产票据）与 consumer ticket（消费票据）。
- 新增测试：
  - `tests/closeout/test_process_audit_fact_chain.py`
  - `tests/negative/test_process_audit_construction_loop_rejected.py`
- 同步调整既有 ProcessAudit 测试 fixture：
  - `tests/closeout/test_process_audit.py`
  - `tests/closeout/test_process_audit_artifacts.py`
- 同步 `doc/04-implementation/INDEX.md`。

### 2.2 Out of Scope

- 不修改 Git facts（Git 事实）fallback；该问题属于 V2-071D。
- 不修改 CloseoutPackage（收尾包）引用命名空间和 payload binding；该问题属于 V2-071E。
- 不修改 ReplayBundle（重放包）re-replay 逻辑；该问题已由 V2-071B 负责。
- 不引入 runtime（运行时）治理决策；runtime 仍只执行、记录、校验和投影事实。
- 不读取、迁移或复制 legacy runtime（旧运行时）实现。

### 2.3 兼容性策略

本工作包会改变 `ProcessAuditBuilderInput`（流程审计构造输入）和 `SourceInventory`（源码清单）的模型契约。兼容性目标不是保持旧调用方式可用，而是 fail closed（失败关闭）地拒绝第二事实源和缺失来源链字段。

既有测试 fixture 必须随新契约显式提供 consumer ticket refs（消费票据引用）和完整 ticket graph / agent context 字段，不能通过默认值或伪造字段绕过。

## 3. 目标契约

### 3.1 构造顺序契约

V2-071C 后，流程必须满足以下顺序：

```text
EventLog（事件日志）
   ↓
ReplayBundle（重放包：从 events 重新投影）
   ↓
ProcessAuditBundle（流程审计包：复用 replay_bundle.events，不要求 closeout_committed）
   ↓
GitVersionAuditBundle（Git 版本审计包）
   ↓
CloseoutGate（收尾门禁）
   ↓
CloseoutPackage（收尾包）
   ↓
CLOSEOUT_COMMITTED event（收尾提交治理事件）
   ↓
CloseoutReducer / CloseoutProjection（收尾归约器 / 收尾投影）
```

关键约束：

1. ProcessAudit 不得要求事件流中存在 `CLOSEOUT_COMMITTED`。
2. ProcessAudit 不得引用尚未构造的 CloseoutPackage。
3. ProcessAudit 不得接收外部传入的第二份 `events`。
4. ProcessAudit 输出 timeline 的每条事件必须由 ReplayBundle events 派生，不能来自外部第二事件源。

### 3.2 ProcessAuditBuilderInput 契约

`ProcessAuditBuilderInput` 必须删除独立 `events` 字段：

```python
class ProcessAuditBuilderInput(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    project_ref: ProjectRef
    generated_at: datetime
    package_contract: SkipValidation[PackageContract]
    acceptance_contract: SkipValidation[AcceptanceContract]
    agent_context_index: BaseModel
    ticket_graph_summary: BaseModel
    source_inventory: SkipValidation[SourceInventory]
    workspace_evidence_bundle: SkipValidation[WorkspaceEvidenceBundle]
    final_evidence_table: SkipValidation[FinalEvidenceTable]
    checker_verdict: SkipValidation[CheckerVerdict]
    verification_runs: tuple[SkipValidation[VerificationRun], ...]
    verified_evidence: tuple[SkipValidation[VerifiedEvidence], ...]
    provider_attempt_refs: tuple[ProviderAttemptRef, ...]
    replay_bundle: SkipValidation[ReplayBundle]
    replay_readiness: SkipValidation[ReplayBundleReadiness]
    git_version_audit_bundle: SkipValidation[GitVersionAuditBundle]
    git_audit_readiness: SkipValidation[GitAuditReadiness]
```

所有 ProcessAudit 内部事件读取统一通过 helper：

```python
def _audit_events(builder_input: ProcessAuditBuilderInput) -> tuple[EventRecord, ...]:
    return builder_input.replay_bundle.events
```

### 3.3 Timeline required kinds 契约

`_REQUIRED_TIMELINE_EVENT_KINDS` 必须删除 `closeout_committed`：

```python
_REQUIRED_TIMELINE_EVENT_KINDS = {
    "seat_assigned",
    "ticket_created",
    "ticket_started",
    "provider_attempt_recorded",
    "work_product_submitted",
    "command_run_recorded",
}
```

允许 event stream（事件流）在 ProcessAudit 阶段尚未包含 closeout 事件；如果包含 `CLOSEOUT_COMMITTED`，它也不得作为 ProcessAudit 构造成功的必要条件。

## 4. Event equality（事件一致性）设计

### 4.1 单一事实源

ProcessAudit 的事件事实源为：

```text
builder_input.replay_bundle.events
```

禁止以下模式：

```text
ProcessAuditBuilderInput.events
ProcessAudit builder caller supplied events
任何由 ProcessAudit 自行重放或重新查询得到的 events
```

### 4.2 校验规则

`_validate_event_timeline_closure(...)` 应改为对 ReplayBundle events 本身做校验：

1. `events` 不得为空。
2. `graph_version` 必须严格递增。
3. 必需 timeline kind 除 `closeout_committed` 外必须覆盖。
4. 每个 ReplayBundle attestation（重放包证明声明）的 event window 必须被 events 覆盖。
5. event window 的每个 `graph_version` 必须存在对应事件。
6. window 中首尾 event id 必须匹配。
7. ProcessAudit 输出 timeline 中的每条事件必须来自 ReplayBundle events；不得从调用方输入、重新查询或重新投影获得第二事件源。

### 4.3 失败信息

推荐错误信息保持可诊断但不泄漏复杂内部结构：

- `events must be strictly increasing by graph_version`
- `timeline missing real event kind: <kind>`
- `events must cover replay bundle event window`
- `events must match replay bundle event window`
- `process audit events must come from replay bundle`

## 5. Fail-closed 字段读取设计

### 5.1 TicketGraphSummary（票据图摘要）

ProcessAudit 读取 `ticket_graph_summary.tickets[*]` 时必须显式要求：

- `ticket_ref`
- `status`
- `owner_seat_ref`
- `acceptance_refs`

禁止以下 fallback：

```python
getattr(ticket, "ticket_ref", "ticket")
getattr(ticket, "status", "unknown")
getattr(ticket, "owner_seat_ref", "unknown")
```

建议新增 helper：

```python
def _required_attr(value: object, attr_name: str, *, context: str) -> object:
    if not hasattr(value, attr_name):
        raise ProcessAuditError(f"{context} missing {attr_name}")
    attr = getattr(value, attr_name)
    if attr is None:
        raise ProcessAuditError(f"{context} missing {attr_name}")
    return attr
```

并用它替换 ticket graph markdown（票据图 Markdown）和 `_ticket_refs(...)` 的宽松读取。

### 5.2 AgentContextIndex（智能体上下文索引）

ProcessAudit 必须继续从 `entry.snapshot.*` 读取字段：

- `entry.snapshot.execution_package_ref`
- `entry.snapshot.model_execution_profile`

禁止回退到 entry 顶层平铺字段。缺字段必须 raise `ProcessAuditError`。

### 5.3 Audit output（审计输出）占位值禁止

以下字符串不得因缺字段而出现在审计产物中：

- `"unknown"`
- `"ticket"`

如果这些字符串作为真实业务值出现，调用方必须显式提供并通过上游 value object / schema 校验；ProcessAudit 不得自行生成。

## 6. SourceInventory consumer lineage（源码清单消费来源链）设计

### 6.1 新字段

在 `SourceLineageRecord` 和 `SourceInventoryEntry` 中新增：

```python
consumer_ticket_refs: tuple[TicketId, ...]
```

选择复数字段的原因：一个源码文件可能由 ticket A 生产，又被 ticket B、ticket C 分别消费并形成后续 evidence（证据）或 closeout（收尾）依据；单数 `consumer_ticket_ref` 会过早收窄模型。

### 6.2 Validation 规则

- `consumer_ticket_refs` 必须是 tuple/list 输入。
- `consumer_ticket_refs` 不得为空。
- 每个元素必须规范化为 `TicketId`。
- `consumer_ticket_refs` 可以包含 producer ticket 本身，表示生产 ticket 也消费了该文件；但不得由 ProcessAudit 默认把 consumer 设置为 producer。
- 是否允许重复值：不允许。重复 consumer ticket refs 必须 fail closed。

### 6.3 Serialization（序列化）

`SourceInventoryEntry.model_dump()` 中 `consumer_ticket_refs` 应序列化为：

```json
[
  {"value": "ticket-a"},
  {"value": "ticket-b"}
]
```

ProcessAudit 的 `artifact-lineage.json` 中可输出为字符串数组，便于审计阅读：

```json
{
  "producer_ticket_ref": "ticket-a",
  "producer_attempt_ref": "provider-attempt-1",
  "consumer_ticket_refs": ["ticket-b"],
  "acceptance_refs": ["AC-1"],
  "evidence_refs": ["verified-evidence-1"]
}
```

## 7. Artifact lineage（产物来源链）设计

### 7.1 输出契约

`artifact-lineage.json` 的每个 artifact lineage item 必须包含：

- `path`
- `sha256`
- `source_surface_ref`
- `producer_ticket_ref`
- `producer_attempt_ref`
- `consumer_ticket_refs`
- `acceptance_refs`
- `evidence_refs`

其中：

- `producer_ticket_ref` 来自 `SourceInventoryEntry.producer_ticket_ref`。
- `producer_attempt_ref` 来自 `SourceInventoryEntry.producer_attempt_ref`。
- `consumer_ticket_refs` 来自 `SourceInventoryEntry.consumer_ticket_refs`。
- 不得把 `consumer_ticket_refs` 伪造为 producer。

### 7.2 Producer / consumer 分离证明

测试必须覆盖：

```text
ticket-a produces file-x
ticket-b consumes file-x to produce verified evidence
```

期望 `artifact-lineage.json`：

```json
{
  "producer_ticket_ref": "ticket-a",
  "consumer_ticket_refs": ["ticket-b"]
}
```

如果输出为：

```json
{
  "consumer_ticket_ref": "ticket-a"
}
```

或缺失 consumer 字段，测试必须失败。

## 8. Fallback lineage（降级来源链）排他校验

### 8.1 规则

设：

```python
expected_fallback_refs = set(bundle.process_audit_report.expected_fallback_decision_refs)
actual_fallback_refs = {
    lineage["fallback_decision_record_ref"]
    for lineage in artifact_lineage["fallback_lineages"]
}
```

必须满足：

```python
actual_fallback_refs == expected_fallback_refs
```

这意味着：

- expected 为空，actual 必须为空。
- expected 非空，actual 不得缺失。
- actual 不得多出 expected 之外的 fallback decision refs（降级判定引用）。
- `fallback_lineages` 中缺 `fallback_decision_record_ref` 必须失败。

### 8.2 错误信息

推荐统一错误：

```text
fallback lineage decision refs must match expected fallback decisions
```

## 9. checked_refs（已检查引用）确定性设计

### 9.1 序列语义与集合语义分离

ProcessAudit 的 `checked_refs` 由两类输入组成：

1. 序列语义输入：
   - events（事件）
   - event hash chain（事件哈希链，如存在）
   - 这些必须保持 graph_version 顺序，不得 sort。
2. 集合语义输入：
   - `provider_attempt_refs`
   - `verification_runs`
   - `verified_evidence`
   - `source_inventory.entries`
   - `agent_context_checked_refs`
   - `fallback_decision_record_ref`
   - 这些必须 canonical sort（规范排序）。

### 9.2 排序规则

使用 V2-071A 的 `canonical_sort_for_hash(...)`：

| 输入 | 排序 key |
|---|---|
| `provider_attempt_refs` | `ref.value` |
| `verification_runs` | `run.verification_run_id.value` |
| `verified_evidence` | `evidence.verified_evidence_id.value` |
| `source_inventory.entries` | `entry.path.value` |
| `agent_context_checked_refs` | identity (`str`) |
| `fallback_decision_record_ref` | `ref.value` |

最终仍可用稳定 de-dup（去重）保留首次出现顺序，但首次出现顺序必须由上述规则决定，而不是调用方输入顺序决定。

### 9.3 预期性质

同一组集合语义输入在不同排列下必须产生相同：

- `checked_refs`
- ProcessAudit report hash（如由 checked_refs 参与）
- ProcessAudit bundle hash（如由 report hash 参与）

## 10. 测试计划

### 10.1 Negative tests（必须先写）

`tests/negative/test_process_audit_construction_loop_rejected.py`：

1. `test_process_audit_builds_before_closeout_committed_event_exists`
   - 构造不含 `CLOSEOUT_COMMITTED` 的 replay bundle events。
   - ProcessAudit 必须成功构造。
   - 该测试是“旧实现会失败，新实现必须通过”的 construction loop regression。

2. `test_process_audit_rejects_external_events_field`
   - 向 `ProcessAuditBuilderInput` 传入 `events`。
   - 因 `extra="forbid"` 必须失败。

3. `test_process_audit_timeline_is_derived_from_replay_bundle_events`
   - 构造 replay bundle events 后生成 ProcessAudit。
   - timeline 中的 `event_id` / `event_type` / `graph_version` / `actor_ref` / `payload_refs` 必须与 ReplayBundle events 对应字段一致。
   - 测试不得通过外部 `events` 字段喂给 ProcessAudit。

4. `test_process_audit_rejects_replay_bundle_event_window_gap`
   - replay bundle attestation window 覆盖的 graph_version 在 events 中缺失时必须失败。

5. `test_process_audit_rejects_non_increasing_replay_bundle_events`
   - ReplayBundle events 的 `graph_version` 非严格递增时必须失败。

6. `test_process_audit_rejects_ticket_without_ticket_ref`
   - ticket graph summary 缺 `ticket_ref` 必须失败。

7. `test_process_audit_rejects_ticket_without_status`
   - ticket graph summary 缺 `status` 必须失败。

8. `test_process_audit_rejects_ticket_without_owner_seat_ref`
   - ticket graph summary 缺 `owner_seat_ref` 必须失败。

9. `test_process_audit_rejects_agent_context_without_snapshot_execution_package_ref`
   - agent context snapshot 缺 `execution_package_ref` 必须失败。

10. `test_process_audit_rejects_agent_context_without_snapshot_model_execution_profile`
    - agent context snapshot 缺 `model_execution_profile` 必须失败。

11. `test_artifact_lineage_rejects_missing_consumer_ticket_refs`
    - SourceInventory entry 缺 consumer ticket refs 必须失败。

12. `test_artifact_lineage_does_not_default_consumer_to_producer`
    - producer 为 ticket-a，consumer 为 ticket-b。
    - 输出不得把 consumer 写成 ticket-a。

13. `test_artifact_lineage_rejects_fallback_lineages_when_expected_empty`
    - expected fallback refs 为空但 artifact-lineage.json 含 fallback_lineages 必须失败。

14. `test_artifact_lineage_rejects_missing_expected_fallback_lineage`
    - expected 非空但 actual 缺失必须失败。

15. `test_checked_refs_stable_under_collection_input_reordering`
    - 乱序 `provider_attempt_refs` / `verification_runs` / `verified_evidence`。
    - `checked_refs` 必须相同。

### 10.2 Happy path tests

`tests/closeout/test_process_audit_fact_chain.py`：

1. `test_process_audit_uses_replay_bundle_events_before_closeout_package`
   - 构造 ReplayBundle 后立即构造 ProcessAudit。
   - 不需要 CloseoutPackage。
   - 不需要 `CLOSEOUT_COMMITTED`。

2. `test_process_audit_timeline_matches_replay_bundle_events_exactly`
   - ProcessAudit 输出 timeline 由 replay bundle events 派生。
   - event id / type / graph_version / actor / payload refs 与 ReplayBundle events 一致。

3. `test_artifact_lineage_separates_producer_and_consumer_tickets`
   - artifact-lineage.json 明确输出 producer 与 consumer。

4. `test_ticket_graph_markdown_uses_real_ticket_fields`
   - ticket graph markdown 使用真实 `ticket_ref` / `status` / `owner_seat_ref`。
   - 不包含 ProcessAudit 生成的 placeholder。

5. `test_agent_context_index_reads_snapshot_fields`
   - agent context index 使用 `entry.snapshot.execution_package_ref` 和 `entry.snapshot.model_execution_profile`。

6. `test_checked_refs_hash_stable_under_reordering`
   - 集合语义输入乱序，ProcessAudit report/bundle 的相关 hash 稳定。

### 10.3 Existing fixture updates

需要同步调整：

- `tests/closeout/test_process_audit.py`
- `tests/closeout/test_process_audit_artifacts.py`

调整点：

- 删除构造 `ProcessAuditBuilderInput(events=...)` 的调用。
- 所有 ProcessAudit event fixture 改为从 ReplayBundle fixture 提供。
- SourceInventory fixture 增加 `consumer_ticket_refs`。
- ticket graph summary fixture 显式提供 `ticket_ref` / `status` / `owner_seat_ref`。
- agent context fixture 显式使用 `snapshot.execution_package_ref` / `snapshot.model_execution_profile`。

## 11. 验证命令

```powershell
$env:PYTHONPATH = "src;."
python -m pytest tests/negative/test_process_audit_construction_loop_rejected.py tests/closeout/test_process_audit_fact_chain.py -q --basetemp=.pytest-tmp-v2071c
```

回归建议：

```powershell
python -m pytest tests/closeout/test_process_audit.py tests/closeout/test_process_audit_artifacts.py -q --basetemp=.pytest-tmp-v2071c-existing
python -m pytest tests/closeout tests/negative -q --basetemp=.pytest-tmp-v2071c-regression
```

成功标准：

1. 新增 negative tests 先失败于旧实现，并在实现后通过。
2. 新增 happy path tests 通过。
3. 既有 ProcessAudit 相关测试通过。
4. 不要求 V2-071D/E 尚未覆盖的 Git fallback / CloseoutPackage namespace 问题在本包闭合。

## 12. 文档同步

完成实现后必须按 backlog 工作包完成协议更新：

1. `doc/04-implementation/backlog.md`
   - V2-071C 状态改 DONE。
   - TL;DR 当前未完成工作包指向 V2-071D。
   - Phase 7.5 进度由 `2 / 6` 改为 `3 / 6`。
   - 总进度同步增加 1。
2. `doc/04-implementation/acceptance-criteria.md`
   - 勾选 V2-071C 对应 ProcessAudit 构造环、ReplayBundle.events 单一事实源、producer/consumer lineage、placeholder fallback、fallback 排他、checked_refs 稳定性相关 checkbox。
3. `doc/05-project-log/2026-05.md`
   - 追加 V2-071C 完成记录。
4. `doc/05-project-log/decisions.md`
   - 不新增 DEC，除非实现中改变 DEC-0017 的语义。
5. `doc/04-implementation/INDEX.md`
   - 本 spec 创建时已登记。

## 13. 完成判定

V2-071C 完成时必须满足：

1. `ProcessAuditBuilderInput.events` 已删除，外部传入 `events` 会被拒绝。
2. ProcessAudit 只从 `ReplayBundle.events` 派生 timeline 和 checked refs 中的 event refs。
3. ProcessAudit 可在无 `CLOSEOUT_COMMITTED` 的事件流上成功构造。
4. ProcessAudit 不再要求 CloseoutPackage 已存在。
5. event window 覆盖与事件事实一致性校验 fail closed。
6. ticket graph / agent context 缺字段直接失败，不生成 `"unknown"` / `"ticket"` fallback。
7. `SourceInventory` 显式保存 `consumer_ticket_refs`。
8. `artifact-lineage.json` 分离 producer 与 consumer，不再伪造 consumer。
9. fallback lineage actual set 与 expected set 完全一致。
10. `checked_refs` 对集合语义输入乱序稳定。
11. 新增和相关回归测试通过。
12. backlog、acceptance criteria、项目日志和 INDEX 按协议同步。
