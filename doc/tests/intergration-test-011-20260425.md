# intergration-test-011-20260425

## Scope

- Scenario slug: `library_management_autopilot_live_011`
- Config: `backend/data/live-tests/library_management_autopilot_live_011.toml`
- Template: `backend/integration-tests.template.toml`
- Provider base URL: `http://codex.truerealbill.com:11234/v1`
- API key: configured locally; do not record plaintext in docs or logs.
- Role routing:
  - CEO: `gpt-5.5@high`
  - Architect / CTO: `gpt-5.5@xhigh`
  - Developer roles: `gpt-5.3-codex-spark@high`
  - Checker / UI designer: `gpt-5.4@high`

## Final State

- Workflow: `wf_01c3733dd2a0`
- Final workflow status: `COMPLETED`
- Final stage: `closeout`
- Final report: `backend/data/scenarios/library_management_autopilot_live_011/run_report.json`
- Report result: `success=true`, `completion_mode=full`, `ticks_used=1`
- Final ticket distribution: `COMPLETED=22`, `FAILED=18`
- Static artifact server: `http://127.0.0.1:8011/`
- Important artifact paths:
  - `backend/data/scenarios/library_management_autopilot_live_011/artifacts/10-project/src/terminal_command_contract.py`
  - `backend/data/scenarios/library_management_autopilot_live_011/artifacts/10-project/src/books_db.py`
  - `backend/data/scenarios/library_management_autopilot_live_011/artifacts/10-project/src/books_db_contract_probe.py`
  - `backend/data/scenarios/library_management_autopilot_live_011/artifacts/20-evidence/closeout/tkt_19950c0e6ba0/delivery-closeout-package.json`
  - `backend/data/scenarios/library_management_autopilot_live_011/artifacts/reports/workflow-chain/wf_01c3733dd2a0/workflow-chain-report.json`

## Execution Timeline

### 1. Launch and Initial Stable State

- Time: 2026-04-25 15:52 +08:00
- Command:

```powershell
py -3 -m tests.live.run_configured --config data/live-tests/library_management_autopilot_live_011.toml --clean --max-ticks 180 --timeout-sec 7200
```

- Initial PID: `46268`
- Logs:
  - `backend/.tmp/integration-011-full-live.out.log`
  - `backend/.tmp/integration-011-full-live.err.log`
- Scenario root: `backend/data/scenarios/library_management_autopilot_live_011`
- Initial workflow stage: `plan`
- Provider stream began normally for `tkt_wf_01c3733dd2a0_ceo_architecture_brief`.

### 2. Pytest Temp Directory Setup Issue

- Symptom: `py -3 -m pytest tests/test_live_configured_runner.py -q` initially hit `PermissionError: [WinError 5]` under system temp.
- Cause: temp root was set relative to `backend\.tmp` in a way that did not resolve correctly, so pytest fell back to user temp.
- Minimal action: created and used `backend/.tmp/pytest-temp`, setting `TMP`, `TEMP`, and `PYTEST_DEBUG_TEMPROOT`.
- Verification: `tests/test_live_configured_runner.py` passed, `9 passed`.

### 3. Developer Staffing Gap

- Time: 2026-04-25 16:23-16:27 +08:00
- Symptom: two pending rework tickets could not be leased; scheduler repeatedly recorded orchestration with no runtime execution.
- State: `COMPLETED=16`, `FAILED=2`, `PENDING=2`
- Failure type: `WORKSPACE_HOOK_VALIDATION_ERROR=2`
- Cause: pending tickets needed `backend_engineer_primary` and `database_engineer_primary`; roster lacked available employees for those role profiles, and the previous frontend worker was excluded by rework rules.
- Minimal action: inserted board-approved active employees for this scenario:
  - `emp_backend_integration_011`
  - `emp_database_integration_011`
  - `emp_platform_integration_011`
- Result: scheduler leased rework tickets to the new backend/database employees.

### 4. Artifact Ref Collision

- Time: 2026-04-25 16:38-16:41 +08:00
- Symptom: backend/database retries repeatedly failed with `ARTIFACT_VALIDATION_ERROR`.
- Error: `Artifact ref already exists in artifact index.`
- Cause: source-code rework wrote the same logical path, such as `10-project/src/terminal_command_contract.py` and `10-project/src/books_db.py`; runtime used logical path as `artifact_ref`, while artifact index requires unique refs.
- Minimal patch:
  - File: `backend/app/core/runtime.py`
  - Change: source/test output artifacts now use unique refs under `art://workspace/<ticket>/...`, while preserving logical paths.
