# V2-070B ReplayBundle（重放包）同行评审 spec

## 1. 背景与现实场景

V2-070B 要处理的现实场景是：generated project package（生成项目包）准备进入 closeout（收尾）时，审计员不能只相信 runtime（运行时）当前内存状态或一句“workflow completed（工作流完成）”。审计员需要拿到一份可归档、可重新校验的 ReplayBundle（重放包），证明关键 projection summary（投影摘要）确实可以从 EventLog（事件日志）、payload manifest（载荷清单）、artifact manifest（产物清单）和 hash manifest（哈希清单）重建出来，且 replay input（重放输入）没有被静默篡改。

通俗地说，本工作包要做的是“给收尾审计材料装一个可重放证据盒”。今天盒子里只放一条 `seat_assignment_graph`（席位分配图）证明：这些 ticket（任务）为什么分配给这些 agent seat（智能体席位）、ready/blocked（就绪/阻塞）状态能否从事件历史重建。盒子的外层结构用 `attestations`（证明条目）列表，以便未来 V2-070F / V2-080 增加 closeout reducer（收尾归约器）或更多 projection（投影）证明时，不破坏已经归档的老 replay bundle。

本轮 Pre-flight（一致性预检）结论：`backlog.md`（待办）当前未完成工作包为 V2-070B；`src/boardroom_os/audit/replay_bundle.py` 和 `tests/closeout/test_replay_bundle.py` 尚不存在；`acceptance-criteria.md`（验收标准）中 Phase 7 的 AC-V2-CLOSEOUT-002（replay bundle required，重放包必需）仍未勾选；状态一致，无 drift（漂移）。

## 2. 选项背景

### 2.1 方案 A：单 projection 顶级字段

`ReplayBundle`（重放包）直接包含 `seat_assignment_graph_summary`、`event_range`、`projection_version`、`artifact_manifest_ref`、`hash_manifest_ref` 和 `replay_report_ref` 等顶级字段。

优点：字段最少，测试最直观。

不采用原因：ReplayBundle（重放包）是 durable audit artifact（持久审计产物），不是临时 runtime object（运行时对象）。如果今天把 `seat_assignment_graph_summary` 固化为顶级字段，未来 V2-070F / V2-080 增加 ticket graph（任务图）、evidence map（证据映射）或 closeout reducer（收尾归约器）重放时，要么破坏老 bundle schema（老包结构），要么顶级字段并列堆积，要么提前引入 schema migration（结构迁移）。这些都会让“半年前签发的 bundle 今天还能不能重新校验”变成合规风险。

### 2.2 方案 B：完整多 projection 抽象层

`ReplayBundle`（重放包）定义 `ReplayerProtocol`（重放器协议）、`ReplayerRegistry`（重放器注册表）、插件式 dispatch（分发）和多 projection 注册机制。

优点：未来扩展能力强。

不采用原因：这是真正的过早抽象。当前 V2-070B 只有 V2-020F 已实现的 `ProjectionReplay`（投影重放）和 `seat_assignment_graph`（席位分配图）summary（摘要）。现在定义插件层、注册表或通用 replayer protocol（重放协议）会把未实现 projection 的行为猜进架构，违反 YAGNI（不做不需要的事）和 fail-closed（失败关闭）边界。

### 2.3 方案 C：轻量版 B，attestations 列表但只实现一种 kind

`ReplayBundle`（重放包）顶层包含 `attestations: tuple[ReplayAttestation, ...]`（证明条目集合）。每条 `ReplayAttestation`（重放证明条目）有 `kind` 字段，首版 `Literal["seat_assignment_graph"]`（字面量类型）只允许一个实现。builder（构建器）和 verifier（验证器）只处理这个 kind，不预写未实现 projection 名称、不定义插件注册表、不写空 TODO 分支。

优点：

- durable artifact schema（持久产物结构）一开始就是可追加证明条目的形态。
- 首版实现仍然只支持已存在的 `seat_assignment_graph`，范围窄。
- 未来扩展时只需扩展 `kind` union（类型联合）和新增明确分支；老 bundle 仍可读取和重新校验。
- 没有 ReplayerProtocol / ReplayerRegistry / plugin dispatch（插件分发）等过早抽象。

代价：

- 比方案 A 多一个列表层，以及“首版列表必须恰好一条且 kind 正确”的 schema 断言。
- CloseoutGate（收尾门禁）当前仍消费 V2-070A 已定义的 `ReplayBundleReadiness`（重放包就绪摘要），V2-070B 需要提供从 ReplayBundle 到 readiness summary 的投影函数。

