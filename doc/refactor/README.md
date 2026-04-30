# 重构文档入口

`doc/refactor/` 存放当前和历史重构控制面。

## 当前优先入口

- [planning/INDEX.md](planning/INDEX.md) — 2026-05 自治 runtime 大重构控制面。
- [planning/00-refactor-north-star.md](planning/00-refactor-north-star.md) — 本轮重构北极星。
- [planning/09-refactor-plan.md](planning/09-refactor-plan.md) — 分阶段重构计划。
- [planning/10-refactor-acceptance-criteria.md](planning/10-refactor-acceptance-criteria.md) — 可验证验收标准。
- [planning/11-round-prompts.md](planning/11-round-prompts.md) — 每轮推进提示词。

## 既有新架构实施资料

以下文档保留为历史实施主计划和会话提示，不在本次初始提交中重写：

- [new-architecture-implementation-plan.md](new-architecture-implementation-plan.md) — 旧新架构重构实施计划。
- [new-architecture-implementation-plan-template.md](new-architecture-implementation-plan-template.md) — 旧实施计划模板。
- [new-architecture-refactor-session-prompt.md](new-architecture-refactor-session-prompt.md) — 旧重构会话提示词。

## 使用规则

- 新一轮大重构默认从 `planning/INDEX.md` 进入。
- `doc/new-architecture/` 仍是目标架构 canon，不在普通实施中直接改写。
- `doc/mainline-truth.md` 仍是当前代码事实锚点。
- 历史愿景只从 `doc/archive/specs/feature-spec.md` 追溯。
