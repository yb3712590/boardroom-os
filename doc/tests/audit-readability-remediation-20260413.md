# Audit Readability Remediation - 2026-04-13

> 这是按 `doc/tests/integration-audit-remediation-master-plan-20260413.md` 落的第二批执行记录。
> 这轮只收 4 件事：`P1-1`、`P1-2`、`P2-1`、`P2-2`。

## 本轮结论

第二批把“人怎么审这轮长测”这层入口收正了。

现在场景根目录已经有 4 份固定的人类入口：

- `audit-summary.md`
- `integration-monitor-report.md`
- `artifacts/reports/governance/<ticket>/*.audit.md`
- `ticket_context_archives/<ticket>.md`

第三方现在不用先翻数据库和大 JSON，也能先判断：

- 这轮跑到哪一阶段
- 当前卡在哪张票
- governance 链产出了什么结论
- 某张 ticket 编译时到底吃了哪些上下文

## 已落地变更

### 1. `audit-summary.md` 升成正式版

- shared harness 现在会固定输出：
  - 场景名
  - 起止时间和耗时
  - workflow 阶段流转
  - ticket 完成 / 失败 / pending 数
  - 当前活跃 ticket
  - provider 摘要与候选链
  - governance 文档产出链
  - 代码 / 测试 / git 证据概览
  - approval / incident 汇总
  - 最长静默区间

### 2. `integration-monitor-report.md` 改成变化点报告

- 这份文件现在由 shared harness 自动生成，不再依赖人工手记
- 只在状态变化时追加
- 长时间无变化时，不再刷一堆“无变化”心跳
- 恢复变化时会补一条“静默 X 分钟后恢复”

### 3. governance JSON 自动旁挂 `.audit.md`

- 五类治理文档 JSON 现在都会自动生成同目录同 basename 的 `.audit.md`
- `.audit.md` 只保留：
  - 摘要
  - 关键决策
  - 关键约束
  - 各节 `content_markdown`
- 不再把 `linked_artifact_refs / source_process_asset_refs / linked_document_refs / content_json` 这类机器字段直接扔给人看

### 4. `ticket_context_archives` 改成执行卡片

- 每张 ticket 的 markdown 现在会直接展示：
  - 基本信息
  - 输入上下文来源表
  - token 预算与实际使用
  - truncated / degradation / cache hit
  - allowed write set
  - checkout / git branch
  - terminal 后的实际 artifact 路径
- 这份文件会保留“一票一文件”
- runtime compile 后先写第一版
- ticket 完成或失败后，会用同名文件刷新最终状态

## 本轮验证

已实跑通过：

```bash
./backend/.venv/Scripts/python -m pytest backend/tests/test_live_library_management_runner.py -q
./backend/.venv/Scripts/python -m pytest backend/tests/test_project_workspace_hooks.py -q
./backend/.venv/Scripts/python -m pytest backend/tests/test_ticket_context_archive.py -q
./backend/.venv/Scripts/python -m pytest backend/tests/test_live_library_management_runner.py backend/tests/test_project_workspace_hooks.py backend/tests/test_ticket_context_archive.py -q
```

## 当前还没收的点

- `P2-3 developer_inspector 减冗余` 这轮没动，当前仍保留三份 JSON。
- `P2-4 project workspace 入口收口` 这轮也没动，目录层级负担还在。
- 真实 provider 长测还没在这台机器上重跑通过。
- `test_api.py / test_scheduler_runner.py` 里那批 fail-closed 后的历史测试，仍要单独收口。

## 第三批建议

- 先收 `P2-3 developer_inspector 减冗余`
- 再收 `P2-4 workspace 入口收口`
- 然后推进 `P3-1 / P3-2` 的流程目标函数和熔断
