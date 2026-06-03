from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, ValidationInfo, field_validator, model_validator

from boardroom_os.agents.skills import _normalize_ref_fields
from boardroom_os.contracts.evidence_obligation import EvidenceObligation, RequiredArtifactType
from boardroom_os.contracts.types import (
    AcceptanceRef,
    EvidenceObligationRef,
    NonEmptyTextValue,
    SourceSurfaceRef,
)
from boardroom_os.execution.context_index import ProviderAttemptRef
from boardroom_os.execution.fallback import EvidencePurpose, FallbackKind
from boardroom_os.execution.package import FallbackPolicyRef
from boardroom_os.execution.verification_run import VerificationRun, VerificationRunRef
from boardroom_os.evidence.live_blackbox import (
    LiveBlackboxIntegrationEvidence,
)
from boardroom_os.evidence.service_run import ServiceRunEvidence
from boardroom_os.execution.work_product import WorkProduct, WorkProductClaimDraft


class EvidenceClaimBuildError(ValueError):
    pass


class EvidenceClaimRef(NonEmptyTextValue):
    pass


class EvidenceArtifactRef(NonEmptyTextValue):
    pass


class EvidenceClaimSourceKind(StrEnum):
    WORK_PRODUCT = "work_product"
    VERIFICATION_RUN = "verification_run"
    SERVICE_RUN = "service_run"
    LIVE_BLACKBOX = "live_blackbox"


_TUPLE_REF_FIELDS = (
    "acceptance_refs",
    "source_surface_refs",
    "artifact_refs",
    "verification_run_refs",
)


def _reject_malformed_tuple_ref_inputs(data: Any) -> Any:
    if not isinstance(data, dict):
        return data
    for field_name in _TUPLE_REF_FIELDS:
        if field_name in data and not isinstance(data[field_name], list | tuple):
            raise ValueError(f"{field_name} must be a tuple or list")
    return data


