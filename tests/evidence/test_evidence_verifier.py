from __future__ import annotations

from datetime import UTC, datetime

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
    EvidenceVerificationBlocker,
    EvidenceVerificationBlockerCode,
    EvidenceVerificationInput,
    EvidenceVerificationResult,
    EvidenceVerifier,
    FallbackDecisionRecordedRef,
    VerifiedEvidence,
)
from boardroom_os.agents.profiles import ModelExecutionProfile
from boardroom_os.contracts.package import PackageCommand
from boardroom_os.execution.context_index import ProviderAttemptRef
from boardroom_os.execution.fallback import EvidencePurpose, FallbackKind, FallbackPolicy
from boardroom_os.execution.package import ExecutionPackage, FallbackPolicyRef
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
from tests.fixtures.execution.role_prompt_hooks import (
    baseline_role_prompt_hook,
    baseline_role_prompt_hook_fields,
    baseline_role_prompt_hook_registry,
)

_VALID_SHA256 = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
_VERIFIED_AT = datetime(2026, 5, 20, 9, 2, tzinfo=UTC)


def _acceptance_ref(value: str = "AC-BACKEND") -> AcceptanceRef:
    return AcceptanceRef(value=value)


def _source_surface_ref(value: str = "surface.backend") -> SourceSurfaceRef:
    return SourceSurfaceRef(value=value)


def _evidence_obligation_ref(value: str = "evidence.source.backend") -> EvidenceObligationRef:
    return EvidenceObligationRef(value=value)


def _provider_attempt_ref(value: str = "provider-attempt.backend") -> ProviderAttemptRef:
    return ProviderAttemptRef(value=value)


def _artifact_ref(value: str = "artifact.source.backend") -> EvidenceArtifactRef:
    return EvidenceArtifactRef(value=value)


def _criterion(acceptance_ref: str = "AC-BACKEND") -> AcceptanceCriterion:
    return AcceptanceCriterion(
        acceptance_ref=_acceptance_ref(acceptance_ref),
        statement="Backend source satisfies the active acceptance criterion.",
        evidence_required=(EvidenceRequirement(value="auditable artifact hash"),),
        blocking=True,
        source_surface_refs=(_source_surface_ref(),),
        verification_strategy=VerificationStrategy(value="verify artifact hash and lineage"),
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
        project_goal="Generate auditable backend evidence.",
        delivery_type="generated_project_package",
        non_goals=("Do not read legacy runtime.",),
        constraints=("Evidence must be verified before acceptance.",),
        risks=("Synthetic evidence must be blocked.",),
        success_summary="Evidence claims become auditable verified evidence.",
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
    evidence_obligation_ref: EvidenceObligationRef | None = None,
    acceptance_refs: tuple[AcceptanceRef, ...] | None = None,
    source_surface_refs: tuple[SourceSurfaceRef, ...] | None = None,
    required_artifact_type: RequiredArtifactType | None = None,
) -> EvidenceObligation:
    return EvidenceObligation(
        evidence_obligation_id=evidence_obligation_ref or _evidence_obligation_ref(),
        acceptance_refs=acceptance_refs or (_acceptance_ref(),),
        source_surface_refs=source_surface_refs or (_source_surface_ref(),),
        required_artifact_type=required_artifact_type
        or RequiredArtifactType(value="source_patch"),
        required_verifier=RequiredVerifier(value="verifier.source.patch"),
        blocking=True,
    )


def _provider_attempt(
    *,
    provider_attempt_ref: str = "provider-attempt.backend",
    status: ProviderAttemptStatus = ProviderAttemptStatus.SUCCEEDED,
    outcome: ProviderAttemptOutcome = ProviderAttemptOutcome.PRIMARY_PROVIDER_OUTPUT,
    fallback_kind: FallbackKind | None = None,
) -> ProviderAttempt:
    fields: dict[str, object] = {
        "provider_attempt_id": _provider_attempt_ref(provider_attempt_ref),
        "provider": "anthropic",
        "model": "claude-opus-4-7",
        "reasoning_effort": "medium",
        "input_package_ref": "exec.backend.1",
        "seat_ref": "seat.worker.backend",
        **baseline_role_prompt_hook_fields(),
        "status": status,
        "outcome": outcome,
        "started_at": datetime(2026, 5, 20, 9, 0, tzinfo=UTC),
        "finished_at": datetime(2026, 5, 20, 9, 1, tzinfo=UTC),
    }
    if outcome is ProviderAttemptOutcome.FALLBACK_ARTIFACT:
        fields["fallback_kind"] = (
            fallback_kind or FallbackKind.CONTRACT_ALLOWED_DETERMINISTIC_TRANSFORM
        )
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


