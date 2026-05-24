# V2-060F AgentAssetImport（智能体资产导入）同行评审 spec

## 1. 背景与现实场景

V2-060F 要处理的现实场景是：Boardroom OS V2（董事会式智能体团队框架）已经能生成 `10-project`（生成项目包）和 `20-evidence`（证据区）相关清单，但 agent team（智能体团队）本身还依赖项目外的 role config（角色配置）、skill file（技能文件）、prompt file（提示词文件）和 MCP interface manifest（MCP 接口清单）。如果这些外部文件只停留在开发者机器上，后续 closeout（收尾）、replay（重放）和 process audit（流程审计）就无法证明“当时 agent 到底使用了哪套资产”。

通俗地说，本工作包要做的是把项目外的一包 agent 资产“装箱拍照”：读取本地资产文件，计算真实 sha256（内容哈希），把文件复制到 generated project workspace（生成项目工作区）的 `00-boardroom/agents/` 下，并写出 `00-boardroom/agents/asset-import-manifest.yaml`（资产导入清单）。这样最终项目工作区不再依赖外部 prompt/skill/MCP 文件，也不会因为外部文件静默变化而改变已经编译过的 ExecutionPackage（执行包）。

本轮 Pre-flight（一致性预检）结论：`backlog.md`（待办）当前未完成工作包为 V2-060F；`src/boardroom_os/workspace/agent_asset_import.py` 和 `tests/proving/test_agent_asset_import.py` 尚不存在；`acceptance-criteria.md`（验收标准）中 Phase 6 的 “Agent asset bundle 导入可审计” checkbox（复选项）仍未勾选，状态一致，无 drift（漂移）。

## 2. 选项背景

### 2.1 方案 A：只生成纯 AgentAssetImportManifest（智能体资产导入清单）计划

只新增 typed domain model（类型化领域模型），让调用方传入 source_path（来源路径）、target_path（目标路径）和 sha256（内容哈希），返回 import plan（导入计划），不读取源文件、不写目标文件、不生成实际 `asset-import-manifest.yaml` 文件。

优点：延续 V2-060A ~ V2-060E 的纯模型边界，测试不触碰文件系统。

不采用原因：V2-060F 与 V2-060A ~ V2-060E 有本质差异。前几个工作包消费的是已经存在的 typed facts（类型化事实），而 V2-060F 的输入是项目外真实文件。DEC-0012 明确要求在 workspace/package 阶段物化为 `00-boardroom/agents/` 快照；backlog 也要求复制/物化、计算 sha256、拒绝静默覆盖。若只输出计划，Phase 6 结束时仍没有自包含 agent asset snapshot（智能体资产快照）。

### 2.2 方案 B：只做直接物化，不建立领域计划

只提供 `materialize_agent_assets(...)`（物化智能体资产函数），扫描外部目录并直接复制到 `00-boardroom/agents/`，同时生成导入清单。

优点：实现路径短，最贴近“复制/物化”的字面动作。

不采用原因：缺少领域计划会让路径、hash、source lineage（来源链）和 overwrite policy（覆盖策略）散落在 IO（输入输出）流程中，难以用 fail-closed（失败关闭）模型测试覆盖，也不利于后续 V2-070 process audit（流程审计）稳定引用。

### 2.3 方案 C：领域计划 + 1:1 materializer（物化器）

新增 AgentAssetImportManifest（智能体资产导入清单）、AgentAssetImportBatch（智能体资产导入批次）和 AgentAssetImportEntry（智能体资产导入条目）等 typed model，同时新增窄口径 `materialize_agent_assets(...)`。领域层负责声明“应导入哪些文件、从哪里来、目标写到哪里、期望 sha256 是什么”；物化层只负责按清单读源文件、验 hash、写 `00-boardroom/agents/` 目标文件和 `asset-import-manifest.yaml`。

优点：

- 满足 DEC-0012 “物化为快照”的承诺。
- 满足 backlog 对复制/物化、sha256 和静默覆盖检测的字面要求。
- 保留 V2-060A ~ V2-060E 的 typed model（类型化模型）可测边界。
- 将文件系统副作用限制在一个明确 materializer（物化器）函数中，可用 `tmp_path` 隔离测试。
- 保持 ExecutionPackage compiler（执行包编译器）0 外部文件输入：compiler 仍只消费已编译 registry / contract / graph / seat assignment，不读取这些外部资产文件。
- 支持既有项目后续追加导入批次：旧批次不可变，新批次以新的 source_ref（来源引用）写入同一 cumulative manifest（累计清单）。

代价：

- V2-060F 会成为 Phase 6 第一个包含真实文件系统 IO（输入输出）的 workspace 工作包。
- 需要明确拒绝 symlink（符号链接）、远端 fetch（远端拉取）、force overwrite（强制覆盖）、encoding transform（编码转换）等范围蔓延点。
- 测试必须严格使用 `tmp_path`，不得触碰框架仓库真实目录。
- manifest（清单）要区分“同一 manifest 完全重跑”的幂等与“追加新批次”的显式变更。

## 3. 选型结论

采用方案 C 的窄口径版：领域计划 + 与之 1:1 的 materializer（物化器）。

核心边界是：V2-060F 必须真实把本地 agent assets（智能体资产）物化到 generated project workspace（生成项目工作区）的 `00-boardroom/agents/` 快照，并写出 cumulative `asset-import-manifest.yaml`（累计资产导入清单）；但它不负责解析这些资产语义、不重新编译 RoleProfile（角色模板）或 SkillBinding（技能绑定）、不参与 ExecutionPackage compiler（执行包编译器）、不做远端同步或覆盖策略扩展。

本 spec 选择以下三条收口策略：

