# V2-070C ProcessAudit（流程审计）同行评审 spec

## 1. 背景与现实场景

V2-070C 要处理的现实场景是：generated project package（生成项目包）已经完成 implementation（实施）、verification（验证）、evidence export（证据导出）、checker review（检查者评审）和 replay bundle（重放包）构建后，人类 reviewer（评审者）、CEO（首席决策者）或审计员不能只看一堆 raw event（原始事件）和 hash（哈希）就批准 closeout（收尾）。他们需要一套可归档、可复核、可读懂的 ProcessAudit（流程审计）材料，说明这个项目从需求进入到最终收尾，中间每个关键治理、执行、验证和证据闭合环节是如何发生的。

通俗地说，本工作包要做的是“给项目收尾做一套审计说明书和证据目录”。V2-070B 的 ReplayBundle（重放包）证明关键 projection（投影）可以从事件历史重建；V2-070C 在此基础上把过程解释成人类可读、机器可校验的 `30-audit/` 十项产物，并形成一个带 artifact manifest（产物清单）、hash manifest（哈希清单）和 readiness projection（就绪投影）的正式 ProcessAuditBundle（流程审计包）。

本轮 Pre-flight（一致性预检）结论：`backlog.md`（待办）当前未完成工作包为 V2-070C；`acceptance-criteria.md`（验收标准）中 Phase 7 的 AC-V2-CLOSEOUT-003（human-readable process audit，人类可读流程审计）仍未勾选；`src/boardroom_os/audit/process_audit.py`、`tests/closeout/test_process_audit.py` 和 `tests/closeout/test_process_audit_artifacts.py` 尚不存在；V2-070A / V2-070B 已完成并提供 CloseoutGate（收尾门禁） readiness contract（就绪合同）与 ReplayBundle（重放包）物化风格，状态一致，无 drift（漂移）。

## 2. 统一风格来源

### 2.1 V2-070A CloseoutGate（收尾门禁）的边界

V2-070A 已经确定 CloseoutGate（收尾门禁）是纯 domain gate（领域门禁）：

1. 只消费 typed objects（类型化对象）和 readiness summaries（就绪摘要）。
2. 不访问 filesystem（文件系统）。
3. 不运行 git。
4. 不重放 EventLog（事件日志）。
5. 不生成 audit artifacts（审计产物）。
6. 业务不满足时返回 `CloseoutGateResult(verdict="blocked")` 和 typed blockers（类型化阻断项）。
7. 输入结构非法、raw dict（原始字典）或 scalar tuple（标量元组）等结构问题必须 fail closed（失败关闭）。

因此 V2-070C 不能把流程审计构建逻辑塞进 gate（门禁）；它必须独立构建正式 ProcessAudit（流程审计）对象，并投影为 V2-070A 已定义的 `ProcessAuditReadiness（流程审计就绪摘要）`。

### 2.2 V2-070B ReplayBundle（重放包）的物化风格

V2-070B 已经确定 replay（重放）不是一个临时 bool，而是 durable audit artifact（持久审计产物）：

1. `ReplayBundle（重放包）` 有固定 `version: 1`。
2. 所有逻辑产物通过 manifest entry（清单条目）表达。
3. 每个 entry 有 `content_ref（内容引用）` 和 `sha256`。
4. `HashManifest（哈希清单）` 会重新计算 event window（事件窗口）、payload manifest（载荷清单）、artifact manifest（产物清单）、replay report（重放报告）和 attestation（证明条目）hash。
5. readiness projection（就绪投影）会重新校验 bundle 本体和 hash closure（哈希闭合），而不是信任传入的 ready bool。
6. 不引入未实现的插件框架，不提前定义未来 projection kind（投影类型）。

因此 V2-070C 也必须采用同一风格：正式 bundle（包）先闭合，再投影为 CloseoutGate（收尾门禁）能消费的 readiness summary（就绪摘要）。

## 3. 选项背景

### 3.1 方案 A：只生成 ProcessAuditReadiness（流程审计就绪摘要）

V2-070C 只提供一个函数，把调用方传来的 artifact paths（产物路径）和若干 bool 转成 `ProcessAuditReadiness（流程审计就绪摘要）`。

优点：实现最小，能快速让 CloseoutGate（收尾门禁）通过 happy path（正向路径）。

不采用原因：这与 V2-070B 的物化风格不统一。它只能证明“调用方声称十项产物齐了”，不能证明十项 `30-audit/` artifact（审计产物）真的有稳定内容、稳定 hash、可归档 manifest（清单）和可重新校验的 evidence map（证据映射）/ lineage（来源链）。这会让 AC-V2-CLOSEOUT-003（人类可读 process audit 必需）退化为路径列表检查。

### 3.2 方案 B：ProcessAuditBuilder（流程审计构建器）直接写文件到 workspace

V2-070C builder（构建器）直接把十项 `30-audit/` 文件写入 generated project workspace（生成项目工作区），再扫描文件系统生成 readiness summary（就绪摘要）。

优点：贴近最终目录结构，容易人工查看。

不采用原因：这会把 domain artifact model（领域产物模型）、filesystem materializer（文件系统物化器）和 readiness projection（就绪投影）混在一起。V2-070A / V2-070B 当前风格是 typed object（类型化对象）先闭合，外层再决定是否写盘；V2-070C 不应让 filesystem side effect（文件系统副作用）成为核心领域校验前提。

### 3.3 方案 C：ProcessAuditBundle（流程审计包）+ artifact/hash manifest（产物/哈希清单）+ readiness projection（就绪投影）

V2-070C 定义正式 `ProcessAuditBundle（流程审计包）`，包含十项 `30-audit/` artifact（审计产物）的 typed entries（类型化条目）、artifact manifest（产物清单）、hash manifest（哈希清单）、ProcessAuditReport（流程审计报告）和 checked refs（已检查引用）。builder（构建器）只消费 typed inputs（类型化输入），先在内存对象层形成可归档 bundle；`process_audit_readiness(...)` 再重新校验 bundle 并投影为 V2-070A 的 `ProcessAuditReadiness（流程审计就绪摘要）`。

