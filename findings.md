# Findings

## Current Task

用户要的是一套适合“循环推进重构”的文档资产，不是一次性说明书。

## Key Findings

- 现有 `doc/roadmap-reset/agent-reset-prompt.md` 已经有“连续切片推进”的风格，可以复用语气和边界。
- `doc/new-architecture/README.md` 明确了目标架构的阅读顺序和不可留 TODO 的约束，适合作为只读决策层。
- `doc/README.md` 目前没有 `refactor/` 入口，补索引能降低下次会话的找文档成本。
- 为了高幂等性，除了模板外，还需要一个固定路径的主计划文档，让新会话直接续跑。

## Planned Outputs

- `doc/refactor/new-architecture-implementation-plan-template.md`
- `doc/refactor/new-architecture-implementation-plan.md`
- `doc/refactor/new-architecture-refactor-session-prompt.md`
- `doc/README.md` 入口更新
