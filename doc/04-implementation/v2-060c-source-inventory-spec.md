# V2-060C SourceInventory（源码清单）同行评审 spec

## 1. 背景与现实场景

V2-060C 要处理的现实场景是：Boardroom OS V2（董事会式智能体团队框架）已经通过 V2-060B PackageAssembly（项目包装配结果）确认哪些文件计划进入 `10-project`（生成项目包），下一步必须证明这些最终源码文件不是“只存在一个引用”，而是具备可审计的 implementation lineage（实现来源链路）。

通俗地说，系统不能只说“`backend/app.py` 在包里”。它必须能回答：这个文件位于 package root（包根）内吗？sha256（哈希）是什么？由哪个 producer ticket（生产任务）产生？绑定哪个 ProviderAttempt（模型调用尝试记录）？对应哪个 SourceSurface（源码实现面）？满足哪些 AcceptanceRef（验收引用）？被哪些 VerifiedEvidence（已验证证据）支撑？

本轮已确认采用方案 3：先实现纯 SourceInventory（源码清单）领域模型与 builder（构建器），要求输入已经携带真实 sha256 和 lineage（来源链），但不在 V2-060C 内提前实现 filesystem scanner（文件系统扫描器）或 git scanner（Git 扫描器）。后续 V2-070D GitVersionAudit（Git 版本审计）可以把真实 package root（包根）扫描结果转成同一输入形状，再复用 SourceInventoryBuilder（源码清单构建器）。

## 2. 目标

1. 新增 SourceInventory（源码清单）模型，绑定 package commit（包提交）、PackageAssembly（项目包装配结果）、PackageContract（包合同）和 source file entries（源码文件条目）。
2. 新增 SourceInventoryEntry（源码清单条目）模型，逐文件记录 path（路径）、sha256、SourceSurfaceRef（源码实现面引用）、producer_ticket_ref（生产任务引用）、producer_attempt_ref（生产模型尝试引用）、acceptance_refs（验收引用）和 evidence_refs（证据引用）。
3. 新增 SourceFileRecord（源码文件记录）输入，表达 package-relative file path（包内相对文件路径）和 sha256。
4. 新增 SourceLineageRecord（源码来源链记录）输入，表达同一路径的 producer/evidence lineage（生产者与证据来源链）。
5. 新增 `build_source_inventory()`（构建源码清单函数）或等价 SourceInventoryBuilder（源码清单构建器），执行 fail-closed（失败关闭）校验。
6. 证明 ref-only inventory（只有引用的清单）、缺 sha256、缺 producer_ticket_ref、缺 producer_attempt_ref、缺 acceptance_refs、缺 evidence_refs 均无法通过。
7. 证明 package root（包根）内文件可映射到 source surface（源码实现面）、producer ticket（生产任务）、provider attempt（模型调用尝试记录）和 verified evidence（已验证证据）。

## 3. 非目标

V2-060C 不做以下事情：

1. 不读取真实文件系统，不遍历 `10-project/`。
2. 不调用 git，不生成真实 commit，不检查 dirty status（脏工作区状态）。
3. 不创建 workspace（工作区）目录，不写入 `20-evidence/source-inventory/`。
4. 不重新验证 EvidenceClaim（证据声明）或 VerifiedEvidence（已验证证据）；V2-050B EvidenceVerifier（证据验证器）已经负责 claim -> verified evidence。
5. 不生成 FinalEvidenceTable（最终证据表），不导出 evidence bundle（证据包）；这些属于 V2-050C 和 V2-060E。
6. 不生成或绑定 run commands（运行命令）；这些属于 V2-060D RunManifest（运行清单）。
7. 不把 PackageArtifact（包产物）本身当作 evidence（证据）。PackageArtifact（包产物）只证明 package shape（包形状），不能证明 implementation lineage（实现来源链）。
8. 不读取旧 runtime（旧运行时）、旧 source inventory（旧源码清单）实现或旧测试作为实现依据。

## 4. 选型结论

采用“纯领域模型 + 预留 adapter 输入形状”方案。

### 4.1 被采用方案：纯模型，预留 adapter 输入

SourceInventoryBuilder（源码清单构建器）接收：

