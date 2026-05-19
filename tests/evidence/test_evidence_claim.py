from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from boardroom_os.agents.profiles import ModelExecutionProfile
from boardroom_os.contracts.evidence_obligation import (
    EvidenceObligation,
    RequiredArtifactType,
    RequiredVerifier,
)
from boardroom_os.contracts.package import PackageCommand
from boardroom_os.contracts.types import (
    AcceptanceRef,
    ContractId,
    EvidenceObligationRef,
    SourceSurfaceRef,
)
from boardroom_os.evidence import (
    EvidenceArtifactRef,
    EvidenceClaim,
    EvidenceClaimBuildError,
    EvidenceClaimRef,
    EvidenceClaimSourceKind,
    FallbackLineageMarker,
    build_evidence_claim_from_verification_run,
    build_evidence_claim_from_work_product,
)
from boardroom_os.execution.context_index import ProviderAttemptRef
from boardroom_os.execution.fallback import EvidencePurpose, FallbackKind
from boardroom_os.execution.package import ExecutionPackage, ExecutionPackageRef, FallbackPolicyRef
from boardroom_os.execution.verification_run import (
    CommandOutputRef,
    EnvironmentProfileRef,
    RunnerRef,
    VerificationRun,
    VerificationRunRef,
    VerificationRunStatus,
    WorkspaceSnapshotRef,
)
from boardroom_os.execution.work_product import (
    WorkProduct,
    WorkProductArtifactRef,
    WorkProductClaimDraft,
    WorkProductClaimDraftRef,
    WorkProductRef,
    build_work_product_from_provider_attempt,
)
from boardroom_os.graph.ticket import TicketId
from boardroom_os.providers.attempt import (
    ProviderArtifactRef,
    ProviderAttempt,
    ProviderAttemptOutcome,
    ProviderAttemptStatus,
)


def _claim_fields(**overrides: object) -> dict[str, object]:
    fields: dict[str, object] = {
        "evidence_claim_id": EvidenceClaimRef(
            value="evidence-claim.work_product.work-product.backend.evidence.backend"
        ),
        "evidence_obligation_ref": EvidenceObligationRef(value="evidence.backend"),
        "producer_attempt_ref": ProviderAttemptRef(value="provider-attempt.backend"),
        "source_kind": EvidenceClaimSourceKind.WORK_PRODUCT,
        "source_ref": "work-product.backend",
        "expected_purpose": EvidencePurpose.IMPLEMENTATION,
        "required_artifact_type": RequiredArtifactType(value="source"),
        "acceptance_refs": (AcceptanceRef(value="AC-BACKEND"),),
        "source_surface_refs": (SourceSurfaceRef(value="surface.backend"),),
        "artifact_refs": (EvidenceArtifactRef(value="artifact.backend.source"),),
        "verification_run_refs": (),
        "fallback_marker": None,
        "summary": "Backend implementation evidence claim.",
    }
    fields.update(overrides)
    return fields


def _evidence_obligation(
    *,
    acceptance_refs: tuple[AcceptanceRef, ...] = (AcceptanceRef(value="AC-BACKEND"),),
    source_surface_refs: tuple[SourceSurfaceRef, ...] = (
        SourceSurfaceRef(value="surface.backend"),
    ),
    artifact_type: str = "source",
    evidence_obligation_id: EvidenceObligationRef = EvidenceObligationRef(
        value="evidence.backend"
    ),
) -> EvidenceObligation:
    return EvidenceObligation(
        evidence_obligation_id=evidence_obligation_id,
        acceptance_refs=acceptance_refs,
        source_surface_refs=source_surface_refs,
        required_artifact_type=RequiredArtifactType(value=artifact_type),
        required_verifier=RequiredVerifier(value="source_inventory"),
        blocking=True,
    )


