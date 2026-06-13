# V2-100A Rework Domain Model Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development（子智能体驱动开发，推荐）or superpowers:executing-plans（按计划执行）to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement V2-100A Rework domain model（返工领域模型）so verified blockers（已验证阻塞项）from evidence/checker/closeout（证据/检查/收尾）can become typed ReworkRequest（返工请求）、ReworkIssue（返工问题）、ReworkPlan（返工计划）、ReworkAttempt（返工尝试）and ReworkOutcome（返工结果）objects.

**Architecture:** Add a focused `boardroom_os.rework` package（返工包）with pure Pydantic v2 frozen models（不可变模型）in `model.py` and explicit blocker projection（阻塞项投影）helpers in `blocker_projection.py`. V2-100A does not commit TicketGraph（工单图）changes, does not run provider（模型供应商）, and does not decide rework acceptance（返工接受）; it only defines fail-closed typed objects and projection boundaries that V2-100B/C/D will consume.

**Tech Stack:** Python 3.11+, Pydantic v2, pytest, existing Boardroom OS V2 models: FinalEvidenceTable（最终证据表）, CheckerVerdict（检查结论）, CloseoutGateResult（收尾门禁结果）, ExecutionPackage（执行包）, ProviderAttemptRef（模型调用尝试引用）, SourceInventory（源码清单）lineage refs, RunManifest（运行清单）refs, AcceptanceContract（验收合同）refs and PackageContract（包合同）refs.

---

## File Structure

- Create `src/boardroom_os/rework/__init__.py`
  - Public exports for V2-100A domain objects（领域对象）and projection helpers（投影辅助器）.
- Create `src/boardroom_os/rework/model.py`
  - Value objects（值对象）, enums（枚举）, frozen Pydantic models（不可变 Pydantic 模型）, deterministic hash helper（确定性哈希辅助器）, and contract-scope validators（合同范围校验器）.
- Create `src/boardroom_os/rework/blocker_projection.py`
  - Projection from FinalEvidenceTable missing/failed row（最终证据表缺失/失败行）, CheckerVerdict blocker（检查结论阻塞项）, CloseoutGate failure（收尾门禁失败）, and V2-090K curated failure summary（精选失败摘要）into BlockerReport（阻塞报告）, ReworkIssue（返工问题）, and ReworkRequest（返工请求）.
- Create `tests/rework/test_rework_model.py`
  - Happy-path model construction（正向模型构造）, serialization（序列化）, deterministic hash（确定性哈希）, and full request/plan/attempt/outcome chain（完整请求/计划/尝试/结果链）.
- Create `tests/rework/test_v2_090k_failure_snapshot_projection.py`
  - Projection coverage for `examples/generated-workspaces/tiny-fullstack/30-audit/v2-090k-failure-snapshot/failure-summary.json`.
- Create `tests/negative/test_rework_model_fail_closed.py`
  - Fail-closed negative tests（失败关闭负例）for missing verified blocker（缺已验证阻塞项）, stale acceptance refs（陈旧验收引用）, missing provider attempt（缺模型调用尝试）, missing evidence/source lineage（缺证据/源码来源链）, and invalid acceptance（无效接受）.
- Modify `doc/04-implementation/INDEX.md`
  - Register this implementation plan（实施计划）only. Do not mark V2-100A DONE in backlog（任务清单）during plan drafting.

---

## Public API Target

Implement these public names in `src/boardroom_os/rework/model.py`.

Value objects（值对象）:

- `BlockerReportId`
- `BlockerRef`
- `ObservedFactRef`
- `ExpectedFactRef`
- `RunId`
- `ReworkCycleId`
- `ReworkRequestId`
- `ReworkIssueId`
- `ReworkPlanId`
- `ReworkDecisionId`
- `TicketGraphPatchId`
- `TicketGraphPatchOperationId`
- `GraphPatchReviewId`
- `GraphPatchApprovalSetId`
- `ReworkAttemptId`
- `ReworkOutcomeId`
- `ReworkTerminationDecisionId`

Enums（枚举）:

- `BlockerSourceKind`
- `ReworkActorKind`
- `ReworkCycleStatus`
- `ReworkIssueCode`
- `ReworkIssueSeverity`
- `ReworkSuspectedDomain`
- `ReworkDecisionKind`
- `GraphPatchOperationKind`
- `GraphPatchReviewDomain`
- `GraphPatchReviewStatus`
- `GraphPatchApprovalStatus`
- `ReworkOutcomeStatus`
- `ReworkTerminationReason`

Models（模型）:

- `BlockerReport`
- `ReworkIssue`
- `ReworkRequest`
- `ReworkCycle`
- `ReworkDecision`
- `ReworkPlan`
- `TicketGraphPatchOperation`
- `TicketGraphPatch`
- `GraphPatchReview`
- `GraphPatchApprovalSet`
- `ReworkAttempt`
- `ReworkOutcome`
- `ReworkTerminationDecision`

Helpers（辅助器）:

- `canonical_rework_hash(model: BaseModel) -> str`
- `validate_issue_contract_scope(issue, *, active_acceptance_refs, active_source_surface_refs, active_evidence_obligation_refs) -> None`
- `validate_request_verified_sources(request, blocker_reports) -> None`

Implement these public names in `src/boardroom_os/rework/blocker_projection.py`.

- `BlockerProjectionContext`
- `project_final_evidence_table_blockers(table, context) -> ReworkRequest`
- `project_checker_verdict_blockers(verdict, context) -> ReworkRequest`
- `project_closeout_gate_blockers(closeout_gate_result, context) -> ReworkRequest`
- `project_v2_090k_failure_summary(summary_path, context) -> ReworkRequest`

---

## Pre-flight Before Implementation

- [ ] **Step 1: Confirm branch and task state**

Run:

```bash
git status --short --branch
test ! -e src/boardroom_os/rework/model.py
test ! -e tests/rework/test_rework_model.py
test ! -e tests/negative/test_rework_model_fail_closed.py
```

Expected: branch is `rebuild/v2-clean-foundation`, existing unrelated changes are understood before editing, and the three `test ! -e ...` checks pass. If any V2-100A implementation file already exists, inspect it first and preserve user changes.

- [ ] **Step 2: Confirm the V2-090K snapshot input is available**

Run:

```bash
python - <<'PY'
import json
from pathlib import Path

path = Path("examples/generated-workspaces/tiny-fullstack/30-audit/v2-090k-failure-snapshot/failure-summary.json")
data = json.loads(path.read_text(encoding="utf-8"))
failure_ids = [item["failure_id"] for item in data["primary_failures"]]
print(data["snapshot_id"])
print(failure_ids)
assert failure_ids == [
    "probe-response-shape-mismatch",
    "env-binding-not-converged",
    "final-evidence-uses-old-acceptance-refs",
    "closeout-audit-references-old-run",
]
PY
```

Expected: prints the V2-090K snapshot id（快照 ID）and the four known failure ids（失败 ID）in order.

- [ ] **Step 3: Confirm local import style**

Run:

```bash
PYTHONPATH=src python - <<'PY'
from boardroom_os.evidence.table import FinalEvidenceTable
from boardroom_os.checker.verdict import CheckerVerdict
from boardroom_os.closeout.gate import CloseoutGateResult
from boardroom_os.execution.package import ExecutionPackageRef
from boardroom_os.execution.context_index import ProviderAttemptRef
print("v2 model imports ok")
PY
```

Expected: prints `v2 model imports ok`.

---

### Task 1: Write fail-closed tests for raw domain models

**Files:**
- Create `tests/negative/test_rework_model_fail_closed.py`

- [ ] **Step 1: Create negative test fixtures**

Add helper values at the top of `tests/negative/test_rework_model_fail_closed.py`:

```python
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from boardroom_os.contracts.evidence_obligation import RequiredArtifactType
from boardroom_os.contracts.types import AcceptanceRef, ContractId, EvidenceObligationRef, SourceSurfaceRef
from boardroom_os.execution.context_index import ProviderAttemptRef
from boardroom_os.execution.package import ExecutionPackageRef
from boardroom_os.graph.ticket import TicketId
from boardroom_os.rework.model import (
    BlockerRef,
    BlockerReport,
    BlockerReportId,
    BlockerSourceKind,
    ExpectedFactRef,
    GraphPatchOperationKind,
    ObservedFactRef,
    ReworkActorKind,
    ReworkDecision,
    ReworkDecisionId,
    ReworkDecisionKind,
    ReworkIssue,
    ReworkIssueCode,
    ReworkIssueId,
    ReworkIssueSeverity,
    ReworkOutcome,
    ReworkOutcomeId,
    ReworkOutcomeStatus,
    ReworkPlan,
    ReworkPlanId,
    ReworkRequest,
    ReworkRequestId,
    ReworkSuspectedDomain,
    RunId,
    TicketGraphPatchId,
    validate_issue_contract_scope,
)

NOW = datetime(2026, 6, 13, 10, 0, tzinfo=UTC)
ACTIVE_ACCEPTANCE = (AcceptanceRef(value="acceptance.book.add"),)
ACTIVE_SURFACES = (SourceSurfaceRef(value="surface.backend.api"),)
ACTIVE_OBLIGATIONS = (EvidenceObligationRef(value="evidence.add.api"),)
```

- [ ] **Step 2: Add helper constructors**

Add compact helpers that are reused by every negative case:

```python
def _blocker_report() -> BlockerReport:
    return BlockerReport(
        blocker_report_id=BlockerReportId(value="blocker-report.final-evidence.add"),
        run_id=RunId(value="run-v2-100a"),
        source_kind=BlockerSourceKind.FINAL_EVIDENCE_TABLE,
        source_ref="final-evidence-table.acceptance.v2-090f",
        contract_refs=(ContractId(value="acceptance.v2-090f"),),
        acceptance_refs=ACTIVE_ACCEPTANCE,
        package_contract_ref=ContractId(value="package.v2-090f"),
        run_manifest_ref="run-manifest.v2-090f",
        blockers=(BlockerRef(value="final-evidence-blocker.failed.acceptance.book.add.probe"),),
        created_at=NOW,
    )


def _issue() -> ReworkIssue:
    return ReworkIssue(
        issue_id=ReworkIssueId(value="rework-issue.probe-response-shape-mismatch"),
        blocker_refs=(BlockerRef(value="final-evidence-blocker.failed.acceptance.book.add.probe"),),
        issue_code=ReworkIssueCode.PROBE_RESPONSE_SHAPE_MISMATCH,
        severity=ReworkIssueSeverity.BLOCKING,
        acceptance_refs=ACTIVE_ACCEPTANCE,
        source_surface_refs=ACTIVE_SURFACES,
        run_manifest_refs=("run-manifest.v2-090f",),
        evidence_obligation_refs=ACTIVE_OBLIGATIONS,
        observed_fact_refs=(ObservedFactRef(value="fact.response.body.book.title"),),
        expected_fact_refs=(ExpectedFactRef(value="fact.probe.path.title"),),
        suspected_domains=(
            ReworkSuspectedDomain.IMPLEMENTATION,
            ReworkSuspectedDomain.PROBE,
        ),
        required_artifact_types=(RequiredArtifactType(value="live_blackbox_integration"),),
        description="Behavioral probe expected $.title while backend returned $.book.title.",
    )
```

- [ ] **Step 3: Prove request without verified issues fails**

Add:

```python
def test_rework_request_without_issues_fails() -> None:
    with pytest.raises(ValidationError, match="issues must not be empty"):
        ReworkRequest(
            rework_request_id=ReworkRequestId(value="rework-request.empty"),
            cycle_id="rework-cycle.v2-100a",
            run_id=RunId(value="run-v2-100a"),
            request_source_refs=("blocker-report.final-evidence.add",),
            issues=(),
            requested_by_actor=ReworkActorKind.CHECKER,
            requested_at=NOW,
            active_contract_refs=(ContractId(value="acceptance.v2-090f"), ContractId(value="package.v2-090f")),
            active_graph_version=41,
        )
```

- [ ] **Step 4: Prove notes-only or exception-only source fails**

Add:

```python
def test_blocker_report_without_blockers_fails() -> None:
    with pytest.raises(ValidationError, match="blockers must not be empty"):
        BlockerReport(
            blocker_report_id=BlockerReportId(value="blocker-report.notes-only"),
            run_id=RunId(value="run-v2-100a"),
            source_kind=BlockerSourceKind.CHECKER_VERDICT,
            source_ref="checker-note.non-blocking",
            contract_refs=(ContractId(value="acceptance.v2-090f"),),
            acceptance_refs=ACTIVE_ACCEPTANCE,
            package_contract_ref=ContractId(value="package.v2-090f"),
            run_manifest_ref="run-manifest.v2-090f",
            blockers=(),
            created_at=NOW,
        )
```

- [ ] **Step 5: Prove malformed issue scope fails**