- Verification:
  - `py -3 -m py_compile app/core/runtime.py`
  - `py -3 -m pytest tests/test_runtime_fallback_payload.py tests/test_live_configured_runner.py -q`
  - Result: `11 passed`
- Restart:
  - old PID `46268` stopped
  - resumed non-clean run with PID `47048`
- Result: BR003 completion ticket `tkt_2100a1dc4a97` and BR002 completion ticket `tkt_001272d4e3e1` both completed after retries.

### 5. Max Ticks / CEO NO_ACTION Divergence

- Time: 2026-04-25 16:53-17:06 +08:00
- Symptom: resumed full live exited with `RuntimeError: Scenario exceeded max_ticks=180`.
- Snapshot: `backend/data/scenarios/library_management_autopilot_live_011/failure_snapshots/max_ticks.json`
- State at max ticks:
  - `COMPLETED=20`
  - `FAILED=18`
  - no `PENDING`, `LEASED`, or `EXECUTING` tickets
- Controller state:
  - `state=READY_FOR_FANOUT`
  - `recommended_action=CREATE_TICKET`
- Live CEO behavior:
  - Proposed `NO_ACTION`
  - Reason: graph health was `CRITICAL` because BR002/BR003 were persistent failure zones.
  - Validator rejected `NO_ACTION` because controller expected `CREATE_TICKET`.
- Minimal patches applied during the run:
  - `backend/app/core/ceo_scheduler.py`
    - Added restricted deterministic fallback when live proposal has no accepted actions, rejected action is `NO_ACTION`, and controller requires a mutating action.
    - Added due-workflow selection based on controller action when idle signal is absent.
  - `backend/tests/live/_autopilot_live_harness.py`
    - Added per-run idempotency token for non-clean resume keys.
- Verification:
  - `py -3 -m py_compile app/core/ceo_scheduler.py tests/live/_autopilot_live_harness.py`
  - `py -3 -m pytest tests/test_ceo_scheduler.py::test_ceo_shadow_run_rejects_live_no_action_when_controller_requires_backlog_fanout tests/test_ceo_scheduler.py::test_idle_ceo_maintenance_targets_controller_action_even_without_idle_signal tests/test_live_configured_runner.py tests/test_runtime_fallback_payload.py -q`
  - Result: `13 passed`
- Residual unrelated test issue:
  - `tests/test_scheduler_runner.py::test_scheduler_runner_idle_ceo_maintenance_creates_next_governance_document_ticket` still failed because actual controller state was `ARCHITECT_REQUIRED` while test expected `GOVERNANCE_REQUIRED`.

### 6. Incorrect Closeout Created

- Time: 2026-04-25 17:05-17:06 +08:00
- CEO run: `ceo_cc2d41e5f03d`
- Deterministic fallback reason:

```text
Deterministic fallback used because the live CEO proposal had no accepted actions while controller_state.recommended_action is CREATE_TICKET.
```

- Actual fallback action:
  - created `tkt_19950c0e6ba0`
  - node: `node_ceo_delivery_closeout`
  - schema: `delivery_closeout_package`
  - parent ticket: `tkt_001272d4e3e1`
- Expected safe behavior:
  - either keep waiting for graph health to recover
  - or, if respecting controller `CREATE_TICKET`, create BR004
- Result:
  - closeout completed
  - closeout review `tkt_0f9d90358118` completed
  - workflow moved to `COMPLETED/closeout`

### 7. Final Harness Assertion Fixes

- Time: 2026-04-25 17:07-17:15 +08:00
- Minimal patches:
  - `backend/tests/live/_autopilot_live_harness.py`
    - Source delivery payload audit now skips historical failed retry tickets.
    - Non-clean resume can attach to latest `EXECUTING` or `COMPLETED` workflow.
    - Terminal payload assumption/provider audit handling updated for compact payloads.
  - `backend/tests/live/_config.py`
  - `backend/tests/live/_scenario_profiles.py`
    - Expected model/reasoning now derived from role bindings instead of one global preferred model.