def _execution_package() -> ExecutionPackage:
    evidence_obligation = _evidence_obligation(
        acceptance_refs=(AcceptanceRef(value="AC-BACKEND-API"),),
        source_surface_refs=(SourceSurfaceRef(value="surface.backend-api"),),
        evidence_obligation_id=EvidenceObligationRef(value="evidence.backend-api"),
    )
    return ExecutionPackage(
        execution_package_id="execution-package.backend-api",
        ticket_ref="ticket.backend-api",
        graph_version=1,
        seat_ref="seat.worker.backend",
        model_execution_profile=ModelExecutionProfile(
            model_execution_profile_id="model-profile.worker",
            provider="anthropic",
            model="claude-opus-4-7",
            reasoning_effort="medium",
            context_window=200000,
            temperature=0.2,
            tool_permissions=("provider.invoke",),
            fallback_policy_ref="fallback-policy.default",
        ),
        objective="Implement the backend API.",
        context_refs=("context.project-charter",),
        constraints=("Stay inside allowed write set.",),
        acceptance_refs=("AC-BACKEND-API",),
        source_surface_refs=("surface.backend-api",),
        allowed_read_refs=("read.contracts",),
        allowed_write_set=("backend/app.py",),
        required_outputs=("backend source files",),
        commands=(
            PackageCommand(
                command_id={"value": "command.test"},
                label="Run tests",
                command=("pytest",),
                cwd=".",
            ),
        ),
        evidence_obligations=(evidence_obligation,),
        fallback_policy_ref="fallback-policy.default",
        audit_requirements=("record work product lineage",),
    )


def _provider_attempt(**overrides: object) -> ProviderAttempt:
    fields: dict[str, object] = {
        "provider_attempt_id": ProviderAttemptRef(value="provider-attempt.backend-api"),
        "provider": "anthropic",
        "model": "claude-opus-4-7",
        "reasoning_effort": "medium",
        "input_package_ref": ExecutionPackageRef(value="execution-package.backend-api"),
        "seat_ref": "seat.worker.backend",
        "status": ProviderAttemptStatus.SUCCEEDED,
        "outcome": ProviderAttemptOutcome.PRIMARY_PROVIDER_OUTPUT,
        "started_at": datetime(2026, 5, 18, 9, 0, tzinfo=UTC),
        "finished_at": datetime(2026, 5, 18, 9, 1, tzinfo=UTC),
        "raw_output_ref": ProviderArtifactRef(value="provider-artifact.raw.backend-api"),
        "parsed_output_ref": ProviderArtifactRef(
            value="provider-artifact.parsed.backend-api"
        ),
    }
    fields.update(overrides)
    return ProviderAttempt(**fields)



def _work_product(**overrides: object) -> WorkProduct:
    fields: dict[str, object] = {
        "work_product_id": WorkProductRef(value="work-product.backend"),
        "execution_package_ref": ExecutionPackageRef(value="execution-package.backend"),
        "ticket_ref": TicketId(value="ticket.backend"),
        "producer_attempt_ref": ProviderAttemptRef(value="provider-attempt.backend"),
        "artifact_refs": (
            WorkProductArtifactRef(value="artifact.backend.raw"),
            WorkProductArtifactRef(value="artifact.backend.parsed"),
        ),
        "claim_refs": (WorkProductClaimDraftRef(value="claim-draft.backend"),),
        "summary": "Backend work product.",
    }
    fields.update(overrides)
    return WorkProduct(**fields)



def _claim_draft(**overrides: object) -> WorkProductClaimDraft:
    fields: dict[str, object] = {
        "claim_draft_ref": WorkProductClaimDraftRef(value="claim-draft.backend"),
        "producer_attempt_ref": ProviderAttemptRef(value="provider-attempt.backend"),
        "execution_package_ref": ExecutionPackageRef(value="execution-package.backend"),
        "ticket_ref": TicketId(value="ticket.backend"),
        "acceptance_refs": (AcceptanceRef(value="AC-BACKEND"),),
        "source_surface_refs": (SourceSurfaceRef(value="surface.backend"),),
        "artifact_refs": (
            WorkProductArtifactRef(value="artifact.backend.raw"),
            WorkProductArtifactRef(value="artifact.backend.parsed"),
        ),
        "summary": "Backend claim draft.",
    }
    fields.update(overrides)
    return WorkProductClaimDraft(**fields)



def _fallback_marker(**overrides: object) -> FallbackLineageMarker:
    fields: dict[str, object] = {
        "fallback_policy_ref": FallbackPolicyRef(value="fallback.policy.backend"),
        "fallback_kind": FallbackKind.TOOLING_PREFLIGHT,
        "producer_attempt_ref": ProviderAttemptRef(value="provider-attempt.backend"),
    }
    fields.update(overrides)
    return FallbackLineageMarker(**fields)



