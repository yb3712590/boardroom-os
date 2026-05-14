# Backlog

## TL;DR / AI 启动入口

后续任务都从本文件开始，不从旧 runtime、旧 contracts、旧测试或旧文档推导 V2 实施。

启动顺序：

1. 读取本文件，选择第一个未完成的 `TODO` / `IN_PROGRESS` 工作包。
2. 执行下面的 **Pre-flight 一致性检查**：确认 backlog 状态与代码 / 文档实际状态一致。若发现 drift，停下并向用户报告，不擅自补齐。
3. 按工作包的输入文档读取相关架构和验收文件。
4. 若工作包涉及 contract、evidence、runtime、testing、closeout、workspace 或架构边界，额外读取 `doc/03-architecture/` 下相关文档和 `doc/06-reference/legacy-boundary.md`。
5. 实施前先写 negative tests（负例测试），再写最小实现和 happy path（正向路径）测试。
6. 完成后执行下面的 **工作包完成更新协议** 全部条目。

**当前任务文件**：`doc/04-implementation/backlog.md`

**当前验收文件**：`doc/04-implementation/acceptance-criteria.md`

**当前未完成工作包**：`V2-001A`

**当前重点**：先完成 V2-001 的 Phase 0 文档基座确认，再进入 V2-010 Contract Kernel（合同内核）。

## 实施幂等性 / 工作包完成更新协议

每次会话的启动提示词都接近。为保证跨会话项目状态全局一致，模型必须严格从下列文档协议推导"完成后改哪些文件"，不依赖会话记忆。

### Pre-flight 一致性检查

进入任一工作包前必须确认：

1. 工作包状态字段（`TODO` / `IN_PROGRESS` / `DONE` / `BLOCKED` / `DEFERRED`）与代码、测试、文档实际状态一致。
2. 工作包"输出文件"声明的路径在 git tree 中的存在状态与状态字段一致（DONE 则文件必须存在；TODO 则文件不应存在或仅占位）。
3. 对应"分批验收"checkbox（见 `acceptance-criteria.md`）与工作包状态一致。

若发现任一不一致（drift），停下并报告，不擅自补齐或回滚。

### 工作包完成更新协议（每个工作包完成后必须按序执行）

1. **`doc/04-implementation/backlog.md`**
   - 把对应工作包"状态"改为 `DONE`
   - 更新顶部 TL;DR 的"当前未完成工作包"指向下一个 `TODO` 工作包
   - 更新"进度总览"表中对应 phase 的完成计数

2. **`doc/04-implementation/acceptance-criteria.md`**
   - 勾选本工作包覆盖的"分批验收"checkbox
   - 若本工作包是本 phase 最后一项，勾选"进入下一 Phase 前置"全部项

3. **`doc/05-project-log/YYYY-MM.md`（当月日志）**
   - 按日期追加一条记录：包含工作包 ID、关键产出文件、走过的 negative / happy 测试、验证证据引用

4. **`doc/05-project-log/decisions.md`（仅当产生方法论 / 架构 / 范围层面决策）**
   - 新增 `DEC-XXXX` 条目

5. **相应子目录 `INDEX.md`（仅当新增了文档文件）**
   - 在 `doc/` 子目录新增了 Markdown 时，更新对应 INDEX.md
   - 代码模块新增不要求更新 doc INDEX，但 backlog 输出文件清单应反映出来

6. **`doc/04-implementation/acceptance-criteria.md` 中的 AC-V2-XXX 抽象原则段**
   - 仅当本工作包扩展或改变了原有 AC 语义时同步

### 幂等保证

上述更新允许重复执行而不引入新副作用：状态字段是赋值（重复赋值不变），checkbox 是幂等切换（重复勾选仍为已勾选），日志条目以"日期 + 工作包 ID"作为去重键。若发现本工作包已有完整更新痕迹，**不重复添加新条目**。

### 里程碑 vs 工作包

顶层 `V2-XXX`（如 V2-010、V2-020）是里程碑，**不要求** negative / happy tests 和单独的输出文件 —— 它通过其下所有 `V2-XXXA` / `V2-XXXB` 工作包的完成来满足。Pre-flight 检查和完成协议只针对工作包级别，不针对里程碑级别。

## V2-000 完成情况确认

| 项目 | 当前状态 | 依据 |
|---|---|---|
| clean foundation | DONE | 根入口、doc 全目录、src/tests/scripts/examples 占位已建立 |
| legacy boundary（旧实现边界） | DONE | `AGENTS.md`、`doc/06-reference/legacy-boundary.md` 和决策日志均声明 abandoned by default |
| 新实现入口 | DONE | V2 主代码限定为 `src/boardroom_os/`，测试进入 `tests/`，脚本进入 `scripts/` |
| Phase 0 文档基座 | DONE | PRD、construction plan、architecture、acceptance criteria、roadmap、backlog、phase-0-plan 均存在 |
| 实现代码 | TODO | 当前仍是 foundation-only；V2-010 之前不写实现主路径 |

结论：V2-000 已完成，可作为 clean foundation 基线；后续所有实施从本 backlog 的未完成工作包开始，不能回到旧 runtime 语义。

## 工作包规则

顶层 `V2-xxx` 是里程碑，不是足够实施的任务。实际实施必须落到 `V2-xxxA` / `V2-xxxB` 这类工作包。

每个工作包必须具备：

```text
ID
状态
目标
输入文档
依赖
输出文件
必须先写的 negative tests
必须证明的 happy path
验收口径
```

状态枚举：

```text
TODO | IN_PROGRESS | DONE | BLOCKED | DEFERRED
```

代码落点固定为：

```text
src/boardroom_os/
tests/
scripts/
```

禁止把 generated project workspace（生成项目工作区）的目录结构误用为本框架自身仓库结构。

## 子项目依赖图

```text
V2-001 Phase 0 audit
  -> V2-010 Contract Kernel
  -> V2-020 Event + Reducer Kernel
  -> V2-030 Agent Seat + Execution Package Compiler
  -> V2-040 Runtime Executor + Provider + Command Runner
  -> V2-050 Evidence Verifier + Checker + Rework
  -> V2-060 Workspace + Package Assembler
  -> V2-070 Closeout + Replay + Process Audit
  -> V2-080 Tiny Full-stack Proving Scenario
```

关键接入链必须显式实现，不能靠散文约定：

```text
RoleProfile（角色模板）
  -> AgentSeat（项目席位）
  -> ModelExecutionProfile（provider/model/effort 配置）
  -> ExecutionPackage（执行包，携带 seat_ref 和 model_execution_profile）
  -> ProviderAttempt（模型调用尝试记录，绑定 execution_package_ref）
  -> WorkProduct（工作产物，绑定 producer_attempt_ref）
  -> EvidenceClaim（证据声明，绑定 producer_attempt_ref）
  -> VerifiedEvidenceTable（已验证证据表）
  -> SourceInventory（源码清单，绑定 producer_ticket / attempt / evidence）
  -> CloseoutPackage（收尾包）
```

