# V2-090 Tiny Fullstack 黑盒整改计划

## 文档职责

本文承接 2026-05-31 tiny-fullstack 失败复审，将 V2-080 从“最小端到端能力成立”撤回为“失败复审后结束”，并定义 V2-090 的整改批次。

V2-090 的目标不是继续修补一个 golden sample（黄金样例），而是把 proving scenario（证明场景）改成真实黑盒闭环：声明什么命令，就必须运行或 probe（探测）什么命令；声明 HTTP integration（HTTP 集成），就必须启动服务并用真实 HTTP 验证；声明 closeout（收尾），就必须证明最终 generated project package（生成项目包）可启动、可测试、可审计。

## 复审结论

两份复审材料：

- `boardroom-os-tiny-fullstack-audit-20260531.md`
- `boardroom-os-tiny-fullstack-gptpro-review.md`

共同结论是：V2-080 已经避免了旧 runtime（运行时）直接伪造 source（源码）和 verification（验证）的失败模式，但进入了更隐蔽的伪闭环。

```text
ProviderAttempt（模型调用尝试记录）真实存在；
pytest command（测试命令）真实执行；
SourceInventory（源码清单）、FinalEvidenceTable（最终证据表）、CloseoutPackage（收尾包）和 ProcessAuditBundle（流程审计包）真实生成；
但这些证据证明的是错误命题。
```

V2-080 的证据链证明了“后端函数库可被测试直接调用、前端函数会调用 fakeFetch（模拟 fetch）、run manifest（运行清单）文件存在、引用和哈希可绑定”，没有证明“generated package（生成包）按 run manifest 可启动、backend/frontend（后端/前端）真实串联、SQLite（SQLite 数据库）经 HTTP 工作流持久化”。

因此，V2-080A~F 保留 `DONE` 作为历史工作包执行记录，但 Phase 8 不再作为 V2 minimal end-to-end（最小端到端）成立依据。

## 根因判断

### 1. RolePrompt（角色提示词）约束缺失

在自治服务中，CEO（首席治理者）、Architect（架构师）、Worker（实施者）、Tester（测试者）、Checker（检查者）和 Closeout（收尾者）不会收到外部逐步人工指导；它们只能从最初简短 PRD（产品需求文档）和上游产物派生工作。

V2-080 暴露的问题是：Architect（架构师）在缺少基础提示词边界的情况下，给出了过浅的 architecture contract（架构合同）和 implementation plan（实施方案），没有把 run command（运行命令）、service boundary（服务边界）、HTTP route（HTTP 路由）、SQLite persistence（SQLite 持久化）和 live integration evidence（真实集成证据）编译成强约束。后续 Worker / Tester / Checker 只能沿着这个浅层合同继续生产结构正确但命题错误的证据。

### 2. Contract（合同）内部自相矛盾

V2-080 的 package contract（包合同）声明 `run-backend = python -m uvicorn backend.app:app`，但 provider prompt（模型提示词）又禁止第三方框架并要求标准库函数式 backend（后端）。这导致 Worker（实施者）生成了符合 prompt 的函数库，却无法满足 run manifest（运行清单）的 ASGI（异步服务网关接口）启动命令。

### 3. Evidence（证据）覆盖了引用，不覆盖行为命题

CloseoutGate（收尾门禁）只校验已有 VerificationRun（验证运行）与 run manifest binding（运行清单绑定）的引用一致性，没有要求 run manifest 中每个 command（命令）都有 final evidence（最终证据）。`run-backend` 和 `run-frontend` 从未启动，但 closeout 仍然 passed（通过）。

### 4. Integration（集成）证据被 fakeFetch 代替

前端集成测试只验证 fakeFetch（模拟 fetch）捕获 `/books` 路径，不启动 backend service（后端服务）或 frontend service（前端服务），也不经 HTTP 验证 SQLite 写入。

### 5. Audit（审计）产物证明了错误链路

