from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import ValidationError

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
    FallbackRegistryError,
    evaluate_fallback_claim,
)
from boardroom_os.execution.context_index import ProviderAttemptRef
from boardroom_os.execution.fallback import (
    EvidencePurpose,
    FallbackEvidenceDecision,
    FallbackKind,
    FallbackPolicy,
)
from boardroom_os.execution.package import FallbackPolicyRef


ALWAYS_BLOCKED_FALLBACK_KINDS = (
    FallbackKind.PROVIDER_UNAVAILABLE,
    FallbackKind.TEST_ONLY_SIMULATION,
    FallbackKind.DETERMINISTIC_GOVERNANCE_DRAFT,
)


def _policy(
    kind: FallbackKind = FallbackKind.CONTRACT_ALLOWED_DETERMINISTIC_TRANSFORM,
    *,
    fallback_policy_ref: str = "fallback.hash-manifest",
    allowed_artifact_types: tuple[RequiredArtifactType, ...] | None = None,
    allowed_acceptance_refs: tuple[AcceptanceRef, ...] | None = None,
) -> FallbackPolicy:
    if kind is FallbackKind.CONTRACT_ALLOWED_DETERMINISTIC_TRANSFORM:
        artifact_types = (
            allowed_artifact_types
            if allowed_artifact_types is not None
            else (RequiredArtifactType(value="hash_manifest"),)
        )
        acceptance_refs = (
            allowed_acceptance_refs
            if allowed_acceptance_refs is not None
            else (
                AcceptanceRef(value="AC-HASH-MANIFEST"),
                AcceptanceRef(value="AC-REPLAY-HASH"),
            )
        )
        return FallbackPolicy(
            fallback_policy_ref=FallbackPolicyRef(value=fallback_policy_ref),
            kind=kind,
            allowed_artifact_types=artifact_types,
            allowed_acceptance_refs=acceptance_refs,
        )
    return FallbackPolicy(
        fallback_policy_ref=FallbackPolicyRef(value=fallback_policy_ref),
        kind=kind,
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
    evidence_claim_id: str = "evidence-claim.work_product.work-product.backend-api.EO-BACKEND-API",
    evidence_obligation_ref: str = "EO-BACKEND-API",
    producer_attempt_ref: str = "provider-attempt.backend-api",
    expected_purpose: EvidencePurpose = EvidencePurpose.DETERMINISTIC,
    required_artifact_type: str = "hash_manifest",
    acceptance_refs: tuple[AcceptanceRef, ...] | None = None,
    fallback_marker: FallbackLineageMarker | None = None,
) -> EvidenceClaim:
    resolved_acceptance_refs = (
        acceptance_refs
        if acceptance_refs is not None
        else (
            AcceptanceRef(value="AC-HASH-MANIFEST"),
            AcceptanceRef(value="AC-REPLAY-HASH"),
        )
    )
    return EvidenceClaim(
        evidence_claim_id=EvidenceClaimRef(value=evidence_claim_id),
        evidence_obligation_ref=EvidenceObligationRef(value=evidence_obligation_ref),
        producer_attempt_ref=ProviderAttemptRef(value=producer_attempt_ref),
        source_kind=EvidenceClaimSourceKind.WORK_PRODUCT,
        source_ref="work-product.backend-api",
        expected_purpose=expected_purpose,
        required_artifact_type=RequiredArtifactType(value=required_artifact_type),
        acceptance_refs=resolved_acceptance_refs,
        source_surface_refs=(SourceSurfaceRef(value="backend-api"),),
        artifact_refs=(EvidenceArtifactRef(value="artifact.hash-manifest"),),
        fallback_marker=fallback_marker,
        summary="fallback evidence claim",
    )


def _allowed_decision(
    *,
    fallback_policy_ref: str = "fallback.hash-manifest",
    applied_kind: FallbackKind = FallbackKind.CONTRACT_ALLOWED_DETERMINISTIC_TRANSFORM,
    evaluated_purpose: EvidencePurpose = EvidencePurpose.DETERMINISTIC,
    allowed: bool = True,
    blocking_reasons: tuple[str, ...] = (),
) -> FallbackEvidenceDecision:
    return FallbackEvidenceDecision(
        fallback_policy_ref=FallbackPolicyRef(value=fallback_policy_ref),
        applied_kind=applied_kind,
        evaluated_purpose=evaluated_purpose,
        allowed=allowed,
        blocking_reasons=blocking_reasons,
    )


