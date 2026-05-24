# V2-070A CloseoutGate（收尾门禁）同行评审 spec

## 1. 背景与现实场景

V2-070A 要处理的现实场景是：一个 generated project package（生成项目包）已经完成 implementation（实施）、verification（验证）、source inventory（源码清单）、evidence export（证据导出）和 checker review（检查者评审），但还不能因为“流程跑完了”就宣布项目完成。现实里这相当于交付前的发布审计闸门：发布经理或审计员要确认源码、测试证据、模型调用记录、git 状态、replay（重放）材料和 process audit（流程审计）都闭合后，才允许进入 closeout（收尾）。

通俗地说，本工作包要做的是给最终交付加一道总闸门。它不再写业务代码，不重新跑命令，也不替 V2-070B/C/D 构建 replay bundle（重放包）、process audit（流程审计）或 git audit（Git 审计）；它只消费这些阶段产出的 typed facts（类型化事实）和 readiness summaries（就绪摘要），判断是否允许产生 closeout verdict（收尾结论）。

本轮 Pre-flight（一致性预检）结论：`backlog.md`（待办）当前未完成工作包为 V2-070A；`src/boardroom_os/closeout/gate.py`、`tests/closeout/test_closeout_gate.py` 和 `tests/negative/test_closeout_fail_closed.py` 尚不存在；`acceptance-criteria.md`（验收标准）中 Phase 7 的 V2-070A 相关 checkbox（复选项）仍未勾选，状态一致，无 drift（漂移）。

## 2. 选项背景

### 2.1 方案 A：typed readiness summaries（类型化就绪摘要）

V2-070A 定义 `ReplayBundleReadiness`（重放包就绪摘要）、`GitAuditReadiness`（Git 审计就绪摘要）和 `ProcessAuditReadiness`（流程审计就绪摘要），并要求字段足够细，不能只用 `is_ready: bool`。CloseoutGate（收尾门禁）消费 readiness summaries 与已有 V2-050 / V2-060 typed objects（类型化对象），只做 fail-closed（失败关闭）判断。

优点：

- 清晰执行依赖反转：V2-070B/C/D 后续正式 builder（构建器）只需把正式对象投影为 readiness summary（就绪摘要），V2-070A gate（门禁）无需修改。
- V2-070A 不越界实现 replay/git/process audit 的正式 builder。
- negative tests（负例测试）可以精确覆盖缺 replay hash chain（重放哈希链）、git dirty（Git 脏状态）、缺 10 项 audit artifact（审计产物）等阻断条件。
- 字段粒度足够细，可避免“ready bool 被伪造”的弱门禁。

代价：

- V2-070A 会先引入三个 readiness summary schema（就绪摘要结构），这些 schema 后续必须由 V2-070B/C/D 的正式模型适配。
- readiness summary（就绪摘要）不是最终交付对象；最终 closeout package（收尾包）仍由 V2-070E 绑定。

### 2.2 方案 B：直接在 V2-070A 定义 replay/git/process audit 正式模型占位

V2-070A 同时定义 `ReplayBundle`（重放包）、`GitVersionAudit`（Git 版本审计）和 `ProcessAuditReport`（流程审计报告）的正式最小模型，并在 gate（门禁）中直接消费这些对象。

优点：后续 V2-070B/C/D 的接口看起来更稳定。

不采用原因：这会让 V2-070A 越过工作包边界，提前承担 V2-070B replay bundle builder（重放包构建器）、V2-070C process audit builder（流程审计构建器）和 V2-070D git audit（Git 审计）的职责，容易把“判断能否收尾”和“构建审计材料”混在一起。

### 2.3 方案 C：只检查已有 V2-050 / V2-060 对象，replay/git/audit 只用字符串 ref

V2-070A 只消费 FinalEvidenceTable（最终证据表）、SourceInventory（源码清单）、RunManifest（运行清单）、WorkspaceEvidenceBundle（工作区证据包）和 CheckerVerdict（检查结论），对 replay/git/process audit 只要求非空字符串引用。

优点：实现最小。

不采用原因：缺 replay bundle（重放包）、缺 hash chain（哈希链）、git dirty（Git 脏状态）、final command evidence（最终命令证据）不是 final commit（最终提交）运行、缺 process audit 10 项产物等关键阻断无法被类型化表达，门禁过弱。

## 3. 选型结论

采用方案 A：typed readiness summaries（类型化就绪摘要）。

核心边界是：V2-070A 的 CloseoutGate（收尾门禁）是纯领域 gate（门禁），它只消费 typed objects（类型化对象）和 readiness summaries（就绪摘要），不访问文件系统、不运行 git、不重放 event log（事件日志）、不生成 audit artifact（审计产物）。V2-070B/C/D 后续正式 builder 负责生成 replay/git/process audit 的完整对象，并投影成 V2-070A 已定义的 readiness summary。

readiness summary 字段必须足够细：

- `ReplayBundleReadiness`（重放包就绪摘要）必须包含 `replay_passed`、`summary_hash`、`event_range`、`projection_versions`、`hash_chain_verified`。
- `GitAuditReadiness`（Git 审计就绪摘要）必须包含 `git_clean`、`final_commit_sha`、`source_inventory_hash`、`source_inventory_hash_matches`、`final_command_evidence_at_final_commit`。
- `ProcessAuditReadiness`（流程审计就绪摘要）必须包含 10 项 audit artifact paths（审计产物路径）、`all_artifacts_present`、`timeline_key_events_present`、`agent_context_index_complete`、`artifact_lineage_complete`、`evidence_map_consistent_with_final_table`。

## 4. 目标

