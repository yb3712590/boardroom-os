# Message Mechanism Design

## Status
- Draft
- Date: 2026-03-28
- Scope: workflow control plane, state bus, ticket scheduling, board approval integration

## 1. Design Goal

This framework uses an event-sourced workflow bus with stateless ticket executors instead of multi-agent chat threads. The purpose is to make the system:

- cheap in token usage
- easy to audit and replay
- robust under retries and model variance
- explicit about escalation and approval
- compatible with company-style governance

The system is not designed around "agents remembering a long conversation". It is designed around:

- durable events
- deterministic state projection
- explicit tickets
- controlled actions
- approval gates

## 2. Non-Goal

This mechanism does not attempt to:

- eliminate hallucination absolutely
- let agents free-chat with each other
- use implicit hidden memory as a core control primitive
- allow LLM text outputs to mutate system state directly

## 3. Core Principle

### 3.1 Control Plane vs Execution Plane

- The control plane owns state, events, approvals, retries, budgets, and routing.
- The execution plane only consumes tickets and returns structured results.
- LLMs belong to the execution plane and decision proposal layer, not the state authority layer.

### 3.2 Compute-Stateless CEO

The CEO is compute-stateless, not logically empty.

- The CEO does not keep conversational memory between invocations.
- The company still keeps durable memory in the event log and state projection.
- Every CEO invocation is a pure function over current snapshot plus trigger event.

### 3.3 No Unmodeled Direct Chat

- Agent collaboration is allowed.
- Unstructured direct conversation is not allowed.
- Collaboration must appear as events, tickets, artifact references, or approval records.

### 3.4 LLMs Propose, Reducer Decides

- LLM outputs are proposals.
- Reducer and Transition Guard decide whether proposals are valid.
- Only validated actions become committed state.

## 4. High-Level Architecture

```text
Board / Human Review
        |
        v
  Event Log (SQLite)
        |
        v
 State Projection
        |
        +--> CEO Tick Scheduler
        |         |
        |         v
        |   Proposed Actions
        |         |
        |         v
        |   Reducer + Transition Guard
        |         |
        |         v
        |    Ticket Pool / Approval Gate
        |
        +--> Context Compiler
        |         |
        |         v
        |   Stateless Workers
        |         |
        |         v
        |  Structured Results + Artifacts
        |
        +--> Monitoring / Replay / Audit
```

## 5. Main Components

### 5.1 Event Log

Single source of truth for everything that happened.

Examples:

- board directive received
- CEO action proposed and accepted
- employee hired
- ticket created
- ticket leased
- ticket completed
- artifact submitted
- test failed
- board review requested
- board review approved
- circuit breaker opened

Rules:

- append-only
- immutable after commit
- every event has actor, timestamp, workflow_id, idempotency_key, payload

### 5.2 State Projection

Derived current-state view built from event log.

Examples of projected state:

- active workflow graph
- current stage status
- ticket queue and leases
- budget usage
- employee roster
- board approval status
- artifact index
- retry counters
- incident state

The CEO reads projection, not raw event history.

### 5.3 Tick Scheduler

Wakes the CEO only on explicit triggers.

Typical triggers:

- new board directive
- ticket completion
- ticket failure
- timeout reached
- retry window reached
- approval returned
- budget threshold crossed
- circuit breaker opened

### 5.4 Reducer and Transition Guard

This is the hard safety layer.

Responsibilities:

- validate legal transitions
- enforce budget and approval policies
- check dependency graph
- reject invalid writes
- enforce write-set scope
- deduplicate repeated actions via idempotency keys

Without this layer, the architecture degenerates back into prompt orchestration.

Important constraint:

- the Reducer itself should remain deterministic and side-effect free
- LLMs propose actions
- the Reducer validates proposed actions and returns accepted state changes plus derived effects
- the runtime is responsible for appending resulting events to the Event Log

In other words:

- agents do not mutate state directly
- reducers do not perform hidden writes
- event commit is a separate runtime responsibility

### 5.5 Ticket Pool

Queue of executable work items.

Properties:

- each ticket has a lifecycle
- each ticket can be leased by exactly one executor at a time
- retries are controlled by policy
- repeated failures can trip a circuit breaker

### 5.6 Context Compiler

Deterministic context builder that prepares the minimal context for a ticket.

Inputs:

- ticket schema
- context_query_plan
- artifact references
- state projection
- retrieval policies

Outputs:

- final execution prompt input package
- structured context bundle
- provenance list of every included artifact or record

The CEO decides what evidence class is required. The Context Compiler gathers it.

### 5.7 Stateless Workers

Workers do not own hidden memory.

They receive:

- role profile
- constraints
- atomic context
- allowed tools
- output schema

They return:

- status
- structured payload
- artifact references
- confidence / issues / assumptions

## 6. Core Invariants

The system should enforce the following invariants:

1. No state change is committed directly from free text.
2. Every committed action has a typed event.
3. Every ticket has a unique idempotency key.
4. Every ticket lease expires.
5. Every worker write is restricted by allowed_write_set.
6. Every board-gated node remains frozen until approval result is committed.
7. Every retry increments a visible counter.
8. Every circuit breaker event is explicit and auditable.

## 7. Event Model

## 7.1 Event Envelope

```json
{
  "event_id": "evt_...",
  "workflow_id": "wf_...",
  "event_type": "TICKET_CREATED",
  "actor_type": "ceo|worker|board|system",
  "actor_id": "ceo_main",
  "occurred_at": "2026-03-28T12:00:00+08:00",
  "idempotency_key": "....",
  "causation_id": "evt_prev",
  "correlation_id": "wf_...",
  "payload": {}
}
```

## 7.2 Recommended Event Types

### Board events

- `BOARD_DIRECTIVE_RECEIVED`
- `BOARD_REVIEW_REQUIRED`
- `BOARD_REVIEW_APPROVED`
- `BOARD_REVIEW_REJECTED`

### Organization events

- `SYSTEM_INITIALIZED`
- `EMPLOYEE_HIRE_REQUESTED`
- `EMPLOYEE_HIRED`
- `EMPLOYEE_DEACTIVATED`
- `EMPLOYEE_REPLACED`
- `EMPLOYEE_FROZEN`
- `EMPLOYEE_REMOVED`

### Workflow events

- `WORKFLOW_CREATED`
- `WORKFLOW_STAGE_ENTERED`
- `WORKFLOW_STAGE_COMPLETED`
- `WORKFLOW_ESCALATED`
- `WORKFLOW_FAILED`
- `WORKFLOW_COMPLETED`

### Ticket events

- `TICKET_CREATED`
- `TICKET_LEASED`
- `TICKET_STARTED`
- `TICKET_HEARTBEAT_RECORDED`
- `TICKET_COMPLETED`
- `TICKET_FAILED`
- `TICKET_TIMED_OUT`
- `TICKET_RETRY_SCHEDULED`
- `TICKET_CANCELLED`

### Artifact events

- `ARTIFACT_WRITTEN`
- `ARTIFACT_ACCEPTED`
- `ARTIFACT_REJECTED`

### Governance events

- `BUDGET_WARNING`
- `INCIDENT_ESCALATED`
- `CIRCUIT_BREAKER_OPENED`
- `CIRCUIT_BREAKER_CLOSED`

### Reducer-oriented validation rules

The following validation rules should be treated as baseline guards:

- `TICKET_CREATED`
  - budget must remain non-negative after reservation
  - all upstream dependencies must already be completed
  - if the node requires board approval before execution, approval state must allow creation
  - target role or executor pool must exist
- `TICKET_COMPLETED`
  - result payload must pass schema validation
  - artifact writes must pass allowed write-set validation
  - only then may the ticket move to completed state
- `TICKET_FAILED`
  - runtime should derive an error fingerprint from normalized failure detail
  - if fingerprint recurrence is below retry budget, schedule retry
  - if fingerprint recurrence reaches threshold, open circuit breaker instead of blind retry

## 8. SQLite Control Plane

SQLite is the embedded control-plane store, not the universal content store.

## 8.1 Recommended SQLite Settings

