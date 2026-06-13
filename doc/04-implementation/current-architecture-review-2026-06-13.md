# Boardroom OS current architecture review — 2026-06-13

## Scope

本评审基于 `boardroom-os-minimal-2055dd3.zip` 的最小项目包，重点检查：

1. 当前框架是否还存在会阻碍 agent team autonomy（智能体团队自治）的设计缺陷或功能缺口。
2. 角色提示词是否足以约束多角色协作、证据、返工和 closeout（收尾）。
3. `.env` + 多个 YAML 的配置体系是否合理，以及后续调整建议。
4. V2-100 ticket graph / rework loop（工单图 / 返工循环）方向是否合理，以及是否应只由 CEO 更新图。

审阅覆盖的核心文件包括：

- `README.md`
- `AGENTS.md`
- `SESSION_PROMPT.md`
- `.env.example`
- `.env.template`
- `config/boardroom-runtime.example.yaml`
- `config/boardroom-providers.example.yaml`
- `config/boardroom-roles.example.yaml`
- `config/boardroom-runtime.v2-090f.yaml`
- `config/boardroom-providers.v2-090f.yaml`
- `config/boardroom-roles.v2-090f.yaml`
- `src/boardroom_os/config/boardroom.py`
- `src/boardroom_os/workspace/run_manifest.py`
- `src/boardroom_os/agents/role_prompt_hooks.py`
- `src/boardroom_os/proving/v2_090f_prd_agent_team.py`
- `src/boardroom_os/graph/ticket.py`
- `src/boardroom_os/reducers/ticket_reducer.py`
- `src/boardroom_os/events/types.py`
- `src/boardroom_os/closeout/gate.py`
- `doc/03-architecture/domain-model.md`
- `doc/03-architecture/contract-and-evidence-model.md`
- `doc/03-architecture/execution-and-runtime-boundary.md`
- `doc/04-implementation/acceptance-criteria.md`
- `doc/04-implementation/backlog.md`
- `examples/generated-workspaces/tiny-fullstack/30-audit/v2-090k-failure-snapshot/`

## Executive verdict

V2-100 的方向是正确的，但必须从 “CEO 单点图更新” 调整为 “CEO 负责提出返工意图与路线，Architect / Checker / Tester / Release DevOps 分域审查，reducer 负责唯一提交”。

换句话说：CEO 可以是 accountable planner（责任规划者），但不应是 graph patch（图补丁）的唯一审查者或提交者。真正稳健的自治不是让一个模型角色拥有所有权限，而是让多个模型角色在强类型合同、事件、证据和 reducer 门禁下分工制衡。

当前项目已经具备较好的底层基础：合同、EvidenceVerifier、CheckerVerdict、RunManifest、SourceInventory、CloseoutGate、Replay/Process/Git audit、role prompt hook 哈希审计、runtime/executor 边界等都已经成形。阻碍自治的主要问题不在于“没有基础设施”，而在于：返工循环尚未一等化、graph patch 缺多角色审查、提示词资产此前较弱、配置和场景 runner 仍有若干第二权威源/耦合风险。

## Test observations

已执行的本地验证：

```bash
PYTHONPATH=src:. python -m pytest \
  tests/execution/test_role_prompt_hooks.py \
  tests/execution/test_role_prompt_hooks_rework_governance.py \
  tests/workspace/test_run_manifest_behavioral_probe.py \
  tests/workspace/test_run_manifest_service_contract.py \
  -q
```

结果：`32 passed`。

提示词专项验证：

```bash
PYTHONPATH=src:. python -m pytest \
  tests/execution/test_role_prompt_hooks.py \
  tests/execution/test_role_prompt_hooks_rework_governance.py \
  -q
```

结果：`18 passed`。

全量测试收集目前不能在该最小 zip 中直接运行，原因是项目代码在 `src/boardroom_os/config/boardroom.py` 顶层导入外部依赖：

```python
from atomic_agent.providers.openai_compatible import OpenAICompatibleProviderOptions
```

最小包没有包含依赖声明文件，也没有安装 `atomic_agent`，所以 `python -m pytest -q` 会在 collection 阶段失败：

```text
ModuleNotFoundError: No module named 'atomic_agent'
```

