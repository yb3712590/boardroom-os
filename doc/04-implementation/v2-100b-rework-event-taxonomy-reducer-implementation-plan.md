# V2-100B Rework Event Taxonomy + Reducer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development（子智能体驱动开发，推荐）or superpowers:executing-plans（按计划执行）to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement V2-100B Rework event taxonomy + reducer（返工事件分类与归约器）so ReworkCycle（返工循环）state advances only through typed governance events（类型化治理事件）, GraphPatchReviewGate（图补丁审查门禁）and reducer（归约器）validation.

**Architecture:** Extend the existing EventRecord（事件记录）/ EventType（事件类型）pattern: events carry only payload_refs（载荷引用）, and ReworkReducer（返工归约器）resolves typed payload（类型化载荷）through a resolver protocol before projection. V2-100B does not call providers（模型供应商）, does not execute rework tickets（返工工单）, and does not re-run evidence（证据）; it protects governance state transitions, actor permissions（执行者权限）, GraphPatchReviewGate policy（图补丁审查门禁策略）and replayable ReworkProjection（可回放返工投影）that V2-100C/D consume.

**Tech Stack:** Python 3.11+, Pydantic v2, pytest, existing Boardroom OS V2 EventRecord（事件记录）, InMemoryEventLog（内存事件日志）, RuntimeEventBoundary（运行时事件边界）, TicketGraph（工单图）, TicketCreatedPayload（工单创建载荷）, TicketReducer（工单归约器）, and V2-100A rework models（返工模型）.

---

## Scope And Non-Goals

V2-100B owns:

- Rework event taxonomy（返工事件分类） in `EventType`.
- Runtime boundary（运行时边界） rejection for governance-only `REWORK_*` events.
- Typed reducer payloads（类型化归约器载荷） and resolver protocol（解析器协议）.
- GraphPatchReviewGate（图补丁审查门禁） for GraphPatchApprovalSet（图补丁批准集） and TicketGraphPatch（工单图补丁） readiness.
- ReworkReducer（返工归约器） and ReworkProjection（返工投影） over replayed events.
- Optional TicketReducer（工单归约器） integration for graph patch operations that create/block rework tickets.

V2-100B does not own:

- CEO provider-backed planning（项目经理模型支撑规划）; V2-100C owns it.
- Evidence/checker/closeout re-run（证据/检查/收尾重验）; V2-100D owns it.
- End-to-end multi-round proving scenario（多轮证明场景）; V2-100E owns it.
- Any runner/helper auto-repair（运行器/辅助器自动修复）.

---

## File Structure

- Modify `src/boardroom_os/events/types.py`
  - Add governance `REWORK_*` EventType（事件类型） values.
- Modify `src/boardroom_os/execution/runtime_executor.py`
  - Ensure RuntimeEventBoundary（运行时事件边界） treats governance `REWORK_*` events as forbidden for runtime/executor（运行时/执行器） except `REWORK_ATTEMPT_STARTED` and `REWORK_ATTEMPT_SUBMITTED`, which are execution facts（执行事实）.
- Create `src/boardroom_os/reducers/rework.py`
  - Rework reducer payload models（返工归约器载荷模型）, GraphPatchReviewGate（图补丁审查门禁）, ReworkProjection（返工投影）, ReworkReducer（返工归约器）, resolver protocol（解析器协议） and fail-closed errors（失败关闭错误）.
- Modify `src/boardroom_os/reducers/errors.py`
  - Add `ReworkReducerError`（返工归约器错误） if the project keeps reducer errors centralized; otherwise define it in `rework.py` and re-export.
- Modify `src/boardroom_os/rework/__init__.py`
  - Export GraphPatchReviewGate（图补丁审查门禁） only if implementation keeps it under `boardroom_os.reducers.rework` public API; do not duplicate model exports.
- Create `tests/reducers/test_rework_reducer.py`
  - Happy path and replay projection tests（正向路径与重放投影测试）.
- Create `tests/negative/test_rework_reducer_fail_closed.py`
  - Negative tests（负例测试） for actor permissions（执行者权限）, invalid order（非法顺序）, stale blocker closure（陈旧阻塞项关闭）, graph patch review gaps（图补丁审查缺口）, and unsafe graph patch operations（不安全图补丁操作）.
- Modify `tests/execution/test_runtime_executor_boundary.py`
  - Add runtime boundary（运行时边界） coverage for `REWORK_*` governance events.
- Modify `doc/04-implementation/INDEX.md`
  - Register this implementation plan（实施计划）. Do not mark V2-100B DONE during plan drafting.

---

## Public API Target

Add EventType（事件类型） values in `src/boardroom_os/events/types.py`:

```python
class EventType(StrEnum):
    ...
    REWORK_REQUESTED = "rework_requested"
    REWORK_PLANNED = "rework_planned"
    REWORK_GRAPH_PATCH_REVIEWED = "rework_graph_patch_reviewed"
    REWORK_GRAPH_PATCH_APPROVED = "rework_graph_patch_approved"
    REWORK_TICKET_CREATED = "rework_ticket_created"
    REWORK_ATTEMPT_STARTED = "rework_attempt_started"
    REWORK_ATTEMPT_SUBMITTED = "rework_attempt_submitted"
    REWORK_REVIEWED = "rework_reviewed"
    REWORK_ACCEPTED = "rework_accepted"
    REWORK_ESCALATED = "rework_escalated"
    REWORK_EXHAUSTED = "rework_exhausted"
```

Implement in `src/boardroom_os/reducers/rework.py`:

```python
class ReworkReducerError(ValueError):
    pass

class ReworkTerminalStatus(StrEnum):
    OPEN = "open"
    ACCEPTED = "accepted"
    ESCALATED = "escalated"
    EXHAUSTED = "exhausted"

class ReworkRequestPayload(BaseModel): ...
class ReworkPlanPayload(BaseModel): ...
class GraphPatchReviewPayload(BaseModel): ...
class GraphPatchApprovalPayload(BaseModel): ...
class ReworkTicketCreatedPayload(BaseModel): ...
class ReworkAttemptPayload(BaseModel): ...
class ReworkReviewPayload(BaseModel): ...
class ReworkTerminalPayload(BaseModel): ...

class ReworkProjection(BaseModel): ...
class ReworkReducerPayloadResolver(Protocol): ...
class GraphPatchReviewGate: ...
class ReworkReducer: ...
```

Reducer（归约器） invariants:

- `REWORK_REQUESTED` must be first for a cycle and must resolve to a ReworkRequest（返工请求） whose `active_graph_version` is covered by the event.
- `REWORK_PLANNED` requires prior request and resolves to a CEO-owned ReworkPlan（返工计划） plus TicketGraphPatch（工单图补丁）.
- `REWORK_GRAPH_PATCH_REVIEWED` records typed GraphPatchReview（图补丁审查） only for the planned patch.
- `REWORK_GRAPH_PATCH_APPROVED` requires GraphPatchReviewGate（图补丁审查门禁） `READY_TO_COMMIT`.
- `REWORK_TICKET_CREATED` requires an approved patch and validates created TicketCreatedPayload（工单创建载荷） against patch operations（补丁操作）.
- `REWORK_ATTEMPT_STARTED` / `REWORK_ATTEMPT_SUBMITTED` are runtime facts（运行时事实） but must reference an approved rework ticket（已批准返工工单）.
- `REWORK_REVIEWED` requires a submitted attempt and resolves to ReworkOutcome（返工结果）.
- `REWORK_ACCEPTED` requires a reviewed accepted outcome with fresh evidence refs（新证据引用）.
- `REWORK_ESCALATED` / `REWORK_EXHAUSTED` require ReworkTerminationDecision（返工终止决策）.
- Runtime/executor/atomic-agent（运行时/执行器/原子智能体） cannot emit governance terminal events（治理终态事件）.

---

## Pre-Flight Before Implementation

- [ ] **Step 1: Confirm branch and task state**

Run:

```bash
git status --short --branch
test ! -e src/boardroom_os/reducers/rework.py
test ! -e tests/reducers/test_rework_reducer.py
test ! -e tests/negative/test_rework_reducer_fail_closed.py
```

Expected: branch is `rebuild/v2-clean-foundation`; `V2-100A` is DONE in `doc/04-implementation/backlog.md`; `V2-100B` is TODO; the three `test ! -e ...` checks pass. If any target file already exists, inspect it first and preserve user changes.

- [ ] **Step 2: Confirm V2-100A public API exists**

Run:

```bash
PYTHONPATH=src python - <<'PY'
from boardroom_os.rework.model import (
    GraphPatchApprovalSet,
    GraphPatchApprovalStatus,
    GraphPatchReview,
    ReworkActorKind,
    ReworkAttempt,
    ReworkOutcome,
    ReworkOutcomeStatus,
    ReworkPlan,
    ReworkRequest,
    ReworkTerminationDecision,
    TicketGraphPatch,
)

print("v2-100a rework api ok")
PY
```

Expected: prints `v2-100a rework api ok`.

- [ ] **Step 3: Confirm existing event/reducer tests pass before editing**

Run:

```bash
PYTHONPATH=src python -m pytest \
  tests/reducers/test_event_record.py \
  tests/reducers/test_event_log.py \
  tests/reducers/test_ticket_reducer_transitions.py \
  tests/closeout/test_closeout_reducer.py \
  tests/execution/test_runtime_executor_boundary.py \
  -q
```

Expected: existing tests pass. If they fail, stop and diagnose before changing V2-100B code.

---

### Task 1: Add Rework Event Taxonomy And Runtime Boundary Tests

**Files:**
- Modify `tests/reducers/test_event_record.py`
- Modify `tests/execution/test_runtime_executor_boundary.py`
- Modify `src/boardroom_os/events/types.py`
- Modify `src/boardroom_os/execution/runtime_executor.py`

- [ ] **Step 1: Write event taxonomy test**

Append to `tests/reducers/test_event_record.py`:

```python
def test_event_record_accepts_rework_event_types() -> None:
    rework_event_types = (
        EventType.REWORK_REQUESTED,
        EventType.REWORK_PLANNED,
        EventType.REWORK_GRAPH_PATCH_REVIEWED,
        EventType.REWORK_GRAPH_PATCH_APPROVED,
        EventType.REWORK_TICKET_CREATED,
        EventType.REWORK_ATTEMPT_STARTED,
        EventType.REWORK_ATTEMPT_SUBMITTED,
        EventType.REWORK_REVIEWED,
        EventType.REWORK_ACCEPTED,
        EventType.REWORK_ESCALATED,
        EventType.REWORK_EXHAUSTED,
    )

    for index, event_type in enumerate(rework_event_types, start=10):
        event = _valid_event_record(
            event_id=EventId(value=f"evt-rework-{event_type.value}"),
            event_type=event_type,
            payload_refs=(EventPayloadRef(value=f"payload:{event_type.value}"),),
            graph_version=index,
        )

        assert event.event_type is event_type
        assert event.stable_dump()["event_type"] == event_type.value
```