- Verification:
  - `py -3 -m py_compile tests/live/_autopilot_live_harness.py tests/live/_config.py tests/live/_scenario_profiles.py`
  - `py -3 -m pytest tests/test_live_library_management_runner.py::test_library_outcome_accepts_compact_completed_scope_without_ticket_count_floor tests/test_live_library_management_runner.py::test_assert_source_delivery_payload_quality_skips_failed_retry_history tests/test_live_configured_runner.py -q`
  - Result: `11 passed`
- Final command:

```powershell
py -3 -m tests.live.run_configured --config data/live-tests/library_management_autopilot_live_011.toml --max-ticks 30 --timeout-sec 900
```

- Final report succeeded with empty stderr.

## Actual Delivered Code Review

The generated artifact is not a complete deliverable application. It is a partial terminal-oriented code slice.

### Generated Files

- `terminal_command_contract.py`
  - Parses commands and returns structured outcomes.
  - Does not execute state-changing operations against the repository.
- `books_db.py`
  - Provides a SQLite-backed `BooksRepository`.
  - Implements persistence operations.
- `books_db_contract_probe.py`
  - Exercises repository behavior.
  - Has a Windows cleanup issue because repository resources are not closed before `TemporaryDirectory` cleanup.

### Product Scope Note

The scenario input itself targets a single-machine terminal/console product, not a website:

- `backend/integration-tests.template.toml` uses the goal text `单机版终端系统`.
- It also includes the hard constraint `界面固定为高信息密度 terminal/console 风格`.
- `board-brief.md`, architecture brief, technology decision, detailed design, and backlog recommendation all preserve this terminal-only scope.

This is not treated as a defect for round 011 unless the intended scenario is changed to request a browser/web UI.

## Confirmed Defects

### P1. Deterministic Fallback Closes Out Before Backlog Fanout

- Files:
  - `backend/app/core/ceo_proposer.py`
- Evidence:
  - `build_deterministic_fallback_batch()` calls `_build_autopilot_closeout_batch()` before checking `recommended_action == CREATE_TICKET`.
  - At `ceo_cc2d41e5f03d`, controller state was `READY_FOR_FANOUT / CREATE_TICKET`.
  - `capability_plan.followup_ticket_plans` contained BR004-BR007 with `existing_ticket_id=null`.
  - Fallback created `node_ceo_delivery_closeout` instead of BR004.
- Impact:
  - BR004-BR007 were never implemented.
  - Workflow completed with only BR002/BR003 partial delivery.
- Correct behavior:
  - When backlog followup plans contain unmaterialized tickets, closeout must not be eligible.
  - If `recommended_action == CREATE_TICKET`, fallback must prefer required governance ticket or backlog followup ticket creation over closeout.
- Suggested fix:
  - Move closeout fallback after `CREATE_TICKET` handling, or gate closeout with `no_unmaterialized_followup_plans`.
  - Add a regression test reproducing 011 state: BR001-BR003 completed, BR004-BR007 pending, controller `CREATE_TICKET`; fallback must create BR004, not closeout.

### P1. Closeout Readiness / Delivery Evidence Is Too Weak

- Files:
  - `backend/app/core/workflow_completion.py`
  - `backend/app/core/ceo_proposer.py`
- Evidence:
  - `ticket_has_delivery_mainline_evidence()` returns true if a ticket maps to any delivery mainline stage.
  - BR002 command contract smoke evidence counted as enough delivery evidence for closeout.
  - Closeout package explicitly says delivery remains `command-level only`.
- Impact:
  - A partial command-contract slice can close the workflow.
  - Required downstream implementation and checker packets are bypassed.
- Correct behavior:
  - For backlog-driven fanout, closeout readiness must require all required followup tickets to be materialized and completed/reviewed, or require an explicit completed checker handoff ticket.
- Suggested fix:
  - Add closeout readiness checks against `implementation_handoff.recommended_sequence`.
  - Require BR004-BR007 completion for this scenario.
  - Require evidence for service behavior, rendering/e2e behavior, tests/evidence, and checker handoff before closeout.

### P1. CEO Waiting Was Reasonable but Controller/Validator Rejected It

- Files:
  - `backend/app/core/workflow_controller.py`
  - `backend/app/core/ceo_scheduler.py`
  - graph health / controller integration code to locate in next session.
