from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, field_validator

from boardroom_os.agents.categories import RoleCategory
from boardroom_os.agents.team import AgentTeamProjection
from boardroom_os.contracts.package import PackageContract
from boardroom_os.contracts.types import ContractId
from boardroom_os.events.record import EventRecord
from boardroom_os.events.types import ActorRef, EventId, EventPayloadRef, EventType, ProjectRef
from boardroom_os.execution.context_index import ProviderAttemptRef
from boardroom_os.execution.package import ExecutionPackage, ExecutionPackageId
from boardroom_os.execution.provider_executor import ProviderExecutor, ProviderExecutorInput
from boardroom_os.execution.verification_run import (
    EnvironmentProfileRef,
    RunnerRef,
    VerificationRun,
    VerificationRunRef,
    WorkspaceSnapshotRef,
)
from boardroom_os.execution.work_product import (
    WorkProductSubmission,
    build_work_product_from_provider_attempt,
    build_work_product_submitted_event,
)
from boardroom_os.providers.attempt import ProviderAttempt, ProviderAttemptStatus


class RuntimeExecutorError(ValueError):
    pass


class ReservedRuntimeGovernanceEvent(StrEnum):
    PROJECT_COMPLETED = "project_completed"
    CLOSEOUT_COMMITTED = "closeout_committed"


class RuntimeEventBoundary:
    _ALLOWED_FACT_EVENT_VALUES = {
        EventType.EXECUTION_STARTED.value,
        EventType.PROVIDER_ATTEMPT_RECORDED.value,
        EventType.TOOL_ATTEMPT_RECORDED.value,
        EventType.WORK_PRODUCT_SUBMITTED.value,
        EventType.COMMAND_RUN_RECORDED.value,
    }
    _REJECTED_GOVERNANCE_EVENT_VALUES = {
        EventType.TICKET_COMPLETED.value,
        ReservedRuntimeGovernanceEvent.PROJECT_COMPLETED.value,
        ReservedRuntimeGovernanceEvent.CLOSEOUT_COMMITTED.value,
    }
    _EXECUTABLE_ROLE_CATEGORIES = {
        RoleCategory.IMPLEMENTATION,
        RoleCategory.VERIFICATION,
        RoleCategory.INTEGRATION,
    }

    @classmethod
    def require_runtime_fact_event(cls, event_type: EventType | str) -> EventType:
        normalized = cls._normalize_event_type(event_type)
        if normalized in cls._REJECTED_GOVERNANCE_EVENT_VALUES:
            raise RuntimeExecutorError(f"runtime cannot emit governance event: {normalized}")
        if normalized not in cls._ALLOWED_FACT_EVENT_VALUES:
            raise RuntimeExecutorError(f"unknown runtime event: {normalized}")
        return EventType(normalized)

    @classmethod
    def require_execution_actor_boundary(
        cls,
        execution_package: ExecutionPackage,
        agent_team_projection: AgentTeamProjection,
        runtime_actor_ref: ActorRef,
    ) -> None:
        active_seats = agent_team_projection.active_seats
        if any(seat.actor_ref == runtime_actor_ref for seat in active_seats.values()):
            raise RuntimeExecutorError(
                f"runtime actor must not match active seat actor: {runtime_actor_ref.value}"
            )

        execution_seat = active_seats.get(execution_package.seat_ref)
        if execution_seat is None:
            raise RuntimeExecutorError(
                f"execution package must target an active execution seat: {execution_package.seat_ref.value}"
            )

        if execution_seat.role_category not in cls._EXECUTABLE_ROLE_CATEGORIES:
            allowed_categories = ", ".join(
                sorted(role_category.value for role_category in cls._EXECUTABLE_ROLE_CATEGORIES)
            )
            raise RuntimeExecutorError(
                "execution package seat has non-executable role category: "
                f"seat_ref={execution_package.seat_ref.value}, "
                f"role_category={execution_seat.role_category.value}, "
                f"allowed_role_categories={allowed_categories}"
            )

    @staticmethod
    def _normalize_event_type(event_type: EventType | str) -> str:
        if isinstance(event_type, EventType):
            return event_type.value
        if isinstance(event_type, str):
            return event_type.strip()
        raise RuntimeExecutorError(f"unknown runtime event: {event_type!r}")


