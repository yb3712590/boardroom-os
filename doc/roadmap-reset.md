# Boardroom OS 路线纠偏决议

> 生效时间：2026-03-31
> 用法：这份短版只保留当前还会影响决策的规则。长版背景看 `roadmap-reset/rationale.md`，整段提示词看 `roadmap-reset/agent-reset-prompt.md`。

## 当前阶段唯一主线

Boardroom OS 当前阶段固定为“本地单机 Agent Delivery OS MVP”：

1. 本地单机可运行
2. 事件流与投影是系统真相源
3. Ticket 驱动无状态执行器推进工作
4. Maker-Checker 与 Review Room 构成真实质量闭环
5. React Boardroom UI 只做最薄治理控制壳

任何不直接服务这条主线的新增复杂度，都默认延后。

## 当前产品定义

当前阶段不是：

- 公网多租户 SaaS
- 远程 worker 运维平台
- 云原生基础设施项目
- 以鉴权和接入边界为中心的控制面

当前阶段应当是：

- 本地优先、自托管优先的 Agent Delivery OS 原型
- 用结构化事件、结构化状态和结构化工单治理 Agent Team 的系统
- 先把执行闭环和治理闭环做短、做稳，再补前端壳的产品

## MVP 完成口径

只有下面几件事都成立，当前阶段才算真正收口：

- 用户可以在本地启动系统并初始化一个 workflow
- CEO / Worker 路径可以把任务拆分并推进到可交付结果
- 执行过程由 Ticket、事件和投影驱动，而不是长对话记忆驱动
- Maker-Checker review loop 真正落地，而不是只停留在文档层
- Board 审批可以通过 `Inbox -> Review Room` 查看和裁决
- 有一个最薄的 Web UI 能看 `dashboard / inbox / review room`

当前补记：

- 本地主闭环已经真实可跑，会议室最小版也已落地
- 但冻结能力隔离、后置增强判断、UI/文档收口仍要继续按这套边界推进

## 当前明确不做

下面这些能力保留、不删除，但默认不继续扩张：

- `worker-admin` HTTP 运维控制面
- 多租户 worker scope / 租户级运维能力
- 操作人签名令牌、可信代理断言、独立 auth rejection 读面
- multipart artifact upload
- 本地默认 + 可选对象存储双后端
- 远程 worker handoff / 远程多节点控制面
- 公网身份层与外网暴露策略

## 开发判断规则

以后每个新任务进入实现前，都先回答一个问题：

“它是否直接缩短了本地单机 MVP 从 Board 指令到 Review 交付的路径？”

如果答案是：

- `是`：可以进入当前主线
- `不是，但能明显降低主线实现成本`：按辅线评估
- `不是`：默认后置

执行时继续遵守这些硬规则：

- 每轮只允许选一个方向推进，不要同时跨多个无关方向
- 一次默认做 `2` 到 `4` 个前后衔接、强相关的连续切片
- 主线外代码只允许做最小解堵，不允许顺势扩接口、补平台化抽象或重写目录
- 不因为“顺手可以一起补”就扩张范围；发现支线问题先记到文档，再停
- 只要当前链路已经可运行、可验证、文档真实，就继续往下推进，不为架构纯度补额外复杂度
- 不做大面积重命名、不重排目录、不重建骨架、不为未来假想需求预铺扩展点
- 如果设计与代码不一致，先说明差异，再做最保守、最接近现状的处理
- 汇报和文档只能写已实现、已验证、已暴露的真实状态，不能把计划或 placeholder 写成已完成

## 文档约束与默认阅读顺序

- `README.md` 必须把“本地无状态 agent team + 最薄 Web 壳”写成第一叙事
- `doc/TODO.md` 只保留当前主线待办
- `doc/history/context-baseline.md` 保留稳定不常变的规则和架构基线
- `doc/history/memory-log.md` 只保留最近几天仍会影响实现判断的事实

默认阅读顺序固定为：

1. `README.md`
2. `doc/README.md`
3. `doc/mainline-truth.md`
4. `doc/roadmap-reset.md`
5. `doc/TODO.md`
6. `doc/history/context-baseline.md`
7. `doc/history/memory-log.md`
8. 只按需读相关设计文档
9. 只有在需要精确历史原因、原始验证记录或旧兼容细节时，才看 `doc/history/archive/*`

## 延伸资料

- 长版背景与推导：[roadmap-reset/rationale.md](roadmap-reset/rationale.md)
- 给开发代理整段复制的提示词：[roadmap-reset/agent-reset-prompt.md](roadmap-reset/agent-reset-prompt.md)