- `journal_mode=WAL`
- `synchronous=NORMAL` or `FULL` depending on reliability target
- `busy_timeout` configured
- explicit transaction boundaries
- optimistic version fields on mutable projections

## 8.2 Recommended Tables

### `events`

- `event_id`
- `workflow_id`
- `event_type`
- `actor_type`
- `actor_id`
- `occurred_at`
- `idempotency_key`
- `causation_id`
- `correlation_id`
- `payload_json`

### `workflow_projection`

- `workflow_id`
- `north_star_goal`
- `current_stage`
- `status`
- `budget_total`
- `budget_used`
- `board_gate_state`
- `updated_at`
- `version`

### `ticket_projection`

- `ticket_id`
- `workflow_id`
- `node_id`
- `status`
- `lease_owner`
- `lease_expires_at`
- `retry_count`
- `retry_budget`
- `timeout_sla_sec`
- `priority`
- `blocking_reason_code`
- `updated_at`
- `version`

### `employee_projection`

- `employee_id`
- `role_type`
- `skill_profile_json`
- `personality_profile_json`
- `aesthetic_profile_json`
- `state`
- `board_approved`
- `updated_at`
- `version`

### `artifact_index`

- `artifact_ref`
- `workflow_id`
- `ticket_id`
- `node_id`
- `logical_path`
- `kind`
- `media_type`
- `materialization_status`
- `storage_relpath`
- `content_hash`
- `size_bytes`
- `created_at`

### `approval_projection`

- `approval_id`
- `workflow_id`
- `approval_type`
- `status`
- `requested_by`
- `resolved_by`
- `resolved_at`
- `payload_json`

### `incident_projection`

- `incident_id`
- `workflow_id`
- `incident_type`
- `status`
- `severity`
- `fingerprint`
- `opened_at`
- `closed_at`
- `payload_json`

## 9. Artifact Storage

Large artifacts should not be stored inline in SQLite.

Current minimal implementation status:

- SQLite `artifact_index` stores artifact metadata, materialization status, lifecycle status, retention fields, content hash, and optional filesystem location.
- Filesystem storage is rooted at `backend/data/artifacts/` by default and can be overridden with `BOARDROOM_OS_ARTIFACT_STORE_ROOT`.
- `JSON`, `TEXT`, `MARKDOWN`, `IMAGE`, `PDF`, and other medium-sized binary artifacts can be materialized to normalized relative paths under that root through `ticket-result-submit`.
- Binary artifacts may still be accepted without inline body and remain `materialization_status = REGISTERED_ONLY` for compatibility.
- The current store uses safe relative-path normalization plus temporary-file write and atomic replace semantics.
- Artifact lifecycle now distinguishes `ACTIVE`, `DELETED`, and `EXPIRED`.
- Runtime exposes local artifact metadata / content / preview APIs keyed by `artifact_ref`.

Recommended storage split:

- SQLite: metadata, references, hashes, summaries
- Filesystem/object directory: code patches, reports, screenshots, mockups, logs, bundles

Recommended URI patterns:

- `file://...` or internal normalized relative paths
- artifact hashes for content deduplication

Current conservative reality:

- `storage_relpath` currently uses normalized internal relative paths instead of external signed URLs.
- Binary upload currently uses inline `base64` in `ticket-result-submit`; multipart upload, chunking, and object storage are still out of scope for the current MVP.
- UI / review surfaces still use local relative artifact API paths.
- External worker handoff now uses per-worker bootstrap tokens plus refreshable worker sessions on `GET /api/v1/worker-runtime/assignments`; request-time legacy shared-secret fallback has been removed from `/api/v1/worker-runtime/*`, while the bootstrap and delivery signing secrets may still fall back to `BOARDROOM_OS_WORKER_SHARED_SECRET` as configuration compatibility.
- The returned execution package, artifact access descriptors, and worker command endpoints are rewritten into absolute `/api/v1/worker-runtime/*` URLs carrying short-lived signed `access_token` query parameters scoped to one worker, one ticket, and one route family.
- Each execution-package URL, artifact content/download/preview URL, and command URL now creates its own persisted `worker_delivery_grant`, so one specific URL may be revoked without invalidating sibling URLs from the same session.
- Those signed delivery URLs are now bound to both one worker session and one persisted delivery grant, so revoking a session or rotating a bootstrap credential invalidates the related active grants without waiting for delivery-token expiry.
- `BOARDROOM_OS_PUBLIC_BASE_URL` can override the URL base used for these signed delivery links, while `BOARDROOM_OS_WORKER_DELIVERY_SIGNING_SECRET` can be rotated independently from the bootstrap signing secret if desired.
- Worker-side `tenant_id/workspace_id` binding is now real across workflow projection, ticket projection, bootstrap state, bootstrap issue records, session state, and delivery grants; one worker may now keep multiple bootstrap bindings, while each session and delivery grant remains bound to exactly one scope.
- New bootstrap tokens now carry `issue_id`; runtime still accepts legacy bootstrap tokens without that claim until they expire naturally, but if `issue_id` is present the backend also requires a matching non-revoked persisted `worker_bootstrap_issue`.
- Local operator tooling now includes explicit binding lifecycle commands (`create-binding`, enriched `list-bindings`, `cleanup-bindings`), HTTP revoke controls for session and delivery grant under `worker-admin`, a dedicated operator-token CLI on `python -m app.worker_admin_auth_cli issue-token` with bounded short-lived TTLs, and projection read models on `GET /api/v1/projections/worker-runtime` plus `GET /api/v1/projections/worker-admin-audit`.
- The trusted `worker-admin` HTTP surface now enforces a signed entry boundary: every request must carry `X-Boardroom-Operator-Token`, deployments may additionally require `X-Boardroom-Trusted-Proxy-Id` through `BOARDROOM_OS_WORKER_ADMIN_TRUSTED_PROXY_IDS`, `platform_admin` keeps global read/write, `scope_admin` and `scope_viewer` are limited to one exact `tenant_id/workspace_id` scope, and legacy `X-Boardroom-Operator-*` headers are now only compatibility assertions rather than identity truth.
- Assignment and delivery validation now reject on four layers:
  - token claim route match
  - persisted bootstrap/session/grant state match
  - current ticket ownership
  - ticket / workflow `tenant_id/workspace_id` consistency
- `worker_auth_rejection_log` now records assignment and delivery rejections with route family, reason code, worker/session/grant/ticket ids, and the bound tenant/workspace scope.
- Broader multi-tenant administration and fuller public delivery boundaries are still not implemented.

## 10. Ticket Contract

## 10.1 Control-Plane Ticket Spec

```json
{
  "ticket_id": "tkt_...",
  "workflow_id": "wf_...",
  "node_id": "frontend_home_v1",
  "tenant_id": "tenant_default",
  "workspace_id": "ws_default",
  "parent_ticket_id": null,
  "attempt_no": 1,
  "role_profile_ref": "ui_designer_primary",
  "constraints_ref": "global_constraints_v3",
  "input_artifact_refs": ["art_1", "art_2"],
  "context_query_plan": {
    "keywords": ["homepage", "brand", "visual"],
    "semantic_queries": ["approved visual direction"],
    "max_context_tokens": 3000
  },
  "acceptance_criteria": [
    "Must satisfy approved visual direction",
    "Must produce 3 options",
    "Must include rationale and risks"
  ],
  "output_schema_ref": "ui_milestone_review",
  "output_schema_version": 1,
  "allowed_tools": ["read_artifact", "write_artifact", "image_gen"],
  "allowed_write_set": [
    "artifacts/ui/homepage/*",
    "reports/review/*"
  ],
  "lease_timeout_sec": 600,
  "retry_budget": 2,
  "priority": "high",
  "timeout_sla_sec": 1800,
  "deadline_at": "2026-03-28T18:00:00+08:00",
  "escalation_policy": {
    "on_timeout": "retry",
    "on_schema_error": "retry",
    "on_repeat_failure": "escalate_ceo",
    "repeat_failure_threshold": 2,
    "timeout_repeat_threshold": 2,
    "timeout_backoff_multiplier": 1.5,
    "timeout_backoff_cap_multiplier": 2.0
  },
  "idempotency_key": "wf_...:node_...:attempt_1"
}
```

