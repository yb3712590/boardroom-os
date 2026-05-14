from enum import StrEnum
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, SkipValidation, ValidationInfo, field_validator, model_validator

from boardroom_os.contracts.directive import DirectiveRegistry
from boardroom_os.contracts.types import ContractId


class DeliveryType(StrEnum):
    GENERATED_PROJECT_PACKAGE = "generated_project_package"


class ProjectCharter(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", revalidate_instances="never")

    project_charter_id: ContractId
    board_directive_ref: ContractId
    project_goal: str
    delivery_type: DeliveryType
    non_goals: tuple[str, ...]
    constraints: tuple[str, ...]
    risks: tuple[str, ...]
    success_summary: str

    @field_validator("project_goal", "success_summary")
    @classmethod
    def _reject_empty_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("text fields must not be empty")
        return normalized

    @field_validator("non_goals", "constraints", "risks")
    @classmethod
    def _reject_empty_text_items(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(value.strip() for value in values)
        if any(not value for value in normalized):
            raise ValueError("text lists must not contain empty items")
        return normalized

    @model_validator(mode="after")
    def _require_registered_board_directive(self, info: ValidationInfo) -> Self:
        registry = info.context.get("directive_registry") if info.context else None
        if not isinstance(registry, DirectiveRegistry):
            raise ValueError("board directive registry is required")
        if not registry.contains(self.board_directive_ref):
            raise ValueError("board directive ref must exist")
        return self


class ProjectCharterRegistry(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    charters: tuple[SkipValidation[ProjectCharter], ...]

    @classmethod
    def from_charters(cls, *charters: ProjectCharter) -> Self:
        return cls(charters=charters)

    def contains(self, project_charter_ref: ContractId) -> bool:
        return any(
            charter.project_charter_id == project_charter_ref
            for charter in self.charters
        )


def create_project_charter(*, registry: DirectiveRegistry, **charter_fields: Any) -> ProjectCharter:
    return ProjectCharter.model_validate(
        charter_fields,
        context={"directive_registry": registry},
    )
