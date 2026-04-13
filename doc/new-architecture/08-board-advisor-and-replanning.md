# 董事会顾问环与重规划

## TL;DR

Board 不只是一个最终审批按钮。  
在自治状态机里，Board 还是一个随时可唤醒的顾问环，用来处理：

- 约束变更
- 高成本分支选择
- 图长期不收敛
- 多个恢复路径都有明显代价

CEO 负责把问题压成结构化顾问包。Board 负责做高层裁决。图补丁还是由 CEO 提交。

## 设计目标

- 让 Board 在真正需要时介入，而不是日常被打扰。
- 让约束变化直接落到图补丁，不再靠补一份长文档解释。
- 让 CEO 能在任意运行节点重新找最优可执行节点。
- 让重规划保留审计线索和版本边界。

## 非目标

- 不把 Board 拉回到日常项目管理。
- 不允许 Board 直接手改图结构和任务细节。
- 不把所有 incident 都升级给 Board。
- 不把顾问会话做成开放式群聊。

## 核心 Contract

### 1. `BoardAdvisorySession`

| 字段 | 含义 |
|---|---|
| `session_id` | 会话标识 |
| `workflow_id` | 所属 workflow |
| `trigger_type` | 为什么需要顾问 |
| `source_version` | 触发时的图版本 |
| `governance_profile_ref` | 触发时生效的治理档位 |
| `affected_nodes[]` | 受影响节点 |
| `decision_pack_refs[]` | 顾问包引用 |
| `option_set[]` | CEO 提供的备选路径 |
| `board_decision` | Board 选择结果 |
| `approved_patch_ref` | 最终批准的图补丁 |

### 2. 触发条件

| `trigger_type` | 何时触发 |
|---|---|
| `CONSTRAINT_CHANGE` | 董事会修改目标、预算、范围 |
| `APPROVAL_POLICY_ESCALATION` | 当前 `approval_mode` 不允许 CEO 自闭环，需要升级裁决 |
| `HIGH_COST_BRANCHING` | 多条高成本路径都可行 |
| `GRAPH_INSTABILITY` | 图反复补丁仍不收敛 |
| `RECOVERY_STALEMATE` | 恢复动作进入僵局 |
| `REVIEW_POLICY_CONFLICT` | 审查意见和业务方向冲突 |

### 3. Board 和 CEO 的边界

| 决策项 | 谁拍板 |
|---|---|
| 业务目标和约束 | `Board` |
| 高成本分支选择 | `Board` |
| 图的具体补丁结构 | `CEO` |
| 节点优先级细节 | `CEO` |
| 具体执行者 | `CEO` |

## 状态机 / 流程

### 顾问环重规划流程图

```mermaid
flowchart LR
    A["触发器\n约束变更 / incident 僵局 / 分支选择"] --> B["CEO 生成顾问包"]
    B --> C["BoardAdvisorySession OPEN"]
    C --> D["Board 选择方向或修改约束"]
    D --> E["CEO 生成 graph patch"]
    E --> F["Reducer 校验 patch"]
    F --> G["写入新 graph_version"]
    G --> H["重算 ReadyIndex / CriticalPathIndex"]
    H --> I["恢复自治执行"]
```

### 顾问包最小内容

- 当前状态摘要
- 受影响节点
- 备选路径 2 到 3 个
- 每条路径的成本、风险、回报
- CEO 推荐项
- 推荐补丁影响面

顾问包只服务裁决，不服务日常讨论。

如果 Board 修改的是 `approval_mode` 或 `audit_mode`，顾问环的正式输出必须同时包含：

- superseding `GovernanceProfile`
- 必要的 graph patch

## 失败与恢复

| 失败 | 说明 | 恢复 |
|---|---|---|
| `ADVISORY_TIMEOUT` | Board 长时间未决 | 冻结受影响分支，其他分支继续 |
| `CONFLICTING_BOARD_DECISION` | 新旧裁决互相冲突 | 生成新顾问包，显式 supersede |
| `PATCH_REJECTED` | CEO 补丁不合法 | 重新基于最新图生成 |
| `ADVISORY_SPAM` | CEO 过度频繁拉顾问 | 开 `GRAPH_INSTABILITY` incident |

恢复原则：

- 顾问环只冻结必要分支，不冻结全局。
- Board 的结论必须版本化，不能口头覆盖旧结论。
- 没有 `approved_patch_ref` 的顾问会话，不得直接改图。

## 统一示例

`library_management_autopilot` 中途如果 Board 改口说：

“先保借阅与库存，管理后台可以后置。”

这时正确链路不是：

- 再补一份说明文档
- 让 CEO 自己在长记忆里体会这个意思

而是：

1. 打开 `BoardAdvisorySession(CONSTRAINT_CHANGE)`。
2. CEO 提供 2 到 3 个补丁方案。
3. Board 选“先收核心借阅闭环”的方案。
4. CEO 生成新 `graph_version`，必要时同时 supersede 当前 `GovernanceProfile`。
5. `ReadyIndex` 重新排序，低价值分支降权或冻结。

## 和现有主线的关系

当前主线已经有：

- `Board Review`
- `Modify Constraints`
- 会议和 ADR

当前主线还缺：

- 正式的 `BoardAdvisorySession`
- 顾问包到图补丁的单一协议
- “Board 决策影响的是图版本”这条硬连接

新架构的重点，就是把 Board 从“审批终点”扩成“重规划顾问环”，但仍然保持低频介入。
