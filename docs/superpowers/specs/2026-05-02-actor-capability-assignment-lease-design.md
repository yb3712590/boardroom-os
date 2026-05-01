# Phase 3 Actor / Capability / Assignment / Lease Runtime Design

## Goal

Migrate runtime execution identity from role templates to an actor/capability/assignment/lease model for Phase 3 acceptance.

Runtime dispatch must answer four separate questions:

1. Which actor is eligible to do this work?
2. Which actor was selected for this ticket?
3. Which actor currently owns the execution window?
4. Which provider/model was preferred and actually used?

Employee and role template language remains product/governance vocabulary. Runtime selection uses actor state and required capabilities.

## Confirmed design choices

- Add persistent projections for actor, assignment, and lease.
- In the first implementation, `actor_id == employee_id` for compatibility with worker APIs, workforce UI, and existing command payloads.
- Keep `role_profile_ref` in ticket and employee payloads as product/governance metadata, but do not use it as the runtime execution key.
- Preserve existing ticket projection fields such as `lease_owner` as compatibility views backed by actor/lease state.

## Architecture

### Actor registry

Add an `actor_projection` rebuilt from lifecycle events.

Minimum fields:

- `actor_id`
- `employee_id`
- `status`: `ACTIVE`, `SUSPENDED`, `DEACTIVATED`, `REPLACED`
- `capability_tags_json`
- `provider_binding_refs_json` or provider preference metadata
- `source_role_profile_refs_json`
- `replacement_actor_id`
- `deactivated_reason`
- `updated_at`
- `version`

Existing employee lifecycle events drive actor state:

- `EMPLOYEE_HIRED` creates/enables an `ACTIVE` actor.
- `EMPLOYEE_FROZEN` suspends the actor.
- `EMPLOYEE_RESTORED` reactivates the actor.
- `EMPLOYEE_REPLACED` marks the old actor `REPLACED` and links `replacement_actor_id`.

This gives runtime a replayable actor registry without changing external worker identity yet.

### Role template and capability mapping

Role templates can only provide capability defaults. Runtime dispatch consumes `execution_contract.required_capability_tags` and actor `capability_tags_json`.

Allowed:

- `role_profile_ref` -> capability mapping in a catalog/helper.
- Ticket creation filling `execution_contract` from role template or output schema when needed.

Not allowed in runtime execution paths:

- role name -> selected worker
- role name -> write root
- role name -> provider execution key

Provider binding should move toward capability or execution target preferences. Legacy `role_profile:*` provider bindings can be accepted only as compatibility lookup candidates, not as the primary runtime identity.

### Assignment projection

Add `ticket_assignment_projection` rebuilt from a new `TICKET_ASSIGNED` event.

Minimum fields:

- `assignment_id`
- `ticket_id`
- `workflow_id`
- `node_id`
- `actor_id`
- `required_capability_tags_json`
- `selection_reason`
- `eligibility_snapshot_json`
- `excluded_actor_ids_json`
- `exclusion_scope_json`
- `preferred_provider_id`
- `preferred_model`
- `created_at`
- `status`
- `version`

Assignment means “this actor was selected for this ticket.” It does not grant execution ownership.

### Lease projection

Add `ticket_lease_projection` rebuilt from `TICKET_LEASED`, `TICKET_STARTED`, terminal ticket events, and timeout events.

Minimum fields:

- `lease_id`
- `assignment_id`
- `ticket_id`
- `workflow_id`
- `node_id`
- `actor_id`
- `lease_status`: `LEASED`, `EXECUTING`, `RELEASED`, `TIMED_OUT`, `FAILED`
- `lease_expires_at`
- `actual_provider_id`
- `actual_model`
- `fallback_reason`
- `provider_selection_reason`
- `started_at`
- `released_at`
- `updated_at`
- `version`

Lease means “this actor owns the execution window until expiry or release.” Lease expiry must not delete assignment history.

## Dispatch flow

