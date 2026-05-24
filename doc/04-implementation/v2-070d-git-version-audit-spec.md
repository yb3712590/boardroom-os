# V2-070D GitVersionAudit（Git 版本审计）同行评审 spec

## 1. 背景与现实场景

V2-070D 要处理的现实场景是：generated project package（生成项目包）已经完成 implementation（实施）、verification（验证）、source inventory（源码清单）、evidence export（证据导出）、checker review（检查者评审）、ReplayBundle（重放包）和 ProcessAudit（流程审计）构建后，审计员还不能只相信“测试通过了”或“流程审计文件存在”。他们需要证明最终交付包到底对应哪个 Git commit（Git 提交）、当时 package workspace（项目包工作区）是不是 clean（干净）、SourceInventory（源码清单）有没有被篡改、最终 run/test command evidence（运行/测试命令证据）是不是就在这个最终 commit 上运行。

通俗地说，本工作包要做的是“给最终交付包盖一个 Git 版本戳，并证明这个戳没被乱贴”。V2-070A 的 CloseoutGate（收尾门禁）已经定义 `GitAuditReadiness`（Git 审计就绪摘要）；V2-070D 要补上正式的 GitVersionAudit（Git 版本审计）对象、hash closure（哈希闭合）和 readiness projection（就绪投影），让 closeout（收尾）可以证明最终版本是什么。

本轮 Pre-flight（一致性预检）结论：`backlog.md`（待办）当前未完成工作包为 V2-070D；`acceptance-criteria.md`（验收标准）中 Phase 7 的 “Git version audit 完整” 仍未勾选；`src/boardroom_os/adapters/git_audit.py`、`src/boardroom_os/audit/git_version_audit.py` 和 `tests/closeout/test_git_version_audit.py` 尚不存在；V2-070A/B/C 已完成并提供 CloseoutGate（收尾门禁）readiness contract（就绪合同）、ReplayBundle（重放包）和 ProcessAuditBundle（流程审计包）的统一风格，状态一致，无 drift（漂移）。

## 2. 统一风格来源

### 2.1 V2-070A CloseoutGate（收尾门禁）的边界

V2-070A 已确定 CloseoutGate（收尾门禁）是纯 domain gate（领域门禁）：

1. 只消费 typed objects（类型化对象）和 readiness summaries（就绪摘要）。
2. 不访问 filesystem（文件系统）。
3. 不运行 git。
4. 不重放 EventLog（事件日志）。
5. 不生成 audit artifacts（审计产物）。
6. 业务不满足时返回 `CloseoutGateResult(verdict="blocked")` 和 typed blockers（类型化阻断项）。
7. 输入结构非法、raw dict（原始字典）或 scalar tuple（标量元组）等结构问题必须 fail closed（失败关闭）。

因此 V2-070D 不能把 git 执行逻辑塞进 CloseoutGate（收尾门禁）；它必须构建正式 GitVersionAudit（Git 版本审计）对象，并投影为 V2-070A 已定义的 `GitAuditReadiness`（Git 审计就绪摘要）。

### 2.2 V2-070B ReplayBundle（重放包）的物化风格

V2-070B 已确定 ReplayBundle（重放包）不是临时 bool，而是 durable audit artifact schema（持久审计产物结构）：

1. `ReplayBundle` 有固定 `version: 1`。
2. 所有逻辑产物通过 manifest entry（清单条目）表达。
3. 每个 entry 有 content/ref（内容/引用）和 sha256（哈希）。
4. `ReplayHashManifest`（重放哈希清单）会重新计算 event window（事件窗口）、payload manifest（载荷清单）、artifact manifest（产物清单）、replay report（重放报告）和 attestation（证明条目）hash。
5. `replay_bundle_readiness(...)`（重放包就绪投影）会重新校验 bundle 本体和 hash closure（哈希闭合），而不是信任传入的 ready bool。
6. 不引入未实现的插件框架，不提前定义未来 projection kind（投影类型）。

因此 V2-070D 也必须把 Git audit（Git 审计）表达成正式 bundle/report/facts（包/报告/事实），并由 readiness projection（就绪投影）重新校验。

### 2.3 V2-070C ProcessAudit（流程审计）的物化风格

V2-070C 已确定 ProcessAuditBundle（流程审计包）先在 typed object（类型化对象）层闭合：

1. 固定 `version: 1`。
2. 固定十项 `30-audit/` logical artifacts（逻辑产物）。
3. artifact manifest（产物清单）与 hash manifest（哈希清单）必须可重算。
4. builder（构建器）只消费 typed V2 facts（类型化 V2 事实），不读取旧 runtime（旧运行时），不从 raw dict 猜状态。
5. readiness projection（就绪投影）重新验证 artifact contents（产物内容）、manifest（清单）、hash closure（哈希闭合）、timeline（时间线）、agent context index（智能体上下文索引）、artifact lineage（产物来源链）和 evidence map（证据映射）。
6. `git-version-audit.md` 在 V2-070C 中只消费 `GitAuditReadiness`（Git 审计就绪摘要）或后续 GitVersionAudit（Git 版本审计）事实，不运行真实 git。

因此 V2-070D 应提供正式 GitVersionAudit（Git 版本审计）事实，供 V2-070E CloseoutPackage（收尾包）和后续 process audit 集成绑定；但本轮不反向改造 ProcessAudit（流程审计）职责边界。

## 3. 选项背景

### 3.1 方案 A：只生成 GitAuditReadiness（Git 审计就绪摘要）

V2-070D 只提供一个函数，把调用方传来的 final commit SHA（最终提交 SHA）、git clean（Git 干净状态）、source inventory hash（源码清单哈希）和 final command bool（最终命令布尔值）转成 V2-070A 的 `GitAuditReadiness`（Git 审计就绪摘要）。

