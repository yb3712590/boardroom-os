# V2-090J Atomic Action Protocol Repair 设计

## 背景

V2-090I Resettable medium implementation scenario（可重置中等复杂实施场景）证明了真实 provider-backed `AtomicAgentExecutor`（模型供应商支撑的原子智能体执行器）在中等复杂多文件任务上仍未达到可验收稳定性。三次真实 run（运行）均失败：

- Run 1：`action_parse_failed`，多次 invalid JSON（非法 JSON）和旧 `action_envelope`（动作信封）结构，写出 2/5 个必需文件后失败。
- Run 2：`policy_denied`，provider（模型供应商）选择 `apply_patch` 一次写多文件，被 permission policy（权限策略）拒绝为 `invalid_path_type_denied`。
- Run 3：禁用 `apply_patch` 后写出 4/5 个必需文件，但仍因 invalid JSON / `action_parse_failed` 失败，未生成测试文件，未运行 `cmd.check-medium-scenario`。

外部评审一致指出：主因不是 Boardroom OS（董事会系统）的 command evidence（命令证据）、allowed write set（允许写入集合）或 source lineage（源码来源链）门禁过严；这些门禁仍是防止 mocked success path（模拟成功路径）和 silent fallback（静默降级）的必要条件。根因在 atomic-agent（原子智能体）的 action protocol（动作协议）和执行循环对中等复杂任务不够稳。

## 失败根因总结

### 根因 1：单 action JSON 协议与中等复杂任务不匹配

atomic-agent 当前 `parse_agent_action`（动作解析器）只接受整个 provider output（模型输出）为单个 JSON object（JSON 对象）。V2-090I prompt（提示词）已明确要求每轮只输出一个顶层 JSON action，但真实 provider 仍会自然输出多个 action、旧 `action_envelope` 或带说明文本的批量方案。当前 parser 对整轮输出 fail closed（失败关闭），导致其中本来合法的写文件、运行命令或提交动作无法被执行。

这不是要静默拆 JSON 或放松门禁。修复必须把多动作能力显式协议化、版本化、审计化，或使用 provider-native structured output / tool calling（供应商原生结构化输出 / 工具调用）在结构层强制单动作。

### 根因 2：`apply_patch` 工具可见性与运行时权限错配

Boardroom settings（配置）和 `AtomicToolPolicyResolver`（原子工具策略解析器）允许 worker（工作者）通过 `write_file` 或 `apply_patch` 满足 workspace mutation（工作区变更）能力；atomic-agent 协议也声明 `apply_patch` 是合法动作。但 V2-090I Run 2 中 provider 选择 `apply_patch` 后，运行时权限拒绝为 `invalid_path_type_denied`，且不可重试，直接终止 run。

这说明工具可见性、工具 schema（结构）和 permission policy（权限策略）没有形成单一一致事实源。多文件任务中 `apply_patch` 是合理工具；如果不正式支持，就不应暴露给 provider。如果正式支持，必须逐路径校验 allowed write set 并记录 workspace mutation / diff evidence（差异证据）。

### 根因 3：validator command 是终局硬要求，但不是执行循环中的阶段化调度

V2-090I `ExecutionPackage`（执行包）声明 `cmd.check-medium-scenario`，Boardroom executor（执行器）最终也要求 command evidence（命令证据）。但 agent loop（智能体循环）没有确定性阶段在 required outputs（必需产物）齐备后触发 validator command（验证命令）。当 provider 写出部分文件后陷入 parse failure（解析失败），run 可以长时间消耗预算而没有运行一次验证命令。

修复不应让 runtime 生成 evidence（证据）或替代 agent 决策；但可以把声明命令作为 deterministic checkpoint（确定性检查点）调度：一旦 required outputs 齐备，executor 可以运行声明命令并把 observation（观察结果）反馈给 agent 修复。最终 `command.completed` 仍必须来自真实 command runner（命令运行器）。

### 根因 4：V2-090I 单 ticket 粒度偏重

当前单个 ticket 同时要求生成 package skeleton（包骨架）、多步算法、文件间 import（导入依赖）、tests（测试）、CLI（命令行）、validator command（验证命令）和 `submit_result`（提交结果）。这对只支持单 action turn（单动作轮次）的 agent loop 过重。即便协议修复后，V2-090I 也应保留一个 staged medium scenario（分阶段中等场景）复验，证明任务拆分策略能降低协议压力。

## 设计目标

V2-090J 目标是修复 V2-090I 暴露出的 atomic action execution bottleneck（原子动作执行瓶颈），并建立复验路径。完成后应证明：

