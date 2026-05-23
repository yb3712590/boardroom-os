# V2-060B PackageAssembler（项目包装配器）同行评审 spec

## 1. 背景与现实场景

V2-060B 要处理的现实场景是：Boardroom OS V2（董事会式智能体团队框架）已经通过 V2-060A WorkspaceManifest（工作区清单）画清楚 generated project workspace（生成项目工作区）的四区边界，下一步需要确认最终交付给用户的 `10-project`（生成项目包）里应该包含哪些文件。

通俗地说，V2-060B 不是“真的把文件写到磁盘”，而是先生成一张严格的装箱清单：哪些 README、AGENTS、source files（源码文件）、tests（测试）、`package-contract.json`（包合同文件）和 `run-manifest.json`（运行清单文件）会进入最终包；如果缺少必需清单文件，或者任何 source artifact（源码产物）试图写到 `10-project` 之外，就必须 fail closed（失败关闭）。

本轮已确认采用“纯装配计划 + 校验”口径：PackageAssembler（项目包装配器）只输出 typed PackageAssembly（类型化项目包装配结果），不创建目录、不写文件、不复制文件、不计算 hash。真实文件 hash 与 producer lineage（生产者来源链）留给 V2-060C SourceInventory（源码清单），declared commands（声明命令）与 runner binding（执行器绑定）留给 V2-060D RunManifest（运行清单）。

## 2. 目标

1. 新增 `PackageArtifact`（包产物）模型，用 typed value（类型化值）表达计划进入 `10-project` 的文件。
2. 新增 `PackageAssembly`（项目包装配结果）模型，绑定 WorkspaceManifest（工作区清单）、PackageContract（包合同）、package root（包根）和 artifact list（产物清单）。
3. 新增 `assemble_package()`（装配项目包函数）或等价 PackageAssembler（项目包装配器）入口，执行 fail-closed（失败关闭）校验。
4. 证明 `package-contract.json`（包合同文件）和 `run-manifest.json`（运行清单文件）是 package assembly（项目包装配）的必需产物。
5. 证明所有 artifact path（产物路径）都必须位于 `10-project` 包内，不能逃逸到 `00-boardroom`、`20-evidence`、`30-audit` 或框架仓库路径。
6. 证明 PackageContract.source_surfaces（包合同源码实现面）声明的 paths（路径）必须被 assembly artifacts（装配产物）覆盖，避免最终交付物退化为离散 source artifact（源码片段）。

## 3. 非目标

V2-060B 不做以下事情：

1. 不创建 workspace（工作区）目录，也不写入本地文件系统。
2. 不复制 provider output（模型输出）或 work product artifact（工作产物产物）。
3. 不计算 sha256（哈希）、不读取 git tree（Git 树）、不构建 SourceInventory（源码清单）。
4. 不生成或验证 `run-manifest.json` 内部命令 schema（结构）；命令绑定属于 V2-060D。
5. 不导出 VerificationRun（验证运行）、FinalEvidenceTable（最终证据表）或 `20-evidence` 证据包；这些属于 V2-060E。
6. 不导入 role config（角色配置）、skill file（技能文件）、prompt file（提示词文件）或 MCP interface manifest（MCP 接口清单）；这些属于 V2-060F。
7. 不读取旧 runtime（旧运行时）、旧 workspace 实现或旧测试作为实现依据。

## 4. 选型结论

采用“纯装配计划 + 严格校验”方案。

### 4.1 被采用方案：纯装配计划 + 校验

PackageAssembler（项目包装配器）接收：

```text
WorkspaceManifest（工作区清单）
PackageContract（包合同）
PackageArtifact tuple（包产物集合）
```

输出：

```text
PackageAssembly（项目包装配结果）
```

优点：

- 边界清晰：V2-060B 只回答“最终包应该包含什么”，不提前承担文件系统 side effect（副作用）。
- 适合 negative tests first（负例优先）：可以先用纯模型证明缺文件、路径逃逸、surface coverage（实现面覆盖）不足无法通过。
- 与 V2-060C / V2-060D / V2-060E 解耦：后续模块可以消费 PackageAssembly（项目包装配结果），再分别处理 hash、run command binding（运行命令绑定）和 evidence export（证据导出）。
- 不会把 generated project workspace（生成项目工作区）误用为 Boardroom OS V2 repo（框架仓库）结构。

代价：

