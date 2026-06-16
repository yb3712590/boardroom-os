# V2-100 Agent-team Rework Loop Hardening Spec

## Status

- Stage: V2-100
- State: proposed implementation spec
- Input: V2-090K fail-closed golden-sample rerun, especially `examples/generated-workspaces/tiny-fullstack/30-audit/v2-090k-failure-snapshot/`
- Output: typed rework loop, multi-role graph patch governance, re-evidence/re-check/re-closeout pipeline, proving scenario

## Decision

V2-100 is the correct next stage, but it must not be implemented as “CEO alone reviews and updates the ticket graph”.

The safe design is:

```text
Verified blocker / closeout failure
  -> ReworkRequest
  -> CEO ReworkPlan + TicketGraphPatch proposal
  -> Architect / Checker / Tester / Release DevOps domain reviews
  -> GraphPatchReviewGate
  -> governance command handler appends commit event after reducer/validator checks
  -> Worker / Tester / Release DevOps execute rework tickets
  -> EvidenceVerifier / SourceInventory / FinalEvidenceTable / Checker re-run
  -> CloseoutGate re-run
  -> accepted, next rework cycle, or explicit escalation/exhaustion
```

CEO is the accountable planner, not the only graph authority. Graph mutation is committed only through a typed governance command that passes reducer/validator checks. Runtime and atomic-agent remain fact executors, not governance decision makers.

## Why V2-100 is necessary

V2-090K achieved the right fail-closed behavior: the system no longer hides agent-generated inconsistencies behind helper-written verdicts or fixed runner assumptions. The recorded failure snapshot shows autonomy-relevant gaps:

1. `probe-response-shape-mismatch`: the behavioral probe expected fields such as `$.title` / `$.id`, while the backend returned a nested response shape like `{"ok": true, "book": {...}, "id": ...}`.
2. `env-binding-not-converged`: the RunManifest and implementation disagreed about environment variable names.
3. `final-evidence-uses-old-acceptance-refs`: final evidence referenced stale `AC-TINY-*` rather than active generated acceptance refs.
4. `closeout-audit-references-old-run`: closeout and audit materials referenced an old run.

These are not single-role problems. They cross contract design, implementation, behavioral testing, run configuration, evidence projection, and closeout audit. Therefore the next stage must prove multi-role rework governance.

## Non-goals

V2-100 does not require the first full run to pass. It requires the system to handle a failed run autonomously and safely.

V2-100 must not add a runner helper that silently fixes agent outputs, rewrites contracts, patches probes, or writes checker/closeout verdicts.

V2-100 must not make provider intelligence the only safety mechanism. GPT-5.5 quality helps planning and repair, but autonomy still needs typed contracts, typed events, reducer permissions, evidence gates, and auditable role separation.

## Core invariants

### Invariant 1: blocker-first rework

A ReworkRequest can only be created from at least one verified source:

- FinalEvidenceTable missing row.
- FinalEvidenceTable failed row.
- CheckerVerdict blocker.
- CloseoutGate failure.
- RunManifest / service / behavioral probe failure that is mapped to an active contract or evidence obligation.

RunManifest, service, or behavioral probe failures are not allowed to open rework directly from runtime output. They must first be projected by EvidenceVerifier, Checker, CloseoutGate, or an equivalent governance adapter into a verified blocker source.

Free-text notes, exceptions, provider confidence, or reviewer comments are not enough.

### Invariant 2: CEO proposes, reducer commits

CEO may propose:

- ReworkPlan.
- TicketGraphPatch.
- Rework termination or escalation rationale.

CEO may not directly mutate graph state. All graph state changes pass through typed events and reducer validation.

### Invariant 3: graph patches require typed multi-role review

A TicketGraphPatch must satisfy the GraphPatchReviewGate before it can be committed.

Required review domains:

| Domain | Default reviewer | Required when | Main question |
|---|---|---|---|
| `planning` | CEO | Always | Does the patch address project scope, blocker routing, and rework decision? |
| `structural` | Architect | Always | Does the patch preserve graph, contract, dependency, source-surface, and allowed-write-set invariants? |
| `blocker_coverage` | Checker | Always | Does every blocker have a mapped rework target or explicit escalation? |
| `behavioral_probe` | Tester | When behavior, API shape, integration, or acceptance probe is involved | Does the patch fix the right side of contract/probe/implementation mismatch? |
| `run_env_readiness` | Release DevOps | When RunManifest, env, service startup, readiness, frontend/backend topology, or sample promotion is involved | Can the patch be run and audited using declared commands and env bindings? |
| `closeout_fact_chain` | Closeout or Checker | When closeout/audit/fact-chain materials are affected | Does the patch prevent stale run refs, stale evidence, and cross-run closeout reuse? |

### Invariant 4: each rework attempt re-enters all gates

