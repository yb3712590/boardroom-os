# V2-060D RunManifest（运行清单）同行评审 spec

## 1. 背景与现实场景

V2-060D 要处理的现实场景是：Boardroom OS V2（董事会式智能体团队框架）已经能通过 V2-060B PackageAssembly（项目包装配结果）确认 `10-project`（生成项目包）里必须包含 `run-manifest.json`（运行清单文件），也能通过 V2-040D CommandRunner（命令执行器）运行 PackageContract（包合同）里声明的 command（命令）。下一步需要把这两件事闭合起来：最终 package（项目包）里的 `run-manifest.json` 必须成为 PackageContract（包合同）run/test commands（运行/测试命令）的可审计镜像，而不是一个只占位的文件名。

通俗地说，系统不能只交付源码和测试文件，然后在收尾时临时挑一个命令跑一下。它必须提前声明：“这个项目怎么启动、怎么测试、在哪个 cwd（工作目录）执行、命令 ID 是什么”。后续 CommandRunner（命令执行器）只能执行已经被 PackageContract（包合同）和 RunManifest（运行清单）共同声明的 command（命令），这样 verification evidence（验证证据）才不是 synthetic verification（合成验证）或临时补证据。

本轮 Pre-flight（一致性预检）结论：`backlog.md`（待办）当前未完成工作包为 V2-060D；`src/boardroom_os/workspace/run_manifest.py` 和 `tests/proving/test_run_manifest.py` 尚不存在；`acceptance-criteria.md`（验收标准）中 AC-V2-PACKAGE-002（可运行包验收）仍未勾选，状态一致，无 drift（漂移）。

## 2. 选项背景

### 2.1 方案 1：RunManifest（运行清单）作为 PackageContract（包合同）的可执行镜像

RunManifest（运行清单）是一个 typed domain model（类型化领域模型），从 PackageContract（包合同）生成或校验，包含 `package_contract_ref`、`package_root`、`run_commands`、`test_commands`、`workspace_manifest_ref` 等字段。builder（构建函数）要求 RunManifest（运行清单）的 commands（命令）与 PackageContract（包合同）的 run/test commands（运行/测试命令）完全一致。

CommandRunner（命令执行器）现有边界保持不变：它继续消费 ExecutionPackage（执行包）和 PackageContract（包合同）来执行命令。V2-060D 新增一个 RunManifest binding validator（运行清单绑定校验器），用于证明 runner 即将执行的 command（命令）同时存在于 RunManifest（运行清单）与 PackageContract（包合同）。

优点：

- 不破坏 V2-040D 已稳定的 CommandRunner（命令执行器）接口。
- 能满足 AC-V2-PACKAGE-002（可运行包验收）：可运行软件项目必须有可验证 run/test commands（运行/测试命令）。
- 适合 negative tests first（负例优先）：可以直接证明缺 run/test commands、manifest/contract mismatch（清单/合同不一致）、未声明命令执行均 fail closed（失败关闭）。
- 与 V2-060B PackageAssembly（项目包装配结果）和 V2-060E EvidenceExport（证据导出）职责清晰分离。

代价：

- RunManifest（运行清单）本身仍是领域对象，不在 V2-060D 内写入磁盘。
- CommandRunner（命令执行器）不会被强制改签名，调用方需要在运行前显式通过 binding validator（绑定校验器）。
- `run-manifest.json`（运行清单文件）的实际导出和进入 `20-evidence`（证据区）留给 V2-060E。

### 2.2 方案 2：把 CommandRunnerInput（命令执行器输入）改为必须携带 RunManifest（运行清单）

CommandRunner（命令执行器）执行时同时消费 ExecutionPackage（执行包）、PackageContract（包合同）和 RunManifest（运行清单）。

优点：执行边界最硬，漏调 binding validator（绑定校验器）的可能性更低。

不采用原因：这会扩大 V2-040D 已稳定接口，影响现有 CommandRunner（命令执行器）、RuntimeExecutor（运行时执行器）和相关测试；V2-060D 的目标是证明 package runnable contract（包可运行合同）闭合，不应反向重构 runtime execution boundary（运行时执行边界）。