Add:

```python
def test_rework_issue_without_blocker_ref_fails() -> None:
    data = _issue().model_dump()
    data["blocker_refs"] = ()
    with pytest.raises(ValidationError, match="blocker_refs must not be empty"):
        ReworkIssue(**data)


def test_rework_issue_without_acceptance_source_surface_or_artifact_fails() -> None:
    for field_name in ("acceptance_refs", "source_surface_refs", "required_artifact_types"):
        data = _issue().model_dump()
        data[field_name] = ()
        with pytest.raises(ValidationError, match=f"{field_name} must not be empty"):
            ReworkIssue(**data)
```

- [ ] **Step 6: Prove stale acceptance refs fail when active refs are supplied**

Add:

```python
def test_rework_issue_stale_ac_tiny_ref_fails_against_active_contract_scope() -> None:
    stale_issue = _issue().model_copy(
        update={"acceptance_refs": (AcceptanceRef(value="AC-TINY-API-BOOK-CREATE"),)}
    )

    with pytest.raises(ValueError, match="unknown acceptance_ref in rework issue"):
        validate_issue_contract_scope(
            stale_issue,
            active_acceptance_refs=ACTIVE_ACCEPTANCE,
            active_source_surface_refs=ACTIVE_SURFACES,
            active_evidence_obligation_refs=ACTIVE_OBLIGATIONS,
        )
```

- [ ] **Step 7: Prove ReworkPlan planner attempt and patch ref are mandatory**

Add:

```python
def test_rework_plan_requires_planner_attempt_ref_and_graph_patch_ref() -> None:
    decision = ReworkDecision(
        decision_id=ReworkDecisionId(value="rework-decision.fix-api-shape"),
        decision_kind=ReworkDecisionKind.FIX_IMPLEMENTATION,
        blocker_refs=_issue().blocker_refs,
        issue_ids=(_issue().issue_id,),
        target_ticket_refs=(TicketId(value="ticket.fix-backend-create-response"),),
        rationale="Fix backend response shape to match active behavioral probe.",
    )

    with pytest.raises(ValidationError, match="planner_attempt_ref"):
        ReworkPlan(
            rework_plan_id=ReworkPlanId(value="rework-plan.missing-attempt"),
            cycle_id="rework-cycle.v2-100a",
            rework_request_id=ReworkRequestId(value="rework-request.final-evidence"),
            planner_actor=ReworkActorKind.CEO,
            planner_attempt_ref=None,
            decisions=(decision,),
            ticket_graph_patch_ref=TicketGraphPatchId(value="ticket-graph-patch.fix-api-shape"),
            risk_notes=("Keep probe and implementation aligned with active contract.",),
            stop_or_escalation_conditions=("Escalate after two identical probe mismatches.",),
        )

    with pytest.raises(ValidationError, match="ticket_graph_patch_ref"):
        ReworkPlan(
            rework_plan_id=ReworkPlanId(value="rework-plan.missing-patch"),
            cycle_id="rework-cycle.v2-100a",
            rework_request_id=ReworkRequestId(value="rework-request.final-evidence"),
            planner_actor=ReworkActorKind.CEO,
            planner_attempt_ref=ProviderAttemptRef(value="provider-attempt.ceo.rework-plan"),
            decisions=(decision,),
            ticket_graph_patch_ref=None,
            risk_notes=("Keep probe and implementation aligned with active contract.",),
            stop_or_escalation_conditions=("Escalate after two identical probe mismatches.",),
        )
```

- [ ] **Step 8: Prove ReworkAttempt cannot be evidence-free**

Add:

```python
def test_rework_attempt_requires_execution_provider_command_and_source_lineage() -> None:
    from boardroom_os.rework.model import ReworkAttempt, ReworkAttemptId

    base = {
        "rework_attempt_id": ReworkAttemptId(value="rework-attempt.fix-api-shape.1"),
        "cycle_id": "rework-cycle.v2-100a",
        "rework_plan_ref": ReworkPlanId(value="rework-plan.fix-api-shape"),
        "ticket_ref": TicketId(value="ticket.fix-backend-create-response"),
        "execution_package_ref": ExecutionPackageRef(value="execution-package.fix-api-shape"),
        "actor_ref": "agent-seat.worker.backend",
        "provider_attempt_refs": (ProviderAttemptRef(value="provider-attempt.worker.fix-api-shape"),),
        "workspace_mutation_refs": ("workspace-mutation.fix-api-shape.server-py",),
        "command_evidence_refs": ("verification-run.backend-tests.after-rework",),
        "source_lineage_refs": ("source-lineage.backend.server-py.after-rework",),
        "run_manifest_ref": "run-manifest.v2-090f",
        "submitted_at": NOW,
    }
    for field_name in (
        "execution_package_ref",
        "provider_attempt_refs",
        "command_evidence_refs",
        "source_lineage_refs",
    ):
        data = dict(base)
        data[field_name] = None if field_name == "execution_package_ref" else ()
        with pytest.raises(ValidationError, match=field_name):
            ReworkAttempt(**data)
```

- [ ] **Step 9: Prove accepted outcome cannot retain blockers**

Add:

```python
def test_rework_outcome_accepted_with_remaining_blockers_fails() -> None:
    with pytest.raises(ValidationError, match="accepted outcome must not include remaining blockers"):
        ReworkOutcome(
            rework_outcome_id=ReworkOutcomeId(value="rework-outcome.fix-api-shape"),
            rework_attempt_ref="rework-attempt.fix-api-shape.1",
            final_evidence_table_ref="final-evidence-table.acceptance.v2-090f.rework.1",
            source_inventory_ref="source-inventory.rework.1",
            checker_verdict_ref="checker-verdict.rework.1",
            closeout_gate_ref=None,
            status=ReworkOutcomeStatus.ACCEPTED,
            remaining_blocker_refs=(BlockerRef(value="checker-blocker.still-failing"),),
            accepted_blocker_refs=(BlockerRef(value="final-evidence-blocker.failed.acceptance.book.add.probe"),),
            created_at=NOW,
        )
```

- [ ] **Step 10: Run negative tests and confirm they fail before implementation**

Run:

```bash
PYTHONPATH=src python -m pytest tests/negative/test_rework_model_fail_closed.py -q
```

Expected before production code: import failure for `boardroom_os.rework` or validation failure mismatches. This confirms tests are red before implementation.

---

### Task 2: Implement typed rework domain models

