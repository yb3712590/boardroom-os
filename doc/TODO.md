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

- backend：当前 shell 的裸 `pytest` 仍不在 PATH；本轮先确认 `pytest tests/ -q` 直接报 `CommandNotFoundException`，再通过 `py -m pytest tests/ -q` 完成全量复核，`414 passed`
- frontend：`npm run build` → passed，`npm run test:run` → `64 passed`

## 现在先做什么

| 批次 / 任务 | 状态 | 现实目标 | 详细看哪里 |
|-------------|------|----------|------------|
| `P2-B` | 进行中 | 已完成边界、依赖、测试归属和阻塞证据固化；下一步仍只在前置条件满足后评估物理迁移 | [task-backlog/active.md](task-backlog/active.md) |
| `P2-C` | 未开始 | 只在证明当前主链不够用后，再补检索、Provider 路由和发布准备 | [task-backlog/active.md](task-backlog/active.md) |
| `P2-D` | 进行中 | 首页 UI 收口已完成；下一步只补剩余文档，不反过来破坏现有主链 | [task-backlog/active.md](task-backlog/active.md) |

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

- [x] `P2-UI-001`：保留现有 `Workflow River` 粒子方向，并补上 `prefers-reduced-motion` 降级
- [x] `P2-UI-002`：统一首页河道与顶栏 `Board Gate` 的呼吸语义和节奏
- [x] `P2-UI-003`：首页左中右区域改成真实骨架屏，不再只显示一条全局 loading 文案
- [x] `P2-UI-004`：窄屏下 `Workflow River` 改为保留横向河道表达，不再碎成纵向五张卡
- [x] `P2-UI-005`：当前前端全部可达路由补齐键盘可访问性，抽屉现在会处理初始焦点、焦点循环、`Escape` 关闭、关闭后回到触发点
- [x] `P2-UI-006`：现有 dark-glass 基线已补齐更稳定的 surface / divider / focus / disabled token，对比度和状态语义收口到同一套样式变量
- [x] `P2-UI-007`：`Review / Meeting / Incident / Dependency Inspector / Provider Settings` 抽屉已改为按需懒加载，`boardroom-event` 刷新现在走 `500ms` debounce
- [x] `P2-UI-008`：补齐首页 loading / board gate 语义相关的最小前端测试
- [x] `P2-DOC-002`：`TODO` 已同步成“补齐现有半落地实现并验证”的真实状态
- [x] `P2-DOC-004`：`memory-log` 已追加这轮会影响后续判断的事实
- [ ] README、运维指南、API 文档按真实状态继续收口

本轮完成补记：

- 首页 loading 现在按面板分区显示：`InboxWell`、`Workflow River`、`WorkforcePanel`、`EventTicker` 都有真实骨架屏
- `Workflow River` 保留现有粒子与 Board Gate 提醒语义，但补了 reduced-motion 兼容，不把“正在加载”或“窄屏”写成第二套页面
- 当前前端路由已补上 skip link、main landmark、抽屉焦点管理和稳定的 `:focus-visible`，不再把键盘用户丢在 overlay 外面
- 当前首页和抽屉仍保持既有 dark-glass 语言，只补了 token 和对比度，不新增 light theme，也没有重做首页主舞台
- 当前前端性能收口只做了最小必要两件事：overlay 按需懒加载，SSE 失效通知按 `500ms` 合并刷新；没有新增缓存层，也没有改后端接口
- 当前未新增主线任务；`P2-D` 下一步只剩 `P2-DOC-001` / `003` / `005`

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
