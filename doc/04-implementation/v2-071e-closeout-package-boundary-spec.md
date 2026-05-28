# V2-071E CloseoutPackage boundary + payload binding（收尾包边界与载荷内容绑定）同行评审 spec

## 1. 背景与现实场景

V2-071E 处理的是最终 closeout（收尾）前的“结案袋防串包”场景：系统已经完成 ReplayBundle（重放包）、ProcessAuditBundle（流程审计包）、GitVersionAuditBundle（Git 版本审计包）、CloseoutGateResult（收尾门禁结果）和相关 readiness summaries（就绪摘要），但还必须证明这些材料都属于同一个 project（项目）、同一次 run（运行）、同一个内容 hash（内容哈希）和同一个 replay proof boundary（重放证明边界）。

通俗地说：ReplayBundle 像录像，ProcessAudit 像审计报告，GitVersionAudit 像版本封条，CloseoutPackage 像最终结案袋。结案袋不能只看“文件名都在”，还要确认录像实际证明到哪一帧、录像清单里的每个 payload hash 是否能用真实内容重算、审计报告里的 artifact/content ref 是否带项目与内容命名空间，以及同项目多次 closeout 不会互相串包。

外部审计报告中本工作包闭合三类缺口：

- P0-5：CloseoutPackage.graph_version（收尾包图版本）允许超过 ReplayBundle.last_graph_version（重放包最后图版本）。
- P1-1：ReplayPayloadManifest（重放载荷清单）只校验 ref 覆盖，不校验 sha256 与真实 payload 内容绑定。
- P1-5：fact_set_id / artifact_ref / content_ref 等持久引用命名空间不足。

Pre-flight（一致性预检）：`backlog.md` 当前未完成工作包为 V2-071E；V2-071B/C/D 已 DONE；本文件创建前不存在；`tests/closeout/test_closeout_package_boundary.py`、`tests/negative/test_closeout_package_graph_version_overflow_rejected.py`、`tests/negative/test_replay_payload_manifest_tampering_rejected.py` 创建前不存在；待改代码文件 `src/boardroom_os/closeout/package.py`、`src/boardroom_os/audit/replay_bundle.py`、`src/boardroom_os/audit/process_audit.py`、`src/boardroom_os/audit/git_version_audit.py` 均已存在；Phase 7.5 进度为 4/6，相关 checkbox 未勾选，未发现 drift（状态漂移）。

## 2. 范围与边界

### 2.1 In Scope

- 新建本 spec，并同步 `doc/04-implementation/INDEX.md`。
- 修改 `src/boardroom_os/audit/replay_bundle.py`：
  - 引入 `ReplayPayloadResolver`（重放载荷解析器）协议。
  - `replay_bundle_readiness(...)` 必须接收 resolver 并用真实 payload 内容重算每条 `ReplayPayloadManifest.entries[*].sha256`。
  - `ReplayBundleReadiness` 增加 payload sha256 已验证标记或等价 typed 字段；由于 resolver 必填，该字段必须为 true。
- 修改 `src/boardroom_os/closeout/package.py`：
  - `builder_input.graph_version` 必须严格等于 ReplayBundle proof boundary（重放证明边界）。
  - `CloseoutPackageRef` 使用 V2-071A `namespaced_ref(...)`。
  - builder 校验 replay/process/git/closeout ref 的 namespace binding（命名空间绑定）。
- 修改 `src/boardroom_os/audit/process_audit.py`：
  - `ProcessAuditArtifactRef` 与 `ProcessAuditContentRef` 的新生成值使用 `namespaced_ref(...)`，包含 project_ref、artifact/content hash、run_id 与 kind suffix。
  - `ProcessAuditBundleRef`、`ProcessAuditReportRef`、manifest ref 如本轮触及，按同一命名空间规则收紧。
  - 旧短格式 `process-audit-artifact.{kind}` / `process-audit-content.{kind}` 必须在 readiness 或 builder 校验中失败。
- 修改 `src/boardroom_os/audit/git_version_audit.py`：
  - `GitVersionAuditBundleRef` 等新生成引用使用 `namespaced_ref(...)` 或继续保持已由 V2-071D 收紧的 `fact_set_id` 语义，并补足跨包 binding 校验。
