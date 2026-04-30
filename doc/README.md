# 文档索引

`doc/` 现在只保留当前真相、自治 runtime 重构控制面、后端参考和必要历史入口。默认不要从旧路线、旧设计、旧任务流水或长 integration logs 开始读。

## 默认首读

1. [mainline-truth.md](mainline-truth.md)：当前后端代码事实、runtime 支持矩阵和冻结边界。
2. [refactor/planning/INDEX.md](refactor/planning/INDEX.md)：2026-05 自治 runtime 大重构控制面。
3. [refactor/planning/00-refactor-north-star.md](refactor/planning/00-refactor-north-star.md)：本轮重构北极星、非目标和核心不变量。
4. [refactor/planning/09-refactor-plan.md](refactor/planning/09-refactor-plan.md)：分阶段重构计划。
5. [refactor/planning/10-refactor-acceptance-criteria.md](refactor/planning/10-refactor-acceptance-criteria.md)：每阶段验收标准。

## 当前工作参考

- [refactor/README.md](refactor/README.md)：重构文档入口。
- [refactor/planning/11-round-prompts.md](refactor/planning/11-round-prompts.md)：后续每轮推进提示词。
- [backend-runtime-guide.md](backend-runtime-guide.md)：后端运行、live 场景和排障指南。
- [api-reference.md](api-reference.md)：当前后端 HTTP 接口参考。
- [new-architecture/README.md](new-architecture/README.md)：目标架构 canon；不等同于当前实现事实。

## 必要历史入口

- [archive/README.md](archive/README.md)：旧 spec、旧计划、旧设计、旧路线、旧任务流水、旧会话提示词和旧 integration logs 的统一入口。
- [archive/specs/feature-spec.md](archive/specs/feature-spec.md)：初始历史愿景来源，只作追溯。
- [tests/intergration-test-015-20260429.md](tests/intergration-test-015-20260429.md)：015 详细审计证据。
- [tests/intergration-test-015-20260429-final.md](tests/intergration-test-015-20260429-final.md)：015 精简结论。

## 阅读规则

- 默认固定顺序：`README.md -> doc/README.md -> doc/mainline-truth.md -> doc/refactor/planning/INDEX.md`。
- 做 runtime 重构时，按 [refactor/planning/INDEX.md](refactor/planning/INDEX.md) 的阅读顺序进入。
- 涉及目录、产物、写权限时，优先读 [refactor/planning/03-directory-contract.md](refactor/planning/03-directory-contract.md) 和 [refactor/planning/04-write-surface-policy.md](refactor/planning/04-write-surface-policy.md)。
- 旧设计、旧路线、旧任务 backlog 和 001-014 integration logs 只从 [archive/README.md](archive/README.md) 按需打开。
