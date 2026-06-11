# V2-090F PRD-to-Delivery Agent Team Golden Sample 设计规格

## 结论

V2-090F（Golden sample rebuild，黄金样例重建）的目标不是验证一个预拆好的 backend/frontend/integration 三段流水线，而是验证：

```text
short PRD（简短产品需求） -> agent team（智能体团队）自治规划、实施、测试、修复、收尾 -> passed golden sample（通过黄金样例）
```

Boardroom OS（董事会系统）在本阶段只能提供入口脚本、配置基线、证据门禁、运行边界和验收门禁；不得在 runner（运行器）里预先替 agent team 拆 implementation tickets（实施任务）、指定 backend/frontend/integration 执行顺序，或把人工脚手架当作自治能力。

本规格只修订 V2-090F 的设计入口，不实施代码。实施必须等待本规格和配套 plan（实施计划）通过人工评审。

## 背景

V2-090G/H/I/J 已证明：

- Boardroom OS 能通过 package/import（包导入）接入外部 `atomic-agent`（原子智能体）。
- `AtomicAgentExecutor`（原子智能体执行器）能让 implementation ticket 在真实 provider-backed agent loop（模型供应商支撑智能体循环）中读写 workspace（工作区）、运行命令、提交 result（结果），并产生 event stream（事件流）、workspace mutation（工作区变更）、command evidence（命令证据）、provider turn facts（模型轮次事实）和 source lineage input（源码来源链输入）。
- V2-090J 已修复 action protocol（动作协议）、tool policy（工具策略）和 required-output checkpoint（必需产物检查点）。

但这些只证明 worker-level implementation（工人级实施）可行。V2-090F 必须继续证明 agent team-level autonomy（智能体团队级自治）：CEO / Architect / Worker / Tester / Checker / Closeout（决策、架构、实施、测试、检查、收尾）是否能从短 PRD 自治地产生合同、任务图、实现、测试、证据和 closeout package（收尾包）。

## 腐化边界

以下旧口径必须废弃：

1. provider artifact lock（模型产物锁）或单次 JSON source delivery（源码交付）不能作为 implementation evidence（实施证据）。
2. `scripts/build_tiny_closeout_sample.py --check`（构建脚本检查模式）不能单独证明端到端成立。
3. `AgentRunResult.status == completed`（智能体运行完成）不能直接映射为 `TICKET_COMPLETED`（任务完成）或 `CloseoutPackage.passed`（收尾包通过）。
4. 预先固定三个 implementation tickets 并由 runner 逐票监督执行，不能证明 agent team autonomy。
5. 所有角色共用 `seat.worker.implementation`（工人实施席位）不能证明 RolePromptHook（角色提示词钩子）、RoleProfile（角色模板）和 skill context（技能上下文）按角色加载。

## 目标

V2-090F 新入口必须接受一个简短 PRD，例如：

```text
Build a tiny library checkout web app. Users can add books, list books,
checkout and return a book, delete a book, and see the UI update from a
real backend. Persist data in SQLite. Use standard-library Python backend
and static frontend. Provide tests and run instructions.
```

入口脚本建议为：

```bash
PYTHONPATH=src:. python scripts/run_v2_090f_prd_agent_team.py --prd examples/directives/tiny-fullstack-prd.md --reset
```

成功后发布：

```text
examples/generated-workspaces/tiny-fullstack/
  00-boardroom/
  10-project/
  20-evidence/
  30-audit/
  closeout-package.json
  replay-bundle.json
  git-version-audit-bundle.json
  sample-manifest.json
```

其中：

- `00-boardroom/` 记录 agent team run（智能体团队运行）的 PRD、配置基线、角色上下文快照、自治生成的合同与任务图。
- `10-project/` 是 agent team 自治产生的交付项目。
- `20-evidence/` 记录 source inventory（源码清单）、run manifest（运行清单）、verification runs（验证运行）、service run evidence（服务运行证据）、live blackbox evidence（真实黑盒证据）和 final evidence table（最终证据表）。
- `30-audit/` 记录 process/replay/git/config/role-context audit（流程/重放/Git/配置/角色上下文审计）。

## Agent Team 自治边界

V2-090F 必须让 agent team 自治地产生：

