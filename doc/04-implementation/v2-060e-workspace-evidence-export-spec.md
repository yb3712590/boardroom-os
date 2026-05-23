# V2-060E WorkspaceEvidenceExport（工作区证据导出）同行评审 spec

## 1. 背景与现实场景

V2-060E 要处理的现实场景是：Boardroom OS V2（董事会式智能体团队框架）已经通过 V2-060A ~ V2-060D 建立了 WorkspaceManifest（工作区清单）、PackageAssembly（项目包装配结果）、SourceInventory（源码清单）和 RunManifest（运行清单）；V2-050B / V2-050C 已建立 VerifiedEvidence（已验证证据）和 FinalEvidenceTable（最终证据表）；V2-040D 已建立 VerificationRun（验证运行）。下一步需要把这些已验证事实组织为 `20-evidence`（证据区）下可供 V2-070 closeout（收尾）消费的 evidence bundle（证据包）。

通俗地说，系统不能只交付 `10-project`（生成项目包）然后口头说“测试也跑过”。它必须同步产出一份机器可检查的证据包：哪些源码文件进入最终包、这些源码来自哪个 ticket（任务）和 provider attempt（模型调用尝试记录）、哪些 command（命令）真实运行过、stdout/stderr（标准输出/标准错误）在哪里、哪些 verified evidence（已验证证据）满足了哪些 acceptance criterion（验收项）。V2-060E 的职责是把这些事实整理成 closeout-ready（可收尾）的导出计划，而不是重新验证或补造证据。

本轮 Pre-flight（一致性预检）结论：`backlog.md`（待办）当前未完成工作包为 V2-060E；`src/boardroom_os/workspace/evidence_export.py` 和 `tests/proving/test_workspace_evidence_export.py` 尚不存在；`acceptance-criteria.md`（验收标准）中 Phase 6 的 “Workspace / package / evidence 三者同步” checkbox（复选项）仍未勾选，状态一致，无 drift（漂移）。

## 2. 选项背景

### 2.1 方案 1：纯 WorkspaceEvidenceBundle（工作区证据包）装配计划

新增 `WorkspaceEvidenceBundle`（工作区证据包）typed domain model（类型化领域模型）和 `build_workspace_evidence_bundle()`（构建工作区证据包函数）。该 builder（构建函数）消费 WorkspaceManifest（工作区清单）、PackageAssembly（项目包装配结果）、SourceInventory（源码清单）、RunManifest（运行清单）、VerificationRun（验证运行）集合、VerifiedEvidence（已验证证据）集合和 FinalEvidenceTable（最终证据表），输出 deterministic（确定性）bundle plan（证据包计划）及 `20-evidence/...` 下的 logical artifacts（逻辑产物）。

优点：

- 延续 V2-060B / V2-060C / V2-060D 的纯领域模型边界：不创建目录、不写文件、不调用 git、不运行命令。
- 能直接证明 workspace（工作区）、package（项目包）和 evidence（证据）同步，不允许先交付再补证据。
- 可用 negative tests first（负例优先）覆盖 incomplete FinalEvidenceTable（不完整最终证据表）、缺 source lineage（源码来源链）、缺 stdout/stderr refs（标准输出/错误引用）等 fail-closed（失败关闭）场景。
- 为 V2-070 closeout（收尾）提供稳定输入，也为 V2-080 tiny scenario（微型端到端证明场景）的真实物化保留边界。

代价：

- V2-060E 不会真实落盘 `20-evidence` 文件。
- 后续若需要写文件，需要单独 materializer（物化器）或由 proving scenario（证明场景）测试层完成。
- 需要新增 bundle artifact（证据包产物）模型，而不是简单复用 PackageArtifact（包产物）。

### 2.2 方案 2：真实写入 `20-evidence` 文件

在 V2-060E 中直接创建 `20-evidence/tests`、`20-evidence/source-inventory`、`20-evidence/closeout` 等目录，并写入 JSON evidence files（证据文件）。

优点：更接近最终生成 workspace（工作区）的运行形态。

不采用原因：这会引入文件系统副作用、临时目录清理、幂等写入和编码策略问题，且与 V2-060B / V2-060C “纯装配计划”边界不一致。当前阶段的核心能力是 contract/evidence 同步校验（合同/证据同步校验），不是 materialization（物化）。

