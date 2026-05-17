import pytest
from pydantic import ValidationError

from boardroom_os.contracts.evidence_obligation import RequiredArtifactType
from boardroom_os.contracts.types import AcceptanceRef
from boardroom_os.execution.fallback import (
    EvidencePurpose,
    FallbackEvidenceDecision,
    FallbackEvidenceRequest,
    FallbackKind,
    FallbackPolicy,
    evaluate_fallback_evidence,
)
from boardroom_os.execution.package import FallbackPolicyRef


ALWAYS_BLOCKED_FALLBACK_KINDS = (
    FallbackKind.PROVIDER_UNAVAILABLE,
    FallbackKind.TEST_ONLY_SIMULATION,
    FallbackKind.DETERMINISTIC_GOVERNANCE_DRAFT,
)

NON_CONTRACT_FALLBACK_KINDS = ALWAYS_BLOCKED_FALLBACK_KINDS + (
    FallbackKind.TOOLING_PREFLIGHT,
)


def _policy(kind: FallbackKind) -> FallbackPolicy:
    if kind is FallbackKind.CONTRACT_ALLOWED_DETERMINISTIC_TRANSFORM:
        return FallbackPolicy(
            fallback_policy_ref=FallbackPolicyRef(value="fallback.hash-manifest"),
            kind=kind,
            allowed_artifact_types=(RequiredArtifactType(value="hash_manifest"),),
            allowed_acceptance_refs=(AcceptanceRef(value="AC-FALLBACK-DETERMINISTIC"),),
        )
    return FallbackPolicy(
        fallback_policy_ref=FallbackPolicyRef(value=f"fallback.{kind.value.lower()}"),
        kind=kind,
    )


def _request(purpose: EvidencePurpose) -> FallbackEvidenceRequest:
    return FallbackEvidenceRequest(
        purpose=purpose,
        artifact_type=RequiredArtifactType(value="hash_manifest"),
        acceptance_refs=(AcceptanceRef(value="AC-FALLBACK-DETERMINISTIC"),),
    )


@pytest.mark.parametrize("kind", ALWAYS_BLOCKED_FALLBACK_KINDS)
def test_always_blocked_fallback_kinds_cannot_satisfy_implementation_evidence(
    kind: FallbackKind,
) -> None:
    policy = _policy(kind)

    decision = evaluate_fallback_evidence(
        policy=policy,
        request=_request(EvidencePurpose.IMPLEMENTATION),
    )

    assert decision == FallbackEvidenceDecision(
        fallback_policy_ref=policy.fallback_policy_ref,
        applied_kind=kind,
        evaluated_purpose=EvidencePurpose.IMPLEMENTATION,
        allowed=False,
        blocking_reasons=(
            "implementation evidence cannot be satisfied by fallback",
            f"fallback kind cannot satisfy evidence: {kind.value}",
        ),
    )


def test_tooling_preflight_cannot_satisfy_implementation_evidence() -> None:
    decision = evaluate_fallback_evidence(
        policy=_policy(FallbackKind.TOOLING_PREFLIGHT),
        request=_request(EvidencePurpose.IMPLEMENTATION),
    )

    assert decision == FallbackEvidenceDecision(
        fallback_policy_ref=FallbackPolicyRef(value="fallback.tooling_preflight"),
        applied_kind=FallbackKind.TOOLING_PREFLIGHT,
        evaluated_purpose=EvidencePurpose.IMPLEMENTATION,
        allowed=False,
        blocking_reasons=(
            "implementation evidence cannot be satisfied by fallback",
            "tooling preflight fallback is diagnostic only",
        ),
    )


def test_contract_deterministic_transform_cannot_satisfy_implementation_purpose() -> None:
    decision = evaluate_fallback_evidence(
        policy=_policy(FallbackKind.CONTRACT_ALLOWED_DETERMINISTIC_TRANSFORM),
        request=_request(EvidencePurpose.IMPLEMENTATION),
    )

    assert decision.allowed is False
    assert decision.fallback_policy_ref == FallbackPolicyRef(value="fallback.hash-manifest")
    assert decision.applied_kind is FallbackKind.CONTRACT_ALLOWED_DETERMINISTIC_TRANSFORM
    assert decision.evaluated_purpose is EvidencePurpose.IMPLEMENTATION
    assert "implementation evidence cannot be satisfied by fallback" in decision.blocking_reasons
    assert "deterministic transform can satisfy only deterministic evidence" in decision.blocking_reasons


def test_contract_deterministic_transform_requires_allowed_artifact_type_scope() -> None:
    decision = evaluate_fallback_evidence(
        policy=_policy(FallbackKind.CONTRACT_ALLOWED_DETERMINISTIC_TRANSFORM),
        request=FallbackEvidenceRequest(
            purpose=EvidencePurpose.DETERMINISTIC,
            artifact_type=RequiredArtifactType(value="source_patch"),
            acceptance_refs=(AcceptanceRef(value="AC-FALLBACK-DETERMINISTIC"),),
        ),
    )

    assert decision.allowed is False
    assert "artifact_type is outside fallback policy scope" in decision.blocking_reasons


