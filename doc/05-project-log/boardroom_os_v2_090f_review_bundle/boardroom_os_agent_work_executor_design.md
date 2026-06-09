# Boardroom OS 小型通用 AgentWorkExecutor 设计草案

生成日期：2026-06-03  
目标分支：`rebuild/v2-clean-foundation`

---

## 1. 设计目标

实现一个最小但真正通用的 agent 执行模块，使 Boardroom OS 的 agent team 从“provider chat 文本输出”升级为“受控 workspace 内的多步执行循环”。

目标能力：

1. provider/model 可切换  
   具体模型来自 `ModelExecutionProfile.provider` 和 `ModelExecutionProfile.model`，可支持 OpenAI-compatible、Anthropic-compatible、local、future provider。

2. role hook 可加载  
   每个 loop 根据 `ExecutionPackage.role_prompt_hook`、`RoleProfile`、`SkillBinding` 组合系统指令、角色边界和工具约束。

3. skill 可加载  
   Skill 不只是 prompt 文本，而要解析为：
   - 可注入上下文片段；
   - 可启用工具集合；
   - 可启用 MCP interface 或本地 tool adapter；
   - 输入要求和输出效果；
   - 审计 metadata。

4. workspace 可读写  
   agent 可以读取 package/workspace 文件，生成 patch，写入 allowed paths，查看 diff/hash。

5. 命令可运行  
   agent 可以运行 PackageContract/ExecutionPackage 声明的命令，拿到 stdout/stderr/exit code 作为 observation。

6. 可迭代修复  
   agent loop 支持：计划 -> 读文件 -> 写文件 -> 运行测试 -> 观察失败 -> 修复 -> 再测试 -> submit。

7. 证据可追溯  
   每次 provider turn、tool call、file mutation、command run 都是可重放/可审计事实；最终 closeout 仍由现有 gate/reducer/checker 判断。

---

## 2. 非目标

第一阶段不做：

- 不做完全通用多 agent planner。
- 不做长期记忆或分布式 agent runtime。
- 不依赖 provider 原生 tool-calling 作为唯一路径。
- 不让 agent 自己发 `TICKET_COMPLETED` / `CLOSEOUT_COMMITTED`。
- 不把 Codex/Claude Code 直接嵌入核心事实链。
- 不允许自由 shell。只能运行 PackageContract 声明的 command_id，或安全白名单工具。

---

## 3. 模块位置建议

```text
src/boardroom_os/execution/
  agent_work_executor.py        # loop 主体
  agent_actions.py              # Boardroom AgentAction schema
  workspace_tools.py            # read/list/write/apply_patch guards
  tool_attempt.py               # ToolAttempt / ToolResult evidence model
  workspace_mutation.py         # WorkspaceMutation / file hash / diff model
  agent_transcript.py           # loop transcript and replay bundle
  provider_turn.py              # ProviderTurnRequest/Response normalization
```

必要时新增：

```text
src/boardroom_os/tools/
  registry.py
  filesystem.py
  patch.py
  command.py
  service.py
  mcp.py

src/boardroom_os/agents/
  skill_loader.py
  role_runtime.py
```

---

## 4. 核心类型草案

### 4.1 AgentWorkExecutorInput

```python
class AgentWorkExecutorInput(BaseModel):
    execution_package: ExecutionPackage
    package_contract: PackageContract
    agent_team_projection: AgentTeamProjection
    role_profile: RoleProfile
    model_execution_profile: ModelExecutionProfile
    role_prompt_hook: RolePromptHook
    skill_bindings: tuple[SkillBinding, ...]
    provider_adapter: ProviderTransport
    workspace_root: Path
    project_ref: ProjectRef
    runtime_actor_ref: ActorRef
    runner_ref: RunnerRef
    environment_profile_ref: EnvironmentProfileRef
    workspace_snapshot_ref: WorkspaceSnapshotRef
    first_fact_graph_version: int
    max_steps: int = 24
    max_wall_seconds: float = 600
    max_observation_chars: int = 12000
```

