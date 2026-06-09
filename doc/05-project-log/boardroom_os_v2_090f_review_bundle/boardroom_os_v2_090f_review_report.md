# Boardroom OS V2-090F / rebuild/v2-clean-foundation 深度复审报告

生成日期：2026-06-03  
审查对象：`yb3712590/boardroom-os` 的 `rebuild/v2-clean-foundation` 分支，最新可见 HEAD 为 `0a80ee3a77f8f12e57af7cc4e53d0811afc9f472`，提交主题为 `fix(v2-090f): 记录智能体循环缺口`。  
审查方法：通过 GitHub 连接器读取分支文档、运行时、provider、tiny proving fixtures、closeout/sample 构建链路和进程执行器；未在本地 clone 仓库，也未重跑 provider 集成测试。因此本报告判断基于静态审查和分支内已有测试/文档证据。

---

## 1. 总结判断

你的核心判断成立：当前 V2-090F 的失败不是单纯 provider 参数、上下文窗口、prompt wording、timeout 或 closeout gate 的局部问题，而是缺少“最基本的原子 agent work loop”。

当前系统已经搭出了较完整的治理/合约/证据/投影/closeout 框架，但真正执行实现工作的链路仍然是：

```text
ExecutionPackage
  -> ProviderExecutor.render_prompt(...)
  -> provider_adapter.invoke(...)
  -> OpenAI-compatible chat/responses API returns text
  -> store raw/parsed text artifacts
  -> build WorkProductSubmission from ProviderAttempt
```

这不是 autonomous agent execution。它没有在同一循环内读 workspace、写文件、运行声明命令、观察失败、修复代码、再运行验证并形成 tool/command/workspace mutation evidence。V2-090F 把“LLM 一次性返回 JSON 文件集合”当成“agent 完成实现”，因此 tiny fullstack 这种跨后端、前端、测试、服务启动、SQLite 持久化和 live blackbox 的任务会持续脆弱失败。

更精确地说，本项目并不是“完全没框架”。它有一个可用的治理内核：

- ExecutionPackage / PackageContract / EvidenceObligation / ProviderAttempt / VerificationRun / SourceInventory / CloseoutGate 等模型是有方向的。
- RuntimeExecutor 明确禁止 runtime 自行发出 `TICKET_COMPLETED` 等治理事件，这是正确边界。
- CommandRunner / ServiceRunner 已能执行声明命令并记录 stdout/stderr/exit。
- tiny closeout 链路已经能表达 run-manifest、service run、live blackbox、source lineage、process audit 等证据对象。

但缺少中间的“执行工作层”：`AgentWorkExecutor`。没有这个模块，ProviderAttempt 只能证明“模型被调用并返回文本”，不能证明“某个角色 agent 以受控权限对 workspace 进行实现工作并根据验证反馈迭代”。

---

## 2. 证据摘要

### 2.1 项目文档本身承认 V2 是干净地基，不是完整 agent runtime

README 明确将当前 V2 描述为 clean foundation/foundation-only，代码入口是 `src/boardroom_os/`，并强调 runtime 只能执行、记录、验证和投影事实，不能替代 governance；证据必须来自真实执行而非声明。  
来源：`README.md`，`AGENTS.md`，架构文档。参考：fileciteturn2file0L9-L16，fileciteturn2file0L24-L31，fileciteturn7file0L101-L118

`doc/04-implementation/backlog.md` 在最新批次中已经把 V2-090F 标为 BLOCKED，并直指问题：real provider-backed source delivery 仍是单次 LLM request returning JSON，缺少 AgentWorkExecutor / agent loop executor 的 workspace read/write、tool calls、command run、repair 和 evidence archive。  
来源：`doc/04-implementation/backlog.md`。参考：fileciteturn25file0L12-L23

### 2.2 ProviderExecutor 只是 prompt -> ProviderAttempt

`ProviderExecutor.execute` 的实际动作是：构造 context snapshot，渲染 prompt，创建 `ProviderRequest`，调用 `provider_adapter.invoke()`，验证返回的 ProviderAttempt 绑定关系，返回 prompt 与 provider attempt。它没有工具循环、没有 workspace mutation、没有 command feedback loop。  
来源：`src/boardroom_os/execution/provider_executor.py`。参考：fileciteturn27file0L61-L80，fileciteturn27file0L133-L151

