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
- Output schema enforcement is currently real on the active local MVP runtime paths, including `ui_milestone_review@1` and `maker_checker_verdict@1`.

### Durable Open Gaps

- There is still no dedicated tenant-management control plane, OAuth or mTLS layer, or broader public-internet hardening.
- Control-plane multipart upload and optional object-store delivery now exist, but browser direct upload, worker-runtime upload, and cloud presigned multipart remain post-MVP.
- The current large-input / binary handling is now closed for the local MVP read path, but broader artifact platformization and public-network delivery policy are still intentionally frozen.
- Provider routing, richer output schema coverage, and fuller Context Compiler retrieval and caching beyond the current local MVP path are still incomplete.

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

- Closed the shortest-path Maker-Checker gap for visual milestones: `ui_milestone_review@1` results with `VISUAL_MILESTONE` review now route through an auto-created checker ticket before any board approval opens.
- Added `maker_checker_verdict@1` as a real structured output contract, and taught the minimal in-process runtime to execute checker tickets with a deterministic `APPROVED_WITH_NOTES` verdict.
- Checker pass / escalate now opens the existing `Inbox -> Review Room` path with backend-generated `maker_checker_summary`; `CHANGES_REQUIRED` now creates a follow-up fix ticket instead of sending manual feedback through the board path.
- Tightened visual-milestone rework governance: `CHANGES_REQUIRED` now derives a stable blocking-finding fingerprint, writes `required_fixes` / `rework_fingerprint` / `rework_streak_count` into fix-ticket context, and appends explicit close-the-finding acceptance criteria.
- Repeated identical blocking findings in the visual Maker-Checker loop no longer create unbounded fix tickets: once the existing repeat-failure threshold is hit, backend now opens a dedicated `MAKER_CHECKER_REWORK_ESCALATION` incident plus circuit breaker and surfaces that path through inbox copy instead of mislabeling it as a generic runtime failure.
- The current limitation is explicit: this loop only covers the visual-milestone path for now, and employee lifecycle / richer checker routing are still open.
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
- Closed the next public-entry gap inside that trusted control plane: when `BOARDROOM_OS_WORKER_ADMIN_TRUSTED_PROXY_IDS` is configured, `worker-admin`, `worker-admin-audit`, and `worker-admin-auth-rejections` now all require `X-Boardroom-Trusted-Proxy-Id` before token validation, so the control plane can be pinned behind one expected reverse proxy hop instead of trusting any direct caller with a valid token.
- Extended both worker-admin logs with ingress context: `worker_admin_action_log` and `worker_admin_auth_rejection_log` now persist `trusted_proxy_id` and `source_ip`, and the two projection surfaces expose those fields directly for operator-side debugging.
- Fresh focused verification after this change is:
  - `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_api.py -k "trusted_proxy or worker_admin_audit_projection_exposes_trusted_proxy_context" backend/tests/test_repository.py -k "trusted_proxy or worker_admin_action_log_round_trips_filters_and_details or worker_admin_auth_rejection_log_round_trips_filters or legacy_tables" -q` -> `7 passed`
  - `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_worker_admin_auth_cli.py -q` -> `4 passed`
  - `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_repository.py -q` -> `11 passed`
  - `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_api.py -k "worker_admin" -q` -> `37 passed, 130 deselected`
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
- Extended artifact retention from rough long-lived vs temporary handling into a first scenario-based split: `PERSISTENT` still stays non-expiring by default, `REVIEW_EVIDENCE` now defaults to `BOARDROOM_OS_ARTIFACT_REVIEW_EVIDENCE_DEFAULT_TTL_SEC`, and `EPHEMERAL` keeps `BOARDROOM_OS_ARTIFACT_EPHEMERAL_DEFAULT_TTL_SEC`.
- Runtime-generated default review option artifacts now explicitly land as `REVIEW_EVIDENCE`, so the minimal in-process runtime no longer leaves Board-facing review materials looking like generic persistent blobs.
- Repository initialization now also backfills legacy `REVIEW_EVIDENCE` rows without `expires_at`, and `GET /api/v1/projections/dashboard` now exposes a `retention_defaults` map alongside the existing cleanup summary.
- Fresh focused verification after this change is:
  - `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_api.py -k "retention or artifact_cleanup or runtime_default_result_artifacts_use_review_evidence_retention" -q` -> `6 passed, 157 deselected`
  - `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_repository.py -k "artifact_retention or artifact_cleanup or review_evidence_artifact_retention" -q` -> `3 passed, 7 deselected`
  - `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_scheduler_runner.py -k "artifact_cleanup or dispatches_using_persisted_roster" -q` -> `2 passed, 10 deselected`