如果任一 implementation ticket（实施任务）需要 provider（模型供应商）但缺 `ModelExecutionProfile`、`AgentSeat`、`ExecutionPackage` 或 `ProviderAttempt` 绑定，必须 fail closed（失败关闭）。

## 进度总览

| 阶段 | 顶层任务 | 工作包完成/总数 | 状态 |
|---|---|---:|---|
| Phase 0：Foundation | V2-000, V2-001 | 1 / 4 | 进行中 |
| Phase 1：Contract Kernel | V2-010 | 0 / 7 | 待开始 |
| Phase 2：Event + Reducer Kernel | V2-020 | 0 / 6 | 待开始 |
| Phase 3：Agent + Execution Package | V2-030 | 0 / 6 | 待开始 |
| Phase 4：Runtime + Provider + Runner | V2-040 | 0 / 5 | 待开始 |
| Phase 5：Evidence + Checker | V2-050 | 0 / 6 | 待开始 |
| Phase 6：Workspace + Package | V2-060 | 0 / 5 | 待开始 |
| Phase 7：Closeout + Replay + Audit | V2-070 | 0 / 6 | 待开始 |
| Phase 8：Tiny proving scenario | V2-080 | 0 / 6 | 待开始 |
| **合计** | **V2-000 ~ V2-080** | **1 / 51** | **foundation-only** |

## 当前约束摘要

- Contract first：implementation ticket 前必须有 active AcceptanceContract（验收合同）和 PackageContract（包合同）。
- Reducer first：关键状态变更必须通过 reducer（状态归约器）或 validator（校验器）。
- Evidence first：没有真实 evidence（证据）不得 closeout（收尾）。
- Runtime bounded：runtime（运行时）只执行、记录、校验、投影事实，不做 CEO / architect / checker / closeout 决策。
- Negative tests first：先证明伪交付、fallback、synthetic verification 等失败路径不能通过。
- Final output：最终交付物是 generated project package（生成项目包），不是离散 source artifact（源码片段）。

---

## V2-000: 建立 clean foundation

- 状态：DONE
- 目标：创建 V2 文档基座和目录结构。
- 输入文档：用户决策、外部审计摘要。
- 输出文件：根 README、AGENTS、doc 全目录、src/tests/scripts/examples 占位。
- 验收口径：旧实现 abandoned by default；新代码入口明确；phase 0 文档齐全；没有 V2 实现代码。

## V2-001: 确认 Phase 0 文档基座

- 状态：TODO
- 目标：人工审阅本基座，确认是否作为新 clean foundation 的实施起点。
- 输入文档：全部 Phase 0 文档。
- 输出文件：必要修订。
- 验收口径：用户确认目录、文档职责、legacy boundary、工作包拆解和后续路线。

### V2-001A: Phase 0 完整性审计

- 状态：TODO
- 目标：逐项确认 Phase 0 完成标准是否被当前文件覆盖。
- 输入文档：`doc/04-implementation/phase-0-plan.md`、`doc/04-implementation/acceptance-criteria.md`、`doc/05-project-log/decisions.md`。
- 依赖：V2-000。
- 输出文件：`doc/04-implementation/backlog.md`、必要时更新 `doc/05-project-log/2026-05.md`。
- 必须先写的 negative tests：无代码；文档审计必须列出任何缺失项，不能把“文档存在”自动等同于“职责完整”。
- 必须证明的 happy path：Phase 0 完成标准 10 项均可映射到现有文档或明确后续任务。
- 验收口径：V2-001 是否可以进入用户确认状态有明确依据。

### V2-001B: 工作包计划审计

- 状态：TODO
- 目标：确认每个后续里程碑都拆成可实施工作包，且每包有输入、输出、负例、正例和验收。
- 输入文档：本文件、`doc/03-architecture/technical-architecture.md`、`doc/03-architecture/agent-team-model.md`。
- 依赖：V2-001A。
- 输出文件：`doc/04-implementation/backlog.md`。
- 必须先写的 negative tests：无代码；审计必须标记任何“只有阶段名、没有可落地文件和测试”的任务。
- 必须证明的 happy path：后续 worker 可以从任意 `TODO` 工作包知道要读什么、写什么、测什么。
- 验收口径：backlog 不再只是 8 步阶段索引，而是可执行 work package plan（工作包计划）。

### V2-001C: Phase 0 用户确认与冻结

- 状态：TODO
- 目标：拿到用户对 Phase 0 和 backlog 工作包拆解的确认。
- 输入文档：本文件、`doc/04-implementation/acceptance-criteria.md`。
- 依赖：V2-001B。
- 输出文件：`doc/05-project-log/2026-05.md`。
- 必须先写的 negative tests：无代码；不得在用户确认前宣称 Phase 0 已可进入实现阶段。
- 必须证明的 happy path：用户确认后，V2-010 可以作为第一个代码实施子项目启动。
- 验收口径：V2-001 状态可改为 DONE，下一包为 V2-010A。

---

## V2-010: Contract Kernel（合同内核）

- 状态：TODO
- 目标：实现 ProjectCharter、AcceptanceContract、PackageContract、SourceSurface、EvidenceObligation 的最小 typed schema（类型化结构）和 fail-closed 校验。
- 输入文档：`doc/03-architecture/domain-model.md`、`doc/03-architecture/contract-and-evidence-model.md`、`doc/04-implementation/acceptance-criteria.md`。
- 输出目录：`src/boardroom_os/contracts/`、`tests/contracts/`、`tests/negative/`。
- 顶层验收口径：schema validation tests 通过；缺 active AcceptanceContract 或 PackageContract 的 implementation ticket 无效；static universal AC 不能替代动态合同。

### V2-010A: 建立 contracts 包和基础值对象

- 状态：TODO
- 目标：创建合同模块的包结构、基础枚举、ID 类型和值对象。
- 输入文档：`domain-model.md`。
- 依赖：V2-001C。
- 输出文件：`src/boardroom_os/contracts/__init__.py`、`src/boardroom_os/contracts/types.py`、`tests/contracts/test_contract_types.py`。
- 必须先写的 negative tests：空 ID、空 acceptance refs、未知状态必须校验失败。
- 必须证明的 happy path：合法 ID、状态、引用集合可构造并序列化。
- 验收口径：后续 schema 不直接使用裸 dict 表达核心字段。

### V2-010B: 实现 BoardDirective intake

