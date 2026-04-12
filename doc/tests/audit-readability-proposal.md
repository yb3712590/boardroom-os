# 场景产出可读性整改建议

> 审计对象: `library_management_autopilot_live/`
> 审计日期: 2026-04-13
> 总文件数: ~70 个 (含 .gitkeep)
> 总体积: ~7.6 MB (其中 developer_inspector 占 2.6 MB, SQLite 占 4.5 MB)

---

## 一、核心问题

当前场景目录作为集成测试的产出，对人工审计极不友好。主要痛点：

1. **没有一份"一眼看懂这轮跑了什么"的摘要文件**——要理解全貌，必须同时翻数据库、JSON、巡检日志
2. **巡检报告是流水账**——731 行中，大量是"无变化"的重复心跳，有效信息被淹没
3. **治理文档 JSON 结构过重**——每份 130~374 行，充斥 `linked_artifact_refs`、`source_process_asset_refs` 等机器元数据，人工审计时完全无用
4. **developer_inspector 三份文件高度冗余**——`compiled_context_bundle`、`rendered_execution_payload`、`compile_manifest` 对同一张票存三份视角，内容重叠率 >70%
5. **ticket_context_archives 的"人工可读"名不副实**——实际内容是 JSON preview 的截断拼接，不比直接看 JSON 好多少
6. **目录层级过深**——`artifacts/project-workspaces/wf_df95d935a020/10-project/docs/tracking/task-index.md`，6 层嵌套，路径本身就是认知负担

---

## 二、逐项整改建议

### 2.1 新增：场景级审计摘要 (`audit-summary.md`)

**问题**: 当前没有任何单一文件能回答"这轮测试跑了什么、结果如何"。

**建议**: 每轮场景结束后，自动生成一份 `audit-summary.md`，放在场景根目录。内容结构：

```
# 场景审计摘要
- 场景: library_management_autopilot_live
- 时间: 2026-04-13 01:37 ~ 02:48 (71 分钟)
- 最终状态: EXECUTING / build 阶段
- Provider: gpt-5.4 via https://free.9e.nz/v1

## Workflow 进度
- 阶段流转: project_init → plan → build
- 总 ticket 数: 15
- 完成 ticket 数: 12
- 失败 ticket 数: 0
- 当前活跃 ticket: tkt_xxx (source_code_delivery)

## 治理文档产出链
| 序号 | Ticket ID | 文档类型 | 状态 | 关键结论(一句话) |
|------|-----------|----------|------|-------------------|
| 1 | tkt_wf_...brief | architecture_brief | COMPLETED | MVP 范围锁定为图书馆管理 |
| 2 | tkt_845b... | technology_decision | COMPLETED | Python + SQLite + Flask |
| 3 | tkt_033f... | milestone_plan | COMPLETED | 5 里程碑 M0-M4 |
| 4 | tkt_1291... | detailed_design | COMPLETED | 单页 SPA 借还书流程 |
| 5 | tkt_2a74... | backlog_recommendation | COMPLETED | P1: 实现借还书核心流程 |
| 6 | tkt_83b3... | architecture_brief | COMPLETED | 实现前架构确认 |

## 代码产出
- src/ 下有实际代码: 是/否
- tests/ 下有测试: 是/否
- evidence/ 下有证据: 是/否

## 异常与卡点
- incident 数: 0
- approval 数: 0
- 最长无变化区间: 01:40~01:53 (13 分钟, plan 阶段等待 provider 响应)
```

**实现方式**: 在测试 harness 的 `on_scenario_end` 钩子中，从 SQLite 查询 workflow/ticket 表，拼接生成。

---

### 2.2 整改：巡检报告去重压缩

**问题**: `integration-monitor-report.md` 有 731 行，其中约 60% 是"无变化"的重复心跳记录。审计时需要逐行扫描才能找到状态跳变点。

**建议**:

**方案 A (推荐)——只记变化点**:
巡检逻辑改为：只在状态发生变化时追加记录。连续无变化时，只在恢复变化时补一行"静默了 N 分钟"。

改后效果示例：
```
### 01:38:41 workflow 启动
- wf_df95d935a020 / EXECUTING / project_init, tickets: 0, events: 5

### 01:39:41 → plan 阶段
- tickets: 1, events: 8

### 01:54:41 [静默 14 分钟后恢复]
- → project_init, tickets: 2, events: 10

### 01:57:41 → plan 阶段
- tickets: 3, events: 16
```