这个失败本身是一个架构/交付问题：最小可审计包应当至少包含 dependency manifest，或让真实 provider 依赖延迟导入，使纯模型、合同、reducer、证据测试可以在无外部 provider SDK 时收集并运行。

## What is already strong

### 1. 合同优先的方向正确

项目已经把 AcceptanceContract、PackageContract、SourceInventory、RunManifest、EvidenceClaim、VerifiedEvidence、FinalEvidenceTable、CheckerVerdict、CloseoutGate 等拆成强类型边界。这是 agent team autonomy 的正确地基，因为它让模型输出必须进入可验证结构，而不是靠 reviewer prose（评审文字）或 runner helper（运行器辅助器）宣布完成。

### 2. Runtime / executor 边界方向正确

`doc/03-architecture/execution-and-runtime-boundary.md` 已经明确 runtime 和 atomic-agent 不能直接推进治理终态。这个原则必须在 V2-100 继续强化：runtime 只能执行事实、记录事实、提交事实事件；不能替 CEO 规划、替 Checker 判断、替 CloseoutGate 通过。

### 3. CloseoutGate 已经比普通项目脚手架强很多

`src/boardroom_os/closeout/gate.py` 已经检查 package contract、source inventory、run manifest、final evidence table、checker verdict、verified evidence、provider attempts、command binding、replay/git/process readiness 等。这是防止 “命令跑过 = 项目完成” 的关键。

### 4. RolePromptHook 已经具备哈希审计

`src/boardroom_os/agents/role_prompt_hooks.py` 会读取模板、计算 sha256、绑定 role profile，并拒绝缺失 prompt hook 的执行包。这意味着提示词可以成为可审计资产，而不是随手拼接的 prompt 文本。

### 5. V2-090K 失败快照非常有价值

`examples/generated-workspaces/tiny-fullstack/30-audit/v2-090k-failure-snapshot/` 捕获了四类真实失败：行为探针响应 shape 错配、环境变量绑定未收敛、最终证据表引用旧 AC、closeout/audit 引用旧 run。这个快照正好可以作为 V2-100 的真实 blocker 输入，而不是再构造玩具失败。

## P0 blockers to agent team autonomy

### P0-1: Rework loop 仍主要存在于文档和 backlog，尚未成为代码一等模型

`doc/03-architecture/domain-model.md` 已经描述了 ReworkCycle / ReworkRequest / ReworkPlan / ReworkAttempt / ReworkOutcome，但当前代码层还没有对应的 `boardroom_os/rework/` 强类型模型、事件、reducer 和 recheck pipeline。

结果是：系统已经能 fail closed，但不能自治地从 fail closed 进入“结构化返工 -> 更新工单图 -> 执行返工 -> 重验证 -> 收敛或升级”。这正是 V2-100 必须补齐的核心。

建议：V2-100A~E 应继续推进，但要加入 GraphPatchReviewGate（图补丁审查门禁），详见 `v2-100-agent-team-rework-loop-spec.md`。

### P0-2: 只让 CEO 进行图重审/图更新会形成新的单点脆弱性

CEO 适合负责目标、范围、路线和取舍，但不适合独自判断所有图不变量。V2-090K 暴露的问题跨越多个专业域：

- 响应 shape 错配属于 contract/probe/implementation 三方不一致，需要 Tester 和 Architect 参与判断。
- env binding 未收敛属于 RunManifest、启动命令、实现读取变量三方不一致，需要 Release DevOps 和 Architect 参与判断。
- 旧 AC 引用属于 evidence projection / contract authority 问题，需要 Checker 参与判断。
- 旧 run 引用属于 closeout/audit fact-chain 问题，需要 Closeout/Checker 参与判断。

因此 CEO 只能提出 TicketGraphPatch，不应单独批准或提交。推荐规则：

- CEO：提出 ReworkPlan 和 TicketGraphPatch。
- Architect：审查 contract、dependency、allowed_write_set、source surface、graph invariant。
- Checker：审查 blocker coverage、evidence obligation、旧证据复用风险。
- Tester：审查 test/probe 行为语义，尤其是 contract-vs-probe-vs-implementation mismatch。
- Release DevOps：审查 RunManifest、env binding、readiness、service startup、sample promotion。
- Reducer：唯一可以提交 graph patch 的程序边界。