优点：实现最小，能快速让 CloseoutGate（收尾门禁） happy path（正向路径）消费。

不采用原因：这与 V2-070B/C 的物化风格不统一。它只能证明“调用方声称 Git 状态就绪”，不能证明 Git facts（Git 事实）、diff summary（差异摘要）、source inventory canonical hash（源码清单规范哈希）和 command evidence binding（命令证据绑定）本身可归档、可重算、可审计。

### 3.2 方案 B：GitAuditAdapter（Git 审计适配器）直接返回 readiness

V2-070D 实现一个 adapter（适配器）运行 `git status`、`git rev-parse`、`git diff` 等命令，并直接返回 `GitAuditReadiness`（Git 审计就绪摘要）。

优点：贴近真实仓库状态，调用路径短。

不采用原因：这会把 fact collection（事实采集）、domain validation（领域校验）、hash closure（哈希闭合）和 readiness projection（就绪投影）混在一起。V2-070A/B/C 的统一边界是：adapter 或 builder 收集/构建事实，正式 typed object（类型化对象）先闭合，再投影为 readiness summary（就绪摘要）。

### 3.3 方案 C：GitVersionAuditBundle（Git 版本审计包）+ typed Git facts（类型化 Git 事实）+ readiness projection（就绪投影）

V2-070D 定义正式 `GitVersionAuditBundle`（Git 版本审计包），包含 Git fact set（Git 事实集）、source inventory hash proof（源码清单哈希证明）、final command evidence proof（最终命令证据证明）、git audit report（Git 审计报告）、hash manifest（哈希清单）和 checked refs（已检查引用）。`GitAuditAdapter`（Git 审计适配器）只作为薄采集层，把真实 git 状态转为 typed facts；核心校验全部在 `boardroom_os.audit.git_version_audit`（Git 版本审计领域模块）中完成。

优点：

- 与 V2-070B ReplayBundle（重放包）和 V2-070C ProcessAuditBundle（流程审计包）风格统一。
- Git audit（Git 审计）成为 durable audit object（持久审计对象），而不是几个易伪造 bool。
- CloseoutGate（收尾门禁）继续只消费 `GitAuditReadiness`（Git 审计就绪摘要）。
- adapter（适配器）可以被替换或测试，不影响领域校验。
- negative tests（负例测试）可以精确覆盖 dirty package（脏项目包）、source inventory hash mismatch（源码清单哈希不匹配）、final commands not at final commit（最终命令不是在最终提交运行）等 backlog 要求。

代价：

- 比方案 A/B 多一层 bundle/report/hash manifest schema（包/报告/哈希清单结构）。
- 首版需要定义 command evidence commit binding（命令证据提交绑定）的最小结构。
- 需要小心不把本轮扩展成完整 Git 操作框架。

## 4. 选型结论

采用方案 C：GitVersionAuditBundle（Git 版本审计包）+ typed Git facts（类型化 Git 事实）+ readiness projection（就绪投影）。

核心边界：

1. V2-070D 构建正式 GitVersionAuditBundle（Git 版本审计包），不是只构建 `GitAuditReadiness`（Git 审计就绪摘要）。
2. GitVersionAuditBundle 是 durable audit artifact schema（持久审计产物结构），可 dump JSON、可重新校验 hash closure（哈希闭合）。
3. `GitAuditAdapter`（Git 审计适配器）只采集 final commit SHA（最终提交 SHA）、dirty status（脏状态）、changed files（变更文件）、diff summary（差异摘要）和 optional tag（可选标签）等 Git facts（Git 事实）。
4. builder（构建器）只消费 typed V2 facts（类型化 V2 事实）和 typed Git facts（类型化 Git 事实），不读取旧 runtime（旧运行时），不从 raw dict（原始字典）猜测状态。
5. builder 不创建 CloseoutPackage（收尾包）、不推进 reducer terminal success（归约器终态成功）、不生成 ProcessAudit（流程审计）十项产物。
6. readiness projection（就绪投影）必须重新校验 GitVersionAuditBundle（Git 版本审计包）内容、source inventory hash（源码清单哈希）、final commit binding（最终提交绑定）、command evidence commit binding（命令证据提交绑定）和 hash manifest（哈希清单）。
7. CloseoutGate（收尾门禁）仍然只消费 V2-070A 已有的 `GitAuditReadiness`（Git 审计就绪摘要）。

## 5. 目标

1. 新增 `src/boardroom_os/audit/git_version_audit.py`，定义 GitVersionAuditBundle（Git 版本审计包）、GitVersionAuditFactSet（Git 版本审计事实集）、GitVersionAuditReport（Git 版本审计报告）、GitVersionAuditHashManifest（Git 版本审计哈希清单）、GitCommandEvidenceBinding（Git 命令证据绑定）和 builder/readiness projection（构建器/就绪投影）。
2. 新增 `src/boardroom_os/adapters/git_audit.py`，定义 GitAuditAdapter（Git 审计适配器）和可测试的 command transport（命令传输）边界。
3. 新增 `tests/closeout/test_git_version_audit.py`，先写 fail-closed negative tests（失败关闭负例测试），再写 happy path（正向路径）。
4. GitVersionAuditBundle 必须记录 final package commit（最终项目包提交）、dirty status（脏状态）、changed files（变更文件）、diff summary（差异摘要）、source inventory hash（源码清单哈希）、source inventory hash match（源码清单哈希匹配）和 final command evidence（最终命令证据）。
5. SourceInventory（源码清单）必须通过 canonical JSON hash（规范 JSON 哈希）重新计算，并与 GitVersionAuditFactSet（Git 版本审计事实集）中的 source inventory hash 比对。
6. SourceInventory.package_commit_ref（源码清单包提交引用）必须与 final commit SHA（最终提交 SHA）指向同一版本。
7. 每个 final VerificationRun（最终验证运行）必须有 GitCommandEvidenceBinding（Git 命令证据绑定），证明 command evidence（命令证据）绑定到 final commit（最终提交）。
8. GitVersionAuditBundle 必须提供 `git_version_audit_readiness(...)`，投影为 V2-070A 的 `GitAuditReadiness`（Git 审计就绪摘要）。
9. 输出必须 audit-friendly JSON（审计友好 JSON），不得包含宿主绝对路径、Windows drive（Windows 盘符）、反斜杠路径、临时目录或旧实现路径。
10. 测试必须证明 dirty package、source inventory hash mismatch、final command evidence not at final commit、package commit mismatch、hash manifest mismatch、raw dict input 都会 fail closed。

