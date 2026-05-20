from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import ValidationError

from boardroom_os.contracts.acceptance import (
    AcceptanceContract,
    AcceptanceCriterion,
    EvidenceRequirement,
    VerificationStrategy,
    create_acceptance_contract,
)
from boardroom_os.contracts.directive import BoardDirective, DirectiveRegistry
from boardroom_os.contracts.evidence_obligation import (
    EvidenceObligation,
    RequiredArtifactType,
    RequiredVerifier,
)
from boardroom_os.contracts.project import ProjectCharterRegistry, create_project_charter
from boardroom_os.contracts.types import (
    AcceptanceRef,
    ContractId,
    ContractStatus,
    EvidenceObligationRef,
    SourceSurfaceRef,
)
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
from boardroom_os.evidence.verifier import (
    ArtifactManifest,
    ArtifactManifestEntry,
    ArtifactSha256,
    EvidencePurposePolicy,
    EvidencePurposeRule,
    EvidenceVerificationInput,
    EvidenceVerifier,
    FallbackDecisionRecordedRef,
    VerifiedEvidence,
)
from boardroom_os.execution.context_index import ProviderAttemptRef
from boardroom_os.execution.fallback import (
    EvidencePurpose,
    FallbackEvidenceDecision,
    FallbackKind,
    FallbackPolicy,
)
from boardroom_os.execution.package import FallbackPolicyRef
from boardroom_os.execution.verification_run import (
    CommandOutputRef,
    VerificationRun,
    VerificationRunRef,
    VerificationRunStatus,
)
from boardroom_os.providers.attempt import (
    ProviderAttempt,
    ProviderAttemptOutcome,
    ProviderAttemptStatus,
)

_VALID_SHA256 = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
_VERIFY_ERRORS = (ValueError, ValidationError)


def _acceptance_ref(value: str = "AC-BACKEND") -> AcceptanceRef:
    return AcceptanceRef(value=value)


def _source_surface_ref(value: str = "surface.backend") -> SourceSurfaceRef:
    return SourceSurfaceRef(value=value)


def _verification_run_ref(value: str = "verification-run.backend") -> VerificationRunRef:
    return VerificationRunRef(value=value)


def _command_output_ref(value: str) -> CommandOutputRef:
    return CommandOutputRef(value=value)


def _provider_attempt_ref(value: str = "provider-attempt.backend") -> ProviderAttemptRef:
    return ProviderAttemptRef(value=value)


def _artifact_ref(value: str = "artifact.parsed.backend") -> EvidenceArtifactRef:
    return EvidenceArtifactRef(value=value)


def _criterion(acceptance_ref: str = "AC-BACKEND") -> AcceptanceCriterion:
    return AcceptanceCriterion(
        acceptance_ref=_acceptance_ref(acceptance_ref),
        statement="Backend source satisfies the active acceptance criterion.",
        evidence_required=(EvidenceRequirement(value="source patch with content hash"),),
        blocking=True,
        source_surface_refs=(_source_surface_ref(),),
        verification_strategy=VerificationStrategy(value="verify manifest hash and provider lineage"),
    )


def _charter_registry() -> ProjectCharterRegistry:
    directive = BoardDirective(
        board_directive_id=ContractId(value="directive.backend"),
        source_type="natural_language",
        content_ref=ContractId(value="content.backend"),
        received_at=datetime(2026, 5, 20, 8, 0, tzinfo=UTC),
        requester_ref=ContractId(value="human-board"),
    )
    charter = create_project_charter(
        registry=DirectiveRegistry.from_directives(directive),
        project_charter_id=ContractId(value="project.charter.backend"),
        board_directive_ref=ContractId(value="directive.backend"),
        project_goal="Generate auditable backend source evidence.",
        delivery_type="generated_project_package",
        non_goals=("Do not read legacy runtime.",),
        constraints=("Evidence first.",),
        risks=("Synthetic evidence must be blocked.",),
        success_summary="Backend evidence is verifiable.",
    )
    return ProjectCharterRegistry.from_charters(charter)


def _acceptance_contract(
    *,
    status: ContractStatus | None = None,
    criteria: tuple[AcceptanceCriterion, ...] | None = None,
) -> AcceptanceContract:
    return create_acceptance_contract(
        registry=_charter_registry(),
        acceptance_contract_id=ContractId(value="contract.acceptance.backend"),
        project_charter_ref=ContractId(value="project.charter.backend"),
        status=status or ContractStatus.active(),
        criteria=criteria or (_criterion(),),
    )