- 修改 `src/boardroom_os/contracts/refs.py`：
  - 增加 `assert_namespaced_ref_binding(...)`，用于验证 kind、project_ref、content_hash[:12]、run_id 和 extra_suffix 绑定关系。
- 新增测试：
  - `tests/closeout/test_closeout_package_boundary.py`
  - `tests/negative/test_closeout_package_graph_version_overflow_rejected.py`
  - `tests/negative/test_replay_payload_manifest_tampering_rejected.py`

### 2.2 Out of Scope

- 不修改 legacy runtime（旧运行时）或旧 backend 路径。
- 不重新设计 CloseoutGate（收尾门禁）的 pass/fail authority（通过/失败权威）。
- 不新增 CloseoutReducer（收尾归约器）或 CloseoutClosure（收尾闭包）端到端集成；V2-071F 负责端到端重锁。
- 不把 optional resolver（可选解析器）或半验证 readiness 作为兼容路径；本工作包按用户确认采用 resolver 必填策略。
- 不读取真实文件系统作为默认 resolver；测试和调用方必须显式提供 resolver，避免隐式外部状态。

### 2.3 兼容性策略

本工作包不保留 backwards-compat shim（向后兼容垫片）。缺 resolver、旧短格式 ref、graph_version 越界、payload 内容 hash 不匹配全部 fail closed（失败关闭）。既有测试 fixture 必须迁移到显式 resolver 和命名空间 ref。

## 3. 目标契约

### 3.1 构造顺序契约

V2-071E 不改变 V2-071A 固定的事实链顺序：

```text
EventLog（事件日志）
   ↓
ReplayBundle（重放包：从 events 重新投影）
   ↓
ReplayBundleReadiness（重放包就绪摘要：resolver 重算 payload sha256）
   ↓
ProcessAuditBundle（流程审计包：复用 replay_bundle.events）
   ↓
GitVersionAuditBundle（Git 版本审计包）
   ↓
CloseoutGate（收尾门禁：消费 readiness summaries）
   ↓
CloseoutPackage（收尾包：绑定同一 proof boundary）
   ↓
CLOSEOUT_COMMITTED event（收尾提交治理事件）
```

关键约束：

1. `CloseoutPackage.graph_version == ReplayBundle.last_graph_version`，不得小于或大于。
2. `ReplayBundleReadiness` 必须证明 payload manifest 的 sha256 与真实 payload 内容一致。
3. `CloseoutPackage` 只做绑定一致性校验，不重新判断 gate pass/fail。
4. 跨包持久引用必须可通过 namespace helper 证明 kind/project/content/run 绑定。

### 3.2 ReplayPayloadResolver 契约

新增协议：

```python
from typing import Protocol

class ReplayPayloadResolver(Protocol):
    def resolve_payload(self, content_ref: ReplayContentRef) -> bytes | str | Mapping[str, Any]: ...
```

解析结果规范化规则：

- 若返回 `bytes`，直接对 bytes 计算 SHA-256。
- 若返回 `str`，按 UTF-8 编码计算 SHA-256。
- 若返回 `Mapping` / `BaseModel` / list / tuple，使用 replay bundle 既有 canonical JSON 语义编码后计算 SHA-256。
- resolver 缺失、返回 `None`、无法 canonicalize、content_ref 缺失、sha256 不匹配，都 raise `ReplayBundleError`。

`replay_bundle_readiness(...)` 新签名：

```python
def replay_bundle_readiness(
    bundle: ReplayBundle,
    *,
    payload_resolver: ReplayPayloadResolver,
) -> ReplayBundleReadiness: ...
```

`payload_resolver` 必填；缺失即 raise `ReplayBundleError("payload resolver is required")`。不提供 `payload_sha256_verified=False` 的半验证模式。

### 3.3 ReplayBundleReadiness 契约

`ReplayBundleReadiness` 增加：

```yaml
payload_sha256_verified: true
payload_manifest_ref:
payload_manifest_hash:
```

