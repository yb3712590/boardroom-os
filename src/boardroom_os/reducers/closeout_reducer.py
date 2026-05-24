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
                raise CloseoutReducerError(
                    "succeeded projection requires closeout refs and work product history"
                )
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
        closeout_event_count = sum(
            1 for event in events if event.event_type is EventType.CLOSEOUT_COMMITTED
        )
        if closeout_event_count > 1:
            raise CloseoutReducerError("duplicate closeout commit is not allowed")
        closeout_committed = bool(base_history.closeout_package_refs) if base_history else False

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
                self._require_single_payload_ref(event)
                self._reject_runtime_closeout(event)
                if closeout_committed:
                    raise CloseoutReducerError("duplicate closeout commit is not allowed")
                closeout_committed = True
                payload = self._resolve_closeout_commit(event.payload_refs[0])
                package = self._resolve_closeout_package(payload.closeout_package_ref)
                deduped_work_product_refs = tuple(dict.fromkeys(work_product_refs))
                self._validate_closeout_binding(
                    event=event,
                    payload=payload,
                    package=package,
                    work_product_refs=deduped_work_product_refs,
                )
                checked_refs.extend(_closeout_checked_refs(payload, package))
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

        deduped_work_product_refs = tuple(dict.fromkeys(work_product_refs))
        return CloseoutProjection(
            project_ref=project_ref,
            graph_version=graph_version,
            terminal_status=CloseoutTerminalStatus.OPEN,
            work_product_history_refs=deduped_work_product_refs,
            checked_refs=tuple(dict.fromkeys(checked_refs)),
        )

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

    @staticmethod
    def _reject_runtime_closeout(event: EventRecord) -> None:
        actor = event.actor_ref.value
        if actor.startswith("runtime:") or actor.startswith("executor:"):
            raise CloseoutReducerError("runtime/executor cannot commit closeout")

    @staticmethod
    def _require_single_payload_ref(event: EventRecord) -> None:
        if len(event.payload_refs) != 1:
            raise CloseoutReducerError("event must have exactly one payload_ref")

    @staticmethod
    def _validate_base_history(base_history: CloseoutHistoryProjection | None) -> None:
        if base_history is not None and base_history.terminal_status is CloseoutTerminalStatus.SUCCEEDED:
            raise CloseoutReducerError("succeeded base_history cannot be reduced again")


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


__all__ = [
    "CloseoutCommitPayload",
    "CloseoutCommitVerdict",
    "CloseoutHistoryProjection",
    "CloseoutProjection",
    "CloseoutReducer",
    "CloseoutReducerError",
    "CloseoutReducerPayloadResolver",
    "CloseoutTerminalStatus",
]