Provider adapter protocol 也只有 `invoke(request) -> ProviderAttempt`；fake transport 只是构造 ProviderAttempt 和 artifact refs。  
来源：`src/boardroom_os/providers/adapter.py`。参考：fileciteturn28file0L86-L124

### 2.3 OpenAI adapter 是文本调用，不是 agent execution

`OpenAIProviderTransport.invoke()` 调用 Responses API 或 Chat Completions API，把返回文本写成 raw/parsed artifacts，然后返回 `ProviderAttempt`。Responses API 和 chat completions 的调用参数中没有 Boardroom 的 file tools、patch tools、command tools、workspace sandbox 或 role skill execution。  
来源：`src/boardroom_os/providers/openai_adapter.py`。参考：fileciteturn37file0L217-L259，fileciteturn37file0L284-L312，fileciteturn38file0L21-L36

### 2.4 RuntimeExecutor 是事件/命令外壳，不是 agent loop

`RuntimeExecutor.execute_package()` 先发 `EXECUTION_STARTED`，执行 provider，发 `PROVIDER_ATTEMPT_RECORDED`，成功后用 provider attempt 生成 work product 并发 `WORK_PRODUCT_SUBMITTED`，然后只对 `runtime_input.command_ids` 调用 `CommandRunner`。在 tiny provider attempt 链路里，传入的 `command_ids=()`，所以 provider 阶段没有任何验证命令参与反馈。  
来源：`src/boardroom_os/execution/runtime_executor.py`，`tests/proving/fixtures/tiny_provider_attempts.py`。参考：fileciteturn36file0L260-L362，fileciteturn34file0L18-L65

这是边界上正确但能力上不足：RuntimeExecutor 目前像“事实记录器 + 可选命令运行器”，不是“agent 工作执行器”。

### 2.5 tiny provider attempts 当前是“source delivery JSON”，不是 agent 实现

`tiny_source_delivery_system_instructions()` 要求 provider 返回 minified JSON：

```json
{"files":{"relative/path":"complete UTF-8 file content"}}
```

并要求 files 精确覆盖 allowed_write_set。该 prompt 虽然很长，但本质是要求 LLM 一次性吐完整文件内容。  
来源：`tests/proving/fixtures/tiny_provider_attempts.py`。参考：fileciteturn34file0L173-L250

`_execute_tiny_runtime_package_with_real_retries()` 的“重试”也只是再次调用 provider 并检查 parsed artifact 是否是合法文件 JSON；它没有把失败测试输出反馈给模型，也没有应用 patch 后运行命令。  
来源：`tests/proving/fixtures/tiny_provider_attempts.py`。参考：fileciteturn34file0L68-L112，fileciteturn34file0L128-L159

`_source_delivery_files_from_provider()` 从 provider parsed artifact 读取 JSON，并通过 `_extract_source_delivery_payload()` 检查文件路径是否在 allowed_write_set 里、内容是否非空、是否覆盖 expected paths。随后 `_package_contents_with_generated_files()` 加上 typed run-manifest/package-contract 并写入临时 package。  
来源：`tests/proving/fixtures/tiny_package_assembly.py`。参考：fileciteturn48file0L121-L155，fileciteturn48file0L190-L212，fileciteturn53file0L22-L51

这证明当前“实现”主要是 provider text artifact -> JSON files -> fixture 写包，而不是 agent 使用工具逐步构建项目。

### 2.6 项目已有 command/service runner，但没有被纳入 agent loop

`CommandRunner` 已经能对声明命令调用 subprocess，捕获 exit code/stdout/stderr 并构造 VerificationRun。`ServiceRunner` 也存在并可用 readiness probe。tiny package assembly 会在写包之后运行 `test-backend` 和 `test-integration`，live blackbox fixture 还会启动 `run-backend` 和 `run-frontend` 并做 HTTP/Node probes。  
来源：`src/boardroom_os/adapters/process_runner.py`，`tests/proving/fixtures/tiny_package_assembly.py`。参考：fileciteturn59file0L174-L243，fileciteturn46file0L210-L242，fileciteturn46file0L245-L344

问题不是“完全没有跑命令能力”，而是这些能力在 provider 完成之后、由测试 fixture/closeout assembly 触发；不是 provider/agent 工作过程中的 observation-repair loop。