This is the persistent control-plane form of a ticket.

It is not necessarily the exact payload sent to a worker. The worker should receive a compiled execution package derived from this spec.

## 10.2 Compiled Execution Package

The execution package is the final worker-facing payload after Context Compiler expansion.

```json
{
  "meta": {
    "ticket_id": "tkt_...",
    "workflow_id": "wf_...",
    "node_id": "frontend_home_v1",
    "attempt_no": 1,
    "idempotency_key": "wf_...:node_...:attempt_1"
  },
  "compiled_role": {
    "role_id": "ui_designer_primary",
    "skills": ["visual_direction", "layout", "interaction"],
    "personality_profile": {},
    "aesthetic_profile": {}
  },
  "compiled_constraints": {
    "global_rules": [],
    "board_constraints": [],
    "budget_constraints": {}
  },
  "atomic_context_bundle": {
    "context_blocks": [],
    "provenance": [],
    "token_budget": 3000
  },
  "execution": {
    "atomic_task": "Produce 2-3 homepage visual directions for board review.",
    "acceptance_criteria": [],
    "allowed_tools": ["read_artifact", "write_artifact", "image_gen"],
    "allowed_write_set": [
      "artifacts/ui/homepage/*",
      "reports/review/*"
    ],
    "output_schema_ref": "ui_milestone_review",
    "output_schema_version": 1
  },
  "governance": {
    "retry_budget": 2,
    "timeout_sla_sec": 1800,
    "escalation_policy": {
      "on_timeout": "retry",
      "on_schema_error": "retry",
      "on_repeat_failure": "escalate_ceo",
      "repeat_failure_threshold": 2,
      "timeout_repeat_threshold": 2,
      "timeout_backoff_multiplier": 1.5,
      "timeout_backoff_cap_multiplier": 2.0
    }
  }
}
```

Rule:

- workers should consume compiled execution packages, not raw references when execution starts
- control-plane refs stay in storage for audit and replay
- runtime expands refs into concrete execution input before dispatch

Current minimal handoff reality:

- `CompiledExecutionPackage` is now persisted alongside `CompiledContextBundle` and `CompileManifest`.
- `GET /api/v1/worker-runtime/assignments` remains the bootstrap endpoint:
  - it now accepts only `X-Boardroom-Worker-Bootstrap` or `X-Boardroom-Worker-Session`
  - it returns only the current worker's `LEASED` / `EXECUTING` / `CANCEL_REQUESTED` tickets
  - it now also returns `session_id`, `session_token`, and `session_expires_at`
  - each assignment now includes a short-lived signed `execution_package_url` plus `delivery_expires_at`
- Bootstrap-token validation is now split in two paths:
  - legacy tokens without `issue_id` still validate only against persisted bootstrap state until they expire
  - newer tokens with `issue_id` must also match one persisted `worker_bootstrap_issue` row on worker, scope, credential version, issue time, and expiry
- `GET /api/v1/worker-runtime/tickets/{ticket_id}/execution-package` now requires a signed `access_token`, returns the latest persisted package for the currently leased worker, compiles it on demand if that attempt has not been persisted yet, and also returns `delivery_expires_at`.
- Artifact access descriptors inside the delivered package remain reference-first, but their `content_url` / `preview_url` / `download_url` are now rewritten into worker-scoped absolute signed URLs for that request; each of those URLs gets its own persisted delivery grant.
- `GET /api/v1/worker-runtime/artifacts/by-ref` conservatively reuses any valid artifact token for the same `ticket_id + artifact_ref`; there is no separate metadata-only grant.
- `POST /api/v1/worker-runtime/commands/ticket-start|ticket-heartbeat|ticket-result-submit` now require signed command URLs and still reuse the existing command handlers, so they do not introduce a second governance path.
- Signed delivery token validation is ordered as:
  - signature + expiry
  - persisted delivery grant exists, is not revoked, is not expired, and matches the token claim set
  - active session exists and is not revoked
  - session credential version still matches the worker's current bootstrap credential version
  - scope / ticket / artifact / command exact match
  - current worker ownership of the ticket
  - existing artifact access and lifecycle rules