- 本工作包不证明磁盘上真实文件存在。
- 本工作包不证明 source content（源码内容）与 provider attempt（模型调用尝试记录）或 evidence（证据）之间的 lineage（来源链）。
- 后续实现必须确保 V2-060C 从实际 package root（包根）和 git/hash 构建 SourceInventory（源码清单），不能只信任 PackageAssembly（项目包装配结果）。

### 4.2 未采用方案：真实写入 workspace

PackageAssembler（项目包装配器）直接创建目录并写入文件。

不采用原因：会把 assembly validation（装配校验）、directory creation（目录创建）、overwrite policy（覆盖策略）、encoding（编码）和 hash/source inventory（源码清单）混在一起，过早扩大 V2-060B 的职责。

### 4.3 未采用方案：内存装配 + materialize 接口

PackageAssembler（项目包装配器）默认输出 PackageAssembly（项目包装配结果），同时提供 `materialize_package()`（物化项目包函数）写入磁盘。

不采用原因：这个方案最终可能需要，但会把 V2-060B 扩展成两个工作包的范围。当前 backlog（待办）只要求证明 package assembler（项目包装配器）边界和 fail-closed（失败关闭）规则。

## 5. 模块设计

### 5.1 新增文件

```text
src/boardroom_os/workspace/assembler.py
tests/proving/test_package_assembler.py
```

需要同步 `src/boardroom_os/workspace/__init__.py` 导出核心对象，保持 workspace package（工作区包）的公开入口一致。

### 5.2 建议公开对象

```python
class PackageAssemblerError(ValueError): ...

class PackageAssemblyRef(NonEmptyTextValue): ...

class PackageArtifactKind(StrEnum):
    README = "readme"
    AGENTS = "agents"
    PACKAGE_CONTRACT = "package_contract"
    RUN_MANIFEST = "run_manifest"
    SOURCE = "source"
    TEST = "test"
    DOC = "doc"

class PackageArtifact(BaseModel): ...
class PackageAssembly(BaseModel): ...


def assemble_package(
    *,
    workspace_manifest: WorkspaceManifest,
    package_contract: PackageContract,
    artifacts: tuple[PackageArtifact, ...],
) -> PackageAssembly: ...
```

`PackageAssemblerError`（项目包装配错误）用于 factory/service（工厂/服务）层的语义错误；Pydantic（Pydantic 模型）结构错误仍可抛 `ValidationError`（校验错误）。

## 6. Schema（结构）设计

### 6.1 PackageArtifactPath（包产物路径）

可以复用 V2-060A 的 `WorkspacePath`（工作区路径）校验风格，也可以定义更窄的 `PackageArtifactPath`（包产物路径）。建议新建 `PackageArtifactPath`，因为它的语义是 `10-project` 内的相对文件路径，不是 workspace section root（工作区分区根）。

必须满足：

1. 非空，去除首尾空白后仍非空。
2. 使用 `/` 作为路径分隔符。
3. 不得是 absolute path（绝对路径），例如 `/tmp/app.py` 必须失败。
4. 不得包含 Windows drive prefix（Windows 盘符前缀），例如 `C:/tmp/app.py` 必须失败。
5. 不得包含 `..`、`.`、空 segment（空路径片段）或反斜杠。
6. 不得以 `/` 结尾；artifact（产物）必须是文件路径，不是目录路径。
7. 不得以 workspace section path（工作区分区路径）开头：`00-boardroom/`、`10-project/`、`20-evidence/`、`30-audit/` 都必须失败。artifact path（产物路径）已经相对于 `10-project`，不能重复写 `10-project/README.md`。
8. 显式允许普通 generated package（生成包）使用 `src/`、`tests/`、`backend/`、`frontend/`、`docs/` 作为包内路径前缀。
9. 明确拒绝框架仓库保留前缀：`src/boardroom_os/`、`doc/`、`scripts/`、`examples/`。`backend/` 作为 generated package（生成包）的后端源码前缀允许使用，但不得被解释为旧 `backend/app/core/` 实现迁移依据。

### 6.2 PackageArtifact（包产物）

建议 schema：

```yaml
relative_path:
artifact_kind:
source_surface_refs:
acceptance_refs:
```

字段说明：