- Continued artifact retention governance into conservative scenario defaults: when callers omit `retention_class`, backend now derives it from path with `reports/review/* -> REVIEW_EVIDENCE`, `reports/ops/* -> OPERATIONAL_EVIDENCE`, `reports/diagnostics/* -> OPERATIONAL_EVIDENCE`, and all other paths staying `PERSISTENT`.
- Added `OPERATIONAL_EVIDENCE` as a first built-in class for ops and diagnostic materials, with `BOARDROOM_OS_ARTIFACT_OPERATIONAL_EVIDENCE_DEFAULT_TTL_SEC` defaulting to 14 days.
- Persisted `retention_class_source` on `artifact_index` and surfaced it through ticket artifact and cleanup-candidate projections, so operators can now distinguish explicit retention from path-derived defaults and `LEGACY_COMPAT` backfill state directly from one read surface.
- Fresh focused verification after this change is:
  - `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_api.py -k "review_evidence_default_ttl or operational_evidence or explicit_retention_class_overrides_path_default or dashboard_and_cleanup_candidates_expose_retention_policy_state" -q` -> `3 passed, 166 deselected`
  - `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_api.py -k "retention or artifact_cleanup or runtime_default_result_artifacts_use_review_evidence_retention" -q` -> `7 passed, 162 deselected`
  - `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_repository.py -k "artifact_retention or artifact_cleanup or review_evidence_artifact_retention or retention_class_source" -q` -> `4 passed, 8 deselected`
  - `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_scheduler_runner.py -k "artifact_cleanup or runtime_default" -q` -> `1 passed, 11 deselected`
- Extended artifact storage from local-file only into a local-default / optional object-store abstraction. `artifact_index` now also persists `storage_backend`, `storage_object_key`, `storage_delete_status`, and `storage_delete_error`, while old rows backfill conservatively during repository initialization.
- Added control-plane multipart upload state under `artifact_upload_session` + `artifact_upload_part`, plus `POST /api/v1/artifact-uploads/sessions`, `PUT /parts/{part_number}`, `POST /complete`, and `POST /abort`, so medium and large binary artifacts can be uploaded first and then consumed through `ticket-result-submit` via `upload_session_id`.
- Kept artifact governance on one path: `ticket-result-submit` still owns retention-class resolution, expiry calculation, artifact indexing, and audit semantics; upload sessions only prepare the binary body.
- Extended artifact delete and cleanup from “delete local file” into “delete by storage backend and write back storage outcome”. Cleanup and ticket artifact projections now expose `storage_backend` / `storage_delete_status`, and dashboard maintenance now also shows `delete_failed_count`.
- Fresh focused verification after this change is:
  - `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_api.py -k "artifact or retention or cleanup or object_store" -q` -> `25 passed, 147 deselected`
  - `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_repository.py -k "artifact" -q` -> `5 passed, 9 deselected`
  - `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_scheduler_runner.py -k "artifact_cleanup" -q` -> `1 passed, 11 deselected`
  - `backend\.venv\Scripts\python.exe -m pytest backend/tests -q` -> `243 passed`

### 2026-04-01