def _record_fields(
    *,
    evidence_claim_ref: str = "evidence-claim.work_product.work-product.backend-api.EO-BACKEND-API",
    fallback_policy_ref: str = "fallback.hash-manifest",
    fallback_kind: FallbackKind = FallbackKind.CONTRACT_ALLOWED_DETERMINISTIC_TRANSFORM,
    evaluated_purpose: EvidencePurpose = EvidencePurpose.DETERMINISTIC,
    required_artifact_type: str = "hash_manifest",
    acceptance_refs: tuple[AcceptanceRef, ...] | None = None,
    decision: FallbackEvidenceDecision | None = None,
    evaluated_at: datetime | None = None,
) -> dict[str, Any]:
    resolved_acceptance_refs = (
        acceptance_refs
        if acceptance_refs is not None
        else (
            AcceptanceRef(value="AC-HASH-MANIFEST"),
            AcceptanceRef(value="AC-REPLAY-HASH"),
        )
    )
    resolved_decision = decision or _allowed_decision(
        fallback_policy_ref=fallback_policy_ref,
        applied_kind=fallback_kind,
        evaluated_purpose=evaluated_purpose,
    )
    return {
        "fallback_decision_record_id": FallbackDecisionRecordRef(
            value="fallback-decision.evidence-claim.work_product.work-product.backend-api.EO-BACKEND-API.fallback.hash-manifest"
        ),
        "evidence_claim_ref": EvidenceClaimRef(value=evidence_claim_ref),
        "producer_attempt_ref": ProviderAttemptRef(value="provider-attempt.backend-api"),
        "fallback_policy_ref": FallbackPolicyRef(value=fallback_policy_ref),
        "fallback_kind": fallback_kind,
        "evaluated_purpose": evaluated_purpose,
        "required_artifact_type": RequiredArtifactType(value=required_artifact_type),
        "acceptance_refs": resolved_acceptance_refs,
        "decision": resolved_decision,
        "evaluated_at": evaluated_at or datetime(2026, 5, 20, 9, 0, tzinfo=UTC),
    }


def test_fallback_registry_requires_non_empty_policies() -> None:
    with pytest.raises((ValidationError, FallbackRegistryError), match="policies"):
        FallbackPolicyRegistry(policies=())


def test_fallback_registry_rejects_duplicate_policy_refs() -> None:
    duplicate_ref = "fallback.hash-manifest"

    with pytest.raises((ValidationError, FallbackRegistryError), match="duplicate|unique"):
        _registry(
            _policy(fallback_policy_ref=duplicate_ref),
            _policy(
                kind=FallbackKind.TOOLING_PREFLIGHT,
                fallback_policy_ref=duplicate_ref,
            ),
        )


def test_fallback_registry_rejects_non_policy_items() -> None:
    with pytest.raises((ValidationError, TypeError, FallbackRegistryError), match="FallbackPolicy"):
        FallbackPolicyRegistry(policies=(_policy(), "fallback.hash-manifest"))


def test_fallback_registry_resolve_rejects_unknown_policy_ref() -> None:
    registry = _registry(_policy())

    with pytest.raises(FallbackRegistryError, match="unknown|resolve|fallback_policy_ref"):
        registry.resolve(FallbackPolicyRef(value="fallback.unknown"))


def test_fallback_registry_resolve_rejects_non_ref_input() -> None:
    registry = _registry(_policy())

    with pytest.raises((TypeError, FallbackRegistryError), match="FallbackPolicyRef"):
        registry.resolve("fallback.hash-manifest")


@pytest.mark.parametrize("kind", ALWAYS_BLOCKED_FALLBACK_KINDS)
def test_fallback_registry_rejects_dangerous_kinds_as_evidence_policy(
    kind: FallbackKind,
) -> None:
    with pytest.raises((ValidationError, FallbackRegistryError), match=kind.value):
        _registry(_policy(kind=kind, fallback_policy_ref=f"fallback.{kind.value.lower()}"))


def test_evaluate_fallback_claim_requires_registry() -> None:
    with pytest.raises((TypeError, FallbackRegistryError), match="registry"):
        evaluate_fallback_claim(
            claim=_claim(fallback_marker=_fallback_marker()),
            registry=None,
            evaluated_at=datetime(2026, 5, 20, 9, 0, tzinfo=UTC),
        )


def test_evaluate_fallback_claim_requires_fallback_marker() -> None:
    with pytest.raises(FallbackRegistryError, match="fallback_marker"):
        evaluate_fallback_claim(
            claim=_claim(fallback_marker=None),
            registry=_registry(_policy()),
            evaluated_at=datetime(2026, 5, 20, 9, 0, tzinfo=UTC),
        )


def test_evaluate_fallback_claim_rejects_unresolved_policy_ref() -> None:
    claim = _claim(
        fallback_marker=_fallback_marker(fallback_policy_ref="fallback.missing"),
    )

    with pytest.raises(FallbackRegistryError, match="fallback.missing"):
        evaluate_fallback_claim(
            claim=claim,
            registry=_registry(_policy()),
            evaluated_at=datetime(2026, 5, 20, 9, 0, tzinfo=UTC),
        )