```text
PackageAssembly（项目包装配结果）
PackageContract（包合同）
PackageCommitRef（包提交引用）
SourceFileRecord[]（源码文件记录）
SourceLineageRecord[]（源码来源链记录）
```

输出：

```text
SourceInventory（源码清单）
```

优点：

- 边界清晰：V2-060C 只回答“最终包内源码文件的 lineage 是否完整”，不提前承担 IO/git side effect（副作用）。
- 延续 V2-060B 的纯装配边界：PackageAssembly（项目包装配结果）仍然不写文件、不算 hash；V2-060C 只消费已经准备好的 sha256/source lineage 输入。
- 适合 negative tests first（负例优先）：可以先证明 ref-only、缺 hash、缺 producer 或缺 evidence 的清单无法通过。
- 后续可复用：真实 filesystem/git adapter（文件系统/Git 适配器）可以在 V2-070D 或后续工作包中生产 SourceFileRecord（源码文件记录），不需要改变 SourceInventory schema（源码清单结构）。

代价：

- 本工作包不证明磁盘上真实文件存在。
- 本工作包不证明 package commit（包提交）真的存在于 git 中。
- 调用方必须提供真实 sha256 和 lineage；builder（构建器）只验证完整性与一致性，不自行获取事实。

### 4.2 未采用方案：直接读取 package root 并计算 hash

Builder（构建器）直接遍历 `10-project/`，读取文件内容并计算 sha256。

不采用原因：会把领域模型、文件系统访问、路径遍历、hash 计算、git commit 绑定和测试 fixture（测试夹具）混在一起，过早扩大 V2-060C 的职责，也会与 V2-060B 已确定的“纯装配计划”边界不一致。

### 4.3 未采用方案：只复用 PackageAssembly artifact refs

SourceInventory（源码清单）直接从 PackageAssembly.artifacts（项目包装配产物）生成，不要求额外 SourceFileRecord（源码文件记录）或 SourceLineageRecord（源码来源链记录）。

不采用原因：这会退化成 ref-only inventory（只有引用的清单），无法证明 sha256、producer attempt（生产模型尝试）和 evidence refs（证据引用），正好违反 AC-V2-EVIDENCE-002（SourceInventory 证明实现来源链）。

## 5. 模块设计

### 5.1 新增文件

```text
src/boardroom_os/workspace/source_inventory.py
tests/proving/test_source_inventory.py
tests/negative/test_source_inventory_ref_only_rejected.py
```

需要同步 `src/boardroom_os/workspace/__init__.py` 导出核心对象，保持 workspace package（工作区包）的公开入口一致。

### 5.2 建议公开对象

```python
class SourceInventoryError(ValueError): ...

class SourceInventoryRef(NonEmptyTextValue): ...
class PackageCommitRef(NonEmptyTextValue): ...
class SourceFilePath(NonEmptyTextValue): ...
# producer_ticket_ref 直接使用 TicketId（任务 ID），不新增字符串孤岛。

class SourceFileRecord(BaseModel): ...
class SourceLineageRecord(BaseModel): ...
class SourceInventoryEntry(BaseModel): ...
class SourceInventory(BaseModel): ...


def build_source_inventory(
    *,
    package_assembly: PackageAssembly,
    package_contract: PackageContract,
    package_commit_ref: PackageCommitRef,
    source_files: tuple[SourceFileRecord, ...],
    lineage_records: tuple[SourceLineageRecord, ...],
) -> SourceInventory: ...
```

`SourceInventoryError`（源码清单错误）用于 builder/service（构建器/服务）层的语义错误；Pydantic（Pydantic 模型）结构错误仍可抛 `ValidationError`（校验错误）。

## 6. Schema（结构）设计

### 6.1 SourceFilePath（源码文件路径）

`SourceFilePath`（源码文件路径）表示相对于 `10-project` package root（包根）的文件路径。

必须满足：