## 3. 选型结论

采用方案 C：轻量版 B。

核心边界：

1. `ReplayBundle`（重放包）是可归档的 durable audit artifact schema（持久审计产物结构），顶层使用 `attestations`（证明条目）列表。
2. 首版 `ReplayAttestation.kind`（证明条目类型）只允许 `"seat_assignment_graph"`，不预声明 `ticket_graph`、`evidence_map`、`closeout_reducer` 等未实现名字。
3. 不定义 `ReplayerProtocol`（重放器协议）、`ReplayerRegistry`（重放器注册表）、插件入口或动态 dispatch（分发）。
4. builder（构建器）只消费已有 `ProjectionReplaySummary`（投影重放摘要）、ordered EventRecord（有序事件记录）和 manifest/hash typed inputs（清单/哈希类型化输入），不重新解释 runtime state（运行时状态）。
5. V2-070B 只产出 replay bundle readiness（重放包就绪摘要）给 V2-070A CloseoutGate（收尾门禁）消费，不创建 CloseoutPackage（收尾包）、不推进 reducer terminal success（归约器终态成功）。

## 4. 目标

1. 新增 `src/boardroom_os/audit/replay_bundle.py`，定义 ReplayBundle（重放包）、ReplayAttestation（重放证明条目）、event window/hash chain/hash manifest/artifact manifest/replay report 等最小模型和 builder（构建器）。
2. 新增 `tests/closeout/test_replay_bundle.py`，先写 fail-closed（失败关闭）负例，再写 happy path（正向路径）。
3. ReplayBundle（重放包）必须包含 event range（事件范围）、projection version（投影版本）、artifact manifest（产物清单）、hash manifest（哈希清单）、event log hash chain（事件日志哈希链）和 replay report（重放报告）。
4. ReplayBundle（重放包）必须能从 V2-020F 的 `ProjectionReplaySummary`（投影重放摘要）生成 `seat_assignment_graph` attestation（席位分配图证明条目）。
5. ReplayBundle（重放包）必须证明 replay input（重放输入）没有被静默篡改：event window hash（事件窗口哈希）、event hash chain（事件哈希链）、artifact manifest hash（产物清单哈希）、payload manifest hash（载荷清单哈希）和 replay report hash（重放报告哈希）必须闭合。
6. ReplayBundle（重放包）必须提供 `to_closeout_readiness(...)` 或等价函数，把正式 bundle 投影为 V2-070A 的 `ReplayBundleReadiness`（重放包就绪摘要）。
7. 输出对象必须 audit-friendly JSON（审计友好 JSON），不包含宿主绝对路径、不包含平台相关路径、不读取旧 runtime（旧运行时）。
8. 测试必须证明缺 event range、projection version mismatch（投影版本不匹配）、artifact hash missing（产物哈希缺失）、event log hash chain / hash manifest missing（事件日志哈希链 / 哈希清单缺失）、replay report missing（重放报告缺失）都会失败。

## 5. 非目标

V2-070B 不做以下事情：

1. 不实现 branchable governance replay（可分叉治理重放）的 CEO decision（CEO 决策）、branch identity（分支身份）或 successor history（后继历史）。本轮只做 closeout audit replay（收尾审计重放）归档包。
2. 不定义多 projection plugin framework（多投影插件框架）。
3. 不预写未实现的 `ReplayAttestation.kind`（证明条目类型）名称。
4. 不改造 V2-020F `ProjectionReplay`（投影重放）或 InMemoryEventLog（内存事件日志）的最小接口；hash chain / hash manifest（哈希链 / 哈希清单）在 replay bundle 层处理。
5. 不生成 `30-audit/` 的 10 项 process audit artifact（流程审计产物）；那属于 V2-070C。
6. 不运行 git、不生成 GitVersionAudit（Git 版本审计）；那属于 V2-070D。
7. 不创建 CloseoutPackage（收尾包）；那属于 V2-070E。
8. 不实现 closeout reducer（收尾归约器）或 terminal success projection（终态成功投影）；那属于 V2-070F。
9. 不读取旧实现，不迁移旧 workflow completion（工作流完成）或旧 closeout state machine（收尾状态机）。
10. 不允许 fallback（降级）或 placeholder manifest（占位清单）满足 replay evidence（重放证据）。

## 6. 模块设计

### 6.1 新增文件