def _execution_package(
    *,
    execution_package_id: str = "exec.backend.1",
    hook_ref: str = "role-prompt-hook.baseline.worker.v1",
) -> ExecutionPackage:
    return ExecutionPackage(
        execution_package_id=execution_package_id,
        ticket_ref="ticket.backend.1",
        graph_version=7,
        seat_ref="seat.worker.backend",
        model_execution_profile=ModelExecutionProfile(
            model_execution_profile_id="model.worker.backend",
            provider="anthropic",
            model="claude-opus-4-7",
            reasoning_effort="medium",
            context_window=200000,
            temperature=0.2,
            tool_permissions=("filesystem.write",),
            fallback_policy_ref=ContractId(value="fallback.worker.record_failure"),
        ),
        role_prompt_hook=baseline_role_prompt_hook(hook_ref),
        objective="Verify backend evidence.",
        context_refs=("context.backend",),
        constraints=("Evidence must be bound to the execution package.",),
        acceptance_refs=(_acceptance_ref(),),
        source_surface_refs=(_source_surface_ref(),),
        allowed_write_set=("src/backend/app.py",),
        required_outputs=("work-product.backend",),
        commands=(
            PackageCommand(
                command_id=ContractId(value="test.backend"),
                label="Run backend tests",
                command=("python", "-m", "pytest"),
                cwd=".",
            ),
        ),
        evidence_obligations=(_evidence_obligation(),),
        fallback_policy_ref="fallback.worker.record_failure",
        audit_requirements=("provider_attempt_hook_snapshot_binding",),
    )


def _claim(
    *,
    evidence_claim_id: str = "evidence-claim.work_product.work-product.backend.evidence.source.backend",
    evidence_obligation_ref: EvidenceObligationRef | None = None,
    producer_attempt_ref: ProviderAttemptRef | None = None,
    source_kind: EvidenceClaimSourceKind = EvidenceClaimSourceKind.WORK_PRODUCT,
    source_ref: str = "work-product.backend",
    expected_purpose: EvidencePurpose = EvidencePurpose.IMPLEMENTATION,
    required_artifact_type: RequiredArtifactType | None = None,
    acceptance_refs: tuple[AcceptanceRef, ...] | None = None,
    source_surface_refs: tuple[SourceSurfaceRef, ...] | None = None,
    artifact_refs: tuple[EvidenceArtifactRef, ...] | None = None,
    verification_run_refs: tuple[VerificationRunRef, ...] | None = None,
    fallback_marker: FallbackLineageMarker | None = None,
) -> EvidenceClaim:
    fields: dict[str, object] = {
        "evidence_claim_id": EvidenceClaimRef(value=evidence_claim_id),
        "evidence_obligation_ref": evidence_obligation_ref or _evidence_obligation_ref(),
        "producer_attempt_ref": producer_attempt_ref or _provider_attempt_ref(),
        "source_kind": source_kind,
        "source_ref": source_ref,
        "expected_purpose": expected_purpose,
        "required_artifact_type": required_artifact_type
        or RequiredArtifactType(value="source_patch"),
        "acceptance_refs": acceptance_refs or (_acceptance_ref(),),
        "source_surface_refs": source_surface_refs or (_source_surface_ref(),),
        "artifact_refs": artifact_refs or (_artifact_ref(),),
        "summary": "Backend evidence claim.",
    }
    if verification_run_refs is not None:
        fields["verification_run_refs"] = verification_run_refs
    if fallback_marker is not None:
        fields["fallback_marker"] = fallback_marker
    return EvidenceClaim(**fields)