1. 新增 `src/boardroom_os/closeout/gate.py`，定义 CloseoutGate（收尾门禁）及其输入、结果、阻断项和 readiness summary（就绪摘要）模型。
2. 新增 `tests/negative/test_closeout_fail_closed.py`，先证明缺 replay bundle（重放包）、缺 evidence map（证据映射）、open blocker（未关闭阻断项）、provider attempt count 为 0、git dirty（Git 脏状态）、final command evidence（最终命令证据）未绑定 RunManifestBinding（运行清单绑定）都不能通过。
3. 新增 `tests/closeout/test_closeout_gate.py`，证明所有 gate inputs（门禁输入）闭合时 closeout verdict（收尾结论）为 `passed`。
4. CloseoutGate（收尾门禁）必须校验 FinalEvidenceTable（最终证据表）完整且 rows（行）全 satisfied（已满足）。
5. CloseoutGate 必须校验 SourceInventory（源码清单）存在 entries（条目）、每个 entry 有 producer ticket（生产任务）、producer attempt（生产模型调用尝试）、acceptance refs（验收引用）和 evidence refs（证据引用）。
6. CloseoutGate 必须校验 WorkspaceEvidenceBundle（工作区证据包）为 closeout-ready（收尾就绪），并与 SourceInventory / RunManifest / FinalEvidenceTable refs（引用）一致。
7. CloseoutGate 必须校验 CheckerVerdict（检查结论）为 approved（批准）或 approved_with_non_blocking_notes（带非阻断备注批准），且没有 blockers（阻断项）。
8. CloseoutGate 必须校验 provider_attempt_refs（模型调用尝试引用）非空，并覆盖 SourceInventory（源码清单）与 verified evidence（已验证证据）涉及的 producer attempts。
9. CloseoutGate 必须校验 final command evidence（最终命令证据）来自 RunManifestBinding（运行清单绑定）且 VerificationRun（验证运行）全部 passed（通过）。
10. CloseoutGate 必须校验 ReplayBundleReadiness（重放包就绪摘要）通过重放、具备 summary_hash（摘要哈希）、event_range（事件范围）、projection_versions（投影版本）和 hash chain proof（哈希链证明）。
11. CloseoutGate 必须校验 GitAuditReadiness（Git 审计就绪摘要）证明 git clean（Git 干净）、final commit SHA（最终提交 SHA）、source inventory hash match（源码清单哈希匹配）和最终命令证据在最终提交运行。
12. CloseoutGate 必须校验 SourceInventory.package_commit_ref（源码清单包提交引用）与 GitAuditReadiness.final_commit_sha（Git 审计最终提交 SHA）指向同一最终版本；首版规则为 `package_commit_ref.value == f"package-commit.{final_commit_sha.value}"` 或 `package_commit_ref.value == final_commit_sha.value`，V2-070D 可在 GitVersionAudit（Git 版本审计）实现时收紧生成规则。
13. CloseoutGate 必须校验 ProcessAuditReadiness（流程审计就绪摘要）包含 `30-audit/` 的 10 项必需产物，并证明 timeline（时间线）、agent context index（智能体上下文索引）、artifact lineage（产物来源链）和 evidence map（证据映射）闭合。
14. CloseoutGateResult（收尾门禁结果）必须 deterministic（确定性）地产生 `closeout-gate.<package_commit_ref>.<final_evidence_table_ref>` 形式的 result id（结果 ID）或等价稳定 ID。
15. CloseoutGateResult 必须在失败时返回 `blocked` verdict（阻断结论）和 typed blockers（类型化阻断项），而不是抛出后让调用方丢失审计信息；输入结构本身非法仍可由 Pydantic validation（Pydantic 校验）或 CloseoutGateError（收尾门禁错误）fail closed。

## 5. 非目标

V2-070A 不做以下事情：

1. 不构建 ReplayBundle（重放包）；event range（事件范围）、projection versions（投影版本）、hash manifest（哈希清单）和 replay report（重放报告）的构建属于 V2-070B。
2. 不生成 `30-audit/` 产物；process audit builder（流程审计构建器）属于 V2-070C。
3. 不运行 git 命令、不读取 git 仓库、不计算 final package commit（最终包提交）；git version audit（Git 版本审计）属于 V2-070D。
4. 不创建 CloseoutPackage（收尾包）；最终绑定 gate result（门禁结果）、source inventory（源码清单）、evidence table（证据表）、replay bundle（重放包）和 process audit（流程审计）属于 V2-070E。
5. 不推进 reducer terminal success（归约器终态成功）；closeout reducer（收尾归约器）属于 V2-070F。
6. 不读取旧 runtime（旧运行时）、旧 closeout state machine（旧收尾状态机）或旧 workflow completion（旧工作流完成）实现。
7. 不把 workflow completed（工作流完成）当作项目完成。
8. 不给 missing evidence（缺失证据）、git dirty（Git 脏状态）、缺 replay bundle（缺重放包）或缺 audit artifact（缺审计产物）提供 fallback（降级）通路。
9. 不重新验证 EvidenceClaim（证据声明），不重新运行 CommandRunner（命令执行器），只消费已验证事实。
10. 不把 checker notes（检查备注）当作 blocker（阻断项）豁免。

## 6. 模块设计

### 6.1 新增文件

```text
src/boardroom_os/closeout/gate.py
tests/closeout/test_closeout_gate.py
tests/negative/test_closeout_fail_closed.py
```

需要同步 `src/boardroom_os/closeout/__init__.py` 导出核心对象。如果当前目录只有 `.gitkeep`，应新增 `__init__.py`。

### 6.2 建议公开对象