### 2.7 Role、model、skill 的数据模型存在，但未形成运行时能力

`ModelExecutionProfile` 有 provider、model、reasoning_effort、context_window、temperature、tool_permissions；`SkillBinding` 有 skill file、allowed roles、capability tags、prompt refs、mcp interface refs、input requirements、output effects。这些是实现 AgentWorkExecutor 的良好输入模型。  
来源：`src/boardroom_os/agents/profiles.py`，`src/boardroom_os/agents/skills.py`。参考：fileciteturn55file0L151-L162，fileciteturn57file0L95-L109，fileciteturn58file0L3-L36

但是 tiny profile 实际只给 implementation attempts 配了 `("provider.invoke",)`，并未赋予 filesystem/patch/command tools。  
来源：`tests/proving/fixtures/tiny_provider_attempts.py`。参考：fileciteturn35file0L98-L113

---

## 3. 对 V2-090F 失败原因的重新判断

### 根因

V2-090F 失败的根因是：系统把“LLM source delivery”误当成了“agent implementation execution”。

具体缺口：

1. 没有 workspace session  
   agent 无法枚举文件、读现有文件、理解当前 tree、生成局部 patch、检查写入后的文件状态。

2. 没有受控写入工具  
   allowed_write_set 只在 JSON 后验检查中使用，没有作为 tool guard 在写入动作前强制执行。

3. 没有 command-observation-repair loop  
   模型无法运行 `test-backend`、`test-integration`、`run-backend`、`run-frontend`，也无法基于 stdout/stderr 反馈修复。

4. 没有 tool attempt / workspace mutation 证据  
   ProviderAttempt 只能说明模型输出了文本；缺少“某次 agent action 调用了 read_file/apply_patch/run_command，结果是什么”的证据链。

5. 没有 role-aware skill runtime  
   role_prompt_hook、skill、MCP interface、tool permission 现在是数据模型或 prompt lineage，未变成可执行的能力调度。

6. tiny fixture 的验证发生在 provider 之后  
   它能发现输出不满足要求，但无法把失败作为 observation 交回同一 agent loop 进行修复。

### 非根因或次要因素

- 不是单纯 OpenAI model 太弱。换模型或增大上下文只能提高一次性 JSON 生成概率，不能让文本调用获得文件系统和命令执行能力。
- 不是 closeout gate 太严格。gate 在拦截“没有真实证据”的结果，这是正确的 fail-closed 行为。
- 不是仅仅缺更多 prompt wording。当前 prompt 已经把大量验收细节塞进去，但这仍然是一次性生成，不是执行。
- 不是需要把 RuntimeExecutor 放宽到可以直接完成 ticket。runtime 不应发治理完成事件；问题是它缺少 agent work fact 的生成能力，而不是治理边界过严。

---

## 4. 当前分支能力评估

| 维度 | 当前状态 | 评价 |
|---|---|---|
| 合约/领域模型 | ExecutionPackage、ProviderAttempt、VerificationRun、SourceInventory、EvidenceObligation、CloseoutGate 都有明确建模 | 良好，可保留 |
| 事件边界 | RuntimeExecutor 明确禁止 TICKET_COMPLETED/CLOSEOUT_COMMITTED 等治理事件 | 正确 |
| Provider 接入 | 可调用 OpenAI-compatible chat/responses，记录 raw/parsed artifact hash | 可用但只是文本 transport |
| CommandRunner / ServiceRunner | 可执行声明命令、记录 stdout/stderr/exit、服务 readiness | 可复用 |
| Role/model/hook/skill 数据模型 | 已存在 RoleProfile、ModelExecutionProfile、SkillBinding/MCPInterface | 有地基，但未执行化 |
| Agent 原子 loop | 缺失 | P0 缺口 |
| Workspace 工具 | 缺失 read/list/write/apply_patch guard | P0 缺口 |
| Repair loop | 缺失基于命令输出的多轮修复 | P0 缺口 |
| Provider attempt 语义 | 记录了模型调用，但被上层当成实现证据 | 语义混淆 |
| tiny proving | 现在测试的是“provider 能否一次性吐完整 JSON 项目” | 与目标自治状态机不匹配 |

---

## 5. 对“是否只是欠缺 agent 执行器模块”的回答

大方向是“是”，但要避免低估范围。