A ReworkAttempt is not accepted by “changed files exist” or “provider said completed”. It must re-enter:

- SourceInventory.
- EvidenceVerifier.
- FinalEvidenceTableBuilder.
- CheckerService.
- CloseoutGate when the rework affects closeout readiness.
- Replay/process/git audit when the run is promoted.

### Invariant 5: stale evidence is always suspect

The following are invalid as acceptance evidence for a new rework round unless they are explicitly re-derived in the new round:

- Old FinalEvidenceTable satisfied rows.
- Old Checker approved verdicts.
- Old CloseoutPackage passed state.
- Old run ids in closeout/audit references.
- Old SourceInventory not tied to the new source lineage.
- Old RunManifest not tied to the new graph/package contract.

### Invariant 6: termination is explicit

Rework budget exhaustion, repeated same blocker, impossible contract conflict, or missing provider capability must produce an explicit ReworkTerminationDecision:

- `accepted`
- `escalated_human_review`
- `exhausted_budget`
- `blocked_by_missing_contract`
- `blocked_by_provider_capability`
- `blocked_by_untrusted_evidence`

No infinite loop and no silent downgrade.

### Invariant 7: manifest ambiguity becomes rework context

RunManifest / BehavioralProbePlan（运行清单 / 行为探针计划） ingestion must not treat provider-produced assertion vocabulary as a closed success protocol. Unknown, variant, or ambiguous assertion types must not raw-crash the run, must not be silently ignored, and must not count as passed evidence.

The framework should preserve raw assertion payloads and manifest skeleton context, then pass them to Tester / Release DevOps（测试 / 发布运维） as inputs for provider-backed BlackboxVerificationPlan（黑盒验证计划） generation. The runner executes that agent-owned plan and records real command / HTTP / browser / tool facts（命令 / HTTP / 浏览器 / 工具事实）. It must not synthesize business probes, default endpoints, or hidden assertions. Closeout may pass only after active behavior claims are proven by real evidence; otherwise failure should become ReworkRequest（返工请求） context or explicit escalation.

## Work package overview

```text
V2-100A Rework domain model
  -> typed blocker/request/issue/plan/attempt/outcome/termination objects

V2-100B Rework events + reducer + GraphPatchReviewGate
  -> event taxonomy, actor permissions, graph patch review policy, replayable projection

V2-100C Multi-role rework planner boundary
  -> CEO plan proposal, Architect/Checker/Tester/Release DevOps reviews, graph patch creation

V2-100D Rework evidence/checker/closeout reintegration
  -> re-run evidence, source inventory, final evidence table, checker, closeout, stale-evidence rejection

V2-100E Multi-round proving scenario
  -> consume 090K failure snapshot and resettable failing fixture; prove accepted or escalated path

V2-100F RunManifest tolerant ingestion and rework entry
  -> preserve raw assertions, route RunManifest ambiguity into Tester / Release DevOps blackbox planning, execute agent-owned plans, and project failures into rework context
```

## Shared typed model vocabulary

The exact field names may be refined during implementation, but the following objects must exist as first-class, Pydantic/frozen typed models.

### BlockerReport

Purpose: normalize blocker sources before ReworkRequest creation.

Required fields:

- `blocker_report_id`
- `run_id`
- `source_kind`: `final_evidence_table | checker_verdict | closeout_gate | run_manifest | behavioral_probe | process_audit | replay_bundle`
- `source_ref`
- `contract_refs`
- `acceptance_refs`
- `package_contract_ref`
- `run_manifest_ref`
- `blockers`
- `created_at`

Validation:

- Must reference a current run.
- Must reference active contracts when acceptance/package claims are involved.
- Must not be created from notes-only material.

### ReworkIssue

Purpose: one concrete issue to be addressed.

Required fields:

- `issue_id`
- `blocker_refs`
- `issue_code`
- `severity`: `blocking | escalation_required`
- `acceptance_refs`
- `source_surface_refs`
- `run_manifest_refs`
- `evidence_obligation_refs`
- `observed_fact_refs`
- `expected_fact_refs`
- `suspected_domains`: `contract | implementation | probe | run_env | evidence_projection | closeout_audit | graph`
- `required_artifact_types`
- `description`

V2-100A first defines the normative `ReworkIssueCode` set used by blocker projection. Later V2-100 work packages may add codes only through spec and acceptance update:

- `final_evidence_missing`
- `final_evidence_failed`
- `checker_blocker`
- `contract_mismatch`
- `work_product_mismatch`
- `invalid_checker_input`
- `closeout_gate_failure`
- `run_manifest_mismatch`
- `probe_response_shape_mismatch`
- `env_binding_not_converged`
- `final_evidence_old_acceptance_refs`
- `closeout_audit_old_run_refs`

Validation:

- Must map to at least one blocker.
- Must identify at least one affected domain.
- Must not use stale acceptance refs.

### ReworkRequest

