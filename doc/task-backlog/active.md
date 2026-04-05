# Active Task Backlog

> 说明：这里只保留当前仍未关闭、仍可能被反复读取的任务。已完成的详细任务卡片和完成补记统一看 `done.md`。

## 快速定位

| 方向 | 任务范围 | 默认状态 | 备注 |
|------|----------|----------|------|
| 冻结能力隔离 | `P1-CLN-001` 到 `P1-CLN-006` | 进行中 | `P1-CLN-005`、`P1-CLN-006` 已完成；`P1-CLN-001` 到 `P1-CLN-004` 已进入进行中，但物理迁移都还没启动 |
| 检索层 | `P2-RET-001` 到 `P2-RET-005` | 未开始 | 仍属后置增强 |
| Provider 增强 | `P2-PRV-001` 到 `P2-PRV-008` | 未开始 | 仍属后置增强 |
| 治理模板与文档型角色 | `P2-GOV-001` 到 `P2-GOV-006` | 未开始 | 仍属后置增强 |

## P1：重要

### 3.3 代码清理

> 当前状态补记：`P1-CLN-005` 和 `P1-CLN-006` 已完成。`P1-CLN-001` 已完成前置拆分：`worker-admin` 共用的 scope / bootstrap / session / grant helper 已移到 `worker_scope_ops.py`，`worker-admin` projection 入口已拆到独立文件，但仍没有启动 `_frozen/` 物理迁移。`P1-CLN-002` 已推进到主线 command 侧解耦：`project-init`、`ticket-create`、CEO 建票和审批 follow-up 建票不再直接吃 `tenant_id/workspace_id`，而是统一从 workflow/default 解析 scope；命令 API 仍保留弃用兼容输入。`P1-CLN-004` 这轮也已推进到前置拆分阶段：`worker-runtime` projection 入口已拆到独立文件，管理读面改成复用 `worker_scope_ops.py` helper。
>
> 当前挂起原因：
> `P1-CLN-001` 还不能直接收口成物理迁移，因为 worker-admin 的 API、auth、projection、CLI 仍需成组移动。`P1-CLN-002` 到 `P1-CLN-004` 当前都还不能直接启动物理迁移：
> `P1-CLN-002`：主线 command 侧已解耦，但 runtime、`worker-admin / worker-runtime` contracts 和共享读面仍保留 `tenant_id/workspace_id` shape。
> `P1-CLN-003`：`ticket-result-submit` 已不再桥接 upload session；当前仍保留独立的 `ticket-artifact-import-upload` 导入入口和 upload session 存储，所以还不能直接做 `_frozen/` 物理迁移。
> `P1-CLN-004`：独立 projection 入口和 helper 收口已完成，但 `worker-runtime` 路由、CLI 和 bootstrap/session/delivery-grant schema 仍需成组保留。

> 本轮补记：
> `P1-CLN-003` 现在新增了控制面和 `worker-runtime` 两条 `ticket-artifact-import-upload` 写回链；上传会话完成后先导入为正常 artifact，再让 `ticket-result-submit` 只引用 `artifact_ref`。
> `backend/tests/test_api.py` 已补回归，覆盖控制面导入、路径越界拒绝、worker-runtime 签名导入后再提交；`backend/tests/test_mainline_truth.py` 也已改成新阻塞口径。
> `P1-CLN-004` 这轮已从“未开始（阻塞评估已固化）”推进到“进行中”：`/api/v1/projections/worker-runtime` 已拆到独立 `worker_runtime_projections.py`，`build_worker_runtime_projection(...)` 已改成复用 `worker_scope_ops.py` 的 `list_binding_admin_views / list_sessions / list_delivery_grants / list_auth_rejections`。
> `backend/app/core/mainline_truth.py` 与 `backend/tests/test_mainline_truth.py` 这轮同步成新阻塞口径：独立 projection 入口前置拆分已经完成，但 `/api/v1/worker-runtime`、`worker_auth_cli.py` 和三张 handoff schema 仍是成组阻塞点。

| ID | 标题 | 预估 | 状态 |
|----|------|------|------|
| P1-CLN-001 | 移动 worker-admin 代码到 _frozen/ | 3h | 进行中 |
| P1-CLN-002 | 移动多租户代码到 _frozen/ | 2h | 进行中 |
| P1-CLN-003 | 移动对象存储代码到 _frozen/ | 2h | 进行中 |
| P1-CLN-004 | 移动远程 handoff 代码到 _frozen/ | 2h | 进行中 |

## P2：增强

### 4.1 检索层

| ID | 标题 | 预估 | 状态 |
|----|------|------|------|
| P2-RET-001 | 创建 FTS5 虚拟表 | 4h | 未开始 |
| P2-RET-002 | 索引工单结果和审查摘要 | 4h | 未开始 |
| P2-RET-003 | Context Compiler 集成 FTS5 查询 | 4h | 未开始 |
| P2-RET-004 | 检索结果排序和去重 | 4h | 未开始 |
| P2-RET-005 | 检索层测试 | 4h | 未开始 |

### 4.2 Provider 增强

| ID | 标题 | 预估 | 状态 |
|----|------|------|------|
| P2-PRV-001 | 多 Provider 配置支持 | 4h | 未开始 |
| P2-PRV-002 | 能力标签定义 | 3h | 未开始 |
| P2-PRV-003 | 基础健康检查 | 3h | 未开始 |
| P2-PRV-004 | 简单 fallback 路由 | 4h | 未开始 |
| P2-PRV-005 | Provider 增强测试 | 6h | 未开始 |
| P2-PRV-006 | 角色级默认模型绑定 | 4h | 未开始 |
| P2-PRV-007 | 任务级模型覆盖与 preferred/actual model 追踪 | 4h | 未开始 |
| P2-PRV-008 | 成本分层与高价模型低频路由 | 4h | 未开始 |

### 4.3 治理模板与文档型角色

| ID | 标题 | 预估 | 状态 |
|----|------|------|------|
| P2-GOV-001 | 定义治理模板数据结构 | 4h | 未开始 |
| P2-GOV-002 | 定义 CTO / 架构师低频角色模板 | 4h | 未开始 |
| P2-GOV-003 | 定义架构 / 选型 / 里程碑 / 详细设计 / TODO 文档产物契约 | 4h | 未开始 |
| P2-GOV-004 | CEO 按治理模板触发文档型任务 | 4h | 未开始 |
| P2-GOV-005 | 文档型角色默认不参与日常编码 / 测试执行约束 | 3h | 未开始 |
| P2-GOV-006 | 治理模板与文档型角色测试和文档 | 5h | 未开始 |

## 依赖提醒

- `P1-CLN-*` 如果真正启动，应先做依赖图和调用清单，不要直接搬目录
- `P2-RET-*`、`P2-PRV-*`、`P2-GOV-*` 目前都属于后置增强；只有在本地 MVP 主链已经证明需要时，才值得打开