class RuntimeEventSequencer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    base_graph_version: int = Field(gt=0)
    first_fact_graph_version: int = Field(gt=0)
    _next_fact_graph_version: int = PrivateAttr(default=0)

    def model_post_init(self, __context: object) -> None:
        if self.first_fact_graph_version <= self.base_graph_version:
            raise ValueError("first_fact_graph_version must be greater than base_graph_version")
        self._next_fact_graph_version = self.first_fact_graph_version

    def next_graph_version(self) -> int:
        graph_version = self._next_fact_graph_version
        self._next_fact_graph_version += 1
        return graph_version


def _event_id(prefix: str, payload_value: str, graph_version: int) -> EventId:
    return EventId(value=f"event.{prefix}.{payload_value}.{graph_version}")


def _runtime_fact_event(
    *,
    event_type: EventType,
    payload_ref: EventPayloadRef,
    project_ref: ProjectRef,
    actor_ref: ActorRef,
    graph_version: int,
    timestamp: datetime,
    event_id: EventId | None = None,
) -> EventRecord:
    resolved_event_type = RuntimeEventBoundary.require_runtime_fact_event(event_type)
    resolved_event_id = event_id or _event_id(
        prefix=resolved_event_type.value.replace("_", "-"),
        payload_value=payload_ref.value,
        graph_version=graph_version,
    )
    return EventRecord(
        event_id=resolved_event_id,
        event_type=resolved_event_type,
        project_ref=project_ref,
        actor_ref=actor_ref,
        timestamp=timestamp,
        graph_version=graph_version,
        payload_refs=(payload_ref,),
    )


def build_execution_started_event(
    *,
    execution_package_id: ExecutionPackageId,
    project_ref: ProjectRef,
    actor_ref: ActorRef,
    graph_version: int,
    timestamp: datetime,
    event_id: EventId | None = None,
) -> EventRecord:
    return _runtime_fact_event(
        event_type=EventType.EXECUTION_STARTED,
        payload_ref=EventPayloadRef(value=execution_package_id.value),
        project_ref=project_ref,
        actor_ref=actor_ref,
        graph_version=graph_version,
        timestamp=timestamp,
        event_id=event_id,
    )


def build_provider_attempt_recorded_event(
    *,
    provider_attempt_ref: ProviderAttemptRef,
    project_ref: ProjectRef,
    actor_ref: ActorRef,
    graph_version: int,
    timestamp: datetime,
    event_id: EventId | None = None,
) -> EventRecord:
    return _runtime_fact_event(
        event_type=EventType.PROVIDER_ATTEMPT_RECORDED,
        payload_ref=EventPayloadRef(value=provider_attempt_ref.value),
        project_ref=project_ref,
        actor_ref=actor_ref,
        graph_version=graph_version,
        timestamp=timestamp,
        event_id=event_id,
    )


def build_command_run_recorded_event(
    *,
    verification_run_ref: VerificationRunRef,
    project_ref: ProjectRef,
    actor_ref: ActorRef,
    graph_version: int,
    timestamp: datetime,
    event_id: EventId | None = None,
) -> EventRecord:
    return _runtime_fact_event(
        event_type=EventType.COMMAND_RUN_RECORDED,
        payload_ref=EventPayloadRef(value=verification_run_ref.value),
        project_ref=project_ref,
        actor_ref=actor_ref,
        graph_version=graph_version,
        timestamp=timestamp,
        event_id=event_id,
    )