1. **asset kind（资产类型）按需导入**：manifest 至少包含一个 entry（条目）；present asset kinds（已出现资产类型）必须路径正确，但模型层不强制每个项目都有 role/skill/prompt/MCP 四类资产。四类资产全覆盖仅作为 framework capability test（框架能力测试）证明，不作为每个项目的合同不变量。
2. **asset_ref（资产引用）绑定 V2-030A registry refs（注册表引用）**：`asset_ref` 不是新的孤立 ID，而是对应 V2-030A RoleProfileId / SkillFileRef / PromptRef / McpInterfaceRef 的同值引用。V2-060F 必须在 materialize 前通过 registry 校验拒绝野生资产。
3. **单文件 cumulative manifest（累计清单）**：文件路径仍固定为 `00-boardroom/agents/asset-import-manifest.yaml`，但文件内容是多批次 ledger（账本）。已有批次不可变；新 source_ref 只能追加新批次，不能改写历史批次。

## 4. 目标

1. 新增 AgentAssetImportManifest（智能体资产导入清单）模型，表达 workspace（工作区）内累计的资产导入账本、目标 manifest 路径和 batches（批次）。
2. 新增 AgentAssetImportBatch（智能体资产导入批次）模型，表达一次外部资产包导入的 source_ref（来源引用）、source_kind（来源类型）、imported_at（导入时间）和 entries（条目）。
3. 新增 AgentAssetImportEntry（智能体资产导入条目）模型，表达单个 role config（角色配置）、skill file（技能文件）、prompt file（提示词文件）或 MCP interface manifest（MCP 接口清单）的 registry-backed asset_ref（注册表支撑资产引用）、source_path（来源路径）、target_path（目标路径）和 sha256（内容哈希）。
4. 新增 registry binding validation（注册表绑定校验），证明每个 `asset_ref` 都能按 asset_kind（资产类型）在 V2-030A registry（注册表）中解析。
5. 新增 `materialize_agent_assets()`（物化智能体资产函数），按 manifest（清单）读取新批次 source file（来源文件）、计算 sha256、比对 expected sha256（期望哈希）、复制到 `00-boardroom/agents/`，并写出或追加 `00-boardroom/agents/asset-import-manifest.yaml`。
6. 证明导入目标写到 `00-boardroom/agents/` 外必须 fail closed（失败关闭）。
7. 证明 manifest（清单）缺 workspace_manifest_ref（工作区清单引用）、manifest_path（清单路径）或 batches（批次）必须失败；batch 缺 source_ref、source_kind、imported_at 或 entries 必须失败。
8. 证明 entry（条目）缺 asset_ref、asset_kind、source_path、target_path 或 sha256 必须失败。
9. 证明 sha256 mismatch（哈希不一致）、source file missing（来源文件缺失）、source file 非普通文件、source path escape（来源路径逃逸）必须失败。
10. 证明 target file（目标文件）已存在且 hash 不同必须失败；已存在且 hash 相同可以幂等通过，不静默改写。
11. 证明已有 `asset-import-manifest.yaml` 的历史批次不可变；同一 manifest 完全重跑幂等；新 source_ref 可以追加新批次。
12. 证明 happy path（正向路径）可以把包含 role/skill/prompt/MCP 四类文件的本地 bundle（资产包）复制到 `00-boardroom/agents/`，并生成 `asset-import-manifest.yaml`。该正例证明框架能力，不代表所有项目必须具备四类资产。
13. 证明 manifest（清单）与 materializer（物化器）支持只导入项目实际使用的 asset_kinds（资产类型）子集，不需要伪造未使用的资产类型。
14. 证明 ExecutionPackage compiler（执行包编译器）仍无外部文件输入；V2-060F 只产生 workspace snapshot（工作区快照）和 audit lineage（审计来源链），不改变 V2-030D compiler 边界。

## 5. 非目标

V2-060F 不做以下事情：

1. 不解析 role config（角色配置）、skill file（技能文件）、prompt file（提示词文件）或 MCP interface manifest（MCP 接口清单）的业务语义；V2-030A 的 RoleProfile / SkillBinding / PromptSource / McpInterface registry（注册表）仍由其既有入口负责。
2. 不从外部文件重新编译 ExecutionPackage（执行包），不让 ExecutionPackage compiler（执行包编译器）读取 source_root（来源根目录）或 workspace filesystem（工作区文件系统）。
3. 不支持 remote URL fetch（远端 URL 拉取）、git clone（Git 克隆）、package manager install（包管理器安装）或网络下载。
4. 不支持 symlink copy（符号链接复制）、hardlink（硬链接）、权限位保留、mtime 保留或 executable bit（可执行位）策略。
5. 不做 encoding transform（编码转换）；资产文件按 bytes（字节）读取、hash 和复制。只有 `asset-import-manifest.yaml` 由 materializer（物化器）以 UTF-8 写出。
6. 不提供 force overwrite（强制覆盖）参数。若目标已有不同 hash，必须失败；更新资产必须使用新的 source_ref（来源引用）追加批次，并使用不会覆盖历史目标的 target_path（目标路径）。
7. 不清理 `00-boardroom/agents/` 下的旧文件或额外文件；本期只负责 manifest batches（清单批次）、entries（条目）和 `asset-import-manifest.yaml` 的写入与冲突保护。
8. 不创建 `10-project`、`20-evidence`、`30-audit` 内容，不替代 PackageAssembly（项目包装配结果）或 WorkspaceEvidenceBundle（工作区证据包）。
9. 不调用 git，不证明 final commit（最终提交）、dirty status（脏状态）或 source inventory hash（源码清单哈希）；这些属于 V2-070D GitVersionAudit（Git 版本审计）。
10. 不读取旧 runtime（旧运行时）、旧 workspace（旧工作区）或旧 agent asset implementation（旧智能体资产实现）。

## 6. 模块设计

### 6.1 新增文件

```text
src/boardroom_os/workspace/agent_asset_import.py
tests/proving/test_agent_asset_import.py
```

需要同步 `src/boardroom_os/workspace/__init__.py` 导出核心对象，保持 workspace package（工作区包）公开入口一致。

### 6.2 建议公开对象