Purpose: governance input to planning.

Required fields:

- `rework_request_id`
- `cycle_id`
- `run_id`
- `request_source_refs`
- `issues`
- `requested_by_actor`
- `requested_at`
- `active_contract_refs`
- `active_graph_version`

Validation:

- Must contain at least one ReworkIssue.
- Every issue must originate from a verified blocker source.
- `requested_by_actor` can be Checker, CloseoutGate, GraphPatchReviewGate, or a governance adapter; not runtime/executor alone.

### ReworkPlan

Purpose: CEO-owned route for rework.

Required fields:

- `rework_plan_id`
- `cycle_id`
- `rework_request_id`
- `planner_actor`: CEO role profile ref
- `planner_attempt_ref`: provider attempt ref
- `decisions`
- `ticket_graph_patch_ref`
- `risk_notes`
- `stop_or_escalation_conditions`

Allowed decision kinds:

- `fix_implementation`
- `fix_contract_or_probe`
- `split_ticket`
- `reorder_dependencies`
- `narrow_scope`
- `escalate_human_review`

Validation:

- Every decision maps to one or more `blocker_refs` and `issue_ids`.
- Every non-escalation decision maps to target tickets or graph patch operations.
- Runtime/atomic-agent cannot be planner.
- Plan cannot mark any blocker closed.

### TicketGraphPatch

Purpose: proposed graph mutations.

Required fields:

- `ticket_graph_patch_id`
- `base_graph_version`
- `proposed_by_plan_ref`
- `operations`
- `affected_ticket_refs`
- `affected_contract_refs`
- `affected_source_surface_refs`
- `required_review_domains`
- `patch_hash`

Allowed operation kinds:

- `create_rework_ticket`
- `split_ticket`
- `update_dependencies`
- `narrow_allowed_write_set`
- `append_evidence_obligation`
- `mark_ticket_blocked_by_rework`
- `request_contract_or_probe_revision`
- `escalate_without_graph_change`

Disallowed operation kinds:

- direct source edits
- direct evidence approval
- direct checker approval
- direct closeout approval
- direct ticket completion
- hidden allowed_write_set expansion

### GraphPatchReview

Purpose: typed review by a role over a domain.

Required fields:

- `graph_patch_review_id`
- `ticket_graph_patch_ref`
- `review_domain`
- `reviewer_actor`
- `reviewer_role_kind`
- `reviewer_attempt_ref`
- `status`: `approved | rejected | needs_changes | abstained_not_applicable`
- `checked_invariants`
- `blockers`
- `non_blocking_notes`
- `created_at`

Validation:

- Reviewer role kind must match review domain.
- Rejection must include blockers.
- Approval must list checked invariants.
- `abstained_not_applicable` is only valid for conditional domains not required by the patch.

### GraphPatchApprovalSet

Purpose: aggregate graph patch reviews before reducer commit.

Required fields:

- `approval_set_id`
- `ticket_graph_patch_ref`
- `required_domains`
- `reviews`
- `status`: `ready_to_commit | rejected | incomplete`
- `computed_at`

Validation:

- Always requires CEO planning, Architect structural, Checker blocker coverage.
- Requires Tester if the patch touches behavior/probes/contracts with user-facing behavior.
- Requires Release DevOps if the patch touches run/env/readiness/topology/sample promotion.
- Requires Closeout/Checker fact-chain review if the patch touches closeout/audit material.

### ReworkAttempt

Purpose: record one execution round of a rework ticket.

Required fields:

- `rework_attempt_id`
- `cycle_id`
- `rework_plan_ref`
- `ticket_ref`
- `execution_package_ref`
- `actor_ref`
- `provider_attempt_refs`
- `workspace_mutation_refs`
- `command_evidence_refs`
- `source_lineage_refs`
- `run_manifest_ref`
- `submitted_at`

Validation:

- Must be tied to a reducer-committed rework ticket.
- Must not be accepted without source lineage and required evidence.
- Must not mutate files outside allowed_write_set.

### ReworkOutcome

Purpose: reviewer outcome after an attempt.

Required fields:

- `rework_outcome_id`
- `rework_attempt_ref`
- `final_evidence_table_ref`
- `source_inventory_ref`
- `checker_verdict_ref`
- `closeout_gate_ref` when applicable
- `status`: `accepted | rework_required | escalated | exhausted`
- `remaining_blocker_refs`
- `accepted_blocker_refs`
- `created_at`

Validation:

- `accepted` requires no remaining blockers for targeted issues.
- `accepted` requires new evidence for the current round.
- `rework_required` requires remaining blockers.
- `exhausted` requires budget/loop proof.

## Event taxonomy

Add or formalize the following typed events.

