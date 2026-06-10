# V2-090I 可重置中等复杂实施场景设计

## 目标

V2-090I（Resettable Medium Scenario，可重置中等复杂场景）在 V2-090H（Atomic-agent executor switch，原子智能体执行器切换）和 V2-090F（Golden sample rebuild，黄金样例重建）之间增加一个专项 proving stage（证明阶段）。它验证真实 provider-backed atomic-agent executor（模型供应商支撑的原子智能体执行器）能交付中等复杂、多文件、带文件间依赖、带真实命令验证的 implementation ticket（实施任务）。

本阶段优先证明“从小规模单文件到中等规模可运行包”的可信交付能力。Retry cost（重试成本）不是失败条件；可信 evidence（证据）、workspace mutation（工作区变更）、command evidence（命令证据）和 source lineage input（源码来源链输入）才是验收重点。

## 背景

V2-090H 已证明单个最小 implementation ticket 可以通过真实 provider-backed atomic-agent executor 写入文件、运行命令并提交结果。Retry-rate probe（重试率探针）进一步证明三个不同单文件 ticket 均可完成，但仍未证明：

- 多目录、多文件项目写入；
- 文件间 import（导入依赖）；
- 生成测试文件并运行真实测试命令；
- 中等复杂函数/算法逻辑；
- 可重置 workspace（工作区）以避免残留状态污染专项验证。

V2-090I 补齐这些能力，但不直接进入 HTTP service（HTTP 服务）、SQLite persistence（SQLite 持久化）或 frontend/backend integration（前后端集成）。这些仍留给 V2-090F。

## 场景范围

V2-090I 构造一个单 ticket、单 workspace 的中等复杂 CLI/package（命令行/包）场景：

```text
ticket.medium.forecast-engine
```

Agent（智能体）需要在 `work/` 下生成一个标准库 Python package（Python 包）：

```text
work/forecast_engine/
  __init__.py
  statistics.py
  risk.py
  cli.py
work/tests/
  test_forecast_engine.py
```

该场景按“方案 B”的复杂度规模设计：它不是简单 math utils（数学工具）包，而是一个小型 time-series forecast and risk CLI（时间序列预测与风险命令行工具）。函数逻辑必须包含多步数学/算法计算，不能只做加减乘除或字符串拼接。

## 行为契约

Agent 生成的 package 必须至少提供以下 public API（公开接口）：

- `weighted_moving_average(values, window)`：使用最近 `window` 个数值和三角权重 `1..window` 计算加权移动平均。
- `linear_regression_forecast(values)`：使用最小二乘线性回归，令 `x = 0..n-1`，预测 `x = n` 的下一点。
- `max_drawdown(values)`：扫描序列，计算从历史峰值到后续低点的最大回撤比例。
- `analyze_series(values)`：组合 mean（均值）、population standard deviation（总体标准差）、weighted moving average（加权移动平均）、linear regression forecast（线性回归预测）、max drawdown（最大回撤）和 trend penalty（趋势惩罚），返回包含 `risk_score` 与 `risk_level` 的 dict（字典）。

`risk.py` 必须 import `statistics.py` 中的计算函数，不能把所有逻辑塞进单文件。`cli.py` 必须能读取 JSON 输入文件并输出 JSON 报告，供真实命令验证调用。

推荐算法定义：

```text
mean_abs = abs(mean(values)) or 1.0
volatility = population_stddev(values) / mean_abs
trend_ratio = regression_slope(values) / mean_abs
negative_trend = max(0.0, -trend_ratio)
risk_score = round(min(100.0, volatility * 45.0 + max_drawdown(values) * 35.0 + negative_trend * 20.0), 4)
risk_level = low if score < 8.0; medium if score < 20.0; high otherwise
```

实现可以拆出内部 helper（辅助函数），但最终 public API 和 CLI behavior（命令行行为）必须稳定。

## 可重置 workspace

V2-090I 必须使用专用 workspace：

```text
.evidence/atomic-agent/v2-090i-medium-scenario-workspace/
```

Runner（运行脚本）必须提供显式 reset（重置）入口，例如：

```bash
python scripts/run_v2_090i_medium_scenario.py --reset
```

Reset 必须 fail closed（失败关闭）：

- 只允许删除 V2-090I 专用 workspace；
- workspace 首次创建时写入 marker file（标记文件），例如 `.boardroom-v2-090i-workspace.json`；
- 若目标目录已存在但缺 marker file，脚本必须拒绝删除；
- reset 后 workspace 必须重新创建 `work/` 目录并清空旧产物。

该机制防止旧文件让 scenario（场景）误通过，也防止脚本误删非本场景目录。

## 配置来源

真实 provider（模型供应商）配置仍只来自：

- `.env` / `.env.test` 中的 config path（配置路径）、secret（密钥）和 bootstrap path（启动路径）；
- `config/boardroom-runtime.example.yaml`；
- `config/boardroom-providers.example.yaml`；
- `config/boardroom-roles.example.yaml`。