**Files:**
- Create `src/boardroom_os/rework/__init__.py`
- Create `src/boardroom_os/rework/model.py`
- Modify `tests/negative/test_rework_model_fail_closed.py` only if exact Pydantic error wording differs while semantics stay identical

- [ ] **Step 1: Create `src/boardroom_os/rework/model.py` with value objects and enums**

Implement:

```python
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from enum import Enum, StrEnum
from typing import Any, Mapping, Self

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator, model_validator

from boardroom_os.contracts.evidence_obligation import RequiredArtifactType
from boardroom_os.contracts.types import AcceptanceRef, ContractId, EvidenceObligationRef, NonEmptyTextValue, SourceSurfaceRef
from boardroom_os.execution.context_index import ProviderAttemptRef
from boardroom_os.execution.package import ExecutionPackageRef
from boardroom_os.graph.ticket import TicketId
```

Add every value object listed in **Public API Target** as a subclass of `NonEmptyTextValue`.

Do not import `_normalize_ref_fields` in V2-100A unless a specific model needs JSON/YAML-style deserialization from strings or `{value: ...}` dicts. Programmatic constructors in these tests can pass typed ref objects directly. If normalization is later added, it must only convert explicit input refs and must not infer missing facts, synthesize blockers, or act as a fallback path.

Add enum values:

```python
class BlockerSourceKind(StrEnum):
    FINAL_EVIDENCE_TABLE = "final_evidence_table"
    CHECKER_VERDICT = "checker_verdict"
    CLOSEOUT_GATE = "closeout_gate"
    RUN_MANIFEST = "run_manifest"
    BEHAVIORAL_PROBE = "behavioral_probe"
    PROCESS_AUDIT = "process_audit"
    REPLAY_BUNDLE = "replay_bundle"


class ReworkActorKind(StrEnum):
    CEO = "ceo"
    ARCHITECT = "architect"
    WORKER = "worker"
    TESTER = "tester"
    RELEASE_DEVOPS = "release_devops"
    CHECKER = "checker"
    CLOSEOUT = "closeout"
    CLOSEOUT_GATE = "closeout_gate"
    EVIDENCE_VERIFIER = "evidence_verifier"
    GRAPH_PATCH_REVIEW_GATE = "graph_patch_review_gate"
    GOVERNANCE_ADAPTER = "governance_adapter"
    GOVERNANCE_COMMAND_HANDLER = "governance_command_handler"
    RUNTIME = "runtime"
    EXECUTOR = "executor"
    ATOMIC_AGENT = "atomic_agent"
```

Define `ReworkIssueCode` here using the normative set in `doc/04-implementation/v2-100-agent-team-rework-loop-spec.md`:

```python
class ReworkIssueCode(StrEnum):
    FINAL_EVIDENCE_MISSING = "final_evidence_missing"
    FINAL_EVIDENCE_FAILED = "final_evidence_failed"
    CHECKER_BLOCKER = "checker_blocker"
    CONTRACT_MISMATCH = "contract_mismatch"
    WORK_PRODUCT_MISMATCH = "work_product_mismatch"
    INVALID_CHECKER_INPUT = "invalid_checker_input"
    CLOSEOUT_GATE_FAILURE = "closeout_gate_failure"
    RUN_MANIFEST_MISMATCH = "run_manifest_mismatch"
    PROBE_RESPONSE_SHAPE_MISMATCH = "probe_response_shape_mismatch"
    ENV_BINDING_NOT_CONVERGED = "env_binding_not_converged"
    FINAL_EVIDENCE_OLD_ACCEPTANCE_REFS = "final_evidence_old_acceptance_refs"
    CLOSEOUT_AUDIT_OLD_RUN_REFS = "closeout_audit_old_run_refs"
```

Define `ReworkSuspectedDomain` with all seven spec domains:

```python
class ReworkSuspectedDomain(StrEnum):
    CONTRACT = "contract"
    IMPLEMENTATION = "implementation"
    PROBE = "probe"
    RUN_ENV = "run_env"
    EVIDENCE_PROJECTION = "evidence_projection"
    CLOSEOUT_AUDIT = "closeout_audit"
    GRAPH = "graph"
```

Use the exact decision and operation values from `doc/04-implementation/v2-100-agent-team-rework-loop-spec.md`:

```python
class ReworkDecisionKind(StrEnum):
    FIX_IMPLEMENTATION = "fix_implementation"
    FIX_CONTRACT_OR_PROBE = "fix_contract_or_probe"
    SPLIT_TICKET = "split_ticket"
    REORDER_DEPENDENCIES = "reorder_dependencies"
    NARROW_SCOPE = "narrow_scope"
    ESCALATE_HUMAN_REVIEW = "escalate_human_review"
```

Continue with `GraphPatchOperationKind`, `GraphPatchReviewDomain`, `GraphPatchReviewStatus`, `GraphPatchApprovalStatus`, `ReworkOutcomeStatus`, and `ReworkTerminationReason` using the spec values.

- [ ] **Step 2: Add common validators and hash helper**

Implement private helpers:

```python
def _reject_empty_tuple(values: tuple[Any, ...], field_name: str) -> tuple[Any, ...]:
    if not values:
        raise ValueError(f"{field_name} must not be empty")
    return values


def _reject_duplicate_value_refs(values: tuple[Any, ...], field_name: str) -> tuple[Any, ...]:
    seen: set[str] = set()
    for value in values:
        ref_value = getattr(value, "value", str(value))
        if ref_value in seen:
            raise ValueError(f"{field_name} must be unique")
        seen.add(ref_value)
    return values


def _require_timezone(value: datetime, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value
```

Implement canonical hash:

```python
def _canonicalize(value: Any) -> Any:
    if isinstance(value, BaseModel):
        field_names = tuple(type(value).model_fields)
        if field_names == ("value",):
            return _canonicalize(value.value)
        return {field_name: _canonicalize(getattr(value, field_name)) for field_name in field_names}
    if isinstance(value, tuple | list):
        return [_canonicalize(item) for item in value]
    if isinstance(value, Mapping):
        return {str(key): _canonicalize(item) for key, item in value.items()}
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def canonical_rework_hash(model: BaseModel) -> str:
    payload = json.dumps(_canonicalize(model), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
```

- [ ] **Step 3: Implement `BlockerReport`**

Fields:

```python
class BlockerReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    blocker_report_id: BlockerReportId
    run_id: RunId
    source_kind: BlockerSourceKind
    source_ref: str
    contract_refs: tuple[ContractId, ...]
    acceptance_refs: tuple[AcceptanceRef, ...]
    package_contract_ref: ContractId
    run_manifest_ref: str
    blockers: tuple[BlockerRef, ...]
    created_at: datetime
```

