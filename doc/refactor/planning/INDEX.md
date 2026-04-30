# 重构规划索引

这组文档是 `boardroom-os` 大规模重构的控制面。它不替代 `doc/new-architecture/` 的目标架构 canon，也不替代 `doc/mainline-truth.md` 的当前代码事实；它负责把当前问题、重构目标、目录约束、执行契约和后续推进提示词收口为可执行计划。

## 阅读顺序

1. [00-refactor-north-star.md](00-refactor-north-star.md) — 本轮重构北极星和取舍边界。
2. [01-current-state-audit.md](01-current-state-audit.md) — 当前问题审计和 015 测试评价。
3. [02-target-architecture.md](02-target-architecture.md) — 目标架构分层和核心边界。
4. [03-directory-contract.md](03-directory-contract.md) — 项目目录、workspace、artifact 和 archive 契约。
5. [04-write-surface-policy.md](04-write-surface-policy.md) — capability 驱动的写入权限策略。
6. [05-provider-contract.md](05-provider-contract.md) — provider adapter、streaming 和 retry 契约。
7. [06-actor-role-lifecycle.md](06-actor-role-lifecycle.md) — actor/employee/role/capability 生命周期。
8. [07-progression-policy.md](07-progression-policy.md) — 显式推进策略和 graph action 规则。
9. [08-deliverable-contract.md](08-deliverable-contract.md) — PRD 交付物契约和 closeout 可信性。
10. [09-refactor-plan.md](09-refactor-plan.md) — 分阶段重构计划。
11. [10-refactor-acceptance-criteria.md](10-refactor-acceptance-criteria.md) — 每阶段可验证验收标准。
12. [11-round-prompts.md](11-round-prompts.md) — 后续每一轮推进的提示词。

## 关联资料

- 当前代码事实：[../../mainline-truth.md](../../mainline-truth.md)
- 目标架构 canon：[../../new-architecture/README.md](../../new-architecture/README.md)
- 初始历史愿景：[../../archive/specs/feature-spec.md](../../archive/specs/feature-spec.md)
- 015 长审计：[../../tests/intergration-test-015-20260429.md](../../tests/intergration-test-015-20260429.md)
- 015 精简结论：[../../tests/intergration-test-015-20260429-final.md](../../tests/intergration-test-015-20260429-final.md)

## 使用规则

- 开始任何 runtime 重构前，先读 `00`、`02`、`09`、`10`。
- 涉及目录、产物或写权限时，必须读 `03` 和 `04`。
- 涉及 provider 时，必须读 `05`。
- 涉及员工、角色、派工或租约时，必须读 `06`。
- 涉及推进、fanout、rework、closeout 或 incident 时，必须读 `07` 和 `08`。
- 每轮执行优先使用 `11-round-prompts.md` 中对应提示词。