| Event | Actor allowed | Purpose |
|---|---|---|
| `REWORK_REQUESTED` | Checker / CloseoutGate / governance adapter | Opens a cycle from verified blockers. |
| `REWORK_PLANNED` | CEO | Records ReworkPlan proposal, not graph commit. |
| `GRAPH_PATCH_PROPOSED` | CEO | Records TicketGraphPatch proposal. |
| `GRAPH_PATCH_REVIEWED` | Architect / Checker / Tester / Release DevOps / Closeout | Records domain review. |
| `GRAPH_PATCH_ACCEPTED` | Governance command handler after reducer/validator approval-set checks | Authorizes graph patch application. |
| `REWORK_TICKET_CREATED` | Governance command handler after reducer/validator checks | Creates reducer-approved rework ticket. |
| `REWORK_ATTEMPT_STARTED` | Runtime/executor | Records execution start only. |
| `REWORK_ATTEMPT_SUBMITTED` | Runtime/executor | Records factual submission only. |
| `REWORK_REVIEWED` | Checker / EvidenceVerifier / CloseoutGate adapter | Records revalidation outcome. |
| `REWORK_ACCEPTED` | Governance command handler after checker/closeout gates and reducer/validator checks | Closes targeted issues. |
| `REWORK_ESCALATED` | Governance command handler after CEO decision and reducer/validator checks | Escalates unresolved issue. |
| `REWORK_EXHAUSTED` | Governance command handler after reducer/validator budget checks | Terminates after budget/loop exhaustion. |

Runtime and executor can only emit started/submitted factual events. They cannot emit accepted, escalated, exhausted, graph accepted, or ticket completed events.

## Actor permission matrix

| Actor | May propose plan | May review graph patch | May commit graph patch | May execute ticket | May submit evidence | May approve blocker closure | May closeout |
|---|---:|---:|---:|---:|---:|---:|---:|
| CEO | yes | planning only | no | no | no | no | no |
| Architect | no | structural | no | no | no | no | no |
| Worker | no | no | no | yes | implementation evidence only | no | no |
| Tester | no | behavioral/test domain | no | yes for test/probe tickets | test evidence only | no | no |
| Release DevOps | no | run/env/readiness domain | no | yes for run packaging tickets | run evidence only | no | no |
| Checker | no | blocker/evidence domain | no | no | no | yes, via CheckerVerdict only | no |
| Closeout | no | fact-chain domain when applicable | no | no | no | no | yes, via CloseoutGate only |
| Runtime/executor | no | no | no | executes package only | factual command/provider/workspace records | no | no |
| Reducer / validator | no | validates approval set | validates only | no | no | validates state after gates | validates state after gates |

## V2-100A — Rework domain model

### Goal

Implement first-class typed models for rework cycle/request/issue/plan/attempt/outcome. Convert V2-090K failure taxonomy into structured ReworkIssue records.

### Proposed files

- `src/boardroom_os/rework/__init__.py`
- `src/boardroom_os/rework/model.py`
- `src/boardroom_os/rework/blocker_projection.py`
- `tests/rework/test_rework_model.py`
- `tests/rework/test_v2_090k_failure_snapshot_projection.py`
- `tests/negative/test_rework_model_fail_closed.py`

### Required implementation

1. Add value objects:
   - `ReworkCycleId`
   - `ReworkRequestId`
   - `ReworkIssueId`
   - `ReworkPlanId`
   - `TicketGraphPatchId`
   - `GraphPatchReviewId`
   - `ReworkAttemptId`
   - `ReworkOutcomeId`
2. Add enums:
   - `ReworkIssueCode`
   - `ReworkSuspectedDomain`
   - `ReworkDecisionKind`
   - `GraphPatchOperationKind`
   - `GraphPatchReviewDomain`
   - `GraphPatchReviewStatus`
   - `ReworkOutcomeStatus`
   - `ReworkTerminationReason`
3. Add typed models listed in shared vocabulary.
4. Add projection helper from:
   - FinalEvidenceTable missing/failed row.
   - CheckerVerdict blocker.
   - CloseoutGate failure.
   - V2-090K curated failure summary.
5. Ensure all models are frozen, extra-forbid, deterministic-id/hash friendly, and JSON serializable.

### Must-write negative tests first

- ReworkRequest with no issues fails.
- ReworkRequest from notes-only source fails.
- ReworkIssue with no blocker ref fails.
- ReworkIssue with stale `AC-TINY-*` acceptance ref fails when active acceptance refs are supplied.
- ReworkPlan with no `planner_attempt_ref` fails.
- ReworkPlan with decision outside enum fails.
- ReworkAttempt without execution package fails.
- ReworkAttempt without provider attempt and required evidence refs fails.
- ReworkOutcome accepted with remaining blockers fails.

### Happy-path tests

- Build ReworkRequest from FinalEvidenceTable missing row.
- Build ReworkRequest from CheckerVerdict blocker.
- Build ReworkRequest from CloseoutGate failure.
- Project the four V2-090K failure snapshot issues into ReworkIssue objects:
  - probe response shape mismatch
  - env binding not converged
  - final evidence old acceptance refs
  - closeout audit old run refs
