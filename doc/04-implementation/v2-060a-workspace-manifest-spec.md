# V2-060A WorkspaceManifest（工作区清单）同行评审 spec

## 1. 背景与现实场景

V2-060A 要处理的现实场景是：Boardroom OS V2（董事会式智能体团队框架）已经具备 contract（合同）、ticket graph（任务图）、ExecutionPackage（执行包）、ProviderAttempt（模型调用尝试记录）、EvidenceVerifier（证据验证器）和 CompletionGate（完成门禁）等内核能力；下一步要进入 generated project package（生成项目包）阶段，把 agent team（智能体团队）自治写代码过程中的治理材料、真正交付物、证据材料和人类审计材料放入一个稳定、可验证、可重放的 workspace（工作区）。

通俗地说，V2-060A 不是开始“施工写项目”，而是先画清楚“工地分区图”：

- `00-boardroom/` 放治理事实和 agent team（智能体团队）过程材料；
- `10-project/` 放最终交付给用户的 generated project package（生成项目包）；
- `20-evidence/` 放机器可验证和人类可审计的证据；
- `30-audit/` 放人类可读的 process audit（流程审计）与 replay（重放）材料。

本轮已确认采用“严格固定四区”口径：V2-060A 第一版只表达 durable/auditable workspace（持久可审计工作区），明确排除 build cache（构建缓存）、secrets/credentials（密钥/凭据）和 runtime scratch（运行时草稿缓存）。这些临时或敏感材料不能成为 workspace contract（工作区合同）的一部分。

## 2. 目标

1. 新增 `WorkspaceManifest`（工作区清单）模块，用 typed model（类型化模型）表达 generated project workspace（生成项目工作区）的四个固定顶层分区。
2. 证明 workspace（工作区）是 generated project（生成项目）的 staging area（暂存/装配区），不是 Boardroom OS V2 框架仓库自己的源码布局。
3. 让 `PackageContract.package_root`（包合同中的包根目录）只能绑定到 `10-project`，并且必须处于 workspace（工作区）内部。
4. 让后续 V2-060B PackageAssembler（包装配器）、V2-060C SourceInventory（源码清单）、V2-060E EvidenceExport（证据导出）和 V2-060F AgentAssetImport（智能体资产导入）共享同一套 canonical roots（规范根路径）。
5. 用 fail-closed（失败关闭）测试证明缺 `10-project`、缺 `20-evidence`、package root（包根目录）逃逸 workspace（工作区）等情况不能通过。

## 3. 非目标

V2-060A 不做以下事情：

1. 不创建目录、不写文件系统、不复制 source files（源码文件）。目录创建和文件写入属于 V2-060B PackageAssembler（包装配器）或更靠后的 workspace orchestration（工作区编排）。
2. 不写 `package-contract.json`、`run-manifest.json`、README 或 AGENTS.md；这些属于 V2-060B/V2-060D。
3. 不计算 source file hash（源码文件哈希）、不构建 SourceInventory（源码清单）；这些属于 V2-060C。
4. 不导出 FinalEvidenceTable（最终证据表）、VerificationRun（验证运行）或 command output（命令输出）；这些属于 V2-060E。
5. 不导入 role config（角色配置）、skill file（技能文件）、prompt file（提示词文件）或 MCP interface manifest（MCP 接口清单）；这些属于 V2-060F。
6. 不新增 scratch/cache/secrets 顶层目录；临时缓存和密钥只能作为外部引用或被显式排除。
7. 不读取旧 runtime（旧运行时）、旧 project workspace（旧项目工作区）或旧 tests（旧测试）作为实现依据。

## 4. 选型结论

采用“类型化 manifest（清单）+ 严格四区 + PackageContract（包合同）绑定校验”方案。

### 4.1 被采用方案：严格固定四区

`WorkspaceManifest`（工作区清单）只接受以下四个顶层 section（分区）：

```text
00-boardroom
10-project
20-evidence
30-audit
```

每个 section（分区）都有明确职责，不允许新增第五个 durable section（持久分区），也不允许把 section root（分区根）改名为 `src`、`project`、`evidence`、`audit` 或框架仓库路径。

优点：

- 精确对应 `generated-project-workspace.md`（生成项目工作区架构文档）的结构。
- 对 V2-060A 的 fail-closed（失败关闭）目标最强。
- 能防止把 `00-boardroom` / `10-project` / `20-evidence` / `30-audit` 误认为 Boardroom OS V2 repo（框架仓库）的源码布局。
- 后续模块可以通过 manifest（清单）读取 canonical roots（规范根路径），不再各自硬编码路径。