```text
src/boardroom_os/audit/replay_bundle.py
tests/closeout/test_replay_bundle.py
```

若 `src/boardroom_os/audit/` 目录不存在，应新增 `__init__.py` 并导出核心对象。该目录属于 V2-070 audit（审计）模块，不是 generated project workspace（生成项目工作区）的 `30-audit/` 目录。

### 6.2 建议公开对象

`ReplaySummaryHash`（重放摘要哈希）、`EventRangeRef`（事件范围引用）和 `ProjectionVersionRef`（投影版本引用）必须从 `boardroom_os.closeout.gate` 复用，不得在 `boardroom_os.audit.replay_bundle` 中重新定义，避免 replay bundle readiness（重放包就绪摘要）与 CloseoutGate（收尾门禁）字段出现 shadow type（影子类型）不兼容。

```python
class ReplayBundleError(ValueError): ...

class ReplayBundleRef(NonEmptyTextValue): ...
class ReplayAttestationRef(NonEmptyTextValue): ...
class ReplayReportRef(NonEmptyTextValue): ...
class ReplayManifestRef(NonEmptyTextValue): ...
class ReplayArtifactRef(NonEmptyTextValue): ...
class ReplayHashRef(NonEmptyTextValue): ...
class ReplayContentHash(NonEmptyTextValue): ...

class ReplayAttestationKind(StrEnum):
    SEAT_ASSIGNMENT_GRAPH = "seat_assignment_graph"

class ReplayManifestKind(StrEnum):
    EVENT_WINDOW = "event_window"
    PAYLOAD_MANIFEST = "payload_manifest"
    ARTIFACT_MANIFEST = "artifact_manifest"
    HASH_MANIFEST = "hash_manifest"
    REPLAY_REPORT = "replay_report"

class ReplayEventWindow(BaseModel): ...
class ReplayEventHashNode(BaseModel): ...
class ReplayHashManifest(BaseModel): ...
class ReplayManifestEntry(BaseModel): ...
class ReplayArtifactManifest(BaseModel): ...
class ReplayReport(BaseModel): ...
class ReplayAttestation(BaseModel): ...
class ReplayBundle(BaseModel): ...
class ReplayBundleBuilderInput(BaseModel): ...
class ReplayBundleBuilder(BaseModel | plain class): ...
```

也可以用函数式入口替代 builder class（构建器类）：

```python
def build_replay_bundle(input: ReplayBundleBuilderInput) -> ReplayBundle: ...
def replay_bundle_readiness(bundle: ReplayBundle) -> ReplayBundleReadiness: ...
```

## 7. Schema（结构）设计

### 7.1 ReplayBundle（重放包）

建议 schema：

```yaml
version: 1
replay_bundle_id:
project_ref:
generated_at:
attestations:
  - ...
hash_manifest:
  ...
artifact_manifest:
  ...
replay_report:
  ...
checked_refs:
  - ...
```

字段说明：

- `version`：首版固定为 `1`。
- `replay_bundle_id`：确定性 ID，建议由 `project_ref`、attestation ids（证明条目 ID）和 bundle hash（包哈希）派生。
- `project_ref`：ProjectRef（项目引用），必须与 attestation/event summary（证明条目/事件摘要）一致。
- `generated_at`：带时区 datetime（日期时间）。
- `attestations`：ReplayAttestation（重放证明条目）列表。V2-070B 首版必须恰好一条，且 kind 为 `seat_assignment_graph`。
- `hash_manifest`：ReplayHashManifest（重放哈希清单），证明 event window、payload manifest、artifact manifest、replay report 和 attestation summary hashes（证明摘要哈希）闭合。
- `artifact_manifest`：ReplayArtifactManifest（重放产物清单），列出 replay bundle 依赖的 payload/artifact/report refs（载荷/产物/报告引用）及 hash。
- `replay_report`：ReplayReport（重放报告），记录 replay passed（重放通过）、summary hash（摘要哈希）、event range（事件范围）和 projection version（投影版本）。
- `checked_refs`：审计引用集合，至少包含 event ids（事件 ID）、payload refs（载荷引用）、artifact manifest ref、hash manifest ref、replay report ref、summary hash。

不变量：

