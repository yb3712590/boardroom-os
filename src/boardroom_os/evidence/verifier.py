from __future__ import annotations

import re
from datetime import datetime
from enum import StrEnum
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from boardroom_os.agents.role_prompt_hooks import (
    RolePromptHookRef,
    RolePromptHookRegistry,
    RolePromptHookSha256,
)
from boardroom_os.agents.skills import _normalize_ref_fields
from boardroom_os.contracts.acceptance import AcceptanceContract
from boardroom_os.contracts.evidence_obligation import (
    EvidenceObligation,
    RequiredArtifactType,
)
from boardroom_os.contracts.package import PackageContract
from boardroom_os.contracts.types import (
    AcceptanceRef,
    EvidenceObligationRef,
    NonEmptyTextValue,
    SourceSurfaceRef,
)
from boardroom_os.evidence.claim import (
    EvidenceArtifactRef,
    EvidenceClaim,
    EvidenceClaimRef,
    EvidenceClaimSourceKind,
)
from boardroom_os.evidence.live_blackbox import (
    LiveBlackboxIntegrationEvidence,
    LiveBlackboxIntegrationEvidenceRef,
    LiveBlackboxIntegrationVerifier,
    LiveBlackboxVerifierInput,
)
from boardroom_os.evidence.service_run import (
    ServiceRunEvidence,
    ServiceRunEvidenceRef,
    stderr_ref_for_service_run,
    stdout_ref_for_service_run,
)
from boardroom_os.evidence.fallback_registry import (
    FallbackDecisionRecord,
    FallbackDecisionRecordRef,
    FallbackPolicyRegistry,
    FallbackRegistryError,
    evaluate_fallback_claim,
)
from boardroom_os.execution.context_index import ProviderAttemptRef
from boardroom_os.execution.fallback import EvidencePurpose
from boardroom_os.execution.package import ExecutionPackage
from boardroom_os.execution.verification_run import (
    VerificationRun,
    VerificationRunRef,
    VerificationRunStatus,
)
from boardroom_os.providers.attempt import (
    ProviderAttempt,
    ProviderAttemptOutcome,
    ProviderAttemptStatus,
)


_VERIFIED_EVIDENCE_TUPLE_REF_FIELDS = (
    "acceptance_refs",
    "source_surface_refs",
    "verification_run_refs",
    "service_run_refs",
    "live_blackbox_evidence_refs",
)

def _reject_malformed_verified_evidence_tuple_ref_inputs(data: Any) -> Any:
    if not isinstance(data, dict):
        return data
    for field_name in _VERIFIED_EVIDENCE_TUPLE_REF_FIELDS:
        if field_name in data and not isinstance(data[field_name], list | tuple):
            raise ValueError(f"{field_name} must be a tuple or list")
    return data


class EvidenceVerificationError(ValueError):
    pass


class VerifiedEvidenceRef(NonEmptyTextValue):
    pass


class ArtifactSha256(NonEmptyTextValue):
    @field_validator("value")
    @classmethod
    def _require_lowercase_sha256(cls, value: str) -> str:
        if not re.fullmatch(r"[0-9a-f]{64}", value):
            raise ValueError("sha256 must be a 64-character lowercase hex digest")
        return value


class FallbackDecisionRecordedRef(NonEmptyTextValue):
    pass


