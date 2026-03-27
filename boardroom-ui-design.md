# Boardroom UI Design

## Status
- Draft
- Date: 2026-03-28
- Scope: lightweight web control plane and human approval console for the Agent Team framework

## 1. Positioning

`Boardroom UI` is not a chat app, not an office animation product, and not a generic project management system.

It should be treated as:

- an `Agent Workflow Control Plane`
- a `Human Approval Console`
- a projection-first runtime dashboard

Its primary jobs are:

- show current workflow state clearly
- expose governance pressure points
- let the Board intervene only at defined checkpoints
- surface model routing and system health
- keep the entire system observable without turning the UI into the place where logic lives

## 2. Product Boundaries

The UI should not attempt to:

- replicate the entire workflow engine in the browser
- make chat transcripts the main product surface
- force users to understand raw event history before acting
- become a full ERP-style admin system

The UI should focus on:

- projection rendering
- command submission
- approval workflows
- system and workforce monitoring
- model/provider configuration

## 3. Core Design Principles

1. Projection-first, not prompt-first.
2. High density, not decorative animation.
3. Human intervention should be rare, clear, and consequential.
4. Runtime truth stays in backend projections and event log.
5. Frontend may own local view state, but never workflow truth.
6. The control plane should stay lightweight enough to clone and run as a base project.

## 4. Startup Flow

The startup experience should be split into two tracks.

### 4.1 System Setup

This is done rarely and should configure the environment itself:

- providers
- API keys
- default model pool
- workspace path
- default budget policy

This should not run every time a new project starts.

### 4.2 Project Init

This is the real "startup ritual" for a new workflow.

It should support two entry modes:

- `Guided Setup`
  - simple form or wizard
  - suitable for first-time users and non-technical operators
- `Quick Start`
  - command-palette style launch
  - suitable for repeat users and technical users

Minimum project init fields:

- north star goal
- hard constraints
- budget cap
- optional delivery deadline

The ritual should feel decisive, but not theatrical. The sense of ceremony should come from crisp execution and immediate state transition, not from repeated animations.

## 5. Information Architecture

Recommended default layout: `three columns + one overlay + one inspector`.

### 5.1 Left Column: Inbox and System Entry

Purpose:

- show what needs Board action now
- provide entry to config and system controls

Contents:

- approval inbox
- escalations
- budget alerts
- provider health alerts
- entry points to model/provider settings

### 5.2 Center Column: Pipeline View

This is the primary runtime view.

Recommended default representation:

- pipeline lanes
- collapsible tree list
- phase -> epic -> task hierarchy

Node states should remain visible:

- pending
- executing
- under review
- blocked for board
- fused / incident
- completed

The center column should show:

- current stage
- critical path
- blocked nodes
- ticket ownership
- current status summaries

### 5.3 Right Column: Workforce and Event Stream

Upper section:

- active executors
- role pools
- current assignments
- current model binding
- elapsed time
- retry / rework pressure

Lower section:

- event ticker
- filterable by workflow, severity, category, actor, or node
- collapsed summaries for noisy repeated events

### 5.4 Overlay: Review Room

This is the Board interaction room for approval actions.

It should open from the inbox, not as a tiny modal.

Recommended behavior:

- full-screen drawer or dedicated review page
- optimized for inspection and decision
- used for:
  - visual approval
  - budget exceptions
  - no-consensus escalations
  - strategic constraint changes

### 5.5 Secondary Inspector: Dependency Inspector

The DAG should not be the default homepage view, but it should exist as a secondary inspector.

Purpose:

- inspect dependency structure
- debug freezes and deadlocks
- view dependent subgraph impact
- see critical path and blocker chains

This avoids turning the main UI into a spaghetti graph while preserving the architecture's true dependency model.

## 6. Review Room Contract

The Board should not be forced to read raw `CompiledContextBundle` as its primary artifact.

The UI should present a `Board Review Pack` assembled from lower-level execution context and review artifacts.

Detailed projection and `Board Review Pack` contracts are defined in `boardroom-data-contracts.md`.

Recommended review pack sections:

- what is being reviewed
- why review was triggered
- current recommendation
- artifact preview
- delta versus previous attempt
- key evidence summary
- Maker-Checker result summary
- risks
- budget impact
- actionable buttons

The raw `CompiledContextBundle` can exist behind an advanced "developer inspector" section, but should not be the default Board-facing representation.

## 7. Required UI Surfaces

### 7.1 Must-have for MVP

- project init screen
- main control dashboard
- approval inbox
- review room
- provider/model configuration page

### 7.2 Important but secondary

- dependency inspector
- worker detail panel
- incident detail panel
- queryable event explorer

### 7.3 Explicitly not required for MVP