### 2.3 方案 3：只确认 PackageAssembly（项目包装配结果）包含 `run-manifest.json`

只沿用 V2-060B 的检查，确认 `10-project/run-manifest.json` 是 package artifact（包产物）。

优点：实现量最小。

不采用原因：这只能证明文件名存在，不能证明 manifest commands（清单命令）与 PackageContract（包合同）一致，也不能阻止 runner 执行未声明 command（命令），不足以支撑 AC-V2-PACKAGE-002（可运行包验收）。

## 3. 选型结论

采用方案 1：RunManifest（运行清单）作为 PackageContract（包合同）的可执行镜像，并新增显式 command binding validator（命令绑定校验器）。

该方案的核心判断是：V2-060D 应当证明“package 声明的运行方式是可验证的”，但不应把 CommandRunner（命令执行器）重新设计成依赖 workspace package（工作区包）模块。CommandRunner（命令执行器）仍然只负责真实运行 declared command（声明命令）并生成 VerificationRun（验证运行）；RunManifest（运行清单）负责在 package assembly（项目包装配）与 command evidence（命令证据）之间提供可审计绑定。

## 4. 目标

1. 新增 RunManifest（运行清单）模型，绑定 WorkspaceManifest（工作区清单）、PackageContract（包合同）、package root（包根）和 declared commands（声明命令）。
2. 新增 RunManifestCommand（运行清单命令）或直接复用 PackageCommand（包命令），表达 run/test command（运行/测试命令）的 command_id（命令 ID）、label（标签）、command（命令参数）和 cwd（工作目录）。
3. 新增 `build_run_manifest()`（构建运行清单函数），从 PackageContract（包合同）生成确定性 RunManifest（运行清单）。
4. 新增 `validate_run_manifest_binding()`（校验运行清单绑定函数）或等价入口，证明 RunManifest（运行清单）、PackageContract（包合同）和即将运行的 command_id（命令 ID）一致。
5. 证明软件项目缺 run/test commands（运行/测试命令）无法形成有效 RunManifest（运行清单）。
6. 证明 manifest command（清单命令）与 PackageContract（包合同）不一致时 fail closed（失败关闭）。
7. 证明 runner 执行未声明 command（命令）无法通过 binding（绑定）和 CommandRunner（命令执行器）校验。
8. 证明 declared command（声明命令）可被 CommandRunner（命令执行器）真实执行，并生成 VerificationRun（验证运行）。

## 5. 非目标

V2-060D 不做以下事情：

1. 不创建 workspace（工作区）目录，不写入 `run-manifest.json` 文件。
2. 不导出 `20-evidence`（证据区）中的 verification runs（验证运行）或 stdout/stderr（标准输出/标准错误）；这些属于 V2-060E。
3. 不重新实现 CommandRunner（命令执行器）的进程执行逻辑。
4. 不修改 RuntimeExecutor（运行时执行器）事实事件边界。
5. 不构建 SourceInventory（源码清单），也不把 `run-manifest.json` 伪装成 provider-backed source artifact（模型产出的源码产物）。
6. 不调用 git，不证明 final commit（最终提交）或 dirty status（脏工作区状态）。
7. 不读取旧 runtime（旧运行时）、旧 workspace（旧工作区）或旧测试作为实现依据。

## 6. 模块设计

### 6.1 新增文件

```text
src/boardroom_os/workspace/run_manifest.py
tests/proving/test_run_manifest.py
```

需要同步 `src/boardroom_os/workspace/__init__.py` 导出核心对象，保持 workspace package（工作区包）公开入口一致。

### 6.2 建议公开对象

```python
class RunManifestError(ValueError): ...

class RunManifestRef(NonEmptyTextValue): ...

class RunManifestCommandKind(StrEnum):
    RUN = "run"
    TEST = "test"

class RunManifestCommand(BaseModel): ...
class RunManifest(BaseModel): ...
class RunManifestBinding(BaseModel): ...


def build_run_manifest(
    *,
    workspace_manifest: WorkspaceManifest,
    package_contract: PackageContract,
) -> RunManifest: ...


def validate_run_manifest_binding(
    *,
    run_manifest: RunManifest,
    package_contract: PackageContract,
    command_id: ContractId,
) -> RunManifestBinding: ...
```

