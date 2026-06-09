# Boardroom OS V2-090F 复审证据索引与决策记录

生成日期：2026-06-03

---

## 1. 仓库证据索引

| 主题 | 文件 | 关键发现 | 引用 |
|---|---|---|---|
| V2 定位 | `README.md` | 当前 V2 是 clean foundation / foundation-only，强调真实执行证据 | fileciteturn2file0L9-L16, fileciteturn2file0L24-L31 |
| 开发约束 | `AGENTS.md` | contract-first、evidence-first、fail-closed、runtime bounded、禁止 zero-attempt/fallback 作为实现证据 | fileciteturn7file0L101-L118 |
| ExecutionPackage | `doc/03-architecture/domain-model.md` | ExecutionPackage 应包含 commands、allowed_write_set、required outputs、fallback policy | fileciteturn8file0L144-L162 |
| Runtime 边界 | `doc/03-architecture/execution-and-runtime-boundary.md` | Runtime 可调用 provider/tool、运行命令、记录 attempts；禁止发治理完成事件 | fileciteturn10file0L17-L42, fileciteturn10file0L115-L139 |
| Agent team | `doc/03-architecture/agent-team-model.md` | 角色、hook、skill、model profile 被建模；delegation loop 有设想 | fileciteturn12file0L9-L18, fileciteturn12file0L190-L216 |
| 当前阻塞 | `doc/04-implementation/backlog.md` | V2-090F 明确 BLOCKED：source delivery 是单次 LLM JSON，缺少 AgentWorkExecutor | fileciteturn25file0L12-L23 |
| ProviderExecutor | `src/boardroom_os/execution/provider_executor.py` | 只渲染 prompt 并调用 provider_adapter.invoke | fileciteturn27file0L61-L80 |
| OpenAI adapter | `src/boardroom_os/providers/openai_adapter.py` | 调用 responses/chat completions，写 raw/parsed text artifacts | fileciteturn37file0L217-L259, fileciteturn37file0L284-L312 |
| RuntimeExecutor | `src/boardroom_os/execution/runtime_executor.py` | 记录 provider attempt/work product；仅在 command_ids 非空时跑命令 | fileciteturn36file0L260-L362 |
| tiny provider fixture | `tests/proving/fixtures/tiny_provider_attempts.py` | `command_ids=()`，provider 阶段不跑命令；重试仅检查 source JSON | fileciteturn34file0L18-L65, fileciteturn34file0L68-L112 |
| source delivery prompt | `tests/proving/fixtures/tiny_provider_attempts.py` | 要求模型一次性返回 `{"files": ...}` | fileciteturn34file0L173-L250 |
| package assembly | `tests/proving/fixtures/tiny_package_assembly.py` | 从 provider parsed artifact 提取 files，写临时 package 后再跑 tests | fileciteturn48file0L121-L155, fileciteturn52file0L3-L24 |
| package contents | `tests/proving/fixtures/tiny_package_assembly.py` | `_package_contents_with_generated_files` 要求 provider contents 覆盖 expected paths | fileciteturn53file0L22-L51 |
| process runner | `src/boardroom_os/adapters/process_runner.py` | CommandRunner 已能真实执行声明命令并生成 VerificationRun | fileciteturn59file0L174-L243 |
| model profile | `src/boardroom_os/agents/profiles.py` | provider/model/reasoning/context/tool_permissions 已建模 | fileciteturn55file0L151-L162 |
| skill binding | `src/boardroom_os/agents/skills.py` | skill/MCP/prompt/capability/role binding 已建模 | fileciteturn57file0L95-L109, fileciteturn58file0L3-L36 |

---

## 2. 外部方案评估依据

| 方案 | 官方资料观察 | 对 Boardroom OS 的建议 |
|---|---|---|
| OpenAI Agents SDK | 官方文档称其提供 agent loop、tool invocation、handoffs、guardrails、sandbox agents、tracing；也明确 Responses API 更适合“自己拥有 loop/tool dispatch/state handling”的路径 | 可作为参考或 provider-specific adapter；Boardroom 第一阶段仍应自己拥有 loop/evidence/state |
| LangGraph | 官方文档定位为 low-level orchestration runtime，面向 long-running stateful agents，提供 durable execution、human-in-loop、memory、streaming 等 | 可借鉴持久化/状态图；不应替代 Boardroom reducers/gates |
| Microsoft AutoGen | 官方文档定位为构建 conversational single/multi-agent apps 和 event-driven multi-agent systems，并有 Docker command executor/MCP 扩展 | 重叠 Boardroom agent team；可参考但不建议核心嵌入 |
| Hugging Face smolagents | 官方文档提供 multi-step agents、tools、secure code execution、memory、multi-agent orchestration 等主题 | 轻量原型候选；但安全/证据/权限模型必须重包 |
| Claude Code | 官方文档说明它可读代码、编辑文件、运行命令、集成开发工具，并支持 skills/hooks/subagents/Agent SDK | 能力强但较重；建议作为外部 coding tool，不作为 Boardroom 核心状态机 |
| Codex | OpenAI docs 包含 tools、shell、apply patch、sandbox agents、skills、subagents、automation 等 coding-agent 能力入口 | 能力方向匹配，但模型/产品耦合较强；适合作为后续 ExternalCodingAgentTool |

---

## 3. 决策记录

### DR-001：将 V2-090F 失败归因为 AgentWorkExecutor 缺失

状态：建议采纳。  
理由：当前 provider path 没有 workspace tool、没有 command feedback loop、没有 mutation evidence；分支 backlog 也已记录同一阻塞。

### DR-002：自研核心 AgentWorkExecutor

状态：建议采纳。  
理由：Boardroom OS 的关键价值是 contract/evidence/fail-closed/replay。现成框架的 trace/agent state 不等价于 Boardroom 的治理事实链。

### DR-003：provider-agnostic JSON action protocol 起步

状态：建议采纳。  
理由：能同时适配 OpenAI-compatible chat、Responses、Anthropic-compatible、local models；先证明 loop semantics，再优化 native tool calling。

### DR-004：Codex/Claude Code 作为可选外部工具，不作为核心 executor

状态：建议采纳。  
理由：它们能读写文件和跑命令，但会带来模型/产品/权限/trace 语义耦合。Boardroom 的 allowed_write_set、EvidenceVerifier、CloseoutGate 必须继续做事实源。

### DR-005：ProviderAttempt 语义降级为“模型 turn evidence”

状态：建议采纳。  
理由：ProviderAttempt 只能证明模型被调用和输出被存档；implementation evidence 必须来自 ProviderAttempt + ToolAttempt + WorkspaceMutation + VerificationRun 的组合。
