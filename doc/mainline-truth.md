# 主线真相表

> 最后更新：2026-04-06
> 这份文档只回答一个问题：**当前代码里到底什么是真的**。如果 `README`、设计文档和这里冲突，先以代码现实和这份表为准。

## 1. 主链阶段对照表

| 阶段 | 当前状态 | 代码现实 | 直接结论 |
|------|----------|----------|----------|
| `project-init -> scope review` | 真实运行 | `project-init` 会先由 CEO 发起首个 kickoff scope 共识票，再自动推进到首个 scope review | 不是只建 workflow 的空壳 |
| `BUILD` 内部 maker-checker | 真实运行 | 先产出 `implementation_bundle@1`，再走 `maker -> checker -> fix / incident` | `BUILD` 不会直接放行到 `CHECK` |
| `CHECK` 内部 maker-checker | 真实运行 | `delivery_check_report@1` 也有独立内审闭环 | `CHECK` 不会直接放行到最终董事会 |
| 最终 `REVIEW` | 真实运行 | 只有真正 board-facing 的 review 才进入 `Inbox -> Review Room` | 董事会只看真实审批点 |
| `closeout` 内部 maker-checker | 真实运行 | final review 通过后会自动补 `delivery_closeout_package@1`，closeout 完成后才算 workflow 完成 | completion 不是 board approve 就立刻出现 |

补充差异：

- `project-init -> scope review` 这条共识链仍保留 `ui_designer_primary`，但首个 scope kickoff 票已经不再由命令处理器硬编码创建，而是由 `BOARD_DIRECTIVE_RECEIVED` 的 CEO shadow run 发起
- 但 `BUILD / REVIEW / closeout` 这条 maker 主线已经切到独立的 `frontend_engineer_primary`
- 为了不打断还没迁走的 scope 共识链，调度层会把 `frontend_engineer_primary` 兼容匹配到旧的 `ui_designer_primary` 票型；这只是收口期兼容，不代表又回到了“没有独立 worker”
- 当前 CEO 也能在窄触发条件下自动创建 `TECHNICAL_DECISION` 会议请求：只覆盖决策/评审型票的失败恢复，或董事会 `REJECT / MODIFY_CONSTRAINTS` 后的重新对齐；不会在 idle maintenance 里泛化自动开会，也不会对 `MEETING_ESCALATION` 再递归开会

## 2. Runtime 支持矩阵

当前 runtime 默认走本地 `LOCAL_DETERMINISTIC`。如果员工 `provider_id=prov_openai_compat`，并且本地保存了完整 provider 配置，同一批主线角色和输出会走 `OPENAI_COMPAT_LIVE`。

| owner role | role profile | 输出 | Deterministic | OpenAI Compat Live | 备注 |
|------------|--------------|------|---------------|--------------------|------|
| `frontend_engineer` | `ui_designer_primary` | `consensus_document` | 支持 | 支持 | 当前共识文档仍由旧 scope 共识链产出 |
| `frontend_engineer` | `frontend_engineer_primary` | `implementation_bundle` | 支持 | 支持 | `BUILD` 产物当前由独立 frontend worker 产出 |
| `checker` | `checker_primary` | `delivery_check_report` | 支持 | 支持 | `CHECK` 报告当前由 checker 产出 |
| `frontend_engineer` | `frontend_engineer_primary` | `ui_milestone_review` | 支持 | 支持 | 最终董事会 review 包当前由独立 frontend worker 产出 |
| `frontend_engineer` | `frontend_engineer_primary` | `delivery_closeout_package` | 支持 | 支持 | closeout package 当前由独立 frontend worker 产出 |
| `checker` | `checker_primary` | `maker_checker_verdict` | 支持 | 支持 | 主线 maker-checker verdict 当前都走 checker |

当前不应误判的点：

- `OpenAI Compat` live path **不只** 支持 `ui_milestone_review` 和 `maker_checker_verdict`
- 当前主线真实覆盖的 role profile 已经是三类：`ui_designer_primary`、`frontend_engineer_primary`、`checker_primary`
- CEO 的 `REQUEST_MEETING` 当前也同时支持 deterministic 和 OpenAI Compat live，但 deterministic 只会在 snapshot 里恰好存在一个合格会议候选时触发