```python
class CloseoutGateError(ValueError): ...

class CloseoutGateResultRef(NonEmptyTextValue): ...
class ReplaySummaryHash(NonEmptyTextValue): ...
class EventRangeRef(NonEmptyTextValue): ...
class ProjectionVersionRef(NonEmptyTextValue): ...
class GitCommitSha(NonEmptyTextValue): ...
class SourceInventoryHash(NonEmptyTextValue): ...
class ProcessAuditArtifactPath(NonEmptyTextValue): ...
class CloseoutGateBlockerRef(NonEmptyTextValue): ...

class CloseoutGateVerdict(StrEnum):
    PASSED = "passed"
    BLOCKED = "blocked"

class CloseoutGateBlockerCode(StrEnum):
    FINAL_EVIDENCE_INCOMPLETE = "final_evidence_incomplete"
    SOURCE_INVENTORY_INCOMPLETE = "source_inventory_incomplete"
    WORKSPACE_EVIDENCE_BUNDLE_NOT_READY = "workspace_evidence_bundle_not_ready"
    CHECKER_NOT_APPROVED = "checker_not_approved"
    PROVIDER_ATTEMPTS_MISSING = "provider_attempts_missing"
    COMMAND_EVIDENCE_NOT_FINAL = "command_evidence_not_final"
    REPLAY_NOT_READY = "replay_not_ready"
    GIT_AUDIT_NOT_READY = "git_audit_not_ready"
    PACKAGE_COMMIT_MISMATCH = "package_commit_mismatch"
    PROCESS_AUDIT_NOT_READY = "process_audit_not_ready"
    REF_MISMATCH = "ref_mismatch"

class ReplayBundleReadiness(BaseModel): ...
class GitAuditReadiness(BaseModel): ...
class ProcessAuditReadiness(BaseModel): ...
class CloseoutCommandEvidenceBinding(BaseModel): ...
class CloseoutGateBlocker(BaseModel): ...
class CloseoutGateInput(BaseModel): ...
class CloseoutGateResult(BaseModel): ...

class CloseoutGate:
    def evaluate(self, gate_input: CloseoutGateInput) -> CloseoutGateResult: ...
```

`CloseoutGateError`（收尾门禁错误）用于输入类型错误、无法形成审计结果的结构性异常；业务阻断应优先进入 `CloseoutGateResult.blockers`（门禁结果阻断项）。

## 7. Schema（结构）设计

### 7.1 ReplayBundleReadiness（重放包就绪摘要）

建议 schema：

```yaml
replay_passed: true
summary_hash:
event_range:
projection_versions:
  - ...
hash_chain_verified: true
```

字段说明：

- `replay_passed`：V2-070B 的 replay builder（重放构建器）是否已证明 typed summary（类型化摘要）可重建。
- `summary_hash`：ProjectionReplaySummary（投影重放摘要）或 replay report（重放报告）的稳定摘要哈希。必须为 64 位小写 sha256 hex digest（十六进制摘要），或复用已有 hash value object（哈希值对象）。
- `event_range`：事件范围引用或值对象，首版可用 `EventRangeRef`（事件范围引用）表达；必须非空。
- `projection_versions`：参与重放的 projection version refs（投影版本引用），必须非空且唯一。
- `hash_chain_verified`：event log hash chain / hash manifest（事件日志哈希链 / 哈希清单）是否已验证。

不变量：

1. `replay_passed` 必须为 true 才能通过 gate。
2. `summary_hash` 必须非空且符合 hash 格式。
3. `event_range` 必须非空。
4. `projection_versions` 必须非空且唯一。
5. `hash_chain_verified` 必须为 true。
6. 任意 extra fields（额外字段）必须 fail closed（失败关闭）。

### 7.2 GitAuditReadiness（Git 审计就绪摘要）

建议 schema：

```yaml
git_clean: true
final_commit_sha:
source_inventory_hash:
source_inventory_hash_matches: true
final_command_evidence_at_final_commit: true
```

字段说明：

- `git_clean`：final package workspace（最终项目包工作区）是否干净。
- `final_commit_sha`：最终包提交 SHA。必须是合法 git SHA 形状，首版建议接受 40 位小写 hex SHA-1；若后续支持 SHA-256 repo，可由 V2-070D 扩展类型。
- `source_inventory_hash`：SourceInventory（源码清单）序列化内容哈希。必须为 64 位小写 sha256 hex digest。
- `source_inventory_hash_matches`：GitVersionAudit（Git 版本审计）记录的 source inventory hash 是否与 gate 输入 SourceInventory（源码清单）派生 hash 一致。
- `final_command_evidence_at_final_commit`：所有 final command evidence（最终命令证据）是否在 `final_commit_sha` 对应版本运行。

不变量：

1. `git_clean` 必须为 true。
2. `final_commit_sha` 必须非空且格式合法。
3. `source_inventory_hash` 必须非空且格式合法。
4. `source_inventory_hash_matches` 必须为 true。
5. `final_command_evidence_at_final_commit` 必须为 true。
6. 任意 extra fields（额外字段）必须 fail closed（失败关闭）。

### 7.3 ProcessAuditReadiness（流程审计就绪摘要）

必需 artifact paths（产物路径）固定为 backlog V2-070C 的 10 项：

```text
30-audit/process-audit.md
30-audit/timeline.json
30-audit/decision-log.md
30-audit/agent-context-index.json
30-audit/ticket-graph.md
30-audit/artifact-lineage.json
30-audit/evidence-map.json
30-audit/git-version-audit.md
30-audit/closeout-summary.md
30-audit/replay-bundle-report.json
```

建议 schema：