优点：

- 与 V2-070B ReplayBundle（重放包）风格统一。
- 十项 `30-audit/` artifact 有稳定 path、kind、content_ref、sha256 和 hash closure（哈希闭合）。
- CloseoutGate（收尾门禁）继续只消费 readiness summary，不越界构建流程审计。
- 负例可以精确覆盖缺产物、产物不一致、timeline 缺关键事件、agent context index 不完整、artifact lineage 不完整、evidence map 与 final table 不一致等 fail-closed 场景。
- 后续 V2-070E CloseoutPackage（收尾包）可以绑定正式 ProcessAuditBundle，而不是绑定临时路径列表。

代价：

- 比方案 A 多一层 bundle / manifest / hash manifest schema。
- 首版需要为 markdown/json artifact（Markdown/JSON 审计产物）定义最小内容结构。
- V2-070D GitVersionAudit（Git 版本审计）尚未实现时，`git-version-audit.md` 在 V2-070C 中只能作为 process audit artifact（流程审计产物）参与完整性和 hash closure，不负责真实 git 命令执行。

## 4. 选型结论

采用方案 C：ProcessAuditBundle（流程审计包）+ artifact/hash manifest（产物/哈希清单）+ readiness projection（就绪投影）。

核心边界：

1. V2-070C 构建正式 ProcessAuditBundle（流程审计包），不是只构建 `ProcessAuditReadiness（流程审计就绪摘要）`。
2. ProcessAuditBundle 是 durable audit artifact schema（持久审计产物结构），与 V2-070B ReplayBundle（重放包）一样可归档、可 dump JSON、可重新校验 hash closure（哈希闭合）。
3. 首版固定 10 项 `30-audit/` artifact（审计产物），不允许缺项、多项、重名或路径漂移。
4. builder（构建器）只消费 typed V2 facts（类型化 V2 事实），不读取旧 runtime（旧运行时），不从 raw dict（原始字典）猜测状态。
5. builder 不运行 git、不构建 CloseoutPackage（收尾包）、不推进 reducer terminal success（归约器终态成功）。
6. readiness projection 必须重新验证 bundle 内容、manifest、hash closure、timeline/event coverage（时间线/事件覆盖）、agent context index completeness（智能体上下文索引完整性）、artifact lineage（产物来源链）和 evidence map consistency（证据映射一致性）。
7. CloseoutGate（收尾门禁）仍然只消费 V2-070A 已有的 `ProcessAuditReadiness（流程审计就绪摘要）`。

## 5. 目标

1. 新增 `src/boardroom_os/audit/process_audit.py`，定义 ProcessAuditBundle（流程审计包）、ProcessAuditReport（流程审计报告）、ProcessAuditArtifact（流程审计产物）、ProcessAuditArtifactManifest（流程审计产物清单）、ProcessAuditHashManifest（流程审计哈希清单）和 builder/readiness projection（构建器/就绪投影）。
2. 新增 `tests/closeout/test_process_audit.py`，覆盖 ProcessAuditBundle（流程审计包）构建、hash closure（哈希闭合）、readiness projection（就绪投影）和 audit-friendly JSON（审计友好 JSON）。
3. 新增 `tests/closeout/test_process_audit_artifacts.py`，先写 fail-closed negative tests（失败关闭负例测试），证明十项 `30-audit/` 产物缺一不可且内容必须闭合。
4. ProcessAuditBundle 必须生成或持有以下 10 项 logical artifact（逻辑产物）：
   - `30-audit/process-audit.md`
   - `30-audit/timeline.json`
   - `30-audit/decision-log.md`
   - `30-audit/agent-context-index.json`
   - `30-audit/ticket-graph.md`
   - `30-audit/artifact-lineage.json`
   - `30-audit/evidence-map.json`
   - `30-audit/git-version-audit.md`
   - `30-audit/closeout-summary.md`
   - `30-audit/replay-bundle-report.json`
5. 每个 artifact 必须有 path（路径）、kind（类型）、content_ref（内容引用）、content（内容）或 canonical payload（规范载荷）和 sha256（哈希）。
6. ProcessAuditHashManifest 必须重新计算十项 artifact hash、artifact manifest hash、report hash 和 bundle hash，不信任调用方传入的 placeholder hash（占位哈希）。
7. `process_audit_readiness(bundle)` 必须返回 V2-070A 的 `ProcessAuditReadiness（流程审计就绪摘要）`，并在返回前重新验证 bundle。
8. 测试必须证明 timeline.json（时间线）缺关键事件、decision-log.md（决策日志）缺 CEO / human board decision（人类董事会决策）、agent-context-index.json（智能体上下文索引）缺 execution package / model execution profile / provider attempt、artifact-lineage.json（产物来源链）不完整、fallback lineage（降级来源链）不完整、evidence-map.json（证据映射）与 FinalEvidenceTable（最终证据表）不一致、git-version-audit.md（Git 版本审计文件）缺 final commit / dirty status / source inventory hash 时都会失败。
9. 输出必须 audit-friendly（审计友好），不得包含宿主绝对路径、Windows drive（Windows 盘符）、反斜杠路径、临时目录或旧实现路径。

## 6. 非目标

V2-070C 不做以下事情：

