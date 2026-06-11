# V2-090I 实施流水与外部评审记录

## 文档职责

本文件记录 V2-090I Resettable medium implementation scenario（可重置中等复杂实施场景）实施流水、验证证据、真实 provider run（模型供应商运行）失败事实、V2-090J 修复后复跑证据和自审结论，供外部分析评审。本文不包含 `.env`、provider secret（模型供应商密钥）或 raw provider output（模型原始输出）。

## 结论

V2-090I runner（运行器）、reset safety（重置安全）、非 provider 测试和文档同步已经实现。2026-06-10 三次真实 provider-backed atomic-agent executor（模型供应商支撑原子智能体执行器）运行均未完成中等复杂多文件 Python package/CLI（Python 包/命令行工具），这些失败保留为 pre-repair evidence（修复前证据）。V2-090J 修复 action protocol（动作协议）、tool policy（工具策略）和 required-output checkpoint（必需产物检查点）后，2026-06-11 V2-090I 原 runner 复跑通过 `cmd.check-medium-scenario` command evidence（命令证据）门禁。因此 V2-090I 状态更新为 `DONE`；V2-090F Golden sample rebuild（黄金样例重建）仍为 `BLOCKED`，不得自动恢复。

## 实施范围

- 新增 `scripts/run_v2_090i_medium_scenario.py`：构造真实 provider-backed `AtomicAgentExecutor`（原子智能体执行器）运行入口、resettable workspace（可重置工作区）、中等复杂 `ExecutionPackage`（执行包）、外部 validator command（验证命令）和 JSON report（报告）。
- 新增 `tests/proving/test_v2_090i_medium_scenario_script.py`：覆盖 reset guardrail（重置护栏）、run id（运行编号）、外部 validator command（验证命令）、配置派生 `ExecutionPackage`、事件摘要和 success 判定。
- 新增 `tests/proving/test_v2_090i_medium_scenario.py`：显式 opt-in 的真实 provider proving test（模型供应商证明测试），仅在 `OPENAI_API_KEY` 与 `BOARDROOM_RUN_REAL_PROVIDER_PROVING=1` 同时存在时运行。
- 更新 `scripts/README.md`、`doc/04-implementation/backlog.md`、`doc/04-implementation/acceptance-criteria.md`、`doc/05-project-log/2026-06.md`，先记录 V2-090I 三次阻塞事实，后记录 V2-090J 修复后的 V2-090I 复跑通过事实。

## 场景合同

V2-090I 要求单个 implementation ticket（实施任务）在 `.evidence/atomic-agent/v2-090i-medium-scenario-workspace/` 下生成：

```text
work/forecast_engine/__init__.py
work/forecast_engine/statistics.py
work/forecast_engine/risk.py
work/forecast_engine/cli.py
work/tests/test_forecast_engine.py
```

外部 validator command（验证命令）`cmd.check-medium-scenario` 必须独立验证：

- required files（必需文件）全部存在；
- `risk.py` 对 `statistics.py` 有真实 import（导入依赖）；
- package（包）可从 `work/` import；
- public API（公开接口）算法结果符合 weighted moving average（加权移动平均）、linear regression forecast（线性回归预测）、max drawdown（最大回撤）和 risk analysis（风险分析）契约；
- `python -m unittest discover -s work/tests -p "test_*.py"` 通过；
- `python -m forecast_engine.cli <input.json>` 输出可解析 JSON 且包含稳定 key（键）和值。

## 实施流水

1. 建立 V2-090I spec（规格）和 implementation plan（实施计划），定位为 V2-090H 与 V2-090F 之间的中等复杂 proving stage（证明阶段）。
2. 先写 reset safety（重置安全）和 run id（运行编号）测试，证明缺 runner 时测试失败，再实现 `initialize_medium_scenario_workspace`（初始化中等场景工作区）与 `_new_run_id`（新运行编号）。
3. 增加外部 validator command（验证命令），用测试夹具生成合法 `forecast_engine` package（预测引擎包），证明 validator 能真实 import/API/unittest/CLI 验证，而不是只看源码字符串。
4. 接入 `load_boardroom_settings`（加载董事会配置）和既有 runtime/providers/roles YAML（运行时/供应商/角色配置），构造 V2-090I `ExecutionPackage`（执行包）。
5. 实现 `run_medium_scenario`（运行中等场景），通过真实 `AtomicAgentExecutor`（原子智能体执行器）调用 provider-backed atomic-agent loop（模型供应商支撑原子智能体循环），并从 event stream（事件流）汇总 provider turns（模型轮次）、action rejections（动作拒绝）、command exit codes（命令退出码）、workspace mutation paths（工作区变更路径）和 source lineage inputs（源码来源链输入）。
6. 第一次真实 provider run 失败后，加强 prompt constraints（提示词约束），要求每轮只输出一个 top-level JSON action（顶层 JSON 动作），禁止 `action_envelope`。
7. 第二次真实 provider run 因 `apply_patch` 工具策略失败后，在 V2-090I scenario-local settings（场景局部配置）中移除 `apply_patch` 和 `skill.filesystem.patch`，避免 provider 选择不被当前 permission policy（权限策略）接受的批量 patch 路径。
8. 第三次真实 provider run 仍因 invalid JSON / `action_parse_failed` 失败；停止继续试跑，避免把 prompt 反复微调伪装为验收通过。
9. 自审发现 runner 中曾用脚本内 `"high"` 作为 `reasoning_effort`（推理强度）默认值，违反“provider 参数只来自配置”约束；已移除该默认值，让缺配置通过 `ModelExecutionProfile`（模型执行配置）校验 fail closed（失败关闭）。
10. 同步 backlog（待办清单）、acceptance criteria（验收标准）、project log（项目日志）和 scripts README（脚本说明），当时将 V2-090I 明确记录为 `BLOCKED`；2026-06-11 修复后复跑通过，当前状态已更新为 `DONE`。

