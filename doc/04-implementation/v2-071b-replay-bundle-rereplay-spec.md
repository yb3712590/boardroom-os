# V2-071B ReplayBundle re-replay（从 events 重新投影）同行评审 spec

## 1. 背景与现实场景

外部独立审计报告 P0-2 指出：`ReplayBundleBuilderInput` 接受调用方传入的 `projection_summary: ProjectionReplaySummary`，builder 内部只校验 `project_ref`、`projection_kind`、`event_count`、`graph_version` 边界等"骨架"字段的一致性，**不**从 `events` 重新调用 `ProjectionReplay.replay_events(...)` 计算 `summary_hash`。

实际代码（`src/boardroom_os/audit/replay_bundle.py` line 737）：

```python
summary_hash=ReplaySummaryHash(value=builder_input.projection_summary.summary_hash),
```

由于 `ProjectionReplaySummary.summary_hash` 是 `@computed_field`，对外暴露的 hash 篡改攻击会被 Pydantic 自动重算挡住；但调用方完全可以传入：

- 与真实 events 一致的边界字段（first/last graph_version、event_id、event_count），
- 与真实 events **不一致** 的内容字段（`nodes`、`blocked_by`、`seat_assignments`、`completed_nodes`、`seat_blockers` 等），

让 builder 用伪造的 projection 字段重新计算 hash 后写入 `ReplayReport.summary_hash` 与 `ReplayAttestation.summary_hash`。结果：ReplayBundle 看似哈希闭合，实际证明的"是事件得到的投影"是伪事实。

P2-2 进一步指出 `ReplayPayloadManifest._validate_entries` 与 `ReplayArtifactManifest._validate_entries` 只校验非空与唯一，不做 canonical sort，因此 `payload_manifest_hash` / `artifact_manifest_hash` / `replay_bundle_id` 在乱序输入下不稳定。

V2-071B 的目标是把 ReplayBundle 改造为 events 的纯派生：删除 `projection_summary` 输入，builder 内部重新投影，并对 manifest entries 实施 canonical sort。

Pre-flight：`backlog.md` 当前未完成工作包为 V2-071B（V2-071A 已完成）；`src/boardroom_os/audit/replay_bundle.py` line 590-676 `ReplayBundleBuilderInput` 仍接受 `projection_summary`；`src/boardroom_os/contracts/refs.py` 由 V2-071A 提供 `canonical_sort_for_hash`。

## 2. 范围与边界

### 2.1 In Scope

- 修改 `src/boardroom_os/audit/replay_bundle.py`：
  - 删除 `ReplayBundleBuilderInput.projection_summary` 字段。
  - 增加 `seat_assignment_projector: SeatAssignmentProjector` 输入字段（typed 注入）。
  - builder 内部调用 `ProjectionReplay.replay_events(events=...)` 重新投影，由其结果生成 `ReplayReport.summary_hash` 与 `ReplayAttestation.summary_hash`。
  - `ReplayPayloadManifest._validate_entries` 与 `ReplayArtifactManifest._validate_entries` 改用 `canonical_sort_for_hash`，并把排序后的 tuple 作为 `entries` 字段值。
  - `replay_bundle_id` 改用 V2-071A `namespaced_ref(...)`，包含 `project_ref` + `summary_hash[:12]` + 可选 `run_id`。
- 新增 `tests/closeout/test_replay_bundle_rereplay.py`、`tests/negative/test_replay_bundle_external_summary_rejected.py`。
- 调整既有 `tests/closeout/test_replay_bundle.py` fixture：删除显式 `projection_summary` 构造，改为提供 events + projector。

### 2.2 Out of Scope

- 不修改 `src/boardroom_os/graph/replay.py`：`ProjectionReplay.replay_events(...)` 与 `ProjectionReplaySummary` 已有的契约保持不变。
- 不修改 ProcessAudit 对 `replay_bundle.events` 的依赖（由 V2-071C 处理）。
- 不实现 `ReplayPayloadResolver`（payload 内容校验）—— 由 V2-071E 处理。

### 2.3 兼容性策略

按 hard rule **no backwards-compat shim**：删除 `projection_summary` 字段后，调用方若仍传入此字段必须 fail closed（Pydantic `extra="forbid"` 自动拒绝）。既有测试 fixture 必须迁移；本工作包负责完成迁移。

## 3. 模块设计

### 3.1 ReplayBundleBuilderInput 新形态

