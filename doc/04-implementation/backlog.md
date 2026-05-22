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

**当前未完成工作包**：`V2-060A`

**当前重点**：Phase 6 Workspace + Package（工作区与项目包）启动；当前重点转为 V2-060A workspace manifest（工作区清单），表达 generated project workspace（生成项目工作区）的逻辑结构，并防止把 `00-boardroom` / `10-project` / `20-evidence` / `30-audit` 误作框架源码布局。

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
| Phase 0：Foundation | V2-000, V2-001 | 4 / 4 | 完成 |
| Phase 1：Contract Kernel | V2-010 | 7 / 7 | 完成 |
| Phase 2：Event + Reducer Kernel | V2-020 | 6 / 6 | 完成 |
| Phase 3：Agent + Execution Package | V2-030 | 6 / 6 | 完成 |
| Phase 4：Runtime + Provider + Runner | V2-040 | 5 / 5 | 完成 |
| Phase 5：Evidence + Checker | V2-050 | 7 / 7 | 完成 |
| Phase 6：Workspace + Package | V2-060 | 0 / 6 | 待开始 |
| Phase 7：Closeout + Replay + Audit | V2-070 | 0 / 6 | 待开始 |
| Phase 8：Tiny proving scenario | V2-080 | 0 / 6 | 待开始 |
| **合计** | **V2-000 ~ V2-080** | **35 / 53** | **Phase 6 待启动** |

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

- 状态：TODO
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
- 完成证据：2026-05-17 新增 AgentTeamProjector（智能体团队投影器）作为 role profile change facts（角色模板变更事实）与 seat lifecycle facts（席位生命周期事实）的单一 graph_version 编排入口，并新增 ExecutionPackageCompiler（执行包编译器）从 ready ticket（就绪任务）、active AcceptanceContract（活跃验收合同）、PackageContract（包合同）、ExecutionWorkspaceContext（执行工作区上下文）、SeatAssignmentGraph（席位分配图）和 AgentTeamProjection（智能体团队投影）编译 ExecutionPackage（执行包）。负例覆盖 graph_version mismatch、缺 bootstrap/重复 bootstrap、role/seat payload 缺口、缺派工、inactive/unknown seat、capability mismatch、inactive contract、acceptance/source/evidence/command/model/role 缺口、unsafe write path 和 evidence_required 不匹配；正例证明 backend worker ticket 可编译出含 commands、context_refs、allowed_write_set、evidence_obligations、fallback_policy_ref 的 ExecutionPackage。验证命令：`PYTHONPATH="src;." pytest tests/negative/test_agent_team_projector_fail_closed.py tests/execution/test_agent_team_projector.py tests/negative/test_execution_package_compiler_fail_closed.py tests/execution/test_execution_package_compiler.py -q` 通过（44 passed）；`PYTHONPATH="src;." pytest tests/execution/test_execution_package_schema.py tests/execution/test_agent_profiles.py tests/execution/test_agent_seat_policy.py tests/reducers/test_seat_assignment_projection.py tests/reducers/test_projection_replay.py -q` 通过（71 passed）；`PYTHONPATH="src;." pytest tests/contracts tests/reducers tests/execution tests/negative -q` 通过（325 passed）。

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
- 完成证据：2026-05-18 新增 ProviderAttempt（模型调用尝试记录）、ProviderAttemptStatus（模型调用状态）、ProviderAttemptOutcome（模型调用结果）、ProviderArtifactRef（模型产物引用）、ProviderAdapter（模型供应商适配器）、ProviderRequest（模型供应商请求）、ProviderResponse（模型供应商响应）和 FakeProviderTransport（模拟传输）；负例证明缺 provider / model / reasoning_effort / input_package_ref / seat_ref / status / outcome、无时区时间戳、finished_at 早于 started_at、成功 attempt 缺 raw/parsed output ref、成功 attempt 携带 failure_kind、失败 attempt 缺 failure_kind、unknown extra fields、fallback outcome 缺 typed fallback_kind、primary outcome 携带 fallback_kind 均 fail closed；正例证明 fake provider transport 可由 ProviderRequest 生成 succeeded ProviderAttempt，并绑定 ExecutionPackageRef（执行包引用）、AgentSeatRef（智能体席位引用）、raw output ref、parsed output ref 与 primary/non-fallback outcome。验证命令：先运行 `PYTHONPATH=src pytest tests/execution/test_provider_attempt.py -q` 得到预期 RED（缺 provider 模块 / 缺 ProviderAttemptOutcome）；实现后 `PYTHONPATH=src pytest tests/execution/test_provider_attempt.py -q` 通过（24 passed）；`PYTHONPATH="src;." pytest tests/execution -q` 通过（124 passed）。

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

