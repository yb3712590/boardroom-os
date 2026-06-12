# scripts

本目录放置开发、验证、文档检查和本地工具脚本。

脚本不得绕过 contract、reducer、evidence 或 closeout gate。

建议未来脚本：

```text
scripts/check_docs.py
scripts/run_negative_tests.sh
scripts/run_proving_scenario.sh
scripts/build_process_audit_sample.py
scripts/build_tiny_closeout_sample.py
```

## 当前脚本

`scripts/build_tiny_closeout_sample.py` 是 V2-090F PRD-to-delivery agent team golden sample（从 PRD 到交付的智能体团队黄金样例）公开构建/检查入口；当前 V2-090F 为 BLOCKED（阻塞），2026-06-12 已修订 spec/plan（规格/计划）并等待人工评审。脚本改动只能作为阶段性进度，不能宣称 golden sample（黄金样例）已通过。

- 默认输出：`examples/generated-workspaces/tiny-fullstack/`
- 新 `--check` 目标语义：只验证已发布样例的 PRD sha256、baseline hash（基线哈希）、角色上下文快照、manifest（清单）、文件 hash（哈希）、证据引用、closeout payload（收尾载荷）和禁用运行时文件；不得调用 provider（模型供应商），不得写 output root（输出根目录）
- 默认 build 委托 `scripts/run_v2_090f_prd_agent_team.py`，必须显式 opt-in 真实 provider run（模型供应商运行）；未设置 `BOARDROOM_RUN_REAL_PROVIDER_PROVING=1` 时失败退出，不生成伪样例
- 默认 build 目标语义：读取 short PRD（简短产品需求），启动 CEO/Architect/Worker/Tester/Checker/Closeout agent seats（决策/架构/实施/测试/检查/收尾智能体席位）自治生成 contracts（合同）、ticket graph（任务图）、implementation tickets（实施任务）、verification plan（验证计划）、evidence（证据）和 closeout artifacts（收尾产物）
- 旧 provider artifact lock（模型产物锁）、provider-backed generation subprocess（模型供应商支撑生成子进程）、单次 JSON source delivery（源码交付）和 runner 预拆固定 ticket graph（固定任务图）已经降级为腐化边界，不能作为 V2-090F 成功证据
- 旧 V2-080F failure package（失败包）只能作为 regression negative（回归负例）证明被阻断
- `AgentRunResult.status == completed`（智能体运行完成）只能作为 execution facts（执行事实），不得直接映射为 `TICKET_COMPLETED`（任务完成）或 `CloseoutPackage.passed`（收尾包通过）
- 所有角色共用 `seat.worker.implementation`（工人实施席位）不能作为正式 agent team baseline（智能体团队基线）；必须验证每个角色加载自己的 RolePromptHook（角色提示词钩子）和 skill context（技能上下文）
- V2-090F 使用独立 high-budget config baseline（高预算配置基线）：`config/boardroom-runtime.v2-090f.yaml`、`config/boardroom-providers.v2-090f.yaml`、`config/boardroom-roles.v2-090f.yaml`。预算、timeout（超时）和 retry policy（重试策略）不得通过 `.env` 临时覆盖。

PowerShell 示例：

```powershell
$env:PYTHONPATH='src;.'; python scripts/build_tiny_closeout_sample.py
$env:PYTHONPATH='src;.'; python scripts/build_tiny_closeout_sample.py --check
```

## V2-090I medium scenario runner

`scripts/run_v2_090i_medium_scenario.py` 运行 V2-090I Resettable Medium Scenario（可重置中等复杂场景）。它派发一个 real provider-backed atomic-agent implementation ticket（真实模型供应商支撑的原子智能体实施任务），要求在标记 workspace（工作区）下创建多文件 `forecast_engine` Python package（Python 包）和 CLI（命令行工具）。

