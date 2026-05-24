# V2-070F CloseoutReducer（收尾归约器）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现 `CLOSEOUT_COMMITTED`（收尾已提交）治理事件与 `CloseoutReducer`（收尾归约器），让 passed `CloseoutPackage`（通过的收尾包）在显式 `WORK_PRODUCT_SUBMITTED`（工作产物已提交）历史存在时投影为 project terminal success（项目终态成功）。

**Architecture:** 新增 `EventType.CLOSEOUT_COMMITTED`（收尾已提交事件）作为 governance event（治理事件），并保持 `RuntimeEventBoundary`（运行时事件边界）拒绝 runtime emit（运行时发出）。新增 `src/boardroom_os/reducers/closeout_reducer.py`，通过 resolver（解析器）解析 `CloseoutCommitPayload`（收尾提交载荷）与 typed `CloseoutPackage`（类型化收尾包），校验事件顺序、actor boundary（参与者边界）、payload/package refs（载荷/包引用）与历史 work product facts（工作产物事实）后产出 `CloseoutProjection`（收尾投影）。

**Tech Stack:** Python 3、Pydantic（Pydantic 模型）、pytest（测试框架）、现有 `EventRecord`（事件记录）、`EventType`（事件类型）、`CloseoutPackage`（收尾包）、`RuntimeEventBoundary`（运行时事件边界）。

---

## 0. 文件结构与职责

**创建：**

- `src/boardroom_os/reducers/closeout_reducer.py`
  - 定义 `CloseoutReducerError`（收尾归约器错误）。
  - 定义 `CloseoutCommitPayload`（收尾提交载荷）。
  - 定义 `CloseoutHistoryProjection`（收尾历史投影）。
  - 定义 `CloseoutProjection`（收尾投影）。
  - 定义 `CloseoutReducerPayloadResolver`（收尾归约器载荷解析器）。
  - 定义 `CloseoutReducer.reduce(...)`（收尾归约函数）。

- `tests/closeout/test_closeout_reducer.py`
  - 覆盖 spec（规格）的负例与正例。
  - 复用 `tests.closeout.test_closeout_package._build_package` helper（辅助函数）构造 passed `CloseoutPackage`（通过的收尾包）。

**修改：**

- `src/boardroom_os/events/types.py`
  - 新增 `EventType.CLOSEOUT_COMMITTED = "closeout_committed"`。

- `src/boardroom_os/execution/runtime_executor.py`
  - 将 `RuntimeEventBoundary._REJECTED_GOVERNANCE_EVENT_VALUES`（运行时拒绝治理事件集合）中的 closeout 拒绝项从字符串枚举改为正式 `EventType.CLOSEOUT_COMMITTED.value`。
  - 保留 `ReservedRuntimeGovernanceEvent.PROJECT_COMPLETED`（保留运行时治理事件：项目完成）作为被拒绝字符串，不把 `PROJECT_COMPLETED` 加入正式 EventType（事件类型）。

- `doc/04-implementation/INDEX.md`
  - 加入本 implementation plan（实施计划）文档条目。

**完成后修改（只在全部测试通过后执行）：**

- `doc/04-implementation/backlog.md`
  - V2-070F 状态改为 DONE。
  - 顶部当前未完成工作包改为 V2-080A。
  - Phase 7 进度改为 6 / 6；合计改为 47 / 53；Phase 8 保持 0 / 6。

- `doc/04-implementation/acceptance-criteria.md`
  - 勾选 Phase 7 的 `Closeout reducer 接入`。
  - 勾选 `V2-070A ~ V2-070F 六个工作包全部 DONE`。
  - 勾选 `backlog.md 进度总览 Phase 7 显示 6/6`。
  - 勾选 Phase 7 的进入 Phase 8 前置三项。

- `doc/05-project-log/2026-05.md`
  - 追加 V2-070F 完成记录，包含产出文件、负例/正例测试和真实验证命令。

---

## Task 1: 扩展事件类型并写 runtime boundary（运行时边界）负例

**Files:**
- Modify: `src/boardroom_os/events/types.py`
- Modify: `src/boardroom_os/execution/runtime_executor.py`
- Test: `tests/closeout/test_closeout_reducer.py`

- [ ] **Step 1: 写入最小失败测试文件，证明 `CLOSEOUT_COMMITTED` 还不存在**

Create `tests/closeout/test_closeout_reducer.py` with this content:

```python
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from boardroom_os.closeout.package import CloseoutPackage, CloseoutPackageRef
from boardroom_os.events.record import EventRecord
from boardroom_os.events.types import ActorRef, EventId, EventPayloadRef, EventRef, EventType, ProjectRef
from boardroom_os.execution.runtime_executor import RuntimeEventBoundary, RuntimeExecutorError

_PROJECT_REF = ProjectRef(value="project.closeout-reducer")
_NOW = datetime(2026, 5, 25, 10, 0, tzinfo=UTC)


def _event(
    *,
    event_id: str,
    event_type: EventType,
    payload_ref: str,
    graph_version: int,
    actor_ref: str = "seat-closeout",
    project_ref: ProjectRef = _PROJECT_REF,
) -> EventRecord:
    return EventRecord(
        event_id=EventId(value=event_id),
        event_type=event_type,
        project_ref=project_ref,
        actor_ref=ActorRef(value=actor_ref),
        timestamp=_NOW,
        graph_version=graph_version,
        payload_refs=(EventPayloadRef(value=payload_ref),),
    )


def test_closeout_committed_event_is_accepted_by_event_record_but_not_runtime_boundary() -> None:
    event = _event(
        event_id="evt.closeout.committed",
        event_type=EventType.CLOSEOUT_COMMITTED,
        payload_ref="payload.closeout.commit",
        graph_version=10,
    )

    assert event.event_type is EventType.CLOSEOUT_COMMITTED
    with pytest.raises(RuntimeExecutorError, match="runtime cannot emit governance event"):
        RuntimeEventBoundary.require_runtime_fact_event(EventType.CLOSEOUT_COMMITTED)
```

- [ ] **Step 2: 运行测试确认 RED（失败）**

Run:

```bash
PYTHONPATH="src;." python -m pytest tests/closeout/test_closeout_reducer.py::test_closeout_committed_event_is_accepted_by_event_record_but_not_runtime_boundary -q
```

Expected: FAIL with `AttributeError: CLOSEOUT_COMMITTED` or equivalent enum missing error.

- [ ] **Step 3: 新增 EventType（事件类型）枚举值**

Modify `src/boardroom_os/events/types.py`. Add this line after `COMMAND_RUN_RECORDED`:

```python
    CLOSEOUT_COMMITTED = "closeout_committed"
```

The bottom of `EventType` should look like:

```python
class EventType(StrEnum):
    TICKET_CREATED = "ticket_created"
    TICKET_LEASED = "ticket_leased"
    TICKET_BLOCKED = "ticket_blocked"
    TICKET_CHECKED = "ticket_checked"
    TICKET_COMPLETED = "ticket_completed"
    TICKET_REWORKED = "ticket_reworked"
    BOOTSTRAP_GOVERNANCE_AUTHORITY = "bootstrap_governance_authority"
    ROLE_PROFILE_REGISTERED = "role_profile_registered"
    ROLE_PROFILE_REPLACED = "role_profile_replaced"
    ROLE_PROFILE_SUPERSEDED = "role_profile_superseded"
    SEAT_CREATED = "seat_created"
    SEAT_ACTIVATED = "seat_activated"
    SEAT_DEACTIVATED = "seat_deactivated"
    SEAT_REPLACED = "seat_replaced"
    SEAT_SUPERSEDED = "seat_superseded"
    SEAT_ASSIGNED = "seat_assigned"
    EXECUTION_STARTED = "execution_started"
    PROVIDER_ATTEMPT_RECORDED = "provider_attempt_recorded"
    TOOL_ATTEMPT_RECORDED = "tool_attempt_recorded"
    WORK_PRODUCT_SUBMITTED = "work_product_submitted"
    COMMAND_RUN_RECORDED = "command_run_recorded"
    CLOSEOUT_COMMITTED = "closeout_committed"
```