## 6. 非目标

V2-070D 不做以下事情：

1. 不修改 V2-070A CloseoutGate（收尾门禁）的职责边界。
2. 不重新构建 ReplayBundle（重放包）；那属于 V2-070B。
3. 不生成 ProcessAuditBundle（流程审计包）或十项 `30-audit/` artifact（审计产物）；那属于 V2-070C。
4. 不创建 CloseoutPackage（收尾包）；最终绑定 gate result（门禁结果）、replay bundle（重放包）、process audit（流程审计）和 git audit（Git 审计）属于 V2-070E。
5. 不推进 closeout reducer（收尾归约器）或 terminal success（终态成功）；这属于 V2-070F。
6. 不读取旧 runtime（旧运行时）、旧 closeout state machine（旧收尾状态机）或旧 workflow completion（旧工作流完成）。
7. 不实现通用 Git hosting integration（Git 托管集成）、remote push（远端推送）、tag creation（标签创建）或 PR 操作。
8. 不把 dirty status（脏状态）、placeholder hash（占位哈希）、synthetic command evidence（合成命令证据）或 fallback（降级）当成可通过审计的证据。
9. 不改造 `VerificationRun`（验证运行）基础 schema；首版用外层 GitCommandEvidenceBinding（Git 命令证据绑定）证明运行对应 final commit。
10. 不把 GitAuditAdapter（Git 审计适配器）做成决策者；adapter 只采集事实，不决定 readiness（就绪）。

## 7. 模块设计

### 7.1 新增文件

```text
src/boardroom_os/audit/git_version_audit.py
src/boardroom_os/adapters/git_audit.py
tests/closeout/test_git_version_audit.py
```

需要同步 `src/boardroom_os/audit/__init__.py` 导出核心对象；如果 `src/boardroom_os/adapters/__init__.py` 已存在，应追加 Git audit（Git 审计）相关导出，不破坏现有 adapter（适配器）。

### 7.2 建议公开对象

`GitAuditReadiness`（Git 审计就绪摘要）、`GitCommitSha`（Git 提交 SHA）和 `SourceInventoryHash`（源码清单哈希）必须从 `boardroom_os.closeout.gate` 复用，不得在 `boardroom_os.audit.git_version_audit` 中定义 shadow type（影子类型）。

```python
class GitVersionAuditError(ValueError): ...

class GitVersionAuditBundleRef(NonEmptyTextValue): ...
class GitVersionAuditReportRef(NonEmptyTextValue): ...
class GitVersionAuditManifestRef(NonEmptyTextValue): ...
class GitVersionAuditContentHash(NonEmptyTextValue): ...
class GitVersionAuditCheckedRef(NonEmptyTextValue): ...
class GitTagRef(NonEmptyTextValue): ...
class GitBranchRef(NonEmptyTextValue): ...
class GitWorktreeRef(NonEmptyTextValue): ...
class GitDiffSummaryRef(NonEmptyTextValue): ...

class GitDirtyStatus(StrEnum):
    CLEAN = "clean"
    DIRTY = "dirty"

class GitChangedFileStatus(StrEnum):
    ADDED = "added"
    MODIFIED = "modified"
    DELETED = "deleted"
    RENAMED = "renamed"
    UNTRACKED = "untracked"

class GitChangedFile(BaseModel): ...
class GitDiffSummary(BaseModel): ...
class GitVersionAuditFactSet(BaseModel): ...
class GitCommandEvidenceBinding(BaseModel): ...
class GitVersionAuditReport(BaseModel): ...
class GitVersionAuditHashManifest(BaseModel): ...
class GitVersionAuditBundle(BaseModel): ...
class GitVersionAuditBuilderInput(BaseModel): ...


def build_git_version_audit_bundle(builder_input: GitVersionAuditBuilderInput) -> GitVersionAuditBundle: ...
def git_version_audit_readiness(bundle: GitVersionAuditBundle) -> GitAuditReadiness: ...
def source_inventory_hash(source_inventory: SourceInventory) -> SourceInventoryHash: ...
```

Adapter（适配器）建议公开对象：

```python
class GitAuditAdapterError(ValueError): ...
class GitCommandResult(BaseModel): ...
class GitCommandTransport(Protocol): ...
class GitAuditAdapter: ...  # Pydantic model 或 plain class，任选一种并保持可注入
```

也可以用函数式 adapter（适配器）入口，只要保持可注入 command transport（命令传输）并避免测试依赖真实当前仓库。

## 8. Schema（结构）设计

### 8.1 GitVersionAuditFactSet（Git 版本审计事实集）

建议 schema：