### P0-3: 最小包不可完全复现测试

缺少 `pyproject.toml` / dependency lock / extras 声明，导致没有安装 `atomic_agent` 时全量测试无法 collection。更重要的是，`atomic_agent` 依赖在 config 模块顶层导入，会让与 provider 无关的测试也被阻断。

建议：

1. 增加项目依赖声明，至少包含 core/test/provider extras。
2. 将 provider-specific SDK 导入延迟到 provider adapter 或 factory 内部。
3. 没有 provider SDK 时，纯合同、reducer、run manifest、evidence、closeout 测试应能照常收集和运行。
4. provider/integration 测试使用 marker，例如 `pytest -m provider`，默认跳过或 fail with clear install instruction。

### P0-4: RunManifest 对 runnable 项目的强制性还不够

`src/boardroom_os/workspace/run_manifest.py` 已经能表达 service contracts、env bindings、readiness probes、behavioral probes、frontend topology 等。但现有验证逻辑对 `service_contracts == ()` 会拒绝 run commands，对 `service_contracts is None` 的语义仍较宽。

对于 fullstack/software workspace，只要声明了 run commands、service run evidence、readiness probe、behavioral probe 或 frontend/backend topology，就应强制存在显式 service contracts。否则系统容易回到 “能跑命令但没有可审计服务协议” 的弱状态。

建议：V2-100D 或 V2-100E 增加负例：有 run command / service evidence / behavioral probe 但无 service_contracts 时 fail closed。

## P1 design risks

### P1-1: Scenario runner 仍过重，容易成为第二权威源

`src/boardroom_os/proving/v2_090f_prd_agent_team.py` 包含大量规划、normalize、payload build、probe run、workspace materialize、evidence/closeout helper 逻辑。V2-090K 已经消除了不少硬编码，但该文件仍然过大，且存在 scenario-specific 常量和校验路径，例如 hard CRUD operation acceptance validation。

这类代码在 proving scenario 阶段可以存在，但不能成为框架事实源。后续建议把可复用能力拆到独立模块：

- `boardroom_os/rework/model.py`
- `boardroom_os/rework/blocker_projection.py`
- `boardroom_os/rework/ticket_graph_patch.py`
- `boardroom_os/rework/reducer.py`
- `boardroom_os/rework/evidence.py`
- `boardroom_os/proving/scenarios/v2_100_rework_loop.py`

Scenario runner 只应做 scenario composition（场景编排），不应生成最终事实、替 agent 判断或修正模型输出。

### P1-2: Role YAML 没有承载 prompt hook 绑定

代码中 RoleProfile 已经要求 `role_prompt_hook_ref`、version、sha256，但配置层的 roles YAML 还没有成为 prompt hook 的可治理入口。现在 v2-090F runner 中存在 seat -> hook ref 的代码映射，这会造成“角色配置在 YAML，提示词绑定在 Python”的双轨状态。

建议：

- 在 `config/boardroom-roles*.yaml` 为每个 seat 增加 `role_prompt_hook_ref`、`role_prompt_hook_version`、`role_prompt_hook_sha256` 或 `role_prompt_profile`。
- 启动时由配置 loader 校验 hook ref、version、sha256 与模板实际内容一致。
- 运行产物记录 prompt hook hash，作为 provider attempt 和 closeout audit 的一部分。

### P1-3: README 状态已落后

`README.md` 仍描述为 “foundation-only / no implementation package”。当前项目已经包含大量实现、proving runner、配置、测试和真实失败快照。文档状态落后会误导后续 agent team。

建议：新增 README 当前状态更新，至少说明：

- 当前处于 V2-100 前置状态。
- V2-090K 已产生 fail-closed 快照，V2-090F golden sample 仍待 V2-100 后复判。
- 默认全量测试需要 provider 依赖或 extras；无 provider 依赖时使用 core test 命令。

### P1-4: TicketGraph 状态机还不够表达多轮返工

