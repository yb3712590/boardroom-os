from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, field_serializer, field_validator


class _NonEmptyValue(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    value: str

    @field_validator("value")
    @classmethod
    def _reject_empty_value(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("value must not be empty")
        return normalized


class ContractId(_NonEmptyValue):
    pass


class AcceptanceRef(_NonEmptyValue):
    pass


class SourceSurfaceRef(_NonEmptyValue):
    pass


class EvidenceObligationRef(_NonEmptyValue):
    pass


class NonEmptyTextValue(_NonEmptyValue):
    pass


class AcceptanceRefSet(BaseModel):
    model_config = ConfigDict(frozen=True)

    refs: tuple[AcceptanceRef, ...]

    @field_validator("refs")
    @classmethod
    def _reject_empty_refs(cls, refs: tuple[AcceptanceRef, ...]) -> tuple[AcceptanceRef, ...]:
        if not refs:
            raise ValueError("acceptance refs must not be empty")
        return refs

    @field_serializer("refs")
    def _serialize_refs(self, refs: tuple[AcceptanceRef, ...]) -> list[dict[str, str]]:
        return [ref.model_dump() for ref in refs]

    def as_tuple(self) -> tuple[str, ...]:
        return tuple(ref.value for ref in self.refs)


class _StatusValue(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    RETIRED = "retired"


class ContractStatus(BaseModel):
    model_config = ConfigDict(frozen=True, use_enum_values=True)

    value: _StatusValue

    @classmethod
    def draft(cls) -> Self:
        return cls(value=_StatusValue.DRAFT)

    @classmethod
    def active(cls) -> Self:
        return cls(value=_StatusValue.ACTIVE)

    @classmethod
    def retired(cls) -> Self:
        return cls(value=_StatusValue.RETIRED)