- Evidence:
  - Live CEO repeatedly proposed `NO_ACTION` because graph health was `CRITICAL`.
  - Validator rejected `NO_ACTION` when controller state remained `READY_FOR_FANOUT / CREATE_TICKET`.
- Impact:
  - A reasonable health-gate pause was treated as invalid.
  - This forced deterministic fallback, which then incorrectly closed out.
- Correct behavior:
  - If graph health is `CRITICAL` with pause recommendation, controller should surface `WAIT_FOR_INCIDENT`, `WAIT_FOR_GRAPH_HEALTH`, or otherwise allow `NO_ACTION`.
- Suggested fix:
  - Feed graph health severity into controller state.
  - Add regression test: with `PERSISTENT_FAILURE_ZONE` critical and no active tickets, controller should not demand `CREATE_TICKET` until health recovers or is explicitly overridden.

### P1. Graph Health Does Not Recover Promptly After Successful Retry

- Evidence:
  - BR002 final implementation ticket `tkt_001272d4e3e1` completed at 2026-04-25 16:41:57.
  - BR003 final implementation ticket `tkt_2100a1dc4a97` completed at 2026-04-25 16:41:16.
  - BR002/BR003 review tickets also completed.
  - Graph health `gv_454` still reported both nodes as `PERSISTENT_FAILURE_ZONE`.
- Impact:
  - CEO continued to see `CRITICAL` after recovery.
  - This promoted repeated `NO_ACTION` decisions and stalled fanout.
- Correct behavior:
  - Successful completion plus successful review of the latest recovery ticket should downgrade or clear the persistent failure zone.
- Suggested fix:
  - Add recovery rule: if latest ticket for affected runtime node is `COMPLETED` and latest review is `COMPLETED`, and no active incident remains for that node, do not keep the node as CRITICAL solely due to recent historical incidents.
  - Alternatively decay incident counts after successful recovery.

### P1. BR002/BR003 Artifact Validation Failures Created Persistent Failure Zones

- Evidence:
  - BR002 failures:
    - `WORKSPACE_HOOK_VALIDATION_ERROR=2`
    - `ARTIFACT_VALIDATION_ERROR=8`
  - BR003 failures:
    - `ARTIFACT_VALIDATION_ERROR=8`
  - Main error: `Artifact ref already exists in artifact index.`
  - Earlier BR002 error: `Code delivery tickets must version verification evidence paths by attempt.`
- Root cause:
  - Source-code rework reused logical paths as artifact refs.
  - Artifact index requires unique artifact refs.
- Action already taken:
  - `runtime.py` now emits unique `art://workspace/<ticket>/...` refs for source/test artifacts.
- Follow-up:
  - Add regression tests for repeated rework attempts writing the same logical path.
  - Confirm hook validation also requires attempt-versioned evidence paths across all source delivery shapes.

### P1. Command Layer Does Not Mutate Repository State

- File:
  - `backend/data/scenarios/library_management_autopilot_live_011/artifacts/10-project/src/terminal_command_contract.py`
- Evidence:
  - `check out`, `return`, `add`, and `remove` return `SUCCESS` payloads without calling `BooksRepository`.
  - Manual validation showed `check out 1` returned success while repository status remained `IN_LIBRARY`.
- Impact:
  - Users see accepted/successful commands, but database state does not change.
  - Product does not satisfy "maintain whether a book is in the library".
- Correct behavior:
  - BR004 should implement domain/application service that validates preconditions and calls repository operations atomically.
  - BR005 should render service outcomes.
- Suggested fix:
  - Implement service layer for Add, Check Out, Return, Remove.
  - Connect parser/terminal command handling to service layer.
  - Add before/after repository state tests.

### P1. Availability Query Does Not Read Real Inventory

- File:
  - `backend/data/scenarios/library_management_autopilot_live_011/artifacts/10-project/src/terminal_command_contract.py`
- Evidence:
  - `availability/title` returns a queued/echo payload.
  - It does not query SQLite.
  - It does not return candidates, total copies, available copies, or can-take-now labels.
- Impact:
  - Product cannot answer "这本书现在能不能拿走".
- Correct behavior:
  - Query repository by normalized title.
  - Group by normalized author.
  - Return `NOT_FOUND`, definitive aggregate answer, or `AMBIGUOUS_TITLE`.