- [ ] **Step 2: Run test and verify it fails**

Run:

```bash
PYTHONPATH=src python -m pytest tests/reducers/test_event_record.py::test_event_record_accepts_rework_event_types -q
```

Expected: FAIL with `AttributeError: REWORK_REQUESTED` or equivalent missing enum member.

- [ ] **Step 3: Add rework EventType values**

Modify `src/boardroom_os/events/types.py`:

```python
class EventType(StrEnum):
    TICKET_CREATED = "ticket_created"
    ...
    CLOSEOUT_COMMITTED = "closeout_committed"
    REWORK_REQUESTED = "rework_requested"
    REWORK_PLANNED = "rework_planned"
    REWORK_GRAPH_PATCH_REVIEWED = "rework_graph_patch_reviewed"
    REWORK_GRAPH_PATCH_APPROVED = "rework_graph_patch_approved"
    REWORK_TICKET_CREATED = "rework_ticket_created"
    REWORK_ATTEMPT_STARTED = "rework_attempt_started"
    REWORK_ATTEMPT_SUBMITTED = "rework_attempt_submitted"
    REWORK_REVIEWED = "rework_reviewed"
    REWORK_ACCEPTED = "rework_accepted"
    REWORK_ESCALATED = "rework_escalated"
    REWORK_EXHAUSTED = "rework_exhausted"
```

Keep existing values unchanged.

- [ ] **Step 4: Run event taxonomy test and verify it passes**

Run:

```bash
PYTHONPATH=src python -m pytest tests/reducers/test_event_record.py::test_event_record_accepts_rework_event_types -q
```

Expected: PASS.

- [ ] **Step 5: Write runtime boundary test for rework events**

Append to `tests/execution/test_runtime_executor_boundary.py`:

```python
import pytest

from boardroom_os.events.types import EventType
from boardroom_os.execution.runtime_executor import RuntimeEventBoundary, RuntimeExecutorError


@pytest.mark.parametrize(
    "event_type",
    (
        EventType.REWORK_REQUESTED,
        EventType.REWORK_PLANNED,
        EventType.REWORK_GRAPH_PATCH_REVIEWED,
        EventType.REWORK_GRAPH_PATCH_APPROVED,
        EventType.REWORK_TICKET_CREATED,
        EventType.REWORK_REVIEWED,
        EventType.REWORK_ACCEPTED,
        EventType.REWORK_ESCALATED,
        EventType.REWORK_EXHAUSTED,
    ),
)
def test_runtime_boundary_rejects_rework_governance_events(event_type: EventType) -> None:
    with pytest.raises(RuntimeExecutorError, match="runtime cannot emit governance event"):
        RuntimeEventBoundary.require_runtime_fact_event(event_type)


@pytest.mark.parametrize(
    "event_type",
    (
        EventType.REWORK_ATTEMPT_STARTED,
        EventType.REWORK_ATTEMPT_SUBMITTED,
    ),
)
def test_runtime_boundary_allows_only_rework_attempt_fact_events(event_type: EventType) -> None:
    RuntimeEventBoundary.require_runtime_fact_event(event_type)
```

If imports already exist, merge them instead of duplicating.

- [ ] **Step 6: Run runtime boundary tests and verify they fail**

Run:

```bash
PYTHONPATH=src python -m pytest \
  tests/execution/test_runtime_executor_boundary.py::test_runtime_boundary_rejects_rework_governance_events \
  tests/execution/test_runtime_executor_boundary.py::test_runtime_boundary_allows_only_rework_attempt_fact_events \
  -q
```

Expected: FAIL until `RuntimeEventBoundary` classifies `REWORK_*` events.

- [ ] **Step 7: Update RuntimeEventBoundary**

Modify `src/boardroom_os/execution/runtime_executor.py` so runtime fact events include only execution facts. Preserve the existing string-value boundary style because `ReservedRuntimeGovernanceEvent.PROJECT_COMPLETED`（保留运行时治理事件：项目完成） is intentionally not an `EventType`（事件类型） member:

```python
class RuntimeEventBoundary:
    _ALLOWED_FACT_EVENT_VALUES = {
        EventType.EXECUTION_STARTED.value,
        EventType.PROVIDER_ATTEMPT_RECORDED.value,
        EventType.TOOL_ATTEMPT_RECORDED.value,
        EventType.WORK_PRODUCT_SUBMITTED.value,
        EventType.COMMAND_RUN_RECORDED.value,
        EventType.REWORK_ATTEMPT_STARTED.value,
        EventType.REWORK_ATTEMPT_SUBMITTED.value,
    }
    _REJECTED_GOVERNANCE_EVENT_VALUES = {
        EventType.TICKET_COMPLETED.value,
        EventType.CLOSEOUT_COMMITTED.value,
        EventType.REWORK_REQUESTED.value,
        EventType.REWORK_PLANNED.value,
        EventType.REWORK_GRAPH_PATCH_REVIEWED.value,
        EventType.REWORK_GRAPH_PATCH_APPROVED.value,
        EventType.REWORK_TICKET_CREATED.value,
        EventType.REWORK_REVIEWED.value,
        EventType.REWORK_ACCEPTED.value,
        EventType.REWORK_ESCALATED.value,
        EventType.REWORK_EXHAUSTED.value,
        ReservedRuntimeGovernanceEvent.PROJECT_COMPLETED.value,
    }

    @classmethod
    def require_runtime_fact_event(cls, event_type: EventType | str) -> EventType:
        normalized = cls._normalize_event_type(event_type)
        if normalized in cls._REJECTED_GOVERNANCE_EVENT_VALUES:
            raise RuntimeExecutorError(f"runtime cannot emit governance event: {normalized}")
        if normalized not in cls._ALLOWED_FACT_EVENT_VALUES:
            raise RuntimeExecutorError(f"unknown runtime event: {normalized}")
        return EventType(normalized)

    @staticmethod
    def _normalize_event_type(event_type: EventType | str) -> str:
        if isinstance(event_type, EventType):
            return event_type.value
        if isinstance(event_type, str):
            return event_type.strip()
        raise RuntimeExecutorError(f"unknown runtime event: {event_type!r}")
```

This keeps `PROJECT_COMPLETED` as a rejected reserved string without introducing unrelated project completion semantics into `EventType`（事件类型）.

- [ ] **Step 8: Run runtime boundary tests and verify they pass**

Run:

```bash
PYTHONPATH=src python -m pytest tests/execution/test_runtime_executor_boundary.py -q
```

Expected: PASS.

- [ ] **Step 9: Commit Task 1**

```bash
git add src/boardroom_os/events/types.py src/boardroom_os/execution/runtime_executor.py tests/reducers/test_event_record.py tests/execution/test_runtime_executor_boundary.py
git commit -m "feat(rework): 增加返工事件分类"
```

---

### Task 2: Write Fail-Closed Rework Reducer Tests

**Files:**
- Create `tests/negative/test_rework_reducer_fail_closed.py`

- [ ] **Step 1: Create negative test fixtures**

Create `tests/negative/test_rework_reducer_fail_closed.py`:

```python
from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import ValidationError

from boardroom_os.agents.seat import RoleCategory, SeatDemand
from boardroom_os.agents.skills import CapabilityTag
from boardroom_os.contracts.evidence_obligation import RequiredArtifactType
from boardroom_os.contracts.types import AcceptanceRef, ContractId, EvidenceObligationRef, SourceSurfaceRef
from boardroom_os.events.record import EventRecord
from boardroom_os.events.types import ActorRef, EventId, EventPayloadRef, EventType, ProjectRef
from boardroom_os.execution.context_index import ProviderAttemptRef
from boardroom_os.execution.package import ExecutionPackageRef
from boardroom_os.graph.ticket import TicketCreatedPayload, TicketId
from boardroom_os.reducers.rework import (
    GraphPatchApprovalPayload,
    GraphPatchReviewGate,
    GraphPatchReviewPayload,
    ReworkAttemptPayload,
    ReworkPlanPayload,
    ReworkReducer,
    ReworkReducerError,
    ReworkReducerPayloadResolver,
    ReworkRequestPayload,
    ReworkReviewPayload,
    ReworkTerminalPayload,
)
from boardroom_os.rework.model import (
    BlockerRef,
    GraphPatchApprovalSet,
    GraphPatchApprovalSetId,
    GraphPatchApprovalStatus,
    GraphPatchOperationKind,
    GraphPatchReview,
    GraphPatchReviewDomain,
    GraphPatchReviewId,
    GraphPatchReviewStatus,
    ReworkActorKind,
    ReworkAttempt,
    ReworkAttemptId,
    ReworkCycleId,
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
    ReworkTerminationDecision,
    ReworkTerminationDecisionId,
    ReworkTerminationReason,
    RunId,
    TicketGraphPatch,
    TicketGraphPatchId,
    TicketGraphPatchOperation,
    TicketGraphPatchOperationId,
)

NOW = datetime(2026, 6, 14, 10, 0, tzinfo=UTC)
PROJECT = ProjectRef(value="project.v2-100b")
ACCEPTANCE = AcceptanceRef(value="acceptance.book.add")
SURFACE = SourceSurfaceRef(value="surface.backend.api")
OBLIGATION = EvidenceObligationRef(value="evidence.add.api")
CYCLE = ReworkCycleId(value="rework-cycle.v2-100b")
REQUEST_ID = ReworkRequestId(value="rework-request.v2-100b")
PLAN_ID = ReworkPlanId(value="rework-plan.v2-100b")
PATCH_ID = TicketGraphPatchId(value="ticket-graph-patch.v2-100b")
REWORK_TICKET = TicketId(value="ticket.rework.backend-api-shape")
BLOCKER = BlockerRef(value="blocker.probe-response-shape")
```

- [ ] **Step 2: Add object builders**

Add to the same file:

```python
def _issue() -> ReworkIssue:
    return ReworkIssue(
        issue_id=ReworkIssueId(value="rework-issue.probe-response-shape"),
        blocker_refs=(BLOCKER,),
        issue_code=ReworkIssueCode.PROBE_RESPONSE_SHAPE_MISMATCH,
        severity=ReworkIssueSeverity.BLOCKING,
        acceptance_refs=(ACCEPTANCE,),
        source_surface_refs=(SURFACE,),
        run_manifest_refs=("run-manifest.v2-090f",),
        evidence_obligation_refs=(OBLIGATION,),
        suspected_domains=(ReworkSuspectedDomain.IMPLEMENTATION, ReworkSuspectedDomain.PROBE),
        required_artifact_types=(RequiredArtifactType(value="live_blackbox_integration"),),
        description="Probe expects $.title but backend returns $.book.title.",
    )


def _request() -> ReworkRequest:
    return ReworkRequest(
        rework_request_id=REQUEST_ID,
        cycle_id=CYCLE,
        run_id=RunId(value="run.v2-100b"),
        request_source_refs=("blocker-report.final-evidence",),
        issues=(_issue(),),
        requested_by_actor=ReworkActorKind.CHECKER,
        requested_at=NOW,
        active_contract_refs=(ContractId(value="acceptance.v2-090f"), ContractId(value="package.v2-090f")),
        active_graph_version=40,
    )


def _patch() -> TicketGraphPatch:
    operation = TicketGraphPatchOperation(
        operation_id=TicketGraphPatchOperationId(value="op.create-rework-ticket"),
        operation_kind=GraphPatchOperationKind.CREATE_REWORK_TICKET,
        target_ticket_refs=(REWORK_TICKET,),
        acceptance_refs=(ACCEPTANCE,),
        source_surface_refs=(SURFACE,),
        evidence_obligation_refs=(OBLIGATION,),
        rationale="Create bounded rework ticket for API response shape.",
    )
    return TicketGraphPatch(
        ticket_graph_patch_id=PATCH_ID,
        base_graph_version=40,
        proposed_by_plan_ref=PLAN_ID,
        operations=(operation,),
        affected_ticket_refs=(REWORK_TICKET,),
        affected_contract_refs=(ContractId(value="acceptance.v2-090f"),),
        affected_source_surface_refs=(SURFACE,),
        required_review_domains=(
            GraphPatchReviewDomain.PLANNING,
            GraphPatchReviewDomain.STRUCTURAL,
            GraphPatchReviewDomain.BLOCKER_COVERAGE,
            GraphPatchReviewDomain.BEHAVIORAL_PROBE,
        ),
        patch_hash="sha256:ticket-graph-patch.v2-100b",
    )


def _plan() -> ReworkPlan:
    decision = ReworkDecision(
        decision_id=ReworkDecisionId(value="decision.fix-api-shape"),
        decision_kind=ReworkDecisionKind.FIX_IMPLEMENTATION,
        blocker_refs=(BLOCKER,),
        issue_ids=(_issue().issue_id,),
        target_ticket_refs=(REWORK_TICKET,),
        target_graph_operation_refs=(_patch().operations[0].operation_id,),
        rationale="Fix backend implementation to satisfy active probe.",
    )
    return ReworkPlan(
        rework_plan_id=PLAN_ID,
        cycle_id=CYCLE,
        rework_request_id=REQUEST_ID,
        planner_actor=ReworkActorKind.CEO,
        planner_attempt_ref=ProviderAttemptRef(value="provider-attempt.ceo.rework-plan"),
        decisions=(decision,),
        ticket_graph_patch_ref=PATCH_ID,
        risk_notes=("Do not change acceptance refs without contract revision.",),
        stop_or_escalation_conditions=("Escalate after two identical blocker rounds.",),
    )


def _review(
    domain: GraphPatchReviewDomain,
    role: ReworkActorKind,
    *,
    status: GraphPatchReviewStatus = GraphPatchReviewStatus.APPROVED,
    suffix: str | None = None,
) -> GraphPatchReview:
    name = suffix or domain.value
    return GraphPatchReview(
        graph_patch_review_id=GraphPatchReviewId(value=f"graph-patch-review.{name}"),
        ticket_graph_patch_ref=PATCH_ID,
        review_domain=domain,
        reviewer_actor=role,
        reviewer_role_kind=role,
        reviewer_attempt_ref=ProviderAttemptRef(value=f"provider-attempt.{role.value}.{domain.value}"),
        status=status,
        checked_invariants=(f"{domain.value} invariant checked.",),
        blockers=() if status is GraphPatchReviewStatus.APPROVED else (BLOCKER,),
        non_blocking_notes=(),
        created_at=NOW,
    )


def _approval_set(
    status: GraphPatchApprovalStatus = GraphPatchApprovalStatus.READY_TO_COMMIT,
) -> GraphPatchApprovalSet:
    return GraphPatchApprovalSet(
        approval_set_id=GraphPatchApprovalSetId(value="graph-patch-approval.v2-100b"),
        ticket_graph_patch_ref=PATCH_ID,
        required_domains=_patch().required_review_domains,
        reviews=(
            _review(GraphPatchReviewDomain.PLANNING, ReworkActorKind.CEO),
            _review(GraphPatchReviewDomain.STRUCTURAL, ReworkActorKind.ARCHITECT),
            _review(GraphPatchReviewDomain.BLOCKER_COVERAGE, ReworkActorKind.CHECKER),
            _review(GraphPatchReviewDomain.BEHAVIORAL_PROBE, ReworkActorKind.TESTER),
        ),
        status=status,
        computed_at=NOW,
    )
```

- [ ] **Step 3: Add event and resolver helpers**

Add:

```python
def _event(
    event_type: EventType,
    *,
    graph_version: int,
    actor_ref: str,
    payload_ref: str | None = None,
) -> EventRecord:
    payload = payload_ref or f"payload:{event_type.value}"
    return EventRecord(
        event_id=EventId(value=f"evt:{event_type.value}:{graph_version}"),
        event_type=event_type,
        project_ref=PROJECT,
        actor_ref=ActorRef(value=actor_ref),
        timestamp=NOW,
        graph_version=graph_version,
        payload_refs=(EventPayloadRef(value=payload),),
    )


class InMemoryReworkResolver(ReworkReducerPayloadResolver):
    def __init__(self, **payloads: dict[str, Any]) -> None:
        self.request_payloads = payloads.get("request_payloads", {})
        self.plan_payloads = payloads.get("plan_payloads", {})
        self.review_payloads = payloads.get("review_payloads", {})
        self.approval_payloads = payloads.get("approval_payloads", {})
        self.ticket_payloads = payloads.get("ticket_payloads", {})
        self.attempt_payloads = payloads.get("attempt_payloads", {})
        self.review_outcome_payloads = payloads.get("review_outcome_payloads", {})
        self.terminal_payloads = payloads.get("terminal_payloads", {})

    def resolve_rework_request(self, payload_ref: EventPayloadRef) -> ReworkRequestPayload:
        return self.request_payloads[payload_ref.value]

    def resolve_rework_plan(self, payload_ref: EventPayloadRef) -> ReworkPlanPayload:
        return self.plan_payloads[payload_ref.value]

    def resolve_graph_patch_review(self, payload_ref: EventPayloadRef) -> GraphPatchReviewPayload:
        return self.review_payloads[payload_ref.value]

    def resolve_graph_patch_approval(self, payload_ref: EventPayloadRef) -> GraphPatchApprovalPayload:
        return self.approval_payloads[payload_ref.value]

    def resolve_rework_ticket_created(self, payload_ref: EventPayloadRef) -> TicketCreatedPayload:
        return self.ticket_payloads[payload_ref.value]

    def resolve_rework_attempt(self, payload_ref: EventPayloadRef) -> ReworkAttemptPayload:
        return self.attempt_payloads[payload_ref.value]

    def resolve_rework_review(self, payload_ref: EventPayloadRef) -> ReworkReviewPayload:
        return self.review_outcome_payloads[payload_ref.value]

    def resolve_rework_terminal(self, payload_ref: EventPayloadRef) -> ReworkTerminalPayload:
        return self.terminal_payloads[payload_ref.value]
```

- [ ] **Step 4: Add negative tests for actor permissions and ordering**

Add:

```python
def test_runtime_actor_cannot_accept_escalate_or_exhaust_rework() -> None:
    resolver = InMemoryReworkResolver(
        terminal_payloads={
            "payload:rework_accepted": ReworkTerminalPayload(
                cycle_id=CYCLE,
                outcome_ref=ReworkOutcomeId(value="rework-outcome.accepted"),
                termination_decision_ref=None,
                accepted_blocker_refs=(BLOCKER,),
                remaining_blocker_refs=(),
            )
        }
    )

    with pytest.raises(ReworkReducerError, match="runtime/executor/atomic-agent cannot emit governance"):
        ReworkReducer(resolver).reduce(
            (
                _event(
                    EventType.REWORK_ACCEPTED,
                    graph_version=50,
                    actor_ref="runtime:executor",
                    payload_ref="payload:rework_accepted",
                ),
            )
        )


def test_rework_planned_without_requested_fails() -> None:
    resolver = InMemoryReworkResolver(
        plan_payloads={
            "payload:rework_planned": ReworkPlanPayload(
                request_ref=REQUEST_ID,
                plan=_plan(),
                patch=_patch(),
            )
        }
    )

    with pytest.raises(ReworkReducerError, match="request must exist before rework_planned"):
        ReworkReducer(resolver).reduce(
            (
                _event(
                    EventType.REWORK_PLANNED,
                    graph_version=41,
                    actor_ref="seat-ceo",
                    payload_ref="payload:rework_planned",
                ),
            )
        )
```

- [ ] **Step 5: Add negative tests for GraphPatchReviewGate**

Add:

```python
def test_graph_patch_review_gate_rejects_missing_required_domain() -> None:
    incomplete = GraphPatchApprovalSet(
        approval_set_id=GraphPatchApprovalSetId(value="graph-patch-approval.incomplete"),
        ticket_graph_patch_ref=PATCH_ID,
        required_domains=_patch().required_review_domains,
        reviews=(
            _review(GraphPatchReviewDomain.PLANNING, ReworkActorKind.CEO),
            _review(GraphPatchReviewDomain.STRUCTURAL, ReworkActorKind.ARCHITECT),
            _review(GraphPatchReviewDomain.BLOCKER_COVERAGE, ReworkActorKind.CHECKER),
        ),
        status=GraphPatchApprovalStatus.INCOMPLETE,
        computed_at=NOW,
    )

    with pytest.raises(ReworkReducerError, match="missing required review domain"):
        GraphPatchReviewGate.evaluate(_patch(), incomplete)


def test_graph_patch_review_gate_rejects_rejected_review() -> None:
    rejected = GraphPatchApprovalSet(
        approval_set_id=GraphPatchApprovalSetId(value="graph-patch-approval.rejected"),
        ticket_graph_patch_ref=PATCH_ID,
        required_domains=_patch().required_review_domains,
        reviews=(
            _review(GraphPatchReviewDomain.PLANNING, ReworkActorKind.CEO),
            _review(GraphPatchReviewDomain.STRUCTURAL, ReworkActorKind.ARCHITECT),
            _review(GraphPatchReviewDomain.BLOCKER_COVERAGE, ReworkActorKind.CHECKER),
            _review(
                GraphPatchReviewDomain.BEHAVIORAL_PROBE,
                ReworkActorKind.TESTER,
                status=GraphPatchReviewStatus.REJECTED,
            ),
        ),
        status=GraphPatchApprovalStatus.REJECTED,
        computed_at=NOW,
    )

    with pytest.raises(ReworkReducerError, match="graph patch approval is not ready"):
        GraphPatchReviewGate.evaluate(_patch(), rejected)
```