1. `version == 1`。
2. `generated_at` 必须带时区。
3. `attestations` 必须是 tuple/list，不接受 scalar string（标量字符串）。
4. V2-070B 首版 `attestations` 必须恰好一条，kind 必须为 `seat_assignment_graph`。
5. `attestation_id` 必须唯一。
6. `project_ref` 必须与每条 attestation / report / event window 一致。
7. `hash_manifest`、`artifact_manifest`、`replay_report` 必须存在且互相引用一致。
8. `checked_refs` 必须非空且唯一。
9. 任意 extra fields（额外字段）必须 fail closed（失败关闭）。

### 7.2 ReplayAttestation（重放证明条目）

建议 schema：

```yaml
attestation_id:
kind: seat_assignment_graph
project_ref:
projection_version:
event_window:
event_window_hash:
payload_manifest_ref:
artifact_manifest_ref:
hash_manifest_ref:
replay_report_ref:
summary_hash:
replay_passed: true
```

字段说明：

- `kind`：首版仅允许 `seat_assignment_graph`。
- `projection_version`：ProjectionVersionRef（投影版本引用），建议首版使用 `projection.seat_assignment_graph.v1` 或等价稳定值；必须与 `ProjectionReplaySummary.projection_kind`（投影重放摘要类型）一致。
- `event_window`：ReplayEventWindow（重放事件窗口），包含 first/last graph version（首尾图版本）、first/last event id（首尾事件 ID）和 event count（事件数量）。
- `event_window_hash`：对 canonical event window（规范事件窗口）和事件 hash chain terminal（哈希链终端）计算出的稳定 hash。
- `payload_manifest_ref`：payload manifest（载荷清单）引用。
- `artifact_manifest_ref`：artifact manifest（产物清单）引用。
- `hash_manifest_ref`：hash manifest（哈希清单）引用。
- `replay_report_ref`：replay report（重放报告）引用。
- `summary_hash`：必须等于 `ProjectionReplaySummary.summary_hash`（投影重放摘要哈希）。
- `replay_passed`：必须为 true。

不变量：

1. `kind` 不允许未知字符串。
2. `projection_version` 必须非空。
3. `event_window` 不得为空，且 first/last graph version 必须与 summary.event_range（摘要事件范围）一致。
4. `event_window.event_count` 必须等于输入事件数量，也必须等于 summary.event_count。
5. `summary_hash` 必须为 64 位小写 sha256 hex digest。
6. `event_window_hash` 必须为 64 位小写 sha256 hex digest。
7. `replay_passed` 必须为 true。
8. `kind.value == projection_summary.projection_kind`，因为 ProjectionReplaySummary.projection_kind（投影重放摘要类型）是 `Literal["seat_assignment_graph"]`（字面量类型），而 ReplayAttestationKind（重放证明条目类型）是 StrEnum（字符串枚举），实施时必须显式比较 enum value（枚举值）。
9. manifest/report refs 必须能在 bundle 的 hash/artifact/report 中闭合。

### 7.3 ReplayEventWindow（重放事件窗口）

建议 schema：

```yaml
project_ref:
first_graph_version:
last_graph_version:
first_event_id:
last_event_id:
event_count:
```

不变量：

1. graph version（图版本）必须为正数。
2. `first_graph_version <= last_graph_version`。
3. `event_count > 0`。
4. `event_count == last_graph_version - first_graph_version + 1`，因为 V2-020F audit replay（审计重放）要求 graph_version 连续。
5. first/last event id（首尾事件 ID）必须非空。
6. `project_ref` 必须与所有 events（事件）一致。

### 7.4 ReplayEventHashNode（重放事件哈希节点）与 hash chain（哈希链）

建议 schema：

```yaml
event_id:
graph_version:
event_hash:
previous_hash:
chain_hash:
```

计算建议：

- `event_hash = sha256(canonical_json(event.model_dump(mode="json")))`
- 第一条事件 `previous_hash = "0" * 64`
- `chain_hash = sha256(previous_hash + event_hash)`，按 graph_version 顺序迭代
- event window terminal hash（事件窗口终端哈希）为最后一个 `chain_hash`

不变量：

1. hash node 数量必须等于 event_count。
2. graph_version 必须严格递增且连续。
3. event ids 必须唯一。
4. 每个 hash 都必须是 64 位小写 sha256 hex digest。
5. 任何 event_hash / previous_hash / chain_hash 缺失或不一致必须 fail closed。

### 7.5 ReplayHashManifest（重放哈希清单）

建议 schema：

```yaml
hash_manifest_id:
project_ref:
event_hash_chain:
terminal_event_chain_hash:
event_window_hash:
payload_manifest_hash:
artifact_manifest_hash:
replay_report_hash:
attestation_hashes:
  attestation-id: sha256...
```

