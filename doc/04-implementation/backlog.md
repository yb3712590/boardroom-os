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

**当前未完成工作包**：`V2-100F`（IN_PROGRESS，RunManifest tolerant ingestion and native rework orchestration，运行清单宽容摄取与原生返工编排；V2-100F-A/B/C/D 已完成，V2-100F-E/F 尚未实施；真实 V2-090F rerun 已证明 raw assertion enum（原始断言枚举）会阻断 ReworkRequest（返工请求）形成）

**当前重点**：2026-05-31 tiny-fullstack 失败复审撤回 Phase 8 “V2 最小端到端能力成立”结论。V2-080A~F 保留 `DONE` 作为历史工作包执行记录，但 V2-080 不再作为端到端验收依据。Phase 9 的因果链已明确：`V2-090K` 完成 agent team autonomy remediation（智能体团队自治整改），目标是移除 runner/helper（运行器/辅助器）对业务域、启动接口、静态验收引用和源码面映射的外部介入，让 agent-generated AcceptanceContract / PackageContract / RunManifest / BehavioralProbePlan（智能体生成验收合同 / 包合同 / 运行清单 / 行为探针计划）成为权威源；090K 后真实 provider full run（完整模型供应商运行）可以 fail closed（失败关闭）地暴露合同、实现、探针和收尾投影不一致，这不等同于 090K 未完成。V2-100A~E 已证明 CEO-governed rework loop（项目经理治理返工循环）可以在结构化 verified blocker（已验证阻塞项）存在时规划、返工、重验和收敛。2026-06-16 真实 V2-090F rerun rework-entry validation（重跑返工入口验证）进一步暴露新缺口：RunManifest assertion vocabulary（运行清单断言词汇）被当作封闭枚举处理，`json_array_contains_field` 这类模型自然输出会在 ingestion/normalization（摄取/归一化）阶段 raw crash（原始崩溃），导致无法形成 ReworkRequest。当前提升为 V2-100F，目标是实现 tolerant semantic ingestion（宽容语义摄取）和 native rework orchestration（原生返工编排）：unknown assertion（未知断言）不能通过、不能被忽略，也不能阻断 CEO-governed verify-blackbox ticket（项目经理治理黑盒验证工单）进入 TicketGraph / SeatAssignmentGraph / ExecutionPackage / ProviderAttempt（工单图 / 席位派工图 / 执行包 / 模型调用尝试记录）原生链路。`BlackboxVerificationPlan`（黑盒验证计划）替代 `RunManifest.behavioral_probes`（运行清单行为探针）的直接执行路径；具体实施者由 CEO 通过 TicketGraph/SeatDemand（工单图/席位需求）决定，不硬编码 Tester（测试者）。V2-090F golden sample（黄金样例）保持 REVIEW_REQUIRED / BLOCKED，等待 V2-100F 重写计划评审及实施。

**Phase 3 验收边界**：进度总览中的 `完成` 表示 V2-030A ~ V2-030F 工作包 6/6 已完成；V2-050B 已通过 EvidenceVerifier（证据验证器）实际消费 FallbackPolicyRegistry（降级策略注册表）与 FallbackDecisionRecord（降级判定记录）闭合 AC-V2-EXECUTION-003（fallback 不能满足 implementation evidence，降级不能满足实现证据）。

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
  -> V2-071 Closeout fact-chain hardening（事实链强化重构）
  -> V2-080 Tiny Full-stack Proving Scenario
  -> V2-090 Tiny Fullstack Blackbox Recovery（黑盒整改）
  -> V2-100 Agent-team Rework Loop Hardening（智能体团队返工循环强化）
```

关键接入链必须显式实现，不能靠散文约定。CEO / Architect / Worker / Tester / Checker / Closeout 都是 provider-backed agent role（模型支撑的智能体角色），均应通过 ExecutionPackage（执行包）接收上下文，通过 LLM（大模型）返回影响工作流的产物或判断；工具、validator（校验器）、reducer（归约器）和 gate（门禁）不代表 agent role。

```text
RoleProfile（角色模板）
  -> AgentSeat（项目席位）
  -> ModelExecutionProfile（provider/model/effort 配置）
  -> ExecutionPackage（执行包，携带 seat_ref 和 model_execution_profile）
  -> ProviderAttempt（模型调用尝试记录，绑定 execution_package_ref）
  -> WorkProduct（工作产物，绑定 producer_attempt_ref）
  -> EvidenceClaim（证据声明，绑定 producer_attempt_ref）
  -> FinalEvidenceTable（最终证据表）
  -> SourceInventory（源码清单，绑定 producer_ticket / attempt / evidence）
  -> CloseoutPackage（收尾包）