### 2.3 方案 3：只校验输入一致，不输出 bundle plan

只检查 SourceInventory（源码清单）、RunManifest（运行清单）、VerificationRun（验证运行）和 FinalEvidenceTable（最终证据表）之间的关系，不返回 `20-evidence` 产物计划。

优点：实现量最小。

不采用原因：backlog（待办）明确要求“汇入 `20-evidence`”。如果没有 bundle plan（证据包计划），后续 closeout（收尾）无法稳定引用 evidence bundle manifest（证据包清单）、source inventory export（源码清单导出）、verification runs export（验证运行导出）和 final evidence table export（最终证据表导出）。

## 3. 选型结论

采用方案 1：纯 WorkspaceEvidenceBundle（工作区证据包）装配计划。

该方案的核心判断是：V2-060E 应该证明“`10-project` 项目包装配与 `20-evidence` 证据包同步成立”，但不应提前承担文件系统物化职责。它只消费已经存在的 typed facts（类型化事实），构建 closeout-ready evidence bundle（可收尾证据包）和 deterministic artifact plan（确定性产物计划）；真实写文件留给后续 materializer（物化器）或 V2-080 proving scenario（证明场景）。

## 4. 目标

1. 新增 `WorkspaceEvidenceBundle`（工作区证据包）模型，表达 `20-evidence` 下可供 closeout（收尾）消费的证据包。
2. 新增 `EvidenceBundleArtifact`（证据包产物）模型，表达将导出的 logical artifact（逻辑产物）路径、类型、关联 refs（引用）和可审计 source refs（来源引用）。
3. 新增 `build_workspace_evidence_bundle()`（构建工作区证据包函数），从 WorkspaceManifest（工作区清单）、PackageAssembly（项目包装配结果）、SourceInventory（源码清单）、RunManifest（运行清单）、VerificationRun（验证运行）、VerifiedEvidence（已验证证据）和 FinalEvidenceTable（最终证据表）生成 deterministic bundle（确定性证据包）。
4. 证明 FinalEvidenceTable（最终证据表）缺 blocking criterion（阻塞验收项）或存在 missing/failed row（缺失/失败行）时不得导出 closeout-ready evidence（可收尾证据）。
5. 证明 SourceInventory（源码清单）缺 lineage（来源链）或 entries（条目）为空时不得导出。
6. 证明 VerificationRun（验证运行）非法构造、非 passed status（通过状态）或重复 verification_run_id（验证运行 ID）时不得导出。
7. 证明 SourceInventory（源码清单）、VerifiedEvidence（已验证证据）、VerificationRun（验证运行）和 FinalEvidenceTable（最终证据表）之间的 refs（引用）必须交叉闭合，不能出现 orphan evidence（孤儿证据）或 orphan run（孤儿验证运行）。
8. 证明所有 evidence bundle artifact paths（证据包产物路径）必须位于 `20-evidence` 下，不能写入 `10-project`、`00-boardroom`、`30-audit` 或框架 repo（仓库）布局。
9. 证明 happy path（正向路径）可以生成包含 source inventory（源码清单）、run manifest（运行清单）、verification runs（验证运行）、final evidence table（最终证据表）和 bundle manifest（证据包清单）的完整 evidence bundle（证据包）。

## 5. 非目标

V2-060E 不做以下事情：

1. 不创建 `20-evidence` 目录，不写 JSON 文件，不复制 stdout/stderr 内容。
2. 不运行 command（命令），不重新执行 CommandRunner（命令执行器）。
3. 不重新验证 EvidenceClaim（证据声明），不替代 EvidenceVerifier（证据验证器）或 FinalEvidenceTableBuilder（最终证据表构建器）。
4. 不重复 FinalEvidenceTable（最终证据表）已校验的 AcceptanceContract activeness（验收合同活跃性检查）；V2-060E 只消费已构建的 table（表）并校验其 complete（完成状态）和 rows（行）形状。
5. 不调用 git，不证明 final package commit（最终项目包提交）或 dirty status（脏状态）；这些属于 V2-070D GitVersionAudit（Git 版本审计）。
6. 不生成 closeout verdict（收尾结论）或 CloseoutPackage（收尾包）；这些属于 V2-070。
7. 不把 `run-manifest.json` 当作 provider-backed source artifact（模型产出的源码产物）补进 SourceInventory（源码清单）。
8. 不读取旧 runtime（旧运行时）、旧 workspace（旧工作区）或旧 evidence implementation（旧证据实现）。

