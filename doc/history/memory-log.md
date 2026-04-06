# Memory Log

> This file is intentionally compact. Stable baseline context lives in `doc/history/context-baseline.md`.
> Detailed recent logs now live in:
>
> - `doc/history/archive/memory-log-detailed-2026-03-27_to_2026-03-30.md`
> - `doc/history/archive/memory-log-detailed-2026-03-31_to_2026-04-02.md`
> - `doc/history/archive/memory-log-detailed-2026-04-03_to_2026-04-06.md`

## How To Use This File

- Read `doc/history/context-baseline.md` first for stable rules and architecture.
- Read `doc/TODO.md` next for the current action list.
- Use this file only for recent changes that still affect implementation decisions.
- Open the archive only when exact historical rationale, raw verification commands, or old compatibility details are required.

## Current Mainline Truth

- Current executable truth lives in `doc/mainline-truth.md`.
- This file is recent memory, not a second truth source.

## Recent Memory

### 2026-04-03

- `delivery_check_report@1` 获得独立 checker gate，final review 通过后会自动补 `delivery_closeout_package@1`，workflow 完成口径因此改成 closeout 真正收口
- `doc/mainline-truth.md` 成为当前代码真相入口，provider 健康标签也收口成 `LOCAL_ONLY / HEALTHY / INCOMPLETE / PAUSED`
- `frontend_engineer` 已有独立 runtime profile，scope kickoff 只保留兼容 alias

### 2026-04-04

- CEO 从影子进入有限执行首轮：当前真实执行 `CREATE_TICKET / RETRY_TICKET / HIRE_EMPLOYEE / REQUEST_MEETING`，`ESCALATE_TO_BOARD` 仍保持 `DEFERRED_SHADOW_ONLY`
- `project-init` 的首个 scope kickoff 票改由 CEO 发起，`scheduler_runner.py` 也会在空转时做受控 idle maintenance
- 前端数据层拆分和 persona 真相源收口完成，执行包当前会携带 `persona_summary`

### 2026-04-05

- `P0-INT-*` 收口为八条明确集成验收任务，主线 deterministic、provider、incident、frontend 烟囱覆盖矩阵已明确
- 最小会议室主线落地：`meeting-request`、`TECHNICAL_DECISION` 状态机、会议投影和只读 `MeetingRoomDrawer` 已进入真实闭环
- 自动会议仍只覆盖窄触发条件，不递归 reopen `MEETING_ESCALATION`
- `P1-CLN-005`、`P1-CLN-006` 已关闭，冻结边界、测试归属和迁移前置条件已写进 `mainline_truth.py`

### 2026-04-06

- `P1-CLN-001` 与 `P1-CLN-004` 已完成 shim 迁移：真实实现分别进入 `backend/app/_frozen/worker_admin/` 和 `backend/app/_frozen/worker_runtime/`
- `P1-CLN-002` 与 `P1-CLN-003` 的 blocker 已进一步收口：共享 scope data shape 仍保留，upload 导入入口与 session 存储仍保留
- `FrozenCapabilityBoundary` 现在还会记录 `api_surface_groups` 与 `storage_table_refs`，接口分组也有 `api_surface.py` 回归保护
- 高频文档入口这轮已按新愿景重整：`README`、`TODO`、`task-backlog`、`milestone-timeline` 和 `postponed` 已重新分层，不再把当前批次、已完成补记和远期储备混写
- `P2-GOV-007` 已按 soft rule 收口：`delivery_closeout_package@1` 可选携带 `documentation_updates`，closeout checker / runtime review 会显式总结文档同步状态，但不会把 `FOLLOW_UP_REQUIRED` 自动升级成硬门禁
- runtime 生成 structured artifact 的写回顺序已收正：`implementation_bundle`、`delivery_check_report`、`delivery_closeout_package` 的默认 artifact 现在会持久化最终 payload，而不是先写空壳再补内存结果
- `P2-RET-001` 到 `P2-RET-005` 已完成：SQLite 现在有 `review / incident / artifact` 三通道 FTS5 检索索引，repository 检索改成“查询前懒刷新 + FTS 命中 + 稳定排序去重”
- `P2-RET-006` 已完成：execution package 与 rendered `SYSTEM_CONTROLS` 现在都会携带结构化 `org_context`，最小暴露上游提供者、下游 reviewer、活跃 sibling 协作者、升级路径和职责边界；缺 direct dependent 时会回退到预期 reviewer，不新建持久化或 retrieval 通道
- artifact 检索继续保留原有粗匹配边界：只有路径 / `kind` / `media_type` 先命中关键词时，正文命中才会进入历史 retrieval summary，避免把当前输入附件正文误回灌进执行包
- 当前主线已从 `P2-B` 切到 `M7`：`P1-CLN-002/003` 降级为冻结后置，`P2-M7-001` 到 `P2-M7-005` 已全部完成；当前没有新的可直接开启主线任务
- 前端现在有统一 `ArtifactPreviewDrawer`：Review Room 的 artifact 型 evidence `source_ref`、option `artifact_refs` 和 completion card 的 final / closeout artifact refs 都会接到现有本地 artifact metadata / preview / content 只读接口，不新建 artifact 浏览器
- completion 投影现在会汇总 closeout 文档同步摘要、更新数和 follow-up 数；Review Room 也会展示 evidence `source_ref`，当前验证基线更新为 backend `437 passed`、frontend build passed、frontend `70 passed`
- `P2-CEO-001` 已完成：`project-init` 现在支持显式 `force_requirement_elicitation`，也会在保守启发式命中明显弱输入时先打开 `REQUIREMENT_ELICITATION`
- 初始化澄清继续复用现有 `Inbox -> Review Room -> board-*` 审批流；董事会在 Review Room 提交结构化 `elicitation_answers` 后，`APPROVE` 会生成 `requirements-elicitation` / enriched board brief artifact 并继续进入 scope kickoff，`MODIFY_CONSTRAINTS` 会重新打开一版澄清板审
- 当前验证基线更新为 backend `441 passed`、frontend build passed、frontend `72 passed`

## Current Working Set

- Prefer reading `README.md`, `doc/README.md`, `doc/mainline-truth.md`, `doc/roadmap-reset.md`, `doc/TODO.md`, `doc/history/context-baseline.md`, and then this file before touching the archive.
- Keep only facts that still change implementation decisions here; move raw logs and exhaustive verification into archive files.
