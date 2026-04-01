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
- `workforce` 读面，以及按角色泳道看的最小员工状态面
- 最小可运行的 runtime 与 `ticket-result-submit` 闭环
- 视觉里程碑 `Maker -> Checker -> Fix Ticket / Escalation -> Review Room` 最小闭环
- 员工治理现在也进入事件流主线：默认 roster 启动时会 bootstrap 成 employee 事件，`employee-hire-request / employee-replace-request` 会走 `Inbox -> Review Room` 的 `CORE_HIRE_APPROVAL` 审批闭环，`employee-freeze` 会立即阻止新 dispatch / lease / start / worker-runtime bootstrap
- Maker-Checker 返工票现在会默认排除刚刚被打回的原 maker，调度器会优先换给同角色的其他 active 员工，而不是继续把 fix 票发回同一个人
- artifact 持久化、索引和清理链路的基础能力
- Context Compiler 已能把常见本地文本输入直接内联进执行包；超预算的 `TEXT / MARKDOWN / JSON` 现在会先退到确定性的相关片段编译，片段仍放不下时再退到确定性预览，并保留结构化降级原因、selector 和 artifact URL 兜底
- Context Compiler 现在也会把图片 / PDF 输入作为结构化媒体引用放进执行包，把其他二进制输入作为结构化下载引用放进执行包；执行器能直接知道它是可预览媒体还是仅下载附件，而不是只拿到一条模糊 descriptor
- Context Compiler 现在还能在编译时拉入同 workspace 的本地历史 review / incident / artifact 摘要卡片，让 worker 不只看当前输入，也能带着过去的审批结论和事故教训进入执行
- Context Compiler 现在会对显式输入逐级执行 `完整内联 -> 相关片段 -> 局部预览 -> 引用描述` 的严格预算闸门；如果连 mandatory 输入的最小 descriptor 都放不进剩余预算，编译会按 `FAIL_CLOSED` 直接失败，而不是偷偷把超预算包继续交给 worker
- `Review Room` 的 developer inspector 现在能直接汇总本次编译的预算总量、已用预算、剩余预算、被截掉的 token，以及检索/显式输入的降级数量；排障时不再需要先手翻原始 manifest 才知道这次编译是不是“勉强塞进去”的
- Context Compiler 现在除了 `bundle / manifest` 外，还会产出一个最小 `json_messages_v1` 渲染结果；worker execution package 和 `Review Room` developer inspector 都能直接看到同一份最终输入视图，不用再靠手翻 context blocks 反推真正交付给执行器的内容
- in-process runtime 现在也支持一个最小真实 provider 适配层：当 lease owner 对应 employee 的 `provider_id=prov_openai_compat`，并且本地配置了兼容 OpenAI `responses` 的 `base_url / api_key / model` 后，runtime 会直接调用 `POST {base_url}/responses`；还可以额外用 `BOARDROOM_OS_PROVIDER_OPENAI_COMPAT_REASONING_EFFORT` 指定 `low / medium / high / xhigh`；未配置时继续走本地 deterministic runtime，保证零配置链路不断
- 这条真实 provider 路径会把成功、`429`、超时 / 连接失败 / `5xx`、`401/403` 和坏响应分别映射回现有治理链；只有 `PROVIDER_RATE_LIMITED` 和 `UPSTREAM_UNAVAILABLE` 会进入既有 provider pause / incident 处理，鉴权失败和坏响应只让当前 ticket 失败
- `Review Room` 的 compile summary 和 worker execution package 现在都会显式给出展示语义：文本类会落到 `INLINE_FULL / INLINE_FRAGMENT / INLINE_PARTIAL / REFERENCE_ONLY`，图片 / PDF 会带 `display_hint=OPEN_PREVIEW_URL`，其他下载型二进制会带 `display_hint=DOWNLOAD_ATTACHMENT`

这些能力足以支撑继续收敛到“本地单机 Agent Delivery OS MVP”。

## 已有但降级为后置能力的部分

仓库里已经落了一批更重的基础设施能力，包括：

- 多租户 worker scope 与 `worker-admin` 运维控制面
- 操作人令牌、可信代理断言、独立鉴权拒绝读面
- multipart artifact upload 与可选对象存储后端
- 更偏远程 worker handoff 的交付链路

这些实现不会被立刻删除，但它们不再代表当前阶段的主线，也不应继续吞掉主要开发预算。除非某项工作直接服务本地 MVP，否则默认后置。

## 当前最重要的未完成项

- 在已落地的核心 employee lifecycle（`hire / replace / freeze`）之上，继续补完整 staffing 治理：更丰富的换人策略、恢复/返岗策略，以及与更多票型联动
- 把只覆盖视觉里程碑的 Maker-Checker 闭环扩到更多关键产物，并补完换人策略等剩余返工治理
- 实现最薄的 React Boardroom UI，把 `dashboard / inbox / review room` 接起来

说明：真实 `prov_openai_compat` provider 适配层、当前 MVP 需要的大输入 / 媒体 / 下载型二进制展示语义，这一轮已经按本地单机口径收口；更远的 provider routing、多模型策略、浏览器直传和云预签名 multipart 继续后置。

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
