# V2-070E CloseoutPackage（收尾包）同行评审 spec

## 1. 背景与现实场景

V2-070E 要处理的现实场景是：generated project package（生成项目包）已经完成 implementation（实施）、verification（验证）、source inventory（源码清单）、evidence export（证据导出）、checker review（检查者评审）、ReplayBundle（重放包）、ProcessAuditBundle（流程审计包）和 GitVersionAuditBundle（Git 版本审计包）之后，审计员仍然不能只看“这些材料分别存在”。他们需要一个最终封套回答：这一次 closeout（收尾）到底绑定的是哪个 gate result（门禁结果）、哪份 evidence table（证据表）、哪份源码清单、哪份重放材料、哪份流程审计、哪份 Git 版本审计，以及这些材料是否属于同一个最终版本。

通俗地说，本工作包要做的是“把已经验真的所有交付证明装进同一个不可错绑的结案袋”。CloseoutGate（收尾门禁）像最终放行章，ReplayBundle（重放包）像可复盘录像，ProcessAuditBundle（流程审计包）像人类审计报告，GitVersionAuditBundle（Git 版本审计包）像最终版本戳，SourceInventory（源码清单）和 FinalEvidenceTable（最终证据表）像交付物与验收映射。CloseoutPackage（收尾包）不重新盖章、不重新审计、不重新运行测试；它负责把这些已经成立的事实按同一项目、同一版本、同一门禁结果绑定在一起，防止“拿 A 项目的 Git 戳配 B 项目的 evidence table”这类错绑。

因此，最终成功不能由 workflow completed（流程完成）或某个 audit bundle（审计包）单独表达，必须由 `CloseoutGateResult(verdict="passed")`（通过的收尾门禁结果）与引用闭合的 `CloseoutPackage`（收尾包）共同表达；V2-070F CloseoutReducer（收尾归约器）后续只能消费这个包产生 terminal success projection（终态成功投影）。

本轮 Pre-flight（一致性预检）结论：`backlog.md`（待办）当前未完成工作包为 V2-070E；`acceptance-criteria.md`（验收标准）中 Phase 7 的 “CloseoutPackage 绑定一致” 仍未勾选；`src/boardroom_os/closeout/package.py` 与 `tests/closeout/test_closeout_package.py` 尚不存在；V2-070A/B/C/D 已完成并分别提供 CloseoutGate（收尾门禁）、ReplayBundle（重放包）、ProcessAuditBundle（流程审计包）与 GitVersionAuditBundle（Git 版本审计包）的 typed boundary（类型化边界）；当前状态与输出文件、验收 checkbox（一致性勾选项）一致，无 drift（漂移）。

## 2. 统一风格来源

### 2.1 V2-070A CloseoutGate（收尾门禁）的边界

V2-070A 已确定 CloseoutGate（收尾门禁）是 gate authority（门禁权威）：

1. 只消费 typed objects（类型化对象）和 readiness summaries（就绪摘要）。
2. 不访问 filesystem（文件系统）、不运行 git（Git 命令）、不重放 EventLog（事件日志）。
3. 业务不满足时返回 `CloseoutGateResult(verdict="blocked")` 和 typed blockers（类型化阻断项）。
4. gate pass/fail（门禁通过/失败）只能由 CloseoutGate（收尾门禁）表达，不能由 CloseoutPackage（收尾包）从 bundle（包）中二次推断。
5. 当前 `closeout_gate_result_id` 的确定性派生公式来自 `CloseoutGate.evaluate(...)`：`closeout-gate-result.{source_inventory_id}.{final_evidence_table_id}`。V2-070E 必须按此公式重算校验；若 V2-070A 后续公式变更，应以 V2-070A 的公开工厂/实现为唯一来源。

因此 V2-070E 不能把 CloseoutPackage（收尾包）做成第二个 gate（门禁）；它只能确认 gate result（门禁结果）确实指向当前 source inventory（源码清单）与 final evidence table（最终证据表）。

### 2.2 V2-070B ReplayBundle（重放包）的物化风格

V2-070B 已确定 ReplayBundle（重放包）不是临时 bool，而是 durable audit object（持久审计对象）：

1. 固定 `version: 1`。
2. 保存 EventRecord（事件记录）切片、attestation（证明条目）、payload manifest（载荷清单）、artifact manifest（产物清单）、hash manifest（哈希清单）和 replay report（重放报告）。
3. `replay_bundle_readiness(...)`（重放包就绪投影）会重算 hash closure（哈希闭合），再投影为 `ReplayBundleReadiness`（重放包就绪摘要）。
4. CloseoutGate（收尾门禁）消费 readiness summary（就绪摘要），而不是直接消费完整 bundle（包）。

因此 V2-070E 应同时绑定完整 ReplayBundle（重放包）和 CloseoutGate 已检查过的 ReplayBundleReadiness（重放包就绪摘要）字段，防止完整重放包与 gate 检查摘要错位。

### 2.3 V2-070C ProcessAuditBundle（流程审计包）的物化风格

V2-070C 已确定 ProcessAuditBundle（流程审计包）先在 typed object（类型化对象）层闭合：