- `relative_path`：`PackageArtifactPath`（包产物路径），相对于 `10-project`。
- `artifact_kind`：`PackageArtifactKind`（包产物类型），用于区分 README、AGENTS、package contract、run manifest、source、test、doc。
- `source_surface_refs`：tuple of `SourceSurfaceRef`（源码实现面引用），表示该产物覆盖哪些 PackageContract.source_surfaces（包合同源码实现面）。README/AGENTS 可以为空；package contract、run manifest、source、test、doc 必须有明确 surface refs。
- `acceptance_refs`：tuple of `AcceptanceRef`（验收引用），表示该产物关联哪些 acceptance criteria（验收项）。README/AGENTS 可以为空；实现、测试、文档、run manifest 必须有明确 acceptance refs。

不变量：

1. `relative_path` 必须唯一，不能两个 artifact（产物）写同一路径。
2. `package-contract.json` 必须使用 `PackageArtifactKind.PACKAGE_CONTRACT`。
3. `run-manifest.json` 必须使用 `PackageArtifactKind.RUN_MANIFEST`。
4. `README.md` 必须使用 `PackageArtifactKind.README`。
5. `AGENTS.md` 必须使用 `PackageArtifactKind.AGENTS`。
6. 非 README/AGENTS 的 artifact（产物）必须携带非空 `source_surface_refs` 和 `acceptance_refs`。
7. artifact（产物）引用的 `source_surface_refs` 必须属于 active PackageContract.source_surfaces（活跃包合同源码实现面）。
8. artifact（产物）引用的 `acceptance_refs` 必须属于对应 source surface（源码实现面）的 acceptance_refs（验收引用）。V2-060B 不读取 AcceptanceContract（验收合同），但可以通过 SourceSurface（源码实现面）做局部一致性校验。

### 6.3 PackageAssembly（项目包装配结果）

建议 schema：

```yaml
package_assembly_id:
workspace_manifest_ref:
package_contract_ref:
package_root:
artifacts:
  - relative_path: README.md
    artifact_kind: readme
  - relative_path: AGENTS.md
    artifact_kind: agents
  - relative_path: package-contract.json
    artifact_kind: package_contract
  - relative_path: run-manifest.json
    artifact_kind: run_manifest
```

字段说明：

- `package_assembly_id`：`PackageAssemblyRef`（项目包装配引用），建议确定性 ID：`package-assembly.<workspace_manifest_ref>.<package_contract_ref>`。确定性 ID 的稳定性前提是 `WorkspaceManifestRef.value`（工作区清单引用值）和 `ContractId.value`（合同 ID 值）的格式由各自模块保证，`assemble_package()`（装配项目包函数）不重新解析或规范化这些 ref（引用）。
- `workspace_manifest_ref`：`WorkspaceManifestRef`（工作区清单引用）。
- `package_contract_ref`：`ContractId`（包合同 ID）。
- `package_root`：`WorkspacePath`（工作区路径），必须等于 WorkspaceManifest.package_root（工作区清单包根），也就是 `10-project`。
- `artifacts`：tuple of `PackageArtifact`（包产物集合），顺序应稳定，建议按 `relative_path` 排序后存储。

Manifest/package invariants（清单与包合同不变量）：

1. `workspace_manifest.package_contract_ref` 必须等于 `package_contract.package_contract_id`。
2. `workspace_manifest.package_root.value` 必须等于 `package_contract.package_root`，且必须为 `10-project`。
3. `package_root` 必须等于 `10-project`。
4. artifacts（产物）不能为空。
5. artifacts（产物）路径必须唯一。
6. 必须包含：
   - `README.md`
   - `AGENTS.md`
   - `package-contract.json`
   - `run-manifest.json`
7. 必须覆盖 PackageContract.source_surfaces（包合同源码实现面）声明的所有 paths（路径）。覆盖规则见 6.4。
8. 软件或 mixed package（混合包）必须至少包含一个 `source` artifact（源码产物）和一个 `test` artifact（测试产物）。文档型 package（文档包）可以不要求 source/test，但仍必须满足 source surface coverage（实现面覆盖）。
9. 当 `PackageContract.docs_required=True`（包合同要求文档）时，artifacts（产物）必须至少包含一个 `PackageArtifactKind.DOC`（文档产物）。
10. 任意 extra fields（额外字段）必须 fail closed（失败关闭）。

### 6.4 SourceSurface coverage（源码实现面覆盖）规则

PackageContract.source_surfaces（包合同源码实现面）中的 `paths` 可能表示目录前缀或具体文件：

