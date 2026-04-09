# Boardroom OS

> 像带着一个会自己往前推进的 AI 团队做项目：你给目标、约束和验收标准，系统负责拆解、执行、检查、返工和交付整理；只有关键节点才回来请你拍板。

## 这是什么

Boardroom OS 是一个面向真实交付的 Agent Delivery OS 原型。

它不是让你和一个 AI 一直来回聊天，而是想把 AI 组织成一个能持续推进、能自我检查、也能把关键决定交还给人的小团队。

如果用更直白的话说，它想同时做到两件事：

- 有 `vibe coding` 的顺手感：不用你盯着每一步，系统会自己继续往前推
- 有 `harness engineering` 的稳定感：每一步都有边界、有记录、有检查，不靠“这次刚好运气好”

## 它和普通 AI 编程工具有什么不同

很多 AI 工具擅长“陪你一起做”，但不一定擅长“自己把事情做完”。

Boardroom OS 更在意的是交付闭环：

- 不是把所有问题都抛回给你，而是默认先基于合理假设继续推进
- 不是只让一个 Agent 从头聊到尾，而是把 CEO、执行者、检查者和董事会分开治理
- 不是代码生成完就算结束，而是继续做检查、返工、复核和收口
- 不是只看模型会不会写，而是关心过程是否可追踪、结果是否可复核、交付是否能落地

## 核心竞争力

### ✅ 已实现

- 已经能在本地跑通一条真实交付闭环：项目启动、需求补充、执行、检查、董事会评审、closeout
- 默认“继续推进”，只有碰到真正需要拍板的节点才升级给董事会
- 不靠长对话记忆接力，而是靠事件、状态、Ticket 和 Artifact 协作，过程可追踪、可回看
- `maker-checker` 已经落地，执行和审查分开，减少“自己写、自己评、自己过”的失真
- 视觉结果已经被当成单独治理对象，董事会可以在 `Inbox` 和 `Review Room` 集中做决定
- 前端已经提供 `Dashboard`、`Inbox`、`Review Room`、`Meeting Room`、`Workforce`、`Provider Settings` 等主界面
- `Provider Settings` 现在已是多 provider 配置中心：可录入多个 OpenAI-compatible Responses provider、测试连通性、拉取模型列表，并按 `provider + model` 组合给 CEO 和 role 绑定优先级
- 运行时已支持本地 deterministic 路径；当前 provider center 真实执行 OpenAI-compatible Responses，`Claude Code CLI` 兼容执行路径仍保留，但不在这套新配置流程里开放录入
- 团队组织不是写死的，系统已经支持招聘、冻结、恢复、替换员工

### 🟡 正在补齐

- 让后端、数据库、平台等更多角色拿到更直接的正式派工入口
- 把技术决策、治理文档和高级角色能力接进更完整的正式主线
- 把证据包、文档同步、交接材料做得更完整，让复核、留档和交接更省心
- 把过程资产、项目地图、组织学习这些长期能力做成系统级能力
- 继续清理与当前 MVP 无关的旧能力和兼容壳，让主线更轻、更稳、更清楚

## 当前已经做到哪一步

- 本地单机版本已经可以真实跑通，不再只是概念演示
- 当输入还不够清楚时，系统会先触发受控澄清，再继续推进主线
- 系统里的 CEO 已经能创建任务、重试任务、招人、换人、冻结成员、恢复成员和发起会议
- 检查和复核已经进入日常流程，不靠一次性产出直接交差
- 董事会可以在 `Inbox` 和 `Review Room` 里集中审批，不需要被零散流程反复打断
- 后端保存事件和状态，前端负责把当前情况讲清楚，真实流程以后端投影为准

更多当前代码真相见 [doc/mainline-truth.md](doc/mainline-truth.md)。

## 当前边界

- 当前重点仍是本地单机 MVP
- 多租户公网平台、远程运维控制面、对象存储平台化都不是当前重点
- 前端负责展示和操作，真实流程以后端事件和投影为准
- 一切优先级都围绕一件事展开：缩短从董事会指令到交付复核的路径

## 技术栈

- Backend: `FastAPI`、`Pydantic`、`pytest`
- Frontend: `React`、`Vite`、`TypeScript`、`Vitest`

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

运行后端验证：

```bash
cd backend
./.venv/bin/pytest tests/ -q
```

运行后端 live 集成场景：

```bash
cd backend
export BOARDROOM_OS_PROVIDER_OPENAI_COMPAT_BASE_URL="https://<your-openai-compatible-base-url>/v1"
export BOARDROOM_OS_PROVIDER_OPENAI_COMPAT_API_KEY="<your-api-key>"
python -m tests.live.library_management_autopilot_live
```

这条 live 场景不会进默认 `pytest`。

它会把独立运行环境、artifact、provider 配置、developer inspector、每票 markdown 上下文留档和 `run_report.json` 全部收进：

- `backend/data/scenarios/library_management_autopilot_live/`

运行前端验证：

```bash
cd frontend
npm run build
npm run test:run
```

## 建议先读

1. [doc/README.md](doc/README.md)
2. [doc/mainline-truth.md](doc/mainline-truth.md)
3. [doc/backend-runtime-guide.md](doc/backend-runtime-guide.md)
4. [doc/roadmap-reset.md](doc/roadmap-reset.md)
5. [doc/TODO.md](doc/TODO.md)
6. [doc/history/context-baseline.md](doc/history/context-baseline.md)
7. [doc/task-backlog.md](doc/task-backlog.md)

## 项目原则

- 先把真实交付跑通，再谈远期扩张
- 先把关键决策和责任分清，再谈更炫的自动化
- 先把记录留完整，再谈更复杂的能力拼装
- 先让本地版本稳定可用，再谈远程化和平台化
