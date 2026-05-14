from typing import Any, Self

from pydantic import BaseModel, ConfigDict, ValidationInfo, field_serializer, field_validator, model_validator

from boardroom_os.contracts.project import ProjectCharterRegistry
from boardroom_os.contracts.types import AcceptanceRef, ContractId, ContractStatus, SourceSurfaceRef


class _NonEmptyTextValue(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    value: str

    @field_validator("value")
    @classmethod
    def _reject_empty_value(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("value must not be empty")
        return normalized


class EvidenceRequirement(_NonEmptyTextValue):
    pass


class VerificationStrategy(_NonEmptyTextValue):
    pass


class AcceptanceCriterion(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    acceptance_ref: AcceptanceRef
    statement: str
    evidence_required: tuple[EvidenceRequirement, ...]
    blocking: bool
    source_surface_refs: tuple[SourceSurfaceRef, ...]
    verification_strategy: VerificationStrategy

    @field_validator("statement")
    @classmethod
    def _reject_empty_statement(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("statement must not be empty")
        return normalized

    @field_validator("evidence_required")
    @classmethod
    def _reject_empty_evidence_required(
        cls,
        values: tuple[EvidenceRequirement, ...],
    ) -> tuple[EvidenceRequirement, ...]:
        if not values:
            raise ValueError("evidence required must not be empty")
        return values

    @field_serializer("evidence_required")
    def _serialize_evidence_required(
        self,
        values: tuple[EvidenceRequirement, ...],
    ) -> list[dict[str, str]]:
        return [value.model_dump() for value in values]

    @field_validator("source_surface_refs")
    @classmethod
    def _reject_empty_source_surface_refs(
        cls,
        values: tuple[SourceSurfaceRef, ...],
    ) -> tuple[SourceSurfaceRef, ...]:
        if not values:
            raise ValueError("source surface refs must not be empty")
        return values

    @field_serializer("source_surface_refs")
    def _serialize_source_surface_refs(
        self,
        values: tuple[SourceSurfaceRef, ...],
    ) -> list[dict[str, str]]:
        return [value.model_dump() for value in values]


class AcceptanceContract(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    acceptance_contract_id: ContractId
    project_charter_ref: ContractId
    status: ContractStatus
    criteria: tuple[AcceptanceCriterion, ...]

    @field_validator("criteria")
    @classmethod
    def _reject_empty_or_non_blocking_criteria(
        cls,
        values: tuple[AcceptanceCriterion, ...],
    ) -> tuple[AcceptanceCriterion, ...]:
        if not values:
            raise ValueError("criteria must not be empty")
        if not any(criterion.blocking for criterion in values):
            raise ValueError("at least one blocking criterion is required")
        return values

    @field_serializer("criteria")
    def _serialize_criteria(
        self,
        values: tuple[AcceptanceCriterion, ...],
    ) -> list[dict[str, object]]:
        return [value.model_dump() for value in values]

    @model_validator(mode="after")
    def _require_registered_project_charter(self, info: ValidationInfo) -> Self:
        registry = info.context.get("project_charter_registry") if info.context else None
        if not isinstance(registry, ProjectCharterRegistry):
            raise ValueError("project charter registry is required")
        if not registry.contains(self.project_charter_ref):
            raise ValueError("project charter ref must exist")
        return self

    def blocking_criteria(self) -> tuple[AcceptanceCriterion, ...]:
        if self.status.value != "active":
            return ()
        return tuple(criterion for criterion in self.criteria if criterion.blocking)


def create_acceptance_contract(
    *,
    registry: ProjectCharterRegistry,
    **contract_fields: Any,
) -> AcceptanceContract:
    return AcceptanceContract.model_validate(
        contract_fields,
        context={"project_charter_registry": registry},
    )