- Serialize and hash a full ReworkRequest / ReworkPlan / ReworkOutcome chain.

### Acceptance

V2-100A is done when rework objects are not free-form runner dictionaries. They must be importable, validated, serialized, hashed, and tested independently from the full provider run.

## V2-100B — Rework events, reducer, and GraphPatchReviewGate

### Goal

Make rework state replayable and reducer-governed. Add actor permissions and graph patch review aggregation.

### Proposed files

- `src/boardroom_os/events/types.py` updates
- `src/boardroom_os/reducers/rework_reducer.py`
- `src/boardroom_os/rework/graph_patch.py`
- `src/boardroom_os/rework/review_gate.py`
- `tests/reducers/test_rework_reducer.py`
- `tests/rework/test_graph_patch_review_gate.py`
- `tests/negative/test_rework_reducer_fail_closed.py`
- `tests/negative/test_graph_patch_review_gate_fail_closed.py`

### Required implementation

1. Add event types from the event taxonomy section.
2. Add event payload models for each event.
3. Add reducer projection:
   - active cycles
   - requests
   - plans
   - graph patches
   - graph patch reviews
   - approval sets
   - attempts
   - outcomes
   - terminal decisions
4. Add GraphPatchReviewGate:
   - determines required review domains from patch operations and affected domains.
   - validates review actor role kind.
   - aggregates approvals/rejections.
   - emits ready/rejected/incomplete approval set.
5. Integrate graph version checks.
6. Enforce runtime/executor actor restrictions.

### Must-write negative tests first

- Runtime actor emits `REWORK_ACCEPTED` -> fail.
- Runtime actor emits `GRAPH_PATCH_ACCEPTED` -> fail.
- `REWORK_PLANNED` without `REWORK_REQUESTED` -> fail.
- `GRAPH_PATCH_ACCEPTED` without Architect review -> fail.
- `GRAPH_PATCH_ACCEPTED` without Checker blocker coverage review -> fail.
- Behavioral patch without Tester review -> fail.
- Run/env/readiness patch without Release DevOps review -> fail.
- Patch with stale base graph version -> fail.
- Patch expands allowed_write_set without Architect approval and Checker coverage -> fail.
- Same blocker marked accepted without new ReworkOutcome evidence -> fail.

### Happy-path tests

- `REWORK_REQUESTED -> REWORK_PLANNED -> GRAPH_PATCH_PROPOSED -> GRAPH_PATCH_REVIEWED* -> GRAPH_PATCH_ACCEPTED -> REWORK_TICKET_CREATED` projects correctly.
- Behavioral mismatch patch requires Tester and passes after Tester approves.
- Env binding patch requires Release DevOps and passes after Release DevOps approves.
- Closeout old-run patch requires fact-chain review and passes after Closeout/Checker approves.
- Projection is replay deterministic.

### Acceptance

V2-100B is done when all rework lifecycle state transitions are replayable and reducer-guarded, and when graph patch commit cannot be achieved by CEO-only output or runtime output.

## V2-100C — Multi-role rework planner boundary

### Goal

Implement the provider-backed planning and review boundary: CEO proposes ReworkPlan and TicketGraphPatch; other roles provide domain reviews; reducer commits only after GraphPatchReviewGate passes.

### Proposed files

- `src/boardroom_os/rework/planner.py`
- `src/boardroom_os/rework/reviewer.py`
- `src/boardroom_os/rework/ticket_graph_patch.py`
- `src/boardroom_os/agents/prompt_templates/baseline/v1/*.md` updates already started in this review
- `tests/rework/test_ceo_rework_planner.py`
- `tests/rework/test_multi_role_graph_patch_reviews.py`
- `tests/negative/test_ceo_rework_planner_fail_closed.py`
- `tests/negative/test_multi_role_graph_patch_reviews_fail_closed.py`

### Required implementation

1. Create `CeoReworkPlannerInput`:
   - ReworkRequest
   - current TicketGraph projection
   - active AcceptanceContract
   - active PackageContract
   - RunManifest
   - SourceInventory refs
   - Checker/Closeout blocker refs
   - role prompt hook snapshot
2. Create `CeoReworkPlannerOutput`:
   - ProviderAttempt ref
   - parsed ReworkPlan
   - proposed TicketGraphPatch
   - validation result
3. Create domain reviewer inputs and outputs:
   - `ArchitectGraphPatchReviewInput/Output`
   - `CheckerGraphPatchReviewInput/Output`
   - `TesterGraphPatchReviewInput/Output`
   - `ReleaseDevOpsGraphPatchReviewInput/Output`
   - optional `CloseoutFactChainReviewInput/Output`
