# Boardroom OS

> 一个本地优先、事件溯源、用无状态 Agent Team 推进交付的控制面原型。

## 当前是什么

Boardroom OS 当前阶段固定为“本地单机 Agent Delivery OS MVP”：

- 用户像董事会，只给目标、约束和验收标准
- 后端按 `Board -> Worker -> Review` 的治理链推进工作
- 事件流和投影是真相源，前端只读当前治理状态
- Maker-Checker、Review Room 和最小 Meeting Room 都是主线治理，不是演示壳

路线边界见 [doc/roadmap-reset.md](doc/roadmap-reset.md)。

## 当前真实闭环

- `project-init -> scope review -> BUILD -> CHECK -> REVIEW -> closeout` 已真实跑通
- 当初始化输入明显不足，或董事会在启动时显式要求先澄清时，`project-init` 会先打开一次 `REQUIREMENT_ELICITATION` 板审，再继续进入首个 scope review
- `BUILD`、`CHECK`、`closeout` 都带内部 maker-checker；最终董事会只看真正的 board-facing `REVIEW`
- CEO 已真实执行 `CREATE_TICKET / RETRY_TICKET / HIRE_EMPLOYEE / REQUEST_MEETING`
- `ESCALATE_TO_BOARD` 仍是 `DEFERRED_SHADOW_ONLY`
- CEO 现在也可在当前 live 规划角色上先创建五类治理文档票；治理文档结果会写回统一 `GOVERNANCE_DOCUMENT` 过程资产，并可自动带入后续实施票
- runtime provider 设置现在已升级为最小 registry：首版真实支持 `OpenAI Compat` 与 `Claude Code CLI`，并可给当前真实角色保存默认 provider / model 绑定、能力标签、健康明细和最小 fallback provider 链
- `workforce` 与 runtime provider 设置现在都会暴露统一只读 `role_templates_catalog`：固定包含当前 live 执行角色、未来执行角色预留、治理角色预留、文档类型和模板片段；其中 `backend / database / platform / architect / cto` 现在已进入 Board/workforce staffing 主链，但仍未进入 CEO preset 或 runtime live 路径
- React 壳当前可看 `dashboard / inbox / review room / meeting room / incident / workforce / dependency inspector / completion`

更细代码真相统一看 [doc/mainline-truth.md](doc/mainline-truth.md)。

## 当前主线边界

- 本地单机优先，不按公网多租户平台推进
- Ticket 驱动无状态执行器，不按聊天式 Agent shell 推进
- Context Compiler 负责受控执行包，不给 Worker 任意全局记忆
- Web UI 继续做最薄治理壳，不接管工作流真相

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

## 默认先读

1. [doc/README.md](doc/README.md)
2. [doc/mainline-truth.md](doc/mainline-truth.md)
3. [doc/roadmap-reset.md](doc/roadmap-reset.md)
4. [doc/TODO.md](doc/TODO.md)
5. [doc/history/context-baseline.md](doc/history/context-baseline.md)
6. [doc/history/memory-log.md](doc/history/memory-log.md)
7. [doc/task-backlog.md](doc/task-backlog.md)

## 当前不主动扩张

- `worker-admin` 与更细的多租户运维面
- 对象存储平台化与上传链路扩张
- 远程 handoff / 远程控制面
- 在没有明确证据前继续扩检索层、Provider 路由和发布复杂度
- 任何不直接缩短本地 MVP 路径的远期愿景系统化能力

## 项目原则

- 治理比热闹重要
- 审计比想象重要
- 幂等比炫技重要
- 结构化协作比自由群聊可靠
- 本地可跑通，比过早远程化更重要