1. 固定 `version: 1`。
2. 固定十项 `30-audit/` logical artifacts（逻辑产物）。
3. artifact manifest（产物清单）与 hash manifest（哈希清单）必须可重算。
4. readiness projection（就绪投影）重新验证 artifact contents（产物内容）、manifest（清单）、hash closure（哈希闭合）、timeline（时间线）、agent context index（智能体上下文索引）、artifact lineage（产物来源链）和 evidence map（证据映射）。
5. 当前 `30-audit/git-version-audit.md` 只用 `GitAuditReadiness`（Git 审计就绪摘要）渲染简表；V2-070D 已提供完整 GitVersionAuditBundle（Git 版本审计包），V2-070E 应补齐二者绑定。

因此 V2-070E 应升级 ProcessAuditBuilderInput（流程审计构建输入）为 required（必需）接收完整 GitVersionAuditBundle（Git 版本审计包），并校验它与 GitAuditReadiness（Git 审计就绪摘要）一致。

### 2.4 V2-070D GitVersionAuditBundle（Git 版本审计包）的边界

V2-070D 已确定 GitVersionAuditBundle（Git 版本审计包）是正式 durable audit object（持久审计对象）：

1. 固定 `version: 1`。
2. 包含 GitVersionAuditFactSet（Git 版本审计事实集）、GitCommandEvidenceBinding（Git 命令证据绑定）、GitVersionAuditReport（Git 版本审计报告）和 GitVersionAuditHashManifest（Git 版本审计哈希清单）。
3. `git_version_audit_readiness(...)`（Git 版本审计就绪投影）投影为 V2-070A 的 `GitAuditReadiness`（Git 审计就绪摘要）。
4. CloseoutGate（收尾门禁）仍只消费 GitAuditReadiness（Git 审计就绪摘要）。

因此 V2-070E 应把 GitVersionAuditBundle（Git 版本审计包）与 ReplayBundle（重放包）、ProcessAuditBundle（流程审计包）并列绑定，而不是让 ProcessAudit（流程审计）或 CloseoutPackage（收尾包）从 Git bundle（Git 包）里二次推导 gate verdict（门禁结论）。

## 3. 选项背景

### 3.1 方案 A：最小引用封套

只新增 CloseoutPackage（收尾包）schema，字段仅保存 `closeout_gate_result_ref`、`source_inventory_ref`、`final_evidence_table_ref`、`replay_bundle_ref`、`process_audit_bundle_ref` 和 `verdict`，校验缺字段与 verdict（结论）一致。

优点：实现最小，能快速满足 backlog（待办）中的“缺任一必需 ref 失败、verdict 与 gate 不一致失败”。

不采用原因：它无法证明 GitVersionAuditBundle（Git 版本审计包）与 ReplayBundle（重放包）、ProcessAuditBundle（流程审计包）三者并列绑定，也无法封堵 readiness summary（就绪摘要）与完整 bundle（包）错绑。审计员仍需跨文件手工确认 AC-V2-CLOSEOUT（收尾验收）完整覆盖。

### 3.2 方案 B：强一致引用封套 + ProcessAudit Git 集成升级

CloseoutPackage（收尾包）绑定 CloseoutGateResult（收尾门禁结果）、SourceInventory（源码清单）、FinalEvidenceTable（最终证据表）、ReplayBundle（重放包）、ProcessAuditBundle（流程审计包）和 GitVersionAuditBundle（Git 版本审计包），同时校验三类 readiness summary（就绪摘要）与完整 bundle（包）一致。ProcessAudit（流程审计）升级为用完整 GitVersionAuditBundle（Git 版本审计包）渲染 `30-audit/git-version-audit.md`，但 CloseoutGate（收尾门禁）仍只消费 GitAuditReadiness（Git 审计就绪摘要）。

优点：

- 与 V2-070A/B/C/D 的 typed bundle + readiness projection（类型化包 + 就绪投影）风格一致。
- 防止 gate result（门禁结果）、evidence table（证据表）、source inventory（源码清单）和三类 audit bundle（审计包）错绑。
- 让 `30-audit/git-version-audit.md` 从完整 Git 审计事实渲染，提升人类可读审计价值。
- 不产生双重 gate truth（双重门禁事实源）：Gate 仍消费 readiness summary（就绪摘要），Package 只做绑定一致性校验。

代价：需要更新现有 V2-070C ProcessAudit（流程审计）fixture（夹具）与测试预期；当前 `tests/closeout/test_process_audit.py` 和 `tests/closeout/test_process_audit_artifacts.py` 共 26 个 test functions（测试函数），按 V2-070C 完成证据对应约 41 个 test cases（pytest 参数化展开后的测试用例）需要回归。

### 3.3 方案 C：CloseoutPackage 内嵌所有 audit 内容

CloseoutPackage（收尾包）不仅引用 ReplayBundle（重放包）、ProcessAuditBundle（流程审计包）和 GitVersionAuditBundle（Git 版本审计包），还复制它们的核心 report/hash manifest（报告/哈希清单）内容。

优点：单个对象携带全部信息，读取方便。

