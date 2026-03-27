# Boardroom OS

> Event-sourced Agent Governance.

English overview. 中文版请见 [README.md](README.md)

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
- `GET /api/v1/projections/review-room/{review_pack_id}` reserved route, currently returning `404`
- `GET /api/v1/events/stream?after={cursor}` SSE stream
- real `CommandAckEnvelope`
- minimal `events`, `workflow_projection`, and `approval_projection` schema
- API and reducer test scaffolding

## Not Implemented Yet

The following are still pending or stubbed:

- CEO tick scheduler
- ticket pool and lease protocol
- worker execution chain
- Maker-Checker review loop
- board approval commands
- full Review Room projection content
- Context Compiler execution
- FTS / vector retrieval
- React Boardroom UI

## Implemented Contracts

The first backend slice already locks the route names and API boundaries:

- `POST /api/v1/commands/project-init`
- `GET /api/v1/projections/dashboard`
- `GET /api/v1/projections/inbox`
- `GET /api/v1/projections/review-room/{review_pack_id}`
- `GET /api/v1/events/stream?after={cursor}`

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

Run tests with:

```bash
cd backend
pytest
```

Default database path:

- `backend/data/boardroom_os.db`

Override with:

- `BOARDROOM_OS_DB_PATH`

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
- ticket / review / approval state machines
- Context Compiler skeleton
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

The goal is not “an agent that talks a lot”.

The goal is:

**an agent operating system that can be governed, reviewed, and shipped**

