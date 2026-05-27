# V2-071D Git audit hardening（同行评审 spec）

## 1. 背景与现实场景

V2-071D 处理的是最终收尾前的 Git version audit（Git 版本审计）场景：generated project package（生成项目包）已经有 SourceInventory（源码清单）、RunManifest（运行清单）、VerificationRun（验证运行）和 GitVersionAuditBundle（Git 版本审计包），但外部审计发现 GitAuditAdapter（Git 审计适配器）与 GitVersionAudit（Git 版本审计）仍存在四类风险：

1. `base_commit_sha`（基线提交）和 `worktree_ref`（工作树引用）缺失时被 silent fallback（隐式降级）为看似有效值。
2. `git status --porcelain` 使用换行文本解析，特殊文件名可能被误读。
3. `git diff --stat` 统计用未锚定 regex（正则表达式）解析全文，文件名可能污染 insertions/deletions（新增/删除行数）。
4. `verification_runs`（验证运行）和 `command_evidence_bindings`（命令证据绑定）按调用方输入顺序进入 `command_evidence_refs`（命令证据引用）、`checked_refs`（已检查引用）和 `bundle_payload_hash`（包载荷哈希），导致同一事实乱序后 hash 不稳定。

通俗地说，本工作包要做的是把“最终交付包的 Git 防伪封条”从“系统帮你猜缺失信息”改成“缺什么就失败”；同时保证脏文件解析和审计哈希在特殊文件名、乱序输入下仍可复现。

Pre-flight（一致性预检）：`backlog.md` 当前未完成工作包为 V2-071D；本 spec 在 V2-071D 输出文件清单中声明；本文件创建前不存在；`tests/closeout/test_git_audit_hardening.py` 与 `tests/negative/test_git_audit_fallback_rejected.py` 创建前不存在；现有 `src/boardroom_os/adapters/git_audit.py` 仍含 `base_commit_sha or final_commit_sha` 与 `worktree_ref or f"worktree.{package_root}"` fallback，符合 TODO 状态。

## 2. 范围与边界

### 2.1 In Scope

- 新建 `doc/04-implementation/v2-071d-git-audit-hardening-spec.md`（本文件）。
- 修改 `src/boardroom_os/adapters/git_audit.py`：
  - `GitAuditAdapter.collect(...)` 强制要求 `base_commit_sha` 与 `worktree_ref` 显式传入。
  - `git status` 改为 `git status --porcelain=v1 -z`。
  - `git diff` 改为 `git diff --shortstat`，或严格只解析 summary footer（摘要尾行）。
  - status parser（状态解析器）按 NUL（空字符）分隔解析，支持换行、引号、反斜杠、制表符和 ` -> ` 文件名。
- 修改 `src/boardroom_os/audit/git_version_audit.py`：
  - 对 `verification_runs` 与 `command_evidence_bindings` 使用 `canonical_sort_for_hash(...)`（规范排序哈希 helper）。
  - 稳定 `command_evidence_refs`、`checked_refs`、`command_binding_hashes` 和 `bundle_payload_hash`。
  - `fact_set_id` 使用 V2-071A 的 `namespaced_ref(...)`（命名空间引用 helper），并通过包含 `final_commit_sha` 的 payload hash 绑定最终提交。
  - `git_version_audit_bundle_id` / `hash_manifest_id` / `report_id` 如被本轮改动触及，应保持 project/hash/run 命名空间趋势，但不承担 V2-071E 的全部跨包引用改造。
- 新增测试：
  - `tests/negative/test_git_audit_fallback_rejected.py`
  - `tests/closeout/test_git_audit_hardening.py`
- 同步既有 `tests/closeout/test_git_version_audit.py` fixture。
- 同步 `doc/04-implementation/INDEX.md`。

### 2.2 Out of Scope