def _verification_run(**overrides: object) -> VerificationRun:
    fields: dict[str, object] = {
        "verification_run_id": VerificationRunRef(value="verification-run.backend-tests"),
        "execution_package_ref": ExecutionPackageRef(value="execution-package.backend"),
        "ticket_ref": TicketId(value="ticket.backend"),
        "command_id": ContractId(value="command.backend-tests"),
        "command": ("python", "-m", "pytest", "tests/backend"),
        "cwd": ".",
        "exit_code": 0,
        "status": VerificationRunStatus.PASSED,
        "stdout_ref": CommandOutputRef(value="command-output.backend-tests.stdout"),
        "stderr_ref": CommandOutputRef(value="command-output.backend-tests.stderr"),
        "duration_ms": 1000,
        "started_at": datetime(2026, 5, 19, 9, 0, tzinfo=UTC),
        "finished_at": datetime(2026, 5, 19, 9, 0, 1, tzinfo=UTC),
        "runner_ref": RunnerRef(value="runner.local"),
        "environment_profile_ref": EnvironmentProfileRef(value="environment.local"),
        "workspace_snapshot_ref": WorkspaceSnapshotRef(value="workspace.snapshot"),
    }
    fields.update(overrides)
    return VerificationRun(**fields)


def test_evidence_claim_accepts_minimal_work_product_claim() -> None:
    claim = EvidenceClaim(**_claim_fields())

    assert claim.evidence_claim_id == EvidenceClaimRef(
        value="evidence-claim.work_product.work-product.backend.evidence.backend"
    )
    assert claim.source_kind is EvidenceClaimSourceKind.WORK_PRODUCT
    assert claim.source_ref == "work-product.backend"
    assert claim.expected_purpose is EvidencePurpose.IMPLEMENTATION
    assert claim.verification_run_refs == ()
    assert claim.fallback_marker is None


@pytest.mark.parametrize(
    "missing_field",
    [
        "evidence_claim_id",
        "producer_attempt_ref",
        "evidence_obligation_ref",
        "source_kind",
        "source_ref",
        "expected_purpose",
        "required_artifact_type",
        "acceptance_refs",
        "source_surface_refs",
        "artifact_refs",
    ],
)
def test_evidence_claim_requires_scalar_fields(missing_field: str) -> None:
    fields = _claim_fields()
    del fields[missing_field]

    with pytest.raises(ValidationError):
        EvidenceClaim(**fields)


@pytest.mark.parametrize(
    "field_name",
    [
        "acceptance_refs",
        "source_surface_refs",
        "artifact_refs",
    ],
)
def test_evidence_claim_requires_non_empty_required_tuples(field_name: str) -> None:
    with pytest.raises(ValidationError, match=field_name):
        EvidenceClaim(**_claim_fields(**{field_name: ()}))


@pytest.mark.parametrize(
    ("field_name", "malformed_value"),
    [
        ("acceptance_refs", "AC-BACKEND"),
        ("source_surface_refs", "surface.backend"),
        ("artifact_refs", "artifact.backend.source"),
        ("acceptance_refs", {"value": "AC-BACKEND"}),
    ],
)
def test_evidence_claim_rejects_malformed_required_tuple_inputs(
    field_name: str,
    malformed_value: object,
) -> None:
    with pytest.raises(ValidationError, match=field_name):
        EvidenceClaim(**_claim_fields(**{field_name: malformed_value}))


def test_verification_run_claim_rejects_malformed_verification_run_refs_input() -> None:
    with pytest.raises(ValidationError, match="verification_run_refs"):
        EvidenceClaim(
            **_claim_fields(
                source_kind=EvidenceClaimSourceKind.VERIFICATION_RUN,
                source_ref="verification-run.backend-tests",
                verification_run_refs="verification-run.backend-tests",
            )
        )


def test_evidence_claim_requires_non_empty_summary() -> None:
    with pytest.raises(ValidationError, match="summary"):
        EvidenceClaim(**_claim_fields(summary="   "))


def test_verification_run_claim_requires_verification_run_refs() -> None:
    with pytest.raises(ValidationError, match="verification_run_refs"):
        EvidenceClaim(
            **_claim_fields(
                source_kind=EvidenceClaimSourceKind.VERIFICATION_RUN,
                source_ref="verification-run.backend-tests",
                verification_run_refs=(),
            )
        )


