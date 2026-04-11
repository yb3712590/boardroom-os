# Active Task Backlog

> 最后更新：2026-04-11
> 说明：这里只保留当前仍未关闭、仍会影响当前主线实现的任务。已完成的详细任务卡片和完成补记统一看 `done.md`。

## 当前主线：`P0-COR`

| ID | 标题 | 状态 | 说明 |
|----|------|------|------|
| `P0-COR-001` | canonical 协议收口 | 进行中 | 已落第一段：`project-init` 会创建三分区项目工作区，`ticket-create` 会自动补 project workspace / deliverable / 文档 / git 相关真相，并生成 ticket dossier |
| `P0-COR-002` | 单一 workflow controller | 进行中 | 已落第二段：新增 `required_governance_ticket_plan`，architect gate 场景下 `ceo_scheduler / deterministic fallback / validator / workflow_auto_advance` 已能共用同一条治理补票真相；当前仍先覆盖 `CEO_AUTOPILOT_FINE_GRAINED + backlog_recommendation` |
| `P0-COR-003` | architect / meeting 硬约束 | 进行中 | 已落第二段：autopilot backlog fanout 遇到 `architect_primary` / 技术决策会议硬约束时，会先走 `HIRE_EMPLOYEE / REQUEST_MEETING / 治理补票`，不再静默 fallback；当前默认只自动补 `architect_primary + architecture_brief`，更广覆盖面还没做 |
| `P0-COR-004` | 源码交付 contract 与 write set 重构 | 进行中 | 已落第六段：workspace-managed `source_code_delivery` 票已是真实 git repo / worktree / 写盘 / commit 主线；`structured_document_delivery` 也已统一补上 declared artifact / written artifact 对齐 contract，覆盖 `consensus_document` 与五类治理文档；但更广义的非代码 deliverable kind 还没正式进入主线 |
| `P0-COR-005` | checker / closeout 硬门禁 | 进行中 | 已落第六段：workspace-managed `source_code_delivery` 票会在 final review approve 前真实 merge；五类治理文档继续只复用过 internal governance gate 的逻辑文档，`consensus_document` 也已补到 `MEETING_ESCALATION` 批准后才进入 CEO reuse；architect / meeting gate 已先在 autopilot backlog fanout 落第一段，但 closeout 扩展和 live 退出标准还没完成 |
| `P0-COR-006` | live 场景回归与退出标准重建 | 进行中 | 已补 deterministic architect gate 回归和 live 脚本断言；真实 live provider 长测这轮尚未重跑 |

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