### 4.2 AgentAction

采用 provider-agnostic JSON 协议起步：

```json
{
  "action_id": "step-0004",
  "action": "apply_patch",
  "path": "backend/app.py",
  "patch": "...",
  "reason_summary": "Add HTTP DELETE route and /health endpoint."
}
```

动作集合第一阶段只保留最小闭环：

| Action | 用途 | 关键 guard |
|---|---|---|
| `list_files` | 枚举 workspace/package | 只能在 workspace root 内 |
| `read_file` | 读取上下文 | 受 allowed read scope / package root 限制 |
| `write_file` | 写完整文件 | path 必须在 allowed_write_set |
| `apply_patch` | 应用局部 patch | path 必须在 allowed_write_set；patch 后 hash 记录 |
| `run_command` | 运行声明命令 | command_id 必须在 ExecutionPackage.commands / PackageContract.commands |
| `submit_work_product` | 提交结果摘要和 produced files/evidence refs | 只能在至少一次 workspace mutation 后提交 |
| `request_stop` | 超限/无法继续时 fail closed | 记录 blocker，不完成 ticket |

第二阶段可加：

- `run_service`
- `http_probe`
- `mcp_call`
- `spawn_subagent`
- `review_diff`
- `load_skill_file`

### 4.3 AgentStep

```python
class AgentStep(BaseModel):
    step_index: int
    provider_attempt_ref: ProviderAttemptRef
    action: AgentAction
    tool_attempt_ref: ToolAttemptRef | None
    observation_ref: ObservationRef | None
    workspace_mutation_refs: tuple[WorkspaceMutationRef, ...]
    verification_run_refs: tuple[VerificationRunRef, ...]
```

### 4.4 AgentWorkResult

```python
class AgentWorkResult(BaseModel):
    provider_attempts: tuple[ProviderAttempt, ...]
    tool_attempts: tuple[ToolAttempt, ...]
    workspace_mutations: tuple[WorkspaceMutation, ...]
    verification_runs: tuple[VerificationRun, ...]
    work_product_submission: WorkProductSubmission | None
    events: tuple[EventRecord, ...]
    transcript_ref: AgentTranscriptRef
    stdout_by_verification_run: dict[VerificationRunRef, str]
    stderr_by_verification_run: dict[VerificationRunRef, str]
```

---

## 5. Loop 流程

```text
1. Resolve runtime seat
2. Load RoleProfile + RolePromptHook
3. Load SkillBindings for role/ticket type
4. Build tool registry from:
   - ModelExecutionProfile.tool_permissions
   - SkillBinding.mcp_interface_refs
   - ExecutionPackage.allowed_write_set
   - PackageContract.commands
5. Create workspace session
6. Build first prompt:
   - role hook
   - ExecutionPackage facts
   - PackageContract command list
   - allowed_write_set
   - required outputs/evidence obligations
   - tool protocol
   - current workspace inventory
7. Repeat until max_steps:
   a. provider_adapter.invoke_turn(...)
   b. store ProviderAttempt/ProviderTurn artifact
   c. parse AgentAction JSON
   d. validate action against policy
   e. execute tool
   f. record ToolAttempt / WorkspaceMutation / VerificationRun
   g. append observation to next prompt
   h. if submit_work_product and minimum evidence conditions satisfied:
      return result
8. Fail closed with incomplete AgentWorkResult
```

关键点：模型不需要原生 tool calling。即使 provider 只支持普通 chat text，也可要求其输出 Boardroom-defined JSON action。等核心 loop 稳定后，可在 adapter 层支持 OpenAI/Anthropic native tool calls，并归一化为同一个 `AgentAction`。

---

## 6. Tool guard 设计

### 6.1 路径守卫

所有路径必须：

- 是相对路径；
- 规范化后仍在 workspace root；
- 不包含 `..`；
- 不穿越 symlink；
- 写入路径必须属于 `ExecutionPackage.allowed_write_set`；
- package contract typed artifacts 如 `run-manifest.json`、`package-contract.json` 默认不可由 agent 手写，除非 package contract 明确允许。