## 6. 模块设计

### 6.1 新增文件

```text
src/boardroom_os/workspace/evidence_export.py
tests/proving/test_workspace_evidence_export.py
```

需要同步 `src/boardroom_os/workspace/__init__.py` 导出核心对象，保持 workspace package（工作区包）公开入口一致。

### 6.2 建议公开对象

```python
class WorkspaceEvidenceExportError(ValueError): ...

class WorkspaceEvidenceBundleRef(NonEmptyTextValue): ...
class EvidenceBundleArtifactPath(NonEmptyTextValue): ...

class EvidenceBundleArtifactKind(StrEnum):
    BUNDLE_MANIFEST = "bundle_manifest"
    SOURCE_INVENTORY = "source_inventory"
    RUN_MANIFEST = "run_manifest"
    VERIFICATION_RUNS = "verification_runs"
    FINAL_EVIDENCE_TABLE = "final_evidence_table"

class EvidenceBundleArtifact(BaseModel): ...
class WorkspaceEvidenceBundle(BaseModel): ...


def build_workspace_evidence_bundle(
    *,
    workspace_manifest: WorkspaceManifest,
    package_assembly: PackageAssembly,
    source_inventory: SourceInventory,
    run_manifest: RunManifest,
    verification_runs: tuple[VerificationRun, ...],
    verified_evidence: tuple[VerifiedEvidence, ...],
    final_evidence_table: FinalEvidenceTable,
) -> WorkspaceEvidenceBundle: ...
```

`WorkspaceEvidenceExportError`（工作区证据导出错误）用于 builder/service（构建器/服务）层的语义错误；Pydantic（Pydantic 模型）结构错误仍可抛 `ValidationError`（校验错误）。

## 7. Schema（结构）设计

### 7.1 EvidenceBundleArtifactPath（证据包产物路径）

路径必须满足：

1. 必须以 `workspace_manifest.evidence_root.value + "/"` 派生的 evidence root（证据根）前缀开头；当前 canonical value（规范值）为 `20-evidence`。
2. 必须是相对路径，禁止 absolute path（绝对路径）、Windows drive（Windows 盘符）、反斜杠、空 segment（空路径段）、`.`、`..` 和尾部斜杠。
3. 不得落入 `10-project/`、`00-boardroom/`、`30-audit/` 或框架 repo layout（仓库布局），例如 `src/boardroom_os`、`doc`、`scripts`、`examples`。
4. 必须命名具体文件，不表达目录。

建议首版固定产物路径：

```text
20-evidence/source-inventory/source-inventory.json
20-evidence/tests/verification-runs.json
20-evidence/tests/run-manifest.json
20-evidence/closeout/final-evidence-table.json
20-evidence/closeout/evidence-bundle-manifest.json
```

V2-060E 只占用以下 `closeout/` 子路径：

```text
20-evidence/closeout/final-evidence-table.json
20-evidence/closeout/evidence-bundle-manifest.json
```

`20-evidence/closeout/` 下其它命名（例如 closeout summary、gate report、git audit mirror）预留给 V2-070A / V2-070C / V2-070D，不在 V2-060E 中提前占用。

### 7.2 EvidenceBundleArtifact（证据包产物）

建议 schema：

```yaml
relative_path:
artifact_kind:
source_ref:
related_refs:
```

字段说明：

- `relative_path`：EvidenceBundleArtifactPath（证据包产物路径）。
- `artifact_kind`：EvidenceBundleArtifactKind（证据包产物类型）。
- `source_ref`：该导出产物来自的 typed fact ref（类型化事实引用），例如 `source_inventory_id`、`run_manifest_id`、`verification_run_id`、`final_evidence_table_id` 或 bundle id（证据包 ID）。
- `related_refs`：与产物相关的 refs（引用），例如 package contract ref（包合同引用）、workspace manifest ref（工作区清单引用）、verification run refs（验证运行引用）等。

不变量：