## 10.3 Ticket Lifecycle

```text
created -> leased -> started -> completed
created -> leased -> started -> failed -> retry_scheduled -> created
created -> leased -> started -> failed -> escalated
created -> cancelled
```

## 10.4 Ticket Result Contract

Every worker result should include:

- `result_status`
- `schema_version`
- `payload`
- `artifact_refs`
- `written_artifacts`
- `assumptions`
- `issues`
- `confidence`
- `needs_escalation`
- `summary`

Example:

```json
{
  "result_status": "completed",
  "schema_version": "ui_milestone_review_v1",
  "payload": {
    "summary": "Runtime prepared a minimal review package.",
    "recommended_option_id": "option_a",
    "options": [
      {
        "option_id": "option_a",
        "label": "Option A",
        "summary": "Primary minimal runtime-generated review option.",
        "artifact_refs": ["art://runtime/tkt_ui_home_03/option-a.json"]
      }
    ]
  },
  "artifact_refs": ["art://runtime/tkt_ui_home_03/option-a.json"],
  "written_artifacts": [
    {
      "path": "reports/review/option-a.json",
      "artifact_ref": "art://runtime/tkt_ui_home_03/option-a.json",
      "kind": "JSON",
      "content_json": {
        "option_id": "option_a",
        "headline": "Primary runtime-generated structured review artifact."
      }
    }
  ],
  "assumptions": ["mobile first", "existing brand palette retained"],
  "issues": [],
  "confidence": 0.78,
  "needs_escalation": false,
  "summary": "Runtime prepared a minimal review package."
}
```

Current `ticket-result-submit` rules:

- `POST /api/v1/commands/ticket-result-submit` is the unified structured result ingress.
- `schema_version` plus `payload` must pass submit-time validation against the created ticket's `output_schema_ref/output_schema_version`.
- `written_artifacts[*].path` must match the ticket `allowed_write_set`.
- `artifact_ref` and normalized `path` must both be unique within one submission.
- `JSON` artifacts must include `content_json`.
- `TEXT` and `MARKDOWN` artifacts must include `content_text`.
- Binary kinds may include `content_base64` plus optional `media_type` to trigger real materialization; if the body is omitted they stay `REGISTERED_ONLY`.
- Each written artifact may carry `retention_class` and optional `retention_ttl_sec`; cleanup later moves expired artifacts into `EXPIRED`.
- Artifact validation and materialization happen before `TICKET_COMPLETED`; failures are converted into controlled `SCHEMA_ERROR`, `WRITE_SET_VIOLATION`, `ARTIFACT_VALIDATION_ERROR`, or `ARTIFACT_PERSIST_ERROR` paths instead of bypassing governance.
- The in-process runtime success path now emits real structured JSON artifacts such as `option-a.json` and `option-b.json` instead of placeholder image refs.
- Compiled execution packages still stay reference-first, but artifact source descriptors now include access metadata such as `materialization_status`, `lifecycle_status`, `content_url`, and `preview_url`.

Current minimal output schema registry coverage:

- `ui_milestone_review@1`
- `consensus_document@1`
- Unknown schema refs may still return a placeholder schema body for discovery, but submit-time validation rejects them.

## 11. CEO Tick Cycle

## 11.1 Input

Each CEO invocation should receive:

- workflow summary
- current stage and node states
- trigger event
- outstanding approvals
- budget summary
- active incidents
- hire roster summary
- ready / blocked ticket counts

## 11.2 Output

The CEO must return actions only.

Example:

```json
{
  "actions": [
    {
      "type": "CREATE_TICKET",
      "payload": {}
    },
    {
      "type": "REQUEST_BOARD_REVIEW",
      "payload": {}
    }
  ]
}
```

## 11.3 Validation

Reducer checks:

- are prerequisites complete
- is write scope legal
- does action require board approval
- is budget sufficient
- is retry budget exhausted
- does employee exist and match role

Only validated actions become events.

## 12. Context Compiler

