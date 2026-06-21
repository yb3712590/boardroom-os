from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal, Protocol, Self

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from boardroom_os.adapters.process_runner import (
    Clock,
    CommandRunner,
    CommandRunnerInput,
    ProcessExecutor,
    SystemClock,
)
from boardroom_os.agents.skills import _normalize_ref_fields
from boardroom_os.contracts.hashes import Sha256Hex
from boardroom_os.contracts.package import PackageContract
from boardroom_os.contracts.types import AcceptanceRef, ContractId, NonEmptyTextValue
from boardroom_os.evidence.blackbox_plan import (
    BlackboxPlanAction,
    BlackboxPlanActionKind,
    BlackboxPlanApproval,
    BlackboxVerificationPlan,
    BlackboxVerificationPlanRef,
    validate_blackbox_plan_approval,
)
from boardroom_os.execution.package import ContextRef, ExecutionPackage
from boardroom_os.execution.verification_run import (
    CommandOutputRef,
    EnvironmentProfileRef,
    RunnerRef,
    VerificationRunRef,
    WorkspaceSnapshotRef,
)


class BlackboxActionExecutionFactRef(NonEmptyTextValue):
    pass


class BlackboxPlanRunnerStatus(StrEnum):
    FACTS_RECORDED = "facts_recorded"
    BLOCKED_OR_ESCALATED = "blocked_or_escalated"