不采用原因：会复制已有 bundle（包）的职责，产生 stale copy（陈旧副本）和双重事实源风险；也会让 CloseoutPackage（收尾包）变成第四个 audit bundle（审计包），偏离“最终封套”职责。

## 4. 选型结论

采用方案 B：强一致引用封套 + ProcessAudit Git 集成升级。

核心边界：

1. CloseoutGate（收尾门禁）仍是 pass/fail（通过/失败）的唯一门禁权威。
2. CloseoutPackage（收尾包）不重新执行 gate（门禁）、不重新验证 evidence（证据）、不重新生成 audit bundle（审计包）。
3. CloseoutPackage（收尾包）必须同时绑定 ReplayBundle（重放包）、ProcessAuditBundle（流程审计包）和 GitVersionAuditBundle（Git 版本审计包），三者并列存在，缺一不可。
4. CloseoutPackage（收尾包）必须校验 gate 已检查过的 readiness summary（就绪摘要）与完整 bundle（包）核心字段一致，但这些校验不能替代 CloseoutGate（收尾门禁）结论。
5. ProcessAudit（流程审计）在本轮升级为消费完整 GitVersionAuditBundle（Git 版本审计包）渲染 `30-audit/git-version-audit.md`，同时继续保留 GitAuditReadiness（Git 审计就绪摘要）一致性校验。
6. per-source-ticket Git audit（逐源码任务 Git 审计）不进入 V2-070E 主路径。若后续需要逐任务 Git history（Git 历史）或 per-ticket commit attribution（逐任务提交归因），应拆为 V2-070G 或后续工作包。

## 5. 目标

1. 新增 `src/boardroom_os/closeout/package.py`，定义 CloseoutPackage（收尾包）、CloseoutPackageBuilderInput（收尾包构建输入）、CloseoutPackageRef（收尾包引用）、CloseoutPackageVerdict（收尾包结论）和 builder（构建函数）。
2. 新增 `tests/closeout/test_closeout_package.py`，先写 negative tests（负例测试），再写 happy path（正向路径）。
3. CloseoutPackage（收尾包）必须绑定 CloseoutGateResult（收尾门禁结果）、SourceInventory（源码清单）、FinalEvidenceTable（最终证据表）、ReplayBundle（重放包）、ProcessAuditBundle（流程审计包）和 GitVersionAuditBundle（Git 版本审计包）。
4. Builder（构建函数）必须重算并校验 `closeout_gate_result_id`（收尾门禁结果 ID）与 V2-070A 当前派生公式一致。
5. Builder（构建函数）必须校验 ReplayBundleReadiness（重放包就绪摘要）、ProcessAuditReadiness（流程审计就绪摘要）、GitAuditReadiness（Git 审计就绪摘要）与对应完整 bundle（包）一致。
6. 修改 `src/boardroom_os/audit/process_audit.py`，让 ProcessAuditBuilderInput（流程审计构建输入）required（必需）接收 `git_version_audit_bundle: GitVersionAuditBundle`。
7. `30-audit/git-version-audit.md` 必须从完整 GitVersionAuditBundle（Git 版本审计包）渲染，包括 final commit（最终提交）、dirty status（脏状态）、source inventory hash（源码清单哈希）、command evidence refs（命令证据引用）、bundle/report/hash manifest refs（包/报告/哈希清单引用）。
8. 输出必须 audit-friendly JSON（审计友好 JSON），不得包含宿主绝对路径、Windows drive（Windows 盘符）、反斜杠路径、临时目录或旧实现路径。

## 6. 非目标

V2-070E 不做以下事情：

1. 不产生 terminal success projection（终态成功投影）；这属于 V2-070F CloseoutReducer（收尾归约器）。
2. 不重新执行 CloseoutGate（收尾门禁）。
3. 不重新验证 EvidenceClaim（证据声明）或 VerifiedEvidence（已验证证据）。
4. 不重新构建 SourceInventory（源码清单）、ReplayBundle（重放包）、ProcessAuditBundle（流程审计包）或 GitVersionAuditBundle（Git 版本审计包）。
5. 不读取旧 runtime（旧运行时）、旧 closeout state machine（旧收尾状态机）或旧 workflow completion（旧流程完成）。
6. 不实现 per-source-ticket Git audit（逐源码任务 Git 审计）或 per-ticket Git history（逐任务 Git 历史）。
7. 不把 ProcessAudit（流程审计）升级为 gate authority（门禁权威）；它仍只是人类可读审计包。
8. 不改变 CloseoutGate（收尾门禁）的公开 API（公开接口）或让其直接消费 GitVersionAuditBundle（Git 版本审计包）。

## 7. 模块设计

### 7.1 新增/修改文件

```text
src/boardroom_os/closeout/package.py
tests/closeout/test_closeout_package.py
src/boardroom_os/audit/process_audit.py
tests/closeout/test_process_audit.py
tests/closeout/test_process_audit_artifacts.py
```

必要时同步 public API（公开接口）导出：

```text
src/boardroom_os/closeout/__init__.py
src/boardroom_os/audit/__init__.py
```

### 7.2 建议公开对象