def _evidence_obligation(
    *,
    acceptance_refs: tuple[AcceptanceRef, ...] | None = None,
    source_surface_refs: tuple[SourceSurfaceRef, ...] | None = None,
    required_artifact_type: RequiredArtifactType | None = None,
) -> EvidenceObligation:
    return EvidenceObligation(
        evidence_obligation_id=EvidenceObligationRef(value="evidence.source.backend"),
        acceptance_refs=acceptance_refs or (_acceptance_ref(),),
        source_surface_refs=source_surface_refs or (_source_surface_ref(),),
        required_artifact_type=required_artifact_type
        or RequiredArtifactType(value="source_patch"),
        required_verifier=RequiredVerifier(value="verifier.source.patch"),
        blocking=True,
    )


def _claim(
    *,
    evidence_obligation_ref: EvidenceObligationRef | None = None,
    source_kind: EvidenceClaimSourceKind = EvidenceClaimSourceKind.WORK_PRODUCT,
    source_ref: str = "work-product.backend",
    expected_purpose: EvidencePurpose = EvidencePurpose.IMPLEMENTATION,
    required_artifact_type: RequiredArtifactType | None = None,
    artifact_refs: tuple[EvidenceArtifactRef, ...] | None = None,
    acceptance_refs: tuple[AcceptanceRef, ...] | None = None,
    source_surface_refs: tuple[SourceSurfaceRef, ...] | None = None,
    verification_run_refs: tuple[VerificationRunRef, ...] | None = None,
    fallback_marker: object | None = None,
    producer_attempt_ref: ProviderAttemptRef | None = None,
    evidence_claim_id: str = "evidence-claim.work_product.backend",
) -> EvidenceClaim:
    fields: dict[str, object] = {
        "evidence_claim_id": EvidenceClaimRef(value=evidence_claim_id),
        "evidence_obligation_ref": evidence_obligation_ref
        or EvidenceObligationRef(value="evidence.source.backend"),
        "producer_attempt_ref": producer_attempt_ref or _provider_attempt_ref(),
        "source_kind": source_kind,
        "source_ref": source_ref,
        "expected_purpose": expected_purpose,
        "required_artifact_type": required_artifact_type
        or RequiredArtifactType(value="source_patch"),
        "acceptance_refs": acceptance_refs or (_acceptance_ref(),),
        "source_surface_refs": source_surface_refs or (_source_surface_ref(),),
        "artifact_refs": artifact_refs or (_artifact_ref(),),
        "summary": "Source patch evidence claim.",
    }
    if verification_run_refs is not None:
        fields["verification_run_refs"] = verification_run_refs
    if fallback_marker is not None:
        fields["fallback_marker"] = fallback_marker
    return EvidenceClaim(**fields)


def _provider_attempt(
    *,
    provider_attempt_ref: str = "provider-attempt.backend",
    status: ProviderAttemptStatus = ProviderAttemptStatus.SUCCEEDED,
    outcome: ProviderAttemptOutcome = ProviderAttemptOutcome.PRIMARY_PROVIDER_OUTPUT,
) -> ProviderAttempt:
    fields: dict[str, object] = {
        "provider_attempt_id": provider_attempt_ref,
        "provider": "anthropic",
        "model": "claude-opus-4-7",
        "reasoning_effort": "medium",
        "input_package_ref": "exec.backend.1",
        "seat_ref": "seat.worker.backend",
        "status": status,
        "outcome": outcome,
        "started_at": datetime(2026, 5, 20, 9, 0, tzinfo=UTC),
        "finished_at": datetime(2026, 5, 20, 9, 1, tzinfo=UTC),
    }
    if outcome is ProviderAttemptOutcome.FALLBACK_ARTIFACT:
        fields["fallback_kind"] = FallbackKind.TEST_ONLY_SIMULATION
    if status is ProviderAttemptStatus.SUCCEEDED:
        fields.update(
            {
                "raw_output_ref": "artifact.raw.backend",
                "parsed_output_ref": "artifact.parsed.backend",
            }
        )
    else:
        fields["failure_kind"] = "provider_error"
    return ProviderAttempt(**fields)


def _manifest_entry(
    *,
    artifact_ref: EvidenceArtifactRef | None = None,
    sha256: ArtifactSha256 | None = None,
    producer_attempt_ref: ProviderAttemptRef | None = None,
    source_ref: str = "work-product.backend",
    artifact_kind: str = "source_patch",
) -> ArtifactManifestEntry:
    return ArtifactManifestEntry(
        artifact_ref=artifact_ref or _artifact_ref(),
        sha256=sha256 or ArtifactSha256(value=_VALID_SHA256),
        producer_attempt_ref=producer_attempt_ref or _provider_attempt_ref(),
        source_ref=source_ref,
        artifact_kind=artifact_kind,
    )