- 不修改 CloseoutPackage（收尾包）的 `graph_version` 边界；该问题属于 V2-071E。
- 不实现 ReplayPayloadResolver（重放载荷解析器）或 payload 内容绑定；该问题属于 V2-071E。
- 不全面改造 ProcessAuditArtifactRef（流程审计产物引用）/ ProcessAuditContentRef（流程审计内容引用）；V2-071C 已处理流程审计事实链，剩余跨包引用绑定由 V2-071E 收束。
- 不创建 tag（标签）、commit（提交）、push（推送）、checkout（检出）或 reset（重置）等写 Git 操作。
- 不读取 legacy runtime（旧运行时）实现。

### 2.3 兼容性策略

本工作包不保留旧调用方兼容路径。任何缺失 `base_commit_sha` 或 `worktree_ref` 的调用必须 fail closed（失败关闭）。测试 fixture 必须显式传入这两个字段；旧 fallback 不以 deprecation（弃用）或默认值方式保留。

## 3. GitAuditAdapter 契约

### 3.1 collect 输入契约

`GitAuditAdapter.collect(...)` 必须要求：

```python
adapter.collect(
    package_root="10-project",
    project_ref="project-tiny-fullstack",
    cwd="...",
    source_inventory_hash="...",
    base_commit_sha="abcdef...",      # required
    worktree_ref="worktree.final",    # required
    generated_at=now,
)
```

Fail-closed 规则：

1. `source_inventory_hash is None`：raise `GitAuditAdapterError("source_inventory_hash is required")`。
2. `base_commit_sha is None`：raise `GitAuditAdapterError("base_commit_sha is required")`。
3. `worktree_ref is None`：raise `GitAuditAdapterError("worktree_ref is required")`。
4. `base_commit_sha` 或 final HEAD 不是合法 Git SHA-1：由 `GitVersionAuditFactSet` / `GitCommitSha`（Git 提交 SHA 值对象）校验失败。
5. `worktree_ref` 不再由 `package_root` 推导。

### 3.2 只读 Git command allowlist（命令白名单）

Adapter 只允许执行：

```text
git rev-parse HEAD
git rev-parse --abbrev-ref HEAD
git status --porcelain=v1 -z
git diff --shortstat
git tag --points-at HEAD
```

禁止任何写命令或通用 runner（运行器）暴露，例如 `commit`、`tag -a`、`push`、`checkout`、`reset`、`clean`。

### 3.3 status -z 解析契约

`git status --porcelain=v1 -z` 的解析规则：

1. 输出按 `\0` 分隔。
2. 每条 entry（条目）的前 2 字符是 status code（状态码），第 3 字符是空格，后面是原始路径。
3. rename/copy（重命名/复制）在 `-z` 模式下不能用文本 `old -> new` 解析；必须按 NUL 条目消费旧路径和新路径。
4. 文件名可包含换行、双引号、反斜杠、制表符和 ` -> `，这些都必须作为路径普通字符保留。
5. 解析后的路径仍必须通过 GitChangedFile（Git 变更文件）模型的 audit-friendly path（审计友好路径）校验；反斜杠路径若被模型判定不安全，应 fail closed，而不是错误拆分。

推荐 parser（解析器）接口：

```python
def _parse_status_z(self, status_output: str) -> tuple[GitChangedFile, ...]: ...
```

如果 transport（命令传输）使用 text 模式，仍可用 Python string 保存 NUL；不要求本轮引入 bytes transport（字节传输）。

### 3.4 diff shortstat 解析契约

优先使用：

```text
git diff --shortstat
```

解析规则：

1. clean（干净）时 stdout 为空，summary_text 为 `clean working tree`，insertions/deletions 为 0。
2. dirty（脏）时 stdout 通常形如：

```text
 2 files changed, 12 insertions(+), 3 deletions(-)
```

3. parser 只解析 shortstat line（短统计行）本身，不扫描完整 diff stat 文件名区域。
4. 没有 insertions/deletions 片段时对应计数为 0。
5. 文件名如 `docs/12 insertions.md` 不得影响 insertions 计数，因为该文件名不会出现在 `--shortstat` 输出中。

若保留 `--stat`，必须只解析最后一行 summary footer；但推荐直接改为 `--shortstat`，减少语义歧义。

## 4. GitVersionAudit 确定性哈希契约

### 4.1 集合语义输入排序

以下输入是集合语义，必须先 canonical sort（规范排序）再进入任何 report/hash/bundle：