1. 不修改 V2-070A CloseoutGate（收尾门禁）的职责边界。
2. 不重新构建 ReplayBundle（重放包）；只消费 V2-070B 产生的 ReplayBundle / ReplayReport（重放报告）或 replay readiness facts（重放就绪事实）。
3. 不运行 git 命令、不读取 git 仓库、不计算真实 final commit SHA（最终提交 SHA）；真实 GitVersionAudit（Git 版本审计）属于 V2-070D。
4. 不创建 CloseoutPackage（收尾包）；最终绑定 gate result（门禁结果）、replay bundle（重放包）、process audit（流程审计）和 git audit（Git 审计）属于 V2-070E。
5. 不推进 closeout reducer（收尾归约器）或 terminal success（终态成功）；这属于 V2-070F。
6. 不读取旧 runtime、旧 closeout state machine（旧收尾状态机）或旧 workflow completion（工作流完成）实现。
7. 不把 process audit artifact 的存在降级为 “path 非空即可”。
8. 不允许 fallback（降级）、placeholder（占位符）或 synthetic evidence（合成证据）满足流程审计。
9. 不把 markdown prose（Markdown 文本说明）当成唯一事实来源；机器可校验的 JSON artifact 必须参与 hash closure（哈希闭合）和 readiness projection（就绪投影）。

## 7. 模块设计

### 7.1 新增文件

```text
src/boardroom_os/audit/process_audit.py
tests/closeout/test_process_audit.py
tests/closeout/test_process_audit_artifacts.py
```

需要同步 `src/boardroom_os/audit/__init__.py` 导出核心对象；如果现有 `__init__.py` 已导出 ReplayBundle（重放包），应追加 ProcessAudit（流程审计）相关对象，不破坏 V2-070B 导出。

### 7.2 建议公开对象

`ProcessAuditReadiness（流程审计就绪摘要）` 和 `ProcessAuditArtifactPath（流程审计产物路径）` 必须从 `boardroom_os.closeout.gate` 复用，不得在 `boardroom_os.audit.process_audit` 中定义 shadow type（影子类型）。

```python
class ProcessAuditError(ValueError): ...

class ProcessAuditBundleRef(NonEmptyTextValue): ...
class ProcessAuditReportRef(NonEmptyTextValue): ...
class ProcessAuditArtifactRef(NonEmptyTextValue): ...
class ProcessAuditManifestRef(NonEmptyTextValue): ...
class ProcessAuditContentRef(NonEmptyTextValue): ...
class ProcessAuditContentHash(NonEmptyTextValue): ...
class ProcessAuditCheckedRef(NonEmptyTextValue): ...

class ProcessAuditArtifactKind(StrEnum):
    PROCESS_AUDIT = "process_audit"
    TIMELINE = "timeline"
    DECISION_LOG = "decision_log"
    AGENT_CONTEXT_INDEX = "agent_context_index"
    TICKET_GRAPH = "ticket_graph"
    ARTIFACT_LINEAGE = "artifact_lineage"
    EVIDENCE_MAP = "evidence_map"
    GIT_VERSION_AUDIT = "git_version_audit"
    CLOSEOUT_SUMMARY = "closeout_summary"
    REPLAY_BUNDLE_REPORT = "replay_bundle_report"

class ProcessAuditArtifactFormat(StrEnum):
    MARKDOWN = "markdown"
    JSON = "json"

class ProcessAuditTimelineEventKind(StrEnum): ...
class ProcessAuditArtifact(BaseModel): ...
class ProcessAuditArtifactManifestEntry(BaseModel): ...
class ProcessAuditArtifactManifest(BaseModel): ...
class ProcessAuditHashManifest(BaseModel): ...
class ProcessAuditReport(BaseModel): ...
class ProcessAuditBundle(BaseModel): ...
class ProcessAuditBuilderInput(BaseModel): ...

def build_process_audit_bundle(builder_input: ProcessAuditBuilderInput) -> ProcessAuditBundle: ...
def process_audit_readiness(bundle: ProcessAuditBundle) -> ProcessAuditReadiness: ...
```

可以采用函数式 builder（构建器）入口，避免提前引入可替换 builder class（构建器类）或 registry（注册表）。

## 8. Schema（结构）设计

### 8.1 Required artifact paths（必需产物路径）

固定为 V2-070A CloseoutGate（收尾门禁）已经声明的 10 项：

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

路径不变量：

1. 必须使用 forward slash（正斜杠）。
2. 必须位于 `30-audit/`。
3. 不允许 absolute path（绝对路径）。
4. 不允许 Windows drive（Windows 盘符）。
5. 不允许反斜杠。
6. 不允许 `.`、`..` 或尾部斜杠。
7. 路径集合必须与必需集合完全一致；缺项、多项、重复项都 fail closed（失败关闭）。

### 8.2 ProcessAuditArtifact（流程审计产物）

建议 schema：

```yaml
artifact_id:
path:
kind:
format: markdown | json
content_ref:
content:
sha256:
source_refs:
```

字段说明：

- `artifact_id`：确定性 ID，建议 `process-audit-artifact.<kind>`。
- `path`：十项固定路径之一，类型复用 `ProcessAuditArtifactPath（流程审计产物路径）`。
- `kind`：必须与 path 一一对应。
- `format`：`.md` 文件为 `markdown`，`.json` 文件为 `json`。
- `content_ref`：逻辑内容引用，不是宿主文件路径。例如 `process-audit-content.timeline`。
- `content`：markdown string（Markdown 字符串）或 canonical JSON payload（规范 JSON 载荷）。
- `sha256`：对 canonical content（规范内容）计算得到的 64 位小写 sha256。
- `source_refs`：该 artifact 使用的 typed input refs（类型化输入引用），用于 checked refs（已检查引用）闭合。

不变量：

1. `path` 与 `kind` 必须一一对应。
2. `format` 必须与 path 后缀一致。
3. `content_ref` 必须非空、唯一、稳定，且不得像文件系统绝对路径。
4. `content` 不得为空。
5. `sha256` 必须等于重新计算的 content hash。
6. `source_refs` 必须非空且唯一。
7. 任意 extra fields（额外字段）必须 fail closed。

