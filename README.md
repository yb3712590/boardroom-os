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
- `project-init` 现在不再只创建 workflow：后端会先落一份 board brief artifact，再自动创建首张 `consensus_document@1` 范围票，同步串行跑 `maker -> checker`，把默认本地路径直接推进到首个 `MEETING_ESCALATION` review；如果没有可派单员工或途中出现 incident，就停在真实 pending / incident 状态，不会伪造 review
- 首个 scope review 被 `board-approve` 通过后，后端现在会从已批准的 `consensus_document` artifact 里读取全部“当前支持范围内”的 follow-up，先整组校验，再原子创建真实执行票，并继续同步推进到下一个真实停点：新的 review、incident、无可派单员工或没有进一步状态变化
- 这条 scope follow-up 续跑仍然保持 fail-closed 和主线收口：当前只支持 `frontend_engineer -> ui_designer_primary`，任一 follow-up 的 artifact、JSON、`owner_role`、重复 `ticket_id` 或现有投影冲突不合法，整次 `board-approve` 都会被拒绝，review 继续待决，不会出现“部分落票、部分跳过”的假完成
- 多张同级 follow-up 现在也会按 ticket 隔离写入范围：每张票各自写到自己的 `artifacts/ui/scope-followups/<ticket_id>/` 和 `reports/review/<ticket_id>/` 下，避免兄弟票互相覆盖
- `Maker -> Checker -> Fix Ticket / Escalation -> Review Room` 现在已覆盖两条真实关键产物链：视觉里程碑 `ui_milestone_review@1`，以及会议/范围决策文档 `consensus_document@1`
- 员工治理现在也进入事件流主线：默认 roster 启动时会 bootstrap 成 employee 事件，`employee-hire-request / employee-replace-request` 会走 `Inbox -> Review Room` 的 `CORE_HIRE_APPROVAL` 审批闭环，`employee-freeze` 会立即阻止新 dispatch / lease / start / worker-runtime bootstrap，`employee-restore` 会把被冻结员工直接恢复到可派单、可手动接单、可进入 worker-runtime 的 active 状态
- 员工变更现在会联动处理中票：被冻结或被替换员工手上的已 lease 未开工票会自动回收到 `PENDING` 并排除原员工再次接手；执行中票会进入 `staffing containment` 围堵，打开 incident / circuit breaker，并同步暴露到 `dashboard / inbox / workforce`
- `employee-restore` 现在也会自动恢复因 freeze 被回收的旧票，移除这次冻结临时加上的排除名单；`incident-resolve` 也新增了 `RESTORE_AND_RETRY_LATEST_STAFFING_CONTAINMENT`，可以把被 staffing containment 打断的执行票重新拉回待执行链，而不用人工重建票
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
- 仓库现在也有一个独立运行的 React Boardroom UI 壳，放在 `frontend/`
  - 首页已接通 `dashboard + inbox + workflow river + Board Gate`
  - `Inbox` 里的 review 项可直接打开 `Review Room`
  - UI 可直接提交 `project-init / board-approve / board-reject / modify-constraints`
  - 前端只拥有本地视图状态，真实工作流状态仍只来自后端投影与事件流
- `dashboard.pipeline_summary.phases` 现在不再是空数组，而是固定五段的高层治理读面：`Intake / Plan / Build / Check / Review`
  - 这层摘要由当前 workflow、node、approval 和 open incident 真相确定性汇总，只服务首页河道，不是完整 DAG 回放

这些能力足以支撑继续收敛到“本地单机 Agent Delivery OS MVP”。

## 已有但降级为后置能力的部分

仓库里已经落了一批更重的基础设施能力，包括：

- 多租户 worker scope 与 `worker-admin` 运维控制面
- 操作人令牌、可信代理断言、独立鉴权拒绝读面
- multipart artifact upload 与可选对象存储后端
- 更偏远程 worker handoff 的交付链路

这些实现不会被立刻删除，但它们不再代表当前阶段的主线，也不应继续吞掉主要开发预算。除非某项工作直接服务本地 MVP，否则默认后置。

## 当前最重要的未完成项

- 在已落地的核心 employee lifecycle（`hire / replace / freeze / restore`）之上，继续补完整 staffing 治理：当前 freeze 回收票恢复和 staffing containment incident 恢复已打通，但更多票型上的 staffing policy 还没补齐
- 在已覆盖 `ui_milestone_review@1` 与 `consensus_document@1` 的 Maker-Checker 之上，继续扩更多关键产物，并补完剩余返工治理
- 继续把 React Boardroom UI 从“最薄可用壳”推进到完整 MVP 读面
  - 当前已经接通 `dashboard / inbox / review room`，并在没有 active workflow 时提供最小 `project-init` 入口；这个入口现在会直接尝试推进到首个 scope review
  - 当前首页河道依赖 `dashboard.pipeline_summary.phases` 的固定五段高层摘要，不是完整 DAG 回放
  - 当前仍缺 `provider / model` 设置页、incident 详情、workforce 深入读面和 dependency inspector
  - 当前更明显的后续缺口，已经变成已批准 scope 的 follow-up 虽然都能落成真实视觉票，但下游票型仍先收口在现有 `ui_milestone_review@1` 链上，还没有更丰富的 build / check 票型

说明：真实 `prov_openai_compat` provider 适配层、当前 MVP 需要的大输入 / 媒体 / 下载型二进制展示语义，这一轮已经按本地单机口径收口；更远的 provider routing、多模型策略、浏览器直传和云预签名 multipart 继续后置。

更具体的执行项见 [doc/TODO.md](doc/TODO.md)。

## 快速开始

启动后端：

```bash
cd backend
source .venv/bin/activate
uvicorn app.main:app --reload
```

启动前端：

```bash
cd frontend
npm install
npm run dev
```

前端会通过 Vite dev proxy 直接连本地 FastAPI。当前默认 `project-init` 会尝试把 workflow 同步推进到首个 scope review；首个 scope review 通过后，后端还会继续把所有“当前支持范围内”的已批准 follow-up 往下推到下一个治理停点。如果本地没有可派单员工，或中途出现 incident，它会停在真实 pending / incident 状态，而不是假装链路已经走完。

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
- [doc/design/boardroom-ui-visual-concept.md](doc/design/boardroom-ui-visual-concept.md)：当前确认的首页视觉方向与独立设计稿
- [doc/design/boardroom-ui-visual-spec.md](doc/design/boardroom-ui-visual-spec.md)：前端实现时应遵循的详细视觉规范
- [frontend/README.md](frontend/README.md)：独立前端壳的运行方式、边界和当前已落地能力
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