1. 每个 artifact path（产物路径）唯一。
2. 每个 artifact kind（产物类型）必须满足最小必需集合。
3. `source_ref` 和 `related_refs` 必须非空。
4. `artifact_kind` 与 path（路径）必须匹配，例如 `source_inventory` 只能导出到 `20-evidence/source-inventory/source-inventory.json`。
5. 任意 extra fields（额外字段）必须 fail closed（失败关闭）。

### 7.3 WorkspaceEvidenceBundle（工作区证据包）

建议 schema：

```yaml
workspace_evidence_bundle_id:
workspace_manifest_ref:
package_assembly_ref:
package_contract_ref:
source_inventory_ref:
run_manifest_ref:
final_evidence_table_ref:
verification_run_refs:
verified_evidence_refs:
artifacts:
closeout_ready:
```

字段说明：

- `workspace_evidence_bundle_id`：WorkspaceEvidenceBundleRef（工作区证据包引用），建议确定性 ID：`workspace-evidence-bundle.<workspace_manifest_ref>.<package_assembly_ref>.<final_evidence_table_ref>`。
- `workspace_manifest_ref`：WorkspaceManifestRef（工作区清单引用）。
- `package_assembly_ref`：PackageAssemblyRef（项目包装配引用）。
- `package_contract_ref`：ContractId（合同 ID），必须贯穿 workspace / package / source inventory / run manifest。
- `source_inventory_ref`：SourceInventoryRef（源码清单引用）。
- `run_manifest_ref`：RunManifestRef（运行清单引用）。
- `final_evidence_table_ref`：FinalEvidenceTableRef（最终证据表引用）。
- `verification_run_refs`：tuple of VerificationRunRef（验证运行引用集合），按 ref value（引用值）稳定排序。
- `verified_evidence_refs`：tuple of VerifiedEvidenceRef（已验证证据引用集合），按 ref value（引用值）稳定排序，必须与 FinalEvidenceTable（最终证据表）和 SourceInventory（源码清单）交叉闭合。
- `artifacts`：tuple of EvidenceBundleArtifact（证据包产物集合），按 path（路径）稳定排序。
- `closeout_ready`：bool（布尔值），必须由输入 facts（事实）派生；首版只有所有 required checks（必需检查）通过时为 `True`。

不变量：

1. `workspace_manifest.package_contract_ref == package_assembly.package_contract_ref == source_inventory.package_contract_ref == run_manifest.package_contract_ref`。
2. `workspace_manifest.workspace_manifest_id == package_assembly.workspace_manifest_ref == run_manifest.workspace_manifest_ref`。
3. `source_inventory.package_assembly_ref == package_assembly.package_assembly_id`。
4. `workspace_manifest.evidence_root.value` 必须作为 artifact path（产物路径）前缀来源；当前 canonical value（规范值）为 `20-evidence`，实现不得另起硬编码常量与 WorkspaceManifest（工作区清单）形成双源。
5. `final_evidence_table.complete is True`，且所有 rows（行）状态均为 `satisfied`；`complete` 必须已经由 FinalEvidenceTableBuilder（最终证据表构建器）或 FinalEvidenceTable（最终证据表）自身派生，不允许 V2-060E 调用方通过 bundle 输入覆盖。
6. `source_inventory.entries` 非空，每个 entry（条目）必须带 `sha256`、`producer_ticket_ref`、`producer_attempt_ref`、`acceptance_refs` 和 `evidence_refs`。
7. `verification_runs` 非空，每个 VerificationRun（验证运行）必须 `status == passed`，且 stdout_ref / stderr_ref / exit_code / runner_ref / environment_profile_ref / workspace_snapshot_ref 都存在。
8. `verification_run_refs` 必须唯一，并且 artifact plan（产物计划）必须覆盖全部 verification runs（验证运行）。
9. `verified_evidence` 非空，且 `verified_evidence_refs` 必须唯一。
10. INV-X1：`source_inventory.entries[*].evidence_refs` 的并集必须是 `final_evidence_table.rows[*].verified_evidence_refs` 并集的子集；SourceInventory（源码清单）不能声称被 FinalEvidenceTable（最终证据表）不承认的 evidence（证据）覆盖。
11. INV-X2：每个传入 VerificationRun（验证运行）必须被至少一个 VerifiedEvidence（已验证证据）的 `verification_run_refs` 引用，且该 VerifiedEvidence（已验证证据）必须出现在 FinalEvidenceTable（最终证据表）的 satisfied rows（满足行）或 SourceInventory（源码清单）entries 的 `evidence_refs` 中；不得把 orphan run（孤儿验证运行）打进 bundle（证据包）。
12. FinalEvidenceTable（最终证据表）引用的每个 VerifiedEvidenceRef（已验证证据引用）必须能在 `verified_evidence` 输入集合中找到，避免 orphan evidence（孤儿证据）。
13. RunManifest mirror（运行清单镜像）必须与 `10-project/run-manifest.json` 对应同一个 `run_manifest_id`，不能出现 `20-evidence/tests/run-manifest.json` 与 package artifact（项目包产物）分叉。
14. `artifacts` 必须包含 source inventory（源码清单）、run manifest（运行清单）、verification runs（验证运行集合）、final evidence table（最终证据表）和 bundle manifest（证据包清单）。
15. `closeout_ready` 不能由调用方自由传入；必须由 builder（构建函数）在所有校验通过后设置。

