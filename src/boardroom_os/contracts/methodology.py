from enum import StrEnum
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, StrictBool, field_validator, model_validator

from boardroom_os.contracts.types import ContractId


class MethodologyTemplateKind(StrEnum):
    MINIMAL = "minimal"
    AGILE = "agile"
    COMPLIANCE = "compliance"
    HYBRID = "hybrid"


class DocumentationDensity(StrEnum):
    LIGHT = "light"
    STANDARD = "standard"
    HEAVY = "heavy"
    REGULATED = "regulated"


class DocumentationObligation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    obligation_id: ContractId
    artifact_name: str
    required: StrictBool
    audience: str
    purpose: str

    @field_validator("artifact_name", "audience", "purpose")
    @classmethod
    def _reject_empty_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("text fields must not be empty")
        return normalized


_DOCS_TEMPLATE_KEYS: dict[MethodologyTemplateKind, str] = {
    MethodologyTemplateKind.MINIMAL: "methodology/minimal",
    MethodologyTemplateKind.AGILE: "methodology/agile",
    MethodologyTemplateKind.COMPLIANCE: "methodology/compliance",
    MethodologyTemplateKind.HYBRID: "methodology/hybrid",
}


_DEFAULT_DOCUMENTATION_OBLIGATIONS: dict[
    MethodologyTemplateKind,
    tuple[tuple[str, str, str, str], ...],
] = {
    MethodologyTemplateKind.MINIMAL: (
        (
            "doc-minimal-readme",
            "README",
            "delivery-team",
            "capture the minimal setup and verification path",
        ),
    ),
    MethodologyTemplateKind.AGILE: (
        (
            "doc-agile-runbook",
            "Iteration Runbook",
            "delivery-team",
            "describe how to run and inspect the current increment",
        ),
    ),
    MethodologyTemplateKind.COMPLIANCE: (
        (
            "doc-compliance-evidence-pack",
            "Compliance Evidence Pack",
            "compliance-reviewers",
            "preserve auditable evidence for regulated delivery",
        ),
    ),
    MethodologyTemplateKind.HYBRID: (
        (
            "doc-hybrid-architecture",
            "Hybrid Architecture Notes",
            "delivery-reviewers",
            "summarize architecture, operations, and evidence touchpoints",
        ),
    ),
}


def docs_template_key_for(template_kind: MethodologyTemplateKind) -> str:
    return _DOCS_TEMPLATE_KEYS[template_kind]



def default_documentation_obligations_for(
    template_kind: MethodologyTemplateKind,
) -> tuple[DocumentationObligation, ...]:
    return tuple(
        DocumentationObligation(
            obligation_id=ContractId(value=obligation_id),
            artifact_name=artifact_name,
            required=True,
            audience=audience,
            purpose=purpose,
        )
        for obligation_id, artifact_name, audience, purpose in _DEFAULT_DOCUMENTATION_OBLIGATIONS[
            template_kind
        ]
    )


class MethodologyProfile(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", revalidate_instances="always")

    methodology_profile_id: ContractId
    project_charter_ref: ContractId
    template_kind: MethodologyTemplateKind
    documentation_density: DocumentationDensity
    docs_template_key: str
    documentation_obligations: tuple[DocumentationObligation, ...]

    @field_validator("docs_template_key")
    @classmethod
    def _reject_empty_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("docs_template_key must not be empty")
        return normalized

    @field_validator("documentation_obligations")
    @classmethod
    def _require_documentation_obligations(
        cls,
        values: tuple[DocumentationObligation, ...],
    ) -> tuple[DocumentationObligation, ...]:
        if not values:
            raise ValueError("documentation_obligations must not be empty")
        return values

    @model_validator(mode="after")
    def _reject_invalid_template_density_combinations(self) -> Self:
        if (
            self.template_kind == MethodologyTemplateKind.MINIMAL
            and self.documentation_density == DocumentationDensity.REGULATED
        ):
            raise ValueError("minimal methodology cannot use regulated documentation density")
        if (
            self.template_kind == MethodologyTemplateKind.COMPLIANCE
            and self.documentation_density == DocumentationDensity.LIGHT
        ):
            raise ValueError("compliance methodology cannot use light documentation density")
        return self


class MethodologyProfileRegistry(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    profiles: tuple[MethodologyProfile, ...]

    @classmethod
    def from_profiles(cls, *profiles: MethodologyProfile) -> Self:
        return cls(profiles=profiles)

    @model_validator(mode="before")
    @classmethod
    def _validate_profiles(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data

        profiles = cls._materialize_profiles(data.get("profiles"))
        if not profiles:
            raise ValueError("profiles must not be empty")

        seen_profile_ids: set[ContractId] = set()
        validated_profiles: list[MethodologyProfile] = []
        for profile in profiles:
            normalized_profile = cls._normalize_profile_value(profile)
            validated_profile = MethodologyProfile.model_validate(normalized_profile)
            if validated_profile.methodology_profile_id in seen_profile_ids:
                raise ValueError("methodology_profile_id values must be unique")
            seen_profile_ids.add(validated_profile.methodology_profile_id)
            validated_profiles.append(validated_profile)

        return {**data, "profiles": tuple(validated_profiles)}

    @staticmethod
    def _materialize_profiles(profiles: object) -> tuple[object, ...]:
        try:
            return tuple(profiles)  # type: ignore[arg-type]
        except TypeError as exc:
            raise ValueError("profiles must be iterable") from exc

    @classmethod
    def _normalize_profile_value(cls, value: object) -> object:
        if isinstance(value, BaseModel):
            return cls._normalize_profile_value(value.model_dump(warnings=False))
        if isinstance(value, dict):
            return {
                key: cls._normalize_profile_value(item)
                for key, item in value.items()
            }
        if isinstance(value, (list, tuple)):
            return tuple(cls._normalize_profile_value(item) for item in value)
        return value

    def contains(self, methodology_profile_ref: ContractId) -> bool:
        return self.get(methodology_profile_ref) is not None

    def get(self, methodology_profile_ref: ContractId) -> MethodologyProfile | None:
        return next(
            (
                profile
                for profile in self.profiles
                if profile.methodology_profile_id == methodology_profile_ref
            ),
            None,
        )
