# Boardroom OS 开发推进提示词

> 版本：3.0
> 日期：2026-04-03
> 用途：每轮开发会话的系统提示词模板
> 使用方式：复制对应提示词内容，粘贴到任意 LLM 客户端（Codex App / VS Code Codex / Claude / ChatGPT 等）

---

## 文档结构说明

所有项目文档集中在 `doc/` 目录下：

| 文档 | 位置 | 用途 |
|------|------|------|
| 代码真相表 | `doc/mainline-truth.md` | 主链现实、runtime 支持矩阵、冻结边界 |
| 路线纠偏决议 | `doc/roadmap-reset.md` | 当前阶段范围边界 |
| 唯一待办 | `doc/TODO.md` | 主线待办 + 已完成概要 + 执行批次 |
| 任务清单 | `doc/task-backlog.md` | 112 项任务（工时、依赖、验收标准） |
| CTO 评审 | `doc/cto-assessment-report.md` | 诊断、差距分析、优先级建议 |
| 里程碑时间线 | `doc/milestone-timeline.md` | 13 周 9 里程碑 |
| 后端运行指南 | `doc/backend-runtime-guide.md` | Runtime / Worker 操作手册 |
| 产品规格 | `doc/feature-spec.md` | 57 条设计原则 |
| 设计文档 | `doc/design/*.md` | 事件总线、Context Compiler、UI 等 |
| 前端架构 | `doc/design/frontend-architecture-guide.md` | 目录结构、类型、状态管理、迁移计划 |
| 前端组件规格 | `doc/design/frontend-component-spec.md` | 组件 Props、HTML、视觉规则 |
| 工作记忆 | `doc/history/memory-log.md` | 长期记忆与近期进展 |
| 历史归档 | `doc/history/archive/` | 详细历史（按需查阅） |

---

## 工作流概览

每个批次的完整流程：

```
开工（选 A/B/C/D 之一）→ 实现 → 自动收尾（验证 + 文档 + 提交）
```

**提示词 A~D 已内置收尾流程**，做完代码后会自动执行验证、文档更新和 git 提交。
正常情况下你只需要贴一次提示词。

如果某轮只做了一半、或者需要单独补收尾，使用 **提示词 Z（单独收尾）**。

---

## 提示词 A：标准推进

```
继续推进 Boardroom OS，在现有代码上增量开发，不重建骨架。

上下文加载顺序：
1. README.md
2. doc/README.md → doc/mainline-truth.md → doc/roadmap-reset.md → doc/TODO.md → doc/history/memory-log.md
3. doc/milestone-timeline.md → doc/task-backlog.md
4. 按需读相关设计文档，不读无关文件
5. doc/history/archive/* 仅在需要精确历史原因时查看

推进规则：
- 以 doc/TODO.md 的优先级和执行批次为主线
- 以 doc/task-backlog.md 的任务清单为执行依据（含工时、依赖、验收标准）
- 以 doc/milestone-timeline.md 的里程碑顺序为参考时间线
- 优先完成当前批次中状态为「未开始」的最高优先级任务
- 同一闭环内的相邻环节可以连续推进，允许跨后端/前端一起做
- 不开多个无关方向，不顺手优化，不为假想需求铺扩展点
- 已降级代码（worker-admin/多租户/对象存储/远程handoff）视为冻结，不动

开始前输出：
1. 当前所处里程碑和进度判断（一句话）
2. 本轮要完成的具体任务 ID 列表（引用 doc/task-backlog.md）
3. 每个任务完成后的直接结果
4. 本轮明确不做的内容

然后直接开始实现，不停在计划阶段。

实现要求：
- 交付可运行代码 + 最小测试 + 必要文档更新
- 设计与代码不一致时，先说明差异，做最保守处理
- 不把 stub/placeholder 写成已完成

--- 收尾（代码完成后自动执行以下全部步骤）---

第一步：验证
- 运行后端测试：cd backend && pytest tests/ -q
- 运行前端构建：cd frontend && npm run build
- 运行前端测试：cd frontend && npm run test:run
- 如果任何一项失败，先修复再继续

第二步：文档更新
- doc/TODO.md — 标记已完成的任务，添加新发现的任务，每项标明与主线的关系
- doc/history/memory-log.md — 追加本轮进展到 Recent Memory，只记影响实现决策的事实
- doc/task-backlog.md — 标记已完成的任务 ID
- README.md — 仅当本轮改变了对外能力或运行方式时更新
- 只写真实现状，不预写未来能力

第三步：Git 提交
- git status 查看变更
- git diff 确认变更内容
- git add 相关文件（不要 add 敏感文件）
- git commit（提交信息用中文，格式：feat/fix/refactor/docs: 一句话描述）
- 如果有冲突或验证失败，说明卡点，不假装完成

第四步：汇报
1. 改了哪些文件
2. 落地了哪些能力
3. 哪些仍是 mock/stub
4. 测试结果（后端 passed 数 / 前端 build 状态 / 前端 passed 数）
5. 更新了哪些文档
6. git commit hash
7. 下一步最合理的任务 ID
8. 当前里程碑完成度

全程用通俗中文，先结论后细节，不堆术语。
```