```python
class CloseoutPackageError(ValueError): ...

class CloseoutPackageRef(NonEmptyTextValue): ...
class CloseoutPackageCheckedRef(NonEmptyTextValue): ...

class CloseoutPackageVerdict(StrEnum):
    PASSED = "passed"
    FAILED = "failed"

class CloseoutPackage(BaseModel): ...
class CloseoutPackageBuilderInput(BaseModel): ...


def build_closeout_package(builder_input: CloseoutPackageBuilderInput) -> CloseoutPackage: ...
```

CloseoutPackage（收尾包）首版可以定义 `FAILED` 枚举值以保留 domain vocabulary（领域词汇），但 V2-070E builder happy path（构建正向路径）只允许从 passed CloseoutGateResult（通过的收尾门禁结果）构建 `verdict="passed"`。Blocked/failed closeout（阻断/失败收尾）由 CloseoutGateResult.blockers（收尾门禁阻断项）表达，不构建最终 CloseoutPackage（收尾包）。

## 8. Schema（结构）设计

### 8.1 CloseoutPackage（收尾包）

建议 schema：

```yaml
version: 1
closeout_package_id:
project_ref:
graph_version:
generated_at:
package_commit_ref:
verdict: passed | failed
closeout_gate_result_ref:
acceptance_summary_ref:
source_inventory_ref:
final_evidence_table_ref:
replay_bundle_ref:
process_audit_bundle_ref:
git_version_audit_bundle_ref:
checked_refs:
```

字段语义：

- `version` 固定为 `1`；任何非 1 版本必须 fail closed（失败关闭）。
- `closeout_package_id` 必须 deterministic（确定性），建议由 project_ref（项目引用）、gate result ref（门禁结果引用）、source inventory ref（源码清单引用）、final evidence table ref（最终证据表引用）和三个 bundle refs（包引用）的 canonical hash（规范哈希）派生。
- `project_ref` 来自 ReplayBundle（重放包）、ProcessAuditBundle（流程审计包）和 GitVersionAuditBundle（Git 版本审计包），三者必须一致。
- `graph_version` 是 closeout package（收尾包）生成时的最终 graph version（图版本），必须为正数，并不得小于 ReplayBundle（重放包）中 event window（事件窗口）的 last graph version。
- `package_commit_ref` 来自 `SourceInventory.package_commit_ref`（源码清单项目提交引用），并与 `GitVersionAuditBundle.report.package_commit_ref`（Git 版本审计报告项目提交引用）一致。
- `closeout_gate_result_ref` 指向唯一 `CloseoutGateResult`（收尾门禁结果）。
- `acceptance_summary_ref` 在 V1 中等同于 `FinalEvidenceTableRef`（最终证据表引用），不新增单独 summary artifact（摘要产物），避免双重事实源。
- `replay_bundle_ref`、`process_audit_bundle_ref`、`git_version_audit_bundle_ref` 是三个并列 audit bundle refs（审计包引用）。
- `checked_refs` 是 CloseoutPackage（收尾包）封装时确认过的关键事实引用集合，必须稳定去重且 audit-friendly（审计友好）。

### 8.2 CloseoutPackageBuilderInput（收尾包构建输入）

Builder input（构建输入）必须只接收 typed instances（类型化实例）：

```yaml
closeout_gate_result: CloseoutGateResult
source_inventory: SourceInventory
final_evidence_table: FinalEvidenceTable
replay_bundle: ReplayBundle
replay_readiness: ReplayBundleReadiness
process_audit_bundle: ProcessAuditBundle
process_audit_readiness: ProcessAuditReadiness
git_version_audit_bundle: GitVersionAuditBundle
git_audit_readiness: GitAuditReadiness
graph_version: int
generated_at: datetime
```

禁止 raw dict（原始字典）、scalar tuple refs（标量元组引用）或只传 ref string（引用字符串）绕过 typed validation（类型化校验）。

## 9. Validation（校验）规则

Builder（构建函数）与 model（模型）必须 fail closed（失败关闭）：