def _artifact_manifest(
    entries: tuple[ArtifactManifestEntry, ...] | None = None,
) -> ArtifactManifest:
    return ArtifactManifest(entries=entries or (_manifest_entry(),))


def _verification_run(
    *,
    verification_run_ref: VerificationRunRef | None = None,
    status: VerificationRunStatus = VerificationRunStatus.PASSED,
    stdout_ref: CommandOutputRef | None = None,
    stderr_ref: CommandOutputRef | None = None,
) -> VerificationRun:
    run_ref = verification_run_ref or _verification_run_ref()
    return VerificationRun(
        verification_run_id=run_ref,
        execution_package_ref="exec.backend.1",
        ticket_ref="ticket.backend.1",
        command_id="command.pytest.backend",
        command=("python", "-m", "pytest"),
        cwd="/workspace/generated/backend",
        exit_code=0 if status is VerificationRunStatus.PASSED else 1,
        status=status,
        stdout_ref=stdout_ref or _command_output_ref(f"command-output.{run_ref.value}.stdout"),
        stderr_ref=stderr_ref or _command_output_ref(f"command-output.{run_ref.value}.stderr"),
        duration_ms=1000,
        started_at=datetime(2026, 5, 20, 9, 0, tzinfo=UTC),
        finished_at=datetime(2026, 5, 20, 9, 1, tzinfo=UTC),
        runner_ref="runner.local",
        environment_profile_ref="env.python",
        workspace_snapshot_ref="workspace.snapshot.backend",
    )


def _verification_run_claim(
    *,
    verification_run: VerificationRun | None = None,
    source_ref: str | None = None,
    artifact_refs: tuple[EvidenceArtifactRef, ...] | None = None,
) -> EvidenceClaim:
    run = verification_run or _verification_run()
    return _claim(
        source_kind=EvidenceClaimSourceKind.VERIFICATION_RUN,
        source_ref=source_ref or run.verification_run_id.value,
        artifact_refs=artifact_refs
        or (
            EvidenceArtifactRef(value=run.stdout_ref.value),
            EvidenceArtifactRef(value=run.stderr_ref.value),
        ),
        verification_run_refs=(run.verification_run_id,),
    )


def _verification_run_manifest(run: VerificationRun) -> ArtifactManifest:
    return _artifact_manifest(
        entries=(
            _manifest_entry(
                artifact_ref=EvidenceArtifactRef(value=run.stdout_ref.value),
                source_ref=run.verification_run_id.value,
                artifact_kind="command_stdout",
            ),
            _manifest_entry(
                artifact_ref=EvidenceArtifactRef(value=run.stderr_ref.value),
                source_ref=run.verification_run_id.value,
                artifact_kind="command_stderr",
            ),
        )
    )


def _purpose_policy(
    rules: tuple[EvidencePurposeRule, ...] | None = None,
) -> EvidencePurposePolicy:
    return EvidencePurposePolicy(
        rules=rules
        or (
            EvidencePurposeRule(
                required_artifact_type=RequiredArtifactType(value="source_patch"),
                allowed_purposes=(EvidencePurpose.IMPLEMENTATION,),
            ),
        )
    )


def _input(
    *,
    claim: EvidenceClaim | None = None,
    evidence_obligation: EvidenceObligation | None = None,
    active_acceptance_contract: AcceptanceContract | None = None,
    artifact_manifest: ArtifactManifest | None = None,
    purpose_policy: EvidencePurposePolicy | None = None,
    provider_attempts: tuple[ProviderAttempt, ...] | None = None,
    verification_runs: tuple[Any, ...] | None = None,
    verified_at: datetime | None = None,
    fallback_policy_registry: FallbackPolicyRegistry | None = None,
    fallback_decision_record: FallbackDecisionRecord | None = None,
    fallback_decision_recorded_ref: FallbackDecisionRecordedRef | None = None,
) -> EvidenceVerificationInput:
    return EvidenceVerificationInput(
        claim=claim or _claim(),
        evidence_obligation=evidence_obligation or _evidence_obligation(),
        active_acceptance_contract=active_acceptance_contract or _acceptance_contract(),
        artifact_manifest=artifact_manifest or _artifact_manifest(),
        purpose_policy=purpose_policy or _purpose_policy(),
        provider_attempts=(
            provider_attempts if provider_attempts is not None else (_provider_attempt(),)
        ),
        verification_runs=verification_runs if verification_runs is not None else (),
        fallback_policy_registry=fallback_policy_registry,
        fallback_decision_record=fallback_decision_record,
        fallback_decision_recorded_ref=fallback_decision_recorded_ref,
        verified_at=verified_at or datetime(2026, 5, 20, 9, 2, tzinfo=UTC),
    )