字段语义：

- `payload_sha256_verified` 固定为 true；只有 resolver 校验全部 entry 成功才可构造 readiness。
- `payload_manifest_ref` 绑定 `ReplayPayloadManifest.payload_manifest_id`。
- `payload_manifest_hash` 来自 payload manifest canonical hash，用于 CloseoutGate / CloseoutPackage checked_refs 覆盖。

如修改 `ReplayBundleReadiness` 会影响 CloseoutGate 现有比较，必须同步更新 gate/package 测试 fixture，但不得让 CloseoutGate 直接访问完整 ReplayBundle。

### 3.4 CloseoutPackage graph boundary 契约

现有逻辑只拒绝：

```python
builder_input.graph_version < replay_last_graph_version
```

V2-071E 改为：

```python
if builder_input.graph_version != replay_last_graph_version:
    raise CloseoutPackageError("graph_version must equal replay bundle proof boundary")
```

其中 `replay_last_graph_version` 由 ReplayBundle 的 attestation event window 计算。若多个 attestation 后续被引入，必须使用所有 attestation 覆盖后的最大 last_graph_version，并另行确保 windows 连续；本工作包当前按既有单 attestation 结构实现。

### 3.5 命名空间引用契约

所有本轮新生成或触及的持久引用遵循 V2-071A 格式：

```text
<kind>.<project_ref>.<content_hash_short>[.<run_id>[.<extra_suffix>]]
```

推荐 kind：

| 对象 | kind | content_hash 来源 | run_id | extra_suffix |
|---|---|---|---|---|
| ReplayBundle | `replay-bundle` | summary hash | 可选 | 无 |
| ProcessAuditArtifact | `process-audit-artifact` | artifact content sha256 | 必填或由 builder input 提供 | artifact kind |
| ProcessAuditContent | `process-audit-content` | artifact content sha256 | 必填或由 builder input 提供 | artifact kind |
| ProcessAuditBundle | `process-audit-bundle` | bundle payload hash | 可选 | 无 |
| ProcessAuditReport | `process-audit-report` | report payload hash | 可选 | 无 |
| GitVersionAuditBundle | `git-version-audit-bundle` | bundle payload hash | 可选 | 无 |
| CloseoutPackage | `closeout-package` | closeout package payload hash | 可选 | 无 |

本工作包采用唯一策略：在本轮触及的 builder input 中新增 `run_id: str | None = None`，测试 fixture 显式传入 `run_id`。ProcessAudit artifact/content refs 和 CloseoutPackage refs 必须包含 run_id；ReplayBundle 已支持 run_id；GitVersionAudit bundle/report/hash manifest refs 若本轮改造其生成逻辑，也必须透传同一 run_id。不得用“无 run_id 但有 project/hash”作为本工作包的新生成持久引用格式。

### 3.6 assert_namespaced_ref_binding 契约

新增 helper：

```python
def assert_namespaced_ref_binding(
    value: str,
    *,
    kind: str,
    project_ref: str,
    content_hash: str | Sha256Hex,
    run_id: str | None = None,
    extra_suffix: str | None = None,
    field_name: str = "namespaced_ref",
) -> str: ...
```

行为：

1. 使用 `namespaced_ref(...)` 计算 expected ref。
2. 若 `value != expected`，raise `NamespacedRefError(f"{field_name} namespace binding mismatch")`。
3. 复用 `assert_namespace_segment(...)` 和 `Sha256Hex` 校验。
4. 不做 prefix-only 校验；必须全字符串相等。

该 helper 不是 parser，也不接受 legacy short ref。

## 4. 模块设计

### 4.1 replay_bundle.py

新增：

- `ReplayPayloadResolver` protocol。
- `_payload_bytes_for_hash(value: object) -> bytes`。
- `_verify_payload_manifest_entries(bundle, payload_resolver)`。
- `ReplayBundleReadiness.payload_sha256_verified`、`payload_manifest_ref`、`payload_manifest_hash`。

`replay_bundle_readiness(...)` 流程：

