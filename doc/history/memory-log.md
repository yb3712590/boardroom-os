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
- Delivery grants can now be revoked from both the local worker auth CLI and the trusted `worker-admin` HTTP surface.
- Scope binding now exists across workflow, ticket, worker bootstrap and session, delivery grants, and compiled execution package metadata.
- One worker can now keep multiple bootstrap bindings keyed by `worker_id + tenant_id + workspace_id`; each session and delivery grant still stays bound to exactly one scope.
- Worker bootstrap issuance is now also persisted as `worker_bootstrap_issue`, so newer bootstrap tokens carry `issue_id` and may be invalidated conservatively without changing the compatibility path for older tokens.
- Trusted control-plane operators now also have a `worker-admin` HTTP surface for binding, bootstrap, session, and delivery-grant management; the HTTP side now requires signed operator tokens instead of trusting raw operator headers, and it also exposes a dedicated action-audit projection.
- Output schema enforcement is currently real for `ui_milestone_review@1` and `consensus_document@1`.

### Durable Open Gaps

- There is still no dedicated tenant-management control plane, OAuth or mTLS layer, or broader public-internet hardening.
- Multipart or large-file upload and object-storage delivery are still missing.
- Richer artifact retention classes and the larger-file upload path still need follow-through beyond the current local-store auto cleanup loop.
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
- Extended `worker-admin` with `revoke-session` and `revoke-delivery-grant`, so tenant incident handling can now stay in one control-plane entrypoint instead of bouncing back to local CLI.
- Added persisted revoke audit fields on worker sessions and delivery grants, and surfaced them back through `GET /api/v1/projections/worker-runtime` for direct post-action verification.
- Extended `worker-admin` again with `GET /api/v1/worker-admin/sessions`, `delivery-grants`, `auth-rejections`, and `scope-summary`, so operators can now inspect one tenant/workspace scope directly instead of pivoting through one worker at a time.
- Added `POST /api/v1/worker-admin/contain-scope`, which supports dry-run impact preview first and then real scope containment with `expected_active_*` count checks; the write path now stamps `revoked_via = worker_admin_scope_containment` for batch stop-the-bleeding actions.
- Closed the earlier legacy scope-backfill risk in current code: repository initialization now backfills default `tenant_id/workspace_id` values for old projection, bootstrap, session, and delivery-grant rows, and the repository test suite covers that upgrade path.
- Added a minimal operator boundary on `worker-admin`: every HTTP request now requires operator headers, `platform_admin` keeps global read/write, `scope_admin` is limited to one exact tenant/workspace scope, and `scope_viewer` is read-only inside one exact scope.
- Moved HTTP-side `issued_by` / `revoked_by` truth to the operator headers. Request-body fields with those names are now only compatibility assertions; if they disagree with `X-Boardroom-Operator-Id`, the backend returns `400` instead of silently trusting the body.
- Tightened the `worker-admin` entry boundary again: HTTP requests now require `X-Boardroom-Operator-Token`, backend validates a short-lived signed operator token against `BOARDROOM_OS_WORKER_ADMIN_SIGNING_SECRET`, and the old `X-Boardroom-Operator-*` headers are now only optional compatibility assertions.
- Added `python -m app.worker_admin_auth_cli issue-token`, so local operators can mint scoped `platform_admin` / `scope_admin` / `scope_viewer` tokens for real `worker-admin` calls instead of hand-crafting trusted headers.
- Added persisted `worker_admin_action_log` plus `GET /api/v1/projections/worker-admin-audit`, so operators can now read an independent audit stream of `create-binding`, `issue-bootstrap`, `revoke-*`, `cleanup-bindings`, and `contain-scope` actions, including dry-run previews.
- Fresh focused verification after this change is:
  - `backend/.venv/bin/python -m pytest backend/tests/test_worker_admin_auth_cli.py -q` -> `1 passed`
  - `backend/.venv/bin/python -m pytest backend/tests/test_repository.py -k "worker_admin_action_log" -q` -> `1 passed`
  - `backend/.venv/bin/python -m pytest backend/tests/test_api.py -k "legacy_headers_without_signed_token or mismatched_assertion_headers_against_signed_token or audit_projection" -q` -> `4 passed`
  - `backend/.venv/bin/python -m pytest backend/tests/test_api.py -k "worker_admin or worker_runtime_projection" -q` -> `30 passed`