### 8.3 ProcessAuditArtifactManifest（流程审计产物清单）

建议 schema：

```yaml
artifact_manifest_id:
project_ref:
entries:
  - artifact_ref:
    path:
    kind:
    format:
    content_ref:
    sha256:
```

不变量：

1. entries 必须恰好 10 条。
2. path 集合必须等于十项固定路径集合。
3. kind 集合必须等于十项固定 kind 集合。
4. artifact_ref、content_ref、path 均不得重复。
5. 每个 sha256 必须为 64 位小写 sha256。
6. manifest 自身必须可 canonical JSON dump（规范 JSON 导出）。
7. 不接受 host absolute path（宿主绝对路径）或 platform-specific path（平台相关路径）。

### 8.4 ProcessAuditHashManifest（流程审计哈希清单）

建议 schema：

```yaml
hash_manifest_id:
project_ref:
artifact_hashes:
  30-audit/process-audit.md: sha256...
  ...
artifact_manifest_hash:
process_audit_report_hash:
bundle_payload_hash:
```

字段说明：

- `artifact_hashes`：十项 artifact path 到 content hash 的映射。
- `artifact_manifest_hash`：对 artifact manifest canonical JSON（规范 JSON）计算。
- `process_audit_report_hash`：对 ProcessAuditReport（流程审计报告）canonical JSON 计算。
- `bundle_payload_hash`：对 bundle 中除 computed bundle hash（计算字段包哈希）之外的稳定 payload 计算。

不变量：

1. artifact_hashes 必须覆盖十项固定路径且无孤儿 path。
2. 每个 hash 必须能从对应 ProcessAuditArtifact.content 重新计算。
3. artifact_manifest_hash 必须能从 ProcessAuditArtifactManifest 重新计算。
4. process_audit_report_hash 必须能从 ProcessAuditReport 重新计算。
5. bundle_payload_hash 必须能从 ProcessAuditBundle 的稳定字段重新计算。
6. 任意 hash missing（哈希缺失）、placeholder hash（占位哈希）或 mismatch（不匹配）必须 fail closed。

### 8.5 ProcessAuditReport（流程审计报告）

建议 schema：

```yaml
process_audit_report_id:
project_ref:
generated_at:
process_audit_ref:
timeline_ref:
decision_log_ref:
agent_context_index_ref:
ticket_graph_ref:
artifact_lineage_ref:
evidence_map_ref:
git_audit_ref:
closeout_summary_ref:
replay_bundle_report_ref:
checked_refs:
```

字段说明：

- `process_audit_ref`：`30-audit/process-audit.md` 的 artifact ref。
- `timeline_ref`：`30-audit/timeline.json` 的 artifact ref。
- `decision_log_ref`：`30-audit/decision-log.md` 的 artifact ref。
- `agent_context_index_ref`：`30-audit/agent-context-index.json` 的 artifact ref。
- `ticket_graph_ref`：`30-audit/ticket-graph.md` 的 artifact ref。
- `artifact_lineage_ref`：`30-audit/artifact-lineage.json` 的 artifact ref。
- `evidence_map_ref`：`30-audit/evidence-map.json` 的 artifact ref。
- `git_audit_ref`：`30-audit/git-version-audit.md` 的 artifact ref。
- `closeout_summary_ref`：`30-audit/closeout-summary.md` 的 artifact ref。
- `replay_bundle_report_ref`：`30-audit/replay-bundle-report.json` 的 artifact ref。
- `checked_refs`：至少包含 project、contract、ticket、provider attempt、verification run、verified evidence、source inventory、final evidence table、checker verdict、replay bundle/report 相关引用。

不变量：

1. 所有 artifact refs 必须能在 artifact manifest 中解析。
2. `generated_at` 必须带时区。
3. `checked_refs` 必须非空且唯一。
4. 不允许缺少 domain-model（领域模型）要求的任何 ref。
5. 任意 extra fields 必须 fail closed。

### 8.6 ProcessAuditBundle（流程审计包）

建议 schema：

```yaml
version: 1
process_audit_bundle_id:
project_ref:
generated_at:
artifacts:
  - ...
artifact_manifest:
hash_manifest:
process_audit_report:
checked_refs:
bundle_hash:
```

字段说明：

- `version`：首版固定为 `1`。
- `process_audit_bundle_id`：确定性 ID，建议由 project_ref（项目引用）和 bundle hash（包哈希）派生。
- `project_ref`：ProjectRef（项目引用），必须与所有输入和 artifact/report 一致。
- `generated_at`：带时区 datetime（日期时间）。
- `artifacts`：十项 ProcessAuditArtifact（流程审计产物）。
- `artifact_manifest`：十项 artifact 的清单。
- `hash_manifest`：十项 artifact 和 report/manifest 的哈希闭合证明。
- `process_audit_report`：流程审计报告索引。
- `checked_refs`：审计过程中检查过的引用集合。
- `bundle_hash`：computed field（计算字段），对稳定 payload 计算。

不变量：

1. `version == 1`。
2. `generated_at` 必须带时区。
3. artifacts 必须恰好 10 项。
4. artifact paths/kinds 必须完整且唯一。
5. artifact_manifest entries 必须与 artifacts 一致。
6. hash_manifest 必须与 artifacts、artifact_manifest、process_audit_report 一致。
7. process_audit_report 所有 refs 必须能解析。
8. checked_refs 必须非空且唯一。
9. 任意 extra fields 必须 fail closed。

## 9. Artifact 内容要求

### 9.1 process-audit.md（流程审计主报告）

必须是 human-readable Markdown（人类可读 Markdown），至少包含以下章节：