- [ ] **Step 4: 更新 runtime boundary（运行时边界）拒绝正式 closeout 事件**

Modify `src/boardroom_os/execution/runtime_executor.py` so `_REJECTED_GOVERNANCE_EVENT_VALUES` uses the formal enum value:

```python
    _REJECTED_GOVERNANCE_EVENT_VALUES = {
        EventType.TICKET_COMPLETED.value,
        EventType.CLOSEOUT_COMMITTED.value,
        ReservedRuntimeGovernanceEvent.PROJECT_COMPLETED.value,
    }
```

Keep `ReservedRuntimeGovernanceEvent.CLOSEOUT_COMMITTED` class member if you want minimal churn, but do not reference it in `_REJECTED_GOVERNANCE_EVENT_VALUES`. If removing it causes no style issues, remove this member:

```python
    CLOSEOUT_COMMITTED = "closeout_committed"
```

- [ ] **Step 5: 运行测试确认 GREEN（通过）**

Run:

```bash
PYTHONPATH="src;." python -m pytest tests/closeout/test_closeout_reducer.py::test_closeout_committed_event_is_accepted_by_event_record_but_not_runtime_boundary -q
```

Expected: PASS (`1 passed`).

- [ ] **Step 6: 回归 runtime governance（运行时治理边界）负例**

Run:

```bash
PYTHONPATH="src;." python -m pytest tests/negative/test_runtime_cannot_govern.py -q
```

Expected: PASS; existing assertions about `closeout_committed` string remain protected.

---

## Task 2: 建立 closeout reducer（收尾归约器）模型与 open projection（开放投影）

**Files:**
- Create: `src/boardroom_os/reducers/closeout_reducer.py`
- Modify: `tests/closeout/test_closeout_reducer.py`

- [ ] **Step 1: 追加测试 helpers（辅助函数）和无 closeout 事件的 open projection 测试**

Append to `tests/closeout/test_closeout_reducer.py`:

```python
from pydantic import ValidationError

from boardroom_os.execution.work_product import WorkProductRef
from boardroom_os.graph.ticket import TicketId
from boardroom_os.reducers.closeout_reducer import (
    CloseoutCommitPayload,
    CloseoutHistoryProjection,
    CloseoutProjection,
    CloseoutReducer,
    CloseoutReducerError,
    CloseoutCommitVerdict,
    CloseoutReducerPayloadResolver,
    CloseoutTerminalStatus,
)
from boardroom_os.workspace.source_inventory import PackageCommitRef
from tests.closeout.test_closeout_package import _build_package


def _passed_package() -> CloseoutPackage:
    return _build_package()


class InMemoryCloseoutPayloadResolver(CloseoutReducerPayloadResolver):
    def __init__(
        self,
        *,
        commit_payloads: dict[str, CloseoutCommitPayload] | None = None,
        packages: dict[str, CloseoutPackage] | None = None,
    ) -> None:
        self._commit_payloads = commit_payloads or {}
        self._packages = packages or {}

    def resolve_closeout_commit(self, payload_ref: EventPayloadRef) -> CloseoutCommitPayload:
        return self._commit_payloads[payload_ref.value]

    def resolve_closeout_package(self, closeout_package_ref: CloseoutPackageRef) -> CloseoutPackage:
        return self._packages[closeout_package_ref.value]


def _work_product_event(graph_version: int = 9) -> EventRecord:
    return _event(
        event_id=f"evt.work-product.submitted.{graph_version}",
        event_type=EventType.WORK_PRODUCT_SUBMITTED,
        payload_ref=f"work-product.submitted.{graph_version}",
        graph_version=graph_version,
        actor_ref="seat-worker",
    )


def test_closeout_reducer_keeps_projection_open_without_closeout_committed_event() -> None:
    projection = CloseoutReducer(InMemoryCloseoutPayloadResolver()).reduce(
        (_work_product_event(graph_version=9),)
    )

    assert projection.terminal_status is CloseoutTerminalStatus.OPEN
    assert projection.project_ref == _PROJECT_REF
    assert projection.graph_version == 9
    assert projection.closeout_package_ref is None
    assert projection.work_product_history_refs == (EventPayloadRef(value="work-product.submitted.9"),)
```

- [ ] **Step 2: 运行测试确认 RED（失败）**

Run:

```bash
PYTHONPATH="src;." python -m pytest tests/closeout/test_closeout_reducer.py::test_closeout_reducer_keeps_projection_open_without_closeout_committed_event -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'boardroom_os.reducers.closeout_reducer'`.

- [ ] **Step 3: 创建最小 closeout_reducer 模块**

Create `src/boardroom_os/reducers/closeout_reducer.py` with this content:

```python
from __future__ import annotations

from enum import StrEnum
from typing import Any, Protocol, Self

from pydantic import BaseModel, ConfigDict, field_serializer, field_validator, model_validator

from boardroom_os.agents.skills import _normalize_ref_fields
from boardroom_os.closeout.package import (
    CloseoutPackage,
    CloseoutPackageRef,
    CloseoutPackageVerdict,
)
from boardroom_os.contracts.types import NonEmptyTextValue
from boardroom_os.events.record import EventRecord
from boardroom_os.events.types import EventId, EventPayloadRef, EventType, ProjectRef
from boardroom_os.workspace.source_inventory import PackageCommitRef


class CloseoutReducerError(ValueError):
    pass


class CloseoutCommitVerdict(StrEnum):
    PASSED = "passed"


class CloseoutTerminalStatus(StrEnum):
    OPEN = "open"
    SUCCEEDED = "succeeded"


class CloseoutCommitPayload(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    closeout_package_ref: CloseoutPackageRef
    closeout_gate_result_ref: NonEmptyTextValue
    source_inventory_ref: NonEmptyTextValue
    final_evidence_table_ref: NonEmptyTextValue
    replay_bundle_ref: NonEmptyTextValue
    process_audit_bundle_ref: NonEmptyTextValue
    git_version_audit_bundle_ref: NonEmptyTextValue
    package_commit_ref: PackageCommitRef
    terminal_verdict: CloseoutCommitVerdict

    @model_validator(mode="before")
    @classmethod
    def _normalize_refs(cls, data: Any) -> Any:
        return _normalize_ref_fields(
            data,
            {
                "closeout_package_ref": CloseoutPackageRef,
                "closeout_gate_result_ref": NonEmptyTextValue,
                "source_inventory_ref": NonEmptyTextValue,
                "final_evidence_table_ref": NonEmptyTextValue,
                "replay_bundle_ref": NonEmptyTextValue,
                "process_audit_bundle_ref": NonEmptyTextValue,
                "git_version_audit_bundle_ref": NonEmptyTextValue,
                "package_commit_ref": PackageCommitRef,
            },
        )

    @model_validator(mode="after")
    def _require_terminal_passed(self) -> Self:
        if self.terminal_verdict is not CloseoutCommitVerdict.PASSED:
            raise CloseoutReducerError("terminal_verdict must be passed")
        return self

    @field_serializer("terminal_verdict")
    def _serialize_terminal_verdict(self, value: CloseoutCommitVerdict) -> str:
        return value.value


class CloseoutHistoryProjection(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    project_ref: ProjectRef
    graph_version: int
    work_product_submitted_refs: tuple[EventPayloadRef, ...]
    ticket_completed_refs: tuple[EventPayloadRef, ...] = ()
    closeout_package_refs: tuple[CloseoutPackageRef, ...] = ()
    terminal_status: CloseoutTerminalStatus = CloseoutTerminalStatus.OPEN

    @model_validator(mode="before")
    @classmethod
    def _normalize_refs(cls, data: Any) -> Any:
        if isinstance(data, dict):
            for field_name in (
                "work_product_submitted_refs",
                "ticket_completed_refs",
                "closeout_package_refs",
            ):
                if field_name in data and not isinstance(data[field_name], list | tuple):
                    raise CloseoutReducerError(f"{field_name} must be a tuple or list")
        return _normalize_ref_fields(
            data,
            {"project_ref": ProjectRef},
            {
                "work_product_submitted_refs": EventPayloadRef,
                "ticket_completed_refs": EventPayloadRef,
                "closeout_package_refs": CloseoutPackageRef,
            },
        )

    @field_validator("graph_version")
    @classmethod
    def _require_positive_graph_version(cls, value: int) -> int:
        if value <= 0:
            raise CloseoutReducerError("graph_version must be positive")
        return value

    @field_serializer("terminal_status")
    def _serialize_terminal_status(self, value: CloseoutTerminalStatus) -> str:
        return value.value


class CloseoutProjection(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    project_ref: ProjectRef
    graph_version: int
    terminal_status: CloseoutTerminalStatus
    closeout_package_ref: CloseoutPackageRef | None = None
    closeout_gate_result_ref: NonEmptyTextValue | None = None
    package_commit_ref: PackageCommitRef | None = None
    committed_event_ref: EventId | None = None
    work_product_history_refs: tuple[EventPayloadRef, ...]
    checked_refs: tuple[str, ...]

    @field_validator("graph_version")
    @classmethod
    def _require_positive_graph_version(cls, value: int) -> int:
        if value <= 0:
            raise CloseoutReducerError("graph_version must be positive")
        return value

    @field_validator("work_product_history_refs")
    @classmethod
    def _require_unique_work_product_refs(
        cls,
        values: tuple[EventPayloadRef, ...],
    ) -> tuple[EventPayloadRef, ...]:
        ref_values = [value.value for value in values]
        if len(ref_values) != len(set(ref_values)):
            raise CloseoutReducerError("work_product_history_refs must be unique")
        return values

    @field_validator("checked_refs")
    @classmethod
    def _require_unique_checked_refs(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(value.strip() for value in values)
        if any(not value for value in normalized):
            raise CloseoutReducerError("checked_refs must not contain empty values")
        if len(normalized) != len(set(normalized)):
            raise CloseoutReducerError("checked_refs must be unique")
        return normalized

    @model_validator(mode="after")
    def _validate_terminal_shape(self) -> Self:
        if self.terminal_status is CloseoutTerminalStatus.SUCCEEDED:
            if (
                self.closeout_package_ref is None
                or self.closeout_gate_result_ref is None
                or self.package_commit_ref is None
                or self.committed_event_ref is None
                or not self.work_product_history_refs
            ):
                raise CloseoutReducerError("succeeded projection requires closeout refs and work product history")
        return self

    @field_serializer("terminal_status")
    def _serialize_terminal_status(self, value: CloseoutTerminalStatus) -> str:
        return value.value


class CloseoutReducerPayloadResolver(Protocol):
    def resolve_closeout_commit(
        self,
        payload_ref: EventPayloadRef,
    ) -> CloseoutCommitPayload: ...

    def resolve_closeout_package(
        self,
        closeout_package_ref: CloseoutPackageRef,
    ) -> CloseoutPackage: ...


class CloseoutReducer:
    def __init__(self, payload_resolver: CloseoutReducerPayloadResolver) -> None:
        self._payload_resolver = payload_resolver

    def reduce(
        self,
        events: tuple[EventRecord, ...],
        *,
        base_history: CloseoutHistoryProjection | None = None,
    ) -> CloseoutProjection:
        if not events and base_history is None:
            raise CloseoutReducerError("events or base_history must be provided")
        self._validate_base_history(base_history)
        project_ref = base_history.project_ref if base_history is not None else events[0].project_ref
        graph_version = base_history.graph_version if base_history is not None else 0
        work_product_refs = list(base_history.work_product_submitted_refs) if base_history else []
        checked_refs: list[str] = [ref.value for ref in work_product_refs]

        previous_graph_version = graph_version
        for event in events:
            if event.project_ref != project_ref:
                raise CloseoutReducerError("events must belong to one project_ref")
            if event.graph_version <= previous_graph_version:
                raise CloseoutReducerError("events must be strictly increasing by graph_version")
            previous_graph_version = event.graph_version
            graph_version = event.graph_version

            if event.event_type is EventType.WORK_PRODUCT_SUBMITTED:
                self._require_single_payload_ref(event)
                payload_ref = event.payload_refs[0]
                work_product_refs.append(payload_ref)
                checked_refs.append(payload_ref.value)
                continue

            if event.event_type is EventType.CLOSEOUT_COMMITTED:
                # Full closeout validation lands in later tasks.
                continue

        deduped_work_product_refs = tuple(dict.fromkeys(work_product_refs))
        return CloseoutProjection(
            project_ref=project_ref,
            graph_version=graph_version,
            terminal_status=CloseoutTerminalStatus.OPEN,
            work_product_history_refs=deduped_work_product_refs,
            checked_refs=tuple(dict.fromkeys(checked_refs)),
        )

    @staticmethod
    def _require_single_payload_ref(event: EventRecord) -> None:
        if len(event.payload_refs) != 1:
            raise CloseoutReducerError("event must have exactly one payload_ref")

    @staticmethod
    def _validate_base_history(base_history: CloseoutHistoryProjection | None) -> None:
        if base_history is not None and base_history.terminal_status is CloseoutTerminalStatus.SUCCEEDED:
            raise CloseoutReducerError("succeeded base_history cannot be reduced again")


__all__ = [
    "CloseoutCommitVerdict",
    "CloseoutCommitPayload",
    "CloseoutHistoryProjection",
    "CloseoutProjection",
    "CloseoutReducer",
    "CloseoutReducerError",
    "CloseoutReducerPayloadResolver",
    "CloseoutTerminalStatus",
]
```

- [ ] **Step 4: 运行测试确认 GREEN（通过）**

Run:

```bash
PYTHONPATH="src;." python -m pytest tests/closeout/test_closeout_reducer.py::test_closeout_reducer_keeps_projection_open_without_closeout_committed_event -q
```

Expected: PASS.

- [ ] **Step 5: 运行当前文件全部测试**

Run:

```bash
PYTHONPATH="src;." python -m pytest tests/closeout/test_closeout_reducer.py -q
```

Expected: PASS for the two tests currently present.

---

## Task 3: 实现 closeout commit（收尾提交）happy path

**Files:**
- Modify: `src/boardroom_os/reducers/closeout_reducer.py`
- Modify: `tests/closeout/test_closeout_reducer.py`

- [ ] **Step 1: 追加 payload helper（载荷辅助函数）和 terminal success 正例**

Append to `tests/closeout/test_closeout_reducer.py`:

```python

def _commit_payload(package: CloseoutPackage | None = None, **overrides: Any) -> CloseoutCommitPayload:
    resolved_package = package or _passed_package()
    fields: dict[str, Any] = {
        "closeout_package_ref": resolved_package.closeout_package_id,
        "closeout_gate_result_ref": resolved_package.closeout_gate_result_ref,
        "source_inventory_ref": resolved_package.source_inventory_ref,
        "final_evidence_table_ref": resolved_package.final_evidence_table_ref,
        "replay_bundle_ref": resolved_package.replay_bundle_ref,
        "process_audit_bundle_ref": resolved_package.process_audit_bundle_ref,
        "git_version_audit_bundle_ref": resolved_package.git_version_audit_bundle_ref,
        "package_commit_ref": resolved_package.package_commit_ref,
        "terminal_verdict": CloseoutCommitVerdict.PASSED,
    }
    fields.update(overrides)
    return CloseoutCommitPayload(**fields)


def _closeout_event(graph_version: int = 10, actor_ref: str = "seat-closeout") -> EventRecord:
    return _event(
        event_id="evt.closeout.committed",
        event_type=EventType.CLOSEOUT_COMMITTED,
        payload_ref="payload.closeout.commit",
        graph_version=graph_version,
        actor_ref=actor_ref,
    )


def _resolver_for_package(package: CloseoutPackage) -> InMemoryCloseoutPayloadResolver:
    payload = _commit_payload(package)
    return InMemoryCloseoutPayloadResolver(
        commit_payloads={"payload.closeout.commit": payload},
        packages={package.closeout_package_id.value: package},
    )


def test_closeout_reducer_projects_terminal_success_from_passed_closeout_package() -> None:
    package = _passed_package()
    projection = CloseoutReducer(_resolver_for_package(package)).reduce(
        (
            _work_product_event(graph_version=9),
            _closeout_event(graph_version=package.graph_version),
        )
    )

    assert projection.terminal_status is CloseoutTerminalStatus.SUCCEEDED
    assert projection.project_ref == _PROJECT_REF
    assert projection.graph_version == package.graph_version
    assert projection.closeout_package_ref == package.closeout_package_id
    assert projection.closeout_gate_result_ref == package.closeout_gate_result_ref
    assert projection.package_commit_ref == package.package_commit_ref
    assert projection.committed_event_ref == EventId(value="evt.closeout.committed")
    assert projection.work_product_history_refs == (EventPayloadRef(value="work-product.submitted.9"),)
    assert package.closeout_package_id.value in projection.checked_refs
    assert package.closeout_gate_result_ref.value in projection.checked_refs
    assert package.replay_bundle_ref.value in projection.checked_refs
```

- [ ] **Step 2: 运行测试确认 RED（失败）**

Run:

```bash
PYTHONPATH="src;." python -m pytest tests/closeout/test_closeout_reducer.py::test_closeout_reducer_projects_terminal_success_from_passed_closeout_package -q
```

Expected: FAIL because reducer still returns `OPEN` for `CLOSEOUT_COMMITTED`.

- [ ] **Step 3: 实现 closeout commit happy path 归约**

Modify `src/boardroom_os/reducers/closeout_reducer.py`.

Replace this block inside `reduce(...)`:

```python
            if event.event_type is EventType.CLOSEOUT_COMMITTED:
                # Full closeout validation lands in later tasks.
                continue
```

with:

```python
            if event.event_type is EventType.CLOSEOUT_COMMITTED:
                self._require_single_payload_ref(event)
                payload = self._resolve_closeout_commit(event.payload_refs[0])
                package = self._resolve_closeout_package(payload.closeout_package_ref)
                self._validate_closeout_binding(
                    event=event,
                    payload=payload,
                    package=package,
                    work_product_refs=tuple(dict.fromkeys(work_product_refs)),
                )
                checked_refs.extend(_closeout_checked_refs(payload, package))
                deduped_work_product_refs = tuple(dict.fromkeys(work_product_refs))
                return CloseoutProjection(
                    project_ref=project_ref,
                    graph_version=graph_version,
                    terminal_status=CloseoutTerminalStatus.SUCCEEDED,
                    closeout_package_ref=package.closeout_package_id,
                    closeout_gate_result_ref=package.closeout_gate_result_ref,
                    package_commit_ref=package.package_commit_ref,
                    committed_event_ref=event.event_id,
                    work_product_history_refs=deduped_work_product_refs,
                    checked_refs=tuple(dict.fromkeys(checked_refs)),
                )
```

Add these methods to `CloseoutReducer` before `_require_single_payload_ref`:

```python
    def _resolve_closeout_commit(self, payload_ref: EventPayloadRef) -> CloseoutCommitPayload:
        try:
            payload = self._payload_resolver.resolve_closeout_commit(payload_ref)
        except Exception as error:
            raise CloseoutReducerError(
                f"closeout payload_ref could not be resolved: {payload_ref.value}"
            ) from error
        if not isinstance(payload, CloseoutCommitPayload):
            raise CloseoutReducerError("closeout commit payload must be CloseoutCommitPayload")
        return payload

    def _resolve_closeout_package(self, package_ref: CloseoutPackageRef) -> CloseoutPackage:
        try:
            package = self._payload_resolver.resolve_closeout_package(package_ref)
        except Exception as error:
            raise CloseoutReducerError(
                f"closeout package could not be resolved: {package_ref.value}"
            ) from error
        if not isinstance(package, CloseoutPackage):
            raise CloseoutReducerError("closeout package must be CloseoutPackage")
        return package

    def _validate_closeout_binding(
        self,
        *,
        event: EventRecord,
        payload: CloseoutCommitPayload,
        package: CloseoutPackage,
        work_product_refs: tuple[EventPayloadRef, ...],
    ) -> None:
        if package.verdict is not CloseoutPackageVerdict.PASSED:
            raise CloseoutReducerError("closeout package verdict must be passed")
        if package.closeout_package_id != payload.closeout_package_ref:
            raise CloseoutReducerError("closeout package ref mismatch")
        if event.graph_version < package.graph_version:
            raise CloseoutReducerError("closeout commit graph_version must cover package graph_version")
        if not work_product_refs:
            raise CloseoutReducerError("work product history is required before closeout")
        expected_pairs = {
            "closeout_gate_result_ref": package.closeout_gate_result_ref,
            "source_inventory_ref": package.source_inventory_ref,
            "final_evidence_table_ref": package.final_evidence_table_ref,
            "replay_bundle_ref": package.replay_bundle_ref,
            "process_audit_bundle_ref": package.process_audit_bundle_ref,
            "git_version_audit_bundle_ref": package.git_version_audit_bundle_ref,
            "package_commit_ref": package.package_commit_ref,
        }
        for field_name, expected in expected_pairs.items():
            if getattr(payload, field_name) != expected:
                raise CloseoutReducerError(f"{field_name} mismatch")
        package_checked_refs = {ref.value for ref in package.checked_refs}
        required_checked_refs = {
            payload.closeout_gate_result_ref.value,
            payload.source_inventory_ref.value,
            payload.final_evidence_table_ref.value,
            payload.replay_bundle_ref.value,
            payload.process_audit_bundle_ref.value,
            payload.git_version_audit_bundle_ref.value,
            payload.package_commit_ref.value,
        }
        if not required_checked_refs.issubset(package_checked_refs):
            raise CloseoutReducerError("closeout package checked_refs missing payload refs")
```

Add this module-level helper above `__all__`:

```python
def _closeout_checked_refs(
    payload: CloseoutCommitPayload,
    package: CloseoutPackage,
) -> tuple[str, ...]:
    refs = [
        package.closeout_package_id.value,
        payload.closeout_gate_result_ref.value,
        payload.source_inventory_ref.value,
        payload.final_evidence_table_ref.value,
        payload.replay_bundle_ref.value,
        payload.process_audit_bundle_ref.value,
        payload.git_version_audit_bundle_ref.value,
        payload.package_commit_ref.value,
        *(ref.value for ref in package.checked_refs),
    ]
    return tuple(dict.fromkeys(refs))
```

- [ ] **Step 4: 运行正例确认 GREEN（通过）**

Run:

```bash
PYTHONPATH="src;." python -m pytest tests/closeout/test_closeout_reducer.py::test_closeout_reducer_projects_terminal_success_from_passed_closeout_package -q
```

Expected: PASS.

- [ ] **Step 5: 运行当前 closeout reducer 测试文件**

Run:

```bash
PYTHONPATH="src;." python -m pytest tests/closeout/test_closeout_reducer.py -q
```

Expected: PASS for all tests currently present.

---

## Task 4: 增量 base history（基准历史）与 work product 历史 fail-closed

**Files:**
- Modify: `src/boardroom_os/reducers/closeout_reducer.py`
- Modify: `tests/closeout/test_closeout_reducer.py`

- [ ] **Step 1: 追加增量成功与历史缺口负例**

Append to `tests/closeout/test_closeout_reducer.py`:

```python

def _base_history(
    *,
    work_product_refs: tuple[EventPayloadRef, ...] = (EventPayloadRef(value="work-product.submitted.base"),),
    terminal_status: CloseoutTerminalStatus = CloseoutTerminalStatus.OPEN,
    closeout_package_refs: tuple[CloseoutPackageRef, ...] = (),
) -> CloseoutHistoryProjection:
    return CloseoutHistoryProjection(
        project_ref=_PROJECT_REF,
        graph_version=9,
        work_product_submitted_refs=work_product_refs,
        ticket_completed_refs=(EventPayloadRef(value="payload.ticket.completed"),),
        closeout_package_refs=closeout_package_refs,
        terminal_status=terminal_status,
    )


def test_closeout_reducer_supports_incremental_base_history_with_explicit_work_product_refs() -> None:
    package = _passed_package()
    projection = CloseoutReducer(_resolver_for_package(package)).reduce(
        (_closeout_event(graph_version=package.graph_version),),
        base_history=_base_history(),
    )

    assert projection.terminal_status is CloseoutTerminalStatus.SUCCEEDED
    assert projection.work_product_history_refs == (EventPayloadRef(value="work-product.submitted.base"),)
    assert projection.closeout_package_ref == package.closeout_package_id


def test_closeout_reducer_rejects_incremental_closeout_without_work_product_history() -> None:
    package = _passed_package()

    with pytest.raises(CloseoutReducerError, match="work product history"):
        CloseoutReducer(_resolver_for_package(package)).reduce(
            (_closeout_event(graph_version=package.graph_version),),
            base_history=_base_history(work_product_refs=()),
        )


def test_closeout_reducer_rejects_missing_work_product_history_even_if_ticket_completed_exists() -> None:
    package = _passed_package()
    history = CloseoutHistoryProjection(
        project_ref=_PROJECT_REF,
        graph_version=9,
        work_product_submitted_refs=(),
        ticket_completed_refs=(EventPayloadRef(value="payload.ticket.completed"),),
    )

    with pytest.raises(CloseoutReducerError, match="work product history"):
        CloseoutReducer(_resolver_for_package(package)).reduce(
            (_closeout_event(graph_version=package.graph_version),),
            base_history=history,
        )
```

- [ ] **Step 2: 运行新增测试确认预期状态**

Run:

```bash
PYTHONPATH="src;." python -m pytest tests/closeout/test_closeout_reducer.py::test_closeout_reducer_supports_incremental_base_history_with_explicit_work_product_refs tests/closeout/test_closeout_reducer.py::test_closeout_reducer_rejects_incremental_closeout_without_work_product_history tests/closeout/test_closeout_reducer.py::test_closeout_reducer_rejects_missing_work_product_history_even_if_ticket_completed_exists -q
```

Expected: The first test may PASS already after Task 3; both negative tests should PASS if Task 3 implemented `if not work_product_refs` in `_validate_closeout_binding`. If any negative test fails, continue to Step 3.

- [ ] **Step 3: Ensure history validation is explicit**

If negative tests failed, edit `_validate_closeout_binding(...)` in `src/boardroom_os/reducers/closeout_reducer.py` and ensure this exact block is present before ref comparisons:

```python
        if not work_product_refs:
            raise CloseoutReducerError("work product history is required before closeout")
```

Also ensure `reduce(...)` merges base history work product refs before processing events:

```python
        work_product_refs = list(base_history.work_product_submitted_refs) if base_history else []
```

- [ ] **Step 4: 运行测试确认 GREEN（通过）**

Run the command from Step 2 again.

Expected: PASS.

---

## Task 5: 事件顺序、跨项目、重复 closeout 和 runtime closeout 负例

**Files:**
- Modify: `src/boardroom_os/reducers/closeout_reducer.py`
- Modify: `tests/closeout/test_closeout_reducer.py`

- [ ] **Step 1: 追加事件级 fail-closed 测试**

Append to `tests/closeout/test_closeout_reducer.py`:

```python

def test_closeout_reducer_rejects_runtime_closeout_event() -> None:
    package = _passed_package()

    with pytest.raises(CloseoutReducerError, match="runtime|executor"):
        CloseoutReducer(_resolver_for_package(package)).reduce(
            (
                _work_product_event(graph_version=9),
                _closeout_event(graph_version=package.graph_version, actor_ref="runtime:executor"),
            )
        )


def test_closeout_reducer_rejects_duplicate_closeout_commit() -> None:
    package = _passed_package()
    duplicate = _event(
        event_id="evt.closeout.committed.duplicate",
        event_type=EventType.CLOSEOUT_COMMITTED,
        payload_ref="payload.closeout.commit",
        graph_version=package.graph_version + 1,
        actor_ref="seat-closeout",
    )

    with pytest.raises(CloseoutReducerError, match="duplicate|already"):
        CloseoutReducer(_resolver_for_package(package)).reduce(
            (
                _work_product_event(graph_version=9),
                _closeout_event(graph_version=package.graph_version),
                duplicate,
            )
        )


def test_closeout_reducer_rejects_succeeded_base_history_recloseout() -> None:
    package = _passed_package()

    with pytest.raises(CloseoutReducerError, match="succeeded base_history"):
        CloseoutReducer(_resolver_for_package(package)).reduce(
            (_closeout_event(graph_version=package.graph_version),),
            base_history=_base_history(terminal_status=CloseoutTerminalStatus.SUCCEEDED),
        )


def test_closeout_reducer_rejects_out_of_order_or_cross_project_events() -> None:
    package = _passed_package()
    reducer = CloseoutReducer(_resolver_for_package(package))

    with pytest.raises(CloseoutReducerError, match="strictly increasing"):
        reducer.reduce(
            (
                _work_product_event(graph_version=package.graph_version),
                _closeout_event(graph_version=package.graph_version),
            )
        )

    with pytest.raises(CloseoutReducerError, match="project_ref"):
        reducer.reduce(
            (
                _work_product_event(graph_version=9),
                _event(
                    event_id="evt.closeout.other-project",
                    event_type=EventType.CLOSEOUT_COMMITTED,
                    payload_ref="payload.closeout.commit",
                    graph_version=package.graph_version,
                    project_ref=ProjectRef(value="project.other"),
                ),
            )
        )
```

- [ ] **Step 2: 运行测试确认 RED（失败）**

Run:

```bash
PYTHONPATH="src;." python -m pytest tests/closeout/test_closeout_reducer.py::test_closeout_reducer_rejects_runtime_closeout_event tests/closeout/test_closeout_reducer.py::test_closeout_reducer_rejects_duplicate_closeout_commit tests/closeout/test_closeout_reducer.py::test_closeout_reducer_rejects_succeeded_base_history_recloseout tests/closeout/test_closeout_reducer.py::test_closeout_reducer_rejects_out_of_order_or_cross_project_events -q
```

Expected: At least runtime/duplicate tests FAIL if not yet implemented; base history and ordering may already pass.

