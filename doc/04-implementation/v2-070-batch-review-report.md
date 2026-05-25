# V2-070 大批次独立审查报告

> 日期：2026-05-25  
> 审查范围：`04d1b2e^...HEAD`，即 V2-070A 到 V2-070G 当前完整实现。  
> 审查视角：独立第三方专家团队视角。  
> 审查目标：判断 V2-070 当前代码是否满足重构 PRD 所需的 closeout / replay / audit 能力，并重点识别隐式 fallback、硬编码、虚假 mock、重复实现、第二事实源、吞错、非确定性哈希等可能导致项目再次失败的问题。

## 1. 执行摘要

当前 V2-070G 已经补强了 Closeout Closure（收尾闭包）阶段的一部分 fail-closed（失败封闭）校验，但本次审查认为：

**V2-070G 尚未把整个 V2-070 批次整改闭合。**

主要原因不是单点代码缺陷，而是 V2-070 的核心事实链仍存在结构性问题：

1. ProcessAudit（流程审计）与 CloseoutPackage（收尾包）之间存在构造环风险。
2. ReplayBundle（回放包）没有从 events（事件流）重新计算 ProjectionReplaySummary（投影回放摘要），存在第二事实源。
3. ProcessAudit（流程审计）没有强校验自身 events 与 ReplayBundle（回放包）的 events 完全一致。
4. GitAuditAdapter（Git 审计适配器）存在 base_commit_sha / worktree_ref 的隐式 fallback。
5. CloseoutPackage（收尾包）允许 graph_version（图版本）超过 ReplayBundle（回放包）证明到的最后版本。
6. 多处哈希构造依赖调用方输入顺序，破坏 deterministic hashing（确定性哈希）。
7. 多处引用 ID 缺少 run/hash/project 命名空间，存在跨 bundle 串包风险。
8. ProcessAudit（流程审计）存在宽泛 BaseModel（基础模型）输入和 `getattr(..., "unknown")` 类占位 fallback。

因此，本报告建议：

> 不采用单纯“18 个问题逐项串行打补丁”的方式，也不推倒重写整个 070。推荐进行一次**有边界的 V2-070 fact-chain hardening（事实链强化）重构**，先重构事实权威源、构造顺序和跨包绑定，再按 P0 / P1 / P2 串行修复外围问题。

## 2. 审查范围与方法

### 2.1 审查范围

本次审查范围为：

```bash
git diff 04d1b2e^...HEAD
```

即从 V2-070A `feat(closeout): 实现V2-070A收尾门禁` 到当前 `HEAD` 的完整 V2-070 批次。

主要涉及文件：

- `src/boardroom_os/audit/replay_bundle.py`
- `src/boardroom_os/audit/process_audit.py`
- `src/boardroom_os/audit/git_version_audit.py`
- `src/boardroom_os/adapters/git_audit.py`
- `src/boardroom_os/closeout/gate.py`
- `src/boardroom_os/closeout/package.py`
- `src/boardroom_os/closeout/closure.py`
- `src/boardroom_os/reducers/closeout_reducer.py`
- `src/boardroom_os/contracts/hashes.py`
- `tests/closeout/*`
- `tests/negative/test_closeout_fail_closed.py`

### 2.2 审查方法

采用 extra-high recall（高召回）代码审查方式，从以下角度独立扫描：

1. line-by-line diff scan（逐行 diff 扫描）
2. removed-behavior auditor（删除行为审计）
3. cross-file tracer（跨文件调用链追踪）
4. Python language-pitfall specialist（Python 语言陷阱审查）
5. wrapper / adapter correctness（包装器与适配器正确性审查）

重点关注：

- 隐式 fallback
- 硬编码
- 虚假 mock / synthetic success path（合成成功路径）
- 重复实现
- 第二事实源
- 吞错
- hash 非确定性
- 跨包事实不一致
- 审计证据没有内容绑定

## 3. 总体结论

### 3.1 070G 是否解决了这些问题？

没有完全解决。