ProcessAuditBundle（流程审计包）、SourceInventory（源码清单）和 FinalEvidenceTable（最终证据表）能证明已有 refs（引用）、hashes（哈希）和 artifacts（产物）结构一致，但不能自动证明上游 acceptance claim（验收命题）正确。

## 整改原则

1. RolePromptHook（角色提示词钩子）先行，但不得替代 schema（模式）、reducer（归约器）、validator（校验器）或 CloseoutGate（收尾门禁）。
2. 每个角色基础提示词必须版本化，并进入 RoleProfile（角色模板）、ExecutionPackage（执行包）和 ProviderAttempt（模型调用尝试记录）的审计链。
3. Contract-first（合同优先）必须扩展到 service boundary（服务边界）和 command coverage（命令覆盖）：合同声明的命令必须有对应证据义务。
4. Evidence-first（证据优先）必须验证行为命题，而不只是引用闭包。
5. Fail closed（失败关闭）：缺任一 declared run/test command evidence（声明运行/测试命令证据）、service readiness（服务就绪证据）、live integration evidence（真实集成证据）或 source inventory lineage（源码清单来源链）均不能 closeout passed（收尾通过）。
6. Golden sample（黄金样例）只有在黑盒证据齐全后才能重建为成功样例；当前样例降级为 regression negative fixture（回归负例素材）。

## V2-090 工作包总览

| 工作包 | 状态 | 目标 |
|---|---|---|
| V2-090A RolePromptHook | TODO | 定义角色基础提示词 hook，并纳入可审计执行链 |
| V2-090B Closeout all-command coverage | TODO | CloseoutGate 要求 RunManifest 中每个 command 均有最终证据 |
| V2-090C ServiceRunEvidence | TODO | 区分一次性 command evidence 与长运行 service startup/readiness evidence |
| V2-090D Tiny contract recovery | TODO | 修正 tiny-fullstack contract 与 provider prompt 路线矛盾 |
| V2-090E Live blackbox integration | TODO | 启动真实 backend/frontend 并通过 HTTP 验证 CRUD、SQLite 和前端调用 |
| V2-090F Golden sample rebuild | TODO | 重建 golden sample，只有黑盒证据齐全时 closeout passed |

## V2-090A: RolePromptHook

- 状态：TODO
- 目标：为 CEO / Architect / Worker / Tester / Checker / Closeout 定义基础提示词职责边界，并把 RolePromptHook（角色提示词钩子）作为 governed asset（治理资产）进入审计链。
- 输入文档：`domain-model.md`、`contract-and-evidence-model.md`、`execution-and-runtime-boundary.md`、`agent-team-model.md`、两份 2026-05-31 tiny-fullstack 复审报告。
- 依赖：V2-030A RoleProfile（角色模板）、V2-030C ExecutionPackage（执行包）、V2-040A ProviderAttempt（模型调用尝试记录）。
- 输出文件：`src/boardroom_os/agents/role_prompt_hooks.py`、`tests/execution/test_role_prompt_hooks.py`、必要时更新 `doc/03-architecture/agent-team-model.md`。
- 必须先写的 negative tests：
  - RoleProfile（角色模板）缺 role prompt hook version（角色提示词钩子版本）不得编译 ExecutionPackage（执行包）。
  - ProviderAttempt（模型调用尝试记录）缺 role prompt hook ref（角色提示词钩子引用）不得作为 implementation evidence（实施证据）。
  - Prompt hook（提示词钩子）不能声明自己绕过 AcceptanceContract（验收合同）、PackageContract（包合同）、EvidenceVerifier（证据验证器）或 CloseoutGate（收尾门禁）。
  - Architect（架构师）提示词缺“run command 与 service boundary 一致性检查”职责时，tiny contract compilation（微型合同编译）必须失败。