- [ ] **Step 3: 实现 runtime actor 和 duplicate closeout 检查**

Modify `src/boardroom_os/reducers/closeout_reducer.py`.

In `reduce(...)`, add `closeout_committed = False` before the loop:

```python
        closeout_committed = bool(base_history.closeout_package_refs) if base_history else False
```

Inside the `CLOSEOUT_COMMITTED` branch, before resolving payload, add:

```python
                self._reject_runtime_closeout(event)
                if closeout_committed:
                    raise CloseoutReducerError("duplicate closeout commit is not allowed")
                closeout_committed = True
```

Add this static method to `CloseoutReducer`:

```python
    @staticmethod
    def _reject_runtime_closeout(event: EventRecord) -> None:
        actor = event.actor_ref.value
        if actor.startswith("runtime:") or actor.startswith("executor:"):
            raise CloseoutReducerError("runtime/executor cannot commit closeout")
```

- [ ] **Step 4: 确保 succeeded base history 被拒绝**

Confirm `_validate_base_history(...)` contains:

```python
    @staticmethod
    def _validate_base_history(base_history: CloseoutHistoryProjection | None) -> None:
        if base_history is not None and base_history.terminal_status is CloseoutTerminalStatus.SUCCEEDED:
            raise CloseoutReducerError("succeeded base_history cannot be reduced again")
```

- [ ] **Step 5: 运行测试确认 GREEN（通过）**

Run the command from Step 2 again.

Expected: PASS.

---

## Task 6: Payload/package binding（载荷/包绑定）负例

**Files:**
- Modify: `src/boardroom_os/reducers/closeout_reducer.py`
- Modify: `tests/closeout/test_closeout_reducer.py`

- [ ] **Step 1: 追加 payload/package mismatch 测试**

Append to `tests/closeout/test_closeout_reducer.py`:

```python

def test_closeout_reducer_rejects_missing_closeout_gate_or_blocked_package() -> None:
    package = _passed_package()
    payload = _commit_payload(package, closeout_gate_result_ref="closeout-gate-result.missing")
    resolver = InMemoryCloseoutPayloadResolver(
        commit_payloads={"payload.closeout.commit": payload},
        packages={package.closeout_package_id.value: package},
    )

    with pytest.raises(CloseoutReducerError, match="closeout_gate_result_ref"):
        CloseoutReducer(resolver).reduce(
            (_work_product_event(graph_version=9), _closeout_event(graph_version=package.graph_version))
        )


def test_closeout_reducer_rejects_missing_replay_bundle_binding() -> None:
    package = _passed_package()
    payload = _commit_payload(package, replay_bundle_ref="replay-bundle.other")
    resolver = InMemoryCloseoutPayloadResolver(
        commit_payloads={"payload.closeout.commit": payload},
        packages={package.closeout_package_id.value: package},
    )

    with pytest.raises(CloseoutReducerError, match="replay_bundle_ref"):
        CloseoutReducer(resolver).reduce(
            (_work_product_event(graph_version=9), _closeout_event(graph_version=package.graph_version))
        )


@pytest.mark.parametrize(
    ("field_name", "replacement"),
    (
        ("source_inventory_ref", "source-inventory.other"),
        ("final_evidence_table_ref", "final-evidence-table.other"),
        ("process_audit_bundle_ref", "process-audit-bundle.other"),
        ("git_version_audit_bundle_ref", "git-version-audit-bundle.other"),
        ("package_commit_ref", "package-commit." + "f" * 40),
    ),
)
def test_closeout_reducer_rejects_package_payload_ref_mismatch(
    field_name: str,
    replacement: str,
) -> None:
    package = _passed_package()
    payload = _commit_payload(package, **{field_name: replacement})
    resolver = InMemoryCloseoutPayloadResolver(
        commit_payloads={"payload.closeout.commit": payload},
        packages={package.closeout_package_id.value: package},
    )

    with pytest.raises(CloseoutReducerError, match=field_name):
        CloseoutReducer(resolver).reduce(
            (_work_product_event(graph_version=9), _closeout_event(graph_version=package.graph_version))
        )


def test_closeout_reducer_rejects_closeout_before_package_graph_version() -> None:
    package = _passed_package()

    with pytest.raises(CloseoutReducerError, match="graph_version"):
        CloseoutReducer(_resolver_for_package(package)).reduce(
            (_work_product_event(graph_version=9), _closeout_event(graph_version=package.graph_version - 1))
        )


def test_closeout_reducer_rejects_raw_dict_payloads() -> None:
    package = _passed_package()
    resolver = InMemoryCloseoutPayloadResolver(
        commit_payloads={"payload.closeout.commit": _commit_payload(package)},
        packages={package.closeout_package_id.value: package},
    )
    resolver._commit_payloads["payload.closeout.commit"] = _commit_payload(package).model_dump(mode="python")  # type: ignore[assignment]

    with pytest.raises(CloseoutReducerError, match="CloseoutCommitPayload"):
        CloseoutReducer(resolver).reduce(
            (_work_product_event(graph_version=9), _closeout_event(graph_version=package.graph_version))
        )


def test_closeout_reducer_rejects_checked_refs_gap() -> None:
    package = _passed_package()
    package_with_gap = package.model_copy(update={"checked_refs": package.checked_refs[1:]})
    resolver = InMemoryCloseoutPayloadResolver(
        commit_payloads={"payload.closeout.commit": _commit_payload(package_with_gap)},
        packages={package_with_gap.closeout_package_id.value: package_with_gap},
    )

    with pytest.raises(CloseoutReducerError, match="checked_refs"):
        CloseoutReducer(resolver).reduce(
            (_work_product_event(graph_version=9), _closeout_event(graph_version=package_with_gap.graph_version))
        )
```

- [ ] **Step 2: 运行新增测试确认当前状态**

Run:

```bash
PYTHONPATH="src;." python -m pytest tests/closeout/test_closeout_reducer.py::test_closeout_reducer_rejects_missing_closeout_gate_or_blocked_package tests/closeout/test_closeout_reducer.py::test_closeout_reducer_rejects_missing_replay_bundle_binding tests/closeout/test_closeout_reducer.py::test_closeout_reducer_rejects_package_payload_ref_mismatch tests/closeout/test_closeout_reducer.py::test_closeout_reducer_rejects_closeout_before_package_graph_version tests/closeout/test_closeout_reducer.py::test_closeout_reducer_rejects_raw_dict_payloads tests/closeout/test_closeout_reducer.py::test_closeout_reducer_rejects_checked_refs_gap -q
```

Expected: Some tests may PASS from Task 3; `checked_refs_gap` may FAIL depending on which ref is removed. Continue to Step 3 if needed.

- [ ] **Step 3: Ensure checked_refs validation checks every external payload ref**

In `_validate_closeout_binding(...)`, ensure this exact set is used:

```python
        required_checked_refs = {
            payload.closeout_gate_result_ref.value,
            payload.source_inventory_ref.value,
            payload.final_evidence_table_ref.value,
            payload.replay_bundle_ref.value,
            payload.process_audit_bundle_ref.value,
            payload.git_version_audit_bundle_ref.value,
            payload.package_commit_ref.value,
        }
```

Do not include `payload.closeout_package_ref.value` in this set; package self ref is checked by:

```python
        if package.closeout_package_id != payload.closeout_package_ref:
            raise CloseoutReducerError("closeout package ref mismatch")
```

- [ ] **Step 4: 运行测试确认 GREEN（通过）**

Run the command from Step 2 again.

Expected: PASS.

---

## Task 7: Projection JSON（投影 JSON）审计友好与全文件回归

**Files:**
- Modify: `src/boardroom_os/reducers/closeout_reducer.py`
- Modify: `tests/closeout/test_closeout_reducer.py`