def _manifest_entry(
    *,
    artifact_ref: EvidenceArtifactRef | None = None,
    producer_attempt_ref: ProviderAttemptRef | None = None,
    source_ref: str = "work-product.backend",
    artifact_kind: str = "source_patch",
) -> ArtifactManifestEntry:
    return ArtifactManifestEntry(
        artifact_ref=artifact_ref or _artifact_ref(),
        sha256=ArtifactSha256(value=_VALID_SHA256),
        producer_attempt_ref=producer_attempt_ref or _provider_attempt_ref(),
        source_ref=source_ref,
        artifact_kind=artifact_kind,
    )


def _artifact_manifest(
    entries: tuple[ArtifactManifestEntry, ...] | None = None,
) -> ArtifactManifest:
    return ArtifactManifest(entries=entries or (_manifest_entry(),))


def _purpose_policy(
    *,
    required_artifact_type: RequiredArtifactType | None = None,
    allowed_purposes: tuple[EvidencePurpose, ...] | None = None,
) -> EvidencePurposePolicy:
    return EvidencePurposePolicy(
        rules=(
            EvidencePurposeRule(
                required_artifact_type=required_artifact_type
                or RequiredArtifactType(value="source_patch"),
                allowed_purposes=allowed_purposes or (EvidencePurpose.IMPLEMENTATION,),
            ),
        )
    )


def _verification_run(
    *,
    verification_run_ref: VerificationRunRef | None = None,
    status: VerificationRunStatus = VerificationRunStatus.PASSED,
) -> VerificationRun:
    run_ref = verification_run_ref or VerificationRunRef(value="verification-run.backend")
    return VerificationRun(
        verification_run_id=run_ref,
        execution_package_ref="exec.backend.1",
        ticket_ref="ticket.backend.1",
        command_id="command.pytest.backend",
        command=("python", "-m", "pytest"),
        cwd="/workspace/generated/backend",
        exit_code=0 if status is VerificationRunStatus.PASSED else 1,
        status=status,
        stdout_ref=CommandOutputRef(value=f"command-output.{run_ref.value}.stdout"),
        stderr_ref=CommandOutputRef(value=f"command-output.{run_ref.value}.stderr"),
        duration_ms=1000,
        started_at=datetime(2026, 5, 20, 9, 0, tzinfo=UTC),
        finished_at=datetime(2026, 5, 20, 9, 1, tzinfo=UTC),
        runner_ref="runner.local",
        environment_profile_ref="env.python",
        workspace_snapshot_ref="workspace.snapshot.backend",
    )