class ArtifactManifestEntry(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    artifact_ref: EvidenceArtifactRef
    sha256: ArtifactSha256
    producer_attempt_ref: ProviderAttemptRef
    source_ref: str
    artifact_kind: str

    @model_validator(mode="before")
    @classmethod
    def _normalize_refs(cls, data: Any) -> Any:
        return _normalize_ref_fields(
            data,
            {
                "artifact_ref": EvidenceArtifactRef,
                "sha256": ArtifactSha256,
                "producer_attempt_ref": ProviderAttemptRef,
            },
        )

    @field_validator("source_ref", "artifact_kind")
    @classmethod
    def _reject_empty_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("text fields must not be empty")
        return normalized


class ArtifactManifest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    entries: tuple[ArtifactManifestEntry, ...]

    @model_validator(mode="after")
    def _validate_entries(self) -> Self:
        if not self.entries:
            raise ValueError("entries must not be empty")

        seen: set[str] = set()
        for entry in self.entries:
            artifact_ref_value = entry.artifact_ref.value
            if artifact_ref_value in seen:
                raise ValueError("artifact_ref values must be unique")
            seen.add(artifact_ref_value)
        return self

    def by_ref(self, artifact_ref: EvidenceArtifactRef) -> ArtifactManifestEntry | None:
        for entry in self.entries:
            if entry.artifact_ref == artifact_ref:
                return entry
        return None


class EvidencePurposeRule(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    required_artifact_type: RequiredArtifactType
    allowed_purposes: tuple[EvidencePurpose, ...]

    @model_validator(mode="before")
    @classmethod
    def _normalize_refs(cls, data: Any) -> Any:
        return _normalize_ref_fields(
            data,
            {"required_artifact_type": RequiredArtifactType},
        )

    @field_validator("allowed_purposes")
    @classmethod
    def _reject_empty_allowed_purposes(
        cls,
        values: tuple[EvidencePurpose, ...],
    ) -> tuple[EvidencePurpose, ...]:
        if not values:
            raise ValueError("allowed_purposes must not be empty")
        return values


class EvidencePurposePolicy(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    rules: tuple[EvidencePurposeRule, ...]

    @model_validator(mode="after")
    def _validate_rules(self) -> Self:
        if not self.rules:
            raise ValueError("rules must not be empty")

        seen: set[str] = set()
        for rule in self.rules:
            artifact_type_value = rule.required_artifact_type.value
            if artifact_type_value in seen:
                raise ValueError("required_artifact_type values must be unique")
            seen.add(artifact_type_value)
        return self

    def has_rule(self, required_artifact_type: RequiredArtifactType) -> bool:
        return any(
            rule.required_artifact_type == required_artifact_type
            for rule in self.rules
        )

    def allows(
        self,
        required_artifact_type: RequiredArtifactType,
        purpose: EvidencePurpose,
    ) -> bool:
        for rule in self.rules:
            if rule.required_artifact_type == required_artifact_type:
                return purpose in rule.allowed_purposes
        return False


class VerifiedArtifact(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    artifact_ref: EvidenceArtifactRef
    sha256: ArtifactSha256
    producer_attempt_ref: ProviderAttemptRef
    source_ref: str
    artifact_kind: str

    @model_validator(mode="before")
    @classmethod
    def _normalize_refs(cls, data: Any) -> Any:
        return _normalize_ref_fields(
            data,
            {
                "artifact_ref": EvidenceArtifactRef,
                "sha256": ArtifactSha256,
                "producer_attempt_ref": ProviderAttemptRef,
            },
        )

    @field_validator("source_ref", "artifact_kind")
    @classmethod
    def _reject_empty_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("text fields must not be empty")
        return normalized


class EvidenceVerificationBlockerCode(StrEnum):
    MISSING_ARTIFACT = "missing_artifact"
    MISSING_PROVIDER_ATTEMPT = "missing_provider_attempt"
    PROVIDER_ATTEMPT_NOT_SUCCEEDED = "provider_attempt_not_succeeded"
    ACCEPTANCE_REF_NOT_IN_ACTIVE_CONTRACT = "acceptance_ref_not_in_active_contract"
    INACTIVE_ACCEPTANCE_CONTRACT = "inactive_acceptance_contract"
    EVIDENCE_OBLIGATION_REF_MISMATCH = "evidence_obligation_ref_mismatch"
    ACCEPTANCE_REFS_MISMATCH = "acceptance_refs_mismatch"
    SOURCE_SURFACE_REFS_MISMATCH = "source_surface_refs_mismatch"
    REQUIRED_ARTIFACT_TYPE_MISMATCH = "required_artifact_type_mismatch"
    MISSING_PURPOSE_RULE = "missing_purpose_rule"
    PURPOSE_NOT_ALLOWED = "purpose_not_allowed"
    EXTRA_ARTIFACT = "extra_artifact"
    ARTIFACT_PRODUCER_ATTEMPT_MISMATCH = "artifact_producer_attempt_mismatch"
    ARTIFACT_SOURCE_REF_MISMATCH = "artifact_source_ref_mismatch"
    MISSING_VERIFICATION_RUN = "missing_verification_run"
    VERIFICATION_RUN_NOT_PASSED = "verification_run_not_passed"
    VERIFICATION_RUN_REF_MISMATCH = "verification_run_ref_mismatch"
    VERIFICATION_RUN_ARTIFACT_REFS_MISMATCH = "verification_run_artifact_refs_mismatch"
    MISSING_SERVICE_RUN = "missing_service_run"
    SERVICE_RUN_NOT_READY = "service_run_not_ready"
    SERVICE_RUN_ARTIFACT_REFS_MISMATCH = "service_run_artifact_refs_mismatch"
    MISSING_LIVE_BLACKBOX_EVIDENCE = "missing_live_blackbox_evidence"
    LIVE_BLACKBOX_SOURCE_KIND_REQUIRED = "live_blackbox_source_kind_required"
    PRIMARY_CLAIM_WITH_FALLBACK_ATTEMPT = "primary_claim_with_fallback_attempt"
    PRIMARY_CLAIM_WITH_FALLBACK_DECISION_RECORD = "primary_claim_with_fallback_decision_record"
    FALLBACK_CLAIM_WITH_PRIMARY_ATTEMPT = "fallback_claim_with_primary_attempt"
    MISSING_FALLBACK_POLICY_REGISTRY = "missing_fallback_policy_registry"
    UNRESOLVED_FALLBACK_POLICY = "unresolved_fallback_policy"
    MISSING_FALLBACK_DECISION_RECORD = "missing_fallback_decision_record"
    MISSING_FALLBACK_DECISION_RECORDED_REF = "missing_fallback_decision_recorded_ref"
    FALLBACK_DECISION_RECORD_MISMATCH = "fallback_decision_record_mismatch"
    FALLBACK_DECISION_NOT_ALLOWED = "fallback_decision_not_allowed"
    PROVIDER_ATTEMPT_ROLE_PROMPT_HOOK_INVALID = "provider_attempt_role_prompt_hook_invalid"


class EvidenceVerificationBlocker(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    code: EvidenceVerificationBlockerCode
    message: str
    related_ref: str | None = None

    @field_validator("message")
    @classmethod
    def _reject_empty_message(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("message must not be empty")
        return normalized

    @field_validator("related_ref")
    @classmethod
    def _reject_empty_related_ref(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("related_ref must not be empty")
        return normalized


class VerifiedEvidence(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    version: Literal[1] = 1
    verified_evidence_id: VerifiedEvidenceRef
    evidence_claim_ref: EvidenceClaimRef
    evidence_obligation_ref: EvidenceObligationRef
    producer_attempt_ref: ProviderAttemptRef
    source_kind: EvidenceClaimSourceKind
    source_ref: str
    expected_purpose: EvidencePurpose
    required_artifact_type: RequiredArtifactType
    acceptance_refs: tuple[AcceptanceRef, ...]
    source_surface_refs: tuple[SourceSurfaceRef, ...]
    verified_artifacts: tuple[VerifiedArtifact, ...]
    verification_run_refs: tuple[VerificationRunRef, ...] = ()
    service_run_refs: tuple[ServiceRunEvidenceRef, ...] = ()
    live_blackbox_evidence_refs: tuple[LiveBlackboxIntegrationEvidenceRef, ...] = ()
    fallback_decision_record_ref: FallbackDecisionRecordRef | None = None
    fallback_decision_recorded_ref: FallbackDecisionRecordedRef | None = None
    verified_at: datetime

    @model_validator(mode="before")
    @classmethod
    def _normalize_refs(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        normalized = dict(_reject_malformed_verified_evidence_tuple_ref_inputs(data))
        if "verified_evidence_id" not in normalized and "evidence_claim_ref" in normalized:
            evidence_claim_ref = normalized["evidence_claim_ref"]
            if isinstance(evidence_claim_ref, EvidenceClaimRef):
                claim_ref_value = evidence_claim_ref.value
            elif isinstance(evidence_claim_ref, dict):
                claim_ref_value = evidence_claim_ref.get("value")
            else:
                claim_ref_value = str(evidence_claim_ref)
            normalized["verified_evidence_id"] = VerifiedEvidenceRef(
                value=f"verified-evidence.{claim_ref_value}"
            )
        return _normalize_ref_fields(
            normalized,
            {
                "verified_evidence_id": VerifiedEvidenceRef,
                "evidence_claim_ref": EvidenceClaimRef,
                "evidence_obligation_ref": EvidenceObligationRef,
                "producer_attempt_ref": ProviderAttemptRef,
                "required_artifact_type": RequiredArtifactType,
                "fallback_decision_record_ref": FallbackDecisionRecordRef,
                "fallback_decision_recorded_ref": FallbackDecisionRecordedRef,
            },
            {
                "acceptance_refs": AcceptanceRef,
                "source_surface_refs": SourceSurfaceRef,
                "verification_run_refs": VerificationRunRef,
                "service_run_refs": ServiceRunEvidenceRef,
                "live_blackbox_evidence_refs": LiveBlackboxIntegrationEvidenceRef,
            },
        )

    @field_validator("source_ref")
    @classmethod
    def _reject_empty_source_ref(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("source_ref must not be empty")
        return normalized

    @field_validator("acceptance_refs", "source_surface_refs", "verified_artifacts")
    @classmethod
    def _reject_empty_required_tuples(
        cls,
        values: tuple[object, ...],
    ) -> tuple[object, ...]:
        if not values:
            raise ValueError("required tuple fields must not be empty")
        return values

    @field_validator("verified_at")
    @classmethod
    def _require_timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("verified_at must be timezone-aware")
        return value


class EvidenceVerificationInput(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    claim: EvidenceClaim
    evidence_obligation: EvidenceObligation
    active_acceptance_contract: AcceptanceContract
    active_package_contract: PackageContract | None = None
    artifact_manifest: ArtifactManifest
    purpose_policy: EvidencePurposePolicy
    provider_attempts: tuple[ProviderAttempt, ...]
    execution_packages: tuple[ExecutionPackage, ...]
    role_prompt_hook_registry: RolePromptHookRegistry
    verification_runs: tuple[VerificationRun, ...] = ()
    service_runs: tuple[ServiceRunEvidence, ...] = ()
    live_blackbox_evidence: tuple[LiveBlackboxIntegrationEvidence, ...] = ()
    fallback_policy_registry: FallbackPolicyRegistry | None = None
    fallback_decision_record: FallbackDecisionRecord | None = None
    fallback_decision_recorded_ref: FallbackDecisionRecordedRef | None = None
    verified_at: datetime

    @field_validator("active_acceptance_contract", mode="wrap")
    @classmethod
    def _require_acceptance_contract_instance(
        cls,
        value: Any,
        handler: Any,
    ) -> AcceptanceContract:
        if not isinstance(value, AcceptanceContract):
            raise ValueError("active_acceptance_contract must be an AcceptanceContract")
        return value

    @field_validator("active_package_contract", mode="wrap")
    @classmethod
    def _require_package_contract_instance(
        cls,
        value: Any,
        handler: Any,
    ) -> PackageContract | None:
        if value is None:
            return None
        if not isinstance(value, PackageContract):
            raise ValueError("active_package_contract must be a PackageContract")
        return value

    @field_validator("role_prompt_hook_registry", mode="wrap")
    @classmethod
    def _require_role_prompt_hook_registry_instance(
        cls,
        value: Any,
        handler: Any,
    ) -> RolePromptHookRegistry:
        if not isinstance(value, RolePromptHookRegistry):
            raise ValueError("role_prompt_hook_registry must be a RolePromptHookRegistry")
        return value

    @field_validator("verified_at")
    @classmethod
    def _require_timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("verified_at must be timezone-aware")
        return value


class EvidenceVerificationResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    verified_evidence: VerifiedEvidence | None = None
    blockers: tuple[EvidenceVerificationBlocker, ...] = ()

    @property
    def success(self) -> bool:
        return self.verified_evidence is not None

    @model_validator(mode="after")
    def _validate_success_xor_blockers(self) -> Self:
        if self.verified_evidence is not None and self.blockers:
            raise ValueError("successful verification must not include blockers")
        if self.verified_evidence is None and not self.blockers:
            raise ValueError("failed verification must include blockers")
        return self


class EvidenceVerifier:
    def verify(self, verification_input: EvidenceVerificationInput) -> EvidenceVerificationResult:
        blockers: list[EvidenceVerificationBlocker] = []

        claim = verification_input.claim
        evidence_obligation = verification_input.evidence_obligation
        artifact_manifest = verification_input.artifact_manifest

        self._verify_active_contract(verification_input, blockers)
        self._verify_claim_obligation_alignment(claim, evidence_obligation, blockers)
        self._verify_purpose_policy(verification_input, blockers)
        self._verify_artifact_manifest(verification_input, blockers)
        self._verify_provider_attempt(verification_input, blockers)
        self._verify_verification_run(verification_input, blockers)
        self._verify_service_run(verification_input, blockers)
        self._verify_live_blackbox_evidence(verification_input, blockers)
        fallback_decision_record = self._verify_fallback_lineage(
            verification_input,
            blockers,
        )

        if blockers:
            return EvidenceVerificationResult(blockers=tuple(blockers))

        verified_artifacts = tuple(
            self._verified_artifact_from_entry(artifact_manifest.by_ref(artifact_ref))
            for artifact_ref in claim.artifact_refs
        )
        return EvidenceVerificationResult(
            verified_evidence=VerifiedEvidence(
                evidence_claim_ref=claim.evidence_claim_id,
                evidence_obligation_ref=claim.evidence_obligation_ref,
                producer_attempt_ref=claim.producer_attempt_ref,
                source_kind=claim.source_kind,
                source_ref=claim.source_ref,
                expected_purpose=claim.expected_purpose,
                required_artifact_type=claim.required_artifact_type,
                acceptance_refs=claim.acceptance_refs,
                source_surface_refs=claim.source_surface_refs,
                verified_artifacts=verified_artifacts,
                verification_run_refs=claim.verification_run_refs,
                service_run_refs=(
                    (ServiceRunEvidenceRef(value=claim.source_ref),)
                    if claim.source_kind is EvidenceClaimSourceKind.SERVICE_RUN
                    else ()
                ),
                live_blackbox_evidence_refs=(
                    (LiveBlackboxIntegrationEvidenceRef(value=claim.source_ref),)
                    if claim.source_kind is EvidenceClaimSourceKind.LIVE_BLACKBOX
                    else ()
                ),
                fallback_decision_record_ref=(
                    fallback_decision_record.fallback_decision_record_id
                    if fallback_decision_record is not None
                    else None
                ),
                fallback_decision_recorded_ref=verification_input.fallback_decision_recorded_ref,
                verified_at=verification_input.verified_at,
            )
        )

    def _verify_active_contract(
        self,
        verification_input: EvidenceVerificationInput,
        blockers: list[EvidenceVerificationBlocker],
    ) -> None:
        contract = verification_input.active_acceptance_contract
        claim = verification_input.claim
        if contract.status.value != "active":
            blockers.append(
                EvidenceVerificationBlocker(
                    code=EvidenceVerificationBlockerCode.INACTIVE_ACCEPTANCE_CONTRACT,
                    message="active_acceptance_contract must be active",
                    related_ref=contract.acceptance_contract_id.value,
                )
            )
            return

        active_acceptance_refs = {
            criterion.acceptance_ref.value for criterion in contract.criteria
        }
        for acceptance_ref in claim.acceptance_refs:
            if acceptance_ref.value not in active_acceptance_refs:
                blockers.append(
                    EvidenceVerificationBlocker(
                        code=(
                            EvidenceVerificationBlockerCode.ACCEPTANCE_REF_NOT_IN_ACTIVE_CONTRACT
                        ),
                        message="claim acceptance_ref is not in active contract",
                        related_ref=acceptance_ref.value,
                    )
                )

    def _verify_claim_obligation_alignment(
        self,
        claim: EvidenceClaim,
        evidence_obligation: EvidenceObligation,
        blockers: list[EvidenceVerificationBlocker],
    ) -> None:
        if claim.evidence_obligation_ref != evidence_obligation.evidence_obligation_id:
            blockers.append(
                EvidenceVerificationBlocker(
                    code=EvidenceVerificationBlockerCode.EVIDENCE_OBLIGATION_REF_MISMATCH,
                    message="claim evidence_obligation_ref does not match obligation id",
                    related_ref=claim.evidence_obligation_ref.value,
                )
            )
        if claim.acceptance_refs != evidence_obligation.acceptance_refs:
            blockers.append(
                EvidenceVerificationBlocker(
                    code=EvidenceVerificationBlockerCode.ACCEPTANCE_REFS_MISMATCH,
                    message="claim acceptance_refs do not match evidence obligation",
                    related_ref=claim.evidence_claim_id.value,
                )
            )
        if claim.source_surface_refs != evidence_obligation.source_surface_refs:
            blockers.append(
                EvidenceVerificationBlocker(
                    code=EvidenceVerificationBlockerCode.SOURCE_SURFACE_REFS_MISMATCH,
                    message="claim source_surface_refs do not match evidence obligation",
                    related_ref=claim.evidence_claim_id.value,
                )
            )
        if claim.required_artifact_type != evidence_obligation.required_artifact_type:
            blockers.append(
                EvidenceVerificationBlocker(
                    code=EvidenceVerificationBlockerCode.REQUIRED_ARTIFACT_TYPE_MISMATCH,
                    message="claim required_artifact_type does not match evidence obligation",
                    related_ref=claim.required_artifact_type.value,
                )
            )

    def _verify_purpose_policy(
        self,
        verification_input: EvidenceVerificationInput,
        blockers: list[EvidenceVerificationBlocker],
    ) -> None:
        claim = verification_input.claim
        purpose_policy = verification_input.purpose_policy
        if not purpose_policy.has_rule(claim.required_artifact_type):
            blockers.append(
                EvidenceVerificationBlocker(
                    code=EvidenceVerificationBlockerCode.MISSING_PURPOSE_RULE,
                    message="purpose policy has no rule for required_artifact_type",
                    related_ref=claim.required_artifact_type.value,
                )
            )
            return

        if not purpose_policy.allows(
            claim.required_artifact_type,
            claim.expected_purpose,
        ):
            blockers.append(
                EvidenceVerificationBlocker(
                    code=EvidenceVerificationBlockerCode.PURPOSE_NOT_ALLOWED,
                    message="purpose policy does not allow claim expected_purpose",
                    related_ref=claim.required_artifact_type.value,
                )
            )

    def _verify_artifact_manifest(
        self,
        verification_input: EvidenceVerificationInput,
        blockers: list[EvidenceVerificationBlocker],
    ) -> None:
        claim = verification_input.claim
        artifact_manifest = verification_input.artifact_manifest
        claim_artifact_ref_values = {artifact_ref.value for artifact_ref in claim.artifact_refs}

        for artifact_ref in claim.artifact_refs:
            entry = artifact_manifest.by_ref(artifact_ref)
            if entry is None:
                blockers.append(
                    EvidenceVerificationBlocker(
                        code=EvidenceVerificationBlockerCode.MISSING_ARTIFACT,
                        message="claim artifact_ref is missing from artifact manifest",
                        related_ref=artifact_ref.value,
                    )
                )
                continue
            if entry.producer_attempt_ref != claim.producer_attempt_ref:
                blockers.append(
                    EvidenceVerificationBlocker(
                        code=(
                            EvidenceVerificationBlockerCode.ARTIFACT_PRODUCER_ATTEMPT_MISMATCH
                        ),
                        message="artifact producer_attempt_ref does not match claim",
                        related_ref=entry.artifact_ref.value,
                    )
                )
            if entry.source_ref != claim.source_ref:
                blockers.append(
                    EvidenceVerificationBlocker(
                        code=EvidenceVerificationBlockerCode.ARTIFACT_SOURCE_REF_MISMATCH,
                        message="artifact source_ref does not match claim source_ref",
                        related_ref=entry.artifact_ref.value,
                    )
                )

        for entry in artifact_manifest.entries:
            if entry.artifact_ref.value not in claim_artifact_ref_values:
                blockers.append(
                    EvidenceVerificationBlocker(
                        code=EvidenceVerificationBlockerCode.EXTRA_ARTIFACT,
                        message="artifact manifest contains artifact outside claim artifact_refs",
                        related_ref=entry.artifact_ref.value,
                    )
                )

    def _verify_provider_attempt(
        self,
        verification_input: EvidenceVerificationInput,
        blockers: list[EvidenceVerificationBlocker],
    ) -> None:
        claim = verification_input.claim
        provider_attempt = self._provider_attempt_by_ref(
            verification_input.provider_attempts,
            claim.producer_attempt_ref,
        )
        if provider_attempt is None:
            blockers.append(
                EvidenceVerificationBlocker(
                    code=EvidenceVerificationBlockerCode.MISSING_PROVIDER_ATTEMPT,
                    message="claim producer_attempt_ref is missing from provider_attempts",
                    related_ref=claim.producer_attempt_ref.value,
                )
            )
            return

        if provider_attempt.status is not ProviderAttemptStatus.SUCCEEDED:
            blockers.append(
                EvidenceVerificationBlocker(
                    code=EvidenceVerificationBlockerCode.PROVIDER_ATTEMPT_NOT_SUCCEEDED,
                    message="provider attempt did not succeed",
                    related_ref=provider_attempt.provider_attempt_id.value,
                )
            )
        if (
            provider_attempt.role_prompt_hook_ref is None
            or provider_attempt.role_prompt_hook_version is None
            or provider_attempt.role_prompt_hook_sha256 is None
        ):
            blockers.append(
                EvidenceVerificationBlocker(
                    code=(
                        EvidenceVerificationBlockerCode
                        .PROVIDER_ATTEMPT_ROLE_PROMPT_HOOK_INVALID
                    ),
                    message="provider attempt role prompt hook audit fields are required",
                    related_ref=provider_attempt.provider_attempt_id.value,
                )
            )
            return
        if not isinstance(provider_attempt.role_prompt_hook_ref, RolePromptHookRef) or not isinstance(
            provider_attempt.role_prompt_hook_sha256,
            RolePromptHookSha256,
        ):
            blockers.append(
                EvidenceVerificationBlocker(
                    code=(
                        EvidenceVerificationBlockerCode
                        .PROVIDER_ATTEMPT_ROLE_PROMPT_HOOK_INVALID
                    ),
                    message="provider attempt role prompt hook audit fields must be typed",
                    related_ref=provider_attempt.provider_attempt_id.value,
                )
            )
            return
        try:
            hook = verification_input.role_prompt_hook_registry.require(
                provider_attempt.role_prompt_hook_ref
            )
        except ValueError:
            blockers.append(
                EvidenceVerificationBlocker(
                    code=(
                        EvidenceVerificationBlockerCode
                        .PROVIDER_ATTEMPT_ROLE_PROMPT_HOOK_INVALID
                    ),
                    message="provider attempt role prompt hook ref is not registered",
                    related_ref=provider_attempt.role_prompt_hook_ref.value,
                )
            )
            return
        if (
            provider_attempt.role_prompt_hook_version != hook.hook_version
            or provider_attempt.role_prompt_hook_sha256 != hook.content_sha256
        ):
            blockers.append(
                EvidenceVerificationBlocker(
                    code=(
                        EvidenceVerificationBlockerCode
                        .PROVIDER_ATTEMPT_ROLE_PROMPT_HOOK_INVALID
                    ),
                    message="provider attempt role prompt hook version or hash mismatch",
                    related_ref=provider_attempt.provider_attempt_id.value,
                )
            )
            return
        execution_package = self._execution_package_by_ref(
            verification_input.execution_packages,
            provider_attempt.input_package_ref,
        )
        if execution_package is None:
            blockers.append(
                EvidenceVerificationBlocker(
                    code=(
                        EvidenceVerificationBlockerCode
                        .PROVIDER_ATTEMPT_ROLE_PROMPT_HOOK_INVALID
                    ),
                    message="provider attempt input_package_ref is missing from execution_packages",
                    related_ref=provider_attempt.input_package_ref.value,
                )
            )
            return
        package_hook = execution_package.role_prompt_hook
        try:
            registered_package_hook = verification_input.role_prompt_hook_registry.require(
                package_hook.hook_ref
            )
        except ValueError:
            blockers.append(
                EvidenceVerificationBlocker(
                    code=(
                        EvidenceVerificationBlockerCode
                        .PROVIDER_ATTEMPT_ROLE_PROMPT_HOOK_INVALID
                    ),
                    message="execution package role prompt hook snapshot is not registered",
                    related_ref=execution_package.execution_package_id.value,
                )
            )
            return
        if package_hook != registered_package_hook:
            blockers.append(
                EvidenceVerificationBlocker(
                    code=(
                        EvidenceVerificationBlockerCode
                        .PROVIDER_ATTEMPT_ROLE_PROMPT_HOOK_INVALID
                    ),
                    message="execution package role prompt hook snapshot is not registered",
                    related_ref=execution_package.execution_package_id.value,
                )
            )
            return
        if (
            provider_attempt.role_prompt_hook_ref != package_hook.hook_ref
            or provider_attempt.role_prompt_hook_version != package_hook.hook_version
            or provider_attempt.role_prompt_hook_sha256 != package_hook.content_sha256
        ):
            blockers.append(
                EvidenceVerificationBlocker(
                    code=(
                        EvidenceVerificationBlockerCode
                        .PROVIDER_ATTEMPT_ROLE_PROMPT_HOOK_INVALID
                    ),
                    message=(
                        "provider attempt role prompt hook does not match "
                        "execution package snapshot"
                    ),
                    related_ref=provider_attempt.provider_attempt_id.value,
                )
            )
            return
        if (
            provider_attempt.outcome is ProviderAttemptOutcome.FALLBACK_ARTIFACT
            and claim.fallback_marker is None
        ):
            blockers.append(
                EvidenceVerificationBlocker(
                    code=(
                        EvidenceVerificationBlockerCode.PRIMARY_CLAIM_WITH_FALLBACK_ATTEMPT
                    ),
                    message="primary claim must not use a fallback provider attempt",
                    related_ref=provider_attempt.provider_attempt_id.value,
                )
            )
        if (
            provider_attempt.outcome is ProviderAttemptOutcome.PRIMARY_PROVIDER_OUTPUT
            and claim.fallback_marker is not None
        ):
            blockers.append(
                EvidenceVerificationBlocker(
                    code=EvidenceVerificationBlockerCode.FALLBACK_CLAIM_WITH_PRIMARY_ATTEMPT,
                    message="fallback claim must use a fallback provider attempt",
                    related_ref=provider_attempt.provider_attempt_id.value,
                )
            )

    def _verify_verification_run(
        self,
        verification_input: EvidenceVerificationInput,
        blockers: list[EvidenceVerificationBlocker],
    ) -> None:
        claim = verification_input.claim
        if claim.source_kind is not EvidenceClaimSourceKind.VERIFICATION_RUN:
            return

        verification_run = self._verification_run_by_ref(
            verification_input.verification_runs,
            claim.source_ref,
        )
        if verification_run is None:
            blockers.append(
                EvidenceVerificationBlocker(
                    code=EvidenceVerificationBlockerCode.MISSING_VERIFICATION_RUN,
                    message="verification_run claim source_ref is missing from verification_runs",
                    related_ref=claim.source_ref,
                )
            )
            return

        expected_verification_run_refs = (verification_run.verification_run_id,)
        if claim.verification_run_refs != expected_verification_run_refs:
            blockers.append(
                EvidenceVerificationBlocker(
                    code=EvidenceVerificationBlockerCode.VERIFICATION_RUN_REF_MISMATCH,
                    message="verification_run_refs must contain only the verified run",
                    related_ref=verification_run.verification_run_id.value,
                )
            )
        if verification_run.status is not VerificationRunStatus.PASSED:
            blockers.append(
                EvidenceVerificationBlocker(
                    code=EvidenceVerificationBlockerCode.VERIFICATION_RUN_NOT_PASSED,
                    message="verification_run must have passed status",
                    related_ref=verification_run.verification_run_id.value,
                )
            )

        expected_artifact_refs = (
            verification_run.stdout_ref.value,
            verification_run.stderr_ref.value,
        )
        claim_artifact_refs = tuple(artifact_ref.value for artifact_ref in claim.artifact_refs)
        if claim_artifact_refs != expected_artifact_refs:
            blockers.append(
                EvidenceVerificationBlocker(
                    code=(
                        EvidenceVerificationBlockerCode.VERIFICATION_RUN_ARTIFACT_REFS_MISMATCH
                    ),
                    message="verification_run claim artifact_refs must equal stdout_ref and stderr_ref",
                    related_ref=verification_run.verification_run_id.value,
                )
            )

    def _verify_service_run(
        self,
        verification_input: EvidenceVerificationInput,
        blockers: list[EvidenceVerificationBlocker],
    ) -> None:
        claim = verification_input.claim
        if (
            claim.required_artifact_type.value == "service_run"
            and claim.source_kind is not EvidenceClaimSourceKind.SERVICE_RUN
        ):
            blockers.append(
                EvidenceVerificationBlocker(
                    code=EvidenceVerificationBlockerCode.MISSING_SERVICE_RUN,
                    message="service_run artifact claims must reference service run evidence",
                    related_ref=claim.source_ref,
                )
            )
            return
        if claim.source_kind is not EvidenceClaimSourceKind.SERVICE_RUN:
            return

        service_run = self._service_run_by_ref(
            verification_input.service_runs,
            claim.source_ref,
        )
        if service_run is None:
            blockers.append(
                EvidenceVerificationBlocker(
                    code=EvidenceVerificationBlockerCode.MISSING_SERVICE_RUN,
                    message="service_run claim source_ref is missing from service_runs",
                    related_ref=claim.source_ref,
                )
            )
            return

        if service_run.probe_status_code < 200 or service_run.probe_status_code >= 300:
            blockers.append(
                EvidenceVerificationBlocker(
                    code=EvidenceVerificationBlockerCode.SERVICE_RUN_NOT_READY,
                    message="service_run must include a successful readiness probe",
                    related_ref=service_run.service_run_evidence_id.value,
                )
            )

        expected_artifact_refs = (
            service_run.stdout_ref.value,
            service_run.stderr_ref.value,
        )
        canonical_artifact_refs = (
            stdout_ref_for_service_run(service_run.service_run_evidence_id).value,
            stderr_ref_for_service_run(service_run.service_run_evidence_id).value,
        )
        claim_artifact_refs = tuple(artifact_ref.value for artifact_ref in claim.artifact_refs)
        if claim_artifact_refs != expected_artifact_refs or expected_artifact_refs != canonical_artifact_refs:
            blockers.append(
                EvidenceVerificationBlocker(
                    code=EvidenceVerificationBlockerCode.SERVICE_RUN_ARTIFACT_REFS_MISMATCH,
                    message="service_run artifact_refs must equal canonical stdout_ref and stderr_ref",
                    related_ref=service_run.service_run_evidence_id.value,
                )
            )

    def _verify_live_blackbox_evidence(
        self,
        verification_input: EvidenceVerificationInput,
        blockers: list[EvidenceVerificationBlocker],
    ) -> None:
        claim = verification_input.claim
        if (
            verification_input.evidence_obligation.required_verifier.value == "live_blackbox"
            and claim.source_kind is not EvidenceClaimSourceKind.LIVE_BLACKBOX
        ):
            blockers.append(
                EvidenceVerificationBlocker(
                    code=EvidenceVerificationBlockerCode.LIVE_BLACKBOX_SOURCE_KIND_REQUIRED,
                    message="live integration artifact claims must reference live blackbox evidence",
                    related_ref=claim.source_ref,
                )
            )
            return
        if claim.source_kind is not EvidenceClaimSourceKind.LIVE_BLACKBOX:
            return

        evidence = self._live_blackbox_evidence_by_ref(
            verification_input.live_blackbox_evidence,
            claim.source_ref,
        )
        if evidence is None:
            blockers.append(
                EvidenceVerificationBlocker(
                    code=EvidenceVerificationBlockerCode.MISSING_LIVE_BLACKBOX_EVIDENCE,
                    message="live_blackbox claim source_ref is missing from live_blackbox_evidence",
                    related_ref=claim.source_ref,
                )
            )
            return

        if verification_input.active_package_contract is None:
            blockers.append(
                EvidenceVerificationBlocker(
                    code=EvidenceVerificationBlockerCode.MISSING_LIVE_BLACKBOX_EVIDENCE,
                    message="live_blackbox evidence requires active package contract",
                    related_ref=claim.source_ref,
                )
            )
            return

        result = LiveBlackboxIntegrationVerifier().verify(
            LiveBlackboxVerifierInput(
                evidence=evidence,
                package_contract=verification_input.active_package_contract,
                service_runs=verification_input.service_runs,
            )
        )
        if not result.success:
            blocker_messages = "; ".join(
                blocker.message for blocker in result.blockers
            )
            blockers.append(
                EvidenceVerificationBlocker(
                    code=EvidenceVerificationBlockerCode.MISSING_LIVE_BLACKBOX_EVIDENCE,
                    message=(
                        "live_blackbox evidence failed blackbox validation: "
                        f"{blocker_messages}"
                    ),
                    related_ref=claim.source_ref,
                )
            )
            return

    def _verify_fallback_lineage(
        self,
        verification_input: EvidenceVerificationInput,
        blockers: list[EvidenceVerificationBlocker],
    ) -> FallbackDecisionRecord | None:
        claim = verification_input.claim
        if claim.fallback_marker is None:
            if (
                verification_input.fallback_decision_record is not None
                or verification_input.fallback_decision_recorded_ref is not None
                or verification_input.fallback_policy_registry is not None
            ):
                blockers.append(
                    EvidenceVerificationBlocker(
                        code=(
                            EvidenceVerificationBlockerCode.PRIMARY_CLAIM_WITH_FALLBACK_DECISION_RECORD
                        ),
                        message="primary claim must not include fallback decision lineage",
                        related_ref=claim.evidence_claim_id.value,
                    )
                )
            return None

        if verification_input.fallback_policy_registry is None:
            blockers.append(
                EvidenceVerificationBlocker(
                    code=EvidenceVerificationBlockerCode.MISSING_FALLBACK_POLICY_REGISTRY,
                    message="fallback claim requires fallback_policy_registry",
                    related_ref=claim.evidence_claim_id.value,
                )
            )
            return None
        if verification_input.fallback_decision_record is None:
            blockers.append(
                EvidenceVerificationBlocker(
                    code=EvidenceVerificationBlockerCode.MISSING_FALLBACK_DECISION_RECORD,
                    message="fallback claim requires fallback_decision_record",
                    related_ref=claim.evidence_claim_id.value,
                )
            )
            return None
        if verification_input.fallback_decision_recorded_ref is None:
            blockers.append(
                EvidenceVerificationBlocker(
                    code=(
                        EvidenceVerificationBlockerCode.MISSING_FALLBACK_DECISION_RECORDED_REF
                    ),
                    message="fallback claim requires fallback_decision_recorded_ref",
                    related_ref=claim.evidence_claim_id.value,
                )
            )
            return None

        try:
            expected_record = evaluate_fallback_claim(
                claim=claim,
                registry=verification_input.fallback_policy_registry,
                evaluated_at=verification_input.verified_at,
            )
        except FallbackRegistryError as error:
            blockers.append(
                EvidenceVerificationBlocker(
                    code=EvidenceVerificationBlockerCode.UNRESOLVED_FALLBACK_POLICY,
                    message=str(error),
                    related_ref=claim.fallback_marker.fallback_policy_ref.value,
                )
            )
            return None

        supplied_record = verification_input.fallback_decision_record
        if supplied_record != expected_record:
            blockers.append(
                EvidenceVerificationBlocker(
                    code=EvidenceVerificationBlockerCode.FALLBACK_DECISION_RECORD_MISMATCH,
                    message="fallback_decision_record does not match evaluated claim scope",
                    related_ref=supplied_record.fallback_decision_record_id.value,
                )
            )
            return expected_record

        if not expected_record.decision.allowed:
            blockers.append(
                EvidenceVerificationBlocker(
                    code=EvidenceVerificationBlockerCode.FALLBACK_DECISION_NOT_ALLOWED,
                    message="fallback decision does not allow verified evidence",
                    related_ref=expected_record.fallback_decision_record_id.value,
                )
            )
        return expected_record

    def _verification_run_by_ref(
        self,
        verification_runs: tuple[VerificationRun, ...],
        source_ref: str,
    ) -> VerificationRun | None:
        for verification_run in verification_runs:
            if verification_run.verification_run_id.value == source_ref:
                return verification_run
        return None

    def _service_run_by_ref(
        self,
        service_runs: tuple[ServiceRunEvidence, ...],
        source_ref: str,
    ) -> ServiceRunEvidence | None:
        for service_run in service_runs:
            if service_run.service_run_evidence_id.value == source_ref:
                return service_run
        return None

    def _live_blackbox_evidence_by_ref(
        self,
        live_blackbox_evidence: tuple[LiveBlackboxIntegrationEvidence, ...],
        source_ref: str,
    ) -> LiveBlackboxIntegrationEvidence | None:
        for evidence in live_blackbox_evidence:
            if evidence.live_blackbox_evidence_id.value == source_ref:
                return evidence
        return None

    def _provider_attempt_by_ref(
        self,
        provider_attempts: tuple[ProviderAttempt, ...],
        provider_attempt_ref: ProviderAttemptRef,
    ) -> ProviderAttempt | None:
        for provider_attempt in provider_attempts:
            if provider_attempt.provider_attempt_id == provider_attempt_ref:
                return provider_attempt
        return None

    def _execution_package_by_ref(
        self,
        execution_packages: tuple[ExecutionPackage, ...],
        execution_package_ref,
    ) -> ExecutionPackage | None:
        matches = tuple(
            execution_package
            for execution_package in execution_packages
            if execution_package.execution_package_id.value == execution_package_ref.value
        )
        if len(matches) == 1:
            return matches[0]
        return None

    def _verified_artifact_from_entry(
        self,
        entry: ArtifactManifestEntry | None,
    ) -> VerifiedArtifact:
        if entry is None:
            raise EvidenceVerificationError("artifact entry must exist after verification")
        return VerifiedArtifact(
            artifact_ref=entry.artifact_ref,
            sha256=entry.sha256,
            producer_attempt_ref=entry.producer_attempt_ref,
            source_ref=entry.source_ref,
            artifact_kind=entry.artifact_kind,
        )


__all__ = [
    "ArtifactManifest",
    "ArtifactManifestEntry",
    "ArtifactSha256",
    "EvidencePurposePolicy",
    "EvidencePurposeRule",
    "EvidenceVerificationBlocker",
    "EvidenceVerificationBlockerCode",
    "EvidenceVerificationError",
    "EvidenceVerificationInput",
    "EvidenceVerificationResult",
    "EvidenceVerifier",
    "FallbackDecisionRecordedRef",
    "VerifiedArtifact",
    "VerifiedEvidence",
    "VerifiedEvidenceRef",
]