| Declared path（声明路径） | 匹配方式 | 可满足的 artifact path（产物路径）示例 | 不可满足示例 |
|---|---|---|---|
| `backend/` | 目录前缀匹配 | `backend/app.py` | `backend`、`src/backend/app.py` |
| `frontend/` | 目录前缀匹配 | `frontend/App.tsx` | `frontend`、`docs/frontend.md` |
| `tests/` | 目录前缀匹配 | `tests/test_app.py` | `test_app.py` |
| `docs/` | 目录前缀匹配 | `docs/usage.md` | `README.md` |
| `run-manifest.json` | 精确文件匹配 | `run-manifest.json` | `docs/run-manifest.json` |

- `backend/` 表示必须至少有一个 artifact path（产物路径）以 `backend/` 开头。
- `frontend/` 表示必须至少有一个 artifact path（产物路径）以 `frontend/` 开头。
- `tests/` 表示必须至少有一个 artifact path（产物路径）以 `tests/` 开头。
- `run-manifest.json` 表示必须存在该精确文件。
- `docs/` 表示必须至少有一个 artifact path（产物路径）以 `docs/` 开头。

覆盖时必须同时满足：

1. 每个 source surface（源码实现面）至少被一个 artifact（产物）的 `source_surface_refs` 引用。
2. 对该 surface（实现面）的每个 declared path（声明路径），至少有一个 artifact path（产物路径）匹配。
3. 匹配该 surface（实现面）的 artifact（产物）必须携带该 surface 的 acceptance_refs（验收引用）子集或全集；不能携带 surface 未声明的 acceptance_ref。
4. `package-contract.json` 可以视为 package metadata（包元数据），不必要求 PackageContract.source_surfaces（包合同源码实现面）专门声明它；但 `run-manifest.json` 必须由 `run-manifest` 或等价 source surface（源码实现面）覆盖，因为 backlog（待办）明确把 run manifest（运行清单）纳入装配产物。

## 7. 数据流

```text
PackageContract（包合同，来自 V2-010D）
WorkspaceManifest（工作区清单，来自 V2-060A）
PackageArtifact[]（包产物清单，来自 worker work products / deterministic package metadata）
  -> assemble_package（装配项目包）
  -> PackageAssembly（项目包装配结果）
      -> V2-060C SourceInventory（源码清单）
      -> V2-060D RunManifest（运行清单）
      -> V2-060E EvidenceExport（证据导出）
```

关键边界：

- PackageAssembly（项目包装配结果）证明 package shape（包形状）与 PackageContract（包合同）一致。
- PackageAssembly（项目包装配结果）不证明文件存在、内容正确或 hash 稳定。
- PackageAssembly（项目包装配结果）不替代 SourceInventory（源码清单）。
- PackageAssembly（项目包装配结果）不替代 run command verification（运行命令验证）。

## 8. 错误处理

1. Pydantic models（Pydantic 模型）使用 `ConfigDict(frozen=True, extra="forbid")`，拒绝未知字段和运行时篡改。
2. 路径级结构错误抛 `ValidationError`（校验错误）。
3. `assemble_package()`（装配项目包函数）遇到语义错误时抛 `PackageAssemblerError`（项目包装配错误）。
4. 错误信息应指出具体 invariant（不变量），例如 `package-contract.json is required`、`run-manifest.json is required`、`artifact path must be relative to package root`、`source surface backend-api is not covered`。
5. 不提供 fallback（降级）或自动补文件；调用方必须补齐真实 artifact（产物）。

## 9. 测试方案

新增测试文件：

```text
tests/proving/test_package_assembler.py
```

测试应遵循 negative tests first（负例优先）：先写 backlog（待办）明确要求的三个失败场景，再补充 package boundary（包边界）与 source surface coverage（源码实现面覆盖）负例，最后写 tiny happy path（微型正向路径）。

### 9.1 必须先写的 negative tests（负例测试）

1. 缺 `package-contract.json` 时 `assemble_package()` 失败。
2. 缺 `run-manifest.json` 时 `assemble_package()` 失败。
3. source artifact（源码产物）路径写到 package root（包根）外时失败，例如：
   - `/tmp/app.py`
   - `../app.py`
   - `20-evidence/source.json`
   - `30-audit/process-audit.md`
   - `00-boardroom/tickets/ticket.json`
   - `10-project/src/app.py`