| 输入 | 排序 key | 影响字段 |
|---|---|---|
| `verification_runs` | `run.verification_run_id.value` | `command_evidence_refs`、`checked_refs` |
| `command_evidence_bindings` | `binding.binding_id.value` | `command_binding_hashes`、`checked_refs`、`bundle_payload_hash` |

统一使用：

```python
verification_runs = canonical_sort_for_hash(
    builder_input.verification_runs,
    key=lambda run: run.verification_run_id.value,
)
command_evidence_bindings = canonical_sort_for_hash(
    builder_input.command_evidence_bindings,
    key=lambda binding: binding.binding_id.value,
)
```

理由：`binding_id` 是 GitCommandEvidenceBinding（Git 命令证据绑定）的唯一身份，且与 V2-071A canonical sort table（规范排序表）一致。`verification_run_ref` 只是 binding 与 run 的 join key（连接键），同一 VerificationRun（验证运行）未来可能对应多条 binding；用它排序会触发 duplicate key fail closed（重复键失败关闭），用它做 dict key 还会覆盖数据。

重复 `binding_id` 由 `canonical_sort_for_hash(...)` 直接 fail closed；重复 `verification_run_ref` 不应在排序或 hash manifest（哈希清单）层被误判为重复。

### 4.2 Builder 内部必须使用排序后对象

`build_git_version_audit_bundle(...)` 内部应先构造 normalized input（归一化输入）或局部变量：

```python
sorted_runs = canonical_sort_for_hash(...)
sorted_bindings = canonical_sort_for_hash(...)
```

后续必须全部使用排序后的对象：

- `_validate_command_bindings(...)`
- `_build_report(...)`
- `_checked_refs(...)`
- `_build_hash_manifest(...)`
- `_bundle_payload_for_hash(...)`
- `GitVersionAuditBundle.command_evidence_bindings`

不得在某些路径使用排序前 tuple，避免 hash 与 report 不一致。

### 4.3 checked_refs 规则

`checked_refs` 应包含且仅稳定包含：

1. `package_contract.package_contract_id`
2. `source_inventory.source_inventory_id`
3. `run_manifest.run_manifest_id`
4. `git_facts.fact_set_id`
5. `git_facts.final_commit_sha`
6. `git_facts.source_inventory_hash`
7. sorted verification run refs
8. sorted command binding refs
9. report ref（bundle 级别）

去重可以保留，但输入顺序必须由 canonical sort 决定，不能由调用方 tuple 顺序决定。

### 4.4 command_binding_hashes 规则

`GitVersionAuditHashManifest.command_binding_hashes` 必须以稳定 key 顺序生成。由于 Python dict（字典）保持插入顺序，构造时应基于 sorted bindings，且 dict key 必须使用唯一 `binding_id.value`，不得使用可能重复的 `verification_run_ref.value`：

```python
command_binding_hashes = {
    binding.binding_id.value: _content_hash(binding.model_dump(mode="json"))
    for binding in sorted_bindings
}
```

`_validate_hash_manifest(...)` 重算时也必须使用相同排序规则和 `binding_id.value` key，避免同一 VerificationRun（验证运行）的多条 binding 覆盖数据。

## 5. fact_set_id 命名空间契约

### 5.1 问题

旧 `fact_set_id` 形如：

```text
git-version-audit-facts.<project_ref>
```

同一 project（项目）多次审计或不同 final commit（最终提交）会复用 ID，违反 V2-071A 的 namespace（命名空间）要求。

### 5.2 新规则

`GitAuditAdapter.collect(...)` 必须使用 V2-071A 的 helper：

```python
fact_payload_hash = hash_namespaced_payload(
    {
        "project_ref": project_ref,
        "base_commit_sha": base_commit_sha,
        "final_commit_sha": final_commit_sha,
        "worktree_ref": worktree_ref,
        "source_inventory_hash": source_inventory_hash,
    }
)
fact_set_id = namespaced_ref(
    kind="git-version-audit-facts",
    project_ref=project_ref,
    content_hash=fact_payload_hash,
    extra_suffix=None,
)
```

