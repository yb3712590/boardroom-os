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


def test_contract_allowed_deterministic_transform_can_satisfy_scoped_deterministic_evidence() -> None:
    policy = FallbackPolicy(
        fallback_policy_ref=FallbackPolicyRef(value="fallback.hash-manifest"),
        kind=FallbackKind.CONTRACT_ALLOWED_DETERMINISTIC_TRANSFORM,
        allowed_artifact_types=(RequiredArtifactType(value="hash_manifest"),),
        allowed_acceptance_refs=(AcceptanceRef(value="AC-HASH-MANIFEST"),),
    )
    request = FallbackEvidenceRequest(
        purpose=EvidencePurpose.DETERMINISTIC,
        artifact_type=RequiredArtifactType(value="hash_manifest"),
        acceptance_refs=(AcceptanceRef(value="AC-HASH-MANIFEST"),),
    )

    decision = evaluate_fallback_evidence(policy=policy, request=request)

    assert decision == FallbackEvidenceDecision(
        fallback_policy_ref=FallbackPolicyRef(value="fallback.hash-manifest"),
        applied_kind=FallbackKind.CONTRACT_ALLOWED_DETERMINISTIC_TRANSFORM,
        evaluated_purpose=EvidencePurpose.DETERMINISTIC,
        allowed=True,
    )
    assert decision.model_dump(mode="json") == {
        "fallback_policy_ref": {"value": "fallback.hash-manifest"},
        "applied_kind": "CONTRACT_ALLOWED_DETERMINISTIC_TRANSFORM",
        "evaluated_purpose": "deterministic",
        "allowed": True,
        "blocking_reasons": [],
    }


def test_tooling_preflight_can_only_return_diagnostic_eligibility() -> None:
    policy = FallbackPolicy(
        fallback_policy_ref=FallbackPolicyRef(value="fallback.tooling-preflight"),
        kind=FallbackKind.TOOLING_PREFLIGHT,
    )
    request = FallbackEvidenceRequest(
        purpose=EvidencePurpose.DIAGNOSTIC,
        artifact_type=RequiredArtifactType(value="preflight_report"),
        acceptance_refs=(AcceptanceRef(value="AC-PREFLIGHT"),),
    )

    decision = evaluate_fallback_evidence(policy=policy, request=request)

    assert decision == FallbackEvidenceDecision(
        fallback_policy_ref=FallbackPolicyRef(value="fallback.tooling-preflight"),
        applied_kind=FallbackKind.TOOLING_PREFLIGHT,
        evaluated_purpose=EvidencePurpose.DIAGNOSTIC,
        allowed=True,
    )


def test_tooling_preflight_cannot_satisfy_deterministic_evidence() -> None:
    policy = FallbackPolicy(
        fallback_policy_ref=FallbackPolicyRef(value="fallback.tooling-preflight"),
        kind=FallbackKind.TOOLING_PREFLIGHT,
    )
    request = FallbackEvidenceRequest(
        purpose=EvidencePurpose.DETERMINISTIC,
        artifact_type=RequiredArtifactType(value="hash_manifest"),
        acceptance_refs=(AcceptanceRef(value="AC-HASH-MANIFEST"),),
    )

    decision = evaluate_fallback_evidence(policy=policy, request=request)

    assert decision.allowed is False
    assert decision.blocking_reasons == ("tooling preflight fallback is diagnostic only",)


def test_blocked_decision_must_include_reasons() -> None:
    with pytest.raises(
        ValidationError,
        match="blocked fallback decisions must include blocking reasons",
    ):
        FallbackEvidenceDecision(
            fallback_policy_ref=FallbackPolicyRef(value="fallback.blocked"),
            applied_kind=FallbackKind.TOOLING_PREFLIGHT,
            evaluated_purpose=EvidencePurpose.DETERMINISTIC,
            allowed=False,
        )


def test_allowed_decision_must_not_include_reasons() -> None:
    with pytest.raises(
        ValidationError,
        match="allowed fallback decisions must not include blocking reasons",
    ):
        FallbackEvidenceDecision(
            fallback_policy_ref=FallbackPolicyRef(value="fallback.allowed"),
            applied_kind=FallbackKind.TOOLING_PREFLIGHT,
            evaluated_purpose=EvidencePurpose.DIAGNOSTIC,
            allowed=True,
            blocking_reasons=("not allowed",),
        )