def test_evaluate_fallback_claim_rejects_marker_kind_policy_kind_mismatch() -> None:
    claim = _claim(
        fallback_marker=_fallback_marker(
            fallback_kind=FallbackKind.TOOLING_PREFLIGHT,
        )
    )

    with pytest.raises(FallbackRegistryError, match="fallback_kind|kind mismatch"):
        evaluate_fallback_claim(
            claim=claim,
            registry=_registry(_policy()),
            evaluated_at=datetime(2026, 5, 20, 9, 0, tzinfo=UTC),
        )


def test_evaluate_fallback_claim_uses_claim_expected_purpose() -> None:
    claim = _claim(
        expected_purpose=EvidencePurpose.IMPLEMENTATION,
        fallback_marker=_fallback_marker(),
    )

    record = evaluate_fallback_claim(
        claim=claim,
        registry=_registry(_policy()),
        evaluated_at=datetime(2026, 5, 20, 9, 0, tzinfo=UTC),
    )

    assert record.evaluated_purpose is EvidencePurpose.IMPLEMENTATION
    assert record.decision.evaluated_purpose is EvidencePurpose.IMPLEMENTATION
    assert "implementation evidence cannot be satisfied by fallback" in record.decision.blocking_reasons


def test_evaluate_fallback_claim_uses_full_acceptance_refs_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    claim = _claim(fallback_marker=_fallback_marker())
    seen_requests: list[tuple[AcceptanceRef, ...]] = []

    def _fake_evaluate_fallback_evidence(*, policy: FallbackPolicy, request: Any) -> FallbackEvidenceDecision:
        del policy
        seen_requests.append(request.acceptance_refs)
        return _allowed_decision(
            fallback_policy_ref="fallback.hash-manifest",
            applied_kind=FallbackKind.CONTRACT_ALLOWED_DETERMINISTIC_TRANSFORM,
            evaluated_purpose=EvidencePurpose.DETERMINISTIC,
        )

    # 验证 registry orchestration contract，刻意 patch 模块本地 evaluator 引用。
    monkeypatch.setattr(
        "boardroom_os.evidence.fallback_registry.evaluate_fallback_evidence",
        _fake_evaluate_fallback_evidence,
    )

    evaluate_fallback_claim(
        claim=claim,
        registry=_registry(_policy()),
        evaluated_at=datetime(2026, 5, 20, 9, 0, tzinfo=UTC),
    )

    assert seen_requests == [claim.acceptance_refs]


def test_fallback_decision_record_rejects_decision_policy_mismatch() -> None:
    with pytest.raises(ValidationError, match="fallback_policy_ref"):
        FallbackDecisionRecord(
            **_record_fields(
                decision=_allowed_decision(fallback_policy_ref="fallback.other-policy"),
            )
        )


def test_fallback_decision_record_rejects_decision_kind_mismatch() -> None:
    with pytest.raises(ValidationError, match="applied_kind|fallback_kind"):
        FallbackDecisionRecord(
            **_record_fields(
                decision=_allowed_decision(applied_kind=FallbackKind.TOOLING_PREFLIGHT),
            )
        )


def test_fallback_decision_record_rejects_decision_purpose_mismatch() -> None:
    with pytest.raises(ValidationError, match="evaluated_purpose"):
        FallbackDecisionRecord(
            **_record_fields(
                decision=_allowed_decision(evaluated_purpose=EvidencePurpose.DIAGNOSTIC),
            )
        )


def test_fallback_decision_record_rejects_empty_acceptance_refs() -> None:
    with pytest.raises(ValidationError, match="acceptance_refs"):
        FallbackDecisionRecord(
            **_record_fields(
                acceptance_refs=(),
            )
        )


def test_fallback_decision_record_requires_timezone_aware_evaluated_at() -> None:
    with pytest.raises(ValidationError, match="timezone-aware"):
        FallbackDecisionRecord(
            **_record_fields(
                evaluated_at=datetime(2026, 5, 20, 9, 0),
            )
        )


def test_implementation_purpose_fallback_decision_is_blocked() -> None:
    record = evaluate_fallback_claim(
        claim=_claim(
            expected_purpose=EvidencePurpose.IMPLEMENTATION,
            fallback_marker=_fallback_marker(),
        ),
        registry=_registry(_policy()),
        evaluated_at=datetime(2026, 5, 20, 9, 0, tzinfo=UTC),
    )

    assert record.decision.allowed is False
    assert "implementation evidence cannot be satisfied by fallback" in record.decision.blocking_reasons