```yaml
fact_set_id:
project_ref:
package_root:
branch_ref:
worktree_ref:
base_commit_sha:
final_commit_sha:
optional_tag_ref:
dirty_status: clean | dirty
git_clean: true
changed_files:
  - ...
diff_summary:
source_inventory_hash:
generated_at:
```

字段说明：

- `fact_set_id`：确定性 ID，建议 `git-version-audit-facts.<project_ref>.<final_commit_sha>`。
- `project_ref`：ProjectRef（项目引用），必须与 builder input（构建输入）一致。
- `package_root`：generated project package root（生成项目包根），必须是 audit-friendly relative path（审计友好相对路径），通常为 `10-project`。
- `branch_ref`：最终 package 所在分支引用。
- `worktree_ref`：最终 package 所在 worktree（工作树）逻辑引用，不是宿主绝对路径。
- `base_commit_sha`：构建或审计起点提交。
- `final_commit_sha`：最终 package commit（最终项目包提交）。
- `optional_tag_ref`：可选 tag（标签），首版允许为空。
- `dirty_status` / `git_clean`：必须一致；clean 才能通过 readiness projection（就绪投影）。
- `changed_files`：相对路径变更清单；clean happy path 可为空，dirty 负例必须表达脏文件。
- `diff_summary`：diff（差异）摘要，不能包含完整敏感内容或宿主绝对路径。
- `source_inventory_hash`：对 SourceInventory（源码清单）重新计算的规范哈希。
- `generated_at`：带时区 datetime（日期时间）。

不变量：

1. `generated_at` 必须带 timezone（时区）。
2. `final_commit_sha` 必须是 40 位小写 hex SHA-1；后续若支持 SHA-256 Git repo，应另行扩展，不在首版猜测。
3. `base_commit_sha` 必须是 40 位小写 hex SHA-1。
4. `source_inventory_hash` 必须是 64 位小写 sha256 hex digest。
5. `package_root`、`branch_ref`、`worktree_ref`、`optional_tag_ref` 不得是 host absolute path（宿主绝对路径）、Windows drive（Windows 盘符）、反斜杠路径、`.`、`..` 或尾部斜杠。
6. `dirty_status == clean` 时 `git_clean` 必须为 true，且 `changed_files` 必须为空。
7. `dirty_status == dirty` 时 `git_clean` 必须为 false，且 `changed_files` 必须非空。
8. `changed_files.path` 必须是 package-root-relative（包根相对）或 repo-relative（仓库相对）审计友好路径。
9. 任意 extra fields（额外字段）必须 fail closed（失败关闭）。

### 8.2 GitChangedFile（Git 变更文件）

建议 schema：

```yaml
path:
status: added | modified | deleted | renamed | untracked
previous_path:
```

不变量：

1. path 必须非空。
2. path 不得是 absolute path（绝对路径）、Windows drive（Windows 盘符）、反斜杠路径、`.`、`..` 或尾部斜杠。
3. status 为 renamed（重命名）时 previous_path 必须存在且审计友好。
4. status 非 renamed 时 previous_path 必须为空。
5. dirty fact set（脏事实集）必须至少有一个 changed file（变更文件）。

### 8.3 GitDiffSummary（Git 差异摘要）

建议 schema：

```yaml
diff_summary_id:
changed_file_count:
insertions:
deletions:
summary_text:
```

不变量：

1. `changed_file_count` 必须等于 changed_files 数量。
2. clean fact set（干净事实集）时 insertions/deletions 必须为 0，summary_text 可为 `clean working tree`。
3. dirty fact set（脏事实集）时 changed_file_count 必须大于 0。
4. summary_text 不得为空，不得包含宿主绝对路径、Windows drive 或反斜杠路径。

### 8.4 GitCommandEvidenceBinding（Git 命令证据绑定）

V2-070D 需要证明 final command evidence（最终命令证据）不是任意 VerificationRun（验证运行），而是在 final commit（最终提交）对应版本运行过。

建议 schema：

```yaml
binding_id:
verification_run_ref:
run_manifest_ref:
package_contract_ref:
command_id:
command:
cwd:
workspace_snapshot_ref:
commit_sha:
source_inventory_hash:
```

字段说明：

- `verification_run_ref`：VerificationRunRef（验证运行引用），必须能在 builder input 的 `verification_runs` 中解析。
- `run_manifest_ref`：RunManifestRef（运行清单引用），必须等于输入 RunManifest（运行清单）。
- `package_contract_ref`：ContractId（合同 ID），必须等于输入 PackageContract / RunManifest（包合同/运行清单）。
- `command_id` / `command` / `cwd`：必须与 VerificationRun（验证运行）和 RunManifest declared command（运行清单声明命令）一致。
- `workspace_snapshot_ref`：必须等于 VerificationRun.workspace_snapshot_ref（验证运行工作区快照引用）。
- `commit_sha`：必须等于 GitVersionAuditFactSet.final_commit_sha（Git 版本审计事实集最终提交）。
- `source_inventory_hash`：必须等于 GitVersionAuditFactSet.source_inventory_hash（Git 版本审计事实集源码清单哈希）。

不变量：

1. `verification_run_ref` 不得重复。
2. 每个 final VerificationRun（最终验证运行）必须恰好有一条 binding。
3. binding 的 command_id、command、cwd 必须与 VerificationRun 一致。
4. binding 的 command_id、command、cwd 必须能在 RunManifest（运行清单）声明命令中解析。
5. binding.commit_sha 必须等于 fact_set.final_commit_sha。
6. binding.source_inventory_hash 必须等于 fact_set.source_inventory_hash。
7. 任意 final command evidence 不在 final commit 运行必须 fail closed。

### 8.5 GitVersionAuditReport（Git 版本审计报告）