1. Requirement interpretation（需求解释）：说明 BoardDirective（董事会指令）/ ProjectCharter（项目章程）如何形成工作。
2. Contract formation（合同形成）：说明 AcceptanceContract（验收合同）和 PackageContract（包合同）如何约束实施。
3. Team execution（团队执行）：说明 AgentSeat（智能体席位）、ExecutionPackage（执行包）和 ProviderAttempt（模型调用尝试记录）如何参与。
4. Evidence verification（证据验证）：说明 VerificationRun（验证运行）、VerifiedEvidence（已验证证据）和 FinalEvidenceTable（最终证据表）如何闭合。
5. Checker review（检查者评审）：说明 CheckerVerdict（检查结论）如何处理 blockers（阻断项）和 notes（备注）。
6. Replay and closeout readiness（重放与收尾就绪）：说明 ReplayBundle（重放包）、GitAuditReadiness（Git 审计就绪摘要）和 ProcessAuditReadiness（流程审计就绪摘要）如何进入收尾。

缺任一章节必须 fail closed。

### 9.2 timeline.json（时间线）

必须是 JSON artifact（JSON 产物），至少覆盖关键事件 kind：

1. `directive_received`
2. `charter_created`
3. `acceptance_contract_created`
4. `package_contract_created`
5. `seat_assigned`
6. `ticket_created`
7. `ticket_started`
8. `provider_attempt_recorded`
9. `work_product_submitted`
10. `command_run_recorded`
11. `evidence_verified`
12. `checker_verdict_recorded`
13. `closeout_prepared`
14. `replay_bundle_materialized`

不变量：

1. timeline events 必须按 timestamp（时间戳）和 graph_version（图版本）稳定排序。
2. 每个 event 必须包含 event_ref、kind、timestamp、actor_ref、graph_version 和 related_refs。
3. 缺任一关键 kind 必须 fail closed。
4. project_ref 必须一致。

### 9.3 decision-log.md（决策日志）

必须是 human-readable Markdown，至少包含：

1. CEO / human board decision（CEO / 人类董事会决策）。
2. Architect / contract decision（架构师 / 合同决策）。
3. Checker decision（检查者决策）。
4. Closeout readiness decision（收尾就绪决策）。

缺 CEO / human board decision 必须 fail closed。

### 9.4 agent-context-index.json（智能体上下文索引）

必须从 `AgentContextIndex（智能体上下文索引）` 或等价 typed input（类型化输入）投影，且每个 entry 至少包含：

1. `execution_package_ref（执行包引用）`
2. `model_execution_profile（模型执行配置）`
3. `provider_attempt_refs（模型调用尝试引用集合）`

不变量：

1. entries 必须非空。
2. 每个 entry.provider_attempt_refs 必须非空。
3. provider_attempt_refs 必须能被 ProcessAuditBuilderInput（流程审计构建输入）的 provider attempt refs 解析。
4. 缺 execution_package_ref、model_execution_profile 或 provider_attempt_ref 必须 fail closed。

### 9.5 ticket-graph.md（任务图说明）

必须说明 ticket graph（任务图）的关键治理状态：

1. ticket refs（任务引用）和状态。
2. acceptance refs（验收引用）。
3. source surface refs（源码面引用）。
4. evidence obligation refs（证据义务引用）。
5. owner seat refs（负责人席位引用）。
6. blocker/rework（阻断/返工）关系。

首版可以是 Markdown summary（Markdown 摘要），但必须由 typed ticket/projection facts（类型化任务/投影事实）生成，不能手写孤立文本。

### 9.6 artifact-lineage.json（产物来源链）

必须表达主链路：

```text
producer attempt -> artifact -> consumer ticket -> evidence claim -> verifier -> closeout
```

每条 lineage edge（来源边）至少包含：

1. producer_attempt_ref
2. artifact_ref 或 source path
3. consumer_ticket_ref
4. evidence_claim_ref 或 verified_evidence_ref
5. verifier_ref 或 verification_run_ref
6. closeout_related_ref

fallback artifact（降级产物）必须额外表达：

```text
fallback decision -> verifier -> evidence map -> closeout
```

不变量：

1. source inventory entries 必须全部有 lineage。
2. final evidence table rows 必须全部能追踪到 lineage。
3. fallback evidence 如果存在，必须有 fallback decision record lineage。
4. 缺 producer attempt、artifact、consumer ticket、evidence claim、verifier 或 closeout 任一环节必须 fail closed。

### 9.7 evidence-map.json（证据映射）

必须与 `FinalEvidenceTable（最终证据表）` 一致，至少包含：

1. acceptance_ref
2. criterion_ref
3. status
4. verified_evidence_refs
5. source_inventory_refs
6. verification_run_refs
7. checker_verdict_ref

不变量：

1. 每个 blocking criterion（阻断验收标准）都必须出现。
2. 每个 satisfied row（已满足行）的 verified_evidence_refs 必须非空。
3. evidence-map.json 中的 rows 必须与 FinalEvidenceTable rows 一致。
4. 不允许 orphan evidence（孤儿证据）。
5. 不一致必须 fail closed。

### 9.8 git-version-audit.md（Git 版本审计说明）

V2-070C 不运行真实 git audit（Git 审计），但该 artifact 必须记录来自 `GitAuditReadiness（Git 审计就绪摘要）` 或后续 V2-070D GitVersionAudit（Git 版本审计）的 typed facts（类型化事实）：

1. final commit SHA（最终提交 SHA）
2. git clean / dirty status（Git 干净/脏状态）
3. source inventory hash（源码清单哈希）
4. source inventory hash match（源码清单哈希匹配）
5. final command evidence at final commit（最终命令证据在最终提交运行）

缺 final commit、dirty status 或 source inventory hash 必须 fail closed。

### 9.9 closeout-summary.md（收尾摘要）

必须 summarize（总结）：

1. package contract ref（包合同引用）。
2. source inventory ref（源码清单引用）。
3. final evidence table ref（最终证据表引用）。
4. checker verdict ref（检查结论引用）。
5. replay readiness summary（重放就绪摘要）。
6. process audit readiness summary（流程审计就绪摘要）。
7. remaining blockers（剩余阻断项），happy path 必须为空。