1. `version` 必须固定为 `1`；构造或反序列化时非 1 必须失败。
2. `generated_at` 必须带 timezone（时区）。
3. `graph_version` 必须为正数，且不得小于 ReplayBundle（重放包）证明的最后 graph version（图版本）。
4. `closeout_gate_result.verdict` 必须为 `passed`，且 blockers（阻断项）为空。
5. `CloseoutPackage.verdict` 必须与 `closeout_gate_result.verdict` 一致；V1 builder（第一版构建器）只允许生成 `passed`。
6. Builder 必须按 V2-070A 当前公式重算 `closeout_gate_result_id`：`closeout-gate-result.{source_inventory.source_inventory_id}.{final_evidence_table.final_evidence_table_id}`；输入 ID 不一致必须 fail closed。
7. `source_inventory.source_inventory_id` 必须等于 `source_inventory_ref`；`source_inventory.package_commit_ref` 必须匹配 `git_version_audit_bundle.report.package_commit_ref`。
8. `final_evidence_table.final_evidence_table_id` 必须同时作为 `final_evidence_table_ref` 与 `acceptance_summary_ref`。
9. `ReplayBundleReadiness.summary_hash`、`event_range`、`projection_versions` 必须被 `closeout_gate_result.checked_refs` 覆盖，并且与 ReplayBundle（重放包）attestation/report（证明条目/报告）一致。
10. `ProcessAuditReadiness.artifact_paths` 必须被 `closeout_gate_result.checked_refs` 覆盖，并且 ProcessAuditBundle（流程审计包）必须索引所有 10 项 `30-audit/` required artifacts（必需产物）。
11. `GitAuditReadiness.final_commit_sha`、`source_inventory_hash` 必须被 `closeout_gate_result.checked_refs` 覆盖，并且与 GitVersionAuditBundle（Git 版本审计包）的 `fact_set` / `report` 一致。
12. GitVersionAuditBundle（Git 版本审计包）、ReplayBundle（重放包）、ProcessAuditBundle（流程审计包）必须并列存在；缺任一 bundle ref（包引用）都不能构造 CloseoutPackage（收尾包）。
13. 三个 audit bundle（审计包）的 `project_ref` 必须一致。
14. `checked_refs` 不得为空、不得重复、不得包含空字符串，并且必须包含：gate result ref（门禁结果引用）、source inventory ref（源码清单引用）、final evidence table ref（最终证据表引用）、replay bundle ref（重放包引用）、process audit bundle ref（流程审计包引用）、git version audit bundle ref（Git 版本审计包引用）、git final commit（Git 最终提交）、source inventory hash（源码清单哈希）、replay summary hash（重放摘要哈希）、process audit artifact refs（流程审计产物引用）。
15. `model_dump(mode="json")` 不得包含宿主绝对路径、Windows drive（Windows 盘符）、反斜杠路径、`.pytest` 临时目录或旧实现路径。

## 10. GitVersionAuditBundle（Git 版本审计包）与 Gate readiness（门禁就绪摘要）边界

CloseoutGate（收尾门禁）的 Git 判断仍消费 `GitAuditReadiness`（Git 审计就绪摘要）。V2-070E 不改变 CloseoutGate API（收尾门禁接口），也不让 CloseoutPackage（收尾包）从 GitVersionAuditBundle（Git 版本审计包）反推出 gate pass（门禁通过）。

V2-070E 只做两类绑定：

1. Gate already checked（门禁已检查）的事实：`final_commit_sha`（最终提交）、`source_inventory_hash`（源码清单哈希）、final command evidence（最终命令证据）必须已经出现在 `CloseoutGateResult.checked_refs`。
2. Audit detail（审计详情）：完整 GitVersionAuditBundle（Git 版本审计包）必须作为最终收尾包的并列 audit bundle（审计包）引用，供人审和后续 package（包）读取详细事实。

如果 `git_version_audit_readiness(git_version_audit_bundle)`（Git 版本审计就绪投影）重新投影出的字段与传入 `git_audit_readiness`（Git 审计就绪摘要）不同，CloseoutPackage builder（收尾包构建函数）必须 fail closed（失败关闭）。该重新投影只用于 consistency check（一致性检查），不用于替代 CloseoutGate（收尾门禁）原始输入。

## 11. ProcessAudit（流程审计）升级

V2-070E 必须同步升级 ProcessAudit（流程审计）：

1. `ProcessAuditBuilderInput`（流程审计构建输入）新增 required（必需）字段 `git_version_audit_bundle: GitVersionAuditBundle`。
2. 缺该字段必须 fail closed（失败关闭）；不提供 optional fallback（可选降级）或默认空 Git 审计。
3. 现有 V2-070C fixture（夹具）需要更新：`tests/closeout/test_process_audit.py` 与 `tests/closeout/test_process_audit_artifacts.py` 的 helper（辅助函数）必须构造完整 GitVersionAuditBundle（Git 版本审计包）并传入 builder input（构建输入）。当前这两个文件共 26 个 test functions（测试函数），按 V2-070C 完成证据约 41 个 test cases（pytest 参数化展开后的测试用例）必须回归。
4. `30-audit/git-version-audit.md` 从 GitVersionAuditBundle（Git 版本审计包）渲染，而不是只从 GitAuditReadiness（Git 审计就绪摘要）渲染。
5. Markdown 至少包含：final commit SHA（最终提交 SHA）、dirty status（脏状态）、source inventory hash（源码清单哈希）、source inventory ref（源码清单引用）、package commit ref（项目包提交引用）、command evidence refs（命令证据引用）、git version audit bundle ref（Git 版本审计包引用）、git version audit report ref（Git 版本审计报告引用）、hash manifest ref（哈希清单引用）。
6. `ProcessAuditBuilderInput` 继续接收 `git_audit_readiness: GitAuditReadiness`（Git 审计就绪摘要），并校验 readiness（就绪摘要）与 bundle（包）核心字段一致。
7. `ProcessAuditBundle.checked_refs`（流程审计包检查引用）必须新增 `git_version_audit_bundle_id`、`git_version_audit_report_id`、`hash_manifest_id` 和 command evidence binding refs（命令证据绑定引用）。
8. ProcessAudit（流程审计）仍不是 gate authority（门禁权威）：它可以渲染完整 Git 审计细节，但不能决定 closeout passed（收尾通过）。