```python
class AgentAssetImportError(ValueError): ...

class AgentAssetImportManifestRef(NonEmptyTextValue): ...
class AgentAssetBundleSourceRef(NonEmptyTextValue): ...
class AgentAssetRef(NonEmptyTextValue): ...
class AgentAssetSha256(NonEmptyTextValue): ...
class AgentAssetSourcePath(NonEmptyTextValue): ...
class AgentAssetTargetPath(NonEmptyTextValue): ...
class AgentAssetManifestPath(NonEmptyTextValue): ...

class AgentAssetBundleSourceKind(StrEnum):
    LOCAL_BUNDLE = "local_bundle"

class AgentAssetKind(StrEnum):
    ROLE_CONFIG = "role_config"
    SKILL_FILE = "skill_file"
    PROMPT_FILE = "prompt_file"
    MCP_INTERFACE_MANIFEST = "mcp_interface_manifest"

class AgentAssetImportEntry(BaseModel): ...
class AgentAssetImportBatch(BaseModel): ...
class AgentAssetImportManifest(BaseModel): ...
class AgentAssetMaterializationResult(BaseModel): ...


def validate_agent_asset_registry_bindings(
    *,
    manifest: AgentAssetImportManifest,
    role_profile_registry: RoleProfileRegistry,
    skill_file_registry: SkillFileSourceRegistry,
    prompt_registry: PromptSourceRegistry,
    mcp_interface_registry: McpInterfaceRegistry,
) -> None: ...


def materialize_agent_assets(
    manifest: AgentAssetImportManifest,
    *,
    workspace_manifest: WorkspaceManifest,
    source_root: Path,
    workspace_root: Path,
    role_profile_registry: RoleProfileRegistry,
    skill_file_registry: SkillFileSourceRegistry,
    prompt_registry: PromptSourceRegistry,
    mcp_interface_registry: McpInterfaceRegistry,
) -> AgentAssetMaterializationResult: ...
```

`AgentAssetImportError`（智能体资产导入错误）用于 service/materializer（服务/物化器）层语义错误；Pydantic（Pydantic 模型）结构错误仍可抛 `ValidationError`（校验错误）。

首版不新增 `agent_asset_materializer.py`，避免把 V2-060F 拆成两个工作包；materializer（物化器）与 typed model（类型化模型）同处 `agent_asset_import.py`，后续若出现复用压力再拆分。

## 7. Schema（结构）设计

### 7.1 AgentAssetBundleSourceKind（智能体资产包来源类型）

首版只支持本地资产包：

```yaml
source_kind: local_bundle
```

不支持 URL、git repo（Git 仓库）、package registry（包注册表）或云端存储引用。若未来需要远端来源，应新增工作包定义 fetch/auth/cache（拉取/鉴权/缓存）边界，不能扩展本期 materializer（物化器）。

### 7.2 AgentAssetKind（智能体资产类型）

首版支持四类 asset（资产），但不要求每个项目都导入四类：

```yaml
role_config
skill_file
prompt_file
mcp_interface_manifest
```

canonical target prefix（规范目标前缀）：

```text
role_config             -> 00-boardroom/agents/roles/
skill_file              -> 00-boardroom/agents/skills/
prompt_file             -> 00-boardroom/agents/prompts/
mcp_interface_manifest  -> 00-boardroom/agents/mcp/
```

`asset_kind`（资产类型）与 `target_path`（目标路径）必须匹配，避免把 MCP manifest（MCP 接口清单）写到 prompts（提示词）目录或把 prompt file（提示词文件）写到 roles（角色）目录。

### 7.3 AgentAssetSourcePath（智能体资产来源路径）

`source_path`（来源路径）必须相对当前导入调用的 `source_root`（来源根目录），并满足：

1. 必须使用 forward slash（正斜杠）。
2. 禁止 absolute path（绝对路径）、Windows drive（Windows 盘符）、反斜杠、空 segment（空路径段）、`.`、`..` 和尾部斜杠。
3. 必须命名具体文件，不表达目录。
4. 不得以 workspace section（工作区分区）作为前缀，例如 `00-boardroom/`、`10-project/`、`20-evidence/`、`30-audit/`。
5. 不得落入框架 repo layout（仓库布局）前缀，例如 `src/boardroom_os/`、`doc/`、`scripts/`、`examples/`。

`source_path` 不保存 host absolute path（宿主机绝对路径），避免把开发者机器路径写入可交付审计产物。materializer（物化器）通过函数参数 `source_root` 将相对路径解析到本地临时目录或调用方选择的资产目录。

### 7.4 AgentAssetTargetPath（智能体资产目标路径）

`target_path`（目标路径）必须相对 workspace root（工作区根目录），并满足：

1. 必须以 `00-boardroom/agents/` 开头。
2. 必须使用 forward slash（正斜杠）。
3. 禁止 absolute path（绝对路径）、Windows drive（Windows 盘符）、反斜杠、空 segment（空路径段）、`.`、`..` 和尾部斜杠。
4. 必须命名具体文件。
5. 不得等于 `00-boardroom/agents/asset-import-manifest.yaml`；该路径保留给 generated manifest（生成清单）。
6. 不得写入 `10-project/`、`20-evidence/`、`30-audit/` 或框架 repo layout（仓库布局）。
7. 必须匹配 `asset_kind`（资产类型）的 canonical target prefix（规范目标前缀）。

### 7.5 AgentAssetManifestPath（智能体资产清单路径）

`manifest_path`（清单路径）使用独立类型，不复用 AgentAssetTargetPath（智能体资产目标路径），因为普通资产文件不得占用 `asset-import-manifest.yaml`，而 manifest 自身必须写到该路径。

`manifest_path` 必须满足：

1. 必须等于 `00-boardroom/agents/asset-import-manifest.yaml`。
2. 必须是相对 workspace root（工作区根目录）的文件路径。
3. 禁止 absolute path（绝对路径）、Windows drive（Windows 盘符）、反斜杠、空 segment（空路径段）、`.`、`..` 和尾部斜杠。
4. 任意其它路径必须 fail closed（失败关闭）。

