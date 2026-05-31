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

`examples/generated-workspaces/tiny-fullstack/` 是 V2-080F tiny closeout（微型收尾）可重生成样例。

它由 `scripts/build_tiny_closeout_sample.py` 生成，包含：

- `10-project/`：tiny generated project package（微型生成项目包）；
- `20-evidence/`：SourceInventory（源码清单）、RunManifest（运行清单）、VerificationRun（验证运行）和 FinalEvidenceTable（最终证据表）；
- `30-audit/`：固定 10 项 ProcessAuditBundle（流程审计包）产物；
- `closeout-package.json`、`replay-bundle.json`、`git-version-audit-bundle.json` 和 `sample-manifest.json`。

该样例是 generated project workspace（生成项目工作区）的 golden sample（黄金样例），不是 Boardroom OS 框架源码目录。不要把其中的 `10-project/`、`20-evidence/` 或 `30-audit/` 移到仓库根目录，也不要把它当作 `src/boardroom_os/` 的实现入口。

首次生成会读取 ignored `.env` / `.env.test` 并调用真实 OpenAI-compatible provider（兼容 OpenAI 的模型供应商）。生成后样例保存 provider artifact lock（模型产物锁），后续重放用锁内 raw/parsed artifacts（原始/解析模型产物）稳定再生成；篡改 lock 会 fail closed（失败关闭）。

脚本在 repository worktree（仓库工作树）dirty（脏）时会拒绝生成或 `--check`。先提交或清理当前改动，再运行脚本级 golden sample 校验。

重生成命令：

```powershell
$env:PYTHONPATH='src;.'; python scripts/build_tiny_closeout_sample.py
$env:PYTHONPATH='src;.'; python scripts/build_tiny_closeout_sample.py --check
```