- 必须证明的 happy path：
  - CEO（首席治理者）提示词约束需求澄清、范围、非目标和验收命题。
  - Architect（架构师）提示词约束合同编译、run/test command、service boundary、integration boundary 和 evidence obligations（一致证据义务）。
  - Worker（实施者）提示词约束只在 allowed write set（允许写入集合）内实现，不用 fallback（降级）满足 implementation evidence。
  - Tester（测试者）提示词约束 negative tests first（负例优先）、blackbox service probe（黑盒服务探针）和 live integration（真实集成）。
  - Checker（检查者）提示词约束不得用 notes（备注）清除 blocker（阻断项）。
  - Closeout（收尾者）提示词约束 workflow completed（工作流完成）不能替代 CloseoutPackage（收尾包）和 `CLOSEOUT_COMMITTED`（收尾已提交）。
- 验收口径：角色基础提示词已版本化、可引用、可审计；ExecutionPackage 与 ProviderAttempt 均能追踪本次调用使用的 role prompt hook；提示词仅约束 agent 行为，不替代程序化门禁。

## V2-090B: Closeout all-command coverage

- 状态：TODO
- 目标：CloseoutGate（收尾门禁）必须要求 RunManifest（运行清单）中的每个 run/test command（运行/测试命令）都有最终证据。
- 输入文档：`contract-and-evidence-model.md`、`process-audit-and-replay.md`、两份复审报告。
- 依赖：V2-090A、V2-060D、V2-070A。
- 输出文件：`src/boardroom_os/closeout/gate.py`、`tests/negative/test_run_manifest_command_coverage.py`。
- 必须先写的 negative tests：当前 V2-080 附件包缺 `run-backend` / `run-frontend` evidence 时必须被 CloseoutGate blocked（阻断），blocker 包含 `RUN_MANIFEST_COMMAND_UNVERIFIED` 或等价机器可读 reason（原因）。
- 必须证明的 happy path：run/test commands（运行/测试命令）全部有 final evidence 后 CloseoutGate 才可 passed（通过）。
- 验收口径：已有 verification runs（验证运行）不能代表未运行的 manifest commands（清单命令）。

## V2-090C: ServiceRunEvidence

- 状态：TODO
- 目标：引入 ServiceRunEvidence（服务运行证据）或等价类型，区分长运行服务的 startup/readiness probe（启动/就绪探针）与一次性 test command（测试命令）。
- 输入文档：`execution-and-runtime-boundary.md`、`contract-and-evidence-model.md`。
- 依赖：V2-090B、V2-040D。
- 输出文件：`src/boardroom_os/evidence/service_run.py`、`src/boardroom_os/adapters/process_runner.py`、相关 negative tests。
- 必须先写的 negative tests：service command（服务命令）只产生 process id（进程 ID）但无 readiness probe（就绪探针）不得满足 evidence；服务启动后立即退出不得满足 readiness；probe（探针）命中错误端口或错误 path（路径）必须失败。
- 必须证明的 happy path：backend/frontend service（后端/前端服务）启动后，健康检查和内容探针均通过，并记录 stdout/stderr refs（标准输出/错误引用）、started_at/finished_at（开始/结束时间）、port（端口）和 readiness URL（就绪地址）。
- 验收口径：长运行服务不再伪装成普通 passed pytest command（通过测试命令）。

## V2-090D: Tiny contract recovery

- 状态：TODO
- 目标：修正 tiny-fullstack 合同路线。推荐采用标准库 HTTP（`http.server`）路线，避免 `uvicorn`（ASGI 服务器）依赖与“标准库 only”提示词冲突。
- 输入文档：`proving-scenario-tiny-fullstack.md`、两份复审报告。
- 依赖：V2-090A、V2-090C。
- 输出文件：`tests/fixtures/contracts/tiny_fullstack_contract.py`、`tests/proving/fixtures/tiny_provider_attempts.py`、相关 contract negative tests。
- 必须先写的 negative tests：合同声明 `uvicorn backend.app:app` 但 provider prompt 禁止第三方依赖时必须 fail closed；acceptance 只写“fetch backend API”但不要求 live HTTP integration（真实 HTTP 集成）时不得进入 closeout-ready（可收尾）。
- 必须证明的 happy path：PackageContract（包合同）中的 run commands（运行命令）、source surfaces（源码实现面）、integration boundaries（集成边界）和 evidence obligations（证据义务）一致，并要求 backend HTTP endpoints（后端 HTTP 端点）、frontend service（前端服务）、SQLite persistence（SQLite 持久化）和 live integration evidence（真实集成证据）。
- 验收口径：tiny-fullstack 不再同时保留互斥路线。

