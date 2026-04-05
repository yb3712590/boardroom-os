# Memory Log

> This file is intentionally compact. Stable baseline context now lives in `doc/history/context-baseline.md`.
> Detailed older round logs still live in:
>
> - `doc/history/archive/memory-log-detailed-2026-03-27_to_2026-03-30.md`
> - `doc/history/archive/memory-log-detailed-2026-03-31_to_2026-04-02.md`

## How To Use This File

- Read `doc/history/context-baseline.md` first for stable rules and architecture.
- Read `doc/TODO.md` next for the current action list.
- Use this file only for recent changes that still affect implementation decisions.
- Open the archive only when exact historical rationale, raw verification commands, or old compatibility details are required.

## Current Mainline Truth

- Current executable truth now lives in `doc/mainline-truth.md`.
- This file no longer duplicates the stable product model, governance rules, or frozen-boundary notes.
- Treat this file as compressed recent memory, not as a second truth source.

## Recent Memory

### 2026-04-03

- `delivery_check_report@1` gained its own internal checker gate before final board review.
- Final board approval now auto-creates a `delivery_closeout_package@1` ticket, and workflow completion depends on that closeout loop finishing.
- Thin staffing deblocking became available in the React shell through `freeze / restore / hire request / replace request` controls.
- Added `doc/mainline-truth.md` as the dedicated entrypoint for current code truth and runtime support.
- OpenAI Compat live execution now retries `timeout / 429 / 5xx`, classifies non-retry failures cleanly, and falls back to deterministic execution without breaking the workflow.
- Provider health is now surfaced through stable labels: `LOCAL_ONLY / HEALTHY / INCOMPLETE / PAUSED`.
- `frontend_engineer` now has an independent runtime profile, while scope kickoff keeps a narrow compatibility alias to the legacy scope-only lane.

### 2026-04-04

- Successful live-path structured outputs now materialize the same default audit artifacts as deterministic execution, so scope approval, review evidence, and closeout read from one consistent shape.
- CEO shadow mode became real through `ceo_actions.py`, `ceo_snapshot.py`, `ceo_prompts.py`, `ceo_proposer.py`, `ceo_validator.py`, and `ceo_scheduler.py`.
- CEO then moved into a limited-execution first slice: accepted `CREATE_TICKET / RETRY_TICKET / HIRE_EMPLOYEE` actions now execute through the existing command handlers, while `ESCALATE_TO_BOARD` stays `DEFERRED_SHADOW_ONLY`.
- `project-init` now lets CEO create the first stable kickoff scope ticket instead of hardcoding that ticket in `command_handlers.py`.
- `scheduler_runner.py` now runs idle CEO maintenance when a workflow has no active approval or incident, no leased/executing ticket, and still has a clear actionable signal.
- Frontend data-layer split is now real: the live types, clients, SSE manager, hook, and Zustand stores moved under `frontend/src/types/`, `frontend/src/api/`, `frontend/src/hooks/`, and `frontend/src/stores/`.
- `App.tsx` is back to a pure router entry, while layout, dashboard, workforce, events, overlays, shared UI primitives, styles, and utilities all moved into dedicated folders.
- Persona data now has one source of truth in `backend/app/core/persona_profiles.py`; runtime execution packages carry `persona_summary`, and both Workforce and staffing review views expose that normalized persona shape.
- Full verification by the end of this day had reached `py -m pytest tests/ -q` -> `394 passed`, `npm run build` -> passed, and `npm run test:run` -> `49 passed`.

### 2026-04-05

- Expanded the old aggregated `P0-INT-*` placeholder into eight explicit integration-closure tasks in `doc/task-backlog.md`.
- Added explicit deterministic, provider fallback, staffing containment recovery, timeout recovery, repeated failure recovery, provider recovery, frontend smoke, and incident drawer regression proofs for the current mainline.
- Full verification for the integration-closure round reached `py -m pytest tests/ -q` -> `399 passed`, `npm run build` -> passed, and `npm run test:run` -> `50 passed`.
- Split long-term requirements into two tracks and kept them out of `doc/TODO.md`: framework capability and company governance.
- `doc/feature-spec.md`, `doc/milestone-timeline.md`, and `doc/task-backlog.md` now explicitly cover multi-model coexistence, role-to-model binding, task-level override, preferred/actual model tracking, and high-cost low-frequency routing.
- `DashboardPage.tsx` was further slimmed from 629 lines to 298 through page-level helper files, and `StaffingActions` now shows hire-template persona summary through `ProfileSummary`.
- Added the first ticket-backed meeting room slice without creating a second chat system: backend now supports `meeting-request`, four auditable meeting event types, a persisted meeting projection, and a `TECHNICAL_DECISION` meeting state machine that runs `POSITION -> CHALLENGE -> PROPOSAL -> CONVERGENCE` over a `consensus_document` ticket.
- The React shell now has a read-only meeting path at `/meeting/:meetingId`, and inbox meeting items open `MeetingRoomDrawer` with topic, participants, round summaries, consensus state, and jump-through to review room.
- CEO now has a limited `REQUEST_MEETING` execution path: `ceo_shadow_snapshot` exposes auditable `meeting_candidates`, deterministic mode only opens a meeting when exactly one candidate is eligible, and live provider proposals are constrained to those snapshot candidates.
- Automatic meetings stay narrow: they only cover decision-oriented ticket failure recovery or board `REJECT / MODIFY_CONSTRAINTS` realignment, they do not run in idle maintenance, and they do not recursively reopen `MEETING_ESCALATION`.
- Full verification for the CEO auto-meeting round finished at `py -m pytest tests/ -q` -> `408 passed`, `npm run build` -> passed, and `npm run test:run` -> `53 passed`.

## Current Working Set

- Prefer reading `README.md`, `doc/README.md`, `doc/mainline-truth.md`, `doc/roadmap-reset.md`, `doc/TODO.md`, `doc/history/context-baseline.md`, and then this file before touching the archive.
- Treat this file as semantic memory plus compressed recent progress, not as a full transcript.
- When adding new memory, keep only facts that still change implementation decisions; push raw logs and exhaustive verification into archive files.

## Archive Index

- `doc/history/archive/memory-log-detailed-2026-03-27_to_2026-03-30.md`: detailed early history before the roadmap reset was fully absorbed.
- `doc/history/archive/memory-log-detailed-2026-03-31_to_2026-04-02.md`: detailed recent implementation notes before this compaction pass.
