# 技术架构方案

## 文档职责

本文件给出 V2 的总体技术架构。详细领域对象见 `domain-model.md`，agent team 见 `agent-team-model.md`，证据链见 `contract-and-evidence-model.md`。

## 架构目标

V2 的核心架构目标：

```text
CEO-governed
contract-first
reducer-protected
evidence-backed
package-oriented
audit-readable
replayable
```

## 总体数据流

```text
BoardDirective / PRD
  -> ProjectCharter
  -> AcceptanceContract
  -> PackageContract
  -> TicketGraph
  -> ExecutionPackage
  -> ProviderAttempt / ToolAttempt
  -> WorkProduct
  -> VerificationRun
  -> EvidenceClaim
  -> EvidenceVerifier
  -> CheckerVerdict
  -> SourceInventory
  -> CloseoutPackage
  -> ReplayBundle
  -> ProcessAuditReport
```

## 模块划分

建议未来代码模块：

```text
src/boardroom_os/
├── contracts/       # schema and typed domain contracts
├── events/          # event records and event log abstraction
├── reducers/        # state transition reducers and validators
├── graph/           # ticket graph projection and query
├── agents/          # role, seat, prompt package, delegation model
├── execution/       # execution package compiler and executor boundary
├── providers/       # provider adapters and attempt recording
├── workspace/       # generated project workspace manager
├── evidence/        # evidence claims, verifiers, source inventory
├── closeout/        # closeout gates and summaries
├── audit/           # process audit and replay materialization
└── adapters/        # filesystem, git, process runner, persistence
```

## 核心服务

### Contract Compiler

输入：用户需求、PRD、CEO/architect governance artifacts。

输出：

- `ProjectCharter`
- `AcceptanceContract`
- `PackageContract`

职责：把自然语言目标转为可验证合同。

### Ticket Graph Reducer

输入：validated graph events。

输出：current graph projection。

职责：保护所有状态变更，防止 executor 直接推进项目。

### Execution Package Compiler

输入：ready ticket、contract、workspace manifest、seat assignment。

输出：`ExecutionPackage`。

职责：给 worker 明确目标、上下文、写入边界、证据义务和命令要求。

### Provider Executor

输入：`ExecutionPackage`。

输出：provider attempt record、raw output、parsed work product。

职责：调用模型或工具，不做产品完成判断。

### Command Runner

输入：declared command、workspace root、environment profile。

输出：`VerificationRun`。

职责：真实执行测试、启动、集成或检查命令，记录 exit code/stdout/stderr/duration/hash。

### Evidence Verifier

输入：evidence claims、verification runs、source files、git state、contracts。

输出：verified evidence table / blockers。

职责：证明 evidence 是否满足 active contract。

### Checker

输入：work product、source diff、verified evidence、contract obligations。

输出：checker verdict。

职责：独立审查，不能替 worker 补证据。

### Closeout Manager

输入：completed graph、source inventory、final evidence table、replay bundle、git audit。

输出：closeout package。

职责：只收束已证明事实。

### Process Audit Builder

输入：event log、graph projection、agent contexts、artifacts、evidence、git audit。

输出：human-readable audit report。

职责：让人能读懂过程，而不是只看 raw events。

## 状态源

| 状态 | Source of Truth |
|---|---|
| 需求 | BoardDirective / PRD |
| 验收 | AcceptanceContract |
| 包结构和运行方式 | PackageContract |
| 流程进度 | TicketGraph projection |
| 历史 | EventLog |
| 产物 | Workspace + artifact store |
| 证据 | Verified evidence table |
| 版本 | Git audit |
| 最终完成 | CloseoutPackage |

## 关键设计约束

- runtime 不能制造 implementation source。
- command result 必须来自 runner。
- acceptance criteria 必须动态派生。
- source inventory 必须绑定 git/hash/producer/evidence。
- closeout 不能通过 raw event scanning 猜完成。
- process audit 是产品能力，不是 debug dump。

