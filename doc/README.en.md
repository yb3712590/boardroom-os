# Boardroom OS

> Event-sourced agent governance for autonomous software delivery.

English overview. 中文首页见 [../README.md](../README.md)

Boardroom OS is not meant to be a multi-agent group chat wrapper. It is a governed delivery control plane where:

- the user acts as the Board
- a CEO agent keeps execution moving
- workers execute atomic tickets without hidden long-lived state
- important milestones go through explicit approval gates
- events and projections remain the source of truth

## Current Status

This repository now contains design documents plus a runnable backend slice in `backend/`.

What is already real:

- FastAPI command, projection, and SSE event-stream endpoints
- SQLite control-plane storage with WAL
- ticket create / lease / start / heartbeat / result-submit / cancel flows
- minimal incident, circuit-breaker, retry, and recovery governance
- review room plus board approve / reject / modify-constraints commands
- independent scheduler runner and optional in-process scheduler loop
- a minimal artifact store and artifact index for `JSON` / `TEXT` / `MARKDOWN` plus image / PDF / other medium-sized binary ticket outputs
- a ticket artifacts projection plus strict output-schema validation for `ui_milestone_review@1` and `consensus_document@1`
- artifact metadata / content / preview endpoints keyed by `artifact_ref`
- artifact lifecycle commands for delete and cleanup
- an external worker handoff surface where workers bootstrap with per-worker tokens, refresh per-worker sessions, and then continue through short-lived signed URLs under `/api/v1/worker-runtime/*`, now backed by persisted per-URL delivery grants plus worker-side multi-binding `tenant_id/workspace_id` scope state

## Quick Start

```bash
cd backend
source .venv/bin/activate
uvicorn app.main:app --reload
```

Enable the in-process scheduler loop explicitly:

```bash
cd backend
source .venv/bin/activate
BOARDROOM_OS_ENABLE_INPROCESS_SCHEDULER=true uvicorn app.main:app --reload
```

Switch into external-worker handoff mode:

```bash
cd backend
source .venv/bin/activate
BOARDROOM_OS_RUNTIME_EXECUTION_MODE=EXTERNAL \
BOARDROOM_OS_WORKER_BOOTSTRAP_SIGNING_SECRET=bootstrap-signing-secret \
BOARDROOM_OS_WORKER_DELIVERY_SIGNING_SECRET=delivery-signing-secret \
BOARDROOM_OS_PUBLIC_BASE_URL=http://127.0.0.1:8000 \
uvicorn app.main:app --reload
```

Issue a bootstrap token for one worker:

```bash
cd backend
source .venv/bin/activate
python -m app.worker_auth_cli issue-bootstrap --worker-id emp_frontend_2
python -m app.worker_auth_cli list-bindings --worker-id emp_frontend_2
python -m app.worker_auth_cli list-delivery-grants --worker-id emp_frontend_2
python -m app.worker_auth_cli list-sessions --worker-id emp_frontend_2
python -m app.worker_auth_cli list-auth-rejections --worker-id emp_frontend_2
python -m app.worker_auth_cli revoke-delivery-grant --grant-id <grant_id>
```

Run the standalone scheduler runner:

```bash
cd backend
source .venv/bin/activate
python -m app.scheduler_runner
```

Mode notes:

- `BOARDROOM_OS_RUNTIME_EXECUTION_MODE=INPROCESS` remains the default, and the runner / in-process scheduler still executes leased tickets locally.
- `BOARDROOM_OS_RUNTIME_EXECUTION_MODE=EXTERNAL` keeps scheduling and leasing, but stops automatic local `start / execute / result-submit`.
- Recommended bootstrap flow: issue a worker-specific bootstrap token with `python -m app.worker_auth_cli issue-bootstrap --worker-id <employee_id>`, then call `GET /api/v1/worker-runtime/assignments` with `X-Boardroom-Worker-Bootstrap`.
- Worker bootstrap state is now keyed by `worker_id + tenant_id + workspace_id`, so one worker may keep multiple bindings at once; sessions and delivery grants still stay bound to exactly one scope.
- When a worker already has multiple bindings, `issue-bootstrap`, `rotate-bootstrap`, and `revoke-bootstrap` must receive both `--tenant-id` and `--workspace-id`; single-binding workers still keep the old convenience behavior.
- The assignments response now also returns `tenant_id`, `workspace_id`, `session_id`, `session_token`, and `session_expires_at`; workers can keep polling assignments with `X-Boardroom-Worker-Session` and receive a refreshed session token plus a fresh batch of delivery URLs.
- Assignment polling now returns only tickets for the current session scope; if the backend finds a ticket owned by that worker under an unknown scope with no matching bootstrap binding, it still rejects and logs the mismatch instead of silently hiding it.
- The returned execution-package URLs, artifact URLs, and worker command URLs all carry short-lived `access_token` query parameters and are now backed by persisted delivery grants.
- Delivered execution-package payloads now also expose `tenant_id` and `workspace_id`, while backend authorization still treats persisted worker/session/grant/ticket state as the source of truth.
- Those signed delivery URLs are claim-bound, session-bound, grant-bound, and ticket/workflow-scope-bound, so revoking one worker session invalidates that session's URLs, one specific URL can be revoked independently through the local CLI, and cross-tenant or cross-workspace mismatches are rejected instead of being silently filtered around.
- `/api/v1/worker-runtime/tickets/*`, `/api/v1/worker-runtime/artifacts/*`, and `/api/v1/worker-runtime/commands/*` no longer accept the old shared-secret request fallback.
- Local operators can inspect and revoke delivery grants through `python -m app.worker_auth_cli list-delivery-grants`, inspect active sessions through `python -m app.worker_auth_cli list-sessions`, and inspect worker auth rejection audit rows through `python -m app.worker_auth_cli list-auth-rejections`.
- `BOARDROOM_OS_WORKER_BOOTSTRAP_SIGNING_SECRET` signs bootstrap tokens and falls back to `BOARDROOM_OS_WORKER_SHARED_SECRET` when omitted.
- `BOARDROOM_OS_WORKER_SESSION_TTL_SEC` defaults to `86400` and controls assignment-session refresh windows.
- `BOARDROOM_OS_PUBLIC_BASE_URL` rewrites those delivery URLs for remotely reachable workers; if omitted, the backend falls back to the incoming request base URL.
- `BOARDROOM_OS_WORKER_DELIVERY_TOKEN_TTL_SEC` defaults to `3600`, and `BOARDROOM_OS_WORKER_DELIVERY_SIGNING_SECRET` falls back to `BOARDROOM_OS_WORKER_SHARED_SECRET` when not set.

Run tests:

```bash
cd backend
source .venv/bin/activate
python -m pytest tests -q
```

Default storage roots:

- `backend/data/boardroom_os.db`
- `backend/data/artifacts/` (override with `BOARDROOM_OS_ARTIFACT_STORE_ROOT`)

Known realities:

- `pip install -e .[dev]` may still fail in a fresh environment because of the current flat backend packaging layout.
- Binary uploads currently go through inline base64 in `ticket-result-submit`; there is no multipart, chunked-upload, or object-storage path yet.
- External worker handoff now supports worker-side multi-binding `tenant_id/workspace_id` scope state across workflow, ticket, bootstrap state, session, and delivery grant, plus four-layer runtime validation and persisted auth-rejection audit rows.
- Broader multi-tenant administration is still not implemented: workers can now hold multiple bindings, but dedicated tenant-management flows and stronger public-internet hardening beyond the current token/session/grant/ticket-scope checks remain open work.

## Docs

- [README.md](README.md): docs index
- [TODO.md](TODO.md): current open work distilled from README, design docs, and recent history
- [feature-spec.md](feature-spec.md): product and governance rule set
- [design/message-bus-design.md](design/message-bus-design.md): event bus and control-plane design
- [design/context-compiler-design.md](design/context-compiler-design.md): context compiler design
- [design/meeting-room-protocol.md](design/meeting-room-protocol.md): meeting room protocol
- [design/boardroom-ui-design.md](design/boardroom-ui-design.md): UI design
- [design/boardroom-data-contracts.md](design/boardroom-data-contracts.md): UI-facing data contracts
- [history/memory-log.md](history/memory-log.md): historical iteration log
