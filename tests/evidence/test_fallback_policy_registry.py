from __future__ import annotations

from datetime import UTC, datetime

from boardroom_os.contracts.evidence_obligation import RequiredArtifactType
from boardroom_os.contracts.types import AcceptanceRef, EvidenceObligationRef, SourceSurfaceRef
from boardroom_os.evidence.claim import (
    EvidenceArtifactRef,
    EvidenceClaim,
    EvidenceClaimRef,
    EvidenceClaimSourceKind,
    FallbackLineageMarker,
)
from boardroom_os.evidence.fallback_registry import (
    FallbackDecisionRecord,
    FallbackDecisionRecordRef,
    FallbackPolicyRegistry,
    evaluate_fallback_claim,
)
from boardroom_os.execution.context_index import ProviderAttemptRef
from boardroom_os.execution.fallback import EvidencePurpose, FallbackKind, FallbackPolicy
from boardroom_os.execution.package import FallbackPolicyRef


EVALUATED_AT = datetime(2026, 5, 20, 12, 0, tzinfo=UTC)


DETERMINISTIC_ACCEPTANCE_REFS = (
    AcceptanceRef(value="AC-HASH-MANIFEST"),
    AcceptanceRef(value="AC-REPLAY-HASH"),
)


def _deterministic_policy(
    *,
    fallback_policy_ref: str = "fallback.hash-manifest",
    allowed_artifact_types: tuple[RequiredArtifactType, ...] = (
        RequiredArtifactType(value="hash_manifest"),
    ),
    allowed_acceptance_refs: tuple[AcceptanceRef, ...] = DETERMINISTIC_ACCEPTANCE_REFS,
) -> FallbackPolicy:
    return FallbackPolicy(
        fallback_policy_ref=FallbackPolicyRef(value=fallback_policy_ref),
        kind=FallbackKind.CONTRACT_ALLOWED_DETERMINISTIC_TRANSFORM,
        allowed_artifact_types=allowed_artifact_types,
        allowed_acceptance_refs=allowed_acceptance_refs,
    )


def _tooling_preflight_policy(
    *,
    fallback_policy_ref: str = "fallback.tooling-preflight",
) -> FallbackPolicy:
    return FallbackPolicy(
        fallback_policy_ref=FallbackPolicyRef(value=fallback_policy_ref),
        kind=FallbackKind.TOOLING_PREFLIGHT,
    )


def _registry(*policies: FallbackPolicy) -> FallbackPolicyRegistry:
    return FallbackPolicyRegistry(policies=policies)


def _fallback_marker(
    *,
    fallback_policy_ref: str = "fallback.hash-manifest",
    fallback_kind: FallbackKind = FallbackKind.CONTRACT_ALLOWED_DETERMINISTIC_TRANSFORM,
    producer_attempt_ref: str = "provider-attempt.backend-api",
) -> FallbackLineageMarker:
    return FallbackLineageMarker(
        fallback_policy_ref=FallbackPolicyRef(value=fallback_policy_ref),
        fallback_kind=fallback_kind,
        producer_attempt_ref=ProviderAttemptRef(value=producer_attempt_ref),
    )


def _claim(
    *,
    evidence_claim_id: str = "evidence-claim.work_product.work-product.backend-api.evidence.hash-manifest",
    evidence_obligation_ref: str = "evidence.hash-manifest",
    producer_attempt_ref: str = "provider-attempt.backend-api",
    expected_purpose: EvidencePurpose = EvidencePurpose.DETERMINISTIC,
    required_artifact_type: str = "hash_manifest",
    acceptance_refs: tuple[AcceptanceRef, ...] = DETERMINISTIC_ACCEPTANCE_REFS,
    fallback_marker: FallbackLineageMarker | None = None,
) -> EvidenceClaim:
    return EvidenceClaim(
        evidence_claim_id=EvidenceClaimRef(value=evidence_claim_id),
        evidence_obligation_ref=EvidenceObligationRef(value=evidence_obligation_ref),
        producer_attempt_ref=ProviderAttemptRef(value=producer_attempt_ref),
        source_kind=EvidenceClaimSourceKind.WORK_PRODUCT,
        source_ref="work-product.backend-api",
        expected_purpose=expected_purpose,
        required_artifact_type=RequiredArtifactType(value=required_artifact_type),
        acceptance_refs=acceptance_refs,
        source_surface_refs=(SourceSurfaceRef(value="surface.backend-api"),),
        artifact_refs=(EvidenceArtifactRef(value="artifact.hash-manifest"),),
        fallback_marker=fallback_marker or _fallback_marker(
            producer_attempt_ref=producer_attempt_ref,
        ),
        summary="fallback evidence claim",
    )


def test_registry_resolves_fallback_policy_by_ref() -> None:
    policy = _deterministic_policy()
    registry = _registry(policy)

    resolved_policy = registry.resolve(FallbackPolicyRef(value="fallback.hash-manifest"))

    assert resolved_policy == policy