代价：

- 第一版不表达扩展区、临时缓存区或第三方工具工作目录。
- 如果未来需要 long-running sandbox（长时运行沙箱）或 large artifact cache（大产物缓存），必须另行设计为 non-durable external ref（非持久外部引用），不能直接塞进 workspace manifest（工作区清单）。

### 4.2 未采用方案：固定四区 + 扩展区

允许除四个固定区之外新增 `40-cache/`、`tmp/`、`scratch/` 等扩展区。

不采用原因：V2-060A 的首要目标是建立清晰、可审计、可交付的 workspace boundary（工作区边界）。扩展区会让后续 assembler（装配器）和 evidence export（证据导出）需要额外判断“哪些区算审计输入”，容易弱化 fail-closed（失败关闭）约束。

### 4.3 未采用方案：只校验必需区

只要求存在 package root（包根）、evidence root（证据根）和 audit root（审计根），不限制其他顶层区。

不采用原因：过于宽松，无法充分证明 generated project workspace（生成项目工作区）不是框架 repo layout（仓库布局），也无法阻止离散 source artifact（源码片段）绕过 `10-project` 聚合成最终 package（包）。

### 4.4 未采用方案：V2-060A 直接创建目录

V2-060A 在构造 manifest（清单）时直接 `mkdir` 四区。

不采用原因：会把 schema validation（结构校验）和 filesystem side effect（文件系统副作用）混在一起。V2-060A 应该只定义和验证 workspace topology（工作区拓扑）；真正创建目录属于装配或运行阶段。

## 5. 模块设计

### 5.1 新增文件

```text
src/boardroom_os/workspace/manifest.py
tests/proving/test_workspace_manifest.py
```

如当前 `src/boardroom_os/workspace/` 仅有 `.gitkeep`，实现时需要新增 `src/boardroom_os/workspace/__init__.py`，但 V2-060A 的 backlog（待办）输出文件只要求 `manifest.py` 和测试文件。是否导出 `__all__` 可按现有包导出风格处理。

### 5.2 建议公开对象

```python
class WorkspaceManifestError(ValueError): ...

class WorkspaceManifestRef(NonEmptyTextValue): ...
class WorkflowRef(NonEmptyTextValue): ...
class WorkspacePath(NonEmptyTextValue): ...

class WorkspaceSection(StrEnum):
    BOARDROOM = "boardroom"
    PROJECT = "project"
    EVIDENCE = "evidence"
    AUDIT = "audit"

class WorkspaceSectionPath(BaseModel): ...
class WorkspaceManifest(BaseModel): ...

def build_workspace_manifest(
    *,
    workflow_ref: WorkflowRef,
    workspace_root: WorkspacePath,
    package_contract: PackageContract,
) -> WorkspaceManifest: ...
```

`WorkspaceManifestError`（工作区清单错误）用于 service/factory（服务/工厂）层的语义错误；Pydantic（Pydantic 模型）结构错误仍可抛 `ValidationError`（校验错误）。

## 6. Schema（结构）设计

### 6.1 WorkspacePath（工作区路径）

`WorkspacePath`（工作区路径）是逻辑 POSIX relative path（POSIX 风格相对路径），不是本机绝对路径。

必须满足：

1. 非空，去除首尾空白后仍非空。
2. 使用 `/` 作为路径分隔符。
3. 不得是 absolute path（绝对路径），例如 `/tmp/project` 必须失败。
4. 不得包含 Windows drive prefix（Windows 盘符前缀），例如 `C:\\tmp` 或 `C:/tmp` 必须失败。
5. 不得包含 `..` segment（上级目录片段）。
6. 不得包含空 segment（空路径片段），例如 `10-project//src` 必须失败。
7. 不得包含 `.` segment（当前目录片段），例如 `./10-project` 或 `10-project/.` 必须失败。
8. 不得包含反斜杠 `\\`。
9. 不得以 `/` 结尾；如实现选择 normalize（归一化）尾部斜杠，必须保证序列化输出稳定为无尾斜杠形式。

建议实现方式：把输入保留为 string（字符串）以符合现有合同模型风格，但用 `PurePosixPath`（纯 POSIX 路径）或等价字符串校验做 fail-closed（失败关闭）验证。

### 6.2 WorkspaceSectionPath（工作区分区路径）

建议 schema：

```yaml
section:
relative_path:
```

字段说明：

- `section`：`WorkspaceSection`（工作区分区枚举），只能是 `boardroom` / `project` / `evidence` / `audit`。
- `relative_path`：`WorkspacePath`（工作区路径），必须是 workspace root（工作区根）下的顶层相对路径。

