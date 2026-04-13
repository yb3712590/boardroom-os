# 集成测试审计总整改计划

## 先说结论

这份计划覆盖三类输入：

- `audit-readability-proposal.md`
- `library-management-autopilot-live-audit-20260413.md`
- 本轮补充的 provider / timeout / retry / 禁本地回落问题

整改顺序也先说清：

1. **P0：先收真相**
2. **P1：再收证据**
3. **P2：最后收可读性和体积**

原因很直接。

如果 provider 失败还能补成本地成功，或者交付证据还能被覆盖，那审计目录再好看也没用。

---

## 当前状态

### 已经落地

这轮代码已经落了 P0 的第一段：

- runtime 改成 fail-closed
- 禁止 provider 失败后本地回落成功
- provider 候选链按 `provider_model_entry_refs[]` 顺序执行
- OpenAI-compatible 请求改成 `instructions + input`
- provider 超时拆成 connect / write / first token / stream idle / total
- live harness 会写 `audit-summary.md`
- failure snapshot 已补 `provider_candidate_chain / provider_attempt_log / fallback_blocked / final_failure_kind`

对应专项记录在：

- `doc/tests/provider-runtime-strict-remediation-plan-20260413.md`

### 本轮新增已落地

- 第一批执行切片已落：
  - `source_code_delivery@1` 现在必须带 `source_files[] / verification_runs[]`
  - workspace-managed 代码票会直接拦占位源码和极简测试自报结果
  - `20-evidence/tests|git` 已按 `ticket_id/attempt-1` 分路径
  - live harness full success 已补源码证据质量和证据路径撞车断言

对应专项记录在：

- `doc/tests/source-delivery-evidence-remediation-20260413.md`

### 还没落地

下面这些问题仍然没收：

- 流程繁荣、交付贫瘠
- schema 合规替代真实业务交付
- 测试证据质量太低
- 产物可覆盖，导致不可追溯
- 巡检报告太吵
- governance / inspector / context archive 对人不友好
- project workspace 路径和目录组织负担太重

---

## P0：真相优先

### P0-1 Runtime 严格执行

目标：

- 任何主线 runtime 都只认真实 provider 结果
- provider 不可用时直接失败，不补 deterministic completed

已落地：

- `backend/app/core/runtime.py`
- `backend/app/core/runtime_provider_config.py`
- `backend/app/core/provider_openai_compat.py`
- `backend/app/core/projections.py`
- `frontend/src/pages/dashboard-page-helpers.ts`
- `frontend/src/components/dashboard/RuntimeStatusCard.tsx`

验收口径：

- `ticket_projection.status` 不再因 provider 失败变成 `COMPLETED`
- terminal event 必须保留真实 `failure_kind`
- projection / dashboard 不再出现 `LOCAL_DETERMINISTIC / LOCAL_ONLY`

### P0-2 交付成功条件改真

当前状态：`第一批已落`

目标：

- ticket 完成条件从“schema 对了”改成“产物真能交付”

实施点：

- `backend/app/core/runtime.py`
- `backend/app/core/ticket_handlers.py`
- `backend/app/core/output_schemas.py`
- `backend/app/core/command_handlers.py`

要改的规则：

- `source_code_delivery` 不能只交占位文件
- `written_artifacts` 必须包含真实写入内容
- `verification_evidence_refs` 必须包含原始测试证据
- `git_commit_record` 不能只写摘要，要能回到真实提交或真实 diff

新增门禁：

- 占位源码命中直接失败
- 没有原始测试输出直接失败
- 没有与票范围匹配的实际 artifact 直接失败

验收口径：

- `source_code_delivery` 票的完成事件必须含真实文件写入
- 不能再出现 70 字节左右的占位源码通过主线

### P0-3 证据不可覆盖

当前状态：`第一批已落最小闭环`

目标：

- 同类产物必须版本化或分票隔离，不能再反复覆盖同一路径

实施点：

- `backend/app/core/artifacts.py`
- `backend/app/core/runtime.py`
- `backend/app/db/repository.py`

要改的路径策略：

- `20-evidence/tests/test-report.json` 改成按 `ticket_id` 或 `attempt_no` 分路径
- `20-evidence/git/git-commit.json` 改成按票分路径
- `10-project/src/source.tsx` 这类占位式固定文件名不能再作为主线交付路径

验收口径：

- 同一 workflow 下，多张票不会写同一最终证据路径
- `artifact_index` 不再出现几十次覆盖同一逻辑证据文件

---

## P1：证据层收口

### P1-1 场景级审计摘要正式化

目标：

- 场景根目录一眼看懂

当前已做：

- `audit-summary.md` 基础版已落

还要补：

- workflow 阶段流转
- ticket 完成 / 失败 / pending 数
- 当前活跃 ticket
- provider 选择链
- 最长静默区间
- incident / approval 汇总
- 代码 / 测试 / evidence 产出概览

实施点：

- `backend/tests/live/_autopilot_live_harness.py`

### P1-2 巡检报告去重

目标：

- `integration-monitor-report.md` 只看变化点

实施点：

