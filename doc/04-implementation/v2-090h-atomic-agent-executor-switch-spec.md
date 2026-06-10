# V2-090H Atomic-agent executor switch spec（原子智能体执行器切换规范）

## 状态

Draft for expert review（待专家评审）。本文只定义 V2-090H 的实施边界、配置模型、请求体编译目标、fail-closed（失败关闭）矩阵和实施计划输入；本轮不写生产实现代码，不承诺真实 atomic execution（原子执行）已经完成。

## 背景

V2-090G Atomic-agent package/import integration（原子智能体包导入集成）已完成，但它只证明 Boardroom OS（董事会操作系统）可以通过外部 `atomic-agent`（原子智能体）Python package（Python 包）调用 `AgentRuntimePort.invoke(AgentInvocation)`（智能体运行端口调用）并校验 `AgentRunResult`（智能体运行结果）。当前 implementation ticket（实施任务）主执行路径仍可能停留在 `ProviderExecutor`（模型供应商执行器）+ `OpenAIProviderTransport`（OpenAI 模型传输）的单次 LLM request（大模型请求），这只能证明 `ProviderAttempt`（模型调用尝试记录）存在，不能证明 agent loop（智能体循环）在受控 workspace（工作区）中读文件、写文件、运行命令、观察失败并提交可审计结果。

V2-090H 必须把 implementation ticket 主路径切到 atomic-agent executor（原子智能体执行器）。但在实施前需要先纠正配置边界：Boardroom OS 的现有 `.env.template`（环境变量模板）承载了大量 provider/model 参数；atomic-agent 已有 `AgentInvocation`（智能体调用）字段和 `OpenAICompatibleProviderOptions`（OpenAI 兼容供应商选项），继续把所有字段平铺进 `.env` 会形成 second source of truth（第二事实源），也无法表达不同 role slot（角色席位）绑定不同 provider/model/skill（供应商/模型/技能）的互补能力。

## 本轮决策

V2-090H 采用三文件配置方案，`.env` 只保留路径和密钥。

外部 `atomic-agent` 安装路径不得在实现或测试中硬编码。Boardroom OS 使用 `BOARDROOM_ATOMIC_AGENT_PATH`（原子智能体路径）作为 bootstrap path（启动路径），默认值为 `../atomic-agent`。所有 pre-flight、editable install（可编辑安装）、contract hash（契约哈希）和 package provenance（包来源）检查都必须从该变量或等价 runtime config 字段解析路径；不得直接依赖当前工作目录旁边必然存在 `../atomic-agent`。

1. `config/boardroom-runtime.example.yaml`：runtime config（运行时配置）。定义 atomic executor（原子执行器）启用状态、event/artifact roots（事件/产物根目录）、default budgets（默认预算）、tool limits（工具限制）、network policy（网络策略）和 implementation execution mode（实施执行模式）。
2. `config/boardroom-providers.example.yaml`：providers config（供应商配置）。首版只支持 OpenAI-compatible profiles（OpenAI 兼容配置档），每个 profile 可对应不同 base URL、model、timeout、stream、sampling/request 参数和 secret env ref（密钥环境变量引用）。
3. `config/boardroom-roles.example.yaml`：roles config（角色/席位配置）。表达 Boardroom role slot（角色席位）如何绑定 provider profile（供应商配置档）、model execution profile（模型执行配置）、skill bindings（技能绑定）和 per-role budgets（按角色预算）。roles.yaml 只引用 provider profile id（供应商配置档标识），不得重复 provider request 参数。

`.env.template` 与 `.env.example` 的新定位：只放 config path（配置文件路径）、secret（密钥）和少量 bootstrap/local path（启动/本地路径），不再承载模型参数、timeout、retries、context window、system instructions（系统指令）等配置项。

首版 provider 仅按 OpenAI-compatible protocol（OpenAI 兼容协议）设计。OpenAI、Anthropic、Gemini 等后台若已经统一转为 OpenAI-compatible endpoint（OpenAI 兼容端点），Boardroom OS 不直接支持 Anthropic SDK（Anthropic 软件开发包）或 Gemini SDK（Gemini 软件开发包）。若未来新增 native provider（原生供应商）协议，必须新增显式 provider type（供应商类型）和 fail-closed schema（失败关闭结构），不能在 OpenAI-compatible 字段中静默兼容。

## 已验证的 atomic-agent active contract（活跃契约）

V2-090H 实施必须基于外部 `../atomic-agent` 的实际 active contract，不得凭记忆扩展协议。

### Dependency and contract lock（依赖与契约锁定）

V2-090H 必须把 `atomic-agent` 的版本、源码路径和契约文档 hash 记录为可审计事实。当前本地 `atomic-agent` 仍导出 `__version__ = "0.0.0"`，因此不能只依赖 semver（语义化版本）判断兼容性；在正式版本号稳定前，Boardroom OS 必须以 contract hash（契约哈希）和 model fields snapshot（模型字段快照）作为兼容性门禁。

`AtomicAgentDependencyInfo`（原子智能体依赖信息）需要扩展为至少包含：

```text
package_name
package_version
source_path
runtime_port_contract_ref
contract_hashes
model_fields_snapshot
compatible_version_range
```

`contract_hashes` 至少覆盖：

- `docs/03-contracts/agent-runtime-port.md`
- `docs/03-contracts/agent-action-protocol.md`
- `docs/03-contracts/event-stream-protocol.md`
- `src/atomic_agent/models.py`
- `src/atomic_agent/event_recorder.py`