## 12. per-source-ticket Git audit（逐源码任务 Git 审计）处理

本轮不新增 per-source-ticket Git audit（逐源码任务 Git 审计）子系统，理由：

1. SourceInventory（源码清单）已经绑定每个文件的 `producer_ticket_ref`（生产任务引用）、`producer_attempt_ref`（生产模型调用尝试引用）、acceptance refs（验收引用）和 evidence refs（证据引用）。
2. GitVersionAuditBundle（Git 版本审计包）当前证明 final commit（最终提交）、source inventory hash（源码清单哈希）和 final command evidence（最终命令证据）。
3. “每个 source ticket 对应哪些 Git commits / diffs” 是新的 lineage dimension（来源链维度），需要额外 Git history model（Git 历史模型）和测试，不应混入 CloseoutPackage（收尾包）封套职责。

V2-070E 可以在评审关注点中保留此问题；如果后续确认需要，应新增 V2-070G，定义 PerTicketGitAuditBundle（逐任务 Git 审计包）或 SourceTicketGitLineage（源码任务 Git 来源链）。

## 13. 测试计划

### 13.1 CloseoutPackage negative tests（收尾包负例测试）

新增 `tests/closeout/test_closeout_package.py`，建议 test names（测试名）：

1. `test_closeout_package_requires_typed_builder_inputs`
   - 缺 `closeout_gate_result` / `source_inventory` / `final_evidence_table` / `replay_bundle` / `process_audit_bundle` / `git_version_audit_bundle` 任一 typed input（类型化输入）必须失败。
   - raw dict（原始字典）替代 typed instance（类型化实例）必须失败。

2. `test_closeout_package_rejects_scalar_tuple_refs`
   - `checked_refs`、projection versions（投影版本）或 artifact paths（产物路径）使用 scalar tuple refs（标量元组引用）绕过 typed refs（类型化引用）必须失败。

3. `test_closeout_package_rejects_blocked_gate_result`
   - `CloseoutGateResult(verdict="blocked")` 或带 blockers（阻断项）的 gate result（门禁结果）不能构建 CloseoutPackage（收尾包）。

4. `test_closeout_package_rejects_verdict_mismatch`
   - package verdict（包结论）与 gate verdict（门禁结论）不一致必须失败。

5. `test_closeout_package_rejects_non_v1_version`
   - `version != 1` 必须 fail closed（失败关闭）。

6. `test_closeout_package_recomputes_gate_result_id`
   - 按 V2-070A 当前公式重算 `closeout-gate-result.{source_inventory_id}.{final_evidence_table_id}`。
   - 输入 gate result id（门禁结果 ID）与重算值不一致必须失败。

7. `test_closeout_package_rejects_source_inventory_git_commit_mismatch`
   - `SourceInventory.package_commit_ref` 与 `GitVersionAuditBundle.report.package_commit_ref` 不一致必须失败。

8. `test_closeout_package_rejects_git_readiness_bundle_mismatch`
   - `GitAuditReadiness.final_commit_sha`、`source_inventory_hash`、`source_inventory_hash_matches` 或 `final_command_evidence_at_final_commit` 与 GitVersionAuditBundle（Git 版本审计包）不一致必须失败。

9. `test_closeout_package_rejects_replay_readiness_bundle_mismatch`
   - `ReplayBundleReadiness.summary_hash`、`event_range` 或 `projection_versions` 与 ReplayBundle（重放包）不一致必须失败。

10. `test_closeout_package_rejects_process_audit_readiness_gap`
    - `ProcessAuditReadiness.artifact_paths` 未覆盖十项 `30-audit/` required artifacts（必需产物）必须失败。

11. `test_closeout_package_rejects_gate_checked_refs_gap`
    - `CloseoutGateResult.checked_refs` 未覆盖 source inventory（源码清单）、final evidence table（最终证据表）、git readiness（Git 就绪摘要）、replay readiness（重放就绪摘要）或 process audit artifacts（流程审计产物）必须失败。

12. `test_closeout_package_rejects_project_ref_mismatch_across_bundles`
    - ReplayBundle（重放包）、ProcessAuditBundle（流程审计包）、GitVersionAuditBundle（Git 版本审计包）的 `project_ref` 不一致必须失败。

13. `test_closeout_package_rejects_naive_generated_at`
    - `generated_at` 无 timezone（时区）必须失败。

14. `test_closeout_package_rejects_unsafe_checked_refs_or_paths`
    - 输出或 checked_refs（检查引用）包含宿主绝对路径、Windows drive（Windows 盘符）、反斜杠路径、`.pytest` 临时目录或旧实现路径必须失败。

### 13.2 CloseoutPackage happy tests（收尾包正例测试）

1. `test_closeout_package_binds_passed_gate_and_all_audit_bundles`
   - 完整 typed input（类型化输入）可构建 `CloseoutPackage(verdict="passed")`。
   - package（包）指向 SourceInventory（源码清单）、FinalEvidenceTable（最终证据表）、ReplayBundle（重放包）、ProcessAuditBundle（流程审计包）和 GitVersionAuditBundle（Git 版本审计包）。