V2-070G 主要强化的是 Closeout Closure（收尾闭包）最后阶段的失败封闭校验，例如 closeout committed 事件 payload 是否完整、closure 与 package/readiness/report 是否绑定等。

但本次审查发现的问题大多位于更上游：

- ReplayBundle（回放包）事实生成层
- ProcessAudit（流程审计）事实整合层
- GitVersionAudit（Git 版本审计）事实采集层
- CloseoutPackage（收尾包）跨包聚合层
- deterministic hash（确定性哈希）与 artifact identity（产物标识）层

因此，V2-070G 不能被视为已经关闭整个 070 批次的系统性风险。

### 3.2 070 当前的主要失败模式

当前实现容易出现以下失败模式：

1. **测试场景可构造，真实流程不可自然构造。**  
   ProcessAudit（流程审计）与 CloseoutPackage（收尾包）之间可能存在构造环。

2. **审计包看似完整，但事实来源不唯一。**  
   ReplayBundle（回放包）和 ProcessAudit（流程审计）都接受外部输入的事实摘要或事件列表，但没有充分证明它们来自同一权威事实源。

3. **缺失输入被默认值或占位文本掩盖。**  
   例如 GitAuditAdapter（Git 审计适配器）对 base_commit_sha 的 fallback，以及 ProcessAudit（流程审计）中的 `unknown` 占位。

4. **同一事实多次构建得到不同 hash。**  
   多处 tuple/list 输入未 canonical sort（规范排序）。

5. **报告引用可能跨 bundle 串包。**  
   artifact_ref、content_ref、fact_set_id 缺少足够命名空间。

## 4. 关键发现清单

### P0-1. ProcessAudit 与 CloseoutPackage 存在构造环

**位置：**

- `src/boardroom_os/audit/process_audit.py`
- `src/boardroom_os/closeout/package.py`
- `src/boardroom_os/reducers/closeout_reducer.py`

**问题：**

ProcessAudit（流程审计）要求事件流中已经存在 `closeout_committed`；但 CloseoutPackage（收尾包）又要求先提供 ProcessAuditBundle（流程审计包）。这会形成真实收尾流程上的循环依赖。

**失败场景：**

真实项目刚完成 verified evidence（已验证证据）、ReplayBundle（回放包）和 GitVersionAudit（Git 版本审计）时，尚未产生真实 `CLOSEOUT_COMMITTED` 事件。此时构建 ProcessAuditBundle（流程审计包）会失败；若先人为写入 `CLOSEOUT_COMMITTED`，则该事件又需要绑定真实 CloseoutPackage（收尾包）和审计包引用。

**影响：**

这会导致测试可以依赖 synthetic payload（合成载荷）通过，但真实收尾流程无法自然闭合。

---

### P0-2. ReplayBundle 没有从 events 重新计算 ProjectionReplaySummary

**位置：**

- `src/boardroom_os/audit/replay_bundle.py`

**问题：**

ReplayBundleBuilderInput（回放包构建输入）接受外部传入的 ProjectionReplaySummary（投影回放摘要），但主要只校验 project_ref、projection_kind、event_count、graph_version 边界等字段，没有从 events（事件流）重新投影并重新计算 summary_hash。

**失败场景：**

调用方传入真实 events，但同时传入一个边界一致、内部内容被篡改的 ProjectionReplaySummary。系统仍可能把伪造 summary_hash 写入 ReplayReport（回放报告）和 ReplayAttestation（回放证明）。

**影响：**

ReplayBundle（回放包）不能证明“事件流得到该投影摘要”，只是在包装调用方给出的摘要，形成第二事实源。

---

### P0-3. ProcessAudit 没有校验自身 events 与 ReplayBundle.events 完全一致

**位置：**

- `src/boardroom_os/audit/process_audit.py`
- `src/boardroom_os/audit/replay_bundle.py`

**问题：**

ProcessAudit（流程审计）只校验 event window（事件窗口）、graph_version（图版本）覆盖、首尾 event_id 和必要事件类型，没有逐条比对自身 events 与 ReplayBundle（回放包）中的 events 是否完全一致。