def test_evaluate_fallback_claim_records_allowed_deterministic_decision() -> None:
    claim = _claim()

    record = evaluate_fallback_claim(
        claim=claim,
        registry=_registry(_deterministic_policy()),
        evaluated_at=EVALUATED_AT,
    )

    assert isinstance(record, FallbackDecisionRecord)
    assert record.evidence_claim_ref == claim.evidence_claim_id
    assert record.producer_attempt_ref == ProviderAttemptRef(
        value="provider-attempt.backend-api"
    )
    assert record.fallback_policy_ref == FallbackPolicyRef(value="fallback.hash-manifest")
    assert record.fallback_kind is FallbackKind.CONTRACT_ALLOWED_DETERMINISTIC_TRANSFORM
    assert record.evaluated_purpose is EvidencePurpose.DETERMINISTIC
    assert record.required_artifact_type == RequiredArtifactType(value="hash_manifest")
    assert record.acceptance_refs == DETERMINISTIC_ACCEPTANCE_REFS
    assert record.decision.allowed is True
    assert record.decision.fallback_policy_ref == FallbackPolicyRef(
        value="fallback.hash-manifest"
    )
    assert record.decision.applied_kind is FallbackKind.CONTRACT_ALLOWED_DETERMINISTIC_TRANSFORM
    assert record.decision.evaluated_purpose is EvidencePurpose.DETERMINISTIC
    assert record.decision.blocking_reasons == ()
    assert record.evaluated_at == EVALUATED_AT


def test_evaluate_fallback_claim_records_blocked_implementation_decision() -> None:
    claim = _claim(expected_purpose=EvidencePurpose.IMPLEMENTATION)

    record = evaluate_fallback_claim(
        claim=claim,
        registry=_registry(_deterministic_policy()),
        evaluated_at=EVALUATED_AT,
    )

    assert record.evaluated_purpose is EvidencePurpose.IMPLEMENTATION
    assert record.decision.allowed is False
    assert record.decision.evaluated_purpose is EvidencePurpose.IMPLEMENTATION
    assert (
        "implementation evidence cannot be satisfied by fallback"
        in record.decision.blocking_reasons
    )


def test_evaluate_fallback_claim_records_tooling_preflight_diagnostic_decision() -> None:
    claim = _claim(
        evidence_claim_id="evidence-claim.work_product.work-product.backend-api.evidence.preflight",
        evidence_obligation_ref="evidence.preflight",
        expected_purpose=EvidencePurpose.DIAGNOSTIC,
        required_artifact_type="preflight_report",
        acceptance_refs=(AcceptanceRef(value="AC-PREFLIGHT"),),
        fallback_marker=_fallback_marker(
            fallback_policy_ref="fallback.tooling-preflight",
            fallback_kind=FallbackKind.TOOLING_PREFLIGHT,
        ),
    )

    record = evaluate_fallback_claim(
        claim=claim,
        registry=_registry(_tooling_preflight_policy()),
        evaluated_at=EVALUATED_AT,
    )

    assert record.fallback_policy_ref == FallbackPolicyRef(
        value="fallback.tooling-preflight"
    )
    assert record.fallback_kind is FallbackKind.TOOLING_PREFLIGHT
    assert record.evaluated_purpose is EvidencePurpose.DIAGNOSTIC
    assert record.required_artifact_type == RequiredArtifactType(value="preflight_report")
    assert record.acceptance_refs == (AcceptanceRef(value="AC-PREFLIGHT"),)
    assert record.decision.allowed is True
    assert record.decision.applied_kind is FallbackKind.TOOLING_PREFLIGHT
    assert record.decision.blocking_reasons == ()


def test_decision_record_uses_deterministic_default_id() -> None:
    claim = _claim(evidence_claim_id="evidence-claim.custom-deterministic")

    record = evaluate_fallback_claim(
        claim=claim,
        registry=_registry(_deterministic_policy()),
        evaluated_at=EVALUATED_AT,
    )

    assert record.fallback_decision_record_id == FallbackDecisionRecordRef(
        value="fallback-decision.evidence-claim.custom-deterministic.fallback.hash-manifest"
    )


def test_decision_record_can_use_explicit_id() -> None:
    explicit_record_id = FallbackDecisionRecordRef(
        value="fallback-decision.explicit-review"
    )

    record = evaluate_fallback_claim(
        claim=_claim(),
        registry=_registry(_deterministic_policy()),
        evaluated_at=EVALUATED_AT,
        decision_record_id=explicit_record_id,
    )

    assert record.fallback_decision_record_id == explicit_record_id


def test_decision_record_serializes_as_audit_friendly_json() -> None:
    record = evaluate_fallback_claim(
        claim=_claim(),
        registry=_registry(_deterministic_policy()),
        evaluated_at=EVALUATED_AT,
    )

    assert record.model_dump(mode="json") == {
        "version": 1,
        "fallback_decision_record_id": {
            "value": (
                "fallback-decision."
                "evidence-claim.work_product.work-product.backend-api.evidence.hash-manifest."
                "fallback.hash-manifest"
            )
        },
        "evidence_claim_ref": {
            "value": "evidence-claim.work_product.work-product.backend-api.evidence.hash-manifest"
        },
        "producer_attempt_ref": {"value": "provider-attempt.backend-api"},
        "fallback_policy_ref": {"value": "fallback.hash-manifest"},
        "fallback_kind": "CONTRACT_ALLOWED_DETERMINISTIC_TRANSFORM",
        "evaluated_purpose": "deterministic",
        "required_artifact_type": {"value": "hash_manifest"},
        "acceptance_refs": [
            {"value": "AC-HASH-MANIFEST"},
            {"value": "AC-REPLAY-HASH"},
        ],
        "decision": {
            "fallback_policy_ref": {"value": "fallback.hash-manifest"},
            "applied_kind": "CONTRACT_ALLOWED_DETERMINISTIC_TRANSFORM",
            "evaluated_purpose": "deterministic",
            "allowed": True,
            "blocking_reasons": [],
        },
        "evaluated_at": "2026-05-20T12:00:00Z",
    }