1. 非空，去除首尾空白后仍非空。
2. 使用 `/` 作为路径分隔符。
3. 不得是 absolute path（绝对路径），例如 `/tmp/app.py` 必须失败。
4. 不得包含 Windows drive prefix（Windows 盘符前缀），例如 `C:/tmp/app.py` 必须失败。
5. 不得包含 `..`、`.`、空 segment（空路径片段）或反斜杠。
6. 不得以 `/` 结尾；source file（源码文件）必须是文件路径。
7. 不得以 workspace section path（工作区分区路径）开头：`00-boardroom/`、`10-project/`、`20-evidence/`、`30-audit/` 都必须失败。路径已经相对于 `10-project`。
8. 不得以框架仓库保留前缀开头：`src/boardroom_os/`、`doc/`、`scripts/`、`examples/`。
9. 允许 generated package（生成包）使用 `backend/`、`frontend/`、`src/`、`tests/`、`docs/` 等包内路径；其中 `src/` 仅表示目标项目源码，不得解释为 Boardroom OS V2 repo（框架仓库）源码。

### 6.2 SourceFileRecord（源码文件记录）

建议 schema：

```yaml
path:
sha256:
```

字段说明：

- `path`：`SourceFilePath`（源码文件路径），相对于 `10-project`。
- `sha256`：`ArtifactSha256`（产物哈希），复用 V2-050B EvidenceVerifier（证据验证器）的 64 位小写 hex digest（十六进制摘要）规则。

不变量：

1. source_files（源码文件记录集合）不能为空。
2. `path` 必须唯一。
3. `sha256` 必须是 64 字符小写 hex digest。
4. 不能只提供 path 而缺 sha256。

### 6.3 SourceLineageRecord（源码来源链记录）

建议 schema：

```yaml
path:
source_surface_ref:
producer_ticket_ref:
producer_attempt_ref:
acceptance_refs:
evidence_refs:
```

字段说明：

- `path`：`SourceFilePath`（源码文件路径），必须对应一个 SourceFileRecord（源码文件记录）。
- `source_surface_ref`：`SourceSurfaceRef`（源码实现面引用），必须属于 PackageContract.source_surfaces（包合同源码实现面）。
- `producer_ticket_ref`：`TicketId`（任务 ID），表示产生该最终文件的 implementation ticket（实施任务）；V2-060C 不新增独立 `ProducerTicketRef`，避免后续 lineage join（来源链关联）出现“字符串相同但类型不同”的孤岛。
- `producer_attempt_ref`：`ProviderAttemptRef`（模型调用尝试引用），表示产生该最终文件的 provider attempt（模型调用尝试记录）。
- `acceptance_refs`：tuple of `AcceptanceRef`（验收引用），必须非空，且属于对应 SourceSurface（源码实现面）声明的 acceptance_refs。
- `evidence_refs`：tuple of `VerifiedEvidenceRef`（已验证证据引用），必须非空。

不变量：

1. lineage_records（来源链记录集合）不能为空。
2. 每个 SourceFileRecord.path（源码文件记录路径）必须有且只有一个 SourceLineageRecord（源码来源链记录）。
3. SourceLineageRecord.path（来源链路径）不能指向未出现在 source_files（源码文件记录集合）中的路径。
4. `source_surface_ref` 必须属于 PackageContract.source_surfaces（包合同源码实现面）。
5. `acceptance_refs` 必须是该 SourceSurface.acceptance_refs（源码实现面验收引用）的非空子集。
6. `producer_ticket_ref`、`producer_attempt_ref` 和 `evidence_refs` 均不可为空。
7. 不允许以 notes（备注）、checker verdict（检查结论）或 raw artifact ref（原始产物引用）替代 verified evidence refs（已验证证据引用）。

### 6.4 SourceInventoryEntry（源码清单条目）

建议 schema：

```yaml
path:
sha256:
source_surface_ref:
producer_ticket_ref:
producer_attempt_ref:
acceptance_refs:
evidence_refs:
```

字段说明：

- `path` 与 `sha256` 来自 SourceFileRecord（源码文件记录）。
- lineage 字段来自 SourceLineageRecord（源码来源链记录）。
- entry（条目）是 SourceInventory（源码清单）的最小审计单元。

不变量：

1. entry（条目）必须绑定完整 lineage（来源链）。
2. `acceptance_refs` 和 `evidence_refs` 必须保持稳定排序或保持调用方显式顺序；builder（构建器）输出整体条目按 `path` 排序，保证 deterministic dump（确定性导出）。
3. entry（条目）不得包含 content（源码内容），避免把 inventory（清单）变成 source artifact store（源码产物存储）。