预计行数从 731 行降到 ~80 行。

**方案 B——保留全量但折叠**:
保留当前格式，但在文件头部增加"变化点索引"，列出所有状态跳变的时间戳和摘要，方便跳转。

---

### 2.3 整改：治理文档增加人工可读层

**问题**: `artifacts/reports/governance/tkt_xxx/*.json` 是纯机器结构。每份文件 130~374 行 JSON，包含大量审计时不需要的字段：`linked_artifact_refs`(12 条)、`source_process_asset_refs`(13 条)、`followup_recommendations` 的 `recommendation_id` 等。

人工审计只关心：这份治理文档做了什么决策、有什么约束、关键结论是什么。

**建议**: 每份治理 JSON 旁边自动生成一份同名 `.audit.md`，只提取人工关心的字段：

```
# Architecture Brief — tkt_83b3b8a129bc

## 摘要
为图书馆管理系统 MVP 准备架构治理简报...

## 关键决策
1. Keep the next delivery step explicit and document-first.
2. ...

## 关键约束
1. Do not widen the current MVP boundary...
2. ...

## 各节要点
### 1. Target slice architecture
(content_markdown 的内容，纯文本)

### 2. Scope and change boundaries
...
```

**不需要出现的字段**: `linked_artifact_refs`, `source_process_asset_refs`, `linked_document_refs`, `section_id`, `content_json`(和 `content_markdown` 重复)。

**实现方式**: 在 ticket 完成写入 JSON 后，用一个简单的 post-processor 提取 `summary` + `decisions` + `constraints` + 各 section 的 `content_markdown`。

---

### 2.4 整改：developer_inspector 三合一

**问题**: 每张 ticket 在 `developer_inspector/` 下产出 3 个 JSON 文件：

| 文件 | 用途 | 单文件大小 |
|------|------|-----------|
| `compile_manifest` | 编译决策摘要 | ~10 KB |
| `compiled_context_bundle` | 完整上下文块 | ~80 KB |
| `rendered_execution_payload` | 最终 LLM payload | ~80 KB |

12 张 ticket × 3 = 36 个文件，总计 2.6 MB。

**冗余分析**:
- `compiled_context_bundle` 的 `context_blocks` 和 `rendered_execution_payload` 的 `messages` 内容几乎完全一致，只是外层包装不同（一个是 block 数组，一个是 message 数组）
- `compile_manifest` 的 `source_log` 和 `input_fingerprint` 与 bundle 的 `meta` 高度重叠

**建议**:

**方案 A (推荐)——合并为单文件**:
每张 ticket 只产出一个 `tkt_xxx.inspector.json`，结构：
```json
{
  "compile_meta": { ... },
  "budget": { "plan": {...}, "actual": {...} },
  "source_log": [ ... ],
  "context_blocks": [ ... ],
  "rendered_messages": [ ... ],  // 只存与 context_blocks 的差异部分(system_controls, task_definition, output_contract_reminder)
  "degradation": { ... }
}
```

预计体积从 ~170 KB/ticket 降到 ~90 KB/ticket。

**方案 B——保留三文件但增加索引**:
在 `developer_inspector/` 根目录生成一份 `inspector-index.md`：
```
| Ticket | 总 token | 截断? | 降级? | 来源数 | 最大来源 |
|--------|---------|-------|-------|--------|---------|
| tkt_83b3... | 12949 | 否 | 否 | 10 | backlog_recommendation (5026) |
```

---

### 2.5 整改：ticket_context_archives 重写

**问题**: 这些 `.md` 文件号称"人工可读"，但实际内容是：
- 每个 Context Block 只展示了 JSON 的 `Preview` 截断（被截断到几百字符）
- Rendered Messages 同样是截断 preview
- 没有任何人工语言的解释或摘要

结果是：既不如直接看 JSON 完整，又不如真正的摘要简洁。两头不靠。

**建议**: 重新定义这类文件的目标——它应该是"给人看的 ticket 执行卡片"：