def _verification_run_claim(run: VerificationRun) -> EvidenceClaim:
    return _claim(
        evidence_claim_id=(
            "evidence-claim.verification_run."
            f"{run.verification_run_id.value}.evidence.command.backend"
        ),
        source_kind=EvidenceClaimSourceKind.VERIFICATION_RUN,
        source_ref=run.verification_run_id.value,
        required_artifact_type=RequiredArtifactType(value="command_run"),
        artifact_refs=(
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


def _fallback_marker(
    *,
    fallback_policy_ref: str = "fallback.hash-manifest",
    fallback_kind: FallbackKind = FallbackKind.CONTRACT_ALLOWED_DETERMINISTIC_TRANSFORM,
    producer_attempt_ref: str = "provider-attempt.backend",
) -> FallbackLineageMarker:
    return FallbackLineageMarker(
        fallback_policy_ref=FallbackPolicyRef(value=fallback_policy_ref),
        fallback_kind=fallback_kind,
        producer_attempt_ref=_provider_attempt_ref(producer_attempt_ref),
    )


def _fallback_policy(
    *,
    required_artifact_type: RequiredArtifactType | None = None,
    acceptance_refs: tuple[AcceptanceRef, ...] | None = None,
) -> FallbackPolicy:
    return FallbackPolicy(
        fallback_policy_ref=FallbackPolicyRef(value="fallback.hash-manifest"),
        kind=FallbackKind.CONTRACT_ALLOWED_DETERMINISTIC_TRANSFORM,
        allowed_artifact_types=(
            required_artifact_type or RequiredArtifactType(value="hash_manifest"),
        ),
        allowed_acceptance_refs=acceptance_refs or (_acceptance_ref(),),
    )


def _fallback_registry(
    *,
    required_artifact_type: RequiredArtifactType | None = None,
    acceptance_refs: tuple[AcceptanceRef, ...] | None = None,
) -> FallbackPolicyRegistry:
    return FallbackPolicyRegistry(
        policies=(
            _fallback_policy(
                required_artifact_type=required_artifact_type,
                acceptance_refs=acceptance_refs,
            ),
        )
    )


def _fallback_claim(
    *,
    expected_purpose: EvidencePurpose = EvidencePurpose.DETERMINISTIC,
    required_artifact_type: RequiredArtifactType | None = None,
) -> EvidenceClaim:
    artifact_type = required_artifact_type or RequiredArtifactType(value="hash_manifest")
    return _claim(
        evidence_claim_id="evidence-claim.work_product.work-product.backend.evidence.hash-manifest",
        expected_purpose=expected_purpose,
        required_artifact_type=artifact_type,
        artifact_refs=(EvidenceArtifactRef(value="artifact.hash-manifest"),),
        fallback_marker=_fallback_marker(),
    )


def _input(
    *,
    claim: EvidenceClaim | None = None,
    evidence_obligation: EvidenceObligation | None = None,
    active_acceptance_contract: AcceptanceContract | None = None,
    artifact_manifest: ArtifactManifest | None = None,
    purpose_policy: EvidencePurposePolicy | None = None,
    provider_attempts: tuple[ProviderAttempt, ...] | None = None,
    execution_packages: tuple[ExecutionPackage, ...] | None = None,
    verification_runs: tuple[VerificationRun, ...] | None = None,
    fallback_policy_registry: FallbackPolicyRegistry | None = None,
    fallback_decision_recorded_ref: FallbackDecisionRecordedRef | None = None,
) -> EvidenceVerificationInput:
    resolved_claim = claim or _claim()
    return EvidenceVerificationInput(
        claim=resolved_claim,
        evidence_obligation=evidence_obligation or _evidence_obligation(),
        active_acceptance_contract=active_acceptance_contract or _acceptance_contract(),
        artifact_manifest=artifact_manifest or _artifact_manifest(),
        purpose_policy=purpose_policy or _purpose_policy(),
        provider_attempts=provider_attempts
        if provider_attempts is not None
        else (_provider_attempt(),),
        execution_packages=execution_packages
        if execution_packages is not None
        else (_execution_package(),),
        verification_runs=verification_runs if verification_runs is not None else (),
        fallback_policy_registry=fallback_policy_registry,
        fallback_decision_record=(
            evaluate_fallback_claim(
                claim=resolved_claim,
                registry=fallback_policy_registry,
                evaluated_at=_VERIFIED_AT,
            )
            if fallback_policy_registry is not None
            else None
        ),
        fallback_decision_recorded_ref=fallback_decision_recorded_ref,
        role_prompt_hook_registry=baseline_role_prompt_hook_registry(),
        verified_at=_VERIFIED_AT,
    )


def _fallback_input(
    *,
    claim: EvidenceClaim | None = None,
) -> EvidenceVerificationInput:
    resolved_claim = claim or _fallback_claim()
    registry = _fallback_registry(
        required_artifact_type=resolved_claim.required_artifact_type,
        acceptance_refs=resolved_claim.acceptance_refs,
    )
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
            ),
        ),
        artifact_manifest=_artifact_manifest(
            entries=(
                _manifest_entry(
                    artifact_ref=resolved_claim.artifact_refs[0],
                    source_ref=resolved_claim.source_ref,
                    artifact_kind=resolved_claim.required_artifact_type.value,
                ),
            )
        ),
        purpose_policy=_purpose_policy(
            required_artifact_type=resolved_claim.required_artifact_type,
            allowed_purposes=(resolved_claim.expected_purpose,),
        ),
        provider_attempts=(
            _provider_attempt(outcome=ProviderAttemptOutcome.FALLBACK_ARTIFACT),
        ),
        fallback_policy_registry=registry,
        fallback_decision_recorded_ref=FallbackDecisionRecordedRef(
            value="audit.fallback-decision.backend"
        ),
    )


