# V2-100C CEO Rework Planner Boundary Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development（子智能体驱动开发，推荐）or superpowers:executing-plans（按计划执行）to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement V2-100C CEO rework planner boundary（CEO 返工规划边界）so a provider-backed CEO（模型支撑的项目经理）can turn a verified ReworkRequest（返工请求）into a validated ReworkPlan（返工计划）and TicketGraphPatch（工单图补丁）, while multi-role GraphPatchReview（图补丁审查）and ReworkReducer（返工归约器）remain the only path to graph commit.

**Architecture:** Add focused planning and review boundary modules under `src/boardroom_os/rework/`（返工包）. `planner.py` parses and validates strict CEO JSON output against existing V2-100A ReworkPlan / TicketGraphPatch models（返工计划 / 工单图补丁模型）and ProviderAttempt（模型调用尝试记录）lineage; `ticket_graph_patch.py` derives required review domains（必需审查域）and validates active contract scope（活跃合同范围）; `reviewer.py` parses provider-backed domain review outputs（领域审查输出） into GraphPatchReview objects. V2-100C does not execute rework tickets, does not rebuild evidence, and does not close blockers; V2-100D/E own those stages.

**Tech Stack:** Python 3.11+, Pydantic v2, pytest, existing Boardroom OS V2 models: ReworkRequest（返工请求）, ReworkPlan（返工计划）, TicketGraphPatch（工单图补丁）, GraphPatchReview（图补丁审查）, GraphPatchApprovalSet（图补丁批准集）, ReworkReducer（返工归约器）, ProviderAttempt（模型调用尝试记录）, RolePromptHook（角色提示词钩子）, TicketCreatedPayload（工单创建载荷）, AcceptanceContract（验收合同） refs, PackageContract（包合同） refs, SourceSurface（源码面） refs, EvidenceObligation（证据义务） refs.

---

## Scope And Non-Goals

V2-100C owns:

- CEO planner boundary（CEO 规划边界） input/output schemas.
- Strict provider output parser（严格模型输出解析器） for CEO planning and graph patch review.
- ProviderAttempt（模型调用尝试记录） lineage validation for CEO and reviewer outputs.
- Contract-bound TicketGraphPatch（合同绑定工单图补丁） scope validation.
- Required review domain inference（必需审查域推导） for behavioral probe, run/env readiness, and closeout fact-chain issues.
- Reducer-backed happy-path tests（归约器支撑正向测试） proving graph patch commit only after required reviews.

V2-100C does not own:

- Rework domain base objects; V2-100A owns them.
- Rework event taxonomy, GraphPatchReviewGate（图补丁审查门禁）, or reducer state machine; V2-100B owns them.
- ReworkAttempt（返工尝试） execution, SourceInventory（源码清单） rebuild, FinalEvidenceTable（最终证据表） rebuild, CheckerVerdict（检查结论） regeneration, or CloseoutGate（收尾门禁） rerun; V2-100D owns them.
- Multi-round proving script（多轮证明脚本） and resettable failing fixture（可重置失败夹具）; V2-100E owns them.
- Any runtime/helper（运行时/辅助器） auto-repair. Runtime remains a fact executor（事实执行者）.

V2-100C intentionally limits accepted CEO decision kinds to the work package acceptance list:

```text
fix_implementation
fix_contract_or_probe
split_ticket
reorder_dependencies
escalate_human_review
```

The base ReworkDecisionKind（返工决策类型） currently also contains `narrow_scope`（缩小范围） from V2-100A shared vocabulary. V2-100C must reject it until the backlog（任务清单） and Phase 10 acceptance checkbox（第十阶段验收复选项） explicitly include it.

---

## File Structure

- Create `src/boardroom_os/rework/planner.py`
  - CEO planner input/output models（规划器输入/输出模型）, strict payload parser（严格载荷解析器）, ProviderAttempt lineage validation（模型调用来源链校验）, blocker coverage validation（阻塞项覆盖校验）, and planner boundary errors（规划边界错误）.
- Create `src/boardroom_os/rework/ticket_graph_patch.py`
  - Patch scope validation（补丁范围校验）, required review domain inference（必需审查域推导）, patch hash helper（补丁哈希辅助器）, and approval set builder（批准集构建器） that reuses V2-100A models and V2-100B GraphPatchReviewGate（图补丁审查门禁）.
- Create `src/boardroom_os/rework/reviewer.py`
  - Generic reviewer input/output models（通用审查输入/输出模型） plus domain-specific constructors for Architect（架构师）, Checker（检查者）, Tester（测试者）, Release DevOps（发布运维）, and Closeout（收尾） review boundaries.
- Modify `src/boardroom_os/rework/__init__.py`
  - Export new planner/reviewer/patch boundary public names（公共名称） without duplicating reducer APIs.
- Modify `tests/execution/test_role_prompt_hooks_rework_governance.py`
  - Lock the existing baseline RolePromptHook（基线角色提示词钩子） wording needed for V2-100C strict planning and review.
- Create `tests/rework/test_ceo_rework_planner.py`
  - Happy-path CEO planning and graph patch commit tests（正向规划与图补丁提交测试） using V2-090K failure snapshot（失败快照） issues.
- Create `tests/rework/test_multi_role_graph_patch_reviews.py`
  - Multi-role review parser and approval set tests（多角色审查解析与批准集测试）.
- Create `tests/negative/test_ceo_rework_planner_fail_closed.py`
  - CEO planner fail-closed tests（失败关闭测试） for missing ProviderAttempt（模型调用尝试记录）, wrong role hook（错误角色钩子）, unmapped blockers（未映射阻塞项）, stale acceptance refs（陈旧验收引用）, unsafe decision kinds（不安全决策类型）, runtime auto-fix instructions（运行时自动修复指令）, and graph commit bypass（绕过图提交）.
- Create `tests/negative/test_multi_role_graph_patch_reviews_fail_closed.py`
  - Reviewer fail-closed tests（审查失败关闭测试） for prose-only output（仅散文输出）, wrong role/domain mapping（错误角色/审查域映射）, missing checked invariants（缺已检查不变量）, missing required review domains（缺必需审查域）, and review without ProviderAttempt（无模型调用审查）.
- Modify `doc/04-implementation/INDEX.md`
  - Register this implementation plan（实施计划） only. Do not update backlog status（任务状态） or acceptance checkboxes（验收复选项） during plan review.

