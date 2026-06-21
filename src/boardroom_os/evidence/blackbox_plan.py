from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, ValidationInfo, field_validator, model_validator

from boardroom_os.agents.role_prompt_hooks import RolePromptHookRef
from boardroom_os.agents.seat import AgentSeatRef
from boardroom_os.agents.skills import _normalize_ref_fields
from boardroom_os.contracts.types import (
    AcceptanceRef,
    EvidenceObligationRef,
    NonEmptyTextValue,
)
from boardroom_os.execution.context_index import ProviderAttemptRef
from boardroom_os.execution.package import ContextRef, ExecutionPackage, ExecutionPackageRef
from boardroom_os.providers.attempt import (
    ProviderAttempt,
    ProviderAttemptOutcome,
    ProviderAttemptStatus,
)


class BlackboxVerificationPlanRef(NonEmptyTextValue):
    pass


class BlackboxPlanApprovalRef(NonEmptyTextValue):
    pass


class BlackboxPlanActionKind(StrEnum):
    COMMAND = "command"
    HTTP = "http"
    BROWSER = "browser"
    TOOL = "tool"
    FILE_READ = "file_read"


_SUCCESS_CLAIM_FIELDS = frozenset(
    {
        "passed",
        "approved",
        "closeout_ready",
        "verified",
        "satisfied",
        "success",
        "evidence_passed",
    }
)


