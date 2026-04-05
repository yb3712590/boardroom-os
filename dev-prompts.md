# Boardroom OS 开发推进提示词

> 版本：4.0
> 日期：2026-04-05
> 用途：每轮开发会话的系统提示词模板
> 使用方式：复制对应提示词内容，粘贴到任意 LLM 客户端（Codex App / VS Code Codex / Claude / ChatGPT 等）

---

## 文档结构说明

所有项目文档集中在 `doc/` 目录下，但现在按“入口摘要 -> 详细页 / 归档页”分层：

| 文档 | 位置 | 用途 |
|------|------|------|
| 代码真相表 | `doc/mainline-truth.md` | 主链现实、runtime 支持矩阵、冻结边界 |
| 路线纠偏决议 | `doc/roadmap-reset.md` | 当前阶段范围边界和判断规则 |
| 唯一待办 | `doc/TODO.md` | 当前主线待办 |
| 稳定基线 | `doc/history/context-baseline.md` | 产品模型、治理规则、架构基线 |
| 工作记忆 | `doc/history/memory-log.md` | 最近几天的关键进展 |
| 任务库入口 | `doc/task-backlog.md` | 任务总览、活跃区域索引 |
| 活跃任务 | `doc/task-backlog/active.md` | 当前未关闭任务明细 |
| 历史任务快照 | `doc/task-backlog/done.md` | 已完成任务卡片、工时、依赖、验收标准、完成补记 |
| 里程碑时间线 | `doc/milestone-timeline.md` | 中长期里程碑排程 |
| 后端运行指南 | `doc/backend-runtime-guide.md` | Runtime / Worker 操作手册 |
| 产品规格 | `doc/feature-spec.md` | 长期设计原则 |
| 设计文档 | `doc/design/*.md` | 事件总线、Context Compiler、UI 等 |
| 历史归档 | `doc/history/archive/` | 详细历史（按需查阅） |

---

## 工作流概览

每个批次的完整流程：

```text
开工（选 A/B/C/D 之一）→ 实现 → 自动收尾（验证 + 文档 + 提交）
```

**提示词 A~D 已内置收尾流程**，做完代码后会自动执行验证、文档更新和 git 提交。
正常情况下你只需要贴一次提示词。

如果某轮只做了一半、或者需要单独补收尾，使用 **提示词 Z（单独收尾）**。

---

## 提示词 A：标准推进

```md
继续推进 Boardroom OS，在现有代码上增量开发，不重建骨架。

上下文加载顺序：
1. README.md
2. doc/README.md → doc/mainline-truth.md → doc/roadmap-reset.md → doc/TODO.md
3. doc/history/context-baseline.md → doc/history/memory-log.md
4. 需要任务 ID、状态和详细约束时，再读 doc/task-backlog.md → doc/task-backlog/active.md
5. 需要周级排程时再读 doc/milestone-timeline.md
6. 按需读相关设计文档，不读无关文件
7. doc/history/archive/* 仅在需要精确历史原因时查看

推进规则：
- 以 doc/TODO.md 的优先级和执行批次为主线
- 以 doc/task-backlog/active.md 的任务清单为执行依据；需要历史卡片时再查 doc/task-backlog/done.md
- 以 doc/milestone-timeline.md 的里程碑顺序为参考时间线，而不是当前真相源
- 优先完成当前批次中状态为“未开始”的最高优先级任务
- 同一闭环内的相邻环节可以连续推进，允许跨后端/前端一起做
- 不开多个无关方向，不顺手优化，不为假想需求铺扩展点
- 已降级代码（worker-admin / 多租户 / 对象存储 / 远程 handoff）视为冻结，不动

开始前输出：
1. 当前所处主线状态和进度判断（一句话）
2. 本轮要完成的具体任务 ID 列表（引用 doc/task-backlog/active.md）
3. 每个任务完成后的直接结果
4. 本轮明确不做的内容

然后直接开始实现，不停在计划阶段。

实现要求：
- 交付可运行代码 + 最小测试 + 必要文档更新
- 设计与代码不一致时，先说明差异，做最保守处理
- 不把 stub / placeholder 写成已完成

--- 收尾（代码完成后自动执行以下全部步骤）---

第一步：验证
- 运行后端测试：cd backend && pytest tests/ -q
- 运行前端构建：cd frontend && npm run build
- 运行前端测试：cd frontend && npm run test:run
- 如果任何一项失败，先修复再继续

第二步：文档更新
- doc/TODO.md — 标记已完成的任务，添加新发现的任务，每项标明与主线的关系
- doc/history/memory-log.md — 追加本轮进展到 Recent Memory，只记影响实现决策的事实
- doc/task-backlog.md / doc/task-backlog/active.md / doc/task-backlog/done.md — 同步状态索引和对应详细补记
- README.md — 仅当本轮改变了对外能力或运行方式时更新
- 只写真实现状，不预写未来能力

第三步：Git 提交
- git status 查看变更
- git diff --stat 先看概览；只对需要确认的单文件再看详细 diff
- git add 相关文件（不要 add 敏感文件）
- git commit（提交信息用中文，格式：feat/fix/refactor/docs: 一句话描述）
- 如果有冲突或验证失败，说明卡点，不假装完成

第四步：汇报
1. 改了哪些文件
2. 落地了哪些能力
3. 哪些仍是 mock / stub
4. 测试结果（后端 passed 数 / 前端 build 状态 / 前端 passed 数）
5. 更新了哪些文档
6. git commit hash
7. 下一步最合理的任务 ID
8. 当前里程碑完成度
```

