# Boardroom OS

> 一个本地优先、事件溯源、用无状态 Agent Team 推进交付的控制面原型。

## 当前是什么

Boardroom OS 当前阶段不是公网多租户平台，而是一个本地单机 Agent Delivery OS MVP：

- 用户像董事会，只给目标、约束和验收标准
- 后端按 `Board -> Worker -> Review` 的治理链推进工作
- 事件流和投影是真相源，前端只读现有治理状态
- `Inbox -> Review Room` 和 Maker-Checker 是真实闭环，不是演示页面

路线纠偏决议见 [doc/roadmap-reset.md](doc/roadmap-reset.md)。

## 当前真实闭环

默认本地小项目已经能跑通这条链：

`project-init -> scope review -> BUILD 内部 maker-checker -> CHECK -> final REVIEW -> closeout 内部 maker-checker`

当前这条链的现实状态：

- `project-init` 会先由 CEO 发起首个 kickoff scope 共识票，再自动推进到首个 scope review
- scope 通过后，`BUILD` 会先产出 `implementation_bundle@1`，再走内部 `maker -> checker -> fix / incident`
- `CHECK` 产出的 `delivery_check_report@1` 现在也会先走内部 `maker -> checker -> fix / incident`
- 只有 build 和 check 两段内审都通过后，系统才会放行最终董事会 `REVIEW`
- 最终董事会只在真正的 board-facing `REVIEW` 进入 `Inbox -> Review Room`
- 最终董事会通过后，系统会自动补一张 `delivery_closeout_package@1` 收口票，再走内部 `maker -> checker -> fix / incident`
- React 壳已经能看 `dashboard / inbox / review room / incident / workforce / dependency inspector / completion`，并且能在 `workforce` 上直接做最小 staffing 解堵：`freeze / restore / hire request / replace request`

## 仓库里现在有的主线能力

- FastAPI + SQLite 后端，事件流、投影、ticket 生命周期、approval / incident / breaker 都已可用
- Maker-Checker 已覆盖 `consensus_document@1`、`implementation_bundle@1`、`delivery_check_report@1`、`ui_milestone_review@1`、`delivery_closeout_package@1`
- employee 生命周期已进入主线：`hire / replace / freeze / restore` 与 staffing containment 都是事件驱动，且当前已带最小人格模型（`skill / personality / aesthetic` 三组画像）与同岗高重合招聘约束
- CEO 已从纯影子进入有限接管首轮：当前会真实执行 `CREATE_TICKET / RETRY_TICKET / HIRE_EMPLOYEE`，其中 `project-init` 后的首个 scope kickoff 票已由 CEO 发起；scheduler 也会在 workflow 空转但仍有待推进信号时补打一轮 CEO idle maintenance 审计；`ESCALATE_TO_BOARD` 仍保持 shadow-only
- Context Compiler 已能处理常见文本、媒体、下载型附件和本地历史摘要，并产出可审计执行包；当前 worker 执行包会显式携带标准化员工画像与 `persona_summary`
- runtime 默认走本地 deterministic；也支持本地保存的 `OpenAI Compat` provider 配置，并会在 provider 暂停、限流、超时或坏响应时按现有 incident 规则留痕后自动回退到 deterministic
- React 壳里的 `workforce` 与 staffing `Review Room` 现在都能直接看到当前员工/候选员工画像，不需要翻事件或数据库

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

运行测试：

```bash
cd backend
source .venv/bin/activate
python -m pytest tests -q
```

补充说明：

- 前端通过 Vite dev proxy 直连本地 FastAPI
- runtime provider 配置默认保存在 `backend/data/runtime-provider-config.json`
- scope 通过后，如果没有可派单员工或途中出现 incident，链路会停在真实 `pending / incident`，不会伪造完成
- completion card 现在只会在最终 review 之后的 closeout 内审也收口后出现

## 建议先读

- [doc/mainline-truth.md](doc/mainline-truth.md)：当前代码真相表，先看主链现实、runtime 支持矩阵和冻结边界
- [doc/roadmap-reset.md](doc/roadmap-reset.md)：当前阶段边界和判断规则
- [doc/TODO.md](doc/TODO.md)：当前主线待办
- [doc/history/memory-log.md](doc/history/memory-log.md)：压缩后的长期记忆和最近进展
- [doc/backend-runtime-guide.md](doc/backend-runtime-guide.md)：后端运行方式
- [frontend/README.md](frontend/README.md)：前端壳的边界和运行方式

## 当前不优先

这些能力还保留在仓库里，但默认冻结，除非直接解堵本地 MVP：

- `auth / worker-admin`
- 多租户 scope
- 对象存储和上传平台化
- 远程 handoff / 远程控制面
- Search / Retrieval 扩张

## 项目原则

- 治理比热闹重要
- 审计比想象重要
- 幂等比炫技重要
- 结构化协作比自由群聊可靠
- 本地可跑通，比过早远程化更重要
