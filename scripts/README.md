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