Boardroom OS 需要新增 `doc/06-reference/atomic-agent-contract-lock.md`（原子智能体契约锁定清单）。该文件是审计锁定清单，不是第二事实源；它记录当前已评审的外部 contract path（契约路径）、sha256、`AgentInvocation` 字段集合、`AgentRunResult` 字段集合和 event stream format（事件流格式）。运行时发现 hash 或字段集合不匹配时必须 fail closed，并提示重新评审 `atomic-agent` 契约，而不是静默继续执行。

### AgentInvocation（智能体调用）字段

`../atomic-agent/src/atomic_agent/models.py` 当前定义：

```text
invocation_id: str
task: str
workspace_root: str
allowed_write_set: list[str]
tools: list[str]
permission_policy: dict[str, Any]
provider_profile: dict[str, Any]
budgets: dict[str, Any]
output_requirements: dict[str, Any]
role_context: str | None
skill_context: dict[str, Any] | None
initial_files: list[str] | None
metadata: dict[str, Any] | None
```

`AgentLoop`（智能体循环）当前会 fail closed 校验：

- `permission_policy.policy_ref` 必须是非空字符串。
- `budgets.max_steps` 必须是正整数。
- `budgets.max_parse_failures` 必须是非负整数。
- `budgets.max_observation_chars` 必须是正整数。
- `budgets.max_wall_seconds` 必须是有限正数。
- `invocation.tools` 必须包含 `submit_result`。

### AgentRunResult（智能体运行结果）字段

```text
run_id: str
status: completed | failed | interrupted | requires_approval
event_stream_ref: str
events_hash: str
tool_attempts: list[dict[str, Any]]
workspace_mutations: list[dict[str, Any]]
artifacts: list[dict[str, Any]]
summary: str
failure_kind: str | None
failure_message: str | None
failed_action_ref: str | None
```

`status == completed` 只表示 atomic-agent runtime（原子智能体运行时）提交了结果，不代表 Boardroom `TICKET_COMPLETED`（任务完成）、`CloseoutPackage.passed`（收尾包通过）或 `CLOSEOUT_COMMITTED`（收尾已提交）。

### OpenAI-compatible provider 当前消费方式

只读探索确认：

- `AgentInvocation.provider_profile` 当前主要是审计画像和 provider context（供应商上下文）透传字段；`AgentLoop` 不从该 dict 反向构造 provider client（供应商客户端）。
- atomic-agent 真实 OpenAI-compatible 调用由 `OpenAICompatibleProviderOptions`（OpenAI 兼容供应商选项）构造 `OpenAICompatibleProviderAdapter`（OpenAI 兼容供应商适配器）。
- `OpenAICompatibleProviderOptions.to_provider_profile()` 会生成脱敏 `provider_profile` 写入 `AgentInvocation`，用于 audit/evidence（审计/证据）。
- Chat Completions streaming（聊天补全流式）请求固定发送 `model`、`messages`、`stream=True`、`max_tokens`；仅在显式配置时发送 `temperature`、`reasoning_effort`、`top_p`、`presence_penalty`、`frequency_penalty`、`seed`、`stop`、`response_format`、`stream_options`、`service_tier`、`user`。

因此 Boardroom OS 必须从 providers.yaml 编译出两类对象：

1. atomic-agent runtime 实际需要的 `OpenAICompatibleProviderOptions`；
2. 写入 `AgentInvocation.provider_profile` 的脱敏审计 profile。

不得只把 provider profile dict 传给 `AgentInvocation` 后假装真实 provider 已配置。

## 非目标

- 不在 V2-090H spec/plan 阶段写生产实现代码。
- 不恢复 V2-090F golden sample rebuild（黄金样例重建）。
- 不把 atomic-agent examples CLI（示例命令行）作为 Boardroom 正式执行协议。
- 不复制 `../atomic-agent/src/atomic_agent` 源码进 `src/boardroom_os/`。
- 不新增 Anthropic/Gemini native SDK provider（原生 SDK 供应商）。
- 不允许 fake provider transport（模拟供应商传输）满足 V2-090H 真实 executor happy path（正向路径）。
- 不让 runtime（运行时）或 executor（执行器）越权提交 `TICKET_COMPLETED` / `CLOSEOUT_COMMITTED`。

## 目标状态

V2-090H 实施完成后，implementation ticket 主路径应为：

```text
Active AcceptanceContract（验收合同） + PackageContract（包合同）
  -> TicketGraph（任务图）中的 implementation ticket（实施任务）
  -> AgentSeat（智能体席位） + RoleProfile（角色模板） + RolePromptHook（角色提示词钩子）
  -> ModelExecutionProfile（模型执行配置）
  -> ExecutionPackage（执行包）
  -> Boardroom runtime/providers/roles config（三文件配置）
  -> AtomicExecutionRequest（原子执行请求，Boardroom 内部边界）
  -> AtomicInvocationCompiler（原子调用编译器）生成 AgentInvocation
  -> AtomicAgentRuntimeFactory（原子智能体运行时工厂）生成 AgentRuntimePort
  -> atomic_agent.AgentRuntimePort.invoke(...)
  -> AgentRunResult + event stream + artifacts + workspace mutations + command evidence
  -> AtomicAgentResultValidator（原子结果校验器）
  -> AtomicResultProjector（原子结果投影器）
  -> WorkProductSubmission（工作产物提交） + source lineage input（源码来源链输入）
  -> EvidenceVerifier / Checker / Reducer / CloseoutGate（证据验证器/检查者/归约器/收尾门禁）
```

关键约束：