- 状态：TODO
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
- 必须证明的 happy path：所有 blocking criteria 都有 verified_evidence_refs 时 table complete。
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

- 状态：TODO
- 目标：生成目标项目 workspace、run manifest、package contract 文件、source inventory、agent asset import manifest 和最终 package assembly。
- 输入文档：`generated-project-workspace.md`、`contract-and-evidence-model.md`。
- 输出目录：`src/boardroom_os/workspace/`、`tests/proving/`、`tests/negative/`。
- 顶层验收口径：source inventory 来自 package root + git/hash，不来自 payload 猜测；最终产物是 generated project package；外部 agent assets（智能体资产）只能在 package workspace 阶段导入为 `00-boardroom/agents/` 快照。
- V2-060 Workspace（工作区）必须消费 V2-010F 产出的 `docs_template_key`（文档模板键）与 `documentation_obligations`（文档义务），不得在 assembler（装配器）中重新解释 methodology（方法论）。
- ExecutionPackage compiler（执行包编译器）必须保持可在 0 外部文件输入下运行：它只消费已编译 registry / contract / graph / seat assignment，不负责同步外部 skill、prompt 或 MCP 资产。

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

### V2-060F: 导入 agent asset bundle

- 状态：TODO
- 目标：把外部预置的 role config、skill file、prompt file 和 MCP interface manifest 导入为 generated project workspace 内的 `00-boardroom/agents/` 快照，并记录来源链。
- 输入文档：`generated-project-workspace.md`、`agent-team-model.md`、`process-audit-and-replay.md`。
- 依赖：V2-060A、V2-030A。
- 输出文件：`src/boardroom_os/workspace/agent_asset_import.py`、`tests/proving/test_agent_asset_import.py`。
- 必须先写的 negative tests：导入目标写到 `00-boardroom/agents/` 外、缺 `asset-import-manifest.yaml`、manifest 缺 source_ref/source_kind/imported_at、导入项缺 source_path/target_path/sha256、静默覆盖已有不同 hash 资产必须失败。
- 必须证明的 happy path：本地 agent asset bundle 可被复制/物化为 `00-boardroom/agents/` 快照，生成 `asset-import-manifest.yaml`，并保留 role/skill/prompt/MCP 文件的 source lineage（来源链）。
- 验收口径：外部 skill/prompt/MCP 资产是 workspace/package 阶段的可审计输入，不是 ExecutionPackage compiler 的运行时外部依赖；既有项目更新资产必须产生新 ref 或显式导入记录，不能静默改写。

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
- 输入文档：`process-audit-and-replay.md`、`decisions.md`（DEC-0011）。
- 依赖：V2-020F、V2-060E。
- 输出文件：`src/boardroom_os/audit/replay_bundle.py`、`tests/closeout/test_replay_bundle.py`。
- 必须先写的 negative tests：event range 缺失、projection version 不匹配、artifact hash 缺失、event log hash chain / hash manifest 缺失、replay report 缺失必须失败。
- 必须证明的 happy path：事件 + artifact manifest + hash manifest 可重建 typed summary，并证明 replay 输入未被静默篡改。
- 验收口径：缺 replay bundle 不允许 terminal success；hash chain / hash manifest 在 replay bundle 层处理，不回填到 Phase 2 的 InMemoryEventLog 最小接口。

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
  - fallback artifact 缺 `fallback decision -> verifier -> evidence map -> closeout` lineage 必须失败
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
- 输入文档：`execution-and-runtime-boundary.md`、`process-audit-and-replay.md`、`decisions.md`（DEC-0011）。
- 依赖：V2-070E、V2-020D。
- 输出文件：`src/boardroom_os/reducers/closeout_reducer.py`、`tests/closeout/test_closeout_reducer.py`。
- 必须先写的 negative tests：runtime 直接 closeout、workflow completed 但 closeout gate missing、缺 replay bundle、增量 reducer/replay 输入缺历史 `WORK_PRODUCT_SUBMITTED` 事实必须失败。
- 必须证明的 happy path：CloseoutPackage passed 事件可投影为 project terminal success；若采用 base projection + new events（基准投影 + 新事件）增量模式，work product 历史必须作为显式 projection/replay 输入保留。
- 验收口径：不把 workflow completed 当作项目完成；closeout reducer 不能依赖 `TicketReducer.reduce()` 调用内局部集合来推断历史 work product。

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