4. Each reviewer output must be backed by provider attempt lineage when provider mode is enabled.
5. Add parser/validator rules that fail closed when a provider returns prose instead of strict JSON.
6. Add deterministic fake-provider fixtures for tests.
7. Ensure runner cannot create a ReworkPlan or GraphPatchReview without an agent/provider attempt record, except in explicitly named fixture tests.

### Prompt requirements

The baseline prompt hooks must include the following behavior. This review already wrote them into the seven baseline templates; V2-100C should lock them with tests.

CEO:

- Creates ReworkRequest/ReworkPlan from blockers.
- Maps decisions to blocker refs, acceptance refs, source surfaces, evidence obligations, and target tickets.
- Does not directly commit graph patches.
- Requires Architect/Checker/Tester/Release DevOps review as needed.

Architect:

- Reviews graph structural invariants.
- Checks contract/package/source-surface/run-command boundaries.
- Rejects hidden allowed_write_set expansion.

Checker:

- Reviews blocker coverage and evidence obligations.
- Rejects old evidence, old acceptance refs, old run ids, notes-as-blocker-clearance.

Tester:

- Reviews behavior and probe shape.
- Distinguishes whether mismatch should fix implementation, contract, or probe.

Release DevOps:

- Reviews RunManifest, env binding, readiness, service startup, topology, sample promotion.

Closeout:

- Rejects cross-run closeout reuse and stale fact-chain.

### Must-write negative tests first

- CEO output with no provider attempt fails.
- CEO output with decision outside enum fails.
- CEO output with blocker not mapped to any action fails.
- CEO directly marks ticket completed fails.
- CEO graph patch accepted without Architect and Checker review fails.
- Probe mismatch patch accepted without Tester review fails.
- Env binding patch accepted without Release DevOps review fails.
- Reviewer prose without schema fails.
- Reviewer approval with no checked invariants fails.
- Review from wrong role kind fails.

### Happy-path tests

- Use the 090K `probe-response-shape-mismatch` issue: CEO proposes either `fix_implementation` or `fix_contract_or_probe`; Architect/Tester/Checker approve a bounded patch; reducer commits rework ticket.
- Use the 090K `env-binding-not-converged` issue: CEO proposes RunManifest/implementation alignment; Architect/Release DevOps/Checker approve; reducer commits rework ticket.
- Use the 090K `final-evidence-uses-old-acceptance-refs` issue: CEO routes to evidence projection/rebuild ticket; Checker approves blocker coverage; reducer commits.
- Use the 090K `closeout-audit-references-old-run` issue: CEO routes to closeout/audit fact-chain ticket; Closeout/Checker approve.

### Acceptance

V2-100C is done when graph patch creation is agent-driven but not CEO-singleton, and when the reducer can prove every committed graph patch passed required role reviews.

## V2-100D — Rework evidence, checker, and closeout reintegration

### Goal

Ensure every ReworkAttempt produces fresh evidence and cannot reuse previous pass artifacts.

### Proposed files

- `src/boardroom_os/rework/evidence.py`
- `src/boardroom_os/rework/attempt_runner.py`
- updates to evidence/final evidence/source inventory/closeout integration as needed
- `tests/rework/test_rework_evidence_recheck.py`
- `tests/rework/test_rework_closeout_fact_chain.py`
- `tests/negative/test_rework_evidence_fail_closed.py`
- `tests/negative/test_rework_closeout_fail_closed.py`

### Required implementation

1. Add `ReworkEvidenceRecheckInput`:
   - ReworkAttempt
   - active contracts
   - active RunManifest
   - source lineage records
   - command evidence
   - behavioral probe results
2. Add `ReworkEvidenceRecheckResult`:
   - new SourceInventory ref
   - new FinalEvidenceTable ref
   - new CheckerVerdict ref
   - optional CloseoutGate result ref
   - stale evidence rejection details
3. Make each rework round produce a new evidence namespace:
   - include cycle id and attempt id in evidence refs.
   - include active graph version.
   - include active config hashes.
4. Enforce no old pass artifacts:
   - final evidence table rows must be rebuilt from active AcceptanceContract.
   - source inventory must be rebuilt from active PackageContract and source lineage.
   - checker verdict must be generated after evidence verification for this attempt.
   - closeout package must reference this run/cycle/attempt lineage.
5. Add behavioral probe mapping checks:
   - BehavioralProbePlan entries map to acceptance refs.
   - response shape assertion failures become blocker-backed evidence rows.
   - captured dynamic ids/fields are auditable.
6. Strengthen RunManifest runnable-project requirement:
   - if run commands, service evidence, readiness probes, behavioral probes, or topology exist, service contracts must be explicit.

### Must-write negative tests first