- 真实 live runner 的 monitor 写入逻辑
- 只在状态跳变时追加
- 连续静默压成一条摘要

验收口径：

- 同规模长测下，报告行数明显下降
- 文件头部能直接看到阶段跳变时间轴

### P1-3 原始测试证据保留

当前状态：`第一批已落最小闭环`

目标：

- 不能只剩一句 `pytest -q passed`

实施点：

- `backend/app/core/runtime.py`
- `backend/app/core/ticket_handlers.py`
- live / smoke 相关测试执行器

最少保留：

- 原始 stdout / stderr
- 测试发现数量
- 用例列表或失败明细
- 耗时
- 关联 ticket / artifact / commit

### P1-4 provider 审计闭环

目标：

- 审计时不用翻内部事件也能看清 provider 行为

实施点：

- `backend/app/core/projections.py`
- `backend/tests/live/_autopilot_live_harness.py`
- `doc/tests/provider-runtime-strict-remediation-plan-20260413.md`

要稳定暴露：

- candidate chain
- 实际命中 provider
- 尝试次数
- 每次失败 kind
- 是否切到 backup provider
- 为什么没切 backup

---

## P2：人工可读层和体积治理

### P2-1 governance 文档旁挂 `.audit.md`

目标：

- JSON 继续给机器用
- 人看同名 `.audit.md`

实施点：

- governance 文档落盘后 post-processor

摘要字段：

- summary
- decisions
- constraints
- section `content_markdown`

明确不出现在 `.audit.md` 里的字段：

- `linked_artifact_refs`
- `source_process_asset_refs`
- `linked_document_refs`
- `section_id`
- 冗余 `content_json`

### P2-2 ticket_context_archives 重写

目标：

- 从“截断 JSON preview”改成“执行卡片”

实施点：

- `backend/app/core/ticket_context_archive.py`

最少包含：

- 基本信息
- 输入上下文来源表
- token 使用情况
- 输出路径
- 截断 / 降级 / cache 命中状态

### P2-3 developer_inspector 减冗余

目标：

- 三份 JSON 至少先做到有索引

短期做法：

- 先加 `inspector-index.md`

长期做法：

- 合并成单票单文件

实施点：

- `backend/app/core/developer_inspector.py`
- compile artifact export 路径

### P2-4 project-workspaces 降认知负担

目标：

- 常见单 workflow 场景，入口别藏太深

短期：

- 根目录补快捷入口或清晰索引

长期：

- 评估是否把单 workflow 场景的 `10-project / 00-boardroom / 20-evidence` 扁平化

---

## P3：流程纠偏

### P3-1 控制面别再奖励“流程痕迹”

目标：

- 奖励真实交付，不奖励票数和落盘次数

实施点：

- `backend/app/core/ceo_proposer.py`
- `backend/app/core/ceo_scheduler.py`
- `backend/app/core/workflow_auto_advance.py`

要改的判断：

- 不再把“产出一个 schema 合法包”当完成业务
- BUILD 票必须绑定真实 write set / diff / test evidence
- governance 票和 implementation 票不能无限 fanout

### P3-2 长期只增票、不增代码时熔断

目标：

- 别再跑几个小时制造成功幻觉

熔断条件：

- 连续 N 张 implementation 票后，总代码量仍低于阈值
- 连续多次命中占位模式
- build 阶段长时间无有效交付增长
- provider 多次失败且没有 backup provider

实施点：

- scheduler monitor
- workflow auto advance
- live harness

---

## 推荐实施顺序

### 第一批

- P0-2 交付成功条件改真
- P0-3 证据不可覆盖
- P1-3 原始测试证据保留

这是下一轮最该做的。

原因：

- 这三项直接决定“是不是还在制造假阳性”

### 第二批

- P1-1 场景级审计摘要正式化
- P1-2 巡检报告去重
- P2-1 governance `.audit.md`
- P2-2 ticket_context_archives 重写

### 第三批

- P2-3 developer_inspector 减冗余
- P2-4 workspace 入口收口
- P3-1 / P3-2 流程目标函数与熔断

---

## 每批验收方式

### 第一批验收

- 真实 `library_management_autopilot_live` 再跑时，不会再用占位源码 + 极简测试 JSON 过关
- 同类证据文件不再互相覆盖
- 失败时能直接看到原始测试输出和真实失败票

### 第二批验收

- 第三方只看场景根目录和几份 `.md` 就能判断这轮测试卡在哪
- 不需要先翻数据库才能看懂主线

### 第三批验收

- 长测出现偏航时会尽早熔断
- 不再出现“跑了很久、票很多、结果没系统”的假繁荣

---

## 文档关系

这 3 份文档现在分工如下：

- `audit-readability-proposal.md`
  - 记录“人工审计为什么难读”
- `library-management-autopilot-live-audit-20260413.md`
  - 记录“为什么这次长测应判失败”
- `provider-runtime-strict-remediation-plan-20260413.md`
  - 记录“本轮已落的 P0 provider 严格执行整改”
- `integration-audit-remediation-master-plan-20260413.md`
  - 记录“覆盖全部审计问题的总实施计划”
