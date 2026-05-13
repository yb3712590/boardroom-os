# Boardroom OS V2 文档索引

本目录是 V2 的文档基座。它不是旧文档迁移结果，而是全新实现的治理、架构、合同、证据和实施约束入口。

## 阅读路径

```text
01-product/prd.md
  -> 02-solution/construction-plan.md
  -> 03-architecture/technical-architecture.md
  -> 03-architecture/domain-model.md
  -> 03-architecture/contract-and-evidence-model.md
  -> 04-implementation/acceptance-criteria.md
```

## 目录结构

```text
doc/
├── README.md
├── AI_CONVENTIONS.md
├── CODE_CONVENTIONS.md
├── TEST_CONVENTIONS.md
├── 01-product/
├── 02-solution/
├── 03-architecture/
├── 04-implementation/
├── 05-project-log/
└── 06-reference/
```

## 目录职责

| 目录 | 职责 |
|---|---|
| `01-product/` | 产品语义、用户、场景、非目标、成功标准 |
| `02-solution/` | 建设路线、阶段、里程碑、风险和取舍 |
| `03-architecture/` | 领域模型、agent team、合同证据、runtime 边界、workspace、audit/replay |
| `04-implementation/` | roadmap、backlog、验收标准、当前阶段计划、proving scenario |
| `05-project-log/` | 决策日志和时间线 |
| `06-reference/` | 审计摘要和旧实现边界 |

## 维护要求

1. 每个子目录必须保留 `INDEX.md`。
2. 新增文档必须加入对应 `INDEX.md`。
3. 重大决策必须写入 `05-project-log/decisions.md`。
4. 验收规则变化必须同步 `04-implementation/acceptance-criteria.md`。
5. 与旧实现相关的描述必须只放在 `06-reference/`，不要污染架构主文档。