def _fallback_marker(
    *,
    fallback_policy_ref: str = "fallback.hash-manifest",
    fallback_kind: FallbackKind = FallbackKind.CONTRACT_ALLOWED_DETERMINISTIC_TRANSFORM,
    producer_attempt_ref: str = "provider-attempt.backend",
) -> FallbackLineageMarker:
    return FallbackLineageMarker(
        fallback_policy_ref=FallbackPolicyRef(value=fallback_policy_ref),
        fallback_kind=fallback_kind,
        producer_attempt_ref=ProviderAttemptRef(value=producer_attempt_ref),
    )


def _fallback_policy(
    *,
    fallback_policy_ref: str = "fallback.hash-manifest",
    allowed_artifact_types: tuple[RequiredArtifactType, ...] | None = None,
    allowed_acceptance_refs: tuple[AcceptanceRef, ...] | None = None,
) -> FallbackPolicy:
    return FallbackPolicy(
        fallback_policy_ref=FallbackPolicyRef(value=fallback_policy_ref),
        kind=FallbackKind.CONTRACT_ALLOWED_DETERMINISTIC_TRANSFORM,
        allowed_artifact_types=allowed_artifact_types
        or (RequiredArtifactType(value="source_patch"),),
        allowed_acceptance_refs=allowed_acceptance_refs or (_acceptance_ref(),),
    )


def _fallback_registry(
    policies: tuple[FallbackPolicy, ...] | None = None,
) -> FallbackPolicyRegistry:
    return FallbackPolicyRegistry(policies=policies or (_fallback_policy(),))


def _fallback_claim(
    *,
    evidence_claim_id: str = "evidence-claim.fallback.backend",
    expected_purpose: EvidencePurpose = EvidencePurpose.DETERMINISTIC,
    required_artifact_type: RequiredArtifactType | None = None,
    acceptance_refs: tuple[AcceptanceRef, ...] | None = None,
    source_surface_refs: tuple[SourceSurfaceRef, ...] | None = None,
    fallback_marker: FallbackLineageMarker | None = None,
) -> EvidenceClaim:
    return _claim(
        evidence_claim_id=evidence_claim_id,
        expected_purpose=expected_purpose,
        required_artifact_type=required_artifact_type
        or RequiredArtifactType(value="source_patch"),
        acceptance_refs=acceptance_refs or (_acceptance_ref(),),
        source_surface_refs=source_surface_refs or (_source_surface_ref(),),
        fallback_marker=fallback_marker or _fallback_marker(),
    )


def _fallback_decision_record(
    claim: EvidenceClaim | None = None,
    *,
    registry: FallbackPolicyRegistry | None = None,
    evaluated_at: datetime | None = None,
    decision_record_id: FallbackDecisionRecordRef | None = None,
) -> FallbackDecisionRecord:
    return evaluate_fallback_claim(
        claim=claim or _fallback_claim(),
        registry=registry or _fallback_registry(),
        evaluated_at=evaluated_at or datetime(2026, 5, 20, 9, 2, tzinfo=UTC),
        decision_record_id=decision_record_id,
    )


def _fallback_decision_recorded_ref(
    value: str = "audit.fallback-decision.backend",
) -> FallbackDecisionRecordedRef:
    return FallbackDecisionRecordedRef(value=value)


def _fallback_input(
    *,
    claim: EvidenceClaim | None = None,
    registry: FallbackPolicyRegistry | None = None,
    decision_record: FallbackDecisionRecord | None = None,
    decision_recorded_ref: FallbackDecisionRecordedRef | None = None,
    provider_attempt: ProviderAttempt | None = None,
    verified_at: datetime | None = None,
) -> EvidenceVerificationInput:
    resolved_claim = claim or _fallback_claim()
    resolved_registry = registry or _fallback_registry()
    resolved_verified_at = verified_at or datetime(2026, 5, 20, 9, 2, tzinfo=UTC)
    return _input(
        claim=resolved_claim,
        evidence_obligation=_evidence_obligation(
            acceptance_refs=resolved_claim.acceptance_refs,
            source_surface_refs=resolved_claim.source_surface_refs,
            required_artifact_type=resolved_claim.required_artifact_type,
        ),
        active_acceptance_contract=_acceptance_contract(
            criteria=tuple(
                _criterion(acceptance_ref.value)
                for acceptance_ref in resolved_claim.acceptance_refs
            )
        ),
        purpose_policy=_purpose_policy(
            rules=(
                EvidencePurposeRule(
                    required_artifact_type=resolved_claim.required_artifact_type,
                    allowed_purposes=(resolved_claim.expected_purpose,),
                ),
            )
        ),
        provider_attempts=(
            provider_attempt
            or _provider_attempt(outcome=ProviderAttemptOutcome.FALLBACK_ARTIFACT),
        ),
        fallback_policy_registry=resolved_registry,
        fallback_decision_record=(
            decision_record
            if decision_record is not None
            else _fallback_decision_record(
                claim=resolved_claim,
                registry=resolved_registry,
                evaluated_at=resolved_verified_at,
            )
        ),
        fallback_decision_recorded_ref=decision_recorded_ref
        or _fallback_decision_recorded_ref(),
        verified_at=resolved_verified_at,
    )



