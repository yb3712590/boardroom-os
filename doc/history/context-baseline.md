# Context Baseline

> Stable context that rarely changes. Read this after `doc/mainline-truth.md` and before `doc/history/memory-log.md`.

## How To Use This File

- Use this file for product model, governance rules, stable architecture, and frozen boundaries.
- Use `doc/mainline-truth.md` for current executable truth.
- Use `doc/TODO.md` for the current action list.
- Use `doc/history/memory-log.md` only for recent changes that still affect implementation decisions.

## Product Model

- Boardroom OS is an event-sourced agent delivery control plane, not a multi-agent chat shell.
- The intended operating model remains: Board -> structured worker execution -> auditable deliverables -> explicit review gates.
- Board involvement should stay limited to real approval points, not internal drafting chatter.
- React Boardroom UI is a thin governance shell; workflow truth stays in backend events and projections.

## Governance Rules

- Ticket lifecycle, incidents, approvals, and review loops are the real control surface.
- Maker-Checker is the default internal quality gate before CEO or Board escalation.
- Important outputs must stay schema-checked, write-set-checked, and auditable.
- Runtime should keep work moving autonomously and escalate only on defined blocking, risk, or approval conditions.

## Stable Architecture

- Backend remains the executable center: FastAPI + Pydantic v2 + SQLite.
- Durable truth lives in the event log plus deterministic projections.
- Worker input should come from a compiled execution package, not ad hoc payload stitching.
- Context Compiler is the deterministic boundary for evidence selection, budget control, and audit artifacts.
- Runtime output should flow back through the same structured `ticket-result-submit` ingress.

## Frozen But Still Present

- The repo still contains heavier infrastructure slices such as `worker-admin`, multi-scope worker binding, object-store support, and remote handoff.
- Those paths are not current mainline. Unless they directly unblock local MVP, treat them as frozen.

## Current Entry Points

- `doc/mainline-truth.md`: current code truth and support matrix
- `doc/roadmap-reset.md`: current boundary and decision rules
- `doc/TODO.md`: current pending work only
- `doc/history/memory-log.md`: recent implementation memory only
