# Active Task Backlog

> 最后更新：2026-04-12
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