def _verify(**overrides: object) -> object:
    return EvidenceVerifier().verify(_input(**overrides))


def _blocker_codes(result: object) -> tuple[str, ...]:
    codes: list[str] = []
    for blocker in result.blockers:
        code = getattr(blocker, "code")
        codes.append(str(getattr(code, "value", code)))
    return tuple(codes)


def _assert_blocked(result: object, expected_code: str) -> None:
    assert result.verified_evidence is None
    assert any(expected_code in code for code in _blocker_codes(result))


def test_evidence_verification_input_rejects_invalid_acceptance_contract() -> None:
    with pytest.raises(_VERIFY_ERRORS):
        EvidenceVerificationInput(
            claim=_claim(),
            evidence_obligation=_evidence_obligation(),
            active_acceptance_contract={"status": "active"},
            artifact_manifest=_artifact_manifest(),
            purpose_policy=_purpose_policy(),
            provider_attempts=(_provider_attempt(),),
            verified_at=datetime(2026, 5, 20, 9, 2, tzinfo=UTC),
        )


@pytest.mark.parametrize(
    ("field_name", "field_value"),
    (
        ("acceptance_refs", "AC-BACKEND"),
        ("source_surface_refs", "surface.backend"),
        ("verification_run_refs", "verification-run.backend"),
    ),
)
def test_verified_evidence_rejects_string_tuple_ref_fields(
    field_name: str,
    field_value: str,
) -> None:
    fields: dict[str, object] = {
        "evidence_claim_ref": _claim().evidence_claim_id,
        "evidence_obligation_ref": _evidence_obligation().evidence_obligation_id,
        "producer_attempt_ref": _provider_attempt_ref(),
        "source_kind": EvidenceClaimSourceKind.WORK_PRODUCT,
        "source_ref": "work-product.backend",
        "expected_purpose": EvidencePurpose.IMPLEMENTATION,
        "required_artifact_type": RequiredArtifactType(value="source_patch"),
        "acceptance_refs": (_acceptance_ref(),),
        "source_surface_refs": (_source_surface_ref(),),
        "verified_artifacts": (
            {
                "artifact_ref": _artifact_ref(),
                "sha256": ArtifactSha256(value=_VALID_SHA256),
                "producer_attempt_ref": _provider_attempt_ref(),
                "source_ref": "work-product.backend",
                "artifact_kind": "source_patch",
            },
        ),
        "verification_run_refs": (),
        "verified_at": datetime(2026, 5, 20, 9, 2, tzinfo=UTC),
    }
    fields[field_name] = field_value

    with pytest.raises(_VERIFY_ERRORS, match=field_name):
        VerifiedEvidence(**fields)


def test_verifier_rejects_missing_artifact_manifest_entry() -> None:
    missing_artifact_ref = _artifact_ref("artifact.parsed.backend")
    unrelated_artifact_ref = _artifact_ref("artifact.parsed.other")

    result = _verify(
        claim=_claim(artifact_refs=(missing_artifact_ref,)),
        artifact_manifest=_artifact_manifest(
            entries=(
                _manifest_entry(artifact_ref=unrelated_artifact_ref),
            )
        ),
    )

    _assert_blocked(result, "missing_artifact")


def test_artifact_manifest_entry_rejects_missing_sha256() -> None:
    with pytest.raises(_VERIFY_ERRORS, match="sha256"):
        ArtifactManifestEntry(
            artifact_ref=_artifact_ref(),
            producer_attempt_ref=_provider_attempt_ref(),
            source_ref="work-product.backend",
            artifact_kind="source_patch",
        )