如果 `project_ref` 当前包含 V2 value object wrapper（值对象包装），需传 `.value` 后的 segment（段）。`project_ref` 必须符合 namespace segment（命名空间段）规则；若未来 ProjectRef 允许点号或大写，本轮不做兼容转换，直接 fail closed。

### 5.3 final_commit_sha 绑定

`fact_set_id` 不直接把 Git SHA-1 拼进引用段，因为 V2-071A 要求 `content_hash` 使用完整 SHA-256。final commit（最终提交）必须进入 `hash_namespaced_payload(...)` 输入，以此确保同一 project 不同 final commit 得到不同 `fact_set_id`。

## 6. 测试计划

### 6.1 Negative tests first（必须先写）

`tests/negative/test_git_audit_fallback_rejected.py`：

1. `test_git_audit_adapter_requires_base_commit_sha`
   - `base_commit_sha=None` 必须 raise `GitAuditAdapterError("base_commit_sha is required")`。
   - 断言不会 fallback 到 final commit。

2. `test_git_audit_adapter_requires_worktree_ref`
   - `worktree_ref=None` 必须 raise `GitAuditAdapterError("worktree_ref is required")`。
   - 断言不会 fallback 到 `worktree.{package_root}`。

3. `test_git_audit_adapter_uses_status_porcelain_v1_z`
   - fake transport 断言收到 `("git", "status", "--porcelain=v1", "-z")`。
   - 不应再调用 `("git", "status", "--porcelain")`。

4. `test_git_audit_adapter_uses_diff_shortstat`
   - fake transport 断言收到 `("git", "diff", "--shortstat")`。
   - 不应再调用 `("git", "diff", "--stat")`。

5. `test_git_audit_adapter_rejects_missing_source_inventory_hash`
   - 保留既有 source inventory hash（源码清单哈希）必填语义。

### 6.2 Hardening tests（硬化正反例）

`tests/closeout/test_git_audit_hardening.py`：

1. `test_status_z_parses_filename_with_newline_quote_tab_and_arrow_text`
   - status 输出包含文件名：`docs/name with\nnewline.md`、`docs/quote"name.md`、`docs/tab\tname.md`、`docs/a -> b.md`。
   - 解析后路径不被 splitlines（按行分割）或 ` -> ` 误拆。

2. `test_status_z_parses_renamed_file_without_arrow_syntax`
   - 构造 NUL 模式 rename 输出。
   - `previous_path` 和 `path` 正确进入 GitChangedFile（Git 变更文件）。

3. `test_diff_shortstat_ignores_filename_containing_insertions`
   - fake transport 中 status 表示 dirty 文件 `docs/12 insertions.md`。
   - diff shortstat 输出只给真实 `1 file changed, 1 deletion(-)`。
   - 断言 `GitDiffSummary.insertions == 0`，不会从文件名读出 12。

4. `test_verification_runs_reordering_keeps_command_evidence_refs_and_bundle_hash_stable`
   - 同一组 VerificationRun（验证运行）以不同顺序输入。
   - `report.command_evidence_refs` 相同。
   - `bundle.bundle_hash` 相同。

5. `test_command_bindings_reordering_keeps_checked_refs_and_bundle_hash_stable`
   - 同一组 GitCommandEvidenceBinding（Git 命令证据绑定）以不同顺序输入。
   - `checked_refs` 相同。
   - `bundle.bundle_hash` 相同。

6. `test_fact_set_id_is_namespaced_by_final_commit_payload`
   - 同一 project_ref、不同 final_commit_sha 得到不同 `fact_set_id`。
   - `fact_set_id` 以 `git-version-audit-facts.<project_ref>.<hash12>` 形式出现。

7. `test_git_audit_adapter_collects_explicit_base_and_worktree`
   - 合法显式 base/worktree 输入仍可构造 GitVersionAuditFactSet（Git 版本审计事实集）。

### 6.3 Existing fixture updates（既有测试迁移）

需要同步调整 `tests/closeout/test_git_version_audit.py`：

