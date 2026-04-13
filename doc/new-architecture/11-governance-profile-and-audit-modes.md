# 治理档位与审计档位

## TL;DR

`小白模式 / 专家模式` 和 `不审计 / 中度审计 / 重度审计` 不能只停留在产品开关层。  
在自治状态机里，它们必须收成一份 workflow 级 `GovernanceProfile`。

这份协议只做两件事：

- 定义谁可以关审批口
- 定义系统要把多少过程材料物化出来

这里有一条底线：

`MINIMAL` 不是“没有审计”。  
它只是“不保留扩展审计材料”。`EventRecord`、图状态变化、最小交付证据，依然不能关。

## 设计目标

- 把治理档位从“UI 选项”收成运行时正式合同。
- 让 CEO、Compiler、Hook Runner、Archive Materializer 消费同一份模式定义。
- 让后续补功能时，只是补执行细节，不用重写总架构。
- 保证“快产出”和“可追溯”都能被同一状态机表达。

## 非目标

- 不在这份规格里直接设计产品页交互。
- 不把 `专家模式` 强行绑定成某一个固定人工角色。
- 不允许审计档位改写系统真相边界。
- 不要求当前主线立刻把所有档位一次做全。

## 核心 Contract

### 1. `GovernanceProfile`

| 字段 | 含义 |
|---|---|
| `profile_id` | 当前治理档位版本标识 |
| `workflow_id` | 所属 workflow |
| `approval_mode` | 当前审批档位 |
| `audit_mode` | 当前审计档位 |
| `auto_approval_scope` | CEO 允许自动关口的节点范围 |
| `expert_review_targets[]` | 专家模式下的升级目标，通常是 `Checker / Board` |
| `audit_materialization_policy` | 当前档位要求落哪些 trace / archive |
| `source_ref` | 来源，一般指向 charter 或 decision asset |
| `supersedes_ref` | 被哪一版取代或取代哪一版 |
| `effective_from_event` | 从哪个事件开始生效 |

`GovernanceProfile` 是 workflow 级治理资产。  
它本身不是系统真相第四层，而是从 `Constitution / Charter / DecisionAsset` 派生出来的结构化控制面协议。

### 2. 审批档位

| `approval_mode` | 说明 |
|---|---|
| `AUTO_CEO` | 默认走自治闭环。只要节点落在 `auto_approval_scope` 内，CEO 可以自动关审批口。 |
| `EXPERT_GATED` | 关键节点不能由 CEO 自闭环。必须显式走 `Checker`、`Board` 或其他专家路径。 |

这两个档位的区别，不是 CEO “人格变了”。  
区别是：**哪些审批口允许 CEO 自动关闭，哪些必须显式升级。**

### 3. 审计档位

| `audit_mode` | 说明 |
|---|---|
| `MINIMAL` | 只保留最小真相和最小交付收口材料，不默认保留逐票 trace 和全量沟通历史。 |
| `TICKET_TRACE` | 保留每个 ticket 的上下文摘要、实施记录、交付结果和证据引用。 |
| `FULL_TIMELINE` | 在 `TICKET_TRACE` 基础上，再保留自治机沟通时间线和重放索引。 |

### 4. 审计底线

无论选哪个 `audit_mode`，下面这些都不能关：

- `EventRecord`
- `TicketNode / TicketEdge` 状态变化
- 最小 `ProcessAsset` 引用
- `closeout` 所需的最低交付证据

也就是说：

- `MINIMAL` 可以少留扩展材料
- 不能少留系统真相

### 5. 消费面

| 消费方 | 必须看到什么 |
|---|---|
| `ProjectionSnapshot` | 当前 `GovernanceProfile` 摘要 |
| `CEO` | `approval_mode`、`auto_approval_scope`、升级边界 |
| `Context Compiler` | `audit_mode`、必需 trace、可裁剪读面 |
| `CompiledExecutionPackage` | 当前票要遵守的治理切片 |
| `Hook Runner` | 当前档位下哪些 hook 是 required / optional |
| `Archive Materializer` | 当前档位下哪些材料进入 `20-evidence`，哪些进入 `90-archive` |

## 状态机 / 流程

### 治理档位消费链

```mermaid
flowchart LR
    A["Board / CEO 修改 charter 或 decision"] --> B["生成新 GovernanceProfile"]
    B --> C["写结构化资产 + supersede 关系"]
    C --> D["ProjectionSnapshot 注入模式摘要"]
    D --> E["Context Compiler 组治理切片"]
    E --> F["Worker / Checker 按模式执行"]
    F --> G["Hook Runner 按 audit_mode 物化材料"]
    G --> H["Archive Materializer 决定是否写时间线归档"]
```

### 模式变更规则

1. 模式变化必须版本化，不能口头生效。
2. `approval_mode` 变化如果影响审批口，必须反映到图边或 gate 上。
3. `audit_mode` 变化只影响材料物化级别，不影响历史事件真假。
4. 打开的执行包如果基于旧模式，必须重编译，不能继续带旧合同执行。

## 失败与恢复

| 失败 | 说明 | 恢复 |
|---|---|---|
| `GOVERNANCE_PROFILE_MISSING` | workflow 没有可解析的治理档位 | 阻止执行包下发，回到 charter / decision 解析 |
| `APPROVAL_SCOPE_LEAK` | CEO 试图自动关闭不在范围内的审批口 | 拒绝动作并升级 |
| `AUDIT_FLOOR_BREACH` | 某档位试图关掉最低真相或最低证据 | 拒绝模式变更 |
| `STALE_GOVERNANCE_PROFILE` | 执行包基于旧模式版本 | 重新编译执行包 |
| `MODE_CHANGE_CONFLICT` | 新旧模式和当前 Board 决策冲突 | 开顾问会话并 supersede |

恢复原则：

- 治理档位错了，优先重编译，不靠临场口头解释。
- 审批边界错了，优先 fail-closed，不先放行再补审计。
- 审计级别可以降，但只能降扩展材料，不能降真相底座。

## 统一示例

`library_management_autopilot` 如果要快速产出 MVP，可以这样配：

- `approval_mode = AUTO_CEO`
- `audit_mode = MINIMAL`

这时系统仍然会保留：

- 事件
- 图状态变化
- 真实源码交付引用
- 最低 closeout 证据

只是不会默认保留：

- 每张票的完整上下文包
- 全量自治沟通时间线

如果要做重审计复盘，则切成：

- `approval_mode = EXPERT_GATED`
- `audit_mode = FULL_TIMELINE`

这时关键节点要显式过专家路径，系统还会保留逐票 trace 和沟通时间线索引，支持按时间轴重放。

## 和现有主线的关系

当前主线已经有这些相关碎片：

- `Board Review`
- `Modify Constraints`
- `documentation_updates`
- `evidence capture`
- `transcript archive`

当前缺的不是“能不能留痕”，而是：

- 没有 workflow 级统一治理档位
- 审批强度和审计强度还没被正式解耦
- 没有“最低真相永远不能关”这条硬规则

这份规格补的，就是这条横切协议。
