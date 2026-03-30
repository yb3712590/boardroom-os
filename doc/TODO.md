# TODO

这份 TODO 由根 `README`、设计文档和最近仍有效的 `memory-log` 归纳而来，只保留当前还没完成、且没有明显过期的事项。

## Runtime / Backend

- 多租户 worker 运维面第二批连续切片已落地：
  - CLI 与后端现在共用同一套 worker admin 服务，不再各自复制 binding / bootstrap 规则
  - 新增 `GET /api/v1/worker-admin/bindings` 与 `GET /api/v1/worker-admin/bootstrap-issues`，可以直接按 worker / scope 看 binding 和 bootstrap issue
  - 新增 `POST /api/v1/worker-admin/create-binding`、`issue-bootstrap`、`revoke-bootstrap`、`cleanup-bindings`，形成最小 HTTP 管理闭环
  - `GET /api/v1/projections/worker-runtime` 继续负责统一观察 binding、session、delivery grant 和拒绝日志
- 继续推进更强多租户远端隔离：
  - 把当前最小 HTTP 管理面继续推进成更完整的租户管理面，例如 session / delivery grant 管理、粒度更细的租户自助能力
  - 收紧公开互联网场景下的安全边界，例如更强的外网暴露策略、独立租户管理面和更完整的身份层
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
