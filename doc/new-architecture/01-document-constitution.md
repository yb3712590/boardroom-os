# 文档宪法

## TL;DR

文档体系必须固定骨架、固定责任、固定写法。  
任何角色都不能“顺手写一份文档当真相”。文档只允许做四种事：

- `REPLACE_VIEW`
- `APPEND_LEDGER`
- `VERSION_SUPERSEDE`
- `IMMUTABLE_ARCHIVE`

## 设计目标

- 保证文档长期可读，不会越跑越乱。
- 让每类文档只有一种职责，不再一份文档同时当计划、记忆、状态、报告。
- 让 CEO、Worker、Checker 知道“该读什么、能改什么、改完会触发什么”。
- 让文档和事件、图、资产的关系可追踪。

## 非目标

- 不把 Markdown 文件当控制面数据库。
- 不允许 Boardroom UI 直接改写真相文档。
- 不为每次执行都生成新的“解释性流水账”。
- 不要求所有过程材料都默认进入上下文。

## 核心 Contract

### 1. 固定目录骨架

```text
workflow-root/
├─ 00-boardroom/
│  ├─ 00-constitution/
│  ├─ 10-charter/
│  ├─ 20-graph/
│  ├─ 30-decisions/
│  ├─ 40-runtime/
│  └─ 50-project-map/
├─ 10-project/
│  ├─ src/
│  ├─ docs/
│  └─ assets/
├─ 20-evidence/
│  ├─ tests/
│  ├─ reviews/
│  ├─ git/
│  └─ delivery/
└─ 90-archive/
   ├─ events/
   ├─ projections/
   └─ transcripts/
```

### 2. 文档责任矩阵

| 文档面 | 谁能写 | 允许更新模式 | 真相来源 |
|---|---|---|---|
| `00-constitution` | 只有治理变更 | `VERSION_SUPERSEDE` | 宪法层 |
| `10-charter` | Board / CEO | `VERSION_SUPERSEDE` | Board 指令 |
| `20-graph` | 只允许物化器 | `REPLACE_VIEW` | 图与投影 |
| `30-decisions` | CEO / Board / 会议秘书 | `VERSION_SUPERSEDE` | 决策资产 |
| `40-runtime` | Hook / runtime | `APPEND_LEDGER` | 事件与执行回执 |
| `50-project-map` | Hook / Compiler / Checker | `REPLACE_VIEW` | 项目地图资产 |
| `10-project/docs` | Worker + Hook | `VERSION_SUPERSEDE` | 交付结果 |
| `20-evidence/*` | Hook / runtime | `APPEND_LEDGER` | 证据资产 |
| `90-archive/*` | 只允许归档器 | `IMMUTABLE_ARCHIVE` | 审计材料 |

### 3. 文档更新模式

| 模式 | 适用对象 | 规则 |
|---|---|---|
| `REPLACE_VIEW` | 当前状态视图 | 每次全量重算，旧版本不再被当默认读面 |
| `APPEND_LEDGER` | 回执、证据、incident、git 记录 | 只能追加，不能回写历史 |
| `VERSION_SUPERSEDE` | charter、ADR、治理文档、产品说明 | 允许新版本替代默认视图，但旧版必须可追溯 |
| `IMMUTABLE_ARCHIVE` | transcript、原始事件导出、旧投影快照 | 一旦归档不得编辑 |

### 4. `GovernanceProfile` 固定入口

- `approval_mode` 和 `audit_mode` 必须以结构化字段存在于 `10-charter` 或受控 `30-decisions` 资产里。
- 任何角色都不能从正文语气里“猜测当前是不是小白模式 / 专家模式”。
- `audit_mode = MINIMAL` 只允许减少扩展审计材料，不允许关闭 `20-graph`、`20-evidence` 的最低交付证据和 `90-archive/events` 的基础归档。
- `audit_mode = FULL_TIMELINE` 时，`90-archive/transcripts/` 和时间线索引必须成为正式物化面。

### 5. 文档最小读写权限

- Worker 默认只读 `00-constitution`、当前 `charter` 摘要、相关 `20-graph` 摘要、必要 `30-decisions` 和 `50-project-map` 切片。
- Worker 默认只写 `10-project/*` 的允许写集，以及自己票对应的 `20-evidence/*`。
- CEO 不直接写 `10-project/src`。
- Board 不直接改项目源码和运行回执。
- 任何角色都不能直接编辑 `20-graph` 当前视图。它必须由图物化器重算。

### 6. 文档可读性规则

每类人类可读文档都必须固定这些段落：

- 这份文档是什么
- 当前版本结论
- 来源引用
- 影响范围
- 下游消费方
- 版本与替代关系

## 状态机 / 流程

文档更新链固定是这条：

`EventRecord -> ProjectionSnapshot / ProcessAsset -> Document Materializer -> 文档视图`

禁止这条反向路径：

`人工编辑文档 -> 系统推断真实状态`

只有两类例外允许文档先变，再触发状态机：

- Board 在 `10-charter` 上给出新约束
- Board / CEO 在 `30-decisions` 上批准新版 ADR

即便这样，真正驱动系统的也不是文档正文，而是对应的结构化命令或资产记录。

## 失败与恢复

### 文档侧常见失败

| 失败 | 判断方式 | 恢复动作 |
|---|---|---|
| 文档和投影不一致 | 视图 hash 和真相 hash 不匹配 | 重建 `REPLACE_VIEW` 文档 |
| Worker 漏更文档 | hook 检到 `documentation_updates` 缺口 | 生成 `DOCUMENTATION_SYNC_REQUIRED` |
| 证据没落盘就宣称完成 | `20-evidence` 缺资产 | 拒绝开放下游节点 |
| charter 被正文改乱 | 正文无法映射成结构化约束 | 回退到上一版 `VERSION_SUPERSEDE` |
| 治理档位正文漂移 | 正文和结构化 `GovernanceProfile` 不一致 | 以结构字段为准并出新版本 |

### 恢复原则

- 可重算视图一律重算，不人工修补。
- 可版本替代文档一律出新版本，不回改旧版。
- 原始审计材料永不覆盖。

## 统一示例

在 `library_management_autopilot` 里：

- `node_backlog_recommendation` 完成后，会在 `00-boardroom/30-decisions/` 形成一版正式 backlog 决策文档。
- `node_backend_catalog_build` 完成后，源码写进 `10-project/src`，测试和 git 回执写进 `20-evidence/`。
- 图视图会重算 `00-boardroom/20-graph/ready-queue.md` 和 `critical-path.md`。
- 如果 build 只写了代码，没写文档更新说明，节点不会对 `node_delivery_check` 开放。

## 和现有主线的关系

当前主线已经有好的起点：

- 三分区目录 `00-boardroom / 10-project / 20-evidence`
- `documentation_updates`
- `worker-preflight / worker-postrun / evidence-capture / git-closeout` 回执

当前主线还没完全立法的地方：

- 哪些文档是视图，哪些是资产，哪些是归档，还不够硬。
- 很多高频文档还同时承担“人类阅读说明”和“系统状态来源”两种职责。
- `ProjectMap` 还没有正式落成文档面。

新架构做的事很明确：把文档降级成稳定视图，不再让它兼任隐式状态机。