```python
class ReplayBundleBuilderInput(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    project_ref: ProjectRef
    events: tuple[EventRecord, ...]
    # projection_summary: 已删除
    seat_assignment_projector: SkipValidation[SeatAssignmentProjector]  # 新增
    projection_version: ProjectionVersionRef
    payload_manifest_ref: ReplayManifestRef
    payload_manifest_entries: tuple[ReplayManifestEntry, ...]
    event_window_ref: ReplayManifestRef
    artifact_manifest_ref: ReplayManifestRef
    artifact_manifest_entries: tuple[ReplayArtifactManifestEntry, ...]
    hash_manifest_ref: ReplayManifestRef
    replay_report_ref: ReplayReportRef
    generated_at: datetime
    run_id: str | None = None  # 新增（可选），传入 V2-071A namespaced_ref
```

校验：

- `_validate_input` 中**删除**所有 `summary.* != ...` 比较；改为：
  1. 校验 events 严格按 graph_version 递增、project_ref 一致；
  2. 调用 `ProjectionReplay(projection_kind=SEAT_ASSIGNMENT_GRAPH).replay_events(events=..., project_ref=..., expected_graph_version=events[-1].graph_version, projector=seat_assignment_projector)` 得到 `summary`；
  3. 用 `summary.summary_hash` 作为唯一 hash 来源。

### 3.2 build_replay_bundle 新流程

```python
def build_replay_bundle(builder_input: ReplayBundleBuilderInput) -> ReplayBundle:
    builder_input = _validate_builder_input_instance(builder_input)
    # 1. Re-replay 从 events 计算真实 summary
    summary = ProjectionReplay(
        projection_kind=ReplayAttestationKind.SEAT_ASSIGNMENT_GRAPH.value
    ).replay_events(
        events=builder_input.events,
        project_ref=builder_input.project_ref,
        expected_graph_version=builder_input.events[-1].graph_version,
        projector=builder_input.seat_assignment_projector,
    )
    # 2. payload_manifest / artifact_manifest entries 经 canonical_sort_for_hash
    sorted_payload_entries = canonical_sort_for_hash(
        builder_input.payload_manifest_entries,
        key=lambda entry: entry.content_ref.value,
    )
    sorted_artifact_entries = canonical_sort_for_hash(
        builder_input.artifact_manifest_entries,
        key=lambda entry: entry.kind.value,
    )
    # 3. 余下流程保持现状（event_hash_chain、artifact manifest hashes 等）
    ...
    # 4. replay_bundle_id 改用 namespaced_ref
    replay_bundle_id = ReplayBundleRef(
        value=namespaced_ref(
            kind="replay-bundle",
            project_ref=builder_input.project_ref.value,
            content_hash=summary.summary_hash,
            run_id=builder_input.run_id,
        )
    )
```

### 3.3 ReplayPayloadManifest / ReplayArtifactManifest 校验调整

```python
class ReplayPayloadManifest(BaseModel):
    ...
    @field_validator("entries")
    @classmethod
    def _validate_entries(
        cls, values: tuple[ReplayManifestEntry, ...]
    ) -> tuple[ReplayManifestEntry, ...]:
        if not values:
            raise ReplayBundleError("payload manifest entries must not be empty")
        # canonical_sort_for_hash 同时拒绝重复 key
        return canonical_sort_for_hash(values, key=lambda entry: entry.content_ref.value)
```

同样改造 `ReplayArtifactManifest._validate_entries`，以 `entry.kind.value` 为 key（kind 在 v1 必须唯一）。

## 4. Validation 规则

1. `ReplayBundleBuilderInput` 在 `extra="forbid"` 下自动拒绝 `projection_summary=...`。
2. `_validate_input` 在 events 为空时 raise；events project_ref 不一致时 raise。
3. `ProjectionReplay.replay_events` 在事件 graph_version 非连续时 raise（既有行为）。
4. `canonical_sort_for_hash` 在 entries 含重复 `content_ref` 时 raise。
5. `replay_bundle_id` 使用 `namespaced_ref` 内部校验 namespace segment 形态。

## 5. 测试计划

### 5.1 Negative tests（必须先写）

`tests/negative/test_replay_bundle_external_summary_rejected.py`：