def _verified_evidence() -> VerifiedEvidence:
    result = EvidenceVerifier().verify(_input())
    assert result.verified_evidence is not None
    return result.verified_evidence


def test_primary_work_product_claim_becomes_verified_evidence() -> None:
    claim = _claim()

    result = EvidenceVerifier().verify(_input(claim=claim))

    assert result.success is True
    assert result.blockers == ()
    assert result.verified_evidence is not None
    assert result.verified_evidence.evidence_claim_ref == claim.evidence_claim_id
    assert result.verified_evidence.evidence_obligation_ref == claim.evidence_obligation_ref
    assert result.verified_evidence.producer_attempt_ref == claim.producer_attempt_ref
    assert result.verified_evidence.source_kind is EvidenceClaimSourceKind.WORK_PRODUCT
    assert result.verified_evidence.verified_artifacts[0].artifact_ref == _artifact_ref()
    assert result.verified_evidence.fallback_decision_record_ref is None
    assert result.verified_evidence.fallback_decision_recorded_ref is None


def test_evidence_verification_input_requires_role_prompt_hook_registry() -> None:
    with pytest.raises(ValidationError, match="role_prompt_hook_registry"):
        EvidenceVerificationInput(
            claim=_claim(),
            evidence_obligation=_evidence_obligation(),
            active_acceptance_contract=_acceptance_contract(),
            artifact_manifest=_artifact_manifest(),
            purpose_policy=_purpose_policy(),
            provider_attempts=(_provider_attempt(),),
            execution_packages=(_execution_package(),),
            verified_at=_VERIFIED_AT,
        )


def test_evidence_verification_input_requires_execution_packages() -> None:
    with pytest.raises(ValidationError, match="execution_packages"):
        EvidenceVerificationInput(
            claim=_claim(),
            evidence_obligation=_evidence_obligation(),
            active_acceptance_contract=_acceptance_contract(),
            artifact_manifest=_artifact_manifest(),
            purpose_policy=_purpose_policy(),
            provider_attempts=(_provider_attempt(),),
            role_prompt_hook_registry=baseline_role_prompt_hook_registry(),
            verified_at=_VERIFIED_AT,
        )


@pytest.mark.parametrize(
    ("field_name", "field_value"),
    (
        ("role_prompt_hook_ref", "role-prompt-hook.fake.worker.v9"),
        ("role_prompt_hook_version", "v9"),
        ("role_prompt_hook_sha256", {"value": "0" * 64}),
    ),
)
def test_verifier_blocks_provider_attempt_with_unregistered_hook_lineage(
    field_name: str,
    field_value: object,
) -> None:
    attempt = _provider_attempt().model_copy(update={field_name: field_value})

    result = EvidenceVerifier().verify(
        _input(provider_attempts=(attempt,))
    )

    assert result.verified_evidence is None
    assert any(
        blocker.code
        is EvidenceVerificationBlockerCode.PROVIDER_ATTEMPT_ROLE_PROMPT_HOOK_INVALID
        for blocker in result.blockers
    )


def test_verifier_blocks_provider_attempt_hook_mismatch_with_execution_package_snapshot() -> None:
    attempt = _provider_attempt().model_copy(
        update=baseline_role_prompt_hook_fields("role-prompt-hook.baseline.tester.v1")
    )

    result = EvidenceVerifier().verify(_input(provider_attempts=(attempt,)))

    assert result.verified_evidence is None
    assert (
        EvidenceVerificationBlocker(
            code=EvidenceVerificationBlockerCode.PROVIDER_ATTEMPT_ROLE_PROMPT_HOOK_INVALID,
            message=(
                "provider attempt role prompt hook does not match execution package snapshot"
            ),
            related_ref=attempt.provider_attempt_id.value,
        )
        in result.blockers
    )


def test_verifier_blocks_provider_attempt_without_execution_package_binding() -> None:
    result = EvidenceVerifier().verify(_input(execution_packages=()))

    assert result.verified_evidence is None
    assert (
        EvidenceVerificationBlocker(
            code=EvidenceVerificationBlockerCode.PROVIDER_ATTEMPT_ROLE_PROMPT_HOOK_INVALID,
            message="provider attempt input_package_ref is missing from execution_packages",
            related_ref="exec.backend.1",
        )
        in result.blockers
    )


