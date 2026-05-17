from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from boardroom_os.agents.profiles import ModelExecutionProfile
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


class ExecutionPackage(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    version: Literal[1] = 1
    execution_package_id: ExecutionPackageId
    ticket_ref: TicketId
    graph_version: int = Field(gt=0)
    seat_ref: AgentSeatRef
    model_execution_profile: ModelExecutionProfile
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
        "allowed_write_set",
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