1. Boardroom 不放松 evidence gates（证据门禁）：仍要求 real provider（真实模型供应商）、provider turn facts（模型轮次事实）、workspace mutation（工作区变更）、declared command evidence（声明命令证据）和 source lineage input（源码来源链输入）。
2. atomic-agent action protocol（动作协议）不再只靠 prompt 文字约束维持稳定；要么启用 provider-native structured output/tool calling，要么支持显式 `batch_actions`（批量动作）协议。
3. `apply_patch` 工具策略要一致：正式支持受限 patch 或从 resolved tools（解析后工具集合）中彻底移除。
4. `cmd.check-medium-scenario` 或等价 validator command（验证命令）被纳入执行循环 checkpoint（检查点），而不是只在最终验收时发现缺失。
5. 复跑 V2-090I 或 V2-090J medium scenario（中等场景）时，真实 provider-backed executor 能完成中等复杂任务并通过 command evidence。

## 非目标

- 不放宽 Boardroom closeout / completion gate（收尾 / 完成门禁）。
- 不把 failed atomic run（失败原子运行）投影为 successful WorkProduct（成功工作产物）。
- 不静默接受 `action_envelope`、多个 JSON object（多个 JSON 对象）或 Markdown 包裹内容；任何兼容都必须有显式协议版本和审计事件。
- 不直接恢复 V2-090F Golden sample rebuild（黄金样例重建）。
- 不把增加 `max_steps` 或 `max_parse_failures` 作为主要修复。

## 推荐方案

采用四段式修复：

1. **协议层优先**：在 atomic-agent 中新增 `AgentActionBatch`（智能体动作批次）或 provider-native structured output/tool calling adapter（结构化输出 / 工具调用适配器）。短期推荐 `AgentActionBatch`，因为它不绑定单一 provider；长期可加 native tool calling。
2. **工具策略对齐**：先在 Boardroom 侧默认不暴露 `apply_patch`，并新增 fail-closed 测试证明 role tools（角色工具）和 runtime tools（运行时工具）不一致时不能进入真实 run；同时在 atomic-agent 单独设计受限 `apply_patch` 支持，成熟后再启用。
3. **validator checkpoint**：在 Boardroom 的 atomic invocation metadata（原子调用元数据）或 output requirements（输出要求）中声明 required-output checkpoint（必需产物检查点）。agent loop 只在 required outputs 齐备时运行声明 validator command，并把 observation 反馈给 provider；该 command evidence 必须进入 event stream。
4. **任务粒度复验**：新增 V2-090J proving runner（证明运行器），复用 V2-090I package/CLI 合同，但拆成 staged execution expectations（阶段化执行期望）：先生成源码文件，再生成 tests，再跑 validator，再修复并 submit。该 proving runner 不生成 closeout passed golden sample。

## 协议层要求

### AgentActionBatch

如果选择 batch 协议，provider output 必须是以下二选一之一：

```json
{
  "action_id": "step-0001",
  "action": "write_file",
  "reason_summary": "Create statistics module.",
  "input": {"path": "work/forecast_engine/statistics.py", "content": "..."}
}
```

或：

```json
{
  "batch_id": "batch-0001",
  "protocol": "agent-action-batch-v1",
  "reason_summary": "Create the initial package files and then run validation.",
  "actions": [
    {
      "action_id": "step-0001",
      "action": "write_file",
      "reason_summary": "Create statistics module.",
      "input": {"path": "work/forecast_engine/statistics.py", "content": "..."}
    },
    {
      "action_id": "step-0002",
      "action": "run_command",
      "reason_summary": "Run declared medium scenario validator.",
      "input": {"command_id": "cmd.check-medium-scenario"}
    }
  ]
}
```

要求：

- batch 必须有 `protocol="agent-action-batch-v1"`，不得通过数组裸传。
- parser（解析器）必须先判断显式 `protocol`：只有 `parsed.get("protocol") == "agent-action-batch-v1"` 才按 batch 解析；若 JSON object（JSON 对象）包含 `actions` 或 `batch_id` 但缺显式协议，必须以 `batch_like_without_protocol` fail closed（失败关闭）。
- parser 不得接受裸数组、多个 JSON object 串联、Markdown 包裹 JSON、旧 `action_envelope` 或 provider explanation text（模型说明文本）。
- batch 内每个 action 仍复用 `AgentAction` schema（动作结构），逐条 permission decision（权限判定）、tool attempt（工具尝试）和 event（事件）记录。
- batch 的 action 数量必须受预算限制，字段名为 `max_actions_per_turn`。该字段必须同时存在于 atomic-agent runtime budget（运行时预算）、Boardroom `AgentExecutionBudgetConfig`（智能体执行预算配置）、`budget_profiles`（预算档）和 `budget_caps`（预算上限）中；默认值为 `1` 只用于向后兼容，V2-090J runner（运行器）必须断言解析后的值大于 `1`。
- 任一 action 失败时，run fail closed 或返回可审计 observation；不得跳过失败动作继续伪造成功。
- `submit_result` 若出现在 batch 中，必须是最后一个 action；且前面必须已存在 required command evidence（必需命令证据）。
- `action_envelope` 不作为兼容输入。若要支持旧结构，必须先发布 `agent-action-envelope-v2` 协议，不在本工作包内。

