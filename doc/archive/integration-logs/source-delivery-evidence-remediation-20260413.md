# Source Delivery Evidence Remediation - 2026-04-13

> 这是按 `doc/tests/integration-audit-remediation-master-plan-20260413.md` 落的第一批执行记录。
> 范围只收 3 件事：`P0-2`、`P0-3`、`P1-3`。

## 本轮结论

这轮先把 `source_code_delivery` 的假阳性入口收掉了。

现在主线不再接受下面这些东西混成“已完成”：

- 固定 `source.ts / source.tsx` 这类占位文件名
- `runtimeSourceDelivery = true`
- `generated for <ticket>`
- 空 stdout / stderr
- 只有一句 `pytest -q passed`
- 多张代码票共用同一个测试证据路径或 git 证据路径

## 已落地变更

### 1. `source_code_delivery@1` 扩成真实交付包

- payload 现在必须带：
  - `source_files[]`
  - `verification_runs[]`
- `source_file_refs[]` 继续保留，但必须和 `source_files[].artifact_ref` 一一对齐
- `verification_evidence_refs[]` 继续保留，但对 workspace-managed 代码票，必须和 `verification_runs[].artifact_ref` 一一对齐

### 2. Schema 先拦明显假内容

- `backend/app/core/output_schemas.py` 现在会直接拦：
  - 缺 `source_files[]`
  - 缺 `verification_runs[]`
  - 源码正文为空或明显是占位模板
  - 测试运行详情没有原始 stdout
  - 测试发现数还是 `0`

### 3. Runtime 默认产物不再写占位源码和极简测试 JSON

- `backend/app/core/runtime.py` 现在不再生成：
  - `source.tsx`
  - `pytest -q passed`
  - 伪造 commit sha
- `source_code_delivery` 默认会转成：
  - 真实源码正文写入 `written_artifacts`
  - 结构化 `verification_runs[]` 写入 `written_artifacts`
  - git 证据路径先占位，真正的 `git_commit_record` 由 workspace commit 后回填

### 4. 证据路径改成按票隔离

- 测试证据：
  - `20-evidence/tests/<ticket_id>/attempt-1/test-report.json`
- git 证据：
  - `20-evidence/git/<ticket_id>/attempt-1/git-closeout.json`
- 这轮没有给 `artifact_index.logical_path` 加全局唯一约束。
- 当前做法是把主线路径策略先收正，避免多张代码票继续写同一路径。

### 5. Live harness 成功断言收紧

- `backend/tests/live/_autopilot_live_harness.py` 现在会额外检查：
  - `source_code_delivery` terminal payload 里必须有 `source_files[] / verification_runs[]`
  - `verification_runs[].stdout` 不能空
  - 同一个 workflow 下，`20-evidence/tests/` 和 `20-evidence/git/` 不能跨票撞路径

## 本轮验证

已实跑通过：

```bash
./backend/.venv/Scripts/python -m pytest backend/tests/test_output_schemas.py -q
./backend/.venv/Scripts/python -m pytest backend/tests/test_project_workspace_hooks.py -q
./backend/.venv/Scripts/python -m pytest backend/tests/test_runtime_fallback_payload.py -q
./backend/.venv/Scripts/python -m pytest backend/tests/test_live_library_management_runner.py -q
./backend/.venv/Scripts/python -m pytest backend/tests/test_workflow_autopilot.py -q
```

## 当前还没收的点

- `test_api.py` 和 `test_scheduler_runner.py` 里那批依赖旧 deterministic 主线的历史测试，当前仍会被 provider fail-closed 链路打断。
- 这不是本轮第一批新增的问题，但它会影响更大范围回归。
- 第二批建议先收：
  - `P1-1` 场景级审计摘要正式化
  - `P1-2` 巡检报告去重
  - 然后再回头把 provider fail-closed 后的历史测试口径整体重写一遍
