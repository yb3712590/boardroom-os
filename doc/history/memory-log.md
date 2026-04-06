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

## Current Working Set

- Prefer reading `README.md`, `doc/README.md`, `doc/mainline-truth.md`, `doc/roadmap-reset.md`, `doc/TODO.md`, `doc/history/context-baseline.md`, and then this file before touching the archive.
- Keep only facts that still change implementation decisions here; move raw logs and exhaustive verification into archive files.
