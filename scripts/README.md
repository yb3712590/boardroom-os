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

PowerShell 示例：

```powershell
$env:PYTHONPATH='src;.'; python scripts/build_tiny_closeout_sample.py
$env:PYTHONPATH='src;.'; python scripts/build_tiny_closeout_sample.py --check
```