### 9.10 replay-bundle-report.json（重放包报告）

必须从 V2-070B ReplayBundle（重放包）/ ReplayReport（重放报告）投影，至少包含：

1. replay_bundle_ref
2. replay_report_ref
3. projection kind（投影类型）
4. projection version（投影版本）
5. event range（事件范围）
6. summary hash（摘要哈希）
7. hash chain verified（哈希链已验证）
8. replay passed（重放通过）

不变量：

1. replay_passed 必须为 true。
2. hash_chain_verified 必须为 true。
3. summary_hash 必须与 ReplayBundleReadiness（重放包就绪摘要）一致。
4. projection_versions 必须与 ReplayBundleReadiness 一致。

## 10. Builder（构建器）输入

建议 schema：

```yaml
project_ref:
generated_at:
events:
  - EventRecord...
package_contract:
acceptance_contract:
agent_context_index:
ticket_graph_summary:
source_inventory:
workspace_evidence_bundle:
final_evidence_table:
checker_verdict:
verification_runs:
verified_evidence:
provider_attempt_refs:
replay_bundle:
replay_readiness:
git_audit_readiness:
```

字段说明：

- `events`：EventRecord（事件记录）切片，用于 timeline（时间线）和 decision log（决策日志）。
- `package_contract` / `acceptance_contract`：合同事实，用于 process-audit.md（流程审计主报告）和 evidence-map.json（证据映射）。
- `agent_context_index`：AgentContextIndex（智能体上下文索引），用于 agent-context-index.json。
- `ticket_graph_summary`：任务图摘要；首版可接受 V2-020C/V2-050F 已有 typed projection facts（类型化投影事实）的最小 summary object（摘要对象），但不得 raw dict。
- `source_inventory`：SourceInventory（源码清单），用于 artifact-lineage.json 和 git-version-audit.md。
- `workspace_evidence_bundle`：WorkspaceEvidenceBundle（工作区证据包），用于 artifact refs（产物引用）和 closeout readiness（收尾就绪）。
- `final_evidence_table`：FinalEvidenceTable（最终证据表），用于 evidence-map.json。
- `checker_verdict`：CheckerVerdict（检查结论），用于 decision-log.md 和 closeout-summary.md。
- `verification_runs` / `verified_evidence`：用于 evidence map（证据映射）和 artifact lineage（产物来源链）。
- `provider_attempt_refs`：用于 agent context 与 lineage 闭合。
- `replay_bundle` / `replay_readiness`：来自 V2-070B。
- `git_audit_readiness`：来自 V2-070A/V2-070D 边界的 GitAuditReadiness（Git 审计就绪摘要）。

输入不变量：

1. 所有 tuple/list 字段必须是真的 tuple/list，不接受 scalar string。
2. 所有 typed object 字段必须是 Pydantic model（Pydantic 模型）或已定义值对象，不接受 raw dict。
3. project_ref 必须与所有输入一致。
4. generated_at 必须带时区。
5. events 不可为空，且必须按 graph_version 连续或提供可审计 gap explanation（缺口说明）；首版建议要求连续。
6. provider_attempt_refs 不可为空且唯一。
7. replay_readiness 必须能由 replay_bundle 重新投影得到。
8. git_audit_readiness 必须具备 final commit、source inventory hash 和 dirty status 字段。

## 11. Builder 语义

### 11.1 构建流程

```text
ProcessAuditBuilderInput（流程审计构建输入）
  -> validate typed refs and project alignment（校验类型化引用与项目一致性）
  -> build 10 logical artifacts（构建十项逻辑产物）
  -> compute artifact hashes（计算产物哈希）
  -> build artifact manifest（构建产物清单）
  -> build ProcessAuditReport（构建流程审计报告）
  -> compute hash manifest（计算哈希清单）
  -> build ProcessAuditBundle（构建流程审计包）
  -> process_audit_readiness(bundle)（投影为流程审计就绪摘要）
```

### 11.2 Hash determinism（哈希确定性）

建议规则：

1. JSON content 使用 `json.dumps(payload, sort_keys=True, separators=(",", ":"))` 的 canonical JSON（规范 JSON）。
2. Markdown content 使用 UTF-8 string（UTF-8 字符串）原文计算 sha256。
3. Pydantic model 使用 `model_dump(mode="json")` 后 canonical JSON。
4. artifact manifest、hash manifest、process audit report 和 bundle hash 都必须排除 computed field（计算字段）后重新计算。

### 11.3 Readiness projection（就绪投影）

`process_audit_readiness(bundle)` 必须执行：

1. `_validate_bundle_instance(...)`：重新构造/校验 ProcessAuditBundle（流程审计包）。
2. `_revalidate_artifact_manifest(...)`：校验十项 artifact 与 manifest entries 一致。
3. `_revalidate_hash_manifest(...)`：重新计算所有 artifact/report/manifest hash。
4. `_validate_timeline(...)`：确认 timeline key events（关键时间线事件）齐全。
5. `_validate_agent_context_index(...)`：确认 execution_package_ref、model_execution_profile、provider_attempt_ref 齐全。
6. `_validate_artifact_lineage(...)`：确认主 lineage 和 fallback lineage 闭合。
7. `_validate_evidence_map(...)`：确认 evidence map 与 FinalEvidenceTable 一致。
8. 返回 V2-070A `ProcessAuditReadiness（流程审计就绪摘要）`。

返回字段映射：

```yaml
artifact_paths: bundle.artifact_manifest.paths
all_artifacts_present: true
timeline_key_events_present: true
agent_context_index_complete: true
artifact_lineage_complete: true
evidence_map_consistent_with_final_table: true
```

