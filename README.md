# Boardroom OS

> 给团队一个目标、几条约束和验收标准，系统继续往下推进；需要拍板的时候，再回到董事会面前。

## 这是什么

很多团队都有同一个难题。
负责人能说清方向，也能说清底线，但很难一直盯着拆解、执行、检查、返工和收口。

Boardroom OS 就是为这类场景准备的。
它把交付过程接过去，把任务分下去，把结果收回来，把关键决定留给真正该拍板的人。

现在的版本重点很明确：先把本地可运行、可验证、可演示的交付闭环做扎实。

## 核心竞争力

### ✅ done

- 已经能把项目启动、需求补充、执行、检查、最终复核串成一条真实闭环
- 负责人只在关键节点介入，平时不用盯着每一步
- 执行、检查、复核已经拆开，减少“自己做、自己评、自己过”的失真
- 每一步都有结构化记录，进度、决策和结果都能回看
- 本地就能跑通主流程，不需要先搭一整套云端平台
- 前端已经能看到仪表盘、收件箱、评审、会议、人员、依赖和交付结果
- 多种角色和模型提供方已经接进主流程，团队编制和执行入口开始成形

### 🟡 todo

- 让更多角色直接进入正式执行入口，减少“已经接入但还不能直接派活”的情况
- 把更多董事会升级动作做成正式能力，让高风险决策有更完整的处理面
- 把证据包、文档更新和交付展示补得更完整，方便复核、留档和交接
- 继续清理与当前 MVP 无关的旧能力和复杂边角，让系统更轻、更稳、更聚焦

## 当前做到哪一步

- 本地单机版本已经可以真实跑通，不再停留在概念演示
- 当输入过于模糊时，系统会先把缺的信息补齐，再继续推进
- 系统里的 CEO 已经能创建任务、重试任务、招人和发起会议
- 检查和复核已经进入日常流程，不靠一次性产出直接交差
- 董事会可以在 `Inbox` 和 `Review Room` 里集中做决定
- 后端保存事件和状态，前端负责把当前情况清楚地展示出来

更多当前真相见 [doc/mainline-truth.md](doc/mainline-truth.md)。

## 当前边界

- 当前重点仍在本地单机版本
- 多租户公网平台、远程运维控制面、对象存储平台化都先不扩张
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

运行前端验证：

```bash
cd frontend
npm run build
npm run test:run
```

## 推荐先读

1. [doc/README.md](doc/README.md)
2. [doc/mainline-truth.md](doc/mainline-truth.md)
3. [doc/roadmap-reset.md](doc/roadmap-reset.md)
4. [doc/TODO.md](doc/TODO.md)
5. [doc/history/context-baseline.md](doc/history/context-baseline.md)
6. [doc/task-backlog.md](doc/task-backlog.md)

## 项目原则

- 先把真实交付跑通，再谈远期扩张
- 先把关键决策和责任分清，再谈更炫的自动化
- 先把记录留完整，再谈更复杂的能力拼装
- 先让本地版本稳定可用，再谈远程化和平台化