- `BoardDirective`（董事会指令）或等价 PRD intake（需求摄入）产物；
- `AcceptanceContract`（验收合同）；
- `PackageContract`（包合同）；
- `TicketGraph`（任务图）；
- implementation tickets（实施任务）；
- verification plan（验证计划）；
- checker verdict（检查结论）；
- closeout evidence map（收尾证据映射）。

外部 runner 可以声明 hard acceptance probes（硬验收探针），例如最终必须真实启动 backend/frontend、通过 HTTP CRUD、SQLite persistence（SQLite 持久化）和 frontend-to-backend live probe（真实前后端探针）。但 runner 不得预先规定 agent team 必须拆成几张票、每张票的名称、执行顺序或源码文件布局。

## 多角色上下文基线

090F 必须冻结并验证 agent team role-context baseline（智能体团队角色上下文基线）。允许多个角色使用同一 provider/model（模型供应商/模型），但不允许所有角色共用同一个 worker seat（工人席位）。

必需角色席位：

| Seat（席位） | 责任 | 写权限基线 |
|---|---|---|
| `seat.ceo.delivery` | PRD intake、目标裁剪、交付授权 | 不写 implementation source（实施源码） |
| `seat.architect.delivery` | 合同、任务图、边界设计 | 不写 implementation source |
| `seat.worker.implementation` | 写源码、运行命令、修复失败 | 可写 allowed implementation paths（允许实施路径） |
| `seat.tester.integration` | 验证计划、测试命令、黑盒探针设计 | 可写测试/验证资产，不写业务源码，除非合同授权 |
| `seat.checker.acceptance` | 读取 evidence/package 并判断合同满足情况 | 不写 implementation source |
| `seat.closeout.package` | 读取证据并整理 closeout/audit artifacts（收尾/审计产物） | 可写 closeout/audit artifacts，不写 implementation source |

每个 seat 必须绑定：

- 独立 `role_profile_ref`；
- 与 role category（角色类别）匹配的 `RolePromptHook`；
- 审计可见的 hook ref/version/sha256；
- 与角色相符的 `skill_refs`；
- 与角色相符的 tools（工具）和 permissions（权限）；
- resolved budget（解析后预算）和 provider profile ref（供应商配置引用）。

## 当前配置缺口

当前 `config/boardroom-roles.example.yaml` 只显式包含 worker seats（工人席位）。V2-090F 是重要 proving run（证明运行），不应污染通用 example config（示例配置），也不应让临时 `.env` 参数覆盖真实基线。因此 V2-090F 实施前必须新增专用配置基线：

```text
config/boardroom-runtime.v2-090f.yaml
config/boardroom-providers.v2-090f.yaml
config/boardroom-roles.v2-090f.yaml
```

`.env` 只允许指向这三份文件并提供 secret（密钥）与 atomic-agent path（原子智能体路径）。所有预算、provider timeout（模型供应商超时）、角色席位、tools（工具）和 skill refs（技能引用）必须来自上述 YAML，而不是 `.env` 临时键。

V2-090F 专用 roles baseline（角色基线）必须新增 fail-closed 检查：

- 缺任一 required seat 必须失败；
- 任一 required seat 复用 `seat.worker.implementation` 必须失败；
- 任一 required seat 未绑定 V2-090F high-budget profile 或 high-reasoning provider profile 必须失败；
- role slot（角色席位）的 `role_profile_ref` 与 compiled `ExecutionPackage.role_prompt_hook` 不匹配必须失败；
- `AgentInvocation.role_context`（智能体调用角色上下文）缺 hook ref/version/sha256 或 prompt text snapshot（提示词快照）必须失败；
- `AgentInvocation.skill_context.skill_refs` 与 role slot 配置不一致必须失败；
- provider attempt（模型调用尝试记录）的 hook ref/version/hash 与对应 execution package 不一致必须失败。

## 编译器边界

当前 `AtomicInvocationCompiler.compile_with_settings`（带配置的原子调用编译）默认要求 command evidence 和 workspace mutation，这适合 worker implementation（工人实施），但不适合 CEO/Architect/Checker/Closeout。

V2-090F 计划必须先支持 role-specific invocation requirements（按角色区分的调用要求）：

