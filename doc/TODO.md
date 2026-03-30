# TODO

这份 TODO 由根 `README`、设计文档和最近仍有效的 `memory-log` 归纳而来，只保留当前还没完成、且没有明显过期的事项。

## Runtime / Backend

- 把当前共享密钥版 external worker handoff 推进到更细粒度的签名 URL / per-ticket 短时令牌 / 更强远端可达边界
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