class FallbackLineageMarker(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    fallback_policy_ref: FallbackPolicyRef
    fallback_kind: FallbackKind
    producer_attempt_ref: ProviderAttemptRef

    @model_validator(mode="before")
    @classmethod
    def _normalize_yaml_refs(cls, data: Any) -> Any:
        return _normalize_ref_fields(
            data,
            {
                "fallback_policy_ref": FallbackPolicyRef,
                "producer_attempt_ref": ProviderAttemptRef,
            },
        )


class EvidenceClaim(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    version: Literal[1] = 1
    evidence_claim_id: EvidenceClaimRef
    evidence_obligation_ref: EvidenceObligationRef
    producer_attempt_ref: ProviderAttemptRef
    source_kind: EvidenceClaimSourceKind
    source_ref: str
    expected_purpose: EvidencePurpose
    required_artifact_type: RequiredArtifactType
    acceptance_refs: tuple[AcceptanceRef, ...]
    source_surface_refs: tuple[SourceSurfaceRef, ...]
    artifact_refs: tuple[EvidenceArtifactRef, ...]
    verification_run_refs: tuple[VerificationRunRef, ...] = ()
    fallback_marker: FallbackLineageMarker | None = None
    summary: str

    @model_validator(mode="before")
    @classmethod
    def _normalize_yaml_refs(cls, data: Any) -> Any:
        data = _reject_malformed_tuple_ref_inputs(data)
        return _normalize_ref_fields(
            data,
            {
                "evidence_claim_id": EvidenceClaimRef,
                "evidence_obligation_ref": EvidenceObligationRef,
                "producer_attempt_ref": ProviderAttemptRef,
                "required_artifact_type": RequiredArtifactType,
            },
            {
                "acceptance_refs": AcceptanceRef,
                "source_surface_refs": SourceSurfaceRef,
                "artifact_refs": EvidenceArtifactRef,
                "verification_run_refs": VerificationRunRef,
            },
        )

    @field_validator("source_ref", "summary")
    @classmethod
    def _reject_empty_text(cls, value: str, info: ValidationInfo) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError(f"{info.field_name} must not be empty")
        return normalized

    @field_validator("acceptance_refs", "source_surface_refs", "artifact_refs")
    @classmethod
    def _reject_empty_required_tuples(
        cls,
        values: tuple[object, ...],
        info: ValidationInfo,
    ) -> tuple[object, ...]:
        if not values:
            raise ValueError(f"{info.field_name} must not be empty")
        return values

    @model_validator(mode="after")
    def _validate_claim_shape(self) -> Self:
        if self.source_kind is EvidenceClaimSourceKind.VERIFICATION_RUN:
            if not self.verification_run_refs:
                raise ValueError(
                    "verification_run_refs are required for verification_run claims"
                )
            if self.source_ref != self.verification_run_refs[0].value:
                raise ValueError(
                    "source_ref must match the first verification_run_ref"
                )
        elif self.verification_run_refs:
            raise ValueError("non-verification_run claims must not include verification_run_refs")

        if self.fallback_marker is not None:
            if self.fallback_marker.producer_attempt_ref != self.producer_attempt_ref:
                raise ValueError(
                    "fallback_marker.producer_attempt_ref must match producer_attempt_ref"
                )
        return self


def _claim_id_for(
    *,
    source_kind: EvidenceClaimSourceKind,
    source_ref: str,
    evidence_obligation_ref: EvidenceObligationRef,
) -> EvidenceClaimRef:
    return EvidenceClaimRef(
        value=f"evidence-claim.{source_kind.value}.{source_ref}.{evidence_obligation_ref.value}"
    )



def _ensure_subset(
    *,
    provided_values: tuple[NonEmptyTextValue, ...],
    required_values: tuple[NonEmptyTextValue, ...],
    field_name: str,
) -> None:
    provided = {value.value for value in provided_values}
    required = {value.value for value in required_values}
    if not required.issubset(provided):
        raise EvidenceClaimBuildError(f"{field_name} must cover evidence obligation refs")


def _claim_refs_for_obligation(
    *,
    provided_values: tuple[NonEmptyTextValue, ...],
    required_values: tuple[NonEmptyTextValue, ...],
    field_name: str,
) -> tuple[NonEmptyTextValue, ...]:
    _ensure_subset(
        provided_values=provided_values,
        required_values=required_values,
        field_name=field_name,
    )
    provided_by_value = {value.value: value for value in provided_values}
    return tuple(provided_by_value[value.value] for value in required_values)



def _evidence_artifact_refs(
    values: tuple[NonEmptyTextValue, ...],
) -> tuple[EvidenceArtifactRef, ...]:
    return tuple(EvidenceArtifactRef(value=value.value) for value in values)



def _validate_expected_purpose(expected_purpose: EvidencePurpose) -> None:
    if not isinstance(expected_purpose, EvidencePurpose):
        raise EvidenceClaimBuildError("expected_purpose must be an EvidencePurpose")



def _validate_producer_attempt_ref(
    producer_attempt_ref: ProviderAttemptRef,
) -> None:
    if not isinstance(producer_attempt_ref, ProviderAttemptRef):
        raise EvidenceClaimBuildError("producer_attempt_ref must be a ProviderAttemptRef")



def _normalize_builder_tuple_refs(
    *,
    values: object,
    ref_type: type[NonEmptyTextValue],
    field_name: str,
) -> tuple[NonEmptyTextValue, ...]:
    if not isinstance(values, tuple | list):
        raise EvidenceClaimBuildError(f"{field_name} must be a tuple or list")

    normalized: list[NonEmptyTextValue] = []
    for value in values:
        if isinstance(value, ref_type):
            normalized.append(value)
            continue
        if isinstance(value, str) or (isinstance(value, dict) and set(value) == {"value"}):
            raise EvidenceClaimBuildError(
                f"{field_name} must contain {ref_type.__name__} values"
            )
        raise EvidenceClaimBuildError(
            f"{field_name} must contain {ref_type.__name__} values"
        )
    return tuple(normalized)



def _normalize_acceptance_refs(
    acceptance_refs: object,
) -> tuple[AcceptanceRef, ...]:
    return tuple(
        _normalize_builder_tuple_refs(
            values=acceptance_refs,
            ref_type=AcceptanceRef,
            field_name="acceptance_refs",
        )
    )



def _normalize_source_surface_refs(
    source_surface_refs: object,
) -> tuple[SourceSurfaceRef, ...]:
    return tuple(
        _normalize_builder_tuple_refs(
            values=source_surface_refs,
            ref_type=SourceSurfaceRef,
            field_name="source_surface_refs",
        )
    )



def _validate_work_product_claim_draft_alignment(
    *,
    work_product: WorkProduct,
    claim_draft: WorkProductClaimDraft,
) -> None:
    if claim_draft.claim_draft_ref not in work_product.claim_refs:
        raise EvidenceClaimBuildError(
            "claim_draft_ref must belong to work_product.claim_refs"
        )
    if claim_draft.producer_attempt_ref != work_product.producer_attempt_ref:
        raise EvidenceClaimBuildError(
            "claim_draft.producer_attempt_ref must match work_product.producer_attempt_ref"
        )
    if claim_draft.execution_package_ref != work_product.execution_package_ref:
        raise EvidenceClaimBuildError(
            "claim_draft.execution_package_ref must match work_product.execution_package_ref"
        )
    if claim_draft.ticket_ref != work_product.ticket_ref:
        raise EvidenceClaimBuildError(
            "claim_draft.ticket_ref must match work_product.ticket_ref"
        )
    if claim_draft.artifact_refs != work_product.artifact_refs:
        raise EvidenceClaimBuildError(
            "claim_draft.artifact_refs must match work_product.artifact_refs"
        )



def build_evidence_claim_from_work_product(
    *,
    work_product: WorkProduct,
    claim_draft: WorkProductClaimDraft,
    evidence_obligation: EvidenceObligation,
    expected_purpose: EvidencePurpose,
    summary: str,
    fallback_policy_ref: FallbackPolicyRef | None = None,
    claim_id: EvidenceClaimRef | None = None,
) -> EvidenceClaim:
    _validate_expected_purpose(expected_purpose)
    _validate_work_product_claim_draft_alignment(
        work_product=work_product,
        claim_draft=claim_draft,
    )
    acceptance_refs = _claim_refs_for_obligation(
        provided_values=claim_draft.acceptance_refs,
        required_values=evidence_obligation.acceptance_refs,
        field_name="acceptance_refs",
    )
    source_surface_refs = _claim_refs_for_obligation(
        provided_values=claim_draft.source_surface_refs,
        required_values=evidence_obligation.source_surface_refs,
        field_name="source_surface_refs",
    )

    fallback_marker: FallbackLineageMarker | None = None
    if work_product.fallback_kind is None:
        if fallback_policy_ref is not None:
            raise EvidenceClaimBuildError(
                "primary work product must not include fallback_policy_ref"
            )
    else:
        if fallback_policy_ref is None:
            raise EvidenceClaimBuildError(
                "fallback work product requires fallback_policy_ref"
            )
        fallback_marker = FallbackLineageMarker(
            fallback_policy_ref=fallback_policy_ref,
            fallback_kind=work_product.fallback_kind,
            producer_attempt_ref=work_product.producer_attempt_ref,
        )

    source_ref = work_product.work_product_id.value
    resolved_claim_id = claim_id or _claim_id_for(
        source_kind=EvidenceClaimSourceKind.WORK_PRODUCT,
        source_ref=source_ref,
        evidence_obligation_ref=evidence_obligation.evidence_obligation_id,
    )
    return EvidenceClaim(
        evidence_claim_id=resolved_claim_id,
        evidence_obligation_ref=evidence_obligation.evidence_obligation_id,
        producer_attempt_ref=work_product.producer_attempt_ref,
        source_kind=EvidenceClaimSourceKind.WORK_PRODUCT,
        source_ref=source_ref,
        expected_purpose=expected_purpose,
        required_artifact_type=evidence_obligation.required_artifact_type,
        acceptance_refs=acceptance_refs,
        source_surface_refs=source_surface_refs,
        artifact_refs=_evidence_artifact_refs(work_product.artifact_refs),
        verification_run_refs=(),
        fallback_marker=fallback_marker,
        summary=summary,
    )



def build_evidence_claim_from_verification_run(
    *,
    verification_run: VerificationRun,
    evidence_obligation: EvidenceObligation,
    producer_attempt_ref: ProviderAttemptRef,
    acceptance_refs: tuple[AcceptanceRef, ...],
    source_surface_refs: tuple[SourceSurfaceRef, ...],
    expected_purpose: EvidencePurpose,
    summary: str,
    claim_id: EvidenceClaimRef | None = None,
) -> EvidenceClaim:
    _validate_producer_attempt_ref(producer_attempt_ref)
    _validate_expected_purpose(expected_purpose)
    normalized_acceptance_refs = _normalize_acceptance_refs(acceptance_refs)
    normalized_source_surface_refs = _normalize_source_surface_refs(source_surface_refs)
    claim_acceptance_refs = _claim_refs_for_obligation(
        provided_values=normalized_acceptance_refs,
        required_values=evidence_obligation.acceptance_refs,
        field_name="acceptance_refs",
    )
    claim_source_surface_refs = _claim_refs_for_obligation(
        provided_values=normalized_source_surface_refs,
        required_values=evidence_obligation.source_surface_refs,
        field_name="source_surface_refs",
    )
    source_ref = verification_run.verification_run_id.value
    resolved_claim_id = claim_id or _claim_id_for(
        source_kind=EvidenceClaimSourceKind.VERIFICATION_RUN,
        source_ref=source_ref,
        evidence_obligation_ref=evidence_obligation.evidence_obligation_id,
    )
    return EvidenceClaim(
        evidence_claim_id=resolved_claim_id,
        evidence_obligation_ref=evidence_obligation.evidence_obligation_id,
        producer_attempt_ref=producer_attempt_ref,
        source_kind=EvidenceClaimSourceKind.VERIFICATION_RUN,
        source_ref=source_ref,
        expected_purpose=expected_purpose,
        required_artifact_type=evidence_obligation.required_artifact_type,
        acceptance_refs=claim_acceptance_refs,
        source_surface_refs=claim_source_surface_refs,
        artifact_refs=(
            EvidenceArtifactRef(value=verification_run.stdout_ref.value),
            EvidenceArtifactRef(value=verification_run.stderr_ref.value),
        ),
        verification_run_refs=(verification_run.verification_run_id,),
        fallback_marker=None,
        summary=summary,
    )


def build_evidence_claim_from_service_run(
    *,
    service_run: ServiceRunEvidence,
    evidence_obligation: EvidenceObligation,
    producer_attempt_ref: ProviderAttemptRef,
    acceptance_refs: tuple[AcceptanceRef, ...],
    source_surface_refs: tuple[SourceSurfaceRef, ...],
    expected_purpose: EvidencePurpose,
    summary: str,
    claim_id: EvidenceClaimRef | None = None,
) -> EvidenceClaim:
    _validate_producer_attempt_ref(producer_attempt_ref)
    _validate_expected_purpose(expected_purpose)
    normalized_acceptance_refs = _normalize_acceptance_refs(acceptance_refs)
    normalized_source_surface_refs = _normalize_source_surface_refs(source_surface_refs)
    claim_acceptance_refs = _claim_refs_for_obligation(
        provided_values=normalized_acceptance_refs,
        required_values=evidence_obligation.acceptance_refs,
        field_name="acceptance_refs",
    )
    claim_source_surface_refs = _claim_refs_for_obligation(
        provided_values=normalized_source_surface_refs,
        required_values=evidence_obligation.source_surface_refs,
        field_name="source_surface_refs",
    )
    source_ref = service_run.service_run_evidence_id.value
    resolved_claim_id = claim_id or _claim_id_for(
        source_kind=EvidenceClaimSourceKind.SERVICE_RUN,
        source_ref=source_ref,
        evidence_obligation_ref=evidence_obligation.evidence_obligation_id,
    )
    return EvidenceClaim(
        evidence_claim_id=resolved_claim_id,
        evidence_obligation_ref=evidence_obligation.evidence_obligation_id,
        producer_attempt_ref=producer_attempt_ref,
        source_kind=EvidenceClaimSourceKind.SERVICE_RUN,
        source_ref=source_ref,
        expected_purpose=expected_purpose,
        required_artifact_type=evidence_obligation.required_artifact_type,
        acceptance_refs=claim_acceptance_refs,
        source_surface_refs=claim_source_surface_refs,
        artifact_refs=(
            EvidenceArtifactRef(value=service_run.stdout_ref.value),
            EvidenceArtifactRef(value=service_run.stderr_ref.value),
        ),
        verification_run_refs=(),
        fallback_marker=None,
        summary=summary,
    )


def build_evidence_claim_from_live_blackbox(
    *,
    evidence: LiveBlackboxIntegrationEvidence,
    evidence_obligation: EvidenceObligation,
    producer_attempt_ref: ProviderAttemptRef,
    expected_purpose: EvidencePurpose,
    summary: str,
    claim_id: EvidenceClaimRef | None = None,
) -> EvidenceClaim:
    _validate_producer_attempt_ref(producer_attempt_ref)
    _validate_expected_purpose(expected_purpose)
    source_ref = evidence.live_blackbox_evidence_id.value
    obligation_acceptance_refs = {ref.value for ref in evidence_obligation.acceptance_refs}
    matching_probe_refs = tuple(
        f"{source_ref}.{probe.probe_ref.value}"
        for probe in sorted(evidence.probes, key=lambda item: item.probe_ref.value)
        if obligation_acceptance_refs.intersection(
            acceptance_ref.value for acceptance_ref in probe.acceptance_refs
        )
    )
    if not matching_probe_refs:
        raise EvidenceClaimBuildError(
            "live blackbox evidence has no probe bound to evidence obligation acceptance refs"
        )
    resolved_claim_id = claim_id or _claim_id_for(
        source_kind=EvidenceClaimSourceKind.LIVE_BLACKBOX,
        source_ref=source_ref,
        evidence_obligation_ref=evidence_obligation.evidence_obligation_id,
    )
    return EvidenceClaim(
        evidence_claim_id=resolved_claim_id,
        evidence_obligation_ref=evidence_obligation.evidence_obligation_id,
        producer_attempt_ref=producer_attempt_ref,
        source_kind=EvidenceClaimSourceKind.LIVE_BLACKBOX,
        source_ref=source_ref,
        expected_purpose=expected_purpose,
        required_artifact_type=evidence_obligation.required_artifact_type,
        acceptance_refs=evidence_obligation.acceptance_refs,
        source_surface_refs=evidence_obligation.source_surface_refs,
        artifact_refs=tuple(EvidenceArtifactRef(value=value) for value in matching_probe_refs),
        verification_run_refs=(),
        fallback_marker=None,
        summary=summary,
    )


__all__ = [
    "EvidenceArtifactRef",
    "EvidenceClaim",
    "EvidenceClaimBuildError",
    "EvidenceClaimRef",
    "EvidenceClaimSourceKind",
    "FallbackLineageMarker",
    "build_evidence_claim_from_service_run",
    "build_evidence_claim_from_live_blackbox",
    "build_evidence_claim_from_verification_run",
    "build_evidence_claim_from_work_product",
]