1. Read dispatchable ticket and its `execution_contract.required_capability_tags`.
2. Normalize exclusions into scoped actor exclusions.
3. Build eligible actor list from `actor_projection`:
   - status is `ACTIVE`
   - required capability tags are present
   - actor is not busy under current active leases
   - actor is not excluded in the relevant scope
   - provider is available for the selected preference
4. If `dispatch_intent.assignee_employee_id` exists, treat it as `actor_id` and validate the same eligibility rules.
5. Emit `TICKET_ASSIGNED` with selected actor, capability requirements, exclusion scope, eligibility snapshot, and preferred provider/model.
6. Emit `TICKET_LEASED` with `lease_id`, `assignment_id`, `actor_id`, expiry, and actual provider/model selection.
7. Keep `ticket_projection.lease_owner = actor_id` for compatibility.

## Replacement behavior

Replacement is not a new hire shortcut.

When an actor is replaced:

- Old actor status becomes `REPLACED` and must not be eligible for new assignments.
- New actor may inherit capability eligibility through role template/capability mapping.
- New actor does not inherit old assignments or leases.
- Active old-actor work is handled by existing staffing containment/retry paths or lease timeout; any new work requires a new assignment and lease.

## Scoped exclusions

Keep the old `excluded_employee_ids` field as input compatibility, but normalize it before dispatch.

New structured exclusion shape should include:

- `actor_id`
- `scope`: `attempt`, `ticket`, `node`, `capability`, or `workflow`
- `capability_tags` when scope is capability-specific
- `source_ticket_id`
- `source_event_id` or reason

Rules:

- `attempt` only affects the current attempt.
- `ticket` only affects retries of the same ticket lineage.
- `node` affects the current graph node.
- `capability` affects matching capability tags.
- `workflow` requires an incident or explicit containment reason.

Unscoped copying from maker/checker retry or rework into unrelated future tickets is not allowed.

## No eligible actor handling

No eligible actor must produce explicit runtime evidence, not a silent stall.

The scheduler should emit a structured action or incident with:

- ticket and node identity
- required capabilities
- candidate actors considered
- why each candidate was ineligible
- scoped exclusions applied
- recommended follow-up: create actor, reassign executor, request human decision, or block node for no capable actor

Existing lease diagnostics can remain, but they are not sufficient unless surfaced as an explicit action/incident contract.

## Provider metadata

Preferred and actual provider/model must be present across assignment, lease/attempt, and result evidence.

- Assignment records preferred provider/model and selection policy.
- Lease records actual provider/model selected for the execution window.
- Provider attempt projection already records provider attempt lineage and should remain the attempt-level evidence source.
- Ticket result/provider audit evidence must preserve `preferred_provider_id`, `preferred_model`, `actual_provider_id`, `actual_model`, `selection_reason`, `policy_reason`, and fallback reason.
- Field names should align with provider smoke output.

## Compatibility boundaries

Do not rename external worker commands in Phase 3.

- `TicketLeaseCommand.leased_by`, `TicketStartCommand.started_by`, `TicketResultSubmitCommand.submitted_by`, and worker session IDs stay accepted as employee IDs.
- Runtime internals interpret those values as actor IDs.
- Workforce UI can still display employees and role lanes, but should source runtime availability from actor/lease projections where needed.

## Test plan

Add or update backend tests for:

1. Actor enable/suspend/deactivate/replace lifecycle projection.
2. Replaced actor is not eligible; replacement actor does not inherit old lease.
3. RoleTemplate maps to capability only and is not a runtime execution key.
4. Assignment and lease are separate projections; lease expiry does not delete assignment.
5. Scoped `excluded_employee_ids` does not pollute unrelated dispatch.
6. No eligible actor produces explicit action or incident.
7. Provider preferred/actual fields are recorded on assignment, lease/attempt, and result evidence.
8. Grep/audit confirms no role name -> write root or role name -> execution key branches remain in runtime, scheduler, provider selection, or write-surface paths.

## Acceptance impact

This design satisfies Phase 3 by making actor lifecycle replayable, dispatch capability-driven, assignment and lease independently testable, no-worker stalls explicit, and provider preferred/actual metadata traceable.
