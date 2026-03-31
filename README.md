# Boardroom OS

> Event-sourced agent governance for autonomous software delivery.

Boardroom OS 想做的不是“多 Agent 群聊外壳”，而是一个可审计、可治理、可审批的 Agent 交付控制面：用户扮演董事会，只给目标、约束和验收标准；系统持续拆解、委派、推进；关键节点通过明确的审批门和事件记录留痕。

## 这是什么

- 一个围绕 `Board -> CEO -> Worker -> Gate` 这条链路设计的 Agent Operating System
- 一个把“持续推进”“结构化交付”“治理可追溯”放在聊天体验之前的项目
- 一个以后端控制面为先、再逐步补齐前端和更完整产品面的仓库

## 当前进度

这个仓库已经不是纯设计稿，而是“设计文档 + 可运行后端切片”：

- 已有 FastAPI + SQLite 的后端控制面
- 已跑通 ticket 生命周期、结构化结果提交、审批和 incident 治理
- 已有 artifact 持久化、投影读面、事件流和审计基础
- artifact 生命周期现在已经补到“可过期 + 调度自动清理 + dashboard 可见清理状态”
- 已跑通外部 worker handoff，包括 bootstrap、session、signed delivery 和多租户 scope 约束
- 已补到多租户 worker 的租户级运维闭环，包括 binding 生命周期、统一观察面、`worker-admin` 下的 bootstrap / session / delivery grant 管理、按租户读面、带 dry-run / 计数保护的 scope 止血入口，以及带持久化 `token_id`、活动令牌列表 / 撤销和独立鉴权拒绝读面的受信签名操作人令牌入口

当前状态更接近“最小可运行控制面原型”，还不是完整产品。

## 当前已实现的 Feature

- 治理与审批：ticket 生命周期、Board 审批、incident / circuit-breaker / retry 治理已经串起来
- 运行时交付：支持结构化结果入口、artifact 持久化、外部 worker handoff 和最小调度闭环
- artifact 运维：`EPHEMERAL` 产物现在会进入自动 cleanup 闭环，`dashboard` 可直接看到最近一次 cleanup 是否跑过、删了多少、还有没有待处理积压
- 审计与可追溯：事件流、projection、SQLite WAL、compile 相关产物都已真实落盘
- 运维与排障：已有 `dashboard`、`inbox`、`review room`、`worker-runtime` 等读面，也有可直接按租户查看 session / grant / rejection、做 scope-summary、看独立 `worker-admin` 动作审计与操作人鉴权拒绝读面，以及带 dry-run / `409` 保护、可直接列出 / 撤销活动操作人令牌的 `worker-admin` HTTP 入口和本地运维 CLI

## 开发主线

- 当前最顺手的主线仍然是 `Runtime / Backend`
- 最近一批完成的是“多租户 worker 运维面 -> 租户级读面 + 安全批量止血入口 + 受信入口边界 + 独立操作审计读面”，以及紧接着补上的“artifact 自动清理闭环 -> 物理删除记账 + 调度自动 cleanup + dashboard 清理读面”
- 还在后面的主要方向包括：更强公网安全边界、artifact 自动清理与大文件链路、完整 Context Compiler、Search / Retrieval、React UI

更细的进行中事项看 [doc/TODO.md](doc/TODO.md)。

## 快速开始

启动后端：

```bash
cd backend
source .venv/bin/activate
uvicorn app.main:app --reload
```

运行测试：

```bash
cd backend
source .venv/bin/activate
python -m pytest tests -q
```

如果你要看更详细的运行方式、外部 worker 模式、运维命令和环境变量，请直接看 [doc/backend-runtime-guide.md](doc/backend-runtime-guide.md)。

## 文档入口

- [doc/README.md](doc/README.md)：文档总索引
- [doc/TODO.md](doc/TODO.md)：当前路线和未完成事项
- [doc/backend-runtime-guide.md](doc/backend-runtime-guide.md)：后端运行、外部 worker handoff 和运维说明
- [doc/feature-spec.md](doc/feature-spec.md)：产品边界和治理规则总表
- [doc/design/message-bus-design.md](doc/design/message-bus-design.md)：后端主线设计
- [doc/history/memory-log.md](doc/history/memory-log.md)：近期进展和长期记忆

## 当前已知现实

- `backend/` 的 editable install 还没完全补平，新环境下 `pip install -e .[dev]` 仍可能出问题
- 大文件上传还没有 multipart / 分片 / 对象存储链路，当前更适合中等体量文件；这轮只补了现有本地 artifact store 的自动 cleanup，没有扩到大文件链路
- `worker-admin` 现在已经要求短时效签名操作人令牌，不再单独信裸请求头；新签发令牌会持久化 `token_id`，可列出、可撤销、撤销后会立即失效并写鉴权拒绝日志；默认 TTL 为 15 分钟、最大 TTL 为 1 小时，但公开互联网场景下还没有完整身份层、反向代理断言或租户自助面

## 项目原则

- 治理比热闹重要
- 审计比想象重要
- 幂等比炫技重要
- 结构化协作比自由群聊可靠

最终目标不是做一个“很会聊天的 Agent 项目”，而是做一个真正可推进、可治理、可交付的 Agent Operating System。