```markdown
# Ticket 执行卡片: tkt_83b3b8a129bc

## 基本信息
- 任务: 产出 architecture_brief
- 角色: architect_primary (governance_architect)
- 上游: tkt_2a744f32cab2 (backlog_recommendation, COMPLETED)
- 下游审查: checker_primary
- 状态: COMPLETED

## 输入上下文 (10 个来源, 共 12949 tokens)
| 来源 | 类型 | tokens | 截断? |
|------|------|--------|-------|
| backlog_recommendation.json | JSON | 5026 | 否 |
| governance-document/tkt_2a744f32cab2 | JSON | 5059 | 否 |
| AGENTS.md | TEXT | 315 | 否 |
| ARCHITECTURE.md | TEXT | 366 | 否 |
| project-brief.md | TEXT | 410 | 否 |
| boundaries.md | TEXT | 360 | 否 |
| task-index.md | TEXT | 347 | 否 |
| active-tasks.md | TEXT | 356 | 否 |
| context-baseline.md | TEXT | 357 | 否 |
| memory-recent.md | TEXT | 353 | 否 |

## 产出
- 写入路径: reports/governance/tkt_83b3b8a129bc/*
- 产出文件: architecture_brief.json

## 编译健康度
- Token 预算: 270,000 (实际使用 12,949, 利用率 4.8%)
- 截断: 无
- 降级: 无
- 缓存命中: 否
```

**关键改变**: 不再 dump JSON preview，而是提取结构化摘要。

---

### 2.6 整改：project-workspaces 目录扁平化

**问题**: 当前路径 `artifacts/project-workspaces/wf_df95d935a020/10-project/docs/tracking/task-index.md` 有 6 层嵌套。对于单场景单 workflow 的常见情况，`artifacts/project-workspaces/wf_xxx/` 这层完全多余。

**建议**:

**方案 A (短期)——符号链接**:
在场景根目录创建快捷入口：
```
project/  →  artifacts/project-workspaces/wf_df95d935a020/10-project/
boardroom/ → artifacts/project-workspaces/wf_df95d935a020/00-boardroom/
evidence/  → artifacts/project-workspaces/wf_df95d935a020/20-evidence/
```

**方案 B (长期)——重构目录**:
如果场景始终只有一个 workflow，直接把 `10-project/`、`00-boardroom/`、`20-evidence/` 提到场景根目录下。

---

### 2.7 整改：空目录清理

**问题**: 以下目录当前只有 `.gitkeep`，在审计时造成"看起来有东西但其实没有"的困惑：
- `artifact_uploads/` (空)
- `10-project/src/.gitkeep`
- `10-project/tests/.gitkeep`
- `20-evidence/builds/.gitkeep`
- `20-evidence/git/.gitkeep`
- `20-evidence/releases/.gitkeep`
- `20-evidence/reviews/.gitkeep`
- `20-evidence/tests/.gitkeep`

**建议**: 在 `audit-summary.md` 中明确标注哪些目录为空（见 2.1 的"代码产出"部分）。不需要删除 `.gitkeep`（它们是工作区模板的一部分），但审计摘要应该让人一眼知道"还没走到那一步"。

---

## 三、优先级排序

| 优先级 | 改动 | 工作量 | 收益 |
|--------|------|--------|------|
| P0 | 新增 `audit-summary.md` | 小 (查 DB + 模板渲染) | 解决"一眼看懂"的核心问题 |
| P0 | 巡检报告去重 | 小 (改巡检写入逻辑) | 731 行 → ~80 行 |
| P1 | 治理文档 `.audit.md` | 小 (JSON 提取 + 模板) | 让治理链可审计 |
| P1 | ticket_context_archives 重写 | 中 (重写渲染逻辑) | 让"人工可读"名副其实 |
| P2 | developer_inspector 合并/索引 | 中 (改编译器输出) | 减少 2/3 冗余文件 |
| P2 | 目录快捷入口 | 小 (加符号链接) | 降低路径认知负担 |
| P3 | 空目录标注 | 无 (随 audit-summary 一起) | 消除"有没有写代码"的疑惑 |

---

## 四、不建议改的部分

- **`boardroom_os.db`**: 这是真相源，结构合理，不需要改。审计需求通过 `audit-summary.md` 解决。
- **`runtime-provider-config.json`**: 20 行，结构清晰，保持原样。
- **治理 JSON 的原始结构**: 不要改 JSON schema 本身——它是机器消费的，下游 checker 和 controller 依赖它。只需要在旁边加人工可读层。
- **`workspace-manifest.json`**: 20 行，结构清晰，保持原样。

---

## 五、一句话总结

当前场景目录的问题不是"信息不够"，而是"信息全部以机器格式存在，缺少面向人工审计的摘要层"。整改的核心思路是：**保留所有机器文件不动，在关键位置叠加人工可读的摘要文件**。