def test_artifact_sha256_rejects_uppercase_or_non_64_digit_digest() -> None:
    malformed_digests = (
        "E3B0C44298FC1C149AFBF4C8996FB92427AE41E4649B934CA495991B7852B855",
        "abc123",
    )

    for digest in malformed_digests:
        with pytest.raises(_VERIFY_ERRORS, match="sha256|SHA-256|hex|64"):
            ArtifactSha256(value=digest)


def test_verifier_rejects_provider_zero_attempt_for_implementation_evidence() -> None:
    result = _verify(provider_attempts=())

    _assert_blocked(result, "missing_provider_attempt")


def test_verifier_rejects_failed_provider_attempt_for_implementation_evidence() -> None:
    result = _verify(
        provider_attempts=(_provider_attempt(status=ProviderAttemptStatus.FAILED),)
    )

    _assert_blocked(result, "provider_attempt_not_succeeded")


def test_verifier_rejects_acceptance_ref_outside_active_contract() -> None:
    outside_ref = _acceptance_ref("AC-OUTSIDE")

    result = _verify(
        evidence_obligation=_evidence_obligation(acceptance_refs=(outside_ref,)),
        claim=_claim(acceptance_refs=(outside_ref,)),
    )

    _assert_blocked(result, "acceptance_ref_not_in_active_contract")


def test_verifier_rejects_inactive_acceptance_contract() -> None:
    result = _verify(
        active_acceptance_contract=_acceptance_contract(status=ContractStatus.draft())
    )

    _assert_blocked(result, "inactive_acceptance_contract")



def test_verifier_rejects_evidence_obligation_ref_mismatch() -> None:
    result = _verify(
        claim=_claim(
            evidence_obligation_ref=EvidenceObligationRef(value="evidence.source.other")
        )
    )

    _assert_blocked(result, "evidence_obligation_ref_mismatch")


def test_verifier_rejects_acceptance_refs_mismatch() -> None:
    result = _verify(
        claim=_claim(acceptance_refs=(_acceptance_ref("AC-FRONTEND"),))
    )

    _assert_blocked(result, "acceptance_refs_mismatch")


def test_verifier_rejects_source_surface_refs_mismatch() -> None:
    result = _verify(
        claim=_claim(source_surface_refs=(_source_surface_ref("surface.frontend"),))
    )

    _assert_blocked(result, "source_surface_refs_mismatch")


def test_verifier_rejects_required_artifact_type_mismatch() -> None:
    result = _verify(
        claim=_claim(required_artifact_type=RequiredArtifactType(value="test_report"))
    )

    _assert_blocked(result, "required_artifact_type_mismatch")


def test_verifier_rejects_purpose_artifact_type_mismatch() -> None:
    result = _verify(
        claim=_claim(required_artifact_type=RequiredArtifactType(value="test_report")),
        evidence_obligation=_evidence_obligation(
            required_artifact_type=RequiredArtifactType(value="test_report")
        ),
    )

    _assert_blocked(result, "missing_purpose_rule")


def test_verifier_rejects_manifest_with_extra_artifact_ref() -> None:
    result = _verify(
        artifact_manifest=_artifact_manifest(
            entries=(
                _manifest_entry(),
                _manifest_entry(
                    artifact_ref=_artifact_ref("artifact.parsed.extra"),
                    source_ref="work-product.backend",
                ),
            )
        )
    )

    _assert_blocked(result, "extra_artifact")


def test_verifier_rejects_synthetic_verification_without_run_record() -> None:
    run = _verification_run()

    result = _verify(
        claim=_verification_run_claim(verification_run=run),
        artifact_manifest=_verification_run_manifest(run),
        verification_runs=(),
    )

    _assert_blocked(result, "missing_verification_run")


def test_verifier_rejects_failed_verification_run() -> None:
    run = _verification_run(status=VerificationRunStatus.FAILED)

    result = _verify(
        claim=_verification_run_claim(verification_run=run),
        artifact_manifest=_verification_run_manifest(run),
        verification_runs=(run,),
    )

    _assert_blocked(result, "verification_run_not_passed")


def test_verifier_rejects_verification_run_without_stdout_stderr_hashes() -> None:
    run = _verification_run()
    claim = _verification_run_claim(verification_run=run)

    result = _verify(
        claim=claim,
        artifact_manifest=_artifact_manifest(
            entries=(
                _manifest_entry(
                    artifact_ref=EvidenceArtifactRef(value=run.stdout_ref.value),
                    source_ref=run.verification_run_id.value,
                    artifact_kind="command_stdout",
                ),
            )
        ),
        verification_runs=(run,),
    )

    _assert_blocked(result, "missing_artifact")