### 6.5 SourceInventory（源码清单）

建议 schema：

```yaml
source_inventory_id:
package_assembly_ref:
package_contract_ref:
package_commit_ref:
package_root:
entries:
  - path:
    sha256:
    source_surface_ref:
    producer_ticket_ref:
    producer_attempt_ref:
    acceptance_refs:
    evidence_refs:
```

字段说明：

- `source_inventory_id`：`SourceInventoryRef`（源码清单引用），建议确定性 ID：`source-inventory.<package_assembly_ref>.<package_commit_ref>`。
- `package_assembly_ref`：`PackageAssemblyRef`（项目包装配引用）。
- `package_contract_ref`：`ContractId`（包合同 ID）。
- `package_commit_ref`：`PackageCommitRef`（包提交引用），由调用方提供；V2-060C 只要求非空，不验证 git 存在性。
- `package_root`：`WorkspacePath`（工作区路径），必须等于 `10-project`。
- `entries`：tuple of SourceInventoryEntry（源码清单条目集合），必须非空并按 path（路径）稳定排序。

Manifest/package invariants（清单与包合同不变量）：

1. `package_assembly.package_contract_ref` 必须等于 `package_contract.package_contract_id`。
2. `package_assembly.package_root.value` 必须等于 `package_contract.package_root`，且必须为 `10-project`。
3. `package_commit_ref` 必须非空。
4. source inventory entries（源码清单条目）必须覆盖 PackageAssembly.artifacts（项目包装配产物）中所有 implementation-bearing artifacts（承载实现的产物）。
5. implementation-bearing artifacts（承载实现的产物）包括 `PackageArtifactKind.SOURCE`、`PackageArtifactKind.TEST`、`PackageArtifactKind.DOC`。
6. README、AGENTS、package-contract metadata（包合同元数据）和 `run-manifest.json`（运行清单文件）不进入 V2-060C SourceInventory（源码清单）；`run-manifest.json` 的命令绑定与 lineage（来源链）由 V2-060D RunManifest（运行清单）单独证明，避免要求 deterministic manifest（确定性清单）伪造 provider attempt（模型调用尝试）。
7. SourceInventoryEntry.path（源码清单条目路径）必须对应 PackageAssembly.artifacts 中的 implementation-bearing artifact path（承载实现的产物路径），不能 invent（凭空创造）包外文件，也不能指向 README、AGENTS、package-contract metadata（包合同元数据）或 `run-manifest.json`（运行清单文件）。
8. SourceInventoryEntry.source_surface_ref（源码实现面引用）必须与对应 PackageArtifact.source_surface_refs（包产物源码实现面引用）兼容。
9. SourceInventoryEntry.acceptance_refs（源码清单验收引用）必须覆盖对应 PackageArtifact.acceptance_refs（包产物验收引用），且不得越出 SourceSurface.acceptance_refs（源码实现面验收引用）。
10. 任意 extra fields（额外字段）必须 fail closed（失败关闭）。

## 7. 数据流

```text
PackageContract（包合同，来自 V2-010D）
PackageAssembly（项目包装配结果，来自 V2-060B）
SourceFileRecord[]（源码文件记录，来自未来 materializer/filesystem adapter 或测试夹具）
SourceLineageRecord[]（源码来源链记录，来自 provider/work product/evidence 链路）
PackageCommitRef（包提交引用，来自调用方或未来 git adapter）
  -> build_source_inventory（构建源码清单）
  -> SourceInventory（源码清单）
      -> V2-060E EvidenceExport（证据导出）
      -> V2-070D GitVersionAudit（Git 版本审计）
      -> V2-070A CloseoutGate（收尾门禁）
```

关键边界：

- PackageAssembly（项目包装配结果）证明 package shape（包形状）。
- SourceInventory（源码清单）证明 package source lineage（包内源码来源链）。
- SourceInventory（源码清单）不证明 git clean（Git 干净状态）或 final commit existence（最终提交存在性）。
- SourceInventory（源码清单）不替代 EvidenceVerifier（证据验证器）或 FinalEvidenceTable（最终证据表）。

## 8. 错误处理