---

## Public API Target

Implement these public names in `src/boardroom_os/rework/planner.py`.

- `CeoReworkPlannerError`
- `CeoReworkPlannerInput`
- `CeoReworkPlannerOutput`
- `CeoPlannerParsedPayload`
- `CeoReworkPlannerBoundary`
- `parse_ceo_rework_planner_payload(payload: Mapping[str, object]) -> CeoPlannerParsedPayload`
- `validate_ceo_rework_plan(output: CeoReworkPlannerOutput) -> CeoReworkPlannerOutput`

`CeoReworkPlannerInput` required fields:

- `rework_request: ReworkRequest`
- `blocker_reports: tuple[BlockerReport, ...]`
- `current_graph_version: int`
- `active_contract_refs: tuple[ContractId, ...]`
- `active_acceptance_refs: tuple[AcceptanceRef, ...]`
- `active_source_surface_refs: tuple[SourceSurfaceRef, ...]`
- `active_evidence_obligation_refs: tuple[EvidenceObligationRef, ...]`
- `package_contract_ref: ContractId`
- `run_manifest_ref: str`
- `planner_execution_package_ref: ExecutionPackageRef`
- `planner_role_prompt_hook_ref: RolePromptHookRef`

`CeoReworkPlannerOutput` required fields:

- `planner_input: CeoReworkPlannerInput`
- `provider_attempt: ProviderAttempt`
- `plan: ReworkPlan`
- `patch: TicketGraphPatch`
- `parsed_payload_ref: ProviderArtifactRef`
- `validated_at: datetime`

Validation rules:

- `provider_attempt.status` must be `SUCCEEDED`.
- `provider_attempt.outcome` must be `PRIMARY_PROVIDER_OUTPUT`.
- `provider_attempt.provider_attempt_id` must equal `plan.planner_attempt_ref`.
- `provider_attempt.input_package_ref` must equal `planner_input.planner_execution_package_ref`.
- `provider_attempt.role_prompt_hook_ref` must equal `planner_input.planner_role_prompt_hook_ref`.
- `planner_role_prompt_hook_ref` must be the active CEO hook ref from RolePromptHookRegistry（角色提示词钩子注册表）.
- `plan.planner_actor` must be `ReworkActorKind.CEO`.
- Every ReworkIssue.blocker_refs（返工问题阻塞引用） in the request must be mapped by at least one ReworkDecision（返工决策） or by an explicit `escalate_human_review` decision.
- Every non-escalation decision must map to at least one TicketGraphPatchOperation（工单图补丁操作）.
- V2-100C must reject `ReworkDecisionKind.NARROW_SCOPE` until acceptance criteria（验收标准） are updated.
- `patch.base_graph_version` must equal `rework_request.active_graph_version`.
- `patch.proposed_by_plan_ref` must equal `plan.rework_plan_id`.
- `patch.ticket_graph_patch_id` must equal `plan.ticket_graph_patch_ref`.
- All patch acceptance/source/evidence refs must be subsets of active refs from planner input.
- The patch must not contain operations outside GraphPatchOperationKind（图补丁操作类型）.
- The patch cannot close blockers, approve evidence, approve checker verdicts, complete tickets, or request runtime auto-repair.

Implement these public names in `src/boardroom_os/rework/ticket_graph_patch.py`.

- `TicketGraphPatchBoundaryError`
- `RequiredReviewDomainInput`
- `infer_required_review_domains(input: RequiredReviewDomainInput) -> tuple[GraphPatchReviewDomain, ...]`
- `validate_ticket_graph_patch_scope(patch: TicketGraphPatch, *, active_acceptance_refs, active_source_surface_refs, active_evidence_obligation_refs, active_contract_refs) -> TicketGraphPatch`
- `derive_ticket_graph_patch_hash(patch_without_hash: TicketGraphPatch) -> str`
- `build_graph_patch_approval_set(patch: TicketGraphPatch, reviews: tuple[GraphPatchReview, ...], *, computed_at: datetime) -> GraphPatchApprovalSet`

Required review domain rules:

- Always require `planning`, `structural`, and `blocker_coverage`.
- Require `behavioral_probe` when any issue has `PROBE_RESPONSE_SHAPE_MISMATCH`, `CONTRACT_MISMATCH`, or suspected domain `probe`.
- Require `run_env_readiness` when any issue has `ENV_BINDING_NOT_CONVERGED`, `RUN_MANIFEST_MISMATCH`, or suspected domain `run_env`.
- Require `closeout_fact_chain` when any issue has `CLOSEOUT_AUDIT_OLD_RUN_REFS`, `CLOSEOUT_GATE_FAILURE`, or suspected domain `closeout_audit`.

Implement these public names in `src/boardroom_os/rework/reviewer.py`.

- `GraphPatchReviewerError`
- `GraphPatchReviewerInput`
- `GraphPatchReviewerOutput`
- `GraphPatchReviewParsedPayload`
- `parse_graph_patch_review_payload(payload: Mapping[str, object]) -> GraphPatchReviewParsedPayload`
- `validate_graph_patch_review(output: GraphPatchReviewerOutput) -> GraphPatchReviewerOutput`
- `architect_graph_patch_review_input(...) -> GraphPatchReviewerInput`
- `checker_graph_patch_review_input(...) -> GraphPatchReviewerInput`
- `tester_graph_patch_review_input(...) -> GraphPatchReviewerInput`
- `release_devops_graph_patch_review_input(...) -> GraphPatchReviewerInput`
- `closeout_graph_patch_review_input(...) -> GraphPatchReviewerInput`

Reviewer validation rules:

- ProviderAttempt（模型调用尝试记录） must be present, succeeded, primary provider output, and non-fallback.
- ProviderAttempt hook ref/version/hash must match the expected reviewer RolePromptHook（角色提示词钩子） snapshot.
- Reviewer role kind must match GraphPatchReviewDomain（图补丁审查域） using existing V2-100A model rules.
- `APPROVED` review must contain `checked_invariants`.
- `REJECTED` and `NEEDS_CHANGES` must contain blockers.
- Prose-only provider output must fail because parser accepts only a single JSON object with a `review` object.

---

## Pre-Flight Before Implementation

- [ ] **Step 1: Confirm branch and task state**

Run:

```bash
git status --short --branch
test ! -e src/boardroom_os/rework/planner.py
test ! -e src/boardroom_os/rework/ticket_graph_patch.py
test ! -e src/boardroom_os/rework/reviewer.py
test ! -e tests/rework/test_ceo_rework_planner.py
test ! -e tests/negative/test_ceo_rework_planner_fail_closed.py
```

Expected: branch is `rebuild/v2-clean-foundation`; V2-100A and V2-100B are done in `doc/04-implementation/backlog.md`; V2-100C is still pending; target implementation files do not exist. If any target file exists, inspect it first and preserve user changes.

- [ ] **Step 2: Confirm V2-100A/B public APIs exist**

Run:

```bash
PYTHONPATH=src python - <<'PY'
from boardroom_os.reducers.rework import GraphPatchReviewGate, ReworkPlanPayload, ReworkReducer
from boardroom_os.rework.model import (
    GraphPatchApprovalSet,
    GraphPatchReview,
    ReworkPlan,
    ReworkRequest,
    TicketGraphPatch,
)

print("v2-100a-b rework api ok")
PY
```

Expected: prints `v2-100a-b rework api ok`.

- [ ] **Step 3: Confirm V2-090K snapshot input remains available**

Run:

```bash
python - <<'PY'
import json
from pathlib import Path

path = Path("examples/generated-workspaces/tiny-fullstack/30-audit/v2-090k-failure-snapshot/failure-summary.json")
data = json.loads(path.read_text(encoding="utf-8"))
print(data["snapshot_id"])
print([item["failure_id"] for item in data["primary_failures"]])
PY
```

Expected: prints `v2-090k-failure-snapshot.tiny-fullstack.2026-06-13` and the four known failure ids: `probe-response-shape-mismatch`, `env-binding-not-converged`, `final-evidence-uses-old-acceptance-refs`, `closeout-audit-references-old-run`.

- [ ] **Step 4: Run current rework and prompt governance tests before editing**

Run:

```bash
PYTHONPATH=src:. python -m pytest \
  tests/rework/test_rework_model.py \
  tests/rework/test_v2_090k_failure_snapshot_projection.py \
  tests/reducers/test_rework_reducer.py \
  tests/negative/test_rework_model_fail_closed.py \
  tests/negative/test_rework_reducer_fail_closed.py \
  tests/execution/test_role_prompt_hooks_rework_governance.py \
  -q
```

Expected: all selected tests pass before V2-100C implementation starts.

---

### Task 1: Write CEO Planner Fail-Closed Tests

**Files:**
- Create `tests/negative/test_ceo_rework_planner_fail_closed.py`
- Create `tests/rework/test_ceo_rework_planner.py`

- [ ] **Step 1: Add negative test fixtures**

Create `tests/negative/test_ceo_rework_planner_fail_closed.py` with shared values for one V2-090K probe mismatch request. Use these exact constants:

```python
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from boardroom_os.agents.role_prompt_hooks import RolePromptHookRef, RolePromptHookSha256
from boardroom_os.agents.seat import AgentSeatRef
from boardroom_os.contracts.types import AcceptanceRef, ContractId, EvidenceObligationRef, SourceSurfaceRef
from boardroom_os.execution.context_index import ProviderAttemptRef
from boardroom_os.execution.fallback import FallbackKind
from boardroom_os.execution.package import ExecutionPackageRef
from boardroom_os.providers.attempt import (
    ProviderArtifactRef,
    ProviderAttempt,
    ProviderAttemptOutcome,
    ProviderAttemptStatus,
)
from boardroom_os.rework.model import ReworkDecisionKind
from boardroom_os.rework.planner import (
    CeoReworkPlannerBoundary,
    CeoReworkPlannerError,
    CeoReworkPlannerInput,
    CeoReworkPlannerOutput,
    parse_ceo_rework_planner_payload,
)

NOW = datetime(2026, 6, 14, 14, 0, tzinfo=UTC)
CEO_HOOK_REF = RolePromptHookRef(value="role-prompt-hook.baseline.ceo.v1")
CEO_HOOK_SHA = RolePromptHookSha256(value="0" * 64)
PLANNER_PACKAGE = ExecutionPackageRef(value="execution-package.ceo.rework-plan")
CEO_ATTEMPT_REF = ProviderAttemptRef(value="provider-attempt.ceo.rework-plan")
```

Reuse helper constructors from `tests/reducers/test_rework_reducer.py` by importing `_request`, `_plan`, and `_patch` if they remain importable. If importing test helpers is rejected by local conventions during implementation, copy those helper constructors into this file so tests stay self-contained.

- [ ] **Step 2: Add ProviderAttempt helper**

Add this helper:

```python
def _provider_attempt(
    *,
    attempt_ref: ProviderAttemptRef = CEO_ATTEMPT_REF,
    hook_ref: RolePromptHookRef = CEO_HOOK_REF,
    status: ProviderAttemptStatus = ProviderAttemptStatus.SUCCEEDED,
    outcome: ProviderAttemptOutcome = ProviderAttemptOutcome.PRIMARY_PROVIDER_OUTPUT,
) -> ProviderAttempt:
    return ProviderAttempt(
        provider_attempt_id=attempt_ref,
        provider="fake-provider",
        model="gpt-test",
        reasoning_effort="high",
        input_package_ref=PLANNER_PACKAGE,
        seat_ref=AgentSeatRef(value="seat.ceo.delivery"),
        role_prompt_hook_ref=hook_ref,
        role_prompt_hook_version="v1",
        role_prompt_hook_sha256=CEO_HOOK_SHA,
        status=status,
        outcome=outcome,
        started_at=NOW,
        finished_at=NOW,
        raw_output_ref=ProviderArtifactRef(value="provider-artifact.raw.ceo-rework-plan"),
        parsed_output_ref=ProviderArtifactRef(value="provider-artifact.parsed.ceo-rework-plan"),
        fallback_kind=(
            FallbackKind.PROVIDER_UNAVAILABLE
            if outcome is ProviderAttemptOutcome.FALLBACK_ARTIFACT
            else None
        ),
    )
```

- [ ] **Step 3: Add planner input helper**

Add this helper:

```python
def _planner_input() -> CeoReworkPlannerInput:
    return CeoReworkPlannerInput(
        rework_request=_request(),
        blocker_reports=(),
        current_graph_version=40,
        active_contract_refs=(ContractId(value="acceptance.v2-090f"), ContractId(value="package.v2-090f")),
        active_acceptance_refs=(AcceptanceRef(value="acceptance.book.add"),),
        active_source_surface_refs=(SourceSurfaceRef(value="surface.backend.api"),),
        active_evidence_obligation_refs=(EvidenceObligationRef(value="evidence.add.api"),),
        package_contract_ref=ContractId(value="package.v2-090f"),
        run_manifest_ref="run-manifest.v2-090f",
        planner_execution_package_ref=PLANNER_PACKAGE,
        planner_role_prompt_hook_ref=CEO_HOOK_REF,
    )
```

- [ ] **Step 4: Prove missing ProviderAttempt fails**

Add:

```python
def test_ceo_rework_plan_requires_provider_attempt() -> None:
    with pytest.raises(CeoReworkPlannerError, match="provider_attempt is required"):
        CeoReworkPlannerBoundary.validate(
            CeoReworkPlannerOutput(
                planner_input=_planner_input(),
                provider_attempt=None,
                plan=_plan(),
                patch=_patch(),
                parsed_payload_ref=ProviderArtifactRef(value="provider-artifact.parsed.ceo-rework-plan"),
                validated_at=NOW,
            )
        )
```

Run:

```bash
PYTHONPATH=src:. python -m pytest tests/negative/test_ceo_rework_planner_fail_closed.py::test_ceo_rework_plan_requires_provider_attempt -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'boardroom_os.rework.planner'` before implementation.

- [ ] **Step 5: Prove non-CEO hook fails**

Add:

```python
def test_ceo_rework_plan_requires_ceo_role_prompt_hook() -> None:
    output = CeoReworkPlannerOutput(
        planner_input=_planner_input(),
        provider_attempt=_provider_attempt(
            hook_ref=RolePromptHookRef(value="role-prompt-hook.baseline.worker.v1")
        ),
        plan=_plan(),
        patch=_patch(),
        parsed_payload_ref=ProviderArtifactRef(value="provider-artifact.parsed.ceo-rework-plan"),
        validated_at=NOW,
    )

    with pytest.raises(CeoReworkPlannerError, match="CEO role prompt hook"):
        CeoReworkPlannerBoundary.validate(output)
```

- [ ] **Step 6: Prove fallback ProviderAttempt fails**

Add:

```python
def test_ceo_rework_plan_rejects_fallback_provider_attempt() -> None:
    failed_attempt = _provider_attempt(outcome=ProviderAttemptOutcome.FALLBACK_ARTIFACT)

    output = CeoReworkPlannerOutput(
        planner_input=_planner_input(),
        provider_attempt=failed_attempt,
        plan=_plan(),
        patch=_patch(),
        parsed_payload_ref=ProviderArtifactRef(value="provider-artifact.parsed.ceo-rework-plan"),
        validated_at=NOW,
    )

    with pytest.raises(CeoReworkPlannerError, match="primary provider output"):
        CeoReworkPlannerBoundary.validate(output)
```

- [ ] **Step 7: Prove unmapped blockers fail**

Add a helper that removes decision blocker coverage and then add:

```python
def test_ceo_rework_plan_must_map_every_blocker() -> None:
    plan = _plan().model_copy(
        update={
            "decisions": (
                _plan().decisions[0].model_copy(update={"blocker_refs": ()}),
            )
        }
    )
    output = CeoReworkPlannerOutput(
        planner_input=_planner_input(),
        provider_attempt=_provider_attempt(),
        plan=plan,
        patch=_patch(),
        parsed_payload_ref=ProviderArtifactRef(value="provider-artifact.parsed.ceo-rework-plan"),
        validated_at=NOW,
    )

    with pytest.raises((ValidationError, CeoReworkPlannerError), match="blocker"):
        CeoReworkPlannerBoundary.validate(output)
```

- [ ] **Step 8: Prove `narrow_scope` is rejected for V2-100C**

Add:

```python
def test_v2_100c_rejects_narrow_scope_until_acceptance_includes_it() -> None:
    decision = _plan().decisions[0].model_copy(
        update={"decision_kind": ReworkDecisionKind.NARROW_SCOPE}
    )
    plan = _plan().model_copy(update={"decisions": (decision,)})
    output = CeoReworkPlannerOutput(
        planner_input=_planner_input(),
        provider_attempt=_provider_attempt(),
        plan=plan,
        patch=_patch(),
        parsed_payload_ref=ProviderArtifactRef(value="provider-artifact.parsed.ceo-rework-plan"),
        validated_at=NOW,
    )

    with pytest.raises(CeoReworkPlannerError, match="not allowed for V2-100C"):
        CeoReworkPlannerBoundary.validate(output)
```

- [ ] **Step 9: Prove stale acceptance refs fail**

Add:

```python
def test_ceo_graph_patch_rejects_stale_acceptance_refs() -> None:
    operation = _patch().operations[0].model_copy(
        update={"acceptance_refs": (AcceptanceRef(value="AC-TINY-API-BOOK-CREATE"),)}
    )
    patch = _patch().model_copy(update={"operations": (operation,)})
    output = CeoReworkPlannerOutput(
        planner_input=_planner_input(),
        provider_attempt=_provider_attempt(),
        plan=_plan(),
        patch=patch,
        parsed_payload_ref=ProviderArtifactRef(value="provider-artifact.parsed.ceo-rework-plan"),
        validated_at=NOW,
    )

    with pytest.raises(CeoReworkPlannerError, match="unknown acceptance_ref"):
        CeoReworkPlannerBoundary.validate(output)
```

- [ ] **Step 10: Prove prose-only CEO output fails**

Add:

```python
def test_ceo_planner_rejects_prose_only_output() -> None:
    with pytest.raises(CeoReworkPlannerError, match="single JSON object"):
        parse_ceo_rework_planner_payload(
            {"message": "I will ask the runtime to fix this automatically."}
        )
```

- [ ] **Step 11: Run negative tests and verify planned failures**

Run:

```bash
PYTHONPATH=src:. python -m pytest tests/negative/test_ceo_rework_planner_fail_closed.py -q
```

Expected: FAIL until `src/boardroom_os/rework/planner.py` exists and enforces the boundary.

---

### Task 2: Implement CEO Planner Boundary

**Files:**
- Create `src/boardroom_os/rework/planner.py`
- Modify `src/boardroom_os/rework/__init__.py`

- [ ] **Step 1: Create planner error and models**