def test_verification_run_claim_requires_source_ref_to_match_current_run() -> None:
    with pytest.raises(ValidationError, match="source_ref"):
        EvidenceClaim(
            **_claim_fields(
                source_kind=EvidenceClaimSourceKind.VERIFICATION_RUN,
                source_ref="verification-run.other",
                verification_run_refs=(
                    VerificationRunRef(value="verification-run.backend-tests"),
                ),
            )
        )


def test_work_product_claim_rejects_verification_run_refs() -> None:
    with pytest.raises(ValidationError, match="verification_run_refs"):
        EvidenceClaim(
            **_claim_fields(
                verification_run_refs=(
                    VerificationRunRef(value="verification-run.backend-tests"),
                ),
            )
        )


@pytest.mark.parametrize(
    "missing_field",
    [
        "fallback_policy_ref",
        "fallback_kind",
        "producer_attempt_ref",
    ],
)
def test_fallback_marker_requires_required_fields(missing_field: str) -> None:
    fields = {
        "fallback_policy_ref": FallbackPolicyRef(value="fallback.policy.backend"),
        "fallback_kind": FallbackKind.TOOLING_PREFLIGHT,
        "producer_attempt_ref": ProviderAttemptRef(value="provider-attempt.backend"),
    }
    del fields[missing_field]

    with pytest.raises(ValidationError):
        FallbackLineageMarker(**fields)


def test_evidence_claim_rejects_fallback_marker_producer_mismatch() -> None:
    with pytest.raises(ValidationError, match="producer_attempt_ref"):
        EvidenceClaim(
            **_claim_fields(
                fallback_marker=_fallback_marker(
                    producer_attempt_ref=ProviderAttemptRef(value="provider-attempt.other")
                )
            )
        )




def test_work_product_builder_requires_claim_draft_ref_to_belong_to_work_product() -> None:
    with pytest.raises(EvidenceClaimBuildError, match="claim_draft_ref"):
        build_evidence_claim_from_work_product(
            work_product=_work_product(),
            claim_draft=_claim_draft(
                claim_draft_ref=WorkProductClaimDraftRef(value="claim-draft.other")
            ),
            evidence_obligation=_evidence_obligation(),
            expected_purpose=EvidencePurpose.IMPLEMENTATION,
            summary="Build claim.",
        )



def test_work_product_builder_rejects_claim_draft_attempt_mismatch() -> None:
    with pytest.raises(EvidenceClaimBuildError, match="producer_attempt_ref"):
        build_evidence_claim_from_work_product(
            work_product=_work_product(),
            claim_draft=_claim_draft(
                producer_attempt_ref=ProviderAttemptRef(value="provider-attempt.other")
            ),
            evidence_obligation=_evidence_obligation(),
            expected_purpose=EvidencePurpose.IMPLEMENTATION,
            summary="Build claim.",
        )



def test_work_product_builder_rejects_claim_draft_execution_package_mismatch() -> None:
    with pytest.raises(EvidenceClaimBuildError, match="execution_package_ref"):
        build_evidence_claim_from_work_product(
            work_product=_work_product(),
            claim_draft=_claim_draft(
                execution_package_ref=ExecutionPackageRef(value="execution-package.other")
            ),
            evidence_obligation=_evidence_obligation(),
            expected_purpose=EvidencePurpose.IMPLEMENTATION,
            summary="Build claim.",
        )



def test_work_product_builder_rejects_claim_draft_ticket_mismatch() -> None:
    with pytest.raises(EvidenceClaimBuildError, match="ticket_ref"):
        build_evidence_claim_from_work_product(
            work_product=_work_product(),
            claim_draft=_claim_draft(ticket_ref=TicketId(value="ticket.other")),
            evidence_obligation=_evidence_obligation(),
            expected_purpose=EvidencePurpose.IMPLEMENTATION,
            summary="Build claim.",
        )



def test_work_product_builder_rejects_claim_draft_artifact_mismatch() -> None:
    with pytest.raises(EvidenceClaimBuildError, match="artifact_refs"):
        build_evidence_claim_from_work_product(
            work_product=_work_product(),
            claim_draft=_claim_draft(
                artifact_refs=(WorkProductArtifactRef(value="artifact.other"),)
            ),
            evidence_obligation=_evidence_obligation(),
            expected_purpose=EvidencePurpose.IMPLEMENTATION,
            summary="Build claim.",
        )



