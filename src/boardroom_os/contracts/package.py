from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, StrictBool, field_serializer, field_validator, model_validator

from boardroom_os.contracts.source_surface import SourceSurface
from boardroom_os.contracts.types import ContractId


class PackageProjectType(StrEnum):
    SOFTWARE = "software"
    DOCUMENTATION = "documentation"
    MIXED = "mixed"


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


class IntegrationBoundary(_NonEmptyTextValue):
    pass


class PackageCommand(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    command_id: ContractId
    label: str
    command: tuple[str, ...]
    cwd: str

    @field_validator("label", "cwd")
    @classmethod
    def _reject_empty_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("text fields must not be empty")
        return normalized

    @field_validator("command")
    @classmethod
    def _reject_empty_command(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(value.strip() for value in values)
        if not normalized:
            raise ValueError("command must not be empty")
        if any(not value for value in normalized):
            raise ValueError("command must not contain empty items")
        return normalized


class PackageContract(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    package_contract_id: ContractId
    project_charter_ref: ContractId
    package_root: str
    project_type: PackageProjectType
    source_surfaces: tuple[SourceSurface, ...]
    run_commands: tuple[PackageCommand, ...]
    test_commands: tuple[PackageCommand, ...]
    integration_boundaries: tuple[IntegrationBoundary, ...]
    docs_required: StrictBool
    closeout_required: StrictBool

    @field_validator("package_root")
    @classmethod
    def _reject_empty_package_root(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("package root must not be empty")
        return normalized

    @field_validator("source_surfaces")
    @classmethod
    def _reject_empty_source_surfaces(
        cls,
        values: tuple[SourceSurface, ...],
    ) -> tuple[SourceSurface, ...]:
        if not values:
            raise ValueError("source surfaces must not be empty")
        return values

    @field_serializer("source_surfaces")
    def _serialize_source_surfaces(
        self,
        values: tuple[SourceSurface, ...],
    ) -> list[dict[str, object]]:
        return [value.model_dump() for value in values]

    @field_serializer("run_commands", "test_commands")
    def _serialize_commands(
        self,
        values: tuple[PackageCommand, ...],
    ) -> list[dict[str, object]]:
        return [value.model_dump() for value in values]

    @field_serializer("integration_boundaries")
    def _serialize_integration_boundaries(
        self,
        values: tuple[IntegrationBoundary, ...],
    ) -> list[dict[str, str]]:
        return [value.model_dump() for value in values]

    @model_validator(mode="after")
    def _require_commands_for_runnable_packages(self) -> Self:
        if self.project_type in {PackageProjectType.SOFTWARE, PackageProjectType.MIXED}:
            if not self.run_commands:
                raise ValueError("software and mixed packages require run commands")
            if not self.test_commands:
                raise ValueError("software and mixed packages require test commands")
        return self