### Provider-native structured output

若使用 structured output/tool calling（结构化输出/工具调用），必须满足：

- provider profile（供应商配置档）显式声明支持该能力；
- 不支持时 fail closed，不退回自由文本 JSON；
- raw tool call payload（原始工具调用载荷）和 parsed action（解析动作）都写入 artifact（产物）并进入 event stream；
- schema 与 `AgentAction` / `AgentActionBatch` 保持同一权威定义。

## 工具策略要求

V2-090J 不要求立即支持 `apply_patch`。最低可接受修复是：

- Boardroom worker role（工作者角色）默认 resolved tools（解析后工具）只暴露 `write_file`、`run_command`、`submit_result` 和必要 read/search 工具；
- `allow_apply_patch` 是 runtime filesystem policy（运行时文件系统策略），字段位置为 `atomic_agent.filesystem.allow_apply_patch`，对应 `AtomicFilesystemConfig.allow_apply_patch: bool = False`；
- 如果 role tools（角色工具）或 runtime default tools（运行时默认工具）含 `apply_patch`，但 `atomic_agent.filesystem.allow_apply_patch` 为 `false`，`AtomicInvocationCompiler`（原子调用编译器）必须 fail closed，而不是让 provider 运行后才失败；
- V2-090I scenario-local workaround（场景局部绕过）必须被替换为正式配置：要么从 `config/boardroom-runtime.example.yaml` 和 `config/boardroom-roles.example.yaml` 移除 `apply_patch` / `skill.filesystem.patch`，要么显式设置 `atomic_agent.filesystem.allow_apply_patch: false` 并让 resolver（解析器）在编译期拒绝不一致配置；脚本不得私有过滤工具作为第二事实源。

如果选择正式支持 `apply_patch`，必须另外满足：

- patch input schema（补丁输入结构）必须明确是 single-file patch（单文件补丁）还是 multi-file patch（多文件补丁）。
- multi-file patch 必须解析出每个路径，并逐路径校验 allowed write set。
- 每个被修改文件都必须产生 workspace mutation event（工作区变更事件）和 before/after hash（前后哈希）。
- 拒绝 absolute path（绝对路径）、`..` 逃逸、删除 allowed write set 外文件、二进制 patch 和无法解析路径的 patch。

## Validator checkpoint 要求

新增 checkpoint 只执行已在 `ExecutionPackage.commands`（执行包命令集合）声明的 command_id（命令编号），不得执行自由 shell。建议语义：

```json
{
  "required_output_checkpoint": {
    "when_all_paths_exist": [
      "work/forecast_engine/__init__.py",
      "work/forecast_engine/statistics.py",
      "work/forecast_engine/risk.py",
      "work/forecast_engine/cli.py",
      "work/tests/test_forecast_engine.py"
    ],
    "run_command_id": "cmd.check-medium-scenario",
    "max_auto_runs": 3
  }
}
```

规则：

- checkpoint 只能在 required outputs 全部存在后触发。
- V2-090J 只支持 `ExecutionPackage.commands`（执行包命令集合）恰好包含一个声明命令时自动生成 checkpoint；若包声明多个 commands，因当前 `PackageCommand`（包命令）没有 validator marker（验证器标记）字段，必须 fail closed，不能默认选择第一个命令。
- `max_auto_runs` 必须来自配置，不得硬编码。推荐配置路径为 `atomic_agent.checkpoints.required_output.max_auto_runs`，对应 Boardroom 配置模型 `AtomicAgentCheckpointConfig.required_output.max_auto_runs` 或同等单一权威源。
- `max_auto_runs` 表示同一个 required-output checkpoint（必需产物检查点）最多自动触发的次数。第 1 次失败后 observation（观察结果）反馈给 provider 修复；达到上限后 runtime 不再自动触发，也不得自动提交成功，provider 仍可显式执行已声明 command。
- checkpoint 运行结果必须记录 `command.completed` event（命令完成事件）和 stdout/stderr artifact refs（标准输出/错误产物引用）。
- checkpoint exit code 非 0 时，将 observation 反馈给 provider 修复。
- checkpoint exit code 为 0 后，provider 仍必须显式 `submit_result`；runtime 不得自动提交。
- checkpoint 不得在缺 provider attempt（模型调用尝试）或 provider zero-turn（零模型轮次）时生成可满足 implementation evidence 的结果。

## Boardroom 集成要求

Boardroom OS 侧只做三类改变：