Implement `CeoReworkPlannerError`, `CeoReworkPlannerInput`, `CeoPlannerParsedPayload`, and `CeoReworkPlannerOutput` with frozen Pydantic models（不可变 Pydantic 模型） and `extra="forbid"`（禁止额外字段）.

Required model rules:

- Text refs (`run_manifest_ref`) must be non-empty.
- `current_graph_version` must be positive.
- Active refs tuples must be non-empty and unique.
- `provider_attempt` is typed as `ProviderAttempt | None` only so the fail-closed test can prove missing attempt is rejected by boundary validation.
- `validated_at` must be timezone-aware.

- [ ] **Step 2: Implement strict parser**

Implement `parse_ceo_rework_planner_payload(payload)` so the only accepted shape is:

```json
{
  "plan": { "rework_plan_id": { "value": "rework-plan.v2-100c" } },
  "patch": { "ticket_graph_patch_id": { "value": "ticket-graph-patch.v2-100c" } }
}
```

Actual objects must be parsed through existing `ReworkPlan.model_validate(...)` and `TicketGraphPatch.model_validate(...)`. Unknown top-level keys, missing `plan`, missing `patch`, or prose-only keys such as `message`, `summary`, `runtime_fix`, `approved`, or `completed` must raise `CeoReworkPlannerError("CEO planner output must be a single JSON object with plan and patch")`.

- [ ] **Step 3: Implement ProviderAttempt validation**

In `CeoReworkPlannerBoundary.validate(output)`, fail closed when:

- `output.provider_attempt is None`
- provider attempt status is not `SUCCEEDED`
- provider attempt outcome is not `PRIMARY_PROVIDER_OUTPUT`
- provider attempt ref does not equal plan planner attempt ref
- provider attempt input package ref does not equal planner execution package ref
- provider attempt role prompt hook ref does not equal planner input CEO hook ref
- planner input hook ref is not `role-prompt-hook.baseline.ceo.v1`
- plan planner actor is not `ReworkActorKind.CEO`

- [ ] **Step 4: Implement request/plan/patch binding validation**

Fail closed when:

- `plan.rework_request_id != input.rework_request.rework_request_id`
- `plan.cycle_id != input.rework_request.cycle_id`
- `patch.proposed_by_plan_ref != plan.rework_plan_id`
- `patch.ticket_graph_patch_id != plan.ticket_graph_patch_ref`
- `patch.base_graph_version != input.rework_request.active_graph_version`
- `input.current_graph_version != input.rework_request.active_graph_version`

- [ ] **Step 5: Implement blocker coverage validation**

Compute request blocker refs from every `issue.blocker_refs`. Compute planned blocker refs from every decision. Fail closed when any request blocker is missing from planned decisions. Escalation decisions count only when `decision_kind` is `ESCALATE_HUMAN_REVIEW`.

- [ ] **Step 6: Implement decision policy validation**

Accept only:

- `FIX_IMPLEMENTATION`
- `FIX_CONTRACT_OR_PROBE`
- `SPLIT_TICKET`
- `REORDER_DEPENDENCIES`
- `ESCALATE_HUMAN_REVIEW`

Reject `NARROW_SCOPE` with message `decision kind is not allowed for V2-100C`.

Also fail closed when a non-escalation decision has no `target_ticket_refs` and no `target_graph_operation_refs`.

- [ ] **Step 7: Delegate patch scope validation**

Call `validate_ticket_graph_patch_scope(...)` from `ticket_graph_patch.py` with active refs from planner input. Until Task 3 creates that module, define a private local helper with the same behavior, then replace it in Task 3 in the same implementation commit.

- [ ] **Step 8: Export public names**

Update `src/boardroom_os/rework/__init__.py` to export planner names:

```python
from boardroom_os.rework.planner import (
    CeoPlannerParsedPayload,
    CeoReworkPlannerBoundary,
    CeoReworkPlannerError,
    CeoReworkPlannerInput,
    CeoReworkPlannerOutput,
    parse_ceo_rework_planner_payload,
    validate_ceo_rework_plan,
)
```

- [ ] **Step 9: Run planner negative tests**

Run:

```bash
PYTHONPATH=src:. python -m pytest tests/negative/test_ceo_rework_planner_fail_closed.py -q
```

Expected: all tests in this file pass.

---

### Task 3: Implement TicketGraphPatch Scope And Review-Domain Boundary

**Files:**
- Create `src/boardroom_os/rework/ticket_graph_patch.py`
- Modify `src/boardroom_os/rework/planner.py`
- Create `tests/rework/test_multi_role_graph_patch_reviews.py`
- Create `tests/negative/test_multi_role_graph_patch_reviews_fail_closed.py`

- [ ] **Step 1: Write review domain inference tests**

Create `tests/rework/test_multi_role_graph_patch_reviews.py` with tests:

```python
def test_probe_response_shape_patch_requires_tester_review() -> None:
    domains = infer_required_review_domains(
        RequiredReviewDomainInput(issues=(_probe_response_shape_issue(),), operations=(_patch().operations[0],))
    )

    assert domains == (
        GraphPatchReviewDomain.PLANNING,
        GraphPatchReviewDomain.STRUCTURAL,
        GraphPatchReviewDomain.BLOCKER_COVERAGE,
        GraphPatchReviewDomain.BEHAVIORAL_PROBE,
    )


def test_env_binding_patch_requires_release_devops_review() -> None:
    domains = infer_required_review_domains(
        RequiredReviewDomainInput(issues=(_env_binding_issue(),), operations=(_patch().operations[0],))
    )

    assert GraphPatchReviewDomain.RUN_ENV_READINESS in domains


def test_closeout_old_run_patch_requires_fact_chain_review() -> None:
    domains = infer_required_review_domains(
        RequiredReviewDomainInput(issues=(_closeout_old_run_issue(),), operations=(_patch().operations[0],))
    )

    assert GraphPatchReviewDomain.CLOSEOUT_FACT_CHAIN in domains
```

Use helper issues from the V2-090K snapshot projection where possible; if helper extraction makes tests harder to read, construct explicit ReworkIssue values in the test file.

- [ ] **Step 2: Write patch scope negative tests**

Create `tests/negative/test_multi_role_graph_patch_reviews_fail_closed.py` with:

```python
def test_patch_scope_rejects_acceptance_refs_outside_active_contract() -> None:
    operation = _patch().operations[0].model_copy(
        update={"acceptance_refs": (AcceptanceRef(value="acceptance.not-active"),)}
    )
    patch = _patch().model_copy(update={"operations": (operation,)})

    with pytest.raises(TicketGraphPatchBoundaryError, match="unknown acceptance_ref"):
        validate_ticket_graph_patch_scope(
            patch,
            active_acceptance_refs=(AcceptanceRef(value="acceptance.book.add"),),
            active_source_surface_refs=(SourceSurfaceRef(value="surface.backend.api"),),
            active_evidence_obligation_refs=(EvidenceObligationRef(value="evidence.add.api"),),
            active_contract_refs=(ContractId(value="acceptance.v2-090f"),),
        )
```

Add equivalent tests for unknown source surface and unknown evidence obligation.

- [ ] **Step 3: Implement RequiredReviewDomainInput**

Implement a frozen model:

```python
class RequiredReviewDomainInput(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    issues: tuple[ReworkIssue, ...]
    operations: tuple[TicketGraphPatchOperation, ...]
```

Both tuples must be non-empty.

- [ ] **Step 4: Implement infer_required_review_domains**

Return domains in stable order:

```python
(
    GraphPatchReviewDomain.PLANNING,
    GraphPatchReviewDomain.STRUCTURAL,
    GraphPatchReviewDomain.BLOCKER_COVERAGE,
    optional GraphPatchReviewDomain.BEHAVIORAL_PROBE,
    optional GraphPatchReviewDomain.RUN_ENV_READINESS,
    optional GraphPatchReviewDomain.CLOSEOUT_FACT_CHAIN,
)
```

Derive optional domains using the rules from Public API Target. Do not infer domains from file path prefixes.

- [ ] **Step 5: Implement validate_ticket_graph_patch_scope**

Validate each `TicketGraphPatchOperation`:

- every `acceptance_ref` is in `active_acceptance_refs`
- every `source_surface_ref` is in `active_source_surface_refs`
- every `evidence_obligation_ref` is in `active_evidence_obligation_refs`
- every `affected_contract_ref` is in `active_contract_refs`
- every operation target ticket appears in `patch.affected_ticket_refs`
- patch has `planning`, `structural`, and `blocker_coverage` in `required_review_domains`

- [ ] **Step 6: Implement derive_ticket_graph_patch_hash**

Use existing `canonical_rework_hash(...)` over a patch copy with an empty placeholder hash normalized to `sha256:pending` before hashing. Return `sha256:<64 lowercase hex>`. Tests should assert that identical patches produce identical hashes and changed operations change the hash.

- [ ] **Step 7: Implement build_graph_patch_approval_set**

Build `GraphPatchApprovalSet` from patch and reviews:

- `approval_set_id`: `graph-patch-approval.<first16_of_patch_hash>`
- `required_domains`: `patch.required_review_domains`
- `reviews`: provided reviews
- `status`: `READY_TO_COMMIT` only if every required domain has an approved review; otherwise `INCOMPLETE`
- `computed_at`: caller-supplied timezone-aware datetime

Do not call reducer commit here. This function only constructs typed approval input for GraphPatchReviewGate（图补丁审查门禁）.

- [ ] **Step 8: Replace planner local helper**

Modify `src/boardroom_os/rework/planner.py` to import and call `validate_ticket_graph_patch_scope`.

- [ ] **Step 9: Run patch boundary tests**

Run:

```bash
PYTHONPATH=src:. python -m pytest \
  tests/rework/test_multi_role_graph_patch_reviews.py \
  tests/negative/test_multi_role_graph_patch_reviews_fail_closed.py \
  -q
```

Expected: patch boundary tests pass.

---

### Task 4: Implement Graph Patch Reviewer Boundary

**Files:**
- Create `src/boardroom_os/rework/reviewer.py`
- Modify `src/boardroom_os/rework/__init__.py`
- Modify `tests/rework/test_multi_role_graph_patch_reviews.py`
- Modify `tests/negative/test_multi_role_graph_patch_reviews_fail_closed.py`

- [ ] **Step 1: Write reviewer parser negative tests**

Add:

```python
def test_reviewer_rejects_prose_without_review_schema() -> None:
    with pytest.raises(GraphPatchReviewerError, match="single JSON object"):
        parse_graph_patch_review_payload({"message": "looks good"})
```

- [ ] **Step 2: Write wrong-role negative test**

Add:

```python
def test_architect_review_cannot_claim_checker_domain() -> None:
    review = _review(GraphPatchReviewDomain.BLOCKER_COVERAGE, ReworkActorKind.ARCHITECT)

    with pytest.raises((ValidationError, GraphPatchReviewerError), match="reviewer_role_kind"):
        GraphPatchReviewerOutput(
            reviewer_input=architect_graph_patch_review_input(
                patch=_patch(),
                expected_provider_attempt_ref=ProviderAttemptRef(value="provider-attempt.architect.review"),
            ),
            provider_attempt=_architect_attempt(),
            review=review,
            parsed_payload_ref=ProviderArtifactRef(value="provider-artifact.parsed.architect-review"),
            validated_at=NOW,
        )
```

- [ ] **Step 3: Write missing checked invariants negative test**

Add:

```python
def test_approved_review_requires_checked_invariants() -> None:
    with pytest.raises(ValidationError, match="checked_invariants"):
        _review(GraphPatchReviewDomain.STRUCTURAL, ReworkActorKind.ARCHITECT).model_copy(
            update={"checked_invariants": ()}
        )
```

- [ ] **Step 4: Implement reviewer models**

Implement:

- `GraphPatchReviewerInput`
- `GraphPatchReviewParsedPayload`
- `GraphPatchReviewerOutput`

Required fields for `GraphPatchReviewerInput`:

- `patch: TicketGraphPatch`
- `review_domain: GraphPatchReviewDomain`
- `reviewer_role_kind: ReworkActorKind`
- `expected_provider_attempt_ref: ProviderAttemptRef`
- `reviewer_execution_package_ref: ExecutionPackageRef`
- `reviewer_role_prompt_hook_ref: RolePromptHookRef`

- [ ] **Step 5: Implement parser**

Accept only:

```json
{
  "review": {
    "graph_patch_review_id": {"value": "graph-patch-review.structural"},
    "ticket_graph_patch_ref": {"value": "ticket-graph-patch.v2-100c"},
    "review_domain": "structural",
    "reviewer_actor": "architect",
    "reviewer_role_kind": "architect",
    "reviewer_attempt_ref": {"value": "provider-attempt.architect.review"},
    "status": "approved",
    "checked_invariants": ["contract refs checked"],
    "blockers": [],
    "non_blocking_notes": [],
    "created_at": "2026-06-14T14:00:00+00:00"
  }
}
```

Unknown top-level keys or prose-only output must fail.

- [ ] **Step 6: Implement ProviderAttempt and hook validation**

`validate_graph_patch_review(output)` must fail when:

- provider attempt missing
- provider attempt failed
- provider attempt is fallback
- provider attempt id does not equal expected attempt ref
- provider attempt input package does not equal reviewer execution package ref
- provider attempt hook ref does not equal reviewer expected hook ref
- review domain differs from reviewer input domain
- review reviewer role kind differs from reviewer input role kind
- review ticket patch ref differs from input patch id

- [ ] **Step 7: Implement domain-specific input constructors**

Constructors must set expected role and hook refs:

- Architect structural review: `GraphPatchReviewDomain.STRUCTURAL`, `ReworkActorKind.ARCHITECT`, `role-prompt-hook.baseline.architect.v1`
- Checker blocker coverage review: `GraphPatchReviewDomain.BLOCKER_COVERAGE`, `ReworkActorKind.CHECKER`, `role-prompt-hook.baseline.checker.v1`
- Tester behavioral probe review: `GraphPatchReviewDomain.BEHAVIORAL_PROBE`, `ReworkActorKind.TESTER`, `role-prompt-hook.baseline.tester.v1`
- Release DevOps run/env/readiness review: `GraphPatchReviewDomain.RUN_ENV_READINESS`, `ReworkActorKind.RELEASE_DEVOPS`, `role-prompt-hook.baseline.release-devops.v1`
- Closeout fact-chain review: `GraphPatchReviewDomain.CLOSEOUT_FACT_CHAIN`, `ReworkActorKind.CLOSEOUT`, `role-prompt-hook.baseline.closeout.v1`

- [ ] **Step 8: Export reviewer names**

Update `src/boardroom_os/rework/__init__.py` with reviewer public names.

- [ ] **Step 9: Run reviewer tests**

Run:

```bash
PYTHONPATH=src:. python -m pytest \
  tests/rework/test_multi_role_graph_patch_reviews.py \
  tests/negative/test_multi_role_graph_patch_reviews_fail_closed.py \
  -q
```

Expected: all reviewer boundary tests pass.

---

### Task 5: Prove CEO Planning Happy Paths With Reducer Commit

**Files:**
- Modify `tests/rework/test_ceo_rework_planner.py`

- [ ] **Step 1: Add V2-090K request helper**

Use `project_v2_090k_failure_summary(...)` from `boardroom_os.rework.blocker_projection`（返工阻塞投影） to construct a ReworkRequest（返工请求） from:

```text
examples/generated-workspaces/tiny-fullstack/30-audit/v2-090k-failure-snapshot/failure-summary.json
```

The helper must use active refs already proven by `tests/rework/test_v2_090k_failure_snapshot_projection.py`.

- [ ] **Step 2: Add probe mismatch happy path**

Test scenario:

- Input issue: `PROBE_RESPONSE_SHAPE_MISMATCH`
- CEO decision: `FIX_IMPLEMENTATION` or `FIX_CONTRACT_OR_PROBE`
- Required reviews: planning, structural, blocker coverage, behavioral probe
- Rework ticket target: `ticket.rework.backend-api-shape`
- Reducer sequence:
  - `REWORK_REQUESTED`
  - `REWORK_PLANNED`
  - one `REWORK_GRAPH_PATCH_REVIEWED` per required review
  - `REWORK_GRAPH_PATCH_APPROVED`
  - `REWORK_TICKET_CREATED`

Assert:

- planner output validates
- approval set is `READY_TO_COMMIT`
- `GraphPatchReviewGate.evaluate(...)` passes
- ReworkReducer（返工归约器） projection status is `EXECUTING`
- projection contains `ticket.rework.backend-api-shape`

- [ ] **Step 3: Add env binding happy path**

Test scenario:

- Input issue: `ENV_BINDING_NOT_CONVERGED`
- CEO decision: `FIX_IMPLEMENTATION` or `FIX_CONTRACT_OR_PROBE`
- Required reviews include `RUN_ENV_READINESS`
- Rework ticket target: `ticket.rework.run-manifest-env-binding`

Assert Release DevOps（发布运维） review is required and reducer commits only after Release DevOps approved review exists.

- [ ] **Step 4: Add stale acceptance refs happy path**

Test scenario:

- Input issue: `FINAL_EVIDENCE_OLD_ACCEPTANCE_REFS`
- CEO decision: `FIX_IMPLEMENTATION` targeting evidence projection rebuild
- Required reviews: planning, structural, blocker coverage
- Rework ticket target: `ticket.rework.final-evidence-active-refs`

Assert no `AC-TINY-*` ref appears in plan decisions, patch operations, or created rework ticket payload.

- [ ] **Step 5: Add closeout old-run happy path**

Test scenario:

- Input issue: `CLOSEOUT_AUDIT_OLD_RUN_REFS`
- CEO decision: `FIX_IMPLEMENTATION` or `SPLIT_TICKET`
- Required reviews include `CLOSEOUT_FACT_CHAIN`
- Rework ticket target: `ticket.rework.closeout-same-run-fact-chain`

Assert Closeout（收尾） or Checker（检查者） fact-chain review is required and reducer commits only after that review exists.

- [ ] **Step 6: Run happy-path tests**

Run:

```bash
PYTHONPATH=src:. python -m pytest tests/rework/test_ceo_rework_planner.py -q
```

Expected: all V2-100C happy paths pass.

---

### Task 6: Lock RolePromptHook Rework Governance Requirements

**Files:**
- Modify `tests/execution/test_role_prompt_hooks_rework_governance.py`
- Modify prompt templates under `src/boardroom_os/agents/prompt_templates/baseline/v1/` only if tests prove a required phrase is absent.

- [ ] **Step 1: Add CEO strict output and allowed decision assertions**

Append:

```python
def test_ceo_prompt_locks_v2_100c_decision_space_and_json_output() -> None:
    prompt = _prompt("ceo")

    assert "one json object only" in prompt
    assert "fix_implementation" in prompt
    assert "fix_contract_or_probe" in prompt
    assert "split_ticket" in prompt
    assert "reorder_dependencies" in prompt
    assert "escalate_human_review" in prompt
    assert "runtime" in prompt
    assert "do not write implementation files" in prompt
```

- [ ] **Step 2: Add reviewer prompt assertions**

Append assertions that:

- Architect prompt mentions `allowed_write_set`, `source surfaces`, and `graph patch`.
- Checker prompt mentions `blocker coverage`, `old run ids`, and `fresh verified evidence`.
- Tester prompt mentions `response shape` and `fix contract or probe`.
- Release DevOps prompt mentions `environment mapping`, `readiness`, and `run/env/readiness`.
- Closeout prompt mentions `same-run`, `old run refs`, and `CloseoutGate`.

Existing tests already cover most of these terms; keep duplicates minimal and make missing V2-100C-specific terms explicit.

- [ ] **Step 3: Run prompt governance tests**

Run:

```bash
PYTHONPATH=src:. python -m pytest tests/execution/test_role_prompt_hooks_rework_governance.py -q
```

Expected: pass. If a required term is absent, update only the relevant prompt template and rerun. Do not claim prompt text replaces programmatic gates.

---

### Task 7: Run Focused And Regression Verification

**Files:**
- No new files unless implementation discovered a necessary import/export fix.

- [ ] **Step 1: Run V2-100C focused tests**

Run:

```bash
PYTHONPATH=src:. python -m pytest \
  tests/negative/test_ceo_rework_planner_fail_closed.py \
  tests/negative/test_multi_role_graph_patch_reviews_fail_closed.py \
  tests/rework/test_ceo_rework_planner.py \
  tests/rework/test_multi_role_graph_patch_reviews.py \
  tests/execution/test_role_prompt_hooks_rework_governance.py \
  -q
```

Expected: all focused tests pass.

- [ ] **Step 2: Run rework reducer regression tests**

Run:

```bash
PYTHONPATH=src:. python -m pytest \
  tests/rework/test_rework_model.py \
  tests/rework/test_v2_090k_failure_snapshot_projection.py \
  tests/reducers/test_rework_reducer.py \
  tests/negative/test_rework_model_fail_closed.py \
  tests/negative/test_rework_reducer_fail_closed.py \
  -q
```

Expected: all V2-100A/B regression tests pass.

- [ ] **Step 3: Run broader affected suite**

Run:

```bash
PYTHONPATH=src:. python -m pytest \
  tests/contracts \
  tests/reducers \
  tests/execution \
  tests/evidence \
  tests/closeout \
  tests/rework \
  tests/negative \
  -q
```

Expected: existing affected suite passes. If unrelated failures appear, record them with exact failing test names and do not mark V2-100C complete until the V2-100C-relevant failures are resolved or clearly isolated.

---

### Task 8: Completion Documentation Updates After Implementation

**Files:**
- Modify `doc/04-implementation/backlog.md`
- Modify `doc/04-implementation/acceptance-criteria.md`
- Modify `doc/05-project-log/2026-06.md`
- Modify `doc/04-implementation/INDEX.md` only if implementation adds new Markdown files beyond this plan.

- [ ] **Step 1: Update backlog only after tests pass**

In `doc/04-implementation/backlog.md`:

- Change V2-100C status from pending to done.
- Add completion evidence under V2-100C with exact test commands and pass counts.
- Update current incomplete work package from `V2-100C` to `V2-100D`.
- Update Phase 10 progress from `2 / 5` to `3 / 5`.
- Update total progress from `71 / 75` to `72 / 75`.

- [ ] **Step 2: Update acceptance checkbox**

In `doc/04-implementation/acceptance-criteria.md`, check:

```markdown
- [x] AC-V2-REWORK-003 / AC-V2-AGENT-001（CEO 返工规划受合同和模型调用审计约束）...
```

Do not check V2-100D or V2-100E items.

- [ ] **Step 3: Update monthly project log**

Append one `2026-06-14 — V2-100C CEO rework planner boundary` entry to `doc/05-project-log/2026-06.md` with:

- key output files
- negative tests run
- happy-path tests run
- broader verification command
- note that V2-100D/E remain pending

- [ ] **Step 4: Do not update decisions unless implementation changes architecture**

Do not add a decision entry for this plan. Add `DEC-XXXX` only if implementation changes the accepted V2-100 architecture, decision kind set, or runtime/reducer boundary.

---

## Self-Review

### Spec Coverage

- V2-100C missing CEO ProviderAttempt（模型调用尝试记录） failure is covered by Task 1 and Task 2.
- Blocker-to-decision mapping is covered by Task 1, Task 2, and Task 5.
- Allowed decision set is covered by Task 1 and Task 2, including explicit rejection of `narrow_scope` for this work package.
- Direct source edits, passed verdicts, ticket completion, and runtime auto-repair are blocked by strict parser shape, existing graph patch operation enum（图补丁操作枚举）, and Task 2 validation.
- Active contract / source surface / evidence obligation scope is covered by Task 3 and Task 5.
- Multi-role review is covered by Task 3, Task 4, and reducer-backed Task 5.
- RolePromptHook（角色提示词钩子） audit requirements are covered by Task 2, Task 4, and Task 6.

### Placeholder Scan

This plan contains no placeholder tokens, deferred implementation notes, or open-ended tasks. Every created/modified file is named explicitly, and each verification command has an expected result.

### Type Consistency

The plan uses existing V2-100A/B public types: `ReworkRequest`, `ReworkPlan`, `TicketGraphPatch`, `GraphPatchReview`, `GraphPatchApprovalSet`, `ReworkReducer`, `ProviderAttempt`, `ProviderAttemptRef`, `ExecutionPackageRef`, `RolePromptHookRef`, and `TicketCreatedPayload`. The only deliberate policy restriction is V2-100C rejection of `ReworkDecisionKind.NARROW_SCOPE` because the current backlog and Phase 10 checkbox do not list it as accepted planner output.

### Scope Check

The plan is scoped to planner/reviewer/patch proposal boundaries. It does not rebuild SourceInventory（源码清单）, FinalEvidenceTable（最终证据表）, CheckerVerdict（检查结论）, or CloseoutPackage（收尾包） because those belong to V2-100D/E.