2. `test_closeout_package_checked_refs_are_stable_and_complete`
   - `checked_refs` 稳定、去重、可审计。
   - 包含 gate result（门禁结果）、三类 audit bundle refs（审计包引用）、git final commit（Git 最终提交）、source inventory hash（源码清单哈希）、replay summary hash（重放摘要哈希）和 process audit artifact refs（流程审计产物引用）。

3. `test_closeout_package_id_is_deterministic`
   - 相同输入重复构建得到相同 `closeout_package_id`。
   - 改变任一关键 ref（引用）后 ID 改变。

4. `test_closeout_package_dump_is_audit_friendly_json`
   - `model_dump(mode="json")` 成功。
   - 输出不含宿主绝对路径、Windows drive（Windows 盘符）、反斜杠路径、临时目录或旧实现路径。

### 13.3 ProcessAudit integration tests（流程审计集成测试）

同步更新现有 `tests/closeout/test_process_audit.py` 与 `tests/closeout/test_process_audit_artifacts.py`，建议新增或调整 test names（测试名）：

1. `test_process_audit_builder_input_requires_git_version_audit_bundle`
   - 缺 GitVersionAuditBundle（Git 版本审计包）必须失败。

2. `test_process_audit_rejects_git_version_audit_bundle_readiness_mismatch`
   - GitVersionAuditBundle（Git 版本审计包）与 GitAuditReadiness（Git 审计就绪摘要）核心字段不一致必须失败。

3. `test_process_audit_git_version_audit_markdown_renders_full_bundle`
   - `30-audit/git-version-audit.md` 必须包含 final commit（最终提交）、dirty status（脏状态）、source inventory hash（源码清单哈希）、command evidence refs（命令证据引用）和 bundle/report/hash manifest refs（包/报告/哈希清单引用）。

4. `test_process_audit_checked_refs_include_git_version_audit_bundle_refs`
   - ProcessAuditBundle.checked_refs（流程审计包检查引用）包含 git_version_audit_bundle_id、report id、hash manifest id 和 command binding refs。

5. `test_process_audit_existing_artifact_and_hash_manifest_regressions_still_pass`
   - 现有 10 项 `30-audit/` artifact（审计产物）、artifact manifest（产物清单）、hash manifest（哈希清单）、timeline（时间线）、evidence map（证据映射）和 replay report（重放报告）校验不回退。

### 13.4 回归边界

实施完成后应至少回归：

1. `tests/closeout/test_closeout_gate.py`，证明 CloseoutGate（收尾门禁）仍消费 readiness summaries（就绪摘要），没有改为直接消费 GitVersionAuditBundle（Git 版本审计包）。
2. `tests/negative/test_closeout_fail_closed.py`，证明缺 replay/process/git readiness（重放/流程/Git 就绪摘要）仍被 gate 阻断。
3. `tests/closeout/test_replay_bundle.py`，证明 ReplayBundle（重放包）hash closure（哈希闭合）不受 CloseoutPackage（收尾包）影响。
4. `tests/closeout/test_process_audit.py` 与 `tests/closeout/test_process_audit_artifacts.py`，证明 V2-070C 现有约 41 个 process audit cases（流程审计用例）在新增 GitVersionAuditBundle（Git 版本审计包）输入后仍通过。
5. `tests/closeout/test_git_version_audit.py`，证明 V2-070D GitVersionAuditBundle（Git 版本审计包）仍可独立构建并投影 readiness（就绪摘要）。
6. `tests/proving/test_source_inventory.py` 与 `tests/negative/test_source_inventory_ref_only_rejected.py`，证明 SourceInventory（源码清单）来源链语义未被 CloseoutPackage（收尾包）改写。
7. `tests/proving/test_run_manifest.py` 与 `tests/execution/test_command_runner.py`，证明 final command evidence（最终命令证据）仍来自 RunManifest（运行清单）与 CommandRunner（命令执行器）。

## 14. 验证命令

实施完成后建议运行：

```bash
PYTHONPATH="src;." python -m pytest tests/closeout/test_closeout_package.py -q
PYTHONPATH="src;." python -m pytest tests/closeout/test_closeout_package.py tests/closeout/test_closeout_gate.py tests/negative/test_closeout_fail_closed.py -q
PYTHONPATH="src;." python -m pytest tests/closeout/test_process_audit.py tests/closeout/test_process_audit_artifacts.py tests/closeout/test_git_version_audit.py tests/closeout/test_closeout_package.py -q
PYTHONPATH="src;." python -m pytest tests/closeout/test_replay_bundle.py tests/closeout/test_process_audit.py tests/closeout/test_process_audit_artifacts.py tests/closeout/test_git_version_audit.py tests/closeout/test_closeout_package.py -q
PYTHONPATH="src;." python -m pytest tests/proving/test_source_inventory.py tests/negative/test_source_inventory_ref_only_rejected.py tests/proving/test_run_manifest.py tests/execution/test_command_runner.py tests/closeout/test_closeout_package.py -q
PYTHONPATH="src;." python -m pytest tests/contracts tests/reducers tests/execution tests/evidence tests/proving tests/closeout tests/negative -q
```