- chat-first interface
- animated office metaphors
- full employee history timeline
- Meeting Room dedicated UI

Meeting Room can first surface as a standard escalation or incident item without custom collaboration visuals.

## 8. Runtime Health Layer

The UI should include a compact but always-visible `Ops Strip` or `Health Bar`.

Minimum fields:

- total budget used / remaining
- token burn rate
- active ticket count
- blocked node count
- circuit breaker count
- provider health
- queue depth
- retry storm indicator

This can live as a header strip above the main layout.

## 9. Frontend and Backend Boundary

The browser should not own workflow state. Backend remains the source of truth.

### 9.1 Data pattern

Use a stable `snapshot + stream + command` model.

#### Snapshot

Used for initial load and resync.

Examples:

- `GET /api/v1/projections/dashboard`
- `GET /api/v1/projections/workflow/{id}`
- `GET /api/v1/projections/inbox`
- `GET /api/v1/projections/providers`

#### Stream

Used for ongoing event-driven updates.

Recommended transport:

- `SSE` for MVP

Examples:

- `GET /api/v1/events/stream?after=cursor`

Expected stream behavior:

- reconnect support
- cursor-based resume
- heartbeat events
- projection version hints
- full-resync hint on drift

#### Command

Used for explicit human actions.

Examples:

- `POST /api/v1/commands/project-init`
- `POST /api/v1/commands/board-approve`
- `POST /api/v1/commands/board-reject`
- `POST /api/v1/commands/modify-constraints`
- `POST /api/v1/commands/provider-upsert`
- `POST /api/v1/commands/provider-test-route`

### 9.2 Frontend-owned state

Allowed local state:

- filters
- sort mode
- expanded rows
- active workflow tab
- event cursor
- side panel visibility
- review draft form state
- command in-flight state

Disallowed frontend authority:

- workflow transition logic
- ticket legality
- approval enforcement
- model routing rules
- budget guard logic

## 10. Model and Provider Center

This should behave like infrastructure orchestration, not a simple settings form.

### 10.1 Provider-level configuration

Minimum fields:

- provider name
- base URL
- API key
- supported model list
- default headers if needed
- enabled / disabled state

### 10.2 Model-level routing metadata

Recommended first-class fields:

- capability tags
  - coding
  - reasoning
  - vision
  - long-context
  - tool-use
  - structured-output
- cost tier
- latency tier
- context window
- reliability note
- max concurrency
- rate limit
- fallback target
- health check status

### 10.3 Role binding

The system should support:

- default model by role
- override by task type
- fallback route when preferred provider fails

This prevents the entire company from being locked to one model or one vendor.

## 11. BYOK Policy

The project should prefer simplicity and cross-platform usability over enterprise-grade secret management complexity.

Accepted design direction:

- BYOK must be easy for ordinary users
- the app may run on Windows, macOS, Linux, or mainstream self-hosted environments
- secret handling should not depend on a single OS-specific credential API

Recommended practical policy:

- default path:
  - users enter API keys in the UI
  - app stores them locally in app config storage
  - UI masks keys after save
- optional advanced path:
  - import from environment variables
  - allow manual secret rotation
  - allow export/import of non-secret provider metadata

Important note:

- this is a local or self-hosted convenience product, not a multi-tenant cloud secret vault
- the system should clearly disclose that local BYOK storage trades maximum security for portability and simplicity

SQLite or local config storage is acceptable here if the goal is friction reduction, as long as the product communicates the trust model honestly.

## 12. Boardroom UI and Existing Runtime Features

The UI should explicitly surface existing governance mechanisms already decided elsewhere:

- Board Gate inbox and review flow
- Maker-Checker review state
- Meeting Room escalations as incidents or inbox items
- Context Compiler status only as metadata or diagnostics
- circuit breaker incidents
- dependent-subgraph freezes

The UI should not pretend these systems are decorative. They are core runtime structures and must be observable.

## 13. MVP Scope

Recommended MVP backend:

- FastAPI
- SQLite event store and projections
- SSE event stream
- model/provider registry
- command endpoints for project init and board decisions

Recommended MVP frontend:

- web dashboard
- project init flow
- pipeline view
- inbox
- review room
- workforce panel
- event ticker
- provider/model settings
- compact ops strip

Deferred after MVP:

- Meeting Room dedicated interface
- advanced dependency graph explorer
- historical analytics
- multi-workspace management
- deep employee persona browsing

## 14. Final Product Shape

The correct end-state is not a cute office simulator and not a bloated admin backend.

It should feel like:

- a hacker-style governance console
- a workflow observability surface
- a human override panel for a mostly autonomous company

That balance matters. If the UI becomes too decorative, it loses engineering value. If it becomes too read-only, it stops being a useful governance tool.