`TicketStatus` 目前主要是 READY / BLOCKED / COMPLETED，已有 `TICKET_REWORKED` 语义，但没有一等 ReworkCycle 状态、GraphPatch 状态、Review 状态、Attempt 状态。V2-100 不一定要把所有状态塞进 TicketStatus，但必须有可回放的 ReworkReducer 投影。

建议：TicketGraph 保持 task dependency source of truth；ReworkReducer 维护 cycle/attempt/patch/review projection；二者通过 graph_version 和 ticket_ref 关联。

### P1-5: Closeout 对 behavioral probes 的显式约束可以再加强

CloseoutGate 已经检查大量事实链，但 090K 暴露的 `probe-response-shape-mismatch` 说明 behavioral probe result 必须成为 final evidence row 的强约束，而不是旁路材料。

建议：RunManifest 的 behavioral probes 应和 AcceptanceContract proposition 形成显式 mapping；FinalEvidenceTableBuilder 必须能从 mapping 推导每个 live behavior 的 row requirement；CloseoutGate 要拒绝 behavioral probe 未映射、未执行、shape mismatch 或旧轮次复用。

## Configuration review

### 总体判断

`.env` + 多个 `.yaml` 的配置体系总体合理。推荐继续保留这个方向：

- `.env`：只承载本地秘密、配置文件路径、环境开关、provider API key、workspace 根路径等机器相关值。
- `boardroom-providers*.yaml`：承载 provider base URL、model、timeout、retry、structured output 能力等模型供应商配置。
- `boardroom-runtime*.yaml`：承载执行边界、预算、工具权限、网络/文件系统/命令策略、artifact 路径等运行时约束。
- `boardroom-roles*.yaml`：承载 seat、role、capability、budget、tools、skills、responsibilities、prompt hook 绑定等团队结构。

这个拆分方向是对的，因为它把 secret、本地路径、供应商配置、运行时权限、角色治理分开了。

### 配置体系建议

#### 1. `.env` 只放本地/秘密，不放治理策略

保留：

- API key / token。
- config file path。
- local workspace root。
- opt-in 开关，例如 real provider run。

避免：

- acceptance / package / graph / rework policy。
- role prompt 文本。
- evidence gate 行为。
- model temperature、budget、tool 权限等可审计治理策略。

#### 2. 增加 config bundle manifest

当前 `.env` 通过多个路径指向 runtime/providers/roles YAML，长期容易组合出未经审计的混搭配置。建议新增：

```yaml
version: 1
bundle_id: boardroom-config.v2-100.default
runtime_config: config/boardroom-runtime.v2-100.yaml
providers_config: config/boardroom-providers.v2-100.yaml
roles_config: config/boardroom-roles.v2-100.yaml
expected_hashes:
  runtime_sha256: ...
  providers_sha256: ...
  roles_sha256: ...
```

`.env` 优先只指向 bundle：

```bash
BOARDROOM_CONFIG_BUNDLE=config/boardroom-config.v2-100.yaml
```

如果仍保留三路径模式，也应把三份配置的 hash 写入 run manifest / process audit。

#### 3. roles YAML 增加 prompt hook 绑定

推荐每个 seat 显式配置：

```yaml
seats:
  - seat: ceo
    role_kind: ceo
    role_prompt_hook_ref: role-prompt-hook.baseline.ceo.v1
    role_prompt_hook_version: v1
    role_prompt_policy_refs:
      - policy.contract-first
      - policy.reducer-protected
      - policy.evidence-first
      - policy.fail-closed
    graph_review_domains:
      - scope
      - blocker_routing
      - rework_plan
```

sha256 可以由 loader 计算并写入 run artifact；也可以在 YAML 中钉死，适合 release profile。

#### 4. runtime YAML 增加 graph patch review policy

V2-100 建议新增：

```yaml
graph_patch_review_policy:
  require_ceo_proposal: true
  required_review_domains:
    structural: architect
    blocker_coverage: checker
    behavioral_probe: tester
    run_env_readiness: release_devops
  commit_actor: reducer
  allow_runtime_commit: false
  allow_executor_commit: false
```

#### 5. provider YAML 增加能力声明

不同模型/provider 对 structured output、JSON schema、tool calling、max context、retry idempotency 的支持不同。建议在 providers YAML 中显式声明：