**失败场景：**

传入一组被篡改的 events：首尾 event_id 与 ReplayBundle 一致，graph_version 连续，但中间事件的 event_type、payload 或 actor 已被替换。ProcessAudit 仍可能构建 timeline（时间线）和 decision log（决策日志）。

**影响：**

ProcessAudit（流程审计）可能生成与 ReplayBundle（回放包）不一致的第二套事实。

---

### P0-4. GitAuditAdapter 对 base_commit_sha / worktree_ref 存在隐式 fallback

**位置：**

- `src/boardroom_os/adapters/git_audit.py`

**问题：**

GitAuditAdapter.collect() 在 base_commit_sha 缺失时静默 fallback 到 final_commit_sha；worktree_ref 为空时也会 fallback 到默认 worktree 引用。

**失败场景：**

调用方漏传 base_commit_sha，而真实分支包含多个提交。系统仍生成成功的 GitVersionAuditFactSet（Git 版本审计事实集），但审计起点被伪装成最终提交。

**影响：**

这直接违反 No silent fallbacks（禁止隐式 fallback）工程硬规则，会把“审计起点未知”伪装成“审计范围为空”。

---

### P0-5. CloseoutPackage 允许 graph_version 超过 ReplayBundle 已证明范围

**位置：**

- `src/boardroom_os/closeout/package.py`
- `src/boardroom_os/reducers/closeout_reducer.py`

**问题：**

CloseoutPackage（收尾包）只拒绝 graph_version 小于 ReplayBundle 最后 graph_version 的情况，但允许 package.graph_version 大于 replay_last_graph_version。

**失败场景：**

ReplayBundle（回放包）只证明到 graph_version = 100，调用方构建 CloseoutPackage（收尾包）时使用 graph_version = 105。系统接受后，收尾包声称覆盖到 105，但 replay/process audit 实际只证明到 100。

**影响：**

收尾结论可能超前于被审计事实边界。

---

### P1-1. ReplayPayloadManifest 只校验 payload_ref 覆盖，不校验 sha256 对应真实 payload 内容

**位置：**

- `src/boardroom_os/audit/replay_bundle.py`

**问题：**

ReplayPayloadManifest（回放载荷清单）检查 payload_ref 覆盖情况，但没有拿真实 payload 内容重新计算 entry.sha256。

**失败场景：**

调用方提供 payload_ref 完整但 sha256 被篡改的 manifest。ReplayBundle（回放包）和 readiness（就绪检查）仍可能通过。

**影响：**

payload hash 证明不可信。

---

### P1-2. ProcessAudit 使用宽泛 BaseModel 与 getattr 占位 fallback

**位置：**

- `src/boardroom_os/audit/process_audit.py`

**问题：**

ProcessAuditBuilderInput（流程审计构建输入）中的 agent_context_index（智能体上下文索引）和 ticket_graph_summary（任务图摘要）使用宽泛 BaseModel 类型，下游用 `getattr(..., "unknown")` 或 `getattr(..., "ticket")` 获取字段。

**失败场景：**

调用方传入结构不完整的 BaseModel，缺少 ticket_ref、owner_seat_ref 或 acceptance_refs。系统不 fail closed，而是把 `unknown` 或 `ticket` 写入审计产物。

**影响：**

缺失事实被占位值伪装成有效事实。

---

### P1-3. artifact-lineage.json 伪造 consumer_ticket_ref

**位置：**

- `src/boardroom_os/audit/process_audit.py`
- `src/boardroom_os/workspace/source_inventory.py`

**问题：**

SourceInventoryEntry（源码清单条目）只有 producer_ticket_ref（生产任务引用），但 artifact-lineage.json 又生成 consumer_ticket_ref（消费任务引用），且值直接等于 producer_ticket_ref。

**失败场景：**

ticket A 产出源码，ticket B 消费该源码作为验收证据。当前 lineage 可能写成 producer=A、consumer=A，掩盖真实跨 ticket 证据流向。

**影响：**

producer 与 consumer 两种不同事实被混同，形成伪事实。

---

