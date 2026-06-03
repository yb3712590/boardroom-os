# examples

本目录放置示例输入、示例 generated project workspace（生成项目工作区）和示例 process audit（流程审计）。

示例不得伪装为框架源码目录，也不得写到仓库根 `10-project/`、`20-evidence/` 或 `30-audit/`。

建议未来结构：

```text
examples/
├── directives/
├── contracts/
├── generated-workspaces/
└── process-audits/
```

## 当前 golden sample（黄金样例）

`examples/generated-workspaces/tiny-fullstack/` 是 V2-090F Golden sample rebuild（黄金样例重建）的目标产物，但当前 V2-090F 为 BLOCKED（阻塞）。它必须由脚本从真实 closeout evidence loop（收尾证据闭环）生成；旧 V2-080F failure package（失败包）只能作为 regression negative（回归负例）证明被阻断，不能手工修补成通过样例。V2-090F 解阻前，本目录不得被宣称为 passed golden sample（通过黄金样例）。

它由 `scripts/build_tiny_closeout_sample.py` 生成，包含：

- `10-project/`：tiny generated project package（微型生成项目包）；
- `20-evidence/`：SourceInventory（源码清单）、RunManifest（运行清单）、VerificationRun（验证运行）、ServiceRunEvidence（服务运行证据）、LiveBlackboxIntegrationEvidence（真实黑盒集成证据）和 FinalEvidenceTable（最终证据表）；
- `30-audit/`：固定 10 项 ProcessAuditBundle（流程审计包）产物；
- `closeout-package.json`、`replay-bundle.json`、`git-version-audit-bundle.json` 和 `sample-manifest.json`。

该样例目标是 generated project workspace（生成项目工作区）的 golden sample（黄金样例），不是 Boardroom OS 框架源码目录。不要把其中的 `10-project/`、`20-evidence/` 或 `30-audit/` 移到仓库根目录，也不要把它当作 `src/boardroom_os/` 的实现入口。

首次生成在没有有效 provider artifact lock（模型产物锁）时会读取 ignored `.env` / `.env.test` 并调用真实 OpenAI-compatible provider（兼容 OpenAI 的模型供应商）。生成后样例保存真实 ProviderAttempt（模型调用尝试记录）和 raw/parsed provider artifacts（原始/解析模型产物）；后续 `--check` 只重放锁定产物并比较生成树，不再依赖网络调用。篡改 lock、缺 run command final evidence（运行命令最终证据）、缺 service readiness（服务就绪）或缺 live blackbox evidence（真实黑盒证据）都会 fail closed（失败关闭）。但 ProviderAttempt（模型调用尝试记录）只证明 LLM request（大模型请求）事实，不等于 autonomous agent work（自主智能体工作）；V2-090F 需要 AgentWorkExecutor（智能体工作执行器）/ agent loop executor（智能体循环执行器）后才能闭合。

Provider timeout（模型供应商请求超时）由 ignored `.env.test` / `.env` 的 `BOARDROOM_OPENAI_TIMEOUT_SECONDS` 提供；当前本地 V2-090F 生成配置为 `600` 秒。没有有效 provider artifact lock 时，样例构建脚本当前会把同一值用于 provider-backed generation subprocess deadline（模型供应商生成子进程期限）；这是 V2-090F 期间暴露出的临时边界，不得解释为 agent task deadline（智能体任务期限）。缺少该配置会 fail closed（失败关闭）。显式传入 `--provider-deadline-seconds` 才会覆盖默认值。

Provider context window（模型供应商上下文窗口）由 ignored `.env.test` / `.env` 的 `BOARDROOM_OPENAI_CONTEXT_WINDOW` 提供，默认值为 `400000`。已锁定 provider artifact replay（模型产物锁定重放）优先使用样例 `30-audit/agent-context-index.json` 中记录的窗口值，避免本机 `.env` 改动破坏离线 `--check`。

脚本会整体替换样例输出目录；不要在 `examples/generated-workspaces/tiny-fullstack/` 内保留未登记的 `__pycache__`、`.pytest*` 或临时 SQLite 文件。

重生成命令：

```powershell
$env:PYTHONPATH='src;.'; python scripts/build_tiny_closeout_sample.py
$env:PYTHONPATH='src;.'; python scripts/build_tiny_closeout_sample.py --check
```
