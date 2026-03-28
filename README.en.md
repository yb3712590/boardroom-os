# Boardroom OS

> Event-sourced Agent Governance.

English overview. 涓枃鐗堣瑙?[README.md](README.md)

Boardroom OS is an event-sourced agent governance framework for autonomous software delivery.

It is designed around a simple model:

- the user acts as the Board
- a CEO agent drives execution
- workers execute atomic tickets
- checkers review important outputs
- key milestones go through explicit approval gates
- all state changes remain auditable through events and projections

## Current Code State

This repository is no longer design-only. It now contains **design documents plus the first runnable backend slice**.

Implemented code lives in [backend/](backend/). The current backend slice includes:

- FastAPI app bootstrap
- SQLite control-plane storage with `WAL`
- backend-enforced `SYSTEM_INITIALIZED` idempotency
- `POST /api/v1/commands/project-init`
- `GET /api/v1/projections/dashboard`
- `GET /api/v1/projections/inbox`
- `GET /api/v1/projections/review-room/{review_pack_id}` real projection for persisted approval packs
- `GET /api/v1/events/stream?after={cursor}` SSE stream
- real `CommandAckEnvelope`
- minimal `events`, `workflow_projection`, `ticket_projection`, `node_projection`, `approval_projection`, and `employee_projection` schema
- minimal persisted `compiled_context_bundle` and `compile_manifest` audit tables
- `POST /api/v1/commands/ticket-create` for full control-plane ticket creation
- `POST /api/v1/commands/ticket-lease` for explicit ticket lease acquisition and renewal
- `POST /api/v1/commands/ticket-start` for moving the latest node ticket into execution
- `POST /api/v1/commands/ticket-fail` for explicit worker failure reporting plus minimal retry creation
- `POST /api/v1/commands/ticket-complete` to turn structured ticket results into upstream approval requests
- seeded persisted worker roster for the minimal executor pool
- `POST /api/v1/commands/scheduler-tick` for timeout handling, retry creation, and expired-lease dispatch using persisted roster by default
- dashboard `workforce_summary` backed by real roster and ticket state instead of fixed zeros
- independent scheduler runner via `python -m app.scheduler_runner`
- runner-driven minimal automatic execution chain from `TICKET_LEASED` to `TICKET_STARTED`, then through a minimal `CompileRequest -> CompiledContextBundle / CompileManifest -> CompiledExecutionPackage` compile-and-persist boundary before `TICKET_COMPLETED` or `TICKET_FAILED`
- persisted minimal `CompiledContextBundle` / `CompileManifest` audit artifacts with ticket-level lookup; provenance is still reference-only and does not hydrate artifact bodies yet
- `POST /api/v1/commands/board-approve`
- `POST /api/v1/commands/board-reject`
- `POST /api/v1/commands/modify-constraints`
- minimal API, lifecycle, approval-flow, and reducer tests

## Not Implemented Yet

The following are still pending or stubbed:

- full compiled execution package delivery and external worker runtime handoff beyond the in-process minimal compiler boundary
- employee hire / replace / freeze lifecycle beyond the seeded roster
- incident / circuit-breaker escalation
- cancel / richer retry policy / heartbeat timeout states beyond the current minimal loop
- Maker-Checker review loop
- richer Review Room evidence assembly beyond persisted approval packs
- non-reference-only Context Compiler execution with artifact hydration, cache reuse, and richer provenance
- artifact store / artifact index and strict worker-result validator
- FTS / vector retrieval
- React Boardroom UI

## Implemented Contracts

The first backend slice already locks the route names and API boundaries:

- `POST /api/v1/commands/project-init`
- `GET /api/v1/projections/dashboard`
- `GET /api/v1/projections/inbox`
- `GET /api/v1/projections/review-room/{review_pack_id}`
- `GET /api/v1/events/stream?after={cursor}`
- `POST /api/v1/commands/ticket-create`
- `POST /api/v1/commands/ticket-lease`
- `POST /api/v1/commands/ticket-start`
- `POST /api/v1/commands/ticket-fail`
- `POST /api/v1/commands/ticket-complete`
- `POST /api/v1/commands/scheduler-tick`
- `POST /api/v1/commands/board-approve`
- `POST /api/v1/commands/board-reject`
- `POST /api/v1/commands/modify-constraints`

The command acknowledgement is already real and returns:

- `command_id`
- `idempotency_key`
- `status`
- `received_at`
- `reason`
- `causation_hint`

## Local Run

After installing Python 3.12 locally:

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -e .[dev]
uvicorn app.main:app --reload
```

Run the independent scheduler runner with:

```bash
cd backend
python -m app.scheduler_runner
```

Run tests with:

```bash
cd backend
python -m pytest
```

Default database path:

- `backend/data/boardroom_os.db`

Override with:

- `BOARDROOM_OS_DB_PATH`
- `BOARDROOM_OS_BUSY_TIMEOUT_MS`
- `BOARDROOM_OS_RECENT_EVENT_LIMIT`
- `BOARDROOM_OS_SCHEDULER_POLL_INTERVAL_SEC`
- `BOARDROOM_OS_SCHEDULER_MAX_DISPATCHES`

## Document Index

- [feature.txt](feature.txt)
- [message-bus-design.md](message-bus-design.md)
- [context-compiler-design.md](context-compiler-design.md)
- [meeting-room-protocol.md](meeting-room-protocol.md)
- [boardroom-ui-design.md](boardroom-ui-design.md)
- [boardroom-data-contracts.md](boardroom-data-contracts.md)
- [memory.txt](memory.txt)

## Planned Stack

- Backend: Python 3.12 + FastAPI + Pydantic v2
- Data layer: SQLite + WAL + hand-written SQL
- Frontend: React + Vite + TypeScript + TailwindCSS
- Sync: REST + SSE
- Storage: SQLite for control-plane metadata, filesystem references for larger artifacts

## Near-Term MVP Direction

This slice only establishes the first control-plane loop. The next implementation layers still follow the written design:

- richer projection reducer
- ticket cancel / richer retry / incident state machines
- expansion from the current reference-only compiler boundary to full compilation with artifact hydration, retrieval, and cache reuse
- worker / checker execution chain
- Board Review Pack and decision commands
- minimal Boardroom UI

## Philosophy

Boardroom OS is opinionated:

- less chat
- more governance
- less hidden state
- more auditability
- less prompt juggling
- more structured delivery

The goal is not 鈥渁n agent that talks a lot鈥?

The goal is:

**an agent operating system that can be governed, reviewed, and shipped**