Validation:

- `source_ref` and `run_manifest_ref` must be non-empty strings.
- `contract_refs`, `acceptance_refs`, and `blockers` must be non-empty and unique.
- `created_at` must be timezone-aware.
- The enum excludes free-text note or exception sources by construction.

- [ ] **Step 4: Implement `ReworkIssue`**

Fields match the V2-100 spec:

```python
class ReworkIssue(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    issue_id: ReworkIssueId
    blocker_refs: tuple[BlockerRef, ...]
    issue_code: ReworkIssueCode
    severity: ReworkIssueSeverity
    acceptance_refs: tuple[AcceptanceRef, ...]
    source_surface_refs: tuple[SourceSurfaceRef, ...]
    run_manifest_refs: tuple[str, ...]
    evidence_obligation_refs: tuple[EvidenceObligationRef, ...]
    observed_fact_refs: tuple[ObservedFactRef, ...]
    expected_fact_refs: tuple[ExpectedFactRef, ...]
    suspected_domains: tuple[ReworkSuspectedDomain, ...]
    required_artifact_types: tuple[RequiredArtifactType, ...]
    description: str
```

Validation:

- All tuple fields except `observed_fact_refs` and `expected_fact_refs` are non-empty and unique.
- `description` is non-empty.
- `severity=blocking` or `severity=escalation_required` only.
- Do not store `active_acceptance_refs` on this model; active contract authority remains external.

- [ ] **Step 5: Implement contract-scope validators**

Add:

```python
def validate_issue_contract_scope(
    issue: ReworkIssue,
    *,
    active_acceptance_refs: tuple[AcceptanceRef, ...],
    active_source_surface_refs: tuple[SourceSurfaceRef, ...],
    active_evidence_obligation_refs: tuple[EvidenceObligationRef, ...],
) -> None:
    active_acceptance = {ref.value for ref in active_acceptance_refs}
    active_surfaces = {ref.value for ref in active_source_surface_refs}
    active_obligations = {ref.value for ref in active_evidence_obligation_refs}
    for ref in issue.acceptance_refs:
        if ref.value not in active_acceptance:
            raise ValueError(f"unknown acceptance_ref in rework issue: {ref.value}")
    for ref in issue.source_surface_refs:
        if ref.value not in active_surfaces:
            raise ValueError(f"unknown source_surface_ref in rework issue: {ref.value}")
    for ref in issue.evidence_obligation_refs:
        if ref.value not in active_obligations:
            raise ValueError(f"unknown evidence_obligation_ref in rework issue: {ref.value}")
```

This keeps AcceptanceContract（验收合同）as the source of truth and prevents a second source of truth inside ReworkIssue（返工问题）.

- [ ] **Step 6: Implement request, cycle, decision, and plan models**

Key validation:

- `ReworkRequest.issues` must be non-empty.
- `ReworkRequest.requested_by_actor` may be `CHECKER`, `CLOSEOUT_GATE`, `GRAPH_PATCH_REVIEW_GATE`, `GOVERNANCE_ADAPTER`, `EVIDENCE_VERIFIER`, or `CLOSEOUT`; it must reject `RUNTIME`, `EXECUTOR`, `ATOMIC_AGENT`, `WORKER`, and `TESTER`.
- Every `request_source_refs` value must be non-empty.
- `active_graph_version` must be greater than zero.
- `ReworkDecision` maps every decision to non-empty `blocker_refs` and `issue_ids`.
- Non-escalation `ReworkDecision` values require non-empty `target_ticket_refs` or `target_graph_operation_refs`.
- `ReworkPlan.planner_actor` must be `CEO`.
- `ReworkPlan.planner_attempt_ref` and `ticket_graph_patch_ref` are not optional.
- `ReworkPlan` cannot mark blockers closed; it contains decisions only.

- [ ] **Step 7: Implement graph patch and review data models without reducer behavior**

Add typed data objects:

- `TicketGraphPatchOperation`
- `TicketGraphPatch`
- `GraphPatchReview`
- `GraphPatchApprovalSet`

Validation:

- `TicketGraphPatch.base_graph_version > 0`.
- `TicketGraphPatch.operations`, `affected_ticket_refs`, `affected_contract_refs`, `affected_source_surface_refs`, and `required_review_domains` are non-empty.
- `TicketGraphPatchOperation.operation_kind` cannot express direct source edit, direct evidence approval, direct checker approval, direct closeout approval, direct ticket completion, or hidden allowed write expansion because those values are absent from `GraphPatchOperationKind`.
- `GraphPatchReview.status=approved` requires non-empty `checked_invariants`.
- `GraphPatchReview.status=rejected` or `needs_changes` requires non-empty `blockers`.
- `GraphPatchApprovalSet.status=ready_to_commit` requires at least planning, structural, and blocker coverage domains in `required_domains`.

- [ ] **Step 8: Implement attempt, outcome, and termination models**

Validation:

- `ReworkAttempt.execution_package_ref` is required.
- `ReworkAttempt.provider_attempt_refs`, `workspace_mutation_refs`, `command_evidence_refs`, and `source_lineage_refs` are non-empty and unique.
- `ReworkAttempt.submitted_at` is timezone-aware.
- `ReworkOutcome.status=accepted` requires empty `remaining_blocker_refs`, non-empty `accepted_blocker_refs`, and non-empty current-round evidence refs: `final_evidence_table_ref`, `source_inventory_ref`, and `checker_verdict_ref`.
- `ReworkOutcome.status=rework_required` requires non-empty `remaining_blocker_refs`.
- `ReworkOutcome.status=exhausted` requires `termination_decision_ref`.
- `ReworkTerminationDecision.reason` uses `ReworkTerminationReason` and includes non-empty evidence refs proving budget, loop, contract, provider, or evidence trust reason.

- [ ] **Step 9: Export public names**

Create `src/boardroom_os/rework/__init__.py` that imports and exposes all public V2-100A model names and projection helpers.

- [ ] **Step 10: Run negative tests until green**

Run:

```bash
PYTHONPATH=src python -m pytest tests/negative/test_rework_model_fail_closed.py -q
```

Expected after implementation: all tests pass.

---

### Task 3: Write happy-path model tests

**Files:**
- Create `tests/rework/test_rework_model.py`

- [ ] **Step 1: Build typed chain from final evidence blocker to accepted outcome**

Create tests that construct:

1. `BlockerReport` with `source_kind=final_evidence_table`.
2. `ReworkIssue` for `probe_response_shape_mismatch`.
3. `ReworkRequest` requested by `checker`.
4. `ReworkDecision` with `decision_kind=fix_implementation`.
5. `ReworkPlan` planned by `ceo` and backed by `ProviderAttemptRef`.
6. `TicketGraphPatch` with `create_rework_ticket` and `mark_ticket_blocked_by_rework`.
7. `ReworkAttempt` with ExecutionPackage（执行包）, ProviderAttempt（模型调用尝试）, command evidence（命令证据）, workspace mutation（工作区变更）, and source lineage（源码来源链）refs.
8. `ReworkOutcome(status=accepted)` with new FinalEvidenceTable（最终证据表）, SourceInventory（源码清单）, and CheckerVerdict（检查结论）refs.

Assertion targets:

```python
assert request.issues == (issue,)
assert plan.planner_actor is ReworkActorKind.CEO
assert attempt.provider_attempt_refs == (ProviderAttemptRef(value="provider-attempt.worker.fix-api-shape"),)
assert outcome.status is ReworkOutcomeStatus.ACCEPTED
```

- [ ] **Step 2: Prove deterministic serialization and hash**

Add:

```python
def test_rework_chain_serializes_and_hashes_deterministically() -> None:
    request, plan, outcome = build_rework_chain()

    first = (
        canonical_rework_hash(request),
        canonical_rework_hash(plan),
        canonical_rework_hash(outcome),
    )
    second = (
        canonical_rework_hash(request.model_validate(request.model_dump())),
        canonical_rework_hash(plan.model_validate(plan.model_dump())),
        canonical_rework_hash(outcome.model_validate(outcome.model_dump())),
    )

    assert first == second
    assert all(len(value) == 64 for value in first)
```

- [ ] **Step 3: Prove the three verified source families can create requests**

Add three tests named:

- `test_build_rework_request_from_final_evidence_missing_row`
- `test_build_rework_request_from_checker_verdict_blocker`
- `test_build_rework_request_from_closeout_gate_failure`

These can call the projection helpers introduced in Task 4 once that task exists. During Task 3, keep the tests in the file but mark exact helper imports at the top; the test file may remain red until Task 4 is complete.

- [ ] **Step 4: Run happy-path model tests and confirm expected red state**

Run:

```bash
PYTHONPATH=src python -m pytest tests/rework/test_rework_model.py -q
```

Expected after Task 2 and before Task 4: direct model/hash tests pass, projection helper tests fail because `blocker_projection.py` is not implemented yet.

---

### Task 4: Implement blocker projection helpers

**Files:**
- Create `src/boardroom_os/rework/blocker_projection.py`
- Update `tests/rework/test_rework_model.py`
- Keep `tests/negative/test_rework_model_fail_closed.py` green

- [ ] **Step 1: Implement `BlockerProjectionContext`**

Fields:

```python
class BlockerProjectionContext(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    cycle_id: ReworkCycleId
    run_id: RunId
    package_contract_ref: ContractId
    run_manifest_ref: str
    active_acceptance_refs: tuple[AcceptanceRef, ...]
    active_source_surface_refs: tuple[SourceSurfaceRef, ...]
    active_evidence_obligation_refs: tuple[EvidenceObligationRef, ...]
    active_graph_version: int = Field(gt=0)
    requested_by_actor: ReworkActorKind
    requested_at: datetime
```

Validation:

- Active ref tuples are non-empty and unique.
- `requested_by_actor` follows ReworkRequest（返工请求）requester rules.
- `requested_at` is timezone-aware.

- [ ] **Step 2: Implement FinalEvidenceTable projection**

Rules:

- Consume only `FinalEvidenceRow.status in {FinalEvidenceStatus.MISSING, FinalEvidenceStatus.FAILED}`.
- `MISSING` rows do not contain `FinalEvidenceBlocker`（最终证据阻塞对象）by model design. Generate one `ReworkIssue` directly from the row, with synthetic blocker ref shaped as `final-evidence-missing.<acceptance_ref>`.
- `FAILED` rows must contain `FinalEvidenceBlocker` values. Reuse each `FinalEvidenceBlocker.blocker_id` as the blocker ref.
- Issue code is `FINAL_EVIDENCE_MISSING` for missing rows. For failed rows, use a specific V2-090K code only when the blocker message/source explicitly identifies that failure; otherwise use `FINAL_EVIDENCE_FAILED`.
- Required artifact types come from `row.missing_required_artifact_types` for missing rows. For failed rows, the projection must use an explicit mapping from blocker source/message to active context obligations or fall back to a context-provided required artifact type; it must not assume `FinalEvidenceBlockerCode` has missing-row codes.
- Every projected issue must pass `validate_issue_contract_scope(...)`.

- [ ] **Step 3: Implement CheckerVerdict projection**

Rules:

- Accept only `CheckerVerdictStatus.REWORK_REQUIRED` and `CheckerVerdictStatus.ESCALATE`.
- Reject approved verdicts and note-only verdicts by raising `ValueError("checker verdict has no verified blockers")`.
- Each `CheckerVerdictBlocker` becomes one `ReworkIssue`.
- `CheckerBlockerCode.FINAL_EVIDENCE_MISSING` maps to `ReworkIssueCode.FINAL_EVIDENCE_MISSING`.
- `CheckerBlockerCode.FINAL_EVIDENCE_FAILED` maps to `ReworkIssueCode.FINAL_EVIDENCE_FAILED`.
- `CheckerBlockerCode.CONTRACT_MISMATCH` maps to suspected domains `contract`, `probe`, and `implementation`.

- [ ] **Step 4: Implement CloseoutGate projection**

Rules:

- Accept only `closeout_gate_result.verdict == CloseoutGateVerdict.BLOCKED`.
- Reject `closeout_gate_result.verdict == CloseoutGateVerdict.PASSED` by raising `ValueError("closeout gate passed, no blockers to project")`.
- Each closeout blocker becomes a `ReworkIssue` with suspected domain `closeout_audit` when the blocker code or related ref targets replay/process/git audit, otherwise `evidence_projection`.
- Closeout projection must not mark any blocker accepted; it only creates a request.

- [ ] **Step 5: Run projection tests**

Run:

```bash
PYTHONPATH=src python -m pytest tests/rework/test_rework_model.py tests/negative/test_rework_model_fail_closed.py -q
```

Expected: all tests in these two files pass.

---

### Task 5: Project V2-090K curated failure snapshot