def test_contract_deterministic_transform_requires_allowed_acceptance_scope() -> None:
    decision = evaluate_fallback_evidence(
        policy=_policy(FallbackKind.CONTRACT_ALLOWED_DETERMINISTIC_TRANSFORM),
        request=FallbackEvidenceRequest(
            purpose=EvidencePurpose.DETERMINISTIC,
            artifact_type=RequiredArtifactType(value="hash_manifest"),
            acceptance_refs=(AcceptanceRef(value="AC-OUTSIDE-SCOPE"),),
        ),
    )

    assert decision.allowed is False
    assert "acceptance_refs are outside fallback policy scope" in decision.blocking_reasons


def test_contract_deterministic_transform_policy_requires_explicit_allow_lists() -> None:
    with pytest.raises(
        ValidationError,
        match="deterministic transform policies require allowed artifact types",
    ):
        FallbackPolicy(
            fallback_policy_ref=FallbackPolicyRef(value="fallback.missing-artifacts"),
            kind=FallbackKind.CONTRACT_ALLOWED_DETERMINISTIC_TRANSFORM,
            allowed_artifact_types=(),
            allowed_acceptance_refs=(AcceptanceRef(value="AC-FALLBACK-DETERMINISTIC"),),
        )

    with pytest.raises(
        ValidationError,
        match="deterministic transform policies require allowed acceptance refs",
    ):
        FallbackPolicy(
            fallback_policy_ref=FallbackPolicyRef(value="fallback.missing-acceptance"),
            kind=FallbackKind.CONTRACT_ALLOWED_DETERMINISTIC_TRANSFORM,
            allowed_artifact_types=(RequiredArtifactType(value="hash_manifest"),),
            allowed_acceptance_refs=(),
        )


@pytest.mark.parametrize("kind", NON_CONTRACT_FALLBACK_KINDS)
def test_only_contract_deterministic_transform_policy_may_declare_allow_lists(
    kind: FallbackKind,
) -> None:
    with pytest.raises(
        ValidationError,
        match="only contract-allowed deterministic transform policies may declare allow lists",
    ):
        FallbackPolicy(
            fallback_policy_ref=FallbackPolicyRef(value="fallback.invalid-allow-list"),
            kind=kind,
            allowed_artifact_types=(RequiredArtifactType(value="hash_manifest"),),
            allowed_acceptance_refs=(AcceptanceRef(value="AC-FALLBACK-DETERMINISTIC"),),
        )


def test_fallback_request_requires_non_empty_acceptance_refs() -> None:
    with pytest.raises(ValidationError, match="acceptance_refs must not be empty"):
        FallbackEvidenceRequest(
            purpose=EvidencePurpose.DETERMINISTIC,
            artifact_type=RequiredArtifactType(value="hash_manifest"),
            acceptance_refs=(),
        )


@pytest.mark.parametrize(
    "missing_field",
    ("purpose", "artifact_type", "acceptance_refs"),
)
def test_fallback_request_rejects_missing_required_fields(missing_field: str) -> None:
    fields = {
        "purpose": EvidencePurpose.DETERMINISTIC,
        "artifact_type": RequiredArtifactType(value="hash_manifest"),
        "acceptance_refs": (AcceptanceRef(value="AC-FALLBACK-DETERMINISTIC"),),
    }
    fields.pop(missing_field)

    with pytest.raises(ValidationError):
        FallbackEvidenceRequest(**fields)


def test_fallback_models_reject_unknown_extra_fields() -> None:
    with pytest.raises(ValidationError):
        FallbackPolicy(
            fallback_policy_ref=FallbackPolicyRef(value="fallback.extra"),
            kind=FallbackKind.TOOLING_PREFLIGHT,
            unexpected="not allowed",
        )

    with pytest.raises(ValidationError):
        FallbackEvidenceRequest(
            purpose=EvidencePurpose.DETERMINISTIC,
            artifact_type=RequiredArtifactType(value="hash_manifest"),
            acceptance_refs=(AcceptanceRef(value="AC-FALLBACK-DETERMINISTIC"),),
            unexpected="not allowed",
        )

    with pytest.raises(ValidationError):
        FallbackEvidenceDecision(
            fallback_policy_ref=FallbackPolicyRef(value="fallback.extra"),
            applied_kind=FallbackKind.TOOLING_PREFLIGHT,
            evaluated_purpose=EvidencePurpose.DIAGNOSTIC,
            allowed=True,
            unexpected="not allowed",
        )