Canonical mapping（规范映射）：

| WorkspaceSection（工作区分区） | relative_path（相对路径） | 职责 |
|---|---|---|
| `boardroom` | `00-boardroom` | 治理材料、workflow metadata（流程元数据）、tickets（任务）、agents（智能体）、process-audit drafts（流程审计草稿） |
| `project` | `10-project` | 最终 generated project package（生成项目包） |
| `evidence` | `20-evidence` | verification runs（验证运行）、command output（命令输出）、source inventory（源码清单）、final evidence table（最终证据表） |
| `audit` | `30-audit` | process audit（流程审计）、timeline（时间线）、decision log（决策日志）、replay report（重放报告） |

不变量：

1. `relative_path` 必须精确等于该 section（分区）的 canonical path（规范路径）。
2. `relative_path` 必须是单个 top-level segment（顶层路径片段），不允许 `10-project/src` 作为 section root（分区根）。
3. 任意 extra fields（额外字段）必须 fail closed（失败关闭）。

### 6.3 WorkspaceManifest（工作区清单）

建议 schema：

```yaml
workspace_manifest_id:
workflow_ref:
workspace_root:
package_contract_ref:
sections:
  - section: boardroom
    relative_path: 00-boardroom
  - section: project
    relative_path: 10-project
  - section: evidence
    relative_path: 20-evidence
  - section: audit
    relative_path: 30-audit
```

字段说明：

- `workspace_manifest_id`：`WorkspaceManifestRef`（工作区清单引用），建议确定性 ID：`workspace-manifest.<workflow_ref>`。
- `workflow_ref`：`WorkflowRef`（工作流引用），表示 `workspace/<workflow_id>/` 中的 workflow identifier（工作流标识）。
- `workspace_root`：`WorkspacePath`（工作区根路径），例如 `workspace/workflow-tiny-fullstack`。
- `package_contract_ref`：`ContractId`（合同 ID），绑定 active PackageContract（活跃包合同）。
- `sections`：四个 `WorkspaceSectionPath`（工作区分区路径），必须完整、唯一且精确匹配 canonical mapping（规范映射）。

派生属性建议：

```python
@property
def boardroom_root(self) -> WorkspacePath: ...  # 00-boardroom

@property
def package_root(self) -> WorkspacePath: ...  # 10-project

@property
def evidence_root(self) -> WorkspacePath: ...  # 20-evidence

@property
def audit_root(self) -> WorkspacePath: ...  # 30-audit

def section_path(self, section: WorkspaceSection) -> WorkspacePath: ...

def full_section_path(self, section: WorkspaceSection) -> WorkspacePath: ...
```

`full_section_path()`（完整分区路径）只做逻辑拼接，例如 `workspace/workflow-tiny-fullstack/10-project`，不检查本地文件系统存在性。

Manifest-level invariants（清单级不变量）：

1. 必须正好包含四个 section（分区），不多不少。
2. 四个 section（分区）必须分别是 `boardroom`、`project`、`evidence`、`audit`，且每种只出现一次。
3. `project` section（项目分区）的 `relative_path` 必须是 `10-project`。
4. `evidence` section（证据分区）的 `relative_path` 必须是 `20-evidence`。
5. `audit` section（审计分区）的 `relative_path` 必须是 `30-audit`。
6. `boardroom` section（治理分区）的 `relative_path` 必须是 `00-boardroom`。
7. 任一 root path（根路径）不得逃逸 workspace root（工作区根）。由于 section paths（分区路径）是相对路径，逃逸主要通过 absolute path（绝对路径）、`..`、`.`、反斜杠或多 segment section root（多片段分区根）体现。
8. `workspace_root` 本身必须是相对逻辑路径，且不能落到本 repo 源码路径，例如 `src/boardroom_os`、`tests`、`doc` 这类框架仓库目录不能作为 generated workspace root（生成项目工作区根）。
9. `workspace_manifest_id` 必须与 `workflow_ref` 稳定对应，避免同一 workflow（工作流）出现多个不可比较的 manifest refs（清单引用）。
10. 任意 extra fields（额外字段）必须 fail closed（失败关闭）。

第 8 条建议第一版使用 reserved repo prefixes（框架仓库保留前缀）检查：

```text
src
src/boardroom_os
tests
doc
scripts
examples
backend
```

这样可以直接防止把 Boardroom OS V2 repo layout（框架仓库布局）误用为 generated project workspace（生成项目工作区）。如果同行评审认为该规则过硬，也可以降级为仅在 tests（测试）中覆盖 `src/boardroom_os` 和 `tests` 两个最危险路径。

