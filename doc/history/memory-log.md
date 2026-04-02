# Memory Log

> This file is intentionally compact. Detailed older round logs now live in:
>
> - `doc/history/archive/memory-log-detailed-2026-03-27_to_2026-03-30.md`
> - `doc/history/archive/memory-log-detailed-2026-03-31_to_2026-04-02.md`

## How To Use This File

- Read this file first for stable context and the latest mainline truth.
- Read `doc/TODO.md` next for the current action list.
- Open the archive only when exact historical rationale, raw verification commands, or old compatibility details are required.

## Long-Term Memory

### Product Model

- Boardroom OS is an event-sourced agent delivery control plane, not a multi-agent chat shell.
- The intended operating model remains: Board -> structured worker execution -> auditable deliverables -> explicit review gates.
- Board involvement should stay limited to real approval points, not internal drafting chatter.
- React Boardroom UI is a thin governance shell; workflow truth stays in backend events and projections.

### Governance Rules

- Ticket lifecycle, incidents, approvals, and review loops are the real control surface.
- Maker-Checker is the default internal quality gate before CEO or Board escalation.
- Important outputs must stay schema-checked, write-set-checked, and auditable.
- Runtime should keep work moving autonomously and escalate only on defined blocking, risk, or approval conditions.

### Stable Architecture

- Backend remains the executable center: FastAPI + Pydantic v2 + SQLite.
- Durable truth lives in the event log plus deterministic projections.
- Worker input should come from a compiled execution package, not ad hoc payload stitching.
- Context Compiler is the deterministic boundary for evidence selection, budget control, and audit artifacts.
- Runtime output should flow back through the same structured `ticket-result-submit` ingress.

### Frozen But Still Present

- The repo still contains heavier infrastructure slices such as `worker-admin`, multi-scope worker binding, object-store support, and remote handoff.
- Those paths are not current mainline. Unless they directly unblock local MVP, treat them as frozen.

## Current Mainline Truth

- Local MVP chain is now real: `project-init -> scope review -> BUILD internal maker-checker -> CHECK -> final REVIEW -> closeout internal maker-checker`.
- `BUILD` no longer feeds `CHECK` directly. `implementation_bundle@1` must pass an internal `maker -> checker -> fix / incident` loop first.
- `CHECK` no longer feeds final board review directly either. `delivery_check_report@1` must now pass its own internal `maker -> checker -> fix / incident` loop before final `REVIEW` starts.
- Final board approval no longer ends the workflow immediately. It now auto-creates a `delivery_closeout_package@1` ticket, and that package must pass its own internal `maker -> checker -> fix / incident` loop before completion is exposed.
- Maker-Checker currently covers five real artifact families: `consensus_document@1`, `implementation_bundle@1`, `delivery_check_report@1`, `ui_milestone_review@1`, and `delivery_closeout_package@1`.
- Employee governance is on the mainline: `hire / replace / freeze / restore`, staffing containment, and containment recovery all run through events and projections.
- `dashboard / inbox / review room / incident / workforce / dependency inspector / completion` are live in the React shell.
- `workforce` now exposes `rework loops`, so build/check-chain rework pressure is visible without reading raw events.
- `workforce` now also exposes server-driven staffing templates and actions, so supported `freeze / restore / hire request / replace request` flows no longer require dropping to CLI.
- Deterministic runtime remains the zero-config default; local `OpenAI Compat` config is optional and already wired into the UI.
- Context Compiler already supports inline text, fragment fallback, preview fallback, media/download refs, local history summary cards, and deterministic `json_messages_v1` rendering.

## Main Remaining Gaps

- More ticket types still need the same staffing policy depth that build/visual/consensus/closeout now have.
- Heavier publish / launch / deploy style post-closeout paths are still not yet on the MVP mainline.
- UI is still intentionally thin: it shows current truth, but richer trend and analysis surfaces are still missing.
- Provider routing, richer retrieval, public identity, and remote control-plane work remain post-MVP unless they directly unblock the local chain.

## Recent Memory

### 2026-03-31

- Closed the first real maker-checker loop for `ui_milestone_review@1`.
- Moved employee lifecycle and staffing containment into the event-sourced mainline.
- Kept heavier `worker-admin` and public-edge work in the repo, but those paths became explicitly non-mainline.

### 2026-04-01

- Brought the first real React Boardroom shell onto the MVP path.
- Pushed Context Compiler from simple inline text support to budgeted fragments, previews, media refs, history summaries, rendered execution payloads, and optional local `OpenAI Compat` execution.
- Added `dependency inspector`, runtime provider settings, and final completion card to the UI.

### 2026-04-02

- `project-init` now auto-advances to the first scope review instead of stopping at workflow creation.
- `board-approve` now consumes approved scope follow-ups and continues the staged chain toward the next real governance stop.
- The default local chain now runs `BUILD -> CHECK -> REVIEW` instead of stopping at a single early visual ticket.
- `implementation_bundle@1` now has an internal build checker gate with real rework and incident handling before downstream `CHECK`.

### 2026-04-03

- `delivery_check_report@1` now has its own internal checker gate with real `maker -> checker -> fix / incident` handling before final board review.
- Scope follow-up `CHECK` tickets now carry a dedicated internal review type instead of reusing the build-bundle wording.
- `workforce_summary.rework_loops` now reflects both build-chain and check-chain rework pressure.
- Final board approval now auto-creates a `delivery_closeout_package@1` ticket, and that package also goes through internal maker-checker before the workflow is considered complete.
- Dashboard completion now depends on closeout completion, not just final board approval; the React completion card shows both the final review approval time and the closeout completion time.
- Staffing deblocking is now closed through the thin UI as well: supported hire/replace requests are validated against a tiny mainline staffing catalog, and `workforce` now provides server-driven `freeze / restore / hire request / replace request` controls instead of leaving operators on the CLI.

### 2026-04-02 (docs compaction)

- Simplified the homepage `README.md` so first-time readers see the product definition, current real chain, quick start, and doc entrypoints without scrolling through round-by-round implementation history.
- Moved the previous detailed `memory-log.md` snapshot into a new archive file and rewrote this file as a compact working-memory document.

## Current Working Set

- Prefer reading `README.md`, `doc/README.md`, `doc/roadmap-reset.md`, and `doc/TODO.md` before touching the archive.
- Treat this file as semantic memory plus compressed recent progress, not as a full transcript.
- When adding new memory, keep only facts that still change implementation decisions; push raw logs and exhaustive verification into archive files.

## Archive Index

- `doc/history/archive/memory-log-detailed-2026-03-27_to_2026-03-30.md`: detailed early history before the roadmap reset was fully absorbed.
- `doc/history/archive/memory-log-detailed-2026-03-31_to_2026-04-02.md`: detailed recent implementation notes before this compaction pass.