建议 schema：

```yaml
git_version_audit_report_id:
project_ref:
generated_at:
fact_set_ref:
final_commit_sha:
package_commit_ref:
source_inventory_ref:
source_inventory_hash:
source_inventory_hash_matches:
git_clean:
final_command_evidence_at_final_commit:
command_evidence_refs:
checked_refs:
```

不变量：

1. `generated_at` 必须带 timezone（时区）。
2. `package_commit_ref` 必须与 final_commit_sha 指向同一版本；首版沿用 V2-070A 规则：等于 raw SHA 或 `package-commit.<sha>`。
3. source_inventory_hash 必须等于重新计算的 SourceInventory（源码清单）规范哈希。
4. `source_inventory_hash_matches` 必须由 builder 计算，不接受调用方任意传入。
5. `git_clean` 必须来自 fact set（事实集）。
6. `final_command_evidence_at_final_commit` 必须由 command evidence bindings（命令证据绑定）计算。
7. `checked_refs` 必须包含 package contract、source inventory、run manifest、verification runs、command bindings、final commit SHA 和 source inventory hash。
8. `checked_refs` 必须非空且唯一。

### 8.6 GitVersionAuditHashManifest（Git 版本审计哈希清单）

建议 schema：

```yaml
hash_manifest_id:
project_ref:
fact_set_hash:
report_hash:
command_binding_hashes:
  verification-run-ref: sha256...
bundle_payload_hash:
```

字段说明：

- `fact_set_hash`：对 GitVersionAuditFactSet canonical JSON（规范 JSON）计算。
- `report_hash`：对 GitVersionAuditReport canonical JSON 计算。
- `command_binding_hashes`：每条 GitCommandEvidenceBinding canonical JSON hash。
- `bundle_payload_hash`：对 GitVersionAuditBundle 稳定字段计算。

不变量：

1. fact_set_hash 必须可从 fact set 重新计算。
2. report_hash 必须可从 report 重新计算。
3. command_binding_hashes 必须覆盖全部 final command evidence bindings，且不能有 orphan binding hash（孤儿绑定哈希）。
4. bundle_payload_hash 必须可从 bundle 稳定字段重新计算。
5. 任意 hash missing（哈希缺失）、placeholder hash（占位哈希）或 mismatch（不匹配）必须 fail closed。

### 8.7 GitVersionAuditBundle（Git 版本审计包）

建议 schema：

```yaml
version: 1
git_version_audit_bundle_id:
project_ref:
generated_at:
fact_set:
command_evidence_bindings:
report:
hash_manifest:
checked_refs:
bundle_hash:
```

字段说明：

- `version`：首版固定为 `1`。
- `git_version_audit_bundle_id`：确定性 ID，建议由 project_ref（项目引用）、final commit SHA（最终提交 SHA）和 bundle hash（包哈希）派生。
- `project_ref`：ProjectRef（项目引用），必须与 fact set/report 一致。
- `generated_at`：带 timezone datetime（带时区日期时间）。
- `fact_set`：GitVersionAuditFactSet（Git 版本审计事实集）。
- `command_evidence_bindings`：GitCommandEvidenceBinding（Git 命令证据绑定）集合。
- `report`：GitVersionAuditReport（Git 版本审计报告）。
- `hash_manifest`：GitVersionAuditHashManifest（Git 版本审计哈希清单）。
- `checked_refs`：审计过程中检查过的引用集合。
- `bundle_hash`：computed field（计算字段），对稳定 payload 计算。

不变量：

1. `version == 1`。
2. `generated_at` 必须带 timezone（时区）。
3. fact set、report、hash manifest 的 project_ref 必须一致。
4. command_evidence_bindings 必须非空且 verification_run_ref 唯一。
5. report 的 final_commit_sha、source_inventory_hash、git_clean 和 command evidence verdict 必须与 fact set / bindings 一致。
6. checked_refs 必须非空且唯一。
7. hash_manifest 必须与 fact_set、report、bindings 和 bundle payload 一致。
8. 任意 extra fields（额外字段）必须 fail closed（失败关闭）。

## 9. Builder（构建器）输入

建议 schema：

```yaml
project_ref:
generated_at:
package_contract:
source_inventory:
run_manifest:
verification_runs:
command_evidence_bindings:
git_facts:
```

字段说明：

- `project_ref`：ProjectRef（项目引用）。
- `generated_at`：带 timezone datetime（带时区日期时间）。
- `package_contract`：PackageContract（包合同）。
- `source_inventory`：SourceInventory（源码清单）。
- `run_manifest`：RunManifest（运行清单）。
- `verification_runs`：tuple[VerificationRun, ...]（验证运行集合）。
- `command_evidence_bindings`：tuple[GitCommandEvidenceBinding, ...]（Git 命令证据绑定集合）。
- `git_facts`：GitVersionAuditFactSet（Git 版本审计事实集），可由 GitAuditAdapter（Git 审计适配器）采集，也可在测试中显式构造。

输入不变量：

1. 所有 tuple/list 字段必须是真的 tuple/list，不接受 scalar string（标量字符串）。
2. 所有 typed object 字段必须是 Pydantic model（Pydantic 模型）或已定义值对象，不接受 raw dict（原始字典）。
3. project_ref 必须与 git_facts 一致。
4. generated_at 必须带 timezone（时区）。
5. verification_runs 不可为空，且必须全部 status passed（通过）且 exit_code 为 0。
6. command_evidence_bindings 必须与 verification_runs 一一对应。
7. source inventory package_contract_ref 必须等于 package_contract.package_contract_id。
8. run manifest package_contract_ref 必须等于 package_contract.package_contract_id。
9. source inventory package_commit_ref 必须与 git_facts.final_commit_sha 指向同一版本。
10. git_facts.source_inventory_hash 必须等于重新计算的 source inventory canonical hash。
11. git_facts.git_clean 必须为 true 才能得到 passed readiness（通过就绪）。