- `ProviderExecutor.execute` 不再用于 implementation category ticket（实施类别任务）的成功证据。
- `ProviderAttempt` 仍必须存在，但它应来自 atomic-agent event stream 中的 provider turn facts（模型轮次事实）或由 Boardroom projector（投影器）绑定 atomic run（原子运行）生成，而不是单次 JSON source delivery（JSON 源码交付）。
- Command evidence（命令证据）必须来自 atomic-agent `run_command` action（运行命令动作）和 `command.completed` event（命令完成事件），且 command id 必须来自 `ExecutionPackage.commands`。
- Workspace mutation（工作区变更）必须来自 `write_file` / `apply_patch` action（写文件/补丁动作），路径必须落在 `allowed_write_set`。
- Source inventory lineage（源码清单来源链）必须绑定 producer ticket（生产任务）、provider attempt（模型调用尝试）、atomic run id（原子运行标识）、tool attempt id（工具尝试标识）、sha256（哈希）、acceptance refs（验收引用）、source surface refs（源码实现面引用）和 evidence refs（证据引用）。

## 配置设计

### 1. `config/boardroom-runtime.example.yaml`

职责：定义 Boardroom runtime（运行时）如何启用 atomic-agent executor、在哪里落事件和产物、工具限制和默认预算。

```yaml
version: 1
runtime_id: boardroom-runtime.local
execution:
  implementation_executor: atomic_agent
  reject_provider_executor_for_implementation: true
atomic_agent:
  package_name: atomic-agent
  import_name: atomic_agent
  runtime_port_contract_ref: atomic-agent.docs.agent-runtime-port.v1
  event_stream_root: .evidence/atomic-agent/events
  artifact_root: .evidence/atomic-agent/artifacts
  run_id_prefix: boardroom-atomic
  dependency:
    atomic_agent_path_env: BOARDROOM_ATOMIC_AGENT_PATH
    default_atomic_agent_path: ../atomic-agent
    contract_lock_ref: doc/06-reference/atomic-agent-contract-lock.md
    require_contract_hash_match: true
  execution_policy:
    wall_time_seconds: 900
    retry_on_provider_timeout: false
    retry_on_runtime_crash: true
    max_retries: 1
    interrupt_grace_period_seconds: 30
    retry_requires_no_workspace_mutation: true
  concurrency:
    mode: serial_per_workspace
    workspace_lock_root: .evidence/atomic-agent/locks
    require_run_scoped_event_artifact_roots: true
  default_tools:
    - list_files
    - read_file
    - search_files
    - write_file
    - apply_patch
    - run_command
    - submit_result
  required_tools:
    - submit_result
  tool_permission_map:
    filesystem.read:
      - list_files
      - read_file
      - search_files
    filesystem.write:
      - write_file
      - apply_patch
    command.execute:
      - run_command
    network.fetch:
      - web_fetch
  budget_profiles:
    atomic.proving.minimal:
      max_steps: 32
      max_parse_failures: 2
      max_observation_chars: 16000
      max_wall_seconds: 1200
    worker.implementation.default:
      max_steps: 96
      max_parse_failures: 3
      max_observation_chars: 24000
      max_wall_seconds: 3600
    worker.implementation.large:
      max_steps: 160
      max_parse_failures: 4
      max_observation_chars: 32000
      max_wall_seconds: 7200
  budget_caps:
    max_steps: 240
    max_parse_failures: 6
    max_observation_chars: 64000
    max_wall_seconds: 10800
  filesystem:
    default_read_limit: 12000
    max_read_limit: 50000
    default_max_entries: 200
    max_entries_limit: 1000
    default_max_matches: 50
    max_matches_limit: 500
  commands:
    default_timeout_seconds: 60
    max_timeout_seconds: 300
    max_output_bytes: 200000
  network:
    default: deny
    allow_rules: []
```

Fail-closed 要求：

- `execution.implementation_executor != atomic_agent` 时，implementation ticket 不得通过 V2-090H happy path。
- `reject_provider_executor_for_implementation` 缺失或为 false 时，implementation ticket 走 `ProviderExecutor` 必须失败。
- `event_stream_root` / `artifact_root` 缺失、为空、绝对路径越界、指向 symlink escape（符号链接逃逸）或不可创建时失败。
- `default_tools` 缺 `submit_result` 时失败。
- `budget_profiles` 缺少 role slot 引用的 `budget_profile_ref`、`budget_caps` 缺失、或 resolved budget（解析预算）超过 caps 时失败。
- command timeout / output bytes 缺失或非正数时失败。
- network default 必须为 `deny`；允许网络必须写显式 allow rule（允许规则）。
- `dependency.contract_lock_ref` 缺失、文件缺失、hash mismatch（哈希不匹配）或字段集合不匹配时失败。
- `BOARDROOM_ATOMIC_AGENT_PATH` 指向不存在路径、`.worktrees/atomic-agent` 历史探索副本或不可审计路径时失败。
- `execution_policy.max_retries` 为负数、`retry_on_provider_timeout=true` 但未声明幂等策略、或 retry（重试）发生在已有 workspace mutation 后时失败。
- `concurrency.mode` 首版只能是 `serial_per_workspace`；同一 workspace 已有运行锁时必须拒绝并报告冲突。

### 2. `config/boardroom-providers.example.yaml`

职责：定义 OpenAI-compatible provider profiles（OpenAI 兼容供应商配置档）和真实请求参数。首版 provider type 只能是 `openai_compatible`。

