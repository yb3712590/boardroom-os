# 交付物契约

## 目标

`DeliverableContract` 定义“最终产物是否满足 PRD”，而不是只判断 ticket 是否完成、checker 是否 approved、graph 是否 terminal。

第 15 轮暴露的问题是：runtime graph 可以被推到 completed，但 frontend placeholder、浅层 smoke evidence、failed check convergence、closeout final refs 误选等问题仍可能削弱最终交付可信度。

## 输入来源

交付物契约由以下输入编译：

- PRD / charter；
- locked scope；
- governance decisions；
- architecture/design assets；
- backlog recommendation；
- acceptance criteria；
- risk constraints；
- required audit mode。

契约编译结果必须成为 process asset，并记录版本。

## 核心字段

```yaml
deliverable_contract:
  contract_id: dc_<workflow_id>_<version>
  workflow_id: ...
  graph_version: ...
  source_prd_refs: []
  locked_scope: []
  acceptance_criteria: []
  required_source_surfaces: []
  required_evidence: []
  required_review_gates: []
  forbidden_placeholder_patterns: []
  closeout_requirements: []
  supersede_rules: []
```

## Required source surfaces

每个 source surface 必须描述：

- path pattern；
- owning capability；
- expected behavior；
- linked acceptance criteria；
- minimum non-placeholder evidence；
- required tests/checks。

示例：

```yaml
- surface_id: frontend.reader_loans
  paths:
    - 10-project/src/frontend/**/reader*/**
  required_capabilities:
    - source.modify.frontend
  acceptance_refs:
    - AC-reader-borrowing
    - AC-reader-reservations
  required_evidence:
    - frontend.integration_smoke
    - api_contract_test
```

## Required evidence kinds

| Evidence kind | 说明 |
|---|---|
| `source_inventory` | changed files + purpose mapping |
| `unit_test` | 单元测试结果 |
| `integration_test` | 前后端/服务集成测试 |
| `api_contract_test` | API contract 验证 |
| `ui_smoke` | UI 可见行为 smoke，截图/录屏/trace 优先 |
| `security_check` | 权限、输入、敏感信息检查 |
| `performance_check` | 如 PRD 要求 |
| `git_closeout` | diff/commit/working tree 证据 |
| `maker_checker_verdict` | 审查结论和 findings |
| `risk_disposition` | 已知风险与接受/修复说明 |

## Placeholder 禁止规则

以下内容不能满足 deliverable contract：

- 文件名或内容是 `source.py` 且无业务实现。
- 页面文字说明“后续里程碑补齐”但被当作最终 UI。
- 只有泛化 `1 passed`，没有业务断言。
- 测试 stdout 由 runtime fallback 默认生成。
- source inventory 未覆盖 changed source。
- evidence pack 没有关联 acceptance criteria。
- checker 只给 `APPROVED_WITH_NOTES`，但 blocking evidence gap 未关闭。
- closeout final refs 只有治理文档，没有 source/evidence/check refs。

## Supersede 规则

返工、重试、replacement 产生新产物时：

- 新 source delivery 必须声明 supersedes；
- 旧 placeholder / failed evidence 不能继续进入 final evidence set；
- closeout 只能选择 current graph pointer 对应的最终证据；
- old ticket late completion 只能作为 archive，不自动成为 current evidence。

## Checker 和 DeliverableContract 的关系

Checker verdict 不是最终真相。最终判断顺序：

1. schema validation；
2. write-set validation；
3. evidence completeness；
4. deliverable contract evaluation；
5. checker policy；
6. closeout policy。

`APPROVED_WITH_NOTES` 只能放行非阻塞 finding。只要 deliverable contract 存在 blocker，就必须 rework 或 explicit convergence policy。

## Closeout 要求

Closeout package 必须包含：

- deliverable contract version；
- acceptance criteria status table；
- final source surfaces；
- final evidence refs；
- supersede summary；
- unresolved non-blocking notes；
- risk disposition；
- replay bundle refs；
- audit materialization refs。

Closeout 不能只写：

```text
runtime graph completed
```

它必须写：

```text
PRD acceptance satisfied by these source/evidence/check refs
```

## 015 回归要求

新的 deliverable contract 必须阻断以下 015 中出现的问题：

- BR-040 placeholder fix 被 maker-checker 放行。
- BR-041 source.py 占位加一条泛化测试。
- BR-100 final checker 长循环无法收敛。
- closeout final refs 混入 `ARCHITECTURE.md` 或 backlog recommendation。
- manual closeout recovery 绕过 final evidence completeness。

## 验收标准

- 每个 deliverable contract 可独立评估。
- Contract evaluation 输出 machine-readable findings。
- Placeholder detection 有测试。
- Closeout 只接受 current graph final evidence。
- 015 replay 包可用于验证旧问题被阻断。
