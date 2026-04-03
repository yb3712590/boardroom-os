# Boardroom OS 开发推进提示词

> 版本：1.0
> 日期：2026-04-03
> 用途：每轮开发会话的系统提示词模板

---

## 提示词 A：标准推进（每轮使用）

```
继续推进 Boardroom OS，在现有代码上增量开发，不重建骨架。

上下文加载顺序：
1. README.md
2. doc/README.md → doc/roadmap-reset.md → doc/TODO.md → doc/history/memory-log.md
3. CTO/milestone-timeline.md → CTO/detailed-todo.md
4. 按需读相关设计文档，不读无关文件
5. doc/history/archive/* 仅在需要精确历史原因时查看

推进规则：
- 以 CTO/milestone-timeline.md 的里程碑顺序为主线，以 CTO/detailed-todo.md 的任务清单为执行依据
- 优先完成当前里程碑中状态为「未开始」的最高优先级任务
- 同一闭环内的相邻环节可以连续推进，允许跨后端/前端一起做
- 不开多个无关方向，不顺手优化，不为假想需求铺扩展点
- 已降级代码（worker-admin/多租户/对象存储/远程handoff）视为冻结，不动

开始前输出：
1. 当前所处里程碑和进度判断（一句话）
2. 本轮要完成的具体任务 ID 列表（引用 CTO/detailed-todo.md）
3. 每个任务完成后的直接结果
4. 本轮明确不做的内容

然后直接开始实现，不停在计划阶段。

实现要求：
- 交付可运行代码 + 最小测试 + 必要文档更新
- 设计与代码不一致时，先说明差异，做最保守处理
- 不把 stub/placeholder 写成已完成

完成后汇报：
1. 改了哪些文件
2. 落地了哪些能力
3. 哪些仍是 mock/stub
4. 做了哪些测试，哪些因环境限制没做
5. 更新了哪些文档（README / TODO / memory-log）
6. 下一步最合理的任务 ID
7. 当前里程碑完成度

全程用通俗中文，先结论后细节，不堆术语。
```

---

## 提示词 B：前端专项推进

```
继续推进 Boardroom OS 前端重构，在现有代码上增量开发。

上下文加载顺序：
1. CTO/frontend-architecture-guide.md（架构总纲）
2. CTO/frontend-component-spec.md（组件规格）
3. CTO/detailed-todo.md（P0-FE-* 任务）
4. doc/design/boardroom-ui-visual-spec.md（视觉规范）
5. frontend/README.md
6. 按需读当前要改的组件源码

推进规则：
- 严格按 CTO/detailed-todo.md 中 P0-FE-* 的依赖顺序执行
- 每完成一个任务，立即运行 npm run build 和 npm run test:run 验证
- 功能必须与重构前完全一致，不加新功能
- 样式遵循 CTO/frontend-architecture-guide.md 中的设计令牌和命名规范
- 组件 props 接口遵循 CTO/frontend-component-spec.md

开始前输出：
1. 当前前端重构进度（已完成哪些 P0-FE-* 任务）
2. 本轮要完成的任务 ID 列表
3. 每个任务的验收标准

然后直接开始实现。

完成后汇报：
1. 完成的任务 ID
2. 新建/修改的文件列表
3. npm run build 结果
4. npm run test:run 结果
5. 下一个任务 ID
```

---

## 提示词 C：CEO Agent 专项推进

```
继续推进 Boardroom OS 的 CEO Agent 实现。

上下文加载顺序：
1. CTO/detailed-todo.md（P0-CEO-* 任务）
2. CTO/milestone-timeline.md（M1 里程碑）
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

完成后运行 pytest tests/ -q 验证无回归，然后汇报。
```

---

## 提示词 D：Worker 执行专项推进

```
继续推进 Boardroom OS 的 Worker 真实执行能力。

上下文加载顺序：
1. CTO/detailed-todo.md（P0-WRK-* 任务）
2. CTO/milestone-timeline.md（M2 里程碑）
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

完成后运行 pytest tests/ -q 验证无回归，然后汇报。
```

---

## 提示词 E：集成验证

```
对 Boardroom OS 进行端到端集成验证。

上下文加载顺序：
1. CTO/milestone-timeline.md（当前里程碑的成功标准）
2. CTO/detailed-todo.md（P0-INT-* 任务）
3. doc/TODO.md
4. doc/history/memory-log.md

验证步骤：
1. 启动后端：cd backend && source .venv/bin/activate && uvicorn app.main:app
2. 启动前端：cd frontend && npm run dev
3. 运行后端测试：cd backend && pytest tests/ -q
4. 运行前端测试：cd frontend && npm run test:run
5. 运行前端构建：cd frontend && npm run build
6. 手动验证核心链路：project-init → 查看 dashboard → 查看 inbox → 打开 review room

汇报：
1. 每项验证的通过/失败状态
2. 失败项的具体错误信息
3. 当前里程碑的成功标准达成情况
4. 需要修复的问题列表（引用 CTO/detailed-todo.md 任务 ID）
```

---

## 提示词 F：文档收尾

```
对 Boardroom OS 进行本轮文档收尾。

需要更新的文档：
1. doc/TODO.md — 标记已完成的任务，添加新发现的任务
2. doc/history/memory-log.md — 追加本轮进展到 Recent Memory
3. README.md — 如果本轮改变了对外能力或运行方式
4. CTO/detailed-todo.md — 标记已完成的任务 ID

规则：
- 只写真实现状，不预写未来能力
- README 保持简洁，细节下沉到对应文档
- TODO 每项标明与主线的关系
- memory-log 只记影响实现决策的事实

完成后列出更新了哪些文档，每个文档改了什么。
```

---

## 提示词 G：Git 收尾

```
本轮开发已完成并验证通过，执行 git 收尾。

步骤：
1. git status 查看变更
2. git diff 确认变更内容
3. git add 相关文件
4. git commit（提交信息用中文，格式：feat/fix/refactor/docs: 一句话描述）
5. 如果在分支上，合并到 main
6. git push
7. 清理本地分支

如果有冲突、权限或验证失败，说明卡点，不假装完成。
```

---

## 使用指南

| 场景 | 使用的提示词 |
|------|-------------|
| 日常推进（不确定做什么） | A |
| 专门做前端 | B |
| 专门做 CEO Agent | C |
| 专门做 Worker 执行 | D |
| 里程碑结束时验证 | E |
| 每轮结束时更新文档 | F |
| 确认完成后提交代码 | G |

典型工作流：A（或 B/C/D）→ F → E → G