- governance/planning/checking/closeout roles（治理/规划/检查/收尾角色）可以只读或只写 audit/contract artifacts；
- implementation worker 必须要求 workspace mutation、command evidence 和 source lineage；
- checker/closeout 不得因为缺 implementation workspace mutation 被迫失败；
- 所有角色仍必须产生 provider turn facts 和 event stream。

这不是放松 evidence gates，而是防止把 worker-only executor policy（仅工人执行策略）错误套到全团队角色上。

## 配置基线

090F 必须生成并校验 `00-boardroom/v2-090f-baseline.json`，至少包含：

- PRD path 和 PRD sha256；
- runtime/providers/roles YAML 路径和 sha256；
- atomic-agent contract lock ref/hash；
- required seats 列表；
- 每个 seat 的 role_profile_ref、role_category、provider_profile_ref、model、reasoning_effort、tools、skill_refs、budget_profile_ref、resolved budget hash；
- action protocol（动作协议）、max_actions_per_turn、required-output checkpoint max_auto_runs；
- evidence root、event stream root、artifact root；
- network policy（网络策略）和 filesystem write policy（文件系统写策略）。

若 baseline hash 漂移，`--check` 必须失败并提示重新运行受控 rebuild，不得静默接受。

V2-090F 专用配置必须采用 high-budget baseline（高预算基线），避免本轮被预算或 timeout 绊住：

- 所有 required seats 使用 high reasoning provider profile（高推理供应商配置）。
- 所有 required seats 使用 `agent_team.v2_090f.fullstack` 或等价高预算 profile。
- resolved budget 应接近或等于现有 `budget_caps`（预算上限），例如 `max_steps=240`、`max_parse_failures=6`、`max_observation_chars=64000`、`max_wall_seconds=10800`、`max_actions_per_turn=8`。
- provider `total_timeout_seconds` 和 `stream_idle_timeout_seconds` 可在 `config/boardroom-providers.v2-090f.yaml` 中显式提高，但必须进入 baseline hash。
- 不得通过 `.env` 临时提高 model、timeout、reasoning effort、budget 或 retry。

Retry policy（重试策略）必须保持可审计：允许 provider parse/action retry（解析/动作重试）和 runtime crash before mutation retry（工作区变更前运行时崩溃重试）；不得在 workspace mutation（工作区变更）之后整票重试，除非另行设计 idempotency policy（幂等策略）并通过评审。

## Reference Examples

为降低首次 agent team planning（智能体团队规划）失败率，V2-090F 可以向 CEO/Architect/Tester 提供 reference examples（参考示例），但这些示例只能作为上下文，不得成为 runner 预置任务图：

- 可以提供一份 tiny fullstack acceptance example（微型全栈验收示例），说明合同应覆盖真实 backend/frontend service、HTTP CRUD、SQLite persistence 和 live probe。
- 可以提供一份 ticket graph shape example（任务图形状示例），说明任务图必须有 owner seat、dependencies（依赖）、evidence obligations（证据义务）和 acceptance refs（验收引用）。
- 不得提供固定 ticket refs、固定 backend/frontend/integration 三票、固定执行顺序或固定源码文件清单。
- 任何由 reference example 影响的产物仍必须由 agent role provider attempt（角色模型调用尝试）生成，并留下 role context evidence（角色上下文证据）。

## 数据流

```text
short PRD
  -> PRD intake by CEO seat
  -> Architect generates AcceptanceContract + PackageContract + TicketGraph
  -> Tester generates verification plan and probes
  -> Worker executes autonomous implementation tickets through AtomicAgentExecutor
  -> Checker evaluates evidence against contracts
  -> Closeout assembles closeout/audit package
  -> Boardroom gates verify facts, reducers, evidence, closeout
  -> examples/generated-workspaces/tiny-fullstack/
```

Boardroom runner 只负责启动、记录和验证，不替 agent team 设计内部任务分解。

## Fail-Closed Matrix

