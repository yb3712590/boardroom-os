# Boardroom OS

一个让 AI Agent 团队自主交付项目的本地操作系统。

你定义目标和验收标准，系统负责拆解、执行、审查、返工和交付。不是又一个 AI 编程助手——是一支能跑完整个交付流程的 Agent 团队。

## 为什么不一样

**多角色治理，不是单 Agent 对话。** 系统内设 CEO（调度拆解）、Executor（执行）、Checker（审查）、Board（决策）四类角色，各司其职。Executor 和 Checker 刻意选用互补思维风格，减少盲区。

**跑完全流程，不是生成片段。** 从需求细化 → 任务分解 → 执行 → 验证 → 评审 → 交付，完整闭环。不需要你在中间反复介入拼接。

**Ticket 驱动，无状态执行。** 工作单元是结构化 Ticket，不是聊天记录。Worker 无状态消费任务，CEO 读取快照做调度——没有隐式上下文依赖，每一步可追溯、可重放。

## 核心设计

| 机制 | 做什么 | 完成进度 |
|------|--------|----------|
| Event Sourcing | 全量事件流 + 状态投影，替代自由对话作为协作基底 | 已落地 |
| Maker-Checker | 执行和审查分离，审查不通过自动生成修复 Ticket | 已落地 |
| Git Worktree | 每个代码任务独立 worktree，合并经过门禁审查 | 已落代码链 |
| 三层上下文 | L1 当前工作区 / L2 按需检索(RAG) / L3 持久存储，防止上下文爆炸 | L1 已落，L2/L3 逐步补齐 |
| Circuit Breaker | 重复失败、预算耗尽自动熔断上报，不做无限重试 | 基础版已落 |
| 证据包 | 交付物附带测试结果、diff、审查结论、截图、已知风险 | 基础版已落，持续补齐 |

## 人只管关键决策

系统默认自主推进。只有这些情况会请求你介入：

- 多个高成本视觉方向需要抉择
- 需求、预算、合规边界存在冲突
- 所需权限或外部依赖无法获取

UI 提供 Dashboard、Inbox、Review Room，看的是状态投影和审批队列，不是聊天记录。

## 技术栈

- **后端** FastAPI + Pydantic + SQLite(WAL) + pytest
- **前端** React + Vite + TypeScript + Vitest
- **模型** 支持 OpenAI 兼容端点，按角色绑定模型，高成本模型留给低频高杠杆角色

## 快速开始

```bash
git clone https://github.com/yb3712590/boardroom-os.git
cd boardroom-os
# 后端
cd backend && pip install -r requirements.txt && uvicorn main:app
# 前端
cd frontend && npm install && npm run dev
```

## 状态

本地 MVP 可用。当前重心：先把交付流程跑通跑稳，再谈平台化。

## License

MIT
