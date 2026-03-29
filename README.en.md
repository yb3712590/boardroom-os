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
- `GET /api/v1/projections/incidents/{incident_id}` for minimal incident detail projection
- `GET /api/v1/projections/review-room/{review_pack_id}` real projection for persisted approval packs
- `GET /api/v1/projections/review-room/{review_pack_id}/developer-inspector` for persisted developer inspector JSON artifacts
- `GET /api/v1/events/stream?after={cursor}` SSE stream
- real `CommandAckEnvelope`
- minimal `events`, `workflow_projection`, `ticket_projection`, `node_projection`, `approval_projection`, `employee_projection`, and `incident_projection` schema
- minimal persisted `compiled_context_bundle` and `compile_manifest` audit tables
- `POST /api/v1/commands/ticket-create` for full control-plane ticket creation, including explicit lease timeout plus repeated-timeout escalation and backoff policy
- `POST /api/v1/commands/ticket-lease` for explicit ticket lease acquisition and renewal
- `POST /api/v1/commands/ticket-start` for moving the latest node ticket into execution
- `POST /api/v1/commands/ticket-heartbeat` for explicit liveness heartbeats while a ticket is already executing
- `POST /api/v1/commands/ticket-fail` for explicit worker failure reporting plus minimal retry creation
- `POST /api/v1/commands/ticket-complete` to turn structured ticket results into upstream approval requests
- `ticket-complete -> review_request` now only declares `developer_inspector_refs`; the review-room inspector files are exported from that ticket's real persisted minimal compile artifacts, and the companion projection stays honestly `partial` when those artifacts do not exist yet
- seeded persisted worker roster for the minimal executor pool
- `POST /api/v1/commands/scheduler-tick` for total execution timeout, heartbeat timeout, timeout-retry backoff, repeated-timeout incident / circuit-breaker escalation, and expired-lease dispatch using persisted roster by default
- dashboard `workforce_summary` backed by real roster and ticket state instead of fixed zeros
- dashboard / inbox incident and circuit-breaker counts are now backed by real projections instead of fixed zeros
- dashboard `provider_health_summary` and `provider_alerts` are now backed by minimal real provider-incident projections instead of placeholder values
- repeated runtime timeouts now open a minimal incident and circuit breaker on the affected node and block further automatic dispatch on that node
- ordinary `TICKET_FAILED` results now also participate in repeated-failure governance on the same `workflow_id + node_id` retry chain; when `escalation_policy.on_repeat_failure=escalate_ceo` and the same failure fingerprint reaches `repeat_failure_threshold`, backend opens a minimal incident and circuit breaker and blocks later automatic dispatch on that node
- `POST /api/v1/commands/incident-resolve` now provides a controlled manual recovery path: by default it still only closes the circuit breaker and the incident, but an explicit `RESTORE_AND_RETRY_LATEST_TIMEOUT` follow-up can reopen the node and create one bounded retry for the latest timeout ticket in the same transaction
- `incident-resolve` now also supports ordinary failure recovery; an explicit `RESTORE_AND_RETRY_LATEST_FAILURE` follow-up validates that the latest terminal state is still an ordinary `TICKET_FAILED` and that retry budget still allows one more retry, then creates one bounded retry in the same transaction
- the minimal worker roster now carries internal `provider_id` bindings for provider-level runtime governance
- `PROVIDER_RATE_LIMITED` and `UPSTREAM_UNAVAILABLE` failures now open provider-scoped incidents and circuit breakers, pausing later automatic dispatch plus manual lease/start on that provider
- `incident-resolve` also supports provider recovery now; an explicit `RESTORE_AND_RETRY_LATEST_PROVIDER_FAILURE` follow-up validates retry budget on the latest provider-failure ticket and creates one bounded retry in the same transaction
- independent scheduler runner via `python -m app.scheduler_runner`
- runner-driven minimal automatic execution chain from `TICKET_LEASED` to `TICKET_STARTED`, then through a minimal `CompileRequest -> CompiledContextBundle / CompileManifest -> CompiledExecutionPackage` compile-and-persist boundary before `TICKET_COMPLETED` or `TICKET_FAILED`
- FastAPI can now also host an optional in-process background scheduler loop behind an explicit env flag; it stays off by default so app startup behavior does not change unless requested
- persisted minimal `CompiledContextBundle` / `CompileManifest` audit artifacts with ticket-level lookup; provenance is still reference-only and does not hydrate artifact bodies yet
- `POST /api/v1/commands/board-approve`
- `POST /api/v1/commands/board-reject`
- `POST /api/v1/commands/modify-constraints`
- minimal API, lifecycle, approval-flow, and reducer tests

## Not Implemented Yet

The following are still pending or stubbed:

- full compiled execution package delivery and external worker runtime handoff beyond the in-process minimal compiler boundary
- employee hire / replace / freeze lifecycle beyond the seeded roster
- cancel / richer retry policy / automatic incident recovery and close state beyond the current minimal loop
- richer provider routing, automatic recovery, and a fuller multi-provider management surface
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
- `GET /api/v1/projections/incidents/{incident_id}`
- `GET /api/v1/projections/review-room/{review_pack_id}`
- `GET /api/v1/projections/review-room/{review_pack_id}/developer-inspector`
- `GET /api/v1/events/stream?after={cursor}`
- `POST /api/v1/commands/ticket-create`
- `POST /api/v1/commands/ticket-lease`
- `POST /api/v1/commands/ticket-start`
- `POST /api/v1/commands/ticket-heartbeat`
- `POST /api/v1/commands/ticket-fail`
- `POST /api/v1/commands/ticket-complete`
- `POST /api/v1/commands/scheduler-tick`
- `POST /api/v1/commands/incident-resolve`
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

To enable the FastAPI in-process scheduler loop explicitly:

```bash
cd backend
BOARDROOM_OS_ENABLE_INPROCESS_SCHEDULER=true uvicorn app.main:app --reload
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
- `BOARDROOM_OS_ENABLE_INPROCESS_SCHEDULER`
- `BOARDROOM_OS_SCHEDULER_POLL_INTERVAL_SEC`
- `BOARDROOM_OS_SCHEDULER_MAX_DISPATCHES`
- `BOARDROOM_OS_DEVELOPER_INSPECTOR_ROOT`

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
- ticket cancel / richer retry / incident recovery state machines
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