1. validate bundle instance。
2. revalidate hash manifest。
3. validate replay report alignment。
4. 调用 `_verify_payload_manifest_entries(...)`：
   - 遍历 `bundle.payload_manifest.entries`。
   - 用 resolver 解析 `entry.content_ref`。
   - canonical hash 解析结果。
   - 与 `entry.sha256.value` 比对。
5. 返回 readiness，`payload_sha256_verified=True`。

错误信息：

- 缺 resolver：`payload resolver is required`
- resolver 缺 content：`payload content missing for replay manifest entry`
- hash 不匹配：`payload manifest sha256 mismatch`

### 4.2 process_audit.py

`_build_artifacts(...)` 改造：

1. 先计算每个 artifact content 的 sha256。
2. 用 `namespaced_ref(...)` 生成 artifact_id 和 content_ref。
3. `extra_suffix=kind.value`，run_id 来自 builder input。
4. `_artifact_lineage_payload(...)` 调用处传入新的 evidence_map artifact id，不再拼短格式。

新增或扩展校验：

- `process_audit_readiness(...)` 检查每个 artifact_id/content_ref 都等于按 project_ref + sha256 + run_id + kind 计算出的 namespaced ref。
- 旧短格式必须 raise `ProcessAuditError("process audit artifact ref namespace binding mismatch")`。

### 4.3 git_version_audit.py

优先改造 bundle/report/hash manifest id 的生成：

- bundle id 用 `namespaced_ref(kind="git-version-audit-bundle", project_ref=..., content_hash=bundle_payload_hash)`。
- report id 用 `namespaced_ref(kind="git-version-audit-report", project_ref=..., content_hash=report_payload_hash)`。
- hash manifest id 用 `namespaced_ref(kind="git-version-audit-hash-manifest", project_ref=..., content_hash=hash_manifest_payload_hash)`。

如果二次 hash 依赖造成构造环，允许保留 placeholder → final rebuild 两阶段，但最终对象内不得保留旧短格式。

### 4.4 closeout/package.py

改造点：

1. `_validate_builder_input(...)` 中 graph boundary 改为严格相等。
2. 所有调用 `replay_bundle_readiness(...)` 的路径传入 builder input 中的 replay readiness；package 不自行解析 payload 内容。
3. `CloseoutPackageRef` 改用 `namespaced_ref(...)`。
4. `_validate_gate_checked_refs(...)` 增加 payload manifest ref/hash 和 `payload_sha256_verified` 的覆盖检查。
5. `_validate_builder_input(...)` 对 replay/process/git/package refs 调用 `assert_namespaced_ref_binding(...)`。

## 5. Validation 规则

### 5.1 Fail-closed 条件

以下情况必须失败：

1. `replay_bundle_readiness(bundle)` 未传 resolver。
2. resolver 找不到某个 payload content_ref。
3. resolver 重算 sha256 与 manifest entry 不一致。
4. `CloseoutPackageBuilderInput.graph_version > ReplayBundle.last_graph_version`。
5. `CloseoutPackageBuilderInput.graph_version < ReplayBundle.last_graph_version`。
6. `ProcessAuditArtifactRef(value="process-audit-artifact.timeline")` 等旧短格式进入 readiness。
7. `ProcessAuditContentRef(value="process-audit-content.timeline")` 等旧短格式进入 readiness。
8. `CloseoutPackageRef` 不包含 project_ref + content hash 命名空间。
9. 同一 project_ref 多次构建 CloseoutPackage 时，如果 run_id 或 payload hash 不同却得到相同 `closeout_package_id`。
10. 跨 project / 跨 run / 跨 bundle 的 artifact_ref、content_ref、fact_set_id 或 closeout_package_id 被混用。

### 5.2 允许条件

以下情况必须通过：

1. graph_version 严格等于 ReplayBundle last_graph_version。
2. resolver 对每个 payload content_ref 返回真实内容且 sha256 重算一致。
3. ProcessAudit 所有 artifact/content refs 由 namespace helper 生成。
4. GitVersionAudit 与 CloseoutPackage 新生成 refs 可由 namespace binding helper 校验。
5. CloseoutPackage checked_refs 稳定、唯一、覆盖 gate result、source inventory、final evidence table、replay/process/git bundles、payload manifest hash、replay summary hash、process artifacts、git final commit 和 source inventory hash。