def test_fallback_claim_requires_typed_fallback_marker() -> None:
    with pytest.raises(EvidenceClaimBuildError, match="fallback_policy_ref"):
        build_evidence_claim_from_work_product(
            work_product=_work_product(fallback_kind=FallbackKind.TOOLING_PREFLIGHT),
            claim_draft=_claim_draft(),
            evidence_obligation=_evidence_obligation(),
            expected_purpose=EvidencePurpose.DIAGNOSTIC,
            summary="Fallback diagnostic claim.",
        )



def test_work_product_builder_rejects_fallback_without_policy_ref() -> None:
    with pytest.raises(EvidenceClaimBuildError, match="fallback_policy_ref"):
        build_evidence_claim_from_work_product(
            work_product=_work_product(fallback_kind=FallbackKind.TOOLING_PREFLIGHT),
            claim_draft=_claim_draft(),
            evidence_obligation=_evidence_obligation(),
            expected_purpose=EvidencePurpose.DIAGNOSTIC,
            summary="Fallback diagnostic claim.",
        )



def test_work_product_builder_rejects_primary_with_policy_ref() -> None:
    with pytest.raises(EvidenceClaimBuildError, match="fallback_policy_ref"):
        build_evidence_claim_from_work_product(
            work_product=_work_product(),
            claim_draft=_claim_draft(),
            evidence_obligation=_evidence_obligation(),
            expected_purpose=EvidencePurpose.IMPLEMENTATION,
            summary="Primary implementation claim.",
            fallback_policy_ref=FallbackPolicyRef(value="fallback.policy.backend"),
        )



def test_work_product_builder_rejects_acceptance_refs_outside_obligation() -> None:
    with pytest.raises(EvidenceClaimBuildError, match="acceptance_refs"):
        build_evidence_claim_from_work_product(
            work_product=_work_product(),
            claim_draft=_claim_draft(acceptance_refs=(AcceptanceRef(value="AC-OTHER"),)),
            evidence_obligation=_evidence_obligation(),
            expected_purpose=EvidencePurpose.IMPLEMENTATION,
            summary="Build claim.",
        )



def test_work_product_builder_rejects_source_surface_refs_outside_obligation() -> None:
    with pytest.raises(EvidenceClaimBuildError, match="source_surface_refs"):
        build_evidence_claim_from_work_product(
            work_product=_work_product(),
            claim_draft=_claim_draft(
                source_surface_refs=(SourceSurfaceRef(value="surface.other"),)
            ),
            evidence_obligation=_evidence_obligation(),
            expected_purpose=EvidencePurpose.IMPLEMENTATION,
            summary="Build claim.",
        )



def test_work_product_builder_limits_claim_refs_to_evidence_obligation() -> None:
    claim = build_evidence_claim_from_work_product(
        work_product=_work_product(),
        claim_draft=_claim_draft(
            acceptance_refs=(
                AcceptanceRef(value="AC-BACKEND"),
                AcceptanceRef(value="AC-EXTRA"),
            ),
            source_surface_refs=(
                SourceSurfaceRef(value="surface.backend"),
                SourceSurfaceRef(value="surface.extra"),
            ),
        ),
        evidence_obligation=_evidence_obligation(),
        expected_purpose=EvidencePurpose.IMPLEMENTATION,
        summary="Build claim.",
    )

    assert claim.acceptance_refs == (AcceptanceRef(value="AC-BACKEND"),)
    assert claim.source_surface_refs == (SourceSurfaceRef(value="surface.backend"),)



def test_work_product_builder_rejects_non_evidence_purpose_input() -> None:
    with pytest.raises(EvidenceClaimBuildError, match="expected_purpose"):
        build_evidence_claim_from_work_product(
            work_product=_work_product(),
            claim_draft=_claim_draft(),
            evidence_obligation=_evidence_obligation(),
            expected_purpose="implementation",  # type: ignore[arg-type]
            summary="Build claim.",
        )



def test_verification_run_builder_rejects_missing_producer_attempt_ref() -> None:
    with pytest.raises(TypeError):
        build_evidence_claim_from_verification_run(
            verification_run=_verification_run(),
            evidence_obligation=_evidence_obligation(artifact_type="command_run"),
            acceptance_refs=(AcceptanceRef(value="AC-BACKEND"),),
            source_surface_refs=(SourceSurfaceRef(value="surface.backend"),),
            expected_purpose=EvidencePurpose.IMPLEMENTATION,
            summary="Backend tests claim.",
        )