字段说明：

- `event_hash_chain`：ReplayEventHashNode（事件哈希节点）列表。
- `terminal_event_chain_hash`：最后一个 chain hash（链哈希）。
- `event_window_hash`：由 event window + terminal hash 计算。
- `payload_manifest_hash`：payload manifest（载荷清单）内容 hash。首版 payload manifest 可作为 `ReplayManifestEntry` 集合表达。
- `artifact_manifest_hash`：artifact manifest（产物清单）内容 hash。
- `replay_report_hash`：ReplayReport（重放报告）内容 hash。
- `attestation_hashes`：每条 ReplayAttestation（重放证明条目）的 canonical hash。

不变量：

1. hash chain（哈希链）不可为空。
2. terminal hash 必须等于最后一个 node.chain_hash。
3. event_window_hash 必须与 attestation.event_window_hash 一致。
4. replay_report_hash 必须能从 bundle.replay_report 重新计算。
5. artifact_manifest_hash 必须能从 bundle.artifact_manifest 重新计算。
6. attestation_hashes 必须覆盖全部 attestations，且不能有孤儿 attestation id。
7. 任意 hash missing（哈希缺失）或 mismatch（不匹配）必须 fail closed。

### 7.6 ReplayArtifactManifest（重放产物清单）

建议 schema：

```yaml
artifact_manifest_id:
project_ref:
entries:
  - manifest_ref:
    kind: event_window | payload_manifest | artifact_manifest | hash_manifest | replay_report
    content_ref:
    sha256:
```

字段说明：

- `manifest_ref`：manifest entry（清单条目）引用。
- `kind`：首版固定枚举，不接受未知 kind。
- `content_ref`：对应逻辑内容引用，例如 payload manifest ref、replay report ref。
- `sha256`：该逻辑内容的稳定 hash。

不变量：

1. entries 必须非空。
2. 必须覆盖 event_window、payload_manifest、artifact_manifest、hash_manifest、replay_report 五类中的必需项。
3. 每个 sha256 必须为 64 位小写 sha256 hex digest。
4. manifest_ref / content_ref 不得重复。
5. 不接受 host absolute path（宿主绝对路径）、Windows drive（Windows 盘符）、反斜杠、`.`、`..` 或尾部斜杠作为 content_ref 路径形态。
6. 不允许 placeholder hash（占位哈希）或空 hash。

### 7.7 ReplayReport（重放报告）

建议 schema：

```yaml
replay_report_id:
project_ref:
projection_kind: seat_assignment_graph
projection_version:
event_range:
event_count:
summary_hash:
replay_passed: true
blockers: []
generated_at:
```

不变量：

1. `projection_kind` 必须为 `seat_assignment_graph`。
2. `projection_version` 必须与 attestation.projection_version 一致。
3. `summary_hash` 必须等于 ProjectionReplaySummary.summary_hash。
4. `event_range` 必须等于 ProjectionReplaySummary.event_range。
5. `event_count` 必须等于 ProjectionReplaySummary.event_count。
6. `replay_passed` 必须为 true。
7. `blockers` 首版必须为空；若 replay 失败，不应构建 passed ReplayBundle，而应 fail closed。
8. `generated_at` 必须带时区。

### 7.8 ReplayBundleBuilderInput（重放包构建输入）

建议 schema：

```yaml
project_ref:
events:
  - EventRecord...
projection_summary:
payload_manifest_entries:
  - ...
artifact_manifest_entries:
  - ...
generated_at:
```

字段说明：

- `events`：ordered EventRecord（有序事件记录）集合。必须来自 V2-020F replay 使用的同一事件窗口，且不可为空。
- `projection_summary`：ProjectionReplaySummary（投影重放摘要），必须是 `seat_assignment_graph`。
- `payload_manifest_entries`：payload manifest（载荷清单）条目，证明 projection replay 所需 payload refs（载荷引用）可解析。
- `artifact_manifest_entries`：artifact manifest（产物清单）条目，证明 replay report / payload manifest 等逻辑产物具备 hash。
- `generated_at`：带时区 datetime。

不变量：

1. events 必须 tuple/list，不接受 scalar string。
2. events 不可为空。
3. events 的 project_ref 必须全部等于 input.project_ref。
4. events 的 graph_version 必须严格递增且连续。
5. projection_summary.project_ref 必须等于 input.project_ref。
6. projection_summary.projection_kind 必须为 `seat_assignment_graph`。
7. projection_summary.event_range 必须与 events 首尾一致。
8. projection_summary.event_count 必须等于 len(events)。
9. payload_manifest_entries 必须覆盖 events 中所有 payload_refs。
10. generated_at 必须带时区。
11. projection_summary.graph_version 必须等于最后一条 event.graph_version。