### P1-4. expected_fallback_decision_refs 为空时不拒绝额外 fallback_lineages

**位置：**

- `src/boardroom_os/audit/process_audit.py`

**问题：**

当 expected_fallback_decision_refs（预期降级决策引用）为空时，ProcessAudit readiness（流程审计就绪检查）没有明确拒绝 artifact-lineage.json 中额外出现的 fallback_lineages。

**失败场景：**

真实 evidence chain（证据链）没有任何 fallback decision record（降级决策记录），但 artifact-lineage.json 被手工塞入 fallback_lineages。readiness 仍可能通过。

**影响：**

审计产物可引入不存在于真实证据链的 fallback 事实。

---

### P1-5. fact_set_id / artifact_ref / content_ref 命名空间不足

**位置：**

- `src/boardroom_os/adapters/git_audit.py`
- `src/boardroom_os/audit/git_version_audit.py`
- `src/boardroom_os/audit/process_audit.py`

**问题：**

GitVersionAuditFactSet（Git 版本审计事实集）的 fact_set_id 只由 project_ref 派生；ProcessAuditArtifactRef（流程审计产物引用）和 ProcessAuditContentRef（流程审计内容引用）只按 kind 命名。

**失败场景：**

同一项目多次审计，或多个项目各自审计，可能生成相同 fact_set_id / artifact_ref / content_ref。若外部存储按这些引用读取对象，旧 report 可能读到新 bundle 的对象。

**影响：**

report 到 fact set/artifact/content 的一对一绑定不可靠，存在串包风险。

---

### P2-1. GitVersionAudit 输入顺序影响 bundle hash

**位置：**

- `src/boardroom_os/audit/git_version_audit.py`

**问题：**

verification_runs（验证运行记录）和 command_evidence_bindings（命令证据绑定）未 canonical sort（规范排序），直接参与 command_evidence_refs、checked_refs 和 bundle_payload_hash。

**失败场景：**

同一组验证运行记录仅传入顺序不同，就生成不同 bundle_id。

**影响：**

破坏同一事实对应同一 hash 的审计可重现性。

---

### P2-2. Replay manifest entries 顺序影响 replay_bundle_id

**位置：**

- `src/boardroom_os/audit/replay_bundle.py`

**问题：**

ReplayPayloadManifest（回放载荷清单）和 ReplayArtifactManifest（回放产物清单）的 entries 只校验非空和唯一，没有 canonical sort。

**失败场景：**

同一组 manifest entries 仅顺序不同，生成不同 payload_manifest_hash、artifact_manifest_hash 和 replay_bundle_id。

**影响：**

破坏回放包的确定性。

---

### P2-3. ProcessAudit checked_refs 顺序不稳定

**位置：**

- `src/boardroom_os/audit/process_audit.py`

**问题：**

provider_attempt_refs（模型调用尝试引用）、verification_runs（验证运行记录）、verified_evidence（已验证证据）等输入顺序直接影响 checked_refs 和 bundle_payload_hash。

**失败场景：**

同一组输入仅顺序不同，生成不同 ProcessAuditBundle（流程审计包）哈希。

**影响：**

破坏流程审计包的长期可比对性。

---

### P2-4. Git status 解析未使用 `--porcelain -z`

**位置：**

- `src/boardroom_os/adapters/git_audit.py`

**问题：**

GitAuditAdapter（Git 审计适配器）使用普通 `git status --porcelain` 并用字符串切片和 `split(" -> ", 1)` 解析路径。

**失败场景：**

文件名包含换行、引号、反斜杠、制表符或 ` -> ` 字符串时，Git 会进行 C-style quoting/escaping，当前解析器可能误解析路径或直接失败。

**影响：**

特殊文件名会导致 Git 审计事实错误或审计失败。

---

### P2-5. Git diff stat 使用未锚定 regex 解析全文

**位置：**

- `src/boardroom_os/adapters/git_audit.py`

**问题：**

Git diff 统计通过 regex 搜索整段 `git diff --stat` 输出中的 `insertions` / `deletions`，没有限定 summary footer。