其中第一条证明 V2-070E 自身；第二条证明 V2-070A/E gate-package chain（门禁-收尾包链）一致；第三条证明 V2-070C/D/E 在 ProcessAudit（流程审计）与 GitVersionAudit（Git 版本审计）集成后不回退；第四条证明 V2-070B/C/D/E closeout audit bundles（收尾审计包）并列绑定且各自 hash closure（哈希闭合）不回退；第五条证明 V2-060C/D 和 V2-040D 边界未被 CloseoutPackage（收尾包）改写；第六条作为全量回归。

## 15. 完成后文档同步

实现完成并通过验证后，必须按 `backlog.md` 的工作包完成更新协议同步：

1. `doc/04-implementation/backlog.md`
   - V2-070E 状态改为 DONE。
   - 顶部“当前未完成工作包”指向 V2-070F。
   - Phase 7 进度从 4 / 6 改为 5 / 6；总计数字以实施当时 backlog 为准。
2. `doc/04-implementation/acceptance-criteria.md`
   - 勾选 Phase 7 的 “CloseoutPackage 绑定一致”。
   - 勾选时必须引用 `tests/closeout/test_closeout_package.py` 对缺必需 ref、verdict/gate mismatch、GitVersionAuditBundle / ReplayBundle / ProcessAuditBundle 并列绑定、readiness/bundle mismatch 的证明。
3. `doc/05-project-log/2026-05.md`
   - 追加 V2-070E 完成记录，包含关键产出文件、negative/happy tests（负例/正例测试）和真实验证命令证据。
4. `doc/05-project-log/decisions.md`
   - 仅当实现中改变 CloseoutGate（收尾门禁）权威边界、让 CloseoutPackage（收尾包）直接决定 passed/blocked、或把 per-source-ticket Git audit（逐源码任务 Git 审计）纳入 V2-070E 主路径时才新增决策。按本 spec 实施不需要新增 DEC。
5. `doc/04-implementation/INDEX.md`
   - 本 spec 文件已加入索引；若新增 implementation plan（实施计划）文档，应同步追加。
6. `doc/04-implementation/acceptance-criteria.md` 抽象 AC 段
   - 仅当本轮改变 AC-V2-CLOSEOUT-001/002/003 语义时同步。按本 spec 实施只闭合 Phase 7 checkbox，不改变抽象 AC 语义。

## 16. 评审关注点

1. 是否同意 CloseoutPackage（收尾包）定位为“强一致引用封套”，而不是第四个 audit bundle（审计包）。
2. 是否同意 CloseoutGate（收尾门禁）仍是唯一 pass/fail authority（通过/失败权威）。
3. 是否同意 CloseoutPackage builder（收尾包构建函数）重算 `closeout_gate_result_id`，并以 V2-070A 当前公式为准。
4. 是否同意 `acceptance_summary_ref` 在 V1 中等同于 FinalEvidenceTableRef（最终证据表引用），不新增单独 summary artifact（摘要产物）。
5. 是否同意 GitVersionAuditBundle（Git 版本审计包）与 ReplayBundle（重放包）、ProcessAuditBundle（流程审计包）并列绑定，缺一不可。
6. 是否同意 GitAuditReadiness（Git 审计就绪摘要）继续作为 CloseoutGate（收尾门禁）输入，CloseoutPackage（收尾包）只做一致性校验，不二次产生 gate truth（门禁事实）。
7. 是否同意 ProcessAuditBuilderInput（流程审计构建输入）新增 required GitVersionAuditBundle（必需 Git 版本审计包），并同步更新现有 V2-070C fixture（夹具）与约 41 个 process audit test cases（流程审计测试用例）。
8. 是否同意 `30-audit/git-version-audit.md` 从完整 GitVersionAuditBundle（Git 版本审计包）渲染，而不是只渲染 readiness summary（就绪摘要）。
9. 是否同意 per-source-ticket Git audit（逐源码任务 Git 审计）不进入 V2-070E，后续如需拆 V2-070G。
10. 是否同意 V2-070E 不修改 CloseoutGate（收尾门禁）公开 API，也不提前实现 V2-070F CloseoutReducer（收尾归约器）。

## 17. 完成判定

V2-070E 完成时：

1. `CloseoutPackage`（收尾包）是最终完成的唯一 package-level expression（包级表达）。
2. CloseoutGate（收尾门禁）仍是 pass/fail（通过/失败）的唯一门禁权威。
3. GitVersionAuditBundle（Git 版本审计包）、ReplayBundle（重放包）、ProcessAuditBundle（流程审计包）并列绑定，且不产生双重 readiness source（就绪事实源）。
4. ProcessAudit（流程审计）能用完整 GitVersionAuditBundle（Git 版本审计包）渲染 `30-audit/git-version-audit.md`。
5. `closeout_gate_result_id`（收尾门禁结果 ID）、package_commit_ref（项目包提交引用）、readiness summaries（就绪摘要）和完整 bundles（完整包）之间的一致性由测试证明。
6. Negative tests first（负例先行）与 happy path（正向路径）测试通过，且完整 closeout（收尾）相关回归通过。