1. Pydantic models（Pydantic 模型）使用 `ConfigDict(frozen=True, extra="forbid")`，拒绝未知字段和运行时篡改。
2. 路径、hash、引用形状错误抛 `ValidationError`（校验错误）。
3. `build_source_inventory()`（构建源码清单函数）遇到语义错误时抛 `SourceInventoryError`（源码清单错误）。
4. 错误信息应指出具体 invariant（不变量），例如 `source file sha256 is required`、`producer_attempt_ref is required`、`source inventory cannot be ref-only`、`source file is missing lineage`、`lineage path is not in package assembly`。
5. 不提供 fallback（降级）或自动补 lineage（来源链）；调用方必须补齐真实 source file record（源码文件记录）和 lineage record（来源链记录）。

## 9. 测试方案

新增测试文件：

```text
tests/proving/test_source_inventory.py
tests/negative/test_source_inventory_ref_only_rejected.py
```

测试应遵循 negative tests first（负例优先）：先写 backlog（待办）明确要求的 ref-only / 缺字段失败场景，再补充 package/contract/evidence lineage（包/合同/证据来源链）一致性负例，最后写 tiny happy path（微型正向路径）。

### 9.1 必须先写的 negative tests（负例测试）

1. 只传 PackageAssembly（项目包装配结果）或 artifact refs（产物引用）而没有 SourceFileRecord（源码文件记录）和 SourceLineageRecord（来源链记录）时失败，证明 ref-only inventory（只有引用的清单）不能通过。
2. SourceFileRecord（源码文件记录）缺 sha256 时失败。
3. sha256 不是 64 字符小写 hex digest 时失败。
4. SourceLineageRecord（来源链记录）缺 producer_ticket_ref（生产任务引用）时失败。
5. SourceLineageRecord（来源链记录）缺 producer_attempt_ref（生产模型尝试引用）时失败。
6. SourceLineageRecord（来源链记录）缺 acceptance_refs（验收引用）时失败。
7. SourceLineageRecord（来源链记录）缺 evidence_refs（证据引用）时失败。
8. SourceFileRecord.path（源码文件路径）使用绝对路径、`..`、反斜杠、`10-project/`、`20-evidence/`、`30-audit/` 或框架 repo prefix（框架仓库前缀）时失败。
9. source_files（源码文件记录集合）有重复 path（路径）时失败。
10. lineage_records（来源链记录集合）有重复 path（路径）时失败。
11. SourceFileRecord（源码文件记录）缺对应 lineage record（来源链记录）时失败。
12. lineage record（来源链记录）指向未出现在 source_files（源码文件记录集合）中的 path（路径）时失败。
13. lineage path（来源链路径）不在 PackageAssembly.artifacts（项目包装配产物）中时失败。
14. implementation-bearing artifact（承载实现的产物）缺 source inventory entry（源码清单条目）时失败。
15. source_surface_ref（源码实现面引用）不属于 PackageContract.source_surfaces（包合同源码实现面）时失败。
16. acceptance_refs（验收引用）越出 SourceSurface.acceptance_refs（源码实现面验收引用）时失败。
17. inventory entry（清单条目）的 source_surface_ref 与 PackageArtifact.source_surface_refs（包产物源码实现面引用）不兼容时失败。
18. inventory entry（清单条目）的 acceptance_refs 未覆盖 PackageArtifact.acceptance_refs（包产物验收引用）时失败。
19. package_assembly.package_contract_ref 与 package_contract.package_contract_id 不一致时失败。
20. package_commit_ref（包提交引用）为空时失败。
21. 传入 extra fields（额外字段）时失败。

### 9.2 Happy path（正向路径）

1. tiny full-stack package（微型全栈包）的 PackageAssembly（项目包装配结果）包含：
   - `run-manifest.json`（由 V2-060D RunManifest（运行清单）证明，不进入 V2-060C SourceInventory（源码清单））
   - `backend/app.py`
   - `frontend/App.tsx`
   - `tests/test_app.py`
   - `docs/usage.md`