### 6.2 命令守卫

`run_command` 只能接收 command_id，不能接收任意 shell string。执行器通过 command_id 查 `ExecutionPackage.commands` 和 `PackageContract.commands`，两者必须匹配后才调用现有 `CommandRunner`。

这样复用当前 `CommandRunner` 的真实执行和 VerificationRun 记录能力，同时避免 agent 获得自由 shell。

### 6.3 输出守卫

- stdout/stderr 截断后作为 observation。
- 完整 stdout/stderr 仍进入 artifact store/evidence store。
- 大文件读取需要分片。
- 不把 API keys/secrets 回传给 model。

### 6.4 迭代限制

- `max_steps`
- `max_wall_seconds`
- `max_file_bytes`
- `max_total_written_bytes`
- `max_command_runs`
- `max_failed_same_command_retries`
- provider token budget / compaction

超限后返回 fail-closed result，不造完成事件。

---

## 7. Evidence/Event 集成

新增或复用事件类型建议：

| Event | 用途 |
|---|---|
| `PROVIDER_ATTEMPT_RECORDED` | 每次模型 turn |
| `TOOL_ATTEMPT_RECORDED` | 每次 tool action |
| `COMMAND_RUN_RECORDED` | 每次 run_command |
| `WORKSPACE_MUTATION_RECORDED` | 每次 write/apply_patch |
| `WORK_PRODUCT_SUBMITTED` | agent 最终提交 |

当前 RuntimeEventBoundary 已允许 `TOOL_ATTEMPT_RECORDED`、`COMMAND_RUN_RECORDED`、`WORK_PRODUCT_SUBMITTED`，只需要补齐 ToolAttempt/WorkspaceMutation 的 payload model 和 projector。仍然不能 emit `TICKET_COMPLETED`。

WorkspaceMutation 应记录：

```python
class WorkspaceMutation(BaseModel):
    mutation_id: WorkspaceMutationRef
    tool_attempt_ref: ToolAttemptRef
    path: WorkspacePath
    mutation_kind: Literal["create", "modify", "delete"]
    before_sha256: str | None
    after_sha256: str | None
    diff_ref: ArtifactRef
    allowed_write_set_ref: str
    applied_at: datetime
```

SourceInventory 的 producer_attempt_ref 应指向造成该文件最终版本的 provider/tool lineage，而不是只指向一次 provider text artifact。

---

## 8. 与当前 tiny 090F 的替换方式

当前路线：

```text
build_tiny_provider_attempt_fixture
  -> RuntimeExecutor(command_ids=())
  -> OpenAIProviderTransport returns JSON files
  -> _source_delivery_files_from_provider
  -> _package_contents_with_generated_files
  -> write tmp package
  -> run tests / service probes
```

建议路线：

```text
build_tiny_agent_work_fixture
  -> AgentWorkExecutor(workspace_root=temp package root)
  -> agent loop writes files via write_file/apply_patch
  -> agent loop runs test-backend/test-integration
  -> agent loop observes failures and repairs
  -> submit_work_product
  -> package/evidence assembly consumes actual workspace tree + mutations + command runs
  -> closeout gate
```

第一阶段可只要求：

- backend ticket 能写 `backend/app.py`、`backend/db.py`；
- tests ticket 能写 `backend/tests/test_api.py`、`tests/integration/test_frontend_backend.py`；
- docs ticket 能写 README/AGENTS/docs；
- 每个 ticket 至少一次 real provider turn；
- 每个 source file 有 workspace mutation evidence；
- final tests/service probes 由 existing fixture/gate 继续验证。

---

## 9. Provider adapter 策略

### 阶段 1：纯文本 JSON action

适用于所有 chat provider。最小协议：

```json
{
  "action": "write_file",
  "path": "backend/app.py",
  "content": "...",
  "reason_summary": "Implement standard-library HTTP backend."
}
```