- Synced `doc/roadmap-reset.md` with the new documentation baseline by adding explicit anti-drift execution constraints, so future development rounds must read the roadmap reset early, stay on one mainline direction, and stop scope growth once a side path no longer shortens the local `Board -> Review` MVP chain.
- Added a ready-to-copy reset prompt to `doc/roadmap-reset.md`, updating the fixed reading order to include the roadmap decision itself before `doc/TODO.md` and `doc/history/memory-log.md`, and removing outdated default expansion toward `Search / Retrieval` or other post-MVP infrastructure directions.
- Moved the Context Compiler past the earlier pure reference-only state for local execution: active materialized `TEXT / MARKDOWN / JSON` input artifacts now inline directly into the compiled execution package, while unreadable or over-budget sources fall back to descriptor form with explicit compile-manifest reasons.
- Extended compile audit output so the manifest now records why a source stayed descriptor-only, distinguishes hydrated vs reference blocks in final bundle stats, and keeps the signed artifact URL path available even for inlined sources.
- Continued the Context Compiler along the local MVP path instead of widening governance scope: compile requests, context blocks, and manifest source logs now carry stable degradation reason codes such as `ARTIFACT_NOT_INDEXED`, `ARTIFACT_NOT_READABLE`, `UNSUPPORTED_ARTIFACT_KIND`, and `INLINE_BUDGET_EXCEEDED`.
- Large-but-readable local `TEXT / MARKDOWN / JSON` inputs no longer collapse straight to pure descriptor form when full hydration would overflow the rough token budget. The compiler now emits deterministic head previews for text and top-level previews for JSON, while keeping artifact access URLs and marking the block as partial inline hydration.
- `GET /api/v1/projections/review-room/{review_pack_id}/developer-inspector` now adds a compact `compile_summary`, so debugging a blocked review no longer starts with manually reading raw manifest JSON just to answer “how many sources degraded, and why?”.
- Continued the Context Compiler from “explicit inputs only” into a first real local knowledge path: compile requests now materialize a deterministic `retrieval_plan`, and compilation can pull in same-workspace, cross-workflow `review / incident / artifact` history as structured summary cards instead of leaving `keywords / semantic_queries` unused.
- Kept that new retrieval path inside the local MVP boundary: no vector store, no web search, no external knowledge service; `semantic_queries` are normalized into deterministic local match terms, and artifact retrieval still prefers compact summary cards over raw historical bodies.
- Compile manifests and Review Room developer-inspector summaries now expose retrieval counts by channel plus budget-driven retrieval drops, so排障时可以直接看到“本轮编译带进来了哪些历史经验，哪些因为预算被丢掉了”，不用再手翻完整 manifest。
- Continued the Context Compiler along the same local-execution path instead of widening into provider routing: `IMAGE / PDF` inputs now stay in compiled execution packages as structured media references with explicit `kind` and `preview_kind=INLINE_MEDIA`, while other binary inputs stay as structured download references with `preview_kind=DOWNLOAD_ONLY`.
- Replaced the earlier catch-all binary fallback in current compiler behavior with more honest degradation codes: review/debug surfaces now distinguish `MEDIA_REFERENCE_ONLY` from `BINARY_REFERENCE_ONLY` instead of reporting both as one vague `UNSUPPORTED_ARTIFACT_KIND`.
- Worker-facing execution packages keep those new `artifact_access.kind / preview_kind` hints after signed URL rewriting, so downstream workers no longer need to guess whether an input should be previewed inline or handled as a download-only attachment.
- Continued the Context Compiler on the same mainline by adding deterministic fragment compilation for oversized `TEXT / MARKDOWN / JSON` inputs: the compiler now prefers `MARKDOWN_SECTION`, `TEXT_WINDOW`, and `JSON_PATH` slices before falling back to the older partial-preview path.
- Worker-facing atomic context blocks now carry the same selector metadata as the compiled bundle, so runtime packages and Review Room debugging no longer disagree about which fragment the worker actually received.
- `GET /api/v1/projections/review-room/{review_pack_id}/developer-inspector` compile summaries now count `inline_fragment_count`, making it visible when a run was neither full-inline nor plain preview-only.
- Closed the current Context Compiler budget-truth gap on the local MVP path: explicit inputs now reserve the minimum descriptor budget required by later mandatory sources, so earlier large sources can no longer consume the whole ticket budget and leave later mandatory inputs with no legal compile form.
- Tightened the fallback chain itself into a real strict gate: the compiler now only keeps `INLINE_PARTIAL` or `REFERENCE_ONLY` blocks if they individually fit the remaining budget, and if a mandatory source cannot fit even as a descriptor the compile now fails closed instead of emitting an over-budget execution package.
- Compile manifests now write real budget accounting instead of placeholder totals: `budget_plan` reserves retrieval space only when retrieval is present, `budget_actual.truncated_tokens` now reflects actual tokens removed by fragment/preview/descriptor fallback and dropped retrieval, and final bundle stats now record `dropped_explicit_source_count` alongside retrieval drops.
- `GET /api/v1/projections/review-room/{review_pack_id}/developer-inspector` now surfaces compile-budget pressure directly with `total_budget_tokens`, `used_budget_tokens`, `remaining_budget_tokens`, `truncated_tokens`, and `dropped_explicit_source_count`, so operators can see whether a run barely fit without opening raw manifest JSON.
- Fresh focused verification after this change is:
  - `D:\projects\boardroom-os\backend\.venv\Scripts\python.exe -m pytest backend/tests/test_context_compiler.py -q` -> `22 passed`
  - `D:\projects\boardroom-os\backend\.venv\Scripts\python.exe -m pytest backend/tests/test_api.py -k "review_room_developer_inspector or worker_runtime_execution_package" -q` -> `10 passed, 171 deselected`
  - `D:\projects\boardroom-os\backend\.venv\Scripts\python.exe -m pytest backend/tests/test_scheduler_runner.py -k "mandatory_source_descriptor_exceeds_budget" -q` -> `1 passed, 13 deselected`
  - `D:\projects\boardroom-os\backend\.venv\Scripts\python.exe -m pytest backend/tests/test_scheduler_runner.py -k "runtime" -q` -> `1 passed, 13 deselected`