- 状态：TODO
- 目标：把用户原始需求（自然语言、PRD 文件、人审反馈）落地为 typed BoardDirective，作为合同链入口。
- 输入文档：`domain-model.md`、`process-audit-and-replay.md`。
- 依赖：V2-010A。
- 输出文件：`src/boardroom_os/contracts/directive.py`、`tests/contracts/test_board_directive.py`、`tests/negative/test_board_directive_fail_closed.py`。
- 必须先写的 negative tests：directive 缺 `source_type` / `content_ref` / `received_at` / `requester_ref` 必须失败；未知 `source_type` 必须失败；ProjectCharter 引用不存在的 directive 必须失败。
- 必须证明的 happy path：三种 `source_type`（`natural_language` / `prd_file` / `human_review_update`）的 directive 都可构造、序列化并被 ProjectCharter 引用。
- 验收口径：合同链入口闭合 —— 不存在 BoardDirective 不得创建 ProjectCharter。

### V2-010C: 实现 ProjectCharter 与 AcceptanceContract

- 状态：TODO
- 目标：表达项目章程和动态验收合同。
- 输入文档：`domain-model.md`、`contract-and-evidence-model.md`。
- 依赖：V2-010B。
- 输出文件：`src/boardroom_os/contracts/project.py`、`src/boardroom_os/contracts/acceptance.py`、`tests/contracts/test_acceptance_contract.py`、`tests/negative/test_acceptance_contract_fail_closed.py`。
- 必须先写的 negative tests：空 criteria、非 blocking criteria 全覆盖、criterion 缺 evidence_required、criterion 缺 source_surface_refs、charter 缺 board_directive_ref 必须失败。
- 必须证明的 happy path：动态 criteria 可绑定 ProjectCharter，并能查询 blocking criteria。
- 验收口径：implementation ticket 不能用固定静态 AC 列表绕过 active AcceptanceContract。

### V2-010D: 实现 PackageContract 与 SourceSurface

- 状态：TODO
- 目标：定义最终 generated project package（生成项目包）的目录、运行命令、测试命令、source surfaces（源码实现面）和 integration boundaries（集成边界）。
- 输入文档：`contract-and-evidence-model.md`、`generated-project-workspace.md`。
- 依赖：V2-010C。
- 输出文件：`src/boardroom_os/contracts/package.py`、`src/boardroom_os/contracts/source_surface.py`、`tests/contracts/test_package_contract.py`、`tests/negative/test_package_contract_fail_closed.py`。
- 必须先写的 negative tests：缺 package_root、缺 source_surfaces、软件项目缺 run/test commands、surface 无 acceptance_refs 必须失败。
- 必须证明的 happy path：一个 tiny full-stack package contract 能声明 backend、frontend、tests、docs、run manifest surfaces。
- 验收口径：最终交付被约束为 package，不是散落 source artifacts。

### V2-010E: 实现 EvidenceObligation 与 contract gate

- 状态：TODO
- 目标：把 acceptance criteria 转换成 ticket/execution 必须满足的 evidence obligations（证据义务）。
- 输入文档：`contract-and-evidence-model.md`、`acceptance-criteria.md`。
- 依赖：V2-010D。
- 输出文件：`src/boardroom_os/contracts/evidence_obligation.py`、`src/boardroom_os/contracts/gates.py`、`tests/contracts/test_evidence_obligation.py`、`tests/negative/test_contract_gate.py`。
- 必须先写的 negative tests：缺 active acceptance contract、缺 package contract、acceptance_ref 不属于 active contract、obligation 不 blocking 但对应 blocking criterion 必须失败。
- 必须证明的 happy path：从 active contracts 生成完整 obligation set。
- 验收口径：后续 ticket graph 创建 implementation ticket 前可调用 contract gate。

### V2-010F: 实现 MethodologyProfile 与 workspace template 绑定

- 状态：TODO
- 目标：把 CEO 选择的方法论（Minimal / Agile / Compliance / Hybrid）落地为 typed MethodologyProfile，并与 PackageContract、生成项目 docs template 绑定。
- 输入文档：`agent-team-model.md`、`generated-project-workspace.md`、`02-solution/construction-plan.md`。
- 依赖：V2-010E。
- 输出文件：`src/boardroom_os/contracts/methodology.py`、`tests/contracts/test_methodology_profile.py`、`tests/negative/test_methodology_profile_fail_closed.py`。
- 必须先写的 negative tests：profile 缺 `template_kind` / `documentation_density`、未知 `template_kind`、与 PackageContract `docs_required` 冲突必须失败；PackageContract 缺 `methodology_profile_ref` 必须失败。
- 必须证明的 happy path：四种 `template_kind`（Minimal / Agile / Compliance / Hybrid）都可绑定 PackageContract 并影响 workspace docs template 选择。
- 验收口径：方法论决策可被合同表达；无 MethodologyProfile 的项目不能进入 BUILD。

### V2-010G: 合同 fixture 与 schema 文档化

- 状态：TODO
- 目标：提供 tiny proving scenario 所需的最小合同 fixture 和 schema 使用示例。
- 输入文档：`proving-scenario-tiny-fullstack.md`。
- 依赖：V2-010F。
- 输出文件：`tests/fixtures/contracts/tiny_fullstack_contract.py` 或等价测试 fixture；必要时更新 `doc/04-implementation/acceptance-criteria.md`。
- 必须先写的 negative tests：fixture 不能省略 blocking evidence；不能把 fallback 标为 implementation evidence；fixture 的 acceptance_ref 与 `acceptance-criteria.md` 中任何 AC-V2 抽象 AC **未显式绑定** 时必须失败。
- 必须证明的 happy path：fixture 可被 V2-020 ticket graph 测试复用；fixture 中每个 acceptance_ref 都映射到 active AcceptanceContract 中的具体 criterion。
- 验收口径：V2-010 完成后，V2-020 可直接消费合同对象，不再重新解释散文需求；fixture 与 `acceptance-criteria.md` 形成强绑定，避免 fixture 静悄悄背离 AC。

---

## V2-020: Event + Reducer Kernel（事件与状态归约内核）

- 状态：TODO
- 目标：实现 event record（事件记录）、event log abstraction（事件日志抽象）、ticket graph projection（任务图投影）和 reducer（状态归约器）。
- 输入文档：`technical-architecture.md`、`domain-model.md`、`execution-and-runtime-boundary.md`。
- 输出目录：`src/boardroom_os/events/`、`src/boardroom_os/reducers/`、`src/boardroom_os/graph/`、`tests/reducers/`。
- 顶层验收口径：invalid transition fail closed；executor 不能直接完成 ticket；graph version 可追踪；replay projection 可重建状态。

### V2-020A: 定义 typed event record

- 状态：TODO
- 目标：定义所有可进入 event log 的最小事件类型和公共字段。
- 输入文档：`domain-model.md`、`process-audit-and-replay.md`。
- 依赖：V2-010E。
- 输出文件：`src/boardroom_os/events/record.py`、`src/boardroom_os/events/types.py`、`tests/reducers/test_event_record.py`。
- 必须先写的 negative tests：事件缺 actor、timestamp、graph_version、payload refs 必须失败。
- 必须证明的 happy path：事件可稳定序列化并保留 causation/correlation refs。
- 验收口径：audit/replay 不依赖未结构化日志。

