# Boardroom OS V2-091 修复计划：从 Provider Source Delivery 升级到 Agent Work Loop

生成日期：2026-06-03  
背景：V2-090F tiny integration provider-backed run 已多次失败。复审判断：失败根因是缺少 agent 执行器，而不是单纯 provider/chat prompt 问题。

---

## 0. 总目标

用一个小型、可审计、provider-agnostic 的 `AgentWorkExecutor` 替代 V2-090F 的 “provider 一次性返回 JSON files” 路线。

最终 tiny proving 应证明：

```text
真实 provider attempt
  -> agent tool loop
  -> workspace file mutations
  -> declared commands run
  -> failed output fed back
  -> repaired files
  -> final command/service/live evidence
  -> closeout gate passed
```

而不是：

```text
真实 provider attempt
  -> text JSON files
  -> fixture 写入 package
  -> fixture 测试
```

---

## 1. V2-091A：先写红测，锁定当前缺口

### 测试 A1：ProviderAttempt 不等于 AgentWork

断言：只有 ProviderAttempt，没有 ToolAttempt/WorkspaceMutation 的 RuntimeExecutionResult 不能被视作 implementation work product。

预期失败点：当前 RuntimeExecutor 会在 provider success 后直接 build work product。

### 测试 A2：source delivery JSON 不能直接满足 source implementation evidence

断言：parsed artifact 中的 JSON files 即使覆盖 allowed_write_set，也不能生成 source lineage，除非有 workspace mutation evidence。

### 测试 A3：没有 run_command observation 的 tiny provider attempt 不能 closeout

断言：agent work 至少应运行 package contract 中与 ticket 相关的 test command，并把 stdout/stderr 作为 observation 或 evidence。

### 测试 A4：写出 allowed_write_set 之外必须 fail closed

模拟 provider action 要写 `backend/evil.py` 或 `../outside.py`，必须被 workspace guard 拒绝并记录 failed ToolAttempt。

### 测试 A5：未声明 command 不可运行

模拟 action `run_command: "rm -rf ."` 或任意 shell，必须拒绝；只允许 command_id lookup。

---

## 2. V2-091B：Workspace 工具与 guard

新增模块：

```text
src/boardroom_os/execution/workspace_tools.py
src/boardroom_os/execution/workspace_mutation.py
src/boardroom_os/execution/tool_attempt.py
```

实现最小工具：

1. `list_files`
2. `read_file`
3. `write_file`
4. `apply_patch`
5. `run_command`
6. `submit_work_product`

验收：

- 路径规范化、拒绝 `..`、拒绝 symlink escape。
- 写入前检查 `allowed_write_set`。
- 运行命令前通过 `ExecutionPackage.commands` 和 `PackageContract.commands` 双重匹配。
- 每个 tool call 都返回 ToolAttempt/ToolResult。
- 文件变更产生 before/after sha256 和 diff artifact。

---

## 3. V2-091C：Provider turn/action 协议

新增：

```text
src/boardroom_os/execution/agent_actions.py
src/boardroom_os/execution/provider_turn.py
```

协议：

```json
{
  "action": "read_file | list_files | write_file | apply_patch | run_command | submit_work_product",
  "path": "optional",
  "content": "optional",
  "patch": "optional",
  "command_id": "optional",
  "reason_summary": "short, non-chain-of-thought rationale"
}
```

验收：

- 无效 JSON -> failed provider turn + observation retry。
- 多余字段 -> fail closed 或 strict validation error。
- action schema 与 provider 原生 tool calling 解耦。
- Provider raw output、parsed action、prompt lineage 都有 artifact refs。

---

## 4. V2-091D：AgentWorkExecutor 主循环

新增：

```text
src/boardroom_os/execution/agent_work_executor.py
src/boardroom_os/execution/agent_transcript.py
```

Loop 规则：

1. resolve role/profile/model/skill。
2. build tool registry。
3. create prompt with package facts + allowed tools + current workspace inventory。
4. provider turn。
5. parse action。
6. execute guarded tool。
7. append observation。
8. repeat。
9. submit work product 或 fail closed。

验收：

- `max_steps` 达到后 fail closed。
- provider failed 后可按 fallback policy 记录失败，但不能产生 implementation evidence。
- no workspace mutation -> no work product。
- command failures 可以作为 observation 继续修复。
- RuntimeEventBoundary 仍禁止治理完成事件。