- [ ] **Step 6: Add negative tests for unsafe patch and stale acceptance**

Add:

```python
def test_rework_ticket_created_rejects_allowed_write_set_expansion_outside_patch_surface() -> None:
    ticket_payload = TicketCreatedPayload(
        ticket_id=REWORK_TICKET,
        purpose="Fix backend API response shape",
        seat_demand=SeatDemand(
            required_role_category=RoleCategory.IMPLEMENTATION,
            required_capability_tags=(
                CapabilityTag(value="task.implementation"),
                CapabilityTag(value="surface.backend"),
            ),
        ),
        depends_on=(),
        acceptance_refs=(ACCEPTANCE.value,),
        source_surface_refs=(SURFACE.value,),
        evidence_obligations=(OBLIGATION.value,),
        allowed_read_refs=("contract:acceptance.v2-090f",),
        allowed_write_set=("10-project/**",),
        attempt_count=0,
    )
    resolver = InMemoryReworkResolver(
        request_payloads={"payload:request": ReworkRequestPayload(request=_request())},
        plan_payloads={"payload:plan": ReworkPlanPayload(request_ref=REQUEST_ID, plan=_plan(), patch=_patch())},
        approval_payloads={
            "payload:approval": GraphPatchApprovalPayload(
                patch_ref=PATCH_ID,
                approval_set=_approval_set(),
            )
        },
        ticket_payloads={"payload:ticket": ticket_payload},
    )

    with pytest.raises(ReworkReducerError, match="allowed_write_set"):
        ReworkReducer(resolver).reduce(
            (
                _event(EventType.REWORK_REQUESTED, graph_version=41, actor_ref="seat-checker", payload_ref="payload:request"),
                _event(EventType.REWORK_PLANNED, graph_version=42, actor_ref="seat-ceo", payload_ref="payload:plan"),
                _event(EventType.REWORK_GRAPH_PATCH_APPROVED, graph_version=43, actor_ref="governance:graph-patch-review-gate", payload_ref="payload:approval"),
                _event(EventType.REWORK_TICKET_CREATED, graph_version=44, actor_ref="governance:command-handler", payload_ref="payload:ticket"),
            )
        )
```

The target behavior is a fail-closed rejection caused by write-set expansion（允许写集合扩大）, not Pydantic parsing.

- [ ] **Step 7: Run negative tests and verify they fail**

Run:

```bash
PYTHONPATH=src python -m pytest tests/negative/test_rework_reducer_fail_closed.py -q
```

Expected: FAIL with `ModuleNotFoundError: boardroom_os.reducers.rework`.

---

### Task 3: Implement Rework Reducer Payload Models And GraphPatchReviewGate

**Files:**
- Create `src/boardroom_os/reducers/rework.py`
- Modify `src/boardroom_os/reducers/errors.py` if centralizing `ReworkReducerError`
- Run `tests/negative/test_rework_reducer_fail_closed.py`

- [ ] **Step 1: Create reducer module skeleton**

Create `src/boardroom_os/reducers/rework.py`:

```python
from __future__ import annotations

from enum import StrEnum
from typing import Protocol, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from boardroom_os.events.record import EventRecord
from boardroom_os.events.types import EventId, EventPayloadRef, EventType, ProjectRef
from boardroom_os.execution.package import ExecutionPackageRef
from boardroom_os.graph.ticket import TicketCreatedPayload, TicketId
from boardroom_os.rework.model import (
    BlockerRef,
    GraphPatchApprovalSet,
    GraphPatchApprovalStatus,
    GraphPatchReview,
    GraphPatchReviewDomain,
    GraphPatchReviewStatus,
    ReworkActorKind,
    ReworkAttempt,
    ReworkAttemptId,
    ReworkCycleId,
    ReworkCycleStatus,
    ReworkOutcome,
    ReworkOutcomeId,
    ReworkOutcomeStatus,
    ReworkPlan,
    ReworkPlanId,
    ReworkRequest,
    ReworkRequestId,
    ReworkTerminationDecision,
    ReworkTerminationDecisionId,
    TicketGraphPatch,
    TicketGraphPatchId,
)


class ReworkReducerError(ValueError):
    pass


class ReworkTerminalStatus(StrEnum):
    OPEN = "open"
    ACCEPTED = "accepted"
    ESCALATED = "escalated"
    EXHAUSTED = "exhausted"
```

- [ ] **Step 2: Add payload models**

Add to `rework.py`:

```python
class ReworkRequestPayload(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    request: ReworkRequest


class ReworkPlanPayload(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    request_ref: ReworkRequestId
    plan: ReworkPlan
    patch: TicketGraphPatch

    @model_validator(mode="after")
    def _validate_plan_patch_binding(self) -> Self:
        if self.plan.rework_request_id != self.request_ref:
            raise ReworkReducerError("plan request_ref mismatch")
        if self.plan.rework_plan_id != self.patch.proposed_by_plan_ref:
            raise ReworkReducerError("patch proposed_by_plan_ref mismatch")
        if self.plan.ticket_graph_patch_ref != self.patch.ticket_graph_patch_id:
            raise ReworkReducerError("plan ticket_graph_patch_ref mismatch")
        return self


class GraphPatchReviewPayload(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    patch_ref: TicketGraphPatchId
    review: GraphPatchReview

    @model_validator(mode="after")
    def _validate_review_patch_binding(self) -> Self:
        if self.review.ticket_graph_patch_ref != self.patch_ref:
            raise ReworkReducerError("graph patch review ref mismatch")
        return self


class GraphPatchApprovalPayload(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    patch_ref: TicketGraphPatchId
    approval_set: GraphPatchApprovalSet

    @model_validator(mode="after")
    def _validate_approval_patch_binding(self) -> Self:
        if self.approval_set.ticket_graph_patch_ref != self.patch_ref:
            raise ReworkReducerError("graph patch approval ref mismatch")
        return self


class ReworkAttemptPayload(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    attempt: ReworkAttempt


class ReworkReviewPayload(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    outcome: ReworkOutcome


class ReworkTerminalPayload(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    cycle_id: ReworkCycleId | str
    outcome_ref: ReworkOutcomeId | None = None
    termination_decision_ref: ReworkTerminationDecisionId | None = None
    accepted_blocker_refs: tuple[BlockerRef, ...] = ()
    remaining_blocker_refs: tuple[BlockerRef, ...] = ()
```

- [ ] **Step 3: Add resolver protocol**

Add:

```python
class ReworkReducerPayloadResolver(Protocol):
    def resolve_rework_request(self, payload_ref: EventPayloadRef) -> ReworkRequestPayload: ...
    def resolve_rework_plan(self, payload_ref: EventPayloadRef) -> ReworkPlanPayload: ...
    def resolve_graph_patch_review(self, payload_ref: EventPayloadRef) -> GraphPatchReviewPayload: ...
    def resolve_graph_patch_approval(self, payload_ref: EventPayloadRef) -> GraphPatchApprovalPayload: ...
    def resolve_rework_ticket_created(self, payload_ref: EventPayloadRef) -> TicketCreatedPayload: ...
    def resolve_rework_attempt(self, payload_ref: EventPayloadRef) -> ReworkAttemptPayload: ...
    def resolve_rework_review(self, payload_ref: EventPayloadRef) -> ReworkReviewPayload: ...
    def resolve_rework_terminal(self, payload_ref: EventPayloadRef) -> ReworkTerminalPayload: ...
```

- [ ] **Step 4: Implement GraphPatchReviewGate**

Add:

```python
class GraphPatchReviewGate:
    @staticmethod
    def evaluate(
        patch: TicketGraphPatch,
        approval_set: GraphPatchApprovalSet,
    ) -> GraphPatchApprovalSet:
        if approval_set.ticket_graph_patch_ref != patch.ticket_graph_patch_id:
            raise ReworkReducerError("approval set patch ref mismatch")
        if approval_set.status is not GraphPatchApprovalStatus.READY_TO_COMMIT:
            raise ReworkReducerError("graph patch approval is not ready")

        required = set(patch.required_review_domains)
        declared = set(approval_set.required_domains)
        if required != declared:
            raise ReworkReducerError("approval set required domains must match patch")

        approved_domains: set[GraphPatchReviewDomain] = set()
        for review in approval_set.reviews:
            if review.ticket_graph_patch_ref != patch.ticket_graph_patch_id:
                raise ReworkReducerError("review patch ref mismatch")
            if review.review_domain not in required:
                raise ReworkReducerError("review domain is not required by patch")
            if review.status is not GraphPatchReviewStatus.APPROVED:
                raise ReworkReducerError("graph patch approval is not ready")
            approved_domains.add(review.review_domain)

        missing = required - approved_domains
        if missing:
            names = ", ".join(sorted(domain.value for domain in missing))
            raise ReworkReducerError(f"missing required review domain: {names}")
        return approval_set
```

- [ ] **Step 5: Run GraphPatchReviewGate negative tests**

Run:

```bash
PYTHONPATH=src python -m pytest \
  tests/negative/test_rework_reducer_fail_closed.py::test_graph_patch_review_gate_rejects_missing_required_domain \
  tests/negative/test_rework_reducer_fail_closed.py::test_graph_patch_review_gate_rejects_rejected_review \
  -q
```

Expected: PASS for gate failures.

- [ ] **Step 6: Commit Task 3**

```bash
git add src/boardroom_os/reducers/rework.py tests/negative/test_rework_reducer_fail_closed.py
git commit -m "feat(rework): 增加图补丁审查门禁"
```

---

### Task 4: Implement Rework Projection And Reducer Ordering

**Files:**
- Modify `src/boardroom_os/reducers/rework.py`
- Modify `tests/negative/test_rework_reducer_fail_closed.py`

- [ ] **Step 1: Add ReworkProjection**

Add to `rework.py`:

```python
class ReworkProjection(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    project_ref: ProjectRef
    graph_version: int = Field(gt=0)
    cycle_id: ReworkCycleId | str
    status: ReworkCycleStatus
    terminal_status: ReworkTerminalStatus = ReworkTerminalStatus.OPEN
    request_ref: ReworkRequestId | None = None
    plan_ref: ReworkPlanId | None = None
    patch_ref: TicketGraphPatchId | None = None
    approval_set_ref: str | None = None
    rework_ticket_refs: tuple[TicketId, ...] = ()
    attempt_refs: tuple[ReworkAttemptId, ...] = ()
    outcome_refs: tuple[ReworkOutcomeId, ...] = ()
    accepted_blocker_refs: tuple[BlockerRef, ...] = ()
    remaining_blocker_refs: tuple[BlockerRef, ...] = ()
    committed_event_refs: tuple[EventId, ...] = ()
    checked_refs: tuple[str, ...] = ()

    @field_validator(
        "rework_ticket_refs",
        "attempt_refs",
        "outcome_refs",
        "accepted_blocker_refs",
        "remaining_blocker_refs",
        "committed_event_refs",
    )
    @classmethod
    def _reject_duplicate_refs(cls, values: tuple[object, ...]) -> tuple[object, ...]:
        raw = [getattr(value, "value", str(value)) for value in values]
        if len(raw) != len(set(raw)):
            raise ReworkReducerError("projection refs must be unique")
        return values
```

- [ ] **Step 2: Add reducer class skeleton**

Add:

```python
_GOVERNANCE_TERMINAL_EVENTS = {
    EventType.REWORK_ACCEPTED,
    EventType.REWORK_ESCALATED,
    EventType.REWORK_EXHAUSTED,
}


class ReworkReducer:
    def __init__(self, payload_resolver: ReworkReducerPayloadResolver) -> None:
        self._payload_resolver = payload_resolver

    def reduce(self, events: tuple[EventRecord, ...]) -> ReworkProjection:
        if not events:
            raise ReworkReducerError("events must not be empty")
        self._pre_scan_events(events)

        project_ref = events[0].project_ref
        graph_version = 0
        request: ReworkRequest | None = None
        plan: ReworkPlan | None = None
        patch: TicketGraphPatch | None = None
        approved = False
        rework_ticket_refs: list[TicketId] = []
        attempt_refs: list[ReworkAttemptId] = []
        outcome_refs: list[ReworkOutcomeId] = []
        accepted_blockers: tuple[BlockerRef, ...] = ()
        remaining_blockers: tuple[BlockerRef, ...] = ()
        committed_event_refs: list[EventId] = []
        checked_refs: list[str] = []
        status = ReworkCycleStatus.REQUESTED
        terminal_status = ReworkTerminalStatus.OPEN

        for event in events:
            self._require_single_payload_ref(event)
            graph_version = event.graph_version
            payload_ref = event.payload_refs[0]
            committed_event_refs.append(event.event_id)

            if event.event_type is EventType.REWORK_REQUESTED:
                if request is not None:
                    raise ReworkReducerError("duplicate rework request")
                payload = self._resolve_request(payload_ref)
                request = payload.request
                checked_refs.append(request.rework_request_id.value)
                status = ReworkCycleStatus.REQUESTED
                continue

            if event.event_type is EventType.REWORK_PLANNED:
                if request is None:
                    raise ReworkReducerError("request must exist before rework_planned")
                payload = self._resolve_plan(payload_ref)
                if payload.request_ref != request.rework_request_id:
                    raise ReworkReducerError("rework plan does not match request")
                plan = payload.plan
                patch = payload.patch
                checked_refs.extend((plan.rework_plan_id.value, patch.ticket_graph_patch_id.value))
                status = ReworkCycleStatus.PLANNED
                continue

            if event.event_type is EventType.REWORK_GRAPH_PATCH_APPROVED:
                if patch is None:
                    raise ReworkReducerError("patch must exist before graph patch approval")
                payload = self._resolve_approval(payload_ref)
                GraphPatchReviewGate.evaluate(patch, payload.approval_set)
                approved = True
                checked_refs.append(payload.approval_set.approval_set_id.value)
                continue

            if event.event_type is EventType.REWORK_TICKET_CREATED:
                if patch is None or not approved:
                    raise ReworkReducerError("approved patch required before rework ticket creation")
                ticket_payload = self._resolve_ticket(payload_ref)
                self._validate_rework_ticket_payload(ticket_payload, patch)
                rework_ticket_refs.append(ticket_payload.ticket_id)
                checked_refs.append(ticket_payload.ticket_id.value)
                status = ReworkCycleStatus.EXECUTING
                continue

            if event.event_type in {EventType.REWORK_ATTEMPT_STARTED, EventType.REWORK_ATTEMPT_SUBMITTED}:
                if not rework_ticket_refs:
                    raise ReworkReducerError("rework ticket must exist before attempt")
                payload = self._resolve_attempt(payload_ref)
                if payload.attempt.ticket_ref not in rework_ticket_refs:
                    raise ReworkReducerError("rework attempt ticket is not approved")
                if event.event_type is EventType.REWORK_ATTEMPT_SUBMITTED:
                    attempt_refs.append(payload.attempt.rework_attempt_id)
                    status = ReworkCycleStatus.REVIEWING
                checked_refs.append(payload.attempt.rework_attempt_id.value)
                continue

            if event.event_type is EventType.REWORK_REVIEWED:
                if not attempt_refs:
                    raise ReworkReducerError("submitted attempt required before rework review")
                payload = self._resolve_review(payload_ref)
                outcome_refs.append(payload.outcome.rework_outcome_id)
                remaining_blockers = payload.outcome.remaining_blocker_refs
                accepted_blockers = payload.outcome.accepted_blocker_refs
                checked_refs.append(payload.outcome.rework_outcome_id.value)
                continue

            if event.event_type in _GOVERNANCE_TERMINAL_EVENTS:
                self._reject_runtime_governance(event)
                if not outcome_refs and event.event_type is EventType.REWORK_ACCEPTED:
                    raise ReworkReducerError("reviewed outcome required before accepted")
                payload = self._resolve_terminal(payload_ref)
                if event.event_type is EventType.REWORK_ACCEPTED:
                    if remaining_blockers:
                        raise ReworkReducerError("remaining blockers must be empty before accepted")
                    terminal_status = ReworkTerminalStatus.ACCEPTED
                    status = ReworkCycleStatus.ACCEPTED
                    accepted_blockers = payload.accepted_blocker_refs
                elif event.event_type is EventType.REWORK_ESCALATED:
                    terminal_status = ReworkTerminalStatus.ESCALATED
                    status = ReworkCycleStatus.ESCALATED
                    remaining_blockers = payload.remaining_blocker_refs
                else:
                    terminal_status = ReworkTerminalStatus.EXHAUSTED
                    status = ReworkCycleStatus.EXHAUSTED
                    remaining_blockers = payload.remaining_blocker_refs
                continue

        if request is None:
            raise ReworkReducerError("rework request event is required")

        return ReworkProjection(
            project_ref=project_ref,
            graph_version=graph_version,
            cycle_id=request.cycle_id,
            status=status,
            terminal_status=terminal_status,
            request_ref=request.rework_request_id,
            plan_ref=plan.rework_plan_id if plan else None,
            patch_ref=patch.ticket_graph_patch_id if patch else None,
            rework_ticket_refs=tuple(dict.fromkeys(rework_ticket_refs)),
            attempt_refs=tuple(dict.fromkeys(attempt_refs)),
            outcome_refs=tuple(dict.fromkeys(outcome_refs)),
            accepted_blocker_refs=accepted_blockers,
            remaining_blocker_refs=remaining_blockers,
            committed_event_refs=tuple(committed_event_refs),
            checked_refs=tuple(dict.fromkeys(checked_refs)),
        )
```

- [ ] **Step 3: Add resolver helper methods and event validation**

Add methods inside `ReworkReducer`:

```python
    @staticmethod
    def _pre_scan_events(events: tuple[EventRecord, ...]) -> None:
        project_ref = events[0].project_ref
        previous_graph_version = 0
        terminal_seen = False
        for event in events:
            if event.project_ref != project_ref:
                raise ReworkReducerError("events must belong to one project_ref")
            if event.graph_version <= previous_graph_version:
                raise ReworkReducerError("events must be strictly increasing by graph_version")
            previous_graph_version = event.graph_version
            if terminal_seen:
                raise ReworkReducerError("events after rework terminal event are not allowed")
            if event.event_type in _GOVERNANCE_TERMINAL_EVENTS:
                terminal_seen = True

    @staticmethod
    def _require_single_payload_ref(event: EventRecord) -> None:
        if len(event.payload_refs) != 1:
            raise ReworkReducerError("event must have exactly one payload_ref")

    @staticmethod
    def _reject_runtime_governance(event: EventRecord) -> None:
        actor = event.actor_ref.value
        if actor.startswith(("runtime:", "executor:", "atomic-agent:")):
            raise ReworkReducerError("runtime/executor/atomic-agent cannot emit governance event")

    def _resolve_request(self, payload_ref: EventPayloadRef) -> ReworkRequestPayload:
        try:
            return self._payload_resolver.resolve_rework_request(payload_ref)
        except Exception as error:
            raise ReworkReducerError(f"rework request payload could not be resolved: {payload_ref.value}") from error

    def _resolve_plan(self, payload_ref: EventPayloadRef) -> ReworkPlanPayload:
        try:
            return self._payload_resolver.resolve_rework_plan(payload_ref)
        except Exception as error:
            raise ReworkReducerError(f"rework plan payload could not be resolved: {payload_ref.value}") from error

    def _resolve_approval(self, payload_ref: EventPayloadRef) -> GraphPatchApprovalPayload:
        try:
            return self._payload_resolver.resolve_graph_patch_approval(payload_ref)
        except Exception as error:
            raise ReworkReducerError(f"graph patch approval payload could not be resolved: {payload_ref.value}") from error

    def _resolve_ticket(self, payload_ref: EventPayloadRef) -> TicketCreatedPayload:
        try:
            return self._payload_resolver.resolve_rework_ticket_created(payload_ref)
        except Exception as error:
            raise ReworkReducerError(f"rework ticket payload could not be resolved: {payload_ref.value}") from error

    def _resolve_attempt(self, payload_ref: EventPayloadRef) -> ReworkAttemptPayload:
        try:
            return self._payload_resolver.resolve_rework_attempt(payload_ref)
        except Exception as error:
            raise ReworkReducerError(f"rework attempt payload could not be resolved: {payload_ref.value}") from error

    def _resolve_review(self, payload_ref: EventPayloadRef) -> ReworkReviewPayload:
        try:
            return self._payload_resolver.resolve_rework_review(payload_ref)
        except Exception as error:
            raise ReworkReducerError(f"rework review payload could not be resolved: {payload_ref.value}") from error

    def _resolve_terminal(self, payload_ref: EventPayloadRef) -> ReworkTerminalPayload:
        try:
            return self._payload_resolver.resolve_rework_terminal(payload_ref)
        except Exception as error:
            raise ReworkReducerError(f"rework terminal payload could not be resolved: {payload_ref.value}") from error
```

