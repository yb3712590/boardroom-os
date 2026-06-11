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

`scripts/build_tiny_closeout_sample.py` 是 V2-090F blackbox-evidence-backed golden sample（黑盒证据支撑黄金样例）构建入口；当前 V2-090F 为 BLOCKED（阻塞），脚本改动只能作为阶段性进度，不能宣称 golden sample（黄金样例）已通过。

- 默认输出：`examples/generated-workspaces/tiny-fullstack/`
- `--check`：在临时目录重放已锁定 ProviderAttempt（模型调用尝试记录）并与当前样例逐字节比较，不修改当前样例
- 生成逻辑复用 `tests/proving/fixtures/tiny_closeout.py`，不复制测试内部拼装逻辑
- 默认 build 在无有效 provider artifact lock（模型产物锁）时调用真实 OpenAI-compatible provider（兼容 OpenAI 的模型供应商）和真实 GitAuditAdapter（Git 审计适配器）；没有 provider 配置、provider attempt 失败、run command final evidence（运行命令最终证据）缺失、service readiness（服务就绪）缺失或 live blackbox evidence（真实黑盒证据）不完整都会 fail closed（失败关闭）
- Provider timeout（模型供应商请求超时）必须来自 ignored `.env.test` / `.env` 的 `BOARDROOM_OPENAI_TIMEOUT_SECONDS`；当前本地 V2-090F 生成配置为 `600` 秒。无 provider artifact lock 时，脚本当前使用同一值作为 provider-backed generation subprocess deadline（模型供应商生成子进程期限）；这是 V2-090F 阻塞期间的临时执行边界，不是 agent task deadline（智能体任务期限）。缺少该 env 项会 fail closed。`--provider-deadline-seconds` 仅用于显式人工覆盖，不是默认第二来源。
- Provider context window（模型供应商上下文窗口）由 ignored `.env.test` / `.env` 的 `BOARDROOM_OPENAI_CONTEXT_WINDOW` 提供，默认值为 `400000`。已锁定 provider artifact replay（模型产物锁定重放）优先使用样例 `30-audit/agent-context-index.json` 中记录的窗口值，避免本机 `.env` 改动破坏离线 `--check`。
- 样例内的 provider artifact lock 用于离线稳定重放，不是 mock success path（模拟成功路径）；旧 V2-080F failure package（失败包）只能作为 regression negative（回归负例）证明被阻断
- ProviderAttempt（模型调用尝试记录）只证明 LLM request（大模型请求）事实，不等于 autonomous agent work（自主智能体工作）。V2-090F 解阻前，必须先补 AgentWorkExecutor（智能体工作执行器）/ agent loop executor（智能体循环执行器），让 agent 能读写 workspace（工作区）、运行命令、多轮修复并产出 evidence（证据）。

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
- 当前状态：三次 real-provider attempts（真实模型供应商尝试）后仍为 BLOCKED（阻塞）。runner（运行器）与 fail-closed tests（失败关闭测试）是评审产物；只有 real provider proving test（真实供应商证明测试）通过后，V2-090I 才能被接受。

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

POSIX shell example:

```bash
set -a; source .env; set +a; BOARDROOM_RUN_REAL_PROVIDER_PROVING=1 PYTHONPATH=src:. python -m pytest tests/proving/test_v2_090j_medium_scenario.py -q --tb=short --basetemp .pytest-tmp-v2090j-medium-real
```