## 8. Builder（构建器）语义

### 8.1 构建流程

```text
ProjectionReplay.replay_events(...)（V2-020F 已有）
  -> ProjectionReplaySummary（投影重放摘要）
  -> ReplayBundleBuilderInput（重放包构建输入）
  -> build event hash chain（构建事件哈希链）
  -> build payload/artifact/hash manifests（构建载荷/产物/哈希清单）
  -> build ReplayReport（构建重放报告）
  -> build ReplayAttestation(kind="seat_assignment_graph")（构建席位分配图证明条目）
  -> build ReplayBundle（构建重放包）
  -> replay_bundle_readiness(bundle)（投影为收尾门禁就绪摘要）
```

`hash_manifest`（哈希清单）在最后一步对前面所有 logical artifacts（逻辑产物）重新计算 sha256，不复用任何中间变量；它不是 `artifact_manifest`（产物清单）的子集，而是独立验证层。

### 8.2 与 CloseoutGate（收尾门禁）的连接

V2-070A 已有 `ReplayBundleReadiness`（重放包就绪摘要），字段为：

```yaml
replay_passed: true
summary_hash:
event_range:
projection_versions:
  - ...
hash_chain_verified: true
```

V2-070B 必须提供从 ReplayBundle（重放包）到该 readiness summary（就绪摘要）的投影：

- `replay_passed`：所有 attestations（首版恰好一条）和 replay_report 都通过。
- `summary_hash`：首版取唯一 attestation.summary_hash。
- `event_range`：首版可派生为稳定 EventRangeRef（事件范围引用），例如 `event-range.<project_ref>.<first_graph_version>-<last_graph_version>`。
- `projection_versions`：来自 attestations 的 projection_version 集合。
- `hash_chain_verified`：hash manifest 校验通过。

该投影函数必须重新校验 hash manifest（哈希清单）与 bundle 内容一致，而不是只读布尔字段。

### 8.3 Determinism（确定性）

以下 ID / hash 必须 deterministic（确定性）：

1. ReplayEventWindow hash（事件窗口哈希）。
2. ReplayHashManifest hash（哈希清单哈希）。
3. ReplayArtifactManifest hash（产物清单哈希）。
4. ReplayReport hash（重放报告哈希）。
5. ReplayAttestation id/hash（证明条目 ID/哈希）。
6. ReplayBundle id（重放包 ID）。

建议所有 hash 使用 `json.dumps(model_dump(mode="json"), sort_keys=True, separators=(",", ":"))` 的 canonical JSON（规范 JSON）再 sha256。

## 9. Fail-closed（失败关闭）规则

### 9.1 模型层必须失败的情况

1. ReplayBundle 缺 `attestations`、`hash_manifest`、`artifact_manifest` 或 `replay_report`。
2. ReplayBundle.attestations 不是 tuple/list。
3. V2-070B 首版 attestations 为空、多于一条，或 kind 不是 `seat_assignment_graph`。
4. ReplayAttestation 缺 event_window、projection_version、event_window_hash、manifest refs、replay_report_ref、summary_hash。
5. ReplayAttestation.kind 是未知字符串。
6. summary_hash / event_window_hash / manifest hash 不是 64 位小写 sha256 hex digest。
7. ReplayEventWindow 缺 first/last graph version、first/last event id、event_count。
8. ReplayEventWindow graph version 非正数或 event_count 非正数。
9. ReplayEventHashNode 缺 event_hash、previous_hash 或 chain_hash。
10. ReplayHashManifest 缺 event_hash_chain、terminal_event_chain_hash、event_window_hash、artifact_manifest_hash、payload_manifest_hash 或 replay_report_hash。
11. ReplayArtifactManifest entries 为空或含 unsafe path/ref（不安全路径/引用）。
12. ReplayReport 缺 projection_kind、projection_version、event_range、summary_hash 或 replay_passed。
13. generated_at 无时区。
14. 任意 extra fields（额外字段）。

### 9.2 Builder 层必须失败的情况