- Fresh focused verification after this change is:
  - `source backend/.venv/bin/activate && cd backend && python -m pytest tests/test_api.py -k "worker_admin" -q` -> `23 passed`
  - `source backend/.venv/bin/activate && cd backend && python -m pytest tests/test_api.py -k "worker_admin or worker_runtime_projection" -q` -> `26 passed`
  - `source backend/.venv/bin/activate && cd backend && python -m pytest tests/test_worker_auth_cli.py -q` -> `15 passed`
  - `source backend/.venv/bin/activate && cd backend && python -m pytest tests/test_repository.py -q` -> `4 passed`
- Closed the remaining `worker-admin` operator-token governance gap inside the trusted control plane: `issue-token` now persists `worker_admin_token_issue`, new operator tokens carry a durable `token_id`, and backend validation for new tokens now checks persisted issue state instead of trusting signature + TTL alone.
- Added operator-token management surfaces on both paths: `python -m app.worker_admin_auth_cli list-tokens` / `revoke-token`, plus `GET /api/v1/worker-admin/operator-tokens` and `POST /api/v1/worker-admin/revoke-operator-token`, with the same platform-vs-scope role boundaries on listing and revoke.
- Added a dedicated `worker_admin_auth_rejection_log` and `GET /api/v1/projections/worker-admin-auth-rejections`, so post-revoke verification no longer depends on manual `401` spot checks; operators can now see missing-token, bad-signature, expired, revoked, assertion-mismatch, and scope-denied failures directly.
- Fresh focused verification after this change is:
  - `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_worker_admin_auth_cli.py -q` -> `4 passed`
  - `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_repository.py -q` -> `7 passed`
  - `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_api.py -k "worker_admin" -q` -> `33 passed, 123 deselected`
- Closed the manual-only artifact cleanup gap for the current local artifact store: `artifact_index` now persists `storage_deleted_at`, cleanup no longer re-counts already-cleared files, and scheduler / runner now trigger automatic cleanup on a bounded interval.
- Extended `GET /api/v1/projections/dashboard` with `artifact_maintenance`, so排障时可以直接看到自动 cleanup 是否开启、当前过期待清理积压、以及最近一次 cleanup 的触发来源、操作者和删除数量。
- Extended `GET /api/v1/projections/tickets/{ticket_id}/artifacts` with `deleted_by`, `delete_reason`, and `storage_deleted_at`, so单张 ticket 的 artifact 读面现在能直接区分“逻辑过期”与“文件已物理删除”。
- Closed the main retention-governance gap in the current artifact path: new `EPHEMERAL` artifacts now default to `BOARDROOM_OS_ARTIFACT_EPHEMERAL_DEFAULT_TTL_SEC` when callers omit `retention_ttl_sec`, and legacy `EPHEMERAL` rows without `expires_at` are backfilled conservatively during repository initialization.
- Added persisted `retention_ttl_sec` and `retention_policy_source` on `artifact_index`, so ticket-level artifact reads now show not only whether an artifact is expired, but also whether that retention came from an explicit TTL, the class default, a legacy backfill, or an unknown older rule.
- Added `GET /api/v1/projections/artifact-cleanup-candidates`, so值守排障时不再只看 dashboard 汇总计数，而是能直接看到当前哪些 artifact 在等过期处理、哪些只差本地文件清理记账。
- Fresh focused verification after this change is:
  - `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_repository.py -k "artifact_cleanup_candidates_ignore_storage_already_deleted_rows" -q` -> `1 passed`
  - `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_api.py -k "artifact_cleanup_does_not_recount_storage_already_cleared or dashboard_exposes_artifact_cleanup_maintenance_summary or ticket_artifacts_projection_exposes_cleanup_audit_fields or artifact_cleanup_expires_elapsed_artifacts_and_deletes_files" -q` -> `4 passed, 155 deselected`
  - `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_scheduler_runner.py -k "auto_runs_artifact_cleanup_once_per_interval_bucket" -q` -> `1 passed, 11 deselected`

### Current Watch-Outs

- Latest commit also continued the append-only `memory-log.md` pattern. Before archival, this file had grown to about `2300` lines, `119 KB`, and `14.9k` words.
- There is no backend runtime path that automatically loads `doc/history/memory-log.md`; the pressure came from human or agent workflow repeatedly opening the history file as working memory.

## Current Working Set

- Prefer reading `README.md`, `doc/README.md`, and `doc/TODO.md` before touching the archive.
- Treat this file as semantic memory plus recent episodic memory, not a full transcript.
- When adding new memory, update stable bullets or the recent section; move raw logs, exhaustive verification output, and long file inventories to the archive.

## Archive Index

- `doc/history/archive/memory-log-detailed-2026-03-27_to_2026-03-30.md`: raw session-by-session history that used to live in this file before archival on 2026-03-30.
