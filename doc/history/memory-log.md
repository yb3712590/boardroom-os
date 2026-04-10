# Memory Log

> This file is intentionally compact and no longer part of the default first-read stack. Stable baseline context lives in `doc/history/context-baseline.md`.
> Detailed recent logs now live in:
>
> - `doc/history/archive/memory-log-detailed-2026-03-27_to_2026-03-30.md`
> - `doc/history/archive/memory-log-detailed-2026-03-31_to_2026-04-02.md`
> - `doc/history/archive/memory-log-detailed-2026-04-03_to_2026-04-06.md`
> - `doc/history/archive/memory-log-detailed-2026-04-07_to_2026-04-10.md`

## How To Use This File

- Read `doc/mainline-truth.md` and `doc/TODO.md` first.
- Open this file only when recent changes still affect implementation decisions.
- Open the archive only when exact historical rationale, raw verification commands, or old compatibility details are required.

## Current Mainline Truth

- Current executable truth lives in `doc/mainline-truth.md`.
- This file is recent memory, not a second truth source.

## Recent Memory

### 2026-04-10

- `python -m tests.live.library_management_autopilot_live` 这条真实 LLM 长测已经证明：当前主线虽然能跑到 closeout，但 `BUILD` 仍会退化成“文档式 artifact 交付”，不是“真实源码交付”
- 当前最高优先级已切到 `P0-COR`：canonical 协议、单一 workflow controller、architect/meeting/source-code deliverable 硬约束，以及源码交付 contract / checker / closeout 硬门禁
- 这条 live 场景的留档仍在 `backend/data/scenarios/library_management_autopilot_live/`，需要复盘真实上下文时优先看这里，不要回看旧计划文档
- `doc/` 根目录的旧 spec、旧计划和旧分析已迁到 `doc/archive/`；高频入口现在只保留当前真相层
- `doc/task-backlog/active.md` 已重写为“只保留未关闭任务”，已完成流水统一留在 `doc/task-backlog/done.md`

## Current Working Set

- Prefer reading `README.md`, `doc/README.md`, `doc/mainline-truth.md`, `doc/roadmap-reset.md`, and `doc/TODO.md` first.
- Open `doc/history/context-baseline.md` only when stable rules matter, and open this file only when recent changes matter.
- Keep only facts that still change implementation decisions here; move raw logs and exhaustive verification into archive files.