优点：

- provider-agnostic；
- 易测试；
- 无需依赖 OpenAI/Anthropic tool calling 差异；
- 与当前 OpenAIProviderTransport 改动较小。

缺点：

- 模型可能输出无效 JSON，需要 parser/retry/repair；
- tool schema 只能在 prompt 中约束，不如 native tool calling 强。

### 阶段 2：native tool calling adapter

为 OpenAI/Anthropic/Gemini 等 provider 增加 `ProviderTurn` 归一化：

```python
class ProviderTurnResponse(BaseModel):
    raw_output_ref: ProviderArtifactRef
    normalized_actions: tuple[AgentAction, ...]
    assistant_message: str | None
```

native tool calls 与 JSON text 都转成 `AgentAction`，执行器不关心 provider 差异。

### 阶段 3：外部 coding agent bridge

Codex/Claude Code 只作为外部工具：

```text
AgentAction: external_coding_agent_run
  -> ExternalCodingAgentTool
  -> collect diff, tests, logs
  -> import as WorkspaceMutation + CommandRun evidence
```

不能让外部 coding agent 绕过 Boardroom 的 allowed_write_set、source inventory、evidence verifier 和 closeout gate。

---

## 10. Skill 运行时设计

SkillBinding 当前包含：

- `skill_ref`
- `purpose`
- `skill_file_ref`
- `allowed_roles`
- `required_for_ticket_types`
- `capability_tags`
- `prompt_refs`
- `mcp_interface_refs`
- `input_requirements`
- `output_effects`

建议新增 `SkillRuntimeLoader`：

```python
class SkillRuntimeContext(BaseModel):
    skill_ref: SkillRef
    prompt_snippets: tuple[str, ...]
    tool_permissions: tuple[str, ...]
    mcp_interfaces: tuple[McpInterfaceDefinition, ...]
    input_requirements: tuple[str, ...]
    output_effects: tuple[str, ...]
    content_hashes: tuple[str, ...]
```

加载规则：

1. role 必须在 `allowed_roles`。
2. ticket type 必须匹配 `required_for_ticket_types` 或由 method profile 明确指定。
3. skill file hash 写入 provider prompt lineage。
4. skill 只能增加它声明的工具/MCP interface，不能无限扩权。
5. skill instructions 进入 system/developer prompt；tool schemas 进入 tool registry。

---

## 11. 应该自己实现，还是嵌入现成方案？

建议自己实现核心 executor，理由：

1. Boardroom 的价值是 contract/evidence/reducer/closeout，而现成框架通常把 trace/log 当 observability，不等价于 Boardroom 的 governance facts。
2. 当前项目必须 provider/model 可切换；直接依赖 Codex/Claude Code 会把模型、权限和工作目录语义绑死。
3. 当前项目已经有 CommandRunner、EvidenceVerifier、CloseoutGate，直接嵌入重型框架会形成两套状态机。
4. 自己实现的最小 JSON-action loop 只需几十个核心分支，足够满足 tiny 090F；后续可替换 provider turn adapter 或 tool backend。
5. 现成框架最适合被“包在 Boardroom tool boundary 里”，而不是成为 Boardroom runtime 的事实来源。

推荐决策：

| 方案 | 建议 | 用法 |
|---|---|---|
| 自研 AgentWorkExecutor | 第一优先 | Boardroom 的核心事实链 |
| OpenAI Agents SDK | 可参考/后续可选 adapter | 借鉴 loop、guardrails、sandbox agents；不要直接替代 evidence model |
| LangGraph | 可参考状态/持久化 | 如需长事务可作为 internal loop engine，但 events 要映射回 Boardroom |
| AutoGen | 不建议作为核心 | 多 agent 能力会重叠 Boardroom agent team |
| smolagents | 可做 prototype | 轻量，但安全和证据模型需重包 |
| Codex / Claude Code | 不建议作为核心 | 可作为 ExternalCodingAgentTool，导入 diff/evidence |
