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

## What It Is

Boardroom OS is not:

- a chat-first agent shell
- an animated AI office demo
- a loose multi-agent group chat

It is a control-plane-oriented system for governed agent execution.

## Core Ideas

- Event log as source of truth
- Projection-first runtime state
- Ticket-driven stateless workers
- Context Compiler for deterministic context assembly
- Maker-Checker internal review
- Board Gate for explicit human approval
- Boardroom UI as a governance console

## Current Status

This repository is currently in the design-finalization and bootstrap stage.

What exists now:

- feature constraints
- workflow bus design
- Context Compiler design
- Meeting Room protocol design
- Boardroom UI design
- Boardroom data contracts

This repository should currently be understood as:

**RFC + PRD + API contract set for Boardroom OS**

It is not production-ready yet.

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

## MVP Direction

The first runnable slice aims to include:

- project initialization
- event store
- projection APIs
- SSE event stream
- Context Compiler skeleton
- worker execution skeleton
- one Maker-Checker loop
- one Board review loop
- a minimal Boardroom UI shell

## Non-Goals for MVP

- chat-first UI
- animated office metaphors
- complex homepage DAG rendering
- dedicated Meeting Room UI
- heavy ORM-based persistence
- speculative features outside the written design contracts

## Open Source Direction

Boardroom OS is intended to become a GitHub-friendly open-source base project:

- easy to clone
- easy to understand
- explicit in architectural boundaries
- suitable for human + AI collaboration

## Versioning

Planned starting version:

- `0.1.0`

Suggested current stage:

- `pre-alpha`

## License

License is not finalized yet.

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
