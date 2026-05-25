from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import ValidationError

from boardroom_os.closeout.package import (
    CloseoutPackage,
    CloseoutPackageCheckedRef,
    CloseoutPackageRef,
    CloseoutPackageVerdict,
)
from boardroom_os.events.record import EventRecord
from boardroom_os.events.types import ActorRef, EventId, EventPayloadRef, EventType, ProjectRef
from boardroom_os.execution.runtime_executor import RuntimeEventBoundary, RuntimeExecutorError
from boardroom_os.reducers.closeout_reducer import (
    CloseoutCommitPayload,
    CloseoutCommitVerdict,
    CloseoutHistoryProjection,
    CloseoutReducer,
    CloseoutReducerError,
    CloseoutReducerPayloadResolver,
    CloseoutTerminalStatus,
)
from tests.closeout.test_closeout_package import _build_package

_PROJECT_REF = ProjectRef(value="project.closeout-reducer")
_NOW = datetime(2026, 5, 25, 10, 0, tzinfo=UTC)


def _passed_package() -> CloseoutPackage:
    return _build_package(graph_version=10).model_copy(update={"project_ref": _PROJECT_REF})


class InMemoryCloseoutPayloadResolver(CloseoutReducerPayloadResolver):
    def __init__(
        self,
        *,
        commit_payloads: dict[str, Any] | None = None,
        packages: dict[str, Any] | None = None,
    ) -> None:
        self._commit_payloads = commit_payloads or {}
        self._packages = packages or {}

    def resolve_closeout_commit(self, payload_ref: EventPayloadRef) -> CloseoutCommitPayload:
        return self._commit_payloads[payload_ref.value]

    def resolve_closeout_package(self, closeout_package_ref: CloseoutPackageRef) -> CloseoutPackage:
        return self._packages[closeout_package_ref.value]


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


def _work_product_event(graph_version: int = 9) -> EventRecord:
    return _event(
        event_id=f"evt.work-product.submitted.{graph_version}",
        event_type=EventType.WORK_PRODUCT_SUBMITTED,
        payload_ref=f"work-product.submitted.{graph_version}",
        graph_version=graph_version,
        actor_ref="runtime:executor",
    )


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


def test_closeout_reducer_keeps_projection_open_without_closeout_committed_event() -> None:
    projection = CloseoutReducer(InMemoryCloseoutPayloadResolver()).reduce(
        (_work_product_event(graph_version=9),)
    )

    assert projection.terminal_status is CloseoutTerminalStatus.OPEN
    assert projection.project_ref == _PROJECT_REF
    assert projection.graph_version == 9
    assert projection.closeout_package_ref is None
    assert projection.work_product_history_refs == (EventPayloadRef(value="work-product.submitted.9"),)


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

    with pytest.raises(CloseoutReducerError, match="events after closeout|duplicate|already"):
        CloseoutReducer(_resolver_for_package(package)).reduce(
            (
                _work_product_event(graph_version=9),
                _closeout_event(graph_version=package.graph_version),
                duplicate,
            )
        )

    duplicate_history = _base_history(closeout_package_refs=(package.closeout_package_id,))
    with pytest.raises(CloseoutReducerError, match="events after closeout|duplicate|already"):
        CloseoutReducer(_resolver_for_package(package)).reduce(
            (_closeout_event(graph_version=package.graph_version),),
            base_history=duplicate_history,
        )


def test_closeout_reducer_rejects_any_event_after_closeout_commit() -> None:
    package = _passed_package()

    with pytest.raises(CloseoutReducerError, match="events after closeout commit"):
        CloseoutReducer(_resolver_for_package(package)).reduce(
            (
                _work_product_event(graph_version=9),
                _closeout_event(graph_version=package.graph_version),
                _work_product_event(graph_version=package.graph_version + 1),
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

    package_payload = package.model_dump(mode="python")
    package_payload["checked_refs"] = tuple(
        CloseoutPackageCheckedRef(value=value)
        for value in (*[ref.value for ref in package.checked_refs], "package-commit.override")
    )
    package_payload["package_commit_ref"] = "package-commit.override"
    blocked_package = CloseoutPackage.model_validate(package_payload)
    blocked_package = blocked_package.model_copy(update={"verdict": CloseoutPackageVerdict.FAILED})
    resolver = InMemoryCloseoutPayloadResolver(
        commit_payloads={"payload.closeout.commit": _commit_payload(blocked_package)},
        packages={blocked_package.closeout_package_id.value: blocked_package},
    )

    with pytest.raises(CloseoutReducerError, match="verdict"):
        CloseoutReducer(resolver).reduce(
            (_work_product_event(graph_version=9), _closeout_event(graph_version=blocked_package.graph_version))
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
        ("package_commit_ref", "package-commit.fedcba9876543210fedcba9876543210fedcba98"),
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
        commit_payloads={"payload.closeout.commit": _commit_payload(package).model_dump(mode="python")},
        packages={package.closeout_package_id.value: package},
    )

    with pytest.raises(CloseoutReducerError, match="CloseoutCommitPayload"):
        CloseoutReducer(resolver).reduce(
            (_work_product_event(graph_version=9), _closeout_event(graph_version=package.graph_version))
        )


def test_closeout_reducer_rejects_raw_dict_package() -> None:
    package = _passed_package()
    resolver = InMemoryCloseoutPayloadResolver(
        commit_payloads={"payload.closeout.commit": _commit_payload(package)},
        packages={package.closeout_package_id.value: package.model_dump(mode="python")},
    )

    with pytest.raises(CloseoutReducerError, match="CloseoutPackage"):
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


def test_closeout_projection_dump_is_audit_friendly_json() -> None:
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


def test_closeout_commit_payload_rejects_non_passed_terminal_verdict() -> None:
    package = _passed_package()

    with pytest.raises(ValidationError, match="terminal_verdict"):
        _commit_payload(package, terminal_verdict="failed")
