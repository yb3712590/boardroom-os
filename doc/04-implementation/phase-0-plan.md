# Phase 0 Plan

## 文档职责

本文件定义当前 foundation-only 阶段的具体完成标准。

## 目标

建立一个可直接作为 V2 clean branch 初始提交的文档基座。

## 创建文件

根目录：

- `README.md`
- `AGENTS.md`
- `.gitignore`

通用规范：

- `doc/README.md`
- `doc/AI_CONVENTIONS.md`
- `doc/CODE_CONVENTIONS.md`
- `doc/TEST_CONVENTIONS.md`

产品与方案：

- `doc/01-product/INDEX.md`
- `doc/01-product/prd.md`
- `doc/02-solution/INDEX.md`
- `doc/02-solution/construction-plan.md`

架构：

- `doc/03-architecture/INDEX.md`
- `doc/03-architecture/technical-architecture.md`
- `doc/03-architecture/domain-model.md`
- `doc/03-architecture/agent-team-model.md`
- `doc/03-architecture/contract-and-evidence-model.md`
- `doc/03-architecture/execution-and-runtime-boundary.md`
- `doc/03-architecture/generated-project-workspace.md`
- `doc/03-architecture/process-audit-and-replay.md`

实施：

- `doc/04-implementation/INDEX.md`
- `doc/04-implementation/roadmap.md`
- `doc/04-implementation/backlog.md`
- `doc/04-implementation/acceptance-criteria.md`
- `doc/04-implementation/phase-0-plan.md`
- `doc/04-implementation/proving-scenario-tiny-fullstack.md`

日志与参考：

- `doc/05-project-log/INDEX.md`
- `doc/05-project-log/decisions.md`
- `doc/05-project-log/2026-05.md`
- `doc/06-reference/INDEX.md`
- `doc/06-reference/audit-summary.md`
- `doc/06-reference/legacy-boundary.md`

实现入口占位：

- `src/README.md`
- `tests/README.md`
- `scripts/README.md`
- `examples/README.md`

## 完成标准

Phase 0 完成时：

1. 旧实现边界明确；
2. V2 产品目标明确；
3. V2 建设路线明确；
4. 核心对象模型明确；
5. runtime 权力边界明确；
6. contract/evidence/closeout 关系明确；
7. negative acceptance 明确；
8. backlog 已初始化；
9. 后续代码入口明确；
10. 没有实现代码。

## 明确不做

Phase 0 不做：

- schema 实现；
- event log 实现；
- provider adapter；
- command runner；
- workspace manager；
- CLI/API/UI；
- 旧代码迁移；
- legacy asset map。