---

## 提示词 B：前端专项推进

```
继续推进 Boardroom OS 前端重构，在现有代码上增量开发。

上下文加载顺序：
1. doc/design/frontend-architecture-guide.md（架构总纲）
2. doc/design/frontend-component-spec.md（组件规格）
3. doc/task-backlog.md（P0-FE-* 任务）
4. doc/design/boardroom-ui-visual-spec.md（视觉规范）
5. frontend/README.md
6. 按需读当前要改的组件源码

推进规则：
- 严格按 doc/task-backlog.md 中 P0-FE-* 的依赖顺序执行
- 每完成一个任务，立即运行 npm run build 和 npm run test:run 验证
- 功能必须与重构前完全一致，不加新功能
- 样式遵循 doc/design/frontend-architecture-guide.md 中的设计令牌和命名规范
- 组件 props 接口遵循 doc/design/frontend-component-spec.md

开始前输出：
1. 当前前端重构进度（已完成哪些 P0-FE-* 任务）
2. 本轮要完成的任务 ID 列表
3. 每个任务的验收标准

然后直接开始实现。

--- 收尾（代码完成后自动执行以下全部步骤）---

第一步：验证
- cd frontend && npm run build
- cd frontend && npm run test:run
- cd backend && pytest tests/ -q（确认没有跨端回归）
- 如果任何一项失败，先修复再继续

第二步：文档更新
- doc/TODO.md — 标记已完成的任务
- doc/history/memory-log.md — 追加本轮进展
- doc/task-backlog.md — 标记已完成的任务 ID
- 只写真实现状，不预写未来能力

第三步：Git 提交
- git add 相关文件 && git commit（中文，格式：refactor/feat: 一句话描述）

第四步：汇报
1. 完成的任务 ID
2. 新建/修改的文件列表
3. 测试结果（build 状态 / 前端 passed 数 / 后端 passed 数）
4. git commit hash
5. 下一个任务 ID
```

---

## 提示词 C：CEO Agent 专项推进

```
继续推进 Boardroom OS 的 CEO Agent 实现。

上下文加载顺序：
1. doc/task-backlog.md（P0-CEO-* 任务）
2. doc/milestone-timeline.md（M1 里程碑）
3. doc/design/message-bus-design.md（事件总线设计）
4. backend/app/core/workflow_auto_advance.py（当前硬编码逻辑，要被替换）
5. backend/app/core/runtime.py（当前执行逻辑）
6. backend/app/contracts/commands.py（命令契约）
7. backend/app/core/output_schemas.py（输出 schema）

推进规则：
- 严格按 P0-CEO-* 的依赖顺序执行
- CEO 输出的动作必须经过 Reducer 级别校验
- LLM 不可用时必须回退到当前硬编码逻辑
- 每个新文件都要有对应的单元测试
- 不修改已工作的 Ticket/Approval/Employee handler

开始前输出：
1. 当前 CEO 实现进度
2. 本轮要完成的任务 ID
3. 需要新建的文件列表
4. 需要修改的现有文件列表

然后直接开始实现。

--- 收尾（代码完成后自动执行以下全部步骤）---

第一步：验证
- cd backend && pytest tests/ -q
- cd frontend && npm run build（确认没有跨端回归）
- 如果任何一项失败，先修复再继续

第二步：文档更新
- doc/TODO.md — 标记已完成的任务
- doc/history/memory-log.md — 追加本轮进展
- doc/task-backlog.md — 标记已完成的任务 ID

第三步：Git 提交
- git add 相关文件 && git commit（中文，格式：feat: 一句话描述）

第四步：汇报
1. 完成的任务 ID 和落地能力
2. 测试结果（后端 passed 数）
3. git commit hash
4. 下一个任务 ID
```