---

## 提示词 B：前端专项推进

```md
继续推进 Boardroom OS 前端壳，在现有代码上增量开发。

上下文加载顺序：
1. doc/design/frontend-architecture-guide.md（先看 TL;DR）
2. doc/design/frontend-component-spec.md（先看 TL;DR）
3. doc/task-backlog.md（先看索引；需要历史 P0-FE 细节时再看 doc/task-backlog/done.md）
4. doc/design/boardroom-ui-visual-spec.md
5. frontend/README.md
6. 按需读当前要改的组件源码

推进规则：
- 严格按任务依赖顺序执行，不为视觉打磨重开已关闭的大方向
- 每完成一个批次，立即运行 npm run build 和 npm run test:run 验证
- 功能必须与重构后当前行为一致，不凭感觉加新功能
- 样式遵循前端架构指南中的设计令牌和命名规范
- 组件 props 接口遵循组件规格说明

收尾时同步更新：doc/TODO.md、doc/history/memory-log.md，以及 task-backlog 对应入口 / 详细页。
```

---

## 提示词 C：CEO Agent 专项推进

```md
继续推进 Boardroom OS 的 CEO Agent。

上下文加载顺序：
1. doc/task-backlog.md（先看索引；需要 CEO 历史任务细节时再看 doc/task-backlog/done.md）
2. doc/TODO.md
3. doc/milestone-timeline.md（只用来判断长期排程）
4. doc/design/message-bus-design.md（先看 TL;DR）
5. backend/app/core/workflow_auto_advance.py
6. backend/app/core/runtime.py
7. backend/app/contracts/commands.py
8. backend/app/core/output_schemas.py

推进规则：
- CEO 输出动作必须经过 Reducer 级校验
- LLM 不可用时必须回退到当前确定性路径
- 不修改已工作的 Ticket / Approval / Employee handler，除非明确属于当前切片
- 收尾时同步更新：doc/TODO.md、doc/history/memory-log.md，以及 task-backlog 对应入口 / 详细页
```

---

## 提示词 D：Worker 执行专项推进

```md
继续推进 Boardroom OS 的 Worker 真实执行能力。

上下文加载顺序：
1. doc/task-backlog.md（先看索引；需要 Worker 历史任务细节时再看 doc/task-backlog/done.md）
2. doc/TODO.md
3. doc/milestone-timeline.md（只用来判断长期排程）
4. backend/app/core/runtime.py
5. backend/app/core/provider_openai_compat.py
6. backend/app/core/context_compiler.py（需要时先看设计文档 TL;DR）
7. backend/app/core/output_schemas.py

推进规则：
- 确定性路径必须保留为回退
- 真实 LLM 输出必须经过 schema 校验 + 写集验证
- Provider 错误必须分类并记录为 incident 事件
- 每个新能力都要有 mock LLM 响应的单元测试
- 收尾时同步更新：doc/TODO.md、doc/history/memory-log.md，以及 task-backlog 对应入口 / 详细页
```

---

## 提示词 Z：单独收尾

> 用于：本轮开发已经做完代码但还没收尾，或者上一轮中断了需要补收尾。
> 正常情况下不需要用这个，A/B/C/D 已经内置了收尾流程。

```md
对 Boardroom OS 当前工作目录中的变更执行收尾流程。

先读取上下文：
1. doc/TODO.md
2. doc/history/context-baseline.md
3. doc/history/memory-log.md
4. doc/task-backlog.md → doc/task-backlog/active.md
5. git status 和 git diff --stat 了解当前变更

然后按顺序执行以下全部步骤：

第一步：验证
- cd backend && pytest tests/ -q
- cd frontend && npm run build
- cd frontend && npm run test:run
- 如果任何一项失败，先修复再继续

第二步：文档更新
- doc/TODO.md — 根据本轮实际变更，标记已完成的任务，添加新发现的任务，每项标明与主线的关系
- doc/history/memory-log.md — 追加本轮进展到 Recent Memory，只记影响实现决策的事实
- doc/task-backlog.md / doc/task-backlog/active.md / doc/task-backlog/done.md — 同步状态索引和对应详细补记
- README.md — 仅当本轮改变了对外能力或运行方式时更新
- 只写真实现状，不预写未来能力

第三步：Git 提交
- git status 查看变更
- git diff --stat 先看概览；只对需要确认的单文件再看详细 diff
- git add 相关文件（不要 add 敏感文件）
- git commit（提交信息用中文，格式：feat/fix/refactor/docs: 一句话描述）
- 如果有冲突或验证失败，说明卡点，不假装完成

第四步：汇报
1. 改了哪些文件
2. 落地了哪些能力
3. 测试结果（后端 passed 数 / 前端 build 状态 / 前端 passed 数）
4. 更新了哪些文档
5. git commit hash
6. 下一步最合理的任务 ID
```

---

## 使用指南

| 场景 | 贴哪个 | 说明 |
|------|--------|------|
| 日常推进 | A | 自动选任务 + 实现 + 收尾，一次搞定 |
| 专门做前端 | B | 前端壳推进 + 收尾 |
| 专门做 CEO Agent | C | CEO 实现 + 收尾 |
| 专门做 Worker 执行 | D | Worker 执行 + 收尾 |
| 只补收尾 | Z | 验证 + 文档 + 提交 |