def test_verification_run_builder_rejects_invalid_producer_attempt_ref() -> None:
    with pytest.raises(EvidenceClaimBuildError, match="producer_attempt_ref"):
        build_evidence_claim_from_verification_run(
            verification_run=_verification_run(),
            evidence_obligation=_evidence_obligation(artifact_type="command_run"),
            producer_attempt_ref=None,  # type: ignore[arg-type]
            acceptance_refs=(AcceptanceRef(value="AC-BACKEND"),),
            source_surface_refs=(SourceSurfaceRef(value="surface.backend"),),
            expected_purpose=EvidencePurpose.IMPLEMENTATION,
            summary="Backend tests claim.",
        )



def test_verification_run_builder_rejects_acceptance_refs_outside_obligation() -> None:
    with pytest.raises(EvidenceClaimBuildError, match="acceptance_refs"):
        build_evidence_claim_from_verification_run(
            verification_run=_verification_run(),
            evidence_obligation=_evidence_obligation(artifact_type="command_run"),
            producer_attempt_ref=ProviderAttemptRef(value="provider-attempt.backend"),
            acceptance_refs=(AcceptanceRef(value="AC-OTHER"),),
            source_surface_refs=(SourceSurfaceRef(value="surface.backend"),),
            expected_purpose=EvidencePurpose.IMPLEMENTATION,
            summary="Backend tests claim.",
        )



def test_verification_run_builder_rejects_source_surface_refs_outside_obligation() -> None:
    with pytest.raises(EvidenceClaimBuildError, match="source_surface_refs"):
        build_evidence_claim_from_verification_run(
            verification_run=_verification_run(),
            evidence_obligation=_evidence_obligation(artifact_type="command_run"),
            producer_attempt_ref=ProviderAttemptRef(value="provider-attempt.backend"),
            acceptance_refs=(AcceptanceRef(value="AC-BACKEND"),),
            source_surface_refs=(SourceSurfaceRef(value="surface.other"),),
            expected_purpose=EvidencePurpose.IMPLEMENTATION,
            summary="Backend tests claim.",
        )



def test_verification_run_builder_rejects_non_evidence_purpose_input() -> None:
    with pytest.raises(EvidenceClaimBuildError, match="expected_purpose"):
        build_evidence_claim_from_verification_run(
            verification_run=_verification_run(),
            evidence_obligation=_evidence_obligation(artifact_type="command_run"),
            producer_attempt_ref=ProviderAttemptRef(value="provider-attempt.backend"),
            acceptance_refs=(AcceptanceRef(value="AC-BACKEND"),),
            source_surface_refs=(SourceSurfaceRef(value="surface.backend"),),
            expected_purpose="implementation",  # type: ignore[arg-type]
            summary="Backend tests claim.",
        )



@pytest.mark.parametrize(
    ("field_name", "malformed_value"),
    [
        ("acceptance_refs", "AC-BACKEND"),
        ("source_surface_refs", "surface.backend"),
        ("acceptance_refs", {"value": "AC-BACKEND"}),
        ("source_surface_refs", {"value": "surface.backend"}),
    ],
)
def test_verification_run_builder_rejects_malformed_scalar_ref_inputs(
    field_name: str,
    malformed_value: object,
) -> None:
    kwargs = {
        "verification_run": _verification_run(),
        "evidence_obligation": _evidence_obligation(artifact_type="command_run"),
        "producer_attempt_ref": ProviderAttemptRef(value="provider-attempt.backend"),
        "acceptance_refs": (AcceptanceRef(value="AC-BACKEND"),),
        "source_surface_refs": (SourceSurfaceRef(value="surface.backend"),),
        "expected_purpose": EvidencePurpose.IMPLEMENTATION,
        "summary": "Backend tests claim.",
    }
    kwargs[field_name] = malformed_value

    with pytest.raises(EvidenceClaimBuildError, match=field_name):
        build_evidence_claim_from_verification_run(**kwargs)



def test_evidence_claim_build_error_is_value_error_subclass() -> None:
    with pytest.raises(ValueError) as error_info:
        raise EvidenceClaimBuildError("build failed")

    assert isinstance(error_info.value, EvidenceClaimBuildError)