### V2-020B: 实现 in-memory event log 与 append 校验

- 状态：TODO
- 目标：提供最小 event log 接口，用于测试 reducer 和 replay。
- 输入文档：`technical-architecture.md`。
- 依赖：V2-020A。
- 输出文件：`src/boardroom_os/events/log.py`、`tests/reducers/test_event_log.py`。
- 必须先写的 negative tests：graph_version 回退、重复 event_id、未知 event_type 必须失败。
- 必须证明的 happy path：append 后可按 project_ref 和版本范围读取事件。
- 验收口径：后续 runtime 只能 append 事实事件，不能直接改 projection。

### V2-020C: 实现 TicketNode 与 TicketGraph projection

- 状态：TODO
- 目标：从事件构建 ticket graph（任务图）的当前状态。
- 输入文档：`domain-model.md`。
- 依赖：V2-020B。
- 输出文件：`src/boardroom_os/graph/ticket.py`、`src/boardroom_os/graph/projection.py`、`tests/reducers/test_ticket_graph_projection.py`。
- 必须先写的 negative tests：ticket 缺 acceptance_refs、source_surface_refs、evidence_obligations、allowed_write_set 必须无效。
- 必须证明的 happy path：合法 ticket 可进入 ready_queue，blocked ticket 不可执行。
- 验收口径：ticket graph 是流程状态源。

### V2-020D: 实现 reducer 状态转换

- 状态：TODO
- 目标：保护 ticket created、leased、work submitted、checked、completed、rework 等转换。
- 输入文档：`execution-and-runtime-boundary.md`、`contract-and-evidence-model.md`。
- 依赖：V2-020C。
- 输出文件：`src/boardroom_os/reducers/ticket_reducer.py`、`src/boardroom_os/reducers/errors.py`、`tests/reducers/test_ticket_reducer_transitions.py`、`tests/negative/test_executor_cannot_complete_ticket.py`。
- 必须先写的 negative tests：executor 提交 `TICKET_COMPLETED`、provider attempt count 为 0、checker blocker 未清除时完成 ticket 必须失败。
- 必须证明的 happy path：verified evidence complete + checker approved 时 reducer 产生 completed projection。
- 验收口径：executor/runtime 永远不能直接决定 ticket completed。

### V2-020E: 实现 seat assignment 事件入口

- 状态：TODO
- 目标：在图中表达 AgentSeatAssignment（席位分配），但不在此阶段调用 provider。
- 输入文档：`agent-team-model.md`。
- 依赖：V2-020D。
- 输出文件：`src/boardroom_os/graph/seat_assignment.py`、`tests/reducers/test_seat_assignment_projection.py`。
- 必须先写的 negative tests：ticket 无 owner_seat_ref、seat capability 与 ticket type 不匹配、seat 缺 model_execution_profile_ref 必须失败或保持 blocked。
- 必须证明的 happy path：CEO/architect/worker/checker seat 可被分配到不同 ticket。
- 验收口径：V2-030 能基于 seat assignment 编译 ExecutionPackage。

### V2-020F: 实现 projection replay

- 状态：TODO
- 目标：证明 graph projection 可由 event log 重放生成。
- 输入文档：`process-audit-and-replay.md`。
- 依赖：V2-020E。
- 输出文件：`src/boardroom_os/graph/replay.py`、`tests/reducers/test_projection_replay.py`。
- 必须先写的 negative tests：事件缺失、事件乱序、projection version 不匹配必须失败。
- 必须证明的 happy path：同一事件序列重放得到同一 graph hash 或等价 projection summary。
- 验收口径：后续 closeout/replay 不依赖 runtime 内存状态。

---

## V2-030: Agent Seat + Execution Package Compiler（席位与执行包编译器）

- 状态：TODO
- 目标：实现 role（角色）、seat（席位）、skill binding（技能绑定）、ModelExecutionProfile（模型执行配置）和 ExecutionPackage（执行包）编译。
- 输入文档：`agent-team-model.md`、`execution-and-runtime-boundary.md`、`technical-architecture.md`。
- 输出目录：`src/boardroom_os/agents/`、`src/boardroom_os/execution/`、`tests/execution/`、`tests/negative/`。
- 顶层验收口径：缺 acceptance refs、allowed write set、evidence obligations、seat_ref 或 model_execution_profile 时 execution package 无效；role/provider 接入链清晰可测。

### V2-030A: 定义 RoleProfile、SkillBinding、ModelExecutionProfile

- 状态：TODO
- 目标：把角色职责、技能能力和 provider/model/effort 配置拆开表达。
- 输入文档：`agent-team-model.md`。
- 依赖：V2-020E。
- 输出文件：`src/boardroom_os/agents/profiles.py`、`src/boardroom_os/agents/skills.py`、`tests/execution/test_agent_profiles.py`。
- 必须先写的 negative tests：role 直接包含 provider credential、skill 绑定未知 role、model profile 缺 provider/model 必须失败。
- 必须证明的 happy path：同一 RoleProfile 可绑定不同 ModelExecutionProfile 形成不同 seat。
- 验收口径：role 不直接调用 provider；provider 通过 ModelExecutionProfile 接入。

### V2-030B: 定义 AgentSeat 与 seat policy

- 状态：TODO
- 目标：表达项目中被 CEO 激活的具体 seat，并校验 seat 能力边界。
- 输入文档：`agent-team-model.md`、`domain-model.md`。
- 依赖：V2-030A。
- 输出文件：`src/boardroom_os/agents/seat.py`、`src/boardroom_os/agents/policy.py`、`tests/execution/test_agent_seat_policy.py`。
- 必须先写的 negative tests：worker seat 缺 allowed capability、checker seat 与 worker seat 相同且无独立验证边界、seat 缺 model_execution_profile_ref 必须失败。
- 必须证明的 happy path：CEO、Architect、Worker、Checker seats 可被创建并映射到 ticket 类型。
- 验收口径：seat 是 role/provider/context 的接合点。

### V2-030C: 定义 ExecutionPackage schema

- 状态：TODO
- 目标：实现 worker/checker 执行前必须接收的结构化执行包。
- 输入文档：`execution-and-runtime-boundary.md`、`domain-model.md`。
- 依赖：V2-030B。
- 输出文件：`src/boardroom_os/execution/package.py`、`tests/execution/test_execution_package_schema.py`、`tests/negative/test_execution_package_fail_closed.py`。
- 必须先写的 negative tests：缺 ticket_id、graph_version、seat_ref、model_execution_profile、acceptance_refs、allowed_write_set、evidence_obligations、fallback_policy 必须失败。
- 必须证明的 happy path：ready ticket + active contracts + seat assignment 可形成完整 ExecutionPackage。
- 验收口径：worker 不接收散文任务；必须接收结构化执行包。

### V2-030D: 实现 ExecutionPackage compiler