### 7.4 closeout_ready（可收尾）派生公式

V2-060E 不产出 partial bundle（部分证据包）。任一不变量失败时，builder（构建函数）直接 fail closed（失败关闭）并抛 `WorkspaceEvidenceExportError`（工作区证据导出错误），而不是返回 `closeout_ready=False`。成功返回时，`closeout_ready` 必须按以下公式派生为 `True`：

```python
closeout_ready = (
    final_evidence_table.complete is True
    and all(row.status == FinalEvidenceStatus.SATISFIED for row in final_evidence_table.rows)
    and bool(source_inventory.entries)
    and all(run.status == VerificationRunStatus.PASSED for run in verification_runs)
    and required_artifact_kinds_are_present
    and all_workspace_package_source_run_table_refs_match
    and source_inventory_evidence_refs_are_subset_of_final_table_refs
    and every_verification_run_is_referenced_by_verified_evidence
    and every_final_table_evidence_ref_resolves_to_verified_evidence
)
```

该公式中的最后三项对应 INV-X1 / INV-X2 / orphan evidence（孤儿证据）防御，是 V2-060E 阶段性收口的核心：缺口必须在 evidence bundle（证据包）装配时暴露，不能推迟到 V2-070 closeout（收尾）。

## 8. 数据流

```text
WorkspaceManifest（工作区清单，V2-060A）
PackageAssembly（项目包装配结果，V2-060B）
SourceInventory（源码清单，V2-060C）
RunManifest（运行清单，V2-060D）
VerificationRun（验证运行，V2-040D）
VerifiedEvidence（已验证证据，V2-050B）
FinalEvidenceTable（最终证据表，V2-050C）
  -> build_workspace_evidence_bundle（构建工作区证据包）
  -> WorkspaceEvidenceBundle（工作区证据包）
      -> V2-070 CloseoutGate（收尾门禁）
      -> V2-080 TinyPackageAssembly（微型项目包装配证明）
```

关键边界：

- SourceInventory（源码清单）证明 source lineage（源码来源链）。
- VerificationRun（验证运行）证明 command evidence（命令证据）来自 runner（执行器）。
- FinalEvidenceTable（最终证据表）证明 active AcceptanceContract（活跃验收合同）的 blocking criteria（阻塞验收项）已满足。
- VerifiedEvidence（已验证证据）连接 VerificationRun（验证运行）、SourceInventory（源码清单）和 FinalEvidenceTable（最终证据表）的 refs（引用），防止 orphan run（孤儿验证运行）或 orphan evidence（孤儿证据）。
- WorkspaceEvidenceBundle（工作区证据包）只证明这些事实被同步汇入 `20-evidence` 的 closeout-ready plan（可收尾计划），不替代任何上游 verifier（验证器）。

## 9. 错误处理

1. Pydantic models（Pydantic 模型）使用 `ConfigDict(frozen=True, extra="forbid")`，拒绝未知字段和运行时篡改。
2. path shape（路径形状）错误抛 `ValidationError`（校验错误）。
3. `build_workspace_evidence_bundle()`（构建工作区证据包函数）遇到语义错误时抛 `WorkspaceEvidenceExportError`（工作区证据导出错误）。
4. 错误信息应指出具体 invariant（不变量），例如 `final evidence table must be complete`、`source inventory entries must not be empty`、`verification run must have stdout and stderr refs`、`evidence artifact path must be under 20-evidence`。
5. 不提供 fallback（降级）、默认 verification run（验证运行）或 synthetic evidence（合成证据）。调用方必须传入真实上游事实。