- ReworkAttempt with workspace mutations but no provider attempt fails.
- ReworkAttempt with source edits but no source lineage fails.
- ReworkAttempt accepted using old FinalEvidenceTable row fails.
- Checker approved verdict earlier than new evidence verification fails.
- CloseoutGate references old run id fails.
- CloseoutGate references old RunManifest fails.
- Behavioral probe failure is omitted from final evidence table fails.
- Run commands exist but service contracts are absent fails.
- Env variable read by implementation is not declared/bound in RunManifest fails.

### Happy-path tests

- ReworkAttempt rebuilds SourceInventory and FinalEvidenceTable from active contracts.
- Checker returns `REWORK_REQUIRED` when one target issue remains.
- Checker returns approved only after fresh evidence satisfies targeted issue.
- CloseoutGate passes when all fact-chain refs are same-run/current-cycle.
- 090K failure classes are all converted into fresh evidence requirements and either satisfied or kept as blockers.

### Acceptance

V2-100D is done when rework cannot be represented as a comment or one-off source patch. Every attempt must produce a fresh, auditable evidence/checker/closeout chain.

## V2-100E — Multi-round rework proving scenario

### Goal

Prove end-to-end that agent team can take a real or resettable failure, create structured blockers, plan graph changes, execute rework, revalidate, and converge or escalate.

### Proposed files

- `scripts/run_v2_100_rework_loop_scenario.py`
- `src/boardroom_os/proving/v2_100_rework_loop.py`
- `tests/proving/test_v2_100_rework_loop.py`
- `tests/negative/test_v2_100_rework_loop_fail_closed.py`
- audit exports under `examples/generated-workspaces/tiny-fullstack/30-audit/v2-100-*`

### Scenario inputs

1. Curated real failure snapshot:
   - `examples/generated-workspaces/tiny-fullstack/30-audit/v2-090k-failure-snapshot/failure-summary.json`
2. Resettable failing fixture:
   - a controlled tiny-fullstack fixture that can reproduce at least two failure classes without relying on an expensive/non-deterministic real provider run.
3. Optional real provider run:
   - only when explicit real-provider opt-in is present.

### Required scenario phases

1. Load active contracts/run manifest/source/evidence snapshot.
2. Project failure summary into ReworkRequest.
3. Ask CEO planner for ReworkPlan + TicketGraphPatch.
4. Ask Architect/Checker/Tester/Release DevOps/Closeout reviewers as required.
5. Commit graph patch through reducer.
6. Execute rework ticket(s) through runtime/executor.
7. Collect provider attempts, command evidence, source lineage, behavioral probes.
8. Rebuild SourceInventory and FinalEvidenceTable.
9. Re-run Checker.
10. Re-run CloseoutGate when applicable.
11. If failed, either create another ReworkRequest or explicit escalation/exhaustion.
12. Export replay/process/git audit timeline.

### Must-write negative tests first

- Scenario tries to create ReworkRequest with no blocker -> fail.
- Scenario runner writes ReworkPlan without CEO provider attempt -> fail.
- Scenario runner writes GraphPatchReview without reviewer attempt -> fail.
- Scenario accepts after command success but behavioral probe still mismatches -> fail.
- Scenario accepts using old final evidence table -> fail.
- Scenario accepts using old closeout run ref -> fail.
- Scenario loops beyond budget without escalation -> fail.
- Scenario runtime directly emits `REWORK_ACCEPTED` -> fail.

### Happy-path tests

- Curated snapshot projection creates four ReworkIssue objects.
- Resettable fixture round 1 fails with structured blockers.
- CEO creates plan and graph patch.
- Required reviewers approve or reject by domain.
- Reducer commits only after approval set is complete.
- Attempt produces fresh evidence.
- Checker closes fixed blockers or keeps remaining blockers.
- Final state is either:
  - accepted with closeout passed and full audit chain, or
  - escalated/exhausted with explicit termination decision and full audit chain.

### Acceptance

V2-100E is done when the proving scenario demonstrates not “perfect first pass”, but autonomous recovery from imperfection with auditable governance.

## Prompt pack acceptance tests

Add tests that lock the new prompt intent. Proposed test file:

- `tests/execution/test_role_prompt_hooks_rework_governance.py`

Required assertions:

- CEO prompt contains ReworkRequest/ReworkPlan/TicketGraphPatch and multi-role review requirements.
- Architect prompt contains graph patch structural review, contract/source surface/allowed write set invariants.
- Checker prompt contains blocker coverage and stale evidence/run rejection.
- Tester prompt contains behavioral probe response shape / contract-probe-implementation mismatch responsibility.
- Release DevOps prompt contains RunManifest/env/readiness/service startup/sample promotion review.
- Closeout prompt contains same-run fact-chain and old run ref rejection.

## Config changes recommended for V2-100

### Add `config/boardroom-config.v2-100.yaml`

```yaml
version: 1
bundle_id: boardroom-config.v2-100.default
runtime_config: config/boardroom-runtime.v2-100.yaml
providers_config: config/boardroom-providers.v2-100.yaml
roles_config: config/boardroom-roles.v2-100.yaml
```