### 7.6 AgentAssetSha256（智能体资产内容哈希）

`sha256` 必须是 64 位小写 hex digest（十六进制摘要）。

不允许空字符串、非 hex 字符、大小写混用、短 hash、长 hash 或算法前缀（例如 `sha256:<digest>`）。materializer（物化器）读取 source file bytes（来源文件字节）后计算 sha256，并与 entry.sha256（条目哈希）完全一致才允许写入。

### 7.7 AgentAssetImportEntry（智能体资产导入条目）

建议 schema：

```yaml
asset_ref:
asset_kind:
source_path:
target_path:
sha256:
```

字段说明：

- `asset_ref`：AgentAssetRef（智能体资产引用），必须唯一于同一 batch（批次），并且必须等于对应 V2-030A registry ref（注册表引用）的 `.value`。
- `asset_kind`：AgentAssetKind（智能体资产类型），四类之一。
- `source_path`：AgentAssetSourcePath（来源路径），相对 source_root（来源根目录）。
- `target_path`：AgentAssetTargetPath（目标路径），相对 workspace_root（工作区根目录），必须位于 `00-boardroom/agents/`。
- `sha256`：AgentAssetSha256（内容哈希），期望来源文件哈希。

`asset_ref` 按 asset_kind（资产类型）绑定 V2-030A registry（注册表）：

```text
role_config             -> RoleProfileRegistry.contains(RoleProfileId(asset_ref.value))
skill_file              -> SkillFileSourceRegistry.contains(SkillFileRef(asset_ref.value))
prompt_file             -> PromptSourceRegistry.contains(PromptRef(asset_ref.value))
mcp_interface_manifest  -> McpInterfaceRegistry.contains(McpInterfaceRef(asset_ref.value))
```

不变量：

1. `asset_ref` 必须非空并可按 asset_kind 转换成对应 registry ref 类型。
2. 同一 batch（批次）内 `asset_ref` 必须唯一。
3. 同一 batch（批次）内 `source_path` 必须唯一，避免同一来源文件在同一导入批次中被重复声明为不同资产。
4. 同一 batch（批次）内 `target_path` 必须唯一，避免两个资产竞争同一目标路径。
5. `asset_kind` 与 `target_path` canonical prefix（规范前缀）必须一致。
6. 任意 extra fields（额外字段）必须 fail closed（失败关闭）。

跨 batch（批次）规则：

1. 同一 cumulative manifest（累计清单）中，`source_ref` 必须唯一。
2. 跨批次重复 `asset_ref` 只有在 sha256 和 target_path 完全一致时才允许作为显式重复导入记录；若同一 asset_ref 对应不同 sha256 或不同 target_path，必须失败，调用方应产生新的 registry ref（注册表引用）。
3. 跨批次重复 `target_path` 只有在 sha256 完全一致时才允许；不同 sha256 必须失败，禁止 in-place replacement（原地替换）。

### 7.8 AgentAssetImportBatch（智能体资产导入批次）

建议 schema：

```yaml
source_ref:
source_kind:
imported_at:
entries:
```

字段说明：

- `source_ref`：AgentAssetBundleSourceRef（智能体资产包来源引用），标识这次导入的外部资产包或资产版本。资产更新时必须产生新 source_ref，并追加新 batch（批次），不能复用旧 source_ref 静默改写。
- `source_kind`：AgentAssetBundleSourceKind（智能体资产包来源类型），首版必须为 `local_bundle`。
- `imported_at`：timezone-aware datetime（带时区时间），记录该批次首次导入时间，禁止 naive datetime（无时区时间）。
- `entries`：tuple of AgentAssetImportEntry（导入条目集合），必须非空，按 target_path（目标路径）稳定排序。

不变量：

1. `source_ref`、`source_kind`、`imported_at` 和 `entries` 均为必需字段。
2. `source_kind` 必须为 `local_bundle`。
3. `imported_at` 必须带时区。
4. entries（条目）必须非空。
5. entries 按 target_path（目标路径）稳定排序，保证 manifest dump（清单导出）可重现。
6. 不要求 entries 覆盖四类 asset_kind（资产类型）。没有 MCP 的项目不能被迫伪造 MCP asset（MCP 资产）。
7. 任意 extra fields（额外字段）必须 fail closed（失败关闭）。

幂等说明：

`imported_at` 是首次导入时间，必须由调用方持久化后复用。V2-060F 的幂等只针对字段完全相同的 batch/manifest（批次/清单）；如果调用方用新的 `datetime.now()` 重新生成同一 source_ref 的 batch，则这不是同一 manifest，必须 fail closed（失败关闭）。

### 7.9 AgentAssetImportManifest（智能体资产导入清单）

建议 schema：

```yaml
agent_asset_import_manifest_id:
workspace_manifest_ref:
manifest_path:
batches:
```

字段说明：

- `agent_asset_import_manifest_id`：AgentAssetImportManifestRef（智能体资产导入清单引用），建议确定性 ID：`agent-asset-import.<workspace_manifest_ref>`。
- `workspace_manifest_ref`：WorkspaceManifestRef（工作区清单引用），必须来自 WorkspaceManifest（工作区清单）。
- `manifest_path`：AgentAssetManifestPath（智能体资产清单路径），必须等于 `00-boardroom/agents/asset-import-manifest.yaml`。
- `batches`：tuple of AgentAssetImportBatch（智能体资产导入批次集合），必须非空，按导入账本顺序保存。

不变量：

1. `workspace_manifest_ref`、`manifest_path` 和 `batches` 均为必需字段。
2. `manifest_path` 必须固定为 `00-boardroom/agents/asset-import-manifest.yaml`，不得写到 `10-project`、`20-evidence`、`30-audit` 或其它 boardroom 子目录。
3. `agent_asset_import_manifest_id` 必须与 `workspace_manifest_ref` 一致。
4. batches（批次）必须非空。
5. `source_ref` 在 batches 中必须唯一。
6. 同一 `source_ref` 已存在时，后续 manifest 只能携带完全相同 batch（幂等），不能改变 imported_at、entries 或 sha256。
7. 任意 extra fields（额外字段）必须 fail closed（失败关闭）。