def test_verifier_blocks_execution_package_hook_snapshot_not_matching_registry() -> None:
    package = _execution_package()
    tampered_hook = package.role_prompt_hook.model_copy(
        update={
            "required_responsibilities": (
                "Tampered responsibility outside governed registry.",
            ),
        }
    )

    result = EvidenceVerifier().verify(
        _input(
            execution_packages=(
                package.model_copy(update={"role_prompt_hook": tampered_hook}),
            ),
        )
    )

    assert result.verified_evidence is None
    assert (
        EvidenceVerificationBlocker(
            code=EvidenceVerificationBlockerCode.PROVIDER_ATTEMPT_ROLE_PROMPT_HOOK_INVALID,
            message="execution package role prompt hook snapshot is not registered",
            related_ref="exec.backend.1",
        )
        in result.blockers
    )


def test_verifier_accepts_registered_verification_hook_when_bound_to_execution_package_snapshot() -> None:
    attempt = _provider_attempt().model_copy(
        update=baseline_role_prompt_hook_fields("role-prompt-hook.baseline.tester.v1")
    )

    result = EvidenceVerifier().verify(
        _input(
            provider_attempts=(attempt,),
            execution_packages=(
                _execution_package(hook_ref="role-prompt-hook.baseline.tester.v1"),
            ),
        )
    )

    assert result.success is True
    assert result.blockers == ()
    assert result.verified_evidence is not None


def test_command_verification_run_claim_becomes_verified_evidence() -> None:
    run = _verification_run()
    claim = _verification_run_claim(run)

    result = EvidenceVerifier().verify(
        _input(
            claim=claim,
            evidence_obligation=_evidence_obligation(
                required_artifact_type=RequiredArtifactType(value="command_run")
            ),
            artifact_manifest=_verification_run_manifest(run),
            purpose_policy=_purpose_policy(
                required_artifact_type=RequiredArtifactType(value="command_run")
            ),
            verification_runs=(run,),
        )
    )

    assert result.success is True
    assert result.blockers == ()
    assert result.verified_evidence is not None
    assert result.verified_evidence.source_kind is EvidenceClaimSourceKind.VERIFICATION_RUN
    assert result.verified_evidence.verification_run_refs == (run.verification_run_id,)
    assert tuple(
        artifact.artifact_ref.value for artifact in result.verified_evidence.verified_artifacts
    ) == (run.stdout_ref.value, run.stderr_ref.value)
    assert tuple(
        artifact.artifact_kind for artifact in result.verified_evidence.verified_artifacts
    ) == ("command_stdout", "command_stderr")


def test_verifier_rejects_verification_run_artifact_refs_out_of_order() -> None:
    run = _verification_run()
    claim = _verification_run_claim(run).model_copy(
        update={
            "artifact_refs": (
                EvidenceArtifactRef(value=run.stderr_ref.value),
                EvidenceArtifactRef(value=run.stdout_ref.value),
            )
        }
    )

    result = EvidenceVerifier().verify(
        _input(
            claim=claim,
            evidence_obligation=_evidence_obligation(
                required_artifact_type=RequiredArtifactType(value="command_run")
            ),
            artifact_manifest=_verification_run_manifest(run),
            purpose_policy=_purpose_policy(
                required_artifact_type=RequiredArtifactType(value="command_run")
            ),
            verification_runs=(run,),
        )
    )

    assert result.success is False
    assert result.verified_evidence is None
    assert tuple(blocker.code for blocker in result.blockers) == (
        EvidenceVerificationBlockerCode.VERIFICATION_RUN_ARTIFACT_REFS_MISMATCH,
    )


