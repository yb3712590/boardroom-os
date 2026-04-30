# Meeting Room Protocol

## TL;DR

- Positioning: a bounded, auditable exception path for cross-role alignment problems that are too coupled for normal serial tickets.
- Read this when: changing meeting entry conditions, meeting events, meeting state machine, consensus outputs, or how meetings return to the main workflow.
- Key contracts: `MEETING_ROOM_REQUESTED` and related events, bounded participant/input set, round execution model, `Consensus_Document`, and reopen policy.
- Current boundary: meeting room is not a persistent chat system, not a board bypass, and not a second source of workflow truth.
- Related docs: `message-bus-design.md`, `boardroom-data-contracts.md`.

## Status
- Draft
- Date: 2026-03-28
- Scope: controlled multi-role alignment subworkflow inside the workflow bus

## 1. Positioning

`Meeting Room Protocol` is a controlled exception to the standard Ticket flow.

It exists for one purpose only: solve high-coupling, cross-role alignment problems faster and more reliably than repeated serial retries.

It is not:

- a persistent group chat
- a default collaboration mode
- a bypass around the event bus
- a place where agents keep long-lived private memory
- a backdoor for writing uncontrolled state

The normal path remains:

- CEO creates tickets
- workers execute atomically
- results return through the bus

The Meeting Room should open only when normal Ticket flow is likely to waste more budget than a short, bounded alignment session.

## 2. Design Goal

The protocol should:

- resolve interface and ownership conflicts across roles
- turn transient discussion into durable structured consensus
- keep token cost bounded
- preserve auditability
- prevent endless debate loops
- hand control back to the main bus immediately after alignment

## 3. Typical Use Cases

Recommended cases:

- UI designer, frontend engineer, and backend architect need to align on an API contract
- implementation cost and interaction design are in direct conflict
- test strategy and architecture constraints are producing repeated rework
- multiple serial tickets have failed because the issue is cross-functional rather than local
- CEO needs a bounded design-review room before issuing the next wave of tickets

Do not use it for:

- ordinary task decomposition
- broad brainstorming with unclear scope
- single-owner decisions that one role can make alone
- work that should go directly to Board review
- replacing normal implementation or testing tickets

## 4. Entry Conditions

The runtime should allow `MEETING_ROOM_REQUESTED` only when at least one of the following is true:

1. Two or more roles have conflicting constraints on the same node or artifact family.
2. The same node family has repeated retry or rework signals, and the root cause spans multiple roles.
3. A contract decision is required before downstream tickets can be created safely.
4. CEO explicitly decides that bounded alignment is cheaper than more serial retries.
5. Board or governance policy explicitly demands a cross-role design review before continuation.

The runtime should reject opening a meeting when:

- the topic is not decision-bounded
- required input artifacts are missing
- a Board-only decision is being disguised as a meeting
- the same unresolved topic has already exceeded its reopen policy

## 5. Control Plane Model

The Meeting Room is modeled as a temporary child workflow or special coordination node.

It has:

- a `meeting_id`
- a parent `workflow_id`
- a bounded topic
- a fixed participant set
- fixed input references
- fixed budget limits
- a required output schema
- a designated recorder

The meeting room can write only meeting-scoped artifacts until it closes. It cannot directly mutate production state, merge code, or mark delivery milestones complete.

Its durable outputs are:

- typed meeting events
- a `Consensus_Document`
- optional follow-up ticket proposals

## 6. Event Types

Recommended event set:

- `MEETING_ROOM_REQUESTED`
- `MEETING_ROOM_OPENED`
- `MEETING_PARTICIPANTS_LOCKED`
- `MEETING_ROUND_STARTED`
- `MEETING_ROUND_COMPLETED`
- `MEETING_BUDGET_WARNING`
- `MEETING_CONSENSUS_SUBMITTED`
- `MEETING_NO_CONSENSUS`
- `MEETING_ROOM_CLOSED`

Optional governance events:

- `MEETING_REOPEN_REQUESTED`
- `MEETING_REOPEN_REJECTED`
- `MEETING_TRANSCRIPT_PURGED`

## 7. State Machine

Recommended lifecycle:

```text
REQUESTED
  -> OPEN
  -> IN_ROUND
  -> CONSENSUS_SUBMITTED
  -> CLOSED

REQUESTED
  -> OPEN
  -> IN_ROUND
  -> NO_CONSENSUS
  -> CLOSED
```

State meanings:

- `REQUESTED`: waiting for reducer validation and room creation
- `OPEN`: topic, participants, recorder, and budget are locked
- `IN_ROUND`: structured discussion is actively running
- `CONSENSUS_SUBMITTED`: recorder has produced a valid `Consensus_Document`
- `NO_CONSENSUS`: budget exhausted or deadlock reached without acceptable convergence
- `CLOSED`: runtime has persisted outcome and destroyed ephemeral room context

Reducer guards:

- a closed room cannot emit new discussion rounds
- participant list cannot mutate after `OPEN` unless the room is closed and reopened
- consensus submission must pass schema validation
- if limits are exceeded before consensus, runtime must emit `MEETING_NO_CONSENSUS`

## 8. Participant Rules

Participant rules should be strict:

- recommended participant count: `2-4`
- hard cap: `6`
- every participant must have a declared role and reason for attendance
- at least one participant should represent implementation constraints
- at least one participant should represent user-facing or product-facing constraints when relevant
- one participant must be assigned as `recorder`
- CEO may sponsor the meeting, but should not always be a participant

Behavioral constraints:

- participants only receive the compiled meeting package, not arbitrary global memory
- each statement must stay inside the declared topic
- unsupported claims should reference input artifacts, prior tickets, or explicit assumptions
- participants cannot directly create production artifacts outside the allowed meeting write-set
- participants cannot continue chatting after the room is closed

## 9. Compiled Meeting Package

Workers should not enter the room from raw references alone. Runtime should compile a closed meeting package similar to a ticket execution package.

Suggested structure:

```json
{
  "meta": {
    "meeting_id": "mtg_...",
    "workflow_id": "wf_...",
    "topic": "Homepage API contract alignment",
    "opened_by": "ceo_main"
  },
  "participants": [
    {
      "employee_id": "emp_frontend_1",
      "role": "frontend_engineer",
      "meeting_responsibility": "implementation feasibility"
    }
  ],
  "inputs": {
    "artifact_refs": ["art_..."],
    "ticket_refs": ["tkt_..."],
    "constraint_refs": ["constraints_v3"]
  },
  "governance": {
    "max_rounds": 5,
    "max_total_turns": 12,
    "max_total_tokens": 12000,
    "wall_clock_timeout_sec": 600,
    "reopen_budget": 1
  },
  "output_schema_ref": "consensus_document_v1",
  "recorder_id": "emp_architect_1"
}
```

## 10. Structured Round Protocol

Meeting Room should prefer structured rounds over open argument.

Recommended sequence:

1. `Position Round`
   - each participant states goal, hard constraints, preferred direction
2. `Challenge Round`
   - each participant questions hidden assumptions and identifies risks
3. `Proposal Round`
   - participants propose one or more concrete convergent options
4. `Convergence Round`
   - room compares options, merges compatible proposals, and identifies likely decision
5. `Closing Round`
   - recorder summarizes accepted points, rejected options, unresolved items, and follow-up work

Default rules:

- one substantive turn per participant per round
- optional single clarification turn only if budget allows
- no new topic introduction after `Proposal Round`
- if a participant repeats prior points without adding evidence or tradeoffs, runtime may truncate the turn

## 11. Budget Policy

The protocol is only valuable if it is cheaper than repeated serial rework.

Recommended default limits:

- `max_rounds = 5`
- `max_total_turns = 12`
- `participant_count <= 4`
- `wall_clock_timeout_sec = 600`
- `reopen_budget = 1`

Budget dimensions to track:

- total tokens consumed
- total turns consumed
- elapsed time
- reopen count for the same topic family

When any hard limit is reached before valid consensus:

- stop discussion
- emit `MEETING_NO_CONSENSUS`
- attach budget snapshot
- escalate under policy

## 12. Consensus_Document

The room exists to produce a structured decision artifact, not to preserve chat.

Required schema:

```json
{
  "meta": {
    "meeting_id": "mtg_...",
    "workflow_id": "wf_...",
    "topic": "string",
    "created_at": "2026-03-28T01:00:00+08:00",
    "recorder_id": "emp_..."
  },
  "participants": [
    {
      "employee_id": "emp_...",
      "role": "frontend_engineer",
      "stance_summary": "string"
    }
  ],
  "inputs": {
    "artifact_refs": ["art_..."],
    "ticket_refs": ["tkt_..."],
    "constraint_refs": ["constraints_v3"]
  },
  "considered_options": [
    {
      "option_id": "A",
      "summary": "string",
      "pros": ["string"],
      "cons": ["string"],
      "rejected_reason": "string"
    }
  ],
  "consensus": {
    "status": "CONSENSUS|PARTIAL|NONE",
    "selected_option_id": "A",
    "rationale": "string",
    "dissent_summary": ["string"],
    "unresolved_questions": ["string"]
  },
  "contracts": {
    "api_contracts": ["string"],
    "ui_contracts": ["string"],
    "data_contracts": ["string"],
    "ownership_assignments": [
      {
        "owner": "frontend_engineer",
        "responsibility": "string"
      }
    ]
  },
  "follow_up": {
    "recommended_tickets": [
      {
        "role": "frontend_engineer",
        "task": "string"
      }
    ],
    "needs_ceo_action": true,
    "needs_board_review": false
  },
  "governance": {
    "rounds_used": 4,
    "tokens_used": 8200,
    "budget_exhausted": false
  }
}
```

Validation rules:

- missing required fields means the meeting did not produce a valid outcome
- only a schema-valid consensus document may emit `MEETING_CONSENSUS_SUBMITTED`
- follow-up tickets still need normal reducer validation after the meeting

## 13. No-Consensus Escalation

If the room cannot converge, the system should fail explicitly instead of extending the meeting indefinitely.

Triggers for `MEETING_NO_CONSENSUS`:

- round cap reached
- token cap reached
- wall-clock timeout reached
- direct contradiction remains on a critical contract
- recorder cannot produce a schema-valid document

Escalation policy:

1. emit `MEETING_NO_CONSENSUS`
2. close the room
3. attach summary, unresolved points, and budget snapshot
4. wake CEO
5. CEO chooses one of:
   - split the problem into smaller tickets
   - replace or add participants
   - escalate to Board if the unresolved point is strategic, visual, budgetary, or irreversible
   - cancel the branch

Important rule:

- the same topic should not loop through unlimited reopen cycles
- reopening requires a new cause, new evidence, or changed participants

## 14. Audit and Retention

The system should retain durable summary, not permanent free-chat logs.

Durable records:

- event history
- participant list
- meeting package hash
- budget snapshot
- `Consensus_Document`
- transcript hash or compressed audit digest

Ephemeral records:

- full turn-by-turn transcript
- temporary scratch notes

Retention guidance:

- default: purge full transcript after room closure and digest persistence
- keep digest and hashes for replay and dispute tracing
- preserve full transcript only for incident investigation, policy audit, or explicit Board requirement

This keeps the room auditable without turning it into hidden long-term memory.

## 15. Relation to Main Ticket Bus

The Meeting Room must remain subordinate to the main bus.

Rules:

- meetings are opened by bus events, not ad hoc chat
- meeting inputs come from tickets, artifacts, and constraints already in the system
- meeting outputs return to the bus as events plus `Consensus_Document`
- actual implementation returns to normal ticket execution after the room closes
- Board Gate remains separate; a meeting cannot replace required Board approval

Recommended integration pattern:

1. CEO or runtime detects high-coupling conflict
2. `MEETING_ROOM_REQUESTED`
3. reducer validates entry conditions
4. runtime opens room and dispatches compiled meeting package
5. room produces consensus or no-consensus outcome
6. CEO consumes result and issues normal follow-up tickets or escalation

## 16. Final Position

The Meeting Room has clear implementation value, but only as a bounded coordination primitive.

If it becomes a default collaboration mode, the framework will regress into:

- hidden chat state
- poor auditability
- unstable cost
- repeated discussion loops

If it stays constrained, it becomes useful for exactly the class of problems where serial tickets are too slow and plain retries are too dumb.