## 3. 冻结边界清单

下面这些能力在仓库里还在，部分路由也还挂着，但**默认不继续扩张**。只有直接解堵本地 MVP 时，才允许最小修改。

| 能力 | 真实入口 | 当前主线依赖 | 当前处理 | 迁移前置条件 |
|------|----------|--------------|----------|--------------|
| `worker-admin` 管理面 | `/api/v1/worker-admin`、`/api/v1/projections/worker-admin-audit`、`/api/v1/projections/worker-admin-auth-rejections`、`worker_admin_auth_cli.py` | 无 | 冻结，真实实现已迁入 `_frozen/worker_admin`，现有入口只保留兼容壳 | 兼容壳删除前，`worker-admin` API、认证投影和 CLI 仍需成组收口 |
| 多租户 scope / binding | `commands/runtime/worker_admin/worker_runtime` 契约、`/api/v1/projections/worker-runtime` 等共享读面 | 主线 command handler 已不再直接依赖 `tenant_id/workspace_id`，但 runtime / worker-admin / worker-runtime contracts 与共享读面仍保留这组数据形状 | 冻结，但保留兼容数据结构；这块是共享数据结构，不是可独立搬走的目录 | 在 `tenant_id/workspace_id` 脱离 runtime、projection 和冻结 contracts 的数据形状前，不做物理迁移 |
| 控制面上传 / 可选对象存储 | `/api/v1/artifact-uploads`、`artifact_uploads.py`、`artifact_store.py`、`_frozen/object_store.py` | 主线已改成“先导入 upload session 为 artifact，再由 `ticket-result-submit` 只引用 `artifact_ref`”；本地 artifact 存储与 upload staging 仍属主线 | 冻结，只保留最小解堵；可选对象存储实现已迁入 `_frozen/object_store.py`，不继续平台化 | 只有在 upload 导入入口和 upload session 存储也不再被主线需要时，才谈物理迁移 |
| 外部 worker handoff | `/api/v1/worker-runtime`、`/api/v1/projections/worker-runtime`、`worker_auth_cli.py` | 无 | 冻结，保留交接面和运维读面，但不作为当前主线继续推进 | `worker-runtime` 路由、投影和 bootstrap/session/delivery-grant 存储仍共用现有 schema，不能拆一半搬一半 |

这张边界表的目的不是否认这些代码存在，而是避免再次把它们误写成当前 MVP 主线。

当前补记：

- `artifact_uploads_and_object_store` 不能误判成“整块冻结死代码”，因为主线虽然已经不再让 `ticket-result-submit` 直接消费 upload session，但当前仍保留独立的 `ticket-artifact-import-upload` 导入入口
- 这轮已把可选对象存储实现拆到 `backend/app/_frozen/object_store.py`；`backend/app/core/artifact_store.py` 现在只保留主线必需的本地 artifact 存储、upload staging 和统一入口，这轮又进一步把 object-store backend 的建链细节也收进了 `_frozen/object_store.py`
- `worker-admin` 这轮已完成 shim 物理迁移：真实实现现在位于 `backend/app/_frozen/worker_admin/`，但 `app/api/worker_admin*.py`、`app/core/worker_admin.py` 和 `app/worker_admin_auth_cli.py` 仍保留兼容入口
- `multi_tenant_scope` 这轮已从主线 command 侧去掉 `tenant_id/workspace_id`：`project-init`、`ticket-create`、CEO 建票和审批 follow-up 建票现在统一从 workflow/default 解析 scope
- 命令 API 为了兼容旧调用，当前仍接受 `tenant_id/workspace_id`，但这两个字段不再驱动主线路径，也不再作为主线 command 契约的一部分
- `multi_tenant_scope` 当前仍不能按目录整体搬走，因为 runtime contracts、worker-admin / worker-runtime contracts 和共享读面还保留这组多租户数据形状；这轮只是在 `backend/app/contracts/scope.py` 里把这组 shared scope shape 收成了单点 contract
- 冻结边界当前不只记录入口和阻塞摘要；`backend/app/core/mainline_truth.py` 已把对应 `api_surface_groups` 和共享存储表锚点也固化成代码真相，并由 `backend/tests/test_mainline_truth.py` 持续回归