```yaml
version: 1
providers:
  - provider_profile_id: provider.openai-compatible.primary
    provider_type: openai_compatible
    provider_label: truerealbill-openai-compatible
    base_url: https://api.truerealbill.com/v1
    api_key_env: OPENAI_API_KEY
    model: gpt-5.5
    context_window_tokens: 400000
    max_output_tokens: 128000
    stream_idle_timeout_seconds: 120
    total_timeout_seconds: 600
    reasoning_effort: high
    temperature: null
    top_p: null
    presence_penalty: null
    frequency_penalty: null
    seed: null
    stop: null
    response_format: null
    stream_options: null
    service_tier: null
    user: boardroom-os
  - provider_profile_id: provider.openai-compatible.fast-worker
    provider_type: openai_compatible
    provider_label: fast-worker-openai-compatible
    base_url: https://api.truerealbill.com/v1
    api_key_env: OPENAI_API_KEY
    model: gpt-5.5-fast
    context_window_tokens: 400000
    max_output_tokens: 64000
    stream_idle_timeout_seconds: 90
    total_timeout_seconds: 420
    reasoning_effort: medium
```

Fail-closed 要求：

- `provider_type` 不是 `openai_compatible` 时失败。
- `api_key_env` 缺失、为空或对应环境变量为空时失败。
- `base_url`、`model`、`context_window_tokens`、`max_output_tokens`、`stream_idle_timeout_seconds`、`total_timeout_seconds` 缺失时失败。
- timeout 非有限正数、stream idle timeout 大于 total timeout 时失败。
- `reasoning_effort` 若提供，必须属于 atomic-agent 当前允许集合：`none`、`minimal`、`low`、`medium`、`high`、`xhigh`。
- `stop` 若提供，必须是非空字符串数组。
- `response_format` / `stream_options` 若提供，必须是 JSON object（JSON 对象）。
- provider profile 不得包含 raw API key（原始密钥）；审计输出只能包含 `api_key_env` 或 redacted marker（脱敏标记）。

### 3. `config/boardroom-roles.example.yaml`

职责：定义 role slot（角色席位）如何绑定 provider/model/skill（供应商/模型/技能）能力。roles.yaml 是 Boardroom role layer（角色层）的配置，不重复 provider transport 参数。

```yaml
version: 1
role_slots:
  - seat_ref: seat.worker.implementation
    role_profile_ref: role.worker.implementation
    role_category: worker
    model_execution_profile_id: model-profile.worker.implementation.primary
    provider_profile_ref: provider.openai-compatible.primary
    skill_refs:
      - skill.filesystem.patch
      - skill.command.test
    default_tools:
      - list_files
      - read_file
      - search_files
      - write_file
      - apply_patch
      - run_command
      - submit_result
    budget_profile_ref: worker.implementation.default
    budgets_override:
      max_steps: 128
      max_wall_seconds: 5400
  - seat_ref: seat.worker.fast-fix
    role_profile_ref: role.worker.implementation
    role_category: worker
    model_execution_profile_id: model-profile.worker.fast-fix
    provider_profile_ref: provider.openai-compatible.fast-worker
    skill_refs:
      - skill.filesystem.patch
      - skill.command.test
    default_tools:
      - read_file
      - apply_patch
      - run_command
      - submit_result
    budget_profile_ref: atomic.proving.minimal
    budgets_override:
      max_steps: 48
      max_wall_seconds: 1800
```

Fail-closed 要求：

- `provider_profile_ref` 必须存在于 providers.yaml。
- `model_execution_profile_id` 必须唯一，且编译出的 `ModelExecutionProfile`（模型执行配置）与 provider profile 的 provider/model/reasoning/context window 字段一致。
- role slot 不得内联 `base_url`、`api_key_env`、`model`、`temperature` 等 provider transport 参数。
- implementation role slot 必须启用 mutating filesystem tool（可变更文件系统工具）和 `run_command`。
- `skill_refs` 缺失或为空时失败；未知 skill ref 必须失败。
- `budget_profile_ref` 必须存在于 runtime.yaml 的 `budget_profiles`。
- budgets override（预算覆盖）只能覆盖 budget profile 中已定义字段，不能引入未知预算键，且解析后不得超过 `budget_caps`。

### 4. `.env.template` / `.env.example`

新结构示例：

```text
BOARDROOM_RUNTIME_CONFIG=config/boardroom-runtime.example.yaml
BOARDROOM_PROVIDERS_CONFIG=config/boardroom-providers.example.yaml
BOARDROOM_ROLES_CONFIG=config/boardroom-roles.example.yaml
OPENAI_API_KEY=
BOARDROOM_ATOMIC_AGENT_PATH=../atomic-agent
BOARDROOM_EVIDENCE_ROOT=.evidence
```

禁止继续保留：

- `BOARDROOM_OPENAI_MODEL`
- `BOARDROOM_OPENAI_API_PROTOCOL`
- `BOARDROOM_OPENAI_REASONING_EFFORT`
- `BOARDROOM_OPENAI_TEXT_VERBOSITY`
- `BOARDROOM_OPENAI_MAX_OUTPUT_TOKENS`
- `BOARDROOM_OPENAI_TIMEOUT_SECONDS`
- `BOARDROOM_OPENAI_CONTEXT_WINDOW`
- `BOARDROOM_OPENAI_MAX_RETRIES`
- `BOARDROOM_OPENAI_SYSTEM_INSTRUCTIONS`

这些字段必须迁移到 providers.yaml 或 runtime.yaml。若运行时同时发现新 config path 和旧 `BOARDROOM_OPENAI_*` 模型参数，应 fail closed，提示旧 `.env` 结构已废弃，而不是静默以某一边为准。预算参数同样不得进入 `.env`：`BOARDROOM_ATOMIC_MAX_STEPS`、`BOARDROOM_ATOMIC_WALL_TIME_SECONDS` 或类似环境变量必须被视为 stale execution config（过期执行配置）并失败；人为调参只能通过 runtime.yaml / roles.yaml 的 budget profiles、caps 和 overrides 完成。

