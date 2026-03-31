# Boardroom OS 路线纠偏决议

> 生效时间：2026-03-31

## 1. 这份决议解决什么问题

项目最近几轮实现明显偏向了鉴权、worker 运维控制面、多租户 scope、对象存储和远程交付链路。它们本身不是错误方向，但已经开始挤压项目原始目标：

- 本地运行
- 事件溯源状态总线
- Ticket 驱动无状态 Agent Team
- 真实的审查与审批闭环
- 最后套一层轻量 Web 可视化壳

这份决议的目的，是把主线重新拉回“本地单机 Agent Delivery OS MVP”。

## 2. 重新确认的产品定义

Boardroom OS 当前阶段不是：

- 公网多租户 SaaS
- 远程 worker 运维平台
- 云原生基础设施项目
- 以鉴权和接入边界为中心的控制面

Boardroom OS 当前阶段应当是：

- 一个本地优先、自托管优先的 Agent Delivery OS 原型
- 一个用结构化事件、结构化状态和结构化工单治理 Agent Team 的系统
- 一个先把执行闭环和治理闭环做短、做稳，再补前端壳的产品

## 3. 当前阶段唯一主线

从现在起，项目主线固定为：

1. 本地单机可运行
2. 事件流与投影是系统真相源
3. Ticket 驱动无状态执行器推进工作
4. Maker-Checker 与 Review Room 构成真实质量闭环
5. React Boardroom UI 只做最薄治理控制壳

任何不直接服务这条主线的新增复杂度，都默认延后。

## 4. MVP 的完成定义

只有当下面几件事都成立，才算当前阶段 MVP 真正完成：

- 用户可以在本地启动系统并初始化一个 workflow
- CEO / Worker 路径可以把任务拆分并推进到可交付结果
- 执行过程由 Ticket、事件和投影驱动，而不是长对话记忆驱动
- Maker-Checker review loop 真正落地，而不是只停留在文档层
- Board 审批可以通过 `Inbox -> Review Room` 查看和裁决
- 有一个最薄的 Web UI 能看 `dashboard / inbox / review room`

当前进度补记：

- `Inbox -> Review Room` 这条董事会审批链已经真实可用
- 视觉里程碑已经具备最小 `Maker -> Checker -> Review Room` 闭环
- 但 Maker-Checker 目前仍只覆盖 `VISUAL_MILESTONE + ui_milestone_review@1`，所以整体里程碑还不能算完全关闭

## 5. 已实现但降级为后置能力

下面这些能力已经在仓库中存在，但从这份决议开始降级为“保留、不扩张、非主线”：

- 多租户 worker scope 绑定
- `worker-admin` HTTP 运维控制面
- 操作人签名令牌、可信代理断言、独立 auth rejection 读面
- multipart artifact upload
- 本地默认 + 可选对象存储双后端
- 更偏远程 worker handoff 的交付链路

处理原则：

- 不主动删除现有实现
- 不把它们继续包装成当前阶段核心卖点
- 不继续为它们新增大块设计和实现预算
- 只有在它们直接服务本地 MVP 时，才允许做最小必要修改

## 6. 当前阶段明确后置的方向

在本地 MVP 收口完成前，下面这些方向默认冻结：

- 新的 `worker-admin` 读写接口
- 更细粒度的租户隔离与租户级运维能力
- 面向公网的身份层、外网暴露策略和强信任边界
- 浏览器直传、云厂商预签名直传、远程对象存储链路增强
- 为远程多节点运行设计的新复杂控制面

## 7. 当前阶段必须推进的能力

接下来优先级最高的能力是：

- employee hire / replace / freeze 生命周期
- 把只覆盖视觉里程碑的 Maker-Checker review loop 扩到更多关键产物
- 能稳定支撑本地执行的 Context Compiler
- 最薄的 React Boardroom UI

这些能力比继续补 `auth / worker-admin / object store` 更符合项目起点，也更能尽快形成可体验产品。

## 8. 对现有代码的处理原则

这次纠偏不是一次“清库重来”，而是一次“主线收口”。

因此：

- 保留已有 backend 基础和可运行切片
- 允许继续使用现有 projection、artifact、runtime、worker-runtime 读面
- 对已有重型基础设施代码采取“冻结、收口、少动”的策略
- 新开发优先补主链路缺口，而不是再给外围控制面加层次

## 9. 后续开发的判断规则

以后每个新任务在进入实现前，都先回答一个问题：

“它是否直接缩短了本地单机 MVP 从 Board 指令到 Review 交付的路径？”

如果答案是：

- `是`：可以进入当前主线
- `不是，但能明显降低主线实现成本`：按辅线评估
- `不是`：默认后置

## 10. 文档与叙事约束

从这份决议开始：

- `README.md` 必须把“本地无状态 agent team + 最薄 web 壳”写成第一叙事
- `doc/TODO.md` 只保留当前主线待办
- 历史文档仍保留真实演进记录，但不再代表当前阶段优先级

这不是否认已经做过的工作，而是明确项目现在真正要冲向哪里。