`RunManifestError`（运行清单错误）用于 builder/service（构建器/服务）层的语义错误；Pydantic（Pydantic 模型）结构错误仍可抛 `ValidationError`（校验错误）。

## 7. Schema（结构）设计

### 7.1 RunManifestCommand（运行清单命令）

建议 schema：

```yaml
command_id:
kind: run | test
label:
command:
  - python
  - -m
  - pytest
cwd:
```

字段说明：

- `command_id`：`ContractId`（合同 ID），必须与 PackageCommand.command_id（包命令 ID）一致。
- `kind`：`RunManifestCommandKind`（运行清单命令类型），区分 run command（运行命令）和 test command（测试命令）。
- `label`：命令的人类可读标签，必须与 PackageCommand.label（包命令标签）一致。
- `command`：tuple of str（字符串元组），必须与 PackageCommand.command（包命令参数）一致。
- `cwd`：相对 package root（包根）的 cwd（工作目录），必须与 PackageCommand.cwd（包命令工作目录）一致。

不变量：

1. `command` 必须非空，且每个 item（项目）非空。
2. `cwd` 必须非空。
3. run manifest（运行清单）内 command_id（命令 ID）必须唯一。
4. run/test kind（运行/测试类型）由 PackageContract.run_commands/test_commands（包合同运行/测试命令）来源决定，不能由调用方随意改写。
5. 任意 extra fields（额外字段）必须 fail closed（失败关闭）。

### 7.2 RunManifest（运行清单）

建议 schema：

```yaml
run_manifest_id:
workspace_manifest_ref:
package_contract_ref:
package_root:
commands:
  - command_id:
    kind:
    label:
    command:
    cwd:
```

字段说明：

- `run_manifest_id`：`RunManifestRef`（运行清单引用），建议确定性 ID：`run-manifest.<workspace_manifest_ref>.<package_contract_ref>`。
- `workspace_manifest_ref`：`WorkspaceManifestRef`（工作区清单引用）。
- `package_contract_ref`：`ContractId`（包合同 ID）。
- `package_root`：`WorkspacePath`（工作区路径），必须等于 `10-project`。
- `commands`：tuple of RunManifestCommand（运行清单命令集合），按 kind（类型）和 command_id（命令 ID）稳定排序。

不变量：

1. `workspace_manifest.package_contract_ref` 必须等于 `package_contract.package_contract_id`。
2. `workspace_manifest.package_root.value` 必须等于 `package_contract.package_root`，且必须为 `10-project`。
3. software/mixed package（软件/混合包）必须有至少一个 run command（运行命令）和至少一个 test command（测试命令）。PackageContract（包合同）已有同类校验，RunManifest（运行清单）仍应在 builder 层 fail closed（失败关闭），避免绕过 PackageContract 构造入口。
4. RunManifest.commands（运行清单命令集合）必须与 PackageContract.run_commands + PackageContract.test_commands（包合同运行命令和测试命令）一一对应。
5. command_id（命令 ID）、label（标签）、command（命令参数）和 cwd（工作目录）必须完全一致。
6. command_id（命令 ID）不得在 run/test 两类中重复。
7. `model_dump()`（模型导出）输出必须稳定、可审计。

### 7.3 RunManifestBinding（运行清单绑定）

建议 schema：

```yaml
run_manifest_ref:
package_contract_ref:
command_id:
kind:
command:
cwd:
```

用途：

`RunManifestBinding`（运行清单绑定）是 `validate_run_manifest_binding()`（校验运行清单绑定函数）的成功结果，用来证明某个 command_id（命令 ID）在 RunManifest（运行清单）和 PackageContract（包合同）中完全一致。它不是 VerificationRun（验证运行），不包含 exit_code（退出码）、stdout_ref（标准输出引用）或 stderr_ref（标准错误引用）。真实执行证据仍然只能来自 CommandRunner（命令执行器）。