1. 编译配置：`AtomicInvocationCompiler` 把 action protocol version（动作协议版本）、batch budget（批次预算）和 checkpoint requirements（检查点要求）写入 `AgentInvocation.metadata` / `output_requirements`。`max_actions_per_turn` 和 checkpoint `max_auto_runs` 必须来自 settings（配置），且 V2-090J runner 必须断言解析后的 `max_actions_per_turn > 1`。
2. 校验结果：`AtomicAgentResultValidator` 继续要求 provider turn facts、workspace mutation、command evidence 和 source lineage input；新增校验 batch events（批次事件）或 checkpoint events（检查点事件）必须完整。
3. 复验证明：新增 V2-090J proving test（证明测试）默认 skip，显式 opt-in 后跑真实 provider，成功后只证明中等复杂 executor path（执行器路径）恢复，不解除 V2-090F。

## 测试策略

### atomic-agent 测试

- parser negative：裸数组、多个 JSON 对象串联、Markdown 包裹 JSON、缺 `protocol` 的 batch、batch 内未知 action 均失败。
- parser happy：单 action 仍可解析；`agent-action-batch-v1` 可解析为有序 action 列表。
- loop happy：用 test provider double（测试替身）覆盖 batch 执行循环，逐条记录 `action.parsed`、`permission.decided`、`tool.attempt.*`、`command.completed` 和 `result.submitted`。该类单元测试只证明 loop semantics（循环语义），不能作为 V2-090J proving success（证明成功）证据。
- loop negative：batch 中第二个 action 权限失败时后续动作不得执行；`submit_result` 非最后一个 action 失败；超过 `max_actions_per_turn` 失败。
- checkpoint happy：required outputs 齐备后自动运行声明 command，失败 observation 可反馈，修复后再次运行并通过。

### Boardroom 测试

- `AtomicInvocationCompiler` 编译出 action protocol / batch / checkpoint metadata。
- tool policy negative：`apply_patch` 可见但 runtime 不支持时 fail closed；默认 medium scenario 不再需要脚本局部移除工具。
- `AtomicAgentResultValidator` 接受 batch/checkpoint 事件流，但仍拒绝缺 command evidence、缺 workspace mutation、缺 source lineage input。
- V2-090J proving script 非 provider tests 覆盖 reset、report、event summary、checkpoint metadata、`max_actions_per_turn > 1` resolved budget（解析后预算）和 fail-closed secret 缺失。
- 真实 provider proving test 默认 skip；显式 opt-in 后必须完成 medium package/CLI 并通过 command evidence。

## 文档更新

- Boardroom：更新 `doc/04-implementation/backlog.md`、`doc/04-implementation/acceptance-criteria.md`、`doc/05-project-log/2026-06.md` 或 `2026-06` 后续日志，新增 V2-090J 状态。
- atomic-agent：更新 `docs/03-contracts/agent-action-protocol.md`、`docs/03-contracts/event-stream-protocol.md`、相关 implementation spec/plan 和 project log。
- V2-090I run record（实施流水记录）保留为阻塞证据，不覆盖或改写为成功。

## 验收标准

V2-090J 只有在以下全部满足时才能标记 `DONE`：

- atomic-agent 单元与负例测试证明 batch/structured protocol（批量/结构化协议）不静默兼容非法输出。
- Boardroom 单元与负例测试证明工具策略和 checkpoint metadata（检查点元数据）fail closed。
- V2-090J settings（配置）证明 `max_actions_per_turn > 1` 和 checkpoint `max_auto_runs` 均来自配置，不是 runner 或 compiler 常量。
- 真实 provider V2-090J medium proving test 显式 opt-in 通过，报告包含：
  - `provider_transport_kind="real"`；
  - terminal event（终止事件）为 `run.completed`；
  - 至少一个 provider turn；
  - 至少一个 workspace mutation；
  - `cmd.check-medium-scenario` exit code 为 0；
  - source lineage inputs 非空；
  - action parse failure rate（动作解析失败率）低于 V2-090I 三次阻塞样本中的失败模式，且不靠单纯提高预算通过。
- V2-090F 仍保持 `BLOCKED`，直到人工评审 V2-090J 证据后明确恢复。

## 自审

- Placeholder scan（占位扫描）：本文不含 TBD/TODO 或未定义路径；JSON 示例中的 `content: "..."` 仅表示文件内容载荷省略，不是待补设计项。
- Consistency check（一致性检查）：方案不放松 Boardroom evidence gates（证据门禁），修复点集中在 action protocol（动作协议）、工具策略和执行 checkpoint（检查点）。
- Scope check（范围检查）：V2-090J 是一个独立修复工作包，不直接实现 V2-090F golden sample rebuild（黄金样例重建）。
- Ambiguity check（歧义检查）：`batch_actions` 不是静默拆 JSON；必须以 `protocol="agent-action-batch-v1"` 显式声明并逐 action 审计。