class BlackboxPlanAction(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    version: Literal[1] = 1
    action_id: str
    action_kind: BlackboxPlanActionKind
    description: str
    acceptance_refs: tuple[AcceptanceRef, ...]
    input_refs: tuple[ContextRef, ...] = ()
    command: tuple[str, ...] | None = None
    cwd: str | None = None
    method: str | None = None
    url: str | None = None
    browser_target: str | None = None
    browser_action: str | None = None
    tool_name: str | None = None
    tool_input_ref: ContextRef | None = None
    file_path: str | None = None
    required_permissions: tuple[str, ...]
    expected_observations: tuple[str, ...]

    @model_validator(mode="before")
    @classmethod
    def _normalize_refs(cls, data: Any) -> Any:
        return _normalize_ref_fields(
            data,
            {"tool_input_ref": ContextRef},
            {
                "acceptance_refs": AcceptanceRef,
                "input_refs": ContextRef,
            },
        )

    @field_validator("action_id", "description")
    @classmethod
    def _reject_empty_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("text fields must not be empty")
        return normalized

    @field_validator("acceptance_refs")
    @classmethod
    def _reject_empty_acceptance_refs(
        cls,
        values: tuple[AcceptanceRef, ...],
    ) -> tuple[AcceptanceRef, ...]:
        if not values:
            raise ValueError("acceptance_refs must not be empty")
        return values

    @field_validator("command", "required_permissions", "expected_observations")
    @classmethod
    def _reject_empty_text_tuples(
        cls,
        values: tuple[str, ...] | None,
        info: ValidationInfo,
    ) -> tuple[str, ...] | None:
        if values is None:
            return None
        if not values:
            raise ValueError(f"{info.field_name} must not be empty")
        normalized_values = tuple(value.strip() for value in values)
        if any(not value for value in normalized_values):
            raise ValueError(f"{info.field_name} must not contain empty values")
        return normalized_values

    @field_validator(
        "cwd",
        "method",
        "url",
        "browser_target",
        "browser_action",
        "tool_name",
        "file_path",
    )
    @classmethod
    def _normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("optional text fields must not be empty")
        return normalized

    @model_validator(mode="after")
    def _validate_kind_specific_fields(self) -> Self:
        if self.action_kind is BlackboxPlanActionKind.COMMAND:
            if self.command is None or self.cwd is None:
                raise ValueError("command actions require command and cwd")
        elif self.action_kind is BlackboxPlanActionKind.HTTP:
            if self.method is None or self.url is None:
                raise ValueError("http actions require method and url")
        elif self.action_kind is BlackboxPlanActionKind.BROWSER:
            if self.browser_target is None or self.browser_action is None:
                raise ValueError("browser actions require browser_target and browser_action")
        elif self.action_kind is BlackboxPlanActionKind.TOOL:
            if self.tool_name is None:
                raise ValueError("tool actions require tool_name")
        elif self.action_kind is BlackboxPlanActionKind.FILE_READ:
            if self.file_path is None:
                raise ValueError("file_read actions require file_path")
        return self


class BlackboxVerificationPlan(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    version: Literal[1] = 1
    plan_id: BlackboxVerificationPlanRef
    execution_package_ref: ExecutionPackageRef
    producer_attempt_ref: ProviderAttemptRef
    producer_seat_ref: AgentSeatRef
    role_prompt_hook_ref: RolePromptHookRef
    objective: str
    input_context_refs: tuple[ContextRef, ...]
    run_manifest_context_ref: ContextRef
    acceptance_refs: tuple[AcceptanceRef, ...]
    package_contract_ref: ContextRef
    actions: tuple[BlackboxPlanAction, ...]
    evidence_obligation_refs: tuple[EvidenceObligationRef, ...]
    created_at: datetime

    @model_validator(mode="before")
    @classmethod
    def _reject_success_claims_and_normalize_refs(cls, data: Any) -> Any:
        if isinstance(data, dict):
            forbidden_fields = sorted(_SUCCESS_CLAIM_FIELDS.intersection(data))
            if forbidden_fields:
                raise ValueError(
                    "blackbox plan must not contain success claims: "
                    + ", ".join(forbidden_fields)
                )
        return _normalize_ref_fields(
            data,
            {
                "plan_id": BlackboxVerificationPlanRef,
                "execution_package_ref": ExecutionPackageRef,
                "producer_attempt_ref": ProviderAttemptRef,
                "producer_seat_ref": AgentSeatRef,
                "role_prompt_hook_ref": RolePromptHookRef,
                "run_manifest_context_ref": ContextRef,
                "package_contract_ref": ContextRef,
            },
            {
                "input_context_refs": ContextRef,
                "acceptance_refs": AcceptanceRef,
                "evidence_obligation_refs": EvidenceObligationRef,
            },
        )

    @field_validator("objective")
    @classmethod
    def _reject_empty_objective(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("objective must not be empty")
        return normalized

    @field_validator(
        "input_context_refs",
        "acceptance_refs",
        "actions",
        "evidence_obligation_refs",
    )
    @classmethod
    def _reject_empty_required_tuples(
        cls,
        values: tuple[object, ...],
    ) -> tuple[object, ...]:
        if not values:
            raise ValueError("required tuple fields must not be empty")
        return values

    @field_validator("created_at")
    @classmethod
    def _require_timezone_aware_created_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("created_at must be timezone-aware")
        return value

    @model_validator(mode="after")
    def _validate_internal_plan_refs(self) -> Self:
        input_context_values = {context_ref.value for context_ref in self.input_context_refs}
        if self.run_manifest_context_ref.value not in input_context_values:
            raise ValueError("run_manifest_context_ref must be present in input_context_refs")
        if self.package_contract_ref.value not in input_context_values:
            raise ValueError("package_contract_ref must be present in input_context_refs")
        if len(input_context_values) != len(self.input_context_refs):
            raise ValueError("input_context_refs must be unique")

        action_ids = tuple(action.action_id for action in self.actions)
        if len(set(action_ids)) != len(action_ids):
            raise ValueError("action_id values must be unique")

        plan_acceptance_values = {acceptance_ref.value for acceptance_ref in self.acceptance_refs}
        for action in self.actions:
            action_acceptance_values = {
                acceptance_ref.value for acceptance_ref in action.acceptance_refs
            }
            if not action_acceptance_values.issubset(plan_acceptance_values):
                raise ValueError("action acceptance refs must be a subset of plan acceptance_refs")
            action_input_values = {input_ref.value for input_ref in action.input_refs}
            if not action_input_values.issubset(input_context_values):
                raise ValueError("action input_refs must be a subset of plan input_context_refs")
        return self


class BlackboxPlanApproval(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    version: Literal[1] = 1
    approval_id: BlackboxPlanApprovalRef
    plan_ref: BlackboxVerificationPlanRef
    approved_action_ids: tuple[str, ...]
    approval_scope: Literal["execute_plan_actions_only"]
    approved_at: datetime

    @model_validator(mode="before")
    @classmethod
    def _reject_success_claims_and_normalize_refs(cls, data: Any) -> Any:
        if isinstance(data, dict):
            forbidden_fields = sorted(_SUCCESS_CLAIM_FIELDS.intersection(data))
            if forbidden_fields:
                raise ValueError(
                    "blackbox plan approval must not contain success claims: "
                    + ", ".join(forbidden_fields)
                )
        return _normalize_ref_fields(
            data,
            {
                "approval_id": BlackboxPlanApprovalRef,
                "plan_ref": BlackboxVerificationPlanRef,
            },
        )

    @field_validator("approved_action_ids")
    @classmethod
    def _validate_action_ids(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if not values:
            raise ValueError("approved_action_ids must not be empty")
        normalized_values = tuple(value.strip() for value in values)
        if any(not value for value in normalized_values):
            raise ValueError("approved_action_ids must not contain empty values")
        if len(set(normalized_values)) != len(normalized_values):
            raise ValueError("approved_action_ids must be unique")
        return normalized_values

    @field_validator("approved_at")
    @classmethod
    def _require_timezone_aware_approved_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("approved_at must be timezone-aware")
        return value


def validate_blackbox_plan_lineage(
    plan: BlackboxVerificationPlan,
    *,
    execution_package: ExecutionPackage,
    provider_attempts: tuple[ProviderAttempt, ...],
) -> BlackboxVerificationPlan:
    expected_package_ref = ExecutionPackageRef(
        value=execution_package.execution_package_id.value
    )
    if plan.execution_package_ref != expected_package_ref:
        raise ValueError("plan execution_package_ref must match execution package")

    provider_attempt = _resolve_provider_attempt(
        plan.producer_attempt_ref,
        provider_attempts,
    )
    if provider_attempt is None:
        raise ValueError("provider attempt could not be resolved")
    if provider_attempt.status is not ProviderAttemptStatus.SUCCEEDED:
        raise ValueError("provider attempt must be succeeded")
    if provider_attempt.outcome is not ProviderAttemptOutcome.PRIMARY_PROVIDER_OUTPUT:
        raise ValueError("provider attempt must be primary provider output")
    if provider_attempt.input_package_ref != expected_package_ref:
        raise ValueError("provider attempt input_package_ref must match execution package")
    if provider_attempt.seat_ref != execution_package.seat_ref:
        raise ValueError("provider attempt seat_ref must match execution package")
    if plan.producer_seat_ref != execution_package.seat_ref:
        raise ValueError("producer seat must match execution package")

    package_hook = execution_package.role_prompt_hook
    if plan.role_prompt_hook_ref != package_hook.hook_ref:
        raise ValueError("plan role_prompt_hook_ref must match execution package")
    if (
        provider_attempt.role_prompt_hook_ref != package_hook.hook_ref
        or provider_attempt.role_prompt_hook_version != package_hook.hook_version
        or provider_attempt.role_prompt_hook_sha256 != package_hook.content_sha256
    ):
        raise ValueError("provider attempt role prompt hook must match execution package")

    package_acceptance_refs = {
        acceptance_ref.value for acceptance_ref in execution_package.acceptance_refs
    }
    plan_acceptance_refs = {acceptance_ref.value for acceptance_ref in plan.acceptance_refs}
    if not plan_acceptance_refs.issubset(package_acceptance_refs):
        raise ValueError("plan acceptance refs must be active in execution package")

    package_context_refs = {context_ref.value for context_ref in execution_package.context_refs}
    plan_context_refs = {context_ref.value for context_ref in plan.input_context_refs}
    if not plan_context_refs.issubset(package_context_refs):
        raise ValueError("input_context_refs must come from execution package")
    if plan.run_manifest_context_ref.value not in package_context_refs:
        raise ValueError("run_manifest_context_ref must be present in execution package")
    if plan.package_contract_ref.value not in package_context_refs:
        raise ValueError("package_contract_ref must be present in execution package")

    package_obligation_refs = {
        obligation.evidence_obligation_id.value
        for obligation in execution_package.evidence_obligations
    }
    plan_obligation_refs = {
        evidence_obligation_ref.value
        for evidence_obligation_ref in plan.evidence_obligation_refs
    }
    if not plan_obligation_refs.issubset(package_obligation_refs):
        raise ValueError(
            "plan evidence_obligation_refs must come from execution package"
        )
    return plan


def validate_blackbox_plan_approval(
    approval: BlackboxPlanApproval,
    *,
    plan: BlackboxVerificationPlan,
) -> BlackboxPlanApproval:
    if approval.plan_ref != plan.plan_id:
        raise ValueError("approval plan_ref must match plan")
    plan_action_ids = {action.action_id for action in plan.actions}
    approved_action_ids = set(approval.approved_action_ids)
    if not approved_action_ids.issubset(plan_action_ids):
        raise ValueError("approved action ids must exist in plan")
    return approval


def _resolve_provider_attempt(
    provider_attempt_ref: ProviderAttemptRef,
    provider_attempts: tuple[ProviderAttempt, ...],
) -> ProviderAttempt | None:
    matches = tuple(
        attempt
        for attempt in provider_attempts
        if attempt.provider_attempt_id == provider_attempt_ref
    )
    if len(matches) == 1:
        return matches[0]
    return None


__all__ = [
    "BlackboxPlanAction",
    "BlackboxPlanActionKind",
    "BlackboxPlanApproval",
    "BlackboxPlanApprovalRef",
    "BlackboxVerificationPlan",
    "BlackboxVerificationPlanRef",
    "validate_blackbox_plan_approval",
    "validate_blackbox_plan_lineage",
]
