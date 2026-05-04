# 交付物契约

## 目标

`DeliverableContract` 定义“最终产物是否满足 PRD”，而不是只判断 ticket 是否完成、checker 是否 approved、graph 是否 terminal。

第 15 轮暴露的问题是：runtime graph 可以被推到 completed，但 placeholder source、浅层 smoke evidence、failed check convergence、closeout final refs 误选等问题仍可能削弱最终交付可信度。

## 输入来源

交付物契约由以下输入编译：

- PRD / charter；
- locked scope；
- governance decisions；
- architecture/design assets；
- backlog recommendation；
- acceptance criteria；
- risk constraints；
- required audit mode。

契约编译结果必须成为 process asset，并记录版本。

## 核心字段

```yaml
deliverable_contract:
  contract_id: dc_<workflow_id>_<version>
  workflow_id: ...
  graph_version: ...
  source_prd_refs: []
  locked_scope: []
  acceptance_criteria: []
  required_source_surfaces: []
  required_evidence: []
  required_review_gates: []
  forbidden_placeholder_patterns: []
  closeout_requirements: []
  supersede_rules: []
```

## Required source surfaces

每个 source surface 必须描述：

- path pattern；
- owning capability；
- expected behavior；
- linked acceptance criteria；
- minimum non-placeholder evidence；
- required tests/checks。

示例：

```yaml
- surface_id: backend.loan_transactions
  paths:
    - 10-project/src/backend/**/loans*/**
  required_capabilities:
    - source.modify.backend
  acceptance_refs:
    - AC-loan-create
    - AC-loan-return
  required_evidence:
    - backend.integration_test
    - api_contract_test
```

## Required evidence kinds

| Evidence kind | 说明 |
|---|---|
| `source_inventory` | changed files + purpose mapping |
| `unit_test` | 单元测试结果 |
| `integration_test` | 服务/模块集成测试 |
| `api_contract_test` | API contract 验证 |
| `runtime_smoke` | runtime 可见行为 smoke，trace/log 优先 |
| `security_check` | 权限、输入、敏感信息检查 |
| `performance_check` | 如 PRD 要求 |
| `git_closeout` | diff/commit/working tree 证据 |
| `maker_checker_verdict` | 审查结论和 findings |
| `risk_disposition` | 已知风险与接受/修复说明 |

## Placeholder 禁止规则

以下内容不能满足 deliverable contract：

- 文件名或内容是 `source.py` 且无业务实现。
- 产物文字说明“后续里程碑补齐”但被当作最终交付。
- 只有泛化 `1 passed`，没有业务断言。
- 测试 stdout 由 runtime fallback 默认生成。
- source inventory 未覆盖 changed source。
- evidence pack 没有关联 acceptance criteria。
- checker 只给 `APPROVED_WITH_NOTES`，但 blocking evidence gap 未关闭。
- closeout final refs 只有治理文档，没有 source/evidence/check refs。

## Supersede 规则

返工、重试、replacement 产生新产物时：

- 新 source delivery 必须声明 supersedes；
- 旧 placeholder / failed evidence 不能继续进入 final evidence set；
- closeout 只能选择 current graph pointer 对应的最终证据；
- old ticket late completion 只能作为 archive，不自动成为 current evidence。

## Checker 和 DeliverableContract 的关系

Checker verdict 不是最终真相。最终判断顺序：

1. schema validation；
2. write-set validation；
3. evidence completeness；
4. deliverable contract evaluation；
5. checker policy；
6. closeout policy。

`APPROVED_WITH_NOTES` 只能放行非阻塞 finding。只要 deliverable contract 存在 blocker，就必须 rework 或 explicit convergence policy。

## Closeout 要求

Closeout package 必须包含：

- deliverable contract version；
- deliverable contract id；
- evaluation fingerprint；
- acceptance criteria status table；
- final evidence table；
- final source surfaces；
- final evidence refs；
- supersede summary；
- unresolved non-blocking notes；
- risk disposition；
- replay bundle refs；
- audit materialization refs。

Closeout 不能只写：

```text
runtime graph completed
```

它必须写：

```text
PRD acceptance satisfied by these source/evidence/check refs
```

Round 9E 将 closeout 的 runtime 放行口径收口为 `DeliverableEvaluation` + final evidence table。`final_artifact_refs` 继续保留为 API/display 兼容字段，但不能单独证明 contract satisfaction。

Final evidence table 的固定列为：

- acceptance criterion；
- evidence ref；
- producer ticket；
- producer node/source surface；
- artifact kind；
- legality status；
- supersede/current status；
- finding disposition。

