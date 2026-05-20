"""Evidence-layer primitives for Boardroom OS V2."""

from boardroom_os.evidence.claim import (
    EvidenceArtifactRef,
    EvidenceClaim,
    EvidenceClaimBuildError,
    EvidenceClaimRef,
    EvidenceClaimSourceKind,
    FallbackLineageMarker,
    build_evidence_claim_from_verification_run,
    build_evidence_claim_from_work_product,
)
from boardroom_os.evidence.fallback_registry import (
    FallbackDecisionRecord,
    FallbackDecisionRecordRef,
    FallbackPolicyRegistry,
    FallbackRegistryError,
    evaluate_fallback_claim,
)

__all__ = [
    "EvidenceArtifactRef",
    "EvidenceClaim",
    "EvidenceClaimBuildError",
    "EvidenceClaimRef",
    "EvidenceClaimSourceKind",
    "FallbackLineageMarker",
    "FallbackDecisionRecord",
    "FallbackDecisionRecordRef",
    "FallbackPolicyRegistry",
    "FallbackRegistryError",
    "build_evidence_claim_from_verification_run",
    "build_evidence_claim_from_work_product",
    "evaluate_fallback_claim",
]