### 6.4 build_workspace_manifest（工作区清单构建函数）

建议公开一个小型 factory（工厂函数），而不是让调用方到处手写四个 section（分区）：

```python
def build_workspace_manifest(
    *,
    workflow_ref: WorkflowRef,
    workspace_root: WorkspacePath,
    package_contract: PackageContract,
) -> WorkspaceManifest:
    ...
```

构建规则：

1. `package_contract.package_root` 必须精确等于 `10-project`。
2. `package_contract.package_contract_id` 写入 `package_contract_ref`。
3. `sections` 使用 canonical mapping（规范映射）自动生成。
4. `workspace_manifest_id` 使用 deterministic ref（确定性引用）派生，例如 `workspace-manifest.<workflow_ref.value>`。
5. 如果 `package_contract.package_root` 是 `/tmp/project`、`../project`、`project`、`src/boardroom_os` 或 `10-project/src`，必须 fail closed（失败关闭）。

这个 factory（工厂函数）是 V2-060A 与 V2-010D PackageContract（包合同）的最小绑定点。它不读取、创建或写入 `package-contract.json` 文件。

## 7. 数据流

```text
PackageContract（包合同，来自 V2-010D）
  -> build_workspace_manifest（构建工作区清单）
  -> WorkspaceManifest（工作区清单）
      -> boardroom_root: 00-boardroom（治理区）
      -> package_root: 10-project（项目包区）
      -> evidence_root: 20-evidence（证据区）
      -> audit_root: 30-audit（审计区）
  -> V2-060B PackageAssembler（包装配器）
  -> V2-060C SourceInventory（源码清单）
  -> V2-060E EvidenceExport（证据导出）
  -> V2-060F AgentAssetImport（智能体资产导入）
```

关键边界：

- `WorkspaceManifest`（工作区清单）只提供 topology（拓扑）和 canonical roots（规范根路径）。
- `WorkspaceManifest`（工作区清单）不证明任何文件已经存在。
- `WorkspaceManifest`（工作区清单）不代表 `10-project` 已经可运行；run/test command binding（运行/测试命令绑定）属于 V2-060D。
- `WorkspaceManifest`（工作区清单）不代表 evidence bundle（证据包）已经完整；evidence export（证据导出）属于 V2-060E。

## 8. 错误处理

1. Pydantic models（Pydantic 模型）使用 `ConfigDict(frozen=True, extra="forbid")`，拒绝运行时篡改和未知字段。
2. Value objects（值对象）继承或复用现有 `NonEmptyTextValue`（非空文本值对象）风格，保持与 contracts（合同）模块一致。
3. `WorkspacePath`（工作区路径）校验失败时抛 `ValidationError`（校验错误）。
4. `build_workspace_manifest()`（工作区清单构建函数）遇到 PackageContract（包合同）语义不匹配时抛 `WorkspaceManifestError`（工作区清单错误），例如 `PackageContract.package_root != "10-project"`。
5. 错误信息应指出具体被拒绝的 invariant（不变量），例如 `project section must be 10-project`、`workspace path must be relative`、`package root must be inside workspace`。
6. 不提供 fallback（降级）或自动修复路径；调用方必须修正合同或输入。

## 9. 测试方案

新增测试文件：

```text
tests/proving/test_workspace_manifest.py
```

测试应遵循 negative tests first（负例优先）：先写失败用例证明缺区、路径逃逸和 repo layout misuse（仓库布局误用）不能通过，再写 tiny happy path（微型正向路径）。

### 9.1 必须先写的 negative tests（负例测试）

