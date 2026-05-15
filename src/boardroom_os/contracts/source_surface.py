from pydantic import BaseModel, ConfigDict, field_serializer, field_validator

from boardroom_os.contracts.types import AcceptanceRef, NonEmptyTextValue, SourceSurfaceRef


class OwnerSeatRef(NonEmptyTextValue):
    pass


class RequiredTestRef(NonEmptyTextValue):
    pass


class SourceSurface(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    source_surface_ref: SourceSurfaceRef
    name: str
    paths: tuple[str, ...]
    owned_by: OwnerSeatRef
    acceptance_refs: tuple[AcceptanceRef, ...]
    required_tests: tuple[RequiredTestRef, ...]

    @field_validator("name")
    @classmethod
    def _reject_empty_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("name must not be empty")
        return normalized

    @field_validator("paths")
    @classmethod
    def _reject_empty_paths(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(value.strip() for value in values)
        if not normalized:
            raise ValueError("paths must not be empty")
        if any(not value for value in normalized):
            raise ValueError("paths must not contain empty items")
        return normalized

    @field_validator("acceptance_refs")
    @classmethod
    def _reject_empty_acceptance_refs(
        cls,
        values: tuple[AcceptanceRef, ...],
    ) -> tuple[AcceptanceRef, ...]:
        if not values:
            raise ValueError("acceptance refs must not be empty")
        return values

    @field_serializer("acceptance_refs")
    def _serialize_acceptance_refs(
        self,
        values: tuple[AcceptanceRef, ...],
    ) -> list[dict[str, str]]:
        return [value.model_dump() for value in values]

    @field_serializer("required_tests")
    def _serialize_required_tests(
        self,
        values: tuple[RequiredTestRef, ...],
    ) -> list[dict[str, str]]:
        return [value.model_dump() for value in values]