## 10. 测试方案

新增测试文件：

```text
tests/proving/test_workspace_evidence_export.py
```

测试应遵循 negative tests first（负例优先）：先覆盖 backlog（待办）明确要求的三个失败场景，再补充 bundle artifact path（证据包产物路径）和 refs consistency（引用一致性）负例，最后写完整 happy path（正向路径）。

### 10.1 必须先写的 negative tests（负例测试）

1. FinalEvidenceTable（最终证据表）存在 missing row（缺失行）时，`build_workspace_evidence_bundle()` 必须失败。
2. FinalEvidenceTable（最终证据表）存在 failed row（失败行）时，必须失败。
3. FinalEvidenceTable（最终证据表）rows（行）为空或 complete（完成状态）与 rows 不一致时，必须 fail closed（失败关闭）。
4. SourceInventory（源码清单）entries（条目）为空时，必须失败。
5. SourceInventoryEntry（源码清单条目）缺 sha256（哈希）、producer_ticket_ref（生产任务引用）、producer_attempt_ref（生产尝试引用）、acceptance_refs（验收引用）或 evidence_refs（证据引用）时，必须失败。
6. SourceInventory（源码清单）与 PackageAssembly（项目包装配结果）的 package_assembly_ref（项目包装配引用）不一致时，必须失败。
7. VerificationRun（验证运行）非法 dict（字典）构造缺 stdout_ref（标准输出引用）或 stderr_ref（标准错误引用）时，应在 VerificationRun（验证运行）模型层失败；V2-060E builder（构建函数）边界负责拒绝重复 verification_run_id（验证运行 ID）、混入 failed status run（失败状态验证运行）和 orphan run（孤儿验证运行）。
8. VerificationRun（验证运行）status（状态）不是 `passed` 时，必须失败。
9. VerificationRun（验证运行）重复 verification_run_id（验证运行 ID）时，必须失败。
10. RunManifest（运行清单）与 WorkspaceManifest（工作区清单）或 PackageContract（包合同）引用不一致时，必须失败。
11. bundle artifact path（证据包产物路径）尝试写到 `10-project`、`00-boardroom`、`30-audit`、`src/boardroom_os`、`doc`、绝对路径或 `..` 时，必须失败。
12. 缺少 `20-evidence/closeout/evidence-bundle-manifest.json` 或其他必需 bundle artifact（证据包产物）时，必须失败。
13. SourceInventory（源码清单）提到的 evidence_ref（证据引用）不在 FinalEvidenceTable（最终证据表）的 `verified_evidence_refs` 中时，必须失败。
14. FinalEvidenceTable（最终证据表）引用的 verified_evidence_ref（已验证证据引用）无法在 `verified_evidence` 输入集合中解析时，必须失败。
15. VerificationRun（验证运行）不被任何 VerifiedEvidence（已验证证据）引用，或引用它的 VerifiedEvidence（已验证证据）不在 FinalEvidenceTable（最终证据表）/ SourceInventory（源码清单）链路中时，必须失败。
16. 调用方试图构造 `closeout_ready=True` 但缺必需 artifact（产物）或 evidence refs（证据引用）时，必须失败。

### 10.2 Happy path（正向路径）