@pytest.mark.parametrize(
    "field_name",
    [
        "allowed",
        "decision",
    ],
)
def test_fallback_lineage_marker_rejects_unknown_fields(field_name: str) -> None:
    with pytest.raises(ValidationError, match=field_name):
        FallbackLineageMarker(
            fallback_policy_ref=FallbackPolicyRef(value="fallback.policy.backend"),
            fallback_kind=FallbackKind.TOOLING_PREFLIGHT,
            producer_attempt_ref=ProviderAttemptRef(value="provider-attempt.backend"),
            **{field_name: True},
        )



def test_work_product_builds_implementation_evidence_claim() -> None:
    execution_package = _execution_package()
    submission = build_work_product_from_provider_attempt(
        execution_package=execution_package,
        provider_attempt=_provider_attempt(),
        summary="Backend source implementation claim.",
    )

    claim = build_evidence_claim_from_work_product(
        work_product=submission.work_product,
        claim_draft=submission.claim_drafts[0],
        evidence_obligation=execution_package.evidence_obligations[0],
        expected_purpose=EvidencePurpose.IMPLEMENTATION,
        summary="Backend source implementation claim.",
    )

    assert claim.evidence_claim_id == EvidenceClaimRef(
        value=(
            "evidence-claim.work_product."
            "work-product.provider-attempt.backend-api.evidence.backend-api"
        )
    )
    assert claim.evidence_obligation_ref == EvidenceObligationRef(
        value="evidence.backend-api"
    )
    assert claim.source_kind is EvidenceClaimSourceKind.WORK_PRODUCT
    assert claim.source_ref == "work-product.provider-attempt.backend-api"
    assert claim.producer_attempt_ref == ProviderAttemptRef(
        value="provider-attempt.backend-api"
    )
    assert claim.expected_purpose is EvidencePurpose.IMPLEMENTATION
    assert claim.required_artifact_type == RequiredArtifactType(value="source")
    assert tuple(ref.value for ref in claim.acceptance_refs) == ("AC-BACKEND-API",)
    assert tuple(ref.value for ref in claim.source_surface_refs) == (
        "surface.backend-api",
    )
    assert tuple(ref.value for ref in claim.artifact_refs) == (
        "provider-artifact.raw.backend-api",
        "provider-artifact.parsed.backend-api",
    )
    assert claim.verification_run_refs == ()
    assert claim.fallback_marker is None



def test_work_product_builder_uses_explicit_claim_id() -> None:
    claim = build_evidence_claim_from_work_product(
        work_product=_work_product(),
        claim_draft=_claim_draft(),
        evidence_obligation=_evidence_obligation(),
        expected_purpose=EvidencePurpose.IMPLEMENTATION,
        summary="Backend source implementation claim.",
        claim_id=EvidenceClaimRef(value="evidence-claim.custom"),
    )

    assert claim.evidence_claim_id == EvidenceClaimRef(value="evidence-claim.custom")



def test_fallback_work_product_claim_records_lineage_without_allowed_decision() -> None:
    claim = build_evidence_claim_from_work_product(
        work_product=_work_product(fallback_kind=FallbackKind.TOOLING_PREFLIGHT),
        claim_draft=_claim_draft(),
        evidence_obligation=_evidence_obligation(),
        expected_purpose=EvidencePurpose.DIAGNOSTIC,
        summary="Fallback diagnostic claim.",
        fallback_policy_ref=FallbackPolicyRef(value="fallback.policy.backend"),
    )

    assert claim.fallback_marker == FallbackLineageMarker(
        fallback_policy_ref=FallbackPolicyRef(value="fallback.policy.backend"),
        fallback_kind=FallbackKind.TOOLING_PREFLIGHT,
        producer_attempt_ref=ProviderAttemptRef(value="provider-attempt.backend"),
    )
    assert not hasattr(claim.fallback_marker, "allowed")
    assert not hasattr(claim.fallback_marker, "decision")



def test_work_product_builder_fixes_expected_purpose_from_builder_input() -> None:
    claim = build_evidence_claim_from_work_product(
        work_product=_work_product(),
        claim_draft=_claim_draft(),
        evidence_obligation=_evidence_obligation(),
        expected_purpose=EvidencePurpose.DIAGNOSTIC,
        summary="Diagnostic implementation claim.",
    )

    assert claim.expected_purpose is EvidencePurpose.DIAGNOSTIC
    assert claim.required_artifact_type == RequiredArtifactType(value="source")