## 请求体编译设计

V2-090G 的 `AtomicInvocationCompiler` 当前只从 `ExecutionPackage` 和少量构造参数生成 `AgentInvocation`。V2-090H 必须扩展为显式消费：

```text
ExecutionPackage
+ BoardroomRuntimeConfig（运行时配置）
+ ProviderProfileConfig（供应商配置）
+ RoleSlotConfig（角色席位配置）
+ AtomicExecutionPaths（原子执行路径）
+ ResolvedAgentExecutionBudget（解析后智能体执行预算）
+ ResolvedAtomicToolPolicy（解析后原子工具策略）
-> atomic_agent.models.AgentInvocation
+ OpenAICompatibleProviderOptions
+ AtomicExecutionRequest audit snapshot（原子执行请求审计快照）
```

字段映射必须如下：

| 输入 | 输出 | 规则 |
|---|---|---|
| `execution_package.execution_package_id` | `invocation_id` | 稳定前缀 `atomic-invocation.`，不得随机。 |
| `execution_package.objective` + constraints + evidence obligations | `task` | 面向 agent 的任务说明；包含 acceptance refs / source surfaces / required outputs；不包含 chain-of-thought（思维链）。 |
| runtime workspace root | `workspace_root` | 必须是 generated project package workspace（生成项目包工作区）中的受控路径。 |
| `execution_package.allowed_write_set` | `allowed_write_set` | 只传相对路径；禁止绝对路径、Windows 盘符、`..` 和 symlink escape。 |
| `AtomicToolPolicyResolver` 输出 | `tools` | 从 runtime default tools、role slot tools、`ModelExecutionProfile.tool_permissions`、skill refs 和 evidence requirements 交叉解析；implementation ticket 必须包含 `submit_result`、需要命令证据时必须有 `run_command`、需要写入时必须有 mutating filesystem tool。 |
| runtime policy + `declared_command_ids_from_execution_package` | `permission_policy` | 必须含 `policy_ref`；commands 只能来自 `ExecutionPackage.commands` 的 `command_id` allow-list；network default deny。 |
| provider config | `provider_profile` | 使用 `OpenAICompatibleProviderOptions.to_provider_profile()` 生成脱敏审计画像；不得含 raw API key。 |
| `ResolvedAgentExecutionBudget` | `budgets` | 来自 runtime `budget_profiles` + role `budgets_override` + ticket-specific override（任务级覆盖，如已由治理编译）并受 `budget_caps` 限制；必须完整包含 `max_steps`、`max_parse_failures`、`max_observation_chars`、`max_wall_seconds`。 |
| evidence obligations + required outputs | `output_requirements` | 必须要求 event stream、tool attempts、workspace mutations、artifacts、command evidence、source lineage。 |
| `RolePromptHook` snapshot | `role_context` | 包含 hook ref/version/hash 和 prompt text snapshot。 |
| role slot skill refs | `skill_context` | 包含 resolved skill refs、allowed tool classes、audit requirements；未知 skill 失败。 |
| `context_refs` / `allowed_read_refs` | `initial_files` | 只放可审计相对引用，不读取旧实现。 |
| package/ticket/seat/config refs | `metadata` | 包含 execution package ref、ticket ref、seat ref、graph version、acceptance refs、source surface refs、runtime config hash、providers config hash、roles config hash、budget_profile_ref、resolved_budget_hash、resolved_tool_policy_hash。 |

### Budget resolution（预算解析）

预算是人为设定的重要执行策略，必须参数化、可审计、可重放。`.env` 不得承载预算；YAML 是人为配置源，`ExecutionPackage` 或 `AtomicExecutionRequest` 必须保存 resolved snapshot（解析后快照）。

解析顺序：

```text
runtime.budget_profiles[role_slot.budget_profile_ref]
  + role_slot.budgets_override
  + ticket_budget_override（如 ExecutionPackageCompiler 后续引入任务级覆盖）
  -> ResolvedAgentExecutionBudget
  -> validate <= runtime.budget_caps
  -> AgentInvocation.budgets + metadata.resolved_budget_hash
```

`ResolvedAgentExecutionBudget` 至少包含：

```text
max_steps
max_parse_failures
max_observation_chars
max_wall_seconds
budget_profile_ref
resolved_from_refs
resolved_budget_hash
```

主路径不得依赖 `AtomicInvocationCompiler.__init__(max_steps=..., wall_time_seconds=...)` 这类构造器默认值。若为了 V2-090G regression（回归）保留旧 `compile()`，必须明确标记为 legacy regression helper（遗留回归辅助），V2-090H 主路径只能走 config-aware compiler（配置感知编译器）。

### Tool policy resolution（工具策略解析）

工具集不得由 `enabled_tools` 构造器默认值决定。V2-090H 必须新增 `AtomicToolPolicyResolver`（原子工具策略解析器），按以下输入解析：

```text
runtime.default_tools
∩ role_slot.default_tools
∩ tools derived from ExecutionPackage.model_execution_profile.tool_permissions
∩ tools allowed by role_slot.skill_refs
+ runtime.required_tools
+ tools required by evidence obligations
```

`tool_permissions` 的首版映射：

```text
filesystem.read    -> list_files, read_file, search_files
filesystem.write   -> write_file, apply_patch
command.execute    -> run_command
network.fetch      -> web_fetch
```

Fail-closed 规则：未知 `tool_permission`、role slot 请求 runtime 未允许的工具、skill ref 不支持该工具、需要 command evidence 却无 `run_command`、需要 workspace mutation 却无 `write_file` 或 `apply_patch`、缺 `submit_result`，均失败。

