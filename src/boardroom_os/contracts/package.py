from enum import StrEnum
from typing import Any, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    StrictBool,
    ValidationInfo,
    field_serializer,
    field_validator,
    model_validator,
)

from boardroom_os.contracts.methodology import (
    DocumentationObligation,
    MethodologyProfileRegistry,
)
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
    methodology_profile_ref: ContractId | None = None
    docs_template_key: str | None = None
    documentation_obligations: tuple[DocumentationObligation, ...] = ()

    @field_validator("package_root")
    @classmethod
    def _reject_empty_package_root(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("package root must not be empty")
        return normalized

    @field_validator("docs_template_key")
    @classmethod
    def _reject_empty_docs_template_key(cls, value: str | None) -> str | None:
        if value is None:
            return value
        normalized = value.strip()
        if not normalized:
            raise ValueError("docs_template_key must not be empty")
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

    @field_serializer("documentation_obligations")
    def _serialize_documentation_obligations(
        self,
        values: tuple[DocumentationObligation, ...],
    ) -> list[dict[str, object]]:
        return [value.model_dump() for value in values]

    @model_validator(mode="after")
    def _validate_package_contract(self, info: ValidationInfo) -> Self:
        self._validate_runnable_commands()
        self._validate_documentation_binding()
        self._validate_methodology_registry_binding(info)
        return self

    def _validate_runnable_commands(self) -> None:
        if self.project_type not in {PackageProjectType.SOFTWARE, PackageProjectType.MIXED}:
            return
        if not self.run_commands:
            raise ValueError("software and mixed packages require run commands")
        if not self.test_commands:
            raise ValueError("software and mixed packages require test commands")

    def _validate_documentation_binding(self) -> None:
        if self.docs_required:
            if self.methodology_profile_ref is None:
                raise ValueError("methodology_profile_ref is required when docs_required is true")
            if self.docs_template_key is None:
                raise ValueError("docs_template_key is required when docs_required is true")
            if not self.documentation_obligations:
                raise ValueError("documentation_obligations are required when docs_required is true")

        if not self.docs_required and any(
            obligation.required for obligation in self.documentation_obligations
        ):
            raise ValueError(
                "documentation_obligations cannot include required items when docs_required is false"
            )

    def _validate_methodology_registry_binding(self, info: ValidationInfo) -> None:
        registry = info.context.get("methodology_registry") if info.context else None
        if registry is None:
            if self.docs_required:
                raise ValueError("methodology registry is required when docs_required is true")
            return
        if not isinstance(registry, MethodologyProfileRegistry):
            raise ValueError("methodology registry is invalid")
        if self.methodology_profile_ref is None:
            raise ValueError("methodology_profile_ref is required when methodology registry is provided")

        profile = registry.get(self.methodology_profile_ref)
        if profile is None:
            raise ValueError("methodology_profile_ref must exist in methodology registry")
        if self.project_charter_ref != profile.project_charter_ref:
            raise ValueError("project_charter_ref must match the methodology profile")
        if self.docs_template_key != profile.docs_template_key:
            raise ValueError("docs_template_key must match the methodology profile")
        if self.documentation_obligations != profile.documentation_obligations:
            raise ValueError("documentation_obligations must match the methodology profile")


def create_package_contract(*, methodology_registry: MethodologyProfileRegistry, **contract_fields: Any) -> PackageContract:
    return PackageContract.model_validate(
        contract_fields,
        context={"methodology_registry": methodology_registry},
    )
