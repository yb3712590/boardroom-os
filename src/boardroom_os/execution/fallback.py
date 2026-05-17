from __future__ import annotations

from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from boardroom_os.contracts.evidence_obligation import RequiredArtifactType
from boardroom_os.contracts.types import AcceptanceRef
from boardroom_os.execution.package import FallbackPolicyRef


class EvidencePurpose(StrEnum):
    IMPLEMENTATION = "implementation"
    DIAGNOSTIC = "diagnostic"
    DETERMINISTIC = "deterministic"


class FallbackKind(StrEnum):
    DETERMINISTIC_GOVERNANCE_DRAFT = "DETERMINISTIC_GOVERNANCE_DRAFT"
    TOOLING_PREFLIGHT = "TOOLING_PREFLIGHT"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    TEST_ONLY_SIMULATION = "TEST_ONLY_SIMULATION"
    CONTRACT_ALLOWED_DETERMINISTIC_TRANSFORM = "CONTRACT_ALLOWED_DETERMINISTIC_TRANSFORM"


class FallbackPolicy(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    fallback_policy_ref: FallbackPolicyRef
    kind: FallbackKind
    allowed_artifact_types: tuple[RequiredArtifactType, ...] = ()
    allowed_acceptance_refs: tuple[AcceptanceRef, ...] = ()

    @model_validator(mode="after")
    def _validate_allow_lists(self) -> Self:
        if self.kind is FallbackKind.CONTRACT_ALLOWED_DETERMINISTIC_TRANSFORM:
            if not self.allowed_artifact_types:
                raise ValueError(
                    "deterministic transform policies require allowed artifact types"
                )
            if not self.allowed_acceptance_refs:
                raise ValueError(
                    "deterministic transform policies require allowed acceptance refs"
                )
            return self
        if self.allowed_artifact_types or self.allowed_acceptance_refs:
            raise ValueError(
                "only contract-allowed deterministic transform policies may declare allow lists"
            )
        return self


class FallbackEvidenceRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    purpose: EvidencePurpose
    artifact_type: RequiredArtifactType
    acceptance_refs: tuple[AcceptanceRef, ...]

    @field_validator("acceptance_refs")
    @classmethod
    def _reject_empty_acceptance_refs(
        cls,
        values: tuple[AcceptanceRef, ...],
    ) -> tuple[AcceptanceRef, ...]:
        if not values:
            raise ValueError("acceptance_refs must not be empty")
        return values


class FallbackEvidenceDecision(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    fallback_policy_ref: FallbackPolicyRef
    applied_kind: FallbackKind
    evaluated_purpose: EvidencePurpose
    allowed: bool
    blocking_reasons: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _validate_reasons(self) -> Self:
        if self.allowed and self.blocking_reasons:
            raise ValueError("allowed fallback decisions must not include blocking reasons")
        if not self.allowed and not self.blocking_reasons:
            raise ValueError("blocked fallback decisions must include blocking reasons")
        return self


def evaluate_fallback_evidence(
    *,
    policy: FallbackPolicy,
    request: FallbackEvidenceRequest,
) -> FallbackEvidenceDecision:
    blocking_reasons: list[str] = []

    if request.purpose is EvidencePurpose.IMPLEMENTATION:
        blocking_reasons.append("implementation evidence cannot be satisfied by fallback")

    if policy.kind is FallbackKind.TOOLING_PREFLIGHT:
        if request.purpose is not EvidencePurpose.DIAGNOSTIC:
            blocking_reasons.append("tooling preflight fallback is diagnostic only")
    elif policy.kind is FallbackKind.CONTRACT_ALLOWED_DETERMINISTIC_TRANSFORM:
        if request.purpose is not EvidencePurpose.DETERMINISTIC:
            blocking_reasons.append(
                "deterministic transform can satisfy only deterministic evidence"
            )

        allowed_artifact_types = {
            artifact_type.value for artifact_type in policy.allowed_artifact_types
        }
        if request.artifact_type.value not in allowed_artifact_types:
            blocking_reasons.append("artifact_type is outside fallback policy scope")

        allowed_acceptance_refs = {
            acceptance_ref.value for acceptance_ref in policy.allowed_acceptance_refs
        }
        request_acceptance_refs = {
            acceptance_ref.value for acceptance_ref in request.acceptance_refs
        }
        if not request_acceptance_refs.issubset(allowed_acceptance_refs):
            blocking_reasons.append("acceptance_refs are outside fallback policy scope")
    else:
        blocking_reasons.append(
            f"fallback kind cannot satisfy evidence: {policy.kind.value}"
        )

    if blocking_reasons:
        return FallbackEvidenceDecision(
            fallback_policy_ref=policy.fallback_policy_ref,
            applied_kind=policy.kind,
            evaluated_purpose=request.purpose,
            allowed=False,
            blocking_reasons=tuple(dict.fromkeys(blocking_reasons)),
        )

    return FallbackEvidenceDecision(
        fallback_policy_ref=policy.fallback_policy_ref,
        applied_kind=policy.kind,
        evaluated_purpose=request.purpose,
        allowed=True,
    )


__all__ = [
    "EvidencePurpose",
    "FallbackKind",
    "FallbackPolicy",
    "FallbackEvidenceRequest",
    "FallbackEvidenceDecision",
    "evaluate_fallback_evidence",
]