---

## 5. V2-091E：Evidence / SourceInventory / Closeout 集成

目标：让 closeout 消费真实 agent work facts。

新增/扩展：

- ToolAttempt payload resolver。
- WorkspaceMutation payload resolver。
- SourceInventory builder 接收 final workspace tree + workspace mutation lineage。
- EvidenceVerifier 支持 ToolAttempt/WorkspaceMutation 作为 source evidence。
- ProcessAuditBundle 收录 agent transcript、tool attempts、command observations。

验收：

- 每个 source file 有 producer attempt + workspace mutation + file hash。
- 每个 command evidence 有 VerificationRun + stdout/stderr artifact hash。
- Provider artifact 只是 lineage 的一部分，不是单独 implementation evidence。
- fake/fallback/synthetic 仍不能 pass closeout。

---

## 6. V2-091F：Tiny atomic loop golden path

新建 proving fixture：

```text
tests/proving/fixtures/tiny_agent_work.py
tests/proving/test_tiny_agent_work_executor.py
```

第一版可以用 FakeProviderTransport 驱动固定 action 序列：

1. write backend/app.py
2. write backend/db.py
3. run test-backend -> fail
4. read stderr
5. apply patch
6. run test-backend -> pass
7. submit work product

再接真实 provider：

1. provider 通过 JSON action 写最小 backend。
2. executor 运行 test-backend。
3. provider 根据 stderr 修复。
4. closeout 不要求一次到位，但要求完整证据链。

验收：

- fake path 证明 executor semantics。
- real provider path 证明最小 provider loop。
- 不再使用 “Return all files as one JSON blob” 作为核心实现机制。

---

## 7. V2-092：替换 V2-090F sample build

替换点：

- `build_tiny_provider_attempt_fixture()` 不再作为 source implementation 入口。
- 新增 `build_tiny_agent_work_fixture()`。
- `_source_delivery_files_from_provider()` 降级为 legacy negative-test helper 或删除。
- `materialize_tiny_closeout_sample()` 从 actual workspace tree + mutation evidence materialize files。
- provider artifact lock 变成 agent transcript/provider-turn lock，而不是 source JSON lock。

验收：

- sample 中包含 provider attempts、tool attempts、workspace mutations、command runs、service runs、live blackbox evidence。
- `scripts/build_tiny_closeout_sample.py --check` 可重放 lock，并验证 artifact hashes。
- closeout gate 看到的是完整 agent work evidence。

---

## 8. 风险与缓解

| 风险 | 影响 | 缓解 |
|---|---|---|
| provider 输出无效 action JSON | loop 卡死 | strict parser + bounded retry + observation |
| agent 写错路径 | 安全/污染 | allowed_write_set + path guard + symlink guard |
| agent 无限修复 | 成本/时间 | max_steps/max_command_runs/max_wall_seconds |
| stdout/stderr 太大 | context 爆炸 | artifact store 完整保存，observation 截断 |
| 外部框架绕过证据链 | closeout 不可信 | 所有外部结果必须导入 ToolAttempt/WorkspaceMutation/VerificationRun |
| tests flaky | proving 不稳定 | deterministic fake loop first，real provider 只作为 integration gate |
| provider/tool permission 混乱 | 权限扩大 | tool registry = model profile ∩ skill binding ∩ package contract |

---

## 9. 里程碑退出条件

### Exit V2-091

- Fake provider atomic agent loop pass。
- Real provider minimal agent loop pass。
- Negative tests cover forbidden writes/commands/no-mutation-no-workproduct。
- Existing RuntimeExecutor governance boundary unchanged。

### Exit V2-092

- Tiny fullstack closeout sample built from agent workspace mutations。
- run-backend/run-frontend service evidence present。
- live blackbox HTTP + frontend integration evidence present。
- provider attempts are real provider attempts。
- source lineage binds files to provider/tool/workspace evidence。
- no fallback/fake/synthetic artifacts satisfy implementation evidence。

### Exit V2-093

- Multi-role delegation loop starts to use AgentWorkExecutor for Worker/Tester/Integration roles。
- Checker remains separate governance/evaluation role。
- Closeout remains gate-driven。