## 6. 测试计划

### 6.1 Negative tests first（必须先写）

`tests/negative/test_closeout_package_graph_version_overflow_rejected.py`：

1. `test_closeout_package_rejects_graph_version_above_replay_boundary`
   - replay last graph_version = 100，builder graph_version = 101。
   - 必须 raise `CloseoutPackageError("graph_version must equal replay bundle proof boundary")`。
2. `test_closeout_package_rejects_graph_version_below_replay_boundary`
   - replay last graph_version = 100，builder graph_version = 99。
   - 必须同样失败，防止旧错误信息只覆盖 below。

`tests/negative/test_replay_payload_manifest_tampering_rejected.py`：

1. `test_replay_bundle_readiness_requires_payload_resolver`
   - 不传 resolver 必须失败。
2. `test_replay_bundle_readiness_rejects_missing_payload_content`
   - resolver 无法解析某个 content_ref 必须失败。
3. `test_replay_bundle_readiness_rejects_payload_sha256_tampering`
   - manifest entry sha256 被替换为另一真实 sha256，resolver 返回原内容，必须失败。
4. `test_replay_bundle_readiness_hashes_canonical_json_payload`
   - resolver 返回 Mapping，字段顺序不同但语义相同，hash 稳定；若 manifest 用非 canonical hash 必须失败。

`tests/closeout/test_closeout_package_boundary.py` 中 negative cases：

1. `test_process_audit_readiness_rejects_legacy_artifact_ref`
2. `test_process_audit_readiness_rejects_legacy_content_ref`
3. `test_closeout_package_rejects_cross_project_process_audit_artifact_ref`
4. `test_closeout_package_rejects_cross_run_artifact_ref`
5. `test_closeout_package_id_changes_when_run_id_changes`
6. `test_closeout_package_rejects_non_namespaced_package_id`

### 6.2 Happy path tests

`tests/closeout/test_closeout_package_boundary.py`：

1. `test_replay_bundle_readiness_verifies_payload_manifest_with_resolver`
   - resolver 提供真实 payload，readiness payload_sha256_verified 为 true。
2. `test_closeout_package_accepts_graph_version_equal_to_replay_boundary`
   - graph_version 与 replay last graph_version 相等时可构造。
3. `test_process_audit_artifact_and_content_refs_are_namespaced`
   - 所有 10 项 artifact/content refs 均包含 kind、project_ref、content_hash short、run_id、artifact kind suffix。
4. `test_closeout_package_ref_is_namespaced_by_project_hash_and_run`
   - closeout_package_id 由 namespace helper 生成。
5. `test_namespaced_ref_binding_helper_accepts_exact_binding`
   - helper 对合法 kind/project/hash/run/suffix 通过。
6. `test_closeout_package_checked_refs_cover_payload_manifest_hash`
   - checked_refs 覆盖 payload manifest ref/hash 与 replay readiness。

### 6.3 Existing fixture updates

需要同步调整：

- `tests/closeout/test_replay_bundle.py`
- `tests/closeout/test_replay_bundle_rereplay.py`
- `tests/closeout/test_process_audit.py`
- `tests/closeout/test_process_audit_artifacts.py`
- `tests/closeout/test_process_audit_fact_chain.py`
- `tests/closeout/test_git_version_audit.py`
- `tests/closeout/test_closeout_package.py`
- `tests/closeout/test_closeout_reducer.py`
- `tests/negative/test_closeout_fail_closed.py`

迁移规则：

1. 所有 `replay_bundle_readiness(bundle)` 改为传入测试 resolver。
2. ProcessAudit fixture 提供 run_id 或使用 helper 生成 namespaced artifact/content refs。
3. CloseoutPackage fixture 的 graph_version 与 replay boundary 严格一致。
4. 任何断言旧短格式 ref 的测试改为断言 namespace helper 输出。

## 7. 验证命令

新增测试先跑：

