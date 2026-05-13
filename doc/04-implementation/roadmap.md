# Roadmap

## 文档职责

本文件定义 V2 从文档基座到 proving scenario 的长期实施路线。

## Phase 0: Foundation

目标：建立干净分支和基础文档。

产物：

- README / AGENTS；
- 文档目录和索引；
- PRD；
- 建设方案；
- 架构草案；
- 领域模型；
- agent team 模型；
- contract/evidence 模型；
- runtime 边界；
- acceptance criteria；
- backlog；
- legacy boundary。

验收：

- 旧实现默认 abandoned by default；
- 新代码入口明确；
- no code implementation；
- AI 行为约束明确。

## Phase 1: Contract Model

目标：实现可版本化 contract objects。

产物：

- ProjectCharter；
- AcceptanceContract；
- PackageContract；
- SourceSurface；
- EvidenceObligation；
- schema validation；
- negative contract tests。

验收：

- 不存在 active acceptance contract 时无法创建 implementation ticket；
- static criteria 不能替代动态 criteria；
- package contract 缺 run/test commands 必须失败。

## Phase 2: Event + Reducer

目标：建立 event log、ticket graph projection 和 reducer。

产物：

- event record schema；
- reducer；
- graph projection；
- state transition validators；
- replay of graph projection。

验收：

- executor 不能直接完成 ticket；
- invalid transition 被拒绝；
- graph version 可追踪。

## Phase 3: Execution Package Compiler

目标：将 ticket + contract + seat 编译为 execution package。

产物：

- seat assignment；
- execution package；
- allowed write set；
- context refs；
- evidence obligations；
- fallback policy。

验收：

- 缺 acceptance refs 或 write set 的 execution package 无效；
- worker 不能写入非授权路径。

## Phase 4: Provider Executor + Command Runner

目标：接入 provider attempt 和真实命令执行。

产物：

- provider adapter interface；
- fake provider with attempt record；
- command runner；
- stdout/stderr artifact capture；
- failure taxonomy。

验收：

- provider zero-attempt 阻断 implementation completion；
- command evidence 必须来自 runner；
- fallback 不满足 implementation evidence。

## Phase 5: Evidence Verifier + Checker

目标：验证 evidence 并形成 rework 闭环。

产物：

- evidence claim；
- verifier；
- final evidence table；
- checker verdict；
- rework ticket generation。

验收：

- missing evidence -> REWORK_REQUIRED；
- checker notes 不能覆盖 blocker；
- source inventory ref-only 不能 closeout。

## Phase 6: Workspace + Package Assembler

目标：生成项目 workspace 和 package manifest。

产物：

- workspace manager；
- generated project docs template；
- package assembler；
- source inventory from git tree；
- run manifest。

验收：

- source files 在 package root 内；
- final commit clean；
- source inventory 覆盖 required surfaces。

## Phase 7: Closeout + Replay + Process Audit

目标：closeout 只收束已证明事实，并产出审计资料。

产物：

- closeout gate；
- replay bundle；
- process audit builder；
- git version audit；
- closeout summary。

验收：

- missing replay bundle 阻断 terminal success；
- process audit 能回答关键治理问题。

## Phase 8: Tiny Full-stack Proving Scenario

目标：端到端生成一个小型 full-stack 项目包。

验收：见 `proving-scenario-tiny-fullstack.md`。

