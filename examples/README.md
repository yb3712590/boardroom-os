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

`examples/generated-workspaces/tiny-fullstack/` 是 V2-090F Golden sample rebuild（黄金样例重建）的目标产物，但当前 V2-090F 为 BLOCKED（阻塞）。2026-06-12 已修订 V2-090F PRD-to-delivery agent team（从 PRD 到交付的智能体团队）spec/plan（规格/计划），等待人工评审后才可恢复实施。它必须由 short PRD（简短产品需求）触发 agent team（智能体团队）自治规划、实施、测试、检查和收尾，并通过 closeout evidence loop（收尾证据闭环）生成；旧 V2-080F failure package（失败包）只能作为 regression negative（回归负例）证明被阻断，不能手工修补成通过样例。V2-090F 完成前，本目录不得被宣称为 passed golden sample（通过黄金样例）。

它由 `scripts/build_tiny_closeout_sample.py` 生成，包含：

- `10-project/`：tiny generated project package（微型生成项目包）；
- `20-evidence/`：SourceInventory（源码清单）、RunManifest（运行清单）、VerificationRun（验证运行）、ServiceRunEvidence（服务运行证据）、LiveBlackboxIntegrationEvidence（真实黑盒集成证据）和 FinalEvidenceTable（最终证据表）；
- `30-audit/`：固定 10 项 ProcessAuditBundle（流程审计包）产物；
- `closeout-package.json`、`replay-bundle.json`、`git-version-audit-bundle.json` 和 `sample-manifest.json`。

该样例目标是 generated project workspace（生成项目工作区）的 golden sample（黄金样例），不是 Boardroom OS 框架源码目录。不要把其中的 `10-project/`、`20-evidence/` 或 `30-audit/` 移到仓库根目录，也不要把它当作 `src/boardroom_os/` 的实现入口。

旧 V2-090F 曾把首次生成建立在 provider artifact lock（模型产物锁）和单次 JSON source delivery（源码交付）上；早期修订又过度倾向 runner 预拆 backend/frontend/integration tickets（后端/前端/集成任务）。这些口径都不能作为 agent team autonomy（智能体团队自治）成功路径。新 V2-090F 必须从 short PRD 出发，由 CEO/Architect/Worker/Tester/Checker/Closeout seats（决策/架构/实施/测试/检查/收尾席位）分别加载自己的 RolePromptHook（角色提示词钩子）、RoleProfile（角色模板）和 skill context（技能上下文），自治产生 contracts（合同）、ticket graph（任务图）、implementation tickets（实施任务）、evidence（证据）和 closeout artifacts（收尾产物）。`ProviderAttempt`（模型调用尝试记录）只证明 LLM request（大模型请求）事实，不等于 autonomous agent work（自主智能体工作）。

新 `--check` 语义必须只验证已发布样例的 PRD sha256、baseline hash（基线哈希）、角色上下文快照、manifest（清单）、文件 hash（哈希）、证据引用、closeout payload（收尾载荷）和禁用运行时文件；不得调用 provider（模型供应商），不得写 output root（输出根目录），也不得单独作为 agent team framework（智能体团队框架）端到端成立证据。

旧 provider timeout（模型供应商请求超时）、provider-backed generation subprocess deadline（模型供应商支撑生成子进程期限）和 provider context window（模型供应商上下文窗口）记录只作为历史阻塞证据保留；新 V2-090F 的执行预算必须来自 Boardroom runtime/provider/role configuration（运行时/供应商/角色配置）和 atomic-agent budget policy（原子智能体预算策略），不得恢复旧 `.env` 模型参数路径作为第二来源，也不得让所有角色共用 `seat.worker.implementation`（工人实施席位）作为正式基线。

V2-090F 将使用独立 `config/boardroom-runtime.v2-090f.yaml`、`config/boardroom-providers.v2-090f.yaml` 和 `config/boardroom-roles.v2-090f.yaml` 作为 high-budget baseline（高预算基线）。预算、timeout（超时）和 retry policy（重试策略）必须进入样例 `00-boardroom/v2-090f-baseline.json`；`--check` 会验证这些 hash 是否漂移。

脚本完成实施后会整体替换样例输出目录；不要在 `examples/generated-workspaces/tiny-fullstack/` 内保留未登记的 `__pycache__`、`.pytest*`、临时 SQLite 文件或端口文件。

重生成命令：

```powershell
$env:PYTHONPATH='src;.'; python scripts/build_tiny_closeout_sample.py
$env:PYTHONPATH='src;.'; python scripts/build_tiny_closeout_sample.py --check
```