### 7.10 AgentAssetMaterializationResult（智能体资产物化结果）

建议 schema：

```yaml
agent_asset_import_manifest_ref:
workspace_manifest_ref:
manifest_path:
materialized_source_refs:
materialized_asset_refs:
materialized_target_paths:
manifest_sha256:
```

字段说明：

- `agent_asset_import_manifest_ref`：物化的 AgentAssetImportManifestRef（智能体资产导入清单引用）。
- `workspace_manifest_ref`：WorkspaceManifestRef（工作区清单引用）。
- `manifest_path`：AgentAssetManifestPath（智能体资产清单路径），固定 `00-boardroom/agents/asset-import-manifest.yaml`。
- `materialized_source_refs`：本次调用实际新增或幂等确认的 source refs（来源引用）。
- `materialized_asset_refs`：本次调用实际新增或幂等确认的 asset refs（资产引用）。
- `materialized_target_paths`：本次调用实际新增或幂等确认的 target paths（目标路径）。
- `manifest_sha256`：写出的 `asset-import-manifest.yaml` 内容哈希。

不变量：

1. `materialized_source_refs` 必须来自 manifest.batches 的 source_ref 集合。
2. `materialized_asset_refs` 必须来自 materialized batches（已物化批次）中的 asset_ref 集合。
3. `materialized_target_paths` 必须来自 materialized batches（已物化批次）中的 target_path 集合。
4. `manifest_sha256` 必须是 64 位小写 sha256 hex digest。
5. materializer 成功返回前必须确认 `asset-import-manifest.yaml` 已存在且内容与本次 cumulative manifest dump（累计清单导出）一致。

## 8. Registry binding（注册表绑定）语义

V2-060F 不解析资产文件内容，但必须证明每个导入文件是已编译 registry（注册表）会使用的资产，而不是 workspace（工作区）里的野生文件。

`validate_agent_asset_registry_bindings(...)` 必须：

1. 遍历 manifest.batches[*].entries（清单批次条目）。
2. 按 asset_kind（资产类型）把 asset_ref 转成对应 V2-030A ref 类型。
3. 调用对应 registry（注册表）的 `contains(...)` 或等价只读接口。
4. 任意 asset_ref 无法转换、registry 缺少对应 ref、或 asset_kind/registry 类型不匹配时 fail closed（失败关闭）。
5. 不读取 source file（来源文件），不解析 YAML/Markdown 内容，不调用 ExecutionPackage compiler（执行包编译器）。

该校验闭合后，V2-070C process audit（流程审计）才能从 provider attempt（模型调用尝试记录）追到 AgentSeat（智能体席位）、SkillBinding（技能绑定）、PromptSource（提示词来源）/ SkillFileSource（技能文件来源）/ McpInterfaceDefinition（MCP 接口定义），再追到 V2-060F snapshot file（快照文件）。

## 9. Materializer（物化器）语义

### 9.1 函数签名

```python
def materialize_agent_assets(
    manifest: AgentAssetImportManifest,
    *,
    workspace_manifest: WorkspaceManifest,
    source_root: Path,
    workspace_root: Path,
    role_profile_registry: RoleProfileRegistry,
    skill_file_registry: SkillFileSourceRegistry,
    prompt_registry: PromptSourceRegistry,
    mcp_interface_registry: McpInterfaceRegistry,
) -> AgentAssetMaterializationResult: ...
```

### 9.2 输入边界

1. `source_root` 和 `workspace_root` 是 host filesystem path（宿主文件系统路径），只作为执行参数，不写入 manifest（清单）。
2. `workspace_manifest` 必须与 `manifest.workspace_manifest_ref` 匹配；错配必须 fail closed（失败关闭）。
3. `source_root` 必须存在且是目录。
4. `workspace_root` 必须存在且是目录；materializer（物化器）可以创建 `00-boardroom/agents/...` 子目录，但不创建整个 workspace root（工作区根）。
5. materializer 必须先调用 `validate_agent_asset_registry_bindings(...)`；registry binding（注册表绑定）失败时不得执行任何文件写入。
6. materializer 解析路径时必须使用 `Path.resolve()` 或等价方式确认：
   - source file（来源文件）在 source_root 内；
   - target file（目标文件）在 workspace_root / `00-boardroom/agents` 内；
   - manifest file（清单文件）在 workspace_root / `00-boardroom/agents/asset-import-manifest.yaml`。
7. 任意路径逃逸必须 fail closed（失败关闭）。

### 9.3 读取已有 manifest（清单）

1. 如果 `asset-import-manifest.yaml` 不存在，本次 manifest 的全部 batches（批次）都是待物化批次。
2. 如果 `asset-import-manifest.yaml` 已存在，必须按 canonical JSON（规范 JSON）解析为 AgentAssetImportManifest（智能体资产导入清单）。
3. 已存在 manifest 的 `agent_asset_import_manifest_id`、`workspace_manifest_ref` 和 `manifest_path` 必须与本次 manifest 一致。
4. 已存在 manifest 的 batches 必须是本次 manifest.batches 的 prefix（前缀），且每个已有 batch 必须逐字段完全相同。
5. 若已有 manifest 与本次 manifest 完全相同，则本次调用是幂等重跑，只需确认目标文件 hash 与 manifest entries 一致。
6. 若本次 manifest 在已有 prefix 后追加新 batches，则只对新增 batches 读取 source_root 中的 source files（来源文件）；历史 batches 不要求 source_root 仍保留旧来源文件。
7. 如果已有 manifest 内容不是合法 canonical JSON、不是合法 AgentAssetImportManifest、不是本次 manifest 前缀，或重定义同一 source_ref，必须 fail closed（失败关闭）。

