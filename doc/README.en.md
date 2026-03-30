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

Run the standalone scheduler runner:

```bash
cd backend
source .venv/bin/activate
python -m app.scheduler_runner
```

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
- Artifact access currently uses local relative API URLs. External-worker reachability, auth, and signed-URL delivery are still not implemented.

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