- Default workspace（默认工作区）：`.evidence/atomic-agent/v2-090i-medium-scenario-workspace/`
- `--reset`：只删除并重建带 V2-090I marker（标记文件）的 workspace；若目录存在但缺 `.boardroom-v2-090i-workspace.json`，脚本 fail closed（失败关闭）而不是删除目录。
- Provider/runtime/role configuration（模型供应商 / 运行时 / 角色配置）仍只来自 `.env` config paths（配置路径）以及 `config/boardroom-runtime.example.yaml`、`config/boardroom-providers.example.yaml`、`config/boardroom-roles.example.yaml`。
- 完整 pytest 默认跳过真实 provider test（模型供应商测试），除非同时设置 `BOARDROOM_RUN_REAL_PROVIDER_PROVING=1` 和 `OPENAI_API_KEY`。
- 当前状态：V2-090J action protocol repair（原子动作协议修复）后复跑通过。2026-06-11 `tests/proving/test_v2_090i_medium_scenario.py` 显式 opt-in 通过（`1 passed in 222.99s`）；独立 runner report（运行器报告）`boardroom-atomic.v2-090i.medium.20260611T160350Z.9f07d150` 也通过，包含 10 个 provider turns（模型轮次）、9 条 workspace mutations（工作区变更）、`cmd.check-medium-scenario` command evidence（命令证据，最终 exit 0）、5 条 source lineage inputs（源码来源链输入）和 `run.completed`。

PowerShell example:

```powershell
$env:PYTHONPATH='src;.'; $env:BOARDROOM_RUN_REAL_PROVIDER_PROVING='1'; python -m pytest tests/proving/test_v2_090i_medium_scenario.py -q --tb=short
```

POSIX shell example:

```bash
set -a; source .env; set +a; BOARDROOM_RUN_REAL_PROVIDER_PROVING=1 PYTHONPATH=src:. python -m pytest tests/proving/test_v2_090i_medium_scenario.py -q --tb=short --basetemp .pytest-tmp-v2090i-medium-real
```

## V2-090J medium scenario runner

`scripts/run_v2_090j_medium_scenario.py` 运行 V2-090J Atomic action protocol repair（原子动作协议修复）中等场景。它复用 V2-090I medium scenario（中等场景）目标，但允许显式 `AgentActionBatch`（智能体动作批次）或单个 `AgentAction`（智能体动作），要求 resolved `max_actions_per_turn`（解析后每轮最大动作数）大于 1，且 required-output checkpoint（必需产物检查点）的 `max_auto_runs` 来自 runtime config（运行时配置）。

- Default workspace（默认工作区）：`.evidence/atomic-agent/v2-090j-medium-scenario-workspace/`
- `--reset`：只删除并重建带 V2-090J marker（标记文件）的 workspace；若目录存在但缺 `.boardroom-v2-090j-workspace.json`，脚本 fail closed（失败关闭）。
- 完整 pytest 默认跳过真实 provider test（模型供应商测试），除非同时设置 `BOARDROOM_RUN_REAL_PROVIDER_PROVING=1` 和 `OPENAI_API_KEY`。
- 成功报告必须包含 `action_protocol="agent-action-batch-v1"`、`max_actions_per_turn > 1`、`checkpoint_max_auto_runs >= 1`、`cmd.check-medium-scenario` exit 0、workspace mutation（工作区变更）和 source lineage input（源码来源链输入）。
- 2026-06-11 复跑结论：一次真实 provider run 因 provider output（模型输出）串联多个 JSON 后又遇到 provider SDK connection error（供应商 SDK 连接错误）失败；随后 `tests/proving/test_v2_090j_medium_scenario.py` 显式 opt-in 通过（`1 passed in 505.05s`），独立 runner report（运行器报告）`boardroom-atomic.v2-090j.medium.20260611T060341Z.b564b20d` 也通过，包含 8 个 provider turns（模型轮次）、11 个 workspace mutations（工作区变更）、6 次 `cmd.check-medium-scenario` command evidence（命令证据，最终 exit 0）、source lineage input（源码来源链输入）和 `run.completed`。

POSIX shell example:

```bash
set -a; source .env; set +a; BOARDROOM_RUN_REAL_PROVIDER_PROVING=1 PYTHONPATH=src:. python -m pytest tests/proving/test_v2_090j_medium_scenario.py -q --tb=short --basetemp .pytest-tmp-v2090j-medium-real
```