该函数不得只读取 bundle 中已有 bool；必须重新验证后再投影。

## 12. Fail-closed（失败关闭）规则

### 12.1 模型层必须失败的情况

1. ProcessAuditBundle 缺 `artifacts`、`artifact_manifest`、`hash_manifest` 或 `process_audit_report`。
2. ProcessAuditBundle.version 不是 `1`。
3. generated_at 无 timezone（时区）。
4. artifacts 不是 tuple/list。
5. artifacts 数量不是 10。
6. artifact path 缺项、多项、重复、越界、absolute path、Windows drive、反斜杠、`.`、`..` 或尾部斜杠。
7. artifact kind 与 path 不匹配。
8. artifact format 与文件后缀不匹配。
9. artifact content 为空。
10. artifact sha256 不是 64 位小写 sha256 或与内容不一致。
11. artifact_manifest entries 与 artifacts 不一致。
12. hash_manifest 缺任一 artifact hash、artifact_manifest_hash、process_audit_report_hash 或 bundle_payload_hash。
13. process_audit_report 缺任一十项 artifact ref。
14. checked_refs 为空或重复。
15. 任意 extra fields。

### 12.2 Builder validation（构建器校验）必须失败的情况

1. builder input 传 raw dict 替代 typed model。
2. builder input tuple/list 字段传 scalar string。
3. project_ref 与 events / contracts / evidence / replay / git readiness 不一致。
4. events 为空。
5. provider_attempt_refs 为空。
6. agent_context_index entries 为空。
7. replay_bundle 与 replay_readiness 不一致。
8. git_audit_readiness 缺 final commit / dirty status / source inventory hash。
9. source inventory entries 无法映射到 artifact lineage。
10. final evidence table rows 无法映射到 evidence-map.json。
11. verified evidence 中存在 final table 未引用的 orphan evidence。
12. fallback evidence 存在但缺 fallback decision lineage。

### 12.3 Artifact validation（产物校验）必须失败的情况

1. 十项 `30-audit/` 产物任意一项缺失。
2. `timeline.json` 缺任一关键事件 kind。
3. `decision-log.md` 缺 CEO / human board decision。
4. `agent-context-index.json` 缺 execution_package_ref。
5. `agent-context-index.json` 缺 model_execution_profile。
6. `agent-context-index.json` 缺 provider_attempt_ref。
7. `artifact-lineage.json` 不能表达 `producer attempt -> artifact -> consumer ticket -> evidence claim -> verifier -> closeout`。
8. fallback artifact 缺 `fallback decision -> verifier -> evidence map -> closeout` lineage。
9. `evidence-map.json` 与 FinalEvidenceTable 不一致。
10. `git-version-audit.md` 缺 final commit、dirty status 或 source inventory hash。
11. `replay-bundle-report.json` 与 ReplayBundleReadiness 不一致。
12. `closeout-summary.md` 声称无 blockers，但 checker verdict 或 gate facts 中仍有 blockers。

## 13. 测试计划

测试文件：

```text
tests/closeout/test_process_audit.py
tests/closeout/test_process_audit_artifacts.py
```

### 13.1 Negative tests first（负例优先）

`tests/closeout/test_process_audit_artifacts.py` 建议覆盖：

1. `test_process_audit_rejects_missing_process_audit_markdown`
2. `test_process_audit_rejects_missing_timeline_json`
3. `test_process_audit_rejects_missing_decision_log_markdown`
4. `test_process_audit_rejects_missing_agent_context_index_json`
5. `test_process_audit_rejects_missing_ticket_graph_markdown`
6. `test_process_audit_rejects_missing_artifact_lineage_json`
7. `test_process_audit_rejects_missing_evidence_map_json`
8. `test_process_audit_rejects_missing_git_version_audit_markdown`
9. `test_process_audit_rejects_missing_closeout_summary_markdown`
10. `test_process_audit_rejects_missing_replay_bundle_report_json`
11. `test_process_audit_rejects_extra_audit_artifact_path`
12. `test_process_audit_rejects_duplicate_audit_artifact_path`
13. `test_process_audit_rejects_unsafe_audit_artifact_path`
14. `test_process_audit_rejects_timeline_missing_key_event`
15. `test_process_audit_rejects_decision_log_without_ceo_or_human_board_decision`
16. `test_process_audit_rejects_agent_context_index_without_execution_package_ref`
17. `test_process_audit_rejects_agent_context_index_without_model_execution_profile`
18. `test_process_audit_rejects_agent_context_index_without_provider_attempt_ref`
19. `test_process_audit_rejects_incomplete_artifact_lineage`
20. `test_process_audit_rejects_fallback_lineage_without_decision_record`
21. `test_process_audit_rejects_evidence_map_inconsistent_with_final_table`
22. `test_process_audit_rejects_git_version_audit_without_final_commit`
23. `test_process_audit_rejects_git_version_audit_without_dirty_status`
24. `test_process_audit_rejects_git_version_audit_without_source_inventory_hash`
25. `test_process_audit_rejects_replay_bundle_report_mismatch`
26. `test_process_audit_rejects_hash_manifest_mismatch`
27. `test_process_audit_rejects_raw_dict_inputs`
28. `test_process_audit_rejects_scalar_tuple_inputs`

这些负例应先写，并在实现前得到预期 RED（红灯），例如缺 `boardroom_os.audit.process_audit` 模块或缺对应模型。

### 13.2 Happy path（正向路径）

`tests/closeout/test_process_audit.py` 建议覆盖：

1. `test_process_audit_bundle_materializes_required_audit_artifacts`
   - 构造最小 typed input（类型化输入）。
   - 调用 `build_process_audit_bundle(...)`。
   - 断言 bundle.artifacts 恰好包含十项固定 path。

2. `test_process_audit_bundle_computes_hash_manifest`
   - 断言每项 artifact sha256 与内容一致。
   - 断言 artifact_manifest_hash、process_audit_report_hash 和 bundle hash 稳定。

