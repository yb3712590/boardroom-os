from __future__ import annotations

from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from boardroom_os.agents.categories import RoleCategory
from boardroom_os.agents.profiles import ModelExecutionProfile
from boardroom_os.agents.role_prompt_hooks import RolePromptHook
from boardroom_os.agents.seat import AgentSeatRef
from boardroom_os.agents.skills import _normalize_ref_fields
from boardroom_os.contracts.evidence_obligation import EvidenceObligation
from boardroom_os.contracts.package import PackageCommand
from boardroom_os.contracts.types import (
    AcceptanceRef,
    NonEmptyTextValue,
    SourceSurfaceRef,
)
from boardroom_os.graph.ticket import TicketId


class ExecutionPackageId(NonEmptyTextValue):
    pass


class ExecutionPackageRef(NonEmptyTextValue):
    pass


class ContextRef(NonEmptyTextValue):
    pass


class AllowedReadRef(NonEmptyTextValue):
    pass


class AllowedWritePath(NonEmptyTextValue):
    pass


class RequiredOutput(NonEmptyTextValue):
    pass


class AuditRequirement(NonEmptyTextValue):
    pass


class FallbackPolicyRef(NonEmptyTextValue):
    pass


def validate_execution_package_write_boundary(
    *,
    role_prompt_hook: RolePromptHook,
    context_refs: tuple[ContextRef, ...],
    allowed_read_refs: tuple[AllowedReadRef, ...],
    allowed_write_set: tuple[AllowedWritePath, ...],
    ticket_ref: TicketId,
    graph_version: int,
) -> None:
    if allowed_write_set:
        return
    if role_prompt_hook.role_category is not RoleCategory.VERIFICATION:
        raise ValueError(
            "read-only execution packages require verification role prompt hook"
        )
    if not allowed_read_refs:
        raise ValueError("read-only execution packages require allowed_read_refs")

    allowed_read_values = {allowed_read_ref.value for allowed_read_ref in allowed_read_refs}
    unauthorized_context_refs = tuple(
        context_ref.value
        for context_ref in context_refs
        if not _is_authorized_read_only_context_ref(
            context_ref.value,
            allowed_read_values=allowed_read_values,
            ticket_ref=ticket_ref,
            graph_version=graph_version,
        )
    )
    if unauthorized_context_refs:
        raise ValueError(
            "context_refs must be covered by allowed_read_refs for read-only execution packages: "
            + ", ".join(unauthorized_context_refs)
        )


def _is_authorized_read_only_context_ref(
    value: str,
    *,
    allowed_read_values: set[str],
    ticket_ref: TicketId,
    graph_version: int,
) -> bool:
    if value in allowed_read_values:
        return True
    if value == ticket_ref.value:
        return True
    if value == f"context.agent-team-projection.graph-version-{graph_version}":
        return True
    return False


class ExecutionPackage(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    version: Literal[1] = 1
    execution_package_id: ExecutionPackageId
    ticket_ref: TicketId
    graph_version: int = Field(gt=0)
    seat_ref: AgentSeatRef
    model_execution_profile: ModelExecutionProfile
    role_prompt_hook: RolePromptHook
    objective: str
    context_refs: tuple[ContextRef, ...]
    constraints: tuple[str, ...]
    acceptance_refs: tuple[AcceptanceRef, ...]
    source_surface_refs: tuple[SourceSurfaceRef, ...]
    allowed_read_refs: tuple[AllowedReadRef, ...] = ()
    # SourceSurface 路径边界需要 active PackageContract，由 V2-030D 编译器校验。
    allowed_write_set: tuple[AllowedWritePath, ...]
    required_outputs: tuple[RequiredOutput, ...]
    commands: tuple[PackageCommand, ...]
    # 完整对象供 worker / checker 按 required_artifact_type 与 blocking 做执行决策。
    evidence_obligations: tuple[EvidenceObligation, ...]
    # 本字段是 V2-030D 固化后的实际策略，不在 schema 层比对 profile 默认值。
    fallback_policy_ref: FallbackPolicyRef
    audit_requirements: tuple[AuditRequirement, ...]

    @model_validator(mode="before")
    @classmethod
    def _normalize_yaml_refs(cls, data: Any) -> Any:
        return _normalize_ref_fields(
            data,
            {
                "execution_package_id": ExecutionPackageId,
                "ticket_ref": TicketId,
                "seat_ref": AgentSeatRef,
                "fallback_policy_ref": FallbackPolicyRef,
            },
            {
                "context_refs": ContextRef,
                "acceptance_refs": AcceptanceRef,
                "source_surface_refs": SourceSurfaceRef,
                "allowed_read_refs": AllowedReadRef,
                "allowed_write_set": AllowedWritePath,
                "required_outputs": RequiredOutput,
                "audit_requirements": AuditRequirement,
            },
        )

    @field_validator("objective")
    @classmethod
    def _reject_empty_objective(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("objective must not be empty")
        return normalized

    @field_validator("constraints")
    @classmethod
    def _reject_empty_constraints(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if not values:
            raise ValueError("constraints must not be empty")
        normalized_values = tuple(value.strip() for value in values)
        if any(not value for value in normalized_values):
            raise ValueError("constraints must not contain empty values")
        return normalized_values

    @field_validator(
        "context_refs",
        "acceptance_refs",
        "source_surface_refs",
        "required_outputs",
        "commands",
        "evidence_obligations",
        "audit_requirements",
    )
    @classmethod
    def _reject_empty_required_tuples(cls, values: tuple[object, ...]) -> tuple[object, ...]:
        if not values:
            raise ValueError("required tuple must not be empty")
        return values

    @model_validator(mode="after")
    def _require_write_scope_for_writable_packages(self) -> Self:
        validate_execution_package_write_boundary(
            role_prompt_hook=self.role_prompt_hook,
            context_refs=self.context_refs,
            allowed_read_refs=self.allowed_read_refs,
            allowed_write_set=self.allowed_write_set,
            ticket_ref=self.ticket_ref,
            graph_version=self.graph_version,
        )
        return self


__all__ = [
    "AllowedReadRef",
    "AllowedWritePath",
    "AuditRequirement",
    "ContextRef",
    "ExecutionPackage",
    "ExecutionPackageId",
    "ExecutionPackageRef",
    "FallbackPolicyRef",
    "RequiredOutput",
    "validate_execution_package_write_boundary",
]