## 验证命令

非 provider V2-090I 验证：

```bash
PYTHONPATH=src:. python -m pytest tests/proving/test_v2_090i_medium_scenario_script.py tests/proving/test_v2_090i_medium_scenario.py -q --tb=short --basetemp .pytest-tmp-v2090i-non-provider
```

结果：

```text
9 passed, 1 skipped
```

executor/config（执行器/配置）回归验证：

```bash
PYTHONPATH=src:. python -m pytest tests/config/test_boardroom_config.py tests/negative/test_boardroom_config_fail_closed.py tests/execution/test_atomic_agent_executor.py tests/negative/test_atomic_agent_executor_fail_closed.py tests/proving/test_tiny_atomic_agent_executor_script.py -q --tb=short --basetemp .pytest-tmp-v2090i-regression
```

结果：

```text
29 passed
```

格式检查：

```bash
git diff --check
```

结果：通过，无输出。

缺 provider secret（模型供应商密钥）fail-closed 验证：

```bash
env -u OPENAI_API_KEY PYTHONPATH=src:. python scripts/run_v2_090i_medium_scenario.py --reset
```

结果：exit 1，stderr 为 `ValueError: provider api key env is required`。

## 真实 provider run 记录（修复前）

真实 provider proving test（模型供应商证明测试）命令形态：

```bash
set -a; source /Users/bill/projects/boardroom-os/.env; set +a; BOARDROOM_RUN_REAL_PROVIDER_PROVING=1 PYTHONPATH=src:. python -m pytest tests/proving/test_v2_090i_medium_scenario.py -q --tb=short --basetemp .pytest-tmp-v2090i-medium-real
```

### Run 1

- run id：`boardroom-atomic.v2-090i.medium.20260610T145623Z.cbc1565e`
- event stream（事件流）：`.evidence/atomic-agent/events/boardroom-atomic.v2-090i.medium.20260610T145623Z.cbc1565e.jsonl`
- pytest 结果：失败，耗时 610.35s
- event counts（事件计数）：`provider.turn.completed=10`、`action.rejected=7`、`workspace.mutation.recorded=2`、`tool.attempt.completed=3`、`command.completed=0`
- terminal event（终止事件）：`run.failed`
- failure kind（失败类型）：`action_parse_failed`
- 观察：provider 多次输出 invalid JSON 或旧 `action_envelope` schema（动作信封结构）；写出 `work/forecast_engine/__init__.py` 与 `work/forecast_engine/statistics.py` 后失败。

### Run 2

- run id：`boardroom-atomic.v2-090i.medium.20260610T150942Z.6856ed07`
- event stream（事件流）：`.evidence/atomic-agent/events/boardroom-atomic.v2-090i.medium.20260610T150942Z.6856ed07.jsonl`
- pytest 结果：失败，耗时 287.48s
- event counts（事件计数）：`provider.turn.completed=3`、`action.rejected=2`、`workspace.mutation.recorded=0`、`tool.attempt.completed=1`、`command.completed=0`
- terminal event（终止事件）：`run.failed`
- failure kind（失败类型）：`policy_denied`
- 观察：provider 已能输出合法 action（动作），但选择 `apply_patch` 一次写多文件；当前 permission policy（权限策略）拒绝，错误为 `invalid_path_type_denied`。

### Run 3

- run id：`boardroom-atomic.v2-090i.medium.20260610T151602Z.f22b41dc`
- event stream（事件流）：`.evidence/atomic-agent/events/boardroom-atomic.v2-090i.medium.20260610T151602Z.f22b41dc.jsonl`
- pytest 结果：失败，耗时 849.23s
- event counts（事件计数）：`provider.turn.completed=11`、`action.rejected=7`、`workspace.mutation.recorded=4`、`tool.attempt.completed=4`、`command.completed=0`
- terminal event（终止事件）：`run.failed`
- failure kind（失败类型）：`action_parse_failed`
- 观察：禁用 `apply_patch` 后，provider 写出 `work/forecast_engine/__init__.py`、`statistics.py`、`risk.py`、`cli.py`；但未生成 `work/tests/test_forecast_engine.py`，未运行 `cmd.check-medium-scenario`，最终仍因 invalid JSON / `action_parse_failed` 失败。

第三次失败后 workspace（工作区）残留文件：