## V2-090E: Live blackbox integration

- 状态：TODO
- 目标：真实启动 generated package（生成包）的 backend/frontend（后端/前端），通过 HTTP 验证 CRUD、SQLite persistence（SQLite 持久化）和前端调用后端。
- 输入文档：V2-090D 修正后的 tiny contract（微型合同）、`execution-and-runtime-boundary.md`。
- 依赖：V2-090C、V2-090D。
- 输出文件：`tests/proving/fixtures/tiny_package_assembly.py`、`tests/proving/test_tiny_package_assembly.py`、`tests/proving/test_tiny_live_blackbox_integration.py`。
- 必须先写的 negative tests：fakeFetch-only（仅模拟 fetch）集成不得满足 full-stack acceptance（全栈验收）；backend HTTP endpoint（后端 HTTP 端点）缺 delete / checkout / return 任一操作不得 satisfied（满足）；SQLite 只在函数单测中落盘不得满足 HTTP persistence evidence（HTTP 持久化证据）。
- 必须证明的 happy path：backend startup probe（后端启动探针）、backend HTTP CRUD probe（后端 HTTP CRUD 探针）、SQLite file/schema/data probe（SQLite 文件/模式/数据探针）、frontend startup probe（前端启动探针）和 live frontend-backend probe（真实前后端探针）均通过。
- 验收口径：集成证据必须来自运行中的服务，不来自 mock（模拟）或源码字符串检查。

## V2-090F: Golden sample rebuild

- 状态：TODO
- 目标：重建 `examples/generated-workspaces/tiny-fullstack/`，只有所有黑盒证据齐全时生成 CloseoutPackage（收尾包）passed。
- 输入文档：V2-090A~E 产物。
- 依赖：V2-090E。
- 输出文件：`examples/generated-workspaces/tiny-fullstack/`、`scripts/build_tiny_closeout_sample.py`、`examples/README.md`、`scripts/README.md`。
- 必须先写的 negative tests：当前 V2-080 failure package（失败包）必须作为 regression negative（回归负例）被 closeout gate 阻断；缺任一 `RunManifest.commands[*]` evidence（运行清单命令证据）不得生成 passed sample（通过样例）；golden sample 不得包含未登记的 `__pycache__` 或临时文件。
- 必须证明的 happy path：样例可在 clean worktree（干净工作树）重生成；连续两次 hash（哈希）稳定；文件数量固定；总大小在上限内；`--check` 只比较不写文件；CloseoutPackage、ReplayBundle（重放包）、GitVersionAuditBundle（Git 版本审计包）和 ProcessAuditBundle（流程审计包）都绑定黑盒证据。
- 验收口径：golden sample 不再只是 deterministic fixture（确定性夹具），而是 blackbox-evidence-backed sample（黑盒证据支持样例）。

## Completion Protocol

V2-090 完成前不得恢复“V2 最小端到端能力成立”的结论。每个工作包完成时按 `backlog.md` 的工作包完成更新协议同步：

1. `doc/04-implementation/backlog.md`
2. `doc/04-implementation/acceptance-criteria.md`
3. `doc/05-project-log/YYYY-MM.md`
4. 必要时 `doc/05-project-log/decisions.md`
5. 必要时 `doc/04-implementation/INDEX.md`

当前文档阶段只建立 V2-090 批次和 V2-090A 入口，不修改源码、测试、生成样例或运行时产物。