```yaml
artifact_paths:
  - 30-audit/process-audit.md
  - 30-audit/timeline.json
  - 30-audit/decision-log.md
  - 30-audit/agent-context-index.json
  - 30-audit/ticket-graph.md
  - 30-audit/artifact-lineage.json
  - 30-audit/evidence-map.json
  - 30-audit/git-version-audit.md
  - 30-audit/closeout-summary.md
  - 30-audit/replay-bundle-report.json
all_artifacts_present: true
timeline_key_events_present: true
agent_context_index_complete: true
artifact_lineage_complete: true
evidence_map_consistent_with_final_table: true
```

字段说明：

- `artifact_paths`：ProcessAudit（流程审计）实际产出的 artifact path（产物路径）集合，必须与 10 项必需路径完全一致。
- `all_artifacts_present`：V2-070C 是否已证明 10 项产物都存在。
- `timeline_key_events_present`：timeline.json（时间线）是否包含 directive received、charter created、acceptance contract created、package contract created、seat assigned、ticket lifecycle、provider attempt、command run、evidence verified、checker verdict、closeout、replay 等关键事件。
- `agent_context_index_complete`：agent-context-index.json（智能体上下文索引）是否包含 execution_package_ref（执行包引用）、model_execution_profile（模型执行配置）和 provider_attempt_ref（模型调用尝试引用）。
- `artifact_lineage_complete`：artifact-lineage.json（产物来源链）是否表达 producer attempt -> artifact -> consumer ticket -> evidence claim -> verifier -> closeout 链路，并覆盖 fallback decision（降级判定）链路。
- `evidence_map_consistent_with_final_table`：evidence-map.json（证据映射）是否与 FinalEvidenceTable（最终证据表）一致。

不变量：

1. `artifact_paths` 必须是 tuple/list，且路径集合与 10 项必需路径完全一致。
2. `artifact_paths` 不允许重复路径。
3. 所有 path 必须位于 `30-audit/`，使用 forward slash（正斜杠），不得 absolute path（绝对路径）、Windows drive（Windows 盘符）、反斜杠、`.`、`..` 或尾部斜杠。
4. `all_artifacts_present` 必须为 true。
5. `timeline_key_events_present` 必须为 true。
6. `agent_context_index_complete` 必须为 true。
7. `artifact_lineage_complete` 必须为 true。
8. `evidence_map_consistent_with_final_table` 必须为 true。
9. 任意 extra fields（额外字段）必须 fail closed（失败关闭）。

### 7.4 CloseoutCommandEvidenceBinding（收尾命令证据绑定）

V2-070A 需要证明 final command evidence（最终命令证据）不是任意 VerificationRun（验证运行），而是经 RunManifestBinding（运行清单绑定）确认的 declared command（声明命令）。

建议 schema：

```yaml
verification_run_ref:
run_manifest_ref:
package_contract_ref:
command_id:
binding_kind: run | test
```

字段说明：

- `verification_run_ref`：VerificationRunRef（验证运行引用），必须能在 `verification_runs` 输入中解析。
- `run_manifest_ref`：RunManifestRef（运行清单引用），必须等于输入 RunManifest（运行清单）。
- `package_contract_ref`：ContractId（合同 ID），必须等于输入 PackageContract / RunManifest / WorkspaceEvidenceBundle（工作区证据包）中的 package contract ref（包合同引用）。
- `command_id`：ContractId（命令 ID），必须能通过 `validate_run_manifest_binding(...)` 或传入的 RunManifestBinding（运行清单绑定）证明。
- `binding_kind`：run 或 test，必须与 RunManifestCommandKind（运行清单命令类型）一致。

首版实现可以直接让 CloseoutGateInput（收尾门禁输入）携带 `final_command_bindings: tuple[RunManifestBinding, ...]` 与 `verification_runs: tuple[VerificationRun, ...]`，不一定新增 `CloseoutCommandEvidenceBinding`；但测试必须覆盖“任一 declared command 未经 RunManifestBinding 即被用作 final command evidence 必须失败”。

### 7.5 CloseoutGateInput（收尾门禁输入）

建议 schema：

```yaml
package_contract:
source_inventory:
run_manifest:
workspace_evidence_bundle:
final_evidence_table:
checker_verdict:
verification_runs:
verified_evidence:
provider_attempt_refs:
final_command_bindings:
replay_readiness:
git_audit_readiness:
process_audit_readiness:
```

字段说明：

- `package_contract`：PackageContract（包合同），用于确认 package root（包根）、declared commands（声明命令）和 contract refs（合同引用）。
- `source_inventory`：SourceInventory（源码清单）。
- `run_manifest`：RunManifest（运行清单）。
- `workspace_evidence_bundle`：WorkspaceEvidenceBundle（工作区证据包）。
- `final_evidence_table`：FinalEvidenceTable（最终证据表）。
- `checker_verdict`：CheckerVerdict（检查结论）。
- `verification_runs`：tuple[VerificationRun, ...]（验证运行集合），必须非空且全部 passed。
- `verified_evidence`：tuple[VerifiedEvidence, ...]（已验证证据集合），必须解析 final evidence table 中所有 refs。
- `provider_attempt_refs`：tuple[ProviderAttemptRef, ...]（模型调用尝试引用集合），必须非空。
- `final_command_bindings`：tuple[RunManifestBinding, ...]（最终命令绑定集合），必须覆盖作为 final command evidence 的 VerificationRun。
- `replay_readiness`：ReplayBundleReadiness（重放包就绪摘要）。
- `git_audit_readiness`：GitAuditReadiness（Git 审计就绪摘要）。
- `process_audit_readiness`：ProcessAuditReadiness（流程审计就绪摘要）。

不变量：