| 缺口 | 结果 |
|---|---|
| 缺 PRD 或 PRD 为空 | fail closed |
| 缺任一 required agent team seat | fail closed |
| 所有角色复用 worker seat | fail closed |
| 任一非 worker required seat 复用 worker role profile | fail closed |
| 任一 required seat 未使用 V2-090F high-budget / high-reasoning provider baseline | fail closed |
| 任一角色 role_context 缺 hook ref/version/sha256/prompt text | fail closed |
| 任一角色 skill_context 与 role slot 不一致 | fail closed |
| 非 worker 角色获得 implementation source 写权限且未显式授权 | fail closed |
| runner 预置固定 implementation ticket graph | fail closed |
| implementation ticket 走 `ProviderExecutor` | fail closed |
| worker atomic run 缺 provider turn facts/workspace mutation/command evidence/source lineage | fail closed |
| checker/closeout 直接写 `CloseoutPackage.passed` 绕过 gate | fail closed |
| run-backend/run-frontend 缺 service readiness | closeout blocked |
| 缺 live blackbox evidence | closeout blocked |
| `10-project/` 含 `__pycache__`、`.pytest*`、SQLite runtime DB 或临时端口文件 | materialization blocked |
| V2-080 failure package 被当作 passed sample | materialization blocked |
| `--check` 调用 provider 或写 output root | fail closed |

## `scripts/build_tiny_closeout_sample.py` 新语义

保留该脚本名作为 public check/build entrypoint（公开检查/构建入口），但它应委托 PRD agent team runner：

- 默认 build：读取短 PRD，启动 agent team autonomous run（智能体团队自治运行），完成合同、任务图、实施、测试、检查和收尾后发布样例。
- `--check`：只验证已发布样例的 PRD sha256、baseline hash、角色上下文快照、文件 hash、证据 refs、closeout payload 和 forbidden runtime files；不得调用 provider，不得写 output root。
- `--reset`：只清理带 V2-090F marker（标记）的 staging workspace；缺 marker 必须拒绝删除。

## 验收

V2-090F 完成必须同时满足：

1. Role-context negative tests（角色上下文负例）：缺 seat、共用 worker seat、hook mismatch（提示词钩子不匹配）、skill refs mismatch（技能引用不匹配）、越权写源码均失败。
2. PRD autonomy negative tests（PRD 自治负例）：runner 不能预置固定 ticket graph；缺 PRD、空 PRD、静态手写任务图、ProviderExecutor 路径均失败。
3. Non-provider tests（非模型供应商测试）：配置 baseline、reset safety（重置安全）、check no-write（检查不写入）、manifest comparison（清单比较）和 forbidden runtime files（禁用运行时文件）通过。
4. Real provider proving（真实模型供应商证明）：显式 opt-in 后，从短 PRD 触发 agent team 自治交付，最终 closeout gate passed。
5. Sample verification（样例验证）：`scripts/build_tiny_closeout_sample.py --check` exit 0；样例 declared commands 在 `10-project/` 内可运行；service/live blackbox evidence 完整。
6. Documentation sync（文档同步）：backlog、acceptance criteria、examples/scripts README、project log 更新；V2-090F checkbox 只在真实证据齐全后勾选。

## 自审

- Contract first：agent team 必须从 PRD 生成 active contracts 后才能进入 implementation。
- Reducer first：ticket completion 和 closeout verdict 仍由 reducer/gate 决定，agent 不能自封完成。
- Evidence first：每个角色调用、每个 implementation ticket、每个 declared command 和 live probe 都要有真实 evidence。
- Fail closed：缺 seat、缺 hook、缺 skill context、缺 command/service/live/source lineage evidence 默认失败。
- Runtime bounded：atomic-agent 只提供 execution facts，不做 Boardroom 治理结论。
- Negative tests first：先证明 worker-only、pre-split、provider-lock、缺角色上下文等伪闭环失败。

## 评审关注点

- 是否接受为 090F 新增完整 agent team role slots，或先建立 V2-090F 专用 roles config（角色配置）。
- 非 worker 角色是否需要通过 atomic-agent 执行，还是可由现有 provider-backed role execution path（模型支撑角色执行路径）执行；无论哪种，都必须留下 RolePromptHook 与 skill context 证据。
- `AtomicInvocationCompiler` 的 role-specific requirements 是否应作为 090F 前置修复独立拆包。
- 真实 provider run 采用高预算专用 baseline 后，是否仍需要 provider-native structured output/tool calling（供应商原生结构化输出 / 工具调用）来进一步提升稳定性。