## 10. Builder 语义

### 10.1 构建流程

```text
GitAuditAdapter.collect(...)（Git 审计适配器采集，可选）
  -> GitVersionAuditFactSet（Git 版本审计事实集）
  -> GitVersionAuditBuilderInput（Git 版本审计构建输入）
  -> validate typed refs and command bindings（校验类型化引用与命令绑定）
  -> recompute SourceInventory canonical hash（重算源码清单规范哈希）
  -> build GitVersionAuditReport（构建 Git 版本审计报告）
  -> compute hash manifest（计算哈希清单）
  -> build GitVersionAuditBundle（构建 Git 版本审计包）
  -> git_version_audit_readiness(bundle)（投影为 Git 审计就绪摘要）
```

### 10.2 SourceInventory hash（源码清单哈希）

建议规则：

1. 使用 `source_inventory.model_dump(mode="json")` 得到 JSON payload（JSON 载荷）。
2. 使用 `json.dumps(..., sort_keys=True, separators=(",", ":"), ensure_ascii=False)` 生成 canonical JSON（规范 JSON）。
3. 对 UTF-8 bytes（UTF-8 字节）计算 sha256。
4. 生成 `SourceInventoryHash`（源码清单哈希）。

该函数必须 deterministic（确定性），同一 SourceInventory（源码清单）重复计算得到相同 hash；不得读取 filesystem（文件系统）或 git。

### 10.3 Hash determinism（哈希确定性）

建议规则：

1. Pydantic model（Pydantic 模型）使用 `model_dump(mode="json")` 后 canonical JSON。
2. tuple/list（元组/列表）按输入顺序参与 hash；需要稳定排序的集合在 builder 中排序后写入模型。
3. `bundle_hash` 和 `bundle_payload_hash` 必须排除 computed field（计算字段）后重新计算。
4. 所有 hash 必须是 64 位小写 sha256 hex digest。
5. placeholder hash（占位哈希，如同一字符重复 64 次）不得满足 hash manifest（哈希清单）。

### 10.4 Readiness projection（就绪投影）

`git_version_audit_readiness(bundle)` 必须执行：

1. 重新校验 GitVersionAuditBundle（Git 版本审计包）结构。
2. 重新计算 fact_set_hash（事实集哈希）、report_hash（报告哈希）、command_binding_hashes（命令绑定哈希）和 bundle_payload_hash（包载荷哈希）。
3. 校验 fact set（事实集）为 clean（干净）。
4. 校验 SourceInventory hash（源码清单哈希）已匹配。
5. 校验 final command evidence（最终命令证据）全部在 final commit（最终提交）运行。
6. 返回 V2-070A `GitAuditReadiness`（Git 审计就绪摘要）。

返回字段映射：

```yaml
git_clean: bundle.fact_set.git_clean
final_commit_sha: bundle.fact_set.final_commit_sha
source_inventory_hash: bundle.fact_set.source_inventory_hash
source_inventory_hash_matches: bundle.report.source_inventory_hash_matches
final_command_evidence_at_final_commit: bundle.report.final_command_evidence_at_final_commit
```

该函数不得只读取 bundle 中已有 bool；必须重新验证后再投影。

## 11. GitAuditAdapter（Git 审计适配器）语义

### 11.1 Adapter 边界

GitAuditAdapter（Git 审计适配器）只负责采集 Git facts（Git 事实）：

1. final commit SHA（最终提交 SHA）。
2. branch_ref（分支引用）。
3. worktree logical ref（工作树逻辑引用）。
4. dirty status（脏状态）。
5. changed files（变更文件）。
6. diff summary（差异摘要）。
7. optional tag（可选标签）。

Adapter 不负责：

1. 不构造 GitAuditReadiness（Git 审计就绪摘要）。
2. 不调用 CloseoutGate（收尾门禁）。
3. 不修改 git repository（Git 仓库）。
4. 不创建 tag（标签）、commit（提交）、push（推送）或 checkout（检出）。
5. 不读取旧 runtime（旧运行时）。
6. 不决定 dirty 是否可以豁免。

### 11.2 Command transport（命令传输）

为了可测试，adapter 应通过可注入 transport（传输）执行命令：

```python
class GitCommandTransport(Protocol):
    def run(self, command: tuple[str, ...], *, cwd: str) -> GitCommandResult: ...
```

`GitCommandResult`（Git 命令结果）至少包含：

```yaml
command:
cwd:
exit_code:
stdout:
stderr:
```

不变量：

1. adapter 只允许执行只读 git 命令，例如 `rev-parse`、`status --porcelain`、`diff --stat`、`tag --points-at`。
2. transport 层可接收宿主绝对 cwd（当前目录）用于执行命令，但产出的 GitVersionAuditFactSet（Git 版本审计事实集）必须归一化为审计友好的逻辑路径（如 `10-project`）；宿主绝对路径绝不进入 typed object（类型化对象）。
3. 任一 git command exit_code 非 0 必须 fail closed（失败关闭），抛出 GitAuditAdapterError（Git 审计适配器错误）。
4. adapter 输出必须归一化为 audit-friendly refs（审计友好引用），不泄漏宿主绝对路径。

## 12. Fail-closed（失败关闭）规则

### 12.1 模型层必须失败的情况

