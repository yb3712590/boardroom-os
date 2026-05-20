from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from boardroom_os.agents.skills import _normalize_ref_fields
from boardroom_os.contracts.evidence_obligation import RequiredArtifactType
from boardroom_os.contracts.types import AcceptanceRef, NonEmptyTextValue
from boardroom_os.evidence.claim import EvidenceClaim, EvidenceClaimRef
from boardroom_os.execution.context_index import ProviderAttemptRef
from boardroom_os.execution.fallback import (
    EvidencePurpose,
    FallbackEvidenceDecision,
    FallbackEvidenceRequest,
    FallbackKind,
    FallbackPolicy,
    evaluate_fallback_evidence,
)
from boardroom_os.execution.package import FallbackPolicyRef


class FallbackRegistryError(ValueError):
    pass


class FallbackDecisionRecordRef(NonEmptyTextValue):
    pass


_DANGEROUS_EVIDENCE_POLICY_KINDS = frozenset(
    {
        FallbackKind.PROVIDER_UNAVAILABLE,
        FallbackKind.TEST_ONLY_SIMULATION,
        FallbackKind.DETERMINISTIC_GOVERNANCE_DRAFT,
    }
)

_TUPLE_REF_FIELDS = ("acceptance_refs",)


def _reject_malformed_tuple_ref_inputs(data: Any) -> Any:
    if not isinstance(data, dict):
        return data
    for field_name in _TUPLE_REF_FIELDS:
        if field_name in data and not isinstance(data[field_name], list | tuple):
            raise ValueError(f"{field_name} must be a tuple or list")
    return data


class FallbackPolicyRegistry(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    policies: tuple[FallbackPolicy, ...]

    @model_validator(mode="after")
    def _validate_policies(self) -> Self:
        if not self.policies:
            raise ValueError("policies must not be empty")

        seen_policy_refs: set[str] = set()
        for policy in self.policies:
            policy_ref_value = policy.fallback_policy_ref.value
            if policy_ref_value in seen_policy_refs:
                raise ValueError("fallback_policy_ref values must be unique")
            seen_policy_refs.add(policy_ref_value)

            if policy.kind in _DANGEROUS_EVIDENCE_POLICY_KINDS:
                raise FallbackRegistryError(
                    f"{policy.kind.value} cannot be registered as evidence policy"
                )
        return self

    def resolve(self, fallback_policy_ref: FallbackPolicyRef) -> FallbackPolicy:
        if not isinstance(fallback_policy_ref, FallbackPolicyRef):
            raise FallbackRegistryError(
                "fallback_policy_ref must be a FallbackPolicyRef"
            )

        for policy in self.policies:
            if policy.fallback_policy_ref == fallback_policy_ref:
                return policy

        raise FallbackRegistryError(
            f"cannot resolve unknown fallback_policy_ref: {fallback_policy_ref.value}"
        )


class FallbackDecisionRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    version: Literal[1] = 1
    fallback_decision_record_id: FallbackDecisionRecordRef
    evidence_claim_ref: EvidenceClaimRef
    producer_attempt_ref: ProviderAttemptRef
    fallback_policy_ref: FallbackPolicyRef
    fallback_kind: FallbackKind
    evaluated_purpose: EvidencePurpose
    required_artifact_type: RequiredArtifactType
    acceptance_refs: tuple[AcceptanceRef, ...]
    decision: FallbackEvidenceDecision
    evaluated_at: datetime

    @model_validator(mode="before")
    @classmethod
    def _normalize_yaml_refs(cls, data: Any) -> Any:
        data = _reject_malformed_tuple_ref_inputs(data)
        return _normalize_ref_fields(
            data,
            {
                "fallback_decision_record_id": FallbackDecisionRecordRef,
                "evidence_claim_ref": EvidenceClaimRef,
                "producer_attempt_ref": ProviderAttemptRef,
                "fallback_policy_ref": FallbackPolicyRef,
                "required_artifact_type": RequiredArtifactType,
            },
            {
                "acceptance_refs": AcceptanceRef,
            },
        )

    @field_validator("acceptance_refs")
    @classmethod
    def _reject_empty_acceptance_refs(
        cls,
        values: tuple[AcceptanceRef, ...],
    ) -> tuple[AcceptanceRef, ...]:
        if not values:
            raise ValueError("acceptance_refs must not be empty")
        return values

    @field_validator("evaluated_at")
    @classmethod
    def _require_timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("evaluated_at must be timezone-aware")
        return value

    @model_validator(mode="after")
    def _validate_decision_alignment(self) -> Self:
        if self.decision.fallback_policy_ref != self.fallback_policy_ref:
            raise ValueError(
                "decision.fallback_policy_ref must match fallback_policy_ref"
            )
        if self.decision.applied_kind != self.fallback_kind:
            raise ValueError("decision.applied_kind must match fallback_kind")
        if self.decision.evaluated_purpose != self.evaluated_purpose:
            raise ValueError(
                "decision.evaluated_purpose must match evaluated_purpose"
            )
        return self


def evaluate_fallback_claim(
    *,
    claim: EvidenceClaim,
    registry: FallbackPolicyRegistry,
    evaluated_at: datetime,
    decision_record_id: FallbackDecisionRecordRef | None = None,
) -> FallbackDecisionRecord:
    if not isinstance(registry, FallbackPolicyRegistry):
        raise FallbackRegistryError("registry must be a FallbackPolicyRegistry")

    fallback_marker = claim.fallback_marker
    if fallback_marker is None:
        raise FallbackRegistryError("claim.fallback_marker is required")

    policy = registry.resolve(fallback_marker.fallback_policy_ref)
    if fallback_marker.fallback_kind is not policy.kind:
        raise FallbackRegistryError(
            "fallback_kind and policy kind mismatch: "
            f"{fallback_marker.fallback_kind.value} != {policy.kind.value}"
        )

    decision = evaluate_fallback_evidence(
        policy=policy,
        request=FallbackEvidenceRequest(
            purpose=claim.expected_purpose,
            artifact_type=claim.required_artifact_type,
            acceptance_refs=claim.acceptance_refs,
        ),
    )

    resolved_record_id = decision_record_id or FallbackDecisionRecordRef(
        value=(
            "fallback-decision."
            f"{claim.evidence_claim_id.value}."
            f"{fallback_marker.fallback_policy_ref.value}"
        )
    )
    return FallbackDecisionRecord(
        fallback_decision_record_id=resolved_record_id,
        evidence_claim_ref=claim.evidence_claim_id,
        producer_attempt_ref=claim.producer_attempt_ref,
        fallback_policy_ref=fallback_marker.fallback_policy_ref,
        fallback_kind=fallback_marker.fallback_kind,
        evaluated_purpose=claim.expected_purpose,
        required_artifact_type=claim.required_artifact_type,
        acceptance_refs=claim.acceptance_refs,
        decision=decision,
        evaluated_at=evaluated_at,
    )


__all__ = [
    "FallbackDecisionRecord",
    "FallbackDecisionRecordRef",
    "FallbackPolicyRegistry",
    "FallbackRegistryError",
    "evaluate_fallback_claim",
]