1. 所有 tuple/list 输入必须是真的 tuple/list，不接受 scalar string（标量字符串）。
2. 所有对象字段必须是对应 typed model（类型化模型）实例，不接受 raw dict（原始字典）绕过。
3. `provider_attempt_refs`、`verification_runs`、`verified_evidence`、`final_command_bindings` 必须非空且 ref 唯一。
4. 任意 extra fields（额外字段）必须 fail closed（失败关闭）。

### 7.6 CloseoutGateBlocker（收尾门禁阻断项）

建议 schema：

```yaml
blocker_id:
code:
message:
related_ref:
source:
```

字段说明：

- `blocker_id`：确定性 ID，建议 `closeout-blocker.<code>.<related_ref>`。
- `code`：CloseoutGateBlockerCode（收尾门禁阻断码）。
- `message`：人类可读说明。
- `related_ref`：相关对象引用，例如 final evidence table ref（最终证据表引用）、source inventory ref（源码清单引用）、run manifest ref（运行清单引用）。
- `source`：产生阻断的 gate check（门禁检查）名称。

`message`、`related_ref`、`source` 均不能为空；blocker id（阻断项 ID）必须 deterministic（确定性）。

### 7.7 CloseoutGateResult（收尾门禁结果）

建议 schema：

```yaml
version: 1
closeout_gate_result_id:
package_contract_ref:
package_commit_ref:
final_evidence_table_ref:
source_inventory_ref:
workspace_evidence_bundle_ref:
verdict: passed | blocked
blockers:
checked_refs:
```

字段说明：

- `package_commit_ref`：来自 SourceInventory.package_commit_ref（源码清单包提交引用）。
- `verdict`：没有 blockers 时为 `passed`，有 blockers 时为 `blocked`。
- `blockers`：typed blockers（类型化阻断项）。
- `checked_refs`：可审计引用集合，至少包含 source inventory、final evidence table、workspace evidence bundle、run manifest、checker verdict、replay summary hash、git final commit、process audit artifact refs；若 verified evidence（已验证证据）包含 fallback_decision_record_ref（降级判定记录引用），也必须包含全部 fallback_decision_record_refs，方便审计员从 closeout result（收尾结果）追踪 fallback lineage（降级来源链）。

不变量：

1. `closeout_gate_result_id` 必须由 `package_commit_ref` 和 `final_evidence_table_ref` 稳定派生。
2. `passed` verdict 不允许 blockers。
3. `blocked` verdict 必须至少一个 blocker。
4. `checked_refs` 必须非空且唯一。
5. 任意 extra fields（额外字段）必须 fail closed（失败关闭）。

## 8. CloseoutGate（收尾门禁）校验语义

### 8.1 Reference closure（引用闭合）

CloseoutGate 必须先校验各对象引用一致：

1. `package_contract.package_contract_id == source_inventory.package_contract_ref`。
2. `package_contract.package_contract_id == run_manifest.package_contract_ref`。
3. `package_contract.package_contract_id == workspace_evidence_bundle.package_contract_ref`。
4. `source_inventory.source_inventory_id == workspace_evidence_bundle.source_inventory_ref`。
5. `run_manifest.run_manifest_id == workspace_evidence_bundle.run_manifest_ref`。
6. `final_evidence_table.final_evidence_table_id == workspace_evidence_bundle.final_evidence_table_ref`。
7. `checker_verdict.final_evidence_table_ref == final_evidence_table.final_evidence_table_id`。
8. `checker_verdict.acceptance_contract_ref == final_evidence_table.acceptance_contract_ref`。
9. `source_inventory.package_commit_ref` 必须与 `git_audit_readiness.final_commit_sha` 指向同一最终版本；首版允许 `package_commit_ref.value == final_commit_sha.value` 或 `package_commit_ref.value == f"package-commit.{final_commit_sha.value}"`。

第 1~8 项任一不一致产生 `REF_MISMATCH` blocker（引用不一致阻断项）；第 9 项不一致产生 `PACKAGE_COMMIT_MISMATCH` blocker（包提交不一致阻断项）。

### 8.2 Final evidence table（最终证据表）

必须满足：

1. `complete is True`。
2. rows 非空。
3. 所有 row status 都是 `satisfied`。
4. 每个 satisfied row 都有 verified_evidence_refs。
5. final evidence table 中所有 verified_evidence_refs 都能在 `verified_evidence` 输入中解析。
6. `verified_evidence` 输入不能包含 final table 未引用的孤儿证据。

否则产生 `FINAL_EVIDENCE_INCOMPLETE` blocker。

### 8.3 Source inventory（源码清单）

必须满足：

1. entries 非空。
2. 每个 entry 有 path、sha256、source_surface_ref、producer_ticket_ref、producer_attempt_ref、acceptance_refs、evidence_refs。
3. 每个 entry.evidence_refs 都必须被 final evidence table 承认。
4. 每个 entry.producer_attempt_ref 都必须出现在 `provider_attempt_refs` 中。
5. `source_inventory.package_commit_ref` 必须非空，并作为 closeout gate result 的 package_commit_ref。

否则产生 `SOURCE_INVENTORY_INCOMPLETE` blocker。

### 8.4 Workspace evidence bundle（工作区证据包）

必须满足：

1. `closeout_ready is True`。
2. artifacts 覆盖 source inventory、verification runs、run manifest、final evidence table 和 bundle manifest 五类。
3. bundle refs 与 gate 输入对象一致。
4. bundle.verified_evidence_refs 与 final evidence table refs 一致。
5. bundle.verification_run_refs 与 `verification_runs` 输入一致。

否则产生 `WORKSPACE_EVIDENCE_BUNDLE_NOT_READY` blocker。

### 8.5 Checker verdict（检查结论）