### 9.4 写入资产文件策略

对每个需要物化或确认的 entry（条目）：

1. 新增 batch（新增批次）的 entry：读取 `source_root / entry.source_path` bytes（字节）。
2. source path 必须存在、必须是 regular file（普通文件）、不得是 symlink（符号链接）或目录。
3. 计算 source sha256，并与 entry.sha256 完全一致；不一致则失败，不写目标文件。
4. 解析 `workspace_root / entry.target_path`。
5. 若目标文件不存在：创建父目录并写入 source bytes。
6. 若目标文件已存在：计算目标文件 sha256。
   - 若与 entry.sha256 一致：幂等通过，不重写。
   - 若不同：fail closed（失败关闭），不得覆盖。
7. 历史 batch（历史批次）的 entry：不要求 source file 仍存在，但目标文件必须存在且 sha256 与 entry.sha256 一致；否则 fail closed（失败关闭）。
8. 任意写入错误必须停止并抛 `AgentAssetImportError`（智能体资产导入错误）。

### 9.5 `asset-import-manifest.yaml` 写入策略

1. materializer 在所有 asset files（资产文件）写入或幂等确认后，生成 canonical JSON text（规范 JSON 文本）。文件名保留为 `.yaml`，因为 backlog 和 DEC-0012 已固定该审计产物名；内容采用 JSON-compatible YAML subset（JSON 兼容 YAML 子集），避免新增 PyYAML（YAML 库）依赖和手写 YAML 不确定性。
2. canonical JSON 必须由 `AgentAssetImportManifest.model_dump(mode="json")`（模型 JSON 导出）派生，并使用 `json.dumps(..., sort_keys=True, ensure_ascii=False, separators=(",", ":")) + "\n"` 或等价稳定参数。
3. canonical JSON 内容不得包含 host absolute paths（宿主绝对路径）。
4. 如果 manifest file（清单文件）不存在：写入 UTF-8 文件。
5. 如果 manifest file 已存在且本次 manifest 与已有 manifest 完全相同：幂等通过，不重写。
6. 如果 manifest file 已存在且已有 manifest 是本次 manifest 的 prefix（前缀）：写入包含旧批次 + 新批次的完整 canonical JSON。旧批次必须逐字段不变。
7. 如果 manifest file 已存在但不满足 prefix append（前缀追加）规则：fail closed（失败关闭），不得覆盖。
8. 成功后计算 manifest_sha256（清单哈希）并返回 AgentAssetMaterializationResult（智能体资产物化结果）。

### 9.6 原子性边界

V2-060F 首版不承诺事务型 rollback（回滚）。如果某个后续 entry 写入失败，已经写入的同 hash 文件可以保留；调用方再次用同一 manifest 运行时应幂等通过这些已写文件，并在失败点继续暴露同一错误。

该选择避免在本期实现目录清理和临时 staging rename（临时暂存重命名）策略。后续若要强原子导入，应新增工作包定义 transaction/staging/cleanup（事务/暂存/清理）边界。

## 10. 数据流

```text
External local agent asset bundle（外部本地智能体资产包）
  roles/*.yaml
  skills/*.md
  prompts/*.md
  mcp/*.yaml      # 可选；没有 MCP 的项目不需要伪造

V2-030A registries（V2-030A 注册表）
  RoleProfileRegistry / SkillFileSourceRegistry / PromptSourceRegistry / McpInterfaceRegistry

AgentAssetImportManifest（智能体资产导入清单）
  workspace_manifest_ref / manifest_path
  batches[source_ref, source_kind, imported_at, entries]
  entries[asset_ref, asset_kind, source_path, target_path, sha256]

validate_agent_asset_registry_bindings（校验智能体资产注册表绑定）
  -> asset_ref must resolve in matching V2-030A registry（资产引用必须在对应注册表中解析）

materialize_agent_assets（物化智能体资产）
  -> read source file bytes for new batches（读取新批次来源文件字节）
  -> compute sha256（计算哈希）
  -> compare expected sha256（比对期望哈希）
  -> write 00-boardroom/agents/...（写入智能体资产快照）
  -> append/write 00-boardroom/agents/asset-import-manifest.yaml（追加/写入导入清单）

AgentAssetMaterializationResult（智能体资产物化结果）
  -> V2-070 ProcessAudit（流程审计）
  -> V2-080 Tiny proving scenario（微型端到端证明场景）
```

关键边界：

```text
RoleProfile / SkillBinding registries（角色模板/技能绑定注册表）
  -> V2-030D ExecutionPackage compiler（执行包编译器）

External agent asset files（外部智能体资产文件）
  -> V2-060F workspace snapshot（工作区快照）
```

两条线不能交叉：ExecutionPackage compiler（执行包编译器）不读取 external files（外部文件）；V2-060F materializer（物化器）不重新编译 ExecutionPackage（执行包）。

## 11. Fail-closed（失败关闭）规则

### 11.1 模型层必须失败的情况

1. manifest 缺 `workspace_manifest_ref`、`manifest_path` 或 `batches`。
2. manifest `manifest_path` 不等于 `00-boardroom/agents/asset-import-manifest.yaml`。
3. manifest ID 与 workspace_manifest_ref 不一致。
4. batches 为空。
5. batch 缺 `source_ref`、`source_kind`、`imported_at` 或 `entries`。
6. batch 使用 naive datetime（无时区时间）。
7. batch `source_kind` 非 `local_bundle`。
8. batch entries 为空。
9. batch entries 未按 target_path 稳定排序。
10. entry 缺 `asset_ref`、`asset_kind`、`source_path`、`target_path` 或 `sha256`。
11. source_path / target_path 使用绝对路径、Windows drive、反斜杠、`.`、`..`、空 segment 或尾部斜杠。
12. target_path 不在 `00-boardroom/agents/` 下。
13. target_path 指向 `asset-import-manifest.yaml`。
14. asset_kind 与 target_path canonical prefix 不一致。
15. sha256 非 64 位小写 hex digest。
16. 同一 batch 内重复 asset_ref、source_path 或 target_path。
17. 同一 manifest 内重复 source_ref，或同一 source_ref 被不同 batch 内容重定义。
18. 跨 batch 重复 asset_ref 但 sha256 或 target_path 不一致。
19. 跨 batch 重复 target_path 但 sha256 不一致。
20. 任意 extra fields（额外字段）。