def test_verification_run_builds_command_evidence_claim() -> None:
    claim = build_evidence_claim_from_verification_run(
        verification_run=_verification_run(),
        evidence_obligation=_evidence_obligation(artifact_type="command_run"),
        producer_attempt_ref=ProviderAttemptRef(value="provider-attempt.backend"),
        acceptance_refs=(AcceptanceRef(value="AC-BACKEND"),),
        source_surface_refs=(SourceSurfaceRef(value="surface.backend"),),
        expected_purpose=EvidencePurpose.IMPLEMENTATION,
        summary="Backend command run claim.",
    )

    assert claim.evidence_claim_id == EvidenceClaimRef(
        value=(
            "evidence-claim.verification_run."
            "verification-run.backend-tests.evidence.backend"
        )
    )
    assert claim.evidence_obligation_ref == EvidenceObligationRef(value="evidence.backend")
    assert claim.source_kind is EvidenceClaimSourceKind.VERIFICATION_RUN
    assert claim.source_ref == "verification-run.backend-tests"
    assert claim.verification_run_refs == (
        VerificationRunRef(value="verification-run.backend-tests"),
    )
    assert tuple(ref.value for ref in claim.artifact_refs) == (
        "command-output.backend-tests.stdout",
        "command-output.backend-tests.stderr",
    )
    assert claim.producer_attempt_ref == ProviderAttemptRef(value="provider-attempt.backend")
    assert claim.expected_purpose is EvidencePurpose.IMPLEMENTATION
    assert claim.required_artifact_type == RequiredArtifactType(value="command_run")
    assert not hasattr(claim, "command_id")



def test_verification_run_builder_limits_claim_refs_to_evidence_obligation() -> None:
    claim = build_evidence_claim_from_verification_run(
        verification_run=_verification_run(),
        evidence_obligation=_evidence_obligation(artifact_type="command_run"),
        producer_attempt_ref=ProviderAttemptRef(value="provider-attempt.backend"),
        acceptance_refs=(
            AcceptanceRef(value="AC-BACKEND"),
            AcceptanceRef(value="AC-EXTRA"),
        ),
        source_surface_refs=(
            SourceSurfaceRef(value="surface.backend"),
            SourceSurfaceRef(value="surface.extra"),
        ),
        expected_purpose=EvidencePurpose.IMPLEMENTATION,
        summary="Backend command run claim.",
    )

    assert claim.acceptance_refs == (AcceptanceRef(value="AC-BACKEND"),)
    assert claim.source_surface_refs == (SourceSurfaceRef(value="surface.backend"),)



def test_verification_run_builder_uses_explicit_claim_id() -> None:
    claim = build_evidence_claim_from_verification_run(
        verification_run=_verification_run(),
        evidence_obligation=_evidence_obligation(artifact_type="command_run"),
        producer_attempt_ref=ProviderAttemptRef(value="provider-attempt.backend"),
        acceptance_refs=(AcceptanceRef(value="AC-BACKEND"),),
        source_surface_refs=(SourceSurfaceRef(value="surface.backend"),),
        expected_purpose=EvidencePurpose.IMPLEMENTATION,
        summary="Backend command run claim.",
        claim_id=EvidenceClaimRef(value="evidence-claim.custom.verification-run"),
    )

    assert claim.evidence_claim_id == EvidenceClaimRef(
        value="evidence-claim.custom.verification-run"
    )



def test_verification_run_builder_fixes_expected_purpose_from_builder_input() -> None:
    claim = build_evidence_claim_from_verification_run(
        verification_run=_verification_run(),
        evidence_obligation=_evidence_obligation(artifact_type="command_run"),
        producer_attempt_ref=ProviderAttemptRef(value="provider-attempt.backend"),
        acceptance_refs=(AcceptanceRef(value="AC-BACKEND"),),
        source_surface_refs=(SourceSurfaceRef(value="surface.backend"),),
        expected_purpose=EvidencePurpose.DIAGNOSTIC,
        summary="Diagnostic command run claim.",
    )

    assert claim.expected_purpose is EvidencePurpose.DIAGNOSTIC
    assert claim.required_artifact_type == RequiredArtifactType(value="command_run")



def test_evidence_claim_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        EvidenceClaim(**_claim_fields(unexpected="not allowed"))