```yaml
capabilities:
  structured_output: true
  json_schema_strict: true
  tool_calling: false
  max_input_tokens: ...
  max_output_tokens: ...
retry_policy:
  max_attempts: 2
  retry_on_transport_error: true
  retry_on_schema_error: false
```

这能避免 runner 在未知 provider 能力下猜测输出契约。

#### 6. 增加配置验证 CLI

建议新增：

```bash
python -m boardroom_os.config.validate --bundle config/boardroom-config.v2-100.yaml
```

验证项至少包括：

- YAML schema。
- env key 存在但不泄漏。
- provider profile 可解析。
- roles seat 与 prompt hook ref 匹配。
- runtime tool policy 与 role tools 不冲突。
- config hash 可写入 run manifest。

## Prompt work applied in this review

本次评审已强化并写入以下七个 prompt hook 模板：

- `src/boardroom_os/agents/prompt_templates/baseline/v1/ceo.md`
- `src/boardroom_os/agents/prompt_templates/baseline/v1/architect.md`
- `src/boardroom_os/agents/prompt_templates/baseline/v1/worker.md`
- `src/boardroom_os/agents/prompt_templates/baseline/v1/tester.md`
- `src/boardroom_os/agents/prompt_templates/baseline/v1/release_devops.md`
- `src/boardroom_os/agents/prompt_templates/baseline/v1/checker.md`
- `src/boardroom_os/agents/prompt_templates/baseline/v1/closeout.md`

写入后的提示词强化了：

- CEO 只做 accountable planning，不单点提交 graph patch。
- Architect 负责 contract / source surface / graph invariant / run boundary 审查。
- Worker 只在 allowed_write_set 内实施，不修改合同、证据或 closeout。
- Tester 负责 negative-first、live behavior、probe shape 和 contract/probe/implementation mismatch 判断。
- Release DevOps 负责 RunManifest、env binding、readiness、service startup、sample promotion。
- Checker 负责 blocker coverage、evidence obligation、旧证据/旧 run 引用拒绝。
- Closeout 负责同一轮 fact-chain、replay/process/git audit 和旧 run/旧证据拒绝。

已验证 `tests/execution/test_role_prompt_hooks.py` 和新增的 `tests/execution/test_role_prompt_hooks_rework_governance.py` 通过，说明模板仍满足当前 RolePromptHook 哈希/责任项审计，并锁定了多角色 graph patch review、返工、旧证据/旧 run 拒绝等关键约束。

## V2-100 judgement

V2-100 阶段合理，且是 V2-090K 后的正确下一步。但建议把名称里的 “CEO-governed rework loop” 精确定义为：

> CEO-governed means CEO-owned intent and rework route, not CEO-only graph authority.

推荐 V2-100 的核心不变量：

1. ReworkRequest 必须来自 verified blocker、FinalEvidenceTable failed/missing row 或 CloseoutGate failure。
2. ReworkPlan 必须有 CEO provider attempt lineage。
3. TicketGraphPatch 必须被多角色分域审查。
4. Reducer 是唯一 graph commit 边界。
5. Runtime/executor/atomic-agent 不能直接提交 accepted/completed/escalated/exhausted。
6. 每个 ReworkAttempt 都必须重新进入 source inventory、evidence verifier、final evidence table、checker 和 closeout gate。
7. 旧证据、旧 checker verdict、旧 closeout package、旧 run ref 不得跨轮次复用为通过证据。
8. 返工预算耗尽必须生成 explicit escalation / termination decision，不能无限循环。

详细工作包 spec 见：`doc/04-implementation/v2-100-agent-team-rework-loop-spec.md`。

## Immediate next actions

1. 接受本次 prompt pack，并把 roles YAML 与 RolePromptHook 绑定纳入配置系统。
2. 实施 V2-100A：先做 Rework domain model 和 090K failure snapshot -> ReworkIssue projection。
3. 实施 V2-100B：增加 rework event taxonomy、ReworkReducer、GraphPatchReviewGate。
4. 在 V2-100C 前明确多角色 graph patch review policy，避免 CEO 单点图更新。
5. 在实现 V2-100E 前修复最小包依赖复现问题，否则真实回归难以自动化。