### Add graph patch policy to governance configuration

```yaml
graph_patch_review_policy:
  require_ceo_proposal: true
  required_review_domains:
    planning: ceo
    structural: architect
    blocker_coverage: checker
    behavioral_probe: tester
    run_env_readiness: release_devops
    closeout_fact_chain: closeout
  always_required_domains:
    - planning
    - structural
    - blocker_coverage
  conditional_domains:
    behavioral_probe:
      when_patch_touches:
        - acceptance_behavior
        - behavioral_probe
        - api_response_shape
        - integration_test
    run_env_readiness:
      when_patch_touches:
        - run_manifest
        - env_binding
        - service_startup
        - readiness_probe
        - frontend_backend_topology
        - sample_promotion
    closeout_fact_chain:
      when_patch_touches:
        - closeout_package
        - process_audit
        - replay_bundle
        - git_audit
  commit_actor: reducer
  allow_runtime_commit: false
  allow_executor_commit: false
```

This policy is a governance policy, not a runtime-only option. It should live in the config bundle or an explicitly referenced governance policy file, carry a stable hash, and be recorded in RunManifest / ProcessAudit. Runtime YAML may reference the policy for execution limits, but it must not become a second source of truth for graph mutation governance.

### Add prompt hook binding to roles YAML

```yaml
seats:
  - seat: ceo
    role_kind: ceo
    role_prompt_hook_ref: role-prompt-hook.baseline.ceo.v1
    graph_review_domains:
      - planning
  - seat: architect
    role_kind: architect
    role_prompt_hook_ref: role-prompt-hook.baseline.architect.v1
    graph_review_domains:
      - structural
  - seat: checker
    role_kind: checker
    role_prompt_hook_ref: role-prompt-hook.baseline.checker.v1
    graph_review_domains:
      - blocker_coverage
  - seat: tester
    role_kind: tester
    role_prompt_hook_ref: role-prompt-hook.baseline.tester.v1
    graph_review_domains:
      - behavioral_probe
  - seat: release_devops
    role_kind: release_devops
    role_prompt_hook_ref: role-prompt-hook.baseline.release-devops.v1
    graph_review_domains:
      - run_env_readiness
  - seat: closeout
    role_kind: closeout
    role_prompt_hook_ref: role-prompt-hook.baseline.closeout.v1
    graph_review_domains:
      - closeout_fact_chain
```

## Definition of done for V2-100

V2-100 is complete only when all of the following are true:

- V2-100A~E are all implemented and tested.
- ReworkRequest cannot be created without verified blockers.
- CEO planner cannot produce accepted/completed state.
- TicketGraphPatch cannot commit without required multi-role reviews.
- Runtime/executor/atomic-agent cannot emit governance terminal events.
- Every ReworkAttempt re-enters evidence/checker/closeout gates.
- Old evidence, old acceptance refs, old run refs, and old closeout artifacts are rejected.
- Resettable failing fixture proves multi-round accepted or escalated path.
- V2-090K curated failure snapshot is consumed by projection tests.
- ProcessAudit/ReplayBundle show complete multi-round timeline.
- Full run golden sample remains blocked until V2-100 passes and V2-090F is re-evaluated against fresh package/closeout/audit evidence.

## Suggested test commands

Core fast tests:

```bash
PYTHONPATH=src:. python -m pytest \
  tests/rework \
  tests/reducers/test_rework_reducer.py \
  tests/execution/test_role_prompt_hooks.py \
  -q
```

Negative tests:

```bash
PYTHONPATH=src:. python -m pytest \
  tests/negative/test_rework_model_fail_closed.py \
  tests/negative/test_rework_reducer_fail_closed.py \
  tests/negative/test_graph_patch_review_gate_fail_closed.py \
  tests/negative/test_rework_evidence_fail_closed.py \
  tests/negative/test_v2_100_rework_loop_fail_closed.py \
  -q
```

Proving scenario:

```bash
PYTHONPATH=src:. python -m pytest tests/proving/test_v2_100_rework_loop.py -q
```

Real provider opt-in should be separate and explicit:

```bash
BOARDROOM_USE_REAL_PROVIDER=1 \
PYTHONPATH=src:. python scripts/run_v2_100_rework_loop_scenario.py --real-provider --export-audit
```

## Migration notes from current V2-090K state

1. Keep the 090K failure snapshot immutable. Do not edit it to make tests pass.
2. Add a projection test that reads the snapshot and produces typed ReworkIssue records.
3. Do not wire the V2-100 scenario directly into the huge V2-090F runner. First build `boardroom_os/rework/*` as reusable modules.
4. Once V2-100A~D are stable, the proving runner can call reusable modules.
5. After V2-100E passes, rerun the V2-090F golden sample and decide whether it can finally be marked DONE.