- [ ] **Step 4: Add ticket payload validation**

Add:

```python
    @staticmethod
    def _validate_rework_ticket_payload(
        ticket_payload: TicketCreatedPayload,
        patch: TicketGraphPatch,
    ) -> None:
        affected_tickets = {ticket.value for ticket in patch.affected_ticket_refs}
        if ticket_payload.ticket_id.value not in affected_tickets:
            raise ReworkReducerError("rework ticket is not listed in graph patch")

        patch_acceptance = {ref.value for operation in patch.operations for ref in operation.acceptance_refs}
        patch_surfaces = {ref.value for operation in patch.operations for ref in operation.source_surface_refs}
        patch_obligations = {ref.value for operation in patch.operations for ref in operation.evidence_obligation_refs}

        if not set(ticket_payload.acceptance_refs).issubset(patch_acceptance):
            raise ReworkReducerError("rework ticket acceptance refs must be patch-bound")
        if not set(ticket_payload.source_surface_refs).issubset(patch_surfaces):
            raise ReworkReducerError("rework ticket source surfaces must be patch-bound")
        if not set(ticket_payload.evidence_obligations).issubset(patch_obligations):
            raise ReworkReducerError("rework ticket evidence obligations must be patch-bound")

        for path in ticket_payload.allowed_write_set:
            if path in {"**", "10-project/**", "20-evidence/**", "30-audit/**"}:
                raise ReworkReducerError("allowed_write_set expansion is not allowed")
```

This is intentionally conservative until V2-100C introduces richer allowed-write-set patch semantics（允许写集合补丁语义）.

- [ ] **Step 5: Run negative reducer tests**

Run:

```bash
PYTHONPATH=src python -m pytest tests/negative/test_rework_reducer_fail_closed.py -q
```

Expected: current negative tests pass. If fixture parsing fails before reducer assertions, adjust fixtures to use existing `SeatDemand`（席位需求） and `CapabilityTag`（能力标签） constructors while preserving the same fail-closed assertions.

- [ ] **Step 6: Commit Task 4**

```bash
git add src/boardroom_os/reducers/rework.py tests/negative/test_rework_reducer_fail_closed.py
git commit -m "feat(rework): 增加返工归约器门禁"
```

---

### Task 5: Add Happy Path Rework Reducer Projection Tests

**Files:**
- Create `tests/reducers/test_rework_reducer.py`
- Modify `src/boardroom_os/reducers/rework.py` if happy path exposes gaps

- [ ] **Step 1: Create happy path test file**

Create `tests/reducers/test_rework_reducer.py`:

```python
from datetime import UTC, datetime
from typing import Any

from boardroom_os.agents.seat import RoleCategory, SeatDemand
from boardroom_os.agents.skills import CapabilityTag
from boardroom_os.contracts.evidence_obligation import RequiredArtifactType
from boardroom_os.contracts.types import AcceptanceRef, ContractId, EvidenceObligationRef, SourceSurfaceRef
from boardroom_os.events.record import EventRecord
from boardroom_os.events.types import ActorRef, EventId, EventPayloadRef, EventType, ProjectRef
from boardroom_os.execution.context_index import ProviderAttemptRef
from boardroom_os.execution.package import ExecutionPackageRef
from boardroom_os.graph.ticket import TicketCreatedPayload, TicketId
from boardroom_os.reducers.rework import (
    GraphPatchApprovalPayload,
    ReworkAttemptPayload,
    ReworkPlanPayload,
    ReworkReducer,
    ReworkReducerPayloadResolver,
    ReworkRequestPayload,
    ReworkReviewPayload,
    ReworkTerminalPayload,
    ReworkTerminalStatus,
)
from boardroom_os.rework.model import (
    BlockerRef,
    GraphPatchApprovalSet,
    GraphPatchApprovalSetId,
    GraphPatchApprovalStatus,
    GraphPatchOperationKind,
    GraphPatchReview,
    GraphPatchReviewDomain,
    GraphPatchReviewId,
    GraphPatchReviewStatus,
    ReworkActorKind,
    ReworkAttempt,
    ReworkAttemptId,
    ReworkCycleId,
    ReworkCycleStatus,
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
    TicketGraphPatch,
    TicketGraphPatchId,
    TicketGraphPatchOperation,
    TicketGraphPatchOperationId,
)

NOW = datetime(2026, 6, 14, 11, 0, tzinfo=UTC)
PROJECT = ProjectRef(value="project.v2-100b")
ACCEPTANCE = AcceptanceRef(value="acceptance.book.add")
SURFACE = SourceSurfaceRef(value="surface.backend.api")
OBLIGATION = EvidenceObligationRef(value="evidence.add.api")
CYCLE = ReworkCycleId(value="rework-cycle.v2-100b")
REQUEST_ID = ReworkRequestId(value="rework-request.v2-100b")
PLAN_ID = ReworkPlanId(value="rework-plan.v2-100b")
PATCH_ID = TicketGraphPatchId(value="ticket-graph-patch.v2-100b")
REWORK_TICKET = TicketId(value="ticket.rework.backend-api-shape")
ATTEMPT_ID = ReworkAttemptId(value="rework-attempt.backend-api-shape.1")
OUTCOME_ID = ReworkOutcomeId(value="rework-outcome.backend-api-shape.1")
BLOCKER = BlockerRef(value="blocker.probe-response-shape")
```

- [ ] **Step 2: Add builders**

Add builders equivalent to Task 2, but include a valid `TicketCreatedPayload` and accepted `ReworkOutcome`:

```python
def _issue() -> ReworkIssue:
    return ReworkIssue(
        issue_id=ReworkIssueId(value="rework-issue.probe-response-shape"),
        blocker_refs=(BLOCKER,),
        issue_code=ReworkIssueCode.PROBE_RESPONSE_SHAPE_MISMATCH,
        severity=ReworkIssueSeverity.BLOCKING,
        acceptance_refs=(ACCEPTANCE,),
        source_surface_refs=(SURFACE,),
        run_manifest_refs=("run-manifest.v2-090f",),
        evidence_obligation_refs=(OBLIGATION,),
        suspected_domains=(ReworkSuspectedDomain.IMPLEMENTATION, ReworkSuspectedDomain.PROBE),
        required_artifact_types=(RequiredArtifactType(value="live_blackbox_integration"),),
        description="Probe expects $.title but backend returns $.book.title.",
    )


def _request() -> ReworkRequest:
    return ReworkRequest(
        rework_request_id=REQUEST_ID,
        cycle_id=CYCLE,
        run_id=RunId(value="run.v2-100b"),
        request_source_refs=("blocker-report.final-evidence",),
        issues=(_issue(),),
        requested_by_actor=ReworkActorKind.CHECKER,
        requested_at=NOW,
        active_contract_refs=(ContractId(value="acceptance.v2-090f"), ContractId(value="package.v2-090f")),
        active_graph_version=40,
    )


def _patch() -> TicketGraphPatch:
    operation = TicketGraphPatchOperation(
        operation_id=TicketGraphPatchOperationId(value="op.create-rework-ticket"),
        operation_kind=GraphPatchOperationKind.CREATE_REWORK_TICKET,
        target_ticket_refs=(REWORK_TICKET,),
        acceptance_refs=(ACCEPTANCE,),
        source_surface_refs=(SURFACE,),
        evidence_obligation_refs=(OBLIGATION,),
        rationale="Create bounded rework ticket for API response shape.",
    )
    return TicketGraphPatch(
        ticket_graph_patch_id=PATCH_ID,
        base_graph_version=40,
        proposed_by_plan_ref=PLAN_ID,
        operations=(operation,),
        affected_ticket_refs=(REWORK_TICKET,),
        affected_contract_refs=(ContractId(value="acceptance.v2-090f"),),
        affected_source_surface_refs=(SURFACE,),
        required_review_domains=(
            GraphPatchReviewDomain.PLANNING,
            GraphPatchReviewDomain.STRUCTURAL,
            GraphPatchReviewDomain.BLOCKER_COVERAGE,
            GraphPatchReviewDomain.BEHAVIORAL_PROBE,
        ),
        patch_hash="sha256:ticket-graph-patch.v2-100b",
    )
```

- [ ] **Step 3: Add plan, reviews, ticket, attempt and outcome builders**

Add:

```python
def _plan() -> ReworkPlan:
    decision = ReworkDecision(
        decision_id=ReworkDecisionId(value="decision.fix-api-shape"),
        decision_kind=ReworkDecisionKind.FIX_IMPLEMENTATION,
        blocker_refs=(BLOCKER,),
        issue_ids=(_issue().issue_id,),
        target_ticket_refs=(REWORK_TICKET,),
        target_graph_operation_refs=(_patch().operations[0].operation_id,),
        rationale="Fix backend implementation to satisfy active probe.",
    )
    return ReworkPlan(
        rework_plan_id=PLAN_ID,
        cycle_id=CYCLE,
        rework_request_id=REQUEST_ID,
        planner_actor=ReworkActorKind.CEO,
        planner_attempt_ref=ProviderAttemptRef(value="provider-attempt.ceo.rework-plan"),
        decisions=(decision,),
        ticket_graph_patch_ref=PATCH_ID,
        risk_notes=("Do not change acceptance refs without contract revision.",),
        stop_or_escalation_conditions=("Escalate after two identical blocker rounds.",),
    )


def _review(domain: GraphPatchReviewDomain, role: ReworkActorKind) -> GraphPatchReview:
    return GraphPatchReview(
        graph_patch_review_id=GraphPatchReviewId(value=f"graph-patch-review.{domain.value}"),
        ticket_graph_patch_ref=PATCH_ID,
        review_domain=domain,
        reviewer_actor=role,
        reviewer_role_kind=role,
        reviewer_attempt_ref=ProviderAttemptRef(value=f"provider-attempt.{role.value}.{domain.value}"),
        status=GraphPatchReviewStatus.APPROVED,
        checked_invariants=(f"{domain.value} invariant checked.",),
        blockers=(),
        non_blocking_notes=(),
        created_at=NOW,
    )


def _approval_set() -> GraphPatchApprovalSet:
    return GraphPatchApprovalSet(
        approval_set_id=GraphPatchApprovalSetId(value="graph-patch-approval.v2-100b"),
        ticket_graph_patch_ref=PATCH_ID,
        required_domains=_patch().required_review_domains,
        reviews=(
            _review(GraphPatchReviewDomain.PLANNING, ReworkActorKind.CEO),
            _review(GraphPatchReviewDomain.STRUCTURAL, ReworkActorKind.ARCHITECT),
            _review(GraphPatchReviewDomain.BLOCKER_COVERAGE, ReworkActorKind.CHECKER),
            _review(GraphPatchReviewDomain.BEHAVIORAL_PROBE, ReworkActorKind.TESTER),
        ),
        status=GraphPatchApprovalStatus.READY_TO_COMMIT,
        computed_at=NOW,
    )


def _ticket_payload() -> TicketCreatedPayload:
    return TicketCreatedPayload(
        ticket_id=REWORK_TICKET,
        purpose="Fix backend API response shape",
        seat_demand=SeatDemand(
            required_role_category=RoleCategory.IMPLEMENTATION,
            required_capability_tags=(
                CapabilityTag(value="task.implementation"),
                CapabilityTag(value="surface.backend"),
            ),
        ),
        depends_on=(),
        acceptance_refs=(ACCEPTANCE.value,),
        source_surface_refs=(SURFACE.value,),
        evidence_obligations=(OBLIGATION.value,),
        allowed_read_refs=("contract:acceptance.v2-090f",),
        allowed_write_set=("10-project/backend/**",),
        attempt_count=0,
    )


def _attempt() -> ReworkAttempt:
    return ReworkAttempt(
        rework_attempt_id=ATTEMPT_ID,
        cycle_id=CYCLE,
        rework_plan_ref=PLAN_ID,
        ticket_ref=REWORK_TICKET,
        execution_package_ref=ExecutionPackageRef(value="execution-package.rework.backend-api-shape"),
        actor_ref="seat-worker-backend",
        provider_attempt_refs=(ProviderAttemptRef(value="provider-attempt.worker.rework"),),
        workspace_mutation_refs=("workspace-mutation.backend.server-py",),
        command_evidence_refs=("verification-run.backend-tests.rework",),
        source_lineage_refs=("source-lineage.backend.server-py.rework",),
        run_manifest_ref="run-manifest.v2-090f",
        submitted_at=NOW,
    )


def _accepted_outcome() -> ReworkOutcome:
    return ReworkOutcome(
        rework_outcome_id=OUTCOME_ID,
        rework_attempt_ref=ATTEMPT_ID,
        final_evidence_table_ref="final-evidence-table.rework.1",
        source_inventory_ref="source-inventory.rework.1",
        checker_verdict_ref="checker-verdict.rework.1",
        closeout_gate_ref=None,
        status=ReworkOutcomeStatus.ACCEPTED,
        remaining_blocker_refs=(),
        accepted_blocker_refs=(BLOCKER,),
        created_at=NOW,
    )
```

- [ ] **Step 4: Add resolver and event helpers**

Add:

```python
class InMemoryReworkResolver(ReworkReducerPayloadResolver):
    def __init__(self) -> None:
        self.request_payloads = {"payload:request": ReworkRequestPayload(request=_request())}
        self.plan_payloads = {"payload:plan": ReworkPlanPayload(request_ref=REQUEST_ID, plan=_plan(), patch=_patch())}
        self.approval_payloads = {
            "payload:approval": GraphPatchApprovalPayload(patch_ref=PATCH_ID, approval_set=_approval_set())
        }
        self.ticket_payloads = {"payload:ticket": _ticket_payload()}
        self.attempt_payloads = {"payload:attempt": ReworkAttemptPayload(attempt=_attempt())}
        self.review_payloads = {"payload:review": ReworkReviewPayload(outcome=_accepted_outcome())}
        self.terminal_payloads = {
            "payload:accepted": ReworkTerminalPayload(
                cycle_id=CYCLE,
                outcome_ref=OUTCOME_ID,
                termination_decision_ref=None,
                accepted_blocker_refs=(BLOCKER,),
                remaining_blocker_refs=(),
            )
        }

    def resolve_rework_request(self, payload_ref: EventPayloadRef) -> ReworkRequestPayload:
        return self.request_payloads[payload_ref.value]

    def resolve_rework_plan(self, payload_ref: EventPayloadRef) -> ReworkPlanPayload:
        return self.plan_payloads[payload_ref.value]

    def resolve_graph_patch_review(self, payload_ref: EventPayloadRef):
        raise AssertionError("review events are not used by this happy path")

    def resolve_graph_patch_approval(self, payload_ref: EventPayloadRef) -> GraphPatchApprovalPayload:
        return self.approval_payloads[payload_ref.value]

    def resolve_rework_ticket_created(self, payload_ref: EventPayloadRef) -> TicketCreatedPayload:
        return self.ticket_payloads[payload_ref.value]

    def resolve_rework_attempt(self, payload_ref: EventPayloadRef) -> ReworkAttemptPayload:
        return self.attempt_payloads[payload_ref.value]

    def resolve_rework_review(self, payload_ref: EventPayloadRef) -> ReworkReviewPayload:
        return self.review_payloads[payload_ref.value]

    def resolve_rework_terminal(self, payload_ref: EventPayloadRef) -> ReworkTerminalPayload:
        return self.terminal_payloads[payload_ref.value]


def _event(event_type: EventType, graph_version: int, actor_ref: str, payload_ref: str) -> EventRecord:
    return EventRecord(
        event_id=EventId(value=f"evt:{event_type.value}:{graph_version}"),
        event_type=event_type,
        project_ref=PROJECT,
        actor_ref=ActorRef(value=actor_ref),
        timestamp=NOW,
        graph_version=graph_version,
        payload_refs=(EventPayloadRef(value=payload_ref),),
    )
```

- [ ] **Step 5: Add happy path projection test**

Add:

```python
def test_rework_reducer_projects_full_governed_rework_cycle() -> None:
    projection = ReworkReducer(InMemoryReworkResolver()).reduce(
        (
            _event(EventType.REWORK_REQUESTED, 41, "seat-checker", "payload:request"),
            _event(EventType.REWORK_PLANNED, 42, "seat-ceo", "payload:plan"),
            _event(EventType.REWORK_GRAPH_PATCH_APPROVED, 43, "governance:graph-patch-review-gate", "payload:approval"),
            _event(EventType.REWORK_TICKET_CREATED, 44, "governance:command-handler", "payload:ticket"),
            _event(EventType.REWORK_ATTEMPT_STARTED, 45, "runtime:executor", "payload:attempt"),
            _event(EventType.REWORK_ATTEMPT_SUBMITTED, 46, "runtime:executor", "payload:attempt"),
            _event(EventType.REWORK_REVIEWED, 47, "seat-checker", "payload:review"),
            _event(EventType.REWORK_ACCEPTED, 48, "governance:command-handler", "payload:accepted"),
        )
    )

    assert projection.project_ref == PROJECT
    assert projection.graph_version == 48
    assert projection.cycle_id == CYCLE
    assert projection.status is ReworkCycleStatus.ACCEPTED
    assert projection.terminal_status is ReworkTerminalStatus.ACCEPTED
    assert projection.request_ref == REQUEST_ID
    assert projection.plan_ref == PLAN_ID
    assert projection.patch_ref == PATCH_ID
    assert projection.rework_ticket_refs == (REWORK_TICKET,)
    assert projection.attempt_refs == (ATTEMPT_ID,)
    assert projection.outcome_refs == (OUTCOME_ID,)
    assert projection.accepted_blocker_refs == (BLOCKER,)
    assert projection.remaining_blocker_refs == ()
```

- [ ] **Step 6: Add replay determinism test**

Add:

```python
def test_rework_reducer_replay_is_deterministic() -> None:
    events = (
        _event(EventType.REWORK_REQUESTED, 41, "seat-checker", "payload:request"),
        _event(EventType.REWORK_PLANNED, 42, "seat-ceo", "payload:plan"),
        _event(EventType.REWORK_GRAPH_PATCH_APPROVED, 43, "governance:graph-patch-review-gate", "payload:approval"),
        _event(EventType.REWORK_TICKET_CREATED, 44, "governance:command-handler", "payload:ticket"),
        _event(EventType.REWORK_ATTEMPT_SUBMITTED, 45, "runtime:executor", "payload:attempt"),
        _event(EventType.REWORK_REVIEWED, 46, "seat-checker", "payload:review"),
        _event(EventType.REWORK_ACCEPTED, 47, "governance:command-handler", "payload:accepted"),
    )

    first = ReworkReducer(InMemoryReworkResolver()).reduce(events)
    replayed_events = tuple(EventRecord(**event.stable_dump()) for event in events)
    second = ReworkReducer(InMemoryReworkResolver()).reduce(replayed_events)

    assert first == second
    assert first.checked_refs == second.checked_refs
```

- [ ] **Step 7: Run happy path tests and verify they fail before implementation is complete**

Run:

```bash
PYTHONPATH=src python -m pytest tests/reducers/test_rework_reducer.py -q
```

Expected: FAIL if Task 4 is not complete; PASS after Task 4 implementation is complete.

- [ ] **Step 8: Run happy and negative rework reducer tests**

Run:

```bash
PYTHONPATH=src python -m pytest \
  tests/reducers/test_rework_reducer.py \
  tests/negative/test_rework_reducer_fail_closed.py \
  -q
```

Expected: PASS.

- [ ] **Step 9: Commit Task 5**

```bash
git add src/boardroom_os/reducers/rework.py tests/reducers/test_rework_reducer.py tests/negative/test_rework_reducer_fail_closed.py
git commit -m "feat(rework): 投影返工治理循环"
```

---

### Task 6: Integrate Rework Ticket Creation With TicketGraph Projection

**Files:**
- Modify `src/boardroom_os/reducers/rework.py`
- Modify `tests/reducers/test_rework_reducer.py`
- Optional Modify `src/boardroom_os/reducers/ticket_reducer.py` only if a narrow integration point is necessary

- [ ] **Step 1: Add graph patch operation coverage test**

Append to `tests/reducers/test_rework_reducer.py`:

```python
def test_rework_ticket_creation_projection_remains_patch_bound() -> None:
    projection = ReworkReducer(InMemoryReworkResolver()).reduce(
        (
            _event(EventType.REWORK_REQUESTED, 41, "seat-checker", "payload:request"),
            _event(EventType.REWORK_PLANNED, 42, "seat-ceo", "payload:plan"),
            _event(EventType.REWORK_GRAPH_PATCH_APPROVED, 43, "governance:graph-patch-review-gate", "payload:approval"),
            _event(EventType.REWORK_TICKET_CREATED, 44, "governance:command-handler", "payload:ticket"),
        )
    )

    assert projection.status is ReworkCycleStatus.EXECUTING
    assert projection.rework_ticket_refs == (REWORK_TICKET,)
    assert REWORK_TICKET.value in projection.checked_refs
```

- [ ] **Step 2: Run targeted projection test**

Run:

```bash
PYTHONPATH=src python -m pytest tests/reducers/test_rework_reducer.py::test_rework_ticket_creation_projection_remains_patch_bound -q
```

Expected: PASS after Task 4; if it fails because ticket binding is incomplete, fix `_validate_rework_ticket_payload`.

- [ ] **Step 3: Keep TicketReducer integration explicit**

If V2-100B requires TicketGraph（工单图） mutation in the same reducer pass, do not silently reuse `TICKET_CREATED`. Instead add an explicit adapter function in `rework.py`:

```python
def rework_ticket_payload_to_ticket_created_payload(
    payload: TicketCreatedPayload,
    *,
    patch: TicketGraphPatch,
) -> TicketCreatedPayload:
    ReworkReducer._validate_rework_ticket_payload(payload, patch)
    return payload
```

This keeps TicketReducer（工单归约器） as the only TicketGraph（工单图） projection source while ensuring V2-100B validates the rework patch boundary before any `TicketCreatedPayload`（工单创建载荷） is appended as a graph mutation event.

- [ ] **Step 4: Add adapter test if adapter is added**

Append:

```python
def test_rework_ticket_payload_adapter_returns_valid_ticket_created_payload() -> None:
    from boardroom_os.reducers.rework import rework_ticket_payload_to_ticket_created_payload

    payload = rework_ticket_payload_to_ticket_created_payload(_ticket_payload(), patch=_patch())

    assert payload.ticket_id == REWORK_TICKET
```

Run:

```bash
PYTHONPATH=src python -m pytest tests/reducers/test_rework_reducer.py::test_rework_ticket_payload_adapter_returns_valid_ticket_created_payload -q
```

Expected: PASS if adapter exists. If no adapter is needed, skip this step and document in the commit message that V2-100B keeps graph mutation validation inside ReworkReducer（返工归约器） only.

- [ ] **Step 5: Commit Task 6**

```bash
git add src/boardroom_os/reducers/rework.py tests/reducers/test_rework_reducer.py
git commit -m "feat(rework): 绑定返工工单图补丁"
```

---

### Task 7: Public API Exports And Regression Verification

**Files:**
- Modify `src/boardroom_os/rework/__init__.py` if exporting `GraphPatchReviewGate` from rework package is desired
- Create or modify `tests/rework/test_rework_model.py` only for API export coverage

- [ ] **Step 1: Add API export test**

Append to `tests/rework/test_rework_model.py`:

```python
def test_rework_package_exports_v2_100b_reducer_api() -> None:
    from boardroom_os.reducers import rework as rework_reducer

    for name in (
        "GraphPatchReviewGate",
        "ReworkProjection",
        "ReworkReducer",
        "ReworkReducerError",
        "ReworkTerminalStatus",
    ):
        assert hasattr(rework_reducer, name)
```

- [ ] **Step 2: Run export test**

Run:

```bash
PYTHONPATH=src python -m pytest tests/rework/test_rework_model.py::test_rework_package_exports_v2_100b_reducer_api -q
```

Expected: PASS.

- [ ] **Step 3: Run V2-100A/B focused tests**

Run:

```bash
PYTHONPATH=src python -m pytest \
  tests/negative/test_rework_model_fail_closed.py \
  tests/rework/test_rework_model.py \
  tests/rework/test_v2_090k_failure_snapshot_projection.py \
  tests/negative/test_rework_reducer_fail_closed.py \
  tests/reducers/test_rework_reducer.py \
  tests/reducers/test_event_record.py \
  tests/execution/test_runtime_executor_boundary.py \
  -q
```

Expected: PASS.

- [ ] **Step 4: Run reducer and execution regression tests**

Run:

```bash
PYTHONPATH=src python -m pytest \
  tests/reducers \
  tests/execution/test_runtime_executor_boundary.py \
  tests/closeout/test_closeout_reducer.py \
  -q
```

Expected: PASS.

- [ ] **Step 5: Commit Task 7**

```bash
git add src/boardroom_os/reducers/rework.py tests/rework/test_rework_model.py
git commit -m "test(rework): 覆盖返工归约器导出"
```

---

### Task 8: Work Package Completion Updates

**Files:**
- Modify `doc/04-implementation/backlog.md`
- Modify `doc/04-implementation/acceptance-criteria.md`
- Modify `doc/05-project-log/2026-06.md`
- Modify `doc/04-implementation/INDEX.md` only if it was not already updated by plan drafting

- [ ] **Step 1: Run final verification before documentation closeout**

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

Expected: PASS. Report the exact pass count from pytest output.

- [ ] **Step 2: Update backlog**

In `doc/04-implementation/backlog.md`:

- Change `V2-100B` status from `TODO` to `DONE`.
- Change top TL;DR current incomplete package from `V2-100B` to `V2-100C`.
- Change Phase 10 progress from `1 / 5` to `2 / 5`.
- Add completion evidence under `V2-100B`:

```markdown
- 完成证据：2026-06-14 已实现 `REWORK_REQUESTED` / `REWORK_PLANNED` / `REWORK_GRAPH_PATCH_REVIEWED` / `REWORK_GRAPH_PATCH_APPROVED` / `REWORK_TICKET_CREATED` / `REWORK_ATTEMPT_STARTED` / `REWORK_ATTEMPT_SUBMITTED` / `REWORK_REVIEWED` / `REWORK_ACCEPTED` / `REWORK_ESCALATED` / `REWORK_EXHAUSTED` 返工事件分类与 ReworkReducer（返工归约器）；runtime/executor/atomic-agent（运行时/执行器/原子智能体）不能提交治理终态；GraphPatchReviewGate（图补丁审查门禁）要求 planning/structural/blocker_coverage 等必需审查域 ready_to_commit；返工工单创建受 TicketGraphPatch（工单图补丁）、active acceptance refs（活跃验收引用）、source surfaces（源码面）、evidence obligations（证据义务）和 allowed_write_set（允许写集合）约束。验证：`PYTHONPATH=src:. python -m pytest ... -q` 通过（填入实际 pass count）。
```

- [ ] **Step 3: Update acceptance checkbox**

In `doc/04-implementation/acceptance-criteria.md`, change the V2-100B checkbox:

```markdown
- [x] AC-V2-REWORK-001 / AC-V2-GRAPH-001 / AC-V2-GRAPH-002（返工状态由 TicketGraph 和 reducer 推进）— 由 V2-100B 证明：...
```

Do not check V2-100C/D/E or Phase 10 final prerequisites.

- [ ] **Step 4: Update project log**

Append or update the 2026-06-14 V2-100B entry in `doc/05-project-log/2026-06.md`:

```markdown
### 2026-06-14 — V2-100B Rework event taxonomy + reducer（返工事件分类与归约器）

- 产出：`src/boardroom_os/reducers/rework.py`、`src/boardroom_os/events/types.py`、`tests/reducers/test_rework_reducer.py`、`tests/negative/test_rework_reducer_fail_closed.py`、`tests/execution/test_runtime_executor_boundary.py`。
- 负例：runtime/executor/atomic-agent 直接提交 `REWORK_ACCEPTED` / `REWORK_ESCALATED` / `REWORK_EXHAUSTED` 失败；无 `REWORK_REQUESTED` 直接 `REWORK_PLANNED` 失败；GraphPatchReviewGate 缺必需审查域或存在 rejected review 失败；返工工单扩大 allowed_write_set 或引用 patch 外 acceptance/source/evidence 失败。
- 正例：`REWORK_REQUESTED -> REWORK_PLANNED -> REWORK_GRAPH_PATCH_APPROVED -> REWORK_TICKET_CREATED -> REWORK_ATTEMPT_SUBMITTED -> REWORK_REVIEWED -> REWORK_ACCEPTED` 可回放为 ReworkProjection（返工投影），并保留 checked_refs（已检查引用）和 committed_event_refs（已提交事件引用）。
- 验证：`PYTHONPATH=src:. python -m pytest ... -q` 通过（填入实际 pass count）。
```

- [ ] **Step 5: Commit completion docs**

```bash
git add doc/04-implementation/backlog.md doc/04-implementation/acceptance-criteria.md doc/05-project-log/2026-06.md
git commit -m "docs(rework): 完成返工归约器工作包"
```

---

## Self-Review Checklist

Run this checklist after implementation and before marking V2-100B DONE:

1. Spec coverage（规格覆盖）:
   - `REWORK_*` event taxonomy（事件分类） exists.
   - Runtime boundary（运行时边界） blocks governance events（治理事件）.
   - ReworkReducer（返工归约器） enforces event order and actor permissions（执行者权限）.
   - GraphPatchReviewGate（图补丁审查门禁） enforces required domains.
   - Rework ticket creation（返工工单创建） is patch-bound and cannot expand allowed_write_set（允许写集合） broadly.
   - Rework accepted/escalated/exhausted（接受/升级/耗尽） requires explicit reviewed outcome or termination decision（终止决策）.

2. Placeholder scan（占位扫描）:
   - Search the new files for `TODO`, `TBD`, `pass`, `NotImplemented`, `placeholder`, and remove anything that affects production behavior.

3. Type consistency（类型一致性）:
   - EventType values match test names and reducer branches.
   - Payload model fields match resolver method names.
   - ReworkProjection（返工投影） status values come from ReworkCycleStatus（返工循环状态） and ReworkTerminalStatus（返工终态状态） consistently.

4. Boundary check（边界检查）:
   - Runtime/executor/atomic-agent（运行时/执行器/原子智能体） may emit only `REWORK_ATTEMPT_STARTED` / `REWORK_ATTEMPT_SUBMITTED`.
   - CEO（项目经理） may propose but cannot directly mutate graph without GraphPatchReviewGate（图补丁审查门禁）.
   - TicketGraph（工单图） remains the state source; no second graph state store is introduced.

5. Completion protocol（完成协议）:
   - Only after tests pass, update backlog（任务清单）, acceptance checkbox（验收复选框）, monthly log（月度日志）, and INDEX（索引） if a new doc was added.