- 状态：TODO
- 目标：从 ready ticket、active contracts、workspace manifest 和 seat assignment 编译执行包。
- 输入文档：`technical-architecture.md`、`generated-project-workspace.md`。
- 依赖：V2-030C。
- 输出文件：`src/boardroom_os/execution/compiler.py`、`tests/execution/test_execution_package_compiler.py`。
- 必须先写的 negative tests：ticket not ready、acceptance_ref 不属于 active contract、write set 超出 source surface、seat capability 不匹配必须失败。
- 必须证明的 happy path：tiny backend worker ticket 能编译出含 commands、context_refs、allowed_write_set、evidence_obligations 的 package。
- 验收口径：V2-040 runtime 只消费执行包，不重新解释治理状态。

### V2-030E: 实现 fallback policy 分类

- 状态：TODO
- 目标：把 fallback 明确分类，防止 fallback 被误当 implementation evidence。
- 输入文档：`execution-and-runtime-boundary.md`。
- 依赖：V2-030D。
- 输出文件：`src/boardroom_os/execution/fallback.py`、`tests/execution/test_fallback_policy.py`、`tests/negative/test_fallback_cannot_satisfy_implementation.py`。
- 必须先写的 negative tests：`PROVIDER_UNAVAILABLE`、`TEST_ONLY_SIMULATION`、`DETERMINISTIC_GOVERNANCE_DRAFT` 满足 implementation evidence 必须失败。
- 必须证明的 happy path：`CONTRACT_ALLOWED_DETERMINISTIC_TRANSFORM` 只能满足合同显式允许的 deterministic evidence。
- 验收口径：旧系统 fallback success 不可复活。

### V2-030F: 生成 agent context index 草稿

- 状态：TODO
- 目标：为 process audit 记录每次 agent attempt 接收的上下文、约束和模型配置。
- 输入文档：`process-audit-and-replay.md`。
- 依赖：V2-030D。
- 输出文件：`src/boardroom_os/execution/context_index.py`、`tests/execution/test_agent_context_index.py`。
- 必须先写的 negative tests：缺 execution_package_ref、model_execution_profile、allowed_write_set 或 provider_attempt_ref 的 context entry 不能进入最终 audit。
- 必须证明的 happy path：execution package 可生成可审计的 context index entry。
- 验收口径：后续 process audit 能回答“agent 接收了什么上下文”。

---

## V2-040: Runtime Executor + Provider + Command Runner（运行时执行器、模型调用与命令证据）

- 状态：TODO
- 目标：实现 provider attempt（模型调用尝试记录）、provider adapter boundary（供应商适配边界）、runtime executor（运行时执行器）和 command runner（命令执行器）。
- 输入文档：`execution-and-runtime-boundary.md`、`TEST_CONVENTIONS.md`。
- 输出目录：`src/boardroom_os/providers/`、`src/boardroom_os/adapters/`、`src/boardroom_os/execution/`、`tests/execution/`、`tests/negative/`。
- 顶层验收口径：zero provider attempt 必须阻断 implementation ticket；command evidence 必须来自 runner；runtime 只记录事实不做治理判断。

### V2-040A: 定义 ProviderAdapter 与 ProviderAttempt

- 状态：TODO
- 目标：建立 provider 调用接口和 attempt record，不接入真实外部模型也能 fake transport（模拟传输）测试。
- 输入文档：`execution-and-runtime-boundary.md`、`agent-team-model.md`。
- 依赖：V2-030C。
- 输出文件：`src/boardroom_os/providers/adapter.py`、`src/boardroom_os/providers/attempt.py`、`tests/execution/test_provider_attempt.py`。
- 必须先写的 negative tests：attempt 缺 provider、model、input_package_ref、seat_ref、status 必须失败。
- 必须证明的 happy path：fake provider transport 产生 attempt record、raw output ref 和 parsed output ref。
- 验收口径：provider attempt 可追踪到 ExecutionPackage 和 AgentSeat。

### V2-040B: 实现 provider executor boundary

- 状态：TODO
- 目标：runtime 通过 ExecutionPackage 调用 provider，不能直接从 role 或 ticket 调用 provider。
- 输入文档：`execution-and-runtime-boundary.md`。
- 依赖：V2-040A。
- 输出文件：`src/boardroom_os/execution/provider_executor.py`、`tests/execution/test_provider_executor.py`、`tests/negative/test_provider_executor_requires_execution_package.py`。
- 必须先写的 negative tests：缺 execution package、package 缺 model_execution_profile、seat/provider 不匹配时不得调用 provider。
- 必须证明的 happy path：合法 execution package 调用 fake provider 并记录 attempt。
- 验收口径：role/provider 接入路径闭合：RoleProfile -> AgentSeat -> ModelExecutionProfile -> ExecutionPackage -> ProviderAttempt。

### V2-040C: 实现 WorkProduct 解析和提交事件

- 状态：TODO
- 目标：把 provider raw output 转成 WorkProduct（工作产物）并提交 `WORK_PRODUCT_SUBMITTED` 事实事件。
- 输入文档：`domain-model.md`、`execution-and-runtime-boundary.md`。
- 依赖：V2-040B。
- 输出文件：`src/boardroom_os/execution/work_product.py`、`tests/execution/test_work_product_submission.py`。
- 必须先写的 negative tests：WorkProduct 缺 producer_attempt_ref、artifact_refs 或 claim_refs 时不得用于 evidence。
- 必须证明的 happy path：fake provider 输出可生成 WorkProduct，并附带 producer attempt。
- 验收口径：runtime 只提交 work product 事实，不完成 ticket。

### V2-040D: 实现 CommandRunner

- 状态：TODO
- 目标：真实运行 declared commands 并记录 VerificationRun（验证运行）。
- 输入文档：`execution-and-runtime-boundary.md`、`TEST_CONVENTIONS.md`。
- 依赖：V2-030D。
- 输出文件：`src/boardroom_os/adapters/process_runner.py`、`src/boardroom_os/execution/verification_run.py`、`tests/execution/test_command_runner.py`。
- 必须先写的 negative tests：合成 verification success、缺 stdout/stderr refs、缺 exit_code、命令不在 package contract 中必须失败。
- 必须证明的 happy path：运行一个本地确定性命令并捕获 exit code/stdout/stderr/duration。
- 验收口径：command evidence 唯一可信来源是 runner。

### V2-040E: 实现 runtime executor 事实事件边界

- 状态：TODO
- 目标：限制 runtime 只能 emit execution/provider/tool/command/work product 事实事件。
- 输入文档：`execution-and-runtime-boundary.md`。
- 依赖：V2-040C、V2-040D。
- 输出文件：`src/boardroom_os/execution/runtime_executor.py`、`tests/execution/test_runtime_executor_boundary.py`、`tests/negative/test_runtime_cannot_govern.py`。
- 必须先写的 negative tests：runtime emit `TICKET_COMPLETED`、`PROJECT_COMPLETED`、`CLOSEOUT_COMMITTED` 必须失败。
- 必须证明的 happy path：runtime 对 ready execution package 可记录 provider attempt、work product 和 command run。
- 验收口径：runtime bounded 约束可由测试证明。

