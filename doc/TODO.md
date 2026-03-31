# TODO

这份 TODO 由根 `README`、设计文档和最近仍有效的 `memory-log` 归纳而来，只保留当前还没完成、且没有明显过期的事项。

## Runtime / Backend

- 多租户 worker 运维面第二批连续切片已落地：
  - CLI 与后端现在共用同一套 worker admin 服务，不再各自复制 binding / bootstrap 规则
  - 新增 `GET /api/v1/worker-admin/bindings` 与 `GET /api/v1/worker-admin/bootstrap-issues`，可以直接按 worker / scope 看 binding 和 bootstrap issue
  - 新增 `POST /api/v1/worker-admin/create-binding`、`issue-bootstrap`、`revoke-bootstrap`、`revoke-session`、`revoke-delivery-grant`、`cleanup-bindings`，把常见事故处置动作拉进同一控制面
  - `GET /api/v1/projections/worker-runtime` 继续负责统一观察 binding、session、delivery grant 和拒绝日志，并回显更清楚的撤销审计字段
- 多租户 worker 运维面第三批连续切片已落地：
  - 新增 `GET /api/v1/worker-admin/sessions`、`delivery-grants`、`auth-rejections`、`scope-summary`，值守同学现在可以直接按 `tenant_id + workspace_id` 看租户下的 worker 运行态，而不必先猜 `worker_id`
  - 新增 `POST /api/v1/worker-admin/contain-scope`，支持先 dry-run 预演 impact，再带 `expected_*` 计数保护做真正止血；现场变了会返回 `409`
  - scope containment 会写入独立的 `revoked_via = worker_admin_scope_containment`，方便事后区分“单条撤销”和“批量止血”
- 多租户 worker 运维面第四批连续切片已落地：
  - `worker-admin` HTTP 入口现在必须携带操作人上下文，最小角色模型为 `platform_admin`、`scope_admin`、`scope_viewer`
  - `scope_admin` / `scope_viewer` 只能显式查看自己的 `tenant_id + workspace_id` scope，不能再用不带 scope 的查询横向扫读
  - `issue-bootstrap`、`revoke-session`、`revoke-delivery-grant`、`contain-scope` 等 HTTP 写接口现在把 `issued_by` / `revoked_by` 统一收口到受信操作人身份；请求体若带不一致值会直接返回 `400`
- 多租户 worker 运维面第五批连续切片已落地：
  - `worker-admin` 不再单独信 `X-Boardroom-Operator-*` 裸头，所有入口现在都必须携带 `X-Boardroom-Operator-Token`；旧头只剩兼容断言作用，不再代表身份
  - 新增 `python -m app.worker_admin_auth_cli issue-token`，平台值守和租户管理员现在可以先签发短时效操作人令牌，再调用 `worker-admin`；默认 TTL 15 分钟，最大 TTL 1 小时
  - 新增 `worker_admin_action_log` 和 `GET /api/v1/projections/worker-admin-audit`，值守同学现在不只看 session / grant 被谁撤了，还能直接按 scope 看谁做过 `create-binding`、`issue-bootstrap`、`contain-scope`、`cleanup-bindings` 等动作，以及是不是 dry-run
- 继续推进更强多租户远端隔离：
  - 在现有签名令牌入口之外，继续收紧公开互联网场景下的安全边界，例如反向代理断言、更强的外网暴露策略、独立租户管理面，以及完整身份层
- 把当前命令驱动的 artifact delete / cleanup 推进到自动后台清理、更细粒度 retention policy 和更大文件的上传路径
- 扩展 output schema registry，不再只真实覆盖 `ui_milestone_review@1` 和 `consensus_document@1`
- 补齐更完整的 provider 路由、多 provider 控制面和恢复策略
- 解决 `backend/pyproject.toml` 的 editable install 打包问题，让 `pip install -e .[dev]` 在新环境可用

## Workflow Governance

- 完成 employee hire / replace / freeze 生命周期
- 落地 Maker-Checker review loop，而不只是停留在设计层
- 把 Review Room 从“已持久化审批包投影”扩展到更完整的证据拼装
- 把 reference-only Context Compiler 推进到带 artifact hydration、检索和缓存复用的完整编译链
- 增加 richer retry policy 和超出最小闭环的自动恢复能力

## Search / Retrieval

- 增加 FTS 检索
- 增加向量检索能力

## Frontend / Product

- 实现 React Boardroom UI
- MVP 后补上 Meeting Room 专用界面
- MVP 后补上高级 dependency graph explorer
- MVP 后补上历史分析、多 workspace 管理和更深入的员工画像浏览
