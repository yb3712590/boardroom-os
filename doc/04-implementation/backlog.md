# Backlog

## 任务字段

每项任务必须包含：

```text
ID
状态
目标
输入文档
输出文件
验收口径
```

状态枚举：

```text
TODO | IN_PROGRESS | DONE | BLOCKED | DEFERRED
```

## 当前 Backlog

### V2-000: 建立 clean foundation

- 状态：DONE
- 目标：创建 V2 文档基座和目录结构。
- 输入文档：用户决策、外部审计摘要。
- 输出文件：根 README、AGENTS、doc 全目录。
- 验收口径：旧实现 abandoned by default；新代码入口明确；phase 0 文档齐全。

### V2-001: 确认 Phase 0 文档基座

- 状态：TODO
- 目标：人工审阅本基座，确认是否作为新 orphan 分支初始提交。
- 输入文档：全部 Phase 0 文档。
- 输出文件：必要修订。
- 验收口径：用户确认目录、文档职责、legacy boundary 和后续路线。

### V2-010: 定义 Contract Model schema

- 状态：TODO
- 目标：实现 ProjectCharter、AcceptanceContract、PackageContract、SourceSurface、EvidenceObligation 的最小 typed schema。
- 输入文档：`03-architecture/domain-model.md`、`contract-and-evidence-model.md`。
- 输出文件：`src/boardroom_os/contracts/`。
- 验收口径：schema validation tests；缺 active acceptance contract 的 implementation ticket 无效。

### V2-020: 定义 Event + Reducer kernel

- 状态：TODO
- 目标：实现 event record、ticket graph projection 和 reducer。
- 输入文档：`technical-architecture.md`、`domain-model.md`。
- 输出文件：`src/boardroom_os/events/`、`src/boardroom_os/reducers/`、`src/boardroom_os/graph/`。
- 验收口径：invalid transition fail closed；executor 不能直接完成 ticket。

### V2-030: 编译 ExecutionPackage

- 状态：TODO
- 目标：从 ready ticket + contract + seat assignment 生成 execution package。
- 输入文档：`agent-team-model.md`、`execution-and-runtime-boundary.md`。
- 输出文件：`src/boardroom_os/execution/`。
- 验收口径：缺 acceptance refs、allowed write set、evidence obligations 时无效。

### V2-040: Provider attempt 与 command runner

- 状态：TODO
- 目标：实现 provider attempt 记录和本地命令执行证据。
- 输入文档：`execution-and-runtime-boundary.md`、`TEST_CONVENTIONS.md`。
- 输出文件：`src/boardroom_os/providers/`、`src/boardroom_os/adapters/process_runner.py`。
- 验收口径：zero provider attempt 必须阻断 implementation ticket；command evidence 来自 runner。

### V2-050: Evidence verifier 与 checker

- 状态：TODO
- 目标：实现 evidence claim、verifier、checker verdict 和 rework 触发。
- 输入文档：`contract-and-evidence-model.md`。
- 输出文件：`src/boardroom_os/evidence/`。
- 验收口径：missing evidence -> REWORK_REQUIRED；checker notes 不能覆盖 blocker。

### V2-060: Workspace 与 package assembler

- 状态：TODO
- 目标：生成目标项目 workspace、run manifest 和 source inventory。
- 输入文档：`generated-project-workspace.md`。
- 输出文件：`src/boardroom_os/workspace/`。
- 验收口径：source inventory 来自 package root + git/hash，不来自 payload 猜测。

### V2-070: Closeout / replay / process audit

- 状态：TODO
- 目标：实现 closeout gate、replay bundle 和 process audit。
- 输入文档：`process-audit-and-replay.md`。
- 输出文件：`src/boardroom_os/closeout/`、`src/boardroom_os/audit/`。
- 验收口径：缺 replay 或 evidence map 不能 terminal success。

### V2-080: Tiny full-stack proving scenario

- 状态：TODO
- 目标：端到端生成 tiny book availability tracker。
- 输入文档：`proving-scenario-tiny-fullstack.md`。
- 输出文件：scenario test、generated workspace、closeout audit。
- 验收口径：所有 proving scenario 验收项通过。

