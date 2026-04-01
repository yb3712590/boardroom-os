# Boardroom OS

> 一个本地优先、事件溯源、用无状态 Agent Team 推进交付的控制面原型。

## 项目现在要解决什么

Boardroom OS 的目标不是先做一套复杂的远程基础设施，而是先做一个能在本地跑通的 Agent Delivery OS：

- 用户像董事会，只给目标、约束和验收标准
- 系统按 `Board -> CEO -> Worker -> Review` 的链路拆解和推进工作
- 执行器保持无状态，真实状态落在事件流和投影里
- 关键节点通过 `Inbox -> Review Room` 进入人工审查
- 最后再在运行框架外套一层轻量 Web 可视化壳

路线纠偏决议见 [doc/roadmap-reset.md](doc/roadmap-reset.md)。

## 当前主线

从现在开始，项目主线按下面的顺序推进：

1. 跑通本地单机闭环：事件流、Ticket 生命周期、基础 runtime、投影读面
2. 补齐无状态 Agent Team 治理能力：employee 生命周期、Maker-Checker、Review 闭环
3. 把 Context Compiler 从最小原型推进到足够支撑本地执行的稳定编译链
4. 实现最薄的 React Boardroom UI，只做治理控制壳，不承载工作流真相

## 仓库里已经有什么

当前仓库已经有一个可运行的后端切片：

- FastAPI + SQLite 的控制面原型
- 事件流、projection、ticket 生命周期、approval / incident / breaker 等基础治理骨架
- `dashboard`、`inbox`、`review room`、`worker-runtime` 等读面
- 最小可运行的 runtime 与 `ticket-result-submit` 闭环
- 视觉里程碑 `Maker -> Checker -> Fix Ticket / Escalation -> Review Room` 最小闭环
- artifact 持久化、索引和清理链路的基础能力
- Context Compiler 已能把常见本地文本输入直接内联进执行包；超预算的文本与 JSON 会退到确定性预览而不是纯引用，并保留结构化降级原因和 artifact URL 兜底
- Context Compiler 现在也会把图片 / PDF 输入作为结构化媒体引用放进执行包，把其他二进制输入作为结构化下载引用放进执行包；执行器能直接知道它是可预览媒体还是仅下载附件，而不是只拿到一条模糊 descriptor
- Context Compiler 现在还能在编译时拉入同 workspace 的本地历史 review / incident / artifact 摘要卡片，让 worker 不只看当前输入，也能带着过去的审批结论和事故教训进入执行

这些能力足以支撑继续收敛到“本地单机 Agent Delivery OS MVP”。

## 已有但降级为后置能力的部分

仓库里已经落了一批更重的基础设施能力，包括：

- 多租户 worker scope 与 `worker-admin` 运维控制面
- 操作人令牌、可信代理断言、独立鉴权拒绝读面
- multipart artifact upload 与可选对象存储后端
- 更偏远程 worker handoff 的交付链路

这些实现不会被立刻删除，但它们不再代表当前阶段的主线，也不应继续吞掉主要开发预算。除非某项工作直接服务本地 MVP，否则默认后置。

## 当前最重要的未完成项

- 完成 employee hire / replace / freeze 生命周期
- 把只覆盖视觉里程碑的 Maker-Checker 闭环扩到更多关键产物，并补完换人策略等剩余返工治理
- 继续把 Context Compiler 从“文本可内联 + 结构化二进制引用 + 本地历史摘要可检索”的当前版本推进到更稳定的本地执行链，补完更细的大文件策略、预算压缩和后续渲染层能力
- 实现最薄的 React Boardroom UI，把 `dashboard / inbox / review room` 接起来

更具体的执行项见 [doc/TODO.md](doc/TODO.md)。

## 快速开始

启动后端：

```bash
cd backend
source .venv/bin/activate
uvicorn app.main:app --reload
```

运行测试：

```bash
cd backend
source .venv/bin/activate
python -m pytest tests -q
```

## 文档入口

- [doc/roadmap-reset.md](doc/roadmap-reset.md)：路线纠偏决议与当前阶段边界
- [doc/TODO.md](doc/TODO.md)：当前主线待办
- [doc/backend-runtime-guide.md](doc/backend-runtime-guide.md)：后端运行方式与现有 runtime / worker 面说明
- [doc/feature-spec.md](doc/feature-spec.md)：产品边界与治理原则
- [doc/design/message-bus-design.md](doc/design/message-bus-design.md)：后端主线设计
- [doc/design/boardroom-ui-design.md](doc/design/boardroom-ui-design.md)：Boardroom UI 产品边界
- [doc/history/memory-log.md](doc/history/memory-log.md)：近几轮进展与长期记忆

## 当前约束

- 这是一个本地优先、自托管优先的原型，不是公网多租户 SaaS
- 当前最需要的是把主链路做短、做稳、做可视化，而不是继续扩远程运维面
- 能服务本地单机 MVP 的复杂度可以接受；不能直接服务 MVP 的复杂度默认延后

## 项目原则

- 治理比热闹重要
- 审计比想象重要
- 幂等比炫技重要
- 结构化协作比自由群聊可靠
- 本地可跑通，比过早远程化更重要
