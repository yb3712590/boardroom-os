# Worker 上下文与执行包

## TL;DR

Worker 的“无状态”不等于“空着脑袋开干”。  
它的正确形态是：**每次启动都拿到一份受控、封闭、最小、可审计的 `CompiledExecutionPackage`。**

这份执行包要同时约束：

- 要做什么
- 能读什么
- 能写什么
- 该遵守什么组织规则
- 完成后会触发哪些标准动作

## 设计目标

- 避免 Worker 因为上下文过宽而幻觉。
- 避免 Worker 因为上下文过窄而越权瞎写。
- 把“文档更新、证据补齐、git closeout”这些要求，从提示词习惯改成正式合同。
- 让同一张票在 `implementation / review / debugging` 之间切换时，执行包也跟着切。

## 非目标

- 不把全仓库一次性塞进 prompt。
- 不允许 Worker 自己决定额外写哪些目录。
- 不让角色模板继续直接充当 runtime 唯一执行键。
- 不让 Worker 通过私聊补齐缺失上下文。

## 核心 Contract

### 1. `CompiledExecutionPackage`

| 字段 | 含义 |
|---|---|
| `ticket_ref` | 当前 `ticket_id / node_id / graph_version` |
| `task_frame` | 当前目标、完成定义、失败定义 |
| `compiled_role` | 当前票需要的角色约束 |
| `compiled_constraints` | 安全、品牌、技术、合规约束 |
| `governance_mode_slice` | 当前 workflow 的 `approval_mode / audit_mode` 和适用边界 |
| `atomic_context_bundle` | 当前票的最小证据集 |
| `required_doc_surfaces` | 必须同步的文档面 |
| `allowed_tools` | 允许工具集合 |
| `allowed_write_set` | 允许写入路径和对象 |
| `output_contract` | 必须返回的 schema 和证据 |
| `org_boundary` | 上游、下游、升级路径、协作边界 |
| `skill_binding_refs` | 当前票解析出的技能绑定 |
| `idempotency_key` | 本次执行的幂等键 |

### 2. Worker 上下文分层

| 层 | 内容 | 默认预算 |
|---|---|---|
| `W0 Constitution Slice` | 必要规则、schema、写权、hook 说明、治理档位切片 | 小 |
| `W1 Task Frame` | 当前票目标、验收标准、失败边界 | 中 |
| `W2 Evidence Slice` | 必要代码、文档、ADR、项目地图切片 | 中 |
| `W3 Runtime Guard` | 工具、写集、超时、重试预算 | 小 |

Worker 默认只看 `W0 + W1 + W2 + W3`。  
历史 transcript、旧长文档、无关模块代码都不默认进入执行包。

### 3. `org_boundary`

`org_boundary` 至少包含：

- `upstream_providers`
- `downstream_consumers`
- `review_owner`
- `escalation_targets`
- `forbidden_direct_contacts`

它的作用很单纯：让 Worker 知道自己不是一个人在仓库里乱写。

### 4. 交付合同

| 票类型 | 最低要求 |
|---|---|
| `source_code_delivery` | 源码、测试证据、文档更新、git 证据 |
| `structured_document_delivery` | 正式文档、来源引用、版本关系、下游消费说明 |
| `maker_checker_verdict` | findings、严重级别、证据引用、阻塞判断 |

## 状态机 / 流程

执行包生命周期固定如下：

1. `Scheduler` 选中 ready 节点。
2. `Context Compiler` 根据 `TicketNode + ProcessAsset + ProjectMap + GovernanceProfile` 组包。
3. `Skill Resolver` 绑定当前票所需技能。
4. Worker 执行。
5. 结果进入 `schema / write-set / evidence` 校验。
6. 校验通过后再触发 `RoleHook`。

这条链里，Worker 只负责第 4 步。  
组包、验收、后置动作都不靠 Worker 自觉。

这里有一条补充规则：

- `audit_mode = MINIMAL` 不等于“没有审计要求”，只表示执行包里不会强制带上逐票 trace 和全量时间线档位。

## 失败与恢复

| 失败 | 说明 | 恢复 |
|---|---|---|
| `PACKAGE_STALE` | 执行包基于旧图或旧约束 | 重新编译执行包 |
| `WRITE_SET_VIOLATION` | 写到了未授权区域 | 失败并开 incident |
| `DOC_SURFACE_MISSING` | 漏了必要文档更新 | 拒绝开放下游 |
| `EVIDENCE_GAP` | 没交测试、git 或 review 证据 | 触发补证或 fix 票 |
| `ORG_BOUNDARY_BREACH` | 试图绕过审查或直接改不该改的东西 | 拒绝结果 |

恢复原则只有两个：

- 能重编译就重编译，不重用脏执行包。
- 不能用“靠提示词再提醒一次”代替正式合同。

## 统一示例

当 `node_backend_catalog_build` 被编译成执行包时，它应该拿到：

- 当前 backend build 的目标和验收标准
- `node_technology_decision` 和 `node_detailed_design` 的必要切片
- backend 相关模块的 `ProjectMap` 片段
- `10-project/src/backend/*` 和 `20-evidence/tests/<ticket>/*` 这类允许写集
- 必须同步的 `10-project/docs/` 文档面
- 完成后要触发的 `documentation_sync`、`evidence_capture`、`git_closeout` hook

如果同一节点转成 `debugging` 票，执行包会变：

- `task_frame` 从“实现功能”变成“定位故障并修复”
- 技能绑定切到调试类
- 证据切片更多看 incident、失败指纹和最近 diff

## 和现有主线的关系

当前主线已经有：

- `compiled_execution_package`
- `allowed_write_set`
- `allowed_tools`
- `required_read_refs`
- `documentation_updates`

当前主线还不够硬的地方：

- 组织边界还比较弱，Worker 容易只看到“我要改什么”，看不到“我会影响谁”。
- 技能绑定还没有正式进入执行包合同。
- 不同任务类型的分层上下文预算还没正式立法。

新架构做的不是发明全新对象，而是把现有执行包收成真正的 runtime 合同。