**失败场景：**

文件名如 `docs/12 insertions.md` 可能污染统计数字。

**影响：**

GitDiffSummary（Git 差异摘要）可能与真实 diff 不一致。

## 5. 用户提出的整改选择

评审前，用户提出了一个关键选择：

> 是出一个计划针对性串行修改这些问题，还是重构 070 阶段的实现？

本报告将该选择归纳为两条路线：

### 5.1 路线 A：针对性串行修补

做法：

- 将上文发现的问题逐项建任务；
- 按 P0 / P1 / P2 顺序逐个修改；
- 不先改变 V2-070 的事实链结构。

优点：

- 短期改动较小；
- 每个问题容易单独验收；
- 对现有测试扰动较小。

缺点：

- 容易在旧结构上继续堆补丁；
- ProcessAudit / CloseoutPackage 构造环等结构问题难以靠局部补丁解决；
- ReplayBundle / ProcessAudit / CloseoutPackage 之间的事实源边界不清，会不断诱发新问题；
- 修掉 fallback 后，原有 synthetic tests（合成测试）可能暴露更深层流程不成立。

### 5.2 路线 B：重构 070 阶段实现

做法：

- 重新校准 V2-070 的事实权威源；
- 明确 EventLog、ReplayBundle、ProcessAuditBundle、GitVersionAuditBundle、CloseoutPackage、CLOSEOUT_COMMITTED event、CloseoutClosure 之间的构造顺序；
- 再串行修复外围问题。

优点：

- 能从根源解决第二事实源、构造环、事实边界漂移；
- 后续每个校验会变成自然约束，而不是补丁；
- 更符合重构 PRD 所需的可靠 closeout/audit 能力。

缺点：

- 短期成本高于单点修补；
- 需要重写部分 tests 和 builder 输入模型；
- 如果范围失控，可能演变为全量重写。

## 6. 推荐方案

本报告建议采用第三种折中路线：

> **有边界的 V2-070 fact-chain hardening（事实链强化）重构 + P0/P1/P2 串行修复。**

这不是推倒重写整个 070，也不是简单逐项补丁。

核心原则：

1. 先重构事实链主干。
2. 再按优先级串行修补外围问题。
3. 尽量保留现有领域模型、readiness 框架和负向测试资产。
4. 禁止引入新的 silent fallback（隐式 fallback）、synthetic success path（合成成功路径）和第二事实源。

## 7. 推荐事实链

建议将 V2-070 的权威事实链调整为：

```text
EventLog（事件日志）
   ↓
ReplayBundle（回放包：从 events 重新投影）
   ↓
ProcessAuditBundle（流程审计包：消费 replay 的同一事实）
   ↓
GitVersionAuditBundle（Git 版本审计包：绑定真实 commit range）
   ↓
CloseoutPackage（收尾包：聚合已验证审计包）
   ↓
CLOSEOUT_COMMITTED event（收尾提交事件）
   ↓
CloseoutReducer / CloseoutClosure（收尾归约器 / 收尾闭包）
```

关键约束：

1. EventLog（事件日志）是事件事实的唯一权威源。
2. ReplayBundle（回放包）必须从 events 重新计算 ProjectionReplaySummary（投影回放摘要）。
3. ProcessAuditBundle（流程审计包）必须消费与 ReplayBundle 完全一致的 events。
4. ProcessAuditBundle 不应要求 `CLOSEOUT_COMMITTED` 已经存在。
5. `CLOSEOUT_COMMITTED` 应该在 CloseoutPackage 构建完成后产生。
6. CloseoutReducer（收尾归约器）消费 `CLOSEOUT_COMMITTED`。
7. CloseoutClosure（收尾闭包）负责最后校验 package、readiness、report、reducer state 和 event payload 是否闭合。
8. CloseoutPackage.graph_version 必须严格等于 ReplayBundle 证明到的 last_graph_version，除非额外设计扩展证明窗口。
9. 所有 hash 输入若语义为集合，必须 canonical sort；若语义为序列，必须说明序列权威来源。
10. 所有跨包引用必须有 project/run/hash/content 命名空间，避免串包。