必须满足：

1. status 为 `approved` 或 `approved_with_non_blocking_notes`。
2. blockers 为空。
3. ticket/work product/source diff 相关 refs 非空。
4. verdict 的 final_evidence_table_ref 和 acceptance_contract_ref 与 gate 输入一致。

否则产生 `CHECKER_NOT_APPROVED` blocker。

### 8.6 Provider attempts（模型调用尝试）

必须满足：

1. `provider_attempt_refs` 非空。
2. `provider_attempt_refs` 唯一。
3. 所有 VerifiedEvidence.producer_attempt_ref 都在 `provider_attempt_refs` 中。
4. 所有 SourceInventoryEntry.producer_attempt_ref 都在 `provider_attempt_refs` 中。

否则产生 `PROVIDER_ATTEMPTS_MISSING` blocker。

### 8.7 Final command evidence（最终命令证据）

必须满足：

1. `verification_runs` 非空且全部 status passed。
2. 每个 verification run ref 都被 WorkspaceEvidenceBundle（工作区证据包）引用。
3. `final_command_bindings` 非空。
4. 每个 final command binding 都属于输入 RunManifest（运行清单）与 PackageContract（包合同）。
5. 每个作为 final command evidence 的 VerificationRun（验证运行）都能关联到一个 RunManifestBinding（运行清单绑定）。
6. GitAuditReadiness.final_command_evidence_at_final_commit 必须为 true。

否则产生 `COMMAND_EVIDENCE_NOT_FINAL` blocker。

### 8.8 Replay readiness（重放就绪）

必须满足 ReplayBundleReadiness 全部不变量：`replay_passed is True`、summary_hash 非空、event_range 非空、projection_versions 非空且唯一、`hash_chain_verified is True`。

否则产生 `REPLAY_NOT_READY` blocker。

### 8.9 Git audit readiness（Git 审计就绪）

必须满足 GitAuditReadiness 全部不变量：`git_clean is True`、final_commit_sha 合法、source_inventory_hash 合法、`source_inventory_hash_matches is True`、`final_command_evidence_at_final_commit is True`。此外，SourceInventory.package_commit_ref（源码清单包提交引用）必须与 GitAuditReadiness.final_commit_sha（Git 审计最终提交 SHA）指向同一最终版本；首版匹配规则为 `package_commit_ref.value == final_commit_sha.value` 或 `package_commit_ref.value == f"package-commit.{final_commit_sha.value}"`。

否则产生 `GIT_AUDIT_NOT_READY` 或 `PACKAGE_COMMIT_MISMATCH` blocker。

### 8.10 Process audit readiness（流程审计就绪）

必须满足 ProcessAuditReadiness 全部不变量：10 项 artifact_paths 完全覆盖，且所有细粒度布尔均为 true。

否则产生 `PROCESS_AUDIT_NOT_READY` blocker。

## 9. 数据流

```text
V2-050F CompletionGate（完成门禁）
  -> ticket completion facts（任务完成事实）
  -> FinalEvidenceTable（最终证据表）
  -> CheckerVerdict（检查结论）

V2-060C SourceInventory（源码清单）
  -> package_commit_ref（包提交引用）
  -> source lineage（源码来源链）

V2-060D RunManifest（运行清单）
  -> RunManifestBinding（运行清单绑定）
  -> declared command evidence（声明命令证据）

V2-060E WorkspaceEvidenceBundle（工作区证据包）
  -> closeout_ready evidence bundle（收尾就绪证据包）

V2-070B ReplayBundle builder（重放包构建器，后续）
  -> ReplayBundleReadiness（重放包就绪摘要）

V2-070C ProcessAudit builder（流程审计构建器，后续）
  -> ProcessAuditReadiness（流程审计就绪摘要）

V2-070D GitVersionAudit builder（Git 版本审计构建器，后续）
  -> GitAuditReadiness（Git 审计就绪摘要）

CloseoutGate（收尾门禁）
  -> CloseoutGateResult(verdict=passed|blocked)（收尾门禁结果）
```

关键边界：

```text
Builders construct facts/readiness summaries（构建器产出事实/就绪摘要）
Gate evaluates facts/readiness summaries（门禁评估事实/就绪摘要）
Reducers consume passed gate result later（归约器后续消费已通过门禁结果）
```

V2-070A 不把 readiness summary（就绪摘要）反向扩展为正式 replay/git/audit 对象。

## 10. Fail-closed（失败关闭）规则

### 10.1 模型层必须失败的情况

1. ReplayBundleReadiness 缺 `replay_passed`、`summary_hash`、`event_range`、`projection_versions` 或 `hash_chain_verified`。
2. ReplayBundleReadiness `summary_hash` 非 64 位小写 sha256 hex digest。
3. ReplayBundleReadiness `projection_versions` 为空或重复。
4. GitAuditReadiness 缺 `git_clean`、`final_commit_sha`、`source_inventory_hash`、`source_inventory_hash_matches` 或 `final_command_evidence_at_final_commit`。
5. GitAuditReadiness `final_commit_sha` 为空或格式非法。
6. GitAuditReadiness `source_inventory_hash` 非 64 位小写 sha256 hex digest。
7. ProcessAuditReadiness 缺 `artifact_paths` 或任一细粒度布尔。
8. ProcessAuditReadiness `artifact_paths` 不是 tuple/list。
9. ProcessAuditReadiness `artifact_paths` 有重复、越界路径、反斜杠、absolute path、Windows drive、`.`、`..` 或尾部斜杠。
10. ProcessAuditReadiness `artifact_paths` 不等于 10 项必需路径集合。
11. CloseoutGateInput 的 tuple/list 字段传入 scalar string。
12. CloseoutGateInput 传入 raw dict 替代 typed model。
13. CloseoutGateResult 的 verdict 与 blockers 不一致。
14. 任意 extra fields（额外字段）。