- [ ] **Step 1: 追加 audit-friendly JSON 正例与 workflow completed 负例**

Append to `tests/closeout/test_closeout_reducer.py`:

```python

def test_closeout_projection_dump_is_audit_friendly_json() -> None:
    import json

    package = _passed_package()
    projection = CloseoutReducer(_resolver_for_package(package)).reduce(
        (_work_product_event(graph_version=9), _closeout_event(graph_version=package.graph_version))
    )
    serialized = json.dumps(projection.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)

    assert "D:/" not in serialized
    assert "C:/" not in serialized
    assert "D:\\" not in serialized
    assert "C:\\" not in serialized
    assert ".pytest" not in serialized
    assert "backend/app/core" not in serialized


def test_closeout_reducer_rejects_workflow_completed_without_closeout_package() -> None:
    projection = CloseoutReducer(InMemoryCloseoutPayloadResolver()).reduce(
        (_work_product_event(graph_version=9),)
    )

    assert projection.terminal_status is CloseoutTerminalStatus.OPEN
    assert projection.closeout_package_ref is None
```

- [ ] **Step 2: 运行新增测试确认 GREEN（通过）**

Run:

```bash
PYTHONPATH="src;." python -m pytest tests/closeout/test_closeout_reducer.py::test_closeout_projection_dump_is_audit_friendly_json tests/closeout/test_closeout_reducer.py::test_closeout_reducer_rejects_workflow_completed_without_closeout_package -q
```

Expected: PASS.

- [ ] **Step 3: 运行 closeout reducer 测试全文件**

Run:

```bash
PYTHONPATH="src;." python -m pytest tests/closeout/test_closeout_reducer.py -q
```

Expected: PASS for all tests in the file.

- [ ] **Step 4: 若 import 顺序或 lint 风格有明显问题，整理测试 import**

Ensure the top of `tests/closeout/test_closeout_reducer.py` has one coherent import block like:

```python
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import ValidationError

from boardroom_os.closeout.package import CloseoutPackage, CloseoutPackageRef
from boardroom_os.events.record import EventRecord
from boardroom_os.events.types import ActorRef, EventId, EventPayloadRef, EventType, ProjectRef
from boardroom_os.execution.runtime_executor import RuntimeEventBoundary, RuntimeExecutorError
from boardroom_os.execution.work_product import WorkProductRef
from boardroom_os.graph.ticket import TicketId
from boardroom_os.reducers.closeout_reducer import (
    CloseoutCommitPayload,
    CloseoutHistoryProjection,
    CloseoutProjection,
    CloseoutReducer,
    CloseoutReducerError,
    CloseoutCommitVerdict,
    CloseoutReducerPayloadResolver,
    CloseoutTerminalStatus,
)
from boardroom_os.workspace.source_inventory import PackageCommitRef
from tests.closeout.test_closeout_package import _build_package
```

Remove imports that are not used after all tasks are complete.

---

## Task 8: Closeout chain（收尾链）与 reducer 边界回归

**Files:**
- No new source files.
- Test command only unless failures require minimal fixes.

- [ ] **Step 1: Run gate-package-reducer chain tests（门禁-包-归约链测试）**

Run:

```bash
PYTHONPATH="src;." python -m pytest tests/closeout/test_closeout_reducer.py tests/closeout/test_closeout_package.py tests/closeout/test_closeout_gate.py tests/negative/test_closeout_fail_closed.py -q
```

Expected: PASS. This proves V2-070A/E/F chain still agrees.

- [ ] **Step 2: Run ticket completion vs closeout regression（任务完成与收尾边界回归）**

Run:

```bash
PYTHONPATH="src;." python -m pytest tests/reducers/test_completion_gate_with_evidence.py tests/reducers/test_ticket_reducer_transitions.py tests/closeout/test_closeout_reducer.py -q
```

Expected: PASS. This proves `TicketReducer`（任务归约器） and `CloseoutReducer`（收尾归约器） remain separate.

- [ ] **Step 3: Run runtime governance regression（运行时治理边界回归）**

Run:

```bash
PYTHONPATH="src;." python -m pytest tests/negative/test_runtime_cannot_govern.py tests/execution/test_runtime_executor_boundary.py tests/closeout/test_closeout_reducer.py -q
```

Expected: PASS. This proves runtime cannot emit `TICKET_COMPLETED`（任务已完成） or `CLOSEOUT_COMMITTED`（收尾已提交）.

- [ ] **Step 4: Run full suite（全量测试）**

Run:

```bash
PYTHONPATH="src;." python -m pytest tests/contracts tests/reducers tests/execution tests/evidence tests/proving tests/closeout tests/negative -q --basetemp=.pytest-tmp-v2070f-all
```

Expected: PASS with the current suite size plus new V2-070F tests. If the first run fails due to Windows pytest temp permission, keep the `--basetemp=.pytest-tmp-v2070f-all` argument and rerun once after removing stale pytest temp if needed.

---

## Task 9: 文档完成更新协议

**Files:**
- Modify: `doc/04-implementation/backlog.md`
- Modify: `doc/04-implementation/acceptance-criteria.md`
- Modify: `doc/05-project-log/2026-05.md`
- Modify: `doc/04-implementation/INDEX.md`

- [ ] **Step 1: Update `doc/04-implementation/INDEX.md` for the plan**

Add this row after `v2-070f-closeout-reducer-spec.md`:

```markdown
| `v2-070f-closeout-reducer-implementation-plan.md` | V2-070F CloseoutReducer（收尾归约器）实施计划 |
```

- [ ] **Step 2: Update backlog V2-070F status and TL;DR**

In `doc/04-implementation/backlog.md`, make these exact semantic changes:

- Top TL;DR:
  - `当前未完成工作包：V2-070F` → `当前未完成工作包：V2-080A`
  - 当前重点改为 Phase 8 starting V2-080A（定义 tiny scenario active contracts，定义微型场景活跃合同）。 Suggested text:

```markdown
**当前重点**：Phase 8 启动 V2-080A tiny scenario active contracts（微型场景活跃合同），为 tiny book availability tracker（微型图书可用性追踪器）生成 ProjectCharter（项目章程）、AcceptanceContract（验收合同）和 PackageContract（包合同）fixture，覆盖 API / UI / persistence / run / test acceptance refs（验收引用）。
```

- Progress table:
  - Phase 7: `5 / 6 | 进行中` → `6 / 6 | 完成`
  - Total: `46 / 53 | Phase 7 进行中` → `47 / 53 | Phase 8 待开始`

- V2-070F section:
  - `状态：TODO` → `状态：DONE`
  - Add completion evidence paragraph under 验收口径:

```markdown
- 完成证据：2026-05-25 新增 `EventType.CLOSEOUT_COMMITTED`（收尾已提交事件）与 CloseoutReducer（收尾归约器），保持 RuntimeEventBoundary（运行时事件边界）拒绝 runtime emit（运行时发出）治理事件；`tests/closeout/test_closeout_reducer.py` 证明 runtime closeout、workflow completed 替代 closeout、缺 closeout gate/package/replay binding、payload/package ref mismatch、缺 WORK_PRODUCT_SUBMITTED 历史、重复 closeout、乱序/跨项目事件均 fail closed；passed CloseoutPackage（通过收尾包）经治理事件可投影为 terminal success（终态成功）。验证命令见 `doc/05-project-log/2026-05.md` V2-070F 记录。
```

- [ ] **Step 3: Update acceptance criteria Phase 7 checkboxes**

In `doc/04-implementation/acceptance-criteria.md`, in Phase 7:

Change:

```markdown
- [ ] Closeout reducer 接入 — 由 V2-070F `test_closeout_reducer.py` 证明：增量 reducer/replay 不得丢失历史 `WORK_PRODUCT_SUBMITTED` 事实
- [ ] V2-070A ~ V2-070F 六个工作包全部 DONE
- [ ] `backlog.md` 进度总览 Phase 7 显示 6/6
```

to:

```markdown
- [x] Closeout reducer 接入 — 由 V2-070F `test_closeout_reducer.py` 证明：runtime closeout、workflow completed 替代 closeout、缺 closeout gate/package/replay binding、payload/package ref mismatch、缺历史 `WORK_PRODUCT_SUBMITTED` 事实、重复 closeout、乱序/跨项目事件均 fail closed；passed CloseoutPackage（通过收尾包）经 `CLOSEOUT_COMMITTED`（收尾已提交）治理事件可投影为 terminal success（终态成功）
- [x] V2-070A ~ V2-070F 六个工作包全部 DONE
- [x] `backlog.md` 进度总览 Phase 7 显示 6/6
```

In Phase 7 “进入 Phase 8 前置”, change all three checkboxes to `[x]`:

```markdown
- [x] 上述 AC checkbox 全部勾选
- [x] V2-070A ~ V2-070F 状态全部 DONE
- [x] 10 项 30-audit 产物的 schema 稳定
```

- [ ] **Step 4: Append project log entry**

Append to `doc/05-project-log/2026-05.md`:

```markdown
### V2-070F closeout reducer 集成（2026-05-25）

- 工作包：V2-070F
- 状态：DONE
- 关键产出：`src/boardroom_os/reducers/closeout_reducer.py`、`tests/closeout/test_closeout_reducer.py`；`src/boardroom_os/events/types.py` 新增 `EventType.CLOSEOUT_COMMITTED`（收尾已提交事件），`RuntimeEventBoundary`（运行时事件边界）继续拒绝 runtime emit（运行时发出）治理事件。
- Negative tests：runtime closeout（运行时收尾）、workflow completed（流程完成）替代 closeout、缺 closeout gate/package/replay binding（收尾门禁/收尾包/重放绑定）、payload/package ref mismatch（载荷/包引用不一致）、缺历史 `WORK_PRODUCT_SUBMITTED`（工作产物已提交）、仅 ticket completed（任务已完成）历史、重复 closeout commit（重复收尾提交）、乱序 graph_version（图版本）和跨项目事件均 fail closed。
- Happy path：当前事件历史包含 `WORK_PRODUCT_SUBMITTED` 与合法 `CLOSEOUT_COMMITTED` 时可投影 `terminal_status=succeeded`（终态成功）；增量模式可通过显式 `CloseoutHistoryProjection`（收尾历史投影）携带 work product refs（工作产物引用）后完成收尾。
- 验证证据：`PYTHONPATH="src;." python -m pytest tests/closeout/test_closeout_reducer.py -q` 通过；`PYTHONPATH="src;." python -m pytest tests/closeout/test_closeout_reducer.py tests/closeout/test_closeout_package.py tests/closeout/test_closeout_gate.py tests/negative/test_closeout_fail_closed.py -q` 通过；`PYTHONPATH="src;." python -m pytest tests/reducers/test_completion_gate_with_evidence.py tests/reducers/test_ticket_reducer_transitions.py tests/closeout/test_closeout_reducer.py -q` 通过；`PYTHONPATH="src;." python -m pytest tests/contracts tests/reducers tests/execution tests/evidence tests/proving tests/closeout tests/negative -q --basetemp=.pytest-tmp-v2070f-all` 通过。
```

If actual test counts are available from command output, append counts in parentheses.

- [ ] **Step 5: Run doc grep sanity checks**

Run:

```bash
python - <<'PY'
from pathlib import Path
backlog = Path('doc/04-implementation/backlog.md').read_text(encoding='utf-8')
ac = Path('doc/04-implementation/acceptance-criteria.md').read_text(encoding='utf-8')
index = Path('doc/04-implementation/INDEX.md').read_text(encoding='utf-8')
assert '**当前未完成工作包**：`V2-080A`' in backlog
assert '| Phase 7：Closeout + Replay + Audit | V2-070 | 6 / 6 | 完成 |' in backlog
assert '- 状态：DONE' in backlog.split('### V2-070F: closeout reducer 集成', 1)[1].split('---', 1)[0]
assert '- [x] Closeout reducer 接入' in ac
assert '- [x] V2-070A ~ V2-070F 六个工作包全部 DONE' in ac
assert 'v2-070f-closeout-reducer-implementation-plan.md' in index
print('doc sanity ok')
PY
```

Expected: `doc sanity ok`.

---

## Task 10: Final verification（最终验证）与收尾检查

**Files:**
- No source changes unless verification finds an issue.

- [ ] **Step 1: Run targeted V2-070F test**

Run:

```bash
PYTHONPATH="src;." python -m pytest tests/closeout/test_closeout_reducer.py -q
```

Expected: PASS.

- [ ] **Step 2: Run closeout package/gate regression**

Run:

```bash
PYTHONPATH="src;." python -m pytest tests/closeout/test_closeout_reducer.py tests/closeout/test_closeout_package.py tests/closeout/test_closeout_gate.py tests/negative/test_closeout_fail_closed.py -q
```

Expected: PASS.

- [ ] **Step 3: Run ticket reducer boundary regression**

Run:

```bash
PYTHONPATH="src;." python -m pytest tests/reducers/test_completion_gate_with_evidence.py tests/reducers/test_ticket_reducer_transitions.py tests/closeout/test_closeout_reducer.py -q
```

Expected: PASS.

- [ ] **Step 4: Run full suite with stable basetemp**

Run:

```bash
PYTHONPATH="src;." python -m pytest tests/contracts tests/reducers tests/execution tests/evidence tests/proving tests/closeout tests/negative -q --basetemp=.pytest-tmp-v2070f-all
```

Expected: PASS.

- [ ] **Step 5: Inspect git diff（检查变更）**

Run:

```bash
git diff -- src/boardroom_os/events/types.py src/boardroom_os/execution/runtime_executor.py src/boardroom_os/reducers/closeout_reducer.py tests/closeout/test_closeout_reducer.py doc/04-implementation/backlog.md doc/04-implementation/acceptance-criteria.md doc/05-project-log/2026-05.md doc/04-implementation/INDEX.md doc/04-implementation/v2-070f-closeout-reducer-spec.md doc/04-implementation/v2-070f-closeout-reducer-implementation-plan.md
```

Expected: Diff only includes V2-070F source/test/docs and the minor spec correction about `checked_refs` not requiring package self ref.

- [ ] **Step 6: Do not commit unless user explicitly asks**

No commit in this session unless the user explicitly requests it. If asked to commit, use commit format from global instructions, e.g.:

```text
feat(closeout): 实现收尾归约器终态投影
```

---

## Self-review checklist

- Spec coverage: Tasks 1-7 cover `CLOSEOUT_COMMITTED` event, RuntimeEventBoundary rejection, CloseoutReducer models, payload/package binding, explicit work product history, duplicate/ordering/cross-project fail-closed, terminal success projection, and audit-friendly JSON. Tasks 8-10 cover regression and completion protocol.
- Placeholder scan: No TBD/TODO/fill-later placeholders; each step includes exact code or exact command.
- Type consistency: `CloseoutCommitVerdict`, `CloseoutCommitPayload`, `CloseoutHistoryProjection`, `CloseoutProjection`, `CloseoutReducerPayloadResolver`, `CloseoutTerminalStatus`, and `CloseoutReducerError` are defined before use in tests; `CloseoutPackageRef` comes from `boardroom_os.closeout.package`; `PackageCommitRef` comes from `boardroom_os.workspace.source_inventory`; `EventPayloadRef` is used for work product history payload refs.
