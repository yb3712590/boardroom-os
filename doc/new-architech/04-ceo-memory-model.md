# CEO 记忆模型

## TL;DR

CEO 不是一个长期挂着的聊天会话。  
CEO 的正确形态是：**被事件唤醒时，读取受控快照和资产切片，做判断，输出受控动作，然后离开。**

CEO 必须有分层记忆。  
不然它不是爆上下文，就是被长历史拖着走。

## 设计目标

- 把 CEO 从长对话记忆改成分层快照记忆。
- 让 CEO 始终先看当前状态，再按需看资产，而不是先翻旧文档。
- 限制 CEO 的默认读面，避免“什么都给一点，最后什么都没抓住”。
- 支持 CEO 在局部失败和约束变化时快速重规划。

## 非目标

- 不让 CEO 直接看全量 transcript。
- 不把 CEO 变成图引擎、调度器或文档仓库本身。
- 不要求 CEO 永远保留上一次 prompt 的完整上下文。
- 不允许 CEO 靠模糊印象决定派单。

## 核心 Contract

### 1. CEO 记忆五层

| 层 | 内容 | 默认消费方式 |
|---|---|---|
| `M0 Constitution` | 角色合同、审批规则、hook 规则、schema | 常驻小片段 |
| `M1 Control Snapshot` | workflow 状态、ready 队列、incidents、open approvals、graph digest | 每次唤醒必读 |
| `M2 Replan Focus` | 当前需要重决策的节点、补丁候选、关键依赖摘要 | 按需注入 |
| `M3 Process Assets` | ADR、治理文档摘要、FailureFingerprint、ProjectMap 切片 | 受控检索 |
| `M4 Audit Archive` | 原始事件、历史 transcript、旧投影 | 默认不读 |

### 2. `ProjectionSnapshot`

CEO 可读的标准快照至少包含：

- `workflow_status`
- `graph_version`
- `ready_nodes[]`
- `blocked_nodes[]`
- `hot_dependencies[]`
- `open_incidents[]`
- `open_board_items[]`
- `recent_asset_digests[]`
- `reuse_candidates[]`

### 3. 上下文预算

CEO 的上下文预算按比例切，不按“谁重要就多塞点”来拍脑袋。

| 区块 | 默认占比 |
|---|---|
| `M0` | 10% |
| `M1` | 40% |
| `M2` | 20% |
| `M3` | 20% |
| 预留缓冲 | 10% |

一旦 `M3` 资产切片太多，先压缩资产，不压缩 `M1` 当前快照。

### 4. 默认读面顺序

1. `ProjectionSnapshot`
2. 当前图版本摘要
3. 当前最热 incident
4. 当前 Board 队列
5. 必要 `ProcessAsset` 摘要

CEO 不得跳过当前快照，直接根据旧文档做大动作。

## 状态机 / 流程

CEO 唤醒链固定如下：

1. 接到触发器。
2. 生成当前 `ProjectionSnapshot`。
3. 判断是否需要 `M2 Replan Focus`。
4. 只在需要时提升 `M3 ProcessAssets`。
5. 输出受控动作。
6. Reducer 校验后写事件。

可接受的触发器固定是：

- `BOARD_DIRECTIVE_RECEIVED`
- `TICKET_COMPLETED`
- `TICKET_FAILED`
- `INCIDENT_ESCALATED`
- `BOARD_DECISION_RECORDED`
- `TIMEOUT_RECHECK_DUE`

## 失败与恢复

| 失败 | 说明 | 恢复 |
|---|---|---|
| `SNAPSHOT_STALE` | 快照基于旧版本投影 | 重抓快照 |
| `MEMORY_OVERFLOW` | 资产切片撑爆窗口 | 只保留 digest，降级细节 |
| `REPLAN_LOOP` | CEO 反复 patch 图但不收敛 | 打开 `GRAPH_THRASHING` incident |
| `ASSET_MISREAD` | CEO 引用了不再有效的旧资产 | 强制重检版本关系 |

恢复原则：

- 当前状态优先于历史解释。
- 摘要优先于正文。
- 新鲜投影优先于旧记忆。

## 统一示例

当 `library_management_autopilot` 卡在 `build` 阶段时，CEO 应先看到：

- 哪些节点 ready
- 哪些节点 blocked
- 哪个分支 failure heat 最高
- 哪些 build 已有真实源码证据，哪些只有流程痕迹

这时 CEO 如果还需要进一步判断，才去读：

- 最近一版 `backlog_recommendation` 摘要
- 相关 `FailureFingerprint`
- backend 或 frontend 的 `ProjectMap` 切片

它不该先去翻一长串历史讨论，再猜今天该派哪张票。

## 和现有主线的关系

当前主线已经有：

- `ceo_shadow`
- `task_sensemaking`
- `capability_plan`
- `controller_state`
- `reuse_candidates`

当前主线还缺：

- 正式的 `M0-M4` 记忆层协议
- 明确的上下文预算
- `M2 Replan Focus` 这种“只为了当前决策存在”的层
- CEO 默认读面顺序的硬规则

新架构的 CEO 记忆模型，核心就是把“会聊天的 CEO”收成“会读快照的 CEO”。