- Fresh focused verification after this change is:
  - `cd backend && source .venv/bin/activate && python -m pytest tests/test_context_compiler.py -q` -> `10 passed`
  - `cd backend && source .venv/bin/activate && python -m pytest tests/test_api.py -k "review_room_developer_inspector" -q` -> `3 passed, 174 deselected`
  - `cd backend && source .venv/bin/activate && python -m pytest tests/test_context_compiler.py -q` -> `13 passed`
  - `cd backend && source .venv/bin/activate && python -m pytest tests/test_api.py -k "review_room_developer_inspector or worker_runtime_execution_package" -q` -> `6 passed, 171 deselected`
  - `cd backend && source .venv/bin/activate && python -m pytest tests/test_worker_auth_cli.py -q` -> `15 passed`
- Continued the Context Compiler on the same mainline by adding a first real render layer on top of the existing bundle truth: each compile now also emits a deterministic `json_messages_v1` rendered execution payload instead of leaving downstream workers and operators to reconstruct final input order from raw context blocks.
- Kept the boundary conservative: `atomic_context_bundle` remains the source of truth, while the new rendered payload is a pure derived view with fixed channel order `SYSTEM_CONTROLS -> TASK_DEFINITION -> CONTEXT_BLOCK -> OUTPUT_CONTRACT_REMINDER`.
- Extended worker delivery and Review Room inspection together, so `GET /api/v1/worker-runtime/tickets/{ticket_id}/execution-package` and `GET /api/v1/projections/review-room/{review_pack_id}/developer-inspector` now surface the same rendered payload plus compact render-summary counts.
- Extended developer-inspector refs with `render://`, and developer-inspector availability now treats bundle / manifest / rendered payload as one consistent set instead of marking a fully materialized three-artifact export as only partial.
- Fresh focused verification after this change is:
  - `D:\projects\boardroom-os\backend\.venv\Scripts\python.exe -m pytest backend/tests/test_context_compiler.py -q` -> `25 passed`
  - `D:\projects\boardroom-os\backend\.venv\Scripts\python.exe -m pytest backend/tests/test_api.py -k "worker_runtime_execution_package or review_room_developer_inspector" -q` -> `12 passed, 171 deselected`
