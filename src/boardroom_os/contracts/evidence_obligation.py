from pydantic import BaseModel, ConfigDict, StrictBool, field_serializer, field_validator

from boardroom_os.contracts.types import AcceptanceRef, EvidenceObligationRef, SourceSurfaceRef


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


class RequiredArtifactType(_NonEmptyTextValue):
    pass


class RequiredVerifier(_NonEmptyTextValue):
    pass


class EvidenceObligation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    evidence_obligation_id: EvidenceObligationRef
    acceptance_refs: tuple[AcceptanceRef, ...]
    source_surface_refs: tuple[SourceSurfaceRef, ...]
    required_artifact_type: RequiredArtifactType
    required_verifier: RequiredVerifier
    blocking: StrictBool

    @field_validator("acceptance_refs")
    @classmethod
    def _reject_empty_acceptance_refs(
        cls,
        values: tuple[AcceptanceRef, ...],
    ) -> tuple[AcceptanceRef, ...]:
        if not values:
            raise ValueError("acceptance refs must not be empty")
        return values

    @field_validator("source_surface_refs")
    @classmethod
    def _reject_empty_source_surface_refs(
        cls,
        values: tuple[SourceSurfaceRef, ...],
    ) -> tuple[SourceSurfaceRef, ...]:
        if not values:
            raise ValueError("source surface refs must not be empty")
        return values

    @field_serializer("acceptance_refs")
    def _serialize_acceptance_refs(
        self,
        values: tuple[AcceptanceRef, ...],
    ) -> list[dict[str, str]]:
        return [value.model_dump() for value in values]

    @field_serializer("source_surface_refs")
    def _serialize_source_surface_refs(
        self,
        values: tuple[SourceSurfaceRef, ...],
    ) -> list[dict[str, str]]:
        return [value.model_dump() for value in values]