def test_verifier_rejects_verification_run_artifact_ref_mismatch() -> None:
    run = _verification_run()
    claim = _verification_run_claim(
        verification_run=run,
        artifact_refs=(
            EvidenceArtifactRef(value=run.stdout_ref.value),
            EvidenceArtifactRef(value="command-output.verification-run.backend.trace"),
        ),
    )

    result = _verify(
        claim=claim,
        artifact_manifest=_artifact_manifest(
            entries=(
                _manifest_entry(
                    artifact_ref=EvidenceArtifactRef(value=run.stdout_ref.value),
                    source_ref=run.verification_run_id.value,
                    artifact_kind="command_stdout",
                ),
                _manifest_entry(
                    artifact_ref=EvidenceArtifactRef(
                        value="command-output.verification-run.backend.trace"
                    ),
                    source_ref=run.verification_run_id.value,
                    artifact_kind="command_trace",
                ),
            )
        ),
        verification_runs=(run,),
    )

    _assert_blocked(result, "verification_run_artifact_refs_mismatch")


def test_verifier_rejects_verification_run_claim_with_extra_run_ref() -> None:
    run = _verification_run()
    claim = _claim(
        source_kind=EvidenceClaimSourceKind.VERIFICATION_RUN,
        source_ref=run.verification_run_id.value,
        artifact_refs=(
            EvidenceArtifactRef(value=run.stdout_ref.value),
            EvidenceArtifactRef(value=run.stderr_ref.value),
        ),
        verification_run_refs=(
            run.verification_run_id,
            _verification_run_ref("verification-run.backend.extra"),
        ),
    )

    result = _verify(
        claim=claim,
        artifact_manifest=_verification_run_manifest(run),
        verification_runs=(run,),
    )

    _assert_blocked(result, "verification_run_ref_mismatch")


def test_verifier_rejects_primary_claim_with_fallback_attempt() -> None:
    result = _verify(
        provider_attempts=(
            _provider_attempt(outcome=ProviderAttemptOutcome.FALLBACK_ARTIFACT),
        )
    )

    _assert_blocked(result, "primary_claim_with_fallback_attempt")


def test_verifier_rejects_primary_claim_with_fallback_decision_record() -> None:
    fallback_claim = _fallback_claim()

    result = _verify(
        fallback_decision_record=_fallback_decision_record(claim=fallback_claim),
        fallback_decision_recorded_ref=_fallback_decision_recorded_ref(),
    )

    _assert_blocked(result, "primary_claim_with_fallback_decision_record")


def test_verifier_rejects_fallback_claim_with_primary_attempt() -> None:
    claim = _fallback_claim()

    result = EvidenceVerifier().verify(
        _fallback_input(
            claim=claim,
            provider_attempt=_provider_attempt(
                outcome=ProviderAttemptOutcome.PRIMARY_PROVIDER_OUTPUT,
            ),
        )
    )

    _assert_blocked(result, "fallback_claim_with_primary_attempt")


def test_verifier_rejects_fallback_claim_without_registry() -> None:
    claim = _fallback_claim()

    result = _verify(
        claim=claim,
        provider_attempts=(
            _provider_attempt(outcome=ProviderAttemptOutcome.FALLBACK_ARTIFACT),
        ),
        fallback_decision_record=_fallback_decision_record(claim=claim),
        fallback_decision_recorded_ref=_fallback_decision_recorded_ref(),
    )

    _assert_blocked(result, "missing_fallback_policy_registry")


def test_verifier_rejects_fallback_claim_with_unresolved_policy() -> None:
    claim = _fallback_claim(
        fallback_marker=_fallback_marker(fallback_policy_ref="fallback.missing"),
    )

    result = _verify(
        claim=claim,
        purpose_policy=_purpose_policy(
            rules=(
                EvidencePurposeRule(
                    required_artifact_type=claim.required_artifact_type,
                    allowed_purposes=(claim.expected_purpose,),
                ),
            )
        ),
        provider_attempts=(
            _provider_attempt(outcome=ProviderAttemptOutcome.FALLBACK_ARTIFACT),
        ),
        fallback_policy_registry=_fallback_registry(),
        fallback_decision_record=_fallback_decision_record(claim=_fallback_claim()),
        fallback_decision_recorded_ref=_fallback_decision_recorded_ref(),
    )

    _assert_blocked(result, "unresolved_fallback_policy")