### Declared command ids（声明命令标识）

`AtomicAgentResultValidator` 的 `declared_command_ids` 必须由 `ExecutionPackage.commands` 单一来源提取，不得由 config、event stream 或 provider 输出反推。新增 helper：

```python
def declared_command_ids_from_execution_package(
    execution_package: ExecutionPackage,
) -> tuple[str, ...]:
    command_ids = tuple(command.command_id.value for command in execution_package.commands)
    if not command_ids:
        raise ValueError("execution_package.commands must declare at least one command")
    if len(set(command_ids)) != len(command_ids):
        raise ValueError("execution_package.commands contains duplicate command_id")
    return command_ids
```

需要 command evidence 的 implementation ticket 若 `ExecutionPackage.commands` 为空必须失败；event stream 中任何 `command.completed.command_id` 不在该 tuple 内必须失败。

### 必须禁止的编译行为

- 不得把 `.env` 中旧模型参数和 providers.yaml 混合成配置。
- 不得在缺 provider profile 时回退到 `OPENAI_BASE_URL` 或默认 model。
- 不得在 role slot 缺 provider binding（供应商绑定）时使用第一个 provider profile。
- 不得在 budgets 缺字段时补构造器默认值；预算只能来自 runtime.yaml `budget_profiles`、roles.yaml `budgets_override` 和已审计 ticket override，并进入 config hash / resolved budget hash。
- 不得从 `.env` 读取预算或工具集参数。
- 不得把 command argv（命令参数）传成 shell string（shell 字符串）。
- 不得让 unsupported request params（不支持的请求参数）穿透到 `OpenAICompatibleProviderOptions`。
- 不得从 atomic-agent event stream 或 result summary 反推 declared command ids。
- 不得把 `AgentRunResult.status == completed` 编译成 ticket completed metadata（任务完成元数据）。

## Atomic runtime factory（原子运行时工厂）设计

V2-090H 需要新增 Boardroom 侧 runtime factory（运行时工厂），把配置编译为 atomic-agent 运行依赖。

建议模块：`src/boardroom_os/execution/atomic_executor.py`。

核心对象：

- `BoardroomRuntimeConfig`（Boardroom 运行时配置）
- `ProviderProfileConfig`（供应商配置档）
- `RoleSlotConfig`（角色席位配置）
- `AtomicExecutionRequest`（原子执行请求）
- `AtomicExecutionResult`（原子执行结果）
- `AtomicAgentRuntimeFactory`（原子智能体运行时工厂）
- `AtomicAgentExecutor`（原子智能体执行器）

运行时工厂必须构造：

- `WorkspacePathGuard`（工作区路径保护器）
- `FilesystemTools`（文件系统工具）
- `CommandPolicy` / `CommandTools`（命令策略/命令工具）
- `NetworkPolicy` / `WebFetchTools`（网络策略/网页抓取工具，默认禁用或 deny）
- `ArtifactWriter`（产物写入器）
- `EventRecorder`（事件记录器）
- `OpenAICompatibleProviderAdapter`（OpenAI 兼容供应商适配器）
- `AgentLoop` + `BoardroomAgentRuntimePortAdapter`（智能体循环 + Boardroom 运行端口适配器）

Boardroom OS 应调用 `AtomicAgentPackageAdapter.invoke(invocation)`，而不是直接依赖 atomic-agent 内部 `AgentLoop` 成为治理事实源。工厂可在 Boardroom 边界构造 atomic-agent public runner（公开运行器）并包装为 `AgentRuntimePort`，但证据验收仍必须走 `AtomicAgentResultValidator` 和 `AtomicResultProjector`。

## AtomicAgentExecutionPolicy（原子智能体执行策略）

V2-090H 必须显式建模 execution policy（执行策略），不能只把 `budgets.max_wall_seconds` 当成全部超时语义。首版策略：

```text
wall_time_seconds: 900
retry_on_provider_timeout: false
retry_on_runtime_crash: true
max_retries: 1
interrupt_grace_period_seconds: 30
retry_requires_no_workspace_mutation: true
```

语义：

- provider timeout（模型供应商超时）默认不重试，避免重复真实 provider 调用和重复写入。
- runtime crash（运行时崩溃）最多 fresh-run retry（新运行重试）一次，且前一次必须没有 workspace mutation。
- 每次 retry 必须使用新的 `run_id`、新的 event stream path（事件流路径）和新的 artifact path（产物路径），原失败事实必须保留。
- in-process `AgentLoop`（进程内智能体循环）通过 `max_wall_seconds`、provider total/idle timeout 和 fail-closed result 终止；只有 proving helper（证明辅助脚本）作为 subprocess（子进程）运行时才需要外层 terminate/kill grace period（终止/强杀宽限期）。
- `failed`、`interrupted`、`requires_approval` 均不得生成 successful `WorkProductSubmission`（成功工作产物提交）。

## Event stream canonical format（事件流规范格式）

Boardroom validator（校验器）必须把 atomic-agent 事件流格式作为显式契约检查。当前 active format 为：

```text
event_stream_format = jsonl-utf8-lf-canonical-json-v1
line_encoding = UTF-8
line_separator = LF (\n)

event_json = json.dumps(event.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
event_hash = sha256(json.dumps(event_without_hash, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))
events_hash = sha256(raw_event_stream_bytes)
```

必须拒绝：

- CRLF（`\r\n`）或混合换行。
- 非 UTF-8。
- 空行。
- 可 parse 但不是 canonical serialization（规范序列化）的 JSON line。
- 单事件 `event_hash` 与 canonical event 不一致。
- stream bytes hash 与 `AgentRunResult.events_hash` 不一致。