不变量：

1. command_id（命令 ID）必须同时存在于 RunManifest（运行清单）和 PackageContract（包合同）。
2. 两边匹配到的 command（命令）必须完全一致。
3. 如果 RunManifest（运行清单）中的 command kind（命令类型）与 PackageContract（包合同）来源不一致，必须失败。
4. 绑定成功不代表命令已运行；它只允许后续 CommandRunner（命令执行器）运行该 declared command（声明命令）。

## 8. 数据流

```text
WorkspaceManifest（工作区清单，来自 V2-060A）
PackageContract（包合同，来自 V2-010D）
  -> build_run_manifest（构建运行清单）
  -> RunManifest（运行清单）
      -> validate_run_manifest_binding（校验运行清单绑定）
      -> CommandRunner（命令执行器，来自 V2-040D）
      -> VerificationRun（验证运行）
      -> V2-060E EvidenceExport（证据导出）
```

关键边界：

- RunManifest（运行清单）证明 package（项目包）声明了可运行命令。
- RunManifestBinding（运行清单绑定）证明某条命令同时被 manifest（清单）和 contract（合同）声明。
- CommandRunner（命令执行器）证明命令真实运行，并产生 VerificationRun（验证运行）。
- RunManifest（运行清单）不替代 VerificationRun（验证运行）或 EvidenceVerifier（证据验证器）。

## 9. 错误处理

1. Pydantic models（Pydantic 模型）使用 `ConfigDict(frozen=True, extra="forbid")`，拒绝未知字段和运行时篡改。
2. command shape（命令形状）错误抛 `ValidationError`（校验错误）。
3. `build_run_manifest()`（构建运行清单函数）和 `validate_run_manifest_binding()`（校验运行清单绑定函数）遇到语义错误时抛 `RunManifestError`（运行清单错误）。
4. 错误信息应指出具体 invariant（不变量），例如 `run command is required`、`test command is required`、`run manifest command must match package contract command`、`command is not declared in run manifest`。
5. 不提供 fallback（降级）或默认命令；调用方必须补齐 PackageContract（包合同）中的真实 declared commands（声明命令）。

## 10. 测试方案

新增测试文件：

```text
tests/proving/test_run_manifest.py
```

测试应遵循 negative tests first（负例优先）：先写 backlog（待办）明确要求的三个失败场景，再补充 manifest/contract binding（清单/合同绑定）一致性负例，最后写 declared command（声明命令）可由 CommandRunner（命令执行器）真实执行的 happy path（正向路径）。

### 10.1 必须先写的 negative tests（负例测试）

1. software package（软件包）缺 run commands（运行命令）时无法构建 RunManifest（运行清单）。
2. software package（软件包）缺 test commands（测试命令）时无法构建 RunManifest（运行清单）。
3. runner 执行未在 RunManifest（运行清单）中声明的 command_id（命令 ID）时必须失败。
4. manifest command（清单命令）与 PackageContract（包合同）同 command_id（命令 ID）但 label（标签）不同，必须失败。
5. manifest command（清单命令）与 PackageContract（包合同）同 command_id（命令 ID）但 command tuple（命令参数元组）不同，必须失败。
6. manifest command（清单命令）与 PackageContract（包合同）同 command_id（命令 ID）但 cwd（工作目录）不同，必须失败。
7. manifest command kind（清单命令类型）把 run command（运行命令）标成 test command（测试命令）或反向标记，必须失败。
8. RunManifest（运行清单）缺 PackageContract（包合同）中的任意 declared command（声明命令）时失败。
9. RunManifest（运行清单）包含 PackageContract（包合同）未声明 command（命令）时失败。
10. RunManifest.commands（运行清单命令集合）中 command_id（命令 ID）重复时失败。
11. workspace_manifest.package_contract_ref（工作区清单包合同引用）与 package_contract.package_contract_id（包合同 ID）不一致时失败。
12. package_root（包根）不是 `10-project` 或与 WorkspaceManifest（工作区清单）不一致时失败。
13. command（命令）为空、command item（命令项目）为空、cwd（工作目录）为空时失败。
14. 传入 extra fields（额外字段）时失败。