1. GitVersionAuditBundle 缺 `fact_set`、`command_evidence_bindings`、`report` 或 `hash_manifest`。
2. GitVersionAuditBundle.version 不是 `1`。
3. generated_at 无 timezone（时区）。
4. final_commit_sha 或 base_commit_sha 不是 40 位小写 hex SHA-1。
5. source_inventory_hash 不是 64 位小写 sha256 hex digest。
6. source_inventory_hash 是 placeholder / synthetic hash（占位/合成哈希）。
7. changed_files 不是 tuple/list。
8. dirty_status 与 git_clean 不一致。
9. dirty_status 为 clean 但 changed_files 非空。
10. dirty_status 为 dirty 但 changed_files 为空。
11. changed file path 不安全。
12. diff summary 与 changed_files 数量不一致。
13. command_evidence_bindings 不是 tuple/list、为空或 verification_run_ref 重复。
14. checked_refs 为空或重复。
15. 任意 extra fields（额外字段）。

### 12.2 Builder validation（构建器校验）必须失败的情况

1. builder input 传 raw dict 替代 typed model。
2. builder input tuple/list 字段传 scalar string。
3. project_ref 与 git_facts 不一致。
4. generated_at 无 timezone（时区）。
5. verification_runs 为空。
6. verification run status 不是 passed 或 exit_code 不是 0。
7. command_evidence_bindings 未覆盖全部 verification_runs。
8. command_evidence_bindings 含 verification_runs 中不存在的孤儿 binding。
9. binding command_id / command / cwd 与 VerificationRun 不一致。
10. binding command_id / command / cwd 不属于 RunManifest（运行清单）声明命令。
11. binding.commit_sha 不等于 final_commit_sha。
12. binding.source_inventory_hash 不等于 git_facts.source_inventory_hash。
13. source inventory package_contract_ref 与 package_contract 不一致。
14. run manifest package_contract_ref 与 package_contract 不一致。
15. source inventory package_commit_ref 与 final_commit_sha 不一致。
16. 重新计算的 SourceInventory hash 与 git_facts.source_inventory_hash 不一致。
17. git_facts.git_clean 为 false。
18. hash manifest 中任意 hash 与 bundle 内容重算结果不一致。

### 12.3 Readiness projection（就绪投影）必须失败的情况

1. GitVersionAuditBundle 本身结构非法。
2. hash manifest 无法重新验证。
3. fact set 不是 clean。
4. source inventory hash 不匹配。
5. final command evidence 没有全部绑定 final commit。
6. report 与 fact set / bindings 不一致。
7. 返回的 GitAuditReadiness（Git 审计就绪摘要）缺任一 V2-070A 必需字段。

### 12.4 Adapter（适配器）必须失败的情况

1. git command exit_code 非 0。
2. git status 输出无法解析。
3. git rev-parse 输出不是合法 commit SHA。
4. changed file path 不安全。
5. diff stat 输出无法形成稳定 summary。
6. adapter 试图执行写操作命令，例如 commit、tag create、push、checkout、reset、clean。

## 13. 测试计划

测试文件：

```text
tests/closeout/test_git_version_audit.py
```

### 13.1 Negative tests first（负例优先）

必须先写以下负例，并在实现前得到预期 RED（红灯），例如 `ModuleNotFoundError: No module named 'boardroom_os.audit.git_version_audit'` 或缺对应类：

1. `test_git_version_audit_rejects_dirty_package`
2. `test_git_version_audit_rejects_source_inventory_hash_mismatch`
3. `test_git_version_audit_rejects_final_command_not_at_final_commit`
4. `test_git_version_audit_rejects_source_inventory_package_commit_mismatch`
5. `test_git_version_audit_rejects_missing_command_evidence_binding`
6. `test_git_version_audit_rejects_orphan_command_evidence_binding`
7. `test_git_version_audit_rejects_command_binding_not_declared_in_run_manifest`
8. `test_git_version_audit_rejects_failed_verification_run`
9. `test_git_version_audit_rejects_hash_manifest_mismatch`
10. `test_git_version_audit_rejects_raw_dict_inputs`
11. `test_git_version_audit_rejects_scalar_tuple_inputs`
12. `test_git_version_audit_rejects_naive_generated_at`
13. `test_git_version_audit_rejects_placeholder_source_inventory_hash`
14. `test_git_audit_adapter_rejects_git_command_failure`
15. `test_git_audit_adapter_rejects_write_git_commands`

这些测试应覆盖 backlog V2-070D 明确要求：dirty package（脏项目包）、source inventory hash mismatch（源码清单哈希不匹配）、final commands not at final commit（最终命令不是最终提交运行）必须失败。

### 13.2 Happy path（正向路径）

建议覆盖：

1. `test_git_version_audit_bundle_records_clean_final_version`
   - 构造 PackageContract（包合同）、SourceInventory（源码清单）、RunManifest（运行清单）、passed VerificationRun（通过的验证运行）和 GitVersionAuditFactSet（Git 版本审计事实集）。
   - 调用 `build_git_version_audit_bundle(...)`。
   - 断言 bundle.version == 1。
   - 断言 final commit SHA、package commit ref、source inventory hash、command evidence refs 全部闭合。

2. `test_git_version_audit_readiness_matches_closeout_gate_contract`
   - 调用 `git_version_audit_readiness(bundle)`。
   - 断言返回类型为 V2-070A `GitAuditReadiness`（Git 审计就绪摘要）。
   - 断言 git_clean true、source_inventory_hash_matches true、final_command_evidence_at_final_commit true。

3. `test_git_version_audit_recomputes_source_inventory_hash_deterministically`
   - 同一 SourceInventory（源码清单）重复 hash 得到同一值。
   - 修改任一 inventory entry 后 hash 改变。