不再作为模型层失败条件：entries 未覆盖 role_config / skill_file / prompt_file / mcp_interface_manifest 四类资产。没有 MCP 的项目可合法缺少 MCP asset（MCP 资产）。

### 11.2 Registry binding（注册表绑定）必须失败的情况

1. role_config entry 的 asset_ref 无法转换为 RoleProfileId（角色模板 ID）。
2. skill_file entry 的 asset_ref 无法转换为 SkillFileRef（技能文件引用）。
3. prompt_file entry 的 asset_ref 无法转换为 PromptRef（提示词引用）。
4. mcp_interface_manifest entry 的 asset_ref 无法转换为 McpInterfaceRef（MCP 接口引用）。
5. 对应 registry（注册表）不包含 asset_ref。
6. materializer（物化器）未执行 registry binding validation（注册表绑定校验）就开始 IO（输入输出）。

### 11.3 物化层必须失败的情况

1. workspace_manifest 与 manifest.workspace_manifest_ref 不一致。
2. source_root 不存在或不是目录。
3. workspace_root 不存在或不是目录。
4. 已有 `asset-import-manifest.yaml` 非合法 canonical JSON 或非合法 AgentAssetImportManifest。
5. 已有 `asset-import-manifest.yaml` 不是本次 manifest 的 prefix（前缀），或尝试修改历史 batch（历史批次）。
6. 新 batch 的 source file 不存在。
7. 新 batch 的 source file 是目录、symlink 或非 regular file（普通文件）。
8. source path resolve 后逃出 source_root。
9. target path resolve 后逃出 workspace_root / `00-boardroom/agents`。
10. source file sha256 与 entry.sha256 不一致。
11. target file 已存在且 sha256 与 entry.sha256 不一致。
12. 历史 batch 对应 target file 缺失或 sha256 不一致。
13. 写入后 `asset-import-manifest.yaml` 缺失或 manifest_sha256 非法。

## 12. 测试计划

测试文件：

```text
tests/proving/test_agent_asset_import.py
```

首版单文件覆盖模型层、registry binding（注册表绑定）和 materializer（物化器）层；若测试文件过长，后续可拆成 model/materialize 两个测试文件，但本工作包输出仍以 backlog 声明的测试文件为准。

### 12.1 Negative tests first（负例优先）

模型层负例：

1. `test_agent_asset_import_manifest_rejects_missing_workspace_manifest_ref_or_batches`
2. `test_agent_asset_import_manifest_rejects_missing_or_wrong_manifest_path`
3. `test_agent_asset_import_batch_rejects_missing_source_ref_source_kind_or_imported_at`
4. `test_agent_asset_import_batch_rejects_naive_imported_at`
5. `test_agent_asset_import_manifest_allows_subset_of_asset_kinds`
6. `test_agent_asset_import_entry_rejects_missing_source_path_target_path_or_sha256`
7. `test_agent_asset_paths_reject_absolute_windows_drive_and_backslash`
8. `test_agent_asset_paths_reject_escape_current_parent_empty_or_workspace_misuse`
9. `test_agent_asset_target_path_must_stay_under_boardroom_agents`
10. `test_agent_asset_target_path_must_match_asset_kind_prefix`
11. `test_agent_asset_sha256_must_be_lowercase_hex_digest`
12. `test_agent_asset_import_manifest_rejects_duplicate_asset_source_or_target_refs_within_batch`
13. `test_agent_asset_import_manifest_rejects_redefined_source_ref_or_mutated_historical_asset`

Registry binding（注册表绑定）负例：

1. `test_registry_binding_rejects_role_asset_ref_missing_from_role_registry`
2. `test_registry_binding_rejects_skill_file_ref_missing_from_skill_file_registry`
3. `test_registry_binding_rejects_prompt_ref_missing_from_prompt_registry`
4. `test_registry_binding_rejects_mcp_ref_missing_from_mcp_registry`
5. `test_materializer_rejects_unbound_asset_before_file_io`

物化层负例：

1. `test_materializer_rejects_workspace_manifest_ref_mismatch`
2. `test_materializer_rejects_missing_source_file_for_new_batch`
3. `test_materializer_rejects_source_directory_or_symlink`
4. `test_materializer_rejects_source_hash_mismatch`
5. `test_materializer_rejects_existing_target_with_different_hash`
6. `test_materializer_rejects_existing_manifest_that_is_not_prefix`
7. `test_materializer_rejects_existing_manifest_with_mutated_historical_batch`
8. `test_materializer_rejects_source_root_or_workspace_root_missing`
9. `test_materializer_does_not_write_outside_boardroom_agents`
10. `test_materializer_rejects_missing_or_changed_historical_target`

### 12.2 Happy path（正向路径）

1. `test_materializer_imports_local_agent_asset_bundle_into_boardroom_agents_snapshot`
   - 使用 `tmp_path` 创建 source bundle（来源资产包）：
     - `roles/worker.yaml`
     - `skills/review.md`
     - `prompts/worker.md`
     - `mcp/filesystem.yaml`
   - 构造对应 RoleProfileRegistry（角色模板注册表）、SkillFileSourceRegistry（技能文件来源注册表）、PromptSourceRegistry（提示词来源注册表）和 McpInterfaceRegistry（MCP 接口注册表）。
   - 计算真实 sha256 并构造 AgentAssetImportManifest（智能体资产导入清单）。
   - 调用 `materialize_agent_assets(...)`。
   - 断言四类文件出现在 `workspace_root/00-boardroom/agents/...`。
   - 断言 `workspace_root/00-boardroom/agents/asset-import-manifest.yaml` 存在。
   - 断言 result.materialized_asset_refs / target_paths 与 manifest entries 完全一致。
   - 断言 manifest 文件内容不包含 host absolute source_root（宿主绝对来源根路径）或 workspace_root（工作区根路径）。

