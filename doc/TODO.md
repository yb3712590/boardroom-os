# TODO

> 最后更新：2026-04-06
> 本文件仍是项目唯一的待办真相源，但正文只保留当前要推进的批次。已完成能力改看 `todo/completed-capabilities.md`，冻结与后置范围改看 `todo/postponed.md`。

## 当前阶段目标

把项目继续收敛成一个本地单机可运行、可验证、可演示的 Agent Delivery OS MVP：

- 事件溯源状态总线是真相源
- Ticket 驱动无状态执行器推进工作
- Maker-Checker 和 Review 闭环真实可用
- React 只做最薄治理壳，不接管工作流真相

## 当前基线（2026-04-06 实测）

- backend：当前 shell 的裸 `pytest` 仍不在 PATH；本轮先确认 `pytest tests/ -q` 直接报 `CommandNotFoundException`，再通过重定向方式执行 `py -m pytest tests/ -q` 完成全量复核，`422 passed`
- frontend：`npm run build` → passed，`npm run test:run` → `64 passed`

## 现在先做什么

| 批次 / 任务 | 状态 | 现实目标 | 详细看哪里 |
|-------------|------|----------|------------|
| `P2-B` | 进行中 | 已完成边界、依赖、测试归属和阻塞证据固化；下一步仍只在前置条件满足后评估物理迁移 | [task-backlog/active.md](task-backlog/active.md) |
| `P2-C` | 未开始 | 只在证明当前主链不够用后，再补检索、Provider 路由和发布准备 | [task-backlog/active.md](task-backlog/active.md) |

## 当前活跃批次

### `P1-MTG-008`：CEO 触发会议决策（已完成）

主线关系：**主链增强**，建立在现有会议室最小闭环已稳定的前提上。

- [x] 让 CEO 在明确需要跨角色对齐时，能创建 `TECHNICAL_DECISION` 会议请求
- [x] 仍保持会议是受控例外，不变成常驻聊天系统
- [x] 触发条件、输入工件和回主线方式都要可审计

本轮完成补记：

- 新增了 `REQUEST_MEETING` 这条 CEO 有限执行动作，并继续沿用现有 `ceo_shadow_run` 审计，不另起第二套状态存储
- CEO snapshot 现在会暴露 `meeting_candidates`，候选来自当前员工投影派生的最小能力/角色匹配，而不是新建持久化 Capability Registry
- 自动会议只在窄触发下开启：决策/评审型票失败且串行重试已不划算，或董事会 `REJECT / MODIFY_CONSTRAINTS` 后需要重对齐；不会在 idle maintenance 里泛化开会，也不会对 `MEETING_ESCALATION` 递归开会

对应任务库：`P1-MTG-008`

### `P2-B`：代码瘦身与冻结能力隔离

主线关系：**后置收口**；当前阶段仍以边界清楚、入口清楚、依赖清楚为主，但 `worker-admin` 已完成带兼容壳的 shim 物理迁移，其余冻结切片暂不直接做无壳迁移。

- [x] `P1-CLN-005`：已把冻结能力的真实入口、主线依赖、测试归属和迁移前置条件写进 `backend/app/core/mainline_truth.py`，并用 `backend/tests/test_mainline_truth.py` 固化
- [x] `P1-CLN-006`：已把 frozen 相关测试边界收口成可执行断言，明确哪些测试属于冻结入口回归，哪些不是主链闭环测试
- [x] `P1-CLN-001`：已完成；`worker-admin` 真实实现已迁入 `backend/app/_frozen/worker_admin/`，现有 API / auth / projection / CLI / core 入口只保留兼容壳，不改 HTTP 路径、鉴权规则和 CLI 调用方式
- [ ] `P1-CLN-002`：已进入进行中；主线 `project-init / ticket-create / CEO 建票 / 审批 follow-up 建票` 已改成统一从 workflow/default 解析 scope，API 入口仍保留弃用兼容；runtime、projection 和冻结 contracts 的多租户 shape 仍未拆
- [ ] `P1-CLN-003`：已进入进行中；`ticket-result-submit` 已不再直接消费 upload session，当前改成“upload session -> ticket-artifact-import-upload -> artifact_ref -> ticket-result-submit”，但 upload 导入入口和 upload session 存储仍在，所以 `_frozen/` 物理迁移前置条件还没全满足
- [ ] `P1-CLN-004`：已进入进行中；`/api/v1/projections/worker-runtime` 已从通用 `projections.py` 拆到独立入口，`worker-runtime` 管理读面已收口到 `worker_scope_ops.py` helper，但 `/api/v1/worker-runtime`、`worker_auth_cli.py` 和 `worker_bootstrap/session/delivery-grant` schema 仍需成组保留
- [ ] 如果后续启动物理迁移，仍以“不影响主线测试”为绝对前提

本轮完成补记：