### 10.2 Happy path（正向路径）

1. tiny software package（微型软件包）PackageContract（包合同）声明一个 run command（运行命令）和一个 test command（测试命令）。
2. `build_run_manifest()`（构建运行清单函数）成功返回 RunManifest（运行清单）。
3. RunManifest（运行清单）绑定正确的 `workspace_manifest_ref`、`package_contract_ref` 和 `package_root == 10-project`。
4. commands（命令集合）按确定性顺序输出，重复构建得到相同 `run_manifest_id` 与相同 command order（命令顺序）。
5. `validate_run_manifest_binding()`（校验运行清单绑定函数）对 run/test command（运行/测试命令）均返回 RunManifestBinding（运行清单绑定）。
6. 对已绑定的 declared command（声明命令），CommandRunner（命令执行器）可执行本地确定性命令并生成 VerificationRun（验证运行）。
7. VerificationRun（验证运行）包含 exit_code（退出码）、stdout_ref（标准输出引用）、stderr_ref（标准错误引用）、runner_ref（执行器引用）、environment_profile_ref（环境配置引用）和 workspace_snapshot_ref（工作区快照引用）。
8. `model_dump()`（模型导出）输出稳定、可审计。

## 11. 验收口径

V2-060D 完成后必须满足：

1. `src/boardroom_os/workspace/run_manifest.py` 存在，并定义 RunManifest（运行清单）、RunManifestCommand（运行清单命令）、RunManifestBinding（运行清单绑定）和 `build_run_manifest()` / `validate_run_manifest_binding()` 或等价入口。
2. `tests/proving/test_run_manifest.py` 存在，并覆盖 backlog（待办）明确要求的 negative tests（负例测试）：软件项目缺 run/test commands、runner 执行未声明命令、manifest command 与 PackageContract（包合同）不一致必须失败。
3. happy path（正向路径）证明 declared command（声明命令）可被 CommandRunner（命令执行器）执行并生成 VerificationRun（验证运行）。
4. 实现不创建目录、不写文件、不导出 `20-evidence`、不修改 RuntimeExecutor（运行时执行器）治理边界。
5. RunManifest（运行清单）证明 package runnable contract（包可运行合同），但不替代 VerificationRun（验证运行）或 EvidenceVerifier（证据验证器）。
6. 文档同步：完成实施后需按 backlog（待办）协议更新 `backlog.md`、`acceptance-criteria.md`、`doc/05-project-log/2026-05.md`；若只写本 spec（规格）则只需更新 `doc/04-implementation/INDEX.md`。

## 12. 同行评审关注点

请重点审查：

1. RunManifest（运行清单）作为 PackageContract（包合同）可执行镜像是否足以满足 V2-060D，而不需要修改 CommandRunner（命令执行器）签名。
2. `validate_run_manifest_binding()`（校验运行清单绑定函数）是否应该成为 RuntimeExecutor（运行时执行器）调用前的强制前置；本 spec 选择先作为 V2-060D 的显式校验入口，不改 V2-040D 既有接口。
3. RunManifest.commands（运行清单命令集合）是否应直接复用 PackageCommand（包命令）还是引入 RunManifestCommand（运行清单命令）并添加 `kind` 字段；本 spec 倾向引入 RunManifestCommand，以便审计区分 run/test command（运行/测试命令）。
4. RunManifest（运行清单）是否应记录 command output refs（命令输出引用）；本 spec 选择不记录，stdout/stderr refs（标准输出/标准错误引用）只属于 VerificationRun（验证运行）。
5. `run-manifest.json` 是否应进入 SourceInventory（源码清单）；V2-060C spec（规格）已选择不进入，V2-060D 只证明 command binding（命令绑定），不伪造 provider attempt lineage（模型调用尝试来源链）。
6. 是否需要在 V2-060D 物化 `run-manifest.json` 文件；本 spec 选择不物化，把导出交给 V2-060E EvidenceExport（证据导出）或后续 materializer（物化器）。
