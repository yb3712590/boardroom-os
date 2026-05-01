# Round 7B Capability-driven Assignment Design

## Goal

Round 7B migrates scheduler assignment eligibility from role/employee matching to actor capability eligibility, inheriting Round 7A's independent actor registry and RoleTemplate -> Capability contract. The runtime scheduler must select from active actors whose capability set satisfies the ticket's required capabilities, then either lease the selected actor through the existing lease event path or emit an explicit no-eligible diagnostic.

## Boundaries

In scope:

- Add a focused assignment resolver consumed by the scheduler.
- Treat `role_profile_ref` only as a migration-time input for compiling required capabilities before resolver execution.
- Define scoped exclusion semantics for legacy `excluded_employee_ids` and new scoped exclusions.
- Prevent retry/rework from copying unscoped exclusions across unrelated dispatch attempts.
- Upgrade the existing scheduler diagnostic event payload for no eligible actor.
- Update Round 7B planning docs and tests.

Out of scope:

- Do not introduce final Assignment/Lease split events; Round 7C owns that.
- Do not change closeout, fanout, or rework progression policy.
- Do not add role-name, ticket-summary, hardcoded employee-id, or role fallback dispatch paths.

## Architecture

Add a small core resolver module that receives explicit scheduler inputs and returns either a selected actor or a diagnostic. The resolver input is:

- required ticket capabilities;
- actor projections from the actor registry;
- actor status;
- provider health/circuit-breaker state;
- currently active leases;
- scoped exclusion policy.

`ticket_handlers.run_scheduler_tick()` remains the orchestration layer: it loads ready tickets, checks existing dependency/precondition gates, builds resolver input, calls the resolver, and writes either `EVENT_TICKET_LEASED` or `EVENT_SCHEDULER_LEASE_DIAGNOSTIC_RECORDED`. The resolver must not inspect `role_profile_ref`, employee role refs, ticket summaries, or role names for eligibility.

## Capability Compilation

Ticket required capabilities are resolved before calling the resolver:

1. Prefer a new/explicit required capability list when present on the ticket execution contract.
2. If the legacy execution contract only has runtime provider `required_capability_tags`, map the ticket's execution target to the corresponding RoleTemplate capability contract.
3. If historical ticket data only has `role_profile_ref` + `output_schema_ref`, compile required capabilities using the existing RoleTemplate -> Capability contract.

This is a migration read boundary only. The compiled capabilities become resolver input; `role_profile_ref` does not participate in runtime eligibility.

## Scoped Exclusion Semantics

New scoped exclusions are normalized into entries with:

- `actor_id` / legacy `employee_id` mapped to the same runtime identity string used by current leases;
- `scope`: `attempt`, `ticket`, `node`, `capability`, or `workflow`;
- optional `ticket_id`, `node_id`, `capability`, and `workflow_id` match keys;
- `reason` and optional `source` metadata.

Legacy `excluded_employee_ids` is interpreted as ticket-scoped only for the current ticket payload. It is not copied wholesale to retry or rework follow-up tickets. Rework may add a scoped exclusion for the maker that completed the rejected delivery, but that exclusion must be limited to the rework ticket/capability context instead of poisoning unrelated tickets or future nodes.

## No Eligible Actor Output

Round 7B uses the existing `EVENT_SCHEDULER_LEASE_DIAGNOSTIC_RECORDED` event and upgrades its payload:

- `reason_code`: `NO_ELIGIBLE_ACTOR`;
- `required_capabilities`;
- `candidate_summary`;
- `candidate_details` with actor id, status, capabilities, provider id, provider paused flag, busy flag, exclusion matches, missing capabilities, and final eligibility;
- `suggested_actions`: `CREATE_ACTOR`, `REASSIGN_EXECUTOR`, `REQUEST_HUMAN_DECISION`, `BLOCK_NODE_NO_CAPABLE_ACTOR`.

This satisfies explicit action/incident-payload requirements without introducing Phase 4 incident policy changes.

## Testing

Tests must prove:

- a ready ticket is leased to an active actor with the required capabilities;
- an actor without required capabilities is not eligible even if legacy role/profile data would have matched;
- scoped exclusions apply only to matching attempt/ticket/node/capability/workflow scope;
- retry/rework does not propagate legacy unscoped exclusion pollution;
- no eligible actor produces the upgraded scheduler diagnostic payload and does not silently stall;
- grep confirms scheduler/controller/ticket handler did not gain role-name-to-execution-key fallback branches.

## Documentation Updates

Update:

- `doc/refactor/planning/06-actor-role-lifecycle.md` with 7B implementation status and scoped exclusion semantics;
- `doc/refactor/planning/09-refactor-plan.md` with completed 7B tasks and 7C dependency on lease separation;
- `doc/refactor/planning/10-refactor-acceptance-criteria.md` only for Phase 3 items backed by tests/grep.
