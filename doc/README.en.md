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
- an external worker handoff surface where bootstrap still uses a shared secret, but delivery now continues through short-lived signed URLs under `/api/v1/worker-runtime/*`

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
BOARDROOM_OS_WORKER_SHARED_SECRET=change-me \
BOARDROOM_OS_PUBLIC_BASE_URL=http://127.0.0.1:8000 \
uvicorn app.main:app --reload
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
- External workers first bootstrap with `X-Boardroom-Worker-Key` and `X-Boardroom-Worker-Id` on `GET /api/v1/worker-runtime/assignments`.
- The returned execution-package URLs, artifact URLs, and worker command URLs all carry short-lived `access_token` query parameters and can be called without repeating the shared-secret headers.
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
- External worker handoff now uses a deployment-level shared-secret bootstrap plus per-ticket short-lived signed delivery URLs, but stronger multi-tenant isolation, independent token revocation / rotation, and more hardened public-internet delivery boundaries are still not implemented.

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