V2-090I 不得引入新的 provider 配置源，不得恢复旧 `BOARDROOM_OPENAI_*` 模型参数路径，不得在脚本中硬编码 model/base URL/timeout/reasoning effort（模型、基础地址、超时、推理强度）。脚本只能通过 `load_boardroom_settings`（加载董事会配置）解析 settings（配置对象），再由 role slot（角色席位）引用 provider profile（供应商配置档）。

## 专项测试与全量测试行为

V2-090I 的真实 provider proving test（真实供应商证明测试）默认跳过，避免 full suite（完整测试套件）被真实 provider 调用拖慢。测试只有在以下条件同时满足时运行：

```text
OPENAI_API_KEY 存在
BOARDROOM_RUN_REAL_PROVIDER_PROVING=1
```

专项测试必须先初始化场景，即调用 runner 的 `--reset` 路径，然后执行真实 provider-backed run（模型供应商支撑运行）。全量测试若未显式 opt-in（选择加入），必须跳过真实 provider 调用。

非 provider 单元测试应覆盖 reset safety（重置安全）、run id（运行编号）格式、ExecutionPackage（执行包）构造和 validator command（验证命令）基础约束。

## 验收证据

Runner 成功时必须输出 JSON report（报告），至少包含：

- `ticket_ref`；
- `execution_package_id`；
- `atomic_run_id`；
- `workspace_root`；
- `event_stream_ref`；
- `events_hash`；
- `provider_attempt_ref`；
- `work_product_ref`；
- `command_exit_codes`；
- `workspace_mutation_paths`；
- `source_lineage_inputs`；
- `provider_turn_completed_count`；
- `action_rejected_count`；
- `retry_rate`；
- `success`。

成功条件：

- terminal event（终止事件）为 `run.completed`；
- 至少一个 `provider.turn.completed`；
- `cmd.check-medium-scenario` exit code 为 `0`；
- 所有 required output paths（必需输出路径）存在；
- event stream summary（事件流摘要）包含 workspace mutation paths；
- `source_lineage_inputs` 非空；
- `provider_transport_kind` 为 `real`；
- reset 后生成的文件来自本轮运行，不依赖旧残留。

## 外部验证命令

`ExecutionPackage.commands`（执行包命令集合）必须包含一个外部验证命令：

```text
cmd.check-medium-scenario
```

该命令必须独立验证：

1. 必需文件存在；
2. `risk.py` 对 `statistics.py` 存在真实 import 依赖；
3. package 可从 `work/` import；
4. public API 对多个非平凡输入返回正确结果；
5. `python -m unittest discover -s work/tests -p "test_*.py"` 通过；
6. `python -m forecast_engine.cli <input.json>` 输出可解析 JSON，且包含稳定 key（键）和值。

验收不能只依赖 agent 自己生成的 tests（测试），也不能只做源码字符串检查。源码结构检查可以作为辅助，但最终必须运行 import/API/CLI/test command（导入/API/命令行/测试命令）。

## Fail-closed 规则

以下情况必须失败：

- 目标 workspace 已存在但没有 V2-090I marker file；
- 未显式 reset 的专项测试复用旧产物；
- agent 只写单文件或缺任一 required output path；
- `risk.py` 没有依赖 `statistics.py`；
- public API 缺失或输出不符合算法契约；
- `work/tests/test_forecast_engine.py` 缺失或 unittest 失败；
- CLI 不能读取 JSON 输入或输出 JSON 报告；
- command evidence 缺失或 exit code 非 0；
- event stream 缺 provider turn facts（模型轮次事实）；
- workspace mutation 或 source lineage input 为空；
- runner 使用 fake provider transport（模拟供应商传输）；
- runner 从脚本硬编码 provider 参数，绕过 `.env` 和 yaml 配置。

## 非目标

V2-090I 不做：

- CEO / Architect / Worker / Tester 多 ticket 协同；
- HTTP service startup/readiness（HTTP 服务启动/就绪）；
- SQLite persistence（SQLite 持久化）；
- frontend/backend live integration（前后端真实集成）；
- CloseoutPackage passed（收尾包通过）；
- tiny-fullstack golden sample rebuild（微型全栈黄金样例重建）；
- 将 retry rate 高低作为成功/失败门槛。

## 后续交接

V2-090I 通过后，只能说明中等复杂单 ticket implementation（单任务实施）可由真实 provider-backed atomic-agent executor 可信交付。它为恢复 V2-090F 提供前置信心，但不自动解除 V2-090F 的 BLOCKED（阻塞）状态。是否恢复 V2-090F 仍需要人工评审 V2-090H 与 V2-090I 的 evidence（证据）。

## 自审结果

- 占位符扫描：无未定义占位内容；所有路径、命令、配置源和验收条件均已具体化。
- 一致性检查：场景定位为单 ticket 中等复杂 package/CLI，与“不进入 090F 全栈复杂度”的边界一致。
- 范围检查：本 spec 聚焦一个可独立实施和验证的 proving stage，不拆分为多个独立子项目。
- 歧义检查：全量测试跳过条件、专项 reset 行为、provider 配置权威源和 fail-closed 条件均已明确。