欠缺的不是一个薄 wrapper，而是一组小而完整的 execution subsystem：

```text
AgentWorkExecutor
  + WorkspaceSession / WorkspaceToolRegistry
  + Tool permission guard
  + Provider turn adapter
  + Structured action parser
  + Observation model
  + Patch/write applier
  + Command/service runner bridge
  + Evidence/event recorder
  + Replay transcript
```

不过，这组模块可以在不推翻现有架构的情况下实现，因为现有项目已经有：

- ExecutionPackage：提供 ticket、seat、role hook、allowed_write_set、commands、required outputs。
- ModelExecutionProfile：提供 provider/model/reasoning/context/tool permissions。
- RolePromptHook/SkillBinding：可作为 prompt/context/tool permission 的来源。
- CommandRunner/ServiceRunner：可复用为 run_command/run_service 工具。
- EvidenceVerifier/CloseoutGate：可继续负责最终验收，而不是由 agent 自判完成。
- RuntimeEventBoundary：可扩展为记录 tool/workspace facts，但仍禁止治理完成事件。

因此建议：保留现有 governance kernel，在其下新增一个小型通用 `AgentWorkExecutor`，替换 V2-090F 的“source delivery JSON fixture”。

---

## 6. 建议的边界：ProviderTransport vs AgentWorkExecutor

应该把 provider 调用和 agent work 执行分开：

### ProviderTransport

只负责：

- 根据 provider/model/profile 发起模型调用。
- 支持 text / structured JSON / native tool calls 的统一输出。
- 记录 raw/parsed response artifacts。
- 返回 ProviderAttempt 或 ProviderTurnAttempt。

### AgentWorkExecutor

负责：

- 加载 ExecutionPackage、role hook、skill context、allowed tools。
- 维护 conversation/workspace/tool state。
- 把模型输出解析成 Boardroom-defined AgentAction。
- 执行受控工具。
- 把工具结果作为 observation 回传给模型。
- 在 max_steps/max_seconds/max_tokens 内循环。
- 生成 work product submission 与 evidence references。
- 记录 provider attempts、tool attempts、workspace mutations、command runs。
- 但不发 `TICKET_COMPLETED`，仍由 reducer/gate/checker 判定完成。

这能避免把 OpenAI/Claude/其它 provider 的具体 tool API 深度耦合到 Boardroom 的业务状态机里。

---

## 7. 对现成方案的判断

本报告另有 `boardroom_os_agent_work_executor_design.md` 和 `boardroom_os_remediation_plan.md` 细化方案。总体建议：

- 第一阶段自己实现小型通用 AgentWorkExecutor。
- 不要直接把 Codex/Claude Code 当核心 executor。
- 可以把外部框架作为可选后端或参考实现，而不是 Boardroom 的事实来源。
- 可以以后添加 `ExternalCodingAgentTool`，把 Codex/Claude Code 的结果导入 Boardroom evidence 模型，但不能让外部工具绕过 ExecutionPackage、allowed_write_set、ProviderAttempt、VerificationRun、SourceInventory 和 CloseoutGate。

这样做的理由是 Boardroom OS 的核心价值在“可审计自治状态机”，不是通用聊天或通用 coding assistant。直接引入大型 agent framework 很容易得到能改代码的 agent，但会丢失本项目最重要的 contract/evidence/replay/fail-closed 语义。

---

## 8. 推荐下一步

1. 冻结 V2-090F 的 provider source delivery 路线，不再继续靠 prompt 逼模型吐完整项目。
2. 新建 V2-091：AgentWorkExecutor 最小闭环。
3. 先写红测，证明当前 provider chat path 不能通过：
   - 没有 tool attempt 不可声明 source implementation。
   - 没有 workspace mutation 不可生成 SourceInventory lineage。
   - 没有 run_command observation 不可通过 tiny closeout。
4. 实现 `read_file/list_files/apply_patch/write_file/run_command/submit_work_product` 六个最小工具。
5. 用 provider-agnostic JSON action protocol 起步，不依赖 provider 原生 tool calling。
6. 让 tiny backend worker 在一个临时 workspace 内：写文件 -> run test -> 读 stderr/stdout -> patch -> rerun -> submit。
7. 待 tiny loop 稳定后再把 service runner/live blackbox 纳入 same-loop 或 post-loop evidence。