### 10.2 Gate evaluation（门禁评估）必须 blocked 的情况

1. final evidence table incomplete（最终证据表不完整）。
2. final evidence table 有 missing / failed row（缺失/失败行）。
3. final evidence table refs 无法解析到 verified evidence（已验证证据）。
4. source inventory entries 为空。
5. source inventory evidence refs 未被 final evidence table 承认。
6. source inventory producer attempt refs 不在 provider_attempt_refs 中。
7. workspace evidence bundle closeout_ready 不是 true。
8. workspace evidence bundle artifact kinds（产物类型）不完整。
9. checker verdict status 不是 approved / approved_with_non_blocking_notes。
10. checker verdict 有 blockers。
11. provider_attempt_refs 为空或重复。
12. verified evidence producer_attempt_ref 不在 provider_attempt_refs 中。
13. verification_runs 为空、重复或任一 failed。
14. final command evidence 缺 RunManifestBinding（运行清单绑定）。
15. RunManifestBinding 与 RunManifest / PackageContract 不一致。
16. replay_passed 为 false。
17. hash_chain_verified 为 false。
18. git_clean 为 false。
19. source_inventory_hash_matches 为 false。
20. final_command_evidence_at_final_commit 为 false。
21. source_inventory.package_commit_ref 与 git_audit_readiness.final_commit_sha 不指向同一最终版本。
22. process audit 10 项 artifact 缺任意一项。
23. timeline_key_events_present 为 false。
24. agent_context_index_complete 为 false。
25. artifact_lineage_complete 为 false。
26. evidence_map_consistent_with_final_table 为 false。
27. 任一关键 ref 不一致。

## 11. 测试计划

测试文件：

```text
tests/negative/test_closeout_fail_closed.py
tests/closeout/test_closeout_gate.py
```

### 11.1 Negative tests first（负例优先）

`tests/negative/test_closeout_fail_closed.py` 建议覆盖：

1. `test_closeout_gate_rejects_missing_replay_bundle_readiness_fields`
2. `test_closeout_gate_blocks_when_replay_not_passed`
3. `test_closeout_gate_blocks_when_replay_hash_chain_not_verified`
4. `test_closeout_gate_blocks_when_final_evidence_table_missing_or_failed`
5. `test_closeout_gate_blocks_when_evidence_map_is_empty_or_unresolved`
6. `test_closeout_gate_blocks_when_checker_verdict_has_open_blocker`
7. `test_closeout_gate_blocks_when_provider_attempt_refs_are_empty`
8. `test_closeout_gate_blocks_when_source_inventory_attempt_not_in_provider_attempts`
9. `test_closeout_gate_blocks_when_git_dirty`
10. `test_closeout_gate_blocks_when_source_inventory_hash_does_not_match_git_audit`
11. `test_closeout_gate_blocks_when_final_command_evidence_not_at_final_commit`
12. `test_closeout_gate_blocks_when_declared_command_lacks_run_manifest_binding`
13. `test_closeout_gate_blocks_when_process_audit_missing_required_artifact_path`
14. `test_closeout_gate_blocks_when_timeline_key_events_missing`
15. `test_closeout_gate_blocks_when_agent_context_index_incomplete`
16. `test_closeout_gate_blocks_when_artifact_lineage_incomplete`
17. `test_closeout_gate_blocks_when_evidence_map_inconsistent_with_final_table`
18. `test_closeout_gate_blocks_when_source_inventory_commit_does_not_match_git_audit`
19. `test_closeout_gate_blocks_when_verified_evidence_contains_orphan_not_in_final_table`
20. `test_closeout_gate_rejects_scalar_tuple_inputs`
21. `test_closeout_gate_rejects_raw_dict_model_inputs`
22. `test_closeout_gate_result_requires_blockers_for_blocked_verdict`

这些负例必须先写，并应在实现前得到预期 RED（红灯），例如缺 `boardroom_os.closeout.gate` 模块或缺对应模型。

### 11.2 Happy path（正向路径）

`tests/closeout/test_closeout_gate.py` 建议覆盖：

1. `test_closeout_gate_passes_when_all_inputs_are_ready`
   - 优先复用 `tests/proving/test_workspace_evidence_export.py` 中 closeout-ready bundle（收尾就绪证据包）相关 fixture/helper（夹具/辅助函数）形状，避免重新搭建与 V2-060E 重复的完整 evidence bundle（证据包）闭合逻辑。
   - 构造 active PackageContract（包合同）。
   - 构造 complete FinalEvidenceTable（完整最终证据表）。
   - 构造 SourceInventory（源码清单）且每个 entry 绑定 producer attempt / evidence refs。
   - 构造 RunManifest（运行清单）、RunManifestBinding（运行清单绑定）和 passed VerificationRun（通过的验证运行）。
   - 构造 closeout_ready WorkspaceEvidenceBundle（收尾就绪工作区证据包）。
   - 构造 approved CheckerVerdict（批准检查结论）。
   - 构造 provider_attempt_refs（模型调用尝试引用）。
   - 构造三类 readiness summaries（就绪摘要）且所有细字段闭合。
   - 断言 `CloseoutGate.evaluate(...).verdict == passed`。
   - 断言 result id（结果 ID）、package_commit_ref（包提交引用）、checked_refs（已检查引用）稳定。

2. `test_closeout_gate_allows_checker_non_blocking_notes`
   - CheckerVerdict（检查结论）为 approved_with_non_blocking_notes（带非阻断备注批准）。
   - 无 blockers（阻断项）。
   - gate 仍 passed。