```text
.evidence/atomic-agent/v2-090i-medium-scenario-workspace/.boardroom-v2-090i-workspace.json
.evidence/atomic-agent/v2-090i-medium-scenario-workspace/work/forecast_engine/__init__.py
.evidence/atomic-agent/v2-090i-medium-scenario-workspace/work/forecast_engine/cli.py
.evidence/atomic-agent/v2-090i-medium-scenario-workspace/work/forecast_engine/risk.py
.evidence/atomic-agent/v2-090i-medium-scenario-workspace/work/forecast_engine/statistics.py
```

## 真实 provider run 记录（V2-090J 修复后）

V2-090J 已修复 atomic-agent action protocol（原子智能体动作协议）、`apply_patch` 可见性策略、required-output checkpoint（必需产物检查点）和 provider system prompt（模型供应商系统提示词）后，复跑 V2-090I 原 runner。

### Pytest gate

命令：

```bash
set -a; source .env; set +a; BOARDROOM_RUN_REAL_PROVIDER_PROVING=1 PYTHONPATH=src:. python -m pytest tests/proving/test_v2_090i_medium_scenario.py -q --tb=short --basetemp .pytest-tmp-v2090i-medium-real-rerun
```

结果：

```text
1 passed in 222.99s
```

run id：`boardroom-atomic.v2-090i.medium.20260611T155920Z.5f0c3ba9`

事件流摘要：

- terminal event（终止事件）：`run.completed`
- `provider.turn.completed=7`
- `workspace.mutation.recorded=5`
- `command.completed=2`，`cmd.check-medium-scenario` 先返回 3 后修复到 0
- `result.submitted=1`
- 无 `action.rejected`

该 run 证明 validator command（验证命令）参与了修复循环，而不是源码一次写出后直接提交。

### Independent runner report

命令：

```bash
set -a; source .env; set +a; PYTHONPATH=src:. python scripts/run_v2_090i_medium_scenario.py --reset
```

结果：exit 0。

run id：`boardroom-atomic.v2-090i.medium.20260611T160350Z.9f07d150`

JSON report（报告）关键字段：

- `success=true`
- `terminal_event_type="run.completed"`
- `provider_transport_kind="real"`
- `provider_turn_completed_count=10`
- `action_rejected_count=0`
- `retry_rate=0.0`
- `command_exit_codes["cmd.check-medium-scenario"]=0`
- `workspace_mutation_paths` 包含 9 条 mutation（变更），覆盖全部 5 个 required output（必需产物）
- `source_lineage_inputs` 包含 5 条源码来源链输入，分别绑定 `__init__.py`、`statistics.py`、`risk.py`、`cli.py` 和 `tests/test_forecast_engine.py`
- `events_hash="sha256:ab242b8aedc400769aab7aa1a49a66504e6ca0045a37384f51826cc6979a8704"`

## 自审结论

- 未发现 mocked success path（模拟成功路径）：2026-06-10 真实 provider proving test（模型供应商证明测试）失败后保持失败；2026-06-11 更新状态只基于新鲜真实 provider pytest gate（门禁测试）和独立 runner report（运行器报告）均通过。
- 未发现 silent fallback（静默降级）：缺 provider secret（模型供应商密钥）时 fail closed；真实 happy path 固定 `provider_transport_kind="real"`。
- 未发现 second source of truth（第二事实源）：provider/runtime/role 配置继续来自 `.env` config paths（配置路径）和既有 YAML；runner 不新增 model/base URL/timeout 配置源。
- 已修正 hardcoded configurable option（硬编码可配置项）：移除脚本内 `reasoning_effort="high"` 默认值。
- V2-090I 的非 provider 测试只能证明 runner、guardrail（护栏）和 validator command（验证命令）行为正确；V2-090I acceptance（验收）由 2026-06-11 的真实 provider run 证明。
- 三次历史失败均缺 `cmd.check-medium-scenario` command evidence（命令证据），因此当时不能满足 V2-090I acceptance；修复后独立 runner report 已包含最终 exit 0 的 command evidence、workspace mutation 和 source lineage input。

## 外部评审关注点

- atomic-agent action protocol（动作协议）是否已充分统一 system prompt（系统提示词）、parser（解析器）和 tool schema（工具结构），还是仍应引入 provider-native structured output / tool calling（供应商原生结构化输出 / 工具调用）进一步降低输出漂移风险。
- 中等复杂任务是否应拆为更小 ticket（任务）或由 planner（规划器）生成 staged work plan（阶段计划），而不是单 ticket 一次完成多文件、测试和 CLI。
- permission policy（权限策略）是否应支持受限 `apply_patch`，或 role tools（角色工具）是否必须更强地避免不可用工具。
- parse failure budget（解析失败预算）和 max steps（最大步骤数）能否从 scenario-local override（场景局部覆盖）升级为正式策略，而不是单场景调参。
- validator command（验证命令）是否应更早被 agent loop（智能体循环）强制调用，避免写了部分文件但未运行 command evidence（命令证据）。

## 状态

```text
V2-090I: DONE
V2-090F: BLOCKED
next: expert review of V2-090H/V2-090I/V2-090J evidence before deciding whether to resume V2-090F golden sample rebuild
```