## 8. 建议执行计划

### Step 1：确认事实链设计

先形成一份 V2-070 fact-chain hardening plan（事实链强化计划），用于评审确认。

该计划应明确：

- EventLog（事件日志）与 ReplayBundle（回放包）的关系；
- ReplayBundle 是否内部重放投影；
- ProcessAuditBundle 是否允许审计 closeout 前状态；
- GitVersionAuditBundle 如何绑定 commit range；
- CloseoutPackage 如何绑定 replay/process/git 三类审计包；
- `CLOSEOUT_COMMITTED` 事件何时产生；
- CloseoutClosure 最后校验哪些闭包关系；
- 哪些字段禁止外部传入；
- 哪些输入集合必须排序；
- 哪些引用必须内容绑定。

### Step 2：先写失败用例

新增或调整负向测试，先暴露真实失败：

- 没有 `CLOSEOUT_COMMITTED` 时仍能构建 ProcessAuditBundle；
- ProcessAudit events 与 ReplayBundle events 不一致必须失败；
- ReplayBundle projection_summary 被篡改必须失败；
- GitAuditAdapter 缺失 base_commit_sha 必须失败；
- CloseoutPackage.graph_version 超过 ReplayBundle.last_graph_version 必须失败；
- payload manifest sha256 与真实 payload 内容不一致必须失败；
- ProcessAudit 输入缺字段时不得输出 `unknown`；
- expected fallback refs 为空时，actual fallback lineages 必须为空；
- 同一输入乱序后 hash 必须稳定。

### Step 3：重构核心 builder 与 readiness

重点修改：

- `src/boardroom_os/audit/replay_bundle.py`
- `src/boardroom_os/audit/process_audit.py`
- `src/boardroom_os/closeout/package.py`
- `src/boardroom_os/reducers/closeout_reducer.py`
- `src/boardroom_os/closeout/closure.py`

目标：

- 移除构造环；
- 移除第二事实源；
- 建立跨包内容绑定；
- 明确 graph_version 边界；
- 保证 readiness fail closed。

### Step 4：修复 Git 审计与确定性哈希

重点修改：

- `src/boardroom_os/adapters/git_audit.py`
- `src/boardroom_os/audit/git_version_audit.py`
- `src/boardroom_os/contracts/hashes.py`
- replay/process audit 的 hash payload 构造函数。

目标：

- 移除 base_commit_sha / worktree_ref fallback；
- 使用 `git status --porcelain -z`；
- 使用 `git diff --shortstat` 或严格解析 summary footer；
- 对集合语义输入 canonical sort；
- 对 artifact/content/fact_set 引用增加命名空间或 hash 绑定。

### Step 5：全量验证

建议至少运行：

```bash
pytest tests/closeout tests/negative/test_closeout_fail_closed.py tests/contracts/test_hashes.py
```

并新增针对 V2-070 fact-chain 的集成验证，覆盖从 EventLog 到 CloseoutClosure 的真实收尾路径。

## 9. 风险与取舍

| 方案 | 短期成本 | 长期风险 | 评估 |
|---|---:|---:|---|
| 逐项串行补丁 | 低到中 | 高 | 不推荐单独采用 |
| 全量推倒重写 070 | 高 | 中 | 不推荐 |
| 有边界事实链重构 + 串行修复 | 中 | 低 | 推荐 |

## 10. 最终建议

本报告建议：

1. 不把 V2-070G 视为 070 批次最终闭合。
2. 不直接启动“18 个问题逐项补丁”作为唯一整改路线。
3. 启动 V2-070 fact-chain hardening（事实链强化）整改。
4. 先评审并确认事实链权威源与构造顺序。
5. 再按 P0 / P1 / P2 串行落地。

一句话结论：

> V2-070 当前不是缺少几个局部 bugfix，而是需要一次小范围结构性重构来重新固定事实链；完成该重构后，再串行修复隐式 fallback、内容绑定、引用命名空间和 deterministic hashing 等外围问题。