3. `test_closeout_gate_blocked_result_is_auditable`
   - 触发多个 business blockers（业务阻断），例如 git dirty + replay failed。
   - 断言 result.verdict 为 blocked。
   - 断言 blockers 包含 deterministic blocker_id、code、message、related_ref、source。
   - 断言不会把首个 blocker 之后的其它 blocker 静默吞掉。

4. `test_readiness_summaries_are_audit_friendly_json`
   - 三个 readiness summary 可 model_dump(mode="json")。
   - 输出不含 host absolute path（宿主绝对路径）。
   - process audit artifact paths（流程审计产物路径）为稳定集合。

### 11.3 回归边界

实施完成后应至少回归：

1. `tests/evidence/test_final_evidence_table.py`，证明 FinalEvidenceTable（最终证据表）语义未被 gate 改写。
2. `tests/proving/test_workspace_evidence_export.py`，证明 WorkspaceEvidenceBundle（工作区证据包）仍由 V2-060E 构建。
3. `tests/reducers/test_completion_gate_with_evidence.py`，证明 ticket completion gate（任务完成门禁）和 closeout gate（收尾门禁）分层清晰。
4. `tests/execution/test_command_runner.py` 与 `tests/proving/test_run_manifest.py`，证明 command evidence（命令证据）仍来自 runner（运行器）和 RunManifestBinding（运行清单绑定）。

## 12. 验证命令

实施完成后建议运行：

```bash
PYTHONPATH="src;." python -m pytest tests/negative/test_closeout_fail_closed.py -q
PYTHONPATH="src;." python -m pytest tests/closeout/test_closeout_gate.py -q
PYTHONPATH="src;." python -m pytest tests/negative/test_closeout_fail_closed.py tests/closeout/test_closeout_gate.py -q
PYTHONPATH="src;." python -m pytest tests/evidence/test_final_evidence_table.py tests/proving/test_workspace_evidence_export.py tests/reducers/test_completion_gate_with_evidence.py tests/execution/test_command_runner.py tests/proving/test_run_manifest.py tests/negative/test_closeout_fail_closed.py tests/closeout/test_closeout_gate.py -q
PYTHONPATH="src;." python -m pytest tests/contracts tests/reducers tests/execution tests/evidence tests/proving tests/closeout tests/negative -q
```

其中前两条分别证明负例和正例；第三条证明 V2-070A 自身；第四条证明 V2-050/V2-060 边界未回退；第五条作为全量回归。

## 13. 完成后文档同步

实现完成并通过验证后，必须按 `backlog.md` 的工作包完成更新协议同步：

1. `doc/04-implementation/backlog.md`
   - V2-070A 状态改为 DONE。
   - 顶部 “当前未完成工作包” 指向 V2-070B。
   - Phase 7 进度从 0 / 6 改为 1 / 6；总计从 41 / 53 改为 42 / 53。
2. `doc/04-implementation/acceptance-criteria.md`
   - 勾选 AC-V2-CLOSEOUT-001（closeout 只能在 verified evidence 之后）中 V2-070A 覆盖部分。
   - 若 replay bundle required（重放包必需）仍需 V2-070B 闭合，则不得提前勾选 AC-V2-CLOSEOUT-002 的完整项，只能在日志/说明中标记 V2-070A 已建立 gate 消费边界。
3. `doc/05-project-log/2026-05.md`
   - 追加 V2-070A 完成记录，包含关键产出文件、negative/happy tests（负例/正例测试）和验证命令证据。
4. `doc/05-project-log/decisions.md`
   - 仅当实现中改变 readiness summary（就绪摘要）作为依赖反转边界、提前实现 V2-070B/C/D builder、或改变 closeout gate 与 reducer 的职责边界时才新增决策。按本 spec 实施不需要新增 DEC。
5. `doc/04-implementation/INDEX.md`
   - 本 spec 文件需加入索引；若后续新增实施计划文档，再按文件名补充。

## 14. 评审关注点

1. 是否同意 V2-070A 只做 CloseoutGate（收尾门禁），不构建 replay/git/process audit 正式对象。
2. 是否同意 readiness summaries（就绪摘要）作为 V2-070A 与 V2-070B/C/D 的依赖反转接口。
3. 是否同意 readiness summaries 采用细粒度字段，而不是 `is_ready: bool`。
4. 是否同意 ReplayBundleReadiness（重放包就绪摘要）必须同时要求 replay_passed、summary_hash、event_range、projection_versions 和 hash_chain_verified。
5. 是否同意 GitAuditReadiness（Git 审计就绪摘要）必须同时要求 git_clean、final_commit_sha、source_inventory_hash、source_inventory_hash_matches 和 final_command_evidence_at_final_commit。
6. 是否同意 ProcessAuditReadiness（流程审计就绪摘要）必须强制 10 项 `30-audit/` artifact paths，并分别校验 timeline、agent context index、artifact lineage、evidence map。
7. 是否同意 CloseoutGate（收尾门禁）返回 blocked result（阻断结果）和 typed blockers（类型化阻断项），而不是遇到第一个业务阻断就抛异常。
8. 是否同意 raw dict（原始字典）不能绕过 gate input（门禁输入）类型检查。
9. 是否同意 final command evidence（最终命令证据）必须经 RunManifestBinding（运行清单绑定），不能只凭 VerificationRun（验证运行）存在就通过。
10. 是否同意 V2-070A 不提前勾选 AC-V2-CLOSEOUT-002 的 replay bundle required（重放包必需）完整验收，而由 V2-070B 补齐 replay bundle builder（重放包构建器）后闭合。