```sh
PYTHONPATH=src:. python -m pytest tests/negative/test_closeout_package_graph_version_overflow_rejected.py tests/negative/test_replay_payload_manifest_tampering_rejected.py tests/closeout/test_closeout_package_boundary.py -q --basetemp=.pytest-tmp-v2071e-new
```

相关回归：

```sh
PYTHONPATH=src:. python -m pytest tests/closeout/test_replay_bundle.py tests/closeout/test_replay_bundle_rereplay.py tests/closeout/test_process_audit.py tests/closeout/test_process_audit_artifacts.py tests/closeout/test_process_audit_fact_chain.py tests/closeout/test_git_version_audit.py tests/closeout/test_closeout_package.py -q --basetemp=.pytest-tmp-v2071e-closeout
PYTHONPATH=src:. python -m pytest tests/closeout tests/negative -q --basetemp=.pytest-tmp-v2071e-closeout-negative
PYTHONPATH=src:. python -m pytest tests/contracts tests/reducers tests/execution tests/evidence tests/proving tests/closeout tests/negative -q --basetemp=.pytest-tmp-v2071e-all
```

成功标准：

1. 新增 negative tests 在旧实现上失败，实施后通过。
2. replay readiness 必须有 resolver 内容校验证据。
3. closeout graph_version overflow 与 underflow 都失败。
4. 旧短格式 process audit refs 被拒绝。
5. 相关 closeout 和 full regression 不回退。

## 8. 文档同步

完成实现后按 backlog 工作包完成协议更新：

1. `doc/04-implementation/backlog.md`
   - V2-071E 状态改 DONE。
   - TL;DR 当前未完成工作包指向 V2-071F。
   - Phase 7.5 进度由 4/6 改为 5/6。
   - 总进度同步增加 1。
2. `doc/04-implementation/acceptance-criteria.md`
   - 勾选 AC-V2-CLOSEOUT-007 graph_version 边界严格。
   - 勾选 AC-V2-CLOSEOUT-008 payload 内容绑定。
   - 勾选 AC-V2-CLOSEOUT-009 中 fact_set_id / artifact_ref / content_ref / closeout_package_id 命名空间相关项中 V2-071E 负责的部分。
3. `doc/05-project-log/2026-05.md`
   - 追加 V2-071E 完成记录，包含关键产出文件、negative/happy tests 和真实验证命令。
4. `doc/05-project-log/decisions.md`
   - 不新增 DEC，除非实现改变 DEC-0017 的事实链权威源原则。
5. `doc/04-implementation/INDEX.md`
   - 本 spec 创建时登记。

## 9. 风险与取舍

| 风险 | 影响 | 控制方式 |
|---|---|---|
| resolver 必填导致 fixture 迁移面较大 | 相关 closeout tests 需要统一传 resolver | 新增测试 helper，不在生产代码提供 fallback |
| namespace ref 改造触发大量字符串断言更新 | 短期测试改动增加 | 只更新本工作包触及 ref，不做无关重命名 |
| GitVersionAudit id 二阶段 hash 可能形成自引用 | bundle hash 难以稳定 | 使用 placeholder → final rebuild，但最终对象不得保留旧格式 |
| run_id 传播范围扩大 | 可能牵动 ProcessAudit fixture | 在本轮触及的 builder input 中显式添加 run_id，并集中更新测试 helper |

## 10. 完成判定

V2-071E 完成时必须满足：

1. `replay_bundle_readiness(...)` 缺 ReplayPayloadResolver 必须失败。
2. ReplayPayloadManifest sha256 与 resolver 重算内容不一致必须失败。
3. ReplayBundleReadiness 明确记录 payload sha256 已验证。
4. CloseoutPackage.graph_version 必须严格等于 ReplayBundle.last_graph_version。
5. ProcessAudit artifact/content refs 不再使用旧短格式。
6. CloseoutPackageRef 使用 project/hash/run 命名空间。
7. 新增 `assert_namespaced_ref_binding(...)` 并有负例/正例测试覆盖。
8. 新增 V2-071E tests 和相关 closeout/negative/full regression 通过。
9. backlog、acceptance criteria、项目日志和 INDEX 按协议同步。