```

如果任一 implementation ticket（实施任务）需要 provider（模型供应商）但缺 `ModelExecutionProfile`、`AgentSeat`、`ExecutionPackage` 或 `ProviderAttempt` 绑定，必须 fail closed（失败关闭）。

## 进度总览

| 阶段 | 顶层任务 | 工作包完成/总数 | 状态 |
|---|---|---:|---|
| Phase 0：Foundation | V2-000, V2-001 | 4 / 4 | 完成 |
| Phase 1：Contract Kernel | V2-010 | 7 / 7 | 完成 |
| Phase 2：Event + Reducer Kernel | V2-020 | 6 / 6 | 完成 |
| Phase 3：Agent + Execution Package | V2-030 | 6 / 6 | 完成 |
| Phase 4：Runtime + Provider + Runner | V2-040 | 5 / 5 | 完成 |
| Phase 5：Evidence + Checker | V2-050 | 7 / 7 | 完成 |
| Phase 6：Workspace + Package | V2-060 | 6 / 6 | 完成 |
| Phase 7：Closeout + Replay + Audit | V2-070 | 6 / 6 | 完成 |
| Phase 7.5：Closeout fact-chain 重构 | V2-071 | 6 / 6 | 完成 |
| Phase 8：Tiny proving scenario | V2-080 | 6 / 6 | 失败复审后结束；不作为端到端成立证据 |
| Phase 9：Tiny blackbox recovery | V2-090 | 10 / 11 | 部分闭合；V2-090K 完成自治整改并保留 fail-closed 现场，V2-090F golden sample 仍 REVIEW_REQUIRED / BLOCKED |
| Phase 10：Agent-team rework loop hardening | V2-100 | 5 / 6 | V2-100A~E 完成；V2-100F IN_PROGRESS（A/B/C/D 完成，E/F 待实施） |
| **合计** | **V2-000 ~ V2-100** | **74 / 76** | **V2-090A ~ V2-090E、V2-090G、V2-090H、V2-090I、V2-090J、V2-090K 与 V2-100A/B/C/D/E 完成；V2-100F IN_PROGRESS；V2-090F REVIEW_REQUIRED / BLOCKED** |

## 当前约束摘要

- Contract first：implementation ticket 前必须有 active AcceptanceContract（验收合同）和 PackageContract（包合同）。
- Reducer first：关键状态变更必须通过 reducer（状态归约器）或 validator（校验器）。
- Evidence first：没有真实 evidence（证据）不得 closeout（收尾）。
- Runtime bounded：runtime（运行时）只执行、记录、校验、投影事实，不做 CEO / architect / checker / closeout 决策。
- Rework governed：返工循环必须由 CEO（项目经理/治理角色）读取 verified blocker（已验证阻塞项）后规划，并通过 TicketGraph（工单图）和 reducer（归约器）推进；runtime / atomic-agent completed（运行时 / 原子智能体完成）不能直接关闭返工。
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

- 状态：DONE
- 目标：人工审阅本基座，确认是否作为新 clean foundation 的实施起点。
- 输入文档：全部 Phase 0 文档。
- 输出文件：必要修订（已完成：见 DEC-0008、backlog 扩展、分批验收）。
- 验收口径：用户确认目录、文档职责、legacy boundary、工作包拆解和后续路线（2026-05-14 用户确认）。

### V2-001A: Phase 0 完整性审计

- 状态：DONE
- 目标：逐项确认 Phase 0 完成标准是否被当前文件覆盖。
- 输入文档：`doc/04-implementation/phase-0-plan.md`、`doc/04-implementation/acceptance-criteria.md`、`doc/05-project-log/decisions.md`。
- 依赖：V2-000。
- 输出文件：`doc/04-implementation/backlog.md`、必要时更新 `doc/05-project-log/2026-05.md`。
- 必须先写的 negative tests：无代码；文档审计必须列出任何缺失项，不能把"文档存在"自动等同于"职责完整"。
- 必须证明的 happy path：Phase 0 完成标准 10 项均可映射到现有文档或明确后续任务。
- 验收口径：V2-001 是否可以进入用户确认状态有明确依据。
- 完成证据：2026-05-14 独立架构审计完成，识别 4 项阻塞缺口 + 1 项幂等性缺口，全部映射到具体修复任务（DEC-0008 / V2-010B / V2-010F / V2-070C 拆分 / acceptance-criteria 分批验收 / 幂等更新协议）。

### V2-001B: 工作包计划审计

- 状态：DONE
- 目标：确认每个后续里程碑都拆成可实施工作包，且每包有输入、输出、负例、正例和验收。
- 输入文档：本文件、`doc/03-architecture/technical-architecture.md`、`doc/03-architecture/agent-team-model.md`。
- 依赖：V2-001A。
- 输出文件：`doc/04-implementation/backlog.md`。
- 必须先写的 negative tests：无代码；审计必须标记任何"只有阶段名、没有可落地文件和测试"的任务。
- 必须证明的 happy path：后续 worker 可以从任意 `TODO` 工作包知道要读什么、写什么、测什么。
- 验收口径：backlog 不再只是 8 步阶段索引，而是可执行 work package plan（工作包计划）。
- 完成证据：51 个工作包均具备 ID / 状态 / 目标 / 输入 / 依赖 / 输出 / negative tests / happy path / 验收口径 九项要素；幂等更新协议接入；V2-070C 已拆为 10 项 30-audit 产物逐项负例。

### V2-001C: Phase 0 用户确认与冻结

- 状态：DONE
- 目标：拿到用户对 Phase 0 和 backlog 工作包拆解的确认。
- 输入文档：本文件、`doc/04-implementation/acceptance-criteria.md`。
- 依赖：V2-001B。
- 输出文件：`doc/05-project-log/2026-05.md`。
- 必须先写的 negative tests：无代码；不得在用户确认前宣称 Phase 0 已可进入实现阶段。
- 必须证明的 happy path：用户确认后，V2-010 可以作为第一个代码实施子项目启动。
- 验收口径：V2-001 状态可改为 DONE，下一包为 V2-010A。
- 完成证据：2026-05-14 用户在审阅独立审计、修复改动和提交 `578c7a8` 后，明确指示推进工作包状态；Phase 0 冻结，V2-010A 开放。

---

## V2-010: Contract Kernel（合同内核）

- 状态：DONE
- 目标：实现 ProjectCharter、AcceptanceContract、PackageContract、SourceSurface、EvidenceObligation 的最小 typed schema（类型化结构）和 fail-closed 校验。
- 输入文档：`doc/03-architecture/domain-model.md`、`doc/03-architecture/contract-and-evidence-model.md`、`doc/04-implementation/acceptance-criteria.md`。
- 输出目录：`src/boardroom_os/contracts/`、`tests/contracts/`、`tests/negative/`。
- 顶层验收口径：schema validation tests 通过；缺 active AcceptanceContract 或 PackageContract 的 implementation ticket 无效；static universal AC 不能替代动态合同。

### V2-010A: 建立 contracts 包和基础值对象

- 状态：DONE
- 目标：创建合同模块的包结构、基础枚举、ID 类型和值对象。
- 输入文档：`domain-model.md`。
- 依赖：V2-001C。
- 输出文件：`src/boardroom_os/contracts/__init__.py`、`src/boardroom_os/contracts/types.py`、`tests/contracts/test_contract_types.py`。
- 必须先写的 negative tests：空 ID、空 acceptance refs、未知状态必须校验失败。
- 必须证明的 happy path：合法 ID、状态、引用集合可构造并序列化。
- 验收口径：后续 schema 不直接使用裸 dict 表达核心字段。
- 完成证据：2026-05-14 采用 Pydantic model（Pydantic 模型）实现冻结值对象；`PYTHONPATH=src pytest tests/contracts/test_contract_types.py` 通过（4 passed）。

### V2-010B: 实现 BoardDirective intake

- 状态：DONE
- 目标：把用户原始需求（自然语言、PRD 文件、人审反馈）落地为 typed BoardDirective，作为合同链入口。
- 输入文档：`domain-model.md`、`process-audit-and-replay.md`。
- 依赖：V2-010A。
- 输出文件：`src/boardroom_os/contracts/directive.py`、`src/boardroom_os/contracts/project.py`、`tests/contracts/test_board_directive.py`、`tests/negative/test_board_directive_fail_closed.py`。
- 必须先写的 negative tests：directive 缺 `source_type` / `content_ref` / `received_at` / `requester_ref` 必须失败；未知 `source_type` 必须失败；ProjectCharter 引用不存在的 directive 必须失败。
- 必须证明的 happy path：三种 `source_type`（`natural_language` / `prd_file` / `human_review_update`）的 directive 都可构造、序列化并被 ProjectCharter 引用。
- 验收口径：合同链入口闭合 —— 不存在 BoardDirective 不得创建 ProjectCharter。
- 完成证据：2026-05-14 新增 BoardDirective（董事会指令）、DirectiveRegistry（指令注册表）和 ProjectCharter（项目章程）入口校验；补充 fail-closed 校验，要求 ProjectCharter 公开构造也必须携带 directive registry 上下文，并拒绝无时区 received_at 与未知字段；`PYTHONPATH=src pytest tests/contracts/test_board_directive.py tests/negative/test_board_directive_fail_closed.py` 通过（15 passed）；`PYTHONPATH=src pytest tests/contracts tests/negative` 通过（19 passed）。

### V2-010C: 实现 ProjectCharter 与 AcceptanceContract

- 状态：DONE
- 目标：表达项目章程和动态验收合同。
- 输入文档：`domain-model.md`、`contract-and-evidence-model.md`。
- 依赖：V2-010B。
- 输出文件：`src/boardroom_os/contracts/acceptance.py`、`tests/contracts/test_acceptance_contract.py`、`tests/negative/test_acceptance_contract_fail_closed.py`。
- 修改文件：`src/boardroom_os/contracts/project.py`（V2-010B 已建立，V2-010C 仅扩展 charter 校验如需）。
- 必须先写的 negative tests：空 criteria、非 blocking criteria 全覆盖、criterion 缺 evidence_required、criterion 缺 source_surface_refs、charter 缺 board_directive_ref 必须失败。
- 必须证明的 happy path：动态 criteria 可绑定 ProjectCharter，并能查询 blocking criteria。
- 验收口径：implementation ticket 不能用固定静态 AC 列表绕过 active AcceptanceContract。
- 完成证据：2026-05-14 新增 AcceptanceContract（验收合同）、AcceptanceCriterion（验收项）、ProjectCharterRegistry（项目章程注册表）、EvidenceRequirement（证据要求）和 VerificationStrategy（验证策略）；动态 criteria 必须绑定已注册 ProjectCharter，并且只有 active AcceptanceContract 暴露 blocking criteria；`PYTHONPATH=src pytest tests/negative/test_acceptance_contract_fail_closed.py` 通过（7 passed）；`PYTHONPATH=src pytest tests/contracts/test_acceptance_contract.py` 通过（4 passed）；`PYTHONPATH=src pytest tests/contracts tests/negative` 通过（30 passed）。

### V2-010D: 实现 PackageContract 与 SourceSurface

- 状态：DONE
- 目标：定义最终 generated project package（生成项目包）的目录、运行命令、测试命令、source surfaces（源码实现面）和 integration boundaries（集成边界）。
- 输入文档：`contract-and-evidence-model.md`、`generated-project-workspace.md`。
- 依赖：V2-010C。
- 输出文件：`src/boardroom_os/contracts/package.py`、`src/boardroom_os/contracts/source_surface.py`、`tests/contracts/test_package_contract.py`、`tests/negative/test_package_contract_fail_closed.py`。
- 必须先写的 negative tests：缺 package_root、缺 source_surfaces、软件项目缺 run/test commands、surface 无 acceptance_refs 必须失败。
- 必须证明的 happy path：一个 tiny full-stack package contract 能声明 backend、frontend、tests、docs、run manifest surfaces。
- 验收口径：最终交付被约束为 package，不是散落 source artifacts。
- 完成证据：2026-05-14 新增 PackageContract（包合同）、PackageProjectType（包项目类型）、PackageCommand（包命令）、IntegrationBoundary（集成边界）和 SourceSurface（源码实现面）；`software` / `mixed` 包缺 run/test commands 必须失败，SourceSurface 缺 paths 或 acceptance_refs 必须失败，并补充 unknown fields（未知字段）与 strict bool（严格布尔）fail-closed 校验；`PYTHONPATH=src pytest tests/contracts/test_package_contract.py tests/negative/test_package_contract_fail_closed.py -v` 通过（15 passed）；`PYTHONPATH=src pytest tests/contracts tests/negative -v` 通过（46 passed）。

### V2-010E: 实现 EvidenceObligation 与 contract gate

- 状态：DONE
- 目标：把 acceptance criteria 转换成 ticket/execution 必须满足的 evidence obligations（证据义务）。
- 输入文档：`contract-and-evidence-model.md`、`acceptance-criteria.md`。
- 依赖：V2-010D。
- 输出文件：`src/boardroom_os/contracts/evidence_obligation.py`、`src/boardroom_os/contracts/gates.py`、`tests/contracts/test_evidence_obligation.py`、`tests/negative/test_contract_gate.py`。
- 必须先写的 negative tests：缺 active acceptance contract、缺 package contract、acceptance_ref 不属于 active contract、obligation 不 blocking 但对应 blocking criterion 必须失败。
- 必须证明的 happy path：从 active contracts 生成完整 obligation set。
- 验收口径：后续 ticket graph 创建 implementation ticket 前可调用 contract gate。
- 完成证据：2026-05-14 新增 EvidenceObligation（证据义务）、ContractGateResult（合同门禁结果）、compile_evidence_obligations（证据义务编译函数）和 validate_contract_gate（合同门禁校验函数）；按 blocking criterion × evidence_required 展开 obligation，并 fail closed 拒绝 inactive acceptance contract、缺 package contract、acceptance_ref 不属于 active contract、blocking criterion 无 blocking obligation、显式传入的 obligation set 与 active contract 不一致、criterion 引用不存在 source surface；`PYTHONPATH=src pytest tests/contracts/test_evidence_obligation.py tests/negative/test_contract_gate.py -q` 通过（10 passed）；`PYTHONPATH=src pytest tests/contracts tests/negative -q` 通过（56 passed）。

### V2-010F: 实现 MethodologyProfile 与 workspace template 绑定

- 状态：DONE
- 目标：把 CEO 选择的方法论（Minimal / Agile / Compliance / Hybrid）落地为 typed MethodologyProfile，并与 PackageContract、生成项目 docs template 绑定。
- 输入文档：`agent-team-model.md`、`generated-project-workspace.md`、`02-solution/construction-plan.md`。
- 依赖：V2-010E。
- 输出文件：`src/boardroom_os/contracts/methodology.py`、`tests/contracts/test_methodology_profile.py`、`tests/negative/test_methodology_profile_fail_closed.py`。
- 必须先写的 negative tests：profile 缺 `template_kind` / `documentation_density`、未知 `template_kind`、与 PackageContract `docs_required` 冲突必须失败；PackageContract 缺 `methodology_profile_ref` 必须失败。
- 必须证明的 happy path：四种 `template_kind`（Minimal / Agile / Compliance / Hybrid）都可绑定 PackageContract 并影响 workspace docs template 选择。
- 验收口径：方法论决策可被合同表达；无 MethodologyProfile 的项目不能进入 BUILD。
- 完成证据：2026-05-15 新增 MethodologyProfile（方法论配置）、MethodologyProfileRegistry（方法论配置注册表）、DocumentationObligation（文档义务）、DocumentationDensity（文档密度）和 docs template binding（文档模板绑定）；PackageContract（包合同）在 `docs_required=True` 时必须通过 MethodologyProfileRegistry 携带并校验 `methodology_profile_ref`、`docs_template_key` 与 `documentation_obligations`，并拒绝无 registry context、跨 ProjectCharter（项目章程）绑定、template/obligation 不一致、重复或非法 profile；`PYTHONPATH=src pytest tests/contracts/test_methodology_profile.py tests/negative/test_methodology_profile_fail_closed.py -q` 通过（26 passed）；`PYTHONPATH=src pytest tests/contracts tests/negative -q` 通过（82 passed）。

### V2-010G: 合同 fixture 与 schema 文档化

- 状态：DONE
- 目标：提供 tiny proving scenario 所需的最小合同 fixture 和 schema 使用示例。
- 输入文档：`doc/04-implementation/proving-scenario-tiny-fullstack.md`。
- 依赖：V2-010F。
- 输出文件：`tests/fixtures/contracts/tiny_fullstack_contract.py`、`tests/contracts/test_tiny_fullstack_contract_fixture.py`、`tests/negative/test_tiny_fullstack_contract_fixture_fail_closed.py`。
- 必须先写的 negative tests：fixture 不能省略 blocking evidence；不能把 fallback 标为 implementation evidence；fixture 的 acceptance_ref 与 `acceptance-criteria.md` 中任何 AC-V2 抽象 AC **未显式绑定** 时必须失败。
- 必须证明的 happy path：fixture 可被 V2-020 ticket graph 测试复用；fixture 中每个 acceptance_ref 都映射到 active AcceptanceContract 中的具体 criterion。
- 验收口径：V2-010 完成后，V2-020 可直接消费合同对象，不再重新解释散文需求；fixture 与 `acceptance-criteria.md` 形成强绑定，避免 fixture 静悄悄背离 AC。
- 完成证据：2026-05-15 新增 TinyFullstackContractFixture（微型全栈合同夹具），覆盖 BoardDirective（董事会指令）、ProjectCharter（项目章程）、MethodologyProfile（方法论配置）、AcceptanceContract（验收合同）、PackageContract（包合同）和 ContractGateResult（合同门禁结果）；通过 `TINY_FULLSTACK_AC_V2_BINDINGS` 显式绑定每个 blocking acceptance_ref（阻塞验收引用）到 AC-V2 抽象原则，并用 fail-closed 测试拒绝缺绑定、未知 AC-V2 绑定和 fallback implementation evidence（降级实施证据）；`PYTHONPATH=src:. pytest tests/contracts/test_tiny_fullstack_contract_fixture.py tests/negative/test_tiny_fullstack_contract_fixture_fail_closed.py -q` 通过（6 passed）。

---

## V2-020: Event + Reducer Kernel（事件与状态归约内核）

- 状态：DONE
- 目标：实现 event record（事件记录）、event log abstraction（事件日志抽象）、ticket graph projection（任务图投影）和 reducer（状态归约器）。
- 输入文档：`technical-architecture.md`、`domain-model.md`、`execution-and-runtime-boundary.md`。
- 输出目录：`src/boardroom_os/events/`、`src/boardroom_os/reducers/`、`src/boardroom_os/graph/`、`tests/reducers/`。
- 顶层验收口径：invalid transition fail closed；executor 不能直接完成 ticket；graph version 可追踪；replay projection 可重建状态。

### V2-020A: 定义 typed event record

- 状态：DONE
- 目标：定义所有可进入 event log 的最小事件类型和公共字段。
- 输入文档：`domain-model.md`、`process-audit-and-replay.md`。
- 依赖：V2-010E。
- 输出文件：`src/boardroom_os/events/record.py`、`src/boardroom_os/events/types.py`、`tests/reducers/test_event_record.py`。
- 必须先写的 negative tests：事件缺 actor、timestamp、graph_version、payload refs 必须失败。
- 必须证明的 happy path：事件可稳定序列化并保留 causation/correlation refs。
- 验收口径：audit/replay 不依赖未结构化日志。
- 完成证据：2026-05-15 新增 EventRecord（事件记录）、EventType（事件类型）、EventId（事件 ID）、EventRef（事件引用）、ProjectRef（项目引用）、ActorRef（参与者引用）和 EventPayloadRef（事件载荷引用）；按 V2-020A 更窄范围仅覆盖 Phase 2 / runtime boundary 已明确需要的 ticket 与 execution 事实事件，后续阶段在实际消费时扩展自己的 EventType（见 DEC-0010）；缺 actor、timestamp、graph_version、payload refs、空 actor、graph_version 非正数、空 payload refs、无时区 timestamp、未知 event_type 均 fail closed；EventType 保持枚举类型供 reducer 分支使用，stable dump 保持 Pydantic value object 形态并可直接回放为 EventRecord；`PYTHONPATH=src pytest tests/reducers/test_event_record.py -q` 通过（12 passed）。

### V2-020B: 实现 in-memory event log 与 append 校验

- 状态：DONE
- 目标：提供最小 event log 接口，用于测试 reducer 和 replay。
- 输入文档：`technical-architecture.md`。
- 依赖：V2-020A。
- 输出文件：`src/boardroom_os/events/log.py`、`tests/reducers/test_event_log.py`。
- 必须先写的 negative tests：graph_version 回退、重复 event_id、未知 event_type 必须失败。
- 必须证明的 happy path：append 后可按 project_ref 和版本范围读取事件。
- 验收口径：后续 runtime 只能 append 事实事件，不能直接改 projection。
- 完成证据：2026-05-15 新增 InMemoryEventLog（内存事件日志）与 EventLogAppendError（事件日志追加错误）；append-only（只追加）接口按 project_ref（项目引用）隔离 graph_version（图版本）严格递增，拒绝重复 event_id（事件 ID）与通过不安全构造绕过的未知 event_type（事件类型）；read（读取）接口可按 project_ref、from_graph_version 和 to_graph_version 返回稳定版本序列；`PYTHONPATH=src pytest tests/reducers/test_event_record.py tests/reducers/test_event_log.py -q` 通过（17 passed）。

### V2-020C: 实现 TicketNode 与 TicketGraph projection

- 状态：DONE
- 目标：从事件构建 ticket graph（任务图）的当前状态。
- 输入文档：`domain-model.md`。
- 依赖：V2-020B。
- 输出文件：`src/boardroom_os/graph/ticket.py`、`src/boardroom_os/graph/projection.py`、`tests/reducers/test_ticket_graph_projection.py`。
- 必须先写的 negative tests：ticket 缺 acceptance_refs、source_surface_refs、evidence_obligations、allowed_write_set 必须无效。
- 必须证明的 happy path：合法 ticket 可进入 ready_queue，blocked ticket 不可执行。
- 验收口径：ticket graph 是流程状态源。
- 完成证据：2026-05-15 新增 TicketNode（任务节点）、TicketGraph（任务图）、TicketCreatedPayload（任务创建载荷）、TicketBlockedPayload（任务阻塞载荷）、TicketPayloadResolver（任务载荷解析器）和 TicketGraphProjector（任务图投影器）；`EventRecord.payload_refs`（事件载荷引用）保持为审计指针，projection（投影）通过 resolver 解析 typed payload，未来 V2-070 可替换为 replay resolver（重放解析器）而不改变投影语义；缺 acceptance_refs / source_surface_refs / evidence_obligations / allowed_write_set、无法解析 payload_ref、重复 ticket、未知 dependency、unsupported ticket event、blocked ticket 进入 ready_queue 均 fail closed；`TICKET_CREATED` 不能表达 completed 状态，合法 ticket 可进入 ready_queue，blocked ticket 不可执行，non-ticket event 不改变 graph；`PYTHONPATH=src pytest tests/reducers/test_event_record.py tests/reducers/test_event_log.py tests/reducers/test_ticket_graph_projection.py -q` 通过（77 passed）。

### V2-020D: 实现 reducer 状态转换

- 状态：DONE
- 目标：保护 ticket created、leased、work submitted、checked、completed、rework 等转换。
- 输入文档：`execution-and-runtime-boundary.md`、`contract-and-evidence-model.md`。
- 依赖：V2-020C。
- 输出文件：`src/boardroom_os/reducers/ticket_reducer.py`、`src/boardroom_os/reducers/errors.py`、`tests/reducers/test_ticket_reducer_transitions.py`、`tests/negative/test_executor_cannot_complete_ticket.py`。
- 必须先写的 negative tests：executor 提交 `TICKET_COMPLETED`、provider attempt count 为 0、checker blocker 未清除时完成 ticket 必须失败。
- 必须证明的 happy path：verified evidence complete + checker approved 时 reducer 产生 completed projection。
- 验收口径：executor/runtime 永远不能直接决定 ticket completed。
- 完成证据：2026-05-16 新增 TicketReducer（任务状态归约器）、TicketCompletionSnapshot（任务完成快照）、TicketCheckSnapshot（检查快照）和 TicketRefPayload（任务引用载荷）；V2-020D 固化 reducer completion boundary（完成边界）作为后续 V2-050F 接入点，而不提前实现 FinalEvidenceTable（最终证据表）或 CheckerVerdict（检查结论）模型。负例证明 executor/runtime actor 提交 `TICKET_COMPLETED`、provider_attempt_count 为 0、completion snapshot 自带 blocker、历史 checker blocker 未清除、无 checker blocker 发起 rework 均 fail closed；正例证明 lease/work submitted 不会完成 ticket，checker blocker 可触发 rework blocked projection，reworked ticket 经后续 checker approved 可恢复 READY 并完成，evidence complete + checker approved + provider attempt recorded 时 ticket completed。`PYTHONPATH=src pytest tests/reducers/test_ticket_reducer_transitions.py tests/negative/test_executor_cannot_complete_ticket.py -q` 通过（12 passed）；`PYTHONPATH=src pytest tests/reducers/test_event_record.py tests/reducers/test_event_log.py tests/reducers/test_ticket_graph_projection.py tests/reducers/test_ticket_reducer_transitions.py tests/negative/test_executor_cannot_complete_ticket.py -q` 通过（89 passed）；`PYTHONPATH="src;." pytest tests/contracts tests/reducers tests/negative -q` 通过（179 passed）。

### V2-020E: 实现 seat assignment 事件入口

- 状态：DONE
- 目标：在图中表达 AgentSeatAssignment（席位分配），但不在此阶段调用 provider。
- 输入文档：`agent-team-model.md`。
- 依赖：V2-020D。
- 输出文件：`src/boardroom_os/graph/seat_assignment.py`、`tests/reducers/test_seat_assignment_projection.py`。
- 必须先写的 negative tests：ticket 无 owner_seat_ref、缺 SEAT_ASSIGNED 事件、SEAT_ASSIGNED 早于 TICKET_CREATED、SEAT_ASSIGNED 多 payload_refs、assignment 引用未知 ticket、seat 声明 capability 与 assignment required_capability_tags 不匹配、seat 缺 model_execution_profile_ref 必须失败或保持 blocked。
- 必须证明的 happy path：CEO/architect/worker/checker seat 可被分配到不同 ticket。
- 验收口径：V2-030 能基于 seat assignment 编译 ExecutionPackage。
- 完成证据：2026-05-16 新增 SeatDefinition（席位定义快照）、SeatAssignmentPayload（席位分配载荷）、SeatAssignmentGraph（席位分配图投影）和 SeatAssignmentProjector（席位分配投影器）；V2-020E 只在 graph 层表达 seat assignment 事实，不提前创建 V2-030 agents 包且不调用 provider。负例证明 ticket 缺 owner_seat_ref、缺 SEAT_ASSIGNED 事件、SEAT_ASSIGNED 早于 TICKET_CREATED、多 payload_refs、assignment 引用未知 ticket、seat 缺 model_execution_profile_ref、未知 seat、inactive seat、seat 声明 capability 与 assignment required_capability_tags 不一致、ticket owner 与 assignment seat 不一致均 fail closed 或保持 blocked；正例证明 CEO/architect/worker/checker seat 可分配到不同 ticket 并进入 ready_queue，且测试事件可被 InMemoryEventLog 接受为唯一 event_id 序列。先运行 `PYTHONPATH=src pytest tests/reducers/test_seat_assignment_projection.py -q` 得到预期 RED（`ModuleNotFoundError: No module named 'boardroom_os.graph.seat_assignment'`）；审计修复前补充 early assignment / unknown ticket / multi payload_refs 得到预期 RED；实现后同命令通过（11 passed）。

### V2-020F: 实现 projection replay

- 状态：DONE
- 目标：证明 graph projection 可由 event log 重放生成。
- 输入文档：`process-audit-and-replay.md`。
- 依赖：V2-020E。
- 输出文件：`src/boardroom_os/graph/replay.py`、`tests/reducers/test_projection_replay.py`。
- 必须先写的 negative tests：事件缺失、事件乱序、projection version 不匹配必须失败。
- 必须证明的 happy path：同一事件序列重放得到同一 graph hash 或等价 projection summary。
- 验收口径：后续 closeout/replay 不依赖 runtime 内存状态。
- 完成证据：2026-05-16 新增 ProjectionReplay（投影重放器）、ProjectionReplaySummary（投影重放摘要）和 ProjectionReplayEventRange（投影重放事件范围），当前边界只覆盖 audit replay（审计重放），不提前实现 V2-070 branchable governance replay（可分叉治理重放）。负例证明空事件范围、graph_version 缺口、输入乱序、project mismatch（项目不匹配）、non-positive expected_graph_version（非正预期图版本）、from_graph_version 中段重放缺 snapshot/base projection contract（快照/基准投影合同）、projection version mismatch（投影版本不匹配）和 unresolved payload ref（未解析载荷引用）均 fail closed；正例证明 seat_assignment_graph（席位分配图）projection summary 可确定性重建，并对 happy path 产出 stable `summary_hash`。验证命令：`PYTHONPATH=src pytest tests/reducers/test_projection_replay.py -q` 通过（11 passed）；`PYTHONPATH=src pytest tests/reducers/test_event_record.py tests/reducers/test_event_log.py tests/reducers/test_ticket_graph_projection.py tests/reducers/test_ticket_reducer_transitions.py tests/reducers/test_seat_assignment_projection.py tests/reducers/test_projection_replay.py tests/negative/test_executor_cannot_complete_ticket.py -q` 通过（111 passed）。

---

## V2-030: Agent Seat + Execution Package Compiler（席位与执行包编译器）

- 状态：DONE
- 目标：实现 role（角色）、seat（席位）、skill binding（技能绑定）、ModelExecutionProfile（模型执行配置）和 ExecutionPackage（执行包）编译。
- 输入文档：`agent-team-model.md`、`execution-and-runtime-boundary.md`、`technical-architecture.md`。
- 输出目录：`src/boardroom_os/agents/`、`src/boardroom_os/execution/`、`tests/execution/`、`tests/negative/`。
- 顶层验收口径：缺 acceptance refs、allowed write set、evidence obligations、seat_ref 或 model_execution_profile 时 execution package 无效；role/provider 接入链清晰可测。

### V2-030A: 定义 RoleProfile、SkillBinding、ModelExecutionProfile

- 状态：DONE
- 目标：把角色职责、技能能力和 provider/model/effort 配置拆开表达。
- 输入文档：`agent-team-model.md`、`decisions.md`（DEC-0011）。
- 依赖：V2-020E。
- 输出文件：`src/boardroom_os/agents/profiles.py`、`src/boardroom_os/agents/skills.py`、`tests/execution/test_agent_profiles.py`。
- 必须先写的 negative tests：role 直接包含 provider credential、skill 绑定未知 role、model profile 缺 provider/model、capability tag 不在 registry（能力标签注册表）中必须失败。
- 必须证明的 happy path：同一 RoleProfile 可绑定不同 ModelExecutionProfile 形成不同 seat；RoleProfile capability_tags（角色能力标签）能被后续 AgentSeat policy 消费。
- 验收口径：role 不直接调用 provider；provider 通过 ModelExecutionProfile 接入；capability_tags 不再是无注册表约束的散字符串。
- 完成证据：2026-05-16 新增 RoleProfile（角色模板）、SkillBinding（技能绑定）、ModelExecutionProfile（模型执行配置）、CapabilityRegistry（能力标签注册表）、PromptSourceRegistry（提示词来源注册表）、SkillFileSourceRegistry（技能文件来源注册表）和 McpInterfaceRegistry（MCP 接口注册表）；SkillBinding 首版纳入 `skill_file_ref`、`prompt_refs`、`mcp_interface_refs`，并支持 `version: 1` YAML-shaped（YAML 形状）人工配置解析。负例证明 role 泄漏 provider 字段、未知 capability tag、skill 绑定未知 role、未知 skill/prompt/MCP ref、MCP 所需能力缺失、model profile 缺 provider/model 或携带 credential/api_key 均 fail closed；正例证明分层命名 capability tags 可经 registry 校验，人工配置模板可编译成 role/skill/model registries，且同一 RoleProfile 可对应多个 ModelExecutionProfile。验证命令：先运行 `PYTHONPATH=src pytest tests/execution/test_agent_profiles.py -q` 得到预期 RED（`ModuleNotFoundError: No module named 'boardroom_os.agents.profiles'`）；补充 YAML-shaped 配置测试后得到预期 RED（拒绝 `version` 与裸字符串 refs）；实现后 `PYTHONPATH=src pytest tests/execution/test_agent_profiles.py -q` 通过（10 passed）；`PYTHONPATH="src;." pytest tests/execution/test_agent_profiles.py tests/reducers/test_seat_assignment_projection.py tests/contracts tests/negative -q` 通过（112 passed）。

### V2-030B: 定义 AgentSeat 与 seat policy

- 状态：DONE
- 目标：表达项目中被 CEO 激活的具体 seat，并校验 seat 能力边界。
- 输入文档：`agent-team-model.md`、`domain-model.md`、`decisions.md`（DEC-0011）。
- 依赖：V2-030A。
- 输出文件：`src/boardroom_os/agents/categories.py`、`src/boardroom_os/agents/seat.py`、`src/boardroom_os/agents/policy.py`、`tests/execution/test_agent_seat_policy.py`；并更新 `src/boardroom_os/graph/ticket.py`、`src/boardroom_os/graph/seat_assignment.py`、`src/boardroom_os/events/types.py`、相关 reducers / negative tests。
- 必须先写的 negative tests：worker seat 缺 allowed capability、checker seat 与 worker seat 相同且无独立验证边界、seat 缺 model_execution_profile_ref、未激活 seat 被分配或编译 execution package 必须失败。
- 必须证明的 happy path：CEO、Architect、Worker、Checker seats 可被创建并映射到 ticket 类型；seat activated/deactivated（席位启用/停用）事实可投影出 active seats（活跃席位）并供 seat assignment / execution package 消费。
- 验收口径：seat 是 role/provider/context 的接合点；席位生命周期必须可审计，不能长期依赖构造器注入的 SeatDefinition 快照。
- 完成证据：2026-05-17 新增封闭 `RoleCategory`（角色类别）、`AgentSeat`（智能体席位）、`SeatDemand`（席位需求）、SeatLifecycleProjection（席位生命周期投影）、BootstrapGovernanceAuthority（治理创世授权）、RoleProfileProjection（角色模板投影）和 SeatPolicy（席位策略）；`BOOTSTRAP_GOVERNANCE_AUTHORITY` 作为可重放事实由 GovernanceAuthorityProjector（治理授权投影器）唯一校验，bootstrap actor（创世参与者）仅可在有限序列内注册首个 governance RoleProfile（治理角色模板）并激活首个 CEO AgentSeat。`TicketCreatedPayload` 与 `TicketNode` 一次性退役 `owner_seat_ref` 并改为 `seat_demand`；SeatAssignmentProjector（席位分配投影器）消费 active AgentSeat projection（活跃席位投影），不再依赖 graph-local SeatDefinition 快照，也不自动 follow replacement chain（替换链）。负例覆盖 bootstrap fact 缺失/重复/解析失败、非 bootstrap actor 注册首个 governance role、bootstrap actor 长期超级用户、seat 静态字段被 lifecycle event 改写、role capability subset 越界、未激活 / unknown seat assignment、default worker fallback、checker/worker 同 seat 或同 role category 等 fail closed；正例证明 CEO/Architect/Worker/Checker seats 可投影并用于 demand-first assignment（需求优先分配）。最终审查后新增 DEC-0013，要求 V2-030D 在编译执行包前先引入 AgentTeamProjector（智能体团队投影器）或等价编排入口，避免 RoleProfile 与 Seat lifecycle 交织事件由 compiler 临时拼接。验证证据：`PYTHONPATH=src pytest tests/execution/test_agent_profiles.py tests/execution/test_agent_seat_policy.py tests/reducers/test_ticket_graph_projection.py tests/reducers/test_seat_assignment_projection.py tests/reducers/test_projection_replay.py -q` 通过（128 passed）；`PYTHONPATH="src;." pytest tests/contracts tests/reducers tests/execution tests/negative -q` 通过（248 passed）。

### V2-030C: 定义 ExecutionPackage schema

- 状态：DONE
- 目标：实现 worker/checker 执行前必须接收的结构化执行包。
- 输入文档：`execution-and-runtime-boundary.md`、`domain-model.md`。
- 依赖：V2-030B。
- 输出文件：`src/boardroom_os/execution/package.py`、`tests/execution/test_execution_package_schema.py`、`tests/negative/test_execution_package_fail_closed.py`。
- 必须先写的 negative tests：缺 ticket_ref、graph_version、seat_ref、model_execution_profile、acceptance_refs、allowed_write_set、evidence_obligations、fallback_policy_ref 必须失败；只传 ticket_id alias 或 model_execution_profile_ref 也必须失败。
- 必须证明的 happy path：直接构造完整对象图，不调用 compiler，即可形成包含 ModelExecutionProfile snapshot、PackageCommand、EvidenceObligation 和 fallback_policy_ref 的完整 ExecutionPackage。
- 验收口径：worker 不接收散文任务；必须接收结构化执行包。
- 完成证据：2026-05-17 新增 ExecutionPackage（执行包）schema，字段名锁定为 `ticket_ref`（任务引用）并复用 `TicketId`（任务 ID），`seat_ref` 复用 `AgentSeatRef`（智能体席位引用），内嵌完整 `ModelExecutionProfile`（模型执行配置）和 `EvidenceObligation`（证据义务），`commands` 复用 `PackageCommand`（包命令），顶层 `fallback_policy_ref` 表达实际生效降级策略引用；不实现 compiler、fallback classification 或跨 registry 校验。先运行 `PYTHONPATH=src pytest tests/negative/test_execution_package_fail_closed.py -q` 得到预期 RED（`ModuleNotFoundError: No module named 'boardroom_os.execution.package'`）；实现后同命令通过（28 passed）；`PYTHONPATH=src pytest tests/execution/test_execution_package_schema.py tests/negative/test_execution_package_fail_closed.py -q` 通过（30 passed）；`PYTHONPATH="src;." pytest tests/execution tests/reducers tests/negative -q` 通过（247 passed）。

### V2-030D: 实现 ExecutionPackage compiler

- 状态：DONE
- 目标：从 ready ticket、active contracts、workspace manifest 和 seat assignment 编译执行包。
- 输入文档：`technical-architecture.md`、`generated-project-workspace.md`。
- 依赖：V2-030C。
- 输出文件：`src/boardroom_os/agents/team.py`、`src/boardroom_os/execution/compiler.py`、`tests/negative/test_agent_team_projector_fail_closed.py`、`tests/execution/test_agent_team_projector.py`、`tests/negative/test_execution_package_compiler_fail_closed.py`、`tests/execution/test_execution_package_compiler.py`。
- 必须先写的 negative tests：ticket not ready、acceptance_ref 不属于 active contract、write set 超出 source surface、seat capability 不匹配必须失败。
- 必须证明的 happy path：tiny backend worker ticket 能编译出含 commands、context_refs、allowed_write_set、evidence_obligations 的 package。
- 前置架构约束：V2-030D 必须先引入 AgentTeamProjector（智能体团队投影器）或等价单一编排入口，按 graph_version 交织消费 RoleProfile change facts（角色模板变更事实）与 Seat lifecycle facts（席位生命周期事实），再把稳定 projection（投影）交给 ExecutionPackage compiler；compiler 不得分别调用 RoleProfileProjection.apply_changes 与 SeatLifecycleProjector.project 后自行拼接治理状态。
- 验收口径：V2-040 runtime 只消费执行包，不重新解释治理状态。
- 完成证据：2026-05-17 新增 AgentTeamProjector（智能体团队投影器）作为 role profile change facts（角色模板变更事实）与 seat lifecycle facts（席位生命周期事实）的单一 graph_version 编排入口，并新增 ExecutionPackageCompiler（执行包编译器）从 ready ticket（就绪任务）、active AcceptanceContract（活跃验收合同）、PackageContract（包合同）、ExecutionWorkspaceContext（执行工作区上下文）、SeatAssignmentGraph（席位分配图）和 AgentTeamProjection（智能体团队投影）编译 ExecutionPackage（执行包）。负例覆盖 graph_version mismatch、缺 bootstrap/重复 bootstrap、role/seat payload 缺口、缺派工、inactive/unknown seat、capability mismatch、inactive contract、acceptance/source/evidence/command/model/role 缺口、unsafe write path 和 evidence_required 不匹配；正例证明 backend worker ticket 可编译出含 commands、context_refs、allowed_write_set、evidence_obligations、fallback_policy_ref 的 ExecutionPackage。验证命令：`PYTHONPATH="src;." pytest tests/negative/test_agent_team_projector_fail_closed.py tests/execution/test_agent_team_projector.py tests/negative/test_execution_package_compiler_fail_closed.py tests/execution/test_execution_package_compiler.py -q` 通过（44 passed）；`PYTHONPATH="src;." pytest tests/execution/test_execution_package_schema.py tests/execution/test_agent_profiles.py tests/execution/test_agent_seat_policy.py tests/reducers/test_seat_assignment_projection.py tests/reducers/test_projection_replay.py -q` 通过（71 passed）；`PYTHONPATH="src;." pytest tests/contracts tests/reducers tests/execution tests/negative -q` 通过（328 passed）。

### V2-030E: 实现 fallback policy 分类

- 状态：DONE
- 目标：把 fallback 明确分类，防止 fallback 被误当 implementation evidence。
- 输入文档：`execution-and-runtime-boundary.md`。
- 依赖：V2-030D。
- 输出文件：`src/boardroom_os/execution/fallback.py`、`tests/execution/test_fallback_policy.py`、`tests/negative/test_fallback_cannot_satisfy_implementation.py`。
- 必须先写的 negative tests：`PROVIDER_UNAVAILABLE`、`TEST_ONLY_SIMULATION`、`DETERMINISTIC_GOVERNANCE_DRAFT` 满足 implementation evidence 必须失败。
- 必须证明的 happy path：`CONTRACT_ALLOWED_DETERMINISTIC_TRANSFORM` 只能满足合同显式允许的 deterministic evidence。
- 验收口径：旧系统 fallback success 不可复活。
- 完成证据：2026-05-17 新增 EvidencePurpose（证据用途）、FallbackPolicy（降级策略）、FallbackKind（降级类型）、FallbackEvidenceRequest（降级证据请求）、FallbackEvidenceDecision（降级证据判定）和 evaluate_fallback_evidence（降级证据判定函数），复用 FallbackPolicyRef（降级策略引用）、RequiredArtifactType（必需产物类型）和 AcceptanceRef（验收引用）；负例证明 PROVIDER_UNAVAILABLE、TEST_ONLY_SIMULATION、DETERMINISTIC_GOVERNANCE_DRAFT、TOOLING_PREFLIGHT 以及越界 CONTRACT_ALLOWED_DETERMINISTIC_TRANSFORM 均不能满足 implementation evidence（实施证据）；正例证明合同显式允许的 deterministic transform（确定性转换）只能满足窄范围 deterministic evidence（确定性证据），tooling preflight（工具预检）只能满足 diagnostic evidence（诊断证据）。验证命令：`PYTHONPATH=src pytest tests/negative/test_fallback_cannot_satisfy_implementation.py tests/execution/test_fallback_policy.py -q` 通过（22 passed）；`PYTHONPATH="src;." pytest tests/execution tests/negative -q` 通过（201 passed）。

### V2-030F: 生成 agent context index 草稿

- 状态：DONE
- 目标：为 process audit 记录每次 agent attempt 接收的上下文、约束和模型配置。
- 输入文档：`process-audit-and-replay.md`。
- 依赖：V2-030D。
- 输出文件：`src/boardroom_os/execution/context_index.py`、`tests/execution/test_agent_context_index.py`。
- 必须先写的 negative tests：缺 execution_package_ref、model_execution_profile、allowed_write_set 或 provider_attempt_ref 的 context entry 不能进入最终 audit。
- 必须证明的 happy path：execution package 可生成可审计的 context index entry。
- 验收口径：后续 process audit 能回答“agent 接收了什么上下文”。
- 完成证据：2026-05-17 新增 AgentContextSnapshot（智能体上下文快照）、AgentContextIndexEntry（智能体上下文索引条目）、AgentContextIndex（智能体上下文索引）、ProviderAttemptRef（模型调用尝试引用）和 build_agent_context_snapshot（构建上下文快照函数）；负例证明缺 execution_package_ref / model_execution_profile / allowed_write_set / provider_attempt_refs、执行包 ID alias 绕过、snapshot fingerprint 篡改、snapshot fingerprint 非 SHA-256 hex digest、重复 provider attempt ref、同一 provider attempt ref 被多个 entry 认领均 fail closed；正例证明 ExecutionPackage（执行包）可幂等生成完整 agent-facing input snapshot（面向智能体的输入快照），provider retry（模型供应商重试）可按顺序绑定多个 ProviderAttemptRef 且不重新打包上下文。验证命令：`PYTHONPATH="src;." pytest tests/execution/test_agent_context_index.py -q` 通过（46 passed）；`PYTHONPATH="src;." pytest tests/execution -q` 通过（100 passed）；`PYTHONPATH="src;." pytest tests/contracts tests/reducers tests/execution tests/negative -q` 通过（400 passed）。

---

## V2-040: Runtime Executor + Provider + Command Runner（运行时执行器、模型调用与命令证据）

- 状态：DONE
- 目标：实现 provider attempt（模型调用尝试记录）、provider adapter boundary（供应商适配边界）、runtime executor（运行时执行器）和 command runner（命令执行器）。
- 输入文档：`execution-and-runtime-boundary.md`、`TEST_CONVENTIONS.md`。
- 输出目录：`src/boardroom_os/providers/`、`src/boardroom_os/adapters/`、`src/boardroom_os/execution/`、`tests/execution/`、`tests/negative/`。
- 顶层验收口径：zero provider attempt 必须阻断 implementation ticket；command evidence 必须来自 runner；runtime 只记录事实不做治理判断。

### V2-040A: 定义 ProviderAdapter 与 ProviderAttempt

- 状态：DONE
- 目标：建立 provider 调用接口和 attempt record，不接入真实外部模型也能 fake transport（模拟传输）测试。
- 输入文档：`execution-and-runtime-boundary.md`、`agent-team-model.md`。
- 依赖：V2-030C。
- 输出文件：`src/boardroom_os/providers/adapter.py`、`src/boardroom_os/providers/attempt.py`、`tests/execution/test_provider_attempt.py`。
- 必须先写的 negative tests：attempt 缺 provider、model、input_package_ref、seat_ref、status 必须失败；缺 outcome（模型调用结果）、fallback outcome（降级结果）缺 typed fallback_kind（类型化降级类型）、primary outcome（主路径结果）携带 fallback_kind 必须失败。
- 必须证明的 happy path：fake provider transport 产生 attempt record、raw output ref、parsed output ref，并显式标记为 primary/non-fallback outcome（主路径/非降级结果）。
- 验收口径：provider attempt 可追踪到 ExecutionPackage 和 AgentSeat。
- 完成证据：2026-05-18 新增 ProviderAttempt（模型调用尝试记录）、ProviderAttemptStatus（模型调用状态）、ProviderAttemptOutcome（模型调用结果）、ProviderArtifactRef（模型产物引用）、ProviderAdapter（模型供应商适配器）、ProviderRequest（模型供应商请求）、ProviderResponse（模型供应商响应）和 FakeProviderTransport（模拟传输）；负例证明缺 provider / model / reasoning_effort / input_package_ref / seat_ref / status / outcome、无时区时间戳、finished_at 早于 started_at、成功 attempt 缺 raw/parsed output ref、成功 attempt 携带 failure_kind、失败 attempt 缺 failure_kind、unknown extra fields、fallback outcome 缺 typed fallback_kind、primary outcome 携带 fallback_kind 均 fail closed；正例证明 fake provider transport 可由 ProviderRequest 生成 succeeded ProviderAttempt，并绑定 ExecutionPackageRef（执行包引用）、AgentSeatRef（智能体席位引用）、raw output ref、parsed output ref 与 primary/non-fallback outcome。验证命令：先运行 `PYTHONPATH=src pytest tests/execution/test_provider_attempt.py -q` 得到预期 RED（缺 provider 模块 / 缺 ProviderAttemptOutcome）；实现后 `PYTHONPATH=src pytest tests/execution/test_provider_attempt.py -q` 通过（28 passed）；`PYTHONPATH="src;." pytest tests/execution -q` 通过（128 passed）。

### V2-040B: 实现 provider executor boundary

- 状态：DONE
- 目标：runtime 通过 ExecutionPackage 调用 provider，不能直接从 role 或 ticket 调用 provider。
- 输入文档：`execution-and-runtime-boundary.md`。
- 依赖：V2-040A。
- 输出文件：`src/boardroom_os/execution/provider_executor.py`、`tests/execution/test_provider_executor.py`、`tests/negative/test_provider_executor_fail_closed.py`。
- 必须先写的 negative tests：缺 execution package、RoleProfile / TicketNode shortcut、provider attempt 错绑 input_package_ref / seat_ref / provider / model / reasoning_effort 时不得调用或不得放行 provider 结果。
- 必须证明的 happy path：合法 execution package 调用 fake provider 并记录 attempt；failed attempt 作为可审计事实返回。
- 验收口径：role/provider 接入路径闭合：RoleProfile -> AgentSeat -> ModelExecutionProfile -> ExecutionPackage -> ProviderAttempt。
- 完成证据：2026-05-18 新增 ProviderExecutor（模型供应商执行器）、ProviderExecutorInput（模型供应商执行器输入）、ProviderExecutorResult（模型供应商执行器结果）、ProviderExecutorError（模型供应商执行器错误）和 render_prompt_from_snapshot（从快照渲染提示词函数）；ProviderExecutor 只能消费 ExecutionPackage（执行包），调用 build_agent_context_snapshot（构建上下文快照函数）生成 AgentContextSnapshot（智能体上下文快照），由 snapshot 纯派生 ProviderRequest.prompt（模型供应商请求提示词），调用 ProviderAdapter（模型供应商适配器）后校验 ProviderAttempt（模型调用尝试记录）与 snapshot 的 execution_package_ref / seat_ref / provider / model / reasoning_effort 一致。TDD 证据：先运行 `PYTHONPATH=src pytest tests/negative/test_provider_executor_fail_closed.py::test_provider_executor_input_requires_execution_package tests/negative/test_provider_executor_fail_closed.py::test_provider_executor_input_rejects_extra_role_or_ticket_fields -q` 得到预期 RED（缺 `boardroom_os.execution.provider_executor` 模块）；prompt / executor 正例也先得到缺 `render_prompt_from_snapshot` / `ProviderExecutor` 的预期 RED。负例证明缺 ExecutionPackage、RoleProfile / TicketNode shortcut（角色模板/任务节点捷径）、错绑 input_package_ref / seat_ref / provider / model / reasoning_effort 均 fail closed；正例证明合法 ExecutionPackage 可通过 FakeProviderTransport（模拟传输）产生 succeeded ProviderAttempt，failed ProviderAttempt 会作为事实返回而不是抛错，prompt 可由 snapshot 确定性重算。验证命令：`PYTHONPATH="src;." pytest tests/execution/test_provider_attempt.py tests/execution/test_agent_context_index.py tests/execution/test_provider_executor.py tests/negative/test_provider_executor_fail_closed.py -q` 通过（82 passed）；`PYTHONPATH="src;." pytest tests/execution tests/negative -q` 通过（290 passed）。

### V2-040C: 实现 WorkProduct 解析和提交事件

- 状态：DONE
- 目标：把 provider raw output 转成 WorkProduct（工作产物）并提交 `WORK_PRODUCT_SUBMITTED` 事实事件。
- 输入文档：`domain-model.md`、`execution-and-runtime-boundary.md`。
- 依赖：V2-040B。
- 输出文件：`src/boardroom_os/execution/work_product.py`、`tests/execution/test_work_product_submission.py`。
- 必须先写的 negative tests：WorkProduct 缺 producer_attempt_ref、artifact_refs 或 claim_refs 时不得用于 evidence。
- 必须证明的 happy path：fake provider 输出可生成 WorkProduct，并附带 producer attempt。
- 验收口径：runtime 只提交 work product 事实，不完成 ticket。
- 完成证据：2026-05-18 新增 WorkProduct（工作产物）、WorkProductClaimDraft（工作产物证据声明草稿）、WorkProductSubmission（工作产物提交包）、build_work_product_from_provider_attempt（从模型尝试构建工作产物）和 build_work_product_submitted_event（构建工作产物已提交事件）；负例证明 WorkProduct 缺 producer_attempt_ref / artifact_refs / claim_refs、WorkProductClaimDraft 缺 acceptance_refs / source_surface_refs、WorkProductSubmission 缺 claim_drafts 或 claim_refs 与 claim_drafts 不一致、失败 ProviderAttempt（模型调用尝试记录）、错绑 execution_package_ref / seat_ref、缺 raw/parsed output ref、空白 summary 均 fail closed；正例证明 fake provider transport（模拟模型传输）可生成绑定 ExecutionPackageRef（执行包引用）、TicketId（任务 ID）、ProviderAttemptRef（模型调用尝试引用）、raw+parsed artifact refs（原始+解析产物引用）与 claim draft refs（声明草稿引用）的 WorkProduct，并且 event factory（事件工厂）只生成 WORK_PRODUCT_SUBMITTED 事实事件；该事件的 payload_refs 指向 WorkProductRef（工作产物引用），TicketReducer（任务状态归约器）通过 resolve_work_product_ticket_ref（解析工作产物对应任务引用）从 WorkProduct payload（工作产物载荷）恢复 ticket_ref（任务引用）并登记“已提交工作产物”，不会单独完成 ticket（任务）；V2-040E 返回 runtime facts（运行时事实），由后续调用方负责 event log append（事件日志追加）与 payload store（载荷仓库）持久化。验证命令：`PYTHONPATH="src;." pytest tests/execution/test_work_product_submission.py -q` 通过（38 passed）；`PYTHONPATH="src;." pytest tests/execution/test_provider_attempt.py tests/execution/test_provider_executor.py tests/execution/test_agent_context_index.py tests/execution/test_work_product_submission.py tests/negative/test_provider_executor_fail_closed.py -q` 通过（120 passed）；`PYTHONPATH="src;." pytest tests/contracts tests/reducers tests/execution tests/negative -q` 通过（474 passed）。

### V2-040D: 实现 CommandRunner

- 状态：DONE
- 目标：真实运行 declared commands 并记录 VerificationRun（验证运行）。
- 输入文档：`execution-and-runtime-boundary.md`、`TEST_CONVENTIONS.md`。
- 依赖：V2-030D。
- 输出文件：`src/boardroom_os/adapters/process_runner.py`、`src/boardroom_os/execution/verification_run.py`、`tests/execution/test_command_runner.py`。
- 必须先写的 negative tests：合成 verification success、缺 stdout/stderr refs、缺 exit_code、命令不在 package contract 中必须失败。
- 必须证明的 happy path：运行一个本地确定性命令并捕获 exit code/stdout/stderr/duration。
- 验收口径：command evidence 唯一可信来源是 runner。
- 完成证据：`CommandRunner` 只执行同时存在于 `ExecutionPackage.commands` 与 `PackageContract.run_commands/test_commands` 且完整相等的 `PackageCommand`；`VerificationRun` 要求 exit_code、stdout/stderr refs、时区时间戳、environment profile 和 workspace snapshot；malformed process result、cwd escape、absolute cwd、naive/rollback clock 均 fail closed。验证：`PYTHONPATH="src;." python -m pytest tests/execution/test_command_runner.py -q`（36 passed）；`PYTHONPATH="src;." python -m pytest tests/contracts tests/reducers tests/execution tests/negative -q`（510 passed）。

### V2-040E: 实现 runtime executor 事实事件边界

- 状态：DONE
- 目标：限制 runtime 只能 emit execution/provider/tool/command/work product 事实事件。
- 输入文档：`execution-and-runtime-boundary.md`、`decisions.md`（DEC-0011）。
- 依赖：V2-040C、V2-040D。
- 输出文件：`src/boardroom_os/execution/runtime_executor.py`、`tests/execution/test_runtime_executor_boundary.py`、`tests/negative/test_runtime_cannot_govern.py`。
- 必须先写的 negative tests：runtime emit `TICKET_COMPLETED`、`PROJECT_COMPLETED`、`CLOSEOUT_COMMITTED` 必须失败；runtime/executor 使用普通 seat actor_ref 伪装治理 actor 时也必须失败。
- 必须证明的 happy path：runtime 对 ready execution package 可记录 provider attempt、work product 和 command run。
- 验收口径：runtime bounded 约束可由测试证明；越权判断必须基于 RoleProfile / AgentSeat 的角色边界，而不是仅依赖 `actor_ref` 字符串前缀。
- 完成证据：2026-05-19 新增 RuntimeExecutor（运行时执行器）、RuntimeEventBoundary（运行时事件边界）、RuntimeEventSequencer（运行时事件序列器）和 runtime fact event factories（运行时事实事件工厂）；负例证明 runtime emit `TICKET_COMPLETED`、保留治理事件名 `project_completed` / `closeout_committed`、未知事件名、runtime_actor_ref 伪装任一 active AgentSeat.actor_ref、缺 active execution seat、GOVERNANCE / ARCHITECTURE / AUDIT seat 执行包、first_fact_graph_version 未大于执行包 graph_version 均 fail closed；正例证明 RuntimeExecutor 对 ready ExecutionPackage 可记录 `EXECUTION_STARTED`、`PROVIDER_ATTEMPT_RECORDED`、`WORK_PRODUCT_SUBMITTED`、`COMMAND_RUN_RECORDED` 事实事件，provider failed 只记录 failed ProviderAttempt，command failed 记录 failed VerificationRun 而不 emit completion。验证命令：`PYTHONPATH=src:. python -m pytest tests/negative/test_runtime_cannot_govern.py -q`（15 passed）；`PYTHONPATH=src:. python -m pytest tests/execution/test_runtime_executor_boundary.py -q`（10 passed）；`PYTHONPATH=src:. python -m pytest tests/execution/test_provider_executor.py tests/execution/test_work_product_submission.py tests/execution/test_command_runner.py tests/execution/test_runtime_executor_boundary.py tests/negative/test_provider_executor_fail_closed.py tests/negative/test_runtime_cannot_govern.py -q`（111 passed）；`PYTHONPATH=src:. python -m pytest tests/contracts tests/reducers tests/execution tests/negative -q`（535 passed）。

---

## V2-050: Evidence Verifier + Checker + Rework（证据验证、检查与返工）

- 状态：DONE
- 目标：实现 evidence claim（证据声明）、evidence verifier（证据验证器）、final evidence table（最终证据表）、checker verdict（检查结论）和 rework ticket（返工任务）触发。
- 输入文档：`contract-and-evidence-model.md`、`agent-team-model.md`。
- 输出目录：`src/boardroom_os/evidence/`、`src/boardroom_os/checker/`、`tests/evidence/`、`tests/negative/`。
- 顶层验收口径：missing evidence -> REWORK_REQUIRED；checker notes 不能覆盖 blocker；source inventory ref-only 不能 closeout。

### V2-050A: 实现 EvidenceClaim

- 状态：DONE
- 目标：表达 producer 对 source/test/run/integration/closeout evidence 的声明。
- 输入文档：`contract-and-evidence-model.md`。
- 依赖：V2-040C、V2-040D。
- 输出文件：`src/boardroom_os/evidence/claim.py`、`src/boardroom_os/evidence/__init__.py`、`tests/evidence/test_evidence_claim.py`。
- 必须先写的 negative tests：claim 缺 producer_attempt_ref、acceptance_refs、source_surface_refs、artifact_refs、expected_purpose（证据预期用途）必须失败；fallback claim 缺 typed fallback marker（类型化降级标记）必须失败。
- 必须证明的 happy path：WorkProduct 和 VerificationRun 可生成 EvidenceClaim；claim 的 expected_purpose 由 EvidenceObligation（证据义务）派生，verifier 不得自由选择 purpose。
- 验收口径：claim 不是 verified evidence；EvidencePurpose（证据用途）必须在 claim/obligation 链路中被类型化表达，避免把 implementation artifact 错判为 deterministic evidence。
- 完成证据：2026-05-19 新增 EvidenceClaim（证据声明）、FallbackLineageMarker（降级来源链标记）和 builder（构建函数）；WorkProduct builder（工作产物构建器）同时消费 WorkProduct（工作产物）与 WorkProductClaimDraft（工作产物证据声明草稿），校验 producer_attempt_ref、execution_package_ref、ticket_ref、artifact_refs 和 claim_draft_ref 归属一致，并把 claim refs 限制为 EvidenceObligation（证据义务）范围；VerificationRun builder（验证运行构建器）要求调用方显式传入 ProviderAttemptRef（模型调用尝试引用），以 stdout/stderr refs 生成 EvidenceArtifactRef（证据产物引用），不复制 command_id。负例覆盖缺 required fields、空 refs、malformed scalar refs、fallback marker 缺字段/unknown decision、fallback WorkProduct 缺 fallback_policy_ref、primary 携带 fallback_policy_ref、claim draft 对齐失败、acceptance/source coverage 不足、expected_purpose 越权、VerificationRun 缺/错 producer_attempt_ref、source_ref 与当前 verification_run_refs 不一致。正例覆盖 ProviderAttempt → WorkProductSubmission → EvidenceClaim 链路、VerificationRun command evidence claim、fallback lineage marker 只记录 typed lineage 不记录 allowed/decision、explicit claim_id override 和 expected_purpose 固定。验证命令：`PYTHONPATH="src:." python -m pytest tests/evidence/test_evidence_claim.py -q`（60 passed）；`PYTHONPATH="src:." python -m pytest tests/execution/test_work_product_submission.py tests/execution/test_command_runner.py tests/evidence/test_evidence_claim.py -q`（134 passed）；`PYTHONPATH="src:." python -m pytest tests/contracts tests/reducers tests/execution tests/evidence tests/negative -q`（595 passed）。

### V2-050A1: 实现 FallbackPolicyRegistry 与 fallback lineage 标记

- 状态：DONE
- 目标：把 `fallback_policy_ref` 解析为唯一权威 FallbackPolicy（降级策略），并让 fallback lineage（降级来源链）成为 verifier 可见的 typed fact（类型化事实）。
- 输入文档：`execution-and-runtime-boundary.md`、`contract-and-evidence-model.md`、`decisions.md`（DEC-0014）。
- 依赖：V2-030E、V2-040A、V2-040C、V2-050A。
- 输出文件：`src/boardroom_os/evidence/fallback_registry.py`、`tests/evidence/test_fallback_policy_registry.py`、`tests/negative/test_fallback_registry_fail_closed.py`。
- 必须先写的 negative tests：fallback_policy_ref 无法解析、ref 解析出的 FallbackKind 与 provider/work product fallback marker 不一致、registry 缺位、fallback artifact 缺 typed fallback marker、将 TEST_ONLY_SIMULATION / PROVIDER_UNAVAILABLE / DETERMINISTIC_GOVERNANCE_DRAFT 注册为可满足 evidence、按 acceptance_ref 拆分调用 evaluator 均必须失败。
- 必须证明的 happy path：registry 可把合法 fallback_policy_ref 解析为 FallbackPolicy；每个 fallback work product 以完整 acceptance_refs 一次性调用 evaluate_fallback_evidence 并生成可审计 decision。
- 验收口径：fallback ref -> policy 的解析只有 registry 一个权威入口；registry 落地前 V2-050 对任何 fallback artifact 必须 fail closed。
- 完成证据：2026-05-20 新增 `FallbackPolicyRegistry`（降级策略注册表）、`FallbackDecisionRecord`（降级判定记录）与 `evaluate_fallback_claim`（降级声明判定函数），把 fallback claim 的 `fallback_policy_ref` 解析为唯一权威 `FallbackPolicy`（降级策略），并产出 verifier 可消费的 typed decision record（类型化判定记录）；同时补齐正例测试 `tests/evidence/test_fallback_policy_registry.py` 与负例测试 `tests/negative/test_fallback_registry_fail_closed.py`，覆盖 registry 缺位、未知 policy ref、fallback kind 不一致、危险 fallback kind 注册、fallback_marker 缺失、decision 对齐失败，以及完整 acceptance_refs 单次调用 evaluator 的 orchestration contract（编排契约）。验证证据：`PYTHONPATH="src:." python -m pytest tests/negative/test_fallback_registry_fail_closed.py -q`（20 passed）；`PYTHONPATH="src:." python -m pytest tests/evidence/test_fallback_policy_registry.py -q`（7 passed）；`PYTHONPATH="src:." python -m pytest tests/evidence/test_evidence_claim.py tests/evidence/test_fallback_policy_registry.py tests/negative/test_fallback_registry_fail_closed.py tests/negative/test_fallback_cannot_satisfy_implementation.py tests/execution/test_fallback_policy.py -q`（116 passed）；`PYTHONPATH="src:." python -m pytest tests/contracts tests/reducers tests/execution tests/evidence tests/negative -q`（622 passed）。

### V2-050B: 实现 artifact/hash/provider/command evidence verifier

- 状态：DONE
- 目标：验证 artifact 存在性、hash 稳定性、producer attempt、command run、active contract refs 和 fallback decision（降级判定）。
- 输入文档：`contract-and-evidence-model.md`。
- 依赖：V2-050A、V2-050A1。
- 输出文件：`src/boardroom_os/evidence/verifier.py`、`tests/evidence/test_evidence_verifier.py`、`tests/negative/test_synthetic_evidence_rejected.py`。
- 必须先写的 negative tests：synthetic verification、provider zero-attempt、artifact 缺 hash、acceptance_ref 不属于 active contract、fallback artifact 未解析 registry、未调用 evaluate_fallback_evidence、缺 FALLBACK_DECISION_RECORDED、decision allowed=False 却进入 verified evidence、EvidencePurpose 与 RequiredArtifactType 不匹配必须失败。
- 必须证明的 happy path：真实 runner 记录 + provider attempt + artifact hash 可转为 verified evidence；合同显式允许的 deterministic fallback artifact 必须带 allowed=True 的 fallback decision 才可转为 verified evidence。
- 验收口径：verified evidence table 不能由 claim 直接替代；AC-V2-EXECUTION-003 只能在 verifier 实际执行 fallback gate 并记录 decision 后勾选。
- 完成证据：2026-05-20 新增 EvidenceVerifier（证据验证器）、ArtifactManifest（产物清单）、EvidencePurposePolicy（证据用途策略）、VerifiedEvidence（已验证证据）和 EvidenceVerificationResult（证据验证结果）；负例覆盖 missing artifact/hash/provider、inactive/unknown acceptance refs、EvidenceObligation（证据义务）不对齐、purpose/artifact mismatch、VerificationRun（验证运行）缺失/失败/stdout·stderr 不一致、primary/fallback attempt mismatch、fallback registry/decision/recorded ref 缺失、unresolved policy、decision scope mismatch、allowed=False，以及 `evaluate_fallback_claim`（降级声明判定函数）必须用完整 claim scope（声明作用域）和 verified_at（验证时间）调用一次。正例覆盖 primary WorkProduct（主路径工作产物）、command VerificationRun（命令验证运行）、allowed deterministic fallback（允许的确定性降级）、deterministic verified evidence id（确定性已验证证据 ID）、audit-friendly JSON（审计友好 JSON）和 success-or-blockers XOR（成功或阻断互斥）。验证证据：`PYTHONPATH="src:." python -m pytest tests/negative/test_synthetic_evidence_rejected.py -q`（33 passed）；`PYTHONPATH="src:." python -m pytest tests/evidence/test_evidence_verifier.py -q`（7 passed）；`PYTHONPATH="src:." python -m pytest tests/evidence/test_evidence_claim.py tests/evidence/test_fallback_policy_registry.py tests/evidence/test_evidence_verifier.py tests/negative/test_synthetic_evidence_rejected.py tests/negative/test_fallback_registry_fail_closed.py -q`（127 passed）；`PYTHONPATH="src:." python -m pytest tests/contracts tests/reducers tests/execution tests/evidence tests/negative -q`（662 passed）。

### V2-050C: 实现 FinalEvidenceTable

- 状态：DONE
- 目标：按 active AcceptanceContract 汇总 satisfied/failed/missing 状态。
- 输入文档：`contract-and-evidence-model.md`、`acceptance-criteria.md`。
- 依赖：V2-050B。
- 输出文件：`src/boardroom_os/evidence/table.py`、`tests/evidence/test_final_evidence_table.py`、`tests/negative/test_missing_acceptance_map_blocks_closeout.py`。
- 必须先写的 negative tests：acceptance map 为空、blocking criterion missing、failed evidence 被 notes 覆盖必须失败。
- 必须证明的 happy path：所有 blocking criteria 的 `evidence_required`（证据需求）均被 VerifiedEvidence.required_artifact_type（已验证证据必需产物类型）完整覆盖时 table complete。
- 验收口径：closeout 只消费 complete final evidence table。
- 完成证据：2026-05-21 新增 FinalEvidenceTable（最终证据表）、FinalEvidenceRow（最终证据行）、FinalEvidenceBlocker（最终证据阻断项）和 FinalEvidenceTableBuilder（最终证据表构建器）；关键产出文件为 `src/boardroom_os/evidence/table.py`、`tests/evidence/test_final_evidence_table.py`、`tests/negative/test_missing_acceptance_map_blocks_closeout.py`。负例证明 inactive contract、空 acceptance map、missing blocking criterion、未知 acceptance_ref、notes 输入、EvidenceClaim / EvidenceVerificationResult 误入、非确定性 table id、satisfied/failed/complete 不变量破坏均 fail closed；正例证明单个与多个 blocking criteria 可由 VerifiedEvidence 覆盖，单条 VerifiedEvidence 可覆盖多个 acceptance_ref，missing/failed row 使 table incomplete，failed blocker 不能被 VerifiedEvidence 覆盖，table 可审计 JSON 序列化且使用确定性 id。验证命令：`PYTHONPATH="src:." python -m pytest tests/evidence/test_evidence_verifier.py tests/evidence/test_final_evidence_table.py tests/negative/test_synthetic_evidence_rejected.py tests/negative/test_missing_acceptance_map_blocks_closeout.py -q`（70 passed）；`PYTHONPATH="src:." python -m pytest tests/contracts tests/reducers tests/execution tests/evidence tests/negative -q`（692 passed）。

### V2-050D: 实现 CheckerVerdict

- 状态：DONE
- 目标：让 checker 独立消费 work product、source diff、verified evidence 和 contracts，输出 verdict。
- 输入文档：`agent-team-model.md`、`contract-and-evidence-model.md`。
- 依赖：V2-050C。
- 输出文件：`src/boardroom_os/checker/verdict.py`、`src/boardroom_os/checker/checker.py`、`tests/evidence/test_checker_verdict.py`。
- 必须先写的 negative tests：verified evidence incomplete 但 checker approved、notes 覆盖 blocker、checker 自行补 evidence 必须失败。
- 必须证明的 happy path：evidence complete 时 checker 可 APPROVED 或 APPROVED_WITH_NON_BLOCKING_NOTES。
- 验收口径：checker 不能替 verifier 放行。
- 完成证据：2026-05-21 新增 CheckerVerdict（检查结论）、CheckerVerdictBlocker（检查结论阻断项）、CheckerNote（检查备注）、SourceDiffRef（源码差异引用）、CheckerServiceInput（检查服务输入）和 CheckerService（检查服务）；关键产出文件为 `src/boardroom_os/checker/verdict.py`、`src/boardroom_os/checker/checker.py`、`src/boardroom_os/checker/__init__.py`、`tests/evidence/test_checker_verdict.py`。负例证明 dict / raw EvidenceClaim（证据声明）/ VerifiedEvidence（已验证证据）/ EvidenceVerificationResult（证据验证结果）/ final_evidence_blockers（最终证据阻断项）/ override 字段不能进入 CheckerService；inactive contract、contract mismatch、ticket mismatch、空 source_diff_ref、缺 artifact_refs / claim_refs、FinalEvidenceTable（最终证据表）complete 不一致、FAILED row 缺 blocker、row status 非枚举、row acceptance_ref 越界、copied CheckerServiceInput（复制后的检查服务输入）篡改均 fail closed；missing / failed evidence rows 生成 `REWORK_REQUIRED` blocker；notes 不能清除 blocker；manual checker blocker 强制 rework。正例证明 complete evidence 无备注返回 `approved`，有非阻断备注返回 `approved_with_non_blocking_notes`，并提供 audit-friendly JSON（审计友好 JSON）与确定性 `checker-verdict.<ticket_ref>.<final_evidence_table_ref>`。验证命令：`PYTHONPATH="src:." python -m pytest tests/evidence/test_checker_verdict.py -q`（43 passed）；`PYTHONPATH="src:." python -m pytest tests/evidence/test_final_evidence_table.py tests/evidence/test_checker_verdict.py tests/negative/test_missing_acceptance_map_blocks_closeout.py -q`（73 passed）；`PYTHONPATH="src:." python -m pytest tests/contracts tests/reducers tests/execution tests/evidence tests/negative -q`（735 passed）。

### V2-050E: 实现 rework ticket 触发

- 状态：DONE
- 目标：把 checker blocker 和 evidence gaps 转换成 graph 中的 rework ticket。
- 输入文档：`agent-team-model.md`、`domain-model.md`。
- 依赖：V2-050D、V2-020D。
- 输出文件：`src/boardroom_os/checker/rework.py`、`tests/evidence/test_rework_ticket_generation.py`。
- 必须先写的 negative tests：blocking gap 不生成 rework、rework ticket 缺 acceptance_refs/evidence_obligations 必须失败。
- 必须证明的 happy path：missing test evidence 生成绑定原 ticket 的 rework ticket。
- 验收口径：缺口在 checker/rework 阶段暴露，不留到 closeout 首次发现。
- 完成证据：2026-05-21 新增 ReworkTicketGenerator（返工任务生成器）、ReworkTicketPlan（返工任务计划）、ReworkTicketOverrides（返工覆盖项）和 ReworkTicketGenerationResult（返工任务生成结果）；负例覆盖 approved/escalate verdict（批准/升级结论）、ticket/verdict mismatch（任务/结论不匹配）、缺 blocker、空 blocker 文本、未知 acceptance_ref（验收引用）、畸形 ticket scope（任务范围）、allowed_read_refs 非字符串、allowed_write_set 扩展、naive generated_at（无时区生成时间）、extra input fields（额外输入字段）、result/payload mismatch（结果/载荷不一致）和 EventRecord 越界；正例证明 missing/failed/manual blocker（缺失/失败/手动阻断项）生成 `depends_on=()` 的 rework ticket，allowed_read_refs 使用 `.value` 字符串，purpose override（目的覆盖）仍保留 original/blocker trace（原任务/阻断项追踪），并通过 TicketReducer（任务状态归约器）证明 original ticket BLOCKED（原任务阻塞）且 rework ticket READY（返工任务就绪）。验证命令：`PYTHONPATH="src:." python -m pytest tests/evidence/test_rework_ticket_generation.py -q`（42 passed）；`PYTHONPATH="src:." python -m pytest tests/evidence/test_checker_verdict.py tests/evidence/test_rework_ticket_generation.py -q`（85 passed）；`PYTHONPATH="src:." python -m pytest tests/reducers/test_ticket_reducer_transitions.py tests/evidence/test_rework_ticket_generation.py -q`（54 passed）；`PYTHONPATH="src:." python -m pytest tests/contracts tests/reducers tests/execution tests/evidence tests/negative -q`（777 passed）。

### V2-050F: evidence 与 reducer 集成门禁

- 状态：DONE
- 目标：把 verified evidence + checker verdict 接入 reducer 的 ticket completion gate。
- 输入文档：`execution-and-runtime-boundary.md`、`contract-and-evidence-model.md`、`decisions.md`（DEC-0011 / DEC-0014）。
- 依赖：V2-050E、V2-020D。
- 输出文件：`src/boardroom_os/reducers/completion_gate.py`、`tests/reducers/test_completion_gate_with_evidence.py`。
- 必须先写的 negative tests：checker approved 但 evidence table missing、evidence complete 但 checker blocker、attempt count 为 0、缺 `WORK_PRODUCT_SUBMITTED` 历史事实、任一 verified evidence 关联的 fallback decision allowed=False、缺 `FALLBACK_DECISION_RECORDED` lineage 必须阻断 completion。
- 必须证明的 happy path：evidence complete + checker approved + provider attempts recorded + work product submitted + fallback decisions all allowed 时 reducer 可完成 ticket。
- 验收口径：ticket completion 不由 runtime 或 checker 单独决定；V2-050F 只能适配正式 evidence/checker 模型到既有 completion boundary，不能绕过 work product、provider attempt 或 fallback decision 门禁。
- 完成证据：2026-05-22 新增 CompletionGate（完成门禁）、CompletionGateInput（完成门禁输入）和 CompletionGateResult（完成门禁结果）；负例覆盖 checker/evidence/provider/work_product/fallback/reducer history（检查结论/证据/模型调用/工作产物/降级/归约历史）；正例覆盖 primary evidence（主路径证据）、approved_with_non_blocking_notes（带非阻断备注批准）、allowed deterministic fallback lineage（允许的确定性降级来源链）和 TicketReducer（任务状态归约器）completion；验证命令：`PYTHONPATH="src:." python -m pytest tests/reducers/test_completion_gate_with_evidence.py -q`（28 passed）；`PYTHONPATH="src:." python -m pytest tests/reducers/test_ticket_reducer_transitions.py tests/evidence/test_final_evidence_table.py tests/evidence/test_checker_verdict.py tests/evidence/test_fallback_policy_registry.py tests/evidence/test_evidence_verifier.py tests/reducers/test_completion_gate_with_evidence.py -q`（111 passed）；`PYTHONPATH="src:." python -m pytest tests/contracts tests/reducers tests/execution tests/evidence tests/negative -q`（805 passed）。

---

## V2-060: Workspace + Package Assembler（工作区与项目包装配器）

- 状态：DONE
- 目标：生成目标项目 workspace、run manifest、package contract 文件、source inventory、agent asset import manifest 和最终 package assembly。
- 输入文档：`generated-project-workspace.md`、`contract-and-evidence-model.md`。
- 输出目录：`src/boardroom_os/workspace/`、`tests/proving/`、`tests/negative/`。
- 顶层验收口径：source inventory 来自 package root + git/hash，不来自 payload 猜测；最终产物是 generated project package；外部 agent assets（智能体资产）只能在 package workspace 阶段导入为 `00-boardroom/agents/` 快照。
- V2-060 Workspace（工作区）必须消费 V2-010F 产出的 `docs_template_key`（文档模板键）与 `documentation_obligations`（文档义务），不得在 assembler（装配器）中重新解释 methodology（方法论）。
- ExecutionPackage compiler（执行包编译器）必须保持可在 0 外部文件输入下运行：它只消费已编译 registry / contract / graph / seat assignment，不负责同步外部 skill、prompt 或 MCP 资产。

### V2-060A: 实现 workspace manifest

- 状态：DONE
- 目标：表达 `00-boardroom`、`10-project`、`20-evidence`、`30-audit` 的逻辑结构，但不把它误作本 repo 结构。
- 输入文档：`generated-project-workspace.md`。
- 依赖：V2-010D。
- 输出文件：`src/boardroom_os/workspace/__init__.py`、`src/boardroom_os/workspace/manifest.py`、`tests/proving/test_workspace_manifest.py`。
- 必须先写的 negative tests：package root 不在 workspace 内、缺 10-project、缺 20-evidence 必须失败。
- 必须证明的 happy path：tiny workspace manifest 可定位 package root、evidence root、audit root。
- 验收口径：workspace 是 generated project 的 staging area，不是框架源码布局。
- 完成证据：2026-05-22 新增 WorkspaceManifest（工作区清单）与 WorkspacePath（工作区路径），固定四区 `00-boardroom` / `10-project` / `20-evidence` / `30-audit`，生成 deterministic `workspace-manifest.<workflow_ref>`，并拒绝绝对路径、Windows drive、`..`、`.`、空 segment、反斜杠、尾部斜杠、缺 project/evidence、重复 section、非 canonical section path、extra fields、workspace_root 落入框架 repo layout（`src`、`src/boardroom_os`、`tests`、`doc`、`scripts`、`examples`、`backend`）、workspace_manifest_id 与 workflow_ref 不匹配，以及 `package_contract.package_root != 10-project`。Negative / happy tests 由 `tests/proving/test_workspace_manifest.py` 覆盖；正向路径证明 tiny PackageContract（微型包合同）可构建 manifest 并定位 boardroom/package/evidence/audit roots、`full_section_path`，`model_dump` section order 稳定，重复构建稳定。验证命令：`PYTHONPATH="src:." python -m pytest tests/proving/test_workspace_manifest.py -q`（46 passed）；`PYTHONPATH="src:." python -m pytest tests/contracts/test_package_contract.py tests/proving/test_workspace_manifest.py -q`（49 passed）；`PYTHONPATH="src:." python -m pytest -q`（853 passed）。副作用检查：未创建 `workspace/`、`00-boardroom/`、`10-project/`、`20-evidence/`、`30-audit/`。

### V2-060B: 实现 package assembler

- 状态：DONE
- 目标：把 source surfaces、docs、run manifest、package contract 装配到 `10-project`。
- 输入文档：`generated-project-workspace.md`、`PackageContract`（包合同）。
- 依赖：V2-060A。
- 输出文件：`src/boardroom_os/workspace/assembler.py`、`tests/proving/test_package_assembler.py`。
- 必须先写的 negative tests：缺 package-contract.json、缺 run-manifest.json、source 写到 package root 外必须失败。
- 必须证明的 happy path：tiny package 包含 README、AGENTS、package-contract、run-manifest、src/tests 或 backend/frontend/tests。
- 验收口径：交付物是 package，不是离散文件列表。
- 完成证据：2026-05-23 新增 PackageArtifact（包产物）、PackageArtifactPath（包产物路径）、PackageArtifactKind（包产物类型）、PackageAssembly（项目包装配结果）和 assemble_package（装配项目包函数）；保持纯装配计划 + 校验边界，不创建目录、不写文件、不计算 hash、不构建 SourceInventory（源码清单）。负例证明缺 package-contract.json、缺 run-manifest.json、source artifact（源码产物）写到 package root（包根）外、unsafe path（不安全路径）、framework repo prefix（框架仓库前缀）、manifest/contract mismatch（清单/合同不匹配）、缺 README/AGENTS、软件包缺 source/test、docs_required 缺 DOC artifact（文档产物）、未知 source_surface_ref（源码实现面引用）、acceptance_ref 越界、source surface path 未覆盖、重复 artifact path（产物路径）和错误 artifact_kind（产物类型）均 fail closed；正例证明 tiny full-stack package（微型全栈包）包含 README、AGENTS、package-contract、run-manifest、backend/frontend/tests/docs，并生成 deterministic PackageAssembly（确定性项目包装配结果）。验证命令：`PYTHONPATH="src;." python -m pytest tests/proving/test_package_assembler.py -q`（40 passed in 0.13s）；`PYTHONPATH="src;." python -m pytest tests/proving/test_workspace_manifest.py tests/proving/test_package_assembler.py -q`（86 passed in 0.21s）；`PYTHONPATH="src;." python -m pytest tests/contracts/test_package_contract.py tests/negative/test_package_contract_fail_closed.py tests/proving/test_workspace_manifest.py tests/proving/test_package_assembler.py -q`（101 passed in 0.18s）；`PYTHONPATH="src;." python -m pytest tests/contracts tests/proving/test_workspace_manifest.py tests/proving/test_package_assembler.py -q`（117 passed in 0.21s）。副作用检查：未创建目录、未写文件、未复制文件，扫描仅命中 PurePosixPath / PureWindowsPath 路径校验。

### V2-060C: 实现 source inventory builder

- 状态：DONE
- 目标：从 package root 和 git/hash 构建 SourceInventory（源码清单）。
- 输入文档：`contract-and-evidence-model.md`。
- 依赖：V2-060B、V2-050B。
- 输出文件：`src/boardroom_os/workspace/source_inventory.py`、`tests/proving/test_source_inventory.py`、`tests/negative/test_source_inventory_ref_only_rejected.py`。
- 必须先写的 negative tests：只证明 ref 存在、缺 sha256、缺 producer_ticket_ref、缺 producer_attempt_ref、缺 acceptance_refs、缺 evidence_refs 必须失败。
- 必须证明的 happy path：package root 内文件可映射到 source_surface、producer ticket、attempt 和 evidence。
- 验收口径：source inventory 证明 implementation lineage（实现来源链路）。
- 完成证据：2026-05-23 新增 SourceInventory（源码清单）、SourceFileRecord（源码文件记录）、SourceLineageRecord（源码来源链记录）、SourceInventoryEntry（源码清单条目）、PackageCommitRef（包提交引用）和 build_source_inventory（构建源码清单函数）；保持纯领域模型边界，不读取文件系统、不调用 git、不写 `20-evidence`，并明确只把 SOURCE / TEST / DOC package artifacts（源码/测试/文档包产物）作为 implementation-bearing artifacts（承载实现的产物），run-manifest 由 V2-060D 证明。负例证明 ref-only PackageAssembly（只有引用的项目包装配结果）、缺 sha256、缺 producer_ticket_ref、缺 producer_attempt_ref、缺 acceptance_refs、缺 evidence_refs、unsafe source path（不安全源码路径）、重复 source/lineage path、source/lineage/package artifact 不一致、未知 source surface、surface/acceptance 覆盖不一致、scalar tuple refs（标量元组引用）和 package contract mismatch（包合同错配）均 fail closed；正例证明 package files 可稳定映射到 source_surface、producer TicketId（任务 ID）、ProviderAttemptRef（模型调用尝试引用）、VerifiedEvidenceRef（已验证证据引用）和 audit-friendly model_dump（审计友好转储）。验证命令：`PYTHONPATH="src;." python -m pytest tests/negative/test_source_inventory_ref_only_rejected.py tests/proving/test_source_inventory.py -q`（36 passed in 0.18s）；`PYTHONPATH="src;." python -m pytest tests/contracts/test_package_contract.py tests/negative/test_package_contract_fail_closed.py tests/proving/test_workspace_manifest.py tests/proving/test_package_assembler.py tests/negative/test_source_inventory_ref_only_rejected.py tests/proving/test_source_inventory.py -q`（137 passed in 0.27s）；`PYTHONPATH="src;." python -m pytest tests/contracts tests/proving/test_workspace_manifest.py tests/proving/test_package_assembler.py tests/negative/test_source_inventory_ref_only_rejected.py tests/proving/test_source_inventory.py -q`（153 passed in 0.27s）。

### V2-060D: 实现 run manifest 与 command binding

- 状态：DONE
- 目标：把 package contract 的 run/test commands 落到 run manifest，并供 CommandRunner 校验。
- 输入文档：`generated-project-workspace.md`、`execution-and-runtime-boundary.md`。
- 依赖：V2-060B、V2-040D。
- 输出文件：`src/boardroom_os/workspace/run_manifest.py`、`tests/proving/test_run_manifest.py`；同步调整 `src/boardroom_os/execution/runtime_executor.py` 的 CommandRunner（命令执行器）延迟导入边界，避免独立导入 runner 时形成循环导入。
- 必须先写的 negative tests：软件项目缺 run/test commands、runner 执行未声明命令、manifest 命令与 PackageContract 不一致必须失败。
- 必须证明的 happy path：declared command 可被 runner 执行并生成 verification evidence。
- 验收口径：可运行软件项目必须有可验证 run/test commands。
- 完成证据：2026-05-23 新增 RunManifest（运行清单）、RunManifestCommand（运行清单命令）、RunManifestBinding（运行清单绑定）和 build_run_manifest / validate_run_manifest_binding（运行清单构建/绑定校验入口）；同步导出 `boardroom_os.workspace` public API（公开入口），并将 `RuntimeExecutor`（运行时执行器）中的 CommandRunner（命令执行器）改为执行时延迟导入，避免干净进程独立导入 `boardroom_os.adapters.process_runner` 时触发循环导入。负例覆盖 software/mixed package 缺 run/test commands、未声明 command、manifest/contract command label/command/cwd/kind 不一致、manifest 缺/多 declared command、重复 command_id、空 command / command item / cwd、extra fields、workspace/package contract ref mismatch（工作区/包合同引用不匹配）、package root mismatch（包根不匹配）、非 canonical `10-project` package root 和伪造 run_manifest_id 均 fail closed；documentation package 可无 commands。正例证明 declared command 先通过 validate_run_manifest_binding，再使用 binding.command_id 串联 CommandRunner.run，生成真实 VerificationRun（验证运行）及 stdout/stderr refs（标准输出/错误引用）。验证命令：`PYTHONPATH="src;." python -c "from boardroom_os.adapters.process_runner import CommandRunner; print(CommandRunner.__name__)"`（输出 `CommandRunner`）；`PYTHONPATH="src;." python -m pytest tests/proving/test_run_manifest.py -q`（28 passed）；`PYTHONPATH="src;." python -m pytest tests/execution/test_command_runner.py -q --basetemp=.pytest_cache/tmp-command-runner`（36 passed）；`PYTHONPATH="src;." python -m pytest tests/execution/test_command_runner.py tests/proving/test_run_manifest.py -q --basetemp=.pytest_cache/tmp-run-manifest-command-runner`（60 passed）；`PYTHONPATH="src;." python -m pytest tests/proving/test_workspace_manifest.py tests/proving/test_package_assembler.py tests/proving/test_source_inventory.py tests/proving/test_run_manifest.py -q --basetemp=.pytest_cache/tmp-workspace-proving`（112 passed）。

### V2-060E: workspace/package 与 evidence 集成

- 状态：DONE
- 目标：把 source inventory、run manifest、verification runs 和 final evidence table 汇入 `20-evidence`。
- 输入文档：`generated-project-workspace.md`、`contract-and-evidence-model.md`。
- 依赖：V2-060C、V2-060D、V2-050C。
- 输出文件：`src/boardroom_os/workspace/evidence_export.py`、`tests/proving/test_workspace_evidence_export.py`。
- 必须先写的 negative tests：final evidence table 缺 blocking criterion、source inventory 缺 lineage、verification runs 缺 stdout/stderr refs 时不得导出 closeout-ready evidence。
- 必须证明的 happy path：`20-evidence` 形成可供 closeout 消费的 evidence bundle。
- 验收口径：package assembly 与 evidence assembly 同步，不允许先交付再补证据。
- 完成证据：2026-05-23 新增 WorkspaceEvidenceBundle（工作区证据包）、EvidenceBundleArtifact（证据包产物）、EvidenceBundleArtifactPath（证据包产物路径）、EvidenceBundleArtifactKind（证据包产物类型）和 build_workspace_evidence_bundle（构建工作区证据包函数）；保持纯 bundle plan（证据包计划）边界，不创建目录、不写 `20-evidence` JSON、不复制 stdout/stderr、不重新运行命令、不调用 git、不重新验证 EvidenceClaim（证据声明）。负例覆盖 FinalEvidenceTable（最终证据表）missing / failed rows、complete 派生不一致、SourceInventory（源码清单）空 entries 和缺 lineage 字段、source inventory/package assembly mismatch（源码清单/项目包装配错配）、VerificationRun（验证运行）缺 stdout_ref 模型层失败、failed status run、重复 verification_run_id、RunManifest（运行清单）workspace mismatch、INV-X1 source inventory evidence refs 不被 final evidence table 承认、FinalEvidenceTable orphan VerifiedEvidenceRef（孤儿已验证证据引用）、INV-X2 orphan VerificationRun（孤儿验证运行）、非 `20-evidence` artifact path（产物路径）和伪造 closeout_ready 均 fail closed。正例证明 `20-evidence/source-inventory/source-inventory.json`、`20-evidence/tests/verification-runs.json`、`20-evidence/tests/run-manifest.json`、`20-evidence/closeout/final-evidence-table.json`、`20-evidence/closeout/evidence-bundle-manifest.json` 五类 logical artifacts（逻辑产物）可按确定性顺序生成，且 refs 在 WorkspaceManifest / PackageAssembly / SourceInventory / RunManifest / VerificationRun / VerifiedEvidence / FinalEvidenceTable 之间闭合。验证命令：`PYTHONPATH="src;." python -m pytest tests/proving/test_workspace_evidence_export.py -q`（17 passed in 0.22s）；`PYTHONPATH="src;." python -m pytest tests/proving/test_workspace_evidence_export.py tests/proving/test_source_inventory.py tests/proving/test_run_manifest.py tests/evidence/test_final_evidence_table.py tests/evidence/test_evidence_verifier.py -q`（65 passed in 0.25s）；`PYTHONPATH="src;." python -m pytest tests/proving -q`（129 passed in 0.28s）。

### V2-060F: 导入 agent asset bundle

- 状态：DONE
- 目标：把外部预置的 role config、skill file、prompt file 和 MCP interface manifest 导入为 generated project workspace 内的 `00-boardroom/agents/` 快照，并记录来源链。
- 输入文档：`generated-project-workspace.md`、`agent-team-model.md`、`process-audit-and-replay.md`。
- 依赖：V2-060A、V2-030A。
- 输出文件：`src/boardroom_os/workspace/agent_asset_import.py`、`tests/proving/test_agent_asset_import.py`。
- 必须先写的 negative tests：导入目标写到 `00-boardroom/agents/` 外、缺 `asset-import-manifest.yaml`、manifest 缺 source_ref/source_kind/imported_at、导入项缺 source_path/target_path/sha256、静默覆盖已有不同 hash 资产必须失败。
- 必须证明的 happy path：本地 agent asset bundle 可被复制/物化为 `00-boardroom/agents/` 快照，生成 `asset-import-manifest.yaml`，并保留 role/skill/prompt/MCP 文件的 source lineage（来源链）。
- 验收口径：外部 skill/prompt/MCP 资产是 workspace/package 阶段的可审计输入，不是 ExecutionPackage compiler 的运行时外部依赖；既有项目更新资产必须产生新 ref 或显式导入记录，不能静默改写。
- 完成证据：2026-05-23 新增 AgentAssetImportManifest（智能体资产导入清单）、AgentAssetImportBatch（智能体资产导入批次）、AgentAssetImportEntry（智能体资产导入条目）、AgentAssetMaterializationResult（智能体资产物化结果）、validate_agent_asset_registry_bindings（校验智能体资产注册表绑定函数）、dump_agent_asset_import_manifest（导出资产导入清单函数）和 materialize_agent_assets（物化智能体资产函数）；实现本地 agent asset bundle（智能体资产包）复制/物化到 `00-boardroom/agents/`，并写出 canonical JSON 内容的 `asset-import-manifest.yaml`。负例覆盖 unsafe source/target/manifest paths（不安全来源/目标/清单路径）、Windows drive/backslash（Windows 盘符/反斜杠）、缺 manifest/batch/entry 字段、naive imported_at（无时区导入时间）、sha256 mismatch（哈希不一致）、source missing/directory/symlink（来源缺失/目录/符号链接）、registry binding gap（注册表绑定缺口）、target overwrite（目标覆盖）、existing manifest 非 prefix（既有清单非前缀）、mutated historical batch（历史批次被改写）和 historical target missing/changed（历史目标缺失/变更）均 fail closed。正例证明四类 role/skill/prompt/MCP asset 可写入快照、项目可只导入实际使用 asset kind 子集、相同 manifest 幂等重跑、追加新 source_ref batch 不改写历史、canonical JSON dump 稳定且不包含宿主绝对路径；ExecutionPackage compiler（执行包编译器）边界回归保持 0 外部文件输入。验证命令：`PYTHONPATH="src;." python -m pytest tests/proving/test_agent_asset_import.py -q --basetemp=.pytest-tmp`（45 passed, 2 skipped）；`PYTHONPATH="src;." python -m pytest tests/proving -q --basetemp=.pytest-tmp-proving`（174 passed, 2 skipped）；`PYTHONPATH="src;." python -m pytest tests/execution/test_execution_package_compiler.py tests/execution/test_agent_profiles.py tests/proving/test_agent_asset_import.py -q --basetemp=.pytest-tmp-compiler`（58 passed, 2 skipped）；`PYTHONPATH="src;." python -m pytest tests/contracts tests/reducers tests/execution tests/evidence tests/proving tests/negative -q --basetemp=.pytest-tmp-all`（1015 passed, 2 skipped）。

---

## V2-070: Closeout + Replay + Process Audit（收尾、重放与流程审计）

- 状态：IN_PROGRESS
- 目标：实现 closeout gate、replay bundle、process audit 和 git audit。
- 输入文档：`process-audit-and-replay.md`、`contract-and-evidence-model.md`。
- 输出目录：`src/boardroom_os/closeout/`、`src/boardroom_os/audit/`、`tests/closeout/`、`tests/negative/`。
- 顶层验收口径：缺 replay bundle 或 evidence map 不能 terminal success；process audit 能回答关键治理问题。

### V2-070A: 实现 closeout gate

- 状态：DONE
- 目标：检查 graph、source inventory、final evidence table、package contract、commands、provider attempts、git audit、replay、process audit。
- 输入文档：`contract-and-evidence-model.md`。
- 依赖：V2-050F、V2-060E。
- 输出文件：`src/boardroom_os/closeout/gate.py`、`tests/closeout/test_closeout_gate.py`、`tests/negative/test_closeout_fail_closed.py`。
- 必须先写的 negative tests：缺 replay bundle、缺 evidence map、open blocker、provider attempt count 为 0、git dirty、任一 declared command 未经 RunManifestBinding 即被用作 final command evidence 必须失败。
- 必须证明的 happy path：所有 gate 输入 ready 时 closeout verdict passed。
- 验收口径：closeout 只收束已证明事实。
- 完成证据：2026-05-24 新增 CloseoutGate（收尾门禁）typed readiness summaries（类型化就绪摘要）与 fail-closed evaluator（失败关闭判定器），覆盖 replay/git/process audit readiness、FinalEvidenceTable（最终证据表）、SourceInventory（源码清单）、WorkspaceEvidenceBundle（工作区证据包）、RunManifestBinding（运行清单绑定）、CheckerVerdict（检查结论）、ProviderAttemptRef（模型调用尝试引用）、package commit / final commit 一致性和 fallback decision lineage（降级判定来源链）；`PYTHONPATH=src pytest tests/negative/test_closeout_fail_closed.py tests/closeout/test_closeout_gate.py -q` 通过（27 passed）；`PYTHONPATH="src;." pytest -q --basetemp=.pytest_tmp` 通过（1042 passed, 2 skipped）。

### V2-070B: 实现 replay bundle builder

- 状态：DONE
- 目标：产出 event range、projection versions、artifact manifest、hash manifest 和 replay report。
- 输入文档：`process-audit-and-replay.md`、`decisions.md`（DEC-0011）。
- 依赖：V2-020F、V2-060E。
- 输出文件：`src/boardroom_os/audit/replay_bundle.py`、`tests/closeout/test_replay_bundle.py`。
- 必须先写的 negative tests：event range 缺失、projection version 不匹配、artifact hash 缺失、event log hash chain / hash manifest 缺失、replay report 缺失必须失败。
- 必须证明的 happy path：事件 + artifact manifest + hash manifest 可重建 typed summary，并证明 replay 输入未被静默篡改。
- 验收口径：缺 replay bundle 不允许 terminal success；hash chain / hash manifest 在 replay bundle 层处理，不回填到 Phase 2 的 InMemoryEventLog 最小接口。
- 完成证据：2026-05-24 新增 ReplayBundle（重放包）builder、ReplayAttestation（重放证明条目）、ReplayPayloadManifest（重放载荷清单）、ReplayArtifactManifest（重放产物清单）、ReplayHashManifest（重放哈希清单）、ReplayReport（重放报告）和 `replay_bundle_readiness`（重放包就绪摘要投影）；首版只允许 `seat_assignment_graph`（席位分配图）证明条目，复用 CloseoutGate（收尾门禁）的 `ReplaySummaryHash` / `EventRangeRef` / `ProjectionVersionRef` 类型，归档 EventRecord（事件记录）切片并在 readiness 中重算 event hash chain（事件哈希链）与 manifest hashes（清单哈希）。Negative tests 覆盖缺 event range、projection version 不匹配、artifact/hash/report 缺失、placeholder sha256、unsafe content_ref、projection_summary.graph_version mismatch、event_hash 篡改后同步重算仍失败、EVENT_WINDOW content_ref 篡改后同步重算仍失败；happy path 证明 replay bundle 可生成 `ReplayBundleReadiness` 并与 hash manifest 独立闭合。验证证据：`PYTHONPATH="src;." python -m pytest tests/closeout/test_replay_bundle.py -q` 通过（59 passed）；`PYTHONPATH="src;." python -m pytest tests/reducers/test_projection_replay.py tests/closeout/test_replay_bundle.py -q` 通过（70 passed）；`PYTHONPATH="src;." python -m pytest tests/negative/test_closeout_fail_closed.py tests/closeout/test_closeout_gate.py tests/closeout/test_replay_bundle.py -q` 通过（86 passed）；完整套件首次因 Windows pytest 临时目录权限失败，改用 `--basetemp=/tmp/boardroom-os-pytest` 后 `PYTHONPATH="src;." python -m pytest tests/contracts tests/reducers tests/execution tests/evidence tests/proving tests/closeout tests/negative -q --basetemp=/tmp/boardroom-os-pytest` 通过（1101 passed, 2 skipped）。

### V2-070C: 实现 process audit builder

- 状态：DONE
- 目标：生成人类可读 process audit（流程审计），解释需求、决策、角色、上下文、ticket、evidence 和 closeout。生成 `30-audit/` 全部 10 项产物。
- 输入文档：`process-audit-and-replay.md`。
- 依赖：V2-030F、V2-050C、V2-060E。
- 输出文件：`src/boardroom_os/audit/process_audit.py`、`src/boardroom_os/audit/__init__.py`、`tests/closeout/test_process_audit.py`、`tests/closeout/test_process_audit_artifacts.py`。
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
  - fallback artifact 缺 `fallback decision -> verifier -> evidence map -> closeout` lineage 必须失败
  - `evidence-map.json` 与 final evidence table 不一致必须失败
  - `git-version-audit.md` 缺 final commit / dirty status / source inventory hash 必须失败
- 必须证明的 happy path：audit 能回答"谁做了什么决策、agent 收到什么上下文、哪些 evidence 满足哪些 acceptance、最终 git 状态是什么、replay 是否可重建"。10 项产物全部存在且互相一致。
- 验收口径：process audit 是产品能力，不是 raw event dump；10 项产物缺一不可，且必须互相一致。
- 完成证据：2026-05-24 新增 ProcessAuditBundle（流程审计包）、ProcessAuditArtifact（流程审计产物）、ProcessAuditArtifactManifest（流程审计产物清单）、ProcessAuditHashManifest（流程审计哈希清单）、ProcessAuditReport（流程审计报告）、build_process_audit_bundle（构建流程审计包函数）和 process_audit_readiness（流程审计就绪摘要投影函数），按 V2-070B ReplayBundle（重放包）风格物化 `30-audit/` 十项流程审计产物并闭合 content_ref（内容引用）、sha256（内容哈希）、artifact manifest（产物清单）和 hash manifest（哈希清单）。Negative tests 覆盖十项必需 artifact 缺失、额外/重复/unsafe path、timeline key event 缺失、decision log 缺 CEO / human board decision、agent context index 缺 execution package / model profile / provider attempts、主 artifact lineage 和 fallback lineage 缺失、evidence map 与 FinalEvidenceTable（最终证据表）不一致、git version audit markdown 缺 final commit / dirty status / source inventory hash、replay bundle report mismatch 和 hash manifest mismatch；happy path 证明 bundle materialization（包物化）、hash manifest closure（哈希清单闭合）、CloseoutGate（收尾门禁）readiness projection（就绪投影）、audit-friendly JSON（审计友好 JSON）、report indexing（报告索引）、标准 Markdown human readability（人类可读 Markdown）、真实 EventRecord（事件记录）timeline projection（时间线投影）和 typed builder boundary（类型化构建输入边界）。验证证据：`PYTHONPATH="src;." python -m pytest tests/closeout/test_process_audit_artifacts.py tests/closeout/test_process_audit.py -q` 通过（41 passed in 0.53s）；`PYTHONPATH="src;." python -m pytest tests/negative/test_closeout_fail_closed.py tests/closeout/test_replay_bundle.py tests/closeout/test_process_audit_artifacts.py tests/closeout/test_process_audit.py -q` 通过（128 passed in 0.66s）；`PYTHONPATH="src;." python -m pytest tests/contracts tests/reducers tests/execution tests/evidence tests/proving tests/closeout tests/negative -q --basetemp=.pytest-tmp-v2070c-final` 通过（1142 passed, 2 skipped in 1.91s）。

### V2-070D: 实现 git version audit

- 状态：DONE
- 目标：记录 final package commit、dirty status、diff summary、source inventory hash 和 final command evidence。
- 输入文档：`process-audit-and-replay.md`。
- 依赖：V2-060C、V2-060D。
- 输出文件：`src/boardroom_os/adapters/git_audit.py`、`src/boardroom_os/audit/git_version_audit.py`、`tests/closeout/test_git_version_audit.py`。
- 必须先写的 negative tests：dirty package、source inventory hash 不匹配、final commands 不是最终 commit 运行必须失败。
- 必须证明的 happy path：clean package commit 可生成 git audit summary。
- 验收口径：closeout 可证明最终版本是什么。
- 完成证据：2026-05-24 新增 GitVersionAuditBundle（Git 版本审计包）、GitVersionAuditFactSet（Git 版本审计事实集）、GitCommandEvidenceBinding（Git 命令证据绑定）、GitVersionAuditReport（Git 版本审计报告）、GitVersionAuditHashManifest（Git 版本审计哈希清单）、build_git_version_audit_bundle（构建 Git 版本审计包函数）、git_version_audit_readiness（Git 版本审计就绪摘要投影函数）和 GitAuditAdapter（Git 审计适配器）。Negative tests 覆盖 dirty package（脏项目包）、source inventory hash mismatch（源码清单哈希不匹配）、final command evidence（最终命令证据）不在 final commit（最终提交）、SourceInventory.package_commit_ref（源码清单项目提交引用）不匹配、缺/孤儿 command evidence binding（命令证据绑定）、未声明 RunManifest command（运行清单命令）、失败 VerificationRun（验证运行）、hash manifest mismatch（哈希清单不匹配）、raw dict / scalar tuple input（原始字典/标量元组输入）、无时区 generated_at（生成时间）、placeholder source inventory hash（占位源码清单哈希）、git command failure（Git 命令失败）和 write git command（写 Git 命令）均 fail closed。Happy path 证明 clean package commit（干净项目包提交）可生成 GitVersionAuditBundle，投影为 CloseoutGate（收尾门禁）可消费的 GitAuditReadiness（Git 审计就绪摘要），source_inventory_hash（源码清单哈希）确定性重算，hash manifest（哈希清单）闭合，JSON 审计友好且 GitAuditAdapter 可通过可注入 transport（传输层）采集 Git facts（Git 事实）。验证证据：`PYTHONPATH="src;." python -m pytest tests/closeout/test_git_version_audit.py -q` 通过（21 passed in 0.32s）；`PYTHONPATH="src;." python -m pytest tests/closeout -q` 通过（128 passed in 0.71s）；`PYTHONPATH="src;." python -m pytest tests/negative -q` 通过（304 passed in 0.43s）；初次 proving/full run 受 Windows pytest temp 权限阻断，改用仓库内 basetemp 后 `PYTHONPATH="src;." python -m pytest tests/proving -q --basetemp=.pytest-tmp-v2-070d-proving` 通过（174 passed, 2 skipped in 0.56s），`PYTHONPATH="src;." python -m pytest tests -q --basetemp=.pytest-tmp-v2-070d-all` 通过（1163 passed, 2 skipped in 1.83s）。

### V2-070E: 实现 CloseoutPackage

- 状态：DONE
- 目标：把 closeout gate 结果、source inventory、evidence table、replay bundle、process audit 和 git version audit 绑定为最终收尾包。
- 输入文档：`domain-model.md`、`contract-and-evidence-model.md`、`doc/04-implementation/v2-070e-closeout-package-spec.md`。
- 依赖：V2-070A、V2-070B、V2-070C、V2-070D。
- 输出文件：`src/boardroom_os/closeout/package.py`、`tests/closeout/test_closeout_package.py`；同步升级 `src/boardroom_os/audit/process_audit.py` 以消费完整 `GitVersionAuditBundle`。
- 必须先写的 negative tests：closeout package 缺任一必需 typed input、raw dict/scalar refs、blocked gate result、verdict mismatch、version 非 1、naive generated_at、gate result id mismatch、source inventory / git audit / replay / process readiness mismatch、project_ref mismatch、unsafe checked_refs 均必须失败。
- 必须证明的 happy path：passed CloseoutPackage 可稳定绑定完整 closeout gate result、SourceInventory、FinalEvidenceTable、ReplayBundle、ProcessAuditBundle 和 GitVersionAuditBundle，`checked_refs` 稳定唯一完整且 JSON 审计友好。
- 验收口径：最终完成只由 CloseoutPackage 表达；CloseoutGate 继续消费 readiness summaries，不从 bundle 二次提取事实。

### V2-070F: closeout reducer 集成

- 状态：DONE
- 目标：让 reducer 在 closeout gate passed 后产生 terminal success projection。
- 输入文档：`execution-and-runtime-boundary.md`、`process-audit-and-replay.md`、`decisions.md`（DEC-0011）。
- 依赖：V2-070E、V2-020D。
- 输出文件：`src/boardroom_os/reducers/closeout_reducer.py`、`tests/closeout/test_closeout_reducer.py`。
- 必须先写的 negative tests：runtime 直接 closeout、workflow completed 但 closeout gate missing、缺 replay bundle、增量 reducer/replay 输入缺历史 `WORK_PRODUCT_SUBMITTED` 事实必须失败。
- 必须证明的 happy path：CloseoutPackage passed 事件可投影为 project terminal success；若采用 base projection + new events（基准投影 + 新事件）增量模式，work product 历史必须作为显式 projection/replay 输入保留。
- 验收口径：不把 workflow completed 当作项目完成；closeout reducer 不能依赖 `TicketReducer.reduce()` 调用内局部集合来推断历史 work product。
- 完成证据：2026-05-25 新增 `EventType.CLOSEOUT_COMMITTED`（收尾已提交事件）作为 governance event（治理事件），并保持 `RuntimeEventBoundary`（运行时事件边界）拒绝 runtime emit（运行时发出）；新增 `CloseoutReducer`（收尾归约器）、`CloseoutCommitPayload`（收尾提交载荷）、`CloseoutHistoryProjection`（收尾历史投影）和 `CloseoutProjection`（收尾投影）。Negative tests 覆盖 runtime/executor closeout、workflow completed 替代 closeout、缺 work product 历史、增量历史缺 `WORK_PRODUCT_SUBMITTED`、重复 closeout、已 succeeded base history 再 closeout、graph_version 乱序、cross project、payload/package ref mismatch、缺 replay bundle binding、raw dict payload/package、checked_refs gap 和非 passed terminal verdict 均 fail closed。Happy path 证明 passed CloseoutPackage（通过的收尾包）经 `CLOSEOUT_COMMITTED` 可投影为 project terminal success（项目终态成功），且增量 base_history 必须显式携带 work product history。验证证据：`PYTHONPATH="src;." python -m pytest tests/closeout/test_closeout_reducer.py -q` 通过（28 passed in 1.09s）；`PYTHONPATH="src;." python -m pytest tests/closeout/test_closeout_reducer.py tests/closeout/test_closeout_package.py tests/closeout/test_closeout_gate.py tests/negative/test_closeout_fail_closed.py -q` 通过（69 passed in 1.57s）；`PYTHONPATH="src;." python -m pytest tests/reducers/test_completion_gate_with_evidence.py tests/reducers/test_ticket_reducer_transitions.py tests/closeout/test_closeout_reducer.py -q` 通过（64 passed in 0.99s）；`PYTHONPATH="src;." python -m pytest tests/contracts tests/reducers tests/execution tests/evidence tests/proving tests/closeout tests/negative -q --basetemp=.pytest-tmp-v2070f-all` 通过（1208 passed, 2 skipped in 3.39s）。

---

## V2-071: Closeout fact-chain hardening（收尾事实链强化重构）

- 状态：DONE
- 目标：在不重写 V2-070A~G 实现的前提下，修复 2026-05-25 外部独立审计（`doc/04-implementation/v2-070-batch-review-report.md`）识别的 18 项 P0/P1/P2 缺口，重新固定 V2-070 大阶段的事实链权威源、跨包绑定与确定性哈希契约。
- 输入文档：`doc/04-implementation/v2-070-batch-review-report.md`、`doc/03-architecture/process-audit-and-replay.md`、`doc/03-architecture/contract-and-evidence-model.md`、`doc/05-project-log/decisions.md`（DEC-0016、DEC-0017）。
- 输出目录：`src/boardroom_os/contracts/refs.py`（新建）、复用 `src/boardroom_os/audit/`、`src/boardroom_os/closeout/`、`src/boardroom_os/adapters/`、`src/boardroom_os/reducers/`；`tests/closeout/`、`tests/negative/`、`tests/contracts/` 新增 fail-closed 回归。
- 顶层验收口径：审计报告 P0 1-5 / P1 1-5 / P2 1-5 全部通过独立 negative test 证明已闭合；ProcessAudit 不再要求 `CLOSEOUT_COMMITTED` 出现在事件流中；ReplayBundle 从 events 重新投影而非接受外部 ProjectionReplaySummary；ProcessAudit events 与 ReplayBundle.events 逐条一致；GitAuditAdapter 无任何 fallback；CloseoutPackage.graph_version 严格等于 ReplayBundle.last_graph_version；payload manifest sha256 与真实内容通过 PayloadResolver 校验；所有跨包引用使用 project/run/hash 命名空间；所有集合语义输入按 canonical sort 进入 hash；Phase 7.5 AC checkbox 全部勾选后方可进入 Phase 8。
- 兼容性策略：按 CLAUDE.md hard rule **no second source of truth** 与 **no silent fallbacks**，本次必须删除所有冲突旧 boundary，不保留 backwards-compat shim；测试 fixture 同步迁移。

### V2-071A: 事实链权威源设计 + 跨包命名空间 helper

- 状态：DONE
- 目标：冻结 V2-071 整体事实链设计（CloseoutDomainInputs / CloseoutDomainOutputs 与构造顺序）；抽出共享 ref namespacing helper（引用命名空间助手）与确定性哈希助手，作为后续 V2-071B~E 修改的共同地基。
- 输入文档：`doc/04-implementation/v2-070-batch-review-report.md`、`doc/04-implementation/v2-070g-closeout-closure-hardening-spec.md`、`doc/03-architecture/process-audit-and-replay.md`、`decisions.md`（DEC-0016、DEC-0017）。
- 依赖：V2-070F。
- 输出文件：`doc/04-implementation/v2-071a-fact-chain-design-spec.md`、`src/boardroom_os/contracts/refs.py`、`tests/contracts/test_namespaced_refs.py`、`tests/negative/test_namespaced_refs_fail_closed.py`；同步更新 `src/boardroom_os/contracts/__init__.py`、`doc/04-implementation/INDEX.md`。
- 必须先写的 negative tests：跨包引用缺 `project_ref` namespace（项目引用命名空间）、缺 `run_id` 或 `content_hash` 段、namespace segment 含 unsafe path component（不安全路径段）、命名空间助手对相同输入产生不同 hash、canonical_sort helper 收到非可哈希集合元素必须 fail closed。
- 必须证明的 happy path：`namespaced_ref(project_ref, kind, content_hash, run_id)` 对同一输入稳定返回同一 ref；`canonical_sort_for_hash(values, key=...)` 对乱序输入返回确定性序列；fact-chain 设计文档完整描述 V2-070 构造顺序与禁止外部传入的字段清单。
- 验收口径：V2-071A 不修改任何 070 已有 builder，仅冻结设计并提供共享工具；V2-071B~E 修改必须复用 `boardroom_os.contracts.refs`，禁止在 audit/closeout 模块内自行实现 namespace 拼接。
- 完成证据：2026-05-25 修订 `v2-071a-fact-chain-design-spec.md`，明确 `content_hash` 必须复用 `Sha256Hex`（SHA-256 摘要值对象）并由完整摘要派生短 hash，Git audit ref 使用包含 commit SHA 的 payload hash 而非直接使用 Git SHA-1；新增 `boardroom_os.contracts.refs`（引用命名空间 helper）与 negative / happy tests，覆盖 unsafe namespace segment、短/占位 hash、禁止无 `run_id` 的 `extra_suffix` 单尾段、非 dict / 非 JSONable payload、BaseModel / StrEnum / tuple/list canonicalization、重复 canonical sort key、非字符串 sort key、乱序输入稳定性与 UTF-8 canonical payload hash。验证命令：`PYTHONPATH="src:." python -m pytest tests/contracts/test_namespaced_refs.py tests/negative/test_namespaced_refs_fail_closed.py -q --basetemp=.pytest-tmp-v2071a-review-final-focused` 通过（22 passed）；`PYTHONPATH="src:." python -m pytest tests/contracts tests/closeout -q --basetemp=.pytest-tmp-v2071a-review-regression` 通过（257 passed）。

### V2-071B: ReplayBundle re-replay（从 events 重新投影）

- 状态：DONE
- 目标：让 ReplayBundle（重放包）成为 events 的唯一权威派生，不接受调用方传入的 `ProjectionReplaySummary`（投影回放摘要）内容字段；同步对 manifest entries 进行 canonical sort（规范排序），消除顺序敏感哈希。
- 输入文档：`v2-071a-fact-chain-design-spec.md`、`process-audit-and-replay.md`、V2-070B 产物。
- 依赖：V2-071A。
- 输出文件：`doc/04-implementation/v2-071b-replay-bundle-rereplay-spec.md`、修改 `src/boardroom_os/audit/replay_bundle.py`、`tests/closeout/test_replay_bundle_rereplay.py`、`tests/negative/test_replay_bundle_external_summary_rejected.py`；同步调整 `tests/closeout/test_replay_bundle.py` fixture。
- 必须先写的 negative tests：调用方通过 `ReplayBundleBuilderInput` 直接传入 `ProjectionReplaySummary.nodes` / `seat_assignments` / `blocked_by` 等内容字段必须失败；外部传入的 summary 字段内容与从 events 重新投影的结果不一致必须失败；payload_manifest entries 顺序变化导致 `payload_manifest_hash` 不稳定必须失败；artifact_manifest entries 顺序变化导致 `artifact_manifest_hash` 不稳定必须失败；篡改 events 中任一事件 payload 后 `summary_hash` 必须随之变化（不可静默通过）。
- 必须证明的 happy path：`ReplayBundleBuilderInput` 仅接受 `project_ref`、`events`、manifest refs 与 generated_at，**不再接受 `projection_summary`**；builder 内部调用 `ProjectionReplay.replay_events(...)` 从 events 重新计算 `ProjectionReplaySummary`，并把 `summary_hash` 作为唯一权威 hash 来源写入 `ReplayReport` 与 `ReplayAttestation`；同一组 events 在不同输入顺序下经 canonical sort 产生同一 `replay_bundle_id`。
- 验收口径：ReplayBundle 不再是"调用方提供的 summary 的包装层"；任何对 events 的篡改都会传播到 summary_hash；篡改 summary_hash（已不暴露）不再可能。
- 完成证据：2026-05-26 删除 `ReplayBundleBuilderInput.projection_summary` 外部输入，ReplayBundle（重放包）builder 内部调用 `ProjectionReplay.replay_events(...)` 从 EventRecord（事件记录）重新投影 `ProjectionReplaySummary`（投影回放摘要），以内部 `summary_hash` 作为唯一权威来源写入 `ReplayReport`（重放报告）与 attestation（证明条目）；payload/artifact manifest entries（载荷/产物清单条目）经 `canonical_sort_for_hash` 规范排序后参与 hash；`replay_bundle_id` 改为基于 `namespaced_ref` 的 project/run/hash 命名空间引用。Negative tests 覆盖外部 `projection_summary` 输入被 `extra="forbid"` 拒绝、`model_copy(update=...)` 注入额外 `projection_summary` 被构建入口拒绝、events payload 篡改导致 summary/hash 变化、payload/artifact manifest 输入乱序仍稳定。验证证据：`PYTHONPATH="src:." python -m pytest tests/closeout/test_replay_bundle.py tests/closeout/test_replay_bundle_rereplay.py tests/negative/test_replay_bundle_external_summary_rejected.py -q --basetemp=.pytest-tmp-v2071b-final-targeted` 通过（74 passed）；`PYTHONPATH="src:." python -m pytest tests/closeout tests/negative -q --basetemp=.pytest-tmp-v2071b-final-closeout-negative` 通过（519 passed）；`PYTHONPATH="src:." python -m pytest tests/contracts tests/reducers tests/closeout tests/negative -q --basetemp=.pytest-tmp-v2071b-final-full` 通过（732 passed）。

### V2-071C: ProcessAudit 解构构造环 + events 单一来源

- 状态：DONE
- 目标：解除 ProcessAudit（流程审计）与 CloseoutPackage（收尾包）之间的构造环；ProcessAudit 不再要求 `CLOSEOUT_COMMITTED` 出现在事件流中；ProcessAudit 直接复用 `ReplayBundle.events`，与 ReplayBundle 形成 events 单一权威源；移除 `getattr(..., "unknown")` 占位 fallback、`consumer_ticket_ref` 伪造、`expected_fallback_decision_refs` 为空时不拒绝额外 fallback_lineages 等隐式宽松校验；对 `checked_refs` canonical sort。
- 输入文档：`v2-071a-fact-chain-design-spec.md`、`v2-071b-replay-bundle-rereplay-spec.md`、`process-audit-and-replay.md`、V2-070C 产物。
- 依赖：V2-071B。
- 输出文件：`doc/04-implementation/v2-071c-process-audit-fact-chain-spec.md`、修改 `src/boardroom_os/audit/process_audit.py`、修改 `src/boardroom_os/workspace/source_inventory.py`（若需要新增 `consumer_ticket_refs` 字段以分离 producer / consumer）；`tests/closeout/test_process_audit_fact_chain.py`、`tests/negative/test_process_audit_construction_loop_rejected.py`；同步调整既有 `tests/closeout/test_process_audit.py`、`tests/closeout/test_process_audit_artifacts.py` fixture。
- 必须先写的 negative tests：
  - ProcessAudit 输入事件流不包含 `CLOSEOUT_COMMITTED` 时**必须可成功构造**（旧实现会失败）；
  - ProcessAudit 的 `events` 与 `replay_bundle.events` 任意中间事件 `event_type` / `payload_refs` / `actor_ref` 不一致必须失败；
  - `ticket_graph_summary.tickets[*].status` / `owner_seat_ref` / `ticket_ref` 缺失时不得在 audit 产物中出现 `"unknown"` / `"ticket"` 字面量，必须直接 raise；
  - `agent_context_index.entries[*]` 缺 `snapshot.execution_package_ref` / `snapshot.model_execution_profile` 必须失败（不再依赖顶层平铺字段）；
  - SourceInventory 中 `producer_ticket_ref` 与 `consumer_ticket_ref` 相同但 ticket B 在 evidence chain 中实际消费 ticket A 的产出时，artifact-lineage.json 必须明确分离两者；
  - `expected_fallback_decision_refs` 为空但 artifact-lineage.json 含 `fallback_lineages` 必须失败；
  - `provider_attempt_refs` / `verification_runs` / `verified_evidence` 输入乱序时 `checked_refs` 仍按 canonical sort 产生稳定结果。
- 必须证明的 happy path：ProcessAudit 在 CloseoutPackage 构造**之前**完成，事件流不含 `CLOSEOUT_COMMITTED`；ProcessAudit.events 与 ReplayBundle.events 完全相等（逐条比对，不仅是首尾 event_id）；agent context index 从 `entry.snapshot.*` 读取真实字段；`checked_refs` 在乱序输入下哈希稳定。
- 验收口径：构造顺序变为 `Replay → ProcessAudit → GitAudit → CloseoutPackage → CLOSEOUT_COMMITTED → CloseoutReducer`，与 `closeout_reducer.py` 已实现的 reducer 顺序一致；不再可能在真实流程之外构造 synthetic event 通过 audit。
- 完成证据：2026-05-27 新增 `v2-071c-process-audit-fact-chain-spec.md` 并收紧 ProcessAudit（流程审计）事实链语义：`ProcessAuditBuilderInput`（流程审计构造输入）删除外部 `events` 字段，timeline 与 checked refs 中的事件事实统一来自 `ReplayBundle.events`（重放包事件）；`_REQUIRED_TIMELINE_EVENT_KINDS` 不再要求 `closeout_committed`；ticket graph（任务图）与 AgentContextIndex（智能体上下文索引）缺字段时 fail closed，不再生成 `"unknown"` / `"ticket"` 占位；SourceInventory（源码清单）新增并强制 `consumer_ticket_refs`，artifact-lineage.json 分离 producer/consumer；fallback lineage actual refs 必须与 expected fallback decisions 完全一致；集合语义输入经 `canonical_sort_for_hash`（规范排序哈希 helper）稳定 `checked_refs`。验证证据：`PYTHONPATH="src:." python -m pytest tests/negative/test_process_audit_construction_loop_rejected.py tests/closeout/test_process_audit_fact_chain.py tests/closeout/test_process_audit.py tests/closeout/test_process_audit_artifacts.py -q --basetemp=.pytest-tmp-v2071c-audit` 通过（128 passed in 1.30s）；`PYTHONPATH="src:." python -m pytest tests/closeout tests/negative -q --basetemp=.pytest-tmp-v2071c-audit-regression` 通过（602 passed in 2.46s）。

### V2-071D: Git 审计强化（移除 fallback + 解析正确性 + 确定性哈希）

- 状态：DONE
- 目标：`GitAuditAdapter` 强制 `base_commit_sha` / `worktree_ref` 显式传入，禁止任何 fallback；`git status --porcelain` 改为 `--porcelain=v1 -z` 并按 NUL 分隔解析；`git diff` 统计使用 `--shortstat` 或锚定 summary footer 的 regex；对 `verification_runs` / `command_evidence_bindings` 按 canonical sort 计算 `command_evidence_refs` / `checked_refs` / `bundle_payload_hash`。
- 输入文档：`v2-071a-fact-chain-design-spec.md`、V2-070D 产物。
- 依赖：V2-071A（命名空间 helper 与 canonical sort helper）。
- 输出文件：`doc/04-implementation/v2-071d-git-audit-hardening-spec.md`、修改 `src/boardroom_os/adapters/git_audit.py`、修改 `src/boardroom_os/audit/git_version_audit.py`；`tests/closeout/test_git_audit_hardening.py`、`tests/negative/test_git_audit_fallback_rejected.py`。
- 必须先写的 negative tests：
  - `GitAuditAdapter.collect(base_commit_sha=None, ...)` 必须 raise `GitAuditAdapterError("base_commit_sha is required")`，**不再 fallback 到 `final_commit_sha`**；
  - `GitAuditAdapter.collect(worktree_ref=None, ...)` 必须 raise，**不再 fallback 到 `worktree.{package_root}`**；
  - 文件名含换行 / 引号 / 反斜杠 / 制表符 / ` -> ` 字符串的 `git status` 输出必须能被正确解析（使用 `-z`）；
  - 文件名含 `12 insertions.md` 的 diff 输出不得污染 `GitDiffSummary.insertions` 计数；
  - `verification_runs` 输入顺序变化必须产生**相同** `command_evidence_refs` 与 `bundle_payload_hash`（canonical sort 后稳定）；
  - `command_evidence_bindings` 输入顺序变化同样必须产生稳定 `checked_refs`；
  - `fact_set_id` 必须包含 `final_commit_sha` 段（命名空间助手提供），同一项目不同 commit 不能复用同一 `fact_set_id`。
- 必须证明的 happy path：合法显式传入 base/worktree 的 `GitAuditAdapter.collect(...)` 仍可生成 GitVersionAuditFactSet；`bundle_payload_hash` 在任意输入顺序下稳定；`fact_set_id` 与 `final_commit_sha` 形成强绑定。
- 验收口径：审计报告 P0-4 / P2-1 / P2-4 / P2-5 全部闭合；GitAuditAdapter 不再有任何 silent fallback；Git 解析对特殊文件名鲁棒；同一事实重建得到同一哈希。
- 完成证据：2026-05-27 新增 `v2-071d-git-audit-hardening-spec.md`、`tests/negative/test_git_audit_fallback_rejected.py`、`tests/closeout/test_git_audit_hardening.py`，并收紧 `GitAuditAdapter`（Git 审计适配器）和 `GitVersionAudit`（Git 版本审计）：缺 `base_commit_sha` / `worktree_ref` / `source_inventory_hash` 直接 fail closed；Git status 使用 `--porcelain=v1 -z` 并按 NUL 解析特殊文件名与 rename；Git diff 使用 `--shortstat`；`fact_set_id` 使用 V2-071A namespace helper 并绑定 final commit payload；`verification_runs` 与 `command_evidence_bindings` 经 `canonical_sort_for_hash` 稳定 report、checked_refs、hash manifest 和 bundle payload，`command_binding_hashes` 改用唯一 `binding_id` key。验证证据：`PYTHONPATH=src:. python -m pytest tests/closeout/test_git_version_audit.py tests/closeout/test_git_audit_hardening.py tests/negative/test_git_audit_fallback_rejected.py -q --basetemp=.pytest-tmp-v2071d-git` 通过（34 passed in 0.24s）。

### V2-071E: CloseoutPackage 边界严格化 + payload 内容绑定

- 状态：DONE
- 目标：`CloseoutPackage.graph_version` 严格等于 `ReplayBundle.last_graph_version`（不再允许超过）；引入 `ReplayPayloadResolver` 协议，让 `ReplayBundleReadiness` 在投影时通过 resolver 重新计算 `ReplayPayloadManifest.entries[*].sha256` 并与提供值比较；`artifact_ref` / `content_ref` / `fact_set_id` 全部改用 V2-071A 的 namespace helper；CloseoutPackage / ProcessAudit / ReplayBundle 之间的引用必须经 `assert_namespaced_ref_binding(...)` 校验。
- 输入文档：`v2-071a-fact-chain-design-spec.md`、`v2-071b-replay-bundle-rereplay-spec.md`、`v2-071c-process-audit-fact-chain-spec.md`、V2-070E 产物。
- 依赖：V2-071B、V2-071C。
- 输出文件：`doc/04-implementation/v2-071e-closeout-package-boundary-spec.md`、修改 `src/boardroom_os/closeout/package.py`、修改 `src/boardroom_os/audit/replay_bundle.py`（引入 PayloadResolver 协议）、修改 `src/boardroom_os/audit/process_audit.py` 与 `src/boardroom_os/audit/git_version_audit.py`（namespace 改造）；`tests/closeout/test_closeout_package_boundary.py`、`tests/negative/test_closeout_package_graph_version_overflow_rejected.py`、`tests/negative/test_replay_payload_manifest_tampering_rejected.py`。
- 必须先写的 negative tests：
  - `builder_input.graph_version > replay_bundle.last_graph_version` 时必须 raise `CloseoutPackageError("graph_version must equal replay bundle proof boundary")`；
  - `ReplayPayloadManifest.entries[*].sha256` 与 resolver 重算结果不一致时必须 raise；
  - `ReplayPayloadResolver` 未提供时 `replay_bundle_readiness(...)` 必须降级为只校验 ref 覆盖并显式标记 `payload_sha256_verified=False`，或要求调用方必须传入 resolver（按 spec 选定）；
  - `ProcessAuditArtifactRef(value="process-audit-artifact.{kind}")` 形式被替换为 `namespaced_ref(project_ref, "process-audit-artifact", kind, content_hash=...)`；旧形式被检测到必须 raise；
  - 同一 `project_ref` 多次构建 CloseoutPackage 应得到不同 `closeout_package_id`（基于 run_id / generated_at 命名空间）。
- 必须证明的 happy path：`CloseoutPackage.graph_version == replay_last_graph_version` 时可成功构造；payload resolver 提供真实内容时 sha256 重算通过；所有跨包引用通过 namespace 校验。
- 验收口径：审计报告 P0-5 / P1-1 / P1-5 全部闭合；CloseoutPackage 不再可能声称覆盖超出 Replay 证明边界的状态；artifact 引用不再可能跨 run / 跨 project 串包。
- 完成证据：2026-05-28 新增 `v2-071e-closeout-package-boundary-spec.md` 与 `v2-071e-closeout-package-boundary-implementation-plan.md`，并收紧 ReplayBundle（重放包）、ProcessAudit（流程审计）、GitVersionAudit（Git 版本审计）与 CloseoutPackage（收尾包）边界：`ReplayPayloadResolver`（重放载荷解析器）在 `replay_bundle_readiness(...)` 中必填，缺 resolver / 缺真实 payload / sha256 篡改均 fail closed；`ReplayBundleReadiness`（重放包就绪摘要）新增 `payload_sha256_verified`、`payload_manifest_ref`、`payload_manifest_hash`；CloseoutPackage `graph_version` 必须严格等于 replay proof boundary；ProcessAudit 与 CloseoutPackage 只消费 typed readiness binding（类型化就绪摘要绑定），不再自行重算或回退；ProcessAudit artifact/content refs、ProcessAudit bundle/report/manifest refs、GitVersionAudit bundle/report/hash-manifest refs、CloseoutPackage id 均采用 project/hash/run namespaced ref（命名空间引用）并拒绝旧式或跨 project/run 串包。Negative tests 覆盖 graph_version 上/下越界、payload manifest 篡改、缺 resolver、缺 payload content、旧式 process audit artifact/content refs、非命名空间 closeout package id、跨 project/run process audit refs。Happy path 覆盖 canonical JSON payload hash、payload manifest readiness 绑定、closeout package boundary 等于 replay boundary、checked_refs 包含 payload manifest ref/hash、run_id 改变后包 id 改变。验证证据：`PYTHONPATH=src:. python -m pytest tests/closeout/test_git_version_audit.py tests/closeout/test_git_audit_hardening.py -q --tb=short -rf --basetemp=.pytest-tmp-v2071e-git` 通过（30 passed in 0.27s）；`PYTHONPATH=src:. python -m pytest tests/closeout/test_process_audit.py tests/closeout/test_process_audit_artifacts.py tests/closeout/test_process_audit_fact_chain.py tests/closeout/test_git_version_audit.py tests/closeout/test_git_audit_hardening.py tests/closeout/test_closeout_package.py tests/closeout/test_closeout_package_boundary.py tests/negative/test_process_audit_construction_loop_rejected.py -q --tb=short -rf --basetemp=.pytest-tmp-v2071e-audit` 通过（187 passed in 2.38s）；`PYTHONPATH=src:. python -m pytest tests/contracts tests/reducers tests/execution tests/evidence tests/proving tests/closeout tests/negative -q --basetemp=.pytest-tmp-v2071e-all` 通过（1410 passed in 3.68s）。

### V2-071F: 端到端 fail-closed 回归 + Phase 7 重锁

- 状态：DONE
- 目标：构造一个完整的 V2-070 fact-chain 集成测试（从 EventLog 真实跑到 CloseoutClosure），覆盖审计报告所有 18 项缺口的端到端 negative test；在 V2-070A~G 既有 negative tests 之上新增 fact-chain 级别的回归；重新勾选 Phase 7 验收 checkbox 并补齐 Phase 7.5 验收段；解锁 Phase 8。
- 输入文档：`v2-071a-fact-chain-design-spec.md` ~ `v2-071e-closeout-package-boundary-spec.md`、`acceptance-criteria.md`、`v2-070-batch-review-report.md`。
- 依赖：V2-071A、V2-071B、V2-071C、V2-071D、V2-071E。
- 输出文件：`doc/04-implementation/v2-071f-fact-chain-regression-spec.md`、`tests/closeout/test_v2_070_fact_chain_end_to_end.py`、`tests/negative/test_v2_070_audit_report_p0_regressions.py`、`tests/negative/test_v2_070_audit_report_p1_regressions.py`、`tests/negative/test_v2_070_audit_report_p2_regressions.py`；同步更新 `doc/04-implementation/acceptance-criteria.md` Phase 7.5 段、`doc/04-implementation/backlog.md` 进度总览、`doc/05-project-log/2026-05.md`。
- 必须先写的 negative tests（审计报告 18 项逐条对应）：
  - P0-1：合法事件流不含 `closeout_committed` 时 ProcessAuditBundle 必须可成功构造，且后续 CloseoutPackage 构造完成后再发出 `CLOSEOUT_COMMITTED` 事件经 CloseoutReducer 投影为 succeeded；
  - P0-2：调用方通过 builder 输入伪造 `ProjectionReplaySummary` 内容字段必须被拒绝（V2-071B 已删除该输入字段）；
  - P0-3：ProcessAudit.events 与 ReplayBundle.events 中间事件不一致必须失败；
  - P0-4：GitAuditAdapter 缺 `base_commit_sha` / `worktree_ref` 必须失败；
  - P0-5：CloseoutPackage.graph_version > ReplayBundle.last_graph_version 必须失败；
  - P1-1：ReplayPayloadManifest sha256 被篡改必须失败；
  - P1-2：ProcessAudit 输入缺字段时不得输出 `"unknown"` / `"ticket"` 占位；
  - P1-3：producer ticket 与 consumer ticket 不同时 artifact-lineage.json 必须正确分离；
  - P1-4：`expected_fallback_decision_refs` 为空但 actual fallback lineages 非空必须失败；
  - P1-5：跨 run / 跨 project 的 `fact_set_id` / `artifact_ref` / `content_ref` 串包必须失败；
  - P2-1：GitVersionAudit `verification_runs` 乱序输入哈希必须稳定；
  - P2-2：Replay manifest entries 乱序输入哈希必须稳定；
  - P2-3：ProcessAudit `checked_refs` 乱序输入哈希必须稳定；
  - P2-4：含特殊字符文件名的 `git status` 必须正确解析；
  - P2-5：含 "insertions" 关键字的文件名 diff 输出必须不污染统计。
- 必须证明的 happy path：真实 EventLog（含 work product / provider attempt / command run / verification 等事件，**不含** `closeout_committed`）→ Replay → ProcessAudit → GitAudit → CloseoutGate → CloseoutPackage → `CLOSEOUT_COMMITTED`（governance event）→ CloseoutReducer.terminal_status = SUCCEEDED；CloseoutClosure 闭包校验通过；端到端构造稳定可重复执行 N 次得到字节相同的 readiness 与 hash。
- 验收口径：Phase 7.5 全部 AC checkbox 勾选；`v2-070-batch-review-report.md` 列出的 18 项 P0/P1/P2 缺口均有独立 negative test 证明已闭合；Phase 8 V2-080A 解锁可启动；本工作包完成后 backlog 顶部 TL;DR 的"当前未完成工作包"指向 `V2-080A`。
- 完成证据：2026-05-29 新增 `doc/04-implementation/v2-071f-fact-chain-regression-spec.md`、`tests/closeout/test_v2_070_fact_chain_end_to_end.py`、`tests/negative/test_v2_070_audit_report_p0_regressions.py`、`tests/negative/test_v2_070_audit_report_p1_regressions.py`、`tests/negative/test_v2_070_audit_report_p2_regressions.py`。P0/P1/P2 共 18 项回归均有独立测试函数覆盖；P1-2 使用缺字段 `ProcessAuditBuilderInput` 证明不会生成 `unknown` / `ticket` 占位；P2-4/P2-5 证明特殊 Git 输出解析正确且 dirty facts 不能进入 GitVersionAuditBundle。验证证据：`PYTHONPATH=src:. python -m pytest tests/negative/test_v2_070_audit_report_p0_regressions.py tests/negative/test_v2_070_audit_report_p1_regressions.py tests/negative/test_v2_070_audit_report_p2_regressions.py tests/closeout/test_v2_070_fact_chain_end_to_end.py -q --basetemp=.pytest-tmp-v2071f` 通过（20 passed in 1.27s）；`PYTHONPATH=src:. python -m pytest tests/closeout/test_replay_bundle_rereplay.py tests/closeout/test_process_audit_fact_chain.py tests/closeout/test_git_audit_hardening.py tests/closeout/test_closeout_package_boundary.py tests/closeout/test_closeout_reducer.py tests/closeout/test_closeout_closure_hardening.py -q --basetemp=.pytest-tmp-v2071f-history` 通过（69 passed in 1.36s）；`PYTHONPATH=src:. python -m pytest tests/contracts tests/reducers tests/execution tests/evidence tests/proving tests/closeout tests/negative -q --basetemp=.pytest-tmp-v2071f-all` 通过（1432 passed in 4.74s）。

---

- 状态：TODO
- 目标：端到端生成 tiny book availability tracker，证明 contract-first、reducer-protected、evidence-backed、package-oriented、audit-readable、replayable 的闭环。
- 输入文档：`proving-scenario-tiny-fullstack.md` 和 V2-010~V2-070 产物。
- 输出目录：`tests/proving/`、generated workspace、closeout audit。
- 顶层验收口径：**已撤回**。V2-080A~F 保留 `DONE` 作为历史工作包执行记录；2026-05-31 失败复审证明 V2-080 的证据链未覆盖 declared run commands（声明运行命令）、live frontend/backend integration（真实前后端集成）和 SQLite-over-HTTP persistence（经 HTTP 的 SQLite 持久化），因此 Phase 8 失败复审后结束，不再作为 V2 minimal end-to-end（最小端到端）成立依据。整改转入 V2-090。

### V2-080A: 定义 tiny scenario active contracts

- 状态：DONE
- 目标：为 tiny book availability tracker 生成 ProjectCharter、AcceptanceContract、PackageContract fixture。
- 输入文档：`proving-scenario-tiny-fullstack.md`、V2-010 产物。
- 依赖：V2-010G、V2-071F（Phase 7.5 fact-chain 重构闭合后方可进入 Phase 8）。
- 输出文件：`tests/proving/fixtures/tiny_fullstack_contracts.py`、`tests/proving/test_tiny_contracts.py`。
- 必须先写的 negative tests：缺 API/UI/persistence/run/test acceptance refs 时 scenario 无效。
- 必须证明的 happy path：active contracts 能覆盖 full-stack package 的 source surfaces 和 evidence obligations。
- 验收口径：scenario 不使用静态 universal AC。
- 完成证据：2026-05-29 新增 `tests/proving/fixtures/tiny_fullstack_contracts.py`、`tests/proving/fixtures/__init__.py` 和 `tests/proving/test_tiny_contracts.py`。Negative tests 覆盖缺 API / UI / persistence / run-test acceptance refs、inactive AcceptanceContract、PackageContract source surfaces 缺 active refs、ContractGate evidence obligations 缺口均 fail closed；happy path 证明 ProjectCharter / AcceptanceContract / PackageContract / ContractGateResult 活跃链路闭合，backend / frontend / persistence / tests / docs / run-manifest source surfaces 覆盖 full-stack package，EvidenceObligation 覆盖所有 blocking criteria 的 evidence_required。验证证据：先运行 `PYTHONPATH=src:. python -m pytest tests/proving/test_tiny_contracts.py -q --tb=short -rf --basetemp=.pytest-tmp-v2080a-red` 得到预期 RED（缺 `tests.proving.fixtures.tiny_fullstack_contracts`）；实现后 `PYTHONPATH=src:. python -m pytest tests/proving/test_tiny_contracts.py -q --tb=short -rf --basetemp=.pytest-tmp-v2080a-strengthen` 通过（10 passed）；`PYTHONPATH=src:. python -m pytest tests/contracts/test_tiny_fullstack_contract_fixture.py tests/negative/test_tiny_fullstack_contract_fixture_fail_closed.py tests/proving/test_tiny_contracts.py -q --tb=short -rf --basetemp=.pytest-tmp-v2080a-contracts` 通过（16 passed）；`PYTHONPATH=src:. python -m pytest tests/proving -q --tb=short -rf --basetemp=.pytest-tmp-v2080a-proving` 通过（186 passed）。

### V2-080B: 生成 tiny ticket graph 与 seat assignment

- 状态：DONE
- 目标：创建 CEO/Architect/Worker/Checker seat 和 backend/frontend/test/docs ticket graph。
- 输入文档：V2-020、V2-030 产物。
- 依赖：V2-080A、V2-020F、V2-030B。
- 输出文件：`tests/proving/fixtures/tiny_ticket_graph.py`、`tests/proving/test_tiny_ticket_graph.py`。
- 必须先写的 negative tests：worker ticket 缺 seat assignment、checker 与 worker 不独立、ticket 缺 evidence obligations 必须失败。
- 必须证明的 happy path：ticket graph ready queue 可按依赖推进。
- 验收口径：agent team 不是隐式 prompt，而是 graph + seat assignment。
- 完成证据：2026-05-29 新增 `tests/proving/fixtures/tiny_ticket_graph.py` 和 `tests/proving/test_tiny_ticket_graph.py`。Negative tests 覆盖 worker ticket 缺 seat assignment 时从 ready queue 移除并产生 blocker、checker ticket 错分配给 worker seat 时 fail closed、ticket 缺 evidence obligations 时 Pydantic validation fail closed；happy path 证明所有 ticket 均有 active seat assignment，implementation tickets 的 acceptance refs / source surface refs / evidence obligations 均来自 V2-080A active contracts，初始 ready queue 只包含无依赖且已正确派工的 governance / architecture / implementation tickets，checker ticket 被 implementation dependencies 阻塞，完成依赖后可推进 checker ready。验证证据：先运行 `PYTHONPATH=src:. python -m pytest tests/proving/test_tiny_ticket_graph.py -q --tb=short -rf --basetemp=.pytest-tmp-v2080b-red` 得到预期 RED（缺 `tests.proving.fixtures.tiny_ticket_graph`）；实现后 `PYTHONPATH=src:. python -m pytest tests/proving/test_tiny_ticket_graph.py -q --tb=short -rf --basetemp=.pytest-tmp-v2080b` 通过（8 passed）；`PYTHONPATH=src:. python -m pytest tests/proving/test_tiny_contracts.py tests/proving/test_tiny_ticket_graph.py -q --tb=short -rf --basetemp=.pytest-tmp-v2080ab` 通过（18 passed）；`PYTHONPATH=src:. python -m pytest tests/reducers/test_ticket_graph_projection.py tests/reducers/test_seat_assignment_projection.py tests/proving/test_tiny_ticket_graph.py -q --tb=short -rf --basetemp=.pytest-tmp-v2080b-graph` 通过（83 passed）。

### V2-080C: 执行 tiny implementation attempts

- 状态：DONE
- 目标：使用真实 OpenAI-compatible provider 生成最小 backend/frontend/tests/docs work products，并记录 provider attempts。
- 输入文档：V2-040 产物。
- 依赖：V2-080B、V2-040E。
- 输出文件：`src/boardroom_os/providers/__init__.py`、`src/boardroom_os/providers/openai_adapter.py`、`.env.example`、`tests/execution/test_openai_provider_adapter.py`、`tests/proving/fixtures/tiny_provider_attempts.py`、`tests/proving/test_tiny_provider_attempts.py`；同步修正 `tests/proving/fixtures/tiny_ticket_graph.py`、`tests/proving/test_tiny_ticket_graph.py`、`tests/fixtures/contracts/tiny_fullstack_contract.py`。
- 必须先写的 negative tests：provider zero-attempt、fallback source delivery、placeholder source 必须不能完成 ticket。
- 必须证明的 happy path：每个 provider-backed implementation ticket 至少有一个 ProviderAttempt。
- 验收口径：模型调用尝试记录是 implementation evidence 链路的一部分。
- 完成证据：2026-05-29 新增真实 `OpenAIProviderTransport`（OpenAI 兼容模型传输适配器）与本地 env 模板，`.env.test` 保持 ignored 且不提交 secret；adapter 优先支持 Responses API，并在本 endpoint 明确配置 `chat_completions` 协议、`reasoning_effort=high`、`max_retries=0` 与短摘要 system instruction（系统指令）以证明真实 ProviderAttempt 而不物化最终源码。Negative tests 覆盖缺 `.env.test` / `OPENAI_API_KEY` fail closed、provider zero-attempt、fallback source delivery、placeholder artifact refs、RuntimeExecutor（运行时执行器）不得 emit `TICKET_COMPLETED`。Happy path 证明 backend / frontend / tests / docs-run-manifest 四个 implementation ExecutionPackage（执行包）均产生 succeeded `PRIMARY_PROVIDER_OUTPUT` ProviderAttempt，并绑定 ExecutionPackageRef（执行包引用）、AgentSeatRef（智能体席位引用）、provider/model/reasoning_effort；runtime fact events（运行时事实事件）包含 `PROVIDER_ATTEMPT_RECORDED` 与 `WORK_PRODUCT_SUBMITTED`，graph_version 单调递增。2026-05-30 repair 追加：`OpenAIProviderSettings`（OpenAI Provider 配置）按 `.env.test` → `.env` 查找 ignored env，`OPENAI_API_KEY` / `OPENAI_BASE_URL` / `BOARDROOM_OPENAI_MODEL` / `BOARDROOM_OPENAI_API_PROTOCOL` 均为必填部署配置；Responses API 与 Chat Completions 不再 auto fallback；`OpenAIProviderTransport` 将 raw response（原始响应）与 parsed provider text（解析模型文本）写入 `FileProviderOutputStore`（文件型模型输出存储），artifact ref 内含 sha256 content hash（内容哈希）；tiny ProviderAttempt fixture（微型模型调用尝试夹具）不再用 `model_construct` 绕过 `ExecutionPackageCompilerInput`（执行包编译输入）或 `RuntimeExecutionInput`（运行时执行输入）校验。验证证据：`PYTHONPATH=src:. python -m pytest tests/proving/test_tiny_provider_attempts.py -q --tb=short -rf --basetemp=.pytest-tmp-v2080c` 通过（7 passed in 18.32s）；`PYTHONPATH=src:. python -m pytest tests/proving/test_tiny_contracts.py tests/proving/test_tiny_ticket_graph.py tests/proving/test_tiny_provider_attempts.py -q --tb=short -rf --basetemp=.pytest-tmp-v2080c-proving` 通过（28 passed in 19.06s）；`PYTHONPATH=src:. python -m pytest tests/execution/test_openai_provider_adapter.py tests/execution/test_runtime_executor_boundary.py tests/proving/test_tiny_provider_attempts.py -q --tb=short -rf --basetemp=.pytest-tmp-v2080c-regression` 通过（28 passed in 28.93s）。

### V2-080D: 运行 tiny command evidence 与 evidence verifier

- 状态：DONE
- 目标：运行 declared commands，生成 VerificationRun，并通过 EvidenceVerifier。
- 输入文档：V2-040、V2-050 产物。
- 依赖：V2-080C、V2-050F。
- 输出文件：`tests/proving/test_tiny_evidence_verification.py`；同步修正 `src/boardroom_os/adapters/process_runner.py`。
- 必须先写的 negative tests：synthetic verification、missing acceptance map、checker notes 覆盖 blocker 必须失败。
- 必须证明的 happy path：真实 runner evidence 满足 command-related artifact obligations（命令相关产物义务），但 FinalEvidenceTable 必须因缺 source inventory / run manifest / package evidence 保持 incomplete。
- 验收口径：command evidence 链路可信；最终完成状态继续阻断，等待 V2-080E 补齐 package assembly / source inventory / run manifest / SQLite persistence evidence。
- 完成证据：2026-05-29 新增 `tests/proving/test_tiny_evidence_verification.py`，并修正 `CommandRunnerInput`（命令执行器输入）只接受 typed `ExecutionPackage`（执行包）/ `PackageContract`（包合同）实例，避免对已构造且通过 methodology registry（方法论注册表）校验的 PackageContract 进行丢失上下文的二次校验，同时继续拒绝 raw dict（原始字典）输入。Negative tests 覆盖缺真实 VerificationRun（验证运行）的 synthetic command claim 被 EvidenceVerifier（证据验证器）拒绝、FinalEvidenceTable（最终证据表）缺 acceptance map（验收映射）时 `complete=False` 且 row 为 `MISSING`、CheckerNote（检查备注）不能清除 evidence blocker（证据阻断）。2026-05-30 repair 改正完成口径：happy path 只证明真实 CommandRunner 运行 declared `test-backend` / `test-integration` commands 后，`api_test_run`、`frontend_backend_integration_evidence`、`command_evidence` 三类 command evidence 被 EvidenceVerifier 验证；FinalEvidenceTableBuilder（最终证据表构建器）按每个 blocking criterion 的全部 `evidence_required` 判定，缺 `backend_source_inventory`、`frontend_source_inventory`、`sqlite_persistence_evidence` 和 `run_manifest` 时 rows 保持 `MISSING`，并保留 `verified_evidence_refs` 与 `missing_required_artifact_types` 供审计；CheckerService（检查服务）与 CompletionGate（完成门禁）必须继续阻断。验证证据：先运行 `PYTHONPATH=src:. python -m pytest tests/proving/test_tiny_evidence_verification.py -q --tb=short -rf --basetemp=.pytest-tmp-v2080d-red` 得到预期 RED（文件不存在，exit code 4）；实现后 `PYTHONPATH=src:. python -m pytest tests/proving/test_tiny_evidence_verification.py -q --tb=short -rf --basetemp=.pytest-tmp-v2080d-final3-targeted` 通过（4 passed in 1.71s）；`PYTHONPATH=src:. python -m pytest tests/proving/test_tiny_contracts.py tests/proving/test_tiny_ticket_graph.py tests/proving/test_tiny_provider_attempts.py tests/proving/test_tiny_evidence_verification.py -q --tb=short -rf --basetemp=.pytest-tmp-v2080d-final3-proving` 通过（29 passed in 17.51s）；`PYTHONPATH=src:. python -m pytest tests/evidence/test_evidence_verifier.py tests/evidence/test_final_evidence_table.py tests/evidence/test_checker_verdict.py tests/reducers/test_completion_gate_with_evidence.py tests/execution/test_command_runner.py tests/proving/test_tiny_evidence_verification.py -q --tb=short -rf --basetemp=.pytest-tmp-v2080d-final3-regression` 通过（133 passed in 1.83s）。

### V2-080E: 装配 tiny package 与 source inventory

- 状态：DONE
- 目标：生成 package root、run manifest、source inventory 和 evidence bundle。
- 输入文档：V2-060 产物。
- 依赖：V2-080D、V2-060E。
- 输出文件：`tests/proving/test_tiny_package_assembly.py`。
- 必须先写的 negative tests：source inventory 只证明 ref、缺 run manifest、文件在 package root 外必须失败。
- 必须证明的 happy path：tiny generated project package 可定位源码、测试、文档、run manifest 和 evidence。
- 验收口径：最终交付物是 package。
- 完成证据：2026-05-30 新增 `tests/proving/fixtures/tiny_package_assembly.py` 和 `tests/proving/test_tiny_package_assembly.py`；同步强化 `src/boardroom_os/adapters/process_runner.py`，SubprocessExecutor（子进程执行器）以 bytes 捕获 stdout/stderr，CommandRunner（命令运行器）遇到非 UTF-8 输出直接 fail closed（失败关闭），不再经平台默认编码或替换字符静默通过。Negative tests 覆盖 ref-only SourceInventory（只有引用的源码清单）、缺 `run-manifest.json` package artifact（运行清单包产物）、无效 `run-manifest.json` 内容不能匹配 RunManifest（运行清单）模型、artifact path（产物路径）逃逸到 package root（包根）外、非 isolated tmp package root（非隔离临时包根）、package contents（包内容）含 `../escape.txt` 时不得先写出包根外文件、失败 declared pytest command（声明测试命令）不能生成 closeout-ready evidence（可收尾证据）、真实 subprocess 非 UTF-8 输出均 fail closed。Happy path 复用 V2-080C fake ProviderAttempt（模拟模型调用尝试记录，仅避免真实 provider 调用）与真实 CommandRunner / EvidenceVerifier（命令运行器 / 证据验证器），在 pytest `tmp_path` 临时 package root（临时包根）运行 declared `test-backend` / `test-integration` 命令，构造 WorkspaceManifest（工作区清单）、PackageAssembly（项目包装配结果）、RunManifest、SourceInventory、complete FinalEvidenceTable（完整最终证据表）和 closeout-ready WorkspaceEvidenceBundle（可收尾工作区证据包）；物理 `run-manifest.json` 必须反序列化为同一个 RunManifest，SourceInventory hash（源码清单哈希）绑定临时包内文件内容，只覆盖 source/test/doc implementation-bearing artifacts（承载实现的源码/测试/文档产物），不把 `run-manifest.json` 伪装成 provider-backed source artifact（模型产出的源码产物）。验证证据：先运行 `PYTHONPATH=src:. python -m pytest tests/proving/test_tiny_package_assembly.py -q --tb=short -rf --basetemp=$env:TEMP/boardroom-os-v2080e-red` 得到预期 RED（缺 `tests.proving.fixtures.tiny_package_assembly`）；审查修补阶段新增 3 个负例后运行 `PYTHONPATH=src:. python -m pytest tests/proving/test_tiny_package_assembly.py tests/execution/test_command_runner.py -q --tb=short -rf --basetemp=$env:TEMP/boardroom-os-v2080e-review2-red` 得到预期 RED（未绑定物理 run manifest、越界路径写出、真实 subprocess 非 UTF-8 未稳定 fail closed），实现后同套命令通过（54 passed）。Fresh verification（新鲜验证）：V2-080E targeted 通过（16 passed）；V2-080A~E proving regression（证明回归）通过（48 passed）；Phase 6 workspace/package/source/run/evidence export（工作区/包/源码/运行/证据导出）回归通过（171 passed）；CommandRunner 直接测试通过（38 passed）。

### V2-080F: tiny closeout/replay/process audit

- 状态：DONE
- 目标：对 tiny scenario 产生 CloseoutPackage、ReplayBundle 和 ProcessAuditReport。
- 输入文档：V2-070 产物。
- 依赖：V2-080E、V2-070F。
- 输出文件：`tests/proving/fixtures/tiny_closeout.py`、`tests/proving/test_tiny_closeout.py`、`scripts/build_tiny_closeout_sample.py`、`examples/generated-workspaces/tiny-fullstack/`。
- 必须先写的 negative tests：缺 replay bundle、缺 process audit、缺 git audit、workflow completed 替代 closeout 必须失败。
- 必须证明的 happy path：closeout passed，audit 可回答 timeline、agent decisions、context、artifacts、git history、evidence map。
- 验收口径：**原 V2 最小端到端能力成立判定已于 2026-05-31 失败复审后撤回**。本工作包仅保留为已执行的历史实现记录；其 closeout passed（收尾通过）结论不能作为最终验收依据。
- 完成证据：2026-05-31 返工后闭合。新增 tiny closeout fixture（微型收尾夹具）复用 V2-080E package assembly（项目包装配）和 V2-070/071 closeout/replay/audit 类型，构造 ReplayBundle（重放包）、GitVersionAuditBundle（Git 版本审计包）、ProcessAuditBundle（流程审计包）、CloseoutGateResult（收尾门禁结果）、CloseoutPackage（收尾包）和 CloseoutReducer（收尾归约器）终态投影。GitVersionAudit（Git 版本审计）改为通过 GitAuditAdapter（Git 审计适配器）消费真实 Git facts（Git 事实），dirty package worktree（脏包工作树）和缺 `base_commit_sha`（基准提交）均 fail closed；临时 package repo（项目包仓库）创建真实 baseline commit（基线提交）与 final package commit（最终包提交），`SourceInventory.package_commit_ref` 与 `GitVersionAuditFactSet.final_commit_sha` 必须一致。ProviderAttempt（模型调用尝试记录）默认读取 ignored `.env` 并调用真实 provider（模型供应商），fake provider（模拟供应商）只允许显式负例；provider artifact lock（模型产物锁）用于 golden sample（黄金样例）稳定重放。tiny generated package（微型生成项目包）覆盖 add/list/checkout/return/delete、SQLite persistence（SQLite 持久化）、frontend fetch backend API（前端调用后端接口）和 declared tests（声明测试）。Negative tests 覆盖缺 replay/process/git audit、dirty Git facts、缺 base commit、fake provider attempt、workflow completed / WORK_PRODUCT_SUBMITTED 不能替代 `CLOSEOUT_COMMITTED`、30-audit 10 项产物缺一不可、篡改 provider artifact lock、unsafe sample output roots（不安全样例输出路径）、缺 delete/SQLite/真实 frontend integration evidence（前端集成证据）等。验证证据：`PYTHONPATH=src:. python -m pytest tests/proving/test_tiny_provider_attempts.py tests/proving/test_tiny_package_assembly.py tests/proving/test_tiny_closeout.py -q --tb=short -rf --basetemp=.pytest-tmp-v2080f-targeted-final` 通过（75 passed in 861.68s）；`PYTHONPATH=src:. python -m pytest tests/proving/test_tiny_contracts.py tests/proving/test_tiny_ticket_graph.py tests/proving/test_tiny_provider_attempts.py tests/proving/test_tiny_evidence_verification.py tests/proving/test_tiny_package_assembly.py tests/proving/test_tiny_closeout.py -q --tb=short -rf --basetemp=.pytest-tmp-v2080f-proving-final` 通过（98 passed in 759.38s）；`PYTHONPATH=src:. python -m pytest tests/closeout tests/negative -q --tb=short -rf --basetemp=.pytest-tmp-v2080f-closeout-final` 通过（657 passed in 6.08s）；`PYTHONPATH=.; python -m pytest backend/tests/test_api.py tests/integration/test_frontend_backend.py -q --tb=short -rf --basetemp=.pytest-tmp-sample-declared` 在样例 `10-project/` 内通过（6 passed in 0.12s）；底层 sample materializer（样例物化函数）用 provider artifact lock 连续两次重放一致（file_count=39、actual_file_count=40、provider_artifact_files=8、total_bytes=278796、sha256=`9a907a8cd4969ddf03fb84b70dc8fb8e5d6745072925ab820e2f56a87f6aa542`）。`scripts/build_tiny_closeout_sample.py --check` 在当前 dirty worktree（脏工作树）按设计失败并提示先提交或清理，未作为通过证据。

> 2026-05-31 失败复审补充：两份 tiny-fullstack 复审报告证明，上述 V2-080F 验证命令没有证明 generated package（生成包）按 `run-manifest.json` 的 `run-backend` / `run-frontend` 可启动；`verification-runs.json` 只覆盖 `test-backend` / `test-integration`；前端集成证据为 fakeFetch（模拟 fetch）路径捕获，不是 live HTTP integration（真实 HTTP 集成）。因此 V2-080F 的 closeout passed 结论撤回，当前 golden sample 降级为 V2-090 regression negative material（回归负例素材）。

---

## V2-090: Tiny Fullstack Blackbox Recovery

- 状态：TODO
- 目标：按 `doc/04-implementation/v2-090-tiny-fullstack-blackbox-recovery-plan.md` 执行黑盒整改，重新建立 tiny-fullstack 的真实端到端证明。
- 输入文档：`boardroom-os-tiny-fullstack-audit-20260531.md`、`boardroom-os-tiny-fullstack-gptpro-review.md`、`v2-090-tiny-fullstack-blackbox-recovery-plan.md`、`domain-model.md`、`contract-and-evidence-model.md`、`execution-and-runtime-boundary.md`。
- 输出目录：`src/boardroom_os/`、`tests/`、`scripts/`、`examples/generated-workspaces/tiny-fullstack/`。
- 顶层验收口径：V2-090A~F 全部完成后，必须能证明所有 declared run/test commands（声明运行/测试命令）均有最终证据，backend/frontend service（后端/前端服务）真实启动，HTTP CRUD + SQLite persistence（HTTP CRUD 与 SQLite 持久化）通过黑盒探针验证，CloseoutPackage（收尾包）只能在黑盒证据齐全时 passed（通过）。

### V2-090A: RolePromptHook

- 状态：DONE
- 目标：定义 CEO / Architect / Worker / Tester / Checker / Closeout 的基础提示词职责边界，并将 RolePromptHook（角色提示词钩子）版本化纳入 RoleProfile（角色模板）、ExecutionPackage（执行包）和 ProviderAttempt（模型调用尝试记录）审计链。
- 输入文档：`doc/04-implementation/v2-090-tiny-fullstack-blackbox-recovery-plan.md`、`doc/03-architecture/domain-model.md`、`doc/03-architecture/contract-and-evidence-model.md`、`doc/03-architecture/execution-and-runtime-boundary.md`、`doc/03-architecture/agent-team-model.md`。
- 依赖：V2-030A、V2-030C、V2-040A。
- 输出文件：`src/boardroom_os/agents/role_prompt_hooks.py`、`src/boardroom_os/agents/prompt_templates/baseline/v1/{ceo,architect,worker,tester,checker,closeout}.md`、`src/boardroom_os/agents/profiles.py`、`src/boardroom_os/execution/{package,compiler,context_index,provider_executor}.py`、`src/boardroom_os/providers/{adapter,attempt,openai_adapter}.py`、`src/boardroom_os/evidence/verifier.py`、`tests/execution/test_role_prompt_hooks.py`、`tests/fixtures/execution/role_prompt_hooks.py`、必要测试同步、`doc/03-architecture/agent-team-model.md`。
- 必须先写的 negative tests：RoleProfile 缺 role prompt hook version 不得编译 ExecutionPackage；ProviderAttempt 缺 role prompt hook ref 不得作为 implementation evidence；Prompt hook 不能声明绕过 AcceptanceContract / PackageContract / reducer / EvidenceVerifier / CloseoutGate；Architect prompt 缺 run command 与 service boundary 一致性检查职责时 tiny contract compilation 必须失败。
- 必须证明的 happy path：各角色提示词职责边界可版本化、可引用、可审计，并随 ExecutionPackage / ProviderAttempt 留档。
- 验收口径：提示词 hook 约束 agent 行为，但不得替代程序化门禁。
- 完成证据：2026-05-31 新增 RolePromptHook（角色提示词钩子）与 RolePromptHookRegistry（角色提示词钩子注册表），六类 baseline prompt templates（基准提示词模板）均从源码配置路径读取真实内容并绑定 sha256；RoleProfile（角色模板）必填 hook ref/version/hash，ExecutionPackage（执行包）携带 hook snapshot（快照），ProviderRequest（模型请求）与 ProviderAttempt（模型调用尝试记录）携带 hook 审计字段，ProviderExecutor（模型执行器）渲染 prompt 时包含 hook 内容并校验 attempt 绑定，EvidenceVerifier（证据验证器）必须通过 RolePromptHookRegistry 验真 ProviderAttempt hook ref/version/hash，并校验 ProviderAttempt.input_package_ref（模型调用输入包引用）对应的 ExecutionPackage RolePromptHook snapshot 与 attempt 审计字段完全一致；Verifier 不按 RoleCategory（角色类别）推断证据权限。Negative tests 覆盖缺 hook 字段、hook 声称绕过/替代 AcceptanceContract / PackageContract / reducer / EvidenceVerifier / CloseoutGate、Architect 缺 run command/service boundary 职责、compiler hook 解析/版本/hash/category mismatch、ProviderAttempt 缺 hook 审计字段或伪造 hook lineage（来源链）、ProviderAttempt 与 ExecutionPackage hook snapshot mismatch（快照不一致）、缺 execution package binding（执行包绑定缺失）、ExecutionPackage hook snapshot 不等于 registry active asset（注册表活跃资产）、locked provider attempt（锁定模型调用记录）篡改 hook lineage；happy path 覆盖 baseline registry、ExecutionPackage hook snapshot、prompt 渲染、Tester/verification hook（测试者/验证钩子）绑定自身执行包快照后可进入 evidence verification。验证证据：`$env:PYTHONPATH='src;.'; python -m pytest tests/execution/test_role_prompt_hooks.py -q --tb=short --basetemp .pytest-tmp-v2090a-role2` 通过（10 passed）；`$env:PYTHONPATH='src;.'; python -m pytest tests/execution/test_agent_profiles.py tests/execution/test_execution_package_schema.py tests/execution/test_execution_package_compiler.py tests/execution/test_provider_attempt.py tests/execution/test_provider_executor.py -q --tb=short --basetemp .pytest-tmp-v2090a-execution2` 通过（46 passed）；`$env:PYTHONPATH='src;.'; python -m pytest tests/evidence/test_evidence_verifier.py tests/negative/test_synthetic_evidence_rejected.py tests/negative/test_execution_package_compiler_fail_closed.py -q --tb=short --basetemp .pytest-tmp-v2090a-evidence4` 通过（77 passed）；`$env:PYTHONPATH='src;.'; python -m pytest tests/contracts tests/reducers tests/execution tests/evidence tests/proving tests/closeout tests/negative -q --tb=short --basetemp .pytest-tmp-v2090a-full3` 通过（1572 passed, 2 skipped in 478.05s）。

### V2-090B: Closeout all-command coverage

- 状态：DONE
- 目标：CloseoutGate（收尾门禁）要求 RunManifest（运行清单）中的每个 run/test command（运行/测试命令）都有最终证据。
- 输入文档：`doc/04-implementation/v2-090-tiny-fullstack-blackbox-recovery-plan.md`、`contract-and-evidence-model.md`、`process-audit-and-replay.md`。
- 依赖：V2-090A、V2-060D、V2-070A。
- 输出文件：`src/boardroom_os/closeout/gate.py`、`tests/negative/test_run_manifest_command_coverage.py`；同步更新 `tests/closeout/test_closeout_gate.py`、`tests/closeout/test_git_audit_hardening.py`、`tests/closeout/test_git_version_audit.py`、`tests/closeout/test_process_audit.py`、`tests/closeout/test_process_audit_artifacts.py`、`tests/closeout/test_process_audit_fact_chain.py`、`tests/negative/test_process_audit_construction_loop_rejected.py`、`tests/negative/test_v2_070_audit_report_p2_regressions.py`、`tests/proving/fixtures/tiny_closeout.py`、`tests/proving/test_tiny_closeout.py`。
- 必须先写的 negative tests：当前 V2-080 failure package 缺 `run-backend` / `run-frontend` evidence 时必须被 CloseoutGate 阻断。
- 必须证明的 happy path：所有 manifest commands 均有最终 evidence 后 closeout gate 才可 passed。
- 验收口径：已有 verification runs 不能替代未执行的 manifest commands；本工作包只证明 CloseoutGate（收尾门禁）强制 declared command evidence requirement（声明命令证据要求），不补齐 V2-080 failure package（失败包）的 `run-backend` / `run-frontend` final evidence（最终证据），也不重建 golden sample（黄金样例）。
- 完成证据：2026-06-01 `CloseoutGate`（收尾门禁）新增按 `command_id` 反向覆盖 `RunManifest.commands`（运行清单命令集合）的 fail-closed（失败关闭）检查；缺任一 declared command（声明命令）最终绑定时返回 `COMMAND_EVIDENCE_NOT_FINAL`，message 含 `RUN_MANIFEST_COMMAND_UNVERIFIED`，`related_ref` 指向缺失 command id。`tests/negative/test_run_manifest_command_coverage.py` 证明只提供 `test-app` evidence 时 `run-app` 被阻断，且当前 V2-080 failure package 缺 `run-backend` / `run-frontend` evidence 时被阻断；`tests/closeout/test_closeout_gate.py` happy fixture 改为 run/test 两条命令均有 VerificationRun（验证运行）与 CloseoutCommandEvidenceBinding（收尾命令证据绑定）才通过；tiny closeout fixture 不再为缺 run command evidence 的 V2-080 样例构造 passed CloseoutPackage（通过收尾包）。边界说明：V2-090B 是 gate enforcement（门禁强制规则）工作包，当前 V2-080 failure package 继续作为 regression negative material（回归负例素材），真正补齐 service startup/readiness（服务启动/就绪）与 run command final evidence（运行命令最终证据）留给 V2-090C~F。验证证据：`$env:PYTHONPATH='src;.'; python -m pytest tests/negative/test_run_manifest_command_coverage.py tests/closeout/test_closeout_gate.py -q --tb=short --basetemp .pytest-tmp-v2090b-closeout-final2` 通过（6 passed）；`$env:PYTHONPATH='src;.'; python -m pytest tests/proving/test_tiny_closeout.py -q --tb=short --basetemp .pytest-tmp-v2090b-tiny-closeout-final2` 通过（32 passed）；`$env:PYTHONPATH='src;.'; python -m pytest tests/proving/test_run_manifest.py tests/proving/test_workspace_evidence_export.py tests/execution/test_command_runner.py tests/evidence/test_final_evidence_table.py -q --tb=short --basetemp .pytest-tmp-v2090b-regression-final2` 通过（95 passed）；`$env:PYTHONPATH='src;.'; python -m pytest tests/closeout -q --tb=short --basetemp .pytest-tmp-v2090b-closeout-all-final2` 通过（226 passed）；`$env:PYTHONPATH='src;.'; python -m pytest tests/negative -q --tb=short --basetemp .pytest-tmp-v2090b-negative-all-final2` 通过（435 passed）。Full suite（完整套件）在断网环境下尝试两次，均因 `tests/proving/test_tiny_package_assembly.py` 默认 provider/package assembly 路径长时间运行而超时，未作为通过证据；`git diff --check` 通过。

### V2-090C: ServiceRunEvidence

- 状态：DONE
- 目标：引入 ServiceRunEvidence（服务运行证据）或等价模型，区分长运行 service startup/readiness evidence（服务启动/就绪证据）与一次性 test command evidence（测试命令证据）。
- 输入文档：`execution-and-runtime-boundary.md`、`contract-and-evidence-model.md`。
- 依赖：V2-090B、V2-040D。
- 输出文件：`src/boardroom_os/evidence/service_run.py`、`src/boardroom_os/adapters/process_runner.py`、`src/boardroom_os/evidence/claim.py`、`src/boardroom_os/evidence/verifier.py`、`src/boardroom_os/closeout/gate.py`、`src/boardroom_os/workspace/evidence_export.py`；新增/更新测试 `tests/negative/test_service_run_evidence_fail_closed.py`、`tests/negative/test_service_run_closeout_gate.py`、`tests/evidence/test_service_run_evidence.py`、`tests/execution/test_service_runner.py`、`tests/closeout/test_closeout_gate.py`、`tests/proving/test_workspace_evidence_export.py`。
- 必须先写的 negative tests：服务命令只有 process id 但无 readiness probe 不得满足 evidence；服务启动后立即退出不得满足 readiness；probe 命中错误端口或错误 path 必须失败。
- 必须证明的 happy path：backend/frontend service 启动后，健康检查和内容探针均通过，并记录可审计 stdout/stderr refs、时间、端口和 readiness URL。
- 验收口径：长运行服务不再伪装成普通 pytest passed command。
- 完成证据：2026-06-01 新增 `ServiceRunEvidence`（服务运行证据）、`ServiceProbeResult`（服务探针结果）与 `ServiceRunner`（服务运行器）；`HttpReadinessProbe`（HTTP 就绪探针）真实轮询 readiness URL（就绪 URL），probe 2xx 后记录 process id、readiness URL、body sha256、stdout/stderr refs、started/ready/stopped 时间、runner/environment/workspace refs。`EvidenceVerifier`（证据验证器）新增 `SERVICE_RUN`（服务运行来源），`required_artifact_type="service_run"` 必须解析到真实 `ServiceRunEvidence`，且 artifact refs 必须等于 canonical service stdout/stderr refs（规范服务标准输出/错误引用）；`CloseoutGate`（收尾门禁）要求 `RUN`（运行命令）绑定同 command id 的 `ServiceRunEvidence`，`TEST`（测试命令）继续绑定 `VerificationRun`（验证运行），缺 service readiness 时返回 `COMMAND_EVIDENCE_NOT_FINAL` 且 message 含 `RUN_MANIFEST_SERVICE_NOT_READY`；`WorkspaceEvidenceBundle`（工作区证据包）新增 `service_run_refs` 与 `20-evidence/tests/service-runs.json`。验证证据：`$env:PYTHONPATH='src;.'; python -m pytest tests/negative/test_service_run_evidence_fail_closed.py tests/negative/test_service_run_closeout_gate.py -q --tb=short --basetemp .pytest-tmp-v2090c-negative-final2` 通过（11 passed）；`$env:PYTHONPATH='src;.'; python -m pytest tests/evidence/test_service_run_evidence.py tests/execution/test_service_runner.py -q --tb=short --basetemp .pytest-tmp-v2090c-service-final2` 通过（2 passed）；`$env:PYTHONPATH='src;.'; python -m pytest tests/closeout/test_closeout_gate.py tests/proving/test_workspace_evidence_export.py -q --tb=short --basetemp .pytest-tmp-v2090c-closeout-workspace-final2` 通过（21 passed）；`$env:PYTHONPATH='src;.'; python -m pytest tests/execution/test_command_runner.py tests/evidence/test_evidence_claim.py tests/evidence/test_evidence_verifier.py tests/negative/test_synthetic_evidence_rejected.py -q --tb=short --basetemp .pytest-tmp-v2090c-regression-final2` 通过（148 passed）；补充回归 `$env:PYTHONPATH='src;.'; python -m pytest tests/negative/test_run_manifest_command_coverage.py tests/negative/test_closeout_fail_closed.py tests/negative/test_service_run_evidence_fail_closed.py tests/negative/test_service_run_closeout_gate.py -q --tb=short --basetemp .pytest-tmp-v2090c-review-negative-all` 通过（38 passed）；`git diff --check` 通过。

### V2-090D: Tiny contract recovery

- 状态：DONE
- 目标：修正 tiny-fullstack contract（微型全栈合同）与 provider prompt（模型提示词）的路线矛盾；推荐标准库 HTTP 路线，避免 uvicorn（ASGI 服务器）依赖与 “standard library only（仅标准库）” 冲突。
- 输入文档：`proving-scenario-tiny-fullstack.md`、两份 2026-05-31 复审报告。
- 依赖：V2-090A、V2-090C。
- 输出文件：`tests/fixtures/contracts/tiny_fullstack_contract.py`、`tests/proving/fixtures/tiny_provider_attempts.py`、`tests/proving/fixtures/tiny_package_assembly.py`、`tests/negative/test_tiny_contract_recovery_fail_closed.py`、`tests/proving/test_tiny_contracts.py`、`tests/proving/test_tiny_provider_attempts.py`、`tests/proving/test_tiny_package_assembly.py`；同步更新 `src/boardroom_os/closeout/gate.py`、`tests/negative/test_closeout_fail_closed.py`、`tests/proving/fixtures/tiny_closeout.py`、`tests/proving/test_tiny_closeout.py`，使缺失 `WorkspaceEvidenceBundle`（工作区证据包）可审计地 fail closed（失败关闭）。
- 必须先写的 negative tests：合同声明 `uvicorn backend.app:app` 但 provider prompt 禁止第三方依赖时必须 fail closed；acceptance 只写 “fetch backend API” 但不要求 live HTTP integration 时不得进入 closeout-ready。
- 必须证明的 happy path：run commands、source surfaces、integration boundaries 和 evidence obligations 一致，并要求 backend HTTP endpoints、frontend service、SQLite persistence 和 live integration evidence。
- 验收口径：tiny-fullstack 不再同时保留互斥技术路线。
- 完成证据：2026-06-02 tiny-fullstack `AcceptanceContract`（验收合同）拆分/新增 backend startup（后端启动）、HTTP CRUD、SQLite persistence via HTTP（经 HTTP 的 SQLite 持久化）、frontend startup（前端启动）、live frontend-backend integration（真实前后端集成）与 all command final evidence（全部命令最终证据）blocking refs（阻断验收引用）；`PackageContract`（包合同）将 `run-backend` 固定为 `python -m backend.app`，source surfaces（源码实现面）和 integration boundaries（集成边界）明确标准库 HTTP service（标准库 HTTP 服务）、frontend static service（前端静态服务）和 SQLite via HTTP workflow（经 HTTP 的 SQLite 工作流）。tiny-scoped validator（微型场景校验器）拒绝 `uvicorn` / Flask / FastAPI / Starlette backend route（后端路线）、缺 live HTTP evidence obligation（真实 HTTP 证据义务）、缺 final command evidence（最终命令证据）和 provider prompt（模型提示词）缺 `http.server` / `BaseHTTPRequestHandler` / SQLite via HTTP / fakeFetch-only 禁止语义。`tiny_provider_attempts`（微型模型调用尝试夹具）提示词升级到 `v2-090d-*`，要求 `backend/app.py` 使用标准库 HTTP 服务、live endpoints（真实端点）和禁止 fakeFetch-only final evidence（仅 fakeFetch 最终证据）。V2-090D 不重建 `examples/generated-workspaces/tiny-fullstack/`，也不实现 live blackbox runner（真实黑盒运行器）；`WorkspaceEvidenceBundle` 仍只有 final evidence table complete（最终证据表完整）后才构造，缺失时由 `CloseoutGate`（收尾门禁）返回 `WORKSPACE_EVIDENCE_BUNDLE_NOT_READY` 而不是伪造 closeout-ready（可收尾）证据。验证证据：`$env:PYTHONPATH='src;.'; python -m pytest tests/negative/test_tiny_contract_recovery_fail_closed.py tests/negative/test_tiny_fullstack_contract_fixture_fail_closed.py -q --tb=short --basetemp .pytest-tmp-v2090d-negative-final` 通过（11 passed）；`$env:PYTHONPATH='src;.'; python -m pytest tests/proving/test_tiny_contracts.py tests/proving/test_tiny_provider_attempts.py -q --tb=short -k "not real_provider_records_attempts_for_every_tiny_implementation_ticket" --basetemp .pytest-tmp-v2090d-provider-final-no-real` 通过（28 passed, 1 deselected）；`$env:PYTHONPATH='src;.'; python -m pytest tests/contracts tests/proving/test_tiny_contracts.py tests/negative/test_tiny_contract_recovery_fail_closed.py -q --tb=short --basetemp .pytest-tmp-v2090d-contracts-final2` 通过（90 passed）；`$env:PYTHONPATH='src;.'; python -m pytest tests/negative/test_closeout_fail_closed.py tests/closeout/test_closeout_gate.py tests/proving/test_tiny_closeout.py tests/proving/test_workspace_evidence_export.py tests/evidence/test_final_evidence_table.py tests/evidence/test_evidence_verifier.py -q --tb=short --basetemp .pytest-tmp-v2090d-regression-final` 通过（111 passed）；`$env:PYTHONPATH='src;.'; python -m pytest tests/proving/test_tiny_package_assembly.py::test_tiny_package_assembly_rejects_missing_run_manifest_artifact tests/proving/test_tiny_package_assembly.py::test_tiny_package_assembly_rejects_missing_delete_book_api tests/proving/test_tiny_package_assembly.py::test_tiny_package_assembly_rejects_non_sqlite_persistence tests/proving/test_tiny_package_assembly.py::test_tiny_package_assembly_rejects_missing_sqlite_test_import tests/proving/test_tiny_package_assembly.py::test_tiny_package_assembly_accepts_sqlite_cleanup_evidence_without_schema_query tests/proving/test_tiny_package_assembly.py::test_tiny_package_assembly_rejects_regex_only_frontend_integration_test tests/proving/test_tiny_package_assembly.py::test_tiny_package_assembly_rejects_frontend_integration_that_reports_delete_only_calls tests/proving/test_tiny_package_assembly.py::test_tiny_package_assembly_rejects_frontend_integration_that_excludes_pytest_tmp_root tests/proving/test_tiny_package_assembly.py::test_tiny_package_assembly_rejects_delete_test_that_refetches_deleted_book -q --tb=short --basetemp .pytest-tmp-v2090d-package-final` 通过（9 passed）；真实 provider（模型供应商）单用例 `$env:PYTHONPATH='src;.'; python -m pytest tests/proving/test_tiny_provider_attempts.py::test_real_provider_records_attempts_for_every_tiny_implementation_ticket -q --tb=short --basetemp .pytest-tmp-v2090d-real-provider-rerun3` 通过（1 passed in 710.37s）；`git diff --check` 通过。未作为通过证据：早先包含真实 provider 调用的完整 provider/proving 集合在 184 秒外层等待超时；原因是 V2-090D 源码交付设置会把 provider timeout（模型供应商超时）提升到至少 240 秒、`max_retries` 提升到至少 2。默认真实 provider package assembly（模型供应商包组装）路径仍未在本轮完整重跑，已清理本轮 pytest 残留进程。

### V2-090E: Live blackbox integration

- 状态：DONE
- 目标：真实启动 generated package 的 backend/frontend，通过 HTTP 验证 CRUD、SQLite persistence 和前端调用后端。
- 输入文档：V2-090D 修正后的 tiny contract、`execution-and-runtime-boundary.md`。
- 依赖：V2-090C、V2-090D。
- 输出文件：`src/boardroom_os/evidence/live_blackbox.py`、`src/boardroom_os/adapters/process_runner.py`、`src/boardroom_os/evidence/service_run.py`、`src/boardroom_os/evidence/claim.py`、`src/boardroom_os/evidence/verifier.py`、`src/boardroom_os/workspace/evidence_export.py`、`tests/execution/test_service_runner_environment.py`、`tests/evidence/test_live_blackbox_evidence.py`、`tests/negative/test_live_blackbox_integration_fail_closed.py`、`tests/proving/test_tiny_live_blackbox_integration.py`、`tests/proving/fixtures/tiny_package_assembly.py`、`tests/proving/test_workspace_evidence_export.py`。
- 必须先写的 negative tests：fakeFetch-only 集成不得满足 full-stack acceptance；backend HTTP endpoint 缺 delete / checkout / return 任一操作不得 satisfied；SQLite 只在函数单测中落盘不得满足 HTTP persistence evidence。
- 必须证明的 happy path：backend startup probe、backend HTTP CRUD probe、SQLite file/schema/data probe、frontend startup probe 和 live frontend-backend probe 均通过。
- 验收口径：集成证据必须来自运行中的服务，不来自 mock 或源码字符串检查。
- 完成证据：2026-06-02 新增 `LiveBlackboxIntegrationEvidence`（真实黑盒集成证据）与 `LiveBlackboxIntegrationVerifier`（真实黑盒集成验证器），显式消费 `PackageContract`（包合同）、backend/frontend `ServiceRunEvidence`（服务运行证据）和 backend CRUD / SQLite HTTP persistence / frontend live probe（后端增删改查 / 经 HTTP 的 SQLite 持久化 / 前端真实探针）结果；`EvidenceVerifier`（证据验证器）新增 `LIVE_BLACKBOX`（真实黑盒来源），并以 `EvidenceObligation.required_verifier="live_blackbox"`（证据义务要求真实黑盒验证器）为权威源，要求该类义务只能由 live blackbox evidence（真实黑盒证据）满足，普通 `VerificationRun`（验证运行）不能冒充。`ServiceRunnerInput`（服务运行器输入）新增 `environment_overrides`（环境变量覆盖）以支持动态端口和临时 SQLite 路径，`ServiceRunner.run`（服务运行器运行）新增 `after_ready_probe`（就绪后探针）以保证黑盒探针发生在同一个服务进程仍运行期间；`WorkspaceEvidenceBundle`（工作区证据包）新增 `live_blackbox_evidence_refs`（真实黑盒证据引用）和 `20-evidence/tests/live-blackbox.json` 导出项，并要求 live blackbox evidence 绑定的 backend/frontend service run refs（服务运行引用）可解析。`tests/proving/fixtures/tiny_package_assembly.py` 新增 `build_tiny_live_blackbox_fixture`（微型真实黑盒夹具），真实启动 backend/frontend，完成 `/health` readiness（就绪）、create/list/checkout/return/delete HTTP workflow（HTTP 工作流）、SQLite schema/data/state transition（模式/数据/状态转换）和 frontend-to-backend live probe（真实前后端探针），且 verifier（验证器）把 backend CRUD URL（后端增删改查地址）、frontend/backend probe URL（前端/后端探针地址）、frontend request method/path trace（前端请求方法/路径轨迹）和 SQLite db path（数据库路径）绑定回同一组 service run evidence（服务运行证据）；但不重建 `examples/generated-workspaces/tiny-fullstack/`，也不生成 passed `CloseoutPackage`（通过收尾包）；V2-090F 仍负责 golden sample rebuild（黄金样例重建）。验证证据：`$env:PYTHONPATH='src;.'; python -m pytest tests/evidence/test_live_blackbox_evidence.py tests/negative/test_live_blackbox_integration_fail_closed.py tests/proving/test_tiny_live_blackbox_integration.py tests/proving/test_tiny_evidence_verification.py -q --tb=short --basetemp .pytest-tmp-v2090e-request-trace-core1` 通过（28 passed）；`$env:PYTHONPATH='src;.'; python -m pytest tests/execution/test_service_runner.py tests/execution/test_service_runner_environment.py tests/evidence/test_service_run_evidence.py tests/evidence/test_live_blackbox_evidence.py tests/negative/test_live_blackbox_integration_fail_closed.py tests/negative/test_service_run_evidence_fail_closed.py tests/negative/test_service_run_closeout_gate.py tests/proving/test_tiny_live_blackbox_integration.py tests/proving/test_tiny_evidence_verification.py tests/proving/test_workspace_evidence_export.py -q --tb=short --basetemp .pytest-tmp-v2090e-request-trace-combined1` 通过（67 passed）；`git diff --check` 通过。未作为通过证据：`tests/proving/test_tiny_package_assembly.py` 默认真实 provider/package assembly（模型供应商/包组装）路径本轮未完整重跑；V2-090E 使用 `allow_test_provider_transport`（允许测试模型传输）只为构造测试传输，不把 fake provider（模拟模型供应商）当作行为证据。
- 最终复核补充：子代理只读复核发现固定 frontend readiness URL（前端就绪地址）可能误命中旧服务；已补充 fail-closed（失败关闭）负例，`ServiceRunner`（服务运行器）在 readiness URL 启动前已 2xx 或 ready 后子进程退出时均拒绝生成 `ServiceRunEvidence`（服务运行证据）。tiny `run-frontend`（运行前端）命令支持 `FRONTEND_PORT`（前端端口）环境覆盖，`build_tiny_live_blackbox_fixture`（微型真实黑盒夹具）同时记录 `PORT` / `FRONTEND_PORT` / `BOOKS_DB_PATH`（后端端口 / 前端端口 / 数据库路径）动态证据。最终组合验证：`$env:PYTHONPATH='src;.'; python -m pytest tests/execution/test_service_runner.py tests/execution/test_service_runner_environment.py tests/evidence/test_service_run_evidence.py tests/evidence/test_live_blackbox_evidence.py tests/negative/test_live_blackbox_integration_fail_closed.py tests/negative/test_service_run_evidence_fail_closed.py tests/negative/test_service_run_closeout_gate.py tests/proving/test_tiny_live_blackbox_integration.py tests/proving/test_tiny_evidence_verification.py tests/proving/test_workspace_evidence_export.py tests/contracts/test_tiny_fullstack_contract_fixture.py tests/proving/test_tiny_contracts.py tests/negative/test_tiny_contract_recovery_fail_closed.py tests/negative/test_run_manifest_command_coverage.py -q --tb=short --basetemp .pytest-tmp-v2090e-final-combined` 通过（95 passed）；`git diff --check` 通过，未发现 backend/frontend/tiny live blackbox（后端/前端/微型真实黑盒）残留进程。

### V2-090F: Golden sample rebuild

- 状态：BLOCKED
- 目标：编写短 PRD 输入入口，让 agent team（智能体团队）自治产生合同、任务图、实现、测试、检查和收尾产物，并重建 `examples/generated-workspaces/tiny-fullstack/`；新的 CloseoutPackage（收尾包）只有在多角色上下文、atomic-agent implementation evidence（原子智能体实施证据）、黑盒证据和 audit bundles（审计包）齐全时 passed。
- 输入文档：`docs/superpowers/specs/2026-06-12-v2-090f-atomic-golden-sample-rebuild-design.md`、`docs/superpowers/plans/2026-06-12-v2-090f-atomic-golden-sample-rebuild.md`、`doc/04-implementation/v2-090f-rerun-rework-entry-validation-spec.md`、`doc/04-implementation/v2-090f-rerun-rework-entry-validation-implementation-plan.md`、V2-090A~E、V2-090G~J、V2-100A~E 产物。
- 依赖：V2-090A~E、V2-090G、V2-090H、V2-090I、V2-090J、V2-090K、V2-100；V2-090K 完成自治整改并保留 fail-closed（失败关闭）现场后，必须通过 V2-100 CEO-governed rework loop（项目经理治理返工循环）复判，才可决定是否标记 V2-090F DONE。
- 输出文件：`examples/directives/tiny-fullstack-prd.md`、`examples/directives/v2-090f-reference-examples.md`、`config/boardroom-runtime.v2-090f.yaml`、`config/boardroom-providers.v2-090f.yaml`、`config/boardroom-roles.v2-090f.yaml`、`src/boardroom_os/proving/v2_090f_prd_agent_team.py`、`src/boardroom_os/proving/v2_090f_rework_entry.py`、`scripts/run_v2_090f_prd_agent_team.py`、`scripts/build_tiny_closeout_sample.py`、`examples/generated-workspaces/tiny-fullstack/`、`examples/README.md`、`scripts/README.md`、`tests/negative/test_v2_090f_agent_team_fail_closed.py`、`tests/negative/test_v2_090f_rework_entry_fail_closed.py`、`tests/proving/test_v2_090f_prd_agent_team_script.py`、`tests/proving/test_v2_090f_prd_agent_team_real.py`、`tests/proving/test_v2_090f_rework_entry_validation.py`。
- 必须先写的 negative tests：缺 PRD、空 PRD、runner 预置固定 ticket graph（任务图）、所有角色复用 `seat.worker.implementation`、缺 CEO/Architect/Worker/Tester/Checker/Closeout required seat、RolePromptHook / skill context mismatch（角色提示词钩子 / 技能上下文不匹配）、非 worker 角色越权写源码、旧 provider lock（模型产物锁）、单 `ProviderAttempt`（模型调用尝试记录）、`ProviderExecutor`（模型供应商执行器）源码交付路径、当前 V2-080 failure package（失败包）、缺 atomic run evidence（原子运行证据）、缺 command/service/live blackbox/source lineage evidence（命令/服务/真实黑盒/来源链证据）均 fail closed。
- 必须证明的 happy path：入口脚本读取 short PRD，并使用 V2-090F 专用高预算配置基线；CEO/Architect/Tester/Worker/Checker/Closeout agent seats（智能体席位）自治产生 directive（指令）、contracts（合同）、ticket graph（任务图）、implementation tickets（实施任务）、verification plan（验证计划）、checker verdict（检查结论）和 closeout/audit artifacts（收尾/审计产物）。Task 7 分段实施：7A 生成合同和任务图，7B 执行 worker implementation tickets，7C 完成 Tester/Checker/Closeout 与 Boardroom gates。implementation tickets 必须通过真实 provider-backed `AtomicAgentExecutor` 执行并产生 provider turn facts、workspace mutation、declared command evidence 和 source lineage input；最终由既有 `SourceInventory`、`RunManifest`、`VerificationRun`、`ServiceRunEvidence`、`LiveBlackboxIntegrationEvidence`、`FinalEvidenceTable`、`WorkspaceEvidenceBundle`、`ReplayBundle`、`ProcessAuditBundle`、`GitVersionAuditBundle` 和 `CloseoutGate` 生成 passed sample（通过样例）。
- 验收口径：golden sample 不再是 provider-locked deterministic fixture（模型产物锁定确定性夹具）或 runner 预拆任务流水线，而是 PRD-to-delivery agent team autonomous sample（从 PRD 到交付的智能体团队自治样例）。`AgentRunResult.status == completed` 只能作为 execution facts（执行事实），不得直接触发 `TICKET_COMPLETED` 或 `CloseoutPackage.passed`。
- 当前阻塞：2026-06-12 已修订 spec/plan 并自审，明确废弃旧 provider-backed generation subprocess、provider artifact lock 和固定三票监督实施作为成功路径。第一次真实 provider run（真实模型运行）跑通 worker implementation chain（工人实施链路）和基础 CRUD，但专家评审认定存在明确外部介入：planning prompt（规划提示词）和 ticket graph validator（任务图校验器）硬编码 `app/server.py`、`python -m app.server`、`LIBRARY_API_*`；closeout runner（收尾运行器）硬编码 `/books` 行为探针；FinalEvidenceTable（最终证据表）和 SourceInventory（源码清单）仍由 runner 内置 `AC-V2-090F-*`、`app/`、`static/`、`tests/` 等第二权威源推断；Checker/Closeout（检查/收尾）也没有各自 provider attempt（模型调用尝试记录）。2026-06-13 V2-090K 已移除这些自治偏移并保留结构化 fail-closed 现场，2026-06-15 V2-100E 已证明返工循环可治理收敛；2026-06-16 新增 `v2-090f-rerun-rework-entry-validation-spec.md` 和 `v2-090f-rerun-rework-entry-validation-implementation-plan.md`，要求先真实重跑 V2-090F 观察是否自然形成 verified blocker / ReworkRequest / TicketGraphPatch（已验证阻塞项 / 返工请求 / 工单图补丁），再决定是否只补最小 rework-entry adapter（返工入口适配器）。实施计划已写入并等待评审；V2-090F 因此继续保持 REVIEW_REQUIRED / BLOCKED，等待该重跑复判。
- 新 `--check` 语义：`scripts/build_tiny_closeout_sample.py --check` 只能验证已发布样例的 PRD sha256、baseline hash（基线哈希）、角色上下文快照、manifest（清单）、文件 hash、证据引用、closeout payload（收尾载荷）和禁用运行时文件；不得调用 provider（模型供应商），不得写 output root（输出根目录），也不得单独作为 agent team framework 端到端成立证据。
- 配置基线：V2-090F 使用独立 `config/boardroom-*.v2-090f.yaml`，所有角色采用 high reasoning（高推理）和高预算 `agent_team.v2_090f.fullstack` 或等价 profile；预算、timeout（超时）和 retry policy（重试策略）必须进入 baseline hash，不得通过 `.env` 临时覆盖。允许提高 provider timeout，禁止 workspace mutation 后整票重试。

### V2-090K: Agent team autonomy remediation（智能体团队自治整改）

- 状态：DONE
- 目标：整改 V2-090F first run（首次运行）暴露的自治性偏移，把可启动性、环境映射、前后端拓扑、行为探针计划、验收合同、源码面归属、检查结论和收尾草案交回 agent role（智能体角色）产出；runner（运行器）只消费 AcceptanceContract（验收合同）/PackageContract（包合同）/RunManifest（运行清单）/BehavioralProbePlan（行为探针计划）并执行真实门禁。
- 输入文档：`docs/superpowers/specs/2026-06-12-v2-090k-agent-team-autonomy-remediation-design.md`、`docs/superpowers/plans/2026-06-12-v2-090k-agent-team-autonomy-remediation.md`、`doc/05-project-log/v2-090f-implementation-intervention-log.md`、V2-090F first run 专家评审报告、V2-090A~E/G~J 产物。
- 依赖：V2-090A~E、V2-090G、V2-090H、V2-090I、V2-090J、V2-090F first run evidence（首次运行证据）。
- 输出文件：`src/boardroom_os/agents/prompt_templates/baseline/v1/release_devops.md`、`src/boardroom_os/agents/role_prompt_hooks.py`、`config/boardroom-roles.v2-090f.yaml`、`src/boardroom_os/workspace/run_manifest.py`、`src/boardroom_os/proving/v2_090f_prd_agent_team.py`、`tests/negative/test_v2_090k_autonomy_regression_fail_closed.py`、`tests/proving/test_v2_090k_dynamic_closeout_contract.py`、`examples/generated-workspaces/tiny-fullstack/`、`examples/generated-workspaces/tiny-fullstack/30-audit/v2-090k-failure-snapshot/`。
- 必须先写的 negative tests：active source/tests/config（活动源码/测试/配置）不得继续要求 `app/server.py`、`python -m app.server`、`LIBRARY_API_HOST`、`LIBRARY_API_PORT`、`LIBRARY_DB_PATH`、固定 backend/SQLite/frontend/integration/docs 五票任务图、`/books` / `Dune` / `checked_out` 等业务域探针、`AC-V2-090F-*` 静态验收引用，或 `app/` / `static/` 路径前缀源码面权威映射；缺 agent-generated AcceptanceContract（智能体生成验收合同）、PackageContract（包合同）、RunManifest（运行清单）、BehavioralProbePlan（行为探针计划）、service command（服务命令）、env binding（环境绑定）、readiness probe（就绪探针）、frontend/backend topology（前后端拓扑）、source surface path mapping（源码面路径映射）、Checker ProviderAttempt（检查者模型调用尝试记录）或 Closeout ProviderAttempt（收尾者模型调用尝试记录）均 fail closed；任何 dict-only（仅字典）AcceptanceContract/PackageContract/SourceSurface/FinalEvidenceTable/SourceInventory（验收合同/包合同/源码面/最终证据表/源码清单）平行实现不得作为通过路径。
- 必须证明的 happy path：RolePromptHook（角色提示词钩子）新增或强化 DevOps/Release（运维/发布）职责；Architect/Tester/Release DevOps（架构/测试/发布运维）从 PRD 产出 AcceptanceContract（验收合同）、PackageContract（包合同）、RunManifest（运行清单）和声明式 BehavioralProbePlan（行为探针计划），由 runner 动态绑定 agent 声明的 env names（环境变量名）并按声明启动服务、执行 readiness/live behavioral probes（就绪/真实行为探针）；BehavioralProbe executor（行为探针执行器）必须支持 capture（捕获）、`${}` interpolation（占位符替换）和 `json_equals` / `json_contains` / `field_equals` / `field_absent` 断言且失败关闭；AcceptanceContract / PackageContract 必须强类型解析并通过 validate_contract_gate（合同门禁校验）；FinalEvidenceTable（最终证据表）只由现有 FinalEvidenceTableBuilder（最终证据表构建器）从 AcceptanceContract 构造，SourceInventory（源码清单）只由现有 build_source_inventory（源码清单构建器）从 PackageContract.source_surfaces（包合同源码面）和 SourceLineageRecord（源码来源链记录）构造；Checker/Closeout（检查/收尾）各自产生 provider-backed artifact（模型支撑产物）。真实 provider full run 若暴露合同、实现、探针或收尾投影不一致，必须 fail closed 并保留 failure taxonomy（失败分类）和可供 V2-100 消费的 failure snapshot（失败快照），不得放松门禁。
- 验收口径：V2-090K 只在消除 090F first run 的硬编码运行接口、固定任务图、业务域探针、静态验收引用、路径前缀源码面映射和 helper-written checker/closeout verdict（辅助器写检查/收尾结论）后成立；它不要求 single-pass full run passed（单轮完整运行通过），也不要求默认 `--check` exit 0 才能标记 DONE。若真实 provider full run 失败但失败来自 agent 产物之间的合同/实现/探针不一致，且 runner 已 fail closed 并留下结构化现场，则该失败是 V2-100 的输入。V2-090F golden sample 是否满足 package + closeout + audit（包/收尾/审计）验收，必须等 `V2-090K + V2-100` 后复判。
- 完成证据：2026-06-13 已实现并验证 090K helper/runner 负例与动态收尾基础设施；真实 provider full run 产生 tiny-fullstack 产物但 fail closed 暴露四类 blocker：BehavioralProbePlan（行为探针计划）期待 `$.title` / `$.id` 而 backend 创建响应为 `{"ok": true, "book": {...}, "id": ...}`；RunManifest（运行清单）声明 `HOST` / `PORT` / `DATABASE_PATH` 但实现仍读取 `LIBRARY_DB_PATH` 等额外环境变量；FinalEvidenceTable（最终证据表）仍投影旧 `AC-TINY-*` 验收引用；closeout/audit（收尾/审计）仍引用 `run-v2-080f`。精选现场保存在 `examples/generated-workspaces/tiny-fullstack/30-audit/v2-090k-failure-snapshot/`，作为 V2-100A~E 的真实失败输入；完整 raw provider artifacts（原始模型产物）仍保留在工作区但未复制进精选快照。

### V2-090I: Resettable medium implementation scenario（可重置中等复杂实施场景）

- 状态：DONE
- 目标：构造一个可重置的中等复杂 implementation ticket（实施任务），由真实 provider-backed atomic-agent executor（模型供应商支撑原子智能体执行器）生成多文件 Python package/CLI（Python 包/命令行工具），包含文件间 import（导入依赖）、非平凡数学/算法逻辑、真实 unittest/CLI 验证和可审计 JSON report（报告）。
- 输入文档：`docs/superpowers/specs/2026-06-10-v2-090i-resettable-medium-scenario-design.md`、`docs/superpowers/plans/2026-06-10-v2-090i-resettable-medium-scenario.md`、`config/boardroom-runtime.example.yaml`、`config/boardroom-providers.example.yaml`、`config/boardroom-roles.example.yaml`、`scripts/run_atomic_agent_retry_rate_probe.py`、`scripts/run_tiny_atomic_agent_executor.py`。
- 依赖：V2-090G、V2-090H。
- 输出文件：`scripts/run_v2_090i_medium_scenario.py`、`tests/proving/test_v2_090i_medium_scenario_script.py`、`tests/proving/test_v2_090i_medium_scenario.py`、`scripts/README.md`。
- 必须先写的 negative tests（负例测试）：reset 拒绝删除缺 marker 的既有目录；真实 provider proving test 默认跳过；脚本缺 provider secret 时 fail closed；validator command 拒绝缺文件、缺 import、算法结果错误、unittest/CLI 失败。
- 必须证明的 happy path（正向路径）：显式 opt-in 后，专项测试先 `--reset` 初始化场景，再通过真实 provider-backed atomic-agent executor 生成 `forecast_engine` 多文件 package，运行 `cmd.check-medium-scenario` exit 0，event stream 包含 provider turn facts、workspace mutation、command evidence 和 source lineage input。
- 验收口径：V2-090I 只证明中等复杂单 ticket 可信交付能力；不解除 V2-090F BLOCKED，不生成 closeout passed golden sample。
- 历史阻塞证据：2026-06-10 三次真实 provider-backed run 均未通过 `tests/proving/test_v2_090i_medium_scenario.py`。第一次 `boardroom-atomic.v2-090i.medium.20260610T145623Z.cbc1565e` 发生多次 invalid JSON / `action_envelope` schema mismatch，写出 `__init__.py` 与 `statistics.py` 后 `run.failed`。第二次 `boardroom-atomic.v2-090i.medium.20260610T150942Z.6856ed07` 已能输出合法 action，但选择 `apply_patch` 一次写多文件，被 permission policy 拒绝为 `invalid_path_type_denied`。第三次 `boardroom-atomic.v2-090i.medium.20260610T151602Z.f22b41dc` 禁用 `apply_patch` 后写出 `__init__.py`、`statistics.py`、`risk.py`、`cli.py`，产生 11 个 provider turns、7 个 action rejections 和 4 个 workspace mutations，但未生成 `work/tests/test_forecast_engine.py`，未运行 `cmd.check-medium-scenario`，最终因 `action_parse_failed` / invalid JSON 失败。
- 完成证据：2026-06-11 在 V2-090J action protocol repair（原子动作协议修复）后复跑 V2-090I 原 runner。`BOARDROOM_RUN_REAL_PROVIDER_PROVING=1 PYTHONPATH=src:. python -m pytest tests/proving/test_v2_090i_medium_scenario.py -q --tb=short --basetemp .pytest-tmp-v2090i-medium-real-rerun` 通过（`1 passed in 222.99s`）；独立 runner `PYTHONPATH=src:. python scripts/run_v2_090i_medium_scenario.py --reset` exit 0，run id `boardroom-atomic.v2-090i.medium.20260611T160350Z.9f07d150`，report（报告）包含 `success=true`、`terminal_event_type="run.completed"`、`provider_turn_completed_count=10`、`command_exit_codes["cmd.check-medium-scenario"]=0`、9 条 workspace mutations（工作区变更）和 5 条 source lineage inputs（源码来源链输入）。非 provider 验证 `PYTHONPATH=src:. python -m pytest tests/proving/test_v2_090i_medium_scenario_script.py tests/proving/test_v2_090i_medium_scenario.py -q --tb=short --basetemp .pytest-tmp-v2090i-non-provider-rerun` 通过（`9 passed, 1 skipped`）。
- 根因结论：V2-090I 先前失败不是 Boardroom evidence gates（证据门禁）整体过严，而是 atomic-agent action protocol（原子动作协议）对中等复杂任务过脆、`apply_patch` 工具可见性与权限策略错配、validator command（验证命令）没有作为执行循环 checkpoint（检查点）前置调度。V2-090J 修复后，V2-090I 原场景已证明中等复杂单 ticket 可信交付能力；完整流水和外部评审见 `doc/05-project-log/v2-090i-implementation-run-record.md`。

### V2-090J: Atomic action protocol repair（原子动作协议修复）

- 状态：DONE
- 目标：修复 V2-090I 暴露的 action protocol（动作协议）、tool policy（工具策略）和 validator checkpoint（验证命令检查点）问题，并用中等复杂真实 provider proving test（真实供应商证明测试）复验。
- 输入文档：`docs/superpowers/specs/2026-06-11-v2-090j-atomic-action-protocol-repair-design.md`、`docs/superpowers/plans/2026-06-11-v2-090j-atomic-action-protocol-repair.md`、`doc/05-project-log/v2-090i-implementation-run-record.md`、外部 atomic-agent action protocol docs（动作协议文档）。
- 依赖：V2-090H、V2-090I 阻塞证据、外部 atomic-agent 可修改并通过 baseline tests（基线测试）。
- 输出文件：`scripts/run_v2_090j_medium_scenario.py`、`tests/proving/test_v2_090j_medium_scenario_script.py`、`tests/proving/test_v2_090j_medium_scenario.py`、Boardroom 配置/执行器测试、外部 atomic-agent batch/checkpoint 改动。
- 必须先写的 negative tests（负例测试）：裸数组、串联 JSON、Markdown 包裹 JSON、缺 `protocol` 的 batch-like output（批次形状输出）、`action_envelope`、超过 `max_actions_per_turn`、`apply_patch` 可见但 runtime 不支持、checkpoint 多命令包、缺 command evidence 均必须 fail closed。
- 必须证明的 happy path（正向路径）：真实 provider-backed executor 通过显式 `agent-action-batch-v1` 或等价 provider-native structured output（结构化输出）完成 medium package/CLI，运行 `cmd.check-medium-scenario` exit 0，并产生 provider turn facts、workspace mutation、command evidence 和 source lineage input。
- 验收口径：V2-090J 只证明 action protocol repair 后中等复杂 executor path 恢复；不放松 command evidence、workspace mutation、source lineage 或 provider turn facts 门禁；不自动解除 V2-090F BLOCKED。
- 当前证据：atomic-agent targeted tests `106 passed`；Boardroom targeted tests `81 passed, 1 skipped`；真实 provider proving gate `tests/proving/test_v2_090j_medium_scenario.py` 在显式 opt-in 下通过，初次通过耗时 `534.17s`。2026-06-11 复跑中，第一次 run `boardroom-atomic.v2-090j.medium.20260611T054851Z.7c27fddc` 因 provider 输出串联多个 JSON 后又遇到 provider SDK connection error 失败；第二次 pytest gate 通过，run id `boardroom-atomic.v2-090j.medium.20260611T055454Z.016a2a2a`，结果 `1 passed in 505.05s`，事件流包含 5 个 provider turns、9 个 workspace mutations、5 次 `cmd.check-medium-scenario` command evidence（最终 exit 0）、1 个 `result.submitted` 和 `run.completed`；随后独立 runner report `boardroom-atomic.v2-090j.medium.20260611T060341Z.b564b20d` 也通过，包含 8 个 provider turns、11 个 workspace mutations、6 次 `cmd.check-medium-scenario` command evidence（最终 exit 0）、source lineage input 和 `run.completed`。早期三次真实 run（`...183832Z.eb20d2d6`、`...185459Z.40fd49fe`、`...191431Z.593beabf`）保留为 protocol/prompt 修复前的失败或不稳定证据。


### V2-090G: Atomic-agent package/import integration

- 状态：DONE
- 目标：通过同级目录安装并 import 外部 `atomic-agent` Python package（Python 包），建立 Boardroom OS 到 `AgentRuntimePort`（智能体运行端口）的防腐边界、调用编译器、结果校验器和事实投影输入；本工作包不切换 implementation ticket（实施任务）主执行路径。
- 输入文档：`doc/04-implementation/v2-090g-atomic-agent-package-integration-spec.md`、`doc/04-implementation/v2-090g-atomic-agent-package-integration-implementation-plan.md`、`../atomic-agent/docs/03-contracts/agent-runtime-port.md`、`../atomic-agent/docs/03-contracts/agent-action-protocol.md`、`../atomic-agent/docs/03-contracts/event-stream-protocol.md`、`../atomic-agent/docs/00-overview/boardroom-os-integration-summary.md`、`doc/03-architecture/execution-and-runtime-boundary.md`、`doc/03-architecture/contract-and-evidence-model.md`。
- 依赖：V2-090E、V2-090F 阻塞复盘、外部 `atomic-agent` 可通过 `python -m pip install -e ../atomic-agent` 安装。
- 输出文件：`src/boardroom_os/execution/atomic_agent.py`、`tests/execution/test_atomic_agent_invocation_compiler.py`、`tests/execution/test_atomic_agent_result_projection.py`、`tests/negative/test_atomic_agent_integration_fail_closed.py`、`tests/proving/test_tiny_atomic_agent_bridge.py`、`README.md`、必要时 `src/boardroom_os/execution/__init__.py`。
- 必须先写的 negative tests：缺 `atomic-agent` package 不得 fallback；`AgentRunResult.status != completed` 不得生成 successful WorkProduct（成功工作产物）；缺 event stream/hash/tool attempts/workspace mutations/artifacts 必须失败；event stream hash mismatch（事件流哈希不一致）必须失败；atomic-agent 返回 `ticket_completed` / `closeout_committed` / `evidence_verified` 等治理字段必须失败；workspace mutation path（工作区变更路径）超出 `allowed_write_set` 必须失败；command_id 未在 ExecutionPackage.commands 声明必须失败。
- 必须证明的 happy path：ExecutionPackage 可确定性编译为 atomic-agent `AgentInvocation`；fake `AgentRuntimePort` 返回 completed `AgentRunResult` 后，Boardroom 可验证 event stream hash，投影 workspace mutations/artifacts 为 WorkProductSubmission（工作产物提交）和 SourceInventory lineage input（源码清单来源链输入）；README 说明同级目录安装和 import 验证命令。
- 验收口径：atomic-agent 作为外部 package/import 执行边界接入，Boardroom 不复制源码、不调用不稳定示例 CLI、不服务化；atomic-agent completed 只作为 execution evidence（执行证据），后续仍由 EvidenceVerifier / Checker / Reducer / CloseoutGate 决定完成和收尾。V2-090G 只证明 adapter/compiler/validator/projector（适配器/编译器/校验器/投影器）边界可用，不证明 `ProviderExecutor`（模型供应商执行器）主路径已被替换，也不得自动恢复 V2-090F。
- 完成证据：2026-06-10 新增 `AtomicAgentPackageAdapter`（原子智能体包适配器）、`AtomicInvocationCompiler`（原子调用编译器）、`AtomicAgentResultValidator`（原子结果校验器）与 `AtomicResultProjector`（原子结果投影器），通过外部 `atomic-agent` package import（包导入）调用 `AgentRuntimePort`（智能体运行端口），并把 completed `AgentRunResult`（智能体运行结果）的 event stream / tool attempts / workspace mutations / artifacts（事件流 / 工具尝试 / 工作区变更 / 产物）投影为 Boardroom `WorkProductSubmission`（工作产物提交）和 SourceInventory lineage input（源码清单来源链输入）。Negative tests 覆盖缺包、缺可审计 package version（包版本）或 `unknown` 版本、伪造同名 AgentRunResult、failed/interrupted status（失败/中断状态）、缺 workspace mutation（工作区变更）、治理字段注入、allowed_write_set（允许写入集合）越界、POSIX / Windows 绝对路径与 `..` 逃逸、command cwd（命令工作目录）越界、文件路径目录扩权、result-side 与 event stream `command_results`（事件流命令结果）未声明 command_id（命令编号）、result.run_id（结果运行 ID）与 event stream run_id（事件流运行 ID）不一致、event stream bytes/hash mismatch（事件流字节哈希不一致）、event hash chain mismatch（事件哈希链不一致）、event_stream_root（事件流根目录）缺失或越界、artifact 缺 sha256、workspace mutation 缺 tool attempt lineage（工具尝试来源链）和 provider attempt / execution package mismatch（模型调用尝试 / 执行包不匹配）、result 侧 workspace mutation/artifact 与 event stream summary（事件流摘要）不一致。验证证据：`PYTHONPATH=src:. python -m pytest tests/execution/test_atomic_agent_invocation_compiler.py tests/execution/test_atomic_agent_result_projection.py tests/negative/test_atomic_agent_integration_fail_closed.py tests/proving/test_tiny_atomic_agent_bridge.py -q --tb=short --basetemp .pytest-tmp-v2090g-targeted-final` 通过（36 passed）；`PYTHONPATH=src:. python -m pytest tests/execution/test_execution_package_schema.py tests/execution/test_execution_package_compiler.py tests/execution/test_work_product_submission.py tests/evidence/test_evidence_claim.py tests/evidence/test_evidence_verifier.py tests/reducers/test_completion_gate_with_evidence.py -q --tb=short --basetemp .pytest-tmp-v2090g-regression-final` 通过（146 passed）；`PYTHONPATH=src:. python -m pytest tests/proving/test_tiny_contracts.py tests/proving/test_tiny_ticket_graph.py tests/proving/test_tiny_live_blackbox_integration.py tests/proving/test_workspace_evidence_export.py tests/proving/test_tiny_atomic_agent_bridge.py -q --tb=short --basetemp .pytest-tmp-v2090g-phase9-final` 通过（47 passed）；`git diff --check` 通过。V2-090G 不重建 golden sample（黄金样例），V2-090F 仍为 BLOCKED。

### V2-090H: Atomic-agent executor switch

- 状态：DONE
- 目标：新增 Boardroom OS implementation execution path（实施执行路径），使用外部 atomic-agent executor（原子智能体执行器）替代 `ProviderExecutor`（模型供应商执行器）单次 LLM request（大模型请求）作为 implementation ticket（实施任务）的主执行器；构造并派发一个 atomic implementation ticket（原子实施任务），由接入真实 provider（模型供应商）的 atomic-agent executor 在受控 workspace（工作区）内读写文件、运行允许命令、观察失败并提交结果。
- 输入文档：`doc/04-implementation/v2-090g-atomic-agent-package-integration-spec.md`、`doc/04-implementation/v2-090g-atomic-agent-package-integration-implementation-plan.md`、`../atomic-agent/docs/03-contracts/agent-runtime-port.md`、`../atomic-agent/docs/03-contracts/agent-action-protocol.md`、`../atomic-agent/docs/03-contracts/event-stream-protocol.md`、`../atomic-agent/docs/00-overview/boardroom-os-integration-summary.md`、`doc/03-architecture/execution-and-runtime-boundary.md`、`doc/03-architecture/contract-and-evidence-model.md`、`doc/04-implementation/acceptance-criteria.md`。
- 依赖：V2-090G、外部 `atomic-agent` 可通过 `python -m pip install -e ../atomic-agent` 安装并具备真实 provider-backed executor（模型供应商支撑执行器）。
- 输出文件：预计 `src/boardroom_os/execution/atomic_executor.py`、`tests/execution/test_atomic_agent_executor.py`、`tests/negative/test_atomic_agent_executor_fail_closed.py`、`tests/proving/test_tiny_atomic_agent_executor.py`；必要时更新 `src/boardroom_os/execution/__init__.py`、`scripts/` 下 proving helper（证明辅助脚本）。
- 必须先写的 negative tests：implementation category（实施类别）ticket 仍走 `ProviderExecutor.execute`（模型供应商执行器执行）必须失败；缺 `AtomicAgentPackageAdapter` / `AgentRuntimePort` / `event_stream_root` / active `ExecutionPackage`（执行包）必须失败；atomic result 缺 ProviderAttempt（模型调用尝试记录）、ToolAttempt（工具尝试）、CommandEvidence（命令证据）、workspace mutation（工作区变更）或 source lineage input（源码来源链输入）必须失败；fake provider transport（模拟模型传输）不得满足本工作包真实 executor happy path；atomic-agent completed（运行完成）不得直接触发 `TICKET_COMPLETED`（任务完成）或 closeout passed（收尾通过）。
- 必须证明的 happy path：构造一个最小 atomic implementation ticket（原子实施任务），由真实 provider-backed atomic-agent executor 通过 `AgentRuntimePort.invoke(AgentInvocation)`（智能体运行端口调用）写入预期文件、运行声明命令、产出 event stream（事件流）和 command evidence（命令证据）；Boardroom OS 通过 `AtomicAgentResultValidator`（原子结果校验器）与 `AtomicResultProjector`（原子结果投影器）生成 `WorkProductSubmission`（工作产物提交）和 source lineage input（源码来源链输入），且后续仍由 EvidenceVerifier（证据验证器）/ Checker（检查者）/ Reducer（归约器）/ CloseoutGate（收尾门禁）决策。
- 验收口径：implementation ticket 主执行路径必须可配置或明确切换到 atomic-agent executor；老 `ProviderExecutor` 单次 LLM JSON source delivery（源码交付）不得再被用于证明 implementation work（实施工作）完成，只能保留为非实施类 provider attempt（模型调用尝试）或显式标记的 legacy-blocked path（遗留阻塞路径）。完成 V2-090H 后仍不得自动恢复 V2-090F；必须先由人工评审 V2-090H 真实执行证据，再明确确认是否将 V2-090F 从 BLOCKED 恢复为 TODO / IN_PROGRESS。
- 完成证据：2026-06-10 新增三文件配置模型（runtime/providers/roles，运行时/供应商/角色配置）、`AtomicAgentExecutor`（原子智能体执行器）、`AtomicAgentRuntimeFactory`（原子智能体运行时工厂）、provider attempt projection（模型调用尝试投影）和真实 proving helper（证明辅助脚本）。真实 provider-backed proving（模型供应商支撑证明）通过 `tests/proving/test_tiny_atomic_agent_executor.py`，由外部 atomic-agent `AgentRuntimePort.invoke(AgentInvocation)`（智能体运行端口调用）写入 `work/real-provider-output.txt`、执行声明命令 `cmd.check-output`、产生 canonical event stream（规范事件流）、workspace mutation（工作区变更）、command evidence（命令证据）、provider turn facts（模型轮次事实）和 source lineage input（源码来源链输入）。Negative tests 覆盖 `ProviderExecutor` 不得满足 implementation ticket evidence（实施任务证据）、缺 runtime port（运行时端口）、缺 provider turn facts、缺 command evidence、fake provider transport（模拟供应商传输）、治理字段注入、CRLF event stream（CRLF 事件流）、retry after workspace mutation（工作区变更后重试）、相对 event stream ref（事件流引用）解析、目录 allowed_write_set（允许写入集合）策略、`after_hash` 写后哈希和 extra audit artifacts（额外审计产物）。V2-090H 不直接触发 `TICKET_COMPLETED`（任务完成）或 closeout passed（收尾通过），V2-090F 仍需人工评审后决定是否恢复。


---

## V2-100: Agent-team Rework Loop Hardening（智能体团队返工循环强化）

- 状态：DONE
- 目标：把 agent team（智能体团队）从 single-pass fail-closed（单轮失败关闭）升级为 CEO-governed rework loop（项目经理治理返工循环）。当 Checker（检查者）或 CloseoutGate（收尾门禁）发现合同、证据、接口协议或实现不一致时，系统应生成结构化 blocker（阻塞项）、由 CEO/Architect（项目经理/架构师）规划返工并更新 TicketGraph（工单图），再由 Worker/Tester/Checker/Closeout（实施/测试/检查/收尾）按新图返工、重验、留痕。
- 输入文档：`domain-model.md`、`contract-and-evidence-model.md`、`execution-and-runtime-boundary.md`、`acceptance-criteria.md`、`examples/generated-workspaces/tiny-fullstack/30-audit/v2-090k-failure-snapshot/`、V2-090F/K 真实 full run 失败证据、`doc/05-project-log/v2-090f-implementation-intervention-log.md`。
- 输出目录：`src/boardroom_os/`、`tests/`、`scripts/`、必要时 `examples/generated-workspaces/tiny-fullstack/20-evidence/` 审计产物。
- 顶层验收口径：V2-100 不追求一次性生成正确项目；它必须证明首轮局部产物不达标时，agent team 能自治发现具体问题、形成 ReworkRequest（返工请求）、生成 ReworkPlan（返工计划）、更新 TicketGraph（工单图）、执行返工、重新进入 EvidenceVerifier（证据验证器）/ Checker（检查者）/ CloseoutGate（收尾门禁），并把每轮 provider attempt、事件、证据和决策完整留痕。runtime（运行时）只执行事实，不做 CEO 决策。

### V2-100A: Rework domain model（返工领域模型）

- 状态：DONE
- 目标：实现 ReworkCycle（返工循环）、ReworkRequest（返工请求）、ReworkIssue（返工问题）、ReworkPlan（返工计划）、ReworkAttempt（返工尝试）和 ReworkOutcome（返工结果）的强类型模型，作为 Checker/Closeout blocker（检查/收尾阻塞项）到 CEO 返工规划的合同边界。
- 输入文档：`doc/03-architecture/domain-model.md`、`doc/03-architecture/contract-and-evidence-model.md`、`examples/generated-workspaces/tiny-fullstack/30-audit/v2-090k-failure-snapshot/failure-summary.json`、V2-090K 真实 full run 失败证据。
- 依赖：V2-090K DONE；090K curated failure snapshot（精选失败快照）；V2-050 Evidence/Checker（证据/检查）模型；V2-020 TicketGraph（工单图）。
- 输出文件：`src/boardroom_os/rework/model.py`、`src/boardroom_os/rework/blocker_projection.py`、`src/boardroom_os/rework/__init__.py`、`tests/rework/test_rework_model.py`、`tests/rework/test_v2_090k_failure_snapshot_projection.py`、`tests/negative/test_rework_model_fail_closed.py`。
- 必须先写的 negative tests：缺 verified blocker（已验证阻塞项）不得创建 ReworkRequest；ReworkIssue 缺 acceptance_ref/source_surface_ref/required_artifact_type（验收引用/源码面/必需产物类型）必须失败；ReworkPlan 缺 planner_attempt_ref（规划者模型调用尝试引用）或 ticket_graph_patch_ref（工单图补丁引用）必须失败；ReworkAttempt 缺 ExecutionPackage（执行包）、provider attempt、command evidence 或 source lineage input（源码来源链输入）不得作为返工尝试；只从自由文本 exception（异常）或 reviewer note（评审备注）创建返工请求必须失败。
- 必须证明的 happy path：由 FinalEvidenceTable missing/failed row（最终证据表缺失/失败行）、Checker blocker（检查阻塞项）或 CloseoutGate failure（收尾门禁失败）构造 ReworkRequest；090K failure snapshot（失败快照）中的 `probe-response-shape-mismatch`、`env-binding-not-converged`、`final-evidence-uses-old-acceptance-refs` 和 `closeout-audit-references-old-run` 可投影为结构化 ReworkIssue（返工问题）；后续 ReworkAttempt 和 ReworkOutcome 可序列化、hash、审计。
- 验收口径：返工对象是 V2 一等领域模型，不是 Python exception（异常）、自由文本 notes（备注）或 runner helper（运行器辅助器）私有结构。
- 完成证据：2026-06-14 已实现强类型 ReworkCycle / ReworkRequest / ReworkIssue / ReworkPlan / ReworkAttempt / ReworkOutcome（返工循环/请求/问题/计划/尝试/结果）和 BlockerReport（阻塞报告）投影；090K failure snapshot 可投影为结构化返工请求；缺 verified blocker、缺 blocker source、缺 provider attempt、缺 command/source evidence、自由文本异常/备注创建返工等负例均 fail closed。验证：`PYTHONPATH=src python -m pytest tests/negative/test_rework_model_fail_closed.py tests/rework/test_rework_model.py tests/rework/test_v2_090k_failure_snapshot_projection.py -q` 通过（20 passed）；`PYTHONPATH=src:. python -m pytest tests/contracts tests/reducers tests/execution tests/evidence tests/closeout tests/negative -q` 通过（1463 passed）。

### V2-100B: Rework event taxonomy + reducer（返工事件分类与归约器）

- 状态：DONE
- 目标：新增返工 typed events（类型化事件）和 reducer（归约器）门禁，确保 ReworkCycle（返工循环）状态只能通过治理事实推进，runtime/atomic-agent（运行时/原子智能体）不能直接提交 accepted/completed（接受/完成）。
- 输入文档：`doc/03-architecture/execution-and-runtime-boundary.md`、`doc/03-architecture/domain-model.md`、V2-020 event/reducer（事件/归约器）产物。
- 依赖：V2-100A。
- 输出文件：预计 `src/boardroom_os/events/types.py` 事件扩展、`src/boardroom_os/reducers/rework.py`、`tests/reducers/test_rework_reducer.py`、`tests/negative/test_rework_reducer_fail_closed.py`。
- 必须先写的 negative tests：runtime actor（运行时执行者）提交 `REWORK_ACCEPTED` / `REWORK_ESCALATED` / `REWORK_EXHAUSTED` 必须失败；无 `REWORK_REQUESTED` 直接 `REWORK_PLANNED` 必须失败；ReworkTicket（返工工单）扩大 allowed_write_set（允许写集合）或引用非 active AcceptanceContract（活跃验收合同）必须失败；同一 blocker 未被重新验证时不得关闭返工循环。
- 必须证明的 happy path：`REWORK_REQUESTED -> REWORK_PLANNED -> REWORK_TICKET_CREATED -> REWORK_ATTEMPT_SUBMITTED -> REWORK_REVIEWED -> REWORK_ACCEPTED` 可由治理角色和 reducer 按 graph_version（图版本）推进，并产出可回放 projection（投影）。
- 验收口径：TicketGraph（工单图）仍是流程状态源；返工状态不可由 executor/runtime（执行器/运行时）直接写终态。
- 完成证据：2026-06-14 已实现 `REWORK_REQUESTED` / `REWORK_PLANNED` / `REWORK_GRAPH_PATCH_REVIEWED` / `REWORK_GRAPH_PATCH_APPROVED` / `REWORK_TICKET_CREATED` / `REWORK_ATTEMPT_STARTED` / `REWORK_ATTEMPT_SUBMITTED` / `REWORK_REVIEWED` / `REWORK_ACCEPTED` / `REWORK_ESCALATED` / `REWORK_EXHAUSTED` 返工事件分类与 ReworkReducer（返工归约器）；runtime/executor/atomic-agent（运行时/执行器/原子智能体）不能提交治理终态；GraphPatchReviewGate（图补丁审查门禁）要求必需审查域 ready_to_commit；返工工单创建受 TicketGraphPatch（工单图补丁）、active acceptance refs（活跃验收引用）、source surfaces（源码面）、evidence obligations（证据义务）和 allowed_write_set（允许写集合）约束。验证：`PYTHONPATH=src:. python -m pytest tests/contracts tests/reducers tests/execution tests/evidence tests/closeout tests/rework tests/negative -q` 通过（1496 passed）。

### V2-100C: CEO rework planner boundary（CEO 返工规划边界）

- 状态：DONE
- 目标：让 CEO（项目经理/治理角色）读取 BlockerReport（阻塞报告）/ ReworkRequest（返工请求），生成 ReworkPlan（返工计划）和 TicketGraphPatch（工单图补丁），并决定修原 ticket、拆新 ticket、重排依赖、要求合同修订或升级人工复核。
- 输入文档：`doc/03-architecture/agent-team-model.md`、`doc/03-architecture/domain-model.md`、`doc/03-architecture/execution-and-runtime-boundary.md`、V2-090F/K 失败案例。
- 依赖：V2-100A、V2-100B、V2-090A RolePromptHook（角色提示词钩子）。
- 输出文件：`src/boardroom_os/rework/planner.py`、`src/boardroom_os/rework/ticket_graph_patch.py`、`src/boardroom_os/rework/reviewer.py`、`src/boardroom_os/rework/__init__.py`、`tests/rework/test_ceo_rework_planner.py`、`tests/rework/test_multi_role_graph_patch_reviews.py`、`tests/negative/test_ceo_rework_planner_fail_closed.py`、`tests/negative/test_multi_role_graph_patch_reviews_fail_closed.py`、`tests/execution/test_role_prompt_hooks_rework_governance.py`。
- 必须先写的 negative tests：缺 CEO ProviderAttempt（项目经理模型调用尝试）不得生成 ReworkPlan；CEO 计划没有逐项映射 blocker_refs（阻塞引用）必须失败；计划 action（动作）不在 `fix_implementation` / `fix_contract_or_probe` / `split_ticket` / `reorder_dependencies` / `escalate_human_review` 枚举内必须失败；计划直接修改源码或写 passed verdict（通过结论）必须失败；计划绕过 active contract、复用旧 evidence row、把 Checker notes 当 blocker 豁免或要求 runtime 自动修复必须失败。
- 必须证明的 happy path：以 090K 真实失败形态为输入，例如 RunManifest（运行清单）期待 `$.title` 但 backend 实际返回 `{"book": {...}}`，CEO 能在有限决策空间内生成明确返工路线：`fix_implementation` 或 `fix_contract_or_probe`，必要时 `split_ticket` / `reorder_dependencies` / `escalate_human_review`，创建目标 ReworkTicket，并保持 evidence obligations（证据义务）可追踪。
- 验收口径：CEO 是返工路线和 TicketGraphPatch（工单图补丁）的权威规划者；runtime 不做项目经理决策。
- 完成证据：2026-06-14 已实现 provider-backed CEO ReworkPlan（模型支撑项目经理返工计划）严格解析与 lineage validation（来源链校验）、TicketGraphPatch（工单图补丁）active contract scope validation（活跃合同范围校验）、required review domain inference（必需审查域推导）、multi-role GraphPatchReview（多角色图补丁审查）解析与 approval set builder（批准集合构建）。负例证明缺 CEO ProviderAttempt、fallback attempt、错误 role hook、未映射 blocker、planner input 合同引用与 ReworkRequest 不一致、`narrow_scope`、旧 `AC-TINY-*` acceptance refs、prose-only output、审查缺 provider attempt / wrong domain / 缺 checked invariants 均 fail closed。正例证明 090K 四类失败可形成 CEO 计划、必需审查域和 reducer-backed rework ticket commit。验证：`PYTHONPATH=src:. python -m pytest tests/negative/test_ceo_rework_planner_fail_closed.py tests/negative/test_multi_role_graph_patch_reviews_fail_closed.py tests/rework/test_ceo_rework_planner.py tests/rework/test_multi_role_graph_patch_reviews.py tests/execution/test_role_prompt_hooks_rework_governance.py -q` 通过（31 passed）；`PYTHONPATH=src:. python -m pytest tests/rework/test_rework_model.py tests/rework/test_v2_090k_failure_snapshot_projection.py tests/reducers/test_rework_reducer.py tests/negative/test_rework_model_fail_closed.py tests/negative/test_rework_reducer_fail_closed.py -q` 通过（32 passed）；`PYTHONPATH=src:. python -m pytest tests/contracts tests/reducers tests/execution tests/evidence tests/closeout tests/rework tests/negative -q` 通过（1521 passed）。

### V2-100D: Rework evidence/checker reintegration（返工证据与检查重接入）

- 状态：DONE
- 目标：每次 ReworkAttempt（返工尝试）产物都必须重新进入 EvidenceVerifier（证据验证器）、FinalEvidenceTableBuilder（最终证据表构建器）、SourceInventory（源码清单）和 CheckerVerdict（检查结论），不得复用上一轮通过结论。
- 输入文档：`doc/03-architecture/contract-and-evidence-model.md`、`doc/04-implementation/acceptance-criteria.md`、V2-050/V2-070/V2-090 evidence（证据）产物。
- 依赖：V2-100A、V2-100B、V2-100C。
- 输出文件：预计 `src/boardroom_os/rework/evidence.py`、Evidence/Checker/Closeout（证据/检查/收尾）必要适配、`tests/rework/test_rework_evidence_recheck.py`、`tests/negative/test_rework_evidence_fail_closed.py`。
- 必须先写的 negative tests：ReworkAttempt 只产生 workspace mutation 但缺 command evidence/source lineage/provider attempt 必须失败；沿用首轮 FinalEvidenceTable satisfied row（已满足行）作为返工通过证据必须失败；Checker approved verdict（检查通过结论）早于返工 evidence verification（证据验证）必须失败；CloseoutGate 使用旧 RunManifest/SourceInventory（运行清单/源码清单）引用必须失败。
- 必须证明的 happy path：返工提交后重新构造 FinalEvidenceTable（最终证据表）和 SourceInventory（源码清单），Checker 生成新的 ProviderAttempt 与 CheckerVerdict，CloseoutGate 只消费新轮次证据。
- 验收口径：返工不是“补一条备注”；每轮都必须重验合同、源码、命令、行为探针和检查结论。
- 完成证据：2026-06-14 已实现 `src/boardroom_os/rework/evidence.py` 作为 ReworkAttempt（返工尝试）证据重验薄协调层；扩展 `src/boardroom_os/evidence/table.py` 支持可选 EvidenceNamespaceRef（证据命名空间引用），未命名空间 ID/JSON 保持兼容，返工轮次使用 `run_id + cycle_id + rework_attempt_id + graph_version` 命名空间；新增 `tests/rework/fixtures/rework_evidence.py`、`tests/negative/test_rework_evidence_fail_closed.py`、`tests/negative/test_rework_closeout_fail_closed.py`、`tests/rework/test_rework_evidence_recheck.py` 和 `tests/rework/test_rework_closeout_fact_chain.py`。负例证明缺 provider attempt（模型调用尝试记录）、缺 source lineage（源码来源链）、旧 FinalEvidenceTable（最终证据表）、过早 CheckerVerdict（检查结论）、遗漏 behavioral probe（行为探针）失败、缺 service contract（服务合同）、未声明 env usage（环境变量使用）和旧 RunManifest/SourceInventory/CheckerVerdict（运行清单/源码清单/检查结论）均 fail closed。正例证明当前轮可重建 SourceInventory（源码清单）、FinalEvidenceTable（最终证据表）、CheckerVerdict（检查结论）和 CloseoutGateResult（收尾门禁结果），ReworkOutcome.accepted_blocker_refs（返工结果已接受阻塞项引用）只来自 target_blocker_refs。验证：V2-100D focused tests `12 passed`；V2-100 regression `68 passed`；evidence/checker/source/run-manifest/closeout regression `141 passed`。

### V2-100E: Multi-round rework proving scenario（多轮返工证明场景）

- 状态：DONE
- 目标：用 090K 真实失败快照和一个可重置 failing fixture（失败夹具）构造首轮失败、CEO 自治返工、重验通过或明确升级的端到端证明，验证 agent team 流程能像人类团队一样沟通、返工和留痕。
- 输入文档：V2-100A~D、`docs/superpowers/specs/2026-06-12-v2-090k-agent-team-autonomy-remediation-design.md`、`docs/superpowers/plans/2026-06-12-v2-090k-agent-team-autonomy-remediation.md`、`examples/generated-workspaces/tiny-fullstack/30-audit/v2-090k-failure-snapshot/`、V2-090F/K 真实 run artifacts（运行产物）。
- 依赖：V2-100A、V2-100B、V2-100C、V2-100D；V2-090K 已完成并保留真实失败证据。
- 输出文件：`src/boardroom_os/proving/v2_100_rework_loop.py`、`src/boardroom_os/proving/v2_100_resettable_fixture.py`、`scripts/run_v2_100_rework_loop_scenario.py`、`tests/proving/fixtures/v2_100_resettable_rework.py`、`tests/proving/test_v2_100_rework_loop.py`、`tests/proving/test_v2_100_rework_loop_provider_integration.py`、`tests/negative/test_v2_100_rework_loop_fail_closed.py`、`doc/04-implementation/v2-100e-multi-round-rework-proving-scenario-expert-review-plan.md`，以及 ignored local audit export（本地忽略的审计导出）`examples/generated-workspaces/tiny-fullstack/20-evidence/v2-100e-rework-loop/`。
- 必须先写的 negative tests：命令通过但证明命题错误不得 closeout passed；无 blocker 创建返工必须失败；runner/helper 直接写 ReworkPlan 或 checker/closeout verdict 必须失败；只靠 `AgentRunResult.status == completed`、ProviderAttempt（模型调用尝试记录）、`--check` 或一次 live probe（真实探针）不得推出返工 accepted；无限返工或预算耗尽无 escalation（升级）必须失败。
- 必须证明的 happy path：先用 090K curated failure snapshot（精选失败快照）证明真实失败可被转为结构化 blocker，再用可重置 failing fixture（失败夹具）运行多轮返工：Checker/Closeout 生成结构化 blocker，CEO 产生 ReworkPlan 和 TicketGraphPatch，Worker/Tester/Release DevOps 执行返工，EvidenceVerifier/Checker/Closeout 重新验证，最终 accepted 或明确 escalated；ProcessAudit/ReplayBundle（流程审计/重放包）能展示完整多轮时间线和责任归属。
- 验收口径：V2-100 的通过标准不是“首次运行成功”，而是“局部产物不达标时，agent team 能自治识别、规划、返工、重验并可审计地收敛或升级”。
- 完成证据：2026-06-15 已实现 `src/boardroom_os/proving/v2_100_rework_loop.py`、`src/boardroom_os/proving/v2_100_resettable_fixture.py`、`scripts/run_v2_100_rework_loop_scenario.py`、`tests/proving/test_v2_100_rework_loop.py`、`tests/proving/test_v2_100_rework_loop_provider_integration.py`、`tests/negative/test_v2_100_rework_loop_fail_closed.py` 和 `tests/proving/fixtures/v2_100_resettable_rework.py`。负例覆盖无 verified blocker（已验证阻塞项）、fake provider success（模拟供应商成功）、helper-written verdict（辅助器写结论）、旧证据复用、重绑定预制 accepted evidence（通过证据）为真实 worker evidence（实施者证据）、命令成功但命题错误、runtime 直接 accepted（运行时直接接受）和预算耗尽无决策。正例证明 090K failure snapshot（失败快照）可投影为 ReworkRequest（返工请求），resettable fixture（可重置夹具）可经真实 provider-backed CEO/reviewer/worker（真实模型支撑项目经理/审查者/实施者）返工 accepted（接受）或预算耗尽显式终止，并导出 event/evidence/audit（事件/证据/审计）链。真实 CLI proof（命令行证明）在 `examples/generated-workspaces/tiny-fullstack/20-evidence/v2-100e-rework-loop` 导出审计，terminal_status=`accepted`、CloseoutGate（收尾门禁）`passed`，`real-provider-package` 的 PackageContract / RunManifest（包合同 / 运行清单）非空，SourceInventory hash（源码清单哈希）与实际文件 sha256 一致。验证：V2-100 focused regression `111 passed, 1 skipped, 1 warning`；evidence/checker/closeout regression `180 passed`；V2-100E local suite `42 passed, 1 skipped, 1 warning`；真实 provider opt-in suite `4 passed, 1 warning in 104.32s`；真实 CLI proof 通过；`git diff --check` 通过。

### V2-100F: RunManifest tolerant ingestion and rework entry（运行清单宽容摄取与返工入口）

- 状态：IN_PROGRESS（V2-100F-A、V2-100F-B、V2-100F-C、V2-100F-D 已完成；V2-100F-E/F 待实施）
- 目标：把 RunManifest behavior assertion（运行清单行为断言）从封闭枚举摄取改为宽容语义摄取，并把黑盒验证从框架执行 manifest steps（运行清单步骤）升级为原生编排路径：CEO 通过 TicketGraph / SeatDemand（工单图 / 席位需求）创建并派工 `verify-blackbox` ticket（黑盒验证工单），SeatAssignmentGraph（席位派工图）决定 AgentSeat（智能体席位），ExecutionPackage（执行包）携带 raw manifest context（原始运行清单上下文），ProviderAttempt（模型调用尝试记录）产出 BlackboxVerificationPlan（黑盒验证计划），runner（运行器）记录真实 facts（事实），EvidenceVerifier / Checker / CloseoutGate / ReworkReducer（证据验证器 / 检查者 / 收尾门禁 / 返工归约器）决定 `passed` / `rework_required` / `blocked_or_escalated`；LLM（大模型）产生的新断言词汇不得 raw crash（原始崩溃），也不得被框架解释为通过证据。
- 输入文档：`doc/04-implementation/v2-100f-manifest-tolerant-ingestion-rework-entry-spec.md`、`doc/04-implementation/v2-100f-manifest-tolerant-ingestion-rework-entry-implementation-plan.md`、`doc/04-implementation/v2-090f-rerun-rework-entry-validation-spec.md`、`doc/04-implementation/v2-090f-rerun-rework-entry-validation-implementation-plan.md`、V2-090F 真实 rerun artifacts（重跑产物）、V2-100A~E 返工能力产物。
- 依赖：V2-090F rerun rework-entry validation（重跑返工入口验证）真实结果为 `blocked_by_missing_rework_entry`；V2-100A~E DONE；V2-100F spec 已写入；旧 implementation plan（实施计划）因偏向外接 helper/hook（辅助器/钩子）路径已废弃，2026-06-21 重写为 V2-100F-A~F 分阶段 native orchestration plan（原生编排计划）。当前 A/B/C/D 已完成，E/F 待实施。
- 输出文件：当前新增 spec 与重写计划：`doc/04-implementation/v2-100f-manifest-tolerant-ingestion-rework-entry-spec.md`、`doc/04-implementation/v2-100f-manifest-tolerant-ingestion-rework-entry-implementation-plan.md`；V2-100F-A/B 已新增 `src/boardroom_os/workspace/run_manifest_ingestion.py`、`src/boardroom_os/orchestration/verification.py`、`tests/workspace/test_run_manifest_tolerant_ingestion.py`、`tests/negative/test_manifest_tolerant_ingestion_fail_closed.py`、`tests/orchestration/test_verify_blackbox_native_ticket.py` 和 `tests/negative/test_verify_blackbox_orchestration_fail_closed.py`；V2-100F-C 已新增 `src/boardroom_os/evidence/blackbox_plan.py`、`tests/evidence/test_blackbox_verification_plan.py`、`tests/negative/test_blackbox_plan_fail_closed.py`，并导出 `src/boardroom_os/evidence/__init__.py`；V2-100F-D 已新增 `src/boardroom_os/execution/blackbox_plan_runner.py`、`tests/execution/test_blackbox_plan_runner.py`、`tests/negative/test_blackbox_plan_runner_fail_closed.py`，并通过 `src/boardroom_os/execution/__init__.py` 懒加载导出。V2-100F-E/F 仍待实施。
- 必须先写的 negative tests：未知 assertion type（断言类型）不得 raw crash；未知 assertion 不得被忽略；未知 assertion 不得 closeout passed（收尾通过）；`verify-blackbox` 不得绕过 TicketGraphProjector / SeatAssignmentProjector / ExecutionPackageCompiler（工单图投影器 / 席位派工投影器 / 执行包编译器）直接进入 ready queue 或指定固定 Tester；V2-100F active path（活跃路径）不得调用 `run_v2_100_rework_loop_for_request`、依赖 V2-100E resettable fixture（可重置夹具）或读取 `v2-090k-failure-snapshot`（V2-090K 历史失败快照）；缺被派工 AgentSeat（智能体席位）的 ProviderAttempt（模型调用尝试记录）不得生成有效 BlackboxVerificationPlan；runner（运行器）不得在缺 agent plan（智能体计划）时自造测试动作；runner 不得执行计划外动作；缺 HTTP/browser/tool executor（HTTP / 浏览器 / 工具执行器）必须 `blocked_or_escalated`，不得伪装为 `rework_required`；agent prose（智能体散文）、advisory labels（参考标签）或 interpretation summary（解释摘要）不得被改写为 `passed`（通过）；新代码和新产物不得继续使用 `RUN_MANIFEST_MISMATCH` 作为 active routing code（活跃路由代码）；stub / `assert True` / `changed_files: []` 不得满足 worker evidence（实施者证据）。
- 必须证明的 happy path：provider（模型供应商）产生 novel assertion vocabulary（新断言词汇）时，RunManifest 可摄取并保留 raw assertion（原始断言）；CEO provider output（项目经理模型输出）创建 `verify-blackbox` ticket（黑盒验证工单）并由真实 TicketGraph reducer/projection（工单图归约器/投影）消费进入 ready queue（就绪队列）；SeatAssignmentGraph（席位派工图）为该工单匹配 active AgentSeat（活跃智能体席位）；raw manifest、PackageContract、AcceptanceContract、项目文档、源码引用和既有失败上下文进入 graph-assigned AgentSeat（工单图派工席位）的 ExecutionPackage（执行包）；被派工 AgentSeat 生成 provider-backed BlackboxVerificationPlan；runner 执行该计划并记录 command / HTTP / browser / tool facts（命令 / HTTP / 浏览器 / 工具事实）或 typed `blocked_or_escalated` reason（类型化阻断/升级原因）；Checker / Closeout / ReworkReducer（检查 / 收尾 / 返工归约器）基于真实事实给出 `passed`、`rework_required` 或 `blocked_or_escalated`。
- 验收口径：V2-100F 的目标不是放宽通过门槛，而是把 raw exception（原始异常）转换为 agent-owned verification（智能体拥有的验证）和可返工事实。RunManifest 是上下文和运行承诺，不是唯一测试脚本；框架不能替 CEO/被派工 AgentSeat（项目经理/智能体席位）决定黑盒测试语义，也不能从 raw text（原始文本）自动判定 `MANIFEST` suspected domain（运行清单疑似域）。
- 当前证据：2026-06-16 真实 V2-090F rerun 在 RunManifest assertion normalization（运行清单断言归一化）阶段因 `json_array_contains_field` raw crash，导出 `blocked_by_missing_rework_entry`；样例工程后端 CRUD 和本地测试可运行，但 RunManifest 与实现存在 readiness path（就绪路径）和 response shape（响应结构）等真实 drift（漂移）。2026-06-21 已丢弃偏外接 helper/hook（辅助器/钩子）的旧 plan，重写为 V2-100F-A~F。V2-100F-A 已完成宽容摄取上下文；V2-100F-B 已证明 `verify-blackbox` 通过 `TICKET_CREATED -> SEAT_ASSIGNED -> SeatAssignmentGraph.ready_queue -> ExecutionPackageCompiler` 原生链路进入执行包，缺 seat / context / queue membership 均 fail closed；review 修补后，`VerificationExecutionContext`（验证执行上下文）派生的全部 refs 必须属于 ticket `allowed_read_refs` 子集，且 `verify-blackbox` ticket 必须声明 `RoleCategory.VERIFICATION` 与 `task.verify-blackbox` capability（能力标签），空写集仍为唯一允许形态。V2-100F-C 已完成 provider-backed `BlackboxVerificationPlan`（模型支撑黑盒验证计划）schema（结构）、`BlackboxPlanApproval`（黑盒计划批准）动作门禁与 lineage validator（来源链校验器），缺 ProviderAttempt、错 seat、fallback attempt、stale package、stale hook、越界 acceptance/context/action ref、计划外 approved action 或计划内成功声明均 fail closed。V2-100F-D 已完成 `BlackboxPlanRunner`（黑盒计划运行器）和 `BlackboxActionExecutionFact`（黑盒动作执行事实）：runner 只执行 approved plan actions（已批准计划动作），command action 通过现有 `CommandRunner` 记录 `VerificationRun` 来源链，HTTP/browser/tool/file_read 缺显式 executor 时返回 typed `blocked_or_escalated`，且 runner 输出只包含 facts，不创建 ReworkRequest、不标记 evidence passed 或 closeout candidate。V2-100F-E/F 尚未实施，未改变 V2-090F BLOCKED 状态，未勾选 AC-V2-REWORK-006。

---

## 非阶段技术债 / Chore backlog

### CHORE-REF-001: 提取 ref normalization 公共 helper

- 状态：TODO
- 目标：将 `_normalize_ref_fields` 从 `boardroom_os.agents.skills` 私有 helper 提取为公共引用归一化工具，避免 agents / execution / contracts 之间依赖私有实现。
- 输入文档：当前代码使用点。
- 依赖：V2-030C。
- 输出文件：待定，建议 `src/boardroom_os/common/refs.py` 或 `src/boardroom_os/contracts/types.py`。
- 必须先写的 negative tests：迁移后现有 YAML-shaped ref strings（YAML 形状引用字符串）归一化行为不得回退。
- 必须证明的 happy path：`agents.profiles`、`agents.seat`、`execution.package` 均改用公共 helper 且相关测试通过。
- 验收口径：不再从非 agents 模块引用 `boardroom_os.agents.skills._normalize_ref_fields`。