The Context Compiler is a deterministic service, not an LLM policy role.

Detailed contract, trust model, token budget strategy, and IR schema are defined in `context-compiler-design.md`.

## 12.1 Inputs

- ticket metadata
- state projection
- artifact references
- FTS hits
- vector hits
- constraint references

## 12.2 Output Bundle

```json
{
  "role": {},
  "constraints": {},
  "atomic_context": [],
  "provenance": [],
  "output_schema": "..."
}
```

## 12.3 Rules

- include only referenced or query-matched artifacts
- keep token budget explicit
- include provenance for every context block
- fail closed on missing critical references

## 13. Board Approval Gate

Board gate is part of the same state machine.

## 13.1 Typical Approval Types

- visual milestone approval
- core hire approval
- major budget deviation approval
- scope pivot approval

## 13.2 Gate Rules

- if node requires board approval, only the dependent subgraph remains frozen
- technical preparation may continue if explicitly allowed by policy
- final merge or final publish cannot proceed before approval event is committed

## 13.3 Visual Milestone Node State Machine

Board-gated visual milestones should use explicit node states:

- `PENDING`
- `EXECUTING`
- `BLOCKED_FOR_BOARD_REVIEW`
- `REWORK_REQUIRED`
- `COMPLETED`

State meaning:

- `PENDING`: waiting for prerequisites or waiting to be scheduled
- `EXECUTING`: worker is currently generating reviewable visual output
- `BLOCKED_FOR_BOARD_REVIEW`: artifact exists and is waiting for board decision
- `REWORK_REQUIRED`: board rejected the current attempt and CEO must create a new attempt
- `COMPLETED`: board-approved version is locked and downstream may proceed

## 13.4 Transition Protocol

### Entering the board gate

1. A visual worker returns a valid `TICKET_COMPLETED`.
2. Reducer validates schema and write-set.
3. If the node has `requires_board_approval=true`, runtime does not mark it completed yet.
4. Runtime appends `BOARD_REVIEW_REQUIRED`.
5. Node state becomes `BLOCKED_FOR_BOARD_REVIEW`.
6. Only downstream dependent nodes are frozen.

### Board approves

1. Runtime appends `BOARD_REVIEW_APPROVED`.
2. Node state becomes `COMPLETED`.
3. Frozen dependent subgraph is unfrozen.
4. CEO is ticked to continue scheduling.

### Board rejects

1. Runtime appends `BOARD_REVIEW_REJECTED` with structured review comments.
2. Node state becomes `REWORK_REQUIRED`.
3. CEO is ticked with board feedback.
4. CEO may create a fresh replacement ticket or restart the node with a new attempt number.

Rule:

- rejection should not silently rewind state to generic `PENDING`
- `REWORK_REQUIRED` preserves the fact that the board reviewed and rejected the current attempt

## 13.5 Approval Payload

```json
{
  "approval_id": "apr_...",
  "approval_type": "visual_milestone",
  "options": [
    {
      "option_id": "A",
      "summary": "...",
      "artifact_refs": ["art_a1"],
      "risks": ["..."]
    }
  ],
  "recommended_option_id": "A"
}
```

## 14. Conflict Resolution and Circuit Breaker

## 14.1 Detectable Failure Patterns

- same test failure fingerprint repeated N times within the same node or ticket family
- same compile error fingerprint repeated N times within the same node or ticket family
- same schema validation failure fingerprint repeated N times within the same node or ticket family
- same write-set conflict fingerprint repeated N times within the same node or ticket family
- budget burn above threshold
- dependency blocked beyond SLA

## 14.2 Circuit Breaker Policy

When triggered:

1. open incident
2. freeze related node or dependent subtree
3. emit escalation event
4. attach failure snapshot
5. route to CEO or Board depending on policy

Current minimal implementation status:

- repeated ordinary `TICKET_FAILED` with the same fingerprint on the same `workflow_id + node_id` retry chain can now open a node-scoped `REPEATED_FAILURE_ESCALATION`
- repeated-failure escalation is gated by `escalation_policy.on_repeat_failure` plus `repeat_failure_threshold`
- repeated `TIMEOUT_SLA_EXCEEDED` and `HEARTBEAT_TIMEOUT` on the same `workflow_id + node_id` retry chain can open the breaker
- timeout-triggered retry create may widen both total timeout and lease / heartbeat window using bounded backoff
- the breaker currently blocks automatic dispatch on that node only
- `PROVIDER_RATE_LIMITED` and `UPSTREAM_UNAVAILABLE` can also open a provider-scoped incident / breaker keyed by `provider_id`
- provider-scoped breaker blocks later automatic dispatch and manual lease / start on workers bound to that provider, while other providers may still take the ticket
- minimal manual restore is now implemented via `CIRCUIT_BREAKER_CLOSED` followed by `INCIDENT_CLOSED`
- `incident-resolve` can use `RESTORE_AND_RETRY_LATEST_FAILURE` to clear a repeated-failure breaker and create one bounded retry from the latest ordinary failure ticket
- `incident-resolve` defaults to restore-only, but an explicit `RESTORE_AND_RETRY_LATEST_TIMEOUT` can add one bounded timeout retry before closing the incident
- `incident-resolve` can also use `RESTORE_AND_RETRY_LATEST_PROVIDER_FAILURE` to clear a paused provider and create one bounded retry from the latest provider-failure ticket
- close / restore still does not imply automatic retry creation by default or automatic incident closure after later success

## 14.3 Failure Snapshot Should Include

- incident fingerprint
- affected ticket ids
- related artifacts
- latest logs
- retry history
- recommended next actions

## 15. Concurrency and Lease Protocol

SQLite needs explicit concurrency discipline.

## 15.1 Lease Rules

- only one executor may hold an active ticket lease
- lease has `lease_expires_at`
- expired lease can be reclaimed by scheduler
- executing tickets should emit explicit heartbeat updates separate from lease acquisition
- total execution SLA and heartbeat timeout should be evaluated independently
- duplicate completion is ignored via idempotency key

## 15.2 Optimistic Update Rule

Projection tables should have a `version` column.

Reducer updates must check:

- current version equals expected version

If not:

- reload projection
- rebuild action
- retry under policy

## 16. Anti-Hallucination Strategy

This design reduces hallucination through structure, not through claims.

Main controls:

- minimal context
- explicit constraints
- output schema validation
- tool result verification
- deterministic reducers
- artifact hashing
- write-set restrictions
- retry classification

## 17. Observability and Time Travel

Because the control plane is event-sourced:

- every workflow can be replayed
- state can be reconstructed at any historical point
- incidents can be debugged from event history
- a `.db` snapshot can serve as a checkpoint for disaster recovery or branch replay

Recommended audit views:

- workflow replay timeline
- ticket retry heatmap
- board gate latency
- budget burn chart
- incident frequency by fingerprint
- employee utilization by role

## 18. Example Flow

### Example: homepage redesign with board visual approval

1. `BOARD_DIRECTIVE_RECEIVED`
2. `WORKFLOW_CREATED`
3. CEO tick creates technical discovery tickets and visual direction ticket
4. Discovery workers submit artifacts
5. CEO tick requests board visual review
6. `BOARD_REVIEW_REQUIRED`
7. Board approves option B
8. `BOARD_REVIEW_APPROVED`
9. Downstream UI implementation tickets unfreeze
10. Worker implements approved direction
11. Test / review tickets run
12. Final artifact bundle created
13. `WORKFLOW_COMPLETED`

## 19. Implementation Order

Recommended delivery order:

1. event log schema
2. projection reducer
3. ticket table and lease protocol
4. CEO action schema and validator
5. worker result schema validator
6. board approval gate
7. context compiler
8. FTS retrieval
9. vector retrieval
10. circuit breaker and incident model

## 20. Final Position

This message mechanism should be treated as a workflow operating system, not as a chat orchestration pattern.

The core idea is:

- state lives in the bus
- decisions are proposed by agents
- legality is enforced by deterministic reducers
- work moves through tickets
- approvals are explicit gates
- replay and audit are first-class

If these properties are maintained, the system can support company-style autonomous execution with controlled human intervention.
