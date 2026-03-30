# Memory Log

> This file is intentionally kept compact and rereadable. Detailed session-by-session history lives in `doc/history/archive/memory-log-detailed-2026-03-27_to_2026-03-30.md`.
>
> Historical file paths in the archive may reflect the repo layout at the time each entry was written. The current documentation entrypoint is `doc/README.md`.

## How To Use This File

- Read this file first for stable context and recent progress.
- Read `doc/TODO.md` for the current action list.
- Open the archive only when exact historical rationale, raw verification commands, or old file-by-file implementation notes are required.

## Long-Term Memory

### Product Model

- Boardroom OS is an event-sourced agent delivery control plane, not a multi-agent chat shell.
- The intended operating model remains: Board -> CEO -> structured worker execution -> auditable deliverables.
- Board involvement should stay limited to explicit approval gates, especially user-visible visual milestones.
- The runtime should keep work moving autonomously and escalate only on defined blocking, risk, or approval conditions.

### Governance And Collaboration Rules

- CEO is responsible for continuous progress, decomposition, delegation, and anti-stall behavior.
- Meeting Room is a bounded, event-driven alignment subworkflow, not free chat.
- Maker-Checker is a structured internal adversarial review stage before CEO or Board escalation when quality gates require it.
- Important outputs must stay schema-checked, write-set-checked, and auditable.

### Architecture Memory

- Backend is the current executable center: FastAPI + Pydantic v2 + SQLite.
- Durable truth lives in the event log plus projections; reducers stay deterministic and side-effect free.
- Worker input should come from a compiled execution package, not ad hoc manual payload hydration.
- Context Compiler remains a deterministic middleware boundary responsible for evidence selection, compression policy, and audit artifacts.
- Artifacts are persisted and indexed; runtime output should flow through the same structured ingress regardless of internal or external execution.

### Runtime State That Is Now Real

- Ticket lifecycle, review and board commands, incident and breaker governance, retry escalation, and structured result submission are implemented in the backend slice.
- External worker handoff is real: bootstrap token -> refreshable session -> signed delivery grants -> execution, artifact, and command URLs.
- Delivery grants can be listed and revoked from the local worker auth CLI.
- Scope binding now exists across workflow, ticket, worker bootstrap and session, delivery grants, and compiled execution package metadata.
- One worker can now keep multiple bootstrap bindings keyed by `worker_id + tenant_id + workspace_id`; each session and delivery grant still stays bound to exactly one scope.
- Worker bootstrap issuance is now also persisted as `worker_bootstrap_issue`, so newer bootstrap tokens carry `issue_id` and may be invalidated conservatively without changing the compatibility path for older tokens.
- Trusted control-plane operators now also have a minimal `worker-admin` HTTP surface for binding and bootstrap management; CLI and HTTP reuse the same scope and issuance rules.
- Output schema enforcement is currently real for `ui_milestone_review@1` and `consensus_document@1`.

### Durable Open Gaps

- There is still no dedicated tenant-management control plane, OAuth or mTLS layer, or broader public-internet hardening.
- Multipart or large-file upload and object-storage delivery are still missing.
- Artifact cleanup scheduling and richer retention classes still need follow-through.
- Provider routing, richer output schema coverage, and fuller Context Compiler retrieval and caching are still incomplete.

## Recent Memory

### 2026-03-29

- Landed conservative recovery governance for timeout incidents: operator-triggered restore closes the breaker and incident, reopens dispatch honestly, and surfaces close events in projections.
- Landed a controlled timeout follow-up retry path on incident resolve, reusing existing timeout retry policy rather than inventing a separate retry system.

### 2026-03-30

- Converged internal runtime success onto `ticket-result-submit`, so schema validation and write-set validation now go through one structured ingress.
- Added provider pause and resume governance plus related projection and reporting surface.
- Made artifact persistence, artifact index, and worker-facing artifact routes real enough for external delivery.
- Brought external worker runtime handoff online: assignments, compiled execution package delivery, artifact access, and signed worker command endpoints.
- Hardened delivery grants and worker auth with persisted per-URL grants, session-linked revocation, and CLI support for listing and revoking grants.
- Added tenant and workspace binding across the worker runtime chain and surfaced scope in assignments and execution-package responses.
- Extended worker bootstrap state from single-binding to multi-binding, so one worker can now hold multiple tenant/workspace scopes without mixing sessions or delivery grants across them.
- Added `list-bindings` plus explicit-scope CLI safeguards for multi-binding workers, and kept assignment polling strict: known alternate bindings are filtered by scope, while unknown dirty scopes still reject and audit.
- Added explicit `create-binding`, enriched `list-bindings`, and `cleanup-bindings`, so local operators can now manage multi-scope worker bindings as lifecycle state instead of only minting tokens.
- Added `GET /api/v1/projections/worker-runtime`, which aligns binding, session, delivery-grant, and auth-rejection reads under one worker/scope filter instead of requiring multiple local CLI calls.
- Tightened bootstrap issuance governance with persisted `worker_bootstrap_issue` records, `issue_id` claims on new bootstrap tokens, runtime validation for new tokens, and CLI-side default TTL / max TTL / optional tenant allowlist policy.
- The most recent archived full-suite verification claim was `backend/tests -q` -> `163 passed`.

### 2026-03-31

- Added a shared worker admin service under the backend, so CLI and HTTP management no longer duplicate binding / bootstrap lifecycle rules.
- Added `GET /api/v1/worker-admin/bindings`, `GET /api/v1/worker-admin/bootstrap-issues`, and the matching create / issue / revoke / cleanup POST routes, closing the minimal HTTP management loop for worker tenant operations.
- Kept `worker-runtime` projections as the unified read surface and left session / delivery-grant revoke in CLI for now, rather than widening the HTTP management scope all at once.
- Fresh full-suite verification is now `backend/tests -q` -> `186 passed`.

### Current Watch-Outs

- Latest commit review found a legacy-database migration risk: old rows in `workflow_projection`, `ticket_projection`, `worker_bootstrap_state`, `worker_session`, and `worker_delivery_grant` can keep `NULL` scope fields after upgrade because the migration adds columns but does not backfill existing rows.
- Latest commit also continued the append-only `memory-log.md` pattern. Before archival, this file had grown to about `2300` lines, `119 KB`, and `14.9k` words.
- There is no backend runtime path that automatically loads `doc/history/memory-log.md`; the pressure came from human or agent workflow repeatedly opening the history file as working memory.

## Current Working Set

- Prefer reading `README.md`, `doc/README.md`, and `doc/TODO.md` before touching the archive.
- Treat this file as semantic memory plus recent episodic memory, not a full transcript.
- When adding new memory, update stable bullets or the recent section; move raw logs, exhaustive verification output, and long file inventories to the archive.

## Archive Index

- `doc/history/archive/memory-log-detailed-2026-03-27_to_2026-03-30.md`: raw session-by-session history that used to live in this file before archival on 2026-03-30.