- `P1-CLN-001` 这轮已真实进入 shim 迁移：`backend/app/_frozen/worker_admin/` 现在承接 `worker-admin` 的 API、auth、projection、core 和 CLI 实现，旧入口只做薄转发
- `backend/tests/test_mainline_truth.py` 这轮新增回归，直接断言 `worker-admin` 的 `code_refs` 已切到 `_frozen/worker_admin`，同时保留旧入口作为兼容壳
- `backend/tests/conftest.py` 这轮同步改成直接 monkeypatch `_frozen.worker_admin.core.worker_admin`，避免测试仍盯着旧 shim 模块
- `P1-CLN-002` 这轮已从“未开始”推进到“进行中”：`ProjectInitCommand`、`TicketCreateCommand` 已不再暴露 `tenant_id/workspace_id`，主线 handler 改成统一从 workflow/default 解析 scope
- `/api/v1/commands/project-init` 与 `/api/v1/commands/ticket-create` 当前仍保留弃用兼容输入，旧字段还能传，但不会再影响主线行为
- 审批 follow-up、closeout 和会议室建票这轮也已补齐 workflow scope 注入，避免绕过 `handle_ticket_create(...)` 时把 scope 丢回默认值
- `P1-CLN-003` 这轮已从“未开始”推进到“进行中”：`ticket-result-submit` 不再直接消费 `upload_session_id`，当前改成先走 `ticket-artifact-import-upload` 导入，再由结果提交只引用 `artifact_ref`
- 控制面与 `worker-runtime` 现在都补了同构的 `ticket-artifact-import-upload` 命令，执行包也会下发新的签名命令 URL，外部 handoff 没有被顺手削弱
- `artifact_uploads` 和 upload session 存储仍保留，所以 `_frozen/` 物理迁移前置条件还没完全满足；这轮目标只是拆掉主线桥接点
- `P1-CLN-004` 这轮已从“未开始”推进到“进行中”：`/api/v1/projections/worker-runtime` 已拆到独立 `worker_runtime_projections.py`，`build_worker_runtime_projection(...)` 也已改成复用 `worker_scope_ops.py` 的 binding/session/grant/rejection helper
- `backend/app/core/mainline_truth.py` 与 `backend/tests/test_mainline_truth.py` 这轮同步成新口径：handoff 的独立 projection 入口前置拆分已经完成，但 runtime 路由、CLI 和三张 handoff schema 仍需成组保留，所以还不能启动 `_frozen/` 物理迁移
- `P1-CLN-001` 到 `P1-CLN-004` 这轮继续补的是“成组迁移清单”而不是物理迁移：`FrozenCapabilityBoundary` 新增 `api_surface_groups` 和 `storage_table_refs`，把冻结边界对应的 route family 和共享表锚点也固化进代码真相源，并由 `backend/tests/test_mainline_truth.py` 直接回归
- `P1-CLN-001`、`P1-CLN-003`、`P1-CLN-004` 这轮继续完成了“路由挂载边界收口”这层前置拆分：新增 `backend/app/api/router_registry.py`，把 `artifact-uploads`、`worker-admin`、`worker-runtime` 及其 projection 统一注册成 frozen 路由组，`main.py` 不再手工散挂这些入口
- `backend/app/core/api_surface.py`、`backend/tests/test_api_surface.py`、`backend/tests/test_mainline_truth.py` 这轮已统一复用同一套路由组顺序，并直接回归 frozen 组仍被注册、仍按现有顺序挂载；这轮没有改任何 HTTP 路径和鉴权行为

对应任务库：已完成 `P1-CLN-001`、`P1-CLN-005`、`P1-CLN-006`；`P1-CLN-002`、`P1-CLN-003`、`P1-CLN-004` 进行中，且还没满足无壳物理迁移前置条件

### `P2-C`：检索、Provider 路由、发布准备

主线关系：**后置增强**，只有在真实 Worker 与 CEO 稳定后才值得继续投入。

- [ ] 检索只在已经证明本地历史摘要不够后再做
- [ ] Provider registry / routing / fallback 策略放在真实 Worker 和 CEO 稳定之后
- [ ] 发布准备以“本地单机演示可复现”为目标，不提前做公网化

对应任务库：`P2-RET-*`、`P2-PRV-*`、`P0-REL-*`

已完成补记：

- `P2-D` 本轮已收口，`README.md`、`doc/backend-runtime-guide.md`、`doc/api-reference.md` 都已按当前代码现实同步
- 当前新增了最小路由分组回归：`backend/app/core/api_surface.py` + `backend/tests/test_api_surface.py`，后续如果接口分组变化但 API 文档没跟上，会先在后端测试里暴露

## 执行约束

- 新工作如果不能直接缩短本地 MVP 路径，就默认延后
- 文档、任务拆分和代码审查都应以“本地无状态 agent team + Web 壳”为判断基准
- 对已有基础设施代码优先采取“冻结、收口、少动”的策略
- 默认先读 `mainline-truth.md`、`roadmap-reset.md`、`history/context-baseline.md`，再决定要不要打开长文

## 建议默认执行顺序

1. `P2-B`：先把冻结能力的边界说明清楚，避免后续误读
2. `P2-C`：只在已证明主链需要时，再补检索 / Provider / 发布准备

## 已完成与后置入口

- 已完成能力与已收口批次：[todo/completed-capabilities.md](todo/completed-capabilities.md)
- 冻结能力和明确后置范围：[todo/postponed.md](todo/postponed.md)

## 参考

- 任务库入口：[task-backlog.md](task-backlog.md)
- 当前活跃任务明细：[task-backlog/active.md](task-backlog/active.md)
- 长期里程碑时间线：[milestone-timeline.md](milestone-timeline.md)
- CTO 评审报告：[cto-assessment-report.md](cto-assessment-report.md)