1. events 为空。
2. events 乱序、graph_version 不连续或 project_ref mismatch（项目引用不匹配）。
3. projection_summary.projection_kind 不是 `seat_assignment_graph`。
4. projection_summary.event_range 与 events 首尾不一致。
5. projection_summary.graph_version 与 last event graph_version 不一致。
6. projection_summary.event_count 与 len(events) 不一致。
7. projection version mismatch（投影版本不匹配）。
8. payload manifest 缺任一 event.payload_refs。
9. artifact manifest 缺 replay report / payload manifest / hash manifest 所需 hash。
10. event hash chain 缺失、断链或 terminal hash 不一致。
11. hash manifest 中任意 hash 与 bundle 内容重算结果不一致。
12. replay report missing（重放报告缺失）或 replay_passed false。
13. artifact_manifest_ref / hash_manifest_ref / replay_report_ref 无法闭合。
14. attestation_hashes 缺当前 attestation 或包含孤儿 attestation id。
15. 任何 placeholder / synthetic / empty hash（占位/合成/空哈希）试图满足 manifest。

### 9.3 Readiness projection（就绪投影）必须失败的情况

1. ReplayBundle 本身结构非法。
2. hash manifest 无法重新验证。
3. attestation 数量不是一条。
4. attestation kind 不是 `seat_assignment_graph`。
5. replay_report 与 attestation summary_hash / event range / projection version 不一致。
6. 返回的 ReplayBundleReadiness（重放包就绪摘要）缺任一 V2-070A 必需字段。

## 10. 测试计划

测试文件：

```text
tests/closeout/test_replay_bundle.py
```

### 10.1 Negative tests first（负例优先）

必须先写以下负例，并在实现前得到预期 RED（红灯），例如 `ModuleNotFoundError: No module named 'boardroom_os.audit.replay_bundle'` 或缺对应类：

1. `test_replay_bundle_rejects_missing_event_range`
2. `test_replay_bundle_rejects_projection_version_mismatch`
3. `test_replay_bundle_rejects_missing_artifact_hash`
4. `test_replay_bundle_rejects_missing_event_hash_chain`
5. `test_replay_bundle_rejects_missing_hash_manifest`
6. `test_replay_bundle_rejects_missing_replay_report`
7. `test_replay_bundle_rejects_unknown_attestation_kind`
8. `test_replay_bundle_rejects_multiple_attestations_in_v1`
9. `test_replay_bundle_rejects_payload_manifest_missing_event_payload_ref`
10. `test_replay_bundle_rejects_hash_manifest_mismatch`
11. `test_replay_bundle_rejects_event_order_gap_or_project_mismatch`
12. `test_replay_bundle_rejects_projection_summary_graph_version_mismatch`
13. `test_replay_bundle_rejects_naive_generated_at`
14. `test_replay_bundle_rejects_placeholder_or_empty_hash`
15. `test_replay_bundle_readiness_revalidates_hash_manifest`

这些测试应覆盖 backlog V2-070B 明确要求：event range 缺失、projection version 不匹配、artifact hash 缺失、event log hash chain / hash manifest 缺失、replay report 缺失必须失败。

### 10.2 Happy path（正向路径）

`tests/closeout/test_replay_bundle.py` 建议同时覆盖：

1. `test_replay_bundle_builds_seat_assignment_attestation_from_projection_summary`
   - 复用或轻量复制 `tests/reducers/test_projection_replay.py` 的 event / payload / projector fixture（夹具）形状。
   - 通过 `ProjectionReplay.replay_events(...)` 生成 ProjectionReplaySummary（投影重放摘要）。
   - 构建 ReplayBundle（重放包）。
   - 断言 bundle.version == 1。
   - 断言 attestations 恰好一条，kind == `seat_assignment_graph`。
   - 断言 summary_hash 等于 ProjectionReplaySummary.summary_hash。
   - 断言 event_window 与 summary.event_range 一致。

2. `test_replay_bundle_hash_chain_proves_event_window_integrity`
   - 断言 event_hash_chain（事件哈希链）长度等于 events 数量。
   - 断言第一条 previous_hash 为 64 个 0。
   - 断言最后 terminal hash 与 hash_manifest.terminal_event_chain_hash 一致。
   - 修改任一 event 后重新校验应失败。

3. `test_replay_bundle_readiness_matches_closeout_gate_contract`
   - 调用 `replay_bundle_readiness(bundle)`。
   - 断言返回对象是 V2-070A `ReplayBundleReadiness`（重放包就绪摘要）。
   - 断言 replay_passed true、hash_chain_verified true、projection_versions 非空、event_range 非空。