1. tiny software package（微型软件包）已经拥有 WorkspaceManifest（工作区清单）、PackageAssembly（项目包装配结果）、SourceInventory（源码清单）、RunManifest（运行清单）、passed VerificationRun（通过验证运行）、VerifiedEvidence（已验证证据）和 complete FinalEvidenceTable（完整最终证据表）。
2. `build_workspace_evidence_bundle()`（构建工作区证据包函数）成功返回 WorkspaceEvidenceBundle（工作区证据包）。
3. bundle（证据包）绑定正确的 workspace_manifest_ref（工作区清单引用）、package_assembly_ref（项目包装配引用）、package_contract_ref（包合同引用）、source_inventory_ref（源码清单引用）、run_manifest_ref（运行清单引用）、verified_evidence_refs（已验证证据引用）和 final_evidence_table_ref（最终证据表引用）。
4. bundle artifacts（证据包产物）包含固定五类产物，并全部位于 `20-evidence` 下。
5. verification_run_refs（验证运行引用集合）按确定性顺序输出，重复构建得到相同 bundle id（证据包 ID）和 artifact order（产物顺序）。
6. `closeout_ready` 自动派生为 `True`，且不能在不满足条件时被调用方伪造。
7. `model_dump()`（模型导出）输出稳定、可审计，可供后续 V2-070 CloseoutGate（收尾门禁）直接引用。
8. happy path（正向路径）明确证明 SourceInventory（源码清单）的 evidence_refs（证据引用）、VerifiedEvidence（已验证证据）的 verification_run_refs（验证运行引用）和 FinalEvidenceTable（最终证据表）的 verified_evidence_refs（已验证证据引用）形成闭合链路。

## 11. 验收口径

V2-060E 完成后必须满足：

1. `src/boardroom_os/workspace/evidence_export.py` 存在，并定义 WorkspaceEvidenceBundle（工作区证据包）、EvidenceBundleArtifact（证据包产物）和 `build_workspace_evidence_bundle()`（构建工作区证据包函数）或等价入口。
2. `tests/proving/test_workspace_evidence_export.py` 存在，并覆盖 backlog（待办）明确要求的 negative tests（负例测试）：final evidence table 缺 blocking criterion（最终证据表缺阻塞验收项）、source inventory 缺 lineage（源码清单缺来源链）、verification runs 缺 stdout/stderr refs（验证运行缺标准输出/错误引用）时不得导出 closeout-ready evidence（可收尾证据）；同时覆盖 SourceInventory（源码清单）、VerifiedEvidence（已验证证据）、VerificationRun（验证运行）和 FinalEvidenceTable（最终证据表）的跨模型 refs（引用）闭合。
3. happy path（正向路径）证明 `20-evidence` evidence bundle plan（证据包计划）可供 closeout（收尾）消费。
4. 实现不创建目录、不写文件、不重新运行命令、不重新验证 evidence claim（证据声明）。
5. WorkspaceEvidenceBundle（工作区证据包）证明 package assembly（项目包装配）与 evidence assembly（证据装配）同步，不允许先交付后补证据。
6. 文档同步：完成实施后需按 backlog（待办）协议更新 `backlog.md`、`acceptance-criteria.md`、`doc/05-project-log/2026-05.md`；若只写本 spec（规格）则只需更新 `doc/04-implementation/INDEX.md`。

## 12. 同行评审关注点

请重点审查：

1. V2-060E 是否应保持纯 bundle plan（证据包计划），不真实写入 `20-evidence` 文件；本 spec 选择保持纯领域模型边界。
2. EvidenceBundleArtifactKind（证据包产物类型）首版固定五类是否足够支撑 V2-070 CloseoutGate（收尾门禁）：bundle manifest（证据包清单）、source inventory（源码清单）、run manifest（运行清单）、verification runs（验证运行）、final evidence table（最终证据表）。
3. 是否需要把 stdout/stderr refs（标准输出/标准错误引用）作为独立 artifact（产物）列出；本 spec 选择首版通过 VerificationRun（验证运行）引用它们，不复制输出内容。
4. SourceInventory（源码清单）、VerifiedEvidence（已验证证据）、VerificationRun（验证运行）和 FinalEvidenceTable（最终证据表）必须在 V2-060E 做 refs（引用）交叉闭合；本 spec 选择不把该检查推迟到 V2-070 CloseoutGate（收尾门禁），否则会违反“package assembly 与 evidence assembly 同步”的阶段口径。
5. 是否应该把 `run-manifest.json` 同时列入 `20-evidence/tests/run-manifest.json` 和 `10-project/run-manifest.json`；本 spec 选择 evidence bundle（证据包）可导出 run manifest mirror（运行清单镜像），但必须指向同一 `run_manifest_id`，不改变 V2-060D 的 `10-project` package artifact（项目包产物）语义。
6. `closeout_ready`（可收尾）是否应该是派生字段还是由调用方传入；本 spec 要求派生，防止调用方绕过 fail-closed（失败关闭）规则。