class RuntimeExecutionInput(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    execution_package: ExecutionPackage
    package_contract: PackageContract
    agent_team_projection: AgentTeamProjection
    provider_adapter: Any
    project_ref: ProjectRef
    runtime_actor_ref: ActorRef
    first_fact_graph_version: int = Field(gt=0)
    package_root: Path
    runner_ref: RunnerRef
    environment_profile_ref: EnvironmentProfileRef
    workspace_snapshot_ref: WorkspaceSnapshotRef
    command_ids: tuple[ContractId, ...]
    timestamp: datetime

    @field_validator("command_ids")
    @classmethod
    def _reject_duplicate_command_ids(
        cls,
        value: tuple[ContractId, ...],
    ) -> tuple[ContractId, ...]:
        command_id_values = tuple(command_id.value for command_id in value)
        if len(command_id_values) != len(set(command_id_values)):
            raise ValueError("command_ids must be unique")
        return value


class RuntimeExecutionResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    provider_attempt: ProviderAttempt
    work_product_submission: WorkProductSubmission | None
    verification_runs: tuple[VerificationRun, ...]
    events: tuple[EventRecord, ...]
    stdout_by_verification_run: dict[VerificationRunRef, str]
    stderr_by_verification_run: dict[VerificationRunRef, str]


class RuntimeExecutor:
    def __init__(self, *, provider_executor: ProviderExecutor | None = None) -> None:
        self._provider_executor = provider_executor or ProviderExecutor()

    def execute_package(self, runtime_input: RuntimeExecutionInput) -> RuntimeExecutionResult:
        RuntimeEventBoundary.require_execution_actor_boundary(
            execution_package=runtime_input.execution_package,
            agent_team_projection=runtime_input.agent_team_projection,
            runtime_actor_ref=runtime_input.runtime_actor_ref,
        )
        sequencer = RuntimeEventSequencer(
            base_graph_version=runtime_input.execution_package.graph_version,
            first_fact_graph_version=runtime_input.first_fact_graph_version,
        )
        events: list[EventRecord] = [
            build_execution_started_event(
                execution_package_id=runtime_input.execution_package.execution_package_id,
                project_ref=runtime_input.project_ref,
                actor_ref=runtime_input.runtime_actor_ref,
                graph_version=sequencer.next_graph_version(),
                timestamp=runtime_input.timestamp,
            )
        ]
        provider_result = self._provider_executor.execute(
            ProviderExecutorInput(
                execution_package=runtime_input.execution_package,
                provider_adapter=runtime_input.provider_adapter,
            )
        )
        provider_attempt = provider_result.provider_attempt
        events.append(
            build_provider_attempt_recorded_event(
                provider_attempt_ref=provider_attempt.provider_attempt_id,
                project_ref=runtime_input.project_ref,
                actor_ref=runtime_input.runtime_actor_ref,
                graph_version=sequencer.next_graph_version(),
                timestamp=runtime_input.timestamp,
            )
        )
        if provider_attempt.status is ProviderAttemptStatus.FAILED:
            return RuntimeExecutionResult(
                provider_attempt=provider_attempt,
                work_product_submission=None,
                verification_runs=(),
                events=tuple(events),
                stdout_by_verification_run={},
                stderr_by_verification_run={},
            )

        work_product_submission = build_work_product_from_provider_attempt(
            execution_package=runtime_input.execution_package,
            provider_attempt=provider_attempt,
        )
        events.append(
            build_work_product_submitted_event(
                work_product=work_product_submission.work_product,
                project_ref=runtime_input.project_ref,
                actor_ref=runtime_input.runtime_actor_ref,
                graph_version=sequencer.next_graph_version(),
                timestamp=runtime_input.timestamp,
            )
        )

        from boardroom_os.adapters.process_runner import CommandRunner, CommandRunnerInput

        command_runner = CommandRunner()
        verification_runs: list[VerificationRun] = []
        stdout_by_verification_run: dict[VerificationRunRef, str] = {}
        stderr_by_verification_run: dict[VerificationRunRef, str] = {}
        for command_id in runtime_input.command_ids:
            command_result = command_runner.run(
                CommandRunnerInput(
                    execution_package=runtime_input.execution_package,
                    package_contract=runtime_input.package_contract,
                    command_id=command_id,
                    package_root=runtime_input.package_root,
                    runner_ref=runtime_input.runner_ref,
                    environment_profile_ref=runtime_input.environment_profile_ref,
                    workspace_snapshot_ref=runtime_input.workspace_snapshot_ref,
                )
            )
            verification_run = command_result.verification_run
            verification_runs.append(verification_run)
            stdout_by_verification_run[verification_run.verification_run_id] = command_result.stdout
            stderr_by_verification_run[verification_run.verification_run_id] = command_result.stderr
            events.append(
                build_command_run_recorded_event(
                    verification_run_ref=verification_run.verification_run_id,
                    project_ref=runtime_input.project_ref,
                    actor_ref=runtime_input.runtime_actor_ref,
                    graph_version=sequencer.next_graph_version(),
                    timestamp=runtime_input.timestamp,
                )
            )

        return RuntimeExecutionResult(
            provider_attempt=provider_attempt,
            work_product_submission=work_product_submission,
            verification_runs=tuple(verification_runs),
            events=tuple(events),
            stdout_by_verification_run=stdout_by_verification_run,
            stderr_by_verification_run=stderr_by_verification_run,
        )


__all__ = [
    "ReservedRuntimeGovernanceEvent",
    "RuntimeEventBoundary",
    "RuntimeEventSequencer",
    "RuntimeExecutionInput",
    "RuntimeExecutionResult",
    "RuntimeExecutor",
    "RuntimeExecutorError",
    "build_command_run_recorded_event",
    "build_execution_started_event",
    "build_provider_attempt_recorded_event",
]