## Concurrency and workspace isolation（并发与工作区隔离）

V2-090H 首版不实现并发 atomic execution（原子执行并发）、disjoint write-set parallelism（不相交写入集合并行）、merge/rebase（合并/变基）或 conflict resolution（冲突解决）。首版规则：

- 每个 atomic run 必须使用 run-scoped event/artifact directories（按运行隔离的事件/产物目录）。
- minimal proving ticket 使用独立 scratch workspace（临时证明工作区）。
- 同一 generated package workspace（生成包工作区）同一时间只允许一个 atomic execution。
- 若检测到同 workspace lock（工作区锁）已存在，必须 fail closed，不等待、不抢占、不合并。
- 后续若要支持并发，必须单独工作包设计 write-set conflict detection（写集合冲突检测）、event stream merge（事件流合并）和 SourceInventory lineage merge（源码清单来源链合并）。

## Error diagnostics and secret hygiene（错误诊断与密钥卫生）

V2-090H 的 fail-closed error（失败关闭错误）必须对人类可诊断，但不得泄露 secret（密钥）。错误消息应包含：

- 失败 path（路径）或 command_id（命令标识）。
- 相关 policy_ref（策略引用）或 provider_profile_ref（供应商配置档引用）。
- allowed_write_set（允许写入集合）摘要。
- contract hash mismatch（契约哈希不匹配）时的 expected/actual hash。

错误消息不得包含：

- API key。
- 完整 provider raw output（模型供应商原始输出）。
- 未脱敏 environment variables（环境变量）。

## ProviderAttempt（模型调用尝试记录）来源链要求

V2-090H 必须修正“ProviderAttempt 只来自 Boardroom 单次 OpenAIProviderTransport”的旧语义。

可接受来源：

1. 从 atomic-agent event stream 的 `provider.turn.started` / `provider.turn.completed` / `provider.turn.failed` 事件投影出 provider attempt draft（模型调用尝试草稿）。
2. draft 必须绑定：
   - `input_package_ref = ExecutionPackageRef(execution_package_id)`
   - `seat_ref`
   - `role_prompt_hook_ref/version/sha256`
   - `provider` / `model` / `reasoning_effort` 来自 selected provider profile（选中供应商配置档）与 execution package model execution profile（执行包模型配置）的一致交叉校验
   - raw/parsed output artifact refs（原始/解析输出产物引用）来自 provider turn artifact（模型轮次产物）
3. 如果 atomic-agent event stream 无 provider turn facts，implementation ticket 必须失败；不能用 invocation provider_profile 或 final summary 补造 provider attempt。

后续 `AtomicResultProjector` 可继续接收 `ProviderAttempt`，但 V2-090H executor 必须负责确保该 attempt 来自 atomic run facts（原子运行事实），而不是旧 `ProviderExecutor`。

## 最小 atomic implementation ticket（原子实施任务）证明口径

V2-090H happy path 不直接重建 tiny-fullstack golden sample。它应构造一个可控、低风险、真实 provider-backed 的最小 implementation ticket，例如：

- workspace：pytest `tmp_path` 下的 generated project package scratch（临时生成项目包工作区）。
- allowed_write_set：`work/` 或 `src/` 下单一文件/目录。
- declared command：稳定命令 `check-output`，使用绝对 Python executable（Python 可执行文件）+ 参数 tuple（参数元组），读取 agent 写入文件并校验内容；禁止自由 shell。
- task：要求 agent 通过 `write_file` 写入固定语义文件，再用 `run_command` 执行 `check-output`，最后 `submit_result`。
- provider：真实 OpenAI-compatible profile，由 providers.yaml + `OPENAI_API_KEY` 编译为 `OpenAICompatibleProviderOptions`。
- evidence：event stream 包含 provider turn、tool attempt、workspace mutation、command.completed、result.submitted、run.completed；Boardroom validator/projector 产出 WorkProductSubmission 和 source lineage input。

该 proving（证明）只证明 atomic-agent executor 主路径和证据链可闭合；不证明 generated project final closeout（生成项目最终收尾）已通过。

## Fail-closed 矩阵

### 配置负例

- 缺 `BOARDROOM_RUNTIME_CONFIG` / `BOARDROOM_PROVIDERS_CONFIG` / `BOARDROOM_ROLES_CONFIG`：失败。
- 配置文件不存在、为空、不是 YAML mapping（YAML 映射）：失败。
- 配置含未知顶层字段：失败。
- `.env` 同时出现新 config path 与旧 `BOARDROOM_OPENAI_*` 模型参数：失败。
- providers.yaml 缺选中的 `provider_profile_ref`：失败。
- roles.yaml role slot 引用未知 provider profile：失败。
- roles.yaml 内联 provider transport 参数：失败。
- runtime budgets 缺 active contract 必填字段：失败。
- unsupported OpenAI-compatible request param：失败。
- atomic-agent contract lock 缺失、hash mismatch 或字段快照不一致：失败。
- `BOARDROOM_ATOMIC_AGENT_PATH` 缺失且默认路径不存在：失败。

### 编译负例

- implementation ticket 被路由到 `ProviderExecutor.execute`：失败。
- 缺 active `ExecutionPackage`：失败。
- `allowed_write_set` 为空、绝对路径、Windows 盘符或 `..`：失败。
- `commands[*].command` 编译成 shell string：失败。
- `permission_policy.policy_ref` 缺失：失败。
- `tools` 缺 `submit_result` / `run_command` / mutating filesystem tool：失败。
- provider profile 与 `ExecutionPackage.model_execution_profile` 不一致：失败。
- role slot seat_ref 与 `ExecutionPackage.seat_ref` 不一致：失败。