---

## V2-050: Evidence Verifier + Checker + Rework（证据验证、检查与返工）

- 状态：TODO
- 目标：实现 evidence claim（证据声明）、evidence verifier（证据验证器）、final evidence table（最终证据表）、checker verdict（检查结论）和 rework ticket（返工任务）触发。
- 输入文档：`contract-and-evidence-model.md`、`agent-team-model.md`。
- 输出目录：`src/boardroom_os/evidence/`、`src/boardroom_os/checker/`、`tests/evidence/`、`tests/negative/`。
- 顶层验收口径：missing evidence -> REWORK_REQUIRED；checker notes 不能覆盖 blocker；source inventory ref-only 不能 closeout。

### V2-050A: 实现 EvidenceClaim

- 状态：TODO
- 目标：表达 producer 对 source/test/run/integration/closeout evidence 的声明。
- 输入文档：`contract-and-evidence-model.md`。
- 依赖：V2-040C、V2-040D。
- 输出文件：`src/boardroom_os/evidence/claim.py`、`tests/evidence/test_evidence_claim.py`。
- 必须先写的 negative tests：claim 缺 producer_attempt_ref、acceptance_refs、source_surface_refs、artifact_refs 必须失败。
- 必须证明的 happy path：WorkProduct 和 VerificationRun 可生成 EvidenceClaim。
- 验收口径：claim 不是 verified evidence。

### V2-050B: 实现 artifact/hash/provider/command evidence verifier

- 状态：TODO
- 目标：验证 artifact 存在性、hash 稳定性、producer attempt、command run 和 active contract refs。
- 输入文档：`contract-and-evidence-model.md`。
- 依赖：V2-050A。
- 输出文件：`src/boardroom_os/evidence/verifier.py`、`tests/evidence/test_evidence_verifier.py`、`tests/negative/test_synthetic_evidence_rejected.py`。
- 必须先写的 negative tests：synthetic verification、provider zero-attempt、artifact 缺 hash、acceptance_ref 不属于 active contract 必须失败。
- 必须证明的 happy path：真实 runner 记录 + provider attempt + artifact hash 可转为 verified evidence。
- 验收口径：verified evidence table 不能由 claim 直接替代。

### V2-050C: 实现 FinalEvidenceTable

- 状态：TODO
- 目标：按 active AcceptanceContract 汇总 satisfied/failed/missing 状态。
- 输入文档：`contract-and-evidence-model.md`、`acceptance-criteria.md`。
- 依赖：V2-050B。
- 输出文件：`src/boardroom_os/evidence/table.py`、`tests/evidence/test_final_evidence_table.py`、`tests/negative/test_missing_acceptance_map_blocks_closeout.py`。
- 必须先写的 negative tests：acceptance map 为空、blocking criterion missing、failed evidence 被 notes 覆盖必须失败。
- 必须证明的 happy path：所有 blocking criteria 都有 verified_evidence_refs 时 table complete。
- 验收口径：closeout 只消费 complete final evidence table。

### V2-050D: 实现 CheckerVerdict

- 状态：TODO
- 目标：让 checker 独立消费 work product、source diff、verified evidence 和 contracts，输出 verdict。
- 输入文档：`agent-team-model.md`、`contract-and-evidence-model.md`。
- 依赖：V2-050C。
- 输出文件：`src/boardroom_os/checker/verdict.py`、`src/boardroom_os/checker/checker.py`、`tests/evidence/test_checker_verdict.py`。
- 必须先写的 negative tests：verified evidence incomplete 但 checker approved、notes 覆盖 blocker、checker 自行补 evidence 必须失败。
- 必须证明的 happy path：evidence complete 时 checker 可 APPROVED 或 APPROVED_WITH_NON_BLOCKING_NOTES。
- 验收口径：checker 不能替 verifier 放行。

### V2-050E: 实现 rework ticket 触发

- 状态：TODO
- 目标：把 checker blocker 和 evidence gaps 转换成 graph 中的 rework ticket。
- 输入文档：`agent-team-model.md`、`domain-model.md`。
- 依赖：V2-050D、V2-020D。
- 输出文件：`src/boardroom_os/checker/rework.py`、`tests/evidence/test_rework_ticket_generation.py`。
- 必须先写的 negative tests：blocking gap 不生成 rework、rework ticket 缺 acceptance_refs/evidence_obligations 必须失败。
- 必须证明的 happy path：missing test evidence 生成绑定原 ticket 的 rework ticket。
- 验收口径：缺口在 checker/rework 阶段暴露，不留到 closeout 首次发现。

### V2-050F: evidence 与 reducer 集成门禁

- 状态：TODO
- 目标：把 verified evidence + checker verdict 接入 reducer 的 ticket completion gate。
- 输入文档：`execution-and-runtime-boundary.md`、`contract-and-evidence-model.md`。
- 依赖：V2-050E、V2-020D。
- 输出文件：`src/boardroom_os/reducers/completion_gate.py`、`tests/reducers/test_completion_gate_with_evidence.py`。
- 必须先写的 negative tests：checker approved 但 evidence table missing、evidence complete 但 checker blocker、attempt count 为 0 必须阻断 completion。
- 必须证明的 happy path：evidence complete + checker approved + provider attempts recorded 时 reducer 可完成 ticket。
- 验收口径：ticket completion 不由 runtime 或 checker 单独决定。

---

## V2-060: Workspace + Package Assembler（工作区与项目包装配器）

- 状态：TODO
- 目标：生成目标项目 workspace、run manifest、package contract 文件、source inventory 和最终 package assembly。
- 输入文档：`generated-project-workspace.md`、`contract-and-evidence-model.md`。
- 输出目录：`src/boardroom_os/workspace/`、`tests/proving/`、`tests/negative/`。
- 顶层验收口径：source inventory 来自 package root + git/hash，不来自 payload 猜测；最终产物是 generated project package。

### V2-060A: 实现 workspace manifest

- 状态：TODO
- 目标：表达 `00-boardroom`、`10-project`、`20-evidence`、`30-audit` 的逻辑结构，但不把它误作本 repo 结构。
- 输入文档：`generated-project-workspace.md`。
- 依赖：V2-010D。
- 输出文件：`src/boardroom_os/workspace/manifest.py`、`tests/proving/test_workspace_manifest.py`。
- 必须先写的 negative tests：package root 不在 workspace 内、缺 10-project、缺 20-evidence 必须失败。
- 必须证明的 happy path：tiny workspace manifest 可定位 package root、evidence root、audit root。
- 验收口径：workspace 是 generated project 的 staging area，不是框架源码布局。

### V2-060B: 实现 package assembler

