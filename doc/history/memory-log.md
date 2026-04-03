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
- Added a dedicated `doc/mainline-truth.md` entrypoint so the current code truth, runtime support matrix, and frozen boundary list stop drifting across docs.
- Locked the current reality in code as `backend/app/core/mainline_truth.py`, including the important gap that `frontend_engineer` still maps to `ui_designer_primary` instead of a separate worker role.
- Re-aligned `README.md`, `doc/README.md`, `doc/TODO.md`, and `doc/backend-runtime-guide.md` around that truth source rather than the older mixed mainline-plus-frozen narrative.
- Follow-up doc closure marked `P0-A` as done in `doc/TODO.md`, added explicit mainline-relation notes to the active TODO sections, and recorded one still-open decision: whether `frontend_engineer` should stay an owner-role alias or become a real runtime worker.
- Updated `doc/task-backlog.md` to reflect current code truth: `P0-WRK-001 / 002 / 004 / 005` are already complete, while `P0-WRK-003` remains open because the repo still routes that work through `ui_designer_primary`.
- OpenAI Compat live execution now retries `timeout / 429 / 5xx` with fixed backoff and `Retry-After` support, while `401/403 / bad response / schema mismatch` stop live execution immediately.
- Pause-worthy provider failures now keep using the existing provider incident + breaker loop, but the current ticket no longer dies with them; runtime falls back to deterministic completion and carries the fallback evidence forward.
- Dashboard and runtime-provider read models now use stable provider health labels: `LOCAL_ONLY / HEALTHY / INCOMPLETE / PAUSED`; paused and incomplete reasons explicitly state that runtime is falling back to deterministic.
- Already leased OpenAI Compat tickets can now continue through local fallback even when the provider is already paused, instead of getting stranded before execution.
- Backend verification for this round finished at `365 passed`; frontend code was updated to match the new runtime-provider contract, but this machine still does not have Node.js / npm, so frontend build and test were not rerun here.
- `frontend_engineer` now has an independent `frontend_engineer_primary` runtime profile for `implementation_bundle@1`, `ui_milestone_review@1`, and `delivery_closeout_package@1`; mainline staffing templates and the default roster now expose that profile instead of `ui_designer_primary`.
- `project-init -> scope review` still stays on `ui_designer_primary`, so scheduler dispatch now carries a narrow compatibility alias from `frontend_engineer_primary` to that legacy scope-only ticket lane instead of rewriting the scope chain itself.
- This round’s focused backend verification for the worker-role split finished at `344 passed`, and the follow-up API + scheduler sweep that exercises the mainline chain finished at `268 passed`.

### 2026-04-04

- Added mock-provider end-to-end coverage for the current mainline in `backend/tests/test_scheduler_runner.py`: one path now proves provider-backed `BUILD -> CHECK -> REVIEW -> closeout` reaches completion, and one path proves a `PROVIDER_BAD_RESPONSE` on final review still falls back cleanly and reaches closeout.
- That verification exposed a real live-path gap: successful OpenAI Compat executions were not materializing the same default runtime artifacts as deterministic execution, which caused provider-backed scope approvals to miss the approved consensus artifact reference.
- Runtime now writes the same default artifact refs and persisted artifact bodies for successful live-path structured outputs as it does for deterministic outputs, so scope approval, review evidence, and closeout completion all read from the same audit shape.
- Full backend verification after this fix finished at `367 passed`.
- Frontend `npm run build` and `npm run test:run` are still blocked on this machine because `npm` is not installed, so the remaining frontend verification gap is environmental rather than code-level.
- Added the first real CEO shadow slice without changing mainline authority: `ceo_actions.py`, `ceo_snapshot.py`, `ceo_prompts.py`, `ceo_proposer.py`, `ceo_validator.py`, and `ceo_scheduler.py` now produce auditable CEO suggestions instead of free text.
- CEO shadow runs are now triggered after ticket completion, ticket failure, approval resolution, and incident recovery; they persist to a dedicated `ceo_shadow_run` store instead of polluting the event log with unexecuted suggestions.
- Added a new read path at `/api/v1/projections/workflows/{workflow_id}/ceo-shadow`, so later UI work can read shadow suggestions and accepted/rejected validation results without direct database inspection.
- Backend verification after the CEO shadow batch finished at `372 passed`.
- CEO shadow closure fixed one real wiring mistake: `ticket-create` no longer emits a bogus `TICKET_FAILED` shadow trigger, and `ticket-fail` now emits its audit trigger from the real failure success path; full backend verification still finished at `372 passed`.
- This machine still does not have `npm`, and the bare `pytest` command is not on PATH; backend verification is reproducible via `py -m pytest tests -q`, while frontend build/test remain environment-blocked rather than code-blocked.
- CEO has now moved past pure shadow mode into a limited-execution first slice: accepted `CREATE_TICKET / RETRY_TICKET / HIRE_EMPLOYEE` actions are translated into the existing command handlers, while `ESCALATE_TO_BOARD` is intentionally left as `DEFERRED_SHADOW_ONLY`.
- The `ceo_shadow_run` store and `/api/v1/projections/workflows/{workflow_id}/ceo-shadow` route now expose `executed_actions`, `execution_summary`, and `deterministic_fallback_*`, so later UI work can compare suggestion, validation, execution, and fallback without opening the database.
- Retry execution now reuses the same ticket retry scheduling helper as the mainline failure path, so retry tickets keep the existing `attempt_no / retry_count / parent_ticket_id / timeout backoff` rules instead of inventing a second retry mechanism.
- Full backend verification after the limited-execution batch finished at `378 passed`; frontend `npm run build` and `npm run test:run` are still blocked on this machine because `npm` is not installed.
- This machine now has Node.js LTS available again, so frontend verification is no longer environment-blocked.
- Frontend data-layer split is now real: `frontend/src/api.ts` has been reduced to a compatibility barrel, while the actual types, projection/command clients, SSE manager, `useSSE` hook, and three Zustand stores live under `frontend/src/types/`, `frontend/src/api/`, `frontend/src/hooks/`, and `frontend/src/stores/`.
- `App.tsx` no longer owns inline fetch wiring or inline SSE setup; it now reads snapshot/review/UI state from stores and calls the split API modules, while `incident detail` and `dependency inspector` state intentionally remain local for the next page-shell batch.
- Frontend verification for this round finished at `npm run build` passed and `npm run test:run` passed with `31 passed`; store resets were added in test setup so the existing long `App.test.tsx` regression suite still runs against clean state.
- Frontend page-shell follow-up is now real: `frontend/src/pages/DashboardPage.tsx` owns route-driven page assembly, SSE invalidation, review/incident loading, and the local `incident detail / dependency inspector` reads that previously stayed in `App.tsx`.
- `frontend/src/components/shared/ErrorBoundary.tsx` and `frontend/src/components/shared/Drawer.tsx` are now in place; the four governance overlays moved under `frontend/src/components/overlays/` and share the same drawer shell instead of each carrying duplicated motion/backdrop code.
- `frontend/src/App.tsx` is now a pure router entry again; the old top-level drawer component files were removed after the overlay migration so there is only one active implementation path.
- Added minimal frontend shared-component tests for drawer close behavior and ErrorBoundary retry behavior; backend verification for this batch still finished at `py -m pytest tests -q` → `378 passed`.
- Current shell no longer has Node.js / npm on PATH, so this round’s frontend `build` and `test:run` could not be re-executed here; the remaining frontend verification gap is environmental again, not a deliberate skip.

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