Final evidence table 只能由 evaluator 认可的 current + legal evidence 编译。`SUPERSEDED`、`PLACEHOLDER`、`ARCHIVE`、`UNKNOWN_REF`、`STALE_CURRENT_POINTER`、`ILLEGAL_KIND`、governance-only docs 和 backlog recommendation-only refs 不得进入 final table。

## 015 回归要求

新的 deliverable contract 必须阻断以下 015 中出现的问题：

- BR-040 placeholder fix 被 maker-checker 放行。
- BR-041 source.py 占位加一条泛化测试。
- BR-100 final checker 长循环无法收敛。
- closeout final refs 混入 `ARCHITECTURE.md` 或 backlog recommendation。
- manual closeout recovery 绕过 final evidence completeness。

## 验收标准

- 每个 deliverable contract 可独立评估。
- Contract evaluation 输出 machine-readable findings。
- Placeholder detection 有测试。
- Closeout 只接受 current graph final evidence。
- 015 replay 包可用于验证旧问题被阻断。

## Round 9A implementation status

Round 9A has landed the minimal versioned contract and pure evaluator skeleton in `backend/app/core/deliverable_contract.py`.

Implemented contract objects:

- `DeliverableContract`
- `AcceptanceCriterion`
- `RequiredSourceSurface`
- `RequiredEvidence`
- `CloseoutObligation`
- `DeliverableEvidencePack`
- `DeliverableEvaluationPolicy`
- `DeliverableEvaluation`
- `ContractFinding`

Compiler boundary:

- `compile_deliverable_contract()` consumes only structured PRD / charter / ticket acceptance inputs supplied by the caller.
- `compile_ticket_acceptance_deliverable_contract()` is a minimal ticket acceptance compiler for later integration.
- The compiler records workflow id, graph version, PRD refs, locked scope, acceptance criteria, source surfaces, evidence requirements, review gates, placeholder rules, supersede rules and closeout obligations.

Evaluator boundary:

- `evaluate_deliverable_contract(contract, evidence_pack, policy)` is pure. It does not read DB rows, artifact file bodies, provider raw transcript, markdown body text or checker notes freeform text.
- Round 9A fail-closed findings cover missing acceptance criteria, missing required evidence, unknown evidence kind and empty final evidence.
- `workflow_completion.py` and `ticket_handlers.py` only expose closeout preview helpers. They do not replace the old checker, rework or closeout decision paths in this batch.

Stable id rules:

- `contract_id = dc_<workflow_id>_<contract_version>_<hash>`.
- `finding_id = cf_<reason_code>_<hash>`.
- `evaluation_fingerprint = de_<contract_id>_<hash>`.
- Hashes are derived from canonical JSON with sorted keys, ASCII output and stable list normalization.

## Round 9B implementation status

Round 9B has extended the pure evaluator and compiler in `backend/app/core/deliverable_contract.py`.

Implemented additions:

- `EvidenceItem` / `EvidencePack` are now the structured evidence input. `DeliverableEvidence` / `DeliverableEvidencePack` remain as compatibility aliases.
- Each evidence item records evidence ref, producer ticket, producer node, source surface refs, artifact kind, legality status, acceptance refs, supersede refs, placeholder/archive flags and current pointer status.
- Required source surfaces can be compiled from structured locked scope, governance decisions, architecture/design assets, backlog recommendations and allowed write set metadata.
- Capability path patterns come from `CAPABILITY_WRITE_SURFACES`; role names, ticket summaries and checker notes are not used as source surface authority.

Evaluator additions:

- Only accepted current evidence can satisfy required evidence.
- Superseded, placeholder, archive, unknown, illegal-kind and stale current pointer evidence produces `invalid_evidence_for_contract` and cannot satisfy required evidence.
- Source surface required evidence kinds are mapped to acceptance criteria. Missing source/test/check/git/closeout evidence produces `acceptance_missing_required_evidence`.
- Placeholder source/test fallback remains fail-closed through structured evidence facts such as `placeholder=true`, `legality_status=PLACEHOLDER`, `stdout_fallback=true` or placeholder reason metadata.

9B verification:

- `pytest --basetemp="D:/Projects/boardroom-os/.pytest-tmp" backend/tests/test_deliverable_contract.py backend/tests/test_workspace_path_contracts.py -q` -> `34 passed`.

9C dependencies:

- Checker verdict / `APPROVED_WITH_NOTES` gate must consume `DeliverableEvaluation` and must not override blocking findings.
- Failed delivery report convergence still needs structured `ConvergencePolicy`; freeform checker notes or graph terminal state must not satisfy the contract.
- Rework target routing and closeout final evidence table remain later Round 9D/9E work.

## Round 9C implementation status

Round 9C has replaced the checker verdict gate for failed delivery reports with a `DeliverableEvaluation` first contract gate.

Implemented additions:

- `ConvergencePolicy` and `ConvergenceAllowedGap` are structured inputs in `backend/app/core/deliverable_contract.py`.
- `checker_contract_gate()` consumes `DeliverableEvaluation`, checker review status and optional `ConvergencePolicy`.
- `APPROVED` / `APPROVED_WITH_NOTES` cannot override blocking contract findings.
- `APPROVED_WITH_NOTES` can pass only when the contract evaluation has no blocking findings, or every blocking gap is explicitly covered by structured convergence policy.
- Failed delivery report convergence requires `allow_failed_delivery_report=true`, declared gap identity, risk disposition, approver/source refs, and expiry or scope limits.

Integrated gates:

- `ticket_handlers.py` now compiles failed delivery check reports into a Round 9C legacy `DeliverableEvaluation` input and converts blocked gates back into existing fix-ticket rework input.
- `workflow_completion.py` now uses the same gate before allowing maker-checker approval of failed delivery reports into closeout eligibility.
- `output_schemas.py` validates optional `maker_checker_verdict.convergence_policy` through the structured model.
- `workflow_controller.py`, `ceo_snapshot.py` and `graph_health.py` approved-review checks are marked as API display / legacy input compiler only, not contract satisfaction.

Round 9E follow-up:

- Final evidence table and closeout package contract version surface have been implemented in Round 9E. Remaining replay/resume/checkpoint validation stays in Phase 6/7.

9C verification:

- `pytest --basetemp="D:/Projects/boardroom-os/.pytest-tmp" backend/tests/test_deliverable_contract.py backend/tests/test_workflow_autopilot.py -q` -> `42 passed, 1 warning`.
- `pytest --basetemp="D:/Projects/boardroom-os/.pytest-tmp" backend/tests/test_api.py::test_check_internal_checker_approval_on_failed_report_creates_fix_ticket backend/tests/test_api.py::test_autopilot_converged_check_report_without_policy_is_forced_back_to_rework backend/tests/test_api.py::test_structured_convergence_policy_allows_failed_check_report -q` -> `3 passed`.
- `pytest --basetemp="D:/Projects/boardroom-os/.pytest-tmp" backend/tests/test_output_schemas.py -q` -> `40 passed`.

## Round 9D implementation status

Round 9D routes blocking contract gaps to upstream rework targets without changing the Phase 4 `ActionProposal` contract.

Implemented additions:

- `compile_contract_rework_recovery_actions()` compiles blocking `ContractFinding` rows into existing `ProgressionPolicy.recovery.actions`.
- Each compiled action carries `source_surface_ref`, `producer_ticket_id`, `producer_node_ref`, `required_capability`, `missing_evidence_kind`, `acceptance_ref`, `current_graph_pointer` and `contract_finding_id`.
- Source/test/git/check evidence gaps prefer the current producer ticket/node for the source surface. Checker-only defects target the checker node only when the missing evidence kind is `maker_checker_verdict`.
- Placeholder, superseded, archive and stale-pointer evidence are invalid lineage only. They cannot become current producer evidence.
- If no current producer ticket is available, the compiled action is `contract_gap_missing_current_producer`; progression turns it into an incident instead of guessing a target.

Integrated paths:

- `workflow_progression.py` maps `finding_kind=deliverable_contract_gap` to `progression.rework.deliverable_contract_gap`, and `contract_gap_missing_current_producer` to `progression.incident.contract_gap_missing_current_producer`.
- `ticket_handlers.py` preserves structured contract rework target metadata when failed delivery reports are forced back to rework, and builds the fix ticket against the upstream producer ticket/node.
- `workflow_completion.py` carries contract gate blocking findings and compiled recovery actions into the closeout gate issue.
- `workflow_controller.py` remains an input compiler and policy caller. It does not parse checker notes or artifact bodies to choose rework targets.

Round 9E follow-up:

- Closeout final evidence table and closeout package contract version surface have been implemented in Round 9E. Remaining 015 full replay validation stays in Phase 7.

9D verification:

- `pytest --basetemp="D:/Projects/boardroom-os/.pytest-tmp" backend/tests/test_deliverable_contract.py backend/tests/test_workflow_progression.py -q` covers upstream source target, missing test evidence target, checker-only target, missing current producer incident, controller recovery input, and BR-040/BR-041 placeholder equivalence.
- `pytest --basetemp="D:/Projects/boardroom-os/.pytest-tmp" backend/tests/test_api.py::test_check_internal_checker_approval_on_failed_report_creates_fix_ticket backend/tests/test_api.py::test_autopilot_converged_check_report_without_policy_is_forced_back_to_rework -q` covers failed delivery checker rework and convergence fallback paths.

## Round 9E implementation status

Round 9E completes the Phase 5 closeout contract integration.

Implemented additions:

- `FinalEvidenceTableRow`, `FinalEvidenceTable` and `compile_final_evidence_table()` are defined in `backend/app/core/deliverable_contract.py`.
- Closeout package schema now requires `deliverable_contract_version`, `deliverable_contract_id`, `evaluation_fingerprint` and `final_evidence_table`.
- Runtime closeout normalization and ticket result submit hooks compile closeout payload contract fields from `DeliverableEvaluation` and the final evidence table.
- Workflow completion re-evaluates the closeout contract and rejects missing/mismatched contract id, version, fingerprint or final evidence table.
- Progression closeout readiness now carries contract id, contract version, evaluation fingerprint, final table row count and blocking finding count. `CLOSEOUT` proposals require contract satisfied and a non-empty final table summary.
- Current graph pointer filtering is applied when compiling closeout final evidence, so stale old attempts do not enter the final evidence set.

Legacy helper boundaries:

- `_delivery_closeout_final_artifact_refs()` remains an input compiler for runtime payload normalization only.
- `classify_closeout_final_artifact_ref()` remains an artifact legality / evaluation helper and API-display vocabulary source.
- Existing checker verdict helpers remain execution shells or input compilers; they do not override blocking `DeliverableEvaluation` findings.
- Existing closeout package refs remain API/display compatibility fields; runtime completion uses contract id/version/fingerprint plus final evidence table.
- Failed delivery checker rework keeps the Round 9D upstream target semantics and still requires structured convergence policy for allowed failed-report gaps.

Round 9E verification:

- `pytest --basetemp="D:/Projects/boardroom-os/.pytest-tmp" backend/tests/test_deliverable_contract.py backend/tests/test_workspace_path_contracts.py backend/tests/test_output_schemas.py -q` covers PRD acceptance compiler, source surface mapping, evidence pack mapping, closeout schema contract fields, final table row fields, and superseded/placeholder/archive/unknown/stale/governance/backlog evidence exclusion.
- `pytest --basetemp="D:/Projects/boardroom-os/.pytest-tmp" backend/tests/test_workflow_autopilot.py backend/tests/test_workflow_progression.py -q` covers closeout contract/table gate, stale old attempt exclusion, governance/backlog final ref rejection, graph terminal not replacing contract satisfaction, and closeout proposal contract readiness.
- `pytest --basetemp="D:/Projects/boardroom-os/.pytest-tmp" backend/tests/test_api.py::test_check_internal_checker_approval_on_failed_report_creates_fix_ticket backend/tests/test_api.py::test_autopilot_converged_check_report_without_policy_is_forced_back_to_rework backend/tests/test_api.py::test_structured_convergence_policy_allows_failed_check_report -q` covers failed delivery checker rework and structured convergence policy.
- `pytest --basetemp="D:/Projects/boardroom-os/.pytest-tmp" backend/tests/test_api.py::test_closeout_internal_checker_approved_returns_completion_summary backend/tests/test_api.py::test_manual_closeout_recovery_cannot_bypass_contract_table -q` covers closeout package contract fields and manual closeout recovery not bypassing the contract.
- `rg -n "graph terminal|checker notes|freeform|final_artifact_refs.*satisf" backend/app/core` and `rg -n "_delivery_closeout_final_artifact_refs|classify_closeout_final_artifact_ref|evaluate_deliverable_contract|final_evidence_table" backend/app/core` are the grep acceptance checks for old release paths and retained helper boundaries.

Remaining Phase 6/7 dependencies:

- Round 10A has implemented the minimal replay resume contract and event cursor boundary. Phase 5 deliverable contract semantics are unchanged; replay only records cursor/version/hash diagnostics.
- Phase 6 still owns graph version resume, ticket/incident resume, checkpoints and replay bundle materialization.
- Phase 7 still owns 015 full replay import and replay-case validation for BR-040, BR-041, BR-100 and closeout/manual recovery on real 015 data.