**Files:**
- Create `tests/rework/test_v2_090k_failure_snapshot_projection.py`
- Modify `src/boardroom_os/rework/blocker_projection.py`

- [ ] **Step 1: Create snapshot test context**

In `tests/rework/test_v2_090k_failure_snapshot_projection.py`, define:

```python
from datetime import UTC, datetime
from pathlib import Path

from boardroom_os.contracts.types import AcceptanceRef, ContractId, EvidenceObligationRef, SourceSurfaceRef
from boardroom_os.rework.blocker_projection import BlockerProjectionContext, project_v2_090k_failure_summary
from boardroom_os.rework.model import ReworkActorKind, ReworkIssueCode, ReworkSuspectedDomain, RunId

SNAPSHOT = Path("examples/generated-workspaces/tiny-fullstack/30-audit/v2-090k-failure-snapshot/failure-summary.json")


def _context() -> BlockerProjectionContext:
    return BlockerProjectionContext(
        cycle_id="rework-cycle.v2-100a.snapshot",
        run_id=RunId(value="run-v2-090k-full-provider"),
        package_contract_ref=ContractId(value="package.v2-090f.tiny-library-checkout"),
        run_manifest_ref="run-manifest.v2-090f.tiny-library-checkout",
        active_acceptance_refs=(
            AcceptanceRef(value="acceptance.book.add"),
            AcceptanceRef(value="acceptance.book.list"),
            AcceptanceRef(value="acceptance.book.checkout"),
            AcceptanceRef(value="acceptance.book.return"),
            AcceptanceRef(value="acceptance.book.delete"),
            AcceptanceRef(value="acceptance.ui.backend_updates"),
            AcceptanceRef(value="acceptance.persistence.sqlite"),
            AcceptanceRef(value="acceptance.instructions.tests"),
        ),
        active_source_surface_refs=(
            SourceSurfaceRef(value="surface.backend.api"),
            SourceSurfaceRef(value="surface.frontend.ui"),
            SourceSurfaceRef(value="surface.persistence.sqlite"),
            SourceSurfaceRef(value="surface.run_manifest"),
            SourceSurfaceRef(value="surface.behavioral_probe"),
            SourceSurfaceRef(value="surface.closeout_audit"),
        ),
        active_evidence_obligation_refs=(
            EvidenceObligationRef(value="evidence.add.api"),
            EvidenceObligationRef(value="evidence.list.api"),
            EvidenceObligationRef(value="evidence.checkout.api"),
            EvidenceObligationRef(value="evidence.return.api"),
            EvidenceObligationRef(value="evidence.delete.api"),
            EvidenceObligationRef(value="evidence.ui.real_backend"),
            EvidenceObligationRef(value="evidence.sqlite.persistence"),
            EvidenceObligationRef(value="evidence.tests.instructions"),
        ),
        active_graph_version=90,
        requested_by_actor=ReworkActorKind.GOVERNANCE_ADAPTER,
        requested_at=datetime(2026, 6, 13, 12, 0, tzinfo=UTC),
    )
```

- [ ] **Step 2: Assert the four failure ids become typed issues**

Add:

```python
def test_v2_090k_failure_snapshot_projects_four_issues() -> None:
    request = project_v2_090k_failure_summary(SNAPSHOT, _context())

    assert len(request.issues) == 4
    assert {issue.issue_code for issue in request.issues} == {
        ReworkIssueCode.PROBE_RESPONSE_SHAPE_MISMATCH,
        ReworkIssueCode.ENV_BINDING_NOT_CONVERGED,
        ReworkIssueCode.FINAL_EVIDENCE_OLD_ACCEPTANCE_REFS,
        ReworkIssueCode.CLOSEOUT_AUDIT_OLD_RUN_REFS,
    }
```

- [ ] **Step 3: Assert each issue maps to active authority instead of stale refs**

Add:

```python
def test_v2_090k_snapshot_projection_uses_active_acceptance_refs_not_ac_tiny_refs() -> None:
    request = project_v2_090k_failure_summary(SNAPSHOT, _context())

    for issue in request.issues:
        assert all(not ref.value.startswith("AC-TINY-") for ref in issue.acceptance_refs)
        assert issue.source_surface_refs
        assert issue.evidence_obligation_refs
        assert issue.required_artifact_types
```

- [ ] **Step 4: Assert domain routing**

Add:

```python
def test_v2_090k_snapshot_projection_routes_domains() -> None:
    request = project_v2_090k_failure_summary(SNAPSHOT, _context())
    by_code = {issue.issue_code: issue for issue in request.issues}

    assert ReworkSuspectedDomain.PROBE in by_code[ReworkIssueCode.PROBE_RESPONSE_SHAPE_MISMATCH].suspected_domains
    assert ReworkSuspectedDomain.IMPLEMENTATION in by_code[ReworkIssueCode.PROBE_RESPONSE_SHAPE_MISMATCH].suspected_domains
    assert ReworkSuspectedDomain.RUN_ENV in by_code[ReworkIssueCode.ENV_BINDING_NOT_CONVERGED].suspected_domains
    assert ReworkSuspectedDomain.EVIDENCE_PROJECTION in by_code[ReworkIssueCode.FINAL_EVIDENCE_OLD_ACCEPTANCE_REFS].suspected_domains
    assert ReworkSuspectedDomain.CLOSEOUT_AUDIT in by_code[ReworkIssueCode.CLOSEOUT_AUDIT_OLD_RUN_REFS].suspected_domains
```

- [ ] **Step 5: Implement `project_v2_090k_failure_summary`**

Implementation rules:

- Load JSON with UTF-8.
- Require `snapshot_kind == "curated_real_provider_failure"`.
- Require exactly the four `primary_failures[*].failure_id` values from the pre-flight command.
- The snapshot JSON is not an authority for active `acceptance_refs`, `source_surface_refs`, or `evidence_obligation_refs`. Those refs come only from `BlockerProjectionContext.active_*_refs`.
- Use an explicit `failure_id` lookup table to select which active context refs are relevant. The lookup table is part of V2-100A and must be visible in `blocker_projection.py`; it must fail closed when a mapped ref is absent from context.
- Mapping table:
  - `probe-response-shape-mismatch` selects acceptance refs `acceptance.book.add` and `acceptance.book.list`, source surfaces `surface.backend.api` and `surface.behavioral_probe`, evidence obligations `evidence.add.api` and `evidence.list.api`, domains `implementation` and `probe`, and required artifact type `live_blackbox_integration`.
  - `env-binding-not-converged` selects acceptance refs `acceptance.persistence.sqlite` and `acceptance.instructions.tests`, source surfaces `surface.run_manifest` and `surface.backend.api`, evidence obligations `evidence.tests.instructions` and `evidence.sqlite.persistence`, domains `run_env` and `implementation`, and required artifact type `run_manifest`.
  - `final-evidence-uses-old-acceptance-refs` selects all active acceptance refs, source surface `surface.closeout_audit`, all active evidence obligations, domain `evidence_projection`, and required artifact type `final_evidence_table`. Store old `AC-TINY-*` refs as `observed_fact_refs`, not as `acceptance_refs`.
  - `closeout-audit-references-old-run` selects all active acceptance refs, source surface `surface.closeout_audit`, all active evidence obligations, domain `closeout_audit`, and required artifact type `process_audit`. Store observed old run ref `run-v2-080f` as an `observed_fact_ref`, not as a current `run_id`.
- Use context active refs as the only accepted authority and call `validate_issue_contract_scope(...)` for each issue.

- [ ] **Step 6: Run snapshot projection tests**

Run:

```bash
PYTHONPATH=src python -m pytest tests/rework/test_v2_090k_failure_snapshot_projection.py -q
```

Expected: all snapshot projection tests pass and no test reads old `backend/app/core/` or forbidden legacy docs.

---

### Task 6: Add import/export regression and targeted verification

**Files:**
- Modify `src/boardroom_os/rework/__init__.py`
- Modify `tests/rework/test_rework_model.py`

- [ ] **Step 1: Assert package exports are stable**

Add a test:

```python
def test_rework_package_exports_v2_100a_public_api() -> None:
    import boardroom_os.rework as rework

    for name in (
        "BlockerReport",
        "ReworkIssue",
        "ReworkRequest",
        "ReworkPlan",
        "TicketGraphPatch",
        "GraphPatchReview",
        "ReworkAttempt",
        "ReworkOutcome",
        "project_v2_090k_failure_summary",
    ):
        assert hasattr(rework, name)
```

- [ ] **Step 2: Run targeted tests**

Run:

```bash
PYTHONPATH=src python -m pytest tests/negative/test_rework_model_fail_closed.py tests/rework/test_rework_model.py tests/rework/test_v2_090k_failure_snapshot_projection.py -q
```

Expected: all V2-100A tests pass.

- [ ] **Step 3: Run nearby regression suites**

Run:

```bash
PYTHONPATH=src python -m pytest tests/evidence/test_final_evidence_table.py tests/evidence/test_checker_verdict.py tests/closeout/test_closeout_gate.py tests/negative/test_closeout_fail_closed.py -q
```

Expected: existing evidence/checker/closeout tests still pass.

- [ ] **Step 4: Run broader non-provider regression**

Run:

```bash
PYTHONPATH=src:. python -m pytest tests/contracts tests/reducers tests/execution tests/evidence tests/closeout tests/negative -q
```

Expected: non-provider regression passes. If a failure is unrelated and pre-existing, capture the exact command, failing test, and reason before asking for review.

---

### Task 7: Close documentation only after verification

**Files:**
- Modify `doc/04-implementation/backlog.md`
- Modify `doc/04-implementation/acceptance-criteria.md`
- Modify `doc/05-project-log/2026-06.md`
- Modify `doc/04-implementation/INDEX.md` if implementation introduces additional docs

- [ ] **Step 1: Update backlog state**

After all Task 6 verification commands pass, update:

- V2-100A status from `TODO` to `DONE`.
- Top TL;DR current incomplete work package from `V2-100A` to `V2-100B`.
- Phase 10 progress from `0 / 5` to `1 / 5`.
- Overall progress from `69 / 75` to `70 / 75`.
- V2-100A output file list to include actual created code/test files.

- [ ] **Step 2: Update acceptance criteria**

Check the V2-100A Phase 10 checkbox:

```text
- [x] AC-V2-REWORK-001 / AC-V2-REWORK-002 ...
```

Do not check V2-100B through V2-100E entries.

- [ ] **Step 3: Update monthly log**

Append one 2026-06 entry keyed by `V2-100A` with:

- Produced files.
- Negative tests run.
- Happy-path tests run.
- V2-090K snapshot projection evidence.
- Regression commands and results.

- [ ] **Step 4: Keep decisions log unchanged unless scope changes**

Do not update `doc/05-project-log/decisions.md` for routine implementation. Add a decision only if implementation changes the V2-100 architecture, moves authority from contract/reducer/evidence to runtime, or changes the Phase 10 acceptance semantics.

---

## Self-review Checklist

- [x] Spec coverage: the plan covers V2-100A required models, value objects, enums, projection from FinalEvidenceTable（最终证据表）, CheckerVerdict（检查结论）, CloseoutGate（收尾门禁）and the V2-090K failure-summary（失败摘要）snapshot.
- [x] Boundary check: the plan does not implement reducer（归约器）, provider-backed CEO planner（模型支撑 CEO 规划器）, graph patch review gate（图补丁审查门禁）, evidence re-run pipeline（证据重跑流水线）, or closeout re-run（收尾重跑）beyond V2-100A typed data boundaries.
- [x] Contract authority: active AcceptanceContract（验收合同）, SourceSurface（源码面）and EvidenceObligation（证据义务）refs stay external and are validated through explicit context, avoiding a second source of truth.
- [x] Runtime boundary: runtime/executor/atomic-agent（运行时/执行器/原子智能体）are rejected as requester/planner/acceptance actors in V2-100A models.
- [x] Negative-first coverage: every backlog negative requirement for V2-100A has a named test before implementation steps.
- [x] Snapshot coverage: the four V2-090K failures are mapped by id and old `AC-TINY-*` refs are stored as observed facts, not accepted as active acceptance refs.
- [x] Review hardening: `ReworkSuspectedDomain.GRAPH`（图领域）is included; `ReworkIssueCode`（返工问题编码）is now normative in the V2-100 spec; V2-090K snapshot mapping is an explicit `failure_id` table over active context refs; FinalEvidenceTable missing rows（最终证据表缺失行）do not depend on `FinalEvidenceBlocker`; CloseoutGate projection（收尾门禁投影）uses `verdict`, not a nonexistent `status`.
- [x] Placeholder scan: the plan contains no unfinished marker or vague implementation directive; every task names exact files, public names, commands, and expected results.
- [x] Type consistency: public names are consistent across file structure, tests, implementation tasks, and package exports.