- Closed the local-MVP provider gap without widening into platformization: in-process runtime now recognizes `provider_id=prov_openai_compat`, calls OpenAI-compatible `POST {base_url}/responses` when the compat env vars are present, and otherwise keeps the zero-config deterministic runtime fallback intact.
- Kept provider failure governance conservative: `429` maps to `PROVIDER_RATE_LIMITED`, timeout / transport / `5xx` map to `UPSTREAM_UNAVAILABLE`, `401/403` map to `PROVIDER_AUTH_FAILED`, and malformed / non-JSON / schema-invalid responses map to `PROVIDER_BAD_RESPONSE`; only rate-limit and upstream-unavailable failures open the existing provider pause / incident path.
- Closed the current local MVP display-semantics gap for large inputs and binary references: context blocks and worker execution packages now carry explicit `display_hint`, while Review Room compile summaries now also count media references, download-only attachments, fragment strategies, preview strategies, and `preview_kind` totals.
- Synced artifact metadata contracts with that new display truth, so both control-plane and worker-scoped artifact read APIs now expose `display_hint` instead of silently dropping it at the response boundary.
- Fresh verification after this change is:
  - `D:\projects\boardroom-os\backend\.venv\Scripts\python.exe -m pytest backend/tests/test_provider_openai_compat.py -q` -> `5 passed`
  - `D:\projects\boardroom-os\backend\.venv\Scripts\python.exe -m pytest backend/tests/test_context_compiler.py -q` -> `25 passed`
  - `D:\projects\boardroom-os\backend\.venv\Scripts\python.exe -m pytest backend/tests/test_scheduler_runner.py -q` -> `18 passed`
  - `D:\projects\boardroom-os\backend\.venv\Scripts\python.exe -m pytest backend/tests/test_api.py -k "review_room_developer_inspector or worker_runtime_execution_package or provider" -q` -> `16 passed, 168 deselected`
  - `D:\projects\boardroom-os\backend\.venv\Scripts\python.exe -m pytest backend/tests/test_api.py -k "artifact" -q` -> `22 passed, 162 deselected`
  - `D:\projects\boardroom-os\backend\.venv\Scripts\python.exe -m pytest backend/tests -q` -> `288 passed`
- No compatible live provider credentials were present in the environment during this round, so the new provider path is code-complete and mock/full-suite verified, but not yet stamped with a real remote smoke run.

### Current Watch-Outs

- Latest commit also continued the append-only `memory-log.md` pattern. Before archival, this file had grown to about `2300` lines, `119 KB`, and `14.9k` words.
- There is no backend runtime path that automatically loads `doc/history/memory-log.md`; the pressure came from human or agent workflow repeatedly opening the history file as working memory.

## Current Working Set

- Prefer reading `README.md`, `doc/README.md`, and `doc/TODO.md` before touching the archive.
- Treat this file as semantic memory plus recent episodic memory, not a full transcript.
- When adding new memory, update stable bullets or the recent section; move raw logs, exhaustive verification output, and long file inventories to the archive.

## Archive Index

- `doc/history/archive/memory-log-detailed-2026-03-27_to_2026-03-30.md`: raw session-by-session history that used to live in this file before archival on 2026-03-30.