---

## 提示词 D：Worker 执行专项推进

```
继续推进 Boardroom OS 的 Worker 真实执行能力。

上下文加载顺序：
1. doc/task-backlog.md（P0-WRK-* 任务）
2. doc/milestone-timeline.md（M2 里程碑）
3. backend/app/core/runtime.py（当前确定性 mock）
4. backend/app/core/provider_openai_compat.py（OpenAI 适配层）
5. backend/app/core/context_compiler.py（上下文编译器）
6. backend/app/core/output_schemas.py（输出 schema 注册表）

推进规则：
- 严格按 P0-WRK-* 的依赖顺序执行
- 确定性路径必须保留为回退
- 真实 LLM 输出必须经过 schema 校验 + 写集验证
- Provider 错误必须分类并记录为 incident 事件
- 每个新能力都要有 mock LLM 响应的单元测试

开始前输出：
1. 当前 Worker 执行进度
2. 本轮要完成的任务 ID
3. 当前支持的输出 schema 列表

然后直接开始实现。

--- 收尾（代码完成后自动执行以下全部步骤）---

第一步：验证
- cd backend && pytest tests/ -q
- cd frontend && npm run build（确认没有跨端回归）
- 如果任何一项失败，先修复再继续

第二步：文档更新
- doc/TODO.md — 标记已完成的任务
- doc/history/memory-log.md — 追加本轮进展
- doc/task-backlog.md — 标记已完成的任务 ID

第三步：Git 提交
- git add 相关文件 && git commit（中文，格式：feat: 一句话描述）

第四步：汇报
1. 完成的任务 ID 和落地能力
2. 测试结果（后端 passed 数）
3. git commit hash
4. 下一个任务 ID
```

---

## 提示词 Z：单独收尾

> 用于：本轮开发已经做完代码但还没收尾，或者上一轮中断了需要补收尾。
> 正常情况下不需要用这个——A/B/C/D 已经内置了收尾流程。

```
对 Boardroom OS 当前工作目录中的变更执行收尾流程。

先读取上下文：
1. doc/TODO.md
2. doc/history/memory-log.md
3. doc/task-backlog.md
4. git status 和 git diff 了解当前变更

然后按顺序执行以下全部步骤：

第一步：验证
- cd backend && pytest tests/ -q
- cd frontend && npm run build
- cd frontend && npm run test:run
- 如果任何一项失败，先修复再继续

第二步：文档更新
- doc/TODO.md — 根据本轮实际变更，标记已完成的任务，添加新发现的任务，每项标明与主线的关系
- doc/history/memory-log.md — 追加本轮进展到 Recent Memory，只记影响实现决策的事实
- doc/task-backlog.md — 标记已完成的任务 ID
- README.md — 仅当本轮改变了对外能力或运行方式时更新
- 只写真实现状，不预写未来能力

第三步：Git 提交
- git status 查看变更
- git diff 确认变更内容
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
| 专门做前端 | B | 前端重构 + 收尾 |
| 专门做 CEO Agent | C | CEO 实现 + 收尾 |
| 专门做 Worker 执行 | D | Worker 实现 + 收尾 |
| 补收尾（上轮中断/只做了代码） | Z | 单独跑验证 + 文档 + 提交 |

**正常流程：贴一次 A/B/C/D，等它做完就行。**
只有中断恢复时才需要 Z。