def test_verifier_rejects_fallback_claim_without_decision_record() -> None:
    claim = _fallback_claim()

    result = _verify(
        claim=claim,
        purpose_policy=_purpose_policy(
            rules=(
                EvidencePurposeRule(
                    required_artifact_type=claim.required_artifact_type,
                    allowed_purposes=(claim.expected_purpose,),
                ),
            )
        ),
        provider_attempts=(
            _provider_attempt(outcome=ProviderAttemptOutcome.FALLBACK_ARTIFACT),
        ),
        fallback_policy_registry=_fallback_registry(),
        fallback_decision_recorded_ref=_fallback_decision_recorded_ref(),
    )

    _assert_blocked(result, "missing_fallback_decision_record")


def test_verifier_rejects_fallback_claim_without_decision_recorded_ref() -> None:
    claim = _fallback_claim()

    result = _verify(
        claim=claim,
        purpose_policy=_purpose_policy(
            rules=(
                EvidencePurposeRule(
                    required_artifact_type=claim.required_artifact_type,
                    allowed_purposes=(claim.expected_purpose,),
                ),
            )
        ),
        provider_attempts=(
            _provider_attempt(outcome=ProviderAttemptOutcome.FALLBACK_ARTIFACT),
        ),
        fallback_policy_registry=_fallback_registry(),
        fallback_decision_record=_fallback_decision_record(claim=claim),
    )

    _assert_blocked(result, "missing_fallback_decision_recorded_ref")


def test_verifier_rejects_fallback_decision_record_scope_mismatch() -> None:
    claim = _fallback_claim()
    mismatched_record = _fallback_decision_record(
        claim=_fallback_claim(evidence_claim_id="evidence-claim.fallback.other")
    )

    result = EvidenceVerifier().verify(
        _fallback_input(
            claim=claim,
            decision_record=mismatched_record,
        )
    )

    _assert_blocked(result, "fallback_decision_record_mismatch")


def test_verifier_rejects_fallback_decision_allowed_false() -> None:
    claim = _fallback_claim(expected_purpose=EvidencePurpose.IMPLEMENTATION)
    blocked_record = _fallback_decision_record(claim=claim)

    result = EvidenceVerifier().verify(
        _fallback_input(
            claim=claim,
            decision_record=blocked_record,
        )
    )

    _assert_blocked(result, "fallback_decision_not_allowed")


def test_verifier_uses_verified_at_for_fallback_decision_evaluation() -> None:
    claim = _fallback_claim()
    stale_record = _fallback_decision_record(
        claim=claim,
        evaluated_at=datetime(2026, 5, 20, 8, 59, tzinfo=UTC),
    )

    result = EvidenceVerifier().verify(
        _fallback_input(
            claim=claim,
            decision_record=stale_record,
            verified_at=datetime(2026, 5, 20, 9, 2, tzinfo=UTC),
        )
    )

    _assert_blocked(result, "fallback_decision_record_mismatch")


def test_verifier_uses_evaluate_fallback_claim_once_with_full_scope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    claim = _fallback_claim(
        acceptance_refs=(
            _acceptance_ref("AC-BACKEND"),
            _acceptance_ref("AC-AUDIT"),
        )
    )
    registry = _fallback_registry(
        policies=(
            _fallback_policy(
                allowed_acceptance_refs=(
                    _acceptance_ref("AC-BACKEND"),
                    _acceptance_ref("AC-AUDIT"),
                )
            ),
        )
    )
    verified_at = datetime(2026, 5, 20, 9, 3, tzinfo=UTC)
    expected_record = _fallback_decision_record(
        claim=claim,
        registry=registry,
        evaluated_at=verified_at,
    )
    calls: list[dict[str, object]] = []

    def _fake_evaluate_fallback_claim(
        *,
        claim: EvidenceClaim,
        registry: FallbackPolicyRegistry,
        evaluated_at: datetime,
    ) -> FallbackDecisionRecord:
        calls.append(
            {
                "claim": claim,
                "registry": registry,
                "evaluated_at": evaluated_at,
                "acceptance_refs": claim.acceptance_refs,
                "source_surface_refs": claim.source_surface_refs,
                "required_artifact_type": claim.required_artifact_type,
            }
        )
        return expected_record

    monkeypatch.setattr(
        "boardroom_os.evidence.verifier.evaluate_fallback_claim",
        _fake_evaluate_fallback_claim,
    )

    result = EvidenceVerifier().verify(
        _fallback_input(
            claim=claim,
            registry=registry,
            decision_record=expected_record,
            verified_at=verified_at,
        )
    )

    assert result.verified_evidence is not None
    assert calls == [
        {
            "claim": claim,
            "registry": registry,
            "evaluated_at": verified_at,
            "acceptance_refs": claim.acceptance_refs,
            "source_surface_refs": claim.source_surface_refs,
            "required_artifact_type": claim.required_artifact_type,
        }
    ]