4. `test_replay_bundle_is_audit_friendly_json`
   - `model_dump(mode="json")` 稳定。
   - 不包含宿主绝对路径。
   - 不包含 Windows drive / 反斜杠。
   - 重复构建产生相同 bundle id / hash。

5. `test_replay_bundle_does_not_define_unimplemented_projection_names`
   - 断言 `ReplayAttestationKind`（重放证明条目类型）只有 `seat_assignment_graph`。
   - 断言没有 `ticket_graph`、`evidence_map`、`closeout_reducer` 占位 kind。

### 10.3 回归边界

实施完成后应至少回归：

```bash
PYTHONPATH="src;." python -m pytest tests/reducers/test_projection_replay.py tests/closeout/test_replay_bundle.py -q
PYTHONPATH="src;." python -m pytest tests/negative/test_closeout_fail_closed.py tests/closeout/test_closeout_gate.py tests/closeout/test_replay_bundle.py -q
```

第一条证明 V2-020F audit replay（审计重放）未被破坏；第二条证明 V2-070A CloseoutGate（收尾门禁）仍能消费 V2-070B readiness summary（就绪摘要）。

## 11. 验证命令

实施完成后建议运行：

```bash
PYTHONPATH="src;." python -m pytest tests/closeout/test_replay_bundle.py -q
PYTHONPATH="src;." python -m pytest tests/reducers/test_projection_replay.py tests/closeout/test_replay_bundle.py -q
PYTHONPATH="src;." python -m pytest tests/negative/test_closeout_fail_closed.py tests/closeout/test_closeout_gate.py tests/closeout/test_replay_bundle.py -q
PYTHONPATH="src;." python -m pytest tests/contracts tests/reducers tests/execution tests/evidence tests/proving tests/closeout tests/negative -q
```

其中第一条证明 V2-070B 自身；第二条证明 replay kernel（重放内核）未回退；第三条证明 closeout gate（收尾门禁）可消费 replay readiness（重放就绪摘要）；第四条作为全量回归。

## 12. 完成后文档同步

实现完成并通过验证后，必须按 `backlog.md` 的工作包完成更新协议同步：

1. `doc/04-implementation/backlog.md`
   - V2-070B 状态改为 DONE。
   - 顶部 “当前未完成工作包” 指向 V2-070C。
   - Phase 7 进度从 1 / 6 改为 2 / 6；总计从 42 / 53 改为 43 / 53。
2. `doc/04-implementation/acceptance-criteria.md`
   - 勾选 AC-V2-CLOSEOUT-002（replay bundle required，重放包必需）中 V2-070B 覆盖部分。
   - 若 V2-070F 仍需补 closeout reducer replay（收尾归约器重放）输入边界，不提前勾选 V2-070F 相关 checkbox。
3. `doc/05-project-log/2026-05.md`
   - 追加 V2-070B 完成记录，包含关键产出文件、negative/happy tests（负例/正例测试）和验证命令证据。
4. `doc/05-project-log/decisions.md`
   - 若评审确认“ReplayBundle durable artifact schema 采用 attestations 列表，首版只允许 `seat_assignment_graph`”属于架构决策，应新增 DEC-XXXX。
   - 如果用户认为本 spec 本身已足够，不新增 DEC 也可；但实现时不得改变此边界。
5. `doc/04-implementation/INDEX.md`
   - 本 spec 文件需加入索引。

## 13. 评审关注点

1. 是否同意 ReplayBundle（重放包）作为 durable audit artifact（持久审计产物）从首版就采用 `attestations` 列表。
2. 是否同意首版 `ReplayAttestation.kind` 只允许 `seat_assignment_graph`，不预写未实现 projection 名称。
3. 是否同意不定义 ReplayerProtocol（重放器协议）、ReplayerRegistry（重放器注册表）或插件入口。
4. 是否同意 event log hash chain（事件日志哈希链）与 hash manifest（哈希清单）在 V2-070B bundle 层实现，不回填 V2-020F InMemoryEventLog（内存事件日志）。
5. 是否同意 `replay_bundle_readiness(bundle)` 必须重新验证 hash manifest，而不是信任 bundle 内的 ready bool。
6. 是否同意 V2-070B 不实现 branchable governance replay（可分叉治理重放），只为后续扩展保留 durable schema（持久结构）。
7. 是否同意未来新增 projection 时，通过扩展 `ReplayAttestationKind` union（类型联合）和新增明确 verifier 分支完成，而不是插件化注册。
