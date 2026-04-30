# 重构文档入口

`doc/refactor/` 只承载当前自治 runtime 大重构控制面。旧新架构实施计划、旧模板和旧会话提示词已经移入 `doc/archive/refactor-legacy/`，不再作为当前执行入口。

## 当前优先入口

- [planning/INDEX.md](planning/INDEX.md) — 2026-05 自治 runtime 大重构控制面。
- [planning/00-refactor-north-star.md](planning/00-refactor-north-star.md) — 本轮重构北极星。
- [planning/01-current-state-audit.md](planning/01-current-state-audit.md) — 当前问题审计与本轮清理记录。
- [planning/03-directory-contract.md](planning/03-directory-contract.md) — 项目目录、workspace、artifact 和 archive 契约。
- [planning/09-refactor-plan.md](planning/09-refactor-plan.md) — 分阶段重构计划。
- [planning/10-refactor-acceptance-criteria.md](planning/10-refactor-acceptance-criteria.md) — 可验证验收标准。
- [planning/11-round-prompts.md](planning/11-round-prompts.md) — 每轮推进提示词。

## 关联资料

- 当前代码事实：[../mainline-truth.md](../mainline-truth.md)
- 目标架构 canon：[../new-architecture/README.md](../new-architecture/README.md)
- 历史愿景：[../archive/specs/feature-spec.md](../archive/specs/feature-spec.md)
- 旧重构实施资料：[../archive/refactor-legacy/](../archive/refactor-legacy/)

## 使用规则

- 新一轮后端自治 runtime 重构默认从 `planning/INDEX.md` 进入。
- `doc/new-architecture/` 仍是目标架构 canon，不在普通实施中直接改写。
- `doc/mainline-truth.md` 仍是当前代码事实锚点。
- 历史材料只从 `doc/archive/` 追溯。