1. `WorkspaceManifest`（工作区清单）缺 `project` section（项目分区）时失败，对应 backlog（待办）中的“缺 10-project 必须失败”。
2. `WorkspaceManifest`（工作区清单）缺 `evidence` section（证据分区）时失败，对应 backlog（待办）中的“缺 20-evidence 必须失败”。
3. `PackageContract.package_root`（包合同包根）为 `/tmp/project`、`../10-project` 或 `project` 时，`build_workspace_manifest()`（工作区清单构建函数）失败，对应“package root 不在 workspace 内必须失败”。
4. `project` section path（项目分区路径）不是 `10-project` 时失败，例如 `project`、`src`、`src/boardroom_os`。
5. `evidence` section path（证据分区路径）不是 `20-evidence` 时失败，例如 `evidence`、`10-project/evidence`。
6. `audit` section path（审计分区路径）不是 `30-audit` 时失败。
7. `boardroom` section path（治理分区路径）不是 `00-boardroom` 时失败。
8. 出现第五个顶层 durable section（持久分区）时失败，例如 `40-cache`、`tmp`、`scratch`。
9. 重复 section（重复分区）时失败，例如两个 `project` section。
10. section path（分区路径）包含 absolute path（绝对路径）、`..`、`.`、反斜杠或空 segment（空片段）时失败。
11. `workspace_root`（工作区根）落到框架 repo layout（仓库布局）时失败，例如 `src/boardroom_os`、`tests`、`doc`。
12. `workspace_manifest_id`（工作区清单引用）与 `workflow_ref`（工作流引用）不匹配时失败。
13. 传入 extra fields（额外字段）时失败。
14. 将 build cache（构建缓存）、secrets（密钥）或 runtime scratch（运行时草稿）作为 section（分区）时失败。

### 9.2 Happy path（正向路径）

1. tiny PackageContract（微型包合同）声明 `package_root="10-project"` 时，`build_workspace_manifest()`（工作区清单构建函数）成功生成四区 manifest（清单）。
2. manifest（清单）可定位：
   - `boardroom_root == "00-boardroom"`
   - `package_root == "10-project"`
   - `evidence_root == "20-evidence"`
   - `audit_root == "30-audit"`
3. `full_section_path(WorkspaceSection.PROJECT)`（项目分区完整路径）稳定返回 `workspace/<workflow_id>/10-project` 形态的逻辑路径。
4. `model_dump()`（模型导出）输出稳定、可审计，section order（分区顺序）固定为 boardroom/project/evidence/audit。
5. 同一 `workflow_ref`、`workspace_root` 和 `PackageContract`（包合同）重复构建，得到相同 `workspace_manifest_id` 和 section paths（分区路径）。

## 10. 验收口径

V2-060A 完成后必须满足：

1. `src/boardroom_os/workspace/manifest.py` 存在，并定义 `WorkspaceManifest`（工作区清单）及其路径/分区校验。
2. `tests/proving/test_workspace_manifest.py` 存在，并覆盖 backlog（待办）明确要求的 negative tests（负例测试）：package root 不在 workspace 内、缺 `10-project`、缺 `20-evidence`。
3. happy path（正向路径）证明 tiny workspace manifest（微型工作区清单）能定位 package root（包根）、evidence root（证据根）和 audit root（审计根）。
4. 实现不创建目录、不写 package 文件、不构建 SourceInventory（源码清单）、不导出 evidence（证据）。
5. `WorkspaceManifest`（工作区清单）明确固定四区，不允许扩展 durable sections（持久分区）。
6. `PackageContract.package_root`（包合同包根）与 `WorkspaceManifest.package_root`（工作区清单包根）一致且固定为 `10-project`。
7. 文档同步：完成实施后需按 backlog（待办）协议更新 `backlog.md`、`acceptance-criteria.md`、`doc/05-project-log/2026-05.md`；若只写本 spec（规格）则只需更新 `doc/04-implementation/INDEX.md`。

## 11. 同行评审关注点

请重点审查：

1. “严格固定四区”是否足以覆盖 agent team framework（智能体团队框架）自治写代码所需的 durable/auditable workspace（持久可审计工作区）。
2. build cache（构建缓存）、secrets（密钥）和 runtime scratch（运行时草稿）是否应完全排除在 `WorkspaceManifest`（工作区清单）之外；本 spec 选择排除。
3. `workspace_root`（工作区根）是否应允许绝对路径；本 spec 选择第一版只接受逻辑相对路径，避免机器相关路径污染 replay（重放）。
4. 是否需要在 V2-060A 就定义 directory creation（目录创建）接口；本 spec 选择不做，留给 assembler/orchestration（装配器/编排）。
5. `PackageContract.package_root`（包合同包根）是否必须固定为 `10-project`；本 spec 选择必须固定，以保证最终交付物永远聚合到 generated project package（生成项目包）。
6. repo layout misuse（仓库布局误用）规则是否应该拒绝所有 `src`、`tests`、`doc`、`scripts`、`examples` 前缀；本 spec 推荐拒绝，以防把 generated workspace（生成工作区）误作 Boardroom OS V2 自身仓库结构。
7. 是否接受传入 `sections`（分区集合）手写清单，还是只允许通过 `build_workspace_manifest()`（工作区清单构建函数）创建；本 spec 允许 typed model（类型化模型）直接构造但必须经过同样严格校验，同时推荐生产路径使用 factory（工厂函数）。
