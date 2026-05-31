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

`scripts/build_tiny_closeout_sample.py` 生成 V2-080F tiny closeout golden sample（微型收尾黄金样例）。

- 默认输出：`examples/generated-workspaces/tiny-fullstack/`
- `--check`：在临时目录重新生成样例并与当前样例逐字节比较，不修改当前样例
- 生成逻辑复用 `tests/proving/fixtures/tiny_closeout.py`，不复制测试内部拼装逻辑
- 默认调用真实 OpenAI-compatible provider（兼容 OpenAI 的模型供应商）和真实 GitAuditAdapter（Git 审计适配器）；没有 provider 配置、provider attempt（模型调用尝试记录）失败、dirty worktree（脏工作树）或证据不完整都会 fail closed（失败关闭）
- 样例内的 provider artifact lock（模型产物锁）用于稳定重放，不是 mock success path（模拟成功路径）

PowerShell 示例：

```powershell
$env:PYTHONPATH='src;.'; python scripts/build_tiny_closeout_sample.py
$env:PYTHONPATH='src;.'; python scripts/build_tiny_closeout_sample.py --check
```