2. 每个 implementation-bearing artifact（承载实现的产物：source/test/doc）都有 SourceFileRecord（源码文件记录）和 SourceLineageRecord（源码来源链记录）。
3. V2-060C 测试中的 `TicketId`（任务 ID）、`ProviderAttemptRef`（模型调用尝试引用）和 `VerifiedEvidenceRef`（已验证证据引用）可作为合法 NonEmptyTextValue（非空文本值）构造；测试不 wire up（接线）完整 ProviderAttempt（模型调用尝试记录）或 VerifiedEvidence（已验证证据）对象，避免越界到 V2-040/V2-050 职责。
4. `build_source_inventory()`（构建源码清单函数）成功返回 SourceInventory（源码清单）。
5. SourceInventory（源码清单）绑定正确的 `package_assembly_ref`、`package_contract_ref`、`package_commit_ref` 和 `package_root == 10-project`。
6. entries（条目）按 path（路径）稳定排序，重复调用得到相同 `source_inventory_id` 与相同 entry order（条目顺序）。
7. 每个 entry（条目）包含 path、sha256、source_surface_ref、producer_ticket_ref、producer_attempt_ref、acceptance_refs、evidence_refs。
8. `model_dump()`（模型导出）输出稳定、可审计。

## 10. 验收口径

V2-060C 完成后必须满足：

1. `src/boardroom_os/workspace/source_inventory.py` 存在，并定义 SourceInventory（源码清单）、SourceInventoryEntry（源码清单条目）、SourceFileRecord（源码文件记录）、SourceLineageRecord（源码来源链记录）和 `build_source_inventory()`（构建源码清单函数）或等价入口。
2. `tests/proving/test_source_inventory.py` 和 `tests/negative/test_source_inventory_ref_only_rejected.py` 存在。
3. negative tests（负例测试）证明 ref-only（只有引用）、缺 sha256、缺 producer_ticket_ref、缺 producer_attempt_ref、缺 acceptance_refs、缺 evidence_refs 均 fail closed（失败关闭）。
4. happy path（正向路径）证明 package root（包根）内文件可映射到 source surface（源码实现面）、producer ticket（生产任务）、provider attempt（模型调用尝试记录）和 verified evidence（已验证证据）。
5. 实现不读取磁盘、不调用 git、不创建目录、不写文件、不导出 `20-evidence`。
6. SourceInventory（源码清单）明确证明 implementation lineage（实现来源链），不退化为 PackageAssembly artifact refs（项目包装配产物引用）的重复列表。
7. 文档同步：完成实施后需按 backlog（待办）协议更新 `backlog.md`、`acceptance-criteria.md`、`doc/05-project-log/2026-05.md`；若只写本 spec（规格）则只需更新 `doc/04-implementation/INDEX.md`。

## 11. 同行评审关注点

请重点审查：

1. “纯领域模型 + 预留 adapter 输入形状”是否足以满足 V2-060C，而不提前进入 filesystem/git scanner（文件系统/Git 扫描器）职责。
2. PackageCommitRef（包提交引用）是否只要求非空，还是 V2-060C 就应验证 git commit existence（Git 提交存在性）；本 spec 选择只要求非空，把真实性留给 V2-070D GitVersionAudit（Git 版本审计）。
3. README/AGENTS/package-contract metadata（包元数据）是否应进入 SourceInventory（源码清单）；本 spec 选择不进入，避免把说明文件和合同文件误判为 implementation evidence（实施证据）。
4. `run-manifest.json` 是否应进入 SourceInventory（源码清单）；本 spec 选择不进入，避免 V2-060C 要求 deterministic run manifest（确定性运行清单）伪造 provider attempt（模型调用尝试），其命令绑定与 lineage（来源链）由 V2-060D RunManifest（运行清单）单独证明。
5. SourceInventoryEntry.acceptance_refs（源码清单条目验收引用）是否必须覆盖 PackageArtifact.acceptance_refs（包产物验收引用）；本 spec 选择必须覆盖，避免源码清单弱于装配清单。
6. evidence_refs（证据引用）是否必须是 VerifiedEvidenceRef（已验证证据引用）；本 spec 选择必须，防止 raw claim（原始声明）或 checker notes（检查备注）替代 verified evidence（已验证证据）。
7. 后续真实 filesystem/git adapter（文件系统/Git 适配器）应该落在 V2-070D，还是需要在 V2-060C 追加小 adapter；本 spec 倾向留到 V2-070D，避免扩大当前工作包。