### 执行负例

- atomic-agent package 不可 import：失败。
- `AgentRuntimePort` 缺失或返回非 `AgentRunResult`：失败。
- fake provider transport 被用于 real executor happy path：失败。
- real provider stream 超时、空输出、解析失败超过预算：失败，且必须记录失败事实。
- `run_command` 请求未声明 command_id：失败。
- 网络请求目标未被 allow rule 授权：失败。

### 结果负例

- `AgentRunResult.status != completed`：不得生成 successful WorkProduct。
- 缺 event stream / events_hash / tool_attempts / workspace_mutations / artifacts：失败。
- event stream hash mismatch 或 event hash chain mismatch：失败。
- 缺 provider turn facts：implementation evidence 失败。
- 缺 `command.completed` 或 command_id 未声明：失败。
- workspace mutation 越过 allowed_write_set：失败。
- source lineage input 为空：失败。
- result 或 event stream 含 `ticket_completed`、`closeout_committed`、`evidence_verified`、`source_inventory_accepted` 等治理字段：失败。
- `AgentRunResult.status == completed` 直接触发 ticket reducer 完成：失败。
- 同一 workspace 并发运行或锁冲突：失败。
- event stream 含 CRLF、非 UTF-8、空行或 non-canonical JSON：失败。
- retry 发生在已有 workspace mutation 后：失败。

## 产出文件

V2-090H 实施计划应产出或修改：

- `config/boardroom-runtime.example.yaml`
- `config/boardroom-providers.example.yaml`
- `config/boardroom-roles.example.yaml`
- `doc/06-reference/atomic-agent-contract-lock.md`
- `.env.template`
- `.env.example`
- `src/boardroom_os/config/boardroom.py` 或同等配置模块
- `src/boardroom_os/execution/atomic_executor.py`
- `src/boardroom_os/execution/atomic_agent.py`（扩展 compiler/projector，如需要）
- `src/boardroom_os/execution/__init__.py`
- `tests/config/test_boardroom_config.py`
- `tests/negative/test_boardroom_config_fail_closed.py`
- `tests/execution/test_atomic_agent_executor.py`
- `tests/negative/test_atomic_agent_executor_fail_closed.py`
- `tests/proving/test_tiny_atomic_agent_executor.py`
- `scripts/run_tiny_atomic_agent_executor.py`（仅作为 proving helper，不能替代正式 API）
- `README.md`
- `doc/04-implementation/backlog.md`
- `doc/04-implementation/acceptance-criteria.md`
- `doc/04-implementation/INDEX.md`

## 验收标准

V2-090H 完成时必须证明：

1. Boardroom OS 的 implementation ticket 主执行路径可明确切换到 atomic-agent executor。
2. `ProviderExecutor.execute` 不能再为 implementation category ticket 提供成功证据。
3. 三文件配置可被 fail-closed 加载、交叉引用校验并编译为 `AgentInvocation` + `OpenAICompatibleProviderOptions`。
4. `.env.template` / `.env.example` 不再承载 provider/model 参数，只保留 config paths、secrets 和 bootstrap/local paths。
5. 首版 provider 只支持 OpenAI-compatible profiles，unsupported provider type 失败。
6. `BOARDROOM_ATOMIC_AGENT_PATH`、contract lock manifest、Python 3.11+ 和 atomic-agent active contract hash 均可审计且 fail closed。
7. `AtomicAgentExecutionPolicy` 明确 timeout、retry、interrupted/failed/requires_approval 状态语义，且 retry 不会覆盖已有 workspace mutation。
8. budget profiles、role overrides、resolved budget snapshot 和 caps 均可审计；`.env` 不承载预算参数。
9. enabled tools 由 `AtomicToolPolicyResolver` 解析，不由 compiler 构造器默认值决定；declared command ids 只来自 `ExecutionPackage.commands`。
10. Event stream canonical format 被程序化校验，CRLF / noncanonical JSONL / hash mismatch 均失败。
11. 首版强制 `serial_per_workspace`，run-scoped event/artifact roots 可审计。
12. 最小 atomic implementation ticket 由真实 provider-backed atomic-agent executor 完成，产生 event stream、workspace mutation、command evidence、provider turn facts 和 source lineage input。
13. fake provider transport、fallback artifact、synthetic verification 或 single-shot JSON source delivery 不能满足 V2-090H happy path。
14. atomic-agent completed 不直接触发 `TICKET_COMPLETED` 或 closeout passed。
15. V2-090F 仍保持 BLOCKED，等待人工评审 V2-090H 真实执行证据后再决定是否恢复。

## 自审结果

- Placeholder scan（占位符扫描）：未保留 TBD / TODO / “后续补齐” 作为需求；未知项均转化为非目标、首版限制或 fail-closed 要求。
- Contract consistency（契约一致性）：字段基于 `../atomic-agent/src/atomic_agent/models.py`、`agent_loop.py`、`providers/openai_compatible.py` 的当前 active contract；没有把 `provider_profile` 误写成完整 provider runtime config。
- Boundary check（边界检查）：Boardroom 保留 AcceptanceContract、PackageContract、reducer、EvidenceVerifier、Checker、CloseoutGate 权威；atomic-agent 只负责受控执行和事实输出。
- Config source-of-truth check（配置权威源检查）：provider/model 参数只在 providers.yaml；role slot 只引用 provider profile；`.env` 只放路径和密钥，避免 second source of truth。
- Scope check（范围检查）：本文是 V2-090H spec，不实施代码，不恢复 V2-090F，不重建 golden sample。
