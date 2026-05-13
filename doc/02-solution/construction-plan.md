# Boardroom OS V2 建设方案

## 文档职责

本文件说明如何建设 V2。它不是 PRD，也不是代码设计细节；它负责阶段、顺序、优先级和防失败策略。

## 总体策略

采用近似全新项目路线：

```text
保留 repo / git 历史作为归档教训；
新分支使用干净目录和文档基座；
旧代码默认 abandoned by default；
V2 代码从新命名空间开始；
先建立合同、状态和证据内核，再接 provider 和生成项目。
```

## 建设原则

1. 先定义 contract，再写 executor。
2. 先写 negative tests，再写 happy path。
3. 先证明不能伪成功，再证明能真成功。
4. 先 tiny full-stack proving scenario，再扩展项目类型。
5. closeout 不是发现问题的地方，只是收束已证明事实。
6. runtime 不是治理者，只是事实执行和记录层。

## 阶段划分

| Phase | 名称 | 目标 |
|---|---|---|
| 0 | Foundation | 建立干净文档、边界和验收基座 |
| 1 | Contract Model | 定义 ProjectCharter、AcceptanceContract、PackageContract |
| 2 | Event + Reducer | 建立事件源、reducer、ticket graph 状态变更 |
| 3 | Execution Package Compiler | 将 ticket + contract 编译为 worker execution package |
| 4 | Provider Executor + Command Runner | 接入 provider attempt 和真实命令执行证据 |
| 5 | Evidence Verifier + Checker | 建立 evidence verifier、checker verdict、rework 闭环 |
| 6 | Workspace + Package Assembler | 生成项目 workspace、manifest、source inventory |
| 7 | Closeout + Replay + Process Audit | closeout gate、replay bundle、人类可读审计报告 |
| 8 | Tiny Full-stack Proving Scenario | 端到端证明一个可运行 full-stack generated project package |

## Phase 0 范围

Phase 0 只做：

- 干净文档目录；
- AI / code / test conventions；
- PRD；
- 建设方案；
- 技术架构草案；
- 领域模型草案；
- agent team 模型；
- contract/evidence 模型；
- generated project workspace 模型；
- roadmap/backlog/acceptance criteria；
- legacy boundary。

Phase 0 不做：

- runtime 实现；
- provider 接入；
- CLI；
- API；
- 数据库；
- UI；
- 旧代码整理；
- 旧模块迁移。

## 串行依赖

必须串行完成的主链：

```text
AcceptanceContract
-> PackageContract
-> TicketGraph
-> ExecutionPackage
-> ProviderAttempt + WorkProduct
-> VerificationRun + EvidenceClaim
-> CheckerVerdict
-> SourceInventory
-> CloseoutPackage
-> ReplayBundle
-> ProcessAuditReport
```

不能跳过前置合同直接写 executor。

## 可并行工作

以下可并行：

- docs template selector；
- negative acceptance tests；
- provider attempt schema；
- command runner sandbox design；
- process audit report template；
- generated workspace layout；
- source inventory schema。

## 最小里程碑

### M0: Clean Foundation

完成本文档基座，并明确旧实现 abandoned by default。

### M1: Contract Kernel

能从用户需求生成 active acceptance contract 和 package contract。

### M2: Graph Kernel

能用 reducer 管理 ticket graph，不允许 executor 直接改状态。

### M3: Evidence Kernel

能记录 provider attempt、command run、evidence claim，并 fail-closed。

### M4: Proving Package

生成 tiny full-stack package 并完成 closeout/replay/process audit。

## 风险与对策

| 风险 | 对策 |
|---|---|
| 再次被旧代码污染 | legacy boundary 默认禁止读取旧实现 |
| 又变成 runtime 流水线 | reducer + contract 决定状态，runtime 只提交事实 |
| evidence 只验形状 | evidence verifier 必须绑定来源、命令、hash、acceptance ref |
| prompt tuning 替代架构 | prompt 只作为 seat 行为输入，不能替代 contract |
| 过早做复杂项目 | tiny full-stack proving scenario 先行 |
| checker 软放行 | blocker 永远优先于 notes |