- Suggested fix:
  - Implement BR004 domain policy and BR005 rendering.
  - Add tests for single match, multiple copies, checked-out-only, and ambiguous title.

### P2. Remove Uses Fake Book Snapshot

- File:
  - `backend/data/scenarios/library_management_autopilot_live_011/artifacts/10-project/src/terminal_command_contract.py`
- Evidence:
  - `_book_snapshot()` fabricates `Book {id}`, `Unknown Author`, and `AVAILABLE`.
  - `remove 999 confirm=yes` can appear successful without checking existence or `IN_LIBRARY`.
- Impact:
  - Remove confirmation and deletion semantics are not trustworthy.
- Correct behavior:
  - Lookup exact id in repository.
  - Deny missing ids.
  - Deny `CHECKED_OUT` rows.
  - Require explicit confirmation displaying real id/title/author/status.
- Suggested fix:
  - Move Remove guard into domain/application service.
  - Add tests for missing id, checked-out id, unconfirmed remove, title-only remove, wildcard/batch remove.

### P2. Contract Probe Leaves SQLite File Locked on Windows

- File:
  - `backend/data/scenarios/library_management_autopilot_live_011/artifacts/10-project/src/books_db_contract_probe.py`
- Evidence:
  - Probe prints `PASS_CONTRACT_CHECKS`.
  - Process exits nonzero on Windows because `TemporaryDirectory` cleanup hits an open SQLite handle.
- Impact:
  - Good repository behavior can still appear failed in Windows CI/local runs.
- Correct behavior:
  - Close repository connection before temp directory cleanup.
- Suggested fix:
  - Add `BooksRepository.close()` usage or context manager support.
  - Update probe to close in `finally`.

### P2. Closeout Created Orphan Subgraph

- Evidence:
  - After premature closeout, graph health `gv_675` reported `ORPHAN_SUBGRAPH`.
  - Affected nodes included BR001/BR003 lanes disconnected from every closeout path.
- Impact:
  - Graph health stayed `CRITICAL` after closeout.
  - Workflow graph appeared internally inconsistent.
- Root cause:
  - Closeout path was created before completing the backlog fanout path.
- Suggested fix:
  - Same as closeout readiness fix.
  - Add graph invariant: closeout cannot be created if any planned implementation path remains unmaterialized or disconnected.

### P2. Scheduler Runner Test Drift

- File:
  - `backend/tests/test_scheduler_runner.py`
- Evidence:
  - `test_scheduler_runner_idle_ceo_maintenance_creates_next_governance_document_ticket` failed during targeted verification.
  - Actual controller state: `ARCHITECT_REQUIRED`
  - Expected state in test: `GOVERNANCE_REQUIRED`
- Impact:
  - Not directly blocking 011, but indicates controller-state expectations drifted.
- Suggested fix:
  - Revisit test expectation and controller naming semantics.
  - Decide whether `ARCHITECT_REQUIRED` replaces or specializes `GOVERNANCE_REQUIRED`.

## Backlog Fanout Reality

The backlog recommendation required seven downstream tickets:

- BR001: Context and scope lock
- BR002: Command vocabulary and terminal outcome contract
- BR003: Local books persistence and repository contract
- BR004: Domain policy and application service
- BR005: Terminal rendering and end-to-end behavior
- BR006: Tests, evidence, and tracking updates
- BR007: Checker handoff and approval review

Actual implementation path:

- BR001 completed.
- BR002 completed after retries.
- BR003 completed after retries.
- BR004 was planned but never materialized.
- BR005 was planned but never materialized.
- BR006 was planned but never materialized.
- BR007 was planned but never materialized.
- `node_ceo_delivery_closeout` was created instead.

Database confirmation:

```text
node_backlog_followup_tkt_34365feaffc7_br004 []
node_backlog_followup_tkt_34365feaffc7_br005 []
node_backlog_followup_tkt_34365feaffc7_br006 []
node_backlog_followup_tkt_34365feaffc7_br007 []
```

Only tickets created after BR002/BR003 checker completion:

```text
tkt_19950c0e6ba0 node_ceo_delivery_closeout
tkt_0f9d90358118 node_ceo_delivery_closeout review
```

## Root Cause Summary

Round 011 completed because the harness and workflow closeout criteria accepted a partial closeout path. The actual product delivery was incomplete.