- 状态：TODO
- 目标：把 source surfaces、docs、run manifest、package contract 装配到 `10-project`。
- 输入文档：`generated-project-workspace.md`、`PackageContract`。
- 依赖：V2-060A。
- 输出文件：`src/boardroom_os/workspace/assembler.py`、`tests/proving/test_package_assembler.py`。
- 必须先写的 negative tests：缺 package-contract.json、缺 run-manifest.json、source 写到 package root 外必须失败。
- 必须证明的 happy path：tiny package 包含 README、AGENTS、package-contract、run-manifest、src/tests 或 backend/frontend/tests。
- 验收口径：交付物是 package，不是离散文件列表。

### V2-060C: 实现 source inventory builder

- 状态：TODO
- 目标：从 package root 和 git/hash 构建 SourceInventory（源码清单）。
- 输入文档：`contract-and-evidence-model.md`。
- 依赖：V2-060B、V2-050B。
- 输出文件：`src/boardroom_os/workspace/source_inventory.py`、`tests/proving/test_source_inventory.py`、`tests/negative/test_source_inventory_ref_only_rejected.py`。
- 必须先写的 negative tests：只证明 ref 存在、缺 sha256、缺 producer_ticket_ref、缺 producer_attempt_ref、缺 acceptance_refs、缺 evidence_refs 必须失败。
- 必须证明的 happy path：package root 内文件可映射到 source_surface、producer ticket、attempt 和 evidence。
- 验收口径：source inventory 证明 implementation lineage（实现来源链路）。

### V2-060D: 实现 run manifest 与 command binding

- 状态：TODO
- 目标：把 package contract 的 run/test commands 落到 run manifest，并供 CommandRunner 校验。
- 输入文档：`generated-project-workspace.md`、`execution-and-runtime-boundary.md`。
- 依赖：V2-060B、V2-040D。
- 输出文件：`src/boardroom_os/workspace/run_manifest.py`、`tests/proving/test_run_manifest.py`。
- 必须先写的 negative tests：软件项目缺 run/test commands、runner 执行未声明命令、manifest 命令与 PackageContract 不一致必须失败。
- 必须证明的 happy path：declared command 可被 runner 执行并生成 verification evidence。
- 验收口径：可运行软件项目必须有可验证 run/test commands。

### V2-060E: workspace/package 与 evidence 集成

- 状态：TODO
- 目标：把 source inventory、run manifest、verification runs 和 final evidence table 汇入 `20-evidence`。
- 输入文档：`generated-project-workspace.md`、`contract-and-evidence-model.md`。
- 依赖：V2-060C、V2-060D、V2-050C。
- 输出文件：`src/boardroom_os/workspace/evidence_export.py`、`tests/proving/test_workspace_evidence_export.py`。
- 必须先写的 negative tests：final evidence table 缺 blocking criterion、source inventory 缺 lineage、verification runs 缺 stdout/stderr refs 时不得导出 closeout-ready evidence。
- 必须证明的 happy path：`20-evidence` 形成可供 closeout 消费的 evidence bundle。
- 验收口径：package assembly 与 evidence assembly 同步，不允许先交付再补证据。

---

## V2-070: Closeout + Replay + Process Audit（收尾、重放与流程审计）

- 状态：TODO
- 目标：实现 closeout gate、replay bundle、process audit 和 git audit。
- 输入文档：`process-audit-and-replay.md`、`contract-and-evidence-model.md`。
- 输出目录：`src/boardroom_os/closeout/`、`src/boardroom_os/audit/`、`tests/closeout/`、`tests/negative/`。
- 顶层验收口径：缺 replay bundle 或 evidence map 不能 terminal success；process audit 能回答关键治理问题。

### V2-070A: 实现 closeout gate

- 状态：TODO
- 目标：检查 graph、source inventory、final evidence table、package contract、commands、provider attempts、git audit、replay、process audit。
- 输入文档：`contract-and-evidence-model.md`。
- 依赖：V2-050F、V2-060E。
- 输出文件：`src/boardroom_os/closeout/gate.py`、`tests/closeout/test_closeout_gate.py`、`tests/negative/test_closeout_fail_closed.py`。
- 必须先写的 negative tests：缺 replay bundle、缺 evidence map、open blocker、provider attempt count 为 0、git dirty 必须失败。
- 必须证明的 happy path：所有 gate 输入 ready 时 closeout verdict passed。
- 验收口径：closeout 只收束已证明事实。

### V2-070B: 实现 replay bundle builder

- 状态：TODO
- 目标：产出 event range、projection versions、artifact manifest、hash manifest 和 replay report。
- 输入文档：`process-audit-and-replay.md`。
- 依赖：V2-020F、V2-060E。
- 输出文件：`src/boardroom_os/audit/replay_bundle.py`、`tests/closeout/test_replay_bundle.py`。
- 必须先写的 negative tests：event range 缺失、projection version 不匹配、artifact hash 缺失、replay report 缺失必须失败。
- 必须证明的 happy path：事件 + artifact manifest 可重建 typed summary。
- 验收口径：缺 replay bundle 不允许 terminal success。

### V2-070C: 实现 process audit builder

- 状态：TODO
- 目标：生成人类可读 process audit（流程审计），解释需求、决策、角色、上下文、ticket、evidence 和 closeout。生成 `30-audit/` 全部 10 项产物。
- 输入文档：`process-audit-and-replay.md`。
- 依赖：V2-030F、V2-050C、V2-060E。
- 输出文件：`src/boardroom_os/audit/process_audit.py`、`tests/closeout/test_process_audit.py`、`tests/closeout/test_process_audit_artifacts.py`。
- 30-audit 必需产物（每项独立校验）：
  1. `process-audit.md`
  2. `timeline.json`
  3. `decision-log.md`
  4. `agent-context-index.json`
  5. `ticket-graph.md`
  6. `artifact-lineage.json`
  7. `evidence-map.json`
  8. `git-version-audit.md`
  9. `closeout-summary.md`
  10. `replay-bundle-report.json`
- 必须先写的 negative tests：
  - 上述 10 项产物中任意一项缺失必须失败（10 条独立用例）
  - `timeline.json` 缺关键事件（directive received / charter created / acceptance contract created / package contract created / seat assigned / ticket lifecycle / provider attempt / command run / evidence verified / checker verdict / closeout / replay）必须失败
  - `decision-log.md` 缺 CEO / human board 决策必须失败
  - `agent-context-index.json` 缺 `execution_package_ref` / `model_execution_profile` / `provider_attempt_ref` 必须失败
  - `artifact-lineage.json` 不能完整表达 `producer attempt -> artifact -> consumer ticket -> evidence claim -> verifier -> closeout` 链必须失败
  - `evidence-map.json` 与 final evidence table 不一致必须失败
  - `git-version-audit.md` 缺 final commit / dirty status / source inventory hash 必须失败
- 必须证明的 happy path：audit 能回答"谁做了什么决策、agent 收到什么上下文、哪些 evidence 满足哪些 acceptance、最终 git 状态是什么、replay 是否可重建"。10 项产物全部存在且互相一致。
- 验收口径：process audit 是产品能力，不是 raw event dump；10 项产物缺一不可，且必须互相一致。