2. `test_materializer_allows_tiny_scenario_without_mcp_asset`
   - 只构造 role_config / skill_file / prompt_file 三类 entry（条目）。
   - 不传入 mcp_interface_manifest entry（MCP 接口清单条目）。
   - 断言 manifest 合法、materializer 成功、registry binding 只校验实际出现的 asset kinds（资产类型）。

3. `test_materializer_is_idempotent_when_manifest_is_identical`
   - 连续运行字段完全相同的 manifest 两次。
   - 第二次不报错，result 与第一次一致。

4. `test_materializer_appends_new_source_ref_batch_without_rewriting_history`
   - 首次导入 batch A。
   - 第二次 manifest 包含 batch A + batch B。
   - 断言 batch A 文件 hash 未变，batch B 新文件写入，manifest file 包含两个批次。

5. `test_agent_asset_import_manifest_model_dump_is_stable_and_audit_friendly`
   - 断言 entries 按 target_path 稳定排序。
   - 断言 imported_at 带时区。
   - 断言 canonical JSON dump 稳定且不包含 host absolute paths（宿主绝对路径）。
   - 断言 source_path/target_path/sha256/source_ref/source_kind 可被审计读取。

### 12.3 集成边界回归

1. `tests/execution/test_execution_package_compiler.py` 不应因 V2-060F 新增文件而需要 source_root/workspace_root 参数。
2. `tests/proving/test_workspace_manifest.py`、`tests/proving/test_package_assembler.py`、`tests/proving/test_source_inventory.py`、`tests/proving/test_run_manifest.py`、`tests/proving/test_workspace_evidence_export.py` 应保持通过，证明 V2-060F 不改变 V2-060A~E 既有边界。

## 13. 验证命令

实施完成后建议运行：

```bash
PYTHONPATH="src;." python -m pytest tests/proving/test_agent_asset_import.py -q
PYTHONPATH="src;." python -m pytest tests/proving -q
PYTHONPATH="src;." python -m pytest tests/execution/test_execution_package_compiler.py tests/execution/test_agent_profiles.py tests/proving/test_agent_asset_import.py -q
PYTHONPATH="src;." python -m pytest tests/contracts tests/reducers tests/execution tests/evidence tests/proving tests/negative -q
```

其中第一条证明 V2-060F 自身；第二条证明 Phase 6 proving tests（证明测试）整体未回退；第三条证明 ExecutionPackage compiler（执行包编译器）仍保持零外部文件输入；第四条作为全量回归。

## 14. 完成后文档同步

实现完成并通过验证后，必须按 `backlog.md` 的工作包完成更新协议同步：

1. `doc/04-implementation/backlog.md`
   - V2-060F 状态改为 DONE。
   - 顶部 “当前未完成工作包” 指向 V2-070A。
   - Phase 6 进度从 5 / 6 改为 6 / 6；总计从 40 / 53 改为 41 / 53。
2. `doc/04-implementation/acceptance-criteria.md`
   - 勾选 “Agent asset bundle 导入可审计”。
   - 勾选 “V2-060A ~ V2-060F 六个工作包全部 DONE”。
   - 勾选 “backlog.md 进度总览 Phase 6 显示 6/6”。
   - 如 Phase 6 全部闭合，勾选进入 Phase 7 前置三项。
3. `doc/05-project-log/2026-05.md`
   - 追加 V2-060F 完成记录，包含关键产出文件、negative/happy tests（负例/正例测试）和验证命令证据。
4. `doc/05-project-log/decisions.md`
   - 仅当实现中改变 DEC-0012 语义、引入 force overwrite、远端 fetch、symlink、或把 compiler 重新接入外部文件时才新增决策。按本 spec 实施不需要新增 DEC。
5. `doc/04-implementation/INDEX.md`
   - 本 spec 文件已加入索引；若后续新增实施计划文档，再按文件名补充。

## 15. 评审关注点

1. 是否同意 V2-060F 成为 Phase 6 中唯一带真实文件物化的工作包。
2. 是否同意 `source_root` / `workspace_root` 只作为 materializer 参数，不写入 manifest（清单）。
3. 是否同意 target path（目标路径）固定在 `00-boardroom/agents/{roles,skills,prompts,mcp}/`，manifest path（清单路径）固定为 `00-boardroom/agents/asset-import-manifest.yaml`。
4. 是否同意首版不提供 force overwrite（强制覆盖）和远端 fetch（远端拉取）。
5. 是否同意 `asset-import-manifest.yaml` 文件名保留，但内容采用 canonical JSON（规范 JSON）作为 YAML-compatible subset（YAML 兼容子集），不引入新 YAML 依赖。
6. 是否同意 materializer（物化器）不做事务 rollback（回滚），依赖同 hash 幂等性保证重复执行安全。
7. 是否同意 manifest（清单）不强制四类资产全覆盖；四类覆盖作为能力正例，tiny proving scenario（微型证明场景）可缺 MCP asset（MCP 资产）。
8. 是否同意 asset_ref（资产引用）必须绑定 V2-030A registry refs（注册表引用），避免 process audit（流程审计）链路断裂。
9. 是否同意单文件 cumulative manifest（累计清单）使用 prefix append（前缀追加）规则支持多批次导入，而不是 per-batch manifest（每批次清单）目录。
10. 是否同意 registry ref（注册表引用）一旦在某 batch（批次）内被物化，其对应 bytes（字节内容）不可在后续 batch 中变更；RoleProfile（角色模板）、SkillFile（技能文件）、Prompt（提示词）或 MCP registry ref 的内容演进必须分配新 ref，并在 V2-070 ProcessAudit（流程审计）阶段验证一致。