3. `test_process_audit_readiness_projects_to_closeout_gate_contract`
   - 调用 `process_audit_readiness(bundle)`。
   - 断言返回类型为 V2-070A `ProcessAuditReadiness（流程审计就绪摘要）`。
   - 断言 artifact_paths 与十项固定路径完全一致。
   - 断言五个 readiness bool 均为 true。

4. `test_process_audit_bundle_is_audit_friendly_json`
   - `model_dump(mode="json")` 成功。
   - 输出不含宿主绝对路径、反斜杠路径、旧实现路径或临时目录。

5. `test_process_audit_report_indexes_all_artifacts`
   - 断言 ProcessAuditReport（流程审计报告）引用十项 artifact。
   - 断言 checked_refs（已检查引用）包含关键 contract/evidence/replay/git refs。

6. `test_process_audit_markdown_is_human_readable`
   - 断言 process-audit.md、decision-log.md、ticket-graph.md、git-version-audit.md、closeout-summary.md 含必要标题和 refs。

### 13.3 回归边界

实施完成后应至少回归：

1. `tests/negative/test_closeout_fail_closed.py`，证明 V2-070A CloseoutGate（收尾门禁）仍按 ProcessAuditReadiness（流程审计就绪摘要）阻断缺口。
2. `tests/closeout/test_replay_bundle.py`，证明 V2-070B ReplayBundle（重放包）物化与 readiness projection（就绪投影）未回退。
3. `tests/execution/test_agent_context_index.py`，证明 agent context index（智能体上下文索引）字段语义未被流程审计改写。
4. `tests/proving/test_workspace_evidence_export.py`，证明 WorkspaceEvidenceBundle（工作区证据包）仍由 V2-060E 构建。
5. `tests/proving/test_source_inventory.py` 和 `tests/negative/test_source_inventory_ref_only_rejected.py`，证明 source inventory lineage（源码清单来源链）仍严格。

## 14. 验证命令

实施完成后建议运行：

```bash
PYTHONPATH="src;." python -m pytest tests/closeout/test_process_audit_artifacts.py -q
PYTHONPATH="src;." python -m pytest tests/closeout/test_process_audit.py -q
PYTHONPATH="src;." python -m pytest tests/closeout/test_process_audit_artifacts.py tests/closeout/test_process_audit.py -q
PYTHONPATH="src;." python -m pytest tests/negative/test_closeout_fail_closed.py tests/closeout/test_replay_bundle.py tests/closeout/test_process_audit_artifacts.py tests/closeout/test_process_audit.py -q
PYTHONPATH="src;." python -m pytest tests/contracts tests/reducers tests/execution tests/evidence tests/proving tests/closeout tests/negative -q
```

前两条分别证明 V2-070C 负例和正例；第三条证明 V2-070C 自身；第四条证明 V2-070A/B/C closeout audit chain（收尾审计链）一致；第五条作为全量回归。

## 15. 完成后文档同步

实现完成并通过验证后，必须按 `backlog.md` 的工作包完成更新协议同步：

1. `doc/04-implementation/backlog.md`
   - V2-070C 状态改为 DONE。
   - 顶部“当前未完成工作包”指向 V2-070D。
   - Phase 7 进度从 2 / 6 改为 3 / 6；总计从 43 / 53 改为 44 / 53，具体数字以实施当时 backlog 为准。
2. `doc/04-implementation/acceptance-criteria.md`
   - 勾选 AC-V2-CLOSEOUT-003（人类可读 process audit required，人类可读流程审计必需）。
   - 勾选时必须引用 `tests/closeout/test_process_audit_artifacts.py` 对十项 `30-audit/` 产物缺一不可的证明。
3. `doc/05-project-log/2026-05.md`
   - 追加 V2-070C 完成记录，包含关键产出文件、negative/happy tests（负例/正例测试）和真实验证命令证据。
4. `doc/05-project-log/decisions.md`
   - 仅当实现中改变 V2-070A/B 已确定的边界、把 filesystem writer（文件系统写入器）纳入 domain builder（领域构建器）、或提前实现 V2-070D/E/F 职责时才新增决策。按本 spec 实施不需要新增 DEC。
5. `doc/04-implementation/INDEX.md`
   - 本 spec 文件加入索引。

## 16. 评审关注点

1. 是否同意 V2-070C 采用 ProcessAuditBundle（流程审计包），而不是只生成 ProcessAuditReadiness（流程审计就绪摘要）。
2. 是否同意 V2-070C 与 V2-070B 统一使用 artifact manifest（产物清单）、content_ref（内容引用）、sha256 和 hash manifest（哈希清单）。
3. 是否同意 builder（构建器）不直接写 filesystem（文件系统），而是在 typed object（类型化对象）层先闭合十项 artifact。
4. 是否同意十项 `30-audit/` artifact paths 固定且缺一不可。
5. 是否同意 `process_audit_readiness(...)` 必须重新校验 bundle，而不是信任 bundle 内部 bool。
6. 是否同意 `git-version-audit.md` 在 V2-070C 中只消费 GitAuditReadiness（Git 审计就绪摘要）或后续 GitVersionAudit（Git 版本审计）事实，不运行真实 git。
7. 是否同意 artifact-lineage.json（产物来源链）必须表达 `producer attempt -> artifact -> consumer ticket -> evidence claim -> verifier -> closeout`。
8. 是否同意 fallback lineage（降级来源链）必须表达 `fallback decision -> verifier -> evidence map -> closeout`。
9. 是否同意 evidence-map.json（证据映射）必须与 FinalEvidenceTable（最终证据表）逐行一致。
10. 是否同意 V2-070C 不提前创建 CloseoutPackage（收尾包）或推进 CloseoutReducer（收尾归约器）。