### V2-070D: 实现 git version audit

- 状态：TODO
- 目标：记录 final package commit、dirty status、diff summary、source inventory hash 和 final command evidence。
- 输入文档：`process-audit-and-replay.md`。
- 依赖：V2-060C、V2-060D。
- 输出文件：`src/boardroom_os/adapters/git_audit.py`、`src/boardroom_os/audit/git_version_audit.py`、`tests/closeout/test_git_version_audit.py`。
- 必须先写的 negative tests：dirty package、source inventory hash 不匹配、final commands 不是最终 commit 运行必须失败。
- 必须证明的 happy path：clean package commit 可生成 git audit summary。
- 验收口径：closeout 可证明最终版本是什么。

### V2-070E: 实现 CloseoutPackage

- 状态：TODO
- 目标：把 closeout gate 结果、source inventory、evidence table、replay bundle 和 process audit 绑定为最终收尾包。
- 输入文档：`domain-model.md`、`contract-and-evidence-model.md`。
- 依赖：V2-070A、V2-070B、V2-070C、V2-070D。
- 输出文件：`src/boardroom_os/closeout/package.py`、`tests/closeout/test_closeout_package.py`。
- 必须先写的 negative tests：closeout package 缺任一必需 ref、verdict 与 gate 结果不一致必须失败。
- 必须证明的 happy path：passed closeout package 可指向完整 audit/evidence/replay/source inventory。
- 验收口径：最终完成只由 CloseoutPackage 表达。

### V2-070F: closeout reducer 集成

- 状态：TODO
- 目标：让 reducer 在 closeout gate passed 后产生 terminal success projection。
- 输入文档：`execution-and-runtime-boundary.md`、`process-audit-and-replay.md`。
- 依赖：V2-070E、V2-020D。
- 输出文件：`src/boardroom_os/reducers/closeout_reducer.py`、`tests/closeout/test_closeout_reducer.py`。
- 必须先写的 negative tests：runtime 直接 closeout、workflow completed 但 closeout gate missing、缺 replay bundle 必须失败。
- 必须证明的 happy path：CloseoutPackage passed 事件可投影为 project terminal success。
- 验收口径：不把 workflow completed 当作项目完成。

---

## V2-080: Tiny Full-stack Proving Scenario（端到端证明场景）

- 状态：TODO
- 目标：端到端生成 tiny book availability tracker，证明 contract-first、reducer-protected、evidence-backed、package-oriented、audit-readable、replayable 的闭环。
- 输入文档：`proving-scenario-tiny-fullstack.md` 和 V2-010~V2-070 产物。
- 输出目录：`tests/proving/`、generated workspace、closeout audit。
- 顶层验收口径：所有 proving scenario 验收项通过；负例覆盖伪交付无法通过。

### V2-080A: 定义 tiny scenario active contracts

- 状态：TODO
- 目标：为 tiny book availability tracker 生成 ProjectCharter、AcceptanceContract、PackageContract fixture。
- 输入文档：`proving-scenario-tiny-fullstack.md`、V2-010 产物。
- 依赖：V2-010G。
- 输出文件：`tests/proving/fixtures/tiny_fullstack_contracts.py`、`tests/proving/test_tiny_contracts.py`。
- 必须先写的 negative tests：缺 API/UI/persistence/run/test acceptance refs 时 scenario 无效。
- 必须证明的 happy path：active contracts 能覆盖 full-stack package 的 source surfaces 和 evidence obligations。
- 验收口径：scenario 不使用静态 universal AC。

### V2-080B: 生成 tiny ticket graph 与 seat assignment

- 状态：TODO
- 目标：创建 CEO/Architect/Worker/Checker seat 和 backend/frontend/test/docs ticket graph。
- 输入文档：V2-020、V2-030 产物。
- 依赖：V2-080A、V2-020F、V2-030B。
- 输出文件：`tests/proving/test_tiny_ticket_graph.py`。
- 必须先写的 negative tests：worker ticket 缺 owner seat、checker 与 worker 不独立、ticket 缺 evidence obligations 必须失败。
- 必须证明的 happy path：ticket graph ready queue 可按依赖推进。
- 验收口径：agent team 不是隐式 prompt，而是 graph + seat assignment。

### V2-080C: 执行 tiny implementation attempts

- 状态：TODO
- 目标：使用 fake provider transport 生成最小 backend/frontend/tests/docs work products，并记录 provider attempts。
- 输入文档：V2-040 产物。
- 依赖：V2-080B、V2-040E。
- 输出文件：`tests/proving/test_tiny_provider_attempts.py`。
- 必须先写的 negative tests：provider zero-attempt、fallback source delivery、placeholder source 必须不能完成 ticket。
- 必须证明的 happy path：每个 provider-backed implementation ticket 至少有一个 ProviderAttempt。
- 验收口径：模型调用尝试记录是 implementation evidence 链路的一部分。

### V2-080D: 运行 tiny command evidence 与 evidence verifier

- 状态：TODO
- 目标：运行 declared commands，生成 VerificationRun，并通过 EvidenceVerifier。
- 输入文档：V2-040、V2-050 产物。
- 依赖：V2-080C、V2-050F。
- 输出文件：`tests/proving/test_tiny_evidence_verification.py`。
- 必须先写的 negative tests：synthetic verification、missing acceptance map、checker notes 覆盖 blocker 必须失败。
- 必须证明的 happy path：真实 runner evidence 满足 active acceptance contract 的 blocking criteria。
- 验收口径：final evidence table complete。

### V2-080E: 装配 tiny package 与 source inventory

- 状态：TODO
- 目标：生成 package root、run manifest、source inventory 和 evidence bundle。
- 输入文档：V2-060 产物。
- 依赖：V2-080D、V2-060E。
- 输出文件：`tests/proving/test_tiny_package_assembly.py`。
- 必须先写的 negative tests：source inventory 只证明 ref、缺 run manifest、文件在 package root 外必须失败。
- 必须证明的 happy path：tiny generated project package 可定位源码、测试、文档、run manifest 和 evidence。
- 验收口径：最终交付物是 package。

### V2-080F: tiny closeout/replay/process audit

- 状态：TODO
- 目标：对 tiny scenario 产生 CloseoutPackage、ReplayBundle 和 ProcessAuditReport。
- 输入文档：V2-070 产物。
- 依赖：V2-080E、V2-070F。
- 输出文件：`tests/proving/test_tiny_closeout.py`。
- 必须先写的 negative tests：缺 replay bundle、缺 process audit、缺 git audit、workflow completed 替代 closeout 必须失败。
- 必须证明的 happy path：closeout passed，audit 可回答 timeline、agent decisions、context、artifacts、git history、evidence map。
- 验收口径：V2 的最小端到端能力成立。