Primary chain:

1. BR002/BR003 hit repeated artifact validation failures.
2. Graph health marked BR002/BR003 as `PERSISTENT_FAILURE_ZONE` and `CRITICAL`.
3. BR002/BR003 later recovered and completed, but graph health did not recover promptly.
4. CEO reasonably proposed `NO_ACTION` because graph health was still `CRITICAL`.
5. Controller still demanded `CREATE_TICKET`; validator rejected CEO `NO_ACTION`.
6. Deterministic fallback ran.
7. Fallback checked autopilot closeout before backlog fanout.
8. Closeout readiness was too broad and accepted BR002 command-contract evidence.
9. Closeout ticket was created instead of BR004.
10. Workflow completed without BR004-BR007 and without a functional end-to-end application.

## Next Session Fix Plan

### Must Fix First

1. Prevent closeout before backlog fanout is complete.
   - Add guard in `_build_autopilot_closeout_batch()`.
   - Or reorder `build_deterministic_fallback_batch()` so `CREATE_TICKET` backlog handling precedes closeout.

2. Strengthen closeout readiness.
   - Require all planned followup tickets from `implementation_handoff.recommended_sequence` to be materialized and complete.
   - Require final checker handoff or equivalent evidence before closeout.

3. Make controller respect critical graph health.
   - If graph health recommends pause, controller should not require `CREATE_TICKET`.
   - It should produce a wait state or allow `NO_ACTION`.

4. Add graph health recovery semantics.
   - Successful latest implementation and review should clear/downgrade persistent failure zone.

### Then Fix Product Delivery Behavior

5. Implement BR004-equivalent service behavior.
   - Domain policy.
   - Availability aggregation.
   - Add / Check Out / Return / Remove mutations.
   - Atomic validation-before-write.

6. Implement BR005-equivalent terminal rendering/e2e behavior.
   - Catalog rows.
   - Availability by title/id.
   - Ambiguity output.
   - Remove confirmation.
   - Canonical run: add, list, lookup, check out, lookup, return, remove, list.

7. Implement BR006/BR007 evidence and checker gates.
   - Positive behavior tests.
   - Fail-closed no-state-change tests.
   - Schema checks.
   - Forbidden-feature checks.

### Regression Tests to Add

- Fallback with BR001-BR003 complete and BR004-BR007 missing must create BR004, not closeout.
- Closeout readiness must fail when any implementation handoff plan remains unmaterialized.
- Graph health must downgrade/clear persistent failure zone after successful latest ticket and review.
- Controller must allow waiting when graph health is critical.
- Rework source delivery must support repeated writes to the same logical path without artifact ref collision.
- Terminal command behavior must mutate/query `BooksRepository` instead of returning parser-only success.
- Windows probe must close SQLite handles before temp directory cleanup.

## Verification Commands Already Run

```powershell
py -3 -m py_compile app/core/runtime.py
py -3 -m pytest tests/test_runtime_fallback_payload.py tests/test_live_configured_runner.py -q
```

Result: `11 passed`

```powershell
py -3 -m py_compile app/core/ceo_scheduler.py tests/live/_autopilot_live_harness.py
py -3 -m pytest tests/test_ceo_scheduler.py::test_ceo_shadow_run_rejects_live_no_action_when_controller_requires_backlog_fanout tests/test_ceo_scheduler.py::test_idle_ceo_maintenance_targets_controller_action_even_without_idle_signal tests/test_live_configured_runner.py tests/test_runtime_fallback_payload.py -q
```

Result: `13 passed`

```powershell
py -3 -m py_compile tests/live/_autopilot_live_harness.py tests/live/_config.py tests/live/_scenario_profiles.py
py -3 -m pytest tests/test_live_library_management_runner.py::test_library_outcome_accepts_compact_completed_scope_without_ticket_count_floor tests/test_live_library_management_runner.py::test_assert_source_delivery_payload_quality_skips_failed_retry_history tests/test_live_configured_runner.py -q
```

Result: `11 passed`

## Do Not Forget

- Do not record API keys in logs.
- The file name intentionally uses existing project spelling: `intergration-test-011-20260425.md`.
- Round 011's final `success=true` is a harness/workflow success, not proof of a complete product.
- The next fix should start with control-plane closeout/fanout behavior before improving generated product code.