4. artifact path（产物路径）使用反斜杠、空 segment、`.` segment、尾部斜杠时失败。
5. `workspace_manifest.package_contract_ref` 与 `package_contract.package_contract_id` 不一致时失败。
6. `PackageContract.package_root` 不是 `10-project` 或与 WorkspaceManifest.package_root（工作区清单包根）不一致时失败。
7. 缺 README 或 AGENTS 时失败。
8. 软件 package（软件包）缺 source artifact（源码产物）或 test artifact（测试产物）时失败。
9. `PackageContract.docs_required=True` 但缺 DOC artifact（文档产物）时失败。
10. artifact（产物）引用未知 source_surface_ref（源码实现面引用）时失败。
11. artifact（产物）引用 source surface（源码实现面）未声明的 acceptance_ref（验收引用）时失败。
12. PackageContract.source_surfaces（包合同源码实现面）声明的 path（路径）没有任何 artifact（产物）覆盖时失败。
13. 重复 artifact relative_path（产物相对路径）时失败。
14. `package-contract.json` 或 `run-manifest.json` 使用错误 artifact_kind（产物类型）时失败。
15. 传入 extra fields（额外字段）时失败。

### 9.2 Happy path（正向路径）

1. tiny full-stack package（微型全栈包）包含：
   - `README.md`
   - `AGENTS.md`
   - `package-contract.json`
   - `run-manifest.json`
   - `backend/app.py` 或 `src/app.py`
   - `frontend/App.tsx` 或等价 UI source（界面源码）
   - `tests/test_app.py` 或等价 test source（测试源码）
   - `docs/usage.md`（当 docs_required=true 时）
2. `assemble_package()` 成功返回 PackageAssembly（项目包装配结果）。
3. PackageAssembly（项目包装配结果）绑定正确的 `workspace_manifest_ref`、`package_contract_ref` 和 `package_root == 10-project`。
4. artifacts（产物）排序稳定，重复调用得到相同 `package_assembly_id` 与相同 artifact order（产物顺序）。
5. PackageContract.source_surfaces（包合同源码实现面）的 backend/frontend/tests/run-manifest/docs paths（路径）均被覆盖。
6. `model_dump()`（模型导出）输出稳定、可审计。

## 10. 验收口径

V2-060B 完成后必须满足：

1. `src/boardroom_os/workspace/assembler.py` 存在，并定义 PackageArtifact（包产物）、PackageAssembly（项目包装配结果）和 assemble_package（装配项目包）或等价入口。
2. `tests/proving/test_package_assembler.py` 存在，并覆盖 backlog（待办）明确要求的 negative tests（负例测试）：缺 `package-contract.json`、缺 `run-manifest.json`、source 写到 package root（包根）外必须失败。
3. happy path（正向路径）证明 tiny package（微型包）包含 README、AGENTS、package-contract、run-manifest、backend/frontend/tests 或 src/tests。
4. 实现不创建目录、不写文件、不计算 hash、不构建 SourceInventory（源码清单）。
5. PackageAssembly（项目包装配结果）明确表达最终交付物是 package（包），不是离散 source artifact list（源码产物列表）。
6. 文档同步：完成实施后需按 backlog（待办）协议更新 `backlog.md`、`acceptance-criteria.md`、`doc/05-project-log/2026-05.md`；若只写本 spec（规格）则只需更新 `doc/04-implementation/INDEX.md`。

## 11. 同行评审关注点

请重点审查：

1. “纯装配计划 + 校验”是否足以满足 V2-060B，而不提前进入 materialize（物化）或 SourceInventory（源码清单）职责。
2. `PackageArtifactPath`（包产物路径）是否应该允许以 `10-project/` 开头；本 spec 选择不允许，因为它已经相对于 package root（包根）。
3. `package-contract.json` 是否应要求对应 source surface（源码实现面）；本 spec 选择不要求，把它视为 package metadata（包元数据）。
4. `run-manifest.json` 是否必须被 source surface coverage（源码实现面覆盖）覆盖；本 spec 选择必须，因为 backlog（待办）明确把 run manifest（运行清单）列为 package assembly（项目包装配）必需产物。
5. 软件 package（软件包）是否必须同时包含 source artifact（源码产物）和 test artifact（测试产物）；本 spec 选择必须，以避免只交付 metadata（元数据）和 docs（文档）。
6. coverage rule（覆盖规则）对目录 path（路径）和文件 path（路径）的区分是否足够清晰。
7. 是否需要把 README/AGENTS 也强制绑定 acceptance_refs（验收引用）；本 spec 选择允许为空，避免把项目说明文件误当 implementation evidence（实施证据）。