4. `test_git_version_audit_hash_manifest_closes_bundle_payload`
   - 断言 fact_set_hash、report_hash、command_binding_hashes 和 bundle_payload_hash 都可重算。
   - 篡改 report 或 binding 后 readiness projection 必须失败。

5. `test_git_version_audit_bundle_is_audit_friendly_json`
   - `model_dump(mode="json")` 成功。
   - 输出不含 `C:/`、`D:/`、反斜杠、`.pytest_tmp`、旧 runtime 路径。
   - 重复构建产生稳定 bundle id/hash。

6. `test_git_audit_adapter_collects_git_facts_from_transport`
   - 使用 fake transport（假命令传输）模拟只读 git 命令输出。
   - 断言 adapter 产出 GitVersionAuditFactSet（Git 版本审计事实集）。
   - 不依赖当前仓库真实状态。

### 13.3 回归边界

实施完成后应至少回归：

1. `tests/closeout/test_closeout_gate.py`，证明 V2-070A CloseoutGate（收尾门禁）仍消费 `GitAuditReadiness`。
2. `tests/negative/test_closeout_fail_closed.py`，证明 dirty git / source inventory mismatch / final command not final 仍被 gate 阻断。
3. `tests/closeout/test_process_audit.py`，证明 V2-070C ProcessAudit（流程审计）仍可用 readiness fact 渲染 `git-version-audit.md`。
4. `tests/proving/test_source_inventory.py` 和 `tests/negative/test_source_inventory_ref_only_rejected.py`，证明 SourceInventory（源码清单）来源链语义未被 Git 审计改写。
5. `tests/proving/test_run_manifest.py` 和 `tests/execution/test_command_runner.py`，证明 final command evidence（最终命令证据）仍来自 RunManifest（运行清单）与 CommandRunner（命令执行器）。

## 14. 验证命令

实施完成后建议运行：

```bash
PYTHONPATH="src;." python -m pytest tests/closeout/test_git_version_audit.py -q
PYTHONPATH="src;." python -m pytest tests/closeout/test_git_version_audit.py tests/closeout/test_closeout_gate.py tests/negative/test_closeout_fail_closed.py -q
PYTHONPATH="src;." python -m pytest tests/closeout/test_process_audit.py tests/closeout/test_process_audit_artifacts.py tests/closeout/test_git_version_audit.py -q
PYTHONPATH="src;." python -m pytest tests/proving/test_source_inventory.py tests/negative/test_source_inventory_ref_only_rejected.py tests/proving/test_run_manifest.py tests/execution/test_command_runner.py tests/closeout/test_git_version_audit.py -q
PYTHONPATH="src;." python -m pytest tests/contracts tests/reducers tests/execution tests/evidence tests/proving tests/closeout tests/negative -q
```

其中第一条证明 V2-070D 自身；第二条证明 V2-070A/D closeout git audit chain（收尾 Git 审计链）一致；第三条证明 V2-070C 与 Git readiness（Git 就绪摘要）集成未回退；第四条证明 V2-060C/D 和 V2-040D 边界未回退；第五条作为全量回归。

## 15. 完成后文档同步

实现完成并通过验证后，必须按 `backlog.md` 的工作包完成更新协议同步：

1. `doc/04-implementation/backlog.md`
   - V2-070D 状态改为 DONE。
   - 顶部“当前未完成工作包”指向 V2-070E。
   - Phase 7 进度从 3 / 6 改为 4 / 6；总计数字以实施当时 backlog 为准。
2. `doc/04-implementation/acceptance-criteria.md`
   - 勾选 Phase 7 的 “Git version audit 完整”。
   - 勾选时必须引用 `tests/closeout/test_git_version_audit.py` 对 dirty package、source inventory hash mismatch、final commands not at final commit 的证明。
3. `doc/05-project-log/2026-05.md`
   - 追加 V2-070D 完成记录，包含关键产出文件、negative/happy tests（负例/正例测试）和真实验证命令证据。
4. `doc/05-project-log/decisions.md`
   - 仅当实现中改变 V2-070A/B/C 已确定边界、把 GitAuditAdapter（Git 审计适配器）变成 readiness 决策者、或改造 VerificationRun（验证运行）基础 schema 时才新增决策。按本 spec 实施不需要新增 DEC。
5. `doc/04-implementation/INDEX.md`
   - 本 spec 文件加入索引。

## 16. 评审关注点

1. 是否同意 V2-070D 采用 GitVersionAuditBundle（Git 版本审计包），而不是只生成 GitAuditReadiness（Git 审计就绪摘要）。
2. 是否同意 GitAuditAdapter（Git 审计适配器）只采集 Git facts（Git 事实），不决定 readiness（就绪）。
3. 是否同意核心校验全部放在 `boardroom_os.audit.git_version_audit`（Git 版本审计领域模块）。
4. 是否同意 SourceInventory hash（源码清单哈希）使用 canonical JSON（规范 JSON）重新计算。
5. 是否同意首版 final commit SHA（最终提交 SHA）只接受 40 位小写 SHA-1。
6. 是否同意首版不改造 VerificationRun（验证运行）基础 schema，而用 GitCommandEvidenceBinding（Git 命令证据绑定）证明 command evidence（命令证据）运行于 final commit（最终提交）。
7. 是否同意 dirty package（脏项目包）没有豁免路径，必须 fail closed（失败关闭）。
8. 是否同意 hash manifest（哈希清单）必须重新校验 fact set、report、command bindings 和 bundle payload。
9. 是否同意 adapter 测试使用 fake transport（假命令传输），不依赖当前仓库真实状态。
10. 是否同意 V2-070D 不提前创建 CloseoutPackage（收尾包）或推进 CloseoutReducer（收尾归约器）。
