# Active Task Backlog

> 最后更新：2026-04-20
> 说明：这里只保留当前仍未关闭、仍会影响当前主线实现的任务。已完成的详细任务卡片和完成补记统一看 `done.md`。

## 当前主线：`P0-COR`

| ID | 标题 | 状态 | 说明 |
|----|------|------|------|
| `P0-COR-001` | canonical 协议收口 | 进行中 | 已落第一段：`project-init` 会创建三分区项目工作区，`ticket-create` 会自动补 project workspace / deliverable / 文档 / git 相关真相，并生成 ticket dossier |
| `P0-COR-002` | 单一 workflow controller | 进行中 | 已落第四段：`STANDARD` 也已切到 governance-first，`project-init` kickoff、requirement elicitation 后续 kickoff、controller、fallback、validator 和 auto-advance 都开始共用同一条治理链真相；legacy scope follow-up 只留给非 autopilot 的手工 `consensus_document` 兼容链 |
| `P0-COR-003` | architect / meeting 硬约束 | 进行中 | 已落第四段：`STANDARD` 在 backlog recommendation 之前也会被治理链阻断，`required_governance_ticket_plan` 会直接暴露下一张治理文档票；backlog recommendation 之后，`STANDARD` 与 `CEO_AUTOPILOT_FINE_GRAINED` 一样会进入 `architect_primary / 技术决策会议 / staffing gap` 硬约束 |
| `P0-COR-004` | 源码交付 contract 与 write set 重构 | 进行中 | 已落第七段：`delivery_closeout_package` 也已并回 `structured_document_delivery` 主线，closeout 票默认写到 `20-evidence/closeout/<ticket>/`，并继续复用 declared artifact / written artifact 对齐 contract；这轮又补了 Windows Git 子进程兼容，本机 workspace-managed 回归已恢复；但更广义的非代码 deliverable kind 还没正式进入主线 |
| `P0-COR-005` | checker / closeout 硬门禁 | 进行中 | 已落第七段：closeout 票现在会继承 canonical docs、doc update 要求和上游 delivery evidence，`payload.final_artifact_refs` 也已进入硬校验；`FOLLOW_UP_REQUIRED` 继续只作为 checker 可见风险；本机 closeout/workspace hook 回归已恢复，但 full live 退出标准还没重跑确认 |
| `P0-COR-006` | live 场景回归与退出标准重建 | 进行中 | 已把 live runner 抽成共享 harness，并补出 `requirement_elicitation / architecture_governance / library_management` 三条 full 入口；这轮新增 `architecture_governance_autopilot_smoke` checkpoint smoke，但当前机器实跑仍被 provider timeout 卡住，其他 full 长测也尚未重跑 |

### 2026-04-20 runtime ticket / legacy compat 硬切收尾

- `consensus_document` 已不再接受 legacy `followup_tickets`，`board-approve` 的 scope review 主链也已不再依赖这个 contract。
- `backend/tests/test_api.py` 里直接读 consensus artifact `followup_tickets` 的 legacy helper 已拆掉，`backend/tests/test_scheduler_runner.py` 里的同类 helper 也已删除。
- 这轮主链收口已经完成：`test_api.py` 的 `scope review -> final review -> closeout` 历史 helper、`test_scheduler_runner.py` 的 provider-backed / timeout / repeated-failure recovery 历史桶、以及 `ceo_execution_presets.py` / `test_ceo_scheduler.py` 的旧 consensus follow-up 残留都已收正并实跑通过。
- minimal recovery seed 的 graph health / workflow completion truth 也已在本轮收口：timeout / repeated-failure 两条历史桶现在会稳定走到 closeout 票完成、workflow `COMPLETED`、dashboard `completion_summary` 非空，且不会再误挂 `GRAPH_HEALTH_CRITICAL`。
- 这一段不再单列 active blocker；当前 active 风险重新回到 `P0-COR-004 / P0-COR-005 / P0-COR-006` 的 live/provider 退出标准，而不是 hard cut 主链或 recovery workflow truth。

### 2026-04-13 审计第一批执行切片

- `P0-2` 已落本轮最小闭环：`source_code_delivery@1` 现在必须带 `source_files[] / verification_runs[]`，不能再只靠 `source_file_refs[]` 过 schema。
- `P0-3` 已落路径隔离：workspace-managed 测试证据统一写到 `20-evidence/tests/<ticket_id>/attempt-1/`，git 证据统一写到 `20-evidence/git/<ticket_id>/attempt-1/`。
- `P1-3` 已落证据质量门禁：空 stdout/stderr、`pytest -q passed`、固定 `source.ts/source.tsx` 占位名和 `runtimeSourceDelivery = true` 现在都会被拦成失败。

### 2026-04-13 审计第二批执行切片

- `P1-1` 已落正式摘要：`audit-summary.md` 现在会固定输出场景时间范围、provider 摘要、workflow 阶段流转、ticket 汇总、governance 产出链、代码/证据概览和最长静默区间。
- `P1-2` 已落巡检去重：live harness 现在会自动生成 `integration-monitor-report.md`，只在状态变化和静默恢复时写记录，不再刷满“无变化”心跳。
- `P2-1` 已落治理文档人工可读层：五类 governance JSON 现在会自动旁挂同名 `.audit.md`，并一起进入 artifact index，但 process asset 仍继续指向原始 JSON。
- `P2-2` 已落 ticket 执行卡片：`ticket_context_archives/*.md` 现在会按 compile / terminal 两阶段刷新，直接展示上下文来源表、token 预算、降级告警、checkout / branch 和实际 artifact 路径。
- 当前 blocker 仍在 `P0-COR-006`：真实 provider 长测还没重跑，`test_api.py / test_scheduler_runner.py` 那批受 provider fail-closed 影响的历史测试也还没一并收口。

## 冻结后置

| ID | 标题 | 状态 | 说明 |
|----|------|------|------|
| `P1-CLN-002` | 移动多租户代码到 `_frozen/` | 冻结后置 | 主线 command 已解耦，但 runtime、`worker-admin / worker-runtime` contracts 和共享读面仍保留 `tenant_id/workspace_id` shape |
| `P1-CLN-003` | 移动对象存储代码到 `_frozen/` | 冻结后置 | 结果提交流程已解耦，但 upload 导入入口和 upload session 存储仍保留 |

## 条件批次

- 当前没有新增开启的 `C1` 条件批次。
- 条件纳入任务进入执行前，必须先把触发原因写回 `TODO.md`。

## 依赖提醒

- `P0-COR` 优先级高于 `M6`、`C1` 和所有新角色扩张。
- `P1-CLN-*` 只有在 blocker 真正松动后才重新打开物理迁移。
- 已完成的 `P2-DEC-* / P2-GOV-* / P2-RLS-* / P2-PRV-* / P2-UI-*` 只保留在 `done.md`，不再占用 active 视图。
