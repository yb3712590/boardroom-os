# Active Task Backlog

> 最后更新：2026-04-11
> 说明：这里只保留当前仍未关闭、仍会影响当前主线实现的任务。已完成的详细任务卡片和完成补记统一看 `done.md`。

## 当前主线：`P0-COR`

| ID | 标题 | 状态 | 说明 |
|----|------|------|------|
| `P0-COR-001` | canonical 协议收口 | 进行中 | 已落第一段：`project-init` 会创建三分区项目工作区，`ticket-create` 会自动补 project workspace / deliverable / 文档 / git 相关真相，并生成 ticket dossier |
| `P0-COR-002` | 单一 workflow controller | 待开始 | 合并 `workflow_auto_advance / scheduler_runner / ceo_scheduler / deterministic fallback` 的推进语义 |
| `P0-COR-003` | architect / meeting 硬约束 | 待开始 | 把 architect 真实参与和必要 meeting 证据升成主线门禁 |
| `P0-COR-004` | 源码交付 contract 与 write set 重构 | 进行中 | 已落第四段：`10-project/` 已变成真实 git repo，workspace-managed `source_code_delivery` 票会分配真实 worktree、真实写盘、真实 commit，并继续维护 active worktree 索引；但非代码 deliverable contract 还没收完 |
| `P0-COR-005` | checker / closeout 硬门禁 | 进行中 | 已落第四段：workspace-managed `source_code_delivery` 票会在 final review approve 前真实 merge，closeout / completion 只继续消费 `MERGED` 的源码交付；merge 冲突会 fail-closed 打开 incident；但非代码票 gate 还没完成 |
| `P0-COR-006` | live 场景回归与退出标准重建 | 待开始 | 用真实代码交付口径重跑 live 场景，重建通过标准 |

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