class BlackboxActionInputRefHash(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    input_ref: ContextRef
    sha256: Sha256Hex

    @model_validator(mode="before")
    @classmethod
    def _normalize_refs(cls, data: Any) -> Any:
        return _normalize_ref_fields(
            data,
            {
                "input_ref": ContextRef,
                "sha256": Sha256Hex,
            },
        )


class BlackboxActionExecutorResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    exit_code: int | None = None
    status_code: int | None = None
    stdout_ref: str | None = None
    stderr_ref: str | None = None
    body_ref: str | None = None
    screenshot_ref: str | None = None
    artifact_refs: tuple[str, ...] = ()
    observed_ref: str | None = None
    status_text: str | None = None

    @field_validator(
        "stdout_ref",
        "stderr_ref",
        "body_ref",
        "screenshot_ref",
        "observed_ref",
        "status_text",
    )
    @classmethod
    def _normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("optional text fields must not be empty")
        return normalized

    @field_validator("artifact_refs")
    @classmethod
    def _normalize_artifact_refs(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(value.strip() for value in values)
        if any(not value for value in normalized):
            raise ValueError("artifact_refs must not contain empty values")
        if len(set(normalized)) != len(normalized):
            raise ValueError("artifact_refs must be unique")
        return normalized

    @field_validator("status_code")
    @classmethod
    def _require_positive_status_code(cls, value: int | None) -> int | None:
        if value is not None and value <= 0:
            raise ValueError("status_code must be positive")
        return value

    @model_validator(mode="after")
    def _require_observable_output(self) -> Self:
        if (
            self.exit_code is None
            and self.status_code is None
            and self.stdout_ref is None
            and self.stderr_ref is None
            and self.body_ref is None
            and self.screenshot_ref is None
            and not self.artifact_refs
            and self.observed_ref is None
            and self.status_text is None
        ):
            raise ValueError("executor result must include observable output")
        return self

    def artifact_ref_tuple(self) -> tuple[str, ...]:
        refs = list(self.artifact_refs)
        if self.observed_ref is not None:
            refs.append(self.observed_ref)
        return tuple(dict.fromkeys(refs))


class HttpActionExecutor(Protocol):
    def execute_http(self, *, method: str, url: str) -> BlackboxActionExecutorResult: ...


class BrowserActionExecutor(Protocol):
    def execute_browser(
        self,
        *,
        browser_target: str,
        browser_action: str,
    ) -> BlackboxActionExecutorResult: ...


class ToolActionExecutor(Protocol):
    def execute_tool(
        self,
        *,
        tool_name: str,
        tool_input_ref: ContextRef | None,
    ) -> BlackboxActionExecutorResult: ...


class FileReadActionExecutor(Protocol):
    def execute_file_read(self, *, file_path: str) -> BlackboxActionExecutorResult: ...


class BlackboxActionExecutionFact(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    version: Literal[1] = 1
    fact_id: BlackboxActionExecutionFactRef
    plan_ref: BlackboxVerificationPlanRef
    action_id: str
    action_kind: BlackboxPlanActionKind
    input_ref_hashes: tuple[BlackboxActionInputRefHash, ...] = ()
    command: tuple[str, ...] | None = None
    cwd: str | None = None
    method: str | None = None
    url: str | None = None
    browser_target: str | None = None
    browser_action: str | None = None
    tool_name: str | None = None
    file_path: str | None = None
    stdout_ref: CommandOutputRef | None = None
    stderr_ref: CommandOutputRef | None = None
    body_ref: str | None = None
    screenshot_ref: str | None = None
    artifact_refs: tuple[str, ...] = ()
    exit_code: int | None = None
    http_status: int | None = None
    status_text: str | None = None
    verification_run_ref: VerificationRunRef | None = None
    started_at: datetime
    finished_at: datetime
    acceptance_refs: tuple[AcceptanceRef, ...]
    package_contract_ref: ContextRef

    @model_validator(mode="before")
    @classmethod
    def _normalize_refs(cls, data: Any) -> Any:
        return _normalize_ref_fields(
            data,
            {
                "fact_id": BlackboxActionExecutionFactRef,
                "plan_ref": BlackboxVerificationPlanRef,
                "stdout_ref": CommandOutputRef,
                "stderr_ref": CommandOutputRef,
                "verification_run_ref": VerificationRunRef,
                "package_contract_ref": ContextRef,
            },
            {"acceptance_refs": AcceptanceRef},
        )

    @field_validator("action_id")
    @classmethod
    def _reject_empty_action_id(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("action_id must not be empty")
        return normalized

    @field_validator(
        "cwd",
        "method",
        "url",
        "browser_target",
        "browser_action",
        "tool_name",
        "file_path",
        "body_ref",
        "screenshot_ref",
        "status_text",
    )
    @classmethod
    def _normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("optional text fields must not be empty")
        return normalized

    @field_validator("command")
    @classmethod
    def _normalize_optional_command(
        cls,
        values: tuple[str, ...] | None,
    ) -> tuple[str, ...] | None:
        if values is None:
            return None
        normalized = tuple(value.strip() for value in values)
        if not normalized or any(not value for value in normalized):
            raise ValueError("command must not be empty")
        return normalized

    @field_validator("artifact_refs")
    @classmethod
    def _normalize_artifact_refs(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(value.strip() for value in values)
        if any(not value for value in normalized):
            raise ValueError("artifact_refs must not contain empty values")
        if len(set(normalized)) != len(normalized):
            raise ValueError("artifact_refs must be unique")
        return normalized

    @field_validator("started_at", "finished_at")
    @classmethod
    def _require_timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamp fields must be timezone-aware")
        return value

    @field_validator("acceptance_refs")
    @classmethod
    def _reject_empty_acceptance_refs(
        cls,
        values: tuple[AcceptanceRef, ...],
    ) -> tuple[AcceptanceRef, ...]:
        if not values:
            raise ValueError("acceptance_refs must not be empty")
        return values

    @model_validator(mode="after")
    def _validate_fact(self) -> Self:
        if self.finished_at < self.started_at:
            raise ValueError("finished_at must not be earlier than started_at")
        if self.action_kind is BlackboxPlanActionKind.COMMAND:
            if self.command is None or self.cwd is None or self.verification_run_ref is None:
                raise ValueError("command facts require command, cwd and verification_run_ref")
        return self


class BlackboxPlanRunnerInput(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    plan: BlackboxVerificationPlan
    approval: BlackboxPlanApproval
    execution_package: ExecutionPackage
    package_contract: PackageContract
    package_root: Path
    input_ref_hashes: tuple[BlackboxActionInputRefHash, ...]
    runner_ref: RunnerRef
    environment_profile_ref: EnvironmentProfileRef
    workspace_snapshot_ref: WorkspaceSnapshotRef

    @model_validator(mode="before")
    @classmethod
    def _normalize_refs(cls, data: Any) -> Any:
        return _normalize_ref_fields(
            data,
            {
                "runner_ref": RunnerRef,
                "environment_profile_ref": EnvironmentProfileRef,
                "workspace_snapshot_ref": WorkspaceSnapshotRef,
            },
        )

    @field_validator("input_ref_hashes")
    @classmethod
    def _validate_input_ref_hashes(
        cls,
        values: tuple[BlackboxActionInputRefHash, ...],
    ) -> tuple[BlackboxActionInputRefHash, ...]:
        input_ref_values = tuple(item.input_ref.value for item in values)
        if len(set(input_ref_values)) != len(input_ref_values):
            raise ValueError("input_ref_hashes must be unique by input_ref")
        return values


class BlackboxPlanRunnerResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: BlackboxPlanRunnerStatus
    facts: tuple[BlackboxActionExecutionFact, ...] = ()
    blocked_reason_code: str | None = None
    blocked_message: str | None = None

    @field_validator("blocked_reason_code", "blocked_message")
    @classmethod
    def _normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("blocked fields must not be empty")
        return normalized

    @model_validator(mode="after")
    def _validate_status_shape(self) -> Self:
        if self.status is BlackboxPlanRunnerStatus.FACTS_RECORDED:
            if not self.facts:
                raise ValueError("facts_recorded result requires facts")
            if self.blocked_reason_code is not None or self.blocked_message is not None:
                raise ValueError("facts_recorded result must not include blocked reason")
        if self.status is BlackboxPlanRunnerStatus.BLOCKED_OR_ESCALATED:
            if self.facts:
                raise ValueError("blocked_or_escalated result must not include facts")
            if self.blocked_reason_code is None or self.blocked_message is None:
                raise ValueError("blocked_or_escalated result requires blocked reason")
        return self


class BlackboxPlanRunner:
    def __init__(
        self,
        *,
        command_runner: CommandRunner | None = None,
        process_executor: ProcessExecutor | None = None,
        http_executor: HttpActionExecutor | None = None,
        browser_executor: BrowserActionExecutor | None = None,
        tool_executor: ToolActionExecutor | None = None,
        file_read_executor: FileReadActionExecutor | None = None,
        clock: Clock | None = None,
    ) -> None:
        self._clock = clock or SystemClock()
        self._command_runner = command_runner or CommandRunner(
            process_executor=process_executor,
            clock=self._clock,
        )
        self._http_executor = http_executor
        self._browser_executor = browser_executor
        self._tool_executor = tool_executor
        self._file_read_executor = file_read_executor

    def run(self, runner_input: BlackboxPlanRunnerInput) -> BlackboxPlanRunnerResult:
        self._validate_runner_input(runner_input)
        blocked = self._missing_executor_blocker(runner_input)
        if blocked is not None:
            return blocked

        facts = tuple(
            self.run_action(runner_input, action_id=action_id)
            for action_id in runner_input.approval.approved_action_ids
        )
        return BlackboxPlanRunnerResult(
            status=BlackboxPlanRunnerStatus.FACTS_RECORDED,
            facts=facts,
        )

    def run_action(
        self,
        runner_input: BlackboxPlanRunnerInput,
        *,
        action_id: str,
    ) -> BlackboxActionExecutionFact:
        self._validate_runner_input(runner_input)
        action = self._approved_action(runner_input, action_id)
        input_ref_hashes = self._action_input_ref_hashes(runner_input, action)
        if action.action_kind is BlackboxPlanActionKind.COMMAND:
            return self._run_command_action(runner_input, action, input_ref_hashes)
        return self._run_non_command_action(runner_input, action, input_ref_hashes)

    def _validate_runner_input(self, runner_input: BlackboxPlanRunnerInput) -> None:
        if not isinstance(runner_input.plan, BlackboxVerificationPlan):
            raise ValueError("approved BlackboxVerificationPlan is required")
        if not isinstance(runner_input.approval, BlackboxPlanApproval):
            raise ValueError("approved BlackboxVerificationPlan is required")
        validate_blackbox_plan_approval(runner_input.approval, plan=runner_input.plan)

    def _missing_executor_blocker(
        self,
        runner_input: BlackboxPlanRunnerInput,
    ) -> BlackboxPlanRunnerResult | None:
        for action_id in runner_input.approval.approved_action_ids:
            action = self._approved_action(runner_input, action_id)
            if self._executor_for(action.action_kind) is None:
                return BlackboxPlanRunnerResult(
                    status=BlackboxPlanRunnerStatus.BLOCKED_OR_ESCALATED,
                    blocked_reason_code="executor_missing",
                    blocked_message=(
                        "executor missing for approved blackbox action kind: "
                        f"{action.action_kind.value}"
                    ),
                )
        return None

    def _executor_for(self, action_kind: BlackboxPlanActionKind) -> object:
        if action_kind is BlackboxPlanActionKind.COMMAND:
            return self._command_runner
        if action_kind is BlackboxPlanActionKind.HTTP:
            return self._http_executor
        if action_kind is BlackboxPlanActionKind.BROWSER:
            return self._browser_executor
        if action_kind is BlackboxPlanActionKind.TOOL:
            return self._tool_executor
        if action_kind is BlackboxPlanActionKind.FILE_READ:
            return self._file_read_executor
        raise ValueError(f"unsupported blackbox action kind: {action_kind}")

    def _approved_action(
        self,
        runner_input: BlackboxPlanRunnerInput,
        action_id: str,
    ) -> BlackboxPlanAction:
        approved_action_ids = set(runner_input.approval.approved_action_ids)
        if action_id not in approved_action_ids:
            raise ValueError("action is not approved by plan")
        matches = tuple(
            action
            for action in runner_input.plan.actions
            if action.action_id == action_id
        )
        if len(matches) != 1:
            raise ValueError("action is not approved by plan")
        return matches[0]

    def _action_input_ref_hashes(
        self,
        runner_input: BlackboxPlanRunnerInput,
        action: BlackboxPlanAction,
    ) -> tuple[BlackboxActionInputRefHash, ...]:
        hash_by_ref = {
            input_ref_hash.input_ref.value: input_ref_hash
            for input_ref_hash in runner_input.input_ref_hashes
        }
        missing_refs = tuple(
            input_ref.value
            for input_ref in action.input_refs
            if input_ref.value not in hash_by_ref
        )
        if missing_refs:
            raise ValueError("input ref hashes must cover action input_refs")
        return tuple(hash_by_ref[input_ref.value] for input_ref in action.input_refs)

    def _run_command_action(
        self,
        runner_input: BlackboxPlanRunnerInput,
        action: BlackboxPlanAction,
        input_ref_hashes: tuple[BlackboxActionInputRefHash, ...],
    ) -> BlackboxActionExecutionFact:
        command = self._resolve_approved_package_command(runner_input, action)
        command_result = self._command_runner.run(
            CommandRunnerInput(
                execution_package=runner_input.execution_package,
                package_contract=runner_input.package_contract,
                command_id=command.command_id,
                package_root=runner_input.package_root,
                runner_ref=runner_input.runner_ref,
                environment_profile_ref=runner_input.environment_profile_ref,
                workspace_snapshot_ref=runner_input.workspace_snapshot_ref,
            )
        )
        run = command_result.verification_run
        return BlackboxActionExecutionFact(
            fact_id=_fact_id(runner_input.plan, action),
            plan_ref=runner_input.plan.plan_id,
            action_id=action.action_id,
            action_kind=action.action_kind,
            input_ref_hashes=input_ref_hashes,
            command=action.command,
            cwd=action.cwd,
            stdout_ref=run.stdout_ref,
            stderr_ref=run.stderr_ref,
            exit_code=run.exit_code,
            status_text=run.status.value,
            verification_run_ref=run.verification_run_id,
            started_at=run.started_at,
            finished_at=run.finished_at,
            acceptance_refs=action.acceptance_refs,
            package_contract_ref=runner_input.plan.package_contract_ref,
        )

    def _run_non_command_action(
        self,
        runner_input: BlackboxPlanRunnerInput,
        action: BlackboxPlanAction,
        input_ref_hashes: tuple[BlackboxActionInputRefHash, ...],
    ) -> BlackboxActionExecutionFact:
        started_at = _require_timezone_aware(self._clock.now())
        result = self._execute_non_command_action(action)
        finished_at = _require_timezone_aware(self._clock.now())
        if finished_at < started_at:
            raise ValueError("clock finished_at must not be earlier than started_at")

        return BlackboxActionExecutionFact(
            fact_id=_fact_id(runner_input.plan, action),
            plan_ref=runner_input.plan.plan_id,
            action_id=action.action_id,
            action_kind=action.action_kind,
            input_ref_hashes=input_ref_hashes,
            method=action.method,
            url=action.url,
            browser_target=action.browser_target,
            browser_action=action.browser_action,
            tool_name=action.tool_name,
            file_path=action.file_path,
            body_ref=result.body_ref,
            screenshot_ref=result.screenshot_ref,
            artifact_refs=result.artifact_ref_tuple(),
            exit_code=result.exit_code,
            http_status=result.status_code,
            status_text=result.status_text,
            started_at=started_at,
            finished_at=finished_at,
            acceptance_refs=action.acceptance_refs,
            package_contract_ref=runner_input.plan.package_contract_ref,
        )

    def _execute_non_command_action(
        self,
        action: BlackboxPlanAction,
    ) -> BlackboxActionExecutorResult:
        if action.action_kind is BlackboxPlanActionKind.HTTP:
            if self._http_executor is None:
                raise ValueError("executor missing for action kind")
            return self._http_executor.execute_http(
                method=_require_action_text(action.method, "method"),
                url=_require_action_text(action.url, "url"),
            )
        if action.action_kind is BlackboxPlanActionKind.BROWSER:
            if self._browser_executor is None:
                raise ValueError("executor missing for action kind")
            return self._browser_executor.execute_browser(
                browser_target=_require_action_text(
                    action.browser_target,
                    "browser_target",
                ),
                browser_action=_require_action_text(
                    action.browser_action,
                    "browser_action",
                ),
            )
        if action.action_kind is BlackboxPlanActionKind.TOOL:
            if self._tool_executor is None:
                raise ValueError("executor missing for action kind")
            return self._tool_executor.execute_tool(
                tool_name=_require_action_text(action.tool_name, "tool_name"),
                tool_input_ref=action.tool_input_ref,
            )
        if action.action_kind is BlackboxPlanActionKind.FILE_READ:
            if self._file_read_executor is None:
                raise ValueError("executor missing for action kind")
            return self._file_read_executor.execute_file_read(
                file_path=_require_action_text(action.file_path, "file_path"),
            )
        raise ValueError("unsupported non-command action kind")

    def _resolve_approved_package_command(
        self,
        runner_input: BlackboxPlanRunnerInput,
        action: BlackboxPlanAction,
    ):
        matches = tuple(
            command
            for command in runner_input.execution_package.commands
            if command.command == action.command and command.cwd == action.cwd
        )
        if len(matches) != 1:
            raise ValueError(
                "approved command action must match exactly one execution package command"
            )
        return matches[0]


def _fact_id(
    plan: BlackboxVerificationPlan,
    action: BlackboxPlanAction,
) -> BlackboxActionExecutionFactRef:
    return BlackboxActionExecutionFactRef(
        value=f"blackbox-action-fact.{plan.plan_id.value}.{action.action_id}"
    )


def _require_action_text(value: str | None, field_name: str) -> str:
    if value is None:
        raise ValueError(f"{field_name} is required for action execution")
    return value


def _require_timezone_aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("clock.now() must return timezone-aware datetime")
    return value


__all__ = [
    "BlackboxActionExecutionFact",
    "BlackboxActionExecutionFactRef",
    "BlackboxActionExecutorResult",
    "BlackboxActionInputRefHash",
    "BlackboxPlanRunner",
    "BlackboxPlanRunnerInput",
    "BlackboxPlanRunnerResult",
    "BlackboxPlanRunnerStatus",
    "BrowserActionExecutor",
    "FileReadActionExecutor",
    "HttpActionExecutor",
    "ToolActionExecutor",
]