- fake transport command keys 从 `status --porcelain` 改为 `status --porcelain=v1 -z`。
- fake transport command keys 从 `diff --stat` 改为 `diff --shortstat`。
- 所有 adapter collect happy path 显式传入 `base_commit_sha` 与 `worktree_ref`。
- `_git_facts(...)` 中如使用旧 `fact_set_id="git-version-audit-facts.project"`，应改为符合新 namespace 的 helper 或测试专用 builder。

## 7. 验证命令

```sh
PYTHONPATH=src:. python -m pytest tests/negative/test_git_audit_fallback_rejected.py tests/closeout/test_git_audit_hardening.py -q --basetemp=.pytest-tmp-v2071d
```

回归建议：

```sh
PYTHONPATH=src:. python -m pytest tests/closeout/test_git_version_audit.py tests/closeout/test_git_audit_hardening.py tests/negative/test_git_audit_fallback_rejected.py -q --basetemp=.pytest-tmp-v2071d-git
PYTHONPATH=src:. python -m pytest tests/closeout tests/negative -q --basetemp=.pytest-tmp-v2071d-closeout-negative
PYTHONPATH=src:. python -m pytest tests/contracts tests/reducers tests/execution tests/evidence tests/proving tests/closeout tests/negative -q --basetemp=.pytest-tmp-v2071d-all
```

成功标准：

1. 新增 fallback negative tests（隐式降级负例）在旧实现上失败，在实现后通过。
2. Git status special filename（特殊文件名）解析测试通过。
3. diff shortstat（差异短统计）不受文件名污染。
4. GitVersionAudit（Git 版本审计）乱序输入 hash 稳定。
5. `fact_set_id` 绑定 final commit payload（最终提交载荷）并区分不同 commit。
6. 既有 closeout / negative / full regression（收尾/负例/全量回归）不回退。

## 8. 文档同步

完成实现后必须按 backlog 工作包完成协议更新：

1. `doc/04-implementation/backlog.md`
   - V2-071D 状态改 DONE。
   - TL;DR 当前未完成工作包指向 V2-071E。
   - Phase 7.5 进度由 `3 / 6` 改为 `4 / 6`。
   - 总进度同步增加 1。
2. `doc/04-implementation/acceptance-criteria.md`
   - 勾选 AC-V2-CLOSEOUT-006 中 GitAuditAdapter fallback（Git 审计适配器降级）对应项。
   - 勾选 Git status `--porcelain -z` 解析鲁棒项。
   - 勾选 Git diff stat footer / shortstat 解析项。
   - 勾选 AC-V2-CLOSEOUT-010 中 GitVersionAudit verification_runs / command_evidence_bindings 稳定性项。
3. `doc/05-project-log/2026-05.md`
   - 追加 V2-071D 完成记录，包含新增测试、关键代码文件和真实验证命令。
4. `doc/05-project-log/decisions.md`
   - 不新增 DEC，除非实现中改变 DEC-0017 的事实链权威源原则。
5. `doc/04-implementation/INDEX.md`
   - 本 spec 创建时登记。

## 9. 完成判定

V2-071D 完成时必须满足：

1. `GitAuditAdapter.collect(...)` 缺 `base_commit_sha` 必须失败，不 fallback 到 final commit。
2. `GitAuditAdapter.collect(...)` 缺 `worktree_ref` 必须失败，不 fallback 到 `worktree.{package_root}`。
3. status command 使用 `git status --porcelain=v1 -z`。
4. status parser 按 NUL 解析特殊文件名和 rename，不依赖 C-style quoted line（C 风格转义行）或 ` -> ` 文本。
5. diff summary 使用 `git diff --shortstat` 或严格 footer 解析，文件名不能污染 insertions/deletions。
6. `verification_runs` 乱序不改变 `command_evidence_refs` 或 `bundle_payload_hash`。
7. `command_evidence_bindings` 乱序不改变 `checked_refs` 或 `bundle_payload_hash`。
8. `fact_set_id` 使用 `namespaced_ref(...)`，并通过包含 `final_commit_sha` 的 SHA-256 payload hash 区分不同 commit。
9. 新增 V2-071D tests 和相关回归测试通过。
10. backlog、acceptance criteria、项目日志和 INDEX 按协议同步。