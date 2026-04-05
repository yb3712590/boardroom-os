# TODO

> 最后更新：2026-04-05
> 本文件仍是项目唯一的待办真相源，但正文只保留当前要推进的批次。已完成能力改看 `todo/completed-capabilities.md`，冻结与后置范围改看 `todo/postponed.md`。

## 当前阶段目标

把项目继续收敛成一个本地单机可运行、可验证、可演示的 Agent Delivery OS MVP：

- 事件溯源状态总线是真相源
- Ticket 驱动无状态执行器推进工作
- Maker-Checker 和 Review 闭环真实可用
- React 只做最薄治理壳，不接管工作流真相

## 当前基线（2026-04-05 实测）

- backend：当前 shell 的裸 `pytest` 仍不在 PATH；已通过 `py -m pytest tests -q` 完成全量复核，`414 passed`
- frontend：`npm run build` → passed，`npm run test:run` → `53 passed`

## 现在先做什么

| 批次 / 任务 | 状态 | 现实目标 | 详细看哪里 |
|-------------|------|----------|------------|
| `P2-B` | 进行中 | 已完成边界、依赖、测试归属和阻塞证据固化；下一步仍只在前置条件满足后评估物理迁移 | [task-backlog/active.md](task-backlog/active.md) |
| `P2-C` | 未开始 | 只在证明当前主链不够用后，再补检索、Provider 路由和发布准备 | [task-backlog/active.md](task-backlog/active.md) |
| `P2-D` | 未开始 | 做 UI 打磨和文档收口，但不反过来破坏现有主链 | [task-backlog/active.md](task-backlog/active.md) |

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

主线关系：**后置收口**；当前阶段只做边界清楚、入口清楚、依赖清楚，不直接做 `_frozen/` 物理迁移。

- [x] `P1-CLN-005`：已把冻结能力的真实入口、主线依赖、测试归属和迁移前置条件写进 `backend/app/core/mainline_truth.py`，并用 `backend/tests/test_mainline_truth.py` 固化
- [x] `P1-CLN-006`：已把 frozen 相关测试边界收口成可执行断言，明确哪些测试属于冻结入口回归，哪些不是主链闭环测试
- [ ] `P1-CLN-001`：已完成前置拆分，当前转为进行中；`worker-admin` 共用的 scope / bootstrap / session / grant helper 已抽到 `worker_scope_ops.py`，`worker-admin` 专属 projection 入口已从通用 `projections.py` 分离，但 `_frozen/` 物理迁移仍未启动
- [ ] `P1-CLN-002`：仍未开始，但阻塞评估已收口；`mainline_truth.py` 和 `test_mainline_truth.py` 现已把共享 contracts、`approval_handlers.py`、`ceo_execution_presets.py`、`ticket_handlers.py` 对 `tenant_id/workspace_id` 的直接依赖固化成结构化证据
- [ ] `P1-CLN-003`：仍未开始，但阻塞评估已收口；`TicketResultSubmitCommand.upload_session_id`、`require_completed_artifact_upload_session(...)` 和上传会话消费路径仍是当前主链桥接点，暂不满足迁移前置条件
- [ ] `P1-CLN-004`：仍未开始，但阻塞评估已收口；`/api/v1/worker-runtime`、`/api/v1/projections/worker-runtime`、`worker_auth_cli.py` 和 `worker_bootstrap/session/delivery-grant` schema 仍需成组保留
- [ ] 如果后续启动物理迁移，仍以“不影响主线测试”为绝对前提

对应任务库：已完成 `P1-CLN-005`、`P1-CLN-006`；`P1-CLN-001` 进行中；`P1-CLN-002` 到 `P1-CLN-004` 已完成阻塞评估收口，但仍未满足物理迁移前置条件

### `P2-C`：检索、Provider 路由、发布准备

主线关系：**后置增强**，只有在真实 Worker 与 CEO 稳定后才值得继续投入。

- [ ] 检索只在已经证明本地历史摘要不够后再做
- [ ] Provider registry / routing / fallback 策略放在真实 Worker 和 CEO 稳定之后
- [ ] 发布准备以“本地单机演示可复现”为目标，不提前做公网化

对应任务库：`P2-RET-*`、`P2-PRV-*`、`P0-REL-*`

### `P2-D`：UI 打磨与文档

主线关系：**后置打磨**，不阻塞当前本地单机 MVP 闭环。

- [ ] Workflow River 粒子动画、Board Gate 呼吸动画、加载骨架屏、响应式布局
- [ ] 键盘可访问性、暗色主题微调、性能优化
- [ ] README、运维指南、API 文档按真实状态继续收口

对应任务库：`P2-UI-*`、`P2-DOC-*`

## 执行约束

- 新工作如果不能直接缩短本地 MVP 路径，就默认延后
- 文档、任务拆分和代码审查都应以“本地无状态 agent team + Web 壳”为判断基准
- 对已有基础设施代码优先采取“冻结、收口、少动”的策略
- 默认先读 `mainline-truth.md`、`roadmap-reset.md`、`history/context-baseline.md`，再决定要不要打开长文

## 建议默认执行顺序

1. `P2-B`：先把冻结能力的边界说明清楚，避免后续误读
2. `P2-C`：只在已证明主链需要时，再补检索 / Provider / 发布准备
3. `P2-D`：在现有闭环稳定后做 UI 打磨和文档收口

## 已完成与后置入口

- 已完成能力与已收口批次：[todo/completed-capabilities.md](todo/completed-capabilities.md)
- 冻结能力和明确后置范围：[todo/postponed.md](todo/postponed.md)

## 参考

- 任务库入口：[task-backlog.md](task-backlog.md)
- 当前活跃任务明细：[task-backlog/active.md](task-backlog/active.md)
- 长期里程碑时间线：[milestone-timeline.md](milestone-timeline.md)
- CTO 评审报告：[cto-assessment-report.md](cto-assessment-report.md)