1. `test_builder_input_rejects_projection_summary_field` — 传入 `projection_summary=fake_summary` 必须 raise `ValidationError`（`extra="forbid"`）。
2. `test_builder_input_rejects_extra_summary_hash` — 传入 `summary_hash="abc..."` 直接的尝试同样 raise。
3. `test_tampered_events_produce_different_summary_hash` — 修改 events 中任一 event 的 payload_refs，重新构造 bundle，得到的 `replay_bundle.replay_report.summary_hash` 与原 bundle 不同；不可能通过任何 builder 输入路径让伪造 events 与真实 summary_hash 共存。
4. `test_payload_manifest_rejects_duplicate_content_ref` — 两个 entry 含相同 `content_ref` 必须 raise（canonical_sort_for_hash 检测）。
5. `test_artifact_manifest_rejects_duplicate_kind` — 两个 entry 含相同 `kind` 必须 raise。

`tests/closeout/test_replay_bundle_rereplay.py` 中的 negative case：

6. `test_re_replay_fails_when_events_violate_graph_version_contiguity` — events graph_version 不连续时 `ProjectionReplay.replay_events` raise，build_replay_bundle 必须传播错误。
7. `test_payload_manifest_entries_order_invariance` — 同一组 entries 两种乱序输入产生相同 `payload_manifest_hash`。
8. `test_artifact_manifest_entries_order_invariance` — 同上对 artifact_manifest_hash。
9. `test_replay_bundle_id_includes_namespaced_segments` — bundle_id 字符串包含 `project_ref` 段与 `summary_hash[:12]` 段。

### 5.2 Happy path

`tests/closeout/test_replay_bundle_rereplay.py`：

1. `test_re_replay_yields_stable_summary_hash` — 给定相同 events 与 projector，重复构造 bundle 得到相同 `summary_hash`。
2. `test_re_replay_matches_independent_projection_replay_call` — 独立调用 `ProjectionReplay.replay_events` 得到的 `summary_hash` 与 bundle 内 `summary_hash` 相等（证明 builder 是纯派生）。
3. `test_build_replay_bundle_with_run_id_produces_unique_bundle_id` — 提供 `run_id="run-001"` 与 `run_id="run-002"` 得到不同 `replay_bundle_id`。
4. `test_existing_replay_bundle_negative_tests_still_pass` — 既有 `tests/closeout/test_replay_bundle.py` 中的 negative tests 迁移到新 fixture 后仍通过。

## 6. 验证命令

```powershell
$env:PYTHONPATH = "src;."
python -m pytest tests/closeout/test_replay_bundle_rereplay.py tests/negative/test_replay_bundle_external_summary_rejected.py -q --basetemp=.pytest-tmp-v2071b
python -m pytest tests/closeout/test_replay_bundle.py tests/closeout/test_replay_bundle_rereplay.py -q --basetemp=.pytest-tmp-v2071b-regression
python -m pytest tests/contracts tests/reducers tests/closeout tests/negative -q --basetemp=.pytest-tmp-v2071b-full
```

成功标准：

- 新增测试全部通过。
- 既有 `tests/closeout/test_replay_bundle.py`（在 fixture 迁移后）全部通过。
- V2-070C ProcessAudit 测试**会失败**（因为 ProcessAudit 仍直接消费 `builder_input.projection_summary` 经过 ReplayBundle 暴露的字段）—— 这是预期的，由 V2-071C 修复。本工作包 commit 时需在 PR 描述中明确这一点，或临时 skip 受影响测试并在 V2-071C 解 skip。

## 7. 文档同步

完成本工作包后：

1. `backlog.md`：V2-071B 状态 DONE；TL;DR → V2-071C；Phase 7.5 进度 2/6。
2. `acceptance-criteria.md`：勾选 Phase 7.5 中 AC-V2-CLOSEOUT-004（事实链单一权威源——ReplayBundle 部分）、AC-V2-CLOSEOUT-010（确定性哈希——payload/artifact manifest 部分）。
3. `INDEX.md`：本 spec 已登记。
4. `2026-05.md`：追加 V2-071B 完成记录。
5. `decisions.md`：不新增 DEC。

## 8. 完成判定

V2-071B 完成时：

1. `ReplayBundleBuilderInput` 不再有 `projection_summary` 字段。
2. `build_replay_bundle` 内部调用 `ProjectionReplay.replay_events(...)` 重新计算 `summary_hash`。
3. payload/artifact manifest entries canonical sort 生效。
4. `replay_bundle_id` 使用 `namespaced_ref`。
5. 第 5 节测试全部通过。
6. ProcessAudit 测试失败已记录，由 V2-071C 承接。
