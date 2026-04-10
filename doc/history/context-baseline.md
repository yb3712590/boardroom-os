# Context Baseline

> Stable context that rarely changes. Read this only after `doc/mainline-truth.md` and `doc/TODO.md`, and only when you need stable rules or architecture baseline.

## How To Use This File

- Use this file for product model, governance rules, stable architecture, and frozen boundaries.
- Use `doc/mainline-truth.md` for current executable truth.
- Use `doc/TODO.md` for the current action list.
- Use `doc/history/memory-log.md` only when recent changes still affect implementation decisions.

## Product Model

- Boardroom OS is an event-sourced agent delivery control plane, not a multi-agent chat shell.
- The intended operating model remains: Board -> structured worker execution -> auditable deliverables -> explicit review gates.
- Board involvement should stay limited to real approval points, not internal drafting chatter.
- React Boardroom UI is a thin governance shell; workflow truth stays in backend events and projections.

## Governance Rules

- Ticket lifecycle, incidents, approvals, and review loops are the real control surface.
- Maker-Checker is the default internal quality gate before CEO or Board escalation.
- Important outputs must stay schema-checked, write-set-checked, and auditable.
- CEO should remain outside the workflow state machine: it reads snapshots, emits controlled actions, and does not become a long-lived stateful node.
- Formal dispatch intent should come from CEO based on the employee registry and projections; the scheduler should only execute deterministic readiness, lease, retry, and wakeup mechanics.
- Runtime should keep work moving autonomously and escalate only on defined blocking, risk, or approval conditions.
- Current large refactor priority is protocol/controller/source-deliverable convergence; do not reopen role/provider expansion ahead of that.
- Parallel implementation / serial closeout is a governance preference, not current runtime scheduling policy.
- Documentation governance currently lives in the maintained doc stack (`README` / `mainline-truth` / `roadmap-reset` / `TODO` / `task-backlog` / `history`), not in a separate system engine.
- Completion currently means code, config, UI, tests, evidence, and affected docs should be aligned before downstream claims; for now this is a checker / closeout expectation, not a hard state-machine gate.

## Stable Architecture

- Backend remains the executable center: FastAPI + Pydantic v2 + SQLite.
- Durable truth lives in the event log plus deterministic projections.
- Role templates belong to the staffing/governance layer; runtime execution should converge on ticket contract, execution target, and capability requirements rather than role names as hard execution keys.
- Worker input should come from a compiled execution package, not ad hoc payload stitching.
- Process assets are the durable handoff layer: upstream context is compiled from them, and ticket results should flow back into the same asset surface.
- Context Compiler is the deterministic boundary for evidence selection, budget control, and audit artifacts.
- Runtime output should flow back through the same structured `ticket-result-submit` ingress.

## Frozen But Still Present

- The repo still contains heavier infrastructure slices such as `worker-admin`, multi-scope worker binding, object-store support, and remote handoff.
- Those paths are not current mainline. Unless they directly unblock local MVP, treat them as frozen.
- Higher-impact future capabilities such as `SPIKE_TICKET`, project maps, process-asset systems, and organization learning remain postponed unless the roadmap boundary changes.

## Current Entry Points

- `doc/mainline-truth.md`: current code truth and support matrix
- `doc/roadmap-reset.md`: current boundary and decision rules
- `doc/TODO.md`: current pending work only
- `doc/history/memory-log.md`: recent implementation memory only, not default first-read