def test_allowed_deterministic_fallback_claim_becomes_verified_evidence() -> None:
    claim = _fallback_claim()

    result = EvidenceVerifier().verify(_fallback_input(claim=claim))

    assert result.success is True
    assert result.blockers == ()
    assert result.verified_evidence is not None
    assert result.verified_evidence.evidence_claim_ref == claim.evidence_claim_id
    assert result.verified_evidence.expected_purpose is EvidencePurpose.DETERMINISTIC
    assert result.verified_evidence.fallback_decision_record_ref == FallbackDecisionRecordRef(
        value=(
            "fallback-decision."
            "evidence-claim.work_product.work-product.backend.evidence.hash-manifest."
            "fallback.hash-manifest"
        )
    )
    assert result.verified_evidence.fallback_decision_recorded_ref == (
        FallbackDecisionRecordedRef(value="audit.fallback-decision.backend")
    )


def test_blocked_fallback_decision_returns_auditable_blocker() -> None:
    claim = _fallback_claim(expected_purpose=EvidencePurpose.IMPLEMENTATION)

    result = EvidenceVerifier().verify(_fallback_input(claim=claim))

    assert result.success is False
    assert result.verified_evidence is None
    assert len(result.blockers) == 1
    blocker = result.blockers[0]
    assert blocker.code is EvidenceVerificationBlockerCode.FALLBACK_DECISION_NOT_ALLOWED
    assert blocker.message == "fallback decision does not allow verified evidence"
    assert blocker.related_ref == (
        "fallback-decision."
        "evidence-claim.work_product.work-product.backend.evidence.hash-manifest."
        "fallback.hash-manifest"
    )


def test_verified_evidence_uses_deterministic_default_id() -> None:
    claim = _claim(evidence_claim_id="evidence-claim.custom-deterministic")

    result = EvidenceVerifier().verify(_input(claim=claim))

    assert result.verified_evidence is not None
    assert result.verified_evidence.verified_evidence_id.value == (
        "verified-evidence.evidence-claim.custom-deterministic"
    )


def test_verified_evidence_serializes_as_audit_friendly_json() -> None:
    verified_evidence = _verified_evidence()

    assert verified_evidence.model_dump(mode="json") == {
        "version": 1,
        "verified_evidence_id": {
            "value": (
                "verified-evidence."
                "evidence-claim.work_product.work-product.backend.evidence.source.backend"
            )
        },
        "evidence_claim_ref": {
            "value": "evidence-claim.work_product.work-product.backend.evidence.source.backend"
        },
        "evidence_obligation_ref": {"value": "evidence.source.backend"},
        "producer_attempt_ref": {"value": "provider-attempt.backend"},
        "source_kind": "work_product",
        "source_ref": "work-product.backend",
        "expected_purpose": "implementation",
        "required_artifact_type": {"value": "source_patch"},
        "acceptance_refs": [{"value": "AC-BACKEND"}],
        "source_surface_refs": [{"value": "surface.backend"}],
        "verified_artifacts": [
            {
                "artifact_ref": {"value": "artifact.source.backend"},
                "sha256": {"value": _VALID_SHA256},
                "producer_attempt_ref": {"value": "provider-attempt.backend"},
                "source_ref": "work-product.backend",
                "artifact_kind": "source_patch",
            }
        ],
        "verification_run_refs": [],
        "service_run_refs": [],
        "live_blackbox_evidence_refs": [],
        "fallback_decision_record_ref": None,
        "fallback_decision_recorded_ref": None,
        "verified_at": "2026-05-20T09:02:00Z",
    }


def test_verifier_result_is_success_or_blockers_not_both() -> None:
    verified_evidence = _verified_evidence()
    blocker = EvidenceVerificationBlocker(
        code=EvidenceVerificationBlockerCode.MISSING_ARTIFACT,
        message="claim artifact_ref is missing from artifact manifest",
        related_ref="artifact.missing",
    )

    success = EvidenceVerificationResult(verified_evidence=verified_evidence)
    blocked = EvidenceVerificationResult(blockers=(blocker,))

    assert success.success is True
    assert success.blockers == ()
    assert blocked.success is False
    assert blocked.verified_evidence is None
    assert blocked.blockers == (blocker,)
    with pytest.raises(ValidationError, match="successful verification"):
        EvidenceVerificationResult(
            verified_evidence=verified_evidence,
            blockers=(blocker,),
        )
    with pytest.raises(ValidationError, match="failed verification"):
        EvidenceVerificationResult()
